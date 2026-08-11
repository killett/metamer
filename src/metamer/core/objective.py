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
UNMASKED ROWS, because that is what the filter accumulates. Using a
batch-level `log|X'X|` and `rank(X)` for a gapped series is wrong by
`0.5 * (log|X'X| - log|X_r'X_r|)`, which is again theta-free and so again
invisible to every differential test -- the same defect class as a wrong
constant, one level down. Measured on a 10-epoch gap: -95.7269 against the
oracle's -95.9113, the difference being exactly that half-difference to 13
digits. Since auditability is the entire reason an absolute `log_lik` is
stored, and real data always has gaps, that is not a corner case.

`DesignInfo` therefore carries `rank` and `gram_logdet` as `(B,)` arrays built
from the mask -- see `signal.DesignInfo`. THIS DOES NOT UNDO THE HOISTING: both
depend on (design, mask) and nothing else, both theta-free, so they are still
computed exactly once per fit at setup and this module only reads them.

`design.rank` IS NOT `ScoredResult.rank_x`. The first is `rank(X_r)`, a
property of the design alone, independent of Sigma, and it is the one Harville's
constant `(n - rank(X)) log 2 pi` refers to. The second is the rank of the
WHITENED Gram and depends on theta. `ObjectiveResult` carries BOTH, as
`design_rank` and `rank_x`, precisely because they answer different questions.

TASK 9 MUST COUNT WITH `design_rank`, not `rank_x`. REML's effective sample size
`n_obs - rank(X)` has to use the same rank the constant above was computed with,
or the counting is inconsistent with the likelihood it is counting for. An
earlier version of this paragraph directed Task 9 to `rank_x`, which was wrong
and was harmless only because the two agree on every path that produces a finite
value -- a deficient `X_r` fails its series before it is scored. Two quantities
that agree in practice and are documented as one are how an off-by-one reaches
BIC, so both are carried and both are named.

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
from metamer.core.signal import DesignInfo
from metamer.core.statespace import StateSpace
from metamer.core.terms import ProcessSpec, free_param_index

_EPS = float(np.finfo(np.float64).eps)

