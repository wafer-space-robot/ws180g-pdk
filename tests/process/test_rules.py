# SPDX-License-Identifier: Apache-2.0
import re
from decimal import Decimal

import pytest
from ws180g_process.model import RuleField

# The ids of the Phase 0 rule-set table and the generation parameter (plan, shared vocabulary).
TABLE_IDS = {
    "nw.w", "nw.s", "nw.e.pd", "nw.e.nd", "nw.s.nd", "nw.s.pd",
    "df.w", "df.s", "df.s.np", "df.x.po", "df.e.co", "df.area", "nd.s.pgate", "pd.s.ngate",
    "po.w", "po.l.n", "po.l.p", "po.s", "po.x.df", "po.s.df", "po.e.co",
    "co.size", "co.s", "co.s.gate", "co.po.s.df", "co.s.butt", "co.in", "co.no.gate",
    "co.no.butt",
    "m1.w", "m1.s", "m1.e.co", "m1.e.v1", "m1.area", "v1.size", "v1.s",
    "m2.w", "m2.s", "m2.e.v1", "m2.e.v2", "m2.area", "v2.size", "v2.s",
    "m3.w", "m3.s", "m3.e.v2", "m3.e.v3", "m3.area", "v3.size", "v3.s",
    "m4.w", "m4.s", "m4.e.v3", "m4.area", "m4.e.v4", "v4.size", "v4.s",
    "mtop.w", "mtop.w.long", "mtop.s", "mtop.e.v4", "mtop.area", "mtop.v4.array",
    "pad.w", "pad.s", "mtop.e.pad",
    "sab.w", "sab.s", "sab.s.co", "sab.e.po", "sab.e.df", "po.x.sab", "df.x.sab", "sab.s.df",
    "sab.s.po", "sab.area", "sab.no.gate",
    "nsel.w", "nsel.s", "psel.w", "psel.s", "nw.tap.dmax", "ps.tap.dmax", "dnw.w", "dnw.s",
    "grid", "angle", "cut.ortho", "sel.x",
}
KLAYOUT_ONLY = {"co.s.butt", "mtop.w.long", "mtop.v4.array", "nw.tap.dmax", "ps.tap.dmax",
                "grid", "angle", "cut.ortho"}
NO_ENGINE = {"nsel.w", "nsel.s", "psel.w", "psel.s", "sel.x"}
FIXTURES = {"co.in": "co_on_field", "co.no.gate": "co_on_gate", "co.no.butt": "co_on_butt",
            "sab.no.gate": "sab_on_gate", "mtop.v4.array": "v4_array", "grid": "grid",
            "angle": "angle", "cut.ortho": "cut_ortho", "co.s.butt": "co_s_butt"}


def _names(expr: str) -> set[str]:
    """The bare layer names and aliases of a layer expression (field paths dropped)."""
    expr = re.sub(r"\.sized\([^()]*\)", "", expr).replace(".unrelated(", "|(")
    return {n for n in re.split(r"[|&\-()\s]+", expr) if n}


def test_spot_values(process):
    r = process.rules
    assert r["df.s"].value == Decimal("0.435")
    assert r["co.size"].kind == "exact-size" and r["co.size"].margin is None
    assert r["nw.tap.dmax"].engines == ["klayout"] and r["nw.tap.dmax"].margin == Decimal("1.5")
    assert r["nsel.w"].engines == []
    assert r["mtop.area"].implied_by == "rules.mtop.w"
    assert r["pad.w"].provenance == "chosen"
    assert r["mtop.w.long"].condition == "length > 800"
    assert r["sel.x"].kind == "generation" and r["sel.x"].value == Decimal("0.28")
    assert r["nd.s.pgate"].composed_of == ["gf180mcu-drm/NP.4a", "gf180mcu-drm/NP.4b",
                                           "scmos8/4.1/deep", "scmos8/4.1/subm", "rules.sel.x"]
    assert r["pd.s.ngate"].composed_of[-1] == "rules.sel.x"
    assert (r["sab.e.po"].edges, r["sab.e.po"].edge_layer) == ("sides", "po")
    assert (r["sab.e.df"].edges, r["sab.e.df"].edge_layer) == ("sides", "df")
    assert (r["po.s.df"].edges, r["po.s.df"].edge_layer) == ("exclude", "gate")
    assert r["m1.area"].margin_achieved == Decimal("1.524")
    assert r["dnw.w"].module == "deep-n-well"


