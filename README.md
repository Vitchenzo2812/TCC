# Falhas funcionais do Claude Opus 5.5 na geração de código Python: pacote de replicação

Estudo de caso único (Runeson & Höst, 2009). O caso é o modelo `claude-opus-5-5`, avaliado no MBPP+ (EvalPlus v0.2.0, 378 problemas) e nos problemas acrescentados na release `v6` do LiveCodeBench (175 problemas), com 5 amostras por problema.

> Em construção. As fases ainda não executadas estão marcadas como *pendente*.

## Requisitos
- Python ≥ 3.10 para a geração; Docker para a avaliação (o código gerado pelo modelo **só** roda em contêiner)
- `ANTHROPIC_API_KEY` no ambiente (ver `.env.example`; nunca versionar `.env`)

## Fase 0: ambiente
```bash
python -m venv .venv-gen && .venv-gen/Scripts/pip install anthropic pyyaml pandas openpyxl scikit-learn statsmodels numpy
python -m venv .venv-evalplus && .venv-evalplus/Scripts/pip install evalplus==0.3.1   # só para baixar o MBPP+
git clone https://github.com/LiveCodeBench/LiveCodeBench.git && git -C LiveCodeBench checkout 28fef95ea8c9f7a547c8329f2cd3d32b92c1fa24
mkdir -p data/raw/datasets
curl -L -o data/raw/datasets/lcb_test6.jsonl https://huggingface.co/datasets/livecodebench/code_generation_lite/resolve/main/test6.jsonl
.venv-evalplus/Scripts/python -c "from evalplus.data.mbpp import _ready_mbpp_plus_path as p; print(p())"   # copiar para data/raw/datasets/
docker build -f docker/evalplus.Dockerfile -t tcc-evalplus:0.3.1 .
docker build -f docker/lcb.Dockerfile -t tcc-lcb:28fef95 .
```
Conferir os hashes dos datasets com os de `config/params.yaml`.

## Fase 1: piloto
```bash
cd scripts
../.venv-gen/Scripts/python generate.py select-pilot                       # -> config/pilot_ids.json (semente 42)
../.venv-gen/Scripts/python generate.py sync --run pilot --ids config/pilot_ids.json
../.venv-gen/Scripts/python generate.py retry --run pilot
../.venv-gen/Scripts/python extract_code.py --run pilot
../.venv-gen/Scripts/python generate.py cost --run pilot
```
Avaliação do piloto: *pendente*.

## Fases 2 a 7
*Pendente.*

## Estrutura
Ver a seção 4 do roteiro. `data/raw/` é de escrita única: os scripts abrem os arquivos em modo `x` e falham se o arquivo já existir.
