"""Aplica a regra de reconciliação e monta as tabelas finais de causas (roteiro, seção 11).

Uso: python scripts/reconcile.py [--respostas data/processed/coding/respostas]
Regra decidida pelos pesquisadores em 2026-11-24: onde A e B concordam, vale a resposta comum;
onde divergem (defeito do benchmark ou causa principal), vale a resposta do codificador A.
Exceção decidida pelos dois codificadores em 2026-11-25: nas falhas de EXECUTION_OVERRIDES, a
verificação por execução (analysis/verificacoes/relatorio_docker.csv) confirmou o defeito que B
apontou, e a decisão final segue essa evidência (defeito = sim) em vez da resposta de A.
Nenhuma causa é atribuída aqui; o script só aplica a regra às respostas humanas.

Saída em data/processed/coding/:
  reconciliacao.csv        uma linha por falha: respostas de A e B, decisão final e origem
Saída em data/processed/metrics/:
  defeitos_benchmark.csv   falhas excluídas como defeito do benchmark
  causas_por_nivel.csv     causa final por nível de complexidade
  causas_por_manifestacao.csv, causas_por_recorrencia.csv
  causas_secundarias.csv   contagem das causas secundárias finais
"""
import argparse

import pandas as pd

from common import PROCESSED

# falha -> verificação de execução que sustenta o defeito (ver relatorio_docker.csv)
EXECUTION_OVERRIDES = {
    "F063": "gabarito reproduzido só proibindo zero à esquerda, restrição ausente do enunciado",
    "F077": "entrada viola 1 <= nums[i] <= nums.length",
    "F078": "entrada viola 3 <= points.length",
    "F082": "entrada viola nums[i] < 2^7",
}

LEVEL_NAMES = {1: "1. MBPP+", 2: "2. LCB fácil", 3: "3. LCB médio", 4: "4. LCB difícil"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--respostas", default=str(PROCESSED / "coding" / "respostas"))
    a = ap.parse_args()
    df = pd.read_excel(f"{a.respostas}/Resposta de Ambos/codificacao.xlsx")
    for c in ["defeito_benchmark_A", "defeito_benchmark_B", "causa_principal_A", "causa_principal_B",
              "causas_secundarias_A", "causas_secundarias_B"]:
        df[c] = df[c].astype("string").str.strip()

    same_defect = df["defeito_benchmark_A"] == df["defeito_benchmark_B"]
    same_cause = df["causa_principal_A"].fillna("") == df["causa_principal_B"].fillna("")
    df["defeito_final"] = df["defeito_benchmark_A"]
    override = df["id_falha"].isin(EXECUTION_OVERRIDES)
    assert override.sum() == len(EXECUTION_OVERRIDES), "falha da exceção não encontrada"
    assert (df.loc[override, "defeito_benchmark_B"] == "sim").all(), "exceção só vale onde B apontou defeito"
    df.loc[override, "defeito_final"] = "sim"
    df["causa_final"] = df["causa_principal_A"].where(df["defeito_final"] == "não")
    df["causas_secundarias_final"] = df["causas_secundarias_A"].where(df["defeito_final"] == "não")
    df["origem"] = "consenso"
    df.loc[~same_defect, "origem"] = "divergência de defeito: vale A"
    df.loc[same_defect & (df["defeito_final"] == "não") & ~same_cause, "origem"] = "divergência de causa: vale A"
    df.loc[override, "origem"] = "divergência de defeito: vale a evidência de execução"
    assert df.loc[df["defeito_final"] == "não", "causa_final"].notna().all(), "falha sem causa final"

    df["nivel"] = df["nivel_complexidade"].map(LEVEL_NAMES)
    keep = ["id_falha", "problem_id", "benchmark", "dificuldade", "nivel", "manifestacao", "recorrencia",
            "suspeita_defeito_benchmark", "defeito_benchmark_A", "causa_principal_A", "defeito_benchmark_B",
            "causa_principal_B", "defeito_final", "causa_final", "causas_secundarias_final", "origem"]
    df[keep].to_csv(PROCESSED / "coding" / "reconciliacao.csv", index=False, encoding="utf-8-sig")

    out = PROCESSED / "metrics"
    defects = df[df["defeito_final"] == "sim"]
    defects[["id_falha", "problem_id", "nivel", "manifestacao", "recorrencia", "suspeita_defeito_benchmark",
             "origem"]].to_csv(out / "defeitos_benchmark.csv", index=False, encoding="utf-8-sig")
    coded = df[df["defeito_final"] == "não"]
    tables = {
        "causas_por_nivel.csv": pd.crosstab(coded["causa_final"], coded["nivel"], margins=True, margins_name="Total"),
        "causas_por_manifestacao.csv": pd.crosstab(coded["causa_final"], coded["manifestacao"], margins=True,
                                                   margins_name="Total"),
        "causas_por_recorrencia.csv": pd.crosstab(coded["causa_final"], coded["recorrencia"], margins=True,
                                                  margins_name="Total"),
    }
    for name, t in tables.items():
        t.sort_values("Total", ascending=False).to_csv(out / name, encoding="utf-8-sig")
    secondary = coded["causas_secundarias_final"].dropna().str.split(";").explode().str.strip()
    secondary.value_counts().rename_axis("causa_secundaria").rename("falhas").to_csv(
        out / "causas_secundarias.csv", encoding="utf-8-sig")

    pd.set_option("display.width", 200, "display.max_columns", None)
    print("origem das decisões:\n", df["origem"].value_counts().to_string())
    print("\ndefeito do benchmark por nível:\n", pd.crosstab(df["nivel"], df["defeito_final"], margins=True).to_string())
    for name, t in tables.items():
        print(f"\n{name}:\n", t.sort_values("Total", ascending=False).to_string())
    print("\ncausas secundárias:\n", secondary.value_counts().to_string())


if __name__ == "__main__":
    main()
