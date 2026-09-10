#!/usr/bin/env python
"""The real-data spike, second half: does PROXIMITY buy anything beyond being converged.

**READ [`realdata-spike2-preflight.md`](realdata-spike2-preflight.md) FIRST.**
This implements what that document specifies and re-argues none of it.

## The quantity

D1's amendment split 2c's 42.28% into **~30 points from starting at any converged
optimum** and **12.00 from the neighbour being near**. The coarse grid, the
barrier, the spiral and the stride inside `fit_hash` exist to buy the 12. The
first half established the 30 has more to work with on real data. **This measures
whether the 12 survives**, and the quantity is `warm - random`.

## Why all four arms share one code path

`warm - random` is a DIFFERENCE, and a difference between two code paths is not
one. Nothing shipped produces `random` or `self`, so all four arms go through
in-process `core.fit` with assembled `x0` -- 2c's construction -- while the warm
RULE is the shipped `warmstart.source_map`. The shipped two-pass driver is run
separately as a cross-check that (j5) permits: same quantity, same conditions,
different route.

## The two refusals, before any real number is produced

1. **The control** reproduces 2d's WARM arm exactly, or the two-pass path has
   moved and no warm number here is comparable to anything.
2. **The warm start reached the optimizer.** Every point warm-started with
   `x0_valid` all false is byte-identical to a cold run, so `InitRung.WARM_START`
   is counted and a shortfall refuses.

Usage:
    realdata-spike2-harness.py <out.jsonl> <fixture-dir> [smoke|full]
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, TextIO

import numpy as np
import xarray as xr
from numpy.typing import NDArray
from threadpoolctl import threadpool_limits

from metamer.batch.timeaxis import to_decimal_years
from metamer.batch.warmstart import source_map
from metamer.bench import fields, host
from metamer.config.candidates import parse_candidate
from metamer.config.model import WarmStart
from metamer.config.signal_terms import parse_signal_terms
from metamer.core.criteria import Criterion
from metamer.core.fit import FitResult, fit
from metamer.core.optimize import InitRung
from metamer.core.outcomes import Outcome

REPORT_PATH = Path(__file__).with_name("realdata-spike2-report.json")
SMOKE_REPORT_PATH = Path(__file__).with_name("realdata-spike2-smoke.json")

#: 2d's committed WARM arm, from `phase2d-difficulty-rung-report.json`. **Frozen
#: literals** -- (j8)'s third register: a record of a past value, not a spelling
#: of a current one.
CONTROL_WARM_PER_POINT = 24.463541666666668
CONTROL_WARM_OK_TOTAL = 9394

#: 2c's own threshold for "genuinely distant", in FINE index cells, unchanged.
#: The pre-flight measured this geometry's warm radius at mean 2.602 / max 4, so
#: the two arms are separated -- (i7). **Re-choosing it would change the
#: instrument that produced the 12.00 points.**
DISTANT_MIN = 6

#: 2c's seed for the distant draw, unchanged for the same reason.
DISTANT_SEED = 20260823

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


def load_box(
    store: Path,
) -> tuple[NDArray[np.float64], NDArray[np.float64], tuple[int, int]]:
    """The fine grid as `(B, N)` in row-major order, its axis, and its shape.

    **ROW-MAJOR, WHICH IS `SourceMap`'s ORDER AND `assemble_tile`'s.** A row of
    one lines up with a row of the other without a reindex, and getting this
    wrong would silently pair every point with another point's warm start.
    """
    dataset = xr.open_zarr(store, chunks=None, decode_times=True, consolidated=True)
    values = np.asarray(dataset["sla"].values, dtype=np.float64)
    n_time, n_y, n_x = values.shape
    series = values.reshape(n_time, n_y * n_x).T
    t = to_decimal_years(dataset["time"].values)
    return series, t, (n_y, n_x)


def coarse_indices(
    shape: tuple[int, int], stride: int
) -> tuple[list[int], tuple[int, int]]:
    """Flat fine-grid indices of the coarse points, and the coarse shape.

    **DERIVED FROM THE SHAPE AND THE STRIDE, WHICH IS WHAT `decimate` DOES**, so
    the coarse set here is the set pass 1 would fit rather than a second
    definition of it.
    """
    n_y, n_x = shape
    rows = list(range(0, n_y, stride))
    cols = list(range(0, n_x, stride))
    return [r * n_x + c for r in rows for c in cols], (len(rows), len(cols))


def distant_sources(
    shape: tuple[int, int],
    stride: int,
    coarse_ok: NDArray[np.bool_],
    *,
    distant_min: int,
    seed: int,
) -> tuple[NDArray[np.int64], NDArray[np.bool_], int]:
    """2c's `random` arm: a coarse point genuinely far away, per candidate.

    **2c's HARNESS FELL BACK TO THE WARM SOURCE WHERE NO POINT WAS FAR ENOUGH**,
    which makes "no distant source existed" and "the distant source behaved like
    the near one" the same reading and pulls `random` toward `warm` -- shrinking
    the headline quantity without saying so. (a0) at a control arm.

    **THIS RETURNS THE FALLBACK COUNT INSTEAD, AND THE CALLER REFUSES ON IT.**

    Args:
        shape: The fine grid `(n_y, n_x)`.
        stride: The coarse stride.
        coarse_ok: `(n_coarse_y, n_coarse_x, M)` -- whether each coarse point's
            fit is `OK` for that candidate. Per candidate, never per point.
        distant_min: Minimum Chebyshev distance in FINE cells, exclusive.
        seed: The draw's seed.

    Returns:
        `(index, valid, fallbacks)` with `index` a flat COARSE-grid index per
        `(point, candidate)` matching `SourceMap.index`'s convention, `valid`
        where a distant OK source was found, and the count of points where none
        was.
    """
    n_y, n_x = shape
    n_cy, n_cx = coarse_ok.shape[0], coarse_ok.shape[1]
    n_models = coarse_ok.shape[2]
    centres = [(a * stride, b * stride) for a in range(n_cy) for b in range(n_cx)]

    rng = np.random.default_rng(seed)
    index = np.full((n_y * n_x, n_models), -1, dtype=np.int64)
    fallbacks = 0
    flat_ok = coarse_ok.reshape(n_cy * n_cx, n_models)
    for i in range(n_y):
        for j in range(n_x):
            b = i * n_x + j
            for c in range(n_models):
                far = [
                    k
                    for k, (cr, cc) in enumerate(centres)
                    if flat_ok[k, c] and max(abs(cr - i), abs(cc - j)) > distant_min
                ]
                if far:
                    index[b, c] = int(rng.choice(far))
                else:
                    fallbacks += 1
    return index, index >= 0, fallbacks


def gather_x0(
    donor: NDArray[np.float64], index: NDArray[np.int64], valid: NDArray[np.bool_]
) -> NDArray[np.float64]:
    """Assemble `(B, M, p_max)` starts from a per-`(point, candidate)` source.

    **NaN WHERE INVALID, NEVER A DONOR ROW.** `fit` reads rows to `:p` per
    candidate and refuses a non-finite value inside a cell marked valid, so an
    invalid cell must carry nothing rather than something unused.
    """
    n_points, n_models = index.shape
    out = np.full((n_points, n_models, donor.shape[2]), np.nan)
    for b in range(n_points):
        for c in range(n_models):
            if valid[b, c]:
                out[b, c, :] = donor[index[b, c], c, :]
    return out


def selected(result: FitResult) -> NDArray[np.int64]:
    """The selected candidate per point, `-1` where nothing was selectable."""
    best = np.asarray(result.ranking.best_index, dtype=np.int64)
    return best.reshape(best.shape[0]) if best.ndim > 1 else best


def arm_reading(result: FitResult, arm: str, seconds: float) -> dict[str, Any]:
    """One arm's readings: iterations, outcomes, init rungs, conditioning."""
    n_iter = np.asarray(result.n_iter, dtype=np.int64)
    codes = np.asarray(result.outcome)
    ok = codes == Outcome.OK.code
    points = n_iter.shape[0]
    rungs = np.asarray(result.init_rung)
    rung_counts = {rung.name: int((rungs == rung.value).sum()) for rung in InitRung}
    condition = np.asarray(result.hessian_cond, dtype=np.float64)
    finite = np.isfinite(condition)
    counts = {
        Outcome.from_code(int(code)).name: int((codes == code).sum())
        for code in np.unique(codes)
    }
    return {
        "record": "arm",
        "arm": arm,
        "points": points,
        "cells": int(n_iter.size),
        "total_iterations": int(n_iter.sum()),
        "per_point": float(n_iter.sum() / points),
        "per_cell": float(n_iter.sum() / n_iter.size),
        "ok_total_iterations": int(n_iter[ok].sum()),
        "ok_per_point": float(n_iter[ok].sum() / points),
        "cells_ok": int(ok.sum()),
        "ok_fraction": float(ok.mean()),
        "outcome_counts": counts,
        "init_rungs": rung_counts,
        "cells_at_cap": int((n_iter >= 200).sum()),
        "kappa_median": float(np.median(condition[finite])) if finite.any() else None,
        "kappa_max": float(condition[finite].max()) if finite.any() else None,
        "kappa_above_limit": int((condition[finite] > 2.0**26).sum()),
        "loglik_fingerprint": float(np.nansum(np.asarray(result.loglik))),
        "seconds": seconds,
    }


