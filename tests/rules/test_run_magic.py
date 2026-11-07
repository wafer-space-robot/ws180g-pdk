# SPDX-License-Identifier: Apache-2.0
"""The Magic runner (Task 17), host side: the `drc listall why` parser, the cache key, the
generated Tcl script, and `run_magic_many` driven by a fake runner that writes the result
files instead of starting a container. The container half is `test_magic_fixtures.py`."""

import re
import subprocess
from pathlib import Path

import klayout.db as kdb
import pytest
from ws180g_process.load import load_process
from ws180g_rules.run_klayout import DrcResult
from ws180g_rules.run_magic import (
    CONTAINER_OUT,
    cache_key,
    magic_rule_ids,
    magic_script,
    parse_why,
    run_magic,
    run_magic_many,
)
from ws180g_rules.table import RuleTable
from ws180g_tech.magic import write_magic_tech

# What the runner's Tcl writes per layout: `total` (Magic's `drc list count total`), one line
# per entry of `drc listall why` (the number of error tiles, then the why string), `end`.
TRANSCRIPT = """total 7
2 po.w: po width < 0.24 um
1 po.w: po width < 0.24 um (second Magic rule of the same id)
3 df.x.po: df extension beyond gate < 0.48 um
1 Overlap between subcells is not allowed
end
"""


def test_parse_why_sums_tiles_per_rule_id():
    assert parse_why(TRANSCRIPT, 76) == DrcResult(
        violations={"po.w": 3, "df.x.po": 3, "Overlap between subcells is not allowed": 1},
        categories_run=76)


def test_parse_why_clean():
    assert parse_why("total 0\nend\n", 76) == DrcResult(violations={}, categories_run=76)


def test_parse_why_truncated_result_raises():
    with pytest.raises(ValueError, match="end"):
        parse_why("total 2\n2 po.w: po width < 0.24 um\n", 76)


def test_parse_why_without_total_raises():
    with pytest.raises(ValueError, match="total"):
        parse_why("2 po.w: po width < 0.24 um\nend\n", 76)


def test_parse_why_checks_the_cell_and_its_bounding_box():
    good = "cell c_0001\nbbox -2000 -2000 360 1000\ntotal 0\nend\n"
    assert parse_why(good, 76, cell="c_0001") == DrcResult(violations={}, categories_run=76)
    with pytest.raises(ValueError, match="cell"):
        parse_why(good, 76, cell="c_0002")
    with pytest.raises(ValueError, match="cell"):
        parse_why("bbox 0 0 10 10\ntotal 0\nend\n", 76, cell="c_0001")
    with pytest.raises(ValueError, match="bbox"):
        parse_why("cell c_0001\ntotal 0\nend\n", 76, cell="c_0001")
    # Magic gives a cell with nothing in it the box 0 0 1 1
    with pytest.raises(ValueError, match="empty"):
        parse_why("cell c_0001\nbbox 0 0 1 1\ntotal 0\nend\n", 76, cell="c_0001")


def test_script_records_the_cell_and_its_box():
    script = magic_script(["c_0000"])
    assert "set bbox [box values]" in script
    assert 'puts $f "cell [cellname list self]"' in script
    assert 'puts $f "bbox $bbox"' in script
    # the box is read before it is grown
    assert script.index("set bbox [box values]") < script.index("box grow c")


def test_magic_rule_ids_reads_the_drc_section():
    tech = ('drc\n # "co.w: commented"\n width nwell 1440 "nw.w: nw width < 1.44 um"\n'
            ' spacing poly poly 240 touching_ok \\\n  "po.s: po space < 0.24 um"\n'
            ' width poly 180 "po.w: x"\nend\n')
    assert magic_rule_ids(tech) == {"nw.w", "po.s", "po.w"}


def _files(root: Path, tech: bytes, rc: bytes, gds: bytes) -> tuple[list[Path], Path]:
    root.mkdir(parents=True)
    (root / "v.tech").write_bytes(tech)
    (root / "v.magicrc").write_bytes(rc)
    (root / "x.gds").write_bytes(gds)
    return [root / "v.tech", root / "v.magicrc"], root / "x.gds"


