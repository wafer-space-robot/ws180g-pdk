<!-- SPDX-License-Identifier: Apache-2.0 -->
# GF180MCU ngspice model card (`gf180mcu-models`)

The entries in `evidence/data/gf180mcu-models.toml` are transcribed by hand from the
ngspice model card `sm141064.ngspice` of the open GF180MCU PDK:

- **Upstream:** repository `fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr`, path
  `models/ngspice/sm141064.ngspice`, pinned to commit
  `63d25e2aeb8db6976cc107474a9658b4ea73cc05` (`commit` in `evidence/data/sources.toml`):
  <https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/63d25e2aeb8db6976cc107474a9658b4ea73cc05/models/ngspice/sm141064.ngspice>.
  That is the last upstream commit with the file under this name: commit `7f72dd7` renamed
  the model files to `.sp`, so the path on `main` no longer exists.
- **Licence:** Apache-2.0. The file is not vendored (it is about 755 kB and only a few
  values are used); the line numbers below let anyone check them.
- **Retrieved:** 2026-11-07

## The copy read: line numbers and sha256

The values were read from the copy installed by **open_pdks commit
`1689ac3f2dc763876eaf967227c7dfe831b031ae`** at
`/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice` in the container image
`ghcr.io/mithro/gf180-tcad-charon:local`, with
`docker run --rm ghcr.io/mithro/gf180-tcad-charon:local grep -n ... <path>`. **The line
numbers in every `cite` and the sha256 below refer to that installed copy, not to the
upstream file.** open_pdks rewrites the card when it installs it (the `.lib` includes
point at `sm141064.spice`, `.param` lines lose their spaces and quotes, and continuation
lines are split one parameter per line), so its bytes and line numbers differ from
upstream. The installation's `SOURCES` file names only the open_pdks commit.

| File | sha256 |
|---|---|
| `sm141064.ngspice` | `69a7ab877344a6d477fdd11440457f64e7ad88a624504a737a161da463de8bc8` (installed copy) |

The upstream file at the pinned commit (sha256
`677822db50bf8968f77854bb455006ac5c245deb46ecfc8b352934e752135c46`) was fetched on
2026-11-07 and checked: every transcribed value appears there unchanged, at the upstream
lines given in the last column below.

## What was transcribed

| Entry | Line (installed) | Model | As written | Value | Line (upstream) |
|---|---|---|---|---|---|
| `gf180mcu-models/nfet_06v0/lmin` | 37515 | `nfet_06v0.1` | `lmin=6e-007` | 0.6 um | 37626 |
| `gf180mcu-models/nfet_06v0/lmin_bin0` | 37177 | `nfet_06v0.0` | `lmin=7e-007` | 0.7 um | 37535 |
| `gf180mcu-models/nfet_06v0/toxe` | 37309 | `nfet_06v0.0` | `toxe='1.52e-008+nfet_06v0_tox'` | 15.2 nm | 37541 |
| `gf180mcu-models/nfet_06v0/toxp` | 37311 | `nfet_06v0.0` | `toxp='1.6e-008+nfet_06v0_tox'` | 16.0 nm | 37541 |
| `gf180mcu-models/nfet_06v0/vth0` | 37337 | `nfet_06v0.0` | `vth0='0.67314+nfet_06v0_vth0'` | 0.67314 V | 37549 |
| `gf180mcu-models/pfet_06v0/lmin` | 38177 | `pfet_06v0.0` | `lmin=0.5e-6` | 0.5 um | 37958 |
| `gf180mcu-models/pfet_06v0/vth0` | 38274 | `pfet_06v0.0` | `vth0='-0.8978+pfet_06v0_dvth0'` | -0.8978 V | 37973 |

The nfet card has two length bins in `.lib nfet_06v0_t`: `.model nfet_06v0.0` (installed
line 37055, `lmin=7e-007`, `lmax=5.0001e-005`) and `.model nfet_06v0.1` (installed line
37393, with `lmin=6e-007` on line 37515 and `lmax=7e-007`). `nfet_06v0/lmin` is the
smallest gate length the card supports (0.6 um, bin .1), like the pfet entry; the bin-0
bound is kept as `nfet_06v0/lmin_bin0`. The pfet lines belong to `.model pfet_06v0.0`
(installed line 38091, in `.lib pfet_06v0_t`), the only bin of that library.

Both libraries are included by the `typical` section (`.lib typical`, installed lines 105 to
135), which sets the corner offsets to zero: `.param nfet_06v0_vth0=0` (line 111),
`.param nfet_06v0_tox=0` (line 114) and `.param pfet_06v0_dvth0=0` (line 124); upstream
lines 112, 115 and 125. The values above are the typical values with those offsets
resolved; the other corners (`ff`, `ss`, `fs`, `sf`) shift them. `lmin` is a bound of a
model bin, not a design rule.
