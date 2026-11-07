# SPDX-License-Identifier: Apache-2.0
"""Gate check 1, Magic half (Task 17): every per-rule fixture of Task 14 through the Magic
technology in the container.

The fixture set is the KLayout half's (`test_klayout_fixtures.FIXTURES`, computed at
collection and written under `tmp/klayout-fixtures/fixtures/` by its session fixture
`fixture_files`). Magic runs once for all of them (one
container, one Magic session) in a session-scoped fixture, and each parametrised test reads
its result. Magic's counts are error tiles, so a fixture is checked by its set of rule ids:
`magic_markers(fixture)`, the KLayout markers unless `MAGIC_EXCEPTIONS` records Magic's own
set. Results are cached by the bytes of the technology and of the derived layout; delete
`tmp/magic-fixtures/` to force a fresh engine run."""

import subprocess
from pathlib import Path

import pytest
from test_klayout_fixtures import FIXTURES, PROCESS, TABLE, fixture_files  # noqa: F401
from ws180g_rules.run_magic import run_magic_many
from ws180g_tech.magic import magic_markers, write_magic_tech

REPO = Path(__file__).resolve().parents[2]
WORK = REPO / "tmp" / "magic-fixtures"
VARIANT = "ws180g005"
#: The rule ids Magic checks (a fixture of any other rule is skipped).
MAGIC_RULES = {r.id for r in TABLE.checkable() if "magic" in r.engines}


@pytest.fixture(scope="session")
def tech_dir() -> Path:
    return write_magic_tech(TABLE, PROCESS, VARIANT, WORK / "tech")[0].parent


@pytest.fixture(scope="session")
def magic_results(sandbox, tech_dir, request):
    """The results of every fixture of a Magic rule, from one Magic session (or the cache)."""
    request.getfixturevalue("fixture_files")  # the fixture files, written once
    inputs = [f.path for f in FIXTURES if f.rule_id in MAGIC_RULES]
    return run_magic_many(tech_dir, inputs, WORK / "run", sandbox.run, PROCESS)


@pytest.mark.sandbox
@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda f: f"{f.rule_id}/{f.expect}_{f.name}")
def test_magic_fixture(fixture, request):
    if fixture.rule_id not in MAGIC_RULES:
        pytest.skip("KLayout-only")
    result = request.getfixturevalue("magic_results")[fixture.path]
    assert result.categories_run > 0
    # a pass fixture is clean; a fail fixture trips its own rule (and the forced companions
    # of fixtures.EXPECTED_MARKERS), or Magic's recorded set in MAGIC_EXCEPTIONS
    assert set(result.violations) == magic_markers(fixture), result.violations


class Counting:
    """Wraps a runner and counts the containers it starts."""

    def __init__(self, runner) -> None:
        self.runner = runner
        self.calls = 0

    def __call__(self, cmd: list[str], workdir: Path) -> subprocess.CompletedProcess:
        self.calls += 1
        return self.runner(cmd, workdir)


@pytest.mark.sandbox
def test_cache_hit(sandbox, tech_dir, magic_results):
    inputs = list(magic_results)
    runner = Counting(sandbox.run)
    again = run_magic_many(tech_dir, inputs, WORK / "run", runner, PROCESS)
    assert runner.calls == 0
    assert again.cache_hits == len(inputs)
    assert again == magic_results
