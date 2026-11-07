# SPDX-License-Identifier: Apache-2.0
"""The rule table: the machine-readable view of the rule fields of the process description.

The DRC deck generators, the fixture generator, the Magic tech generator and the manual read
this table; it is built from `Process.rules` alone and never reads the evidence set (the
achieved margin is the author's figure, copied from the field and checked by the margin
report).
"""

import argparse
import csv
import json
from dataclasses import asdict, dataclass, fields
from decimal import Decimal
from pathlib import Path

from ws180g_process.model import Process, RuleField

from ws180g_rules.layer_expr import LayerExpr, parse_layer_expr

DEFAULT_VARIANT = "ws180g005"
_DECIMALS = ("value", "margin", "margin_achieved")


@dataclass(frozen=True)
class RuleRow:
    """One rule, `rules.<id>`, with its layer expressions parsed and aliases expanded. `text`
    is the rule's note; `module` the optional module the rule belongs to (None: baseline)."""

    id: str
    kind: str
    layers: list[LayerExpr]
    value: Decimal | None
    unit: str | None
    field: str
    variant: str
    module: str | None
    evidence: list[str]
    margin: Decimal | None
    margin_reason: str
    margin_achieved: Decimal | None
    composed_of: list[str]
    engines: list[str]
    condition: str | None
    edges: str | None
    edge_layer: str | None
    implied_by: str | None
    fixture: str | None
    text: str

    @classmethod
    def from_rule(cls, rid: str, rule: RuleField, process: Process) -> "RuleRow":
        return cls(
            id=rid, kind=rule.kind,
            layers=[parse_layer_expr(e, process.aliases, process.layers) for e in rule.layers],
            value=rule.value, unit=rule.unit, field=f"rules.{rid}", variant=rule.variant,
            module=rule.module, evidence=list(rule.evidence), margin=rule.margin,
            margin_reason=rule.margin_reason, margin_achieved=rule.margin_achieved,
            composed_of=list(rule.composed_of), engines=list(rule.engines),
            condition=rule.condition, edges=rule.edges, edge_layer=rule.edge_layer,
            implied_by=rule.implied_by, fixture=rule.fixture, text=rule.note,
        )

    def to_json(self) -> dict:
        data = asdict(self)
        data["layers"] = [str(e) for e in self.layers]
        for key in _DECIMALS:
            if data[key] is not None:
                data[key] = str(data[key])
        return data

    @classmethod
    def from_json(cls, data: dict, layer_names: list[str]) -> "RuleRow":
        data = dict(data)
        data["layers"] = [parse_layer_expr(e, {}, layer_names) for e in data["layers"]]
        for key in _DECIMALS:
            if data[key] is not None:
                data[key] = Decimal(data[key])
        return cls(**data)


CSV_COLUMNS = [f.name for f in fields(RuleRow)]


@dataclass
class RuleTable:
    """The rules of one variant (its own and those of the variants it contains), in a stable
    order: by the first layer name of the first expression, in `layers.toml` order (rules with
    no layers last), then by id. `layers` is that layer order."""

    variant: str
    layers: list[str]
    rows: list[RuleRow]

    @classmethod
    def from_process(cls, process: Process, variant: str = DEFAULT_VARIANT) -> "RuleTable":
        if variant not in process.variants:
            raise KeyError(f"unknown variant {variant}")
        wanted = {variant, *process.variants[variant].contains}
        rows = [RuleRow.from_rule(rid, rule, process)
                for rid, rule in process.rules.items() if rule.variant in wanted]
        return cls(variant, list(process.layers), rows)._in_order()

    def _in_order(self) -> "RuleTable":
        order = {name: i for i, name in enumerate(self.layers)}

        def key(row: RuleRow) -> tuple[int, str]:
            first = row.layers[0].names()[0] if row.layers else None
            return (len(order) if first is None else order[first], row.id)

        return RuleTable(self.variant, self.layers, sorted(self.rows, key=key))

    def __getitem__(self, rid: str) -> RuleRow:
        for row in self.rows:
            if row.id == rid:
                return row
        raise KeyError(f"no rule {rid} in the {self.variant} table")

    def __len__(self) -> int:
        return len(self.rows)

    def checkable(self) -> list[RuleRow]:
        """The rows a DRC deck checks: those with at least one engine."""
        return [r for r in self.rows if r.engines]

    def with_fail_fixture(self) -> list[RuleRow]:
        """The checkable rows that get a fail fixture: those not implied by another rule."""
        return [r for r in self.checkable() if r.implied_by is None]

    def write_json(self, path: Path) -> None:
        data = {"variant": self.variant, "layers": self.layers,
                "rows": [r.to_json() for r in self.rows]}
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    @classmethod
    def read_json(cls, path: Path) -> "RuleTable":
        data = json.loads(path.read_text(encoding="utf-8"))
        layers = list(data["layers"])
        return cls(data["variant"], layers,
                   [RuleRow.from_json(r, layers) for r in data["rows"]])

    def write_csv(self, path: Path) -> None:
        """One row per rule; lists (layer expressions included) are joined by spaces, unset
        values are empty."""
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, lineterminator="\n")
            writer.writerow(CSV_COLUMNS)
            for row in self.rows:
                cells = []
                for name in CSV_COLUMNS:
                    value = getattr(row, name)
                    if isinstance(value, list):
                        value = " ".join(str(v) for v in value)
                    cells.append("" if value is None else str(value))
                writer.writerow(cells)


def main(argv: list[str] | None = None) -> int:
    """`ws180g-rule-table [--variant V] [--json PATH] [--csv PATH]`: build the rule table of
    variant V (default ws180g005) from the process description, write it where asked and
    print a one-line summary."""
    from ws180g_process.load import load_process

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--variant", default=DEFAULT_VARIANT,
                        help=f"process variant (default: {DEFAULT_VARIANT})")
    parser.add_argument("--json", type=Path, help="write the table as JSON here")
    parser.add_argument("--csv", type=Path, help="write the table as CSV here")
    args = parser.parse_args(argv)
    table = RuleTable.from_process(load_process(), args.variant)
    for path, write in ((args.json, table.write_json), (args.csv, table.write_csv)):
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            write(path)
    print(f"{table.variant}: {len(table)} rules, {len(table.checkable())} checkable, "
          f"{len(table.with_fail_fixture())} with a fail fixture")
    return 0
