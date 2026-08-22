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

EVERY CONSUMER TAKING ONE SERIES MUST CALL `DesignInfo.series(b)` FIRST.
`rank`, `gram_logdet`, `condition_number`, `n_rows` and `unit_variance_beta_var`
are all `(B,)`-shaped and describe **X restricted to that series' unmasked
rows**. Handing the full-batch object to a per-series routine pairs one series'
data with the whole batch's diagnostics. That is a PLAUSIBLE-NUMBER failure,
not a crash: the arrays are the right dtype, the right sign and the right
order of magnitude, so an off-by-one series lands in the store looking exactly
like a fit. `fit.py` narrows before every `optimize_series` and every
`evaluate` call for this reason, and it is the one thing signature binding
could not have caught during the Task 14 audit -- every call bound correctly
and the code still did not work.

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

from metamer.core.registry import signal_registry

#: How many series the batched restricted SVD decomposes per call.
#:
#: **POLICY, AND IT BOUNDS THE LARGEST TEMPORARY IN A FIT.**
#: `_restricted_singular_values`' third tier builds `x[None] * mask[..., None]`,
#: which is `B * N * k_beta * 8` bytes -- **1.49 GB at the design doc's worked
#: example**, N = 630 and the published tile side of 272, and measured at Phase
#: 2b's OQ18 Task A-prime as **the fit phase's maximum at 17 of 17 points** and
#: the single largest unmodelled term in the memory model. Chunking bounds it at
#: `SVD_CHUNK_SERIES * N * k_beta * 8` and changes no returned bit, because
#: LAPACK decomposes each `(N, k)` matrix independently.
#:
#: **THE ASYMMETRY, AND ONLY ONE SIDE OF IT COSTS ANYTHING MEASURABLE.** Too
#: large and the temporary is unbounded again, which is the defect. Too small
#: and per-call overhead should dominate -- **measured, and it does not**: at
#: B = 9216 the whole ladder from 64 to 9216 series per call is flat at
#: **48.9-66.7 ms** at N = 60, and at N = 240 chunking is **faster** than not,
#: **121.3 ms at 512 against 161.2 ms whole**. So the constant is chosen for the
#: bound rather than for the clock.
#:
#: **512 PUTS THE TEMPORARY AT ABOUT 1 MB AT N = 60, 3.9 MB AT N = 240 AND
#: 10.3 MB AT THE WORKED EXAMPLE'S N = 630** -- three orders below what it
#: replaces, and below the window of every RSS assertion in the suite.
SVD_CHUNK_SERIES: int = 512

X_RANK_RTOL: float = float(np.finfo(np.float64).eps) ** 0.5
"""Relative singular-value tolerance for the numerical rank of X. sqrt(eps).

DERIVED FROM float64, NOT PICKED. It was `1e-10` until 2026-08-10 -- a round
number with no argument behind it, and 149x tighter than the derivation gives,
which is the wrong direction: it called a column full rank whose contribution
to the Gram had already vanished.

UNITS: a ratio of singular values of the DESIGN MATRIX `X` itself,
`s_i / s_max`, not of the Gram.

THE DERIVATION. COUNT THE SQUARINGS. `X` is never used directly: every
consumer of this rank forms `X' Sigma^-1 X`, whose singular values are the
SQUARES of the whitened design's. A direction survives that squaring only if
its squared ratio is still representable,

    (s_i / s_max)^2 > eps   =>   s_i / s_max > sqrt(eps) = 1.4901e-08

so `sqrt(eps)` is where a column stops contributing anything the Gram can
carry. One squaring, hence the square root -- the same count that gives
`objective.CONDITION_LOG_LIMIT` its fourth root (that constant thresholds a
condition number, which is a ratio of a ratio; this one thresholds the ratio).
Copying either exponent to the other is the measured default mistake.

CONSEQUENCE, STATED SO IT IS NOT QUIETLY RETUNED: a design whose singular
values span more than `1/sqrt(eps) = 6.7e7` is now reported rank deficient
where `1e-10` called it full rank. The measured instance is
`test_gram_logdet_accurate_at_cond_1e9_slogdet_route_fails`, whose fixture sits
at `cond(X) = 1e9`: its Gram is at `cond = 1e18`, past float64 entirely, and
calling it full rank was the old constant's error rather than that fixture's.

CONTRAST WITH THE ENGINE'S GRAM CUTOFF, which is a different constant with a
different job. `engines.kalman._RANK_RTOL` thresholds the accumulated
`X'Sigma^-1X`, and it is **calibrated with a recorded measurement** rather than
derived -- its docstring carries the measured window that bounds it from both
sides and its reason for staying at `1e-10`, which is an effective `1e-5` on
`X_w`'s own singular values. `objective.RANK_DEFICIENT_LOG_LIMIT` is derived
from THAT constant, not from this one; PROGRESS.md and the Phase 1 handoff said
otherwise, and were wrong. This constant only governs `SignalSpec.rank`'s
upfront, X-only diagnostic -- `design_matrix`'s returned rank and
`DesignInfo.rank`. The two still disagree by construction, which is the point:
`test_signal_rank_and_gram_rank_disagree_at_cond_1e7` pins a synthetic design
at `cond(X) = 1e7` where this module says 3 and the engine says 2.
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
        # Explicit dtype: numpy 2.4's stubs infer `floating[Any]` for this
        # expression where 2.5's infer `float64`, and numba pins numpy<2.5.
        return np.asarray((t - t.mean())[:, None], dtype=np.float64)


@dataclass(frozen=True)
class Accel:
    """A quadratic term, parameterized so its coefficient is an acceleration."""

    linear: bool = True

    def columns(self, t: NDArray[np.float64]) -> NDArray[np.float64]:
        """Return (t - mean(t))^2 / 2."""
        return np.asarray((0.5 * (t - t.mean()) ** 2)[:, None], dtype=np.float64)


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

    `rank`, `gram_logdet` and `condition_number` ARE ALL PER SERIES, shape
    `(B,)`, and describe **X restricted to that series' unmasked rows** -- call
    it `X_r`. They are not batch-level summaries of the shared `matrix`.

    The reason is Harville's REML form, which needs `rank(X)` and `log|X'X|`
    over the SAME design the quadratic form is built on. The Kalman engine
    accumulates `X' Sigma^-1 X` only over each series' unmasked epochs, so that
    design is `X_r`, not `X`. Using the full-design values for a gapped series
    is wrong by `0.5 * (log|X'X| - log|X_r'X_r|)` in the log-likelihood. That
    error is THETA-FREE, so it cancels in every delta-IC and no differential
    test can see it -- the same defect class as a wrong REML constant, one
    level down -- while the stored absolute `log_lik` is wrong for every series
    with a gap, which is every real series. Measured on a 10-epoch gap:
    -95.7269 against the oracle's -95.9113.

    THIS DOES NOT UNDO THE HOISTING. These quantities depend on `(matrix,
    mask)` and nothing else; the mask is DATA, not theta, so they stay constant
    across an optimization and are still computed exactly once, at setup, by
    `SignalSpec.design_info`. Widening them from scalars to `(B,)` arrays
    changes their shape, not when they are computed. Nothing in the likelihood
    may recompute them.

    `rank` IS NOT `ScoredResult.rank_x`, and the two must not be conflated.
    This one is `rank(X_r)`: a property of the DESIGN alone, independent of
    Sigma, thresholded on X's own singular values at `X_RANK_RTOL`. The
    engine's `rank_x` is the rank of the WHITENED Gram `X_r' Sigma^-1 X_r`,
    thresholded at `kalman._RANK_RTOL`, and therefore depends on theta. They
    answer different questions and disagree at moderate condition numbers (see
    `X_RANK_RTOL`'s docstring for the measured five-orders-of-magnitude gap).
    Harville's rank constant is THIS one, and `ObjectiveResult.design_rank`
    is where it is carried through to Task 9, which MUST compute REML's
    effective sample size `n_obs - rank(X)` from it. `ObjectiveResult.rank_x`
    carries the engine's whitened rank instead, as a numerical diagnostic of
    the solve at that theta, and counting with it makes the count inconsistent
    with the constant the likelihood was built from. Both are carried on
    `ObjectiveResult` precisely so neither has to be inferred; see its
    docstring for which is which.

    `gram_logdet` is log|X_r'X_r| -- the FULL determinant's log, NOT half of
    it. Harville's (1974) basis-invariance term is `+ (1/2) * log|X'X|` in the
    log-likelihood; Task 8's objective applies that one-half itself.

    It is computed as `2 * sum(log(s))` over X_r's singular values, from the
    SAME decomposition as `condition_number` (see `_restricted_singular_values`
    and `_diagnostics`), and NOT from `slogdet(X'X)`. Forming the Gram squares
    the condition number and `slogdet`'s LU factorization inherits that loss:
    measured (task-7-report.md) at +3.20 nats of error at cond(X) = 1e9 and
    +8.58 nats at 1e10, both silently reported as finite; and at cond(X) = 1e9
    one fixed-seed construction made `slogdet` return a spurious NEGATIVE sign
    for a matrix that is genuinely positive semidefinite, which a
    `sign > 0 else -inf` branch would have turned into `gram_logdet = -inf` for
    a design that is actually full rank.

    **`gram_logdet` reaches -inf ONLY when X_r is EXACTLY singular** (an
    all-zero column, or more columns than unmasked rows). A design that is
    merely NUMERICALLY rank-deficient -- its smallest singular value clears
    zero but falls below `X_RANK_RTOL` -- still has a finite, if very negative,
    value: singular values `[1, 1e-2, 1e-11]` give rank 2 of 3 with
    `gram_logdet` ~ -59.9, not -inf. **`is_deficient` is the gate for rank
    deficiency; a finite `gram_logdet` is not proof of full rank, and
    `gram_logdet == -inf` is only one of the ways a deficient design shows up.**

    `condition_number` is cond(X_r) = s_max/s_min from X_r's OWN singular
    values (not the Gram's -- see `X_RANK_RTOL`'s docstring). The design doc
    requires a condition-number diagnostic that WARNS rather than blocks
    (SS4.8, SS8.5); this field is that number and nothing in this module blocks
    on it. Infinite where X_r is exactly singular or has more columns than
    unmasked rows.

    `n_rows` is the per-series count of unmasked epochs this object was built
    from. It exists to be CHECKED against the mask the objective is evaluated
    with: a `DesignInfo` built from one mask and used with another yields a
    silently wrong absolute REML value and no other symptom, which is precisely
    the failure class the per-series widening exists to remove. It equals
    `ScoredResult.n_used` for the same mask.

    SEAM (Phase 2, per-point regressors): when a regressor is a per-point field
    -- a GIA model -- `matrix` becomes (B, N, k) and `per_point` becomes True.
    The derived fields are already (B,), so that change no longer widens them.
    It does trigger the N*k_beta*8-per-series memory term, which dominates the
    per-series budget.
    """

    matrix: NDArray[np.float64]
    rank: NDArray[np.int64]
    gram_logdet: NDArray[np.float64]
    condition_number: NDArray[np.float64]
    n_rows: NDArray[np.int64]
    per_point: bool = False
    column_terms: tuple[str, ...] = ()
    """Class name of the term that produced each column, length `n_beta`.

    Built from each term's OWN column count, not from `len(terms)`: `Harmonic`
    (hence `Annual` and `SemiAnnual`) contributes two columns, everything else
    in Phase 1 contributes one, so a per-term mapping is off by one from the
    first harmonic onward -- silently, because the labels remain plausible
    strings in plausible positions.

    It exists so `counting.n_eff_trend` can find the trend column. Without it
    the caller assumes index 1, which holds only for the `[Constant, Trend,
    ...]` ordering fixtures happen to use; with `[Annual(), Trend()]` the trend
    is column 2 and the reported effective sample size is a seasonal
    amplitude's, labelled as a trend's.
    """
    mask: NDArray[np.bool_] | None = None
    """The presence mask this object was built with, shape (B, N).

    Carried so `unit_variance_beta_var` can restrict the design to each series'
    own rows. `DesignInfo`'s contract is already that every derived field
    describes the RESTRICTED design; keeping the mask makes that computable
    later instead of only asserted.
    """

    @property
    def batch(self) -> int:
        """Number of series these derived quantities describe."""
        return int(self.rank.shape[0])

    def series(self, index: int) -> DesignInfo:
        """Return this design narrowed to one series, as a batch of one.

        `optimize_series` fits one series at a time against a `(B,)`-wide
        design, so something has to narrow it. Doing that at the call site by
        hand is how a series' rank comes to be paired with another series'
        rows -- silently, because both are the right shape and dtype.

        Args:
            index: Which series.

        Returns:
            A `DesignInfo` with `batch == 1`, carrying that series' mask and
            derived fields. The matrix is the shared one unless `per_point`.
        """
        window = slice(index, index + 1)
        return DesignInfo(
            self.matrix[window] if self.per_point else self.matrix,
            rank=self.rank[window],
            gram_logdet=self.gram_logdet[window],
            condition_number=self.condition_number[window],
            n_rows=self.n_rows[window],
            per_point=self.per_point,
            column_terms=self.column_terms,
            mask=None if self.mask is None else np.asarray(self.mask)[window],
        )

    @property
    def trend_column(self) -> int | None:
        """Index of the `Trend` column, or None if the design has no trend.

        Returns:
            The column index, or None.
        """
        if "Trend" not in self.column_terms:
            return None
        return self.column_terms.index("Trend")

    @property
    def unit_variance_beta_var(self) -> NDArray[np.float64]:
        """`diag((X_r' X_r)^-1)` per series, shape (B, n_beta).

        The coefficient variances the record would give under **white noise of
        unit variance**, so multiplying by a marginal variance gives the
        white-noise reference `counting.n_eff_trend` divides into. Per series,
        because the mask decides which rows enter `X_r` -- computing it from
        the full design instead reports `1/n` where a half-masked series' truth
        is `2/n`, an effective sample size wrong by exactly the mask fraction
        and wrong in the flattering direction.

        Returns:
            The diagonal, shape (B, n_beta), **NaN for any series whose
            restricted design is rank deficient** -- there is no inverse there,
            and `np.linalg.inv` on a singular Gram either raises, taking down
            the tile, or returns a huge finite number that becomes a
            confident-looking effective sample size for a design the record
            does not identify.
        """
        out = np.full((self.batch, self.n_beta), np.nan, dtype=np.float64)
        if self.n_beta == 0 or self.mask is None:
            return out
        deficient = self.is_deficient
        for series in range(self.batch):
            if bool(deficient[series]):
                continue
            rows = np.asarray(self.mask)[series]
            restricted = (
                self.matrix[series][rows] if self.per_point else self.matrix[rows]
            )
            gram = restricted.T @ restricted
            out[series] = np.diag(np.linalg.inv(gram))
        return out

    @property
    def n_beta(self) -> int:
        """Number of design columns."""
        return int(self.matrix.shape[-1])

    @property
    def is_deficient(self) -> NDArray[np.bool_]:
        """Per-series rank deficiency of X_r, shape (B,)."""
        return np.asarray(self.rank < self.n_beta, dtype=np.bool_)


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

    def design_info(
        self, t: NDArray[np.float64], mask: NDArray[np.bool_]
    ) -> DesignInfo:
        """Build the design matrix and its per-series theta-free quantities once.

        THE MASK IS REQUIRED, and the returned `rank`, `gram_logdet`,
        `condition_number` and `n_rows` all describe **X restricted to each
        series' unmasked rows** -- see `DesignInfo`'s docstring for why
        Harville's REML form needs the restricted design and not the full one.
        There is deliberately no default: an implicit "all epochs present"
        would produce a plausible, silently wrong absolute REML value for every
        gapped series, which is exactly the failure this signature prevents.

        CALL THIS ONCE PER FIT, at setup. Everything it returns is theta-free
        (the mask is data), so it is constant across an optimization and must
        never be recomputed inside the likelihood.

        Args:
            t: Time axis, shape (N,), in decimal years -- see the module
                docstring's TIME-AXIS UNIT CONTRACT.
            mask: Presence mask, shape (B, N), True where an observation
                exists. The SAME mask must later be passed to the objective.

        Returns:
            A DesignInfo whose derived fields are all shape (B,).
            `gram_logdet` is -inf exactly where the restricted design is rank
            deficient; a design that is merely ILL-CONDITIONED still has a
            finite (if very negative) value, so **`is_deficient` is the gate a
            caller must use for RANK_DEFICIENT_X, never `gram_logdet == -inf`**
            -- see `DesignInfo`'s docstring for the measured counter-example.

        Raises:
            ValueError: If `mask` is not two-dimensional or its time axis
                disagrees with `t`.
        """
        t = np.asarray(t, dtype=np.float64)
        mask = np.asarray(mask, dtype=bool)
        if mask.ndim != 2 or mask.shape[1] != t.size:
            raise ValueError(
                f"mask shape {mask.shape} does not match the time axis "
                f"(N = {t.size}): a presence mask must be (B, N)"
            )
        matrix = self.design_matrix(t)[0]
        batch, n_beta = mask.shape[0], matrix.shape[-1]
        n_rows = np.count_nonzero(mask, axis=1).astype(np.int64)

        if n_beta == 0:
            # No columns at all: nothing can be rank-deficient, and X'X is the
            # 0x0 empty matrix, whose determinant is 1 and whose log is 0.
            # Handled explicitly rather than routed through the SVD, whose
            # empty-matrix conventions aren't something to lean on for a case
            # with a well-defined trivial answer. Distinct from the zero-ROWS
            # case, which the general path below handles correctly (all
            # singular values structurally zero => rank 0 < n_beta).
            return DesignInfo(
                matrix,
                rank=np.zeros(batch, dtype=np.int64),
                gram_logdet=np.zeros(batch, dtype=np.float64),
                condition_number=np.ones(batch, dtype=np.float64),
                n_rows=n_rows,
                column_terms=self._column_terms(t),
                mask=mask,
            )

        values = self._restricted_singular_values(matrix, mask)
        condition_number, gram_logdet, rank = self._diagnostics(values)
        return DesignInfo(
            matrix,
            rank=rank,
            gram_logdet=gram_logdet,
            condition_number=condition_number,
            n_rows=n_rows,
            column_terms=self._column_terms(t),
            mask=mask,
        )

    def _column_terms(self, t: NDArray[np.float64]) -> tuple[str, ...]:
        """Return the term class name behind each design column.

        Counted from each term's OWN `columns(t)` width rather than assuming
        one column per term: `Harmonic` contributes two.

        Args:
            t: Time axis, shape (N,).

        Returns:
            One name per column, length `n_beta`.
        """
        names: list[str] = []
        for term in self.terms:
            width = int(np.shape(term.columns(t))[1])
            names.extend([type(term).__name__] * width)
        return tuple(names)

    @staticmethod
    def _restricted_singular_values(
        x: NDArray[np.float64], mask: NDArray[np.bool_]
    ) -> NDArray[np.float64]:
        """Singular values of each series' restricted design, shape (B, k).

        ZEROING A ROW AND DELETING IT GIVE THE SAME GRAM, hence the same
        non-zero singular values: `(M X)'(M X) = X_r' X_r` for `M = diag(mask)`.
        So one batched `svdvals` of `X[None] * mask[..., None]` serves the whole
        batch without materializing B differently-shaped submatrices, and a
        series keeping fewer rows than columns simply picks up structural zeros
        -- which is the correct answer, not an error.

        THREE TIERS, cheapest first, because the batched route allocates
        `B * N * k * 8` bytes (320 MB at B = 10^4, N = 10^3, k = 4) and the two
        degenerate mask patterns are the common ones:

          1. The mask keeps every row for every series: one SVD of X itself.
          2. Every series shares one mask: one SVD of the zero-masked design.
          3. Masks differ: a batched SVD **per `SVD_CHUNK_SERIES` block**, which
             is what bounds the temporary -- see that constant for the measured
             runtime trade and for the 1.49 GB it replaces at the worked example.

        The result is padded to width `n_beta` so callers can index `[:, -1]`
        for the smallest singular value even when `N < k` (`svdvals` returns
        only `min(N, k)` values, so a "wide" design's structurally-zero values
        never appear in that array at all -- reading s_min from the ones that
        DO appear would silently miss the singularity).

        Args:
            x: The shared design matrix, shape (N, k) with k >= 1.
            mask: Presence mask, shape (B, N).

        Returns:
            Descending singular values per series, shape (B, k).
        """
        batch, n_beta = mask.shape[0], x.shape[-1]
        # READ AT CALL TIME, not bound as a default: a module-level default is
        # captured at import and a test that sets the constant would be patching
        # something nothing reads.
        step = max(int(SVD_CHUNK_SERIES), 1)
        if bool(mask.all()):
            values = np.linalg.svdvals(x)[None, :]
        elif bool(np.array_equal(mask, np.broadcast_to(mask[0], mask.shape))):
            values = np.linalg.svdvals(x * mask[0][:, None])[None, :]
        else:
            # CHUNKED, so the temporary is `SVD_CHUNK_SERIES * N * k * 8` rather
            # than `B * N * k * 8`. Each block's matrices are decomposed
            # independently by LAPACK, so this is the same arithmetic in the same
            # order and the values are bit-for-bit what one call returns; the
            # test asserts that rather than assuming it.
            blocks = [
                np.linalg.svdvals(x[None, :, :] * mask[start : start + step, :, None])
                for start in range(0, batch, step)
            ]
            values = blocks[0] if len(blocks) == 1 else np.concatenate(blocks)
        if values.shape[1] < n_beta:
            values = np.pad(values, ((0, 0), (0, n_beta - values.shape[1])))
        return np.asarray(np.broadcast_to(values, (batch, n_beta)), dtype=np.float64)

    @staticmethod
    def _diagnostics(
        values: NDArray[np.float64],
    ) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.int64]]:
        """cond(X_r), log|X_r'X_r| and rank(X_r) from one stack of singular values.

        `log|X'X| = 2 * sum(log(s))` exactly, for any X: `X'X = V diag(s^2) V'`
        is a similarity transform of `diag(s^2)`, whose determinant is
        `prod(s^2)` regardless of the orthogonal U used to build X. THIS IS NOT
        `slogdet(X'X)` ON PURPOSE -- forming the Gram squares the condition
        number and `slogdet`'s LU factorization inherits that loss: measured
        (Task 7) at +3.20 nats of error at cond(X) = 1e9 and +8.58 at 1e10,
        both silently finite, and at cond(X) = 1e9 one fixed-seed construction
        made `slogdet` return a spurious NEGATIVE sign for a genuinely positive
        semidefinite Gram.

        Args:
            values: Descending singular values per series, shape (B, k),
                already padded to the full column count by
                `_restricted_singular_values` so `[:, -1]` is the true
                smallest singular value even for a "wide" design.

        Returns:
            (condition_number, gram_logdet, rank), each shape (B,).

            `gram_logdet` IS -inf ONLY WHERE X_r IS EXACTLY SINGULAR (a
            smallest singular value of exactly zero: an all-zero column, or
            more columns than unmasked rows). A design that is merely
            NUMERICALLY deficient -- its smallest singular value clears zero
            but falls below `X_RANK_RTOL` -- keeps a finite, if very negative,
            determinant, because that is its true value: singular values
            [1, 1e-2, 1e-11] give rank 2 of 3 with log|X'X| = -59.9, not -inf.
            Gating the determinant on `rank == n_beta` instead would report
            -inf for a matrix whose determinant is genuinely nonzero. **The
            caller's gate for RANK_DEFICIENT_X is `rank`, never this field.**
            The condition number is +inf in exactly the same cases.
        """
        largest = values[:, :1]
        rank = np.asarray((values > X_RANK_RTOL * largest).sum(axis=1), dtype=np.int64)
        nonsingular = values[:, -1] > 0.0
        with np.errstate(divide="ignore", invalid="ignore"):
            gram_logdet = np.where(
                nonsingular,
                2.0 * np.log(np.where(values > 0.0, values, 1.0)).sum(axis=1),
                -np.inf,
            )
            condition_number = np.where(
                nonsingular, values[:, 0] / values[:, -1], np.inf
            )
        return (
            np.asarray(condition_number, dtype=np.float64),
            np.asarray(gram_logdet, dtype=np.float64),
            rank,
        )

    @staticmethod
    def _condition_number(x: NDArray[np.float64]) -> float:
        """cond(X) = s_max / s_min from X's own singular values.

        Not the Gram's -- see `X_RANK_RTOL`'s docstring. Infinite where X has
        more columns than rows: `np.linalg.svdvals` returns only
        `min(n_rows, n_cols)` values, so a "wide" X's `n_cols - n_rows`
        structurally-zero singular values never appear in that array at all,
        and reading s_min from the values that ARE returned would silently
        miss the singularity -- measured before this fix: n=2, k=3 returned a
        finite cond ~2.0, contradicting `rank(2) < n_beta(3)`. Also infinite
        where the smallest RETURNED singular value is exactly zero (e.g. an
        all-zero column, distinct from the more-columns-than-rows case above).
        Kept as a standalone method (used directly by
        `test_condition_number_infinite_for_more_columns_than_rows`) even
        though `design_info`'s hot path routes through
        `_restricted_singular_values` and `_diagnostics` instead, which share
        one decomposition across cond, log|X'X| and rank, to avoid paying for
        it twice.
        """
        if x.shape[0] < x.shape[1]:
            return float("inf")
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