CONDITION_LOG_LIMIT: float = -0.25 * float(np.log(_EPS))
"""Largest log cond(X_w) tolerated before X'Sigma^-1X reads as ILL_CONDITIONED_X.

DERIVED FROM float64, NOT CALIBRATED AGAINST A FIXTURE. Tuning a production
threshold until a chosen test case fires is circular: it pins the constant to
whatever that case happens to measure -- usually its row count -- and tells you
nothing about any other design. Everything below follows from the arithmetic.

UNITS: the natural log of cond(X_w), where `X_w = Sigma^(-1/2) X_r` is the
WHITENED restricted design. Both limits in this module are stated in these
units so they are directly comparable; a threshold stated on the Gram is off by
a factor of two in the log, which is where most of the confusion about this
value came from. The diagnostic is computed from the accumulated Gram's own
singular values,

    log cond(X_w) = 0.5 * (log s_max - log s_min),

halved because the Gram's singular values are the SQUARES of X_w's. That is the
construction `kalman._RANK_RTOL`'s docstring prescribes. An earlier draft used
an AM-GM bound on the Gram's DIAGONAL (`k log(tr(A)/k) - log|A|`) as a
cheap-inside-the-loop proxy; this check runs once per fit at the optimum, not
per iteration, so the approximation bought nothing and cost accuracy.

THE DERIVATION. The GLS solve here runs on the NORMAL EQUATIONS -- the
accumulator IS `X'Sigma^-1X`, and `gls_solution` factorizes it with a Cholesky.
The forward error of that solve goes like `eps * cond(Gram)`, and
`cond(Gram) = cond(X_w)^2`, so the error goes like `eps * cond(X_w)^2`. Roughly
half the significant digits are gone when it reaches `sqrt(eps)`:

    eps * cond(X_w)^2 = sqrt(eps)   =>   cond(X_w) = eps^(-1/4) = 8192

giving `log cond(X_w) = 9.0109`. NOTE THE EXPONENT. The familiar `1/sqrt(eps) =
6.7e7` is the half-digit point for a solve performed on X_w ITSELF (a QR of the
whitened design); forming the Gram squares the condition number, so in cond(X_w)
units the boundary is the SQUARE ROOT of that. Stating it as 6.7e7 here would
put the ill-conditioned limit ABOVE the rank cutoff and make ILL_CONDITIONED_X
unreachable all over again -- the same factor-of-two-in-the-log mistake, one
level up. If the solve is ever changed to run on X_w directly, this exponent
changes with it.

THE LADDER IS ORDERED, and that is a module invariant, checked at import below
and pinned by `test_the_conditioning_ladder_is_ordered_and_derived_from_float64`:

    ILL_CONDITIONED at 9.0109 nats  (cond(X_w) = 8.19e3)
    RANK_DEFICIENT  at 11.5129 nats (cond(X_w) = 1.00e5)

a band 2.50 nats (a factor of 12.2) wide. The brief's value made this band
EMPTY: at `k * 30 = 90` nats, cond(X_w) ~ 1e39, the rank test fired first for
every design and ILL_CONDITIONED_X was dead code -- a named outcome the failure
map could never show.

WHAT THE FIXTURE IS FOR, now that it does not set this number. It shows the
band is REACHABLE by an actual masked design -- see
`test_the_fixture_lands_in_all_three_bands`, which measures where its three
cases fall and compares them to these constants rather than to pinned values.
It can be retuned freely; this constant does not move with it.

KNOWN LIMITATION, stated because the error direction matters. cond(X_w) is not
invariant to column scaling, and `signal.py` deliberately does not rescale
columns (doing so would shift `gram_logdet` and corrupt the REML term). The raw
condition number of a WELL-supported design therefore grows with the record's
span, because the trend and acceleration columns' norms do. So the error falls
toward FALSE ILL_CONDITIONED_X on very long, well-supported records rather than
toward missing a genuinely unidentified term -- and it is loud (a named outcome
on the map) rather than a silently wrong fit. If that direction bites, the fix
is a scale-aware diagnostic, not a bigger constant.

MEASURED, on FULL-SUPPORT designs at theta = (0.4, 1.2, 6.0), through the
engine's own accumulated Gram (reproduction recipe below). This is the only
quantitative check anyone has run on that false-positive direction, and it is
recorded here because it ARGUES FOR the derived constant over the calibrated
one it replaced. Margins are how far each case sits BELOW the limit, so larger
is safer:

    [Constant, Trend, Accel, Annual, SemiAnnual], monthly
      years   cond(X_w)      log   vs 8192 (derived)   vs 1e3 (calibrated)
          5       2.805   1.0314        +7.9795 nats          +5.8763 nats
         20       33.89   3.5231        +5.4878               +3.3846
         30       76.02   4.3310        +4.6799               +2.5767
         50       210.6   5.3502        +3.6608               +1.5576
        100       840.7   6.7342        +2.2767               +0.1735

    [Constant, Trend, Offset(midpoint)], annual
      years   cond(X_w)      log   vs 8192 (derived)   vs 1e3 (calibrated)
         20       26.12   3.2625        +5.7484 nats          +3.6452 nats
         60       77.88   4.3552        +4.6557               +2.5525
        100       129.8   4.8657        +4.1452               +2.0420

TO REPRODUCE EVERY NUMBER IN THIS DOCSTRING, stated here in full rather than
cited to a script, because a citation to a file nobody can open is worse than
no citation at all:

    t = 2000.0 + np.arange(round(years * per_year)) / per_year
    mask = np.ones((1, t.size), bool)
    x = SignalSpec(terms).design_info(t, mask).matrix
    gram = KalmanEngine().score(
        state_space, theta, np.zeros((1, t.size)), mask, t, x
    ).normal_equations[0, 1:, 1:]
    lam = np.linalg.eigvalsh(gram)[::-1]
    log_cond = 0.5 * (np.log(lam[0]) - np.log(lam[-1]))

with `state_space = StateSpace.from_spec(ProcessSpec((white, matern12)))`
(`metamer.core.statespace`, `metamer.core.terms`) and `theta =
np.array([[0.4, 1.2, 6.0]])`. That parameter order is not a convention to
guess: `ProcessSpec` sorts its terms canonically, and `free_param_index` on
this spec returns matern12 sigma, matern12 rho, white sigma, in that order.

WHICH KNOBS EACH TABLE TURNS. The two tables above vary `years`, `per_year`
and `terms` only, at fixed theta. The table under THE DIAGNOSTIC IS
THETA-DEPENDENT varies `theta` alone, and it is measured NOT on a full-support
design but on the conditioning fixture in `tests/test_objective.py`: substitute
`t = _GAP_T`, `mask = _window(2)[None, :]` (the 42-row ILL case) and
`x = _gapped_signal(t).design_info(t, mask).matrix` for the first three lines,
leaving the rest as written. The scale-invariance figure at the end of this
docstring uses that same fixture with every amplitude multiplied by c.

READ THE LAST ROW OF THE FIRST TABLE. A century-long monthly record with an
acceleration term is perfectly well supported, and against the fixture-calibrated
1e3 it cleared by **0.1735 nats** -- a factor of 1.19, so a record only ~10%
longer would have been flagged ILL_CONDITIONED_X for no reason but its span.
Against the derived 8192 the same case clears by 2.2767 nats, a factor of 9.7.
The float64 derivation is thus not merely better justified than the calibrated
value, it is roughly ten times safer in the direction that actually bites, and
the margin is a full order of magnitude on every case measured.

THE DIAGNOSTIC IS THETA-DEPENDENT, because the Gram is. The same mask on the
same design classifies differently at different noise parameters. Measured on
the fixture's ill-conditioned case -- identical X, identical 42-row mask, only
theta varied:

    theta (m12 sigma, rho, white sigma)   cond(X_w)      log   band
    (0.4,  1.2,  6.0  )                      24623    10.1114  ILL
    (2.0,  0.1,  0.5  )                       4452.5   8.4012  OK
    (0.4,  1.2,  0.05 )                       4920.1   8.5011  OK
    (5.0,  0.02, 0.01 )                       2981.5   8.0002  OK

That is CORRECT, not a defect -- identifiability really is a property of
`X' Sigma^-1 X`, not of X alone -- but it means a series can change outcome as
the optimizer walks, so Task 13 must treat the resulting NaN as a barrier and
record the outcome at the FINAL theta, not the first one it saw.

IT IS, HOWEVER, INVARIANT TO THE OVERALL NOISE SCALE, which follows from the
definition rather than from any measurement: `X_w = Sigma^(-1/2) X`, so
`Sigma -> c Sigma` gives `X_w -> c^(-1/2) X_w`, and `cond(alpha A) = cond(A)`
for any non-zero alpha. So the limit cannot be tripped by a series simply being
noisier than its neighbours -- only by the SHAPE of Sigma relative to X.
Confirmed numerically on the same case by scaling every kernel amplitude by c
(hence `Sigma -> c^2 Sigma`): log cond(X_w) = 10.1114205303 at c = 1, 10 and
100, drifting by 1.8e-15 over four orders of magnitude, i.e. float64 noise.
"""

