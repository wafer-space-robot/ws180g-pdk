# SPDX-License-Identifier: Apache-2.0
import re
import tomllib
from decimal import Decimal
from pathlib import Path

import pytest
from ws180g_evidence.import_scmos import import_scmos, update_sources

SYNTHETIC = Path(__file__).parent / "data" / "scmos_synthetic"
SYNTHETIC_SECTIONS = {3, 5, 8, 9, 10}


def _pages(**replace: str) -> dict[str, str]:
    pages = {p.stem: p.read_text() for p in sorted(SYNTHETIC.glob("*.html"))}
    return pages | replace


def _import(tmp: Path, pages: dict[str, str] | None = None) -> dict[str, dict]:
    out = tmp / "scmos.toml"
    import_scmos(_pages() if pages is None else pages, out, required=SYNTHETIC_SECTIONS)
    return {e["id"]: e for e in tomllib.loads(out.read_text(), parse_float=Decimal)["entry"]}


def test_lambda_count_times_lambda(tmp):
    entries = _import(tmp)
    deep = entries["scmos8/3.1/deep"]
    assert deep["value"] == Decimal("0.18") and deep["lambda"] == 2
    assert deep["lambda_um"] == Decimal("0.09") and deep["unit"] == "um"
    assert deep["kind"] == "min-width" and deep["layers"] == ["poly"]
    assert deep["cite"] == "SCMOS rev 8.00, page scmos-poly.html, rule 3.1, column DEEP"
    assert entries["scmos8/3.1/subm"]["value"] == Decimal("0.20")
    assert entries["scmos8/3.2.a/deep"]["value"] == Decimal("0.36")
    assert entries["scmos8/3.2.a/deep"]["kind"] == "min-space"


def test_scmos_column_has_no_micron_value(tmp):
    scmos = _import(tmp)["scmos8/3.1/scmos"]
    assert scmos["lambda"] == 2
    assert "value" not in scmos and "lambda_um" not in scmos and "unit" not in scmos


def test_fractional_lambda_count_and_footnote_star(tmp):
    entries = _import(tmp)
    assert entries["scmos8/3.7/subm"]["lambda"] == Decimal("1.5")
    assert entries["scmos8/3.7/deep"]["value"] == Decimal("0.135")
    assert entries["scmos8/3.8/scmos"]["lambda"] == 5
    assert entries["scmos8/3.8/subm"]["value"] == Decimal("0.60")


def test_not_applicable_and_valueless_rows_give_no_entry(tmp):
    entries = _import(tmp)
    assert "scmos8/3.7/scmos" not in entries
    assert "scmos8/8.7/deep" not in entries
    assert not any(e["rule"] == "3.9" for e in entries.values())


def test_highest_metal_group_is_used(tmp):
    entries = _import(tmp)
    via = entries["scmos8/8.6/deep"]
    assert via["lambda"] == 5 and via["value"] == Decimal("0.45")
    assert via["kind"] == "exact-size" and via["layers"] == ["via1"]
    assert entries["scmos8/8.6/scmos"]["lambda"] == 3
    assert entries["scmos8/8.7/subm"]["value"] == Decimal("0.90")
    assert entries["scmos8/9.6/subm"]["layers"] == ["metal2"]
    assert entries["scmos8/9.6/deep"]["lambda"] == 14


def test_tables_nested_in_a_layout_table(tmp):
    entries = _import(tmp)
    cut = entries["scmos8/5.11/deep"]
    assert cut["kind"] == "exact-size" and cut["value"] == Decimal("0.36")
    assert cut["layers"] == ["contact", "poly"]
    assert entries["scmos8/5.12.b/subm"]["value"] == Decimal("0.250")
    assert entries["scmos8/5.12.b/subm"]["layers"] == ["contact", "poly"]


def test_glass_rows_are_guidelines_in_microns(tmp):
    entries = _import(tmp)
    glass = entries["scmos8/10.8"]
    assert glass["value"] == 55 and glass["unit"] == "um" and glass["guideline"] is True
    assert "lambda" not in glass and "column" not in glass
    assert glass["cite"] == "SCMOS rev 8.00, page scmos-glass.html, rule 10.8, column Microns"
    assert entries["scmos8/10.9"]["value"] == Decimal("17.5")
    assert entries["scmos8/3.1/deep"]["guideline"] is False


def test_missing_cited_section_raises(tmp):
    with pytest.raises(ValueError, match=r"\b4\b"):
        import_scmos(_pages(), tmp / "scmos.toml", required=SYNTHETIC_SECTIONS | {4})


def test_lambda_mapping_is_read_from_the_main_page(tmp):
    pages = _pages(main=_pages()["main"].replace("0.09", "0.08"))
    assert _import(tmp, pages)["scmos8/3.1/deep"]["value"] == Decimal("0.16")
    with pytest.raises(ValueError, match="SCN6M_DEEP"):
        _import(tmp, _pages(main=_pages()["main"].replace("SCN6M_DEEP", "SCN5M_DEEP")))


def test_importer_is_reproducible(tmp):
    import_scmos(_pages(), tmp / "a.toml", required=SYNTHETIC_SECTIONS)
    import_scmos(dict(reversed(_pages().items())), tmp / "b.toml", required=SYNTHETIC_SECTIONS)
    assert (tmp / "a.toml").read_bytes() == (tmp / "b.toml").read_bytes()
    ids = [e["id"] for e in tomllib.loads((tmp / "a.toml").read_text())["entry"]]
    assert ids == sorted(ids, key=lambda i: [int(t) if t.isdigit() else t
                                             for t in re.split(r"(\d+)", i)])


def test_update_sources_replaces_only_the_scmos_block(tmp, repo_root):
    path = tmp / "sources.toml"
    path.write_text((repo_root / "evidence/data/sources.toml").read_text())
    digests = {"poly": "ab" * 32, "glass": "cd" * 32}
    update_sources(path, digests, "2026-01-02")
    once = path.read_text()
    update_sources(path, digests, "2026-01-02")
    assert path.read_text() == once
    table = tomllib.loads(once)["sources"]
    assert table["scmos8"]["sha256"] == digests
    assert str(table["scmos8"]["retrieved"]) == "2026-01-02"
    assert table["gf180mcu-drm"] == tomllib.loads(
        (repo_root / "evidence/data/sources.toml").read_text())["sources"]["gf180mcu-drm"]