def saving_on(cold: FitResult, other: FitResult, cells: NDArray[np.bool_]) -> float:
    """One arm's iteration saving against cold, over a chosen set of cells."""
    cold_total = int(np.asarray(cold.n_iter, dtype=np.int64)[cells].sum())
    other_total = int(np.asarray(other.n_iter, dtype=np.int64)[cells].sum())
    return 1.0 - other_total / cold_total if cold_total else float("nan")


def compare(cold: FitResult, other: FitResult, arm: str) -> dict[str, Any]:
    """One arm against cold: the saving, the agreement, the intersection, the flips.

    **THE AGREEMENT'S DENOMINATOR IS NAMED**, because a rate over a population
    the treatment can change is conditioned on the outcome (j7). Points enter
    when BOTH arms have at least one selectable candidate, and that count is
    reported rather than assumed.
    """
    cold_iter = np.asarray(cold.n_iter, dtype=np.int64)
    other_iter = np.asarray(other.n_iter, dtype=np.int64)
    cold_codes = np.asarray(cold.outcome)
    other_codes = np.asarray(other.outcome)
    cold_ok = cold_codes == Outcome.OK.code
    other_ok = other_codes == Outcome.OK.code

    both = cold_ok & other_ok
    gained = (~cold_ok) & other_ok
    lost = cold_ok & (~other_ok)

    cold_sel = selected(cold)
    other_sel = selected(other)
    live = (cold_sel >= 0) & (other_sel >= 0)
    agree = int((cold_sel[live] == other_sel[live]).sum())
    n_live = int(live.sum())

    cold_total = int(cold_iter.sum())
    saving = 1.0 - other_iter.sum() / cold_total if cold_total else float("nan")
    both_cold = int(cold_iter[both].sum())
    both_other = int(other_iter[both].sum())
    return {
        "record": "comparison",
        "arm": arm,
        "against": "cold",
        "saving_all_cells": float(saving),
        "saving_on_both_ok": (
            float(1.0 - both_other / both_cold) if both_cold else float("nan")
        ),
        "cold_total_iterations": cold_total,
        "arm_total_iterations": int(other_iter.sum()),
        "both_ok_cells": int(both.sum()),
        "both_ok_fraction_of_cells": float(both.mean()),
        "cells_gained_ok": int(gained.sum()),
        "cells_lost_ok": int(lost.sum()),
        "flip_asymmetry": (
            float(max(gained.sum(), lost.sum()) / max(min(gained.sum(), lost.sum()), 1))
        ),
        "selection_points_compared": n_live,
        "selection_points_agree": agree,
        "selection_agreement": float(agree / n_live) if n_live else float("nan"),
        "selection_map_arm": [int(v) for v in other_sel],
    }


