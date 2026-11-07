# SPDX-License-Identifier: Apache-2.0
"""Shared fixtures. Later tasks add `report` and `sandbox` here as their interfaces
appear."""

import shutil
from pathlib import Path

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Create `tmp/` so `--basetemp=tmp/pytest` works on a fresh clone.

    pytest creates the basetemp directory but not its parent, and `tmp/` is
    gitignored, so it is missing in CI."""
    (config.rootpath / "tmp").mkdir(exist_ok=True)


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


@pytest.fixture
def tmp(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def data_copy(repo_root: Path, tmp: Path) -> Path:
    """A writable copy of `process/data/ws180g` for tests that break one key."""
    copy = tmp / "ws180g"
    shutil.copytree(repo_root / "process" / "data" / "ws180g", copy)
    return copy


@pytest.fixture
def process():
    from ws180g_process.load import load_process

    return load_process()


@pytest.fixture
def evidence():
    from ws180g_evidence.load import load_evidence

    return load_evidence()


@pytest.fixture
def gf_entries(evidence):
    """The entries imported from the GF180MCU design-manual tables, by id."""
    return {k: e for k, e in evidence.entries.items() if e.source == "gf180mcu-drm"}
