#!/usr/bin/env python3
"""
Verificações por execução usadas na análise manual das falhas (etapa 1 e calibração).

Uso (dentro do contêiner Docker do projeto):
    pip install openpyxl            # numpy também, se a imagem não tiver (F072)
    python verificacoes.py --etapa1 etapa1_A.xlsx --calib calibracao.xlsx [--saida relatorio.csv]

As planilhas só são lidas, nunca alteradas. O código gerado vem da coluna codigo_gerado,
a entrada de entrada_que_falhou e o gabarito de esperado. Cada código roda num
subprocesso separado, com timeout.

Grupos de verificação
  H  harness: o código passa com stdin real e reproduz a falha quando o stdin é trocado por StringIO
  T  tolerância: a saída do código fica dentro da tolerância numérica declarada no enunciado
  V  respostas múltiplas: um validador confirma que a saída do código é válida pelo enunciado
  R  restrições: a entrada que falhou viola as Constraints do enunciado
  C  correção: força bruta ou correção pontual confirma o diagnóstico do código errado

Resultado de cada verificação: CONFIRMA (o diagnóstico da análise se sustenta), NAO_CONFIRMA
ou ERRO (a verificação não rodou). Os tempos não são medidos, porque dependem do hardware.
"""
import argparse
import ast
import csv
import itertools
import json
import os
import random
import re
import subprocess
import sys
import tempfile
from functools import lru_cache

random.seed(12345)
TIMEOUT = 60

# --------------------------------------------------------------------------- leitura


def carregar(caminho):
    from openpyxl import load_workbook
    ws = load_workbook(caminho, read_only=True).active
    linhas = list(ws.iter_rows(values_only=True))
    cab = linhas[0]
    return {l[0]: dict(zip(cab, l)) for l in linhas[1:] if l[0]}


# --------------------------------------------------------------------------- execução

_WRAP_STDIN_MEM = r'''
import io, sys
codigo = open(sys.argv[1], encoding="utf-8").read()
sys.stdin = io.StringIO(open(sys.argv[2], encoding="utf-8").read())
exec(compile(codigo, "<gerado>", "exec"), {"__name__": "__main__"})
'''

_WRAP_FUNC = r'''
import json, sys
from typing import *
import collections, math, heapq, bisect, itertools, functools
codigo = open(sys.argv[1], encoding="utf-8").read()
args = json.loads(open(sys.argv[2], encoding="utf-8").read())
nome = sys.argv[3]
ns = {"__name__": "gerado"}
exec("from typing import *\nimport collections, math, heapq, bisect, itertools, functools\n" + codigo, ns)
if "Solution" in ns:
    f = getattr(ns["Solution"](), nome)
else:
    f = ns[nome]
try:
    r = f(*args)
    print(json.dumps({"ok": True, "valor": repr(r)}))
except Exception as e:
    print(json.dumps({"ok": False, "erro": type(e).__name__ + ": " + str(e)}))
'''


def _tmp(texto):
    fd, p = tempfile.mkstemp(suffix=".txt")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(texto)
    return p


def rodar_stdin(codigo, entrada, memoria=False):
    """Roda um programa de stdin. memoria=True simula o harness (sys.stdin = StringIO)."""
    pc, pe = _tmp(codigo), _tmp(entrada)
    try:
        if memoria:
            pw = _tmp(_WRAP_STDIN_MEM)
            cmd = [sys.executable, "-I", pw, pc, pe]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
            os.unlink(pw)
        else:
            r = subprocess.run([sys.executable, "-I", pc], input=entrada,
                               capture_output=True, text=True, timeout=TIMEOUT)
        err = r.stderr.strip().splitlines()[-1] if r.stderr.strip() else ""
        return r.stdout, err
    except subprocess.TimeoutExpired:
        return None, "TIMEOUT"
    finally:
        os.unlink(pc); os.unlink(pe)


