"""§11.2's audit report: the strata, the withholding, and the denominators.

**EVERY FIXTURE HERE IS CONSTRUCTED RATHER THAN FITTED, AND THAT IS THE ONLY
WAY MOST OF THESE PROPERTIES CAN BE TESTED.** The 30-member boundary needs a
stratum holding exactly 29 members and one holding exactly 30; the rescue and
loss denominators need to DIFFER, or a single flip rate over a common base
reproduces both; and the `κ` guard needs a cell whose cold and warm condition
numbers fall in different bins. A fitted audit fixture at any affordable size
reaches none of those. The end-to-end check that the report runs on real arms
lives in `tests/test_audit.py`, on the two-pass store that module already
builds.

**THE CANDIDATE SET IS TWO THROUGHOUT AND THE TWO HAVE DIFFERENT `p`** -- 1 and
3 at 2a's set. A one-candidate fixture makes the candidate axis degenerate, so a
per-candidate denominator cannot be told apart from a pooled one; and a single
`p` cannot show a per-term split that lost a term.
"""

from __future__ import annotations

from dataclasses import fields

import numpy as np
import pytest

from metamer.batch.audit import Arm, ArmStarts, AuditArms
from metamer.batch.audit_report import (
    KAPPA_BINS,
    KAPPA_BOUNDARIES,
    MARGIN_BINS,
    MARGIN_BOUNDARIES,
    MIN_STRATUM_MEMBERS,
    AuditReport,
    KappaBin,
    MarginBin,
    Quantity,
    audit_report,
    kappa_bin,
    margin_bin,
    parameter_distance,
    selection_margin,
)
from metamer.config.candidates import parse_candidate
from metamer.core.capability import EngineId, Objective
from metamer.core.criteria import CandidateScores, Criterion, Ranking
from metamer.core.fit import FitResult
from metamer.core.outcomes import Outcome
from metamer.core.terms import free_param_index

_SPECS = [parse_candidate("white"), parse_candidate("white + matern12")]
_EXTENTS = [len(free_param_index(spec)) for spec in _SPECS]
_P_MAX = max(_EXTENTS)
_K_BETA = 2


def _result(
    batch: int,
    *,
    outcome: np.ndarray | None = None,
    loglik: np.ndarray | None = None,
    theta_u: np.ndarray | None = None,
    theta_err_u: np.ndarray | None = None,
    theta_err: np.ndarray | None = None,
    beta: np.ndarray | None = None,
    hessian_cond: np.ndarray | None = None,
    delta_ic: np.ndarray | None = None,
    best_index: np.ndarray | None = None,
) -> FitResult:
    """A `FitResult` built rather than fitted, with every array under control.

    Defaults are "every cell OK, every number zero", so each test states only
    the property it is about. `theta_err` defaults to TEN TIMES
    `theta_err_unconstrained`, because a metric that read the natural-unit
    array would otherwise agree with one that read the unconstrained array.
    """
    n_cand = len(_SPECS)
    shape = (batch, n_cand)
    if outcome is None:
        outcome = np.full(shape, Outcome.OK.code, dtype=np.uint8)
    outcome = np.asarray(outcome, dtype=np.uint8)
    ok = outcome == Outcome.OK.code
    if loglik is None:
        loglik = np.where(ok, -100.0, np.nan)
    theta_u = (
        np.zeros((batch, n_cand, _P_MAX)) if theta_u is None else np.array(theta_u)
    )
    theta_err_u = (
        np.ones((batch, n_cand, _P_MAX))
        if theta_err_u is None
        else np.array(theta_err_u)
    )
    theta_err = 10.0 * theta_err_u if theta_err is None else np.array(theta_err)
    if beta is None:
        beta = np.zeros((batch, n_cand, _K_BETA))
    if hessian_cond is None:
        hessian_cond = np.where(ok, 1.0e3, np.nan)
    if delta_ic is None:
        delta_ic = np.tile(np.arange(float(n_cand)) * 5.0, (batch, 1))
    if best_index is None:
        best_index = np.where(ok.any(axis=1), np.argmax(ok, axis=1), -1)

    for model, width in enumerate(_EXTENTS):
        for block in (theta_u, theta_err_u, theta_err):
            block[:, model, width:] = np.nan
    masked = np.where(ok[:, :, None], theta_u, np.nan)
    scores = CandidateScores(
        labels=tuple(spec.spec_hash()[:12] for spec in _SPECS),
        engines=(EngineId.KALMAN,) * n_cand,
        objectives=(Objective.ML,) * n_cand,
        loglik=np.asarray(loglik, dtype=np.float64),
        k=np.full(shape, 3.0),
        n=np.full(shape, 100.0),
        n_eff=np.full(shape, 100.0),
        outcome=outcome,
    )
    ranking = Ranking(
        criterion=Criterion.AIC,
        delta_ic=np.asarray(delta_ic, dtype=np.float64),
        weights=np.full(shape, 1.0 / n_cand),
        ic_best=np.zeros(batch),
        best_index=np.asarray(best_index, dtype=np.int64),
        n_valid=np.count_nonzero(ok, axis=1).astype(np.int64),
    )
    return FitResult(
        candidates=tuple(_SPECS),
        theta=masked,
        theta_err=np.asarray(theta_err, dtype=np.float64),
        theta_err_unconstrained=np.asarray(theta_err_u, dtype=np.float64),
        theta_unconstrained=masked,
        hessian_cond=np.asarray(hessian_cond, dtype=np.float64),
        beta=np.asarray(beta, dtype=np.float64),
        beta_err=np.zeros((batch, n_cand, _K_BETA)),
        loglik=np.asarray(loglik, dtype=np.float64),
        outcome=outcome,
        init_rung=np.empty(shape, dtype=object),
        n_iter=np.ones(shape, dtype=np.int64),
        n_eff_bic=np.full(shape, 100.0),
        n_eff_trend=np.full(shape, 100.0),
        scores=scores,
        ranking=ranking,
        engine=EngineId.KALMAN,
        objective=Objective.ML,
        gradient_mode=tuple(),
    )


