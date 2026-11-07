# SPDX-License-Identifier: Apache-2.0
"""Regression (Task 18, 2026-11-07, outcome (b), fixture): a 2 x 2 v4 array under mtop at
the minimum enclosures, m4.e.v4 0.12 and mtop.e.v4 0.30 um on the right and top (the pass
fixtures `m4.e.v4/min` and `mtop.e.v4/min` of Task 14, as they are now drawn).

GF180MCU reported MT30.8 (2 x 2 array of top vias, 30K top metal only) on the old fixtures,
whose lower row was shifted 0.35 um left: the deck sizes each via cluster over-under by 1 um
and rejects a cluster that is not a rectangle. The pass fixtures now draw an aligned array;
this layout must stay clean for every metal_top value."""

from pathlib import Path

import klayout.db as kdb

#: Generic layer -> boxes in dbu (0.001 um).
BOXES = {
    "v4": [(0, 0, 360, 360), (840, 0, 1200, 360), (0, 840, 360, 1200),
           (840, 840, 1200, 1200)],
    "m4": [(-1000, -1000, 1320, 1320)],
    "mtop": [(-2000, -2000, 1500, 1500)],
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
