# SPDX-License-Identifier: Apache-2.0
from decimal import Decimal

import pytest
from pydantic import ValidationError
from ws180g_process.model import Datatypes, Layer

EXPECTED_GDS = {"nw": (1, 0), "nd": (2, 0), "pd": (3, 0), "po": (4, 0), "co": (5, 0),
                "m1": (11, 0), "v1": (12, 0), "m2": (13, 0), "v2": (14, 0), "m3": (15, 0),
                "v3": (16, 0), "m4": (17, 0), "v4": (18, 0), "mtop": (19, 0), "pad": (20, 0),
                "sab": (21, 0),
                "ox_3v3": (30, 0), "ox_1v8": (31, 0), "dnw": (32, 0), "rhi": (33, 0),
                "mk_res": (40, 0), "mk_cap": (41, 0), "mk_dio": (42, 0), "mk_bjt": (43, 0),
                "mk_esd": (44, 0),
                "mk_nofill": (50, 0), "mk_boundary": (51, 0),
                "nsel": (60, 0), "psel": (61, 0), "gate": (62, 0), "ntap": (63, 0),
                "ptap": (64, 0)}


def test_grid_and_variants(process):
    assert process.grid.value == Decimal("0.005")
    assert process.variants["ws180g135"].contains == ["ws180g005", "ws180g035", "ws180g105"]
    assert process.variants["ws180g005"].oxides == ["5v0"]


def test_layer_numbers_are_frozen(process):  # golden test: the ws180g005 numbers never change
    assert {n: layer.gds for n, layer in process.layers.items()} == EXPECTED_GDS
    assert process.layers["ox_1v8"].variant == "ws180g105"
    assert process.layers["nsel"].kind == "generated"


def test_every_layer_has_a_purpose(process):
    assert all(layer.purpose for layer in process.layers.values())


@pytest.mark.parametrize("gds", [(1.0, 0), ("1", 0), (True, 0), (-1, 0), (65536, 0), (1, 70000)])
def test_gds_numbers_are_strict_ints_in_range(gds):
    with pytest.raises(ValidationError):
        Layer(gds=gds, kind="drawn", variant="ws180g005", purpose="x")


def test_gds_accepts_the_largest_numbers():
    assert Layer(gds=[65535, 65535], kind="drawn", variant="ws180g005", purpose="x").gds == (
        65535, 65535)


def test_datatypes_are_strict_gds_numbers():
    with pytest.raises(ValidationError):
        Datatypes(drawing=0, label=10.0, pin=2)