def _arms(cold: FitResult, warm: FitResult, *, seed: int = 3) -> AuditArms:
    """An `AuditArms` carrying two real arms and two placeholder ones.

    The report reads `cold` and `warm` only -- N1 and N2 are the floor the
    READING is taken against, not an input to the strata -- so they are the
    same objects here. A test that needed them distinct would be testing
    `run_arms`, which `tests/test_audit.py` already does.
    """
    batch = cold.loglik.shape[0]
    zeros = np.zeros((batch, len(_SPECS), _P_MAX))
    flags = np.ones((batch, len(_SPECS)), dtype=bool)
    starts = ArmStarts(
        cold=zeros,
        warm=zeros,
        n1=zeros,
        n2=zeros,
        warm_valid=flags,
        n1_valid=flags,
        n2_valid=flags,
        distance=np.zeros((batch, len(_SPECS))),
        direction=zeros,
        n2_inadmissible=np.zeros((batch, len(_SPECS)), dtype=bool),
        degenerate=np.zeros((batch, len(_SPECS)), dtype=bool),
    )
    return AuditArms(
        starts=starts,
        results={Arm.COLD: cold, Arm.WARM: warm, Arm.N1: cold, Arm.N2: cold},
        points=np.arange(batch, dtype=np.int64),
        seed=seed,
        epsilon=1e-6,
    )


def _report(cold: FitResult, warm: FitResult, **kwargs: object) -> AuditReport:
    return audit_report(_arms(cold, warm), trend_column=1, **kwargs)  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# The binners, and the two axes that must read the cold arm
# --------------------------------------------------------------------------


def test_the_kappa_bins_are_four_and_undefined_is_its_own_one():
    """Two boundaries make three intervals; `undefined` is the fourth bin.

    Behaviour under test: `kappa_bin`'s mapping, at and around both fixed
    boundaries, plus the two non-finite readings.

    Expected values determined independently: `2**26` and `2**52` are
    arithmetic, and the interval rule is half-open upward -- a value AT a
    boundary belongs to the interval that boundary opens.

    Bug this catches: FIVE bins, which is the count the handoff brief carried.
    Two boundaries give three intervals and `undefined` is the fourth. **A
    stratum count wrong by one is not visible in any output the audit
    produces**, because the extra bin is simply always empty and every real
    number still lands somewhere plausible.

    It also catches `undefined` folded into the worst numeric bin -- a category
    reported as a severity -- and `+inf` folded into `undefined`, which is the
    reverse error: an infinite condition number is a real reading of an exactly
    singular Hessian, and `>= 2**52` is the bin for it.
    """
    lower, upper = KAPPA_BOUNDARIES
    values = np.array(
        [0.0, 1.0, lower / 2, lower, upper / 2, upper, upper * 10, np.inf, np.nan]
    )
    got = [KAPPA_BINS[code] for code in kappa_bin(values)]
    assert got == [
        KappaBin.WELL_CONDITIONED,
        KappaBin.WELL_CONDITIONED,
        KappaBin.WELL_CONDITIONED,
        KappaBin.HALF_PRECISION,
        KappaBin.HALF_PRECISION,
        KappaBin.SINGULAR,
        KappaBin.SINGULAR,
        KappaBin.SINGULAR,
        KappaBin.UNDEFINED,
    ]


def test_the_margin_bins_are_three_and_a_point_with_no_next_best_is_not_one():
    """Burnham & Anderson's two cuts, and the excluded fourth code.

    Behaviour under test: `margin_bin`'s mapping, and that a NaN margin gets a
    code OUTSIDE the three bins rather than being placed in one.

    Expected values determined independently: 2 and 10 are the literature's
    boundaries, half-open upward like `kappa`'s.

    Bug this catches: `np.nan_to_num` on the margin, which sends every point
    with no next-best into `margin < 2` -- the MOST AMBIGUOUS bin. That is a
    fabricated reading in the direction that makes the audit look most
    alarming, from points that had no second candidate to be ambiguous
    between.
    """
    lower, upper = MARGIN_BOUNDARIES
    values = np.array([0.0, lower - 1e-9, lower, 5.0, upper, 1e6, np.inf, np.nan])
    codes = margin_bin(values)
    assert [MARGIN_BINS[c] for c in codes[:-1]] == [
        MarginBin.SUBSTANTIAL,
        MarginBin.SUBSTANTIAL,
        MarginBin.WEAK,
        MarginBin.WEAK,
        MarginBin.DECISIVE,
        MarginBin.DECISIVE,
        MarginBin.DECISIVE,
    ]
    assert codes[-1] == len(MARGIN_BINS), "a missing margin must not be a bin"


