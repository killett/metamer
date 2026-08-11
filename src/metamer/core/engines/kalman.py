"""Batched Kalman filter: scalar observations, masked gaps, augmented GLS.

Two structural facts make this simple. The observation is scalar, so the
innovation variance S = H P H' + R is a scalar and there is no inverse, no
Cholesky and no pivoting anywhere in the filter. And P_inf is analytic per
family, so there is no Lyapunov solve either. The filter is therefore analytic
in theta end to end, which is what makes exact-gradient options available.

THE "CLASSIFY FIRST, FACTORIZE THE VALID SUBSET" RULE IS NOT VACUOUS HERE, and
an earlier version of this docstring wrongly said it was on the grounds that S
is scalar. The scalar S removes the Cholesky from the *filter recursion*; it
does not remove batched LAPACK from this module. `_rank` calls
`np.linalg.svdvals` on the stack of accumulated Gram blocks, and that raises
`LinAlgError` for the WHOLE stack if any single series' block is non-finite --
one NaN theta out of B would deny every healthy series its result. `_rank`
therefore masks with `np.isfinite(...).all(axis=(1, 2))` and factorizes only the
valid subset, which is exactly what the rule demands.

Because P and S do not depend on the data, one covariance recursion serves the
observation column and every design column at once: the filter runs on the
augmented matrix [y | X] and accumulates the whitened cross-products from which
the GLS solution and the REML penalty both follow.

**[y | X] IS NEVER MATERIALIZED.** It is a way of describing the recursion, not
an array. The accumulator consumes one row at a time, so the observation is
indexed out of `y` and the design columns out of `_design_block`'s (1, N, k)
or (B, N, k) view, per timestep, into a single reused (B, 1+k) row. Building
the (B, N, 1+k) array instead cost 25 200 B/series at N=630 and did not shrink
when the design was shared -- see `_design_block`.

THE ACCUMULATOR IDENTITY, stated because it is the whole reason the augmented
form works. The innovations of a column z are e_z = L z for a unit
lower-triangular L determined by the state space alone (not by the data), and
the innovations representation of the covariance is Sigma = L^-1 D L^-T with
D = diag(S_1, ..., S_N). Hence for any two columns z, w

    z' Sigma^-1 w = (L z)' D^-1 (L w) = sum_i e_z(i) e_w(i) / S_i,

which is exactly `accum += v v' / S` accumulated over the unmasked epochs. With
the columns stacked as [y | X] the single accumulator therefore holds
y'Sigma^-1 y, y'Sigma^-1 X and X'Sigma^-1 X at once, and log|Sigma| = sum log S
falls out of the same sweep. Every column is initialised from x = 0 because L
depends only on the recursion, never on the values being filtered.

MEMORY NOTE FOR TASK 17. F and Q are built eagerly, once per DISTINCT timestep,
and held for the whole sweep: `2 * S * B * d^2` float64 values, where S is the
number of distinct steps. On a regular axis S = 1 and this is negligible. On a
FULLY IRREGULAR axis S = N - 1, so the eager build degenerates to materializing
every interval's matrices simultaneously -- the amortization failing and the
memory growing linearly in N, with no chunking and no cap in this
implementation. A long irregular series must be driven in chunks by the caller,
or this must grow a cap, before it meets the Task 17 budget.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from metamer.core.capability import EngineId, Objective
from metamer.core.engines.protocol import ScoredResult
from metamer.core.outcomes import Outcome, outcome_array
from metamer.core.statespace import UNIQUE_DT_RTOL, StateSpace

_RANK_RTOL = 1e-10
"""Relative singular-value cutoff for the rank of the accumulated X'Sigma^-1 X.

THIS THRESHOLDS THE GRAM MATRIX, NOT X, AND THE GRAM SQUARES THE CONDITION
NUMBER. For a whitened design X_w the accumulated block is X_w' X_w, whose
singular values are the SQUARES of X_w's. A cutoff of 1e-10 on the Gram is
therefore an effective tolerance of sqrt(1e-10) = 1e-5 on X_w itself: a design
whose whitened condition number reaches 1e5 is reported rank deficient here.

CALIBRATION, measured rather than asserted (numpy 2.x / OpenBLAS, n = 200,
orthonormal Q rescaled to a target condition number):

    cond(X_w)   s_min/s_max (X_w)   s_min/s_max (Gram)
    1e+2        1.000e-02           1.000e-04
    1e+4        1.000e-04           1.000e-08
    1e+5        1.000e-05           1.000e-10   <-- the cutoff, exactly
    1e+6        1.000e-06           1.000e-12
    1e+8        1.000e-08           1.000e-16   <-- at float64 noise already

