<!-- SPDX-License-Identifier: Apache-2.0 -->
# Phase 1 (`ws180g005`) roadmap

**Status:** proposed on 2026-11-16, awaiting the owner's review. Nothing in this document is
approved for execution. It is not an implementation plan: it splits Phase 1 into plans, orders
them and lists the decisions each one needs. Each plan below gets its own plan document
(`docs/superpowers/plans/`), reviewed by the owner before it runs.

**Spec:** `docs/superpowers/specs/2026-10-26-ws180g-pdk-design.md`, section 10 (Phase 1 row),
section 7 (components), section 9 (verification), section 12 (risks).

**Starting point:** Phase 0 as recorded in `docs/phase-0-report.md` (main at `31c5249`).

## What Phase 1 must deliver

From the spec's Phase 1 row:

> TCAD and 5 V models anchored on GF180MCU public cards then MOSIS and GF measured data; LVS
> deck, extraction and netgen setup; `ws180g005_fd_pr`; `ws180g005_fd_sc_*`; `ws180g005_fd_io`;
> LibreLane flow; full precheck with the GF180MCU mapping; fuzz loop against the GF180MCU deck;
> SCMOS compatibility page with `λ_5v0` (section 3.7); ciel installability; first silicon

Gate:

> Example designs clean in both engines; retargeted GDS passes the public GF180MCU deck;
> ring-oscillator simulations bracket the MOSIS and GF180MCU public values; the four tiles
> below are submitted to a wafer.space GF180MCU run.

## Why several plans

Phase 0 was one plan of 23 tasks over six components. Phase 1 covers nine further components
(spec section 7, components 3 to 5 and 8 to 13) that are separate subsystems with their own
tests. One plan per subsystem keeps each plan reviewable and lets each end with working,
tested software on `main`.

## The plans

Size is relative to Phase 0 (= L): S about a third, M about two thirds, XL clearly larger.

| Plan | Scope | Spec component | Needs | Size |
|---|---|---|---|---|
| **1A Rule completion** | Density, antenna, fill, seal-ring and slot rules with fixtures in both engines where Magic can express them; fill and seal-ring generation in `layergen`; the deep-n-well ring topology; the Phase 0 open rule items (nd/pd overlap, `cite` field for value-less rules, v4 cluster-joining gap); the retarget check run against the **complete** GF180MCU deck (density, dummy and antenna decks included) and the `dnw` fixtures re-admitted | 6, 7, 13 (part) | Phase 0 | M |
| **1B Fuzz loop** | Random and edge-biased layouts (spec section 9, layer 3) filtered by the generic decks, retargeted, run through the GF180MCU deck; every GF180MCU failure on a generic-clean layout becomes a permanent regression fixture; stress layouts (density, minimum-pitch arrays, via arrays, antenna) | 14 (layer 3) | 1A for density and antenna; starts on Phase 0 rules; extended when devices (1F) and cells (1G) exist | M |
| **1C Measurements and electrical evidence** | `measurements/`: the parsed public MOSIS wafer-acceptance data (from `mithro/mosis180-pdk`, pinned) and the GF180MCU foundry IV/CV data published in `gf180mcu_fd_pr`; electrical ranges (threshold, drive, sheet resistance, capacitance) entered in the process description with evidence entries and a margin report section | 2, 3 | Phase 0 | S |
| **1D Models** | Stage 1: a 5 V model library whose typical and corner cards are derived from the public GF180MCU cards and bounded by the 1C ranges, in ngspice and Xyce, with the model checks of spec section 9 layer 5. Stage 2: TCAD of the virtual process (reusing `mithro/gf180-tcad`), validated end to end on GF180MCU's public 5 V cards first (risk 3), then BSIM4 fits, corners and mismatch, with fit reports; resistor, capacitor, diode and bipolar models | 4, 5 | 1C; stage 2 also the tcad session's infrastructure | XL (stage 1: S) |
| **1E LVS and extraction** | KLayout LVS deck and netgen set-up from the rule table and the device definitions; Magic extraction; OpenRCX capacitance tables computed from the stack ranges; LVS fixtures per device in both tools | 8 (Phase 1 part) | 1F device definitions (developed together), 1D stage 1 model names | M |
| **1F Primitive devices** (`ws180g005_fd_pr`) | gdsfactory generators for every modelled device; fixed-parameter GDS for the characterised sizes; KLayout PCells without a gdsfactory dependency; Xschem symbols; LVS device definitions; the library repository filled by the build | 9 | 1A (rules final enough), 1D stage 1 | M |
| **1G Standard cells** (`ws180g005_fd_sc_gp<N>t5v0`) | Cell architecture and track count `N` (risk 7); the generator; layout, LEF, CDL, Verilog; characterisation to Liberty with an open characteriser; abutment tests; the library repository | 10 | 1E, 1F, 1D stage 1 | L |
| **1H IO** (`ws180g005_fd_io`) | 5 V pad cells, ESD devices and clamps, pad-frame pieces, `mtop` drawn to the thick-top-metal rules | 11 | 1E, 1F | L |
| **1I Flows** | LibreLane and OpenROAD platform configuration; example designs clean in DRC and LVS in both engines; the SERV test SoC with two-phase clocking | 12 | 1G, 1H | M |
| **1J Precheck, release and docs** | The public precheck tool (generic DRC in both engines, LVS, antenna, density, then the GF180MCU mapping); the open_pdks-style tree with `libs.ref`; the release asset and ciel installability; the SCMOS compatibility page with `λ_5v0`; the docs site; a private-content check on what the build commits to the library repositories | 13, 15 | 1A, 1E; complete once 1G to 1I exist | M |
| **1K First-silicon tiles** | The four tiles of spec section 10: process characterisation, IP characterisation, memory characterisation, the SERV SoC; each through precheck and retarget; ring-oscillator simulations compared with the MOSIS and GF180MCU public values | 14 (layers 5, 6) | everything above | L |

