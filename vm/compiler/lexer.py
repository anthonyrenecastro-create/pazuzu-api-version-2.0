"""Tokenizer for the thaumic DSL (dialect "thaumic-1").

Tokens: OP_NAMES (bind, ward, scry, route, seal, banish, attune), IDENT,
NUMBER (with optional unit suffix, e.g. 10J, 2.5s), STRING, LBRACE, RBRACE,
LPAREN, RPAREN, ARROW (->), EQUALS, COMMA, SEMI, COMMENT (# to end of line),
plus KEYWORD tokens for spell/if/else/on/cost/from/to.
"""

from __future__ import annotations

from dataclasses import dataclass


OP_NAMES = ("bind", "ward", "scry", "route", "seal", "banish", "attune")
KEYWORDS = ("spell", "if", "else", "on", "cost", "from", "to")


@dataclass(frozen=True)
class Token:
    type: str      # e.g. "OP", "IDENT", "NUMBER", ...
    value: object  # str for most; (float, unit|None) for NUMBER
    line: int
    col: int


class LexError(Exception):
    """Raised on any tokenization failure, with line/col context."""


def tokenize(source: str) -> list[Token]:
    tokens: list[Token] = []
    i, line, col = 0, 1, 1
    n = len(source)

    def advance(k: int = 1) -> None:
        nonlocal i, line, col
        for _ in range(k):
            if i < n and source[i] == "\n":
                line += 1
                col = 1
            else:
                col += 1
            i += 1

    while i < n:
        c = source[i]

        # Whitespace
        if c in " \t\r\n":
            advance()
            continue

        # Comment: # ... to end of line (COMMENT token is emitted)
        if c == "#":
            start_col = col
            j = i
            while j < n and source[j] != "\n":
                j += 1
            tokens.append(Token("COMMENT", source[i:j], line, start_col))
            advance(j - i)
            continue

        # String literal (double quotes, \" and \\ escapes)
        if c == '"':
            start_col = col
            advance()  # opening quote
            buf: list[str] = []
            while i < n and source[i] != '"':
                if source[i] == "\\" and i + 1 < n and source[i + 1] in '"\\':
                    buf.append(source[i + 1])
                    advance(2)
                elif source[i] == "\n":
                    raise LexError(f"Unterminated string starting at line {line}, col {start_col}")
                else:
                    buf.append(source[i])
                    advance()
            if i >= n:
                raise LexError(f"Unterminated string starting at line {line}, col {start_col}")
            advance()  # closing quote
            tokens.append(Token("STRING", "".join(buf), line, start_col))
            continue

        # Number with optional unit suffix: 10, 2.5, 10J, 2.5s
        if c.isdigit() or (c == "." and i + 1 < n and source[i + 1].isdigit()):
            start_col = col
            j = i
            seen_dot = False
            while j < n and (source[j].isdigit() or (source[j] == "." and not seen_dot)):
                if source[j] == ".":
                    seen_dot = True
                j += 1
            num_text = source[i:j]
            k = j
            while k < n and source[k].isalpha():
                k += 1
            unit = source[j:k] or None
            try:
                value = float(num_text)
            except ValueError:
                raise LexError(f"Bad number {num_text!r} at line {line}, col {start_col}")
            tokens.append(Token("NUMBER", (value, unit), line, start_col))
            advance(k - i)
            continue

        # Identifier / op name / keyword
        if c.isalpha() or c == "_":
            start_col = col
            j = i
            while j < n and (source[j].isalnum() or source[j] == "_"):
                j += 1
            word = source[i:j]
            if word in OP_NAMES:
                ttype = "OP"
            elif word in KEYWORDS:
                ttype = "KEYWORD"
            else:
                ttype = "IDENT"
            tokens.append(Token(ttype, word, line, start_col))
            advance(j - i)
            continue

        # Multi-char operator: ->
        if c == "-" and i + 1 < n and source[i + 1] == ">":
            tokens.append(Token("ARROW", "->", line, col))
            advance(2)
            continue

        single = {
            "{": "LBRACE", "}": "RBRACE",
            "(": "LPAREN", ")": "RPAREN",
            ";": "SEMI", "=": "EQUALS", ",": "COMMA",
        }
        if c in single:
            tokens.append(Token(single[c], c, line, col))
            advance()
            continue

        raise LexError(f"Unexpected character {c!r} at line {line}, col {col}")

    tokens.append(Token("EOF", "", line, col))
    return tokens
