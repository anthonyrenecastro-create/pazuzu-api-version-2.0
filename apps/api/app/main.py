"""PAZUZU-API v2.0 — FastAPI app factory.

Every route returns real computed results from the orchestrator/stations.
No static placeholder responses anywhere in this module.
"""
from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field

from pazuzu_contracts import (
    Decision,
    ExecutionContext,
    ExecutionPlan,
    MemoryRecord,
    ProviderRequest,
    VMCompileRequest,
    VMSimulateRequest,
)

from . import vm as _vm
from .gateway import (
    AuditMiddleware,
    CorrelationIdMiddleware,
    DeadlineMiddleware,
    IdempotentRoute,
    Principal,
    get_principal,
    rate_limit_dep,
    require_admin,
    require_scopes,
)
from .memory import MemoryStore
from .orchestrator import STATION_REGISTRY, ExecutionEngine, get_execution
from .orchestrator.engine import ExecutionResult
from .providers import ProviderNotConfigured, build_registry, get_adapter
from .quarantine import QuarantineStore, ReviewActionError
from .telemetry import audit_summary, render_prometheus

log = logging.getLogger("pazuzu.api")


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1)
    parameters: dict[str, Any] = Field(default_factory=dict)
    seed: int | None = None
    plan: ExecutionPlan | None = None
    deadline_ms: int | None = Field(default=None, gt=0, le=300_000)


class VerifyRequest(BaseModel):
    text: str = Field(min_length=1)
    seed: int | None = None


class SwarmRequest(BaseModel):
    prompt: str = Field(min_length=1)
    n: int = Field(default=3, ge=2, le=8)
    seed: int | None = None


class MemoryCreateRequest(BaseModel):
    kind: Literal["event", "fact", "telemetry", "evaluation"] = "event"
    content: dict[str, Any] = Field(default_factory=dict)
    embedding_ref: str | None = None
    pinned: bool = False
    expires_at: str | None = None  # ISO-8601


class QuarantineReviewRequest(BaseModel):
    action: Literal["start_review", "release", "destroy"]


