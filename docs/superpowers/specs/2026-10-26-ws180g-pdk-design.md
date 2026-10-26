# wafer.space 180 nm generic PDK (ws180g): design document

- **Date:** 2026-10-26
- **Status:** reviewed; the owner's decisions of 2026-10-26 and 2026-10-27 applied
- **Owner:** Tim 'mithro' Ansell (wafer.space)
- **Licence of this repository:** Apache-2.0

This document is the high-level plan for `ws180g`, a generic, conservative
180 nm process design kit (PDK) whose aim is to let one design be manufactured
at as many 180 nm foundries as possible. It records the decisions taken on
2026-10-26, the pieces that have to be built, what each piece does, how they
fit together, and the order of work. It is the input to the implementation
plans that follow it.

Every number in this document is either a design decision (marked as such) or
comes from a public source named beside it. Nothing here comes from a
foundry document under non-disclosure agreement (NDA). See section 13.

---

## 1. Purpose and priorities

wafer.space runs low-volume, real production shuttles. `ws180g` exists so that
a customer can design once and have that design manufactured at several
foundries, and so that wafer.space can move a run between foundries on cost
and availability rather than on whether the design happens to fit.

Priorities. The owner named the first two together as "the highest priority";
the ordering between them below is the author's proposal (appendix A).

1. **Manufacturable at as many 180 nm foundries as possible.** The PDK is a
   lowest common denominator, chosen conservatively.
2. **Lowest mask count and lowest cost for a mask set plus a first lot of
   about 50 wafers.** Every mask layer has to justify itself.
3. **Everything regenerable from data.** The PDK is the output of a pipeline
   fed by one process description, open TCAD and public measured data. Nothing
   in the released PDK is hand-edited.
4. **Nothing private.** The repository holds only public facts, each with a
   citation. See section 13.

Performance, power and area (PPA) are explicitly **not** optimisation targets.
A design that is twice the area of its single-foundry equivalent but can be
made in three places is the intended outcome, not a failure.

