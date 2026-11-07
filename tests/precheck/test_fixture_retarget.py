# SPDX-License-Identifier: Apache-2.0
"""Gate check 2 (Task 18): every pass fixture of Task 14, retargeted to GF180MCU, passes the
public GF180MCU deck, for every `metal_top` value.

Collection only computes the case ids (from the rule table, writing nothing), so a unit
run (`-m "not sandbox"`) never touches a gate run's files. The session fixtures write the
pass fixtures into `tmp/gf180mcu-retarget/fixtures/` (with the regression fixtures of
`ws180g_precheck.regressions`, which the build runs too), retarget them into `tmp/gf180mcu-retarget/retargeted/` and
run them: one container per `metal_top` value. Results are cached by the retargeted bytes,
the mapping as used, `metal_top`, the deck path and the image ID; delete
`tmp/gf180mcu-retarget/run/` to force fresh runs. A fixture excluded under policy (c) of
`docs/phase-0-retarget-log.md` is listed in `ws180g_precheck.gate.EXCLUDED` with its GF rule
and reason. A summary of every run is written to `tmp/gf180mcu-retarget/reports/gate.json`."""

import json
import shutil
import time
from pathlib import Path

import pytest
from ws180g_precheck.gate import EXCLUDED, regression_names, write_regressions
from ws180g_precheck.gf180mcu import run_gf180mcu_drc_many
from ws180g_precheck.mapping import load_mapping
from ws180g_precheck.retarget import retarget_file
from ws180g_process.load import load_process
from ws180g_rules.fixtures import Kit, cases, write_fixtures
from ws180g_rules.table import RuleTable

REPO = Path(__file__).resolve().parents[2]
WORK = REPO / "tmp" / "gf180mcu-retarget"
PROCESS = load_process()
MAPPING = load_mapping()
#: Parallel klayout runs inside the one container; the sandbox fixture caps it at 2 CPUs.
JOBS = 2

TABLE = RuleTable.from_process(PROCESS)


def _pass_ids() -> list[str]:
    """`<rule id>/<name>` of every Task 14 pass fixture, in `write_fixtures` order, computed
    from the fixture generator's cases without writing a file."""
    kit = Kit(TABLE, PROCESS)
    return [f"{row.id}/{name}" for row in TABLE.checkable()
            for expect, name, _ in cases(row, kit) if expect == "pass"]


PASS_IDS = _pass_ids()
CASE_IDS = ([i for i in PASS_IDS if tuple(i.split("/", 1)) not in EXCLUDED]
            + [f"regressions/{name}" for name in regression_names()])


@pytest.fixture(scope="session")
def generic_layouts() -> dict[str, Path]:
    """Every case's generic layout, by id, written into `tmp/gf180mcu-retarget/fixtures/`."""
    shutil.rmtree(WORK / "fixtures", ignore_errors=True)
    fixtures = write_fixtures(TABLE, PROCESS, WORK / "fixtures")
    out = {f"{f.rule_id}/{f.name}": f.path for f in fixtures if f.expect == "pass"}
    out.update(write_regressions(PROCESS, WORK / "fixtures" / "regressions"))
    return {case_id: out[case_id] for case_id in CASE_IDS}


@pytest.fixture(scope="session")
def retargeted(generic_layouts) -> dict[str, Path]:
    """Every case retargeted, by id: `retargeted/<rule>/<name>.gds`."""
    shutil.rmtree(WORK / "retargeted", ignore_errors=True)
    out = {}
    for case_id, path in generic_layouts.items():
        target = WORK / "retargeted" / path.parent.name / path.name
        retarget_file(path, target, MAPPING, PROCESS)
        out[case_id] = target
    return out


@pytest.fixture(scope="session")
def gf_results(sandbox, retargeted):
    """`{metal_top: {case id: DrcResult}}`: one container per metal_top value."""
    results, summary = {}, {}
    for metal_top in MAPPING.drc.metal_top:
        start = time.monotonic()
        run = run_gf180mcu_drc_many(list(retargeted.values()), WORK / "run", sandbox.run,
                                    MAPPING, metal_top, jobs=JOBS)
        results[metal_top] = {case_id: run[path] for case_id, path in retargeted.items()}
        summary[metal_top] = {
            "seconds": round(time.monotonic() - start, 1), "cache_hits": run.cache_hits,
            "cases": len(retargeted),
            "dirty": {c: r.violations for c, r in results[metal_top].items() if r.violations}}
    (WORK / "reports").mkdir(parents=True, exist_ok=True)
    (WORK / "reports" / "gate.json").write_text(
        json.dumps({"excluded": {f"{r}/{n}": list(v) for (r, n), v in EXCLUDED.items()},
                    "runs": summary}, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return results


@pytest.mark.sandbox
@pytest.mark.parametrize("metal_top", MAPPING.drc.metal_top)
@pytest.mark.parametrize("case", CASE_IDS)
def test_fixture_passes_gf180mcu(case, metal_top, gf_results):
    result = gf_results[metal_top][case]
    assert result.categories_run > 0
    assert result.violations == {}, result.violations


def test_exclusions_are_recorded():
    log = (REPO / "docs" / "phase-0-retarget-log.md").read_text(encoding="utf-8")
    for (rule_id, name), (gf_rule, reason) in EXCLUDED.items():
        assert gf_rule and reason
        assert f"{rule_id}/{name}" in log
        # a stale exclusion (the fixture is gone or renamed) is an error
        assert f"{rule_id}/{name}" in PASS_IDS, (rule_id, name)


def test_case_ids_match_the_written_fixtures(tmp_path):
    """The ids computed at collection are those of the pass fixtures `write_fixtures`
    writes (here into pytest's own temporary directory, not the gate's)."""
    written = write_fixtures(TABLE, PROCESS, tmp_path / "fixtures")
    assert PASS_IDS == [f"{f.rule_id}/{f.name}" for f in written if f.expect == "pass"]


def test_gate_fixtures_are_the_case_ids(tmp_path):
    """`ws180g_precheck.gate.gate_fixtures` (what the build runs) picks the same pass
    fixtures as this test, the regression fixtures aside."""
    from ws180g_precheck.gate import gate_fixtures

    written = write_fixtures(TABLE, PROCESS, tmp_path / "fixtures")
    assert [f"{f.rule_id}/{f.name}" for f in gate_fixtures(written)] == [
        c for c in CASE_IDS if not c.startswith("regressions/")]
