#!/usr/bin/env python3
"""Throughput/latency benchmark for the VL detector server (vLLM nemotron-nano-vl @ :8090).

Mirrors the production classify request (image + json-schema guided decoding) and sweeps
concurrency to find images/sec, latency percentiles, and output tokens/sec. Also samples
time-to-first-token via a streaming request.

    cd ~/aegis && .venv/bin/python scripts/benchmark_vl.py [image.jpg]
"""
import asyncio, base64, json, statistics, sys, time
import httpx

from backend import config
from backend.vl import CLASSIFY_PROMPT, CLASSIFY_SCHEMA

URL = config.VL_OPENAI_URL.rstrip("/") + "/chat/completions"
IMG = sys.argv[1] if len(sys.argv) > 1 else "/tmp/vl_test.jpg"
B64 = base64.b64encode(open(IMG, "rb").read()).decode("ascii")

def payload(stream=False):
    return {
        "model": config.VL_MODEL, "temperature": 0, "max_tokens": 128, "stream": stream,
        "response_format": {"type": "json_schema",
                            "json_schema": {"name": "incident", "schema": CLASSIFY_SCHEMA}},
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": CLASSIFY_PROMPT},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{B64}"}},
        ]}],
    }

async def one(client):
    t = time.perf_counter()
    r = await client.post(URL, json=payload(), timeout=120)
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
            "images_per_s": round(total / wall, 2),
            "tokens_per_s": round(sum(toks) / wall, 1),
            "p50_ms": round(statistics.median(lat), 1), "p95_ms": round(pct(95), 1),
            "mean_ms": round(statistics.mean(lat), 1), "mean_out_tok": round(statistics.mean(toks), 1)}

async def ttft_sample(client):
    """Streaming TTFT + inter-token latency for one request."""
    t = time.perf_counter(); first = None; n = 0
    async with client.stream("POST", URL, json=payload(stream=True), timeout=120) as r:
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
            "inter_token_ms": round((total - (first or 0)) / max(1, n - 1) * 1000, 1)}

async def main():
    async with httpx.AsyncClient() as c:        # warm
        await one(c); await one(c)
    out = {"image_bytes": len(base64.b64decode(B64)), "results": []}
    for conc in [1, 2, 4, 8, 16]:
        res = await level(conc, min(max(conc * 2, 12), 32))
        out["results"].append(res); print(json.dumps(res), flush=True)
    async with httpx.AsyncClient() as c:
        out["ttft"] = await ttft_sample(c)
    print("ttft:", json.dumps(out["ttft"]), flush=True)
    json.dump(out, open("/tmp/vl_bench.json", "w"), indent=2)
    print("WROTE /tmp/vl_bench.json", flush=True)

asyncio.run(main())