RANK_DEFICIENT_LOG_LIMIT: float = -0.5 * float(np.log(_RANK_RTOL))
"""Largest log cond(X_w) tolerated before X'Sigma^-1X reads as RANK_DEFICIENT_X.

`kalman._RANK_RTOL` is a relative singular-value cutoff on the GRAM. Restating
it in this module's cond(X_w) units is exactly what that constant's docstring
instructs Task 8 to do -- "halve the exponent to state it in X's units" -- and
it is the ONLY way the two limits here can be compared at all:

    s_min/s_max = _RANK_RTOL on the Gram
      <=> cond(Gram) = 1/_RANK_RTOL = 1e10
      <=> cond(X_w)  = _RANK_RTOL^(-1/2) = 1e5
      <=> log cond(X_w) = 11.5129

THE CONSTANT ITSELF IS NOT MOVED HERE, deliberately: `_RANK_RTOL` decides where
rank stops, it is calibrated in its own module against measured Gram spectra,
and this is a restatement of it, not a second opinion. Anything this module
calls ill-conditioned rather than deficient must sit strictly below this value.
"""

if not CONDITION_LOG_LIMIT < RANK_DEFICIENT_LOG_LIMIT:  # pragma: no cover
    raise ValueError(
        "outcome ladder inverted: ILL_CONDITIONED_X would be unreachable "
        f"({CONDITION_LOG_LIMIT} >= {RANK_DEFICIENT_LOG_LIMIT}). The rank test "
        "fires first, so every ill-conditioned series would come back "
        "RANK_DEFICIENT_X and the milder outcome would be dead code."
    )

