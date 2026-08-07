"""Tests for the information criteria and the comparability guards.

Every expected value here is derived on paper from the published definition of
the criterion, not copied out of a run of the code under test. Where a number
is not obviously right by inspection the test uses an *analytic endpoint*
instead -- a sample size at which two criteria coincide exactly, so the
assertion is an identity rather than a tolerance band:

    n = e^2   makes BIC's penalty  k ln n      equal AIC's  2k
    n = e^e   makes HQIC's penalty 2k ln ln n  equal AIC's  2k
    n = 25    makes AICc's correction 2k(k+1)/(n-k-1) equal exactly 2 at k = 4

An identity cannot be satisfied by a formula that is off by a constant factor
inside the logarithm, which a hand-transcribed expected value can.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from metamer.core.capability import EngineId, Objective
from metamer.core.counting import penalty_terms
from metamer.core.criteria import (
    CandidateScores,
    ComparabilityError,
    Criterion,
    Ranking,
    ic_value,
    rank_candidates,
)
from metamer.core.outcomes import Outcome
from metamer.core.terms import ProcessSpec
from tests.test_statespace import _term


def _outcomes(*rows: tuple[Outcome, ...]) -> np.ndarray:
    """Build a (B, M) outcome-code array from Outcome members."""
    return np.array([[o.code for o in row] for row in rows], dtype=np.uint8)


def _scores(
    loglik: np.ndarray | list[list[float]],
    *,
    k: float | np.ndarray = 2.0,
    n: float | np.ndarray = 100.0,
    n_eff: float | np.ndarray | None = None,
    engines: tuple[EngineId, ...] | None = None,
    objectives: tuple[Objective, ...] | None = None,
    outcome: np.ndarray | None = None,
) -> CandidateScores:
    """Assemble a (B, M) candidate score block with sensible defaults."""
    values = np.asarray(loglik, dtype=np.float64)
    shape = values.shape

    def _fill(value):
        return np.broadcast_to(np.asarray(value, dtype=np.float64), shape).copy()

    return CandidateScores(
        labels=tuple(f"c{i}" for i in range(shape[1])),
        engines=engines or (EngineId.KALMAN,) * shape[1],
        objectives=objectives or (Objective.ML,) * shape[1],
        loglik=values,
        k=_fill(k),
        n=_fill(n),
        n_eff=_fill(n if n_eff is None else n_eff),
        outcome=(
            np.full(shape, Outcome.OK.code, dtype=np.uint8)
            if outcome is None
            else outcome
        ),
    )


# --------------------------------------------------------------------------
# ic_value: the arithmetic
# --------------------------------------------------------------------------


def test_criterion_formulae_match_their_published_definitions():
    """AIC, AICc, BIC and HQIC evaluate to their textbook expressions.

    Behaviour under test: the arithmetic of each criterion.
    Bug this catches: a dropped factor of two on the fit term (AIC is
    `2k - 2l`, not `2k - l`), or a penalty that uses `k` where it wants `2k`.
    Expected values transcribed from the published formulae with l = -100,
    k = 4, n = 50, so the fit term is exactly 200.
    """
    loglik, k, n = -100.0, 4.0, 50.0
    assert float(ic_value(Criterion.AIC, loglik, k, n, n)) == pytest.approx(2 * 4 + 200)
    assert float(ic_value(Criterion.BIC, loglik, k, n, n)) == pytest.approx(
        4 * math.log(50) + 200
    )
    assert float(ic_value(Criterion.AICC, loglik, k, n, n)) == pytest.approx(
        2 * 4 + 200 + 2 * 4 * 5 / (50 - 4 - 1)
    )
    assert float(ic_value(Criterion.HQIC, loglik, k, n, n)) == pytest.approx(
        2 * 4 * math.log(math.log(50)) + 200
    )


def test_criteria_coincide_with_aic_at_their_analytic_endpoints():
    """Each penalty reduces to AIC's `2k` at the sample size that makes it so.

    Behaviour under test: the exact form of each penalty, checked as an
    identity rather than against a transcribed number.
    Bug this catches: a factor slipped inside a logarithm -- `k ln(2n)`,
    `2k ln ln(n^2)`, or a natural log written as log10. None of those changes
    the ranking on a fixture, and all of them break these identities.
    """
    loglik, k = -100.0, 4.0
    aic = float(ic_value(Criterion.AIC, loglik, k, 50.0, 50.0))

    # ln(e^2) = 2, so BIC's k ln n is 2k.
    assert float(ic_value(Criterion.BIC, loglik, k, math.e**2, 1.0)) == pytest.approx(
        aic
    )
    # ln(ln(e^e)) = ln(e) = 1, so HQIC's 2k ln ln n is 2k.
    assert float(ic_value(Criterion.HQIC, loglik, k, math.e**math.e, 1.0)) == (
        pytest.approx(aic)
    )
    # 2k(k+1)/(n-k-1) = 40/20 = 2 exactly at k = 4, n = 25.
    assert float(ic_value(Criterion.AICC, loglik, k, 25.0, 25.0)) == pytest.approx(
        aic + 2.0
    )
    # BIC_NEFF is BIC with n_eff in place of n, so it coincides when they agree.
    assert float(
        ic_value(Criterion.BIC_NEFF, loglik, k, 999.0, math.e**2)
    ) == pytest.approx(aic)


def test_bic_neff_loosens_the_penalty_by_exactly_the_log_ratio():
    """`bic_neff` is smaller than `bic` by `k (ln n - ln n_eff)`.

    Behaviour under test: `n_eff` substitutes for `n` in the penalty with no
    clamping or floor applied on the way.
    Bug this catches: flooring `n_eff` before the logarithm. A floor at 2.0
    makes `bic_neff` equal to `bic` at n = 2, n_eff = 1.5 -- verified: both
    penalties are 2.7725887 -- which silently contradicts the requirement that
    it be strictly smaller whenever `n_eff < n`. A `loose < strict` assertion
    passes anyway whenever the fixture's `n_eff` sits above the floor.
    """
    loglik, k, n, n_eff = -100.0, 4.0, 500.0, 12.0
    strict = float(ic_value(Criterion.BIC, loglik, k, n, n_eff))
    loose = float(ic_value(Criterion.BIC_NEFF, loglik, k, n, n_eff))
    assert loose < strict
    assert strict - loose == pytest.approx(k * (math.log(n) - math.log(n_eff)))

    # The floored case: a floor at 2.0 would make these two equal.
    tight = float(ic_value(Criterion.BIC, loglik, k, 2.0, 1.5))
    floored = float(ic_value(Criterion.BIC_NEFF, loglik, k, 2.0, 1.5))
    assert floored < tight


def test_log_criteria_refuse_a_sample_size_their_penalty_cannot_use():
    """BIC and HQIC return NaN where their penalty stops penalizing.

    Behaviour under test: the domain of each log-based penalty.
    Bug this catches: evaluating them anyway. Verified numerically: at n = 1,
    BIC's penalty is exactly 0.0 (no penalty at all, so the most complex
    candidate always wins) and HQIC's is -inf (that candidate wins with weight
    1 whatever its fit); at n = 2, HQIC's penalty is -2.93, i.e. it *rewards*
    parameters. `n = 1` is reachable: `penalty_terms` only guarantees REML's
    `n_obs - design_rank >= 1`.
    """
    loglik, k = -100.0, 4.0
    assert math.isnan(float(ic_value(Criterion.BIC, loglik, k, 1.0, 1.0)))
    assert math.isnan(float(ic_value(Criterion.HQIC, loglik, k, 1.0, 1.0)))
    assert math.isnan(float(ic_value(Criterion.HQIC, loglik, k, 2.0, 2.0)))
    assert math.isnan(float(ic_value(Criterion.HQIC, loglik, k, math.e, 1.0)))
    assert math.isnan(float(ic_value(Criterion.BIC_NEFF, loglik, k, 500.0, 1.0)))
    # Just inside the domain the penalty is finite and positive.
    assert float(ic_value(Criterion.BIC, loglik, k, 1.5, 1.5)) > 200.0
    assert float(ic_value(Criterion.HQIC, loglik, k, 3.0, 3.0)) > 200.0


def test_aicc_is_positive_infinity_where_its_correction_is_undefined():
    """AICc diverges rather than turning its correction negative.

    Behaviour under test: the `n - k - 1 <= 0` branch.
    Bug this catches: evaluating the correction anyway. At k = 4, n = 4 the
    denominator is -1 and the correction is -40, so AICc would come back 40
    *below* AIC -- an over-parameterized candidate scoring best precisely where
    AICc exists to stop it.
    """
    loglik, k = -100.0, 4.0
    assert float(ic_value(Criterion.AICC, loglik, k, 5.0, 5.0)) == math.inf
    assert float(ic_value(Criterion.AICC, loglik, k, 4.0, 4.0)) == math.inf
    assert float(ic_value(Criterion.AICC, loglik, k, 5.5, 5.5)) < math.inf


def test_ic_value_propagates_a_missing_primitive_as_nan():
    """A NaN log-likelihood, k or n yields NaN, never a number.

    Behaviour under test: failed series carry NaN through the arithmetic.
    Bug this catches: an `n - k - 1 <= 0` test that treats NaN as "not
    positive" and returns +inf, which reads as a real, infinitely-bad score
    rather than as an absent one.
    """
    assert math.isnan(float(ic_value(Criterion.AICC, np.nan, 4.0, 50.0, 50.0)))
    assert math.isnan(float(ic_value(Criterion.AICC, -100.0, 4.0, np.nan, 50.0)))
    assert math.isnan(float(ic_value(Criterion.AIC, -100.0, np.nan, 50.0, 50.0)))
    assert math.isnan(float(ic_value(Criterion.BIC, -100.0, 4.0, np.nan, 50.0)))


def test_ic_value_is_elementwise_over_a_batch():
    """The criteria evaluate over `(B, M)` arrays, not one series at a time.

    Behaviour under test: `ic_value` broadcasts.
    Bug this catches: an implementation that takes Python floats, which forces
    the caller into a per-series loop over 10^7 points.
    """
    loglik = np.array([[-10.0, -20.0], [-30.0, -40.0]])
    values = ic_value(Criterion.AIC, loglik, 3.0, 100.0, 100.0)
    assert values.shape == (2, 2)
    assert values.dtype == np.float64
    np.testing.assert_allclose(values, 6.0 - 2.0 * loglik)


def test_unknown_criterion_is_refused():
    """A criterion name the module does not implement raises.

    Behaviour under test: the fall-through arm of the dispatch.
    Bug this catches: a dispatch that returns None for an unrecognized name,
    which becomes a TypeError several frames away from the cause.
    """
    with pytest.raises(ValueError, match="unknown criterion"):
        ic_value("tic", -100.0, 4.0, 50.0, 50.0)


# --------------------------------------------------------------------------
# The comparability guards
# --------------------------------------------------------------------------


def test_cross_engine_ranking_is_a_hard_error():
    """A Whittle score and a Kalman score are never ranked together.

    Behaviour under test: the engine guard.
    Bug this catches: the silent-failure mode of design doc section 6.2. A
    Whittle score is not an exact log-likelihood; differencing it against a
    Kalman score yields a number that ranks candidates plausibly and wrongly,
    and at 10^7 series nobody inspects the individual fit that would reveal it.
    """
    scores = _scores([[-10.0, -9.0]], engines=(EngineId.KALMAN, EngineId.WHITTLE))
    with pytest.raises(ComparabilityError, match="engine"):
        rank_candidates(scores, Criterion.AIC)


def test_cross_objective_ranking_is_a_hard_error():
    """An ML score and a REML score are never ranked together.

    Behaviour under test: the objective guard.
    Bug this catches: the same failure class one level up. REML is the
    likelihood of error contrasts -- a different random quantity from `y` -- so
    the two numbers are not on a common measure even though both are negative
    and both improve with fit.
    """
    scores = _scores([[-10.0, -9.0]], objectives=(Objective.ML, Objective.REML))
    with pytest.raises(ComparabilityError, match="objective"):
        rank_candidates(scores, Criterion.AIC)


def test_the_guards_fire_even_when_the_mismatched_candidate_failed():
    """A mixed tag set is refused regardless of any candidate's outcome.

    Behaviour under test: the guards read the candidate set's tags, not the
    surviving subset's.
    Bug this catches: deriving the tag sets after masking to `outcome == OK`.
    The mixture would then be reported at some grid points and not others,
    depending on where a fit happened to fail -- so the same misconfigured run
    would raise on one tile and produce a wrong map on the next.
    """
    failed = _outcomes((Outcome.OK, Outcome.NONFINITE_OBJECTIVE))
    scores = _scores(
        [[-10.0, np.nan]],
        engines=(EngineId.KALMAN, EngineId.WHITTLE),
        outcome=failed,
    )
    with pytest.raises(ComparabilityError, match="engine"):
        rank_candidates(scores, Criterion.AIC)


def test_a_uniformly_tagged_candidate_set_is_accepted():
    """Matching tags do not raise.

    Behaviour under test: the guards are a filter, not a blanket refusal.
    Bug this catches: a guard written against the tag *count* rather than the
    number of *distinct* tags, which would refuse every real candidate set.
    """
    scores = _scores([[-10.0, -9.0, -8.0]])
    assert rank_candidates(scores, Criterion.AIC).n_valid.tolist() == [3]


# --------------------------------------------------------------------------
# Ranking, weights, and the failure rules
# --------------------------------------------------------------------------


def test_delta_ic_is_zero_for_the_best_candidate():
    """The winner has delta-IC exactly zero, and `ic_best` is its value.

    Behaviour under test: delta-IC is referenced to the minimum.
    Bug this catches: normalizing against the mean or against candidate 0,
    which makes every delta-IC map uninterpretable and can make the winner's
    own delta negative.
    """
    scores = _scores([[-20.0, -10.0]], k=2.0, n=100.0)
    result = rank_candidates(scores, Criterion.AIC)
    assert result.delta_ic[0, 1] == 0.0
    assert result.best_index.tolist() == [1]
    assert result.delta_ic[0, 0] == pytest.approx(20.0)  # 2*(-10 - -20) * -1
    assert result.ic_best[0] == pytest.approx(2 * 2 + 20.0)
    assert result.criterion is Criterion.AIC


def test_weights_are_the_akaike_form_with_the_half_in_the_exponent():
    """Weights are `exp(-dIC/2)` normalized, not `exp(-dIC)`.

    Behaviour under test: the exponent.
    Bug this catches: dropping the half. Constructed so the answer is exact:
    two candidates with equal k, log-likelihoods differing by ln 3, hence
    dAIC = 2 ln 3 and a weight ratio of exp(-ln 3) = 1/3 -- weights 3/4 and
    1/4. Dropping the half gives a ratio of 1/9 and weights 9/10, 1/10.
    """
    scores = _scores([[-10.0, -10.0 - math.log(3.0)]], k=2.0)
    result = rank_candidates(scores, Criterion.AIC)
    np.testing.assert_allclose(result.weights[0], [0.75, 0.25])


def test_failed_candidates_do_not_poison_the_weight_vector():
    """A failed candidate gets NaN delta-IC, zero weight, and no vote.

    Behaviour under test: design doc section 10.2.
    Bug this catches: letting NaN through `exp(-dIC/2)`, which makes *every*
    weight at that point NaN and destroys the whole model average -- one
    failed candidate silently blanking a grid point that had two good fits.
    """
    outcome = _outcomes((Outcome.OK, Outcome.NONFINITE_OBJECTIVE, Outcome.OK))
    scores = _scores([[-10.0, np.nan, -12.0]], outcome=outcome)
    result = rank_candidates(scores, Criterion.AIC)
    assert np.isnan(result.delta_ic[0, 1])
    assert result.weights[0, 1] == 0.0
    assert result.weights[0, [0, 2]].sum() == pytest.approx(1.0)
    assert result.n_valid.tolist() == [2]
    assert result.best_index.tolist() == [0]


def test_outcome_not_finiteness_decides_which_candidates_survive():
    """A non-OK candidate is excluded even when its numbers look usable.

    Behaviour under test: survival is gated on `outcome == OK`.
    Bug this catches: gating on `isfinite(loglik)` instead. A candidate that
    hit the iteration cap or a diagnostic limit still carries the last finite
    log-likelihood it evaluated; scoring it resurrects a fit the failure
    ladder had already rejected, and it can win.
    """
    outcome = _outcomes((Outcome.OK, Outcome.DIAGNOSTIC_LIMIT))
    scores = _scores([[-10.0, -1.0]], outcome=outcome)
    result = rank_candidates(scores, Criterion.AIC)
    assert result.best_index.tolist() == [0]
    assert result.weights[0, 1] == 0.0
    assert np.isnan(result.delta_ic[0, 1])
    assert result.n_valid.tolist() == [1]


def test_insufficient_data_is_excluded_without_being_counted_as_valid():
    """An INSUFFICIENT_DATA candidate leaves no trace in the weights.

    Behaviour under test: the outcome gate admits exactly OK, so land and
    permanent ice neither win nor inflate `n_valid`.
    Bug this catches: gating on `Outcome.is_failure`, which is False for
    INSUFFICIENT_DATA and NOT_ATTEMPTED -- both would then be scored, and a
    wholly-masked tile would come back with a confident-looking selection.
    """
    outcome = _outcomes((Outcome.INSUFFICIENT_DATA, Outcome.NOT_ATTEMPTED))
    scores = _scores([[-10.0, -9.0]], outcome=outcome)
    result = rank_candidates(scores, Criterion.AIC)
    assert result.n_valid.tolist() == [0]
    assert result.best_index.tolist() == [-1]
    assert np.isnan(result.ic_best[0])
    assert np.all(np.isnan(result.delta_ic))
    assert np.all(result.weights == 0.0)


def test_a_point_with_no_survivor_does_not_disturb_its_neighbours():
    """One dead series does not stop the rest of the batch from ranking.

    Behaviour under test: the all-failed row is handled per series.
    Bug this catches: calling `nanargmin` on an all-NaN row, which raises
    "All-NaN slice encountered" and takes down the whole tile because one
    grid point was land.
    """
    outcome = _outcomes(
        (Outcome.OK, Outcome.OK),
        (Outcome.RANK_DEFICIENT_X, Outcome.INSUFFICIENT_DATA),
        (Outcome.OK, Outcome.OK),
    )
    scores = _scores(
        [[-10.0, -12.0], [np.nan, np.nan], [-30.0, -20.0]], outcome=outcome
    )
    result = rank_candidates(scores, Criterion.AIC)
    assert result.best_index.tolist() == [0, -1, 1]
    assert result.n_valid.tolist() == [2, 0, 2]
    assert result.weights[1].tolist() == [0.0, 0.0]
    assert result.weights[0].sum() == pytest.approx(1.0)
    assert result.weights[2].sum() == pytest.approx(1.0)


def test_every_series_is_ranked_independently_of_the_rest_of_the_batch():
    """Ranking a batch equals ranking each series on its own.

    Behaviour under test: the per-series reduction axis.
    Bug this catches: taking the winner over the flattened array, so one
    series' log-likelihood level -- which is arbitrary, being a function of N
    and of the data's scale -- decides another series' selected model. This is
    the criteria-layer form of the standing batched-equals-solo guard.
    """
    loglik = np.array([[-10.0, -12.0, -11.0], [-300.0, -299.0, -305.0]])
    batched = rank_candidates(_scores(loglik), Criterion.AIC)
    for b in range(loglik.shape[0]):
        solo = rank_candidates(_scores(loglik[b : b + 1]), Criterion.AIC)
        np.testing.assert_allclose(batched.delta_ic[b], solo.delta_ic[0])
        np.testing.assert_allclose(batched.weights[b], solo.weights[0])
        assert batched.best_index[b] == solo.best_index[0]
        assert batched.n_valid[b] == solo.n_valid[0]


def test_k_and_n_are_read_per_series_and_per_candidate():
    """The penalty uses each cell's own `k` and `n`, not a batch-wide one.

    Behaviour under test: `k` and `n` are `(B, M)`.
    Bug this catches: broadcasting candidate 0's `k` across the row, or series
    0's `n` down the column. `penalty_terms` returns `k` that varies with
    `design_rank`, which varies per series with the mask, so a batch-wide read
    is wrong wherever a gap costs a design column.
    """
    loglik = np.full((2, 2), -100.0)
    k = np.array([[1.0, 5.0], [5.0, 1.0]])
    scores = _scores(loglik, k=k, n=100.0)
    result = rank_candidates(scores, Criterion.AIC)
    assert result.best_index.tolist() == [0, 1]
    assert result.delta_ic[0].tolist() == [0.0, 8.0]
    assert result.delta_ic[1].tolist() == [8.0, 0.0]


def test_a_scored_candidate_whose_criterion_is_infinite_still_counts_as_valid():
    """An AICc of +inf is ranked last, not laundered into a failed fit.

    Behaviour under test: `n_valid` counts candidates whose *fit* succeeded,
    which is what makes it criterion-independent -- the store holds one
    `n_valid[y,x]` for all criteria (design doc section 12.2), so it cannot be
    allowed to depend on which criterion was asked for.
    Bug this catches: defining validity as `isfinite(ic)`. Under AICc a short
    record would then report fewer valid candidates than under AIC, from the
    same fits, and the two would disagree in the store.
    """
    scores = _scores([[-10.0, -9.0]], k=4.0, n=5.0)
    result = rank_candidates(scores, Criterion.AICC)
    assert result.n_valid.tolist() == [2]
    assert result.best_index.tolist() == [-1]
    assert np.all(result.weights == 0.0)

    finite = _scores([[-10.0, -9.0]], k=np.array([[4.0, 1.0]]), n=5.0)
    mixed = rank_candidates(finite, Criterion.AICC)
    assert mixed.n_valid.tolist() == [2]
    assert mixed.best_index.tolist() == [1]
    assert mixed.weights[0].tolist() == [0.0, 1.0]
    assert mixed.delta_ic[0, 0] == math.inf


def test_a_scored_candidate_carrying_a_missing_primitive_is_refused():
    """`outcome == OK` beside a NaN log-likelihood is a hard error.

    Behaviour under test: the store's bidirectional status invariant (design
    doc section 12.5) is enforced at this boundary.
    Bug this catches: silently dropping such a cell from the weights. The
    resulting map reads "that candidate failed at this point" when what
    actually happened is that a value slot and its status disagree -- which is
    a defect in the writer, and the only place it is cheap to notice.
    """
    scores = _scores([[-10.0, np.nan]])
    with pytest.raises(ValueError, match="finite"):
        rank_candidates(scores, Criterion.AIC)

    bad_k = _scores([[-10.0, -9.0]], k=np.array([[2.0, np.nan]]))
    with pytest.raises(ValueError, match="finite"):
        rank_candidates(bad_k, Criterion.AIC)


def test_bic_neff_requires_n_eff_only_when_it_is_the_criterion_asked_for():
    """A NaN `n_eff` is fatal for BIC_NEFF and irrelevant to AIC.

    Behaviour under test: `n_eff` is validated per criterion.
    Bug this catches: demanding `n_eff` unconditionally, which would force
    every AIC run to pay `n_eff_bic`'s O(n_used^2) sum -- roughly 400 000
    autocovariance evaluations per series -- for a number no criterion in that
    run reads.
    """
    scores = _scores([[-10.0, -9.0]], n_eff=np.array([[np.nan, np.nan]]))
    assert rank_candidates(scores, Criterion.AIC).best_index.tolist() == [1]
    with pytest.raises(ValueError, match="n_eff"):
        rank_candidates(scores, Criterion.BIC_NEFF)


def test_ranking_returns_the_shapes_and_dtypes_the_store_declares():
    """`Ranking` matches the `/selection/` layout.

    Behaviour under test: the returned shapes.
    Bug this catches: a scalar `best_index` or `n_valid` from reducing over
    the wrong axis -- which type checking will not see, because both are
    integers either way.
    """
    result = rank_candidates(_scores(np.full((4, 3), -10.0)), Criterion.AIC)
    assert isinstance(result, Ranking)
    assert result.delta_ic.shape == (4, 3)
    assert result.weights.shape == (4, 3)
    assert result.best_index.shape == (4,)
    assert result.n_valid.shape == (4,)
    assert result.ic_best.shape == (4,)
    assert result.delta_ic.dtype == np.float64
    assert result.weights.dtype == np.float64
    assert result.best_index.dtype == np.int64
    assert result.n_valid.dtype == np.int64


def test_a_single_candidate_takes_all_the_weight():
    """M = 1 ranks without special-casing.

    Behaviour under test: the degenerate candidate set.
    Bug this catches: a normalization that divides by `M - 1`, or a delta-IC
    that is only defined relative to a *next*-best candidate.
    """
    result = rank_candidates(_scores([[-10.0]]), Criterion.AIC)
    assert result.weights.tolist() == [[1.0]]
    assert result.delta_ic.tolist() == [[0.0]]
    assert result.n_valid.tolist() == [1]


# --------------------------------------------------------------------------
# CandidateScores: shape and tag coherence
# --------------------------------------------------------------------------


def test_mismatched_per_candidate_arrays_are_refused():
    """Every primitive must be `(B, M)`.

    Behaviour under test: the container's own shape checks.
    Bug this catches: a `k` of shape `(M,)` broadcasting silently down the
    batch, which is right only while the mask is uniform across series -- so
    it passes every complete-data test and is wrong on real data.
    """
    with pytest.raises(ValueError, match="k"):
        CandidateScores(
            labels=("a", "b"),
            engines=(EngineId.KALMAN,) * 2,
            objectives=(Objective.ML,) * 2,
            loglik=np.zeros((3, 2)),
            k=np.zeros(2),
            n=np.full((3, 2), 100.0),
            n_eff=np.full((3, 2), 100.0),
            outcome=np.zeros((3, 2), dtype=np.uint8),
        )


def test_tag_tuples_must_have_one_entry_per_candidate():
    """`engines`, `objectives` and `labels` are per candidate.

    Behaviour under test: tag length against the model axis.
    Bug this catches: a single tag passed for the whole set. The comparability
    guard would then be structurally unable to see a mixture, which is the one
    thing it exists to see.
    """
    block = {
        "loglik": np.zeros((3, 2)),
        "k": np.full((3, 2), 2.0),
        "n": np.full((3, 2), 100.0),
        "n_eff": np.full((3, 2), 100.0),
        "outcome": np.zeros((3, 2), dtype=np.uint8),
    }
    with pytest.raises(ValueError, match="engines"):
        CandidateScores(
            labels=("a", "b"),
            engines=(EngineId.KALMAN,),
            objectives=(Objective.ML,) * 2,
            **block,
        )
    with pytest.raises(ValueError, match="objectives"):
        CandidateScores(
            labels=("a", "b"),
            engines=(EngineId.KALMAN,) * 2,
            objectives=(Objective.ML,),
            **block,
        )
    with pytest.raises(ValueError, match="labels"):
        CandidateScores(
            labels=("only",),
            engines=(EngineId.KALMAN,) * 2,
            objectives=(Objective.ML,) * 2,
            **block,
        )


def test_a_one_dimensional_score_block_is_refused():
    """`(M,)` is not a batch of one.

    Behaviour under test: the rank of `loglik`.
    Bug this catches: accepting a bare candidate vector, which then reduces
    over the candidate axis as though it were the batch axis and returns a
    ranking of one series against itself.
    """
    with pytest.raises(ValueError, match="B, M"):
        CandidateScores(
            labels=("a", "b"),
            engines=(EngineId.KALMAN,) * 2,
            objectives=(Objective.ML,) * 2,
            loglik=np.zeros(2),
            k=np.zeros(2),
            n=np.zeros(2),
            n_eff=np.zeros(2),
            outcome=np.zeros(2, dtype=np.uint8),
        )


def test_an_empty_candidate_set_is_refused():
    """M = 0 raises rather than reporting universal failure.

    Behaviour under test: the empty candidate axis.
    Bug this catches: returning `n_valid = 0` everywhere for a run that was
    simply misconfigured, which is indistinguishable in the store from a run
    where every fit failed.
    """
    with pytest.raises(ValueError, match="at least one candidate"):
        CandidateScores(
            labels=(),
            engines=(),
            objectives=(),
            loglik=np.zeros((3, 0)),
            k=np.zeros((3, 0)),
            n=np.zeros((3, 0)),
            n_eff=np.zeros((3, 0)),
            outcome=np.zeros((3, 0), dtype=np.uint8),
        )


def test_penalty_terms_output_feeds_rank_candidates_unchanged():
    """`counting.penalty_terms` composes with this module without adaptation.

    Behaviour under test: the seam between Task 9 and Task 10 -- both sides
    speak per-series float64 with NaN on the failed entries.
    Bug this catches: a criteria layer that takes Python floats, forcing the
    caller to unpack `penalty_terms`' arrays per series and re-derive which
    entries are NaN. That unpacking is where the `rank_x` / `design_rank`
    substitution and the `n_obs - (-1)` off-by-one get reintroduced.
    """
    spec = ProcessSpec((_term("matern12"),))
    outcome = np.array([Outcome.OK.code, Outcome.RANK_DEFICIENT_X.code], dtype=np.uint8)
    k, n = penalty_terms(
        spec,
        Objective.REML,
        n_obs=np.array([100, 100], dtype=np.int64),
        design_rank=np.array([4, 4], dtype=np.int64),
        outcome=outcome,
        k_beta=4,
    )
    # k_theta = 2 for matern12; REML drops beta and 4 contrasts.
    assert k[0] == pytest.approx(2.0)
    assert n[0] == pytest.approx(96.0)

    scores = CandidateScores(
        labels=("m12",),
        engines=(EngineId.KALMAN,),
        objectives=(Objective.REML,),
        loglik=np.array([[-10.0], [np.nan]]),
        k=k[:, None],
        n=n[:, None],
        n_eff=n[:, None],
        outcome=outcome[:, None],
    )
    result = rank_candidates(scores, Criterion.BIC)
    assert result.n_valid.tolist() == [1, 0]
    assert result.ic_best[0] == pytest.approx(2.0 * math.log(96.0) + 20.0)
    assert np.isnan(result.ic_best[1])
