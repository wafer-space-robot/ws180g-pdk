# SPDX-License-Identifier: Apache-2.0
import json
import re
import subprocess
from decimal import Decimal

import pytest
from helpers import set_toml
from ws180g_evidence.report import margin_report
from ws180g_process.load import load_process


def _rules(data_copy):
    return data_copy / "rules.toml"


@pytest.fixture
def process_with_m1_w_0_35(data_copy):
    set_toml(_rules(data_copy), ["rules", '"m1.w"', "value"], 0.35)
    return load_process(data_copy)


@pytest.fixture
def process_citing_nonexistent_id(data_copy):
    path = _rules(data_copy)
    text = path.read_text()
    assert '"xc018/metal1/width"' in text
    path.write_text(text.replace('"xc018/metal1/width"', '"xc018/metal1/nosuch"', 1))
    return load_process(data_copy)


@pytest.fixture
def process_with_tap_dmax_15(data_copy):
    set_toml(_rules(data_copy), ["rules", '"nw.tap.dmax"', "value"], 15)
    return load_process(data_copy)


@pytest.fixture
def process_with_m1_w_margin_1_0_and_reason(data_copy):
    # The loader rejects a margin below the 1.2 floor, so the field is changed after
    # loading: the report checks the floor again on whatever it is given.
    process = load_process(data_copy)
    rule = process.rules["m1.w"]
    process.rules["m1.w"] = rule.model_copy(
        update={"margin": Decimal("1.0"), "margin_reason": "test: a margin below the floor"})
    return process


@pytest.fixture
def process_with_m1_w_achieved_2_0(data_copy):
    set_toml(_rules(data_copy), ["rules", '"m1.w"', "margin_achieved"], 2.0)
    return load_process(data_copy)


@pytest.fixture
def process_with_v1_size_0_26(data_copy):
    set_toml(_rules(data_copy), ["rules", '"v1.size"', "value"], 0.26)
    return load_process(data_copy)


def test_metal1_width_takes_subm_mapping(report):
    row = report["rules.m1.w"]
    assert row.bound == Decimal("0.30") and row.margin_achieved == Decimal("1.2") and row.status == "ok"


def test_margin_required_is_computed(report):
    assert report["rules.df.area"].single_source and report["rules.df.area"].margin_required == Decimal("1.5")
    assert report["rules.nw.w"].margin_required == Decimal("1.2")
    assert report["rules.nw.tap.dmax"].margin_required == Decimal("1.5") and report["rules.nw.tap.dmax"].margin_achieved == Decimal("1.5")


def test_composed_rule(report):
    assert report["rules.nd.s.pgate"].status == "ok"      # 0.665 - 0.28 = 0.385 >= 1.2 x 0.32
    assert report["rules.nd.s.pgate"].margin_achieved == Decimal("1.203")


def test_under_margin_detected(process_with_m1_w_0_35, evidence):
    assert margin_report(process_with_m1_w_0_35, evidence)["rules.m1.w"].status == "under-margin"


def test_missing_entry_detected(process_citing_nonexistent_id, evidence):
    r = margin_report(process_citing_nonexistent_id, evidence)
    assert r["rules.m1.w"].status == "missing-entry" and r.ok is False


def test_uncovered_lists_density_and_antenna(report):
    ids = {e.id for e in report.uncovered}
    assert {"gf180mcu-drm/PL.8/5v", "gf180mcu-drm/ANT.1", "gf180mcu-drm/LU.1/mv/a"} <= ids
    assert "gf180mcu-drm/CO.5a" not in ids          # cited by co.s.butt
    assert "gf180mcu-drm/CO.6/d" not in ids         # a guideline never binds
    assert all(e.value is not None and not e.guideline for e in report.uncovered)
    assert "gf180mcu-drm/NW.1a/3v3" in {e.id for e in report.out_of_scope}


def test_maximum_uses_ratio(process_with_tap_dmax_15, evidence):
    assert margin_report(process_with_tap_dmax_15, evidence)["rules.nw.tap.dmax"].status == "under-margin"   # ratio 1.0 < 1.5


def test_stack_rows(report):
    row = report["stack.metals.mtop.thickness.min"]
    assert row.status == "ok" and row.margin_required == Decimal("1.2") and "3.2" in row.margin_reason
    assert row.margin_achieved == Decimal("1.2")                       # 0.9 / 0.75
    assert report["stack.metals.mtop.thickness.max"].margin_achieved == Decimal("1.2")   # 3.6 / 3.0
    assert report["stack.oxides.5v0.thickness.min"].status == "ok"
    assert report["stack.oxides.5v0.vt_p.min"].status == "ok"          # compared as magnitudes
    assert report["stack.metals.m1.sheet_rho.max"].margin_required == Decimal("1.5")


def test_override_floor(process_with_m1_w_margin_1_0_and_reason, evidence):
    r = margin_report(process_with_m1_w_margin_1_0_and_reason, evidence)
    assert r["rules.m1.w"].status == "override-too-small" and r.ok is False


def test_achieved_mismatch(process_with_m1_w_achieved_2_0, evidence):
    r = margin_report(process_with_m1_w_achieved_2_0, evidence)
    assert r["rules.m1.w"].status == "achieved-mismatch" and r.ok is False


def test_achieved_rounding(report):
    assert report["rules.m1.area"].margin_achieved == Decimal("1.524")   # 0.22 / 0.1444, rounded to 0.001


def test_exact_size_mismatch_is_under_margin(report, process_with_v1_size_0_26, evidence):
    assert report["rules.v1.size"].status == "exempt" and report["rules.v1.size"].bound == Decimal("0.27")
    assert report["rules.v1.size"].margin_required is None
    r = margin_report(process_with_v1_size_0_26, evidence)
    assert r["rules.v1.size"].status == "under-margin" and r.ok is False


def test_topology_without_evidence_is_exempt(report):
    assert report["rules.co.no.gate"].status == "exempt" and report["rules.co.no.gate"].cited == []
    assert report["rules.co.in"].status == "exempt"                    # cites values, no margin


def test_chosen_and_implied(report):
    assert report["rules.pad.w"].status == "chosen" and report["rules.pad.w"].bound is None
    assert {e.id for e in report["rules.pad.w"].informative} >= {"gf180mcu-drm/PAD.1/ball"}
    row = report["rules.mtop.area"]
    assert row.status == "implied" and row.margin_achieved == Decimal("1.502")
    assert report["rules.sel.x"].status == "ok" and report["rules.sel.x"].margin_achieved == Decimal("1.217")


def test_grid_and_sources(report):
    assert report.grid_ok
    sources = {s.id: s for s in report.sources}
    assert sources["onc18"].transcribed is False and sources["gf180mcu-drm"].transcribed
    assert "registered, not yet transcribed" in report.to_markdown()


def test_full_report_ok(report):
    assert report.ok and report.grid_ok, [(r.field, r.status) for r in report.rows if r.status in (
        "under-margin", "missing-entry", "override-too-small", "achieved-mismatch")]


def test_markdown_has_no_timestamp_and_is_stable(process, evidence):
    first = margin_report(process, evidence).to_markdown()
    second = margin_report(process, evidence).to_markdown()
    assert first == second
    # Dates in the data (a source's `retrieved`, a decision quoted in a margin_reason) are
    # fine; a time of rendering is not.
    assert not re.search(r"\d{4}-\d\d-\d\d[T ]\d\d:\d\d", first)
    assert "generated on" not in first.lower() and "UTC" not in first
    assert first.splitlines()[0].startswith("# ")
    assert "out of scope for ws180g005" in first


def test_json_round_trip(report):
    data = json.loads(report.to_json())
    assert data["ok"] is True and data["grid_ok"] is True
    row = next(r for r in data["rows"] if r["field"] == "rules.m1.w")
    assert row["bound"] == "0.30" and row["margin_achieved"] == "1.200" and row["status"] == "ok"
    assert report.to_json() == margin_report(load_process(), _evidence()).to_json()


def _evidence():
    from ws180g_evidence.load import load_evidence

    return load_evidence()


