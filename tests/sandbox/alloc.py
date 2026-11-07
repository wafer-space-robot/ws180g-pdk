# SPDX-License-Identifier: Apache-2.0
"""Allocate and touch MIB mebibytes, then print `allocated MIB MiB`.

Run inside the container to check that `build/sandbox-run --mem` really caps memory:
`alloc.py 2048` under `--mem 1g` must be OOM-killed (exit 137). Every page is written
(not just reserved), so the allocation counts against the cgroup.
"""

import sys

CHUNK_MIB = 64


def main() -> None:
    total = int(sys.argv[1])
    held = []
    for _ in range(0, total, CHUNK_MIB):
        held.append(b"\x01" * (CHUNK_MIB << 20))
    print(f"allocated {len(held) * CHUNK_MIB} MiB")


if __name__ == "__main__":
    main()
