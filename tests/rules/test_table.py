# SPDX-License-Identifier: Apache-2.0
"""The rule table: the machine-readable view of the rule fields of the process description."""

import csv
import json
from decimal import Decimal

import pytest
from ws180g_rules.layer_expr import (
    Difference,
    Intersection,
    LayerExprError,
    Name,
    Sized,
    Union,
    Unrelated,
)
from ws180g_rules.table import CSV_COLUMNS, RuleTable, main

# rules.toml holds 89 rules, every one of variant ws180g005.
RULE_COUNT = 89


@pytest.fixture
def table(process):
    return RuleTable.from_process(process)


def test_row_count_equals_the_ws180g005_rules(process, table):
    expected = [r for r in process.rules.values() if r.variant == "ws180g005"]
    assert len(table.rows) == len(expected) == RULE_COUNT


def test_aliases_expanded(table):
    assert table["df.w"].layers[0] == Union("nd", "pd")
    assert table["po.s.df"].layers[0] == Difference(
        "po", Union("nd", "pd"))
    assert table["sab.s.df"].layers[1] == Unrelated(Union("nd", "pd"), "sab")


def test_composite_expression(table):
    gate_nw = Intersection("gate", "nw")
    assert table["nd.s.pgate"].layers == [
        Name("nd"),
        Union(gate_nw, Intersection("po", Sized(gate_nw, "rules.po.x.df"))),
    ]


def test_row_fields_copied_from_the_rule(process, table):
    row, rule = table["mtop.area"], process.rules["mtop.area"]
    assert row.id == "mtop.area"
    assert row.field == "rules.mtop.area"
    assert (row.kind, row.value, row.unit, row.variant) == ("min-area", Decimal("0.845"),
                                                            "um2", "ws180g005")
    assert row.evidence == rule.evidence
    assert row.margin == rule.margin
    assert row.margin_achieved == Decimal("1.502")
    assert row.implied_by == "rules.mtop.w"
    assert row.engines == ["klayout", "magic"]
    assert row.text == rule.note


def test_unknown_key_raises(table):
    with pytest.raises(KeyError, match="no.such"):
        table["no.such"]


def test_unknown_layer_raises(process):
    rules = dict(process.rules)
    rules["nw.w"] = rules["nw.w"].model_copy(update={"layers": ["nw|bogus"]})
    with pytest.raises(LayerExprError, match="bogus"):
        RuleTable.from_process(process.model_copy(update={"rules": rules}))


def test_unknown_variant_raises(process):
    with pytest.raises(KeyError, match="ws180g999"):
        RuleTable.from_process(process, variant="ws180g999")


def test_stable_order(process, table):
    again = RuleTable.from_process(process)
    assert [r.id for r in again.rows] == [r.id for r in table.rows]
    order = list(process.layers)

    def key(row):
        first = row.layers[0].names()[0] if row.layers else None
        return (order.index(first) if first else len(order), row.id)

    assert [r.id for r in table.rows] == [r.id for r in sorted(table.rows, key=key)]
    assert table.rows[0].id.startswith("nw.")
    assert [r.id for r in table.rows[-2:]] == ["angle", "grid"]  # no layers: last


def test_generation_rows_kept_without_engines(table):
    assert table["sel.x"].kind == "generation"
    assert table["sel.x"].engines == []


def test_checkable(table):
    ids = {r.id for r in table.checkable()}
    assert "nsel.w" not in ids
    assert "sel.x" not in ids
    assert "nw.w" in ids
    assert all(r.engines for r in table.checkable())


def test_with_fail_fixture(table):
    ids = {r.id for r in table.with_fail_fixture()}
    assert "mtop.area" not in ids
    assert "mtop.w" in ids
    assert ids <= {r.id for r in table.checkable()}
    assert all(r.implied_by is None for r in table.with_fail_fixture())


def test_variant_filter(process, table):
    big = RuleTable.from_process(process, variant="ws180g135")
    assert big.variant == "ws180g135"
    by_id = {r.id: r for r in big.rows}
    for row in table.rows:
        assert by_id[row.id] == row


def test_variant_filter_excludes_other_variants(process):
    rules = dict(process.rules)
    rules["nw.w"] = rules["nw.w"].model_copy(update={"variant": "ws180g035"})
    changed = process.model_copy(update={"rules": rules})
    assert "nw.w" not in {r.id for r in RuleTable.from_process(changed).rows}
    assert "nw.w" in {r.id for r in RuleTable.from_process(changed, variant="ws180g135").rows}
    assert "nw.w" not in {
        r.id for r in RuleTable.from_process(changed, variant="ws180g105").rows}


def test_json_round_trip(table, tmp):
    path = tmp / "rules.json"
    table.write_json(path)
    again = RuleTable.read_json(path)
    assert again == table
    data = json.loads(path.read_text(encoding="utf-8"))
    row = next(r for r in data["rows"] if r["id"] == "po.s.df")
    assert row["layers"][0] == "po-(nd|pd)"
    assert row["value"] == str(table["po.s.df"].value)
    assert set(data) == {"variant", "layers", "rows"}  # no timestamp


def test_json_is_deterministic(table, tmp):
    table.write_json(tmp / "a.json")
    table.write_json(tmp / "b.json")
    assert (tmp / "a.json").read_bytes() == (tmp / "b.json").read_bytes()


def test_csv(table, tmp):
    path = tmp / "rules.csv"
    table.write_csv(path)
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    assert reader.fieldnames == CSV_COLUMNS
    assert CSV_COLUMNS[:6] == ["id", "kind", "layers", "value", "unit", "field"]
    assert len(rows) == RULE_COUNT
    row = next(r for r in rows if r["id"] == "sab.s.df")
    assert row["layers"] == "sab (nd|pd).unrelated(sab)"
    assert row["field"] == "rules.sab.s.df"


def test_console_script(tmp, capsys):
    assert main(["--json", str(tmp / "out" / "t.json"), "--csv", str(tmp / "out" / "t.csv")]) == 0
    assert (tmp / "out" / "t.json").is_file()
    assert (tmp / "out" / "t.csv").is_file()
    assert f"{RULE_COUNT} rules" in capsys.readouterr().out
