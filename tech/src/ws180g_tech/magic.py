# SPDX-License-Identifier: Apache-2.0
"""Magic technology file (DRC only) and startup file, generated from the rule table.

`write_magic_tech(table, process, variant, out_dir)` writes `<variant>.tech` and
`<variant>.magicrc`. The technology follows Magic's standard layer model, because types on
one Magic plane cannot overlap and cross-plane enclosure needs contact types:

- planes `well` (`nwell`), `dnw` (`dnwell`, the deep-n-well module), `active`, `metal1` to
  `metal4`, `metaltop`, `pad`, `sab`, `select` (`nsel`, `psel`), and one plane per remaining
  drawn layer of the variant (markers, module and oxide layers), whose type has the layer's
  name;
- on `active`, disjoint composite types built by boolean operations on the drawn GDS layers
  when the GDS is read (`cifinput` style `gds`, one internal unit = 1 nm), so the lower layer
  is not lost: transistors (`po` over `nd`/`pd`), diffusion and poly contacts, well taps
  (`nsubdiff`, `psubdiff` and their contacts, as layergen's ntap/ptap), unsilicided poly and
  diffusion (under `sab`: `rpoly`, `rndiff`, `rpdiff`), and two error cut types,
  `gatecontact` (a cut on a gate) and `fieldcontact` (a cut on field oxide), which the
  topology rules flag; `cifoutput` style `gds` is the inverse (each GDS layer is the union
  of its types);
- `cifoutput` style `drc` holds the CIF layers of the checks Magic's edge rules cannot make
  (flush and inside extension ends, shapes not interacting with sab, sab on a gate); the drc
  section checks them with `cifmaxwidth <layer> 0` (any shape is an error) and `cifspacing`.

The `drc` section has one block per rule with Magic among its `engines`, each Magic rule
with `"<rule id>: ..."` as its why string and its distances in nanometres, and a comment on
what it measures and where it approximates the KLayout check. Rows with
`engines == ["klayout"]` are listed with their reason in a comment block at the top of the
section; rows with no engine are skipped. `MAGIC_KINDS` maps every rule kind, and the special
keys for `edges`, `condition`, composed layers and topology fixtures, to the Magic rule
emitted or to "KLayout-only: <reason>"; a row that lists Magic under a KLayout-only key
raises `ValueError`. The `extract` section is empty (extraction is Phase 1). The output is
deterministic and carries no date.
"""

import argparse
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from ws180g_process.model import Process
from ws180g_rules.klayout_deck import BUTTING_ALLOWED
from ws180g_rules.layer_expr import Unrelated
from ws180g_rules.table import DEFAULT_VARIANT, RuleRow, RuleTable

from ws180g_tech.klayout import selected_layers

GENERATOR = "ws180g_tech.magic"
SPDX = "# SPDX-License-Identifier: Apache-2.0"
NM = Decimal(1000)
CIF_DRC = "drc"  # the cifoutput style of the CIF checks

# --- the layer model

# Types of the active plane and their cifinput booleans over the drawn GDS layers (first
# entry: the layer the type starts from). The definitions are disjoint, so the paint order
# does not matter. ndiff/pdiff: device diffusion (nd outside, pd inside nw); nsubdiff,
# psubdiff: well taps (nd inside, pd outside nw).
ACTIVE: dict[str, list[str]] = {
    "ndiff": ["nd", "and-not nw", "and-not po,co,sab"],
    "pdiff": ["pd", "and nw", "and-not po,co,sab"],
    "nsubdiff": ["nd", "and nw", "and-not po,co"],
    "psubdiff": ["pd", "and-not nw", "and-not po,co"],
    "rndiff": ["nd", "and sab", "and-not nw", "and-not po,co"],
    "rpdiff": ["pd", "and sab", "and nw", "and-not po,co"],
    "poly": ["po", "and-not nd,pd,co,sab"],
    "rpoly": ["po", "and sab", "and-not nd,pd,co"],
    "ntransistor": ["po", "and nd", "and-not co"],
    "ptransistor": ["po", "and pd", "and-not co"],
    "ndcontact": ["co", "and nd", "and-not nw", "and-not po"],
    "pdcontact": ["co", "and pd", "and nw", "and-not po"],
    "nsubdiffcontact": ["co", "and nd", "and nw", "and-not po"],
    "psubdiffcontact": ["co", "and pd", "and-not nw", "and-not po"],
    "polycontact": ["co", "and po", "and-not nd,pd"],
    "gatecontact": ["co", "and po", "and nd,pd"],
    "fieldcontact": ["co", "and-not po,nd,pd"],
}
# Contact types: (type, residue on the lower plane, residue on the upper plane). The two
# error cuts are contacts too, so the metal 1 enclosure sees them; their active residues
# only matter for connectivity, which this DRC-only technology does not use.
CONTACTS: list[tuple[str, str, str]] = [
    ("ndcontact", "ndiff", "m1"), ("pdcontact", "pdiff", "m1"),
    ("nsubdiffcontact", "nsubdiff", "m1"), ("psubdiffcontact", "psubdiff", "m1"),
    ("polycontact", "poly", "m1"), ("gatecontact", "ntransistor", "m1"),
    ("fieldcontact", "rpoly", "m1"),
    ("via1", "m1", "m2"), ("via2", "m2", "m3"), ("via3", "m3", "m4"), ("via4", "m4", "mtop"),
]
# (plane, metal type, the via type homed on the plane, the via's GDS layer)
METALS = [("metal1", "m1", "via1", "v1"), ("metal2", "m2", "via2", "v2"),
          ("metal3", "m3", "via3", "v3"), ("metal4", "m4", "via4", "v4"),
          ("metaltop", "mtop", None, None)]
