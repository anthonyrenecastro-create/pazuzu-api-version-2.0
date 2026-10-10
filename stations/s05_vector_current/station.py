"""S05 Vector Current — semantic drift monitoring.

Contract
--------
Monitors drift across an ordered list of text segments
(``ctx.parameters["segments"]``, else sentences of the prompt) using
three explicit, documented metrics. Segment embeddings are deterministic
hashing vectors (SURROGATE — not real embeddings; see S04).

Metrics (formulas):
  (a) normalized embedding displacement per segment i:
        disp_i = ||v_i − v_0|| / ||v_0||
      where v_0 is the embedding of the task anchor (default: ctx.prompt).
      Guard: if ||v_0|| == 0, disp_i = 0.0 and a warning is emitted.
  (b) task-intent cosine similarity per segment i:
        intent_i = (v_i · v_0) / (||v_i|| · ||v_0||)
      Guard: zero-norm vectors yield 0.0.
  (c) cyclic inconsistency indicator: for each antonym pair (a, b), each
      segment votes for side a, side b, both, or neither by keyword
      presence. Across the segment sequence, count flip-flops: indices i
      where side[i] == side[i−2] and side[i] != side[i−1] (an A→B→A
      claim reversal). Total flip-flops summed over pairs.

``trigger_corrective_review`` is True when any segment exceeds
``disp_threshold`` (default 0.9), drops below ``intent_threshold``
(default 0.25), or any flip-flop is detected.

FORBIDDEN (audit #58): a 3D curl operator on embeddings was a fatal
math error in v1 (curl is defined on 3D vector *fields*, not on a
sequence of embedding vectors). This station implements no curl, no
divergence, no vorticity — only the three metrics above.

Reconciliation policy: on the same segment, an S10 contradiction verdict
supersedes S05 drift flags (S10 wins over S05).

Assumptions
-----------
- Segments arrive in chronological order.
- Parameters: ``segments``, ``anchor_text`` (default ctx.prompt),
  ``disp_threshold``, ``intent_threshold``, ``vector_dim`` (128).

Known limitations
-----------------
- Surrogate embeddings: drift scores track lexical movement, and a
  paraphrase can look like drift while a subtle semantic flip can look
  stable.
- Antonym-pair flip-flop detection is keyword-based; negation scope and
  sarcasm are not modeled.
- Thresholds are heuristics, uncalibrated.
"""
from __future__ import annotations

import hashlib
import math
import re
import time

from pazuzu_contracts import (
    ExecutionContext,
    Station,
    StationManifest,
    StationOutput,
    StationStatus,
)

ANTONYM_PAIRS = [
    ("increase", "decrease"), ("safe", "dangerous"), ("true", "false"),
    ("legal", "illegal"), ("open", "closed"), ("support", "oppose"),
    ("rise", "fall"), ("possible", "impossible"), ("allow", "forbid"),
    ("always", "never"),
]


def _hash_vector(text: str, dim: int = 128) -> list[float]:
    vec = [0.0] * dim
    t = text.lower()
    for i in range(len(t) - 2):
        h = int(hashlib.md5(t[i:i + 3].encode()).hexdigest(), 16)
        vec[h % dim] += 1.0
    norm = math.sqrt(sum(x * x for x in vec))
    return [x / norm for x in vec] if norm else vec


def _norm(v: list[float]) -> float:
    return math.sqrt(sum(x * x for x in v))


def _sub(a: list[float], b: list[float]) -> list[float]:
    return [x - y for x, y in zip(a, b)]


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _flipflops(segments: list[str]) -> tuple[int, list[dict]]:
    """Count A→B→A claim reversals per antonym pair (keyword heuristic)."""
    total = 0
    detail: list[dict] = []
    lowered = [s.lower() for s in segments]
    for a, b in ANTONYM_PAIRS:
        sides: list[str | None] = []
        for s in lowered:
            has_a = re.search(rf"\b{re.escape(a)}\b", s) is not None
            has_b = re.search(rf"\b{re.escape(b)}\b", s) is not None
            sides.append("a" if has_a and not has_b else ("b" if has_b and not has_a else None))
        seq = [x for x in sides if x is not None]
        flips = sum(1 for i in range(2, len(seq))
                    if seq[i] == seq[i - 2] and seq[i] != seq[i - 1])
        if flips:
            total += flips
            detail.append({"pair": [a, b], "flipflops": flips, "side_sequence": seq})
    return total, detail


