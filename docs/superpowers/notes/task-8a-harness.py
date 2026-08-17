"""Task 8a Arms A and C: peak against current at end of tile, fit and masked.

One run per invocation, in a fresh child behind a bare launcher, because
`peak_rss_bytes` is inherited across fork/exec. `grid = side`, so the tile loop
writes exactly one tile and `on_tile_written` fires once -- at end of tile,
which is where `peak - current` is read.

Usage: arm.py <workdir> <side> <live_fraction> [--allocate MB]
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import xarray as xr

from metamer.core.machine import memory_stall_us

CONFIG = """
data_uri = "{uri}"
variable = "sla"
signal_terms = ["constant", "trend", "annual"]
candidates = ["white", "white + matern12"]
criteria = ["aic"]
memory_budget_gb = {budget}
objective = "reml"
threads = 1
"""

# Runs in the grandchild. `grid = side` by construction, so one tile. The
# watermark and the working set are read in the SAME callback, between the
# tile's data write and its completion bit.
PROBE = """
import json, sys
import zarr
from metamer.batch.run import run
from metamer.core import machine
from metamer.core.memory import FloorReport

# THE FLOOR IS PINNED, as `calibrate` pins it across a ladder: the derived side
# is a function of the floor, the floor is measured fresh per run and moves by
# megabytes, and the budget window that selects one multiple of the base is
# narrower than that -- so an unpinned floor lands the run on a side it was not
# asked for. Measured once in the parent, on THIS input.
pinned = FloorReport(
    pre_warm_bytes={floor}, post_warm_bytes={floor},
    with_input_bytes={floor}, peak_bytes={floor}, components={{}},
)

def vmhwm():
    # `machine.peak_rss_bytes` is `ru_maxrss`, which the kernel maintains
    # LAZILY in `mm->hiwater_rss`; `/proc/self/status`'s VmHWM prints
    # `max(hiwater_rss, current rss)`, so it can never sit below VmRSS while
    # ru_maxrss can -- measured at side 16, by 664 kB. A `peak - current` that
    # can go negative is the wrong instrument for a difference of that size, so
    # both are recorded and the discrepancy is reported rather than hidden.
    with open("/proc/self/status") as handle:
        for line in handle:
            if line.startswith("VmHWM:"):
                return float(line.split()[1]) * 1024.0
    raise RuntimeError("no VmHWM")

readings = []
{allocation}

def seen(tile):
    {inject}
    # THE ELAPSED-TIME CONTROL. The full-fit run at side 48 read a working set
    # 85 MB BELOW its own measured floor after 4073 s, which is reclaim rather
    # than a transient. Holding everything else fixed and varying only the time
    # the process spends alive is what tells those two apart.
    import time as _t
    _t.sleep({idle})
    readings.append(
        (machine.peak_rss_bytes(), machine.current_rss_bytes(), vmhwm())
    )

