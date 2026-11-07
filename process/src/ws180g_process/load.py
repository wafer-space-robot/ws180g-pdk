# SPDX-License-Identifier: Apache-2.0
"""Load the process description from its TOML files into a `Process`.

Every file's problems are collected and raised together as one `ProcessError`, one line per
problem in the form `<file>: <key>: <message>`.
"""

import re
import tomllib
from decimal import Decimal
from pathlib import Path
from typing import get_args, get_origin

from pydantic import BaseModel, TypeAdapter, ValidationError

from ws180g_process.model import Datatypes, Layer, Mask, Process, RuleField, Variant
from ws180g_process.ranges import on_grid

DEFAULT_DATA = Path(__file__).resolve().parents[2] / "data" / "ws180g"

# The database unit in um; every grid is a whole multiple of it.
DATABASE_UNIT = Decimal("0.001")

# Areas (um2) are rounded up to a multiple of this.
AREA_STEP = Decimal("0.005")

# The margin floors (spec 3.6) and the standard ratios a margin may take without a
# `margin_reason`: 1.2, 1.5 for a single source, 1.25 for a x0.8 maximum.
MARGIN_FLOOR = Decimal("1.2")
MAXIMUM_FLOOR = Decimal("1.25")
STANDARD_MARGINS = {
    Decimal("1.2"): "the 20 % rule",
    Decimal("1.5"): "the single-source rule",
    Decimal("1.25"): "the x0.8 maximum rule",
}

# Splits a layer expression into names once `.sized(<field path>)` calls are dropped.
_SIZED = re.compile(r"\.sized\([^()]*\)")
_OPERATORS = re.compile(r"[|&\-()\s]+")

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
    "aliases": "rules.toml",
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
    base = {n for n, v in raw_variants.items()
            if isinstance(v, dict) and v.get("contains") == []} if known else set()
    errors += _check_masks(
        valid.get("masks", []), layer_names, valid.get("layers", {}), known, base)
    raw_stack = data.get("stack")
    raw_stack = raw_stack if isinstance(raw_stack, dict) else {}
    errors += _check_litho(_table(raw_stack, "litho"), layer_names, valid.get("masks", []))
    rules = valid.get("rules", {})
    rule_names = set(rules) if "rules" in valid else None
    errors += _check_stack_paths(raw_stack, rule_names)
    errors += _check_stack_margins(raw_stack)
    modules = {layer.module for layer in valid.get("layers", {}).values() if layer.module}
    names = layer_names | set(valid.get("aliases", {}))
    errors += _check_aliases(valid.get("aliases", {}), names)
    grid = data.get("grid", {}).get("value") if isinstance(data.get("grid"), dict) else None
    errors += _check_rules(rules, names, known, modules,
                           grid if _is_number(grid) and grid > 0 else None)
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
    masks: list[Mask | None], layer_names: set[str], layers: dict[str, Layer], known: set[str],
    base: set[str],
) -> list[ProcessError]:
    """Each mask is a layer of the layer map, listed once, drawn exactly when its layer is,
    names a known variant, and has its layer's module and variant (a mask of a layer that
    first appears in a base variant, one that contains no other, names no variant)."""
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
        if layer is None:
            continue
        if mask.module != layer.module:
            errors.append(ProcessError(
                "masks.toml", f"{key}.module",
                f"{mask.name}: mask module {mask.module} differs from layer module "
                f"{layer.module}"))
        expected = None if layer.variant in base else layer.variant
        if mask.variant != expected:
            errors.append(ProcessError(
                "masks.toml", f"{key}.variant",
                f"{mask.name}: mask variant {mask.variant} differs from {expected} (layer "
                f"variant {layer.variant})"))
    return errors


def _table(table: dict, key: str) -> dict:
    """`table[key]` when it is a table, else an empty one (its schema error is reported)."""
    value = table.get(key)
    return value if isinstance(value, dict) else {}


def _check_litho(
    litho: dict, layer_names: set[str], masks: list[Mask | None]
) -> list[ProcessError]:
    """Each litho entry is a layer, and every baseline drawn mask has one."""
    errors = [ProcessError("stack.toml", f"stack.litho.{name}", "not a layer")
              for name in litho if name not in layer_names]
    for mask in masks:
        if mask is not None and mask.baseline and mask.drawn and mask.name not in litho:
            errors.append(ProcessError(
                "stack.toml", "stack.litho", f"no entry for baseline drawn mask {mask.name}"))
    return errors


def _rule_path_error(path: object, rule_names: set[str]) -> str | None:
    """Why `path` is not the full dotted path of a rule, or None when it is one."""
    if not isinstance(path, str) or not path.startswith("rules."):
        return f"{path!r} is not a rules.<id> field path"
    if path.removeprefix("rules.") not in rule_names:
        return f"{path} names no rule"
    return None