_NEGATIVE_REDUCTION_RTOL: float = _EPS**0.5
"""Excursion in `rss_reduction` too large to be rounding. sqrt(eps) = 1.490e-8.

DERIVED, NOT PICKED. It was `1e-6` until 2026-08-10, and `1e-6` is not a
statement about anything: the quantity it bounds has a forward error this
module already knows the size of.

UNITS: relative to `max(|quadratic|, 1)`, i.e. to `y' Sigma^-1 y`, which is
both the upper bound on `rss_reduction` and its natural scale.

THE DERIVATION, WHICH RESTS ON `CONDITION_LOG_LIMIT` AND NOT ON A SECOND
OPINION. `rss_reduction` comes out of one Cholesky solve against the
accumulated Gram, so its relative forward error goes like `eps * cond(Gram)`.
The largest `cond(Gram)` this module admits is fixed by `CONDITION_LOG_LIMIT`:
above `cond(X_w) = eps^(-1/4)` the series is already reported
`ILL_CONDITIONED_X`, and `cond(Gram) = cond(X_w)^2 = eps^(-1/2)`. So the
largest excursion attributable to rounding, anywhere this check can still be
reached, is

    eps * cond(Gram)_max = eps * eps^(-1/2) = sqrt(eps) = 1.4901e-08

and anything bigger is not rounding. Note the exponent is inherited rather
than chosen: it is one squaring (the Gram) and one solve, and it is stated in
the same units as the limit it comes from so the two are comparable.

CONSEQUENCE: 67x tighter than `1e-6`, so `IMPLAUSIBLE_REDUCTION` now fires on
excursions between `sqrt(eps)` and `1e-6` of the quadratic form that were
previously silent. That is the intended direction -- the upper-bound half of
this check is the dangerous one, because an `rss_reduction` above `y'Sigma^-1y`
drives `y'Py` negative and raises the log-likelihood above its true value,
which wins model selection.
"""


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
            shape (B,) int64, carried through from the engine. THETA-DEPENDENT:
            it is the rank of the WHITENED Gram, thresholded at
            `kalman._RANK_RTOL`, so the same design can yield different values
            at different noise parameters. It is a NUMERICAL DIAGNOSTIC of the
            solve, not a parameter count.

            **-1 where `outcome` is not OK**, meaning "not computed", exactly as
            on `ScoredResult` so the two objects cannot be read under different
            conventions. CHECK `outcome` FIRST: -1 is a clean comparison but is
            NOT fail-loud under arithmetic -- `n_obs - rank_x` at -1 yields
            `n_obs + 1`, a sample size larger than the number of observations,
            which looks entirely plausible in BIC.
        design_rank: `rank(X_r)` PER SERIES, shape (B,) int64 -- the rank of the
            design restricted to that series' unmasked rows, read from
            `DesignInfo.rank`. THETA-FREE, and carrying NO SENTINEL: it is a
            true fact about the design whether or not the fit succeeded, so it
            is populated on every path, including the failure paths where
            `rank_x` is -1. Zero when there is no design, which is its true
            value.

            **THIS IS THE ONE TASK 9 MUST USE** for REML's effective sample
            size `n_obs - rank(X)`. It is the rank that Harville's constant
            `(n - rank(X)) log 2 pi` was actually computed with in this module
            (see `evaluate`), so using anything else makes the counting
            inconsistent with the likelihood it is counting for.

            TWO RANKS ARE CARRIED DELIBERATELY, and they are not
            interchangeable. `rank_x` answers "how well conditioned was the
            solve at this theta"; `design_rank` answers "how many linearly
            independent columns does this series' design have". They are equal
            on every path that currently produces a finite log-likelihood -- a
            deficient `X_r` fails the series before it is scored -- which is
            exactly why the distinction must be written down rather than
            discovered: two quantities that agree in practice and are
            documented as one are how an off-by-one reaches BIC.
    """

    loglik: NDArray[np.float64]
    gls: GlsResult | None
    outcome: NDArray[np.uint8]
    n_used: NDArray[np.int64]
    rank_x: NDArray[np.int64]
    design_rank: NDArray[np.int64]


OUTCOME_PRECEDENCE: tuple[Outcome, ...] = (
    Outcome.INSUFFICIENT_DATA,
    Outcome.NOT_ATTEMPTED,
    Outcome.RANK_DEFICIENT_X,
    Outcome.ILL_CONDITIONED_X,
    Outcome.NONFINITE_OBJECTIVE,
    Outcome.OK,
)
"""Causal ordering of the outcomes this module can combine: EARLIEST CAUSE WINS.

Precedence is DECLARED HERE, once, rather than decided by which call site runs
last. Several places combine two verdicts -- the design precheck, the engine and
the GLS solve all classify the same series -- and an inline "the later one wins
unless the earlier one is special" at each of them is how two sites come to
disagree about what a series failed of.

