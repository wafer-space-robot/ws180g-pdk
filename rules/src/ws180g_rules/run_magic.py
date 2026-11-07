# SPDX-License-Identifier: Apache-2.0
"""Run layouts through the generated Magic technology, in one Magic session, with a cache.

`run_magic_many(tech_dir, gds_files, out_dir, runner, process)` mirrors
`ws180g_rules.run_klayout.run_klayout_many`:

1. copies `<variant>.tech` and `<variant>.magicrc` (written by `ws180g_tech.magic`) from
   `tech_dir` into `out_dir/tech/`;
2. derives the generated layers of every input with `ws180g_layergen.derive_file` into
   `out_dir/derived/<parent dir>__<stem>.gds` (`run_klayout.derived_name`);
3. looks each one up in `out_dir/cache/<key>.json`, where the key is the SHA-256 of the two
   technology files and the derived layout's bytes (`cache_key`);
4. for the misses only, copies each derived layout to `out_dir/magic/c_<NNNN>.gds` with its
   cells renamed to `c_<NNNN>` (the top cell) and `c_<NNNN>_<k>`: every fixture's top cell is
   `test`, and one Magic session cannot hold two cells of one name (`out_dir/magic/names.txt`
   lists the derived name of each, one per line in index order); then writes
   `out_dir/script.tcl` and starts **one**
   `magic -dnull -noconsole -rcfile /work/out/tech/<variant>.magicrc < /work/out/script.tcl`
   through `runner(cmd, workdir=out_dir)`, which must mount `out_dir` at `/work/out`;
5. per layout the script does `gds read`, `load`, `select top cell`, grows the box by 20 um
   (`drc listall why` lists only the errors under the box, and an error area can lie just
   outside the cell's bounding box), `drc check`, `drc catchup`, and writes
   `out_dir/results/c_<NNNN>.txt`: `total <drc list count total>`, one line per entry of
   `drc listall why` (its number of error tiles, then the why string), and `end`;
6. parses each result (`parse_why`), caches it and returns `{input: DrcResult}`.

The rule id of an error is the text before the first `": "` of its why string (the technology
writes every why as `"<rule id>: ..."`); a why string without one (a Magic built-in error)
is kept whole as its own key, so it shows up in any comparison. `DrcResult.violations` counts
**error tiles**, not markers as KLayout does, so compare engines by the set of rule ids.
`DrcResult.categories_run` is the number of rule ids the technology's drc section checks.
The runner is any callable `runner(cmd, workdir) -> CompletedProcess`, as for KLayout.
Magic's output goes to `out_dir/magic.log`. Everything is written under `out_dir`, with
deterministic names and no timestamps.
"""

import hashlib
import re
import shutil
from collections import Counter
from pathlib import Path

import klayout.db as kdb
from ws180g_layergen.derive import derive_file
from ws180g_process.model import Process

from ws180g_rules.run_klayout import DrcResult, DrcResults, Runner, _ordered, derived_name

#: Where the runner mounts `out_dir` in the container.
CONTAINER_OUT = "/work/out"
#: Part of every cache key; bump it when the meaning of a cached result changes (the script,
#: the parser, the result fields), so old entries are not reused.
CACHE_VERSION = b"ws180g-run-magic 1\n"
#: How far the box is grown beyond the cell's bounding box before `drc listall why`, in
#: internal units (nm).
BOX_GROW = 20000

_WHY_ID = re.compile(r'"([A-Za-z0-9_.]+): ')
_TILES = re.compile(r"^(\d+) (.*)$")
_RULE_ID = re.compile(r"^([A-Za-z0-9_.]+): ")


def parse_why(text: str, categories_run: int) -> DrcResult:
    """A result file of the script (`total N`, `<tiles> <why>` lines, `end`): error tiles
    summed per rule id. Raises `ValueError` without the closing `end` (a session that died
    part way) or on a line of another form."""
    lines = text.splitlines()
    if not lines or lines[-1] != "end":
        raise ValueError("Magic result does not finish with 'end' (truncated)")
    counts: Counter[str] = Counter()
    for line in lines[:-1]:
        if line.startswith("total "):
            continue
        match = _TILES.match(line)
        if match is None:
            raise ValueError(f"unexpected line in a Magic result: {line!r}")
        why = match[2].strip()
        rule = _RULE_ID.match(why)
        counts[rule[1] if rule else why] += int(match[1])
    return DrcResult(violations=dict(counts), categories_run=categories_run)


def magic_rule_ids(tech: str) -> set[str]:
    """The rule ids of the why strings of a technology's drc section (comments aside)."""
    match = re.search(r"^drc\n(.*?)^end$", tech, re.MULTILINE | re.DOTALL)
    body = match[1] if match else ""
    rules = [line for line in body.splitlines() if not line.lstrip().startswith("#")]
    return set(_WHY_ID.findall("\n".join(rules)))


def cache_key(tech_files: list[Path], derived: Path) -> str:
    """SHA-256 of the technology files (by name, in name order) and the derived layout."""
    h = hashlib.sha256(CACHE_VERSION)
    for path in sorted(tech_files, key=lambda p: p.name):
        data = path.read_bytes()
        h.update(f"tech {path.name} {len(data)}\n".encode())
        h.update(data)
    data = derived.read_bytes()
    h.update(f"gds {len(data)}\n".encode())
    h.update(data)
    return h.hexdigest()


