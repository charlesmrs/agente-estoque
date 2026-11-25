"""Testes automatizados (pytest). Não precisam de chave de LLM nem da API ligada.

    python -m pytest -v
"""
import httpx
import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from app import config, ferramentas
from app.grafo import construir_grafo, resumo_execucao
from testes.apoio import LLMRoteirizado, api_falsa, chamada_tool


@pytest.fixture(autouse=True)
def usar_api_falsa():
    ferramentas._transport = httpx.MockTransport(api_falsa)
    yield
    ferramentas._transport = None


# ---------------- Regra de negócio ----------------
@pytest.mark.parametrize("qtd,minimo,esperado", [
    (0, 20, "ESGOTADO"), (5, 10, "BAIXO"), (30, 30, "BAIXO"), (40, 15, "NORMAL"), (0, 0, "ESGOTADO"),
])
def test_classificacao(qtd, minimo, esperado):
    assert ferramentas.classificar_situacao(qtd, minimo) == esperado


# ---------------- Ferramenta ----------------
def test_consulta_existente():
    r = ferramentas.consultar_produto_api("prd-001")  # normaliza minúsculas
    assert r["ok"] and r["produto"]["situacao"] == "BAIXO" and r["produto"]["falta_para_minimo"] == 5


def test_codigo_invalido_nem_chama_api():
    r = ferramentas.consultar_produto_api("ABC")
    assert r == {"ok": False, "erro": "codigo_invalido", "mensagem": r["mensagem"]}


def test_produto_inexistente():
    assert ferramentas.consultar_produto_api("PRD-999")["erro"] == "produto_nao_encontrado"


def test_servico_indisponivel():
    assert ferramentas.consultar_produto_api("PRD-503")["erro"] == "servico_indisponivel"


def test_api_desligada():
    def recusa(_req):
        raise httpx.ConnectError("recusada")
    ferramentas._transport = httpx.MockTransport(recusa)
    assert ferramentas.consultar_produto_api("PRD-001")["erro"] == "api_offline"


# ---------------- Grafo (com LLM roteirizado) ----------------
def executar(llm, pergunta, modo="automatico", checkpointer=None, cfg=None):
    g = construir_grafo(llm=llm, checkpointer=checkpointer)
    return g, g.invoke({"pergunta": pergunta, "modo": modo}, cfg or {})


def test_cenario1_usa_ferramenta():
    llm = LLMRoteirizado([chamada_tool("consultar_produto", {"codigo": "PRD-001"}),
                          AIMessage("PRD-001 Mouse sem fio: 5 un, mínimo 10 — BAIXO.")])
    _, estado = executar(llm, "Como está o PRD-001?")
    r = resumo_execucao(estado)
    assert r["ferramentas_usadas"][0].startswith("consultar_produto")
    assert r["tem_alerta"] and r["alertas"][0]["situacao"] == "BAIXO"
    assert "Aviso de verificação" not in r["resposta"]


def test_cenario3_pergunta_conceitual_sem_ferramenta():
    llm = LLMRoteirizado([AIMessage("Estoque mínimo é a quantidade de segurança...")])
    _, estado = executar(llm, "O que é estoque mínimo?")
    assert resumo_execucao(estado)["ferramentas_usadas"] == [] and llm.chamadas == 1


def test_entrada_vazia_bloqueada_sem_llm():
    llm = LLMRoteirizado([])
    _, estado = executar(llm, "   ")
    assert estado["bloqueado"] and llm.chamadas == 0


def test_anti_alucinacao_marca_codigo_sem_fonte():
    llm = LLMRoteirizado([AIMessage("O PRD-777 está esgotado.")])
    _, estado = executar(llm, "Algum produto esgotado?")
    assert "PRD-777" in estado["resposta_final"] and "Aviso de verificação" in estado["resposta_final"]


def test_condicao_de_parada(monkeypatch):
    monkeypatch.setattr(config, "MAX_PASSOS", 2)
    llm = LLMRoteirizado([chamada_tool("listar_produtos", {}, f"c{i}") for i in range(10)])
    _, estado = executar(llm, "loop")
    assert llm.chamadas == 2 and "limite" in estado["resposta_final"]


def test_cadastro_negado_em_modo_automatico():
    args = {"codigo": "PRD-020", "nome": "X", "categoria": "Y",
            "quantidade_atual": 1, "estoque_minimo": 1, "unidade": "un"}
    llm = LLMRoteirizado([chamada_tool("cadastrar_produto", args), AIMessage("Cadastro não realizado.")])
    _, estado = executar(llm, "Cadastre o PRD-020")
    assert "cadastro_nao_autorizado" in estado["ferramentas_usadas"][0]


def test_cadastro_com_aprovacao_humana():
    args = {"codigo": "PRD-020", "nome": "Teclado mecânico", "categoria": "Periféricos",
            "quantidade_atual": 15, "estoque_minimo": 5, "unidade": "un"}
    llm = LLMRoteirizado([chamada_tool("cadastrar_produto", args), AIMessage("Cadastrado.")])
    cfg = {"configurable": {"thread_id": "t1"}}
    g, estado = executar(llm, "Cadastre o PRD-020", modo="interativo",
                         checkpointer=MemorySaver(), cfg=cfg)
    assert "__interrupt__" in estado                     # pausou esperando o humano
    estado = g.invoke(Command(resume="sim"), cfg)
    assert estado["ferramentas_usadas"][0].endswith("-> ok")
