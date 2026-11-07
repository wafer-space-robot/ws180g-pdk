# SPDX-License-Identifier: Apache-2.0
"""Count the outcomes of a `pytest -v` log by test id, per test file.

Usage: `uv run tools/pytest_log_counts.py LOG [--key REGEX]`. Prints one line
`<file> <outcome> <count>` per file and outcome, sorted. With `--key`, the first group of
`REGEX` searched in each test id is added as a third grouping field (`-` when it does not
match), e.g. `--key '\\[([^/]+)/'` for the rule id of a fixture test, or
`--key='-(9K|11K|30K)\\]$'` (with `=`: the regex starts with `-`) for the `metal_top`
of a retarget case.

The outcome is read by test id, not by line: a test that prints output gets its outcome
word (`PASSED [ 76%]`) on a later line than its id, and a line-based count misses it. The
short test summary (`SKIPPED [21] tests/...`) is not counted, since its bracket holds a
count, not a percentage. Used by the Phase 0 gate report (`docs/phase-0-report.md`)."""

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

TEST_ID = re.compile(r"^(tests/\S+?\.py)::(\S+)")
OUTCOME = re.compile(r"\b(PASSED|FAILED|SKIPPED|ERROR|XFAIL|XPASS)\s+\[\s*\d+%\]")


def outcomes(text: str) -> list[tuple[str, str, str]]:
    """`(file, test name, outcome)` for every test of a `pytest -v` log, in log order."""
    out = []
    current: tuple[str, str] | None = None
    for line in text.splitlines():
        m = TEST_ID.match(line)
        if m:
            current = (m.group(1), m.group(2))
        o = OUTCOME.search(line)
        if o and current is not None:
            out.append((*current, o.group(1)))
            current = None
    return out


def counts(text: str, key: str | None = None) -> Counter:
    """The outcomes of `outcomes(text)` counted by (file, outcome) or, with `key`, by
    (file, outcome, first group of `key` in the test name)."""
    pattern = re.compile(key) if key else None
    c: Counter = Counter()
    for file, name, outcome in outcomes(text):
        if pattern is None:
            c[(file, outcome)] += 1
        else:
            m = pattern.search(name)
            c[(file, outcome, m.group(1) if m else "-")] += 1
    return c


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("log", type=Path, help="a pytest -v log")
    parser.add_argument("--key", help="regex; its first group in the test id is a grouping field")
    args = parser.parse_args(argv)
    c = counts(args.log.read_text(encoding="utf-8"), args.key)
    for fields, n in sorted(c.items()):
        sys.stdout.write(" ".join(fields) + f" {n}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
