# SPDX-License-Identifier: Apache-2.0
"""Import the GF180MCU design-manual tables (`evidence/sources/gf180mcu-drm/*.csv`) into
`evidence/data/gf180mcu-drm.toml`.

A rule table is headed `RULE NO.` (binding rules) or `GUIDELINE NO.` (every row a
guideline). Its value columns are named by a row whose first cell is `Layer` (or, failing
that, by the header): voltage classes `3v3`, `5v`, `6v`, `lv`, `mv` and the bond-pad types
`wedge`, `ball`, `bump`; a table with one unnamed value column gives entries without a
column. One entry is written per value: `<source>/<rule>[/<column>][/<part>]`. Tables
that are not rule tables are skipped and listed, except the design grid and the metal-stack
option table. The output is byte-identical across runs.
"""

import argparse
import csv
import re
from decimal import Decimal
from pathlib import Path

from ws180g_evidence.model import Entry

SOURCE = "gf180mcu-drm"
REPO = Path(__file__).resolve().parents[3]
DEFAULT_SRC = REPO / "evidence" / "sources" / SOURCE
DEFAULT_OUT = REPO / "evidence" / "data" / f"{SOURCE}.toml"

GRID_TABLE = "10_Design_Geometry_Rules27.csv"
METAL_OPTION_TABLE = "05_Current_0.18_MCU_9.csv"

# Normalised header cells of a rule table, and whether every row is a guideline. A table
# headed `NO.` (31_Top_Metal_76, 32_Probe_pad_79) is a rule table only when its second
# header cell is `DESCRIPTION`; `No.` also heads the device list.
RULE_HEADERS = {"RULE NO": False, "GUIDELINE NO": True, "NO": False}

# The ordered kind match on the description: the first pattern that matches wins.
_MINMAX = r"\bmin\.?\s*/\s*max"
COVERAGE = r"\bcoverage|\bdensity"
KIND_PATTERNS: list[tuple[str, list[str]]] = [
    ("exact-size", [_MINMAX, r"\bsize"]),
    ("min-space", [_MINMAX, r"\bspac"]),
    ("ratio", [r"\bratio"]),
    ("density-ceiling", [COVERAGE, r"\bmax"]),
    ("density-floor", [COVERAGE]),
    ("max-distance", [r"\bmax", r"\bdistance|\bspac"]),
    ("max-width", [r"\bmax", r"width"]),
    ("min-area", [r"\barea"]),
    ("min-enclosure", [r"overlap|\benclos"]),
    ("min-extension", [r"\bextension|\bextend|overhang"]),
    ("min-space", [r"\bspac"]),
    ("min-width", [r"width"]),
]

# A number with an optional unit and guideline star: `0.35 μm2`, `1mA/um`, `25%`, `0.44*`.
NUMBER = re.compile(
    r"^(?P<num>\d+(?:\.\d+)?)\s*(?P<unit>[uμµ]m2|mA/[uμµ]m|%|[uμµ]m)?\s*(?P<star>\*+)?$")
# A value with a parenthesised condition: `0.23 (n = 1)`.
CONDITIONED = re.compile(r"^(?P<value>[^()]+?)\s*\((?P<condition>[^()]*)\)$")
# A continuation row's part letter: `a\) If x >= 2.0um ...`.
PART_LETTER = re.compile(r"^\(?(?P<letter>[a-z]\d?)\\?\)\s*")
# A percentage in a coverage description: `>= 14%`, `>30%`.
PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s*%")
# A unit named in the description: `Min. COMP area (um2)`, `current density ... (mA/um)`.
DESCRIPTION_UNIT = re.compile(r"\(\s*([uμµ]m2|mA/[uμµ\uf06d]?m)\s*\)")
# LRES.8 prints `(mA/\uf06dm)`: a Symbol-font micro sign in a private-use code point, shown
# as `(mA/m)`. 70_not_coded_rules_187.csv row LRES.8 gives the unit as mA/um.
MA_PER_UM_NOTE = (" [unit printed as (mA/m) with a Symbol-font micro sign U+F06D or none;"
                  " read as mA/um as in 70_not_coded_rules_187.csv row LRES.8]")
NOT_A_VALUE = {"", "NA", "-", "--"}

KEY_ORDER = ["id", "source", "rule", "column", "part", "kind", "layers", "value", "unit",
             "text", "cite", "guideline", "lambda", "lambda_um"]


