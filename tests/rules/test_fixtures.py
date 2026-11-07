# SPDX-License-Identifier: Apache-2.0
"""Per-rule pass and fail fixtures generated from the rule table (Task 14).

The fixtures are generated once per module into pytest's temporary directory and read back
with `klayout.db`; Task 15 runs them through the KLayout deck."""

from pathlib import Path

import klayout.db as kdb
import pytest
from ws180g_process.load import load_process
from ws180g_rules.fixtures import Fixture, main, write_fixtures
from ws180g_rules.table import RuleTable

GRID = 5  # dbu
CUTS = ("co", "v1", "v2", "v3", "v4")


@pytest.fixture(scope="module")
def proc():
    return load_process()


@pytest.fixture(scope="module")
def table(proc) -> RuleTable:
    return RuleTable.from_process(proc)


@pytest.fixture(scope="module")
def out(tmp_path_factory) -> Path:
    return tmp_path_factory.mktemp("fixtures")


@pytest.fixture(scope="module")
def fixtures(table, proc, out) -> list[Fixture]:
    return write_fixtures(table, proc, out)


def _layers(path: Path, proc) -> dict[str, kdb.Region]:
    """The merged region of every process layer in the fixture's top cell."""
    layout = kdb.Layout()
    layout.read(str(path))
    top = layout.top_cell()
    regions = {}
    for name, layer in proc.layers.items():
        index = layout.find_layer(*layer.gds)
        region = kdb.Region() if index is None else kdb.Region(top.begin_shapes_rec(index))
        regions[name] = region.merged()
    return regions


def _get(fixtures: list[Fixture], rid: str, expect: str, name: str) -> Fixture:
    for f in fixtures:
        if (f.rule_id, f.expect, f.name) == (rid, expect, name):
            return f
    raise KeyError(f"{rid}/{expect}_{name}")


def _boxes(region: kdb.Region) -> list[kdb.Box]:
    return [p.bbox() for p in region.each()]


def test_paths_and_layout(fixtures, out):
    assert fixtures
    for f in fixtures:
        assert f.expect in ("pass", "fail")
        assert f.path == out / f.rule_id / f"{f.expect}_{f.name}.gds"
        assert f.path.is_file()
    layout = kdb.Layout()
    layout.read(str(fixtures[0].path))
    assert [c.name for c in layout.each_cell()] == ["test"]
    assert abs(layout.dbu - 0.001) < 1e-12


def test_nw_width(fixtures, proc):
    for name, width in (("min", 1440), ("min_plus_grid", 1445)):
        nw = _layers(_get(fixtures, "nw.w", "pass", name).path, proc)["nw"]
        (box,) = _boxes(nw)
        assert min(box.width(), box.height()) == width
    nw = _layers(_get(fixtures, "nw.w", "fail", "min_minus_grid").path, proc)["nw"]
    (box,) = _boxes(nw)
    assert min(box.width(), box.height()) == 1435


def test_pad_width_inside_mtop(fixtures, proc):
    layers = _layers(_get(fixtures, "pad.w", "pass", "min").path, proc)
    (box,) = _boxes(layers["pad"])
    assert min(box.width(), box.height()) == 60000
    assert max(box.width(), box.height()) >= 300000
    assert (layers["pad"] - layers["mtop"]).is_empty()


def test_sab_width_fail_has_enough_area(fixtures, proc):
    sab = _layers(_get(fixtures, "sab.w", "fail", "min_minus_grid").path, proc)["sab"]
    (box,) = _boxes(sab)
    assert min(box.width(), box.height()) == 500
    assert sab.area() >= 3_000_000
    assert max(box.width(), box.height()) % GRID == 0


def test_tap_distance_fail_has_one_ntap(fixtures, proc):
    layers = _layers(_get(fixtures, "nw.tap.dmax", "fail", "min_plus_grid").path, proc)
    assert (layers["nd"] & layers["nw"]).count() == 1
    assert layers["nd"].count() == 1
    assert not (layers["pd"] & layers["nw"]).is_empty()