# GDS layers the core planes consume; every other drawn layer gets a plane of its own.
CORE_LAYERS = {"nw", "dnw", "nd", "pd", "po", "co", "m1", "v1", "m2", "v2", "m3", "v3", "m4",
               "v4", "mtop", "pad", "sab", "nsel", "psel", "gate", "ntap", "ptap"}
GENERATED_REBUILT = ("gate", "ntap", "ptap")  # read as booleans of the drawn layers instead

# Type groups: the Magic image of each drawn layer of the active plane.
ND = ["ndiff", "nsubdiff", "rndiff", "ntransistor", "ndcontact", "nsubdiffcontact"]
PD = ["pdiff", "psubdiff", "rpdiff", "ptransistor", "pdcontact", "psubdiffcontact"]
GATE = ["ntransistor", "ptransistor", "gatecontact"]
DF = [*ND, *PD, "gatecontact"]
PO = ["poly", "rpoly", "ntransistor", "ptransistor", "polycontact", "gatecontact"]
CO = ["ndcontact", "pdcontact", "nsubdiffcontact", "psubdiffcontact", "polycontact",
      "gatecontact", "fieldcontact"]
DF_OFF_GATE = [t for t in DF if t not in GATE]
PO_OFF_GATE = ["poly", "rpoly", "polycontact"]
# Types inside nw by construction; the other ND/PD types, transistors aside, lie outside.
IN_NW = {"nsubdiff", "nsubdiffcontact", "pdiff", "pdcontact", "rpdiff"}
ALIASES: dict[str, list[str]] = {"allnd": ND, "allpd": PD, "alldf": DF, "allpoly": PO,
                                 "allgate": GATE, "allco": CO}
# Display styles (from Magic's mos display style file); DRC does not use them.
STYLES = {"nwell": "nwell", "dnwell": "cwell", "ndiff": "ndiffusion", "pdiff": "pdiffusion",
          "nsubdiff": "ndiff_in_nwell", "psubdiff": "pdiff_in_pwell", "rndiff": "ndiffusion",
          "rpdiff": "pdiffusion", "poly": "polysilicon", "rpoly": "poly_resist",
          "ntransistor": "ntransistor", "ptransistor": "ptransistor",
          "ndcontact": "ncontact", "pdcontact": "pcontact", "nsubdiffcontact": "ncontact",
          "psubdiffcontact": "pcontact", "polycontact": "poly_contact",
          "gatecontact": "error_waffle", "fieldcontact": "error_waffle",
          "m1": "metal1", "via1": "via1", "m2": "metal2", "via2": "via2", "m3": "metal3",
          "via3": "via3", "m4": "metal4", "via4": "via4", "mtop": "metal5",
          "pad": "overglass", "sab": "silicide_block", "nsel": "nselect", "psel": "pselect"}

# The Magic types of each layer expression the rule table uses, keyed by `str(expr)`.
EXPR_TYPES: dict[str, list[str]] = {
    "nw": ["nwell"], "dnw": ["dnwell"], "nd": ND, "pd": PD, "nd|pd": DF, "po": PO,
    "gate": GATE, "co": CO, "sab": ["sab"], "pad": ["pad"],
    **{metal: [f"*{metal}"] for _, metal, _, _ in METALS},
    **{cut: [via] for _, _, via, cut in METALS if via},
    # approximation: the transistor type follows the diffusion, these rules the well
    "gate-nw": ["ntransistor"], "gate&nw": ["ptransistor"],
    "co&po": ["polycontact", "gatecontact"], "po&sab": ["rpoly"],
    "(nd|pd)&sab": ["rndiff", "rpdiff"], "po-(nd|pd)": PO_OFF_GATE,
}
# cifoutput style gds: each GDS layer and the types it is written from.
OUTPUT: dict[str, list[str]] = {
    "nw": ["nwell"], "dnw": ["dnwell"], "nd": ND, "pd": PD, "po": PO, "co": CO,
    **{metal: [f"*{metal}"] for _, metal, _, _ in METALS},
    **{cut: [via] for _, _, via, cut in METALS if via},
    "pad": ["pad"], "sab": ["sab"], "nsel": ["nsel"], "psel": ["psel"], "gate": GATE,
    "ntap": ["nsubdiff", "nsubdiffcontact"], "ptap": ["psubdiff", "psubdiffcontact"],
}


