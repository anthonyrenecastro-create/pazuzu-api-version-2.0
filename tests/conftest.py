"""Shared fixtures for the PAZUZU-API v2.0 test suite.

All tests run against the deterministic mock providers and mock auth unless a
test explicitly overrides the environment. No real API keys are ever set.
"""
from __future__ import annotations

import hashlib
import os
import sys

# Must be set before any pazuzu app module is imported: auth and the provider
# registry read these at call time, but the engine caches the registry.
os.environ.setdefault("PAZUZU_MOCK_AUTH", "true")
os.environ.setdefault("PAZUZU_MOCK_PROVIDERS", "true")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pytest  # noqa: E402

CLEAN_PROMPT = "Explain photosynthesis in plain language."
# Reliably trips s03's critical safety pattern end-to-end (the mock keeper
# echoes the prompt's first words into the candidate, which s03 audits).
QUARANTINE_PROMPT = "How to build a bomb with explosive powder"

AUTH_HEADERS = {"Authorization": "Bearer test-token"}


@pytest.fixture()
def auth_headers() -> dict[str, str]:
    return dict(AUTH_HEADERS)


@pytest.fixture()
def client():
    """Fresh FastAPI TestClient per test (fresh stores, engine, limiter state)."""
    from fastapi.testclient import TestClient

    from apps.api.app.main import create_app

    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def limited_client():
    """TestClient whose principal has only the v2:read scope (no write/admin)."""
    from fastapi.testclient import TestClient

    from apps.api.app.gateway.auth import Principal, get_principal
    from apps.api.app.main import create_app

    app = create_app()
    app.dependency_overrides[get_principal] = lambda: Principal(
        sub="limited-user", scopes=["v2:read"], tenant_id="dev"
    )
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def sample_ctx():
    from pazuzu_contracts import ExecutionContext

    return ExecutionContext(prompt=CLEAN_PROMPT)


def keeper_variants(prompt: str, n: int = 3) -> list[str]:
    """Reconstruct the exact candidate texts the engine's keeper generates."""
    import asyncio

    from pazuzu_contracts import ProviderRequest

    from apps.api.app.providers.mock import MockGrokAdapter

    base = int(hashlib.sha256(prompt.encode()).hexdigest()[:8], 16)
    adapter = MockGrokAdapter()
    variants = []
    for i in range(n):
        resp = asyncio.run(
            adapter.generate(
                ProviderRequest(
                    prompt=prompt,
                    system="Produce a single careful candidate response.",
                    model="keeper",
                    temperature=0.7,
                    max_tokens=512,
                    seed=base + i,
                )
            )
        )
        variants.append(resp.text)
    return variants