def shipped_cross_check(
    directory: Path, store: Path, handle: TextIO, in_process_total: int
) -> dict[str, Any]:
    """Q7: the shipped two-pass driver against the in-process warm arm.

    **A CROSS-CHECK (j5) PERMITS: same quantity, same conditions, different
    route.** Both take the same source map at the same stride and bound and call
    the same `fit`, and `fit` loops `optimize_series` per series, so batch
    composition should not matter. **A disagreement would mean the two paths do
    not deliver the same warm start, and every warm number in this project would
    inherit the question.** Nobody has run this comparison.

    The store is renamed through the FIRST half's instrument rather than a second
    copy of it, so the two halves cannot disagree about what the rename is -- and
    the rename is a workaround for the open dimension-name defect, not a fix.
    """
    import importlib.util

    from metamer.batch.twopass import run_two_pass

    spec = importlib.util.spec_from_file_location(
        "realdata_spike_harness", Path(__file__).with_name("realdata-spike-harness.py")
    )
    if spec is None or spec.loader is None:  # pragma: no cover - path is fixed
        raise RuntimeError("cannot import the first half's harness")
    first_half = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(first_half)

    out_dir = directory / "shipped"
    out_dir.mkdir(parents=True, exist_ok=True)
    renamed = out_dir / "duacs-yx.zarr"
    emit(handle, first_half.renamed_for_tiling(store, renamed))
    config_path = out_dir / "shipped.toml"
    config_path.write_text(fields.config_text(str(renamed)))

    warm_store = out_dir / "warm.zarr"
    started = time.perf_counter()
    run_two_pass(config_path, warm_store, max_iter=None)
    seconds = time.perf_counter() - started
    everything = fields.iteration_count(warm_store)
    difference = (
        abs(everything.total - in_process_total) / in_process_total
        if in_process_total
        else float("nan")
    )
    record = {
        "record": "shipped_cross_check",
        "shipped_total_iterations": everything.total,
        "in_process_warm_total": in_process_total,
        "relative_difference": difference,
        "within_one_percent": difference <= 0.01,
        "exactly_equal": everything.total == in_process_total,
        "shipped_per_point": everything.per_point,
        "seconds": seconds,
    }
    emit(handle, record)
    return record


