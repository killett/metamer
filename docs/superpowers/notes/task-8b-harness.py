"""Task 8b: one ladder point, both disputed instruments, fixture fully recorded.

**WHY THIS EXISTS.** Two ladders disagree about the per-series cost by 1.86x --
Task 7's 1021.6 +/- 134.7 and Task 8's 1900.9 +/- 84.1 -- and Task 8's fixture
cannot be rebuilt from what was recorded. Two measurements of one named quantity
are not comparable unless they share a recorded precondition set, so this harness
records the whole set and prints it back with every reading.

**THE TWO LADDERS ALSO USED TWO DIFFERENT INSTRUMENTS AND NO RUN HAS REPORTED
BOTH.** Task 7's `memory._CALIBRATION_CHILD` takes the maximum of
`current_rss_bytes()` sampled every 2 ms on a thread inside the measured process;
Task 8 took `machine.peak_rss_bytes()`, which is `ru_maxrss`. A sampler cannot see
a transient shorter than its period and a kernel watermark always can. **Every
point here reports both, plus `VmHWM`** -- which is `max(hiwater_rss, current)`
and therefore can never sit below `VmRSS` while `ru_maxrss` can, measured by
664 kB at side 16 in Task 8a.

**WHAT IS CONTROLLED, AND EACH CONTROL ANSWERS A NAMED DEFECT IN THE OLD LADDER.**

- **The live-series count is constant across the ladder**, not the total. A
  wholly-masked series short-circuits in `optimize.py:517` before any design or
  optimizer exists, so the fit cost is `live * cost_per_fit` with `live` fixed
  while `B = side**2` varies. The tile block, the output slots and the store path
  are shaped by the arrays and never by the outcomes, so the per-series terms
  under measurement are untouched by the masking. **This is what stops run length
  being monotonic in B, which is the confound Task 8a found in Task 8's ladder.**
- **The remainder of the wall clock is padded to a constant**, inside the tile
  callback and therefore after the peak has been set, so padding can inflate no
  reading. Padding at the short points, never truncation at the long ones.
- **The chunking is set explicitly and read back.** Default `to_zarr` chunking
  makes the largest assembly span non-monotonic in B -- 256, 1024, 2304, **2048**,
  2304 across Task 8's five sides -- so an unrecorded chunking is a second
  variable moving with the abscissa. It is also the lever: `assemble_tile` holds
  one span's float32 and its float64 cast alive together, which is 720 B per
  series of the span at N = 60, so a fine chunking puts that transient in the
  intercept and a whole-grid chunking puts it in the slope.
- **The reclaim witness is read IN THE CHILD**, which is where Task 8i said it
  must be read: a parent's working set says nothing about what was taken from its
  child. Zero means "no shortfall seen", never "no reclaim happened".

Usage:
    task-8b-harness.py <workdir> <side> <live> <chunk> <target_s> [tag]
                       [n_time] [candidate_set]

`<chunk>` is `fine` (16 x 16 spatial), `whole` (one spatial chunk per grid) or
`default` (whatever `to_zarr` picks, which is what every fixture this project
has measured used). `<live>` is the live-series count, or **-1 for every
series**, which is Task 8's own setting. `<target_s>` is the wall clock every
point is padded up to; 0 disables padding. `<n_time>` and `<candidate_set>` are
the two levers that separate a data-shaped term from a slot-shaped one; see
`CANDIDATE_SETS`.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import xarray as xr

from metamer.core.machine import available_ram_bytes, memory_stall_us

#: The model and the geometry, stated here and echoed into every payload. The
#: analytic per-series cost at these values is `60 * 9 + output_slot_bytes(2, 3,
#: 4)` = 540 + 386 = **926 B/series**, which is the figure both disputed ladders
#: are compared against.
N_TIME = 60
SIGNAL_TERMS = ("constant", "trend", "annual")
CRITERIA = ("aic",)
OBJECTIVE = "reml"
THREADS = 1
MAX_ITER = 1
K_BETA = 4
P_MAX = 3
STATE_DIM = 1
SEED = 0

#: THE TWO LEVERS THAT SEPARATE A DATA-SHAPED TERM FROM A SLOT-SHAPED ONE.
#: `resident_bytes_per_series` is `n_time * 9 + output_slot_bytes(n_models,
#: p_max, k_beta)`, so `n_time` moves only the first and the candidate count
#: moves only the second. **Both sets hold `p_max` at 3 and `k_beta` at 4**, so
#: nothing else in the formula moves: `matern32` carries two free parameters, so
#: `white + matern32` is 3 like `white + matern12`, and `white + white` is 2.
#: A term measured at one fixture has an unknown DEPENDENCE, and correcting a
#: magnitude without its variables is (a7) and F5 exactly.
CANDIDATE_SETS = {
    # **m1, m4 AND m7 WERE ADDED 2026-08-21 FOR THE 193-VERSUS-240
    # RECONCILIATION, AND THEY CHANGE NOTHING m2 OR m6 DO.** Every set holds
    # `p_max` at 3 -- each contains a 3-parameter candidate and none contains a
    # 4-parameter one -- so the charged `24*p_max + 16*k_beta + 57` = 193 is
    # identical across the ladder and the lever moves M alone. **SEVEN IS THE
    # CEILING at p_max = 3**: the vocabulary is white (1 free parameter),
    # matern12 (2) and matern32 (2), so the candidates with p <= 3 are exactly
    # the seven in `m7`. An eighth raises `p_max`, which moves the charged
    # figure itself and confounds the lever with the quantity under measurement.
    "m1": ("white + matern12",),
    "m2": ("white", "white + matern12"),
    "m6": (
        "white",
        "matern12",
        "matern32",
        "white + white",
        "white + matern12",
        "white + matern32",
    ),
    "m4": (
        "white",
        "matern12",
        "white + white",
        "white + matern12",
    ),
    "m7": (
        "white",
        "matern12",
        "matern32",
        "white + white",
        "white + matern12",
        "white + matern32",
        "white + white + white",
    ),
}

CONFIG = """
data_uri = "{uri}"
variable = "sla"
signal_terms = ["constant", "trend", "annual"]
candidates = {candidates}
criteria = ["aic"]
memory_budget_gb = {budget}
objective = "reml"
threads = 1
"""

# Runs in the grandchild, behind the bare launcher, because `ru_maxrss` is
# inherited across fork/exec. `grid = side`, so the tile loop writes exactly one
# tile and `on_tile_written` fires once -- between the tile's data write and its
# completion bit, with the block still alive.
PROBE = """
import json, os, threading, time
import zarr
from metamer.core import machine
from metamer.core.memory import FloorReport

