# SPDX-License-Identifier: Apache-2.0
"""Regression (Task 18, 2026-11-07, outcome (b), layergen): an n-FET whose source diffusion
is butted by a substrate tap (the pass fixture `pd.s.ngate/min` of Task 14).

GF180MCU reported PP.1 (Pplus width 0.4) and NP.5b (Nplus extension beyond COMP 0.16)
twice each: the derived psel took an x-by-x prong (0.28 um) of the overhang beyond the
butting edge, next to the n-FET's diffusion, so Nplus did not extend beyond that COMP edge.
`ws180g_layergen.derive` now opens psel by psel.w; the overhang falls to nsel."""

from pathlib import Path

import klayout.db as kdb

#: Generic layer -> boxes in dbu (0.001 um).
BOXES = {
    "nd": [(0, 0, 2385, 1000)],
    "pd": [(2385, 0, 2985, 1000)],
    "po": [(1000, -500, 1720, 1500)],
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
