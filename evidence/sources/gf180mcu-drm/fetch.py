# SPDX-License-Identifier: Apache-2.0
"""Vendor the GF180MCU design-manual tables from fossi-foundation/gf180mcu-pdk.

Resolves the branch (default `main`) to a commit, downloads every CSV of
`docs/physical_verification/design_manual/tables_clear/` at that commit and the repository's
LICENSE into this directory, byte for byte, and rewrites the `[sources.gf180mcu-drm]` table of
`evidence/data/sources.toml` with the commit, the retrieval date and each file's sha256.

Run: uv run --no-project python -I evidence/sources/gf180mcu-drm/fetch.py [branch-or-commit]
Standard library only.
"""

import datetime
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

REPO = "fossi-foundation/gf180mcu-pdk"
TABLES = "docs/physical_verification/design_manual/tables_clear"
HERE = Path(__file__).resolve().parent
SOURCES_TOML = HERE.parents[1] / "data" / "sources.toml"
SOURCE_ID = "gf180mcu-drm"
TITLE = "GF180MCU design manual tables (gf180mcu-pdk, tables_clear)"


def _get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "ws180g-fetch"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def _source_table(commit: str, retrieved: str, digests: dict[str, str]) -> str:
    url = f"https://github.com/{REPO}/tree/{commit}/{TABLES}"
    lines = [
        f"[sources.{SOURCE_ID}]",
        f'title = "{TITLE}"',
        f'url = "{url}"',
        'licence = "Apache-2.0"',
        f'commit = "{commit}"',
        f"retrieved = {retrieved}",
        "transcribed = true",
        "vendored = true",
        "public = true",
        "",
        f"[sources.{SOURCE_ID}.sha256]",
    ]
    lines += [f'"{name}" = "{digests[name]}"' for name in sorted(digests)]
    return "\n".join(lines) + "\n"


def _replace_source(text: str, table: str) -> str:
    """Replace this source's tables in `sources.toml`, keeping every other source."""
    kept: list[str] = []
    skipping = False
    for line in text.splitlines(keepends=True):
        if line.startswith("["):
            name = line.strip().strip("[]")
            skipping = name == f"sources.{SOURCE_ID}" or name.startswith(f"sources.{SOURCE_ID}.")
        if not skipping:
            kept.append(line)
    body = "".join(kept).rstrip("\n")
    return (body + "\n\n" if body else "") + table


def main(ref: str = "main") -> None:
    commit = json.loads(_get(f"https://api.github.com/repos/{REPO}/commits/{ref}"))["sha"]
    listing = json.loads(_get(
        f"https://api.github.com/repos/{REPO}/contents/{TABLES}?ref={commit}"))
    names = sorted(item["name"] for item in listing
                   if item["type"] == "file" and item["name"].endswith(".csv"))
    for old in HERE.glob("*.csv"):
        old.unlink()
    digests: dict[str, str] = {}
    raw = f"https://raw.githubusercontent.com/{REPO}/{commit}"
    for name in names:
        data = _get(f"{raw}/{TABLES}/{name}")
        (HERE / name).write_bytes(data)
        digests[name] = hashlib.sha256(data).hexdigest()
    (HERE / "LICENSE").write_bytes(_get(f"{raw}/LICENSE"))
    retrieved = datetime.date.today().isoformat()
    header = "# SPDX-License-Identifier: Apache-2.0\n"
    text = SOURCES_TOML.read_text() if SOURCES_TOML.exists() else header
    SOURCES_TOML.write_text(_replace_source(text, _source_table(commit, retrieved, digests)))
    print(f"{len(names)} tables at {commit}, retrieved {retrieved}")


if __name__ == "__main__":
    main(*sys.argv[1:])
