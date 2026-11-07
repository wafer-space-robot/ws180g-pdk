# SPDX-License-Identifier: Apache-2.0
"""Import the MOSIS SCMOS rev 8.00 layout rules into `evidence/data/scmos8.toml`.

The pages are fetched from the UCSB ECE 224A mirror into `tmp/scmos8/` (gitignored: the
material is not redistributed), their sha256 and the retrieval date are recorded in
`evidence/data/sources.toml`, and the rule tables are read with `html.parser`.

A layer page holds rule tables headed `Rule | Description | Lambda`, with the columns
SCMOS, SUBM and DEEP, on the metal pages repeated per column group ("2 Metal Process",
"3+ Metal Process"); the group for the most metals is used. One entry is written per rule
and column, `scmos8/<rule>/<scmos|subm|deep>`: `lambda` is the lambda count, `lambda_um`
the lambda of the TSMC 0.18 um six-metal mapping read from the index page (Table 2b,
SCN6M_SUBM; Table 2c, SCN6M_DEEP) and `value` their product in um. The SCMOS column has
no 0.18 um mapping: its entries keep the count only. `n/a` gives no entry. The overglass
table (section 10) is in microns; its rows are guidelines, `scmos8/<rule>`. The output is
byte-identical across runs.
"""

import argparse
import hashlib
import re
import tomllib
import urllib.request
from collections.abc import Iterable
from datetime import date
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path

from ws180g_evidence.import_gf180mcu import _check_unique, _kind, _toml_string, _write
from ws180g_evidence.model import Entry

SOURCE = "scmos8"
REPO = Path(__file__).resolve().parents[3]
DEFAULT_DIR = REPO / "tmp" / SOURCE
DEFAULT_OUT = REPO / "evidence" / "data" / f"{SOURCE}.toml"
DEFAULT_SOURCES = REPO / "evidence" / "data" / "sources.toml"

BASE_URL = "https://bears.ece.ucsb.edu/class/ece224a/scmos/"
# Page names: `scmos-<page>.html` under BASE_URL. `main` is the index page (Tables 2b,
# 2c); the thick-active page is `scmos-thick-active.html` (`scmos-thickactive.html`
# redirects to it).
PAGES = ("main", "well", "active", "poly", "select", "contact", "metal1", "metal2",
         "metal3", "metal4", "metal5", "metal6", "glass", "sblock", "thick-active", "dnw")
INDEX = "main"
TITLE = "MOSIS Scalable CMOS (SCMOS) Design Rules, revision 8.00 (UCSB ECE 224A mirror)"
LICENCE = "see README: not redistributed"

# The sections the ws180g rule table cites; the import fails when one is missing.
CITED_SECTIONS = frozenset(
    {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 14, 15, 20, 21, 22, 24, 25, 26, 29, 30, 31})

COLUMNS = ("scmos", "subm", "deep")
# The technology code whose lambda maps a column to the TSMC 0.18 um six-metal process.
LAMBDA_CODES = {"subm": "SCN6M_SUBM", "deep": "SCN6M_DEEP"}

RULE_ID = re.compile(r"^\d+\.\d+(?:\.[a-z])?$")
# A lambda count or micron value, an exact size `2x2` / `3 x 3`, a footnote star.
VALUE = re.compile(r"^(?P<num>\d+(?:\.\d+)?)(?:\s*x\s*(?P<num2>\d+(?:\.\d+)?))?\s*\**$",
                   re.IGNORECASE)
GROUP = re.compile(r"^(\d+)\+?\s+metal\s+process$", re.IGNORECASE)
HEADING_PREFIX = re.compile(r"^SCMOS Layout Rules\s*-\s*", re.IGNORECASE)
# Layer names that differ from the heading word.
LAYER_ALIASES = {"via": "via1", "overglass": "glass"}


class _Open:
    """A table being read: its rows and the row and cell not yet closed."""

    def __init__(self, rows: list[list[str]]) -> None:
        self.rows = rows
        self.row: list[str] | None = None
        self.cell: list[str] | None = None

    def end_cell(self) -> None:
        if self.cell is not None and self.row is not None:
            self.row.append(_collapse("".join(self.cell)))
        self.cell = None

    def end_row(self) -> None:
        self.end_cell()
        if self.row is not None:
            self.rows.append(self.row)
        self.row = None


