# SPDX-License-Identifier: Apache-2.0
"""Rebuilding the image gives the config digest committed in docker/IMAGE_ID."""

import subprocess
from pathlib import Path

import pytest

pytestmark = [pytest.mark.sandbox, pytest.mark.slow]


def test_rebuild_matches_image_id(sandbox, repo_root: Path):
    res = subprocess.run([str(repo_root / "docker" / "build"), "--tag", "ws180g-pdk-base:verify"],
                         capture_output=True, text=True, check=False)
    assert res.returncode == 0, res.stderr[-4000:]
    want = (repo_root / "docker" / "IMAGE_ID").read_text().strip()
    assert res.stdout.strip() == want
