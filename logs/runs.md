# Diário de execuções

## 2026-10-29: Fase 0 (ambiente)

**Hardware:** AMD Ryzen 5 7600 (6 núcleos / 12 threads), 31 GB de RAM, Windows 10 Pro 19045.
**Docker:** Desktop 28.0.1 (backend WSL2). Contêineres de avaliação com `--cpus=2 --memory=4g`.

**Decisão sobre o ambiente (aprovada pelos pesquisadores):** a geração (só chamadas à API, sem executar código gerado) roda no Python 3.14.5 do Windows (`.venv-gen`). Toda a avaliação roda em imagens Docker Linux fixadas, sem Ubuntu no WSL:
- `tcc-evalplus:0.3.1` (`docker/evalplus.Dockerfile`): python:3.11.11-slim + evalplus 0.3.1
- `tcc-lcb:28fef95` (`docker/lcb.Dockerfile`): python:3.11.11-slim + LiveCodeBench no commit `28fef95ea8c9f7a547c8329f2cd3d32b92c1fa24`, instalado com `--no-deps` (sem torch/vllm, que só servem para inferência local)

**Versões:** anthropic SDK 2.3.0 (`.venv-gen`); evalplus 0.3.1; LiveCodeBench `28fef95`.

**Datasets** (em `data/raw/datasets/`, fora do git por tamanho):
| Arquivo | Origem | Problemas | sha256 |
|---|---|---|---|
| `MbppPlus-v0.2.0.jsonl` | release v0.2.0 do evalplus/mbppplus_release | 378 | `ee1701c9…c413` |
| `lcb_test6.jsonl` | huggingface.co/datasets/livecodebench/code_generation_lite, `test6.jsonl` (o que a v6 acrescentou) | 175 (easy 43, medium 52, hard 80); 2025-01-04 a 2025-04-06; AtCoder 112, LeetCode 63 | `bb4c364f…f1f5` |

Total: 553 problemas × 5 = 2.765 amostras.

**Orçamento máximo (regra 2.7):** US$ 100.

**Decisões e desvios registrados:**
1. Sem `fallbacks` de recusa: uma recusa seria respondida por outro modelo, o que contaminaria o caso. O parâmetro também é rejeitado pela Batch API.
2. Sem `response_prefix` (prefill) do EvalPlus: o provider Anthropic do próprio EvalPlus não o envia, e o Opus 5.5 rejeita prefill.
3. `custom_id` = `<benchmark>__<problem_id com "/" trocado por "-">__<sample_idx>`, porque a Batch API não aceita "/". O mapeamento exato fica em `batch_requests.jsonl`.
4. Prompt do LCB: estilo `LMStyle.Claude3` (system + user), conferido com `scripts/check_lcb_prompts.py`.

**Piloto:** `config/pilot_ids.json`, semente 42.
- MBPP+: Mbpp/773, 227, 116, 415, 391, 301, 250, 99, 20, 797
- LCB easy: abc395_b, 3731, abc397_a
- LCB medium: abc388_c, 3720, 3714
- LCB hard: 3762, abc390_e, abc390_g, arc192_e

**Questões de formato encontradas antes do piloto (a resolver nele):**
- `evalplus.evaluate` exige amostras para TODOS os problemas do dataset (`assert len(completion_id) == len(problems)`). No piloto, usar `MBPP_OVERRIDE_PATH` apontando para um subconjunto com os 10 problemas.
- `lcb_runner.runner.custom_evaluator` exige `len(custom_outputs) == len(benchmark)` e carrega o dataset do Hugging Face via script de carga (`trust_remote_code`, `datasets<4`). Com `--release_version release_v6` sem filtro de data, o benchmark tem v1–v6 inteiros. Testar `--start_date`, que deve reproduzir exatamente os 175 problemas do `test6`.

**Verificação dos prompts do LCB:** `scripts/check_lcb_prompts.py` no contêiner `tcc-lcb:28fef95` resultou em 175/175 prompts idênticos aos de `format_prompt_generation(..., LMStyle.Claude3)`. A imagem fixa `anthropic==0.42.0` porque o LCB importa `anthropic.HUMAN_PROMPT`, removido nos SDKs recentes (afeta só a importação, não a avaliação).

## 2026-10-29: Fase 1 (piloto), primeira tentativa de envio

