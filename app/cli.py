"""Interface de linha de comando (modo interativo, com supervisão humana).

Uso:
    python -m app.cli                      # conversa
    python -m app.cli "Como está o PRD-001?"   # pergunta única
"""
import json
import sys
import uuid

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from app.grafo import construir_grafo, resumo_execucao


def perguntar(grafo, pergunta: str) -> dict:
    cfg = {"configurable": {"thread_id": str(uuid.uuid4())}, "recursion_limit": 25}
    estado = grafo.invoke({"pergunta": pergunta, "modo": "interativo"}, cfg)

    # Se o grafo pausou no nó aprovacao_humana, pedimos a decisão ao operador
    while "__interrupt__" in estado:
        pedido = estado["__interrupt__"][0].value
        print("\n🔒 CONFIRMAÇÃO NECESSÁRIA")
        print(json.dumps(pedido["dados"], ensure_ascii=False, indent=2))
        decisao = input(pedido["pergunta"] + " ")
        estado = grafo.invoke(Command(resume=decisao), cfg)
    return resumo_execucao(estado)


def main():
    grafo = construir_grafo(checkpointer=MemorySaver())
    if len(sys.argv) > 1:
        r = perguntar(grafo, " ".join(sys.argv[1:]))
        print(r["resposta"])
        print("\n[ferramentas]", r["ferramentas_usadas"] or "nenhuma")
        return
    print("Analista de Estoque — digite 'sair' para encerrar.")
    while True:
        pergunta = input("\nVocê: ").strip()
        if pergunta.lower() in ("sair", "exit", "quit"):
            break
        r = perguntar(grafo, pergunta)
        print(f"\nAgente: {r['resposta']}")
        print(f"[ferramentas: {r['ferramentas_usadas'] or 'nenhuma'} | passos LLM: {r['passos_llm']}]")


if __name__ == "__main__":
    main()
