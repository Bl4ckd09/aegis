"""Standalone validation: fetch a live JamCam frame and classify it via an
OpenAI-compatible VLM endpoint (e.g. the Modal Nemotron-Nano-VL deploy).

Stdlib only (urllib/base64/json) so it runs on the Mac with no venv/deps.
Usage:  python3 scripts/classify_modal.py <base_url>   # base_url ends in /v1
First call cold-starts the endpoint (downloads model) — uses a long timeout.
"""
import base64
import json
import sys
import time
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "https://sun559064--aegis-vllm-serve.modal.run/v1").rstrip("/")
MODEL = "nemotron-nano-vl"
TIMEOUT = 900  # allow cold start (container boot + model download + vLLM load)

PROMPT = """You are a cautious traffic-camera incident classifier for a road control room. \
Classify the OVERALL road condition in this low-resolution CCTV frame into exactly ONE category.
Categories: clear, congestion, accident, stalled_vehicle, hazard, obscured.
Rules: describe only road/traffic conditions in aggregate; never people or number plates. \
Use accident/stalled_vehicle/hazard only on unambiguous evidence, else clear/congestion. \
Respond JSON only: category, confidence (0-1), one-sentence description of road conditions."""

SCHEMA = {"type": "object", "properties": {
    "category": {"type": "string", "enum": ["clear", "congestion", "accident", "stalled_vehicle", "hazard", "obscured"]},
    "confidence": {"type": "number"}, "description": {"type": "string"}},
    "required": ["category", "confidence", "description"]}


UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


def get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def main():
    print(f"endpoint: {BASE}  model: {MODEL}")
    print("fetching a live JamCam frame from TfL...")
    cams = json.loads(get("https://api.tfl.gov.uk/Place/Type/JamCam"))
    cam = next(c for c in cams if any(
        p.get("key") == "available" and str(p.get("value")).lower() == "true"
        for p in c.get("additionalProperties", [])))
    props = {p["key"]: p["value"] for p in cam["additionalProperties"]}
    name, img_url = cam.get("commonName"), props.get("imageUrl")
    print(f"  camera: {name}\n  image: {img_url}")
    img_b64 = base64.b64encode(get(img_url)).decode()

    payload = {
        "model": MODEL, "temperature": 0, "max_tokens": 400,
        "response_format": {"type": "json_schema", "json_schema": {"name": "incident", "schema": SCHEMA}},
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": PROMPT},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}]}],
    }
    print(f"classifying via Modal endpoint (first call cold-starts the H100, up to {TIMEOUT}s)...")
    req = urllib.request.Request(f"{BASE}/chat/completions",
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json", "User-Agent": UA})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        resp = json.loads(r.read())
    dt = time.time() - t0
    content = resp["choices"][0]["message"]["content"]
    print(f"\nlatency: {dt:.1f}s")
    print(f"raw: {content}")
    try:
        print(f"parsed: {json.loads(content)}")
        print("\nVALIDATION OK ✅  — NVIDIA Nemotron-Nano-VL on Modal classified a live frame")
    except json.JSONDecodeError:
        print("(content not strict JSON — check prompt/schema handling)")


if __name__ == "__main__":
    main()
