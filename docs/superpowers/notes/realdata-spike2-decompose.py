#!/usr/bin/env python
"""Addendum: is a changed selection the optimum MOVING or a candidate DROPPING OUT?

**THE MAIN REPORT CANNOT ANSWER THIS AND THAT IS THE DEFECT IT CRITICISED 2d
FOR.** `realdata-spike2-report.json` carries the per-point selection map for
every arm -- which is what 2d lacked -- but not the per-CELL outcome, so
*"warm selected a different candidate"* cannot be split into:

- **A MOVE.** Both arms had the same candidates available and the optimizer
  landed somewhere that ranked them differently. This is optimizer hysteresis,
  and it is what section 11.2 exists to detect.
- **A DROPOUT.** The winning candidate was `OK` in one arm and not the other, so
  it could not be selected. The selection changed **without any optimum
  moving**, and it is D9's outcome flip -- a different quantity with its own
  denominator (h2).

**BOTH ARE REAL AND ONLY ONE IS HYSTERESIS.** A verdict that reports 34%
disagreement without saying which is reporting two findings under one name.

## Why re-running is honest rather than a second measurement

Iterations are deterministic and `src/` has not moved. **So this asserts the
committed totals before it reports anything** -- if cold does not return 16658
and warm 5877, the environment has drifted and the decomposition is not about
the same run. That assertion is the control, and it is free.

**Only the three arms the decomposition needs are re-fitted.** `self` is the
agreement CEILING and is re-fitted too, because the ceiling is what says how
much of the disagreement is reachable with the exact answer as the start.

Usage:
    realdata-spike2-decompose.py <out.jsonl> <fixture-dir>
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, TextIO

import numpy as np
from numpy.typing import NDArray
from threadpoolctl import threadpool_limits

from metamer.batch.warmstart import source_map
from metamer.bench import fields, host
from metamer.config.candidates import parse_candidate
from metamer.config.model import WarmStart
from metamer.config.signal_terms import parse_signal_terms
from metamer.core.criteria import Criterion
from metamer.core.fit import FitResult, fit
from metamer.core.outcomes import Outcome

REPORT_PATH = Path(__file__).with_name("realdata-spike2-decomposition.json")

#: The committed totals this must reproduce, from `realdata-spike2-report.json`.
#: **Frozen literals** -- a record of that run, not a spelling of anything live.
EXPECTED_TOTALS = {"cold": 16658, "warm": 5877, "random": 6603, "self": 2721}

CRITERION = Criterion.AIC


def emit(handle: TextIO, record: dict[str, Any]) -> None:
    """Append one JSON record and flush."""
    handle.write(json.dumps(record, default=str) + "\n")
    handle.flush()


def _git_head() -> str:
    """The tree this ran on."""
    return subprocess.run(  # noqa: S603
        ["git", "rev-parse", "HEAD"],  # noqa: S607
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def decompose(cold: FitResult, other: FitResult, arm: str) -> dict[str, Any]:
    """Split one arm's selection disagreement into moves and dropouts.

    **THE RULE IS STATED BEFORE THE COUNTS.** A point is a DROPOUT when the
    candidate one arm selected was not `OK` in the other, so it was never
    available to be selected there. It is a MOVE when both arms had both
    selections available and ranked them differently. **A point can be both** --
    each arm's winner unavailable to the other -- and those are counted
    separately rather than assigned to whichever bin is checked first.

    Args:
        cold: The reference arm.
        other: The treated arm.
        arm: Its name.

    Returns:
        The decomposition, with every denominator named.
    """
    cold_ok = np.asarray(cold.outcome) == Outcome.OK.code
    other_ok = np.asarray(other.outcome) == Outcome.OK.code
    cold_sel = np.asarray(cold.ranking.best_index, dtype=np.int64).reshape(-1)
    other_sel = np.asarray(other.ranking.best_index, dtype=np.int64).reshape(-1)

    live = (cold_sel >= 0) & (other_sel >= 0)
    differs = live & (cold_sel != other_sel)

    points = np.flatnonzero(differs)
    move = 0
    dropout = 0
    both = 0
    for b in points:
        c_pick, o_pick = int(cold_sel[b]), int(other_sel[b])
        # Was each arm's winner AVAILABLE in the other arm?
        cold_pick_ok_in_other = bool(other_ok[b, c_pick])
        other_pick_ok_in_cold = bool(cold_ok[b, o_pick])
        if cold_pick_ok_in_other and other_pick_ok_in_cold:
            move += 1
        elif not cold_pick_ok_in_other and not other_pick_ok_in_cold:
            both += 1
        else:
            dropout += 1

    n_live = int(live.sum())
    n_differ = int(differs.sum())
    return {
        "record": "decomposition",
        "arm": arm,
        "points_compared": n_live,
        "points_agreeing": n_live - n_differ,
        "points_differing": n_differ,
        "agreement": float((n_live - n_differ) / n_live) if n_live else float("nan"),
        "differ_by_move": move,
        "differ_by_dropout": dropout,
        "differ_by_both_unavailable": both,
        "move_fraction_of_differences": float(move / n_differ)
        if n_differ
        else float("nan"),
        "move_rate_over_compared": float(move / n_live) if n_live else float("nan"),
        "dropout_rate_over_compared": (
            float((dropout + both) / n_live) if n_live else float("nan")
        ),
        "rule": (
            "a DROPOUT is a point where one arm's selected candidate was not OK "
            "in the other, so it could never have been selected there; a MOVE is "
            "a point where both selections were available in both arms"
        ),
    }


def main() -> int:
    """Re-fit the four arms, assert the committed totals, decompose."""
    out = Path(sys.argv[1])
    fixtures = Path(sys.argv[2])
    settings = WarmStart()

    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "spike2", Path(__file__).with_name("realdata-spike2-harness.py")
    )
    if spec is None or spec.loader is None:  # pragma: no cover - path is fixed
        raise RuntimeError("cannot import the second half's harness")
    main_harness = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(main_harness)

    with out.open("a", encoding="utf-8") as handle:
        emit(
            handle,
            {
                "record": "header",
                "task": "decomposition addendum -- moves against dropouts",
                "git_head": _git_head(),
                "reproduces": "realdata-spike2-report.json",
                "expected_totals": EXPECTED_TOTALS,
            },
        )
        reading = host.quiet_check()
        emit(handle, reading.as_record())
        if not reading.quiet:
            emit(handle, {"record": "refused", "reason": host.REFUSAL})
            return 1

        with threadpool_limits(limits=1):
            store = fixtures / "duacs-monthly.zarr"
            series, t, shape = main_harness.load_box(store)
            mask = np.isfinite(series)
            signal = parse_signal_terms(list(fields.SIGNAL_TERMS))
            candidates = [parse_candidate(name) for name in fields.CANDIDATES]
            n_models = len(candidates)

            flat_coarse, coarse_shape = main_harness.coarse_indices(
                shape, settings.coarse_stride
            )
            coarse = fit(
                series[flat_coarse],
                t,
                signal,
                candidates,
                CRITERION,
                mask=mask[flat_coarse],
            )
            coarse_ok = (np.asarray(coarse.outcome) == Outcome.OK.code).reshape(
                coarse_shape[0], coarse_shape[1], n_models
            )
            sources = source_map(
                shape=shape,
                stride=settings.coarse_stride,
                coarse_ok=coarse_ok,
                spiral_bound=settings.spiral_bound,
            )
            far_index, far_valid, fallbacks = main_harness.distant_sources(
                shape,
                settings.coarse_stride,
                coarse_ok,
                distant_min=main_harness.DISTANT_MIN,
                seed=main_harness.DISTANT_SEED,
            )
            if fallbacks:
                emit(handle, {"record": "refused", "reason": "distant fallback"})
                return 1

            donor = np.asarray(coarse.theta_unconstrained, dtype=np.float64)
            started = time.perf_counter()
            cold = fit(series, t, signal, candidates, CRITERION, mask=mask)
            emit(
                handle,
                {
                    "record": "arm",
                    "arm": "cold",
                    "seconds": time.perf_counter() - started,
                },
            )

            self_valid = np.asarray(cold.outcome) == Outcome.OK.code
            arms: dict[str, tuple[NDArray[np.float64], NDArray[np.bool_]]] = {
                "warm": (
                    main_harness.gather_x0(
                        donor, np.asarray(sources.index), np.asarray(sources.valid)
                    ),
                    np.asarray(sources.valid),
                ),
                "random": (
                    main_harness.gather_x0(donor, far_index, far_valid),
                    far_valid,
                ),
                "self": (
                    np.where(
                        self_valid[:, :, None],
                        np.asarray(cold.theta_unconstrained, dtype=np.float64),
                        np.nan,
                    ),
                    self_valid,
                ),
            }
            fitted: dict[str, FitResult] = {"cold": cold}
            for arm, (x0, valid) in arms.items():
                started = time.perf_counter()
                fitted[arm] = fit(
                    series,
                    t,
                    signal,
                    candidates,
                    CRITERION,
                    mask=mask,
                    x0=x0,
                    x0_valid=valid,
                )
                emit(
                    handle,
                    {
                        "record": "arm",
                        "arm": arm,
                        "seconds": time.perf_counter() - started,
                    },
                )

            # **THE CONTROL, AND IT IS FREE.** If these totals are not the
            # committed ones, this is not a decomposition of that run.
            totals = {
                name: int(np.asarray(result.n_iter, dtype=np.int64).sum())
                for name, result in fitted.items()
            }
            held = totals == EXPECTED_TOTALS
            emit(
                handle,
                {
                    "record": "reproduction_check",
                    "totals": totals,
                    "expected": EXPECTED_TOTALS,
                    "held": held,
                },
            )
            if not held:
                emit(
                    handle, {"record": "refused", "reason": "did not reproduce the run"}
                )
                print(
                    "the arms did not reproduce the committed totals", file=sys.stderr
                )
                return 1

            rows = {
                arm: decompose(cold, fitted[arm], arm)
                for arm in ("warm", "random", "self")
            }
            for row in rows.values():
                emit(handle, row)

            report = {
                "record": "realdata_spike2_decomposition",
                "git_head": _git_head(),
                "reproduction": {
                    "totals": totals,
                    "expected": EXPECTED_TOTALS,
                    "held": held,
                },
                "decomposition": rows,
                "per_cell_outcomes": {
                    name: [int(v) for v in np.asarray(result.outcome).reshape(-1)]
                    for name, result in fitted.items()
                },
                "per_point_selection": {
                    name: [
                        int(v)
                        for v in np.asarray(
                            result.ranking.best_index, dtype=np.int64
                        ).reshape(-1)
                    ]
                    for name, result in fitted.items()
                },
            }
            REPORT_PATH.write_text(json.dumps(report, indent=2, default=str) + "\n")
            emit(handle, {"record": "written", "path": str(REPORT_PATH)})
    return 0


if __name__ == "__main__":
    sys.exit(main())
