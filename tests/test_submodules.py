# SPDX-License-Identifier: Apache-2.0
"""The library repositories are submodules under `libraries/`.

These tests read `.gitmodules` and the index only, never a submodule's content: a plain
`actions/checkout` (what CI does) leaves each submodule as an empty directory, and the suite
must pass there. They also check that the tools which walk the repository cope with both
states of a submodule, empty and checked out."""

import configparser
import subprocess
from pathlib import Path

import pytest
from ws180g_build.naming import check_tree, parse_library
from ws180g_build.private_check import check_private

REPO = Path(__file__).resolve().parents[1]
LIBRARIES = ("ws180g005_fd_io", "ws180g005_fd_pr")
OWNER_URL = "https://github.com/wafer-space-robot"


@pytest.fixture(autouse=True)
def _no_outer_git(monkeypatch):
    """The suite may run from inside a git hook; keep the outer repository's index away."""
    for name in ("GIT_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE", "GIT_COMMON_DIR"):
        monkeypatch.delenv(name, raising=False)


def _gitmodules() -> dict[str, dict[str, str]]:
    parser = configparser.ConfigParser()
    parser.read_string((REPO / ".gitmodules").read_text())
    return {section: dict(parser[section]) for section in parser.sections()}


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(REPO), *args], check=True, capture_output=True, text=True
    ).stdout


def test_gitmodules_lists_exactly_the_two_libraries():
    modules = _gitmodules()
    assert sorted(modules) == [f'submodule "libraries/{name}"' for name in LIBRARIES]
    for name in LIBRARIES:
        assert modules[f'submodule "libraries/{name}"'] == {
            "path": f"libraries/{name}",
            "url": f"{OWNER_URL}/{name}.git",
        }


@pytest.mark.parametrize("name", LIBRARIES)
def test_library_name_parses(name):
    library = parse_library(name)
    assert (library.process, library.source, library.name) == ("ws180g005", "fd", None)
    assert library.type == name.rsplit("_", 1)[1]


def test_index_holds_a_commit_link_for_each_library():
    """Mode 160000 with a full commit id, for exactly the paths of `.gitmodules`."""
    entries = [line.split() for line in _git("ls-files", "-s", "libraries").splitlines()]
    links = {path: sha for mode, sha, _stage, path in entries if mode == "160000"}
    assert sorted(links) == [f"libraries/{name}" for name in LIBRARIES]
    assert all(len(sha) == 40 and set(sha) != {"0"} for sha in links.values())
    # Everything else under libraries/ is the README.
    assert [e[3] for e in entries if e[0] != "160000"] == ["libraries/README.md"]


def test_libraries_readme():
    text = (REPO / "libraries" / "README.md").read_text()
    for name in LIBRARIES:
        assert f"`{name}`" in text
    assert "ws180g005_fd_sc_gp<N>t5v0" in text
    assert "Phase 1" in text
    assert "git submodule update --init" in text


def test_checkers_pass_with_the_submodules():
    """Whether the submodules are empty directories or checked out."""
    assert check_tree(REPO) == []
    assert [f for f in check_private(REPO) if f.path.startswith("libraries/")] == []
    assert [f for f in check_private(REPO, cached=True) if f.path.startswith("libraries/")] == []
