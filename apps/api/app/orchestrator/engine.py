"""ExecutionEngine: runs the 12-station pipeline over an immutable ExecutionContext.

Pipeline shape (ExecutionPlan):
  candidate prep   keeper generates N candidates -> ctx.parameters
                   ("candidate", "candidates", "segments", "text", "sample_text")
  critical path    s01 -> s02 -> s03 -> s06 -> s11   (sequential, fail-closed)
  parallel streams s04, s05, s07, s10                 (asyncio.gather + timeouts)
  background       s08, s12                          (skipped in request path, recorded as scheduled)

The S3 gate (fail-closed): NOTHING reaches the client without s03 approval.
finalize() enforces it — the s03 decision is honored whatever the station
status (ok/degraded/failed); only a MISSING or UNPARSEABLE s03 decision
fails closed to quarantine. The raw candidate is released solely on
'approve'. On 'revise' the client gets s03's own remediated text
(revised_candidate), clearly labeled — never the raw candidate.

Reconcile policy (documented): parallel stations emit per-segment directives
(keep|revise|cut), extracted from each station's NATIVE output format:
  s10: contradictions -> the involved claim indices get "cut"
  s05: drift_report.segments[i].drifted -> "revise" else "keep"
  s04: whole-text consensus -> "keep" (or "revise" on low confidence)
  s07: breath segments grouped by sentence_index -> "revise" if overlong
  (any station may also emit data["directives"] directly; those are honored)
On conflict for the same segment, deterministic precedence decides:
    s10_divergence > s05_vector > s04_swarm > s07_breath
i.e. the divergence cutter outranks the vector current, which outranks the
swarm vote, which outranks the breath divider. This matches the stations'
own documented policies (s10 supersedes s05 on the same segment).

Stations are lazy-imported from ~/workspace/pazuzu-v2/stations/ via
STATION_REGISTRY (owned by the stations agent). If a station module is missing
or fails to load, a warning is logged and a built-in fallback station runs so
the pipeline still produces real computed results end to end.
"""
from __future__ import annotations

import asyncio
import hashlib
import importlib
import json
import logging
import re
import time
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from pazuzu_contracts import (
    Decision,
    ExecutionContext,
    ExecutionPlan,
    ProviderRequest,
    Provenance,
    QuarantineRecord,
    Station,
    StationManifest,
    StationOutput,
    StationStatus,
)

from .. import telemetry as _telemetry

log = logging.getLogger("pazuzu.orchestrator")

# id -> import path + metadata. Lazy-imported; missing modules fall back.
STATION_REGISTRY: dict[str, dict[str, Any]] = {
    "s01": {"module": "stations.s01_chimera.station", "class": "S01Chimera",
            "name": "Chimera Gate", "critical": True},
    "s02": {"module": "stations.s02_sexagesimal.station", "class": "S02Sexagesimal",
            "name": "Sexagesimal Lattice", "critical": True},
    "s03": {"module": "stations.s03_dual_ward.station", "class": "S03DualWard",
            "name": "Dual Ward", "critical": True},
    "s04": {"module": "stations.s04_swarm.station", "class": "S04Swarm",
            "name": "Swarm", "critical": False},
    "s05": {"module": "stations.s05_vector_current.station", "class": "S05VectorCurrent",
            "name": "Vector Current", "critical": False},
    "s06": {"module": "stations.s06_thermodynamic_brake.station", "class": "S06ThermodynamicBrake",
            "name": "Thermodynamic Brake", "critical": True},
    "s07": {"module": "stations.s07_breath_divider.station", "class": "S07BreathDivider",
            "name": "Breath Divider", "critical": False},
    "s08": {"module": "stations.s08_living_memory.station", "class": "S08LivingMemory",
            "name": "Living Memory", "critical": False},
    "s09": {"module": "stations.s09_parallel_paths.station", "class": "S09ParallelPaths",
            "name": "Parallel Paths", "critical": False},
    "s10": {"module": "stations.s10_divergence_cut.station", "class": "S10DivergenceCut",
            "name": "Divergence Cut", "critical": False},
    "s11": {"module": "stations.s11_pattern_quarantine.station", "class": "S11PatternQuarantine",
            "name": "Pattern Quarantine", "critical": True},
    "s12": {"module": "stations.s12_bronze_reduction.station", "class": "S12BronzeReduction",
            "name": "Bronze Reduction", "critical": False},
}

# Deterministic reconcile precedence, highest first.
RECONCILE_PRECEDENCE = ["s10", "s05", "s04", "s07"]

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


def split_segments(text: str) -> list[str]:
    return [s.strip() for s in _SENT_SPLIT.split(text.strip()) if s.strip()]


