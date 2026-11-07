# SPDX-License-Identifier: Apache-2.0
from decimal import Decimal

import pytest
from helpers import set_toml
from ws180g_process.load import ProcessError, load_process
from ws180g_process.ranges import on_grid


def test_rejects_unknown_provenance(data_copy):
    set_toml(data_copy / "process.toml", ["grid", "provenance"], "private")
    with pytest.raises(ProcessError, match="provenance"):
        load_process(data_copy)


def test_rejects_grid_not_multiple_of_dbu(data_copy):
    # the grid must be a multiple of the 0.001 um database unit
    set_toml(data_copy / "process.toml", ["grid", "value"], 0.0033)
    with pytest.raises(ProcessError, match="grid"):
        load_process(data_copy)


def test_reports_every_error_of_a_file_at_once(data_copy):
    set_toml(data_copy / "process.toml", ["grid", "provenance"], "private")
    set_toml(data_copy / "process.toml", ["grid", "unit"], 7)
    with pytest.raises(ProcessError) as caught:
        load_process(data_copy)
    lines = str(caught.value).splitlines()
    assert len(lines) == 2
    assert all(line.startswith("process.toml: grid.") for line in lines)
    assert any("grid.provenance" in line for line in lines)
    assert any("grid.unit" in line for line in lines)


def test_on_grid_is_exact_decimal_arithmetic():
    grid = Decimal("0.005")
    assert on_grid(Decimal("0.435"), grid)
    assert not on_grid(Decimal("0.433"), grid)
    assert on_grid(Decimal(0), grid)
    assert on_grid(Decimal("0.005"), Decimal("0.001"))
    assert not on_grid(Decimal("0.0033"), Decimal("0.001"))


def test_toml_floats_load_as_exact_decimals(process):
    assert isinstance(process.grid.value, Decimal)
    assert process.grid.unit == "um"
    assert process.grid.provenance == "chosen"
