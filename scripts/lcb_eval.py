"""Avalia lcb_outputs.json com o verificador do próprio LiveCodeBench, a partir do test6.jsonl local.

Roda SOMENTE dentro do contêiner tcc-lcb (executa código gerado pelo modelo):
  docker run --rm --network none --cpus=2 --memory=4g -v "<repo>:/work" -w /opt/LiveCodeBench \
      tcc-lcb:28fef95 python /work/scripts/lcb_eval.py --run NOME [--serial --only ARQ]

Chama exatamente o que o custom_evaluator do LCB chama (CodeGenerationProblem.get_evaluation_sample +
codegen_metrics, timeout=6, 12 processos), mas sem carregar o dataset do Hugging Face e sem exigir
o conjunto completo de problemas, o que permite avaliar o piloto. Não reimplementa o verificador.

--serial: um processo (reavaliação de estouros de tempo, roteiro seção 9). --only: JSON com
[[question_id, sample_idx], ...] para reavaliar só essas amostras.
Saída (escrita única): data/raw/NOME/lcb_eval_<modo>_<UTC>/{metrics.json, per_sample.jsonl}
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lcb_runner.benchmarks.code_generation import CodeGenerationProblem  # noqa: E402
from lcb_runner.evaluation import codegen_metrics  # noqa: E402

from common import PROCESSED, RAW, iter_lcb_rows, load_params, write_once  # noqa: E402

# Códigos de lcb_runner/evaluation/testing_util.py e compute_code_generation_metrics.py. O -4 inclui
# erros de compilação (SyntaxError) e exceções; o tipo fica em metadata["error"]/["error_message"].
# -5 = estouro do tempo global (o processo foi morto sem devolver metadado).
ERROR_NAMES = {-2: "wrong_answer", -3: "time_limit", -4: "runtime_or_compile_error", -5: "test_runner_error"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--serial", action="store_true")
    ap.add_argument("--only")
    ap.add_argument("--timeout", type=int, default=6)
    ap.add_argument("--workers", type=int, default=12, help="processos de avaliação (padrão do LCB: 12)")
    ap.add_argument("--chunk", help="i/n: avalia só o i-ésimo de n blocos de problemas (0 <= i < n)")
    a = ap.parse_args()
    params = load_params()

    outputs = json.loads((PROCESSED / a.run / "lcb" / "lcb_outputs.json").read_text(encoding="utf-8"))
    codes = {o["question_id"]: o["code_list"] for o in outputs}

    if a.only:
        pairs = [tuple(p) for p in json.loads(Path(a.only).read_text(encoding="utf-8"))]
    else:
        pairs = [(q, k) for q in sorted(codes) for k in range(len(codes[q]))]
    if a.chunk:
        # Os casos de teste privados do LCB ocupam GBs; avaliar em blocos mantém a memória dentro do --memory.
        i, n = map(int, a.chunk.split("/"))
        qids = sorted({q for q, _ in pairs})
        mine = set(qids[i::n])
        pairs = [p for p in pairs if p[0] in mine]
    wanted = {q for q, _ in pairs}
    problems = {row["question_id"]: CodeGenerationProblem(**{k: v for k, v in row.items() if k != "_source_file"})
                for row in iter_lcb_rows(params, keep=wanted)}
    assert set(problems) == wanted, f"problemas ausentes no dataset: {wanted - set(problems)}"
    # Uma "geração" por entrada da lista: assim cada amostra tem o seu resultado e metadado.
    samples = [problems[q].get_evaluation_sample() for q, _ in pairs]
    gens = [[codes[q][k]] for q, k in pairs]
    metrics, results, metadata = codegen_metrics(
        samples, gens, k_list=[1], num_process_evaluate=1 if a.serial else a.workers, timeout=a.timeout)

    mode = "serial" if a.serial else "paralelo"
    chunk = f"_bloco{a.chunk.replace('/', 'de')}" if a.chunk else ""
    out = RAW / a.run / f"lcb_eval_{mode}{chunk}_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    with write_once(out / "metrics.json") as f:
        json.dump({"mode": mode, "workers": 1 if a.serial else a.workers, "timeout": a.timeout,
                   "chunk": a.chunk, "n_samples": len(pairs), "metrics": metrics}, f, indent=1)
    with write_once(out / "per_sample.jsonl") as f:
        for i, (q, k) in enumerate(pairs):
            test_results = results[i][0]
            meta = json.loads(metadata[i][0])
            passed = bool(test_results) and all(r is True for r in test_results)
            f.write(json.dumps({"question_id": q, "sample_idx": k, "passed": passed,
                                "difficulty": problems[q].difficulty.value,
                                "error_code": meta.get("error_code"),
                                "error_name": ERROR_NAMES.get(meta.get("error_code")),
                                "metadata": meta, "test_results": test_results}, ensure_ascii=False) + "\n")
    print(f"{len(pairs)} amostras avaliadas -> {out}")


if __name__ == "__main__":
    main()
