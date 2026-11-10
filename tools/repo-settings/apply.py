#!/usr/bin/env -S uv run
# SPDX-License-Identifier: Apache-2.0
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Create a GitHub repository if it is missing and apply the ws180g repository settings.

    uv run tools/repo-settings/apply.py <owner/repo> [--dry-run] [--seed DIR]
        [--seed-message FILE] [--description TEXT]

The settings are the three JSON files next to this script, each the body of one GitHub REST
call, read back from the meta-repository `wafer-space-robot/ws180g-pdk`:

- `repo.json` (`PATCH /repos/{owner}/{repo}`): issues on; wiki, projects and discussions
  off; merge commits only; delete branch on merge; secret scanning and push protection.
- `protection.json` (`PUT /repos/{owner}/{repo}/branches/main/protection`): pull request
  required, admins enforced, no force push, no deletion.
- `ruleset-tags.json` (`POST /repos/{owner}/{repo}/rulesets`, or `PUT .../rulesets/{id}`
  when a ruleset of that name exists): the tag ruleset `Enforce vXX.ZZZ version tags`.

Steps, in order (`--dry-run` prints every command of this list and runs none of them, not
even the reads):

1. Read the repository and its `main` branch.
2. If the repository does not exist, create it, public.
3. If it has no `main` branch, make the first commit from the files of `--seed DIR` plus
   the `LICENSE` of this repository, and push it over SSH. This has to come before step 5:
   a protected `main` takes no direct push. Without `--seed` the script stops here, before
   it has created or changed anything. The commit message is the content of
   `--seed-message FILE`, or a fixed line.
4. Apply `repo.json`, then `--description` if given.
5. Apply `protection.json`.
6. Create the tag ruleset, or update the one of the same name.

A rerun on an existing repository with a `main` branch does steps 4 to 6 only, and they set
the same values again. The script needs `gh` logged in as an administrator of the repository
and, for step 3, `git` with SSH push access. It never deletes anything and never changes a
repository's visibility.
"""

import argparse
import json
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
# Scratch directory of the first commit (`tmp/` is gitignored); one subdirectory per name.
WORK = REPO_ROOT / "tmp" / "repo-settings-seed"
SEED_MESSAGE = "Initial commit: README and licence"
RULESET_ID = "RULESET_ID"
_REPO_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.][A-Za-z0-9_.-]*")


def run(argv: list, *, ok_missing: bool = False, cwd: Path | None = None) -> str | None:
    """Run one command (an argument list, no shell), echo it, and return its stdout.

    With `ok_missing`, a `gh api` answer of HTTP 404 returns `None`; any other failure ends
    the script with the command's stderr."""
    argv = [str(a) for a in argv]
    print(shlex.join(argv), flush=True)
    done = subprocess.run(argv, capture_output=True, text=True, check=False, cwd=cwd)
    if done.returncode == 0:
        return done.stdout
    if ok_missing and "(HTTP 404)" in done.stderr:
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
        "create": ["gh", "repo", "create", repo, "--public"],
        "read-main": ["gh", "api", f"{api}/branches/main"],
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
        found["description"] = [
            "gh",
            "api",
            "--method",
            "PATCH",
            api,
            "-f",
            f"description={description}",
        ]
    return found


def _relative(path: Path) -> Path:
    """`path` relative to the repository root when it is inside it (for the dry run)."""
    path = path.resolve()
    return path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path


def dry_run(repo: str, seed: Path | None, message: Path | None, description: str | None) -> None:
    name = repo.split("/")[1]
    shown_seed = _relative(seed) if seed else None
    cmds = commands(
        repo,
        _relative(HERE),
        _relative(WORK / name),
        _relative(message) if message else None,
        description,
    )
    steps: list[tuple[str, list[str]]] = [
        ("read: does the repository exist?", ["read-repo"]),
        ("only if the repository does not exist", ["create"]),
        ("read: does it have a main branch?", ["read-main"]),
    ]
    if seed:
        steps.append(
            (
                (
                    f"only if there is no main branch: copy {shown_seed}/"
                    f"{', '.join(_seed_files(seed))} and LICENSE into the scratch "
                    "directory, commit, push, remove the scratch directory"
                ),
                ["seed-init", "seed-add", "seed-commit", "seed-push"],
            )
        )
    else:
        steps.append(
            (
                (
                    "no --seed: the script stops here, with nothing created or changed, "
                    "if there is no main branch"
                ),
                [],
            )
        )
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


def _seed_files(seed: Path) -> list[str]:
    return sorted(p.relative_to(seed).as_posix() for p in seed.rglob("*") if p.is_file())


def _push_seed(cmds: dict[str, list[str]], seed: Path, work: Path) -> None:
    if work.exists():
        shutil.rmtree(work)
    work.parent.mkdir(parents=True, exist_ok=True)
    try:
        run(cmds["seed-init"])
        shutil.copytree(seed, work, dirs_exist_ok=True)
        shutil.copyfile(REPO_ROOT / "LICENSE", work / "LICENSE")
        for step in ("seed-add", "seed-commit", "seed-push"):
            run(cmds[step])
    finally:
        shutil.rmtree(work, ignore_errors=True)


def apply(repo: str, seed: Path | None, message: Path | None, description: str | None) -> int:
    work = WORK / repo.split("/")[1]
    cmds = commands(repo, HERE, work, message, description)
    exists = run(cmds["read-repo"], ok_missing=True) is not None
    has_main = exists and run(cmds["read-main"], ok_missing=True) is not None
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
        help="files of the first commit of a repository without main",
    )
    parser.add_argument(
        "--seed-message",
        type=Path,
        metavar="FILE",
        help=f"commit message of the first commit (default: {SEED_MESSAGE!r})",
    )
    parser.add_argument("--description", help="set the repository description")
    args = parser.parse_args(argv)
    if args.seed is not None and not args.seed.is_dir():
        parser.error(f"--seed: not a directory: {args.seed}")
    if args.seed_message is not None and not args.seed_message.is_file():
        parser.error(f"--seed-message: not a file: {args.seed_message}")
    seed = args.seed.resolve() if args.seed else None
    message = args.seed_message.resolve() if args.seed_message else None
    if args.dry_run:
        dry_run(args.repo, seed, message, args.description)
        return 0
    return apply(args.repo, seed, message, args.description)


if __name__ == "__main__":
    sys.exit(main())
