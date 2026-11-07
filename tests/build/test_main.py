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


# --- the container half with the engine runners replaced (no container)


class FakeEngines:
    """Stands in for the three runners: every fixture gives exactly the expected markers,
    except the ids in `wrong`, which give one `x.y` marker."""

    def __init__(self, monkeypatch, wrong: set[str] = frozenset()) -> None:
        from ws180g_rules.run_klayout import DrcResult, DrcResults

        self.calls: list[str] = []
        self.wrong = wrong
        self.by_path: dict[Path, object] = {}

        def results(name, paths, expected):
            self.calls.append(name)
            out = DrcResults()
            for p in paths:
                got = expected(p)
                if p.parent.name + "/" + p.stem in self.wrong:
                    got = {"x.y": 1}
                out[p] = DrcResult(violations=got, categories_run=5)
            return out

        def klayout(deck, paths, work, runner, process, image_id):
            assert image_id.startswith("sha256:")
            return results("klayout", paths, lambda p: self.by_path[p].markers())

        def magic(tech, paths, work, runner, process, image_id):
            from ws180g_tech.magic import magic_markers

            return results("magic", paths,
                           lambda p: dict.fromkeys(magic_markers(self.by_path[p]), 1))

        def gf180mcu(paths, work, runner, mapping, metal_top, jobs, image_id):
            return results(f"gf180mcu {metal_top}", paths, lambda p: {})

        monkeypatch.setattr("ws180g_rules.run_klayout.run_klayout_many", klayout)
        monkeypatch.setattr("ws180g_rules.run_magic.run_magic_many", magic)
        monkeypatch.setattr("ws180g_precheck.gf180mcu.run_gf180mcu_drc_many", gf180mcu)


@pytest.fixture
def staged(process, tmp):
    from ws180g_rules.fixtures import write_fixtures
    from ws180g_rules.klayout_deck import write_klayout_deck
    from ws180g_rules.table import RuleTable
    from ws180g_tech.magic import write_magic_tech

    table = RuleTable.from_process(process)
    generated = tmp / "generated"
    write_klayout_deck(table, process, generated / "drc")
    write_magic_tech(table, process, VARIANT, generated / "magic")
    return table, generated, write_fixtures(table, process, generated / "fixtures")


def _run(engines, staged, process, tmp):
    from ws180g_build.main import run_engines

    table, generated, fixtures = staged
    engines.by_path = {f.path: f for f in fixtures}
    run_engines(table, process, fixtures, generated, tmp / "reports", tmp / "work",
                runner=None, image_id="sha256:" + "1" * 64, log=lambda m: None)


def test_container_runs_report_and_pass(monkeypatch, staged, process, tmp):
    engines = FakeEngines(monkeypatch)
    _run(engines, staged, process, tmp)
    assert engines.calls == ["klayout", "magic", "gf180mcu 9K", "gf180mcu 11K",
                             "gf180mcu 30K"]
    for name in ("klayout-fixtures", "magic-fixtures", "gf180mcu-gate"):
        report = json.loads((tmp / "reports" / f"{name}.json").read_text(encoding="utf-8"))
        if name == "gf180mcu-gate":
            assert all(r["dirty"] == {} for r in report["runs"].values())
            assert "dnw.w/min" in report["excluded"]
        else:
            assert report["wrong"] == {} and report["fixtures"] > 0


def test_container_run_with_a_wrong_fixture_fails(monkeypatch, staged, process, tmp):
    engines = FakeEngines(monkeypatch, wrong={"nw.w/pass_min"})
    with pytest.raises(BuildError, match="nw.w/pass_min"):
        _run(engines, staged, process, tmp)
    report = json.loads((tmp / "reports" / "klayout-fixtures.json").read_text(encoding="utf-8"))
    assert report["wrong"]["nw.w/pass_min"] == {"expected": {}, "got": {"x.y": 1}}


def test_gate_2_runs_the_regression_fixtures(monkeypatch, staged, process, tmp):
    """The build's GF180MCU runs include every permanent regression fixture of
    `ws180g_precheck.regressions`, as the gate test does."""
    from ws180g_precheck.gate import gate_fixtures, regression_names

    names = regression_names()
    assert names  # the Task 18 regressions
    engines = FakeEngines(monkeypatch)
    _run(engines, staged, process, tmp)
    report = json.loads((tmp / "reports" / "gf180mcu-gate.json").read_text(encoding="utf-8"))
    assert report["regressions"] == [f"regressions/{n}" for n in names]
    expected = len(gate_fixtures(staged[2])) + len(names)
    assert all(r["fixtures"] == expected for r in report["runs"].values())
    retargeted = tmp / "work" / "gf180mcu" / "retargeted" / "regressions"
    assert sorted(p.stem for p in retargeted.glob("*.gds")) == names


def test_a_dirty_regression_fixture_fails_the_build(monkeypatch, staged, process, tmp):
    from ws180g_precheck.gate import regression_names

    case = f"regressions/{regression_names()[0]}"
    engines = FakeEngines(monkeypatch, wrong={case})
    with pytest.raises(BuildError, match=case):
        _run(engines, staged, process, tmp)
