# SPDX-License-Identifier: Apache-2.0
"""build/sandbox-run's checks of its options and workdir (no Docker: `--check-only`)."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
       "-c", "commit.gpgsign=false", "-c", "init.defaultBranch=main"]


def check(runner: Path, workdir: Path, *opts: str) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    return subprocess.run([str(runner), *opts, "--check-only", "--workdir", str(workdir),
                           "--", "true"], capture_output=True, text=True, check=False, env=env)


@pytest.fixture
def layout(repo_root: Path, tmp: Path) -> dict[str, Path]:
    """A main checkout with two worktrees; the runner is copied into the first worktree."""
    main, wt, wt2 = tmp / "main", tmp / "wt", tmp / "wt2"
    for d in ("process", "tmp/x"):
        (main / d).mkdir(parents=True)
    subprocess.run([*GIT, "init", "-q", str(main)], check=True)
    subprocess.run([*GIT, "-C", str(main), "commit", "-q", "--allow-empty", "-m", "init"],
                   check=True)
    for w, branch in ((wt, "a"), (wt2, "b")):
        subprocess.run([*GIT, "-C", str(main), "worktree", "add", "-q", "-b", branch, str(w)],
                       check=True)
        for d in ("process", "tmp/x"):
            (w / d).mkdir(parents=True)
    (wt / "build").mkdir()
    (wt / "docker").mkdir()
    shutil.copy2(repo_root / "build" / "sandbox-run", wt / "build" / "sandbox-run")
    (wt / "docker" / "IMAGE").write_text("ws180g-pdk-base:local\n")
    return {"main": main, "wt": wt, "wt2": wt2, "runner": wt / "build" / "sandbox-run"}


@pytest.mark.parametrize("rel", ["wt/tmp/x", "main/tmp/x", "wt2/tmp/x"])
def test_scratch_dirs_accepted(layout, tmp, rel):
    res = check(layout["runner"], tmp / rel)
    assert res.returncode == 0, res.stderr


@pytest.mark.parametrize("rel,why", [
    ("wt/process", "repo root"),
    ("wt", "repo root"),
    ("main/process", "main git checkout"),
    ("main", "git common dir"),
    ("wt2/process", "git worktree"),
    ("wt2", "git worktree"),
    ("main/.git", "git common dir"),
    ("main/.git/hooks", "git common dir"),
    (".", "ancestor"),
])
def test_checkouts_refused(layout, tmp, rel, why):
    res = check(layout["runner"], tmp / rel)
    assert res.returncode == 2
    assert why in res.stderr


def test_primary_checkout_source_refused_from_this_checkout(repo_root):
    """Integration check with this host's real layout: from a worktree, the main checkout's
    sources are not a workdir."""
    common = subprocess.run(["git", "-C", str(repo_root), "rev-parse", "--path-format=absolute",
                             "--git-common-dir"], capture_output=True, text=True,
                            check=True).stdout.strip()
    main = Path(common).parent
    if main.resolve() == repo_root.resolve():
        pytest.skip("not run from a worktree")
    res = check(repo_root / "build" / "sandbox-run", main / "process")
    assert res.returncode == 2
    assert "main git checkout" in res.stderr


@pytest.mark.parametrize("opts", [["--cpus", "0"], ["--cpus", "0.0"], ["--cpus", "-1"],
                                  ["--cpus", str((os.cpu_count() or 1) + 1)],
                                  ["--mem", "17g"], ["--mem", "16385m"], ["--mem", "0g"],
                                  ["--mem", "4"], ["--pids", "0"]])
def test_caps_cannot_be_removed(layout, tmp, opts):
    res = check(layout["runner"], tmp / "wt/tmp/x", *opts)
    assert res.returncode == 2
    assert res.stdout == ""


@pytest.mark.parametrize("opts", [["--cpus", "0.5"], ["--cpus", str(os.cpu_count() or 1)],
                                  ["--mem", "16g"], ["--mem", "512m"]])
def test_caps_in_range_accepted(layout, tmp, opts):
    res = check(layout["runner"], tmp / "wt/tmp/x", *opts)
    assert res.returncode == 0, res.stderr


@pytest.mark.sandbox
def test_image_id_mismatch_refused(sandbox, layout, tmp):
    """The local image must have the ID in docker/IMAGE_ID (here a wrong one)."""
    (layout["wt"] / "docker" / "IMAGE_ID").write_text("sha256:" + "0" * 64 + "\n")
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    res = subprocess.run([str(layout["runner"]), "--workdir", str(tmp / "wt/tmp/x"), "--", "true"],
                         capture_output=True, text=True, check=False, env=env)
    assert res.returncode == 2
    assert "docker/IMAGE_ID" in res.stderr
