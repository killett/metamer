"""2c Task 1 -- the stride curve: s(k) at k in {2, 4, 8} on one point set.

**WHY THIS EXISTS.** The coarse stride sits inside `fit_hash` (Q9), so it is the
one warm-start parameter that cannot be revised later without fragmenting every
store built before the revision. Section 11.2 gave only a floor -- *"favourable
for k >= 4"* -- and Task 0 measured `s(4) = 42.28%` and nothing else, so the
curve is one point and the shipped value would otherwise be an **asserted
fit-identity field.**

**THE FIXTURE IS TASK 0's, BY IMPORT RATHER THAN BY COPY.** `build_field`,
`candidate_set` and `spiral_source` come from `warmstart-spike-harness.py`, so
the field, the candidates and section 11.3's nearest-valid rule are **the same
objects**, not a reimplementation that could drift. Task 0's pass 1 at `k = 4`
is reproducible from it bit-identically, which was checked.

**THE STRIDES NEST, AND THAT IS WHAT MAKES THIS CHEAP.** `k = 8`'s coarse set is
a subset of `k = 4`'s, which is a subset of `k = 2`'s. So one pass 1 over the
`k = 2` coarse set (36 points) supplies **every source all three strides need**.
(j4): an existing measurement used as evidence, applied to a fixture.

**AND THE THREE STRIDES ARE READ ON ONE POINT SET.** Each stride has its own
pass-2 set -- 108, 135 and 140 of 144 -- so a saving computed on each stride's
own set would be three savings over three populations, which is exactly the
comparability failure promoted as **(j5)**. `s(k)` is measured on the **common
fine set**: the 108 points that are pass-2 under all three strides, against one
cold reference over those same 108. The `1/k^2` arithmetic that turns `s(k)` into
a run cost is **computed afterwards and never mixed into the measurement.**

**THE OBJECTIVE IS IN TIME AND IS WRITTEN DOWN BEFORE THE NUMBERS EXIST**, in
[`warmstart-stride-predictions.json`](warmstart-stride-predictions.json):

    relative_cost(k) = (1/k^2) + (1 - 1/k^2) * (T_warm(k) / T_cold)

Both rates are measured per-series wall clock **over the same 108 points**, so
the ratio carries no population difference. A series-unit objective would
undervalue large `k`, because Task 0 measured cold at **45.90% slower** than warm
and a series count treats pass 1's expensive work as fungible with pass 2's cheap
work.

Usage:
    warmstart-stride-harness.py <out.jsonl> [n_side] [n_time] [strides]

`<strides>` is comma-separated and must be nested, largest last, e.g. "2,4,8".
"""

from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path
from typing import Any, TextIO

import numpy as np
from threadpoolctl import threadpool_limits

from metamer.core.criteria import Criterion
from metamer.core.fit import FitResult, fit
from metamer.core.signal import Constant, SignalSpec, Trend

_SPIKE = Path(__file__).with_name("warmstart-spike-harness.py")
_spec = importlib.util.spec_from_file_location("warmstart_spike", _SPIKE)
if _spec is None or _spec.loader is None:  # pragma: no cover -- path is fixed
    raise ImportError(f"cannot load Task 0's fixture from {_SPIKE}")
spike = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(spike)


def emit(handle: TextIO, record: dict[str, Any]) -> None:
    """Write one JSONL record and flush, so a killed run keeps what it had."""
    handle.write(json.dumps(record) + "\n")
    handle.flush()


def timing_row(result: FitResult, arm: str, seconds: float, n: int) -> dict[str, Any]:
    """Wall clock, per-series rate, and the determinism fingerprint for one arm."""
    return {
        "kind": "timing",
        "arm": arm,
        "seconds": seconds,
        "per_series_s": seconds / n,
        "n_points": n,
        "n_iter_total": int(result.n_iter.sum()),
        "loglik_fingerprint": float(np.nansum(result.loglik)),
    }


def point_rows(
    result: FitResult,
    arm: str,
    flats: list[int],
    truth: list[dict[str, Any]],
    n_cand: int,
    source_regime: dict[tuple[int, int], str] | None,
) -> list[dict[str, Any]]:
    """One row per (point, candidate), carrying everything the analyser needs."""
    rows = []
    for b, flat in enumerate(flats):
        spec = truth[flat]
        for c in range(n_cand):
            src = None if source_regime is None else source_regime.get((flat, c))
            rows.append(
                {
                    "kind": "point",
                    "arm": arm,
                    "flat": flat,
                    "row": spec["row"],
                    "col": spec["col"],
                    "regime": spec["regime"],
                    "cand": c,
                    "n_iter": int(result.n_iter[b, c]),
                    "outcome": int(result.outcome[b, c]),
                    "loglik": float(result.loglik[b, c]),
                    "theta": [float(v) for v in result.theta[b, c]],
                    "theta_err": [float(v) for v in result.theta_err[b, c]],
                    "best_index": int(result.ranking.best_index[b]),
                    "source_regime": src,
                    "cross_regime": None if src is None else src != spec["regime"],
                }
            )
    return rows


