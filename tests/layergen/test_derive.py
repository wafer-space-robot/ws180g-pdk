# SPDX-License-Identifier: Apache-2.0
"""Layer generation: selects, gate and taps derived from the drawn intent layers.

Every geometry is built in-test with `klayout.db`; areas and boxes are compared in dbu
(0.001 um) with exact integers."""

from decimal import Decimal

import klayout.db as kdb
import pytest
from ws180g_layergen.derive import GENERATED, derive, derive_file

GENERATED_NAMES = ("nsel", "psel", "gate", "ntap", "ptap")


def dbu(value: str | Decimal) -> int:
    """A um value as an exact integer number of 0.001 um database units."""
    return int(Decimal(value) * 1000)


def new_layout() -> tuple[kdb.Layout, kdb.Cell]:
    layout = kdb.Layout()
    layout.dbu = 0.001
    return layout, layout.create_cell("TOP")


def box(layout, cell, layer_name, x1, y1, x2, y2, process) -> None:
    """Draw a box on `layer_name` (GDS number from `process`) with corners in um, given as
    strings so the conversion to dbu is exact."""
    gds = process.layers[layer_name].gds
    index = layout.layer(*gds)
    cell.shapes(index).insert(kdb.Box(dbu(x1), dbu(y1), dbu(x2), dbu(y2)))


def region(layout, cell, layer_name, process) -> kdb.Region:
    index = layout.find_layer(*process.layers[layer_name].gds)
    if index is None:
        return kdb.Region()
    return kdb.Region(cell.begin_shapes_rec(index))


def rect(x1, y1, x2, y2) -> kdb.Region:
    return kdb.Region(kdb.Box(dbu(x1), dbu(y1), dbu(x2), dbu(y2)))


@pytest.fixture
def x(process) -> int:
    return dbu(process.rules["sel.x"].value)


def test_definition_table_covers_exactly_the_generated_layers(process):
    generated = {n for n, layer in process.layers.items() if layer.kind == "generated"}
    assert set(GENERATED) == generated == set(GENERATED_NAMES)
    order = list(GENERATED)
    assert order.index("psel") < order.index("nsel")


def test_nfet_gate_and_nsel(process, x):
    layout, top = new_layout()
    box(layout, top, "nd", "0", "0", "2", "1", process)
    box(layout, top, "po", "0.9", "-0.3", "1.1", "1.3", process)
    derive(layout, process)
    gate = region(layout, top, "gate", process)
    assert gate.count() == 1
    assert gate.bbox() == kdb.Box(dbu("0.9"), 0, dbu("1.1"), dbu("1"))
    assert gate.area() == dbu("0.2") * dbu("1")
    nsel = region(layout, top, "nsel", process)
    assert nsel.count() == 1
    expected = kdb.Box(-x, -x, dbu("2") + x, dbu("1") + x)
    assert nsel.bbox() == expected
    assert nsel.area() == expected.area()
    assert region(layout, top, "psel", process).is_empty()


def test_nd_inside_nw_is_ntap(process):
    layout, top = new_layout()
    box(layout, top, "nw", "-1", "-1", "3", "3", process)
    box(layout, top, "nd", "0", "0", "1", "1", process)
    derive(layout, process)
    ntap = region(layout, top, "ntap", process)
    assert (ntap ^ rect("0", "0", "1", "1")).is_empty()
    assert region(layout, top, "ptap", process).is_empty()


def test_pd_outside_nw_is_ptap(process):
    layout, top = new_layout()
    box(layout, top, "nw", "-1", "-1", "0.5", "3", process)
    box(layout, top, "pd", "2", "0", "3", "1", process)
    derive(layout, process)
    ptap = region(layout, top, "ptap", process)
    assert (ptap ^ rect("2", "0", "3", "1")).is_empty()
    assert region(layout, top, "ntap", process).is_empty()


