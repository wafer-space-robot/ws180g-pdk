# SPDX-License-Identifier: Apache-2.0
"""Layer expressions of the rule set: an immutable algebra, its parser and its rendering.

Syntax (the vocabulary's "Layer expressions"): a layer name or alias; `a|b` union; `a&b`
intersection; `a-b` difference; `a.sized(<field path>)` sizing by the value of a process
field; `a.unrelated(b)` the shapes of `a` not interacting with `b`. The postfix calls bind
tightest, then `&`, then `-`, then `|`; binary operators are left-associative, parentheses
group, whitespace is ignored. Aliases are expanded at parse time, so a parsed expression holds
layer names only. `str(expr)` renders the same syntax with the fewest parentheses, and
`parse_layer_expr(str(e), {}, names) == e`.

This module only describes expressions; evaluating them on a layout is the deck generators'
job.
"""

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass


class LayerExprError(ValueError):
    """A malformed layer expression, an unknown name or an alias cycle."""


def _expr(value: "LayerExpr | str") -> "LayerExpr":
    return Name(value) if isinstance(value, str) else value


class LayerExpr:
    """Base of the expression nodes. `_PREC` orders the binding strength for rendering."""

    _PREC = 0

    def names(self) -> list[str]:
        """The layer names in the expression, left to right, repeats kept."""
        raise NotImplementedError

    def _wrap(self, prec: int) -> str:
        text = str(self)
        return f"({text})" if self._PREC < prec else text


@dataclass(frozen=True)
class Name(LayerExpr):
    name: str
    _PREC = 5

    def names(self) -> list[str]:
        return [self.name]

    def __str__(self) -> str:
        return self.name


@dataclass(frozen=True)
class _Binary(LayerExpr):
    a: LayerExpr
    b: LayerExpr
    _OP = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "a", _expr(self.a))
        object.__setattr__(self, "b", _expr(self.b))

    def names(self) -> list[str]:
        return [*self.a.names(), *self.b.names()]

    def __str__(self) -> str:
        # left-associative: the right operand needs parentheses at equal strength
        return f"{self.a._wrap(self._PREC)}{self._OP}{self.b._wrap(self._PREC + 1)}"


@dataclass(frozen=True)
class Union(_Binary):
    _PREC = 1
    _OP = "|"


@dataclass(frozen=True)
class Difference(_Binary):
    _PREC = 2
    _OP = "-"


@dataclass(frozen=True)
class Intersection(_Binary):
    _PREC = 3
    _OP = "&"


@dataclass(frozen=True)
class Sized(LayerExpr):
    """`expr` sized by the value of the process field at the dotted path `field`; the path is
    kept, its value is read when a deck is generated."""

    expr: LayerExpr
    field: str
    _PREC = 4

    def __post_init__(self) -> None:
        object.__setattr__(self, "expr", _expr(self.expr))

    def names(self) -> list[str]:
        return self.expr.names()

    def __str__(self) -> str:
        return f"{self.expr._wrap(self._PREC)}.sized({self.field})"


@dataclass(frozen=True)
class Unrelated(LayerExpr):
    """The shapes of `a` that do not interact with `b`."""

    a: LayerExpr
    b: LayerExpr
    _PREC = 4

    def __post_init__(self) -> None:
        object.__setattr__(self, "a", _expr(self.a))
        object.__setattr__(self, "b", _expr(self.b))

    def names(self) -> list[str]:
        return [*self.a.names(), *self.b.names()]

    def __str__(self) -> str:
        return f"{self.a._wrap(self._PREC)}.unrelated({self.b})"


_TOKEN = re.compile(r"\s*(?:(?P<name>[A-Za-z_][A-Za-z0-9_]*)|(?P<op>[|&\-().]))")
_FIELD = re.compile(r"\s*(?P<field>[A-Za-z_][A-Za-z0-9_.\-]*?)\s*\)")
_BINARY = {"|": Union, "-": Difference, "&": Intersection}
_LEVELS = ["|", "-", "&"]  # loosest first


class _Parser:
    def __init__(self, text: str, aliases: Mapping[str, str], names: set[str] | None,
                 expanding: tuple[str, ...]) -> None:
        self.text, self.aliases, self.layer_names = text, aliases, names
        self.expanding, self.pos = expanding, 0

    def fail(self, why: str) -> LayerExprError:
        return LayerExprError(f"{why} at position {self.pos} of {self.text!r}")

    def peek(self) -> tuple[str, str] | None:
        match = _TOKEN.match(self.text, self.pos)
        if match is None:
            if self.text[self.pos:].strip():
                raise self.fail(f"unexpected {self.text[self.pos:].strip()[0]!r}")
            return None
        return ("name", match["name"]) if match["name"] else ("op", match["op"])

    def take(self) -> tuple[str, str]:
        token = self.peek()
        if token is None:
            raise self.fail("unexpected end")
        self.pos = _TOKEN.match(self.text, self.pos).end()
        return token

    def expect(self, op: str) -> None:
        if self.take() != ("op", op):
            raise self.fail(f"expected {op!r}")

    def parse(self) -> LayerExpr:
        expr = self.binary(0)
        if self.peek() is not None:
            raise self.fail(f"unexpected {self.peek()[1]!r}")
        return expr

    def binary(self, level: int) -> LayerExpr:
        if level == len(_LEVELS):
            return self.postfix()
        op = _LEVELS[level]
        expr = self.binary(level + 1)
        while self.peek() == ("op", op):
            self.take()
            expr = _BINARY[op](expr, self.binary(level + 1))
        return expr

    def postfix(self) -> LayerExpr:
        expr = self.atom()
        while self.peek() == ("op", "."):
            self.take()
            kind, method = self.take()
            self.expect("(")
            if (kind, method) == ("name", "sized"):
                match = _FIELD.match(self.text, self.pos)
                if match is None:
                    raise self.fail("expected a field path and ')'")
                self.pos = match.end()
                expr = Sized(expr, match["field"])
            elif (kind, method) == ("name", "unrelated"):
                expr = Unrelated(expr, self.binary(0))
                self.expect(")")
            else:
                raise self.fail(f"unknown call {method!r}: expected sized or unrelated")
        return expr

    def atom(self) -> LayerExpr:
        kind, value = self.take()
        if (kind, value) == ("op", "("):
            expr = self.binary(0)
            self.expect(")")
            return expr
        if kind != "name":
            raise self.fail(f"unexpected {value!r}")
        if value in self.aliases:
            if value in self.expanding:
                raise LayerExprError(
                    f"alias cycle {' -> '.join([*self.expanding, value])}")
            return _Parser(self.aliases[value], self.aliases, self.layer_names,
                           (*self.expanding, value)).parse()
        if self.layer_names is not None and value not in self.layer_names:
            raise self.fail(f"unknown layer {value!r}")
        return Name(value)


def parse_layer_expr(text: str, aliases: Mapping[str, str],
                     layer_names: Iterable[str] | None) -> LayerExpr:
    """Parse `text`, expanding `aliases`; a name that is neither an alias nor in `layer_names`
    raises `LayerExprError` naming it (`layer_names=None` accepts any name)."""
    names = None if layer_names is None else set(layer_names)
    return _Parser(text, aliases, names, ()).parse()
