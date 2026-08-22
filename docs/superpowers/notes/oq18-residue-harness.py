"""OQ18 Task A-triple-prime: NAME the 618 B/series fit-phase residue.

**WHY THIS EXISTS.** Task A-double-prime bounded the tier-3 tensor and the peak
did not collapse: a second allocation became dominant at **618.4 +/- 24.2
B/series**, matching A-prime's tier-2 arm at **618.3 +/- 30.5** -- two
independent eliminations agreeing to 0.1 B/series. That residue is what
criterion 7's remaining **+4.63 MB** at side 96 is made of, and it is unnamed.

**THE TIER-2 ARM IS THE PRIMARY FIXTURE HERE, WHICH REVERSES ITS ROLE.** With
`live = 0` every mask is identical, tier 2 fires, and **no per-series tensor is
built at all** -- so the residue is isolated without the chunking being involved
and without the tensor's 17.69 MB sitting on top of it. The bounded tier-3 arm
becomes the confirmation rather than the subject.

**AND THE CONSTRAINT THE SIZE HAS TO SATISFY IS ALREADY MEASURED.** A-prime's
tier-2 arm gave **618.3 +/- 30.5 B/series at N = 60** and **514.3 +/- 74.2 at
N = 240** -- overlapping, so the residue is **`n_time`-INDEPENDENT**, which
excludes every data-shaped term before any candidate is proposed. What is left
is per-CANDIDATE and per-series, which is what `fit`'s preallocated output
arrays are.

**TWO INSTRUMENTS ARE ADDED, AND BOTH READ SIZES RATHER THAN FITTING THEM.**
`np.full`, `np.empty` and `np.zeros` are recorded during the fit call with the
caller's file and line, so an allocation site is **named by where it happened**;
and every array `FitResult` carries is summed by `nbytes` after `fit` returns,
so the retained cost is **read off the objects**. A candidate whose predicted
size matches at one fixture and not across the levers is the
shape-before-magnitude trap, and reading beats regressing.

---

**A-double-prime: what the fit-phase maximum becomes once the tensor is bounded.**

**A-PRIME'S HARNESS WITH ONE ARGUMENT ADDED** -- the chunk size the child sets on
`signal.SVD_CHUNK_SERIES` before the run -- so the chunked and unchunked arms are
**one measurement on one box**, interleaved, rather than today's run compared
against a ladder taken three days ago at 4.5-7.6 GB available. That comparison
is exactly the (a9) confound this project spent Tasks 8a, 8i and 8b on: two
readings differing along an axis they also differ along.

Everything below is A-prime's, unchanged, and its docstring follows.

---

**A-prime: NAME the fit-phase transient that sets the production peak.**

**WHY THIS EXISTS.** Task A established that the peak is
`max(fit-phase transient, post-write plateau)` and that at production B the fit
transient wins -- +862 B/series at N = 60 and +6859 B/series at N = 240 above the
plateau -- so the block's lifetime is the wrong target and the transient itself
is the right one. **A term measured but not named cannot be eliminated, and a
crossed 2 x 2 over an unnamed term measures whatever sum it happens to be.**

**WHAT THIS HARNESS ADDS TO TASK A's.** The same masked, duration-controlled,
floor-pinned point behind the same bare launcher, with the instrumentation moved
one level in: `design_info`, the batched `svdvals` inside it, the series loop,
and each post-loop step are bracketed and given their own phase maximum, and
`optimize_series` is counted so the resident set can be plotted against progress
through the batch. **A setup allocation and an accumulation across series are
the same total and different curves**, and no phase maximum tells them apart.

**THE SUSPECT IS NAMED IN ITS OWN DOCSTRING.**
`SignalSpec._restricted_singular_values` has three tiers, and its third --
taken when the per-series masks differ -- builds `x[None] * mask[..., None]` and
hands it to `svdvals`. That docstring says the batched route allocates
`B * N * k * 8` bytes and quotes 320 MB at B = 10^4, N = 10^3, k = 4. At this
project's fixtures it is 1920 B/series at N = 60 and 7680 at N = 240, against a
measured transient of 1017 and 6974. **So the harness measures the tensor rather
than computing it**: the wrapper on `svdvals` reads `nbytes` off the argument at
the call, which is the allocation itself and not an estimate of it.

**THE ARMS ARE THE TIER, AND THE FIXTURE CHOOSES IT.** `live = 16` leaves the
live series unmasked and the rest wholly masked, so the masks differ and tier 3
runs. `live = 0` masks every series identically, so tier 2 runs and no per-series
tensor is built at all. **The B-slope is the discriminator**: sixteen series
worth of optimizer work is a constant in B and the tensor is not, so the two arms
separate the tier from the fitting even though they also differ in whether any
fit runs.

**AND THE NAMING INSTRUMENT IS QUARANTINED.** `tracemalloc` holds a frame record
per live allocation, so a run under it is not a run whose resident set means
anything. Its arm is flagged in the payload, its RSS readings are not published,
and it exists to rank sites at the moment the tensor is alive -- which is at the
`svdvals` call, since that is the only moment the temporary can be attributed.

Usage:
    oq18-aprime2-harness.py <workdir> <side> <live> <chunk> <target_s> <trace>
                            [tag] [n_time] [candidate_set] [svd_chunk]

`<svd_chunk>` is the value the child writes to `signal.SVD_CHUNK_SERIES`: the
shipped 512 for the bounded arm, or a number above the batch for the unbounded
one, which reproduces the whole-batch allocation A-prime measured.

`<live>` is the tier arm: 16 for tier 3, 0 for tier 2. `<trace>` is 1 for the
tracemalloc naming arm, whose RSS is not a measurement.
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

#: One resident-set reading per this many `optimize_series` calls. At B = 9216
#: and M = 2 that is 18 432 calls, so 64 gives 288 points across the batch --
#: enough to tell a step from a ramp, and cheap enough not to be the thing being
#: measured.
PROGRESS_EVERY = 64

CANDIDATE_SETS = {
    # **m7 WAS ADDED 2026-08-22 FOR G5**, the in-process inventory at the
    # largest candidate count `p_max = 3` admits. Every set here holds `p_max`
    # at 3, so the charged `24*p_max + 16*k_beta + 57` = 193 is the same across
    # all of them and the lever moves M alone. Seven is the ceiling: white has
    # one free parameter, matern12 and matern32 have two, so the candidates
    # with p <= 3 are exactly these seven.
    "m2": ("white", "white + matern12"),
    "m6": (
        "white",
        "matern12",
        "matern32",
        "white + white",
        "white + matern12",
        "white + matern32",
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
# inherited across fork/exec.
PROBE = """
import hashlib, json, sys, threading, time
import numpy as np
import zarr
from metamer.core import machine
from metamer.core.memory import FloorReport