def test_long_top_metal_short_bar(fixtures, proc):
    mtop = _layers(_get(fixtures, "mtop.w.long", "pass", "short").path, proc)["mtop"]
    (box,) = _boxes(mtop)
    assert (box.width(), box.height()) == (799000, 2160)
    for expect, name, width in (("pass", "min", 3300), ("fail", "min_minus_grid", 3295)):
        mtop = _layers(_get(fixtures, "mtop.w.long", expect, name).path, proc)["mtop"]
        (box,) = _boxes(mtop)
        assert (box.width(), box.height()) == (801000, width)


def test_contact_rect(fixtures, proc):
    co = _layers(_get(fixtures, "co.size", "fail", "rect").path, proc)["co"]
    (box,) = _boxes(co)
    assert (box.width(), box.height()) == (220, 225)


def test_df_enclosure_of_contact(fixtures, proc):
    layers = _layers(_get(fixtures, "df.e.co", "pass", "min").path, proc)
    (co,) = _boxes(layers["co"])
    (nd,) = _boxes(layers["nd"])
    margins = sorted([co.left - nd.left, nd.right - co.right, co.bottom - nd.bottom,
                      nd.top - co.top])
    assert margins == [180, 1000, 1000, 1000]
    ptap = layers["pd"] - layers["nw"]
    assert not ptap.is_empty()
    assert ((layers["nd"] - layers["nw"]) - ptap.sized(5000)).is_empty()


def test_implied_rule_has_no_fail_fixture(fixtures):
    mtop_area = [f for f in fixtures if f.rule_id == "mtop.area"]
    assert mtop_area
    assert {f.expect for f in mtop_area} == {"pass"}


def test_rows_without_engines_have_no_fixtures(fixtures, table):
    rids = {f.rule_id for f in fixtures}
    assert not rids & {r.id for r in table.rows if not r.engines}


def test_every_checkable_row_has_a_pass_fixture(fixtures, table):
    passing = {f.rule_id for f in fixtures if f.expect == "pass"}
    assert {r.id for r in table.checkable()} <= passing


def test_every_row_with_a_fail_fixture_has_one(fixtures, table):
    failing = {f.rule_id for f in fixtures if f.expect == "fail"}
    assert failing == {r.id for r in table.with_fail_fixture()}


def test_vertices_on_grid(fixtures):
    """Every vertex is a multiple of the 5 dbu grid, except in the grid rule's fail
    fixture, which exists to put one off the grid."""
    for f in fixtures:
        layout = kdb.Layout()
        layout.read(str(f.path))
        off = []
        for index in layout.layer_indexes():
            for shape in layout.top_cell().shapes(index).each():
                for p in shape.polygon.each_point_hull():
                    if p.x % GRID or p.y % GRID:
                        off.append((p.x, p.y))
        if (f.rule_id, f.expect) == ("grid", "fail"):
            assert off, f.path
        else:
            assert not off, f.path


def test_byte_identical_runs(table, proc, fixtures, tmp_path):
    again = write_fixtures(table, proc, tmp_path)
    assert [(f.rule_id, f.expect, f.name) for f in again] == \
        [(f.rule_id, f.expect, f.name) for f in fixtures]
    for a, b in zip(fixtures, again, strict=True):
        assert a.path.read_bytes() == b.path.read_bytes(), a.path


def test_fixture_count(fixtures, table):
    dimensional = [r for r in table.with_fail_fixture() if r.kind != "topology"]
    assert len(fixtures) >= 3 * len(dimensional)


def test_variants_of_dimensional_rules(fixtures, table):
    names = {}
    for f in fixtures:
        names.setdefault(f.rule_id, set()).add(f"{f.expect}_{f.name}")
    for row in table.with_fail_fixture():
        if row.kind in ("min-width", "min-space", "min-enclosure", "min-extension",
                        "gate-length"):
            assert {"pass_min", "pass_min_plus_grid", "fail_min_minus_grid"} <= names[row.id]
    assert {"fail_flush", "fail_end_inside"} <= names["po.x.df"]
    assert {"fail_flush", "fail_end_inside"} <= names["df.x.po"]
    assert "fail_flush" in names["po.x.sab"] and "fail_end_inside" not in names["po.x.sab"]
    assert "fail_straddle" in names["nw.e.pd"]
    assert "pass_narrow" in names["po.l.n"]
    assert "pass_own_endcap" in names["po.s.df"]
    assert "pass_butted" in names["df.s.np"]
    assert {"pass_exact", "fail_oversize", "fail_rect"} <= names["v4.size"]
    assert {"pass_min", "fail_area_minus"} <= names["m1.area"]
    assert {"pass_min", "fail_min_plus_grid"} <= names["ps.tap.dmax"]
    assert {"pass_co_on_field", "fail_co_on_field"} <= names["co.in"]