def plane_of(magic_type: str) -> str:
    """The home plane of a type (or `*metal` group) of the core model."""
    name = magic_type.lstrip("*")
    if name == "nwell":
        return "well"
    if name == "dnwell":
        return "dnw"
    if name in ACTIVE:
        return "active"
    for plane, metal, via, _ in METALS:
        if name in (metal, via):
            return plane
    if name in ("pad", "sab"):
        return name
    if name in ("nsel", "psel"):
        return "select"
    raise ValueError(f"no plane for Magic type {magic_type!r}")


def images_on(plane: str) -> list[str]:
    """The non-contact type of a metal plane and every contact with an image on it."""
    metal = next(m for p, m, _, _ in METALS if p == plane)
    contacts = [c for c, lo, up in CONTACTS if plane in (plane_of(lo), plane_of(up))]
    return [metal, *contacts]


# --- values and why strings


def nm(value: Decimal) -> int:
    """A length in um as an exact integer number of nanometres."""
    units = value * NM
    if units != units.to_integral_value():
        raise ValueError(f"{value} um is not a whole number of nanometres")
    return int(units)


def nm2(value: Decimal) -> int:
    """An area in um2 as an exact integer number of square nanometres."""
    units = value * NM * NM
    if units != units.to_integral_value():
        raise ValueError(f"{value} um2 is not a whole number of square nanometres")
    return int(units)


def _num(value: Decimal) -> str:
    return f"{value.normalize():f}"


def why(row: RuleRow) -> str:
    """`"<id>: <kind> <layers> <value> <unit>"`, quoted. Magic substitutes `%` sequences in
    why strings, and the string is double-quoted, so neither may appear."""
    parts = [row.kind, ", ".join(str(e) for e in row.layers)]
    if row.value is not None:
        parts.append(f"{_num(row.value)} {row.unit}")
    text = f"{row.id}: {' '.join(p for p in parts if p)}"
    if '"' in text or "%" in text:
        raise ValueError(f"{row.id}: why text {text!r} has a quote or a percent sign")
    return f'"{text}"'


def _list(types: Sequence[str]) -> str:
    """A Magic type list; a whole group is written as its alias."""
    for alias, members in ALIASES.items():
        if list(types) == members:
            return alias
    return ",".join(types)


def _not(types: Sequence[str], plane: str) -> str:
    return f"~({_list(types)})/{plane}"


def _minus(types: Sequence[str], drop: Sequence[str]) -> list[str]:
    return [t for t in types if t not in drop]


# --- rule emission

# Distances of the rules that report every edge between two types ("0" OK types). Magic keeps
# one rule per edge, distance and OK types and drops the others with their why strings, so
# rules that may share an edge get distinct distances: 1 for the topology rules (co.in,
# co.no.gate, co.no.butt), 2 and 3 for the straddling cuts of df.e.co and po.e.co.
STRADDLE = {"nd|pd": 2, "po": 3}


@dataclass
class _Tech:
    """The state of one generation: the process (field values), the minimum widths (area
    horizons) and the CIF layers of the `drc` cifoutput style, each defined once."""

    process: Process
    widths: dict[str, int]
    cif: list[str] = field(default_factory=list)
    cif_names: set[str] = field(default_factory=set)

    def value(self, path: str) -> Decimal:
        rule = self.process.rules.get(path.removeprefix("rules."))
        if not path.startswith("rules.") or rule is None or rule.value is None:
            raise ValueError(f"field {path!r} has no value")
        return rule.value

    def templayer(self, name: str, comment: str, ops: list[str]) -> str:
        """Define CIF layer `c_<name>` (`ops[0]` its starting types or layers, empty for
        none) once and return its name. The prefix keeps CIF layer names apart from type
        names: a CIF layer named like a type shadows the type in later operations."""
        name = f"c_{name}"
        if name not in self.cif_names:
            self.cif_names.add(name)
            self.cif += [f" # {comment}", f" templayer {name} {ops[0]}".rstrip(),
                         *(f"  {op}" for op in ops[1:])]
        return name


Emitted = tuple[list[str], list[str]]  # (comment lines: what Magic measures, rule lines)


def _types(row: RuleRow, index: int) -> list[str]:
    key = str(row.layers[index])
    if key not in EXPR_TYPES:
        raise ValueError(f"{row.id}: no Magic types for layer expression {key!r}")
    return list(EXPR_TYPES[key])


def _arity(row: RuleRow, n: int) -> None:
    if len(row.layers) != n:
        raise ValueError(f"{row.id}: {row.kind} takes {n} layer(s), got {len(row.layers)}")


def _value(row: RuleRow) -> Decimal:
    if row.value is None:
        raise ValueError(f"{row.id}: {row.kind} needs a value")
    return row.value


def _min_width(row: RuleRow, t: _Tech) -> Emitted:
    _arity(row, 1)
    return (["width: every region of the types narrower than the value (contact images",
             "count as metal, as the metal drawn over a cut)"],
            [f"width {_list(_types(row, 0))} {nm(_value(row))} {why(row)}"])


