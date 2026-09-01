"""2d Task 5 -- the easy rung: the positive control, and the gate.

**THIS IS A CALLER.** `report.run_rung` builds the field, runs the cold pass,
runs the shipped two-pass, rebuilds the warm array through the shipped
`coarse_ok` / `source_map` / `read_warm_starts`, runs the map's four arms, takes
the self arm, takes the null FIRST and then the widths, and returns a
`RungReport`. `report.require_clean` is the across-rung gate and it **raises**.
Nothing here re-implements either: **two instruments for one quantity is (j5)**
and the ordering inside `run_rung` is the mechanism.

**WHAT IT ADDS IS THE MEASUREMENT'S OWN DISCIPLINE**, which is not the driver's
job: the host quiet check that **gates**, the predictions committed before the
run, one thread so the cost block is comparable with the rate the budget is
priced at, a wiring smoke at reduced geometry before eight hours are spent, and
the criterion-17 cross-check that says this field is the fixture the committed
figure was measured on.

**THE PREDICTIONS ARE IN `phase2d-easy-rung-predictions.json` AND WERE
COMMITTED BEFORE THIS RAN.** Every reading here is read against them and
against nothing else.

Usage:
    phase2d-easy-rung-harness.py <out.jsonl> [smoke|full]
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, TextIO

import numpy as np
from threadpoolctl import threadpool_limits

from metamer.bench import fields, host, report

#: The field's draw seed. **THE SAME SEED CRITERION 17 WAS MEASURED AT**, so
#: this run's cold store contains the very fits the committed figure describes
#: and the reproduction below is an equality rather than a resemblance.
FIELD_SEED = 20_260_830

#: Criterion 17's committed reading for the easy rung, measured 2026-08-30 and
#: reproduced bit-exactly 2026-08-31 over the 96-point subgrid.
#: **TRANSCRIBED HERE ON PURPOSE**: it is the expected value of a check, taken
#: from an artifact written before this run, and a check whose expectation is
#: recomputed by the code under test checks nothing.
CRITERION_17_ITERATIONS = 2340
CRITERION_17_PER_POINT = 24.375
CRITERION_17_CELLS_OK = 287
CRITERION_17_POINTS = 96
CRITERION_17_STRIDE = 2
CRITERION_17_SOURCE = "phase2d-middle-rung-measured.jsonl, easy rung, 2026-08-31"

#: The reduced geometry the driver's smoke runs used. **26 is the smallest
#: normal axis on which a legal interior null line exists** -- the offset is 12
#: and the null needs `n_normal // 2 - 12 >= 1` -- so a field small enough to be
#: fast cannot carry the control, and this is as small as a wiring check gets.
SMOKE_N_NORMAL = 26
SMOKE_N_PARALLEL = 2
SMOKE_N_TIME = 24


def emit(handle: TextIO, record: dict[str, Any]) -> None:
    """Append one JSON record and flush, so a killed run keeps what it measured."""
    handle.write(json.dumps(record, default=str) + "\n")
    handle.flush()


def _git_head() -> str:
    """The commit this ran at, for the record."""
    return subprocess.run(  # noqa: S603
        ["/usr/bin/env", "git", "rev-parse", "HEAD"],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()


def wiring_smoke(handle: TextIO, directory: Path) -> bool:
    """Run the pipeline at reduced geometry and check what only a run can check.

    **THE ONE LINE NO UNIT TEST REACHES IS THE SEED'S.** `run_rung` reads
    `config.audit.seed` once and hands it to both the N2 map and the instrument
    block; the config round-trip and the block's recording are unit-tested
    either side of it, and this is what closes the middle. **It costs minutes
    and it runs before the eight hours, which is the whole point.**
    """
    started = time.perf_counter()
    smoke = report.run_rung(
        fields.rung("easy"),
        out_dir=directory / "smoke",
        seed=FIELD_SEED,
        is_a_smoke_run=True,
        n_normal=SMOKE_N_NORMAL,
        n_parallel=SMOKE_N_PARALLEL,
        n_time=SMOKE_N_TIME,
    )
    seconds = time.perf_counter() - started
    keyed_on_the_audit_seed = smoke.instrument["audit_seed"] == fields.AUDIT_SEED
    emit(
        handle,
        {
            "record": "wiring_smoke",
            "seconds": seconds,
            "is_a_smoke_run": smoke.instrument["is_a_smoke_run"],
            "geometry": [SMOKE_N_NORMAL, SMOKE_N_PARALLEL, SMOKE_N_TIME],
            "audit_seed_in_the_block": smoke.instrument["audit_seed"],
            "field_seed_in_the_block": smoke.instrument["seed"],
            "keyed_on_the_audit_seed": keyed_on_the_audit_seed,
            "the_two_seeds_differ": smoke.instrument["audit_seed"]
            != smoke.instrument["seed"],
            "contaminated": smoke.contaminated,
            # **THE NULL'S PROFILE TRAVELS EVEN HERE.** The first run of this
            # harness came back contaminated at this geometry and the record
            # said only `contaminated: true`, which is the one thing a firing
            # null must never say on its own: a BAND is the estimator reading
            # the field's structure and a FLAT HIGH LINE is the baseline
            # disagreement rate above a half, and they have different repairs.
            "null_cells": smoke.null_line.cells,
            "null_at_floor": smoke.null_line.at_floor,
            "null_profile": list(smoke.null_line.profile),
            "checks": dict(smoke.checks),
            "ratios": dict(smoke.ratios),
            "not_a_measurement": (
                "reduced geometry and record length; the flag is in the block. "
                "At n_parallel = 2 the majority is over two points, so the "
                "profile is nearly binary and this fixture's null is fragile "
                "by construction -- Task 4 recorded the same thing."
            ),
        },
    )
    return bool(keyed_on_the_audit_seed)


def selection_is_live(store: Path, grid_shape: tuple[int, int]) -> dict[str, Any]:
    """Report which candidates won anywhere; a collapsed axis voids every width.

    At a low iteration cap `matern12` never reaches `OK` and every point selects
    `white`; a width measured on that axis is a statement about the cap. The
    field's two regimes are candidates 1 and 2, so both must win somewhere.
    """
    selected = report._selection_map(store, grid_shape)  # noqa: SLF001
    winners = sorted({int(value) for value in np.unique(selected) if value >= 0})
    return {
        "record": "selection_axis",
        "winners": winners,
        "both_regimes_win": {1, 2} <= set(winners),
        # **OVER THE CANDIDATE SET, NOT OVER `range(len(winners))`.** The first
        # version counted as many candidates as there were WINNERS, so a field
        # where candidates 1 and 2 win reported counts for 0 and 1 and never
        # for 2 -- (c5) in this harness's own output, found by reading it.
        "counts": {
            candidate: int((selected == index).sum())
            for index, candidate in enumerate(fields.CANDIDATES)
        },
    }


def criterion_17_reproduces(store: Path) -> dict[str, Any]:
    """This run's cold store against criterion 17's committed figure.

    **THE SAME 96 POINTS, THE SAME RULE.** The committed harness fitted a
    systematic subgrid through `core.fit` and zeroed non-converged cells; this
    reads the same subgrid out of a store written by `run`, OK-only. **The two
    paths are a tiled, assembled, written run and a bare `fit`**, and iterations
    are deterministic, so agreement is exact or it is a finding.
    """
    reading = fields.iteration_count(store, stride=CRITERION_17_STRIDE, ok_only=True)
    return {
        "record": "criterion_17_reproduction",
        "expected": {
            "iterations_total": CRITERION_17_ITERATIONS,
            "iterations_per_point_mean": CRITERION_17_PER_POINT,
            "cells_ok": CRITERION_17_CELLS_OK,
            "points_sampled": CRITERION_17_POINTS,
            "subgrid_stride": CRITERION_17_STRIDE,
            "source": CRITERION_17_SOURCE,
        },
        "iterations_total": reading.total,
        "iterations_per_point_mean": reading.per_point,
        "cells_ok": reading.cells,
        "points_sampled": reading.points,
        "reproduces": (
            reading.total == CRITERION_17_ITERATIONS
            and reading.cells == CRITERION_17_CELLS_OK
            and reading.points == CRITERION_17_POINTS
        ),
    }


def easy_rung(handle: TextIO, directory: Path) -> None:
    """The measurement. One rung, one report, every arm in one session."""
    out_dir = directory / "easy"
    started = time.perf_counter()
    measured = report.run_rung(fields.rung("easy"), out_dir=out_dir, seed=FIELD_SEED)
    seconds = time.perf_counter() - started

    emit(
        handle,
        {
            "record": "rung_report",
            "wall_clock_seconds": seconds,
            "hours": seconds / 3600.0,
            "report": measured.reproducible(),
            "cost": dict(measured.cost),
        },
    )
    Path("docs/superpowers/notes/phase2d-easy-rung-report.json").write_text(
        json.dumps(measured.reproducible(), indent=2, default=str) + "\n"
    )

    emit(handle, selection_is_live(out_dir / "easy-cold.zarr", (32, 12)))
    emit(handle, criterion_17_reproduces(out_dir / "easy-cold.zarr"))

    # **THE ACROSS-RUNG GATE, AND IT RAISES.** Called after the report is
    # written, because E6 says *stop and diagnose* and the diagnosis is the
    # null's own profile -- which only the committed report carries.
    report.require_clean(measured)
    emit(
        handle,
        {
            "record": "gate",
            "require_clean": "passed",
            "null_cells": measured.null_line.cells,
            "null_at_floor": measured.null_line.at_floor,
        },
    )


def main() -> None:
    """Gate on the host, then smoke the wiring, then measure."""
    out = Path(sys.argv[1])
    mode = sys.argv[2] if len(sys.argv) > 2 else "full"
    with out.open("a", encoding="utf-8") as handle:
        emit(
            handle,
            {
                "record": "header",
                "task": "2d plan Task 5 -- the easy rung, the positive control and the gate",
                "mode": mode,
                "predictions": "phase2d-easy-rung-predictions.json",
                "git_head": _git_head(),
                "field_seed": FIELD_SEED,
                "audit_seed": fields.AUDIT_SEED,
                "threads": 1,
            },
        )
        reading = host.quiet_check()
        emit(handle, reading.as_record())
        if not reading.quiet:
            emit(handle, dict(host.REFUSAL))
            return
        with threadpool_limits(limits=1), tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            if not wiring_smoke(handle, directory):
                emit(
                    handle,
                    {
                        "record": "refused",
                        "why": (
                            "the instrument block does not carry the audit seed the "
                            "map was keyed on, so a committed report could not be "
                            "reproduced and exit criterion 9 could not pass"
                        ),
                    },
                )
                return
            if mode == "full":
                easy_rung(handle, directory)


if __name__ == "__main__":
    main()
