"""OQ18 Task A: does freeing the tile block before the store write move the peak?

**WHY THIS EXISTS.** `--memory-budget` bounds process **peak** RSS (Q1, settled
at the 2b brainstorm) and `tiling.tile_side_for` divides the block budget by
`memory.resident_bytes_per_series`, which Task 8b measured as a model of
**residency and not peak** -- exact on its own subject (533.5 B/series against a
charged `n_time * 9` = 540) and silent about the rest, so the peak sits at
2410.0 +/- 46.0 against an analytic 926. **OQ18's first hypothesis is that this
is a PIPELINE defect rather than a formula one**: the block and the store write's
allocations coexist, and if they are made not to, peak and residency converge and
the model may need no new term.

**THIS IS A HYPOTHESIS TEST AND NOT A REPAIR.** It succeeds if the peak moves and
it succeeds if it does not: a peak that does not move says the store write is not
the dominant allocation despite the timestamp that was read as saying so, which
redirects the crossed 2 x 2 rather than licensing a correction.

**WHAT THE ARM DOES, AND WHY IT IS NOT AN EDIT TO `run.py`.** The `on` arm wraps
`batch.run.write_tile` and rebinds the caller's frame local `block` to `None`
through PEP 667's write-through proxy, immediately before the real write runs.
That is the same effect as inserting `block = None` between run.py:944 and 945,
and it needs no production change to measure. Deletion is refused by the proxy;
rebinding is not. **The equivalence rests on two line ranges that were read**:
nothing sits between `fit` returning and `write_tile` being called, and neither
`on_tile_written` nor `mark_complete` takes the block. **It does not cover the
multi-tile path** -- this harness runs one tile by construction, `grid = side`.

**WHAT IS INSTRUMENTED, AND THE LOCATION IS HALF OF IT.** A maximum is an argmax
as well as a value (8b's finding under its finding), so every phase boundary is
timestamped -- assemble, fit, the free, the write, the callback, the pad, the
completion bit, the tail -- and the 2 ms sampler's whole trace is kept in a
preallocated array so a **per-phase maximum** can be reported beside the overall
peak. "The peak fell by X" and "the peak moved from phase P to phase Q" are
different results and this prints both.

**THE POSITIVE CONTROL FOR AN ABSENCE.** "The resident set did not fall" and "the
free never happened" are one reading. `freed_bytes` says what the wrapper
released and `rss_before_free`/`rss_after_free` say what left the process, so the
allocator's behaviour is separable from the arm's. **At side 16, N = 60 the block
is 122 880 B, below glibc's 128 kB mmap threshold**, and a null there is
predicted rather than interpreted.

**AND THE ARM MUST NOT CHANGE THE ANSWER.** Every point digests the store's
`outcome` and `theta` arrays; the two arms at one point must agree exactly. A
retained view or a lazily derived array would show up as a crash or a difference,
which is what makes the reading worth taking at all.

Usage:
    oq18-a-harness.py <workdir> <side> <live> <chunk> <target_s> <free> [tag]
                      [n_time] [candidate_set]

Arguments are Task 8b's, with `<free>` -- 0 or 1 -- inserted: everything else is
held at that task's settings so the `off` arm is also a reproduction of its
ladder.
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

#: Task 8b's fixture constants, unchanged, because the `off` arm has to
#: reproduce its ladder before the `on` arm can be compared against anything.
N_TIME = 60
SIGNAL_TERMS = ("constant", "trend", "annual")
CRITERIA = ("aic",)
OBJECTIVE = "reml"
THREADS = 1
MAX_ITER = 1
K_BETA = 4
P_MAX = 3
SEED = 0

CANDIDATE_SETS = {
    "m2": ("white", "white + matern12"),
    "m6": (
        "white",
        "matern12",
        "matern32",
        "white + white",
        "white + matern12",
        "white + matern32",
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
# inherited across fork/exec.
PROBE = """
import hashlib, json, sys, threading, time
import numpy as np
import zarr
from metamer.core import machine
from metamer.core.memory import FloorReport

FLOOR = {floor}
FREE = {free}
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


