"""Gemma 4 client via the Gemini API (Google AI Studio). Everything Gemma
returns is recorded as AI-GENERATED and never mixed with observed data.

Env vars:
  GEMINI_API_KEY   your Google AI Studio key (required)
  GEMMA_MODEL      default: gemma-4-31b-it
"""
from __future__ import annotations

import json
import os
import re
import time

import requests

from .util import log, now_iso, sha256_text

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_MODEL = "gemma-4-31b-it"


class GemmaError(RuntimeError):
    pass


class Gemma:
    def __init__(self, model: str | None = None, api_key: str | None = None):
        self.model = model or os.environ.get("GEMMA_MODEL", DEFAULT_MODEL)
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not self.api_key:
            raise GemmaError("GEMINI_API_KEY is not set (put it in a .env file).")
        self.session = requests.Session()
        self.transcript: list[dict] = []   # every prompt/response, for the capsule

    def generate(self, prompt: str, purpose: str, temperature: float = 0.2,
                 max_tokens: int = 8192, retries: int = 5) -> str:
        body = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
        }
        url = ENDPOINT.format(model=self.model)
        delay = 4.0
        last = None
        for attempt in range(retries):
            t = time.time()
            try:
                r = self.session.post(url, params={"key": self.api_key}, json=body, timeout=300)
            except requests.RequestException as exc:
                last = str(exc)
                time.sleep(delay); delay *= 2
                continue
            if r.status_code in (429, 500, 502, 503, 504):
                last = f"HTTP {r.status_code}: {r.text[:300]}"
                log(f"Gemma busy ({r.status_code}); retrying in {delay:.0f}s")
                time.sleep(delay); delay *= 2
                continue
            if r.status_code != 200:
                raise GemmaError(f"HTTP {r.status_code}: {r.text[:500]}")
            data = r.json()
            parts = (data.get("candidates") or [{}])[0].get("content", {}).get("parts", [])
            text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
            self.transcript.append({
                "purpose": purpose, "model": self.model, "at": now_iso(),
                "latency_s": round(time.time() - t, 1),
                "prompt_sha256": sha256_text(prompt), "prompt_chars": len(prompt),
                "response": text, "usage": data.get("usageMetadata"),
            })
            return text
        raise GemmaError(f"Gemma request failed after {retries} attempts: {last}")

    def generate_json(self, prompt: str, purpose: str, **kw):
        text = self.generate(prompt + "\n\nRespond with ONLY valid JSON. No prose, no markdown fences.",
                             purpose, **kw)
        try:
            return extract_json(text)
        except ValueError:
            log(f"Gemma returned non-JSON for {purpose}; asking it to repair")
            fixed = self.generate("Convert the following into ONLY valid JSON, preserving the content:\n\n"
                                  + text, purpose + ":json_repair", temperature=0)
            return extract_json(fixed)


def extract_json(text: str):
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if m:
        text = m.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    starts = [i for i in (text.find("{"), text.find("[")) if i >= 0]
    if not starts:
        raise ValueError("no JSON found")
    start = min(starts)
    opener = text[start]
    closer = "}" if opener == "{" else "]"
    end = text.rfind(closer)
    if end <= start:
        raise ValueError("unterminated JSON")
    return json.loads(text[start:end + 1])