def test_tap_context(fixtures, proc, table):
    """Outside the max-distance rules, every nd in the substrate has a p-tap within 5 um
    and every pd in an n-well an n-tap in that well within 5 um."""
    skip = {r.id for r in table.rows if r.kind == "max-distance"}
    for f in fixtures:
        if f.rule_id in skip:
            continue
        layers = _layers(f.path, proc)
        nw, nd, pd = layers["nw"], layers["nd"], layers["pd"]
        ptap = pd - nw
        assert ((nd - nw) - ptap.sized(5000)).is_empty(), f.path
        for well in nw.each():
            w = kdb.Region(well)
            ntap = nd & w
            assert ((pd & w) - ntap.sized(5000)).is_empty(), f.path


def test_cuts_have_their_metals(fixtures, proc):
    """Every cut overlaps the metals above and below it (the enclosure fixtures draw the
    metal under test themselves)."""
    metals = {"co": ["m1"], "v1": ["m1", "m2"], "v2": ["m2", "m3"], "v3": ["m3", "m4"],
              "v4": ["m4", "mtop"], "pad": ["mtop"]}
    for f in fixtures:
        layers = _layers(f.path, proc)
        for cut, above in metals.items():
            for metal in above:
                assert layers[cut].not_interacting(layers[metal]).is_empty(), (f.path, cut)


def test_cli(tmp_path, capsys):
    assert main(["--out", str(tmp_path)]) == 0
    assert (tmp_path / "nw.w" / "pass_min.gds").is_file()
    assert "fixtures" in capsys.readouterr().out


def test_expected_markers(fixtures):
    """Each forced exception names a real fail fixture and still includes its own rule."""
    from ws180g_rules.fixtures import EXPECTED_MARKERS

    fails = {(f.rule_id, f.name) for f in fixtures if f.expect == "fail"}
    assert set(EXPECTED_MARKERS) <= fails
    for (rid, _), markers in EXPECTED_MARKERS.items():
        assert markers.get(rid, 0) >= 1
    by_key = {(f.rule_id, f.expect, f.name): f for f in fixtures}
    assert by_key[("nw.w", "pass", "min")].markers() == {}
    assert by_key[("nw.w", "fail", "min_minus_grid")].markers() == {"nw.w": 1}
    assert by_key[("grid", "fail", "grid")].markers() == {"grid": 2}


def test_pass_fixture_v4_clusters_are_rectangular_arrays(fixtures, proc):
    """Every v4 cluster of a pass fixture is a rectangular array: GF180MCU MT30.8 (30K top
    metal) merges each cluster's cuts by 1 um over-under sizing and rejects a cluster whose
    shape is not a rectangle (found by the Task 18 retarget check,
    docs/phase-0-retarget-log.md)."""
    for f in fixtures:
        if f.expect != "pass":
            continue
        v4 = _layers(f.path, proc)["v4"]
        if v4.is_empty():
            continue
        clusters = v4.sized(1000).merged().sized(-1000)
        assert clusters.non_rectangles().is_empty(), (f.rule_id, f.name)


def test_v4_array_has_a_staggered_fail_fixture(fixtures, proc):
    """mtop.v4.array rejects a staggered 2 x 2 array (Task 18, outcome (a))."""
    staggered = [f for f in fixtures if (f.rule_id, f.name) == ("mtop.v4.array", "staggered")]
    assert [f.expect for f in staggered] == ["fail"]
    v4 = _layers(staggered[0].path, proc)["v4"]
    assert v4.count() == 4
    s = int(proc.rules["v4.s"].value * 1000)
    assert not v4.sized(s // 2).merged().non_rectangles().is_empty()
