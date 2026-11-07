# SPDX-License-Identifier: Apache-2.0
"""Naming rules for libraries, cells, corners and devices, and a tree checker.

Grammar: spec section 6 and the naming document. Each name class has one
compiled regular expression with named groups and one parser.

Tree conventions: the stem of a file in a built `libs.ref/<library>/<view>/`
tree is `<name>.split(".")[0]` and is checked as the cell part of
`<library>__<stem>`. Per-corner liberty files are named
`<library>__<cell>__<corner>.lib`."""

import argparse
import re
import sys
from decimal import Decimal
from functools import cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict
from ws180g_process.load import load_process

SOURCES = ("fd", "osu")
TYPES = ("pr", "sc", "io", "bd", "xx", "ip")


class NamingError(ValueError):
    """A name that does not follow the naming rules."""

    def __init__(self, name: str, reason: str) -> None:
        super().__init__(f"{name}: {reason}")
        self.name = name
        self.reason = reason


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LibraryName(_Frozen):
    process: str
    source: str
    type: str
    name: str | None


class CellName(_Frozen):
    library: str
    cell: str
    size: str | None


class Corner(_Frozen):
    type: str
    temp_c: int
    voltage: Decimal
    flags: list[str]


class Device(_Frozen):
    prefixes: list[str]
    kind: str
    voltage: Decimal | None
    properties: list[str]


_LIBRARY_TAIL = (
    rf"_(?P<source>{'|'.join(SOURCES)})_(?P<type>{'|'.join(TYPES)})"
    r"(?:_(?P<name>(?!\d)[a-z0-9]+))?"
)


@cache
def _library_re() -> re.Pattern[str]:
    processes = "|".join(re.escape(v) for v in sorted(load_process().variants))
    return re.compile(rf"(?P<process>{processes}){_LIBRARY_TAIL}")


_CELL_RE = re.compile(r"(?P<cell>[a-z0-9]+)(?:_(?P<size>[a-z0-9]+))?")
_CORNER_RE = re.compile(
    r"(?P<type>tt|ss|ff|sf|fs)_(?P<temp>n?\d{2,3})C_(?P<v>\d)v(?P<vf>\d{2})"
    r"(?P<flags>(?:_[a-z0-9]+)*)"
)
_FET_RE = re.compile(
    r"(?P<prefixes>(?:esd_|rf_)*)"
    r"(?P<kind>nfet|pfet|npn|pnp|diode_[a-z]+2[a-z]+)"
    r"_(?P<v>\d{2})v(?P<vf>\d)(?P<props>(?:_[a-z0-9]+)*)"
)
_PASSIVE_RE = re.compile(
    r"(?P<kind>(?:res|cap)_[a-z]+_[a-z0-9]+)(?:_(?P<v>\d{2})v(?P<vf>\d))?"
)


def parse_library(name: str) -> LibraryName:
    match = _library_re().fullmatch(name)
    if not match:
        raise NamingError(
            name,
            "not <process>_<source>_<type>[_<name>] with a known process, source "
            "and type, and a name without underscore or leading digit",
        )
    return LibraryName(**match.groupdict())


def parse_cell(name: str) -> CellName:
    library, sep, rest = name.partition("__")
    if not sep:
        raise NamingError(name, "not <library>__<cell>[_<size>]")
    try:
        parse_library(library)
    except NamingError as err:
        raise NamingError(name, f"bad library part: {err.reason}") from None
    match = _CELL_RE.fullmatch(rest)
    if not match:
        raise NamingError(name, "cell part is not <cell>[_<size>] of lower-case alphanumerics")
    return CellName(library=library, **match.groupdict())


def parse_corner(name: str) -> Corner:
    match = _CORNER_RE.fullmatch(name)
    if not match:
        raise NamingError(name, "not <tt|ss|ff|sf|fs>_<temp>C_<d>v<dd>[_<flag>]")
    temp = match["temp"]
    temp_c = -int(temp[1:]) if temp.startswith("n") else int(temp)
    return Corner(
        type=match["type"],
        temp_c=temp_c,
        voltage=Decimal(f"{match['v']}.{match['vf']}"),
        flags=[f for f in match["flags"].split("_") if f],
    )


def parse_device(name: str) -> Device:
    match = _FET_RE.fullmatch(name)
    if match:
        return Device(
            prefixes=[p for p in match["prefixes"].split("_") if p],
            kind=match["kind"],
            voltage=Decimal(f"{match['v']}.{match['vf']}"),
            properties=[p for p in match["props"].split("_") if p],
        )
    match = _PASSIVE_RE.fullmatch(name)
    if match:
        voltage = Decimal(f"{match['v']}.{match['vf']}") if match["v"] else None
        return Device(prefixes=[], kind=match["kind"], voltage=voltage, properties=[])
    raise NamingError(
        name,
        "not [esd_][rf_]<nfet|pfet|npn|pnp|diode_a2c>_<dd>v<d>[_<prop>] "
        "or <res|cap>_<kind>_<layer>[_<dd>v<d>]",
    )


def _problem(path: Path, root: Path, parse, name: str, *args) -> list[str]:
    try:
        parse(name, *args)
    except NamingError as err:
        return [f"{path.relative_to(root)}: {err.reason}"]
    return []


def _check_files(library_dir: Path, root: Path) -> list[str]:
    """Names of every `<library>__<cell>__<corner>.*` file under a library.

    The library part must be the enclosing library directory, the cell part a
    valid cell, the corner part a valid corner."""
    errors: list[str] = []
    for path in sorted(library_dir.rglob("*")):
        if not path.is_file():
            continue
        parts = path.name.split(".")[0].split("__")
        if len(parts) != 3:
            continue
        library, cell, corner = parts
        found = _problem(path, root, parse_cell, f"{library}__{cell}")
        found += _problem(path, root, parse_corner, corner)
        if not found and library != library_dir.name:
            found = [f"{path.relative_to(root)}: library part is not {library_dir.name}"]
        errors += found
    return errors


def check_tree(root: Path) -> list[str]:
    """Errors (`<path>: <reason>`) in the library trees under `root`; empty when clean."""
    errors: list[str] = []
    libraries = root / "libraries"
    if libraries.is_dir():
        for lib in sorted(p for p in libraries.iterdir() if p.is_dir() and not p.name.startswith(".")):
            errors += _problem(lib, root, parse_library, lib.name)
            cells = lib / "cells"
            if cells.is_dir():
                for cell in sorted(
                    p for p in cells.iterdir() if p.is_dir() and not p.name.startswith(".")
                ):
                    found = _problem(cell, root, parse_cell, cell.name)
                    errors += found
                    if not found and not cell.name.startswith(f"{lib.name}__"):
                        errors.append(f"{cell.relative_to(root)}: does not start with {lib.name}__")
            errors += _check_files(lib, root)
    release = root / "libs.ref"
    if release.is_dir():
        for lib in sorted(p for p in release.iterdir() if p.is_dir() and not p.name.startswith(".")):
            errors += _problem(lib, root, parse_library, lib.name)
            for path in sorted(p for p in lib.glob("*/*") if p.is_file() and not p.name.startswith(".")):
                errors += _problem(path, root, parse_cell, f"{lib.name}__{path.name.split('.')[0]}")
            errors += _check_files(lib, root)
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ws180g-check-names", description=__doc__)
    default = Path(__file__).resolve().parents[3]
    parser.add_argument("root", nargs="?", type=Path, default=default)
    args = parser.parse_args(argv)
    errors = check_tree(args.root)
    for error in errors:
        print(error)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
