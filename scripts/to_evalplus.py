"""Monta o samples.jsonl do EvalPlus (uma linha por amostra, 5 por task_id).

Uso: python scripts/to_evalplus.py --run NOME [--subset]
Saída em data/processed/NOME/evalplus/:
  mbpp_samples.jsonl    {"task_id", "solution"} na ordem (task_id, sample_idx)
  mbpp_samples_map.jsonl linha -> (task_id, sample_idx, status)
  MbppPlus-subset.jsonl  (--subset) só os problemas da execução, para MBPP_OVERRIDE_PATH no piloto:
                         o evalplus.evaluate exige amostras para todos os problemas do dataset.
Amostras sem código (sem_codigo, truncada, recusa, erro_api) entram com solução vazia, para manter
a contagem por problema; truncadas e recusas são excluídas depois, em metrics.py.
"""
import argparse
import json

from common import PROCESSED, ROOT, load_params, read_jsonl, write_once


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--subset", action="store_true")
    a = ap.parse_args()
    params = load_params()
    samples = [s for s in read_jsonl(PROCESSED / a.run / "samples.jsonl") if s["benchmark"] == "mbpp"]
    samples.sort(key=lambda s: (s["problem_id"], s["sample_idx"]))
    out = PROCESSED / a.run / "evalplus"
    with write_once(out / "mbpp_samples.jsonl") as f, write_once(out / "mbpp_samples_map.jsonl") as m:
        for line, s in enumerate(samples):
            f.write(json.dumps({"task_id": s["problem_id"], "solution": s["code"] or ""}, ensure_ascii=False) + "\n")
            m.write(json.dumps({"line": line, "task_id": s["problem_id"], "sample_idx": s["sample_idx"],
                                "status": s["status"]}) + "\n")
    if a.subset:
        ids = {s["problem_id"] for s in samples}
        with write_once(out / "MbppPlus-subset.jsonl") as f:
            for r in read_jsonl(ROOT / params["benchmarks"]["mbpp"]["dataset_file"]):
                if r["task_id"] in ids:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"{len(samples)} amostras do MBPP+ em {out}")


if __name__ == "__main__":
    main()
