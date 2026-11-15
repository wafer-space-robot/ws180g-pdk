<!-- SPDX-License-Identifier: Apache-2.0 -->
# Phase 1 (`ws180g005`) roadmap

**Status:** proposed on 2026-11-16, awaiting the owner's review. Nothing in this document is
approved for execution. It is not an implementation plan: it splits Phase 1 into plans, orders
them and lists the decisions each one needs. Each plan below gets its own plan document
(`docs/superpowers/plans/`), reviewed by the owner before it runs. "Proposal" below means a
choice made by the roadmap's author (the campaign's Claude session) that the owner has not
seen.

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

First silicon means the tiles "submitted to a wafer.space GF180MCU run and accepted by that
run's precheck" (spec section 10).

## Why several plans

Phase 0 was one plan of 23 tasks. Phase 1 adds the components Phase 0 did not touch
(measurements, TCAD, models, devices, cells, IO, flows) and extends the others. They are
separate subsystems with their own tests; one plan per subsystem keeps each plan reviewable
and lets each end with working, tested software on `main`.

## The plans

Size is relative to Phase 0 (= L): S about a third, M about two thirds, XL clearly larger.

| Plan | Scope | Spec component | Needs | Size |
|---|---|---|---|---|
| **1A Rule completion** | Density, antenna, latch-up, ESD and seal-ring rules (the weakly bounded groups of spec section 5.5) and slot rules, with fixtures in both engines where Magic can express them; fill, seal-ring, slot and planarisation-aid generation in `layergen`; the deep-n-well ring topology; the interaction tests of spec section 9 layer 2 (density with fill, antenna with diodes, latch-up with guard rings and taps; the fourth, oxide markers with adjacent active, does not apply until a variant has an oxide marker, in Phase 2); the Phase 0 open rule items (nd/pd overlap, `cite` field for value-less rules, v4 cluster-joining gap); the retarget check run against the **complete** GF180MCU deck, with the `dnw` fixtures re-admitted. The density and dummy decks need a filled die, so 1A runs them on filled fixture tiles (a fixture placed in a die-sized frame and filled by `layergen`); the plan decides the tile size | 6, 7, 13 (part) | Phase 0 | M |
| **1B Fuzz loop** | Random and edge-biased layouts built with gdsfactory (spec section 9, layer 3), filtered by the generic decks, retargeted, run through the GF180MCU deck; every GF180MCU failure on a generic-clean layout becomes a permanent regression fixture; stress layouts (density, minimum-pitch arrays, via arrays, antenna); the 45° select case left open by Phase 0. Part 1 runs on rules alone; part 2 adds random device parameters once 1F exists; part 3 adds cell tilings and abutment rows once 1G exists | 14 (layer 3) | 1A; parts 2 and 3 need 1F and 1G | M |
| **1C Measurements, electrical evidence and stack values** | `measurements/`: per-report model cards and the long-format parameter table parsed from the public MOSIS wafer-acceptance reports, each stored with the report's public URL so a third party can regenerate it from the reports alone; the GF180MCU foundry IV/CV data published in `gf180mcu_fd_pr`. Electrical ranges in the process description with evidence entries and a margin-report section. Replacement of the Phase 0 `chosen` placeholders (metal thicknesses other than `mtop`, dielectric, overlay and implant-doping values; Phase 0 plan decision 14) with evidence-backed ranges. The MOSIS reports cover 1.8 V and 3.3 V devices; the plan states which 5 V quantities they can bound (interconnect, resistors, capacitances) and which rest on GF180MCU data alone | 1, 2, 3 | Phase 0 | M |
| **1D Models** | TCAD of the virtual process (reusing the public `mithro/gf180-tcad`), validated end to end on GF180MCU's public 5 V cards first (spec risk 3), then calibrated against the 1C measurements; BSIM4 fits with typical and envelope corners, temperature and mismatch, in ngspice and Xyce; resistor, capacitor, diode, bipolar and ESD-device models; fit reports against TCAD and against measurements with the three-level verdict; the model checks of spec section 9 layer 5. Optionally preceded by **development cards** (see "Development cards" below) | 4, 5 | 1C; the tcad campaign's infrastructure | XL |
| **1E LVS and extraction** | KLayout LVS deck and netgen set-up from the rule table and the device definitions; Magic extraction; OpenRCX capacitance tables computed from the stack ranges of 1C; LVS fixtures per device in both tools | 8 (Phase 1 part) | 1F (device definitions), 1C (stack), model names from 1D | M |
| **1F Primitive devices** (`ws180g005_fd_pr`) | gdsfactory generators for every modelled device, ESD devices included; fixed-parameter GDS for the characterised sizes; KLayout PCells without a gdsfactory dependency; Xschem symbols; LVS device definitions; the library repository filled by the build | 9 | 1A, model names from 1D | M |
| **1G Standard cells** (`ws180g005_fd_sc_gp<N>t5v0`) | Cell architecture and track count `N` (spec risk 7); the generator; the cell list, including the latches and tri-state buffers that the two-phase SERV SoC and the cell-based memory need; layout, LEF, CDL, Verilog; characterisation to Liberty with an open characteriser, with Liberty sanity checks; LVS of every cell in netgen and KLayout; abutment tests; the library repository | 10 | 1E, 1F; for characterisation, development cards (decision 5) or the 1D cards | L |
| **1H IO** (`ws180g005_fd_io`) | 5 V pad cells built from the 1F ESD devices, clamps, pad-frame pieces, `mtop` drawn to the thick-top-metal rules; LVS in both tools | 11 | 1E, 1F | L |
| **1I Flows** | LibreLane and OpenROAD platform configuration; example designs clean in DRC and LVS in both engines; the SERV test SoC with two-phase clocking | 12 | 1G, 1H | M |
| **1J Precheck, release and docs** | Part 1: the public precheck tool (generic DRC in both engines, LVS, antenna, density, then a foundry mapping), with the mapping behind a public interface whose first implementation is the public GF180MCU mapping (spec component 13; the private mapping repository itself is not Phase 1 work); a private-content check on what the build commits to the library repositories. Part 2, once 1G to 1I exist: the open_pdks-style tree with `libs.ref`; the release asset and ciel installability; the SCMOS compatibility page with the λ tool, the cut-replacement step and the per-λ DRC proof for `λ_5v0` (spec section 3.7); the docs site | 13, 15 | part 1: 1A, 1E; part 2: 1G, 1H, 1I | M |
| **1K First-silicon tiles** | The four tiles of spec section 10: process characterisation, IP characterisation, memory characterisation (with the cell-based memory generator), the SERV SoC; each through precheck and retarget; ring-oscillator simulations compared with the MOSIS and GF180MCU public values | 14 (layers 5, 6) | everything above, with the TCAD-fitted cards of 1D | L |