def test_the_margin_is_the_second_best_and_is_undefined_below_two_candidates():
    """`delta_IC` to next-best, with the winner's own zero skipped.

    Behaviour under test: `selection_margin` reads the RUNNER-UP, not the
    winner and not the worst.

    Expected values determined independently: the winner's `delta_ic` is 0 by
    construction, so the margin is the second smallest entry of the row --
    here 4.0 with a third candidate at 9.0 present to show the worst is not
    what is read.

    Bug this catches: `np.nanmax(delta_ic)`, which reports the distance to the
    WORST candidate. On a set of three that is a different number, and it grows
    with the candidate set rather than describing the selection -- so a
    "decisive" reading would be manufactured by adding a bad candidate.
    """
    ranking = Ranking(
        criterion=Criterion.AIC,
        delta_ic=np.array([[0.0, 4.0, 9.0], [0.0, np.nan, np.nan]]),
        weights=np.zeros((2, 3)),
        ic_best=np.zeros(2),
        best_index=np.array([0, 0], dtype=np.int64),
        n_valid=np.array([3, 1], dtype=np.int64),
    )
    margin = selection_margin(ranking)
    assert margin[0] == 4.0
    assert np.isnan(margin[1]), (
        "a point with one rankable candidate has no next-best, so it has no "
        "margin; a 0.0 here would put it in the most ambiguous bin"
    )


def test_kappa_binning_is_unchanged_when_only_the_warm_arms_kappa_moves():
    """(j7): the stratification cannot be moved by the thing being measured.

    Behaviour under test: that the `κ` axis reads the COLD arm and nothing
    else. Both values are sitting right there in `AuditArms.results`, and D9
    flags this as the one most likely to be got wrong later.

    Expected values determined independently: the perturbation moves the warm
    arm's `κ` from `1e3` to `1e40` -- across BOTH fixed boundaries -- and the
    test asserts that the warm arm's own binning really did change before it
    asserts the report's did not. **Without that first assertion the test
    passes against an implementation that bins by the warm arm and a fixture
    where both arms happen to agree**, which is the vacuity mode named in the
    pre-flight.

    Bug this catches: binning by `warm.hessian_cond`. Conditioning on a
    post-treatment variable: warm-starting changes the curvature at the
    optimum it finds, so cells would migrate between strata according to the
    mechanism under test, and a stratum's disagreement rate would be partly a
    statement about which cells warm-starting moved into it.
    """
    batch = 40
    cold_kappa = np.full((batch, 2), 1.0e3)
    warm_kappa = np.full((batch, 2), 1.0e40)
    assert not np.array_equal(kappa_bin(cold_kappa), kappa_bin(warm_kappa)), (
        "the perturbation must cross a boundary, or this test is vacuous"
    )

    cold = _result(batch, hessian_cond=cold_kappa)
    unperturbed = _report(cold, _result(batch, hessian_cond=cold_kappa.copy()))
    perturbed = _report(cold, _result(batch, hessian_cond=warm_kappa))

    before = [(s.candidate, s.kappa, s.members) for s in unperturbed.cell_strata]
    after = [(s.candidate, s.kappa, s.members) for s in perturbed.cell_strata]
    assert before == after
    # And the members really are somewhere, so "unchanged" is not "both empty".
    assert sum(count for _, _, count in before) == batch * len(_SPECS)


def test_the_winning_candidate_stratum_reads_the_cold_arm_too():
    """(j7) at the axis D9 does not state it for.

    Behaviour under test: the per-POINT strata group by the COLD arm's winner.
    D9 gives the guard for `κ` and is silent about the winner, and the
    argument is identical -- with a sharper edge, since the metric being
    measured IS whether the winner moved.

    Expected values determined independently: the fixture makes the cold arm
    win candidate 0 at every point and the warm arm win candidate 1, so the
    two groupings are disjoint. Every point must land in candidate 0's strata.

    Bug this catches: grouping by `warm.ranking.best_index`. Every
    disagreeing point would then be filed under the candidate warm-starting
    moved it TO -- so "candidate 1 disagrees most" could be reporting nothing
    but the direction of the movement.
    """
    batch = 40
    cold = _result(batch, best_index=np.zeros(batch, dtype=np.int64))
    warm = _result(batch, best_index=np.ones(batch, dtype=np.int64))
    report = _report(cold, warm)

    by_candidate: dict[int, int] = {}
    for stratum in report.point_strata:
        by_candidate.setdefault(stratum.candidate_index, 0)
        by_candidate[stratum.candidate_index] += stratum.members
    assert by_candidate[0] == batch
    assert by_candidate[1] == 0

    # ...and the disagreement it measures is total, which is what makes the
    # grouping choice consequential rather than cosmetic here.
    rates = [
        s.selection_disagreement.value
        for s in report.point_strata
        if s.members >= MIN_STRATUM_MEMBERS
    ]
    assert rates and all(rate == 1.0 for rate in rates)