IMAGE = "sha256:" + "1" * 64


def test_cache_key(tmp, monkeypatch):
    from ws180g_rules import run_magic

    key = cache_key(*_files(tmp / "one", b"tech", b"rc", b"gds"), IMAGE)
    assert len(key) == 64 and int(key, 16) >= 0
    assert cache_key(*_files(tmp / "two", b"tech", b"rc", b"gds"), IMAGE) == key
    paths, gds = _files(tmp / "three", b"tech", b"rc", b"gds")
    assert cache_key(list(reversed(paths)), gds, IMAGE) == key
    assert cache_key(*_files(tmp / "four", b"tech2", b"rc", b"gds"), IMAGE) != key
    assert cache_key(*_files(tmp / "five", b"tech", b"rc2", b"gds"), IMAGE) != key
    assert cache_key(*_files(tmp / "six", b"tech", b"rc", b"gds2"), IMAGE) != key
    assert cache_key(*_files(tmp / "seven", b"rc", b"tech", b"gds"), IMAGE) != key
    # the image the engine runs in, and how far the box is grown, are part of it
    assert cache_key(paths, gds, "sha256:" + "2" * 64) != key
    monkeypatch.setattr(run_magic, "BOX_GROW", run_magic.BOX_GROW + 1000)
    assert cache_key(paths, gds, IMAGE) != key


def test_cache_key_differs_from_klayout():
    from ws180g_rules import run_klayout, run_magic

    assert run_magic.CACHE_VERSION != run_klayout.CACHE_VERSION


# --- run_magic_many with a fake runner


@pytest.fixture(scope="module")
def proc():
    return load_process()


