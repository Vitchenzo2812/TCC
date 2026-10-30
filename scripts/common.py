"""Utilidades compartilhadas: caminhos, configuração, carga dos problemas, montagem de prompts."""
import json
import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"

FMT_STARTER = "You will use the following starter code to write the solution to the problem and enclose your code within delimiters."
FMT_STDIN = "Read the inputs from stdin solve the problem and write the answer to stdout (do not directly test on the sample inputs). Enclose your code within delimiters as follows. Ensure that when the python program runs, it reads the inputs, runs the algorithm and writes output to STDOUT."


def load_dotenv():
    """Lê ROOT/.env (KEY=valor) sem sobrescrever variáveis já definidas no ambiente."""
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip() and not key.lstrip().startswith("#"):
                os.environ.setdefault(key.strip(), value.strip())


def load_params() -> dict:
    load_dotenv()
    return yaml.safe_load((ROOT / "config" / "params.yaml").read_text(encoding="utf-8"))


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def load_problems(params: dict) -> dict:
    """Devolve {benchmark: {problem_id: problema}} com os campos usados no pipeline."""
    mbpp = {
        r["task_id"]: {"problem_id": r["task_id"], "benchmark": "mbpp", "difficulty": None,
                       "prompt": r["prompt"], "entry_point": r["entry_point"]}
        for r in read_jsonl(ROOT / params["benchmarks"]["mbpp"]["dataset_file"])
    }
    lcb = {}
    for r in iter_lcb_rows(params):
        assert r["question_id"] not in lcb, f"question_id duplicado: {r['question_id']}"
        lcb[r["question_id"]] = {"problem_id": r["question_id"], "benchmark": "lcb", "difficulty": r["difficulty"],
                                 "platform": r["platform"], "contest_date": r["contest_date"],
                                 "title": r["question_title"], "question_content": r["question_content"],
                                 "starter_code": r["starter_code"], "source_file": r["_source_file"]}
    return {"mbpp": mbpp, "lcb": lcb}


def iter_lcb_rows(params: dict, keep=None):
    """Percorre os arquivos da release do LCB linha a linha (são ~4,4 GB; nada é carregado de uma vez).
    keep: conjunto de question_id; se dado, só esses são devolvidos."""
    for rel in params["benchmarks"]["lcb"]["dataset_files"]:
        with open(ROOT / rel, encoding="utf-8") as f:
            for line in f:
                row = json.loads(line)
                if keep is not None and row["question_id"] not in keep:
                    continue
                row["_source_file"] = Path(rel).name
                yield row


def mbpp_user_prompt(problem: dict) -> str:
    # Mesmo formato de evalplus/provider/anthropic.py; replace (não format) porque o enunciado pode ter chaves.
    template = (ROOT / "prompts" / "mbpp_user.txt").read_text(encoding="utf-8")
    return template.replace("{prompt}", problem["prompt"].strip())


def lcb_user_prompt(problem: dict) -> str:
    # Réplica de lcb_runner.prompts.code_generation.get_generic_question_template_answer(...).rstrip()
    prompt = f"### Question:\n{problem['question_content']}\n\n"
    if problem["starter_code"]:
        prompt += f"### Format: {FMT_STARTER}\n"
        prompt += f"```python\n{problem['starter_code']}\n```\n\n"
    else:
        prompt += f"### Format: {FMT_STDIN}\n"
        prompt += "```python\n# YOUR CODE HERE\n```\n\n"
    prompt += "### Answer: (use the provided format with backticks)\n\n"
    return prompt.rstrip()


def build_request(problem: dict, params: dict) -> dict:
    """Parâmetros exatos da requisição (sem temperature/top_p/top_k, regra 2.1)."""
    request = dict(
        model=params["model"],
        max_tokens=params["max_tokens"],
        output_config={"effort": params["effort"]},
        thinking={"type": params["thinking"]["type"], "display": params["thinking"]["display"]},
    )
    if problem["benchmark"] == "mbpp":
        request["messages"] = [{"role": "user", "content": mbpp_user_prompt(problem)}]
    else:
        request["system"] = (ROOT / "prompts" / "lcb_system.txt").read_text(encoding="utf-8")
        request["messages"] = [{"role": "user", "content": lcb_user_prompt(problem)}]
    return request


def custom_id(benchmark: str, problem_id: str, sample_idx: int) -> str:
    # A Batch API aceita só [a-zA-Z0-9_-] (até 64 caracteres); "Mbpp/2" vira "Mbpp-2".
    return f"{benchmark}__{problem_id.replace('/', '-')}__{sample_idx}"


def write_once(path: Path):
    """Abre um arquivo bruto só se ele ainda não existir (regra 2.6)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    return open(path, "x", encoding="utf-8")
