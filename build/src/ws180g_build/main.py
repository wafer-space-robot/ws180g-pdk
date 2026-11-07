# SPDX-License-Identifier: Apache-2.0
"""The one-command build: `ws180g-build [--variant ws180g005] [--out out/] [--no-container]`.

In order, every step failing the build when it fails:

1. load the process description (`process/data/ws180g/`) and the evidence set;
2. the evidence margin report: written to `generated/evidence-report.{md,json}`; the build
   stops unless the report is ok (no `under-margin`, `missing-entry`,
   `override-too-small` or `achieved-mismatch` row, grid ok); `chosen`, `exempt`,
   `implied` rows and the uncovered public rules do not fail it;
3. the rule table (`generated/rule-table.{json,csv}`), the KLayout deck (`generated/drc/`),
   the Magic technology (`generated/magic/`), the KLayout technology files
   (`generated/klayout/`), the per-rule fixtures (`generated/fixtures/`) and the manual
   (`generated/rules.md`, from the rule table only);
4. unless `--no-container`: the local image is checked against `docker/IMAGE_ID` and
   rebuilt (`docker/build`) to check that it reproduces that ID; then three container runs,
   one per engine, through `build/sandbox-run` (4 GiB, 2 CPUs), with the DRC cache under
   `tmp/build/<variant>/` (the sandbox accepts a workdir inside a checkout only under its
   `tmp/`): every fixture through the KLayout deck (`reports/klayout-fixtures.json`), every
   fixture of a Magic rule through Magic (`reports/magic-fixtures.json`), and every gate
   pass fixture, retargeted, through the public GF180MCU deck for each `metal_top`
   (`reports/gf180mcu-gate.json`); any fixture with other markers than expected fails;
5. the release tree `<variant>/` (`ws180g_build.tree.assemble`), and the two generated
   pages copied to `--docs` (default `docs/generated/`, which `docs/rules.md` and
   `docs/evidence.md` include);
6. the naming checker on the repository and on the release tree, the private-data checker
   on the repository;
7. `build-manifest.json`: every file under `--out` with its sha256 (paths relative to
   `--out`, sorted), the image ID, the git commit, whether the container runs ran.

Nothing written carries a timestamp, a date or an absolute path, so two builds on the same
inputs give byte-identical outputs.
"""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from ws180g_evidence.load import DEFAULT_DATA as EVIDENCE_DATA
from ws180g_evidence.load import load_evidence
from ws180g_evidence.report import FAILING, margin_report
from ws180g_process.load import DEFAULT_DATA as PROCESS_DATA
from ws180g_process.load import load_process
from ws180g_rules.fixtures import Fixture, write_fixtures
from ws180g_rules.klayout_deck import write_klayout_deck
from ws180g_rules.manual import write_manual
from ws180g_rules.run_klayout import Runner, read_image_id
from ws180g_rules.table import DEFAULT_VARIANT, RuleTable
from ws180g_tech.klayout import write_klayout_tech
from ws180g_tech.magic import write_magic_tech

from ws180g_build import tree
from ws180g_build.naming import check_tree
from ws180g_build.private_check import check_private

REPO = Path(__file__).resolve().parents[3]
MANIFEST = "build-manifest.json"
#: The directories under `--out` a build owns and replaces.
OWNED = ("generated", "reports")
#: The container caps of every engine run (build/sandbox-run).
SANDBOX_MEM = "4g"
SANDBOX_CPUS = 2
#: The tag the reproducibility check rebuilds the image under.
VERIFY_TAG = "ws180g-pdk-base:verify"

Log = Callable[[str], None]


def _log(message: str) -> None:
    """Print a progress line at once (the build is often run with its output in a file)."""
    print(message, flush=True)


class BuildError(RuntimeError):
    """A step of the build failed; the message says which and why."""


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False) + "\n",
                    encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_commit(repo: Path = REPO) -> tuple[str | None, bool]:
    """The commit of `repo` and whether its working tree has changes (`None, False` outside
    a git checkout)."""
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True,
                          text=True, check=False)
    if head.returncode != 0:
        return None, False
    status = subprocess.run(["git", "-C", str(repo), "status", "--porcelain"],
                            capture_output=True, text=True, check=False)
    return head.stdout.strip(), bool(status.stdout.strip())


def sandbox_runner(repo: Path = REPO, mem: str = SANDBOX_MEM,
                   cpus: int = SANDBOX_CPUS) -> Runner:
    """A `runner(cmd, workdir)` running `cmd` in the container through `build/sandbox-run`."""
    def run(cmd: list[str], workdir: Path) -> subprocess.CompletedProcess:
        return subprocess.run(
            [str(repo / "build" / "sandbox-run"), "--mem", mem, "--cpus", str(cpus),
             "--workdir", str(workdir), "--", *cmd],
            capture_output=True, text=True, check=False)
    return run


