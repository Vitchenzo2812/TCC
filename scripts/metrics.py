"""Calcula Pass@1 e os recortes descritivos (roteiro, seção 10.1).

Uso: python scripts/metrics.py
Saída em data/processed/metrics/:
  per_problem.csv   c/n por problema
  pass_at_1.csv     Pass@1 por grupo, com IC 95% bootstrap e Wilson
  by_period.csv     LCB por trimestre do concurso
  by_thinking.csv   taxa de aprovação das amostras com e sem raciocínio, por nível

Pass@1 = média de c/n entre os problemas (Chen et al., 2021). O bootstrap reamostra problemas; o
Wilson é sobre a proporção de problemas com as 5 amostras aprovadas.
"""
import numpy as np
import pandas as pd
from scipy.stats import norm

from common import PROCESSED, load_params, load_problems
from results import LEVELS, load_lcb, load_mbpp, load_samples

N_BOOT = 10000
OUT = PROCESSED / "metrics"


def bootstrap_ci(values: np.ndarray, seed: int) -> tuple:
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(values), (N_BOOT, len(values)))
    return tuple(np.percentile(values[idx].mean(axis=1), [2.5, 97.5]))


def wilson_ci(k: int, n: int) -> tuple:
    z = norm.ppf(0.975)
    p = k / n
    center = (p + z**2 / (2 * n)) / (1 + z**2 / n)
    half = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / (1 + z**2 / n)
    return center - half, center + half


def summarize(name: str, ratio: pd.Series, seed: int) -> dict:
    values = ratio.to_numpy()
    n, solved = len(values), int((values == 1).sum())
    lo, hi = bootstrap_ci(values, seed)
    wlo, whi = wilson_ci(solved, n)
    return {"grupo": name, "problemas": n, "pass_at_1": values.mean(), "ic95_boot_inf": lo, "ic95_boot_sup": hi,
            "problemas_5_de_5": solved, "prop_5_de_5": solved / n, "ic95_wilson_inf": wlo, "ic95_wilson_sup": whi,
            "problemas_com_falha": n - solved}


def main():
    params = load_params()
    seed = params["pilot"]["seed"]
    problems = load_problems(params)
    samples, lcb, mbpp = load_samples(), load_lcb(), load_mbpp()

    statuses = pd.Series([s["status"] for s in samples.values()]).value_counts()
    print("status das amostras:\n", statuses.to_string())
    assert set(statuses.index) == {"ok"}, "há amostras truncadas, recusadas ou sem código: tratar a exclusão antes"
    assert len(mbpp) + len(lcb) == len(samples), "faltam resultados de avaliação"

    rows = []
    for (benchmark, pid, k), s in samples.items():
        think = (s["usage"].get("output_tokens_details") or {}).get("thinking_tokens", 0) > 0
        p = problems[benchmark][pid]
        if benchmark == "mbpp":
            r = mbpp[(pid, k)]
            base, passed = r["base_status"] == "pass", r["base_status"] == "pass" and r["plus_status"] == "pass"
        else:
            base, passed = None, lcb[(pid, k)]["passed"]
        rows.append({"benchmark": benchmark, "problem_id": pid, "sample_idx": k, "dificuldade": p["difficulty"],
                     "nivel_complexidade": LEVELS[(benchmark, p["difficulty"])], "plataforma": p.get("platform"),
                     "data_concurso": p.get("contest_date"), "aprovada_base": base, "aprovada": passed,
                     "raciocinou": think, "tokens_saida": s["usage"]["output_tokens"]})
    df = pd.DataFrame(rows)

    keys = ["benchmark", "problem_id", "dificuldade", "nivel_complexidade", "plataforma", "data_concurso"]
    per = df.groupby(keys, dropna=False).agg(n=("aprovada", "size"), c=("aprovada", "sum"),
                                             c_base=("aprovada_base", "sum")).reset_index()
    assert (per["n"] == params["n_samples"]).all()
    per["ratio"] = per["c"] / per["n"]
    per["ratio_base"] = per["c_base"] / per["n"]

    m, l = per[per["benchmark"] == "mbpp"], per[per["benchmark"] == "lcb"]
    table = [summarize("MBPP+ base", m["ratio_base"], seed), summarize("MBPP+ plus", m["ratio"], seed),
             summarize("LCB geral", l["ratio"], seed)]
    table += [summarize(f"LCB {d}", l[l["dificuldade"] == d]["ratio"], seed) for d in ("easy", "medium", "hard")]
    table += [summarize(f"LCB {pl}", g["ratio"], seed) for pl, g in l.groupby("plataforma")]

    OUT.mkdir(parents=True, exist_ok=True)
    per.to_csv(OUT / "per_problem.csv", index=False, encoding="utf-8-sig")
    pass1 = pd.DataFrame(table)
    pass1.to_csv(OUT / "pass_at_1.csv", index=False, encoding="utf-8-sig")

    l = l.assign(periodo=pd.to_datetime(l["data_concurso"]).dt.to_period("Q").astype(str))
    period = pd.DataFrame([summarize(q, g["ratio"], seed) for q, g in l.groupby("periodo")])
    period.to_csv(OUT / "by_period.csv", index=False, encoding="utf-8-sig")

    thinking = df.groupby(["nivel_complexidade", "raciocinou"]).agg(
        amostras=("aprovada", "size"), aprovadas=("aprovada", "sum"), tokens_saida_mediana=("tokens_saida", "median"))
    thinking["taxa_aprovacao"] = thinking["aprovadas"] / thinking["amostras"]
    thinking.reset_index().to_csv(OUT / "by_thinking.csv", index=False, encoding="utf-8-sig")

    pd.set_option("display.width", 200, "display.max_columns", None, "display.max_rows", None)
    print(pass1.round(3).to_string(index=False))
    print(period[["grupo", "problemas", "pass_at_1", "problemas_com_falha"]].round(3).to_string(index=False))
    print(thinking.round(3).to_string())


if __name__ == "__main__":
    main()
