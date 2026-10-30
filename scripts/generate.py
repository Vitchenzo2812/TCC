"""Geração das soluções com o Claude Opus 5.5.

Subcomandos:
  select-pilot                     sorteia os problemas do piloto -> config/pilot_ids.json
  sync   --run NOME --ids ARQ      requisições síncronas (streaming), usado no piloto
  batch-submit  --run NOME [--ids ARQ]   envia a Message Batches API (todos os problemas se --ids for omitido)
  batch-collect --run NOME         baixa os resultados do lote -> generations.jsonl
  retry  --run NOME                regera UMA vez as amostras truncadas, recusadas ou com erro -> retries.jsonl
  cost   --run NOME                custo observado e projeção para a rodada completa

Cada execução escreve em data/raw/<NOME>/; arquivos brutos nunca são sobrescritos.
"""
import argparse
import json
import platform
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import anthropic
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request

from common import RAW, ROOT, build_request, custom_id, load_params, load_problems, read_jsonl, write_once


def now():
    return datetime.now(timezone.utc).isoformat()


def run_dir(name):
    return RAW / name


def write_run_meta(name, params, extra):
    meta = {"created_utc": now(), "python": sys.version, "platform": platform.platform(),
            "anthropic_sdk": anthropic.__version__, "params": params, **extra}
    path = run_dir(name) / f"run_meta_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
    with write_once(path) as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def jobs_for(ids, problems, n):
    return [(problems[b][pid], k) for b, pid in ids for k in range(n)]


def all_ids(problems):
    return [(b, pid) for b in ("mbpp", "lcb") for pid in problems[b]]


def load_ids(path):
    return [tuple(x) for x in json.loads((ROOT / path).read_text(encoding="utf-8"))]


def record_of(problem, k, request, response=None, error=None, **extra):
    rec = {"problem_id": problem["problem_id"], "benchmark": problem["benchmark"], "sample_idx": k,
           "custom_id": custom_id(problem["benchmark"], problem["problem_id"], k),
           "timestamp_utc": now(), "request": request, **extra}
    if response is not None:
        rec["response"] = response
    if error is not None:
        rec["error"] = error
    return rec


def call_sync(client, request):
    # Streaming evita timeout HTTP com max_tokens alto; o resultado final é a mensagem completa.
    with client.messages.stream(**request) as stream:
        return stream.get_final_message().model_dump(mode="json")


def run_sync(name, jobs, params, out_name, workers):
    client = anthropic.Anthropic(max_retries=4)
    out_path = run_dir(name) / out_name
    lock = threading.Lock()
    with write_once(out_path) as f:
        def work(problem, k):
            request = build_request(problem, params)
            try:
                rec = record_of(problem, k, request, response=call_sync(client, request))
            except anthropic.APIStatusError as e:
                rec = record_of(problem, k, request, error={"status": e.status_code, "type": type(e).__name__, "message": str(e)})
            except anthropic.APIConnectionError as e:
                rec = record_of(problem, k, request, error={"status": None, "type": type(e).__name__, "message": str(e)})
            with lock:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                f.flush()
            return rec

        with ThreadPoolExecutor(workers) as pool:
            futures = [pool.submit(work, p, k) for p, k in jobs]
            for i, fut in enumerate(as_completed(futures), 1):
                rec = fut.result()
                status = rec.get("response", {}).get("stop_reason") or f"ERRO {rec['error']['type']}"
                print(f"[{i}/{len(jobs)}] {rec['custom_id']}: {status}", flush=True)
    print(f"gravado: {out_path}")


def cmd_select_pilot(params, problems):
    cfg = params["pilot"]
    rng = random.Random(cfg["seed"])
    ids = [("mbpp", pid) for pid in rng.sample(sorted(problems["mbpp"]), cfg["mbpp"])]
    for diff, k in cfg["lcb"].items():
        pool = sorted(pid for pid, p in problems["lcb"].items() if p["difficulty"] == diff)
        ids += [("lcb", pid) for pid in rng.sample(pool, k)]
    with write_once(ROOT / "config" / "pilot_ids.json") as f:
        json.dump(ids, f, indent=1)
    print(ids)


