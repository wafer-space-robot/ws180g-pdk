# SPDX-License-Identifier: Apache-2.0
"""Load the process description from its TOML files into a `Process`.

Every file's problems are collected and raised together as one `ProcessError`, one line per
problem in the form `<file>: <key>: <message>`.
"""

import tomllib
from decimal import Decimal
from pathlib import Path
from typing import get_args, get_origin

from pydantic import BaseModel, TypeAdapter, ValidationError

from ws180g_process.model import Datatypes, Layer, Mask, Process, Variant
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
    raw_layers = data.get("layers")
    layer_names = set(raw_layers) if isinstance(raw_layers, dict) else set()
    errors += _check_masks(valid.get("masks", []), layer_names, valid.get("layers", {}), known)
    errors += _check_litho(valid.get("stack", {}).get("litho", {}), layer_names)
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
        result, key_errors = _validate(info.annotation, data[key], (key,), origin)
        errors += key_errors
        if result is not None:  # None: the value failed as a whole
            valid[name] = result
    return valid, errors


def _validate(
    annotation, value, loc: tuple, origin: dict[str, str]
) -> tuple[object, list[ProcessError]]:
    """Validate `value` against `annotation`, splitting it where it is a collection of
    entries so that each entry is checked on its own: a `dict[str, X]` table entry by entry,
    a `list[X]` item by item (an item that fails is `None` in the result), and a table of
    such tables (`Stack`) field by field. Return what validated (`None` when the value
    failed as a whole) and every error."""
    errors: list[ProcessError] = []
    container = get_origin(annotation)
    if container is dict and isinstance(value, dict):
        entry_type = get_args(annotation)[1]
        entries = {}
        for entry, item in value.items():
            result, item_errors = _validate(entry_type, item, loc + (entry,), origin)
            errors += item_errors
            if not item_errors:
                entries[entry] = result
        return entries, errors
    if container is list and isinstance(value, list):
        item_type = get_args(annotation)[0]
        items = []
        for index, item in enumerate(value):
            result, item_errors = _validate(item_type, item, loc + (index,), origin)
            errors += item_errors
            items.append(None if item_errors else result)
        return items, errors
    if _is_table_of_tables(annotation) and isinstance(value, dict):
        fields = {}
        file = origin.get(str(loc[0])) or KEY_FILE.get(str(loc[0]), "process.toml")
        dotted = ".".join(str(part) for part in loc)
        for extra in (k for k in value if k not in annotation.model_fields):
            errors.append(ProcessError(file, f"{dotted}.{extra}", "unknown key"))
        for field, info in annotation.model_fields.items():
            if field not in value:
                if info.is_required():
                    errors.append(ProcessError(file, f"{dotted}.{field}", "missing"))
                continue
            result, field_errors = _validate(
                info.annotation, value[field], loc + (field,), origin)
            errors += field_errors
            if result is not None:
                fields[field] = result
        return fields, errors
    try:
        return TypeAdapter(annotation).validate_python(value), errors
    except ValidationError as exc:
        return None, _from_validation(exc, origin, prefix=loc)


def _is_table_of_tables(annotation: object) -> bool:
    """A model whose every field is a `dict[str, X]` table and that has no model-level rule,
    so validating it field by field loses nothing."""
    return (
        isinstance(annotation, type) and issubclass(annotation, BaseModel)
        and not annotation.__pydantic_decorators__.model_validators
        and all(get_origin(f.annotation) is dict for f in annotation.model_fields.values()))


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
    """A finite Decimal or a non-bool int; NaN and infinity are left to the schema error."""
    if isinstance(value, Decimal):
        return value.is_finite()
    return isinstance(value, int) and not isinstance(value, bool)


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


def _check_masks(
    masks: list[Mask | None], layer_names: set[str], layers: dict[str, Layer], known: set[str]
) -> list[ProcessError]:
    """Each mask is a layer of the layer map, listed once, drawn exactly when its layer is,
    and names a known variant."""
    errors = []
    seen: dict[str, int] = {}
    for index, mask in enumerate(masks):
        if mask is None:  # its schema error is already reported
            continue
        key = f"masks.{index}"
        if mask.name not in layer_names:
            errors.append(ProcessError("masks.toml", f"{key}.name", f"{mask.name} is not a layer"))
        if mask.name in seen:
            errors.append(ProcessError(
                "masks.toml", f"{key}.name", f"duplicate of masks.{seen[mask.name]} ({mask.name})"))
        seen.setdefault(mask.name, index)
        layer = layers.get(mask.name)
        if layer is not None and mask.drawn != (layer.kind == "drawn"):
            errors.append(ProcessError(
                "masks.toml", f"{key}.drawn", f"{mask.name} is a {layer.kind} layer"))
        if mask.variant is not None and mask.variant not in known:
            errors.append(ProcessError(
                "masks.toml", f"{key}.variant", f"unknown variant {mask.variant}"))
    return errors


def _check_litho(litho: dict, layer_names: set[str]) -> list[ProcessError]:
    return [ProcessError("stack.toml", f"stack.litho.{name}", "not a layer")
            for name in litho if name not in layer_names]
