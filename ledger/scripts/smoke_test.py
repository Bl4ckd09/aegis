#!/usr/bin/env python3
"""Quick check that local tunnels reach the Spark's Ollama endpoint."""

import json
import sys
import urllib.error
import urllib.request

OLLAMA_URL = "http://localhost:11434"


def main() -> int:
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=10) as resp:
            data = json.load(resp)
    except urllib.error.URLError as exc:
        print(f"Cannot reach Ollama at {OLLAMA_URL}: {exc}")
        print("Run: ./scripts/connect.sh")
        return 1

    models = [m["name"] for m in data.get("models", [])]
    print(f"Ollama OK — {len(models)} model(s): {', '.join(models) or 'none'}")

    if not models:
        print("No models loaded. Pull one on the Spark: ollama pull <model>")
        return 0

    payload = json.dumps(
        {
            "model": models[0],
            "prompt": "Reply with exactly: LEDGER online",
            "stream": False,
            "think": False,
            "options": {"num_predict": 16},
        }
    ).encode()
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        result = json.load(resp)
    print(f"Inference OK — {models[0]}")
    print(result.get("response", "").strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
