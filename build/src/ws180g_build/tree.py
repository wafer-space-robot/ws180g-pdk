# SPDX-License-Identifier: Apache-2.0
"""The release tree of one variant, `out/<variant>/`, assembled from the build's staging
directory.

`assemble(variant, stage, dest)` copies, from the files the generators wrote into `stage`:

- `libs.tech/klayout/<variant>.{lyp,lyt,map}` (`stage/klayout/`, `ws180g_tech.klayout`);
- `libs.tech/klayout/drc/<variant>.drc`, with the batch entry point and the checks file it
  loads from its own directory (`stage/drc/`, `ws180g_rules.klayout_deck`);
- `libs.tech/magic/<variant>.{tech,magicrc}` (`stage/magic/`, `ws180g_tech.magic`);
- `docs/rules.md` (the manual, `ws180g_rules.manual`) and `docs/evidence-report.md` (the
  evidence margin report).

`dest` is replaced as a whole, so no file of an earlier build survives. A missing input is
an error (`FileNotFoundError`): the tree is complete or not written.
"""

import shutil
from pathlib import Path


def tree_files(variant: str) -> list[tuple[str, str]]:
    """`(path in stage, path in the tree)` of every file of the release tree, in tree
    order."""
    v = variant
    return [
        (f"klayout/{v}.lyp", f"libs.tech/klayout/{v}.lyp"),
        (f"klayout/{v}.lyt", f"libs.tech/klayout/{v}.lyt"),
        (f"klayout/{v}.map", f"libs.tech/klayout/{v}.map"),
        (f"drc/{v}.drc", f"libs.tech/klayout/drc/{v}.drc"),
        (f"drc/{v}_batch.drc", f"libs.tech/klayout/drc/{v}_batch.drc"),
        (f"drc/{v}_checks.rb", f"libs.tech/klayout/drc/{v}_checks.rb"),
        (f"magic/{v}.tech", f"libs.tech/magic/{v}.tech"),
        (f"magic/{v}.magicrc", f"libs.tech/magic/{v}.magicrc"),
        ("rules.md", "docs/rules.md"),
        ("evidence-report.md", "docs/evidence-report.md"),
    ]


def assemble(variant: str, stage: Path, dest: Path) -> list[Path]:
    """Build the release tree of `variant` in `dest` from `stage` (see the module
    docstring) and return the paths written, in tree order."""
    pairs = [(Path(stage) / src, Path(dest) / rel) for src, rel in tree_files(variant)]
    missing = [str(src) for src, _ in pairs if not src.is_file()]
    if missing:
        raise FileNotFoundError(f"release tree of {variant}: missing {', '.join(missing)}")
    if Path(dest).exists():
        shutil.rmtree(dest)
    for src, target in pairs:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, target)
    return [target for _, target in pairs]