`generate.py batch-submit --run pilot` retornou **403 permission_error**: a credencial do `.env` é um token OAuth de assinatura do Claude (prefixo `sk-ant-oat`), não uma chave de API do Console (`sk-ant-api03-…`). Esse tipo de token não tem o escopo de Batch API (`user:batch`/`workspace:inference`). Nenhuma requisição foi processada e não houve custo. O arquivo de requisições gravado antes da falha foi renomeado para `data/raw/pilot/batch_requests.FALHOU_403_20261029.jsonl` e mantido como registro.

Segunda tentativa (nova chave, prefixo `sk-ant-usr-`, com acesso à Batch API confirmado por `batches.list`): **400 invalid_request_error**, "credit balance is too low". Nenhuma requisição processada, sem custo, nenhum arquivo bruto gravado.

Terceira tentativa: lote `msgbatch_01JgEkbzgwx5XmSDVNaL4N1M` (100 requisições), enviado às 22:42 UTC e concluído em menos de 5 min. 100 com sucesso, 0 com erro.

## 2026-10-29: resultados do piloto

**Geração**
- 100/100 com `stop_reason == "end_turn"`: 0 truncadas, 0 recusas, 0 sem código. Todas as respostas trazem `model == "claude-opus-5-5"` e todos os blocos de código vieram rotulados como `python`.
- Tokens (média por amostra, entrada / saída): MBPP+ 109 / 391 (máx. 765); LCB fácil 755 / 277 (máx. 372); LCB médio 801 / 605 (máx. 950); LCB difícil 792 / 2.228 (máx. 4.309). O `max_tokens = 64000` fica muito acima do observado.
- Custo real do piloto: 44.650 tokens de entrada + 77.370 de saída (21.383 de raciocínio) ≈ **US$ 0,86** (Batch API).
- **Projeção da rodada completa (553 × 5, Batch API): US$ 20,27**, abaixo do orçamento de US$ 100. A incerteza maior está nos 80 problemas difíceis do LCB (só 4 no piloto).

**Achado: raciocínio ausente em 63% das amostras.** Com `effort: medium`, o pensamento adaptativo não raciocinou em 63/100 amostras (`thinking_tokens == 0`, nenhum bloco `thinking`): 27/50 no MBPP+ e 36/50 no LCB. Não é falha de extração. Consequência para a etapa 2 da codificação: o `resumo_raciocinio` só existirá em parte das falhas; registrar "sem raciocínio" como valor próprio, não como dado faltante.

**Avaliação**
- EvalPlus (`MBPP_OVERRIDE_PATH` = subconjunto com os 10 problemas do piloto; `sanitize` + `evaluate`, `--network none`): pass@1 **base 1,000 / plus 0,900**. Única falha: **Mbpp/415**, 5/5 amostras reprovam no plus com a mesma entrada `[1000000, 2000000, 3000000, 4000000, 4000000]`. É uma falha sistemática que se encaixa no critério de *suspeita de defeito do benchmark* da seção 10.4; a decisão é dos pesquisadores.
- Ordem das amostras no `eval_results.json` do EvalPlus confirmada: a posição na lista de cada `task_id` corresponde ao `sample_idx` (conferido pelo texto da solução, 50/50).
- A imagem do EvalPlus precisou do HumanEval+ embutido no build: o `evalplus.sanitize` carrega os dois datasets e falhava sem rede.
- LCB (`scripts/lcb_eval.py`, verificador do próprio LCB, timeout 6 s, 12 processos): pass@1 **0,98** (49/50). Única reprovação: `arc192_e` amostra 3, **Time Limit Exceeded** (código −3; o estouro de tempo é uma categoria própria no LCB).
- **Reavaliação serial** (`--serial --only`): `arc192_e`/3 **aprovada** (2,16 s, contra o limite de 6 s), portanto não conta como estouro real. Causa provável: 12 processos de avaliação disputando 2 CPUs.

**Respostas às perguntas do piloto (seção 7.3)**
- Códigos de erro do LCB: −2 resposta errada; −3 estouro de tempo; −4 exceção em tempo de execução **ou** erro de compilação (distinguidos pela mensagem: `metadata.error` traz o tipo da exceção; erro de sintaxe vem como "Error during testing: <mensagem do compilador>"); −5 estouro do tempo global (sem metadado).
- Restringir o LCB à v6: `scripts/lcb_eval.py` avalia diretamente os 175 problemas do `test6.jsonl` local com `CodeGenerationProblem.get_evaluation_sample` + `codegen_metrics`, as mesmas funções que o `custom_evaluator` chama. Evita o carregamento do Hugging Face (script de carga, `datasets<4`, rede) e o `assert` de tamanho, que impedia avaliar o piloto. O `custom_evaluator` com `--start_date` não foi testado. **Decisão pendente dos pesquisadores.**
- `code_list` com 5 códigos: aceito pelo `codegen_metrics`. O `lcb_eval.py` avalia cada amostra separadamente (k = 1), e o pass@1 do problema é c/5, calculado em `metrics.py`.

