"""Unit tests for provider adapters and the provider registry."""
from __future__ import annotations

import pytest
from pazuzu_contracts import ProviderRequest

from apps.api.app.providers.base import ProviderNotConfigured
from apps.api.app.providers.mock import MockDeepSeekAdapter, MockGrokAdapter


def _req(**overrides) -> ProviderRequest:
    kwargs = {"prompt": "Explain photosynthesis.", "model": "keeper", "seed": 7}
    kwargs.update(overrides)
    return ProviderRequest(**kwargs)


async def test_mock_grok_returns_mock_flag():
    resp = await MockGrokAdapter().generate(_req())
    assert resp.mock is True
    assert resp.provider == "grok"
    assert resp.text, "mock keeper must produce candidate text"


async def test_mock_grok_is_deterministic_per_seed():
    adapter = MockGrokAdapter()
    first = await adapter.generate(_req(seed=123))
    second = await adapter.generate(_req(seed=123))
    assert first.text == second.text


async def test_mock_deepseek_returns_four_axes():
    scores = MockDeepSeekAdapter().score(
        "A calm, well-structured paragraph about photosynthesis with hedging language."
    )
    assert set(scores.keys()) == {"toxicity", "contradiction", "pii", "incoherence"}
    assert all(isinstance(v, float) and 0.0 <= v <= 1.0 for v in scores.values())


async def test_mock_deepseek_labels_mock():
    resp = await MockDeepSeekAdapter().generate(_req(prompt="hello world"))
    assert resp.mock is True
    assert resp.provider == "deepseek"


def test_registry_raises_clear_error_without_keys(monkeypatch):
    """PAZUZU_MOCK_PROVIDERS=false with no API keys must raise a clear
    ProviderNotConfigured (never mock silently). No real keys are set."""
    from apps.api.app.providers import registry

    monkeypatch.setenv("PAZUZU_MOCK_PROVIDERS", "false")
    monkeypatch.delenv("PAZUZU_GROK_API_KEY", raising=False)
    monkeypatch.delenv("PAZUZU_DEEPSEEK_API_KEY", raising=False)
    registry.reset_registry()
    try:
        with pytest.raises(ProviderNotConfigured) as excinfo:
            registry.build_registry()
        message = str(excinfo.value)
        assert "PAZUZU_MOCK_PROVIDERS" in message
        assert "PAZUZU_GROK_API_KEY" in message
        assert "PAZUZU_DEEPSEEK_API_KEY" in message
    finally:
        # Leave the cache empty; the next build_registry() lazily rebuilds
        # with the (monkeypatch-restored) mock configuration.
        registry.reset_registry()


def test_registry_builds_mocks_by_default(monkeypatch):
    from apps.api.app.providers import registry

    monkeypatch.setenv("PAZUZU_MOCK_PROVIDERS", "true")
    registry.reset_registry()
    try:
        reg = registry.build_registry()
        assert set(reg) == {"keeper", "watcher"}
        assert reg["keeper"].name == "grok"
        assert reg["watcher"].name == "deepseek"
    finally:
        registry.reset_registry()