# ---------------------------------------------------------------------------
# The config vocabulary
# ---------------------------------------------------------------------------
#
# **THE FACTORIES LIVE BESIDE THEIR CLASSES, NOT IN THE PARSER.** Each one owns
# the knowledge of whether it takes an argument and what that argument means, so
# adding a parameter to a term cannot leave a table in another module stale.
#
# **`Regressor`, `ExpDecay` AND `LogDecay` ARE DELIBERATELY NOT REGISTERED.**
# `Regressor` needs a numpy column, which is the per-point regressor regime
# refused at layer 3; `ExpDecay` and `LogDecay` are nonlinear and their
# `columns()` raises, naming Phase 4. Registering them under a name a config can
# reach would turn a refusal that belongs at layer 3 into an exception raised
# inside the design build, inside the tile loop, ten hours in.


def _no_argument(kind: str, argument: str | None) -> None:
    """Refuse an argument for a term that takes none.

    Args:
        kind: The term's config name.
        argument: What followed the separator, if anything.

    Raises:
        ValueError: If an argument was supplied.
    """
    if argument is not None:
        raise ValueError(
            f"signal term {kind!r} takes no argument, got {argument!r}; "
            f"write {kind!r} on its own"
        )


def _epoch(kind: str, argument: str | None) -> float:
    """Read a required epoch in decimal years.

    Args:
        kind: The term's config name.
        argument: The text after the separator.

    Returns:
        The epoch.

    Raises:
        ValueError: If it is missing or not a number. Breakpoint epochs are
            user-supplied in v1 and detection is out of scope, so a missing one
            is a refusal rather than a default.
    """
    if argument is None:
        raise ValueError(
            f"signal term {kind!r} requires an epoch in decimal years, as "
            f"'{kind}:2005.5'. Breakpoint epochs are user-supplied in v1; "
            "detection is out of scope and is not silently approximated"
        )
    try:
        return float(argument)
    except ValueError as error:
        raise ValueError(
            f"signal term {kind!r} epoch {argument!r} is not a number; it is "
            "a decimal year, e.g. 2005.5"
        ) from error


