"""Path B: the same filter, compiled, with `prange` over series.

This is the *other half* of the stage-1 spike (design doc section 9.2). It
implements exactly the recursion in `kalman.KalmanEngine.score` -- scalar
observation, masked gaps, augmented `[y | X]` columns, plain (non-Joseph)
covariance update -- with the per-timestep loop compiled and the series loop
parallel.

**`[y | X]` IS NEVER MATERIALIZED HERE EITHER.** Until 2026-08-10 this engine
called `KalmanEngine._augment` and then `np.ascontiguousarray` on the result,
so path B -- the path the stage-1 gate adopted for production -- carried the
same 25 200 B/series block as path A, plus the copy. The kernel reads column 0
out of `y` and the rest out of a `(1, N, k)` or `(B, N, k)` design block, so a
shared design is stored once per tile rather than once per series.

**What is compiled and what is not.** The state-space construction stays in
numpy: `F` and `Q` are built once per *distinct* timestep, which is
`O(n_distinct * d^3)` and independent of `N`. Only the `O(N)` recursion is
compiled, because that is the whole of the hot path and the whole of path B's
advantage. Reusing `KalmanEngine._step_matrices` rather than re-deriving the
cluster index is deliberate -- that routine is documented as the ONLY
implementation of the cluster-index invariant, and a second copy is exactly
the failure this project has already paid for five times over.

**`fastmath` is off, and that is not a performance oversight.** It licenses
reassociation, which would void the bitwise-reproducibility precondition the
determinism guarantee (section 11.3) rests on, and would make the 1e-10
agreement test with `KalmanEngine` a measurement of the tolerance rather than
of the implementation.

**Where path B is expected to win on gappy data.** The compiled loop *branches
past* a masked update; the batched numpy path evaluates it and multiplies by
zero, paying full price. That is why the spike sweeps contiguous-block gaps as
well as scattered ones -- the contiguous case is the realistic sea-ice pattern
and it is where the two paths diverge most.
"""

from __future__ import annotations

import numpy as np
from numba import njit, prange
from numpy.typing import NDArray

from metamer.core.capability import EngineId, Objective
from metamer.core.engines.kalman import KalmanEngine
from metamer.core.engines.protocol import ScoredResult
from metamer.core.outcomes import Outcome, outcome_array
from metamer.core.statespace import StateSpace


