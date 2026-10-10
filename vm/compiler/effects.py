"""Effect type system for the thaumic DSL.

Each op declares purity plus a set of effect tags:
  reads_state, writes_state, observes, consumes_mana.

The checker enforces:
  * unknown op            -> error
  * wrong arity           -> error (mirrors parser; ASTs can be hand-built)
  * consumes_mana ops     -> the mana cost must be a statically-known
                             non-negative numeric literal (no dynamic costs,
                             so resource use is auditable before execution)
  * pure contexts         -> `if` guards are pure by construction (expressions
                             contain no op calls); assert_pure() is the hook
                             that future DSL extensions must pass through.

Effect tags per op (honest classification):
  bind   impure  {writes_state, consumes_mana}              -- reference table write
  ward   impure  {reads_state, writes_state, consumes_mana} -- permission predicate install
  scry   impure  {reads_state, observes}                    -- observation; divination is impure
  route  impure  {reads_state}                              -- reads mutable topology
  seal   impure  {writes_state, consumes_mana}              -- integrity record
  banish impure  {writes_state, consumes_mana}              -- tombstone + anti-event
  attune impure  {writes_state, consumes_mana}              -- capability grant
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .lexer import OP_NAMES
from .parser import OP_ARITY
from .ast import walk


# op -> (is_pure, frozenset(effect tags))
EFFECTS: dict[str, tuple[bool, frozenset[str]]] = {
    "bind": (False, frozenset({"writes_state", "consumes_mana"})),
    "ward": (False, frozenset({"reads_state", "writes_state", "consumes_mana"})),
    "scry": (False, frozenset({"reads_state", "observes"})),
    "route": (False, frozenset({"reads_state"})),
    "seal": (False, frozenset({"writes_state", "consumes_mana"})),
    "banish": (False, frozenset({"writes_state", "consumes_mana"})),
    "attune": (False, frozenset({"writes_state", "consumes_mana"})),
}

PURE_OPS = frozenset(op for op, (pure, _) in EFFECTS.items() if pure)


@dataclass
class EffectViolation:
    kind: str      # "error" or "warning"
    message: str
    loc: dict = field(default_factory=dict)


def classify(op: str) -> tuple[bool, frozenset[str]]:
    """Return (is_pure, effect_tags) for an op name. Raises KeyError if unknown."""
    return EFFECTS[op]


def effects_of_stmt(stmt: dict) -> frozenset[str]:
    """Union of effect tags for a statement (recurses into if-branches)."""
    tags: set[str] = set()
    kind = stmt.get("node")
    if kind == "bind":
        tags |= set(EFFECTS["bind"][1])
    elif kind == "ward":
        tags |= set(EFFECTS["ward"][1])
    elif kind == "op":
        _, op_tags = EFFECTS[stmt["op"]]
        tags |= set(op_tags)
    elif kind == "if":
        for s in stmt.get("then", []) + stmt.get("else", []):
            tags |= set(effects_of_stmt(s))
    return frozenset(tags)


def _static_cost(stmt: dict) -> float | None:
    """Extract the mana cost literal for consumes_mana ops.

    bind/scry/route/seal/banish: fixed schedule from constants.MANA_COSTS.
    ward: cost expression must be a non-negative number literal.
    attune: second arg must be a non-negative number literal.
    Returns None when the cost is not statically known.
    """
    from ..constants import MANA_COSTS

    kind = stmt.get("node")
    if kind == "op":
        op = stmt["op"]
        if op == "attune":
            arg = stmt["args"][1]
            if arg.get("node") == "lit" and arg.get("lit_type") == "number":
                return float(arg["value"])
            return None
        return MANA_COSTS.get(op)
    if kind == "bind":
        return MANA_COSTS["bind"]
    if kind == "ward":
        cost = stmt["cost"]
        if cost.get("node") == "lit" and cost.get("lit_type") == "number":
            return float(cost["value"])
        return None
    return None


def assert_pure(node: dict) -> None:
    """Reject impure constructs in a pure context.

    Expressions are pure by construction (no op calls can appear inside
    them), so this currently always passes for `if` guards; it exists as
    the enforcement hook for future DSL extensions.
    """
    for sub in walk(node):
        if sub.get("node") == "op":
            _, tags = EFFECTS[sub["op"]]
            if "observes" in tags or "writes_state" in tags:
                loc = sub.get("loc", {})
                raise EffectViolation(
                    "error",
                    f"Impure op {sub['op']!r} in pure context",
                    loc,
                )


def check(ast: dict) -> list[EffectViolation]:
    """Type-check effects over the whole spell. Returns violations."""
    out: list[EffectViolation] = []
    if not isinstance(ast, dict) or ast.get("node") != "spell":
        return [EffectViolation("error", "AST root must be a spell node")]

    for node in walk(ast):
        kind = node.get("node")
        loc = node.get("loc", {})
        if kind == "op":
            op = node.get("op")
            if op not in OP_NAMES:
                out.append(EffectViolation("error", f"Unknown op {op!r}", loc))
                continue
            want = OP_ARITY[op]
            if len(node.get("args", [])) != want:
                out.append(
                    EffectViolation(
                        "error",
                        f"Op {op!r} takes {want} argument(s), "
                        f"got {len(node.get('args', []))}",
                        loc,
                    )
                )
        elif kind == "if":
            try:
                assert_pure(node["cond"])
            except EffectViolation as v:  # pragma: no cover - hook for extensions
                out.append(v)

    # Mana discipline: every consumes_mana statement needs a statically-known
    # non-negative cost.
    for node in walk(ast):
        kind = node.get("node")
        if kind not in ("bind", "ward", "op"):
            continue
        opname = node["op"] if kind == "op" else kind
        _, tags = EFFECTS[opname]
        if "consumes_mana" not in tags:
            continue
        cost = _static_cost(node)
        loc = node.get("loc", {})
        if cost is None:
            out.append(
                EffectViolation(
                    "error",
                    f"Op {opname!r} consumes mana but its cost is not a "
                    "statically-known numeric literal",
                    loc,
                )
            )
        elif cost < 0:
            out.append(
                EffectViolation(
                    "error", f"Op {opname!r} has negative mana cost {cost}", loc
                )
            )
    return out


def check_strict(ast: dict) -> None:
    """Raise on the first error-level violation."""
    for v in check(ast):
        if v.kind == "error":
            loc = v.loc
            where = (
                f" at line {loc.get('line')}, col {loc.get('col')}"
                if loc
                else ""
            )
            raise EffectViolation(f"error", v.message + where)
