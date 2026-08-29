"""§11.2's hysteresis audit: the strata, and the report they are read through.

WHAT THIS MODULE IS FOR (design doc §11.2, decisions D8, D9 and D10).
---------------------------------------------------------------------
`audit.run_arms` produces four fits of one batch. This turns them into numbers
**that cannot be quoted out of context** -- which is a stronger requirement than
producing correct numbers, and is the whole of D8.

THERE IS NO POOLED FIGURE, EVER, AND THE WITHHOLDING IS VISIBLE.
-----------------------------------------------------------------
§11.2's own sentence is *"the overall number is the one that gets quoted and the
per-stratum numbers are the ones that are true"*. D8 answers it by **not
producing the overall number at all**, on a fact checked before the decision
rather than assumed: **nothing in this system consumes a pooled disagreement
figure.** §11.2 attaches its one threshold to the iteration saving. So
withholding costs no decision rule anything.

**A missing number reads as an omission unless the report says it was
withheld**, which is the same argument that makes `RSS measurement validity`
print at zero. Every withheld quantity here is an object carrying its reason,
never an absent field -- see `Quantity`.

**THE HEADLINE IS THE MAXIMUM OVER STRATA**, because a mean dilutes and a
maximum cannot understate. **Except for the signed one**, where a maximum over
signed values returns the most positive stratum and is blind to an equally
biased negative one -- see `Headline`.

EACH METRIC CROSSES ONLY AXES AT ITS OWN GRANULARITY -- (h2).
-------------------------------------------------------------
That is what dissolved D9's 81-cell problem rather than trading it away:

    metric                            granularity   strata
    --------------------------------  ------------  ----------------------
    selection disagreement            per POINT     margin x winner
    |dloglik|, parameter distance,    per CELL      candidate x kappa
      signed-trend disagreement

**Nothing is crossed that does not share a granularity.** Failure status is a
**partition** and not an axis -- inside the both-OK intersection every cell is
OK/OK and the axis is degenerate -- so what varies is the **outcome flip**, and
it is counted separately with its own denominators (`CandidateOutcomes`).

THE BOUNDARIES ARE FIXED CONSTANTS FROM OUTSIDE THIS PROJECT.
--------------------------------------------------------------
Never quantiles: **a quantile bin means something different in every run**,
which is the pooled-number problem one level in. They are recorded with the
report, because per-stratum figures from two runs are comparable only if the
strata are.

BOTH STRATIFYING AXES READ THE **COLD** ARM, AND THAT IS (j7).
---------------------------------------------------------------
`kappa` from the cold arm and the winning candidate from the cold arm. Both
values are sitting right there for the warm arm too, and using either would let
**the mechanism under test move cells between strata** -- conditioning on a
post-treatment variable. D9 states this for `kappa`; **it applies identically to
the winner, which D9 does not say**, and the omission is recorded at
`point_strata` rather than left for the next reader to re-derive.

TWO OF THE FOUR `kappa` BINS ARE UNREACHABLE, AND THE REPORT SAYS SO.
----------------------------------------------------------------------
`optimize.HESSIAN_COND_LIMIT` is `float(EPS) ** -0.5`, which **is** `2**26` --
D9's first boundary, the same constant by the same derivation. A fit whose
`cond(H)` exceeds it reports `DEGENERATE_HESSIAN` and is therefore not in the
both-OK intersection. **So on the population these strata cross, no cell can
land in `[2**26, 2**52)` except by exact equality, and none at all in
`>= 2**52`.** The `undefined` bin stays reachable, because the taxonomy
thresholds `cond` and never tests positive definiteness.

**Nothing about D9 moves.** Zero members in a bin reads as a fact about the
field and is a fact about the outcome taxonomy, so the report carries
`unreachable_kappa_bins` beside the boundaries -- the same visibility argument
D8 makes for the pooled figure.

WHAT THIS MODULE DOES NOT DO.
------------------------------
**It does not choose the points.** Neither did `audit.run_arms`, and §11.2's
*"stratify the subsample by a post-fit difficulty proxy"* **is not constructible
for the population the audit now draws from**: every proxy it names is post-fit,
and the audit's subject is FINE points, where no cold fit exists until the audit
computes one. `config.audit.subsample` and `config.audit.stratify` still have no
consumer, and that is recorded as an open question rather than closed by a
sampler built on the circularity.

**It does not re-derive the lint or the trend column.** Both arrive as
arguments, from the caller that already holds them, for the same reason
`run_arms` takes an explicit point set.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

import numpy as np
from numpy.typing import NDArray

from metamer.batch.audit import Arm, AuditArms
from metamer.core.criteria import Ranking
from metamer.core.fit import FitResult
from metamer.core.outcomes import Outcome
from metamer.core.terms import ProcessSpec, free_param_index

KAPPA_BOUNDARIES: tuple[float, float] = (2.0**26, 2.0**52)
"""D9's `kappa` cuts, as facts about float64 rather than about this run.

`2**26 = 1/sqrt(eps)` is where inverting the Hessian -- which happens exactly
once, for `theta_err` -- has lost **half its significant digits**.
`2**52 = 1/eps` is where the Hessian is **numerically singular**. Two
boundaries, so THREE intervals, and `undefined` is the FOURTH bin. Four, not
five: a stratum count wrong by one is not visible in any output the audit
produces.

**THE FIRST OF THEM IS ALSO `optimize.HESSIAN_COND_LIMIT`**, which is what
makes the middle and upper bins unreachable on the both-OK intersection. See
the module docstring; the report carries the consequence in
`AuditReport.unreachable_kappa_bins`.
"""

MARGIN_BOUNDARIES: tuple[float, float] = (2.0, 10.0)
"""Burnham & Anderson's standard reading of a delta-IC.

