# SPDX-License-Identifier: Apache-2.0
"""Magic technology file (DRC only): the generated text, and Magic reading it in the project
container.

The text tests read the generated files; the `sandbox` tests run Magic through
`build/sandbox-run` and skip when Docker or the image is missing."""

import dataclasses
import re
from pathlib import Path

import klayout.db as kdb
import pytest
from ws180g_rules.table import RuleTable
from ws180g_tech.magic import MAGIC_KINDS, magic_key, main, write_magic_tech

VARIANT = "ws180g005"
WHY = re.compile(r'"([A-Za-z0-9_.]+): ')


@pytest.fixture
def table(process) -> RuleTable:
    return RuleTable.from_process(process, VARIANT)


@pytest.fixture
def written(table, process, tmp) -> list[Path]:
    return write_magic_tech(table, process, VARIANT, tmp / "magic")


@pytest.fixture
def tech(written) -> str:
    return written[0].read_text(encoding="utf-8")


def _section(text: str, name: str) -> str:
    """The body of a top-level section (`name` alone on a line up to the next `end`)."""
    match = re.search(rf"^{name}\n(.*?)^end$", text, re.MULTILINE | re.DOTALL)
    assert match, f"no {name} section"
    return match.group(1)


def _klayout_only_block(drc: str) -> str:
    """The comment lines after the block's heading, up to the first other line."""
    _, _, rest = drc.partition("# KLayout-only rules (not checked by Magic):\n")
    assert rest, "no KLayout-only block"
    block = []
    for line in rest.splitlines():
        if not line.lstrip().startswith("#"):
            break
        block.append(line.strip() + "\n")
    return "".join(block)


def _why_ids(drc: str) -> set[str]:
    rules = [line for line in drc.splitlines() if not line.lstrip().startswith("#")]
    return set(WHY.findall("\n".join(rules)))


def test_writes_the_two_files(written, tmp):
    assert [p.name for p in written] == [f"{VARIANT}.tech", f"{VARIANT}.magicrc"]
    assert all(p.parent == tmp / "magic" and p.is_file() for p in written)


def test_spdx_on_line_one(written):
    for path in written:
        assert path.read_text().splitlines()[0] == "# SPDX-License-Identifier: Apache-2.0"


def test_tech_section_names_the_variant(tech):
    assert VARIANT in _section(tech, "tech").split()


def test_width_in_nanometres(tech):
    assert 'width nwell 1440 "nw.w' in tech


def test_every_magic_rule_has_a_why(tech, table):
    magic = {r.id for r in table.checkable() if "magic" in r.engines}
    assert magic and magic == _why_ids(_section(tech, "drc"))


def test_klayout_only_rules_are_listed_not_emitted(tech, table):
    drc = _section(tech, "drc")
    block = _klayout_only_block(drc)
    only = [r.id for r in table.checkable() if r.engines == ["klayout"]]
    assert only
    for rid in only:
        assert re.search(rf"^#\s+{re.escape(rid)}: \S", block, re.MULTILINE), rid
    assert not set(only) & _why_ids(drc)


def test_rules_without_engines_are_absent(tech, table):
    none = [r.id for r in table.rows if not r.engines]
    assert "nsel.w" in none
    for rid in none:
        assert f"{rid}:" not in tech and f'"{rid}' not in tech, rid


def test_extract_section_is_empty(tech):
    # Magic falls back to its default technology at startup without the section; there is
    # no extraction in Phase 0, so it is empty
    assert _section(tech, "extract").strip() == ""


def test_cifinput_reads_gds_in_nanometres(tech, process):
    cifin = _section(tech, "cifinput")
    assert re.search(r"^ *style gds$", cifin, re.MULTILINE)
    assert re.search(r"^ *scalefactor 1 nanometers$", cifin, re.MULTILINE)
    for name in ("nw", "nd", "pd", "po", "co", "m1", "v4", "mtop", "pad", "sab", "nsel",
                 "gate"):
        number, datatype = process.layers[name].gds
        assert re.search(rf"^ *calma {name} {number} {datatype}$", cifin, re.MULTILINE), name


def test_composite_types_are_built_by_booleans(tech):
    cifin = _section(tech, "cifinput")
    assert re.search(r"^ *layer ntransistor po\n *and nd\n", cifin, re.MULTILINE)
    assert re.search(r"^ *layer ndcontact co\n *and nd\n", cifin, re.MULTILINE)