@pytest.fixture(scope="module")
def tech_dir(proc, tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("tech")
    write_magic_tech(RuleTable.from_process(proc), proc, "ws180g005", out)
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


READ = re.compile(rf"^gds read {CONTAINER_OUT}/(magic/(c_\d+)\.gds)$", re.MULTILINE)


class FakeRunner:
    """Stands in for the container: checks the command and the script, and writes one result
    file per layout the script reads, with `tiles[derived stem]` error tiles of `nw.w`.
    The derived stem is found through the cell's position in the script and `names`."""

    def __init__(self, tiles: dict[str, int], returncode: int = 0, write: bool = True,
                 log: str = "out", header: str = "cell {cell}\nbbox 0 0 2000 5000\n",
                 total: bool = True) -> None:
        self.tiles = tiles
        self.returncode = returncode
        self.write = write
        self.log = log
        self.header = header
        self.total = total
        self.calls: list[tuple[list[str], Path]] = []
        self.cells: list[list[str]] = []

    def __call__(self, cmd: list[str], workdir: Path) -> subprocess.CompletedProcess:
        self.calls.append((cmd, workdir))
        assert cmd == ["sh", "-c", (f"magic -dnull -noconsole -rcfile {CONTAINER_OUT}/tech/"
                                    f"ws180g005.magicrc < {CONTAINER_OUT}/script.tcl")]
        script = (workdir / "script.tcl").read_text(encoding="utf-8")
        assert script.rstrip().endswith("quit -noprompt")
        reads = READ.findall(script)
        self.cells.append([cell for _, cell in reads])
        names = (workdir / "magic" / "names.txt").read_text(encoding="utf-8").split()
        for (path, cell), name in zip(reads, names, strict=True):
            layout = kdb.Layout()
            layout.read(str(workdir / path))
            assert layout.top_cell().name == cell  # renamed: no two inputs share a cell name
            for line in (f"load {cell}", "box grow c 20000", "drc check", "drc catchup"):
                assert line in script
            if self.write:
                n = self.tiles.get(Path(name).stem, 0)
                text = (self.header.format(cell=cell) + (f"total {n}\n" if self.total else "")
                        + (f"{n} nw.w: nw width < 1.44 um\n" if n else ""))
                (workdir / "results" / f"{cell}.txt").write_text(text + "end\n")
        return subprocess.CompletedProcess(cmd, self.returncode, self.log, "err")


@pytest.fixture
def inputs(proc, tmp) -> list[Path]:
    return [_layout(tmp / "in" / "nw.w" / "fail_min.gds", proc,
                    [("nw", 0, 0, 1000, 5000), ("nd", 200, 200, 800, 800)]),
            _layout(tmp / "in" / "nw.s" / "fail_min.gds", proc, [("nw", 0, 0, 2000, 5000)])]


def _ids(tech_dir: Path) -> int:
    return len(magic_rule_ids((tech_dir / "ws180g005.tech").read_text(encoding="utf-8")))


def test_run_many_one_session_for_all(tech_dir, proc, inputs, tmp):
    out = tmp / "work"
    runner = FakeRunner({"nw.w__fail_min": 2})
    results = run_magic_many(tech_dir, inputs, out, runner, proc)
    n = _ids(tech_dir)
    assert n > 50
    assert len(runner.calls) == 1 and runner.calls[0][1] == out
    assert runner.cells == [["c_0000", "c_0001"]]
    assert results == {inputs[0]: DrcResult({"nw.w": 2}, n), inputs[1]: DrcResult({}, n)}
    assert results.cache_hits == 0
    assert sorted(p.name for p in (out / "tech").iterdir()) == [
        "ws180g005.magicrc", "ws180g005.tech"]
    # the derived layouts carry the generated layers and keep the cell `test`
    layout = kdb.Layout()
    layout.read(str(out / "derived" / "nw.w__fail_min.gds"))
    assert layout.top_cell().name == "test"
    ntap = layout.find_layer(*proc.layers["ntap"].gds)
    assert ntap is not None and not layout.top_cell().shapes(ntap).is_empty()
    assert len(list((out / "cache").glob("*.json"))) == 2


def test_run_many_reuses_the_cache(tech_dir, proc, inputs, tmp):
    out = tmp / "work"
    first = run_magic_many(tech_dir, inputs, out, FakeRunner({"nw.w__fail_min": 1}), proc)
    runner = FakeRunner({})
    again = run_magic_many(tech_dir, inputs, out, runner, proc)
    assert runner.calls == []
    assert again == first and again.cache_hits == 2


def test_run_many_runs_only_the_misses(tech_dir, proc, inputs, tmp):
    out = tmp / "work"
    run_magic_many(tech_dir, inputs[:1], out, FakeRunner({}), proc)
    runner = FakeRunner({"nw.s__fail_min": 4})
    results = run_magic_many(tech_dir, inputs, out, runner, proc)
    assert runner.cells == [["c_0000"]]
    assert results.cache_hits == 1 and list(results) == inputs
    assert results[inputs[1]].violations == {"nw.w": 4}


def test_run_many_tech_change_misses_the_cache(tech_dir, proc, inputs, tmp):
    out = tmp / "work"
    run_magic_many(tech_dir, inputs, out, FakeRunner({}), proc)
    changed = tmp / "tech2"
    changed.mkdir()
    for f in tech_dir.iterdir():
        changed.joinpath(f.name).write_bytes(f.read_bytes())
    rc = changed / "ws180g005.magicrc"
    rc.write_text(rc.read_text(encoding="utf-8") + "# changed\n", encoding="utf-8")
    runner = FakeRunner({})
    results = run_magic_many(changed, inputs, out, runner, proc)
    assert len(runner.calls) == 1 and results.cache_hits == 0


def test_run_many_image_change_misses_the_cache(tech_dir, proc, inputs, tmp):
    out = tmp / "work"
    run_magic_many(tech_dir, inputs, out, FakeRunner({}), proc)
    runner = FakeRunner({})
    assert run_magic_many(tech_dir, inputs, out, runner, proc).cache_hits == 2
    results = run_magic_many(tech_dir, inputs, out, runner, proc,
                             image_id="sha256:" + "3" * 64)
    assert len(runner.calls) == 1 and results.cache_hits == 0


def test_run_many_refuses_repeated_names(tech_dir, proc, tmp):
    a = _layout(tmp / "a" / "nw.w" / "pass_min.gds", proc, [("nw", 0, 0, 2000, 5000)])
    b = _layout(tmp / "b" / "nw.w" / "pass_min.gds", proc, [("nw", 0, 0, 2000, 5000)])
    runner = FakeRunner({})
    with pytest.raises(ValueError, match="nw.w__pass_min"):
        run_magic_many(tech_dir, [a, b], tmp / "work", runner, proc)
    assert runner.calls == []


def test_run_many_engine_failure(tech_dir, proc, inputs, tmp):
    out = tmp / "work"
    with pytest.raises(RuntimeError, match="exit 1"):
        run_magic_many(tech_dir, inputs, out, FakeRunner({}, returncode=1), proc)
    assert not list((out / "cache").glob("*.json"))


def test_run_many_missing_result(tech_dir, proc, inputs, tmp):
    with pytest.raises(RuntimeError, match="no result"):
        run_magic_many(tech_dir, inputs, tmp / "work", FakeRunner({}, write=False), proc)


@pytest.mark.parametrize("log", [
    "Reading \"c_0000\".\nError while reading cell \"c_0000\" (byte position 12)\n",
    "Error parsing GDS-II stream\n",
    "Unknown layer/datatype in boundary, layer=99 type=0\n",
    "invalid command name \"drc\"\nError: script failed\n",
])
def test_run_many_tcl_error_in_the_log_raises(tech_dir, proc, inputs, tmp, log):
    out = tmp / "work"
    with pytest.raises(RuntimeError, match="magic.log"):
        run_magic_many(tech_dir, inputs, out, FakeRunner({}, log=log), proc)
    assert not list((out / "cache").glob("*.json"))
    assert (out / "magic.log").read_text(encoding="utf-8").startswith(log)


def test_run_many_clean_log_passes(tech_dir, proc, inputs, tmp):
    log = ("Warning: Calma reading is not undoable!  I hope that's OK.\nNo errors found.\n")
    results = run_magic_many(tech_dir, inputs, tmp / "work", FakeRunner({}, log=log), proc)
    assert len(results) == 2


def test_run_many_empty_cell_raises(tech_dir, proc, inputs, tmp):
    out = tmp / "work"
    runner = FakeRunner({}, header="cell {cell}\nbbox 0 0 1 1\n")
    with pytest.raises(RuntimeError, match="empty"):
        run_magic_many(tech_dir, inputs, out, runner, proc)
    assert not list((out / "cache").glob("*.json"))


def test_run_many_wrong_cell_raises(tech_dir, proc, inputs, tmp):
    runner = FakeRunner({}, header="cell test\nbbox 0 0 2000 5000\n")
    with pytest.raises(RuntimeError, match="cell"):
        run_magic_many(tech_dir, inputs, tmp / "work", runner, proc)


def test_run_many_missing_total_raises(tech_dir, proc, inputs, tmp):
    out = tmp / "work"
    with pytest.raises(RuntimeError, match="total"):
        run_magic_many(tech_dir, inputs, out, FakeRunner({}, total=False), proc)
    assert not list((out / "cache").glob("*.json"))


def test_run_many_stale_result_is_not_read(tech_dir, proc, inputs, tmp):
    out = tmp / "work"
    (out / "results").mkdir(parents=True)
    (out / "results" / "c_0000.txt").write_text("total 0\nend\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="no result"):
        run_magic_many(tech_dir, inputs, out, FakeRunner({}, write=False), proc)


def test_run_many_bad_tech_dir(proc, inputs, tmp):
    (tmp / "empty").mkdir()
    with pytest.raises(ValueError, match="magicrc"):
        run_magic_many(tmp / "empty", inputs, tmp / "work", FakeRunner({}), proc)


def test_run_one(tech_dir, proc, inputs, tmp):
    runner = FakeRunner({"nw.w__fail_min": 3})
    assert run_magic(tech_dir, inputs[0], tmp / "work", runner, proc) == DrcResult(
        {"nw.w": 3}, _ids(tech_dir))
