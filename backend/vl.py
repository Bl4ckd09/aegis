"""Vision-language + text inference clients.

Supports two serving backends so we can run on llama.cpp (preferred) or Ollama:
  - "ollama":  native /api/chat (images[] + format schema)
  - "openai":  /v1/chat/completions (image_url data URI + json_schema) — llama.cpp, vLLM, NIM

Roles:
  - classify_frame():    detector VLM  (config.VL_BACKEND)
  - generate_briefing(): operator briefing, prefers NVIDIA Nemotron on llama.cpp
                         (config.BRIEFING_BACKEND), with a fallback to the other backend.

Privacy is enforced in the prompt: describe road/traffic conditions in aggregate only —
never people, never number plates, never re-identify a vehicle.
"""
from __future__ import annotations

import base64
import json
from typing import Optional

import httpx

from . import config

# --- Anonymized, conservative classification prompt ---------------------------
CLASSIFY_PROMPT = """You are a cautious traffic-camera incident classifier for a road control room. \
Classify the OVERALL road condition in this low-resolution CCTV frame into exactly ONE category.

STRICT PRIVACY RULES (mandatory):
- Describe ONLY road and traffic conditions and vehicles in aggregate.
- Do NOT describe, identify, or count people or pedestrians.
- Do NOT read number plates or identify or track any specific vehicle.

Categories:
- clear: traffic is flowing freely with no issue
- congestion: traffic is visibly heavy, dense, slow-moving, queuing, or stationary in the lanes
- accident: vehicles are UNMISTAKABLY collided, crashed, or overturned
- stalled_vehicle: a single vehicle is clearly stopped/broken down in a live lane or hard shoulder
- hazard: clear debris, flooding, smoke or fire on the carriageway
- obscured: image is black, frozen, or so heavily blurred/corrupted that the road is unreadable

DECISION RULES:
- Distinguish clear vs congestion by how the traffic is MOVING: free-flowing = clear;
  heavy / dense / slow / queuing / stationary = congestion.
- Use "accident", "stalled_vehicle" or "hazard" ONLY when the evidence is obvious and
  unambiguous. If you are unsure whether one of these applies, do NOT use it — choose
  "congestion" or "clear" instead.
- A large vehicle (bus, lorry, coach) driving, turning, or passing close to the camera is
  NORMAL — it is NOT an accident or a stalled vehicle.
- Rain, glare, wet road, or darkness alone is NOT a hazard and NOT "obscured" — if the road
  is simply wet or hard to see but appears normal, judge it as clear or congestion. Use
  "obscured" only when the image itself is genuinely unusable.

Set confidence to honestly reflect certainty: ~0.9+ only when obvious, ~0.5-0.7 when ambiguous.
Respond with JSON only: category, confidence (0-1), and a one-sentence description of road conditions only."""

CLASSIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "enum": config.CATEGORIES},
        "confidence": {"type": "number"},
        "description": {"type": "string"},
    },
    "required": ["category", "confidence", "description"],
}


def _extract_json(text: str) -> Optional[dict]:
    """Parse JSON, tolerating models that wrap it in prose / code fences."""
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            return None
    return None


def _normalize(result: dict) -> Optional[dict]:
    cat = result.get("category")
    if cat not in config.CATEGORIES:
        return None
    try:
        conf = float(result.get("confidence", 0.0))
    except (TypeError, ValueError):
        conf = 0.0
    return {
        "category": cat,
        "confidence": max(0.0, min(1.0, conf)),
        "description": str(result.get("description", "")).strip(),
    }


# --- detector: classify one frame --------------------------------------------
async def _classify_ollama(client: httpx.AsyncClient, b64: str) -> Optional[dict]:
    payload = {
        "model": config.VL_MODEL, "stream": False, "think": False,
        "options": {"temperature": 0}, "format": CLASSIFY_SCHEMA,
        "messages": [{"role": "user", "content": CLASSIFY_PROMPT, "images": [b64]}],
    }
    r = await client.post(f"{config.OLLAMA_URL}/api/chat", json=payload,
                          timeout=config.VL_TIMEOUT_SECONDS)
    r.raise_for_status()
    return _extract_json(r.json().get("message", {}).get("content", ""))


async def _classify_openai(client: httpx.AsyncClient, b64: str) -> Optional[dict]:
    payload = {
        "model": config.VL_MODEL, "temperature": 0, "max_tokens": 400, "stream": False,
        "response_format": {"type": "json_schema",
                            "json_schema": {"name": "incident", "schema": CLASSIFY_SCHEMA}},
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": CLASSIFY_PROMPT},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
        ]}],
    }
    r = await client.post(f"{config.VL_OPENAI_URL}/chat/completions", json=payload,
                          timeout=config.VL_TIMEOUT_SECONDS)
    r.raise_for_status()
    return _extract_json(r.json()["choices"][0]["message"]["content"])


async def classify_frame(client: httpx.AsyncClient, image_bytes: bytes) -> Optional[dict]:
    """Classify one frame. Returns {category, confidence, description} or None on failure."""
    b64 = base64.b64encode(image_bytes).decode("ascii")
    try:
        if config.VL_BACKEND == "openai":
            result = await _classify_openai(client, b64)
        else:
            result = await _classify_ollama(client, b64)
    except Exception:
        return None
    return _normalize(result) if result else None


# --- briefing: text summary ---------------------------------------------------
def _briefing_prompt(summary_text: str) -> str:
    return (
        "You are the duty officer at a road-traffic control room. Write a concise "
        "(2-4 sentence) situational briefing for the operators based ONLY on the "
        "incident data below. Be factual and specific about categories and locations. "
        "Do not mention any people or vehicles individually. If there are no active "
        "incidents, say conditions are nominal.\n\n"
        f"INCIDENT DATA:\n{summary_text}"
    )


async def _briefing_openai(client: httpx.AsyncClient, prompt: str) -> Optional[str]:
    payload = {
        "model": config.BRIEFING_MODEL, "temperature": 0.3,
        "max_tokens": config.BRIEFING_MAX_TOKENS, "stream": False,
        "messages": [{"role": "user", "content": prompt}],
    }
    r = await client.post(f"{config.BRIEFING_URL}/chat/completions", json=payload,
                          timeout=config.VL_TIMEOUT_SECONDS)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


async def _briefing_ollama(client: httpx.AsyncClient, prompt: str) -> Optional[str]:
    payload = {
        "model": config.VL_MODEL, "stream": False, "think": False,
        "options": {"temperature": 0.3},
        "messages": [{"role": "user", "content": prompt}],
    }
    r = await client.post(f"{config.OLLAMA_URL}/api/chat", json=payload,
                          timeout=config.VL_TIMEOUT_SECONDS)
    r.raise_for_status()
    return r.json().get("message", {}).get("content", "").strip()


async def generate_briefing(client: httpx.AsyncClient, summary_text: str) -> Optional[str]:
    """Generate a control-room briefing. Prefers the configured backend, falls back."""
    prompt = _briefing_prompt(summary_text)
    primary, fallback = (
        (_briefing_openai, _briefing_ollama) if config.BRIEFING_BACKEND == "openai"
        else (_briefing_ollama, _briefing_openai)
    )
    for fn in (primary, fallback):
        try:
            text = await fn(client, prompt)
            if text:
                return text
        except Exception:
            continue
    return None
