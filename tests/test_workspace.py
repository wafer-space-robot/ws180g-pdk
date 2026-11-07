# SPDX-License-Identifier: Apache-2.0
import importlib

import pytest

PACKAGES = ["ws180g_process", "ws180g_evidence", "ws180g_rules", "ws180g_layergen",
            "ws180g_tech", "ws180g_precheck", "ws180g_build"]


@pytest.mark.parametrize("name", PACKAGES)
def test_package_imports(name):
    assert importlib.import_module(name).__name__ == name
