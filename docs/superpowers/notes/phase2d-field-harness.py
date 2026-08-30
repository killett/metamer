"""2d Task 1 -- the benchmark field's own iteration count, and the `l` lever's sign.

**TWO READINGS, BOTH ABOUT THE FIELD RATHER THAN ABOUT THE MECHANISM.**

| # | reading | why it is here |
|---|---|---|
| A | iterations per point, per rung, at `N = 630` | **exit criterion 17.** The budget is `cost(iterations) x points x factor`, and Task 0 measured the cost model and not the field |
| B | the saving under a **long** `l` against a **short** one, at `N = 96` | the premise the whole sweep rests on: that E5's primary lever is a lever and not a label |

**WHY THIS IS A BENCHMARK AND NOT A TEST.** Both readings need real fits over
the benchmark geometry at production or near-production record length -- tens
of minutes. E7 settles the shape: 2d's measurements are a benchmark, and the
exit-criteria suite asserts against the **committed artifact**. (a2d)'s
artifact register is what makes that sound: the artifact carries its instrument
block, so a stale report cannot pass as a current one.

**READING A IS A SAMPLE AND SAYS SO.** A systematic subgrid -- every 2nd point
on each axis, 96 of 384 -- covers both regimes evenly and includes every coarse
index. It is fitted through `core.fit` rather than through a `run` because
**the iteration count is a property of the series and the candidate set, not of
the traversal**, and Task 0 measured a run's whole non-fit cost at under 1%.

**READING B VARIES `l` AND HOLDS THE CONTRAST FIXED.** The shipped rungs move
**both** levers together -- E5's accepted confound -- so comparing `easy`
against `hard` would measure the composite dial. The plan's test asks about
`l`, so `l` is what varies here.

**NO NOISE CLAUSE IS NEEDED FOR READING B.** `fit` has no stochastic component,
which is D7's own reason a cold-versus-cold arm cannot exist, so iteration
counts are deterministic and the ordering is exact. Task 0 measured the same
fixture returning 405 iterations in five consecutive repeats, and that is the
property that let its N1 verdict survive four instrument defects.

**TASK 0's FOUR, WHICH THIS HARNESS INHERITS AS REQUIREMENTS:** matching dtypes
on both sides of any comparison; the axis built by `to_decimal_years` and never
by hand -- here it comes from `build_field`, which takes it from the store; one
fixture per repeat, not a new draw; and the quiet check **gating** rather than
annotating.

Usage:
    phase2d-field-harness.py <out.jsonl> [a|b|all]
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
from threadpoolctl import threadpool_limits

from metamer.batch.run import run
from metamer.batch.twopass import run_two_pass
from metamer.bench import fields
from metamer.core import machine
from metamer.core.criteria import Criterion
from metamer.core.engines.kalman import KalmanEngine
from metamer.core.fit import fit
from metamer.core.outcomes import Outcome
from metamer.core.registry import kernel_registry
from metamer.core.signal import Constant, SignalSpec, Trend
from metamer.core.terms import ProcessSpec, TermSpec

#: Reading A's subgrid stride on each axis. Every 2nd point: 16 x 6 = 96 of
#: 384, both regimes evenly, every coarse index included.
SUBGRID = 2

#: Reading B's record length. Where the 2c spike measured a real positive
#: saving of +7.80%, so an ordering there is an ordering of two live numbers.
N_TIME_LEVER = 96

QUIET_SECONDS = 20.0


def emit(handle: TextIO, record: dict[str, Any]) -> None:
    """Append one JSON record and flush, so a killed run keeps what it measured."""
    handle.write(json.dumps(record) + "\n")
    handle.flush()


def quiet_check() -> dict[str, Any]:
    """Idle, then report load and stall. **Gates** -- Task 0's fourth defect."""
    before = machine.memory_stall_us()
    start = time.perf_counter()
    time.sleep(QUIET_SECONDS)
    elapsed = time.perf_counter() - start
    after = machine.memory_stall_us()
    load = os.getloadavg()
    cores = machine.physical_cores()
    rate = None
    if before is not None and after is not None:
        rate = (after[0] - before[0]) / 1000.0 / elapsed
    return {
        "record": "quiet_check",
        "idle_seconds": elapsed,
        "stall_ms_per_s": rate,
        "loadavg": list(load),
        "physical_cores": cores,
        "load_limit": cores - 1,
        "quiet": load[0] < (cores - 1),
        "machine": machine.fingerprint(),
        "stall_is_not_a_gate": "open question 19",
    }


