# SPDX-License-Identifier: Apache-2.0
"""Run with `klayout -b -r check_tech.py -rd lyt=<file.lyt>`: load the technology and print
the number of layer-map entries as `layers=<n>`."""

from klayout import db

tech = db.Technology()
tech.load(lyt)  # noqa: F821  (`lyt` is injected by `-rd lyt=...`)
options = tech.load_layout_options
layer_map = options.layer_map
print(f"layers={len(layer_map.to_string().splitlines())}")
