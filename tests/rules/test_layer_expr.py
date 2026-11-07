# SPDX-License-Identifier: Apache-2.0
"""Layer expressions: parsing, precedence, alias expansion and rendering."""

import pytest
from ws180g_rules.layer_expr import (
    Difference,
    Intersection,
    LayerExprError,
    Name,
    Sized,
    Union,
    Unrelated,
    parse_layer_expr,
)

NAMES = {"a", "b", "c", "d", "nd", "pd", "po", "sab", "gate", "nw"}


def parse(text: str, aliases: dict[str, str] | None = None):
    return parse_layer_expr(text, aliases or {}, NAMES)


def test_constructors_take_names_as_strings():
    assert Union("a", "b") == Union(Name("a"), Name("b"))
    assert Sized("a", "rules.x") == Sized(Name("a"), "rules.x")
    assert Unrelated("a", "b") == Unrelated(Name("a"), Name("b"))


def test_name():
    assert parse("a") == Name("a")


@pytest.mark.parametrize(("text", "expected"), [
    ("a|b", Union("a", "b")),
    ("a&b", Intersection("a", "b")),
    ("a-b", Difference("a", "b")),
    # & binds tighter than -, which binds tighter than |
    ("a|b&c", Union("a", Intersection("b", "c"))),
    ("a&b|c", Union(Intersection("a", "b"), "c")),
    ("a-b&c", Difference("a", Intersection("b", "c"))),
    ("a|b-c", Union("a", Difference("b", "c"))),
    ("a-b|c", Union(Difference("a", "b"), "c")),
    # left-associative
    ("a-b-c", Difference(Difference("a", "b"), "c")),
    ("a|b|c", Union(Union("a", "b"), "c")),
    # parentheses
    ("a-(b-c)", Difference("a", Difference("b", "c"))),
    ("(a|b)&c", Intersection(Union("a", "b"), "c")),
    # postfix binds tightest
    ("a|b.sized(rules.po.x.df)", Union("a", Sized("b", "rules.po.x.df"))),
    ("(a|b).sized(rules.po.x.df)", Sized(Union("a", "b"), "rules.po.x.df")),
    ("a&b.unrelated(c)", Intersection("a", Unrelated("b", "c"))),
    ("a.unrelated(b|c)", Unrelated("a", Union("b", "c"))),
    ("a.sized(rules.x).unrelated(b)", Unrelated(Sized("a", "rules.x"), "b")),
    # whitespace ignored
    (" a | ( b & c ) . sized( rules.x ) ", Union("a", Sized(Intersection("b", "c"), "rules.x"))),
])
def test_precedence_and_parentheses(text, expected):
    assert parse(text) == expected


def test_aliases_expand_at_parse_time():
    aliases = {"df": "nd|pd", "field_po": "po-(df.sized(rules.po.x.df))"}
    assert parse("df", aliases) == Union("nd", "pd")
    assert parse("field_po", aliases) == Difference(
        "po", Sized(Union("nd", "pd"), "rules.po.x.df"))
    assert parse("df.unrelated(sab)", aliases) == Unrelated(Union("nd", "pd"), "sab")


def test_alias_cycle_raises():
    with pytest.raises(LayerExprError, match="x"):
        parse("x", {"x": "a|y", "y": "x"})


def test_unknown_name_raises_naming_it():
    with pytest.raises(LayerExprError, match="bogus"):
        parse("a|bogus")


def test_unknown_name_in_alias_raises():
    with pytest.raises(LayerExprError, match="bogus"):
        parse("df", {"df": "nd|bogus"})


@pytest.mark.parametrize("text", [
    "", "a|", "|a", "(a", "a)", "a b", "a.grow(b)", "a.sized()", "a.sized(b", "a..sized(x)",
    "a+b",
])
def test_malformed_raises(text):
    with pytest.raises(LayerExprError):
        parse(text)


def test_no_name_check_without_layer_names():
    assert parse_layer_expr("anything|else", {}, None) == Union("anything", "else")


@pytest.mark.parametrize(("expr", "text"), [
    (Union("a", "b"), "a|b"),
    (Difference("po", Sized(Union("nd", "pd"), "rules.po.x.df")),
     "po-(nd|pd).sized(rules.po.x.df)"),
    (Union("a", Union("b", "c")), "a|(b|c)"),
    (Union(Union("a", "b"), "c"), "a|b|c"),
    (Intersection(Union("a", "b"), "c"), "(a|b)&c"),
    (Unrelated(Union("nd", "pd"), "sab"), "(nd|pd).unrelated(sab)"),
])
def test_str_renders_in_the_same_syntax(expr, text):
    assert str(expr) == text
    assert parse(text) == expr


def test_str_round_trips_every_expression_in_the_data(process):
    names = set(process.layers)
    seen = 0
    for expr_text in [*process.aliases.values(),
                      *(e for rule in process.rules.values() for e in rule.layers)]:
        expr = parse_layer_expr(expr_text, process.aliases, names)
        assert parse_layer_expr(str(expr), {}, names) == expr, expr_text
        seen += 1
    assert seen > 100