def run_control(directory: Path, handle: TextIO, *, smoke: bool) -> dict[str, Any]:
    """2d's easy rung through the SHIPPED two-pass driver, checked exactly."""
    from metamer.batch.twopass import run_two_pass

    out_dir = directory / ("control2-smoke" if smoke else "control2")
    out_dir.mkdir(parents=True, exist_ok=True)
    shape = {"n_time": 60, "n_normal": 4, "n_parallel": 3} if smoke else {}
    truth = fields.build_field(
        fields.rung("easy"),
        path=out_dir / "easy-field.zarr",
        seed=fields.FIELD_SEED,
        **shape,
    )
    config_path = fields.write_config(out_dir, "easy.toml", truth.uri)
    warm_store = out_dir / "easy-warm.zarr"
    started = time.perf_counter()
    run_two_pass(config_path, warm_store, max_iter=None)
    seconds = time.perf_counter() - started

    everything = fields.iteration_count(warm_store)
    ok_only = fields.iteration_count(warm_store, ok_only=True)
    record = {
        "record": "control_check",
        "path": "shipped run_two_pass",
        "warm_per_point": everything.per_point,
        "expected_warm_per_point": CONTROL_WARM_PER_POINT,
        "per_point_difference": everything.per_point - CONTROL_WARM_PER_POINT,
        "warm_ok_total": ok_only.total,
        "expected_warm_ok_total": CONTROL_WARM_OK_TOTAL,
        "ok_total_difference": ok_only.total - CONTROL_WARM_OK_TOTAL,
        "held": (
            abs(everything.per_point - CONTROL_WARM_PER_POINT) < 1e-9
            and ok_only.total == CONTROL_WARM_OK_TOTAL
        ),
        "seconds": seconds,
    }
    emit(handle, record)
    return record


