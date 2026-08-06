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
        n_used: Number of unmasked observations per series, shape (B,).
        rank_x: Numerical rank of the accumulated `X' Sigma^-1 X` per series,
            shape (B,). Zero when there is no design. This is the PER-SERIES
            effective rank, not the batch-level rank of X: a gap that removes
            every row supporting a column makes that column unidentifiable for
            that series alone.
        normal_equations: Accumulated whitened cross-products, (B, 1+k, 1+k),
            equal to `[y | X]' Sigma^-1 [y | X]` over each series' unmasked
            epochs.
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