# THE TRACE IS PREALLOCATED AND TOUCHED BEFORE THE BASELINE, so its own pages are
# in the floor of BOTH arms and cannot enter either arm's readings. Appending to
# a list instead would grow the resident set during the window being measured.
CAP = 60000
trace_t = np.zeros(CAP)
trace_v = np.zeros(CAP)
filled = [0]

sampled = [machine.current_rss_bytes()]
sampled_at = [0.0]
stop = threading.Event()


def _sample():
    while not stop.is_set():
        now = machine.current_rss_bytes()
        at = time.monotonic() - started
        index = filled[0]
        if index < CAP:
            trace_t[index] = at
            trace_v[index] = now
            filled[0] = index + 1
        if now > sampled[0]:
            sampled[0] = now
            sampled_at[0] = at
        time.sleep(0.002)


sampler = threading.Thread(target=_sample, daemon=True)
sampler.start()

import metamer.batch.run as runmod

marks = {{}}
free_report = {{}}


def _mark(name):
    marks[name] = time.monotonic() - started


def _wrap(name, real):
    def wrapper(*args, **kwargs):
        _mark(name + "_start")
        try:
            return real(*args, **kwargs)
        finally:
            _mark(name + "_end")
    return wrapper


real_write = runmod.write_tile


def write_tile(*args, **kwargs):
    # THE ARM. `sys._getframe(1)` is `run`'s own frame; rebinding its `block`
    # local through PEP 667's write-through proxy releases the tile block at the
    # moment a production `block = None` would, without editing `run.py`.
    if FREE:
        frame = sys._getframe(1)
        if "block" in frame.f_locals:
            free_report["freed_bytes"] = int(frame.f_locals["block"].nbytes)
            free_report["rss_before_free"] = machine.current_rss_bytes()
            free_report["at_s"] = time.monotonic() - started
            frame.f_locals["block"] = None
            free_report["rss_after_free"] = machine.current_rss_bytes()
        else:
            free_report["freed_bytes"] = 0
    _mark("write_start")
    try:
        return real_write(*args, **kwargs)
    finally:
        _mark("write_end")


runmod.write_tile = write_tile
runmod.assemble_tile = _wrap("assemble", runmod.assemble_tile)
runmod.fit = _wrap("fit", runmod.fit)
runmod.mark_complete = _wrap("mark", runmod.mark_complete)

baseline = machine.current_rss_bytes()
readings = {{}}


def seen(tile):
    # AT END OF TILE. Under the `on` arm the block is already gone by here, which
    # is the point: `at_tile` stops being a reading with the block alive, and the
    # difference between the arms at this field is the free's own magnitude.
    _mark("callback_start")
    readings["at_tile_s"] = time.monotonic() - started
    readings["ru_maxrss_at_tile"] = machine.peak_rss_bytes()
    readings["vmhwm_at_tile"] = status("VmHWM")
    readings["current_at_tile"] = machine.current_rss_bytes()
    readings["shortfall_at_tile"] = machine.reclaim_shortfall_bytes(FLOOR)
    target = {target}
    _mark("pad_start")
    if target:
        remaining = target - (time.monotonic() - started)
        if remaining > 0:
            time.sleep(remaining)
    _mark("pad_end")
    readings["current_after_pad"] = machine.current_rss_bytes()
    readings["shortfall_after_pad"] = machine.reclaim_shortfall_bytes(FLOOR)
    readings["vmhwm_after_pad"] = status("VmHWM")


report = runmod.run(
    {config!r}, {store!r}, on_tile_written=seen, floor=pinned, max_iter={max_iter}
)
_mark("run_end")
stop.set()
sampler.join()

used = filled[0]
times = trace_t[:used]
values = trace_v[:used]


def window(lo, hi):
    # PER-PHASE MAXIMUM AND ITS OWN ARGMAX. An empty window is reported as null
    # rather than as zero -- a phase too short for the 2 ms sampler to land in is
    # not a phase whose maximum is zero.
    if lo is None or hi is None:
        return None
    inside = (times >= lo) & (times <= hi)
    if not inside.any():
        return None
    subset_v = values[inside]
    subset_t = times[inside]
    index = int(subset_v.argmax())
    return {{
        "max": float(subset_v[index]),
        "at_s": float(subset_t[index]),
        "samples": int(inside.sum()),
    }}