def _gate_length(row: RuleRow, t: _Tech) -> Emitted:
    _arity(row, 1)
    (gate,) = _types(row, 0)
    diff = _minus(ND if gate == "ntransistor" else PD, GATE)
    return ([f"gate length: from every edge between source/drain diffusion and {gate} (the",
             "gate edges on po edges) the gate must reach the value. Approximation: the",
             "transistor type follows the diffusion (po over nd or pd), the rule the well",
             "(gate-nw, gate&nw); a gate edge on space (flush diffusion) is not measured"],
            [f"edge4way {_list(diff)} {gate} {nm(_value(row))} allgate 0 0 {why(row)}"])


def _min_space(row: RuleRow, t: _Tech) -> Emitted:
    v = nm(_value(row))
    if len(row.layers) == 1:
        types = _list(_types(row, 0))
        return (["spacing: different regions of the types (or a notch) closer than the",
                 "value; touching regions are one region"],
                [f"spacing {types} {types} {v} touching_ok {why(row)}"])
    _arity(row, 2)
    a, b = _types(row, 0), _types(row, 1)
    if row.id in BUTTING_ALLOWED:
        return (["spacing: the two layers closer than the value; touching (butting) is",
                 "allowed (touching_ok, both on the active plane)"],
                [f"spacing {_list(a)} {_list(b)} {v} touching_ok {why(row)}"])
    comments = ["spacing: the two layers closer than the value, touching or overlapping",
                "included (touching_illegal)"]
    if a == ["nwell"]:
        b = _minus(b, [*IN_NW, *GATE])
        comments += ["the diffusion types inside nw by construction overlap it legally and",
                     "are left out, and so are the transistors, which may sit on either side",
                     "of the well: their source/drain diffusion carries the check"]
    elif a == ["sab"]:
        comments += ["Approximation: a cut inside sab is reported too (KLayout measures",
                     "facing outside edges only)"]
    return comments, [(f"spacing {_list(_minus(a, b))} {_list(b)} {v} touching_illegal "
                      f"{why(row)}")]


def _field_poly_space(row: RuleRow, t: _Tech) -> Emitted:
    _arity(row, 2)
    if row.edge_layer != "gate":
        raise ValueError(f"{row.id}: edges = 'exclude' is supported for gate only")
    poly, v = _types(row, 0), nm(_value(row))
    return (["field poly to diffusion: from every edge between field poly and a non-poly",
             "type (so not the gate ends, which border a transistor), no diffusion within",
             "the value; the constraint extends round convex corners (corner types: not",
             "poly) but not past a gate end, so a transistor's own end cap passes"],
            [(f"edge4way {_list(poly)} {_not(PO, 'active')} {v} {_not(DF, 'active')} "
             f"{_not(PO, 'active')} {v} {why(row)}")])


def _gate_and_endcap_space(row: RuleRow, t: _Tech) -> Emitted:
    """`nd.s.pgate`, `pd.s.ngate`: diffusion to the opposite gate and its end-cap poly."""
    _arity(row, 2)
    (diff_name,) = row.layers[0].names()
    diff = ND if diff_name == "nd" else PD
    gate, own = ("ptransistor", PD) if diff_name == "nd" else ("ntransistor", ND)
    v = nm(_value(row))
    cap = t.value("rules.po.x.df")
    return ([f"{diff_name} to the opposite gate ({gate}) and its end-cap poly (po within",
             f"{_num(cap)} um of the gate): a spacing to {gate}, and from each gate end",
             f"(edge from {gate} to poly) no {diff_name} within the value plus the end cap,",
             "the zone extended sideways by the value where the gate's own source/drain is",
             "beside the end. Approximation: a Manhattan zone over the end cap's straight",
             "extension; the transistor type follows the diffusion, the rule the well"],
            [f"spacing {_list(diff)} {gate} {v} touching_illegal {why(row)}",
             (f"edge4way {gate} {_list(PO_OFF_GATE)} {v + nm(cap)} {_not(diff, 'active')} "
             f"{_list(_minus(own, GATE))} {v} {why(row)}")])


def _unrelated_space(row: RuleRow, t: _Tech) -> Emitted:
    """`sab.s.df`, `sab.s.po`: sab to the diffusion or poly shapes not interacting with sab."""
    _arity(row, 2)
    second = row.layers[1]
    if not isinstance(second, Unrelated) or str(second.b) != "sab" or str(row.layers[0]) != "sab":
        raise ValueError(f"{row.id}: unrelated spacing is supported from sab to x.unrelated(sab)")
    key = str(second.a)
    if key not in EXPR_TYPES:
        raise ValueError(f"{row.id}: no Magic types for layer expression {key!r}")
    types = EXPR_TYPES[key]
    name = "df" if types == DF else key
    sab = t.templayer("sab", "sab", ["sab"])
    on = t.templayer(f"{name}_on_sab", f"the {name} regions overlapping sab",
                     ["", f"bloat-all sab {_list(types)}"])
    off = t.templayer(f"{name}_off_sab", f"the {name} regions not overlapping sab",
                      [_list(types), f"and-not {on}"])
    return ([f"CIF check: sab to the {name} regions that do not overlap sab (bloat-all from",
             "sab selects the connected regions that do), closer than the value, touching",
             "included. Approximation: a region only touching sab counts as unrelated"],
            [f"cifspacing {sab} {off} {nm(_value(row))} touching_illegal {why(row)}"])


