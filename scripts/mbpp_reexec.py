"""Reexecuta, no Docker, as amostras reprovadas do MBPP+ para descobrir COMO cada uma falhou.

Roda SOMENTE dentro do contêiner tcc-evalplus (executa código gerado pelo modelo):
  docker run --rm --network none --cpus=2 --memory=4g -v "<repo>:/work" -w /work \
      tcc-evalplus:0.3.1 python scripts/mbpp_reexec.py --run NOME

O EvalPlus informa aprovação e a entrada que falhou, mas não o tipo de erro. O veredito e a entrada
vêm do próprio untrusted_check (mesma comparação, tolerância e oráculos especiais; nada é
reimplementado). Só depois a amostra roda de novo naquela entrada, com as mesmas proteções
(reliability_guard, swallow_io, time_limit), para capturar a exceção, o estouro ou a saída obtida.
É serial, então vale também como a reavaliação de estouros de tempo do roteiro (seção 9).

Saída (escrita única): data/raw/NOME/mbpp_reexec_<UTC>/per_sample.jsonl
"""
import argparse
import json
import multiprocessing
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from evalplus.config import DEFAULT_GT_TIME_LIMIT_FACTOR, DEFAULT_MIN_TIME_LIMIT  # noqa: E402
from evalplus.data import get_mbpp_plus, get_mbpp_plus_hash  # noqa: E402
from evalplus.eval import PASS, TIMEOUT, query_maximum_memory_bytes, untrusted_check  # noqa: E402
from evalplus.eval._special_oracle import MBPP_OUTPUT_NOT_NONE_TASKS  # noqa: E402
from evalplus.eval.utils import TimeoutException, create_tempdir, reliability_guard, swallow_io, time_limit  # noqa: E402
from evalplus.evaluate import get_groundtruth  # noqa: E402

from common import PROCESSED, RAW, write_once  # noqa: E402

MAX_REPR = 2000


def short(value) -> str:
    return repr(value)[:MAX_REPR]


def capture(code, entry_point, inp, limit, conn):
    """Mesmo roteiro de evalplus.eval.unsafe_execute, mas guarda o que aconteceu na entrada."""
    with create_tempdir():
        rmtree, rmdir, chdir = shutil.rmtree, os.rmdir, os.chdir
        reliability_guard(maximum_memory_bytes=query_maximum_memory_bytes())
        res = {"kind": None, "exc_type": None, "exc_msg": None, "output": None}
        try:
            with swallow_io():
                compiled = compile(code, "<amostra>", "exec")
                exec_globals = {}
                exec(compiled, exec_globals)
                fn = exec_globals[entry_point]
            with time_limit(limit):
                with swallow_io():
                    out = fn(*inp)
            res.update(kind="resposta_errada", output=short(out))
        except TimeoutException:
            res.update(kind="tempo_limite")
        except SyntaxError as e:
            res.update(kind="erro_sintaxe", exc_type=type(e).__name__, exc_msg=str(e)[:MAX_REPR])
        except BaseException as e:
            res.update(kind="excecao", exc_type=type(e).__name__, exc_msg=str(e)[:MAX_REPR])
        conn.send(res)
        shutil.rmtree, os.rmdir, os.chdir = rmtree, rmdir, chdir


def run_capture(code, entry_point, inp, limit):
    parent, child = multiprocessing.Pipe(duplex=False)
    p = multiprocessing.Process(target=capture, args=(code, entry_point, inp, limit, child))
    p.start()
    got = parent.recv() if parent.poll(limit + 10) else None
    p.join(1)
    if p.is_alive():
        p.kill()
    return got or {"kind": "tempo_limite", "exc_type": None, "exc_msg": None, "output": None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    a = ap.parse_args()
    results = json.loads((PROCESSED / a.run / "evalplus" / "mbpp_samples-sanitized_eval_results.json")
                         .read_text(encoding="utf-8"))["eval"]
    problems = get_mbpp_plus()
    truth = get_groundtruth(problems, get_mbpp_plus_hash(), MBPP_OUTPUT_NOT_NONE_TASKS)

    out = RAW / a.run / f"mbpp_reexec_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}" / "per_sample.jsonl"
    n = 0
    with write_once(out) as f:
        for task_id in sorted(results):
            p, gt = problems[task_id], truth[task_id]
            for k, r in enumerate(results[task_id]):
                if r["base_status"] == PASS and r["plus_status"] == PASS:
                    continue
                suite = "base" if r["base_status"] != PASS else "plus"
                inputs, expected, times = p[f"{suite}_input"], gt[suite], gt[f"{suite}_time"]
                stat, details = untrusted_check("mbpp", r["solution"], inputs, p["entry_point"], expected,
                                                p["atol"], times, fast_check=True)
                rec = {"task_id": task_id, "sample_idx": k, "suite": suite, "status_original": r[f"{suite}_status"],
                       "status_reexec": stat}
                if stat == PASS:  # só um estouro espúrio da execução paralela chega aqui
                    rec.update(kind="aprovada_na_reexecucao", input_idx=None, input=None, expected=None,
                               exc_type=None, exc_msg=None, output=None)
                else:
                    # Com fast_check, details para na entrada que falhou; no estouro global, na seguinte.
                    i = min(len(details) - (0 if stat == TIMEOUT else 1), len(inputs) - 1)
                    i = max(i, 0)
                    limit = max(DEFAULT_MIN_TIME_LIMIT, DEFAULT_GT_TIME_LIMIT_FACTOR * times[i])
                    rec.update(run_capture(r["solution"], p["entry_point"], inputs[i], limit))
                    rec.update(input_idx=i, input=short(inputs[i]), expected=short(expected[i]))
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                f.flush()
                n += 1
    print(f"{n} amostras reexecutadas -> {out}")


if __name__ == "__main__":
    main()
