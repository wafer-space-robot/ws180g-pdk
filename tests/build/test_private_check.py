# SPDX-License-Identifier: Apache-2.0
"""Private-data checker, its console script and the git hooks.

The trigger words are built at runtime so this file never contains them."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from helpers import set_toml
from ws180g_build.private_check import Finding, check_private, main

MARKER = "CONFI" + "DENTIAL"
SHORT = "N" + "DA"


@pytest.fixture(autouse=True)
def _no_outer_git(monkeypatch):
    """The suite may run from inside a git hook; keep the outer repository's index away."""
    for name in ("GIT_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE", "GIT_COMMON_DIR"):
        monkeypatch.delenv(name, raising=False)


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


@pytest.fixture
def mini(repo_root: Path, tmp: Path) -> Path:
    """A git repository holding a copy of the evidence and process data, everything staged."""
    root = tmp / "repo"
    for part in ("evidence/data", "evidence/sources", "process/data"):
        shutil.copytree(repo_root / part, root / part)
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    return root


def _add(root: Path, rel: str, text: str | bytes) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_text(text)
    _git(root, "add", "-f", rel)


def test_mini_repo_is_clean(mini):
    assert check_private(mini) == []


def test_real_repository_has_no_findings(repo_root):
    assert check_private(repo_root) == []


def test_unregistered_source_names_the_entry(mini):
    source = "no" + "where"
    _add(mini, "evidence/data/extra.toml",
         f'[[entry]]\nid = "{source}/R1"\nsource = "{source}"\nrule = "R1"\n'
         'kind = "min-width"\ncite = "test"\n')
    findings = check_private(mini)
    assert len(findings) == 1
    (f,) = findings
    assert f.path == "evidence/data/extra.toml"
    assert f.line == 2
    assert f"{source}/R1" in f.reason and source in f.reason


def test_source_without_url(mini):
    set_toml(mini / "evidence/data/sources.toml", ["sources", "onc18", "url"], "")
    findings = check_private(mini)
    assert [(f.path, "onc18" in f.reason, "url" in f.reason) for f in findings] == [
        ("evidence/data/sources.toml", True, True)]


def test_source_not_public(mini):
    set_toml(mini / "evidence/data/sources.toml", ["sources", "onc18", "public"], False)
    findings = check_private(mini)
    assert len(findings) == 1
    assert "onc18" in findings[0].reason and "public" in findings[0].reason


def test_field_citing_missing_evidence(mini):
    path = mini / "process/data/ws180g/process.toml"
    path.write_text(path.read_text().replace('"gf180mcu-drm/GRID"', '"gf180mcu-drm/NOPE.1"'))
    findings = check_private(mini)
    assert len(findings) == 1
    (f,) = findings
    assert f.path == "process/data/ws180g/process.toml"
    assert f.line == 10
    assert "gf180mcu-drm/NOPE.1" in f.reason


def test_provenance_outside_the_allowed_set(mini):
    set_toml(mini / "process/data/ws180g/process.toml", ["grid", "provenance"], "pri" + "vate")
    findings = check_private(mini)
    reasons = [f.reason for f in findings if f.path == "process/data/ws180g/process.toml"]
    assert any("provenance" in r and "grid" in r for r in reasons)
    # The text scan catches the same line as well.
    assert any(f.line == 9 and "matches" in f.reason for f in findings)


def test_marker_in_a_tracked_file(mini):
    _add(mini, "notes.txt", f"first line\nthis is {MARKER} stuff\n")
    assert check_private(mini) == [
        Finding("notes.txt", 2, f"matches \\b{MARKER.lower()}\\b")]


def test_patterns_are_case_insensitive_and_word_bounded(mini):
    _add(mini, "a.md", f"under an {SHORT.lower()}\n")
    _add(mini, "b.md", f"{SHORT}s and x{SHORT}y are fine\n")
    assert [(f.path, f.line) for f in check_private(mini)] == [("a.md", 1)]


def test_marker_like_words_are_fine(mini):
    _add(mini, "c.txt", "the mk_boundary layer\nstandard cells\n")
    assert check_private(mini) == []


def test_untracked_binary_and_tmp_files_are_skipped(mini):
    (mini / "loose.txt").write_text(f"{MARKER}\n")
    _add(mini, "blob.bin", b"\x00\x01" + MARKER.encode() + b"\n")
    _add(mini, "tmp/scratch.txt", f"{MARKER}\n")
    assert check_private(mini) == []