class ReplayRequest(BaseModel):
    execution_id: str


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Fail fast on provider misconfiguration (never mock silently).
        try:
            registry = build_registry()
        except ProviderNotConfigured as exc:
            log.error("provider registry failed: %s", exc)
            raise
        app.state.keeper = registry["keeper"]
        app.state.watcher = registry["watcher"]
        app.state.quarantine_store = QuarantineStore()
        app.state.memory_store = MemoryStore()
        app.state.memory_store.start_reaper()
        app.state.engine = ExecutionEngine(
            keeper=app.state.keeper,
            watcher=app.state.watcher,
            quarantine_store=app.state.quarantine_store,
            memory_store=app.state.memory_store,
        )
        log.info("PAZUZU-API v2.0 ready (keeper=%s watcher=%s)",
                 registry["keeper"].name, registry["watcher"].name)
        yield
        await app.state.memory_store.stop_reaper()

    app = FastAPI(title="PAZUZU-API", version="2.0.0", lifespan=lifespan)

    app.add_middleware(AuditMiddleware)
    app.add_middleware(DeadlineMiddleware)
    app.add_middleware(CorrelationIdMiddleware)

    # -- health (public) ----------------------------------------------------
    @app.get("/health/live")
    async def health_live():
        return {"status": "live", "service": "pazuzu-api", "version": "2.0.0"}

    @app.get("/health/ready")
    async def health_ready():
        try:
            registry = build_registry()
            providers = {role: a.describe() for role, a in registry.items()}
            return {"status": "ready", "providers": providers}
        except ProviderNotConfigured as exc:
            return JSONResponse(status_code=503,
                                content={"status": "not_ready", "detail": str(exc)})

    # -- /v2 routers --------------------------------------------------------
    v2 = APIRouter(prefix="/v2", route_class=IdempotentRoute)
    v2_stream = APIRouter(prefix="/v2")  # SSE: no idempotency wrapper

    # Auth + tenant context for every /v2 route.
    async def authed(request: Request,
                     principal: Principal = Depends(get_principal),
                     _rl: Principal = Depends(rate_limit_dep)) -> Principal:
        request.state.principal_sub = principal.sub
        request.state.principal_tenant = principal.tenant_id
        return principal

    async def authed_admin(request: Request,
                           principal: Principal = Depends(require_admin),
                           _rl: Principal = Depends(rate_limit_dep)) -> Principal:
        request.state.principal_sub = principal.sub
        request.state.principal_tenant = principal.tenant_id
        return principal

    def engine_of(request: Request) -> ExecutionEngine:
        return request.app.state.engine

    def build_ctx(request: Request, principal: Principal, body: GenerateRequest) -> ExecutionContext:
        params = dict(body.parameters)
        if body.seed is not None:
            params["seed"] = body.seed
        return ExecutionContext(
            request_id=uuid4().hex,
            correlation_id=getattr(request.state, "correlation_id", uuid4().hex),
            tenant_id=principal.tenant_id,
            principal=principal.sub,
            scopes=list(principal.scopes),
            prompt=body.prompt,
            parameters=params,
            deadline_ms=body.deadline_ms or 30_000,
        )

    def result_payload(result: ExecutionResult) -> dict[str, Any]:
        return {
            "execution_id": result.execution_id,
            "request_id": result.request_id,
            "correlation_id": result.correlation_id,
            "decision": result.decision.value,
            "status": result.status,
            "text": result.text,
            "revised_text": result.revised_text,
            "quarantine_record_id": result.quarantine_record_id,
            "revision_notes": result.revision_notes,
            "reconcile": result.reconcile_report,
            "scheduled_background": result.scheduled_background,
            "telemetry": result.telemetry_summary,
            "stations": [
                {"station_id": o.station_id, "status": o.status.value,
                 "data": o.data, "warnings": o.warnings,
                 "duration_ms": round(o.telemetry.duration_ms, 3)}
                for o in result.station_outputs
            ],
            "replay_of": result.replay_of,
        }

    # -- generation ---------------------------------------------------------
    @v2.post("/generate", dependencies=[Depends(require_scopes("v2:write"))])
    async def generate(request: Request, body: GenerateRequest,
                       principal: Principal = Depends(authed)):
        ctx = build_ctx(request, principal, body)
        result = await engine_of(request).execute(ctx, body.plan)
        return result_payload(result)

    # -- streaming (SSE) ----------------------------------------------------
    # Fail-closed event sequence: the raw candidate is emitted ONLY when the
    # final decision is approve. Revisions carry s03's remediated text;
    # withheld/rejected/error never carry candidate text.
    @v2_stream.post("/stream", dependencies=[Depends(require_scopes("v2:write"))])
    async def stream(request: Request, body: GenerateRequest,
                     principal: Principal = Depends(authed)):
        ctx = build_ctx(request, principal, body)
        try:
            result = await engine_of(request).execute(ctx, body.plan)
        except Exception as exc:
            async def error_gen():
                yield f"event: error\ndata: {json.dumps({'detail': str(exc)})}\n\n"
            return StreamingResponse(error_gen(), media_type="text/event-stream")

        decision_event = {
            Decision.APPROVE: "approved",
            Decision.REVISE: "revised",
            Decision.REJECT: "rejected",
            Decision.QUARANTINE: "withheld",
        }[result.decision]

        async def event_gen():
            if result.decision == Decision.APPROVE:
                yield f"event: candidate\ndata: {json.dumps({'text': result.text})}\n\n"
                yield f"event: approved\ndata: {json.dumps({'text': result.text})}\n\n"
            elif result.decision == Decision.REVISE:
                yield (f"event: revised\ndata: "
                       f"{json.dumps({'revised_text': result.revised_text, 'revision_notes': result.revision_notes})}\n\n")
            elif result.decision == Decision.REJECT:
                yield (f"event: rejected\ndata: "
                       f"{json.dumps({'reasons': result.revision_notes})}\n\n")
            else:
                yield (f"event: withheld\ndata: "
                       f"{json.dumps({'quarantine_record_id': result.quarantine_record_id, 'reasons': result.revision_notes})}\n\n")
            yield (f"event: completed\ndata: "
                   f"{json.dumps({'execution_id': result.execution_id, 'status': result.status, 'decision': result.decision.value})}\n\n")

        return StreamingResponse(event_gen(), media_type="text/event-stream",
                                 headers={"X-Decision-Event": decision_event})

    # -- verify -------------------------------------------------------------
    # Runs the real s03 Dual Ward gate as a standalone audit of the text.
    @v2.post("/verify", dependencies=[Depends(require_scopes("v2:write"))])
    async def verify(request: Request, body: VerifyRequest,
                     principal: Principal = Depends(authed)):
        engine = engine_of(request)
        station = engine._instantiate("s03")
        ctx = ExecutionContext(
            request_id=uuid4().hex,
            correlation_id=getattr(request.state, "correlation_id", uuid4().hex),
            tenant_id=principal.tenant_id,
            principal=principal.sub,
            prompt=body.text,
            parameters={"candidate": body.text,
                        "seed": body.seed} if body.seed is not None else {"candidate": body.text},
        )
        out = await station.timed_run(ctx)
        return {
            "decision": out.data.get("decision"),
            "axes": out.data.get("axes"),
            "min_axis": out.data.get("min_axis"),
            "threshold": out.data.get("threshold"),
            "reasons": out.warnings,
            "revised_candidate": out.data.get("revised_candidate"),
            "station": {"id": out.station_id, "version": out.station_version,
                        "status": out.status.value},
        }

    # -- swarm --------------------------------------------------------------
    # Runs the real s04 Swarm station over keeper-generated candidates.
    @v2.post("/swarm", dependencies=[Depends(require_scopes("v2:write"))])
    async def swarm(request: Request, body: SwarmRequest,
                    principal: Principal = Depends(authed)):
        import hashlib as _hashlib
        engine = engine_of(request)
        keeper = request.app.state.keeper
        seed = (body.seed if body.seed is not None
                else int.from_bytes(_hashlib.sha256(body.prompt.encode()).digest()[:4], "big"))
        candidates = []
        for i in range(body.n):
            resp = await keeper.generate(ProviderRequest(
                prompt=body.prompt, model="keeper", max_tokens=256, seed=seed + i))
            candidates.append(resp.text)
        station = engine._instantiate("s04")
        ctx = ExecutionContext(
            request_id=uuid4().hex,
            correlation_id=getattr(request.state, "correlation_id", uuid4().hex),
            tenant_id=principal.tenant_id,
            principal=principal.sub,
            prompt=body.prompt,
            parameters={"candidates": candidates},
        )
        out = await station.timed_run(ctx)
        return {
            "winner": out.data.get("winner"),
            "consensus_confidence": out.data.get("consensus_confidence"),
            "dispersion": out.data.get("dispersion"),
            "outliers": out.data.get("outliers"),
            "n_candidates": out.data.get("n_candidates"),
            "seed": seed,
            "station": {"id": out.station_id, "version": out.station_version,
                        "status": out.status.value},
        }

    # -- stations -----------------------------------------------------------
    @v2.get("/stations", dependencies=[Depends(require_scopes("v2:read"))])
    async def list_stations(request: Request, principal: Principal = Depends(authed)):
        engine = engine_of(request)
        return {"stations": [engine.station_manifest(sid) for sid in sorted(STATION_REGISTRY)]}

    @v2.get("/stations/{station_id}", dependencies=[Depends(require_scopes("v2:read"))])
    async def get_station(request: Request, station_id: str,
                          principal: Principal = Depends(authed)):
        if station_id not in STATION_REGISTRY:
            raise HTTPException(status_code=404, detail=f"unknown station '{station_id}'")
        return engine_of(request).station_manifest(station_id)

    # -- pipeline -----------------------------------------------------------
    @v2.get("/pipeline", dependencies=[Depends(require_scopes("v2:read"))])
    async def get_pipeline(principal: Principal = Depends(authed)):
        return ExecutionPlan().model_dump()

    @v2.post("/pipeline/validate")
    async def validate_pipeline(plan: ExecutionPlan, principal: Principal = Depends(authed_admin)):
        errors: list[str] = []
        warnings: list[str] = []
        known = set(STATION_REGISTRY)
        groups = {"critical_path": plan.critical_path,
                  "parallel_streams": plan.parallel_streams, "background": plan.background}
        seen: dict[str, str] = {}
        for group, ids in groups.items():
            for sid in ids:
                if sid not in known:
                    errors.append(f"{group}: unknown station '{sid}'")
                if sid in seen:
                    errors.append(f"station '{sid}' appears in both {seen[sid]} and {group}")
                seen[sid] = group
        if not plan.critical_path:
            errors.append("critical_path must not be empty")
        if "s03" not in plan.critical_path:
            errors.append("critical_path must include s03 (the fail-closed gate)")
        for sid, ms in plan.timeouts_ms.items():
            if sid not in known:
                errors.append(f"timeouts_ms: unknown station '{sid}'")
            if ms <= 0:
                errors.append(f"timeouts_ms[{sid}]: must be positive")
        for sid, fb in plan.fallbacks.items():
            if sid not in known or fb not in known:
                errors.append(f"fallbacks: unknown station in '{sid}' -> '{fb}'")
        unused = known - set(seen)
        if unused:
            warnings.append(f"stations not in any group: {sorted(unused)}")
        return {"valid": not errors, "errors": errors, "warnings": warnings,
                "plan": plan.model_dump()}

    # -- memory -------------------------------------------------------------
    @v2.post("/memory", dependencies=[Depends(require_scopes("v2:write"))])
    async def memory_create(request: Request, body: MemoryCreateRequest,
                            principal: Principal = Depends(authed)):
        from datetime import datetime
        expires = None
        if body.expires_at:
            try:
                expires = datetime.fromisoformat(body.expires_at)
            except ValueError:
                raise HTTPException(status_code=422, detail="expires_at must be ISO-8601")
        rec = MemoryRecord(tenant_id=principal.tenant_id, kind=body.kind,
                           content=body.content, embedding_ref=body.embedding_ref,
                           pinned=body.pinned, expires_at=expires)
        await request.app.state.memory_store.create(rec)
        return rec.model_dump(mode="json")

    @v2.get("/memory", dependencies=[Depends(require_scopes("v2:read"))])
    async def memory_list(request: Request, kind: str | None = Query(default=None),
                          principal: Principal = Depends(authed)):
        records = await request.app.state.memory_store.list(principal.tenant_id, kind=kind)
        return {"records": [r.model_dump(mode="json") for r in records],
                "count": len(records)}

    @v2.delete("/memory/{record_id}", dependencies=[Depends(require_scopes("v2:write"))])
    async def memory_delete(request: Request, record_id: str,
                            principal: Principal = Depends(authed)):
        ok = await request.app.state.memory_store.delete(principal.tenant_id, record_id)
        if not ok:
            raise HTTPException(status_code=404, detail=f"memory record '{record_id}' not found")
        return {"deleted": record_id}

    # -- executions / replay / provenance -----------------------------------
    @v2.get("/executions/{execution_id}", dependencies=[Depends(require_scopes("v2:read"))])
    async def get_execution_route(request: Request, execution_id: str,
                                  principal: Principal = Depends(authed)):
        entry = await get_execution(execution_id)
        if entry is None:
            raise HTTPException(status_code=404, detail=f"execution '{execution_id}' not found")
        return result_payload(entry["result"])

    @v2.post("/replay", dependencies=[Depends(require_scopes("v2:write"))])
    async def replay(request: Request, body: ReplayRequest,
                     principal: Principal = Depends(authed)):
        entry = await get_execution(body.execution_id)
        if entry is None:
            raise HTTPException(status_code=404,
                                detail=f"execution '{body.execution_id}' not found")
        old_ctx: ExecutionContext = entry["ctx"]
        new_ctx = ExecutionContext(
            request_id=uuid4().hex,
            correlation_id=getattr(request.state, "correlation_id", uuid4().hex),
            tenant_id=principal.tenant_id,
            principal=principal.sub,
            scopes=list(principal.scopes),
            prompt=old_ctx.prompt,
            parameters=dict(old_ctx.parameters),
            plan_version=old_ctx.plan_version,
            deadline_ms=old_ctx.deadline_ms,
        )
        result = await engine_of(request).execute(new_ctx, replay_of=body.execution_id)
        return result_payload(result)

    @v2.get("/provenance/{execution_id}", dependencies=[Depends(require_scopes("v2:read"))])
    async def provenance(request: Request, execution_id: str,
                         principal: Principal = Depends(authed)):
        entry = await get_execution(execution_id)
        if entry is None:
            raise HTTPException(status_code=404, detail=f"execution '{execution_id}' not found")
        result: ExecutionResult = entry["result"]
        return {
            "execution_id": execution_id,
            "provenance": [o.provenance.model_dump(mode="json") for o in result.station_outputs],
        }

    # -- quarantine (admin) ---------------------------------------------------
    @v2.get("/quarantine")
    async def quarantine_list(request: Request,
                              status_q: str | None = Query(default=None, alias="status"),
                              principal: Principal = Depends(authed_admin)):
        records = await request.app.state.quarantine_store.list(status=status_q)
        return {"records": [r.model_dump(mode="json") for r in records],
                "count": len(records)}

    @v2.post("/quarantine/{record_id}/review")
    async def quarantine_review(request: Request, record_id: str,
                                body: QuarantineReviewRequest,
                                principal: Principal = Depends(authed_admin)):
        try:
            updated = await request.app.state.quarantine_store.review(
                record_id, body.action, reviewer=principal.sub)
        except ReviewActionError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        return updated.model_dump(mode="json")

    # -- VM -------------------------------------------------------------------
    @v2.post("/vm/compile", dependencies=[Depends(require_scopes("v2:write"))])
    async def vm_compile(body: VMCompileRequest, principal: Principal = Depends(authed)):
        return _vm.compile_source(body).model_dump()

    @v2.post("/vm/simulate", dependencies=[Depends(require_scopes("v2:write"))])
    async def vm_simulate(body: VMSimulateRequest, principal: Principal = Depends(authed)):
        return _vm.simulate_ast(body).model_dump()

    # -- formalisms (admin, raw) ----------------------------------------------
    @v2.get("/formalisms")
    async def formalisms(principal: Principal = Depends(authed_admin)):
        return {"formalisms": _vm.formalisms(), "count": len(_vm.formalisms())}

    # -- metrics / audit --------------------------------------------------------
    @v2.get("/metrics", dependencies=[Depends(require_scopes("v2:read"))])
    async def metrics(principal: Principal = Depends(authed)):
        return PlainTextResponse(render_prometheus(), media_type="text/plain; version=0.0.4")

    @v2.get("/audit", dependencies=[Depends(require_scopes("v2:read"))])
    async def audit(principal: Principal = Depends(authed)):
        return audit_summary()

    app.include_router(v2)
    app.include_router(v2_stream)
    return app


app = create_app()
