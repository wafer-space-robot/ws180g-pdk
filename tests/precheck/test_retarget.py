# SPDX-License-Identifier: Apache-2.0
"""Retarget a generic layout to GF180MCU numbers (Task 18): cuts, layers, oxide."""

from decimal import Decimal
from pathlib import Path

import klayout.db as kdb
import pytest
from ws180g_precheck.mapping import load_mapping
from ws180g_precheck.retarget import RetargetStats, resize_cuts, retarget, retarget_file

MAPPING = load_mapping()


def _layout(process, boxes: list[tuple[str, tuple[int, int, int, int]]]) -> kdb.Layout:
    layout = kdb.Layout()
    layout.dbu = 0.001
    top = layout.create_cell("test")
    for name, (x1, y1, x2, y2) in boxes:
        top.shapes(layout.layer(*process.layers[name].gds)).insert(kdb.Box(x1, y1, x2, y2))
    return layout


def _region(layout: kdb.Layout, gds: tuple[int, int]) -> kdb.Region:
    index = layout.find_layer(*gds)
    if index is None:
        return kdb.Region()
    top = layout.top_cell()
    return kdb.Region(top.begin_shapes_rec(index)).merged()


def _boxes(region: kdb.Region) -> list[tuple[int, int, int, int]]:
    return sorted((p.bbox().left, p.bbox().bottom, p.bbox().right, p.bbox().top)
                  for p in region.each())


# a v1 at (1000, 2000) with 0.27 um side, the metals around it
VIA_STACK = [("m1", (0, 1000, 3000, 4000)), ("m2", (0, 1000, 3000, 4000)),
             ("v1", (1000, 2000, 1270, 2270))]


def test_v1_becomes_026_same_centre(process):
    out = retarget(_layout(process, VIA_STACK), MAPPING, process)
    assert _boxes(_region(out, (35, 0))) == [(1005, 2005, 1265, 2265)]


def test_v4_becomes_026_same_centre(process):
    layout = _layout(process, [("m4", (-1000, -1000, 2000, 2000)),
                               ("mtop", (-3000, -3000, 4000, 4000)), ("v4", (0, 0, 360, 360))])
    out = retarget(layout, MAPPING, process)
    assert _boxes(_region(out, (41, 0))) == [(50, 50, 310, 310)]


def test_contact_keeps_its_size(process):
    layout = _layout(process, [("m1", (-1000, -1000, 1000, 1000)), ("po", (-500, -500, 500, 500)),
                               ("co", (-110, -110, 110, 110))])
    out = retarget(layout, MAPPING, process)
    assert _boxes(_region(out, (33, 0))) == [(-110, -110, 110, 110)]


def test_odd_step_snaps_toward_minus_x_and_y(process):
    cut_sizes = dict(MAPPING.cut_sizes)
    cut_sizes["v1"] = cut_sizes["v1"].model_copy(update={"size": Decimal("0.225")})
    mapping = MAPPING.model_copy(update={"cut_sizes": cut_sizes})
    stats = RetargetStats()
    out = retarget(_layout(process, VIA_STACK), mapping, process, stats)
    # 0.27 - 0.225 = 0.045 um = 9 grid steps: the centred box (1022.5 ... 1247.5) moves
    # half a grid toward -x and -y
    assert _boxes(_region(out, (35, 0))) == [(1020, 2020, 1245, 2245)]
    assert all(v % 5 == 0 for b in _boxes(_region(out, (35, 0))) for v in b)
    assert stats.snapped == 1
    assert stats.cuts == 1


def test_even_step_does_not_snap(process):
    stats = RetargetStats()
    retarget(_layout(process, VIA_STACK), MAPPING, process, stats)
    assert stats.snapped == 0 and stats.cuts == 1


def test_resize_cuts_rejects_a_non_box():
    region = kdb.Region(kdb.Polygon([kdb.Point(0, -155), kdb.Point(155, 0), kdb.Point(0, 155),
                                     kdb.Point(-155, 0)]))
    with pytest.raises(ValueError, match="not a box"):
        resize_cuts(region, 260, 5)


MOS = [("nd", (0, 0, 2000, 1000)), ("po", (900, -500, 1300, 1500)),
       ("pd", (0, 5000, 2000, 6000)), ("nw", (-1000, 4000, 3000, 7000)),
       ("m1", (0, 0, 400, 400)), ("co", (90, 90, 310, 310)),
       ("mtop", (0, 10000, 3000, 13000)), ("mk_nofill", (-500, -500, 500, 500))]


@pytest.fixture
def mos_out(process):
    return retarget(_layout(process, MOS), MAPPING, process)


def test_no_generic_numbers_left(mos_out):
    present = {(info.layer, info.datatype) for info in mos_out.layer_infos()
               if not _region(mos_out, (info.layer, info.datatype)).is_empty()}
    allowed = {t.gds for e in MAPPING.layer_map.values() for t in e.to}
    allowed |= {t.gds for t in MAPPING.oxide.layers}
    assert present <= allowed
    # numbers that are generic and not a GF target number of this mapping
    assert present.isdisjoint({(1, 0), (2, 0), (3, 0), (4, 0), (5, 0), (11, 0), (19, 0),
                               (50, 0), (60, 0), (61, 0), (62, 0), (63, 0), (64, 0)})


def test_oxide_covers_everything(mos_out):
    everything = kdb.Region()
    for info in mos_out.layer_infos():
        everything += _region(mos_out, (info.layer, info.datatype))
    for gds in [(55, 0), (112, 1)]:
        oxide = _region(mos_out, gds)
        assert (everything - oxide).is_empty()
        # the drawn bounding box (-1000, -500, 3000, 13000) sized by 1.0 um
        assert _boxes(oxide) == [(-2000, -1500, 4000, 14000)]


def test_layers_land_on_their_targets(mos_out):
    assert _boxes(_region(mos_out, (81, 0))) == [(0, 10000, 3000, 13000)]
    assert _boxes(_region(mos_out, (22, 0))) == [(0, 0, 2000, 1000), (0, 5000, 2000, 6000)]
    assert not _region(mos_out, (111, 5)).is_empty()
    assert not _region(mos_out, (152, 5)).is_empty()
    # the derived selects: Nplus around nd, Pplus around pd
    assert _region(mos_out, (32, 0)).bbox().contains(kdb.Point(1000, 500))
    assert _region(mos_out, (31, 0)).bbox().contains(kdb.Point(1000, 5500))


def test_unmapped_layer_rejected(process):
    with pytest.raises(ValueError, match="ox_3v3"):
        retarget(_layout(process, [("ox_3v3", (0, 0, 1000, 1000))]), MAPPING, process)


def test_retarget_file_is_deterministic(process, tmp: Path):
    src = tmp / "in.gds"
    options = kdb.SaveLayoutOptions()
    options.gds2_write_timestamps = False
    _layout(process, MOS).write(str(src), options)
    a, b = tmp / "a.gds", tmp / "b.gds"
    stats = retarget_file(src, a, MAPPING, process)
    retarget_file(src, b, MAPPING, process)
    assert a.read_bytes() == b.read_bytes()
    assert stats.cuts == 1
