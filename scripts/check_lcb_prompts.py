"""Confere se scripts/common.lcb_user_prompt reproduz o prompt original do LiveCodeBench.

Roda dentro do contêiner do LCB (tem lcb_runner instalado), a partir da pasta do pacote:
  docker run --rm --network none -v "<repo>:/work" -w /opt/LiveCodeBench tcc-lcb:28fef95 \
      python /work/scripts/check_lcb_prompts.py
Não executa código gerado; só compara textos.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lcb_runner.benchmarks.code_generation import CodeGenerationProblem  # noqa: E402
from lcb_runner.lm_styles import LMStyle  # noqa: E402
from lcb_runner.prompts.code_generation import format_prompt_generation  # noqa: E402

from common import ROOT, iter_lcb_rows, lcb_user_prompt, load_params, load_problems  # noqa: E402

params = load_params()
ours = load_problems(params)["lcb"]
system_ours = (ROOT / "prompts" / "lcb_system.txt").read_text(encoding="utf-8")
ok = 0
for row in iter_lcb_rows(params):
    row.pop("_source_file")
    row["private_test_cases"] = "[]"  # não usado no prompt; evita descomprimir GBs de testes
    q = CodeGenerationProblem(**row)
    system, messages = format_prompt_generation(q, LMStyle.Claude3)
    same = system == system_ours and messages[0]["content"] == lcb_user_prompt(ours[q.question_id])
    ok += same
    if not same:
        print("DIVERGE:", q.question_id)
print(f"{ok}/{len(ours)} prompts idênticos ao LCB")