report = run({config!r}, {store!r}, on_tile_written=seen, floor=pinned)
attrs = dict(zarr.open_group({store!r}, mode="r").attrs)
print(json.dumps({{
    "tile_side": report.tile_side,
    "tiles_total": report.tiles_total,
    "tiles_written": report.tiles_written,
    "readings": readings,
    "floor": attrs.get("floor"),
    "phase_seconds": dict(report.phase_seconds),
}}))
"""

LAUNCHER = """
import subprocess, sys
out = subprocess.run([sys.executable, "-c", {probe!r}], capture_output=True, text=True)
sys.stdout.write(out.stdout)
sys.stderr.write(out.stderr)
sys.exit(out.returncode)
"""


def build_input(path: Path, *, side: int, live_fraction: float, n_time: int) -> str:
    """Write a `side x side` grid of white noise, mostly masked if asked.

    A wholly-masked series short-circuits before any design or optimizer
    exists, so a mostly-masked input is the same tile geometry with the fit
    removed. Masking changes values, not shape.

    Args:
        path: Destination store path.
        side: Grid side; the tile side is chosen to match it.
        live_fraction: Fraction of series left with data.
        n_time: Series length.

    Returns:
        The store path as a URI string.
    """
    rng = np.random.default_rng(0)
    values = rng.standard_normal((n_time, side, side)).astype("float32")
    if live_fraction < 1.0:
        stride = int(round(1.0 / live_fraction))
        flat = values.reshape(n_time, -1)
        keep = np.zeros(flat.shape[1], dtype=bool)
        keep[::stride] = True
        flat[:, ~keep] = np.nan
        values = flat.reshape(n_time, side, side)
    origin = np.datetime64("2000-01-01")
    axis = np.array([origin + np.timedelta64(31 * i, "D") for i in range(n_time)])
    xr.Dataset(
        {"sla": (("time", "y", "x"), values)},
        coords={
            "time": axis,
            "y": np.arange(side, dtype="float64"),
            "x": np.arange(side, dtype="float64"),
        },
    ).to_zarr(path, mode="w")
    return str(path)


def budget_for(side: int, floor_bytes: int) -> float:
    """The smallest budget whose derived side is `side`, in SI GB.

    Args:
        side: The target tile side.
        floor_bytes: The pinned floor.

    Returns:
        `memory_budget_gb`.
    """
    from metamer.batch.tiling import budget_bytes_for_side
    from metamer.core.memory import FloorReport

    floor = FloorReport(
        pre_warm_bytes=floor_bytes,
        post_warm_bytes=floor_bytes,
        with_input_bytes=floor_bytes,
        peak_bytes=floor_bytes,
        components={},
    )
    return (
        budget_bytes_for_side(
            side=side, floor=floor, d=1, k_beta=4, p_max=3, n_time=60, n_models=2
        )
        / 1e9
    )


def main() -> None:
    """Run one arm point and print its readings as JSON."""
    work = Path(sys.argv[1])
    side = int(sys.argv[2])
    live = float(sys.argv[3])
    inject_mb = int(sys.argv[4]) if len(sys.argv) > 4 else 0
    idle = int(sys.argv[5]) if len(sys.argv) > 5 else 0

    work.mkdir(parents=True, exist_ok=True)
    tag = f"s{side}_l{live}_a{inject_mb}_i{idle}"
    # A store left from a previous invocation would be RESUMED, and a resumed
    # run writes no tiles -- so the callback never fires and the readings come
    # back empty rather than wrong. Removed rather than reused.
    shutil.rmtree(work / f"store_{tag}.zarr", ignore_errors=True)
    uri = build_input(work / f"in_{tag}.zarr", side=side, live_fraction=live, n_time=60)

    from metamer.core.memory import measure_floor

    floor = measure_floor(data_uri=uri, variable="sla")
    budget = budget_for(side, floor.peak_bytes)
    config = work / f"c_{tag}.toml"
    config.write_text(CONFIG.format(uri=uri, budget=f"{budget:.9f}"))
    store = work / f"store_{tag}.zarr"

    allocation = "import numpy as np" if inject_mb else ""
    inject = (
        # EVERY page is touched, not every 4096th element. `np.zeros` calloc's
        # lazily, so an array is not resident until written: `block[::4096]`
        # touches one float64 per 32 kB -- one page in eight -- and the control
        # reported 8.0 MB for a 64 MB block. Measured, and the arithmetic
        # predicts exactly that, so the instrument was right and the injection
        # was not.
        f"block = np.zeros({inject_mb} * 1024 * 1024 // 8); block[:] = 1.0; del block"
        if inject_mb
        else "pass"
    )
    probe = PROBE.format(
        config=str(config),
        store=str(store),
        allocation=allocation,
        inject=inject,
        floor=floor.peak_bytes,
        idle=idle,
    )

    # `memory_stall_us` returns None where neither PSI file exists, and a
    # missing instrument must never read as zero pressure (a0) -- so the rate
    # is reported as None rather than as a clean bill of health.
    before = memory_stall_us()
    start = time.monotonic()
    # S603: the argv is this module's own template with paths substituted in
    # as Python literals, run under this interpreter -- the same construction
    # `core.memory` uses for every probe it spawns.
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", LAUNCHER.format(probe=probe)],
        capture_output=True,
        text=True,
        check=False,
    )
    window = time.monotonic() - start
    after = memory_stall_us()
    if result.returncode != 0:
        print(json.dumps({"error": result.stderr[-3000:]}))
        raise SystemExit(1)

    payload = json.loads(result.stdout.strip().splitlines()[-1])
    payload.update(
        {
            "side": side,
            "live_fraction": live,
            "injected_mb": inject_mb,
            "idle_s": idle,
            "batch": side * side,
            "budget_gb": budget,
            "floor_measured_here": floor.peak_bytes,
            "wall_s": round(window, 1),
            "stall_ms_per_s": (
                None
                if before is None or after is None
                else round((after[0] - before[0]) / window / 1000, 4)
            ),
        }
    )
    print(json.dumps(payload))


if __name__ == "__main__":
    main()
