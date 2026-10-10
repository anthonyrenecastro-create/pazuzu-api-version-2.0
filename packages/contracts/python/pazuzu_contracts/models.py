"""Core data models shared across gateway, orchestrator, stations, providers."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class StationStatus(str, Enum):
    OK = "ok"
    DEGRADED = "degraded"
    FAILED = "failed"
    SKIPPED = "skipped"


class Decision(str, Enum):
    APPROVE = "approve"
    REVISE = "revise"
    REJECT = "reject"
    QUARANTINE = "quarantine"


class Provenance(BaseModel):
    request_id: str
    correlation_id: str
    station_id: str
    station_version: str
    input_hash: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    actor: str = "system"


class Telemetry(BaseModel):
    duration_ms: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    extra: dict[str, Any] = Field(default_factory=dict)


class StationOutput(BaseModel):
    """Immutable station result. Stations never mutate shared state."""

    station_id: str
    station_version: str
    status: StationStatus = StationStatus.OK
    data: dict[str, Any] = Field(default_factory=dict)
    provenance: Provenance
    telemetry: Telemetry = Field(default_factory=Telemetry)
    warnings: list[str] = Field(default_factory=list)

    model_config = {"frozen": True}


class ExecutionContext(BaseModel):
    """Versioned, immutable snapshot handed to each station."""

    request_id: str = Field(default_factory=lambda: uuid4().hex)
    correlation_id: str = Field(default_factory=lambda: uuid4().hex)
    idempotency_key: str | None = None
    tenant_id: str = "default"
    principal: str = "anonymous"
    scopes: list[str] = Field(default_factory=list)
    prompt: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    plan_version: str = "1"
    station_outputs: dict[str, StationOutput] = Field(default_factory=dict)
    deadline_ms: int = 30_000
    cancelled: bool = False

    model_config = {"frozen": True}

    def with_output(self, output: StationOutput) -> "ExecutionContext":
        """Return a new context with one more station output (no mutation)."""
        merged = dict(self.station_outputs)
        merged[output.station_id] = output
        return self.model_copy(update={"station_outputs": merged})

    def with_cancelled(self) -> "ExecutionContext":
        return self.model_copy(update={"cancelled": True})


class ExecutionPlan(BaseModel):
    version: str = "1"
    critical_path: list[str] = Field(
        default_factory=lambda: ["s01", "s02", "s03", "s06", "s11"]
    )
    parallel_streams: list[str] = Field(
        default_factory=lambda: ["s04", "s05", "s07", "s10"]
    )
    background: list[str] = Field(default_factory=lambda: ["s08", "s12"])
    timeouts_ms: dict[str, int] = Field(default_factory=dict)
    fallbacks: dict[str, str] = Field(default_factory=dict)


class ProviderCapabilities(BaseModel):
    streaming: bool = False
    token_probabilities: bool = False
    deterministic_seed: bool = False
    reasoning_mode: bool = False
    max_context_tokens: int = 0
    notes: list[str] = Field(default_factory=list)


class MemoryRecord(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    tenant_id: str = "default"
    kind: Literal["event", "fact", "telemetry", "evaluation"] = "event"
    content: dict[str, Any] = Field(default_factory=dict)
    embedding_ref: str | None = None
    pinned: bool = False
    created_at: datetime = Field(default_factory=utcnow)
    expires_at: datetime | None = None
    version: int = 1


class QuarantineRecord(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    request_id: str
    reason_code: str
    risk_class: Literal["low", "medium", "high", "critical"] = "medium"
    payload_ref: str
    station_id: str
    status: Literal["quarantined", "under_review", "released", "destroyed"] = "quarantined"
    created_at: datetime = Field(default_factory=utcnow)
    reviewed_by: str | None = None
    history: list[dict[str, Any]] = Field(default_factory=list)


class VMCompileRequest(BaseModel):
    source: str
    dialect: str = "thaumic-1"


class VMCompileResponse(BaseModel):
    ok: bool
    ast: dict[str, Any] | None = None
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class VMSimulateRequest(BaseModel):
    ast: dict[str, Any]
    initial_state: dict[str, Any] = Field(default_factory=dict)
    max_steps: int = Field(default=1000, le=100_000)
    seed: int = 0


class VMSimulateResponse(BaseModel):
    ok: bool
    final_state: dict[str, Any] | None = None
    events: list[dict[str, Any]] = Field(default_factory=list)
    invariant_checks: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