# ---------------------------------------------------------------------------
# Built-in fallback stations (used when the stations agent's modules are absent)
# ---------------------------------------------------------------------------

class _FallbackBase(Station):
    keeper = None
    watcher = None
    quarantine_store = None

    def _seed(self, ctx: ExecutionContext) -> int:
        seed = ctx.parameters.get("seed")
        if seed is not None:
            return int(seed)
        return int(hashlib.sha256(ctx.prompt.encode()).hexdigest()[:8], 16)


class _S01Chimera(_FallbackBase):
    manifest = StationManifest(id="s01", name="Chimera Gate", version="0.0.0-fallback",
                               critical_path=True,
                               description="Fallback: keeper generates the candidate.")

    async def run(self, ctx: ExecutionContext) -> StationOutput:
        candidate = ctx.parameters.get("candidate")
        if candidate is None:
            req = ProviderRequest(
                prompt=ctx.prompt,
                system="You are the Chimera Gate: produce a single careful candidate response.",
                model="keeper",
                temperature=float(ctx.parameters.get("temperature", 0.7)),
                max_tokens=int(ctx.parameters.get("max_tokens", 512)),
                seed=self._seed(ctx),
            )
            resp = await self.keeper.generate(req)
            candidate = resp.text
        return self.output(ctx, {"candidate": candidate,
                                 "candidate_source": "parameters" if ctx.parameters.get("candidate") else "keeper"})


class _S02Sexagesimal(_FallbackBase):
    manifest = StationManifest(id="s02", name="Sexagesimal Lattice", version="0.0.0-fallback",
                               critical_path=True,
                               description="Fallback: segments candidate into base-60 word blocks.")

    async def run(self, ctx: ExecutionContext) -> StationOutput:
        candidate = ctx.parameters.get("candidate") or ctx.prompt
        words = candidate.split()
        segments = [" ".join(words[i:i + 60]) for i in range(0, len(words), 60)] or [candidate]
        lattice = [{"segment": i, "base60": f"{i // 60}:{i % 60:02d}"} for i in range(len(segments))]
        return self.output(ctx, {
            "segments": segments,
            "segment_count": len(segments),
            "lattice": lattice,
            "word_count": len(words),
        })


def _segments_of(ctx: ExecutionContext) -> list[str]:
    segs = ctx.parameters.get("segments")
    if segs:
        return list(segs)
    s02 = ctx.station_outputs.get("s02")
    if s02 and s02.data.get("segments"):
        return list(s02.data["segments"])
    return [ctx.prompt]


class _S03DualWard(_FallbackBase):
    manifest = StationManifest(id="s03", name="Dual Ward", version="0.0.0-fallback",
                               critical_path=True,
                               description="Fallback: watcher scores each segment; aggregate decision.")

    async def run(self, ctx: ExecutionContext) -> StationOutput:
        segments = _segments_of(ctx)
        per_segment = []
        worst: dict[str, float] = {"toxicity": 0.0, "contradiction": 0.0, "pii": 0.0, "incoherence": 0.0}
        for i, seg in enumerate(segments):
            scores = self.watcher.score(seg) if hasattr(self.watcher, "score") else {}
            per_segment.append({"segment": i, "scores": scores})
            for k in worst:
                worst[k] = max(worst[k], float(scores.get(k, 0.0)))
        decision, reasons = self.watcher.decide("\n".join(segments)) if hasattr(
            self.watcher, "decide") else ("revise", ["watcher lacks decide()"])
        _telemetry.s3_decisions_total.inc({"decision": decision})
        return self.output(ctx, {
            "decision": decision,
            "reasons": reasons,
            "per_segment": per_segment,
            "aggregate_scores": {k: round(v, 4) for k, v in worst.items()},
        })


class _S04Swarm(_FallbackBase):
    manifest = StationManifest(id="s04", name="Swarm", version="0.0.0-fallback",
                               description="Fallback: N keeper variants, watcher-scored, majority vote.")

    async def run(self, ctx: ExecutionContext) -> StationOutput:
        candidates = ctx.parameters.get("candidates")
        if not candidates:
            n = int(ctx.parameters.get("swarm_n", 3))
            seed = self._seed(ctx)
            candidates = []
            for i in range(n):
                req = ProviderRequest(prompt=ctx.prompt, model="keeper",
                                      max_tokens=256, seed=seed + i)
                resp = await self.keeper.generate(req)
                candidates.append(resp.text)
        scored = []
        for i, text in enumerate(candidates):
            score = self.watcher.score(text) if hasattr(self.watcher, "score") else {}
            scored.append({"variant": i, "text": text, "scores": score})
        best = min(range(len(scored)),
                   key=lambda i: sum(float(v) for v in scored[i]["scores"].values()))
        directives = []
        for i in range(len(_segments_of(ctx))):
            directives.append({"segment": i, "directive": "keep",
                               "reason": f"swarm medoid endorses text (variant {best})",
                               "station": "s04"})
        return self.output(ctx, {"winner": {"index": best, "text": candidates[best]},
                                 "variants": scored, "directives": directives})