**Pontos para decisão dos pesquisadores antes da Fase 2**
1. Aprovar o custo projetado (~US$ 20).
2. Aprovar o `lcb_eval.py` no lugar do `custom_evaluator`.
3. Paralelismo da avaliação do LCB: usar 2 processos (= `--cpus`) na rodada completa, mantendo a reavaliação serial de todo estouro de tempo.
4. **Taxa de falhas baixa:** no piloto, só 1 dos 20 problemas teve falha real, e essa falha é suspeita de defeito do benchmark. Se a proporção se mantiver, o número de falhas codificáveis pode ficar pequeno (dezenas). Isso é parte do resultado, mas afeta o poder da análise qualitativa e a estimativa do Kappa.

## 2026-10-29: decisão de desenho, LCB ampliado para a release_v6 completa

**Decisão (pesquisadores, antes da Fase 2 e antes de qualquer resultado da rodada completa):** usar os 1.055 problemas da `release_v6` do LiveCodeBench (arquivos `test.jsonl` a `test6.jsonl`), e não só os 175 acrescentados na v6. Justificativa: (1) é a delimitação descrita no texto do TCC (seção 2.3 e objetivo a); (2) o piloto mostrou taxa de falha baixa, e as falhas tendem a se concentrar em programação competitiva; (3) permite analisar a taxa de falha pela data do problema (2023–2025) como indício de contaminação, no espírito de Jain et al. (2025). A decisão vem do **piloto**, não da rodada completa; a rodada completa ainda não tinha sido executada.

| Arquivo | Problemas | sha256 |
|---|---|---|
| `lcb_test.jsonl` | 400 | `2bd02b38beb48e8c46b5b9987095d999ff38cd8efc255ea5d58974317c48f63f` |
| `lcb_test2.jsonl` | 111 | `095df7c5daf15f882c51a9deb84085cff1e073495a5dbcf95015a564d485f3a3` |
| `lcb_test3.jsonl` | 101 | `28ed26cc83363ce3f1fe2d5fad9f8393077beb1907b167a31bd3b32f80801b79` |
| `lcb_test4.jsonl` | 101 | `d711138ddaebfcf5f8ec6a4283ee677298c0f5c5d374a235af92aaf0584510da` |
| `lcb_test5.jsonl` | 167 | `7f77571c2a6df0c2a72a3277650309f67e01e0008e18117e624633df53f81214` |
| `lcb_test6.jsonl` | 175 | `bb4c364f71921c4495a6ad15abe1a927350b720009f4933e2e71f8af0f6fd1f5` |

Release completa: 1.055 problemas (easy 322, medium 383, hard 350; AtCoder 602, LeetCode 444, CodeForces 9; 2023-05-07 a 2025-04-06). Nenhum `question_id` duplicado. `check_lcb_prompts.py`: **1.055/1.055** prompts idênticos ao LCB.

**Projeção (custo por amostra do piloto): US$ 71,13** para 1.433 problemas × 5 (Batch API). Incerteza maior nos difíceis (base: 4 problemas no piloto).

**Execução em lotes, por limite de saldo:** a ordem dos problemas foi sorteada uma única vez (`config/lots/order.json`: MBPP+ em ordem, depois LCB embaralhado com semente 42), e cada lote pega os próximos problemas dessa ordem até um custo estimado. A divisão não depende de nenhum resultado; os parâmetros são idênticos em todos os lotes.
- Lote 1 (`config/lots/lot1.json`): 464 problemas (MBPP+ 378; LCB easy 30, medium 27, hard 29), estimativa US$ 12,95.

**Avaliação do LCB:** `lcb_eval.py` em blocos (`--chunk i/n`), porque os testes privados da release completa (~4,4 GB) não cabem de uma vez no contêiner de 4 GB; `--workers 2` (= `--cpus`), com reavaliação serial de todo estouro de tempo.

## 2026-10-29/30: lote 1 da rodada completa (`full_lot1`)