def chamar_funcao(codigo, nome, args):
    pc, pa, pw = _tmp(codigo), _tmp(json.dumps(args)), _tmp(_WRAP_FUNC)
    try:
        r = subprocess.run([sys.executable, "-I", pw, pc, pa, nome],
                           capture_output=True, text=True, timeout=TIMEOUT)
        linha = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""
        return json.loads(linha) if linha else {"ok": False, "erro": r.stderr.strip()[-300:]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "erro": "TIMEOUT"}
    finally:
        for p in (pc, pa, pw):
            os.unlink(p)


def norm(s):
    return "\n".join(l.rstrip() for l in str(s).strip().splitlines())


# --------------------------------------------------------------------------- relatório

RESULTADOS = []


def registrar(fid, grupo, descricao, confirma, evidencia):
    status = "CONFIRMA" if confirma is True else ("NAO_CONFIRMA" if confirma is False else "ERRO")
    RESULTADOS.append({"id_falha": fid, "grupo": grupo, "verificacao": descricao,
                       "resultado": status, "evidencia": evidencia})
    print(f"[{status:12}] {fid} ({grupo}) {descricao}\n               {evidencia}")


def protegido(fid, grupo, descricao):
    def deco(fn):
        def run(D):
            if fid not in D:
                registrar(fid, grupo, descricao, None, "falha não encontrada na planilha")
                return
            try:
                ok, ev = fn(D[fid])
                registrar(fid, grupo, descricao, ok, ev)
            except Exception as e:  # noqa: BLE001
                registrar(fid, grupo, descricao, None, f"{type(e).__name__}: {e}")
        run.fid = fid
        return run
    return deco


VERIFS_ETAPA1, VERIFS_CALIB = [], []


def etapa1(fid, grupo, descricao):
    def deco(fn):
        VERIFS_ETAPA1.append(protegido(fid, grupo, descricao)(fn))
        return fn
    return deco


def calib(fid, grupo, descricao):
    def deco(fn):
        VERIFS_CALIB.append(protegido(fid, grupo, descricao)(fn))
        return fn
    return deco


# =========================================================================== H: harness

def _harness(d):
    real, e1 = rodar_stdin(d["codigo_gerado"], d["entrada_que_falhou"])
    mem, e2 = rodar_stdin(d["codigo_gerado"], d["entrada_que_falhou"], memoria=True)
    passa_real = real is not None and norm(real) == norm(d["esperado"])
    falha_mem = mem is None or norm(mem) != norm(d["esperado"])
    ev = (f"stdin real -> {norm(real)[:60]!r} {e1[:80]} | stdin em memória -> "
          f"{norm(mem)[:60] if mem else ''!r} {e2[:120]} | esperado {norm(d['esperado'])[:60]!r}")
    return passa_real and falha_mem, ev


for _f in ("F057", "F072"):
    etapa1(_f, "H", "passa com stdin real e falha com stdin em StringIO (harness)")(_harness)
calib("F068", "H", "passa com stdin real e falha com stdin em StringIO (harness)")(_harness)


# =========================================================================== T: tolerância

TOL_IDS = ["F058", "F062", "F064", "F066", "F071", "F074", "F083", "F085", "F086", "F087", "F092", "F101"]


def _tolerancia(enunciado):
    m = re.search(r"(?:error|within)[^.]*?10\s*\^\s*\{?\s*(-\s*\d+)", enunciado, re.I | re.S)
    return 10.0 ** int(m.group(1).replace(" ", "")) if m else None


def _truncada(d):
    return "(truncated)" in str(d["entrada_que_falhou"])


