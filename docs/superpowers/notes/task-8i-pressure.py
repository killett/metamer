"""A bounded, self-limiting memory-pressure generator.

Task 8i needs a known-bad on demand and Task 8a's 600 s idle run is not one: the
same run reproduced 86.3 MB of loss once and 0.0 MB the next time, and the two
windows differed by 56x in system-wide reclaim that this project did not cause.
So the pressure has to be CONSTRUCTED rather than waited for.

**SELF-LIMITING BY DESIGN.** It allocates in small increments and stops the
moment `MemAvailable` falls below a floor, so the kernel is pushed into
reclaiming cache and mapped file pages without being pushed into the OOM killer.
The floor is checked before every increment, not just at the start.

Usage: pressure.py <hold_seconds> [floor_mb] [cap_mb]
"""

from __future__ import annotations

import sys
import time
from pathlib import Path


def available_mb() -> int:
    """Read `MemAvailable`, in MB.

    Returns:
        Megabytes the kernel believes are available without swapping.

    Raises:
        RuntimeError: If the field is absent, because guessing here is what
            would turn a bounded generator into an unbounded one.
    """
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) // 1024
    raise RuntimeError("no MemAvailable in /proc/meminfo")


def main() -> None:
    """Allocate until the floor is reached, hold, then release."""
    hold = int(sys.argv[1])
    floor_mb = int(sys.argv[2]) if len(sys.argv) > 2 else 2048
    cap_mb = int(sys.argv[3]) if len(sys.argv) > 3 else 6144

    import numpy as np

    chunk_mb = 256
    blocks: list[object] = []
    held = 0
    while held < cap_mb and available_mb() > floor_mb + chunk_mb:
        block = np.empty(chunk_mb * 1024 * 1024 // 8, dtype="float64")
        block[:] = 1.0  # touch every page; np.empty is not resident until written
        blocks.append(block)
        held += chunk_mb
    print(f"held_mb={held} available_mb={available_mb()}", flush=True)
    time.sleep(hold)
    print(f"releasing available_mb={available_mb()}", flush=True)
    del blocks


if __name__ == "__main__":
    main()
