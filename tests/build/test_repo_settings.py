# SPDX-License-Identifier: Apache-2.0
"""`tools/repo-settings`: the settings files parse and say what the plan requires,
`apply.py --dry-run` prints the command list without running anything, a real run follows
that list, and `verify.py` compares live settings with the files."""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SETTINGS = REPO / "tools" / "repo-settings"
APPLY = SETTINGS / "apply.py"
VERIFY = SETTINGS / "verify.py"
LIBRARIES = ("ws180g005_fd_pr", "ws180g005_fd_io")
META_URL = "https://github.com/wafer-space-robot/ws180g-pdk"
# Keys GitHub adds to what it returns; a settings file holds only what `apply.py` sends.
SERVER_KEYS = {
    "id",
    "node_id",
    "url",
    "_links",
    "created_at",
    "updated_at",
    "source",
    "source_type",
    "current_user_can_bypass",
}


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def apply():
    return _load(APPLY)


@pytest.fixture(scope="module")
def verify(apply):
    sys.path.insert(0, str(SETTINGS))
    try:
        return _load(VERIFY)
    finally:
        sys.path.remove(str(SETTINGS))


def _json(name: str):
    return json.loads((SETTINGS / name).read_text())


def _keys(node):
    if isinstance(node, dict):
        for key, value in node.items():
            yield key
            yield from _keys(value)
    elif isinstance(node, list):
        for value in node:
            yield from _keys(value)


@pytest.mark.parametrize("name", ["repo.json", "protection.json", "ruleset-tags.json"])
def test_settings_hold_no_server_fields(name):
    assert not SERVER_KEYS & set(_keys(_json(name)))


def test_repo_settings():
    repo = _json("repo.json")
    assert repo["has_issues"] is True
    assert (repo["has_wiki"], repo["has_projects"], repo["has_discussions"]) == (False,) * 3
    assert repo["allow_merge_commit"] is True
    assert (repo["allow_squash_merge"], repo["allow_rebase_merge"]) == (False, False)
    assert repo["delete_branch_on_merge"] is True
    security = repo["security_and_analysis"]
    assert security["secret_scanning"] == {"status": "enabled"}
    assert security["secret_scanning_push_protection"] == {"status": "enabled"}
    # Per-repository facts are arguments of apply.py, not shared settings.
    assert not {"name", "description", "private", "visibility"} & set(repo)


def test_protection_settings():
    protection = _json("protection.json")
    assert protection["required_pull_request_reviews"] is not None
    assert protection["enforce_admins"] is True
    assert protection["allow_force_pushes"] is False
    assert protection["allow_deletions"] is False
    # The update call requires these two keys even when they are unset.
    assert protection["required_status_checks"] is None
    assert protection["restrictions"] is None


def test_ruleset_settings():
    ruleset = _json("ruleset-tags.json")
    assert ruleset["name"] == "Enforce vXX.ZZZ version tags"
    assert (ruleset["target"], ruleset["enforcement"]) == ("tag", "active")
    assert ruleset["rules"] == [{"type": "creation"}]
    assert ruleset["bypass_actors"] == []
    ref = ruleset["conditions"]["ref_name"]
    assert ref["include"] == ["refs/tags/*"]
    assert "refs/tags/v[0-9][0-9].[0-9][0-9][0-9]" in ref["exclude"]


