# SPDX-License-Identifier: Apache-2.0
"""Permanent regression fixtures of gate check 2 (Task 18, spec 9.3).

Every GF180MCU violation on a pass fixture that ended in outcome (a) (a generic rule raised
or added) or (b) (a fixture's clean context or layergen corrected) adds one module here. A
module defines `build(process, path) -> Path`, which writes the generic ws180g005 layout
that failed (no committed binary), and a docstring naming the fixture, the GF rule, the
outcome and the date. `ws180g_precheck.gate.write_regressions` writes every module's layout;
the gate test (`tests/precheck/test_fixture_retarget.py`) and the build (`ws180g-build`)
retarget them with the pass fixtures and require them clean for every metal_top value. The
decision log is `docs/phase-0-retarget-log.md`. (Until the Phase 0 final fix wave these
modules lived in `tests/precheck/regressions/`.)"""
