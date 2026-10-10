"""Simulation runner: execute a compiled spell AST with bounded steps.

run() takes the `ast` dict straight from VMCompileRequest/VMCompileResponse
and returns a dict shaped like VMSimulateResponse:
  {"ok", "final_state", "events", "invariant_checks", "errors"}

Pipeline:
  1. Validate AST shape (compiler.ast.validate).
  2. Effect type-check (compiler.effects.check) — errors halt before execution.
  3. Build Engine(seed), load initial_state (mana, bindings, capabilities,
     topology), execute with max_steps cap.
  4. Run invariant checkers over final state + event log.
  5. Catch HaltExecution/LexError/etc. -> ok=False with reason in errors.

max_steps: default 1000, hard cap 100000 (matches VMSimulateRequest.le).
Deterministic: identical (ast, initial_state, seed) -> identical event log.
"""

from __future__ import annotations

from ..compiler.ast import validate
from ..compiler.effects import check as check_effects
from ..runtime.engine import Engine, HaltExecution
from ..state.invariants import check_all

HARD_CAP_STEPS = 100_000
DEFAULT_MAX_STEPS = 1000


def run(ast: dict, initial_state: dict | None = None,
        max_steps: int = DEFAULT_MAX_STEPS, seed: int = 0,
        principal: str = "caster") -> dict:
    errors: list[str] = []
    initial_state = initial_state or {}

    if max_steps > HARD_CAP_STEPS:
        return {
            "ok": False,
            "final_state": None,
            "events": [],
            "invariant_checks": [],
            "errors": [f"max_steps {max_steps} exceeds hard cap {HARD_CAP_STEPS}"],
        }

    for err in validate(ast):
        errors.append(f"AST: {err}")
    for v in check_effects(ast):
        if v.kind == "error":
            errors.append(f"effect: {v.message}")
    if errors:
        return {
            "ok": False, "final_state": None, "events": [],
            "invariant_checks": [], "errors": errors,
        }

    engine = Engine(seed=seed)
    try:
        engine.load_initial_state(initial_state)
        engine.execute(ast, principal=principal, max_steps=max_steps)
        ok = True
    except HaltExecution as e:
        ok = False
        errors.append(f"halt: {e.reason}")
    except Exception as e:  # defensive: never leak a traceback as success
        ok = False
        errors.append(f"internal: {type(e).__name__}: {e}")

    events = [dict(ev) for ev in engine.store.events]
    invariant_checks = check_all(engine.state, engine.store.events)

    return {
        "ok": ok and all(c["passed"] for c in invariant_checks),
        "final_state": engine.snapshot_state(),
        "events": events,
        "invariant_checks": invariant_checks,
        "errors": errors,
    }
