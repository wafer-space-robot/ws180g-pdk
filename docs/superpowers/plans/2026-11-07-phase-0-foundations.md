# Phase 0 "Foundations" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the data, generators, decks, tech files, checkers and build skeleton of Phase 0 of the ws180g PDK, so that the `ws180g005` 5 V rule set exists as ranges with public evidence, both DRC engines pass every per-rule fixture, every pass fixture retargeted to GF180MCU passes the public GF180MCU deck, and the margin report proves the margin on every rule.

**Architecture:** One uv workspace in the meta-repository with one Python package per pipeline component (`process`, `evidence`, `rules`, `layergen`, `tech`, `precheck`, `build`), all tests under `tests/`. The process description (TOML) is the only source of numbers; the evidence set (TOML entries plus the vendored Apache-2.0 GF180MCU tables) is read only by the margin report; everything else is generated from the loaded process model. DRC runs in a pinned container built on the public gf180-tcad base image, which carries KLayout, Magic, netgen and the public GF180MCU deck.

**Tech Stack:** Python 3.12+ with `uv` (workspace), `tomllib` (standard library) for reading TOML, pydantic 2 for the typed models, the `klayout` Python module (`klayout.db`) for fixture and layer generation, KLayout 0.30.12 (`klayout -b -r`) and Magic (8.3.685 as found in the base image on 2026-11-07; Task 10 records the exact versions) for DRC, Docker with the gf180-tcad base image `ghcr.io/mithro/gf180-tcad-base@sha256:aedc07956fa71f33094decf80828a13e75ace36cb2426f720b0817aa9aca99b6` (public, pinned), pytest, ruff, Sphinx with MyST and furo for the docs.

**Spec:** `docs/superpowers/specs/2026-10-26-ws180g-pdk-design.md` (sections 3, 5, 6, 7, 8, 9, 10 row "0 Foundations", 11.3, 13, 14, appendix A).

## Global Constraints

