# SPDX-License-Identifier: Apache-2.0
"""`tools/pytest_log_counts.py`: outcomes of a `pytest -v` log counted by test id, including
a test whose output puts its outcome on a later line, and not the short summary lines."""

import importlib.util
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "tools" / "pytest_log_counts.py"

LOG = """\
collecting ... collected 6 items

tests/rules/test_a.py::test_x[po.x.df/pass_min] PASSED [ 16%]
tests/rules/test_a.py::test_x[po.x.df/fail_end_inside]
MAGIC_EXCEPTIONS po.x.df/fail_end_inside: KLayout ['po.x.df'], Magic ['df.x.po']
PASSED [ 33%]
tests/rules/test_a.py::test_x[grid/pass_grid] SKIPPED [ 50%]
tests/precheck/test_b.py::test_y[nw.w/min-9K] PASSED [ 66%]
tests/precheck/test_b.py::test_y[nw.w/min-30K] FAILED [ 83%]
tests/precheck/test_b.py::test_y[regressions/v4-30K] PASSED [100%]

=========================== short test summary info ============================
SKIPPED [1] tests/rules/test_a.py:23: KLayout-only
FAILED tests/precheck/test_b.py::test_y[nw.w/min-30K] - assert 1 == 0
============== 4 passed, 1 skipped, 1 failed in 1.00s ==============
"""


def _module():
    spec = importlib.util.spec_from_file_location("pytest_log_counts", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_outcome_on_a_later_line_is_counted_once():
    c = _module().counts(LOG)
    assert c[("tests/rules/test_a.py", "PASSED")] == 2
    assert c[("tests/rules/test_a.py", "SKIPPED")] == 1
    assert c[("tests/precheck/test_b.py", "PASSED")] == 2
    assert c[("tests/precheck/test_b.py", "FAILED")] == 1
    assert sum(c.values()) == 6


def test_key_groups_by_the_regex_group():
    c = _module().counts(LOG, r"-(9K|11K|30K)\]$")
    assert c[("tests/precheck/test_b.py", "PASSED", "9K")] == 1
    assert c[("tests/precheck/test_b.py", "PASSED", "30K")] == 1
    assert c[("tests/rules/test_a.py", "PASSED", "-")] == 2


def test_script_prints_sorted_lines(tmp_path):
    log = tmp_path / "run.log"
    log.write_text(LOG, encoding="utf-8")
    result = subprocess.run([sys.executable, str(SCRIPT), str(log)], capture_output=True,
                            text=True, check=True)
    assert result.stdout.splitlines() == [
        "tests/precheck/test_b.py FAILED 1",
        "tests/precheck/test_b.py PASSED 2",
        "tests/rules/test_a.py PASSED 2",
        "tests/rules/test_a.py SKIPPED 1",
    ]
