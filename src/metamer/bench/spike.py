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
from collections.abc import Sequence
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


MATERN32_RHO_MULTIPLE = 6.0
"""Separation between the two timescales in the d=3 iteration sample.

Both terms have a free timescale, so a row that puts them close together is
weakly identified whichever kernel drew it -- design doc section 4.8, and the
static half of it is `core.lint`'s overlap rule. Six sampling-interval
multiples apart keeps every row well clear of that ridge while leaving the
longer scale far inside the record: the largest is `13.5 * 6 = 81` intervals,
6.75 years against a 52.5-year record.
"""

ITERATION_ROWS: dict[int, tuple[tuple[float, float], ...]] = {
    1: ((4.0, 0.30), (8.0, 0.40), (16.0, 0.55), (32.0, 0.75)),
    3: ((4.0, 0.30), (6.0, 0.40), (9.0, 0.55), (13.5, 0.75)),
}
"""Per-row generating parameters for the iteration sample, as
`(matern12 rho in sampling intervals, white sigma)`.

**One row is one parameter set, not one amplitude.** See
`measure_mean_iterations` for the measurement that forced that: the
log-likelihood is scale-equivariant, so amplitude spread alone reports
utilization of exactly 1.0.

Every state amplitude is 1.0, so the pairs above are signal-to-noise ratios of
3.3 down to 1.3 -- a spread wide enough to move the iteration count and narrow
enough that every row stays identified. Measured margins at d=3 are
`cond(H) = 5.3e2, 3.8e2, 6.0e3, 1.6e4` against `HESSIAN_COND_LIMIT = 6.71e7`,
the tightest a factor of 4188.
"""


def _process_covariance(
    state_space: StateSpace,
    theta: NDArray[np.float64],
    t: NDArray[np.float64],
) -> NDArray[np.float64]:
    """Sigma for one parameter set: the state terms' ACVF plus measurement noise.

    Only families with `state_dim > 0` contribute to the lag part. White noise
    lives in R and never in a state block, so summing the composite ACVF --
    which already places sigma^2 at lag 0 -- *and* adding `R * I` would count
    the white variance twice. And the measurement noise is keyed on INDEX, not
    on the lag being zero, so two observations sharing a timestamp stay two
    independent measurements.

    Args:
        state_space: The assembled state space.
        theta: Full natural-unit parameters, shape (1, p_full).
        t: Time axis, decimal years.

    Returns:
        Shape (t.size, t.size).
    """
    lags = np.abs(t[:, None] - t[None, :])
    cov = np.zeros((t.size, t.size), dtype=np.float64)
    for family, pslice in zip(
        state_space.families, state_space.param_slices, strict=True
    ):
        if family.state_dim == 0:
            continue
        cov = cov + family.acvf(theta[:, pslice], lags.ravel())[0].reshape(lags.shape)
    nugget = np.eye(t.size) * state_space.measurement_variance(theta)[0]
    return np.asarray(cov + nugget, dtype=np.float64)


def iteration_sample(
    dim: int, t: NDArray[np.float64], seed: int = 5
) -> NDArray[np.float64]:
    """Draw the iteration sample from the candidate's OWN covariance.

    **A fixture whose data does not come from the model being fitted produces
    fits that are not representative of the workload, and every statistic
    conditioned on `OK` inherits that.** This sample was
    `rng.standard_normal(...) * logspace(-1, 1, 4)` -- white noise fitted with
    a composite carrying one or two free timescales -- until 2026-08-10. With
    no correlation structure in the data the Matern amplitudes collapse and
    the timescales sit on a flat ridge, so under the derived
    `HESSIAN_COND_LIMIT` the d=3 sample came back
    `[DEGENERATE_HESSIAN, OK, DEGENERATE_HESSIAN, OK]`. The verdicts were
    right; the sample was two series wide, and `mean_iterations` and
    `utilization` are computed over `OK` only. **This was the third instance
    of one generator defect** -- `test_fit.py`'s `_healthy_row` and
    `_plain_batch` were the first two.

    Rows differ by GENERATING PARAMETERS, not by amplitude. See
    `ITERATION_ROWS` and `measure_mean_iterations`.

    Args:
        dim: 1 or 3.
        t: Time axis, decimal years.
        seed: RNG seed, pinned so the sample is identical across processes and
            machines -- the iteration count multiplies both paths' ms/fit
            columns, so a sample that moved between runs would move the budget
            comparison with it.

    Returns:
        Shape (len(ITERATION_ROWS[dim]), t.size).

    Raises:
        KeyError: If `dim` has no row table.
    """
    from metamer.core.statespace import StateSpace

    spec = build_spec(dim)
    state_space = StateSpace.from_spec(spec)
    dt = float(t[1] - t[0])
    rng = np.random.default_rng(seed)
    rows = []
    for rho_intervals, white_sigma in ITERATION_ROWS[dim]:
        rho = rho_intervals * dt
        if dim == 1:
            theta = np.array([[1.0, rho, white_sigma]])
        else:
            theta = np.array(
                [[1.0, rho, 1.0, MATERN32_RHO_MULTIPLE * rho, white_sigma]]
            )
        cov = _process_covariance(state_space, theta, t)
        rows.append(rng.multivariate_normal(np.zeros(t.size), cov))
    return np.vstack(rows)