- All lengths in micrometres, all physical quantities in SI units; there is no lambda in the process description (spec 3.1).
- Design grid: `0.005` µm, a process-description parameter, provisional (spec 5.2). Every length value, every derived length and every resized cut lies on it; the margin report checks that the grid is a multiple of every target grid the evidence records. Areas are rounded up to a multiple of `0.005` µm².
- Margin rule (spec 3.6): a minimum (width, space, enclosure, extension, area) is at least `1.2 ×` the largest public minimum, rounded **up** to the grid; a maximum (tap distance) is at most `0.8 ×` the smallest public maximum ("at least 20 % smaller"), rounded **down**; a density floor at least `1.2 ×` the largest public floor. Cut sizes are exempt (spec 3.3) and equal the largest public exact size. **Single source** (this plan's provisional choice, recorded in each field's `note` and reviewed when a second source appears): when every binding entry a value cites comes from one registered source, the margin is `1.5 ×` for a minimum and `÷ 1.5` for a maximum. **Margins are always stored as a ratio ≥ 1** (`1.2`, `1.5`, and `1.25` for a ×0.8 maximum); the achieved margin is `value / bound` for minima and `bound / value` for maxima, and must be ≥ the required ratio. A field may carry a different margin than the computed requirement only with a non-empty `margin_reason` (spec 3.6: "a larger margin when the process description records the reason", and the owner's 20 % on the top-metal range, spec 3.2); the report then checks against the field's own ratio, which must itself be ≥ 1.2 for minima and ≥ 1.25 for maxima (the spec's floor), and lists the reason. Each field also records `margin_achieved`, written by the author (spec 3.6 point 1: "the margin achieved"); the report recomputes it and fails if the two differ, so the rule table and manual can carry it without reading the evidence set. **Binding** entries are every evidence entry with a value that is not marked guideline; entries marked guideline (a `*` after a GF180MCU rule number, a GF180MCU table headed `GUIDELINE NO.`, SCMOS section 10 "overglass") are informative and never bound a value. A value with no binding entry is `chosen` with its reasoning. A **range** field produces two report rows: `.min` with achieved = `smallest cited value / range.min`, `.max` with achieved = `range.max / largest cited value`, each against the same required ratio; a range field records `margin_achieved_min` and `margin_achieved_max` instead of one figure. Range bounds are stored rounded to the field's unit precision (`min` down, `max` up; nanometres to 0.01, micrometres to the grid, volts to 0.001, ohm/sq to 0.1). Every achieved ratio is computed from the stored values and compared after rounding to 0.001 (half-up), so `0.22 / 0.1444` is recorded as `1.524`.
- Process fields are referenced everywhere by their full dotted path (`rules.po.x.df`, `rules.sel.x`, `rules.po.l.n`, `stack.metals.mtop.thickness`), in aliases, `composed_of`, `lmin_*`, `Litho` and the report alike.
- Nominal cut sizes (spec 3.3): `co` 0.22, `v1`–`v3` 0.27, `v4` 0.36 µm. Retarget regenerates every cut at the target's exact size, centred on the drawn cut, and snaps toward −x and −y by half a target grid when the size change is an odd number of target-grid steps.
- Nothing private (spec 13): every evidence entry cites a public document in the source registry; the private-data checker rejects any other source. GF180MCU values come only from the open PDK's `tables_clear` CSV tables (Apache-2.0) and its published model cards. Material that may not be redistributed (SCMOS pages, X-FAB and onsemi data sheets) is transcribed as facts with citations, never vendored, not even as test data.
- Naming (spec 6): process `ws180g005`; libraries `ws180g005_fd_pr`, `ws180g005_fd_io` (the standard-cell library waits for its track count in Phase 1); drawn-layer names of spec 5.1; GDS numbers assigned here and fixed forever.
- Variants (spec 4): `ws180g005` ⊂ `ws180g035`, `ws180g105` ⊂ `ws180g135`; Phase 0 generates content for `ws180g005` and declares the chain.
- Every source file starts with `# SPDX-License-Identifier: Apache-2.0`. Dates ISO 8601. Python run with `uv run`; no `python -c`; no `/tmp` (use `tmp/`). Every generated GDS is written with `gds2_write_timestamps = False`; a build on the same inputs is byte-identical.
- Heavy jobs (KLayout, Magic) run only through `build/sandbox-run` with a memory cap, never bare on the host; all fixtures of one engine run in **one** container invocation.
- Git: one worktree and branch per task, small commits, PR with independent review, merge commit.

## Review Focus

1. A rule table cell with several values ("0.6/0.5", "0.23 (n = 1) / 0.28 (2 <= n <= 5)", "NA", "0.35 μm2", "1mA/um") must produce one evidence entry per value with the right unit and kind, or none for non-numeric text; a wrong parse silently weakens the envelope. Test in Task 4 (golden test over whole tables).
2. SCMOS rules bound a value through two lambda mappings (SUBM 0.10 µm, DEEP 0.09 µm); the envelope must take the larger of the two, not the DEEP column alone (metal-1 width: SUBM 0.30 > DEEP 0.27). Test in Task 8.
3. A fail fixture must violate exactly its own rule and nothing else; a narrow-width fail fixture that also trips a minimum-area rule proves nothing, and a fixture without a tap within range trips the tap rule. Tests in Tasks 14 (context and implied-rule policy), 15 and 17 (the assertion `violations == {rule_id: 1}` in KLayout, rule-id set equality in Magic).
4. A cut whose target size differs from the nominal by an odd number of target-grid steps (`v1` 0.27 → 0.26 is two steps, fine; 0.27 → 0.225 would be nine) must be snapped so that both edges stay on the target grid. Test in Task 18.
5. Non-Manhattan or non-square cuts and off-grid vertices must be rejected by the generic deck (KLayout-only rules), otherwise a layout clean in Magic reaches a target deck that forbids them. Test in Task 15.

---

## File structure

```
ws180g/
  pyproject.toml                 uv workspace root; dev deps (pytest, ruff, pydantic, klayout)
  uv.lock
  .github/workflows/ci.yml       ruff, pytest -m "not sandbox", checkers; manual-dispatch sandbox job
  process/pyproject.toml         package ws180g_process
  process/src/ws180g_process/{__init__,model,load,ranges}.py
  process/data/ws180g/{process,layers,masks,stack,rules}.toml
  evidence/pyproject.toml        package ws180g_evidence
  evidence/src/ws180g_evidence/{__init__,model,load,report,import_gf180mcu,import_scmos}.py
  evidence/sources/gf180mcu-drm/{LICENSE,README.md,fetch.py,*.csv}   vendored Apache-2.0 tables
  evidence/sources/{scmos8,xc018,onc18,gf180mcu-models}/README.md     not vendored: URL, sha256, date
  evidence/data/{sources,gf180mcu-drm,scmos8,xc018,gf180mcu-models}.toml   entries
  rules/pyproject.toml           package ws180g_rules
  rules/src/ws180g_rules/{__init__,table,klayout_deck,fixtures,run_klayout,run_magic,manual}.py
  layergen/pyproject.toml        package ws180g_layergen
  layergen/src/ws180g_layergen/{__init__,derive}.py
  tech/pyproject.toml            package ws180g_tech
  tech/src/ws180g_tech/{__init__,klayout,magic}.py
  precheck/pyproject.toml        package ws180g_precheck
  precheck/src/ws180g_precheck/{__init__,mapping,retarget,gf180mcu}.py
  precheck/data/gf180mcu.toml    the public GF180MCU mapping
  build/pyproject.toml           package ws180g_build (console script ws180g-build)
  build/src/ws180g_build/{__init__,main,naming,private_check,tree}.py
  build/private-allow.txt
  build/sandbox-run              bash: run a command in the capped container
  docker/{Dockerfile,build,IMAGE,IMAGE_ID,versions.json,requirements.lock}
  tools/git-hooks/pre-commit, tools/install-hooks
  tools/repo-settings/{apply.py,repo.json,protection.json,ruleset-tags.json}
  docs/{conf.py,index.md,rules.md,evidence.md,phase-0-report.md,phase-0-retarget-log.md,generated/}
  tests/{process,evidence,rules,layergen,tech,precheck,build,sandbox}/test_*.py
  tests/evidence/data/            synthetic inputs only (never copies of non-redistributable pages)
  out/                           build output, gitignored
  libraries/ws180g005_fd_pr, libraries/ws180g005_fd_io   submodules (Task 22)
```

Responsibilities: `process` loads and validates; `evidence` imports, loads and reports; `rules` turns the process model into the rule table, the KLayout deck, the fixtures and the engine runners; `layergen` derives generated layers from a layout; `tech` writes tech files; `precheck` retargets to GF180MCU and runs its deck; `build` orchestrates and checks.

## Shared vocabulary (used by every task)

**Rule kinds** (`kind` in `rules.toml`, in the rule table, in the deck generators and in the fixture generator): `min-width`, `gate-length` (the width of a gate region measured between its two edges that lie on `po` edges), `min-space` (between shapes of one layer, or `layers = [a, b]` for two layers), `min-enclosure` (`layers = [outer, inner]`: outer encloses inner; `edges = "sides"` restricts the checked inner edges to those that are edges of a named layer), `min-extension` (`layers = [a, b]`: a extends beyond its intersection with b, e.g. gate end cap), `min-area`, `exact-size` (square cuts), `max-distance` (tap distance, KLayout-only), `topology` (a named check with a hand-written fixture), `generation` (a parameter read by `layergen`, no check).

**Layer expressions** (`LayerExpr`, Task 9): a layer name; `a|b` union; `a&b` intersection; `a-b` difference; `a.sized(<field path>)` sizing by the value of a process field; `a.unrelated(b)` the shapes of `a` not interacting with `b`. The short names `df` = `nd|pd` and `field_po` = `po-(df.sized(rules.po.x.df))` are defined once in `rules.toml` under `[aliases]`.

**Evidence entry id**: `<source>/<rule>[/<column>][/<part>]`: a column suffix exactly when the table has more than one value column (`gf180mcu-drm/NW.1a/5v`, `gf180mcu-drm/CO.1`), a part suffix for multi-value cells (`gf180mcu-drm/PL.2/5v/n`, `gf180mcu-drm/Mn.1/m1`, `gf180mcu-drm/MT30.1/a`); SCMOS `scmos8/7.1/deep`, `scmos8/7.1/subm`; `xc018/metal1/width`; `gf180mcu-models/nfet_06v0/toxe`.

**Layers** (`layers.toml`; GDS layer/datatype; datatype 0 drawing, 10 label text, 2 pin shapes):

| name | GDS | kind | name | GDS | kind |
|---|---|---|---|---|---|
| `nw` | 1/0 | drawn, baseline | `pad` | 20/0 | drawn, baseline |
| `nd` | 2/0 | drawn, baseline | `sab` | 21/0 | drawn, baseline |
| `pd` | 3/0 | drawn, baseline | `ox_3v3` | 30/0 | drawn, ws180g035/135 |
| `po` | 4/0 | drawn, baseline | `ox_1v8` | 31/0 | drawn, ws180g105/135 |
| `co` | 5/0 | drawn, baseline | `dnw` | 32/0 | drawn, module deep-n-well |
| `m1` | 11/0 | drawn, baseline | `rhi` | 33/0 | drawn, module high-res poly |
| `v1` | 12/0 | drawn, baseline | `mk_res` | 40/0 | drawn marker |
| `m2` | 13/0 | drawn, baseline | `mk_cap` | 41/0 | drawn marker |
| `v2` | 14/0 | drawn, baseline | `mk_dio` | 42/0 | drawn marker |
| `m3` | 15/0 | drawn, baseline | `mk_bjt` | 43/0 | drawn marker |
| `v3` | 16/0 | drawn, baseline | `mk_esd` | 44/0 | drawn marker |
| `m4` | 17/0 | drawn, baseline | `mk_nofill` | 50/0 | drawn marker |
| `v4` | 18/0 | drawn, baseline | `mk_boundary` | 51/0 | drawn marker |
| `mtop` | 19/0 | drawn, baseline | `nsel` | 60/0 | generated |
| | | | `psel` | 61/0 | generated |
| | | | `gate` | 62/0 | generated |
| | | | `ntap` | 63/0 | generated |
| | | | `ptap` | 64/0 | generated |

Generated layers in Phase 0 (`layergen`, Task 11; `x` = `rules.sel.x`, `s` = `rules.nsel.s` = `rules.psel.s`; `close(r) = r.sized(s/2).sized(-s/2)` fills every gap narrower than `s` between shapes of one select): `gate = po & df`; `P = pd | (po & sab)` (unsilicided poly is p+ by default in Phase 0); `psel = close(P.sized(x)) - nd`; `nsel = close(nd.sized(x)) - psel`; `ntap = nd & nw`; `ptap = pd - nw`. The two selects never overlap and meet at an nd/pd butting edge; two nd shapes legally spaced between `df.s` and `s + 2x` get one merged `nsel`. `derive` **replaces** the generated layers of a layout; it never merges into shapes already there. Whether unimplanted field poly (poly interconnect outside any select) is accepted by the GF180MCU deck is checked by the retarget check (Task 18). Fill, seal ring, slots and per-target oxide masks beyond the 5 V whole-design mask are Phase 1.

**Phase 0 rule set for `ws180g005`** (values in µm; "GF" = GF180MCU DRM table, 5 V column where one exists; "XC" = X-FAB XC018 data sheet rev 3.0 p.5; "S8" = SCMOS rev 8 rule, DEEP at λ = 0.09 / SUBM at λ = 0.10 from Tables 2c/2b; ws180g `v4`/`mtop` are compared with the SCMOS top via and top metal of the six-metal process, sections 29 and 30, and with via4 section 25 where the rule is like for like; the generic value is `max × 1.2` rounded up to 0.005 unless marked `×1.5` single-source, `×0.8`/`÷1.5` maximum, `exact`, or `chosen`):

| id | kind | layers | value | public values and derivation |
|---|---|---|---|---|
| `nw.w` | min-width | nw | 1.44 | GF NW.1a 0.86; XC 0.86; S8 1.1 12λ 1.08/1.20 |
| `nw.s` | min-space | nw | 2.16 | GF NW.2b 1.7 (NW.2a 0.74 equipotential); XC 1.4; S8 1.2 18λ 1.62/1.80 |
| `nw.e.pd` | min-enclosure | nw, pd | 0.72 | GF DF.4c 0.60; S8 2.3 6λ 0.54/0.60 |
| `nw.e.nd` | min-enclosure | nw, nd | 0.36 | GF DF.4d 0.16; S8 2.4 3λ 0.27/0.30 |
| `nw.s.nd` | min-space | nw, nd | 0.72 | GF DF.16 0.60; S8 2.3 0.54/0.60 |
| `nw.s.pd` | min-space | nw, pd | 0.36 | GF DF.17 0.16; S8 2.4 0.27/0.30 |
| `df.w` | min-width | df | 0.36 | GF DF.1a 0.30, DF.2a 0.30; XC 0.22; S8 2.1 3λ 0.27/0.30 |
| `df.s` | min-space | df | 0.435 | GF DF.3a 0.36; XC 0.28; S8 2.2 3λ 0.27/0.30 |
| `df.s.np` | min-space | nd, pd (butting allowed) | 0.48 | GF DF.3a 0.36, DF.3b 0 butted; S8 2.5 4λ 0.36/0.40 |
| `df.x.po` | min-extension | df, gate | 0.48 | GF DF.6 0.40; S8 3.4 4λ 0.36 / 3λ 0.30 |
| `df.e.co` | min-enclosure | df, co | 0.18 | GF CO.4 0.07; S8 6.2 1.5λ 0.135/0.15 |
| `df.area` | min-area | df | 0.305 µm² | GF DF.9 0.2025 ×1.5 |
| `nd.s.pgate` | min-space (`composed_of`) | nd, (gate & nw) and its end-cap poly `po & (gate & nw).sized(rules.po.x.df)` | 0.665 | `1.2 × max(GF NP.4a 0.32, NP.4b 0.22, S8 4.1 3λ 0.27/0.30) = 0.385` + `rules.sel.x` 0.28 |
| `pd.s.ngate` | min-space (`composed_of`) | pd, (gate − nw) and its end-cap poly | 0.665 | as `nd.s.pgate` with PP.4a, PP.4b |
| `po.w` | min-width | po | 0.24 | GF PL.1 0.20; XC 0.18; S8 3.1 2λ 0.18/0.20 |
| `po.l.n` | gate-length | gate − nw | 0.72 | GF PL.2 0.60 (first value of "0.6/0.5" is the nfet; the n/p order is justified in the field's `note` only, from the public card: `nfet_06v0` `lmin` 0.7 µm = the first value of the 6 V cell, `pfet_06v0` `lmin` 0.5 µm = the second value of the 5 V cell; the card's 6 V `lmin` is not cited as evidence, 6 V being out of scope); S8 24.5 3λ 0.27/0.30 |
| `po.l.p` | gate-length | gate & nw | 0.60 | GF PL.2 0.50 (p); S8 24.5 |
| `po.s` | min-space | po | 0.435 | GF PL.3a 0.24 (PL.3b 0.4 guideline, informative); XC 0.25; S8 3.2.a 4λ 0.36 (3.2 3λ 0.27/0.30) |
| `po.x.df` | min-extension | po, gate (end cap) | 0.27 | GF PL.4 0.22; S8 3.3 2.5λ 0.225 / 2λ 0.20 |
| `po.s.df` | min-space | field_po, df | 0.36 | GF PL.5a 0.30, PL.5b 0.30; S8 3.5 1λ 0.09/0.10 |
| `po.e.co` | min-enclosure | po, co | 0.18 | GF CO.3 0.07; S8 5.2 1.5λ 0.135/0.15 |
| `co.size` | exact-size | co | 0.22 exact | GF CO.1 0.22; XC 0.22; S8 5.1 2λ 0.18/0.20 |
| `co.s` | min-space | co | 0.435 | GF CO.2a 0.25, CO.2b 0.28; XC 0.25; S8 5.3 4λ 0.36 / 3λ 0.30 |
| `co.s.gate` | min-space | co, gate | 0.24 | GF CO.7 0.15; S8 5.4 2λ 0.18/0.20 |
| `co.po.s.df` | min-space | co & po, df | 0.24 | GF CO.8 0.17; S8 5.6.b 2λ 0.18/0.20 (from the alternative contact rule set, noted in the field) |
| `co.s.butt` | min-space (KLayout-only) | co, the nd/pd butting edge | 0.165 | GF CO.5a/CO.5b 0.1; S8 4.3 select overlap of contact 1.5λ 0.135 / 1λ 0.10 (the selects meet at the butting edge) |
| `co.in` | topology | co inside po ∪ df | — | GF CO.11; S8 sections 5, 6 |
| `co.no.gate` | topology | co ∩ gate = ∅ | — | GF CO.10 |
| `co.no.butt` | topology | co never straddles an nd/pd butting edge | — | GF CO.9 |
| `m1.w` | min-width | m1 | 0.36 | GF Mn.1 0.23; XC 0.23; S8 7.1 3λ 0.27/0.30 |
| `m1.s` | min-space | m1 | 0.36 | GF Mn.2a 0.23, Mn.2b 0.30; XC 0.23; S8 7.2 3λ 0.27/0.30 |
| `m1.e.co` | min-enclosure | m1, co | 0.12 | GF CO.6 0.06; S8 7.3 1λ 0.09/0.10 |
| `m1.e.v1` | min-enclosure | m1, v1 | 0.12 | GF Vn.3 0.06; S8 8.3 1λ |
| `m1.area` | min-area | m1 | 0.22 µm² | GF Mn.3 0.1444 ×1.5 = 0.2166 → 0.22 |
| `v1.size` | exact-size | v1 | 0.27 exact | GF Vn.1 0.26; XC 0.26; S8 8.1 3λ 0.27 / 2λ 0.20 |
| `v1.s` | min-space | v1 | 0.435 | GF Vn.2a 0.26, Vn.2b 0.36; XC 0.26; S8 8.2 3λ 0.27/0.30 |
| `m2.w` | min-width | m2 | 0.36 | GF Mn.1 0.28; XC 0.28; S8 9.1 3λ 0.27/0.30 |
| `m2.s` | min-space | m2 | 0.435 | GF Mn.2a 0.28, Mn.2b 0.30; XC 0.28; S8 9.2 4λ 0.36 / 3λ 0.30 |
| `m2.e.v1` | min-enclosure | m2, v1 | 0.12 | GF Vn.4 0.06; S8 9.3 1λ |
| `m2.e.v2` | min-enclosure | m2, v2 | 0.12 | GF Vn.3 0.06; S8 14.3 1λ |
| `m2.area` | min-area | m2 | 0.22 µm² | GF Mn.3 ×1.5 |
| `v2.size`, `v2.s` | as v1 | v2 | 0.27 exact, 0.435 | GF Vn.1, Vn.2a/b; XC; S8 14.1 3λ, 14.2 3λ |
| `m3.w`, `m3.s`, `m3.e.v2`, `m3.e.v3`, `m3.area` | as m2 | m3 | 0.36, 0.435, 0.12, 0.12, 0.22 | GF Mn.*, Vn.3/4; XC; S8 15.1 3λ, 15.2 4λ, 15.3 1λ, 21.3 1λ |
| `v3.size`, `v3.s` | as v1 | v3 | 0.27 exact, 0.435 | S8 21.1 3λ, 21.2 3λ |
| `m4.w`, `m4.s`, `m4.e.v3`, `m4.area` | as m2 | m4 | 0.36, 0.435, 0.12, 0.22 | S8 22.1 3λ, 22.2 4λ, 22.3 1λ |
| `m4.e.v4` | min-enclosure | m4, v4 | 0.12 | GF Vn.3 0.06; S8 25.3 1λ 0.09/0.10 (29.3 for the six-metal top via, same value) |
| `v4.size` | exact-size | v4 | 0.36 exact | GF Vn.1 0.26; XC Top Via 0.36; S8 29.1 4λ 0.36 / 3λ 0.30 |
| `v4.s` | min-space | v4 | 0.48 | GF Vn.2b 0.36; XC 0.35; S8 29.2 4λ 0.36/0.40 |
| `mtop.w` | min-width | mtop | 2.16 | GF MT30.1a 1.8; XC Top Metal 0.44; S8 30.1 5λ 0.45/0.50 |
| `mtop.w.long` | min-width (KLayout-only; `condition = "length > 800"`) | mtop | 3.3 | GF MT30.1b 2.2 at > 1000 µm ×1.5 (single source); the 800 µm threshold is chosen: 1000 µm × 0.8, so the stricter width applies sooner than at the target |
| `mtop.s` | min-space | mtop | 2.16 | GF MT30.2 1.8; XC 0.46; S8 30.2 5λ |
| `mtop.e.v4` | min-enclosure | mtop, v4 | 0.30 | GF MT30.6 0.25 (MT30.5 0.12); S8 30.3 2λ 0.18 / 1λ 0.10 |
| `mtop.area` | min-area (`implied_by = "rules.mtop.w"`: 2.16² > 0.845, no fail fixture) | mtop | 0.845 µm² | GF MT.4 0.5625 ×1.5 |
| `mtop.v4.array` | topology (KLayout-only) | every v4 cluster under mtop is at least 2 × 2 | — | GF MT30.8b |
| `pad.w` | min-width (`chosen`) | pad | 60 | no binding source: GF PAD.1 40 and PAD.2 sit in a `GUIDELINE NO.` table, TM.1a 40 is the bump flow, S8 10.1 60 is a guideline; chosen 60 = 1.5 × the GF guideline and equal to the SCMOS guideline |
| `pad.s` | min-space (`chosen`) | pad | 13.5 | GF PAD.2 9 (guideline) × 1.5 |
| `mtop.e.pad` | min-enclosure | mtop, pad | 3.0 | GF PAD.4 2 ×1.5 (S8 10.3 6 guideline, informative) |
| `sab.w` | min-width | sab | 0.505 | GF SB.1 0.42; S8 20.1 4λ 0.36/0.40 |
| `sab.s` | min-space | sab | 0.505 | GF SB.2 0.42; S8 20.2 4λ |
| `sab.s.co` | min-space | sab, co | 0.24 | GF SB.4 0.15; S8 20.3 2λ 0.18/0.20 |
| `sab.e.po` | min-enclosure (`edges = "sides"`: inner edges that are `po` edges; the crossing ends are `po.x.sab`) | sab, po & sab | 0.265 | GF SB.9 0.22, SB.12 0.22; S8 20.9 2λ |
| `sab.e.df` | min-enclosure (`edges = "sides"`, df edges) | sab, df & sab | 0.265 | GF SB.6 0.22; S8 20.9 2λ |
| `po.x.sab` | min-extension | po, sab | 0.36 | GF SB.10 0.22; S8 20.10 3λ 0.27/0.30 |
| `df.x.sab` | min-extension | df, sab | 0.36 | GF SB.7 0.22; S8 20.10 3λ |
| `sab.s.df` | min-space | sab, df.unrelated(sab) | 0.265 | GF SB.3 0.22; S8 20.4 2λ |
| `sab.s.po` | min-space | sab, po.unrelated(sab) | 0.36 | GF SB.5a 0.30, SB.5b 0.28; S8 20.5 2λ |
| `sab.area` | min-area | sab | 3.0 µm² | GF SB.13 2.0 ×1.5 |
| `sab.no.gate` | topology | sab ∩ gate = ∅ | — | GF SB.16 |
| `nsel.w`, `nsel.s`, `psel.w`, `psel.s` | min-width / min-space on generated layers, `engines = []` (width by construction: `df.w` 0.36 + 2 × `sel.x` ≥ 0.48; space by the `close` step of `layergen`; both proven by Task 11 unit tests, no fixtures) | nsel, psel | 0.48 | GF NP.1/NP.2/PP.1/PP.2 0.40; S8 4.4 4λ 0.36 / 2λ 0.20 |
| `nw.tap.dmax` | max-distance (KLayout-only; stored `margin = 1.5`) | pd & nw to nearest ntap | 10 | GF DF.13 15 ÷ 1.5 (single source) |
| `ps.tap.dmax` | max-distance (KLayout-only; `margin = 1.5`) | nd − nw to nearest ptap | 10 | GF DF.14 15 ÷ 1.5 |
| `dnw.w` | min-width (module) | dnw | 3.675 | GF DN.1 1.7; S8 31.1 34λ 3.06 / 30λ 3.00 |
| `dnw.s` | min-space (module) | dnw | 6.505 | GF DN.2b 5.42; S8 31.2 56λ 5.04 / 50λ 5.00 |
| `grid` | topology (KLayout-only) | all vertices on 0.005 | — | GF GRID, OFFGRID |
| `angle` | topology (KLayout-only) | edges orthogonal or 45° | — | GF ACUTE |
| `cut.ortho` | topology (KLayout-only) | co, v1–v4 orthogonal squares | — | GF CO.1/Vn.1; S8 contact and via pages |

Layer-generation parameter (kind `generation`): `sel.x` = 0.28 (select extension beyond active, beyond the gate in the poly direction, and beyond SAB poly; GF NP.5a/PP.5a 0.23 overlap of gate, NP.5b/PP.5b 0.16, NP.9/PP.9 0.18; S8 4.2 2λ 0.18/0.20; 0.23 × 1.2 = 0.276 → 0.28).

Public rules the Phase 0 set does not cover (the margin report lists every binding entry no rule cites, grouped by kind; this is the expected content, not an exhaustive list): density (PL.8, Mn.4, MT.3, MT30.7, DCF.*, DPF.*, DM.*; S8 guidelines xx.1–xx.3), antenna (ANT.*), latch-up tables (LU.*), wide-metal spacing (Mn.2b beyond what `m1.s` covers, MT.2b; S8 7.4, 9.4, 15.4, 22.4, 26.4, 30.4), DF.2b, DF.10, DF.11, PL.7, NP.3a–e/PP.3a–e, NP.8/PP.8, NP.12/PP.12 (covered in effect by `nd.s.pgate`/`pd.s.ngate` but not cited), SB.14, SB.15, dummy and marking layers, the `rhi` module, and the deep-n-well ring topology (GF NW.5 "DNWELL enclose Nwell" and S8 31.3/31.4 "N_Well beyond / over the Deep_N_Well edge" require opposite n-well placements: recorded as the module's open item; module fixtures are excluded from gate check 2, Task 18).

---

### Task 1: Workspace skeleton and CI

**Files:**
- Create: `pyproject.toml`, `.github/workflows/ci.yml`, `process/pyproject.toml`, `evidence/pyproject.toml`, `rules/pyproject.toml`, `layergen/pyproject.toml`, `tech/pyproject.toml`, `precheck/pyproject.toml`, `build/pyproject.toml`, each `src/<pkg>/__init__.py`, `tests/conftest.py`, `tests/test_workspace.py`, `docs/index.md` (a stub pointing at the spec and this plan; Task 21 extends it)
- Modify: `.gitignore` (add `out/`, `.venv/`; `uv.lock` stays tracked)
- Modify: `README.md` (how to run `uv sync` and `uv run pytest`)

**Interfaces:**
- Produces: package names `ws180g_process`, `ws180g_evidence`, `ws180g_rules`, `ws180g_layergen`, `ws180g_tech`, `ws180g_precheck`, `ws180g_build`; pytest marker `sandbox` (needs Docker); `tests/conftest.py` fixtures `repo_root: Path`, `tmp` (an alias of `tmp_path`), `data_copy` (a copy of `process/data/ws180g` in `tmp`), `process` (Task 2, `load_process()`), `evidence` (Task 4, `load_evidence()`), `gf_entries` (the `gf180mcu-drm` entries), `report` (Task 8, `margin_report(process, evidence)`), `sandbox` (Task 10); and the helper module `tests/helpers.py` with `set_toml(path, keys: list[str], value)` (rewrites one `key = value` line of a TOML file by regex, since `tomllib` has no writer) and `evidence_dir_with(entries: list[dict], sources: dict) -> Path` (writes a throwaway evidence set in `tmp`). Later tasks add fixtures here as their interfaces say.

- [ ] **Step 1: Write the failing test** `tests/test_workspace.py`:

```python
import importlib
import pytest

PACKAGES = ["ws180g_process", "ws180g_evidence", "ws180g_rules", "ws180g_layergen",
            "ws180g_tech", "ws180g_precheck", "ws180g_build"]

@pytest.mark.parametrize("name", PACKAGES)
def test_package_imports(name):
    assert importlib.import_module(name).__name__ == name
```

- [ ] **Step 2: Run** `uv run pytest tests/test_workspace.py -v`. Expected: FAIL (no packages).
- [ ] **Step 3: Create the workspace.** Root `pyproject.toml`: `[project] name = "ws180g"`, `requires-python = ">=3.12"`, `[tool.uv.workspace] members = ["process", "evidence", "rules", "layergen", "tech", "precheck", "build"]`, `[tool.uv.sources]` mapping each member to `{ workspace = true }`, `[dependency-groups] dev = ["pytest>=9", "ruff", "pydantic>=2.11", "klayout>=0.30.12"]`, `docs = ["sphinx", "myst-parser", "furo"]`, `[tool.pytest.ini_options] testpaths = ["tests"]`, `addopts = "--strict-markers"`, `markers = ["sandbox: runs a tool in the container through build/sandbox-run (needs Docker)", "slow: minutes, not seconds"]`, `[tool.ruff] line-length = 100`. Each member: hatchling build, `packages = ["src/<pkg>"]`, Apache-2.0, `dependencies = ["pydantic>=2.11"]` (plus `"klayout>=0.30.12"` for rules, layergen, precheck).
- [ ] **Step 4: CI** `.github/workflows/ci.yml`: job `host` on ubuntu-latest: `astral-sh/setup-uv`, `uv sync --all-packages`, `uv run ruff check .`, `uv run pytest -rs -v -m "not sandbox"`; job `sandbox` on `workflow_dispatch` only: pull the base image, build `docker/`, run `uv run pytest -rs -v -m sandbox` (the base image is about 15 GB; if the hosted runner cannot hold it, the job's failure is recorded in the Task 23 report and the sandbox tests stay host-run).
- [ ] **Step 5: Run** `uv sync --all-packages && uv run pytest -v && uv run ruff check .`. Expected: 7 passed.
- [ ] **Step 6: Commit** `feat: uv workspace with one package per pipeline component`.

### Task 2: Process schema and loader with layers and variants

**Files:**
- Create: `process/src/ws180g_process/model.py`, `load.py`, `ranges.py`; `process/data/ws180g/process.toml`, `layers.toml`, and empty-table `masks.toml`, `stack.toml`, `rules.toml` (filled in Tasks 3 and 7)
- Test: `tests/process/test_load.py`, `tests/process/test_layers.py`

**Interfaces:**
- Produces: `load_process(data_dir: Path = DEFAULT_DATA) -> Process` where `Process` (pydantic, `extra="forbid"`) has `name: str` ("ws180g"), `grid: Field` (value 0.005 µm), `variants: dict[str, Variant]` (`Variant.oxides: list[str]`, `Variant.contains: list[str]`), `layers: dict[str, Layer]` (`Layer.gds: tuple[int, int]`, `Layer.kind: Literal["drawn", "generated"]`, `Layer.variant: str | None`, `Layer.module: str | None`, `Layer.purpose: str`), `rules: dict[str, RuleField]` (Task 7), `aliases: dict[str, str]` (Task 7), `stack: Stack` (Tasks 3 and 7), `masks: list[Mask]` (Task 3). `Range(min: Decimal, nominal: Decimal, max: Decimal, unit: str)`; `Field(value: Decimal | None, range: Range | None, unit: str, provenance: Literal["design-target", "public-source", "chosen", "derived"], evidence: list[str], margin: Decimal | None, margin_reason: str, margin_achieved: Decimal | None, composed_of: list[str], source: str | None, note: str)` (`margin` is a ratio ≥ 1; a `margin` that differs from the report's computed requirement needs a non-empty `margin_reason` and is still ≥ 1.2 / 1.25; `margin_achieved` is the author's figure, checked by the report). `on_grid(value: Decimal, grid: Decimal) -> bool`. Loader errors are `ProcessError` with the file and key. Decimal everywhere (TOML floats are converted with `Decimal(str(x))`), so 0.435 is exact.

- [ ] **Step 1: Write the failing tests**:

```python
def test_grid_and_variants(process):
    assert process.grid.value == Decimal("0.005")
    assert process.variants["ws180g135"].contains == ["ws180g005", "ws180g035", "ws180g105"]
    assert process.variants["ws180g005"].oxides == ["5v0"]

EXPECTED_GDS = {"nw": (1, 0), "nd": (2, 0), "pd": (3, 0), "po": (4, 0), "co": (5, 0),
                "m1": (11, 0), "v1": (12, 0), "m2": (13, 0), "v2": (14, 0), "m3": (15, 0), "v3": (16, 0),
                "m4": (17, 0), "v4": (18, 0), "mtop": (19, 0), "pad": (20, 0), "sab": (21, 0),
                "ox_3v3": (30, 0), "ox_1v8": (31, 0), "dnw": (32, 0), "rhi": (33, 0),
                "mk_res": (40, 0), "mk_cap": (41, 0), "mk_dio": (42, 0), "mk_bjt": (43, 0), "mk_esd": (44, 0),
                "mk_nofill": (50, 0), "mk_boundary": (51, 0),
                "nsel": (60, 0), "psel": (61, 0), "gate": (62, 0), "ntap": (63, 0), "ptap": (64, 0)}

def test_layer_numbers_are_frozen(process):          # golden test: the ws180g005 numbers never change
    assert {n: l.gds for n, l in process.layers.items()} == EXPECTED_GDS
    assert process.layers["ox_1v8"].variant == "ws180g105"
    assert process.layers["nsel"].kind == "generated"

def test_rejects_unknown_provenance(data_copy):      # fixture: copy of process/data/ws180g in tmp_path
    set_toml(data_copy / "process.toml", ["grid", "provenance"], "private")
    with pytest.raises(ProcessError, match="provenance"):
        load_process(data_copy)

def test_rejects_grid_not_multiple_of_dbu(data_copy):
    set_toml(data_copy / "process.toml", ["grid", "value"], 0.0033)   # the grid must be a multiple of the 0.001 µm database unit
    with pytest.raises(ProcessError, match="grid"):
        load_process(data_copy)
```

- [ ] **Step 2: Run** `uv run pytest tests/process -v`. Expected: FAIL (ImportError).
- [ ] **Step 3: Implement** `model.py`, `ranges.py` (`Range`, `on_grid`), `load.py` (`tomllib`, one file per table, collects errors with file:key). `process.toml` holds `name`, `schema = 1`, `[grid] value = 0.005 unit = "um" provenance = "chosen" evidence = ["gf180mcu-drm/GRID"] note = "provisional, spec 5.2; the least common multiple of the target grids the evidence records"`, `[variants.*]`. `layers.toml` holds the table of the shared vocabulary, one `[layers.<name>]` each, with `purpose` text from spec 5.1.
- [ ] **Step 4: Run** `uv run pytest tests/process -v`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(process): schema, loader, grid, variants and the fixed layer numbers`.

### Task 3: Mask list, supplies, lithography and implant schema

**Files:**
- Create: `process/data/ws180g/masks.toml`; fill the schema part of `stack.toml`; extend `model.py` (`Mask(name, drawn: bool, baseline: bool, module: str | None, justification: str)`, `Stack(oxides: dict[str, Oxide], metals: dict[str, MetalLayer], dielectrics: dict[str, Dielectric], implants: dict[str, Implant], litho: dict[str, Litho], supplies: dict[str, Supply])`, `Oxide(thickness: Range, vt_n: Range, vt_p: Range, lmin_n: str, lmin_p: str)` where `lmin_*` name the rule fields (`"rules.po.l.n"`, `"rules.po.l.p"`) so the gate length lives once, `MetalLayer(thickness: Range | None, sheet_rho: Range | None)`, `Dielectric(thickness: Range | None)`, `Implant(doping: Range | None, note)`, `Litho(min_feature: str, min_space: str, registration: Field)` naming the rule fields it corresponds to (`"rules.m1.w"`), `Supply(nominal: Decimal, tolerance: Decimal, unit)`)
- Test: `tests/process/test_masks.py`, `tests/process/test_stack_schema.py`

**Interfaces:**
- Consumes: Task 2 models.
- Produces: `process.masks`; `process.stack.supplies["5v0"]` = nominal 5.0 V, tolerance 0.10 (the corners `ss_125C_4v50` / `ff_n40C_5v50` of spec 6.2, provenance `chosen`); `process.stack.litho[<layer>]` for every baseline drawn layer naming its width and space rules and a `registration` field `chosen` with `note = "no public overlay data; placeholder until a public source or silicon"`; `process.stack.implants` for `nplus`, `pplus`, `vt_5v0` with `doping = None` and the same placeholder note; `process.stack.dielectrics` for `ild1`–`ild4`, `imd_top`, `passivation` with `thickness = None` placeholders. The evidence-bearing ranges (oxide thickness, Vt, sheet resistance, the `mtop` range) are filled in Task 7, after the evidence sources exist.

- [ ] **Step 1: Write the failing tests**:

```python
def test_baseline_masks_have_justification(process):
    baseline = [m for m in process.masks if m.baseline]
    assert {m.name for m in baseline} >= {"nw", "nd", "pd", "po", "co", "m1", "v1", "m2", "v2", "m3", "v3", "m4", "v4", "mtop", "pad", "sab", "nsel", "psel"}
    assert all(m.justification for m in process.masks)
    assert next(m for m in process.masks if m.name == "dnw").module == "deep-n-well"

def test_supply_and_placeholders(process):
    s = process.stack.supplies["5v0"]
    assert (s.nominal, s.tolerance) == (Decimal("5.0"), Decimal("0.10"))
    assert process.stack.litho["m1"].min_feature == "rules.m1.w" and process.stack.litho["m1"].registration.provenance == "chosen"
    assert process.stack.implants["nplus"].doping is None
```

- [ ] **Step 2: Run**; expected FAIL.
- [ ] **Step 3: Write the data.** `masks.toml`: one entry per drawn baseline layer, the generated selects, the module layers (`dnw`, `rhi`) and the oxide markers, each with `justification` (one sentence from spec 5.3). `stack.toml`: the `supplies`, `litho`, `implants`, `dielectrics` tables above; `oxides` and `metals` tables are added in Task 7.
- [ ] **Step 4: Run**; expected PASS.
- [ ] **Step 5: Commit** `feat(process): mask list, supplies, lithography and implant schema`.

### Task 4: Evidence model, source registry and the GF180MCU table importer

**Files:**
- Create: `evidence/src/ws180g_evidence/model.py`, `load.py`, `import_gf180mcu.py`; `evidence/sources/gf180mcu-drm/README.md`, `LICENSE` (Apache-2.0 copied from the gf180mcu-pdk repository), `fetch.py`, the 85 `*.csv` files from `docs/physical_verification/design_manual/tables_clear` at the commit recorded in the README; `evidence/data/sources.toml`, `evidence/data/gf180mcu-drm.toml` (generated)
- Test: `tests/evidence/test_model.py`, `tests/evidence/test_import_gf180mcu.py`, `tests/evidence/golden/16_Poly2_42.toml` (the expected import of one whole table, written by hand)

**Interfaces:**
- Produces: `Entry(id, source, rule, column: str | None, part: str | None, kind: Kind, layers: list[str], value: Decimal | None, unit: str | None, text: str, cite: str, guideline: bool, lambda_: Decimal | None, lambda_um: Decimal | None)` (`lambda_` is the lambda count of an SCMOS rule, TOML key `lambda`, may be 1.5 or 2.5), `Source(id, title, url, licence, retrieved: date | None, transcribed: bool, vendored: bool, sha256: dict[str, str], public: bool = True)`; `load_evidence(data_dir) -> Evidence` with `.entries: dict[str, Entry]`, `.sources: dict[str, Source]`; `EvidenceError` for an entry whose `source` is not registered. `import_gf180mcu(src_dir, out_path) -> int` (entries written; calls `import_gf180mcu_table(csv_path, out_path) -> int` per table), console script `ws180g-import-gf180mcu`.
- Kinds: the rule kinds of the vocabulary plus `max-width`, `density-floor`, `density-ceiling`, `ratio`, `grid`, `thickness`, `other`. Kind is decided by an **ordered** match on the description, first match wins: "Min/max" with "size" → `exact-size`; "Min/max" with "space" → `min-space`; "ratio" → `ratio`; "coverage"/"density" with "Max"/"max" → `density-ceiling`; "coverage"/"density" → `density-floor`; "Max"/"max" with "distance"/"space" → `max-distance`; "Max"/"max" with "width" → `max-width`; "area" → `min-area`; "overlap"/"enclose"/"enclosure" → `min-enclosure`; "extension"/"extend"/"overhang" → `min-extension`; "space"/"spacing" → `min-space`; "width" → `min-width`; otherwise `other`. A coverage row whose value cell is empty takes its percentage from the description (`>= 14%` → 14, `>30%` → 30, unit `%`). A trailing `*` in a value cell (`0.36/0.44*`) is stripped and sets `guideline` on that part. A continuation row (empty rule cell) whose description starts with `a\)`, `b\)` or `c\)` belongs to the preceding rule and gets that letter as its part (`55_Latch-up_152.csv`: `LU.1/lv/a` 50, `LU.1/mv/a` 15; column names `LV` → `lv`, `MV` → `mv`; a `Comment` column is not a value column). The `GRID` row of `10_Design_Geometry_Rules27.csv` becomes `gf180mcu-drm/GRID` with kind `grid`, value 0.005. The metal-option table `05_Current_0.18_MCU_9.csv` (no rule numbers) yields `gf180mcu-drm/TM9K`, `TM11K`, `TM30K` with kind `thickness`, values 0.9, 1.1, 3.0 µm (n kÅ = n/10 µm), from the `TM<n>K` tokens.

- [ ] **Step 1: Write the failing tests**:

```python
def test_entry_ids_and_columns(gf_entries):
    assert gf_entries["gf180mcu-drm/NW.1a/5v"].value == Decimal("0.86")
    assert gf_entries["gf180mcu-drm/NW.1a/3v3"].value == Decimal("0.86")
    assert gf_entries["gf180mcu-drm/CO.1"].kind == "exact-size" and gf_entries["gf180mcu-drm/CO.1"].value == Decimal("0.22")
    assert gf_entries["gf180mcu-drm/PL.2/5v/n"].value == Decimal("0.6")
    assert gf_entries["gf180mcu-drm/PL.2/5v/p"].value == Decimal("0.5")
    assert gf_entries["gf180mcu-drm/Mn.1/m1"].value == Decimal("0.23")
    assert gf_entries["gf180mcu-drm/Mn.1/mn"].value == Decimal("0.28")
    assert gf_entries["gf180mcu-drm/DF.13/5v"].kind == "max-distance" and gf_entries["gf180mcu-drm/DF.13/5v"].value == Decimal("15")
    assert gf_entries["gf180mcu-drm/DF.9/5v"].unit == "um2"
    assert gf_entries["gf180mcu-drm/MT30.1/a"].value == Decimal("1.8") and gf_entries["gf180mcu-drm/MT30.1/b"].value == Decimal("2.2")
    assert gf_entries["gf180mcu-drm/PL.3b/5v"].guideline is True        # trailing * in the rule number
    assert gf_entries["gf180mcu-drm/PAD.1/wedge"].guideline is True     # table headed GUIDELINE NO.
    assert gf_entries["gf180mcu-drm/PAD.4/ball"].guideline is False
    assert "gf180mcu-drm/PL.6" not in gf_entries                        # text-only rule
    assert gf_entries["gf180mcu-drm/PL.10/5v"].unit == "mA/um"
    assert gf_entries["gf180mcu-drm/GRID"].kind == "grid" and gf_entries["gf180mcu-drm/GRID"].value == Decimal("0.005")
    assert gf_entries["gf180mcu-drm/PL.8/5v"].kind == "density-floor" and gf_entries["gf180mcu-drm/PL.8/5v"].value == Decimal("14")
    assert gf_entries["gf180mcu-drm/DF.2b/5v"].kind == "max-width"
    assert gf_entries["gf180mcu-drm/NP.3d"].kind == "min-space"
    assert gf_entries["gf180mcu-drm/MT.1/b"].guideline is True and gf_entries["gf180mcu-drm/MT.1/b"].value == Decimal("0.44")
    assert gf_entries["gf180mcu-drm/TM30K"].kind == "thickness" and gf_entries["gf180mcu-drm/TM30K"].value == Decimal("3.0")
    assert gf_entries["gf180mcu-drm/LU.1/mv/a"].kind == "max-distance" and gf_entries["gf180mcu-drm/LU.1/mv/a"].value == Decimal("15")

def test_golden_poly_table(repo_root, tmp):
    import_gf180mcu_table(repo_root / "evidence/sources/gf180mcu-drm/16_Poly2_42.csv", tmp / "poly.toml")
    assert tomllib.loads((tmp / "poly.toml").read_text()) == tomllib.loads((repo_root / "tests/evidence/golden/16_Poly2_42.toml").read_text())

def test_importer_is_reproducible(tmp, repo_root):
    import_gf180mcu(repo_root / "evidence/sources/gf180mcu-drm", tmp / "gf.toml")
    assert (tmp / "gf.toml").read_bytes() == (repo_root / "evidence/data/gf180mcu-drm.toml").read_bytes()

def test_unregistered_source_rejected(tmp):
    bad = evidence_dir_with([{"id": "foo/X.1", "source": "foo", "kind": "min-width", "value": 1}], sources={})
    with pytest.raises(EvidenceError, match="source"):
        load_evidence(bad)

def test_vendored_sha256_matches(evidence, repo_root):
    for name, digest in evidence.sources["gf180mcu-drm"].sha256.items():
        assert hashlib.sha256((repo_root / "evidence/sources/gf180mcu-drm" / name).read_bytes()).hexdigest() == digest
```

- [ ] **Step 2: Run**; expected FAIL.
- [ ] **Step 3: Vendor the tables.** `evidence/sources/gf180mcu-drm/fetch.py` fetches the 85 files from the gf180mcu-pdk repository at a recorded commit SHA and writes the URL, commit and each file's sha256 into `sources.toml`; `README.md` names the source URL, commit, licence and retrieval date.
- [ ] **Step 4: Implement the importer.** `csv` module; the header row's first cell is `RULE NO.` (binding) or `GUIDELINE NO.` (every row guideline); a row whose first cell is `Layer` carries the column names (`3.3V` → `3v3`, `5V`/`5V/6V` → `5v`, `6V` → `6v`, `LV`/`MV` kept, the bond-pad columns → `wedge`, `ball`, `bump`); a rule number ending in `*` or `**` sets `guideline = True` (stripped from the id); cell values: numbers → one entry; `a/b` → parts `n` and `p` for PL.2 (gate length; order from the `gf180mcu-models` card, see the rule table) and `a`, `b` otherwise; a cell with parenthesised conditions on separate lines (`0.23 (n = 1)` / `0.28 (2 <= n <= 5)`) → `m1` and `mn`; `(a)`/`(b)` lines in the description (MT30.1) → `a`, `b`; `NA`, `--`, empty → no entry; units from a trailing token (`um2`/`μm2`, `mA/um`, `%`) else `um`. Every entry's `cite` is `"<file>, row <rule>, column <col>"`.
- [ ] **Step 5: Run**; expected PASS. Commit `feat(evidence): source registry and the GF180MCU design-manual importer` (vendored tables in a separate commit `data(evidence): vendor the GF180MCU design-manual tables (Apache-2.0)`).

### Task 5: SCMOS rev 8 importer and entries

**Files:**
- Create: `evidence/src/ws180g_evidence/import_scmos.py`, `evidence/data/scmos8.toml` (generated), `evidence/sources/scmos8/README.md` (page URLs, retrieval date, sha256 of each fetched page; the pages are not vendored)
- Test: `tests/evidence/test_import_scmos.py` with **synthetic** HTML in `tests/evidence/data/scmos_synthetic/*.html` (same table structure, invented rule numbers and values)

**Interfaces:**
- Produces: `import_scmos(pages: dict[str, str], out_path) -> int` where `pages` maps page name to its HTML text; console script `ws180g-import-scmos` that fetches `https://bears.ece.ucsb.edu/class/ece224a/scmos/scmos-<page>.html` for `well`, `active`, `poly`, `select`, `contact` (sections 5 and 6), `metal1`, `metal2` (sections 8 and 9), `metal3` (14, 15), `metal4` (21, 22), `metal5` (25, 26), `metal6` (29, 30), `glass`, `sblock`, `thickactive`, `dnw`, and `main` (Tables 2b and 2c) into `tmp/scmos8/` (gitignored), records each sha256, and imports. The importer asserts that every section the rule table cites (1–10, 14, 15, 20, 21, 22, 24, 25, 26, 29, 30, 31) was found. Entries per rule and column: id `scmos8/<rule>/<scmos|subm|deep>`, `value` in µm = lambda count × `lambda_um`, `lambda_um` 0.10 for `subm` and 0.09 for `deep` (SCN6M, Tables 2b and 2c), `lambda_` the count (Decimal), `unit = "um"`; the `scmos` column (no 0.18 µm mapping) is kept with `lambda_um = None` and `value = None`. On pages with several column groups, the group for the most metals (`3+`, `4+`, `5+`, `6`) is used. `n/a` → no entry. Section 10 (glass) entries are in microns with `guideline = True`.

- [ ] **Step 1: Write the failing tests** on the synthetic pages (for example a "poly" page with rules `3.1` = 2/2/2 and `3.2.a` = 2/3/4, a "metal2" page with two column groups): `3.1/deep` value 0.18 and `lambda_ == 2`; `3.2.a/deep` 0.36; the highest group is used; `n/a` dropped; a glass row is guideline in microns; a `1.5` lambda count parses as `Decimal("1.5")`; a page missing a cited section raises.
- [ ] **Step 2: Run**; FAIL. **Step 3: Implement** with `html.parser` (standard library): strip tags, read rows of `rule, description, c1, c2, c3[, c4, c5, c6]`; the ordered kind map of Task 4; a `*` after a number is ignored. **Step 4: Run**; PASS. Generate `evidence/data/scmos8.toml` from the live pages and commit it with the README; a test checks the committed file has `scmos8/3.1/deep` = 0.18, `8.1/deep` exact-size 0.27, `29.1/deep` 0.36, `30.1/subm` 0.50, `10.1` guideline 60. **Step 5: Commit** `feat(evidence): SCMOS rev 8 importer and entries`.

### Task 6: X-FAB XC018, onsemi ONC18 and GF180MCU model-card entries

**Files:**
- Create: `evidence/data/xc018.toml` (hand-transcribed), `evidence/data/gf180mcu-models.toml` (hand-transcribed), `evidence/sources/xc018/README.md`, `evidence/sources/onc18/README.md`, `evidence/sources/gf180mcu-models/README.md`; the `onc18` and `gf180mcu-models` entries in `sources.toml`
- Test: `tests/evidence/test_hand_entries.py`

**Interfaces:**
- XC018 (`retrieved` date and the PDF's sha256 in `sources.toml`): entries `xc018/<mask>/<width|spacing>` for the ten rows of "Basic Design Rules" (p.5): `nwell` 0.86/1.4, `active` 0.22/0.28, `poly` 0.18/0.25, `polyres` 0.44/0.44, `contact` 0.22/0.25, `metal1` 0.23/0.23, `via` 0.26/0.26, `metal2345` 0.28/0.28, `topvia` 0.36/0.35, `topmetal` 0.44/0.46 (contact, via and top via widths are `exact-size`); `xc018/<device>/vt` for `ne5` 0.77, `pe5` 0.84 (p.5); `xc018/<device>/rs` for `rm1`, `rm2`, `rm3`, `rm4`, `rm5`, `rmtp`, `rmtpl`, `rpp1k1` (p.7, unit `ohm/sq`). The p.7 "Thickness or junction depth" column is **not** transcribed: its metal values are physically inconsistent with the sheet resistances and would contradict the owner's `mtop` range; the README records this.
- `gf180mcu-models` (the open PDK's `libs.tech/ngspice/sm141064.ngspice`, Apache-2.0, present in the container at `/foss/pdks/gf180mcuD/libs.tech/ngspice/`; `sources.toml` records the open_pdks commit and the file's sha256): entries `gf180mcu-models/nfet_06v0/toxe` 15.2 nm, `/toxp` 16.0 nm, `/vth0`, `/lmin` 0.7 µm, `gf180mcu-models/pfet_06v0/vth0`, `/lmin` 0.5 µm, each with `cite = "sm141064.ngspice line N (.model nfet_06v0.0, typical section)"` as read inside the container.
- ONC18: the data sheet `ONC181818/D` could not be downloaded by the automation (the server returns an HTML page to non-browser clients). `sources.toml` registers it with `retrieved = None`, `transcribed = false`; the margin report lists it as "registered, not yet transcribed". When a person downloads the PDF into `tmp/ref/onsemi/`, its "Process Characteristics" values are transcribed into `evidence/data/onc18.toml` with page citations and `transcribed = true`.

- [ ] **Step 1: Tests**: `xc018/topvia/width` is exact-size 0.36; `xc018/metal1/spacing` 0.23; `xc018/rpp1k1/rs` 1000 `ohm/sq`; every xc018 entry's `cite` contains "page"; `gf180mcu-models/nfet_06v0/lmin` 0.7 µm and `/pfet_06v0/lmin` 0.5 µm; `evidence.sources["onc18"].transcribed is False` and no entry has source `onc18`.
- [ ] **Step 2–4**: FAIL, write the TOML by hand (XC018 from the PDF pages 5 and 7 read with the Read tool; the card values from `grep -n` on the file inside the container), PASS.
- [ ] **Step 5: Commit** `data(evidence): X-FAB XC018 and GF180MCU model-card entries; onsemi ONC18 registered, pending retrieval`.

### Task 7: The rule fields and the 5 V stack ranges

**Files:**
- Create: `process/data/ws180g/rules.toml`; fill `oxides` and `metals` in `stack.toml`; extend `model.py` with `RuleField(kind, layers: list[str], value: Decimal | None, unit, variant, provenance, evidence: list[str], margin: Decimal | None, composed_of: list[str], implied_by: str | None, edges: str | None, engines: list[Literal["klayout", "magic"]], condition: str | None, fixture: str | None, note: str)`
- Test: `tests/process/test_rules.py`, `tests/process/test_stack.py`

**Interfaces:**
- Produces: `process.rules["nw.w"]` etc., exactly the Phase 0 rule set table; `process.aliases` = `{"df": "nd|pd", "field_po": "po-(df.sized(rules.po.x.df))"}`; `engines` defaults to both; `fixture` set for every `topology` rule; `composed_of = ["gf180mcu-drm/NP.4a", "gf180mcu-drm/NP.4b", "scmos8/4.1/deep", "scmos8/4.1/subm", "rules.sel.x"]` for `nd.s.pgate` (the report checks the margined part and adds the field named last).
- Stack: `oxides.5v0.thickness` = `Range(15.2/1.2, 15.6, 16.0×1.2, "nm")` with evidence `gf180mcu-models/nfet_06v0/toxe|toxp`, `margin = 1.2`, `margin_reason = "two card parameters (TOXE, TOXP) bound the range from both sides; single-source 1.5 would put the minimum below any published 5 V oxide"`; `vt_n` = `[min(vth0_n, 0.77)/1.2, …, max × 1.2]` citing the card and `xc018/ne5/vt`; `vt_p` likewise with `pe5`; `lmin_n = "rules.po.l.n"`, `lmin_p = "rules.po.l.p"`; `metals.mtop.thickness = Range(0.75, 1.1, 3.6, "um")` with evidence `gf180mcu-drm/TM9K`, `TM11K`, `TM30K`, `margin = 1.2`, `margin_reason` quoting the owner's decision of spec 3.2 (the 6 kÅ option is ignored, spec 3.2); `metals.m1..m4.sheet_rho` from `xc018/rm1..rm4/rs` as single-source ranges `[rs/1.5, rs, rs×1.5]`; `metals.mtop.sheet_rho` from `rmtp` (thin) and `rmtpl` (thick) as `[rmtpl/1.5, rmtp, rmtp×1.5]`; every `metals.*.thickness` other than `mtop` is `None` with the placeholder note.

- [ ] **Step 1: Tests**: `process.rules["df.s"].value == Decimal("0.435")`; `process.rules["co.size"].kind == "exact-size" and .margin is None`; `process.rules["nw.tap.dmax"].engines == ["klayout"] and .margin == Decimal("1.5")`; `process.rules["nsel.w"].engines == []`; `process.rules["mtop.area"].implied_by == "rules.mtop.w"`; `process.rules["pad.w"].provenance == "chosen"`; every `margin` is ≥ 1.2 (≥ 1.25 for `max-distance`); every rule with evidence has a `margin_achieved`; every rule whose unit is `um` has a value on the grid, every `um2` value is a multiple of 0.005; every rule has `evidence` or `provenance == "chosen"`; every topology rule has a `fixture`; `set(process.rules) ⊇` the ids of the table; no rule's `layers` names an unknown layer or alias; `process.stack.metals["mtop"].thickness == Range(0.75, 1.1, 3.6, "um")` and its `margin_reason` is non-empty; `process.stack.oxides["5v0"].lmin_n == "rules.po.l.n"`.
- [ ] **Step 2–4**: FAIL, write `rules.toml` (one `[rules.<id>]` table per row, `note` quoting the public values as in the plan table, `margin = 1.2`, `1.5` or `1.25`, `condition = "length > 800"` for `mtop.w.long`, `fixture = "co_on_field"` etc.) and the stack tables, PASS.
- [ ] **Step 5: Commit** `feat(process): the Phase 0 ws180g005 rule fields and 5 V stack ranges with evidence`.

### Task 8: Evidence margin report

**Files:**
- Create: `evidence/src/ws180g_evidence/report.py`; console script `ws180g-evidence-report`
- Test: `tests/evidence/test_report.py`

**Interfaces:**
- Consumes: `load_process()`, `load_evidence()`.
- Produces: `margin_report(process, evidence) -> Report` with `Report.rows: list[Row]` (`field: str` (`rules.nw.w`, `stack.oxides.5v0.thickness.min`), `value`, `kind`, `cited: list[Entry]`, `bound: Decimal | None` (largest binding minimum or smallest binding maximum, over all cited entries, both SCMOS mappings included), `single_source: bool` (every binding cited entry has the same `source`), `margin_required: Decimal` (computed as a ratio: 1.2, or 1.5 when single source, for minima; 1.25, or 1.5 when single source, for maxima; none for exact-size; replaced by the field's own `margin` when the field has a `margin_reason`, which the row then carries), `margin_achieved: Decimal | None` (`value / bound` for minima, `bound / value` for maxima, after subtracting the `composed_of` field for composed rules; range rows as in the Global Constraints), `status: Literal["ok", "under-margin", "chosen", "missing-entry", "exempt", "implied", "override-too-small", "achieved-mismatch"]` (the last two: a `margin_reason` override below 1.2 / 1.25, and a recorded `margin_achieved` that differs from the computed one)), `Report.uncovered: list[Entry]` (every binding entry with a value, of any kind, that no field cites; grouped by kind in the output; entries from the `3v3` and `6v` columns are listed under "out of scope for ws180g005"), `Report.sources: list[Source]` (with `transcribed`), `Report.grid_ok: bool` (the process grid is a multiple of every `grid` entry); `Report.to_markdown()`, `Report.to_json()`; `report.ok` is `False` if any row is `under-margin`, `missing-entry`, `override-too-small` or `achieved-mismatch`, or `grid_ok` is false. For `exact-size` the status is `exempt` and `value == bound` is checked; guideline entries never bound a value but are listed beside the row as "informative". Range fields produce two rows (`.min` against the smallest binding minimum ÷ margin, `.max` against the largest × margin). Fields of kind `generation` are checked like minima.

- [ ] **Step 1: Tests**:

```python
def test_metal1_width_takes_subm_mapping(report):
    row = report["rules.m1.w"]
    assert row.bound == Decimal("0.30") and row.margin_achieved == Decimal("1.2") and row.status == "ok"
def test_margin_required_is_computed(report):
    assert report["rules.df.area"].single_source and report["rules.df.area"].margin_required == Decimal("1.5")
    assert report["rules.nw.w"].margin_required == Decimal("1.2")
    assert report["rules.nw.tap.dmax"].margin_required == Decimal("1.5") and report["rules.nw.tap.dmax"].margin_achieved == Decimal("1.5")
def test_composed_rule(report):
    assert report["rules.nd.s.pgate"].status == "ok"      # 0.665 - 0.28 = 0.385 >= 1.2 x 0.32
def test_under_margin_detected(process_with_m1_w_0_35, evidence):
    assert margin_report(process_with_m1_w_0_35, evidence)["rules.m1.w"].status == "under-margin"
def test_missing_entry_detected(process_citing_nonexistent_id, evidence):
    assert margin_report(...).ok is False
def test_uncovered_lists_density_and_antenna(report):
    ids = {e.id for e in report.uncovered}
    assert {"gf180mcu-drm/PL.8/5v", "gf180mcu-drm/ANT.1", "gf180mcu-drm/LU.1/mv/a"} <= ids
    assert "gf180mcu-drm/CO.5a" not in ids          # cited by co.s.butt
def test_maximum_uses_ratio(process_with_tap_dmax_15, evidence):
    assert margin_report(process_with_tap_dmax_15, evidence)["rules.nw.tap.dmax"].status == "under-margin"   # ratio 1.0 < 1.5
def test_stack_rows(report):
    row = report["stack.metals.mtop.thickness.min"]
    assert row.status == "ok" and row.margin_required == Decimal("1.2") and "3.2" in row.margin_reason
    assert row.margin_achieved == Decimal("1.2")                       # 0.9 / 0.75
    assert report["stack.metals.mtop.thickness.max"].margin_achieved == Decimal("1.2")   # 3.6 / 3.0
    assert report["stack.oxides.5v0.thickness.min"].status == "ok"
def test_override_floor(process_with_m1_w_margin_1_0_and_reason, evidence):
    r = margin_report(process_with_m1_w_margin_1_0_and_reason, evidence)
    assert r["rules.m1.w"].status == "override-too-small" and r.ok is False
def test_achieved_mismatch(process_with_m1_w_achieved_2_0, evidence):
    r = margin_report(process_with_m1_w_achieved_2_0, evidence)
    assert r["rules.m1.w"].status == "achieved-mismatch" and r.ok is False
def test_achieved_rounding(report):
    assert report["rules.m1.area"].margin_achieved == Decimal("1.524")   # 0.22 / 0.1444, rounded to 0.001
def test_full_report_ok(report):
    assert report.ok and report.grid_ok, [r for r in report.rows if r.status in ("under-margin", "missing-entry")]
```

(`process_with_m1_w_0_35`, `process_citing_nonexistent_id`, `process_with_tap_dmax_15`, `process_with_m1_w_margin_1_0_and_reason` and `process_with_m1_w_achieved_2_0` are built in the test module from `data_copy` with `set_toml`.)

- [ ] **Step 2–4**: FAIL, implement, PASS (`test_full_report_ok` must pass against the real data; if it fails, the value or the evidence id in the TOML is wrong: fix the data, not the test).
- [ ] **Step 5: Commit** `feat(evidence): margin report`.

### Task 9: Rule table

**Files:**
- Create: `rules/src/ws180g_rules/table.py`; console script `ws180g-rule-table`
- Test: `tests/rules/test_table.py`

**Interfaces:**
- Produces: `RuleTable.from_process(process, variant="ws180g005") -> RuleTable` with `rows: list[RuleRow]` (`id, kind, layers: list[LayerExpr], value, unit, field: str` (e.g. `rules.nw.w`), `variant, evidence: list[str], margin` (the ratio applied, from the field), `margin_reason, margin_achieved` (the author's recorded figure from the field, verified by the report; the table itself never reads the evidence set), `composed_of, engines, condition, edges, implied_by, fixture, text`), `LayerExpr` parsed from the vocabulary's expression strings (`name`, `union`, `intersection`, `difference`, `sized(expr, field)`, `unrelated(expr, expr)`), aliases expanded; `RuleTable.write_json(path)`, `write_csv(path)`, `read_json(path)`. Rows are in a stable order (by layer, then id). Rows of kind `generation` are kept with `engines = []`; the deck and fixture generators skip rows with no engines and rows with `implied_by` get no fail fixture.

- [ ] **Step 1: Tests**: row count equals the number of `ws180g005` rules; `table["df.w"].layers[0] == Union("nd", "pd")`; `table["po.s.df"].layers[0] == Difference("po", Sized(Union("nd", "pd"), "rules.po.x.df"))`; `table["sab.s.df"].layers[1] == Unrelated(Union("nd","pd"), "sab")`; `write_json` then `read_json` round-trips; unknown layer name raises.
- [ ] **Step 2–4**: FAIL, implement, PASS. **Step 5: Commit** `feat(rules): machine-readable rule table`.

### Task 10: Reproducible container image and sandbox runner

**Files:**
- Create: `docker/Dockerfile`, `docker/build`, `docker/IMAGE`, `docker/IMAGE_ID`, `docker/versions.json`, `docker/requirements.lock`, `build/sandbox-run`
- Test: `tests/sandbox/test_image.py` (marker `sandbox`), `tests/sandbox/test_image_reproducible.py` (markers `sandbox`, `slow`)

**Interfaces:**
- Produces: image `ghcr.io/wafer-space-robot/ws180g-pdk-base` (built locally as `:local` until a registry push is set up), `FROM ghcr.io/mithro/gf180-tcad-base@sha256:aedc07956fa71f33094decf80828a13e75ace36cb2426f720b0817aa9aca99b6`; adds `PATH=/opt/ws180g/bin:/foss/tools/klayout:/foss/tools/magic/bin:/foss/tools/netgen/bin:...` and a locked venv `/opt/ws180g` holding the workspace's runtime dependencies (pydantic, klayout) from `docker/requirements.lock` (uv-exported, hashes); project code is mounted, never baked. `build/sandbox-run [--mem 4g] [--cpus 2] [--pids 2048] --workdir DIR [--network none] -- CMD...` is a port of gf180-tcad `tools/sandbox-run` (refuses the repo root, `$HOME` and the git dirs as workdir; mounts the repo read-only at `/work/src` and the workdir read-write at `/work/out`; exit code is the command's).
- `docker/build` is a copy of gf180-tcad's `docker/base/build` with the image name changed (pinned BuildKit, `SOURCE_DATE_EPOCH` from the last commit touching the inputs, `rewrite-timestamp`, no attestations); it prints the config digest, which is committed to `IMAGE_ID`. `versions.json` records the base digest and the tool versions **as printed by the tools in the image** (`klayout -v`, `magic --version`, `netgen -batch quit`, `/foss/pdks/versions.txt`).

- [ ] **Step 1: Tests** (`sandbox`): `sandbox-run -- klayout -v` prints the version in `versions.json`; `-- magic --version` and `-- netgen -batch quit` likewise; `-- test -r /foss/pdks/gf180mcuD/libs.tech/klayout/tech/drc/gf180mcu.drc`; a command allocating 8 GiB under `--mem 1g` exits 137; `--workdir <repo root>` is refused with exit 2; (`slow`) `docker/build` run a second time prints the digest in `IMAGE_ID`.
- [ ] **Step 2–4**: build (`docker/build --tag ws180g-pdk-base:local`), run tests, PASS.
- [ ] **Step 5: Commit** `feat(docker): pinned image on the gf180-tcad base with Magic and netgen on PATH; sandbox runner`.

### Task 11: Layer generation

**Files:**
- Create: `layergen/src/ws180g_layergen/derive.py`
- Test: `tests/layergen/test_derive.py`

**Interfaces:**
- Consumes: `Process` (layer numbers, `rules["sel.x"]`, `rules["df.w"]`).
- Produces: `derive(layout: klayout.db.Layout, process: Process, variant: str = "ws180g005") -> None` (clears and rewrites the generated layers of every top cell, flat) and `derive_file(gds_in: Path, gds_out: Path, process)` (writes with `gds2_write_timestamps = False`). Definitions exactly as in the shared vocabulary. All operations in `klayout.db.Region` with the layout dbu 0.001 µm.

- [ ] **Step 1: Tests** (build small layouts in-test with `klayout.db`): an nfet (nd 2 × 1 with po crossing) yields `gate` of the crossing area and `nsel` = nd grown by 0.28 on each side; an nd box inside nw yields `ntap`; a pd box outside nw yields `ptap`; nd and pd butted (gap 0) yield `nsel`/`psel` that do not overlap and share the butting edge; nd and pd at gap 0.28 and at gap 0.48 yield non-overlapping selects; two nd boxes 0.60 µm apart yield one merged `nsel` (the `nsel.s` rule by the `close` step), two nd boxes 1.20 µm apart yield two with a gap ≥ 0.48; `po & sab` yields `psel` around it; a layout with no `sab` has no `psel` from poly; a narrow nd (width `df.w`) butted to pd on both long sides gets `nsel` that ends at the nd's short ends (the band beyond them belongs to `psel`, a known limitation of the formula recorded in the test and left to the Task 18 retarget check to judge against GF NP.5b); a layout that already has shapes on `nsel` gets them replaced; for an nd bar of width `df.w` the `nsel` width is ≥ 0.48 (the `nsel.w` rule by construction); output dbu is 0.001; two runs give byte-identical files.
- [ ] **Step 2–4**: FAIL, implement, PASS. **Step 5: Commit** `feat(layergen): selects, gate and tap derivation`.

### Task 12: KLayout technology files

**Files:**
- Create: `tech/src/ws180g_tech/klayout.py`
- Test: `tests/tech/test_klayout_tech.py`

**Interfaces:**
- Produces: `write_klayout_tech(process, variant, out_dir) -> list[Path]` writing `ws180g005.lyp` (one entry per drawn and generated layer with name, `source` `L/D@1`, a distinct fill colour per layer, generated layers dimmed), `ws180g005.lyt` (`<name>ws180g005</name>`, `<dbu>0.001</dbu>`, `<default-grids>0.005!</default-grids>`, `<layer-properties_file>ws180g005.lyp</layer-properties_file>`, `<add-other-layers>true</add-other-layers>`, a `layer-map` listing every layer `name : L/D`), `ws180g005.map` (LEF/DEF map in the gf180mcu style: `<layer> NET,SPNET,PIN,VIA L 0`, `NAME <layer>/LABEL L 10`, `<layer> PIN L 2` for `m1`–`mtop`, `v1`–`v4`, and `DIEAREA ALL 0 0`).

- [ ] **Step 1: Tests**: files exist and parse as XML; the `.lyp` has exactly `len(process.layers)` entries with the right `source`; the `.lyt` names the `.lyp`; the `.map` has `m1 NET,SPNET,PIN,VIA 11 0`; (`sandbox`) `klayout -b -r <script that loads the .lyt and prints the layer count>` prints the expected count.
- [ ] **Step 2–4**, **Step 5: Commit** `feat(tech): KLayout layer properties, technology and LEF map`.

### Task 13: KLayout DRC deck generator

**Files:**
- Create: `rules/src/ws180g_rules/klayout_deck.py`
- Test: `tests/rules/test_klayout_deck.py`

**Interfaces:**
- Produces: `write_klayout_deck(table: RuleTable, process, out_path) -> Path` writing `ws180g005.drc` (KLayout DRC DSL, Ruby): header with the variant, no date (reproducible output), `source($input)`, `report("ws180g005", $report)`, `deep`, one `layer = input(L, D)` per drawn and generated layer, layer expressions from `LayerExpr` (`sized` → `.sized(v.um)`, `unrelated` → `.not_interacting(b)`), then one check per row: `min-width` → `.width(v.um, euclidian).output(id, text)`; `gate-length` → the edges of `gate` that lie on `po` edges (`gate.edges & po.edges`), paired across the gate with `.width(v.um)` on that edge set; `min-space` one layer → `.space(v.um)`; two layers → `a.separation(b, v.um)`, with the touching pairs removed for `df.s.np` (butting allowed: the implementer picks the idiom that passes the Task 14 fixtures, `pass_butted` included); `min-enclosure` → `outer.enclosing(inner, v.um)`, restricted to the inner edges that are edges of the named layer when `edges = "sides"`; `min-extension` → the edges of `a & b` not shared with `b`, checked with edge arithmetic (implementer's choice, proven by the fixtures); `min-area` → `.with_area(0, v)`; `exact-size` → the union of the offending shapes of three sub-checks (`.without_area(v*v)`, non-square, bbox width or height ≠ v) merged per shape so that one wrong cut gives one marker, output under one id; `max-distance` → `shapes - taps.sized(v)` (every part of a shape farther than `v` from a tap is a violation, so "every point" is checked, as GF DF.13/DF.14 say); `topology` → a hand-written snippet per `fixture` name kept in `klayout_deck.py` (`co_on_field`, `co_on_gate`, `co_on_butt`, `co_s_butt`, `sab_on_gate`, `v4_array`, `grid`, `angle`, `cut_ortho`); a row with `engines == ["klayout"]` is emitted with a `# KLayout-only` comment; rows with no engines are skipped. The deck takes `-rd input=` and `-rd report=`; a second entry point `ws180g005_batch.drc` takes `-rd list=<file of gds paths>` and writes one report per input, so all fixtures run in one KLayout process.

- [ ] **Step 1: Tests**: the generated file contains `nw.width(1.44.um` and `.output("nw.w"`; every rule id of the table with KLayout in `engines` appears exactly once in an `output(` call; `nsel.w` does not appear; the file contains no date; a table with an unknown kind raises; (`sandbox`) `klayout -b -r ws180g005.drc -rd input=empty.gds -rd report=r.lyrdb` exits 0 on an empty layout.
- [ ] **Step 2–4**, **Step 5: Commit** `feat(rules): KLayout DRC deck generated from the rule table`.

### Task 14: Per-rule fixture generator

**Files:**
- Create: `rules/src/ws180g_rules/fixtures.py`
- Test: `tests/rules/test_fixtures.py`

**Interfaces:**
- Produces: `write_fixtures(table, process, out_dir) -> list[Fixture]` with `Fixture(rule_id, name, path, expect: Literal["pass", "fail"])`, files at `out_dir/<rule_id>/<pass|fail>_<name>.gds`, one top cell `test`, dbu 0.001, `gds2_write_timestamps = False`. **Clean context** added to every fixture except those of `max-distance` rules (which place their own single tap): every nd outside nw gets a `ptap` (a pd box in substrate) within 5 µm and every pd inside nw gets an `ntap` (an nd box in that nw), with every tap satisfying its own enclosure and spacing rules; every cut is drawn with its enclosing layers at 1 µm enclosure; every `pad` sits inside an `mtop` with 5 µm enclosure; every `nw` shape is ≥ `nw.w` and every active shape ≥ `df.w` and ≥ `df.area` unless the rule under test says otherwise. Per kind: `min-width`: a bar of width `w` (`v`, `v + grid`, `v − grid`) and length `L = ceil_grid(max(3 µm, 5 × v, area_min / w))` where `area_min` is the layer's min-area rule and `ceil_grid` rounds up to the grid, `pass_min`, `pass_min_plus_grid`, `fail_min_minus_grid`; a conditional width rule (`mtop.w.long`, `condition = "length > 800"`) draws its bars 801 µm long and adds `pass_short` (width `rules.mtop.w`, 799 µm long); `gate-length`: a wide transistor (W = 2 µm) at L = `v`, `v + grid`, `v − grid`, plus `pass_narrow` (W = `df.w`, L = 2 µm); `min-space`: two shapes at `v`, `v + grid`, `v − grid`, plus `pass_butted` for `df.s.np` and `pass_own_endcap` for `po.s.df`; `min-enclosure`: inner 1 × 1 µm (or the cut's exact size for cuts) inside outer with margin `v`, `v + grid`, `v − grid` on one side and 1 µm on the others; `min-extension`: the crossing with extension `v`, `v + grid`, `v − grid`; `min-area`: a square of area ≥ `v` with sides on grid, and `fail_area_minus` (sides one grid smaller) unless the row has `implied_by` (then only the pass fixture); `exact-size`: `pass_exact`, `fail_oversize` (one grid larger), `fail_rect` (v by v + grid); `max-distance`: a tap at `v` and at `v + grid` from the far edge; `topology`: a generator function per `fixture` name producing one pass and one fail layout. Fixtures are generated into `out/fixtures/` by the build, not committed. Rows with no engines produce no fixtures.

- [ ] **Step 1: Tests**: `nw.w/pass_min.gds` has one nw polygon of width exactly 1440 dbu; `fail_min_minus_grid` has width 1435 dbu; `pad.w/pass_min.gds` has a pad of width 60000 dbu and length ≥ 300000 dbu inside an mtop; `sab.w/fail_min_minus_grid.gds` has sab area ≥ 3.0 µm² and its length on grid; `nw.tap.dmax/fail_min_plus_grid.gds` contains exactly one `nd` inside the `nw`; `mtop.w.long/pass_short.gds` is 799 µm long and 2.16 wide; `co.size/fail_rect.gds` has a 220 × 225 dbu box; a fixture for `df.e.co` contains `co` inside `nd` with 180 dbu margin on one side and 1000 on the others and a `ptap` within 5 µm; `mtop.area` has no fail fixture; every fixture's vertices are multiples of 5 dbu; two runs give byte-identical files; the number of fixtures ≥ 3 × the number of dimensional rules with a fail fixture.
- [ ] **Step 2–4**, **Step 5: Commit** `feat(rules): per-rule pass and fail fixtures from the rule table`.

### Task 15: KLayout runner and the fixture test (gate check 1, KLayout half)

**Files:**
- Create: `rules/src/ws180g_rules/run_klayout.py`
- Test: `tests/rules/test_klayout_fixtures.py` (marker `sandbox`)

**Interfaces:**
- Produces: `run_klayout_many(deck_batch: Path, gds_files: list[Path], out_dir: Path, sandbox: Sandbox, process) -> dict[Path, DrcResult]` with `DrcResult.violations: dict[str, int]` (rule id → count) parsed from each `.lyrdb` (`<category>` names are the rule ids) and `DrcResult.categories_run: int`; `run_klayout(deck, gds, report, sandbox, process)` for one file; `Sandbox(mem="4g", cpus=2)` wraps `build/sandbox-run`. The runner first calls `derive_file` (Task 11) on every input so the deck sees the generated layers, then runs one `klayout -b -r ws180g005_batch.drc -rd list=<file>` for all of them. Results are cached in `out/cache/drc/<sha256(deck, derived gds)>.json`. The test module builds `FIXTURES` at collection time by calling `write_fixtures` into `out/fixtures/` (session-scoped fixture) and parametrises over the result; the engine runs once for all of them and the parametrised tests read the cached results.

- [ ] **Step 1: Test**:

```python
@pytest.mark.sandbox
@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda f: f"{f.rule_id}/{f.name}")
def test_klayout_fixture(fixture, klayout_results):
    result = klayout_results[fixture.path]
    assert result.categories_run > 0
    if fixture.expect == "pass":
        assert result.violations == {}, result.violations          # false positive otherwise
    else:
        assert result.violations == {fixture.rule_id: 1}, result.violations   # exactly its own rule, once
```

plus `test_non_manhattan_cut_rejected` (a 45°-rotated `co` violates `cut.ortho`), `test_off_grid_vertex_rejected` (a vertex at 2 dbu violates `grid`), `test_cache_hit` (a second run of the same inputs does not start a container).
- [ ] **Step 2–4**: run `uv run pytest tests/rules/test_klayout_fixtures.py -rs -v`; fix the deck idioms and fixtures until every fixture passes; every change to a rule value goes to `rules.toml` with its evidence, never to the deck.
- [ ] **Step 5: Commit** `feat(rules): KLayout runner; every Phase 0 fixture passes in KLayout`.

### Task 16: Magic technology file (DRC-only)

**Files:**
- Create: `tech/src/ws180g_tech/magic.py`
- Test: `tests/tech/test_magic_tech.py`

**Interfaces:**
- Produces: `write_magic_tech(table, process, variant, out_dir) -> list[Path]` writing `ws180g005.tech` and `ws180g005.magicrc`. The Phase 0 Magic tech follows Magic's standard layer model (as the sky130 and gf180mcu techs do), because types on one Magic plane cannot overlap and cross-plane enclosure needs contact types: planes `well` (`nwell`, `dnwell`), `active` (`ndiff`, `pdiff`, `poly`, `ntransistor`, `ptransistor`, `ndcontact`, `pdcontact`, `polycontact`, `nsubdiff`/`psubdiff` for the taps), `metal1` (`m1`, `via1`), `metal2` (`m2`, `via2`), `metal3` (`m3`, `via3`), `metal4` (`m4`, `via4`), `metaltop` (`mtop`), `pad`, `sab`, `select` (`nsel`, `psel`), one plane per marker group, `dnw`. The `contact` section declares `ndcontact`/`pdcontact`/`polycontact` and `via1`–`via4` as contacts between their planes. `cifinput` style `gds` with `scalefactor 1 nanometers` builds the composite types with boolean operations on the derived GDS (`ntransistor = po and nd`, `ndcontact = co and nd`, `nsubdiff = ntap`, …) so the lower layer is not lost; `cifoutput` is the inverse. `drc` section: `width`, `spacing` (`touching_ok`), `surround ... absence_illegal`, `overhang`, `area`, `width` + `maxwidth` for cut sizes, `edge4way` where a rule needs a plane-crossing edge check, each with `why "<rule id>: <text>"` and distances in nanometres; rows with `engines == ["klayout"]` are not emitted and are listed in a `# KLayout-only rules (not checked by Magic):` comment block at the top of the `drc` section; no `extract` section (Phase 1). The list of rules Magic cannot express is expected to be longer than the seven KLayout-only rows of the table; each such row gets `engines = ["klayout"]` in `rules.toml` with the reason in `note`.

- [ ] **Step 1: Tests**: the file contains `width nwell 1440 "nw.w` (nanometres); every rule id with Magic in `engines` appears in a `why`; every KLayout-only id appears in the comment block; `nsel.w` appears in neither; (`sandbox`) `magic -dnull -noconsole -rcfile ws180g005.magicrc` with a script `tech name; quit -noprompt` prints `ws180g005`, and `gds read` of a transistor fixture followed by `select top cell; what` lists `ntransistor`.
- [ ] **Step 2–4**, **Step 5: Commit** `feat(tech): Magic technology file for DRC`.

### Task 17: Magic runner and the both-engines test (gate check 1 complete)

**Files:**
- Create: `rules/src/ws180g_rules/run_magic.py`
- Test: `tests/rules/test_magic_fixtures.py`, `tests/rules/test_engines_agree.py` (both `sandbox`)

**Interfaces:**
- Produces: `run_magic_many(tech_dir: Path, gds_files: list[Path], out_dir, sandbox, process) -> dict[Path, DrcResult]`: derives every input (Task 11), then runs **one** `magic -dnull -noconsole -rcfile <magicrc>` with a generated Tcl script that, per file, does `gds read`, `load test`, `drc check`, `drc catchup`, `drc listall why` and writes the rule ids parsed from the `why` strings to a per-file result; counts are error tiles, so `DrcResult.violations` carries rule ids with Magic's counts, and the comparisons use the **set of rule ids**. Results are cached like the KLayout ones, keyed on the tech file and the derived GDS.

- [ ] **Step 1: Tests**: the fixture test as Task 15 against Magic with `set(result.violations) == set()` for pass and `== {fixture.rule_id}` for fail, skipping fixtures of KLayout-only rules with reason `KLayout-only`; `test_engines_agree`: for every fixture of a two-engine rule, `set(klayout.violations) == set(magic.violations)`.
- [ ] **Step 2–4**: fix the Magic tech idioms until all pass; a rule Magic cannot express gets `engines = ["klayout"]` in `rules.toml` with the reason in `note`.
- [ ] **Step 5: Commit** `feat(rules): Magic runner; both engines agree on every fixture`.

### Task 18: GF180MCU mapping, retarget and the fixture-retarget check (gate check 2)

**Files:**
- Create: `precheck/data/gf180mcu.toml`, `precheck/src/ws180g_precheck/mapping.py`, `retarget.py`, `gf180mcu.py`; `docs/phase-0-retarget-log.md`; `tests/precheck/regressions/` (permanent fixtures from failures)
- Test: `tests/precheck/test_mapping.py`, `tests/precheck/test_retarget.py`, `tests/precheck/test_gf180mcu_deck.py` (positive control, `sandbox`), `tests/precheck/test_fixture_retarget.py` (`sandbox`), `tests/precheck/test_gf180mcu_io_mt30.py` (`sandbox`, informative)

**Interfaces:**
- `Mapping` (loaded from TOML, every item with the file it was read from): `target = "gf180mcu"`, `variant = "gf180mcuD"`, `metal_level = "5LM"`; **5LM stack**: the deciding source is the public deck itself: `generic_layers.rb` (lines 235–244, read on 2026-11-07) maps `metal_level_numerical = 5` to `top_via: via4`, `top_metal: metal5`, so the five-metal stack is Metal1–Metal4, Via1–Via4 and **Metal5 (81/0) as the top metal**, which "must comply with MetalTop rule" (`03_met_levels8_2.csv`); the DRM table `03_met_levels8_1.csv` describes the other convention (MetalTop 53/0, skip Metal5) and the mapping file records this conflict in a comment; so `layer_map`: `nw` → 21/0 Nwell; `nd`, `pd` → 22/0 COMP; `po` → 30/0 Poly2; `co` → 33/0 Contact; `m1` → 34/0; `v1` → 35/0; `m2` → 36/0; `v2` → 38/0; `m3` → 42/0; `v3` → 40/0; `m4` → 46/0; `v4` → 41/0 Via4; `mtop` → 81/0 Metal5; `pad` → 37/0 Pad; `sab` → 49/0 SAB; `nsel` → 32/0 Nplus; `psel` → 31/0 Pplus; `dnw` → 12/0 DNWELL; `rhi` → 62/0 Resistor; `mk_res` → 110/5 RES_MK; `mk_dio` → 115/5 DIODE_MK; `mk_bjt` → 118/5 LVS_BJT and 127/5 DRC_BJT (DF.3c checks DRC_BJT); `mk_cap` → 166/5 MOS_CAP_MK (the Phase 0 capacitor is a MOS capacitor; CAP_MK 117/5 is MIM, a later module); `mk_esd` → 24/5 ESD_MK; `mk_nofill` → 111/5 NDMY and 152/5 PMNDMY; `mk_boundary` → 0/0 PR_bndry (the cell boundary EDA mark); `drop = ["gate", "ntap", "ptap"]` (no GF counterpart); all from `06_Drawn_layer10.csv` and `07_Mask_Layer14.csv`), `cut_sizes` (`co` 0.22, `v1`–`v4` 0.26; from CO.1 and Vn.1), `grid = 0.005` (GRID), `oxide` (`ws180g005` is all 5 V: emit `Dualgate` 55/0 and `V5_XTOR` 112/1 as the bounding box of all drawn shapes sized by 1.0 µm, per DV.5/DV.6/DV.8 and PL.11), `drc` (`deck = /foss/pdks/gf180mcuD/libs.tech/klayout/tech/drc/gf180mcu.drc`, switches read from `klayout -b -r gf180mcu.drc -rd help=true` on 2026-11-07: `-rd input=`, `-rd report=`, `-rd metal_level=5LM`, `-rd metal_top=<9K|11K|30K>`, `-rd decks=all,-density,-dummy,-antenna` where the tags come from the `tags:` lines of `rule_decks/density.rb`, `dummy_*.rb`, `antenna.rb`; `metal_top = ["9K", "11K", "30K"]`; `excluded_decks` names each excluded rule file and the reason: density, fill and antenna need a whole die and are Phase 1).
- `retarget(layout, mapping, process) -> klayout.db.Layout`: derive (Task 11) → map layers → `resize_cuts` (centre-preserving; when `(nominal − target) / target_grid` is odd, shift the cut by half a target grid toward −x and −y so both edges land on the target grid, and record `snapped`) → oxide shapes → drop generic layers; `retarget_file(gds_in, gds_out, mapping, process)`.
- `run_gf180mcu_drc_many(gds_files, out_dir, sandbox, metal_top) -> dict[Path, DrcResult]` (one container run per `metal_top`; categories of the `.lyrdb` are GF rule ids; `categories_run` counted).
- **Positive control**: a hand-made GF-native layout `tests/precheck/data/gf_control.gds` (written by a script in the test, not committed as binary) with a Metal1 line narrower than Mn.1 and two COMP shapes closer than DF.3a; the deck must report `Mn.1` and `DF.3a` for every `metal_top` value, and `categories_run > 0`.
- **Failure policy for the retarget check** (written into `docs/phase-0-retarget-log.md`): each GF violation on a pass fixture ends in exactly one of: (a) a generic rule value is raised or a new generic rule is added, with public evidence, in `rules.toml`; (b) the fixture's clean context or `layergen` is corrected because the fixture, not the rule set, was wrong; (c) the fixture is excluded from gate check 2 with the GF rule and the reason recorded (expected only for the `dnw` module fixtures, whose ring topology is the module's open item). Every (a) and (b) adds the failing case to `tests/precheck/regressions/` as a permanent fixture (spec 9.3). The log records date, fixture, GF rule, outcome.

- [ ] **Step 1: Tests**: the mapping covers every drawn and generated layer of `ws180g005` not in `drop`; a 0.27 µm `v1` becomes a 0.26 µm box with the same centre; a 0.36 µm `v4` becomes 0.26 with the same centre; with a test mapping whose `v1` target is 0.225, the resized cut is still on the target grid and `snapped == 1`; the retargeted layout has no generic layer numbers left, has `55/0` covering everything and `mtop` shapes on 81/0; (`sandbox`) the positive control; (`sandbox`) `test_fixture_retarget`: for every **pass** fixture of Task 14 not excluded under (c), and every `metal_top` value, `violations == {}` and `categories_run > 0`; (`sandbox`, informative, never fails the gate) `test_gf180mcu_io_mt30`: the public `gf180mcu_fd_io.gds` (`/foss/pdks/gf180mcuD/libs.ref/gf180mcu_fd_io/gds/`) run with `metal_top=30K`, `decks=metaltop_30k` only, and the MT30 rule ids it reports are written to `out/reports/gf180mcu_io_mt30.json` for the Task 23 report (spec 11.3: "Phase 0 runs that DRC").
- [ ] **Step 2–4**: FAIL, implement, run; apply the failure policy until the gate test passes; re-run Tasks 15 and 17 after every (a) or (b).
- [ ] **Step 5: Commit** `feat(precheck): GF180MCU mapping and retarget; every pass fixture passes the public GF180MCU deck`.

### Task 19: Naming checker

**Files:**
- Create: `build/src/ws180g_build/naming.py`; console script `ws180g-check-names`
- Test: `tests/build/test_naming.py`

**Interfaces:**
- Produces: `parse_library(name) -> LibraryName(process, source, type, name)`, `parse_cell(name) -> CellName(library, cell, size)`, `parse_corner(name) -> Corner(type, temp_c: int, voltage: Decimal, flags: list[str])`, `parse_device(name) -> Device(prefixes, kind, voltage: Decimal | None, properties)`, `check_tree(root: Path) -> list[str]` (errors, empty when clean); the parsers raise `NamingError`. Grammar from spec 6 and the naming document: library `<process>_<source>_<type>[_<name>]`, process ∈ the variant names, source ∈ {`fd`, `osu`} (the derived-library tags of appendix A item 23 are added when the owner decides them), type ∈ {`pr`, `sc`, `io`, `bd`, `xx`, `ip`}, name has no underscore and does not start with a digit; cell `<library>__<cell>[_<size>]`; corner `(tt|ss|ff|sf|fs)_(n?\d{2,3})C_(\d)v(\d{2})(_<flag>)*` (`tt_025C_5v00`, `ss_125C_4v50`, `ff_n40C_5v50`; flag `stat`); voltage tokens `5v0` in library names, `5v00` in corners; device `(esd_)?(rf_)?(nfet|pfet|npn|pnp|diode_<a>2<c>)_(\d{2})v(\d)(_<prop>)*` and `(res|cap)_<kind>_<layer>(_(\d{2})v(\d))?` (voltage optional for resistors and capacitors: `res_generic_po`, `res_high_po`, `cap_mim_m4`). `check_tree(root)` walks `libraries/<library>/` (library names), `libraries/<library>/cells/<cell>/` (cell names), and any file named `<library>__<cell>__<corner>.*` (corner names), and the `libs.ref/<library>/<view>/<cell>.*` tree of a built release.

- [ ] **Step 1: Tests** from spec 6.2: `ws180g005_fd_pr`, `ws180g005_fd_sc_gp9t5v0`, `ws180g005_fd_io`, `ws180g035_fd_sc_ls` parse; `ws180g005_fd_sc_gp_9t` (underscore in name), `abc123_osu_sc_7t` (process unknown) and `ws180g005_fd_sc_7t` (name starts with a digit) raise; `ws180g005_fd_sc_gp9t5v0__nand2_1` parses with size 1; corners `tt_025C_5v00`, `ss_125C_4v50`, `ff_n40C_5v50`, `tt_025C_5v00_stat` parse, `typ_1p20V_25C` raises; devices `nfet_05v0`, `diode_pw2nd_05v0`, `res_generic_po`, `res_high_po`, `cap_mim_m4`, `npn_05v0`, `nfet_05v0_dnw` parse, `nfet5v` raises; `check_tree` on a temp tree with one bad directory name returns one error.
- [ ] **Step 2–4**, **Step 5: Commit** `feat(build): naming checker`.

### Task 20: Private-data checker and git hooks

**Files:**
- Create: `build/src/ws180g_build/private_check.py`, `build/private-allow.txt`; console script `ws180g-check-private`; `tools/git-hooks/pre-commit`, `tools/install-hooks`
- Test: `tests/build/test_private_check.py`

**Interfaces:**
- Produces: `check_private(repo_root) -> list[Finding]` (`path, line, reason`) which (1) loads the evidence set and fails on any entry whose `source` is unregistered or whose source has no `url` or `public != true`; (2) fails on any process field whose `provenance` is not in the allowed set or whose `evidence` ids do not exist in the evidence set; (3) scans every tracked text file outside `tmp/` for the word-boundary, case-insensitive patterns `\bprovenance\s*=\s*"private"`, `\bNDA\b`, `\bconfidential\b`, `\bproprietary\b`, `\binternal use only\b`, with `build/private-allow.txt` listing `<path glob>: <exact line text>` entries that are allowed (the spec's and this plan's own sentences about NDA material, and the checker's own source); (4) recomputes the sha256 of every vendored file against the registry. The test's trigger strings are built at runtime (`"CONFI" + "DENTIAL"`) so the test file never contains them. The pre-commit hook runs `uv run ws180g-check-private` and `uv run ws180g-check-names` on the index; `tools/install-hooks` symlinks it.

- [ ] **Step 1: Tests**: a temp repo copy with an entry of a source whose id is built at runtime → one finding naming the entry; a process field citing `gf180mcu-drm/NOPE.1` → finding; a file containing the runtime-built marker → finding with line number; a file containing `mk_boundary` and `standard` → no finding; the real repository → no findings; the allow-list suppresses exactly the listed line.
- [ ] **Step 2–4**, **Step 5: Commit** `feat(build): private-data checker and pre-commit hook`.

### Task 21: Build command, generated manual, release tree and docs

**Files:**
- Create: `build/src/ws180g_build/main.py` (console script `ws180g-build`), `tree.py`; `rules/src/ws180g_rules/manual.py`; `docs/conf.py` (MyST, furo, `exclude_patterns = ["superpowers/**", "_build"]`), `docs/rules.md` (includes `generated/rules.md`), `docs/evidence.md` (includes `generated/evidence-report.md`)
- Modify: `docs/index.md`, `.github/workflows/ci.yml` (add `uv run ws180g-build --no-container` and the two checkers to the host job)
- Test: `tests/build/test_main.py`, `tests/rules/test_manual.py`

**Interfaces:**
- `ws180g-build [--variant ws180g005] [--out out/] [--no-container]`: load process → evidence report (fails the build if not ok; writes `generated/evidence-report.md`) → rule table → KLayout deck → Magic tech → KLayout tech files → fixtures → manual → (unless `--no-container`) KLayout and Magic fixture runs and the GF180MCU retarget check, with the DRC cache → `tree.assemble(out/ws180g005)` producing `libs.tech/klayout/{ws180g005.lyp,ws180g005.lyt,ws180g005.map,drc/ws180g005.drc}`, `libs.tech/magic/{ws180g005.tech,ws180g005.magicrc}`, `docs/` (the generated pages) → naming and private checks → `out/build-manifest.json` (every output with sha256, the image digest, the git commit). Two runs on the same inputs give byte-identical outputs (no timestamps anywhere).
- `write_manual(table, out_path)`: Markdown from the rule table only (spec 3.6 point 2: no generator reads the evidence set), one section per layer, one row per rule with id, text, value, evidence ids, margin applied (and its reason when recorded), margin achieved (the author's recorded figure, which the report has verified before the manual is written), composed-of, engines, condition, implied-by; the uncovered public rules appear only on the evidence-report page. The rule table (Task 9) is not touched by the report.

- [ ] **Step 1: Tests**: `ws180g-build --no-container` exits 0 and creates the tree above; running it twice gives identical manifests; the manual contains a row for `nw.w` with `1.44` and `gf180mcu-drm/NW.1a/5v`; the manual does not mention `PL.8`; the evidence page lists `PL.8` under density; `sphinx-build -W docs out/docs` succeeds.
- [ ] **Step 2–4**, **Step 5: Commit** `feat(build): one-command build, generated manual and the libs.tech tree`.

### Task 22: Library repositories and submodules

**Files:**
- Create: `tools/repo-settings/apply.py` with `repo.json`, `protection.json`, `ruleset-tags.json` (the meta-repository's settings, committed so a third party can reproduce them); GitHub repositories `wafer-space-robot/ws180g005_fd_pr` and `wafer-space-robot/ws180g005_fd_io` (public, Apache-2.0, README naming the library, the meta-repository and the rule that the content is generated by the build); `.gitmodules` with HTTPS URLs; `libraries/ws180g005_fd_pr`, `libraries/ws180g005_fd_io`; `libraries/README.md` (explains that `ws180g005_fd_sc_gp<N>t5v0` is created in Phase 1 once the track count `N` exists)
- Test: `tests/test_submodules.py`, `tests/build/test_repo_settings.py` (the JSON files parse and `apply.py --dry-run` prints the command list)

**Interfaces:**
- `apply.py <owner/repo> [--dry-run]`: creates the repository if missing and applies: issues on, wiki/projects/discussions off, merge commits only, delete branch on merge, secret scanning and push protection, `main` protection (pull request required, admins enforced, no force push or deletion), the tag ruleset `Enforce vXX.ZZZ version tags`. The naming checker (Task 19) must accept both library names.

- [ ] **Step 1: Test**: `.gitmodules` lists exactly the two paths with `https://github.com/wafer-space-robot/<name>.git`; each path parses with `parse_library`.
- [ ] **Step 2–4**: create the repositories with `apply.py`; `git submodule add`; PASS.
- [ ] **Step 5: Commit** `feat: library repositories ws180g005_fd_pr and ws180g005_fd_io as submodules`.

### Task 23: Phase 0 gate report

**Files:**
- Create: `docs/phase-0-report.md`
- Modify: `README.md` (status line, how to build, how to run the container tests)

**Interfaces:**
- The report states the three gate checks of spec section 10 with evidence: (1) `uv run pytest tests/rules/test_klayout_fixtures.py tests/rules/test_magic_fixtures.py tests/rules/test_engines_agree.py -rs -v` summary line (counts of passed and skipped, with every skip's reason being `KLayout-only`, and the list of KLayout-only rules); (2) `tests/precheck/test_fixture_retarget.py` summary for all three `metal_top` values, the positive-control result, the retarget log, and the fixtures excluded under policy (c); (3) the evidence report summary (rows ok, rows under-margin = 0, uncovered public rules by kind, sources with `transcribed = false`); plus the image digest and its reproducibility test result, the git commit, the informative `gf180mcu_fd_io` MT30 result, the CI sandbox job's outcome, the open items (ONC18 transcription, density/antenna/fill in Phase 1, deep-n-well ring topology, the single-source margin 1.5 for review, the standard-cell library repository), the **deviations from the spec's gate wording** needing the owner's agreement (the GF180MCU deck is run without its density, fill and antenna decks; module fixtures excluded), and the full command sequence a third party runs to reproduce.

- [ ] **Step 1**: run the full build with the container on the build host (`build/sandbox-run` caps: `--mem 4g --cpus 2` per job, at most two jobs at once, so the host's other work keeps its share), save the logs under `out/logs/`.
- [ ] **Step 2**: write the report from the logs (no number in the report that is not in a log).
- [ ] **Step 3: Commit** `docs: Phase 0 gate report`.

---

## Decisions this plan makes (for the owner's review; none blocks execution)

1. GDS numbering of the shared vocabulary table (spec: "assigned in Phase 0 and then fixed").
2. Single-source margin `1.5` (spec 3.6 asks for "a larger chosen margin with its reason"), with "single source" defined as "every binding cited entry from one registered source".
3. One n-well space rule (2.16 µm) for any potential; the equipotential relaxation is a later rule.
4. SCMOS evidence counts both the SUBM (λ = 0.10) and DEEP (λ = 0.09) mappings of SCN6M; the envelope takes the larger.
5. Rows in GF180MCU tables headed `GUIDELINE NO.` or marked `*`, and SCMOS section 10 (overglass), are informative, never binding; so `pad.w` 60 and `pad.s` 13.5 are `chosen`.
6. Fixtures and generated layers use the KLayout Python module; gdsfactory enters with the cell generators in Phase 1.
7. Density, antenna, fill, seal ring and slot generation move to Phase 1 with the precheck and fuzz loop; the GF180MCU retarget check therefore runs the public deck **without** its `density`, `dummy` and `antenna` decks. This is a deviation from the gate wording "passes the public GF180MCU deck" and is reported as such.
8. The `dnw` module fixtures are excluded from gate check 2 (ring-topology conflict between GF180MCU and SCMOS), recorded in the retarget log.
9. The Phase 0 Magic tech is DRC-only with Magic's standard composite-type model; extraction comes with LVS in Phase 1.
10. The container image is built on the public, pinned gf180-tcad base image rather than directly on IIC-OSIC-TOOLS.
11. CI runs the host-side tests on every push; the sandbox job is manual-dispatch and may not fit a hosted runner; container tests run on the build host before each merge and their output is quoted in the PR.
12. The standard-cell library repository is created in Phase 1, when its track count exists.
13. The onsemi ONC18 data sheet needs a person to download it (automated download is refused by the site).
14. Metal thicknesses other than `mtop` and all overlay, implant-doping and dielectric values are `chosen` placeholders in Phase 0; the X-FAB "thickness or junction depth" column is not used as evidence.
15. The `mtop.w.long` threshold of 800 µm is chosen (1000 µm × 0.8).
16. The oxide-thickness and top-metal-thickness ranges carry the 20 % margin with a recorded reason instead of the single-source 50 % (spec 3.2 and 3.6 allow a recorded different margin).
17. The margin achieved is written into each process field by the author and verified by the report (spec 3.6 point 1 and 5.5), so that the rule table and manual carry it without any generator reading the evidence set (spec 3.6 point 2).
