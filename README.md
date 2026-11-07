# ws180g-pdk: the wafer.space 180 nm generic PDK

A generic, conservative 180 nm process design kit whose aim is to let one design be
manufactured at as many 180 nm foundries as possible. It is regenerated end to end from one
"virtual process" description with ranged parameters, open-source TCAD and public measured
data, and released as nested variants (`ws180g005`, `ws180g035`, `ws180g105`, `ws180g135`).

Start with the design document:
[`docs/superpowers/specs/2026-10-26-ws180g-pdk-design.md`](docs/superpowers/specs/2026-10-26-ws180g-pdk-design.md).

Everything in this repository comes from public sources, each cited; nothing here is under a
non-disclosure agreement. Licence: Apache-2.0 (see [`LICENSE`](LICENSE)).

Status: Phase 0 (foundations) is complete apart from the library repositories; see the gate report,
[`docs/phase-0-report.md`](docs/phase-0-report.md).

## Development

```
git clone git@github.com:wafer-space-robot/ws180g-pdk.git
cd ws180g-pdk
uv sync --all-packages
uv run pytest -rs -v
uv run ruff check .
```

Run `pytest` from the repository root: the basetemp (`tmp/pytest`) is relative to the invocation directory. pytest clears the basetemp at the start of every run, so do not run two `pytest` processes in one checkout at the same time (use a second worktree).

Gate check 1, KLayout half: `uv run pytest tests/rules/test_klayout_fixtures.py -rs -v` (needs the container
image) runs every per-rule fixture through the KLayout deck in one container run and checks each
against its expected markers. Results are cached in `tmp/klayout-fixtures/run/cache/`, keyed by the deck files, the
derived layout's bytes and the container image ID; delete `tmp/klayout-fixtures/` to force a fresh
engine run (about 4 minutes).

