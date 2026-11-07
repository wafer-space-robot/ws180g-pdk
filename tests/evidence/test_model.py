# SPDX-License-Identifier: Apache-2.0
from decimal import Decimal

import pytest
from helpers import evidence_dir_with
from ws180g_evidence.load import EvidenceError, load_evidence

SOURCE = {"title": "Foo manual", "url": "https://example.org/foo", "licence": "CC-BY-4.0",
          "transcribed": True, "vendored": False}


def test_unregistered_source_rejected(tmp):
    bad = evidence_dir_with([{"id": "foo/X.1", "source": "foo", "kind": "min-width", "value": 1}], sources={}, root=tmp)
    with pytest.raises(EvidenceError, match="source"):
        load_evidence(bad)


def test_registered_source_loads(tmp):
    good = evidence_dir_with(
        [{"id": "foo/X.1", "source": "foo", "kind": "min-width", "value": 1.5, "lambda": 2.5}],
        sources={"foo": SOURCE}, root=tmp)
    evidence = load_evidence(good)
    entry = evidence.entries["foo/X.1"]
    assert entry.value == Decimal("1.5") and entry.lambda_ == Decimal("2.5")
    assert evidence.sources["foo"].id == "foo" and evidence.sources["foo"].public is True


def test_every_error_reported_at_once(tmp):
    bad = evidence_dir_with(
        [{"id": "foo/X.1", "source": "foo", "kind": "min-width", "value": 1},
         {"id": "foo/X.3", "source": "foo", "kind": "nonsense", "value": 1},
         {"id": "bar/X.2", "source": "bar", "kind": "min-width", "value": 1},
         {"id": "foo/X.1", "source": "foo", "kind": "min-width", "value": 1}],
        sources={"foo": SOURCE}, root=tmp)
    with pytest.raises(EvidenceError) as caught:
        load_evidence(bad)
    lines = str(caught.value).splitlines()
    assert len(lines) == 3
    assert all(line.startswith("entries.toml: entry[") for line in lines)
    assert any("kind" in line for line in lines)
    assert any("source 'bar' is not registered" in line for line in lines)
    assert any("duplicate id foo/X.1" in line for line in lines)


def test_id_must_start_with_source(tmp):
    bad = evidence_dir_with([{"id": "bar/X.1", "source": "foo", "kind": "min-width", "value": 1}],
                            sources={"foo": SOURCE}, root=tmp)
    with pytest.raises(EvidenceError, match="id"):
        load_evidence(bad)


def test_every_entry_source_is_registered(evidence):
    assert evidence.entries
    for entry in evidence.entries.values():
        assert entry.source in evidence.sources


def test_every_vendored_file_exists(evidence, repo_root):
    for source in evidence.sources.values():
        if source.vendored:
            assert source.sha256, source.id
            for name in source.sha256:
                assert (repo_root / "evidence/sources" / source.id / name).is_file()
