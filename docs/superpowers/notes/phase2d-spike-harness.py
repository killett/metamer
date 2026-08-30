"""2d Task 0 -- the pricing spike: what an arm costs, what N1 costs, what `run` adds.

**WHY THIS EXISTS AND WHY IT RUNS BEFORE TASK 1.** Phase 2d's budget is 27.0
hours against a 30 hour ceiling and it rests on three things nobody has
measured on this machine today: a per-point-per-arm cost dated 2026-08-29, an
unpriced N1 arm, and a unit measured on `core.fit` but spent on `batch.run`.
A cost 2x the assumed one re-plans the sub-phase; discovered at Task 5 it
re-plans it after 20 hours of compute. **Measured first it costs 45 minutes.**

**WHAT THIS FILE IS NOT.** It builds no benchmark field and it makes no claim
about coherence. The pre-flight moved the `l`-versus-saving reading out of this
task and into Task 1, because measuring it here would mean building the field
in a harness -- **the exact fault that made 2c's criterion 12 unmeasurable**,
since the warm-start spike's coherent field lived in a script that is not in
the tree. The two readings that remain need no field at all, which is why the
gate on Task 1 survives the move.

**THREE READINGS.**

| # | reading | why |
|---|---|---|
| 1 | per-point-per-arm cost through `fit`, `M = 2`, `N = 630`, with repeats | the budget's unit. The inherited figure is two single runs with no spread |
| 2 | N1's cost against cold's, with `self` as the positive control | N1 is not in the 12.048 factor. If it costs a full arm it needs a rung allocation |
| 3 | the `run`-to-`fit` per-point ratio at short `N`, on 2d's own geometry | **bounds** the gap between the unit measured and the unit spent -- (j6) |

**READING 2 IS A NULL AND ITS CEILING ARM IS LOAD-BEARING.** "N1 costs what
cold costs" is byte-identical in the output to "the iteration counter is not
moving", to "both arms silently ran cold", and to "the perturbation never
reached the optimizer". The `self` arm -- each cell started from its own
converged `theta_hat` -- collapsed iterations by 94% across three record
lengths in 2c. **If `self` does not collapse here, no cost number in this file
may be quoted, including reading 1's.** (i2).

**THE WARM AND N2 ARMS ARE NOT RUN AND NOT QUOTED.** N1's start is the cold
start displaced by `N1_EPSILON` along a keyed direction, so it needs a
`warm_valid` mask and nothing from the warm array's contents. The warm array
here is **fabricated** -- a neighbouring row's converged optimum -- which is
sound for N1 and meaningless for the two arms that actually read it. Running
them would cost two thirds of this spike's compute to produce numbers about a
source map that does not exist.

**THE STARTS COME FROM THE SHIPPED PATH.** `audit.cold_starts` and
`audit.arm_starts` build them, so N1 here is the N1 the audit runs. Rebuilding
the perturbation locally would measure a second N1 -- (j), and the whole reason
2c extracted `optimize.ladder_start` in the first place.

**AND THE DATA DOES NOT COME FROM THE CODE UNDER TEST.** The series are drawn
from a textbook Matern covariance written below, never from
`metamer.core.statespace`, so a slip in a family's construction cannot make the
fits artificially cheap and cancel against the thing being priced.

Usage:
    phase2d-spike-harness.py <out.jsonl> [quiet|cost|overhead|all]
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import replace
from pathlib import Path
from typing import Any, TextIO

import numpy as np
import xarray as xr
from numpy.typing import NDArray
from threadpoolctl import threadpool_limits

from metamer.batch.audit import N1_EPSILON, arm_starts, cold_starts
from metamer.batch.run import run
from metamer.core import machine
from metamer.core.capability import Objective
from metamer.core.criteria import Criterion
from metamer.core.engines.kalman import KalmanEngine
from metamer.core.fit import fit
from metamer.core.outcomes import Outcome
from metamer.core.registry import kernel_registry
from metamer.core.signal import Constant, SignalSpec, Trend
from metamer.core.terms import ProcessSpec, TermSpec

#: The candidate set the inherited 21 s was measured over. **M is part of the
#: reading**: it sets the price AND, through D9's `3 x M` point strata and
#: `M x 4` cell strata, the audit's stratum count. A spike at a different M
#: would price a different sub-phase.
CANDIDATE_KINDS = ("white", "white + matern12")

#: Production record length. The only length at which section 11.2's threshold
#: applies, and the length the budget is spent at.
N_TIME_PRODUCTION = 630

#: Short record length for reading 3. The overhead is per point and per tile
#: rather than per iteration, so it is a LARGER fraction of a CHEAPER fit and
#: the ratio here bounds the ratio at production length from above.
N_TIME_SHORT = 96

#: The batch the inherited figure was measured at. Held fixed so this spike's
#: number and the 2026-08-29 number describe the same shape.
BATCH = 16

#: 2c's protocol. Two points cannot separate a reading from the machine's own
#: jitter, and the inherited figure has one point per batch size.
REPEATS = 3

#: Seconds of idle used to establish the host is quiet before anything is
#: timed. Matches the 20 s idle reading 2b used.
QUIET_SECONDS = 20.0

#: Reading 3's grid is **2d's own geometry** -- 32 along the boundary normal
#: (4k, so an interior null line clears the coupling range) by 12 across (the
#: minimum giving two coarse points per axis at k = 8). The per-RUN overhead --
#: validation, opening, store creation, provenance -- amortizes over the point
#: count, so measuring it at 384 points measures it at 2d's own amortization.
OVERHEAD_NORMAL = 32
OVERHEAD_PARALLEL = 12

SQRT3 = np.sqrt(3.0)


def term(kind: str, **defaults: float) -> TermSpec:
    """Build a `TermSpec` from a registered family, overriding its defaults."""
    family = kernel_registry[kind]()
    specs = {
        name: replace(spec, default=defaults.get(name, spec.default))
        for name, spec in family.param_specs().items()
    }
    return TermSpec(
        kind=kind, params=specs, ordering_param=getattr(family, "ordering_param", None)
    )


def candidate_set() -> list[ProcessSpec]:
    """`["white", "white + matern12"]` -- M = 2, the set the 21 s was measured over.

    Lint-clean by construction: no two terms of the same kind with a free
    timescale, so section 4.5's exchangeability cannot fire.
    """
    return [
        ProcessSpec((term("white"),)),
        ProcessSpec((term("matern12"), term("white"))),
    ]


def signal_spec() -> SignalSpec:
    """Constant plus trend. Two design columns, held fixed across every arm."""
    return SignalSpec((Constant(), Trend()))


def matern12_cov(
    t: NDArray[np.float64], sigma: float, rho: float, white: float
) -> NDArray[np.float64]:
    """Textbook Matern nu = 1/2 covariance plus a white floor.

    Rasmussen & Williams eq. 4.9 at nu = 1/2, written here rather than
    imported. **This is the fixture's only source of truth about the family and
    it deliberately shares no code with `metamer.core.statespace`**, so a slip
    in the family's construction cannot cancel between the fixture and the fit.
    """
    d = np.abs(t[:, None] - t[None, :])
    cov = sigma**2 * np.exp(-d / rho) + white**2 * np.eye(t.size)
    return np.asarray(cov, dtype=np.float64)


def draw_batch(
    batch: int, n_time: int, *, seed: int
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """`(y, t)` for a batch of series, each from its own covariance.

    The rows differ smoothly in `sigma` and `rho` so the batch is not one
    series repeated -- a batch of identical rows would price one fit and
    multiply, and the iteration count is what varies between series.
    """
    t = np.arange(n_time, dtype=np.float64) / 12.0
    rows = []
    for b in range(batch):
        u = b / max(batch - 1, 1)
        cov = matern12_cov(t, sigma=1.0 + 0.4 * u, rho=0.6 + 0.8 * u, white=0.4)
        rng = np.random.default_rng(seed + b)
        rows.append(
            rng.multivariate_normal(np.zeros(n_time), cov) + 2.0 + 0.3 * (t - t.mean())
        )
    return np.asarray(rows), t


def emit(handle: TextIO, record: dict[str, Any]) -> None:
    """Append one JSON record and flush, so a killed run keeps what it measured."""
    handle.write(json.dumps(record) + "\n")
    handle.flush()


# --------------------------------------------------------------------------
# The host quiet check -- first, and its reading is part of the record
# --------------------------------------------------------------------------


def quiet_check() -> dict[str, Any]:
    """Idle for `QUIET_SECONDS` and report the cgroup full-stall rate and load.

    **A cost measurement on a contended box prices the contention.** The stall
    counter is per-cgroup and cannot tell a measurement that allocates hard
    from one being squeezed -- open question 19, still open -- so this is a
    precondition and not a validity gate: it can say the box was busy and it
    cannot certify that it was not.
    """
    before = machine.memory_stall_us()
    load_before = os.getloadavg()
    start = time.perf_counter()
    time.sleep(QUIET_SECONDS)
    elapsed = time.perf_counter() - start
    after = machine.memory_stall_us()
    load_after = os.getloadavg()

    rate_ms_per_s: float | None = None
    source: str | None = None
    if before is not None and after is not None:
        source = after[1]
        rate_ms_per_s = (after[0] - before[0]) / 1000.0 / elapsed
    return {
        "record": "quiet_check",
        "idle_seconds": elapsed,
        "stall_ms_per_s": rate_ms_per_s,
        "stall_source": source,
        "loadavg_before": list(load_before),
        "loadavg_after": list(load_after),
        "machine": machine.fingerprint(),
        "cpu": machine.cpu_model(),
        "physical_cores": machine.physical_cores(),
    }


# --------------------------------------------------------------------------
# Readings 1 and 2 -- the cost of an arm, and what N1 costs against cold
# --------------------------------------------------------------------------


def cost_repeat(repeat: int, handle: TextIO) -> None:
    """One interleaved cold / N1 / self triple over one batch.

    **ALL THREE ARMS IN ONE SESSION, INTERLEAVED.** The stride sweep's spurious
    15% came from a cold arm re-run in a different session; here the cost of
    getting it wrong is comparability rather than drift, and it is the same fix.
    """
    candidates = candidate_set()
    signal = signal_spec()
    engine = KalmanEngine()
    y, t = draw_batch(BATCH, N_TIME_PRODUCTION, seed=20_260_830 + 1000 * repeat)
    mask = np.ones(y.shape, dtype=bool)

    # -- cold ------------------------------------------------------------
    start = time.perf_counter()
    cold = fit(y, t, signal, candidates, Criterion.AIC, mask=mask, engine=engine)
    cold_seconds = time.perf_counter() - start
    ok = cold.outcome == Outcome.OK.code

    # -- the shipped starts, so N1 here is the audit's N1 ------------------
    ladder = cold_starts(y, mask, t, candidates, engine=engine, objective=Objective.ML)
    # A FABRICATED warm: each row takes its neighbour's converged optimum. N1
    # reads the direction and the validity mask and nothing of the contents,
    # so this is sound for N1 -- and it is why the WARM and N2 arms are not run.
    warm = np.roll(cold.theta_unconstrained, shift=1, axis=0)
    warm_valid = np.roll(ok, shift=1, axis=0) & ok
    starts = arm_starts(
        cold=ladder,
        warm=warm,
        warm_valid=warm_valid,
        candidates=candidates,
        points=np.arange(BATCH, dtype=np.int64),
        seed=20_260_830,
        epsilon=N1_EPSILON,
    )

    # -- N1 ---------------------------------------------------------------
    start = time.perf_counter()
    n1 = fit(
        y,
        t,
        signal,
        candidates,
        Criterion.AIC,
        mask=mask,
        engine=engine,
        x0=starts.n1,
        x0_valid=starts.n1_valid,
    )
    n1_seconds = time.perf_counter() - start

    # -- self, the ceiling arm and reading 2's positive control -------------
    start = time.perf_counter()
    selfarm = fit(
        y,
        t,
        signal,
        candidates,
        Criterion.AIC,
        mask=mask,
        engine=engine,
        x0=cold.theta_unconstrained,
        x0_valid=ok,
    )
    self_seconds = time.perf_counter() - start

    # **THE ITERATION COMPARISON IS OVER ONE CELL SET, NOT THREE.** `fit` fits
    # every cell in the batch; a cell whose `x0_valid` is false takes the
    # moment ladder, so the N1 arm contains COLD fits wherever the fabricated
    # warm was unavailable. Summing each arm over its own OK cells would then
    # compare 8 N1 fits against 8 cold fits of which two are the same fit --
    # (a0)'s fourth register, a fallback making "did not happen" and "happened
    # and was discarded" one observation. The common mask is the only honest
    # denominator, and the per-arm totals are emitted beside it so the gap is
    # visible rather than absorbed.
    common = (
        starts.n1_valid
        & ok
        & (n1.outcome == Outcome.OK.code)
        & (selfarm.outcome == Outcome.OK.code)
    )
    cells = int(BATCH * len(candidates))
    for name, result, seconds, valid in (
        ("cold", cold, cold_seconds, np.ones_like(ok)),
        ("n1", n1, n1_seconds, starts.n1_valid),
        ("self", selfarm, self_seconds, ok),
    ):
        arm_ok = result.outcome == Outcome.OK.code
        emit(
            handle,
            {
                "record": "cost_arm",
                "repeat": repeat,
                "arm": name,
                "batch": BATCH,
                "n_time": N_TIME_PRODUCTION,
                "candidates": list(CANDIDATE_KINDS),
                "seconds": seconds,
                "seconds_per_point": seconds / BATCH,
                "cells": cells,
                "cells_ok": int(arm_ok.sum()),
                "cells_started_here": int(valid.sum()),
                "iterations_total": int(result.n_iter[arm_ok].sum()),
                "iterations_mean": float(result.n_iter[arm_ok].mean()),
                # The reading the verdict uses: one cell set across all three.
                "cells_common": int(common.sum()),
                "iterations_total_common": int(result.n_iter[common].sum()),
                "iterations_mean_common": (
                    float(result.n_iter[common].mean()) if common.any() else None
                ),
            },
        )
    emit(
        handle,
        {
            "record": "cost_accounting",
            "repeat": repeat,
            "n1_cells_valid": int(starts.n1_valid.sum()),
            "n2_inadmissible": int(starts.n2_inadmissible.sum()),
            "degenerate_distance": int(starts.degenerate.sum()),
            "warm_is_fabricated": True,
            "warm_and_n2_arms_run": False,
            "why": (
                "N1 reads the keyed direction and the validity mask, not the "
                "warm array's contents, so a fabricated warm is sound for N1 "
                "and meaningless for WARM and N2. Those two are not run and "
                "not quoted."
            ),
        },
    )


# --------------------------------------------------------------------------
# Reading 3 -- what `run` adds over `fit`, bounded at short N
# --------------------------------------------------------------------------


CONFIG_TEMPLATE = """
data_uri = "{uri}"
variable = "sla"
signal_terms = ["constant", "trend"]
candidates = ["white", "white + matern12"]
criteria = ["aic"]
"""


def write_field(
    directory: Path, name: str, *, n_time: int, n_y: int, n_x: int, seed: int
) -> tuple[str, NDArray[np.float64], NDArray[np.float64]]:
    """A field on disk, and the same series as a `(time, y, x)` array.

    **The same bytes go through both paths.** `run` reads the zarr; `fit` gets
    the identical rows in the order `run` visits them in, so the two
    measurements are of one workload and the difference is the machinery.
    """
    origin = np.datetime64("2000-01-01")
    t = np.arange(n_time, dtype=np.float64) / 12.0
    values = np.empty((n_time, n_y, n_x), dtype=np.float64)
    for iy in range(n_y):
        for ix in range(n_x):
            u = (iy * n_x + ix) / max(n_y * n_x - 1, 1)
            cov = matern12_cov(t, sigma=1.0 + 0.4 * u, rho=0.6 + 0.8 * u, white=0.4)
            rng = np.random.default_rng(seed + iy * 100 + ix)
            values[:, iy, ix] = (
                rng.multivariate_normal(np.zeros(n_time), cov)
                + 2.0
                + 0.3 * (t - t.mean())
            )
    dataset = xr.Dataset(
        {"sla": (("time", "y", "x"), values.astype("float32"))},
        coords={
            "time": np.array(
                [origin + np.timedelta64(31 * i, "D") for i in range(n_time)]
            ),
            "y": np.arange(n_y, dtype=np.float64),
            "x": np.arange(n_x, dtype=np.float64),
        },
    )
    path = directory / name
    dataset.to_zarr(path)
    return str(path), values, t


def write_config(directory: Path, name: str, uri: str) -> Path:
    """Write the config the run reads. One template, so both paths agree."""
    path = directory / name
    path.write_text(CONFIG_TEMPLATE.format(uri=uri))
    return path


def production_tile_side(handle: TextIO, directory: Path) -> int:
    """What tile side `N = 630` actually gets, on a six-point field.

    **THIS IS NOT A DETAIL, IT IS READING 3's SCOPE.** The tile side is bounded
    below by the process floor -- this box holds ~229 MB before a tile exists,
    and a budget that leaves nothing for a tile is refused at layer 3 -- so the
    smallest legal tile at `N = 96` measured **176** on this machine. **2d's
    field is 32 x 12.** If the production tile side exceeds 32, **2d's whole
    field is a single tile and the per-tile barrier is not part of 2d's cost at
    all**, which is what makes a single-tile overhead reading the right reading
    rather than a compromise.

    `tests/test_twopass.py` reaches multiple tiles only against a **stubbed**
    floor, at budgets around 0.001 GB that a real run refuses. Recorded here so
    nobody reads those budgets as evidence that a real multi-tile run is cheap.
    """
    uri, _, _ = write_field(
        directory, "tileprobe.zarr", n_time=N_TIME_PRODUCTION, n_y=2, n_x=3, seed=5150
    )
    config_path = write_config(directory, "tileprobe.toml", uri)
    report = run(config_path, directory / "tileprobe.out.zarr")
    tiles_2d = max(1, -(-OVERHEAD_NORMAL // report.tile_side)) * max(
        1, -(-OVERHEAD_PARALLEL // report.tile_side)
    )
    emit(
        handle,
        {
            "record": "production_geometry",
            "n_time": N_TIME_PRODUCTION,
            "tile_side": report.tile_side,
            "memory_budget_gb": report.config.memory_budget_gb,
            "budget_was_default": report.memory_budget_requested_gb is None,
            "field_2d": [OVERHEAD_NORMAL, OVERHEAD_PARALLEL],
            "tiles_2d_would_have": tiles_2d,
            "single_tile": tiles_2d == 1,
        },
    )
    return int(report.tile_side)


def overhead_reading(handle: TextIO, directory: Path, production_side: int) -> None:
    """`run` over 2d's own geometry against `fit` over the same series.

    **THE FIT SIDE IS CALLED ONCE PER TILE AT THE TILE'S OWN BATCH SIZE**, so
    the comparison isolates validation, opening, assembly, store creation,
    region writes and provenance from any batch-size effect. On 2d's geometry
    that is one tile and one `fit` call, which is not a compromise -- it is
    what `production_geometry` establishes 2d's own runs will be.

    **SHORT `N` MAKES THIS AN UPPER BOUND.** The overhead is per point and per
    run rather than per iteration, so it is a larger fraction of a cheaper fit.
    The ratio here bounds the ratio at `N = 630` from above -- (j6).
    """
    uri, values, t = write_field(
        directory,
        "overhead.zarr",
        n_time=N_TIME_SHORT,
        n_y=OVERHEAD_NORMAL,
        n_x=OVERHEAD_PARALLEL,
        seed=770_000,
    )
    config_path = write_config(directory, "overhead.toml", uri)

    # -- the run side -----------------------------------------------------
    start = time.perf_counter()
    report = run(config_path, directory / "overhead.out.zarr")
    run_seconds = time.perf_counter() - start

    # -- the fit side, one call per tile, same rows, same order ------------
    tile_side = report.tile_side
    candidates = candidate_set()
    signal = signal_spec()
    engine = KalmanEngine()
    fit_seconds = 0.0
    tiles = 0
    for y0 in range(0, OVERHEAD_NORMAL, tile_side):
        for x0 in range(0, OVERHEAD_PARALLEL, tile_side):
            block = values[:, y0 : y0 + tile_side, x0 : x0 + tile_side]
            rows = block.reshape(block.shape[0], -1).T
            mask = np.ones(rows.shape, dtype=bool)
            start = time.perf_counter()
            fit(rows, t, signal, candidates, Criterion.AIC, mask=mask, engine=engine)
            fit_seconds += time.perf_counter() - start
            tiles += 1

    points = OVERHEAD_NORMAL * OVERHEAD_PARALLEL
    emit(
        handle,
        {
            "record": "overhead",
            "n_time": N_TIME_SHORT,
            "field": [OVERHEAD_NORMAL, OVERHEAD_PARALLEL],
            "points": points,
            "tile_side_run": report.tile_side,
            "tiles_total_run": report.tiles_total,
            "tiles_written_run": report.tiles_written,
            "tiles_fit": tiles,
            "run_seconds": run_seconds,
            "fit_seconds": fit_seconds,
            "run_seconds_per_point": run_seconds / points,
            "fit_seconds_per_point": fit_seconds / points,
            "ratio": run_seconds / fit_seconds if fit_seconds > 0 else None,
            "phase_seconds": dict(report.phase_seconds),
            "production_tile_side": production_side,
            # **THE VOID CLAUSE IS INVERTED FROM THE PREDICTIONS FILE.** It was
            # written as "void if fewer than 2 tiles", on the assumption that
            # the barrier was in 2d's scope. `production_geometry` measures
            # that it is not: 2d's 32 x 12 field is ONE tile at every legal
            # budget, because the tile side is bounded below by the process
            # floor. So a MULTI-tile reading would be the one out of scope --
            # it would price a barrier 2d never pays. Recorded as a departure
            # from the committed prediction, with the measurement that caused
            # it, rather than silently reinterpreted.
            "void_multi_tile_out_of_scope": report.tiles_total > 1,
            "prediction_void_clause_superseded": (
                "predictions.json reading 3 void_when: 'the run produced fewer "
                "than 2 tiles'. Superseded by the production_geometry record: "
                "2d's field is single-tile at every legal budget, so the "
                "per-tile barrier is not part of 2d's cost and a single-tile "
                "reading is the correct scope rather than a gap."
            ),
        },
    )


# --------------------------------------------------------------------------


def main() -> None:
    """Run the requested readings, appending one JSON record per result."""
    out = Path(sys.argv[1])
    mode = sys.argv[2] if len(sys.argv) > 2 else "all"
    with out.open("a", encoding="utf-8") as handle:
        emit(
            handle,
            {
                "record": "header",
                "task": "2d plan Task 0 -- the pricing spike",
                "mode": mode,
                "predictions": "phase2d-spike-predictions.json",
                "argv": sys.argv[1:],
                "git_head": subprocess.run(  # noqa: S603
                    ["/usr/bin/env", "git", "rev-parse", "HEAD"],  # noqa: S607
                    capture_output=True,
                    text=True,
                    check=False,
                ).stdout.strip(),
            },
        )
        if mode in {"quiet", "all"}:
            emit(handle, quiet_check())
        with threadpool_limits(limits=1):
            if mode in {"cost", "all"}:
                for repeat in range(REPEATS):
                    cost_repeat(repeat, handle)
            if mode in {"overhead", "all"}:
                with tempfile.TemporaryDirectory() as raw:
                    directory = Path(raw)
                    side = production_tile_side(handle, directory)
                    overhead_reading(handle, directory, side)


if __name__ == "__main__":
    main()
