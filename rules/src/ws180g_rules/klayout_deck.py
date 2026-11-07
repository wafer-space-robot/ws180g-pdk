# SPDX-License-Identifier: Apache-2.0
"""The KLayout DRC deck, generated from the rule table so that every rule KLayout checks
appears exactly once as a check.

`write_klayout_deck` writes three files: `<variant>_checks.rb` holds the layer inputs, the
derived layers and one check per rule; `<variant>.drc` (`klayout -b -r <variant>.drc -rd
input=<gds> -rd report=<lyrdb>`) runs it on one layout and `<variant>_batch.drc` (`-rd
list=<file of GDS paths, one per line> -rd out=<dir>`) on every layout of a list in one
KLayout process, writing `<dir>/<basename>.lyrdb` per input. Both entry points
`instance_eval` the checks file inside the DRC engine (a `require_relative` would evaluate it
outside the engine, where the DSL is not defined). The input GDS must already carry the
generated layers (`ws180g_layergen.derive_file`); the deck reads them as plain inputs.

Each check's idiom is commented in the generated file with what it measures; the Task 14/15
fixtures prove them. The output is deterministic and carries no date.
"""

import argparse
import re
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path

from ws180g_process.model import Layer, Process

from ws180g_rules.layer_expr import (
    Difference,
    Intersection,
    LayerExpr,
    Name,
    Sized,
    Union,
    Unrelated,
    parse_layer_expr,
)
from ws180g_rules.table import DEFAULT_VARIANT, RuleRow, RuleTable

GENERATOR = "ws180g_rules.klayout_deck"
SPDX = "# SPDX-License-Identifier: Apache-2.0"
# Two-layer spaces whose touching (butted) pairs are legal: GF DF.3b allows nd/pd butting.
BUTTING_ALLOWED = frozenset({"df.s.np"})
_LENGTH_CONDITION = re.compile(r"^\s*length\s*>\s*(\d+(?:\.\d+)?)\s*$")
_MAX_NAME = 32


def variant_layers(process: Process, variant: str) -> dict[str, Layer]:
    """The layers a deck of `variant` reads, in `layers.toml` order: those of the variant or
    of a variant it contains, and those of the optional modules (no variant)."""
    allowed = {variant, *process.variants[variant].contains}
    return {n: layer for n, layer in process.layers.items()
            if layer.variant is None or layer.variant in allowed}


def _num(value: Decimal) -> str:
    """A Ruby float literal for `value`: `0.27`, `10.0`."""
    text = f"{value.normalize():f}"
    return text if "." in text else f"{text}.0"


def _um(value: Decimal) -> str:
    return f"{_num(value)}.um"


def _ruby_str(text: str) -> str:
    """A single-quoted Ruby string: no interpolation, only `\\` and `'` escaped."""
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"