def import_gf180mcu(src_dir: Path = DEFAULT_SRC, out_path: Path = DEFAULT_OUT) -> int:
    """Import every table of `src_dir` into one TOML file; return the number of entries.

    Prints the tables skipped as not being rule tables and the value cells dropped because
    they hold no plain number."""
    entries: list[Entry] = []
    imported: list[str] = []
    skipped: list[str] = []
    dropped: list[str] = []
    for csv_path in sorted(src_dir.glob("*.csv")):
        table = table_entries(csv_path, dropped)
        if table is None:
            skipped.append(csv_path.name)
        else:
            imported.append(csv_path.name)
            entries += table
    _check_unique(entries)
    _write(entries, out_path)
    print(f"{len(entries)} entries from {len(imported)} tables written to {out_path}")
    print(f"skipped {len(skipped)} tables that are not rule tables:")
    for name in skipped:
        print(f"  {name}")
    _print_dropped(dropped)
    return len(entries)


def import_gf180mcu_table(csv_path: Path, out_path: Path) -> int:
    """Import one table into a TOML file of its own; return the number of entries."""
    dropped: list[str] = []
    entries = table_entries(csv_path, dropped) or []
    _check_unique(entries)
    _write(entries, out_path)
    _print_dropped(dropped)
    return len(entries)


def _print_dropped(dropped: list[str]) -> None:
    print(f"dropped {len(dropped)} value cells that hold no plain number:")
    for line in dropped:
        print(f"  {line}")


def table_entries(csv_path: Path, dropped: list[str] | None = None) -> list[Entry] | None:
    """The entries of one table, or `None` when it is not a rule table. Value cells that
    hold text rather than a number are appended to `dropped` as
    `<file>, row <rule>, column <column or ->: <cell>`."""
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    if csv_path.name == METAL_OPTION_TABLE:
        return _metal_options(csv_path.name, rows)
    if not _is_rule_table(rows):
        return None
    return _rule_table(csv_path.name, rows, [] if dropped is None else dropped)


def _header(rows: list[list[str]]) -> str:
    """The first header cell, normalised: `Rule NO` and `RULE\\nNO.` give `RULE NO`."""
    return _normalise(rows[0][0]).upper().rstrip(".") if rows and rows[0] else ""


def _is_rule_table(rows: list[list[str]]) -> bool:
    header = _header(rows)
    if header == "NO":
        return len(rows[0]) > 1 and _normalise(rows[0][1]).upper() == "DESCRIPTION"
    return header in RULE_HEADERS


def _normalise(text: str) -> str:
    """Unescape the Markdown escapes of the tables and collapse whitespace."""
    text = text.replace("\\*", "*").replace("\\-", "-").replace("\\)", ")")
    return " ".join(text.split())


def _column_name(cell: str) -> str | None:
    """The column suffix a value-column heading stands for, or `None`."""
    name = _normalise(cell).lower()
    if name.startswith("3.3v"):
        return "3v3"
    if name.startswith("5v"):  # `5V`, `5V/6V`, `5V OTP (1)`
        return "5v"
    if name.startswith("6v"):
        return "6v"
    if name in ("lv", "mv"):
        return name
    for pad in ("wedge", "ball", "bump"):
        if pad in name:
            return pad
    if name == "other cases":
        return "other"
    return None


def _value_columns(rows: list[list[str]]) -> tuple[list[tuple[int, str | None]], int]:
    """The value columns `(index, suffix)` and the index of the first rule row.

    Column names come from a `Layer` row, or from an unlabelled row (empty rule and
    description cells) that names voltage classes, or else from the header. When no column
    has a name, the first column after the description is the one value column."""
    names, first = rows[0], 1
    row = rows[1] if len(rows) > 1 else []
    label = _normalise(row[0]).lower() if row else ""
    named_here = any(_column_name(c) for c in row[2:])
    unlabelled = len(row) > 2 and not label and not _normalise(row[1])
    if label == "layer" or (unlabelled and named_here):
        first = 2
        if named_here:
            names = row
    named = [(i, _column_name(c)) for i, c in enumerate(names) if i >= 2 and _column_name(c)]
    if named:
        return named, first
    return [(2, None)], first