def _dry_run(*args: str) -> subprocess.CompletedProcess:
    # An empty PATH: a dry run that tried to start `gh` or `git` would fail.
    env = {**os.environ, "PATH": ""}
    return subprocess.run(
        [sys.executable, str(APPLY), *args, "--dry-run"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_dry_run_prints_the_command_list():
    run = _dry_run("example-owner/example-repo")
    assert run.returncode == 0, run.stderr
    commands = [line for line in run.stdout.splitlines() if not line.startswith("#")]
    assert commands == [
        "gh api repos/example-owner/example-repo",
        "gh repo create example-owner/example-repo --public",
        "gh api repos/example-owner/example-repo/branches/main",
        (
            "gh api --method PATCH repos/example-owner/example-repo "
            "--input tools/repo-settings/repo.json"
        ),
        (
            "gh api --method PUT repos/example-owner/example-repo/branches/main/protection "
            "--input tools/repo-settings/protection.json"
        ),
        "gh api repos/example-owner/example-repo/rulesets",
        (
            "gh api --method POST repos/example-owner/example-repo/rulesets "
            "--input tools/repo-settings/ruleset-tags.json"
        ),
        (
            "gh api --method PUT repos/example-owner/example-repo/rulesets/RULESET_ID "
            "--input tools/repo-settings/ruleset-tags.json"
        ),
    ]
    assert "dry run" in run.stdout.splitlines()[0]


def test_dry_run_with_seed_and_description():
    seed = "tools/repo-settings/seed/ws180g005_fd_pr"
    run = _dry_run(
        "example-owner/ws180g005_fd_pr", "--seed", seed, "--description", "ws180g primitives"
    )
    assert run.returncode == 0, run.stderr
    out = run.stdout
    work = "tmp/repo-settings-seed/ws180g005_fd_pr"
    for command in (
        f"git init --quiet --initial-branch=main {work}",
        f"git -C {work} add --all",
        f"git -C {work} push git@github.com:example-owner/ws180g005_fd_pr.git main",
        (
            "gh api --method PATCH repos/example-owner/ws180g005_fd_pr "
            "-f 'description=ws180g primitives'"
        ),
    ):
        assert command in out.splitlines(), command
    assert f"copy {seed}/README.md and LICENSE" in out


@pytest.mark.parametrize("repo", ["no-slash", "a/b/c", "owner/", "owner/re po", "-o/x"])
def test_bad_repository_argument(repo):
    run = _dry_run(repo)
    assert run.returncode == 2
    assert run.stdout == ""


class FakeGh:
    """Stands in for `apply.run`: answers the reads from `state`, records every command."""

    def __init__(self, exists: bool, main: bool, rulesets: list[dict]):
        self.exists, self.main, self.rulesets = exists, main, rulesets
        self.calls: list[list[str]] = []

    def __call__(self, argv, *, ok_missing=False, cwd=None):
        self.calls.append([str(a) for a in argv])
        text = " ".join(self.calls[-1])
        if text.startswith("gh repo create"):
            self.exists = True
        if " push " in text:
            self.main = True
        if text.startswith("gh api repos/") and "--method" not in text:
            if text.endswith("/rulesets"):
                return json.dumps(self.rulesets)
            found = self.main if text.endswith("/branches/main") else self.exists
            if not found:
                assert ok_missing
                return None
        return "{}"


def _methods(calls):
    return [" ".join(c[:5]) for c in calls if "--method" in c]


def test_apply_to_an_existing_repository_only_reapplies_settings(apply, monkeypatch):
    name = "Enforce vXX.ZZZ version tags"
    fake = FakeGh(exists=True, main=True, rulesets=[{"id": 7, "name": name}])
    monkeypatch.setattr(apply, "run", fake)
    assert apply.main(["o/r"]) == 0
    assert not any(c[:3] == ["gh", "repo", "create"] or c[0] == "git" for c in fake.calls)
    assert _methods(fake.calls) == [
        "gh api --method PATCH repos/o/r",
        "gh api --method PUT repos/o/r/branches/main/protection",
        "gh api --method PUT repos/o/r/rulesets/7",
    ]


def test_apply_creates_and_seeds_a_missing_repository(apply, monkeypatch, tmp_path):
    seed = tmp_path / "seed"
    seed.mkdir()
    (seed / "README.md").write_text("# r\n")
    fake = FakeGh(exists=False, main=False, rulesets=[])
    monkeypatch.setattr(apply, "run", fake)
    monkeypatch.setattr(apply, "WORK", tmp_path / "work")
    assert apply.main(["o/r", "--seed", str(seed), "--description", "d"]) == 0
    work = tmp_path / "work" / "r"
    assert ["gh", "repo", "create", "o/r", "--public"] in fake.calls
    assert ["git", "-C", str(work), "push", "git@github.com:o/r.git", "main"] in fake.calls
    # The seed is in place when git commits it: the README and the meta-repository's licence.
    assert not work.exists()
    order = [c[0] if c[0] == "git" else " ".join(c[:3]) for c in fake.calls]
    assert order.index("gh repo create") < order.index("git") < len(order) - 1
    assert _methods(fake.calls)[-1] == "gh api --method POST repos/o/r/rulesets"
    assert ["gh", "api", "--method", "PATCH", "repos/o/r", "-f", "description=d"] in fake.calls


def test_apply_refuses_a_repository_without_main_and_without_seed(apply, monkeypatch, capsys):
    fake = FakeGh(exists=False, main=False, rulesets=[])
    monkeypatch.setattr(apply, "run", fake)
    assert apply.main(["o/r"]) == 1
    assert "--seed" in capsys.readouterr().err
    # Nothing was created or changed.
    assert all(c[:2] == ["gh", "api"] and "--method" not in c for c in fake.calls)


@pytest.mark.parametrize("library", LIBRARIES)
def test_seed_readme(library):
    text = (SETTINGS / "seed" / library / "README.md").read_text()
    assert text.startswith(f"# {library}")
    assert META_URL in text
    assert "generated by the build" in text
    assert "not be edited by hand" in " ".join(text.split())


def test_verify_reports_differences(verify):
    repo, protection, ruleset = (
        _json(n) for n in ("repo.json", "protection.json", "ruleset-tags.json")
    )
    live_protection = {
        key: ({"enabled": value} if isinstance(value, bool) else value)
        for key, value in protection.items()
        if value is not None
    }
    live_protection["url"] = "https://example.invalid"
    live_ruleset = {**ruleset, "id": 7, "node_id": "x"}
    live_repo = {**repo, "id": 1, "name": "r"}
    assert verify.differences(live_repo, live_protection, [live_ruleset]) == []

    live_repo["has_wiki"] = True
    live_protection["enforce_admins"] = {"enabled": False}
    live_protection["restrictions"] = {"users": []}
    live_ruleset["rules"] = []
    found = verify.differences(live_repo, live_protection, [live_ruleset])
    assert [d.split(":")[0] for d in found] == [
        "repo.has_wiki",
        "protection.enforce_admins",
        "protection.restrictions",
        "ruleset.rules",
    ]
    assert verify.differences(live_repo, live_protection, [])[-1].startswith("ruleset: no")
