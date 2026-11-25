"""Servidor HTTP do agente — é a "porta" por onde o n8n conversa com o Python.

Uso:
    python -m uvicorn app.servidor:app --port 8001

POST /analisar  {"pergunta": "..."}  ->  {"resposta", "alertas", "tem_alerta", ...}

Roda em modo "automatico": como não há humano para aprovar, qualquer pedido
de cadastro é negado automaticamente (o agente só faz leituras por aqui).
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.grafo import construir_grafo, resumo_execucao

app = FastAPI(title="Agente de Estoque")
_grafo = None


class Pedido(BaseModel):
    pergunta: str = Field(..., min_length=1, max_length=500,
                          examples=["Quais produtos estão com estoque baixo ou esgotado?"])


def grafo():
    global _grafo
    if _grafo is None:
        _grafo = construir_grafo()
    return _grafo


@app.get("/health")
def health():
    return {"status": "ok", "service": "agente-estoque"}


@app.post("/analisar")
def analisar(pedido: Pedido):
    try:
        estado = grafo().invoke({"pergunta": pedido.pergunta, "modo": "automatico"},
                                {"recursion_limit": 25})
    except Exception as e:  # ex.: chave do LLM inválida
        raise HTTPException(status_code=502, detail=f"Falha ao executar o agente: {type(e).__name__}")
    return {"pergunta": pedido.pergunta, **resumo_execucao(estado)}
