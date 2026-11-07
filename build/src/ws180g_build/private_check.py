# SPDX-License-Identifier: Apache-2.0
"""Private-data checker: the tooling half of the rule that the repository holds only public
facts with public citations.

`check_private(root, cached=False)` runs four checks and returns every problem as a
`Finding`:

1. Evidence registry (`evidence/data`): every entry's `source` is registered in
   `sources.toml`, and every registered source has a non-empty `url` and sets
   `public = true` explicitly.
2. Process description (`process/data/ws180g`): every `provenance` is one of the allowed
   values (`ws180g_process.model.Provenance`), and every `evidence` or `composed_of` id that
   looks like an evidence id (contains `/`) exists in the evidence set.
3. Text scan: every git-tracked text file outside `tmp/` is searched for `PATTERNS`,
   case-insensitive. A file starting with a UTF-16 byte-order mark is decoded as UTF-16; any
   other file with a null byte in its first 8 KiB is binary and skipped; the rest is decoded
   as UTF-8. `build/private-allow.txt` lists the allowed lines as
   `<path glob>: <exact line text>`, each directly below a `#` comment line saying why; an
   entry suppresses only a line whose text equals it exactly in a file its glob matches
   (`fnmatch`, where `*` also matches `/`). An entry that matches no line, has no comment
   above it, or a line not of that form, is itself a finding. The entry lines of the
   allow-list are not scanned; its comment lines are.
4. Vendored files: for every source with `vendored = true`, each file of its `sha256` table
   exists under `evidence/sources/<source>/` and has that sha256.

By default every check reads the working tree (the scan covers the files `git ls-files`
lists). With `cached=True` (`--cached`, what the pre-commit hook uses) every check reads the
staged blobs instead, so what is checked is exactly what the commit will hold.
"""

import argparse
import codecs
import fnmatch
import hashlib
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
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
# Git file modes that hold no file content (a submodule commit).
GITLINK = "160000"


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


class _Tree:
    """The files the checks read: the working tree, or with `cached` the staged blobs.

    `read(rel)` gives a file's bytes or `None`; `listdir(dir)` the files directly in `dir`;
    `tracked()` the files the text scan covers, with their bytes."""

    def __init__(self, root: Path, cached: bool, findings: list[Finding]) -> None:
        self.root = root
        self.cached = cached
        self.blobs: dict[str, bytes] = {}
        if cached:
            self.blobs = _staged_blobs(root, findings)
            self.paths = sorted(self.blobs)
        else:
            self.paths = _tracked(root, findings)

    def read(self, rel: str) -> bytes | None:
        if self.cached:
            return self.blobs.get(rel)
        path = self.root / rel
        return path.read_bytes() if path.is_file() else None

    def listdir(self, directory: str) -> list[str]:
        if self.cached:
            return sorted(p for p in self.blobs if str(PurePosixPath(p).parent) == directory)
        base = self.root / directory
        if not base.is_dir():
            return []
        return sorted(f"{directory}/{p.name}" for p in base.iterdir() if p.is_file())

    def tracked(self):
        for rel in self.paths:
            data = self.read(rel)
            if data is not None:
                yield rel, data


def _git(root: Path, args: list[str], findings: list[Finding],
         stdin: bytes | None = None) -> bytes | None:
    run = subprocess.run(["git", "-C", str(root), *args], input=stdin,
                         capture_output=True, check=False)
    if run.returncode != 0:
        findings.append(Finding(".", None, f"git {args[0]} failed: "
                                f"{run.stderr.decode(errors='replace').strip()}"))
        return None
    return run.stdout


def _tracked(root: Path, findings: list[Finding]) -> list[str]:
    out = _git(root, ["ls-files", "-z"], findings)
    return [] if out is None else sorted({p for p in out.decode().split("\0") if p})


def _staged_blobs(root: Path, findings: list[Finding]) -> dict[str, bytes]:
    """Every stage-0 file of the index with its staged bytes (`git cat-file --batch`)."""
    out = _git(root, ["ls-files", "-s", "-z"], findings)
    if not out:
        return {}
    staged: list[tuple[str, str]] = []
    for record in out.decode().split("\0"):
        if not record:
            continue
        meta, _, path = record.partition("\t")
        mode, sha, stage = meta.split()
        if stage == "0" and mode != GITLINK:
            staged.append((path, sha))
    if not staged:
        return {}
    batch = _git(root, ["cat-file", "--batch"], findings,
                 stdin="".join(f"{sha}\n" for _, sha in staged).encode())
    if batch is None:
        return {}
    blobs: dict[str, bytes] = {}
    pos = 0
    for path, sha in staged:
        end = batch.index(b"\n", pos)
        header = batch[pos:end].decode().split()
        if len(header) != 3 or header[0] != sha:
            findings.append(Finding(path, None, f"cannot read staged blob {sha}"))
            return blobs
        size = int(header[2])
        blobs[path] = batch[end + 1:end + 1 + size]
        pos = end + 1 + size + 1
    return blobs