**Geração:** lote `msgbatch_019kEAvQ9n2ydQKjvz7aCGkP`, 2.320 requisições (464 problemas × 5). 2.320 com sucesso, 0 com erro; extração: 2.320 `ok` (0 truncadas, 0 recusas, 0 sem código).
- **Custo real: US$ 10,88** (estimativa: US$ 12,95).
- Custo médio por amostra (US$): MBPP+ 0,0040; LCB easy 0,0030; medium 0,0064; hard 0,0137 (o piloto tinha superestimado os difíceis: 0,0239).
- **Estimativa para os 969 problemas restantes do LCB** (hard 321, medium 356, easy 292), com os custos do lote 1: **US$ 37,73**. A rodada completa deve ficar em ~US$ 49.

**MBPP+ completo (378 problemas, todos no lote 1):** pass@1 **base 0,991 / plus 0,875**.
- 57/378 problemas com ≥ 1 amostra reprovada no plus (237 amostras reprovadas).
- Recorrência: 40 sistemáticos (5/5) e 17 ocasionais (1/5: 8; 2/5: 2; 3/5: 3; 4/5: 4).
- Só 6 problemas falham já nos testes base; os demais só aparecem com os testes ampliados do EvalPlus.
- Expectativa: parte dos 40 sistemáticos deve ser defeito do benchmark (triagem pelos pesquisadores, seção 11).
- O aviso "N samples to be tested" do EvalPlus é a mensagem periódica de progresso, não um erro; a avaliação foi concluída.

**LCB do lote 1 (86 problemas):**
- Primeira tentativa num único contêiner de 4 GB: **encerrada por falta de memória** em 324/430 amostras, sem traceback e sem resultado gravado. O verificador do LCB copia os casos de teste do problema para cada subprocesso, e os difíceis têm entradas grandes. Reexecutado em 10 blocos (`--chunk i/10`, `--workers 2`): todos com exit 0.
- pass@1: easy **1,000** (0/30 problemas com falha); medium **0,941** (2/27: um 3/5 e um 5/5); hard **0,959** (2/29: um 1/5 e um 5/5).
- Manifestações (14 amostras reprovadas): 6 exceção ou erro de compilação, 6 resposta errada, 2 estouro de tempo.
- **Reavaliação serial** dos 2 estouros (`abc363_c` amostras 1 e 4): **ambos confirmados** como estouro real.

**Saldo:** US$ 20,00 − 0,86 (piloto) − 10,88 (lote 1) ≈ **US$ 8,26** restantes.

## 2026-10-30: lote 2 da rodada completa (`full_lot2`) e estouro do saldo

**Geração:** lote `msgbatch_01FfLwRT6nf4tX5v8JAiD2xf`, 4.845 requisições (969 problemas do LCB × 5), enviado às 00:08 UTC e concluído às 00:17 UTC. 4.845 com sucesso, 0 com erro.

**Custo real: US$ 50,59**, contra a estimativa de US$ 37,73 (+34%). Por dificuldade (US$/amostra): easy 0,0030 (total 4,39), medium 0,0070 (12,48), **hard 0,0210 (33,71)**. Os difíceis custaram ~53% a mais por amostra que no lote 1 (0,0137, base de só 29 problemas), com uma cauda longa: 41 amostras acima de 10 mil tokens de saída (máx. 31.068).

**Consequência:** saldo de créditos negativo em **−US$ 7** (US$ 20 + 35 de créditos − 62,33 de uso). A Batch API processou o lote inteiro mesmo ultrapassando o saldo.
**Erro de planejamento** (registrado como lição): a margem recomendada (~14%) foi pequena para uma distribuição de custo com cauda longa, estimada a partir de poucos problemas difíceis. Deveria ter sido maior, ou o lote 2 deveria ter sido dividido de novo.

**Custo total da geração (todas as fases): US$ 62,33** (piloto 0,86 + lote 1 10,88 + lote 2 50,59), dentro do orçamento de US$ 100. **A geração está completa:** 1.433 problemas × 5 = 7.165 amostras. Não há mais chamadas à API previstas no desenho.

**Avaliação do LCB do lote 2 (em andamento, pausada em 2026-10-30):** 100 blocos (`--chunk i/100`, `--workers 2`, Docker `--cpus=2 --memory=4g`). Blocos **0–58 concluídos, todos com exit 0**; interrompida a pedido no bloco 59, que não gravou saída (a escrita só ocorre ao fim do bloco). **Faltam os blocos 59–99.** Para retomar, rodar apenas os blocos sem pasta `lcb_eval_paralelo_blocoXde100_*`. Depois: juntar os resultados, reavaliar em serial os estouros de tempo (-3/-5) e registrar aqui.