class _Deck:
    """The definitions section of the checks file: one Ruby variable per distinct derived
    layer expression or helper, assigned once, in order of first use."""

    def __init__(self, process: Process, layers: dict[str, Layer]) -> None:
        self.process = process
        self.layers = layers
        self.names = set(layers)
        self.vars: dict[LayerExpr, str] = {}
        self.helpers: dict[str, str] = {}
        self.lines: list[str] = []
        self.aliases = {parse_layer_expr(text, process.aliases, process.layers): name
                        for name, text in sorted(process.aliases.items())}

    def _name(self, wanted: str) -> str:
        """`wanted` if free, else `wanted_2`, `wanted_3`...; a name longer than `_MAX_NAME`
        becomes `expr_1`, `expr_2`... (the comment above the assignment shows the
        expression)."""
        if len(wanted) > _MAX_NAME:
            wanted = "expr"
            self.names.add(wanted)  # never bare `expr`: number every long expression
        name, n = wanted, 1
        if name in self.names:
            n, name = 1, f"{wanted}_1"
        while name in self.names:
            n += 1
            name = f"{wanted}_{n}"
        self.names.add(name)
        return name

    def parse(self, text: str) -> LayerExpr:
        """A layer name or alias (`df`) as a parsed expression."""
        return parse_layer_expr(text, self.process.aliases, self.process.layers)

    def field(self, path: str) -> Decimal:
        """The value of a process field given by dotted path (`rules.po.x.df`)."""
        if not path.startswith("rules."):
            raise ValueError(f"cannot read field {path!r}: only rules.<id> fields are values")
        rule = self.process.rules.get(path.removeprefix("rules."))
        if rule is None or rule.value is None:
            raise ValueError(f"field {path!r} has no value")
        return rule.value

    def expr(self, expr: LayerExpr) -> str:
        """The Ruby variable holding `expr`, defining it (and its operands) on first use."""
        if isinstance(expr, Name):
            if expr.name not in self.layers:
                raise ValueError(f"layer {expr.name!r} is not an input of this variant")
            return expr.name
        if expr in self.vars:
            return self.vars[expr]
        if isinstance(expr, (Union, Intersection, Difference, Unrelated)):
            a, b = self.expr(expr.a), self.expr(expr.b)
            op, word = {Union: ("|", "or"), Intersection: ("&", "and"),
                        Difference: ("-", "not"), Unrelated: (None, "unrelated")}[type(expr)]
            code = f"{a}.not_interacting({b})" if op is None else f"{a} {op} {b}"
            wanted = f"{a}_{word}_{b}"
        elif isinstance(expr, Sized):
            a = self.expr(expr.expr)
            code = f"{a}.sized({_um(self.field(expr.field))})"
            wanted = f"{a}_sized_{expr.field.removeprefix('rules.').replace('.', '_')}"
        else:
            raise TypeError(f"no Ruby rendering for {type(expr).__name__}")
        name = self._name(self.aliases.get(expr, wanted))
        self.vars[expr] = name
        self.lines += [f"# {expr}", f"{name} = {code}"]
        return name

    def helper(self, wanted: str, code: str, comment: str) -> str:
        """A variable for a non-expression helper (edge sets, clusters), defined once."""
        if code not in self.helpers:
            name = self._name(wanted)
            self.helpers[code] = name
            self.lines += [f"# {comment}", f"{name} = {code}"]
        return self.helpers[code]


Emitted = tuple[list[str], str]  # (comment lines on the idiom, Ruby check expression)


def _arity(row: RuleRow, n: int) -> list[LayerExpr]:
    if len(row.layers) != n:
        raise ValueError(f"{row.id}: {row.kind} takes {n} layer(s), got {len(row.layers)}")
    return row.layers


def _value(row: RuleRow) -> Decimal:
    if row.value is None:
        raise ValueError(f"{row.id}: {row.kind} needs a value")
    return row.value


def _min_width(row: RuleRow, d: _Deck) -> Emitted:
    (layer,) = _arity(row, 1)
    a, v = d.expr(layer), _um(_value(row))
    if row.condition is None:
        return (["width: opposite edges of one polygon closer than the value, inside the",
                 "polygon (euclidian: corners measured as distances)"],
                f"{a}.width({v}, euclidian)")
    match = _LENGTH_CONDITION.match(row.condition)
    if match is None:
        raise ValueError(f"{row.id}: unsupported condition {row.condition!r}")
    n = _um(Decimal(match[1]))
    edges = d.helper(f"{a}_long_edges",
                     f"{a}.edges.with_length({n}, nil).without_length({n})",
                     f"edges of {a} longer than {match[1]} um (strictly: the exact length "
                     "is removed)")
    long = d.helper(f"{a}_long", f"{a}.interacting({edges})",
                    f"polygons of {a} with an edge longer than {match[1]} um")
    return ([f"condition {row.condition!r}: the width check applies to the polygons with an",
             "edge longer than the threshold. Approximation: the whole polygon is checked,",
             "short branches included, so the check is conservative"],
            f"{long}.width({v}, euclidian)")


