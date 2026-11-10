#!/usr/bin/env -S uv run
# SPDX-License-Identifier: Apache-2.0
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Create a GitHub repository if it is missing and apply the ws180g repository settings.

    uv run tools/repo-settings/apply.py <owner/repo> [--dry-run] [--seed DIR]

The settings are the three JSON files next to this script, each the body of one GitHub REST
call, read back from the meta-repository `wafer-space-robot/ws180g-pdk`:

- `repo.json` (`PATCH /repos/{owner}/{repo}`): issues on; wiki, projects and discussions
  off; merge commits only; delete branch on merge; secret scanning and push protection.
- `protection.json` (`PUT /repos/{owner}/{repo}/branches/main/protection`): pull request
  required, admins enforced, no force push, no deletion.
- `ruleset-tags.json` (`POST /repos/{owner}/{repo}/rulesets`, or `PUT .../rulesets/{id}`
  when a ruleset of that name exists): the tag ruleset `Enforce vXX.ZZZ version tags`.

What belongs to one repository only is in its seed directory, `--seed DIR`:

- `DIR/files/`: the files of the first commit (the script adds this repository's `LICENSE`);
- `DIR/description.txt` (optional): the repository description, one line;
- `DIR/commit-message.txt` (optional): the message of the first commit; without it the
  message is a fixed line.

Steps, in order (`--dry-run` prints every command of this list, in this order, and runs none
of them, not even the reads):

1. Read the repository and, if it exists, its `main` branch. The branch read counts as "no
   main branch" on HTTP 404 and on HTTP 409, with which GitHub answers some reads of an
   empty repository.
2. If there is no `main` branch and no `--seed`, stop, with nothing created or changed.
3. If the repository does not exist, create it, public.
4. If it has no `main` branch, make the first commit from `DIR/files/` plus `LICENSE` and
   push it over SSH. This has to come before step 6: a protected `main` takes no direct
   push.
5. Apply `repo.json`, then the description if the seed directory gives one.
6. Apply `protection.json`.
7. Create the tag ruleset, or update the one of the same name.

A rerun on an existing repository with a `main` branch does steps 5 to 7 only, and they set
the same values again. A rerun after a run that failed between steps 3 and 4 finds the
repository without `main` and continues at step 4. The script needs `gh` logged in as an
administrator of the repository and, for step 4, `git` with SSH push access. It never
deletes anything and never changes a repository's visibility.
"""

import argparse
import json
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
# Scratch directory of the first commit (`tmp/` is gitignored); one subdirectory per name.
WORK = REPO_ROOT / "tmp" / "repo-settings-seed"
SEED_MESSAGE = "Initial commit: README and licence"
RULESET_ID = "RULESET_ID"
# The repository part is never only dots (`.` and `..` are directories, not names).
_REPO_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]*/(?!\.+$)[A-Za-z0-9_.-]+")
NO_REPOSITORY = (404,)
# GitHub answers some reads of an empty repository with 409 "Git Repository is empty".
NO_BRANCH = (404, 409)


@dataclass(frozen=True)
class Seed:
    """A seed directory: `files/`, and the optional description and commit message."""

    root: Path

    @property
    def files(self) -> Path:
        return self.root / "files"

    @property
    def message(self) -> Path | None:
        path = self.root / "commit-message.txt"
        return path if path.is_file() else None

    @property
    def description(self) -> str | None:
        path = self.root / "description.txt"
        return path.read_text().strip() if path.is_file() else None

    def names(self) -> list[str]:
        files = self.files
        return sorted(p.relative_to(files).as_posix() for p in files.rglob("*") if p.is_file())


def run(argv: list, *, missing: tuple[int, ...] = (), cwd: Path | None = None) -> str | None:
    """Run one command (an argument list, no shell), echo it, and return its stdout.

    A `gh api` failure with one of the HTTP statuses in `missing` returns `None`; any other
    failure ends the script with the command's stderr."""
    argv = [str(a) for a in argv]
    print(shlex.join(argv), flush=True)
    done = subprocess.run(argv, capture_output=True, text=True, check=False, cwd=cwd)
    if done.returncode == 0:
        return done.stdout
    if any(f"(HTTP {status})" in done.stderr for status in missing):
        return None
    sys.stderr.write(done.stdout + done.stderr)
    raise SystemExit(f"apply.py: failed ({done.returncode}): {shlex.join(argv)}")


def commands(
    repo: str, settings: Path, work: Path, message: Path | None, description: str | None
) -> dict[str, list[str]]:
    """Every command the script can run, by step name. `settings` is the directory of the
    JSON files and `work` the scratch directory of the first commit."""
    api = f"repos/{repo}"

    def send(method: str, path: str, body: str) -> list[str]:
        return ["gh", "api", "--method", method, path, "--input", str(settings / body)]

    commit = ["-F", str(message)] if message else ["-m", SEED_MESSAGE]
    found = {
        "read-repo": ["gh", "api", api],
        "read-main": ["gh", "api", f"{api}/branches/main"],
        "create": ["gh", "repo", "create", repo, "--public"],
        "seed-init": ["git", "init", "--quiet", "--initial-branch=main", str(work)],
        "seed-add": ["git", "-C", str(work), "add", "--all"],
        "seed-commit": ["git", "-C", str(work), "commit", "--quiet", *commit],
        "seed-push": ["git", "-C", str(work), "push", f"git@github.com:{repo}.git", "main"],
        "repo": send("PATCH", api, "repo.json"),
        "protection": send("PUT", f"{api}/branches/main/protection", "protection.json"),
        "read-rulesets": ["gh", "api", f"{api}/rulesets"],
        "ruleset-create": send("POST", f"{api}/rulesets", "ruleset-tags.json"),
        "ruleset-update": send("PUT", f"{api}/rulesets/{RULESET_ID}", "ruleset-tags.json"),
    }
    if description is not None:
        found["description"] = ["gh", "api", "--method", "PATCH", api]
        found["description"] += ["-f", f"description={description}"]
    return found


def _relative(path: Path) -> Path:
    """`path` relative to the repository root when it is inside it (for the dry run)."""
    path = path.resolve()
    return path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path


def dry_run(repo: str, seed: Seed | None) -> None:
    """Print the command list in the order a real run follows, with its conditions."""
    name = repo.split("/")[1]
    message = seed.message if seed else None
    description = seed.description if seed else None
    cmds = commands(
        repo,
        _relative(HERE),
        _relative(WORK / name),
        _relative(message) if message else None,
        description,
    )
    steps: list[tuple[str, list[str]]] = [
        ("read: does the repository exist?", ["read-repo"]),
        (
            (
                "only if the repository exists; read: does it have a main branch? "
                f"(HTTP {' or '.join(str(s) for s in NO_BRANCH)}: no)"
            ),
            ["read-main"],
        ),
    ]
    if seed is None:
        stop = "no --seed: if there is no main branch the script stops here, with nothing "
        steps.append((stop + "created or changed", []))
    steps.append(("only if the repository does not exist", ["create"]))
    if seed is not None:
        copy = (
            f"only if there is no main branch: copy {_relative(seed.files)}/"
            f"{', '.join(seed.names())} and LICENSE into the scratch directory, commit, "
            "push, remove the scratch directory"
        )
        steps.append((copy, ["seed-init", "seed-add", "seed-commit", "seed-push"]))
    steps.append(("repository settings", ["repo"]))
    if description is not None:
        steps.append(("description", ["description"]))
    steps += [
        ("protection of main", ["protection"]),
        ("read: is there a ruleset of that name?", ["read-rulesets"]),
        ("only if there is none", ["ruleset-create"]),
        (f"only if there is one; {RULESET_ID} is its id", ["ruleset-update"]),
    ]
    print(f"# dry run: nothing is run. Paths are relative to {REPO_ROOT}")
    for comment, names in steps:
        print(f"# {comment}")
        for step in names:
            print(shlex.join(cmds[step]))


def _push_seed(cmds: dict[str, list[str]], seed: Seed, work: Path) -> None:
    if work.parent != WORK or work.name in ("", ".", ".."):
        raise SystemExit(f"apply.py: refusing the scratch directory {work}")
    if work.exists():
        shutil.rmtree(work)
    work.parent.mkdir(parents=True, exist_ok=True)
    try:
        run(cmds["seed-init"])
        shutil.copytree(seed.files, work, dirs_exist_ok=True)
        shutil.copyfile(REPO_ROOT / "LICENSE", work / "LICENSE")
        for step in ("seed-add", "seed-commit", "seed-push"):
            run(cmds[step])
    finally:
        shutil.rmtree(work, ignore_errors=True)


def apply(repo: str, seed: Seed | None) -> int:
    work = WORK / repo.split("/")[1]
    description = seed.description if seed else None
    cmds = commands(repo, HERE, work, seed.message if seed else None, description)
    exists = run(cmds["read-repo"], missing=NO_REPOSITORY) is not None
    has_main = exists and run(cmds["read-main"], missing=NO_BRANCH) is not None
    if not has_main and seed is None:
        print(
            f"apply.py: {repo} has no main branch; give --seed DIR for its first commit "
            "(nothing was created or changed)",
            file=sys.stderr,
        )
        return 1
    if not exists:
        run(cmds["create"])
    if not has_main:
        _push_seed(cmds, seed, work)
    run(cmds["repo"])
    if description is not None:
        run(cmds["description"])
    run(cmds["protection"])
    name = json.loads((HERE / "ruleset-tags.json").read_text())["name"]
    live = json.loads(run(cmds["read-rulesets"]) or "[]")
    ids = [r["id"] for r in live if r["name"] == name]
    if ids:
        run([a.replace(RULESET_ID, str(ids[0])) for a in cmds["ruleset-update"]])
    else:
        run(cmds["ruleset-create"])
    return 0


def _repo_argument(value: str) -> str:
    if not _REPO_RE.fullmatch(value):
        raise argparse.ArgumentTypeError(f"not <owner>/<repository>: {value!r}")
    return value


def seed_argument(parser: argparse.ArgumentParser, value: Path | None) -> Seed | None:
    """The seed directory of `--seed`, or a usage error when it has no `files/`."""
    if value is None:
        return None
    seed = Seed(value.resolve())
    if not seed.files.is_dir() or not seed.names():
        parser.error(f"--seed: no files/ directory with files in {value}")
    return seed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="apply.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("repo", type=_repo_argument, metavar="owner/repo")
    parser.add_argument(
        "--dry-run", action="store_true", help="print the command list and run nothing"
    )
    parser.add_argument(
        "--seed",
        type=Path,
        metavar="DIR",
        help="seed directory: files/, description.txt, commit-message.txt",
    )
    args = parser.parse_args(argv)
    seed = seed_argument(parser, args.seed)
    if args.dry_run:
        dry_run(args.repo, seed)
        return 0
    return apply(args.repo, seed)


if __name__ == "__main__":
    sys.exit(main())
