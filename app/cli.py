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


def perguntar_com_seguranca(grafo, pergunta: str) -> dict | None:
    """Executa o agente e transforma falhas do LLM em mensagem amigável (sem traceback)."""
    try:
        return perguntar(grafo, pergunta)
    except KeyboardInterrupt:
        raise
    except Exception as e:
        nome = type(e).__name__
        if "Connection" in nome or "Timeout" in nome:
            motivo = "não foi possível conectar ao serviço do LLM (verifique a internet)."
        elif "Authentication" in nome or "Permission" in nome:
            motivo = "a chave da API foi recusada (confira ANTHROPIC_API_KEY no .env)."
        elif "RateLimit" in nome:
            motivo = "limite de uso da API atingido; aguarde e tente de novo."
        else:
            motivo = f"erro inesperado ao consultar o LLM ({nome})."
        print(f"\n⚠️  O agente não conseguiu responder: {motivo}")
        print("Nenhum dado foi inventado e nenhuma alteração foi feita.")
        return None


def main():
    grafo = construir_grafo(checkpointer=MemorySaver())
    if len(sys.argv) > 1:
        r = perguntar_com_seguranca(grafo, " ".join(sys.argv[1:]))
        if r:
            print(r["resposta"])
            print("\n[ferramentas]", r["ferramentas_usadas"] or "nenhuma")
        return
    print("Analista de Estoque — digite 'sair' para encerrar.")
    while True:
        pergunta = input("\nVocê: ").strip()
        if pergunta.lower() in ("sair", "exit", "quit"):
            break
        r = perguntar_com_seguranca(grafo, pergunta)
        if r:
            print(f"\nAgente: {r['resposta']}")
            print(f"[ferramentas: {r['ferramentas_usadas'] or 'nenhuma'} | passos LLM: {r['passos_llm']}]")


if __name__ == "__main__":
    main()