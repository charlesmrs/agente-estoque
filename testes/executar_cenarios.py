"""Executa os cenários exigidos no enunciado com o LLM REAL e a API REAL,
e grava as evidências em evidencias/ (um .json por cenário + um relatório .md).

Pré-requisitos: API do professor ligada e .env com a chave do LLM.
    python -m testes.executar_cenarios
"""
import json
from datetime import datetime
from pathlib import Path

from app import config
from app.grafo import construir_grafo, resumo_execucao

CENARIOS = [
    {"id": "1_analise_estoque", "entrada": "Qual a situação do estoque do produto PRD-001?",
     "esperado": "Usa consultar_produto, informa 5 un vs mínimo 10 e classifica como BAIXO.",
     "verificar": lambda r: any("consultar_produto" in f for f in r["ferramentas_usadas"])
                            and "BAIXO" in r["resposta"].upper()},
    {"id": "2_produto_inexistente", "entrada": "Quantas unidades temos do PRD-999?",
     "esperado": "Consulta a API, recebe 404 e informa que o produto não existe, sem inventar quantidade.",
     "verificar": lambda r: any("produto_nao_encontrado" in f for f in r["ferramentas_usadas"])
                            and not r["alertas"]},
    {"id": "3_pergunta_conceitual", "entrada": "O que significa estoque mínimo?",
     "esperado": "Responde conceitualmente SEM chamar nenhuma ferramenta.",
     "verificar": lambda r: r["ferramentas_usadas"] == []},
    # Extras (reforçam o critério 5 — falhas e limites)
    {"id": "4_api_indisponivel", "entrada": "Como está o estoque do PRD-503?",
     "esperado": "Recebe 503 e avisa que o serviço está indisponível, sem chutar valores.",
     "verificar": lambda r: any("servico_indisponivel" in f for f in r["ferramentas_usadas"])},
    {"id": "5_fora_do_escopo", "entrada": "Me conta uma piada sobre futebol.",
     "esperado": "Recusa com educação e não chama ferramentas.",
     "verificar": lambda r: r["ferramentas_usadas"] == []},
    {"id": "6_cadastro_sem_humano", "entrada":
        "Cadastre o produto PRD-030, Headset USB, categoria Periféricos, 10 un, mínimo 4, unidade un.",
     "esperado": "Em modo automático, o cadastro é bloqueado (exige confirmação humana).",
     "verificar": lambda r: not any(f.startswith("cadastrar_produto") and f.endswith("-> ok")
                                    for f in r["ferramentas_usadas"])},
]


def main():
    pasta = Path("evidencias")
    pasta.mkdir(exist_ok=True)
    grafo = construir_grafo()
    linhas = [f"# Evidências de testes\n\nExecutado em {datetime.now():%d/%m/%Y %H:%M} "
              f"| Modelo: `{config.LLM_MODEL}` | API: `{config.API_ESTOQUE_URL}`\n"]

    for c in CENARIOS:
        estado = grafo.invoke({"pergunta": c["entrada"], "modo": "automatico"}, {"recursion_limit": 25})
        r = resumo_execucao(estado)
        passou = c["verificar"](r)
        registro = {"cenario": c["id"], "entrada": c["entrada"], "esperado": c["esperado"],
                    "observado": r, "resultado": "PASSOU" if passou else "FALHOU",
                    "timestamp": datetime.now().isoformat(timespec="seconds")}
        (pasta / f"cenario_{c['id']}.json").write_text(
            json.dumps(registro, ensure_ascii=False, indent=2), encoding="utf-8")

        linhas += [f"## Cenário {c['id']} — {'✅ PASSOU' if passou else '❌ FALHOU'}\n",
                   f"**Entrada:** {c['entrada']}\n", f"**Resultado esperado:** {c['esperado']}\n",
                   f"**Ferramentas usadas:** `{r['ferramentas_usadas'] or 'nenhuma'}`\n",
                   f"**Resposta observada:**\n\n> " + r["resposta"].replace("\n", "\n> ") + "\n",
                   f"Evidência: `evidencias/cenario_{c['id']}.json`\n"]
        print(f"{'PASSOU' if passou else 'FALHOU':7} {c['id']}")

    (pasta / "RELATORIO_TESTES.md").write_text("\n".join(linhas), encoding="utf-8")
    print("\nRelatório: evidencias/RELATORIO_TESTES.md")


if __name__ == "__main__":
    main()
