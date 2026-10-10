"""S12 Bronze Reduction — resource profiling and quantization planning.

Contract
--------
Profiles a request's resource footprint on a mock workload:
token counts (whitespace estimates), wall-clock latency of the profiling
pass itself, and cache statistics supplied via ``ctx.parameters``
(``cache_hits`` / ``cache_lookups``).

Quantization planning applies ONLY to local artifacts
(``ctx.parameters["artifact_location"] == "local"``). The station
documents explicitly: it never claims to quantize hosted models
(Grok, DeepSeek, or any API-served model) — quantization of a hosted
model is not something a client can do, and any such claim would be
false. If ``artifact_location`` is "hosted" (or a hosted provider name
is given), the plan is refused with a documented reason.

A quality-preservation checklist is emitted with every plan
(perplexity-delta check, eval-suite pass, latency budget, rollback plan,
all marked as operator-verified items, not auto-proven).

Performance regression detector: compares current measurements against
a stored baseline JSON (``ctx.parameters["baseline"]`` =
{latency_p50_ms, tokens_per_sec, error_rate}); flags drift beyond
``regression_thresholds`` (defaults: latency +20%, throughput −20%,
error_rate +0.01 absolute).

Assumptions
-----------
- Mock workload = hashing + token counting over ``workload_text``
  (default: ctx.prompt); it measures harness overhead, not model cost.
- Cache stats are caller-supplied; the station does not observe a real cache.
- Baseline JSON is caller-supplied; the station does not persist it.

Known limitations
-----------------
- Whitespace token estimates, not a real tokenizer.
- Latency measured is local harness time, not provider latency.
- Checklist items are attestations for the operator to verify; the
  station cannot run perplexity or eval suites itself.
"""
from __future__ import annotations

import hashlib
import time

from pazuzu_contracts import (
    ExecutionContext,
    Station,
    StationManifest,
    StationOutput,
    StationStatus,
)

HOSTED_PROVIDERS = {"grok", "deepseek", "openai", "anthropic", "gemini",
                    "mistral", "cohere"}


class S12BronzeReduction(Station):
    """Resource profiler + local-only quantization planner + regression detector."""

    manifest = StationManifest(
        id="s12",
        name="Bronze Reduction",
        version="2.0.0",
        critical_path=False,
        description="Mock-workload resource profiling, quantization planning "
                    "for local artifacts only (never hosted models), "
                    "quality-preservation checklist, baseline regression detection.",
    )

    async def run(self, ctx: ExecutionContext) -> StationOutput:
        t0 = time.perf_counter()
        params = ctx.parameters or {}
        workload = str(params.get("workload_text", ctx.prompt or ""))

        # --- profiling pass (mock workload) ---
        p0 = time.perf_counter()
        tokens = workload.split()
        digest = hashlib.sha256(workload.encode()).hexdigest()
        latency_ms = (time.perf_counter() - p0) * 1000.0
        tokens_in = len(tokens)
        tokens_per_sec = (tokens_in / latency_ms * 1000.0) if latency_ms > 0 else 0.0
        lookups = int(params.get("cache_lookups", 0))
        hits = int(params.get("cache_hits", 0))
        hit_rate = (hits / lookups) if lookups else 0.0

        profile = {
            "tokens_in_estimate": tokens_in,
            "latency_ms": round(latency_ms, 4),
            "tokens_per_sec": round(tokens_per_sec, 2),
            "cache": {"lookups": lookups, "hits": hits,
                      "hit_rate": round(hit_rate, 4)},
            "workload_digest": digest[:16],
            "note": "Mock workload: measures harness overhead, not provider model cost.",
        }

        # --- quantization planning: local artifacts ONLY ---
        location = str(params.get("artifact_location", "local")).lower()
        provider = str(params.get("provider", "")).lower()
        quant: dict = {}
        warnings: list[str] = []
        if location == "hosted" or provider in HOSTED_PROVIDERS:
            quant = {
                "planned": False,
                "reason": (
                    "Quantization planning refused: target is a HOSTED model "
                    f"(location={location}, provider={provider or 'unspecified'}). "
                    "A client cannot quantize Grok, DeepSeek, or any API-served "
                    "model; claiming otherwise would be false. Quantization "
                    "applies only to local artifacts you control."),
            }
            warnings.append("quantization refused for hosted model (documented limitation)")
        else:
            quant = {
                "planned": True,
                "target": params.get("artifact_path", "<local artifact>"),
                "candidate_precisions": ["int8", "int4"],
                "strategy": ("Post-training quantization of the LOCAL artifact; "
                             "calibrate on a held-out sample, verify checklist, "
                             "keep the fp16 original for rollback."),
                "quality_preservation_checklist": [
                    {"item": "perplexity delta vs fp16 within budget",
                     "verified_by": "operator"},
                    {"item": "eval suite passes at parity threshold",
                     "verified_by": "operator"},
                    {"item": "p50 latency within budget on target hardware",
                     "verified_by": "operator"},
                    {"item": "rollback plan: fp16 artifact retained and loadable",
                     "verified_by": "operator"},
                    {"item": "no hosted-model quantization claimed",
                     "verified_by": "station invariant"},
                ],
            }

        # --- regression detector vs stored baseline ---
        baseline = params.get("baseline") or {}
        thresholds = params.get("regression_thresholds",
                                {"latency_p50_ms": 1.20, "tokens_per_sec": 0.80,
                                 "error_rate_abs": 0.01})
        regressions: list[dict] = []
        if baseline:
            if "latency_p50_ms" in baseline and baseline["latency_p50_ms"]:
                ratio = latency_ms / baseline["latency_p50_ms"]
                if ratio > thresholds["latency_p50_ms"]:
                    regressions.append({"metric": "latency_p50_ms",
                                        "baseline": baseline["latency_p50_ms"],
                                        "current": round(latency_ms, 4),
                                        "ratio": round(ratio, 3)})
            if "tokens_per_sec" in baseline and baseline["tokens_per_sec"]:
                ratio = tokens_per_sec / baseline["tokens_per_sec"]
                if ratio < thresholds["tokens_per_sec"]:
                    regressions.append({"metric": "tokens_per_sec",
                                        "baseline": baseline["tokens_per_sec"],
                                        "current": round(tokens_per_sec, 2),
                                        "ratio": round(ratio, 3)})
            err = float(params.get("error_rate", 0.0))
            base_err = float(baseline.get("error_rate", 0.0))
            if err - base_err > thresholds["error_rate_abs"]:
                regressions.append({"metric": "error_rate",
                                    "baseline": base_err, "current": err})

        data = {
            "profile": profile,
            "quantization": quant,
            "regression": {
                "baseline_provided": bool(baseline),
                "regressions": regressions,
                "regression_detected": bool(regressions),
            },
        }
        if regressions:
            warnings.append(f"performance regression detected: {len(regressions)} metric(s)")
            status = StationStatus.DEGRADED
        else:
            status = StationStatus.OK
        return self.output(
            ctx, data, status=status, warnings=warnings,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
            tokens_in=tokens_in,
        )
