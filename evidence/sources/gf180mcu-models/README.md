<!-- SPDX-License-Identifier: Apache-2.0 -->
# GF180MCU ngspice model card (`gf180mcu-models`)

The entries in `evidence/data/gf180mcu-models.toml` are transcribed by hand from the
ngspice model card `sm141064.ngspice` of the open GF180MCU PDK:

- **Upstream:** repository `fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr`, path
  `models/ngspice/sm141064.ngspice`,
  <https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/blob/main/models/ngspice/sm141064.ngspice>
- **Licence:** Apache-2.0. The file is not vendored (it is 755 kB and only six values are
  used); the line numbers below let anyone check them.
- **Retrieved:** 2026-11-07
- **Copy read:** the file as installed by open_pdks commit
  `1689ac3f2dc763876eaf967227c7dfe831b031ae` (recorded as `commit` in
  `evidence/data/sources.toml`; the installation's `SOURCES` file names no
  gf180mcu_fd_pr commit) at `/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice` in
  the container image `ghcr.io/mithro/gf180-tcad-charon:local`, read with
  `docker run --rm ghcr.io/mithro/gf180-tcad-charon:local grep -n ... <path>`. Line numbers
  refer to that copy.

| File | sha256 |
|---|---|
| `sm141064.ngspice` | `69a7ab877344a6d477fdd11440457f64e7ad88a624504a737a161da463de8bc8` |

## What was transcribed

| Entry | Line | As written | Value |
|---|---|---|---|
| `gf180mcu-models/nfet_06v0/lmin` | 37177 | `lmin=7e-007` | 0.7 um |
| `gf180mcu-models/nfet_06v0/toxe` | 37309 | `toxe='1.52e-008+nfet_06v0_tox'` | 15.2 nm |
| `gf180mcu-models/nfet_06v0/toxp` | 37311 | `toxp='1.6e-008+nfet_06v0_tox'` | 16.0 nm |
| `gf180mcu-models/nfet_06v0/vth0` | 37337 | `vth0='0.67314+nfet_06v0_vth0'` | 0.67314 V |
| `gf180mcu-models/pfet_06v0/lmin` | 38177 | `lmin=0.5e-6` | 0.5 um |
| `gf180mcu-models/pfet_06v0/vth0` | 38274 | `vth0='-0.8978+pfet_06v0_dvth0'` | -0.8978 V |

The nfet lines belong to `.model nfet_06v0.0` (line 37055, in `.lib nfet_06v0_t`), the pfet
lines to `.model pfet_06v0.0` (line 38091, in `.lib pfet_06v0_t`). Both libraries are
included by the `typical` section (`.lib typical`, lines 105 to 135), which sets the corner
offsets to zero: `.param nfet_06v0_vth0=0` (line 111), `.param nfet_06v0_tox=0`
(line 114) and `.param pfet_06v0_dvth0=0` (line 124). The values above are the typical
values with those offsets resolved; the other corners (`ff`, `ss`, `fs`, `sf`) shift them.

`lmin` is the lower length bound of the model bin, not a design rule. The nfet card has a
second bin, `.model nfet_06v0.1` (line 37393), with `lmin=6e-007` and `lmax=7e-007`; it is
not transcribed here.