def _rule_table(file: str, rows: list[list[str]], dropped: list[str]) -> list[Entry]:
    all_guideline = RULE_HEADERS[_header(rows)]
    columns, first = _value_columns(rows)
    entries: list[Entry] = []
    rule: str | None = None
    rule_guideline = False
    parent_text = ""
    for row in rows[first:]:
        if not row:
            continue
        lines = [_normalise(line) for line in (row[1] if len(row) > 1 else "").splitlines()]
        lines = [line for line in lines if line]
        description = " ".join(lines)
        raw_rule = _normalise(row[0].strip().splitlines()[0]) if row[0].strip() else ""
        part_letter = None
        if raw_rule:
            rule, part_letter, rule_guideline = _rule_id(raw_rule)
            parent_text = text = description
        else:
            match = PART_LETTER.match(description)
            if rule is None or match is None:
                continue  # a heading or a note between rules
            part_letter = match.group("letter")
            text = f"{parent_text} {description}".strip()
            lines[0] = lines[0][match.end():]
            description = description[match.end():]
        if file == GRID_TABLE:
            entries += _grid(file, rule, row)
            continue
        cells = [(column, row[i] if i < len(row) else "") for i, column in columns]
        if re.search(COVERAGE, description, re.IGNORECASE) and all(
                _normalise(c) in NOT_A_VALUE for _, c in cells):
            percent = PERCENT.search(description)
            if percent:
                cells = [(column, f"{percent.group(1)}%") for column, _ in cells]
        described = DESCRIPTION_UNIT.search(description)
        if described and described.group(1) in ("mA/m", "mA/\uf06dm"):
            text += MA_PER_UM_NOTE
        for column, cell in cells:
            values = _values(cell, rule)
            if not values and _normalise(cell) not in NOT_A_VALUE:
                dropped.append(f"{file}, row {rule}, column {column or '-'}: {_normalise(cell)}")
            for part, value, unit, star in values:
                if part_letter:
                    part = part_letter if part is None else f"{part_letter}-{part}"
                if unit is None and described:
                    unit = _unit(described.group(1))
                kind = _kind(lines[0] if lines else "", unit)
                if kind == "other":
                    kind = _kind(description, unit)
                if unit is None:
                    unit = "1" if kind == "ratio" else "um"
                entries.append(_entry(
                    file, rule, column, part, kind, value, unit, text,
                    guideline=all_guideline or rule_guideline or star))
    return entries


def _rule_id(raw: str) -> tuple[str, str | None, bool]:
    """The rule id without footnote markers, the part a parenthesised letter names, and
    whether an asterisk marks a guideline: `ANT.2 (1)` → `ANT.2`, `DF.15a**` → `DF.15a`
    (guideline), `TM. 3b*` → `TM.3b`, `LVESD.3 (a)` → `LVESD.3` part `a`."""
    guideline = "*" in raw
    letter = re.search(r"\(([a-z])\)", raw)
    rule = re.sub(r"\([^()]*\)", "", raw).replace("*", "")
    return "".join(rule.split()), letter.group(1) if letter else None, guideline


def _kind(description: str, unit: str | None) -> str:
    """The first kind of `KIND_PATTERNS` whose patterns all match; `min-area` only for a
    value in um2 (the word "area" also names regions: `Min. COMP Space in BJT area`)."""
    for kind, patterns in KIND_PATTERNS:
        if kind == "min-area" and unit != "um2":
            continue
        if all(re.search(p, description, re.IGNORECASE) for p in patterns):
            return kind
    return "other"


def _values(cell: str, rule: str) -> list[tuple[str | None, Decimal, str | None, bool]]:
    """The values of one cell as `(part, value, unit, guideline)`; empty when the cell
    holds no number (`NA`, `--`, text). Several lines give parts `a`, `b`, ... or, when
    each carries a condition such as `(n = 1)`, `m1` and `mn`; `a/b` gives parts `a` and
    `b` (`n` and `p` for the gate length PL.2)."""
    lines = [_normalise(line) for line in cell.splitlines()]
    lines = [line for line in lines if line]
    if not lines or (len(lines) == 1 and lines[0] in NOT_A_VALUE):
        return []
    conditioned = [CONDITIONED.match(line) for line in lines]
    if len(lines) > 1 and all(conditioned):
        parts = ["m1" if re.fullmatch(r"n\s*=\s*1", m.group("condition")) else "mn"
                 for m in conditioned]
    elif len(lines) > 1:
        parts = _letters(len(lines))
    elif "/" in lines[0] and "mA/" not in lines[0]:
        lines = [piece.strip() for piece in lines[0].split("/")]
        parts = ["n", "p"] if rule == "PL.2" and len(lines) == 2 else _letters(len(lines))
    else:
        parts = [None]
    values = []
    for part, line in zip(parts, lines, strict=True):
        match = CONDITIONED.match(line)
        match = NUMBER.match(match.group("value") if match else line)
        if match is None:
            return []
        values.append((part, Decimal(match.group("num")), _unit(match.group("unit")),
                       bool(match.group("star"))))
    return values


