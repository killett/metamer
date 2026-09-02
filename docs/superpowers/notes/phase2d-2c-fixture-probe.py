"""2d Task 5b -- what makes 2c's field 40.79, read off 2c's own fixture.

**(j4): AN EXISTING MEASUREMENT IS EVIDENCE, AND 2c's FIXTURE IS IN THE TREE.**
`warmstart-spike-harness.py` carries the construction that produced **40.79 cold
iterations per point at `N = 630`**, and the difficulty ladder says the noise
floor accounts for only about **3.5 of the 16.4-iteration gap** from 2d's field.
**Probing 2c's field directly costs under an hour; approaching its difficulty by
building rungs costs 15 hours a step.**

**THE FIELD IS BUILT BY 2c's OWN CODE, IMPORTED RATHER THAN RE-SPELLED.** A
second spelling of the fixture under test would be a second fixture -- (j9) --
and the whole point is to measure the thing that produced the number.

**FOUR SETTINGS, AND THE DECOMPOSITION IS THE READING.**

| # | field | isolates |
|---|---|---|
| 1 | 2c's, exactly as its harness builds it | **the target**: does 40.79 reproduce under the shipped `fit`? |
| 2 | 2c's, with the SIGNAL removed from the draw | 2c adds `2.0 + 0.3 x (t - t.mean())` to every series and 2d adds **nothing** |
| 3 | 2c's parameters on 2d's TIME AXIS | 31-day steps against exact months -- expected to be nothing, measured because it is free |
| 4 | 2d's field at the same points, for the same `N` | the comparison arm, so the gap is measured in one session rather than across two |

**EVERY SETTING IS FITTED THROUGH THE SHIPPED `fit` WITH THE SHIPPED CANDIDATE
SET**, so the only thing that varies between rows is the data.

Usage:
    phase2d-2c-fixture-probe.py <out.jsonl>
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path
from types import ModuleType
from typing import Any, TextIO

import numpy as np
from threadpoolctl import threadpool_limits

from metamer.batch.timeaxis import to_decimal_years
from metamer.bench import fields, host
from metamer.core.criteria import Criterion
from metamer.core.engines.kalman import KalmanEngine
from metamer.core.fit import fit
from metamer.core.outcomes import Outcome

#: 2c's harness, imported by path. **Its `true_params` and `matern_cov` are the
#: specification of the fixture that produced 40.79.**
_HARNESS = Path(__file__).with_name("warmstart-spike-harness.py")

#: Points per regime. 2c's own field is built on an `n_side` grid; 8 per regime
#: matches the difficulty ladder's series count closely enough to compare
#: spreads, and the readings are per point.
N_SIDE = 4

N_TIME = 630
SEED = 5150


def load_2c() -> ModuleType:
    """Import 2c's harness as a module, without running it."""
    spec = importlib.util.spec_from_file_location("warmstart_spike", _HARNESS)
    if spec is None or spec.loader is None:  # pragma: no cover - path is fixed
        raise RuntimeError(f"cannot import {_HARNESS}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def emit(handle: TextIO, record: dict[str, Any]) -> None:
    """Append one JSON record and flush."""
    handle.write(json.dumps(record, default=str) + "\n")
    handle.flush()


def draw_2c(
    module: ModuleType, *, with_signal: bool, axis: str
) -> tuple[np.ndarray, np.ndarray, list[dict[str, Any]]]:
    """2c's field, by 2c's own `true_params` and covariance.

    Args:
        module: The imported harness.
        with_signal: Whether to add 2c's `2.0 + 0.3 (t - t.mean())`. **2c's own
            build adds it and 2d's adds nothing**, which is the difference this
            probe exists to price.
        axis: `"2c"` for `arange(n)/12`, `"2d"` for the 31-day stamps through
            `to_decimal_years`.
    """
    if axis == "2c":
        t = np.arange(N_TIME, dtype=np.float64) / 12.0
    else:
        origin = np.datetime64("2000-01-01")
        stamps = np.array([origin + np.timedelta64(31 * i, "D") for i in range(N_TIME)])
        t = to_decimal_years(stamps)
        t = t - t[0]

    rows: list[np.ndarray] = []
    truth: list[dict[str, Any]] = []
    for row in range(N_SIDE):
        for col in range(N_SIDE):
            # **2c's OWN PARAMETERS**, at a column inside each regime. Its
            # `BOUNDARY_COL` is 6 on its own grid, so a 4-wide grid would sit
            # entirely in region A; the column is mapped so both regimes appear.
            source_col = col if col < N_SIDE // 2 else module.BOUNDARY_COL + col
            spec = module.true_params(row, source_col, 12)
            covariance = module.matern_cov(t, spec["kind"], spec["sigma"], spec["rho"])
            covariance = covariance + spec["white"] ** 2 * np.eye(N_TIME)
            generator = np.random.default_rng([SEED, row, col])
            draw = generator.multivariate_normal(
                np.zeros(N_TIME), covariance, method=fields.DRAW_METHOD
            )
            if with_signal:
                draw = draw + 2.0 + 0.3 * (t - t.mean())
            rows.append(draw)
            truth.append(spec)
    return np.asarray(rows, dtype=np.float64), t, truth


def draw_2d() -> tuple[np.ndarray, np.ndarray, list[dict[str, Any]]]:
    """2d's field parameters, at the same count, as the comparison arm."""
    origin = np.datetime64("2000-01-01")
    stamps = np.array([origin + np.timedelta64(31 * i, "D") for i in range(N_TIME)])
    t = to_decimal_years(stamps)
    sigma, rho, white = fields.BASE
    rows: list[np.ndarray] = []
    truth: list[dict[str, Any]] = []
    for index in range(N_SIDE * N_SIDE):
        kind = fields.FAMILY_KINDS[index % 2]
        covariance = fields._covariance(t - t[0], kind, sigma, rho, white)  # noqa: SLF001
        generator = np.random.default_rng([SEED, index])
        rows.append(
            generator.multivariate_normal(
                np.zeros(N_TIME), covariance, method=fields.DRAW_METHOD
            )
        )
        truth.append({"kind": kind, "sigma": sigma, "rho": rho, "white": white})
    return np.asarray(rows, dtype=np.float64), t, truth


def measure(
    handle: TextIO,
    name: str,
    y: np.ndarray,
    t: np.ndarray,
    truth: list[dict[str, Any]],
) -> None:
    """Fit one setting through the shipped path and record the three readings."""
    specs = fields.candidate_specs()
    mask = np.ones(y.shape, dtype=np.bool_)
    started = time.perf_counter()
    result = fit(
        y,
        t,
        fields.signal_spec(),
        specs,
        Criterion.AIC,
        mask=mask,
        engine=KalmanEngine(),
    )
    seconds = time.perf_counter() - started

    ok = result.outcome == Outcome.OK.code
    per_point = result.n_iter.copy()
    per_point[~ok] = 0
    totals = per_point.sum(axis=1)
    selected = np.asarray(result.ranking.best_index)
    carries = np.asarray(
        [fields.CANDIDATES.index(f"white + {spec['kind']}") for spec in truth]
    )

    emit(
        handle,
        {
            "record": "probe",
            "setting": name,
            "points": int(y.shape[0]),
            "iterations_per_point_mean": float(totals.mean()),
            "iterations_per_point_std": float(totals.std(ddof=1)),
            "iterations_per_point_min": int(totals.min()),
            "iterations_per_point_max": int(totals.max()),
            "cells_ok": int(ok.sum()),
            "cells_total": int(ok.size),
            "misclassified_fraction": float(np.mean(selected != carries)),
            "seconds_per_point": seconds / y.shape[0],
            "white_over_sigma": sorted(
                {round(spec["white"] / spec["sigma"], 3) for spec in truth}
            ),
            "rho": sorted({round(float(spec["rho"]), 3) for spec in truth}),
            "families": sorted({spec["kind"] for spec in truth}),
            "is_a_sample": True,
        },
    )


def main() -> None:
    """Gate on the host, then walk the four settings."""
    out = sys.argv[1]
    module = load_2c()
    with open(out, "a", encoding="utf-8") as handle:
        emit(
            handle,
            {
                "record": "header",
                "task": "2d Task 5b -- what makes 2c's field 40.79",
                "predictions": "phase2d-2c-fixture-probe-predictions.json",
                "git_head": subprocess.run(  # noqa: S603
                    ["/usr/bin/env", "git", "rev-parse", "HEAD"],  # noqa: S607
                    capture_output=True,
                    text=True,
                    check=False,
                ).stdout.strip(),
                "fixture_source": str(_HARNESS),
                "n_time": N_TIME,
                "points_per_setting": N_SIDE * N_SIDE,
                "seed": SEED,
                "candidates": list(fields.CANDIDATES),
                "not_a_rung": (
                    "independent series, no boundary, no warm starts; no number "
                    "here is a 2d result"
                ),
            },
        )
        reading = host.quiet_check()
        emit(handle, reading.as_record())
        if not reading.quiet:
            emit(handle, dict(host.REFUSAL))
            return

        with threadpool_limits(limits=1):
            y, t, truth = draw_2c(module, with_signal=True, axis="2c")
            measure(handle, "2c as its harness builds it", y, t, truth)

            y, t, truth = draw_2c(module, with_signal=False, axis="2c")
            measure(handle, "2c without its signal", y, t, truth)

            y, t, truth = draw_2c(module, with_signal=True, axis="2d")
            measure(handle, "2c on 2d's time axis", y, t, truth)

            y, t, truth = draw_2d()
            measure(handle, "2d's own parameters, same session", y, t, truth)


if __name__ == "__main__":
    main()