class _Tables(HTMLParser):
    """The tables of a page as rows of whitespace-collapsed cell text, each with the
    `SCMOS Layout Rules - ...` `<h3>` heading in force before it (other `<h3>` are figure
    captions), and the page `<title>`. A table nested in a cell is a table of its own; its
    text is not part of the enclosing cell."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.tables: list[tuple[str, list[list[str]]]] = []
        self._heading: str = ""
        self._in: str | None = None  # "title" or "h3" while their text is collected
        self._text: list[str] = []
        self._open: list[_Open] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        top = self._open[-1] if self._open else None
        if tag in ("title", "h3"):
            self._in, self._text = tag, []
        elif tag == "table":
            self.tables.append((self._heading, []))
            self._open.append(_Open(self.tables[-1][1]))
        elif tag == "tr" and top is not None:
            top.end_row()
            top.row = []
        elif tag in ("td", "th") and top is not None:
            top.end_cell()
            top.cell = []

    def handle_endtag(self, tag: str) -> None:
        top = self._open[-1] if self._open else None
        if tag == self._in:
            text = _collapse("".join(self._text))
            if tag == "title":
                self.title = text
            elif HEADING_PREFIX.match(text):
                self._heading = text
            self._in = None
        elif tag in ("td", "th") and top is not None:
            top.end_cell()
        elif tag == "tr" and top is not None:
            top.end_row()
        elif tag == "table" and top is not None:
            top.end_row()
            self._open.pop()

    def handle_data(self, data: str) -> None:
        if self._in is not None:
            self._text.append(data)
        if self._open and self._open[-1].cell is not None:
            self._open[-1].cell.append(data)

    def close(self) -> None:
        super().close()
        while self._open:
            self._open.pop().end_row()


def _collapse(text: str) -> str:
    return " ".join(text.split())


def _parse(html: str) -> _Tables:
    parser = _Tables()
    parser.feed(html)
    parser.close()
    return parser


def import_scmos(pages: dict[str, str], out_path: Path,
                 required: Iterable[int] = CITED_SECTIONS) -> int:
    """Import the pages (page name → HTML text, `main` the index page) into one TOML file;
    return the number of entries. Raises `ValueError` when a section of `required` has
    no entry or the index page gives no lambda for a column. Prints the entries per page,
    the rule rows without values and the value cells that hold no number."""
    if INDEX not in pages:
        raise ValueError(f"the index page '{INDEX}' is missing")
    lambdas = lambda_mapping(pages[INDEX])
    entries: list[Entry] = []
    counts: dict[str, int] = {}
    valueless: list[str] = []
    dropped: list[str] = []
    for page in sorted(p for p in pages if p != INDEX):
        found = page_entries(page, pages[page], lambdas, valueless, dropped)
        counts[page] = len(found)
        entries += found
    missing = sorted(set(required) - {int(e.rule.split(".")[0]) for e in entries})
    if missing:
        raise ValueError("SCMOS sections not found: " + ", ".join(map(str, missing)))
    _check_unique(entries)
    _write(entries, out_path, generated="ws180g-import-scmos from the SCMOS rev 8.00 pages"
                                        " listed in evidence/sources/scmos8/README.md")
    print(f"{len(entries)} entries written to {out_path}")
    for page, count in counts.items():
        print(f"  scmos-{page}.html: {count}")
    print(f"{len(valueless)} rule rows without values (text rules):")
    for line in valueless:
        print(f"  {line}")
    print(f"{len(dropped)} value cells that hold no number:")
    for line in dropped:
        print(f"  {line}")
    return len(entries)


def lambda_mapping(html: str) -> dict[str, Decimal]:
    """The lambda in um of each mapped column: the `Lambda (micrometers)` cell of the
    index-page row whose options name the column's technology code."""
    found: dict[str, set[Decimal]] = {column: set() for column in LAMBDA_CODES}
    for _, rows in _parse(html).tables:
        if not rows:
            continue
        lambda_cells = [i for i, c in enumerate(rows[0]) if c.lower().startswith("lambda")]
        if not lambda_cells:
            continue
        index = lambda_cells[0]
        for row in rows[1:]:
            codes = {code.strip() for cell in row for code in cell.split(",")}
            for column, code in LAMBDA_CODES.items():
                if code in codes and index < len(row):
                    found[column].add(Decimal(row[index]))
    mapping: dict[str, Decimal] = {}
    for column, values in found.items():
        if len(values) != 1:
            raise ValueError(f"index page: {len(values)} lambda values for "
                             f"{LAMBDA_CODES[column]}: {sorted(values)}")
        mapping[column] = values.pop()
    return mapping


