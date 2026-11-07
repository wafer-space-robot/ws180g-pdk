# SPDX-License-Identifier: Apache-2.0
"""The loader's cross-checks on rules, stack paths and masks: one failing case each."""

import pytest
from helpers import set_toml
from ws180g_process.load import ProcessError, load_process


def _replace(path, old, new):
    text = path.read_text()
    assert old in text
    path.write_text(text.replace(old, new, 1))


def _lines(data_copy) -> list[str]:
    with pytest.raises(ProcessError) as caught:
        load_process(data_copy)
    return str(caught.value).splitlines()


def _has(lines, prefix, text=""):
    return any(line.startswith(prefix) and text in line for line in lines)


def test_the_real_data_loads(data_copy):
    assert load_process(data_copy).rules["m1.w"].value is not None


def test_a_litho_path_must_name_a_rule(data_copy):
    _replace(data_copy / "stack.toml", 'min_feature = "rules.m1.w"',
             'min_feature = "rules.m1.nosuch"')
    assert _has(_lines(data_copy), "stack.toml: stack.litho.m1.min_feature:", "rules.m1.nosuch")


def test_an_oxide_lmin_path_must_name_a_rule(data_copy):
    set_toml(data_copy / "stack.toml", ["stack", "oxides", "5v0", "lmin_n"], "rules.po.l.x")
    assert _has(_lines(data_copy), "stack.toml: stack.oxides.5v0.lmin_n:", "rules.po.l.x")


def test_implied_by_must_name_a_rule(data_copy):
    set_toml(data_copy / "rules.toml", ["rules", '"mtop.area"', "implied_by"], "rules.nosuch")
    assert _has(_lines(data_copy), "rules.toml: rules.mtop.area.implied_by:", "rules.nosuch")


def test_composed_of_paths_must_name_a_rule(data_copy):
    _replace(data_copy / "rules.toml", '"rules.sel.x"]', '"rules.sel.y"]')
    assert _has(_lines(data_copy), "rules.toml: rules.nd.s.pgate.composed_of:", "rules.sel.y")


def test_a_length_must_be_on_the_grid(data_copy):
    set_toml(data_copy / "rules.toml", ["rules", '"m1.w"', "value"], 0.362)
    assert _has(_lines(data_copy), "rules.toml: rules.m1.w.value:", "grid")


def test_an_area_must_be_a_multiple_of_0_005(data_copy):
    set_toml(data_copy / "rules.toml", ["rules", '"m1.area"', "value"], 0.2166)
    assert _has(_lines(data_copy), "rules.toml: rules.m1.area.value:", "0.005")


def test_a_margin_below_1_2_is_an_error(data_copy):
    set_toml(data_copy / "rules.toml", ["rules", '"m1.w"', "margin"], 1.1)
    assert _has(_lines(data_copy), "rules.toml: rules.m1.w.margin:", "1.2")


def test_a_maximum_needs_a_margin_of_1_25(data_copy):
    set_toml(data_copy / "rules.toml", ["rules", '"nw.tap.dmax"', "margin"], 1.2)
    assert _has(_lines(data_copy), "rules.toml: rules.nw.tap.dmax.margin:", "1.25")


def test_a_non_standard_margin_needs_a_reason(data_copy):
    set_toml(data_copy / "rules.toml", ["rules", '"m1.w"', "margin"], 1.3)
    assert _has(_lines(data_copy), "rules.toml: rules.m1.w.margin:", "margin_reason")


def test_a_non_standard_margin_with_a_reason_is_accepted(data_copy):
    set_toml(data_copy / "rules.toml", ["rules", '"m1.w"', "margin"], 1.3)
    _replace(data_copy / "rules.toml", "margin = 1.3\n",
             'margin = 1.3\nmargin_reason = "a recorded reason"\n')
    assert load_process(data_copy).rules["m1.w"].margin_reason == "a recorded reason"


def test_a_stack_range_margin_is_checked(data_copy):
    set_toml(data_copy / "stack.toml", ["stack", "metals", "m1", "sheet_rho", "margin"], 1.3)
    assert _has(_lines(data_copy), "stack.toml: stack.metals.m1.sheet_rho.margin:",
                "margin_reason")


def test_a_topology_rule_needs_a_fixture(data_copy):
    _replace(data_copy / "rules.toml", 'fixture = "co_on_gate"\n', "")
    assert _has(_lines(data_copy), "rules.toml: rules.co.no.gate.fixture:", "missing")


def test_a_rule_layer_must_be_known(data_copy):
    _replace(data_copy / "rules.toml", 'layers = ["sab", "po.unrelated(sab)"]',
             'layers = ["sab", "po.unrelated(sabx)"]')
    assert _has(_lines(data_copy), "rules.toml: rules.sab.s.po.layers:", "sabx")


def test_an_alias_layer_must_be_known(data_copy):
    _replace(data_copy / "rules.toml", 'df = "nd|pd"', 'df = "nd|pdx"')
    assert _has(_lines(data_copy), "rules.toml: aliases.df:", "pdx")


def test_an_edge_layer_must_be_known(data_copy):
    set_toml(data_copy / "rules.toml", ["rules", '"sab.e.po"', "edge_layer"], "pox")
    assert _has(_lines(data_copy), "rules.toml: rules.sab.e.po.edge_layer:", "pox")


def test_a_rule_variant_and_module_must_be_known(data_copy):
    set_toml(data_copy / "rules.toml", ["rules", '"m1.w"', "variant"], "ws180g999")
    set_toml(data_copy / "rules.toml", ["rules", '"dnw.w"', "module"], "no-such-module")
    lines = _lines(data_copy)
    assert _has(lines, "rules.toml: rules.m1.w.variant:", "ws180g999")
    assert _has(lines, "rules.toml: rules.dnw.w.module:", "no-such-module")


def test_a_mask_module_must_match_its_layer(data_copy):
    _replace(data_copy / "masks.toml", 'module = "deep-n-well"', 'module = "high-res-poly"')
    assert _has(_lines(data_copy), "masks.toml: masks.", "module")


def test_a_mask_variant_must_match_its_layer(data_copy):
    _replace(data_copy / "masks.toml", 'variant = "ws180g035"', 'variant = "ws180g105"')
    assert _has(_lines(data_copy), "masks.toml: masks.", "variant")


def test_every_baseline_drawn_mask_has_a_litho_entry(data_copy):
    _replace(data_copy / "stack.toml", "[stack.litho.sab]", "[stack.litho.nw_again]")
    _replace(data_copy / "stack.toml", "[stack.litho.sab.registration]",
             "[stack.litho.nw_again.registration]")
    assert _has(_lines(data_copy), "stack.toml: stack.litho:", "sab")


def test_a_stack_that_is_not_a_table_does_not_crash_the_checks(data_copy):
    (data_copy / "stack.toml").write_text("# SPDX-License-Identifier: Apache-2.0\nstack = 5\n")
    assert _has(_lines(data_copy), "stack.toml: stack:")