FLOOR = {floor}
TRACE = {trace}
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
import metamer.core.signal as sigmod

# THE ARM. Set before anything runs, and echoed back in the payload so a point
# can never be filed under the wrong arm.
SVD_CHUNK = {svd_chunk}
sigmod.SVD_CHUNK_SERIES = SVD_CHUNK

marks = {{}}


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


runmod.write_tile = _wrap("write", runmod.write_tile)
runmod.assemble_tile = _wrap("assemble", runmod.assemble_tile)
runmod.fit = _wrap("fit", runmod.fit)  # rebound again below, after the counter
runmod.mark_complete = _wrap("mark", runmod.mark_complete)

# ---------------------------------------------------------------------------
# INSIDE `fit`, WHICH IS WHERE TASK A LEFT THE PEAK.
# ---------------------------------------------------------------------------
# Each wrapper records the working set on both sides of the call it brackets,
# so a step that allocates and releases within itself is visible as a rise in
# its own phase maximum and NOT as a difference across it. The two readings
# answer different questions and the pair is what separates "held" from
# "touched": `design_info` is expected to release its largest temporary before
# returning, which no before/after difference can see.
from metamer.core.signal import SignalSpec  # noqa: E402

# NOT `from metamer.core import fit`: the package re-exports the FUNCTION under
# that name, so the import binds a callable and every attribute patch below
# would land on nothing. The module object is what has to be patched, and
# `sys.modules` is the only spelling that cannot be shadowed by a re-export.
fitmod = sys.modules["metamer.core.fit"]

spans = {{}}


def _bracket(name, real):
    def wrapper(*args, **kwargs):
        _mark(name + "_start")
        spans[name + "_rss_before"] = machine.current_rss_bytes()
        try:
            return real(*args, **kwargs)
        finally:
            spans[name + "_rss_after"] = machine.current_rss_bytes()
            _mark(name + "_end")
    return wrapper


real_design_info = SignalSpec.design_info


def design_info(self, t, mask):
    # THE SHAPES ARE RECORDED, NEVER THE TIER'S OWN PREDICATES. Re-running
    # `mask.all()` and the broadcast comparison here would allocate the same
    # temporaries the function under measurement allocates, so the instrument
    # would double the thing it is measuring. The fixture decides the tier --
    # `live = 0` makes every mask identical and `live = 16` makes them differ --
    # and the shapes are what the tensor's size is computed from.
    spans["mask_shape"] = list(mask.shape)
    spans["design_rows"] = int(mask.shape[0])
    return real_design_info(self, t, mask)


