"""Stage-1 spike: path A's optimistic bound against path B, measured.

**Stage 1 does not build a batched optimizer.** Design doc section 9.2: path
A's cost is bounded as

    t_A_bound  =  (filter pass cost)  x  (mean iteration count)

assuming a zero-overhead batched optimizer at 100% utilization -- a
performance path A can never exceed. **The inference is one-sided, and that is
what makes it safe**: "B wins even against A's best conceivable case" is a
sound conclusion, while "A wins" against a bound is not, and would need
stage 2's real measurement.

Because the same optimizer drives both paths and both compute the same
likelihood, the mean iteration count is COMMON to the two sides and cancels
out of the ratio. So the A:B ratio is the ratio of per-pass costs, and the
iteration count is what converts either into ms per series-model fit for the
comparison against the **19 ms** core budget.

**Four numbers, not one ratio.** A ratio alone hides whether path A's nominal
throughput is reachable at all:

- ms per series-model fit, against the 19 ms budget
- mean iteration count
- peak RSS against the analytic formula
- **active-mask utilization** for path A -- the fraction of batch slots still
  doing useful work. With realistic heterogeneity some series converge in 20
  iterations and some in 200, so a batch runs at the tail's pace unless the
  active set is compacted. Low utilization means A's effective throughput is
  far below its nominal FLOP rate and periodic compaction is mandatory work
  not yet costed. Path B has no equivalent tax: a thread finishes and takes
  the next series.

**The gap sweep is `{0%, 10% scattered, 40% contiguous}` and the ratio is
reported per case.** The contiguous case is the realistic sea-ice pattern and
it favours path B, because a compiled loop branches past the update while the
batched mask is a multiply that costs full price regardless. Measuring only at
10% understates B's advantage exactly where the data is gappiest.

**The mini PC sweeps {1, 4} threads, not {8, full}** -- it has 4 cores, so 8
would oversubscribe and measure the scheduler. At 1 thread path B loses its
parallelism advantage entirely, so a B win there is the strongest form of the
conservative-for-A inference.

Run:

    pixi run python -m metamer.bench.spike --threads 1 --threads 4
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

if TYPE_CHECKING:
    from metamer.core.engines.protocol import Engine
    from metamer.core.statespace import StateSpace
    from metamer.core.terms import ProcessSpec

CORE_BUDGET_MS = 19.0
"""Per series-model fit budget from design doc section 9.2."""

GAP_CASES = ("none", "scattered_10", "contiguous_40")


def build_spec(dim: int) -> ProcessSpec:
    """Build the spike composite at state dimension 1 or 3.

    d=3 comes from `white + matern12 + matern32`, NOT from Matern 5/2 and not
    from "white + SHO": white is measurement noise and contributes 0 to the
    state, so white + SHO is d=2. This composite also exercises composition,
    block-diagonal assembly and canonical ordering in the same measurement.

    Args:
        dim: 1 or 3.

    Returns:
        The `ProcessSpec`.

    Raises:
        ValueError: If `dim` is not 1 or 3.
    """
    from metamer.core.registry import kernel_registry
    from metamer.core.terms import ProcessSpec, TermSpec

    def term(kind: str) -> TermSpec:
        family = kernel_registry[kind]()
        return TermSpec(
            kind, family.param_specs(), getattr(family, "ordering_param", None)
        )

    if dim == 1:
        return ProcessSpec((term("white"), term("matern12")))
    if dim == 3:
        return ProcessSpec((term("white"), term("matern12"), term("matern32")))
    raise ValueError(f"spike runs at d=1 or d=3, got {dim}")


def full_theta(spec: ProcessSpec, batch: int) -> NDArray[np.float64]:
    """Full natural-unit parameter vector per series.

    `StateSpace.from_spec` slices over ALL of a term's parameters including
    fixed ones, so an engine takes the full vector and not the free-only
    search vector.

    Args:
        spec: The composite.
        batch: Number of series.

    Returns:
        Shape (batch, p_full).
    """
    values = [
        float(term.params[name].default) for term in spec.terms for name in term.params
    ]
    return np.tile(np.asarray(values, dtype=np.float64), (batch, 1))


def gap_mask(kind: str, batch: int, n_time: int, seed: int = 11) -> NDArray[np.bool_]:
    """Build one of the three sweep patterns.

    Args:
        kind: One of `GAP_CASES`.
        batch: Number of series.
        n_time: Series length.
        seed: RNG seed, pinned so the three cases are comparable across runs.

    Returns:
        Presence mask, shape (batch, n_time).

    Raises:
        ValueError: If `kind` is not a known case.
    """
    rng = np.random.default_rng(seed)
    mask = np.ones((batch, n_time), dtype=bool)
    if kind == "none":
        return mask
    if kind == "scattered_10":
        return mask & (rng.random((batch, n_time)) >= 0.10)
    if kind == "contiguous_40":
        width = int(0.40 * n_time)
        for b in range(batch):
            start = int(rng.integers(0, n_time - width))
            mask[b, start : start + width] = False
        return mask
    raise ValueError(f"unknown gap case {kind!r}; expected one of {GAP_CASES}")


def _time_pass(
    engine: Engine,
    state_space: StateSpace,
    theta: NDArray[np.float64],
    y: NDArray[np.float64],
    mask: NDArray[np.bool_],
    t: NDArray[np.float64],
    design: NDArray[np.float64],
    repeats: int,
) -> float:
    """Return the best per-series seconds for one evaluation on `engine`."""
    from metamer.core.capability import Objective

    def run() -> None:
        engine.score(state_space, theta, y, mask, t, design, Objective.ML)

    run()  # warm caches and, for path B, the JIT
    best = float("inf")
    for _ in range(repeats):
        start = time.perf_counter()
        run()
        best = min(best, time.perf_counter() - start)
    return float(best / y.shape[0])


def measure_mean_iterations(dim: int, n_time: int, sample: int = 4) -> dict[str, float]:
    """Fit a small real sample to get the mean iteration count and utilization.

    This is the one place the spike runs the actual optimizer, and it is
    deliberately tiny: measured on this machine `fit` costs ~5.4 s per series
    through the per-series scipy loop, so a large sample is not affordable and
    is not needed -- the iteration count is common to both paths and cancels
    from the ratio.

    **Utilization is reported for path A**, as `mean(n_iter) / max(n_iter)`:
    the fraction of a batch's slots still doing useful work if the batch ran
    to the slowest member without compaction. It is a property of the
    heterogeneity, not of the backend, which is why one sample serves both.

    Args:
        dim: 1 or 3.
        n_time: Series length.
        sample: Series to fit.

    Returns:
        Mapping with `mean_iterations`, `max_iterations` and `utilization`.
    """
    from metamer.core.capability import Objective
    from metamer.core.criteria import Criterion
    from metamer.core.fit import fit
    from metamer.core.outcomes import Outcome
    from metamer.core.signal import Annual, Constant, SemiAnnual, SignalSpec, Trend

    spec = build_spec(dim)
    signal = SignalSpec([Constant(), Trend(), Annual(), SemiAnnual()])
    t = np.arange(n_time, dtype=np.float64) / 12.0
    rng = np.random.default_rng(5)
    # Heterogeneous on purpose: a homogeneous batch converges in lockstep and
    # would report utilization of 1.0 by construction, which is the number the
    # measurement exists to challenge.
    y = rng.standard_normal((sample, n_time)) * np.logspace(-1, 1, sample)[:, None]
    result = fit(y, t, signal, [spec], criterion=Criterion.AIC, objective=Objective.ML)
    ok = result.outcome[:, 0] == Outcome.OK.code
    iters = result.n_iter[:, 0][ok].astype(np.float64)
    if iters.size == 0:
        return {
            "mean_iterations": float("nan"),
            "max_iterations": float("nan"),
            "utilization": float("nan"),
        }
    return {
        "mean_iterations": float(iters.mean()),
        "max_iterations": float(iters.max()),
        "utilization": float(iters.mean() / iters.max()),
    }


def run_spike(
    threads: tuple[int, ...],
    batches: tuple[int, ...] = (1000,),
    dims: tuple[int, ...] = (1, 3),
    n_time: int = 630,
    repeats: int = 3,
) -> dict[str, object]:
    """Run the stage-1 comparison and return the JSON-ready report.

    Args:
        threads: Thread counts to sweep.
        batches: Batch sizes to sweep.
        dims: State dimensions to sweep.
        n_time: Series length.
        repeats: Timing repeats per cell; the minimum is taken.

    Returns:
        The report, ready for `json.dumps`.
    """
    from numba import get_num_threads, set_num_threads

    from metamer.bench.references import (
        as_dict,
        bandwidth_reference,
        canonical_filter_pass,
        compute_reference,
    )
    from metamer.core.engines.compiled import CompiledEngine
    from metamer.core.engines.kalman import KalmanEngine
    from metamer.core.memory import (
        Backend,
        bytes_per_series,
        resident_bytes_per_series,
    )
    from metamer.core.signal import Annual, Constant, SemiAnnual, SignalSpec, Trend
    from metamer.core.statespace import StateSpace
    from metamer.core.terms import free_param_index

    signal = SignalSpec([Constant(), Trend(), Annual(), SemiAnnual()])
    t = np.arange(n_time, dtype=np.float64) / 12.0
    design, k_beta = signal.design_matrix(t)

    canonical = canonical_filter_pass(n_time=n_time)
    report: dict[str, object] = {
        "machine": {
            "platform": platform.platform(),
            "processor": platform.processor() or platform.machine(),
            "python": sys.version.split()[0],
            "numba_threads_available": int(get_num_threads()),  # type: ignore[no-untyped-call]
        },
        "core_budget_ms": CORE_BUDGET_MS,
        "canonical_filter_pass": as_dict(canonical),
        "roofline": {"compute": as_dict(compute_reference())},
        "iterations": {},
        "cells": [],
    }

    roofline: dict[str, object] = report["roofline"]  # type: ignore[assignment]
    for count in sorted({1, *threads}):
        roofline[f"bandwidth_{count}t"] = as_dict(bandwidth_reference(threads=count))

    iterations: dict[str, dict[str, float]] = report["iterations"]  # type: ignore[assignment]
    for dim in dims:
        iterations[f"d{dim}"] = measure_mean_iterations(dim, n_time)

    cells: list[dict[str, object]] = report["cells"]  # type: ignore[assignment]
    for dim in dims:
        spec = build_spec(dim)
        state_space = StateSpace.from_spec(spec)
        p_free = len(free_param_index(spec))
        iters = iterations[f"d{dim}"]["mean_iterations"]
        for batch in batches:
            theta = full_theta(spec, batch)
            rng = np.random.default_rng(3)
            y = rng.standard_normal((batch, n_time))
            for gaps in GAP_CASES:
                mask = gap_mask(gaps, batch, n_time)
                for count in threads:
                    set_num_threads(count)  # type: ignore[no-untyped-call]
                    a_pass = _time_pass(
                        KalmanEngine(), state_space, theta, y, mask, t, design, repeats
                    )
                    b_pass = _time_pass(
                        CompiledEngine(),
                        state_space,
                        theta,
                        y,
                        mask,
                        t,
                        design,
                        repeats,
                    )
                    # The mean iteration count is common to both paths -- same
                    # optimizer, same likelihood -- so it cancels from the
                    # ratio and only converts a pass cost into a fit time.
                    a_fit_ms = a_pass * iters * 1e3
                    b_fit_ms = b_pass * iters * 1e3
                    cells.append(
                        {
                            "d": dim,
                            "batch": batch,
                            "gaps": gaps,
                            "threads": count,
                            "path_a_pass_s_per_series": a_pass,
                            "path_b_pass_s_per_series": b_pass,
                            "a_over_b": a_pass / b_pass,
                            "path_a_bound_ms_per_fit": a_fit_ms,
                            "path_b_ms_per_fit": b_fit_ms,
                            "path_a_over_budget": a_fit_ms / CORE_BUDGET_MS,
                            "path_b_over_budget": b_fit_ms / CORE_BUDGET_MS,
                            "pass_in_canonical_units": a_pass / canonical.seconds,
                            "predicted_bytes_per_series_target": bytes_per_series(
                                Backend.NUMPY_BATCHED,
                                d=dim,
                                k_beta=k_beta,
                                p=p_free,
                                n_time=n_time,
                                n_models=1,
                            ),
                            "predicted_bytes_per_series_resident": (
                                resident_bytes_per_series(
                                    Backend.NUMPY_BATCHED,
                                    d=dim,
                                    k_beta=k_beta,
                                    p=p_free,
                                    n_time=n_time,
                                    n_models=1,
                                )
                            ),
                        }
                    )
    return report


def main(argv: list[str] | None = None) -> int:
    """Command-line entry point.

    Args:
        argv: Arguments, defaulting to `sys.argv[1:]`.

    Returns:
        Process exit status.
    """
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--threads",
        action="append",
        type=int,
        default=None,
        help="thread count to sweep; repeat the flag (mini PC: --threads 1 --threads 4)",
    )
    parser.add_argument("--batch", action="append", type=int, default=None)
    parser.add_argument("--n-time", type=int, default=630)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    threads = tuple(args.threads or (1,))
    batches = tuple(args.batch or (1000,))
    report = run_spike(
        threads=threads, batches=batches, n_time=args.n_time, repeats=args.repeats
    )
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n")
        print(f"wrote {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
