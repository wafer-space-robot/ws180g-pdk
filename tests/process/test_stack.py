# SPDX-License-Identifier: Apache-2.0
from decimal import ROUND_HALF_UP, Decimal

from ws180g_process.ranges import Range

D = Decimal


def _range(lo, nominal, hi, unit) -> Range:
    return Range(min=D(lo), nominal=D(nominal), max=D(hi), unit=unit)


def test_top_metal_thickness(process):
    t = process.stack.metals["mtop"].thickness
    assert t.range == _range("0.75", "1.1", "3.6", "um")
    assert t.margin == D("1.2") and "3.2" in t.margin_reason and "6 k" in t.margin_reason
    assert t.evidence == ["gf180mcu-drm/TM9K", "gf180mcu-drm/TM11K", "gf180mcu-drm/TM30K"]
    assert (t.margin_achieved_min, t.margin_achieved_max) == (D("1.200"), D("1.200"))


def test_oxide_5v0(process):
    ox = process.stack.oxides["5v0"]
    assert (ox.lmin_n, ox.lmin_p) == ("rules.po.l.n", "rules.po.l.p")
    assert ox.thickness.range == _range("12.66", "15.6", "19.2", "nm")
    assert ox.thickness.evidence == ["gf180mcu-models/nfet_06v0/toxe",
                                     "gf180mcu-models/nfet_06v0/toxp"]
    assert ox.thickness.margin == D("1.2") and "TOXE" in ox.thickness.margin_reason
    assert ox.vt_n.range == _range("0.560", "0.722", "0.924", "V")
    assert ox.vt_p.range == _range("0.700", "0.869", "1.078", "V")
    assert "xc018/ne5/vt" in ox.vt_n.evidence and "xc018/pe5/vt" in ox.vt_p.evidence


def test_sheet_resistance_is_single_source(process):
    metals = process.stack.metals
    assert metals["m1"].sheet_rho.range == _range("0.0633", "0.095", "0.1425", "ohm/sq")
    for m in ("m2", "m3", "m4"):
        assert metals[m].sheet_rho.range == _range("0.0566", "0.085", "0.1275", "ohm/sq")
        assert metals[m].sheet_rho.evidence == [f"xc018/r{m}/rs"]
    assert metals["mtop"].sheet_rho.range == _range("0.008", "0.037", "0.0555", "ohm/sq")
    assert all(m.sheet_rho.margin == D("1.5") for m in metals.values())


def test_lower_metal_thickness_is_a_placeholder(process):
    for name, metal in process.stack.metals.items():
        if name != "mtop":
            assert metal.thickness is None and "placeholder" in metal.note, name


def _ratio(a: Decimal, b: Decimal) -> Decimal:
    return (a / b).quantize(D("0.001"), rounding=ROUND_HALF_UP)


def test_recorded_range_margins_match_the_evidence(process, evidence):
    """`.min` achieved = smallest cited value / min, `.max` = max / largest cited value,
    using magnitudes (the PMOS threshold is negative on the card)."""
    ox = process.stack.oxides["5v0"]
    fields = [ox.thickness, ox.vt_n, ox.vt_p,
              *(f for m in process.stack.metals.values() for f in (m.thickness, m.sheet_rho)
                if f is not None)]
    for f in fields:
        values = [abs(evidence.entries[e].value) for e in f.evidence]
        assert f.margin_achieved_min == _ratio(min(values), f.range.min), f
        assert f.margin_achieved_max == _ratio(f.range.max, max(values)), f
        assert f.margin_achieved_min >= f.margin and f.margin_achieved_max >= f.margin, f