def test_butted_nd_pd_selects_meet_at_the_butting_edge(process):
    layout, top = new_layout()
    box(layout, top, "nd", "0", "0", "1", "1", process)
    box(layout, top, "pd", "1", "0", "2", "1", process)
    derive(layout, process)
    nsel = region(layout, top, "nsel", process)
    psel = region(layout, top, "psel", process)
    assert (nsel & psel).is_empty()
    # Along the whole butting edge x = 1, nsel lies just left and psel just right.
    left = rect("0.995", "0", "1", "1")
    right = rect("1", "0", "1.005", "1")
    assert (nsel & left).area() == left.area()
    assert (psel & right).area() == right.area()
    assert (rect("0", "0", "1", "1") - nsel).is_empty()
    assert (rect("1", "0", "2", "1") - psel).is_empty()


@pytest.mark.parametrize("pd_first", [True, False])
def test_butted_selects_split_the_overhang_at_the_butting_line(process, x, pd_first):
    """At a butting edge the selects meet on the straight butting line, also through the
    overhang beyond the actives (GF NP.3d/PP.3d: select edge on the butting edge), so no
    select gets an x-by-x prong narrower than psel.w / nsel.w (GF PP.1, NP.1) and each
    keeps its extension beyond its own active (GF NP.5b, PP.5b). Found by the Task 18
    retarget check (docs/phase-0-retarget-log.md)."""
    layout, top = new_layout()
    left, right = ("pd", "nd") if pd_first else ("nd", "pd")
    box(layout, top, left, "0", "0", "1", "1", process)
    box(layout, top, right, "1", "0", "2", "1", process)
    derive(layout, process)
    sel = {"pd": region(layout, top, "psel", process), "nd": region(layout, top, "nsel", process)}
    assert (sel[left] ^ kdb.Region(kdb.Box(-x, -x, dbu("1"), dbu("1") + x))).is_empty()
    assert (sel[right] ^ kdb.Region(kdb.Box(dbu("1"), -x, dbu("2") + x, dbu("1") + x))).is_empty()
    for name in ("psel", "nsel"):
        w = dbu(process.rules[f"{name}.w"].value)
        assert region(layout, top, name, process).width_check(w).is_empty()


@pytest.mark.parametrize("gap", ["0.28", "0.48"])
def test_nd_pd_at_a_gap_get_non_overlapping_selects(process, gap):
    layout, top = new_layout()
    start = 1 + Decimal(gap)
    box(layout, top, "nd", "0", "0", "1", "1", process)
    box(layout, top, "pd", str(start), "0", str(start + 1), "1", process)
    derive(layout, process)
    nsel = region(layout, top, "nsel", process)
    psel = region(layout, top, "psel", process)
    assert not nsel.is_empty() and not psel.is_empty()
    assert (nsel & psel).is_empty()
    assert (rect("0", "0", "1", "1") - nsel).is_empty()
    assert (rect(str(start), "0", str(start + 1), "1") - psel).is_empty()


def test_nd_boxes_0p60_apart_get_one_merged_nsel(process):
    layout, top = new_layout()
    box(layout, top, "nd", "0", "0", "1", "1", process)
    box(layout, top, "nd", "1.6", "0", "2.6", "1", process)
    derive(layout, process)
    assert region(layout, top, "nsel", process).count() == 1


def test_nd_boxes_1p20_apart_get_two_nsel_spaced_at_least_nsel_s(process, x):
    layout, top = new_layout()
    box(layout, top, "nd", "0", "0", "1", "1", process)
    box(layout, top, "nd", "2.2", "0", "3.2", "1", process)
    derive(layout, process)
    nsel = region(layout, top, "nsel", process)
    assert nsel.count() == 2
    first, second = sorted((p.bbox() for p in nsel.each()), key=lambda b: b.left)
    gap = second.left - first.right
    assert gap == dbu("1.2") - 2 * x
    assert gap >= dbu(process.rules["nsel.s"].value)


