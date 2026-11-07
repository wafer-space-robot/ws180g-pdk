# SPDX-License-Identifier: Apache-2.0
"""The retarget mapping of a target process: layer numbers, cut sizes, grid, oxide, DRC deck.

A mapping is a TOML file in `precheck/data/<name>.toml` (`gf180mcu.toml` for GF180MCU). Every
item records the public file it was read from in its `source`. `load_mapping(path)` validates
it strictly (`extra="forbid"`): a misspelt key is an error, not a silent default.
"""

import tomllib
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel, ConfigDict, PrivateAttr

DATA = Path(__file__).resolve().parents[2] / "data"
DEFAULT_MAPPING = DATA / "gf180mcu.toml"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Target(Strict):
    """One target layer: GDS layer/datatype and its name in the target's tables."""

    gds: tuple[int, int]
    name: str


class LayerMapEntry(Strict):
    """The target layers one generic layer is copied to (one or more)."""

    to: list[Target]
    source: str
    note: str = ""


class CutSize(Strict):
    """The exact size of a cut layer on the target, and the rule that sets it."""

    size: Decimal
    rule: str
    source: str


class Grid(Strict):
    value: Decimal
    rule: str
    source: str


class Oxide(Strict):
    """Whole-design oxide layers: one box each, the drawn bounding box sized by `margin`."""

    layers: list[Target]
    margin: Decimal
    rules: list[str]
    source: str


class Drc(Strict):
    """The target's public DRC deck (a container path) and the switches it is run with."""

    deck: str
    decks: str
    run_mode: str
    workers: int
    metal_top: list[str]
    source: str


class ExcludedDeck(Strict):
    file: str
    tag: str
    reason: str
    source: str


class Mapping(Strict):
    """A whole mapping file; `path` is the file it was loaded from."""

    target: str
    variant: str
    metal_level: str
    source: str
    drop: list[str]
    drop_reason: str
    layer_map: dict[str, LayerMapEntry]
    cut_sizes: dict[str, CutSize]
    grid: Grid
    oxide: Oxide
    drc: Drc
    excluded_decks: list[ExcludedDeck]

    _path: Path | None = PrivateAttr(default=None)

    @property
    def path(self) -> Path | None:
        return self._path


def mapping_path(name_or_path: str | Path) -> Path:
    """A mapping name (`gf180mcu`) is `precheck/data/<name>.toml`; anything else is a path."""
    text = str(name_or_path)
    if "/" not in text and not text.endswith(".toml"):
        return DATA / f"{text}.toml"
    return Path(name_or_path)


def load_mapping(path: str | Path = DEFAULT_MAPPING) -> Mapping:
    """Read and validate the mapping file `path` (or a mapping name)."""
    path = mapping_path(path)
    with path.open("rb") as f:
        data = tomllib.load(f, parse_float=Decimal)
    mapping = Mapping.model_validate(data)
    mapping._path = path
    return mapping
