# SPDX-License-Identifier: Apache-2.0
"""Shared fixtures, including `sandbox` (runs a command in the container image)."""

import shutil
import subprocess
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


@pytest.fixture
def report(process, evidence):
    """The margin report of the real process description against the real evidence set."""
    from ws180g_evidence.report import margin_report

    return margin_report(process, evidence)


class Sandbox:
    """Runs commands in the container image through `build/sandbox-run`."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root
        self.runner = repo_root / "build" / "sandbox-run"
        self.image = (repo_root / "docker" / "IMAGE").read_text().splitlines()[0].strip()

    def run(self, cmd: list[str], workdir: Path, mem: str = "4g",
            cpus: int = 2) -> subprocess.CompletedProcess:
        return subprocess.run(
            [str(self.runner), "--mem", mem, "--cpus", str(cpus), "--workdir", str(workdir),
             "--", *cmd],
            capture_output=True, text=True, check=False)


@pytest.fixture
def sandbox(repo_root: Path) -> Sandbox:
    """A `Sandbox`; skips the test when Docker or the image in `docker/IMAGE` is missing."""
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("docker is not installed")
    if subprocess.run([docker, "info"], capture_output=True, check=False).returncode != 0:
        pytest.skip("the docker daemon is not reachable")
    box = Sandbox(repo_root)
    if subprocess.run([docker, "image", "inspect", box.image], capture_output=True,
                      check=False).returncode != 0:
        pytest.skip(f"image {box.image} is not built (run docker/build)")
    return box