def _verif_tol(d):
    tol = _tolerancia(d["enunciado"])
    if tol is None:
        return False, ("o enunciado NÃO declara tolerância numérica; a classificação como defeito "
                       "por tolerância não se sustenta só por este critério")
    if _truncada(d):
        out, err = d["obtido"], "(entrada truncada na planilha; usada a coluna 'obtido')"
    elif d["benchmark"] == "lcb" and "class Solution" not in d["codigo_gerado"]:
        out, err = rodar_stdin(d["codigo_gerado"], d["entrada_que_falhou"])
    else:
        nome = re.findall(r"def (\w+)\(self", d["codigo_gerado"])[0]
        r = chamar_funcao(d["codigo_gerado"], nome, ast.literal_eval(d["entrada_que_falhou"]))
        out, err = (r.get("valor"), r.get("erro", ""))
    if out is None:
        return False, f"código não produziu saída: {err}"
    a = [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", str(out))]
    b = [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", str(d["esperado"]))]
    if len(a) != len(b) or not a:
        return False, f"saídas com formatos diferentes: {str(out)[:60]!r} x {d['esperado'][:60]!r}"
    dif = max(min(abs(x - y), abs(x - y) / max(abs(y), 1e-300)) for x, y in zip(a, b))
    fonte = " (saída da coluna 'obtido', entrada truncada)" if _truncada(d) else ""
    return dif <= tol, f"maior erro (abs. ou rel.) {dif:.2e}; tolerância do enunciado {tol:.0e}{fonte}"


for _f in TOL_IDS:
    etapa1(_f, "T", "saída dentro da tolerância numérica do enunciado")(_verif_tol)


# =========================================================================== V: respostas múltiplas

def _ints(s):
    return [int(x) for x in re.findall(r"-?\d+", str(s))]


@calib("F056", "V", "saída é um inteiro 0-9 diferente de A+B")
def _v056(d):
    a, b = _ints(d["entrada_que_falhou"])
    out, err = rodar_stdin(d["codigo_gerado"], d["entrada_que_falhou"])
    v = int(out.strip())
    return 0 <= v <= 9 and v != a + b, f"A+B={a+b}; código imprime {v}"


@calib("F110", "V", "procedimento válido e com score ótimo (igual ao do gabarito)")
def _v110(d):
    t = _ints(d["entrada_que_falhou"]); n = t[0]; ed = list(zip(t[1::2], t[2::2]))
    out, _ = rodar_stdin(d["codigo_gerado"], d["entrada_que_falhou"])

    def simular(saida):
        adj = {v: set() for v in range(1, n + 1)}
        for u, v in ed:
            adj[u].add(v); adj[v].add(u)
        nums = _ints(saida); total = 0
        if len(nums) != n:
            return None
        for x, y in zip(nums[::2], nums[1::2]):
            if x not in adj or y not in adj or len(adj[x]) != 1 or len(adj[y]) != 1:
                return None
            dist = {x: 0}; fila = [x]
            for u in fila:
                for w in adj[u]:
                    if w not in dist:
                        dist[w] = dist[u] + 1; fila.append(w)
            total += dist[y]
            for z in (x, y):
                for w in adj[z]:
                    adj[w].discard(z)
                del adj[z]
            # o restante precisa manter emparelhamento perfeito (folha casa com o vizinho)
            g = {k: set(v) for k, v in adj.items()}
            while g:
                folha = next((k for k, v in g.items() if len(v) <= 1), None)
                if folha is None or not g[folha]:
                    return None
                viz = next(iter(g[folha]))
                for z in (folha, viz):
                    for w in g[z]:
                        if w in g:
                            g[w].discard(z)
                for z in (folha, viz):
                    g.pop(z, None)
        return total
    sc, se = simular(out), simular(d["esperado"])
    return sc is not None and sc == se, f"score do código {sc}; score do gabarito {se}"


@etapa1("F091", "V", "posições dos cubos geram exatamente (V1, V2, V3)")
def _v091(d):
    alvo = _ints(d["entrada_que_falhou"])
    out, _ = rodar_stdin(d["codigo_gerado"], d["entrada_que_falhou"])
    c = _ints(out)
    cubos = [c[0:3], c[3:6], c[6:9]]
    lo = [min(x[i] for x in cubos) for i in range(3)]
    hi = [max(x[i] for x in cubos) + 7 for i in range(3)]
    cont = [0, 0, 0, 0]
    for x in range(lo[0], hi[0]):
        for y in range(lo[1], hi[1]):
            for z in range(lo[2], hi[2]):
                k = sum(a <= x < a + 7 and b <= y < b + 7 and e <= z < e + 7 for a, b, e in cubos)
                cont[k] += 1
    ok = out.strip().startswith("Yes") and cont[1:] == alvo and all(abs(v) <= 100 for v in c)
    return ok, f"volumes gerados {cont[1:]}; pedidos {alvo}"


@etapa1("F098", "V", "permutação sem cruzamento de segmentos")
def _v098(d):
    t = _ints(d["entrada_que_falhou"]); n = t[0]
    P = list(zip(t[1:2 * n + 1:2], t[2:2 * n + 1:2])); Q = list(zip(t[2 * n + 1::2], t[2 * n + 2::2]))
    out, _ = rodar_stdin(d["codigo_gerado"], d["entrada_que_falhou"]); R = _ints(out)

    def cr(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    def cruza(p1, p2, p3, p4):
        return (cr(p3, p4, p1) > 0) != (cr(p3, p4, p2) > 0) and (cr(p1, p2, p3) > 0) != (cr(p1, p2, p4) > 0)
    seg = [(P[i], Q[R[i] - 1]) for i in range(n)]
    x = any(cruza(*seg[i], *seg[j]) for i in range(n) for j in range(i + 1, n))
    return sorted(R) == list(range(1, n + 1)) and not x, f"R={R}; há cruzamento: {x}"


@etapa1("F115", "V", "conjunto de confusos não gera contradição (força bruta)")
def _v115(d):
    t = _ints(d["entrada_que_falhou"]); n, m = t[0], t[1]
    T = [tuple(t[2 + 3 * i:5 + 3 * i]) for i in range(m)]
    out, _ = rodar_stdin(d["codigo_gerado"], d["entrada_que_falhou"]); conf = out.strip()

    def consistente(cf):
        for h in itertools.product([0, 1], repeat=n):
            if all((h[b - 1] == (1 if c == 0 else 0)) == bool(h[a - 1] ^ int(cf[a - 1])) for a, b, c in T):
                return True
        return False
    return len(conf) == n and consistente(conf), f"saída do código {conf!r}: sem contradição = {consistente(conf)}"


# =========================================================================== R: restrições

def _args(d):
    return ast.literal_eval(d["entrada_que_falhou"])


@etapa1("F059", "R", "entrada viola 1 <= s.length")
def _r059(d):
    s = _args(d)[0]; return len(s) < 1, f"len(s) = {len(s)}"


@etapa1("F060", "R", "entrada viola 1 <= rewardValues[i]")
def _r060(d):
    v = _ints(d["entrada_que_falhou"]); return min(v) < 1, f"menor valor na entrada = {min(v)} (entrada truncada na planilha; checados os valores visíveis)"


@etapa1("F077", "R", "entrada viola 1 <= nums[i] <= nums.length")
def _r077(d):
    v = _args(d)[0]; return any(not 1 <= x <= len(v) for x in v), f"nums = {v}, len = {len(v)}"


@etapa1("F078", "R", "entrada viola 3 <= points.length")
def _r078(d):
    v = _args(d)[0]
    ok = len(v) < 3 or not all(isinstance(p, list) and len(p) == 2 for p in v)
    return ok, f"points = {v} (menos de 3 pontos e nem é lista de pares)"


@etapa1("F082", "R", "entrada viola nums[i] < 2^7")
def _r082(d):
    v = _ints(d["entrada_que_falhou"]); return max(v) >= 128, f"maior valor na entrada = {max(v)} (entrada truncada na planilha; checados os valores visíveis)"


@etapa1("F102", "R", "entrada viola 1 <= P_i <= i")
def _r102(d):
    t = _ints(d["entrada_que_falhou"]); P = t[1:]
    ruins = [(i + 1, p) for i, p in enumerate(P) if not 1 <= p <= i + 1]
    return bool(ruins), f"(i, P_i) inválidos: {ruins}"


# =========================================================================== C: correção

@etapa1("F040", "C", "força bruta: maior subconjunto com todos os pares divisíveis")
def _c040(d):
    a = _args(d)[0]; best = 0
    for k in range(1, len(a) + 1):
        for c in itertools.combinations(a, k):
            if all(x % y == 0 or y % x == 0 for x, y in itertools.combinations(c, 2)):
                best = k
    r = chamar_funcao(d["codigo_gerado"], "largest_subset", [a])
    return str(best) == r.get("valor") and str(best) != str(d["esperado"]).strip(), \
        f"força bruta = {best}; código = {r.get('valor')}; gabarito = {d['esperado']}"


@etapa1("F044", "C", "aritmética exata: índice mínimo com T(k) >= 10^(n-1)")
def _c044(d):
    n = _args(d)[0]; t = 10 ** (n - 1)
    k_cod = int(chamar_funcao(d["codigo_gerado"], "find_Index", [n])["valor"])
    k_exp = int(str(d["esperado"]).strip())

    def minimo(k):
        return k * (k + 1) // 2 >= t and (k - 1) * k // 2 < t
    return minimo(k_cod) and not minimo(k_exp), f"código mínimo: {minimo(k_cod)}; gabarito mínimo: {minimo(k_exp)}"


def _primos(N=10000):
    ip = [True] * N; ip[0] = ip[1] = False
    for i in range(2, int(N ** .5) + 1):
        if ip[i]:
            ip[i * i::i] = [False] * len(ip[i * i::i])
    return ip


@etapa1("F063", "C", "Dijkstra proibindo zero no dígito mais significativo reproduz o gabarito")
def _c063(d):
    import heapq
    n, m = _args(d); ip = _primos(); L = len(str(n))

    def solve(permite_zero):
        if ip[n] or ip[m]:
            return -1
        dist = {n: n}; pq = [(n, n)]
        while pq:
            dd, x = heapq.heappop(pq)
            if x == m:
                return dd
            if dd > dist[x]:
                continue
            s = list(str(x).zfill(L))
            for i in range(L):
                c = int(s[i])
                for nc in (c - 1, c + 1):
                    if not 0 <= nc <= 9 or (not permite_zero and i == 0 and nc == 0):
                        continue
                    s[i] = str(nc); y = int("".join(s)); s[i] = str(c)
                    if not ip[y] and dd + y < dist.get(y, float("inf")):
                        dist[y] = dd + y; heapq.heappush(pq, (dd + y, y))
        return -1
    com, sem = solve(True), solve(False)
    return str(sem) == str(d["esperado"]).strip() and str(com) == str(d["obtido"]).strip(), \
        f"permitindo zero à esquerda = {com} (saída do código); proibindo = {sem}; gabarito = {d['esperado']}"


def _brute_barras(H, W, bars):
    bars = [list(b) for b in bars]; occ = {}
    for i, (r, c, l) in enumerate(bars):
        for j in range(l):
            occ[(r, c + j)] = i
    mudou = True
    while mudou:
        mudou = False
        for i, (r, c, l) in enumerate(bars):
            if r < H and all((r + 1, c + j) not in occ for j in range(l)):
                for j in range(l):
                    del occ[(r, c + j)]; occ[(r + 1, c + j)] = i
                bars[i][0] = r + 1; mudou = True
    return "\n".join(str(b[0]) for b in bars)


@calib("F100", "C", "código erra contra simulação e a correção no pull-up zera os erros")
def _c100(d):
    cod = d["codigo_gerado"]
    alvo = "                x=mn[2*p]; y=mn[2*p+1]"
    if alvo not in cod:
        return None, "trecho do pull-up não encontrado para aplicar a correção"
    corr = cod.replace(alvo, "                if lz[p]: continue\n" + alvo)
    erros_o = erros_c = 0
    for _ in range(150):
        H, W = random.randint(1, 8), random.randint(1, 8); occ = set(); bars = []
        for _ in range(random.randint(1, 8)):
            r, c = random.randint(1, H), random.randint(1, W); l = random.randint(1, W - c + 1)
            cel = {(r, c + j) for j in range(l)}
            if cel & occ:
                continue
            occ |= cel; bars.append((r, c, l))
        s = f"{H} {W} {len(bars)}\n" + "\n".join(f"{a} {b} {c}" for a, b, c in bars) + "\n"
        b = _brute_barras(H, W, bars)
        erros_o += norm(rodar_stdin(cod, s)[0]) != b
        erros_c += norm(rodar_stdin(corr, s)[0]) != b
    fe = norm(rodar_stdin(corr, d["entrada_que_falhou"])[0]) == norm(d["esperado"])
    return erros_o > 0 and erros_c == 0 and fe, \
        f"150 casos aleatórios: original erra {erros_o}, corrigido erra {erros_c}; corrigido passa na entrada da falha: {fe}"


def _jogo105(n, arestas0):
    pares = list(itertools.combinations(range(n), 2)); P = len(pares)

    def bip(mask):
        col = [-1] * n
        for s in range(n):
            if col[s] != -1:
                continue
            col[s] = 0; pilha = [s]
            while pilha:
                u = pilha.pop()
                for k, (a, b) in enumerate(pares):
                    if mask >> k & 1 and u in (a, b):
                        w = b if a == u else a
                        if col[w] == -1:
                            col[w] = col[u] ^ 1; pilha.append(w)
                        elif col[w] == col[u]:
                            return False
        return True

    @lru_cache(None)
    def vence(mask):
        for k in range(P):
            if not mask >> k & 1:
                nm = mask | 1 << k
                if bip(nm) and not vence(nm):
                    return True
        return False
    m0 = sum(1 << pares.index(tuple(sorted(e))) for e in arestas0)
    return "Aoki" if vence(m0) else "Takahashi"


@etapa1("F105", "C", "jogo resolvido por força bruta diverge da regra do código")
def _c105(d):
    cod = d["codigo_gerado"]; div = []
    casos = [(6, [])] + [(n, []) for n in range(1, 6)]
    for _ in range(40):
        n = random.randint(2, 5)
        pares = list(itertools.combinations(range(n), 2)); random.shuffle(pares)
        cor = [random.randint(0, 1) for _ in range(n)]
        ed = [p for p in pares if cor[p[0]] != cor[p[1]] and random.random() < .5]
        casos.append((n, ed))
    for n, ed in casos:
        s = f"{n} {len(ed)}\n" + "".join(f"{u + 1} {v + 1}\n" for u, v in ed)
        if norm(rodar_stdin(cod, s)[0]) != _jogo105(n, ed):
            div.append((n, ed))
    return bool(div), f"{len(div)} de {len(casos)} grafos com resposta errada; exemplo: N={div[0][0]}, arestas={div[0][1]}" if div else "nenhuma divergência"


@etapa1("F107", "C", "trocar o expoente N+1 por N faz o código acertar os exemplos")
def _c107(d):
    cod = d["codigo_gerado"]
    if "e=N+1" not in cod:
        return None, "trecho 'e=N+1' não encontrado"
    corr = cod.replace("e=N+1", "e=N")
    casos = [("1 7", "16"), ("3 11", "16095"), ("81131 14", "182955659")]
    res = [(norm(rodar_stdin(cod, i)[0]), norm(rodar_stdin(corr, i)[0]), e) for i, e in casos]
    return all(c == e for _, c, e in res) and any(o != e for o, _, e in res), f"(original, corrigido, esperado): {res}"


@etapa1("F108", "C", "contar x < t (em vez de x >= t) faz o código acertar os exemplos")
def _c108(d):
    cod = d["codigo_gerado"]; alvo = "v = floor_sum(K, M, C, M - t) - base"
    if alvo not in cod:
        return None, "trecho da função degrau não encontrado"
    corr = cod.replace(alvo, "v = K - (floor_sum(K, M, C, M - t) - base)")
    casos = [("2 5 3 3\n1 3", "4"), ("5 4 3 182\n0 3 2 1 2", "0"), ("5 718 651 193855\n3 532 44 109 58", "29484897")]
    res = [(norm(rodar_stdin(cod, i)[0]), norm(rodar_stdin(corr, i)[0]), e) for i, e in casos]
    return all(c == e for _, c, e in res) and any(o != e for o, _, e in res), f"(original, corrigido, esperado): {res}"


def _fennec(A):
    sys.setrecursionlimit(100000)

    @lru_cache(None)
    def vence(U, T):
        for k, v in enumerate(U):
            if k and U[k - 1] == v:
                continue
            nU = U[:k] + U[k + 1:]
            if not nU or not vence(nU, T + v - 1):
                return True
        return T > 0 and not vence(U, T - 1)
    return "Fennec" if vence(tuple(sorted(A)), 0) else "Snuke"


@calib("F120", "C", "solucionador exato do jogo concorda com o código (gabarito suspeito)")
def _c120(d):
    amostras = [([1, 9, 2], "Fennec"), ([25, 29], "Snuke"), ([1, 9, 2, 25, 2, 9], "Snuke")]
    ok_am = all(_fennec(a) == e for a, e in amostras)
    A = _ints(d["entrada_que_falhou"])[1:]
    exato = _fennec(A); cod = norm(rodar_stdin(d["codigo_gerado"], d["entrada_que_falhou"])[0])
    return ok_am and exato == cod != norm(d["esperado"]), \
        f"solucionador acerta as 3 amostras: {ok_am}; exato = {exato}; código = {cod}; gabarito = {norm(d['esperado'])}"


@etapa1("F122", "C", "força bruta mostra que o código erra em entradas pequenas")
def _c122(d):
    @lru_cache(None)
    def g(t):
        if len(t) <= 1:
            return 0
        return max(abs(t[i] - t[i + 1]) + g(t[:i] + t[i + 2:]) for i in range(len(t) - 1))
    erros = 0; ex = None
    for _ in range(100):
        n = random.choice([3, 5, 7, 9]); a = [random.randint(1, 20) for _ in range(n)]
        r = norm(rodar_stdin(d["codigo_gerado"], f"{n}\n{' '.join(map(str, a))}\n")[0])
        if r != str(g(tuple(a))):
            erros += 1; ex = ex or (a, r, g(tuple(a)))
    return erros > 0, f"{erros}/100 casos errados; exemplo (entrada, código, correto): {ex}"


@etapa1("F102", "C", "código acerta todas as entradas válidas (comparado com simulação)")
def _c102(d):
    erros = 0
    for _ in range(150):
        n = random.randint(1, 12); P = [random.randint(1, i) for i in range(1, n + 1)]
        A = []
        for i, p in enumerate(P, 1):
            A.insert(p - 1, i)
        erros += norm(rodar_stdin(d["codigo_gerado"], f"{n}\n{' '.join(map(str, P))}\n")[0]) != " ".join(map(str, A))
    return erros == 0, f"{erros}/150 entradas válidas com saída errada"


@etapa1("F059", "C", "código acerta os exemplos do enunciado")
def _c059(d):
    res = [chamar_funcao(d["codigo_gerado"], "lastNonEmptyString", [s]).get("valor") for s in ("aabcbbca", "abcd")]
    return res == ["'ba'", "'abcd'"], f"saídas para os exemplos: {res} (esperado 'ba', 'abcd')"


# =========================================================================== main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--etapa1", required=True, help="planilha da etapa 1 (ex.: etapa1_A.xlsx)")
    ap.add_argument("--calib", help="planilha de calibração (ex.: calibracao.xlsx)")
    ap.add_argument("--saida", default="relatorio_verificacoes.csv")
    a = ap.parse_args()
    print(f"Python {sys.version.split()[0]} em {sys.platform}\n")
    E = carregar(a.etapa1)
    for v in VERIFS_ETAPA1:
        v(E)
    if a.calib:
        C = carregar(a.calib)
        for v in VERIFS_CALIB:
            v(C)
    with open(a.saida, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(RESULTADOS[0]), delimiter=";")
        w.writeheader(); w.writerows(RESULTADOS)
    tot = {s: sum(r["resultado"] == s for r in RESULTADOS) for s in ("CONFIRMA", "NAO_CONFIRMA", "ERRO")}
    print(f"\nResumo: {tot}. Relatório salvo em {a.saida}")


if __name__ == "__main__":
    main()
