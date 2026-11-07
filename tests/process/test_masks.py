# SPDX-License-Identifier: Apache-2.0
import pytest
from ws180g_process.load import ProcessError, load_process

BASELINE = {"nw", "nd", "pd", "po", "co", "m1", "v1", "m2", "v2", "m3", "v3", "m4", "v4",
            "mtop", "pad", "sab", "nsel", "psel"}


def test_baseline_masks_have_justification(process):
    baseline = [m for m in process.masks if m.baseline]
    assert {m.name for m in baseline} >= BASELINE
    assert all(m.justification for m in process.masks)
    assert next(m for m in process.masks if m.name == "dnw").module == "deep-n-well"


def test_mask_list_is_exactly_the_spec_set(process):
    masks = {m.name: m for m in process.masks}
    assert set(masks) == BASELINE | {"dnw", "rhi", "ox_3v3", "ox_1v8"}
    assert all(m.module is None and m.variant is None for m in masks.values() if m.baseline)
    assert masks["rhi"].module == "high-res-poly" and not masks["rhi"].baseline
    assert (masks["ox_3v3"].variant, masks["ox_3v3"].module) == ("ws180g035", None)
    assert masks["ox_1v8"].variant == "ws180g105" and not masks["ox_1v8"].baseline
    assert not masks["nsel"].drawn and not masks["psel"].drawn
    assert masks["sab"].drawn


def test_every_mask_has_a_justification(process):
    assert all(m.justification.strip() for m in process.masks)


def test_marker_layers_are_not_masks(process):
    assert not [m.name for m in process.masks if m.name.startswith("mk_")]


def _replace(path, old, new):
    text = path.read_text()
    assert old in text
    path.write_text(text.replace(old, new, 1))


def _lines(data_copy) -> list[str]:
    with pytest.raises(ProcessError) as caught:
        load_process(data_copy)
    return str(caught.value).splitlines()


def test_a_mask_that_is_not_a_layer_is_an_error(data_copy):
    _replace(data_copy / "masks.toml", 'name = "rhi"', 'name = "nosuch"')
    assert any(line.startswith("masks.toml: masks.") and "nosuch" in line
               for line in _lines(data_copy))


def test_a_duplicate_mask_is_an_error(data_copy):
    _replace(data_copy / "masks.toml", 'name = "rhi"', 'name = "dnw"')
    assert any(line.startswith("masks.toml: masks.") and "duplicate" in line
               for line in _lines(data_copy))


def test_a_mask_drawn_flag_must_match_its_layer(data_copy):
    _replace(data_copy / "masks.toml", 'name = "nsel"\ndrawn = false', 'name = "nsel"\ndrawn = true')
    assert any(line.startswith("masks.toml: masks.") and "nsel" in line
               for line in _lines(data_copy))


def test_a_mask_schema_error_does_not_hide_other_masks(data_copy):
    _replace(data_copy / "masks.toml", 'name = "rhi"', 'name = 7')
    _replace(data_copy / "masks.toml", 'name = "dnw"', 'name = "nosuch"')
    lines = _lines(data_copy)
    assert any(line.startswith("masks.toml: masks.") and ".name:" in line for line in lines)
    assert any("nosuch" in line for line in lines)


def test_a_baseline_mask_has_no_module():
    from ws180g_process.model import Mask

    with pytest.raises(ValueError):
        Mask(name="nw", drawn=True, baseline=True, module="deep-n-well", justification="x")
    with pytest.raises(ValueError):
        Mask(name="dnw", drawn=True, baseline=False, justification="x")
