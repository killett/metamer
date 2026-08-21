"""Open question 19: what the fixed-window stall gate reads on both known-bads.

**WHY THIS EXISTS.** `RSS_STALL_LIMIT_US_PER_S` was set from known-good alone --
20 s idle at 0.9 ms/s and one `measure_floor` at 5.3 -- and the (a2) register
says a gate validated against known-good and a threshold answers *"how far from
good"* and never *"can this counter move when the thing goes wrong"*. Task 8a
then measured that it **could not see** the failure it was named for. Open
question 19's repair gives it a fixed window; **a fixed window does not fix
blindness**, and this script is what puts a number on both halves rather than an
argument.

**THREE CELLS, AND EACH ONE ANSWERS A DIFFERENT QUESTION.**

  - `clean`  -- the workload with no pressure. What a healthy window reads, which
                is the only thing a limit may be derived from.
  - `thrash` -- pressure held near the floor while this process re-touches a
                large working set, so pages it still wants are taken and faulted
                back. **This is the failure the gate is FOR**, and it must fire.
  - `quiet`  -- Task 8i's known-bad: pressure held while this process idles, so
                clean pages it has stopped touching are reclaimed at no stall
                cost. **This is the failure the gate is blind to**, and the
                reading is what turns "blind" into a magnitude. The reclaim
                witness must catch what the stall rate does not.

Every cell reports **both** readings -- the windowed maximum the gate now uses
and the whole-block average it used before -- so the repair's own effect is
visible in the same table as the blindness it does not repair.

Usage:
    oq19-gate-validation.py <clean|thrash|quiet> [seconds] [touch_mb]
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

# THE REPO ROOT, SO THE GATE ITSELF CAN BE IMPORTED. `tests.stall` is where the
# window lives, and validating a gate against a reimplementation of it would be
# an oracle sharing its subject's derivation path (j). This script must import
# the shipped one.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from metamer.core import machine  # noqa: E402
from tests.stall import STALL_WINDOW_S, StallWatch, max_windowed_rate  # noqa: E402

PRESSURE = Path(__file__).with_name("task-8i-pressure.py")


def available_mb() -> int:
    """Read `MemAvailable`, in MB.

    Returns:
        Megabytes the kernel believes are available without swapping.

    Raises:
        RuntimeError: If the field is absent.
    """
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) // 1024
    raise RuntimeError("no MemAvailable in /proc/meminfo")


def main() -> None:
    """Run one cell and print its readings as JSON."""
    cell = sys.argv[1]
    seconds = float(sys.argv[2]) if len(sys.argv) > 2 else 30.0
    touch_mb = int(sys.argv[3]) if len(sys.argv) > 3 else 1536
    if cell not in {"clean", "thrash", "refault", "quiet", "probe"}:
        raise SystemExit(
            f"cell must be clean, thrash, refault, quiet or probe, got {cell!r}"
        )

    # THE WORKING SET IS ALLOCATED AND TOUCHED BEFORE THE WINDOW OPENS, so the
    # reference below describes a process that is already holding it. A reference
    # taken before the allocation would be one this process is entitled to sit
    # above, and the witness would read zero for the wrong reason.
    scratch: Path | None = None
    mapped: np.memmap | None = None
    if cell == "probe":
        # A REAL INPUT, BECAUSE `measure_floor` OPENS ONE. Built once, before the
        # window opens, so the build's own allocation is not what gets measured.
        if len(sys.argv) <= 4:
            raise SystemExit("the probe cell needs a scratch path as argv[4]")
        scratch = Path(sys.argv[4])
        if not scratch.exists():
            import xarray as xr

            grid, n_time = 32, 60
            rng = np.random.default_rng(0)
            xr.Dataset(
                {
                    "sla": (
                        ("time", "y", "x"),
                        rng.standard_normal((n_time, grid, grid)).astype("float32"),
                    )
                },
                coords={
                    "time": np.array(
                        [
                            np.datetime64("2000-01-01") + np.timedelta64(31 * i, "D")
                            for i in range(n_time)
                        ]
                    ),
                    "y": np.arange(grid, dtype="float64"),
                    "x": np.arange(grid, dtype="float64"),
                },
            ).to_zarr(scratch, mode="w")
        held = np.ones(1024 * 1024 // 8, dtype="float64")
    elif cell == "refault":
        # A FILE-BACKED WORKING SET, WHICH IS THE SAFE WAY TO CONSTRUCT A REAL
        # STALL. The `thrash` cell asks the kernel to take anonymous pages this
        # process is touching, and the bounded generator will not push it that
        # far -- measured: 3328 MB held with 2078 MB still available, and the
        # gate read 0.13 ms/s because nothing this process wanted was ever
        # taken. Clean file pages ARE evicted under the same pressure, and
        # reading them back is a refault, which is exactly what PSI `full`
        # counts. **No OOM risk**: the pages are clean and the kernel can drop
        # them at will.
        if len(sys.argv) <= 4:
            # NAMED BY THE CALLER, NEVER DEFAULTED. The file is gigabytes and
            # lives for the run; a default path is how one gets left behind on a
            # box whose free space is itself part of the measurement.
            raise SystemExit("the refault cell needs a scratch path as argv[4]")
        scratch = Path(sys.argv[4])
        if not scratch.exists() or scratch.stat().st_size < touch_mb * 1024 * 1024:
            with scratch.open("wb") as handle:
                chunk = np.ones(64 * 1024 * 1024 // 8, dtype="float64")
                for _ in range(touch_mb // 64):
                    handle.write(chunk.tobytes())
        mapped = np.memmap(scratch, dtype="float64", mode="r")
        held = np.ones(1024 * 1024 // 8, dtype="float64")
    else:
        held = np.ones(touch_mb * 1024 * 1024 // 8, dtype="float64")
    reference = machine.current_rss_bytes()

    pressure = None
    if cell in {"thrash", "refault", "quiet"}:
        # S603: this module's sibling, run under this interpreter.
        pressure = subprocess.Popen(  # noqa: S603
            [sys.executable, str(PRESSURE), str(int(seconds) + 15)],
            stdout=subprocess.PIPE,
            text=True,
        )
        # Wait for it to report that it has taken what it is going to take.
        if pressure.stdout is None:
            raise SystemExit("the pressure generator produced no stdout to read")
        held_line = pressure.stdout.readline().strip()
    else:
        held_line = "no pressure"

    started = time.monotonic()
    samples: list[tuple[float, float]] = []
    reading = machine.memory_stall_us()
    block_start = None if reading is None else reading[0]

    with StallWatch(reader=machine.memory_stall_us) as watch:
        while time.monotonic() - started < seconds:
            if cell == "thrash":
                # RE-TOUCH WHAT THE KERNEL IS TAKING. A stall is time spent
                # WAITING on memory, so it only appears where the process wants
                # a page back; the quiet cell exists to show the same pressure
                # with that want removed.
                held += 1.0
            elif cell == "probe":
                # THE MEASUREMENT'S OWN ALLOCATION, WHICH IS THE CASE THE
                # WINDOWED READING TURNED OUT TO BE SENSITIVE TO. `measure_floor`
                # spawns a five-rung ladder of children, each of which imports
                # numpy, numba and zarr and builds a ~220 MB working set from
                # nothing -- a burst inside one second, on a box whose page cache
                # the kernel must then evict. **No external pressure at all in
                # this cell**: whatever it reads, this process caused.
                from metamer.core.memory import measure_floor

                measure_floor(data_uri=str(scratch), variable="sla")
            elif cell == "refault" and mapped is not None:
                # SWEEP THE WHOLE MAPPING, so every page the kernel dropped is
                # asked for again. The sum is not the point and is discarded.
                float(mapped.sum())
            else:
                time.sleep(0.25)
            now = machine.memory_stall_us()
            if now is not None:
                samples.append((time.monotonic() - started, float(now[0])))

    elapsed = time.monotonic() - started
    reading = machine.memory_stall_us()
    block_end = None if reading is None else reading[0]
    ended = machine.current_rss_bytes()
    shortfall = machine.reclaim_shortfall_bytes(reference)

    if pressure is not None:
        pressure.wait(timeout=seconds + 120)

    print(
        json.dumps(
            {
                "cell": cell,
                "seconds": round(elapsed, 1),
                "touch_mb": touch_mb,
                "pressure": held_line,
                "window_s": STALL_WINDOW_S,
                # WHAT THE GATE NOW READS.
                "windowed_max_us_per_s": watch.rate,
                "windowed_samples": watch.samples,
                # WHAT IT READ BEFORE, ON THE SAME RUN.
                "whole_block_us_per_s": (
                    None
                    if block_start is None or block_end is None
                    else (block_end - block_start) / max(elapsed, 1e-9)
                ),
                # AND THE SAME ARITHMETIC OVER THIS SCRIPT'S OWN SAMPLES, as a
                # second construction of the windowed figure that does not share
                # the watch's sampling thread.
                "windowed_max_from_own_samples": max_windowed_rate(
                    samples, STALL_WINDOW_S
                ),
                # **THE SPECTRUM, BECAUSE THE WINDOW IS NOW THE LIVE PARAMETER.**
                # A self-inflicted allocation burst is sub-second and a sustained
                # external squeeze is not, so the two separate by window length
                # if they separate at all -- and that is a measurement rather
                # than an argument about which one a limit should catch.
                "window_spectrum_us_per_s": {
                    str(w): max_windowed_rate(samples, w)
                    for w in (0.5, 1.0, 2.0, 5.0, 10.0, 30.0)
                },
                "own_samples": len(samples),
                # THE CONDITION THAT CAN SEE QUIET RECLAIM.
                "reference_bytes": reference,
                "end_bytes": ended,
                "reclaim_shortfall_bytes": shortfall,
                "working_set_delta_mb": round((ended - reference) / 1e6, 2),
                "available_mb_at_end": available_mb(),
            }
        )
    )


if __name__ == "__main__":
    main()
