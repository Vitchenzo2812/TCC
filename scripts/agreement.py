"""Concordância entre os pesquisadores A e B na etapa 1 (roteiro, seção 12).

Uso: python scripts/agreement.py --a etapa1_A.xlsx --b etapa1_B.xlsx
Calcula sobre a causa principal, excluindo as falhas que ambos marcaram como defeito do benchmark.
Rodar ANTES da reconciliação. Saída em data/processed/coding/: agreement.json, confusion_matrix.csv,
divergencias.csv.
"""
import argparse
import json

import numpy as np
import pandas as pd
from sklearn.metrics import cohen_kappa_score, confusion_matrix

from common import PROCESSED

OUT = PROCESSED / "coding"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", required=True)
    ap.add_argument("--b", required=True)
    args = ap.parse_args()
    a = pd.read_excel(args.a)[["id_falha", "problem_id", "defeito_benchmark_A", "causa_principal_A"]]
    b = pd.read_excel(args.b)[["id_falha", "defeito_benchmark_B", "causa_principal_B"]]
    df = a.merge(b, on="id_falha", validate="one_to_one")
    assert len(df) == len(a) == len(b), "as planilhas de A e B têm falhas diferentes"

    both_defect = (df["defeito_benchmark_A"] == "sim") & (df["defeito_benchmark_B"] == "sim")
    defect_split = df[(df["defeito_benchmark_A"] == "sim") ^ (df["defeito_benchmark_B"] == "sim")]
    coded = df[~both_defect]
    missing = coded[coded["causa_principal_A"].isna() | coded["causa_principal_B"].isna()]
    coded = coded.drop(index=missing.index).reset_index(drop=True)
    ca, cb = coded["causa_principal_A"], coded["causa_principal_B"]

    kappa = cohen_kappa_score(ca, cb)
    pct = (ca == cb).mean()
    rng = np.random.default_rng(42)
    boots = []
    for _ in range(2000):
        idx = rng.integers(0, len(coded), len(coded))
        boots.append(cohen_kappa_score(ca.iloc[idx], cb.iloc[idx]))
    lo, hi = np.nanpercentile(boots, [2.5, 97.5])

    labels = sorted(set(ca) | set(cb))
    pd.DataFrame(confusion_matrix(ca, cb, labels=labels), index=labels, columns=labels).to_csv(
        OUT / "confusion_matrix.csv", encoding="utf-8-sig")
    coded[ca != cb].to_csv(OUT / "divergencias.csv", index=False, encoding="utf-8-sig")
    result = {"falhas": len(df), "defeito_por_ambos": int(both_defect.sum()),
              "defeito_divergente_para_C": defect_split["id_falha"].tolist(),
              "sem_causa_preenchida": missing["id_falha"].tolist(), "falhas_no_kappa": len(coded),
              "kappa": kappa, "ic95_bootstrap": [lo, hi], "concordancia_percentual": pct}
    (OUT / "agreement.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