**The central invariant (owner's requirement).** There must be no case where a
design passes the generic DRC rules and fails the foundry's DRC after
retargeting, for every supported target. Section 9 is how that claim is
tested; section 12.1 records how far it is proven at any time and the working
assumption for private-deck failures.

## 2. Scope and non-goals

**In scope.** Gate oxides for 5 V, 3.3 V and 1.8 V devices; a 5 metal
aluminium back end with a thick top metal; digital standard cells; IO; the
primitives a 5 V analog designer needs; design rules and DRC decks for KLayout
and Magic; LVS and parasitic extraction; SPICE models for ngspice and Xyce; a
LibreLane and OpenROAD flow; a public precheck that retargets a design to a
specific foundry; a verification suite; documentation; test chips.

**Not in scope for the first releases.** Metal-insulator-metal (MIM)
capacitors (a later optional module); more than five metals; copper back ends;
RF models; SOI; BCD and high-voltage devices beyond the 5 V oxide; SRAM macro
compilers (a DFFRAM-style cell-based memory is in scope, a bit-cell compiler
is later); a gdsfactory-based PDK package (later, section 8.3).

## 3. Principles

### 3.1 One virtual process, in real units

A single versioned, declarative description of a fictional, conservative
180 nm process is the only source of truth. All lengths are in micrometres and
all physical quantities are in SI units. There is no lambda. It describes:

- the layer stack and materials (substrate, wells, active, poly, contacts,
  metals, vias, passivation);
- three gate oxides (5 V, 3.3 V, 1.8 V) with thickness and threshold targets;
- implants and their doping targets;
- lithography and overlay capability per layer (minimum feature, minimum
  space, registration);
- supply domains;
- the mask list, with each mask marked baseline or optional module;
- the variant chain (section 4).

Every derived artifact (a rule, a model parameter, a tech-file entry, a cell)
traces back to named fields of this description. No other source file in the
repository may define a virtual-process value; the evidence set, the
measurements and the generated outputs hold numbers, but never define one.

### 3.2 Every parameter is a range, not a number

The targets are many foundries with different equipment and recipes. So each
physical quantity (oxide thickness, doping, metal and dielectric thickness,
sheet resistance, critical-dimension bias, overlay) is specified as a minimum,
nominal and maximum, with a distribution where one is known. The ranges are
chosen to cover the span of real foundries' values with margin.

Consequences:

- TCAD samples the range space, models are fitted across it, and corners are
  derived as the envelope of the sampled population. Fast and slow corners are
  therefore wider than any one foundry's three-sigma, by design.
- The top-metal thickness is a range: **minimum 9 kÅ minus a margin, maximum
  30 kÅ plus a margin** (owner's decision, 2026-10-26: "min value of the
  9k-extra and a max value of the 30k+extra"). Designs must work at any value
  in that range. The margin is the 20 % of section 3.6 unless the process
  description records a different value with its reason. The GF180MCU design
  rule manual lists top-metal options TM6K, TM9K, TM11K and TM30K
  (`05_Current_0.18_MCU_9.csv`); the owner chose 9 kÅ as the lower anchor and
  ruled on 2026-10-27 that the 6 kÅ option is not available and is to be
  ignored, so the range does not reach down to it and nothing in the PDK
  targets it.
- Corners are **foundry-population corners**: the fast and slow corner cards
  are fitted to the extremes of the sampled range population, so they bound
  every foundry the ranges cover, not one foundry's statistical spread.
  Mismatch and Monte Carlo parameters are a separate, smaller quantity layered
  on top of them.

### 3.3 Drawn layers versus generated masks

The designer draws only layers that carry design intent; the full list is the
drawn-layer table in section 5.1. Every mask the PDK can derive is generated
by the PDK: select and implant masks, well masks a target needs beyond the
drawn n-well, oxide masks, dummy fill, seal ring, slotting, and any
foundry-specific helper layer. DRC and LVS run on the drawn set plus the
generated set. A designer never hand-draws a generated layer.

Contacts and vias are drawn at one nominal size on the generic layers.
Real processes specify cuts as an exact size: 0.22 µm contacts (CO.1,
`21_Contact_56.csv`) and 0.26 µm vias (Vn.1, `23_Vian_59.csv`) in the GF180MCU
design rule manual (DRM), 0.18 µm contacts under SCMOS rev 8 (2λ at
λ = 0.09 µm), 0.36 µm top vias on X-FAB XC018 (data sheet, "Basic Design
Rules"). So the retarget step
regenerates every cut at the target's exact size, centred on the drawn cut,
and the 20 % margin rule of section 3.6 does not apply to cut sizes. The
nominal generic cut size per layer is the largest public exact size: `co`
0.22 µm (GF180MCU and XC018; SCMOS DEEP's 2λ contact is 0.18 µm), `v1` to
`v3` 0.27 µm (SCMOS DEEP's 3λ via, rules 8.1, 14.1 and 21.1, above the
0.26 µm of GF180MCU and XC018), and `v4` (the via onto `mtop`) 0.36 µm; every
enclosure and spacing rule around a cut is computed so that both the largest
and the smallest public target cut fit after the resize; a resize whose size
change is an odd number of grid steps must snap the cut so its vertices stay
on the target grid. The public cut sizes this rests on are the ones cited
above.

### 3.4 Oxide modularity and nested variants

A design using only the 5 V oxide has no dependency on the 1.8 V or 3.3 V
layers existing. The absence of any oxide marker means the base 5 V oxide.
Adding an oxide adds layers, rules, models and cells; it never changes the
meaning of an existing layer, rule, device or cell. Section 4 defines the
variants this produces.

### 3.5 Mask minimisation

The process description tracks each mask with a justification. The baseline
mask set is the fewest masks a usable 5 V digital and analog flow needs.
Everything else is an optional module with its own marker layer, rules, and
device variants, defined from day one. A design that uses a module stays
upward compatible, but can only be made at targets that offer that module.
Section 5.3 lists the baseline and the modules.

### 3.6 Public-facts evidence set

Separate from the virtual process, the repository keeps a cited collection of
public facts about real 180 nm processes: the MOSIS wafer-acceptance reports,
the GF180MCU open PDK, foundry and broker brochures, data sheets and papers.
How the evidence and the virtual process relate (one model, used everywhere
in this document):

1. The author of the virtual process sets each value **by hand, using the
   evidence**: for a minimum, the largest public minimum found times the
   margin; for a maximum, the smallest public maximum divided by the margin.
   The process-description field records the value, the evidence entries it
   was set from, and the margin achieved. That is the owner's rule "find the
   largest possible value and then choose a minimum size 20 % larger".
2. **The pipeline reads only the process description.** Rules, tech files,
   cells and models come from the description's fields; no generator reads
   the evidence set, with the one exception in point 4.
3. **The evidence report checks the description against the evidence** on
   every build and fails if any value no longer carries the margin over the
   public data, or if a value cites an evidence entry that does not exist.
4. The evidence also supplies **TCAD calibration targets** (section 7,
   component 4): the one generator that reads the evidence set, and only for
   calibration, never for a rule or a model value.

The margin rule (design decision): for a minimum width, space, enclosure or
extension, the virtual process value is at least 20 % larger than the largest
public minimum found; for a maximum (tap distance, density ceiling) at least
20 % smaller than the smallest public maximum; for a minimum-density floor at
least 20 % larger than the largest public floor. A value may carry a larger
margin when the process description records the reason. Cut sizes are exempt
(section 3.3). Where no public value exists the value is marked "chosen" with
its reasoning.

### 3.7 Legacy lambda-rule compatibility

The PDK is absolute-unit. A documented, tested example page shows which
lambda value makes existing MOSIS SCMOS lambda-rule assets legal on this
process, with the DRC run included as proof, so that the large body of
SCMOS-era cells, teaching kits and tools can be used.

The lambda is **derived, not assumed**: the rules tool computes, for a named
SCMOS rule set (rev 8.00, SUBM or DEEP column, stated on the page), the
smallest λ for which every SCMOS rule scaled by λ satisfies every ws180g rule
of the variant. It will be far larger than MOSIS's 0.09 or 0.10 µm for TSMC
0.18 (SCMOS tables 2b and 2c), because every ws180g minimum carries the
section 3.6 margin over the public values that include SCMOS itself, and
because the SCMOS gate is the 2λ poly minimum width (SCMOS rule 3.1), so λ
can never be less than half the minimum gate length of the oxide the
transistor is built in.

**One lambda per oxide** (the owner's requirement, 2026-10-26): the tool
computes and the page publishes a separate λ for each gate-oxide class,
`λ_5v0`, `λ_3v3` and `λ_1v8`, because the minimum gate length differs per
oxide and so does the smallest legal scaling. A lambda-rule asset is drawn for
one class; it is placed under that class's oxide marker (section 5.4) and
scaled by that class's λ. Each variant publishes the lambdas of the oxides it
contains: `ws180g005` only `λ_5v0`, `ws180g035` adds `λ_3v3`, `ws180g105`
adds `λ_1v8`, `ws180g135` all three. The gate-length floor of each, from the
public minimum gate lengths with the 20 % margin applied, is the lower bound
the tool starts from; the other rules (contact and via enclosures, well
spacing) decide the final value and are expected to push the two thinner
oxides higher than their floor:

| Class | Public minimum gate length (source) | Margin applied | Floor on λ (half the gate) |
|---|---|---|---|
| 5 V | 0.60 µm nfet / 0.50 µm pfet (GF180MCU PL.2, `16_Poly2_42.csv`) | 0.72 / 0.60 µm | 0.36 µm; final value expected near it (author's estimate: 0.36 to 0.40 µm) |
| 3.3 V | 0.28 µm (GF180MCU PL.2, `16_Poly2_42.csv`) | 0.336 µm | 0.17 µm |
| 1.8 V | 0.18 µm (SCMOS DEEP 2λ at λ = 0.09 µm; X-FAB XC018 data sheet) | 0.216 µm | 0.11 µm |

SCMOS cuts are 2λ squares and ws180g cuts are exact-size (section 3.3), so
the page also documents the cut step: each lambda cut is replaced by a nominal
generic cut at its centre before DRC. The published values are regenerated by
the build whenever the rule table changes, and the page's DRC proof runs once
per lambda.

### 3.8 Nothing private

See section 13. This principle is enforced by review and by tooling.

## 4. Variants and upward compatibility

### 4.1 The variants

Four variants, all built from the one virtual process:

| Variant     | Oxides             | Notes                                                            |
|-------------|--------------------|------------------------------------------------------------------|
| `ws180g005` | 5 V                | First release. GF180MCU is a required manufacturing target.      |
| `ws180g035` | 3.3 V + 5 V        | GF180MCU is a required manufacturing target.                     |
| `ws180g105` | 1.8 V + 5 V        | Not manufacturable on GF180MCU, which has no 1.8 V oxide.        |
| `ws180g135` | 1.8 V + 3.3 V + 5 V | Not manufacturable on GF180MCU, which has no 1.8 V oxide.       |

There is no `ws180g130` (1.8 V + 3.3 V without 5 V) and none is planned.

Each variant is released as a complete, standalone PDK.

### 4.2 Upward compatibility

A design that is clean on a smaller variant is clean, unchanged, on every
larger variant that contains it: same GDS, same netlist, same DRC and LVS
result, same models and cells by name. The compatibility chains are:

- `ws180g005` into `ws180g035`, `ws180g105` and `ws180g135`;
- `ws180g035` into `ws180g135`;
- `ws180g105` into `ws180g135`.

A larger variant may only add layers, devices, rules on new layers, models and
cells. It may never tighten an existing rule, renumber a layer, or rename a
device, model or cell. The variant chain is declared in the virtual process,
the build produces all variants from one source, and the verification suite
runs every smaller variant's fixtures and example designs through every larger
variant's decks on each build (section 9).

Library names carry the variant in which the library was introduced (section
6). A library named `ws180g005_*` is therefore usable, unchanged, on every
variant; `ws180g035` ships `ws180g005_fd_sc_*` as is and adds its own
`ws180g035_fd_sc_*` for 3.3 V cells and level shifters.

### 4.3 Development order

`ws180g005` first, then the 1.8 V oxide (`ws180g105`), then the 3.3 V oxide
(`ws180g035` and `ws180g135`). This is the owner's order, stated as "1v8 can
be a phase two additions, 3v3 can be a phase three addition" before the
variants were named and confirmed on 2026-10-27 ("Priority remains 5v, 1v8
then 3v3") after the author had proposed the opposite. The consequence the
author raised stands and is planned for: GF180MCU has a 3.3 V oxide and no
1.8 V oxide, so `ws180g105` has no silicon path on the wafer.space GF180MCU
runs and its silicon gate is the first non-GF180MCU target, while the 3.3 V
work in Phase 3 returns to GF180MCU silicon. Section 10 is written for this
order.

## 5. The virtual process

### 5.1 What the description contains

The process description is a set of schema-validated TOML data files (the
format `gf180-tcad` already uses, read with the standard library) loaded by
one library into a typed in-memory model.
Fields, each with `value`/`range`, `unit`, `provenance`, `source` and `note`,
following the pattern already used by `mithro/gf180-tcad` (section 11.1):

- **Substrate and wells.** p-type substrate; one drawn n-well; p-well
  implicit (everything outside n-well). Deep n-well as an optional module.
- **Active, poly, contacts.** Single poly. Nominal contact and via sizes.
- **Gate oxides.** Three, with thickness range, target threshold range,
  minimum gate length per polarity.
- **Implants.** N+, P+, threshold adjusts per oxide, with doping ranges.
- **Back end.** Five aluminium metals: `m1`, `m2`, `m3`, `m4` and `mtop`.
  `mtop` is a distinct layer with its own thickness range (section 3.2) and
  its own coarser rules. Per-metal and per-dielectric thickness ranges,
  resistivity ranges, via sizes.
- **Lithography and overlay capability.** Per layer: minimum feature,
  minimum space, line-end and corner allowances, registration to the layers
  it must align to. These are the inputs the rule derivation reads.
- **Supply domains.** 5 V, 3.3 V, 1.8 V nominal with tolerance.
- **Mask list.** Each mask: name, drawn or generated, baseline or optional
  module, justification.
- **Variants.** The chain of section 4.

**Drawn layers** (the complete set a designer may use; GDS numbers are
assigned in Phase 0 and then fixed):

| Drawn layer | Name | Purpose | Variant or module |
|---|---|---|---|
| n-well | `nw` | the one drawn well; p-well is implicit | baseline |
| n-diffusion | `nd` | n+ active (source/drain, n-well tap) | baseline |
| p-diffusion | `pd` | p+ active (source/drain, substrate tap) | baseline |
| poly | `po` | gates and poly interconnect, resistors | baseline |
| contact | `co` | poly or diffusion to `m1`, nominal size | baseline |
| metals | `m1`, `m2`, `m3`, `m4`, `mtop` | interconnect | baseline (5-metal) |
| vias | `v1`, `v2`, `v3`, `v4` | `m1`..`m4` to the next metal, nominal size; `v4` lands on `mtop` | baseline |
| pad opening | `pad` | passivation opening | baseline |
| silicide block | `sab` | unsilicided poly and diffusion | baseline |
| 3.3 V oxide marker | `ox_3v3` | section 5.4 | `ws180g035`, `ws180g135` |
| 1.8 V oxide marker | `ox_1v8` | section 5.4 | `ws180g105`, `ws180g135` |
| deep n-well | `dnw` | isolated p-well region | deep n-well module |
| high-resistance poly | `rhi` | high-sheet-resistance poly implant | high-resistance poly module |
| device markers | `mk_res`, `mk_cap`, `mk_dio`, `mk_bjt`, `mk_esd` | LVS device recognition | baseline |
| intent markers | `mk_nofill`, `mk_boundary` | fill exclusion, cell boundary | baseline |

Because selects are generated, the designer states the diffusion type by
drawing `nd` or `pd`, as sky130 and gf180mcu designers do with their select
layers; the generator derives the n-select and p-select masks from them, and
infers well taps from `nd` inside `nw` and `pd` outside it.

**Generated layers** (never drawn): n-select and p-select, threshold-adjust
implants per oxide class, the per-target oxide masks, any p-well mask a target
requires, dummy fill on diffusion, poly and every metal, seal ring, metal
slots, planarisation aids, and any foundry helper layer. Each is defined once
in `layergen/` (section 7, component 7) with the drawn layers it derives from.

### 5.2 Grid

The design grid must be conservative like every other value: a layout on a
grid finer than a target's grid is off-grid there. Rule (design decision):
the generic grid is the least common multiple of the publicly known target
grids, and it is a parameter of the process description, not a constant in
any tool. Known today: GF180MCU 0.005 µm (GRID rule in the DRM). The MOSIS
SCMOS rev 8 submission grid of 0.045 µm (SCMOS rules section 7) is a
submission rule of a broker rather than a foundry grid and does not count as
a target constraint (owner, 2026-10-27: "probably don't need to care about
the SCMOS submission grid"). The final value is unknown until more target
grids are public (owner, same date); the document and the first process
description use 0.005 µm provisionally, and the evidence set records each
target grid as it becomes known so the build can recompute the multiple.
Derived values (for example a half-rule halo) and resized cuts (section 3.3)
must stay on the grid.

### 5.3 Baseline mask set and optional modules for `ws180g005`

The baseline below and the choice of silicide block as its only module are
the owner's decisions of 2026-10-26. Defining the other modules now, rather
than later, is the author's proposal (appendix A, item 10).

**Baseline** (every `ws180g005` design may use these without choosing a
foundry option):

- the baseline drawn layers of the section 5.1 table (`nw`, `nd`, `pd`,
  `po`, `co`, `m1`..`m4`, `v1`..`v4`, `mtop`, `pad`, markers) and the
  generated select, implant and well masks;
- the 5 V oxide (the base oxide; no marker needed);
- **silicide block (SAB)**: unsilicided poly and diffusion resistors, ESD
  ballast. One mask; offered by GF180MCU (`19_SAB_52.csv`), by SCMOS rev 8
  (`SILICIDE_BLOCK`, rules section 20) and by X-FAB XC018 (its
  non-salicided resistors in the data sheet);
- top-metal thickness anywhere in the range of section 3.2.

**Optional modules**, defined from day one with marker, rules and devices,
not in the baseline:

- **deep n-well**: isolated NMOS, substrate-noise isolation. Offered as the
  "mixed-signal" option by TSMC via CMC, as the DNWELL mask by GF180MCU, as a
  triple-well module by UMC and X-FAB (sources in section 14);
- **high-resistance poly implant**: about 1 kΩ/sq resistors (the GF180MCU
  `ppolyf_u_1k` device in `gf180mcu_fd_pr`; the X-FAB XC018 HRPOLY module's
  `rpp1k1` at 1000 Ω/sq in the data sheet). Optional at GF180MCU (the "Resistor"
  drawn layer is "High sheet rho P-poly resistor (Optional)" in
  `06_Drawn_layer10.csv`) and at TSMC (the "Hipo resistor", TSMC's name for
  its high-resistance poly resistor option, in the Europractice option
  sheet);
- **MIM capacitor**: later; one flavour at most;
- **3 metal stack option**: the owner requires that a 3-metal option exist
  ("5 metal layers should be the default. 3 metal layer option should
  exist."). It is done after the 3.3 V work has completed (owner,
  2026-10-27), which makes it Phase 4 in section 10. What is deferred until
  then is its rule model, in the owner's words: "Focus on the 5 metal stack
  with top metal being a different config. We *might* explore if whatever is
  top metal on the 3 metal stack should also have top-metal DRC rules (making
  the 5 metal stack effectively adding 1 fine metal and 1 course metal type
  config?). Let's defer that for later." Settled with it, at the start of
  Phase 4: how the upward-compatibility rule of section 4.2 applies between
  metal options, since a 3-metal design is not the same GDS as a 5-metal
  design.

Consequences of leaving deep n-well out of the baseline, for designers: no
isolated NMOS, no NMOS at a negative body potential, substrate noise from 5 V
digital couples into analog NMOS, and latch-up protection relies on guard
rings and tap spacing alone. Digital, guard-ringed 5 V analog and level
shifting all work without it.

### 5.4 Oxide markers

One explicit marker layer per non-base oxide, named `ox_3v3` and `ox_1v8`.
Public sources disagree on polarity: GF180MCU's default is 3.3 V and the
drawn `Dualgate` layer marks the 5 V (6 V) gate oxide (`06_Drawn_layer10.csv`,
`15_Dualgate40_1.csv`); SCMOS rev 8's default is the thin oxide and
`THICK_ACTIVE` marks the thick one (SCMOS rules section 24). The generic PDK
draws an explicit marker for each non-base class and the retarget step derives
each foundry's real oxide masks. Class membership is geometric: a gate whose
poly touches or lies inside an oxide marker belongs to that class, and a poly
shape that leaves the marker still carries that class's rules until it ends.

### 5.5 Design rules

Each rule value is a field of the process description, set by the section 3.6
model (largest public value times the margin, recorded with its evidence
entries). The rules tool reads those fields and writes a machine-readable
rule table. Each rule row has: id, layers, value, the process field it reads,
the variant it belongs to, the evidence entries the field cites and the
margin achieved. Formulas from lithography and overlay capability are used
only for rules that no public source bounds, and the row says so. The rule
table generates the KLayout and Magic decks, the design rule manual, and the
per-rule test fixtures (section 9).

Which rules are weakly bounded by public evidence is expected, from the
public sources of section 14 (section 11.3), to be: the 5 V class, bounded
by GF180MCU alone; and density windows, antenna, latch-up, ESD and seal
ring, for which the other sources publish few or no numbers. The
Phase 0 evidence set establishes the actual list. For a rule bounded by one
source the process description takes that public value as one data point and
records a larger chosen margin with its reason, and the rule row says so. Because a larger variant
may never tighten a rule (section 4.2), the `ws180g005` 5 V rules must already
be the envelope over every foundry a later variant will target, so Phase 0's
evidence set must include 5 V data from 1.8 V-core foundries, not only from
GF180MCU.

## 6. Naming

Names follow the "File naming in open source PDKs" document
(bit.ly/open-source-pdks-naming), cross-checked on 2026-10-26 against the
sky130, gf180mcu and IHP sg13g2 PDK repositories.

### 6.1 Cross-check against existing PDKs

| Item                | Naming doc                                   | sky130                                         | gf180mcu                                           | IHP sg13g2                                      | ws180g decision |
|---------------------|----------------------------------------------|------------------------------------------------|----------------------------------------------------|-------------------------------------------------|-----------------|
| Library             | `<process>_<source>_<type>_<name>`           | `sky130_fd_sc_hd`, `sky130_fd_pr`, `sky130_fd_io` | `gf180mcu_fd_sc_mcu7t5v0`, `gf180mcu_fd_pr`, `gf180mcu_fd_io`, `gf180mcu_fd_bd_sram` | `sg13g2_stdcell`, `sg13g2_pr`, `sg13g2_io` (no source tag) | Follow the doc, sky130 and gf180mcu. |
| Cell full name      | `<library>__<cell>_<size>`                   | `sky130_fd_sc_hd__a2111o_1`                    | `gf180mcu_fd_sc_mcu7t5v0__a2111o`                   | `sg13g2_nand2_1` (single underscore)            | Double underscore, as the doc. |
| Corner              | `<type>_<temp>_<voltage>[_<flags>]`          | `ss_n40C_3v00`                                  | `tt_025C_5v00`                                      | `typ_1p20V_25C` (different order and format)   | Follow the doc. |
| Voltage in names    | `v` as decimal point, two digits each side    | `3v00`, `1v80`                                  | `5v0` in library names, `5v00` in corners           | `1p20V`                                         | `5v0` in library names, `5v00` in corners, as gf180mcu. |
| Library repos       | one repo per library                          | `skywater-pdk-libs-sky130_fd_sc_hd`             | `globalfoundries-pdk-libs-gf180mcu_fd_pr`           | one tree in `IHP-Open-PDK`                      | One repo per library, named after the library (section 8.1). |

### 6.2 ws180g names

- **Process name** is the variant: `ws180g005`, `ws180g035`, `ws180g105`,
  `ws180g135`.
- **Source tag.** wafer.space is the foundry for naming purposes, so cells
  and primitives designed for this process use `fd` (owner's decision,
  2026-10-26). For libraries produced by scaling or resizing other people's
  cells the owner said only that the tag "might be different"; the proposal
  (appendix A) is a tag naming the origin, following the doc's source table:
  `osu` for cells derived from the OSU libraries, and a new tag for cells
  derived from the GF180MCU foundry libraries (candidate: `gf`) or from
  SCMOS-era kits (candidate: the kit's own name).
- **Libraries** (first release):
  - `ws180g005_fd_pr`: primitives;
  - `ws180g005_fd_sc_gp<N>t5v0`: general-purpose 5 V standard cells, `N` the
    track count the generator settles on;
  - `ws180g005_fd_io`: 5 V IO;
  - later `ws180g035_fd_sc_gp<N>t3v3`, `ws180g035_fd_sc_ls` (level shifters),
    `ws180g105_*`, `ws180g135_*`, and `ws180g005_fd_bd_*` for memories.
- **Devices** follow the doc's primitive naming. The voltage suffix is the
  device's oxide class by nominal supply, applied uniformly: `nfet_05v0`,
  `pfet_05v0`, `nfet_03v3`, `nfet_01v8`, `nfet_05v0_dnw` (in the deep n-well
  module), `diode_pw2nd_05v0`, `diode_pd2nw_05v0`, `res_generic_po`,
  `res_generic_nd`, `res_high_po` (module), `cap_mim_m4` (later), `npn_05v0`
  and `pnp_05v0` parasitic bipolars.
- **Cells:** `ws180g005_fd_sc_gp<N>t5v0__nand2_1` (for example
  `ws180g005_fd_sc_gp9t5v0__nand2_1` if N = 9).
- **Corners:** `tt_025C_5v00`, `ss_125C_4v50`, `ff_n40C_5v50`. The
  foundry-population corners of section 3.2 use the doc's two-letter codes.
  If a library ever ships a single-foundry statistical corner as well, that
  corner carries the flag `_stat`; the population corners carry no flag.
- **Layers:** the drawn-layer names of the section 5.1 table (`nw`, `nd`,
  `pd`, `po`, `co`, `m1`..`m4`, `v1`..`v4`, `mtop`, `pad`, `sab`, `ox_3v3`,
  `ox_1v8`, `dnw`, `rhi`, `mk_*`).
- **Files per cell:** the doc's cell-file set (`.gds`, `.lef`, `.magic.lef`,
  `.cdl`, `.spice`, `.v`, `.blackbox.v`, `.lib`, `.lib.json`, `.symbol.svg`,
  `.schematic.svg`, `definition.json`), one directory per cell.

A naming checker in the build rejects any artifact whose name does not parse.

## 7. Pipeline components

Each component is a separate Python package with one job, a defined input and
a defined output. Python is run with `uv`. Arrows are data flow, not build
order.

| # | Component       | Reads                                   | Produces                                                                 |
|---|-----------------|-----------------------------------------|--------------------------------------------------------------------------|
| 1 | `process/`      | the data files                           | the typed process model, variant chain, mask list                        |
| 2 | `evidence/`     | cited public documents, kept in the repository | coverage and margin reports, TCAD calibration targets              |
| 3 | `measurements/` | MOSIS report data (vendored, with public source URLs), GF180MCU foundry data, test chips | calibration and validation targets |
| 4 | `tcad/`         | 1, 3; 2 for calibration targets only      | device characterisation dataset over sampled ranges                      |
| 5 | `models/`       | 4, 3                                     | ngspice and Xyce model libraries, corners, fit reports                   |
| 6 | `rules/`        | 1                                        | rule table, KLayout and Magic DRC decks, design rule manual, per-rule fixtures |
| 7 | `layergen/`     | 1, 6                                     | the derived-mask generator used by DRC, LVS, precheck and cells          |
| 8 | `tech/`         | 1, 6, 7 (Phase 0); 5, 9 (Phase 1)        | layer map, KLayout `.lyp`/`.lyt`, Magic tech (Phase 0); LVS deck, netgen device setup, extraction (Magic, OpenRCX) (Phase 1, needs models and device definitions) |
| 9 | `devices/`      | 1, 5, 6, 8                               | `ws180g005_fd_pr`: PCells (KLayout), Xschem symbols, LVS device definitions |
| 10 | `cells/`       | 6, 8, 9                                  | `ws180g005_fd_sc_*`: layout, LEF, Liberty, CDL, Verilog, symbols         |
| 11 | `io/`          | 6, 8, 9                                  | `ws180g005_fd_io`                                                        |
| 12 | `flows/`       | 8, 10, 11                                | LibreLane and OpenROAD platform config, example designs                  |
| 13 | `precheck/`    | 6, 7, 8                                  | public precheck and retarget tool; foundry mappings via a private interface |
| 14 | `tests/`       | all                                      | the verification suite of section 9                                      |
| 15 | `build/`       | all                                      | one-command regeneration, `libs.tech` and `libs.ref` trees, release assets, docs site |

Details per component:

1. **Process specification.** Schema, data, loader with validation, the
   variant chain. The only place process numbers live. The schema generalises
   the `gf180-tcad` process-file pattern (value, bounds, provenance, source,
   role) by adding a range type, a `design-target` provenance, and a foundry
   axis for the evidence links.
2. **Evidence set.** Structured, cited public facts, each entry a file in the
   repository naming the public document it comes from; parsers for the
   sources that have a machine-readable form; the margin report of section
   3.6. The first entries are the public documents listed in section 14,
   each cited as the document itself. The public PDK regenerates from the
   repository alone, with no input from any other location.
3. **Measurements.** Raw silicon data. First content: the per-report BSIM3
   model cards and a long-format parameter table parsed from the public
   MOSIS wafer-acceptance reports for the TSMC 0.18 µm family (section
   11.2), kept in `measurements/` with the public MOSIS
   source URL of every report recorded beside its parsed output, so a third
   party can regenerate them from the reports alone. Also the GF180MCU
   foundry measured IV/CV data published in `gf180mcu_fd_pr`
   (`models/180MCU_SPICE_DATA`); later the test-chip data of section 10.
4. **TCAD.** Open-source device simulation driven by the process model.
   Reuses the `mithro/gf180-tcad` infrastructure and the `mithro/gplugins`
   DEVSIM plugin fork (section 11.1). Builds 1D stacks and parametric 2D
   cross-sections (no GDS needed) for each device class, samples the range
   space with a space-filling design (Sobol or Latin hypercube), runs C-V and
   I-V, and caches every run by parameter hash. Calibrated against GF180MCU's
   public 5 V and 3.3 V cards first, then against measurements. Heavy work is
   1D or coarse 2D; full 2D only at chosen points.
5. **Compact models.** Fits BSIM4 (native in ngspice and Xyce) to the TCAD
   dataset, producing typical and population-envelope corner cards,
   temperature, and mismatch parameters, for each device class; resistor,
   capacitor, diode and bipolar models. BSIM-BULK via OpenVAF/OSDI is a later
   target. Output includes a fit-error report against both TCAD and
   measurements, using the three-level Agree / Same process / Disagree verdict
   from `gf180-tcad`.
6. **Design rules.** The rule table and everything generated from it
   (section 5.5).
7. **Layer generation.** One implementation of each generated layer, used by
   every consumer so that DRC, LVS, precheck and cell generation agree.
8. **Tech files.** Layer map with GDS numbers (one block per variant, with
   `ws180g005` numbers fixed forever); KLayout and Magic technology; netgen;
   KLayout LVS; extraction set-up with capacitance tables computed from the
   stack ranges.
9. **Primitive devices.** Parameterised layout generators and symbols for
   every modelled device, each tied to its LVS definition and model name.
   The generators use gdsfactory, following the owner's direction that
   layout generation "should generally use gdsfactory". The published
   library ships fixed-parameter GDS cells for the characterised sizes plus
   KLayout PCells written against KLayout's own Python API only, generated
   from the same source, so the published PDK has no gdsfactory dependency.
   The gdsfactory PDK package of section 8.3 is a separate, later deliverable.
10. **Standard cells.** A gdsfactory-based generator producing layout from
    cell descriptions against the rule table, then characterisation with an
    open characteriser (CharLib or equivalent), LEF via Magic and KLayout,
    CDL and Verilog.
    Because the rule table can change, cells are regenerated, never
    hand-edited. Tap and end-cap cells are generic like every other cell,
    drawn to the envelope rules including the n-well enclosure envelope with
    margin, one set per variant. Boundary-crossing tap active is expected to
    be what breaks first in abutted rows on a new target (section 11.3); when
    that happens it is a defect in the generic rules or in the retarget
    transform, never a
    reason for a target-specific library cell (owner's requirement: nothing
    about a specific foundry is embedded in IP).
11. **IO.** 5 V pad cells (ESD, clamps, pad frame pieces) generated with
    gdsfactory against the rules, including `mtop` drawn to the thick-top-metal
    rules so one drawing stays legal at every top-metal thickness in the range.
12. **Flows.** LibreLane and OpenROAD platform configuration and example
    designs that prove drawn-to-GDS, DRC and LVS clean for each variant,
    including the SERV test SoC of section 10.
13. **Precheck and retarget.** Public tool modelled on the gf180mcu precheck:
    runs generic DRC in both engines, LVS, antenna, density and the upward
    compatibility checks, then applies a foundry mapping (layer map, cut
    resize, oxide mask derivation, bias, helper layers). Mapping definitions
    and foundry decks live in a private repository behind a public interface;
    the GF180MCU mapping is public because its deck is public.
14. **Verification.** Section 9.
15. **Build and release.** One command regenerates everything from the
    process data with pinned tool versions in a container image (reusing the
    `gf180-tcad` reproducible-image recipe), caches expensive stages by input
    hash, writes the per-library output repositories, assembles the
    open_pdks-style tree per variant, packages the release asset for ciel,
    builds the docs site including the SCMOS compatibility page and the
    evidence report, and runs the naming checker and the private-data checker.
    ciel today knows only its built-in PDK families and their release naming,
    so "installable by ciel" is a work item of its own: either a change to
    ciel to accept this family, or a release layout that matches what ciel
    already fetches, decided and done in Phase 1 (section 10).

## 8. Repositories, published form and hosting

### 8.1 Repositories

Decision of 2026-10-26: multiple repositories with submodules, as gf180mcu and
sky130 do, with the meta-repository holding the pipeline.

- **`ws180g-pdk`** (this repository, GitHub `wafer-space-robot/ws180g-pdk`):
  the meta-repository. Process description,
  evidence set, measurements index, every generator, tests, docs, and the
  library repositories as submodules under `libraries/`. Mirrors the role of
  `gf180mcu-pdk` and `skywater-pdk`, where the scripts live in the
  meta-repository.
- **One repository per library**, holding generated output only, one file
  per item, committed by the build: `ws180g005_fd_pr`,
  `ws180g005_fd_sc_gp<N>t5v0`, `ws180g005_fd_io`, and later the `ws180g035_*`,
  `ws180g105_*` and `ws180g135_*` libraries and `ws180g005_fd_bd_*`. A
  library introduced in one variant is shared, unchanged, by every larger
  variant (section 4.2), so there is never a per-variant copy of a library.
- **A private repository** for foundry mappings and decks that are not
  public, consumed by `precheck/` through its public interface. It is outside
  the regeneration path: the public PDK builds without it. The GF180MCU
  mapping is public and lives in `ws180g-pdk`.

### 8.2 Hosting

Public from the first commit under the `wafer-space-robot` GitHub account,
with the expectation of moving to the `wafer-space` organisation once the
development approach has proved itself. Apache-2.0 for code and generated
content. Third-party material keeps its own licence, recorded in a README in
its directory; material that may not be redistributed (for example the IIT
TSMC 0.18 cells, which are research-only) is referenced, never copied.

### 8.3 Published form

- **One file per item**, in the sky130 and gf180mcu style: each cell or
  device in its own directory with the file set of section 6.2.
- **A combined tree per variant**, in the open_pdks layout, built from the
  per-item files and published as a release asset that ciel can install:

```
ws180g005/
  libs.tech/{klayout,magic,netgen,ngspice,xyce,xschem,openlane,librelane}
  libs.ref/ws180g005_fd_pr/{gds,mag,spice,cdl,xschem}
  libs.ref/ws180g005_fd_sc_gp<N>t5v0/{gds,mag,lef,lib,cdl,spice,verilog}
  libs.ref/ws180g005_fd_io/{gds,mag,lef,lib,cdl,spice,verilog}
  docs/
```

- **Documentation site** generated from the rule table, the process
  description, the model reports, the evidence report and the SCMOS
  compatibility page.
- **gdsfactory PDK package** for consumers: a later deliverable. The PDK
  itself does not use gdsfactory; the generators do.

### 8.4 Meta-repository layout

```
ws180g/
  docs/            this document, generated manual sources, site config
  process/         virtual process data, schema, loader
  evidence/        public facts, parsers, margin reports
  measurements/    pinned imports and their index
  tcad/            device simulation, sampling, calibration, cache
  models/          model fitting and cards
  rules/           rule table, DRC deck generators, manual
  layergen/        derived-mask generation
  tech/            tech-file generators
  devices/         PCells, symbols, LVS device definitions
  cells/           standard-cell generator and characterisation
  io/              pad cell generator
  flows/           LibreLane and OpenROAD configuration, example designs
  precheck/        public precheck and retarget, GF180MCU mapping
  tests/           the verification suite
  build/           orchestration, images, release packaging
  libraries/       submodules: the per-library output repositories
  tmp/             local scratch, gitignored
```

## 9. Verification strategy

Six layers, all run on every build, with the DRC test conventions of the
"Design Rule Check Testing" document (bit.ly/drc-testing): one test per GDS
file, one thing per test, tests readable as documentation.

1. **Unit tests** on the process loader, parsers, rule derivation, layer
   generation and naming rules.
2. **Rule tests.** Every rule has pass fixtures and fail fixtures, generated
   from the rule table, run through both KLayout and Magic. A rule is accepted
   only when both engines agree on every fixture. A pass fixture that fails is
   a false positive; a fail fixture that passes is a false negative. Magic's
   DRC cannot express every rule KLayout can (density windows, some antenna
   and latch-up checks); such a rule is marked "KLayout only" in the rule
   table, is still tested in KLayout, and the Magic deck carries a comment
   listing it, so the exceptions are explicit rather than silent.
   Interaction tests cover known rule pairs: density with fill, antenna with
   diodes, latch-up with guard rings and taps, oxide markers with adjacent
   active.
3. **Generated and fuzz layouts.** Random DRC-clean layouts built with
   gdsfactory: random primitive parameters, random cell tilings and
   abutments (including every pair of neighbouring cells, in both orders, in
   rows about 200 µm long with alternate mirroring), random routing. Each is
   run through the generic decks, then retargeted and run through the public
   GF180MCU deck. Any GF180MCU failure on a generic-clean layout is a defect
   in the generic rules and becomes a permanent regression fixture. Generated
   dimensions are biased to the rule edges: each width, space, enclosure and
   extension is drawn at exactly the generic minimum, at the minimum plus one
   grid step, and at typical values, because a layout at typical dimensions
   does not test the claim. Layouts are generated freely and filtered by the
   generic DRC, so the generator's own notion of "clean" is never trusted.
   Stress layouts cover maximum density, minimum-pitch arrays, large via
   arrays and worst-case antenna ratios. The same loop is run privately
   against every other foundry deck as it becomes available at tapeout time;
   what may flow back from a private failure into the public rules is
   decided when that first happens, with the working assumption of section
   12.1.
4. **Upward compatibility.** Every smaller variant's fixtures and example
   designs run under every larger variant's decks, unchanged, and must give
   the same result.
5. **Model and cell checks.** Fit-error budgets against TCAD and measurements
   with the three-level verdict; physical sanity (monotonic Id-Vg, positive
   capacitances, gate capacitance never above the oxide capacitance);
   ngspice and Xyce convergence and agreement on
   every card, with the BSIM version pinned and recorded; held-out geometries
   never used in fitting; LVS of every cell and primitive in both netgen and
   KLayout; Liberty sanity (delay monotonic in load and slew); ring-oscillator
   simulations compared with the MOSIS reports and the GF180MCU electrical
   specifications.
6. **Silicon.** The test tiles of section 10, measured, fed back into
   `measurements/`, and used to recalibrate TCAD and re-fit models. The flow
   is the one in "Test structure generation and measurement"
   (bit.ly/test-open-pdk): generate structures, simulate them, measure them,
   aggregate into models.

## 10. Phases and gates

Each phase ends with a release: a variant, or the 3-metal option in Phase 4. Phase 1 ends with first silicon,
meaning the four tiles below submitted to a wafer.space GF180MCU run and
accepted by that run's precheck; their measurements arrive during Phase 2 and
are a Phase 2 input, not a Phase 1 gate. The order of Phases 2 and 3 is the
owner's order of section 4.3: 1.8 V before 3.3 V.

| Phase | Deliverable | Gate |
|---|---|---|
| **0 Foundations** | Process schema and loader with the 5 V content as ranges; evidence set with the first margin report; rule table; KLayout and Magic DRC decks with per-rule fixtures; layer generation; the Phase 0 part of the tech files (layer map, KLayout and Magic technology); a minimal GF180MCU layer mapping and the fixture-retarget check; naming and private-data checkers; build skeleton; reproducible image; meta-repository and library repositories created | Both DRC engines pass every fixture (or the rule is marked KLayout-only); every generic pass fixture, retargeted, passes the public GF180MCU deck; the margin report shows the section 3.6 margin on every covered rule and lists every uncovered one. |
| **1 `ws180g005`** | TCAD and 5 V models anchored on GF180MCU public cards then MOSIS and GF measured data; LVS deck, extraction and netgen setup; `ws180g005_fd_pr`; `ws180g005_fd_sc_*`; `ws180g005_fd_io`; LibreLane flow; full precheck with the GF180MCU mapping; fuzz loop against the GF180MCU deck; SCMOS compatibility page with `λ_5v0` (section 3.7); ciel installability; first silicon | Example designs clean in both engines; retargeted GDS passes the public GF180MCU deck; ring-oscillator simulations bracket the MOSIS and GF180MCU public values; the four tiles below are submitted to a wafer.space GF180MCU run. |
| **2 `ws180g105`** | 1.8 V layers, rules, models, primitives, cells, level shifters; `λ_1v8` on the SCMOS page; upward-compatibility proof; Phase 1 tile measurements folded into calibration | All `ws180g005` tests pass unchanged under `ws180g105`; the 1.8 V evidence set and margin report are complete; `ws180g105` has no GF180MCU path, so its silicon gate is a 1.8 V characterisation tile accepted by the first non-GF180MCU target's precheck. |
| **3 `ws180g035` and `ws180g135`** | 3.3 V additions, same shape as Phase 2, including `λ_3v3` on the SCMOS page; `ws180g135` assembled from the two | All `ws180g005` tests pass unchanged under `ws180g035`, and all `ws180g005` and `ws180g105` tests under `ws180g135`; GF180MCU precheck passes for `ws180g035`; a second GF180MCU silicon round adds 3.3 V structures. |
| **4 3-metal option** | The 3-metal stack option on every released variant: its rule model (whether the top metal of the 3-metal stack carries the `mtop` rules) and the compatibility rule between metal options decided at the start of the phase (section 5.3); rules, tech files, flows and example designs for the 3-metal stack | 3-metal example designs clean in both engines; the compatibility rule between metal options is documented and tested; a 3-metal retarget passes a public target deck. |
| **Later** | Silicon calibration loop, MIM module, SRAM bit cell and compiler, more foundry mappings, the gdsfactory PDK package | Per item. |

**First silicon (Phase 1).** The four tiles are the owner's decision of
2026-10-26. That they are designed in `ws180g005`, passed through precheck,
retargeted to GF180MCU and placed on a wafer.space GF180MCU run is the
author's proposal, following from GF180MCU being a required target for
`ws180g005` (appendix A, item 22):

- (a) **a process characterisation tile**: MOSFET arrays over geometry per
  oxide, resistors, capacitors, contact and via chains, line-width and
  line-end structures, ring oscillators;
- (b) **an IP characterisation tile**: the IO cells and standard cells under
  test;
- (c) **a memory characterisation tile**: DFFRAM-style cell-based memory and
  other memory structures;
- (d) **a test SERV SoC** with two-phase clocking, so that hold violations
  cannot occur, generated with LibreLane on the `ws180g005` cells.

## 11. Related work and what is reused

### 11.1 `mithro/gf180-tcad` (public, Apache-2.0)

Open-source TCAD for GF180MCU, validated against the PDK's own SPICE models.
State on 2026-10-26, from its public repository (pull requests up to #42
merged by that date) and its documentation: MOS-capacitor
capacitance-voltage (C-V) curves in 1D and 2D for `nfet_05v0` and
`pfet_05v0`, with mesh-convergence tooling, a byte-identical reproduction
check and a calibration of the capacitor C-V against the PDK's own SPICE
models; no MOSFET I-V and no BSIM extraction yet.

Reused as a base:

- the `mithro/gplugins` DEVSIM plugin fork (1D stack builder, analytic doping,
  typed contacts, quasi-static and small-signal AC C-V sweeps), which is
  PDK-agnostic;
- mesh specification and convergence tooling; the exact 1D Poisson-Boltzmann
  oracle; BSIM4 overlap and fringe bookkeeping;
- the process-file pattern (value, bounds, provenance, source, role; calibrated
  values kept out of the inputs; parameter hashes; leak guards between
  calibration and validation);
- the SPICE reference machinery (ngspice and Xyce runners, raw-file parser,
  metric extraction, corner envelope and spec windows) and the three-level
  agreement verdict;
- the sandbox, reproducible pinned images, manifest and provenance scheme.

What has to change for ws180g: ranges as the sweep space rather than only fit
bounds; a `design-target` provenance; a parametric cross-section builder that
needs no foundry GDS; the device, geometry and bias-grid tables as data per
device class; density-gradient (quantum confinement) and poly-depletion
treatment before thin-oxide results are trusted; an iterative solver or
half-domain for long-channel 2D; a parameter-hash-keyed cache; an extraction
flow that produces BSIM cards (an existing open flow is preferred over
writing one).

### 11.2 Public MOSIS material

MOSIS published wafer-acceptance reports (parametric test results, with a
BSIM3 model card where one was published) for the TSMC 0.18 µm family (MOSIS technology code
SCN018); an archived index and an example report are listed in section 14.
The measurements component (section 7, component 3) collects the reports it
can retrieve from public archives, parses each into a per-report model card
and a long-format parameter table tied to the report's public URL, and
records which runs and years it covers; the count and coverage are an output
of that component, not an assumption of this document. The SCMOS rev 8 rules
(section 14) are public, and the rules component builds the machine-readable
SCMOS rule table from them.

### 11.3 The public 180 nm rule sources

The public rule sources of section 14 are the GF180MCU design rule manual
tables, MOSIS SCMOS rev 8, the X-FAB XC018 process data sheet rev 3.0
("Basic Design Rules" table) and the onsemi ONC18 data sheet ONC181818/D.
The evidence component compares them in full in Phase 0; the rule table of
section 5.5 is built from that comparison, not from this section.

Values read directly from those sources (checked on 2026-10-27):

- GF180MCU (3.3 V column) and X-FAB XC018 publish the same basic minimum
  widths and spaces: active 0.22 / 0.28 µm (DF.1a, DF.3a in
  `14_COMP33_1.csv`), poly 0.18 µm (PL.1, `16_Poly2_42.csv`), contact
  0.22 µm size and 0.25 µm space (CO.1, CO.2a, `21_Contact_56.csv`), metal 1
  0.23 / 0.23 µm (Mn.1, Mn.2a, `22_Metaln_58.csv`), via 0.26 / 0.26 µm
  (Vn.1, Vn.2a, `23_Vian_59.csv`), against the identical XC018 values. The
  author reads this as a TSMC-derived rule family that the author expects
  other TSMC-compatible 180 nm processes to share; the Phase 0 comparison
  says how far the onsemi ONC18 data sheet, which publishes fewer geometric
  values, agrees;
- contacts and vias are exact-size and must be regenerated per target
  (section 3.3); the top via is a real split: 0.26 µm on GF180MCU (Vn.1)
  against 0.36 µm on X-FAB XC018 ("Top Via" width; its space is 0.35 µm) and
  0.36 µm under SCMOS rev 8 rule 29.1 at λ = 0.09 µm;
- the thick-top-metal rules that IO must meet: MT30.2 space 1.8 µm and the
  via-array rule MT30.8b (`25_Thick_MetalTop_62.csv`).

Expectations the design is built on, each to be confirmed or refuted by the
Phase 0 comparison or the Phase 1 cells before anything depends on it:

- the 5 V class is bounded by GF180MCU alone: SCMOS's `THICK_ACTIVE` rules
  (section 24) state no voltage, and the XC018 and ONC18 data sheets offer
  5 V devices but publish no 5 V-specific rule values;
- SCMOS's lambda enclosures set the contacted pitch and are the single most
  expensive choice; cells drawn to the envelope will be substantially larger
  than single-foundry cells (the author's estimate in section 12, item 5),
  and tap and end-cap cells, whose active crosses the cell boundary, are the
  cells most exposed to enclosure rules at abutment and so the likeliest to
  break first in abutted rows;
- the public GF180MCU IO cells (`gf180mcu_fd_io`) are believed to be drawn
  to the thin top metal and so not to meet the MT30 rules; Phase 0 runs that
  DRC.
  IO is generated against the `mtop` rules either way (section 7, component
  11).

Design choices that follow from the sources: the envelope method (largest
public minimum for widths, spaces, enclosures and extensions; smallest public
maximum for tap distance and density; rules matched by meaning, not by name;
device classes matched by oxide), the top metal drawn to the thick rules
everywhere (section 3.2), and one explicit marker per oxide (section 5.4).

### 11.4 Reference documents

- File naming in open source PDKs: bit.ly/open-source-pdks-naming. Used for
  section 6 throughout.
- Building a (future) open source PDK: bit.ly/build-pdk. Taken from it: the
  three-part view of a PDK (design rules, device information, core
  libraries) behind section 7, and the requirement that every design rule
  document both why it exists and how it is checked, which is why each rule
  row in section 5.5 carries its provenance and the per-rule fixtures of
  section 9 double as its documentation. Not taken: its device-behaviour and
  TCAD sections, which are placeholders in the source document.
- Design Rule Check Testing: bit.ly/drc-testing. Used for section 9.
- Test structure generation and measurement: bit.ly/test-open-pdk. Used for
  the silicon layer of section 9 and the tiles of section 10.

## 12. Risks and open questions

1. **Design rules are foundry policy, not physics.** TCAD can produce device
   behaviour but not another foundry's rules. The generic rules are an
   envelope with margin over public data, checked empirically against the one
   public deck (GF180MCU) by the fuzz loop. The invariant of section 1 is
   therefore proven for GF180MCU only until further decks are exercised
   privately at tapeout time. **What happens when a private foundry deck
   fails a generic-clean design is decided when private decks are first
   run** (owner, 2026-10-27: "can be decided when we get to running private
   decks which won't be for a long time"); until then the author's proposal
   below is the working assumption and nothing in Phases 0 to 3 depends on
   it. Raising a public rule to the value the private deck needs, or adding
   a regression fixture built from that failure, would put NDA-derived
   information into the public repository and break section 13. The
   proposed policy: the failure blocks that design for that target in the
   private precheck only; a public rule changes only when a public source or
   a "chosen" justification that does not depend on the private deck supports
   the new value; the private mapping may add target-specific transforms
   (fill, bias, cut resize) that make the design pass without changing the
   public rules. The consequence is that the invariant may remain unprovable
   in public for some targets.
2. **The 5 V class is the weakest-bounded publicly and decides who can make
   the PDK.** Picking the 5 V partner foundries early reduces this risk.
3. **TCAD has not yet produced a MOSFET I-V or a BSIM card anywhere in the
   reused work.** The model pipeline is validated end to end on GF180MCU's
   public 5 V cards before it is pointed at the virtual process. Thin oxides
   need density-gradient and poly-depletion treatment the current DEVSIM
   set-up lacks.
4. **Compute.** 2D TCAD costs hours per sweep; range sampling is feasible only
   with 1D or coarse 2D inner loops, a surrogate over the ranges, and a cache.
5. **Area.** Enclosure-driven contacted pitch may make cells substantially
   larger than single-foundry cells; the author's estimate is a factor of two
   or more, unverified until the Phase 1 cells exist. Accepted by priority 1.
6. **Open: the 3-metal option's rule model** and the compatibility rule
   between metal options, both settled at the start of Phase 4 (section 5.3).
7. **Open: the exact baseline track count and cell architecture**, settled by
   the generator in Phase 1.
8. **Open: which open extraction flow produces the BSIM cards** (DMT-core is
   GPL-3; its licence interaction with an Apache-2.0 pipeline needs checking).
9. **Decisions awaiting the owner** are collected in appendix B; decisions
   the author made without an owner statement are listed in appendix A.

## 13. Rules on private information

- The repository holds only public facts. Every value carries a citation to
  a public document, with the rule or table reference where one exists.
- Nothing is copied from a foundry document under NDA or from any document
  derived from one. GF180MCU values are taken from the open PDK's published
  CSV tables.
- Values with no public source are marked "chosen" with their reasoning,
  never attributed to a foundry.
- A pre-commit and CI check rejects any artifact tagged as sourced from a
  private document, and the evidence parsers refuse unknown sources.
- Third-party material that may not be redistributed is referenced, not
  copied.

## 14. Sources

- GF180MCU design manual tables (Apache-2.0):
  https://github.com/fossi-foundation/gf180mcu-pdk/tree/main/docs/physical_verification/design_manual/tables_clear
  (`03_met_levels8_1.csv`, `05_Current_0.18_MCU_9.csv`, `06_Drawn_layer10.csv`,
  `07_Mask_Layer14.csv`)
- gf180mcu-pdk submodules (`.gitmodules`): https://github.com/fossi-foundation/gf180mcu-pdk
- skywater-pdk libraries: https://github.com/google/skywater-pdk/tree/main/libraries
- IHP Open PDK sg13g2 libraries: https://github.com/IHP-GmbH/IHP-Open-PDK/tree/main/ihp-sg13g2/libs.ref
- CMC Microsystems TSMC 0.18 µm page (process options): https://www.cmc.ca/tsmc-180-nm-cmos/
- Europractice UMC page (L180 MM/RF, triple well, MiM): https://europractice-ic.com/technologies/asics/umc/
- Europractice TSMC 0.18 option sheet (Hipo resistor): https://europractice-ic.com/wp-content/uploads/2019/12/TSMC-EUROPRACTICE-v1-2020-01-01.pdf
- X-FAB XH018 page: https://www.xfab.com/technology/cmos/018-um-xh018/
- X-FAB XC018 process data sheet rev 3.0 (2008), "Basic Design Rules" (mirror): https://datasheet.datasheetarchive.com/originals/crawler/xfab.com/a3edb8140abfda7a83325589538d6415.pdf
- onsemi ONC18 data sheet ONC181818/D rev 0 (2016), "Process Characteristics": https://www.onsemi.com/site/pdf/ONC181818-D.PDF
- MOSIS SCMOS rev 8.00 rules, single-page mirror (UCSB): https://bears.ece.ucsb.edu/class/ece224a/scmos/default.html
- MOSIS TSMC 0.18 run reports (archived index of parametric test results): https://web.archive.org/web/2015/https://www.mosis.com/cgi-bin/params/tsmc-018/
- GF180MCU DRM tables also cited inline: `14_COMP33_1.csv`, `15_Dualgate40_1.csv`, `16_Poly2_42.csv` (PL.1 poly width; PL.2, gate length per voltage class), `21_Contact_56.csv`, `22_Metaln_58.csv`, `23_Vian_59.csv`, `25_Thick_MetalTop_62.csv`, in the same `tables_clear` directory
- MOSIS SCMOS rev 8 mirror, deep n-well page: https://bears.ece.ucsb.edu/class/ece224a/scmos/scmos-dnw.html
- MOSIS TSMC 0.18 run report example (IIT Madras copy): https://www.ee.iitm.ac.in/~nagendra/cadinfo/tsmc018_info.txt
- mithro/gf180-tcad: https://github.com/mithro/gf180-tcad and https://gf180-tcad.readthedocs.io/
- mithro/gplugins (DEVSIM plugin fork): https://github.com/mithro/gplugins

## Appendix A. Decisions proposed by the author

Each of these is a choice the author made without a statement from the owner.
Accept or change each; none is load-bearing for the others unless noted.

1. The strict priority order between manufacturability and mask/wafer cost
   (section 1).
2. "Nothing in the released PDK is hand-edited" and "public measured data
   only" (section 1).
3. The margin rule applied to maxima and density floors, and the "at least"
   wording (section 3.6).
4. Contacts and vias drawn at a nominal size equal to the largest public exact
   size and resized at retarget (section 3.3).
5. Precheck applies bias and helper layers beyond a plain layer map (section
   3.3; section 7, component 13).
6. The absence of an oxide marker means 5 V; marker names `ox_3v3`, `ox_1v8`;
   geometric class membership (sections 3.4, 5.4).
7. Library names carry the variant that introduced them, so larger variants
   ship smaller variants' libraries unchanged (section 4.2).
8. TOML with the standard-library reader for the process description
   (section 5.1).
9. Single drawn n-well with implicit p-well; single poly; the drawn-layer
   names of the section 5.1 table.
10. Deep n-well and high-resistance poly defined as optional modules from day
    one (the owner chose SAB as the only baseline module and asked about the
    consequences of omitting deep n-well; defining the modules now is the
    author's choice) (section 5.3).
11. `5v0` in library names and `5v00` in corners, following gf180mcu rather
    than the naming doc's "two digits each side" (section 6.1); the `gp<N>t`
    library-type naming; the device suffix convention; the corner set; the
    `_stat` flag (section 6.2).
12. The naming checker and the private-data checker in the build (section
    6.2; section 7, component 15; section 13).
13. Fifteen components, one Python package each, run with `uv` (section 7).
14. Sobol or Latin hypercube sampling; BSIM4 first and BSIM-BULK later;
    ngspice and Xyce both (section 7, components 4 and 5).
15. GDS numbers in one block per variant, `ws180g005` numbers fixed forever
    (section 7, component 8).
16. CharLib as the characteriser candidate (section 7, component 10).
17. The private mapping repository and its interface (section 7, component
    13; section 8.1).
18. Apache-2.0 for generated content (section 8.2).
19. `libs.tech` with both `openlane` and `librelane` directories (section 8.3).
20. The meta-repository layout and the `libraries/` submodule path
    (section 8.4).
21. The six verification layers, the "both engines agree" acceptance with
    KLayout-only exceptions, and the 200 µm abutment rows (section 9).
22. The phase structure and every gate, including the 1.8 V characterisation
    tile as the Phase 2 silicon gate, a second GF180MCU silicon round in
    Phase 3 and the ring-oscillator "bracket" gate (section 10).
23. The derived-library source tags (section 6.2).

## Appendix B. Decisions awaiting the owner

Resolved on 2026-10-27 by the owner: the phase order of the oxides is 5 V,
then 1.8 V, then 3.3 V (section 4.3); the 6 kÅ GF180MCU top-metal option is
not available and is ignored, so the top-metal range starts at 9 kÅ minus
margin (section 3.2); the SCMOS submission grid is not a target constraint,
and the design grid is a process-description parameter whose final value is
unknown, 0.005 µm provisionally (section 5.2); the 3-metal option is done
after the 3.3 V work has completed, as Phase 4, with its rule model and the
compatibility rule between metal options settled at the start of that phase
(sections 5.3 and 10); the policy for a private-deck failure is decided when
private decks are first run, far in the future, with the author's proposal
of section 12.1 as the working assumption until then.

1. **Appendix A** as a whole: accept, or change items individually.
