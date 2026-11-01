"""Repete a avaliação das amostras que reprovaram no EvalPlus e passaram em mbpp_reexec.py.

Roda SOMENTE dentro do contêiner tcc-evalplus. Usa o untrusted_check do EvalPlus, serial, nos dois
conjuntos, e mede o tempo de cada entrada contra o limite. Serve para separar estouro espúrio da
execução paralela de comportamento não determinístico da amostra.
Saída (escrita única): data/raw/NOME/mbpp_flaky_<UTC>/per_sample.jsonl
"""
import argparse
import glob
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from evalplus.data import get_mbpp_plus, get_mbpp_plus_hash  # noqa: E402
from evalplus.eval import PASS, untrusted_check  # noqa: E402
from evalplus.eval._special_oracle import MBPP_OUTPUT_NOT_NONE_TASKS  # noqa: E402
from evalplus.evaluate import get_groundtruth  # noqa: E402

from common import PROCESSED, RAW, read_jsonl, write_once  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--repeat", type=int, default=20)
    a = ap.parse_args()
    results = json.loads((PROCESSED / a.run / "evalplus" / "mbpp_samples-sanitized_eval_results.json")
                         .read_text(encoding="utf-8"))["eval"]
    reexec = read_jsonl(Path(sorted(glob.glob(str(RAW / a.run / "mbpp_reexec_*")))[-1]) / "per_sample.jsonl")
    problems = get_mbpp_plus()
    truth = get_groundtruth(problems, get_mbpp_plus_hash(), MBPP_OUTPUT_NOT_NONE_TASKS)
    out = RAW / a.run / f"mbpp_flaky_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}" / "per_sample.jsonl"
    with write_once(out) as f:
        for x in reexec:
            if x["kind"] != "aprovada_na_reexecucao":
                continue
            task, k = x["task_id"], x["sample_idx"]
            r, p, gt = results[task][k], problems[task], truth[task]
            passed = 0
            for _ in range(a.repeat):
                ok = all(untrusted_check("mbpp", r["solution"], p[f"{s}_input"], p["entry_point"], gt[s], p["atol"],
                                         gt[f"{s}_time"], fast_check=True)[0] == PASS for s in ("base", "plus"))
                passed += ok
            rec = {"task_id": task, "sample_idx": k, "suite": x["suite"], "aprovacoes": passed, "repeticoes": a.repeat,
                   "falhou_na_entrada": str(r[f"{x['suite']}_fail_tests"])[:300],
                   "maior_tempo_referencia": max(gt[f"{x['suite']}_time"])}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            print(rec, flush=True)


if __name__ == "__main__":
    main()