def _check_stack_paths(stack: dict, rule_names: set[str] | None) -> list[ProcessError]:
    """`stack.litho.*.min_feature/min_space` and `stack.oxides.*.lmin_n/lmin_p` name rules.
    Skipped when the rules failed to load (their errors are reported)."""
    if rule_names is None:
        return []
    errors = []
    for table, keys in (("litho", ("min_feature", "min_space")),
                        ("oxides", ("lmin_n", "lmin_p"))):
        for name, entry in _table(stack, table).items():
            if not isinstance(entry, dict):
                continue
            for key in keys:
                if key in entry and (why := _rule_path_error(entry[key], rule_names)):
                    errors.append(ProcessError(
                        "stack.toml", f"stack.{table}.{name}.{key}", why))
    return errors


def _margin_error(margin: object, reason: object, floor: Decimal) -> str | None:
    """Why a field's `margin` is not acceptable, or None. The margin is at least `floor`; a
    margin other than a standard ratio needs a `margin_reason`."""
    if not _is_number(margin):
        return None  # absent, or a schema error
    if margin < floor:
        return f"margin {margin} is below the floor {floor} (spec 3.6)"
    if Decimal(margin) not in STANDARD_MARGINS and not (isinstance(reason, str) and reason):
        return (f"margin {margin} is none of the standard ratios "
                f"({', '.join(f'{k} {v}' for k, v in STANDARD_MARGINS.items())}) "
                "and has no margin_reason")
    return None


def _check_stack_margins(stack: dict) -> list[ProcessError]:
    """The margin rules on the range fields of oxides and metals."""
    errors = []
    for table, keys in (("oxides", ("thickness", "vt_n", "vt_p")),
                        ("metals", ("thickness", "sheet_rho"))):
        for name, entry in _table(stack, table).items():
            if not isinstance(entry, dict):
                continue
            for key in keys:
                field = entry.get(key)
                if isinstance(field, dict) and (why := _margin_error(
                        field.get("margin"), field.get("margin_reason"), MARGIN_FLOOR)):
                    errors.append(ProcessError(
                        "stack.toml", f"stack.{table}.{name}.{key}.margin", why))
    return errors


def _expression_names(expr: str) -> set[str]:
    """The bare layer names and aliases in a layer expression; the field path of a
    `.sized(<field path>)` call is dropped, the argument of `.unrelated(<expr>)` kept."""
    expr = _SIZED.sub("", expr).replace(".unrelated(", "|(")
    return {name for name in _OPERATORS.split(expr) if name}


def _check_aliases(aliases: dict[str, str], names: set[str]) -> list[ProcessError]:
    errors = []
    for alias, expr in aliases.items():
        if unknown := sorted(_expression_names(expr) - names):
            errors.append(ProcessError(
                "rules.toml", f"aliases.{alias}", f"unknown layer {', '.join(unknown)}"))
    return errors


def _check_rules(
    rules: dict[str, RuleField], names: set[str], known: set[str], modules: set[str],
    grid: Decimal | None,
) -> list[ProcessError]:
    """Cross-checks of each rule: known layers, variant and module; field paths that resolve;
    lengths on the grid and areas on the area step; the margin floors and standard ratios;
    a fixture for every topology rule."""
    errors = []

    def error(rid: str, key: str, message: str) -> None:
        errors.append(ProcessError("rules.toml", f"rules.{rid}.{key}", message))

    for rid, rule in rules.items():
        for expr in rule.layers:
            if unknown := sorted(_expression_names(expr) - names):
                error(rid, "layers", f"unknown layer {', '.join(unknown)} in {expr!r}")
        if rule.edge_layer is not None and rule.edge_layer not in names:
            error(rid, "edge_layer", f"unknown layer {rule.edge_layer}")
        if known and rule.variant not in known:
            error(rid, "variant", f"unknown variant {rule.variant}")
        if rule.module is not None and rule.module not in modules:
            error(rid, "module", f"unknown module {rule.module}")
        if rule.implied_by is not None and (why := _rule_path_error(rule.implied_by, set(rules))):
            error(rid, "implied_by", why)
        for path in rule.composed_of:
            if "/" not in path and (why := _rule_path_error(path, set(rules))):
                error(rid, "composed_of", why)  # an id with "/" is an evidence entry
        if rule.unit == "um" and grid is not None and not on_grid(rule.value, grid):
            error(rid, "value", f"{rule.value} um is not on the {grid} um grid")
        if rule.unit == "um2" and not on_grid(rule.value, AREA_STEP):
            error(rid, "value", f"{rule.value} um2 is not a multiple of {AREA_STEP} um2")
        floor = MAXIMUM_FLOOR if rule.kind == "max-distance" else MARGIN_FLOOR
        if why := _margin_error(rule.margin, rule.margin_reason, floor):
            error(rid, "margin", why)
        if rule.kind == "topology" and not rule.fixture:
            error(rid, "fixture", "missing: a topology rule names its fixture")
    return errors
