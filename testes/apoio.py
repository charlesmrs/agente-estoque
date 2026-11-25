"""Apoio aos testes automatizados: API falsa e LLM roteirizado (sem custo, sem rede)."""
import httpx
from langchain_core.messages import AIMessage

PRODUTOS = {
    "PRD-001": {"codigo": "PRD-001", "nome": "Mouse sem fio", "categoria": "Periféricos",
                "quantidade_atual": 5, "estoque_minimo": 10, "unidade": "un"},
    "PRD-002": {"codigo": "PRD-002", "nome": "Teclado USB", "categoria": "Periféricos",
                "quantidade_atual": 40, "estoque_minimo": 15, "unidade": "un"},
    "PRD-004": {"codigo": "PRD-004", "nome": "Cabo HDMI 2 m", "categoria": "Cabos e Adaptadores",
                "quantidade_atual": 0, "estoque_minimo": 20, "unidade": "un"},
}


def api_falsa(request: httpx.Request) -> httpx.Response:
    caminho = request.url.path
    if caminho == "/produtos" and request.method == "GET":
        return httpx.Response(200, json={"total": len(PRODUTOS), "produtos": list(PRODUTOS.values())})
    if caminho == "/produtos" and request.method == "POST":
        return httpx.Response(201, json=__import__("json").loads(request.content))
    codigo = caminho.rsplit("/", 1)[-1]
    if codigo == "PRD-503":
        return httpx.Response(503, json={"erro": "servico_indisponivel"})
    if codigo in PRODUTOS:
        return httpx.Response(200, json=PRODUTOS[codigo])
    return httpx.Response(404, json={"erro": "produto_nao_encontrado"})


class LLMRoteirizado:
    """Imita um chat model: devolve, em ordem, as respostas programadas."""

    def __init__(self, respostas: list[AIMessage]):
        self.respostas = list(respostas)
        self.chamadas = 0

    def bind_tools(self, _tools):
        return self

    def invoke(self, _mensagens):
        self.chamadas += 1
        return self.respostas.pop(0)


def chamada_tool(nome: str, args: dict, id_: str = "c1") -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": nome, "args": args, "id": id_}])
