# SPDX-License-Identifier: Apache-2.0
"""The evidence margin report: every process field checked against the evidence it cites.

One row per rule (`rules.<id>`) and two per range field of the stack
(`stack.oxides.5v0.thickness.min` and `.max`). For each row the report finds the binding
entries cited (an entry with a value that is not a guideline), the bound they set (the
largest minimum, or the smallest maximum), the margin the vocabulary requires (1.2; 1.5 when
every binding entry comes from one source; 1.25 for a maximum; the field's own `margin` when
it records a `margin_reason`), the margin achieved, and a status. It also lists every binding
entry no field cites, the source registry, and whether the process grid is a multiple of
every grid the evidence records. The output carries no timestamp: the same inputs give
byte-identical Markdown and JSON.
"""

import argparse
import json
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel

from ws180g_evidence.model import Entry, Evidence, Source

if TYPE_CHECKING:
    from ws180g_process.model import Field, Process, RuleField

Status = Literal["ok", "under-margin", "chosen", "missing-entry", "exempt", "implied",
                 "override-too-small", "achieved-mismatch"]
STATUSES: list[str] = ["ok", "under-margin", "chosen", "missing-entry", "exempt", "implied",
                       "override-too-small", "achieved-mismatch"]
FAILING = frozenset({"under-margin", "missing-entry", "override-too-small", "achieved-mismatch"})

# The margin rules (spec 3.6, plan Global Constraints), all ratios >= 1.
MINIMUM_MARGIN = Decimal("1.2")
MAXIMUM_MARGIN = Decimal("1.25")
SINGLE_SOURCE_MARGIN = Decimal("1.5")
ACHIEVED_STEP = Decimal("0.001")

# Rule kinds checked as a maximum; `topology` and `exact-size` carry no margin; every other
# rule kind (the minima and `generation`) is checked as a minimum.
MAXIMUM_KINDS = frozenset({"max-distance"})

# Evidence columns of the 3.3 V class (`3v3`, `lv`) and of the 6 V class: ws180g005 has
# only the 5 V oxide, so their uncovered entries are listed apart.
OUT_OF_SCOPE_COLUMNS = frozenset({"3v3", "lv", "6v"})
OUT_OF_SCOPE = "out of scope for ws180g005"

# The range fields of the stack, by table.
OXIDE_FIELDS = ("thickness", "vt_n", "vt_p")
METAL_FIELDS = ("thickness", "sheet_rho")


