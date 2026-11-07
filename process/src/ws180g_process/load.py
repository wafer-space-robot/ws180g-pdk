# SPDX-License-Identifier: Apache-2.0
"""Load the process description from its TOML files into a `Process`.

Every file's problems are collected and raised together as one `ProcessError`, one line per
problem in the form `<file>: <key>: <message>`.
"""

import tomllib
from decimal import Decimal
from pathlib import Path
from typing import get_args, get_origin

from pydantic import TypeAdapter, ValidationError

from ws180g_process.model import Datatypes, Layer, Process, Variant
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
    """Load and check the process; on any problem raise one `ProcessError` listing them all.

    Each file is read and each key validated independently, and the cross-key checks run on
    whatever validated, so one broken file or key never hides the problems of another.
    """
    data, origin, read_files, errors = _read(data_dir)
    valid, schema_errors = _validate_keys(data, origin, read_files)
    errors += schema_errors
    errors += _check_grid(data.get("grid"))
    raw_variants = data.get("variants")
    known = set(raw_variants) if isinstance(raw_variants, dict) else set()
    errors += _check_variants(valid.get("variants", {}), known)
    errors += _check_layers(valid.get("layers", {}), known, valid.get("datatypes"))
    if errors:
        errors.sort(key=lambda e: FILES.index(e.file) if e.file in FILES else len(FILES))
        raise ProcessError.collected(errors)
    try:
        return Process.model_validate(data)
    except ValidationError as exc:  # a model-level rule the per-key checks do not cover
        raise ProcessError.collected(_from_validation(exc, origin)) from None


def _read(data_dir: Path) -> tuple[dict, dict[str, str], set[str], list[ProcessError]]:
    """Merge the files' top-level tables; record which file each key came from."""
    data: dict = {}
    origin: dict[str, str] = {}
    read_files: set[str] = set()
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
        read_files.add(file)
        for key, value in table.items():
            if key in origin:
                errors.append(ProcessError(file, key, f"already defined in {origin[key]}"))
            elif key not in KEY_FILE:
                errors.append(ProcessError(file, key, "unknown key"))
            elif KEY_FILE[key] != file:
                errors.append(ProcessError(file, key, f"belongs in {KEY_FILE[key]}"))
            else:
                data[key] = value
                origin[key] = file
    return data, origin, read_files, errors


def _validate_keys(
    data: dict, origin: dict[str, str], read_files: set[str]
) -> tuple[dict, list[ProcessError]]:
    """Validate each top-level key on its own, and each entry of a table of entries on its
    own; return what validated and every error."""
    valid: dict = {}
    errors: list[ProcessError] = []
    for name, info in Process.model_fields.items():
        key = info.alias or name
        file = KEY_FILE[key]
        if key not in data:
            if file in read_files and info.is_required():
                errors.append(ProcessError(file, key, "missing"))
            continue
        if get_origin(info.annotation) is dict and isinstance(data[key], dict):
            entry_type = get_args(info.annotation)[1]
            entries = {}
            for entry, value in data[key].items():
                try:
                    entries[entry] = TypeAdapter(entry_type).validate_python(value)
                except ValidationError as exc:
                    errors += _from_validation(exc, origin, prefix=(key, entry))
            valid[name] = entries
            continue
        try:
            adapter = TypeAdapter(info.annotation)
            valid[name] = adapter.validate_python(data[key])
        except ValidationError as exc:
            errors += _from_validation(exc, origin, prefix=(key,))
    return valid, errors


def _from_validation(
    exc: ValidationError, origin: dict[str, str], prefix: tuple = ()
) -> list[ProcessError]:
    errors = []
    for e in exc.errors():
        loc = prefix + tuple(e["loc"])
        top = str(loc[0])
        file = origin.get(top) or KEY_FILE.get(top, "process.toml")
        errors.append(ProcessError(file, ".".join(str(part) for part in loc), e["msg"]))
    return errors


def _check_grid(grid: object) -> list[ProcessError]:
    """Unit and database-unit checks on the raw grid table, independent of its schema errors.
    A value of the wrong type is left to the schema error."""
    if not isinstance(grid, dict):
        return []
    errors = []
    unit = grid.get("unit")
    if isinstance(unit, str) and unit != "um":
        errors.append(ProcessError("process.toml", "grid.unit", f"must be um, got {unit}"))
    value = grid.get("value")
    if value is None:
        errors.append(ProcessError("process.toml", "grid.value", "missing"))
    elif _is_number(value) and (value <= 0 or not on_grid(Decimal(value), DATABASE_UNIT)):
        errors.append(ProcessError(
            "process.toml", "grid.value",
            f"grid {value} um is not a positive multiple of the {DATABASE_UNIT} um "
            "database unit"))
    return errors


def _is_number(value: object) -> bool:
    return isinstance(value, (Decimal, int)) and not isinstance(value, bool)


def _check_variants(variants: dict[str, Variant], known: set[str]) -> list[ProcessError]:
    errors = []
    for name, variant in variants.items():
        for inner in variant.contains:
            if inner not in known:
                errors.append(ProcessError(
                    "process.toml", f"variants.{name}.contains", f"unknown variant {inner}"))
            elif inner in variants and not set(variants[inner].oxides) <= set(variant.oxides):
                errors.append(ProcessError(
                    "process.toml", f"variants.{name}.contains",
                    f"{inner} has oxides that {name} lacks"))
    return errors


def _check_layers(
    layers: dict[str, Layer], known: set[str], datatypes: Datatypes | None
) -> list[ProcessError]:
    errors = []
    seen: dict[tuple[int, int], str] = {}
    for name, layer in layers.items():
        if layer.variant is not None and layer.variant not in known:
            errors.append(ProcessError(
                "layers.toml", f"layers.{name}.variant", f"unknown variant {layer.variant}"))
        if datatypes is not None and layer.gds[1] != datatypes.drawing:
            errors.append(ProcessError(
                "layers.toml", f"layers.{name}.gds",
                f"datatype must be the drawing datatype {datatypes.drawing}"))
        if layer.gds in seen:
            errors.append(ProcessError(
                "layers.toml", f"layers.{name}.gds", f"{layer.gds} is also {seen[layer.gds]}"))
        seen[layer.gds] = name
    return errors