Gate check 1, Magic half: `uv run pytest tests/rules/test_magic_fixtures.py -rs -v` runs the same fixtures
through the Magic technology in one Magic session (cache in `tmp/magic-fixtures/run/cache/`, keyed by the tech files, the derived layout, the
script's `BOX_GROW` and the image ID; a few seconds).
Both engines: `uv run pytest tests/rules/test_engines_agree.py -rs -v` checks that KLayout and Magic report the
same rule ids on every fixture of a two-engine rule, and prints each recorded `MAGIC_EXCEPTIONS` case.

Gate check 2: `uv run pytest tests/precheck/test_fixture_retarget.py tests/precheck/test_gf180mcu_deck.py -rs -v`
retargets every pass fixture (and the permanent regression fixtures) to GF180MCU and runs them through
the public GF180MCU deck for each `metal_top` value (9K, 11K, 30K), one container per value;
`test_gf180mcu_deck.py` is the positive control (the deck finds known violations in a GF-native
layout). Results are cached in `tmp/gf180mcu-retarget/` (keyed by the retargeted bytes, the mapping,
`metal_top`, the deck path and the image ID); a cold run takes about 15 minutes per `metal_top`.
`tests/precheck/test_gf180mcu_io_mt30.py` is informative only (the public IO library through the 30K
top-metal rules). The decision log is [`docs/phase-0-retarget-log.md`](docs/phase-0-retarget-log.md).

Gate check 3: `uv run ws180g-evidence-report` prints the margin report summary (rows by status, uncovered
binding entries) and any failing row, and exits 1 unless the report is ok; `--markdown PATH` writes the
full report with the uncovered entries by kind.

The full build, `uv run ws180g-build` (default `--out out/`), runs all of it: the evidence report, the
rule table, decks, tech files, fixtures and manual, the image check (including a `docker/build`
rebuild that proves the image ID reproduces, in every container build; its export step took
71.4 s on the build host), gate
check 1 for both engines, gate check 2 with the regressions, the release tree `out/ws180g005/` and
`out/build-manifest.json`. The Phase 0 gate report measured 51:42 cold, on a build host shared
with other container jobs, and 2:10 warm (cache in `tmp/build/`). `uv run ws180g-build --no-container` skips the image check and the engine runs. The
documentation: `uv run sphinx-build -W docs out/docs` (after a build, which writes
`docs/generated/`).

## Pre-commit checks

Two checkers guard every commit:

- `uv run ws180g-check-private [--cached] [ROOT]` enforces the public-sources rule (design document,
  section 13): every evidence entry names a registered source with a `url` and
  `public = true`; every process field has an allowed `provenance` and cites only evidence ids
  that exist; every vendored file under `evidence/sources/` matches its registered sha256; and
  no git-tracked text file outside `tmp/` contains a marker word of private material (the
  pattern list is fixed in `build/src/ws180g_build/private_check.py`). The few lines that must
  mention such material, such as the design document's own rule, are listed in
  `build/private-allow.txt` as `<path glob>: <exact line text>`, each with a comment saying
  why; an entry exempts only that exact line, and an entry that matches nothing is a finding.
- `uv run ws180g-check-names [ROOT]` checks library, cell, corner and device names.

Both print one finding per line and exit 1 when there are any. `--cached` makes the private
check read the staged blobs (index) instead of the working tree, so a line staged with
`git add -p` and then edited away, or a staged file deleted from the working tree, is still
checked. Install the git hook once per clone with `tools/install-hooks`, run from the main
checkout (it refuses a linked worktree, since the hooks directory is shared): it symlinks
`tools/git-hooks/*` into `git rev-parse --git-path hooks`, honouring `core.hooksPath`. The
hook runs `ws180g-check-private --cached` and `ws180g-check-names` on the repository being
committed and refuses the commit on a finding. It runs them with `uv run --project
"$WS180G_PROJECT"`, default the repository root; the tests set `WS180G_PROJECT` to check a
scratch repository with the workspace's code.

## Container image

Every heavy EDA job (KLayout DRC, Magic, netgen, ngspice) runs in one pinned container image
through `build/sandbox-run`, with a memory cap and no swap, never bare on the host.

The image (`docker/Dockerfile`) is the public gf180-tcad base image
(`ghcr.io/mithro/gf180-tcad-base@sha256:aedc0795…`, itself the pinned IIC-OSIC-TOOLS image:
KLayout, Magic, netgen, ngspice and the GF180MCU open PDK under `/foss/pdks`) plus a Python venv
`/opt/ws180g` with the workspace's runtime dependencies from `docker/requirements.lock`. Project
code is never baked in: the runner mounts the checkout. Build it with

```
docker/build            # loads ws180g-pdk-base:local; prints the image config digest
```

The build is reproducible (pinned BuildKit, `SOURCE_DATE_EPOCH` from the last commit touching
`docker/Dockerfile` or `docker/requirements.lock`, rewritten timestamps, no attestations), so the
printed digest equals `docker/IMAGE_ID`. It refuses to build uncommitted inputs, and pulls the
base (about 15 GB) on first use. `docker/versions.json` records the tool versions as the tools in
the image print them (regenerate with `docker/probe_versions.py`, see its docstring). Two
KLayouts are in use: the fixtures, layer derivation (`ws180g_layergen.derive_file`), retargeting
and the other generators use the `klayout` Python module (`klayout_python`, 0.30.13, the same
wheel on the host and in the image's venv), while every DRC run uses the image's `klayout`
binary (`klayout`, 0.30.12) in the container. After a
change to the runtime dependencies, regenerate the lock at the repository root with
`uv export --no-dev --no-emit-workspace --all-packages --format requirements.txt --output-file docker/requirements.lock`.

Run a command in the image:

```
mkdir -p tmp/sandbox/drc
build/sandbox-run --mem 4g --cpus 2 --workdir tmp/sandbox/drc -- klayout -b -r deck.drc ...
```

The repository is mounted read-only at `/work/src` and the workdir read-write at `/work/out` (the
working directory). The command runs as your uid:gid, without network (`--network bridge` to
allow it), with `--mem` as both the memory and the memory+swap limit; its exit code is returned
(137 when the cap kills it). The runner refuses `/`, `$HOME` and its ancestors, the repository
root, the git directories, and any directory inside the repository other than `tmp/`. The tests
that need the image are marked `sandbox` (`uv run pytest -rs -v -m "sandbox and not slow"`); the
`slow` one rebuilds the image and checks the digest.

`docker/IMAGE`, `docker/IMAGE_ID`, `docker/versions.json` and `docker/requirements.lock` carry no
SPDX line: they are generated or data files (JSON and the uv export cannot hold one cleanly).
`IMAGE_ID` must be regenerated (run `docker/build`, commit the digest it prints) after any change
to `docker/Dockerfile` or `docker/requirements.lock`, or to the author time of the last commit
touching them; `build/sandbox-run` refuses to run an image whose ID differs.