SignalSpec.design_info = _bracket("design", design_info)
# Accessed through the class, a staticmethod is already the plain function, so
# there is no `__func__` to unwrap -- and rebinding it must go back through
# `staticmethod` or the wrapper would be handed `self` as its first argument.
SignalSpec._restricted_singular_values = staticmethod(
    _bracket("svd", SignalSpec._restricted_singular_values)
)

# EVERY ARRAY `fit` ALLOCATES, BY SIZE AND BY SITE. Recorded only while the fit
# call is running and only above a threshold, so the recorder cannot become the
# thing being measured. `np.full` builds its buffer through numpy's internal
# `empty` rather than the module attribute, so patching these three names counts
# each allocation once.
allocations = []
recording = [False]
_real_np = {{"full": np.full, "empty": np.empty, "zeros": np.zeros}}


def _record(name):
    real = _real_np[name]

    def wrapper(*args, **kwargs):
        out = real(*args, **kwargs)
        if recording[0]:
            nbytes = int(getattr(out, "nbytes", 0))
            if nbytes >= 32768:
                frame = sys._getframe(1)
                allocations.append(
                    [
                        f"{{frame.f_code.co_filename}}:{{frame.f_lineno}}",
                        name,
                        nbytes,
                        list(np.shape(out)),
                        str(np.asarray(out).dtype),
                    ]
                )
        return out

    return wrapper


np.full = _record("full")
np.empty = _record("empty")
np.zeros = _record("zeros")

result_arrays = {{}}
real_fit_call = fitmod.fit


def counted_fit(*args, **kwargs):
    recording[0] = True
    try:
        out = real_fit_call(*args, **kwargs)
    finally:
        recording[0] = False
    # READ OFF THE OBJECTS, never regressed: what the result actually holds.
    # **DEDUPED BY IDENTITY, because `scores` HOLDS THE SAME ARRAYS.** `loglik`
    # and `scores.loglik` are one allocation under two names, and summing both
    # inflated the total by 18 B/series in the smoke point -- a total that
    # over-counts is the (a) rule at an inventory, and it would have made the
    # residue look better explained than it is.
    seen = set()
    scores = getattr(out, "scores", None)
    fields = [
        (name, getattr(out, name, None))
        for name in (
            "theta", "theta_err", "theta_unconstrained", "beta", "beta_err",
            "loglik", "outcome", "init_rung", "n_iter", "n_eff_bic",
            "n_eff_trend",
        )
    ] + [
        (f"scores.{{name}}", getattr(scores, name, None))
        for name in ("loglik", "k", "n", "n_eff", "outcome")
    ]
    for name, array in fields:
        if array is None or id(array) in seen:
            continue
        seen.add(id(array))
        result_arrays[name] = int(array.nbytes)
    return out


fitmod.fit = counted_fit

# RSS AGAINST PROGRESS THROUGH THE BATCH. A setup allocation and an
# accumulation across series are the same total and different curves, and
# nothing in a phase maximum tells them apart.
progress = []
calls = [0]
real_optimize = fitmod.optimize_series


def optimize_series(*args, **kwargs):
    index = calls[0]
    calls[0] = index + 1
    if index % {progress_every} == 0:
        progress.append(
            [index, machine.current_rss_bytes(), round(time.monotonic() - started, 3)]
        )
    return real_optimize(*args, **kwargs)


fitmod.optimize_series = optimize_series
# `run` looks `fit` up in ITS OWN module namespace, so the counter has to be
# installed there as well as in `core.fit` -- patching one and testing the other
# is how an instrument comes back empty and reads as an absence.
runmod.fit = _wrap("fit", counted_fit)
fitmod.penalty_terms = _bracket("penalty", fitmod.penalty_terms)
fitmod.n_eff_bic = _bracket("neffbic", fitmod.n_eff_bic)
fitmod.n_eff_trend = _bracket("nefftrend", fitmod.n_eff_trend)
fitmod.rank_candidates = _bracket("rank", fitmod.rank_candidates)

# THE TENSOR MEASURES ITSELF. `_restricted_singular_values`'s third tier builds
# `x[None] * mask[..., None]` and hands it straight to `svdvals`, so the
# argument AT THE CALL is the allocation under suspicion and its `nbytes` is the
# size -- read, not computed from B * N * k * 8. Cheap enough for every arm:
# one call per fit.
real_svdvals = np.linalg.svdvals
trace_top = []


