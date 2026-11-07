# SPDX-License-Identifier: Apache-2.0
"""Regression (Task 18, 2026-11-07, outcome (b), layergen): a p-FET whose source diffusion
is butted by an n-well tap (the pass fixture `nd.s.pgate/min` of Task 14).

GF180MCU reported PP.1 (Pplus width 0.4) twice: the derived psel had an x-by-x prong
(0.28 um) beyond the butting edge on each side of the tap. `ws180g_layergen.derive` now
opens psel by psel.w, so the selects meet on the straight butting line."""

from pathlib import Path

import klayout.db as kdb

#: Generic layer -> boxes in dbu (0.001 um).
BOXES = {
    "nw": [(-1000, -1500, 3865, 2500)],
    "pd": [(0, 0, 2265, 1000)],
    "nd": [(2265, 0, 2865, 1000)],
    "po": [(1000, -500, 1600, 1500)],
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
