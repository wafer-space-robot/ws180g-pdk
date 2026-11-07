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