def _gate_length(row: RuleRow, d: _Deck) -> Emitted:
    (layer,) = _arity(row, 1)
    g = d.expr(layer)
    sides = d.helper(f"{g}_po_edges", f"{g}.edges & {d.expr(d.parse('po'))}.edges",
                     f"edges of {g} that lie on po edges: the two sides of the gate across "
                     "which its length is measured")
    return (["gate length: width between the gate edges that lie on po edges, so the gate",
             "width (between the df edges) is not measured"],
            f"{sides}.width({_um(_value(row))}, euclidian)")


def _min_space(row: RuleRow, d: _Deck) -> Emitted:
    v = _um(_value(row))
    if len(row.layers) == 1:
        return (["space: facing edges of different polygons (or of a notch) closer than the",
                  "value, outside the polygons"],
                f"{d.expr(row.layers[0])}.space({v}, euclidian)")
    a, b = (d.expr(e) for e in _arity(row, 2))
    check = f"{a}.separation({b}, {v}, euclidian)"
    if row.id not in BUTTING_ALLOWED:
        return (["separation: facing outside edges of the two layers closer than the value"],
                check)
    return (["separation: facing outside edges of the two layers closer than the value;",
             "butting is allowed, so the touching pairs (distance 0, the shared edge) are",
             "removed with without_distance(0)"],
            f"{check}.without_distance(0)")


def _min_enclosure(row: RuleRow, d: _Deck) -> Emitted:
    outer, inner = (d.expr(e) for e in _arity(row, 2))
    v = _um(_value(row))
    if row.edges is None:
        return (["enclosure: inner edges inside the outer layer closer than the value to its",
                 "edges"],
                f"{outer}.enclosing({inner}, {v}, euclidian)")
    if row.edges != "sides":
        raise ValueError(f"{row.id}: unsupported edges {row.edges!r}")
    el = d.expr(d.parse(row.edge_layer))
    sides = d.helper(f"{inner}_{el}_sides", f"{inner}.edges & {el}.edges",
                     f"edges of {inner} that are {row.edge_layer} edges (the sides; the "
                     f"crossing ends lie on {outer} edges)")
    return ([f"enclosure of the sides only: the {row.edge_layer} edges of the inner layer",
             f"must be at least the value inside the {outer} edges; edges at 90 degrees",
             "(the crossing ends) are ignored by the check"],
            f"{sides}.enclosed({outer}.edges, {v}, euclidian)")


def _min_extension(row: RuleRow, d: _Deck) -> Emitted:
    a_expr, b_expr = _arity(row, 2)
    a = d.expr(a_expr)
    ab = d.expr(Intersection(a_expr, b_expr))
    cross = d.helper(f"{ab}_cross", f"{ab}.edges - {a}.edges",
                     f"edges of {ab} not on {a} edges: where {a} crosses out of {b_expr}")
    return ([f"extension: {a} must reach at least the value beyond each crossing edge of",
             f"{ab}; the crossing edges are checked as enclosed by the {a} edges (end cap)"],
            f"{cross}.enclosed({a}.edges, {_um(_value(row))}, euclidian)")


def _min_area(row: RuleRow, d: _Deck) -> Emitted:
    (layer,) = _arity(row, 1)
    return (["area: with_area(min, max) selects merged polygons with min <= area < max",
             "(um2), so an area equal to the value passes"],
            f"{d.expr(layer)}.with_area(0, {_num(_value(row))}.um2)")


def _exact_size(row: RuleRow, d: _Deck) -> Emitted:
    (layer,) = _arity(row, 1)
    a, value = d.expr(layer), _value(row)
    v = _um(value)
    return (["exact size: the cuts that are not squares, or whose area, bbox width or bbox",
             "height differs from the value; the OR merges the sub-checks so one wrong cut",
             "gives one marker"],
            (f"({a}.without_area({_num(value * value)}.um2) | {a}.non_squares | "
             f"{a}.without_bbox_width({v}) | {a}.without_bbox_height({v}))"))


