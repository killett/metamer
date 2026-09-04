"""2d Task 5b -- the conditioning discriminator, version 1 against version 2.

**WHY THIS EXISTS AND WHY IT IS NOT A COLUMN OF THE RUNG.** The signal does two
things and only one was predicted: it raises iterations, and on a small fixture
it moved convergence from 93/96 to 96/96. So a null at 2c's difficulty has two
readings -- no hysteresis there, or a better-conditioned field with less to be
hysteretic about -- and the pre-decided stop was written as though only the
first existed.

**The rung runs version 2 alone**, so no column added to it can compare two
constructions. The comparison needs both, interleaved in one session. That is
this probe. It costs about eleven minutes against the rung's 13.2 h, so it runs
FIRST: a conditioning difference is then something we KNOW before the thirteen
hours rather than something we REPORT inside them.

Predictions are committed before this runs, at
`phase2d-difficulty-rung-predictions.json`, readings C1 and C2. **Both are
BANDS**, because version 2 could condition better or worse and both are
findings, and both widths come from an argument -- the trend is one column of
the design matrix and is absorbed exactly, so it should move the PATH and not
the CURVATURE -- rather than from the 93/96 observation that raised the
question.

**IT SAMPLES THE SHIPPED BUILDER, NOT A HAND-DRAWN SET AT `BASE`.** The field's
`factor` runs 0.5 to 3.0, so 16 series drawn at `BASE` would answer a question
about `BASE` and not about the field -- the representativeness failure this
project keeps meeting. The points are spread across both regimes and the whole
factor range.

Usage:

    phase2d-conditioning-probe.py <out.jsonl>
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, TextIO

import numpy as np
import xarray as xr

from metamer.bench import fields, host
from metamer.core.criteria import Criterion
from metamer.core.engines.kalman import KalmanEngine
from metamer.core.fit import fit
from metamer.core.outcomes import Outcome

#: The two constructions under comparison.
VERSIONS: tuple[int, ...] = (1, 2)

#: Sample points, spread across BOTH regimes and the whole factor range. The
#: boundary is at `y = 16`, so four `y` values fall either side; two `x` columns
#: give 16 points, which is the size the cost was priced at.
SAMPLE_Y: tuple[int, ...] = (2, 6, 10, 14, 18, 22, 26, 30)
SAMPLE_X: tuple[int, ...] = (3, 9)


def emit(handle: TextIO, record: dict[str, Any]) -> None:
    """Append one JSON record and flush."""
    handle.write(json.dumps(record, default=str) + "\n")
    handle.flush()


def git_head() -> str:
    """The commit this ran at, so the reading names its own tree."""
    return subprocess.run(  # noqa: S603
        ["/usr/bin/env", "git", "rev-parse", "HEAD"],  # noqa: S607
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def fit_one(series: np.ndarray, t: np.ndarray) -> tuple[Any, float]:
    """Fit one series through the shipped `fit`, and time it."""
    y = series[None, :].astype(np.float64)
    started = time.perf_counter()
    result = fit(
        y,
        t,
        fields.signal_spec(),
        fields.candidate_specs(),
        Criterion.AIC,
        mask=np.ones(y.shape, dtype=np.bool_),
        engine=KalmanEngine(),
    )
    return result, time.perf_counter() - started


def main() -> None:
    """Gate on the host, build both constructions, and fit them interleaved."""
    out = Path(sys.argv[1])
    with out.open("w", encoding="utf-8") as handle:
        emit(
            handle,
            {
                "record": "header",
                "task": "2d Task 5b -- the conditioning discriminator, version 1 against version 2",
                "predictions": "phase2d-difficulty-rung-predictions.json",
                "readings": ["C1", "C2"],
                "git_head": git_head(),
                "instrument": {
                    "rung": "easy",
                    "seed": fields.FIELD_SEED,
                    "geometry": [fields.N_NORMAL, fields.N_PARALLEL],
                    "n_time": fields.N_TIME,
                    "boundary_index": fields.BOUNDARY_INDEX,
                    "candidates": list(fields.CANDIDATES),
                    "signal_terms_the_config_fits": list(fields.SIGNAL_TERMS),
                    "drawn_signal_terms": list(fields.DRAWN_SIGNAL_TERMS),
                    "drawn_signal_rise_sigmas": fields.SIGNAL_RISE_SIGMAS,
                    "draw_method": fields.DRAW_METHOD,
                    "versions": list(VERSIONS),
                    "sample_y": list(SAMPLE_Y),
                    "sample_x": list(SAMPLE_X),
                    "arms_are_interleaved": True,
                },
            },
        )

        reading = host.quiet_check()
        emit(handle, reading.as_record())
        if not reading.quiet:
            # **THE GATE REFUSES, IT DOES NOT ANNOTATE.** Task 0's fourth defect
            # was a quiet check whose result was recorded beside a number that
            # was kept anyway.
            emit(handle, dict(host.REFUSAL))
            raise SystemExit(1)

        with TemporaryDirectory() as directory:
            root = Path(directory)
            built = {
                version: fields.build_field(
                    fields.rung("easy"),
                    path=root / f"v{version}.zarr",
                    seed=fields.FIELD_SEED,
                    construction_version=version,
                )
                for version in VERSIONS
            }
            values = {
                version: xr.open_zarr(truth.uri)["sla"].values
                for version, truth in built.items()
            }
            t = built[VERSIONS[0]].t

            # **INTERLEAVED BY POINT, NOT BY BLOCK.** Two blocks would let any
            # drift in the host align with the construction, which is the
            # comparison this probe is making.
            for iy in SAMPLE_Y:
                for ix in SAMPLE_X:
                    for version in VERSIONS:
                        result, seconds = fit_one(values[version][:, iy, ix], t)
                        ok = result.outcome == Outcome.OK.code
                        cond = np.asarray(result.hessian_cond, dtype=np.float64)
                        emit(
                            handle,
                            {
                                "record": "conditioning_probe",
                                "construction_version": version,
                                "y": int(iy),
                                "x": int(ix),
                                "regime": "A" if iy < fields.BOUNDARY_INDEX else "B",
                                "sigma": float(built[version].parameters[iy, ix, 0]),
                                "cells": int(ok.size),
                                "cells_ok": int(ok.sum()),
                                "outcome_codes": [
                                    int(c) for c in result.outcome.ravel()
                                ],
                                "iterations_total": int(result.n_iter[ok].sum()),
                                # NaN is UNDEFINED and has two causes -- no
                                # Hessian, or one that is not positive definite.
                                # Both are COUNTED here; a median over the
                                # defined values alone would report a partly
                                # unmeasured field as better conditioned.
                                "hessian_cond": [
                                    None if not np.isfinite(c) else float(c)
                                    for c in cond.ravel()
                                ],
                                "hessian_cond_undefined": int(
                                    np.count_nonzero(~np.isfinite(cond))
                                ),
                                "seconds": seconds,
                            },
                        )


if __name__ == "__main__":
    main()