def _letters(count: int) -> list[str]:
    return [chr(ord("a") + i) for i in range(count)]


def _unit(token: str | None) -> str | None:
    """The unit a token stands for; `mA/m` (the LRES.8 misprint) is mA/um."""
    if token is None:
        return None
    if token.endswith("m2"):
        return "um2"
    if token.startswith("mA"):
        return "mA/um"
    if token == "%":
        return "%"
    return "um"


def _entry(file: str, rule: str, column: str | None, part: str | None, kind: str,
           value: Decimal, unit: str, text: str, guideline: bool) -> Entry:
    id_ = "/".join(p for p in (SOURCE, rule, column, part) if p)
    return Entry(id=id_, source=SOURCE, rule=rule, column=column, part=part, kind=kind,
                 value=value, unit=unit, text=text,
                 cite=f"{file}, row {rule}, column {column or '-'}", guideline=guideline)


def _grid(file: str, rule: str, row: list[str]) -> list[Entry]:
    """The `GRID` row of the design-geometry table: the grid named in its description."""
    if rule != "GRID":
        return []
    text = _normalise(row[1])
    match = re.search(r"multiple of (\d+(?:\.\d+)?)\s*[uμµ]m", text)
    if match is None:
        raise ValueError(f"{file}: no grid in row GRID: {text}")
    return [_entry(file, rule, None, None, "grid", Decimal(match.group(1)), "um", text,
                   guideline=False)]


def _metal_options(file: str, rows: list[list[str]]) -> list[Entry]:
    """The top-metal thicknesses of the metal-stack options: `TM<n>K` is n kÅ = n/10 um."""
    entries: dict[str, Entry] = {}
    for row in rows[1:]:
        for token in re.findall(r"TM(\d+)K", " ".join(row)):
            rule = f"TM{token}K"
            if rule not in entries:
                entries[rule] = _entry(
                    file, rule, None, None, "thickness", Decimal(token).scaleb(-1), "um",
                    f"Top metal thickness of metal stack option {_normalise(row[1])}",
                    guideline=False)
    return list(entries.values())


def _check_unique(entries: list[Entry]) -> None:
    seen: dict[str, str] = {}
    for entry in entries:
        if entry.id in seen:
            raise ValueError(f"duplicate id {entry.id}: {seen[entry.id]} and {entry.cite}")
        seen[entry.id] = entry.cite


def _toml_string(text: str) -> str:
    out = []
    for ch in text:
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ord(ch) < 0x20 or ord(ch) == 0x7F:
            out.append(f"\\u{ord(ch):04X}")
        else:
            out.append(ch)
    return '"' + "".join(out) + '"'


def _toml_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, str):
        return _toml_string(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    raise TypeError(f"no TOML literal for {type(value).__name__}")


def _natural(entry: Entry) -> tuple[list, str]:
    """Sort key: the id with its digit runs compared as numbers (`PL.2` before `PL.10`),
    then the id itself, so that the order is total."""
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", entry.id)], entry.id


def _write(entries: list[Entry], out_path: Path,
           generated: str = f"ws180g-import-gf180mcu from evidence/sources/{SOURCE}/",
           header: str | None = None) -> None:
    """Write the entries in natural order of id, one `[[entry]]` table each, keys in
    `KEY_ORDER`, keys whose value is `None` left out; `generated` names the generator in
    the header comment. `header` replaces that whole comment line (a hand-written file's
    own header, so it can be checked by writing it back)."""
    lines = [
        "# SPDX-License-Identifier: Apache-2.0",
        header if header is not None else f"# Generated by {generated}; do not edit.",
    ]
    for entry in sorted(entries, key=_natural):
        data = entry.model_dump(by_alias=True)
        lines.append("")
        lines.append("[[entry]]")
        for key in KEY_ORDER:
            if data[key] is not None:
                lines.append(f"{key} = {_toml_value(data[key])}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--src", type=Path, default=DEFAULT_SRC)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    import_gf180mcu(args.src, args.out)


if __name__ == "__main__":
    main()
