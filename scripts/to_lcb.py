"""Monta o JSON do LiveCodeBench: [{"question_id", "code_list": [amostra 0..4]}].

Uso: python scripts/to_lcb.py --run NOME
Saída: data/processed/NOME/lcb/lcb_outputs.json (+ lcb_status.json com o status de cada amostra).
Amostras sem código entram como "" (reprovam na compilação); truncadas e recusas são excluídas em metrics.py.
"""
import argparse
import json
from collections import defaultdict

from common import PROCESSED, load_params, read_jsonl, write_once


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    a = ap.parse_args()
    n = load_params()["n_samples"]
    by_q = defaultdict(dict)
    for s in read_jsonl(PROCESSED / a.run / "samples.jsonl"):
        if s["benchmark"] == "lcb":
            by_q[s["problem_id"]][s["sample_idx"]] = s
    outputs, status = [], {}
    for qid in sorted(by_q):
        assert sorted(by_q[qid]) == list(range(n)), f"{qid}: amostras {sorted(by_q[qid])}"
        outputs.append({"question_id": qid, "code_list": [by_q[qid][k]["code"] or "" for k in range(n)]})
        status[qid] = [by_q[qid][k]["status"] for k in range(n)]
    out = PROCESSED / a.run / "lcb"
    with write_once(out / "lcb_outputs.json") as f:
        json.dump(outputs, f, ensure_ascii=False, indent=1)
    with write_once(out / "lcb_status.json") as f:
        json.dump(status, f, indent=1)
    print(f"{len(outputs)} problemas do LCB em {out}")


if __name__ == "__main__":
    main()
