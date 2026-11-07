# SPDX-License-Identifier: Apache-2.0
# Adapted from mithro/gf180-tcad docker/base/probe_versions.py (Apache-2.0)
"""Print the provenance of the ws180g-pdk base image as JSON (sorted keys, trailing newline).

Runs inside the image, through build/sandbox-run:

    build/sandbox-run --workdir tmp/sandbox -- python /work/src/docker/probe_versions.py \
        > docker/versions.json

Tool versions come from the tools themselves (`klayout -v`, `magic --version`, `netgen -batch
quit`, `ngspice --version`); /foss/pdks/versions.txt is stale for the tools (it says KLayout
0.30.5 where the binary is 0.30.12) and names no open_pdks commit, so that commit is read from the
PDK's own `.config/nodeinfo.json`. Standard library only; no timestamps, hostnames or host paths.
"""

import json
import os
import platform
import re
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path


def _tool_output(*cmd: str) -> str:
    res = subprocess.run(cmd, capture_output=True, text=True, check=True,
                         stdin=subprocess.DEVNULL)
    return res.stdout + res.stderr


def _match(pattern: str, text: str, what: str) -> str:
    m = re.search(pattern, text, re.MULTILINE)
    if not m:
        sys.exit(f"probe_versions: cannot parse the {what} version from:\n{text}")
    return m.group(1)


def _open_pdks(pdk_root: Path, variant: str) -> str:
    listed = (pdk_root / "versions.txt").read_text(encoding="utf-8")
    m = re.search(r"^open_pdks\s+(\S+)", listed, re.MULTILINE)
    if m:
        return m.group(1)
    nodeinfo = json.loads((pdk_root / variant / ".config" / "nodeinfo.json")
                          .read_text(encoding="utf-8"))
    return nodeinfo["commit"]["open_pdks"]


def probe() -> dict[str, str]:
    pdk_root = Path(os.environ["PDK_ROOT"])
    variant = os.environ["PDK"]
    return {
        "base_image": os.environ["WS180G_BASE_IMAGE"],
        "python": platform.python_version(),
        "klayout": _match(r"^KLayout (\S+)", _tool_output("klayout", "-v"), "KLayout"),
        "klayout_python": version("klayout"),
        "pydantic": version("pydantic"),
        "magic": _match(r"^(\d\S*)$", _tool_output("magic", "--version"), "Magic"),
        "netgen": _match(r"\ANetgen (\S+)", _tool_output("netgen", "-batch", "quit"), "netgen"),
        "ngspice": _match(r"\bngspice-(\S+)", _tool_output("ngspice", "--version"), "ngspice"),
        "pdk": variant,
        "open_pdks": _open_pdks(pdk_root, variant),
    }


def main() -> None:
    sys.stdout.write(json.dumps(probe(), indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