Below 2 both models have substantial support; above 10 the loser has
essentially none. **From the literature, so they cannot have been chosen with
the audit's answer in view** -- which is the trap a quantile boundary walks
straight into.
"""

MIN_STRATUM_MEMBERS: int = 30
"""Below this a stratum reports its member COUNT in place of a rate.

**DERIVED, AND IT MUST NOT BE RE-PICKED.** A binomial rate over `n = 30` has a
standard error of ~9% at `p = 0.5` -- enough to tell a rare stratum from a
common one, **not enough to quote a rate.**

**IT COVERS THE MEANS AS WELL AS THE RATES, AND NOT THE MAXIMA.** The
derivation is about estimating a population parameter from `n` draws, so it
applies to the signed-trend mean for exactly the reason it applies to a
proportion. A maximum is not an estimate: the largest of three members is
the largest of three members, stated as such by the count beside it.
"""


class KappaBin(StrEnum):
    """The cold arm's Hessian conditioning, in D9's four bins."""

    WELL_CONDITIONED = "kappa_lt_2^26"
    HALF_PRECISION = "kappa_2^26_to_2^52"
    SINGULAR = "kappa_ge_2^52"
    UNDEFINED = "kappa_undefined"
    """No positive-definite Hessian, so no condition number.

    **A CATEGORY, NOT A SEVERITY.** Letting it fall silently into the worst
    numeric bin says "this fit is the most ill-conditioned we saw" about a fit
    whose curvature is not a curvature at all.
    """


class MarginBin(StrEnum):
    """The cold arm's delta-IC to next-best, in D9's three bins."""

    SUBSTANTIAL = "margin_lt_2"
    WEAK = "margin_2_to_10"
    DECISIVE = "margin_ge_10"


KAPPA_BINS: tuple[KappaBin, ...] = (
    KappaBin.WELL_CONDITIONED,
    KappaBin.HALF_PRECISION,
    KappaBin.SINGULAR,
    KappaBin.UNDEFINED,
)
MARGIN_BINS: tuple[MarginBin, ...] = (
    MarginBin.SUBSTANTIAL,
    MarginBin.WEAK,
    MarginBin.DECISIVE,
)

_NO_MARGIN = len(MARGIN_BINS)
"""Code for a point with no next-best, which is EXCLUDED rather than binned."""


@dataclass(frozen=True)
class Quantity:
    """One reported number, or the stated reason there is not one.

    **A WITHHELD QUANTITY IS AN OBJECT, NOT AN ABSENT FIELD.** Silence and
    absence are the same bytes, so a report that simply omits an invalid rate
    is indistinguishable from one whose stratum was never populated -- and a
    reader supplies the more flattering of the two. `value is None` with a
    `withheld` sentence is the same construction that makes
    `RSS measurement validity` print at zero.

    **EVERY QUANTITY CARRIES ITS OWN SCOPE AND ITS OWN DENOMINATOR.** The scope
    is what makes a pooled figure unconstructible here rather than merely
    discouraged: there is no way to build a `Quantity` that belongs to
    everything. The denominator is stated because a single "flip rate" has no
    obvious base and the choice moves the number.

    Attributes:
        name: What is being reported.
        scope: The stratum, candidate or partition it is reported over. Never
            empty.
        value: The number, or None when withheld.
        denominator: How many members the number is over. Reported even when
            the value is withheld -- it is what is reported INSTEAD.
        withheld: Why there is no value. Present exactly when `value` is None.

    Raises:
        ValueError: If the scope is empty, or if `value` and `withheld`
            disagree about whether this quantity exists.
    """

    name: str
    scope: str
    value: float | None
    denominator: int
    withheld: str | None = None

    def __post_init__(self) -> None:
        """Refuse a scopeless quantity, and a half-stated one.

        Raises:
            ValueError: If the scope is empty, or if `value` and `withheld`
                disagree about whether this quantity exists.
        """
        if not self.scope:
            raise ValueError(
                f"quantity {self.name!r} has no scope; a number reported over "
                "everything is the pooled figure D8 withholds, and it cannot "
                "be constructed here"
            )
        if (self.value is None) != (self.withheld is not None):
            raise ValueError(
                f"quantity {self.name!r} must carry either a value or a reason "
                f"it was withheld, never both and never neither; got "
                f"value={self.value!r} withheld={self.withheld!r}"
            )


def _rate(
    name: str, scope: str, numerator: int, denominator: int, floor: int
) -> Quantity:
    """A proportion, or the count that replaces it below `floor` members."""
    if denominator == 0:
        return Quantity(name, scope, None, 0, "the stratum is empty")
    if denominator < floor:
        return Quantity(
            name,
            scope,
            None,
            denominator,
            f"{denominator} members is below the {floor}-member minimum; a "
            f"binomial rate over 30 has a standard error of ~9% at p = 0.5, so "
            f"the count is reported in place of the rate",
        )
    return Quantity(name, scope, numerator / denominator, denominator)


def _mean(name: str, scope: str, values: NDArray[np.float64], floor: int) -> Quantity:
    """A mean over the finite members, withheld below `floor` of them."""
    finite = np.asarray(values, dtype=np.float64)
    finite = finite[np.isfinite(finite)]
    count = int(finite.size)
    if count == 0:
        return Quantity(name, scope, None, 0, "no member carries this quantity")
    if count < floor:
        return Quantity(
            name,
            scope,
            None,
            count,
            f"{count} members is below the {floor}-member minimum; the mean's "
            f"standard error scales as 1/sqrt(n) for the same reason a rate's "
            f"does, so the count is reported in place of the mean",
        )
    return Quantity(name, scope, float(np.mean(finite)), count)


def _maximum(name: str, scope: str, values: NDArray[np.float64]) -> Quantity:
    """The largest finite member, with no minimum-count rule.

    **THE 30-MEMBER RULE DOES NOT APPLY.** It is derived for estimating a
    population parameter from `n` draws; a maximum over three members is an
    exact statement about those three, and the count beside it says so.
    """
    finite = np.asarray(values, dtype=np.float64)
    finite = finite[np.isfinite(finite)]
    count = int(finite.size)
    if count == 0:
        return Quantity(name, scope, None, 0, "no member carries this quantity")
    return Quantity(name, scope, float(np.max(finite)), count)


def kappa_bin(cold_condition: NDArray[np.float64]) -> NDArray[np.int8]:
    """Assign D9's four `kappa` bins from the COLD arm's condition number.

    **THE ARGUMENT IS THE COLD ARM'S VALUE AND THE FUNCTION CANNOT SEE THE WARM
    ONE.** That is the (j7) guard made structural rather than tested into
    existence: binning by the warm arm would let the mechanism under test move
    cells between strata, and both values are sitting right there in
    `AuditArms.results`. A function that takes one array cannot pick the wrong
    one.

    **NaN IS `undefined` AND `+inf` IS `SINGULAR`, WHICH ARE DIFFERENT
    THINGS.** `optimize.hessian_condition` returns NaN when there is no
    curvature to describe -- no Hessian, or one that is not positive definite.
    An infinite condition number is a real reading: the Hessian is exactly
    singular, which is what the top bin is for.

    Args:
        cold_condition: `FitResult.hessian_cond` for the cold arm, any shape.

    Returns:
        Indices into `KAPPA_BINS`, same shape, int8.
    """
    value = np.asarray(cold_condition, dtype=np.float64)
    lower, upper = KAPPA_BOUNDARIES
    out = np.full(value.shape, KAPPA_BINS.index(KappaBin.UNDEFINED), dtype=np.int8)
    defined = ~np.isnan(value)
    out[defined & (value < lower)] = KAPPA_BINS.index(KappaBin.WELL_CONDITIONED)
    out[defined & (value >= lower) & (value < upper)] = KAPPA_BINS.index(
        KappaBin.HALF_PRECISION
    )
    out[defined & (value >= upper)] = KAPPA_BINS.index(KappaBin.SINGULAR)
    return out


def selection_margin(ranking: Ranking) -> NDArray[np.float64]:
    """delta-IC from the winner to the next-best candidate, per point.

    **NaN WHERE THERE IS NO NEXT-BEST**, which is a point with fewer than two
    rankable candidates or none at all. (a2b): the margin is invalid under a
    condition the code can detect, so it is made **unavailable** and the point
    is excluded and counted rather than binned. `np.nanmin` over an empty
    selection would return NaN with a warning and a `0.0` would put the point
    in the most ambiguous bin -- a fabricated reading in the direction that
    makes the audit look most alarming.

    Args:
        ranking: The COLD arm's ranking. See `AuditReport.point_strata` for why
            the arm is not a free choice.

    Returns:
        One margin per point, shape (B,), NaN where undefined.
    """
    delta = np.asarray(ranking.delta_ic, dtype=np.float64)
    # A candidate that did not fit is NaN here and must not sort to the front;
    # +inf is the right stand-in because "did not fit" is at least as bad as
    # any finite delta, and the winner's own 0.0 keeps position zero.
    ranked = np.where(np.isnan(delta), np.inf, delta)
    if ranked.shape[1] < 2:
        return np.full(ranked.shape[0], np.nan, dtype=np.float64)
    margin = np.sort(ranked, axis=1)[:, 1]
    undefined = (np.asarray(ranking.n_valid) < 2) | (np.asarray(ranking.best_index) < 0)
    return np.where(undefined, np.nan, margin)


def margin_bin(margin: NDArray[np.float64]) -> NDArray[np.int8]:
    """Assign D9's three margin bins, with a fourth code for "no next-best".

    **THE FOURTH CODE IS NOT A BIN.** It is `_NO_MARGIN`, and the points
    carrying it are excluded and counted. D9's margin axis has three bins and
    a stratum count wrong by one is not visible in any output.

    Args:
        margin: From `selection_margin`, shape (B,).

    Returns:
        Indices into `MARGIN_BINS`, or `_NO_MARGIN`, shape (B,), int8.
    """
    value = np.asarray(margin, dtype=np.float64)
    lower, upper = MARGIN_BOUNDARIES
    out = np.full(value.shape, _NO_MARGIN, dtype=np.int8)
    defined = ~np.isnan(value)
    out[defined & (value < lower)] = MARGIN_BINS.index(MarginBin.SUBSTANTIAL)
    out[defined & (value >= lower) & (value < upper)] = MARGIN_BINS.index(
        MarginBin.WEAK
    )
    out[defined & (value >= upper)] = MARGIN_BINS.index(MarginBin.DECISIVE)
    return out


# ------------------------------------------------------------------------
# The per-cell metrics. Each is computed over the both-OK intersection and
# nowhere else, because outside it `loglik` and `theta_unconstrained` are NaN
# by construction and a difference of two NaNs is not a small disagreement.
# ------------------------------------------------------------------------


def _taxonomy_lookup(attribute: str) -> NDArray[np.bool_]:
    """A code-indexed table of one `Outcome` property.

    **BUILT FROM THE MEMBERS' OWN CODES**, never from `range(len(Outcome))`.
    The docstring on `outcomes._CODES` says a new member takes the next free
    code; it does not promise the space stays contiguous, and a gap would make
    the positional form silently mis-map every code above it.
    """
    table = np.zeros(max(member.code for member in Outcome) + 1, dtype=np.bool_)
    for member in Outcome:
        table[member.code] = bool(getattr(member, attribute))
    return table


def _both_ok(arms: AuditArms) -> NDArray[np.bool_]:
    """Cells where the cold and warm arms both returned `OK`."""
    cold = arms.results[Arm.COLD].outcome == Outcome.OK.code
    warm = arms.results[Arm.WARM].outcome == Outcome.OK.code
    return np.asarray(cold & warm, dtype=np.bool_)


def _eligible(outcome: NDArray[np.uint8]) -> NDArray[np.bool_]:
    """Cells that count toward a denominator, by the taxonomy's own rule."""
    return _taxonomy_lookup("is_eligible")[np.asarray(outcome, dtype=np.uint8)]


