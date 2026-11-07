# SPDX-License-Identifier: Apache-2.0
"""Typed model of the evidence set: cited public facts and the sources they come from."""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic import Field as PydanticField

# The rule kinds of the shared vocabulary, plus the kinds only evidence uses.
Kind = Literal[
    "min-width", "gate-length", "min-space", "min-enclosure", "min-extension", "min-area",
    "exact-size", "max-distance", "topology", "generation",
    "max-width", "density-floor", "density-ceiling", "ratio", "grid", "thickness", "other",
]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Entry(Strict):
    """One cited fact. `id` is `<source>/<rule>[/<column>][/<part>]`; `column` names the
    voltage class or pad type of a multi-column table, `part` one of several values in a cell.
    `lambda_` (TOML key `lambda`) is the lambda count of an SCMOS rule, `lambda_um` its value
    in um. A `guideline` entry is informative and never binds a value."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str
    source: str
    rule: str
    column: str | None = None
    part: str | None = None
    kind: Kind
    layers: list[str] = []
    value: Decimal | None = None
    unit: str | None = None
    text: str = ""
    cite: str
    guideline: bool = False
    lambda_: Decimal | None = PydanticField(default=None, alias="lambda")
    lambda_um: Decimal | None = None


class Source(Strict):
    """A public source. `transcribed` is true when entries were taken from it, `vendored`
    when its files are kept under `evidence/sources/<id>/` with their `sha256`."""

    id: str
    title: str
    url: str
    licence: str
    commit: str | None = None
    retrieved: date | None = None
    transcribed: bool
    vendored: bool
    sha256: dict[str, str] = {}
    public: bool = True


class Evidence(Strict):
    entries: dict[str, Entry]
    sources: dict[str, Source]
