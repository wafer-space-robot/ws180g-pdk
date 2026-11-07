# SPDX-License-Identifier: Apache-2.0
"""Regression (Task 18, 2026-11-07, outcome (b), fixture): two 2 x 2 v4 arrays at the
minimum space 0.48 um, side by side at v4.s + one grid step (0.485 um) (the pass fixture
`v4.s/min_plus_grid` of Task 14, as it is now drawn).

GF180MCU reported MT30.8 (30K top metal only) on the old fixture, a single cluster whose
upper pair was 0.485 um apart and lower pair 0.48 um: sized over-under by 1 um it was not a
rectangle (a 5 nm step). An aligned 2 x 2 array at 0.485 um would split into two 2-cut
clusters for the generic `mtop.v4.array` check (clusters join cuts at up to v4.s), so the
fixture now draws two minimum-space arrays at the space under test: two clusters of four
for the generic check, one rectangle for MT30.8."""

from pathlib import Path

import klayout.db as kdb

#: Generic layer -> boxes in dbu (0.001 um).
BOXES = {
    "v4": [(x, y, x + 360, y + 360) for x in (0, 840, 1685, 2525) for y in (0, -840)],
    "m4": [(-1000, -1840, 3885, 1360)],
    "mtop": [(-3000, -3000, 5000, 3000)],
}


def build(process, path: Path) -> Path:
    layout = kdb.Layout()
    layout.dbu = 0.001
    top = layout.create_cell("test")
    for name, boxes in BOXES.items():
        for box in boxes:
            top.shapes(layout.layer(*process.layers[name].gds)).insert(kdb.Box(*box))
    path.parent.mkdir(parents=True, exist_ok=True)
    options = kdb.SaveLayoutOptions()
    options.gds2_write_timestamps = False
    layout.write(str(path), options)
    return path
