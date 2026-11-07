# SPDX-License-Identifier: Apache-2.0
"""Gate check 1, KLayout half (Task 15): every per-rule fixture of Task 14 through the
KLayout deck in the container.

The fixtures are written at collection time so the test can be parametrised over them; the
engine runs once for all of them (one container, `ws180g005_batch.drc`) in a session-scoped
fixture, and each parametrised test reads its result. Results are cached by the bytes of the
deck and of the derived layout, so a rerun with nothing changed starts no container; delete
`tmp/klayout-fixtures/` to force a fresh engine run."""

import shutil
import subprocess
from pathlib import Path

import klayout.db as kdb
import pytest
from ws180g_process.load import load_process
from ws180g_rules.fixtures import write_fixtures
from ws180g_rules.klayout_deck import write_klayout_deck
from ws180g_rules.run_klayout import run_klayout_many
from ws180g_rules.table import RuleTable

REPO = Path(__file__).resolve().parents[2]
# The brief names `out/fixtures/`, but build/sandbox-run accepts a workdir inside a checkout
# only under its gitignored `tmp/`, so the fixtures, the deck and the run live there.
WORK = REPO / "tmp" / "klayout-fixtures"
PROCESS = load_process()
TABLE = RuleTable.from_process(PROCESS)


def _write_fixtures():
    shutil.rmtree(WORK / "fixtures", ignore_errors=True)
    return write_fixtures(TABLE, PROCESS, WORK / "fixtures")


FIXTURES = _write_fixtures()


@pytest.fixture(scope="session")
def deck_dir() -> Path:
    return write_klayout_deck(TABLE, PROCESS, WORK / "deck")[0].parent


@pytest.fixture(scope="session")
def klayout_results(sandbox, deck_dir):
    """The results of every fixture, from one batch run (or the cache)."""
    return run_klayout_many(deck_dir, [f.path for f in FIXTURES], WORK / "run", sandbox.run,
                            PROCESS)


@pytest.mark.sandbox
# ids are <rule>/<expect>_<name> (the file stem): <rule>/<name> repeats for the pass and
# fail fixtures of the topology rules (co.in/co_on_field...).
@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda f: f"{f.rule_id}/{f.expect}_{f.name}")
def test_klayout_fixture(fixture, klayout_results):
    result = klayout_results[fixture.path]
    assert result.categories_run > 0
    # a pass fixture is clean (a false positive otherwise); a fail fixture trips its own rule
    # once, or the geometrically forced set recorded in fixtures.EXPECTED_MARKERS
    assert result.violations == fixture.markers(), result.violations


class Counting:
    """Wraps a runner and counts the containers it starts."""

    def __init__(self, runner) -> None:
        self.runner = runner
        self.calls = 0

    def __call__(self, cmd: list[str], workdir: Path) -> subprocess.CompletedProcess:
        self.calls += 1
        return self.runner(cmd, workdir)


@pytest.mark.sandbox
def test_cache_hit(sandbox, deck_dir, klayout_results):
    inputs = [f.path for f in FIXTURES]
    runner = Counting(sandbox.run)
    again = run_klayout_many(deck_dir, inputs, WORK / "run", runner, PROCESS)
    assert runner.calls == 0
    assert again.cache_hits == len(inputs)
    assert again == klayout_results


# --- layouts the generators cannot draw: a rotated cut and an off-grid vertex


def _layout(path: Path, polygons: list[tuple[str, list[tuple[int, int]]]]) -> Path:
    layout = kdb.Layout()
    layout.dbu = 0.001
    top = layout.create_cell("test")
    for name, points in polygons:
        top.shapes(layout.layer(*PROCESS.layers[name].gds)).insert(
            kdb.Polygon([kdb.Point(x, y) for x, y in points]))
    path.parent.mkdir(parents=True, exist_ok=True)
    options = kdb.SaveLayoutOptions()
    options.gds2_write_timestamps = False
    layout.write(str(path), options)
    return path


def _box(x1: int, y1: int, x2: int, y2: int) -> list[tuple[int, int]]:
    return [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]


@pytest.fixture(scope="session")
def extra(sandbox, deck_dir, tmp_path_factory):
    """A fresh run (no cache) of the two hand-drawn layouts, by name."""
    root = tmp_path_factory.mktemp("klayout-extra")
    inputs = {
        # a contact rotated by 45 degrees (a diamond on the grid), inside m1
        "rotated_co": _layout(root / "in" / "cut.ortho" / "rotated_co.gds", [
            ("co", [(0, -155), (155, 0), (0, 155), (-155, 0)]),
            ("m1", _box(-1200, -1200, 1200, 1200))]),
        # an m1 box with its left edge at x = 2 dbu, off the 5 dbu grid
        "off_grid": _layout(root / "in" / "grid" / "off_grid.gds", [
            ("m1", _box(2, 0, 2000, 2000))]),
    }
    runner = Counting(sandbox.run)
    results = run_klayout_many(deck_dir, list(inputs.values()), root / "run", runner, PROCESS)
    assert runner.calls == 1 and results.cache_hits == 0
    return {name: results[path] for name, path in inputs.items()}


@pytest.mark.sandbox
def test_non_manhattan_cut_rejected(extra):
    assert extra["rotated_co"].categories_run > 0
    assert "cut.ortho" in extra["rotated_co"].violations, extra["rotated_co"].violations


@pytest.mark.sandbox
def test_off_grid_vertex_rejected(extra):
    assert extra["off_grid"].categories_run > 0
    assert "grid" in extra["off_grid"].violations, extra["off_grid"].violations