KEPT AT 1e-10 DELIBERATELY, not tuned. Two facts bound it from either side. An
exactly rank-deficient design (a duplicated column; a column whose entire
support falls behind a gap) puts the null singular value at 0 exactly or at
~5e-17 of the leading one, both decades below any candidate threshold, so the
constant is not what makes those cases work. Meanwhile a Gram formed by
accumulation at cond(X_w) = 1e8 has already lost the small singular value into
float64 noise, so a threshold below ~1e-16 would be reading rounding error.
1e-10 sits in the middle of that window.

TASK 8 INHERITS THIS THRESHOLD'S MEANING. `RANK_DEFICIENT_X` (exactly singular)
and `ILL_CONDITIONED_X` (barely identified) are distinct outcomes, and this
constant is the line between them as seen through the Gram: anything Task 8
classifies as ill-conditioned rather than deficient must sit ABOVE
`_RANK_RTOL`, i.e. at a whitened condition number below 1e5. If Task 8 needs to
separate the two at a finer scale it should compute its condition diagnostic
from the Gram's singular values directly (and halve the exponent to state it in
X's units) rather than move this constant, which only decides where rank stops.
"""


class KalmanEngine:
    """Exact O(N) state-space likelihood, vectorized over the series axis."""

    engine_id = EngineId.KALMAN

    def score(
        self,
        state_space: StateSpace,
        theta: NDArray[np.float64],
        y: NDArray[np.float64],
        mask: NDArray[np.bool_],
        t: NDArray[np.float64],
        design: NDArray[np.float64] | None,
        objective: Objective = Objective.ML,
    ) -> ScoredResult:
        """Filter a batch of series and accumulate whitened cross-products.

        Never interpolates a gap: a masked epoch skips the UPDATE and keeps the
        PREDICTION, so P propagates across the gap and no innovation is
        manufactured.

        Args:
            state_space: Composite state space for this candidate.
            theta: Noise parameters in natural units, shape (B, p). This is the
                FULL parameter vector -- `StateSpace.from_spec` slices over all
                of a term's parameters including fixed ones, so a free-only
                vector must be widened before it arrives here.
            y: Observations, shape (B, N). Values under the mask are ignored
                and may be NaN.
            mask: True where an observation is present, shape (B, N).
            t: Shared time axis, shape (N,).
            design: Optional design matrix, shape (N, k) if shared across
                series or (B, N, k) if per-point.
            objective: Recorded on the result; the penalty itself is applied by
                `metamer.core.objective`.

        Returns:
            A ScoredResult whose `loglik` is the y-only Gaussian log-likelihood
            and whose `normal_equations` is the (B, 1+k, 1+k) accumulator.
            Series that could not be scored carry NaN and a non-OK `outcome`.

        Raises:
            ValueError: If `design` is neither (N, k) nor (B, N, k), or if its
                time axis disagrees with `y`.
        """
        theta = np.asarray(theta, dtype=np.float64)
        y = np.asarray(y, dtype=np.float64)
        mask = np.asarray(mask, dtype=bool)
        t = np.asarray(t, dtype=np.float64)
        batch, n_time = y.shape
        dim = state_space.state_dim

        block, per_series = self._design_block(design, batch, n_time)
        n_cols = 1 + block.shape[2]
        # ONE ROW, REUSED. `[y | X]` is never materialized -- see
        # `_design_block` for the 25 200 B/series this used to cost, and for
        # why the shared design did not make it free.
        row = np.empty((batch, n_cols), dtype=np.float64)

        index, matrices = self._step_matrices(state_space, theta, t)

        h = state_space.observation(theta)
        r = state_space.measurement_variance(theta)
        p = state_space.stationary_cov(theta)
        x = np.zeros((batch, dim, n_cols), dtype=np.float64)

        accum = np.zeros((batch, n_cols, n_cols), dtype=np.float64)
        sum_log_s = np.zeros(batch, dtype=np.float64)
        n_used = np.zeros(batch, dtype=np.int64)
        degenerate = np.zeros(batch, dtype=bool)

        for step in range(n_time):
            if step > 0:
                f, q = matrices[int(index[step - 1])]
                x = f @ x
                p = f @ p @ np.transpose(f, (0, 2, 1)) + q

            active = mask[:, step]
            if not active.any():
                continue

            hp = np.einsum("bd,bde->be", h, p)  # (B, d) == H P == (P H')'
            s = np.einsum("be,be->b", hp, h) + r  # (B,)

            # A non-positive or non-finite innovation variance is a per-series
            # failure with a name, not a NaN that emerges three layers later.
            # It is reachable: R = 0 drives P to exactly 0 after one update, and
            # a repeated timestamp then has F = I, Q = 0 and so S = 0 exactly.
            # Substituting 1.0 keeps the arithmetic (and the other series)
            # clean; the verdict below is what the caller sees.
            usable = np.isfinite(s) & (s > 0.0)
            degenerate |= active & ~usable
            safe_s = np.where(usable, s, 1.0)

            row[:, 0] = y[:, step]
            if n_cols > 1:
                row[:, 1:] = block[:, step, :] if per_series else block[0, step, :]
            v = row - np.einsum("bd,bdc->bc", h, x)  # (B, n_cols)
            # ZERO THE INNOVATION UNDER THE MASK, do not merely down-weight it.
            # Masked slots holding NaN is the normal convention for gappy data,
            # and `0 * NaN` is NaN: a weight of zero would let one series' gap
            # poison every batch-mate sharing the step.
            v = np.where(active[:, None], v, 0.0)
            gain = hp / safe_s[:, None]  # (B, d)

            upd_x = x + gain[:, :, None] * v[:, None, :]
            # Plain (non-Joseph) covariance form. The correction is the
            # symmetric outer product (P H')(H P)/S, so symmetry is preserved
            # structurally rather than by luck; the Joseph form buys nothing
            # here and costs an extra d x d product per step.
            upd_p = p - gain[:, :, None] * hp[:, None, :]

            w = active.astype(np.float64)
            x = np.where(active[:, None, None], upd_x, x)
            p = np.where(active[:, None, None], upd_p, p)

            accum += (w / safe_s)[:, None, None] * v[:, :, None] * v[:, None, :]
            sum_log_s += w * np.log(safe_s)
            n_used += active.astype(np.int64)

        loglik = -0.5 * (
            n_used.astype(np.float64) * np.log(2.0 * np.pi) + sum_log_s + accum[:, 0, 0]
        )
        if n_cols > 1:
            rank_x, gram_ok = self._rank(accum[:, 1:, 1:])
        else:
            rank_x = np.zeros(batch, dtype=np.int64)
            gram_ok = np.ones(batch, dtype=bool)

        outcome = outcome_array(batch)
        # A non-finite score is a NONFINITE_OBJECTIVE however it arose -- the
        # degenerate S above, a NaN sitting at an UNmasked epoch, or a Gram
        # block that could not be factorized at all.
        failed = degenerate | ~np.isfinite(loglik) | ~gram_ok
        outcome[failed] = Outcome.NONFINITE_OBJECTIVE.code
        # An all-masked series is a legitimate expected outcome (land, permanent
        # ice), and it is diagnosed last because it is the more specific fact.
        # Its empty product would otherwise score -0.0, which is HIGHER than any
        # real fit and would rank first everywhere it occurred.
        empty = n_used == 0
        outcome[empty] = Outcome.INSUFFICIENT_DATA.code
        loglik = np.where(failed | empty, np.nan, loglik)

        # POISON THE CROSS-PRODUCTS OF EVERY NON-OK SERIES. For a degenerate
        # series `accum` is a FINITE matrix assembled partly from the
        # `safe_s = 1.0` substitutions above, and for an all-masked series it is
        # all zeros. Both are plausible and both are wrong. Task 8 profiles beta
        # out of exactly this matrix, so leaving them would hand it a credible
        # finite answer built from a substitution that never happened. NaN makes
        # the misuse fail loudly instead. `n_used` is deliberately NOT poisoned:
        # a count of unmasked epochs is true regardless of how the fit went.
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

    @staticmethod
    def _step_matrices(
        state_space: StateSpace,
        theta: NDArray[np.float64],
        t: NDArray[np.float64],
        rtol: float = UNIQUE_DT_RTOL,
    ) -> tuple[
        NDArray[np.intp],
        list[tuple[NDArray[np.float64], NDArray[np.float64]]],
    ]:
        """Build F and Q once per DISTINCT timestep, with the interval mapping.

        THIS IS THE ONLY IMPLEMENTATION of the cluster-index invariant.
        `StateSpace._step_matrices` was a second, near-verbatim copy of it and
        has been deleted; this project already learned from five copies of the
        parameter-layout loop that the invariant needs one home.

        THE INTERVAL IS MAPPED THROUGH THE REPRESENTATIVES, NOT LOOKED UP BY
        VALUE. `unique_dt` returns tolerance-clustered representatives, so the
        raw step `t[i] - t[i-1]` is generally not one of them: `np.linspace(0,
        10, 101)` has eight distinct float64 differences that cluster to one
        representative, and a dict keyed on the raw float misses on every
        interval. `np.arange` grids are bit-exact and hide this completely.

        `steps` is ascending and each cluster is represented by its smallest
        member, so `searchsorted(..., "right") - 1` lands every raw step on its
        own representative; the clip only guards a raw step below the smallest
        representative, which arithmetic noise can produce at the boundary.

        Args:
            state_space: The composite state space.
            theta: Parameters, shape (B, p).
            t: Timestamps, shape (N,).
            rtol: Relative tolerance forwarded to `unique_dt`. Forwarded rather
                than left at the default from the only caller, so the clustering
                scale stays adjustable from outside -- the same reason
                `safe_transition` forwards `cond_threshold`.

        Returns:
            The per-interval index into the distinct steps (length N-1), and the
            (F, Q) pair for each distinct step.
        """
        raw = np.diff(t)
        steps = state_space.unique_dt(t, rtol=rtol)
        if steps.size == 0:
            return np.zeros(0, dtype=np.intp), []
        index = np.clip(
            np.searchsorted(steps, raw, side="right") - 1, 0, steps.size - 1
        ).astype(np.intp)
        matrices = [
            (
                state_space.transition(theta, float(step)),
                state_space.process_noise(theta, float(step)),
            )
            for step in steps
        ]
        return index, matrices

    @staticmethod
    def _design_block(
        design: NDArray[np.float64] | None,
        batch: int,
        n_time: int,
    ) -> tuple[NDArray[np.float64], bool]:
        """Validate the design and present it as (D, N, k) WITHOUT copying it.

        THIS REPLACED `_augment`, WHICH MATERIALIZED `[y | X]` AS A
        `(B, N, 1+k)` FLOAT64 ARRAY -- 25 200 B/series at N=630, k=4, against
        design doc section 9.4's per-series target of 8 682 B for the whole
        filter. The block did not vanish when the design was shared, which is
        the case section 9.4 treats as free, because
        `np.concatenate([y[:, :, None], np.broadcast_to(x, ...)], axis=2)`
        copies the broadcast view into a real array, replicating one shared
        design once per series. The `broadcast_to` above it allocates nothing,
        which is exactly why the copy read as free on a code read.

        The accumulator only ever needed one row at a time, so both engines
        now index the columns out of `y` and this block per timestep. That
        makes section 9.4's model true rather than replacing it.

        A shared design is returned as `x[None]`, a VIEW of shape (1, N, k),
        so the shared case costs one copy of X for the whole tile rather than
        one per series. `per_series` says which axis-0 length the caller has.

        Args:
            design: Optional design, (N, k) shared or (B, N, k) per series.
            batch: B.
            n_time: N.

        Returns:
            `(block, per_series)`. `block` is (1, N, k) when the design is
            shared and (B, N, k) when it is per series; `k` is 0 when there is
            no design, which keeps the shape uniform and makes `n_cols` fall
            out as `1 + block.shape[2]` in both engines.

        Raises:
            ValueError: If `design` has the wrong rank or the wrong time axis.
        """
        if design is None:
            return np.empty((1, n_time, 0), dtype=np.float64), False
        x = np.asarray(design, dtype=np.float64)
        # The time axis is checked EXPLICITLY, not left to indexing. A (k, N)
        # design handed in transposed is a shape numpy will happily index in
        # some combinations and reject with its own message in others; neither
        # is a diagnosis the caller can act on.
        if x.ndim == 2:
            if x.shape[0] != n_time:
                raise ValueError(
                    f"design shape {x.shape} does not match y shape "
                    f"{(batch, n_time)}: a shared design must be (N, k)"
                )
            return x[None], False
        if x.ndim == 3:
            if x.shape[:2] != (batch, n_time):
                raise ValueError(
                    f"design shape {x.shape} does not match y shape "
                    f"{(batch, n_time)}: a per-series design must be (B, N, k)"
                )
            return x, True
        raise ValueError(f"design must be (N, k) or (B, N, k); got shape {x.shape}")

    @staticmethod
    def _rank(
        gram: NDArray[np.float64],
    ) -> tuple[NDArray[np.int64], NDArray[np.bool_]]:
        """Numerical rank of each accumulated X' Sigma^-1 X block.

        CLASSIFY FIRST, FACTORIZE ONLY THE VALID SUBSET. `np.linalg.svdvals`
        raises `LinAlgError` for the ENTIRE stack if any one member fails to
        converge, so handing it a batch containing a single non-finite block
        denies every healthy series its result -- the precise batch-wide failure
        the project rule forbids. A NaN theta reaching here is not hypothetical:
        Task 13's optimizer will produce one, and Task 8 supplies the X that
        makes this path live at all.

        The validity test is `np.isfinite`, which cannot raise, rather than a
        trial factorization.

        Thresholds the GRAM's singular values, whose scale is the square of
        X's -- see `_RANK_RTOL`, which states what that costs.

        Args:
            gram: The accumulated blocks, shape (B, k, k).

        Returns:
            The per-series rank (0 where the block was not factorizable), and
            the per-series validity mask, both shape (B,).
        """
        ok = np.asarray(np.isfinite(gram).all(axis=(1, 2)))
        rank = np.zeros(gram.shape[0], dtype=np.int64)
        if ok.any():
            values = np.linalg.svdvals(gram[ok])
            tol = _RANK_RTOL * values[:, :1]
            rank[ok] = (values > tol).sum(axis=1)
        return rank, ok
