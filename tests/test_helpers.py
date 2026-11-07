# SPDX-License-Identifier: Apache-2.0
import tomllib

import pytest
from helpers import set_toml

SAMPLE = """\
top = 1

[a]
x = 1  # keep me
y = "old"

[a.b]
x = 2.5
flag = false

[c]
x = 9
"""


def test_set_toml_replaces_values(tmp):
    p = tmp / "s.toml"
    p.write_text(SAMPLE)
    set_toml(p, ["a", "x"], 7)
    set_toml(p, ["a", "y"], 'new "q"')
    set_toml(p, ["a", "b", "x"], 3.5)
    set_toml(p, ["a", "b", "flag"], True)
    set_toml(p, ["top"], 0)
    d = tomllib.loads(p.read_text())
    assert d == {"top": 0, "a": {"x": 7, "y": 'new "q"', "b": {"x": 3.5, "flag": True}},
                 "c": {"x": 9}}
    assert "# keep me" in p.read_text()


def test_set_toml_missing_key_raises(tmp):
    p = tmp / "s.toml"
    p.write_text(SAMPLE)
    with pytest.raises(KeyError):
        set_toml(p, ["c", "nope"], 1)