def main() -> None:  # noqa: PLR0915
    """Run the cold reference once and one warm arm per stride, on one point set."""
    out_path = sys.argv[1]
    n_side = int(sys.argv[2]) if len(sys.argv) > 2 else 12
    n_time = int(sys.argv[3]) if len(sys.argv) > 3 else 630
    strides = [
        int(s) for s in (sys.argv[4] if len(sys.argv) > 4 else "2,4,8").split(",")
    ]

    y, t, truth = spike.build_field(n_side, n_time)
    signal = SignalSpec([Constant(), Trend()])
    cands = spike.candidate_set()
    n_cand = len(cands)

    coarse_sets = {k: spike.coarse_indices(n_side, k) for k in strides}
    flat_sets = {k: {r * n_side + c for r, c in coarse_sets[k]} for k in strides}

    # The nesting is the premise the cheapness rests on, so it is ASSERTED rather
    # than assumed: a non-nested stride list would silently make the common fine
    # set wrong and every saving incomparable.
    finest = min(strides)
    for k in strides:
        if not flat_sets[k] <= flat_sets[finest]:
            raise ValueError(f"stride {k} is not nested inside stride {finest}")

    # The common fine set: pass-2 under every stride. One population, one cold
    # reference -- (j5).
    common = sorted(set(range(n_side * n_side)) - flat_sets[finest])
    union_coarse = sorted(flat_sets[finest])

    handle = open(out_path, "w")
    emit(
        handle,
        {
            "kind": "config",
            "n_side": n_side,
            "n_time": n_time,
            "strides": strides,
            "n_common_fine": len(common),
            "n_union_coarse": len(union_coarse),
            "coarse_counts": {str(k): len(coarse_sets[k]) for k in strides},
            "candidates": [str(c.spec_hash()) for c in cands],
        },
    )

    with threadpool_limits(limits=1):
        # ---- One pass 1 over the finest coarse set supplies every stride.
        start = time.perf_counter()
        pass1 = fit(y[union_coarse], t, signal, cands, criterion=Criterion.AIC)
        emit(
            handle,
            timing_row(
                pass1, "pass1_union", time.perf_counter() - start, len(union_coarse)
            ),
        )
        p_max = pass1.theta_unconstrained.shape[2]
        ok_union = pass1.outcome == 0
        pos = {flat: i for i, flat in enumerate(union_coarse)}
        emit(
            handle,
            {
                "kind": "coarse_health",
                "ok_fraction": float(ok_union.mean()),
                "per_candidate_ok": [float(x) for x in ok_union.mean(axis=0)],
            },
        )

        # ---- The cold reference, over the common fine set, once.
        start = time.perf_counter()
        cold = fit(y[common], t, signal, cands, criterion=Criterion.AIC)
        cold_seconds = time.perf_counter() - start
        emit(handle, timing_row(cold, "cold", cold_seconds, len(common)))
        for row in point_rows(cold, "cold", common, truth, n_cand, None):
            emit(handle, row)

        # ---- One warm arm per stride, same 108 points, sources from that
        # stride's own coarse set -- which is a subset of the union already fit.
        for k in strides:
            coarse_k = coarse_sets[k]
            ok_k = np.array(
                [
                    [ok_union[pos[r * n_side + c], j] for j in range(n_cand)]
                    for r, c in coarse_k
                ]
            )
            x0 = np.full((len(common), n_cand, p_max), np.nan)
            src_regime: dict[tuple[int, int], str] = {}
            radii: list[int] = []
            n_invalid = 0
            for b, flat in enumerate(common):
                target = (flat // n_side, flat % n_side)
                for c in range(n_cand):
                    idx, radius = spike.spiral_source(target, coarse_k, ok_k, c, n_side)
                    if idx is None:
                        n_invalid += 1
                        continue
                    src_flat = coarse_k[idx][0] * n_side + coarse_k[idx][1]
                    x0[b, c, :] = pass1.theta_unconstrained[pos[src_flat], c, :]
                    src_regime[(flat, c)] = truth[src_flat]["regime"]
                    radii.append(int(radius))
            emit(
                handle,
                {
                    "kind": "source_map",
                    "stride": k,
                    "n_invalid_cells": n_invalid,
                    "mean_radius": float(np.mean(radii)) if radii else float("nan"),
                    "max_radius": int(np.max(radii)) if radii else -1,
                },
            )
            if n_invalid:
                emit(handle, {"kind": "abort", "stride": k, "reason": "invalid cells"})
                continue

            start = time.perf_counter()
            warm = fit(y[common], t, signal, cands, criterion=Criterion.AIC, x0=x0)
            seconds = time.perf_counter() - start
            row = timing_row(warm, f"warm_k{k}", seconds, len(common))
            row["stride"] = k
            emit(handle, row)
            for r in point_rows(warm, f"warm_k{k}", common, truth, n_cand, src_regime):
                emit(handle, r)

    handle.close()


if __name__ == "__main__":
    main()