def _min_enclosure(row: RuleRow, t: _Tech) -> Emitted:
    _arity(row, 2)
    v = nm(_value(row))
    outer, inner = _types(row, 0), _types(row, 1)
    plane = plane_of(outer[0])
    if plane.startswith("metal"):
        cuts = [c for c in inner if c in images_on(plane)]
        return (["surround: the metal (the metal type and every contact image on its plane,",
                 "stacked contacts included) must surround the cut images by the value, so a",
                 "cut straddling the metal edge is reported. Approximation: absence_illegal,",
                 "a cut with no metal at all is reported too (KLayout does not; Magic counts",
                 "the cut image as metal, so the metal width rule reports it anyway)"],
                [f"surround ({_list(cuts)})/{plane} {outer[0]} {v} absence_illegal {why(row)}"])
    if plane == "active":
        # the cut types that lie on the outer layer by construction
        cuts = [c for c in inner if c in outer]
        others = _minus(CO, cuts)
        return (["surround: the cut types that lie on the outer layer by construction must be",
                 "surrounded by its other types by the value (absence_illegal). A cut",
                 "straddling the outer edge is split there into one of these and another cut",
                 "type: every edge between the two is an error (Magic's surround does not",
                 "measure across an edge between two contact types). A cut wholly outside",
                 "is another type and legal here"],
                [(f"surround {_list(cuts)} {_list(_minus(outer, cuts))} {v} absence_illegal "
                  f"{why(row)}"),
                 (f"edge4way {_list(cuts)} {_list(others)} {STRADDLE[str(row.layers[0])]} "
                  f"0 0 0 {why(row)}")])
    return (["surround: where the outer layer is present, it must surround the inner types",
             "by the value; an inner shape straddling the outer edge is reported, one wholly",
             "outside is legal (absence_ok, as the KLayout check)"],
            [f"surround {_list(inner)} {_list(outer)} {v} absence_ok {why(row)}"])


def _side_enclosure(row: RuleRow, t: _Tech) -> Emitted:
    _arity(row, 2)
    inner = _types(row, 1)
    layer = PO if inner == ["rpoly"] else DF
    return (["enclosure of the sides only: from every edge between the unsilicided type and",
             "a type of another layer (the sides; the crossing ends border the silicided",
             "part of the same layer and are not checked) the region within the value must",
             "be sab (checked on the sab plane). Approximation: an end flush with the sab",
             "edge is reported here as well as by the extension rule"],
            [(f"edge4way {_list(inner)} {_not(layer, 'active')} {nm(_value(row))} sab 0 0 "
             f"{why(row)} sab")])


def _gate_extension(row: RuleRow, t: _Tech, a: str) -> Emitted:
    v = nm(_value(row))
    if a == "nd|pd":
        beyond, ok, partner, partner_name = DF_OFF_GATE, DF, PO_OFF_GATE, "po"
    elif a == "po":
        beyond, ok, partner, partner_name = PO_OFF_GATE, PO, DF_OFF_GATE, "df"
    else:
        raise ValueError(f"{row.id}: an extension beyond gate needs po or df, not {a}")
    strip = t.templayer("gate_space_strip", "1 nm strips beside the gate edges on space",
                        ["allgate", "bloat-or allgate * 1 alldf,allpoly 0", "and-not allgate"])
    tag = "df" if a == "nd|pd" else "po"
    flush = t.templayer(f"{tag}_flush_gate", f"{tag} ending flush with the {partner_name} "
                        f"edge at a gate: a space strip beside the {partner_name} part "
                        "outside the gate", [strip, "grow 2", f"and {_list(partner)}"])
    return ([f"extension beyond the gate: from every edge between a transistor and {a}",
             f"outside the gate, {a} must continue for the value; a CIF check adds {a}",
             f"ending flush with the {partner_name} edge (a gate edge on space whose strip",
             f"touches {partner_name} outside the gate). Approximation: Magic tells a gate's",
             "sides apart only by the neighbouring type, so an end inside the partner is",
             "measured as a side, against the other extension rule and the gate length;",
             f"{a} ending inside {partner_name} is not reported as {row.id}"],
            [f"edge4way allgate {_list(beyond)} {v} {_list(ok)} 0 0 {why(row)}",
             f"cifmaxwidth {flush} 0 bend_illegal {why(row)}"])


