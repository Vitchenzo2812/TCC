# Imagem de avaliação do LiveCodeBench. O código gerado pelo modelo só roda aqui dentro.
# O pacote é instalado sem as dependências de inferência (torch, vllm, SDKs de outros provedores),
# que não são usadas na avaliação; só o verificador do LCB é necessário.
FROM python:3.11.11-slim

RUN pip install --no-cache-dir "datasets>=3.2.0,<4" numpy tqdm pebble annotated-types openai \
    # o LCB importa anthropic.HUMAN_PROMPT, removido nos SDKs recentes; 0.42.0 é o mínimo do pyproject do LCB
    anthropic==0.42.0

COPY LiveCodeBench /opt/LiveCodeBench
RUN pip install --no-cache-dir --no-deps -e /opt/LiveCodeBench

WORKDIR /work