def _failed(outcome: NDArray[np.uint8]) -> NDArray[np.bool_]:
    """Cells that count as a failure, by design doc §8.6's rule.

    **NOT `!= OK`.** `NOT_ATTEMPTED` and `INSUFFICIENT_DATA` are neither OK nor
    failures, and folding them into the rescue rate's denominator would divide
    by a population that was never at risk.
    """
    return _taxonomy_lookup("is_failure")[np.asarray(outcome, dtype=np.uint8)]


def parameter_distance(
    arms: AuditArms, candidates: Sequence[ProcessSpec]
) -> NDArray[np.float64]:
    """`|u_warm - u_cold| / se_cold` per free parameter, in SE units.

    **UNCONSTRAINED THROUGHOUT, WHICH IS §11.2's WORDING AND NOT AN
    ACCIDENT.** *"Distance in unconstrained coordinates, normalized by
    estimated standard error"*. Both the difference and the scale come from
    `theta_unconstrained` / `theta_err_unconstrained`; `theta_err` is in
    NATURAL units and dividing by it would produce a plausible number of the
    wrong quantity, since the arrays have the same shape and neither is NaN.

    **THE SCALE IS THE COLD ARM'S, FOR (j7)'s REASON.** The reference arm sets
    the units; scaling by the warm arm's SE would let the mechanism under test
    move the metric.

    **A ZERO COLD SE YIELDS NaN, NOT `inf`.** `theta_err_unconstrained` is
    clipped at zero, so an inverse Hessian with a non-positive diagonal lands
    exactly there -- and `x / 0` is a severity invented from a missing value.
    (a2b): the cell contributes nothing and is counted.

    Args:
        arms: The four arms.
        candidates: The candidate set, in model-axis order.

    Returns:
        `(B, M, p_max)` float64, NaN in each candidate's padding, outside the
        both-OK intersection, and wherever the cold SE is zero.
    """
    cold = arms.results[Arm.COLD]
    warm = arms.results[Arm.WARM]
    gap = np.abs(warm.theta_unconstrained - cold.theta_unconstrained)
    scale = np.asarray(cold.theta_err_unconstrained, dtype=np.float64)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where(scale > 0.0, gap / scale, np.nan)
    live = _both_ok(arms)
    out[~live] = np.nan
    for model, spec in enumerate(candidates):
        out[:, model, len(free_param_index(spec)) :] = np.nan
    return np.asarray(out, dtype=np.float64)


