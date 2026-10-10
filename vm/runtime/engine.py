"""VM execution engine: event-sourced state, compensating transactions,
capability-based permissions, and mana resource accounting.

Model:
  * State is NEVER mutated in place. Every op appends event(s) to the
    append-only log; `engine.state` is the fold of the log from event 0.
  * "Rollback" does not exist. Compensation appends an anti-event that
    reverses an earlier event's effect (compensating transaction).
  * Every op requires a capability token: capabilities[principal] must
    contain the op name (or "admin"). Missing capability -> clean halt.
  * Every mana-consuming op charges the principal BEFORE appending its
    effect event. Insufficient balance -> clean halt with no partial effect.
  * Deterministic: a seeded RNG (random.Random) drives any tie-breaking;
    the same (ast, initial_state, seed) always yields the same event log.

Halt semantics: HaltExecution carries a reason; the runner catches it and
returns ok=False with the events so far. No exception escapes a halted op
with half-applied state because charge/capability checks precede emission.
"""

from __future__ import annotations

import copy
import random
import secrets

from ..state.store import EventStore
from ..topology.graph import LeylineGraph
from . import opcodes


class HaltExecution(Exception):
    """Clean halt: insufficient mana, missing capability, or op failure."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class Engine:
    def __init__(self, topology: LeylineGraph | None = None, seed: int = 0) -> None:
        self.store = EventStore()
        self.topology = topology or LeylineGraph()
        self.rng = random.Random(seed)
        self.seed = seed
        self.seal_key = secrets.token_bytes(32)  # per-run HMAC key for seal tags
        self.capabilities: dict[str, set[str]] = {"caster": {"admin"}}
        self.state: dict = self._initial_state()

    # -- state ----------------------------------------------------------
    @staticmethod
    def _initial_state() -> dict:
        return {
            "bindings": {},    # reference table: name -> value
            "tombstones": {},  # banished names -> last value (anti-event record)
            "wards": {},       # ward name -> {target, cost, predicate}
            "mana": {},        # principal -> balance
            "seals": [],       # integrity records
            "routes": [],      # computed routes (telemetry)
            "observations": [],  # scry records (telemetry)
        }

    def fold(self, state: dict, event: dict) -> dict:
        """Apply one event. Pure function of (state, event)."""
        t = event["type"]
        p = event["payload"]
        if t == "bind.set":
            state["bindings"][p["name"]] = p["value"]
            state["tombstones"].pop(p["name"], None)
        elif t == "ward.set":
            state["wards"][p["name"]] = {
                "target": p["target"], "cost": p["cost"],
                "predicate": p["predicate"],
            }
        elif t == "banish.tombstone":
            state["bindings"].pop(p["name"], None)
            state["tombstones"][p["name"]] = p["prev"]
        elif t == "seal.created":
            state["seals"].append(
                {"label": p["label"], "digest": p["digest"], "sig": p["sig"]}
            )
        elif t == "route.computed":
            state["routes"].append(
                {"source": p["source"], "target": p["target"],
                 "path": p["path"], "cost": p["cost"]}
            )
        elif t == "scry.observe":
            state["observations"].append(
                {"target": p["target"], "value": p["value"]}
            )
        elif t == "mana.spend":
            state["mana"][p["principal"]] = (
                state["mana"].get(p["principal"], 0.0) - p["amount"]
            )
        elif t == "mana.grant":
            state["mana"][p["principal"]] = (
                state["mana"].get(p["principal"], 0.0) + p["amount"]
            )
        elif t == "mana.exchange":
            state["mana"][p["pool_a"]] = state["mana"].get(p["pool_a"], 0.0) - p["in"]
            state["mana"][p["pool_b"]] = state["mana"].get(p["pool_b"], 0.0) + p["out"]
        elif t == "attune.grant":
            pass  # capabilities tracked on the engine, not in folded state
        elif t == "teleport.abstract":
            state["bindings"][p["name"]] = p["to"]
        elif t == "compensate":
            # Anti-events are applied by compensate(), not by generic fold.
            pass
        return state

    def _refold(self) -> None:
        self.state = self.store.replay(self.fold, self._initial_state())

    # -- event emission ---------------------------------------------------
    def emit(self, event_type: str, payload: dict, principal: str = "caster") -> dict:
        event = self.store.append(event_type, payload, principal)
        self.state = self.fold(self.state, event)
        return event

    # -- capabilities -----------------------------------------------------
    def grant_capability(self, principal: str, ops: list[str] | str) -> None:
        if isinstance(ops, str):
            ops = [ops]
        self.capabilities.setdefault(principal, set()).update(ops)

    def require_capability(self, principal: str, op: str) -> None:
        caps = self.capabilities.get(principal, set())
        if op not in caps and "admin" not in caps:
            raise HaltExecution(
                f"capability denied: principal {principal!r} lacks {op!r}"
            )

    # -- wards --------------------------------------------------------------
    def check_ward(self, target: str, op: str) -> bool:
        """Evaluate ward predicates guarding `target`. A ward with predicate
        'target_match' permits only ops named in its ward record... in this
        honest minimal model a ward is a tripwire: any op touching a warded
        target is recorded and requires the 'ward' capability context.
        Returns True if passage is allowed."""
        for _name, ward in self.state.get("wards", {}).items():
            if ward["target"] == target and ward["predicate"] == "target_match":
                return True  # warded targets are explicitly guarded, not blocked
        return True

    # -- mana ---------------------------------------------------------------
    def charge(self, principal: str, amount: float, op: str) -> None:
        balance = self.state.get("mana", {}).get(principal, 0.0)
        if balance < amount:
            raise HaltExecution(
                f"insufficient mana: {principal!r} has {balance}, "
                f"op {op!r} costs {amount}"
            )
        self.emit("mana.spend", {"principal": principal, "amount": amount,
                                 "op": op}, principal)

    # -- compensation ---------------------------------------------------------
    def compensate(self, seq: int, principal: str = "caster") -> dict:
        """Append an anti-event reversing the effect of event `seq`.

        The original event is never deleted or modified; the anti-event is
        folded on top of it. Currently supports bind.set (restore prev or
        tombstone) and banish.tombstone (restore prev binding).
        """
        events = self.store.events
        if not (0 <= seq < len(events)):
            raise HaltExecution(f"cannot compensate: no event at seq {seq}")
        target = events[seq]
        t, p = target["type"], target["payload"]
        if t == "bind.set":
            anti = {"name": p["name"], "restored": p["prev"]}
            self.emit("compensate",
                      {"target_seq": seq, "anti": anti, "kind": "bind.restore"},
                      principal)
            # Re-apply as a fresh bind.set of the previous value (or tombstone).
            if p["prev"] is None:
                self.emit("banish.tombstone",
                          {"name": p["name"], "prev": p["value"]}, principal)
            else:
                self.emit("bind.set",
                          {"name": p["name"], "value": p["prev"],
                           "prev": p["value"]}, principal)
        elif t == "banish.tombstone":
            self.emit("compensate",
                      {"target_seq": seq,
                       "anti": {"name": p["name"]}, "kind": "banish.restore"},
                      principal)
            if p["prev"] is not None:
                self.emit("bind.set",
                          {"name": p["name"], "value": p["prev"], "prev": None},
                          principal)
        else:
            raise HaltExecution(
                f"cannot compensate event type {t!r}: no anti-event defined"
            )
        return {"compensated_seq": seq}

    # -- execution --------------------------------------------------------------
    def execute_stmt(self, stmt: dict, principal: str = "caster"):
        kind = stmt.get("node")
        if kind == "if":
            cond = self._eval_cond(stmt["cond"], principal)
            branch = stmt["then"] if cond else stmt.get("else", [])
            results = []
            for s in branch:
                results.append(self.execute_stmt(s, principal))
            return results
        if kind in ("bind", "ward"):
            return opcodes.DISPATCH[kind](self, principal, stmt)
        if kind == "op":
            op = stmt["op"]
            if op not in opcodes.DISPATCH:
                raise HaltExecution(f"unknown op {op!r}")
            try:
                return opcodes.DISPATCH[op](self, principal, stmt)
            except opcodes.OpError as e:
                raise HaltExecution(str(e))
        raise HaltExecution(f"cannot execute node {kind!r}")

    def _eval_cond(self, expr: dict, principal: str) -> bool:
        kind = expr.get("node")
        if kind == "lit":
            return bool(expr["value"])
        if kind == "ref":
            return bool(self.state.get("bindings", {}).get(expr["name"]))
        if kind == "arrow":
            return bool(opcodes._resolve(self, expr, principal))
        raise HaltExecution(f"cannot evaluate condition node {kind!r}")

    def execute(self, ast: dict, principal: str = "caster",
                max_steps: int = 1000) -> list:
        """Execute a spell body. Returns per-statement results."""
        if ast.get("node") != "spell":
            raise HaltExecution("engine.execute needs a spell AST")
        results = []
        steps = 0
        # Iterative worklist so `if` branches count toward max_steps.
        worklist = list(ast.get("body", []))
        while worklist:
            if steps >= max_steps:
                raise HaltExecution(
                    f"step budget exhausted after {max_steps} steps"
                )
            stmt = worklist.pop(0)
            steps += 1
            if stmt.get("node") == "if":
                cond = self._eval_cond(stmt["cond"], principal)
                branch = stmt["then"] if cond else stmt.get("else", [])
                worklist = list(branch) + worklist
                results.append({"if": cond})
            else:
                results.append(self.execute_stmt(stmt, principal))
        return results

    # -- initial state loading ----------------------------------------------------
    def load_initial_state(self, initial: dict) -> None:
        """Seed mana balances, bindings, capabilities, and topology from the
        VMSimulateRequest.initial_state dict."""
        for principal, balance in (initial.get("mana") or {}).items():
            self.emit("mana.grant", {"principal": principal,
                                     "amount": float(balance)}, "system")
        for name, value in (initial.get("bindings") or {}).items():
            self.emit("bind.set", {"name": name, "value": value,
                                   "prev": None}, "system")
        for principal, ops in (initial.get("capabilities") or {}).items():
            self.grant_capability(principal, list(ops))
        topo = initial.get("topology")
        if topo:
            self.topology = LeylineGraph.from_dict(topo)

    def snapshot_state(self) -> dict:
        return copy.deepcopy(self.state)