def test_cifoutput_writes_every_drawn_layer(tech, process):
    cifout = _section(tech, "cifoutput")
    for name in ("nw", "nd", "pd", "po", "co", "m1", "v1", "mtop", "pad", "sab"):
        number, datatype = process.layers[name].gds
        assert re.search(rf"^ *layer {name} \S+\n *calma {number} {datatype}$", cifout,
                         re.MULTILINE), name


def test_contacts_are_declared(tech):
    contact = _section(tech, "contact")
    for line in ("ndcontact ndiff m1", "polycontact poly m1", "via1 m1 m2", "via4 m4 mtop"):
        assert re.search(rf"^ *{line}$", contact, re.MULTILINE), line


def test_magicrc(written):
    rc = written[1].read_text()
    assert f"{VARIANT}.tech" in rc and "tech load" in rc
    for line in ("cif istyle gds", "cif ostyle gds", "drc euclidean on", "snap internal"):
        assert re.search(rf"^{line}$", rc, re.MULTILINE), line


def test_no_date_or_time(written):
    for path in written:
        assert not re.search(r"20\d\d-\d\d-\d\d|\d\d:\d\d:\d\d", path.read_text())


def test_byte_identical_runs(table, process, tmp):
    one = write_magic_tech(table, process, VARIANT, tmp / "one")
    two = write_magic_tech(table, process, VARIANT, tmp / "two")
    for a, b in zip(one, two, strict=True):
        assert a.read_bytes() == b.read_bytes()


def test_every_key_of_the_table_is_mapped(table):
    keys = {magic_key(r) for r in table.checkable()}
    assert keys <= set(MAGIC_KINDS)
    for row in table.checkable():
        kind = MAGIC_KINDS[magic_key(row)]
        assert ("magic" in row.engines) == (kind.emit is not None), row.id
        if kind.emit is None:
            assert kind.rule.startswith("KLayout-only: "), row.id


def test_cif_checks_have_their_style(tech):
    drc = _section(tech, "drc")
    assert re.search(r"^ *cifstyle drc$", drc, re.MULTILINE)
    cifout = _section(tech, "cifoutput")
    assert re.search(r"^style drc$", cifout, re.MULTILINE)
    for name in re.findall(r"^ *cif\w+ (c_\w+)", drc, re.MULTILINE):
        assert re.search(rf"^ *templayer {name}\b", cifout, re.MULTILINE), name


def test_a_magic_row_that_magic_cannot_check_raises(table, process, tmp):
    rows = [dataclasses.replace(r, engines=["klayout", "magic"]) if r.id == "grid" else r
            for r in table.rows]
    with pytest.raises(ValueError, match="grid"):
        write_magic_tech(dataclasses.replace(table, rows=rows), process, VARIANT, tmp / "x")


def test_unknown_kind_raises(table, process, tmp):
    rows = [dataclasses.replace(r, kind="no-such-kind") if r.id == "po.w" else r
            for r in table.rows]
    with pytest.raises(ValueError, match="po.w"):
        write_magic_tech(dataclasses.replace(table, rows=rows), process, VARIANT, tmp / "x")


def test_cli(tmp, capsys):
    main(["--out", str(tmp / "cli")])
    assert (tmp / "cli" / f"{VARIANT}.tech").is_file()
    assert f"{VARIANT}.magicrc" in capsys.readouterr().out


# --- sandbox: Magic reads the technology


def _gds(path: Path, process, cell: str, boxes: list[tuple[str, int, int, int, int]]) -> None:
    """Write a layout (boxes in dbu on named layers, one top cell `cell`) and derive its
    generated layers."""
    from ws180g_layergen.derive import derive_file

    layout = kdb.Layout()
    layout.dbu = 0.001
    top = layout.create_cell(cell)
    for name, x1, y1, x2, y2 in boxes:
        top.shapes(layout.layer(*process.layers[name].gds)).insert(kdb.Box(x1, y1, x2, y2))
    drawn = path.with_suffix(".drawn.gds")
    options = kdb.SaveLayoutOptions()
    options.gds2_write_timestamps = False
    layout.write(str(drawn), options)
    derive_file(drawn, path, process)


# A legal n-channel transistor: W = 2.0, L = 0.72, contacted source and drain.
LEGAL_NFET = [
    ("nd", 0, 0, 2000, 2000), ("po", 640, -270, 1360, 2270),
    ("co", 180, 890, 400, 1110), ("co", 1600, 890, 1820, 1110),
    ("m1", 60, 600, 520, 1400), ("m1", 1480, 600, 1940, 1400),
]
NARROW_POLY = [("po", 0, 0, 235, 3000)]


