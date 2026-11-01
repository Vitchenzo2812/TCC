"""Junta os resultados de avaliação dos lotes em uma visão única, por amostra.

Não escreve nada em data/raw. A reavaliação serial substitui o resultado da paralela só na visão
consolidada; as duas execuções continuam guardadas.
"""
import json
import re

from common import PROCESSED, RAW, read_jsonl

LOTS = ["full_lot1", "full_lot2"]
MBPP_RUN = "full_lot1"
LEVELS = {("mbpp", None): 1, ("lcb", "easy"): 2, ("lcb", "medium"): 3, ("lcb", "hard"): 4}


def load_samples() -> dict:
    """{(benchmark, problem_id, sample_idx): amostra} de samples.jsonl dos lotes."""
    out = {}
    for lot in LOTS:
        for s in read_jsonl(PROCESSED / lot / "samples.jsonl"):
            key = (s["benchmark"], s["problem_id"], s["sample_idx"])
            assert key not in out, f"amostra duplicada: {key}"
            out[key] = s
    return out


def load_lcb() -> dict:
    """{(question_id, sample_idx): resultado}; a reavaliação mais recente vale sobre a paralela."""
    out = {}
    for lot in LOTS:
        for d in sorted((RAW / lot).glob("lcb_eval_paralelo_*")):
            for r in read_jsonl(d / "per_sample.jsonl"):
                key = (r["question_id"], r["sample_idx"])
                assert key not in out, f"resultado duplicado: {key}"
                out[key] = r
        for d in sorted((RAW / lot).glob("lcb_eval_serial_*")):
            for r in read_jsonl(d / "per_sample.jsonl"):
                out[(r["question_id"], r["sample_idx"])] = dict(r, reavaliada=True)
    return out


def load_mbpp() -> dict:
    """{(task_id, sample_idx): resultado do EvalPlus}; aprovada = passou em base e plus.

    Amostras que aprovaram em todas as repetições seriais de mbpp_flaky.py eram estouros espúrios da
    execução paralela (o EvalPlus os registra como "fail") e contam como aprovadas (roteiro, seção 9).
    """
    path = PROCESSED / MBPP_RUN / "evalplus" / "mbpp_samples-sanitized_eval_results.json"
    results = json.loads(path.read_text(encoding="utf-8"))["eval"]
    out = {(task_id, k): r for task_id, rs in results.items() for k, r in enumerate(rs)}
    for d in sorted((RAW / MBPP_RUN).glob("mbpp_flaky_*")):
        for x in read_jsonl(d / "per_sample.jsonl"):
            if x["aprovacoes"] == x["repeticoes"]:
                out[(x["task_id"], x["sample_idx"])].update({f"{x['suite']}_status": "pass", "reavaliada": True})
    return out


def load_mbpp_reexec() -> dict:
    dirs = sorted((RAW / MBPP_RUN).glob("mbpp_reexec_*"))
    assert dirs, "rode scripts/mbpp_reexec.py no contêiner tcc-evalplus primeiro"
    return {(r["task_id"], r["sample_idx"]): r for r in read_jsonl(dirs[-1] / "per_sample.jsonl")}


def lcb_manifestation(r: dict) -> tuple:
    """(manifestação, detalhe) a partir do código de erro e dos metadados do LCB."""
    code, meta = r["error_code"], r["metadata"]
    error = meta.get("error") or meta.get("error_message") or ""
    if code == -2:
        return "resposta_errada", meta.get("error_message", "")
    if code in (-3, -5):
        return "tempo_limite", "estouro global do verificador" if code == -5 else "TimeoutException"
    if code in (-1, -4):
        module = re.search(r"No module named '([^']+)'", error)
        if module:
            return "excecao", f"ModuleNotFoundError: {module.group(1)}"
        name = re.match(r"\w+", error)
        if code == -1 or (name and name.group() in ("SyntaxError", "IndentationError", "TabError")):
            return "erro_sintaxe", error[:300]
        return "excecao", error[:300]
    raise ValueError(f"código de erro inesperado: {code} em {r['question_id']}/{r['sample_idx']}")
