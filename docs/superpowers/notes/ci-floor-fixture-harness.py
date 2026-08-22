"""Measure the floor input's contribution as a function of the time axis length.

Run: `pixi run python docs/superpowers/notes/ci-floor-fixture-harness.py <workdir>`

Prints one JSON object per reading to stdout, and nothing else, so the output is
appended to `ci-floor-fixture-measured.jsonl` and read back rather than retyped.

**WHY THIS EXISTS.** The one RSS assertion CI runs asserts that opening the input
adds more than 1 MB to the floor. The same 24x4x4 fixture contributes 11.20 MB on
this box and 1.00 MB on the CI runner, so the recorded contribution is dominated by
a machine-dependent term that is not a function of input size. Sizing the fixture
from that ratio would be a multiplier taken across machines, which the two readings
themselves refute. This measures the part that IS a function of input size.

Predictions are committed first, in `ci-floor-fixture-predictions.json`, including
the horn that would kill the lever (E3: the index is never materialised, so the
slope is zero).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

from metamer.core.machine import available_ram_bytes, memory_stall_us

#: Sizes of the time axis, in steps. 24 is the fixture as it stands today.
N_TIME_POINTS = (24, 65536, 262144, 1048576)

#: Repeats per point, interleaved rather than blocked.
REPEATS = 3


def build_input(path: Path, *, n_time: int, grid: int) -> str:
    """Write a zarr store shaped like the floor fixture, at a chosen length.

    Args:
        path: Where to write the store.
        n_time: Length of the time axis.
        grid: Side of the (square) spatial grid.

    Returns:
        The store URI, as a string.
    """
    import xarray as xr

    origin = np.datetime64("2000-01-01")
    axis = origin + np.arange(n_time, dtype="int64") * np.timedelta64(31, "D")
    xr.Dataset(
        {
            "sla": (
                ("time", "y", "x"),
                np.zeros((n_time, grid, grid), dtype="float32"),
            )
        },
        coords={
            "time": axis,
            "y": np.arange(grid, dtype="float64"),
            "x": np.arange(grid, dtype="float64"),
        },
    ).to_zarr(path, mode="w", consolidated=True)
    return str(path)


def one_reading(work: Path, *, n_time: int, grid: int, repeat: int) -> dict[str, Any]:
    """Build a fixture and measure the floor on it, in a fresh child.

    Args:
        work: Working directory for fixtures.
        n_time: Length of the time axis.
        grid: Side of the spatial grid.
        repeat: Which repeat this is.

    Returns:
        The reading, with the ambient conditions that were true when it was taken.
    """
    from metamer.core.memory import measure_floor

    path = work / f"floor_n{n_time}_g{grid}_r{repeat}.zarr"
    started = time.monotonic()
    uri = build_input(path, n_time=n_time, grid=grid)
    # AMBIENT CONDITIONS BESIDE EVERY READING, not once at the top: available RAM
    # on this box has ranged 1.9 to 9.4 GB and that difference has confounded
    # three prior tasks.
    before_ram = available_ram_bytes()
    before_stall = memory_stall_us()
    report = measure_floor(data_uri=uri, variable="sla")
    after_stall = memory_stall_us()
    elapsed = time.monotonic() - started
    return {
        "n_time": n_time,
        "grid": grid,
        "repeat": repeat,
        "contribution_bytes": report.with_input_bytes - report.post_warm_bytes,
        "with_input_bytes": report.with_input_bytes,
        "post_warm_bytes": report.post_warm_bytes,
        "peak_bytes": report.peak_bytes,
        "reclaim_shortfall_bytes": report.reclaim_shortfall_bytes,
        "components": dict(report.components),
        "data_bytes_written": n_time * grid * grid * 4,
        "available_ram_bytes_before": before_ram,
        "memory_stall_us_before": before_stall,
        "memory_stall_us_after": after_stall,
        "elapsed_s": elapsed,
    }


def main() -> None:
    """Run the interleaved ladder and print every reading as JSON."""
    work = Path(sys.argv[1])
    work.mkdir(parents=True, exist_ok=True)

    # THE CONTROL IS THE FIXTURE AS IT STANDS: 24 x 4 x 4. Every other point is
    # 1x1, so the lever moves the time axis alone.
    plan: list[tuple[int, int]] = [(24, 4)] + [(n, 1) for n in N_TIME_POINTS]

    for repeat in range(REPEATS):
        for n_time, grid in plan:
            reading = one_reading(work, n_time=n_time, grid=grid, repeat=repeat)
            print(json.dumps(reading), flush=True)


if __name__ == "__main__":
    main()