def abs_delta_loglik(arms: AuditArms) -> NDArray[np.float64]:
    """`|loglik_warm - loglik_cold|` per cell, NaN outside the intersection.

    **REPORTED AS A PER-STRATUM MAXIMUM RATHER THAN AS A THRESHOLDED RATE, AND
    THAT IS A DEPARTURE FROM §11.2's WORDING.** §11.2 says *"above a
    threshold"*; **no such threshold exists anywhere in this project**, and
    inventing one here would be a boundary chosen with the audit's answer in
    view -- which is exactly what D9's fixed-constant rule forbids. The maximum
    answers §11.2's question -- *"different optimum, or the same optimum to
    different precision"* -- strictly more informatively, and needs no
    constant.
    """
    cold = arms.results[Arm.COLD]
    warm = arms.results[Arm.WARM]
    out = np.abs(np.asarray(warm.loglik) - np.asarray(cold.loglik))
    out[~_both_ok(arms)] = np.nan
    return np.asarray(out, dtype=np.float64)


def signed_trend_difference(
    arms: AuditArms, trend_column: int | None
) -> NDArray[np.float64]:
    """`beta_warm[trend] - beta_cold[trend]` per cell. SIGNED, deliberately.

    §11.2: *"the actual scientific payload. Mean signed difference, not just
    magnitude -- zero-mean disagreement is noise, a biased one is systematic
    contamination."* Taking `abs` here would destroy the only distinction the
    metric exists to make.

    Args:
        arms: The four arms.
        trend_column: `DesignInfo.trend_column`, or None where the design has
            no trend. **Supplied by the caller rather than re-derived**, so the
            column is the one `fit` itself used -- assuming index 1 holds only
            for a `[Constant, Trend, ...]` ordering, and with
            `[Annual(), Trend()]` the reported number is a seasonal
            amplitude's, labelled as a trend's.

    Returns:
        `(B, M)` float64, all-NaN where the design has no trend column.
    """
    cold = arms.results[Arm.COLD]
    warm = arms.results[Arm.WARM]
    if trend_column is None:
        return np.full(cold.loglik.shape, np.nan, dtype=np.float64)
    out = np.asarray(warm.beta[:, :, trend_column], dtype=np.float64) - np.asarray(
        cold.beta[:, :, trend_column], dtype=np.float64
    )
    out[~_both_ok(arms)] = np.nan
    return out


# ------------------------------------------------------------------------
# The report
# ------------------------------------------------------------------------


@dataclass(frozen=True)
class CellStratum:
    """One `candidate x kappa` cell, and everything quoted about it.

    Attributes:
        candidate: `spec_hash`, which is what makes candidate identity stable
            across runs -- a position on the model axis is not.
        candidate_index: Its position on the model axis, for indexing back.
        lint_flagged: Whether the identifiability lint flagged this candidate.
            **A flagged set is audited, not refused** (D8): refusing denies an
            audit to the users most at risk, and since there is no pooled
            figure at all there is nothing for label switching to contaminate.
        kappa: The bin, from the COLD arm.
        members: Cells in the both-OK intersection landing here.
        max_abs_delta_loglik: Objective disagreement.
        max_parameter_distance: The largest per-parameter distance in SE.
        mean_signed_trend: The signed payload.
        per_term_parameter_distance: One per free parameter, §11.2's
            requirement. **Without it a pure label-switching signal is averaged
            into the aggregate and attributed to warm starting** -- and the
            aggregate above is exactly the maximum of these, so the two cannot
            drift apart.
    """

    candidate: str
    candidate_index: int
    lint_flagged: bool
    kappa: KappaBin
    members: int
    max_abs_delta_loglik: Quantity
    max_parameter_distance: Quantity
    mean_signed_trend: Quantity
    per_term_parameter_distance: tuple[Quantity, ...]


