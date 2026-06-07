#!/usr/bin/env python3
"""Latency/throughput benchmark for the operator-briefing text model
(llama.cpp Nemotron-3-Nano-30B-A3B @ :30000, OpenAI-compatible).

Mirrors the production briefing request and measures end-to-end latency, output
tokens/sec, and streaming time-to-first-token across concurrency levels.

    cd ~/aegis && .venv/bin/python scripts/benchmark_briefing.py
"""
import asyncio, json, statistics, time
import httpx

from backend import config
from backend.vl import _briefing_prompt

URL = config.BRIEFING_URL.rstrip("/") + "/chat/completions"
# representative incident summary (what generate_briefing is fed)
SUMMARY = ("Active incidents (6): congestion A406 North Circular; congestion A2 Old Kent Rd; "
           "stalled_vehicle A40 Westway; hazard debris A23 Brixton; congestion A501 Marylebone Rd; "
           "accident A13 Canning Town. TfL feed matches 4/6; 2 ahead of feed by ~8 min.")
PROMPT = _briefing_prompt(SUMMARY)

def payload(stream=False):
    return {"model": config.BRIEFING_MODEL, "temperature": 0.3,
            "max_tokens": config.BRIEFING_MAX_TOKENS, "stream": stream,
            "messages": [{"role": "user", "content": PROMPT}]}

async def one(client):
    t = time.perf_counter()
    r = await client.post(URL, json=payload(), timeout=300)
    dt = time.perf_counter() - t
    r.raise_for_status()
    tok = r.json().get("usage", {}).get("completion_tokens", 0)
    return dt * 1000, tok

async def level(concurrency, total):
    sem = asyncio.Semaphore(concurrency)
    lat, toks = [], []
    async with httpx.AsyncClient() as c:
        async def task():
            async with sem:
                dt, tk = await one(c); lat.append(dt); toks.append(tk)
        w0 = time.perf_counter()
        await asyncio.gather(*(task() for _ in range(total)))
        wall = time.perf_counter() - w0
    lat.sort()
    pct = lambda p: lat[min(len(lat)-1, int(p/100*len(lat)))]
    return {"concurrency": concurrency, "requests": total,
            "briefings_per_s": round(total / wall, 2),
            "tokens_per_s": round(sum(toks) / wall, 1),
            "p50_ms": round(statistics.median(lat), 1), "p95_ms": round(pct(95), 1),
            "mean_ms": round(statistics.mean(lat), 1), "mean_out_tok": round(statistics.mean(toks), 1)}

async def ttft_sample(client):
    t = time.perf_counter(); first = None; n = 0
    async with client.stream("POST", URL, json=payload(stream=True), timeout=300) as r:
        async for line in r.aiter_lines():
            if line.startswith("data:") and "[DONE]" not in line:
                try:
                    d = json.loads(line[5:].strip())
                    if d.get("choices", [{}])[0].get("delta", {}).get("content"):
                        if first is None: first = time.perf_counter() - t
                        n += 1
                except Exception:
                    pass
    total = time.perf_counter() - t
    return {"ttft_ms": round(first * 1000, 1) if first else None, "tokens": n,
            "total_ms": round(total * 1000, 1),
            "decode_tok_per_s": round((n - 1) / max(0.001, total - (first or 0)), 1)}

async def main():
    async with httpx.AsyncClient() as c:        # warm
        await one(c)
    out = {"results": []}
    for conc in [1, 2, 4]:
        res = await level(conc, max(conc * 2, 6))
        out["results"].append(res); print(json.dumps(res), flush=True)
    async with httpx.AsyncClient() as c:
        out["ttft"] = await ttft_sample(c)
    print("ttft:", json.dumps(out["ttft"]), flush=True)
    json.dump(out, open("/tmp/briefing_bench.json", "w"), indent=2)
    print("WROTE /tmp/briefing_bench.json", flush=True)

asyncio.run(main())
