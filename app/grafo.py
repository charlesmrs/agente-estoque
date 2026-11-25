"""Fluxo principal do agente, construído com LangGraph.

    START
      │
      ▼
  validar_entrada ──(entrada inválida)──────────────┐
      │ ok                                          │
      ▼                                             │
   agente (LLM) ◄──────────────┐                    │
      │                        │                    │
      ├─(tool de leitura)──► ferramentas            │
      ├─(cadastrar_produto)─► aprovacao_humana ─► ferramentas
      └─(sem tool / limite)─► finalizar ◄───────────┘
                                 │
                                END
"""
import json
import operator
import re
from typing import Annotated, Literal, Optional, TypedDict

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import interrupt

from app import config
from app.ferramentas import (TODAS_FERRAMENTAS, cadastrar_produto_api,
                             consultar_produto_api, listar_produtos_api)
from app.prompts import SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# 1. ESTADO COMPARTILHADO: o "prontuário" que passa de nó em nó
# ---------------------------------------------------------------------------
def _juntar_dicts(a: dict, b: dict) -> dict:
    return {**(a or {}), **(b or {})}


class EstadoAgente(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]   # histórico da conversa
    pergunta: str                                          # pergunta original
    modo: Literal["interativo", "automatico"]              # automatico = sem humano (n8n)
    passos: int                                            # ciclos do LLM (condição de parada)
    bloqueado: bool                                        # entrada recusada na validação
    aprovacao: Optional[str]                               # resultado da supervisão humana
    produtos_consultados: Annotated[dict, _juntar_dicts]   # código -> dados vindos da API
    ferramentas_usadas: Annotated[list[str], operator.add] # trilha de auditoria
    resposta_final: str


# ---------------------------------------------------------------------------
# 2. LLM
# ---------------------------------------------------------------------------
def obter_llm():
    from langchain.chat_models import init_chat_model
    return init_chat_model(config.LLM_MODEL)


# ---------------------------------------------------------------------------
# 3. NÓS
# ---------------------------------------------------------------------------
PALAVRAS_INJECAO = ("ignore as instruções", "ignore suas regras", "ignore previous",
                    "system prompt", "você agora é")


def validar_entrada(estado: EstadoAgente) -> dict:
    """Guarda-corpo determinístico ANTES de gastar uma chamada de LLM."""
    pergunta = (estado.get("pergunta") or "").strip()
    if not pergunta:
        return {"bloqueado": True, "resposta_final": "Envie uma pergunta sobre o estoque."}
    if len(pergunta) > config.MAX_CARACTERES_PERGUNTA:
        return {"bloqueado": True, "resposta_final":
                f"Pergunta muito longa (máx. {config.MAX_CARACTERES_PERGUNTA} caracteres)."}
    if any(p in pergunta.lower() for p in PALAVRAS_INJECAO):
        return {"bloqueado": True, "resposta_final":
                "Não posso alterar minhas regras. Posso ajudar com consultas de estoque."}
    return {"bloqueado": False, "passos": 0,
            "messages": [SystemMessage(SYSTEM_PROMPT), HumanMessage(pergunta)]}


def criar_no_agente(llm):
    llm_com_tools = llm.bind_tools(TODAS_FERRAMENTAS)

    def agente(estado: EstadoAgente) -> dict:
        passos = estado.get("passos", 0)
        if passos >= config.MAX_PASSOS:
            # Condição de parada: não chama mais o LLM
            return {"messages": [AIMessage(
                "Atingi o limite de etapas desta análise sem concluir. "
                "Reformule a pergunta de forma mais específica.")]}
        resposta = llm_com_tools.invoke(estado["messages"])
        return {"messages": [resposta], "passos": passos + 1}

    return agente


def aprovacao_humana(estado: EstadoAgente) -> dict:
    """Supervisão humana: pausa o grafo até alguém aprovar o cadastro."""
    ultima = estado["messages"][-1]
    pedido = next(tc["args"] for tc in ultima.tool_calls if tc["name"] == "cadastrar_produto")
    if estado.get("modo") == "automatico":
        return {"aprovacao": "negado_sem_humano"}
    decisao = interrupt({"acao": "cadastrar_produto", "dados": pedido,
                         "pergunta": "Confirma o cadastro deste produto? (sim/não)"})
    aprovado = str(decisao).strip().lower() in ("s", "sim", "y", "yes")
    return {"aprovacao": "aprovado" if aprovado else "negado_pelo_humano"}