@dataclass(frozen=True)
class PointStratum:
    """One `margin x winning candidate` cell, per POINT.

    **THE WINNER IS THE COLD ARM'S, AND D9 DOES NOT SAY SO.** D9 states the
    (j7) guard for `kappa` -- *"the one most likely to be got wrong later,
    because both values are sitting right there"* -- and its argument applies
    identically here: stratifying by the warm arm's winner would let the
    mechanism under test move points between strata, and the metric being
    measured IS whether the winner moved. **Recorded here rather than left for
    the next reader.**

    Attributes:
        candidate: `spec_hash` of the COLD arm's winner.
        candidate_index: Its position on the model axis.
        lint_flagged: Whether the lint flagged this candidate.
        margin: The bin, from the COLD arm's delta-IC to next-best.
        members: Points landing here with a winner in BOTH arms.
        selection_disagreement: The rate over those members.
    """

    candidate: str
    candidate_index: int
    lint_flagged: bool
    margin: MarginBin
    members: int
    selection_disagreement: Quantity


@dataclass(frozen=True)
class CandidateOutcomes:
    """The failure PARTITION, per candidate. Crossed with nothing.

    D9: failure status is not a stratum. Inside the both-OK intersection every
    cell is OK/OK and the axis is degenerate. **What varies is the outcome
    flip** -- a fit appearing or vanishing rather than moving -- and each rate
    carries its own denominator at the definition, because a single "flip rate"
    has no obvious base and the choice moves the number.

    Attributes:
        candidate: `spec_hash`.
        candidate_index: Position on the model axis.
        lint_flagged: Whether the lint flagged it.
        lint_findings: The rules that fired, so a flagged report NAMES the
            flagged pair rather than merely marking it.
        attempted: Eligible cells, by `Outcome.is_eligible`.
        cold_ok: Cells the cold arm fitted.
        cold_failed: Cells the cold arm failed, by `Outcome.is_failure`.
        both_ok: The intersection's size.
        rescue: warm-OK and cold-failed, **over cold-failed cells**.
        loss: warm-failed and cold-OK, **over cold-OK cells**.
        both_ok_fraction: The intersection **over attempted cells**. Near 1.0
            and the survival effect is negligible; below that, every
            disagreement figure for this candidate is conditioned on survival
            and the report says so.
    """

    candidate: str
    candidate_index: int
    lint_flagged: bool
    lint_findings: tuple[str, ...]
    attempted: int
    cold_ok: int
    cold_failed: int
    both_ok: int
    rescue: Quantity
    loss: Quantity
    both_ok_fraction: Quantity


@dataclass(frozen=True)
class PointConditioning:
    """What the per-POINT metric is conditioned on, at its own granularity.

    **D9's intersection fraction is per CELL and cannot qualify this.** The
    selection metric needs both arms to have produced a winner, which is a
    different partition with a different denominator; reporting one fraction
    and letting it cover both would attach the wrong conditioning statement to
    the more interpretable number.

    Attributes:
        audited_points: Rows in the audited batch.
        both_ranked: Points where both arms produced a winner.
        ranked_fraction: `both_ranked / audited_points`.
        cold_only_winner: Points the cold arm ranked and the warm arm did not.
        warm_only_winner: The reverse. **Counted, never folded into the
            selection disagreement rate**: "the warm arm selected nothing" and
            "the warm arm selected something else" are different findings.
        no_margin: Points excluded from every margin stratum because the cold
            arm had fewer than two rankable candidates -- (a2b).
    """

    audited_points: int
    both_ranked: int
    ranked_fraction: Quantity
    cold_only_winner: int
    warm_only_winner: int
    no_margin: int


@dataclass(frozen=True)
class Headline:
    """The one number for a metric: the WORST stratum, never a mean.

    §11.2's own sentence is that the overall number is the one that gets quoted
    and the per-stratum numbers are the ones that are true. **Reporting the
    worst stratum makes the quoted number a true one** -- it is a real
    measurement of a real stratum, named here so it cannot be quoted without
    the stratum it came from.

    **THE SIGNED METRIC IS RANKED ON ABSOLUTE VALUE AND REPORTED SIGNED.** D8's
    argument for the maximum is that *"a maximum cannot understate"*, which is
    false of a signed quantity: a maximum over signed values returns the most
    positive stratum and is blind to a stratum with an equally large negative
    bias -- which §11.2 calls systematic contamination in either direction.

    Attributes:
        name: The metric.
        value: The worst stratum's value, or None when every stratum withheld.
        stratum: Which stratum it came from.
        withheld: Why there is no value.
    """

    name: str
    value: float | None
    stratum: str | None
    withheld: str | None


