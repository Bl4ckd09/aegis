"""LLM client — OpenAI-compatible (DGX Spark) with Ollama fallback.
Supports both blocking chat() and streaming stream_chat() generator.
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Generator

# DGX Spark endpoint (OpenAI-compatible)
DGX_URL   = os.environ.get("DGX_URL",   "http://10.18.216.24:30000")
DGX_MODEL = os.environ.get("DGX_MODEL", "nemotron")

# Ollama fallback (local laptop)
OLLAMA_URL   = os.environ.get("OLLAMA_URL",   "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2")

_SYSTEM = "You are a concise grant application specialist for UK small businesses. No preamble, no markdown headers, just the content asked for."


def _messages(prompt: str, system: str | None) -> list:
    msgs = [{"role": "system", "content": system or _SYSTEM}]
    msgs.append({"role": "user", "content": prompt})
    return msgs


def _openai_chat(prompt: str, *, base_url: str, model: str, system: str | None) -> str:
    payload = json.dumps({
        "model":       model,
        "messages":    _messages(prompt, system),
        "max_tokens":  4096,
        "temperature": 0.1,
    }).encode()
    req = urllib.request.Request(
        f"{base_url}/v1/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        data = json.load(resp)
    return data["choices"][0]["message"]["content"].strip()


def _openai_stream(prompt: str, *, base_url: str, model: str, system: str | None) -> Generator[str, None, None]:
    """Yield text chunks as they arrive via SSE stream."""
    payload = json.dumps({
        "model":       model,
        "messages":    _messages(prompt, system),
        "max_tokens":  4096,
        "temperature": 0.1,
        "stream":      True,
    }).encode()
    req = urllib.request.Request(
        f"{base_url}/v1/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        for raw_line in resp:
            line = raw_line.decode("utf-8").strip()
            if not line.startswith("data:"):
                continue
            data_str = line[5:].strip()
            if data_str == "[DONE]":
                break
            try:
                chunk = json.loads(data_str)
                delta = chunk["choices"][0].get("delta", {})
                text = delta.get("content") or ""
                if text:
                    yield text
            except (json.JSONDecodeError, KeyError, IndexError):
                continue


def _ollama_stream(prompt: str, *, model: str, system: str | None) -> Generator[str, None, None]:
    payload = json.dumps({
        "model":    model,
        "messages": _messages(prompt, system),
        "stream":   True,
        "options":  {"temperature": 0.1, "num_predict": 600},
    }).encode()
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        for raw_line in resp:
            try:
                chunk = json.loads(raw_line.decode("utf-8"))
                text = chunk.get("message", {}).get("content", "")
                if text:
                    yield text
                if chunk.get("done"):
                    break
            except (json.JSONDecodeError, KeyError):
                continue


def chat(prompt: str, *, system: str | None = None) -> str:
    """Blocking: try DGX first, fall back to Ollama."""
    try:
        return _openai_chat(prompt, base_url=DGX_URL, model=DGX_MODEL, system=system)
    except Exception:
        pass
    return _ollama_chat_blocking(prompt, model=OLLAMA_MODEL, system=system)


def stream_chat(prompt: str, *, system: str | None = None) -> Generator[str, None, None]:
    """Streaming: yields text chunks as they arrive. Falls back to Ollama stream."""
    try:
        # Test connection first with a tiny non-streaming call
        yield from _openai_stream(prompt, base_url=DGX_URL, model=DGX_MODEL, system=system)
        return
    except Exception:
        pass
    yield from _ollama_stream(prompt, model=OLLAMA_MODEL, system=system)


def _ollama_chat_blocking(prompt: str, *, model: str, system: str | None) -> str:
    payload = json.dumps({
        "model":    model,
        "messages": _messages(prompt, system),
        "stream":   False,
        "options":  {"temperature": 0.1, "num_predict": 600},
    }).encode()
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.load(resp)
    return data.get("message", {}).get("content", "").strip()
