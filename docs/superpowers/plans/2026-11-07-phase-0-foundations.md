# Phase 0 "Foundations" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the data, generators, decks, tech files, checkers and build skeleton of Phase 0 of the ws180g PDK, so that the `ws180g005` 5 V rule set exists as ranges with public evidence, both DRC engines pass every per-rule fixture, every pass fixture retargeted to GF180MCU passes the public GF180MCU deck, and the margin report proves the margin on every rule.

**Architecture:** One uv workspace in the meta-repository with one Python package per pipeline component (`process`, `evidence`, `rules`, `layergen`, `tech`, `precheck`, `build`), all tests under `tests/`. The process description (TOML) is the only source of numbers; the evidence set (TOML entries plus the vendored Apache-2.0 GF180MCU tables) is read only by the margin report; everything else is generated from the loaded process model. DRC runs in a pinned container built on the public gf180-tcad base image, which carries KLayout, Magic, netgen and the public GF180MCU deck.

**Tech Stack:** Python 3.12+ with `uv` (workspace), `tomllib` (standard library) for reading TOML, pydantic 2 for the typed models, the `klayout` Python module (`klayout.db`) for fixture and layer generation, KLayout 0.30.12 (`klayout -b -r`) and Magic 8.3.685 for DRC, Docker with the gf180-tcad base image `ghcr.io/mithro/gf180-tcad-base@sha256:aedc07956fa71f33094decf80828a13e75ace36cb2426f720b0817aa9aca99b6` (public, pinned), pytest, ruff, Sphinx with MyST and furo for the docs.

**Spec:** `docs/superpowers/specs/2026-10-26-ws180g-pdk-design.md` (sections 3, 5, 6, 7, 8, 9, 10 row "0 Foundations", 11.3, 13, 14, appendix A).

## Global Constraints

- All lengths in micrometres, all physical quantities in SI units; there is no lambda in the process description (spec 3.1).
- Design grid: `0.005` µm, a process-description parameter, provisional (spec 5.2). Every rule value, every derived value and every resized cut lies on it.
- Margin rule (spec 3.6): a minimum (width, space, enclosure, extension) is at least `1.2 ×` the largest public minimum; a maximum (tap distance) at most the smallest public maximum `/ 1.2`; a density floor at least `1.2 ×` the largest public floor. Values are rounded **up** to the grid for minima and **down** for maxima. Cut sizes are exempt (spec 3.3). A value bounded by a single public source carries the margin `1.5` (this plan's provisional choice, recorded in the field's `note`; reviewed when a second source appears).
- Nominal cut sizes (spec 3.3): `co` 0.22, `v1`–`v3` 0.27, `v4` 0.36 µm. Retarget regenerates every cut at the target's exact size, centred on the drawn cut, and snaps when the size change is an odd number of grid steps.
- Nothing private (spec 13): every evidence entry cites a public document in the source registry; the private-data checker rejects any other source. GF180MCU values come only from the open PDK's `tables_clear` CSV tables (Apache-2.0). Material that may not be redistributed (SCMOS pages, X-FAB and onsemi data sheets) is transcribed as facts with citations, never vendored.
- Naming (spec 6): process `ws180g005`; libraries `ws180g005_fd_pr`, `ws180g005_fd_io` (the standard-cell library waits for its track count in Phase 1); drawn-layer names of spec 5.1; GDS numbers assigned here and fixed forever.
- Variants (spec 4): `ws180g005` ⊂ `ws180g035`, `ws180g105` ⊂ `ws180g135`; Phase 0 generates content for `ws180g005` and declares the chain.
- Every source file starts with `# SPDX-License-Identifier: Apache-2.0`. Dates ISO 8601. Python run with `uv run`; no `python -c`; no `/tmp` (use `tmp/`).
- Heavy jobs (KLayout, Magic) run only through `build/sandbox-run` with a memory cap, never bare on the host.
- Git: one worktree and branch per task, small commits, PR with independent review, merge commit.

## Review Focus

1. A rule table cell with several values ("0.6/0.5", "0.23 (n = 1) / 0.28 (2 <= n <= 5)", "NA", "0.35 μm2", "1mA/um") must produce one evidence entry per value with the right unit and kind, or none for non-numeric text; a wrong parse silently weakens the envelope. Test in Task 4.
2. SCMOS rules bound a value through two lambda mappings (SUBM 0.10 µm, DEEP 0.09 µm); the envelope must take the larger of the two, not the DEEP column alone (metal-1 width: SUBM 0.30 > DEEP 0.27). Test in Task 8.
3. A fail fixture must violate exactly its own rule and nothing else; a narrow-width fail fixture that also trips a minimum-area rule proves nothing. Test in Tasks 15 and 17 (the assertion `violations == {rule_id: 1}`).
4. A cut whose target size differs from the nominal by an odd number of grid steps (0.27 → 0.26 is two steps per cut, fine; a 0.23 target would be eight steps; a 0.225 target would be nine) must be snapped so that both edges stay on the grid. Test in Task 18.
5. Non-Manhattan or non-square cuts and off-grid vertices must be rejected by the generic deck (KLayout-only rules), otherwise a layout clean in Magic reaches a target deck that forbids them. Test in Task 15.

---

## File structure

```
ws180g/
  pyproject.toml                 uv workspace root; dev deps (pytest, ruff, pydantic)
  uv.lock
  .github/workflows/ci.yml       ruff, pytest -m "not sandbox", checkers
  process/pyproject.toml         package ws180g_process
  process/src/ws180g_process/{__init__,model,load,ranges}.py
  process/data/ws180g/{process,layers,masks,stack,rules}.toml
  evidence/pyproject.toml        package ws180g_evidence
  evidence/src/ws180g_evidence/{__init__,model,load,report,import_gf180mcu,import_scmos}.py
  evidence/sources/gf180mcu-drm/{LICENSE,README.md,*.csv}      vendored Apache-2.0 tables
  evidence/data/{sources,gf180mcu-drm,scmos8,xc018,onc18}.toml  entries
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
  build/sandbox-run              bash: run a command in the capped container
  docker/{Dockerfile,build,IMAGE,IMAGE_ID,versions.json}
  tools/git-hooks/pre-commit, tools/install-hooks
  docs/{conf.py,index.md,generated/}   Sphinx; generated pages are build outputs
  tests/{process,evidence,rules,layergen,tech,precheck,build,sandbox}/test_*.py
  out/                           build output, gitignored
  libraries/ws180g005_fd_pr, libraries/ws180g005_fd_io   submodules (Task 22)
```

Responsibilities: `process` loads and validates; `evidence` imports, loads and reports; `rules` turns the process model into the rule table, the KLayout deck, the fixtures and the engine runners; `layergen` derives generated layers from a layout; `tech` writes tech files; `precheck` retargets to GF180MCU and runs its deck; `build` orchestrates and checks.

## Shared vocabulary (used by every task)

**Rule kinds** (`kind` in `rules.toml`, in the rule table, in the deck generators and in the fixture generator): `min-width`, `min-space` (between shapes of one layer, or `layers = [a, b]` for two layers), `min-enclosure` (`layers = [outer, inner]`: outer encloses inner), `min-extension` (`layers = [a, b]`: a extends beyond its intersection with b, e.g. gate end cap), `min-area`, `exact-size` (square cuts), `max-distance` (tap distance, KLayout-only), `topology` (a named check with a hand-written fixture).

**Evidence entry id**: `<source>/<rule>[/<column>]`, for example `gf180mcu-drm/NW.1a/5v`, `gf180mcu-drm/CO.1`, `gf180mcu-drm/PL.2/5v/n`, `gf180mcu-drm/Mn.1/m1`, `scmos8/7.1/deep`, `scmos8/7.1/subm`, `xc018/metal1/width`.

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

Generated layers in Phase 0 (`layergen`, Task 11): `gate = po ∩ (nd ∪ pd)`; `psel = (pd ∪ (po ∩ sab)).sized(sel.x)`; `nsel = nd.sized(sel.x) − (pd ∪ (po ∩ sab))`; `ntap = nd ∩ nw`; `ptap = pd − nw`. Fill, seal ring, slots and per-target oxide masks beyond the 5 V whole-design mask are Phase 1.

**Phase 0 rule set for `ws180g005`** (values in µm; "GF" = GF180MCU DRM table, 5 V column where one exists; "XC" = X-FAB XC018 data sheet rev 3.0 p.5; "S8" = SCMOS rev 8 rule, DEEP at λ = 0.09 / SUBM at λ = 0.10 from Tables 2c/2b; the generic value is `max × 1.2` rounded up to 0.005 unless marked `×1.5` single-source or `exact`):

