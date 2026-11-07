# SPDX-License-Identifier: Apache-2.0
"""The container image: its tools, the PDK deck, the venv, and the limits of build/sandbox-run."""

import json
import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.sandbox

DRC_DECK = "/foss/pdks/gf180mcuD/libs.tech/klayout/tech/drc/gf180mcu.drc"


@pytest.fixture
def versions(repo_root: Path) -> dict[str, str]:
    return json.loads((repo_root / "docker" / "versions.json").read_text())


def test_klayout_version(sandbox, tmp, versions):
    res = sandbox.run(["klayout", "-v"], tmp)
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == f"KLayout {versions['klayout']}"


def test_magic_version(sandbox, tmp, versions):
    res = sandbox.run(["magic", "--version"], tmp)
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == versions["magic"]


def test_netgen_runs(sandbox, tmp, versions):
    res = sandbox.run(["netgen", "-batch", "quit"], tmp)
    assert res.returncode == 0, res.stderr
    assert res.stdout.startswith(f"Netgen {versions['netgen']} ")


def test_ngspice_version(sandbox, tmp, versions):
    res = sandbox.run(["ngspice", "--version"], tmp)
    assert res.returncode == 0, res.stderr
    assert f"** ngspice-{versions['ngspice']} " in res.stdout


def test_gf180mcu_drc_deck_readable(sandbox, tmp):
    res = sandbox.run(["test", "-r", DRC_DECK], tmp)
    assert res.returncode == 0, res.stderr


def test_venv_imports_klayout_and_pydantic(sandbox, tmp, versions):
    res = sandbox.run(["python", "/work/src/tests/sandbox/print_imports.py"], tmp)
    assert res.returncode == 0, res.stderr
    assert res.stdout.splitlines() == [
        "/opt/ws180g/bin/python",
        f"python {versions['python']}",
        f"klayout.db {versions['klayout_python']}",
        "pydantic ok",
    ]


def test_runs_as_invoking_user_with_repo_read_only(sandbox, tmp):
    res = sandbox.run(["sh", "-c", "id -u; id -g; pwd; touch /work/src/x 2>&1 || echo ro"], tmp)
    assert res.returncode == 0, res.stderr
    lines = res.stdout.splitlines()
    assert lines[:3] == [str(os.getuid()), str(os.getgid()), "/work/out"]
    assert lines[-1] == "ro"


def test_workdir_is_writable(sandbox, tmp):
    res = sandbox.run(["sh", "-c", "echo hi > out.txt"], tmp)
    assert res.returncode == 0, res.stderr
    assert (tmp / "out.txt").read_text() == "hi\n"


def test_exit_code_is_the_commands(sandbox, tmp):
    assert sandbox.run(["sh", "-c", "exit 7"], tmp).returncode == 7


def test_no_network(sandbox, tmp):
    res = sandbox.run(["cat", "/proc/net/dev"], tmp)
    assert res.returncode == 0, res.stderr
    interfaces = [line.split(":")[0].strip() for line in res.stdout.splitlines()[2:]]
    assert interfaces == ["lo"]


def test_memory_cap_allows_below(sandbox, tmp):
    """The control case: 256 MiB fits in 1 GiB, so the OOM kill below is the cap's doing."""
    res = sandbox.run(["python", "/work/src/tests/sandbox/alloc.py", "256"], tmp, mem="1g")
    assert res.returncode == 0, res.stderr
    assert res.stdout == "allocated 256 MiB\n"


def test_memory_cap_kills_above(sandbox, tmp):
    res = sandbox.run(["python", "/work/src/tests/sandbox/alloc.py", "2048"], tmp, mem="1g")
    assert res.returncode == 137, (res.returncode, res.stdout, res.stderr)
    assert res.stdout == ""


def test_refuses_repo_root(sandbox, repo_root):
    res = sandbox.run(["true"], repo_root)
    assert res.returncode == 2
    assert "repo root" in res.stderr


def test_refuses_home(sandbox):
    res = sandbox.run(["true"], Path.home())
    assert res.returncode == 2
    assert "$HOME" in res.stderr


def test_refuses_git_common_dir(sandbox, repo_root):
    git_dir = subprocess.run(["git", "-C", str(repo_root), "rev-parse", "--path-format=absolute",
                              "--git-common-dir"], capture_output=True, text=True,
                             check=True).stdout.strip()
    res = sandbox.run(["true"], Path(git_dir))
    assert res.returncode == 2
    assert "git" in res.stderr


def test_refuses_filesystem_root(sandbox):
    res = sandbox.run(["true"], Path("/"))
    assert res.returncode == 2


def test_refuses_source_dir_inside_repo(sandbox, repo_root):
    """Inside the repo only `tmp/` (gitignored scratch) may be written."""
    res = sandbox.run(["true"], repo_root / "process")
    assert res.returncode == 2
