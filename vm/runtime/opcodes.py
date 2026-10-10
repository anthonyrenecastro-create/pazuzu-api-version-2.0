"""Opcode implementations for the thaumic VM.

COMPUTABLE ops (honest implementations):
  bind   reference-table write            (sympathetic pointer binding, Eq 25-26)
  ward   permission-predicate install     (ward as predicate, not PH dynamics)
  route  Dijkstra shortest path on an explicit topology
  seal   SHA-256 digest + HMAC-SHA256 event signature (domain integrity tag;
         NOT a BLS/Ed25519 claim — see registry entries CRYPTO-43/64)
  banish tombstone + anti-event           (compensating transaction)
  scry   observation read of a binding    (impure: observes)
  attune capability grant after mana cost

ABSTRACT ops (named, documented stubs — NOT physical):
  teleport       moves a binding's *location label* without path traversal.
                 This is a reference-table relabeling. It is NOT physical
                 teleportation; the name is a domain label.
  mana_exchange constant-product (x*y=k) transfer between two mana pools.
                 This is a computational resource-exchange curve, NOT a market
                 and NOT a physical energy transfer.

Every op is a pure function of (engine, principal, args) that validates,
charges mana, checks capabilities, and appends event(s). State mutation
happens only through the engine's fold.
"""

from __future__ import annotations

import hashlib
import hmac

from ..topology.graph import GraphError


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _resolve(engine, expr, principal):
    """Evaluate an AST expression to a plain value."""
    kind = expr.get("node")
    if kind == "lit":
        return expr["value"]
    if kind == "ref":
        name = expr["name"]
        bindings = engine.state.get("bindings", {})
        if name not in bindings:
            raise OpError(f"Unbound name {name!r}")
        return bindings[name]
    if kind == "arrow":
        # a -> b -> c resolves left-to-right as nested lookup keys joined by "."
        parts = [_resolve(engine, p, principal) for p in expr["parts"]]
        return ".".join(str(p) for p in parts)
    raise OpError(f"Cannot evaluate expression node {kind!r}")


def _binding_name(expr) -> str:
    """A banish/scry target names a binding: a ref contributes its name,
    a string literal contributes its text. Values are never resolved here —
    these ops address the reference table itself."""
    kind = expr.get("node")
    if kind == "ref":
        return expr["name"]
    if kind == "lit" and expr.get("lit_type") == "string":
        return str(expr["value"])
    raise OpError(f"expected a binding name, got {kind!r}")


def _mana_cost_of(engine, op, stmt):
    from ..constants import MANA_COSTS
    from ..compiler.effects import _static_cost  # validated literal at check time
    if op in ("ward", "attune"):
        cost = _static_cost(stmt)
        if cost is None:
            raise OpError(f"Op {op!r} needs a static numeric cost")
        return float(cost)
    return float(MANA_COSTS[op])


class OpError(Exception):
    """Opcode failure. The engine converts these into clean halts."""


# ---------------------------------------------------------------------------
# computable ops
# ---------------------------------------------------------------------------

def op_bind(engine, principal, stmt):
    name = stmt["name"]
    value = _resolve(engine, stmt["value"], principal)
    engine.require_capability(principal, "bind")
    engine.charge(principal, _mana_cost_of(engine, "bind", stmt), "bind")
    prev = engine.state.get("bindings", {}).get(name, None)
    engine.emit("bind.set", {"name": name, "value": value, "prev": prev}, principal)
    return {"bound": name, "value": value}


def op_ward(engine, principal, stmt):
    name = stmt["name"]
    target = _resolve(engine, stmt["target"], principal)
    cost = _resolve(engine, stmt["cost"], principal)
    engine.require_capability(principal, "ward")
    engine.charge(principal, _mana_cost_of(engine, "ward", stmt), "ward")
    # A ward is a permission predicate: predicate(target, op) -> bool.
    # Stored as data; evaluated by engine.check_ward().
    engine.emit(
        "ward.set",
        {"name": name, "target": str(target), "cost": cost,
         "predicate": "target_match"},
        principal,
    )
    return {"ward": name, "target": target}


def op_scry(engine, principal, stmt):
    (target_expr,) = stmt["args"]
    target = _binding_name(target_expr)
    engine.require_capability(principal, "scry")
    engine.charge(principal, _mana_cost_of(engine, "scry", stmt), "scry")
    value = engine.state.get("bindings", {}).get(target, None)
    # Observation is impure: record that it happened (telemetry), not just the value.
    engine.emit("scry.observe", {"target": target, "value": value}, principal)
    return {"target": target, "value": value}


def op_route(engine, principal, stmt):
    src_expr, dst_expr = stmt["args"]
    src, dst = _resolve(engine, src_expr, principal), _resolve(engine, dst_expr, principal)
    engine.require_capability(principal, "route")
    engine.charge(principal, _mana_cost_of(engine, "route", stmt), "route")
    try:
        path, cost = engine.topology.dijkstra(str(src), str(dst))
    except GraphError as e:
        raise OpError(str(e))
    engine.emit(
        "route.computed",
        {"source": str(src), "target": str(dst), "path": path, "cost": cost},
        principal,
    )
    return {"path": path, "cost": cost}