def test_unsilicided_poly_gets_psel(process, x):
    layout, top = new_layout()
    box(layout, top, "po", "0", "0", "3", "0.4", process)
    box(layout, top, "sab", "0.5", "-0.5", "2.5", "0.9", process)
    derive(layout, process)
    psel = region(layout, top, "psel", process)
    expected = kdb.Box(dbu("0.5") - x, -x, dbu("2.5") + x, dbu("0.4") + x)
    assert psel.bbox() == expected
    assert psel.area() == expected.area()


def test_poly_without_sab_gets_no_psel(process):
    layout, top = new_layout()
    box(layout, top, "po", "0", "0", "3", "0.4", process)
    derive(layout, process)
    assert region(layout, top, "psel", process).is_empty()
    assert region(layout, top, "nsel", process).is_empty()


def test_known_limitation_narrow_nd_between_pd_gets_a_df_w_wide_nsel(process, x):
    """KNOWN LIMITATION, recorded not fixed: an nd bar of width df.w butted to pd on both
    long sides gets an nsel only df.w wide. The band beyond each short end (df.w by x) is
    narrower than psel.w, so `open` takes it out of psel and it falls to nsel, which then
    covers the nd and extends x beyond its short ends (GF NP.5b); its width stays df.w, below
    nsel.w. No Task 14 pass fixture draws this; the Task 18 retarget check did not meet it."""
    w = process.rules["df.w"].value
    layout, top = new_layout()
    box(layout, top, "pd", "-1", "0", "0", "2", process)
    box(layout, top, "nd", "0", "0", str(w), "2", process)
    box(layout, top, "pd", str(w), "0", str(w + 1), "2", process)
    derive(layout, process)
    nsel = region(layout, top, "nsel", process)
    psel = region(layout, top, "psel", process)
    assert (nsel & psel).is_empty()
    assert (nsel ^ kdb.Region(kdb.Box(0, -x, dbu(w), dbu("2") + x))).is_empty()
    assert (rect("-1", "0", "0", "2") - psel).is_empty()
    assert (rect(str(w), "0", str(w + 1), "2") - psel).is_empty()


def test_known_limitation_narrow_pd_between_nd_gets_a_df_w_wide_psel(process):
    """KNOWN LIMITATION, recorded not fixed (the mirror of the nd bar above): a pd bar of
    width df.w butted to nd on both long sides gets a psel that is exactly the bar, df.w
    wide (below psel.w and GF PP.1 0.40) and with no extension beyond its short ends (GF
    PP.5b): the band beyond each end is narrower than psel.w, so `open` removes the whole
    bar-wide psel and `P - nd` restores only the bar. nsel then rings the bar, a polygon
    with a hole that touches the pd on all four sides. No Task 14 pass fixture draws it;
    see docs/phase-0-retarget-log.md (open points) and the notes of rules.psel.w/.s."""
    w = process.rules["df.w"].value
    layout, top = new_layout()
    box(layout, top, "nd", "-1", "0", "0", "2", process)
    box(layout, top, "pd", "0", "0", str(w), "2", process)
    box(layout, top, "nd", str(w), "0", str(w + 1), "2", process)
    derive(layout, process)
    nsel = region(layout, top, "nsel", process).merged()
    psel = region(layout, top, "psel", process).merged()
    assert (nsel & psel).is_empty()
    assert (psel ^ rect("0", "0", str(w), "2")).is_empty()
    assert psel.bbox().width() < dbu(process.rules["psel.w"].value)
    assert nsel.count() == 1
    assert next(iter(nsel.each())).holes() == 1


def test_nsel_of_a_df_w_bar_is_at_least_nsel_w(process, x):
    w = process.rules["df.w"].value
    layout, top = new_layout()
    box(layout, top, "nd", "0", "0", str(w), "3", process)
    derive(layout, process)
    nsel = region(layout, top, "nsel", process)
    width = nsel.bbox().width()
    assert width == dbu(w) + 2 * x
    assert width >= dbu(process.rules["nsel.w"].value)


