"""The engine protocol and the tagged score it returns."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import numpy as np
from numpy.typing import NDArray

from metamer.core.capability import EngineId, Objective
from metamer.core.statespace import StateSpace


@dataclass(frozen=True)
class ScoredResult:
    """A likelihood evaluation, tagged with its engine and objective.

    The tags are load-bearing. A Whittle score is not an exact likelihood, and
    an ML and a REML likelihood live on different measures. Both look
    commensurable and are not, so the selection layer refuses to rank across
    either tag.

    EVERY PER-SERIES FIELD IS `(B,)`-SHAPED. `outcome` in particular is never a
    scalar verdict for the batch: one degenerate grid point marking all B as
    failed contradicts "(B, N) is the only code path" and turns the spatial
    failure map -- itself the diagnostic at 10^7 series -- into a picture of the
    tile grid.

    Attributes:
        loglik: Log-likelihood per series, shape (B,). NaN, never -inf, for any
            series whose `outcome` is not OK. -inf is a finite-looking sentinel
            that survives some consumers' checks and is the optimizer's internal
            barrier value only.
        engine: Which engine produced this score.
        objective: Which objective this score is on.
        n_used: Number of unmasked observations per series, shape (B,). This is
            valid even for a failed series: a count of unmasked epochs is true
            regardless of how the fit went. It is the ONLY field that stays
            meaningful when `outcome` is not OK.
        rank_x: Numerical rank of the accumulated `X' Sigma^-1 X` per series,
            shape (B,). Zero when there is no design; **-1 when `outcome` is not
            OK**, meaning "not computed", which is distinct from a genuine rank
            of 0. This is the PER-SERIES effective rank, not the batch-level
            rank of X: a gap that removes every row supporting a column makes
            that column unidentifiable for that series alone.

            THE RANK IS THRESHOLDED ON THE GRAM, WHICH SQUARES THE CONDITION
            NUMBER. The cutoff is a relative singular-value tolerance of 1e-10
            applied to `X' Sigma^-1 X`, and the Gram's singular values are the
            SQUARES of the whitened design's. So it is an effective tolerance of
            sqrt(1e-10) = **1e-5 on X itself**: a design whose whitened
            condition number reaches 1e5 is reported rank deficient here.
            Measured, not asserted -- at cond(X_w) = 1e5 the Gram's
            s_min/s_max is 1.000e-10, exactly the cutoff; at 1e6 it is 1e-12.

            TASK 8 INHERITS THAT MEANING when it separates `RANK_DEFICIENT_X`
            (exactly singular) from `ILL_CONDITIONED_X` (barely identified).
            Anything it calls ill-conditioned rather than deficient must sit
            above the cutoff, i.e. below a whitened condition number of 1e5. To
            separate the two more finely, derive the condition diagnostic from
            the Gram's singular values directly and halve the exponent to state
            it in X's units -- do not move the constant, which only decides
            where rank stops. It is not load-bearing for the deficient cases:
            those land at 0.0 exactly (a column whose support falls behind a
            gap) or ~5e-17 of the leading value (a duplicated column), decades
            below any candidate cutoff.
        normal_equations: Accumulated whitened cross-products, (B, 1+k, 1+k).

            FOR AN OK SERIES this equals `[y | X]' Sigma^-1 [y | X]` over that
            series' unmasked epochs, and the GLS solution and REML penalty both
            follow from it.

            FOR ANY NON-OK SERIES IT IS ALL-NaN, deliberately. The raw
            accumulator for a degenerate series is *finite* -- assembled partly
            from the engine's substituted innovation variances -- and for an
            all-masked series it is all zeros; both are plausible and both are
            wrong. Since profiling beta out of this matrix is exactly what the
            downstream consumer does, a credible finite answer built from a
            substitution that never happened is the worst possible failure mode.
            NaN makes the misuse fail loudly. Check `outcome` before consuming.
        outcome: Per-series `Outcome.code`, shape (B,) uint8.
    """

    loglik: NDArray[np.float64]
    engine: EngineId
    objective: Objective
    n_used: NDArray[np.int64]
    rank_x: NDArray[np.int64]
    normal_equations: NDArray[np.float64]
    outcome: NDArray[np.uint8]


@runtime_checkable
class Engine(Protocol):
    """Evaluates a likelihood for a state space over a batch of series.

    CHECK CONFORMANCE WITH `isinstance`, NEVER `issubclass`. `engine_id` is a
    non-method member, and a `runtime_checkable` protocol with a data member
    raises `TypeError` from `issubclass` by design.
    """

    engine_id: EngineId

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
        """Return the tagged log-likelihood for each series in the batch."""
        ...
