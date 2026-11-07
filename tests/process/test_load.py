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


def test_toml_floats_load_as_exact_decimals(data_copy):
    # a binary float would make 0.435 off the 0.005 grid; the loader keeps the literal
    set_toml(data_copy / "rules.toml", ["rules", '"m1.w"', "value"], 0.435)
    assert load_process(data_copy).rules["m1.w"].value == Decimal("0.435")


def _lines(data_copy) -> list[str]:
    with pytest.raises(ProcessError) as caught:
        load_process(data_copy)
    return str(caught.value).splitlines()


def test_schema_and_grid_errors_of_one_file_are_reported_together(data_copy):
    set_toml(data_copy / "process.toml", ["grid", "provenance"], "private")
    set_toml(data_copy / "process.toml", ["grid", "value"], 0.0033)
    lines = _lines(data_copy)
    assert any(line.startswith("process.toml: grid.provenance:") for line in lines)
    assert any(line.startswith("process.toml: grid.value:") for line in lines)


def test_errors_of_several_files_are_reported_together(data_copy):
    set_toml(data_copy / "process.toml", ["grid", "provenance"], "private")
    set_toml(data_copy / "layers.toml", ["layers", "nd", "kind"], "painted")
    set_toml(data_copy / "layers.toml", ["layers", "pd", "gds"], "x")  # breaks pd only
    lines = _lines(data_copy)
    assert any(line.startswith("process.toml: grid.provenance:") for line in lines)
    assert any(line.startswith("layers.toml: layers.nd.kind:") for line in lines)
    assert any(line.startswith("layers.toml: layers.pd.gds:") for line in lines)


def test_a_layer_schema_error_does_not_hide_layer_cross_checks(data_copy):
    set_toml(data_copy / "layers.toml", ["layers", "nd", "kind"], "painted")
    set_toml(data_copy / "layers.toml", ["layers", "ptap", "variant"], "ws180g999")
    lines = _lines(data_copy)
    assert any(line.startswith("layers.toml: layers.nd.kind:") for line in lines)
    assert any(line.startswith("layers.toml: layers.ptap.variant:") for line in lines)


def test_a_missing_file_does_not_hide_schema_errors(data_copy):
    (data_copy / "masks.toml").unlink()
    set_toml(data_copy / "process.toml", ["grid", "provenance"], "private")
    lines = _lines(data_copy)
    assert any(line.startswith("masks.toml: ") for line in lines)
    assert any(line.startswith("process.toml: grid.provenance:") for line in lines)


@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_rejects_a_non_finite_grid(data_copy, value):
    set_toml(data_copy / "process.toml", ["grid", "value"], value)
    with pytest.raises(ProcessError, match="grid.value"):
        load_process(data_copy)