FLOOR = {floor}
pinned = FloorReport(
    pre_warm_bytes=FLOOR, post_warm_bytes=FLOOR,
    with_input_bytes=FLOOR, peak_bytes=FLOOR, components={{}},
)
started = time.monotonic()


def status(field):
    with open("/proc/self/status") as handle:
        for line in handle:
            if line.startswith(field + ":"):
                return float(line.split()[1]) * 1024.0
    raise RuntimeError(field)


# TASK 7's INSTRUMENT, REPRODUCED EXACTLY: the maximum of the working set,
# sampled every 2 ms on a thread inside the process whose residency is the
# subject. It is here to be COMPARED against the watermark, not because it is
# trusted -- `_CALIBRATION_CHILD`'s own comment says a sampler that records
# nothing leaves every assertion in the suite green.
sampled = [machine.current_rss_bytes()]
sampled_at = [0.0]
stop = threading.Event()


def _sample():
    while not stop.is_set():
        now = machine.current_rss_bytes()
        if now > sampled[0]:
            sampled[0] = now
            sampled_at[0] = time.monotonic() - started
        time.sleep(0.002)


sampler = threading.Thread(target=_sample, daemon=True)
sampler.start()

from metamer.batch.run import run

baseline = machine.current_rss_bytes()
readings = {{}}


