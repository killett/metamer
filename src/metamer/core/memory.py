"""Analytic bytes-per-series, one formula per backend (design doc section 9.4).

    Path A:  B * ( N*9 + X_term + out(M, p, k_beta) + c_A(d, k_beta, p) )
    Path B:  B * ( N*9 + X_term + out(M, p, k_beta) )  +  T * c_B(d, k_beta, p)

**The shapes genuinely differ, and that is not a detail.** Path A's solver
state is per series; path B's is per thread. One formula with different
constants would hide the fact that path B's tile cost depends on the thread
count and path A's does not.

**Peak RAM is independent of core count**, which is what makes a 16 GB machine
and a 64-core machine both runnable: parallelism is *within* a tile and *over*
series, never across tiles. The only thread term anywhere is path B's
`T * c_B`, at ~1.5 kB per thread -- ~96 kB at T=64, against megabytes of tile.

Terms, and why each is where it is:

- `N*9` -- the data tile: 8 bytes of float64 `y` plus a 1-byte mask. Data
  arrives float32 from disk and `core` is float64; the conversion happens **per
  dask chunk during tile assembly**, so the full float32 and full float64
  representations never coexist and the ~44% swing on the dominant term
  disappears.
- `X_term` -- zero when every regressor is shared (one copy, negligible), and
  `N * k_beta * 8` when **any** regressor is a per-point field. At N=630,
  k_beta=4 that is 20.2 kB/series, roughly 2.4x everything else combined. It is
  not a rounding error: it moves `tile_side` by about a factor of two.
- `out(...)` -- output slots, held until the tile is written, and they **do not
  shrink under path B**. The scalar count is **4** (`log_lik`, `k`,
  `n_eff_trend`, `n_eff_bic`), not 2: both `n_eff` variants are per candidate,
  each being a function of the fitted model (section 10.1).

Data plus output slots are 88% of path A's total, so path B saves 12.2% -- and
3.7% once per-point regressors are present. **The reason to prefer path B is
speed and the collapse of the ragged cliff, not memory.**
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
from enum import StrEnum


class Backend(StrEnum):
    """Which execution strategy the formula describes."""

    NUMPY_BATCHED = "numpy_batched"
    COMPILED = "compiled"


def output_slot_bytes(n_models: int, p: int, k_beta: int) -> int:
    """Per-series output slots, held for every candidate until the tile writes.

    Per candidate: `theta_hat` and `theta_hat_err` (`p` each), `beta` and
    `beta_err` (`k_beta` each), then `log_lik`, `k`, `n_eff_trend` and
    `n_eff_bic` as float64, plus `iterations` (uint16) and `status` (uint8).

    **Four scalars, not two.** Both `n_eff` variants are per `(point,
    candidate)` because both are functions of the fitted model -- `n_eff_bic`
    through the model ACF, `n_eff_trend` through the fitted Sigma (section
    10.1). The count was 2 while they were believed per-point, and the
    superseded value survives in older drafts of the section 9.4 table.

    Args:
        n_models: Candidate count held until the tile is written.
        p: Number of free noise parameters.
        k_beta: Number of design columns.

    Returns:
        Bytes of output slots per series.
    """
    return n_models * (2 * p + 2 * k_beta + 4) * 8 + n_models * 3


def _solver_state(backend: Backend, d: int, k_beta: int, p: int) -> int:
    """Solver working set: per series on path A, per thread on path B.

    The optimizer term is the only part that differs. Section 8.3 specifies a
    batched **trust-region** for path A precisely because line search breaks
    batch utilization, and a trust-region with a dense quasi-Newton model
    stores `p^2` plus a few `p`-vectors -- **not** the 22`p` of an L-BFGS
    history. L-BFGS appears only on path B, where it is per thread.

    Args:
        backend: Which execution strategy.
        d: Composite state dimension.
        k_beta: Number of design columns.
        p: Number of free noise parameters.

    Returns:
        Bytes of solver state.
    """
    d2 = 6 * d * d * 8  # P, F, Q, P_inf and two workspace copies
    x_aug = d * (1 + k_beta) * 8  # state augmented over [y | X]
    accum = (k_beta * (k_beta + 1) // 2 + k_beta + 1) * 8
    hessian = p * p * 8  # at the optimum, transient
    if backend is Backend.COMPILED:
        optimizer = 22 * p * 8  # L-BFGS history, m ~= 10
    else:
        optimizer = (p * p + 4 * p) * 8  # dense quasi-Newton trust-region model
    return d2 + x_aug + accum + optimizer + hessian


def bytes_per_series(
    backend: Backend,
    d: int,
    k_beta: int,
    p: int,
    n_time: int,
    n_models: int,
    per_point_design: bool = False,
) -> int:
    """Analytic per-series memory cost.

    Path B's solver state is deliberately absent: it is per thread, and
    `tile_bytes` adds it once per thread rather than once per series.

    Args:
        backend: Which execution strategy.
        d: Composite state dimension.
        k_beta: Number of design columns.
        p: Number of free noise parameters.
        n_time: Series length.
        n_models: Candidate count held until the tile is written.
        per_point_design: True if any regressor is a per-point field, which
            makes X per series rather than one shared copy.

    Returns:
        Bytes per series.
    """
    data = n_time * 9
    x_term = n_time * k_beta * 8 if per_point_design else 0
    total = data + x_term + output_slot_bytes(n_models, p, k_beta)
    if backend is Backend.NUMPY_BATCHED:
        total += _solver_state(backend, d, k_beta, p)
    return int(total)


def thread_state_bytes(d: int, k_beta: int, p: int) -> int:
    """Per-thread solver state for the compiled backend.

    Args:
        d: Composite state dimension.
        k_beta: Number of design columns.
        p: Number of free noise parameters.

    Returns:
        Bytes per thread.
    """
    return int(_solver_state(Backend.COMPILED, d, k_beta, p))


def tile_bytes(
    backend: Backend,
    batch: int,
    threads: int,
    d: int,
    k_beta: int,
    p: int,
    n_time: int,
    n_models: int,
    per_point_design: bool = False,
) -> int:
    """Total bytes for one tile, composing the backend's shape.

    Path A has no thread term at all, so its tile cost is independent of core
    count. Path B adds its solver state once per thread. **This is the whole
    structural difference between the two formulas**, and it is why a single
    formula with different constants would be wrong rather than merely
    imprecise.

    Args:
        backend: Which execution strategy.
        batch: Series in the tile.
        threads: Worker threads. Ignored on path A, by construction.
        d: Composite state dimension.
        k_beta: Number of design columns.
        p: Number of free noise parameters.
        n_time: Series length.
        n_models: Candidate count held until the tile is written.
        per_point_design: True if any regressor is a per-point field.

    Returns:
        Total bytes for the tile.
    """
    per_series = bytes_per_series(
        backend, d, k_beta, p, n_time, n_models, per_point_design
    )
    total = batch * per_series
    if backend is Backend.COMPILED:
        total += threads * thread_state_bytes(d, k_beta, p)
    return int(total)


def tile_side(budget_bytes: int, per_series_bytes: int) -> int:
    """Square spatial tile side from a byte budget and the full accounting.

    Floors rather than rounds: rounding up overcommits a hard memory budget by
    a full tile row, and the 16 GB constraint is hard.

    Args:
        budget_bytes: Memory budget for one tile.
        per_series_bytes: From `bytes_per_series`.

    Returns:
        Tile side in grid points.

    Raises:
        ValueError: If the budget does not hold at least one series. A side of
            0 is a plausible-looking number that holds no data, so the caller
            would loop making no progress rather than see the problem.
    """
    side = int(math.floor(math.sqrt(budget_bytes / per_series_bytes)))
    if side < 1:
        raise ValueError(
            f"budget of {budget_bytes} B does not hold one series at "
            f"{per_series_bytes} B/series"
        )
    return side


def streaming_overhead_bytes(backend: Backend, k_beta: int) -> int:
    """What the streaming filter costs per series beyond section 9.4's model.

    **THIS REPLACED `augmented_block_bytes`, AND THE REPLACEMENT IS THE WHOLE
    POINT OF THE 2026-08-10 ENGINE CHANGE.** Until then `KalmanEngine._augment`
    ended in `np.concatenate([y[:, :, None], x], axis=2)`, materializing a
    `(B, N, 1+k_beta)` float64 array -- **25 200 B/series at N=630, k_beta=4**,
    roughly three times section 9.4's entire per-series total, and it did not
    vanish when the design was shared, which is exactly the case the section's
    `X_term` calls free. Both engines now index the observation and the design
    columns per timestep, so section 9.4's model is true of the code rather
    than aspirational.

    What is left is genuinely per series and genuinely small:

    - **Path A** reuses one `(B, 1+k_beta)` float64 row across all `N` steps:
      `(1 + k_beta) * 8` bytes per series, **40 B at k_beta=4**, against
      25 200 before. It is `N` times smaller because the row is the thing the
      accumulator ever needed.
    - **Path B** carries `block_row`, a `(B,)` `intp` map from series to design
      row, so the compiled kernel can read a shared design without a per-series
      copy and without a branch on a boolean argument inside `prange`:
      **8 B/series**.

    Kept as a named term rather than folded into `bytes_per_series` because
    the seam is the standing check -- *does the memory formula describe the
    code, or a model of the code?* -- and section 9.4 remains the model. The
    next divergence needs somewhere to live.

    Args:
        backend: Which execution strategy.
        k_beta: Number of design columns.

    Returns:
        Bytes per series beyond section 9.4's accounting.
    """
    if backend is Backend.COMPILED:
        return 8
    return int((1 + k_beta) * 8)


def resident_bytes_per_series(
    backend: Backend,
    d: int,
    k_beta: int,
    p: int,
    n_time: int,
    n_models: int,
    per_point_design: bool = False,
) -> int:
    """What a series actually costs, against `bytes_per_series`'s model.

    `bytes_per_series` is design doc section 9.4's formula: the memory a
    streaming implementation uses, and the number to aim at. This adds
    `streaming_overhead_bytes`, everything the real engines hold that the
    section does not name, and is the number to **budget** against.

    **The two now agree to 0.5%.** At the section 9.4 worked example the gap is
    40 B/series -- 8682 B model against 8722 B resident on path A -- and
    `tile_side` at a 1 GB budget is 338 against the model's 339. Until
    2026-08-10 the gap was 25 200 B/series, 8682 against 33 882, a factor of
    3.9, and `tile_side` was **171**. Every Phase 1 tile figure quoting 171
    predates the streaming engines.

    **Still budget against this one, not against the model.** The gap being
    small today is a measurement, not a guarantee, and the seam is what makes
    the next divergence visible instead of silent.

    Args:
        backend: Which execution strategy.
        d: Composite state dimension.
        k_beta: Number of design columns.
        p: Number of free noise parameters.
        n_time: Series length.
        n_models: Candidate count held until the tile is written.
        per_point_design: True if any regressor is a per-point field.

    Returns:
        Bytes per series actually held resident.
    """
    return bytes_per_series(
        backend, d, k_beta, p, n_time, n_models, per_point_design
    ) + streaming_overhead_bytes(backend, k_beta)


def data_and_workspace_bytes_per_series(d: int, k_beta: int, n_time: int) -> int:
    """The subset of the formula one batched likelihood evaluation allocates.

    The data tile plus the engine's per-series working set -- `P`, `F`, `Q`,
    `P_inf` and two workspace copies, the augmented state, the normal-equation
    accumulators, and the one reused `[y | X]` row. It excludes the optimizer
    state, the Hessian and the output slots, none of which a single evaluation
    touches.

    **This was 31 542 B/series until 2026-08-10 and is now 6382**, because
    25 200 of it was the materialized augmented block. Measured against it,
    the slope of resident RSS on batch size went from 43 392 B/series to
    **8471** -- a ratio to the floor of 1.33, inside the ~1.5x the standing
    check allows before a term counts as missing rather than as transients.

    This exists because it is what `measure_evaluation_rss_slope` can actually
    measure. **A full `fit` at tile scale is not runnable**: measured on this
    machine, `fit` costs ~5.4 s per series through the per-series scipy loop,
    so the 10 000-series batch the plan's fence proposed would take ~15 hours.
    Validating the measurable 76% is worth more than not validating anything.

    Args:
        d: Composite state dimension.
        k_beta: Number of design columns.
        n_time: Series length.

    Returns:
        Bytes per series for the data tile plus engine workspace.
    """
    data = n_time * 9
    d2 = 6 * d * d * 8
    x_aug = d * (1 + k_beta) * 8
    accum = (k_beta * (k_beta + 1) // 2 + k_beta + 1) * 8
    return int(
        data
        + d2
        + x_aug
        + accum
        + streaming_overhead_bytes(Backend.NUMPY_BATCHED, k_beta)
    )


_CHILD = """
import json, threading, time
import numpy as np
from metamer.core.capability import Objective
from metamer.core.engines.kalman import KalmanEngine
from metamer.core.machine import current_rss_bytes, peak_rss_bytes
from metamer.core.objective import ConcentratedObjective
from metamer.core.registry import kernel_registry
from metamer.core.signal import Annual, Constant, SemiAnnual, SignalSpec, Trend
from metamer.core.statespace import StateSpace
from metamer.core.terms import ProcessSpec, TermSpec, free_param_index