| id | kind | layers | value | public minima |
|---|---|---|---|---|
| `nw.w` | min-width | nw | 1.44 | GF NW.1a 0.86; XC 0.86; S8 1.1 12λ 1.08/1.20 |
| `nw.s` | min-space | nw | 2.16 | GF NW.2b 1.7 (NW.2a 0.74 equipotential); XC 1.4; S8 1.2 18λ 1.62/1.80 |
| `nw.e.pd` | min-enclosure | nw, pd | 0.72 | GF DF.4c 0.60; S8 2.3 6λ 0.54/0.60 |
| `nw.e.nd` | min-enclosure | nw, nd | 0.36 | GF DF.4d 0.16; S8 2.4 3λ 0.27/0.30 |
| `nw.s.nd` | min-space | nw, nd | 0.72 | GF DF.16 0.60; S8 2.3 0.54/0.60 |
| `nw.s.pd` | min-space | nw, pd | 0.36 | GF DF.17 0.16; S8 2.4 0.27/0.30 |
| `df.w` | min-width | nd ∪ pd | 0.36 | GF DF.1a 0.30, DF.2a 0.30; XC 0.22; S8 2.1 3λ 0.27/0.30 |
| `df.s` | min-space | nd ∪ pd | 0.435 | GF DF.3a 0.36; XC 0.28; S8 2.2 3λ 0.27/0.30 |
| `df.s.np` | min-space | nd, pd (butting allowed) | 0.48 | GF DF.3a 0.36, DF.3b 0 butted; S8 2.5 4λ 0.36/0.40 |
| `df.x.po` | min-extension | nd ∪ pd, gate | 0.48 | GF DF.6 0.40; S8 3.4 4λ 0.36 / 3λ 0.30 |
| `df.e.co` | min-enclosure | nd ∪ pd, co | 0.18 | GF CO.4 0.07; S8 6.2 1.5λ 0.135/0.15 |
| `df.area` | min-area | nd ∪ pd | 0.305 µm² | GF DF.9 0.2025 ×1.5 |
| `nd.s.pgate` | min-space | nd, gate ∩ nw | 0.625 | GF NP.4a 0.32 (+ `sel.x` 0.24); S8 4.1 3λ 0.27/0.30 |
| `pd.s.ngate` | min-space | pd, gate − nw | 0.625 | GF PP.4a 0.32 (+ `sel.x` 0.24); S8 4.1 |
| `po.w` | min-width | po | 0.24 | GF PL.1 0.20; XC 0.18; S8 3.1 2λ 0.18/0.20 |
| `po.l.n` | min-width (gate length: measured between the gate edges that lie on `po` edges) | gate − nw | 0.72 | GF PL.2 0.60 (n); S8 24.5 3λ 0.27/0.30 |
| `po.l.p` | min-width (gate length, as `po.l.n`) | gate ∩ nw | 0.60 | GF PL.2 0.50 (p); S8 24.5 |
| `po.s` | min-space | po | 0.435 | GF PL.3a 0.24; XC 0.25; S8 3.2.a 4λ 0.36 (3.2 3λ 0.27/0.30) |
| `po.x.df` | min-extension | po, gate (end cap) | 0.27 | GF PL.4 0.22; S8 3.3 2.5λ 0.225 / 2λ 0.20 |
| `po.s.df` | min-space | field poly = po − (nd ∪ pd).sized(0.27, the end-cap zone), nd ∪ pd | 0.36 | GF PL.5a 0.30; S8 3.5 1λ 0.09/0.10 |
| `po.e.co` | min-enclosure | po, co | 0.18 | GF CO.3 0.07; S8 5.2 1.5λ 0.135/0.15 |
| `co.size` | exact-size | co | 0.22 exact | GF CO.1 0.22; XC 0.22; S8 5.1 2λ 0.18/0.20 |
| `co.s` | min-space | co | 0.435 | GF CO.2a 0.25, CO.2b 0.28; XC 0.25; S8 5.3 4λ 0.36 / 3λ 0.30 |
| `co.s.gate` | min-space | co, gate | 0.24 | GF CO.7 0.15; S8 5.4 2λ 0.18/0.20 |
| `co.po.s.df` | min-space | co ∩ po, nd ∪ pd | 0.24 | GF CO.8 0.17; S8 5.6.b 2λ 0.18/0.20 |
| `co.in` | topology | co inside po ∪ nd ∪ pd | — | GF CO.11; S8 sections 5, 6 |
| `co.no.gate` | topology | co ∩ gate = ∅ | — | GF CO.10 |
| `co.no.butt` | topology | co never straddles an nd/pd butting edge | — | GF CO.9 |
| `m1.w` | min-width | m1 | 0.36 | GF Mn.1 0.23; XC 0.23; S8 7.1 3λ 0.27/0.30 |
| `m1.s` | min-space | m1 | 0.36 | GF Mn.2a 0.23, Mn.2b 0.30; XC 0.23; S8 7.2 3λ 0.27/0.30 |
| `m1.e.co` | min-enclosure | m1, co | 0.12 | GF CO.6 0.06; S8 7.3 1λ 0.09/0.10 |
| `m1.e.v1` | min-enclosure | m1, v1 | 0.12 | GF Vn.3 0.06; S8 8.3 1λ |
| `m1.area` | min-area | m1 | 0.217 µm² | GF Mn.3 0.1444 ×1.5 |
| `v1.size` | exact-size | v1 | 0.27 exact | GF Vn.1 0.26; XC 0.26; S8 8.1 3λ 0.27 / 2λ 0.20 |
| `v1.s` | min-space | v1 | 0.435 | GF Vn.2a 0.26, Vn.2b 0.36; XC 0.26; S8 8.2 3λ 0.27/0.30 |
| `m2.w` | min-width | m2 | 0.36 | GF Mn.1 0.28; XC 0.28; S8 9.1 3λ 0.27/0.30 |
| `m2.s` | min-space | m2 | 0.435 | GF Mn.2a 0.28, Mn.2b 0.30; XC 0.28; S8 9.2 4λ 0.36 / 3λ 0.30 |
| `m2.e.v1` | min-enclosure | m2, v1 | 0.12 | GF Vn.4 0.06; S8 9.3 1λ |
| `m2.e.v2` | min-enclosure | m2, v2 | 0.12 | GF Vn.3 0.06; S8 14.3 1λ |
| `m2.area` | min-area | m2 | 0.217 µm² | GF Mn.3 ×1.5 |
| `v2.size`, `v2.s` | as v1 | v2 | 0.27 exact, 0.435 | GF Vn.1, Vn.2a/b; XC; S8 14.1 3λ, 14.2 3λ |
| `m3.w`, `m3.s`, `m3.e.v2`, `m3.e.v3`, `m3.area` | as m2 | m3 | 0.36, 0.435, 0.12, 0.12, 0.217 | GF Mn.*, Vn.3/4; XC; S8 15.1 3λ, 15.2 4λ, 15.3 1λ, 21.3 1λ |
| `v3.size`, `v3.s` | as v1 | v3 | 0.27 exact, 0.435 | S8 21.1 3λ, 21.2 3λ |
| `m4.w`, `m4.s`, `m4.e.v3`, `m4.area` | as m2 | m4 | 0.36, 0.435, 0.12, 0.217 | S8 22.1 3λ, 22.2 4λ, 22.3 1λ |
| `m4.e.v4` | min-enclosure | m4, v4 | 0.12 | GF Vn.3 0.06; S8 29.3 1λ 0.09/0.10 |
| `v4.size` | exact-size | v4 | 0.36 exact | GF Vn.1 0.26; XC Top Via 0.36; S8 29.1 4λ 0.36 / 3λ 0.30 |
| `v4.s` | min-space | v4 | 0.48 | GF Vn.2b 0.36; XC 0.35; S8 29.2 4λ 0.36/0.40 |
| `mtop.w` | min-width | mtop | 2.16 | GF MT30.1a 1.8; XC Top Metal 0.44; S8 30.1 5λ 0.45/0.50 |
| `mtop.w.long` | min-width (lines longer than 800 µm; KLayout-only) | mtop | 2.64 | GF MT30.1b 2.2 at > 1000 µm |
| `mtop.s` | min-space | mtop | 2.16 | GF MT30.2 1.8; XC 0.46; S8 30.2 5λ |
| `mtop.e.v4` | min-enclosure | mtop, v4 | 0.30 | GF MT30.6 0.25 (MT30.5 0.12); S8 30.3 2λ 0.18 / 1λ 0.10 |
| `mtop.area` | min-area | mtop | 0.845 µm² | GF MT.4 0.5625 ×1.5 |
| `mtop.v4.array` | topology (KLayout-only) | every v4 cluster under mtop is at least 2 × 2 | — | GF MT30.8b |
| `pad.w` | min-width | pad | 48 | GF PAD.1 40, TM.1a 40 (S8 10.1 60 is a guideline, informative) |
| `pad.s` | min-space | pad | 13.5 | GF PAD.2 9 ×1.5 |
| `mtop.e.pad` | min-enclosure | mtop, pad | 3.0 | GF PAD.4 2 ×1.5 (S8 10.3 6 guideline) |
| `sab.w` | min-width | sab | 0.505 | GF SB.1 0.42; S8 20.1 4λ 0.36/0.40 |
| `sab.s` | min-space | sab | 0.505 | GF SB.2 0.42; S8 20.2 4λ |
| `sab.s.co` | min-space | sab, co | 0.24 | GF SB.4 0.15; S8 20.3 2λ 0.18/0.20 |
| `sab.e.po` | min-enclosure (sides only: the edges of po ∩ sab that are po edges; the crossing ends are `po.x.sab`) | sab, po ∩ sab | 0.265 | GF SB.9 0.22, SB.12 0.22; S8 20.9 2λ |
| `sab.e.df` | min-enclosure (sides only, as `sab.e.po`) | sab, (nd ∪ pd) ∩ sab | 0.265 | GF SB.6 0.22; S8 20.9 2λ |
| `po.x.sab` | min-extension | po, sab | 0.36 | GF SB.10 0.22; S8 20.10 3λ 0.27/0.30 |
| `df.x.sab` | min-extension | nd ∪ pd, sab | 0.36 | GF SB.7 0.22; S8 20.10 3λ |
| `sab.s.df` | min-space | sab, unrelated nd ∪ pd | 0.265 | GF SB.3 0.22; S8 20.4 2λ |
| `sab.s.po` | min-space | sab, unrelated po | 0.36 | GF SB.5a 0.30; S8 20.5 2λ |
| `sab.area` | min-area | sab | 3.0 µm² | GF SB.13 2.0 ×1.5 |
| `sab.no.gate` | topology | sab ∩ gate = ∅ | — | GF SB.16 |
| `nsel.w`, `nsel.s`, `psel.w`, `psel.s` | min-width / min-space (generated) | nsel, psel | 0.48 | GF NP.1/NP.2/PP.1/PP.2 0.40; S8 4.4 4λ 0.36 / 2λ 0.20 |
| `nw.tap.dmax` | max-distance (KLayout-only) | pd ∩ nw to nearest ntap | 10 | GF DF.13 15 /1.5 |
| `ps.tap.dmax` | max-distance (KLayout-only) | nd − nw to nearest ptap | 10 | GF DF.14 15 /1.5 |
| `dnw.w` | min-width (module) | dnw | 3.675 | GF DN.1 1.7; S8 31.1 34λ 3.06 / 30λ 3.00 |
| `dnw.s` | min-space (module) | dnw | 6.505 | GF DN.2b 5.42; S8 31.2 56λ 5.04 / 50λ 5.00 |
| `grid` | topology (KLayout-only) | all vertices on 0.005 | — | GF GRID, OFFGRID |
| `angle` | topology (KLayout-only) | edges orthogonal or 45° | — | GF ACUTE |
| `cut.ortho` | topology (KLayout-only) | co, v1–v4 orthogonal squares | — | GF CO.1/Vn.1; S8 contact and via pages |

