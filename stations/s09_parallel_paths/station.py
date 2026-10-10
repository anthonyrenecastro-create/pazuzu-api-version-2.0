"""S09 Parallel Paths — bounded branching with collapse.

Contract
--------
Builds up to ``max_branches`` (default 3) branch plans, each carrying
explicit assumptions, an estimated cost (``est_ms``), and provenance
(branch id, parent, source). Branching depth is hard-capped at
``max_depth`` (default 2) — no unbounded recursion; deeper expansion is
refused, not attempted. Deadline-aware: branches whose ``est_ms``
exceeds the remaining budget (``ctx.deadline_ms`` minus
``ctx.parameters["elapsed_ms"]``) are skipped with a recorded reason.
Collapse rule: branches are scored by a documented heuristic
(``1/(1+assumptions) − est_ms/1e6`` — fewer assumptions and cheaper cost
win); the top scorer is selected and the rest are retained as provenance
in ``branches_discarded``.

Branch plans come from ``ctx.parameters["branch_strategies"]`` or are
auto-generated as three generic strategies (decompose / alternative /
conservative) over the prompt.

Assumptions
-----------
- Parameters: ``branch_strategies`` (list of {name, assumptions,
  est_ms}), ``max_branches`` (3), ``max_depth`` (2), ``elapsed_ms`` (0).
- est_ms values are estimates supplied by the caller, not measurements.

Known limitations
-----------------
- Branch scoring is a crude heuristic; "best" means cheapest/simplest,
  not most correct.
- No actual parallel execution happens here — this station plans and
  selects; execution is the orchestrator's job.
- Depth cap means genuinely deep decompositions are truncated.
"""
from __future__ import annotations

import time
import uuid

from pazuzu_contracts import (
    ExecutionContext,
    Station,
    StationManifest,
    StationOutput,
    StationStatus,
)

DEFAULT_MAX_BRANCHES = 3
DEFAULT_MAX_DEPTH = 2


def _auto_strategies(prompt: str) -> list[dict]:
    p = (prompt or "")[:120]
    return [
        {"name": "decompose",
         "assumptions": ["request splits into independent sub-tasks",
                         "sub-task outputs compose without conflict"],
         "est_ms": 4000},
        {"name": "alternative",
         "assumptions": ["a second approach exists",
                         "approach cost is comparable"],
         "est_ms": 6000},
        {"name": "conservative",
         "assumptions": ["minimal safe answer suffices",
                         f"prompt scope is as stated: {p}"],
         "est_ms": 2000},
    ]


class S09ParallelPaths(Station):
    """Bounded branching planner with deadline-aware collapse."""

    manifest = StationManifest(
        id="s09",
        name="Parallel Paths",
        version="2.0.0",
        critical_path=False,
        description="Hard-capped branching (max 3 branches, depth 2), "
                    "deadline-aware pruning, heuristic collapse with "
                    "full branch provenance.",
    )

    async def run(self, ctx: ExecutionContext) -> StationOutput:
        t0 = time.perf_counter()
        params = ctx.parameters or {}
        max_branches = min(int(params.get("max_branches", DEFAULT_MAX_BRANCHES)),
                           DEFAULT_MAX_BRANCHES)  # hard cap
        max_depth = min(int(params.get("max_depth", DEFAULT_MAX_DEPTH)),
                        DEFAULT_MAX_DEPTH)  # hard cap
        elapsed = float(params.get("elapsed_ms", 0))
        remaining = max(0.0, ctx.deadline_ms - elapsed)

        strategies = params.get("branch_strategies") or _auto_strategies(ctx.prompt or "")
        strategies = strategies[:max_branches]

        branches: list[dict] = []
        skipped: list[dict] = []
        for i, spec in enumerate(strategies):
            name = spec.get("name", f"branch-{i}")
            assumptions = list(spec.get("assumptions", []))
            est_ms = float(spec.get("est_ms", 5000))
            depth = min(int(spec.get("depth", 1)), max_depth)
            bid = f"br-{uuid.uuid4().hex[:8]}"
            if est_ms > remaining:
                skipped.append({"name": name, "est_ms": est_ms,
                                "reason": "exceeds remaining deadline budget"})
                continue
            # Heuristic score: fewer assumptions and lower cost win.
            score = 1.0 / (1 + len(assumptions)) - est_ms / 1e6
            branches.append({
                "id": bid, "name": name, "depth": depth,
                "assumptions": assumptions, "est_ms": est_ms,
                "score": round(score, 4),
                "provenance": {"parent": "s09", "source": "branch_strategies"
                               if params.get("branch_strategies") else "auto-generated",
                               "request_id": ctx.request_id},
            })

        if not branches:
            return self.output(
                ctx,
                {"error": "no branches within deadline budget",
                 "skipped": skipped, "remaining_ms": remaining},
                status=StationStatus.FAILED,
                duration_ms=(time.perf_counter() - t0) * 1000.0,
            )

        branches.sort(key=lambda b: b["score"], reverse=True)
        selected, discarded = branches[0], branches[1:]

        data = {
            "selected_branch": selected,
            "branches_discarded": discarded,  # retained as provenance
            "branches_skipped": skipped,
            "collapse_rule": "max heuristic score = 1/(1+assumptions) − est_ms/1e6; "
                             "others retained as provenance, not deleted",
            "caps": {"max_branches": max_branches, "max_depth": max_depth,
                     "hard_caps": {"max_branches": DEFAULT_MAX_BRANCHES,
                                   "max_depth": DEFAULT_MAX_DEPTH}},
            "budget": {"deadline_ms": ctx.deadline_ms, "elapsed_ms": elapsed,
                       "remaining_ms": remaining},
        }
        warnings = []
        if skipped:
            warnings.append(f"{len(skipped)} branch(es) skipped: over deadline budget")
        if discarded:
            warnings.append(f"{len(discarded)} branch(es) collapsed away (kept as provenance)")
        return self.output(
            ctx, data, warnings=warnings,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )
