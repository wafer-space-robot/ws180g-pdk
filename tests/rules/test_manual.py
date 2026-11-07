# SPDX-License-Identifier: Apache-2.0
"""The generated design-rule manual (Task 21): Markdown from the rule table only."""

import dataclasses
import re
from decimal import Decimal
from pathlib import Path

import pytest
from ws180g_rules.manual import manual_text, write_manual
from ws180g_rules.table import RuleTable


@pytest.fixture
def table(process):
    return RuleTable.from_process(process)


def _row_line(text: str, rule_id: str) -> str:
    lines = [line for line in text.splitlines() if line.startswith(f"| `{rule_id}` |")]
    assert len(lines) == 1, (rule_id, lines)
    return lines[0]


def test_nw_w_row(table, tmp):
    out = write_manual(table, tmp / "rules.md")
    assert out == tmp / "rules.md"
    line = _row_line(out.read_text(encoding="utf-8"), "nw.w")
    assert "1.44" in line
    assert "`gf180mcu-drm/NW.1a/5v`" in line
    assert "1.200" in line  # the achieved margin, as the author recorded it
    assert "klayout, magic" in line


def test_one_row_per_rule_one_section_per_layer(table):
    text = manual_text(table)
    for row in table.rows:
        _row_line(text, row.id)
    sections = re.findall(r"^## (.+)$", text, re.MULTILINE)
    assert len(sections) == len(set(sections))
    assert sections[0] == "`nw`"
    # nw.w sits in the nw section, nd.s.pgate in the nd section
    nw = text.index("## `nw`")
    nd = text.index("## `nd`")
    assert nw < text.index("| `nw.w` |") < nd < text.index("| `nd.s.pgate` |")
    # rules with no layer come last, in their own section
    assert sections[-1] == "Whole layout"
    assert text.index("## Whole layout") < text.index("| `grid` |")


def test_columns(table):
    text = manual_text(table)
    assert ("| id | rule | value | evidence | margin applied | margin achieved | composed of "
            "| engines | condition | implied by |") in text
    line = _row_line(text, "nd.s.pgate")
    assert "`rules.sel.x`" in line  # composed-of
    implied = next(r for r in table.rows if r.implied_by)
    assert f"`{implied.implied_by}`" in _row_line(text, implied.id)
    conditioned = next(r for r in table.rows if r.condition)
    assert conditioned.condition in _row_line(text, conditioned.id)


def test_margin_reason_is_shown(table):
    row = table["nw.w"]
    reasoned = dataclasses.replace(row, margin=Decimal("1.5"),
                                   margin_reason="owner asked | for more")
    table = RuleTable(table.variant, table.layers,
                      [reasoned if r.id == "nw.w" else r for r in table.rows])
    line = _row_line(manual_text(table), "nw.w")
    assert "1.5 (owner asked \\| for more)" in line


def test_uncovered_rules_are_not_in_the_manual(table):
    assert "PL.8" not in manual_text(table)


def test_deterministic_and_dateless(table, tmp):
    a = write_manual(table, tmp / "a.md").read_bytes()
    b = write_manual(table, tmp / "b.md").read_bytes()
    assert a == b
    assert not re.search(rb"\b20\d\d-\d\d-\d\d\b", a)


def test_manual_does_not_read_the_evidence_set():
    from ws180g_rules import manual

    source = Path(manual.__file__).read_text(encoding="utf-8")
    assert "ws180g_evidence" not in source