Upward compatibility (spec section 9, layer 4) has no larger variant to run against in
Phase 1. Proposal: 1J part 1 builds the precheck so that a variant chain can be checked, and
the check first runs in Phase 2, whose gate is "All `ws180g005` tests pass unchanged under
`ws180g105`".

## Order

```text
wave 1   1A rule completion          1C measurements and stack values
wave 2   1B part 1 (rules)           1D starts (long-running; continues behind waves 3 to 5)
wave 3   1F devices, then 1E LVS and extraction, then 1B part 2
wave 4   1G standard cells           1H IO              1J part 1
wave 5   1I flows, then 1J part 2    1B part 3
wave 6   1D cards final, cells re-characterised by the build, then 1K tiles
```

Items on one line separated by spaces are independent; "then" marks a dependency inside a
wave. Waves 4 and 5 assume development cards (decision 5); if that is refused, the
characterisation part of 1G, and 1I, move behind 1D. Reasons for this order:

- **1A first.** The Phase 0 report lists three deviations from the gate wording. 1A removes
  two of them (the GF180MCU deck run without its density, dummy and antenna decks; the `dnw`
  fixtures excluded). The third stays: its KLayout-only rules are allowed by the spec
  (section 9, layer 2), and its recorded marker exceptions need the owner's agreement
  (decision 1). Every later layout is then checked against the complete deck
  from the start, so cells are not drawn to rules that later move.
- **1C beside it.** TCAD needs doping and stack values, extraction needs dielectric and metal
  ranges, and the ring-oscillator gate needs the public values to bracket.
- **Fuzz loop early.** It is the only empirical test of the claim that a generic-clean layout
  passes the target deck. Run on rules alone it finds rule defects before cells are built on
  them.
- **1D is the long pole.** When the spec was written (2026-10-26) the reused TCAD work had
  not yet produced a MOSFET I-V or a BSIM card (risk 3), and 2D sweeps cost hours each
  (risk 4). The 1D plan starts by checking the current state of that work.

## Development cards (a proposed deviation from the spec)

Devices and LVS (1E, 1F) need only model names and terminals. Cell characterisation,
simulation and flow timing (1G, 1I) need usable cards before 1D can deliver fitted ones.
Proposal: until then the build uses **development cards**: the public GF180MCU 5 V model
cards, unchanged except for the model names.