def at(name):
    return marks.get(name)


phases = {{
    "pre_assemble": window(0.0, at("assemble_start")),
    "assemble": window(at("assemble_start"), at("assemble_end")),
    "fit": window(at("fit_start"), at("fit_end")),
    "write": window(at("write_start"), at("write_end")),
    "callback_pre_pad": window(at("callback_start"), at("pad_start")),
    "pad": window(at("pad_start"), at("pad_end")),
    "mark_complete": window(at("mark_start"), at("mark_end")),
    "tail": window(at("mark_end"), at("run_end")),
}}

group = zarr.open_group({store!r}, mode="r")
outcome = group["status"]["outcome"][:]
# NaN is the fill for the float arrays and NaN != NaN, so a raw digest over them
# would differ from itself; `nan_to_num` at a value the writer cannot emit keeps
# "not written" distinguishable from any real reading.
digest = hashlib.sha256()
digest.update(np.ascontiguousarray(outcome).tobytes())
for path in (("noise", "theta"), ("primitives", "log_lik")):
    array = group[path[0]][path[1]][:]
    digest.update(np.ascontiguousarray(np.nan_to_num(array, nan=-7.5)).tobytes())

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
    "marks": marks,
    "phases": phases,
    "free_report": free_report,
    "trace_samples": int(used),
    "result_digest": digest.hexdigest(),
    "ok": int((outcome == 0).sum()),
    "attempted": int((outcome != 8).sum()),
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

    Task 8b's construction, unchanged. A wholly-masked series short-circuits
    before any design exists, so the live count sets the fit cost while `grid`
    sets the tile geometry -- which is what stops run length being monotonic in
    B.

    Args:
        path: Destination store path.
        grid: Grid side; the tile side is chosen to match, so the run is one tile.
        live: How many series keep their data. Negative means every series.
        chunk_side: Spatial chunk side, time chunked whole. None leaves
            `to_zarr`'s own chunking.
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
    """Run one point of one arm and print it, with its whole fixture, as JSON."""
    work = Path(sys.argv[1])
    side = int(sys.argv[2])
    live = int(sys.argv[3])
    chunking = sys.argv[4]
    target = float(sys.argv[5])
    free = int(sys.argv[6])
    tag = sys.argv[7] if len(sys.argv) > 7 else "a"
    n_time = int(sys.argv[8]) if len(sys.argv) > 8 else N_TIME
    which = sys.argv[9] if len(sys.argv) > 9 else "m2"
    if chunking not in {"fine", "whole", "default"}:
        raise SystemExit(
            f"chunk must be 'fine', 'whole' or 'default', got {chunking!r}"
        )
    if which not in CANDIDATE_SETS:
        raise SystemExit(f"candidate set must be one of {sorted(CANDIDATE_SETS)}")
    if free not in {0, 1}:
        raise SystemExit(f"free must be 0 or 1, got {free!r}")
    chunk_side = {"fine": 16, "whole": side, "default": None}[chunking]
    candidates = CANDIDATE_SETS[which]
    n_models = len(candidates)

    work.mkdir(parents=True, exist_ok=True)
    name = f"s{side}_l{live}_{chunking}_t{int(target)}_n{n_time}_{which}_f{free}_{tag}"
    # A store left from a previous invocation would be RESUMED, and a resumed run
    # writes no tiles -- so the callback never fires and the readings come back
    # empty rather than wrong.
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

    floor = measure_floor(data_uri=uri, variable="sla")
    pinned = FloorReport(
        pre_warm_bytes=floor.peak_bytes,
        post_warm_bytes=floor.peak_bytes,
        with_input_bytes=floor.peak_bytes,
        peak_bytes=floor.peak_bytes,
        components={},
    )
    # The model comes from the production geometry, never from this file's
    # constants: `run_geometry(...).tile_kwargs()` is what `calibrate` asks, and
    # a hand-passed state dimension put Task 8b's early points on a side they
    # were not recorded at.
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
        free=free,
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
            "free": free,
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
            "block_bytes": side * side * n_time * 8,
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
