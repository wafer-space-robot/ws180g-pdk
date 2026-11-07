# SPDX-License-Identifier: Apache-2.0
"""The one-command build (Task 21): `ws180g-build --no-container` on the real process
description, twice, and the Sphinx documentation built on its generated pages.

The build runs in pytest's temporary directory (`--out`, and `--docs` for the generated
pages that `docs/rules.md` and `docs/evidence.md` include), never in the checkout's `out/`
or `docs/generated/`. The container half (the three engine runs) is the full build, run by
hand; see the Task 21 report."""

import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from ws180g_build import tree
from ws180g_build.main import BuildError, build, main

REPO = Path(__file__).resolve().parents[2]
VARIANT = "ws180g005"
TREE = [
    "libs.tech/klayout/ws180g005.lyp",
    "libs.tech/klayout/ws180g005.lyt",
    "libs.tech/klayout/ws180g005.map",
    "libs.tech/klayout/drc/ws180g005.drc",
    "libs.tech/magic/ws180g005.tech",
    "libs.tech/magic/ws180g005.magicrc",
    "docs/rules.md",
    "docs/evidence-report.md",
]


def _build(root: Path) -> tuple[int, Path, Path]:
    out, docs = root / "out", root / "docs-generated"
    code = main(["--variant", VARIANT, "--out", str(out), "--docs", str(docs),
                 "--no-container"])
    return code, out, docs


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    return _build(tmp_path_factory.mktemp("build-one"))


@pytest.fixture(scope="module")
def built_again(tmp_path_factory):
    return _build(tmp_path_factory.mktemp("build-two"))


def test_build_exits_0_and_creates_the_tree(built):
    code, out, _ = built
    assert code == 0
    for rel in TREE:
        assert (out / VARIANT / rel).is_file(), rel
    # the deck's entry points load the checks file from their own directory
    assert (out / VARIANT / "libs.tech/klayout/drc/ws180g005_checks.rb").is_file()


def test_manifest(built):
    _, out, _ = built
    manifest = json.loads((out / "build-manifest.json").read_text(encoding="utf-8"))
    image = (REPO / "docker" / "IMAGE_ID").read_text(encoding="utf-8").split()[0]
    assert manifest["image_id"] == image
    assert manifest["container_runs"] is False
    assert manifest["variant"] == VARIANT
    assert re.fullmatch(r"[0-9a-f]{40}", manifest["git_commit"])
    files = manifest["files"]
    assert list(files) == sorted(files)
    for rel in TREE:
        assert f"{VARIANT}/{rel}" in files
    # every output with its sha256, paths relative to out/
    for rel, digest in files.items():
        assert not Path(rel).is_absolute() and ".." not in Path(rel).parts
        assert hashlib.sha256((out / rel).read_bytes()).hexdigest() == digest
    on_disk = sorted(p.relative_to(out).as_posix() for p in out.rglob("*")
                     if p.is_file() and p.name != "build-manifest.json")
    assert on_disk == list(files)


def test_two_builds_are_byte_identical(built, built_again):
    _, one, _ = built
    _, two, _ = built_again
    assert (one / "build-manifest.json").read_bytes() == (
        two / "build-manifest.json").read_bytes()


def test_no_timestamps_or_absolute_paths(built):
    _, out, _ = built
    for path in out.rglob("*"):
        if path.is_file() and path.suffix in {".md", ".json", ".drc", ".rb", ".tech",
                                              ".magicrc", ".lyp", ".lyt", ".map", ".csv"}:
            text = path.read_text(encoding="utf-8")
            assert str(out) not in text and str(REPO) not in text, path
            assert not re.search(r"\b20\d\d-\d\d-\d\dT\d\d:", text), path


def test_manual_page(built):
    _, out, docs = built
    text = (out / VARIANT / "docs" / "rules.md").read_text(encoding="utf-8")
    line = next(x for x in text.splitlines() if x.startswith("| `nw.w` |"))
    assert "1.44" in line and "gf180mcu-drm/NW.1a/5v" in line
    assert "PL.8" not in text
    assert (docs / "rules.md").read_bytes() == text.encode("utf-8")


def test_evidence_page_lists_pl8_under_density(built):
    _, out, docs = built
    text = (out / VARIANT / "docs" / "evidence-report.md").read_text(encoding="utf-8")
    heading = None
    for line in text.splitlines():
        if line.startswith("### "):
            heading = line
        if "`gf180mcu-drm/PL.8/5v`" in line:
            break
    else:
        pytest.fail("PL.8 is not on the evidence page")
    assert heading is not None and heading.startswith("### density"), heading
    assert (docs / "evidence-report.md").read_bytes() == text.encode("utf-8")


def test_failing_evidence_report_fails_the_build(tmp, data_copy, capsys):
    from helpers import set_toml

    set_toml(data_copy / "rules.toml", ["rules", '"nw.w"', "value"], 0.9)
    args = ["--out", str(tmp / "out"), "--docs", str(tmp / "docs"), "--process",
            str(data_copy)]
    with pytest.raises(BuildError, match="evidence report"):
        build(VARIANT, tmp / "out", tmp / "docs", container=False, process_dir=data_copy)
    # the console script reports it and exits 1, before any container would start
    assert main(args) == 1
    err = capsys.readouterr().err
    assert "evidence report is not ok" in err and "rules.nw.w" in err
    assert not (tmp / "out" / "build-manifest.json").exists()


def test_assemble_refuses_a_missing_input(tmp):
    with pytest.raises(FileNotFoundError):
        tree.assemble(VARIANT, tmp / "nothing", tmp / "dest")


def test_sphinx_builds_without_warnings(built, tmp):
    """`sphinx-build -W` on a copy of `docs/` holding the build's generated pages (the design
    specs and plans left out, as `conf.py` excludes them)."""
    _, _, generated = built
    docs = tmp / "docs"
    shutil.copytree(REPO / "docs", docs,
                    ignore=shutil.ignore_patterns("superpowers", "generated"))
    shutil.copytree(generated, docs / "generated")
    done = subprocess.run([sys.executable, "-m", "sphinx", "-W", "-b", "html", "-q",
                           str(docs), str(tmp / "html")], capture_output=True, text=True,
                          check=False)
    assert done.returncode == 0, done.stdout[-4000:] + done.stderr[-4000:]
    assert "nw.w" in (tmp / "html" / "rules.html").read_text(encoding="utf-8")
    assert "PL.8" in (tmp / "html" / "evidence.html").read_text(encoding="utf-8")