@dataclass(frozen=True)
class AuditReport:
    """§11.2's audit, read through D8 and D9 -- and no field here is pooled.

    Attributes:
        seed: `config.audit.seed`, the one the N2 directions were keyed on.
        kappa_boundaries: Recorded WITH the figures, because per-stratum
            numbers from two runs are comparable only if the strata are.
        margin_boundaries: The same.
        min_stratum_members: The same.
        unreachable_kappa_bins: Bins no cell in the both-OK intersection can
            occupy, given `optimize.HESSIAN_COND_LIMIT`. **Zero members there
            is a fact about the outcome taxonomy and reads as a fact about the
            field**, so it is stated rather than left to be inferred.
        cell_strata: `candidate x kappa`.
        point_strata: `margin x winning candidate`.
        candidates: The failure partition and the survival fraction.
        points: The per-point conditioning.
        headlines: One worst-stratum figure per metric.
        notes: Everything withheld, and why. **Never empty**: the pooled figure
            is withheld on every run.
    """

    seed: int
    kappa_boundaries: tuple[float, float]
    margin_boundaries: tuple[float, float]
    min_stratum_members: int
    unreachable_kappa_bins: tuple[KappaBin, ...]
    cell_strata: tuple[CellStratum, ...]
    point_strata: tuple[PointStratum, ...]
    candidates: tuple[CandidateOutcomes, ...]
    points: PointConditioning
    headlines: tuple[Headline, ...]
    notes: tuple[str, ...]

    def quantities(self) -> tuple[Quantity, ...]:
        """Every reported number, each carrying the scope it belongs to.

        **THIS IS WHAT MAKES "NO POOLED FIGURE" CHECKABLE ON THE OUTPUT RATHER
        THAN ON THE SOURCE.** Grepping the module for `mean(` tests the
        spelling; walking this tests the report. A pooled figure reintroduced
        under any name would have to appear here with a scope, and there is no
        scope for it.
        """
        out: list[Quantity] = []
        for cell in self.cell_strata:
            out.append(cell.max_abs_delta_loglik)
            out.append(cell.max_parameter_distance)
            out.append(cell.mean_signed_trend)
            out.extend(cell.per_term_parameter_distance)
        for point in self.point_strata:
            out.append(point.selection_disagreement)
        for candidate in self.candidates:
            out.extend((candidate.rescue, candidate.loss, candidate.both_ok_fraction))
        out.append(self.points.ranked_fraction)
        return tuple(out)

    def withheld(self) -> tuple[Quantity, ...]:
        """Every quantity that has no value, with its reason.

        Present so the withholding is **read** rather than merely stored: a
        caller that prints only `quantities()` with a `value is not None`
        filter has reinvented silence.
        """
        return tuple(q for q in self.quantities() if q.value is None)


_POOLED_WITHHELD = (
    "No pooled disagreement figure is emitted, on any metric, ever (D8). "
    "Nothing in this system consumes one -- §11.2 attaches its only threshold "
    "to the iteration saving -- which was checked before the decision, so the "
    "withholding costs no decision rule anything. Each headline below is the "
    "WORST stratum and names the stratum it came from, which makes the quoted "
    "number a true one."
)

_UNREACHABLE = (
    "kappa bins {bins} cannot be occupied by any cell this report covers. "
    "optimize.HESSIAN_COND_LIMIT is float(EPS) ** -0.5 = {limit:.1f}, which is "
    "the first kappa boundary, and a fit above it reports DEGENERATE_HESSIAN "
    "and is therefore outside the both-OK intersection. Zero members there is "
    "a fact about the outcome taxonomy, not about the field."
)


def _term_labels(spec: ProcessSpec) -> tuple[str, ...]:
    """`term.parameter` per free parameter, in the order `theta` stores them."""
    return tuple(f"{label}.{name}" for label, name in free_param_index(spec))


def audit_report(
    arms: AuditArms,
    *,
    trend_column: int | None,
    lint_findings: Mapping[str, Sequence[str]] | None = None,
    min_members: int = MIN_STRATUM_MEMBERS,
) -> AuditReport:
    """Turn four arms into per-stratum numbers, and nothing quotable without one.

    **EVERY STRATUM IS EMITTED, INCLUDING THE EMPTY ONES.** A stratification
    that reports only its populated cells cannot tell a reader that a bin was
    unreachable, which is the whole of this report's `unreachable_kappa_bins`
    and half of D8's visibility requirement.

    Args:
        arms: From `audit.run_arms`. All four arms, one batch, one call site.
        trend_column: `DesignInfo.trend_column` for the design the arms were
            fitted under, or None. **Passed rather than re-derived**: building
            a second `DesignInfo` here would be a second derivation of which
            column the trend is, and the failure mode is a seasonal amplitude
            reported as a trend.
        lint_findings: `spec_hash` -> the identifiability rules that fired,
            from `validation.identifiability_warnings`' own `lint` calls.
            **Passed rather than re-derived** because the lint needs a sampling
            interval, which is a property of the data and not of the arms.
            Absent means "the lint was not run", which is reported as such
            rather than as "clean" -- a diagnostic that reports clean because
            it could not run is worse than one that says nothing.
        min_members: The floor below which a rate or a mean is withheld.
            Parameterized for the boundary test and **not for tuning**; see
            `MIN_STRATUM_MEMBERS`.

    Returns:
        The report.

    Raises:
        ValueError: If the arms carry no candidates, or if `min_members` is not
            positive.
    """
    if min_members < 1:
        raise ValueError(f"min_members must be at least 1, got {min_members}")
    cold = arms.results[Arm.COLD]
    warm = arms.results[Arm.WARM]
    specs = list(cold.candidates)
    if not specs:
        raise ValueError("an audit report needs at least one candidate")

    hashes = [spec.spec_hash() for spec in specs]
    findings = dict(lint_findings or {})
    flagged = {name: tuple(findings.get(name, ())) for name in hashes}

    live = _both_ok(arms)
    kappa = kappa_bin(cold.hessian_cond)
    distance = parameter_distance(arms, specs)
    objective_gap = abs_delta_loglik(arms)
    trend_gap = signed_trend_difference(arms, trend_column)
    aggregate = _aggregate_distance(distance)

    cell_strata = _cell_strata(
        hashes,
        specs,
        flagged,
        live,
        kappa,
        objective_gap,
        aggregate,
        distance,
        trend_gap,
        min_members,
    )
    point_strata, conditioning = _point_strata(
        hashes, flagged, cold.ranking, warm.ranking, min_members
    )
    candidates = _candidate_outcomes(hashes, flagged, cold, warm, min_members)

    notes = [_POOLED_WITHHELD]
    unreachable = (KappaBin.HALF_PRECISION, KappaBin.SINGULAR)
    notes.append(
        _UNREACHABLE.format(
            bins=", ".join(str(b) for b in unreachable), limit=KAPPA_BOUNDARIES[0]
        )
    )
    if lint_findings is None:
        notes.append(
            "The identifiability lint was NOT run for this report, so no "
            "candidate is marked flagged. That is not the same as clean: "
            "§11.2 warns that label switching and hysteresis are confounded "
            "and that the lint is the cheap way to know whether the confound "
            "is even present."
        )
    else:
        for name in hashes:
            if flagged[name]:
                notes.append(
                    f"Candidate {name[:12]} is lint-flagged ({', '.join(flagged[name])}). "
                    "It is audited rather than refused (D8) and its cells sit "
                    "in their own candidate strata; parameter disagreement "
                    "there may be non-identifiability rather than hysteresis."
                )
    if trend_column is None:
        notes.append(
            "The design has no trend column, so signed-trend disagreement is "
            "unavailable for every stratum. §11.2 calls it the actual "
            "scientific payload; its absence here is a property of the signal "
            "specification, not a measurement of zero."
        )
    for entry in candidates:
        if (
            entry.both_ok_fraction.value is not None
            and entry.both_ok_fraction.value < 1.0
        ):
            notes.append(
                f"Candidate {entry.candidate[:12]}'s both-OK intersection is "
                f"{entry.both_ok_fraction.value:.4f} of attempted cells, so every "
                "per-cell disagreement figure for it is CONDITIONED ON SURVIVAL. "
                "If warm and cold disagree most on hard cells and hard cells "
                "fail more often, restricting to both-OK removes exactly the "
                "population where the disagreement lives."
            )

    return AuditReport(
        seed=arms.seed,
        kappa_boundaries=KAPPA_BOUNDARIES,
        margin_boundaries=MARGIN_BOUNDARIES,
        min_stratum_members=min_members,
        unreachable_kappa_bins=unreachable,
        cell_strata=cell_strata,
        point_strata=point_strata,
        candidates=candidates,
        points=conditioning,
        headlines=_headlines(cell_strata, point_strata, candidates),
        notes=tuple(notes),
    )


def _aggregate_distance(distance: NDArray[np.float64]) -> NDArray[np.float64]:
    """The per-cell parameter distance: the largest of its per-term distances.

    **THE AGGREGATE IS THE MAXIMUM OF THE COMPONENTS, NOT A NORM OVER THEM.**
    That is what makes §11.2's per-term requirement exact rather than
    approximate: the two numbers cannot drift apart, and a label-switching
    signal concentrated in one term is visible as that term carrying the
    aggregate. A Euclidean norm would mix the terms back together, which is the
    averaging §11.2 names as the defect.
    """
    with np.errstate(invalid="ignore"):
        finite = np.where(np.isfinite(distance), distance, -np.inf)
        out = np.max(finite, axis=2)
    return np.where(np.isfinite(out), out, np.nan)


def _cell_strata(
    hashes: Sequence[str],
    specs: Sequence[ProcessSpec],
    flagged: Mapping[str, tuple[str, ...]],
    live: NDArray[np.bool_],
    kappa: NDArray[np.int8],
    objective_gap: NDArray[np.float64],
    aggregate: NDArray[np.float64],
    distance: NDArray[np.float64],
    trend_gap: NDArray[np.float64],
    floor: int,
) -> tuple[CellStratum, ...]:
    """`candidate x kappa`, every cell of it, populated or not."""
    out: list[CellStratum] = []
    for model, name in enumerate(hashes):
        labels = _term_labels(specs[model])
        for code, binning in enumerate(KAPPA_BINS):
            members = live[:, model] & (kappa[:, model] == code)
            scope = f"candidate={name[:12]} kappa={binning}"
            out.append(
                CellStratum(
                    candidate=name,
                    candidate_index=model,
                    lint_flagged=bool(flagged[name]),
                    kappa=binning,
                    members=int(np.count_nonzero(members)),
                    max_abs_delta_loglik=_maximum(
                        "max_abs_delta_loglik", scope, objective_gap[members, model]
                    ),
                    max_parameter_distance=_maximum(
                        "max_parameter_distance_se", scope, aggregate[members, model]
                    ),
                    mean_signed_trend=_mean(
                        "mean_signed_trend_difference",
                        scope,
                        trend_gap[members, model],
                        floor,
                    ),
                    per_term_parameter_distance=tuple(
                        _maximum(
                            f"max_parameter_distance_se[{label}]",
                            scope,
                            distance[members, model, index],
                        )
                        for index, label in enumerate(labels)
                    ),
                )
            )
    return tuple(out)