@njit(cache=True, fastmath=False, parallel=True, nogil=True)
def _filter_batch(  # pragma: no cover - compiled, exercised via the engine
    y: NDArray[np.float64],
    block: NDArray[np.float64],
    block_row: NDArray[np.intp],
    mask: NDArray[np.bool_],
    index: NDArray[np.intp],
    f_all: NDArray[np.float64],
    q_all: NDArray[np.float64],
    h_all: NDArray[np.float64],
    r_all: NDArray[np.float64],
    p0_all: NDArray[np.float64],
) -> tuple[
    NDArray[np.float64], NDArray[np.float64], NDArray[np.int64], NDArray[np.bool_]
]:
    """Run the augmented scalar-observation filter, one series per thread.

    Args:
        y: Observations, shape (B, N). Read one element per timestep.
        block: Design columns, (1, N, k) shared or (B, N, k) per series, from
            `KalmanEngine._design_block`. NEVER stacked with `y`: the
            augmented `[y | X]` array this kernel used to take was
            25 200 B/series at N=630, k=4, and a shared design was replicated
            into it once per series.
        block_row: Which row of `block` each series reads, shape (B,). All
            zeros for a shared design, `arange(B)` for a per-point one. An
            index array rather than a flag because a branch on a boolean
            argument inside `prange` is what numba refuses to type here, and
            B int64 is 8 B/series against the 25 200 the block cost.
        mask: Presence mask, shape (B, N).
        index: Per-interval index into the distinct steps, length N-1.
        f_all: Transition per distinct step, shape (S, B, d, d).
        q_all: Process noise per distinct step, shape (S, B, d, d).
        h_all: Observation vector, shape (B, d).
        r_all: Measurement variance, shape (B,).
        p0_all: Stationary covariance, shape (B, d, d).

    Returns:
        `(accum, sum_log_s, n_used, degenerate)` with shapes
        (B, C, C), (B,), (B,), (B,).
    """
    batch, n_time = y.shape
    n_cols = 1 + block.shape[2]
    dim = h_all.shape[1]

    accum = np.zeros((batch, n_cols, n_cols), dtype=np.float64)
    sum_log_s = np.zeros(batch, dtype=np.float64)
    n_used = np.zeros(batch, dtype=np.int64)
    degenerate = np.zeros(batch, dtype=np.bool_)

    # mypy cannot type numba's `prange`; it is a compile-time construct that
    # numba rewrites into a parallel loop and that falls back to `range`
    # when parallelism is unavailable.
    for b in prange(batch):  # type: ignore[no-untyped-call, attr-defined]
        d = block_row[b]
        x = np.zeros((dim, n_cols), dtype=np.float64)
        p = p0_all[b].copy()
        x_new = np.zeros((dim, n_cols), dtype=np.float64)
        p_new = np.zeros((dim, dim), dtype=np.float64)
        hp = np.zeros(dim, dtype=np.float64)
        v = np.zeros(n_cols, dtype=np.float64)

        for step in range(n_time):
            if step > 0:
                f = f_all[index[step - 1], b]
                q = q_all[index[step - 1], b]
                # x <- F x
                for i in range(dim):
                    for c in range(n_cols):
                        acc = 0.0
                        for j in range(dim):
                            acc += f[i, j] * x[j, c]
                        x_new[i, c] = acc
                for i in range(dim):
                    for c in range(n_cols):
                        x[i, c] = x_new[i, c]
                # P <- F P F' + Q
                for i in range(dim):
                    for j in range(dim):
                        acc = 0.0
                        for k in range(dim):
                            acc += f[i, k] * p[k, j]
                        p_new[i, j] = acc
                for i in range(dim):
                    for j in range(dim):
                        acc = 0.0
                        for k in range(dim):
                            acc += p_new[i, k] * f[j, k]
                        p[i, j] = acc + q[i, j]

            # THE BRANCH. The batched path evaluates the update and multiplies
            # by zero; here a masked epoch costs nothing but the prediction.
            if not mask[b, step]:
                continue

            for i in range(dim):
                acc = 0.0
                for j in range(dim):
                    acc += h_all[b, j] * p[j, i]
                hp[i] = acc
            s = r_all[b]
            for i in range(dim):
                s += hp[i] * h_all[b, i]

            # A non-positive or non-finite innovation variance is a per-series
            # failure with a name, not a NaN emerging three layers later. It is
            # reachable: R = 0 drives P to exactly 0 after one update, and a
            # repeated timestamp then has F = I, Q = 0, so S = 0 exactly.
            usable = np.isfinite(s) and s > 0.0
            if not usable:
                degenerate[b] = True
            safe_s = s if usable else 1.0

            # Column 0 is the observation and columns 1.. are the design, read
            # straight out of `y` and `block` -- never out of a materialized
            # `[y | X]`. Split rather than selected inside the loop because a
            # ternary over the column index is a construct numba refuses to
            # type inside a parfor.
            acc = 0.0
            for i in range(dim):
                acc += h_all[b, i] * x[i, 0]
            v[0] = y[b, step] - acc
            for c in range(1, n_cols):
                acc = 0.0
                for i in range(dim):
                    acc += h_all[b, i] * x[i, c]
                v[c] = block[d, step, c - 1] - acc

            for i in range(dim):
                gain = hp[i] / safe_s
                for c in range(n_cols):
                    x[i, c] += gain * v[c]
            for i in range(dim):
                gain = hp[i] / safe_s
                for j in range(dim):
                    p[i, j] -= gain * hp[j]

            inv_s = 1.0 / safe_s
            for a in range(n_cols):
                for c in range(n_cols):
                    accum[b, a, c] += inv_s * v[a] * v[c]
            sum_log_s[b] += np.log(safe_s)
            n_used[b] += 1

    return accum, sum_log_s, n_used, degenerate


