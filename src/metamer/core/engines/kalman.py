"""Batched Kalman filter: scalar observations, masked gaps, augmented GLS.

Two structural facts make this simple. The observation is scalar, so the
innovation variance S = H P H' + R is a scalar and there is no inverse, no
Cholesky and no pivoting anywhere in the filter. And P_inf is analytic per
family, so there is no Lyapunov solve either. The filter is therefore analytic
in theta end to end, which is what makes exact-gradient options available.

(The project's rule that validity is classified with the non-raising batched
`slogdet` before any subset is handed to `np.linalg.cholesky` -- which raises
for the WHOLE stack if one member fails -- is vacuous while S is scalar, but it
binds anything added here that factorizes a matrix.)

Because P and S do not depend on the data, one covariance recursion serves the
observation column and every design column at once: the filter runs on the
augmented matrix [y | X] and accumulates the whitened cross-products from which
the GLS solution and the REML penalty both follow.

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
from metamer.core.statespace import StateSpace

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

        cols = self._augment(y, design, batch, n_time)
        n_cols = cols.shape[2]

        steps, index, matrices = self._step_matrices(state_space, theta, t)

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

            v = cols[:, step, :] - np.einsum("bd,bdc->bc", h, x)  # (B, n_cols)
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
        rank_x = (
            self._rank(accum[:, 1:, 1:])
            if n_cols > 1
            else np.zeros(batch, dtype=np.int64)
        )

        outcome = outcome_array(batch)
        # A non-finite score is a NONFINITE_OBJECTIVE however it arose -- the
        # degenerate S above, or a NaN sitting at an UNmasked epoch.
        failed = degenerate | ~np.isfinite(loglik)
        outcome[failed] = Outcome.NONFINITE_OBJECTIVE.code
        # An all-masked series is a legitimate expected outcome (land, permanent
        # ice), and it is diagnosed last because it is the more specific fact.
        # Its empty product would otherwise score -0.0, which is HIGHER than any
        # real fit and would rank first everywhere it occurred.
        empty = n_used == 0
        outcome[empty] = Outcome.INSUFFICIENT_DATA.code
        loglik = np.where(failed | empty, np.nan, loglik)

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
    ) -> tuple[
        NDArray[np.float64],
        NDArray[np.intp],
        list[tuple[NDArray[np.float64], NDArray[np.float64]]],
    ]:
        """Build F and Q once per DISTINCT timestep, with the interval mapping.

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

        Returns:
            The distinct steps, the per-interval index into them (length N-1),
            and the (F, Q) pair for each distinct step.
        """
        raw = np.diff(t)
        steps = state_space.unique_dt(t)
        if steps.size == 0:
            return steps, np.zeros(0, dtype=np.intp), []
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
        return steps, index, matrices

    @staticmethod
    def _augment(
        y: NDArray[np.float64],
        design: NDArray[np.float64] | None,
        batch: int,
        n_time: int,
    ) -> NDArray[np.float64]:
        """Stack [y | X] into a (B, N, 1+k) array of columns to filter.

        Args:
            y: Observations, shape (B, N).
            design: Optional design, (N, k) shared or (B, N, k) per series.
            batch: B.
            n_time: N.

        Returns:
            The augmented columns, shape (B, N, 1+k).

        Raises:
            ValueError: If `design` has the wrong rank or the wrong time axis.
        """
        if design is None:
            return y[:, :, None]
        x = np.asarray(design, dtype=np.float64)
        # The time axis is checked BEFORE `broadcast_to`, not left to it. A
        # (k, N) design handed in transposed is a shape numpy will happily
        # broadcast in some combinations and reject with its own message in
        # others; neither is a diagnosis the caller can act on.
        if x.ndim == 2:
            if x.shape[0] != n_time:
                raise ValueError(
                    f"design shape {x.shape} does not match y shape "
                    f"{(batch, n_time)}: a shared design must be (N, k)"
                )
            x = np.broadcast_to(x, (batch, n_time, x.shape[1]))
        elif x.ndim == 3:
            if x.shape[:2] != (batch, n_time):
                raise ValueError(
                    f"design shape {x.shape} does not match y shape "
                    f"{(batch, n_time)}: a per-series design must be (B, N, k)"
                )
        else:
            raise ValueError(f"design must be (N, k) or (B, N, k); got shape {x.shape}")
        return np.concatenate([y[:, :, None], x], axis=2)

    @staticmethod
    def _rank(gram: NDArray[np.float64]) -> NDArray[np.int64]:
        """Numerical rank of each accumulated X' Sigma^-1 X block.

        Thresholds the GRAM's singular values, whose scale is the square of
        X's -- see `_RANK_RTOL`, which states what that costs.

        Args:
            gram: The accumulated blocks, shape (B, k, k).

        Returns:
            The per-series rank, shape (B,).
        """
        values = np.linalg.svdvals(gram)
        tol = _RANK_RTOL * values[:, :1]
        return np.asarray((values > tol).sum(axis=1), dtype=np.int64)