# --------------------------------------------------------------------------
# D8: no pooled figure, the 30-member boundary, and visible withholding
# --------------------------------------------------------------------------


def test_no_reported_number_exists_without_a_stratum_to_quote_it_with():
    """D8's core, asserted over the OUTPUT rather than over the source.

    Behaviour under test: every number the report emits is attached to a
    stratum, a candidate or a named partition, and every headline names the
    stratum it came from.

    Expected values determined independently: the check walks the report's own
    dataclass fields, so it does not encode the field list this implementation
    happens to have -- a pooled figure added later under any name has to appear
    as a bare float, which is what fails here.

    Bug this catches: a pooled mean reintroduced "for convenience", which is
    how the artifact returns. Grepping the module for `mean(` would test the
    spelling; the per-stratum signed-trend mean is a legitimate `mean(` and the
    pooled one need not contain the word at all.
    """
    report = _report(_result(40), _result(40))

    allowed_scalars = {
        "seed",
        "kappa_boundaries",
        "margin_boundaries",
        "min_stratum_members",
    }
    for field in fields(report):
        if field.name in allowed_scalars:
            continue
        value = getattr(report, field.name)
        assert not isinstance(value, float | int), (
            f"AuditReport.{field.name} is a bare number with no stratum "
            "attached; that is the pooled figure D8 withholds"
        )

    for quantity in report.quantities():
        assert quantity.scope, quantity.name
        assert (quantity.value is None) == (quantity.withheld is not None)
    for headline in report.headlines:
        assert (headline.value is None) == (headline.stratum is None), (
            f"headline {headline.name} must name the stratum it came from, or "
            "it is a pooled number wearing a maximum's clothes"
        )


def test_a_quantity_reported_over_everything_cannot_be_constructed():
    """The pooled figure is unbuildable, not merely undesirable.

    Behaviour under test: `Quantity`'s scope check, and its value/withheld
    exclusivity.

    Bug this catches: a scope defaulted to `""` so a caller can leave it out.
    D8's whole argument is that labelling a number does not stop it being
    quoted -- so the number must not exist. A scope that can be empty is a
    pooled figure with an extra step.
    """
    with pytest.raises(ValueError, match="no scope"):
        Quantity("pooled_disagreement", "", 0.5, 100)
    with pytest.raises(ValueError, match="either a value or a reason"):
        Quantity("half_stated", "candidate=x", None, 0)
    with pytest.raises(ValueError, match="either a value or a reason"):
        Quantity("both_stated", "candidate=x", 0.5, 10, "withheld anyway")


def test_a_twenty_nine_member_stratum_reports_a_count_and_a_thirty_member_one_a_rate():
    """The 30-member boundary, from both sides, one member apart.

    Behaviour under test: (a2b)'s third outing -- a rate invalid under a
    condition the code can detect is made UNAVAILABLE, and the member count is
    reported in its place.

    Expected values determined independently: `MIN_STRATUM_MEMBERS` is 30, so
    the fixture puts exactly 30 both-OK cells in candidate 0 and exactly 29 in
    candidate 1 by failing the warm arm at one cell. `n = 30` has a binomial
    standard error of ~9% at `p = 0.5`; 29 is not a different amount of
    information, which is exactly why the boundary has to be asserted rather
    than felt.

    Bug this catches: `>` where `>=` belongs, which quotes a rate over 29
    members. A one-member error in a minimum is invisible in every output --
    the number that appears is a real rate over a real stratum, just one the
    derivation says is not quotable.
    """
    batch = 30
    outcome = np.full((batch, 2), Outcome.OK.code, dtype=np.uint8)
    warm_outcome = outcome.copy()
    warm_outcome[0, 1] = Outcome.ITER_CAP_LARGE_GRAD.code
    report = _report(_result(batch), _result(batch, outcome=warm_outcome))

    populated = {
        (s.candidate_index, s.kappa): s for s in report.cell_strata if s.members
    }
    thirty = populated[(0, KappaBin.WELL_CONDITIONED)]
    twenty_nine = populated[(1, KappaBin.WELL_CONDITIONED)]
    assert thirty.members == 30
    assert twenty_nine.members == 29

    assert thirty.mean_signed_trend.value is not None
    assert thirty.mean_signed_trend.withheld is None
    assert twenty_nine.mean_signed_trend.value is None
    reason = twenty_nine.mean_signed_trend.withheld
    assert reason is not None and "29 members" in reason

    # The MAXIMA are not withheld at 29, and that is deliberate: the 30 is
    # derived for estimating a population parameter from n draws, and the
    # largest of 29 members is an exact statement about those 29.
    assert twenty_nine.max_abs_delta_loglik.value is not None
    assert twenty_nine.max_parameter_distance.value is not None