def _point_strata(
    hashes: Sequence[str],
    flagged: Mapping[str, tuple[str, ...]],
    cold: Ranking,
    warm: Ranking,
    floor: int,
) -> tuple[tuple[PointStratum, ...], PointConditioning]:
    """`margin x winning candidate`, plus what the metric is conditioned on."""
    cold_best = np.asarray(cold.best_index, dtype=np.int64)
    warm_best = np.asarray(warm.best_index, dtype=np.int64)
    cold_ranked = cold_best >= 0
    warm_ranked = warm_best >= 0
    both = cold_ranked & warm_ranked

    margins = margin_bin(selection_margin(cold))
    # **`both &` HERE IS REDUNDANT AND IS KEPT, AND THE MUTATION IS PROVEN
    # EQUIVALENT RATHER THAN RECORDED AS A SURVIVOR.** Every `members` mask
    # below is built as `both & ...`, so `members & (both & d)` and
    # `members & d` are the same set -- checked over 2000 random
    # (cold_best, warm_best, margin, model) fixtures, `max |difference| = 0`.
    # (e2): the mutant does not differ from the original on any input, which is
    # one of (e)'s six causes and not a coverage gap.
    #
    # It stays because the redundancy is where the RULE is written down: `-1`
    # compares unequal to everything, so a `disagree` that did not carry `both`
    # would call every unranked point a selection disagreement the moment any
    # caller used it without the membership mask.
    disagree = both & (cold_best != warm_best)

    out: list[PointStratum] = []
    for model, name in enumerate(hashes):
        for code, binning in enumerate(MARGIN_BINS):
            members = both & (cold_best == model) & (margins == code)
            count = int(np.count_nonzero(members))
            scope = f"winner={name[:12]} margin={binning}"
            out.append(
                PointStratum(
                    candidate=name,
                    candidate_index=model,
                    lint_flagged=bool(flagged[name]),
                    margin=binning,
                    members=count,
                    selection_disagreement=_rate(
                        "selection_disagreement",
                        scope,
                        int(np.count_nonzero(members & disagree)),
                        count,
                        floor,
                    ),
                )
            )

    total = int(cold_best.size)
    conditioning = PointConditioning(
        audited_points=total,
        both_ranked=int(np.count_nonzero(both)),
        ranked_fraction=_rate(
            "both_ranked_fraction",
            "all audited points",
            int(np.count_nonzero(both)),
            total,
            1,
        ),
        cold_only_winner=int(np.count_nonzero(cold_ranked & ~warm_ranked)),
        warm_only_winner=int(np.count_nonzero(warm_ranked & ~cold_ranked)),
        no_margin=int(np.count_nonzero(both & (margins == _NO_MARGIN))),
    )
    return tuple(out), conditioning


def _candidate_outcomes(
    hashes: Sequence[str],
    flagged: Mapping[str, tuple[str, ...]],
    cold: FitResult,
    warm: FitResult,
    floor: int,
) -> tuple[CandidateOutcomes, ...]:
    """The flip counts and the survival fraction, per candidate."""
    cold_code = np.asarray(cold.outcome, dtype=np.uint8)
    warm_code = np.asarray(warm.outcome, dtype=np.uint8)
    cold_ok = cold_code == Outcome.OK.code
    warm_ok = warm_code == Outcome.OK.code
    cold_bad = _failed(cold_code)
    warm_bad = _failed(warm_code)
    attempted = _eligible(cold_code)

    out: list[CandidateOutcomes] = []
    for model, name in enumerate(hashes):
        scope = f"candidate={name[:12]}"
        failed_here = int(np.count_nonzero(cold_bad[:, model]))
        ok_here = int(np.count_nonzero(cold_ok[:, model]))
        tried_here = int(np.count_nonzero(attempted[:, model]))
        out.append(
            CandidateOutcomes(
                candidate=name,
                candidate_index=model,
                lint_flagged=bool(flagged[name]),
                lint_findings=flagged[name],
                attempted=tried_here,
                cold_ok=ok_here,
                cold_failed=failed_here,
                both_ok=int(np.count_nonzero(cold_ok[:, model] & warm_ok[:, model])),
                rescue=_rate(
                    "rescue_rate over cold-failed cells",
                    scope,
                    int(np.count_nonzero(warm_ok[:, model] & cold_bad[:, model])),
                    failed_here,
                    floor,
                ),
                loss=_rate(
                    "loss_rate over cold-OK cells",
                    scope,
                    int(np.count_nonzero(warm_bad[:, model] & cold_ok[:, model])),
                    ok_here,
                    floor,
                ),
                both_ok_fraction=_rate(
                    "both_ok_fraction over attempted cells",
                    scope,
                    int(np.count_nonzero(cold_ok[:, model] & warm_ok[:, model])),
                    tried_here,
                    1,
                ),
            )
        )
    return tuple(out)


def _worst(name: str, quantities: Sequence[Quantity], signed: bool) -> Headline:
    """The largest available value, and the stratum it came from.

    `signed` ranks on absolute VALUE and reports the value with its SIGN; see
    `Headline` for why that is not the same as a maximum.
    """
    live = [(q.scope, float(q.value)) for q in quantities if q.value is not None]
    if not live:
        return Headline(
            name,
            None,
            None,
            f"every stratum withheld {name}; there is no true number to quote, "
            "and a pooled one is not offered in its place",
        )
    scope, best = max(live, key=lambda pair: abs(pair[1]) if signed else pair[1])
    return Headline(name, best, scope, None)


def _headlines(
    cells: Sequence[CellStratum],
    points: Sequence[PointStratum],
    candidates: Sequence[CandidateOutcomes],
) -> tuple[Headline, ...]:
    """One worst-stratum figure per metric, each naming its stratum."""
    return (
        _worst(
            "selection_disagreement",
            [p.selection_disagreement for p in points],
            signed=False,
        ),
        _worst(
            "max_abs_delta_loglik",
            [c.max_abs_delta_loglik for c in cells],
            signed=False,
        ),
        _worst(
            "max_parameter_distance_se",
            [c.max_parameter_distance for c in cells],
            signed=False,
        ),
        _worst(
            "mean_signed_trend_difference",
            [c.mean_signed_trend for c in cells],
            signed=True,
        ),
        _worst("rescue_rate", [c.rescue for c in candidates], signed=False),
        _worst("loss_rate", [c.loss for c in candidates], signed=False),
    )


__all__ = [
    "KAPPA_BOUNDARIES",
    "KAPPA_BINS",
    "MARGIN_BOUNDARIES",
    "MARGIN_BINS",
    "MIN_STRATUM_MEMBERS",
    "AuditReport",
    "CandidateOutcomes",
    "CellStratum",
    "Headline",
    "KappaBin",
    "MarginBin",
    "PointConditioning",
    "PointStratum",
    "Quantity",
    "abs_delta_loglik",
    "audit_report",
    "kappa_bin",
    "margin_bin",
    "parameter_distance",
    "selection_margin",
    "signed_trend_difference",
]
