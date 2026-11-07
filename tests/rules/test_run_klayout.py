# SPDX-License-Identifier: Apache-2.0
"""The KLayout runner (Task 15), host side: the `.lyrdb` parser, the cache key, and
`run_klayout_many` driven by a fake runner that writes reports instead of starting a
container. The container half is `test_klayout_fixtures.py`."""

import subprocess
from pathlib import Path

import klayout.db as kdb
import pytest
from ws180g_process.load import load_process
from ws180g_rules.klayout_deck import write_klayout_deck
from ws180g_rules.run_klayout import (
    CONTAINER_OUT,
    DrcResult,
    cache_key,
    derived_name,
    parse_lyrdb,
    run_klayout,
    run_klayout_many,
)
from ws180g_rules.table import RuleTable

LYRDB = """<?xml version="1.0" encoding="utf-8"?>
<report-database>
 <description>ws180g005</description>
 <categories>
  <category><name>nw.w</name><description>n-well width</description><categories/></category>
  <category><name>grid</name><description>grid</description><categories/></category>
  <category><name>co.size</name><description>contact size</description><categories/></category>
 </categories>
 <cells><cell><name>test</name></cell></cells>
 <items>
  <item><tags/><category>'nw.w'</category><cell>test</cell><values/></item>
  <item><tags/><category>'nw.w'</category><cell>test</cell><values/></item>
  <item><tags/><category>grid</category><cell>test</cell><values/></item>
 </items>
</report-database>
"""

EMPTY_LYRDB = """<?xml version="1.0" encoding="utf-8"?>
<report-database>
 <categories>
  <category><name>nw.w</name><categories/></category>
 </categories>
 <items/>
</report-database>
"""


def test_parse_lyrdb_counts_items_per_category(tmp):
    path = tmp / "r.lyrdb"
    path.write_text(LYRDB, encoding="utf-8")
    assert parse_lyrdb(path) == DrcResult(violations={"nw.w": 2, "grid": 1}, categories_run=3)


def test_parse_lyrdb_clean_report(tmp):
    path = tmp / "r.lyrdb"
    path.write_text(EMPTY_LYRDB, encoding="utf-8")
    assert parse_lyrdb(path) == DrcResult(violations={}, categories_run=1)


def test_drc_result_json_round_trip():
    result = DrcResult(violations={"nw.w": 2}, categories_run=7)
    assert DrcResult.from_json(result.to_json()) == result


def _files(root: Path, deck: dict[str, bytes], gds: bytes) -> tuple[list[Path], Path]:
    root.mkdir(parents=True)
    paths = []
    for name, data in deck.items():
        (root / name).write_bytes(data)
        paths.append(root / name)
    (root / "x.gds").write_bytes(gds)
    return paths, root / "x.gds"


def test_cache_key(tmp):
    deck = {"a.drc": b"deck", "a_checks.rb": b"checks"}
    key = cache_key(*_files(tmp / "one", deck, b"gds"))
    assert len(key) == 64 and int(key, 16) >= 0
    # the same bytes elsewhere: the same key (the location is not part of it)
    assert cache_key(*_files(tmp / "two", deck, b"gds")) == key
    # the order the deck files are given in is not part of it
    paths, gds = _files(tmp / "three", deck, b"gds")
    assert cache_key(list(reversed(paths)), gds) == key
    # any byte of the deck or the layout is
    assert cache_key(*_files(tmp / "four", {**deck, "a.drc": b"deck2"}, b"gds")) != key
    assert cache_key(*_files(tmp / "five", deck, b"gds2")) != key
    # so is which deck file holds which bytes
    assert cache_key(*_files(tmp / "six", {"a.drc": b"checks", "a_checks.rb": b"deck"},
                             b"gds")) != key


def test_derived_name():
    assert derived_name(Path("out/nw.w/pass_min.gds")) == "nw.w__pass_min.gds"


# --- run_klayout_many with a fake runner


