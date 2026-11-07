<!-- SPDX-License-Identifier: Apache-2.0 -->
# X-FAB XC018 process data sheet, rev 3.0 (`xc018`)

The entries in `evidence/data/xc018.toml` are transcribed by hand from the public X-FAB
XC018 0.18 µm process data sheet, revision 3.0 (2008), cited as "XC018 data sheet rev 3.0":

- **URL:** <https://datasheet.datasheetarchive.com/originals/crawler/xfab.com/a3edb8140abfda7a83325589538d6415.pdf>
- **Retrieved:** 2026-11-07
- **Licence:** the data sheet states no licence for redistribution. It is **not
  redistributed**: the PDF is not in this repository. Only the facts are recorded, each
  with its page, table, row and column. To check them, download the PDF into
  `tmp/ref/xfab/` (gitignored) and compare its digest with the one below.

| File | sha256 |
|---|---|
| `xc018_datasheet.pdf` | `f7cc3687bbf409fd50cf53f7502a20dfbed9aef43da634f3e01e08ed1a4db6cf` |

## What was transcribed

- **Page 5, "Basic Design Rules"**: the Width [µm] and Spacing [µm] of all ten rows
  (N-Well, Active Area, Poly-Silicon Gate, Poly-Silicon Resistor, Contact, Metal 1,
  Via 1/2/3/4, Metal 2/3/4/5, Top Via, Top Metal), as `xc018/<mask>/width` and
  `xc018/<mask>/spacing`. Widths are `min-width`, except Contact, Via 1/2/3/4 and Top Via,
  whose width is the cut size (`exact-size`); spacings are `min-space`.
- **Page 5, "Device Parameters", Active Devices (typical data), MOS Transistors**: the
  |VT| [V] of the 5.0 V NMOS `ne5` (0.77) and 5.0 V PMOS `pe5` (0.84), both in module
  MOS5LP (the MOS5ST rows print "-"), as `xc018/<device>/vt`. The value is the magnitude
  as printed.
- **Page 7, "Device Parameters (continued)", Passive Devices (typical data), Resistors &
  Conductors**: the RS [Ω/□] of `rm1`, `rm2`, `rm3`, `rm4`, `rm5`, `rmtp`, `rmtpl` and
  `rpp1k1`, as `xc018/<device>/rs` in `ohm/sq`. Row labels are kept as printed, including
  the sheet's spelling "Thick Matel" for `rmtpl`.

## What was not transcribed, and why

The page 7 column "Thicknes or junc. depth [µm]" is **not** transcribed. Its metal values
are physically inconsistent with the sheet resistances printed beside them: the implied
resistivity (RS × thickness) is 1.6 µΩ·cm for Metal 1 (0.095 Ω/□ × 0.17 µm), 1.9 µΩ·cm for
Metal 2 (0.085 × 0.22) and 1.3 µΩ·cm for Top Metal (0.037 × 0.35), all below that of bulk
aluminium (about 2.7 µΩ·cm) and, for Top Metal, below that of copper. Either the thickness
or the sheet-resistance column is wrong, and taking the thicknesses would contradict the
top-metal thickness range the process description owns. The sheet resistances are kept.

Every other table of the sheet (varactors, capacitors, other devices) is left for a later
transcription if needed.
