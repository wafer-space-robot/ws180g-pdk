# SPDX-License-Identifier: Apache-2.0
"""Per-rule pass and fail fixtures, generated from the rule table.

Every checkable rule gets small layouts that sit exactly at its value (`pass_min`), one grid
step on the legal side (`pass_min_plus_grid`) and one grid step on the illegal side
(`fail_min_minus_grid`), plus the extra cases of its kind (flush and inside ends of an
extension, a straddling enclosure, the narrow transistor of a gate length...). Task 15 runs
them through the KLayout deck: a pass fixture must be clean, a fail fixture must trip its own
rule exactly once and nothing else.

Fixtures draw only drawn layers (the generated selects, gate and taps are derived by
`ws180g_layergen` before DRC). A **clean context** is added to every fixture by `context`,
except the tap rows of the max-distance rules, which place their single tap themselves:

- every cut gets the metals above and below it (`CUT_METALS`) at 1 um enclosure, every `pad`
  an `mtop` at 5 um, unless the generator drew that metal over the cut (the metal under test);
- every nd in the substrate gets a p-tap (a pd strip below the layout) within 5 um, and every
  pd in an n-well an n-tap (an nd box in that well, the well extended upwards) within 5 um,
  unless the layout already has one.

Lengths are integers in database units (0.001 um), converted exactly from the rule values;
every vertex lies on the process grid (except in the `grid` rule's fail fixture). Files are
`<out>/<rule id>/<pass|fail>_<name>.gds`, one top cell `test`, written without timestamps so
two runs give byte-identical files.
"""

import argparse
import re
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Literal

import klayout.db as kdb
from ws180g_process.model import Process

from ws180g_rules.klayout_deck import BUTTING_ALLOWED
from ws180g_rules.layer_expr import Intersection, LayerExpr, Name, Union, Unrelated
from ws180g_rules.table import DEFAULT_VARIANT, RuleRow, RuleTable

DBU = Decimal("0.001")
UM = 1000  # dbu per um
TOP = "test"
#: Clearance between the fixture and the context taps: beyond every spacing a tap can
#: meet (pd.s.ngate and nd.s.pgate 0.665 um are the largest).
CLEAR = 1000
TAP = 600  # side of a context tap box: above df.w, its area above df.area
TAP_REACH = 5000  # a context tap lies within 5 um of every active it serves
CUT_ENCLOSURE = 1000
PAD_ENCLOSURE = 5000
#: The metals each cut (and the pad opening) needs above and below it.
CUT_METALS = {"co": ("m1",), "v1": ("m1", "m2"), "v2": ("m2", "m3"), "v3": ("m3", "m4"),
              "v4": ("m4", "mtop"), "pad": ("mtop",)}
CUTS = ("co", "v1", "v2", "v3", "v4")
#: Context metal boxes closer than this are merged into one box (beyond every metal space).
METAL_MERGE = 2200
#: Companion v4 cuts of a 2 x 2 array are shifted this far left in the lower row, so the
#: right side of the tested cut (top right) is the only one at the margin under test.
V4_SHIFT = 350
_LENGTH_CONDITION = re.compile(r"^\s*length\s*>\s*(\d+(?:\.\d+)?)\s*$")

#: The fail fixtures whose markers cannot be its own rule exactly once, with the markers the
#: KLayout deck gives (self-check of Task 14), and why the geometry forces them:
#: - a contact straddling the df or po edge has its outside part on field: co.in too (the
#:   outside part on po or df instead would make a gate or a po.s.df violation);
#: - poly enclosing a contact at under 0.24 um from df must reach the df there, so that df
#:   edge is a gate edge: co.s.gate (also 0.24 um) fires with co.po.s.df;
#: - a rotated cut is neither a square box nor of the exact bounding box: co.size too;
#: - an off-grid coordinate is shared by the two ends of an orthogonal edge, and a 45 degree
#:   edge cannot bring both coordinates back on the grid: two grid markers.
EXPECTED_MARKERS: dict[tuple[str, str], dict[str, int]] = {
    ("df.e.co", "straddle"): {"df.e.co": 1, "co.in": 1},
    ("po.e.co", "straddle"): {"po.e.co": 1, "co.in": 1},
    ("co.po.s.df", "min_minus_grid"): {"co.po.s.df": 1, "co.s.gate": 1},
    ("cut.ortho", "cut_ortho"): {"cut.ortho": 1, "co.size": 1},
    ("grid", "grid"): {"grid": 2},
}