def check_image(image_id: str, work: Path, repo: Path = REPO, log: Log = _log) -> None:
    """The local image `docker/IMAGE` names has the ID `image_id`, and rebuilding it with
    `docker/build` gives that ID again (the build log goes to `work/image-build.log`)."""
    image = (repo / "docker" / "IMAGE").read_text(encoding="utf-8").splitlines()[0].strip()
    got = subprocess.run(["docker", "image", "inspect", "-f", "{{.Id}}", image],
                         capture_output=True, text=True, check=False)
    if got.returncode != 0 or got.stdout.strip() != image_id:
        raise BuildError(f"image {image} has ID {got.stdout.strip() or '(none)'}, not "
                         f"{image_id} (docker/IMAGE_ID): build it with docker/build\n"
                         f"{got.stderr[-2000:]}")
    work.mkdir(parents=True, exist_ok=True)
    log_path = work / "image-build.log"
    log(f"image: {image} is {image_id}; rebuilding to check it reproduces ({log_path})")
    with log_path.open("w", encoding="utf-8") as f:
        rebuilt = subprocess.run([str(repo / "docker" / "build"), "--tag", VERIFY_TAG],
                                 stdout=subprocess.PIPE, stderr=f, text=True, check=False)
    if rebuilt.returncode != 0 or rebuilt.stdout.strip() != image_id:
        raise BuildError(f"docker/build exit {rebuilt.returncode} gave "
                         f"{rebuilt.stdout.strip() or '(nothing)'}, not {image_id}; see "
                         f"{log_path}")


def _fixture_id(f: Fixture) -> str:
    return f"{f.rule_id}/{f.expect}_{f.name}"


def run_engines(table: RuleTable, process, fixtures: list[Fixture], generated: Path,
                reports: Path, work: Path, runner: Runner, image_id: str,
                log: Log = _log) -> None:
    """The three container runs of step 4; writes their reports and raises `BuildError`
    when any fixture does not give the expected markers."""
    from ws180g_precheck.gate import EXCLUDED, gate_fixtures
    from ws180g_precheck.gf180mcu import run_gf180mcu_drc_many
    from ws180g_precheck.mapping import load_mapping
    from ws180g_precheck.retarget import retarget_file
    from ws180g_rules.run_klayout import run_klayout_many
    from ws180g_rules.run_magic import run_magic_many
    from ws180g_tech.magic import magic_markers

    failures: list[str] = []

    klayout = run_klayout_many(generated / "drc", [f.path for f in fixtures],
                               work / "klayout", runner, process, image_id)
    log(f"klayout: {len(fixtures)} fixtures, {klayout.cache_hits} from the cache")
    wrong = {_fixture_id(f): {"expected": f.markers(), "got": klayout[f.path].violations}
             for f in fixtures
             if klayout[f.path].violations != f.markers() or not klayout[f.path].categories_run}
    _write_json(reports / "klayout-fixtures.json", {"fixtures": len(fixtures), "wrong": wrong})
    failures += [f"klayout {k}" for k in wrong]

    magic_rules = {r.id for r in table.checkable() if "magic" in r.engines}
    magic_set = [f for f in fixtures if f.rule_id in magic_rules]
    magic = run_magic_many(generated / "magic", [f.path for f in magic_set], work / "magic",
                           runner, process, image_id)
    log(f"magic: {len(magic_set)} fixtures, {magic.cache_hits} from the cache")
    wrong = {_fixture_id(f): {"expected": sorted(magic_markers(f)),
                              "got": sorted(magic[f.path].violations)}
             for f in magic_set
             if set(magic[f.path].violations) != magic_markers(f)
             or not magic[f.path].categories_run}
    _write_json(reports / "magic-fixtures.json", {"fixtures": len(magic_set), "wrong": wrong})
    failures += [f"magic {k}" for k in wrong]

    mapping = load_mapping()
    gate = gate_fixtures(fixtures)
    retargeted_dir = work / "gf180mcu" / "retargeted"
    if retargeted_dir.exists():
        shutil.rmtree(retargeted_dir)
    retargeted = {}
    for f in gate:
        target = retargeted_dir / f.path.parent.name / f.path.name
        retarget_file(f.path, target, mapping, process, table.variant)
        retargeted[_fixture_id(f)] = target
    runs = {}
    for metal_top in mapping.drc.metal_top:
        results = run_gf180mcu_drc_many(list(retargeted.values()), work / "gf180mcu" / "run",
                                        runner, mapping, metal_top, jobs=SANDBOX_CPUS,
                                        image_id=image_id)
        log(f"gf180mcu {metal_top}: {len(gate)} fixtures, {results.cache_hits} from the cache")
        dirty = {case: results[path].violations for case, path in retargeted.items()
                 if results[path].violations or not results[path].categories_run}
        runs[metal_top] = {"fixtures": len(gate), "dirty": dirty}
        failures += [f"gf180mcu {metal_top} {k}" for k in dirty]
    _write_json(reports / "gf180mcu-gate.json", {
        "deck": mapping.drc.deck, "runs": runs,
        "excluded": {f"{r}/{n}": list(v) for (r, n), v in sorted(EXCLUDED.items())}})
    if failures:
        raise BuildError(f"{len(failures)} fixture(s) gave unexpected markers: "
                         f"{', '.join(failures[:10])}; see {reports}")