def seen(tile):
    # AT END OF TILE, WITH THE BLOCK STILL ALIVE. Everything is read before the
    # pad and the working set again after it, so the pad's own effect on the
    # reading is visible rather than assumed.
    readings["at_tile_s"] = time.monotonic() - started
    readings["ru_maxrss_at_tile"] = machine.peak_rss_bytes()
    readings["vmhwm_at_tile"] = status("VmHWM")
    readings["current_at_tile"] = machine.current_rss_bytes()
    readings["shortfall_at_tile"] = machine.reclaim_shortfall_bytes(FLOOR)
    target = {target}
    if target:
        remaining = target - (time.monotonic() - started)
        if remaining > 0:
            time.sleep(remaining)
    readings["current_after_pad"] = machine.current_rss_bytes()
    readings["shortfall_after_pad"] = machine.reclaim_shortfall_bytes(FLOOR)
    readings["vmhwm_after_pad"] = status("VmHWM")


report = run(
    {config!r}, {store!r}, on_tile_written=seen, floor=pinned, max_iter={max_iter}
)
stop.set()
sampler.join()

group = zarr.open_group({store!r}, mode="r")
outcome = group["status"]["outcome"][:]
print(json.dumps({{
    "tile_side": report.tile_side,
    "tiles_total": report.tiles_total,
    "tiles_written": report.tiles_written,
    "baseline": baseline,
    "sampled_peak": sampled[0],
    "sampled_peak_at_s": sampled_at[0],
    "ru_maxrss_end": machine.peak_rss_bytes(),
    "vmhwm_end": status("VmHWM"),
    "current_end": machine.current_rss_bytes(),
    "shortfall_end": machine.reclaim_shortfall_bytes(FLOOR),
    "readings": readings,
    "ok": int((outcome == 0).sum()),
    "attempted": int((outcome != 8).sum()),
    "store_floor_attr": dict(group.attrs).get("floor"),
    "phase_seconds": dict(report.phase_seconds),
    "child_wall_s": time.monotonic() - started,
}}))
"""

LAUNCHER = """
import subprocess, sys
out = subprocess.run([sys.executable, "-c", {probe!r}], capture_output=True, text=True)
sys.stdout.write(out.stdout)
sys.stderr.write(out.stderr)
sys.exit(out.returncode)
"""


def build_input(
    path: Path, *, grid: int, live: int, chunk_side: int | None, n_time: int = N_TIME
) -> str:
    """Write the fixture: white noise, all but `live` series wholly masked.

    **THE DISTRIBUTION IS PART OF THE FIXTURE AND TASK 8 DID NOT RECORD ITS
    OWN.** Standard normal float32 from `np.random.default_rng(0)`, series in
    row-major grid order, the first `live` of them left with data and every
    other one set wholly to NaN. A wholly-masked series short-circuits before
    any design exists, so the live count is what sets the fit cost while the
    tile geometry is set by `grid`.

    Args:
        path: Destination store path.
        grid: Grid side. The tile side is chosen to match, so the run is one
            tile and no preemption path is involved.
        live: How many series keep their data. Negative means every series.
        chunk_side: Spatial chunk side, with the time axis chunked whole. **None
            leaves `to_zarr`'s own chunking**, which is what every fixture this
            project has measured used and what a rebuild of Task 8's ladder has
            to reproduce.
        n_time: Series length.

    Returns:
        The store path as a URI string.
    """
    rng = np.random.default_rng(SEED)
    values = rng.standard_normal((n_time, grid, grid)).astype("float32")
    if live >= 0:
        flat = values.reshape(n_time, -1)
        keep = np.zeros(flat.shape[1], dtype=bool)
        keep[: min(live, flat.shape[1])] = True
        flat[:, ~keep] = np.nan
        values = flat.reshape(n_time, grid, grid)
    origin = np.datetime64("2000-01-01")
    axis = np.array([origin + np.timedelta64(31 * i, "D") for i in range(n_time)])
    dataset = xr.Dataset(
        {"sla": (("time", "y", "x"), values)},
        coords={
            "time": axis,
            "y": np.arange(grid, dtype="float64"),
            "x": np.arange(grid, dtype="float64"),
        },
    )
    if chunk_side is not None:
        dataset["sla"].encoding["chunks"] = (
            n_time,
            min(chunk_side, grid),
            min(chunk_side, grid),
        )
    dataset.to_zarr(path, mode="w")
    return str(path)


def fixture_facts(uri: str, side: int) -> dict[str, Any]:
    """Read the fixture's own chunking and span count back out of the store.

    **READ BACK RATHER THAN ASSERTED FROM THE REQUEST.** What was asked for and
    what the writer produced are different facts, and the chunking is one of the
    four things Task 8's record is missing.

    Args:
        uri: The input store.
        side: The tile side this point will run at.

    Returns:
        The chunk shape, the span count and the largest span, in series.
    """
    from metamer.batch.input import check_contract, open_input
    from metamer.batch.tiling import Tile, assembly_spans, chunk_shape

    handle = open_input(uri, "sla")
    check_contract(handle)
    tile = Tile(y_start=0, y_stop=side, x_start=0, x_stop=side)
    spans = assembly_spans(handle, tile)
    return {
        "chunk_shape": list(chunk_shape(handle)),
        "n_spans": len(spans),
        "largest_span_series": max(span.n_series for span in spans),
    }


def main() -> None:
    """Run one ladder point and print it, with its whole fixture, as JSON."""
    work = Path(sys.argv[1])
    side = int(sys.argv[2])
    live = int(sys.argv[3])
    chunking = sys.argv[4]
    target = float(sys.argv[5])
    tag = sys.argv[6] if len(sys.argv) > 6 else "a"
    n_time = int(sys.argv[7]) if len(sys.argv) > 7 else N_TIME
    which = sys.argv[8] if len(sys.argv) > 8 else "m2"
    if chunking not in {"fine", "whole", "default"}:
        raise SystemExit(
            f"chunk must be 'fine', 'whole' or 'default', got {chunking!r}"
        )
    if which not in CANDIDATE_SETS:
        raise SystemExit(f"candidate set must be one of {sorted(CANDIDATE_SETS)}")
    chunk_side = {"fine": 16, "whole": side, "default": None}[chunking]
    candidates = CANDIDATE_SETS[which]
    n_models = len(candidates)

    work.mkdir(parents=True, exist_ok=True)
    name = f"s{side}_l{live}_{chunking}_t{int(target)}_n{n_time}_{which}_{tag}"
    # A store left from a previous invocation would be RESUMED, and a resumed
    # run writes no tiles -- so the callback never fires and the readings come
    # back empty rather than wrong.
    shutil.rmtree(work / f"store_{name}.zarr", ignore_errors=True)
    uri = build_input(
        work / f"in_{name}.zarr",
        grid=side,
        live=live,
        chunk_side=chunk_side,
        n_time=n_time,
    )

    from metamer.batch.tiling import budget_bytes_for_side
    from metamer.core.memory import FloorReport, measure_floor

    # THE FLOOR IS MEASURED ON THIS INPUT AND PINNED. `measure_floor` takes a
    # `data_uri`, so the floor is input-dependent by construction -- 1.28 MB
    # across three fixtures, measured at Task 9 -- and an unpinned floor lands
    # the run on a side it was not asked for, because the budget window that
    # selects one multiple of the base is narrower than the floor's own drift.
    floor = measure_floor(data_uri=uri, variable="sla")
    pinned = FloorReport(
        pre_warm_bytes=floor.peak_bytes,
        post_warm_bytes=floor.peak_bytes,
        with_input_bytes=floor.peak_bytes,
        peak_bytes=floor.peak_bytes,
        components={},
    )
    # **THE MODEL COMES FROM THE PRODUCTION GEOMETRY, NOT FROM THIS FILE'S
    # CONSTANTS.** Hand-passing `d`, `k_beta` and `p_max` measured them as
    # whatever the harness's author believed: at the six-candidate set the
    # composite state dimension is not 1, the budget came out too small by the
    # solver-state difference, and side 32 derived **16** and ran four tiles.
    # Every reading from such a point is at a different B than the one recorded.
    # `run_geometry(...).tile_kwargs()` is what `calibrate` asks, and the budget
    # does not enter it -- so a placeholder budget is written first, the geometry
    # is read, and the config is rewritten. (j2), at the harness's own inputs.
    config = work / f"c_{name}.toml"
    candidate_json = json.dumps(list(candidates))
    config.write_text(CONFIG.format(uri=uri, budget="1.0", candidates=candidate_json))
    from metamer.batch.input import check_contract, open_input
    from metamer.batch.run import run_geometry
    from metamer.batch.validation import load_config

    loaded = load_config(str(config))
    handle = open_input(loaded.data_uri, loaded.variable)
    model = run_geometry(loaded, handle, check_contract(handle)).tile_kwargs()
    budget = budget_bytes_for_side(side=side, floor=pinned, **model) / 1e9
    config.write_text(
        CONFIG.format(uri=uri, budget=f"{budget:.9f}", candidates=candidate_json)
    )
    store = work / f"store_{name}.zarr"
    probe = PROBE.format(
        config=str(config),
        store=str(store),
        floor=floor.peak_bytes,
        target=target,
        max_iter=MAX_ITER,
    )

    stall_before = memory_stall_us()
    available_before = available_ram_bytes()
    start = time.monotonic()
    # S603: the argv is this module's own template with paths substituted in as
    # Python literals, run under this interpreter -- the construction
    # `core.memory` uses for every probe it spawns.
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", LAUNCHER.format(probe=probe)],
        capture_output=True,
        text=True,
        check=False,
    )
    window = time.monotonic() - start
    stall_after = memory_stall_us()
    if result.returncode != 0:
        print(json.dumps({"point": name, "error": result.stderr[-3000:]}))
        raise SystemExit(1)

    payload: dict[str, Any] = json.loads(result.stdout.strip().splitlines()[-1])
    payload.update(
        {
            "point": name,
            "tag": tag,
            "side": side,
            "batch": side * side,
            "live": live,
            "live_effective": side * side if live < 0 else min(live, side * side),
            "chunking": chunking,
            "target_s": target,
            "wall_s": round(window, 1),
            "budget_gb": budget,
            "floor_measured_here": floor.peak_bytes,
            "available_before": available_before,
            "available_after": available_ram_bytes(),
            "stall_ms_per_s": (
                None
                if stall_before is None or stall_after is None
                else round((stall_after[0] - stall_before[0]) / window / 1000, 4)
            ),
            "fixture": {
                "distribution": "standard normal float32, np.random.default_rng(0)",
                "seed": SEED,
                "n_time": n_time,
                "grid": side,
                "live_selection": "first `live` series in row-major grid order",
                "signal_terms": list(SIGNAL_TERMS),
                "candidates": list(candidates),
                "candidate_set": which,
                "criteria": list(CRITERIA),
                "objective": OBJECTIVE,
                "threads": THREADS,
                "max_iter": MAX_ITER,
                "k_beta": K_BETA,
                "p_max": P_MAX,
                "n_models": n_models,
                "tile_kwargs_from_run_geometry": {
                    k: (v if not hasattr(v, "value") else v.value)
                    for k, v in model.items()
                },
                **fixture_facts(uri, side),
            },
        }
    )
    print(json.dumps(payload))


if __name__ == "__main__":
    main()