class _S05VectorCurrent(_FallbackBase):
    manifest = StationManifest(id="s05", name="Vector Current", version="0.0.0-fallback",
                               description="Fallback: heuristic drift vector per segment.")

    async def run(self, ctx: ExecutionContext) -> StationOutput:
        directives = []
        drifts = []
        for i, seg in enumerate(_segments_of(ctx)):
            words = seg.split()
            long_ratio = sum(1 for w in words if len(w) > 8) / max(len(words), 1)
            drift = round(min(1.0, long_ratio * 1.6), 4)
            drifts.append(drift)
            directives.append({"segment": i,
                               "directive": "revise" if drift > 0.55 else "keep",
                               "reason": f"drift={drift}", "station": "s05"})
        return self.output(ctx, {"drift": drifts, "directives": directives})


class _S06ThermodynamicBrake(_FallbackBase):
    manifest = StationManifest(id="s06", name="Thermodynamic Brake", version="0.0.0-fallback",
                               critical_path=True,
                               description="Fallback: entropy/token budget gate.")

    async def run(self, ctx: ExecutionContext) -> StationOutput:
        candidate = ctx.parameters.get("candidate") or ctx.prompt
        budget = int(ctx.parameters.get("max_tokens", 512))
        used = len(candidate.split())
        ratio = used / max(budget, 1)
        verdict = "revise" if ratio > 1.0 else "pass"
        return self.output(ctx, {
            "verdict": verdict,
            "tokens_used": used,
            "budget": budget,
            "utilization": round(ratio, 4),
            "action": "truncate" if verdict == "revise" else "none",
        })


class _S07BreathDivider(_FallbackBase):
    manifest = StationManifest(id="s07", name="Breath Divider", version="0.0.0-fallback",
                               description="Fallback: splits candidate into breath cadences.")

    async def run(self, ctx: ExecutionContext) -> StationOutput:
        directives = []
        for i, seg in enumerate(_segments_of(ctx)):
            words = len(seg.split())
            directives.append({"segment": i,
                               "directive": "revise" if words > 90 else "keep",
                               "reason": f"breath words={words}", "station": "s07"})
        return self.output(ctx, {"directives": directives})


class _S10DivergenceCut(_FallbackBase):
    manifest = StationManifest(id="s10", name="Divergence Cut", version="0.0.0-fallback",
                               description="Fallback: cuts segments with contradiction signals.")

    async def run(self, ctx: ExecutionContext) -> StationOutput:
        directives = []
        for i, seg in enumerate(_segments_of(ctx)):
            score = self.watcher.score(seg) if hasattr(self.watcher, "score") else {}
            contra = float(score.get("contradiction", 0.0))
            directives.append({"segment": i,
                               "directive": "cut" if contra >= 0.5 else "keep",
                               "reason": f"contradiction={contra}", "station": "s10"})
        return self.output(ctx, {"directives": directives})


class _S11PatternQuarantine(_FallbackBase):
    manifest = StationManifest(id="s11", name="Pattern Quarantine", version="0.0.0-fallback",
                               critical_path=True,
                               description="Fallback: routes s03 quarantine decisions into the quarantine store.")

    async def run(self, ctx: ExecutionContext) -> StationOutput:
        qr = (ctx.parameters or {}).get("quarantine_request")
        if not qr:
            return self.output(ctx, {"action": "none",
                                     "reason": "no quarantine_request in parameters"})
        record = QuarantineRecord(
            id=qr.get("record_id") or uuid4().hex,
            request_id=ctx.request_id,
            reason_code=qr.get("reason_code", "OPERATOR_FLAG"),
            risk_class=qr.get("risk_class", "medium"),
            payload_ref=qr.get("payload_ref") or hashlib.sha256(
                qr.get("payload", "").encode()).hexdigest()[:16],
            station_id="s11",
            history=[{"event": "quarantined", "via": "fallback s11"}],
        )
        if self.quarantine_store is not None:
            await self.quarantine_store.create(record)
        return self.output(ctx, {"action": "quarantined",
                                 "quarantined": record.model_dump(mode="json"),
                                 "quarantine_record_id": record.id})


