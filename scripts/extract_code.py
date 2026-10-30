"""Extrai o código de cada amostra, lendo SOMENTE os blocos type == "text".

Uso: python scripts/extract_code.py --run NOME
Entrada: data/raw/NOME/generations.jsonl (+ retries.jsonl, se existir)
Saída:   data/processed/NOME/samples.jsonl, uma linha por (benchmark, problem_id, sample_idx)

Status:
  ok          código extraído
  sem_codigo  resposta completa sem bloco de código Python (manifestação própria)
  truncada    stop_reason == "max_tokens" (não conta como falha funcional)
  recusa      stop_reason == "refusal"    (não conta como falha funcional)
  erro_api    a requisição falhou
Se a amostra foi regerada (retry), vale a regeração; a original continua em data/raw.
"""
import argparse
import json
import re

from common import PROCESSED, RAW, read_jsonl, write_once

FENCE = re.compile(r"```([^\n`]*)\n(.*?)```", re.DOTALL)
PY_LANGS = {"python", "py", "python3", ""}


def extract(text: str):
    blocks = [(lang.strip().lower(), body) for lang, body in FENCE.findall(text)]
    py = [b for b in blocks if b[0] in PY_LANGS]
    if not py:
        return None, None
    lang, body = py[-1]
    return body, lang or "sem_rotulo"


def process(rec):
    out = {k: rec[k] for k in ("benchmark", "problem_id", "sample_idx", "custom_id")}
    if "error" in rec:
        return {**out, "status": "erro_api", "code": None, "detail": json.dumps(rec["error"], ensure_ascii=False)}
    resp = rec["response"]
    content = resp["content"]
    text = "\n".join(b["text"] for b in content if b["type"] == "text")
    thinking = "\n\n".join(b.get("thinking", "") for b in content if b["type"] == "thinking")
    out.update(stop_reason=resp["stop_reason"], model=resp["model"], message_id=resp["id"],
               usage=resp["usage"], thinking_summary=thinking, response_text=text)
    if resp["stop_reason"] == "max_tokens":
        return {**out, "status": "truncada", "code": None}
    if resp["stop_reason"] == "refusal":
        return {**out, "status": "recusa", "code": None, "detail": json.dumps(resp.get("stop_details"), ensure_ascii=False)}
    code, lang = extract(text)
    if code is None:
        return {**out, "status": "sem_codigo", "code": None}
    return {**out, "status": "ok", "code": code, "code_fence_lang": lang}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    a = ap.parse_args()
    raw = RAW / a.run
    final = {}
    for r in read_jsonl(raw / "generations.jsonl"):
        final[(r["benchmark"], r["problem_id"], r["sample_idx"])] = {**process(r), "source": "original"}
    if (raw / "retries.jsonl").exists():
        for r in read_jsonl(raw / "retries.jsonl"):
            key = (r["benchmark"], r["problem_id"], r["sample_idx"])
            final[key] = {**process(r), "source": "retry", "original_status": final[key]["status"]}
    counts = {}
    with write_once(PROCESSED / a.run / "samples.jsonl") as f:
        for key in sorted(final):
            s = final[key]
            counts[s["status"]] = counts.get(s["status"], 0) + 1
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    print(f"{len(final)} amostras: {counts}")
    bad = counts.get("truncada", 0) + counts.get("recusa", 0)
    if bad / max(len(final), 1) > 0.02:
        print(f"ATENÇÃO: {bad} truncadas/recusas (> 2%). Regra 2.7: parar e consultar os pesquisadores.")


if __name__ == "__main__":
    main()
