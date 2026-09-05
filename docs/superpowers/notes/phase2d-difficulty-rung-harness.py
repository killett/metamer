"""2d Task 5b -- the difficulty rung, on field construction version 2.

**THIS IS A CALLER**, on the same terms as the easy rung's harness:
`report.run_rung` builds the field, runs the cold pass, runs the shipped
two-pass, runs the map's arms, takes the null FIRST and then the widths, and
returns a `RungReport`. Nothing here re-implements any of it -- (j5).

**WHAT DIFFERS FROM THE EASY RUNG'S RUN IS THE CONSTRUCTION VERSION AND NOTHING
ELSE.** The rung is `easy`, the seed is `fields.FIELD_SEED`, the geometry and
record length are the shipped ones. `build_field` draws the trend at the
current default, so this field carries what 2c's carried, and the instrument
block records `field_construction_version` from the field that was BUILT.

**THE PREDICTIONS ARE IN `phase2d-difficulty-rung-predictions.json` AND WERE
COMMITTED BEFORE THIS RAN**, together with the conditioning discriminator whose
two bands held first. The stop is stated there against 43.94, and R1's
lower-edge caution is written there in advance.

**WHAT THIS HARNESS ADDS**, beyond the driver: the quiet check that GATES, one
thread so the cost block is comparable with the rate the budget is priced at,
the wiring smoke before the hours are spent, R4's outcome distribution per arm
read from the stores, and a preconditions block on the cost -- the session was
LIVE on the same four cores for the whole run, so the seconds carry that and
the iterations do not.

**THE QUIET CHECK RUNS ONCE, HERE, BEFORE THE RUN.** `run_rung` does not
re-check, so a host that turns loud mid-run cannot abort a measurement whose
iterations, smear and outcome distribution are host-independent. The gate's
input is host-wide and not this container's (open question 22), which is why
that matters.

Usage:
    phase2d-difficulty-rung-harness.py <out.jsonl> [smoke|full]
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
import zarr
from threadpoolctl import threadpool_limits

from metamer.batch.store import ITERATIONS_UNSET
from metamer.bench import fields, host, report
from metamer.core.outcomes import Outcome

#: The conditioning probe's version-2 non-OK fraction, which R4 reads the
#: rung's own distribution against. **TRANSCRIBED ON PURPOSE**: it is the
#: expected value of a check, taken from an artifact written before this run.
PROBE_V2_NOT_OK_FRACTION = 1 / 48
PROBE_SOURCE = "phase2d-conditioning-probe-measured.jsonl, version 2, 2026-09-04"

#: The reduced geometry the wiring smoke uses -- the smallest normal axis on
#: which a legal interior null line exists.
SMOKE_N_NORMAL = 26
SMOKE_N_PARALLEL = 2
SMOKE_N_TIME = 24

REPORT_PATH = Path("docs/superpowers/notes/phase2d-difficulty-rung-report.json")


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


def outcome_distribution(store: Path, arm: str) -> dict[str, Any]:
    """R4: the outcome codes over every fitted cell of one arm's store.

    Read from the store's own two arrays, exactly as the suite's real-store
    test does, so the reading has no second derivation path.
    """
    root = zarr.open_group(str(store), mode="r")
    written = root["primitives/iterations"]
    outcome = root["status/outcome"]
    if not isinstance(written, zarr.Array) or not isinstance(outcome, zarr.Array):
        raise TypeError("the store's iteration and outcome nodes are not arrays")
    iterations = np.asarray(written[:])
    codes = np.asarray(outcome[:])
    fitted = iterations != ITERATIONS_UNSET
    ok = fitted & (codes == Outcome.OK.code)
    counts: dict[str, int] = {}
    for code in np.unique(codes[fitted]):
        counts[Outcome.from_code(int(code)).name] = int((codes[fitted] == code).sum())
    not_ok = (
        float((fitted.sum() - ok.sum()) / fitted.sum())
        if fitted.any()
        else float("nan")
    )
    return {
        "record": "outcome_distribution",
        "arm": arm,
        "cells_fitted": int(fitted.sum()),
        "cells_ok": int(ok.sum()),
        "not_ok_fraction": not_ok,
        "counts": counts,
        "probe_v2_not_ok_fraction": PROBE_V2_NOT_OK_FRACTION,
        "probe_source": PROBE_SOURCE,
        "r4_difference": not_ok - PROBE_V2_NOT_OK_FRACTION,
        "r4_band": 0.05,
        "r4_held": abs(not_ok - PROBE_V2_NOT_OK_FRACTION) <= 0.05,
    }


def wiring_smoke(handle: TextIO, directory: Path) -> bool:
    """Run the pipeline at reduced geometry before the hours are spent."""
    started = time.perf_counter()
    smoke = report.run_rung(
        fields.rung("easy"),
        out_dir=directory / "smoke",
        seed=fields.FIELD_SEED,
        is_a_smoke_run=True,
        n_normal=SMOKE_N_NORMAL,
        n_parallel=SMOKE_N_PARALLEL,
        n_time=SMOKE_N_TIME,
    )
    seconds = time.perf_counter() - started
    block = smoke.instrument
    wired = (
        block["audit_seed"] == fields.AUDIT_SEED
        and block["seed"] == fields.FIELD_SEED
        and block["field_construction_version"] == fields.FIELD_CONSTRUCTION_VERSION
    )
    emit(
        handle,
        {
            "record": "wiring_smoke",
            "seconds": seconds,
            "is_a_smoke_run": block["is_a_smoke_run"],
            "geometry": [SMOKE_N_NORMAL, SMOKE_N_PARALLEL, SMOKE_N_TIME],
            "field_seed_in_the_block": block["seed"],
            "audit_seed_in_the_block": block["audit_seed"],
            "field_construction_version_in_the_block": block[
                "field_construction_version"
            ],
            "drawn_signal_in_the_block": {
                "terms": block["drawn_signal_terms"],
                "rise_sigmas": block["drawn_signal_rise_sigmas"],
            },
            "wired": wired,
            "contaminated": smoke.contaminated,
            "null_profile": list(smoke.null_line.profile),
            "not_a_measurement": "reduced geometry and record length; the flag is in the block",
        },
    )
    return bool(wired)


def difficulty_rung(handle: TextIO, directory: Path, quiet: host.HostReading) -> None:
    """The measurement. One rung, one report, every arm in one session."""
    out_dir = directory / "rung"
    started = time.perf_counter()
    measured = report.run_rung(
        fields.rung("easy"), out_dir=out_dir, seed=fields.FIELD_SEED
    )
    seconds = time.perf_counter() - started

    cost: dict[str, Any] = dict(measured.cost)
    # **THE PRECONDITIONS THE SECONDS DEPEND ON, RECORDED WITH THEM.** A rate
    # is a measurement of a workload on a machine, and this machine was shared
    # with a live agent session for the whole run. Iterations do not carry
    # this; seconds do.
    cost["preconditions"] = {
        "threads": 1,
        "session_live_on_the_same_cores": True,
        "physical_cores": quiet.physical_cores,
        "loadavg_at_start": list(quiet.loadavg),
        "gate_input_is_host_wide": "open question 22",
        "seconds_are_the_contaminated_half": (
            "iterations, the smear and the outcome distribution are host-independent; "
            "only this block is"
        ),
    }

    emit(
        handle,
        {
            "record": "rung_report",
            "wall_clock_seconds": seconds,
            "hours": seconds / 3600.0,
            "report": measured.reproducible(),
            "cost": cost,
        },
    )
    payload: dict[str, Any] = dict(measured.reproducible())
    payload["cost"] = cost
    REPORT_PATH.write_text(json.dumps(payload, indent=2, default=str) + "\n")

    for arm in ("cold", "warm"):
        emit(handle, outcome_distribution(out_dir / f"easy-{arm}.zarr", arm))

    # **THE ACROSS-RUNG GATE, AND IT RAISES**, after the report is written so
    # the diagnosis -- the null's own profile -- is on disk first.
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
                "task": "2d Task 5b -- the difficulty rung on field construction version 2",
                "mode": mode,
                "predictions": "phase2d-difficulty-rung-predictions.json",
                "stop_is_stated_against": 43.94,
                "git_head": _git_head(),
                "rung": "easy",
                "field_seed": fields.FIELD_SEED,
                "field_construction_version": fields.FIELD_CONSTRUCTION_VERSION,
                "drawn_signal_terms": list(fields.DRAWN_SIGNAL_TERMS),
                "drawn_signal_rise_sigmas": fields.SIGNAL_RISE_SIGMAS,
                "audit_seed": fields.AUDIT_SEED,
                "threads": 1,
                "session_live_on_the_same_cores": True,
            },
        )
        reading = host.quiet_check()
        emit(handle, reading.as_record())
        if not reading.quiet:
            emit(handle, dict(host.REFUSAL))
            raise SystemExit(1)
        with threadpool_limits(limits=1), tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            if not wiring_smoke(handle, directory):
                emit(
                    handle,
                    {
                        "record": "refused",
                        "why": (
                            "the instrument block does not carry the seeds and the "
                            "construction version the run was keyed on, so the report "
                            "could not name its own field -- R5"
                        ),
                    },
                )
                raise SystemExit(1)
            if mode == "full":
                difficulty_rung(handle, directory, reading)


if __name__ == "__main__":
    main()