batch, n_time = {batch}, {n_time}


def _term(kind):
    family = kernel_registry[kind]()
    return TermSpec(kind, family.param_specs(), getattr(family, "ordering_param", None))


# Sample RESIDENT size during the evaluation and keep the maximum. Reading it
# once at the end misses the peak entirely -- the engine's working set is local
# to `score` and is freed the moment it returns -- and reading `ru_maxrss`
# instead reports whatever high-water mark this process inherited from its
# parent across fork/exec.
high = [current_rss_bytes()]
stop = threading.Event()


def _sample():
    while not stop.is_set():
        high[0] = max(high[0], current_rss_bytes())
        time.sleep(0.002)


spec = ProcessSpec((_term("white"), _term("matern12"), _term("matern32")))
signal = SignalSpec([Constant(), Trend(), Annual(), SemiAnnual()])
objective = ConcentratedObjective(
    spec, StateSpace.from_spec(spec), KalmanEngine(), Objective.ML
)
# Decimal years -- 630 monthly samples is 52.5 yr, and Annual/SemiAnnual
# already default to 1.0 and 0.5 in those units.
t = np.arange(n_time, dtype=np.float64) / 12.0
baseline = current_rss_bytes()
sampler = threading.Thread(target=_sample, daemon=True)
sampler.start()
if batch:
    y = np.random.default_rng(0).standard_normal((batch, n_time))
    mask = np.ones_like(y, dtype=bool)
    design = signal.design_info(t, mask)
    u = np.zeros((batch, len(free_param_index(spec))))
    objective.unconstrained_loglik(u, y, mask, t, design)
    high[0] = max(high[0], current_rss_bytes())