def test_allow_list_suppresses_exactly_the_listed_line(mini):
    allowed = f"we never copy {SHORT} material"
    _add(mini, "docs/spec.md", f"{allowed}\n{allowed}, really\n")
    _add(mini, "other.md", f"{allowed}\n")
    _add(mini, "build/private-allow.txt",
         f"# the spec states the rule itself\ndocs/*.md: {allowed}\n")
    assert [(f.path, f.line) for f in check_private(mini)] == [
        ("docs/spec.md", 2), ("other.md", 1)]


def test_stale_and_malformed_allow_entries(mini):
    _add(mini, "build/private-allow.txt", "# comment\ndocs/*.md: no such line\nno separator\n")
    findings = check_private(mini)
    assert [(f.path, f.line) for f in findings] == [
        ("build/private-allow.txt", 2), ("build/private-allow.txt", 3)]
    assert "matches no line" in findings[0].reason
    assert "<path glob>: <exact line text>" in findings[1].reason


def test_allow_list_comment_is_scanned(mini):
    _add(mini, "build/private-allow.txt", f"# about {SHORT} text\n")
    assert [(f.path, f.line) for f in check_private(mini)] == [("build/private-allow.txt", 1)]


def test_vendored_file_with_wrong_sha256(mini):
    csv = mini / "evidence/sources/gf180mcu-drm/16_Poly2_42.csv"
    csv.write_text(csv.read_text() + "x\n")
    findings = check_private(mini)
    assert len(findings) == 1
    assert findings[0].path == "evidence/sources/gf180mcu-drm/16_Poly2_42.csv"
    assert "sha256" in findings[0].reason


def test_vendored_file_missing(mini):
    (mini / "evidence/sources/gf180mcu-drm/LICENSE").unlink()
    findings = check_private(mini)
    assert [(f.path, "missing" in f.reason) for f in findings] == [
        ("evidence/sources/gf180mcu-drm/LICENSE", True)]


def test_finding_str():
    assert str(Finding("a.md", 3, "why")) == "a.md:3: why"
    assert str(Finding("a.md", None, "why")) == "a.md: why"


def test_main_exit_codes(mini, capsys):
    assert main([str(mini)]) == 0
    _add(mini, "notes.txt", f"{MARKER}\n")
    assert main([str(mini)]) == 1
    assert "notes.txt:1:" in capsys.readouterr().out