def main() -> int:  # noqa: C901
    """Gate, control, then the four arms and the shipped cross-check."""
    out = Path(sys.argv[1])
    fixtures = Path(sys.argv[2])
    mode = sys.argv[3] if len(sys.argv) > 3 else "full"
    smoke = mode == "smoke"
    settings = WarmStart()

    with out.open("a", encoding="utf-8") as handle:
        emit(
            handle,
            {
                "record": "header",
                "task": "the real-data spike, second half -- proximity, the 12 points",
                "mode": mode,
                "preflight": "realdata-spike2-preflight.md",
                "predictions": "realdata-spike2-predictions.json",
                "git_head": _git_head(),
                "coarse_stride": settings.coarse_stride,
                "spiral_bound": settings.spiral_bound,
                "distant_min": DISTANT_MIN,
                "distant_seed": DISTANT_SEED,
                "candidates": list(fields.CANDIDATES),
                "signal_terms": list(fields.SIGNAL_TERMS),
                "criterion": CRITERION.name,
            },
        )

        reading = host.quiet_check()
        emit(handle, reading.as_record())
        if not reading.quiet:
            emit(handle, {"record": "refused", "reason": host.REFUSAL})
            print(host.REFUSAL, file=sys.stderr)
            return 1

        results: dict[str, Any] = {}
        with threadpool_limits(limits=1):
            control = run_control(fixtures, handle, smoke=smoke)
            if not control["held"] and not smoke:
                emit(
                    handle,
                    {
                        "record": "refused",
                        "reason": "the control did not reproduce 2d's warm arm",
                    },
                )
                print(
                    "the shipped two-pass path did not reproduce 2d's committed warm "
                    "arm; no warm number here would be comparable to anything",
                    file=sys.stderr,
                )
                return 1

            store = fixtures / "duacs-monthly.zarr"
            series, t, shape = load_box(store)
            if smoke:
                # **THE RECORD SHORTENS AND THE GRID DOES NOT.** Subsetting the
                # POINTS would break the row-major correspondence between
                # `series` and `SourceMap`, silently pairing every point with
                # another point's warm start -- the exact failure `load_box`'s
                # docstring names. Shortening `N` leaves every index alignment
                # intact and still exercises all four arms.
                series, t = series[:, :60], t[:60]
            mask = np.isfinite(series)
            signal = parse_signal_terms(list(fields.SIGNAL_TERMS))
            candidates = [parse_candidate(name) for name in fields.CANDIDATES]
            n_models = len(candidates)

            flat_coarse, coarse_shape = coarse_indices(shape, settings.coarse_stride)
            emit(
                handle,
                {
                    "record": "geometry",
                    "fine_shape": list(shape),
                    "fine_points": shape[0] * shape[1],
                    "coarse_shape": list(coarse_shape),
                    "coarse_points": len(flat_coarse),
                },
            )

            # ---- Pass 1: the coarse fits, which are the donor for warm AND random.
            started = time.perf_counter()
            coarse = fit(
                series[flat_coarse],
                t,
                signal,
                candidates,
                CRITERION,
                mask=mask[flat_coarse],
            )
            emit(
                handle,
                arm_reading(coarse, "coarse_pass1", time.perf_counter() - started),
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
            # **THE GEOMETRIC REACH, AGAINST THE REACH THE OK FILTER ACTUALLY
            # PRODUCED.** 2c called this `ok_changed` and its point is that it is
            # what makes the spiral load-bearing rather than defensive. It also
            # decides whether the `random` arm is still outside where `warm`
            # lives: a coarse cell that fails pushes its dependants' source
            # further out, and a warm source beyond `DISTANT_MIN` is not
            # separated from a distant one at all -- (i7).
            geometric = source_map(
                shape=shape,
                stride=settings.coarse_stride,
                coarse_ok=np.ones_like(coarse_ok),
                spiral_bound=settings.spiral_bound,
            )
            geometric_radius = np.asarray(geometric.radius, dtype=np.int64)
            ok_changed = np.asarray(sources.index) != np.asarray(geometric.index)

            far_index, far_valid, fallbacks = distant_sources(
                shape,
                settings.coarse_stride,
                coarse_ok,
                distant_min=DISTANT_MIN,
                seed=DISTANT_SEED,
            )
            radius = np.asarray(sources.radius, dtype=np.int64)
            emit(
                handle,
                {
                    "record": "source_maps",
                    "warm_valid_cells": int(sources.valid.sum()),
                    "warm_cells": int(sources.valid.size),
                    "warm_radius_mean": float(radius[sources.valid].mean()),
                    "warm_radius_max": int(radius[sources.valid].max()),
                    "random_valid_cells": int(far_valid.sum()),
                    "random_fallbacks": fallbacks,
                    "coarse_ok_fraction": float(coarse_ok.mean()),
                    "geometric_radius_mean": float(geometric_radius.mean()),
                    "geometric_radius_max": int(geometric_radius.max()),
                    "ok_filter_changed_source_cells": int(ok_changed.sum()),
                    "cells_warm_radius_above_distant_min": int(
                        (radius > DISTANT_MIN).sum()
                    ),
                    "why_that_last_number_matters": (
                        "a warm source beyond DISTANT_MIN is as far away as a "
                        "distant one, so warm and random are not separated on "
                        "those cells and the difference is contaminated toward "
                        "zero there -- (i7)"
                    ),
                },
            )
            if fallbacks:
                emit(
                    handle,
                    {
                        "record": "refused",
                        "reason": "the distant arm fell back to a near source",
                    },
                )
                print(
                    f"{fallbacks} cells had no source beyond {DISTANT_MIN} fine cells; "
                    "the distant arm would silently measure proximity again",
                    file=sys.stderr,
                )
                return 1

            # ---- The four arms. Cold first, because self starts from its answer.
            started = time.perf_counter()
            cold = fit(series, t, signal, candidates, CRITERION, mask=mask)
            results["cold"] = arm_reading(cold, "cold", time.perf_counter() - started)
            emit(handle, results["cold"])

            donor = np.asarray(coarse.theta_unconstrained, dtype=np.float64)
            self_valid = np.asarray(cold.outcome) == Outcome.OK.code
            arms: dict[str, tuple[NDArray[np.float64], NDArray[np.bool_]]] = {
                "warm": (
                    gather_x0(
                        donor, np.asarray(sources.index), np.asarray(sources.valid)
                    ),
                    np.asarray(sources.valid),
                ),
                "random": (gather_x0(donor, far_index, far_valid), far_valid),
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
                result = fit(
                    series,
                    t,
                    signal,
                    candidates,
                    CRITERION,
                    mask=mask,
                    x0=x0,
                    x0_valid=valid,
                )
                fitted[arm] = result
                reading_row = arm_reading(result, arm, time.perf_counter() - started)
                reading_row["x0_valid_cells"] = int(valid.sum())
                # **CONSTRAINT 1: DID THE START REACH THE OPTIMIZER?** A valid
                # source is not a used one, and the two are byte-identical in a
                # saving. `used <= valid`, with the gap being cells that fail
                # before the optimizer runs.
                used = reading_row["init_rungs"].get(InitRung.WARM_START.name, 0)
                reading_row["warm_rungs_used"] = used
                reading_row["warm_rungs_unused"] = int(valid.sum()) - used
                reading_row["start_reached_the_optimizer"] = used > 0
                emit(handle, reading_row)
                results[arm] = reading_row
                if used == 0:
                    emit(
                        handle,
                        {
                            "record": "refused",
                            "reason": f"{arm}: x0 never reached the optimizer",
                        },
                    )
                    print(
                        f"{arm}: no cell recorded InitRung.WARM_START", file=sys.stderr
                    )
                    return 1

            comparisons = {
                arm: compare(cold, fitted[arm], arm)
                for arm in ("warm", "random", "self")
            }
            for row in comparisons.values():
                emit(handle, row)

            proximity = (
                comparisons["warm"]["saving_all_cells"]
                - comparisons["random"]["saving_all_cells"]
            ) * 100.0
            # **THE STRATIFIED READING, BINNED BY A QUANTITY THE TREATMENT CANNOT
            # MOVE.** The warm radius is set by the coarse grid and by the COLD
            # coarse fits, so binning on it is not conditioning on the outcome
            # (j7). Cells whose source the OK filter pushed beyond DISTANT_MIN
            # have no separation between the two arms and are reported apart.
            separated = radius <= geometric_radius.max()
            proximity_separated = (
                saving_on(cold, fitted["warm"], separated)
                - saving_on(cold, fitted["random"], separated)
            ) * 100.0
            headline = {
                "record": "headline",
                "proximity_points_on_separated_cells": proximity_separated,
                "separated_cells": int(separated.sum()),
                "unseparated_cells": int((~separated).sum()),
                "warm_saving_points": comparisons["warm"]["saving_all_cells"] * 100.0,
                "random_saving_points": comparisons["random"]["saving_all_cells"]
                * 100.0,
                "proximity_points": proximity,
                "self_over_cold": (
                    results["self"]["total_iterations"]
                    / results["cold"]["total_iterations"]
                ),
                "warm_selection_agreement": comparisons["warm"]["selection_agreement"],
                "twoc_proximity_points": 12.00,
                "twoc_warm_agreement": 0.9037,
            }
            emit(handle, headline)

            cross = shipped_cross_check(
                fixtures, store, handle, results["warm"]["total_iterations"]
            )

            report: dict[str, Any] = {
                "record": "realdata_spike2_report",
                "shipped_cross_check": cross,
                "git_head": _git_head(),
                "quiet": reading.as_record(),
                "control": control,
                "geometry": {
                    "fine_shape": list(shape),
                    "coarse_shape": list(coarse_shape),
                    "coarse_stride": settings.coarse_stride,
                    "spiral_bound": settings.spiral_bound,
                    "distant_min": DISTANT_MIN,
                    "warm_radius_mean": float(radius[sources.valid].mean()),
                    "warm_radius_max": int(radius[sources.valid].max()),
                },
                "arms": results,
                "comparisons": comparisons,
                "headline": headline,
                "cold_selection_map": [int(v) for v in selected(cold)],
                "instrument": {
                    "all_arms": "in-process core.fit; the warm RULE is batch.warmstart.source_map",
                    "candidates": list(fields.CANDIDATES),
                    "candidate_spec_hashes": list(
                        __import__("metamer.config.model", fromlist=["x"])
                        .load(fixtures / "control2" / "easy.toml")
                        .candidate_spec_hashes()
                    )
                    if (fixtures / "control2" / "easy.toml").exists()
                    else None,
                    "criterion": CRITERION.name,
                    "signal_terms": list(fields.SIGNAL_TERMS),
                    "max_iter": 200,
                    "threads": 1,
                    "geography": (
                        "2.125 deg square of subtropical open North Atlantic: no land, "
                        "no ice, no gaps, one regime. A saving here is a saving THERE."
                    ),
                },
            }
            report["is_a_smoke_run"] = bool(smoke)
            destination: Path = SMOKE_REPORT_PATH if smoke else REPORT_PATH
            destination.write_text(json.dumps(report, indent=2, default=str) + "\n")
            emit(handle, {"record": "written", "path": str(destination)})
    return 0


if __name__ == "__main__":
    sys.exit(main())