Layer-generation parameter with evidence (in `rules.toml` as kind `generation`): `sel.x` = 0.24 (select extension beyond active and beyond SAB poly; GF NP.5b/PP.5b 0.16, NP.9/PP.9 0.18; S8 4.2 2λ 0.18/0.20).

Public rules the Phase 0 set does not cover (the report must list them): density (PL.8, Mn.4, MT.3, MT30.7, DCF.*, DPF.*, DM.*; S8 guidelines xx.1–xx.3), antenna (ANT.*), latch-up tables (LU.*), wide-metal spacing (Mn.2b beyond what `m1.s` covers), DF.2b, DF.11, PL.7, dummy and marking layers, the `rhi` module and the deep-n-well ring topology (GF NW.5 and S8 31.3/31.4 require opposite n-well placements: recorded as the module's open item).

---

### Task 1: Workspace skeleton and CI

**Files:**
- Create: `pyproject.toml`, `.github/workflows/ci.yml`, `process/pyproject.toml`, `evidence/pyproject.toml`, `rules/pyproject.toml`, `layergen/pyproject.toml`, `tech/pyproject.toml`, `precheck/pyproject.toml`, `build/pyproject.toml`, each `src/<pkg>/__init__.py`, `tests/conftest.py`, `tests/test_workspace.py`, `docs/index.md` (a stub pointing at the spec and this plan)
- Modify: `.gitignore` (add `out/`, `.venv/`, `uv.lock` stays tracked)
- Modify: `README.md` (how to run `uv sync` and `uv run pytest`)

**Interfaces:**
- Produces: package names `ws180g_process`, `ws180g_evidence`, `ws180g_rules`, `ws180g_layergen`, `ws180g_tech`, `ws180g_precheck`, `ws180g_build`; pytest marker `sandbox` (needs Docker); `tests/conftest.py` fixture `repo_root: Path`.

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
- [ ] **Step 3: Create the workspace.** Root `pyproject.toml`: `[project] name = "ws180g"`, `requires-python = ">=3.12"`, `[tool.uv.workspace] members = ["process", "evidence", "rules", "layergen", "tech", "precheck", "build"]`, `[tool.uv.sources]` mapping each member to `{ workspace = true }`, `[dependency-groups] dev = ["pytest>=9", "ruff", "pydantic>=2.11", "klayout>=0.30.12"]`, `[tool.pytest.ini_options] testpaths = ["tests"]`, `addopts = "--strict-markers"`, `markers = ["sandbox: runs a tool in the container through build/sandbox-run (needs Docker)"]`, `[tool.ruff] line-length = 100`. Each member: hatchling build, `packages = ["src/<pkg>"]`, Apache-2.0, `dependencies = ["pydantic>=2.11"]` (plus `"klayout>=0.30.12"` for rules, layergen, precheck).
- [ ] **Step 4: CI** `.github/workflows/ci.yml`: ubuntu-latest, `astral-sh/setup-uv`, `uv sync --all-packages`, `uv run ruff check .`, `uv run pytest -rs -v -m "not sandbox"`.
- [ ] **Step 5: Run** `uv sync --all-packages && uv run pytest -v && uv run ruff check .`. Expected: 7 passed.
- [ ] **Step 6: Commit** `feat: uv workspace with one package per pipeline component`.

### Task 2: Process schema and loader with layers and variants

**Files:**
- Create: `process/src/ws180g_process/model.py`, `load.py`, `ranges.py`; `process/data/ws180g/process.toml`, `layers.toml`
- Test: `tests/process/test_load.py`, `tests/process/test_layers.py`

**Interfaces:**
- Produces: `load_process(data_dir: Path = DEFAULT_DATA) -> Process` where `Process` (pydantic) has `name: str` ("ws180g"), `grid_um: Decimal` (0.005), `variants: dict[str, Variant]` (`Variant.oxides: list[str]`, `Variant.contains: list[str]`), `layers: dict[str, Layer]` (`Layer.gds: tuple[int, int]`, `Layer.kind: Literal["drawn", "generated"]`, `Layer.variant: str | None`, `Layer.module: str | None`, `Layer.purpose: str`), `rules: dict[str, RuleField]` (Task 7), `stack: Stack` (Task 3), `masks: list[Mask]` (Task 3). `Range(min: Decimal, nominal: Decimal, max: Decimal, unit: str)`; `Field(value | range, unit, provenance: Literal["design-target", "public-source", "chosen", "derived"], evidence: list[str], margin: Decimal | None, source: str | None, note: str)`. `on_grid(value: Decimal, grid: Decimal) -> bool`. Loader errors are `ProcessError` with the file and key.
- Decimal everywhere (TOML floats are converted with `Decimal(str(x))`), so 0.435 is exact.

- [ ] **Step 1: Write the failing tests**:

```python
def test_grid_and_variants(process):
    assert process.grid_um == Decimal("0.005")
    assert process.variants["ws180g135"].contains == ["ws180g005", "ws180g035", "ws180g105"]
    assert process.variants["ws180g005"].oxides == ["5v0"]

def test_drawn_layers_fixed_numbers(process):
    assert process.layers["nw"].gds == (1, 0)
    assert process.layers["mtop"].gds == (19, 0)
    assert process.layers["ox_1v8"].variant == "ws180g105"
    assert process.layers["nsel"].kind == "generated"
    gds = [l.gds for l in process.layers.values()]
    assert len(gds) == len(set(gds))

def test_rejects_unknown_provenance(data_copy):      # fixture: copy of process/data/ws180g in tmp_path
    set_toml(data_copy / "process.toml", ["grid", "provenance"], "private")
    with pytest.raises(ProcessError, match="provenance"):
        load_process(data_copy)

def test_rejects_grid_not_multiple_of_dbu(data_copy):
    set_toml(data_copy / "process.toml", ["grid", "value"], 0.0033)   # the grid must be a multiple of the 0.001 µm database unit
    with pytest.raises(ProcessError, match="grid"):
        load_process(data_copy)
```

(The check that every rule value sits on the grid is Task 7's.)

The loader reads five files (`process`, `layers`, `masks`, `stack`, `rules`); in this task `masks.toml`, `stack.toml` and `rules.toml` are created as empty tables and filled in Tasks 3 and 7. `set_toml` is a test helper in `tests/conftest.py` that rewrites one key (`tomllib` has no writer: edit the text with a regex on the `key = value` line).

- [ ] **Step 2: Run** `uv run pytest tests/process -v`. Expected: FAIL (ImportError).
- [ ] **Step 3: Implement** `model.py` (pydantic models above, `extra="forbid"`), `ranges.py` (`Range`, `on_grid`), `load.py` (`tomllib`, one file per table, collects errors with file:key). `process.toml` holds `name`, `schema = 1`, `[grid] value = 0.005 unit = "um" provenance = "chosen" evidence = ["gf180mcu-drm/GRID"] note = "provisional, spec 5.2"`, `[variants.*]`. `layers.toml` holds the table of the shared vocabulary, one `[layers.<name>]` each, with `purpose` text from spec 5.1.
- [ ] **Step 4: Run** `uv run pytest tests/process -v`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(process): schema, loader, grid, variants and the fixed layer numbers`.

### Task 3: Mask list and the 5 V stack ranges

**Files:**
- Create: `process/data/ws180g/masks.toml`, `stack.toml`; extend `model.py` (`Mask(name, drawn: bool, baseline: bool, module: str | None, justification: str)`, `Stack(oxides: dict[str, Oxide], metals: dict[str, MetalLayer])`, `Oxide(thickness: Range, vt_n: Range, vt_p: Range, lmin_n: Field, lmin_p: Field)`, `MetalLayer(thickness: Range | None, sheet_rho: Range | None)`)
- Test: `tests/process/test_masks.py`, `tests/process/test_stack.py`

**Interfaces:**
- Consumes: Task 2 models.
- Produces: `process.masks`, `process.stack.oxides["5v0"]`, `process.stack.metals["mtop"]`.

- [ ] **Step 1: Write the failing tests**:

```python
def test_baseline_masks_have_justification(process):
    baseline = [m for m in process.masks if m.baseline]
    assert {m.name for m in baseline} >= {"nw", "nd", "pd", "po", "co", "m1", "v1", "m2", "v2", "m3", "v3", "m4", "v4", "mtop", "pad", "sab", "nsel", "psel"}
    assert all(m.justification for m in process.masks)
    assert next(m for m in process.masks if m.name == "dnw").module == "deep-n-well"

def test_top_metal_range_is_owner_decision(process):
    mtop = process.stack.metals["mtop"].thickness
    assert (mtop.min, mtop.max, mtop.unit) == (Decimal("0.75"), Decimal("3.6"), "um")   # 9 kÅ / 1.2, 30 kÅ × 1.2

def test_oxide_5v0_ranges_carry_margin(process):
    ox = process.stack.oxides["5v0"]
    assert ox.thickness.unit == "nm" and ox.thickness.min < ox.thickness.nominal < ox.thickness.max
    assert ox.lmin_n.value == Decimal("0.72") and ox.lmin_p.value == Decimal("0.60")
    assert "gf180mcu-drm/PL.2/5v/n" in ox.lmin_n.evidence
```

- [ ] **Step 2: Run**; expected FAIL.
- [ ] **Step 3: Write the data.** `masks.toml`: one entry per drawn baseline layer, the generated selects, the module layers (`dnw`, `rhi`) and the oxide markers, each with `justification` (one sentence from spec 5.3). `stack.toml`: `oxides.5v0.thickness` = GF180MCU public ngspice card `nfet_06v0` TOXE 15.2 nm / TOXP 16.0 nm (file `libs.tech/ngspice/sm141064.ngspice` of the open PDK; cite the card line numbers the implementer reads inside the container at `/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice`), range `min = 15.2 / 1.2`, `max = 16.0 × 1.2`, nominal 15.6; `vt_n`, `vt_p`: GF card VTH0 of `nfet_06v0`/`pfet_06v0` and XC018 p.5 `ne5` 0.77 V / `pe5` 0.84 V, range `[smallest / 1.2, largest × 1.2]`; `lmin_n = 0.72`, `lmin_p = 0.60` with evidence `gf180mcu-drm/PL.2/5v/n|p` and `scmos8/24.5/deep|subm`; `metals.mtop.thickness = Range(0.75, 1.1, 3.6, "um")` with `note` quoting spec 3.2; `metals.m1..m4.sheet_rho` and `thickness` from XC018 p.7 (rows `rm1`, `rm2`, `rm3`, `rm4`, `rmtp`) as single-source ranges with margin 1.5, `provenance = "design-target"`, `evidence = ["xc018/rm1/rs", ...]`.
- [ ] **Step 4: Run**; expected PASS.
- [ ] **Step 5: Commit** `feat(process): mask list and 5 V stack ranges`.

### Task 4: Evidence model, source registry and the GF180MCU table importer

**Files:**
- Create: `evidence/src/ws180g_evidence/model.py`, `load.py`, `import_gf180mcu.py`; `evidence/sources/gf180mcu-drm/README.md`, `LICENSE` (Apache-2.0 copied from the gf180mcu-pdk repository), the 85 `*.csv` files from `docs/physical_verification/design_manual/tables_clear` at the commit recorded in the README; `evidence/data/sources.toml`, `evidence/data/gf180mcu-drm.toml` (generated)
- Test: `tests/evidence/test_model.py`, `tests/evidence/test_import_gf180mcu.py`

**Interfaces:**
- Produces: `Entry(id, source, rule, column: str | None, kind: Kind, layers: list[str], value: Decimal | None, unit: str | None, text: str, cite: str, guideline: bool, lambda_: int | None, lambda_um: Decimal | None)` (`lambda_` is the lambda count of an SCMOS rule, TOML key `lambda`), `Source(id, title, url, licence, retrieved: date, vendored: bool, sha256: dict[str, str], public: bool = True)`; `load_evidence(data_dir) -> Evidence` with `.entries: dict[str, Entry]`, `.sources: dict[str, Source]`; `EvidenceError` for an entry whose `source` is not registered. `import_gf180mcu(src_dir, out_path) -> int` (entries written), also a console script `ws180g-import-gf180mcu`.
- Kinds: the rule kinds of the vocabulary plus `density-floor`, `density-ceiling`, `ratio`, `other`.

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
    assert "gf180mcu-drm/PL.6" not in gf_entries or gf_entries["gf180mcu-drm/PL.6"].value is None  # text-only rule
    assert gf_entries["gf180mcu-drm/PL.10/5v"].unit == "mA/um"

def test_importer_is_reproducible(tmp_path, repo_root):
    import_gf180mcu(repo_root / "evidence/sources/gf180mcu-drm", tmp_path / "gf.toml")
    assert (tmp_path / "gf.toml").read_bytes() == (repo_root / "evidence/data/gf180mcu-drm.toml").read_bytes()

def test_unregistered_source_rejected(tmp_path):
    with pytest.raises(EvidenceError, match="source"):
        load_evidence(dir_with_entry_source_foo)

def test_vendored_sha256_matches(evidence, repo_root):
    for name, digest in evidence.sources["gf180mcu-drm"].sha256.items():
        assert hashlib.sha256((repo_root / "evidence/sources/gf180mcu-drm" / name).read_bytes()).hexdigest() == digest
```

- [ ] **Step 2: Run**; expected FAIL.
- [ ] **Step 3: Vendor the tables.** Fetch the 85 files with a script `evidence/sources/gf180mcu-drm/fetch.py` (records the gf180mcu-pdk commit SHA, the URL and each sha256 into `sources.toml`); write `README.md` naming the source URL, commit, licence and retrieval date.
- [ ] **Step 4: Implement the importer.** `csv` module; the first row is the header, a row whose first cell is `Layer` carries the column names (`3.3V` → `3v3`, `5V`/`5V/6V` → `5v`, `6V` → `6v`); a rule number ending in `*` or `**` sets `guideline = True` (stripped from the id); cell values: numbers → one entry; `a/b` → `/n` and `/p` for PL.2 (gate length) and `/a`, `/b` otherwise; a cell with parenthesised conditions on separate lines (`0.23 (n = 1)` / `0.28 (2 <= n <= 5)`) → `/m1` and `/mn`; `(a)`/`(b)` lines in the description (MT30.1) → `/a`, `/b`; `NA`, `--`, empty → no entry; units from a trailing token (`um2`/`μm2`, `mA/um`, `%`) else `um`. `kind` from the description: contains "width" → `min-width`; "space"/"spacing" → `min-space`; "overlap"/"enclose"/"enclosure" → `min-enclosure`; "extension"/"extend" → `min-extension`; "area" → `min-area`; "Min/max" + "size" → `exact-size`; "Max distance"/"max" + "space" → `max-distance`; "coverage"/"density" → `density-floor` (or `-ceiling` with "Maximum"); "ratio" → `ratio`; otherwise `other`. Every entry's `cite` is `"<file>, row <rule>, column <col>"`.
- [ ] **Step 5: Run**; expected PASS. Commit `feat(evidence): source registry and the GF180MCU design-manual importer` (vendored tables in a separate commit `data(evidence): vendor the GF180MCU design-manual tables (Apache-2.0)`).

### Task 5: SCMOS rev 8 importer and entries

**Files:**
- Create: `evidence/src/ws180g_evidence/import_scmos.py`, `evidence/data/scmos8.toml` (generated), `evidence/sources/scmos8/README.md` (URLs, retrieval date, note that the pages are not vendored)
- Test: `tests/evidence/test_import_scmos.py`

**Interfaces:**
- Produces: `import_scmos(pages: dict[str, str], out_path) -> int` where `pages` maps page name (`well`, `active`, `poly`, `select`, `contact`, `metal1`, `metal2`, `metal3`, `metal4`, `metal5`, `metal6`, `glass`, `sblock`, `thickactive`, `dnw`) to its HTML text; console script `ws180g-import-scmos` that fetches `https://bears.ece.ucsb.edu/class/ece224a/scmos/scmos-<page>.html` into `tmp/scmos8/` (gitignored) and imports. Entries per rule and column: id `scmos8/<rule>/<scmos|subm|deep>`, `value` in µm = lambda count × `lambda_um`, `lambda_um` 0.10 for `subm` and 0.09 for `deep` (SCN6M, Tables 2b and 2c), `lambda` the count, `unit = "um"`; the `scmos` column (no 0.18 µm mapping) is kept with `lambda_um = None` and `value = None`. On pages with several column groups, the group for the most metals (`3+`, `4+`, `5+`, `6`) is used. `n/a` → no entry. Section 10 (glass) entries are in microns with `guideline = True`.

- [ ] **Step 1: Write the failing tests** on saved page excerpts under `tests/evidence/data/scmos/*.html` (short excerpts of the tables, each at most 40 lines, with the source URL in a comment):

```python
def test_poly_width(scmos):
    assert scmos["scmos8/3.1/deep"].lambda_ == 2 and scmos["scmos8/3.1/deep"].value == Decimal("0.18")
    assert scmos["scmos8/3.1/subm"].value == Decimal("0.20")
def test_poly_space_over_active_deep(scmos):
    assert scmos["scmos8/3.2.a/deep"].value == Decimal("0.36")
def test_via_exact_size_uses_highest_metal_group(scmos):
    assert scmos["scmos8/8.1/deep"].kind == "exact-size" and scmos["scmos8/8.1/deep"].lambda_ == 3
    assert scmos["scmos8/8.1/subm"].lambda_ == 2
def test_top_via_and_metal6(scmos):
    assert scmos["scmos8/29.1/deep"].value == Decimal("0.36") and scmos["scmos8/30.1/subm"].value == Decimal("0.50")
def test_glass_is_guideline_in_microns(scmos):
    assert scmos["scmos8/10.1"].guideline and scmos["scmos8/10.1"].value == Decimal("60")
def test_na_dropped(scmos):
    assert "scmos8/31.1/scmos" not in scmos or scmos["scmos8/31.1/scmos"].value is None
```

- [ ] **Step 2: Run**; FAIL. **Step 3: Implement** with `html.parser` (standard library): strip tags, read rows of `rule, description, c1, c2, c3[, c4, c5, c6]`; the `kind` keyword map of Task 4; a `*` after a number is ignored. **Step 4: Run**; PASS. Generate `evidence/data/scmos8.toml` from the live pages and commit it with the README. **Step 5: Commit** `feat(evidence): SCMOS rev 8 importer and entries`.

### Task 6: X-FAB XC018 and onsemi ONC18 entries

**Files:**
- Create: `evidence/data/xc018.toml` (hand-transcribed), `evidence/data/onc18.toml` (registry entry only until the PDF is retrieved), `evidence/sources/xc018/README.md`, `evidence/sources/onc18/README.md`
- Test: `tests/evidence/test_hand_entries.py`

**Interfaces:**
- Produces entries `xc018/<mask>/<width|spacing>` for the ten rows of "Basic Design Rules" (p.5): `nwell` 0.86/1.4, `active` 0.22/0.28, `poly` 0.18/0.25, `polyres` 0.44/0.44, `contact` 0.22/0.25, `metal1` 0.23/0.23, `via` 0.26/0.26, `metal2345` 0.28/0.28, `topvia` 0.36/0.35, `topmetal` 0.44/0.46; `xc018/<device>/<vt|rs|thickness>` for `ne5`, `pe5` (p.5) and `rm1`, `rm2`, `rm3`, `rm4`, `rm5`, `rmtp`, `rmtpl`, `rpp1k1` (p.7); `cite = "X-FAB XC018 process data sheet rev 3.0, page N, table T, row R"`. The contact and via rows get `kind = "exact-size"` for width (the sheet gives one size), `min-space` for spacing.
- ONC18: the data sheet `ONC181818/D` could not be downloaded by the automation (the server returns an HTML page to non-browser clients). `onc18.toml` holds the source registry entry with `retrieved = false` and no entries; the margin report lists the source as "registered, not yet transcribed". When a person downloads the PDF into `tmp/ref/onsemi/`, its "Process Characteristics" values are transcribed here with page citations.

- [ ] **Step 1: Tests**: `xc018/topvia/width` is exact-size 0.36; `xc018/metal1/spacing` 0.23; `xc018/rpp1k1/rs` 1000 with unit `ohm/sq`; every xc018 entry has a `cite` containing "page"; `evidence.sources["onc18"].retrieved is False` and no entry has source `onc18`.
- [ ] **Step 2–4**: FAIL, write the TOML by hand from the PDF pages (read `tmp/ref/xfab/xc018_datasheet.pdf` pages 5 and 7 with the Read tool), PASS.
- [ ] **Step 5: Commit** `data(evidence): X-FAB XC018 entries; onsemi ONC18 registered, pending retrieval`.

### Task 7: The rule fields of the process description

**Files:**
- Create: `process/data/ws180g/rules.toml`; extend `model.py` with `RuleField(kind: Kind | Literal["generation"], layers: list[str], value: Decimal | None, unit, variant, provenance, evidence: list[str], margin: Decimal | None, engines: list[Literal["klayout", "magic"]], condition: str | None, fixture: str | None, note: str)`
- Test: `tests/process/test_rules.py`

**Interfaces:**
- Produces: `process.rules["nw.w"]` etc., exactly the Phase 0 rule set table; `engines` defaults to both; `fixture` set for every `topology` rule.

- [ ] **Step 1: Tests**: `process.rules["df.s"].value == Decimal("0.435")`; `process.rules["co.size"].kind == "exact-size" and process.rules["co.size"].margin is None`; `process.rules["nw.tap.dmax"].engines == ["klayout"]`; every rule's value is on grid; every rule has `evidence` or `provenance == "chosen"`; every topology rule has a `fixture`; `set(process.rules) ⊇` the ids of the table; no rule's `layers` names an unknown layer (allow the derived names `df` = nd ∪ pd, `gate`, `field_po` which the loader maps to layer expressions).
- [ ] **Step 2–4**: FAIL, write `rules.toml` (one `[rules.<id>]` table per row, `note` quoting the public values as in the plan table, `margin = 1.2` or `1.5`, `condition = "length > 800"` for `mtop.w.long`, `fixture = "co_on_field"` etc.), PASS.
- [ ] **Step 5: Commit** `feat(process): the Phase 0 ws180g005 rule fields with evidence`.

### Task 8: Evidence margin report

**Files:**
- Create: `evidence/src/ws180g_evidence/report.py`; console script `ws180g-evidence-report`
- Test: `tests/evidence/test_report.py`

**Interfaces:**
- Consumes: `load_process()`, `load_evidence()`.
- Produces: `margin_report(process, evidence) -> Report` with `Report.rows: list[Row]` (`rule_id, value, kind, cited: list[Entry], largest_public: Decimal | None, margin_required, margin_achieved: Decimal | None, status: Literal["ok", "under-margin", "chosen", "missing-entry", "exempt"]`), `Report.uncovered: list[Entry]` (public non-guideline entries of kinds width/space/enclosure/extension/area/exact-size/max-distance/density that no rule cites), `Report.sources: list[Source]`; `Report.to_markdown()`, `Report.to_json()`; `report.ok` is `False` if any row is `under-margin` or `missing-entry`. For `max-distance` the achieved margin is `smallest_public / value`; for `exact-size` the status is `exempt` with the equality `value == largest_public` checked; guideline entries never bound a rule but are listed beside it as "informative".

- [ ] **Step 1: Tests**:

```python
def test_metal1_width_takes_subm_mapping(report):
    row = report["m1.w"]
    assert row.largest_public == Decimal("0.30") and row.margin_achieved == Decimal("1.2") and row.status == "ok"
def test_under_margin_detected(process_with_m1_w_0_35, evidence):
    assert margin_report(process_with_m1_w_0_35, evidence)["m1.w"].status == "under-margin"
def test_missing_entry_detected(process_citing_nonexistent_id, evidence):
    assert margin_report(...).ok is False
def test_single_source_margin(report):
    assert report["df.area"].margin_required == Decimal("1.5") and report["df.area"].status == "ok"
def test_uncovered_lists_density(report):
    assert "gf180mcu-drm/PL.8/5v" in {e.id for e in report.uncovered}
def test_full_report_ok(report):
    assert report.ok, [r for r in report.rows if r.status in ("under-margin", "missing-entry")]
```

- [ ] **Step 2–4**: FAIL, implement, PASS (`test_full_report_ok` must pass against the real data; if it fails, the rule value or the evidence id in `rules.toml` is wrong: fix the data, not the test).
- [ ] **Step 5: Commit** `feat(evidence): margin report`.

### Task 9: Rule table

**Files:**
- Create: `rules/src/ws180g_rules/table.py`; console script `ws180g-rule-table`
- Test: `tests/rules/test_table.py`

**Interfaces:**
- Produces: `RuleTable.from_process(process, variant="ws180g005") -> RuleTable` with `rows: list[RuleRow]` (`id, kind, layers: list[LayerExpr], value, unit, field: str` (e.g. `rules.nw.w`), `variant, evidence: list[str], margin, engines, condition, fixture, text`), `LayerExpr` a small algebra over layer names (`name`, `union`, `intersection`, `difference`), parsed from the strings `nd|pd`, `po&df`, `gate-nw` used in `rules.toml`; `RuleTable.write_json(path)`, `write_csv(path)`, `read_json(path)`. Rows are in a stable order (by layer, then id). A field of kind `generation` (`sel.x`) is kept as a row with `engines = []`; the deck and fixture generators skip such rows and `layergen` reads the value from the process model.

- [ ] **Step 1: Tests**: row count equals the number of `ws180g005` rules; `table["df.w"].layers[0] == union("nd", "pd")`; `table["po.l.p"].layers[0] == intersection("gate", "nw")`; `write_json` then `read_json` round-trips; unknown layer name raises.
- [ ] **Step 2–4**: FAIL, implement, PASS. **Step 5: Commit** `feat(rules): machine-readable rule table`.

### Task 10: Reproducible container image and sandbox runner

**Files:**
- Create: `docker/Dockerfile`, `docker/build`, `docker/IMAGE`, `docker/IMAGE_ID`, `docker/versions.json`, `build/sandbox-run`
- Test: `tests/sandbox/test_image.py` (marker `sandbox`)

**Interfaces:**
- Produces: image `ghcr.io/wafer-space-robot/ws180g-pdk-base` (built locally as `:local` until a registry push is set up), `FROM ghcr.io/mithro/gf180-tcad-base@sha256:aedc07956fa71f33094decf80828a13e75ace36cb2426f720b0817aa9aca99b6`; adds `PATH=/opt/ws180g/bin:/foss/tools/klayout:/foss/tools/magic/bin:/foss/tools/netgen/bin:...` and a locked venv `/opt/ws180g` holding the workspace's runtime dependencies (pydantic, klayout) from `docker/requirements.lock` (uv-exported, hashes); project code is mounted, never baked. `build/sandbox-run [--mem 4g] [--cpus 2] [--pids 2048] --workdir DIR [--network none] -- CMD...` is a port of gf180-tcad `tools/sandbox-run` (refuses the repo root, `$HOME` and the git dirs as workdir; mounts the repo read-only at `/work/src` and the workdir read-write at `/work/out`; exit code is the command's).
- `docker/build` is a copy of gf180-tcad's `docker/base/build` with the image name changed (pinned BuildKit, `SOURCE_DATE_EPOCH` from the last commit touching the inputs, `rewrite-timestamp`, no attestations); it prints the config digest, which is committed to `IMAGE_ID`.

- [ ] **Step 1: Tests** (`sandbox` marker): `sandbox-run -- klayout -v` prints `KLayout 0.30.12`; `-- magic --version` prints `8.3.685`; `-- netgen -batch quit` exits 0; `-- test -r /foss/pdks/gf180mcuD/libs.tech/klayout/tech/drc/gf180mcu.drc`; a command allocating 8 GiB under `--mem 1g` exits 137; `--workdir <repo root>` is refused with exit 2.
- [ ] **Step 2–4**: build (`docker/build --tag ws180g-pdk-base:local`), run tests, PASS. Record `versions.json` (base digest, klayout 0.30.12, magic 8.3.685, netgen 1.5.324, open_pdks commit as reported by `/foss/pdks/versions.txt`).
- [ ] **Step 5: Commit** `feat(docker): pinned image on the gf180-tcad base with Magic and netgen on PATH; sandbox runner`.

### Task 11: Layer generation

**Files:**
- Create: `layergen/src/ws180g_layergen/derive.py`
- Test: `tests/layergen/test_derive.py`

**Interfaces:**
- Consumes: `Process` (layer numbers, `rules["sel.x"]`).
- Produces: `derive(layout: klayout.db.Layout, process: Process, variant: str = "ws180g005") -> None` (adds the generated layers in place; flat per top cell is acceptable in Phase 0) and `derive_file(gds_in: Path, gds_out: Path, process)`. Definitions (the shared vocabulary): `gate = po ∩ (nd ∪ pd)`; `psel = (pd ∪ (po ∩ sab)).sized(sel.x)` (unsilicided poly is p+ by default in Phase 0); `nsel = nd.sized(sel.x) − (pd ∪ (po ∩ sab))`, so a select never covers active or resistor poly of the other type and the two selects meet at a butting edge without overlapping; `ntap = nd ∩ nw`; `ptap = pd − nw`. Each generated layer is written to its GDS number from `layers.toml`. All operations in `klayout.db.Region` with the layout dbu 0.001 µm.

- [ ] **Step 1: Tests** (build small layouts in-test with `klayout.db`): an nfet (nd 2 × 1 with po crossing) yields `gate` of the crossing area and `nsel` = nd grown by 0.24 on each side; an nd box inside nw yields `ntap`; a pd box outside nw yields `ptap`; nd and pd butted (shared edge) yield non-overlapping `nsel`/`psel` meeting at the edge; `po ∩ sab` yields `psel` around it; a layout with no `sab` has no `psel` from poly; output dbu is 0.001.
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
- Produces: `write_klayout_deck(table: RuleTable, process, out_path) -> Path` writing `ws180g005.drc` (KLayout DRC DSL, Ruby): header with the variant, the generated date is **not** written (reproducible output), `source($input)`, `report("ws180g005", $report)`, `deep`, one `layer = input(L, D)` per drawn and generated layer, layer expressions from `LayerExpr`, then one check per row: `min-width` → `.width(v.um, euclidian).output(id, text)`; `min-space` one layer → `.space(v.um)`; two layers → `a.separation(b, v.um)` (for `df.s.np` with butting allowed: `.separation(b, v.um, projection)` after removing touching pairs, the implementer picks the idiom that passes the Task 14 fixtures); `min-enclosure` → `outer.enclosing(inner, v.um)`; `min-extension` → the edges of `a ∩ b` not shared with `b`, checked with `.enclosing`/edge arithmetic (implementer's choice, proven by the fixtures); `min-area` → `.with_area(0, v)`; `exact-size` → `.without_area(v*v) + non-square + .with_bbox_width/height` checks under one id; `max-distance` → `shapes.not_interacting(taps.sized(v))` style check; `topology` → a hand-written snippet per `fixture` name kept in `klayout_deck.py` (`co_on_field`, `co_on_gate`, `co_on_butt`, `sab_on_gate`, `v4_array`, `grid`, `angle`, `cut_ortho`); a row with `engines == ["klayout"]` is emitted with a `# KLayout-only` comment. The deck takes `-rd input=` and `-rd report=`.

- [ ] **Step 1: Tests**: the generated file contains `nw.width(1.44.um` and `.output("nw.w"`; every rule id of the table appears exactly once in an `output(` call; the file contains no date; a table with an unknown kind raises; (`sandbox`) `klayout -b -r ws180g005.drc -rd input=empty.gds -rd report=r.lyrdb` exits 0 on an empty layout.
- [ ] **Step 2–4**, **Step 5: Commit** `feat(rules): KLayout DRC deck generated from the rule table`.

### Task 14: Per-rule fixture generator

**Files:**
- Create: `rules/src/ws180g_rules/fixtures.py`
- Test: `tests/rules/test_fixtures.py`

**Interfaces:**
- Produces: `write_fixtures(table, process, out_dir) -> list[Fixture]` with `Fixture(rule_id, name, path, expect: Literal["pass", "fail"])`, files at `out_dir/<rule_id>/<pass|fail>_<name>.gds`, one top cell `test`, dbu 0.001. Per kind: `min-width`: `pass_min` (a bar exactly `v` wide, 3 µm long), `pass_min_plus_grid`, `fail_min_minus_grid`; `min-space`: two shapes at `v`, `v + grid`, `v − grid`; `min-enclosure`: inner 1 × 1 µm (or the cut's exact size for cuts) inside outer with margin `v`, `v + grid`, `v − grid` on one side and 1 µm on the others; `min-extension`: the crossing with extension `v`, `v + grid`, `v − grid`; `min-area`: a square of area `v` (sides rounded up to grid; test passes when area ≥ v), `fail_area_minus` (sides one grid smaller); `exact-size`: `pass_exact`, `fail_oversize` (one grid larger), `fail_rect` (v by v + grid); `max-distance`: a tap at `v` and at `v + grid` from the far edge; `topology`: a generator function per `fixture` name producing one pass and one fail layout. Extra pass fixtures where a rule has an allowed special case: `df.s.np/pass_butted` (nd and pd sharing an edge), `po.s.df/pass_own_endcap` (a transistor whose end cap is the only poly near the active). Gate-length rules (`po.l.n`, `po.l.p`) draw a wide transistor (W = 2 µm) at L = `v`, `v + grid`, `v − grid`, and a narrow one (W = `df.w`, L = 2 µm) that must pass. Every fixture adds the context the rule needs (a `gate` fixture draws nd and po crossing so that `layergen` derives the gate; cuts are drawn with their enclosing layers at generous (1 µm) enclosures; nothing else is at a rule edge). Fixtures are generated into `out/fixtures/` by the build, not committed.

- [ ] **Step 1: Tests**: `nw.w/pass_min.gds` has one polygon of width exactly 1440 dbu; `fail_min_minus_grid` has width 1435 dbu; `co.size/fail_rect.gds` has a 220 × 225 dbu box; a fixture for `df.e.co` contains `co` inside `nd` with 180 dbu margin on one side and 1000 on the others; every fixture's vertices are multiples of 5 dbu; the number of fixtures ≥ 3 × the number of dimensional rules.
- [ ] **Step 2–4**, **Step 5: Commit** `feat(rules): per-rule pass and fail fixtures from the rule table`.

### Task 15: KLayout runner and the fixture test (gate check 1, KLayout half)

**Files:**
- Create: `rules/src/ws180g_rules/run_klayout.py`
- Test: `tests/rules/test_klayout_fixtures.py` (marker `sandbox`)

**Interfaces:**
- Produces: `run_klayout(deck: Path, gds: Path, report: Path, sandbox: Sandbox) -> DrcResult` with `DrcResult.violations: dict[str, int]` (rule id → count) parsed from the `.lyrdb` XML (`<category>` names are the rule ids); `Sandbox(mem="4g", cpus=2)` wraps `build/sandbox-run`. The runner first calls `derive_file` (Task 11) so the deck sees the generated layers, then runs `klayout -b -r <deck> -rd input=<derived.gds> -rd report=<report>`.
- Results are cached in `out/cache/drc/<sha256(deck, gds)>.json`.

- [ ] **Step 1: Test**:

```python
@pytest.mark.sandbox
@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda f: f"{f.rule_id}/{f.name}")
def test_klayout_fixture(fixture, deck, sandbox):
    result = run_klayout(deck, fixture.path, tmp / "r.lyrdb", sandbox)
    if fixture.expect == "pass":
        assert result.violations == {}, result.violations          # false positive otherwise
    else:
        assert result.violations == {fixture.rule_id: 1}, result.violations   # exactly its own rule, once
```

plus `test_non_manhattan_cut_rejected` (a 45°-rotated `co` violates `cut.ortho`), `test_off_grid_vertex_rejected` (a vertex at 2 dbu violates `grid`).
- [ ] **Step 2–4**: run `uv run pytest tests/rules/test_klayout_fixtures.py -rs -v`; fix the deck idioms and fixtures until every fixture passes; every change to a rule value goes to `rules.toml` with its evidence, never to the deck.
- [ ] **Step 5: Commit** `feat(rules): KLayout runner; every Phase 0 fixture passes in KLayout`.

### Task 16: Magic technology file (DRC-only)

**Files:**
- Create: `tech/src/ws180g_tech/magic.py`
- Test: `tests/tech/test_magic_tech.py`

**Interfaces:**
- Produces: `write_magic_tech(table, process, variant, out_dir) -> list[Path]` writing `ws180g005.tech` and `ws180g005.magicrc`. Phase 0 Magic tech is DRC-only: one Magic type per drawn and generated layer, no composite contact types and no extraction section (Phase 1 adds them). Sections: `tech`, `version`, `planes` (`well`, `active`, `metal1`…`metal4`, `metaltop`, `marks`), `types` (`nw`, `dnw` on well; `nd`, `pd`, `po`, `co`, `sab`, `nsel`, `psel`, `gate`, `ntap`, `ptap` on active; `m1`/`v1` on metal1 … `m4`/`v4` on metal4; `mtop`, `pad`, `rhi`, `mk_*` as marks), `styles`, `cifinput` style `gds` with `scalefactor 1 nanometers` (Magic's internal unit is then 1 nm and every `drc` distance is written in nanometres: `width nw 1440 ...`) mapping each GDS layer to its type, `cifoutput` the inverse, `drc` section with `width`, `spacing` (`touching_ok` for same-layer, `touching_illegal` for `df.s.np`? no: butting is allowed, so `touching_ok`), `surround ... absence_illegal`, `overhang`, `area`, `exact_overlap`/`width`+`maxwidth` for cut sizes, each with `why "<rule id>: <text>"`; rows with `engines == ["klayout"]` are not emitted and are listed in a `# KLayout-only rules (not checked by Magic):` comment block at the top of the `drc` section. Magic type names are the layer names.

- [ ] **Step 1: Tests**: the file contains `width nw 1440 "nw.w` (nanometres); every rule id with Magic in `engines` appears in a `why`; every KLayout-only id appears in the comment block; (`sandbox`) `magic -dnull -noconsole -rcfile ws180g005.magicrc` with a script `tech name; quit -noprompt` prints `ws180g005`.
- [ ] **Step 2–4**, **Step 5: Commit** `feat(tech): Magic technology file for DRC`.

### Task 17: Magic runner and the both-engines test (gate check 1 complete)

**Files:**
- Create: `rules/src/ws180g_rules/run_magic.py`
- Test: `tests/rules/test_magic_fixtures.py`, `tests/rules/test_engines_agree.py` (both `sandbox`)

**Interfaces:**
- Produces: `run_magic(tech_dir: Path, gds: Path, sandbox) -> DrcResult` running `magic -dnull -noconsole -rcfile <magicrc>` with a generated Tcl script (`gds read`, `load test`, `drc check`, `drc catchup`, `drc listall why` → parse rule ids from the `why` strings) in the container.

- [ ] **Step 1: Tests**: the same parametrised fixture test as Task 15 against Magic, skipping fixtures of KLayout-only rules with reason `KLayout-only`; `test_engines_agree`: for every fixture of a two-engine rule, `run_klayout(...).violations == run_magic(...).violations`.
- [ ] **Step 2–4**: fix the Magic tech idioms until all pass; a rule Magic cannot express gets `engines = ["klayout"]` in `rules.toml` with the reason in `note` (expected: `mtop.w.long`, `mtop.v4.array`, `nw.tap.dmax`, `ps.tap.dmax`, `grid`, `angle`, `cut.ortho`; `co.in` and `sab.no.gate` may be expressible with an illegal-type `width` trick, the implementer decides and records).
- [ ] **Step 5: Commit** `feat(rules): Magic runner; both engines agree on every fixture`.

### Task 18: GF180MCU mapping, retarget and the fixture-retarget check (gate check 2)

**Files:**
- Create: `precheck/data/gf180mcu.toml`, `precheck/src/ws180g_precheck/mapping.py`, `retarget.py`, `gf180mcu.py`
- Test: `tests/precheck/test_mapping.py`, `tests/precheck/test_retarget.py`, `tests/precheck/test_fixture_retarget.py` (`sandbox`)

**Interfaces:**
- `Mapping` (loaded from TOML): `target = "gf180mcu"`, `variant = "gf180mcuD"` (5LM; `03_met_levels8_1.csv`: Metal1, Via1, Metal2, Via2, Metal3, Via3, Metal4, Via4, MetalTop), `layer_map` (`nw` → 21/0 Nwell; `nd`, `pd` → 22/0 COMP; `po` → 30/0 Poly2; `co` → 33/0 Contact; `m1` → 34/0; `v1` → 35/0; `m2` → 36/0; `v2` → 38/0; `m3` → 42/0; `v3` → 40/0; `m4` → 46/0; `v4` → 41/0 Via4; `mtop` → 53/0 MetalTop; `pad` → 37/0 Pad; `sab` → 49/0 SAB; `nsel` → 32/0 Nplus; `psel` → 31/0 Pplus; `dnw` → 12/0 DNWELL; `rhi` → 62/0 Resistor; `mk_res` → 110/5 RES_MK; `mk_dio` → 115/5 DIODE_MK; `mk_bjt` → 118/5 LVS_BJT; `mk_cap` → 166/5 MOS_CAP_MK; `mk_esd` → 24/5 ESD_MK; `mk_nofill` → 111/5 NDMY and 152/5 PMNDMY; `mk_boundary` → 63/0 Border; all from `06_Drawn_layer10.csv` and `07_Mask_Layer14.csv`), `cut_sizes` (`co` 0.22, `v1`–`v3` 0.26, `v4` 0.26; from CO.1 and Vn.1), `oxide` (`ws180g005` is all 5 V: emit `Dualgate` 55/0 and `V5_XTOR` 112/1 as the bounding box of all drawn shapes sized by 1.0 µm, per DV.5/DV.6/DV.8 and PL.11), `drc` (`deck = /foss/pdks/gf180mcuD/libs.tech/klayout/tech/drc/gf180mcu.drc`, `args = ["-rd", "metal_level=5LM", "-rd", "decks=all,-density,-dummy,-antenna"]`, `metal_top = ["9K", "30K"]`).
- `retarget(layout, mapping, process) -> klayout.db.Layout`: derive (Task 11) → map layers → `resize_cuts` (centre-preserving; when `(nominal − target) / grid` is odd, shift the cut by half a grid toward the origin so both edges land on grid, and record the count of snapped cuts) → oxide shapes → drop generic layers. `retarget_file(gds_in, gds_out, mapping, process)`.
- `run_gf180mcu_drc(gds, report, sandbox, metal_top) -> DrcResult` (categories of the `.lyrdb` are GF rule ids).

- [ ] **Step 1: Tests**: the mapping covers every drawn and generated layer of `ws180g005` (test enumerates `process.layers` minus the other variants' markers); a 0.27 µm `v1` becomes a 0.26 µm box with the same centre; a 0.36 µm `v4` becomes 0.26 with the same centre; with a test mapping whose `co` target is 0.225, the resized cut is still on grid and `snapped == 1`; the retargeted layout has no generic layer numbers left and has `55/0` covering everything; (`sandbox`) `test_fixture_retarget`: for every **pass** fixture of Task 14 and both `metal_top` values, `run_gf180mcu_drc(...).violations == {}`.
- [ ] **Step 2–4**: FAIL, implement, run; every GF violation on a pass fixture is a defect: raise the generic value in `rules.toml` (with the GF rule as evidence and the reason), or fix `layergen`/the oxide generation, re-run Tasks 15 and 17, and add the failing case to `tests/precheck/regressions/` as a permanent fixture (spec 9.3). Record each change in `docs/phase-0-retarget-log.md` (date, fixture, GF rule, change).
- [ ] **Step 5: Commit** `feat(precheck): GF180MCU mapping and retarget; every pass fixture passes the public GF180MCU deck`.

### Task 19: Naming checker

**Files:**
- Create: `build/src/ws180g_build/naming.py`; console script `ws180g-check-names`
- Test: `tests/build/test_naming.py`

**Interfaces:**
- Produces: `parse_library(name) -> LibraryName(process, source, type, name)`, `parse_cell(name) -> CellName(library, cell, size)`, `parse_corner(name) -> Corner(type, temp_c: int, voltage: Decimal, flags: list[str])`, `parse_device(name) -> Device(prefixes, kind, voltage, properties)`, `check_tree(root: Path) -> list[str]` (errors, empty when clean); the parsers raise `NamingError`. Grammar from spec 6 and the naming document: library `<process>_<source>_<type>[_<name>]`, process ∈ the variant names, source ∈ {`fd`, `osu`, `gf`, `ef`}, type ∈ {`pr`, `sc`, `io`, `bd`, `xx`, `ip`}, name has no underscore and does not start with a digit; cell `<library>__<cell>[_<size>]`; corner `<tt|ss|ff|sf|fs>_<n?ddd>C_<d>v<dd>[_<flags>]` (`tt_025C_5v00`, `ss_125C_4v50`, `ff_n40C_5v50`; the flag `_stat` allowed); voltage tokens `5v0` in library names, `5v00` in corners; device `[esd_][rf_]<nfet|pfet|diode_<a>2<c>|res_<x>|cap_<x>|npn|pnp>_<dd>v<d>[_<prop>]`.

- [ ] **Step 1: Tests** from spec 6.2: `ws180g005_fd_pr`, `ws180g005_fd_sc_gp9t5v0`, `ws180g005_fd_io`, `ws180g035_fd_sc_ls` parse; `ws180g005_fd_sc_gp_9t` (underscore in name) and `abc123_osu_sc_7t` (process unknown) and `ws180g005_fd_sc_7t` (name starts with a digit) raise; `ws180g005_fd_sc_gp9t5v0__nand2_1` parses with size 1; corners `tt_025C_5v00`, `ss_125C_4v50`, `ff_n40C_5v50`, `tt_025C_5v00_stat` parse, `typ_1p20V_25C` raises; devices `nfet_05v0`, `diode_pw2nd_05v0`, `res_generic_po`, `npn_05v0`, `nfet_05v0_dnw` parse, `nfet5v` raises; `check_tree` on a temp tree with one bad directory name returns one error.
- [ ] **Step 2–4**, **Step 5: Commit** `feat(build): naming checker`.

### Task 20: Private-data checker and git hooks

**Files:**
- Create: `build/src/ws180g_build/private_check.py`; console script `ws180g-check-private`; `tools/git-hooks/pre-commit`, `tools/install-hooks`
- Test: `tests/build/test_private_check.py`

**Interfaces:**
- Produces: `check_private(repo_root) -> list[Finding]` (`path, line, reason`) which (1) loads the evidence set and fails on any entry whose `source` is unregistered or whose source has no `url` or `public != true`; (2) fails on any process field whose `provenance` is not in the allowed set or whose `evidence` ids do not exist in the evidence set; (3) scans every tracked text file outside `tmp/` for the markers `provenance = "private"`, `NDA`, `confidential`, `proprietary`, `internal use only` (case-insensitive, with an allow-list file `build/private-allow.txt` of path:line entries for the spec's own sentences about NDA); (4) recomputes the sha256 of every vendored file against the registry. The pre-commit hook runs `uv run ws180g-check-private` and `uv run ws180g-check-names` on the index; `tools/install-hooks` symlinks it.

- [ ] **Step 1: Tests**: a temp repo copy with an entry of source `secret-deck` → one finding naming the entry; a process field citing `gf180mcu-drm/NOPE.1` → finding; a file containing "CONFIDENTIAL" → finding with line number; the real repository → no findings; the allow-list suppresses exactly the listed line.
- [ ] **Step 2–4**, **Step 5: Commit** `feat(build): private-data checker and pre-commit hook`.

### Task 21: Build command, generated manual, release tree and docs

**Files:**
- Create: `build/src/ws180g_build/main.py` (console script `ws180g-build`), `tree.py`; `rules/src/ws180g_rules/manual.py`; `docs/conf.py`, `docs/index.md`, `docs/rules.md` (includes `generated/rules.md`), `docs/evidence.md` (includes `generated/evidence-report.md`)
- Modify: `.github/workflows/ci.yml` (add `uv run ws180g-build --no-container` and the two checkers)
- Test: `tests/build/test_main.py`, `tests/rules/test_manual.py`

**Interfaces:**
- `ws180g-build [--variant ws180g005] [--out out/] [--no-container]`: load process → evidence report (fails the build if not ok) → rule table → KLayout deck → Magic tech → KLayout tech files → fixtures → manual → (unless `--no-container`) KLayout and Magic fixture runs and the GF180MCU retarget check, with the DRC cache → `tree.assemble(out/ws180g005)` producing `libs.tech/klayout/{ws180g005.lyp,ws180g005.lyt,ws180g005.map,drc/ws180g005.drc}`, `libs.tech/magic/{ws180g005.tech,ws180g005.magicrc}`, `docs/` (the generated pages) → naming and private checks → `out/build-manifest.json` (every output with sha256, the image digest, the git commit). Two runs on the same inputs give byte-identical outputs (no timestamps).
- `write_manual(table, report, out_path)`: Markdown, one section per layer, one row per rule with id, text, value, evidence ids, margin achieved, engines, condition; a final section listing the uncovered public rules.

- [ ] **Step 1: Tests**: `ws180g-build --no-container` exits 0 and creates the tree above; running it twice gives identical manifests; the manual contains a row for `nw.w` with `1.44` and `gf180mcu-drm/NW.1a/5v`; the manual's uncovered section lists `PL.8`; `sphinx-build -W docs out/docs` succeeds (dev dependency group `docs`: sphinx, myst-parser, furo).
- [ ] **Step 2–4**, **Step 5: Commit** `feat(build): one-command build, generated manual and the libs.tech tree`.

### Task 22: Library repositories and submodules

**Files:**
- Create: GitHub repositories `wafer-space-robot/ws180g005_fd_pr` and `wafer-space-robot/ws180g005_fd_io` (public, Apache-2.0, README naming the library, the meta-repository and the rule that the content is generated by the build); `.gitmodules` with HTTPS URLs; `libraries/ws180g005_fd_pr`, `libraries/ws180g005_fd_io`; `libraries/README.md` (explains that `ws180g005_fd_sc_gp<N>t5v0` is created in Phase 1 once the track count `N` exists)
- Test: `tests/test_submodules.py`

**Interfaces:**
- Repository settings identical to the meta-repository (the snapshot in `tmp/repo-settings/` of this checkout, applied with the same commands as `tmp/recreate_repo.py`): issues on, wiki/projects/discussions off, merge commits only, delete branch on merge, secret scanning and push protection, `main` protection (pull request required, admins enforced, no force push or deletion), the tag ruleset `Enforce vXX.ZZZ version tags`. The naming checker (Task 19) must accept both names.

- [ ] **Step 1: Test**: `.gitmodules` lists exactly the two paths with `https://github.com/wafer-space-robot/<name>.git`; each path parses with `parse_library`.
- [ ] **Step 2–4**: create the repositories with `gh repo create` and the settings script; `git submodule add`; PASS.
- [ ] **Step 5: Commit** `feat: library repositories ws180g005_fd_pr and ws180g005_fd_io as submodules`.

### Task 23: Phase 0 gate report

**Files:**
- Create: `docs/phase-0-report.md`
- Modify: `README.md` (status line, how to build, how to run the container tests)

**Interfaces:**
- The report states the three gate checks of spec section 10 with evidence: (1) `uv run pytest tests/rules/test_klayout_fixtures.py tests/rules/test_magic_fixtures.py tests/rules/test_engines_agree.py -rs -v` summary line (counts of passed and skipped, with every skip's reason being `KLayout-only`); (2) `tests/precheck/test_fixture_retarget.py` summary for both `metal_top` values; (3) `out/ws180g005/docs/evidence-report.md` summary (rows ok, rows under-margin = 0, uncovered public rules listed); plus the image digest, the git commit, the retarget log, the open items (ONC18 transcription, density/antenna/fill in Phase 1, deep-n-well ring topology, the single-source margin 1.5 for review, the standard-cell library repository), and the full command sequence a third party runs to reproduce.

- [ ] **Step 1**: run the full build with the container on the build host (`build/sandbox-run` caps: `--mem 4g --cpus 2` per job, at most two jobs at once, so the host's other work keeps its share), save the logs under `out/logs/`.
- [ ] **Step 2**: write the report from the logs (no number in the report that is not in a log).
- [ ] **Step 3: Commit** `docs: Phase 0 gate report`.

---

## Decisions this plan makes (for the owner's review; none blocks execution)

1. GDS numbering of the shared vocabulary table (spec: "assigned in Phase 0 and then fixed").
2. Single-source margin `1.5` (spec 3.6 asks for "a larger chosen margin with its reason").
3. One n-well space rule (2.16 µm) for any potential; the equipotential relaxation is a later rule.
4. SCMOS evidence counts both the SUBM (λ = 0.10) and DEEP (λ = 0.09) mappings of SCN6M; the envelope takes the larger.
5. SCMOS section 10 (overglass) and rules marked guideline in the GF180MCU tables are informative, never binding.
6. Fixtures and generated layers use the KLayout Python module; gdsfactory enters with the cell generators in Phase 1.
7. Density, antenna, fill, seal ring and slot generation move to Phase 1 with the precheck and fuzz loop; the GF180MCU retarget check excludes the `density`, `dummy` and `antenna` decks of the public deck for that reason.
8. The Phase 0 Magic tech is DRC-only (one type per layer); extraction types come with LVS in Phase 1.
9. The container image is built on the public, pinned gf180-tcad base image rather than directly on IIC-OSIC-TOOLS.
10. CI runs the host-side tests only; container tests run on this host before each merge and their output is quoted in the PR.
11. The standard-cell library repository is created in Phase 1, when its track count exists.
12. The onsemi ONC18 data sheet needs a person to download it (automated download is refused by the site).
