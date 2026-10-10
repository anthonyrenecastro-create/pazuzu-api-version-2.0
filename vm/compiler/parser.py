"""Recursive-descent parser for the thaumic DSL.

Grammar:
    program    := spell_def EOF
    spell_def  := "spell" IDENT "(" params ")" "{" stmt* "}"
    params     := (IDENT ("," IDENT)*)?
    stmt       := bind_stmt | ward_stmt | if_stmt | op_call_stmt
    bind_stmt  := "bind" IDENT "=" expr ";"
    ward_stmt  := "ward" IDENT "on" expr "cost" expr ";"
    if_stmt    := "if" "(" expr ")" block ("else" block)?
    block      := "{" stmt* "}"
    op_call    := OP_NAME "(" args ")" ";"
    args       := (expr ("," expr)*)?
    expr       := primary ("->" primary)*
    primary    := NUMBER | STRING | IDENT

"bind"/"ward" lex as OP tokens; they parse as statements when followed by
IDENT, and as op calls when followed by "(".
"""

from __future__ import annotations

from .lexer import Token, tokenize


class ParseError(Exception):
    """Raised on any syntax error, with line/col context."""


# Arity for the op-call form of each op. The bind/ward statement forms are
# sugar that the parser lowers to the same arities (bind:2, ward:3).
OP_ARITY = {
    "bind": 2,
    "ward": 3,
    "scry": 1,
    "route": 2,
    "seal": 1,
    "banish": 1,
    "attune": 2,
}


def _loc(tok: Token) -> dict:
    return {"line": tok.line, "col": tok.col}


class Parser:
    def __init__(self, tokens: list[Token]):
        # COMMENT tokens carry no grammar meaning; drop them here.
        self.tokens = [t for t in tokens if t.type != "COMMENT"]
        self.pos = 0

    # -- cursor helpers -------------------------------------------------
    def peek(self) -> Token:
        return self.tokens[self.pos]

    def next(self) -> Token:
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def expect(self, ttype: str, value: object = None) -> Token:
        tok = self.peek()
        if tok.type != ttype or (value is not None and tok.value != value):
            want = f"{ttype}" + (f" {value!r}" if value is not None else "")
            raise ParseError(
                f"Expected {want}, found {tok.type} {tok.value!r} "
                f"at line {tok.line}, col {tok.col}"
            )
        return self.next()

    def at(self, ttype: str, value: object = None) -> bool:
        tok = self.peek()
        return tok.type == ttype and (value is None or tok.value == value)

    # -- grammar --------------------------------------------------------
    def parse(self) -> dict:
        node = self.parse_spell()
        self.expect("EOF")
        return node

    def parse_spell(self) -> dict:
        kw = self.expect("KEYWORD", "spell")
        name = self.expect("IDENT")
        self.expect("LPAREN")
        params: list[str] = []
        if not self.at("RPAREN"):
            params.append(self.expect("IDENT").value)
            while self.at("COMMA"):
                self.next()
                params.append(self.expect("IDENT").value)
        self.expect("RPAREN")
        body = self.parse_block()
        return {
            "node": "spell",
            "name": name.value,
            "params": params,
            "body": body,
            "loc": _loc(kw),
        }

    def parse_block(self) -> list[dict]:
        self.expect("LBRACE")
        stmts: list[dict] = []
        while not self.at("RBRACE"):
            stmts.append(self.parse_stmt())
        self.expect("RBRACE")
        return stmts

    def parse_stmt(self) -> dict:
        tok = self.peek()
        if tok.type == "KEYWORD" and tok.value == "if":
            return self.parse_if()
        if tok.type == "OP":
            # bind/ward statement forms vs op-call form, by lookahead.
            nxt = self.tokens[self.pos + 1] if self.pos + 1 < len(self.tokens) else None
            if tok.value == "bind" and nxt is not None and nxt.type == "IDENT":
                return self.parse_bind_stmt()
            if tok.value == "ward" and nxt is not None and nxt.type == "IDENT":
                return self.parse_ward_stmt()
            return self.parse_op_call()
        raise ParseError(
            f"Expected statement, found {tok.type} {tok.value!r} "
            f"at line {tok.line}, col {tok.col}"
        )

    def parse_bind_stmt(self) -> dict:
        op = self.expect("OP", "bind")
        name = self.expect("IDENT")
        self.expect("EQUALS")
        value = self.parse_expr()
        self.expect("SEMI")
        return {"node": "bind", "name": name.value, "value": value, "loc": _loc(op)}

    def parse_ward_stmt(self) -> dict:
        op = self.expect("OP", "ward")
        name = self.expect("IDENT")
        self.expect("KEYWORD", "on")
        target = self.parse_expr()
        self.expect("KEYWORD", "cost")
        cost = self.parse_expr()
        self.expect("SEMI")
        return {
            "node": "ward",
            "name": name.value,
            "target": target,
            "cost": cost,
            "loc": _loc(op),
        }

    def parse_if(self) -> dict:
        kw = self.expect("KEYWORD", "if")
        self.expect("LPAREN")
        cond = self.parse_expr()
        self.expect("RPAREN")
        then = self.parse_block()
        otherwise: list[dict] = []
        if self.at("KEYWORD", "else"):
            self.next()
            otherwise = self.parse_block()
        return {
            "node": "if",
            "cond": cond,
            "then": then,
            "else": otherwise,
            "loc": _loc(kw),
        }

    def parse_op_call(self) -> dict:
        op = self.expect("OP")
        self.expect("LPAREN")
        args: list[dict] = []
        if not self.at("RPAREN"):
            args.append(self.parse_expr())
            while self.at("COMMA"):
                self.next()
                args.append(self.parse_expr())
        self.expect("RPAREN")
        self.expect("SEMI")
        want = OP_ARITY[op.value]
        if len(args) != want:
            raise ParseError(
                f"Op {op.value!r} takes {want} argument(s), got {len(args)} "
                f"at line {op.line}, col {op.col}"
            )
        return {"node": "op", "op": op.value, "args": args, "loc": _loc(op)}

    def parse_expr(self) -> dict:
        first = self.parse_primary()
        parts = [first]
        while self.at("ARROW"):
            self.next()
            parts.append(self.parse_primary())
        if len(parts) == 1:
            return first
        return {"node": "arrow", "parts": parts, "loc": first["loc"]}

    def parse_primary(self) -> dict:
        tok = self.peek()
        if tok.type == "NUMBER":
            self.next()
            value, unit = tok.value
            return {
                "node": "lit",
                "lit_type": "number",
                "value": value,
                "unit": unit,
                "loc": _loc(tok),
            }
        if tok.type == "STRING":
            self.next()
            return {"node": "lit", "lit_type": "string", "value": tok.value, "loc": _loc(tok)}
        if tok.type == "IDENT":
            self.next()
            return {"node": "ref", "name": tok.value, "loc": _loc(tok)}
        raise ParseError(
            f"Expected expression, found {tok.type} {tok.value!r} "
            f"at line {tok.line}, col {tok.col}"
        )


def parse(source: str) -> dict:
    """Tokenize and parse source into a typed AST dict. Raises LexError/ParseError."""
    return Parser(tokenize(source)).parse()
