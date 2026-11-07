# SPDX-License-Identifier: Apache-2.0
"""Shared fixtures. Later tasks add `evidence`, `gf_entries`,
`report` and `sandbox` here as their interfaces appear."""

import shutil
from pathlib import Path

import pytest


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