@dataclass(frozen=True)
class Fixture:
    """One layout of rule `rule_id`: `path` is `<out>/<rule_id>/<expect>_<name>.gds`."""

    rule_id: str
    name: str
    path: Path
    expect: Literal["pass", "fail"]

    def markers(self) -> dict[str, int]:
        """The markers the deck must report: none for a pass fixture, one of its own rule
        for a fail fixture, or the forced set of `EXPECTED_MARKERS`."""
        if self.expect == "pass":
            return {}
        return EXPECTED_MARKERS.get((self.rule_id, self.name), {self.rule_id: 1})


def to_dbu(value: Decimal) -> int:
    """An exact um value as an integer number of database units."""
    units = value / DBU
    if units != units.to_integral_value():
        raise ValueError(f"{value} um is not a whole number of {DBU} um database units")
    return int(units)


def _ceil(x: int, g: int) -> int:
    return -(-x // g) * g


class Cell:
    """The drawn shapes of one fixture, by layer name, in dbu."""

    def __init__(self) -> None:
        self.shapes: dict[str, list[kdb.Polygon]] = {}

    def box(self, layer: str, x1: int, y1: int, x2: int, y2: int) -> kdb.Box:
        b = kdb.Box(min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
        if b.empty() or b.width() == 0 or b.height() == 0:
            raise ValueError(f"empty {layer} box {b}")
        self.shapes.setdefault(layer, []).append(kdb.Polygon(b))
        return b

    def add(self, layer: str, b: kdb.Box) -> kdb.Box:
        return self.box(layer, b.left, b.bottom, b.right, b.top)

    def polygon(self, layer: str, points: list[tuple[int, int]]) -> None:
        self.shapes.setdefault(layer, []).append(
            kdb.Polygon([kdb.Point(x, y) for x, y in points]))

    def region(self, layer: str) -> kdb.Region:
        region = kdb.Region()
        for p in self.shapes.get(layer, []):
            region.insert(p)
        return region.merged()

    def bbox(self) -> kdb.Box:
        box = kdb.Box()
        for polygons in self.shapes.values():
            for p in polygons:
                box += p.bbox()
        return box


class Kit:
    """The rule values a generator needs, in dbu (areas in dbu²)."""

    def __init__(self, table: RuleTable, process: Process) -> None:
        self.table = table
        self.process = process
        self.g = to_dbu(process.grid.value)

    def v(self, rid: str) -> int:
        value = self.table[rid].value
        if value is None:
            raise ValueError(f"rules.{rid} has no value")
        return to_dbu(value)

    def _rows(self, kind: str, layer: str) -> list[RuleRow]:
        return [r for r in self.table.rows if r.kind == kind and r.condition is None
                and len(r.layers) == 1 and covers(r.layers[0], layer)]

    def min_width(self, layer: str) -> int:
        rows = self._rows("min-width", layer)
        return max((to_dbu(r.value) for r in rows), default=0)

    def min_area(self, layer: str) -> int:
        """The layer's minimum area in dbu² (0 when it has none)."""
        rows = self._rows("min-area", layer)
        return max((int(r.value * 1_000_000) for r in rows), default=0)

    def cut(self, layer: str) -> int:
        """The exact size of a cut layer."""
        (row,) = self._rows("exact-size", layer)
        return to_dbu(row.value)

    def gate_length(self, p: bool) -> int:
        (row,) = [r for r in self.table.rows if r.kind == "gate-length" and _is_p(r.layers[0]) == p]
        return to_dbu(row.value)

    def comfort(self, layer: str) -> tuple[int, int]:
        """A width and length for a shape of `layer` that is not under test: at least 1 um
        and the layer's minimum width, long enough for its minimum area."""
        w = _ceil(max(UM, self.min_width(layer)), self.g)
        length = _ceil(max(3 * UM, w, -(-self.min_area(layer) // w)), self.g)
        return w, length


def covers(expr: LayerExpr, layer: str) -> bool:
    """`expr` is `layer` or a union containing it (`df` = `nd|pd` covers both)."""
    if isinstance(expr, Name):
        return expr.name == layer
    if isinstance(expr, Union):
        return covers(expr.a, layer) or covers(expr.b, layer)
    return False


def drawable(expr: LayerExpr) -> str:
    """The drawn layer a generator draws for `expr`: the layer of a name, the first operand
    of a union (`df` draws nd), the shapes of an `unrelated` (drawn away from the other)."""
    if isinstance(expr, Name):
        return expr.name
    if isinstance(expr, (Union, Unrelated)):
        return drawable(expr.a)
    raise ValueError(f"no drawn layer for {expr}")


def _is_p(expr: LayerExpr) -> bool:
    """A p-channel expression: `x & nw` (the n-channel ones are `x - nw`)."""
    return isinstance(expr, Intersection) and Name("nw") in (expr.a, expr.b)


Case = tuple[str, str, Cell]  # (expect, name, cell)


def _steps(v: int, g: int) -> list[tuple[str, str, int]]:
    return [("pass", "min", v), ("pass", "min_plus_grid", v + g),
            ("fail", "min_minus_grid", v - g)]


# --- building blocks


@dataclass(frozen=True)
class Mos:
    active: kdb.Box
    poly: kdb.Box
    gate: kdb.Box


def mos(c: Cell, k: Kit, *, p: bool, w: int = UM, length: int | None = None,
        left: int = UM, right: int = UM, cap_bottom: int = 500, cap_top: int = 500,
        x0: int = 0, y0: int = 0) -> Mos:
    """A transistor: active (pd if `p`, else nd) `left + length + right` wide and `w` high
    from (x0, y0), a vertical poly `length` wide crossing it `left` from its left edge with
    end caps `cap_bottom` and `cap_top` (negative: the poly ends inside the active). A
    negative `right` makes the active end inside the poly. The n-well of a p-transistor is
    drawn by `nwell_around` once every shape is placed."""
    length = k.gate_length(p) if length is None else length
    active = c.box("pd" if p else "nd", x0, y0, x0 + left + length + right, y0 + w)
    poly = c.box("po", x0 + left, y0 - cap_bottom, x0 + left + length, y0 + w + cap_top)
    return Mos(active, poly, active & poly)


def nwell_around(c: Cell, margin: int = UM) -> kdb.Box:
    """An n-well around every drawn shape so far, `margin` beyond their bounding box."""
    return c.add("nw", c.bbox().enlarged(margin, margin))


def v4_cluster(c: Cell, k: Kit, right: int, top: int, shift: int = V4_SHIFT,
               first: kdb.Box | None = None) -> list[kdb.Box]:
    """A 2 x 2 v4 array at the minimum space whose top-right cut (returned first) ends at
    (right, top); the lower row is shifted `shift` to the left so that the top-right cut is
    the only rightmost one. `first` replaces the top-right cut (the exact-size fixtures)."""
    a, s = k.cut("v4"), k.v("v4.s")
    tr = kdb.Box(right - a, top - a, right, top)
    tl = tr.moved(-(a + s), 0)
    br = tr.moved(-shift, -(a + s))
    bl = br.moved(-(a + s), 0)
    boxes = [first or tr, tl, br, bl]
    for b in boxes:
        c.add("v4", b)
    return boxes


def cut(c: Cell, k: Kit, layer: str, x: int, y: int, base: str | None = None,
        w: int | None = None, h: int | None = None) -> kdb.Box:
    """A cut of exact size (or w x h) with its lower-left corner at (x, y); a contact on
    `base` (po or nd) gets that base at 1 um enclosure."""
    size = k.cut(layer)
    b = c.box(layer, x, y, x + (w or size), y + (h or size))
    if base is not None:
        c.add(base, b.enlarged(CUT_ENCLOSURE, CUT_ENCLOSURE))
    return b


def bars(c: Cell, k: Kit, a: str, b: str, s: int) -> None:
    """A vertical bar of `a` and one of `b` to its right at space `s`, facing along their
    long edges."""
    wa, la = k.comfort(a)
    wb, lb = k.comfort(b)
    h = max(la, lb)
    c.box(a, 0, 0, wa, h)
    c.box(b, wa + s, 0, wa + s + wb, h)


# --- per-kind generators


def _min_width(row: RuleRow, k: Kit) -> list[Case]:
    layer = drawable(row.layers[0])
    v = to_dbu(row.value)
    cases = []
    if row.condition is not None:
        match = _LENGTH_CONDITION.match(row.condition)
        if match is None:
            raise ValueError(f"{row.id}: unsupported condition {row.condition!r}")
        threshold = to_dbu(Decimal(match[1]))
        for expect, name, w in _steps(v, k.g):
            c = Cell()
            c.box(layer, 0, 0, threshold + UM, w)
            cases.append((expect, name, c))
        c = Cell()
        c.box(layer, 0, 0, threshold - UM, k.min_width(layer))
        cases.append(("pass", "short", c))
        return cases
    area = k.min_area(layer)
    for expect, name, w in _steps(v, k.g):
        length = _ceil(max(3 * UM, 5 * v, -(-area // w)), k.g)
        c = Cell()
        c.box(layer, 0, 0, length, w)
        cases.append((expect, name, c))
    return cases


def _gate_length(row: RuleRow, k: Kit) -> list[Case]:
    p = _is_p(row.layers[0])
    cases = []
    for expect, name, length in _steps(to_dbu(row.value), k.g):
        c = Cell()
        mos(c, k, p=p, w=2 * UM, length=length)
        cases.append((expect, name, c))
    c = Cell()
    mos(c, k, p=p, w=k.min_width("nd"), length=2 * UM)
    cases.append(("pass", "narrow", c))
    if p:
        for _, _, c in cases:
            nwell_around(c)
    return cases


def _space_cuts(c: Cell, k: Kit, layer: str, s: int) -> None:
    if layer == "v4":
        # Above the minimum: two 2 x 2 arrays at the minimum space, side by side at the
        # space under test (each a cluster of four for mtop.v4.array, together one
        # rectangle for GF MT30.8). At or below it: P and Q at the space under test, R below
        # P and S below Q, R-S at the minimum, one cluster of four (one v4.s marker when
        # failing).
        a, smin = k.cut("v4"), k.v("v4.s")
        rows = (0, -(a + smin))
        if s > smin:
            right = 2 * a + smin + s
            columns = (0, a + smin, right, right + a + smin)
            points = [(x, y) for x in columns for y in rows]
        else:
            points = [(0, 0), (a + s, 0), (0, rows[1]), (a + smin, rows[1])]
        for x, y in points:
            c.box("v4", x, y, x + a, y + a)
        return
    base = "po" if layer == "co" else None
    a = k.cut(layer)
    first = c.box(layer, 0, 0, a, a)
    second = c.box(layer, a + s, 0, 2 * a + s, a)
    if base:
        c.add(base, (first + second).enlarged(CUT_ENCLOSURE, CUT_ENCLOSURE))


def _min_space(row: RuleRow, k: Kit) -> list[Case]:
    v = to_dbu(row.value)
    special = _SPACE_SPECIAL.get(row.id)
    steps = _steps(v, k.g)
    if row.id in BUTTING_ALLOWED:
        steps.append(("pass", "butted", 0))
    cases = []
    for expect, name, s in steps:
        c = Cell()
        if special is not None:
            special(c, k, row, s)
        elif len(row.layers) == 1 and drawable(row.layers[0]) in CUTS:
            _space_cuts(c, k, drawable(row.layers[0]), s)
        elif len(row.layers) == 1:
            layer = drawable(row.layers[0])
            bars(c, k, layer, layer, s)
        else:
            bars(c, k, drawable(row.layers[0]), drawable(row.layers[1]), s)
        cases.append((expect, name, c))
    if row.edges == "exclude":
        c = Cell()
        mos(c, k, p=False, cap_bottom=UM, cap_top=UM)
        cases.append(("pass", "own_endcap", c))
    return cases


def _field_poly(c: Cell, k: Kit, row: RuleRow, s: int) -> None:
    """po.s.df: a transistor with long end caps and a field poly bar `s` right of its
    active."""
    m = mos(c, k, p=False, cap_bottom=UM, cap_top=UM)
    w = k.min_width("po")
    c.box("po", m.active.right + s, m.poly.bottom, m.active.right + s + w, m.poly.top)


def _tap_to_gate(c: Cell, k: Kit, row: RuleRow, s: int) -> None:
    """nd.s.pgate / pd.s.ngate: a transistor whose drain ends `s` beyond the gate with a
    tap of the other type butted to it (an n-tap in the well of a p-transistor)."""
    tap = drawable(row.layers[0])
    p = tap == "nd"
    m = mos(c, k, p=p, right=s)
    c.box(tap, m.active.right, m.active.bottom, m.active.right + TAP, m.active.top)
    if p:
        nwell_around(c)


def _contact_to_gate(c: Cell, k: Kit, row: RuleRow, s: int) -> None:
    """co.s.gate: a contact on the drain, `s` from the gate."""
    a = k.cut("co")
    m = mos(c, k, p=False, right=s + a + 500)
    cut(c, k, "co", m.gate.right + s, m.active.bottom + (m.active.height() - a) // 2)


def _poly_contact_to_df(c: Cell, k: Kit, row: RuleRow, s: int) -> None:
    """co.po.s.df: a contact on the top end cap of a transistor, `s` above the active."""
    a = k.cut("co")
    m = mos(c, k, p=False, cap_top=s + a + 500)
    cut(c, k, "co", m.poly.left + (m.poly.width() - a) // 2, m.active.top + s)


def _contact_to_sab(c: Cell, k: Kit, row: RuleRow, s: int) -> None:
    """sab.s.co: a poly resistor (a poly bar crossing sab) with a contact on its poly `s`
    right of the sab."""
    a = k.cut("co")
    c.box("sab", 0, 0, 2 * UM, 2 * UM)
    c.box("po", -UM, 600, 2 * UM + s + a + 500, 1400)
    cut(c, k, "co", 2 * UM + s, 1000 - a // 2)


_SPACE_SPECIAL: dict[str, Callable[[Cell, Kit, RuleRow, int], None]] = {
    "po.s.df": _field_poly,
    "nd.s.pgate": _tap_to_gate,
    "pd.s.ngate": _tap_to_gate,
    "co.s.gate": _contact_to_gate,
    "co.po.s.df": _poly_contact_to_df,
    "sab.s.co": _contact_to_sab,
}


def _inner(c: Cell, k: Kit, outer: str, inner: str, shift: int = V4_SHIFT) -> list[kdb.Box]:
    """The inner shapes of an enclosure fixture, the tested one first (its right side is
    the one under test): a cut of exact size, a 2 x 2 v4 array, a minimum pad, or a 1 um
    box."""
    if inner == "v4":
        return v4_cluster(c, k, 0, 0, shift=shift)
    if inner in CUTS:
        base = "po" if inner == "co" and outer not in ("po", "nd", "pd") else None
        a = k.cut(inner)
        return [cut(c, k, inner, -a, -a, base=base)]
    side = max(UM, k.min_width(inner))
    return [c.box(inner, -side, -side, 0, 0)]


def _min_enclosure(row: RuleRow, k: Kit) -> list[Case]:
    if row.edges == "sides":
        return _enclosure_of_sides(row, k)
    outer, inner = (drawable(e) for e in row.layers)
    v = to_dbu(row.value)
    other = UM if v + k.g < UM else _ceil(2 * v, k.g)
    cases = []
    for expect, name, m in [*_steps(v, k.g), ("fail", "straddle", None)]:
        c = Cell()
        # a pass case gets an aligned v4 array (GF MT30.8 wants a rectangular array); a
        # fail case keeps the shifted lower row, so the tested cut alone is at the margin
        boxes = _inner(c, k, outer, inner, shift=0 if expect == "pass" else V4_SHIFT)
        bb = kdb.Box()
        for b in boxes:
            bb += b
        tested = boxes[0]
        if m is None:  # the tested shape crosses the outer edge
            t = tested.width() // 2
            if len(boxes) > 1:
                t = min(t, V4_SHIFT - v) // k.g * k.g
            right = tested.right - t
        else:
            right = tested.right + m
        c.box(outer, bb.left - other, bb.bottom - other, right, bb.top + other)
        cases.append((expect, name, c))
    return cases


def _enclosure_of_sides(row: RuleRow, k: Kit) -> list[Case]:
    """sab.e.po / sab.e.df: a vertical bar of the edge layer crossing sab, 1 um beyond it at
    both ends; the sab is `m` beyond the bar's right side and 1 um beyond its left side.
    No straddle case: the inner layer `x & sab` never crosses the sab edge."""
    outer = drawable(row.layers[0])
    bar = "nd" if row.edge_layer == "df" else row.edge_layer
    cases = []
    for expect, name, m in _steps(to_dbu(row.value), k.g):
        c = Cell()
        c.box(bar, 0, -UM, UM, 3 * UM)
        c.box(outer, -UM, 0, UM + m, 2 * UM)
        cases.append((expect, name, c))
    return cases


def _min_extension(row: RuleRow, k: Kit) -> list[Case]:
    a_expr, b_expr = row.layers
    v = to_dbu(row.value)
    steps = [*_steps(v, k.g), ("fail", "flush", 0)]
    if b_expr == Name("gate"):
        steps.append(("fail", "end_inside", None))
    cases = []
    for expect, name, e in steps:
        c = Cell()
        if b_expr == Name("gate"):
            if covers(a_expr, "po"):  # the end cap
                mos(c, k, p=False, length=UM, cap_top=-300 if e is None else e)
            else:  # the active beyond the gate
                mos(c, k, p=False, length=UM, right=-360 if e is None else e)
        else:  # a bar of a crossing b, 1 um beyond it on the left, e on the right
            a, b = drawable(a_expr), drawable(b_expr)
            c.box(b, 0, -UM, 2 * UM, 2 * UM)
            c.box(a, -UM, 0, 2 * UM + e, UM)
        cases.append((expect, name, c))
    return cases


def _min_area(row: RuleRow, k: Kit) -> list[Case]:
    layer = drawable(row.layers[0])
    area = int(row.value * 1_000_000)
    side = k.g
    while side * side < area:
        side += k.g
    c = Cell()
    big = max(side, k.min_width(layer))
    c.box(layer, 0, 0, big, big)
    cases = [("pass", "min", c)]
    if row.implied_by is None:
        small = side - k.g
        if small < k.min_width(layer):
            raise ValueError(f"{row.id}: a square below the area is below the width")
        c = Cell()
        c.box(layer, 0, 0, small, small)
        cases.append(("fail", "area_minus", c))
    return cases


def _exact_size(row: RuleRow, k: Kit) -> list[Case]:
    layer = drawable(row.layers[0])
    v = to_dbu(row.value)
    cases = []
    for expect, name, w, h in (("pass", "exact", v, v), ("fail", "oversize", v + k.g, v + k.g),
                               ("fail", "rect", v, v + k.g)):
        c = Cell()
        if layer == "v4":  # the top-right cut of an array grows right and up
            v4_cluster(c, k, 0, 0, shift=0, first=kdb.Box(-v, -v, -v + w, -v + h))
        else:
            cut(c, k, layer, 0, 0, base="po" if layer == "co" else None, w=w, h=h)
        cases.append((expect, name, c))
    return cases


def _max_distance(row: RuleRow, k: Kit) -> list[Case]:
    """A 1 um active and a single tap whose near edge is `d` from the active's far edge,
    taller than the active so the distance is measured along the axis."""
    shapes, _ = row.layers
    active = drawable(shapes.a) if isinstance(shapes, Intersection) else shapes.names()[0]
    tap = "nd" if active == "pd" else "pd"
    in_well = _is_p(shapes)
    v = to_dbu(row.value)
    cases = []
    for expect, name, d in (("pass", "min", v), ("fail", "min_plus_grid", v + k.g)):
        c = Cell()
        c.box(active, 0, 0, UM, UM)
        c.box(tap, d, -500, d + TAP, UM + 500)
        if in_well:
            nwell_around(c)
        cases.append((expect, name, c))
    return cases


# --- topology: one generator per fixture name, each a pass and a fail layout


def _co_on_field(row: RuleRow, k: Kit) -> list[Case]:
    good, bad = Cell(), Cell()
    cut(good, k, "co", 0, 0, base="po")
    cut(bad, k, "co", 0, 0)
    return [("pass", "co_on_field", good), ("fail", "co_on_field", bad)]


def _co_on_gate(row: RuleRow, k: Kit) -> list[Case]:
    a = k.cut("co")
    good, bad = Cell(), Cell()
    m = mos(good, k, p=False, right=400 + a + 500)
    cut(good, k, "co", m.gate.right + 400, m.active.bottom + (m.active.height() - a) // 2)
    m = mos(bad, k, p=False)
    cut(bad, k, "co", m.gate.left + (m.gate.width() - a) // 2,
        m.gate.bottom + (m.gate.height() - a) // 2)
    return [("pass", "co_on_gate", good), ("fail", "co_on_gate", bad)]


def _butted(c: Cell) -> None:
    """An nd and a pd butted along x = 0 (the pd is the nd's p-tap)."""
    c.box("nd", -2 * UM, 0, 0, 1200)
    c.box("pd", 0, 0, 1500, 1200)


def _co_on_butt(row: RuleRow, k: Kit) -> list[Case]:
    a = k.cut("co")
    good, bad = Cell(), Cell()
    _butted(good)
    cut(good, k, "co", -300 - a, 600 - a // 2)
    _butted(bad)
    cut(bad, k, "co", -a // 2, 600 - a // 2)
    return [("pass", "co_on_butt", good), ("fail", "co_on_butt", bad)]


def _co_s_butt(row: RuleRow, k: Kit) -> list[Case]:
    """A contact in the nd at `s` from the butting edge (the rule has a value, so the
    three steps of a space)."""
    a = k.cut("co")
    cases = []
    for expect, name, s in _steps(to_dbu(row.value), k.g):
        c = Cell()
        _butted(c)
        cut(c, k, "co", -s - a, 600 - a // 2)
        cases.append((expect, name, c))
    return cases


def _sab_on_gate(row: RuleRow, k: Kit) -> list[Case]:
    good, bad = Cell(), Cell()
    good.box("sab", 0, -UM, 2 * UM, 2 * UM)
    good.box("po", -UM, 0, 3 * UM, UM)
    m = mos(bad, k, p=False, left=1200, right=1200)
    bad.box("sab", m.gate.left - 600, m.active.bottom - UM, m.gate.right + 600,
            m.active.top + UM)
    return [("pass", "sab_on_gate", good), ("fail", "sab_on_gate", bad)]


def _v4_array(row: RuleRow, k: Kit) -> list[Case]:
    good, bad = Cell(), Cell()
    v4_cluster(good, k, 0, 0, shift=0)
    a = k.cut("v4")
    bad.box("v4", 0, 0, a, a)
    return [("pass", "v4_array", good), ("fail", "v4_array", bad)]


def _grid(row: RuleRow, k: Kit) -> list[Case]:
    good, bad = Cell(), Cell()
    good.box("m1", 0, 0, 2 * UM, 2 * UM)
    bad.box("m1", 0, 0, 2 * UM + 2, 2 * UM)  # the right edge 2 dbu off the grid
    return [("pass", "grid", good), ("fail", "grid", bad)]


def _angle(row: RuleRow, k: Kit) -> list[Case]:
    """An m1 rectangle with its top-left corner cut at 45 degrees (pass) or at about 30
    degrees (fail: rise 2 um over run 3.465 um, 29.99 degrees, vertices on the grid); every
    corner is obtuse, so no width marker."""
    good, bad = Cell(), Cell()
    good.polygon("m1", [(0, 0), (6 * UM, 0), (6 * UM, 4 * UM), (2 * UM, 4 * UM), (0, 2 * UM)])
    bad.polygon("m1", [(0, 0), (6 * UM, 0), (6 * UM, 4 * UM), (3465, 4 * UM), (0, 2 * UM)])
    return [("pass", "angle", good), ("fail", "angle", bad)]


def _cut_ortho(row: RuleRow, k: Kit) -> list[Case]:
    """A square contact (pass) and one rotated by 45 degrees (fail), both on poly."""
    good, bad = Cell(), Cell()
    cut(good, k, "co", 0, 0, base="po")
    h = 155  # half diagonal: the diamond's side is 0.219 um
    bad.polygon("co", [(h, 0), (2 * h, h), (h, 2 * h), (0, h)])
    bad.add("po", kdb.Box(0, 0, 2 * h, 2 * h).enlarged(CUT_ENCLOSURE, CUT_ENCLOSURE))
    return [("pass", "cut_ortho", good), ("fail", "cut_ortho", bad)]


TOPOLOGY: dict[str, Callable[[RuleRow, Kit], list[Case]]] = {
    "co_on_field": _co_on_field,
    "co_on_gate": _co_on_gate,
    "co_on_butt": _co_on_butt,
    "co_s_butt": _co_s_butt,
    "sab_on_gate": _sab_on_gate,
    "v4_array": _v4_array,
    "grid": _grid,
    "angle": _angle,
    "cut_ortho": _cut_ortho,
}

KINDS: dict[str, Callable[[RuleRow, Kit], list[Case]]] = {
    "min-width": _min_width,
    "gate-length": _gate_length,
    "min-space": _min_space,
    "min-enclosure": _min_enclosure,
    "min-extension": _min_extension,
    "min-area": _min_area,
    "exact-size": _exact_size,
    "max-distance": _max_distance,
}


def cases(row: RuleRow, k: Kit) -> list[Case]:
    """The layouts of one row before the context: by its `fixture` name when it has one
    (topology rules, and `co.s.butt`), else by its kind."""
    if row.fixture is not None:
        if row.fixture not in TOPOLOGY:
            raise ValueError(f"{row.id}: no fixture generator {row.fixture!r}")
        return TOPOLOGY[row.fixture](row, k)
    if row.kind not in KINDS:
        raise ValueError(f"{row.id}: no fixture generator for kind {row.kind!r}")
    return KINDS[row.kind](row, k)


# --- the clean context


def _merge_boxes(boxes: list[kdb.Box]) -> list[kdb.Box]:
    """Boxes that overlap or lie closer than METAL_MERGE, replaced by their bounding box,
    until none do."""
    boxes = sorted(boxes, key=lambda b: (b.left, b.bottom, b.right, b.top))
    changed = True
    while changed:
        changed = False
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                if boxes[i].enlarged(METAL_MERGE, METAL_MERGE).overlaps(boxes[j]):
                    merged = boxes[i] + boxes[j]
                    boxes = [b for n, b in enumerate(boxes) if n not in (i, j)] + [merged]
                    boxes.sort(key=lambda b: (b.left, b.bottom, b.right, b.top))
                    changed = True
                    break
            if changed:
                break
    return boxes


def _metals(c: Cell) -> None:
    """The metals above and below every cut (and over every pad) the generator left bare."""
    wanted: dict[str, list[kdb.Box]] = {}
    for layer, metals in CUT_METALS.items():
        enclosure = PAD_ENCLOSURE if layer == "pad" else CUT_ENCLOSURE
        for polygon in c.region(layer).each():
            for metal in metals:
                if c.region(metal).interacting(kdb.Region(polygon)).is_empty():
                    wanted.setdefault(metal, []).append(
                        polygon.bbox().enlarged(enclosure, enclosure))
    for metal in sorted(wanted):
        for b in _merge_boxes(wanted[metal]):
            c.add(metal, b)


def _ntaps(c: Cell, g: int) -> None:
    """An n-tap in every n-well with pd that has none within TAP_REACH: the well is
    extended upwards beyond the layout and the tap placed in the extension."""
    nd, pd = c.region("nd"), c.region("pd")
    for well in c.region("nw").each():
        w = kdb.Region(well)
        inside = pd & w
        if inside.is_empty() or (inside - (nd & w).sized(TAP_REACH)).is_empty():
            continue
        wb, top = well.bbox(), c.bbox().top
        x = (wb.center().x - TAP // 2) // g * g  # centred, on the grid
        tap = kdb.Box(x, top + CLEAR, x + TAP, top + CLEAR + TAP)
        ext = kdb.Box(wb.left, wb.top, wb.right, tap.top + 500)
        others = ((nd | pd) - w) | (c.region("nw") - w)
        if not (others & kdb.Region(ext)).is_empty():
            raise ValueError(f"the n-tap extension of the well {wb} overlaps other shapes")
        c.add("nw", ext)
        c.add("nd", tap)
        if not (inside - kdb.Region(tap).sized(TAP_REACH)).is_empty():
            raise ValueError(f"the n-tap of the well {wb} is farther than {TAP_REACH} dbu")


def _ptaps(c: Cell) -> None:
    """A p-tap strip below the layout when some nd in the substrate has no p-tap within
    TAP_REACH."""
    nw = c.region("nw")
    substrate_nd = c.region("nd") - nw
    if (substrate_nd - (c.region("pd") - nw).sized(TAP_REACH)).is_empty():
        return
    bb = c.bbox()
    strip = c.box("pd", bb.left, bb.bottom - CLEAR - TAP, max(bb.right, bb.left + UM),
                  bb.bottom - CLEAR)
    if not (substrate_nd - kdb.Region(strip).sized(TAP_REACH)).is_empty():
        raise ValueError(f"the p-tap strip {strip} is farther than {TAP_REACH} dbu")


def context(c: Cell, grid: int, taps: bool = True) -> None:
    """Add the clean context to a fixture: metals over the bare cuts and pads, then (with
    `taps`) the n-taps and the p-tap strip."""
    _metals(c)
    if taps:
        _ntaps(c, grid)
        _ptaps(c)


# --- output


def _write(c: Cell, process: Process, path: Path) -> None:
    layout = kdb.Layout()
    layout.dbu = float(DBU)
    top = layout.create_cell(TOP)
    for name, layer in process.layers.items():
        if name in c.shapes:
            top.shapes(layout.layer(*layer.gds)).insert(c.region(name))
    path.parent.mkdir(parents=True, exist_ok=True)
    options = kdb.SaveLayoutOptions()
    options.gds2_write_timestamps = False
    layout.write(str(path), options)


def write_fixtures(table: RuleTable, process: Process, out_dir: Path) -> list[Fixture]:
    """Write the fixtures of every checkable row of `table` into `out_dir` and return them
    in rule-table order. A row implied by another rule (`implied_by`) gets its pass
    fixtures only."""
    k = Kit(table, process)
    fixtures = []
    for row in table.checkable():
        for expect, name, c in cases(row, k):
            if expect == "fail" and row.implied_by is not None:
                continue
            context(c, k.g, taps=row.kind != "max-distance")
            path = out_dir / row.id / f"{expect}_{name}.gds"
            _write(c, process, path)
            fixtures.append(Fixture(row.id, name, path, expect))
    return fixtures


def main(argv: list[str] | None = None) -> int:
    """`ws180g-fixtures [--variant V] --out DIR`: write the per-rule fixtures of variant V
    (default ws180g005) into DIR and print a one-line summary."""
    from ws180g_process.load import load_process

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--variant", default=DEFAULT_VARIANT,
                        help=f"process variant (default: {DEFAULT_VARIANT})")
    parser.add_argument("--out", type=Path, required=True, help="output directory")
    args = parser.parse_args(argv)
    process = load_process()
    fixtures = write_fixtures(RuleTable.from_process(process, args.variant), process,
                              args.out)
    passing = sum(f.expect == "pass" for f in fixtures)
    print(f"{args.variant}: {len(fixtures)} fixtures ({passing} pass, "
          f"{len(fixtures) - passing} fail) in {args.out}")
    return 0
