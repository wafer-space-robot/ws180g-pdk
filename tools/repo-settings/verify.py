#!/usr/bin/env -S uv run
# SPDX-License-Identifier: Apache-2.0
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Compare a GitHub repository's live settings with the settings files of `apply.py`.

    uv run tools/repo-settings/verify.py <owner/repo> [--seed DIR]

Read-only: three or four `gh api` reads (the repository, the protection of `main`, the
rulesets and the ruleset named in `ruleset-tags.json`). Prints one line per setting that
differs from `repo.json`, `protection.json` or `ruleset-tags.json` and exits 1, or prints
that all settings match and exits 0. Only the keys the files hold are compared. With
`--seed DIR`, the seed directory `apply.py` takes, the repository description is compared
with `DIR/description.txt` too. Reading `security_and_analysis` needs `gh` logged in as an
administrator of the repository.
"""

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from apply import _repo_argument, run, seed_argument


def _settings(name: str):
    return json.loads((HERE / name).read_text())


def _subset(want, live, where: str) -> list[str]:
    """Differences between `want` and the part of `live` it names."""
    if isinstance(want, dict):
        if not isinstance(live, dict):
            return [f"{where}: expected {json.dumps(want)}, live {json.dumps(live)}"]
        found: list[str] = []
        for key, value in want.items():
            found += _subset(value, live.get(key), f"{where}.{key}")
        return found
    if want != live:
        return [f"{where}: expected {json.dumps(want)}, live {json.dumps(live)}"]
    return []


def differences(
    repo: dict, protection: dict, rulesets: list[dict], description: str | None = None
) -> list[str]:
    """Every difference between the settings files and the live answers: the repository,
    the protection of `main`, and the full rulesets of the repository. `description`, when
    given, is the expected repository description."""
    found = _subset(_settings("repo.json"), repo, "repo")
    if description is not None:
        found += _subset(description, repo.get("description"), "repo.description")
    for key, want in _settings("protection.json").items():
        live = protection.get(key)
        # The read wraps each boolean as {"enabled": ...}; an unset object is left out.
        if isinstance(want, bool) and isinstance(live, dict):
            live = live.get("enabled")
        found += _subset(want, live, f"protection.{key}")
    want = _settings("ruleset-tags.json")
    named = [r for r in rulesets if r.get("name") == want["name"]]
    if len(named) != 1:
        found.append(f"ruleset: {'no' if not named else len(named)} ruleset named {want['name']!r}")
    else:
        found += _subset(want, named[0], "ruleset")
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="verify.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("repo", type=_repo_argument, metavar="owner/repo")
    parser.add_argument("--seed", type=Path, metavar="DIR", help="the seed directory of apply.py")
    args = parser.parse_args(argv)
    seed = seed_argument(parser, args.seed)
    api = f"repos/{args.repo}"
    repo = json.loads(run(["gh", "api", api]))
    protection = json.loads(run(["gh", "api", f"{api}/branches/main/protection"]))
    name = _settings("ruleset-tags.json")["name"]
    rulesets = [
        json.loads(run(["gh", "api", f"{api}/rulesets/{r['id']}"]))
        for r in json.loads(run(["gh", "api", f"{api}/rulesets"]))
        if r["name"] == name
    ]
    found = differences(repo, protection, rulesets, seed.description if seed else None)
    for line in found:
        print(line)
    if not found:
        compared = "tools/repo-settings" + (f" and {args.seed}/description.txt" if seed else "")
        print(f"{args.repo}: all settings match {compared}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
