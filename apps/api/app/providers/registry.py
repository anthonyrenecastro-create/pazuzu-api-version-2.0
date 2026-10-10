"""Provider registry: selects mock vs real adapters from environment."""
from __future__ import annotations

import os

from pazuzu_contracts import ProviderAdapter

from .base import ProviderNotConfigured
from .deepseek import HttpDeepSeekAdapter
from .grok import HttpGrokAdapter
from .mock import MockDeepSeekAdapter, MockGrokAdapter

_REGISTRY: dict[str, ProviderAdapter] | None = None


def _use_mocks() -> bool:
    return os.environ.get("PAZUZU_MOCK_PROVIDERS", "true").strip().lower() in ("1", "true", "yes")


def build_registry() -> dict[str, ProviderAdapter]:
    """Build the adapter registry.

    PAZUZU_MOCK_PROVIDERS=true (default) -> deterministic mocks for both roles.
    Otherwise real adapters are required; missing API keys raise
    ProviderNotConfigured with a clear error (never mocked silently).
    """
    global _REGISTRY
    if _REGISTRY is not None:
        return _REGISTRY

    if _use_mocks():
        _REGISTRY = {"keeper": MockGrokAdapter(), "watcher": MockDeepSeekAdapter()}
        return _REGISTRY

    missing: list[str] = []
    adapters: dict[str, ProviderAdapter] = {}
    try:
        adapters["keeper"] = HttpGrokAdapter()
    except ProviderNotConfigured as exc:
        missing.append(str(exc))
    try:
        adapters["watcher"] = HttpDeepSeekAdapter()
    except ProviderNotConfigured as exc:
        missing.append(str(exc))
    if missing:
        raise ProviderNotConfigured(
            "PAZUZU_MOCK_PROVIDERS is false but real provider configuration is incomplete:\n"
            + "\n".join(f"- {m}" for m in missing)
        )
    _REGISTRY = adapters
    return _REGISTRY


def get_adapter(role: str) -> ProviderAdapter:
    reg = build_registry()
    if role not in reg:
        raise ProviderNotConfigured(f"No adapter registered for role '{role}'")
    return reg[role]


def reset_registry() -> None:
    global _REGISTRY
    _REGISTRY = None