def svdvals(a, *args, **kwargs):
    # THE LARGEST CALL, NOT THE LAST ONE. `svdvals` is called again per series
    # deeper in the objective, and recording into a single slot let a (1, 4, 4)
    # call from inside the loop overwrite the (B, N, k) one from `design_info`
    # -- 128 bytes standing where 4.42 MB belongs. Caught in the smoke point,
    # which is what a smoke point is for.
    array = np.asarray(a)
    spans["svdvals_calls"] = spans.get("svdvals_calls", 0) + 1
    if int(array.nbytes) > spans.get("svdvals_max_input_bytes", -1):
        spans["svdvals_max_input_shape"] = list(array.shape)
        spans["svdvals_max_input_bytes"] = int(array.nbytes)
        spans["svdvals_max_at_s"] = round(time.monotonic() - started, 4)
    spans["svdvals_rss_at_entry"] = machine.current_rss_bytes()
    if TRACE and array.nbytes > 1_000_000:
        # SNAPSHOT WHILE THE TENSOR IS ALIVE -- it is this call's argument, so
        # there is no later moment at which it can be attributed. Gated on size
        # so the per-series calls inside the loop cannot bury the one call this
        # arm exists to name.
        import tracemalloc

        snapshot = tracemalloc.take_snapshot()
        for stat in snapshot.statistics("lineno")[:8]:
            trace_top.append([str(stat.traceback[0]), int(stat.size), stat.count])
    out = real_svdvals(a, *args, **kwargs)
    spans["svdvals_rss_at_exit"] = machine.current_rss_bytes()
    return out


np.linalg.svdvals = svdvals

# THE NAMING INSTRUMENT, AND ITS OWN FOOTPRINT DISQUALIFIES THIS ARM'S RSS.
# tracemalloc holds a frame record per live allocation, so a run under it is not
# a run whose resident set means anything. It is here to RANK SITES, and every
# reading it produces is labelled with the arm that produced it.
if TRACE:
    import tracemalloc

    tracemalloc.start(6)

baseline = machine.current_rss_bytes()
readings = {{}}


def seen(tile):
    # AT END OF TILE, WITH THE BLOCK STILL ALIVE -- Task 8b's reading, unchanged,
    # so this ladder's residency column is comparable with that one's.
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

# INSIDE `fit`, AND THE SERIES LOOP IS DEFINED AS WHAT IS LEFT. `design_info`
# runs once at the top and the per-candidate tail runs after the loop, so the
# loop's own window is design_end to the first tail call -- which is the window
# an accumulation across the batch would have to live in.
sub_phases = {{
    "design_info": window(at("design_start"), at("design_end")),
    "svd": window(at("svd_start"), at("svd_end")),
    "series_loop": window(at("design_end"), at("penalty_start")),
    "penalty_terms": window(at("penalty_start"), at("penalty_end")),
    "n_eff_bic": window(at("neffbic_start"), at("neffbic_end")),
    "n_eff_trend": window(at("nefftrend_start"), at("nefftrend_end")),
    "rank_candidates": window(at("rank_start"), at("rank_end")),
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
    "sub_phases": sub_phases,
    "spans": spans,
    "progress": progress,
    "optimize_calls": calls[0],
    "trace_top": trace_top,
    "trace_arm": bool(TRACE),
    "svd_chunk_series": sigmod.SVD_CHUNK_SERIES,
    "allocations": sorted(allocations, key=lambda entry: -entry[2])[:12],
    "allocation_count": len(allocations),
    "result_arrays": result_arrays,
    "result_arrays_total": sum(result_arrays.values()),
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
    trace = int(sys.argv[6])
    tag = sys.argv[7] if len(sys.argv) > 7 else "a"
    n_time = int(sys.argv[8]) if len(sys.argv) > 8 else N_TIME
    which = sys.argv[9] if len(sys.argv) > 9 else "m2"
    svd_chunk = int(sys.argv[10]) if len(sys.argv) > 10 else 512
    if chunking not in {"fine", "whole", "default"}:
        raise SystemExit(
            f"chunk must be 'fine', 'whole' or 'default', got {chunking!r}"
        )
    if which not in CANDIDATE_SETS:
        raise SystemExit(f"candidate set must be one of {sorted(CANDIDATE_SETS)}")
    if trace not in {0, 1}:
        raise SystemExit(f"trace must be 0 or 1, got {trace!r}")
    chunk_side = {"fine": 16, "whole": side, "default": None}[chunking]
    candidates = CANDIDATE_SETS[which]
    n_models = len(candidates)

    work.mkdir(parents=True, exist_ok=True)
    name = (
        f"s{side}_l{live}_{chunking}_t{int(target)}_n{n_time}_{which}"
        f"_x{trace}_c{svd_chunk}_{tag}"
    )
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
        trace=trace,
        svd_chunk=svd_chunk,
        progress_every=PROGRESS_EVERY,
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
            "trace": trace,
            "svd_chunk_requested": svd_chunk,
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
