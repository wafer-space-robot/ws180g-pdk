# SPDX-License-Identifier: Apache-2.0
"""Run layouts through the generated KLayout DRC deck, in one engine process, with a cache.

`run_klayout_many(deck_dir, gds_files, out_dir, runner, process)`:

1. copies the three deck files (`<variant>.drc`, `<variant>_batch.drc`, `<variant>_checks.rb`)
   from `deck_dir` into `out_dir/deck/`;
2. derives the generated layers of every input with `ws180g_layergen.derive_file` into
   `out_dir/derived/<parent dir>__<stem>.gds` (a fixture `<out>/<rule>/<case>.gds` becomes
   `<rule>__<case>.gds`: flat and unique, since the batch deck names its reports by basename
   and refuses repeats);
3. looks each one up in `out_dir/cache/<key>.json`, where the key is the SHA-256 of the deck
   files and the derived layout's bytes (`cache_key`);
4. for the misses only, writes `out_dir/list.txt` (container paths) and starts **one**
   `klayout -b -r /work/out/deck/<variant>_batch.drc -rd list=... -rd out=/work/out/reports`
   through `runner(cmd, workdir=out_dir)`, which must mount `out_dir` at `/work/out`
   (`build/sandbox-run --workdir out_dir`);
5. parses each `.lyrdb` (`parse_lyrdb`), caches the result and returns `{input: DrcResult}`.

The runner is any callable `runner(cmd, workdir) -> CompletedProcess`: the tests pass their
`sandbox` fixture's `run`, the build its own wrapper of `build/sandbox-run`. Everything is
written under `out_dir`, with deterministic names and no timestamps.
"""

import hashlib
import json
import shutil
import subprocess
import xml.etree.ElementTree as ET
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ws180g_layergen.derive import derive_file
from ws180g_process.model import Process

#: Where the runner mounts `out_dir` in the container.
CONTAINER_OUT = "/work/out"
#: Part of every cache key; bump it when the meaning of a cached result changes (the parser,
#: the result fields), so old entries are not reused.
CACHE_VERSION = b"ws180g-run-klayout 1\n"

Runner = Callable[[list[str], Path], subprocess.CompletedProcess]


@dataclass(frozen=True)
class DrcResult:
    """The result of one layout: violations per rule id (category), and the number of
    categories the deck ran (every check writes its category, clean or not)."""

    violations: dict[str, int]
    categories_run: int

    def to_json(self) -> str:
        return json.dumps({"categories_run": self.categories_run,
                           "violations": dict(sorted(self.violations.items()))},
                          indent=1, sort_keys=True) + "\n"

    @classmethod
    def from_json(cls, text: str) -> "DrcResult":
        data = json.loads(text)
        return cls(violations={str(k): int(v) for k, v in data["violations"].items()},
                   categories_run=int(data["categories_run"]))


class DrcResults(dict[Path, DrcResult]):
    """`{input path: DrcResult}`, with `cache_hits`: how many came from the cache."""

    cache_hits: int = 0


def parse_lyrdb(path: Path) -> DrcResult:
    """The top-level `<categories><category><name>` of a KLayout report database are the
    categories run; every `<items><item>` counts one violation of its `<category>` (KLayout
    quotes names with dots: `'nw.w'`)."""
    root = ET.parse(path).getroot()
    categories = root.find("categories")
    names = [] if categories is None else [c.findtext("name") for c in categories.findall("category")]
    items = root.find("items")
    counts: Counter[str] = Counter()
    for item in [] if items is None else items.findall("item"):
        counts[(item.findtext("category") or "").strip().strip("'")] += 1
    return DrcResult(violations=dict(counts), categories_run=len(names))


def cache_key(deck_files: list[Path], derived: Path) -> str:
    """SHA-256 of the deck files (by name, in name order) and the derived layout's bytes."""
    h = hashlib.sha256(CACHE_VERSION)
    for path in sorted(deck_files, key=lambda p: p.name):
        data = path.read_bytes()
        h.update(f"deck {path.name} {len(data)}\n".encode())
        h.update(data)
    data = derived.read_bytes()
    h.update(f"gds {len(data)}\n".encode())
    h.update(data)
    return h.hexdigest()