_FALLBACK_CLASSES: dict[str, type[_FallbackBase]] = {
    "s01": _S01Chimera, "s02": _S02Sexagesimal, "s03": _S03DualWard,
    "s04": _S04Swarm, "s05": _S05VectorCurrent, "s06": _S06ThermodynamicBrake,
    "s07": _S07BreathDivider, "s10": _S10DivergenceCut, "s11": _S11PatternQuarantine,
}


def _redact_sensitive(outputs: list[StationOutput], needles: list[str]) -> list[StationOutput]:
    """S3 gate: strip withheld candidate text out of station output payloads.

    The raw candidate is released solely on s03 'approve'. On 'quarantine'
    and 'reject', every occurrence of the keeper-generated candidate text
    (all swarm variants, not just the primary audited one) is replaced inside
    station output ``data`` dicts, so NOTHING reaches the client without s03
    approval. Station identities, statuses, warnings, provenance and timings
    are preserved; only the withheld text is masked. StationOutput is frozen,
    so redacted copies are built via model_copy — the engine's own outputs
    list is never mutated.
    """
    needles = sorted(
        {n for n in needles if isinstance(n, str) and n}, key=len, reverse=True
    )
    if not needles:
        return outputs
    gated: list[StationOutput] = []
    for out in outputs:
        try:
            dumped = json.dumps(out.data, default=str, ensure_ascii=False)
        except Exception:
            gated.append(out)
            continue
        scrubbed = dumped
        for needle in needles:
            if needle in scrubbed:
                scrubbed = scrubbed.replace(needle, "[REDACTED:withheld-by-s03-gate]")
        if scrubbed != dumped:
            gated.append(out.model_copy(update={"data": json.loads(scrubbed)}))
        else:
            gated.append(out)
    return gated


class ExecutionResult(BaseModel):
    execution_id: str
    request_id: str
    correlation_id: str
    decision: Decision
    status: str  # completed | revise | rejected | quarantined | error | cancelled
    text: str | None = None  # the audited candidate — present ONLY on s03 approve
    revised_text: str | None = None  # s03's own remediated text — present ONLY on revise
    candidate: str | None = None  # the raw candidate as audited (internal; for SSE)
    quarantine_record_id: str | None = None
    station_outputs: list[StationOutput] = Field(default_factory=list)
    reconcile_report: dict[str, Any] = Field(default_factory=dict)
    scheduled_background: list[str] = Field(default_factory=list)
    revision_notes: list[str] = Field(default_factory=list)
    telemetry_summary: dict[str, Any] = Field(default_factory=dict)
    replay_of: str | None = None


# Bounded in-memory execution registry (v1; Postgres migration scheduled).
_EXECUTIONS: dict[str, dict[str, Any]] = {}
_EXEC_LOCK = asyncio.Lock()
_MAX_EXECUTIONS = 500


async def _remember_execution(result: ExecutionResult, ctx: ExecutionContext) -> None:
    async with _EXEC_LOCK:
        _EXECUTIONS[result.execution_id] = {"result": result, "ctx": ctx}
        while len(_EXECUTIONS) > _MAX_EXECUTIONS:
            _EXECUTIONS.pop(next(iter(_EXECUTIONS)))


async def get_execution(execution_id: str) -> dict[str, Any] | None:
    async with _EXEC_LOCK:
        return _EXECUTIONS.get(execution_id)


async def list_executions() -> list[str]:
    async with _EXEC_LOCK:
        return list(_EXECUTIONS.keys())


