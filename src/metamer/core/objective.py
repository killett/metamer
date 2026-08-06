"""Concentrated ML and REML objectives built on the filter's accumulator.

The augmented filter returns A = sum_t v_t v_t' / S_t for the columns [y | X].
Partitioning A gives every quantity needed:

    A[0,0]   = y' Sigma^-1 y
    A[0,1:]  = y' Sigma^-1 X
    A[1:,1:] = X' Sigma^-1 X

so beta_hat, the residual sum of squares, the beta covariance and the REML
penalty all follow from one filter pass and a small Cholesky.

REML CONVENTION (pinned; do not change without updating the oracle).
--------------------------------------------------------------------
This module implements the Harville (1974) form, which is invariant to the
choice of error-contrast basis:

    l_R = -0.5 * [ (n - rank(X)) log(2 pi)
                   + log|Sigma|
                   + log|X' Sigma^-1 X|
                   - log|X' X|
                   + y' P y ]

with P = Sigma^-1 - Sigma^-1 X (X' Sigma^-1 X)^-1 X' Sigma^-1. Relative to the
concentrated ML value l_c = -0.5 [n log(2pi) + log|Sigma| + y'Py] that is

    l_R = l_c + 0.5 * rank(X) * log(2 pi) + 0.5 * log|X'X| - 0.5 * log|X' Sigma^-1 X|

The two correction terms beyond the penalty are CONSTANT IN THETA, so they
cancel in delta-IC and every selection decision is unaffected by omitting them.
That is exactly what makes omitting them dangerous: no in-repo differential test
can see it. They matter because (a) log_lik is stored as an auditable primitive
and would be wrong in absolute terms, and (b) the Hector / CATS / est_noise
cross-validation compares absolute REML values, where an unexplained constant is
unattributable between "different convention" and "implementation bug" -- the
precise ambiguity the exact power-law path exists to eliminate.

EVERY QUANTITY IN THAT FORMULA IS PER SERIES. `n`, `Sigma`, `X`, `rank(X)` and
`log|X'X|` all refer to the design and covariance RESTRICTED TO ONE SERIES'
UNMASKED ROWS, because that is what the filter accumulates. Using the
batch-level `DesignInfo.gram_logdet` and `DesignInfo.rank` for a gapped series
is wrong by `0.5 * (log|X'X| - log|X_r'X_r|)`, which is again theta-free and so
again invisible to every differential test -- the same defect class as a wrong
constant, one level down. Since auditability is the entire reason an absolute
`log_lik` is stored, and real data always has gaps, that is not a corner case.
See `restricted_design_terms`, which computes the per-series pair (and takes the
precomputed batch-level value only when the mask keeps every row, where the two
are the same number).

OPEN: verify which convention Hector uses and record it in the design doc. If it
differs, the cross-validation carries a documented offset, not a mystery.

SIGMA-SQUARED IS NOT PROFILED OUT (deliberate).
-----------------------------------------------
Standard GLS profiles the overall noise scale analytically, dropping p by one
and improving conditioning, and most of the geodesy literature does so. This
package does not, because a composite kernel has a scale per term (white sigma,
matern12 sigma, matern32 sigma) and there is no single sigma^2 to profile
without reparameterizing as an overall amplitude times a simplex of per-term
weights. That is a CROSS-TERM SHARED PARAMETER, and Phase 1 implements no
sharing mechanism (see `terms.free_param_index`, which refuses such specs).

Consequence to keep in view: this is a real comparability difference against
Hector, on top of the REML convention above. Revisit when shared parameters
land; it is a Phase 3+ change to the kernel algebra, not a flag flip.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.linalg import LinAlgError
from numpy.typing import NDArray

from metamer.core.capability import Objective
from metamer.core.engines.kalman import _RANK_RTOL
from metamer.core.engines.protocol import Engine
from metamer.core.outcomes import Outcome, outcome_array
from metamer.core.params import ParamSpec
from metamer.core.signal import X_RANK_RTOL, DesignInfo
from metamer.core.statespace import StateSpace
from metamer.core.terms import ProcessSpec, free_param_index

CONDITION_LOG_LIMIT = 6.907755278982137
"""Largest log cond(X_w) tolerated before X'Sigma^-1X reads as ILL_CONDITIONED_X.

Natural log, stated in the WHITENED DESIGN's units: the diagnostic is

    log cond(X_w) = 0.5 * (log s_max - log s_min)