def achieved_ratio(numerator: Decimal, denominator: Decimal) -> Decimal:
    """A margin ratio rounded half-up to 0.001 (`0.22 / 0.1444` gives `1.524`)."""
    return (numerator / denominator).quantize(ACHIEVED_STEP, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Row:
    """One checked field. `cited` holds every cited entry that exists (binding, guideline or
    without a value), `informative` the guideline ones among them, `missing` the cited ids
    the evidence set does not have; `recorded` is the field's own `margin_achieved`
    (`_min`/`_max` for a range row)."""

    field: str
    section: str
    value: Decimal | None
    unit: str | None
    kind: str
    cited: list[Entry]
    informative: list[Entry]
    missing: list[str]
    bound: Decimal | None
    single_source: bool
    margin_required: Decimal | None
    margin_achieved: Decimal | None
    recorded: Decimal | None
    margin_reason: str
    status: Status

    @property
    def binding(self) -> list[Entry]:
        return [e for e in self.cited if _binding(e)]


@dataclass
class Report:
    rows: list[Row]
    uncovered: list[Entry]
    sources: list[Source]
    grid: Decimal
    grids: list[Entry]
    entry_counts: dict[str, int] = field(default_factory=dict)
    cited_counts: dict[str, int] = field(default_factory=dict)

    def __getitem__(self, key: str) -> Row:
        for row in self.rows:
            if row.field == key:
                return row
        raise KeyError(key)

    @property
    def grid_ok(self) -> bool:
        """The process grid is a whole multiple of every grid the evidence records."""
        return all(e.value is not None and e.value > 0 and self.grid % e.value == 0
                   for e in self.grids)

    @property
    def ok(self) -> bool:
        return self.grid_ok and not any(r.status in FAILING for r in self.rows)

    @property
    def in_scope(self) -> list[Entry]:
        """The uncovered entries of the voltage classes and tables ws180g005 has."""
        return [e for e in self.uncovered if e.column not in OUT_OF_SCOPE_COLUMNS]

    @property
    def out_of_scope(self) -> list[Entry]:
        """The uncovered entries of the 3.3 V and 6 V columns."""
        return [e for e in self.uncovered if e.column in OUT_OF_SCOPE_COLUMNS]

    def by_status(self) -> dict[str, int]:
        counts = {s: sum(r.status == s for r in self.rows) for s in STATUSES}
        return {s: n for s, n in counts.items() if n}

    def summary(self) -> str:
        statuses = ", ".join(f"{s} {n}" for s, n in self.by_status().items())
        return (f"{len(self.rows)} rows, ok: {_yes(self.ok)} ({statuses}); "
                f"grid ok: {_yes(self.grid_ok)}; uncovered binding entries: "
                f"{len(self.in_scope)} in scope, {len(self.out_of_scope)} {OUT_OF_SCOPE}")

    def to_markdown(self) -> str:
        return _markdown(self)

    def to_json(self) -> str:
        return json.dumps(_json(self), indent=2, ensure_ascii=False) + "\n"


def margin_report(process: "Process", evidence: Evidence) -> Report:
    """Check every rule and every range field of the stack against the evidence."""
    rows = [_rule_row(rid, rule, process, evidence) for rid, rule in process.rules.items()]
    for name, oxide in process.stack.oxides.items():
        for key in OXIDE_FIELDS:
            rows += _range_rows(f"stack.oxides.{name}.{key}", getattr(oxide, key), evidence)
    for name, metal in process.stack.metals.items():
        for key in METAL_FIELDS:
            if (value := getattr(metal, key)) is not None and value.range is not None:
                rows += _range_rows(f"stack.metals.{name}.{key}", value, evidence)
    cited = _cited_ids(process)
    uncovered = [e for e in evidence.entries.values() if _binding(e) and e.id not in cited]
    entry_counts = {s: 0 for s in evidence.sources}
    cited_counts = {s: 0 for s in evidence.sources}
    for entry in evidence.entries.values():
        entry_counts[entry.source] = entry_counts.get(entry.source, 0) + 1
        if entry.id in cited:
            cited_counts[entry.source] = cited_counts.get(entry.source, 0) + 1
    return Report(
        rows=rows, uncovered=uncovered,
        sources=sorted(evidence.sources.values(), key=lambda s: s.id),
        grid=process.grid.value,
        grids=[e for e in evidence.entries.values() if e.kind == "grid"],
        entry_counts=entry_counts, cited_counts=cited_counts,
    )


def _binding(entry: Entry) -> bool:
    return entry.value is not None and not entry.guideline


def _resolve(ids: list[str], evidence: Evidence) -> tuple[list[Entry], list[str]]:
    cited, missing = [], []
    for eid in dict.fromkeys(ids):
        if eid in evidence.entries:
            cited.append(evidence.entries[eid])
        else:
            missing.append(eid)
    return cited, missing


def _computed_margin(binding: list[Entry], maximum: bool) -> tuple[Decimal, bool]:
    single = bool(binding) and len({e.source for e in binding}) == 1
    if single:
        return SINGLE_SOURCE_MARGIN, True
    return (MAXIMUM_MARGIN if maximum else MINIMUM_MARGIN), False


def _status(*, missing: list[str], provenance: str, has_bound: bool,
            achieved: Decimal | None, required: Decimal | None, reason: str,
            floor: Decimal, recorded: Decimal | None, implied: bool) -> Status:
    """The status of a margined row; failures first, in a fixed order."""
    if missing:
        return "missing-entry"
    if not has_bound:
        # A value without a binding entry is `chosen`; one that claims to be derived from
        # the evidence but cites nothing binding has lost its entry.
        return "chosen" if provenance == "chosen" else "missing-entry"
    if achieved is not None and required is not None and achieved < required:
        return "under-margin"
    if reason and required is not None and required < floor:
        return "override-too-small"
    if achieved != recorded:
        return "achieved-mismatch"
    if provenance == "chosen":
        return "chosen"
    if implied:
        return "implied"
    return "ok"


def _rule_row(rid: str, rule: "RuleField", process: "Process", evidence: Evidence) -> Row:
    ids = rule.evidence + [p for p in rule.composed_of if "/" in p]
    cited, missing = _resolve(ids, evidence)
    binding = [e for e in cited if _binding(e)]
    maximum = rule.kind in MAXIMUM_KINDS
    bound = None
    if binding:
        bound = (min if maximum else max)(e.value for e in binding)
    common = {
        "field": f"rules.{rid}", "section": rid.split(".")[0], "value": rule.value,
        "unit": rule.unit, "kind": rule.kind, "cited": cited,
        "informative": [e for e in cited if e.guideline], "missing": missing, "bound": bound,
        "recorded": rule.margin_achieved, "margin_reason": rule.margin_reason}
    single = bool(binding) and len({e.source for e in binding}) == 1
    if rule.kind == "topology":
        # A named check with a hand-written fixture: no value, so no margin.
        return Row(**common, single_source=single, margin_required=None,
                   margin_achieved=None, status="missing-entry" if missing else "exempt")
    if rule.kind == "exact-size":
        # Cut sizes are exempt from the margin and equal the largest public exact size.
        if missing:
            status: Status = "missing-entry"
        elif bound is None:
            status = "chosen" if rule.provenance == "chosen" else "missing-entry"
        else:
            status = "exempt" if rule.value == bound else "under-margin"
        return Row(**common, single_source=single, margin_required=None,
                   margin_achieved=None, status=status)
    computed, single = _computed_margin(binding, maximum)
    required = rule.margin if rule.margin_reason and rule.margin is not None else computed
    value = rule.value - sum((_field_value(process, p) for p in rule.composed_of if "/" not in p),
                             Decimal(0))
    achieved = None
    if bound is not None and value > 0:
        achieved = achieved_ratio(bound, value) if maximum else achieved_ratio(value, bound)
    status = _status(
        missing=missing, provenance=rule.provenance, has_bound=bound is not None,
        achieved=achieved, required=required, reason=rule.margin_reason,
        floor=MAXIMUM_MARGIN if maximum else MINIMUM_MARGIN, recorded=rule.margin_achieved,
        implied=rule.implied_by is not None)
    return Row(**common, single_source=single, margin_required=required,
               margin_achieved=achieved, status=status)


def _range_rows(path: str, fld: "Field", evidence: Evidence) -> list[Row]:
    """The `.min` and `.max` rows of a range field. Cited values are compared as magnitudes
    (`vt_p` is stored as a magnitude, the card's `vth0` is negative)."""
    cited, missing = _resolve(fld.evidence, evidence)
    binding = [e for e in cited if _binding(e)]
    computed, single = _computed_margin(binding, maximum=False)
    required = fld.margin if fld.margin_reason and fld.margin is not None else computed
    values = [abs(e.value) for e in binding]
    rows = []
    for end, value, bound, recorded in (
            ("min", fld.range.min, min(values, default=None), fld.margin_achieved_min),
            ("max", fld.range.max, max(values, default=None), fld.margin_achieved_max)):
        achieved = None
        if bound is not None and value > 0:
            achieved = (achieved_ratio(bound, value) if end == "min"
                        else achieved_ratio(value, bound))
        status = _status(
            missing=missing, provenance=fld.provenance, has_bound=bound is not None,
            achieved=achieved, required=required, reason=fld.margin_reason,
            floor=MINIMUM_MARGIN, recorded=recorded, implied=False)
        rows.append(Row(
            field=f"{path}.{end}", section="stack", value=value, unit=fld.unit,
            kind=f"range-{end}", cited=cited, informative=[e for e in cited if e.guideline],
            missing=missing, bound=bound, single_source=single, margin_required=required,
            margin_achieved=achieved, recorded=recorded, margin_reason=fld.margin_reason,
            status=status))
    return rows


def _field_value(process: "Process", path: str) -> Decimal:
    """The value of the field a full dotted path names (`rules.sel.x`)."""
    if path.startswith("rules."):
        value = process.rules[path.removeprefix("rules.")].value
    else:
        obj: object = process
        for part in path.split("."):
            obj = obj[part] if isinstance(obj, dict) else getattr(obj, part)
        value = getattr(obj, "value", obj)
    if not isinstance(value, Decimal):
        raise TypeError(f"{path} has no value")
    return value


def _cited_ids(obj: object) -> set[str]:
    """Every evidence id cited anywhere in the process description: the `evidence` lists and
    the entry ids of `composed_of` of every field, rule and stack table."""
    ids: set[str] = set()
    if isinstance(obj, BaseModel):
        for name in type(obj).model_fields:
            value = getattr(obj, name)
            if name in ("evidence", "composed_of") and isinstance(value, list):
                ids |= {v for v in value if isinstance(v, str) and "/" in v}
            else:
                ids |= _cited_ids(value)
    elif isinstance(obj, dict):
        for value in obj.values():
            ids |= _cited_ids(value)
    elif isinstance(obj, (list, tuple)):
        for value in obj:
            ids |= _cited_ids(value)
    return ids


# --- output


def _yes(flag: bool) -> str:
    return "yes" if flag else "no"


def _dec(value: Decimal | None) -> str:
    return "" if value is None else format(value, "f")


def _cell(text: str) -> str:
    return " ".join(text.split()).replace("|", "\\|")


def _ids(entries: list[Entry]) -> str:
    return ", ".join(f"`{e.id}`" for e in entries)


ROW_HEADER = ("| field | value | kind | bound | margin required | margin achieved | status "
              "| cited | informative | margin reason |\n"
              "|---|---|---|---|---|---|---|---|---|---|")


def _row_line(row: Row) -> str:
    value = f"{_dec(row.value)} {row.unit or ''}".strip()
    cited = _ids([e for e in row.cited if not e.guideline])
    if row.missing:
        cited = ", ".join(filter(None, [cited, *(f"`{m}` (missing)" for m in row.missing)]))
    achieved = _dec(row.margin_achieved)
    if row.status == "achieved-mismatch":
        achieved += f" (recorded {_dec(row.recorded) or 'none'})"
    status = f"**{row.status}**" if row.status in FAILING else row.status
    return (f"| `{row.field}` | {value} | {row.kind} | {_dec(row.bound)} "
            f"| {_dec(row.margin_required)} | {achieved} | {status} | {cited} "
            f"| {_ids(row.informative)} | {_cell(row.margin_reason)} |")


def _entry_table(entries: list[Entry]) -> list[str]:
    lines = []
    for kind in sorted({e.kind for e in entries}):
        group = [e for e in entries if e.kind == kind]
        lines += ["", f"### {kind} ({len(group)})", "", "| id | value | text |", "|---|---|---|"]
        lines += [f"| `{e.id}` | {_dec(e.value)} {e.unit or ''} | {_cell(e.text)} |"
                  for e in group]
    return lines


def _markdown(report: Report) -> str:
    lines = ["# ws180g evidence margin report", "",
             f"**Summary:** {report.summary()}.", "",
             ("Margins are ratios: `value / bound` for a minimum (`bound / value` for a "
              "maximum), after subtracting the `composed_of` fields of a composed rule; a "
              "range row compares `smallest cited / min` and `max / largest cited`. Ratios "
              "are rounded half-up to 0.001. Guideline entries are informative and never "
              "bind."), "",
             "## Rules"]
    sections = list(dict.fromkeys(r.section for r in report.rows if r.section != "stack"))
    for section in sections:
        lines += ["", f"### {section}", "", ROW_HEADER]
        lines += [_row_line(r) for r in report.rows if r.section == section]
    lines += ["", "## Stack", "", ROW_HEADER]
    lines += [_row_line(r) for r in report.rows if r.section == "stack"]
    grids = ", ".join(f"`{e.id}` {_dec(e.value)} {e.unit or ''}".strip() for e in report.grids)
    lines += ["", "## Grid", "",
              (f"Process grid {_dec(report.grid)} um; evidence grids: {grids or 'none'}; "
               f"multiple of every one: {_yes(report.grid_ok)}.")]
    lines += ["", "## Uncovered binding entries", "",
              f"{len(report.in_scope)} binding entries that no field cites, by kind."]
    lines += _entry_table(report.in_scope)
    lines += ["", f"## Uncovered, {OUT_OF_SCOPE}", "",
              (f"{len(report.out_of_scope)} binding entries of the 3.3 V (`3v3`, `lv`) and "
               "6 V (`6v`) columns that no field cites, by kind.")]
    lines += _entry_table(report.out_of_scope)
    lines += ["", "## Sources", "", "| id | title | status | entries | cited | retrieved |",
              "|---|---|---|---|---|---|"]
    for s in report.sources:
        status = "transcribed" if s.transcribed else "registered, not yet transcribed"
        lines.append(f"| `{s.id}` | {_cell(s.title)} | {status} | "
                     f"{report.entry_counts.get(s.id, 0)} | {report.cited_counts.get(s.id, 0)} "
                     f"| {s.retrieved.isoformat() if s.retrieved else ''} |")
    return "\n".join(lines) + "\n"


def _entry_json(entry: Entry) -> dict:
    return {"id": entry.id, "source": entry.source, "kind": entry.kind, "column": entry.column,
            "value": _dec(entry.value) or None, "unit": entry.unit,
            "guideline": entry.guideline, "text": entry.text}


def _json(report: Report) -> dict:
    return {
        "summary": report.summary(),
        "ok": report.ok,
        "grid_ok": report.grid_ok,
        "grid": _dec(report.grid),
        "grids": [e.id for e in report.grids],
        "by_status": report.by_status(),
        "rows": [{
            "field": r.field, "section": r.section, "value": _dec(r.value) or None,
            "unit": r.unit, "kind": r.kind, "bound": _dec(r.bound) or None,
            "single_source": r.single_source,
            "margin_required": _dec(r.margin_required) or None,
            "margin_achieved": _dec(r.margin_achieved) or None,
            "margin_recorded": _dec(r.recorded) or None,
            "margin_reason": r.margin_reason, "status": r.status,
            "cited": [e.id for e in r.cited if not e.guideline],
            "informative": [e.id for e in r.informative], "missing": r.missing,
        } for r in report.rows],
        "uncovered": [_entry_json(e) for e in report.in_scope],
        "out_of_scope": [_entry_json(e) for e in report.out_of_scope],
        "sources": [{
            "id": s.id, "title": s.title, "transcribed": s.transcribed,
            "retrieved": s.retrieved.isoformat() if s.retrieved else None,
            "entries": report.entry_counts.get(s.id, 0),
            "cited": report.cited_counts.get(s.id, 0),
        } for s in report.sources],
    }


def main(argv: list[str] | None = None) -> int:
    """`ws180g-evidence-report [--markdown PATH] [--json PATH]`: print the summary and the
    failing rows; exit 1 when the report is not ok."""
    from ws180g_process.load import DEFAULT_DATA as PROCESS_DATA
    from ws180g_process.load import load_process

    from ws180g_evidence.load import DEFAULT_DATA as EVIDENCE_DATA
    from ws180g_evidence.load import load_evidence

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--markdown", type=Path, help="write the Markdown report here")
    parser.add_argument("--json", type=Path, help="write the JSON report here")
    parser.add_argument("--process", type=Path, default=PROCESS_DATA,
                        help="process data directory (default: process/data/ws180g)")
    parser.add_argument("--evidence", type=Path, default=EVIDENCE_DATA,
                        help="evidence data directory (default: evidence/data)")
    args = parser.parse_args(argv)
    report = margin_report(load_process(args.process), load_evidence(args.evidence))
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(report.to_markdown(), encoding="utf-8")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(report.to_json(), encoding="utf-8")
    print(report.summary())
    for row in report.rows:
        if row.status in FAILING:
            missing = f", missing {', '.join(row.missing)}" if row.missing else ""
            print(f"  {row.field}: {row.status} (value {_dec(row.value)}, bound "
                  f"{_dec(row.bound) or '-'}, required {_dec(row.margin_required) or '-'}, "
                  f"achieved {_dec(row.margin_achieved) or '-'}, recorded "
                  f"{_dec(row.recorded) or '-'}{missing})")
    if not report.grid_ok:
        print(f"  grid {_dec(report.grid)} is not a multiple of every evidence grid")
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
