"""Ferramentas (tools) que o agente pode usar para falar com a API de estoque.

Regra de ouro: a CLASSIFICAÇÃO do estoque é feita aqui, em Python, de forma
determinística. O LLM só interpreta e redige; ele nunca "calcula" a situação.
Isso evita que o modelo invente ou erre a análise.

Toda ferramenta devolve um dicionário com a chave "ok":
  ok=True  -> dados confiáveis vindos da API
  ok=False -> "erro" (código estável) + "mensagem" (texto para o agente)
"""
import re
from typing import Optional

import httpx
from langchain_core.tools import tool

from app import config

PADRAO_CODIGO = re.compile(r"^PRD-\d{3}$")

# Permite que os testes troquem a rede real por uma API falsa (httpx.MockTransport)
_transport: Optional[httpx.BaseTransport] = None


def _cliente() -> httpx.Client:
    return httpx.Client(
        base_url=config.API_ESTOQUE_URL,
        timeout=config.API_TIMEOUT,
        transport=_transport,
    )


# ---------------------------------------------------------------------------
# Regra de negócio: situação do estoque
# ---------------------------------------------------------------------------
def classificar_situacao(quantidade_atual: int, estoque_minimo: int) -> str:
    """Decisão de projeto (documentada no README):
    - ESGOTADO: quantidade = 0
    - CRITICO:  abaixo da metade do mínimo (risco de parar a operação)
    - BAIXO:    da metade até o mínimo (estar no mínimo já pede reposição)
    - NORMAL:   quantidade > mínimo
    """
    if quantidade_atual == 0:
        return "ESGOTADO"
    if quantidade_atual * 2 < estoque_minimo:  # o mesmo que qtd < 50% do mínimo, sem usar decimais
        return "CRITICO"
    if quantidade_atual <= estoque_minimo:
        return "BAIXO"
    return "NORMAL"


def _enriquecer(produto: dict) -> dict:
    """Valida o JSON recebido e acrescenta a situação calculada."""
    obrigatorios = ("codigo", "nome", "quantidade_atual", "estoque_minimo")
    if not all(c in produto for c in obrigatorios):
        raise ValueError(f"Resposta da API sem campos obrigatórios: {produto}")
    qtd, minimo = produto["quantidade_atual"], produto["estoque_minimo"]
    if not isinstance(qtd, int) or not isinstance(minimo, int) or qtd < 0 or minimo < 0:
        raise ValueError(f"Quantidades inválidas na resposta da API: {produto}")
    return {
        **produto,
        "situacao": classificar_situacao(qtd, minimo),
        "falta_para_minimo": max(minimo - qtd, 0),
    }


def _erro(codigo: str, mensagem: str) -> dict:
    return {"ok": False, "erro": codigo, "mensagem": mensagem}


# ---------------------------------------------------------------------------
# Funções "puras" (testáveis sem LLM)
# ---------------------------------------------------------------------------
def consultar_produto_api(codigo: str) -> dict:
    codigo = (codigo or "").strip().upper()
    if not PADRAO_CODIGO.match(codigo):
        return _erro("codigo_invalido",
                     f"Código '{codigo}' inválido. Use o formato PRD-XXX (ex.: PRD-001).")
    try:
        with _cliente() as c:
            r = c.get(f"/produtos/{codigo}")
    except httpx.TimeoutException:
        return _erro("timeout", "A API de estoque demorou demais para responder.")
    except httpx.HTTPError:
        return _erro("api_offline", "Não foi possível conectar à API de estoque. Ela está ligada?")

    if r.status_code == 200:
        try:
            return {"ok": True, "produto": _enriquecer(r.json())}
        except (ValueError, KeyError) as e:
            return _erro("resposta_invalida", str(e))
    if r.status_code == 404:
        return _erro("produto_nao_encontrado", f"Não existe produto cadastrado com o código {codigo}.")
    if r.status_code == 503:
        return _erro("servico_indisponivel", "A API de estoque está temporariamente indisponível.")
    if r.status_code == 422:
        return _erro("codigo_invalido", f"A API recusou o código {codigo} (formato inválido).")
    return _erro("erro_inesperado", f"A API respondeu HTTP {r.status_code}.")


