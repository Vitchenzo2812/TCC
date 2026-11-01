"""Consolida manifestação e recorrência das falhas (roteiro, seção 10.2 a 10.4).

Uso: python scripts/manifestation.py   (depois de mbpp_reexec.py e da reavaliação serial do LCB)
Saída em data/processed/metrics/:
  failed_samples.jsonl  uma linha por amostra reprovada
  failed_problems.csv   uma linha por problema com falha (recorrência e suspeita de defeito)
  manifestation.csv     contagens de manifestação por nível de complexidade
  recurrence.csv        contagens de recorrência por nível de complexidade

Tudo aqui é automático e observável. A coluna suspeita_defeito_benchmark é só uma sugestão mecânica
(todas as amostras falham na mesma entrada e com a mesma saída); quem decide são os pesquisadores.
Nenhuma causa é atribuída neste script.
"""
import json
from collections import Counter

import pandas as pd

from common import PROCESSED, load_params
from results import LEVELS, load_lcb, load_mbpp, load_mbpp_reexec, lcb_manifestation

OUT = PROCESSED / "metrics"
MAX_TEXT = 2000


def mbpp_rows():
    results, reexec = load_mbpp(), load_mbpp_reexec()
    for (pid, k), r in sorted(results.items()):
        if r["base_status"] == "pass" and r["plus_status"] == "pass":
            continue
        x = reexec[(pid, k)]
        assert x["kind"] != "aprovada_na_reexecucao", f"sem veredito de mbpp_flaky.py: {pid}/{k}"
        detail = f"{x['exc_type']}: {x['exc_msg']}" if x["exc_type"] else ""
        yield {"benchmark": "mbpp", "problem_id": pid, "sample_idx": k, "dificuldade": None, "conjunto": x["suite"],
               "manifestacao": x["kind"], "detalhe_erro": detail, "entrada": x["input"], "esperado": x["expected"],
               "obtido": x["output"]}


def lcb_rows():
    for (pid, k), r in sorted(load_lcb().items()):
        if r["passed"]:
            continue
        kind, detail = lcb_manifestation(r)
        meta = r["metadata"]
        yield {"benchmark": "lcb", "problem_id": pid, "sample_idx": k, "dificuldade": r["difficulty"], "conjunto": None,
               "manifestacao": kind, "detalhe_erro": detail, "entrada": str(meta.get("inputs", ""))[:MAX_TEXT],
               "esperado": str(meta.get("expected", ""))[:MAX_TEXT], "obtido": str(meta.get("output", ""))[:MAX_TEXT]}


def level_of(benchmark: str, difficulty) -> int:
    return LEVELS[(benchmark, None if pd.isna(difficulty) else difficulty)]


def summarize_problem(g: pd.DataFrame, n_samples: int) -> dict:
    g = g.sort_values("sample_idx")
    first = g.iloc[0]
    n = len(g)
    same_kind = g["manifestacao"].nunique() == 1
    same_failure = same_kind and g["entrada"].nunique() == 1 and g["obtido"].nunique() == 1
    return {"benchmark": first["benchmark"], "problem_id": first["problem_id"], "dificuldade": first["dificuldade"],
            "nivel_complexidade": level_of(first["benchmark"], first["dificuldade"]), "amostras_reprovadas": n,
            "recorrencia": "sistematica" if n == n_samples else "ocasional", "primeira_amostra": int(first["sample_idx"]),
            "manifestacao": first["manifestacao"], "mesma_manifestacao": same_kind,
            "manifestacoes": dict(Counter(g["manifestacao"])), "mesma_entrada_e_saida": same_failure,
            "suspeita_defeito_benchmark": n == n_samples and same_failure and first["manifestacao"] == "resposta_errada"}


def main():
    params = load_params()
    rows = list(mbpp_rows()) + list(lcb_rows())

    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "failed_samples.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    df = pd.DataFrame(rows)
    n_samples = params["n_samples"]
    per = pd.DataFrame([summarize_problem(g, n_samples) for _, g in df.groupby(["benchmark", "problem_id"])])
    per.to_csv(OUT / "failed_problems.csv", index=False, encoding="utf-8-sig")

    level = df.apply(lambda r: level_of(r["benchmark"], r["dificuldade"]), axis=1)
    kinds = pd.crosstab(level.rename("nivel_complexidade"), df["manifestacao"], margins=True)
    kinds.to_csv(OUT / "manifestation.csv", encoding="utf-8-sig")
    recurrence = pd.crosstab(per["nivel_complexidade"], per["recorrencia"], margins=True)
    recurrence.to_csv(OUT / "recurrence.csv", encoding="utf-8-sig")
    print("amostras reprovadas por manifestação:\n", kinds.to_string())
    print("\nexceções mais comuns:\n", df[df["manifestacao"] == "excecao"]["detalhe_erro"]
          .str.extract(r"^(\w+)")[0].value_counts().head(10).to_string())
    print("\nproblemas por recorrência:\n", recurrence.to_string())
    print("\namostras reprovadas por problema:\n",
          pd.crosstab(per["nivel_complexidade"], per["amostras_reprovadas"], margins=True).to_string())
    print("\nmesma manifestação em todas as amostras reprovadas:", int(per["mesma_manifestacao"].sum()), "de", len(per))
    print("suspeitas de defeito do benchmark:", int(per["suspeita_defeito_benchmark"].sum()))


if __name__ == "__main__":
    main()
