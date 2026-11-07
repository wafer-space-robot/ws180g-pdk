# SPDX-License-Identifier: Apache-2.0
"""Informative (Task 18, spec 11.3 "Phase 0 runs that DRC"): the public GF180MCU IO library
through the 30K top-metal rules only. Never fails the gate: it asserts only that the run
completed and the summary was written.

`gf180mcu_fd_io.gds` (from the container's open PDK) holds 14 named top cells; one container
lists them with a small KLayout script and runs the deck once per cell with
`-rd metal_top=30K -rd decks=metaltop_30k` (the tag of `rule_decks/metaltop_30k.rb`). The
MT30 rule ids each cell reports go to `tmp/gf180mcu-retarget/reports/gf180mcu_io_mt30.json`
for the Task 23 report (the brief names `out/reports/`, which is not a sandbox workdir)."""

import json
import shlex
from pathlib import Path

import pytest
from ws180g_precheck.mapping import load_mapping
from ws180g_rules.run_klayout import CONTAINER_OUT, parse_lyrdb

REPO = Path(__file__).resolve().parents[2]
WORK = REPO / "tmp" / "gf180mcu-retarget" / "io"
SUMMARY = REPO / "tmp" / "gf180mcu-retarget" / "reports" / "gf180mcu_io_mt30.json"
IO_GDS = "/foss/pdks/gf180mcuD/libs.ref/gf180mcu_fd_io/gds/gf180mcu_fd_io.gds"
DECKS = "metaltop_30k"
MAPPING = load_mapping()

TOPS_SCRIPT = f"""# SPDX-License-Identifier: Apache-2.0
import klayout.db as kdb
layout = kdb.Layout()
layout.read({IO_GDS!r})
with open({CONTAINER_OUT + '/tops.txt'!r}, "w") as f:
    for t in layout.each_top_cell():
        name = layout.cell(t).name
        if not name.startswith("("):
            f.write(name + "\\n")
"""


@pytest.mark.sandbox
def test_io_library_mt30(sandbox):
    WORK.mkdir(parents=True, exist_ok=True)
    for old in WORK.glob("reports/*.lyrdb"):
        old.unlink()
    (WORK / "tops.py").write_text(TOPS_SCRIPT, encoding="utf-8")
    out = CONTAINER_OUT
    script = (
        f"set -e; mkdir -p {out}/reports {out}/logs; klayout -b -r {out}/tops.py; "
        f"while read -r c; do klayout -b -r {shlex.quote(MAPPING.drc.deck)} "
        f"-rd input={IO_GDS} -rd topcell=$c -rd report={out}/reports/$c.lyrdb "
        f"-rd metal_level={MAPPING.metal_level} -rd metal_top=30K -rd decks={DECKS} "
        f"-rd run_mode={MAPPING.drc.run_mode} -rd workers={MAPPING.drc.workers} "
        f"> {out}/logs/$c.log 2>&1; done < {out}/tops.txt")
    done = sandbox.run(["sh", "-c", script], WORK)
    assert done.returncode == 0, f"{done.stdout[-2000:]}\n{done.stderr[-2000:]}"
    tops = (WORK / "tops.txt").read_text(encoding="utf-8").split()
    assert tops
    cells = {}
    for cell in tops:
        result = parse_lyrdb(WORK / "reports" / f"{cell}.lyrdb")
        cells[cell] = {"categories_run": result.categories_run,
                       "violations": dict(sorted(result.violations.items()))}
    reported = sorted({rule for c in cells.values() for rule in c["violations"]})
    SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY.write_text(json.dumps(
        {"gds": IO_GDS, "deck": MAPPING.drc.deck, "metal_level": MAPPING.metal_level,
         "metal_top": "30K", "decks": DECKS, "reported_rule_ids": reported, "cells": cells},
        indent=1, sort_keys=True) + "\n", encoding="utf-8")
    assert SUMMARY.is_file()
