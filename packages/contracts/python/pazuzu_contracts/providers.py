"""Provider adapter contract. Real HTTP adapters + deterministic mocks."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator

from pydantic import BaseModel, Field

from .models import ProviderCapabilities


class ProviderRequest(BaseModel):
    prompt: str
    system: str | None = None
    model: str
    temperature: float = 0.7
    top_p: float = 1.0
    max_tokens: int = 1024
    stream: bool = False
    seed: int | None = None
    metadata: dict = Field(default_factory=dict)


class ProviderResponse(BaseModel):
    text: str
    model: str
    provider: str
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: float = 0.0
    mock: bool = False  # True ONLY for deterministic mock adapters
    extra: dict = Field(default_factory=dict)


class ProviderAdapter(ABC):
    """Server-side only. Upstream credentials never leave the server."""

    name: str
    capabilities: ProviderCapabilities

    @abstractmethod
    async def generate(self, req: ProviderRequest) -> ProviderResponse:
        ...

    @abstractmethod
    def stream(self, req: ProviderRequest) -> AsyncIterator[str]:
        ...

    def describe(self) -> dict:
        return {
            "name": self.name,
            "mock": self.capabilities.notes and "mock" in " ".join(self.capabilities.notes).lower(),
            "capabilities": self.capabilities.model_dump(),
        }
