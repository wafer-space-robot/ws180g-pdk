# SPDX-License-Identifier: Apache-2.0
"""Test helpers. `evidence_dir_with` arrives with the evidence package (Task 4)."""

import re
from pathlib import Path


def _literal(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    raise TypeError(f"no TOML literal for {type(value).__name__}")


def set_toml(path: Path, keys: list[str], value: object) -> None:
    """Rewrite one `key = value` line; `keys[:-1]` name the `[table]`, `keys[-1]` the key."""
    *tables, key = keys
    lines = path.read_text().splitlines(keepends=True)
    header = re.compile(r"^\s*\[([^\[\]]+)\]\s*(#.*)?$")
    in_table = not tables
    want = ".".join(tables)
    pattern = re.compile(rf"^(\s*{re.escape(key)}\s*=\s*)[^#\n]*?(\s*(#.*)?)$")
    for i, line in enumerate(lines):
        stripped = line.rstrip("\r\n")
        h = header.match(stripped)
        if h:
            in_table = h.group(1).strip() == want
            continue
        m = pattern.match(stripped)
        if in_table and m:
            ending = line[len(stripped):]
            lines[i] = f"{m.group(1)}{_literal(value)}{m.group(2)}{ending}"
            path.write_text("".join(lines))
            return
    raise KeyError(".".join(keys))
