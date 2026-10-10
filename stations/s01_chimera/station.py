"""S01 Chimera Gate — noisy top-k expert router.

Contract
--------
Given the request prompt, classify it into a domain (keyword/domain
classifier over a configurable domain→expert map), then route to the
top-k experts using *noisy* top-k selection: additive Gaussian noise is
injected into each expert's logit before ranking (audit #11 — the noise
is load-balancing exploration, not a ranking improvement, and the
seed is logged so routing is reproducible).

Availability-aware failover: experts marked unavailable in the
availability table are skipped and the next-best expert takes the slot.
Routing confidence is the softmax margin (p1 − p2) over the selected
experts' noisy logits. Per-expert utilization counters are maintained
per process instance (in-memory; a durable deployment must persist
them) and reported with every output.

Assumptions
-----------
- `ctx.parameters` may carry: ``domain_expert_map`` (domain → [experts]),
  ``domain_keywords`` (domain → [keywords]), ``expert_availability``
  (expert → bool), ``top_k`` (default 2), ``routing_noise_std``
  (default 0.1), ``utilization_seed`` (expert → count).
- Noise RNG is seeded from ``sha256(request_id)``: deterministic per
  request, different across requests.
- No provider/LLM calls: routing is purely lexical.

Known limitations
-----------------
- Keyword classifier is crude: substring matching, no stemming, no
  semantic understanding; adversarial or ambiguous prompts misroute.
- Utilization counters are process-local and reset on restart — they
  are telemetry, not billing-grade accounting.
- Noise does not improve routing quality; it only spreads load.
- Softmax margin is a heuristic confidence, not a calibrated probability.
"""
from __future__ import annotations

import hashlib
import math
import random
import time

from pazuzu_contracts import (
    ExecutionContext,
    Station,
    StationManifest,
    StationOutput,
    StationStatus,
)

DEFAULT_DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "code": ["code", "function", "bug", "python", "error", "debug", "api",
             "compile", "refactor", "script"],
    "math": ["math", "equation", "proof", "theorem", "calculate", "integral",
             "derivative", "matrix"],
    "safety": ["harm", "weapon", "danger", "illegal", "self-harm", "suicide",
               "exploit", "attack"],
    "creative": ["story", "poem", "write", "novel", "character", "plot",
                 "narrative", "essay"],
    "general": [],
}

DEFAULT_DOMAIN_EXPERTS: dict[str, list[str]] = {
    "code": ["expert_coder_a", "expert_coder_b"],
    "math": ["expert_math_a", "expert_math_b"],
    "safety": ["expert_safety_a"],
    "creative": ["expert_writer_a", "expert_writer_b"],
    "general": ["expert_general_a", "expert_general_b"],
}


def _softmax(logits: list[float]) -> list[float]:
    m = max(logits) if logits else 0.0
    exps = [math.exp(x - m) for x in logits]
    total = sum(exps) or 1.0
    return [e / total for e in exps]


class S01Chimera(Station):
    """Noisy top-k expert router with availability failover."""

    manifest = StationManifest(
        id="s01",
        name="Chimera Gate",
        version="2.0.0",
        critical_path=True,
        description="Keyword-domain classifier with noisy top-k expert routing, "
                    "availability-aware failover, and utilization counters.",
    )

    def __init__(self) -> None:
        # Process-local utilization counters (telemetry only — see module docstring).
        self.utilization: dict[str, int] = {}

    async def run(self, ctx: ExecutionContext) -> StationOutput:
        t0 = time.perf_counter()
        params = ctx.parameters or {}
        domain_map: dict[str, list[str]] = params.get("domain_expert_map", DEFAULT_DOMAIN_EXPERTS)
        keywords: dict[str, list[str]] = params.get("domain_keywords", DEFAULT_DOMAIN_KEYWORDS)
        availability: dict[str, bool] = params.get("expert_availability", {})
        top_k = max(1, int(params.get("top_k", 2)))
        noise_std = float(params.get("routing_noise_std", 0.1))

        seed = int.from_bytes(hashlib.sha256(ctx.request_id.encode()).digest()[:8], "big")
        rng = random.Random(seed)

        prompt = (ctx.prompt or "").lower()
        domain_scores = {
            domain: sum(prompt.count(kw.lower()) for kw in kws)
            for domain, kws in keywords.items()
        }
        best_domain = max(domain_scores, key=lambda d: domain_scores[d])
        if domain_scores[best_domain] == 0:
            best_domain = "general"

        experts = list(domain_map.get(best_domain, domain_map.get("general", [])))
        if not experts:
            return self.output(
                ctx,
                {"error": f"no experts configured for domain '{best_domain}'"},
                status=StationStatus.FAILED,
                warnings=["empty expert map; check domain_expert_map"],
                duration_ms=(time.perf_counter() - t0) * 1000.0,
            )

        # Noisy logits: score + N(0, noise_std). Noise is load-balancing
        # exploration (audit #11); seed logged for reproducibility.
        noisy_logits: dict[str, float] = {}
        base_score = domain_scores[best_domain]
        for rank, expert in enumerate(experts):
            prior = (len(experts) - rank) * 0.01  # stable tiebreak toward config order
            noisy_logits[expert] = base_score + prior + rng.gauss(0.0, noise_std)

        ranked = sorted(noisy_logits, key=lambda e: noisy_logits[e], reverse=True)

        # Availability-aware failover: skip unavailable, take next best.
        selected: list[str] = []
        failovers: list[dict[str, str]] = []
        for expert in ranked:
            if availability.get(expert, True):
                selected.append(expert)
                if len(selected) >= top_k:
                    break
            else:
                failovers.append({"skipped": expert, "reason": "marked unavailable"})

        for expert in selected:
            seeded = (params.get("utilization_seed") or {}).get(expert, 0)
            self.utilization[expert] = self.utilization.get(expert, seeded) + 1

        sel_logits = [noisy_logits[e] for e in selected]
        probs = _softmax(sel_logits)
        weights = {e: round(p, 4) for e, p in zip(selected, probs)}
        # Routing confidence = softmax margin p1 − p2 (heuristic, uncalibrated).
        confidence = round(probs[0] - probs[1], 4) if len(probs) > 1 else 1.0

        data = {
            "routing_decision": {
                "domain": best_domain,
                "experts": selected,
                "weights": weights,
                "confidence": confidence,
                "noisy_logits": {e: round(noisy_logits[e], 4) for e in selected},
            },
            "domain_scores": domain_scores,
            "availability_table": {e: availability.get(e, True) for e in experts},
            "failovers": failovers,
            "utilization": dict(self.utilization),
            "routing_noise_std": noise_std,
            "noise_seed": seed,
            "top_k": top_k,
        }
        warnings = []
        if failovers:
            warnings.append(f"{len(failovers)} expert(s) failed over to next-best")
        if confidence < 0.2:
            warnings.append("low routing margin; experts nearly tied")
        return self.output(
            ctx, data, warnings=warnings,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )
