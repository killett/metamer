"""Deterministic signal terms, design-matrix construction, and rank(X).

Linear terms are profiled out analytically by GLS at each noise-parameter
evaluation. Nonlinear terms (exponential and logarithmic decays) break that and
require joint optimization; the taxonomy and the dispatch exist from day one so
the fit driver never has to be rewritten to accommodate them.

TIME-AXIS UNIT CONTRACT, stated once here and referenced everywhere it matters:
every `t` accepted by this module MUST be **decimal years**. `Trend` and `Accel`
centre on `t.mean()`, which tolerates a shifted origin (any epoch), but NOT a
change of unit -- and `Harmonic` (hence `Annual`/`SemiAnnual`), `Offset` and
`RateChange` use `t` verbatim with no centring at all. Nothing in this module
rescales the axis.

Violating the contract is not a graceful precision loss, it is catastrophic.
Measured directly (numpy 2.x; script and full output recorded in
task-7-report.md) on a 20-year monthly record with
`[Constant, Trend, Accel, Annual, SemiAnnual]`:

    axis                        cond(X)     rank
    decimal years                3.4e1       7 of 7
    seconds since 1970          >1e30        2 of 7

In the seconds case the annual and semiannual sine columns collapse to float64
rounding noise (~1e-5, against an O(1) signal) rather than real content, because
`2*pi*t/period` at `t ~ 1e9` has no float64 phase resolution left when `period`
is still stated in years (the ordinary way this mistake happens -- the period is
just never converted). `DesignInfo.condition_number` is what surfaces this
class of mistake: `rank(X)` alone does not, since both cases above compute
*some* finite rank.

COLUMNS ARE NOT AUTO-SCALED, deliberately. A per-column scale `s_j` could
restore conditioning for a badly-scaled `X`, but `gram_logdet` (`log|X'X|`,
computed from this same `X` in `design_info`) would then shift by
`2 * sum(log s_j)` relative to what the REML basis-invariance term (Harville
1974) expects, defined on the *original* `X`. Scaling here without carrying and
unwinding that shift in the objective would silently corrupt REML comparisons
across candidates -- and that bookkeeping belongs with Task 8's objective, which
is the only place that knows how the term is used, not with this task, which
only builds `X`. If a future task wants to normalise, it must carry the scale
vector on `DesignInfo` and state exactly how the objective unwinds it. Until
then, the contract above is the guard: put `t` in decimal years and the
polynomial terms are already well-scaled for any realistic record length.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import numpy as np
from numpy.typing import NDArray

X_RANK_RTOL = 1e-10
"""Relative singular-value tolerance for the numerical rank of X itself.

Thresholds the singular values of the DESIGN MATRIX `X` directly. Contrast with
`metamer.core.engines.kalman._RANK_RTOL`, which thresholds the accumulated
GRAM `X'Sigma^-1 X`: squaring a matrix squares its condition number, so a Gram
threshold of `1e-10` is an effective `1e-5` tolerance on `X`'s own singular
values -- five orders of magnitude looser than this constant. **The engine's
threshold is the calibrated one** (its docstring records the measured
`sqrt(1e-10) = 1e-5` correspondence and the reasoning for keeping it at that
value); this constant only governs `SignalSpec.rank`'s upfront, X-only
diagnostic -- `design_matrix`'s returned rank and `DesignInfo.rank`. A design
this module calls full rank can still be reported rank-deficient once the
engine forms the Gram over a series' unmasked epochs:
`test_signal_rank_and_gram_rank_disagree_at_cond_1e7` in the test suite pins a
synthetic design at `cond(X) = 1e7` where the two literally disagree (3 here,
2 there), so the gap is a recorded fact rather than a future surprise.
"""


@runtime_checkable
class SignalTerm(Protocol):
    """One deterministic term contributing columns to the design matrix."""

    @property
    def linear(self) -> bool:
        """Whether this term is linear in its own parameters."""
        ...

    def columns(self, t: NDArray[np.float64]) -> NDArray[np.float64]:
        """Return this term's design columns, shape (n, n_cols)."""
        ...


@dataclass(frozen=True)
class Constant:
    """An intercept."""

    linear: bool = True

    def columns(self, t: NDArray[np.float64]) -> NDArray[np.float64]:
        """Return a column of ones."""
        return np.ones((t.size, 1), dtype=np.float64)


@dataclass(frozen=True)
class Trend:
    """A linear rate, in time units centred on the record mean."""

    linear: bool = True

    def columns(self, t: NDArray[np.float64]) -> NDArray[np.float64]:
        """Return (t - mean(t))."""
        return (t - t.mean())[:, None]


@dataclass(frozen=True)
class Accel:
    """A quadratic term, parameterized so its coefficient is an acceleration."""

    linear: bool = True

    def columns(self, t: NDArray[np.float64]) -> NDArray[np.float64]:
        """Return (t - mean(t))^2 / 2."""
        return (0.5 * (t - t.mean()) ** 2)[:, None]


@dataclass(frozen=True)
class Harmonic:
    """A cosine/sine pair at a specified period.

    Not centred: `period` and `t` are used exactly as given, in the module's
    required decimal-years unit -- see the module docstring's TIME-AXIS UNIT
    CONTRACT for what breaks otherwise.
    """

    period: float
    linear: bool = True

    def columns(self, t: NDArray[np.float64]) -> NDArray[np.float64]:
        """Return [cos(2 pi t / P), sin(2 pi t / P)]."""
        phase = 2.0 * np.pi * t / self.period
        return np.column_stack([np.cos(phase), np.sin(phase)])


@dataclass(frozen=True)
class Annual(Harmonic):
    """The annual cycle. Default period assumes a time axis in years."""

    period: float = 1.0


@dataclass(frozen=True)
class SemiAnnual(Harmonic):
    """The semiannual cycle: twice per year, hence half the annual period."""

    period: float = 0.5


@dataclass(frozen=True)
class Offset:
    """A step of unit height at a user-supplied epoch.

    Breakpoint epochs are user-supplied in v1. Breakpoint *detection* is out of
    scope and is not silently approximated: an undetected offset is nearly
    indistinguishable from random-walk noise, a well-known trap in GNSS trend
    estimation.

    Not centred: `epoch` and `t` are used exactly as given, in decimal years --
    see the module docstring's TIME-AXIS UNIT CONTRACT.
    """

    epoch: float
    linear: bool = True

    def columns(self, t: NDArray[np.float64]) -> NDArray[np.float64]:
        """Return 1 where t >= epoch (inclusive step), else 0."""
        return (t >= self.epoch).astype(np.float64)[:, None]


@dataclass(frozen=True)
class RateChange:
    """A one-sided ramp starting at a user-supplied epoch.

    Not centred: `epoch` and `t` are used exactly as given, in decimal years --
    see the module docstring's TIME-AXIS UNIT CONTRACT.
    """

    epoch: float
    linear: bool = True

    def columns(self, t: NDArray[np.float64]) -> NDArray[np.float64]:
        """Return max(t - epoch, 0): a continuous hinge, 0 at t == epoch."""
        return np.maximum(t - self.epoch, 0.0)[:, None]


@dataclass(frozen=True, eq=False)
class Regressor:
    """An external regressor supplied as a column of values.

    `eq=False`: the payload is a numpy array, and the default dataclass
    equality would compare it with `==`, which returns an elementwise array
    rather than a bool and raises `ValueError: truth value of an array is
    ambiguous`. `eq=False` falls back to identity-based `__eq__`/`__hash__`
    (inherited from `object`), which is hashable and never touches the
    array's values -- see `test_regressor_equality_and_hash_do_not_touch_array_truth_value`.
    """

    values: NDArray[np.float64]
    name: str = "regressor"
    linear: bool = True

    def columns(self, t: NDArray[np.float64]) -> NDArray[np.float64]:
        """Return the supplied values as a single column."""
        arr = np.asarray(self.values, dtype=np.float64)
        if arr.shape[0] != t.size:
            raise ValueError(
                f"{self.name}: length {arr.shape[0]} != time axis {t.size}"
            )
        return arr.reshape(t.size, -1)


@dataclass(frozen=True)
class ExpDecay:
    """Exponential decay from an epoch. Nonlinear in its timescale `tau`.

    `tau` is carried now (Phase 1) even though it is unused until Phase 4's
    joint optimizer exists, so that Phase 4 does not have to change this
    constructor's signature.
    """

    epoch: float
    tau: float
    linear: bool = False

    def columns(self, t: NDArray[np.float64]) -> NDArray[np.float64]:
        """Not available on the concentrated path."""
        raise NotImplementedError(
            "ExpDecay is nonlinear; joint optimization is Phase 4"
        )


@dataclass(frozen=True)
class LogDecay:
    """Logarithmic decay from an epoch. Nonlinear in its timescale `tau`.

    `tau` is carried now (Phase 1) even though it is unused until Phase 4's
    joint optimizer exists, so that Phase 4 does not have to change this
    constructor's signature.
    """

    epoch: float
    tau: float
    linear: bool = False

    def columns(self, t: NDArray[np.float64]) -> NDArray[np.float64]:
        """Not available on the concentrated path."""
        raise NotImplementedError(
            "LogDecay is nonlinear; joint optimization is Phase 4"
        )


@dataclass(frozen=True, eq=False)
class DesignInfo:
    """A built design matrix and everything derived from it that is theta-free.

    `eq=False`: `matrix` is a numpy array, carrying the same defect class
    Correction 8 fixed on `Regressor` -- the default dataclass equality would
    compare it elementwise and raise. Not one of the brief's named examples,
    but the identical bug on the identical kind of field, fixed here for the
    same reason before it resurfaces as a "new" instance of it.

    `gram_logdet` is log|X'X|, the REML basis-invariance term. It is a property
    of X alone, so computing it inside the likelihood would recompute a fixed
    quantity ~50 times per fit, 12 candidates per point, 10^7 points.

    `condition_number` is cond(X) = s_max/s_min from X's OWN singular values
    (not the Gram's -- see `X_RANK_RTOL`'s docstring). The design doc requires
    a condition-number diagnostic that WARNS rather than blocks (SS4.8, SS8.5:
    "Warn, do not block -- but say it out loud"); this field is that number.
    Nothing in this module blocks on it. Infinite where X has zero rows or is
    exactly singular (an all-zero column, e.g. an offset epoch after the last
    sample).

    `rank` and `is_deficient` are **batch-level**: the design may be shared
    across a batch of series, but the Kalman engine accumulates
    `X'Sigma^-1 X` only over each series' *unmasked* epochs, so a design full
    rank here can still be singular for a series whose gaps remove all support
    for one column (an offset or rate-change epoch falling inside a masked
    stretch is the ordinary case, not a contrived one -- see
    `test_shared_design_full_rank_but_per_series_restricted_deficient`). This
    check is therefore necessary but not sufficient; the per-series
    classification happens in Task 8's objective, not here.

    SEAM (Phase 2, per-point regressors): when a regressor is a per-point field
    -- a GIA model -- `matrix` becomes (B, N, k), `rank` and `gram_logdet`
    become shape (B,), and `per_point` becomes True. Every consumer already
    takes this object rather than a loose (design, rank) pair, so that change is
    a shape widening, not a signature rewrite. It also triggers the
    N*k_beta*8-per-series memory term, which dominates the per-series budget.
    """

    matrix: NDArray[np.float64]
    rank: int
    gram_logdet: float
    condition_number: float
    per_point: bool = False

    @property
    def n_beta(self) -> int:
        """Number of design columns."""
        return int(self.matrix.shape[-1])

    @property
    def is_deficient(self) -> bool:
        """Whether the design is rank-deficient (batch-level; see class docstring)."""
        return self.rank < self.n_beta


@dataclass(frozen=True)
class SignalSpec:
    """An ordered collection of deterministic signal terms.

    TIME-AXIS UNIT CONTRACT: `t` passed to `design_matrix` and `design_info`
    MUST be decimal years -- see the module docstring for what breaks
    otherwise (the seconds-since-1970 measurement is the worked example).
    """

    terms: Sequence[SignalTerm]

    def __post_init__(self) -> None:
        """Freeze `terms` into a tuple so `SignalSpec` is hashable (Task 16)."""
        object.__setattr__(self, "terms", tuple(self.terms))

    def design_info(self, t: NDArray[np.float64]) -> DesignInfo:
        """Build the design matrix and its theta-free derived quantities once.

        Args:
            t: Time axis, shape (n,), in decimal years -- see the module
                docstring's TIME-AXIS UNIT CONTRACT.

        Returns:
            A DesignInfo. `gram_logdet` is -inf for a rank-deficient design;
            the caller classifies that as RANK_DEFICIENT_X rather than using
            it. `rank`/`is_deficient` are batch-level -- see `DesignInfo`'s
            docstring.
        """
        t = np.asarray(t, dtype=np.float64)
        matrix, rank = self.design_matrix(t)
        n_beta = matrix.shape[-1]
        if n_beta == 0:
            # No columns at all: nothing can be rank-deficient, and X'X is the
            # 0x0 empty matrix. Handled explicitly rather than routed through
            # slogdet, whose empty-matrix convention isn't something to lean
            # on for a case with a well-defined trivial answer.
            return DesignInfo(matrix, 0, 0.0, condition_number=1.0)
        if t.size == 0:
            # Zero-length time axis: X'X is a k x k all-zero matrix (summed
            # over zero samples) -- exactly singular -- so every column is
            # unidentifiable and gram_logdet is -inf. `matrix.size` is ALSO 0
            # here (zero rows this time, not zero columns), which is why
            # branching on `matrix.size == 0` alone conflates this case with
            # the one above: doing so would report a finite, innocuous-looking
            # gram_logdet = 0.0 and (via `bool(matrix.size and ...)`) a False
            # is_deficient for a design that cannot estimate anything.
            return DesignInfo(matrix, 0, float("-inf"), condition_number=float("inf"))
        sign, logdet = np.linalg.slogdet(matrix.T @ matrix)
        gram_logdet = float(logdet) if sign > 0 else float("-inf")
        return DesignInfo(
            matrix, rank, gram_logdet, condition_number=self._condition_number(matrix)
        )

    @staticmethod
    def _condition_number(x: NDArray[np.float64]) -> float:
        """cond(X) = s_max / s_min from X's own singular values.

        Not the Gram's -- see `X_RANK_RTOL`'s docstring. Infinite where X is
        exactly singular (s_min == 0), which includes an all-zero column.
        """
        values = np.linalg.svdvals(x)
        if values[-1] == 0.0:
            return float("inf")
        return float(values[0] / values[-1])

    @property
    def is_linear(self) -> bool:
        """True when every term is linear in its parameters."""
        return all(term.linear for term in self.terms)

    def design_matrix(self, t: NDArray[np.float64]) -> tuple[NDArray[np.float64], int]:
        """Build the design matrix and its numerical rank.

        TIME-AXIS UNIT CONTRACT: `t` MUST be decimal years. `Trend` and
        `Accel` centre on `t.mean()` (tolerant of an origin shift, not a unit
        change); `Harmonic` (hence `Annual`/`SemiAnnual`), `Offset` and
        `RateChange` use `t` verbatim and do not rescale. See the module
        docstring for the measured seconds-since-1970 failure (cond(X)
        3.4e1 -> >1e30, rank 7/7 -> 2/7).

        COLUMNS ARE NOT AUTO-SCALED. See the module docstring for why:
        normalising by a per-column scale would shift `gram_logdet` (computed
        in `design_info`) by `2 * sum(log s_j)`, corrupting the REML constant
        unless that scale is carried and unwound in Task 8's objective --
        bookkeeping that belongs there, not here.

        Args:
            t: Time axis, shape (n,), in decimal years.

        Returns:
            A tuple of the design matrix (n, k) and its numerical rank
            (`SignalSpec.rank`, thresholded at `X_RANK_RTOL`).

        Raises:
            NotImplementedError: If any term is nonlinear. Phase 1 implements
                only the GLS-concentrated linear path.
        """
        if not self.is_linear:
            raise NotImplementedError(
                "This signal specification contains nonlinear terms; only the "
                "GLS-concentrated linear path is implemented in Phase 1"
            )
        t = np.asarray(t, dtype=np.float64)
        if not self.terms:
            return np.zeros((t.size, 0), dtype=np.float64), 0
        x = np.concatenate([term.columns(t) for term in self.terms], axis=1)
        return x, self.rank(x)

    @staticmethod
    def rank(x: NDArray[np.float64]) -> int:
        """Numerical rank of a design matrix by SVD.

        Thresholds X's OWN singular values at `X_RANK_RTOL` -- see that
        constant's docstring for why this disagrees with the engine's
        Gram-based rank at moderate condition numbers.
        """
        if x.size == 0:
            return 0
        values = np.linalg.svdvals(x)
        if values[0] == 0.0:
            return 0
        return int((values > X_RANK_RTOL * values[0]).sum())

    def n_beta(self, t: NDArray[np.float64]) -> int:
        """Number of design columns for this time axis."""
        return int(self.design_matrix(t)[0].shape[1])