# --------------------------------------------------------------------------
# Reading A -- exit criterion 17
# --------------------------------------------------------------------------


def reading_a(handle: TextIO, directory: Path) -> None:
    """Iterations per point on a subgrid of each rung's field, at `N = 630`."""
    for name in ("easy", "hard"):
        rung = fields.rung(name)
        built = fields.build_field(
            rung, path=directory / f"{name}.zarr", n_time=fields.N_TIME, seed=20_260_830
        )
        # The subgrid, in the store's own (y, x) order.
        ys = range(0, fields.N_NORMAL, SUBGRID)
        xs = range(0, fields.N_PARALLEL, SUBGRID)
        values = xr.open_zarr(built.uri)["sla"].values
        rows = np.asarray(
            [values[:, iy, ix] for iy in ys for ix in xs], dtype=np.float64
        )
        mask = np.ones(rows.shape, dtype=bool)

        start = time.perf_counter()
        result = fit(
            rows,
            built.t,
            _signal_spec(),
            _candidates(),
            Criterion.AIC,
            mask=mask,
            engine=KalmanEngine(),
        )
        seconds = time.perf_counter() - start

        ok = result.outcome == Outcome.OK.code
        per_point = result.n_iter.copy()
        per_point[~ok] = 0
        totals = per_point.sum(axis=1)
        emit(
            handle,
            {
                "record": "criterion_17",
                "rung": name,
                "coherence_length": rung.coherence_length,
                "contrast": rung.contrast,
                "n_time": fields.N_TIME,
                "points_sampled": int(rows.shape[0]),
                "points_total": fields.N_NORMAL * fields.N_PARALLEL,
                "subgrid_stride": SUBGRID,
                "cells_ok": int(ok.sum()),
                "cells_total": int(ok.size),
                "iterations_total": int(totals.sum()),
                "iterations_per_point_mean": float(totals.mean()),
                "iterations_per_point_std": float(totals.std(ddof=1)),
                "iterations_per_point_min": int(totals.min()),
                "iterations_per_point_max": int(totals.max()),
                "seconds": seconds,
                "seconds_per_point": seconds / rows.shape[0],
                "is_a_sample": True,
            },
        )


def _candidates() -> list[ProcessSpec]:
    """The shipped set, built through the same registry the config resolves."""

    def term(kind: str) -> TermSpec:
        family = kernel_registry[kind]()
        specs = {
            name: replace(spec, default=spec.default)
            for name, spec in family.param_specs().items()
        }
        return TermSpec(
            kind=kind,
            params=specs,
            ordering_param=getattr(family, "ordering_param", None),
        )

    return [
        ProcessSpec((term("white"),)),
        ProcessSpec((term("matern12"), term("white"))),
    ]


def _signal_spec() -> SignalSpec:
    """Constant plus trend -- the same two terms the benchmark config names."""
    return SignalSpec((Constant(), Trend()))


# --------------------------------------------------------------------------
# Reading B -- the lever's sign, with the contrast held fixed
# --------------------------------------------------------------------------


def _lever_rung(name: str, coherence_length: float) -> fields.Rung:
    """A rung that varies `l` alone, at the easy rung's contrast."""
    easy = fields.rung("easy")
    return fields.Rung(
        name=name,
        coherence_length=coherence_length,
        contrast=easy.contrast,
        sources={
            "coherence_length": (
                "constructed for the lever measurement: the only quantity that "
                "varies between the two fields of reading B"
            ),
            "contrast": (
                "held at the easy rung's value, so this reading isolates `l` "
                "from the composite dial the shipped rungs move"
            ),
        },
    )