def measure_mean_iterations(dim: int, n_time: int) -> dict[str, float]:
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

    **AMPLITUDE SPREAD IS NOT HETEROGENEITY HERE, AND THE OLD DOCSTRING SAID
    IT WAS.** The Gaussian log-likelihood is scale-equivariant: scaling a
    series by `c` scales every sigma by `c` and leaves the surface's shape
    alone. Measured, one realization at four amplitudes gives
    `n_iter = [28, 28, 28, 28]` and utilization **exactly 1.0** -- which is
    the number this measurement exists to challenge. What the old fixture
    actually varied was the noise realization. Rows now differ by generating
    parameters; see `ITERATION_ROWS`.

    `n_ok` is reported beside the statistics because both are conditioned on
    it. A sample silently narrowing to two series is what made the previous
    figures uncomparable, and a rate without its denominator cannot show that.

    Args:
        dim: 1 or 3.
        n_time: Series length.

    Returns:
        Mapping with `mean_iterations`, `max_iterations`, `utilization`,
        `n_ok` and `n_sample`.
    """
    from metamer.core.capability import Objective
    from metamer.core.criteria import Criterion
    from metamer.core.fit import fit
    from metamer.core.outcomes import Outcome
    from metamer.core.signal import Annual, Constant, SemiAnnual, SignalSpec, Trend

    spec = build_spec(dim)
    signal = SignalSpec([Constant(), Trend(), Annual(), SemiAnnual()])
    t = np.arange(n_time, dtype=np.float64) / 12.0
    y = iteration_sample(dim, t)
    result = fit(y, t, signal, [spec], criterion=Criterion.AIC, objective=Objective.ML)
    ok = result.outcome[:, 0] == Outcome.OK.code
    iters = result.n_iter[:, 0][ok].astype(np.float64)
    if iters.size == 0:
        return {
            "mean_iterations": float("nan"),
            "max_iterations": float("nan"),
            "utilization": float("nan"),
            "n_ok": 0.0,
            "n_sample": float(y.shape[0]),
        }
    return {
        "mean_iterations": float(iters.mean()),
        "max_iterations": float(iters.max()),
        "utilization": float(iters.mean() / iters.max()),
        "n_ok": float(iters.size),
        "n_sample": float(y.shape[0]),
    }


CELL_REPEATS = 3
"""Independent re-measurements of each cell, each on freshly allocated inputs.

**THE SCATTER IS BETWEEN ALLOCATIONS, NOT WITHIN A TIMING LOOP, SO
`repeats` CANNOT SEE IT.** Measured at d=3, one thread, no gaps, B=1000 on the
mini PC:

| condition | A:B range | path A range |
|---|---|---|
| eight rounds in one process, **same arrays** | 3.34 .. 3.47 | 3.7% |
| eight rounds in one process, **fresh arrays each round** | 3.63 .. 4.08 | 7.6% |
| eight **fresh processes**, one cell each | 3.18 .. 4.00 | 18% |
| five **fresh processes**, full sweep each | 3.07 .. 3.78 | 26% |

