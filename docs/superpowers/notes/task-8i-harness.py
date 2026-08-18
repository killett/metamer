"""Task 8i: three reclaim-detection candidates, read around one measurement window.

Runs the Task 8a fixture at a fixed side and varies ONLY the idle time held
inside the tile callback, which is the variable Task 8a showed produces the
entire `peak - current` effect. Around each run it records every candidate:

  A  cgroup `memory.stat` pgsteal   -- per-cgroup, moving, not per-process
  B  /proc/vmstat pgsteal_*         -- system-wide, always maintained
  C  the process's own end-of-window working set against its own floor

A dose-response across idle time is what separates a gate that tracks the damage
from one that merely correlates with the box being busy.

Usage: probe8i.py <workdir> <side> <live_fraction> <idle_seconds>
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

PROBE = """
import json, time
import zarr
from metamer.batch.run import run
from metamer.core import machine
from metamer.core.memory import FloorReport

pinned = FloorReport(
    pre_warm_bytes={floor}, post_warm_bytes={floor},
    with_input_bytes={floor}, peak_bytes={floor}, components={{}},
)

def status(field):
    with open("/proc/self/status") as handle:
        for line in handle:
            if line.startswith(field + ":"):
                return float(line.split()[1]) * 1024.0
    raise RuntimeError(field)

readings = []

def seen(tile):
    before = (status("VmHWM"), status("VmRSS"))
    time.sleep({idle})
    readings.append(
        {{
            "hwm_before_idle": before[0],
            "rss_before_idle": before[1],
            "hwm": status("VmHWM"),
            "rss": status("VmRSS"),
        }}
    )

report = run({config!r}, {store!r}, on_tile_written=seen, floor=pinned)
attrs = dict(zarr.open_group({store!r}, mode="r").attrs)
print(json.dumps({{
    "tile_side": report.tile_side,
    "tiles_written": report.tiles_written,
    "readings": readings,
    "floor": attrs.get("floor"),
}}))
"""

LAUNCHER = """
import subprocess, sys
out = subprocess.run([sys.executable, "-c", {probe!r}], capture_output=True, text=True)
sys.stdout.write(out.stdout)
sys.stderr.write(out.stderr)
sys.exit(out.returncode)
"""


def counters() -> dict[str, int | None]:
    """Read every reclaim counter this box exposes, right now.

    Returns:
        `cgroup_pgsteal`, `vmstat_pgsteal` and `available_bytes`, each None
        where the file or field is absent. **None rather than 0**: a counter
        that is not maintained and a counter reporting no reclaim are the same
        observation otherwise, which is the fill-value rule at a gate (a0).
    """
    out: dict[str, int | None] = {
        "cgroup_pgsteal": None,
        "vmstat_pgsteal": None,
        "available_bytes": None,
    }
    try:
        for line in Path("/sys/fs/cgroup/memory.stat").read_text().splitlines():
            if line.startswith("pgsteal "):
                out["cgroup_pgsteal"] = int(line.split()[1])
    except OSError:
        pass
    try:
        total = 0
        seen_any = False
        for line in Path("/proc/vmstat").read_text().splitlines():
            name, _, value = line.partition(" ")
            if name.startswith("pgsteal_"):
                total += int(value)
                seen_any = True
        out["vmstat_pgsteal"] = total if seen_any else None
    except OSError:
        pass
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"):
                out["available_bytes"] = int(line.split()[1]) * 1024
    except OSError:
        pass
    return out


def build_input(path: Path, *, side: int, live_fraction: float, n_time: int) -> str:
    """Write a `side x side` grid of white noise, mostly masked if asked.

    Args:
        path: Destination store path.
        side: Grid side; the tile side matches it, so the run is one tile.
        live_fraction: Fraction of series left with data.
        n_time: Series length.

    Returns:
        The store path.
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


def main() -> None:
    """Run one point and print every candidate's reading around its window."""
    work = Path(sys.argv[1])
    side, live, idle = int(sys.argv[2]), float(sys.argv[3]), int(sys.argv[4])
    work.mkdir(parents=True, exist_ok=True)
    tag = f"s{side}_l{live}_i{idle}"
    shutil.rmtree(work / f"store_{tag}.zarr", ignore_errors=True)
    uri = build_input(work / f"in_{tag}.zarr", side=side, live_fraction=live, n_time=60)

    from metamer.batch.tiling import budget_bytes_for_side
    from metamer.core.memory import FloorReport, measure_floor

    floor = measure_floor(data_uri=uri, variable="sla")
    pinned = FloorReport(
        pre_warm_bytes=floor.peak_bytes,
        post_warm_bytes=floor.peak_bytes,
        with_input_bytes=floor.peak_bytes,
        peak_bytes=floor.peak_bytes,
        components={},
    )
    budget = (
        budget_bytes_for_side(
            side=side, floor=pinned, d=1, k_beta=4, p_max=3, n_time=60, n_models=2
        )
        / 1e9
    )
    config = work / f"c_{tag}.toml"
    config.write_text(CONFIG.format(uri=uri, budget=f"{budget:.9f}"))
    store = work / f"store_{tag}.zarr"
    probe = PROBE.format(
        config=str(config), store=str(store), floor=floor.peak_bytes, idle=idle
    )

    before = counters()
    start = time.monotonic()
    # S603: the argv is this module's own template with paths substituted in as
    # Python literals, run under this interpreter.
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", LAUNCHER.format(probe=probe)],
        capture_output=True,
        text=True,
        check=False,
    )
    window = time.monotonic() - start
    after = counters()
    if result.returncode != 0:
        print(json.dumps({"error": result.stderr[-2000:]}))
        raise SystemExit(1)

    payload = json.loads(result.stdout.strip().splitlines()[-1])
    payload.update(
        {
            "side": side,
            "live_fraction": live,
            "idle_s": idle,
            "batch": side * side,
            "wall_s": round(window, 1),
            "before": before,
            "after": after,
            "cgroup_pgsteal_per_s": (
                None
                if before["cgroup_pgsteal"] is None or after["cgroup_pgsteal"] is None
                else round(
                    (after["cgroup_pgsteal"] - before["cgroup_pgsteal"]) / window, 1
                )
            ),
            "vmstat_pgsteal_per_s": (
                None
                if before["vmstat_pgsteal"] is None or after["vmstat_pgsteal"] is None
                else round(
                    (after["vmstat_pgsteal"] - before["vmstat_pgsteal"]) / window, 1
                )
            ),
        }
    )
    print(json.dumps(payload))


if __name__ == "__main__":
    main()