def test_the_thirty_member_boundary_on_a_RATE_reports_one_and_withholds_the_other():
    """The plan's own boundary case, on a rate rather than on a mean.

    Behaviour under test: `>=` where a `>` would go. D8's rule is stated about
    a RATE -- *"a stratum below 30 members reports its member count in place of
    a rate"* -- and the selection disagreement rate is the metric it is stated
    about.

    Expected values determined independently: `MIN_STRATUM_MEMBERS` is 30. The
    fixture gives candidate 0 exactly 30 points and candidate 1 exactly 29, all
    in the same margin bin, so the two strata differ by ONE member and by
    nothing else -- same bin, same agreement, same denominatorless arithmetic.

    Bug this catches: `denominator <= floor` or `< floor - 1`, either of which
    quotes a rate over 29 members. **Found as a surviving mutant**: the sibling
    test asserts this boundary on `mean_signed_trend`, which goes through a
    different helper, so an off-by-one in the RATE helper was invisible to the
    whole suite.
    """
    batch = 59
    best = np.zeros(batch, dtype=np.int64)
    best[30:] = 1
    report = _report(
        _result(batch, best_index=best), _result(batch, best_index=best.copy())
    )
    strata = {
        (s.candidate_index, s.margin): s for s in report.point_strata if s.members
    }
    thirty = strata[(0, MarginBin.WEAK)]
    twenty_nine = strata[(1, MarginBin.WEAK)]
    assert (thirty.members, twenty_nine.members) == (30, 29)

    assert thirty.selection_disagreement.value == 0.0
    assert thirty.selection_disagreement.withheld is None
    assert twenty_nine.selection_disagreement.value is None
    reason = twenty_nine.selection_disagreement.withheld
    assert reason is not None and "29 members" in reason
    # The count is what is reported IN PLACE of the rate, so it is still there.
    assert twenty_nine.selection_disagreement.denominator == 29


def test_a_withheld_stratum_is_present_in_the_output_carrying_its_count():
    """Silence and absence are the same bytes, so neither is used.

    Behaviour under test: a stratum whose rate is withheld still appears, with
    its member count and a sentence saying why there is no rate. The same
    argument that makes `RSS measurement validity` print at zero.

    Expected values determined independently: with 5 members every rate and
    mean is below the 30-member floor, so every one of them must be present and
    withheld -- and the empty strata must be present too, since a
    stratification that emits only its populated cells cannot report that a bin
    was unreachable.

    Bug this catches: dropping withheld strata from the output, or emitting
    `None` with no reason. A reader then cannot tell "we measured this stratum
    and it holds four cells" from "this stratum does not exist", and supplies
    the more flattering of the two.
    """
    report = _report(_result(5), _result(5))

    assert len(report.cell_strata) == len(_SPECS) * len(KAPPA_BINS)
    assert len(report.point_strata) == len(_SPECS) * len(MARGIN_BINS)

    withheld = report.withheld()
    assert withheld, "every rate here is below the floor and must be withheld"
    for quantity in withheld:
        assert quantity.withheld
        assert quantity.scope
    populated = [s for s in report.cell_strata if s.members]
    assert populated, "an all-empty report would make this vacuous"
    for stratum in populated:
        assert stratum.mean_signed_trend.value is None
        reason = stratum.mean_signed_trend.withheld
        assert reason is not None and str(stratum.members) in reason


def test_the_pooled_figure_and_the_unreachable_bins_are_named_in_the_notes():
    """Two withholdings that are properties of every run, stated on every run.

    Behaviour under test: the report says the pooled figure was withheld and
    why, and names the `κ` bins that no cell it covers can occupy.

    Expected values determined independently: `optimize.HESSIAN_COND_LIMIT` is
    `float(EPS) ** -0.5`, which is `2**26` -- the first `κ` boundary. A fit
    above it reports `DEGENERATE_HESSIAN`, so it is not in the both-OK
    intersection, so bins `[2**26, 2**52)` and `>= 2**52` are unreachable here.

    Bug this catches: shipping the four bins with no note. Zero members in the
    two ill-conditioned bins then reads as *"the audit found no ill-conditioned
    cells"* -- a reassuring finding about the field, when it is an arithmetic
    consequence of the outcome taxonomy and would read identically on a field
    made entirely of them.
    """
    from metamer.core.optimize import HESSIAN_COND_LIMIT

    assert HESSIAN_COND_LIMIT == KAPPA_BOUNDARIES[0]
    report = _report(_result(40), _result(40))

    assert report.unreachable_kappa_bins == (
        KappaBin.HALF_PRECISION,
        KappaBin.SINGULAR,
    )
    assert any("No pooled disagreement figure" in note for note in report.notes)
    assert any("DEGENERATE_HESSIAN" in note for note in report.notes)
    # The boundaries travel WITH the figures, or two runs' per-stratum numbers
    # are no more comparable than the pooled one was.
    assert report.kappa_boundaries == KAPPA_BOUNDARIES
    assert report.margin_boundaries == MARGIN_BOUNDARIES
    assert report.min_stratum_members == MIN_STRATUM_MEMBERS