def op_seal(engine, principal, stmt):
    (label_expr,) = stmt["args"]
    label = str(_resolve(engine, label_expr, principal))
    engine.require_capability(principal, "seal")
    engine.charge(principal, _mana_cost_of(engine, "seal", stmt), "seal")
    digest = hashlib.sha256(label.encode()).hexdigest()
    # Domain integrity tag: HMAC-SHA256 over (label, digest, seq) with the
    # engine's per-run key. This is tamper-evidence *within the simulation*;
    # it is not a BLS/Ed25519 signature (see registry CRYPTO-43/64).
    seq = len(engine.store)
    sig = hmac.new(
        engine.seal_key, f"{label}:{digest}:{seq}".encode(), hashlib.sha256
    ).hexdigest()
    engine.emit(
        "seal.created",
        {"label": label, "digest": digest, "sig": sig, "scheme": "HMAC-SHA256-sim"},
        principal,
    )
    return {"label": label, "digest": digest, "sig": sig}


def op_banish(engine, principal, stmt):
    name = stmt["name"] if stmt.get("node") == "bind" else None
    if stmt.get("node") == "op":
        (name_expr,) = stmt["args"]
        name = _binding_name(name_expr)
    else:
        name = stmt["name"]
    engine.require_capability(principal, "banish")
    engine.charge(principal, _mana_cost_of(engine, "banish", stmt), "banish")
    prev = engine.state.get("bindings", {}).get(name, None)
    # Tombstone + anti-event: the binding is removed by folding this event,
    # and the prior value is preserved in the log for compensation.
    engine.emit("banish.tombstone", {"name": name, "prev": prev}, principal)
    return {"banished": name, "prev": prev}


def op_attune(engine, principal, stmt):
    if stmt.get("node") == "op":
        grantee_expr, _cost_expr = stmt["args"]
        grantee = str(_resolve(engine, grantee_expr, principal))
    else:  # pragma: no cover - no attune statement form
        grantee = stmt["name"]
    cost = _mana_cost_of(engine, "attune", stmt)
    engine.require_capability(principal, "attune")
    engine.charge(principal, cost, "attune")
    granted = ["scry", "route", "bind"]
    engine.grant_capability(grantee, granted)
    engine.emit(
        "attune.grant", {"grantee": grantee, "capabilities": granted, "cost": cost},
        principal,
    )
    # Fund the new principal with a small starting balance so it can act.
    engine.emit("mana.grant", {"principal": grantee, "amount": 10.0}, principal)
    return {"grantee": grantee, "capabilities": granted}


# ---------------------------------------------------------------------------
# abstract ops (documented stubs — NOT physical)
# ---------------------------------------------------------------------------

ABSTRACT_OPS = {
    "teleport": (
        "ABSTRACT: relabels a binding's location tag without path traversal. "
        "NOT physical teleportation. Domain label only."
    ),
    "mana_exchange": (
        "ABSTRACT: constant-product (x*y=k) transfer between two mana pools. "
        "Computational resource-exchange curve, NOT a market or physical transfer."
    ),
}


def op_teleport(engine, principal, name: str, dest_label: str):
    """Abstract op: move a binding's location label.

    Honest semantics: updates the reference table's location tag for `name`.
    No path is traversed, no distance is crossed. NOT teleportation.
    """
    engine.require_capability(principal, "teleport")
    bindings = engine.state.get("bindings", {})
    if name not in bindings:
        raise OpError(f"Unbound name {name!r}")
    engine.emit(
        "teleport.abstract",
        {"name": name, "from": bindings[name], "to": dest_label,
         "note": "label move only; not physical"},
        principal,
    )
    return {"name": name, "location": dest_label}


def op_mana_exchange(engine, principal, pool_a: str, pool_b: str, amount_in: float):
    """Abstract op: constant-product AMM exchange between two mana pools.

    x*y=k invariant on (pool_a, pool_b); amount_in leaves pool_a, the curve
    determines what arrives in pool_b. Computational model only.
    """
    engine.require_capability(principal, "mana_exchange")
    mana = engine.state.get("mana", {})
    xa = float(mana.get(pool_a, 0.0))
    xb = float(mana.get(pool_b, 0.0))
    if amount_in <= 0 or amount_in > xa:
        raise OpError("insufficient pool_a balance for exchange")
    k = xa * xb
    new_xa = xa - amount_in
    new_xb = k / new_xa if new_xa > 0 else xb
    out = new_xb - xb
    engine.emit(
        "mana.exchange",
        {"pool_a": pool_a, "pool_b": pool_b, "in": amount_in, "out": out,
         "k": k, "note": "constant-product curve; computational only"},
        principal,
    )
    return {"in": amount_in, "out": out, "k": k}


DISPATCH = {
    "bind": op_bind,
    "ward": op_ward,
    "scry": op_scry,
    "route": op_route,
    "seal": op_seal,
    "banish": op_banish,
    "attune": op_attune,
}
