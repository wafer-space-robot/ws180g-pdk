# SPDX-License-Identifier: Apache-2.0
"""Gate check 1, both engines (Task 17): on every Task 14 fixture of a rule that both
KLayout and Magic check, the two engines report the same set of rule ids.

The KLayout results come from the Task 15 runner and the Magic results from the Task 17
runner, both through their session fixtures (one engine run each, or their caches). Magic's
counts are error tiles, so the comparison is of sets of rule ids. Where `MAGIC_EXCEPTIONS`
records that Magic's set differs (`magic_markers(fixture) != set(fixture.markers())`), the
test asserts each engine against its own expected set instead and prints the exception."""

import pytest
from test_klayout_fixtures import FIXTURES, TABLE, deck_dir, klayout_results  # noqa: F401
from test_magic_fixtures import magic_results, tech_dir  # noqa: F401
from ws180g_tech.magic import MAGIC_EXCEPTIONS, magic_markers

BOTH = {r.id for r in TABLE.checkable() if {"klayout", "magic"} <= set(r.engines)}


@pytest.mark.sandbox
@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda f: f"{f.rule_id}/{f.expect}_{f.name}")
def test_engines_agree(fixture, request, capsys):
    if fixture.rule_id not in BOTH:
        pytest.skip("KLayout-only")
    klayout = set(request.getfixturevalue("klayout_results")[fixture.path].violations)
    magic = set(request.getfixturevalue("magic_results")[fixture.path].violations)
    expected = set(fixture.markers())
    if magic_markers(fixture) == expected:
        assert klayout == magic, f"KLayout {sorted(klayout)}, Magic {sorted(magic)}"
        return
    # a recorded Magic exception: each engine against its own expected set
    assert klayout == expected, f"KLayout {sorted(klayout)}, expected {sorted(expected)}"
    assert magic == magic_markers(fixture), f"Magic {sorted(magic)}"
    reason = MAGIC_EXCEPTIONS[(fixture.rule_id, fixture.name)].reason
    with capsys.disabled():
        print(f"\nMAGIC_EXCEPTIONS {fixture.rule_id}/{fixture.expect}_{fixture.name}: "
              f"KLayout {sorted(klayout)}, Magic {sorted(magic)} ({reason})")