@signal_registry.register("constant")
def _constant(argument: str | None = None) -> SignalTerm:
    """Build an intercept."""
    _no_argument("constant", argument)
    return Constant()


@signal_registry.register("trend")
def _trend(argument: str | None = None) -> SignalTerm:
    """Build a linear rate."""
    _no_argument("trend", argument)
    return Trend()


@signal_registry.register("accel")
def _accel(argument: str | None = None) -> SignalTerm:
    """Build a quadratic acceleration term."""
    _no_argument("accel", argument)
    return Accel()


@signal_registry.register("annual")
def _annual(argument: str | None = None) -> SignalTerm:
    """Build the annual cycle: TWO columns, cos and sin."""
    _no_argument("annual", argument)
    return Annual()


@signal_registry.register("semiannual")
def _semiannual(argument: str | None = None) -> SignalTerm:
    """Build the semiannual cycle: TWO columns, cos and sin."""
    _no_argument("semiannual", argument)
    return SemiAnnual()


@signal_registry.register("harmonic")
def _harmonic(argument: str | None = None) -> SignalTerm:
    """Build a harmonic pair at a stated period in years.

    Raises:
        ValueError: If the period is missing, unparseable or non-positive. A
            period of zero divides by zero inside `columns` and produces a
            design of NaNs with no crash.
    """
    period = _epoch("harmonic", argument)
    if period <= 0.0:
        raise ValueError(
            f"signal term 'harmonic' period {period} must be positive; the "
            "period is in years and divides the time axis"
        )
    return Harmonic(period=period)


