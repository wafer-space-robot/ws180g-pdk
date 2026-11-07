# SPDX-License-Identifier: Apache-2.0
"""The hand-transcribed evidence: X-FAB XC018 (data sheet pages 5 and 7), the GF180MCU
model card (`sm141064.ngspice`) and the registered, not yet transcribed onsemi ONC18."""

import tomllib
from decimal import Decimal

import pytest
from ws180g_evidence.import_gf180mcu import _write
from ws180g_evidence.model import Entry

HAND_FILES = ["xc018.toml", "gf180mcu-models.toml"]


def _of(evidence, source):
    return {k: e for k, e in evidence.entries.items() if e.source == source}


def test_xc018_entries(evidence):
    xc = _of(evidence, "xc018")
    assert xc["xc018/topvia/width"].kind == "exact-size"
    assert xc["xc018/topvia/width"].value == Decimal("0.36")
    assert xc["xc018/metal1/spacing"].value == Decimal("0.23")
    assert xc["xc018/metal1/spacing"].kind == "min-space"
    assert xc["xc018/nwell/width"].kind == "min-width"
    assert xc["xc018/metal2345/width"].layers == ["metal2", "metal3", "metal4", "metal5"]
    assert xc["xc018/rpp1k1/rs"].value == 1000 and xc["xc018/rpp1k1/rs"].unit == "ohm/sq"
    assert xc["xc018/ne5/vt"].value == Decimal("0.77") and xc["xc018/ne5/vt"].unit == "V"
    assert {k for k, e in xc.items() if e.kind == "exact-size"} == {
        "xc018/contact/width", "xc018/via/width", "xc018/topvia/width"}
    masks = ["nwell", "active", "poly", "polyres", "contact", "metal1", "via", "metal2345",
             "topvia", "topmetal"]
    rs = ["rm1", "rm2", "rm3", "rm4", "rm5", "rmtp", "rmtpl", "rpp1k1"]
    assert set(xc) == ({f"xc018/{m}/{c}" for m in masks for c in ("width", "spacing")}
                       | {"xc018/ne5/vt", "xc018/pe5/vt"} | {f"xc018/{r}/rs" for r in rs})


def test_every_xc018_entry_cites_a_page(evidence):
    entries = _of(evidence, "xc018")
    assert len(entries) == 30
    for entry in entries.values():
        assert "page" in entry.cite, entry.id


def test_xc018_source(evidence):
    source = evidence.sources["xc018"]
    assert source.transcribed is True and source.vendored is False
    assert source.retrieved is not None
    assert set(source.sha256) == {"xc018_datasheet.pdf"}


def test_gf180mcu_model_card_entries(evidence):
    gf = _of(evidence, "gf180mcu-models")
    assert gf["gf180mcu-models/nfet_06v0/lmin"].value == Decimal("0.6")
    assert gf["gf180mcu-models/nfet_06v0/lmin"].unit == "um"
    assert "line 37515 (.model nfet_06v0.1," in gf["gf180mcu-models/nfet_06v0/lmin"].cite
    assert gf["gf180mcu-models/nfet_06v0/lmin_bin0"].value == Decimal("0.7")
    assert "line 37177 (.model nfet_06v0.0," in gf["gf180mcu-models/nfet_06v0/lmin_bin0"].cite
    assert gf["gf180mcu-models/pfet_06v0/lmin"].value == Decimal("0.5")
    assert gf["gf180mcu-models/pfet_06v0/lmin"].kind == "gate-length"
    assert gf["gf180mcu-models/nfet_06v0/toxe"].value == Decimal("15.2")
    assert gf["gf180mcu-models/nfet_06v0/toxe"].unit == "nm"
    assert gf["gf180mcu-models/nfet_06v0/toxp"].value == Decimal("16.0")
    assert set(gf) == {f"gf180mcu-models/nfet_06v0/{p}" for p in ("toxe", "toxp", "vth0", "lmin", "lmin_bin0")} | {
        f"gf180mcu-models/pfet_06v0/{p}" for p in ("vth0", "lmin")}
    for entry in gf.values():
        assert entry.cite.startswith("sm141064.ngspice line ")
        assert entry.cite.endswith(", typical section)")
        assert "open_pdks" in entry.text and "1689ac3" in entry.text


def test_gf180mcu_models_source_pins_the_upstream_commit(evidence):
    source = evidence.sources["gf180mcu-models"]
    assert source.commit == "63d25e2aeb8db6976cc107474a9658b4ea73cc05"
    assert f"/blob/{source.commit}/models/ngspice/sm141064.ngspice" in source.url


def test_onc18_registered_not_transcribed(evidence):
    source = evidence.sources["onc18"]
    assert source.transcribed is False and source.retrieved is None
    assert not _of(evidence, "onc18")


def test_untranscribed_sources_have_no_entries(evidence):
    untranscribed = {s for s, src in evidence.sources.items() if not src.transcribed}
    assert untranscribed, "expected at least one registered, untranscribed source"
    assert not [e.id for e in evidence.entries.values() if e.source in untranscribed]


@pytest.mark.parametrize("name", HAND_FILES)
def test_hand_file_round_trips_through_writer(name, repo_root, tmp):
    """A hand-written file is in the writer's form: writing its entries back gives the same
    bytes, given the file's own "Transcribed by hand" header line."""
    path = repo_root / "evidence" / "data" / name
    with path.open("rb") as f:
        raw = tomllib.load(f, parse_float=Decimal)
    entries = [Entry.model_validate(item) for item in raw["entry"]]
    out = tmp / name
    header = path.read_text(encoding="utf-8").split("\n")[1]
    assert header.startswith("# Transcribed by hand")
    _write(entries, out, header=header)
    assert out.read_bytes() == path.read_bytes()


@pytest.mark.parametrize("source", ["xc018", "onc18", "gf180mcu-models"])
def test_source_readme(source, repo_root):
    readme = (repo_root / "evidence" / "sources" / source / "README.md").read_text()
    assert readme.startswith("<!-- SPDX-License-Identifier: Apache-2.0 -->\n")


@pytest.mark.parametrize("source", ["xc018", "gf180mcu-models"])
def test_readme_lists_the_recorded_digests(source, evidence, repo_root):
    readme = (repo_root / "evidence" / "sources" / source / "README.md").read_text()
    for name, digest in evidence.sources[source].sha256.items():
        assert f"`{name}`" in readme and digest in readme
