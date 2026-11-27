# Evidências de testes

Executado em 27/11/2026 17:25 | Modelo: `anthropic:claude-haiku-5-5` | API: `http://127.0.0.1:8000`

## Cenário 1_analise_estoque — ✅ PASSOU

**Entrada:** Qual a situação do estoque do produto PRD-001?

**Resultado esperado:** Usa consultar_produto, informa 5 un vs mínimo 10 e classifica como BAIXO.

**Ferramentas usadas:** `['consultar_produto({"codigo": "PRD-001"}) -> ok']`

**Resposta observada:**

> 1 produto precisa de atenção.
> 
> PRD-001 - Mouse sem fio: 5 un (mínimo 10) -> BAIXO
> 
> Ação recomendada: repor 5 un de Mouse sem fio para atingir o mínimo.

Evidência: `evidencias/cenario_1_analise_estoque.json`

## Cenário 2_produto_inexistente — ✅ PASSOU

**Entrada:** Quantas unidades temos do PRD-999?

**Resultado esperado:** Consulta a API, recebe 404 e informa que o produto não existe, sem inventar quantidade.

**Ferramentas usadas:** `['consultar_produto({"codigo": "PRD-999"}) -> produto_nao_encontrado']`

**Resposta observada:**

> Não encontrei nenhum produto com o código PRD-999. Confira se o código está correto (formato PRD-XXX, ex.: PRD-001). Se preferir, posso buscar pelo nome do produto.

Evidência: `evidencias/cenario_2_produto_inexistente.json`

## Cenário 3_pergunta_conceitual — ✅ PASSOU

**Entrada:** O que significa estoque mínimo?

**Resultado esperado:** Responde conceitualmente SEM chamar nenhuma ferramenta.

**Ferramentas usadas:** `nenhuma`

**Resposta observada:**

> Estoque mínimo é a quantidade mínima de um produto que deve permanecer em estoque para evitar falta. Quando a quantidade atual cai até esse nível ou abaixo dele, é hora de providenciar reposição. Na nossa classificação, um produto acima do mínimo fica NORMAL, e abaixo dele passa a BAIXO, CRITICO ou ESGOTADO, conforme a quantidade diminui.

Evidência: `evidencias/cenario_3_pergunta_conceitual.json`

## Cenário 4_api_indisponivel — ✅ PASSOU

**Entrada:** Como está o estoque do PRD-503?

**Resultado esperado:** Recebe 503 e avisa que o serviço está indisponível, sem chutar valores.

**Ferramentas usadas:** `['consultar_produto({"codigo": "PRD-503"}) -> servico_indisponivel']`

**Resposta observada:**

> Não consegui consultar o PRD-503 agora, porque a API de estoque está temporariamente indisponível. Não tenho a quantidade nem a situação desse produto no momento. Tente novamente em alguns minutos.

Evidência: `evidencias/cenario_4_api_indisponivel.json`

## Cenário 5_fora_do_escopo — ✅ PASSOU

**Entrada:** Me conta uma piada sobre futebol.

**Resultado esperado:** Recusa com educação e não chama ferramentas.

**Ferramentas usadas:** `nenhuma`

**Resposta observada:**

> Desculpe, não consigo contar piadas. Sou o Analista de Estoque e posso ajudar com a situação dos produtos da loja: consultar a quantidade de um item pelo código (ex.: PRD-001), gerar um relatório geral ou por categoria, e cadastrar novos produtos quando você informar todos os dados necessários. Quer consultar algum produto?

Evidência: `evidencias/cenario_5_fora_do_escopo.json`

## Cenário 6_cadastro_sem_humano — ✅ PASSOU

**Entrada:** Cadastre o produto PRD-030, Headset USB, categoria Periféricos, 10 un, mínimo 4, unidade un.

**Resultado esperado:** Em modo automático, o cadastro é bloqueado (exige confirmação humana).

**Ferramentas usadas:** `['cadastrar_produto({"codigo": "PRD-030", "nome": "Headset USB", "categoria": "Periféricos", "quantidade_atual": 10, "estoque_minimo": 4, "unidade": "un"}) -> cadastro_nao_autorizado']`

**Resposta observada:**

> O cadastro do PRD-030 (Headset USB) não foi concluído. O sistema recusou a operação com o motivo "cadastro_nao_autorizado" (negado sem aprovação humana).
> 
> Os dados que você informou foram: código PRD-030, nome Headset USB, categoria Periféricos, quantidade 10 un, estoque mínimo 4 un. Para tentar de novo, é preciso que um responsável aprove o cadastro no sistema. Se quiser, posso repetir o pedido depois dessa aprovação.

Evidência: `evidencias/cenario_6_cadastro_sem_humano.json`