Reading the ladder top to bottom:

  * INSUFFICIENT_DATA and NOT_ATTEMPTED are DATA-LEVEL facts and outrank
    everything. An all-masked series is land or permanent ice: `is_failure` is
    False and `is_eligible` is False, so design doc section 8.6 excludes it from
    the failure-rate denominator. The engine poisons such a series' accumulator
    to NaN, so this module's independent view of it is "non-finite" -- and
    taking that view would relabel every land pixel a failure, moving it into
    the numerator AND inflating the denominator the exclusion protects, which
    would make every reported failure rate meaningless. **A land pixel yielding
    NaN is not a numerical failure, and this ordering is what encodes that.**
  * RANK_DEFICIENT_X then ILL_CONDITIONED_X are DESIGN-LEVEL causes, the second
    milder than the first: a term with no support at all versus a term
    identified by a handful of samples. Which one happened where is the point of
    the failure map, so they stay distinct.
  * NONFINITE_OBJECTIVE is NUMERICAL and names a symptom, not a cause, so any
    named cause refines it.
  * OK is last and can never displace a cause.

An outcome not listed here (a Task 13 optimizer verdict, say) is still a
failure: it outranks OK and nothing else. It is deliberately not silently
promoted above a cause this module actually diagnosed.
"""

# Doubled ranks leave the odd slot `_UNRANKED` free between the last named
# cause and OK, which is where an outcome outside the ladder belongs.
_PRECEDENCE_RANK: dict[int, int] = {
    outcome.code: 2 * position for position, outcome in enumerate(OUTCOME_PRECEDENCE)
}
_UNRANKED = 2 * len(OUTCOME_PRECEDENCE) - 3
_RANK_TABLE: NDArray[np.int64] = np.full(
    max(_PRECEDENCE_RANK) + 1, _UNRANKED, dtype=np.int64
)
for _code, _rank in _PRECEDENCE_RANK.items():
    _RANK_TABLE[_code] = _rank


def merge_outcomes(*outcomes: NDArray[np.uint8]) -> NDArray[np.uint8]:
    """Combine per-series verdicts under `OUTCOME_PRECEDENCE`.

    MERGE, NEVER REPLACE, and merge through the declared ladder rather than by
    inline comparison at each site. The result is symmetric in its arguments:
    the merged verdict is whichever input names the earliest cause, so it does
    not matter which classifier ran first.

    Args:
        *outcomes: Two or more per-series code arrays, each shape (B,) uint8.

    Returns:
        The merged per-series codes, shape (B,) uint8.

    Raises:
        ValueError: If fewer than two arrays are given -- a single-argument
            call is almost certainly a merge site that lost one of its inputs.
    """
    if len(outcomes) < 2:
        raise ValueError(
            f"merge_outcomes needs at least two verdicts, got {len(outcomes)}"
        )
    best = np.asarray(outcomes[0], dtype=np.uint8)
    best_rank = _rank_of(best)
    for other in outcomes[1:]:
        candidate = np.asarray(other, dtype=np.uint8)
        rank = _rank_of(candidate)
        take = rank < best_rank
        best = np.where(take, candidate, best).astype(np.uint8)
        best_rank = np.where(take, rank, best_rank)
    return np.asarray(best, dtype=np.uint8)


def _rank_of(codes: NDArray[np.uint8]) -> NDArray[np.int64]:
    """Look up each code's precedence rank, treating unlisted codes uniformly.

    Args:
        codes: Per-series outcome codes, shape (B,) uint8.

    Returns:
        Precedence ranks, shape (B,); lower binds tighter.
    """
    index = np.asarray(codes, dtype=np.int64)
    inside = index < _RANK_TABLE.size
    return np.where(inside, _RANK_TABLE[np.where(inside, index, 0)], _UNRANKED)


def implausible_reduction_mask(
    rss_reduction: NDArray[np.float64], quadratic: NDArray[np.float64]
) -> NDArray[np.bool_]:
    """Flag residual reductions outside their mathematically valid range.

    TWO QUANTITIES ARE AT RISK HERE, IN OPPOSITE DIRECTIONS, and guarding only
    one of them leaves the other free to inflate a log-likelihood while the
    series still reports OK. Both are quadratic forms in positive semidefinite
    matrices, so in exact arithmetic

        0  <=  rss_reduction = y'SX (X'SX)^-1 X'Sy  <=  y'Sy = quadratic

    and the residual form the likelihood actually uses is the DIFFERENCE

        y'Py = quadratic - rss_reduction,

    formed by cancelling two large positives. The concentrated value is
    `-0.5 * (n log 2pi + log|Sigma| + y'Py)`, so:

      * `rss_reduction < 0` (the lower bound) means the accumulator is not the
        matrix it claims to be;
      * `rss_reduction > quadratic` (the upper bound) drives `y'Py` NEGATIVE,
        which raises the log-likelihood above its true value -- the more
        dangerous direction, because a too-high value wins model selection.

    Nothing takes a log or a sqrt of either, so neither produces a NaN; the
    failure is silent in both directions, which is why it is checked rather
    than left to surface downstream. Small excursions of ORDER ROUNDING are
    deliberately NOT flagged: at cancellation they are expected, and the
    resulting error in the log-likelihood is of the same relative order.

    Recorded as an outcome rather than raised, because raising for one series
    aborts a tile of 10^4.

    Args:
        rss_reduction: The residual reductions, shape (B,).
        quadratic: `y' Sigma^-1 y` per series -- both the upper bound and the
            natural scale to measure the tolerance against, shape (B,).

    Returns:
        True where the reduction falls outside `[0, quadratic]` by more than
        tolerance, shape (B,).
    """
    scale = np.maximum(np.abs(quadratic), 1.0)
    slack = _NEGATIVE_REDUCTION_RTOL * scale
    with np.errstate(invalid="ignore"):
        below = rss_reduction < -slack
        above = rss_reduction > quadratic + slack
    return np.asarray((below | above) & np.isfinite(rss_reduction), dtype=np.bool_)


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
    # prescribes, via a batched `eigvalsh`: the Gram is symmetric positive
    # semidefinite, so its eigenvalues ARE its singular values, and the
    # symmetric routine is both cheaper and better conditioned than a general
    # SVD. It raises for the whole stack on a non-finite member, so it sees
    # only the finite subset -- the same classify-first rule as above. At
    # k <~ 8 the cost is irrelevant either way; this runs once per fit at the
    # optimum, not once per iteration, which is why the diagonal AM-GM proxy an
    # earlier draft used bought nothing.
    values = np.zeros((batch, k), dtype=np.float64)
    if finite.any():
        # eigvalsh returns ASCENDING; flip so [:, 0] is the largest, matching
        # the singular-value convention the thresholds are written against.
        # Clip at zero: a semidefinite Gram can produce a small negative
        # eigenvalue by rounding, and a negative "singular value" would make
        # the log below a NaN instead of the -inf that means "singular".
        values[finite] = np.maximum(np.linalg.eigvalsh(xtx[finite])[:, ::-1], 0.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        log_cond = 0.5 * (np.log(values[:, 0]) - np.log(values[:, -1]))

    # BOTH LIMITS ARE STATED IN log cond(X_w), so the ladder is one comparison
    # on one quantity and the two are directly comparable. The module asserts at
    # import that CONDITION_LOG_LIMIT < RANK_DEFICIENT_LOG_LIMIT, so the `ill`
    # band below is always non-empty -- the brief's constant made it empty and
    # ILL_CONDITIONED_X unreachable.
    positive_definite = (sign > 0) & np.isfinite(log_abs_det)
    singular = finite & ~(positive_definite & (log_cond <= RANK_DEFICIENT_LOG_LIMIT))
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
        # Backstop: identify the offending members individually rather than
        # failing the whole subset.
        #
        # THE OFFENDER IS NUMERICAL, NOT STRUCTURAL, and the ladder ranks those
        # differently, so the distinction is not cosmetic. Every member reaching
        # here has already passed `eigvalsh` with a smallest eigenvalue above
        # the rank cutoff AND a positive `slogdet` sign: its structure is fine
        # and this module has said so. What failed afterwards is the
        # FACTORIZATION -- a LAPACK convergence failure, or a matrix definite by
        # its spectrum yet not factorizable at the working precision on this
        # BLAS. That is a property of the arithmetic, not of the design, and
        # `RANK_DEFICIENT_X` would attribute it to a design that is not at
        # fault. Attribution is the entire point of a failure taxonomy: a map
        # showing "rank deficient" where the truth is "the numerics fell over"
        # sends the reader to the design when they should be looking at the
        # platform.
        keep = np.ones(index.size, dtype=bool)
        factors = np.full((index.size, k, k), np.nan)
        for position in range(index.size):
            try:
                factors[position] = np.linalg.cholesky(sub[position])
            except LinAlgError:
                keep[position] = False
        outcome[index[~keep]] = Outcome.NONFINITE_OBJECTIVE.code
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
    # reach -- the reduction stays inside its bounds for any matrix that
    # survived the classification above, which is exactly why this is a
    # backstop and not a code path (see `implausible_reduction_mask`, which
    # guards BOTH bounds: the upper one is what keeps `y'Py = y'Sy -
    # rss_reduction` from going negative and inflating the log-likelihood).
    bad = implausible_reduction_mask(rss_reduction, accum[:, 0, 0]) & valid
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
        """Classify each series' restricted design before it reaches the likelihood.

        THIS CHECK IS NECESSARY BUT NOT SUFFICIENT, and the reason is now Sigma
        rather than the mask. It sees `rank(X_r)`, a property of the DESIGN
        alone; the system that is actually factorized is the WHITENED Gram
        `X_r' Sigma^-1 X_r`, which depends on theta. A design this check calls
        full rank is routinely reported ill-conditioned -- or, at a whitened
        condition number past 1e5, rank deficient -- once the engine forms that
        Gram, because the Gram squares the condition number and because Sigma
        reweights the rows. `gls_solution` is what catches that, per series, at
        each theta. Identifiability really is a property of `X' Sigma^-1 X`, not
        of X alone.

        Args:
            design: The built design matrix and its per-series quantities.
            batch: Number of series, which must match `design.batch`.

        Returns:
            Per-series outcome codes, shape (B,). RANK_DEFICIENT_X exactly
            where `X_r` is rank deficient.
        """
        codes = outcome_array(batch, Outcome.OK)
        # `is_deficient` is THE gate, not `gram_logdet == -inf`: a merely
        # NUMERICALLY deficient design keeps a finite (very negative) log|X'X|
        # -- singular values [1, 1e-2, 1e-11] give rank 2 of 3 with -59.9 -- so
        # the determinant sentinel alone would pass a design that cannot
        # identify its own columns. The finiteness test is kept as a second,
        # weaker guard on a hand-built DesignInfo, not as the primary one.
        deficient = design.is_deficient | ~np.isfinite(design.gram_logdet)
        codes[deficient] = Outcome.RANK_DEFICIENT_X.code
        return codes

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
        n_used_from_mask = np.count_nonzero(mask, axis=1).astype(np.int64)

        # THE DATA-LEVEL VERDICT IS FORMED FIRST, FROM THE MASK ALONE. It needs
        # no filter pass and no design, and it OUTRANKS every design-level and
        # numerical verdict in OUTCOME_PRECEDENCE. That ordering is load-bearing
        # here rather than decorative: a series with no unmasked epoch has an
        # all-zero restricted design, so `check_design` calls it
        # RANK_DEFICIENT_X -- and is not wrong to, on its own terms. Only the
        # ladder can settle which fact is REPORTED, and the answer is the
        # data-level one, because a land pixel or a permanently ice-covered
        # ocean cell is an EXPECTED outcome and must stay out of both the
        # numerator and the denominator of the section 8.6 failure rate.
        data_level = outcome_array(batch, Outcome.OK)
        data_level[n_used_from_mask == 0] = Outcome.INSUFFICIENT_DATA.code

        # rank(X_r), the DESIGN-level rank, carried separately from the
        # engine's whitened `rank_x` -- see `ObjectiveResult` for which is
        # which and which Task 9 must use. Zero where there is no design, which
        # is its true value: no columns, so nothing to subtract.
        design_rank = (
            design.rank.astype(np.int64)
            if design is not None
            else np.zeros(batch, dtype=np.int64)
        )

        has_design = design is not None and design.n_beta > 0
        precheck = data_level
        matrix: NDArray[np.float64] | None = None
        if design is not None:
            self._validate_design(design, batch, n_used_from_mask)
        if has_design and design is not None:
            # Rank deficiency is classified BEFORE any factorization: a singular
            # X' Sigma^-1 X would otherwise reach cholesky, which raises for the
            # WHOLE STACK if any one member is not positive definite. Merged
            # with the data-level verdict through the ladder rather than
            # replacing it -- the two describe different series in general, and
            # where they describe the same one, precedence decides.
            precheck = merge_outcomes(data_level, self.check_design(design, batch))
            matrix = design.matrix
            if not np.any(precheck == Outcome.OK.code):
                # ONLY short-circuit when EVERY series fails. A per-series
                # precheck that returned early on `np.any(... != OK)` would deny
                # 9,999 healthy grid points their fit because one neighbour's
                # gap removed a column's support -- the exact batched-granularity
                # failure this module exists to prevent.
                #
                # THE SHORT-CIRCUIT IS KEPT, and it is safe to keep only because
                # `data_level` above was folded in first. Returning
                # `check_design`'s verdict alone here skipped the engine, and
                # with it the engine's INSUFFICIENT_DATA, so a WHOLLY masked
                # tile came back RANK_DEFICIENT_X: `is_failure` True AND
                # `is_eligible` True, putting every pixel of an all-land tile
                # into both halves of the failure rate. The saving is worth
                # keeping -- a tile with no usable data anywhere is exactly
                # where a B x N filter sweep buys nothing -- and nothing is lost
                # by keeping it, because "no unmasked epoch" is derivable from
                # the mask and the engine could tell us nothing more.
                #
                # `kalman.score` applies the same `n_used == 0` rule; the two
                # are pinned to agree by
                # `test_a_wholly_masked_tile_agrees_with_and_without_a_design`.
                #
                # n_used is a real count even here (the protocol pins it as the
                # one field that stays meaningful for a failed series); rank_x
                # is the -1 "not computed" sentinel, since nothing was
                # factorized.
                return ObjectiveResult(
                    np.full(batch, np.nan),
                    None,
                    precheck,
                    n_used_from_mask,
                    np.full(batch, -1, dtype=np.int64),
                    design_rank,
                )

        result = self.engine.score(
            self.state_space, self.hydrate(theta), y, mask, t, matrix, self.objective
        )
        if matrix is None or design is None:
            # THIS PATH MERGES TOO. It is the one exit where the objective has
            # nothing of its own to add about the fit, which is exactly what
            # makes handing back `result.outcome` verbatim tempting -- and
            # wrong. `data_level` was computed from the mask before the engine
            # ran, and the ladder, not the engine, decides. Returning the
            # engine's word unmerged is benign only for as long as
            # `kalman.score` keeps applying the same `n_used == 0` rule; the
            # moment the two drift, an all-masked series comes back OK carrying
            # a finite log-likelihood. The value is re-gated alongside the
            # outcome so the store's status invariant holds in both directions
            # on every exit, not just on the ones with a design.
            outcome = merge_outcomes(data_level, result.outcome)
            usable = outcome == Outcome.OK.code
            return ObjectiveResult(
                np.where(usable, result.loglik, np.nan),
                None,
                outcome,
                result.n_used,
                np.where(usable, result.rank_x, -1).astype(np.int64),
                design_rank,
            )

        gls = gls_solution(result.normal_equations)
        outcome = merge_outcomes(precheck, result.outcome, gls.outcome)
        ok = outcome == Outcome.OK.code
        rank_x = np.where(ok, result.rank_x, -1).astype(np.int64)

        concentrated = np.where(ok, result.loglik + 0.5 * gls.rss_reduction, np.nan)
        if self.objective is Objective.ML:
            return ObjectiveResult(
                concentrated, gls, outcome, result.n_used, rank_x, design_rank
            )

        # REML, Harville form -- see the module docstring. The two terms beyond
        # the penalty are constant in theta and cancel in delta-IC, which is
        # exactly why their absence cannot be detected by a differential test.
        # BOTH BELONG TO THE RESTRICTED DESIGN X_r, and `DesignInfo` already
        # holds them per series, built from this same mask at setup: they are
        # theta-free, so they are read here and never recomputed. `design.rank`
        # is rank(X_r), NOT the engine's whitened `rank_x` -- see the module
        # docstring for why those two must not be interchanged.
        reml = np.where(
            ok,
            concentrated
            + 0.5 * design.rank.astype(np.float64) * np.log(2.0 * np.pi)
            + 0.5 * design.gram_logdet
            - 0.5 * gls.logdet,
            np.nan,
        )
        return ObjectiveResult(reml, gls, outcome, result.n_used, rank_x, design_rank)

    @staticmethod
    def _validate_design(
        design: DesignInfo, batch: int, n_used: NDArray[np.int64]
    ) -> None:
        """Refuse a DesignInfo that does not belong to this batch and this mask.

        Every per-series field on `DesignInfo` is derived from a mask. Pairing
        it with a DIFFERENT mask yields a REML value wrong by a theta-free
        constant: finite, plausible, invisible to every differential test, and
        therefore exactly the failure mode the per-series widening exists to
        remove. `n_rows` is carried on `DesignInfo` so the mismatch is loud
        instead. The check is O(B N) on a boolean array, negligible beside the
        O(B N d^2) filter sweep it guards.

        Args:
            design: The design under evaluation.
            batch: Number of series in `y`.
            n_used: Unmasked epochs per series implied by the mask, shape (B,).

        Raises:
            NotImplementedError: If the design is per-point (Phase 2).
            ValueError: If the design's batch or its originating mask disagrees.
        """
        if design.per_point:
            raise NotImplementedError(
                "per-point designs are Phase 2; this objective assumes (N, k)"
            )
        if design.batch != batch:
            raise ValueError(
                f"design describes {design.batch} series but y has {batch}: "
                "DesignInfo's derived fields are per series"
            )
        if not np.array_equal(design.n_rows, n_used):
            raise ValueError(
                "design was built from a different mask than the one passed to "
                "evaluate (unmasked-row counts disagree); rebuild it with "
                "SignalSpec.design_info(t, mask)"
            )

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
