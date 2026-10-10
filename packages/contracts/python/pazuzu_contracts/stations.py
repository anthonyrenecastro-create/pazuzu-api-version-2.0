"""Station interface contract. Every station implements this ABC."""
from __future__ import annotations

import hashlib
import json
import time
from abc import ABC, abstractmethod

from pydantic import BaseModel

from .models import ExecutionContext, Provenance, StationOutput, StationStatus, Telemetry


class StationManifest(BaseModel):
    id: str  # e.g. "s01"
    name: str  # e.g. "Chimera Gate"
    version: str  # semver of the station implementation
    critical_path: bool = False
    description: str = ""


class Station(ABC):
    """Base class for all twelve stations.

    Rules:
    - run() receives an immutable ExecutionContext snapshot.
    - run() returns an immutable StationOutput; it must not mutate ctx.
    - All outputs carry provenance and telemetry.
    - Expensive work must respect ctx.cancelled and ctx.deadline_ms.
    """

    manifest: StationManifest

    @abstractmethod
    async def run(self, ctx: ExecutionContext) -> StationOutput:
        ...

    # -- helpers ---------------------------------------------------------
    def _provenance(self, ctx: ExecutionContext, input_hash: str = "") -> Provenance:
        return Provenance(
            request_id=ctx.request_id,
            correlation_id=ctx.correlation_id,
            station_id=self.manifest.id,
            station_version=self.manifest.version,
            input_hash=input_hash or self._hash_ctx(ctx),
        )

    @staticmethod
    def _hash_ctx(ctx: ExecutionContext) -> str:
        payload = json.dumps(
            {"prompt": ctx.prompt, "params": ctx.parameters, "plan": ctx.plan_version},
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    def output(
        self,
        ctx: ExecutionContext,
        data: dict,
        status: StationStatus = StationStatus.OK,
        warnings: list[str] | None = None,
        duration_ms: float = 0.0,
        **telemetry_extra: object,
    ) -> StationOutput:
        return StationOutput(
            station_id=self.manifest.id,
            station_version=self.manifest.version,
            status=status,
            data=data,
            provenance=self._provenance(ctx),
            telemetry=Telemetry(duration_ms=duration_ms, extra=dict(telemetry_extra)),
            warnings=warnings or [],
        )

    async def timed_run(self, ctx: ExecutionContext) -> StationOutput:
        t0 = time.perf_counter()
        try:
            out = await self.run(ctx)
        except Exception as exc:  # error isolation: never let a station crash the engine
            out = self.output(
                ctx,
                {"error": f"{type(exc).__name__}: {exc}"},
                status=StationStatus.FAILED,
                warnings=["station raised; isolated by engine"],
            )
        ms = (time.perf_counter() - t0) * 1000.0
        return out.model_copy(update={"telemetry": out.telemetry.model_copy(update={"duration_ms": ms})})
