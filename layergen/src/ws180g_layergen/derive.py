# SPDX-License-Identifier: Apache-2.0
"""Derive the generated layers (selects, gate, taps) from the drawn intent layers.

The designer draws only intent layers; `derive` computes the generated ones once, so DRC,
retargeting and cell generation agree. The definitions are those of the shared vocabulary
(Phase 0), held in one place in `GENERATED`:

- `gate = po & df`, with `df = nd | pd`
- `psel = open(close(P.sized(x)) - nd) | (P - nd)` with `P = pd | (po & sab)` (unsilicided
  poly is p+ by default)
- `nsel = close(nd.sized(x)) - psel`
- `ntap = nd & nw`
- `ptap = pd - nw`

where `x = rules.sel.x`, `s = rules.nsel.s` (= `rules.psel.s`) and
`close(r) = r.sized(s/2).sized(-s/2)` fills every gap narrower than `s` within one select;
`open(r) = r.sized(-w/2).sized(w/2)` with `w = rules.psel.w` removes the parts of psel
narrower than `w`: the x-by-x prongs psel would get beyond an nd/pd butting edge, in the
overhang next to the nd (GF PP.1, NP.5b; found by the Task 18 retarget check). That
overhang then falls to nsel, so the selects meet on the straight butting line also beyond
the actives (GF NP.3d, PP.3d). `P - nd` keeps every p-active covered whatever its width.
`psel` is computed before `nsel`, which subtracts it, so the two never overlap and meet at
an nd/pd butting edge. All geometry is in `klayout.db.Region` at the layout dbu 0.001 um.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import klayout.db as kdb
from ws180g_process.model import Process

DBU_UM = Decimal("0.001")


@dataclass(frozen=True)
class Sizes:
    """The rule values the definitions use, in dbu."""

    x: int
    w: int
    s: int


def open_(region: kdb.Region, w: int) -> kdb.Region:
    """Remove every part of `region` narrower than `w`."""
    return region.sized(-(w // 2)).sized(w // 2)


def close(region: kdb.Region, s: int) -> kdb.Region:
    """Fill every gap narrower than `s` between the shapes of `region`."""
    return region.sized(s // 2).sized(-(s // 2))


def _psel(p: kdb.Region, nd: kdb.Region, z: Sizes) -> kdb.Region:
    """`open(close(P.sized(x)) - nd) | (P - nd)`: see the module docstring."""
    return open_(close(p.sized(z.x), z.s) - nd, z.w) | (p - nd)


Definition = Callable[[Mapping[str, kdb.Region], Sizes], kdb.Region]

#: Each generated layer and its construction, in evaluation order: a definition may use the
#: drawn layers and the generated layers listed before it.
GENERATED: dict[str, Definition] = {
    "gate": lambda r, z: r["po"] & (r["nd"] | r["pd"]),
    "psel": lambda r, z: _psel(r["pd"] | (r["po"] & r["sab"]), r["nd"], z),
    "nsel": lambda r, z: close(r["nd"].sized(z.x), z.s) - r["psel"],
    "ntap": lambda r, z: r["nd"] & r["nw"],
    "ptap": lambda r, z: r["pd"] - r["nw"],
}


def to_dbu(value: Decimal) -> int:
    """An exact um value as an integer number of database units."""
    units = value / DBU_UM
    if units != units.to_integral_value():
        raise ValueError(f"{value} um is not a whole number of {DBU_UM} um database units")
    return int(units)


def _sizes(process: Process) -> Sizes:
    s = process.rules["nsel.s"].value
    if s != process.rules["psel.s"].value:
        raise ValueError("close() needs rules.nsel.s == rules.psel.s")
    s_dbu = to_dbu(s)
    if s_dbu % 2:
        raise ValueError(f"rules.nsel.s {s} um is not an even number of database units")
    w_dbu = to_dbu(process.rules["psel.w"].value)
    if w_dbu % 2:
        raise ValueError(f"rules.psel.w {process.rules['psel.w'].value} um is not an even number "
                         "of database units")
    return Sizes(x=to_dbu(process.rules["sel.x"].value), w=w_dbu, s=s_dbu)


class _Layers(dict):
    """Drawn regions of one cell hierarchy, read flat on first use; a missing layer is empty."""

    def __init__(self, layout: kdb.Layout, cell: kdb.Cell, process: Process) -> None:
        super().__init__()
        self._layout, self._cell, self._process = layout, cell, process

    def __missing__(self, name: str) -> kdb.Region:
        if self._process.layers[name].kind != "drawn":
            raise KeyError(f"{name} is generated; a definition may use only earlier results")
        index = self._layout.find_layer(*self._process.layers[name].gds)
        if index is None:
            region = kdb.Region()
        else:
            region = kdb.Region(self._cell.begin_shapes_rec(index))
        self[name] = region
        return region


def derive(layout: kdb.Layout, process: Process, variant: str = "ws180g005") -> None:
    """Replace the generated layers of `layout`: clear them in every cell, then write each
    top cell's result, derived from the flat drawn shapes of its hierarchy, into that top
    cell."""
    if variant not in process.variants:
        raise ValueError(f"unknown variant {variant!r}")
    if abs(layout.dbu - float(DBU_UM)) > 1e-12:
        raise ValueError(f"layout dbu is {layout.dbu} um; layergen works at {DBU_UM} um")
    generated = {n for n, layer in process.layers.items() if layer.kind == "generated"}
    if generated != set(GENERATED):
        raise ValueError(f"generated layers {sorted(generated)} have no definition table match")
    sizes = _sizes(process)
    tops = list(layout.each_top_cell())
    targets = {name: layout.layer(*process.layers[name].gds) for name in GENERATED}
    # Read every top cell's drawn shapes before any output is written.
    results = []
    for top in tops:
        layers = _Layers(layout, layout.cell(top), process)
        derived = {}
        for name, definition in GENERATED.items():
            derived[name] = layers[name] = definition(layers, sizes).merged()
        results.append((top, derived))
    for index in targets.values():
        layout.clear_layer(index)
    for top, derived in results:
        cell = layout.cell(top)
        for name, region in derived.items():
            cell.shapes(targets[name]).insert(region)


def derive_file(gds_in: Path, gds_out: Path, process: Process, variant: str = "ws180g005") -> None:
    """Read `gds_in`, derive the generated layers and write `gds_out` without timestamps, so
    two runs give byte-identical files."""
    layout = kdb.Layout()
    layout.read(str(gds_in))
    derive(layout, process, variant)
    options = kdb.SaveLayoutOptions()
    options.gds2_write_timestamps = False
    layout.write(str(gds_out), options)
