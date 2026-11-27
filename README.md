# Agente Analista de Estoque — LangGraph + n8n

Projeto avaliativo do curso **Agentes de IA (SCTEC — T2)**.

**Integrantes:** `[Seu nome]` — `[contribuição]`
**Vídeo demonstrativo:** `[link do vídeo]`

---

## 1. Problema e objetivo

Lojas precisam saber rapidamente quais produtos estão acabando. A API de estoque entrega apenas dados brutos (quantidade atual e estoque mínimo). Este agente recebe perguntas em linguagem natural, consulta a API por meio de ferramentas, classifica a situação de cada produto e responde **somente com base nos dados obtidos**. Um workflow n8n roda a verificação todos os dias e gera uma lista de reposição.

## 2. Tecnologias

Python 3.11+ · LangGraph · LangChain (`init_chat_model`) · Claude (Anthropic API) — Haiku 5.5 / Sonnet 5.5 · httpx · FastAPI/Uvicorn · n8n · pytest

## 3. Arquitetura

```
Pergunta ─► validar_entrada ─► agente (LLM) ─┬─► ferramentas ──► (volta ao agente)
              │ inválida                      ├─► aprovacao_humana ─► ferramentas
              └──────────────────────────────►└─► finalizar ─► FIM
```

| Nó | Função |
|---|---|
| `validar_entrada` | Bloqueia pergunta vazia, longa demais ou com tentativa de alterar as regras, **sem gastar LLM** |
| `agente` | LLM com as tools vinculadas; decide se consulta a API ou responde direto |
| `ferramentas` | Executa as tools, grava os produtos consultados no estado (trilha de auditoria) |
| `aprovacao_humana` | Pausa o grafo (`interrupt`) antes de qualquer cadastro; em modo automático, nega |
| `finalizar` | Monta a resposta e faz a checagem anti-alucinação (código PRD citado sem vir da API gera aviso) |

**Estado compartilhado** (`EstadoAgente`): `messages`, `pergunta`, `modo`, `passos`, `bloqueado`, `aprovacao`, `produtos_consultados`, `ferramentas_usadas`, `resposta_final`.

**Transições condicionais:** `rota_apos_validacao` e `rota_apos_agente` (tool de leitura → `ferramentas`; cadastro → `aprovacao_humana`; sem tool → `finalizar`).

**Condição de encerramento:** o agente para quando o LLM responde sem pedir ferramentas **ou** quando atinge `MAX_PASSOS` (padrão 6). Há ainda o `recursion_limit` do LangGraph como segunda trava.

### Ferramentas (`app/ferramentas.py`)

| Tool | Parâmetros | Retorno |
|---|---|---|
| `consultar_produto` | `codigo` (PRD-XXX) | produto + `situacao` + `falta_para_minimo` |
| `listar_produtos` | `categoria` (opcional) | lista com situação + resumo por situação |
| `cadastrar_produto` | 6 campos do produto | só executa após confirmação humana |

**Regra de classificação** (calculada em Python, nunca pelo LLM):

| Condição | Situação |
|---|---|
| `quantidade_atual == 0` | ESGOTADO |
| `quantidade_atual < 50% do estoque_minimo` | CRITICO (risco de parar a operação; prioridade de compra) |
| `50% do mínimo <= quantidade_atual <= estoque_minimo` | BAIXO (estar no mínimo já pede reposição) |
| `quantidade_atual > estoque_minimo` | NORMAL |

Com a base do professor: 5 NORMAL, 3 BAIXO (PRD-001, PRD-005, PRD-009), 2 CRITICO (PRD-007, PRD-011) e 2 ESGOTADO (PRD-004, PRD-008).
O nível CRITICO vem da lógica de manutenção industrial: abaixo da metade do mínimo, o risco de faltar a peça antes da reposição chegar é alto.
**Falhas tratadas:** código inválido (validado antes da chamada HTTP), 404 produto inexistente, 503 serviço indisponível, API desligada, timeout, resposta com campos faltando ou valores inválidos.

