# SPDX-License-Identifier: Apache-2.0
"""The committed SCMOS rev 8 entries (evidence/data/scmos8.toml) and their source record."""

from decimal import Decimal

from ws180g_evidence.import_scmos import PAGES


def test_committed_entries(evidence):
    entries = {k: e for k, e in evidence.entries.items() if e.source == "scmos8"}
    assert entries["scmos8/3.1/deep"].value == Decimal("0.18")
    assert entries["scmos8/3.1/deep"].lambda_ == 2
    assert entries["scmos8/8.1/deep"].kind == "exact-size"
    assert entries["scmos8/8.1/deep"].value == Decimal("0.27")
    assert entries["scmos8/29.1/deep"].value == Decimal("0.36")
    assert entries["scmos8/30.1/subm"].value == Decimal("0.50")
    assert entries["scmos8/30.1/subm"].lambda_um == Decimal("0.10")
    assert entries["scmos8/10.1"].guideline is True and entries["scmos8/10.1"].value == 60
    assert entries["scmos8/3.1/scmos"].value is None
    assert entries["scmos8/5.2.b/deep"].value == Decimal("0.09")
    assert {int(e.rule.split(".")[0]) for e in entries.values()} >= {
        1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 14, 15, 20, 21, 22, 24, 25, 26, 29, 30, 31}


def test_every_page_is_registered(evidence):
    assert set(evidence.sources["scmos8"].sha256) == set(PAGES)
    assert evidence.sources["scmos8"].vendored is False


def test_readme_lists_the_recorded_digests(evidence, repo_root):
    readme = (repo_root / "evidence/sources/scmos8/README.md").read_text()
    for page, digest in evidence.sources["scmos8"].sha256.items():
        assert f"| `{page}` |" in readme and digest in readme
