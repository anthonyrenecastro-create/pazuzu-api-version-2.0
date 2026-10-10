"""Unit tests for the Thaumic VM (compiler + simulator)."""
from __future__ import annotations

import pytest
from pazuzu_contracts import VMCompileRequest, VMSimulateRequest

from apps.api.app import vm as vm_mod

VALID_SPELL = """\
# open the gate
set charge 3
add charge 2
emit "gate opened"
assert charge >= 5
"""


def _compile(source: str, dialect: str = "thaumic-1"):
    return vm_mod.compile_source(VMCompileRequest(source=source, dialect=dialect))


def test_compile_valid_spell_ok():
    resp = _compile(VALID_SPELL)
    assert resp.ok is True
    assert resp.errors == []
    assert resp.ast is not None
    assert resp.ast["dialect"] == "thaumic-1"
    ops = [op["op"] for op in resp.ast["ops"]]
    assert ops == ["set", "add", "emit", "assert"]


def test_compile_invalid_spell_reports_errors():
    resp = _compile("set x 1\nfrobnicate the moon\n")
    assert resp.ok is False
    assert resp.ast is None
    assert resp.errors, "expected at least one syntax error"
    assert any("line 2" in e for e in resp.errors)


def test_compile_rejects_unknown_dialect():
    resp = _compile("set x 1\n", dialect="nope-9")
    assert resp.ok is False
    assert any("unsupported dialect" in e for e in resp.errors)


def test_simulate_is_deterministic():
    """Same AST + same seed twice => identical events and final state."""
    ast = _compile(VALID_SPELL).ast
    assert ast is not None
    req = lambda: VMSimulateRequest(ast=ast, seed=42)
    first = vm_mod.simulate_ast(req())
    second = vm_mod.simulate_ast(req())
    assert first.ok and second.ok
    assert first.final_state == second.final_state == {"charge": 5}
    assert first.events == second.events
    assert [e["message"] for e in first.events] == ["gate opened"]
    assert all(c["passed"] for c in first.invariant_checks)


def test_simulate_detects_invariant_violation():
    ast = _compile("set x 5\nsub x 10\nassert x >= 0\n").ast
    assert ast is not None
    resp = vm_mod.simulate_ast(VMSimulateRequest(ast=ast))
    assert resp.ok is False
    assert any("invariant failed" in e for e in resp.errors)
    assert resp.invariant_checks and resp.invariant_checks[0]["passed"] is False
    assert resp.final_state == {"x": -5}


def test_simulate_enforces_max_steps_cap():
    src = "\n".join(f"emit \"tick {i}\"" for i in range(10)) + "\n"
    ast = _compile(src).ast
    assert ast is not None
    resp = vm_mod.simulate_ast(VMSimulateRequest(ast=ast, max_steps=3))
    assert resp.ok is False
    assert len(resp.events) == 3
    assert any("truncated at max_steps=3" in e for e in resp.errors)


def test_simulate_replay_reproduces_state():
    """Re-running the same AST from the same initial state reproduces it."""
    ast = _compile("add counter 7\nemit \"bump\"\nassert counter == 8\n").ast
    assert ast is not None
    req = lambda: VMSimulateRequest(ast=ast, initial_state={"counter": 1})
    first = vm_mod.simulate_ast(req())
    replay = vm_mod.simulate_ast(req())
    assert first.ok and replay.ok
    assert replay.final_state == first.final_state == {"counter": 8}
    assert replay.events == first.events
    assert replay.invariant_checks == first.invariant_checks


def test_simulate_rejects_malformed_ast():
    resp = vm_mod.simulate_ast(VMSimulateRequest(ast={"ops": "not-a-list"}))
    assert resp.ok is False
    assert resp.errors