def cmd_make_lot(params, problems, lot, usd, per_sample):
    """Divide a rodada completa em lotes que caibam no saldo. A ordem dos problemas é sorteada uma vez
    (semente 42) e não depende de nenhum resultado; o lote N pega os próximos problemas dessa ordem
    até o custo estimado atingir `usd`. O lote 1 começa pelo MBPP+ inteiro."""
    order_path = ROOT / "config" / "lots" / "order.json"
    if not order_path.exists():
        lcb = sorted(problems["lcb"])
        random.Random(42).shuffle(lcb)
        with write_once(order_path) as f:
            json.dump([["mbpp", p] for p in sorted(problems["mbpp"])] + [["lcb", p] for p in lcb], f, indent=0)
    order = [tuple(x) for x in json.loads(order_path.read_text(encoding="utf-8"))]
    taken = set()
    for prev in range(1, lot):
        taken |= {tuple(x) for x in json.loads((ROOT / "config" / "lots" / f"lot{prev}.json").read_text(encoding="utf-8"))}
    ids, total = [], 0.0
    for b, pid in order:
        if (b, pid) in taken:
            continue
        group = "mbpp" if b == "mbpp" else f"lcb_{problems['lcb'][pid]['difficulty']}"
        cost = per_sample[group] * params["n_samples"]
        if total + cost > usd and ids:
            break
        ids.append((b, pid))
        total += cost
    with write_once(ROOT / "config" / "lots" / f"lot{lot}.json") as f:
        json.dump(ids, f, indent=0)
    left = len(order) - len(taken) - len(ids)
    print(f"lote {lot}: {len(ids)} problemas, custo estimado US$ {total:.2f}; restam {left} problemas")


def cmd_batch_submit(name, ids, params, problems):
    jobs = jobs_for(ids, problems, params["n_samples"])
    reqs, sidecar = [], []
    for problem, k in jobs:
        request = build_request(problem, params)
        cid = custom_id(problem["benchmark"], problem["problem_id"], k)
        reqs.append(Request(custom_id=cid, params=MessageCreateParamsNonStreaming(**request)))
        sidecar.append({"custom_id": cid, "problem_id": problem["problem_id"],
                        "benchmark": problem["benchmark"], "sample_idx": k, "request": request})
    assert len({r["custom_id"] for r in sidecar}) == len(sidecar), "custom_id duplicado"
    assert not (run_dir(name) / "batch_requests.jsonl").exists(), "lote já enviado para esta execução"
    # Grava as requisições só depois que a API aceitar o lote, para não deixar arquivo bruto órfão.
    batch = anthropic.Anthropic().messages.batches.create(requests=reqs)
    with write_once(run_dir(name) / "batch_requests.jsonl") as f:
        for r in sidecar:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with write_once(run_dir(name) / "batch_meta.json") as f:
        json.dump({"submitted_utc": now(), "batch": batch.model_dump(mode="json")}, f, indent=2)
    write_run_meta(name, params, {"mode": "batch", "batch_id": batch.id, "n_requests": len(reqs)})
    print(f"lote {batch.id} enviado com {len(reqs)} requisições")


def cmd_batch_collect(name):
    client = anthropic.Anthropic()
    meta = json.loads((run_dir(name) / "batch_meta.json").read_text(encoding="utf-8"))
    batch_id = meta["batch"]["id"]
    while (batch := client.messages.batches.retrieve(batch_id)).processing_status != "ended":
        print(f"{now()} {batch.processing_status} {batch.request_counts.model_dump()}", flush=True)
        time.sleep(120)
    sidecar = {r["custom_id"]: r for r in read_jsonl(run_dir(name) / "batch_requests.jsonl")}
    with write_once(run_dir(name) / "generations.jsonl") as f:
        for res in client.messages.batches.results(batch_id):
            s = sidecar[res.custom_id]
            rec = {k: s[k] for k in ("problem_id", "benchmark", "sample_idx", "custom_id", "request")}
            rec["timestamp_utc"] = now()
            rec["batch_id"] = batch_id
            if res.result.type == "succeeded":
                rec["response"] = res.result.message.model_dump(mode="json")
            else:
                rec["error"] = res.result.model_dump(mode="json")
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"resultados gravados; contagem: {batch.request_counts.model_dump()}")