over the singular values of the accumulated Gram `X' Sigma^-1 X`, halved
because the Gram's singular values are the SQUARES of X_w's. That is exactly
the construction `kalman._RANK_RTOL`'s docstring prescribes for separating
"barely identified" from "singular" at a finer scale than the rank cutoff --
derived from the Gram's own singular values, not from a diagonal proxy. An
earlier draft used an AM-GM bound on the diagonal (`k log(tr(A)/k) - log|A|`),
which is scale-free only in the sense of being blind: it cannot distinguish a
column with two supporting samples from one with twenty, since both enter the
trace at their own scale.

VALUE: log(1e3) = 6.9078, i.e. cond(X_w) = 1000. The worst-determined direction
then has 1e6 times the variance of the best-determined one, and the solve has
lost about three of its sixteen digits.

REACHABILITY, which the value it replaced did not have. `kalman._RANK_RTOL`
declares the Gram rank-deficient at s_min/s_max = 1e-10, i.e. at
cond(X_w) = 1e5, i.e. at log cond(X_w) = 11.5129. Any limit at or above that is
NEVER RETURNED -- the rank test fires first and the series comes back
RANK_DEFICIENT_X -- so ILL_CONDITIONED_X would be dead code. The brief's 30.0
(applied as k * 30 = 90 nats, cond(X_w) ~ 1e39) was three times past the point
of unreachability. This value sits 4.6 nats below the cutoff.

CALIBRATED ON ONE SYNTHETIC CASE, named here with its measured numbers so the
next person can re-run it. `tests/test_objective.py::_gapped_setup`: 60 daily
samples on a decimal-years axis, design [Constant, Trend, Offset(day 40),
RateChange(day 40)] -- a coseismic step plus a postseismic rate change, the
ordinary reason a geodetic design carries both at one epoch -- with
theta = (matern12 sigma 0.4, rho 1.2, white sigma 6.0). Measured through the
engine's own accumulated Gram:

    rows   post-break samples   cond(X_w)    log cond(X_w)   s_min/s_max (Gram)
      42          20              141.1         4.9495          5.023e-05
      42           2             3085.4         8.0344          1.050e-07
      40           0              inf           inf             0.0

The first two rows KEEP THE SAME NUMBER OF SAMPLES, so what separates them is
the offset's support, not the sample count. The limit sits between them with a
factor of 7.1 below and 3.1 above (1.96 and 1.13 nats), and the ill-conditioned
case still sits three decades above the rank cutoff -- which is what keeps
RANK_DEFICIENT_X (a term with no support at all, exactly singular) and
ILL_CONDITIONED_X (a term identified by a handful of samples) distinct
outcomes. Which one happened where is the point of the failure map.

ONE SYNTHETIC POINT IS BOOTSTRAPPING A THRESHOLD THAT HAS TO GENERALIZE, and it
is worth being explicit about which way the error falls. cond(X_w) is not
invariant to column scaling, and `signal.py` deliberately does not rescale
columns (doing so would shift `gram_logdet` and corrupt the REML term). So the
raw condition number of a WELL-supported design still grows with the record's
time span, because the trend column's norm does: measured on full-support
[Constant, Trend, Accel, Annual, SemiAnnual] over monthly data,
cond(X_w) = 2.8 (5 yr), 33.9 (20 yr), 76.0 (30 yr), 210.6 (50 yr), 840.7
(100 yr); and on full-support [Constant, Trend, Offset] over annual data, 26.1
(20 yr), 77.9 (60 yr), 129.8 (100 yr). All clear 1000 -- but the century-long
record with an acceleration term clears it by 0.17 nats, so a ~110-year record
with that design would be flagged on a design that is perfectly well supported.
THE ERROR THEREFORE FALLS TOWARD
FALSE ILL_CONDITIONED_X ON VERY LONG, WELL-SUPPORTED RECORDS, not toward
missing a genuinely unidentified term -- and the failure is loud (a named
outcome on the map) rather than a silently wrong fit. Recalibrate against a
real record before Phase 2, and if the false-positive direction bites, the fix
is a scale-aware diagnostic, not a bigger constant.

