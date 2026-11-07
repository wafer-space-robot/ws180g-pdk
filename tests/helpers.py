# SPDX-License-Identifier: Apache-2.0
"""Test helpers."""

import re
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


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
    """Rewrite one `key = value` line; `keys[:-1]` name the `[table]`, `keys[-1]` the key.

    Single-line scalar values only (no multi-line arrays or inline tables); a string value
    containing `#` is not supported.
    """
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


def evidence_dir_with(entries: list[dict], sources: dict) -> Path:
    """A fresh evidence data directory holding `sources.toml` and `entries.toml`.

    `sources` maps a source id to its table; each entry is one `[[entry]]` table and gets
    `rule`, `text` and `cite` filled in when it lacks them. The directory lies under the
    repository's `tmp/`."""
    root = REPO_ROOT / "tmp" / "evidence-dirs"
    root.mkdir(parents=True, exist_ok=True)
    out = Path(tempfile.mkdtemp(dir=root))
    lines: list[str] = []
    for name, table in sources.items():
        lines.append(f"[sources.{name}]")
        lines += [f"{k} = {_literal(v)}" for k, v in table.items()]
        lines.append("")
    (out / "sources.toml").write_text("\n".join(lines))
    lines = []
    for entry in entries:
        filled = {"rule": entry["id"].split("/")[1], "text": "", "cite": "test"} | entry
        lines.append("[[entry]]")
        lines += [f"{k} = {_literal(v)}" for k, v in filled.items()]
        lines.append("")
    (out / "entries.toml").write_text("\n".join(lines))
    return out