def check_private(repo_root: Path, cached: bool = False) -> list[Finding]:
    """Run the four checks on the repository at `repo_root` (on its index with `cached`);
    an empty list means clean."""
    findings: list[Finding] = []
    tree = _Tree(Path(repo_root), cached, findings)
    sources, entry_ids = _check_evidence(tree, findings)
    _check_process(tree, entry_ids, findings)
    _check_vendored(tree, sources, findings)
    _check_text(tree, findings)
    return sorted(set(findings), key=lambda f: (f.path, f.line or 0, f.reason))


def _line_of(text: str, needle: str | re.Pattern) -> int | None:
    for number, line in enumerate(text.splitlines(), start=1):
        if (needle.search(line) if isinstance(needle, re.Pattern) else needle in line):
            return number
    return None


def _toml(tree: _Tree, rel: str, findings: list[Finding]) -> tuple[dict, str] | None:
    data = tree.read(rel)
    if data is None:
        findings.append(Finding(rel, None, "missing"))
        return None
    try:
        text = data.decode("utf-8")
        return tomllib.loads(text), text
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        findings.append(Finding(rel, None, f"cannot read: {exc}"))
        return None


def _check_evidence(tree: _Tree, findings: list[Finding]) -> tuple[dict, set[str]]:
    registry = f"{EVIDENCE_DATA}/sources.toml"
    loaded = _toml(tree, registry, findings)
    sources: dict = {}
    if loaded is not None:
        table, text = loaded
        sources = {k: v for k, v in table.get("sources", {}).items() if isinstance(v, dict)}
        for name, source in sources.items():
            line = _line_of(text, f"[sources.{name}]")
            url = source.get("url")
            if not isinstance(url, str) or not url.strip():
                findings.append(Finding(registry, line, f"source {name} has no url"))
            if source.get("public") is not True:
                findings.append(Finding(
                    registry, line, f"source {name} does not set public = true"))
    entry_ids: set[str] = set()
    for rel in tree.listdir(EVIDENCE_DATA):
        if rel == registry or not rel.endswith(".toml"):
            continue
        loaded = _toml(tree, rel, findings)
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
                    rel, _line_of(text, f'id = "{entry_id}"'),
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


def _check_process(tree: _Tree, entry_ids: set[str], findings: list[Finding]) -> None:
    files = [rel for rel in tree.listdir(PROCESS_DATA) if rel.endswith(".toml")]
    if not files:
        findings.append(Finding(PROCESS_DATA, None, "missing"))
    for rel in files:
        loaded = _toml(tree, rel, findings)
        if loaded is None:
            continue
        table, text = loaded
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


def _check_vendored(tree: _Tree, sources: dict, findings: list[Finding]) -> None:
    for name, source in sources.items():
        if source.get("vendored") is not True:
            continue
        hashes = source.get("sha256", {})
        if not hashes:
            findings.append(Finding(
                f"{EVIDENCE_DATA}/sources.toml", None,
                f"vendored source {name} lists no sha256"))
        for filename, expected in hashes.items():
            rel = f"{EVIDENCE_SOURCES}/{name}/{filename}"
            data = tree.read(rel)
            if data is None:
                findings.append(Finding(rel, None, f"vendored file of {name} is missing"))
                continue
            actual = hashlib.sha256(data).hexdigest()
            if actual != expected:
                findings.append(Finding(
                    rel, None, f"sha256 {actual} differs from the registry's {expected}"))


@dataclass
class _Allow:
    line: int
    glob: str
    text: str
    used: bool = False


def _read_allow(tree: _Tree, findings: list[Finding]) -> list[_Allow]:
    data = tree.read(ALLOW_LIST)
    if data is None:
        return []
    allows: list[_Allow] = []
    previous = ""
    for number, line in enumerate(data.decode("utf-8", errors="replace").splitlines(),
                                  start=1):
        above, previous = previous, line
        if not line.strip() or line.startswith("#"):
            continue
        glob, sep, text = line.partition(": ")
        if not sep or not glob.strip() or not text:
            findings.append(Finding(
                ALLOW_LIST, number, "not of the form <path glob>: <exact line text>"))
            continue
        if not above.startswith("#"):
            findings.append(Finding(
                ALLOW_LIST, number, "entry has no # comment on the line above saying why"))
        allows.append(_Allow(number, glob, text))
    return allows


def _decode(data: bytes) -> str | None:
    """The text of a file, or `None` for a binary file."""
    if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return data.decode("utf-16", errors="replace")
    if b"\0" in data[:SNIFF_BYTES]:
        return None
    return data.decode("utf-8", errors="replace")


def _check_text(tree: _Tree, findings: list[Finding]) -> None:
    allows = _read_allow(tree, findings)
    entry_lines = {a.line for a in allows}
    for rel, data in tree.tracked():
        if rel.startswith("tmp/"):
            continue
        text = _decode(data)
        if text is None:
            continue
        for number, line in enumerate(text.splitlines(), start=1):
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
    parser.add_argument("--cached", action="store_true",
                        help="check the staged blobs instead of the working tree")
    parser.add_argument("root", nargs="?", type=Path, default=default)
    args = parser.parse_args(argv)
    findings = check_private(args.root, cached=args.cached)
    for finding in findings:
        print(finding)
    if findings:
        print(f"ws180g-check-private: {len(findings)} finding(s)", file=sys.stderr)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
