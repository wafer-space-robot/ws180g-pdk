# SPDX-License-Identifier: Apache-2.0
"""Gate check 2 (Task 18): which per-rule pass fixtures must pass the public GF180MCU deck
once retargeted, shared by the test (`tests/precheck/test_fixture_retarget.py`) and the
build (`ws180g-build`).

`EXCLUDED` holds the pass fixtures excluded under policy (c) of
`docs/phase-0-retarget-log.md`, `(rule id, name)` -> (GF rule, reason)."""

from ws180g_rules.fixtures import Fixture

_DN3 = ("DN.3", ("each DNWELL must be directly surrounded by a PCOMP guard ring tied to the "
        "substrate; the dnw fixtures draw a bare deep n-well, and the ring topology is the "
        "deep-n-well module's open item"))
EXCLUDED: dict[tuple[str, str], tuple[str, str]] = {
    ("dnw.w", "min"): _DN3,
    ("dnw.w", "min_plus_grid"): _DN3,
    ("dnw.s", "min"): _DN3,
    ("dnw.s", "min_plus_grid"): _DN3,
}


def gate_fixtures(fixtures: list[Fixture]) -> list[Fixture]:
    """The pass fixtures of `fixtures` that gate check 2 runs (those not in `EXCLUDED`), in
    their order."""
    return [f for f in fixtures
            if f.expect == "pass" and (f.rule_id, f.name) not in EXCLUDED]