def test_existing_generated_shapes_are_replaced(process):
    layout, top = new_layout()
    child = layout.create_cell("CHILD")
    box(layout, top, "nd", "0", "0", "1", "1", process)
    box(layout, top, "nsel", "10", "10", "11", "11", process)
    box(layout, child, "gate", "20", "20", "21", "21", process)
    top.insert(kdb.CellInstArray(child.cell_index(), kdb.Trans()))
    derive(layout, process)
    nsel = region(layout, top, "nsel", process)
    assert (nsel & rect("10", "10", "11", "11")).is_empty()
    assert not nsel.is_empty()
    assert region(layout, top, "gate", process).is_empty()


def test_results_carry_the_gds_numbers_of_layers_toml(process):
    layout, top = new_layout()
    box(layout, top, "nd", "0", "0", "1", "1", process)
    derive(layout, process)
    assert process.layers["nsel"].gds == (60, 0)
    index = layout.find_layer(60, 0)
    assert index is not None
    assert not top.shapes(index).is_empty()


def test_child_cell_shapes_derive_flat_into_the_top_cell(process, x):
    layout, top = new_layout()
    child = layout.create_cell("CHILD")
    box(layout, child, "nd", "0", "0", "1", "1", process)
    top.insert(kdb.CellInstArray(child.cell_index(), kdb.Trans(kdb.Vector(dbu("5"), 0))))
    derive(layout, process)
    nsel_index = layout.find_layer(*process.layers["nsel"].gds)
    assert child.shapes(nsel_index).is_empty()
    nsel = kdb.Region(top.shapes(nsel_index))
    assert nsel.bbox() == kdb.Box(dbu("5") - x, -x, dbu("6") + x, dbu("1") + x)


def test_every_top_cell_is_derived(process):
    layout, top = new_layout()
    other = layout.create_cell("OTHER")
    box(layout, top, "nd", "0", "0", "1", "1", process)
    box(layout, other, "pd", "0", "0", "1", "1", process)
    derive(layout, process)
    assert not region(layout, top, "nsel", process).is_empty()
    assert region(layout, top, "psel", process).is_empty()
    assert not region(layout, other, "psel", process).is_empty()
    assert region(layout, other, "nsel", process).is_empty()


def test_empty_layout_has_empty_generated_layers(process):
    layout, top = new_layout()
    derive(layout, process)
    for name in GENERATED_NAMES:
        assert region(layout, top, name, process).is_empty()


def test_layout_with_another_dbu_is_rejected(process):
    layout = kdb.Layout()
    layout.dbu = 0.0005
    layout.create_cell("TOP")
    with pytest.raises(ValueError, match="dbu"):
        derive(layout, process)


def test_unknown_variant_is_rejected(process):
    layout, _ = new_layout()
    with pytest.raises(ValueError, match="variant"):
        derive(layout, process, variant="ws180g999")


def write_input(path, process) -> None:
    layout, top = new_layout()
    box(layout, top, "nd", "0", "0", "2", "1", process)
    box(layout, top, "po", "0.9", "-0.3", "1.1", "1.3", process)
    box(layout, top, "pd", "3", "0", "4", "1", process)
    box(layout, top, "nw", "2.5", "-1", "5", "2", process)
    options = kdb.SaveLayoutOptions()
    options.gds2_write_timestamps = False
    layout.write(str(path), options)


def test_derive_file_writes_dbu_0p001_and_the_generated_layers(process, tmp):
    write_input(tmp / "in.gds", process)
    derive_file(tmp / "in.gds", tmp / "out.gds", process)
    layout = kdb.Layout()
    layout.read(str(tmp / "out.gds"))
    assert layout.dbu == pytest.approx(0.001, abs=1e-12)
    top = layout.top_cell()
    assert region(layout, top, "gate", process).area() == dbu("0.2") * dbu("1")
    assert not region(layout, top, "psel", process).is_empty()


def test_derive_file_twice_is_byte_identical(process, tmp):
    write_input(tmp / "in.gds", process)
    derive_file(tmp / "in.gds", tmp / "a.gds", process)
    derive_file(tmp / "in.gds", tmp / "b.gds", process)
    assert (tmp / "a.gds").read_bytes() == (tmp / "b.gds").read_bytes()