def _max_distance(row: RuleRow, d: _Deck) -> Emitted:
    shapes, taps = (d.expr(e) for e in _arity(row, 2))
    return ([f"maximum distance: every part of {shapes} farther than the value from {taps}",
             "(the taps sized by the value; sizing approximates the euclidian distance with",
             "cut corners, which is conservative)"],
            f"({shapes} - {taps}.sized({_um(_value(row))}))")


# --- topology: one hand-written snippet per fixture name


def _co_on_field(row: RuleRow, d: _Deck) -> Emitted:
    co, inside = _arity(row, 2)
    return ([f"contacts on field: the parts of {co} outside {inside}"],
            d.expr(Difference(co, inside)))


def _overlap_snippet(what: str) -> Callable[[RuleRow, _Deck], Emitted]:
    def emit(row: RuleRow, d: _Deck) -> Emitted:
        a, b = _arity(row, 2)
        return ([f"{what}: the overlap of {a} and {b}"], d.expr(Intersection(a, b)))
    return emit


def _butt(row: RuleRow, d: _Deck) -> tuple[str, str, str]:
    co, nd, pd = (d.expr(e) for e in _arity(row, 3))
    butt = d.helper(f"{nd}_{pd}_butt", f"{nd}.edges & {pd}.edges",
                    f"the butting edges: {nd} edges that coincide with {pd} edges")
    inside = d.helper(f"{nd}_{pd}_butt_in_{co}", f"{butt}.inside_part({co})",
                      f"the parts of the butting edges inside {co} (not on its boundary)")
    return co, butt, inside


def _co_on_butt(row: RuleRow, d: _Deck) -> Emitted:
    co, _, inside = _butt(row, d)
    return ([f"contacts straddling a butting edge: {co} with a butting edge through its",
             "inside (a contact edge lying on the butting edge does not straddle)"],
            f"{co}.interacting({inside})")


def _co_s_butt(row: RuleRow, d: _Deck) -> Emitted:
    co, butt, inside = _butt(row, d)
    v = _um(_value(row))
    return ([f"space to the butting edge: {co} not straddling it that overlaps the zone within",
             "the value of a butting edge (the edges extended by the value on all four sides;",
             "beyond the edge ends the zone is square, which is conservative)"],
            f"{co}.not_interacting({inside}).overlapping({butt}.extended({v}, {v}, {v}, {v}))")


def _v4_array(row: RuleRow, d: _Deck) -> Emitted:
    mtop, v4 = (d.expr(e) for e in _arity(row, 2))
    size, space = d.field("rules.v4.size"), d.field("rules.v4.s")
    cuts = d.helper(f"{v4}_under_{mtop}", f"{v4}.interacting({mtop})", f"{v4} under {mtop}")
    clusters = d.helper(f"{v4}_clusters", f"{cuts}.sized({_um(space / 2)}).merged",
                        f"{v4} clusters: cuts sized by half of rules.v4.s and merged, so the "
                        "cuts of an array at up to the minimum space form one cluster")
    return (["v4 arrays: cuts of clusters with fewer than 4 cuts, or with a bbox narrower",
             "than two cuts (2 x rules.v4.size + rules.v4.s) in either direction.",
             "Approximation: cuts farther apart than rules.v4.s are separate clusters, and",
             "an L of 4 or more cuts passes"],
            (f"{cuts}.interacting({clusters}.interacting({cuts}, 1, 3) | "
             f"{clusters}.with_bbox_min(nil, {_um(2 * size + space)}))"))


def _drawn(d: _Deck) -> str:
    names = [n for n, layer in d.layers.items() if layer.kind == "drawn"]
    return d.helper("drawn_layers", f"[{', '.join(names)}]",
                    "the drawn input layers (the generated ones are written by layergen)")