def needs_retry(rec):
    return "error" in rec or rec["response"]["stop_reason"] in ("max_tokens", "refusal")


def cmd_retry(name, params, problems, workers):
    gens = read_jsonl(run_dir(name) / "generations.jsonl")
    todo = [r for r in gens if needs_retry(r)]
    print(f"{len(todo)} de {len(gens)} amostras serão regeradas uma única vez")
    if todo:
        jobs = [(problems[r["benchmark"]][r["problem_id"]], r["sample_idx"]) for r in todo]
        run_sync(name, jobs, params, "retries.jsonl", workers)


def usage_of(rec):
    u = rec.get("response", {}).get("usage") or {}
    return u.get("input_tokens", 0), u.get("output_tokens", 0)


def usage_groups(name, problems):
    groups = {}
    for r in read_jsonl(run_dir(name) / "generations.jsonl"):
        key = "mbpp" if r["benchmark"] == "mbpp" else f"lcb_{problems['lcb'][r['problem_id']]['difficulty']}"
        groups.setdefault(key, []).append(usage_of(r))
    return groups


def per_sample_cost(name, params, problems):
    price = params["batch_pricing_usd_per_mtok"]
    return {key: sum(i * price["input"] + o * price["output"] for i, o in us) / len(us) / 1e6
            for key, us in usage_groups(name, problems).items()}


def cmd_cost(name, params, problems):
    price = params["batch_pricing_usd_per_mtok"]
    groups = usage_groups(name, problems)
    total = 0.0
    print(f"{'grupo':12} {'n':>4} {'in_med':>8} {'out_med':>8} {'out_max':>8}  US$/amostra(batch)")
    for key, us in sorted(groups.items()):
        ins, outs = [u[0] for u in us], [u[1] for u in us]
        per = (sum(ins) / len(us) * price["input"] + sum(outs) / len(us) * price["output"]) / 1e6
        if key == "mbpp":
            n_full = len(problems["mbpp"])
        else:
            n_full = sum(1 for p in problems["lcb"].values() if p["difficulty"] == key[4:])
        total += per * n_full * params["n_samples"]
        print(f"{key:12} {len(us):>4} {sum(ins)/len(us):>8.0f} {sum(outs)/len(us):>8.0f} {max(outs):>8}  {per:.4f}")
    print(f"projeção da rodada completa (Batch API, n={params['n_samples']}): US$ {total:.2f}"
          f"  (orçamento: US$ {params['budget_usd']})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["select-pilot", "make-lot", "sync", "batch-submit", "batch-collect", "retry", "cost"])
    ap.add_argument("--lot", type=int)
    ap.add_argument("--usd", type=float, help="make-lot: custo estimado máximo do lote")
    ap.add_argument("--cost-run", default="pilot", help="make-lot: execução cujo custo por amostra é usado")
    ap.add_argument("--run")
    ap.add_argument("--ids", help="JSON com [[benchmark, problem_id], ...]")
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    params = load_params()
    problems = load_problems(params)

    if a.cmd == "select-pilot":
        cmd_select_pilot(params, problems)
    elif a.cmd == "make-lot":
        cmd_make_lot(params, problems, a.lot, a.usd, per_sample_cost(a.cost_run, params, problems))
    elif a.cmd == "sync":
        ids = load_ids(a.ids)
        write_run_meta(a.run, params, {"mode": "sync", "ids_file": a.ids})
        run_sync(a.run, jobs_for(ids, problems, params["n_samples"]), params, "generations.jsonl", a.workers)
    elif a.cmd == "batch-submit":
        cmd_batch_submit(a.run, load_ids(a.ids) if a.ids else all_ids(problems), params, problems)
    elif a.cmd == "batch-collect":
        cmd_batch_collect(a.run)
    elif a.cmd == "retry":
        cmd_retry(a.run, params, problems, a.workers)
    elif a.cmd == "cost":
        cmd_cost(a.run, params, problems)


if __name__ == "__main__":
    main()