**Avaliação do LCB do lote 2 (concluída em 2026-10-31):** blocos 0–99 com exit 0 e 4.845 resultados únicos. 233 amostras reprovadas na execução paralela (195 resposta errada, 36 código −4, 2 estouros). **Reavaliação serial dos 2 estouros:** `abc371_f`/1 confirmado; `abc379_g`/2 **aprovada** (estouro espúrio).

## 2026-10-31: métricas, manifestação e planilhas

**Reexecução do MBPP+ (`scripts/mbpp_reexec.py`, serial, no Docker):** 237 amostras reprovadas. O EvalPlus não informa o tipo de erro; o veredito e a entrada vêm do `untrusted_check`, e a amostra roda de novo naquela entrada com as mesmas proteções para capturar exceção, estouro ou saída.

**Correção de falsos negativos do MBPP+:** 6 das 237 amostras passaram na reexecução. `scripts/mbpp_flaky.py` repetiu cada uma 20 vezes, em serial, nos dois conjuntos: **20/20 aprovações nas 6** (`Mbpp/84` amostras 0–4 e `Mbpp/392` amostra 1), todas com a entrada `[1000000]`. Eram estouros espúrios por carga: `evalplus.evaluate` usa `--parallel 2`, e um `TimeoutException` dentro de uma entrada é registrado como `fail`, não como `timeout`. Pela seção 9 do roteiro, contam como aprovadas. O arquivo original do EvalPlus não foi alterado; a correção é aplicada em `results.py`. Efeito: os números do lote 1 mudam de 57 para **55 problemas com falha** e de 237 para **231 amostras reprovadas**, e pass@1 plus de 0,875 para **0,878**.

**Bibliotecas de terceiros no código gerado do LCB:** `numpy` (388 amostras), `sortedcontainers` (6) e `scipy` (5 importações em 4 amostras). A imagem não traz `scipy` nem `sortedcontainers`.
- `sortedcontainers` não está nos arquivos de dependência do LCB, então a reprovação de `3527`/4 por `ModuleNotFoundError` é igual à do ambiente oficial. As 5 amostras de `3000` importam dentro de um bloco indentado e passaram.
- `scipy` está nos lockfiles do LCB, mas não na imagem. As 4 amostras (`abc301_e`/1, `abc334_e`/1–3) **passaram mesmo assim**, então nenhuma reavaliação foi necessária.
- A versão do `numpy` da imagem não foi fixada na do lockfile do LCB (ameaça menor à validade).

**Resultados finais (7.165 amostras, todas `ok`: 0 truncadas, 0 recusas, 0 sem código):**
| Grupo | Problemas | Pass@1 | IC 95% bootstrap | Problemas com falha |
|---|---|---:|---|---:|
| MBPP+ base | 378 | 0,991 | 0,983–0,998 | 6 |
| MBPP+ plus | 378 | 0,878 | 0,845–0,908 | 55 |
| LCB geral | 1.055 | 0,953 | 0,941–0,965 | 67 |
| LCB easy | 322 | 0,993 | 0,983–1,000 | 3 |
| LCB medium | 383 | 0,963 | 0,944–0,980 | 18 |
| LCB hard | 350 | 0,906 | 0,876–0,934 | 46 |

- **Falhas:** 122 problemas (55 MBPP+, 67 LCB) e 477 amostras reprovadas. Recorrência: **80 sistemáticas, 42 ocasionais**. A mesma manifestação aparece em todas as amostras reprovadas em 118 de 122 problemas.
- **Manifestação (amostras):** 406 resposta errada, 67 exceção, 4 estouro de tempo, **0 erro de sintaxe**.
- **Suspeita de defeito do benchmark (sugestão mecânica):** 50 problemas. A decisão é dos pesquisadores, e a amostra efetiva de causas depende dela.

**Planilhas (`scripts/build_sheet.py`):** 111 falhas na amostra oficial e 11 na calibração, sorteadas com semente 42, proporcionalmente ao nível de complexidade e com ao menos uma de cada nível. `agreement.py` foi testado com dados sintéticos, fora do repositório.

**Limitação:** o conjunto de sensibilidade pós-corte (opcional, AtCoder) não foi executado, por decisão de não haver mais gastos com a API. Fica declarado como limitação.
