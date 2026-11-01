"""Monta as planilhas de codificação (roteiro, seção 11). Nenhuma causa é preenchida aqui.

Uso: python scripts/build_sheet.py [--calibracao 10]
Saída em data/processed/coding/:
  codificacao.xlsx             planilha mestra, com todas as colunas (fica com o pesquisador C)
  calibracao.xlsx              falhas sorteadas para a calibração; não entram na amostra oficial
  etapa1_A.xlsx, etapa1_B.xlsx cópias cegas, sem as colunas do outro e sem resumo_raciocinio
  etapa2_resumos.xlsx          resumos do raciocínio; liberar só depois de fechar a etapa 1

Unidade de análise: a primeira amostra reprovada de cada problema, pela ordem de sample_idx.
"""
import argparse
import json

import numpy as np
import pandas as pd
from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

from common import PROCESSED, load_params, load_problems, lcb_user_prompt
from results import load_mbpp, load_samples

OUT = PROCESSED / "coding"
MAX_CELL = 32000  # o limite do Excel é 32.767 caracteres por célula

SCRIPT_COLUMNS = ["id_falha", "problem_id", "benchmark", "dificuldade", "nivel_complexidade", "manifestacao",
                  "detalhe_erro", "entrada_que_falhou", "esperado", "obtido", "amostras_reprovadas", "recorrencia",
                  "mesma_manifestacao", "outras_manifestacoes", "enunciado", "codigo_gerado",
                  "suspeita_defeito_benchmark"]
CODER_COLUMNS = ["defeito_benchmark_{c}", "causa_principal_{c}", "causas_secundarias_{c}"]
STAGE2_COLUMNS = ["resumo_raciocinio", "causa_mudou_com_resumo_A", "causa_mudou_com_resumo_B"]
FINAL_COLUMNS = ["causa_final", "observacoes"]

CAUSES = ["Misinterpretation", "Missing Corner Case", "Silly Mistake", "Incomplete Generation", "Prompt-biased Code",
          "Non-Prompted Consideration", "Wrong Input Type", "Hallucinated Object", "Wrong Attribute",
          "Algoritmo incorreto", "Complexidade insuficiente"]
WIDTHS = {"enunciado": 70, "codigo_gerado": 70, "entrada_que_falhou": 35, "esperado": 25, "obtido": 25,
          "detalhe_erro": 35, "resumo_raciocinio": 70, "causas_secundarias_A": 28, "causas_secundarias_B": 28,
          "causa_principal_A": 26, "causa_principal_B": 26, "observacoes": 40}


def clean(value):
    if isinstance(value, (bool, int, float, np.integer, np.floating)):
        return value.item() if isinstance(value, np.generic) else value
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return ""
    return ILLEGAL_CHARACTERS_RE.sub("", str(value))[:MAX_CELL]


def write_sheet(path, df, columns, validate=()):
    wb = Workbook()
    ws = wb.active
    ws.title = "codificacao"
    ws.append(columns)
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="DDE6F0" if cell.value in SCRIPT_COLUMNS else "FFF2CC")
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    for _, row in df.iterrows():
        ws.append([""] * len(columns))
        for j, name in enumerate(columns, 1):
            cell = ws.cell(ws.max_row, j)
            cell.value = clean(row.get(name, ""))
            if isinstance(cell.value, str):
                cell.data_type = "s"  # texto que começa com "=" não pode virar fórmula
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    for j, name in enumerate(columns, 1):
        ws.column_dimensions[ws.cell(1, j).column_letter].width = WIDTHS.get(name, 16)
    ws.freeze_panes = "C2"
    ws.auto_filter.ref = ws.dimensions
    last = max(ws.max_row, 2)
    for name, options in validate:
        rule = DataValidation(type="list", formula1='"' + ",".join(options) + '"', allow_blank=True)
        rule.showErrorMessage = False  # categorias novas do codebook precisam poder ser digitadas
        ws.add_data_validation(rule)
        letter = ws.cell(1, columns.index(name) + 1).column_letter
        rule.add(f"{letter}2:{letter}{last}")
    wb.save(path)


