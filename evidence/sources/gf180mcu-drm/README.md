<!-- SPDX-License-Identifier: Apache-2.0 -->
# GF180MCU design-manual tables (`gf180mcu-drm`)

The 85 `*.csv` files here are the rule tables of the GF180MCU design manual as published in
the open PDK, vendored byte for byte:

- **Source:** <https://github.com/fossi-foundation/gf180mcu-pdk>, directory
  `docs/physical_verification/design_manual/tables_clear/`
- **Commit:** `25ed9c64b64b8e1b93cc4d2d5cade4cd82383a9a` (branch `main` on the retrieval date)
- **Licence:** Apache-2.0; the repository's licence is copied unchanged to `LICENSE`
- **Retrieved:** 2026-11-07

The files are not edited, even where a cell is odd (an unquoted comma in `16_Poly2_42.csv`
row PL.12, Markdown escapes such as `a\)` and `\*`); the importer copes with them. The commit,
the retrieval date and each file's sha256 are recorded under `[sources.gf180mcu-drm]` in
`evidence/data/sources.toml`, and a test checks the digests.

To refresh (rewrites the CSVs, `LICENSE` and the registry entry):

```
uv run --no-project python -I evidence/sources/gf180mcu-drm/fetch.py [branch-or-commit]
uv run ws180g-import-gf180mcu
```

The second command regenerates `evidence/data/gf180mcu-drm.toml` and prints the tables it
skips as not being rule tables (process identification, metal levels, layer and device
lists, ESD performance, electromigration tables, ...).