def listar_produtos_api(categoria: Optional[str] = None) -> dict:
    params = {"categoria": categoria.strip()} if categoria and categoria.strip() else None
    try:
        with _cliente() as c:
            r = c.get("/produtos", params=params)
    except httpx.TimeoutException:
        return _erro("timeout", "A API de estoque demorou demais para responder.")
    except httpx.HTTPError:
        return _erro("api_offline", "Não foi possível conectar à API de estoque. Ela está ligada?")
    if r.status_code != 200:
        return _erro("erro_inesperado", f"A API respondeu HTTP {r.status_code}.")
    try:
        produtos = [_enriquecer(p) for p in r.json().get("produtos", [])]
    except (ValueError, KeyError, AttributeError) as e:
        return _erro("resposta_invalida", str(e))

    resumo = {"NORMAL": 0, "BAIXO": 0, "CRITICO": 0, "ESGOTADO": 0}
    for p in produtos:
        resumo[p["situacao"]] += 1
    return {"ok": True, "total": len(produtos), "resumo": resumo,
            "filtro_categoria": categoria, "produtos": produtos}


def cadastrar_produto_api(dados: dict) -> dict:
    """Chamado SOMENTE depois da aprovação humana (ver nó aprovacao_humana)."""
    try:
        with _cliente() as c:
            r = c.post("/produtos", json=dados)
    except httpx.HTTPError:
        return _erro("api_offline", "Não foi possível conectar à API de estoque.")
    if r.status_code == 201:
        return {"ok": True, "produto": _enriquecer(r.json())}
    if r.status_code == 409:
        return _erro("produto_duplicado", f"Já existe produto com o código {dados.get('codigo')}.")
    if r.status_code == 422:
        return _erro("dados_invalidos", r.json().get("mensagem", "Dados inválidos."))
    return _erro("erro_inesperado", f"A API respondeu HTTP {r.status_code}.")


# ---------------------------------------------------------------------------
# Tools expostas ao LLM. A docstring é o que o modelo "lê" para decidir.
# ---------------------------------------------------------------------------
@tool
def consultar_produto(codigo: str) -> dict:
    """Consulta UM produto pelo código (formato PRD-XXX, ex.: PRD-001).
    Retorna nome, quantidade_atual, estoque_minimo e a situacao já calculada
    (NORMAL, BAIXO, CRITICO ou ESGOTADO). Use quando o usuário citar um código específico."""
    return consultar_produto_api(codigo)


@tool
def listar_produtos(categoria: Optional[str] = None) -> dict:
    """Lista todos os produtos (ou só de uma categoria, ex.: 'Periféricos'),
    com a situação de cada um e um resumo de quantos estão NORMAL, BAIXO, CRITICO e ESGOTADO.
    Use para perguntas gerais: 'o que está acabando?', 'relatório do estoque',
    ou quando o usuário citar um produto pelo NOME em vez do código."""
    return listar_produtos_api(categoria)


@tool
def cadastrar_produto(codigo: str, nome: str, categoria: str,
                      quantidade_atual: int, estoque_minimo: int, unidade: str) -> dict:
    """Cadastra um NOVO produto (modifica a base de dados).
    Só use se o usuário pedir explicitamente um cadastro e informar todos os campos.
    A execução fica suspensa até um humano confirmar."""
    # Nunca é executada diretamente: o grafo desvia para o nó de aprovação humana.
    return _erro("nao_autorizado", "Cadastro precisa passar pela aprovação humana.")


FERRAMENTAS_LEITURA = [consultar_produto, listar_produtos]
TODAS_FERRAMENTAS = FERRAMENTAS_LEITURA + [cadastrar_produto]
