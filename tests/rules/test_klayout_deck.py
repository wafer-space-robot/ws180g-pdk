# SPDX-License-Identifier: Apache-2.0
"""The KLayout DRC deck generated from the rule table (Task 13).

The text tests read the generated files; the `sandbox` tests run the deck in the project
container through `build/sandbox-run` and skip when the runner is absent."""

import dataclasses
import re
import shutil
import subprocess
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


# --- sandbox: the deck runs in KLayout


def _runner(repo_root: Path) -> Path:
    runner = repo_root / "build" / "sandbox-run"
    if not runner.exists():
        pytest.skip("build/sandbox-run is absent")
    if shutil.which("docker") is None:
        pytest.skip("docker is absent")
    return runner


def _gds(path: Path, process, boxes: list[tuple[str, int, int, int, int]]) -> None:
    """Write a layout (boxes in dbu on named layers) and derive its generated layers."""
    layout = kdb.Layout()
    layout.dbu = 0.001
    top = layout.create_cell("TOP")
    for name, x1, y1, x2, y2 in boxes:
        top.shapes(layout.layer(*process.layers[name].gds)).insert(kdb.Box(x1, y1, x2, y2))
    drawn = path.with_suffix(".drawn.gds")
    layout.write(str(drawn))
    from ws180g_layergen.derive import derive_file

    derive_file(drawn, path, process)


def _report(path: Path) -> tuple[set[str], Counter]:
    """The category names of a `.lyrdb` and the item count per category."""
    root = ET.parse(path).getroot()
    categories = {c.findtext("name") for c in root.iter("category") if c.find("name") is not None}
    items = Counter(i.findtext("category").strip("'") for i in root.iter("item"))
    return categories, items


def _run(runner: Path, workdir: Path, *args: str) -> None:
    done = subprocess.run(
        [str(runner), "--mem", "2g", "--cpus", "1", "--workdir", str(workdir), "--",
         "klayout", "-b", "-r", *args],
        capture_output=True, text=True, check=False,
    )
    assert done.returncode == 0, done.stdout + done.stderr


@pytest.mark.sandbox
def test_deck_runs_on_an_empty_layout(table, process, repo_root, tmp):
    runner = _runner(repo_root)
    work = tmp / "work"
    write_klayout_deck(table, process, work)
    _gds(work / "empty.gds", process, [])
    _run(runner, work, f"{VARIANT}.drc", "-rd", "input=empty.gds", "-rd", "report=r.lyrdb")
    categories, items = _report(work / "r.lyrdb")
    assert {r.id for r in table.checkable()} <= categories
    assert not items


@pytest.mark.sandbox
def test_batch_deck_writes_one_report_per_input(table, process, repo_root, tmp):
    runner = _runner(repo_root)
    work = tmp / "work"
    write_klayout_deck(table, process, work)
    _gds(work / "empty.gds", process, [])
    # an n-well 1.0 um wide: narrower than nw.w 1.44
    _gds(work / "narrow_nw.gds", process, [("nw", 0, 0, 1000, 5000)])
    (work / "list.txt").write_text("empty.gds\nnarrow_nw.gds\n", encoding="utf-8")
    (work / "out").mkdir()
    _run(runner, work, f"{VARIANT}_batch.drc", "-rd", "list=list.txt", "-rd", "out=out")
    checkable = {r.id for r in table.checkable()}
    categories, items = _report(work / "out" / "empty.lyrdb")
    assert checkable <= categories and not items
    categories, items = _report(work / "out" / "narrow_nw.lyrdb")
    assert checkable <= categories
    assert set(items) == {"nw.w"}