class ExecutionEngine:
    def __init__(self, keeper=None, watcher=None, quarantine_store=None, memory_store=None) -> None:
        self.keeper = keeper
        self.watcher = watcher
        self.quarantine_store = quarantine_store
        self.memory_store = memory_store
        self._loaded: dict[str, type[Station]] = {}

    # -- station loading -------------------------------------------------
    def _load_station(self, sid: str) -> type[Station]:
        if sid in self._loaded:
            return self._loaded[sid]
        spec = STATION_REGISTRY.get(sid)
        cls: type[Station] | None = None
        if spec:
            try:
                module = importlib.import_module(spec["module"])
                cls = getattr(module, spec["class"])
                log.info("loaded station %s from %s", sid, spec["module"])
            except Exception as exc:
                log.warning("station %s unavailable (%s: %s); using fallback",
                            sid, type(exc).__name__, exc)
        if cls is None:
            cls = _FALLBACK_CLASSES.get(sid)
        if cls is None:
            raise RuntimeError(f"No station implementation for '{sid}'")
        self._loaded[sid] = cls
        return cls

    def station_manifest(self, sid: str) -> dict[str, Any]:
        spec = STATION_REGISTRY.get(sid, {})
        # Trigger the lazy import so the manifest reflects real availability,
        # not just instantiation history.
        try:
            loaded = self._load_station(sid)
        except RuntimeError:
            loaded = None
        loaded_real = loaded is not None and not (
            isinstance(loaded, type) and issubclass(loaded, _FallbackBase))
        fb = _FALLBACK_CLASSES.get(sid)
        version = None
        if loaded is not None:
            manifest = getattr(loaded, "manifest", None)
            version = getattr(manifest, "version", None)
        return {
            "id": sid,
            "name": spec.get("name", sid),
            "version": version or (fb.manifest.version if fb else "unknown"),
            "critical_path": bool(spec.get("critical", False)),
            "loaded_real": loaded_real,
            "source": "stations agent" if loaded_real else "built-in fallback",
        }

    def _instantiate(self, sid: str) -> Station:
        inst = self._load_station(sid)()
        # Inject engine-owned dependencies into fallback stations only.
        if isinstance(inst, _FallbackBase):
            inst.keeper = self.keeper
            inst.watcher = self.watcher
            inst.quarantine_store = self.quarantine_store
        return inst

    # -- candidate preparation -------------------------------------------
    def _seed_for(self, ctx: ExecutionContext, salt: int = 0) -> int:
        seed = ctx.parameters.get("seed")
        if seed is not None:
            return int(seed) + salt
        return int(hashlib.sha256(ctx.prompt.encode()).hexdigest()[:8], 16) + salt

    async def _prepare_candidate(self, ctx: ExecutionContext) -> ExecutionContext:
        """Generate keeper candidates and align station inputs.

        Sets ctx.parameters: candidate (primary, audited by s03),
        candidates (swarm variants for s04), segments (shared sentence
        segmentation for s05/s07/s10), text + sample_text (s06/s07/s10).
        Caller-supplied values are respected, never overwritten.
        """
        if self.keeper is None:
            raise RuntimeError("ExecutionEngine has no keeper adapter")
        params = dict(ctx.parameters)
        if "candidate" not in params or "candidates" not in params:
            n = max(2, int(params.get("swarm_n", 3)))
            variants: list[str] = []
            for i in range(n):
                resp = await self.keeper.generate(ProviderRequest(
                    prompt=ctx.prompt,
                    system="Produce a single careful candidate response.",
                    model="keeper",
                    temperature=float(params.get("temperature", 0.7)),
                    max_tokens=int(params.get("max_tokens", 512)),
                    seed=self._seed_for(ctx, salt=i),
                ))
                variants.append(resp.text)
            params.setdefault("candidates", variants)
            params.setdefault("candidate", variants[0])
            params.setdefault("candidate_mock", bool(variants and resp.mock))
        candidate = str(params["candidate"])
        params.setdefault("segments", split_segments(candidate))
        params.setdefault("text", candidate)
        params.setdefault("sample_text", candidate)
        return ctx.model_copy(update={"parameters": params})

    # -- execution -------------------------------------------------------
    async def _run_one(self, sid: str, ctx: ExecutionContext, timeout_ms: int) -> StationOutput:
        inst = self._instantiate(sid)
        try:
            out = await asyncio.wait_for(inst.timed_run(ctx), timeout=timeout_ms / 1000.0)
        except asyncio.TimeoutError:
            out = inst.output(ctx, {"error": f"station timeout after {timeout_ms}ms"},
                              status=StationStatus.FAILED,
                              warnings=[f"{sid} timed out; isolated by engine"])
        _telemetry.station_duration_ms.observe({"station": sid}, out.telemetry.duration_ms)
        if sid == "s03":
            dec = str(out.data.get("decision", "unknown"))
            _telemetry.s3_decisions_total.inc({"decision": dec})
        return out

    def _skipped(self, sid: str, ctx: ExecutionContext, reason: str) -> StationOutput:
        return StationOutput(
            station_id=sid,
            station_version="n/a",
            status=StationStatus.SKIPPED,
            data={"skipped": True, "reason": reason},
            provenance=Provenance(
                request_id=ctx.request_id, correlation_id=ctx.correlation_id,
                station_id=sid, station_version="skipped"),
            warnings=[reason],
        )

    @staticmethod
    def _deadline_exceeded(ctx: ExecutionContext, t0: float, started_ms: float = 0.0) -> bool:
        return (time.monotonic() - t0) * 1000.0 > ctx.deadline_ms

    async def execute(self, ctx: ExecutionContext, plan: ExecutionPlan | None = None,
                      replay_of: str | None = None) -> ExecutionResult:
        plan = plan or ExecutionPlan()
        t0 = time.monotonic()
        execution_id = uuid4().hex

        def timed_out() -> bool:
            return ctx.cancelled or self._deadline_exceeded(ctx, t0)

        # 0. Candidate prep: keeper generates, stations align on it.
        try:
            ctx = await self._prepare_candidate(ctx)
        except Exception as exc:
            log.error("candidate preparation failed: %s", exc)
            result = ExecutionResult(
                execution_id=execution_id, request_id=ctx.request_id,
                correlation_id=ctx.correlation_id, decision=Decision.QUARANTINE,
                status="error", revision_notes=[f"candidate prep failed: {exc}"],
            )
            await _remember_execution(result, ctx)
            return result

        cur = ctx
        outputs: list[StationOutput] = []

        async def run_critical(sid: str, use_ctx: ExecutionContext | None = None) -> bool:
            nonlocal cur
            if timed_out():
                outputs.append(self._skipped(sid, cur, "cancelled or deadline exceeded"))
                return False
            timeout = int(plan.timeouts_ms.get(sid, 15_000))
            out = await self._run_one(sid, use_ctx or cur, timeout)
            cur = cur.with_output(out)
            outputs.append(out)
            return True

        # Critical path: s01 -> s02 -> s03 (the gate), then parallel streams,
        # then the remaining critical gates s06 -> s11.
        for sid in ("s01", "s02", "s03"):
            if sid in plan.critical_path:
                await run_critical(sid)

        # Parallel streams run concurrently with per-station timeouts.
        parallel_ids = [s for s in plan.parallel_streams if s in STATION_REGISTRY]
        parallel_results: dict[str, StationOutput] = {}
        if parallel_ids and not timed_out():
            snap = cur  # immutable: safe to share across gather

            async def run_parallel(sid: str) -> tuple[str, StationOutput]:
                timeout = int(plan.timeouts_ms.get(sid, 10_000))
                return sid, await self._run_one(sid, snap, timeout)

            gathered = await asyncio.gather(
                *(run_parallel(sid) for sid in parallel_ids), return_exceptions=True
            )
            for item in gathered:
                if isinstance(item, Exception):
                    log.error("parallel station raised outside isolation: %s", item)
                    continue
                sid, out = item
                parallel_results[sid] = out
                cur = cur.with_output(out)
                outputs.append(out)
        n_segments = len(cur.parameters.get("segments") or [cur.prompt])
        reconcile_report = self.reconcile(parallel_results, n_segments)

        for sid in ("s06",):
            if sid in plan.critical_path:
                await run_critical(sid)

        # s11: if s03 quarantined, drive intake via quarantine_request so the
        # station performs its sanitization + record creation; the engine then
        # mirrors that record into the API quarantine store (same id).
        s11_ctx = cur
        s03 = cur.station_outputs.get("s03")
        s03_decision = str((s03.data.get("decision") if s03 else "") or "").lower()
        if "s11" in plan.critical_path and s03_decision == Decision.QUARANTINE.value:
            candidate = str(cur.parameters.get("candidate") or cur.prompt)
            reason_code = ("SAFETY_CRITICAL"
                           if s03 and s03.data.get("critical_safety_hit")
                           else "POLICY_VIOLATION")
            risk = "critical" if reason_code == "SAFETY_CRITICAL" else "high"
            params = dict(cur.parameters)
            params["quarantine_request"] = {
                "reason_code": reason_code,
                "risk_class": risk,
                "payload": candidate[:2000],
                "payload_ref": hashlib.sha256(candidate.encode()).hexdigest()[:16],
            }
            s11_ctx = cur.model_copy(update={"parameters": params})
        if "s11" in plan.critical_path:
            await run_critical("s11", s11_ctx)

        # Background stations are not run in the request path; recorded as scheduled.
        scheduled_background = [s for s in plan.background if s in STATION_REGISTRY]

        result = await self.finalize(cur, execution_id, outputs, reconcile_report,
                                     scheduled_background, replay_of)
        result.telemetry_summary["total_ms"] = round((time.monotonic() - t0) * 1000.0, 3)
        await _remember_execution(result, cur)
        _telemetry.executions_total.inc({"status": result.status})
        return result

    # -- reconcile ---------------------------------------------------------
    def _extract_directives(self, sid: str, out: StationOutput,
                            n_segments: int) -> list[dict[str, Any]]:
        """Extract per-segment directives from a station's NATIVE output.

        A station may also emit data["directives"] directly (fallback stations
        and future stations); those are honored verbatim.
        """
        direct = out.data.get("directives")
        if isinstance(direct, list) and direct:
            cleaned = []
            for d in direct:
                try:
                    cleaned.append({"segment": int(d["segment"]),
                                    "directive": str(d.get("directive", "keep")),
                                    "reason": str(d.get("reason", "")),
                                    "station": sid})
                except (KeyError, TypeError, ValueError):
                    continue
            if cleaned:
                return cleaned

        data = out.data
        if sid == "s10":
            # contradictions -> involved claim indices get "cut"
            cut: dict[int, str] = {}
            for c in data.get("contradictions") or []:
                mech = c.get("mechanism", "unknown")
                for key in ("claim_a", "claim_b"):
                    try:
                        idx = int(c[key]["index"])
                    except (KeyError, TypeError, ValueError):
                        continue
                    cut[idx] = f"contradiction ({mech})"
            return [{"segment": i,
                     "directive": "cut" if i in cut else "keep",
                     "reason": cut.get(i, "no contradiction detected"),
                     "station": sid} for i in range(n_segments)]
        if sid == "s05":
            segs = (data.get("drift_report") or {}).get("segments") or []
            out_dirs = []
            for i in range(n_segments):
                entry = segs[i] if i < len(segs) else {}
                drifted = bool(entry.get("drifted", False))
                out_dirs.append({
                    "segment": i,
                    "directive": "revise" if drifted else "keep",
                    "reason": (f"displacement={entry.get('displacement')}, "
                               f"intent={entry.get('intent_cosine')}") if entry else "no data",
                    "station": sid})
            return out_dirs
        if sid == "s04":
            conf = float(data.get("consensus_confidence", 1.0) or 0.0)
            directive = "keep" if conf >= 0.5 else "revise"
            return [{"segment": i, "directive": directive,
                     "reason": f"swarm consensus_confidence={conf}",
                     "station": sid} for i in range(n_segments)]
        if sid == "s07":
            # group breath pieces by sentence_index -> per-sentence directive
            by_sent: dict[int, list[dict]] = {}
            for seg in data.get("segments") or []:
                try:
                    by_sent.setdefault(int(seg.get("sentence_index", 0)), []).append(seg)
                except (TypeError, ValueError):
                    continue
            out_dirs = []
            for i in range(n_segments):
                pieces = by_sent.get(i, [])
                words = sum(p.get("words", 0) for p in pieces)
                out_dirs.append({
                    "segment": i,
                    "directive": "revise" if words > 90 else "keep",
                    "reason": f"breath words={words}",
                    "station": sid})
            return out_dirs
        return []

    def reconcile(self, parallel_outputs: dict[str, StationOutput],
                  n_segments: int = 0) -> dict[str, Any]:
        """Merge per-segment directives from parallel stations.

        When stations disagree on a segment, the deterministic precedence
        s10 > s05 > s04 > s07 decides the winner (documented above and in
        the stations' own reconciliation_policy notes: s10 supersedes s05).
        """
        per_segment: dict[int, list[dict[str, Any]]] = {}
        for sid, out in parallel_outputs.items():
            if out.status not in (StationStatus.OK, StationStatus.DEGRADED):
                continue
            for d in self._extract_directives(sid, out, n_segments):
                per_segment.setdefault(d["segment"], []).append(d)
        rank = {sid: i for i, sid in enumerate(RECONCILE_PRECEDENCE)}
        segments: dict[str, dict[str, Any]] = {}
        conflicts = 0
        for seg, entries in sorted(per_segment.items()):
            directives = {e["directive"] for e in entries}
            entries_sorted = sorted(entries, key=lambda e: rank.get(e["station"], 99))
            winner = entries_sorted[0]
            conflict = len(directives) > 1
            conflicts += 1 if conflict else 0
            segments[str(seg)] = {
                "winner_station": winner["station"],
                "directive": winner["directive"],
                "conflict": conflict,
                "all": entries,
            }
        return {
            "segments": segments,
            "conflicts": conflicts,
            "segments_total": len(segments),
            "precedence": RECONCILE_PRECEDENCE,
        }

    # -- finalize (S3 gate) --------------------------------------------------
    async def finalize(self, ctx: ExecutionContext, execution_id: str,
                       outputs: list[StationOutput], reconcile_report: dict[str, Any],
                       scheduled_background: list[str],
                       replay_of: str | None) -> ExecutionResult:
        """S3 gate — fail-closed.

        The s03 decision is honored whatever the station status
        (ok/degraded/failed); only a missing or unparseable decision fails
        closed to quarantine. The raw candidate is released solely on
        'approve'. On 'revise' the client receives s03's own remediated text
        (revised_candidate), never the raw candidate.
        """
        s03 = ctx.station_outputs.get("s03")
        raw = str((s03.data.get("decision") if s03 else "") or "").lower()
        if raw in Decision._value2member_map_:
            decision = Decision(raw)
            notes: list[str] = [str(w) for w in (s03.warnings if s03 else [])]
        else:
            decision = Decision.QUARANTINE  # fail-closed: no gate verdict
            notes = ["s03 decision missing or unparseable; fail-closed to quarantine"]

        candidate = ctx.parameters.get("candidate")
        candidate = str(candidate) if candidate is not None else None
        s11 = ctx.station_outputs.get("s11")

        text: str | None = None
        revised_text: str | None = None
        quarantine_record_id: str | None = None
        status = "error"

        if decision == Decision.APPROVE:
            status = "completed"
            text = candidate  # S3 approved: the ONLY path that releases the candidate
        elif decision == Decision.REVISE:
            status = "revise"
            revised_text = (s03.data.get("revised_candidate") if s03 else None)
            if not revised_text:
                notes.append("s03 requested revision but attached no revised text")
        elif decision == Decision.REJECT:
            status = "rejected"
        else:  # QUARANTINE
            status = "quarantined"
            # Prefer the s11 station's own record (it ran sanitization); mirror
            # it into the API quarantine store under the same id. Otherwise
            # the engine creates the API record directly. Either way the
            # record exists before the response is returned.
            s11_rec = (s11.data.get("quarantined") if s11 else None)
            record: QuarantineRecord | None = None
            if isinstance(s11_rec, dict) and s11_rec.get("id"):
                try:
                    record = QuarantineRecord(**s11_rec)
                except Exception as exc:
                    log.warning("could not adopt s11 quarantine record: %s", exc)
            if record is None and self.quarantine_store is not None:
                record = QuarantineRecord(
                    request_id=ctx.request_id,
                    reason_code=("SAFETY_CRITICAL"
                                 if s03 and s03.data.get("critical_safety_hit")
                                 else "POLICY_VIOLATION"),
                    risk_class="critical" if s03 and s03.data.get("critical_safety_hit") else "high",
                    payload_ref=hashlib.sha256(
                        (candidate or ctx.prompt).encode()).hexdigest()[:16],
                    station_id="s03",
                    history=[{"event": "quarantined", "via": "engine.finalize",
                              "s03_decision": raw}],
                )
                await self.quarantine_store.create(record)
            elif record is not None and self.quarantine_store is not None:
                # Mirror the s11 record into the API store (same id).
                existing = await self.quarantine_store.get(record.id)
                if existing is None:
                    await self.quarantine_store.create(record)
            if record is not None:
                quarantine_record_id = record.id
            else:
                notes.append("quarantine requested but no store available")

        # S3 gate enforcement: on quarantine/reject/revise the raw candidate must
        # not appear ANYWHERE in the client-facing result — including the
        # parallel stations' output payloads (s02/s04/s07 echo candidate text).
        # Only the s03 decision, warnings, timings, s11's sanitized payload,
        # and (on revise) s03's own remediated revised_candidate survive.
        # revised_candidate never byte-matches a raw needle (it is remediated),
        # so redaction cannot clobber the designed revise release path.
        if decision in (Decision.QUARANTINE, Decision.REJECT, Decision.REVISE):
            needles: list[str] = []
            for key in ("candidate", "candidates", "segments", "text", "sample_text"):
                value = ctx.parameters.get(key)
                if isinstance(value, str):
                    needles.append(value)
                elif isinstance(value, list):
                    needles.extend(v for v in value if isinstance(v, str))
            # Station payloads may echo candidate *fragments* (e.g. s07
            # clause-level segments), which never byte-match a full-candidate
            # needle. Add clause-level fragments so substring redaction
            # catches them.
            fragments: list[str] = []
            for n in needles:
                for part in re.split(r"[.!?,;:\n]+", n):
                    part = part.strip()
                    if len(part) >= 16:
                        fragments.append(part)
            needles.extend(fragments)
            outputs = _redact_sensitive(outputs, needles)

        return ExecutionResult(
            execution_id=execution_id,
            request_id=ctx.request_id,
            correlation_id=ctx.correlation_id,
            decision=decision,
            status=status,
            text=text,  # None unless approved — never the raw candidate otherwise
            revised_text=revised_text,
            candidate=candidate,
            quarantine_record_id=quarantine_record_id,
            station_outputs=outputs,
            reconcile_report=reconcile_report,
            scheduled_background=scheduled_background,
            revision_notes=notes if decision != Decision.APPROVE else [],
            telemetry_summary={},
            replay_of=replay_of,
        )