def page_entries(page: str, html: str, lambdas: dict[str, Decimal],
                 valueless: list[str] | None = None,
                 dropped: list[str] | None = None) -> list[Entry]:
    """The entries of the rule tables of one layer page."""
    valueless = [] if valueless is None else valueless
    dropped = [] if dropped is None else dropped
    parsed = _parse(html)
    entries: list[Entry] = []
    for heading, rows in parsed.tables:
        if not _is_rule_table(rows):
            continue
        layers = _layers(heading or parsed.title.rsplit(" - ", 1)[-1])
        microns = any(c.lower() == "microns" for c in rows[0])
        columns, first = _value_columns(rows, microns)
        for row in rows[first:]:
            rule = row[0] if row else ""
            if not RULE_ID.match(rule):
                continue
            if len(row) < 3 + max(i for i, _ in columns):
                valueless.append(f"scmos-{page}.html, rule {rule}: {' '.join(row[1:])}")
                continue
            description = row[1]
            for index, column in columns:
                cell = row[2 + index]
                if cell.lower() == "n/a":
                    continue
                match = VALUE.match(cell)
                if match is None:
                    dropped.append(f"scmos-{page}.html, rule {rule}, column {column}: {cell}")
                    continue
                entries.append(_entry(page, rule, column, description, layers, lambdas,
                                      Decimal(match.group("num")),
                                      exact=match.group("num2") is not None,
                                      microns=microns))
    return entries


def _is_rule_table(rows: list[list[str]]) -> bool:
    return bool(rows) and [c.lower() for c in rows[0][:2]] == ["rule", "description"]


def _value_columns(rows: list[list[str]], microns: bool) -> tuple[list[tuple[int, str]], int]:
    """The value columns `(index after the description, column)` and the first row after
    the header. A lambda table names SCMOS, SUBM, DEEP once per column group; the group
    with the largest metal count is used, else the last."""
    first = 1
    while first < len(rows) and not (rows[first] and RULE_ID.match(rows[first][0])):
        first += 1
    if microns:
        return [(0, "Microns")], first
    header = rows[1:first]
    names = next((r for r in header if r and all(c.lower() in COLUMNS for c in r)), None)
    if names is None or len(names) % len(COLUMNS):
        raise ValueError(f"no SCMOS/SUBM/DEEP header row in a table: {rows[:first]}")
    groups = len(names) // len(COLUMNS)
    counts = next(([GROUP.match(c) for c in r] for r in header
                   if r and all(GROUP.match(c) for c in r)), None)
    group = groups - 1
    if counts is not None and len(counts) == groups:
        numbers = [int(m.group(1)) for m in counts]
        group = numbers.index(max(numbers))
    start = group * len(COLUMNS)
    return [(start + i, names[start + i].upper()) for i in range(len(COLUMNS))], first


def _layers(heading: str) -> list[str]:
    """`Via` → `via1`, `Contact to Poly` → `contact`, `poly`, `Thick Active` →
    `thick_active`; a parenthesised remark and a `for SCMOS_DEEP` clause are dropped."""
    name = re.sub(r"\([^()]*\)", "", HEADING_PREFIX.sub("", heading))
    name = re.split(r"\s+for\s+", name, flags=re.IGNORECASE)[0].strip()
    layers = []
    for word in re.split(r"\s+to\s+|,", name, flags=re.IGNORECASE):
        layer = "_".join(word.lower().split())
        layers.append(LAYER_ALIASES.get(layer, layer))
    return [layer for layer in layers if layer]