def _magic(sandbox, work: Path, tcl: str) -> str:
    """Run one Magic session in the container with the Tcl script `tcl` on stdin."""
    (work / "script.tcl").write_text(tcl + "\nquit -noprompt\n", encoding="utf-8")
    done = sandbox.run(
        ["sh", "-c", (f"magic -dnull -noconsole -rcfile /work/out/{VARIANT}.magicrc"
                     " < /work/out/script.tcl")],
        work, mem="2g", cpus=2)
    assert done.returncode == 0, done.stdout + done.stderr
    return done.stdout


def _drc_script(cells: list[str]) -> str:
    """Per cell: read its GDS, check it, print `COUNT <cell> <n>` and `WHY <cell> <text>`."""
    lines = []
    for cell in cells:
        # drc listall reports the errors under the box; grow it past the cell's bounding
        # box, which an error area may lie just outside
        lines += [f"gds read /work/out/{cell}.gds", f"load {cell}", "select top cell",
                  "box grow c 20000", "drc check", "drc catchup",
                  f'puts "COUNT {cell} [drc list count total]"',
                  f'foreach {{why boxes}} [drc listall why] {{ puts "WHY {cell} $why" }}']
    return "\n".join(lines)


def _results(out: str) -> tuple[dict[str, int], dict[str, set[str]]]:
    counts = {m[1]: int(m[2]) for m in re.finditer(r"^COUNT (\S+) (\d+)$", out, re.MULTILINE)}
    whys: dict[str, set[str]] = {cell: set() for cell in counts}
    for m in re.finditer(r"^WHY (\S+) ([A-Za-z0-9_.]+): ", out, re.MULTILINE):
        whys[m[1]].add(m[2])
    return counts, whys


@pytest.fixture
def work(written, tmp) -> Path:
    return written[0].parent


@pytest.mark.sandbox
def test_magic_loads_the_technology(sandbox, work):
    out = _magic(sandbox, work, 'puts "TECH [tech name]"')
    assert re.search(rf"^TECH {VARIANT}$", out, re.MULTILINE), out


@pytest.mark.sandbox
def test_gds_read_builds_the_transistor_type(sandbox, work, process):
    _gds(work / "nfet.gds", process, "nfet", LEGAL_NFET)
    out = _magic(sandbox, work, "gds read /work/out/nfet.gds\nload nfet\nselect top cell\n"
                                'select area\nputs "WHAT [lindex [what -list] 0]"')
    line = re.search(r"^WHAT (.*)$", out, re.MULTILINE)
    assert line and "ntransistor" in line[1], out


@pytest.mark.sandbox
def test_drc_passes_a_legal_transistor_and_flags_narrow_poly(sandbox, work, process):
    _gds(work / "legal.gds", process, "legal", LEGAL_NFET)
    _gds(work / "narrow.gds", process, "narrow", NARROW_POLY)
    out = _magic(sandbox, work, _drc_script(["legal", "narrow"]))
    counts, whys = _results(out)
    assert counts.get("legal") == 0, out
    assert counts.get("narrow", 0) >= 1 and "po.w" in whys["narrow"], out


