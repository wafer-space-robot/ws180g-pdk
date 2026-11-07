# SPDX-License-Identifier: Apache-2.0
"""Shared fixtures. Later tasks add `data_copy`, `process`, `evidence`, `gf_entries`,
`report` and `sandbox` here as their interfaces appear."""

from pathlib import Path

import pytest


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


@pytest.fixture
def tmp(tmp_path: Path) -> Path:
    return tmp_path
