# SPDX-License-Identifier: Apache-2.0
"""The GF180MCU deck runner without a container: a fake runner writes the reports."""

import subprocess
from pathlib import Path

import pytest
from ws180g_precheck.gf180mcu import gf180mcu_command, run_gf180mcu_drc_many
from ws180g_precheck.mapping import load_mapping

MAPPING = load_mapping()

LYRDB = """<?xml version="1.0" encoding="utf-8"?>
<report-database>
 <categories>
  <category><name>'DF.3a'</name></category>
  <category><name>'Mn.1'</name></category>
 </categories>
 <items>{items}</items>
</report-database>
"""
ITEM = "<item><category>'DF.3a'</category></item>"


class FakeRunner:
    """Writes a report for every line of the list file the command names; `dirty` inputs
    get one DF.3a item."""

    def __init__(self, dirty: set[str]) -> None:
        self.dirty = dirty
        self.calls: list[list[str]] = []
        self.jobs: list[int] = []

    def __call__(self, cmd: list[str], workdir: Path) -> subprocess.CompletedProcess:
        self.calls.append(cmd)
        script = cmd[-1]
        metal_top = script.split("metal_top=")[1].split()[0]
        self.jobs.append(len(list(workdir.glob(f"list-{metal_top}-*.txt"))))
        names = [n for p in sorted(workdir.glob(f"list-{metal_top}-*.txt"))
                 for n in p.read_text(encoding="utf-8").split()]
        for name in names:
            report = workdir / "reports" / metal_top / name.replace(".gds", ".lyrdb")
            report.parent.mkdir(parents=True, exist_ok=True)
            items = ITEM if name.split("__")[1].removesuffix(".gds") in self.dirty else ""
            report.write_text(LYRDB.format(items=items), encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, "", "")


def _inputs(tmp: Path) -> list[Path]:
    paths = []
    for rule, case in [("m1.w", "a"), ("m1.s", "b")]:
        p = tmp / "in" / rule / f"{case}.gds"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(f"gds {rule} {case}".encode())
        paths.append(p)
    return paths


def test_one_container_per_metal_top_and_cache(tmp):
    inputs = _inputs(tmp)
    runner = FakeRunner(dirty={"b"})
    results = run_gf180mcu_drc_many(inputs, tmp / "run", runner, MAPPING, "11K")
    assert len(runner.calls) == 1
    assert results[inputs[0]].violations == {}
    assert results[inputs[1]].violations == {"DF.3a": 1}
    assert results[inputs[0]].categories_run == 2
    again = run_gf180mcu_drc_many(inputs, tmp / "run", runner, MAPPING, "11K")
    assert len(runner.calls) == 1 and again.cache_hits == 2 and again == results
    # another metal_top is another key: one more container
    run_gf180mcu_drc_many(inputs, tmp / "run", runner, MAPPING, "30K")
    assert len(runner.calls) == 2


def test_changed_layout_misses_the_cache(tmp):
    inputs = _inputs(tmp)
    runner = FakeRunner(dirty=set())
    run_gf180mcu_drc_many(inputs, tmp / "run", runner, MAPPING, "9K")
    inputs[0].write_bytes(b"changed")
    again = run_gf180mcu_drc_many(inputs, tmp / "run", runner, MAPPING, "9K")
    assert again.cache_hits == 1 and len(runner.calls) == 2


def test_command_switches():
    cmd = gf180mcu_command(MAPPING, "30K")
    assert cmd[:2] == ["sh", "-c"]
    script = cmd[2]
    for switch in [f"-r {MAPPING.drc.deck}", "-rd metal_level=5LM", "-rd metal_top=30K",
                   "-rd decks=all,-density,-dummy,-antenna", "-rd run_mode=flat",
                   "-rd workers=1"]:
        assert switch in script


def test_unknown_metal_top_rejected(tmp):
    with pytest.raises(ValueError, match="metal_top"):
        run_gf180mcu_drc_many(_inputs(tmp), tmp / "run", FakeRunner(set()), MAPPING, "12K")


def test_missing_report_is_an_error(tmp):
    def silent(cmd, workdir):
        return subprocess.CompletedProcess(cmd, 0, "", "")

    with pytest.raises(RuntimeError, match="no report"):
        run_gf180mcu_drc_many(_inputs(tmp), tmp / "run", silent, MAPPING, "9K")


def test_jobs_shard_the_list(tmp):
    inputs = _inputs(tmp)
    runner = FakeRunner(dirty={"a"})
    results = run_gf180mcu_drc_many(inputs, tmp / "run", runner, MAPPING, "11K", jobs=4)
    assert runner.jobs == [2]  # never more shards than layouts
    assert results[inputs[0]].violations == {"DF.3a": 1}
    script = gf180mcu_command(MAPPING, "11K", jobs=2)[2]
    assert "for k in 0 1;" in script and "list-11K-$k.txt" in script