# --------------------------------------------------------------------------
# The partition: flips with their own denominators, and the intersection
# --------------------------------------------------------------------------


def test_the_rescue_and_loss_rates_use_the_denominators_they_name():
    """Two rates, two bases, and a single flip rate reproduces neither.

    Behaviour under test: D9's table -- rescue over COLD-FAILED cells, loss
    over COLD-OK cells, both per candidate.

    Expected values determined independently, by hand on a constructed
    fixture. Candidate 0 over 70 points: the cold arm fails 30 and fits 40; the
    warm arm rescues 9 of the 30 and loses 8 of the 40. So

        rescue = 9 / 30 = 0.30      loss = 8 / 40 = 0.20

    and a single "flip rate" over the 70 attempted cells would be
    `17 / 70 = 0.2428...`, which is neither. **The two denominators are chosen
    unequal precisely so that one base cannot pass for the other**; at 30 and
    30 the defect would reproduce both numbers.

    Bug this catches: one flip rate over an unstated base. §11.2 asks whether
    warm-starting rescues fits or destroys them, and those are opposite
    findings sharing a numerator's worth of cells.
    """
    batch = 70
    cold_outcome = np.full((batch, 2), Outcome.OK.code, dtype=np.uint8)
    cold_outcome[:30, 0] = Outcome.ITER_CAP_LARGE_GRAD.code
    warm_outcome = cold_outcome.copy()
    warm_outcome[:9, 0] = Outcome.OK.code  # 9 rescues out of 30 cold failures
    warm_outcome[30:38, 0] = Outcome.TRUST_RADIUS_COLLAPSED.code  # 8 of 40 lost

    report = _report(
        _result(batch, outcome=cold_outcome), _result(batch, outcome=warm_outcome)
    )
    first = report.candidates[0]
    assert first.cold_failed == 30
    assert first.cold_ok == 40
    assert first.attempted == 70
    assert first.rescue.value == pytest.approx(9 / 30)
    assert first.rescue.denominator == 30
    assert first.loss.value == pytest.approx(8 / 40)
    assert first.loss.denominator == 40
    assert first.rescue.value != pytest.approx(17 / 70)
    assert first.loss.value != pytest.approx(17 / 70)

    # The intersection is 32 of 70 attempted, so every per-cell figure for this
    # candidate is conditioned on survival -- and the report says so.
    assert first.both_ok == 32
    assert first.both_ok_fraction.value == pytest.approx(32 / 70)
    assert any("CONDITIONED ON SURVIVAL" in note for note in report.notes)


def test_a_not_attempted_cell_is_in_no_flip_denominator():
    """The failure denominators are §8.6's, not `!= OK`.

    Behaviour under test: `Outcome.is_failure` and `Outcome.is_eligible` decide
    the bases, so a cell that was never tried or had insufficient data is not
    counted as a fit the warm arm failed to rescue.

    Expected values determined independently: of 40 points, candidate 0 has 10
    `NOT_ATTEMPTED` and 10 `INSUFFICIENT_DATA` cold, 10 failures and 10 OK. The
    rescue denominator is therefore 10, not 30; the attempted count is 30, not
    40.

    Bug this catches: `cold_failed = outcome != OK.code`, which is the obvious
    spelling. `INSUFFICIENT_DATA` is land, permanent ice or too few samples --
    a legitimate expected outcome the taxonomy excludes by name -- and folding
    it in divides by a population that was never at risk, making every rescue
    rate smaller in proportion to how much land is in the tile.
    """
    batch = 40
    cold_outcome = np.full((batch, 2), Outcome.OK.code, dtype=np.uint8)
    cold_outcome[:10, 0] = Outcome.NOT_ATTEMPTED.code
    cold_outcome[10:20, 0] = Outcome.INSUFFICIENT_DATA.code
    cold_outcome[20:30, 0] = Outcome.ITER_CAP_LARGE_GRAD.code

    report = _report(
        _result(batch, outcome=cold_outcome), _result(batch, outcome=cold_outcome)
    )
    first = report.candidates[0]
    assert first.cold_failed == 10
    assert first.cold_ok == 10
    assert first.attempted == 30