def _min_extension(row: RuleRow, t: _Tech) -> Emitted:
    _arity(row, 2)
    a, b = str(row.layers[0]), str(row.layers[1])
    if b == "gate":
        return _gate_extension(row, t, a)
    if b != "sab":
        raise ValueError(f"{row.id}: no Magic extension rule beyond {b}")
    inner = EXPR_TYPES["po&sab" if a == "po" else f"({a})&sab"]
    layer = PO if a == "po" else DF
    outside = _minus(layer, inner)
    tag = "po" if a == "po" else "df"
    flush = t.templayer(f"{tag}_flush_sab", f"unsilicided {tag} ending flush with the sab "
                        "edge: the 1 nm strip beside its edges on other layers, outside sab",
                        [_list(inner), f"bloat-or {_list(inner)} * 1 {_list(layer)} 0",
                         f"and-not {_list(inner)}", "and-not sab"])
    return ([f"extension beyond sab: from every edge between unsilicided and silicided {a}",
             f"(the sab crossing) the silicided {a} must continue for the value; a CIF",
             f"check adds unsilicided {a} ending flush with the sab edge (an edge rule on",
             "the same edges would be merged by Magic into the side enclosure rule)"],
            [(f"edge4way {_list(inner)} {_list(outside)} {nm(_value(row))} {_list(outside)} "
              f"0 0 {why(row)}"),
             f"cifmaxwidth {flush} 0 bend_illegal {why(row)}"])


