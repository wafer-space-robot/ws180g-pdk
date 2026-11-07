# SPDX-License-Identifier: Apache-2.0
"""KLayout technology files: layer properties (.lyp), technology (.lyt) and LEF/DEF map (.map).

Output is deterministic: no timestamps, a fixed colour per layer position."""

import argparse
import colorsys
from collections.abc import Sequence
from pathlib import Path
from xml.sax.saxutils import escape

from ws180g_process.load import load_process

SPDX = "SPDX-License-Identifier: Apache-2.0"
DEFAULT_VARIANT = "ws180g005"
# Metals and vias carry a pin purpose and a LEF/DEF map entry.
PIN_LAYERS = ("m1", "v1", "m2", "v2", "m3", "v3", "m4", "v4", "mtop")
GOLDEN = 0.618033988749895


def selected_layers(process, variant):
    """Layers of `variant`: those with no variant, its own, or one it contains."""
    allowed = {variant, *process.variants[variant].contains}
    return {n: l for n, l in process.layers.items() if l.variant is None or l.variant in allowed}


def colour(index: int) -> str:
    """A distinct fixed colour per layer position (golden-ratio hue steps)."""
    r, g, b = colorsys.hsv_to_rgb((index * GOLDEN) % 1.0, 0.65 + 0.1 * (index % 3), 0.95 - 0.1 * (index % 2))
    return f"#{round(r * 255):02x}{round(g * 255):02x}{round(b * 255):02x}"


def _properties(name: str, source: str, rgb: str, brightness: int) -> str:
    return (
        " <properties>\n"
        f"  <frame-color>{rgb}</frame-color>\n"
        f"  <fill-color>{rgb}</fill-color>\n"
        f"  <frame-brightness>{brightness}</frame-brightness>\n"
        f"  <fill-brightness>{brightness}</fill-brightness>\n"
        "  <dither-pattern>I5</dither-pattern>\n"
        "  <line-style/>\n"
        "  <valid>true</valid>\n"
        "  <visible>true</visible>\n"
        "  <transparent>false</transparent>\n"
        "  <width>1</width>\n"
        "  <marked>false</marked>\n"
        "  <xfill>false</xfill>\n"
        "  <animation>0</animation>\n"
        f"  <name>{escape(name)}</name>\n"
        f"  <source>{source}</source>\n"
        " </properties>\n"
    )


def lyp_text(process, layers) -> str:
    label = process.datatypes.label
    pin = process.datatypes.pin
    out = ['<?xml version="1.0" encoding="utf-8"?>\n', f"<!-- {SPDX} -->\n", "<layer-properties>\n"]
    for index, (name, layer) in enumerate(layers.items()):
        number, datatype = layer.gds
        rgb = colour(index)
        dim = -32 if layer.kind == "generated" else 0
        out.append(_properties(name, f"{number}/{datatype}@1", rgb, dim))
        if layer.kind == "drawn":
            out.append(_properties(f"{name}.label", f"{number}/{label}@1", rgb, dim))
        if name in PIN_LAYERS:
            out.append(_properties(f"{name}.pin", f"{number}/{pin}@1", rgb, dim))
    out.append("</layer-properties>\n")
    return "".join(out)


def lyt_text(process, variant: str, layers) -> str:
    entries = ";".join(f"'{name} : {l.gds[0]}/{l.gds[1]}'" for name, l in layers.items())
    layer_map = f"layer_map({entries})"
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        f"<!-- {SPDX} -->\n"
        "<technology>\n"
        f" <name>{variant}</name>\n"
        f" <description>wafer.space 180 nm generic PDK, variant {variant}</description>\n"
        " <dbu>0.001</dbu>\n"
        f" <default-grids>{process.grid.value}!</default-grids>\n"
        f" <layer-properties_file>{variant}.lyp</layer-properties_file>\n"
        " <add-other-layers>true</add-other-layers>\n"
        " <reader-options>\n"
        "  <common>\n"
        f"   <layer-map>{escape(layer_map)}</layer-map>\n"
        "  </common>\n"
        " </reader-options>\n"
        " <writer-options>\n"
        "  <format>GDS2</format>\n"
        "  <gds2>\n"
        "   <write-timestamps>false</write-timestamps>\n"
        "  </gds2>\n"
        " </writer-options>\n"
        "</technology>\n"
    )


def map_text(process, layers) -> str:
    label = process.datatypes.label
    pin = process.datatypes.pin
    lines = [f"# {SPDX}", "# LEF/DEF layer map for ws180g"]
    for name in PIN_LAYERS:
        if name not in layers:
            continue
        number, datatype = layers[name].gds
        lines.append(f"{name} NET,SPNET,PIN,VIA {number} {datatype}")
        lines.append(f"NAME {name}/LABEL {number} {label}")
        lines.append(f"{name} PIN {number} {pin}")
    lines.append("DIEAREA ALL 0 0")
    return "\n".join(lines) + "\n"


def write_klayout_tech(process, variant: str, out_dir: Path) -> list[Path]:
    """Write `<variant>.lyp`, `.lyt` and `.map` into `out_dir`; return the three paths."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    layers = selected_layers(process, variant)
    files = {
        f"{variant}.lyp": lyp_text(process, layers),
        f"{variant}.lyt": lyt_text(process, variant, layers),
        f"{variant}.map": map_text(process, layers),
    }
    paths = []
    for name, text in files.items():
        path = out_dir / name
        path.write_text(text, encoding="utf-8")
        paths.append(path)
    return paths


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="ws180g-klayout-tech", description=__doc__)
    parser.add_argument("--variant", default=DEFAULT_VARIANT)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    for path in write_klayout_tech(load_process(), args.variant, args.out):
        print(path)


if __name__ == "__main__":
    main()
