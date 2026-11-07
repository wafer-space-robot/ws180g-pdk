# SPDX-License-Identifier: Apache-2.0
"""Print the interpreter, its version and the klayout/pydantic imports (one per line).

Run inside the container by tests/sandbox/test_image.py.
"""

import platform
import sys
from importlib.metadata import version

import klayout.db  # noqa: F401
import pydantic  # noqa: F401

print(sys.executable)
print(f"python {platform.python_version()}")
print(f"klayout.db {version('klayout')}")
print("pydantic ok")