class S05VectorCurrent(Station):
    """Semantic drift monitor: displacement, intent cosine, flip-flops."""

    manifest = StationManifest(
        id="s05",
        name="Vector Current",
        version="2.0.0",
        critical_path=False,
        description="Drift monitoring via normalized displacement, task-intent "
                    "cosine, and cyclic-inconsistency flip-flop counts. No curl.",
    )

    async def run(self, ctx: ExecutionContext) -> StationOutput:
        t0 = time.perf_counter()
        params = ctx.parameters or {}
        dim = int(params.get("vector_dim", 128))
        disp_thr = float(params.get("disp_threshold", 0.9))
        intent_thr = float(params.get("intent_threshold", 0.25))

        segments: list[str] = params.get("segments") or [
            s.strip() for s in re.split(r"(?<=[.!?])\s+", ctx.prompt or "") if s.strip()]
        anchor = params.get("anchor_text", ctx.prompt or "")
        v0 = _hash_vector(anchor, dim)
        n0 = _norm(v0)

        warnings = []
        if n0 == 0:
            warnings.append("anchor embedding has zero norm; displacement forced to 0")

        per_segment = []
        for i, seg in enumerate(segments):
            vi = _hash_vector(seg, dim)
            ni = _norm(vi)
            disp = _norm(_sub(vi, v0)) / n0 if n0 else 0.0
            intent = (_dot(vi, v0) / (ni * n0)) if ni and n0 else 0.0
            per_segment.append({
                "index": i,
                "displacement": round(disp, 4),      # ||v_i − v_0|| / ||v_0||
                "intent_cosine": round(intent, 4),   # (v_i·v_0)/(||v_i||·||v_0||)
                "drifted": bool(disp > disp_thr or intent < intent_thr),
            })

        flips, flip_detail = _flipflops(segments)
        max_disp = max((s["displacement"] for s in per_segment), default=0.0)
        min_intent = min((s["intent_cosine"] for s in per_segment), default=1.0)
        trigger = bool(max_disp > disp_thr or min_intent < intent_thr or flips > 0)

        data = {
            "drift_report": {
                "segments": per_segment,
                "max_displacement": round(max_disp, 4),
                "min_intent_cosine": round(min_intent, 4),
                "cyclic_inconsistency": {"flipflops": flips, "pairs": flip_detail},
            },
            "trigger_corrective_review": trigger,
            "thresholds": {"disp_threshold": disp_thr, "intent_threshold": intent_thr},
            "formulas": {
                "displacement": "disp_i = ||v_i − v_0|| / ||v_0||",
                "intent_cosine": "intent_i = (v_i · v_0) / (||v_i|| · ||v_0||)",
                "flipflop": "count of i with side[i]==side[i-2] and side[i]!=side[i-1] per antonym pair",
            },
            "embedding_disclaimer": (
                "Surrogate char-3-gram hashing vectors; lexical drift proxy, "
                "not semantic ground truth."),
            "reconciliation_policy": (
                "On the same segment, an S10 contradiction verdict supersedes "
                "S05 drift flags (S10 wins over S05)."),
            "no_curl_note": (
                "No curl/divergence/vorticity operators are used (audit #58: "
                "3D curl on embedding sequences was a fatal math error)."),
        }
        if trigger:
            warnings.append("drift threshold breached or flip-flop detected; corrective review triggered")
        return self.output(
            ctx, data, warnings=warnings,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )
