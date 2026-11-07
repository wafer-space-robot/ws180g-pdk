# SPDX-License-Identifier: Apache-2.0
"""The KLayout DRC deck generated from the rule table (Task 13).

The text tests read the generated files; the `sandbox` tests run the deck in the project
container through `build/sandbox-run` and skip when the runner is absent."""

import dataclasses
import re
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

import klayout.db as kdb
import pytest
from ws180g_rules.klayout_deck import main, variant_layers, write_klayout_deck
from ws180g_rules.layer_expr import LayerExpr, Sized, Unrelated, _Binary
from ws180g_rules.table import RuleTable

VARIANT = "ws180g005"
NAMES = (f"{VARIANT}.drc", f"{VARIANT}_batch.drc", f"{VARIANT}_checks.rb")
OUTPUT_ID = re.compile(r'\.output\("([^"]+)"')


@pytest.fixture
def table(process) -> RuleTable:
    return RuleTable.from_process(process, VARIANT)


@pytest.fixture
def deck(table, process, tmp) -> dict[str, str]:
    """The generated files by name."""
    paths = write_klayout_deck(table, process, tmp / "deck")
    return {p.name: p.read_text(encoding="utf-8") for p in paths}


def test_writes_the_three_files(table, process, tmp):
    paths = write_klayout_deck(table, process, tmp / "deck")
    assert [p.name for p in paths] == list(NAMES)
    assert all(p.is_file() for p in paths)


def test_spdx_on_line_one(deck):
    for name, text in deck.items():
        assert text.splitlines()[0] == "# SPDX-License-Identifier: Apache-2.0", name


def test_header_names_the_variant_and_generator(deck):
    for name, text in deck.items():
        head = "\n".join(text.splitlines()[:6])
        assert VARIANT in head, name
        assert "ws180g_rules.klayout_deck" in head, name
        assert "generated: do not edit" in head, name


def test_single_entry_point(deck):
    text = deck[f"{VARIANT}.drc"]
    assert "source($input)" in text
    assert f'report("{VARIANT}", $report)' in text
    assert "\ndeep\n" in text
    assert f"{VARIANT}_checks.rb" in text


def test_batch_entry_point(deck):
    text = deck[f"{VARIANT}_batch.drc"]
    assert "$list" in text and "$out" in text
    assert "source(" in text and f'report("{VARIANT}"' in text
    assert "\ndeep\n" in text
    assert f"{VARIANT}_checks.rb" in text


def test_min_width_check(deck):
    checks = deck[f"{VARIANT}_checks.rb"]
    assert "nw.width(1.44.um" in checks
    assert '.output("nw.w"' in checks


def test_every_checkable_rule_is_output_exactly_once(deck, table):
    ids = Counter(OUTPUT_ID.findall("\n".join(deck.values())))
    checkable = [r.id for r in table.checkable() if "klayout" in r.engines]
    assert len(checkable) == len(table.checkable())  # every checkable rule is KLayout's
    assert sorted(ids) == sorted(checkable)
    assert all(n == 1 for n in ids.values()), {k: n for k, n in ids.items() if n != 1}


def test_rules_without_engines_are_absent(deck, table):
    text = "\n".join(deck.values())
    unchecked = [r.id for r in table.rows if not r.engines]
    assert "nsel.w" in unchecked
    for rid in unchecked:
        assert f'"{rid}"' not in text, rid
    assert "nsel.w" not in text


def test_no_date_or_time(deck):
    for name, text in deck.items():
        assert not re.search(r"\b(19|20)\d\d-\d\d-\d\d\b", text), name
        assert not re.search(r"\b\d\d:\d\d(:\d\d)?\b", text), name


def test_byte_identical_runs(table, process, tmp):
    one = write_klayout_deck(table, process, tmp / "one")
    two = write_klayout_deck(table, process, tmp / "two")
    for a, b in zip(one, two, strict=True):
        assert a.read_bytes() == b.read_bytes(), a.name


def test_unknown_kind_raises(table, process, tmp):
    rows = [dataclasses.replace(r, kind="bogus") if r.id == "nw.w" else r for r in table.rows]
    bad = RuleTable(table.variant, table.layers, rows)
    with pytest.raises(ValueError, match="bogus"):
        write_klayout_deck(bad, process, tmp / "deck")


def test_unknown_topology_fixture_raises(table, process, tmp):
    rows = [dataclasses.replace(r, fixture="nope") if r.id == "co.in" else r
            for r in table.rows]
    bad = RuleTable(table.variant, table.layers, rows)
    with pytest.raises(ValueError, match="nope"):
        write_klayout_deck(bad, process, tmp / "deck")


def _sized(expr: LayerExpr) -> list[Sized]:
    found = [expr] if isinstance(expr, Sized) else []
    if isinstance(expr, Sized):
        found += _sized(expr.expr)
    elif isinstance(expr, (_Binary, Unrelated)):
        found += _sized(expr.a) + _sized(expr.b)
    return found


def test_sized_field_values_are_rendered(deck, table, process):
    checks = deck[f"{VARIANT}_checks.rb"]
    assert ".sized(0.27.um)" in checks  # rules.po.x.df
    fields = {s.field for r in table.checkable() for e in r.layers for s in _sized(e)}
    assert fields == {"rules.po.x.df"}
    for field in fields:
        value = process.rules[field.removeprefix("rules.")].value
        assert f".sized({value.normalize():f}.um)" in checks


def test_every_input_layer_of_the_variant_is_declared(deck, process):
    checks = deck[f"{VARIANT}_checks.rb"]
    layers = variant_layers(process, VARIANT)
    assert {"nw", "gate", "ntap", "dnw"} <= set(layers)
    assert "ox_3v3" not in layers
    for name, layer in layers.items():
        assert f"\n{name} = input({layer.gds[0]}, {layer.gds[1]})\n" in checks, name
    assert "ox_3v3" not in checks


def test_each_derived_expression_is_assigned_once(deck):
    checks = deck[f"{VARIANT}_checks.rb"]
    assert "\ndf = nd | pd\n" in checks
    assignments = re.findall(r"^([a-z_][a-z0-9_]*) = ", checks, re.MULTILINE)
    assert len(assignments) == len(set(assignments)), Counter(assignments).most_common(3)


def test_klayout_only_rules_are_marked(deck, table):
    checks = deck[f"{VARIANT}_checks.rb"]
    blocks = checks.split("\n\n")
    for row in table.checkable():
        block = next(b for b in blocks if f'.output("{row.id}"' in b)
        assert ("# KLayout-only" in block) == (row.engines == ["klayout"]), row.id


def test_idioms(deck):
    checks = deck[f"{VARIANT}_checks.rb"]
    assert ".edges & po.edges" in checks  # gate-length
    assert "without_distance(0)" in checks  # df.s.np butting allowed
    assert ".with_area(0, 0.305.um2)" in checks  # df.area
    assert "with_length(800.0.um, nil)" in checks  # mtop.w.long
    assert ".ongrid(0.005.um)" in checks  # grid


def test_cli(tmp):
    assert main(["--out", str(tmp / "cli")]) == 0
    assert sorted(p.name for p in (tmp / "cli").iterdir()) == sorted(NAMES)


def _output_line(checks: str, rid: str) -> str:
    return next(line for line in checks.splitlines() if f'.output("{rid}"' in line)


def test_header_names_the_variant_once(deck):
    for name, text in deck.items():
        assert text.splitlines()[1].count(VARIANT) == 1, name


def test_field_poly_space_excludes_the_gate_ends(deck):
    checks = deck[f"{VARIANT}_checks.rb"]
    assert "\nfield_po = po - df\n" in checks
    assert "\nfield_po_edges_not_gate = field_po.edges - gate.edges\n" in checks
    assert _output_line(checks, "po.s.df").startswith(
        "field_po_edges_not_gate.separation(df.edges, 0.36.um, euclidian)")


def test_unsupported_edges_raise(table, process, tmp):
    rows = [dataclasses.replace(r, edges="ends") if r.id == "po.s.df" else r
            for r in table.rows]
    with pytest.raises(ValueError, match="ends"):
        write_klayout_deck(RuleTable(table.variant, table.layers, rows), process, tmp / "d")


def test_extension_catches_flush_and_inside_ends(deck, table):
    checks = deck[f"{VARIANT}_checks.rb"]
    assert "\npo_ends_in_df = po.edges.inside(df).interacting(po_and_gate)\n" in checks
    assert "\npo_flush_on_df = po.edges.inside(df.edges).interacting(po_and_gate)\n" in checks
    assert "\ndf_ends_in_po = df.edges.inside(po).interacting(df_and_gate)\n" in checks
    assert "po_ends_in_sab" not in checks and "df_ends_in_sab" not in checks
    for row in table.rows:
        if row.kind == "min-extension":
            line = _output_line(checks, row.id)
            assert ".first_edges" in line and ".merged.output(" in line, row.id


def test_enclosure_catches_straddling_inner_shapes(deck, table):
    checks = deck[f"{VARIANT}_checks.rb"]
    assert "\nco_across_m1 = co.overlapping(m1).not_inside(m1)\n" in checks
    for row in table.rows:
        if row.kind == "min-enclosure":
            assert "_across_" in _output_line(checks, row.id), row.id


def test_max_distance_uses_octagonal_sizing(deck):
    checks = deck[f"{VARIANT}_checks.rb"]
    assert _output_line(checks, "nw.tap.dmax").startswith(
        "(pd_and_nw - ntap.sized(10.0.um, octagon_limit))")


# --- sandbox: the deck runs in KLayout


def _gds(path: Path, process, boxes: list[tuple[str, int, int, int, int]]) -> None:
    """Write a layout (boxes in dbu on named layers) and derive its generated layers."""
    from ws180g_layergen.derive import derive_file

    layout = kdb.Layout()
    layout.dbu = 0.001
    top = layout.create_cell("TOP")
    for name, x1, y1, x2, y2 in boxes:
        top.shapes(layout.layer(*process.layers[name].gds)).insert(kdb.Box(x1, y1, x2, y2))
    drawn = path.with_suffix(".drawn.gds")
    layout.write(str(drawn))
    derive_file(drawn, path, process)


def _report(path: Path) -> tuple[set[str], Counter]:
    """The category names of a `.lyrdb` and the item count per category."""
    root = ET.parse(path).getroot()
    categories = {c.findtext("name") for c in root.iter("category") if c.find("name") is not None}
    items = Counter(i.findtext("category").strip("'") for i in root.iter("item"))
    return categories, items


def _klayout(sandbox, workdir: Path, *args: str) -> None:
    done = sandbox.run(["klayout", "-b", "-r", *args], workdir, mem="2g", cpus=2)
    assert done.returncode == 0, done.stdout + done.stderr


@pytest.mark.sandbox
def test_deck_runs_on_an_empty_layout(table, process, sandbox, tmp):
    work = tmp / "work"
    write_klayout_deck(table, process, work)
    _gds(work / "empty.gds", process, [])
    _klayout(sandbox, work, f"{VARIANT}.drc", "-rd", "input=empty.gds", "-rd", "report=r.lyrdb")
    categories, items = _report(work / "r.lyrdb")
    assert {r.id for r in table.checkable()} <= categories
    assert not items


@pytest.mark.sandbox
def test_batch_deck_writes_one_report_per_input(table, process, sandbox, tmp):
    work = tmp / "work"
    write_klayout_deck(table, process, work)
    _gds(work / "empty.gds", process, [])
    # an n-well 1.0 um wide: narrower than nw.w 1.44
    _gds(work / "narrow_nw.gds", process, [("nw", 0, 0, 1000, 5000)])
    (work / "list.txt").write_text("empty.gds\nnarrow_nw.gds\n", encoding="utf-8")
    (work / "out").mkdir()
    _klayout(sandbox, work, f"{VARIANT}_batch.drc", "-rd", "list=list.txt", "-rd", "out=out")
    checkable = {r.id for r in table.checkable()}
    categories, items = _report(work / "out" / "empty.lyrdb")
    assert checkable <= categories and not items
    categories, items = _report(work / "out" / "narrow_nw.lyrdb")
    assert checkable <= categories
    assert set(items) == {"nw.w"}


# Review probes: (boxes in dbu, rules that must fire, rules that must not). The n-diffusion
# cases have no p-tap, so ps.tap.dmax also fires; it is not asserted.
PROBES = {
    "legal_nfet": ([("nd", 0, 0, 2000, 1000), ("po", 640, -400, 1360, 1400)],
                   set(), {"po.s.df", "po.x.df", "df.x.po", "po.l.n"}),
    "field_po_near_df": ([("nd", 0, 0, 1000, 1000), ("po", 1300, 0, 1540, 1000)],
                         {"po.s.df"}, set()),
    "po_flush": ([("nd", 0, 0, 2000, 1000), ("po", 640, -400, 1360, 1000)],
                 {"po.x.df"}, {"df.x.po", "po.s.df"}),
    "po_inside": ([("nd", 0, 0, 2000, 1000), ("po", 640, -400, 1360, 700)],
                  {"po.x.df"}, {"df.x.po", "po.s.df"}),
    "df_flush": ([("nd", 0, 0, 1360, 1000), ("po", 640, -400, 1360, 1400)],
                 {"df.x.po"}, {"po.x.df", "po.s.df"}),
    "df_inside": ([("nd", 0, 0, 1200, 1000), ("po", 640, -400, 1360, 1400)],
                  {"df.x.po"}, {"po.x.df"}),
    "po_sab_flush": ([("sab", 0, 0, 1000, 2000), ("po", 300, -1000, 540, 2000)],
                     {"po.x.sab"}, {"sab.e.po"}),
    # poly ending 0.5 inside sab: governed by sab.e.po, not po.x.sab
    "po_sab_inside": ([("sab", 0, 0, 1000, 2000), ("po", 300, -1000, 540, 1500)],
                      set(), {"po.x.sab"}),
    "nd_wholly_in_sab": ([("sab", 0, 0, 1800, 1800), ("nd", 400, 400, 1400, 1400)],
                         set(), {"df.x.sab", "sab.e.df"}),
    "df_sab_inside": ([("sab", 0, 0, 2000, 2000), ("nd", 300, -1000, 1300, 1600)],
                      set(), {"df.x.sab"}),
    "po_wholly_in_sab": ([("sab", 0, 0, 1800, 3000), ("po", 400, 400, 640, 2600)],
                         set(), {"po.x.sab", "sab.e.po"}),
    "short_end_cap": ([("nd", 0, 0, 2000, 1000), ("po", 640, -100, 1360, 1400)],
                      {"po.x.df"}, {"df.x.po"}),
    "short_df_extension": ([("nd", 440, 0, 2000, 1000), ("po", 640, -400, 1360, 1400)],
                           {"df.x.po"}, {"po.x.df"}),
    "po_abutting_df": ([("nd", 0, 0, 1000, 1000), ("po", 1000, 0, 1240, 1000)],
                       {"po.s.df"}, {"po.x.df", "df.x.po"}),
    "po_sab_legal": ([("sab", 0, 0, 1000, 2000), ("po", 300, -1000, 540, 3000)],
                     set(), {"po.x.sab", "sab.e.po", "sab.s.po"}),
    "df_sab_flush": ([("sab", 0, 0, 2000, 2000), ("nd", 300, -1000, 1300, 2000)],
                     {"df.x.sab"}, {"sab.e.df"}),
    "hanging_co": ([("m1", 0, 0, 1000, 1000), ("co", 900, 300, 1120, 520)],
                   {"m1.e.co"}, set()),
    "legal_outside": ([("nw", 5000, 0, 8000, 3000), ("nd", 0, 0, 1000, 1000),
                       ("co", 300, 300, 520, 520), ("m1", 180, 180, 640, 640),
                       ("po", 3000, -1000, 3240, 2000)],
                      set(), {"nw.e.nd", "po.e.co", "m1.e.co", "df.e.co", "co.in"}),
}


@pytest.mark.sandbox
def test_review_probes(table, process, sandbox, tmp):
    work = tmp / "work"
    write_klayout_deck(table, process, work)
    for name, (boxes, _, _) in PROBES.items():
        _gds(work / f"{name}.gds", process, boxes)
    (work / "list.txt").write_text("".join(f"{n}.gds\n" for n in PROBES), encoding="utf-8")
    (work / "out").mkdir()
    _klayout(sandbox, work, f"{VARIANT}_batch.drc", "-rd", "list=list.txt", "-rd", "out=out")
    wrong = {}
    for name, (_, fire, quiet) in PROBES.items():
        _, items = _report(work / "out" / f"{name}.lyrdb")
        if any(items[r] != 1 for r in fire) or quiet & set(items):
            wrong[name] = dict(items)
    assert not wrong  # each rule that must fire gives exactly one marker, the others none