`_time_pass` takes the best of `repeats` back-to-back passes over one
allocation, so it measures the tight first row and reports it as if it were
the last. Re-allocating also shifts the LEVEL: path A is ~16% slower on fresh
arrays than on reused ones (and path B ~4%, so path A is about four times as
sensitive). **Fresh arrays are the production condition** -- a tile is
materialized, fitted and dropped -- so the harness re-allocates per round and
reports the median with its min and max, rather than a point estimate whose
scatter has to be assumed.
"""


def run_spike(
    threads: tuple[int, ...],
    batches: tuple[int, ...] = (1000,),
    dims: tuple[int, ...] = (1, 3),
    n_time: int = 630,
    repeats: int = 3,
    gaps: tuple[str, ...] = GAP_CASES,
    cell_repeats: int = CELL_REPEATS,
    bandwidth_mib: int = 256,
) -> dict[str, object]:
    """Run the stage-1 comparison and return the JSON-ready report.

    **This is the only harness.** The batch sweep used to be a separate script
    over these same functions, and the two disagreed by 0.57 on the A:B ratio
    at one cell against a ±0.15 scatter that had been assumed rather than
    measured. `dims` and `gaps` are filters so that sweep is a flag
    combination -- `--dim 3 --gaps none` -- and "which harness" stops being a
    variable.

    Args:
        threads: Thread counts to sweep.
        batches: Batch sizes to sweep.
        dims: State dimensions to sweep.
        n_time: Series length.
        repeats: Back-to-back timing passes per round; the minimum is taken.
            This is the WITHIN-allocation repeat and it is not the one that
            matters -- see `CELL_REPEATS`.
        gaps: Gap cases to sweep, a subset of `GAP_CASES`.
        cell_repeats: Independent rounds per cell, each on fresh allocations.
        bandwidth_mib: Vector size for the STREAM reference. It must exceed L3
            by a good margin for the reference to mean anything, so the
            default stands for any published run -- but three vectors at 256
            MiB put this process's peak RSS near 1 GB, and `ru_maxrss` is
            INHERITED by every later child, so a test calling this wants a
            smaller one.

    Returns:
        The report, ready for `json.dumps`.
    """
    import numba
    from numba import get_num_threads, set_num_threads

    from metamer.bench.references import (
        as_dict,
        bandwidth_reference,
        canonical_filter_pass,
        compute_reference,
    )
    from metamer.core.signal import Annual, Constant, SemiAnnual, SignalSpec, Trend

    signal = SignalSpec([Constant(), Trend(), Annual(), SemiAnnual()])
    t = np.arange(n_time, dtype=np.float64) / 12.0
    design, k_beta = signal.design_matrix(t)

    canonical = canonical_filter_pass(n_time=n_time)
    report: dict[str, object] = {
        "machine": {
            "platform": platform.platform(),
            "processor": platform.processor() or platform.machine(),
            "python": sys.version.split()[0],
            # THE CEILING, NOT THE CURRENT MASK. `get_num_threads()` reports
            # whatever was last set in this process -- including by an earlier
            # cell of this very sweep -- so reading it here recorded "available"
            # as a number that was merely current. `NUMBA_NUM_THREADS` is fixed
            # at import and is what "available" means.
            "numba_threads_available": int(numba.config.NUMBA_NUM_THREADS),  # type: ignore[attr-defined]
        },
        "core_budget_ms": CORE_BUDGET_MS,
        "canonical_filter_pass": as_dict(canonical),
        "roofline": {"compute": as_dict(compute_reference())},
        "iterations": {},
        "cells": [],
    }

    roofline: dict[str, object] = report["roofline"]  # type: ignore[assignment]
    for count in sorted({1, *threads}):
        roofline[f"bandwidth_{count}t"] = as_dict(
            bandwidth_reference(threads=count, mib=bandwidth_mib)
        )

    iterations: dict[str, dict[str, float]] = report["iterations"]  # type: ignore[assignment]
    for dim in dims:
        iterations[f"d{dim}"] = measure_mean_iterations(dim, n_time)

    cells: list[dict[str, object]] = report["cells"]  # type: ignore[assignment]
    # RESTORED AFTER THE SWEEP. The per-cell `set_num_threads` below is correct
    # -- each cell is measured at its own thread count -- but the mask persists
    # for the whole PROCESS, so without this the sweep leaves every later caller
    # running at the last cell's count. Measured 2026-08-12: it left a pytest
    # session at 1 thread and silently disabled a test in another module.
    entry_threads = int(get_num_threads())  # type: ignore[no-untyped-call]
    try:
        cells.extend(
            _sweep_cells(
                dims=dims,
                batches=batches,
                gaps=gaps,
                threads=threads,
                iterations=iterations,
                n_time=n_time,
                t=t,
                design=design,
                k_beta=k_beta,
                repeats=repeats,
                cell_repeats=cell_repeats,
                canonical_seconds=canonical.seconds,
            )
        )
    finally:
        set_num_threads(entry_threads)  # type: ignore[no-untyped-call]
    return report


def _sweep_cells(
    *,
    dims: Sequence[int],
    batches: Sequence[int],
    gaps: Sequence[str],
    threads: Sequence[int],
    iterations: dict[str, dict[str, float]],
    n_time: int,
    t: NDArray[np.float64],
    design: NDArray[np.float64],
    k_beta: int,
    repeats: int,
    cell_repeats: int,
    canonical_seconds: float,
) -> list[dict[str, object]]:
    """Measure every (dim, batch, gap, thread) cell. Extracted from `run_spike`.

    Split out only so `run_spike` can restore the process thread mask around the
    whole sweep in one `try/finally` rather than around each cell.

    Args:
        dims: State dimensions to sweep.
        batches: Batch sizes to sweep.
        gaps: Gap patterns to sweep.
        threads: Thread counts to sweep.
        iterations: Per-dimension iteration statistics, keyed `d{dim}`.
        n_time: Series length.
        t: The time axis.
        design: The design matrix.
        k_beta: Number of design columns.
        repeats: Timing repeats within one allocation.
        cell_repeats: Independent rounds on fresh allocations.
        canonical_seconds: The canonical filter pass, for the normalized column.

    Returns:
        One entry per cell.
    """
    from numba import set_num_threads

    from metamer.core.engines.compiled import CompiledEngine
    from metamer.core.engines.kalman import KalmanEngine
    from metamer.core.memory import (
        Backend,
        bytes_per_series,
        resident_bytes_per_series,
    )
    from metamer.core.statespace import StateSpace
    from metamer.core.terms import free_param_index

    cells: list[dict[str, object]] = []
    for dim in dims:
        spec = build_spec(dim)
        state_space = StateSpace.from_spec(spec)
        p_free = len(free_param_index(spec))
        iters = iterations[f"d{dim}"]["mean_iterations"]
        for batch in batches:
            for case in gaps:
                for count in threads:
                    set_num_threads(count)  # type: ignore[no-untyped-call]
                    a_rounds: list[float] = []
                    b_rounds: list[float] = []
                    for _ in range(cell_repeats):
                        # Allocated INSIDE the round: the scatter this harness
                        # exists to report lives between allocations, and
                        # reusing one buffer across rounds hides it and
                        # flatters path A by ~16%.
                        theta = full_theta(spec, batch)
                        y = np.random.default_rng(3).standard_normal((batch, n_time))
                        mask = gap_mask(case, batch, n_time)
                        a_rounds.append(
                            _time_pass(
                                KalmanEngine(),
                                state_space,
                                theta,
                                y,
                                mask,
                                t,
                                design,
                                repeats,
                            )
                        )
                        b_rounds.append(
                            _time_pass(
                                CompiledEngine(),
                                state_space,
                                theta,
                                y,
                                mask,
                                t,
                                design,
                                repeats,
                            )
                        )
                        del theta, y, mask
                    ratios = [a / b for a, b in zip(a_rounds, b_rounds, strict=True)]
                    a_pass = float(np.median(a_rounds))
                    b_pass = float(np.median(b_rounds))
                    # The mean iteration count is common to both paths -- same
                    # optimizer, same likelihood -- so it cancels from the
                    # ratio and only converts a pass cost into a fit time.
                    a_fit_ms = a_pass * iters * 1e3
                    b_fit_ms = b_pass * iters * 1e3
                    cells.append(
                        {
                            "d": dim,
                            "batch": batch,
                            "gaps": case,
                            "threads": count,
                            "cell_repeats": cell_repeats,
                            "path_a_pass_s_per_series": a_pass,
                            "path_a_pass_s_per_series_min": min(a_rounds),
                            "path_a_pass_s_per_series_max": max(a_rounds),
                            "path_b_pass_s_per_series": b_pass,
                            "path_b_pass_s_per_series_min": min(b_rounds),
                            "path_b_pass_s_per_series_max": max(b_rounds),
                            "a_over_b": float(np.median(ratios)),
                            "a_over_b_min": min(ratios),
                            "a_over_b_max": max(ratios),
                            "path_a_bound_ms_per_fit": a_fit_ms,
                            "path_b_ms_per_fit": b_fit_ms,
                            "path_a_over_budget": a_fit_ms / CORE_BUDGET_MS,
                            "path_b_over_budget": b_fit_ms / CORE_BUDGET_MS,
                            "pass_in_canonical_units": a_pass / canonical_seconds,
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
    return cells


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
    parser.add_argument(
        "--dim",
        action="append",
        type=int,
        default=None,
        choices=(1, 3),
        help="state dimension to sweep; repeat the flag (default: both)",
    )
    parser.add_argument(
        "--gaps",
        action="append",
        default=None,
        choices=GAP_CASES,
        help="gap case to sweep; repeat the flag (default: all three). "
        "The former batch-sweep script is `--dim 3 --gaps none --threads 1`",
    )
    parser.add_argument("--n-time", type=int, default=630)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument(
        "--cell-repeats",
        type=int,
        default=CELL_REPEATS,
        help="independent rounds per cell, each on fresh allocations; the "
        "report carries the median with its min and max",
    )
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    threads = tuple(args.threads or (1,))
    batches = tuple(args.batch or (1000,))
    report = run_spike(
        threads=threads,
        batches=batches,
        dims=tuple(args.dim or (1, 3)),
        n_time=args.n_time,
        repeats=args.repeats,
        gaps=tuple(args.gaps or GAP_CASES),
        cell_repeats=args.cell_repeats,
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
