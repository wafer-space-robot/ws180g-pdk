# SPDX-License-Identifier: Apache-2.0
"""Sphinx configuration of the ws180g-pdk documentation.

Build: `uv run ws180g-build --no-container` (writes `docs/generated/`), then
`uv run sphinx-build -W docs out/docs`. The pages are Markdown (MyST). `rules.md` and
`evidence.md` include the generated pages; the design specs and plans under `superpowers/`
are working documents, linked on GitHub, not built here.
"""

project = "ws180g-pdk"
author = "wafer.space"
copyright = "wafer.space contributors, Apache-2.0"

extensions = ["myst_parser"]
source_suffix = {".md": "markdown"}
root_doc = "index"
# generated/ holds pages included by rules.md and evidence.md, not pages of their own.
exclude_patterns = ["superpowers/**", "_build", "generated/**"]

html_theme = "furo"
html_title = "ws180g-pdk"
# No "last updated" stamp and no source links: the output depends only on the sources.
html_last_updated_fmt = None
html_show_sourcelink = False
