# SPDX-License-Identifier: Apache-2.0
"""Typed model of the process description. The TOML files are the only source of numbers."""

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, model_validator
from pydantic import Field as PydanticField

from ws180g_process.ranges import Range

Provenance = Literal["design-target", "public-source", "chosen", "derived"]

# A GDS layer or datatype number: a 16-bit unsigned int, never a float, string or bool.
GdsNumber = Annotated[int, PydanticField(strict=True, ge=0, le=65535)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Field(Strict):
    """One process quantity with where it came from.

    `margin` is a ratio >= 1 between the value and the requirement it covers; `margin_reason`
    explains a margin that differs from the report's computed requirement; `margin_achieved` is
    the author's figure, checked by the report; `composed_of` lists the full dotted paths of
    the fields this one is built from.
    """

    value: Decimal | None = None
    range: Range | None = None
    unit: str
    provenance: Provenance
    evidence: list[str] = []
    margin: Decimal | None = PydanticField(default=None, ge=1)
    margin_reason: str = ""
    margin_achieved: Decimal | None = None
    composed_of: list[str] = []
    source: str | None = None
    note: str = ""


class Variant(Strict):
    oxides: list[str]
    contains: list[str]


class Layer(Strict):
    """A GDS layer. Exactly one of `variant` (where it first appears) or `module` is set."""

    gds: tuple[GdsNumber, GdsNumber]
    kind: Literal["drawn", "generated"]
    variant: str | None = None
    module: str | None = None
    purpose: str

    @model_validator(mode="after")
    def _variant_or_module(self) -> "Layer":
        if (self.variant is None) == (self.module is None):
            raise ValueError("set exactly one of variant and module")
        return self


class Datatypes(Strict):
    """GDS datatypes the layer map reserves."""

    drawing: GdsNumber
    label: GdsNumber
    pin: GdsNumber


class Process(Strict):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: str
    schema_version: Literal[1] = PydanticField(alias="schema")
    grid: Field
    variants: dict[str, Variant]
    datatypes: Datatypes
    layers: dict[str, Layer]
    # Placeholders: Task 3 replaces `masks` with `list[Mask]` and `stack` with `Stack`;
    # Task 7 replaces `rules` with `dict[str, RuleField]` and adds `aliases`.
    masks: list = []
    stack: dict = {}
    rules: dict = {}
