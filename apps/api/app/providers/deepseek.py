"""HttpDeepSeekAdapter: real DeepSeek adapter over HTTP (OpenAI-compatible chat API)."""
from __future__ import annotations

import asyncio
import json
import os
import time
from typing import AsyncIterator

import httpx

from pazuzu_contracts import ProviderAdapter, ProviderCapabilities, ProviderRequest, ProviderResponse

from .base import ProviderNotConfigured


def _detect_capabilities(model: str) -> ProviderCapabilities:
    """Capability detection from model name.

    NOTE: reasoning_mode may not exist on all endpoints even when the model
    name suggests it — some deployments strip chain-of-thought output.
    Detection is best-effort and callers must tolerate its absence.
    """
    name = model.lower()
    reasoning = any(t in name for t in ("reasoner", "reasoning", "r1", "think"))
    return ProviderCapabilities(
        streaming=True,
        token_probabilities=False,
        deterministic_seed=True,
        reasoning_mode=reasoning,
        max_context_tokens=128000 if "128k" in name or "v3" in name else 64000,
        notes=[
            "real upstream adapter; credentials never leave the server",
            f"capabilities inferred from model name '{model}'",
            "reasoning_mode may not exist on all endpoints; tolerate its absence",
        ],
    )


class HttpDeepSeekAdapter(ProviderAdapter):
    """Real DeepSeek HTTP adapter.

    Config (env):
      PAZUZU_DEEPSEEK_API_KEY   (required; else ProviderNotConfigured)
      PAZUZU_DEEPSEEK_BASE_URL  (default https://api.deepseek.com/v1)
      PAZUZU_DEEPSEEK_MODEL     (default deepseek-chat)
      PAZUZU_DEEPSEEK_TIMEOUT_S (default 60)
      PAZUZU_DEEPSEEK_RETRIES   (default 2)
    """

    name = "deepseek"

    def __init__(self) -> None:
        api_key = os.environ.get("PAZUZU_DEEPSEEK_API_KEY", "").strip()
        if not api_key:
            raise ProviderNotConfigured(
                "HttpDeepSeekAdapter requires PAZUZU_DEEPSEEK_API_KEY to be set. "
                "Set PAZUZU_MOCK_PROVIDERS=true to use the deterministic mock instead."
            )
        self._api_key = api_key
        self._base_url = os.environ.get("PAZUZU_DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1").rstrip("/")
        self._default_model = os.environ.get("PAZUZU_DEEPSEEK_MODEL", "deepseek-chat")
        self._timeout_s = float(os.environ.get("PAZUZU_DEEPSEEK_TIMEOUT_S", "60"))
        self._retries = int(os.environ.get("PAZUZU_DEEPSEEK_RETRIES", "2"))
        self.capabilities = _detect_capabilities(self._default_model)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}

    def _payload(self, req: ProviderRequest) -> dict:
        messages = []
        if req.system:
            messages.append({"role": "system", "content": req.system})
        messages.append({"role": "user", "content": req.prompt})
        payload: dict = {
            "model": req.model or self._default_model,
            "messages": messages,
            "temperature": req.temperature,
            "top_p": req.top_p,
            "max_tokens": req.max_tokens,
        }
        if req.seed is not None:
            payload["seed"] = req.seed
        return payload

    async def generate(self, req: ProviderRequest) -> ProviderResponse:
        t0 = time.perf_counter()
        last_exc: Exception | None = None
        for attempt in range(self._retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self._timeout_s) as client:
                    resp = await client.post(
                        f"{self._base_url}/chat/completions",
                        json=self._payload(req),
                        headers=self._headers(),
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    choice = (data.get("choices") or [{}])[0]
                    text = (choice.get("message") or {}).get("content", "")
                    usage = data.get("usage") or {}
                    return ProviderResponse(
                        text=text,
                        model=data.get("model", req.model or self._default_model),
                        provider=self.name,
                        tokens_in=int(usage.get("prompt_tokens", 0)),
                        tokens_out=int(usage.get("completion_tokens", 0)),
                        latency_ms=(time.perf_counter() - t0) * 1000.0,
                        mock=False,
                    )
            except (httpx.HTTPError, httpx.TimeoutException) as exc:
                last_exc = exc
                await asyncio.sleep(min(2.0 ** attempt, 8.0))
        raise RuntimeError(f"DeepSeek request failed after {self._retries + 1} attempts: {last_exc}")

    async def stream(self, req: ProviderRequest) -> AsyncIterator[str]:
        payload = self._payload(req)
        payload["stream"] = True
        async with httpx.AsyncClient(timeout=self._timeout_s) as client:
            async with client.stream(
                "POST", f"{self._base_url}/chat/completions", json=payload, headers=self._headers()
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue
                    chunk = line[5:].strip()
                    if chunk == "[DONE]":
                        break
                    try:
                        obj = json.loads(chunk)
                        delta = ((obj.get("choices") or [{}])[0].get("delta") or {}).get("content")
                        if delta:
                            yield delta
                    except Exception:
                        continue
