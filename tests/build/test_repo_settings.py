# SPDX-License-Identifier: Apache-2.0
"""`tools/repo-settings`: the settings files parse and say what the plan requires,
`apply.py --dry-run` prints the command list without running anything, a real run follows
that list, and `verify.py` compares live settings with the files."""

import importlib.util
import json
import os
import shlex
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
    """In the order of a real run: both reads come before the create."""
    run = _dry_run("example-owner/example-repo")
    assert run.returncode == 0, run.stderr
    lines = run.stdout.splitlines()
    commands = [line for line in lines if not line.startswith("#")]
    assert commands == [
        "gh api repos/example-owner/example-repo",
        "gh api repos/example-owner/example-repo/branches/main",
        "gh repo create example-owner/example-repo --public",
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
    assert "dry run" in lines[0]
    read_main = lines.index("gh api repos/example-owner/example-repo/branches/main")
    assert lines[read_main - 1].startswith("# only if the repository exists")


@pytest.mark.parametrize("library", LIBRARIES)
def test_dry_run_with_seed(library):
    """The message and the description come from the committed seed directory."""
    seed = f"tools/repo-settings/seed/{library}"
    run = _dry_run(f"example-owner/{library}", "--seed", seed)
    assert run.returncode == 0, run.stderr
    out = run.stdout
    work = f"tmp/repo-settings-seed/{library}"
    description = (REPO / seed / "description.txt").read_text().strip()
    for command in (
        f"git init --quiet --initial-branch=main {work}",
        f"git -C {work} add --all",
        f"git -C {work} commit --quiet -F {seed}/commit-message.txt",
        f"git -C {work} push git@github.com:example-owner/{library}.git main",
        shlex.join(
            ["gh", "api", "--method", "PATCH", f"repos/example-owner/{library}"]
            + ["-f", f"description={description}"]
        ),
    ):
        assert command in out.splitlines(), command
    assert f"copy {seed}/files/README.md and LICENSE" in out


@pytest.mark.parametrize(
    "repo", ["no-slash", "a/b/c", "owner/", "owner/re po", "-o/x", "owner/.", "owner/..", "o/..."]
)
def test_bad_repository_argument(repo):
    run = _dry_run(repo)
    assert run.returncode == 2
    assert run.stdout == ""


@pytest.mark.parametrize("repo", ["owner/.github", "owner/a.b", "wafer-space-robot/ws180g-pdk"])
def test_good_repository_argument(repo):
    assert _dry_run(repo).returncode == 0


class _Done:
    def __init__(self, returncode: int, stderr: str = ""):
        self.returncode, self.stdout, self.stderr = returncode, "", stderr


@pytest.mark.parametrize(
    ("stderr", "missing", "expected"),
    [
        ("gh: Not Found (HTTP 404)\n", (404,), None),
        ("gh: Git Repository is empty. (HTTP 409)\n", (404, 409), None),
        ("gh: Git Repository is empty. (HTTP 409)\n", (404,), SystemExit),
        ("gh: Not Found (HTTP 404)\n", (), SystemExit),
        ("gh: Forbidden (HTTP 403)\n", (404, 409), SystemExit),
    ],
)
def test_run_treats_only_the_named_statuses_as_missing(
    apply, monkeypatch, stderr, missing, expected
):
    monkeypatch.setattr(apply.subprocess, "run", lambda *a, **k: _Done(1, stderr))
    if expected is None:
        assert apply.run(["gh", "api", "x"], missing=missing) is None
    else:
        with pytest.raises(SystemExit):
            apply.run(["gh", "api", "x"], missing=missing)


class FakeGh:
    """Stands in for `apply.run`: answers the reads from its state, records every command.

    A missing repository answers 404; a missing `main` answers `no_main` (GitHub answers
    some reads of an empty repository with 409)."""

    def __init__(self, exists: bool, main: bool, rulesets: list[dict], no_main: int = 404):
        self.exists, self.main, self.rulesets, self.no_main = exists, main, rulesets, no_main
        self.calls: list[list[str]] = []

    def __call__(self, argv, *, missing=(), cwd=None):
        self.calls.append([str(a) for a in argv])
        text = " ".join(self.calls[-1])
        if text.startswith("gh repo create"):
            self.exists = True
        if " push " in text:
            self.main = True
        if text.startswith("gh api repos/") and "--method" not in text:
            if text.endswith("/rulesets"):
                return json.dumps(self.rulesets)
            is_main = text.endswith("/branches/main")
            if not (self.main if is_main else self.exists):
                assert (self.no_main if is_main else 404) in missing
                return None
        return "{}"


def _methods(calls):
    return [" ".join(c[:5]) for c in calls if "--method" in c]


def _seed(tmp_path: Path, description: str | None = "d", message: str | None = None) -> Path:
    seed = tmp_path / "seed"
    (seed / "files").mkdir(parents=True)
    (seed / "files" / "README.md").write_text("# r\n")
    if description is not None:
        (seed / "description.txt").write_text(description + "\n")
    if message is not None:
        (seed / "commit-message.txt").write_text(message + "\n")
    return seed


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
    seed = _seed(tmp_path, message="first")
    fake = FakeGh(exists=False, main=False, rulesets=[])
    monkeypatch.setattr(apply, "run", fake)
    monkeypatch.setattr(apply, "WORK", tmp_path / "work")
    copied = {}

    def spy(argv, **kwargs):
        if list(argv[:1]) == ["git"] and "commit" in argv:
            work = tmp_path / "work" / "r"
            copied["files"] = sorted(p.name for p in work.iterdir())
        return fake(argv, **kwargs)

    monkeypatch.setattr(apply, "run", spy)
    assert apply.main(["o/r", "--seed", str(seed)]) == 0
    work = tmp_path / "work" / "r"
    # Only files/ and the licence are committed, not the description or the message.
    assert copied["files"] == ["LICENSE", "README.md"]
    assert ["gh", "repo", "create", "o/r", "--public"] in fake.calls
    commit = ["git", "-C", str(work), "commit", "--quiet", "-F"]
    assert [*commit, str(seed / "commit-message.txt")] in fake.calls
    assert ["git", "-C", str(work), "push", "git@github.com:o/r.git", "main"] in fake.calls
    assert not work.exists()
    order = [c[0] if c[0] == "git" else " ".join(c[:3]) for c in fake.calls]
    assert order.index("gh repo create") < order.index("git") < len(order) - 1
    assert _methods(fake.calls)[-1] == "gh api --method POST repos/o/r/rulesets"
    assert ["gh", "api", "--method", "PATCH", "repos/o/r", "-f", "description=d"] in fake.calls


@pytest.mark.parametrize("no_main", [404, 409])
def test_apply_seeds_an_existing_repository_without_main(apply, monkeypatch, tmp_path, no_main):
    """The state a first run leaves when it fails between the create and the push."""
    seed = _seed(tmp_path, description=None)
    fake = FakeGh(exists=True, main=False, rulesets=[], no_main=no_main)
    monkeypatch.setattr(apply, "run", fake)
    monkeypatch.setattr(apply, "WORK", tmp_path / "work")
    assert apply.main(["o/r", "--seed", str(seed)]) == 0
    work = tmp_path / "work" / "r"
    assert not any(c[:3] == ["gh", "repo", "create"] for c in fake.calls)
    assert ["git", "-C", str(work), "commit", "--quiet", "-m", apply.SEED_MESSAGE] in fake.calls
    push = ["git", "-C", str(work), "push", "git@github.com:o/r.git", "main"]
    protect = ["gh", "api", "--method", "PUT", "repos/o/r/branches/main/protection"]
    assert fake.calls.index(push) < [c[:5] for c in fake.calls].index(protect)
    # No description.txt: the description is left alone.
    assert not any("-f" in c for c in fake.calls)


@pytest.mark.parametrize("exists", [False, True])
def test_apply_refuses_a_repository_without_main_and_without_seed(
    apply, monkeypatch, capsys, exists
):
    fake = FakeGh(exists=exists, main=False, rulesets=[])
    monkeypatch.setattr(apply, "run", fake)
    assert apply.main(["o/r"]) == 1
    assert "--seed" in capsys.readouterr().err
    # Nothing was created or changed.
    assert all(c[:2] == ["gh", "api"] and "--method" not in c for c in fake.calls)


def test_seed_directory_without_files_is_refused(tmp_path):
    (tmp_path / "README.md").write_text("# r\n")
    run = _dry_run("o/r", "--seed", str(tmp_path))
    assert run.returncode == 2
    assert "files" in run.stderr


@pytest.mark.parametrize("library", LIBRARIES)
def test_seed_directory(library):
    seed = SETTINGS / "seed" / library
    assert sorted(p.relative_to(seed).as_posix() for p in seed.rglob("*") if p.is_file()) == [
        "commit-message.txt",
        "description.txt",
        "files/README.md",
    ]
    text = (seed / "files" / "README.md").read_text()
    assert text.startswith(f"# {library}")
    assert META_URL in text
    assert "generated by the build" in text
    assert "not be edited by hand" in " ".join(text.split())
    description = (seed / "description.txt").read_text()
    assert description.startswith(f"{library}: ") and description.count("\n") == 1
    assert (seed / "commit-message.txt").read_text().startswith("Initial commit: README")


@pytest.mark.parametrize("library", LIBRARIES)
def test_libraries_readme_gives_the_seed_command(library):
    text = " ".join((REPO / "libraries" / "README.md").read_text().replace("\\\n", " ").split())
    assert (
        f"uv run tools/repo-settings/apply.py wafer-space-robot/{library} "
        f"--seed tools/repo-settings/seed/{library}"
    ) in text
    assert "--seed-message" not in text and "--description" not in text


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
    live_repo = {**repo, "id": 1, "name": "r", "description": "the text"}
    assert verify.differences(live_repo, live_protection, [live_ruleset]) == []
    assert verify.differences(live_repo, live_protection, [live_ruleset], "the text") == []

    live_repo["has_wiki"] = True
    live_protection["enforce_admins"] = {"enabled": False}
    live_protection["restrictions"] = {"users": []}
    live_ruleset["rules"] = []
    found = verify.differences(live_repo, live_protection, [live_ruleset], "another text")
    assert [d.split(":")[0] for d in found] == [
        "repo.has_wiki",
        "repo.description",
        "protection.enforce_admins",
        "protection.restrictions",
        "ruleset.rules",
    ]
    assert verify.differences(live_repo, live_protection, [])[-1].startswith("ruleset: no")
