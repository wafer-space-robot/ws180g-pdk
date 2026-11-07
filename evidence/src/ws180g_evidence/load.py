# SPDX-License-Identifier: Apache-2.0
"""Load the evidence set: `sources.toml` (the source registry) and every other `*.toml` of
the data directory, each a list of `[[entry]]` tables.

Every problem is collected and raised together as one `EvidenceError`, one line per problem
in the form `<file>: <key>: <message>`.
"""

import tomllib
from decimal import Decimal
from pathlib import Path

from pydantic import ValidationError

from ws180g_evidence.model import Entry, Evidence, Source

DEFAULT_DATA = Path(__file__).resolve().parents[2] / "data"
SOURCES = "sources.toml"


class EvidenceError(ValueError):
    """A problem in the evidence set, at `key` of `file`.

    `errors` holds every problem found in one load; `str()` prints them one per line.
    """

    def __init__(self, file: str, key: str, message: str) -> None:
        super().__init__(file, key, message)
        self.file = file
        self.key = key
        self.message = message
        self.errors: list[EvidenceError] = [self]

    def __str__(self) -> str:
        return "\n".join(f"{e.file}: {e.key}: {e.message}" for e in self.errors)

    @classmethod
    def collected(cls, errors: list["EvidenceError"]) -> "EvidenceError":
        first = cls(errors[0].file, errors[0].key, errors[0].message)
        first.errors = list(errors)
        return first


def load_evidence(data_dir: Path = DEFAULT_DATA) -> Evidence:
    """Load and check the evidence set; on any problem raise one `EvidenceError` listing
    them all. An entry must name a registered source and its id must start with
    `<source>/`; ids are unique across all files."""
    errors: list[EvidenceError] = []
    sources = _load_sources(data_dir, errors)
    entries: dict[str, Entry] = {}
    seen: dict[str, str] = {}
    for path in sorted(data_dir.glob("*.toml")):
        if path.name == SOURCES:
            continue
        table = _read(path, errors)
        if table is None:
            continue
        for extra in (k for k in table if k != "entry"):
            errors.append(EvidenceError(path.name, extra, "unknown key"))
        raw = table.get("entry", [])
        if not isinstance(raw, list):
            errors.append(EvidenceError(path.name, "entry", "must be an array of tables"))
            continue
        for index, item in enumerate(raw):
            key = f"entry[{index}]"
            try:
                entry = Entry.model_validate(item)
            except ValidationError as exc:
                errors += _from_validation(exc, path.name, key)
                continue
            if entry.source not in sources:
                errors.append(EvidenceError(
                    path.name, key, f"source '{entry.source}' is not registered in {SOURCES}"))
            if not entry.id.startswith(f"{entry.source}/"):
                errors.append(EvidenceError(
                    path.name, key, f"id {entry.id} does not start with '{entry.source}/'"))
            if entry.id in seen:
                errors.append(EvidenceError(
                    path.name, key, f"duplicate id {entry.id} (first in {seen[entry.id]})"))
                continue
            seen[entry.id] = path.name
            entries[entry.id] = entry
    if errors:
        raise EvidenceError.collected(errors)
    return Evidence(entries=entries, sources=sources)


def _read(path: Path, errors: list[EvidenceError]) -> dict | None:
    try:
        with path.open("rb") as f:
            # parse_float=Decimal keeps the literal exact.
            return tomllib.load(f, parse_float=Decimal)
    except tomllib.TOMLDecodeError as exc:
        errors.append(EvidenceError(path.name, "(toml)", str(exc)))
        return None


def _load_sources(data_dir: Path, errors: list[EvidenceError]) -> dict[str, Source]:
    if not (data_dir / SOURCES).exists():
        errors.append(EvidenceError(SOURCES, "(file)", f"not found in {data_dir}"))
        return {}
    table = _read(data_dir / SOURCES, errors)
    if table is None:
        return {}
    for extra in (k for k in table if k != "sources"):
        errors.append(EvidenceError(SOURCES, extra, "unknown key"))
    sources: dict[str, Source] = {}
    for name, item in table.get("sources", {}).items():
        key = f"sources.{name}"
        if not isinstance(item, dict):
            errors.append(EvidenceError(SOURCES, key, "must be a table"))
            continue
        try:
            sources[name] = Source.model_validate({"id": name} | item)
        except ValidationError as exc:
            errors += _from_validation(exc, SOURCES, key)
    return sources


def _from_validation(exc: ValidationError, file: str, key: str) -> list[EvidenceError]:
    return [EvidenceError(file, ".".join([key, *(str(p) for p in err["loc"])]), err["msg"])
            for err in exc.errors()]
