# SPDX-License-Identifier: Apache-2.0
"""Private-data checker: the tooling half of the rule that the repository holds only public
facts with public citations.

`check_private(root)` runs four checks and returns every problem as a `Finding`:

1. Evidence registry (`evidence/data`): every entry's `source` is registered in
   `sources.toml`, and every registered source has a non-empty `url` and sets
   `public = true` explicitly.
2. Process description (`process/data/ws180g`): every `provenance` is one of the allowed
   values (`ws180g_process.model.Provenance`), and every `evidence` or `composed_of` id that
   looks like an evidence id (contains `/`) exists in the evidence set.
3. Text scan: every git-tracked text file outside `tmp/` (binaries are skipped by a null-byte
   sniff) is searched for `PATTERNS`, case-insensitive. `build/private-allow.txt` lists the
   allowed lines as `<path glob>: <exact line text>` (`#` starts a comment line); an entry
   suppresses only a line whose text equals it exactly in a file its glob matches
   (`fnmatch`, where `*` also matches `/`). An entry that matches no line, or a line not of
   that form, is itself a finding. The entry lines of the allow-list are not scanned; its
   comment lines are.
4. Vendored files: for every source with `vendored = true`, each file of its `sha256` table
   exists under `evidence/sources/<source>/` and has that sha256.

The scan reads the files `git ls-files` lists (the index), with their working-tree content.
"""

import argparse
import fnmatch
import hashlib
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import get_args

from ws180g_process.model import Provenance

# Not configurable: the allow-list can exempt exact lines, never change what is searched for.
PATTERNS = [re.compile(p, re.IGNORECASE) for p in (
    r'\bprovenance\s*=\s*"private"',
    r"\bnda\b",
    r"\bconfidential\b",
    r"\bproprietary\b",
    r"\binternal use only\b",
)]

ALLOWED_PROVENANCE = frozenset(get_args(Provenance))
EVIDENCE_DATA = "evidence/data"
EVIDENCE_SOURCES = "evidence/sources"
PROCESS_DATA = "process/data/ws180g"
ALLOW_LIST = "build/private-allow.txt"
SNIFF_BYTES = 8192


@dataclass(frozen=True)
class Finding:
    """A problem at `line` (1-based, `None` for the whole file) of `path` (relative to the
    repository root, `/`-separated)."""

    path: str
    line: int | None
    reason: str

    def __str__(self) -> str:
        where = self.path if self.line is None else f"{self.path}:{self.line}"
        return f"{where}: {self.reason}"


def check_private(repo_root: Path) -> list[Finding]:
    """Run the four checks on the repository at `repo_root`; an empty list means clean."""
    root = Path(repo_root)
    findings: list[Finding] = []
    sources, entry_ids = _check_evidence(root, findings)
    _check_process(root, entry_ids, findings)
    _check_vendored(root, sources, findings)
    _check_text(root, findings)
    return sorted(findings, key=lambda f: (f.path, f.line or 0, f.reason))


def _rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _line_of(text: str, needle: str | re.Pattern) -> int | None:
    for number, line in enumerate(text.splitlines(), start=1):
        if (needle.search(line) if isinstance(needle, re.Pattern) else needle in line):
            return number
    return None


def _toml(root: Path, path: Path, findings: list[Finding]) -> tuple[dict, str] | None:
    try:
        text = path.read_text(encoding="utf-8")
        return tomllib.loads(text), text
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        findings.append(Finding(_rel(root, path), None, f"cannot read: {exc}"))
        return None


def _check_evidence(root: Path, findings: list[Finding]) -> tuple[dict, set[str]]:
    data = root / EVIDENCE_DATA
    registry = data / "sources.toml"
    if not registry.is_file():
        findings.append(Finding(f"{EVIDENCE_DATA}/sources.toml", None, "missing"))
        return {}, set()
    loaded = _toml(root, registry, findings)
    sources: dict = {}
    if loaded is not None:
        table, text = loaded
        sources = {k: v for k, v in table.get("sources", {}).items() if isinstance(v, dict)}
        rel = _rel(root, registry)
        for name, source in sources.items():
            line = _line_of(text, f"[sources.{name}]")
            url = source.get("url")
            if not isinstance(url, str) or not url.strip():
                findings.append(Finding(rel, line, f"source {name} has no url"))
            if source.get("public") is not True:
                findings.append(Finding(
                    rel, line, f"source {name} does not set public = true"))
    entry_ids: set[str] = set()
    for path in sorted(data.glob("*.toml")):
        if path == registry:
            continue
        loaded = _toml(root, path, findings)
        if loaded is None:
            continue
        table, text = loaded
        entries = table.get("entry", [])
        for entry in entries if isinstance(entries, list) else []:
            if not isinstance(entry, dict):
                continue
            entry_id = str(entry.get("id", ""))
            entry_ids.add(entry_id)
            source = entry.get("source")
            if source not in sources:
                findings.append(Finding(
                    _rel(root, path), _line_of(text, f'id = "{entry_id}"'),
                    f"entry {entry_id} names unregistered source {source}"))
    return sources, entry_ids