# Probes: (boxes in dbu, the exact set of rule ids Magic reports). The first group is the
# KLayout deck's review probes (tests/rules/test_klayout_deck.py) with the ids KLayout
# reports on them; "differs" marks the documented approximations of the Magic rules, where
# the KLayout ids are given in the comment. The tap-distance rules are KLayout-only.
MAGIC_PROBES: dict[str, tuple[list[tuple[str, int, int, int, int]], set[str]]] = {
    "legal_nfet": ([("nd", 0, 0, 2000, 1000), ("po", 640, -400, 1360, 1400)], set()),
    "field_po_near_df": ([("nd", 0, 0, 1000, 1000), ("po", 1300, 0, 1540, 1000)],
                         {"po.s.df"}),
    "po_flush": ([("nd", 0, 0, 2000, 1000), ("po", 640, -400, 1360, 1000)], {"po.x.df"}),
    # differs: KLayout {po.x.df}; Magic measures the end inside df as a gate side
    "po_inside": ([("nd", 0, 0, 2000, 1000), ("po", 640, -400, 1360, 700)],
                  {"df.x.po", "po.l.n"}),
    "df_flush": ([("nd", 0, 0, 1360, 1000), ("po", 640, -400, 1360, 1400)], {"df.x.po"}),
    # differs: KLayout {df.x.po}; as po_inside
    "df_inside": ([("nd", 0, 0, 1200, 1000), ("po", 640, -400, 1360, 1400)],
                  {"po.x.df", "po.l.n"}),
    # differs: KLayout {po.x.sab, sab.area}; Magic's side enclosure also sees the flush end
    "po_sab_flush": ([("sab", 0, 0, 1000, 2000), ("po", 300, -1000, 540, 2000)],
                     {"po.x.sab", "sab.e.po", "sab.area"}),
    "po_sab_inside": ([("sab", 0, 0, 1000, 2000), ("po", 300, -1000, 540, 1500)],
                      {"sab.area"}),
    "nd_wholly_in_sab": ([("sab", 0, 0, 1800, 1800), ("nd", 400, 400, 1400, 1400)], set()),
    "df_sab_inside": ([("sab", 0, 0, 2000, 2000), ("nd", 300, -1000, 1300, 1600)], set()),
    "po_wholly_in_sab": ([("sab", 0, 0, 1800, 3000), ("po", 400, 400, 640, 2600)], set()),
    "short_end_cap": ([("nd", 0, 0, 2000, 1000), ("po", 640, -100, 1360, 1400)],
                      {"po.x.df"}),
    "short_df_extension": ([("nd", 440, 0, 2000, 1000), ("po", 640, -400, 1360, 1400)],
                           {"df.x.po"}),
    "po_abutting_df": ([("nd", 0, 0, 1000, 1000), ("po", 1000, 0, 1240, 1000)], {"po.s.df"}),
    "po_sab_legal": ([("sab", 0, 0, 1000, 2000), ("po", 300, -1000, 540, 3000)],
                     {"sab.area"}),
    # differs: KLayout {df.x.sab}; as po_sab_flush
    "df_sab_flush": ([("sab", 0, 0, 2000, 2000), ("nd", 300, -1000, 1300, 2000)],
                     {"df.x.sab", "sab.e.df"}),
    "hanging_co": ([("m1", 0, 0, 1000, 1000), ("co", 900, 300, 1120, 520)],
                   {"m1.e.co", "co.in"}),
    "legal_outside": ([("nw", 5000, 0, 8000, 3000), ("nd", 0, 0, 1000, 1000),
                       ("co", 300, 300, 520, 520), ("m1", 180, 180, 640, 640),
                       ("po", 3000, -1000, 3240, 2000)], {"m1.area"}),
    # further probes, each checked against the KLayout deck when written (same ids unless
    # marked "differs")
    "co_rect": ([("nd", 0, 0, 2000, 2000), ("co", 900, 900, 1120, 1125),
                 ("m1", 500, 500, 1500, 1500)], {"co.size"}),
    "v1_straddle_m1": ([("m1", 0, 0, 1000, 1000), ("m2", 0, 0, 2000, 1000),
                        ("v1", 900, 300, 1170, 570)], {"m1.e.v1"}),
    # differs: KLayout reports nothing for a cut without metal
    "v1_no_m1": ([("m2", 0, 0, 2000, 1000), ("v1", 900, 300, 1170, 570)], {"m1.e.v1"}),
    "stacked_co_v1": ([("nd", 0, 0, 2000, 2000), ("co", 890, 890, 1110, 1110),
                       ("m1", 500, 500, 1500, 1500), ("v1", 865, 865, 1135, 1135),
                       ("m2", 500, 500, 1500, 1500)], set()),
    # differs: KLayout {nw.e.pd}; Magic's spacing also sees the outside part touch nw
    "nw_pd_straddle": ([("nw", 0, 0, 5000, 5000), ("pd", 4500, 1000, 5500, 2000)],
                       {"nw.e.pd", "nw.s.pd"}),
    "nw_pd_close": ([("nw", 0, 0, 5000, 5000), ("pd", 3500, 1000, 4500, 2000)], {"nw.e.pd"}),
    "nw_nd_close": ([("nw", 0, 0, 5000, 5000), ("nd", 1000, 1000, 4645, 2000)], {"nw.e.nd"}),
    "nw_nd_near": ([("nw", 0, 0, 5000, 5000), ("nd", 5500, 1000, 6500, 2000)], {"nw.s.nd"}),
    "co_field": ([("co", 0, 0, 220, 220), ("m1", -500, -500, 720, 720)], {"co.in"}),
    "co_gate": ([("nd", 0, 0, 2000, 2000), ("po", 640, -400, 1360, 2400),
                 ("co", 890, 890, 1110, 1110), ("m1", 500, 500, 1500, 1500)], {"co.no.gate"}),
    "co_butt": ([("nw", -3000, -3000, 5000, 5000), ("pd", 0, 0, 1000, 1000),
                 ("nd", 1000, 0, 2000, 1000), ("co", 890, 390, 1110, 610),
                 ("m1", 500, 0, 1500, 1000)], {"co.no.butt"}),
    "co_straddle_df": ([("nd", 0, 0, 1000, 1000), ("co", 900, 300, 1120, 520),
                        ("m1", 500, 0, 1500, 1000)], {"co.in", "df.e.co"}),
    "co_df_close": ([("nd", 0, 0, 1000, 1000), ("co", 700, 300, 920, 520),
                     ("m1", 300, 0, 1300, 1000)], {"df.e.co"}),
    "po_co_close": ([("po", 0, 0, 1000, 1000), ("co", 700, 300, 920, 520),
                     ("m1", 300, 0, 1300, 1000)], {"po.e.co"}),
    "co_near_gate": ([("nd", 0, 0, 2000, 2000), ("po", 640, -270, 1360, 2270),
                      ("co", 1595, 890, 1815, 1110), ("m1", 1475, 600, 1935, 1400)],
                     {"co.s.gate"}),
    "pco_near_df": ([("po", 0, 0, 800, 1000), ("co", 400, 390, 620, 610),
                     ("m1", 280, 200, 740, 800), ("nd", 855, 0, 1855, 1000)],
                    {"co.po.s.df", "po.s.df"}),
    # differs: KLayout {sab.e.po, sab.no.gate, sab.area}; the poly over a gate is a
    # transistor in Magic, not unsilicided poly, so the side enclosure does not see it
    "sab_gate": ([("nd", 0, 0, 2000, 2000), ("po", 640, -400, 1360, 2400),
                  ("sab", 500, 500, 1500, 1500)], {"sab.no.gate", "sab.area"}),
    "sab_e_po_side": ([("sab", 0, 0, 1000, 3500), ("po", 100, -1000, 340, 4500)],
                      {"sab.e.po"}),
    "sab_df_near": ([("sab", 0, 0, 2000, 2000), ("nd", 2200, 0, 3200, 1000)], {"sab.s.df"}),
    "sab_po_cross_and_near": ([("sab", 0, 0, 2000, 2000), ("po", 300, -1000, 540, 3000),
                               ("po", 2300, -1000, 2540, 3000)], {"sab.s.po"}),
    "short_l_n": ([("nd", 0, 0, 2000, 2000), ("po", 640, -400, 1355, 2400)], {"po.l.n"}),
    "short_l_p": ([("nw", -1000, -1000, 3000, 3000), ("pd", 0, 0, 2000, 2000),
                   ("po", 640, -400, 1235, 2400)], {"po.l.p"}),
    "nd_near_pgate": ([("nw", -3000, -3000, 3000, 5000), ("pd", -1000, 0, 1000, 2000),
                       ("po", -360, -400, 360, 2400), ("nd", -500, 2870, 500, 3600)],
                      {"nd.s.pgate"}),
    "nd_far_pgate": ([("nw", -3000, -3000, 3000, 5000), ("pd", -1000, 0, 1000, 2000),
                      ("po", -360, -400, 360, 2400), ("nd", -500, 2935, 500, 3600)], set()),
    "pd_near_ngate": ([("nd", -1000, 0, 1000, 2000), ("po", -360, -400, 360, 2400),
                       ("pd", -500, 2870, 500, 3600)], {"pd.s.ngate"}),
    "df_np_near": ([("nd", 0, 0, 1000, 1000), ("pd", 1450, 0, 2450, 1000)], {"df.s.np"}),
    "df_np_butted": ([("pd", 1000, 0, 2000, 1000), ("nd", 0, 0, 1000, 1000)], set()),
    "dnw_narrow": ([("dnw", 0, 0, 3670, 20000)], {"dnw.w"}),
}


@pytest.mark.sandbox
def test_magic_probes(sandbox, work, process):
    for name, (boxes, _) in MAGIC_PROBES.items():
        _gds(work / f"{name}.gds", process, name, boxes)
    counts, whys = _results(_magic(sandbox, work, _drc_script(list(MAGIC_PROBES))))
    assert set(counts) == set(MAGIC_PROBES)
    wrong = {name: sorted(whys[name]) for name, (_, want) in MAGIC_PROBES.items()
             if whys[name] != want}
    assert not wrong