def build(variant: str, out: Path, docs: Path, container: bool = True,
          process_dir: Path = PROCESS_DATA, evidence_dir: Path = EVIDENCE_DATA,
          runner: Runner | None = None, log: Log = _log) -> dict:
    """Run the build (see the module docstring) and return the manifest."""
    out, docs = Path(out), Path(docs)
    for name in (*OWNED, variant):
        if (out / name).exists():
            shutil.rmtree(out / name)
    (out / MANIFEST).unlink(missing_ok=True)
    generated, reports = out / "generated", out / "reports"
    generated.mkdir(parents=True)

    process = load_process(process_dir)
    report = margin_report(process, load_evidence(evidence_dir))
    log(f"evidence report: {report.summary()}")
    (generated / "evidence-report.md").write_text(report.to_markdown(), encoding="utf-8")
    (generated / "evidence-report.json").write_text(report.to_json(), encoding="utf-8")
    if not report.ok:
        bad = [f"{r.field} ({r.status})" for r in report.rows if r.status in FAILING]
        if not report.grid_ok:
            bad.append("grid")
        raise BuildError(f"the evidence report is not ok: {', '.join(bad)}; see "
                         f"{generated / 'evidence-report.md'}")

    table = RuleTable.from_process(process, variant)
    table.write_json(generated / "rule-table.json")
    table.write_csv(generated / "rule-table.csv")
    write_klayout_deck(table, process, generated / "drc")
    write_magic_tech(table, process, variant, generated / "magic")
    write_klayout_tech(process, variant, generated / "klayout")
    fixtures = write_fixtures(table, process, generated / "fixtures")
    write_manual(table, generated / "rules.md")
    log(f"generated: {len(table)} rules, {len(fixtures)} fixtures, in {generated}")

    image_id = read_image_id()
    if container:
        work = REPO / "tmp" / "build" / variant
        check_image(image_id, work, log=log)
        run_engines(table, process, fixtures, generated, reports, work,
                    runner or sandbox_runner(), image_id, log)
    else:
        log("--no-container: the image check and the three container runs are skipped")

    tree.assemble(variant, generated, out / variant)
    docs.mkdir(parents=True, exist_ok=True)
    for page in ("rules.md", "evidence-report.md"):
        shutil.copyfile(out / variant / "docs" / page, docs / page)
    log(f"release tree: {out / variant}; pages: {docs}")

    errors = check_tree(REPO) + check_tree(out / variant)
    if errors:
        raise BuildError("naming check: " + "; ".join(errors[:10]))
    findings = check_private(REPO)
    if findings:
        raise BuildError("private-data check: " + "; ".join(str(f) for f in findings[:10]))

    commit, dirty = git_commit()
    files = {p.relative_to(out).as_posix(): _sha256(p)
             for p in sorted(out.rglob("*"))
             if p.is_file() and (p.relative_to(out).parts[0] in (*OWNED, variant))}
    manifest = {
        "variant": variant, "git_commit": commit, "git_dirty": dirty, "image_id": image_id,
        "container_runs": container,
        "image_check": "rebuilt, ID reproduced" if container else "skipped (--no-container)",
        "evidence_report": report.summary(), "rules": len(table), "fixtures": len(fixtures),
        "files": dict(sorted(files.items())),
    }
    _write_json(out / MANIFEST, manifest)
    log(f"manifest: {out / MANIFEST} ({len(files)} files)")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ws180g-build", description=__doc__.splitlines()[0])
    parser.add_argument("--variant", default=DEFAULT_VARIANT,
                        help=f"process variant (default: {DEFAULT_VARIANT})")
    parser.add_argument("--out", type=Path, default=Path("out"),
                        help="output directory (default: out/)")
    parser.add_argument("--docs", type=Path, default=REPO / "docs" / "generated",
                        help="where the generated documentation pages go (default: "
                             "docs/generated/ of the checkout)")
    parser.add_argument("--no-container", action="store_true",
                        help="skip the image check and the three container runs")
    parser.add_argument("--process", type=Path, default=PROCESS_DATA,
                        help="process data directory (default: process/data/ws180g)")
    parser.add_argument("--evidence", type=Path, default=EVIDENCE_DATA,
                        help="evidence data directory (default: evidence/data)")
    args = parser.parse_args(argv)
    try:
        build(args.variant, args.out, args.docs, container=not args.no_container,
              process_dir=args.process, evidence_dir=args.evidence)
    except BuildError as exc:
        print(f"ws180g-build: error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