def _walk(node: object, dotted: str):
    """Yield `(dotted path, table)` for every table under `node`."""
    if isinstance(node, dict):
        yield dotted, node
        for key, value in node.items():
            yield from _walk(value, f"{dotted}.{key}" if dotted else str(key))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _walk(value, f"{dotted}[{index}]")


def _check_process(root: Path, entry_ids: set[str], findings: list[Finding]) -> None:
    data = root / PROCESS_DATA
    if not data.is_dir():
        findings.append(Finding(PROCESS_DATA, None, "missing"))
        return
    for path in sorted(data.glob("*.toml")):
        loaded = _toml(root, path, findings)
        if loaded is None:
            continue
        table, text = loaded
        rel = _rel(root, path)
        for dotted, node in _walk(table, ""):
            if "provenance" in node and node["provenance"] not in ALLOWED_PROVENANCE:
                value = node["provenance"]
                line = _line_of(text, re.compile(
                    rf'^\s*provenance\s*=\s*"{re.escape(str(value))}"'))
                findings.append(Finding(
                    rel, line, f"{dotted}: provenance '{value}' is not one of "
                    f"{', '.join(sorted(ALLOWED_PROVENANCE))}"))
            for key in ("evidence", "composed_of"):
                ids = node.get(key)
                for cited in ids if isinstance(ids, list) else []:
                    if isinstance(cited, str) and "/" in cited and cited not in entry_ids:
                        findings.append(Finding(
                            rel, _line_of(text, f'"{cited}"'),
                            f"{dotted}.{key}: {cited} is not in the evidence set"))


def _check_vendored(root: Path, sources: dict, findings: list[Finding]) -> None:
    for name, source in sources.items():
        if source.get("vendored") is not True:
            continue
        hashes = source.get("sha256", {})
        if not hashes:
            findings.append(Finding(
                f"{EVIDENCE_DATA}/sources.toml", None,
                f"vendored source {name} lists no sha256"))
        for filename, expected in hashes.items():
            path = root / EVIDENCE_SOURCES / name / filename
            rel = f"{EVIDENCE_SOURCES}/{name}/{filename}"
            if not path.is_file():
                findings.append(Finding(rel, None, f"vendored file of {name} is missing"))
                continue
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual != expected:
                findings.append(Finding(
                    rel, None, f"sha256 {actual} differs from the registry's {expected}"))


@dataclass
class _Allow:
    line: int
    glob: str
    text: str
    used: bool = False


def _read_allow(root: Path, findings: list[Finding]) -> list[_Allow]:
    path = root / ALLOW_LIST
    if not path.is_file():
        return []
    allows: list[_Allow] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip() or line.startswith("#"):
            continue
        glob, sep, text = line.partition(": ")
        if not sep or not glob.strip() or not text:
            findings.append(Finding(
                ALLOW_LIST, number, "not of the form <path glob>: <exact line text>"))
            continue
        allows.append(_Allow(number, glob, text))
    return allows


def _tracked(root: Path, findings: list[Finding]) -> list[str]:
    run = subprocess.run(["git", "-C", str(root), "ls-files", "-z"],
                         capture_output=True, check=False)
    if run.returncode != 0:
        findings.append(Finding(".", None, f"git ls-files failed: "
                                f"{run.stderr.decode(errors='replace').strip()}"))
        return []
    return sorted({p for p in run.stdout.decode().split("\0") if p})


def _check_text(root: Path, findings: list[Finding]) -> None:
    allows = _read_allow(root, findings)
    entry_lines = {a.line for a in allows}
    for rel in _tracked(root, findings):
        if rel.startswith("tmp/"):
            continue
        path = root / rel
        if not path.is_file():
            continue
        data = path.read_bytes()
        if b"\0" in data[:SNIFF_BYTES]:
            continue
        for number, line in enumerate(data.decode("utf-8", errors="replace").splitlines(),
                                      start=1):
            if rel == ALLOW_LIST and number in entry_lines:
                continue
            hits = [p.pattern for p in PATTERNS if p.search(line)]
            if not hits:
                continue
            allow = next((a for a in allows
                          if a.text == line and fnmatch.fnmatchcase(rel, a.glob)), None)
            if allow is not None:
                allow.used = True
                continue
            findings.append(Finding(rel, number, f"matches {' '.join(hits)}"))
    for allow in allows:
        if not allow.used:
            findings.append(Finding(ALLOW_LIST, allow.line, "entry matches no line"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ws180g-check-private", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    default = Path(__file__).resolve().parents[3]
    parser.add_argument("root", nargs="?", type=Path, default=default)
    args = parser.parse_args(argv)
    findings = check_private(args.root)
    for finding in findings:
        print(finding)
    if findings:
        print(f"ws180g-check-private: {len(findings)} finding(s)", file=sys.stderr)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