def derived_name(gds: Path) -> str:
    """`<parent dir>__<stem>.gds`: the flat name of an input in `out_dir/derived/`."""
    return f"{gds.parent.name}__{gds.stem}.gds"


def _deck(deck_dir: Path) -> tuple[str, list[Path]]:
    """The variant and the three deck files of `deck_dir`."""
    batches = sorted(deck_dir.glob("*_batch.drc"))
    if len(batches) != 1:
        raise ValueError(f"{deck_dir}: expected one *_batch.drc, found {len(batches)}")
    variant = batches[0].name.removesuffix("_batch.drc")
    files = [deck_dir / f"{variant}.drc", batches[0], deck_dir / f"{variant}_checks.rb"]
    for f in files:
        if not f.is_file():
            raise ValueError(f"{deck_dir}: missing {f.name}")
    return variant, files


def run_klayout_many(deck_dir: Path, gds_files: list[Path], out_dir: Path, runner: Runner,
                     process: Process) -> DrcResults:
    """Run every layout of `gds_files` through the deck in `deck_dir` (one engine process
    for all cache misses) and return their results; see the module docstring."""
    variant, sources = _deck(deck_dir)
    names = [derived_name(g) for g in gds_files]
    repeated = sorted({n for n in names if names.count(n) > 1})
    if repeated:
        raise ValueError(f"inputs with the same derived name: {', '.join(repeated)}")

    deck, derived, reports, cache = (out_dir / d for d in ("deck", "derived", "reports", "cache"))
    for d in (deck, derived, reports, cache):
        d.mkdir(parents=True, exist_ok=True)
    deck_files = []
    for src in sources:
        shutil.copyfile(src, deck / src.name)
        deck_files.append(deck / src.name)

    results = DrcResults()
    misses: list[tuple[Path, str, Path]] = []  # (input, derived name, cache file)
    for gds, name in zip(gds_files, names, strict=True):
        derive_file(gds, derived / name, process, variant)
        entry = cache / f"{cache_key(deck_files, derived / name)}.json"
        if entry.is_file():
            results[gds] = DrcResult.from_json(entry.read_text(encoding="utf-8"))
            results.cache_hits += 1
        else:
            misses.append((gds, name, entry))
    if not misses:
        return _ordered(results, gds_files)

    for _, name, _ in misses:
        (reports / name).with_suffix(".lyrdb").unlink(missing_ok=True)
    (out_dir / "list.txt").write_text(
        "".join(f"{CONTAINER_OUT}/derived/{name}\n" for _, name, _ in misses), encoding="utf-8")
    cmd = ["klayout", "-b", "-r", f"{CONTAINER_OUT}/deck/{variant}_batch.drc",
           "-rd", f"list={CONTAINER_OUT}/list.txt", "-rd", f"out={CONTAINER_OUT}/reports"]
    done = runner(cmd, out_dir)
    if done.returncode != 0:
        raise RuntimeError(f"klayout exit {done.returncode}:\n{done.stdout[-4000:]}"
                           f"\n{done.stderr[-4000:]}")
    parsed = []
    for gds, name, entry in misses:
        report = (reports / name).with_suffix(".lyrdb")
        if not report.is_file():
            raise RuntimeError(f"klayout wrote no report for {gds} ({report})")
        parsed.append((gds, entry, parse_lyrdb(report)))
    for gds, entry, result in parsed:
        entry.write_text(result.to_json(), encoding="utf-8")
        results[gds] = result
    return _ordered(results, gds_files)


def _ordered(results: DrcResults, gds_files: list[Path]) -> DrcResults:
    """`results` in input order, keeping `cache_hits`."""
    out = DrcResults((g, results[g]) for g in gds_files)
    out.cache_hits = results.cache_hits
    return out


def run_klayout(deck_dir: Path, gds: Path, out_dir: Path, runner: Runner,
                process: Process) -> DrcResult:
    """Run one layout through the deck (`run_klayout_many` of one input)."""
    return run_klayout_many(deck_dir, [gds], out_dir, runner, process)[gds]