This deviates from the spec and needs the owner's agreement:

- Spec section 3.6 says no generator reads the evidence set except TCAD calibration, "never
  for a rule or a model value"; component 5 (models) reads only TCAD and measurements. The
  GF180MCU cards are evidence. Development cards therefore are not a product of the models
  component and must never be one.
- To keep the deviation contained: development cards are fetched from the public PDK at a
  pinned commit by a development-only build step; neither they nor anything derived from
  them (Liberty files, characterisation reports, simulation results) are written to a
  library repository, the release tree or a release asset; the build refuses to make a release while
  any card is a development card; the ring-oscillator gate and the tiles of 1K use only the
  TCAD-fitted cards of 1D (a comparison of GF180MCU-derived cards with GF180MCU values would
  prove nothing).
- The alternative, without a deviation: characterisation and flows wait for 1D. Layout
  generation, DRC and LVS work can still proceed.

## How the Phase 1 gate maps to the plans

| Gate clause | Proven by |
|---|---|
| Example designs clean in both engines | 1I |
| Retargeted GDS passes the public GF180MCU deck | 1A (fixtures, complete deck), 1B (fuzz layouts), 1I and 1K (designs and tiles) |
| Ring-oscillator simulations bracket the MOSIS and GF180MCU public values | 1C (the public values), 1D (TCAD-fitted cards), 1K (the simulations) |
| The four tiles are submitted to a wafer.space GF180MCU run and accepted by its precheck | 1K; the submission itself is the owner's action |

## Decisions needed from the owner

Before 1A:

1. The three deviations in `docs/phase-0-report.md` and the Phase 0 plan's decision list (in
   particular the single-source margin 1.5 and the 800 µm `mtop.w.long` threshold), since 1A
   builds on them.
2. Appendix A of the spec as a whole (appendix B item 1). Phase 1 rests on items 3 (margin
   rule for maxima and density floors), 14 (sampling, BSIM4, both simulators), 16 (CharLib),
   17 (private mapping interface), 19 (`libs.tech` layout), 21 (verification layers), 22
   (phases and gates) and 23 (derived-library source tags).
3. Whether the 5 V partner foundries are picked before 1A (spec risk 2): their public rule
   sources, if any, would enter the evidence set and could move the envelope.

Before 1C:

4. How the parsed MOSIS data enters the repository. Spec component 3 requires each parsed
   output beside its public report URL, regenerable from the reports alone. Proposal: the
   repository holds the parser and the parsed outputs, fetched from the public archive URLs;
   nothing that does not come from a public report is imported.

Before 1D:

5. Development cards as proposed above, or cell characterisation and flows wait for 1D.
6. The BSIM extraction flow (spec risk 8). The spec prefers an existing open flow over
   writing one (section 11.1), and DMT-core is GPL-3. Proposal: the 1D plan starts with a
   survey of open extraction flows and their licences and brings the choice to the owner; a
   least-squares fit over ngspice written in this repository is the fallback.
7. Compute for TCAD on the shared host, and whether TCAD is run by this campaign or requested
   from the gf180-tcad campaign against the ws180g process description.

Before 1G and 1H:

8. Creating the public repository `ws180g005_fd_sc_gp<N>t5v0` once `N` is known (the Phase 0
   go-ahead covered only the two existing library repositories).
9. The characteriser (appendix A item 16: CharLib as the candidate), after the same licence
   check as decision 6.
10. The ESD approach for 1F and 1H. Only public sources may be used. Proposal: the device
    types and clamp topology of the Apache-2.0 `gf180mcu_fd_io` library, cited by file and
    commit with attribution, redrawn to the generic rules. Only the topology carries over
    (the Phase 0 report records that those cells do not pass the thick-top-metal rules), and
    ESD performance is unproven until silicon.

Before 1J and 1K:

11. ciel installability (spec section 7, component 15): a change to ciel, or a release layout
    that matches what ciel already fetches.
12. Upward-compatibility checks first run in Phase 2, as proposed above.
13. The wafer.space GF180MCU run the tiles aim for, and its date: under the proposal above
    the tiles need the TCAD-fitted cards, so the date bounds 1D.

Carried over from Phase 0, not blocking: the ONC18 data sheet, and whether the sandbox CI job
runs on every push.

## What is not in Phase 1

The 1.8 V and 3.3 V variants (Phases 2 and 3), the 3-metal option (Phase 4), the private
mapping repository and further foundry mappings, the MIM module, the SRAM bit cell and
compiler, and the gdsfactory PDK package (spec section 10, "Later").
