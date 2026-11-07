# SPDX-License-Identifier: Apache-2.0
"""Gate check 2 (Task 18): which per-rule pass fixtures must pass the public GF180MCU deck
once retargeted, shared by the test (`tests/precheck/test_fixture_retarget.py`) and the
build (`ws180g-build`).

`EXCLUDED` holds the pass fixtures excluded under policy (c) of
`docs/phase-0-retarget-log.md`, `(rule id, name)` -> (GF rule, reason). `write_regressions`
writes the permanent regression fixtures of `ws180g_precheck.regressions`, which both also
run."""

import importlib
import pkgutil
from pathlib import Path

from ws180g_process.model import Process
from ws180g_rules.fixtures import Fixture

from ws180g_precheck import regressions

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


def regression_names() -> list[str]:
    """The modules of `ws180g_precheck.regressions`, sorted by name."""
    return sorted(m.name for m in pkgutil.iter_modules(regressions.__path__))


def write_regressions(process: Process, out_dir: Path) -> dict[str, Path]:
    """Write every regression module's layout to `out_dir/<module>.gds`; return the paths
    by case id, `regressions/<module>`, in `regression_names()` order."""
    out = {}
    for name in regression_names():
        module = importlib.import_module(f"{regressions.__name__}.{name}")
        out[f"regressions/{name}"] = module.build(process, Path(out_dir) / f"{name}.gds")
    return out
