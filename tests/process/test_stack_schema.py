# SPDX-License-Identifier: Apache-2.0
from decimal import Decimal

import pytest
from helpers import set_toml
from ws180g_process.load import ProcessError, load_process

BASELINE_DRAWN = ["nw", "nd", "pd", "po", "co", "m1", "v1", "m2", "v2", "m3", "v3", "m4", "v4",
                  "mtop", "pad", "sab"]
CUTS = {"co", "v1", "v2", "v3", "v4"}
PLACEHOLDER = "no public overlay data; placeholder until a public source or silicon"


def test_supply_and_placeholders(process):
    s = process.stack.supplies["5v0"]
    assert (s.nominal, s.tolerance) == (Decimal("5.0"), Decimal("0.10"))
    assert process.stack.litho["m1"].min_feature == "rules.m1.w"
    assert process.stack.litho["m1"].registration.provenance == "chosen"
    assert process.stack.implants["nplus"].doping is None


def test_supply_5v0(process):
    s = process.stack.supplies["5v0"]
    assert (s.unit, s.provenance) == ("V", "chosen")
    assert "ss_125C_4v50" in s.note and "ff_n40C_5v50" in s.note


def test_litho_names_every_baseline_drawn_layer(process):
    assert list(process.stack.litho) == BASELINE_DRAWN
    for layer, litho in process.stack.litho.items():
        rule = "df" if layer in {"nd", "pd"} else layer
        width = "size" if layer in CUTS else "w"
        assert (litho.min_feature, litho.min_space) == (f"rules.{rule}.{width}", f"rules.{rule}.s")
        r = litho.registration
        assert (r.value, r.unit, r.provenance, r.note) == (None, "um", "chosen", PLACEHOLDER)


def test_implant_and_dielectric_placeholders(process):
    assert set(process.stack.implants) == {"nplus", "pplus", "vt_5v0"}
    assert all(i.doping is None and "placeholder" in i.note
               for i in process.stack.implants.values())
    assert set(process.stack.dielectrics) == {"ild1", "ild2", "ild3", "ild4", "imd_top",
                                              "passivation"}
    assert all(d.thickness is None and "placeholder" in d.note
               for d in process.stack.dielectrics.values())


def test_oxides_and_metals_wait_for_task_7(process):
    assert process.stack.oxides == {} and process.stack.metals == {}


def test_oxide_and_metal_accept_task_7_content():
    from ws180g_process.model import MetalLayer, Oxide

    r = {"min": 1, "nominal": 2, "max": 3, "unit": "nm"}
    oxide = Oxide(thickness=r, vt_n=r, vt_p=r, lmin_n="rules.po.l.n", lmin_p="rules.po.l.p")
    assert oxide.lmin_p == "rules.po.l.p"
    assert MetalLayer(thickness=r, sheet_rho=None).thickness.nominal == 2
    assert MetalLayer().sheet_rho is None


def _lines(data_copy) -> list[str]:
    with pytest.raises(ProcessError) as caught:
        load_process(data_copy)
    return str(caught.value).splitlines()


def test_stack_errors_are_reported_per_entry(data_copy):
    set_toml(data_copy / "stack.toml", ["stack", "supplies", "5v0", "nominal"], "five")
    set_toml(data_copy / "stack.toml", ["stack", "litho", "m2", "registration", "provenance"],
             "private")
    lines = _lines(data_copy)
    assert any(line.startswith("stack.toml: stack.supplies.5v0.nominal:") for line in lines)
    assert any(line.startswith("stack.toml: stack.litho.m2.registration.provenance:")
               for line in lines)


def test_litho_of_an_unknown_layer_is_an_error(data_copy):
    path = data_copy / "stack.toml"
    path.write_text(path.read_text().replace("[stack.litho.sab", "[stack.litho.nosuch"))
    assert any(line.startswith("stack.toml: stack.litho.nosuch:") for line in _lines(data_copy))


def test_a_missing_or_unknown_stack_table_is_an_error(data_copy):
    path = data_copy / "stack.toml"
    path.write_text(path.read_text().replace("[stack.supplies.", "[stack.supply."))
    lines = _lines(data_copy)
    assert "stack.toml: stack.supply: unknown key" in lines
    assert "stack.toml: stack.supplies: missing" in lines


def test_a_stack_table_that_is_not_a_table_is_an_error(data_copy):
    path = data_copy / "stack.toml"
    text = path.read_text().replace("[stack.litho.", "[stack.lithox.")
    path.write_text(text.replace("[stack.metals]\n", "[stack.metals]\n\n[stack]\nlitho = 5\n", 1))
    assert any(line.startswith("stack.toml: stack.litho:") for line in _lines(data_copy))


def test_masks_that_are_not_a_list_are_an_error(data_copy):
    (data_copy / "masks.toml").write_text("# SPDX-License-Identifier: Apache-2.0\nmasks = 5\n")
    assert any(line.startswith("masks.toml: masks:") for line in _lines(data_copy))
