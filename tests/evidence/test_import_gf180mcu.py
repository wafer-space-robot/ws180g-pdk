# SPDX-License-Identifier: Apache-2.0
import hashlib
import tomllib
from decimal import Decimal

from ws180g_evidence.import_gf180mcu import import_gf180mcu, import_gf180mcu_table


def test_entry_ids_and_columns(gf_entries):
    assert gf_entries["gf180mcu-drm/NW.1a/5v"].value == Decimal("0.86")
    assert gf_entries["gf180mcu-drm/NW.1a/3v3"].value == Decimal("0.86")
    assert gf_entries["gf180mcu-drm/CO.1"].kind == "exact-size" and gf_entries["gf180mcu-drm/CO.1"].value == Decimal("0.22")
    assert gf_entries["gf180mcu-drm/PL.2/5v/n"].value == Decimal("0.6")
    assert gf_entries["gf180mcu-drm/PL.2/5v/p"].value == Decimal("0.5")
    assert gf_entries["gf180mcu-drm/Mn.1/m1"].value == Decimal("0.23")
    assert gf_entries["gf180mcu-drm/Mn.1/mn"].value == Decimal("0.28")
    assert gf_entries["gf180mcu-drm/DF.13/5v"].kind == "max-distance" and gf_entries["gf180mcu-drm/DF.13/5v"].value == Decimal(15)
    assert gf_entries["gf180mcu-drm/DF.9/5v"].unit == "um2"
    assert gf_entries["gf180mcu-drm/MT30.1/a"].value == Decimal("1.8") and gf_entries["gf180mcu-drm/MT30.1/b"].value == Decimal("2.2")
    assert gf_entries["gf180mcu-drm/PL.3b/5v"].guideline is True        # trailing * in the rule number
    assert gf_entries["gf180mcu-drm/PAD.1/wedge"].guideline is True     # table headed GUIDELINE NO.
    assert gf_entries["gf180mcu-drm/PAD.4/ball"].guideline is False
    assert "gf180mcu-drm/PL.6" not in gf_entries                        # text-only rule
    assert gf_entries["gf180mcu-drm/PL.10/5v"].unit == "mA/um"
    assert gf_entries["gf180mcu-drm/GRID"].kind == "grid" and gf_entries["gf180mcu-drm/GRID"].value == Decimal("0.005")
    assert gf_entries["gf180mcu-drm/PL.8/5v"].kind == "density-floor" and gf_entries["gf180mcu-drm/PL.8/5v"].value == Decimal(14)
    assert gf_entries["gf180mcu-drm/DF.2b/5v"].kind == "max-width"
    assert gf_entries["gf180mcu-drm/NP.3d"].kind == "min-space"
    assert gf_entries["gf180mcu-drm/MT.1/b"].guideline is True and gf_entries["gf180mcu-drm/MT.1/b"].value == Decimal("0.44")
    assert gf_entries["gf180mcu-drm/TM30K"].kind == "thickness" and gf_entries["gf180mcu-drm/TM30K"].value == Decimal("3.0")
    assert gf_entries["gf180mcu-drm/LU.1/mv/a"].kind == "max-distance" and gf_entries["gf180mcu-drm/LU.1/mv/a"].value == Decimal(15)
    assert gf_entries["gf180mcu-drm/PRES.8"].unit == "mA/um"           # unit in the description
    assert gf_entries["gf180mcu-drm/LRES.8"].unit == "mA/um"           # printed (mA/m)
    assert gf_entries["gf180mcu-drm/TM.1a"].value == Decimal(40)       # table headed NO.
    assert gf_entries["gf180mcu-drm/PM.2"].value == Decimal(50)


def test_golden_poly_table(repo_root, tmp):
    import_gf180mcu_table(repo_root / "evidence/sources/gf180mcu-drm/16_Poly2_42.csv", tmp / "poly.toml")
    assert tomllib.loads((tmp / "poly.toml").read_text()) == tomllib.loads((repo_root / "tests/evidence/golden/16_Poly2_42.toml").read_text())
    # Checked without the golden file, from the CSV by hand.
    entries = {e["id"]: e for e in tomllib.loads((tmp / "poly.toml").read_text())["entry"]}
    assert entries["gf180mcu-drm/PL.1/5v"]["value"] == 0.2 and entries["gf180mcu-drm/PL.1/5v"]["kind"] == "min-width"
    assert entries["gf180mcu-drm/PL.8/5v"]["kind"] == "density-floor" and entries["gf180mcu-drm/PL.8/5v"]["value"] == 14
    assert entries["gf180mcu-drm/PL.8/5v"]["unit"] == "%"
    assert entries["gf180mcu-drm/PL.10/5v"]["guideline"] is True and entries["gf180mcu-drm/PL.10/5v"]["unit"] == "mA/um"


def test_importer_is_reproducible(tmp, repo_root):
    import_gf180mcu(repo_root / "evidence/sources/gf180mcu-drm", tmp / "gf.toml")
    assert (tmp / "gf.toml").read_bytes() == (repo_root / "evidence/data/gf180mcu-drm.toml").read_bytes()


def test_vendored_sha256_matches(evidence, repo_root):
    for name, digest in evidence.sources["gf180mcu-drm"].sha256.items():
        assert hashlib.sha256((repo_root / "evidence/sources/gf180mcu-drm" / name).read_bytes()).hexdigest() == digest


def test_every_vendored_table_is_registered(evidence, repo_root):
    vendored = {p.name for p in (repo_root / "evidence/sources/gf180mcu-drm").glob("*.csv")}
    assert len(vendored) == 85
    assert set(evidence.sources["gf180mcu-drm"].sha256) == vendored | {"LICENSE"}


def test_guideline_part_of_a_multi_line_cell(gf_entries):
    # The last item of the description ("III) ... (guideline)", "iii. ... (guideline)*")
    # is the cell's last value; the other parts stay binding.
    for guideline, binding in (("CO.6/d", "CO.6/c"), ("Vn.3/e", "Vn.3/d"), ("Vn.4/d", "Vn.4/c")):
        assert gf_entries[f"gf180mcu-drm/{guideline}"].guideline is True
        assert gf_entries[f"gf180mcu-drm/{guideline}"].value == Decimal("0.12")
        assert gf_entries[f"gf180mcu-drm/{binding}"].guideline is False