def _min_area(row: RuleRow, t: _Tech) -> Emitted:
    _arity(row, 1)
    area = nm2(_value(row))
    width = t.widths.get(str(row.layers[0]))
    if not width:
        raise ValueError(f"{row.id}: no min-width rule for {row.layers[0]} (area horizon)")
    horizon = max(width, -(-area // width))
    return ([f"area: regions smaller than the value (nm2); horizon {horizon} nm (the area",
             "over the layer's minimum width: the longest a region too small can be)"],
            [f"area {_list(_types(row, 0))} {area} {horizon} {why(row)}"])


def _exact_size(row: RuleRow, t: _Tech) -> Emitted:
    _arity(row, 1)
    types, v = _list(_types(row, 0)), nm(_value(row))
    return (["exact size: no cut narrower than the value (width), nor wider in either",
             "direction (maxwidth both); with both, a cut is the square of the value"],
            [f"width {types} {v} {why(row)}", f"maxwidth {types} {v} both {why(row)}"])


def _forbidden_type(magic_type: str, what: str) -> Callable[[RuleRow, _Tech], Emitted]:
    def emit(row: RuleRow, t: _Tech) -> Emitted:
        return ([f"{what}: every edge of {magic_type} on a non-cut type is an error (no type",
                 "is OK beyond it); its edges on other cut types are left to the enclosure",
                 "rules' straddle checks, which a rule on the same edges would mask"],
                [f"edge4way {magic_type} {_not(CO, 'active')} 1 0 0 0 {why(row)}"])
    return emit


def _co_on_butt(row: RuleRow, t: _Tech) -> Emitted:
    _arity(row, 3)
    n, p = ["ndcontact", "nsubdiffcontact"], ["pdcontact", "psubdiffcontact"]
    return (["contact straddling an nd/pd butting edge: the cut is split into an n- and a",
             "p-contact type there, and every edge between the two is an error"],
            [f"edge4way {_list(n)} {_list(p)} 1 0 0 0 {why(row)}"])


def _sab_on_gate(row: RuleRow, t: _Tech) -> Emitted:
    _arity(row, 2)
    t.templayer("sab", "sab", ["sab"])
    overlap = t.templayer("sab_on_gate", "sab over a transistor", ["sab", "and allgate"])
    return (["CIF check: any overlap of sab and a transistor"],
            [f"cifmaxwidth {overlap} 0 bend_illegal {why(row)}"])


@dataclass(frozen=True)
class MagicKind:
    """What Magic emits for a key: `rule` describes it, or starts with "KLayout-only: " and
    gives the reason; `emit` writes it (None: KLayout-only)."""

    rule: str
    emit: Callable[[RuleRow, _Tech], Emitted] | None = None


MAGIC_KINDS: dict[str, MagicKind] = {
    "min-width": MagicKind("width <types> <v>", _min_width),
    "condition": MagicKind(
        "KLayout-only: Magic has no width rule conditional on the length of an edge"),
    "gate-length": MagicKind(
        "edge4way <source/drain diffusion> <transistor> <v> allgate 0 0", _gate_length),
    "min-space": MagicKind(
        "spacing <a> <a> <v> touching_ok; two layers: spacing <a> <b> <v> touching_illegal, "
        "touching_ok where butting is allowed", _min_space),
    "min-space:edges=exclude": MagicKind(
        "edge4way <field poly> ~(allpoly) <v> ~(alldf) ~(allpoly) <v>", _field_poly_space),
    "min-space:gate+endcap": MagicKind(
        "spacing <diffusion> <opposite transistor> <v> touching_illegal and edge4way "
        "<transistor> <field poly> <v + end cap> ~(<diffusion>) <its source/drain> <v>",
        _gate_and_endcap_space),
    "min-space:unrelated": MagicKind(
        "CIF: cifspacing sab <regions not overlapping sab (bloat-all)> <v> touching_illegal",
        _unrelated_space),
    "min-enclosure": MagicKind(
        "surround <inner> <outer> <v> absence_ok (absence_illegal for cuts on active)",
        _min_enclosure),
    "min-enclosure:edges=sides": MagicKind(
        "edge4way <unsilicided type> ~(<its layer>) <v> sab 0 0 (on the sab plane)",
        _side_enclosure),
    "min-extension": MagicKind(
        "edge4way <inside part> <outside part> <v> <layer> 0 0; beyond gate also CIF flush "
        "and inside-end checks (cifmaxwidth 0), beyond sab an edge4way for the flush end",
        _min_extension),
    "min-area": MagicKind("area <types> <v nm2> <horizon>", _min_area),
    "exact-size": MagicKind("width <cut> <v> and maxwidth <cut> <v> both", _exact_size),
    "max-distance": MagicKind(
        "KLayout-only: Magic has no rule for the distance to the nearest shape of a layer"),
    "topology:co_on_field": MagicKind(
        "edge4way fieldcontact ~(allco) 1 0 0 0",
        _forbidden_type("fieldcontact", "contact on field oxide")),
    "topology:co_on_gate": MagicKind(
        "edge4way gatecontact ~(allco) 1 0 0 0",
        _forbidden_type("gatecontact", "contact on a gate")),
    "topology:co_on_butt": MagicKind("edge4way <n contacts> <p contacts> 1 0 0 0", _co_on_butt),
    "topology:sab_on_gate": MagicKind("CIF: cifmaxwidth (sab and allgate) 0", _sab_on_gate),
    "topology:co_s_butt": MagicKind(
        "KLayout-only: KLayout-only in the rule table since Task 7; a space to the nd/pd "
        "butting edge (an edge, not a layer) is not attempted in Magic in Phase 0"),
    "topology:v4_array": MagicKind("KLayout-only: Magic cannot count the cuts of a cluster"),
    "topology:grid": MagicKind(
        "KLayout-only: KLayout-only in the rule table since Task 7; Magic's off_grid rule "
        "is not attempted in Phase 0"),
    "topology:angle": MagicKind(
        "KLayout-only: Magic stores only Manhattan and 45-degree geometry"),
    "topology:cut_ortho": MagicKind(
        "KLayout-only: Magic stores only Manhattan and 45-degree geometry"),
}


def magic_key(row: RuleRow) -> str:
    """The `MAGIC_KINDS` key of a row: its topology fixture, `condition`, `edges` or composed
    layers first, else its kind."""
    if row.fixture is not None:
        return f"topology:{row.fixture}"
    if row.condition is not None:
        return "condition"
    if row.edges is not None:
        return f"{row.kind}:edges={row.edges}"
    if row.kind == "min-space" and len(row.layers) == 2:
        second = str(row.layers[1])
        if ".unrelated(" in second:
            return "min-space:unrelated"
        if ".sized(" in second:
            return "min-space:gate+endcap"
    return row.kind


def _emit(row: RuleRow, t: _Tech) -> Emitted:
    key = magic_key(row)
    if key not in MAGIC_KINDS:
        raise ValueError(f"{row.id}: no Magic rule for {key!r}")
    kind = MAGIC_KINDS[key]
    if kind.emit is None:
        raise ValueError(f"{row.id}: lists magic in engines, but {kind.rule}")
    return kind.emit(row, t)


# --- the file


def _planes(process: Process, variant: str) -> list[tuple[str, list[str]]]:
    layers = selected_layers(process, variant)
    planes = [("well", ["nwell"])]
    if "dnw" in layers:
        planes.append(("dnw", ["dnwell"]))
    planes.append(("active", list(ACTIVE)))
    planes += [(plane, [metal, *([via] if via else [])]) for plane, metal, via, _ in METALS]
    planes += [("pad", ["pad"]), ("sab", ["sab"]), ("select", ["nsel", "psel"])]
    planes += [(name, [name]) for name, layer in layers.items()
               if name not in CORE_LAYERS and layer.kind == "drawn"]
    return planes


def _source(magic_type: str) -> list[str]:
    """The cifinput operations of a type."""
    if magic_type in ACTIVE:
        return ACTIVE[magic_type]
    simple = {"nwell": "nw", "dnwell": "dnw"}
    for _, metal, via, cut in METALS:
        simple[metal] = metal
        if via:
            simple[via] = cut
    return [simple.get(magic_type, magic_type)]


def _cifinput(layers, planes) -> list[str]:
    lines = ["cifinput", "style gds", " scalefactor 1 nanometers", ""]
    for _, types in planes:
        for magic_type in types:
            ops = _source(magic_type)
            lines += [f" layer {magic_type} {ops[0]}", *(f"  {op}" for op in ops[1:])]
    rebuilt = [n for n in GENERATED_REBUILT if n in layers]
    lines += ["", f" # {', '.join(rebuilt)}: generated, rebuilt above from the drawn layers",
              *(f" ignore {n}" for n in rebuilt), ""]
    lines += [f" calma {n} {layer.gds[0]} {layer.gds[1]}" for n, layer in layers.items()]
    return [*lines, "end"]


def _cifoutput(layers, cif: list[str]) -> list[str]:
    lines = ["cifoutput", "style gds", " scalefactor 1 nanometers", ""]
    for name, layer in layers.items():
        lines += [f" layer {name} {_list(OUTPUT.get(name, [name]))}",
                  f"  calma {layer.gds[0]} {layer.gds[1]}"]
    lines += ["", f"style {CIF_DRC}",
              " # the CIF layers of the drc section's cif checks (not for GDS output)",
              " scalefactor 1 nanometers", *cif]
    return [*lines, "end"]


def _drc(table: RuleTable, t: _Tech) -> list[str]:
    head = ["drc", " # KLayout-only rules (not checked by Magic):"]
    for row in table.checkable():
        if row.engines == ["klayout"]:
            kind = MAGIC_KINDS.get(magic_key(row))
            reason = kind.rule.removeprefix("KLayout-only: ") if kind else "no Magic rule"
            head.append(f" #   {row.id}: {reason}")
    body = []
    for row in table.checkable():
        if "magic" not in row.engines:
            continue
        comments, rules = _emit(row, t)
        body += ["", f" # {row.id}", *(f" # {c}" for c in comments), *(f" {r}" for r in rules)]
    return [*head, "", f" cifstyle {CIF_DRC}", *body, "end"]


def tech_text(table: RuleTable, process: Process, variant: str) -> str:
    layers = selected_layers(process, variant)
    widths = {str(r.layers[0]): nm(r.value) for r in table.rows
              if r.kind == "min-width" and r.condition is None and len(r.layers) == 1}
    t = _Tech(process, widths)
    drc = _drc(table, t)  # first: it defines the CIF layers of the drc style
    planes = _planes(process, variant)
    return "\n".join([
        SPDX,
        f"# Magic technology file of variant {variant}, for design-rule checking only. One",
        "# internal unit is 1 nm: every distance in the drc section is in nanometres.",
        f"# Written by {GENERATOR} (ws180g-magic-tech) from the rule table: generated, do not",
        "# edit.",
        "",
        "tech", " format 35", f" {variant}", "end", "",
        "version", " version 0.0.0",
        f' description "wafer.space 180 nm generic PDK, variant {variant}: DRC only"', "end",
        "",
        "planes", *(f" {p}" for p, _ in planes), "end", "",
        "types", *(f" {p} {ty}" for p, types in planes for ty in types), "end", "",
        "contact", *(f" {c} {lo} {up}" for c, lo, up in CONTACTS), " stackable", "end", "",
        "aliases", *(f" {a} {','.join(m)}" for a, m in ALIASES.items()), "end", "",
        "styles", " styletype mos",
        *(f" {ty} {STYLES.get(ty, 'comment')}" for _, types in planes for ty in types),
        "end", "",
        "compose", "end", "",
        "connect", "end", "",
        *_cifoutput(layers, t.cif), "",
        *_cifinput(layers, planes), "",
        *drc, "",
        "# Extraction is Phase 1. The section is present and empty because Magic falls back to",
        "# its default technology at startup when a technology file lacks it.",
        "extract", "end", ""])


def magicrc_text(variant: str) -> str:
    return "\n".join([
        SPDX,
        f"# Magic startup file of variant {variant}: loads {variant}.tech from the directory",
        f"# of this file. Run: magic -dnull -noconsole -rcfile <dir>/{variant}.magicrc",
        f"# Written by {GENERATOR} (ws180g-magic-tech): generated, do not edit.",
        f"tech load [file join [file dirname [info script]] {variant}.tech]",
        "cif istyle gds",
        "cif ostyle gds",
        "drc euclidean on",
        "units internal",
        "snap internal",
        ""])


def write_magic_tech(table: RuleTable, process: Process, variant: str,
                     out_dir: Path) -> list[Path]:
    """Write `<variant>.tech` and `<variant>.magicrc` into `out_dir` and return their paths.
    Raises `ValueError` for a row that lists Magic but that Magic cannot check."""
    texts = {f"{variant}.tech": tech_text(table, process, variant),
             f"{variant}.magicrc": magicrc_text(variant)}
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, text in texts.items():
        path = out_dir / name
        path.write_text(text, encoding="utf-8")
        paths.append(path)
    return paths


def main(argv: Sequence[str] | None = None) -> int:
    """`ws180g-magic-tech [--variant V] --out DIR`: write the Magic technology of variant V
    (default ws180g005) into DIR and print the paths."""
    from ws180g_process.load import load_process

    parser = argparse.ArgumentParser(prog="ws180g-magic-tech",
                                     description=__doc__.splitlines()[0])
    parser.add_argument("--variant", default=DEFAULT_VARIANT,
                        help=f"process variant (default: {DEFAULT_VARIANT})")
    parser.add_argument("--out", type=Path, required=True, help="output directory")
    args = parser.parse_args(argv)
    process = load_process()
    table = RuleTable.from_process(process, args.variant)
    for path in write_magic_tech(table, process, args.variant, args.out):
        print(path)
    return 0