def _grid(row: RuleRow, d: _Deck) -> Emitted:
    _arity(row, 0)
    g = _um(d.process.grid.value)
    return (["off-grid vertices of every drawn layer (generated layers are skipped: sizing",
             "a 45 degree edge in layergen may land off the grid)"],
            f"{_drawn(d)}.map {{ |l| l.ongrid({g}) }}.inject(:+)")


def _angle(row: RuleRow, d: _Deck) -> Emitted:
    _arity(row, 0)
    return (["edges of every drawn layer that are neither orthogonal nor at 45 degrees",
             "(edge angles are measured in -90..90 degrees)"],
            (f"{_drawn(d)}.map {{ |l| l.edges.without_angle(0).without_angle(90)"
             ".without_angle(45).without_angle(-45) }.inject(:+)"))


def _cut_ortho(row: RuleRow, d: _Deck) -> Emitted:
    (cuts,) = _arity(row, 1)
    return ([f"cuts that are not rectilinear: polygons of {cuts} with an edge that is not",
             "horizontal or vertical"],
            f"{d.expr(cuts)}.non_rectilinear")


TOPOLOGY: dict[str, Callable[[RuleRow, _Deck], Emitted]] = {
    "co_on_field": _co_on_field,
    "co_on_gate": _overlap_snippet("contacts on a gate"),
    "co_on_butt": _co_on_butt,
    "co_s_butt": _co_s_butt,
    "sab_on_gate": _overlap_snippet("silicide block on a gate"),
    "v4_array": _v4_array,
    "grid": _grid,
    "angle": _angle,
    "cut_ortho": _cut_ortho,
}

KINDS: dict[str, Callable[[RuleRow, _Deck], Emitted]] = {
    "min-width": _min_width,
    "gate-length": _gate_length,
    "min-space": _min_space,
    "min-enclosure": _min_enclosure,
    "min-extension": _min_extension,
    "min-area": _min_area,
    "exact-size": _exact_size,
    "max-distance": _max_distance,
}


def _emit(row: RuleRow, d: _Deck) -> Emitted:
    """A row with a `fixture` naming a snippet uses it (topology rules, and `co.s.butt`);
    every other row is emitted by its kind."""
    if row.fixture in TOPOLOGY:
        return TOPOLOGY[row.fixture](row, d)
    if row.kind == "topology":
        raise ValueError(f"{row.id}: no topology snippet for fixture {row.fixture!r}")
    if row.kind not in KINDS:
        raise ValueError(f"{row.id}: no KLayout check for kind {row.kind!r}")
    return KINDS[row.kind](row, d)


def _summary(row: RuleRow) -> str:
    parts = [row.kind, ", ".join(str(e) for e in row.layers)]
    if row.value is not None:
        parts.append(f"{_num(row.value)} {row.unit}")
    return " ".join(p for p in parts if p)


def _header(variant: str, what: list[str]) -> list[str]:
    return [SPDX, f"# {variant} KLayout DRC deck, variant {variant}: {what[0]}",
            *(f"# {line}" for line in what[1:]),
            f"# Written by {GENERATOR} (ws180g-klayout-deck) from the rule table:",
            "# generated: do not edit."]


def checks_text(table: RuleTable, process: Process) -> str:
    """The checks file: inputs, derived layers and one check per KLayout rule."""
    layers = variant_layers(process, table.variant)
    d = _Deck(process, layers)
    blocks = []
    for row in table.checkable():
        if "klayout" not in row.engines:
            continue
        comments, check = _emit(row, d)
        lines = [f"# {row.id}: {_summary(row)}", *(f"# {c}" for c in comments)]
        if row.engines == ["klayout"]:
            lines.append("# KLayout-only")
        desc = _ruby_str(f"{row.id}: {_summary(row)}. {row.text}")
        lines.append(f'{check}.output("{row.id}", {desc})')
        blocks.append("\n".join(lines))
    inputs = [f"{name} = input({layer.gds[0]}, {layer.gds[1]})"
              for name, layer in layers.items()]
    head = _header(table.variant, [
        "the checks.",
        f"Evaluated inside the DRC engine by {table.variant}.drc and {table.variant}_batch.drc",
        "after source, report and deep are set; one output per rule, named by the rule id."])
    return "\n".join([
        *head, "",
        "# Inputs: every drawn and generated layer of the variant (the generated layers are",
        "# written into the GDS by ws180g_layergen before DRC).",
        *inputs, "",
        "# Derived layers and helpers, each assigned once.",
        *d.lines, "",
        "# Checks, one per rule, in rule-table order.",
        "\n\n".join(blocks), ""])


