"""AST node helpers, validation, and pretty-printing for the thaumic DSL.

Node shapes (all dicts):
  spell: {"node":"spell","name":str,"params":[str],"body":[stmt],"loc":{...}}
  bind:  {"node":"bind","name":str,"value":expr,"loc":{...}}
  ward:  {"node":"ward","name":str,"target":expr,"cost":expr,"loc":{...}}
  op:    {"node":"op","op":str,"args":[expr],"loc":{...}}
  if:    {"node":"if","cond":expr,"then":[stmt],"else":[stmt],"loc":{...}}
  lit:   {"node":"lit","lit_type":"number"|"string","value":...,"unit":...?,"loc":{...}}
  ref:   {"node":"ref","name":str,"loc":{...}}
  arrow: {"node":"arrow","parts":[expr],"loc":{...}}
"""

from __future__ import annotations

from .lexer import OP_NAMES
from .parser import OP_ARITY


class ASTError(Exception):
    """Semantic validation failure on an otherwise well-formed AST."""


def _loc_str(loc: dict | None) -> str:
    if not loc:
        return "<unknown>"
    return f"line {loc.get('line', '?')}, col {loc.get('col', '?')}"


def walk(node: dict):
    """Yield every node in the AST (pre-order)."""
    yield node
    kind = node.get("node")
    if kind == "spell":
        for s in node.get("body", []):
            yield from walk(s)
    elif kind in ("bind",):
        yield from walk(node["value"])
    elif kind == "ward":
        yield from walk(node["target"])
        yield from walk(node["cost"])
    elif kind == "op":
        for a in node.get("args", []):
            yield from walk(a)
    elif kind == "if":
        yield from walk(node["cond"])
        for s in node.get("then", []):
            yield from walk(s)
        for s in node.get("else", []):
            yield from walk(s)
    elif kind == "arrow":
        for p in node.get("parts", []):
            yield from walk(p)


def validate(ast: dict) -> list[str]:
    """Return a list of semantic error strings (empty == valid).

    Checks: root is a spell; every op name known; op arity correct
    (belt-and-braces with the parser); statement/expression shapes sane.
    """
    errors: list[str] = []

    if not isinstance(ast, dict) or ast.get("node") != "spell":
        return ["AST root must be a spell node"]

    for node in walk(ast):
        kind = node.get("node")
        loc = _loc_str(node.get("loc"))
        if kind == "op":
            op = node.get("op")
            if op not in OP_NAMES:
                errors.append(f"Unknown op {op!r} at {loc}")
                continue
            want = OP_ARITY[op]
            got = len(node.get("args", []))
            if got != want:
                errors.append(
                    f"Op {op!r} takes {want} argument(s), got {got} at {loc}"
                )
        elif kind == "bind":
            if not isinstance(node.get("name"), str):
                errors.append(f"bind needs a name at {loc}")
        elif kind == "ward":
            if not isinstance(node.get("name"), str):
                errors.append(f"ward needs a name at {loc}")
        elif kind == "lit":
            if node.get("lit_type") not in ("number", "string"):
                errors.append(f"Bad literal type at {loc}")
        elif kind == "ref":
            if not isinstance(node.get("name"), str):
                errors.append(f"Bad ref at {loc}")
        elif kind == "arrow":
            if len(node.get("parts", [])) < 2:
                errors.append(f"arrow needs >= 2 parts at {loc}")
        elif kind in ("spell", "if"):
            pass
        else:
            errors.append(f"Unknown AST node kind {kind!r} at {loc}")
    return errors


def _expr_str(e: dict) -> str:
    kind = e.get("node")
    if kind == "lit":
        if e.get("lit_type") == "number":
            unit = e.get("unit") or ""
            v = e["value"]
            return f"{int(v) if float(v).is_integer() else v}{unit}"
        return f"\"{e['value']}\""
    if kind == "ref":
        return e["name"]
    if kind == "arrow":
        return " -> ".join(_expr_str(p) for p in e["parts"])
    return f"<{kind}>"


def pretty(ast: dict, indent: int = 0) -> str:
    """Render the AST back to canonical thaumic source."""
    pad = "  " * indent
    kind = ast.get("node")
    if kind == "spell":
        params = ", ".join(ast["params"])
        body = "\n".join(pretty(s, indent + 1) for s in ast["body"])
        return f"{pad}spell {ast['name']}({params}) {{\n{body}\n{pad}}}"
    if kind == "bind":
        return f"{pad}bind {ast['name']} = {_expr_str(ast['value'])};"
    if kind == "ward":
        return (
            f"{pad}ward {ast['name']} on {_expr_str(ast['target'])} "
            f"cost {_expr_str(ast['cost'])};"
        )
    if kind == "op":
        args = ", ".join(_expr_str(a) for a in ast["args"])
        return f"{pad}{ast['op']}({args});"
    if kind == "if":
        then = "\n".join(pretty(s, indent + 1) for s in ast["then"])
        out = f"{pad}if ({_expr_str(ast['cond'])}) {{\n{then}\n{pad}}}"
        if ast.get("else"):
            els = "\n".join(pretty(s, indent + 1) for s in ast["else"])
            out += f" else {{\n{els}\n{pad}}}"
        return out
    return f"{pad}<{kind}>"


def spell_names(ast: dict) -> list[str]:
    """Names bound by top-level bind statements (for tooling)."""
    return [s["name"] for s in ast.get("body", []) if s.get("node") == "bind"]