## 4. Como executar

```bash
# 1) API do professor (terminal 1)
git clone https://github.com/wangsouza/api-estoque.git && cd api-estoque
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 2) Este agente (terminal 2)
cd agente-estoque
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # e coloque sua ANTHROPIC_API_KEY

python -m app.cli                                # modo conversa
python -m app.cli "Como está o PRD-001?"         # pergunta única
```

## 5. Automação n8n

**Finalidade:** verificação diária automática. O n8n dispara (manual ou todo dia às 8h), chama o agente Python via HTTP, e se houver produtos BAIXO/ESGOTADO gera um CSV de reposição com prioridade; senão, registra "Estoque OK".

```
[Manual | Todo dia 8h] ─► HTTP POST /analisar ─► Tem alerta? ─sim─► Montar lista ─► CSV
                                                              └não─► Estoque OK
```

**Troca de dados:** o n8n envia `{"pergunta": ...}`; o Python devolve `{"resposta", "alertas", "tem_alerta", "ferramentas_usadas"}`. A lógica (LLM, estado, tools) continua toda no LangGraph.

```bash
# terminal 3 — servidor do agente
python -m uvicorn app.servidor:app --host 0.0.0.0 --port 8001
```

No n8n: *Import from File* → `n8n/workflow_alerta_estoque.json`. URL do nó HTTP:
- n8n em Docker: `http://host.docker.internal:8001/analisar` (padrão do arquivo; no Linux, inicie o contêiner com `--add-host=host.docker.internal:host-gateway`)
- n8n via `npx n8n`: troque para `http://127.0.0.1:8001/analisar`

Evidência: `evidencias/n8n_execucao.png` `[adicionar print]`.

## 6. Testes

```bash
python -m pytest -v                 # 20 testes, sem LLM e sem API (usa simuladores)
python -m testes.executar_cenarios  # cenários com LLM e API reais -> evidencias/
```

| # | Entrada | Esperado | Observado |
|---|---|---|---|
| 1 | "Qual a situação do estoque do produto PRD-001?" | consulta a API; 5 un vs mín. 10 → BAIXO | ver `evidencias/cenario_1_analise_estoque.json` |
| 2 | "Quantas unidades temos do PRD-999?" | 404 tratado; informa que não existe | ver `evidencias/cenario_2_produto_inexistente.json` |
| 3 | "O que significa estoque mínimo?" | responde sem chamar ferramenta | ver `evidencias/cenario_3_pergunta_conceitual.json` |
| 4 | "Como está o PRD-503?" | 503 tratado sem inventar | `evidencias/cenario_4_api_indisponivel.json` |
| 5 | Piada sobre futebol | recusa, fora do escopo | `evidencias/cenario_5_fora_do_escopo.json` |
| 6 | Cadastro via n8n/automático | bloqueado (exige humano) | `evidencias/cenario_6_cadastro_sem_humano.json` |

Relatório consolidado: `evidencias/RELATORIO_TESTES.md`.

## 7. Segurança e supervisão

- Chaves somente no `.env` (no `.gitignore`); `.env.example` sem segredos.
- Validação de entrada antes do LLM e validação de parâmetros antes do HTTP.
- O LLM não calcula a situação: a regra é determinística no Python.
- Cadastro (única ação que modifica dados) exige confirmação humana (`interrupt`); pelo servidor/n8n é sempre negado.
- Não há ferramenta de edição ou exclusão.

## 8. Limitações

- Checagem anti-alucinação cobre apenas códigos PRD citados, não nomes ou números soltos.
- Sem memória entre perguntas (cada execução é independente).
- Filtro de categoria depende da grafia exata com acentos.
- Servidor do agente sem autenticação: usar apenas em rede local.
- Qualidade da interpretação depende do LLM escolhido; perguntas muito vagas pedem esclarecimento.
