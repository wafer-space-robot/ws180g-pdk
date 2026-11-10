<!-- SPDX-License-Identifier: Apache-2.0 -->
# Phase 0 gate report

Date: 2026-11-07. Branch `task-23-gate-report`, on `main` `df0f77a`; the commit or tree of
each run is in [the tree of each run](#the-tree-of-each-run). Variant: `ws180g005`.

This report records the evidence for the Phase 0 gate of the design document (section 10):

> Both DRC engines pass every fixture (or the rule is marked KLayout-only); every generic pass
> fixture, retargeted, passes the public GF180MCU deck; the margin report shows the section 3.6
> margin on every covered rule and lists every uncovered one.

Every number below is quoted from a log of a run on the build host (8 CPUs, every container
job through `build/sandbox-run` with `--mem 4g --cpus 2`, at most two jobs at once). The logs
live in the gitignored `tmp/t23/` of the checkout that ran them and are not committed; the
last section gives the commands that regenerate them. The decisions the Phase 0 plan made
for the owner's review are listed once, in the plan's
[decisions list](https://github.com/wafer-space-robot/ws180g-pdk/blob/main/docs/superpowers/plans/2026-11-07-phase-0-foundations.md#decisions-this-plan-makes-for-the-owners-review-none-blocks-execution);
this report refers to them by number.

## Verdict

All three gate checks pass, with the deviations from the gate wording listed below for
the owner's agreement. The deliverable "library repositories created" (Task 22) was
done on 2026-11-10, after the runs this report quotes (see
[the library repositories](#the-library-repositories)). The
full container build exits 0,
the image ID reproduces, a warm rebuild gives an identical output tree, and the CI
sandbox job on a hosted runner rebuilt the image to the same ID and passed every
container test it selects (all but the `slow` image-reproducibility test, see [CI](#ci)).

## Gate check 1: both DRC engines pass every fixture

Command: `uv run pytest tests/rules/test_klayout_fixtures.py tests/rules/test_magic_fixtures.py tests/rules/test_engines_agree.py -rs -v -m sandbox`
(log `tmp/t23/gate1.log`, exit 0):

```text
SKIPPED [21] tests/rules/test_magic_fixtures.py:46: KLayout-only
SKIPPED [21] tests/rules/test_engines_agree.py:23: KLayout-only
========== 745 passed, 42 skipped, 1 deselected in 270.58s (0:04:30) ===========
```

Per file, counted from the same log by test id with `uv run tools/pytest_log_counts.py
tmp/t23/gate1.log` (`tmp/t23/gate1-counts.log`; no `FAILED` line):

| Test file | Passed | Skipped | Failed |
|---|---|---|---|
| `test_klayout_fixtures.py` (261 fixtures and 3 deck tests) | 264 | 0 | 0 |
| `test_magic_fixtures.py` | 241 | 21 | 0 |
| `test_engines_agree.py` | 240 | 21 | 0 |

264 + 241 + 240 = 745, the summary line's count.

Every skip has the reason `KLayout-only`. The 21 skipped fixtures per Magic file belong to the
eight KLayout-only rules (`tmp/t23/gate1-skips-by-rule.log`): `angle` 2, `co.s.butt` 3, `cut.ortho` 2, `grid` 3,
`mtop.v4.array` 3, `mtop.w.long` 4, `nw.tap.dmax` 2, `ps.tap.dmax` 2. (The final Phase 0
review counted 20; the fix wave added the pass fixture `grid/pass_grid_45`.) The agreement
test printed the three recorded `MAGIC_EXCEPTIONS` cases (`po.x.df/fail_end_inside`,
`v4.size/fail_oversize`, `v4.size/fail_rect`), listed with their reasons below. The full
build ran the same fixtures again (`tmp/t23/build1.log`): `klayout: 261 fixtures, 0 from the cache` and `magic: 240 fixtures, 0 from the cache`,
with `"wrong": {}` in both `reports/klayout-fixtures.json` and
`reports/magic-fixtures.json` of the output tree.

## Gate check 2: every generic pass fixture, retargeted, passes the public GF180MCU deck

Command: `uv run pytest tests/precheck/test_fixture_retarget.py tests/precheck/test_gf180mcu_deck.py tests/precheck/test_gf180mcu_io_mt30.py -rs -v -m sandbox`
(log `tmp/t23/gate2.log`, exit 0):

```text
================ 460 passed, 3 deselected in 2988.83s (0:49:48) ================
```

Per `metal_top` value: cases passed and regressions counted by test id with
`tools/pytest_log_counts.py` (`tmp/t23/gate2-counts.log`), violations (`dirty`) and run time
(`seconds`) from the run summary `tmp/gf180mcu-retarget/reports/gate.json`, copied to
`tmp/t23/gate2-gate.json`:

| `metal_top` | Cases passed (pass fixtures and regressions) | of which regressions | Cases with a GF violation | Run time (s) |
|---|---|---|---|---|
| 9K | 152 | 4 | 0 | 937.1 |
| 11K | 152 | 4 | 0 | 871.9 |
| 30K | 152 | 4 | 0 | 992.6 |

The 152 cases are the 148 pass fixtures not excluded and the 4 regression fixtures; the
4 `dnw` pass fixtures are excluded under policy (c) (`"excluded"` in `gate.json`,
table below). The deck runs with `metal_level=5LM`, `run_mode=flat` and
`decks=all,-density,-dummy,-antenna`. The positive control
(`test_gf180mcu_deck.py::test_positive_control`, a GF-native layout with a 0.20 µm
Metal1 line and two COMP boxes 0.20 µm apart) passed for 9K, 11K and 30K: it asserts that the deck, run
the same way, reports `M1.1` and `DF.3a_MV`. The full build ran the same
cases (`tmp/t23/build1.log`: `gf180mcu 9K: 148 fixtures and 4 regressions, 0 from the
cache`, likewise 11K and 30K), and its `reports/gf180mcu-gate.json` has 152 cases and
`"dirty": {}` for each value.

The decisions behind the fixtures and the mapping are recorded in the
[retarget log](phase-0-retarget-log.md): every GF180MCU violation met on a pass fixture
ended in a layergen or fixture correction (outcome (b)), one generic rule tightening
(outcome (a), `mtop.v4.array`), or the exclusion of the four `dnw` fixtures (outcome (c)).
Each (a) and (b) left a permanent regression fixture, listed below; the gate test and the
build run them for every `metal_top` value.

**Informative: `gf180mcu_fd_io` through the 30K top-metal rules.** `test_gf180mcu_io_mt30.py::test_io_library_mt30` passed (it only asserts that the run
completed). Its summary (written by the test to
`tmp/gf180mcu-retarget/reports/gf180mcu_io_mt30.json`, copied to `tmp/t23/gate2-io-mt30.json`):
the 14 top cells of
`gf180mcu_fd_io.gds`, `-rd metal_top=30K -rd decks=metaltop_30k`, no failed cell; 12
cells report MT30 rules (`MT30.1a`, `MT30.2`, `MT30.3`, `MT30.4`, `MT30.5`, `MT30.6`,
`MT30.8`), only `gf180mcu_fd_io__brk2` and `gf180mcu_fd_io__brk5` none. For example
`gf180mcu_fd_io__bi_t` reports `MT30.2` 57, `MT30.3` 57, `MT30.4` 57, `MT30.8` 1, and
`gf180mcu_fd_io__cor` reports `MT30.5` 4709. The run is informative: it does not
enter the gate; it is an input for the `ws180g005_fd_io` design in Phase 1.

## Gate check 3: the margin report

Command: `uv run ws180g-evidence-report --markdown tmp/t23/evidence-report.md --json tmp/t23/evidence-report.json`
(log `tmp/t23/gate3.log`, exit 0):

```text
107 rows, ok: yes (ok 91, chosen 2, exempt 13, implied 1); grid ok: yes; uncovered binding entries: 521 in scope, 108 out of scope for ws180g005
```

No row is under margin: the statuses are only `ok`, `chosen`, `exempt` and `implied`, none
of the failing ones (`under-margin`, `missing-entry`, `override-too-small`,
`achieved-mismatch`), and the report is ok. The uncovered binding entries by kind, from the headings
of the written report (`tmp/t23/gate3-uncovered-by-kind.log`):

| Kind | In scope | Out of scope for `ws180g005` |
|---|---|---|
| density-ceiling | 1 | |
| density-floor | 5 | 2 |
| exact-size | 2 | |
| gate-length | 3 | |
| max-distance | 25 | 19 |
| max-width | 18 | 1 |
| min-area | 11 | 4 |
| min-enclosure | 89 | 17 |
| min-extension | 22 | 7 |
| min-space | 238 | 37 |
| min-width | 44 | 20 |
| other | 47 | 1 |
| ratio | 15 | |
| thickness | 1 | |
| **total** | **521** | **108** |

The kind is the importer's classification of the source row. Some GF180MCU rows are
classified under the wrong kind (for example the `EF.*` rows, `DM.1` and `PL.2` appear as
min-width); they are still listed, only under another heading.

Sources (from the report's "Sources" table): `gf180mcu-drm` 737 entries, 95 cited;
`gf180mcu-models` 7 entries, 4 cited; `scmos8` 276 entries, 126 cited; `xc018` 30 entries,
26 cited, all transcribed. One source has `transcribed = false`: `onc18` (onsemi ONC18 data
sheet, registered, not yet transcribed, 0 entries; plan decision 13).

## Image, reproducibility and git commit

- Image: `ws180g-pdk-base:local`, config digest
  `sha256:2fe8eb944861d8fa2a63da8f7052905fa8c44c758045adc6e503520b08bc8fdd`, equal to
  `docker/IMAGE_ID`. Each of the three builds below checked it and rebuilt it with
  `docker/build`, and each manifest records `"image_check": "rebuilt, ID reproduced"`
  (`tmp/t23/manifests-image-check.log`). Every build overwrites the rebuild's log
  `tmp/build/ws180g005/image-build.log`; the copy kept from the last build,
  `tmp/t23/image-build-build3.log`, shows `exporting config sha256:2fe8eb94…bc8fdd` and the
  longest step, the export, `#7 DONE 71.4s`.
- Full build, cold: `uv run ws180g-build --out tmp/t23/out` exit 0 in 51:42 wall time
  (`tmp/t23/build1.log`) on the shared build host: one pytest container job ran beside it
  at a time (gate check 1, then gate check 2), `manifest:
  tmp/t23/out/build-manifest.json (287 files)`. The manifest records
  `"git_commit": "d284382d9d7a1a19dbb5c7a1d55e411582bb9fee"`, `"git_dirty": true`
  (the HEAD when the manifest was written: the build started at `df0f77a`, see
  [the trees of the runs](#the-tree-of-each-run)), `"container_runs": true`,
  89 rules and 261 fixtures.
- Warm rerun: `uv run ws180g-build --out tmp/t23/out2` exit 0 in 2:10, every engine
  result from the cache (`tmp/t23/build2.log`); `diff -r tmp/t23/out tmp/t23/out2`
  printed nothing and exited 0 (`tmp/t23/diff-out-out2.log`): the two output trees,
  manifest included, are byte-identical.
- Clean rerun at the report's commit: `uv run ws180g-build --out tmp/t23/out3` exit 0
  (`tmp/t23/build3.log`), manifest `"git_commit": "4e7169764be493f5c8708ca73889b34f35e0cd4d"`,
  `"git_dirty": false` (`tmp/t23/build3-manifest.log`); `diff -r tmp/t23/out2 tmp/t23/out3`
  differs only in those two manifest fields (`tmp/t23/diff-out2-out3.log`).

(the-tree-of-each-run)=
### The tree of each run

The runs were made while this branch grew; the commits after `df0f77a` add a layergen test,
the two `tools/` scripts with their tests, this report and README text, none of which the
gate runs execute. "Uncommitted" means files in the worktree that a later commit added.

| Run | Tree |
|---|---|
| Full build, cold (`build1.log`) | started at `df0f77a`; `7843b5a` and `d284382` were committed during it, so its manifest names `d284382`, dirty |
| Gate check 1 (`gate1.log`) | `d284382` |
| Gate check 3, `ws180g-check-private`, `ws180g-check-names` | `d284382` with an uncommitted README draft |
| CI sandbox job | `d284382` (pushed) |
| Gate check 2 (`gate2.log`) | `d284382`, then `8249e4e` from its last minutes, with uncommitted report drafts |
| Warm build (`build2.log`) | `d284382` with uncommitted README and report drafts and the table test |
| Host suite, ruff (`host-suite.log`, `ruff.log`) | `8249e4e` with the report, its table test and the toctree entry uncommitted (committed as `c1b6693`) |
| Clean build (`build3.log`) | `4e71697`, clean |
| Sphinx (`sphinx.log`) | the tree committed as `171bd3a` |

(ci)=
## CI

The `sandbox` job of `.github/workflows/ci.yml` (manual dispatch) was run once, with
`gh workflow run ci.yml --ref task-23-gate-report` at `d284382`:
[run 42372717804](https://github.com/wafer-space-robot/ws180g-pdk/actions/runs/42372717804),
conclusion **success** (`tmp/t23/ci-watch.log`, job log `tmp/t23/ci-sandbox-job.log`).
On the hosted `ubuntu-latest` runner, `docker/build` pulled the base and built the
image in about 5 minutes, printing
`sha256:2fe8eb944861d8fa2a63da8f7052905fa8c44c758045adc6e503520b08bc8fdd`, the same
ID as on the build host; then `uv run pytest -rs -v -m "sandbox and not slow"` gave

```text
SKIPPED [21] tests/rules/test_engines_agree.py:23: KLayout-only
SKIPPED [21] tests/rules/test_magic_fixtures.py:46: KLayout-only
======== 1232 passed, 42 skipped, 524 deselected in 1219.69s (0:20:19) =========
```

which includes gates 1 and 2 (264 KLayout, 241 Magic and 240 agreement tests, 456
retarget cases, 3 positive controls, the IO run; counted by test id in
`tmp/t23/ci-sandbox-counts.log`). The `host` job of the same run also
passed. So the hosted runner can run the sandbox job, and gate checks 1 and 2 now have
a second, independent run. The marker expression `sandbox and not slow` deselects the only
`slow` test file, `tests/sandbox/test_image_reproducible.py` (rebuild the image and compare the
digest); neither this job nor this report ran it. Its check stands in two other places: every
build's image check (`"image_check": "rebuilt, ID reproduced"` in the three manifests above),
and the hosted runner's own `docker/build` printing the same digest as `docker/IMAGE_ID`.

## Recorded exceptions

The tables below are generated from the code constants by `tools/phase0_report_tables.py`
and pasted here; `tests/build/test_phase0_report_tables.py` fails when they differ from the
script's current output, so they cannot go stale. Why the geometry forces each marker set of
`EXPECTED_MARKERS` is written above the constant in `rules/src/ws180g_rules/fixtures.py`: a
cut straddling the df or po edge also lies on field (`co.in`); poly enclosing a contact under
0.24 µm from df makes that df edge a gate edge (`co.s.gate`); a rotated cut is not a square
box (`co.size`); an off-grid coordinate is shared by the two ends of an edge (two `grid`
markers); and every v4 cluster must be a rectangular array (`mtop.v4.array`), so the v4
fixtures report per pair or per cut.

<!-- BEGIN generated by `uv run tools/phase0_report_tables.py`; do not edit -->
### Forced marker sets (`EXPECTED_MARKERS`, 13 fixtures)

| Fail fixture | Markers the KLayout deck must give |
|---|---|
| `co.po.s.df/min_minus_grid` | `co.po.s.df` × 1, `co.s.gate` × 1 |
| `cut.ortho/cut_ortho` | `co.size` × 1, `cut.ortho` × 1 |
| `df.e.co/straddle` | `co.in` × 1, `df.e.co` × 1 |
| `grid/grid` | `grid` × 2 |
| `m4.e.v4/min_minus_grid` | `m4.e.v4` × 2 |
| `m4.e.v4/straddle` | `m4.e.v4` × 2 |
| `mtop.e.v4/min_minus_grid` | `mtop.e.v4` × 2 |
| `mtop.e.v4/straddle` | `mtop.e.v4` × 2 |
| `mtop.v4.array/staggered` | `mtop.v4.array` × 4 |
| `po.e.co/straddle` | `co.in` × 1, `po.e.co` × 1 |
| `v4.s/min_minus_grid` | `v4.s` × 2 |
| `v4.size/oversize` | `mtop.v4.array` × 4, `v4.size` × 1 |
| `v4.size/rect` | `mtop.v4.array` × 4, `v4.size` × 1 |

### Magic exceptions (`MAGIC_EXCEPTIONS`, 3 fixtures)

| Fail fixture | Rule ids Magic reports | Reason |
|---|---|---|
| `po.x.df/end_inside` | `df.x.po`, `po.x.df` | po ends inside df: Magic finds it (the corner rule of po.x.df), but the gate's end edge borders diffusion like a source/drain edge, so df.x.po also measures the diffusion beyond the poly end against its 0.48 um; an edge rule cannot tell the two apart and cannot withdraw another rule's error |
| `v4.size/oversize` | `v4.size` | a v4 one grid step larger than the others of its 2 x 2 array breaks the array's rectangle, so KLayout also reports mtop.v4.array (Task 18); that rule is KLayout-only (Magic cannot count the cuts of a cluster), so Magic reports v4.size alone |
| `v4.size/rect` | `v4.size` | a v4 one grid step larger than the others of its 2 x 2 array breaks the array's rectangle, so KLayout also reports mtop.v4.array (Task 18); that rule is KLayout-only (Magic cannot count the cuts of a cluster), so Magic reports v4.size alone |

### KLayout-only rules (8 rules)

| Rule | Kind | Why Magic does not check it |
|---|---|---|
| `ps.tap.dmax` | max-distance | Magic has no rule for the distance to the nearest shape of a layer |
| `nw.tap.dmax` | max-distance | Magic has no rule for the distance to the nearest shape of a layer |
| `co.s.butt` | min-space | KLayout-only in the rule table since Task 7; a space to the nd/pd butting edge (an edge, not a layer) is not attempted in Magic in Phase 0 |
| `cut.ortho` | topology | Magic stores only Manhattan and 45-degree geometry |
| `mtop.v4.array` | topology | Magic cannot count the cuts of a cluster |
| `mtop.w.long` | min-width | Magic has no width rule conditional on the length of an edge |
| `angle` | topology | Magic stores only Manhattan and 45-degree geometry |
| `grid` | topology | KLayout-only in the rule table since Task 7; Magic's off_grid rule is not attempted in Phase 0 |

### Pass fixtures excluded from gate check 2 (`EXCLUDED`, 4 fixtures)

| Pass fixture | GF180MCU rule | Reason |
|---|---|---|
| `dnw.w/min` | DN.3 | each DNWELL must be directly surrounded by a PCOMP guard ring tied to the substrate; the dnw fixtures draw a bare deep n-well, and the ring topology is the deep-n-well module's open item |
| `dnw.w/min_plus_grid` | DN.3 | each DNWELL must be directly surrounded by a PCOMP guard ring tied to the substrate; the dnw fixtures draw a bare deep n-well, and the ring topology is the deep-n-well module's open item |
| `dnw.s/min` | DN.3 | each DNWELL must be directly surrounded by a PCOMP guard ring tied to the substrate; the dnw fixtures draw a bare deep n-well, and the ring topology is the deep-n-well module's open item |
| `dnw.s/min_plus_grid` | DN.3 | each DNWELL must be directly surrounded by a PCOMP guard ring tied to the substrate; the dnw fixtures draw a bare deep n-well, and the ring topology is the deep-n-well module's open item |

### Permanent regression fixtures of gate check 2 (4 modules)

| Case | What it records |
|---|---|
| `regressions/butted_ntap_pfet` | Regression (Task 18, 2026-11-07, outcome (b), layergen): a p-FET whose source diffusion is butted by an n-well tap (the pass fixture `nd.s.pgate/min` of Task 14). |
| `regressions/butted_ptap_nfet` | Regression (Task 18, 2026-11-07, outcome (b), layergen): an n-FET whose source diffusion is butted by a substrate tap (the pass fixture `pd.s.ngate/min` of Task 14). |
| `regressions/v4_array_enclosure` | Regression (Task 18, 2026-11-07, outcome (b), fixture): a 2 x 2 v4 array under mtop at the minimum enclosures, m4.e.v4 0.12 and mtop.e.v4 0.30 um on the right and top (the pass fixtures `m4.e.v4/min` and `mtop.e.v4/min` of Task 14, as they are now drawn). |
| `regressions/v4_array_space` | Regression (Task 18, 2026-11-07, outcome (b), fixture): two 2 x 2 v4 arrays at the minimum space 0.48 um, side by side at v4.s + one grid step (0.485 um) (the pass fixture `v4.s/min_plus_grid` of Task 14, as it is now drawn). |

### GF180MCU rule-deck files not run (`excluded_decks`, 5 files)

The deck runs with `-rd decks=all,-density,-dummy,-antenna`.

| Deck file | Tag | Reason | Source |
|---|---|---|---|
| `density.rb` | `density` | metal and poly density need a whole die with fill; Phase 1 | `rule_decks/density.rb tags: %w[all density]` |
| `dummy_comp.rb` | `dummy` | dummy (fill) COMP rules: fill is Phase 1 | `rule_decks/dummy_comp.rb tags: %w[all beol dummy dummy_comp]` |
| `dummy_poly2.rb` | `dummy` | dummy (fill) Poly2 rules: fill is Phase 1 | `rule_decks/dummy_poly2.rb tags: %w[all beol dummy dummy_poly2]` |
| `dummy_metal.rb` | `dummy` | dummy (fill) metal rules: fill is Phase 1 | `rule_decks/dummy_metal.rb tags: %w[all beol dummy] + dummy_metal<n>` |
| `antenna.rb` | `antenna` | antenna ratios need the routed die; Phase 1 | `rule_decks/antenna.rb tags: %w[all feol antenna]` |
<!-- END generated -->

## Deviations from the gate wording, for the owner's agreement

The gate is met only with these deviations; each needs the owner's agreement.

1. **"Both DRC engines pass every fixture"**: eight rules are KLayout-only (the spec allows
   this), and 3 fixtures have a Magic marker set that differs from KLayout's
   (`MAGIC_EXCEPTIONS`); 13 fail fixtures carry a forced marker set other than one marker of
   their own rule (`EXPECTED_MARKERS`). Both lists are in the tables above.
2. **"Passes the public GF180MCU deck"**: the deck runs without its density, fill (dummy) and
   antenna rule decks, the five files in the last table (plan decision 7). They need a whole
   die with fill and routing, which come in Phase 1.
3. **"Every generic pass fixture"**: the four `dnw` module fixtures are excluded under policy
   (c), GF DN.3 (plan decision 8): the deep-n-well guard-ring topology is an open item.

(the-library-repositories)=
## Phase 0 deliverables: the library repositories (Task 22)

The design document's Phase 0 deliverables include "meta-repository and library repositories
created". The first version of this report declared Phase 0 complete without Task 22, which
waited for the repository owner's agreement to create public repositories. The owner gave it
on 2026-11-10 and the task was done that day:

- the two repositories
  [`ws180g005_fd_pr`](https://github.com/wafer-space-robot/ws180g005_fd_pr) and
  [`ws180g005_fd_io`](https://github.com/wafer-space-robot/ws180g005_fd_io) exist, public,
  Apache-2.0, each with a placeholder README and the licence and no library content;
- `tools/repo-settings/apply.py` created them and applied the settings of the
  meta-repository, which are committed as `repo.json`, `protection.json` and
  `ruleset-tags.json` beside it; `tools/repo-settings/verify.py` reads a repository's live
  settings and reports no difference from those files for all three repositories;
- `.gitmodules` (HTTPS URLs) and the submodules `libraries/ws180g005_fd_pr` and
  `libraries/ws180g005_fd_io`;
- [`libraries/README.md`](https://github.com/wafer-space-robot/ws180g-pdk/blob/main/libraries/README.md).

Every run this report quotes was made before the submodules existed. In those runs
`ws180g-check-names` checked no library tree: `naming.check_tree` found no `libraries/` or
`libs.ref/` directory (the run in `tmp/t23/ws180g-check-names.log` exits 0 with no finding).
From this change on it checks the two directory names under `libraries/`, and
`tests/test_submodules.py` checks `.gitmodules`, the two commit links and that both checkers
pass with the submodules present. The build reads nothing under `libraries/` in Phase 0, so
its output tree does not depend on them. The standard-cell library repository is created in
Phase 1, once its track count exists (plan decision 12).

## Open items

For Phase 1 or for the owner's review:

- ONC18: the data sheet needs a person to download it, then transcription (plan decision 13).
- Density, antenna, fill, seal ring and slot rules and decks (plan decision 7).
- Deep-n-well ring topology (GF DN.3), which also excludes the `dnw` fixtures from gate 2.
- The single-source margin 1.5 (plan decision 2) and the chosen 800 µm `mtop.w.long`
  threshold (plan decision 15), for the owner's review.
- The standard-cell library repository (plan decision 12).
- An nd/pd overlap trips no generic rule (`df.s.np` uses `separation`, which does not see
  overlapping shapes).
- A `cite` field for value-less topology rules (`grid`, `angle`, `mtop.v4.array`), so that
  `ws180g-check-private` can verify their citation.
- The v4 cluster-joining gap: the generic `mtop.v4.array` joins cuts into one cluster at up to
  `v4.s`, GF180MCU MT30.8 at about 2 µm, so two arrays between those distances are judged
  differently.
- The 45° select case in the Phase 1 fuzz generator: `ws180g_layergen.derive` now snaps
  every generated layer to the grid, and the layergen tests cover a chamfer away from and at
  the nd/pd butting edge; the fuzz loop should still generate such shapes.

## Other notes

- The host suite on the primary checkout has one skip,
  `tests/test_sandbox_run.py::test_primary_checkout_source_refused_from_this_checkout`
  ("not run from a worktree"); from a linked worktree it has none. This worktree:
  `uv run pytest -m "not sandbox" -rs -v` gave `526 passed, 1275 deselected in
  49.42s` (`tmp/t23/host-suite.log`, exit 0); `uv run ruff check .` gave `All checks
  passed!` (`tmp/t23/ruff.log`); `uv run ws180g-check-private` and
  `uv run ws180g-check-names` exited 0 with no finding
  (`tmp/t23/ws180g-check-private.log`, `tmp/t23/ws180g-check-names.log`);
  `uv run sphinx-build -W docs tmp/t23/docs` gave `build succeeded.`
  (`tmp/t23/sphinx.log`).

## Reproducing this report

On a Linux host with Docker (about 30 GB free for the images), from a clone, at a clean
checkout (the clean build records `git_dirty false` only then). Each command writes the log
or file this report cites under the same name.

```sh
git clone https://github.com/wafer-space-robot/ws180g-pdk.git
cd ws180g-pdk
git checkout 4e71697      # the commit of the clean rerun; or main
uv sync --all-packages
docker/build              # the image; prints sha256:2fe8eb94..., equal to docker/IMAGE_ID
mkdir -p tmp/t23

# Builds: cold, warm, and their output trees compared
uv run ws180g-build --out tmp/t23/out > tmp/t23/build1.log 2>&1        # cold: 51:42 here
uv run ws180g-build --out tmp/t23/out2 > tmp/t23/build2.log 2>&1       # warm: 2:10 here
diff -r tmp/t23/out tmp/t23/out2 > tmp/t23/diff-out-out2.log 2>&1
uv run ws180g-build --out tmp/t23/out3 > tmp/t23/build3.log 2>&1       # clean rerun
diff -r tmp/t23/out2 tmp/t23/out3 > tmp/t23/diff-out2-out3.log 2>&1
cp tmp/build/ws180g005/image-build.log tmp/t23/image-build-build3.log  # the last rebuild's log
jq -c '.runs | map_values({cases: (.fixtures | length), dirty})' \
  tmp/t23/out/reports/gf180mcu-gate.json > tmp/t23/build1-gf-summary.log
jq -c '{git_commit, git_dirty, image_id, image_check}' \
  tmp/t23/out3/build-manifest.json > tmp/t23/build3-manifest.log
for o in out out2 out3; do jq -c '{git_commit, git_dirty, image_check}' \
  tmp/t23/$o/build-manifest.json; done > tmp/t23/manifests-image-check.log

# Gate check 1, and its counts by test id
uv run pytest tests/rules/test_klayout_fixtures.py tests/rules/test_magic_fixtures.py \
  tests/rules/test_engines_agree.py -rs -v -m sandbox > tmp/t23/gate1.log 2>&1
uv run tools/pytest_log_counts.py tmp/t23/gate1.log > tmp/t23/gate1-counts.log
uv run tools/pytest_log_counts.py tmp/t23/gate1.log --key '\[([^/]+)/' \
  | grep 'test_magic_fixtures.py SKIPPED' > tmp/t23/gate1-skips-by-rule.log

# Gate check 2, its counts, and the two summaries the tests write
uv run pytest tests/precheck/test_fixture_retarget.py tests/precheck/test_gf180mcu_deck.py \
  tests/precheck/test_gf180mcu_io_mt30.py -rs -v -m sandbox > tmp/t23/gate2.log 2>&1
uv run tools/pytest_log_counts.py tmp/t23/gate2.log --key='-(9K|11K|30K)\]$' \
  > tmp/t23/gate2-counts.log
uv run tools/pytest_log_counts.py tmp/t23/gate2.log --key='\[regressions/[^]]*-(9K|11K|30K)\]$' \
  | grep -v ' - ' | sed 's/^/regressions: /' >> tmp/t23/gate2-counts.log
cp tmp/gf180mcu-retarget/reports/gate.json tmp/t23/gate2-gate.json
cp tmp/gf180mcu-retarget/reports/gf180mcu_io_mt30.json tmp/t23/gate2-io-mt30.json

# Gate check 3, and the uncovered entries by kind (headings of the written report)
uv run ws180g-evidence-report --markdown tmp/t23/evidence-report.md \
  --json tmp/t23/evidence-report.json > tmp/t23/gate3.log 2>&1
grep -E '^## Uncovered|^### [a-z-]+ \([0-9]+\)$' tmp/t23/evidence-report.md \
  > tmp/t23/gate3-uncovered-by-kind.log

# Checkers, host suite, lint, the exception tables, the documentation
uv run ws180g-check-private > tmp/t23/ws180g-check-private.log 2>&1
uv run ws180g-check-names > tmp/t23/ws180g-check-names.log 2>&1
uv run pytest -m "not sandbox" -rs -v > tmp/t23/host-suite.log 2>&1
uv run ruff check . > tmp/t23/ruff.log 2>&1
uv run tools/phase0_report_tables.py     # the exception tables above
uv run sphinx-build -W docs tmp/t23/docs > tmp/t23/sphinx.log 2>&1

# The CI sandbox job (needs push access to a branch of the repository)
gh workflow run ci.yml --ref <branch>
gh run watch <run id> > tmp/t23/ci-watch.log 2>&1
gh run view <run id> --job <sandbox job id> --log > tmp/t23/ci-sandbox-job.log 2>&1
cut -f3- tmp/t23/ci-sandbox-job.log | sed -E 's/^[0-9T:.-]+Z //' > tmp/t23/ci-sandbox-job-plain.log
uv run tools/pytest_log_counts.py tmp/t23/ci-sandbox-job-plain.log > tmp/t23/ci-sandbox-counts.log
```

Run the `pytest` commands one after another, not at the same time: each clears the basetemp
`tmp/pytest` when it starts. The two `cp` lines must follow the gate-2 run, since a later
run of those tests overwrites `tmp/gf180mcu-retarget/reports/`. In this report the steps
ran in a different order on a growing branch ([the tree of each run](#the-tree-of-each-run));
the order above gives the same evidence on one tree.