def single_text(variant: str) -> str:
    return "\n".join([
        *_header(variant, [
            "one layout.",
            f"Run: klayout -b -r {variant}.drc -rd input=<gds> -rd report=<lyrdb>",
            "The GDS must carry the generated layers (ws180g_layergen.derive_file)."]),
        "",
        f'$input or raise("{variant}.drc: pass -rd input=<gds>")',
        f'$report or raise("{variant}.drc: pass -rd report=<lyrdb>")',
        "source($input)",
        f'report("{variant}", $report)',
        "deep",
        "# instance_eval, not require_relative: the checks need the DRC engine's DSL.",
        f'checks = File.join(File.dirname(__FILE__), "{variant}_checks.rb")',
        "instance_eval(File.read(checks), checks)", ""])


def batch_text(variant: str) -> str:
    return "\n".join([
        *_header(variant, [
            "every layout of a list, in one KLayout process.",
            f"Run: klayout -b -r {variant}_batch.drc -rd list=<file> -rd out=<dir>",
            "The list holds one GDS path per line; each writes <dir>/<basename>.lyrdb."]),
        "",
        f'$list or raise("{variant}_batch.drc: pass -rd list=<file of GDS paths>")',
        f'$out or raise("{variant}_batch.drc: pass -rd out=<report directory>")',
        "gds_paths = File.readlines($list, chomp: true).map(&:strip).reject(&:empty?)",
        'stems = gds_paths.map { |p| File.basename(p, ".*") }',
        f'stems.uniq.size == stems.size or raise("{variant}_batch.drc: repeated basename")',
        "deep",
        "# instance_eval, not require_relative: the checks need the DRC engine's DSL.",
        f'checks = File.join(File.dirname(__FILE__), "{variant}_checks.rb")',
        "gds_paths.zip(stems).each do |gds, stem|",
        "  source(gds)",
        f'  report("{variant}", File.join($out, stem + ".lyrdb"))',
        "  instance_eval(File.read(checks), checks)",
        "end", ""])


def write_klayout_deck(table: RuleTable, process: Process, out_dir: Path) -> list[Path]:
    """Write `<variant>.drc`, `<variant>_batch.drc` and `<variant>_checks.rb` into `out_dir`
    and return their paths in that order. Raises `ValueError` for a rule the deck cannot
    check (unknown kind, unknown topology fixture, wrong layer count)."""
    variant = table.variant
    texts = {f"{variant}.drc": single_text(variant),
             f"{variant}_batch.drc": batch_text(variant),
             f"{variant}_checks.rb": checks_text(table, process)}
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, text in texts.items():
        path = out_dir / name
        path.write_text(text, encoding="utf-8")
        paths.append(path)
    return paths


def main(argv: list[str] | None = None) -> int:
    """`ws180g-klayout-deck [--variant V] --out DIR`: write the KLayout DRC deck of variant V
    (default ws180g005) into DIR and print the paths."""
    from ws180g_process.load import load_process

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--variant", default=DEFAULT_VARIANT,
                        help=f"process variant (default: {DEFAULT_VARIANT})")
    parser.add_argument("--out", type=Path, required=True, help="output directory")
    args = parser.parse_args(argv)
    process = load_process()
    for path in write_klayout_deck(RuleTable.from_process(process, args.variant), process,
                                   args.out):
        print(path)
    return 0
