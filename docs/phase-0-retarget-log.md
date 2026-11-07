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
  here and in `ws180g_precheck.gate.EXCLUDED` (expected only for the `dnw` module fixtures,
  whose ring topology is the module's open item).

Every (a) and (b) adds the failing case to `ws180g_precheck.regressions`
(`precheck/src/ws180g_precheck/regressions/`, in `tests/precheck/regressions/` until the
Phase 0 final fix wave) as a permanent fixture: a Python module that regenerates the layout
(spec 9.3). The gate test and the build both run them. A GF violation from a rule
the generic set cannot model in Phase 0 is listed as **unresolved, controller decision**,
with the GF rule text and the fixture.

## Decisions

| date | fixture | GF rule | outcome | reason |
|---|---|---|---|---|
| 2026-11-07 | `nd.s.pgate/min`, `nd.s.pgate/min_plus_grid` (n-tap butted to a p-FET source) | PP.1 (Pplus width 0.4) | (b) `layergen` | `psel = close(P.sized(x)) - nd` left an x-by-x (0.28 um) prong of Pplus beyond the butting edge on each side of the tap, narrower than PP.1 and than the generic `psel.w` 0.48 itself. `derive` now opens psel by `psel.w` (`open(close(P.sized(x)) - nd) \| (P - nd)`); the overhang falls to nsel and the selects meet on the straight butting line (NP.3d/PP.3d). Regression `butted_ntap_pfet`. |
| 2026-11-07 | `pd.s.ngate/min`, `pd.s.ngate/min_plus_grid`, `df.s.np/butted`, `co.s.butt/min`, `co.s.butt/min_plus_grid`, `co.no.butt/co_on_butt` (p-tap or pd butted to nd) | PP.1; NP.5b (Nplus extension beyond COMP 0.16) | (b) `layergen` | the same prong: Pplus took the corner of the overhang next to the nd, so Nplus did not extend beyond that COMP edge. Fixed by the same `derive` change. Regression `butted_ptap_nfet`. |
| 2026-11-07 | `dnw.w/min`, `dnw.w/min_plus_grid`, `dnw.s/min`, `dnw.s/min_plus_grid` | DN.3 ("Each DNWELL shall be directly surrounded by PCOMP guard ring tied to the P-substrate potential") | (c) excluded | the dnw fixtures draw a bare deep n-well; the guard-ring topology is the deep-n-well module's open item (expected by the brief). Listed in `EXCLUDED` of the test. |
| 2026-11-07 | `m4.e.v4/min`, `m4.e.v4/min_plus_grid`, `mtop.e.v4/min`, `mtop.e.v4/min_plus_grid` (30K only) | MT30.8 ("There shall be minimum 2X2 array of vias (top vias) at one location connecting to 3um thick top metal") | (b) fixture | the fixtures shifted the lower row of the 2 x 2 v4 array 0.35 um left (so a fail fixture has one cut at the margin); the deck sizes each via cluster over-under by 1 um and flags a non-rectangular cluster. Pass fixtures now draw an aligned array (the fail fixtures kept the shift until the (a) row below). Regression `v4_array_enclosure`; new Task 14 test `test_pass_fixture_v4_clusters_are_rectangular_arrays`. |
| 2026-11-07 | `v4.s/min_plus_grid` (30K only) | MT30.8 | (b) fixture | the lower pair of the cluster stayed at the minimum space 0.48 while the upper pair was at 0.485: a 5 nm step, not a rectangle. An aligned array at 0.485 would split into two 2-cut clusters for the generic `mtop.v4.array` (Task 15 rerun showed it), so the fixture now draws two minimum-space 2 x 2 arrays side by side at the space under test. Regression `v4_array_space`. |
| 2026-11-07 | all v4 fixtures (follow-up to the MT30.8 rows above; controller ruling) | MT30.8 | (a) generic rule tightened | a staggered or otherwise non-rectangular v4 cluster passed the generic `mtop.v4.array` and fails MT30.8, so it was a generic defect: the rule (KLayout-only) now requires every v4 cluster under mtop to be a full rectangular array of at least 2 x 2 (the clusters sized by v4.s/2 and merged must be rectangles: a staggered row, a missing cut or an odd-sized cut breaks the rectangle). New fail fixture `mtop.v4.array/staggered` (four markers, one per cut). All v4 fixtures now draw rectangular arrays; the forced marker sets of the v4 enclosure, space and size fail fixtures are recorded in `EXPECTED_MARKERS`. The Task 15 KLayout fixture gate passes (263 passed). The regressions `v4_array_enclosure` and `v4_array_space` stay. |

## Open points for the controller

- `layergen` limitation (recorded in `tests/layergen/test_derive.py`): an nd bar of width
  `df.w` butted to pd on both long sides gets an nsel only `df.w` wide (below `nsel.w` and GF
  NP.1), and the psel on its two sides face each other across it (below `psel.s`, GF PP.2);
  no pass fixture draws it.
- The mirror (`test_known_limitation_narrow_pd_between_nd_gets_a_df_w_wide_psel`): a pd bar
  of width `df.w` butted to nd on both long sides gets a psel that is exactly the bar, 0.36 um
  wide (below `psel.w` 0.48 and GF PP.1 0.40) with no extension beyond its short ends (GF
  PP.5b); nsel rings it, a polygon with a hole touching the pd on all four sides. Before
  Task 18 the psel at least extended x beyond the short ends; the `open` step removes that
  band with the rest of the bar-wide psel. No pass fixture draws it. The notes of
  `rules.nsel.w`, `nsel.s`, `psel.w` and `psel.s`, which claimed the select width by
  construction without exception, now say where the construction fails.

## Tally

First run (2026-11-07, 151 pass fixtures, before any decision): 9K 139 clean / 12 dirty,
11K 139 / 12, 30K 134 / 17 (PP.1, NP.5b on the 8 butted fixtures; DN.3 on the 4 dnw
fixtures; MT30.8 on 5 v4 fixtures at 30K only).

Final run (2026-11-07, cold, no cache; 147 gate fixtures = 151 pass fixtures less 4
excluded, plus 4 regression fixtures): 9K 151 clean / 0 dirty (828 s), 11K 151 / 0 (873 s),
30K 151 / 0 (791 s). Excluded under (c): 4 (dnw). Unresolved: 0.

Positive control (`tests/precheck/test_gf180mcu_deck.py`): M1.1 and DF.3a_MV reported for
every metal_top value, 700 to 704 categories run. The deck names its rules per layer and
voltage: Mn.1 of Metal1 is `M1.1`, DF.3a under Dualgate is `DF.3a_MV`.