def test_a_point_ranked_by_only_one_arm_is_counted_and_dilutes_no_rate():
    """The point-level metric has its own partition and its own denominator.

    Behaviour under test: selection disagreement is measured where BOTH arms
    produced a winner. A point one arm ranked and the other did not is counted
    in `PointConditioning` and is **not** in any stratum's denominator.

    Expected values determined independently, by hand. Of 40 points: 5 have no
    cold winner, 5 have a cold winner and no warm one, and 30 are ranked by
    both. Ten of those 30 genuinely disagree. So

        selection disagreement = 10 / 30 = 0.3333...

    and an implementation that let the 5 one-armed points into the stratum
    would report `10 / 35 = 0.2857...` -- **the numerator cannot change, so the
    defect is visible only in the denominator**, which is why the fixture
    carries real disagreements rather than none.

    Bug this catches: dropping the both-ranked filter from the stratum
    membership. Every rate is then DILUTED by points the metric is not defined
    at -- silently, and always in the reassuring direction. A fixture with zero
    disagreements cannot see it at all, since `0/30` and `0/35` are the same
    number; **that fixture is what let this survive its first mutation
    sweep.**

    It also catches `cold.best_index != warm.best_index` over every row: `-1`
    compares unequal to everything, so every unranked point becomes a selection
    disagreement -- and "the warm arm selected nothing here" is a fit appearing
    or vanishing, which D9 counts as the outcome flip and a different quantity.
    """
    batch = 40
    cold_best = np.zeros(batch, dtype=np.int64)
    cold_best[:5] = -1
    warm_best = np.zeros(batch, dtype=np.int64)
    warm_best[5:10] = -1
    warm_best[10:20] = 1  # ten real disagreements among the both-ranked points

    report = _report(
        _result(batch, best_index=cold_best), _result(batch, best_index=warm_best)
    )
    assert report.points.audited_points == 40
    assert report.points.both_ranked == 30
    assert report.points.cold_only_winner == 5
    assert report.points.warm_only_winner == 5

    stratum = next(
        s
        for s in report.point_strata
        if s.candidate_index == 0 and s.margin is MarginBin.WEAK
    )
    assert stratum.members == 30
    assert stratum.selection_disagreement.denominator == 30
    assert stratum.selection_disagreement.value == pytest.approx(10 / 30)
    assert stratum.selection_disagreement.value != pytest.approx(10 / 35)
    assert stratum.selection_disagreement.value != pytest.approx(20 / 40)


# --------------------------------------------------------------------------
# The per-cell metrics
# --------------------------------------------------------------------------


def test_the_parameter_distance_is_scaled_by_the_unconstrained_error():
    """§11.2's unit, pinned: unconstrained difference over unconstrained SE.

    Behaviour under test: `parameter_distance` reads
    `theta_err_unconstrained`, not `theta_err`.

    Expected values determined independently: the fixture sets the cold
    unconstrained SE to 1, 2 and 4 across candidate 1's three free parameters
    and displaces the warm optimum by 8 in each, so the distances are 8, 4 and
    2 SE. `_result` makes `theta_err` ten times the unconstrained array, so an
    implementation reading it would report 0.8, 0.4 and 0.2.

    Bug this catches: dividing an unconstrained distance by a natural-unit
    standard error. Both arrays have the same shape and neither is NaN, so the
    result is a plausible number of a quantity nobody named -- and under a
    `Log` transform the factor is `theta` itself, which is exactly the regime
    where §11.2 says the audit matters most.
    """
    batch = 5
    se = np.ones((batch, 2, _P_MAX))
    se[:, 1, :3] = [1.0, 2.0, 4.0]
    warm_u = np.zeros((batch, 2, _P_MAX))
    warm_u[:, 1, :3] = 8.0

    cold = _result(batch, theta_err_u=se)
    warm = _result(batch, theta_u=warm_u)
    got = parameter_distance(_arms(cold, warm), _SPECS)

    np.testing.assert_allclose(got[0, 1, :3], [8.0, 4.0, 2.0])
    assert not np.allclose(got[0, 1, :3], [0.8, 0.4, 0.2])
    # The padding stays NaN: candidate 0 has one free parameter, not three.
    assert np.all(np.isnan(got[:, 0, 1:]))


def test_the_aggregate_parameter_distance_is_the_largest_of_its_per_term_ones():
    """§11.2's per-term split, and the exact relation to the aggregate.

    Behaviour under test: the per-term quantities are the components of the
    aggregate, so the two cannot drift apart, and one term carrying the whole
    signal is visible AS that term.

    Expected values determined independently: the three per-parameter
    distances are 2, 7 and 3 SE, so the aggregate is 7 and it belongs to the
    second free parameter.

    Bug this catches: an aggregate computed as a Euclidean norm over the
    terms, `sqrt(4 + 49 + 9) = 7.87`. §11.2's whole reason for demanding the
    split is that a pure label-switching signal concentrated in one term gets
    AVERAGED INTO the aggregate and attributed to warm starting -- and a norm
    is that averaging. It also catches the split being dropped: a report with
    no per-term quantities has no way to tell the two apart.
    """
    batch = 40
    se = np.ones((batch, 2, _P_MAX))
    warm_u = np.zeros((batch, 2, _P_MAX))
    warm_u[:, 1, :3] = [2.0, 7.0, 3.0]

    report = _report(_result(batch, theta_err_u=se), _result(batch, theta_u=warm_u))
    stratum = next(
        s
        for s in report.cell_strata
        if s.candidate_index == 1 and s.kappa is KappaBin.WELL_CONDITIONED
    )
    assert stratum.max_parameter_distance.value == pytest.approx(7.0)
    assert [q.value for q in stratum.per_term_parameter_distance] == pytest.approx(
        [2.0, 7.0, 3.0]
    )
    assert stratum.max_parameter_distance.value != pytest.approx(np.sqrt(62.0))
    labels = [q.name for q in stratum.per_term_parameter_distance]
    assert len(labels) == _EXTENTS[1] and len(set(labels)) == _EXTENTS[1]


