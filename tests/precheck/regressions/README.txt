SPDX-License-Identifier: Apache-2.0

Permanent regression fixtures of gate check 2 (Task 18, spec 9.3).

Every GF180MCU violation on a pass fixture that ended in outcome (a) (a generic rule raised
or added) or (b) (a fixture's clean context or layergen corrected) adds one Python module
here. A module defines `build(process, path) -> Path`, which writes the generic ws180g005
layout that failed (no committed binary), and a docstring naming the fixture, the GF rule,
the outcome and the date. tests/precheck/test_fixture_retarget.py retargets every module's
layout with the pass fixtures and requires it clean for every metal_top value. The decision
log is docs/phase-0-retarget-log.md.
