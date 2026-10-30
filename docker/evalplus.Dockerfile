# Imagem de avaliação do MBPP+ (EvalPlus). O código gerado pelo modelo só roda aqui dentro.
FROM python:3.11.11-slim

RUN pip install --no-cache-dir evalplus==0.3.1
# evalplus.sanitize carrega também o HumanEval+; baixado no build para a avaliação rodar com --network none.
RUN python -c "from evalplus.data import get_human_eval_plus; get_human_eval_plus()"

# Dataset fixado (MBPP+ v0.2.0), montado em /work/data/raw/datasets em tempo de execução.
ENV MBPP_OVERRIDE_PATH=/work/data/raw/datasets/MbppPlus-v0.2.0.jsonl
WORKDIR /work
