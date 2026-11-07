# SPDX-License-Identifier: Apache-2.0
"""Run retargeted layouts through the public GF180MCU KLayout deck, one container per
`metal_top` value, with a cache.

`run_gf180mcu_drc_many(gds_files, out_dir, runner, mapping, metal_top)`:

1. copies every retargeted input to `out_dir/gds/<parent dir>__<stem>.gds` (flat, unique);
2. looks each one up in `out_dir/cache/<key>.json`, the key being the SHA-256 of the
   layout's bytes, the mapping file's bytes, `metal_top` and the deck path (`cache_key`);
3. for the misses only, writes `out_dir/list-<metal_top>-<k>.txt` (`jobs` shards) and starts
   **one** container, `sh -c '<loops>'`, whose `jobs` parallel loops run `klayout -b -r
   <deck>` once per listed layout (the public deck has no batch mode) with the switches of
   `mapping.drc`, each run's output in
   `out_dir/logs/<metal_top>/<name>.log` and its report in
   `out_dir/reports/<metal_top>/<name>.lyrdb`;
4. parses each report with `ws180g_rules.run_klayout.parse_lyrdb` (the categories are GF
   rule ids, `DF.3a`, `Mn.1`, ...), caches it and returns `{input: DrcResult}`.

The runner is the same `runner(cmd, workdir)` callable as `ws180g_rules.run_klayout`'s; it
must mount `out_dir` at `/work/out`.
"""

import hashlib
import shlex
import shutil
from pathlib import Path

from ws180g_rules.run_klayout import (
    CONTAINER_OUT,
    DrcResult,
    DrcResults,
    Runner,
    derived_name,
    parse_lyrdb,
)

from ws180g_precheck.mapping import Mapping

#: Part of every cache key; bump it when the meaning of a cached result changes.
CACHE_VERSION = b"ws180g-gf180mcu-drc 1\n"


def cache_key(gds: Path, mapping: Mapping, metal_top: str) -> str:
    """SHA-256 of the retargeted layout, the mapping file, `metal_top` and the deck path."""
    h = hashlib.sha256(CACHE_VERSION)
    for label, data in [("gds", gds.read_bytes()),
                        ("mapping", mapping.path.read_bytes() if mapping.path else b""),
                        ("metal_top", metal_top.encode()), ("deck", mapping.drc.deck.encode())]:
        h.update(f"{label} {len(data)}\n".encode())
        h.update(data)
    return h.hexdigest()


def gf180mcu_command(mapping: Mapping, metal_top: str, jobs: int = 1) -> list[str]:
    """The container command: `jobs` shell loops in parallel, loop `k` running klayout once
    per line of `list-<metal_top>-<k>.txt`; the exit code is 1 when any run failed (the
    others still run)."""
    out = CONTAINER_OUT
    switches = " ".join(shlex.quote(s) for s in [
        "-rd", f"metal_level={mapping.metal_level}", "-rd", f"metal_top={metal_top}",
        "-rd", f"decks={mapping.drc.decks}", "-rd", f"run_mode={mapping.drc.run_mode}",
        "-rd", f"workers={mapping.drc.workers}"])
    loop = (
        f"rc=0; while read -r f; do n=${{f%.gds}}; "
        f"klayout -b -r {shlex.quote(mapping.drc.deck)} -rd input={out}/gds/$f "
        f"-rd report={out}/reports/{metal_top}/$n.lyrdb {switches} "
        f"> {out}/logs/{metal_top}/$n.log 2>&1 || {{ rc=1; echo \"klayout failed: $f\"; }}; "
        f"done < {out}/list-{metal_top}-$k.txt; exit $rc")
    script = (
        f"mkdir -p {out}/reports/{metal_top} {out}/logs/{metal_top}; pids=; "
        f"for k in {' '.join(str(k) for k in range(jobs))}; do ( {loop} ) & pids=\"$pids $!\"; "
        f"done; fail=0; for p in $pids; do wait $p || fail=1; done; exit $fail")
    return ["sh", "-c", script]


def run_gf180mcu_drc_many(gds_files: list[Path], out_dir: Path, runner: Runner,
                          mapping: Mapping, metal_top: str, jobs: int = 1) -> DrcResults:
    """Run every retargeted layout of `gds_files` through the public deck with `metal_top`
    (one container for all cache misses, `jobs` klayout processes at a time: match it to
    the runner's CPU cap) and return their results."""
    if jobs < 1:
        raise ValueError(f"jobs must be at least 1: {jobs}")
    if metal_top not in mapping.drc.metal_top:
        raise ValueError(f"metal_top {metal_top!r} is not one of {mapping.drc.metal_top}")
    names = [derived_name(g) for g in gds_files]
    repeated = sorted({n for n in names if names.count(n) > 1})
    if repeated:
        raise ValueError(f"inputs with the same flat name: {', '.join(repeated)}")
    gds_dir, reports, cache = out_dir / "gds", out_dir / "reports" / metal_top, out_dir / "cache"
    for d in (gds_dir, reports, cache):
        d.mkdir(parents=True, exist_ok=True)

    results = DrcResults()
    misses: list[tuple[Path, str, Path]] = []
    for gds, name in zip(gds_files, names, strict=True):
        shutil.copyfile(gds, gds_dir / name)
        entry = cache / f"{cache_key(gds_dir / name, mapping, metal_top)}.json"
        if entry.is_file():
            results[gds] = DrcResult.from_json(entry.read_text(encoding="utf-8"))
            results.cache_hits += 1
        else:
            misses.append((gds, name, entry))
    if misses:
        for _, name, _ in misses:
            (reports / name).with_suffix(".lyrdb").unlink(missing_ok=True)
        for old in out_dir.glob(f"list-{metal_top}-*.txt"):
            old.unlink()
        jobs = min(jobs, len(misses))
        for k in range(jobs):
            (out_dir / f"list-{metal_top}-{k}.txt").write_text(
                "".join(f"{name}\n" for _, name, _ in misses[k::jobs]), encoding="utf-8")
        done = runner(gf180mcu_command(mapping, metal_top, jobs), out_dir)
        missing = []
        for gds, name, entry in misses:
            report = (reports / name).with_suffix(".lyrdb")
            if not report.is_file():
                missing.append(f"{gds} ({report})")
                continue
            result = parse_lyrdb(report)
            entry.write_text(result.to_json(), encoding="utf-8")
            results[gds] = result
        if done.returncode != 0 or missing:
            raise RuntimeError(
                f"GF180MCU deck (metal_top={metal_top}) exit {done.returncode}; "
                f"no report for {len(missing)}: {'; '.join(missing[:5])}\n"
                f"{done.stdout[-4000:]}\n{done.stderr[-4000:]}\n"
                f"logs: {out_dir / 'logs' / metal_top}")
    out = DrcResults((g, results[g]) for g in gds_files)
    out.cache_hits = results.cache_hits
    return out
