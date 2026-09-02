"""2d Task 5b -- the difficulty rung's calibration: choosing the value, not arguing it.

**THE LEVER IS NAMED BEFORE THIS RUNS** -- `white/sigma`, at the pre-flight, against a
probe. What this buys is the VALUE, and it buys three things at once:

| | |
|---|---|
| the value | the highest difficulty whose baseline stays separable and whose rung fits the ceiling |
| the rung's price | measured seconds at the chosen setting, because the easy rung's rate does not transfer across difficulty |
| a third point for the cost model | which has two, and two cannot tell a line from a curve -- D2's reason, and the rule Task 0's retired `2.43 + 0.324 x iterations` was retired under |

**IT FITS INDEPENDENT SERIES WITH NO FIELD, NO BOUNDARY AND NO WARM STARTS**, which is
why it is minutes rather than hours -- and why no number from it is a 2d result.

**THREE THINGS ARE MEASURED AT EVERY SETTING AND THE THIRD IS THE ONE THAT VOIDS A
RUNG:** iterations per point, seconds per point, and **the misclassification rate against
the truth**. A noisier field makes the two Matern families harder to separate, and a
baseline disagreement above a half is the **second cause** of a firing interior null --
the one that invalidates the subject rather than the estimator.

Usage:
    phase2d-difficulty-calibration.py <out.jsonl>
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from typing import Any, TextIO

import numpy as np
from threadpoolctl import threadpool_limits

from metamer.batch.timeaxis import to_decimal_years
from metamer.bench import fields, host
from metamer.core.criteria import Criterion
from metamer.core.engines.kalman import KalmanEngine
from metamer.core.fit import fit
from metamer.core.outcomes import Outcome

#: The ladder. **One quantity moves**: `sigma` is held at `BASE`'s value and
#: `white` is what varies, so a difference between two rows is attributable.
NOISE_RATIOS: tuple[float, ...] = (0.4, 0.7, 1.0, 1.4)

#: Series per setting per family. 16 gives a standard error near 0.4 iterations
#: at the spread the probe measured, which is fine enough to order a ladder
#: whose steps are expected to be several iterations.
SERIES = 16

#: The seed. **Not a field seed and not the audit's** -- this draws no field.
SEED = 5150

N_TIME = 630


def emit(handle: TextIO, record: dict[str, Any]) -> None:
    """Append one JSON record and flush, so a killed run keeps what it measured."""
    handle.write(json.dumps(record, default=str) + "\n")
    handle.flush()


def axis() -> np.ndarray:
    """The shipped converter's output, never a hand-built decimal year."""
    origin = np.datetime64("2000-01-01")
    stamps = np.array([origin + np.timedelta64(31 * i, "D") for i in range(N_TIME)])
    return to_decimal_years(stamps)


def draw(
    t: np.ndarray, kind: str, sigma: float, rho: float, white: float
) -> np.ndarray:
    """`SERIES` draws from the shipped covariance, one generator per series."""
    rows = []
    covariance = fields._covariance(t - t[0], kind, sigma, rho, white)  # noqa: SLF001
    for index in range(SERIES):
        generator = np.random.default_rng([SEED, index])
        rows.append(
            generator.multivariate_normal(
                np.zeros(N_TIME), covariance, method=fields.DRAW_METHOD
            )
        )
    return np.asarray(rows, dtype=np.float64)


def measure(handle: TextIO, ratio: float) -> None:
    """One rung of the ladder: both families, one setting."""
    t = axis()
    sigma, rho, _ = fields.BASE
    white = ratio * sigma
    specs = fields.candidate_specs()
    signal = fields.signal_spec()

    for kind in fields.FAMILY_KINDS:
        y = draw(t, kind, sigma, rho, white)
        mask = np.ones(y.shape, dtype=np.bool_)
        started = time.perf_counter()
        result = fit(
            y, t, signal, specs, Criterion.AIC, mask=mask, engine=KalmanEngine()
        )
        seconds = time.perf_counter() - started

        ok = result.outcome == Outcome.OK.code
        per_point = result.n_iter.copy()
        per_point[~ok] = 0
        totals = per_point.sum(axis=1)
        # **THE TRUTH IS THE FAMILY, AND THE CANDIDATE SET'S FIRST MEMBER IS
        # `white`.** `CANDIDATES` is (white, white + matern12, white + matern32)
        # and `FAMILY_KINDS` is (matern12, matern32), so the candidate carrying
        # family `f` is at index `f + 1`. Written as an expression over the two
        # shipped tuples rather than as a literal, because a fourth candidate
        # would silently move it.
        carries = fields.CANDIDATES.index(f"white + {kind}")
        selected = np.asarray(result.ranking.best_index)
        misclassified = float(np.mean(selected != carries))

        emit(
            handle,
            {
                "record": "calibration",
                "white_over_sigma": ratio,
                "white": white,
                "sigma": sigma,
                "rho": rho,
                "family": kind,
                "true_candidate_index": carries,
                "series": int(y.shape[0]),
                "iterations_per_point_mean": float(totals.mean()),
                "iterations_per_point_std": float(totals.std(ddof=1)),
                "iterations_per_point_min": int(totals.min()),
                "iterations_per_point_max": int(totals.max()),
                "cells_ok": int(ok.sum()),
                "cells_total": int(ok.size),
                "misclassified_fraction": misclassified,
                "seconds_per_point": seconds / y.shape[0],
                "is_a_sample": True,
            },
        )


def main() -> None:
    """Gate on the host, then walk the ladder."""
    out = sys.argv[1]
    with open(out, "a", encoding="utf-8") as handle:
        emit(
            handle,
            {
                "record": "header",
                "task": "2d Task 5b -- the difficulty rung's calibration",
                "predictions": "phase2d-difficulty-calibration-predictions.json",
                "git_head": subprocess.run(  # noqa: S603
                    ["/usr/bin/env", "git", "rev-parse", "HEAD"],  # noqa: S607
                    capture_output=True,
                    text=True,
                    check=False,
                ).stdout.strip(),
                "lever": "white / sigma",
                "ladder": list(NOISE_RATIOS),
                "n_time": N_TIME,
                "series_per_setting_per_family": SERIES,
                "seed": SEED,
                "candidates": list(fields.CANDIDATES),
                "not_a_rung": (
                    "independent series, no field, no boundary, no warm starts; "
                    "no number here is a 2d result"
                ),
            },
        )
        reading = host.quiet_check()
        emit(handle, reading.as_record())
        if not reading.quiet:
            emit(handle, dict(host.REFUSAL))
            return
        with threadpool_limits(limits=1):
            for ratio in NOISE_RATIOS:
                measure(handle, ratio)


if __name__ == "__main__":
    main()