def reading_b(handle: TextIO, directory: Path) -> None:
    """The saving under a long `l` against a short one, at `N = 96`."""
    easy = fields.rung("easy")
    hard = fields.rung("hard")
    for label, length in (
        ("long", easy.coherence_length),
        ("short", hard.coherence_length),
    ):
        rung = _lever_rung(f"lever_{label}", length)
        built = fields.build_field(
            rung,
            path=directory / f"lever_{label}.zarr",
            n_time=N_TIME_LEVER,
            seed=20_260_830,
        )
        config_path = fields.write_config(directory, f"lever_{label}.toml", built.uri)

        cold = run(config_path, directory / f"lever_{label}_cold.zarr")
        warm = run_two_pass(config_path, directory / f"lever_{label}_warm.zarr")

        cold_iterations = fields.iteration_count(cold.store_path)
        warm_iterations = fields.iteration_count(warm.store_path)
        warm_started = (
            warm.pass2.warm_start.warm_started
            if warm.pass2 is not None and warm.pass2.warm_start is not None
            else 0
        )
        saving = (
            1.0 - warm_iterations.total / cold_iterations.total
            if cold_iterations.total
            else 0.0
        )
        emit(
            handle,
            {
                "record": "lever",
                "arm": label,
                "coherence_length": length,
                "contrast": rung.contrast,
                "n_time": N_TIME_LEVER,
                "cold_iterations_total": cold_iterations.total,
                "warm_iterations_total": warm_iterations.total,
                "cold_iterations_per_point": cold_iterations.per_point,
                "warm_iterations_per_point": warm_iterations.per_point,
                "saving_fraction": saving,
                "warm_started_cells": int(warm_started),
                # The void clause: no warm start means the mechanism did not
                # run and the saving is a measurement of the store round-trip.
                "void_no_warm_start": int(warm_started) == 0,
                "is_a_sign_not_a_magnitude": True,
                "why": (
                    f"N = {N_TIME_LEVER} measures a DIFFERENT number from "
                    "N = 630 rather than a weaker one -- obstacle 3 of "
                    "criterion 12's reduced scope. Only the ordering is "
                    "claimed."
                ),
            },
        )


def main() -> None:
    """Run the requested readings, appending one JSON record per result."""
    out = Path(sys.argv[1])
    mode = sys.argv[2] if len(sys.argv) > 2 else "all"
    with out.open("a", encoding="utf-8") as handle:
        emit(
            handle,
            {
                "record": "header",
                "task": "2d plan Task 1 -- the field's iteration count and the lever",
                "mode": mode,
                "predictions": "phase2d-field-predictions.json",
                "git_head": subprocess.run(  # noqa: S603
                    ["/usr/bin/env", "git", "rev-parse", "HEAD"],  # noqa: S607
                    capture_output=True,
                    text=True,
                    check=False,
                ).stdout.strip(),
                "instrument": {
                    "geometry": [fields.N_NORMAL, fields.N_PARALLEL],
                    "boundary_index": fields.BOUNDARY_INDEX,
                    "coarse_stride": fields.COARSE_STRIDE,
                    "candidates": ["white", "white + matern12"],
                },
            },
        )
        reading = quiet_check()
        emit(handle, reading)
        if not reading["quiet"]:
            emit(
                handle,
                {
                    "record": "refused",
                    "why": (
                        "the host was not quiet: no core was free for a "
                        "single-threaded measurement. (a2b) -- the value is "
                        "made unavailable rather than emitted with a caveat."
                    ),
                },
            )
            return
        with threadpool_limits(limits=1), tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            if mode in {"a", "all"}:
                reading_a(handle, directory)
            if mode in {"b", "all"}:
                reading_b(handle, directory)


if __name__ == "__main__":
    main()