def _tech(tech_dir: Path) -> tuple[str, list[Path]]:
    """The variant and the two technology files of `tech_dir`."""
    rcs = sorted(tech_dir.glob("*.magicrc"))
    if len(rcs) != 1:
        raise ValueError(f"{tech_dir}: expected one *.magicrc, found {len(rcs)}")
    variant = rcs[0].name.removesuffix(".magicrc")
    tech = tech_dir / f"{variant}.tech"
    if not tech.is_file():
        raise ValueError(f"{tech_dir}: missing {tech.name}")
    return variant, [tech, rcs[0]]


def _renamed_copy(derived: Path, out: Path, cell: str) -> None:
    """`derived` with its top cell renamed `cell` and any other cell `<cell>_<k>`."""
    layout = kdb.Layout()
    layout.read(str(derived))
    top = layout.top_cell()
    others = sorted((c for c in layout.each_cell() if c.cell_index() != top.cell_index()),
                    key=lambda c: c.name)
    for k, c in enumerate(others):
        c.name = f"{cell}_{k}"
    top.name = cell
    options = kdb.SaveLayoutOptions()
    options.gds2_write_timestamps = False
    layout.write(str(out), options)


def magic_script(cells: list[str]) -> str:
    """The Tcl script of one session: check every cell and write its result file."""
    lines = []
    for cell in cells:
        result = f"{CONTAINER_OUT}/results/{cell}.txt"
        lines += [f"gds read {CONTAINER_OUT}/magic/{cell}.gds", f"load {cell}",
                  "select top cell", f"box grow c {BOX_GROW}", "drc check", "drc catchup",
                  f"set f [open {result} w]",
                  'puts $f "total [drc list count total]"',
                  'foreach {why boxes} [drc listall why] { puts $f "[llength $boxes] $why" }',
                  'puts $f "end"', "close $f"]
    return "\n".join([*lines, "quit -noprompt", ""])


def run_magic_many(tech_dir: Path, gds_files: list[Path], out_dir: Path, runner: Runner,
                   process: Process) -> DrcResults:
    """Run every layout of `gds_files` through the Magic technology in `tech_dir` (one Magic
    session for all cache misses) and return their results; see the module docstring."""
    variant, sources = _tech(tech_dir)
    names = [derived_name(g) for g in gds_files]
    repeated = sorted({n for n in names if names.count(n) > 1})
    if repeated:
        raise ValueError(f"inputs with the same derived name: {', '.join(repeated)}")

    tech, derived, magic, results_dir, cache = (
        out_dir / d for d in ("tech", "derived", "magic", "results", "cache"))
    for d in (tech, derived, magic, results_dir, cache):
        d.mkdir(parents=True, exist_ok=True)
    tech_files = []
    for src in sources:
        shutil.copyfile(src, tech / src.name)
        tech_files.append(tech / src.name)
    categories = len(magic_rule_ids(tech_files[0].read_text(encoding="utf-8")))

    results = DrcResults()
    misses: list[tuple[Path, str, Path]] = []  # (input, derived name, cache file)
    for gds, name in zip(gds_files, names, strict=True):
        derive_file(gds, derived / name, process, variant)
        entry = cache / f"{cache_key(tech_files, derived / name)}.json"
        if entry.is_file():
            results[gds] = DrcResult.from_json(entry.read_text(encoding="utf-8"))
            results.cache_hits += 1
        else:
            misses.append((gds, name, entry))
    if not misses:
        return _ordered(results, gds_files)

    cells = [f"c_{i:04d}" for i in range(len(misses))]
    for old in [*magic.glob("c_*.gds"), *results_dir.glob("c_*.txt")]:
        old.unlink()
    for (_, name, _), cell in zip(misses, cells, strict=True):
        _renamed_copy(derived / name, magic / f"{cell}.gds", cell)
    (magic / "names.txt").write_text("".join(f"{name}\n" for _, name, _ in misses),
                                     encoding="utf-8")
    (out_dir / "script.tcl").write_text(magic_script(cells), encoding="utf-8")
    cmd = ["sh", "-c", (f"magic -dnull -noconsole -rcfile {CONTAINER_OUT}/tech/{variant}.magicrc"
                        f" < {CONTAINER_OUT}/script.tcl")]
    done = runner(cmd, out_dir)
    (out_dir / "magic.log").write_text(done.stdout + done.stderr, encoding="utf-8")
    if done.returncode != 0:
        raise RuntimeError(f"magic exit {done.returncode}:\n{done.stdout[-4000:]}"
                           f"\n{done.stderr[-4000:]}")
    parsed = []
    for (gds, _, entry), cell in zip(misses, cells, strict=True):
        result = results_dir / f"{cell}.txt"
        if not result.is_file():
            raise RuntimeError(f"magic wrote no result for {gds} ({result}); see "
                               f"{out_dir / 'magic.log'}")
        parsed.append((gds, entry, parse_why(result.read_text(encoding="utf-8"), categories)))
    for gds, entry, result in parsed:
        entry.write_text(result.to_json(), encoding="utf-8")
        results[gds] = result
    return _ordered(results, gds_files)


def run_magic(tech_dir: Path, gds: Path, out_dir: Path, runner: Runner,
              process: Process) -> DrcResult:
    """Run one layout through the Magic technology (`run_magic_many` of one input)."""
    return run_magic_many(tech_dir, [gds], out_dir, runner, process)[gds]
