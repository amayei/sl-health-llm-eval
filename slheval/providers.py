"""Model providers (standard library HTTP only) and a mock provider for pipeline tests."""
from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request

USER_AGENT = "slheval/0.1 (research evaluation harness)"
RETRY_STATUS = {408, 429, 500, 502, 503, 504}

OPENAI_COMPAT_URLS = {
    "groq": "https://api.groq.com/openai/v1/chat/completions",
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
}


class ProviderError(RuntimeError):
    pass


def _retry_after(err):
    value = err.headers.get("Retry-After") if err.headers else None
    try:
        return min(float(value), 90.0) if value else None
    except ValueError:
        return None


def _post_json(url, headers, body, timeout=90, retries=6):
    data = json.dumps(body).encode("utf-8")
    hdrs = {"Content-Type": "application/json", "User-Agent": USER_AGENT, **headers}
    last = "unknown error"
    for attempt in range(retries):
        req = urllib.request.Request(url, data=data, headers=hdrs, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as err:
            detail = err.read().decode("utf-8", "replace")[:300]
            last = f"HTTP {err.code}: {detail}"
            if err.code not in RETRY_STATUS:
                raise ProviderError(last) from err
            wait = _retry_after(err) or min(60, 2 ** attempt * 2)
        except (urllib.error.URLError, TimeoutError, ConnectionError) as err:
            last = f"network error: {err}"
            wait = min(60, 2 ** attempt * 2)
        time.sleep(wait)
    raise ProviderError(f"gave up after {retries} attempts: {last}")


class GeminiProvider:
    def __init__(self, model, api_key, max_tokens=512):
        self.model, self.api_key, self.max_tokens = model, api_key, max_tokens

    def complete(self, system, user):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        body = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"temperature": 0, "maxOutputTokens": self.max_tokens},
        }
        data = _post_json(url, {"x-goog-api-key": self.api_key}, body)
        candidates = data.get("candidates") or []
        if not candidates:
            return {"text": "", "model_returned": data.get("modelVersion"), "note": "no_candidates"}
        parts = (candidates[0].get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts)
        return {"text": text, "model_returned": data.get("modelVersion"), "note": candidates[0].get("finishReason")}


class OpenAICompatProvider:
    def __init__(self, provider, model, api_key, max_tokens=16, base_url=None):
        self.url = base_url if provider == "custom" else OPENAI_COMPAT_URLS[provider]
        self.model, self.api_key, self.max_tokens = model, api_key, max_tokens

    def complete(self, system, user):
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0,
            "max_tokens": self.max_tokens,
        }
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        data = _post_json(self.url, headers, body)
        choices = data.get("choices") or []
        if not choices:
            return {"text": "", "model_returned": data.get("model"), "note": "no_choices"}
        message = choices[0].get("message") or {}
        return {
            "text": message.get("content") or "",
            "model_returned": data.get("model"),
            "note": choices[0].get("finish_reason"),
        }


class OpenAIProvider:
    """OpenAI Chat Completions. Newer models take max_completion_tokens and may reject temperature."""

    URL = "https://api.openai.com/v1/chat/completions"

    def __init__(self, model, api_key, max_tokens=16, extra=None):
        self.model, self.api_key, self.max_tokens, self.extra = model, api_key, max_tokens, extra or {}

    def _body(self, system, user, with_temperature):
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "max_completion_tokens": self.max_tokens,
            **self.extra,
        }
        if with_temperature:
            body["temperature"] = 0
        return body

    def complete(self, system, user):
        headers = {"Authorization": f"Bearer {self.api_key}"}
        note_extra = None
        try:
            data = _post_json(self.URL, headers, self._body(system, user, True))
        except ProviderError as err:
            if "temperature" not in str(err).lower():
                raise
            data = _post_json(self.URL, headers, self._body(system, user, False))
            note_extra = "temperature_not_supported"
        choices = data.get("choices") or []
        if not choices:
            return {"text": "", "model_returned": data.get("model"), "note": "no_choices"}
        message = choices[0].get("message") or {}
        return {
            "text": message.get("content") or "",
            "model_returned": data.get("model"),
            "note": note_extra or choices[0].get("finish_reason"),
        }


