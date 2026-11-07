# SPDX-License-Identifier: Apache-2.0
"""Load the process description from its TOML files into a `Process`.

Every file's problems are collected and raised together as one `ProcessError`, one line per
problem in the form `<file>: <key>: <message>`.
"""

import tomllib
from decimal import Decimal
from pathlib import Path

from pydantic import ValidationError

from ws180g_process.model import Process
from ws180g_process.ranges import on_grid

DEFAULT_DATA = Path(__file__).resolve().parents[2] / "data" / "ws180g"

# The database unit in um; every grid is a whole multiple of it.
DATABASE_UNIT = Decimal("0.001")

# Which file holds each top-level key of `Process`.
KEY_FILE = {
    "name": "process.toml",
    "schema": "process.toml",
    "grid": "process.toml",
    "variants": "process.toml",
    "datatypes": "layers.toml",
    "layers": "layers.toml",
    "masks": "masks.toml",
    "stack": "stack.toml",
    "rules": "rules.toml",
}
FILES = list(dict.fromkeys(KEY_FILE.values()))


class ProcessError(ValueError):
    """A problem in the process description, at `key` (a full dotted path) of `file`.

    `errors` holds every problem found in one load; `str()` prints them one per line.
    """

    def __init__(self, file: str, key: str, message: str) -> None:
        super().__init__(file, key, message)
        self.file = file
        self.key = key
        self.message = message
        self.errors: list[ProcessError] = [self]

    def __str__(self) -> str:
        return "\n".join(f"{e.file}: {e.key}: {e.message}" for e in self.errors)

    @classmethod
    def collected(cls, errors: list["ProcessError"]) -> "ProcessError":
        first = cls(errors[0].file, errors[0].key, errors[0].message)
        first.errors = list(errors)
        return first


def load_process(data_dir: Path = DEFAULT_DATA) -> Process:
    data, origin, errors = _read(data_dir)
    if errors:
        raise ProcessError.collected(errors)
    try:
        process = Process.model_validate(data)
    except ValidationError as exc:
        raise ProcessError.collected(_from_validation(exc, origin)) from None
    errors = _check(process)
    if errors:
        raise ProcessError.collected(errors)
    return process


def _read(data_dir: Path) -> tuple[dict, dict[str, str], list[ProcessError]]:
    """Merge the files' top-level tables; record which file each key came from."""
    data: dict = {}
    origin: dict[str, str] = {}
    errors: list[ProcessError] = []
    for file in FILES:
        try:
            with (data_dir / file).open("rb") as f:
                # parse_float=Decimal keeps the literal exact (0.435 stays 0.435).
                table = tomllib.load(f, parse_float=Decimal)
        except FileNotFoundError:
            errors.append(ProcessError(file, "(file)", f"not found in {data_dir}"))
            continue
        except tomllib.TOMLDecodeError as exc:
            errors.append(ProcessError(file, "(toml)", str(exc)))
            continue
        for key, value in table.items():
            if key in origin:
                errors.append(ProcessError(file, key, f"already defined in {origin[key]}"))
            elif KEY_FILE.get(key, file) != file:
                errors.append(ProcessError(file, key, f"belongs in {KEY_FILE[key]}"))
            else:
                data[key] = value
                origin[key] = file
    return data, origin, errors


def _from_validation(exc: ValidationError, origin: dict[str, str]) -> list[ProcessError]:
    errors = []
    for e in exc.errors():
        top = str(e["loc"][0])
        file = origin.get(top) or KEY_FILE.get(top, "process.toml")
        key = ".".join(str(part) for part in e["loc"])
        errors.append(ProcessError(file, key, e["msg"]))
    return errors


def _check(process: Process) -> list[ProcessError]:
    """Checks that span several keys; each is reported at the key that is wrong."""
    errors: list[ProcessError] = []

    grid = process.grid
    if grid.unit != "um":
        errors.append(ProcessError("process.toml", "grid.unit", f"must be um, got {grid.unit}"))
    if grid.value is None or grid.value <= 0 or not on_grid(grid.value, DATABASE_UNIT):
        errors.append(ProcessError(
            "process.toml", "grid.value",
            f"grid {grid.value} um is not a positive multiple of the {DATABASE_UNIT} um "
            "database unit"))

    for name, variant in process.variants.items():
        for inner in variant.contains:
            if inner not in process.variants:
                errors.append(ProcessError(
                    "process.toml", f"variants.{name}.contains", f"unknown variant {inner}"))
            elif not set(process.variants[inner].oxides) <= set(variant.oxides):
                errors.append(ProcessError(
                    "process.toml", f"variants.{name}.contains",
                    f"{inner} has oxides that {name} lacks"))

    seen: dict[tuple[int, int], str] = {}
    for name, layer in process.layers.items():
        if layer.variant is not None and layer.variant not in process.variants:
            errors.append(ProcessError(
                "layers.toml", f"layers.{name}.variant", f"unknown variant {layer.variant}"))
        if layer.gds[1] != process.datatypes.drawing:
            errors.append(ProcessError(
                "layers.toml", f"layers.{name}.gds",
                f"datatype must be the drawing datatype {process.datatypes.drawing}"))
        if layer.gds in seen:
            errors.append(ProcessError(
                "layers.toml", f"layers.{name}.gds", f"{layer.gds} is also {seen[layer.gds]}"))
        seen[layer.gds] = name
    return errors
