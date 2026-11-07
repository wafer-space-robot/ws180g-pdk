# Phase 0 retarget log (gate check 2)

Gate check 2 claims: every generic pass fixture of Task 14, retargeted to GF180MCU with
`precheck/data/gf180mcu.toml`, passes the public GF180MCU KLayout deck
(`/foss/pdks/gf180mcuD/libs.tech/klayout/tech/drc/gf180mcu.drc`) for every top-metal
thickness (`metal_top` 9K, 11K, 30K), with `metal_level=5LM`, `run_mode=flat` and
`decks=all,-density,-dummy,-antenna` (density, fill and antenna need a whole die: Phase 1).
The test is `tests/precheck/test_fixture_retarget.py`; the positive control, which proves the
deck reports known violations the same way, is `tests/precheck/test_gf180mcu_deck.py`.

## Failure policy

Each GF violation on a pass fixture ends in exactly one of:

- **(a)** a generic rule value is raised, or a new generic rule is added, with public
  evidence, in `process/data/ws180g/rules.toml` (the KLayout fixture test of Task 15 must
  still pass afterwards);
- **(b)** the fixture's clean context or `layergen` is corrected, because the fixture, not the
  rule set, was wrong;
- **(c)** the fixture is excluded from gate check 2, with the GF rule and the reason recorded
  here and in `EXCLUDED` of the test (expected only for the `dnw` module fixtures, whose ring
  topology is the module's open item).

Every (a) and (b) adds the failing case to `tests/precheck/regressions/` as a permanent
fixture: a Python module that regenerates the layout (spec 9.3). A GF violation from a rule
the generic set cannot model in Phase 0 is listed as **unresolved, controller decision**,
with the GF rule text and the fixture.

## Decisions

| date | fixture | GF rule | outcome | reason |
|---|---|---|---|---|
