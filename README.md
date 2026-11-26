# Falhas funcionais do Claude Opus 5.5 na geração de código Python: pacote de replicação

Estudo de caso único (Runeson & Höst, 2009). O caso é o modelo `claude-opus-5-5`, avaliado no MBPP+ (EvalPlus v0.2.0, 378 problemas) e na release completa `release_v6` do LiveCodeBench (1.055 problemas), com 5 soluções independentes por problema (7.165 soluções no total).

## Por onde começar (roteiro de leitura)

| Para conferir | Abra |
|---|---|
| Parâmetros de geração e versões dos benchmarks | `config/params.yaml` e `prompts/` |
| Pass@1 com IC 95% (Tabela 1) | `data/processed/metrics/pass_at_1.csv` |
| Pass@1 por trimestre do concurso | `data/processed/metrics/by_period.csv` |
| Manifestação e recorrência das falhas | `data/processed/metrics/manifestation.csv` e `recurrence.csv` |
| Raciocínio e mediana de tokens de saída por nível | `data/processed/metrics/by_thinking.csv` |
| Respostas dos codificadores A e B | `data/processed/coding/respostas/` |
| Concordância (Kappa da causa e do defeito, com IC) | `data/processed/coding/agreement.json` e `divergencias.csv` |
| Decisão final de cada falha, com a origem da decisão | `data/processed/coding/reconciliacao.csv` |
| Defeitos de benchmark e causas finais | `data/processed/metrics/defeitos_benchmark.csv` e `causas_por_*.csv` |
| Verificações por execução dos diagnósticos | `analysis/verificacoes/` |
| Categorias de causa | `analysis/codebook.md` |

## Estrutura

```
config/        parâmetros congelados, IDs do piloto e lotes da rodada completa
prompts/       modelos de prompt enviados ao modelo (Apêndice A)
docker/        imagens de avaliação (EvalPlus 0.3.1 e LiveCodeBench no commit 28fef95)
scripts/       pipeline: geração, extração, avaliação, métricas, codificação e reconciliação
data/raw/      saídas brutas da API e dos avaliadores (escrita única; os datasets não são versionados)
data/processed/
  pilot/, full_lot1/, full_lot2/   soluções extraídas e resultados por lote
  metrics/                         tabelas usadas nos Resultados
  coding/                          concordância, divergências e reconciliação
  coding/respostas/
    Planilhas vazias/  planilhas entregues aos codificadores, geradas por build_sheet.py
    Codificador A/     respostas de A (calibração, etapa 1 e etapa 2), usadas no Kappa e na reconciliação
    Codificador B/     respostas de B (calibração, etapa 1 e etapa 2), usadas no Kappa e na reconciliação
    Resposta de Ambos/ respostas de A e B lado a lado
analysis/
  codebook.md          categorias de causa
  verificacoes/        script de verificação por execução e relatórios (referência e Docker)
```

Os datasets (`data/raw/datasets/`) não são versionados, porque o do LiveCodeBench tem 134 MB, acima do limite do GitHub. Os hashes estão em `config/params.yaml` . Os logs de cada bloco da avaliação paralela do LiveCodeBench também não são versionados: os resultados desses blocos estão em `data/raw/*/lcb_eval_paralelo_*/per_sample.jsonl`.

## Sobre a codificação

- Dois codificadores: A e B. A etapa 1 foi independente; a etapa 2 incluiu os resumos do raciocínio do modelo.
- **Reconciliação:** onde A e B concordam, vale a resposta comum. Onde divergem, vale a resposta de A, exceto em 4 falhas (F063, F077, F078 e F082), nas quais vale a evidência da verificação por execução. A regra está em `scripts/reconcile.py`.
- **Desvios declarados**:
  - B converteu o texto corrido de A nas categorias do codebook, e A aprovou a conversão.
  - A leu os resumos do raciocínio antes de concluir a etapa 1.
  - O script de verificação foi escrito com auxílio de IA e executado primeiro fora do Docker. A reexecução no Docker reproduziu as 37 verificações.
- Nenhuma ferramenta de IA atribuiu causas ou decidiu defeitos: essas decisões são dos codificadores.

## Como reproduzir

A geração (fase 2) usa chamadas pagas à API, e os resultados dela já estão em `data/raw/`. O restante roda localmente e sem custo. Os comandos abaixo são para Git Bash e partem da raiz do repositório. **Todo código gerado pelo modelo roda só em contêiner, sem rede.**

**Ambiente**
```bash
python -m venv .venv-gen && .venv-gen/Scripts/pip install anthropic pyyaml pandas openpyxl scikit-learn statsmodels numpy
git clone https://github.com/LiveCodeBench/LiveCodeBench.git && git -C LiveCodeBench checkout 28fef95ea8c9f7a547c8329f2cd3d32b92c1fa24
docker build -f docker/evalplus.Dockerfile -t tcc-evalplus:0.3.1 .
docker build -f docker/lcb.Dockerfile -t tcc-lcb:28fef95 .
```
Baixe os datasets para `data/raw/datasets/` e confira os hashes com `config/params.yaml`. A geração exige `ANTHROPIC_API_KEY` em `.env`, que nunca é versionado.

**Geração (paga; um lote por vez)**
```bash
python scripts/generate.py batch-submit --run full_lot1 --ids config/lots/lot1.json
python scripts/generate.py batch-collect --run full_lot1
python scripts/extract_code.py --run full_lot1
```

**Avaliação (só em Docker)**

`to_evalplus.py` e `to_lcb.py` montam as entradas. O LiveCodeBench roda em blocos (`--chunk i/n`), e todo estouro de tempo é reavaliado em série.
```bash
MSYS_NO_PATHCONV=1 docker run --rm --network none --cpus=2 --memory=4g -v "$(pwd -W):/work" -w /opt/LiveCodeBench tcc-lcb:28fef95 python /work/scripts/lcb_eval.py --run full_lot2 --workers 2 --chunk 0/100
MSYS_NO_PATHCONV=1 docker run --rm --network none --cpus=2 --memory=4g -v "$(pwd -W):/work" -w /work tcc-evalplus:0.3.1 python scripts/mbpp_reexec.py --run full_lot1
MSYS_NO_PATHCONV=1 docker run --rm --network none --cpus=2 --memory=4g -v "$(pwd -W):/work" -w /work tcc-evalplus:0.3.1 python scripts/mbpp_flaky.py --run full_lot1
```

**Métricas, concordância e reconciliação**
```bash
python scripts/metrics.py
python scripts/manifestation.py
python scripts/agreement.py --a "data/processed/coding/respostas/Codificador A/etapa1_A.xlsx" --b "data/processed/coding/respostas/Codificador B/etapa1_B.xlsx"
python scripts/reconcile.py
```

`scripts/build_sheet.py` gera as planilhas em branco em `data/processed/coding/`. Não é preciso rodá-lo para reproduzir os resultados, e as cópias usadas estão em `respostas/Planilhas vazias/`.