def test_aliases(process):
    assert process.aliases == {"df": "nd|pd", "field_po": "po-df"}


def test_every_table_rule_is_present(process):
    assert set(process.rules) >= TABLE_IDS


def test_engines(process):
    for rid, rule in process.rules.items():
        if rid in KLAYOUT_ONLY:
            assert rule.engines == ["klayout"], rid
        elif rid in NO_ENGINE:
            assert rule.engines == [], rid
        else:
            assert rule.engines == ["klayout", "magic"], rid


def test_margins_meet_the_floor(process):
    for rid, rule in process.rules.items():
        if rule.margin is not None:
            floor = Decimal("1.25") if rule.kind == "max-distance" else Decimal("1.2")
            assert rule.margin >= floor, rid


def test_every_margined_rule_records_its_achieved_margin(process):
    for rid, rule in process.rules.items():
        if rule.evidence and rule.kind not in ("exact-size", "topology") \
                and rule.provenance != "chosen":
            assert rule.margin is not None and rule.margin_achieved is not None, rid
            assert rule.margin_achieved >= rule.margin, rid
        if rule.kind in ("exact-size", "topology") or rule.provenance == "chosen":
            assert rule.margin is None and rule.margin_achieved is None, rid


def test_values_are_on_the_grid(process):
    grid = process.grid.value
    for rid, rule in process.rules.items():
        if rule.unit == "um":
            assert rule.value % grid == 0, rid
        elif rule.unit == "um2":
            assert rule.value % Decimal("0.005") == 0, rid
        else:
            assert rule.unit is None and rule.value is None, rid


def test_every_rule_has_evidence_or_is_chosen(process):
    for rid, rule in process.rules.items():
        if rule.kind == "topology" and not rule.evidence:
            # GF180MCU topology rules carry no value, so the importer records no entry;
            # the note names the public rule instead.
            assert rule.provenance == "public-source" and "GF180MCU" in rule.note, rid
        else:
            assert rule.evidence or rule.provenance == "chosen", rid


def test_chosen_rules_say_why(process):
    for rid in ("pad.w", "pad.s"):
        rule = process.rules[rid]
        assert rule.provenance == "chosen" and rule.note and rule.evidence, rid


def test_topology_rules_have_fixtures(process):
    for rid, rule in process.rules.items():
        if rule.kind == "topology":
            assert rule.fixture and rule.value is None, rid
    assert {rid: process.rules[rid].fixture for rid in FIXTURES} == FIXTURES


def test_layers_name_known_layers_or_aliases(process):
    known = set(process.layers) | set(process.aliases)
    for rid, rule in process.rules.items():
        for expr in rule.layers:
            assert _names(expr) <= known, (rid, expr)
    for name, expr in process.aliases.items():
        assert _names(expr) <= known, name


def test_cited_evidence_exists(process, evidence):
    for rid, rule in process.rules.items():
        for eid in rule.evidence:
            assert eid in evidence.entries, (rid, eid)
        for path in rule.composed_of:
            assert path.startswith("rules.") or path in evidence.entries, (rid, path)


def test_a_topology_rule_has_no_value():
    with pytest.raises(ValueError):
        RuleField(kind="topology", layers=["co"], value=Decimal(1), unit="um",
                  variant="ws180g005", provenance="public-source", fixture="x")


def test_a_valued_rule_needs_a_unit():
    with pytest.raises(ValueError):
        RuleField(kind="min-width", layers=["co"], value=Decimal(1), variant="ws180g005",
                  provenance="derived")


def test_edges_need_an_edge_layer():
    with pytest.raises(ValueError):
        RuleField(kind="min-enclosure", layers=["sab", "po&sab"], value=Decimal("0.265"),
                  unit="um", variant="ws180g005", provenance="derived", edges="sides")


@pytest.mark.parametrize("edges", ["sides", "exclude"])
def test_edges_values_accepted(edges):
    rule = RuleField(kind="min-space", layers=["po", "df"], value=Decimal("0.36"), unit="um",
                     variant="ws180g005", provenance="derived", edges=edges, edge_layer="gate")
    assert rule.edges == edges


def test_unknown_edges_value_rejected():
    with pytest.raises(ValueError):
        RuleField(kind="min-space", layers=["po", "df"], value=Decimal("0.36"), unit="um",
                  variant="ws180g005", provenance="derived", edges="ends", edge_layer="gate")