def _hook_env(repo_root: Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    return env | {"WS180G_PROJECT": str(repo_root)}


def test_pre_commit_hook(repo_root, mini):
    hook = repo_root / "tools/git-hooks/pre-commit"
    clean = subprocess.run([str(hook)], cwd=mini, env=_hook_env(repo_root),
                           capture_output=True, text=True, check=False)
    assert clean.returncode == 0, clean.stdout + clean.stderr
    _add(mini, "notes.txt", f"{MARKER}\n")
    dirty = subprocess.run([str(hook)], cwd=mini, env=_hook_env(repo_root),
                           capture_output=True, text=True, check=False)
    assert dirty.returncode == 1, dirty.stdout + dirty.stderr
    assert "notes.txt:1:" in dirty.stdout


def test_install_hooks_is_idempotent(repo_root, tmp):
    root = tmp / "hooked"
    shutil.copytree(repo_root / "tools", root / "tools")
    _git(root, "init", "-q")
    for _ in range(2):
        run = subprocess.run([str(root / "tools/install-hooks")], cwd=root,
                             env=_hook_env(repo_root), capture_output=True, text=True,
                             check=False)
        assert run.returncode == 0, run.stdout + run.stderr
    link = root / ".git/hooks/pre-commit"
    assert link.is_symlink()
    assert link.resolve() == (root / "tools/git-hooks/pre-commit").resolve()


def test_cached_sees_a_partially_staged_marker(mini):
    _add(mini, "notes.txt", f"first line\nthis is {MARKER} stuff\n")
    (mini / "notes.txt").write_text("first line\nclean now\n")
    assert check_private(mini) == []
    assert [(f.path, f.line) for f in check_private(mini, cached=True)] == [("notes.txt", 2)]


def test_cached_scans_a_staged_but_deleted_file(mini):
    _add(mini, "notes.txt", f"{MARKER}\n")
    (mini / "notes.txt").unlink()
    assert check_private(mini) == []
    assert [(f.path, f.line) for f in check_private(mini, cached=True)] == [("notes.txt", 1)]


def test_cached_reads_the_staged_evidence(mini):
    assert check_private(mini, cached=True) == []
    set_toml(mini / "evidence/data/sources.toml", ["sources", "onc18", "url"], "")
    assert check_private(mini, cached=True) == []
    _git(mini, "add", "evidence/data/sources.toml")
    assert [f.path for f in check_private(mini, cached=True)] == ["evidence/data/sources.toml"]


def test_cached_reads_the_staged_process(mini):
    path = mini / "process/data/ws180g/process.toml"
    path.write_text(path.read_text().replace('"gf180mcu-drm/GRID"', '"gf180mcu-drm/NOPE.1"'))
    assert check_private(mini, cached=True) == []
    _git(mini, "add", "process/data/ws180g/process.toml")
    assert [(f.path, f.line) for f in check_private(mini, cached=True)] == [
        ("process/data/ws180g/process.toml", 10)]


def test_cached_hashes_the_staged_vendored_bytes(mini):
    rel = "evidence/sources/gf180mcu-drm/16_Poly2_42.csv"
    (mini / rel).write_text((mini / rel).read_text() + "x\n")
    assert check_private(mini, cached=True) == []
    _git(mini, "add", rel)
    assert [f.path for f in check_private(mini, cached=True)] == [rel]
    (mini / rel).unlink()
    assert [f.path for f in check_private(mini, cached=True)] == [rel]


def test_real_repository_index_has_no_findings(repo_root):
    assert check_private(repo_root, cached=True) == []


def test_main_cached(mini, capsys):
    _add(mini, "notes.txt", f"{MARKER}\n")
    (mini / "notes.txt").write_text("clean\n")
    assert main([str(mini)]) == 0
    assert main(["--cached", str(mini)]) == 1
    assert "notes.txt:1:" in capsys.readouterr().out


def test_allow_entry_needs_a_comment_above(mini):
    allowed = f"we never copy {SHORT} material"
    _add(mini, "docs/spec.md", f"{allowed}\n")
    _add(mini, "build/private-allow.txt", f"# why\n\ndocs/*.md: {allowed}\n")
    findings = check_private(mini)
    assert [(f.path, f.line) for f in findings] == [("build/private-allow.txt", 3)]
    assert "comment" in findings[0].reason


@pytest.mark.parametrize("entry", ["docs/*.md: ", "docs/*.md:", ": some text"])
def test_allow_entry_with_empty_text_or_glob(mini, entry):
    _add(mini, "build/private-allow.txt", f"# why\n{entry}\n")
    findings = check_private(mini)
    assert [(f.path, f.line) for f in findings] == [("build/private-allow.txt", 2)]
    assert "<path glob>: <exact line text>" in findings[0].reason


@pytest.mark.parametrize("encoding", ["utf-16", "utf-16-be"])
def test_utf16_text_with_a_bom_is_scanned(mini, encoding):
    text = f"ok\n{MARKER}\n"
    data = text.encode(encoding)
    if encoding == "utf-16-be":
        data = b"\xfe\xff" + data
    _add(mini, "notes.txt", data)
    assert [(f.path, f.line) for f in check_private(mini)] == [("notes.txt", 2)]
    assert [(f.path, f.line) for f in check_private(mini, cached=True)] == [("notes.txt", 2)]


def test_pre_commit_hook_checks_the_index(repo_root, mini):
    hook = repo_root / "tools/git-hooks/pre-commit"
    _add(mini, "notes.txt", f"{MARKER}\n")
    (mini / "notes.txt").write_text("clean\n")
    run = subprocess.run([str(hook)], cwd=mini, env=_hook_env(repo_root),
                         capture_output=True, text=True, check=False)
    assert run.returncode == 1, run.stdout + run.stderr
    assert "notes.txt:1:" in run.stdout


def _hooked_repo(repo_root: Path, tmp: Path) -> Path:
    root = tmp / "hooked"
    shutil.copytree(repo_root / "tools", root / "tools")
    _git(root, "init", "-q")
    return root


def _install(root: Path, repo_root: Path) -> subprocess.CompletedProcess:
    return subprocess.run([str(root / "tools/install-hooks")], cwd=root,
                          env=_hook_env(repo_root), capture_output=True, text=True,
                          check=False)


def test_install_hooks_honours_core_hooks_path(repo_root, tmp):
    root = _hooked_repo(repo_root, tmp)
    _git(root, "config", "core.hooksPath", "myhooks")
    run = _install(root, repo_root)
    assert run.returncode == 0, run.stdout + run.stderr
    assert (root / "myhooks/pre-commit").is_symlink()
    assert not (root / ".git/hooks/pre-commit").exists()


def test_install_hooks_refuses_a_linked_worktree(repo_root, tmp):
    root = _hooked_repo(repo_root, tmp)
    _git(root, "add", "tools")
    _git(root, "-c", "user.name=t", "-c", "user.email=t@example.invalid",
         "commit", "-q", "-m", "tools")
    linked = tmp / "linked"
    _git(root, "worktree", "add", "-q", str(linked))
    run = _install(linked, repo_root)
    assert run.returncode != 0
    assert "main checkout" in run.stderr
    assert not (root / ".git/hooks/pre-commit").exists()