class AnthropicProvider:
    """Anthropic Messages API."""

    URL = "https://api.anthropic.com/v1/messages"

    def __init__(self, model, api_key, max_tokens=16):
        self.model, self.api_key, self.max_tokens = model, api_key, max_tokens

    def _body(self, system, user, with_temperature):
        body = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        if with_temperature:
            body["temperature"] = 0
        return body

    def complete(self, system, user):
        headers = {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"}
        note_extra = None
        try:
            data = _post_json(self.URL, headers, self._body(system, user, True))
        except ProviderError as err:
            if "temperature" not in str(err).lower():
                raise
            data = _post_json(self.URL, headers, self._body(system, user, False))
            note_extra = "temperature_not_supported"
        text = "".join(b.get("text", "") for b in data.get("content") or [] if b.get("type") == "text")
        return {"text": text, "model_returned": data.get("model"), "note": note_extra or data.get("stop_reason")}


class MockProvider:
    """Pseudo-random answers. For testing the pipeline only. Never used for reported results."""

    def __init__(self, label):
        self.label = label

    def complete(self, system, user):
        digest = hashlib.sha256((self.label + user).encode("utf-8")).digest()
        return {"text": "ABCD"[digest[0] % 4], "model_returned": f"mock:{self.label}", "note": "mock"}


def make_provider(cfg, api_key):
    kind = cfg["provider"]
    max_tokens = int(cfg.get("max_tokens", 16))
    if kind == "gemini":
        return GeminiProvider(cfg["model"], api_key, max_tokens)
    if kind == "openai":
        return OpenAIProvider(cfg["model"], api_key, max_tokens, cfg.get("extra"))
    if kind == "anthropic":
        return AnthropicProvider(cfg["model"], api_key, max_tokens)
    if kind in OPENAI_COMPAT_URLS:
        return OpenAICompatProvider(kind, cfg["model"], api_key, max_tokens)
    if kind == "custom":
        base_url = cfg.get("base_url", "")
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("custom provider needs base_url starting with http:// or https://")
        return OpenAICompatProvider(kind, cfg["model"], api_key, max_tokens, base_url=base_url)
    raise ValueError(f"unknown provider: {kind}")


def runnable(cfg, env=None):
    env = os.environ if env is None else env
    return bool(env.get(cfg["api_key_env"]))


def check_models(cfgs, env=None):
    """Send one trivial request to each configured model. Returns {label: (ok, detail)}."""
    env = os.environ if env is None else env
    results = {}
    for cfg in cfgs:
        label = cfg["label"]
        if not runnable(cfg, env):
            results[label] = (False, f"no key in {cfg['api_key_env']}")
            continue
        try:
            provider = make_provider(cfg, env[cfg["api_key_env"]])
            out = provider.complete("Reply with the single letter A.", "Reply with A.")
            results[label] = (True, f"returned model: {out.get('model_returned')}")
        except Exception as err:  # report any failure and keep checking the others
            results[label] = (False, str(err)[:200])
    return results


def list_gemini_models(api_key):
    """Return the Gemini model ids that support generateContent for this key."""
    import json
    import urllib.request
    names = []
    token = ""
    while True:
        url = "https://generativelanguage.googleapis.com/v1beta/models?pageSize=200" + (f"&pageToken={token}" if token else "")
        req = urllib.request.Request(url, headers={"x-goog-api-key": api_key})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        for m in data.get("models", []):
            if "generateContent" in m.get("supportedGenerationMethods", []):
                names.append(m["name"].removeprefix("models/"))
        token = data.get("nextPageToken", "")
        if not token:
            return sorted(names)


def list_provider_models(provider, api_key):
    """Model ids a key can see, for providers with a models endpoint."""
    import json
    import urllib.request
    specs = {
        "openai": ("https://api.openai.com/v1/models", {"Authorization": f"Bearer {api_key}"}),
        "groq": ("https://api.groq.com/openai/v1/models", {"Authorization": f"Bearer {api_key}"}),
        "openrouter": ("https://openrouter.ai/api/v1/models", {}),
        "anthropic": ("https://api.anthropic.com/v1/models?limit=100", {"x-api-key": api_key, "anthropic-version": "2023-06-01"}),
    }
    if provider == "gemini":
        return list_gemini_models(api_key)
    url, headers = specs[provider]
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **headers})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return sorted(m["id"] for m in data.get("data", []))
