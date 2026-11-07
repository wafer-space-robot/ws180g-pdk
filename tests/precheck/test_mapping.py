# SPDX-License-Identifier: Apache-2.0
"""The GF180MCU mapping file (Task 18): it loads, covers ws180g005, and cites its sources."""

import csv
from pathlib import Path

import pytest
from pydantic import ValidationError
from ws180g_precheck.mapping import DEFAULT_MAPPING, Mapping, load_mapping, mapping_path

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def mapping() -> Mapping:
    return load_mapping(DEFAULT_MAPPING)


def _layers_of(process, variant: str) -> set[str]:
    """The drawn and generated layers of `variant` (and of the optional modules); markers of
    other variants (the 3.3 V and 1.8 V oxide markers) are excluded."""
    return {n for n, layer in process.layers.items()
            if layer.variant == variant or layer.module is not None}


def test_identity(mapping):
    assert (mapping.target, mapping.variant, mapping.metal_level) == ("gf180mcu", "gf180mcuD",
                                                                     "5LM")
    assert mapping.path == DEFAULT_MAPPING
    assert mapping_path("gf180mcu") == DEFAULT_MAPPING


def test_covers_ws180g005(mapping, process):
    layers = _layers_of(process, "ws180g005")
    assert {"ox_3v3", "ox_1v8"}.isdisjoint(layers)
    assert set(mapping.drop) == {"gate", "ntap", "ptap"}
    assert layers - set(mapping.drop) == set(mapping.layer_map)


def test_two_targets(mapping):
    assert [t.gds for t in mapping.layer_map["mk_nofill"].to] == [(111, 5), (152, 5)]
    assert [t.gds for t in mapping.layer_map["mk_bjt"].to] == [(118, 5), (127, 5)]
    assert mapping.layer_map["nd"].to == mapping.layer_map["pd"].to
    assert mapping.layer_map["mtop"].to[0].gds == (81, 0)


def _drawn_rows() -> dict[str, tuple[int, int]]:
    """Layer name -> (GDS, datatype) of the GF drawn-layer table, names without notes."""
    path = REPO / "evidence" / "sources" / "gf180mcu-drm" / "06_Drawn_layer10.csv"
    with path.open(encoding="utf-8") as f:
        rows = list(csv.reader(f))[1:]
    return {r[1].split("(")[0].strip(): (int(r[3]), int(r[4])) for r in rows if len(r) >= 5}


def test_every_target_is_in_the_drawn_layer_table(mapping):
    rows = _drawn_rows()
    targets = [t for entry in mapping.layer_map.values() for t in entry.to]
    for t in [*targets, *mapping.oxide.layers]:
        assert rows.get(t.name) == t.gds, t


def test_sources_exist(mapping):
    entries = [*mapping.layer_map.values(), *mapping.cut_sizes.values(), mapping.grid]
    for entry in entries:
        for part in entry.source.split(";"):
            assert (REPO / part.strip()).is_file(), entry.source
    for part in mapping.oxide.source.split(";"):
        assert (REPO / part.strip()).is_file(), mapping.oxide.source


def test_cut_sizes_and_grid(mapping):
    assert {k: str(v.size) for k, v in mapping.cut_sizes.items()} == {
        "co": "0.22", "v1": "0.26", "v2": "0.26", "v3": "0.26", "v4": "0.26"}
    assert str(mapping.grid.value) == "0.005"


def test_cut_sizes_match_the_tables(mapping):
    for cut in mapping.cut_sizes.values():
        with (REPO / cut.source).open(encoding="utf-8") as f:
            values = {r[0].strip(): r[2].strip() for r in csv.reader(f) if len(r) >= 3}
        assert values[cut.rule] == str(cut.size), cut


def test_drc_switches(mapping):
    assert mapping.drc.metal_top == ["9K", "11K", "30K"]
    assert mapping.drc.decks == "all,-density,-dummy,-antenna"
    excluded = {d.tag for d in mapping.excluded_decks}
    assert {f"-{t}" for t in excluded} == set(mapping.drc.decks.split(",")[1:])
    assert all(d.reason for d in mapping.excluded_decks)


def test_extra_keys_rejected(tmp):
    bad = tmp / "bad.toml"
    bad.write_text(DEFAULT_MAPPING.read_text(encoding="utf-8") + '\nsurprise = 1\n',
                   encoding="utf-8")
    with pytest.raises(ValidationError):
        load_mapping(bad)
