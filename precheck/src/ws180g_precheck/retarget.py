# SPDX-License-Identifier: Apache-2.0
"""Retarget a generic ws180g layout to a target process's layer numbers and cut sizes.

`retarget(layout, mapping, process)` returns a new layout with, per top cell (flattened):

1. the generated layers derived from the drawn ones (`ws180g_layergen.derive`, on a copy);
2. every mapped generic layer copied to its target layer(s) (`nd` and `pd` both to COMP;
   a layer with two targets, such as `mk_nofill`, to both);
3. every cut layer of `mapping.cut_sizes` regenerated at the target's exact size, centred on
   the drawn cut (`resize_cuts`); when the size change is an odd number of target-grid
   steps, the cut moves half a grid toward -x and -y so both edges land on the grid
   (`RetargetStats.snapped` counts those cuts);
4. the oxide layers of `mapping.oxide`: one box each, the bounding box of all drawn shapes
   sized by `mapping.oxide.margin` (ws180g005 is all 5 V);
5. nothing else: the generic layers are dropped (the output is built fresh, so no generic
   number survives; the generated layers of `mapping.drop` have no target).

A generic layer present in the layout that is neither mapped nor dropped is an error.
`retarget_file` reads and writes GDS (no timestamps: two runs give identical bytes).
"""

import argparse
from dataclasses import dataclass
from pathlib import Path

import klayout.db as kdb
from ws180g_layergen.derive import derive, to_dbu
from ws180g_process.model import Process

from ws180g_precheck.mapping import Mapping, load_mapping


@dataclass
class RetargetStats:
    """What a retarget did: the cuts it resized, and how many of them it snapped."""

    cuts: int = 0
    snapped: int = 0


def resize_cuts(region: kdb.Region, size: int, grid: int) -> tuple[kdb.Region, int]:
    """Every box of `region` regenerated as a `size` square (dbu) centred on it, snapped
    toward -x/-y onto `grid` (dbu) when the centred edge falls between grid points. Returns
    the new region and the number of cuts that were snapped."""
    if size % grid:
        raise ValueError(f"cut size {size} dbu is not on the {grid} dbu grid")
    out = kdb.Region()
    snapped = 0
    for polygon in region.each():
        if not polygon.is_box():
            raise ValueError(f"cut {polygon} is not a box")
        b = polygon.bbox()
        # twice the centred left/bottom edge, so a half-dbu centre stays exact
        left2, bottom2 = b.left + b.right - size, b.bottom + b.top - size
        left, bottom = (left2 // (2 * grid)) * grid, (bottom2 // (2 * grid)) * grid
        if left2 != 2 * left or bottom2 != 2 * bottom:
            snapped += 1
        out.insert(kdb.Box(left, bottom, left + size, bottom + size))
    return out, snapped


def _flat(layout: kdb.Layout, cell: kdb.Cell, gds: tuple[int, int]) -> kdb.Region:
    index = layout.find_layer(*gds)
    if index is None:
        return kdb.Region()
    return kdb.Region(cell.begin_shapes_rec(index))


def _check_layers(layout: kdb.Layout, mapping: Mapping, process: Process) -> None:
    """Every non-empty layer must be a generic layer that is mapped or dropped."""
    by_gds = {layer.gds: name for name, layer in process.layers.items()}
    known = set(mapping.layer_map) | set(mapping.drop)
    problems = []
    for index in layout.layer_indexes():
        info = layout.get_info(index)
        gds = (info.layer, info.datatype)
        if all(layout.cell(t).bbox_per_layer(index).empty() for t in layout.each_top_cell()):
            continue
        name = by_gds.get(gds)
        if name is None:
            problems.append(f"{gds[0]}/{gds[1]} is not a {process.name} layer")
        elif name not in known:
            problems.append(f"{name} ({gds[0]}/{gds[1]}) has no {mapping.target} mapping")
    if problems:
        raise ValueError("; ".join(problems))


def retarget(layout: kdb.Layout, mapping: Mapping, process: Process,
             stats: RetargetStats | None = None, variant: str = "ws180g005") -> kdb.Layout:
    """The retargeted copy of `layout` (see the module docstring); `layout` is unchanged."""
    stats = stats if stats is not None else RetargetStats()
    _check_layers(layout, mapping, process)
    work = layout.dup()
    derive(work, process, variant)
    grid = to_dbu(mapping.grid.value)
    margin = to_dbu(mapping.oxide.margin)
    drawn = [n for n, layer in process.layers.items() if layer.kind == "drawn"]

    out = kdb.Layout()
    out.dbu = work.dbu
    for top_index in work.each_top_cell():
        top = work.cell(top_index)
        cell = out.create_cell(top.name)
        regions: dict[tuple[int, int], kdb.Region] = {}
        for name, entry in mapping.layer_map.items():
            region = _flat(work, top, process.layers[name].gds)
            if name in mapping.cut_sizes:
                region, snapped = resize_cuts(region.merged(),
                                              to_dbu(mapping.cut_sizes[name].size), grid)
                stats.cuts += region.count()
                stats.snapped += snapped
            for target in entry.to:
                regions.setdefault(target.gds, kdb.Region()).insert(region)
        bbox = kdb.Box()
        for name in drawn:
            bbox += _flat(work, top, process.layers[name].gds).bbox()
        if not bbox.empty():
            for target in mapping.oxide.layers:
                regions.setdefault(target.gds, kdb.Region()).insert(bbox.enlarged(margin, margin))
        for gds in sorted(regions):
            merged = regions[gds].merged()
            if not merged.is_empty():
                cell.shapes(out.layer(*gds)).insert(merged)
    return out


def retarget_file(gds_in: Path, gds_out: Path, mapping: Mapping, process: Process,
                  variant: str = "ws180g005") -> RetargetStats:
    """Read `gds_in`, retarget it and write `gds_out` without timestamps."""
    layout = kdb.Layout()
    layout.read(str(gds_in))
    stats = RetargetStats()
    out = retarget(layout, mapping, process, stats, variant)
    gds_out.parent.mkdir(parents=True, exist_ok=True)
    options = kdb.SaveLayoutOptions()
    options.gds2_write_timestamps = False
    out.write(str(gds_out), options)
    return stats


def main(argv: list[str] | None = None) -> int:
    """`ws180g-retarget --mapping gf180mcu IN.gds OUT.gds`."""
    from ws180g_process.load import load_process

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mapping", default="gf180mcu",
                        help="mapping name in precheck/data/ or a TOML path (default gf180mcu)")
    parser.add_argument("--variant", default="ws180g005", help="generic process variant")
    parser.add_argument("gds_in", type=Path)
    parser.add_argument("gds_out", type=Path)
    args = parser.parse_args(argv)
    mapping = load_mapping(args.mapping)
    stats = retarget_file(args.gds_in, args.gds_out, mapping, load_process(), args.variant)
    print(f"{args.gds_in} -> {args.gds_out} ({mapping.target}): {stats.cuts} cuts resized, "
          f"{stats.snapped} snapped")
    return 0