def ferramentas(estado: EstadoAgente) -> dict:
    """Executa as tools pedidas pelo LLM e devolve o resultado como ToolMessage."""
    ultima = estado["messages"][-1]
    mensagens, consultados, usadas = [], {}, []

    for chamada in ultima.tool_calls:
        nome, args = chamada["name"], chamada.get("args", {})
        if nome == "consultar_produto":
            resultado = consultar_produto_api(args.get("codigo", ""))
            if resultado["ok"]:
                consultados[resultado["produto"]["codigo"]] = resultado["produto"]
        elif nome == "listar_produtos":
            resultado = listar_produtos_api(args.get("categoria"))
            if resultado["ok"]:
                consultados.update({p["codigo"]: p for p in resultado["produtos"]})
        elif nome == "cadastrar_produto":
            if estado.get("aprovacao") == "aprovado":
                resultado = cadastrar_produto_api(args)
            else:
                resultado = {"ok": False, "erro": "cadastro_nao_autorizado",
                             "mensagem": f"Cadastro não executado ({estado.get('aprovacao')})."}
        else:
            resultado = {"ok": False, "erro": "ferramenta_desconhecida", "mensagem": nome}

        usadas.append(f"{nome}({json.dumps(args, ensure_ascii=False)}) -> "
                      f"{'ok' if resultado['ok'] else resultado['erro']}")
        mensagens.append(ToolMessage(json.dumps(resultado, ensure_ascii=False),
                                     tool_call_id=chamada["id"], name=nome))

    return {"messages": mensagens, "produtos_consultados": consultados,
            "ferramentas_usadas": usadas, "aprovacao": None}


def _texto(msg) -> str:
    c = msg.content
    if isinstance(c, list):  # alguns provedores devolvem blocos
        return "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in c)
    return str(c)


def finalizar(estado: EstadoAgente) -> dict:
    """Monta a resposta e faz uma checagem anti-alucinação simples."""
    if estado.get("bloqueado"):
        return {}
    resposta = _texto(estado["messages"][-1]).strip() or "Não consegui gerar uma resposta."

    # Todo código PRD-XXX citado deve ter vindo da API ou da própria pergunta
    citados = set(re.findall(r"PRD-\d{3}", resposta))
    conhecidos = set(estado.get("produtos_consultados", {})) | set(
        re.findall(r"PRD-\d{3}", (estado.get("pergunta") or "").upper()))
    sem_fonte = citados - conhecidos
    if sem_fonte:
        resposta += ("\n\n⚠️ Aviso de verificação: os códigos "
                     f"{', '.join(sorted(sem_fonte))} não foram confirmados pela API.")
    return {"resposta_final": resposta}


# ---------------------------------------------------------------------------
# 4. TRANSIÇÕES CONDICIONAIS
# ---------------------------------------------------------------------------
def rota_apos_validacao(estado: EstadoAgente) -> str:
    return "finalizar" if estado.get("bloqueado") else "agente"


def rota_apos_agente(estado: EstadoAgente) -> str:
    ultima = estado["messages"][-1]
    chamadas = getattr(ultima, "tool_calls", None) or []
    if not chamadas:
        return "finalizar"                      # LLM respondeu direto
    if any(c["name"] == "cadastrar_produto" for c in chamadas):
        return "aprovacao_humana"               # ação sensível
    return "ferramentas"                        # consulta à API


# ---------------------------------------------------------------------------
# 5. MONTAGEM DO GRAFO
# ---------------------------------------------------------------------------
def construir_grafo(llm=None, checkpointer=None):
    g = StateGraph(EstadoAgente)
    g.add_node("validar_entrada", validar_entrada)
    g.add_node("agente", criar_no_agente(llm or obter_llm()))
    g.add_node("aprovacao_humana", aprovacao_humana)
    g.add_node("ferramentas", ferramentas)
    g.add_node("finalizar", finalizar)

    g.add_edge(START, "validar_entrada")
    g.add_conditional_edges("validar_entrada", rota_apos_validacao,
                            {"agente": "agente", "finalizar": "finalizar"})
    g.add_conditional_edges("agente", rota_apos_agente,
                            {"ferramentas": "ferramentas",
                             "aprovacao_humana": "aprovacao_humana",
                             "finalizar": "finalizar"})
    g.add_edge("aprovacao_humana", "ferramentas")
    g.add_edge("ferramentas", "agente")
    g.add_edge("finalizar", END)
    return g.compile(checkpointer=checkpointer)


def resumo_execucao(estado: dict) -> dict:
    """Formato padronizado usado pelo CLI, pelo servidor (n8n) e pelos testes."""
    produtos = estado.get("produtos_consultados", {}) or {}
    alertas = [p for p in produtos.values() if p["situacao"] != "NORMAL"]
    return {
        "resposta": estado.get("resposta_final", ""),
        "ferramentas_usadas": estado.get("ferramentas_usadas", []),
        "passos_llm": estado.get("passos", 0),
        "alertas": [{k: p[k] for k in ("codigo", "nome", "quantidade_atual",
                                       "estoque_minimo", "situacao", "falta_para_minimo")}
                    for p in sorted(alertas, key=lambda p: p["codigo"])],
        "tem_alerta": bool(alertas),
    }
