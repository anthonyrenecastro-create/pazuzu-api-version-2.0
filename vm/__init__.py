"""PAZUZU Virtual Mechanics subsystem.

Subpackages:
  compiler            lexer / parser / AST / effect type system
  runtime             execution engine + opcode implementations
  state               event store + invariant checkers
  topology            leyline graph (divergence, Dijkstra; NO curl)
  simulation          bounded, seeded AST runner
  formalism_registry  honesty-graded registry of source formalisms

API-contract wiring:
  compile_source(src) -> dict shaped like VMCompileResponse
      {"ok", "ast", "errors", "warnings"}
  The returned "ast" dict is consumable as VMCompileRequest.ast.

  simulate(ast, initial_state, max_steps, seed) -> dict shaped like
  VMSimulateResponse
      {"ok", "final_state", "events", "invariant_checks", "errors"}

Both functions best-effort validate against pazuzu_contracts when the
package is importable; they never hard-depend on it.
"""

from __future__ import annotations

from . import compiler, runtime, state, topology, simulation, formalism_registry
from . import constants


def _validate_contract(model_name: str, payload: dict) -> list[str]:
    try:
        from pazuzu_contracts.models import VMCompileResponse, VMSimulateResponse
    except Exception:
        return []  # contracts package not importable here; shapes still match
    model = {"VMCompileResponse": VMCompileResponse,
             "VMSimulateResponse": VMSimulateResponse}[model_name]
    try:
        model(**payload)
        return []
    except Exception as e:
        return [f"contract validation ({model_name}): {e}"]


def compile_source(source: str, dialect: str = "thaumic-1") -> dict:
    """Compile thaumic DSL source. Returns a VMCompileResponse-shaped dict."""
    from .compiler.lexer import tokenize, LexError
    from .compiler.parser import Parser, ParseError
    from .compiler.ast import validate
    from .compiler.effects import check as check_effects

    errors: list[str] = []
    warnings: list[str] = []
    ast = None
    try:
        if dialect != "thaumic-1":
            raise ParseError(f"Unsupported dialect {dialect!r} (only 'thaumic-1')")
        tokens = tokenize(source)
        ast = Parser(tokens).parse()
    except (LexError, ParseError) as e:
        errors.append(str(e))
    if ast is not None:
        for err in validate(ast):
            errors.append(f"AST: {err}")
        for v in check_effects(ast):
            if v.kind == "error":
                errors.append(f"effect: {v.message}")
            else:
                warnings.append(v.message)
    result = {
        "ok": not errors,
        "ast": ast if not errors else None,
        "errors": errors,
        "warnings": warnings,
    }
    result["errors"] += _validate_contract("VMCompileResponse", result)
    result["ok"] = not result["errors"]
    if not result["ok"]:
        result["ast"] = None
    return result


def simulate(ast: dict, initial_state: dict | None = None,
             max_steps: int = 1000, seed: int = 0,
             principal: str = "caster") -> dict:
    """Run a compiled spell AST. Returns a VMSimulateResponse-shaped dict."""
    result = simulation.run(
        ast,
        initial_state=initial_state,
        max_steps=max_steps,
        seed=seed,
        principal=principal,
    )
    result["errors"] += _validate_contract("VMSimulateResponse", result)
    result["ok"] = result["ok"] and not any(
        e.startswith("contract validation") for e in result["errors"]
    )
    return result


__all__ = [
    "compiler", "runtime", "state", "topology", "simulation",
    "formalism_registry", "constants",
    "compile_source", "simulate",
]
