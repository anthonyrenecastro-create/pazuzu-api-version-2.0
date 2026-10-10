"""Thaumic VM: tiny real compiler + simulator for the thaumic-1 dialect.

Dialect thaumic-1 (line-oriented):
    # comment
    set <name> <number|string>      set x 3 | set label "hello"
    add <name> <number>             add x 2
    sub <name> <number>             sub x 1
    emit "<message>"                emit "gate opened"
    assert <name> <op> <number>     assert x >= 0   (op: == != > >= < <=)

compile() parses source into an AST dict (or errors). simulate() executes the
AST deterministically: state updates, emit events, assert invariant checks.
"""
from __future__ import annotations

import re
from typing import Any

from pazuzu_contracts import (
    VMCompileRequest,
    VMCompileResponse,
    VMSimulateRequest,
    VMSimulateResponse,
)

_OPS = ("==", "!=", ">=", "<=", ">", "<")
_LINE_RE = {
    "set": re.compile(r'^set\s+([A-Za-z_][A-Za-z0-9_]*)\s+(.+)$'),
    "add": re.compile(r'^add\s+([A-Za-z_][A-Za-z0-9_]*)\s+(-?\d+(?:\.\d+)?)$'),
    "sub": re.compile(r'^sub\s+([A-Za-z_][A-Za-z0-9_]*)\s+(-?\d+(?:\.\d+)?)$'),
    "emit": re.compile(r'^emit\s+"([^"]*)"$'),
    "assert": re.compile(r'^assert\s+([A-Za-z_][A-Za-z0-9_]*)\s*(==|!=|>=|<=|>|<)\s*(-?\d+(?:\.\d+)?)$'),
}

SUPPORTED_DIALECTS = {
    "thaumic-1": {
        "version": "1.0",
        "kind": "dialect",
        "capabilities": ["compile", "simulate"],
        "description": "Line-oriented thaumic VM dialect: set/add/sub/emit/assert.",
    }
}


def formalisms() -> list[dict[str, Any]]:
    """Computed from the compiler's actually-supported dialects."""
    return [
        {"name": name, **spec} for name, spec in sorted(SUPPORTED_DIALECTS.items())
    ]


def _num(token: str) -> int | float:
    return float(token) if "." in token else int(token)


def compile_source(req: VMCompileRequest) -> VMCompileResponse:
    if req.dialect not in SUPPORTED_DIALECTS:
        return VMCompileResponse(
            ok=False,
            errors=[f"unsupported dialect '{req.dialect}'; supported: {sorted(SUPPORTED_DIALECTS)}"],
        )
    ops: list[dict[str, Any]] = []
    errors: list[str] = []
    warnings: list[str] = []
    for lineno, raw in enumerate(req.source.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        matched = False
        for op, pattern in _LINE_RE.items():
            m = pattern.match(line)
            if not m:
                continue
            matched = True
            if op == "set":
                name, val = m.group(1), m.group(2).strip()
                if val.startswith('"') and val.endswith('"') and len(val) >= 2:
                    value: Any = val[1:-1]
                else:
                    try:
                        value = _num(val)
                    except ValueError:
                        errors.append(f"line {lineno}: set value must be number or quoted string")
                        break
                ops.append({"op": "set", "name": name, "value": value, "line": lineno})
            elif op in ("add", "sub"):
                ops.append({"op": op, "name": m.group(1), "value": _num(m.group(2)), "line": lineno})
            elif op == "emit":
                ops.append({"op": "emit", "message": m.group(1), "line": lineno})
            elif op == "assert":
                ops.append({"op": "assert", "name": m.group(1), "cmp": m.group(2),
                            "value": _num(m.group(3)), "line": lineno})
            break
        if not matched:
            errors.append(f"line {lineno}: syntax error: {raw.strip()!r}")
    if not ops and not errors:
        warnings.append("empty program: no operations")
    return VMCompileResponse(
        ok=not errors,
        ast={"dialect": req.dialect, "ops": ops} if not errors else None,
        errors=errors,
        warnings=warnings,
    )


def _check_cmp(actual: Any, cmp: str, expected: Any) -> bool:
    if not isinstance(actual, (int, float)) or not isinstance(expected, (int, float)):
        return False
    return {
        "==": actual == expected, "!=": actual != expected,
        ">": actual > expected, ">=": actual >= expected,
        "<": actual < expected, "<=": actual <= expected,
    }[cmp]


def simulate_ast(req: VMSimulateRequest) -> VMSimulateResponse:
    ast = req.ast or {}
    ops = ast.get("ops")
    if not isinstance(ops, list):
        return VMSimulateResponse(ok=False, errors=["ast.ops must be a list"])
    state: dict[str, Any] = dict(req.initial_state)
    events: list[dict[str, Any]] = []
    invariant_checks: list[dict[str, Any]] = []
    errors: list[str] = []
    steps = 0
    for op in ops[: req.max_steps]:
        steps += 1
        kind = op.get("op")
        try:
            if kind == "set":
                state[op["name"]] = op["value"]
            elif kind == "add":
                state[op["name"]] = state.get(op["name"], 0) + op["value"]
            elif kind == "sub":
                state[op["name"]] = state.get(op["name"], 0) - op["value"]
            elif kind == "emit":
                events.append({"step": steps, "message": op["message"], "line": op.get("line")})
            elif kind == "assert":
                passed = _check_cmp(state.get(op["name"]), op["cmp"], op["value"])
                invariant_checks.append({
                    "step": steps, "line": op.get("line"),
                    "check": f"{op['name']} {op['cmp']} {op['value']}",
                    "actual": state.get(op["name"]), "passed": passed,
                })
                if not passed:
                    errors.append(f"step {steps}: invariant failed: "
                                  f"{op['name']} {op['cmp']} {op['value']} "
                                  f"(actual={state.get(op['name'])!r})")
                    break
            else:
                errors.append(f"step {steps}: unknown op {kind!r}")
                break
        except Exception as exc:
            errors.append(f"step {steps}: {type(exc).__name__}: {exc}")
            break
    truncated = len(ops) > req.max_steps
    if truncated:
        errors.append(f"truncated at max_steps={req.max_steps}")
    return VMSimulateResponse(
        ok=not errors,
        final_state=state,
        events=events,
        invariant_checks=invariant_checks,
        errors=errors,
    )
