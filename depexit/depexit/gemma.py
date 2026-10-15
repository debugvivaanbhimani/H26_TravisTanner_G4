"""Gemma 4 client. Everything Gemma returns is recorded as AI-GENERATED and never mixed
with observed data.

Three ways to reach Gemma 4 (set GEMMA_PROVIDER in .env):

  gemini      Google AI Studio / Gemini API        needs GEMINI_API_KEY
              default model: gemma-4-26b-a4b-it
  openrouter  OpenRouter hosted API                needs OPENROUTER_API_KEY
              default model: google/gemma-4-26b-a4b-it
  ollama      local open weights via Ollama        needs `ollama serve` running
              default model: gemma4:e4b

Override the model with GEMMA_MODEL. If GEMMA_PROVIDER is not set, the first provider
with credentials is used (openrouter, then gemini), else ollama.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time

import requests

from .util import log, now_iso, sha256_text

PROVIDERS = {
    "gemini": {
        "label": "Google AI Studio (Gemini API)",
        "endpoint": "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        "default_model": "gemma-4-26b-a4b-it",
        "key_env": "GEMINI_API_KEY",
        "terms": "Gemma Terms of Use: https://ai.google.dev/gemma/terms ; Gemini API terms: https://ai.google.dev/gemini-api/terms",
    },
    "openrouter": {
        "label": "OpenRouter (hosted API)",
        "endpoint": "https://openrouter.ai/api/v1/chat/completions",
        "default_model": "google/gemma-4-26b-a4b-it",
        "key_env": "OPENROUTER_API_KEY",
        "terms": "Gemma Terms of Use: https://ai.google.dev/gemma/terms ; OpenRouter terms: https://openrouter.ai/terms",
    },
    "ollama": {
        "label": "Ollama (local open weights)",
        "endpoint": os.environ.get("OLLAMA_URL", "http://localhost:11434") + "/api/chat",
        "default_model": "gemma4:e4b",
        "key_env": None,
        "terms": "Gemma Terms of Use: https://ai.google.dev/gemma/terms (weights run locally via Ollama)",
    },
}


class GemmaError(RuntimeError):
    pass


def _pick_provider() -> str:
    p = (os.environ.get("GEMMA_PROVIDER") or "").strip().lower()
    if p:
        if p not in PROVIDERS:
            raise GemmaError(f"GEMMA_PROVIDER must be one of {list(PROVIDERS)}")
        return p
    if os.environ.get("OPENROUTER_API_KEY"):
        return "openrouter"
    if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
        return "gemini"
    return "ollama"


class Gemma:
    def __init__(self, model: str | None = None, api_key: str | None = None):
        self.provider = _pick_provider()
        cfg = PROVIDERS[self.provider]
        raw = model or os.environ.get("GEMMA_MODEL") or cfg["default_model"]
        # GEMMA_MODEL may list several models, comma-separated: when one is rate-limited
        # the client falls back to the next one (useful for free tiers).
        self.models = [m.strip() for m in raw.split(",") if m.strip()]
        self.model = self.models[0]
        for m in self.models:
            if "gemma" not in m.lower():
                log(f"WARNING: model '{m}' does not look like a Gemma model")
        self.api_key = api_key
        if cfg["key_env"]:
            self.api_key = api_key or os.environ.get(cfg["key_env"]) or (
                os.environ.get("GOOGLE_API_KEY") if self.provider == "gemini" else None)
            if not self.api_key:
                raise GemmaError(f"{cfg['key_env']} is not set (put it in a .env file).")
        self.label = cfg["label"]
        self._endpoint_tpl = cfg["endpoint"]
        self.endpoint = self._endpoint_tpl.replace("{model}", self.model)
        self.terms = cfg["terms"]
        self.session = requests.Session()
        self.transcript: list[dict] = []   # every prompt/response, for the capsule
        # pacing: free tiers allow only a few requests per minute
        free = any(m.endswith(":free") for m in self.models)
        self.min_interval = float(os.environ.get("GEMMA_MIN_INTERVAL", "4" if free else "0"))
        self._lock = threading.Lock()
        self._last_call = 0.0
        # optional on-disk cache of AI answers (development only; flagged in the transcript)
        self.cache_dir = os.environ.get("DEPEXIT_AI_CACHE")
        if self.cache_dir:
            os.makedirs(self.cache_dir, exist_ok=True)

    def describe(self) -> dict:
        used = sorted({t["model"] for t in self.transcript if t.get("model")}) or self.models
        return {"name": ", ".join(used), "configured_models": self.models, "provider": self.label,
                "endpoint": self._endpoint_tpl, "terms": self.terms,
                "cached_responses_used": sum(1 for t in self.transcript if t.get("cached"))}

    # ------------------------------------------------------------------ #
    def _pace(self):
        if not self.min_interval:
            return
        with self._lock:
            wait = self._last_call + self.min_interval - time.time()
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.time()

    def _request(self, prompt: str, temperature: float, max_tokens: int, model: str, json_mode: bool = False):
        self._pace()
        if self.provider == "gemini":
            body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens}}
            r = self.session.post(self._endpoint_tpl.replace("{model}", model),
                                  headers={"x-goog-api-key": self.api_key}, json=body, timeout=300)
            if r.status_code != 200:
                return r, None, None
            data = r.json()
            parts = (data.get("candidates") or [{}])[0].get("content", {}).get("parts", [])
            text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
            return r, text, data.get("usageMetadata")

        if self.provider == "ollama":
            # native Ollama API: lets us raise the context window (default is too small for
            # prompts that include source files) and force well-formed JSON output
            body = {"model": model, "stream": False,
                    "messages": [{"role": "user", "content": prompt}],
                    "options": {"temperature": temperature, "num_predict": max_tokens,
                                "num_ctx": int(os.environ.get("OLLAMA_NUM_CTX", "16384"))}}
            if json_mode and not getattr(self, "_no_structured", False):
                body["format"] = "json"
            r = self.session.post(self._endpoint_tpl, json=body, timeout=1800)
            if r.status_code != 200 and "format" in body and r.status_code in (400, 500, 501) \
                    and ("structured" in r.text.lower() or "format" in r.text.lower()):
                # this model/engine has no JSON mode: remember that and ask again without it
                log("local model has no JSON mode; continuing without it (replies are still parsed as JSON)")
                self._no_structured = True
                body.pop("format")
                r = self.session.post(self._endpoint_tpl, json=body, timeout=1800)
            if r.status_code != 200:
                return r, None, None
            data = r.json()
            if data.get("error"):
                return r, None, None
            usage = {k: data.get(k) for k in ("prompt_eval_count", "eval_count", "total_duration")}
            if usage.get("prompt_eval_count") and usage["prompt_eval_count"] >= int(os.environ.get("OLLAMA_NUM_CTX", "16384")) - 50:
                log("WARNING: prompt may have been truncated by the local context window (raise OLLAMA_NUM_CTX)")
            return r, (data.get("message") or {}).get("content") or "", usage

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if self.provider == "openrouter":
            headers["X-Title"] = "DepExit"
        body = {"model": model, "temperature": temperature, "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}]}
        r = self.session.post(self._endpoint_tpl, headers=headers, json=body, timeout=300)
        if r.status_code != 200:
            return r, None, None
        data = r.json()
        if data.get("error"):
            return r, None, None
        msg = (data.get("choices") or [{}])[0].get("message", {})
        return r, msg.get("content") or "", data.get("usage")

    def _cache_path(self, prompt, temperature):
        key = sha256_text(json.dumps([self.models, temperature, prompt]))
        return os.path.join(self.cache_dir, key + ".json")

    def generate(self, prompt: str, purpose: str, temperature: float = 0.2,
                 max_tokens: int = 8192, retries: int = 8, json_mode: bool = False) -> str:
        if self.cache_dir:
            cp = self._cache_path(prompt, temperature)
            if os.path.exists(cp):
                with open(cp, encoding="utf-8") as fh:
                    entry = json.load(fh)
                self.transcript.append({**entry, "purpose": purpose, "cached": True,
                                        "cached_at": entry.get("at"), "at": now_iso()})
                log(f"(re-used saved Gemma answer for {purpose})")
                return entry["response"]
        delay, last = 5.0, None
        mi = 0
        for attempt in range(retries):
            model = self.models[mi % len(self.models)]
            t = time.time()
            try:
                r, text, usage = self._request(prompt, temperature, max_tokens, model, json_mode)
            except requests.ConnectionError as exc:
                if self.provider == "ollama":
                    raise GemmaError("Cannot reach Ollama at localhost:11434 - is the Ollama app running?") from exc
                last = str(exc)
                time.sleep(delay); delay = min(delay * 2, 60)
                continue
            except requests.RequestException as exc:
                last = str(exc)
                time.sleep(delay); delay = min(delay * 2, 60)
                continue
            if text is None:
                status = r.status_code
                if status in (429, 500, 502, 503, 504, 200):
                    last = f"HTTP {status} from {model}: {r.text[:300]}"
                    mi += 1
                    nxt = self.models[mi % len(self.models)]
                    if len(self.models) > 1 and mi % len(self.models):
                        log(f"{model} busy ({status}); switching to {nxt}")
                        continue
                    log(f"Gemma busy/rate-limited ({status}); waiting {delay:.0f}s then retrying")
                    time.sleep(delay); delay = min(delay * 2, 60)
                    continue
                raise GemmaError(f"HTTP {status}: {r.text[:500]}")
            entry = {
                "purpose": purpose, "provider": self.label, "model": model, "at": now_iso(),
                "latency_s": round(time.time() - t, 1),
                "prompt_sha256": sha256_text(prompt), "prompt_chars": len(prompt),
                "response": text, "usage": usage,
            }
            self.transcript.append(entry)
            if self.cache_dir:
                with open(self._cache_path(prompt, temperature), "w", encoding="utf-8") as fh:
                    json.dump(entry, fh)
            return text
        raise GemmaError(f"Gemma request failed after {retries} attempts: {last}")

    def generate_json(self, prompt: str, purpose: str, **kw):
        kw.setdefault("json_mode", True)
        text = self.generate(prompt + "\n\nRespond with ONLY valid JSON. No prose, no markdown fences.",
                             purpose, **kw)
        try:
            return extract_json(text)
        except ValueError:
            log(f"Gemma returned non-JSON for {purpose}; asking it to repair")
            fixed = self.generate("Convert the following into ONLY valid JSON, preserving the content:\n\n"
                                  + text, purpose + ":json_repair", temperature=0, json_mode=True)
            return extract_json(fixed)


def extract_json(text: str):
    text = (text or "").strip()
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
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
    closer = "}" if text[start] == "{" else "]"
    end = text.rfind(closer)
    if end <= start:
        raise ValueError("unterminated JSON")
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError(str(exc)) from exc