@signal_registry.register("offset")
def _offset(argument: str | None = None) -> SignalTerm:
    """Build a unit step at a stated epoch."""
    return Offset(epoch=_epoch("offset", argument))


@signal_registry.register("rate_change")
def _rate_change(argument: str | None = None) -> SignalTerm:
    """Build a one-sided ramp from a stated epoch."""
    return RateChange(epoch=_epoch("rate_change", argument))


def k_beta(spec: SignalSpec, t: NDArray[np.float64]) -> int:
    """Return the design column count for a signal specification.

    **A COLUMN COUNT, NEVER A TERM COUNT.** `Harmonic` contributes two columns,
    so `["constant", "trend", "annual"]` is **three terms and k_beta = 4** --
    which is design doc 9.4's worked value. The wrong count is not even
    self-consistently wrong: it silently changes `tile_side` and every memory
    figure derived from it.

    Args:
        spec: The signal specification.
        t: The **real** time axis in decimal years. Not a synthetic probe: a
            one-sample axis makes `Trend`'s column identically zero and trips
            `Regressor`'s length check, so a probe would answer a different
            question than the one asked.

    Returns:
        The number of design columns.

    Note:
        `design_matrix` returns `(matrix, rank)`, and **the rank is not the
        column count** -- it is the numerical rank of the built design, which is
        smaller wherever the design is deficient. Taking the second element
        would give a `k_beta` that shrinks on a degenerate axis and a tile size
        that grows because of it.
    """
    matrix, _rank = spec.design_matrix(t)
    return int(matrix.shape[-1])
