# SPDX-License-Identifier: Apache-2.0
"""KLayout technology files: layer properties, technology and LEF/DEF map."""

import re
import shutil
import subprocess
import xml.etree.ElementTree as ET

import pytest
from ws180g_tech.klayout import main, write_klayout_tech

VARIANT = "ws180g005"


def expected_layers(process, variant):
    allowed = {variant, *process.variants[variant].contains}
    return {n: l for n, l in process.layers.items() if l.variant is None or l.variant in allowed}


@pytest.fixture
def written(process, tmp):
    return write_klayout_tech(process, VARIANT, tmp)


def test_three_files_written_and_parse(written, tmp):
    assert [p.name for p in written] == [f"{VARIANT}.lyp", f"{VARIANT}.lyt", f"{VARIANT}.map"]
    for p in written:
        assert p.parent == tmp and p.is_file()
    ET.parse(written[0])
    ET.parse(written[1])


def test_lyp_entries(process, written):
    layers = expected_layers(process, VARIANT)
    entries = ET.parse(written[0]).getroot().findall("properties")
    by_name = {e.findtext("name"): e for e in entries}
    base = [n for n in by_name if "." not in n]
    assert base == list(layers)
    for name, layer in layers.items():
        number, datatype = layer.gds
        assert by_name[name].findtext("source") == f"{number}/{datatype}@1"
        assert by_name[name].findtext("valid") == "true"
        if layer.kind == "drawn":
            assert by_name[f"{name}.label"].findtext("source") == f"{number}/10@1"
        else:
            assert f"{name}.label" not in by_name
    pins = sorted(n for n in by_name if n.endswith(".pin"))
    assert pins == sorted(f"{n}.pin" for n in ("m1", "m2", "m3", "m4", "mtop", "v1", "v2", "v3", "v4"))
    assert by_name["m1.pin"].findtext("source") == "11/2@1"


def test_lyp_colours_distinct_and_generated_dimmed(process, written):
    by_name = {e.findtext("name"): e for e in ET.parse(written[0]).getroot().findall("properties")}
    layers = expected_layers(process, VARIANT)
    colours = [by_name[n].findtext("fill-color") for n in layers]
    assert len(set(colours)) == len(colours)
    for n, layer in layers.items():
        want = "-32" if layer.kind == "generated" else "0"
        assert by_name[n].findtext("fill-brightness") == want
        assert by_name[n].findtext("frame-brightness") == want


def test_lyt_names_lyp_and_layer_map(process, written):
    root = ET.parse(written[1]).getroot()
    assert root.findtext("name") == VARIANT
    assert root.findtext("dbu") == "0.001"
    assert root.findtext("default-grids") == "0.005!"
    assert root.findtext("layer-properties_file") == f"{VARIANT}.lyp"
    assert root.findtext("add-other-layers") == "true"
    text = root.find("reader-options/common/layer-map").text
    layers = expected_layers(process, VARIANT)
    entries = [f"'{n} : {l.gds[0]}/{l.gds[1]}'" for n, l in layers.items()]
    assert text == f"layer_map({';'.join(entries)})"


def test_map_lines(written):
    lines = written[2].read_text().splitlines()
    assert "m1 NET,SPNET,PIN,VIA 11 0" in lines
    assert "NAME m1/LABEL 11 10" in lines
    assert "m1 PIN 11 2" in lines
    assert "v4 PIN 18 2" in lines
    assert lines[-1] == "DIEAREA ALL 0 0"
    assert lines[0].startswith("#")


def test_spdx_headers(written):
    for p in written:
        head = p.read_text().splitlines()[:2]
        assert any("SPDX-License-Identifier: Apache-2.0" in h for h in head)


def test_variant_filter(process, tmp):
    files = write_klayout_tech(process, VARIANT, tmp / "a")
    assert all("ox_3v3" not in p.read_text() and "ox_1v8" not in p.read_text() for p in files)
    files = write_klayout_tech(process, "ws180g035", tmp / "b")
    text = files[1].read_text()
    assert "ox_3v3" in text and "ox_1v8" not in text


def test_byte_identical_runs(process, tmp):
    one = write_klayout_tech(process, VARIANT, tmp / "one")
    two = write_klayout_tech(process, VARIANT, tmp / "two")
    for a, b in zip(one, two, strict=True):
        assert a.read_bytes() == b.read_bytes()


def test_cli(tmp):
    main(["--out", str(tmp / "cli")])
    assert (tmp / "cli" / f"{VARIANT}.lyt").is_file()


@pytest.mark.sandbox
def test_klayout_loads_technology(process, written, repo_root):
    runner = repo_root / "build" / "sandbox-run"
    if not runner.exists():
        pytest.skip("build/sandbox-run is absent")
    script = repo_root / "tests" / "tech" / "check_tech.py"
    if shutil.which("docker") is None:
        pytest.skip("docker is absent")
    done = subprocess.run(
        [str(runner), "klayout", "-b", "-r", str(script), "-rd", f"lyt={written[1]}"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stdout + done.stderr
    match = re.search(r"^layers=(\d+)$", done.stdout, re.MULTILINE)
    assert match, done.stdout
    assert int(match.group(1)) == len(expected_layers(process, VARIANT))