def _entry(page: str, rule: str, column: str, description: str, layers: list[str],
           lambdas: dict[str, Decimal], number: Decimal, exact: bool,
           microns: bool) -> Entry:
    kind = _kind(description, "um")
    if exact or "exact" in description.lower():
        kind = "exact-size"
    cite = f"SCMOS rev 8.00, page scmos-{page}.html, rule {rule}, column {column}"
    common = {"source": SOURCE, "rule": rule, "kind": kind, "layers": layers,
              "text": description, "cite": cite}
    if microns:
        return Entry(id=f"{SOURCE}/{rule}", value=number, unit="um", guideline=True,
                     **common)
    key = column.lower()
    lambda_um = lambdas.get(key)
    return Entry(id=f"{SOURCE}/{rule}/{key}", column=key, lambda_=number, lambda_um=lambda_um,
                 value=None if lambda_um is None else number * lambda_um,
                 unit=None if lambda_um is None else "um", **common)


def update_sources(path: Path, digests: dict[str, str], retrieved: str) -> None:
    """Replace the `[sources.scmos8]` tables of `sources.toml` (or append them) with the
    page digests and the retrieval date; the other sources are left as they are."""
    lines = path.read_text(encoding="utf-8").splitlines()
    kept: list[str] = []
    inside = False
    for line in lines:
        header = re.match(r"^\s*\[([^\[\]]+)\]", line)
        if header:
            inside = header.group(1).strip() in (f"sources.{SOURCE}", f"sources.{SOURCE}.sha256")
        if not inside:
            kept.append(line)
    while kept and not kept[-1].strip():
        kept.pop()
    block = [
        "",
        f"[sources.{SOURCE}]",
        f"title = {_toml_string(TITLE)}",
        f"url = {_toml_string(f'{BASE_URL}scmos-{INDEX}.html')}",
        f"licence = {_toml_string(LICENCE)}",
        f"retrieved = {retrieved}",
        "transcribed = true",
        "vendored = false",
        "public = true",
        "",
        f"[sources.{SOURCE}.sha256]",
        *(f"{_toml_string(page)} = {_toml_string(digests[page])}" for page in sorted(digests)),
    ]
    path.write_text("\n".join(kept + block) + "\n", encoding="utf-8")


def fetch(directory: Path) -> dict[str, bytes]:
    """Download every page of `PAGES` into `directory` as `scmos-<page>.html`."""
    directory.mkdir(parents=True, exist_ok=True)
    pages: dict[str, bytes] = {}
    for page in PAGES:
        url = f"{BASE_URL}scmos-{page}.html"
        request = urllib.request.Request(url, headers={"User-Agent": "ws180g-import-scmos"})
        with urllib.request.urlopen(request, timeout=60) as response:
            pages[page] = response.read()
        (directory / f"scmos-{page}.html").write_bytes(pages[page])
        print(f"fetched {url} ({len(pages[page])} bytes)")
    return pages


def _recorded(sources: Path) -> dict[str, str]:
    with sources.open("rb") as f:
        return tomllib.load(f).get("sources", {}).get(SOURCE, {}).get("sha256", {})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dir", type=Path, default=DEFAULT_DIR,
                        help="where the pages are saved (default tmp/scmos8/)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--sources", type=Path, default=DEFAULT_SOURCES)
    parser.add_argument("--offline", action="store_true",
                        help="import the pages already in --dir, checked against the sha256"
                             " recorded in --sources, without fetching")
    args = parser.parse_args()
    if args.offline:
        raw = {page: (args.dir / f"scmos-{page}.html").read_bytes() for page in PAGES}
        recorded = _recorded(args.sources)
        for page, data in raw.items():
            digest = hashlib.sha256(data).hexdigest()
            if recorded.get(page) != digest:
                raise SystemExit(f"scmos-{page}.html: sha256 {digest} is not the one recorded"
                                 f" in {args.sources}")
    else:
        raw = fetch(args.dir)
        update_sources(args.sources, {p: hashlib.sha256(d).hexdigest() for p, d in raw.items()},
                       date.today().isoformat())
    import_scmos({page: data.decode("utf-8") for page, data in raw.items()}, args.out)


if __name__ == "__main__":
    main()