@pytest.fixture(scope="module")
def proc():
    return load_process()


@pytest.fixture(scope="module")
def deck_dir(proc, tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("deck")
    write_klayout_deck(RuleTable.from_process(proc), proc, out)
    return out


def _layout(path: Path, proc, boxes: list[tuple[str, int, int, int, int]]) -> Path:
    layout = kdb.Layout()
    layout.dbu = 0.001
    top = layout.create_cell("test")
    for name, x1, y1, x2, y2 in boxes:
        top.shapes(layout.layer(*proc.layers[name].gds)).insert(kdb.Box(x1, y1, x2, y2))
    path.parent.mkdir(parents=True, exist_ok=True)
    options = kdb.SaveLayoutOptions()
    options.gds2_write_timestamps = False
    layout.write(str(path), options)
    return path


class FakeRunner:
    """Stands in for the container: checks the command, reads `list.txt` and writes one
    report per listed layout, with `items[stem]` violations of category `nw.w`."""

    def __init__(self, items: dict[str, int], returncode: int = 0) -> None:
        self.items = items
        self.returncode = returncode
        self.calls: list[tuple[list[str], Path]] = []
        self.listed: list[list[str]] = []

    def __call__(self, cmd: list[str], workdir: Path) -> subprocess.CompletedProcess:
        self.calls.append((cmd, workdir))
        assert cmd == ["klayout", "-b", "-r", f"{CONTAINER_OUT}/deck/ws180g005_batch.drc",
                       "-rd", f"list={CONTAINER_OUT}/list.txt",
                       "-rd", f"out={CONTAINER_OUT}/reports"]
        lines = (workdir / "list.txt").read_text(encoding="utf-8").splitlines()
        self.listed.append(lines)
        for line in lines:
            assert line.startswith(f"{CONTAINER_OUT}/derived/")
            host = workdir / line.removeprefix(f"{CONTAINER_OUT}/")
            assert host.is_file()
            stem = Path(line).stem
            items = "".join("<item><category>'nw.w'</category></item>"
                            for _ in range(self.items.get(stem, 0)))
            (workdir / "reports" / f"{stem}.lyrdb").write_text(
                "<report-database><categories><category><name>nw.w</name></category>"
                f"<category><name>grid</name></category></categories><items>{items}</items>"
                "</report-database>", encoding="utf-8")
        return subprocess.CompletedProcess(cmd, self.returncode, "out", "err")


@pytest.fixture
def inputs(proc, tmp) -> list[Path]:
    return [_layout(tmp / "in" / "nw.w" / "fail_min.gds", proc,
                    [("nw", 0, 0, 1000, 5000), ("nd", 200, 200, 800, 800)]),
            _layout(tmp / "in" / "nw.s" / "fail_min.gds", proc, [("nw", 0, 0, 2000, 5000)])]


def test_run_many_one_container_for_all(deck_dir, proc, inputs, tmp):
    out = tmp / "work"
    runner = FakeRunner({"nw.w__fail_min": 2})
    results = run_klayout_many(deck_dir, inputs, out, runner, proc)
    assert len(runner.calls) == 1 and runner.calls[0][1] == out
    assert runner.listed == [[f"{CONTAINER_OUT}/derived/nw.w__fail_min.gds",
                              f"{CONTAINER_OUT}/derived/nw.s__fail_min.gds"]]
    assert results == {inputs[0]: DrcResult({"nw.w": 2}, 2), inputs[1]: DrcResult({}, 2)}
    assert results.cache_hits == 0
    # the deck is copied next to the layouts; the derived layouts carry the generated layers
    assert sorted(p.name for p in (out / "deck").iterdir()) == [
        "ws180g005.drc", "ws180g005_batch.drc", "ws180g005_checks.rb"]
    layout = kdb.Layout()
    layout.read(str(out / "derived" / "nw.w__fail_min.gds"))
    ntap = layout.find_layer(*proc.layers["ntap"].gds)
    assert ntap is not None and not layout.top_cell().shapes(ntap).is_empty()
    assert len(list((out / "cache").glob("*.json"))) == 2


def test_run_many_reuses_the_cache(deck_dir, proc, inputs, tmp):
    out = tmp / "work"
    first = run_klayout_many(deck_dir, inputs, out, FakeRunner({"nw.w__fail_min": 1}), proc)
    runner = FakeRunner({})
    again = run_klayout_many(deck_dir, inputs, out, runner, proc)
    assert runner.calls == []
    assert again == first and again.cache_hits == 2


def test_run_many_runs_only_the_misses(deck_dir, proc, inputs, tmp):
    out = tmp / "work"
    run_klayout_many(deck_dir, inputs[:1], out, FakeRunner({}), proc)
    runner = FakeRunner({})
    results = run_klayout_many(deck_dir, inputs, out, runner, proc)
    assert runner.listed == [[f"{CONTAINER_OUT}/derived/nw.s__fail_min.gds"]]
    assert results.cache_hits == 1 and set(results) == set(inputs)


def test_run_many_deck_change_misses_the_cache(deck_dir, proc, inputs, tmp):
    out = tmp / "work"
    run_klayout_many(deck_dir, inputs, out, FakeRunner({}), proc)
    changed = tmp / "deck2"
    changed.mkdir()
    for f in deck_dir.iterdir():
        changed.joinpath(f.name).write_bytes(f.read_bytes())
    checks = changed / "ws180g005_checks.rb"
    checks.write_text(checks.read_text(encoding="utf-8") + "\n# changed\n", encoding="utf-8")
    runner = FakeRunner({})
    results = run_klayout_many(changed, inputs, out, runner, proc)
    assert len(runner.calls) == 1 and results.cache_hits == 0


def test_run_many_refuses_repeated_names(deck_dir, proc, tmp):
    a = _layout(tmp / "a" / "nw.w" / "pass_min.gds", proc, [("nw", 0, 0, 2000, 5000)])
    b = _layout(tmp / "b" / "nw.w" / "pass_min.gds", proc, [("nw", 0, 0, 2000, 5000)])
    runner = FakeRunner({})
    with pytest.raises(ValueError, match="nw.w__pass_min"):
        run_klayout_many(deck_dir, [a, b], tmp / "work", runner, proc)
    assert runner.calls == []


def test_run_many_engine_failure(deck_dir, proc, inputs, tmp):
    out = tmp / "work"
    with pytest.raises(RuntimeError, match="exit 1"):
        run_klayout_many(deck_dir, inputs, out, FakeRunner({}, returncode=1), proc)
    # nothing is cached from a failed run
    assert not list((out / "cache").glob("*.json"))


def test_run_many_missing_report(deck_dir, proc, inputs, tmp):
    class Silent(FakeRunner):
        def __call__(self, cmd, workdir):
            return subprocess.CompletedProcess(cmd, 0, "", "")

    with pytest.raises(RuntimeError, match="no report"):
        run_klayout_many(deck_dir, inputs, tmp / "work", Silent({}), proc)


def test_run_many_stale_report_is_not_read(deck_dir, proc, inputs, tmp):
    out = tmp / "work"
    (out / "reports").mkdir(parents=True)
    (out / "reports" / "nw.w__fail_min.lyrdb").write_text(EMPTY_LYRDB, encoding="utf-8")

    class Silent(FakeRunner):
        def __call__(self, cmd, workdir):
            return subprocess.CompletedProcess(cmd, 0, "", "")

    with pytest.raises(RuntimeError, match="no report"):
        run_klayout_many(deck_dir, inputs, out, Silent({}), proc)


def test_run_one(deck_dir, proc, inputs, tmp):
    runner = FakeRunner({"nw.w__fail_min": 3})
    assert run_klayout(deck_dir, inputs[0], tmp / "work", runner, proc) == DrcResult(
        {"nw.w": 3}, 2)
