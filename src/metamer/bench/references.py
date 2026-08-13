"""Three benchmark references, each answering a different question.

They are not interchangeable and none of them is "the" machine number:

1. **`canonical_filter_pass`** -- one likelihood evaluation at N=630, d=3,
   single-threaded, fixed theta, no optimizer. **Zero proxy risk, because it
   IS the workload.** This is the normalizer for the budget question, and the
   only one of the three whose units mean anything against the 19 ms
   per-series-model core budget.

2. **`compute_reference`** -- a fixed-iteration loop of `P = F P F' + Q` at
   **d=3**, single-threaded. **NOT a 6x6 LU.** The filter contains no matrix
   factorization at all: the scalar observation makes the innovation variance
   `S` a scalar, so the update is a division and a rank-1 downdate, never a
   solve. A factorization benchmark would measure a kernel this workload never
   executes, and would rank machines by an instruction mix that is not ours.
   The spike runs at d=1 and d=3, so d=6 is not the shape either.

3. **`bandwidth_reference`** -- a STREAM triad over an array sized past L3,
   measured at **1 thread AND at full thread count**, reporting
   bandwidth-per-core at full occupancy. **Single-threaded STREAM measures one
   core's outstanding-miss capacity, not the memory subsystem**: a single core
   cannot saturate a modern memory controller, so a 1-thread number flatters
   wide machines and says nothing about what happens when every core is
   pulling. The per-core figure at full occupancy is the one that predicts
   behaviour under the real workload, where every core is busy.

Together (2) and (3) are the roofline pair used to predict one machine's
result from another's; (1) is what the prediction is checked against.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Timing:
    """One timed reference.

    Attributes:
        name: Which reference this is.
        seconds: Best observed wall time for one unit of work.
        unit: What one unit is, for the reader.
        detail: Free-form extra numbers (thread count, achieved bandwidth).
    """

    name: str
    seconds: float
    unit: str
    detail: dict[str, float]


def _best_of(fn: Callable[[], object], repeats: int) -> float:
    """Return the minimum wall time over `repeats` runs.

    The minimum, not the mean: this is a throughput floor measurement and
    every source of noise on a shared machine -- scheduler preemption, another
    tenant, a page fault -- adds time and never subtracts it. The mean would
    report the machine's current load as if it were the machine.

    Args:
        fn: Zero-argument callable to time.
        repeats: How many times to run it.

    Returns:
        The smallest elapsed time in seconds.
    """
    best = float("inf")
    for _ in range(repeats):
        start = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - start)
    return best


def canonical_filter_pass(
    n_time: int = 630, batch: int = 256, repeats: int = 5
) -> Timing:
    """Time ONE likelihood evaluation per series at N=630, d=3, fixed theta.

    Zero proxy risk: this is the production filter on the production composite
    at the production length, with no optimizer around it. The reported number
    is **seconds per series per pass**, which is what multiplies by the mean
    iteration count to give a per-series-model fit time.

    Batched over `batch` series because the numpy path's per-series cost is
    only meaningful at a realistic batch -- its per-timestep Python overhead
    amortizes over B, so a B=1 measurement would report a number path A never
    experiences in production.

    Args:
        n_time: Series length.
        batch: Series in the batch.
        repeats: Timing repeats; the minimum is reported.

    Returns:
        A `Timing` in seconds per series per pass.
    """
    from metamer.bench.spike import build_spec
    from metamer.core.capability import Objective
    from metamer.core.engines.kalman import KalmanEngine
    from metamer.core.objective import ConcentratedObjective
    from metamer.core.signal import Annual, Constant, SemiAnnual, SignalSpec, Trend
    from metamer.core.statespace import StateSpace

    spec = build_spec(3)
    signal = SignalSpec([Constant(), Trend(), Annual(), SemiAnnual()])
    t = np.arange(n_time, dtype=np.float64) / 12.0
    y = np.random.default_rng(0).standard_normal((batch, n_time))
    mask = np.ones_like(y, dtype=bool)
    design = signal.design_info(t, mask)
    state_space = StateSpace.from_spec(spec)
    objective = ConcentratedObjective(spec, state_space, KalmanEngine(), Objective.ML)
    u = np.zeros((batch, objective.spec.n_theta()))

    def run() -> None:
        objective.unconstrained_loglik(u, y, mask, t, design)

    run()  # warm caches so the first pass does not pay for them
    seconds = _best_of(run, repeats) / batch
    return Timing(
        name="canonical_filter_pass",
        seconds=seconds,
        unit="s per series per likelihood evaluation",
        detail={"n_time": float(n_time), "batch": float(batch), "d": 3.0},
    )


def compute_reference(
    dim: int = 3, iterations: int = 200_000, repeats: int = 3
) -> Timing:
    """Time the filter's actual inner arithmetic: `P = F P F' + Q` at d=3.

    Deliberately **not** a 6x6 LU. The scalar observation makes `S` a scalar,
    so the filter never factorizes anything; its inner loop is two `d x d`
    products, an add, and a rank-1 downdate. Benchmarking a factorization
    would rank machines on a kernel this workload never runs.

    Args:
        dim: State dimension. 3 is the spike's composite.
        iterations: Steps in the loop.
        repeats: Timing repeats; the minimum is reported.

    Returns:
        A `Timing` in seconds per iteration, with the achieved flop rate.
    """
    from metamer.bench._kernels import propagate_covariance

    rng = np.random.default_rng(1)
    f = np.asarray(rng.standard_normal((dim, dim)) * 0.1 + np.eye(dim), order="C")
    q = np.asarray(np.eye(dim) * 0.5, order="C")
    p = np.asarray(np.eye(dim), order="C")
    h = np.asarray(rng.standard_normal(dim), order="C")

    propagate_covariance(f, q, p.copy(), h, 10)  # compile

    def run() -> None:
        propagate_covariance(f, q, p.copy(), h, iterations)

    seconds = _best_of(run, repeats) / iterations
    # 2 d^3 for F P, 2 d^3 for (FP) F', d^2 for +Q, plus the rank-1 downdate.
    flops = 4.0 * dim**3 + 2.0 * dim**2
    return Timing(
        name="compute_reference",
        seconds=seconds,
        unit="s per P = F P F' + Q step (plus rank-1 downdate)",
        detail={"d": float(dim), "gflops": flops / seconds / 1e9},
    )


def bandwidth_reference(threads: int, mib: int = 256, repeats: int = 5) -> Timing:
    """STREAM triad past L3: `a = b + scalar * c`, reporting per-core bandwidth.

    Run this at **1 thread and at full thread count**. The single-thread number
    is one core's outstanding-miss capacity and is not the memory subsystem: a
    lone core cannot saturate a modern controller, so a 1-thread figure
    flatters wide machines. The per-core figure at full occupancy is what
    predicts behaviour under the real workload, where every core is pulling at
    once.

    Args:
        threads: Threads to use.
        mib: Array size per vector, in MiB. Must exceed L3 by a good margin.
        repeats: Timing repeats; the minimum is reported.

    Returns:
        A `Timing` in seconds per triad pass, with total and per-core GB/s.
    """
    from numba import get_num_threads, set_num_threads

    from metamer.bench._kernels import stream_triad

    # RESTORED AFTERWARDS, AND THAT IS NOT TIDINESS. `set_num_threads` has no
    # context-manager form and persists for the whole PROCESS, so a benchmark
    # that sets it and walks away leaves every later measurement in that process
    # running at this thread count. Measured 2026-08-12: it left the mask at 1
    # for the rest of a pytest session, and a test whose skip guard read the
    # ambient mask became a silent no-op that passed in isolation every time.
    # This restores what it changed; it does NOT make bench route through
    # `batch.threads.thread_budget`, which is a layering question recorded in
    # PROGRESS.md.
    previous = int(get_num_threads())  # type: ignore[no-untyped-call]
    try:
        set_num_threads(threads)  # type: ignore[no-untyped-call]
        n = mib * 1024 * 1024 // 8
        b = np.ones(n, dtype=np.float64)
        c = np.full(n, 2.0, dtype=np.float64)
        a = np.zeros(n, dtype=np.float64)

        stream_triad(a[:1024], b[:1024], c[:1024], 3.0)  # compile

        def run() -> None:
            stream_triad(a, b, c, 3.0)

        seconds = _best_of(run, repeats)
    finally:
        set_num_threads(previous)  # type: ignore[no-untyped-call]
    moved = 3.0 * n * 8.0  # read b, read c, write a
    total = moved / seconds / 1e9
    return Timing(
        name="bandwidth_reference",
        seconds=seconds,
        unit="s per STREAM triad pass",
        detail={
            "threads": float(threads),
            "mib_per_vector": float(mib),
            "gb_per_s_total": total,
            "gb_per_s_per_core": total / threads,
        },
    )


def roofline_pair(threads: int) -> dict[str, Timing]:
    """Both cross-machine normalization instruments, measured together.

    Args:
        threads: Full thread count for the occupancy-limited bandwidth run.

    Returns:
        Mapping with `compute`, `bandwidth_1t` and `bandwidth_full`.
    """
    return {
        "compute": compute_reference(),
        "bandwidth_1t": bandwidth_reference(threads=1),
        "bandwidth_full": bandwidth_reference(threads=threads),
    }


def as_dict(timing: Timing) -> dict[str, object]:
    """Render a `Timing` for JSON output."""
    return {
        "name": timing.name,
        "seconds": timing.seconds,
        "unit": timing.unit,
        "detail": dict(timing.detail),
    }


__all__ = [
    "Timing",
    "as_dict",
    "bandwidth_reference",
    "canonical_filter_pass",
    "compute_reference",
    "roofline_pair",
]
