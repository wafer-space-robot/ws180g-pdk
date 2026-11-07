<!-- SPDX-License-Identifier: Apache-2.0 -->
# MOSIS SCMOS design rules, revision 8.00 (`scmos8`)

The entries in `evidence/data/scmos8.toml` are transcribed from the MOSIS Scalable CMOS
(SCMOS) layout rules, revision 8.0 (cited as "SCMOS rev 8.00"), as mirrored for the UCSB
ECE 224A course:

- **Mirror:** <https://bears.ece.ucsb.edu/class/ece224a/scmos/scmos-main.html> (the index page)
- **Retrieved:** 2026-11-07
- **Licence:** the pages state no licence. They are **not redistributed**: they are not in this
  repository. Only the facts (rule numbers, lambda counts, the micron values derived from
  them) are recorded, each with a citation of its page, rule and column.

## Pages

`ws180g-import-scmos` fetches these pages into `tmp/scmos8/` (gitignored), records each
page's sha256 and the retrieval date under `[sources.scmos8]` in
`evidence/data/sources.toml`, and imports them. A test checks that the digests below match
the registry.

| Page | URL | Sections | sha256 |
|---|---|---|---|
| `main` | <https://bears.ece.ucsb.edu/class/ece224a/scmos/scmos-main.html> | index; Tables 2b and 2c (lambda mappings) | `f5fbe666cb20b53e794f7bf7a4a373b6a54a4087f1bfa09d65bc14bd77fd3d23` |
| `well` | <https://bears.ece.ucsb.edu/class/ece224a/scmos/scmos-well.html> | 1 | `35d1c3d5c9d93c6a75ead2d5767836e649ec3321d8ef1b67bf51a2d12283b11b` |
| `active` | <https://bears.ece.ucsb.edu/class/ece224a/scmos/scmos-active.html> | 2 | `faf1ca9e5b4de2a71849877cdae64137424bd205a8cbcd2ba15eef50cd170523` |
| `poly` | <https://bears.ece.ucsb.edu/class/ece224a/scmos/scmos-poly.html> | 3 | `c698ba89dfa92077edf4211e07c6b3f2362eaa9824d591174865309fd63bb6c7` |
| `select` | <https://bears.ece.ucsb.edu/class/ece224a/scmos/scmos-select.html> | 4 | `99dc4b5d0b708c1b0774a11d0f6e3f5d14e369fa019ed851e2827cc3ef659182` |
| `contact` | <https://bears.ece.ucsb.edu/class/ece224a/scmos/scmos-contact.html> | 5, 6 | `fd1251417b739346777976f55dc59f4977d0c9a46f9e937c621686ab6fc792fd` |
| `metal1` | <https://bears.ece.ucsb.edu/class/ece224a/scmos/scmos-metal1.html> | 7 | `44046510c8bd8be78e767f3a02438e83f7f8feff87425272d384a76971241960` |
| `metal2` | <https://bears.ece.ucsb.edu/class/ece224a/scmos/scmos-metal2.html> | 8 (via1), 9 | `a42519165f62601874a7cbe19c65eca37c971a00cb5e505ed4afd013561e2612` |
| `metal3` | <https://bears.ece.ucsb.edu/class/ece224a/scmos/scmos-metal3.html> | 14 (via2), 15 | `05912c6fc946d5b07d718fe7ce0f409a575a2cba9d49fcfa8efb2df8a45c5ae3` |
| `metal4` | <https://bears.ece.ucsb.edu/class/ece224a/scmos/scmos-metal4.html> | 21 (via3), 22 | `c7d0ca387bc5245e5a72a1efa142196c2fefc8e861702e3f3874dc97910b5191` |
| `metal5` | <https://bears.ece.ucsb.edu/class/ece224a/scmos/scmos-metal5.html> | 25 (via4), 26 | `76f9b8c68116828a8e8e354f3acd505e37a91f8a26995f8a493c328fdc87f493` |
| `metal6` | <https://bears.ece.ucsb.edu/class/ece224a/scmos/scmos-metal6.html> | 29 (via5), 30 | `fbacbc93816c59f58755f2e7c04700653c35ac3af01f545d55b65c9397204b07` |
| `glass` | <https://bears.ece.ucsb.edu/class/ece224a/scmos/scmos-glass.html> | 10 (overglass, microns) | `81d530968fddc37324666f211602ee797496eaab20c044b2f54e24b9205ade02` |
| `sblock` | <https://bears.ece.ucsb.edu/class/ece224a/scmos/scmos-sblock.html> | 20 (silicide block) | `23f0379452669226b2cd614d470bef9655021754fc645f9c16aa0121535f6a8a` |
| `thick-active` | <https://bears.ece.ucsb.edu/class/ece224a/scmos/scmos-thick-active.html> | 24 | `eba44f6483e1fc15b4fa6fde6f92ec27004c26a90e13954f29e161a1751ac143` |
| `dnw` | <https://bears.ece.ucsb.edu/class/ece224a/scmos/scmos-dnw.html> | 31 (deep n-well) | `669b38f73a72af615576ed0e7471c2b6c197c58c83fe91e9330f997f8981f543` |

`scmos-thickactive.html` redirects to `scmos-thick-active.html`; the page is named
`thick-active` here and in the citations.

## Lambda mappings

Rules are given in lambda; an entry's `value` in um is the lambda count times the lambda of
the TSMC 0.18 um six-metal mapping on the index page, read from the page by the importer:

| Column | Technology code | Table | lambda (um) |
|---|---|---|---|
| `subm` | SCN6M_SUBM | 2b, SCMOS_SUBM-compatible mappings | 0.10 |
| `deep` | SCN6M_DEEP | 2c, SCMOS_DEEP-compatible mappings | 0.09 |
| `scmos` | none: no 0.18 um mapping | | |

`scmos` entries keep the lambda count (`lambda`) and have no `lambda_um`, `value` or `unit`.
On the metal pages the column group for the most metals (`3+`, `4+`, `5+`, `6+ Metal
Process`, `6 Metal Process`) is used. `n/a` gives no entry; a footnote `*` after a count is
ignored; an exact size `2x2` gives the count 2 and the kind `exact-size`. Section 10
(overglass) is in microns and every row is a guideline (`scmos8/10.<n>`, no column).

Three rules state a topology and carry no value, and give no entry: 14.5 (via2 over
contact), 20.6 (resistor in silicide block) and 24.6 (active inside or outside thick
active).

## Use in ws180g

ws180g has no exact SCMOS counterpart for its top via and top metal: `v4` and `mtop` are
compared with the six-metal top via and top metal (sections 29 and 30) and with via4
(section 25) where like for like.

## Refresh

```
uv run ws180g-import-scmos            # fetch, record sha256 and date, import
uv run ws180g-import-scmos --offline  # re-import tmp/scmos8/, checked against the sha256
```

After a fetch that changes a page, update the table above from `sources.toml`.