def test_the_signed_trend_headline_ranks_on_magnitude_and_keeps_its_sign():
    """A maximum over signed values is blind to the opposite bias.

    Behaviour under test: `Headline`'s one exception to "the worst stratum is
    the maximum". §11.2 calls a biased signed difference systematic
    contamination, and it is contamination in either direction.

    Expected values determined independently: candidate 0's stratum carries a
    trend difference of `+1.0` and candidate 1's carries `-3.0`. Ranking on the
    raw value returns `+1.0`; ranking on magnitude returns the stratum at
    `-3.0`, and the headline reports it SIGNED.

    Bug this catches: `max(values)` applied uniformly to all five metrics
    because D8 says the headline is the maximum. On this fixture that publishes
    `+1.0` and never mentions a stratum three times as contaminated in the
    other direction -- and the sign is the whole content of the metric, so
    reporting `3.0` unsigned is the other half of the same error.
    """
    batch = 40
    beta = np.zeros((batch, 2, _K_BETA))
    beta[:, 0, 1] = 1.0
    beta[:, 1, 1] = -3.0
    report = _report(_result(batch), _result(batch, beta=beta))

    headline = next(h for h in report.headlines if h.name.startswith("mean_signed"))
    assert headline.value == pytest.approx(-3.0)
    assert headline.stratum is not None and "candidate=" in headline.stratum
    assert headline.value != pytest.approx(1.0)
    assert headline.value != pytest.approx(3.0), "the sign is the metric"


def test_a_lint_flagged_candidate_is_audited_apart_and_a_clean_set_is_not():
    """D8's third option, with its positive control.

    Behaviour under test: a lint-flagged candidate set produces a per-stratum
    report with the flagged candidate marked and its findings NAMED, and a
    lint-clean set produces the same report SHAPE with nothing marked.

    Expected values determined independently: the candidate axis already
    separates candidates, so "its own stratum" needs no new axis -- what is
    owed is the marking and the naming, which D8 requires (*"names the flagged
    pair"*). The positive control is the shape equality: same strata, same
    counts, same headlines.

    Bug this catches: refusing a flagged set, which denies an audit to the
    users most at risk -- and, in the other direction, a report that silently
    treats a flagged set the same as a clean one. It also catches "the lint was
    not run" reporting as "the lint found nothing": a diagnostic that reports
    clean because it could not run is worse than one that stops.
    """
    batch = 40
    flagged_hash = _SPECS[1].spec_hash()
    clean = _report(_result(batch), _result(batch), lint_findings={})
    flagged = _report(
        _result(batch),
        _result(batch),
        lint_findings={flagged_hash: ("same_kind_free_timescales",)},
    )

    assert [s.members for s in clean.cell_strata] == [
        s.members for s in flagged.cell_strata
    ]
    assert [h.value for h in clean.headlines] == [h.value for h in flagged.headlines]

    assert not any(s.lint_flagged for s in clean.cell_strata)
    assert [c.lint_flagged for c in flagged.candidates] == [False, True]
    assert flagged.candidates[1].lint_findings == ("same_kind_free_timescales",)
    assert any("same_kind_free_timescales" in note for note in flagged.notes)
    assert not any("lint-flagged" in note for note in clean.notes)

    # And a report built with no lint at all says so, rather than reading as
    # clean -- the third state the boolean cannot carry.
    unrun = _report(_result(batch), _result(batch))
    assert any("lint was NOT run" in note for note in unrun.notes)
    assert not any("lint was NOT run" in note for note in clean.notes)


def test_a_design_with_no_trend_column_reports_absence_and_not_zero():
    """The scientific payload's absence is a property, not a measurement.

    Behaviour under test: `trend_column=None` makes every signed-trend
    quantity unavailable with a reason, rather than producing zeros.

    Expected values determined independently: `beta` differs between the arms
    in the fixture, so an implementation reading column 0 by default would
    report a real non-zero number.

    Bug this catches: defaulting the trend column to 0 or 1 when the design has
    none. §11.2 calls signed-trend disagreement the actual scientific payload;
    a mean of exactly 0.0 over every stratum reads as the strongest possible
    reassurance and would be a statement about a column that is not a trend.
    """
    batch = 40
    beta = np.zeros((batch, 2, _K_BETA))
    beta[:, :, 0] = 5.0
    beta[:, :, 1] = 5.0
    arms = _arms(_result(batch), _result(batch, beta=beta))
    report = audit_report(arms, trend_column=None)

    for stratum in report.cell_strata:
        assert stratum.mean_signed_trend.value is None
        assert stratum.mean_signed_trend.withheld
    headline = next(h for h in report.headlines if h.name.startswith("mean_signed"))
    assert headline.value is None
    assert any("no trend column" in note for note in report.notes)
