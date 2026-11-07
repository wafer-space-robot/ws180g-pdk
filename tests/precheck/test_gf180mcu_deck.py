# SPDX-License-Identifier: Apache-2.0
"""Positive control of gate check 2 (Task 18): the public GF180MCU deck, run the way the
retarget check runs it, finds known GF violations in a GF-native layout.

The layout is written by this test (no committed binary): a Metal1 line narrower than Mn.1
(0.23 um) and two COMP boxes closer than DF.3a, under Dualgate. The brief names
`tests/precheck/data/gf_control.gds`; it is written under the gitignored
`tmp/gf180mcu-retarget/control/` instead, so the checkout stays clean."""

from pathlib import Path

import klayout.db as kdb
import pytest
from ws180g_precheck.gf180mcu import run_gf180mcu_drc_many
from ws180g_precheck.mapping import load_mapping

REPO = Path(__file__).resolve().parents[2]
WORK = REPO / "tmp" / "gf180mcu-retarget" / "control"
MAPPING = load_mapping()


def write_control(path: Path) -> Path:
    layout = kdb.Layout()
    layout.dbu = 0.001
    top = layout.create_cell("gf_control")
    # Metal1 34/0: 0.20 um wide, 5 um long (Mn.1 is 0.23 um)
    top.shapes(layout.layer(34, 0)).insert(kdb.Box(0, 0, 200, 5000))
    # COMP 22/0: two 1 um squares 0.20 um apart (DF.3a is above that)
    top.shapes(layout.layer(22, 0)).insert(kdb.Box(0, 10000, 1000, 11000))
    top.shapes(layout.layer(22, 0)).insert(kdb.Box(1200, 10000, 2200, 11000))
    # Dualgate 55/0 and V5_XTOR 112/1 over everything, as retarget emits them (5 V): the
    # deck then reports the 5 V form of the COMP space, DF.3a_MV
    for gds in [(55, 0), (112, 1)]:
        top.shapes(layout.layer(*gds)).insert(kdb.Box(-1000, -1000, 3200, 12000))
    path.parent.mkdir(parents=True, exist_ok=True)
    options = kdb.SaveLayoutOptions()
    options.gds2_write_timestamps = False
    layout.write(str(path), options)
    return path


@pytest.mark.sandbox
@pytest.mark.parametrize("metal_top", MAPPING.drc.metal_top)
def test_positive_control(sandbox, metal_top):
    gds = write_control(WORK / "in" / "control" / "gf_control.gds")
    result = run_gf180mcu_drc_many([gds], WORK / "run", sandbox.run, MAPPING, metal_top)[gds]
    assert result.categories_run > 0
    # the deck names the rules per layer and voltage: Mn.1 of Metal1 is M1.1, DF.3a at 5 V
    # is DF.3a_MV
    assert "M1.1" in result.violations, result.violations
    assert "DF.3a_MV" in result.violations, result.violations
