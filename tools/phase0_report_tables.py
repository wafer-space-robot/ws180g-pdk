# SPDX-License-Identifier: Apache-2.0
"""Print the exception tables of the Phase 0 gate report (`docs/phase-0-report.md`) as
Markdown, read from the code constants, so the report lists every recorded exception and
cannot go stale (`tests/build/test_phase0_report_tables.py` compares the report's copy with
this output).

Run from the repository root: `uv run tools/phase0_report_tables.py`. The tables are:

1. `EXPECTED_MARKERS` (`ws180g_rules.fixtures`): fail fixtures whose geometry forces a
   marker set other than one marker of their own rule.
2. `MAGIC_EXCEPTIONS` (`ws180g_tech.magic`): fixtures where Magic's rule ids differ from
   KLayout's.
3. The KLayout-only rules (`engines = ["klayout"]` in `process/data/ws180g/rules.toml`), with
   the reason from `ws180g_tech.magic.MAGIC_KINDS`.
4. `EXCLUDED` (`ws180g_precheck.gate`): pass fixtures excluded from gate check 2.
5. The permanent regression fixtures of gate check 2 (`ws180g_precheck.regressions`).
6. The GF180MCU rule-deck files not run by gate check 2 (`precheck/data/gf180mcu.toml`).
"""

import importlib
import sys

from ws180g_precheck import regressions
from ws180g_precheck.gate import EXCLUDED, regression_names
from ws180g_precheck.mapping import load_mapping
from ws180g_process.load import load_process
from ws180g_rules.fixtures import EXPECTED_MARKERS
from ws180g_rules.table import RuleTable
from ws180g_tech.magic import MAGIC_EXCEPTIONS, MAGIC_KINDS, magic_key

KLAYOUT_ONLY = "KLayout-only: "


def _cell(text: str) -> str:
    return " ".join(str(text).split()).replace("|", "\\|")


def _table(header: list[str], rows: list[list[str]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(_cell(c) for c in row) + " |" for row in rows]
    return lines


def _markers(markers: dict[str, int] | frozenset[str]) -> str:
    if isinstance(markers, dict):
        return ", ".join(f"`{rid}` × {n}" for rid, n in sorted(markers.items()))
    return ", ".join(f"`{rid}`" for rid in sorted(markers))


def _first_paragraph(doc: str | None) -> str:
    return (doc or "").strip().split("\n\n")[0]


def tables() -> str:
    """The six tables, each under a level-3 heading, as one Markdown string."""
    out: list[str] = []

    out += [f"### Forced marker sets (`EXPECTED_MARKERS`, {len(EXPECTED_MARKERS)} fixtures)", ""]
    out += _table(["Fail fixture", "Markers the KLayout deck must give"],
                  [[f"`{rid}/{name}`", _markers(m)]
                   for (rid, name), m in sorted(EXPECTED_MARKERS.items())])

    out += ["", f"### Magic exceptions (`MAGIC_EXCEPTIONS`, {len(MAGIC_EXCEPTIONS)} fixtures)",
            ""]
    out += _table(["Fail fixture", "Rule ids Magic reports", "Reason"],
                  [[f"`{rid}/{name}`", _markers(e.expected), e.reason]
                   for (rid, name), e in sorted(MAGIC_EXCEPTIONS.items())])

    table = RuleTable.from_process(load_process())
    only = [row for row in table.rows if row.engines == ["klayout"]]
    out += ["", f"### KLayout-only rules ({len(only)} rules)", ""]
    rows = []
    for row in only:
        reason = MAGIC_KINDS[magic_key(row)].rule
        rows.append([f"`{row.id}`", row.kind, reason.removeprefix(KLAYOUT_ONLY)])
    out += _table(["Rule", "Kind", "Why Magic does not check it"], rows)

    out += ["", (f"### Pass fixtures excluded from gate check 2 (`EXCLUDED`, {len(EXCLUDED)} "
            "fixtures)"), ""]
    out += _table(["Pass fixture", "GF180MCU rule", "Reason"],
                  [[f"`{rid}/{name}`", gf, why] for (rid, name), (gf, why) in EXCLUDED.items()])

    names = regression_names()
    out += ["", f"### Permanent regression fixtures of gate check 2 ({len(names)} modules)", ""]
    rows = []
    for name in names:
        module = importlib.import_module(f"{regressions.__name__}.{name}")
        rows.append([f"`regressions/{name}`", _first_paragraph(module.__doc__)])
    out += _table(["Case", "What it records"], rows)

    mapping = load_mapping()
    out += ["", (f"### GF180MCU rule-deck files not run (`excluded_decks`, "
            f"{len(mapping.excluded_decks)} files)"), "",
            f"The deck runs with `-rd decks={mapping.drc.decks}`.", ""]
    out += _table(["Deck file", "Tag", "Reason", "Source"],
                  [[f"`{d.file}`", f"`{d.tag}`", d.reason, f"`{d.source}`"]
                   for d in mapping.excluded_decks])
    return "\n".join(out) + "\n"


def main() -> int:
    sys.stdout.write(tables())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
