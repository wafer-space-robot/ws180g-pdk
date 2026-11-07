# ws180g-pdk: the wafer.space 180 nm generic PDK

A generic, conservative 180 nm process design kit whose aim is to let one design be
manufactured at as many 180 nm foundries as possible. It is regenerated end to end from one
"virtual process" description with ranged parameters, open-source TCAD and public measured
data, and released as nested variants (`ws180g005`, `ws180g035`, `ws180g105`, `ws180g135`).

Start with the design document:
[`docs/superpowers/specs/2026-10-26-ws180g-pdk-design.md`](docs/superpowers/specs/2026-10-26-ws180g-pdk-design.md).

Everything in this repository comes from public sources, each cited; nothing here is under a
non-disclosure agreement. Licence: Apache-2.0 (see [`LICENSE`](LICENSE)).

## Development

```
git clone git@github.com:wafer-space-robot/ws180g-pdk.git
cd ws180g-pdk
uv sync --all-packages
uv run pytest -rs -v
uv run ruff check .
```

Run `pytest` from the repository root: the basetemp (`tmp/pytest`) is relative to the invocation directory.

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
the image print them (regenerate with `docker/probe_versions.py`, see its docstring). After a
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