## Order

```text
wave 1   1A rule completion        1C measurements
wave 2   1B fuzz loop (rules)      1D stage 1 models       1D stage 2 TCAD (long-running, in the background of waves 2 to 5)
wave 3   1F devices + 1E LVS/extraction (one after the other, same files)
wave 4   1G standard cells         1H IO                   1J precheck/release (first part)
wave 5   1I flows                  1B fuzz loop (cells)    1J (second part)
wave 6   1K tiles                  1D stage 2 cards replace stage 1 cards; cells re-characterised
```

Plans in one wave do not depend on each other. Reasons for this order:

- **1A first.** It removes the two deviations from the Phase 0 gate wording (the GF180MCU deck
  run without its density, dummy and antenna decks; the `dnw` fixtures excluded). Every later
  layout is checked against the complete deck from the start, so cells are not drawn to rules
  that later move.
- **Models in two stages.** No device simulation in the reused TCAD work has yet produced a
  MOSFET I-V or a BSIM card (risk 3), and 2D sweeps cost hours each (risk 4). Devices, LVS,
  cells and flows need only model names, terminals and plausible cards to proceed. Stage 1
  gives them cards with public provenance now; stage 2 replaces the cards without changing
  names, and the cells are re-characterised by the build. If stage 2 slips, it does not block
  layout work.
- **Fuzz loop early.** It is the only empirical test of the claim that a generic-clean layout
  passes the target deck. Run on rules alone it finds rule defects before cells are built on
  them.

## How the Phase 1 gate maps to the plans

| Gate clause | Proven by |
|---|---|
| Example designs clean in both engines | 1I |
| Retargeted GDS passes the public GF180MCU deck | 1A (fixtures, complete deck), 1B (fuzz layouts), 1I and 1K (designs and tiles) |
| Ring-oscillator simulations bracket the MOSIS and GF180MCU public values | 1C (the public values), 1D (cards), 1K (the simulations) |
| The four tiles are submitted to a wafer.space GF180MCU run | 1K; the submission itself is the owner's action |

## Decisions needed from the owner

Before 1A:

1. The deviations and decisions recorded in `docs/phase-0-report.md` and the Phase 0 plan's
   decision list (in particular the single-source margin 1.5 and the 800 µm `mtop.w.long`
   threshold), since 1A builds on them.
2. Whether density, fill and seal-ring values follow the same margin rule over the public
   sources as the Phase 0 rules (the author's assumption: yes, spec section 3.6 names density
   floors explicitly).

Before 1D:

3. Two-stage models as proposed, or wait for TCAD-derived cards before any cell work.
4. The BSIM extraction flow (risk 8): DMT-core is GPL-3; the alternative is the repository's
   own least-squares fit over ngspice. The author's proposal: own fit, no GPL dependency.
5. Compute for TCAD on the shared host, and whether stage 2 is run by this campaign or
   requested from the gf180-tcad campaign against the ws180g process description.

Before 1G and 1H:

6. Creating the public repository `ws180g005_fd_sc_gp<N>t5v0` once `N` is known (the Phase 0
   go-ahead covered only the two existing library repositories).
7. The characteriser (appendix A item 16: CharLib as the candidate).
8. The ESD approach for 1H. Only public sources may be used; the author's proposal is the
   device types and topology documented for the Apache-2.0 `gf180mcu_fd_io` library, redrawn
   to the generic rules, with the limitation that ESD performance is unproven until silicon.

Before 1J and 1K:

9. ciel installability (spec section 7, component 15): a change to ciel, or a release layout
   that matches what ciel already fetches.
10. The wafer.space GF180MCU run the tiles aim for, and its date, because it fixes how much of
    stage 2 of 1D can be in the tiles.

Carried over from Phase 0, not blocking: the ONC18 data sheet, and whether the sandbox CI job
runs on every push.

## What is not in Phase 1

The 1.8 V and 3.3 V variants (Phases 2 and 3), the 3-metal option (Phase 4), the MIM module,
the SRAM bit cell and compiler, further foundry mappings and the gdsfactory PDK package (spec
section 10, "Later").
