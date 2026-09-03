"""2d Task 5b -- 2d's own field WITH a signal: the repair, measured.

**THIS MEASURES A DEFECT'S REPAIR, NOT A KNOB SETTING.** The 2c probe localised
essentially the whole 24.4-to-43.94 difficulty gap in one difference: **2c's
series carry `2.0 + 0.3 x (t - t.mean())` and 2d's carry nothing**, while both
configs fit `constant + trend`. Removing the signal from 2c's own field takes it
from **43.94 to 25.69** iterations per point.

**SO 2d's FIELD BUILDER IS MISSING A TERM THE WHOLE DESIGN ASSUMES** -- section
11.2's subject is trend uncertainty, section 16.2's benchmark is for a
trend-estimation package, and real altimetry has sea-level rise. **The
difficulty is a consequence of the repair rather than its purpose.**

**FOUR SETTINGS, ON 2d's OWN PARAMETERS**, so the only thing that varies is the
signal:

| # | signal added to the draw | isolates |
|---|---|---|
| 1 | none | 2d as it ships -- the baseline, in this session |
| 2 | `2.0 + 0.3 x (t - t.mean())` | **2c's own signal**, so the two are comparable |
| 3 | `2.0 + 0.15 x (t - t.mean())` | half the trend: is the amplitude a lever, or is any trend enough? |
| 4 | `0.3 x (t - t.mean())` | the trend without the offset: which half does the work |

**THREE READINGS AT EACH**, and the third is the one that can void a rung:
iterations per point, seconds per point, and **misclassification against the
truth**.

Usage:
    phase2d-signal-probe.py <out.jsonl>
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

N_TIME = 630
SERIES_PER_FAMILY = 8
SEED = 5150

#: `(name, offset, trend per year)`. **2c's values are row 2**, so this field
#: and 2c's are comparable in the one quantity under test.
SIGNALS: tuple[tuple[str, float, float], ...] = (
    ("none -- 2d as it ships", 0.0, 0.0),
    ("2c's signal: offset 2.0, trend 0.3/yr", 2.0, 0.3),
    ("half trend: offset 2.0, trend 0.15/yr", 2.0, 0.15),
    ("trend only: offset 0.0, trend 0.3/yr", 0.0, 0.3),
)


def emit(handle: TextIO, record: dict[str, Any]) -> None:
    """Append one JSON record and flush."""
    handle.write(json.dumps(record, default=str) + "\n")
    handle.flush()


def axis() -> np.ndarray:
    """The shipped converter's output, never a hand-built decimal year."""
    origin = np.datetime64("2000-01-01")
    stamps = np.array([origin + np.timedelta64(31 * i, "D") for i in range(N_TIME)])
    return to_decimal_years(stamps)


def measure(handle: TextIO, name: str, offset: float, trend: float) -> None:
    """One signal setting, both families, on 2d's own parameters."""
    t = axis()
    sigma, rho, white = fields.BASE
    specs = fields.candidate_specs()

    rows: list[np.ndarray] = []
    truth: list[str] = []
    for kind in fields.FAMILY_KINDS:
        covariance = fields._covariance(t - t[0], kind, sigma, rho, white)  # noqa: SLF001
        for index in range(SERIES_PER_FAMILY):
            generator = np.random.default_rng([SEED, index])
            draw = generator.multivariate_normal(
                np.zeros(N_TIME), covariance, method=fields.DRAW_METHOD
            )
            rows.append(draw + offset + trend * (t - t.mean()))
            truth.append(kind)

    y = np.asarray(rows, dtype=np.float64)
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
    carries = np.asarray([fields.CANDIDATES.index(f"white + {kind}") for kind in truth])

    emit(
        handle,
        {
            "record": "signal_probe",
            "setting": name,
            "offset": offset,
            "trend_per_year": trend,
            "record_span_years": float(t[-1] - t[0]),
            "trend_rise_over_record": trend * float(t[-1] - t[0]),
            "sigma": sigma,
            "white_over_sigma": white / sigma,
            "points": int(y.shape[0]),
            "iterations_per_point_mean": float(totals.mean()),
            "iterations_per_point_std": float(totals.std(ddof=1)),
            "iterations_per_point_min": int(totals.min()),
            "iterations_per_point_max": int(totals.max()),
            "cells_ok": int(ok.sum()),
            "cells_total": int(ok.size),
            "misclassified_fraction": float(np.mean(selected != carries)),
            "seconds_per_point": seconds / y.shape[0],
            "is_a_sample": True,
        },
    )


def main() -> None:
    """Gate on the host, then walk the four signal settings."""
    out = sys.argv[1]
    with open(out, "a", encoding="utf-8") as handle:
        emit(
            handle,
            {
                "record": "header",
                "task": "2d Task 5b -- 2d's field with a signal, the defect's repair measured",
                "predictions": "phase2d-signal-probe-predictions.json",
                "git_head": subprocess.run(  # noqa: S603
                    ["/usr/bin/env", "git", "rev-parse", "HEAD"],  # noqa: S607
                    capture_output=True,
                    text=True,
                    check=False,
                ).stdout.strip(),
                "n_time": N_TIME,
                "series_per_family": SERIES_PER_FAMILY,
                "seed": SEED,
                "base": list(fields.BASE),
                "candidates": list(fields.CANDIDATES),
                "signal_terms_the_config_fits": list(fields.SIGNAL_TERMS),
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
            for name, offset, trend in SIGNALS:
                measure(handle, name, offset, trend)


if __name__ == "__main__":
    main()