def statement(problem) -> str:
    return problem["prompt"] if problem["benchmark"] == "mbpp" else lcb_user_prompt(problem)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--calibracao", type=int, default=10)
    a = ap.parse_args()
    params = load_params()
    problems, samples, mbpp = load_problems(params), load_samples(), load_mbpp()
    per = pd.read_csv(PROCESSED / "metrics" / "failed_problems.csv", encoding="utf-8-sig", keep_default_na=False)
    details = {}
    with open(PROCESSED / "metrics" / "failed_samples.jsonl", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            details[(r["benchmark"], r["problem_id"], r["sample_idx"])] = r

    rows = []
    for _, p in per.sort_values(["nivel_complexidade", "problem_id"]).iterrows():
        key = (p["benchmark"], p["problem_id"], int(p["primeira_amostra"]))
        d, s = details[key], samples[key]
        # No MBPP+ o código avaliado é o sanitizado pelo EvalPlus.
        code = mbpp[key[1:]]["solution"] if p["benchmark"] == "mbpp" else s["code"]
        others = [v for k, v in details.items() if k[:2] == key[:2] and k[2] != key[2]]
        rows.append({"problem_id": p["problem_id"], "benchmark": p["benchmark"], "dificuldade": p["dificuldade"],
                     "nivel_complexidade": int(p["nivel_complexidade"]), "manifestacao": d["manifestacao"],
                     "detalhe_erro": d["detalhe_erro"], "entrada_que_falhou": d["entrada"], "esperado": d["esperado"],
                     "obtido": d["obtido"], "amostras_reprovadas": int(p["amostras_reprovadas"]),
                     "recorrencia": p["recorrencia"], "mesma_manifestacao": p["mesma_manifestacao"],
                     "outras_manifestacoes": "; ".join(f"#{o['sample_idx']}: {o['manifestacao']}" for o in others),
                     "enunciado": statement(problems[p["benchmark"]][p["problem_id"]]), "codigo_gerado": code,
                     "suspeita_defeito_benchmark": p["suspeita_defeito_benchmark"],
                     "resumo_raciocinio": s.get("thinking_summary") or "(sem raciocínio nesta amostra)"})
    df = pd.DataFrame(rows)
    df.insert(0, "id_falha", [f"F{i:03d}" for i in range(1, len(df) + 1)])

    # Sorteio proporcional ao nível de complexidade, com ao menos uma falha de cada nível.
    rng = np.random.default_rng(params["pilot"]["seed"])
    shares = df["nivel_complexidade"].value_counts()
    quota = (shares / len(df) * a.calibracao).round().astype(int).clip(lower=1)
    calib = sorted(i for level, n in quota.items()
                   for i in rng.choice(df.index[df["nivel_complexidade"] == level], min(n, shares[level]), replace=False))
    official = df.drop(index=calib)
    print(f"{len(df)} falhas: {len(official)} na amostra oficial, {len(calib)} na calibração")

    OUT.mkdir(parents=True, exist_ok=True)
    coder = lambda c: [x.format(c=c) for x in CODER_COLUMNS]
    yes_no = ["sim", "não"]
    master = SCRIPT_COLUMNS + coder("A") + coder("B") + STAGE2_COLUMNS + FINAL_COLUMNS
    write_sheet(OUT / "codificacao.xlsx", official, master)
    write_sheet(OUT / "calibracao.xlsx", df.loc[calib], SCRIPT_COLUMNS + coder("A") + coder("B") + ["observacoes"])
    for c in "AB":
        write_sheet(OUT / f"etapa1_{c}.xlsx", official, SCRIPT_COLUMNS + coder(c),
                    validate=[(f"defeito_benchmark_{c}", yes_no), (f"causa_principal_{c}", CAUSES)])
    write_sheet(OUT / "etapa2_resumos.xlsx", official,
                ["id_falha", "problem_id", "codigo_gerado", "resumo_raciocinio", "causa_mudou_com_resumo_A",
                 "causa_mudou_com_resumo_B"])
    print("planilhas em", OUT)


if __name__ == "__main__":
    main()