def test_console_script_exit_code(repo_root, tmp, data_copy):
    md, js = tmp / "report.md", tmp / "report.json"
    ok = subprocess.run(["uv", "run", "ws180g-evidence-report", "--markdown", str(md), "--json", str(js)],
                        cwd=repo_root, capture_output=True, text=True, check=False)
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert md.read_text().startswith("# ") and json.loads(js.read_text())["ok"] is True
    set_toml(data_copy / "rules.toml", ["rules", '"m1.w"', "value"], 0.35)
    bad = subprocess.run(["uv", "run", "ws180g-evidence-report", "--process", str(data_copy)],
                         cwd=repo_root, capture_output=True, text=True, check=False)
    assert bad.returncode == 1, bad.stdout + bad.stderr
    assert "under-margin" in bad.stdout


def test_co_size_cites_both_scmos_contact_sections(report):
    ids = {e.id for e in report["rules.co.size"].cited}
    assert {"scmos8/5.1/subm", "scmos8/6.1/deep", "scmos8/6.1/subm"} <= ids
    assert report["rules.co.size"].status == "exempt" and report["rules.co.size"].bound == Decimal("0.22")


def test_topology_only_citation_is_uncovered(data_copy, evidence):
    # Drop the polysilicon-contact size from co.size: only the topology rule cut.ortho still
    # cites scmos8/5.1/*, and a topology row compares nothing.
    path = data_copy / "rules.toml"
    text = path.read_text()
    old = '"scmos8/5.1/deep", "scmos8/5.1/subm", "scmos8/6.1/deep"'
    assert old in text
    path.write_text(text.replace(old, '"scmos8/6.1/deep"', 1))
    r = margin_report(load_process(data_copy), evidence)
    ids = {e.id for e in r.uncovered}
    assert {"scmos8/5.1/deep", "scmos8/5.1/subm"} <= ids
    assert "rules.cut.ortho" in r.notes["scmos8/5.1/deep"]
    assert "topology rule" in r.notes["scmos8/5.1/deep"]
    assert "scmos8/5.1/deep" in r.to_markdown() and "cited only by topology rule" in r.to_markdown()


def test_topology_row_has_no_bound(report):
    assert report["rules.cut.ortho"].bound is None and report["rules.co.in"].bound is None


def test_zero_bound_is_under_margin(process, evidence):
    entries = dict(evidence.entries)
    for e in report_cited(process, evidence, "m1.w"):
        entries[e] = entries[e].model_copy(update={"value": Decimal(0)})
    r = margin_report(process, evidence.model_copy(update={"entries": entries}))
    assert r["rules.m1.w"].status == "under-margin" and r["rules.m1.w"].message
    assert r.ok is False


def report_cited(process, evidence, rid):
    return [i for i in process.rules[rid].evidence if evidence.entries[i].value is not None]


def test_composed_value_not_positive_is_under_margin(data_copy, evidence):
    set_toml(data_copy / "rules.toml", ["rules", '"sel.x"', "value"], 0.665)
    r = margin_report(load_process(data_copy), evidence)
    row = r["rules.nd.s.pgate"]
    assert row.status == "under-margin" and "0.665" in row.message and r.ok is False


def test_only_vt_p_is_a_magnitude(process, evidence):
    entries = dict(evidence.entries)
    toxe = "gf180mcu-models/nfet_06v0/toxe"
    entries[toxe] = entries[toxe].model_copy(update={"value": Decimal("-15.2")})
    r = margin_report(process, evidence.model_copy(update={"entries": entries}))
    assert r["stack.oxides.5v0.thickness.min"].bound == Decimal("-15.2")
    assert r["stack.oxides.5v0.thickness.min"].status == "under-margin"
    assert margin_report(process, evidence)["stack.oxides.5v0.vt_p.max"].bound == Decimal("0.8978")


# A grid every rule value lies on (the loader checks that) but which is not a multiple of the
# GF180MCU 0.005 um grid; 0.004 um does not load (0.265, 3.675, 6.505 are off it).
GRID_OFF = 0.001


def test_grid_not_a_multiple_fails(data_copy, evidence):
    set_toml(data_copy / "process.toml", ["grid", "value"], GRID_OFF)
    r = margin_report(load_process(data_copy), evidence)
    assert r.grid_ok is False and r.ok is False