class CompiledEngine:
    """Path B: the compiled per-series filter.

    Shares `KalmanEngine`'s design validation and post-processing --
    `_design_block`, `_step_matrices` and `_rank` -- so the only thing that differs
    between the two engines is the recursion itself. That is what makes the
    agreement test meaningful: it compares two implementations of the loop, not
    two implementations of the whole pipeline.
    """

    engine_id = EngineId.KALMAN
    """Deliberately the same tag as the numpy path.

    The engine tag exists to stop a Whittle score being differenced against a
    Kalman score (section 4.2). Path A and path B compute the SAME exact
    Gaussian likelihood by the same recursion, so they are commensurable, and
    tagging them apart would make the selection layer refuse to rank a resumed
    run against the tile before it -- which is precisely the cross-machine
    workflow the determinism guarantee exists to permit.
    """

    def score(
        self,
        state_space: StateSpace,
        theta: NDArray[np.float64],
        y: NDArray[np.float64],
        mask: NDArray[np.bool_],
        t: NDArray[np.float64],
        design: NDArray[np.float64] | None = None,
        objective: Objective = Objective.ML,
    ) -> ScoredResult:
        """Score a batch, matching `KalmanEngine.score` term for term.

        Args:
            state_space: The composite state space.
            theta: Noise parameters in natural units, shape (B, p).
            y: Observations, shape (B, N).
            mask: True where an observation is present, shape (B, N).
            t: Shared time axis, shape (N,).
            design: Optional design, (N, k) shared or (B, N, k) per series.
            objective: Recorded on the result.

        Returns:
            A `ScoredResult` with the same fields as the numpy engine's.
        """
        reference = KalmanEngine()
        theta = np.asarray(theta, dtype=np.float64)
        y = np.asarray(y, dtype=np.float64)
        mask = np.asarray(mask, dtype=bool)
        t = np.asarray(t, dtype=np.float64)
        batch, n_time = y.shape

        block, per_series = reference._design_block(design, batch, n_time)
        block = np.ascontiguousarray(block)
        block_row = (
            np.arange(batch, dtype=np.intp)
            if per_series
            else np.zeros(batch, dtype=np.intp)
        )
        n_cols = 1 + block.shape[2]
        index, matrices = reference._step_matrices(state_space, theta, t)
        dim = state_space.state_dim

        if matrices:
            f_all = np.ascontiguousarray(np.stack([m[0] for m in matrices]))
            q_all = np.ascontiguousarray(np.stack([m[1] for m in matrices]))
        else:
            f_all = np.zeros((1, batch, dim, dim), dtype=np.float64)
            q_all = np.zeros((1, batch, dim, dim), dtype=np.float64)
            index = np.zeros(max(n_time - 1, 0), dtype=np.intp)

        accum, sum_log_s, n_used, degenerate = _filter_batch(
            np.ascontiguousarray(y),
            block,
            block_row,
            np.ascontiguousarray(mask),
            np.ascontiguousarray(index),
            f_all,
            q_all,
            np.ascontiguousarray(state_space.observation(theta)),
            np.ascontiguousarray(state_space.measurement_variance(theta)),
            np.ascontiguousarray(state_space.stationary_cov(theta)),
        )

        loglik = -0.5 * (
            n_used.astype(np.float64) * np.log(2.0 * np.pi) + sum_log_s + accum[:, 0, 0]
        )
        if n_cols > 1:
            rank_x, gram_ok = reference._rank(accum[:, 1:, 1:])
        else:
            rank_x = np.zeros(batch, dtype=np.int64)
            gram_ok = np.ones(batch, dtype=bool)

        # Classification is transcribed from `KalmanEngine.score` rather than
        # re-derived, including the ORDER: INSUFFICIENT_DATA is diagnosed last
        # because it is the more specific fact, and an all-masked series would
        # otherwise score -0.0 -- higher than any real fit, so it would rank
        # first everywhere it occurred. Two engines that classified differently
        # would make the agreement test a comparison of ladders rather than of
        # filters.
        outcome = outcome_array(batch)
        failed = degenerate | ~np.isfinite(loglik) | ~gram_ok
        outcome[failed] = Outcome.NONFINITE_OBJECTIVE.code
        empty = n_used == 0
        outcome[empty] = Outcome.INSUFFICIENT_DATA.code
        loglik = np.where(failed | empty, np.nan, loglik)

        not_ok = outcome != Outcome.OK.code
        accum = np.where(not_ok[:, None, None], np.nan, accum)
        rank_x = np.where(not_ok, -1, rank_x).astype(np.int64)

        return ScoredResult(
            loglik=loglik,
            engine=self.engine_id,
            objective=objective,
            n_used=n_used,
            rank_x=rank_x,
            normal_equations=accum,
            outcome=outcome,
        )