stop.set()
sampler.join()
print(json.dumps({{"baseline": baseline, "peak": high[0],
                  "watermark": peak_rss_bytes()}}))
"""


def _measure_child(batch: int, n_time: int = 630) -> dict[str, float]:
    """Run one batched evaluation in a fresh process, returning its RSS report.

    Returns both instruments so a caller can see the contamination directly:
    `peak` is resident set size (not a watermark, not inherited) and
    `watermark` is `ru_maxrss` (a watermark, and inherited from the parent
    across fork/exec).

    Args:
        batch: Series in the tile. Zero measures the import-only baseline.
        n_time: Series length.

    Returns:
        Mapping with `baseline`, `peak` and `watermark`, all in bytes.

    Raises:
        RuntimeError: If the child fails, with its stderr attached -- a silent
            zero here would look like a perfectly flat memory curve, which is
            indistinguishable from a formula that predicts nothing.
    """
    code = _CHILD.format(batch=batch, n_time=n_time)
    # S603: the argv is this module's own template with two integers
    # substituted in, run under this interpreter. No external input reaches it.
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise RuntimeError(f"peak-RSS child failed for batch={batch}: {result.stderr}")
    return {
        key: float(value)
        for key, value in json.loads(result.stdout.strip().splitlines()[-1]).items()
    }


def _measure_one(batch: int, n_time: int) -> float:
    """Run one batched evaluation in a fresh process, returning peak RSS.

    Args:
        batch: Series in the tile. Zero measures the import-only baseline.
        n_time: Series length.

    Returns:
        Peak RSS of the child process, in bytes.

    Raises:
        RuntimeError: If the child fails, with its stderr attached -- a silent
            zero here would look like a perfectly flat memory curve, which is
            indistinguishable from a formula that predicts nothing.
    """
    return _measure_child(batch, n_time)["peak"]


def measure_evaluation_rss_slope(
    batches: tuple[int, ...], n_time: int
) -> tuple[float, float]:
    """Measure bytes-per-series as the slope of peak RSS against batch size.

    **The formula's claim is about the gradient, not the absolute peak.** A
    process carries a large per-run constant -- interpreter, numpy, imports --
    that is real and is not per-series. Fitting a line separates the two and
    compares the formula against the quantity it actually asserts.

    Each batch runs in a **fresh subprocess**, because `ru_maxrss` is a
    high-water mark that never decreases: two readings in one process are not
    comparable unless the later allocation exceeds every earlier one. That is
    pre-flight (k) -- a quantity whose meaning depends on process-local state.

    Args:
        batches: Batch sizes to measure, at least two and ideally three.
        n_time: Series length.

    Returns:
        `(slope_bytes_per_series, intercept_bytes)`.

    Raises:
        ValueError: If fewer than two batch sizes are given, since a slope
            needs two points.
    """
    if len(batches) < 2:
        raise ValueError(f"need at least two batch sizes to fit a slope, got {batches}")
    import numpy as np

    sizes = np.asarray(batches, dtype=np.float64)
    peaks = np.asarray(
        [_measure_one(int(b), n_time) for b in batches], dtype=np.float64
    )
    slope, intercept = np.polyfit(sizes, peaks, 1)
    return float(slope), float(intercept)