THE DIAGNOSTIC IS THETA-DEPENDENT, because the Gram is. The same mask on the
same design classifies differently at different noise parameters: at
theta = (2.0, 0.1, 0.5) the two-post-break case above measures
cond(X_w) = 437, i.e. OK. That is correct -- identifiability really is a
property of X' Sigma^-1 X, not of X alone -- but it means a series can change
outcome as the optimizer walks, so Task 13 must treat the resulting NaN as a
barrier and record the outcome at the FINAL theta, not the first one it saw.
"""

_NEGATIVE_REDUCTION_RTOL = 1e-6
"""Relative size of a residual-reduction excursion below zero that is not rounding."""


@dataclass(frozen=True)
class GlsResult:
    """Everything one Cholesky of X' Sigma^-1 X yields, computed once.

    Attributes:
        beta: GLS estimates, shape (B, k).
        beta_cov: Their covariance (X' Sigma^-1 X)^-1, shape (B, k, k). This is
            the reported trend uncertainty -- the headline scientific output of
            the package -- so it comes from a triangular solve against the
            identity, never from `np.linalg.inv`.
        logdet: log|X' Sigma^-1 X|, shape (B,).
        rss_reduction: y' Sigma^-1 X (X' Sigma^-1 X)^-1 X' Sigma^-1 y, shape (B,).
        outcome: PER-SERIES outcome codes, shape (B,) uint8. Not a scalar: one
            rank-deficient grid point must not mark the other 9,999 as failed.
    """

    beta: NDArray[np.float64]
    beta_cov: NDArray[np.float64]
    logdet: NDArray[np.float64]
    rss_reduction: NDArray[np.float64]
    outcome: NDArray[np.uint8]


@dataclass(frozen=True)
class ObjectiveResult:
    """One objective evaluation, with everything the driver needs downstream.

    Attributes:
        loglik: Objective value per series, shape (B,). **NaN** where `outcome`
            is not OK -- not -inf. The store's status invariant is bidirectional
            (non-OK implies NaN in the value slots), and -inf is a
            finite-looking sentinel that survives some consumers' checks and
            poisons a downstream mean. -inf is the optimizer's internal barrier
            value only, applied at `optimize_series`, never here.
        gls: The GLS solve, or None when there is no design matrix.
        outcome: PER-SERIES outcome codes, shape (B,) uint8. This is the MERGE
            of the engine's verdict with this module's own -- see
            `merge_outcomes`. It is never a replacement: an INSUFFICIENT_DATA
            series relabelled NONFINITE_OBJECTIVE would turn land and permanent
            ice into failures and inflate the very denominator that
            `Outcome.is_eligible` exists to protect.
        n_used: Unmasked observation count per series, shape (B,). Valid even
            for a failed series, including on the design-precheck path, and
            carries no sentinel -- the same contract as `ScoredResult.n_used`.
        rank_x: Numerical rank of the accumulated `X' Sigma^-1 X` PER SERIES,
            shape (B,) int64, carried through from the engine. NOT the scalar
            `DesignInfo.rank`: a gap that removes every row supporting a column
            drops that series' effective rank alone, and Task 9's REML
            effective sample size `n_obs - rank(X)` is computed per series.

            **-1 where `outcome` is not OK**, meaning "not computed", exactly as
            on `ScoredResult` so the two objects cannot be read under different
            conventions. CHECK `outcome` FIRST: -1 is a clean comparison but is
            NOT fail-loud under arithmetic -- `n_obs - rank_x` at -1 yields
            `n_obs + 1`, a sample size larger than the number of observations,
            which looks entirely plausible in BIC.
    """

    loglik: NDArray[np.float64]
    gls: GlsResult | None
    outcome: NDArray[np.uint8]
    n_used: NDArray[np.int64]
    rank_x: NDArray[np.int64]


_MORE_SPECIFIC = (Outcome.RANK_DEFICIENT_X.code, Outcome.ILL_CONDITIONED_X.code)


def merge_outcomes(
    engine: NDArray[np.uint8], objective: NDArray[np.uint8]
) -> NDArray[np.uint8]:
    """Combine the engine's per-series verdict with this module's own.

    MERGE, NEVER REPLACE. The engine has already classified each series, and
    two of its verdicts are more informative than anything this module can say
    about the same series:

      * INSUFFICIENT_DATA (all-masked: land, permanent ice) is an EXPECTED
        outcome. `is_failure` is False and `is_eligible` is False, so it is
        excluded from the failure-rate denominator of design doc section 8.6.
        The engine poisons such a series' accumulator to NaN, so this module's
        independent view of it is "non-finite" -- and taking that view would
        relabel every land point a failure and inflate precisely the
        denominator the exclusion protects.
      * NONFINITE_OBJECTIVE from a degenerate innovation variance says where
        the trouble started, which "rank deficient" would not.

    The one case that goes the other way is a strictly MORE SPECIFIC verdict:
    RANK_DEFICIENT_X and ILL_CONDITIONED_X name a cause where
    NONFINITE_OBJECTIVE only names a symptom, so they refine it. Nothing
    refines an expected outcome.

    Args:
        engine: Per-series codes from the engine, shape (B,) uint8.
        objective: Per-series codes from `gls_solution`, shape (B,) uint8.

    Returns:
        The merged per-series codes, shape (B,) uint8.
    """
    merged: NDArray[np.uint8] = np.asarray(engine, dtype=np.uint8).copy()
    refines = np.isin(objective, np.asarray(_MORE_SPECIFIC, dtype=np.uint8))
    replaceable = (merged == Outcome.OK.code) | (
        (merged == Outcome.NONFINITE_OBJECTIVE.code) & refines
    )
    merged[replaceable] = np.asarray(objective, dtype=np.uint8)[replaceable]
    return merged


def negative_reduction_mask(
    rss_reduction: NDArray[np.float64], quadratic: NDArray[np.float64]
) -> NDArray[np.bool_]:
    """Flag residual reductions that are negative by more than rounding.

    `rss_reduction = y'SX (X'SX)^-1 X'Sy` is a quadratic form in a positive
    definite matrix, so it is non-negative in exact arithmetic. The
    concentrated value is formed as `engine_loglik + 0.5 * rss_reduction`, a
    difference of two large positives, and a badly conditioned Gram can round
    the reduction slightly below zero. Nothing takes a log or a sqrt of it, so
    the worst case is a log-likelihood slightly too HIGH rather than a NaN --
    benign, and deliberately not flagged.

    A LARGE negative excursion is a different animal: it means the accumulator
    is not the matrix it claims to be, and the series would otherwise come back
    OK with an inflated likelihood. It is recorded as an outcome rather than
    raised, because raising for one series aborts a tile of 10^4.

    Args:
        rss_reduction: The residual reductions, shape (B,).
        quadratic: `y' Sigma^-1 y` per series, the natural scale to measure
            against, shape (B,).

    Returns:
        True where the reduction is negative beyond tolerance, shape (B,).
    """
    scale = np.maximum(np.abs(quadratic), 1.0)
    with np.errstate(invalid="ignore"):
        flagged = rss_reduction < -_NEGATIVE_REDUCTION_RTOL * scale
    return np.asarray(flagged & np.isfinite(rss_reduction), dtype=np.bool_)


def _terms_from_singular_values(
    values: NDArray[np.float64], n_beta: int
) -> tuple[NDArray[np.float64], NDArray[np.int64]]:
    """Turn a stack of design singular values into (log|X'X|, rank).

    `log|X'X| = 2 sum log s` exactly, for any X: `X'X = V diag(s^2) V'`. This is
    NOT `slogdet(X'X)` on purpose -- forming the Gram squares the condition
    number, and at cond(X) = 1e9 `slogdet` has been measured (Task 7) returning
    a NEGATIVE sign for a genuinely positive semidefinite Gram, which would
    yield -inf and a spurious RANK_DEFICIENT_X for a full-rank design.

    Args:
        values: Singular values, shape (B, m) with m <= n_beta, descending.
        n_beta: Number of design columns.

    Returns:
        (log|X'X| per series, rank per series). The determinant is -inf for any
        series whose rank falls short of `n_beta`, which is the true value.
    """
    largest = values[:, :1]
    rank = np.asarray((values > X_RANK_RTOL * largest).sum(axis=1), dtype=np.int64)
    full = rank == n_beta
    with np.errstate(divide="ignore", invalid="ignore"):
        logdet = np.where(
            full, 2.0 * np.log(np.where(values > 0.0, values, 1.0)).sum(axis=1), -np.inf
        )
    return np.asarray(logdet, dtype=np.float64), rank


def restricted_design_terms(
    design: DesignInfo, mask: NDArray[np.bool_]
) -> tuple[NDArray[np.float64], NDArray[np.int64]]:
    """Return per-series `log|X_r'X_r|` and `rank(X_r)` for the masked design.

    X_r is X restricted to one series' unmasked rows -- the design that
    actually enters `X' Sigma^-1 X`, and therefore the one Harville's
    basis-invariance term and rank constant refer to.

    THREE TIERS, cheapest first:

      1. The mask keeps every row. X_r IS X, so the precomputed
         `DesignInfo.gram_logdet` and `DesignInfo.rank` are returned unchanged
         and nothing is decomposed. This is the "computed once on DesignInfo"
         path, and it is the common case for a gap-free record.
      2. Every series shares the same mask. One SVD of the restricted design
         serves the whole batch.
      3. Masks differ. One batched SVD of the ZERO-MASKED design
         `X[None] * mask[..., None]`, whose non-zero singular values are
         exactly those of each X_r (zeroing a row and deleting it give the same
         Gram, hence the same singular values plus structural zeros).

    COST OF TIER 3, for Task 17's budget. It allocates `B * N * k_beta * 8`
    bytes -- 320 MB at B = 10^4, N = 10^3, k = 4, which is the same
    `N * k_beta * 8`-per-series term `DesignInfo`'s Phase 2 note already flags
    as dominating -- and costs O(B N k^2) per call. Both are avoidable by
    chunking the batch. More importantly the result is THETA-FREE: it depends
    only on (design, mask), so Task 14 should compute it once per fit rather
    than once per objective evaluation, or the ~50 evaluations an optimizer
    takes multiply it by 50. It is computed here, not cached here, because this
    module does not own the fit loop.

    Args:
        design: The built design matrix and its theta-free quantities.
        mask: Presence mask, shape (B, N).

    Returns:
        (log|X_r'X_r|, rank(X_r)), both shape (B,). The determinant is -inf
        where the restricted design is rank deficient.
    """
    if design.per_point:
        raise NotImplementedError(
            "per-point designs are Phase 2; restricted_design_terms assumes (N, k)"
        )
    x = np.asarray(design.matrix, dtype=np.float64)
    batch = mask.shape[0]
    n_beta = design.n_beta

    if bool(mask.all()):
        return (
            np.full(batch, design.gram_logdet, dtype=np.float64),
            np.full(batch, design.rank, dtype=np.int64),
        )

    first = mask[0]
    if bool(np.array_equal(mask, np.broadcast_to(first, mask.shape))):
        shared = np.linalg.svdvals(x[first])[None, :]
        logdet, rank = _terms_from_singular_values(shared, n_beta)
        return np.repeat(logdet, batch), np.repeat(rank, batch)

    restricted = x[None, :, :] * mask[:, :, None].astype(np.float64)
    return _terms_from_singular_values(np.linalg.svdvals(restricted), n_beta)


def gls_solution(accum: NDArray[np.float64]) -> GlsResult:
    """Solve the profiled generalized least squares problem, once.

    One Cholesky yields beta, beta_cov, the log-determinant and the residual
    reduction. An earlier draft factorized the same k x k system four times
    (cholesky, solve, inv, then another solve in the caller) and discarded beta
    and beta_cov -- the two quantities the package exists to produce.

    Args:
        accum: Accumulated whitened cross-products, shape (B, 1+k, 1+k), with
            block structure [[y'Sy, y'SX], [X'Sy, X'SX]] where S = Sigma^-1.

    Returns:
        A GlsResult. On a singular, ill-conditioned or non-finite system the
        arrays are filled with NaN and `outcome` names the failure; the caller
        must not treat a non-OK outcome as a usable fit.
    """
    xtx = accum[:, 1:, 1:]
    xty = accum[:, 1:, 0]
    batch, k = xty.shape

    beta = np.full((batch, k), np.nan)
    beta_cov = np.full((batch, k, k), np.nan)
    logdet = np.full(batch, np.nan)
    rss_reduction = np.full(batch, np.nan)
    outcome = outcome_array(batch, Outcome.OK)

    finite = np.isfinite(xtx).all(axis=(1, 2)) & np.isfinite(xty).all(axis=1)
    outcome[~finite] = Outcome.NONFINITE_OBJECTIVE.code

    # slogdet is batched AND non-raising, unlike cholesky, which raises for the
    # whole stack if any single member is not positive definite. Classifying
    # validity here -- before any factorization -- is what keeps one bad grid
    # point from failing its 9,999 neighbours.
    with np.errstate(invalid="ignore", divide="ignore"):
        sign, log_abs_det = np.linalg.slogdet(xtx)

    # Conditioning from the GRAM'S OWN SINGULAR VALUES, as `kalman._RANK_RTOL`
    # prescribes, halved to state it in the whitened design's units. svdvals
    # raises for the whole stack on a non-finite member, so it sees only the
    # finite subset -- the same classify-first rule as above.
    values = np.zeros((batch, k), dtype=np.float64)
    if finite.any():
        values[finite] = np.linalg.svdvals(xtx[finite])
    with np.errstate(divide="ignore", invalid="ignore"):
        log_cond = 0.5 * (np.log(values[:, 0]) - np.log(values[:, -1]))

    positive_definite = (sign > 0) & np.isfinite(log_abs_det)
    full_rank = values[:, -1] > _RANK_RTOL * values[:, 0]
    singular = finite & ~(positive_definite & full_rank)
    ill = finite & ~singular & (log_cond > CONDITION_LOG_LIMIT)
    valid = finite & ~singular & ~ill
    outcome[singular] = Outcome.RANK_DEFICIENT_X.code
    outcome[ill] = Outcome.ILL_CONDITIONED_X.code

    if not valid.any():
        return GlsResult(beta, beta_cov, logdet, rss_reduction, outcome)

    index = np.flatnonzero(valid)
    sub = xtx[index]
    try:
        lower = np.linalg.cholesky(sub)
    except LinAlgError:
        # Backstop for the marginally positive-definite case: identify the
        # offending members individually rather than failing the whole subset.
        keep = np.ones(index.size, dtype=bool)
        factors = np.full((index.size, k, k), np.nan)
        for position in range(index.size):
            try:
                factors[position] = np.linalg.cholesky(sub[position])
            except LinAlgError:
                keep[position] = False
        outcome[index[~keep]] = Outcome.RANK_DEFICIENT_X.code
        index = index[keep]
        if index.size == 0:
            return GlsResult(beta, beta_cov, logdet, rss_reduction, outcome)
        lower = factors[keep]

    upper = np.swapaxes(lower, -1, -2)
    logdet[index] = 2.0 * np.log(np.diagonal(lower, axis1=-2, axis2=-1)).sum(axis=-1)

    # Two triangular solves reuse the one factorization. At k ~ 4 the cost of
    # not exploiting triangularity is irrelevant; avoiding a second
    # factorization -- and avoiding np.linalg.inv for beta_cov -- is not.
    sub_beta = np.linalg.solve(upper, np.linalg.solve(lower, xty[index][..., None]))[
        ..., 0
    ]
    eye = np.broadcast_to(np.eye(k), (index.size, k, k))
    beta[index] = sub_beta
    beta_cov[index] = np.linalg.solve(upper, np.linalg.solve(lower, eye))
    rss_reduction[index] = np.einsum("bi,bi->b", xty[index], sub_beta)

    # Unconditional rather than guarded by `bad.any()`: every assignment below
    # is a no-op on an empty mask, and the guard would be a branch no test can
    # reach -- the form is non-negative for any matrix that survived the
    # classification above, which is exactly why this is a backstop and not a
    # code path (see `negative_reduction_mask`).
    bad = negative_reduction_mask(rss_reduction, accum[:, 0, 0]) & valid
    outcome[bad] = Outcome.NONFINITE_OBJECTIVE.code
    beta[bad] = np.nan
    beta_cov[bad] = np.nan
    logdet[bad] = np.nan
    rss_reduction[bad] = np.nan

    return GlsResult(beta, beta_cov, logdet, rss_reduction, outcome)


@dataclass(frozen=True)
class ConcentratedObjective:
    """The objective the optimizer sees, in natural or unconstrained units."""

    spec: ProcessSpec
    state_space: StateSpace
    engine: Engine
    objective: Objective

    def check_design(self, design: DesignInfo, batch: int) -> NDArray[np.uint8]:
        """Classify the design matrix before it reaches the likelihood.

        THIS CHECK IS NECESSARY BUT NOT SUFFICIENT. It sees only the global
        rank of X. The design that actually enters X' Sigma^-1 X for a given
        series is X RESTRICTED TO THAT SERIES' UNMASKED ROWS, because the filter
        accumulates only over unmasked epochs -- so effective rank is per-series
        whenever masks differ, which in real gridded data is always. A shared,
        globally full-rank X still yields a singular system for any series whose
        gaps remove all support for one of its columns. `gls_solution` is what
        catches that, per series.

        Returns the per-series form for the same reason: a scalar that later has
        to be broadcast is exactly how a per-series concept gets implemented at
        batch granularity.

        Args:
            design: The built design matrix and its derived quantities.
            batch: Number of series.

        Returns:
            Per-series outcome codes, shape (B,).
        """
        if design.is_deficient or not np.isfinite(design.gram_logdet):
            return outcome_array(batch, Outcome.RANK_DEFICIENT_X)
        return outcome_array(batch, Outcome.OK)

    def loglik(
        self,
        theta: NDArray[np.float64],
        y: NDArray[np.float64],
        mask: NDArray[np.bool_],
        t: NDArray[np.float64],
        design: DesignInfo | None,
    ) -> NDArray[np.float64]:
        """Return the concentrated log-likelihood per series.

        Under ML the envelope theorem applies exactly: beta_hat is a stationary
        point, so d loglik / d theta needs no d beta_hat / d theta term. Under
        REML the penalty is NOT covered by that argument, which is why
        analytic REML gradients are strictly more work.

        Args:
            theta: Noise parameters in natural units, shape (B, p_free).
            y: Observations, shape (B, N).
            mask: Presence mask, shape (B, N).
            t: Shared time axis, shape (N,).
            design: The built design matrix and its theta-free quantities, or
                None. Carrying a DesignInfo rather than a loose (matrix, rank)
                pair is what lets per-point regressors widen the shapes in
                Phase 2 without a signature rewrite.

        Returns:
            Log-likelihood per series, shape (B,), NaN where the fit failed.
        """
        return self.evaluate(theta, y, mask, t, design).loglik

    def evaluate(
        self,
        theta: NDArray[np.float64],
        y: NDArray[np.float64],
        mask: NDArray[np.bool_],
        t: NDArray[np.float64],
        design: DesignInfo | None,
    ) -> ObjectiveResult:
        """Evaluate the objective and return everything one pass produces.

        The fit driver consumes `gls.beta` and `gls.beta_cov` from here rather
        than running a second filter pass to recover them.

        Args:
            theta: Noise parameters in natural units, shape (B, p_free).
            y: Observations, shape (B, N).
            mask: Presence mask, shape (B, N).
            t: Shared time axis, shape (N,).
            design: The built design matrix, or None.

        Returns:
            An ObjectiveResult whose `loglik` is NaN for every series whose
            `outcome` is not OK, and whose `outcome` is the MERGE of the
            engine's per-series verdict with this module's own. The caller must
            record the outcome rather than treating the value as a fit.
        """
        y = np.asarray(y, dtype=np.float64)
        mask = np.asarray(mask, dtype=bool)
        batch = y.shape[0]

        # Rank deficiency is classified BEFORE any factorization: a singular
        # X' Sigma^-1 X would otherwise reach cholesky, which raises for the
        # WHOLE STACK if any one member is not positive definite.
        matrix: NDArray[np.float64] | None = None
        if design is not None and design.n_beta > 0:
            precheck = self.check_design(design, batch)
            if np.any(precheck != Outcome.OK.code):
                # n_used is a real count even here: the protocol pins it as the
                # one field that stays meaningful for a failed series. rank_x is
                # the -1 "not computed" sentinel, since nothing was factorized.
                return ObjectiveResult(
                    np.full(batch, np.nan),
                    None,
                    precheck,
                    np.count_nonzero(mask, axis=1).astype(np.int64),
                    np.full(batch, -1, dtype=np.int64),
                )
            matrix = design.matrix

        result = self.engine.score(
            self.state_space, self.hydrate(theta), y, mask, t, matrix, self.objective
        )
        if matrix is None or design is None:
            return ObjectiveResult(
                result.loglik, None, result.outcome, result.n_used, result.rank_x
            )

        gls = gls_solution(result.normal_equations)
        outcome = merge_outcomes(result.outcome, gls.outcome)
        ok = outcome == Outcome.OK.code
        rank_x = np.where(ok, result.rank_x, -1).astype(np.int64)

        concentrated = np.where(ok, result.loglik + 0.5 * gls.rss_reduction, np.nan)
        if self.objective is Objective.ML:
            return ObjectiveResult(concentrated, gls, outcome, result.n_used, rank_x)

        # REML, Harville form -- see the module docstring. The two terms beyond
        # the penalty are constant in theta and cancel in delta-IC, which is
        # exactly why their absence cannot be detected by a differential test.
        # Both belong to the RESTRICTED design, not the batch-level one.
        gram_logdet, rank = restricted_design_terms(design, mask)
        reml = np.where(
            ok,
            concentrated
            + 0.5 * rank.astype(np.float64) * np.log(2.0 * np.pi)
            + 0.5 * gram_logdet
            - 0.5 * gls.logdet,
            np.nan,
        )
        return ObjectiveResult(reml, gls, outcome, result.n_used, rank_x)

    def unconstrained_loglik(
        self,
        u: NDArray[np.float64],
        y: NDArray[np.float64],
        mask: NDArray[np.bool_],
        t: NDArray[np.float64],
        design: DesignInfo | None,
    ) -> NDArray[np.float64]:
        """Evaluate at unconstrained coordinates, mapping through bijectors."""
        return self.loglik(self.to_natural(u), y, mask, t, design)

    def hydrate(self, theta_free: NDArray[np.float64]) -> NDArray[np.float64]:
        """Expand a free-parameter vector to the full per-term layout.

        `StateSpace` slices `theta` over ALL of a term's parameters, including
        frozen ones, so the optimizer's free-only vector must be widened with
        the pinned defaults before it reaches any family. Without this a spec
        with a fixed parameter either raises on a shape mismatch or -- worse --
        silently shifts every subsequent parameter one slot to the left, which
        converges happily to a fit of a different model.

        Args:
            theta_free: Natural-units free parameters, shape (B, p_free).

        Returns:
            Natural-units full parameter matrix, shape (B, p_total).
        """
        arr = np.asarray(theta_free, dtype=np.float64)
        free = {
            pair: column
            for pair, column in zip(free_param_index(self.spec), arr.T, strict=True)
        }
        columns: list[NDArray[np.float64]] = []
        for label, term in zip(self.spec.labels(), self.spec.terms, strict=True):
            for name, spec in term.params.items():
                key = (label, name)
                if key in free:
                    columns.append(free[key])
                else:
                    columns.append(
                        np.full(arr.shape[0], spec.default, dtype=np.float64)
                    )
        return np.column_stack(columns)

    def _free_specs(self) -> tuple[ParamSpec, ...]:
        """Resolve the flat vector's ParamSpecs via the single source of truth.

        All three mappings below drive off `free_param_index` rather than each
        re-deriving the layout. Five separate copies of that nested loop existed
        in an earlier draft, two of them reading their order from different
        sources; divergence produces converged-looking fits at values
        interpreted differently in two places, with no exception raised.
        """
        by_label = dict(zip(self.spec.labels(), self.spec.terms, strict=True))
        return tuple(
            by_label[label].params[name] for label, name in free_param_index(self.spec)
        )

    def _map(self, values: NDArray[np.float64], method: str) -> NDArray[np.float64]:
        """Apply one bijector method column by column, in free-parameter order.

        Args:
            values: Parameter matrix, shape (B, p_free).
            method: `forward`, `inverse` or `dforward`.

        Returns:
            The mapped matrix, shape (B, p_free).

        Raises:
            ValueError: If the column count is not the number of FREE
                parameters -- a full-width vector arriving here means the
                caller derived the layout somewhere other than
                `free_param_index`.
        """
        arr = np.asarray(values, dtype=np.float64)
        specs = self._free_specs()
        if arr.shape[1] != len(specs):
            raise ValueError(
                f"parameter vector has {arr.shape[1]} columns but this spec has "
                f"{len(specs)} free parameters"
            )
        out = np.empty_like(arr)
        for index, spec in enumerate(specs):
            out[:, index] = getattr(spec.transform, method)(arr[:, index])
        return out

    def to_natural(self, u: NDArray[np.float64]) -> NDArray[np.float64]:
        """Map an unconstrained parameter matrix (B, p_free) to natural units."""
        return self._map(u, "forward")

    def to_unconstrained(self, theta: NDArray[np.float64]) -> NDArray[np.float64]:
        """Map a natural-units matrix (B, p_free) to unconstrained space."""
        return self._map(theta, "inverse")

    def dforward(self, u: NDArray[np.float64]) -> NDArray[np.float64]:
        """Return d(natural)/d(unconstrained) for the delta method."""
        return self._map(u, "dforward")
