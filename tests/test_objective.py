"""Tests for the concentrated ML and REML objectives.

Every expected value here comes from `tests.oracles` (explicit Sigma, explicit
inverse, published Harville form) or from a hand-stated identity, never from
re-running the code under test.
"""

from dataclasses import replace

import numpy as np
import pytest

from metamer.core.capability import Objective
from metamer.core.engines.kalman import _RANK_RTOL, KalmanEngine
from metamer.core.objective import (
    CONDITION_LOG_LIMIT,
    OUTCOME_PRECEDENCE,
    RANK_DEFICIENT_LOG_LIMIT,
    ConcentratedObjective,
    gls_solution,
    merge_outcomes,
    negative_reduction_mask,
)
from metamer.core.outcomes import Outcome, outcome_array
from metamer.core.signal import (
    Constant,
    DesignInfo,
    Offset,
    RateChange,
    SignalSpec,
    Trend,
)
from metamer.core.statespace import StateSpace
from metamer.core.terms import ProcessSpec, TermSpec, free_param_index
from tests.oracles import mvn_loglik, reml_loglik, reml_penalty
from tests.test_kalman import _covariance
from tests.test_statespace import _term

LOG_2PI = float(np.log(2.0 * np.pi))


def _setup(seed=3, n=40):
    """A gap-free Constant + Trend fit on a 40-year annual axis."""
    spec = ProcessSpec((_term("white"), _term("matern12")))
    ss = StateSpace.from_spec(spec)
    theta = np.array([[0.4, 1.2, 6.0]])
    t = np.arange(float(n))
    signal = SignalSpec([Constant(), Trend()])
    design = signal.design_info(t, np.ones((1, n), dtype=bool))
    cov = _covariance(ss, theta, t)
    rng = np.random.default_rng(seed)
    y = (rng.multivariate_normal(np.zeros(n), cov) + 2.0 + 0.05 * (t - t.mean()))[
        None, :
    ]
    return spec, ss, theta, t, design, cov, y


# ---------------------------------------------------------------------------
# The conditioning fixture.
#
# ITS JOB IS TO SHOW THE LADDER IS REACHABLE, NOT TO SET THE THRESHOLD. Both
# limits are derived from float64 and from `kalman._RANK_RTOL` (see
# `objective.CONDITION_LOG_LIMIT`); nothing here may be tuned to move them. It
# may be adjusted freely, so long as the three cases still land in the three
# bands -- which `test_the_fixture_lands_in_all_three_bands` checks explicitly
# against the constants rather than against pinned numbers.
#
# 60 samples at 3-HOURLY spacing on a decimal-years axis (a week and a half of
# high-rate data, as the time-axis contract requires), with an offset and a
# rate change at sample 40 -- a coseismic step plus a postseismic rate change,
# the ordinary reason a design carries both at one epoch. The sampling interval
# is the lever: with two post-break samples the rate-change column restricted to
# them has a single non-zero entry of size dt, so cond(X_r) grows like 1/dt.
# Measured through the engine's own accumulated Gram at theta = (0.4, 1.2, 6.0):
#
#     rows   post-break   cond(X_w)   log cond(X_w)   band     margin
#       42       20         1125.6       7.0261       OK       7.3x below ILL
#       42        2        24623.        10.1114      ILL      3.0x above ILL,
#                                                              4.1x below RANK
#       40        0            inf          inf       RANK
#
# The first two keep the SAME NUMBER OF ROWS, so what separates them is the
# offset's support, not the sample count -- a threshold that could not tell
# those two apart would be measuring sample size.
# ---------------------------------------------------------------------------
_GAP_N = 60
_GAP_BREAK_INDEX = 40
_GAP_ROWS = 42
_GAP_T = np.arange(float(_GAP_N)) / (365.25 * 8.0)


def _gapped_signal(t):
    """The shared [Constant, Trend, Offset, RateChange] spec for the break epoch."""
    epoch = float(t[_GAP_BREAK_INDEX])
    return SignalSpec(
        [Constant(), Trend(), Offset(epoch=epoch), RateChange(epoch=epoch)]
    )


def _gapped_setup(mask=None, batch=1):
    """Shared design with an offset and a rate change, so gaps remove support.

    `design_info` needs the mask the fit will use, so the caller passes the one
    it is about to evaluate with; `None` means every epoch present.
    """
    spec = ProcessSpec((_term("white"), _term("matern12")))
    ss = StateSpace.from_spec(spec)
    theta = np.array([[0.4, 1.2, 6.0]])
    t = _GAP_T
    if mask is None:
        mask = np.ones((batch, t.size), dtype=bool)
    design = _gapped_signal(t).design_info(t, mask)
    return spec, ss, theta, t, design, mask


def _window(post_break_kept, rows=_GAP_ROWS):
    """Boolean mask keeping `rows` samples ending `post_break_kept` past the break."""
    stop = _GAP_BREAK_INDEX + post_break_kept
    keep = np.zeros(_GAP_N, dtype=bool)
    keep[max(stop - rows, 0) : stop] = True
    return keep


def _log_cond_whitened(gram):
    """log cond(X_w) from an accumulated Gram, independently of the module."""
    values = np.linalg.svdvals(gram)
    with np.errstate(divide="ignore"):
        return 0.5 * (np.log(values[0]) - np.log(values[-1]))


# ---------------------------------------------------------------------------
# GLS profiling
# ---------------------------------------------------------------------------


def test_beta_hat_matches_explicit_gls():
    """Profiled beta equals an explicit generalized-least-squares inversion.

    Bug this catches: partitioning the accumulator wrongly (row/column swap),
    which produces a plausible but incorrect trend -- the headline number.
    Expected value from an explicit Sigma^-1, sharing no code with the filter.
    """
    _, ss, theta, t, design, cov, y = _setup()
    x = design.matrix
    result = KalmanEngine().score(
        ss, theta, y, np.ones_like(y, dtype=bool), t, design=x
    )
    gls = gls_solution(result.normal_equations)
    cov_inv = np.linalg.inv(cov)
    expected = np.linalg.solve(x.T @ cov_inv @ x, x.T @ cov_inv @ y[0])
    np.testing.assert_allclose(gls.beta[0], expected, rtol=1e-9, atol=1e-9)


def test_beta_covariance_matches_explicit_inverse():
    """Reported beta covariance equals (X' Sigma^-1 X)^-1.

    Bug this catches: returning the un-inverted information matrix, which
    would understate trend uncertainty by orders of magnitude.

    `atol` is set from the magnitude of the quantity being compared, not left
    at zero: the off-diagonals of this covariance are exact numerical zeros
    (~1e-17 either side), and a pure relative tolerance measures rounding noise
    against rounding noise. The diagonals are O(1e-2), so `atol=1e-15` is still
    thirteen orders below anything that carries information.
    """
    _, ss, theta, t, design, cov, y = _setup()
    x = design.matrix
    result = KalmanEngine().score(
        ss, theta, y, np.ones_like(y, dtype=bool), t, design=x
    )
    gls = gls_solution(result.normal_equations)
    cov_inv = np.linalg.inv(cov)
    expected = np.linalg.inv(x.T @ cov_inv @ x)
    assert np.abs(np.diag(expected)).min() > 1e-6, "tolerance would be vacuous"
    np.testing.assert_allclose(gls.beta_cov[0], expected, rtol=1e-9, atol=1e-15)


def test_concentrated_loglik_matches_profiled_mvn():
    """The concentrated ML objective equals the GLS-profiled MVN density.

    The oracle profiles beta explicitly from an explicit covariance matrix, so
    it shares nothing with the augmented-filter route.

    Bug this catches: dropping or double-counting the residual reduction
    `0.5 * y'SX (X'SX)^-1 X'Sy` that turns the y-only filter score into the
    concentrated one.
    """
    spec, ss, theta, t, design, cov, y = _setup()
    obj = ConcentratedObjective(spec, ss, KalmanEngine(), Objective.ML)
    value = obj.loglik(theta, y, np.ones_like(y, dtype=bool), t, design)
    assert value[0] == pytest.approx(
        mvn_loglik(y[0], cov, design=design.matrix), abs=1e-9
    )


def test_concentrated_loglik_on_a_gapped_series_matches_the_restricted_oracle():
    """The ABSOLUTE ML value is right for a gapped series, not just a full one.

    `n log(2 pi)` is theta-independent, so a count taken over ALL epochs rather
    than the UNMASKED ones cancels in every delta-IC and no differential test
    can see it -- the same defect class as a wrong REML constant. The oracle
    here is evaluated on the restricted data and the restricted Sigma, which is
    the definition of the quantity the filter accumulates.

    Bug this catches: `n_used` counting masked epochs. The 10-epoch gap below
    moves the constant by 10 * log(2 pi) = 18.4 nats, so the test is not
    remotely tolerance-limited.
    """
    spec, ss, theta, t, _, cov, y = _setup()
    mask = np.ones_like(y, dtype=bool)
    mask[0, 15:25] = False
    keep = np.flatnonzero(mask[0])
    design = SignalSpec([Constant(), Trend()]).design_info(t, mask)

    obj = ConcentratedObjective(spec, ss, KalmanEngine(), Objective.ML)
    got = obj.loglik(theta, y, mask, t, design)[0]
    expected = mvn_loglik(
        y[0][keep], cov[np.ix_(keep, keep)], design=design.matrix[keep]
    )
    assert got == pytest.approx(expected, abs=1e-9)

    full = obj.loglik(theta, y, np.ones_like(y, dtype=bool), t, _setup()[4])[0]
    assert abs(got - full) > 1.0, "the gap must move the value"


def test_negative_residual_reduction_is_flagged_but_rounding_is_not():
    """A large negative residual reduction is named, not silently absorbed.

    `rss_reduction = y'SX (X'SX)^-1 X'Sy` is a quadratic form in a positive
    definite matrix and is therefore non-negative in exact arithmetic; it can
    only go slightly negative through rounding when the Gram is badly
    conditioned. Nothing takes a log or a sqrt of it, so a small excursion is
    benign -- but a LARGE one means the accumulator is not what it claims and
    the concentrated value would come back too high with an OK outcome.

    Bug this catches: a sign error in the partition (`accum[:, 0, 1:]` read as
    a different block) that makes the reduction systematically negative, which
    without this check would raise every log-likelihood in the batch.

    Tested on the pure helper because the end-to-end path cannot be provoked:
    any Gram bad enough to round the form negative is classified
    ILL_CONDITIONED_X or RANK_DEFICIENT_X before it is ever factorized.
    """
    quadratic = np.array([100.0, 100.0, 100.0, 100.0, 100.0])
    reduction = np.array([0.0, -1e-9, 5.0, -1.0, np.nan])
    got = negative_reduction_mask(reduction, quadratic)
    np.testing.assert_array_equal(got, [False, False, False, True, False])


def test_gls_solution_isolates_a_member_that_defeats_the_pre_classification():
    """One member that reaches cholesky and fails does not fail the stack.

    `xtx = diag(-1, -1)` is the case the pre-classification cannot see: its
    determinant is +1 (so `slogdet` reports a positive sign) and its singular
    values are (1, 1) (so it is neither rank deficient nor ill conditioned),
    yet it is negative definite and `np.linalg.cholesky` raises -- for the
    WHOLE (B, k, k) stack, not for the one member.

    Expected values are hand-computed for the two healthy members:
    G = [[4, 1], [1, 3]] has det 11 and G^-1 = [[3, -1], [-1, 4]] / 11, so
    beta = [5, 2] / 11 and y'SX beta = 12 / 11.

    Bug this catches: letting the LinAlgError propagate (or catching it and
    failing the whole subset), which at B = 10^4 destroys 9,999 good fits over
    one grid point.
    """
    gram = np.array([[4.0, 1.0], [1.0, 3.0]])
    accum = np.zeros((3, 3, 3))
    for index in (0, 2):
        accum[index, 1:, 1:] = gram
        accum[index, 1:, 0] = [2.0, 1.0]
        accum[index, 0, 0] = 10.0
    accum[1, 1:, 1:] = -np.eye(2)
    accum[1, 1:, 0] = [1.0, 1.0]
    accum[1, 0, 0] = 10.0

    gls = gls_solution(accum)

    np.testing.assert_array_equal(
        gls.outcome,
        [Outcome.OK.code, Outcome.RANK_DEFICIENT_X.code, Outcome.OK.code],
    )
    for index in (0, 2):
        np.testing.assert_allclose(
            gls.beta[index], [5.0 / 11.0, 2.0 / 11.0], rtol=1e-12
        )
        assert gls.logdet[index] == pytest.approx(np.log(11.0), rel=1e-12)
        assert gls.rss_reduction[index] == pytest.approx(12.0 / 11.0, rel=1e-12)
    assert np.all(np.isnan(gls.beta[1]))
    assert np.isnan(gls.logdet[1])


def test_gls_solution_handles_every_member_failing_the_factorization():
    """When the whole valid subset fails cholesky, all of it is named.

    Same construction as above with no healthy member left, so the backstop's
    surviving index is empty.

    Bug this catches: falling through to `factors[keep]` and the solves with an
    empty index, which either raises on the (0, k, k) stack or writes nothing
    while leaving the outcomes at OK -- NaN values tagged as a good fit.
    """
    accum = np.zeros((2, 3, 3))
    accum[:, 1:, 1:] = -np.eye(2)
    accum[:, 1:, 0] = [1.0, 1.0]
    accum[:, 0, 0] = 10.0

    gls = gls_solution(accum)

    assert np.all(gls.outcome == Outcome.RANK_DEFICIENT_X.code)
    assert np.all(np.isnan(gls.beta))
    assert np.all(np.isnan(gls.rss_reduction))


def test_gls_solution_names_every_failure_when_nothing_is_solvable():
    """An all-poisoned accumulator returns NaN with per-series outcomes, not a raise.

    This is what the engine hands over when every series in a tile is masked
    out: `normal_equations` is all-NaN by design.

    Bug this catches: reaching `np.flatnonzero(valid)` with an empty index and
    indexing into an empty stack, or letting the NaN block reach `svdvals`,
    which raises for the whole batch.
    """
    accum = np.full((4, 3, 3), np.nan)
    gls = gls_solution(accum)

    assert np.all(gls.outcome == Outcome.NONFINITE_OBJECTIVE.code)
    assert np.all(np.isnan(gls.beta))
    assert np.all(np.isnan(gls.beta_cov))
    assert np.all(np.isnan(gls.logdet))
    assert np.all(np.isnan(gls.rss_reduction))


def test_evaluate_refuses_a_per_point_design():
    """The Phase 2 seam fails loudly rather than computing the wrong thing.

    A per-point design is (B, N, k); every per-series quantity on `DesignInfo`
    is built assuming (N, k), and the objective would otherwise add
    determinants computed for the wrong axis to every log-likelihood.

    Bug this catches: Phase 2 widening `DesignInfo.matrix` while this module
    keeps reading it as shared, which produces finite, plausible REML values
    that are simply wrong.
    """
    spec, ss, theta, t, design, _, y = _setup()
    per_point = DesignInfo(
        design.matrix,
        design.rank,
        design.gram_logdet,
        design.condition_number,
        design.n_rows,
        True,
    )
    obj = ConcentratedObjective(spec, ss, KalmanEngine(), Objective.ML)
    with pytest.raises(NotImplementedError, match="per-point designs are Phase 2"):
        obj.evaluate(theta, y, np.ones_like(y, dtype=bool), t, per_point)


# ---------------------------------------------------------------------------
# REML
# ---------------------------------------------------------------------------


def test_reml_minus_ml_is_the_full_harville_correction():
    """REML - ML equals the WHOLE Harville correction, not just the penalty.

    l_R - l_c = 0.5 rank(X) log(2 pi) + 0.5 log|X'X| - 0.5 log|X'Sigma^-1X|.

    Each of the three terms is built here from an independent source: the
    penalty from `oracles.reml_penalty` (explicit Sigma^-1 and an explicit
    slogdet), the basis-invariance term from an explicit `slogdet(X'X)` on the
    design matrix, and the constant from `rank(X) log(2 pi)` with rank from
    `np.linalg.matrix_rank`.

    Bug this catches: implementing only the -0.5 log|X'Sigma^-1X| penalty and
    calling it REML. That is the pre-Harville convention; it differs from this
    one by 0.5 rank log(2 pi) + 0.5 log|X'X|, which is constant in theta and
    therefore invisible to every delta-IC and every selection test.
    """
    spec, ss, theta, t, design, cov, y = _setup()
    x = design.matrix
    mask = np.ones_like(y, dtype=bool)
    reml = ConcentratedObjective(spec, ss, KalmanEngine(), Objective.REML)
    ml = ConcentratedObjective(spec, ss, KalmanEngine(), Objective.ML)
    delta = (
        reml.loglik(theta, y, mask, t, design)[0]
        - ml.loglik(theta, y, mask, t, design)[0]
    )

    rank = int(np.linalg.matrix_rank(x))
    _, logdet_xtx = np.linalg.slogdet(x.T @ x)
    expected = reml_penalty(cov, x) + 0.5 * rank * LOG_2PI + 0.5 * logdet_xtx
    assert delta == pytest.approx(expected, abs=1e-9)


def test_reml_absolute_value_matches_an_independent_oracle():
    """The REML value itself is right, not merely its difference from ML.

    The oracle is written from the published Harville form, term by term, and
    shares no code with the implementation.

    Bug this catches: inheriting ML's n*log(2pi) constant instead of REML's
    (n - rank(X))*log(2pi), and omitting the +0.5*log|X'X| basis-invariance
    term. Both are constant in theta, so they cancel in delta-IC and every
    selection test passes -- while the stored log_lik primitive is wrong in
    absolute terms and the Hector cross-validation becomes unattributable
    between a convention difference and a bug.
    """
    spec, ss, theta, t, design, cov, y = _setup()
    obj = ConcentratedObjective(spec, ss, KalmanEngine(), Objective.REML)
    got = obj.loglik(theta, y, np.ones_like(y, dtype=bool), t, design)
    assert got[0] == pytest.approx(reml_loglik(y[0], cov, design.matrix), abs=1e-9)


def test_reml_on_a_gapped_series_uses_that_series_restricted_design():
    """REML's basis-invariance term is per series, not the batch design's.

    The design that enters the solve is X restricted to the series' unmasked
    rows, so `log|X'X|` and `rank(X)` in the Harville form must be those of
    X_r, not of the full X. The oracle is evaluated on the restricted Sigma
    and the restricted X, which is the definition of the quantity.

    Bug this catches: using the precomputed full-design `gram_logdet` for a
    gapped series. It is theta-independent, so it cancels in every delta-IC
    and NO differential test can see it -- exactly the defect class of a wrong
    REML constant, one level down. The gap below moves `log|X'X|` by 0.369
    nats, i.e. 0.185 in the log-likelihood, ~8 orders above the tolerance.
    """
    spec, ss, theta, t, full_design, cov, y = _setup()
    mask = np.ones_like(y, dtype=bool)
    mask[0, 15:25] = False
    keep = np.flatnonzero(mask[0])
    design = SignalSpec([Constant(), Trend()]).design_info(t, mask)

    restricted = design.matrix[keep]
    _, logdet_restricted = np.linalg.slogdet(restricted.T @ restricted)
    assert abs(full_design.gram_logdet[0] - logdet_restricted) > 0.1, (
        "the gap must move log|X'X|, or this test cannot see the defect"
    )
    assert design.gram_logdet[0] == pytest.approx(logdet_restricted, rel=1e-10)

    obj = ConcentratedObjective(spec, ss, KalmanEngine(), Objective.REML)
    got = obj.loglik(theta, y, mask, t, design)
    expected = reml_loglik(y[0][keep], cov[np.ix_(keep, keep)], restricted)
    assert got[0] == pytest.approx(expected, abs=1e-9)


@pytest.mark.parametrize("gap", [False, True])
def test_gram_logdet_is_read_from_design_info_and_never_recomputed(gap):
    """log|X_r'X_r| always comes from DesignInfo, gap or no gap.

    Poisoning `DesignInfo.gram_logdet` by a known amount must shift the REML
    value by exactly half of it (the Harville term carries the one-half) on
    BOTH paths, because `DesignInfo` is the single place that quantity is
    computed. It depends on (design, mask) and nothing else -- both theta-free
    -- so it is computed once at setup and the likelihood only reads it.

    Bug this catches: recomputing log|X_r'X_r| inside the likelihood, which
    repeats an O(N k^2) decomposition ~50 times per fit, 12 candidates per
    point, 10^7 points. The gapped case is parametrized alongside the
    gap-free one because an implementation that reads the field only when the
    mask is full -- and silently recomputes otherwise -- passes the gap-free
    half on its own.
    """
    spec, ss, theta, t, _, _, y = _setup()
    mask = np.ones_like(y, dtype=bool)
    if gap:
        mask[0, 15:25] = False
    design = SignalSpec([Constant(), Trend()]).design_info(t, mask)

    obj = ConcentratedObjective(spec, ss, KalmanEngine(), Objective.REML)
    poisoned = DesignInfo(
        design.matrix,
        design.rank,
        design.gram_logdet + 3.0,
        design.condition_number,
        design.n_rows,
    )
    shift = (
        obj.loglik(theta, y, mask, t, poisoned)[0]
        - obj.loglik(theta, y, mask, t, design)[0]
    )
    assert shift == pytest.approx(1.5, abs=1e-9)


def test_evaluate_refuses_a_design_built_from_a_different_mask():
    """A DesignInfo and the mask it is evaluated with must agree, or it raises.

    Every per-series quantity on `DesignInfo` is derived from a mask. Pairing
    it with a different one produces a REML value that is wrong by a
    theta-free constant -- finite, plausible, and invisible to every
    differential test, which is the exact failure the per-series widening
    exists to remove. `n_rows` is carried so the mismatch is loud.

    Bug this catches: building the design once with an all-present mask (the
    natural thing to do at setup) and then evaluating a gappy tile against it.
    """
    spec, ss, theta, t, _, _, y = _setup()
    obj = ConcentratedObjective(spec, ss, KalmanEngine(), Objective.ML)
    full = np.ones_like(y, dtype=bool)
    design = SignalSpec([Constant(), Trend()]).design_info(t, full)

    gapped = full.copy()
    gapped[0, 15:25] = False
    with pytest.raises(ValueError, match="mask"):
        obj.evaluate(theta, y, gapped, t, design)

    wider = SignalSpec([Constant(), Trend()]).design_info(
        t, np.ones((3, t.size), dtype=bool)
    )
    with pytest.raises(ValueError, match="3 series but y has 1"):
        obj.evaluate(theta, y, full, t, wider)


# ---------------------------------------------------------------------------
# Design classification
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mode", ["duplicate_column", "offset_at_first_sample"])
def test_rank_deficient_design_is_a_named_outcome_not_an_exception(mode):
    """A rank-deficient X gives RANK_DEFICIENT_X before any factorization.

    Two realistic cases: a duplicated column, and an offset epoch at the first
    sample, which is collinear with the intercept (design doc section 5.2).

    Bug this catches: a singular X'Sigma^-1X reaching np.linalg.cholesky and
    raising LinAlgError. Exit criterion 6 requires the documented failure; an
    uncaught exception is neither that nor a NaN, and at 10^7 points it aborts
    a tile instead of recording an outcome.
    """
    spec, ss, theta, t, _, _, y = _setup()
    obj = ConcentratedObjective(spec, ss, KalmanEngine(), Objective.REML)
    present = np.ones((1, t.size), dtype=bool)
    if mode == "duplicate_column":
        x_bad = np.column_stack([np.ones(t.size), np.ones(t.size)])
        # A duplicated column makes X'X exactly singular: rank 1 of 2,
        # log|X'X| = -inf and cond(X) = inf, all stated here from the
        # mathematics, not read back from the code that computes them.
        bad = DesignInfo(
            x_bad,
            np.array([1]),
            np.array([-np.inf]),
            np.array([np.inf]),
            np.array([t.size]),
        )
    else:
        bad = SignalSpec([Constant(), Offset(epoch=float(t[0]))]).design_info(
            t, present
        )

    assert np.all(bad.is_deficient)
    assert np.all(obj.check_design(bad, 1) == Outcome.RANK_DEFICIENT_X.code)

    result = obj.evaluate(theta, y, np.ones_like(y, dtype=bool), t, bad)
    assert np.all(result.outcome == Outcome.RANK_DEFICIENT_X.code)
    assert np.all(np.isnan(result.loglik))


def test_precheck_carries_the_real_unmasked_counts():
    """n_used is a true count even on the design-precheck path.

    The protocol pins n_used as the one field that stays meaningful when the
    outcome is not OK, carrying no sentinel. Returning zeros there contradicts
    that and hands Task 9 a zero denominator for a series that has data.

    Bug this catches: `np.zeros(batch)` on the early return -- which looks
    harmless because the fit failed anyway, and then reports "0 observations"
    for a grid point with 37 of them.
    """
    spec, ss, theta, t, _, _, _ = _setup()
    batch = 3
    y = np.zeros((batch, t.size))
    mask = np.ones((batch, t.size), dtype=bool)
    mask[1, :3] = False
    mask[2, 10:] = False
    x_bad = np.column_stack([np.ones(t.size), np.ones(t.size)])
    bad = DesignInfo(
        x_bad,
        np.ones(batch, dtype=np.int64),
        np.full(batch, -np.inf),
        np.full(batch, np.inf),
        np.count_nonzero(mask, axis=1),
    )

    obj = ConcentratedObjective(spec, ss, KalmanEngine(), Objective.ML)
    result = obj.evaluate(np.repeat(theta, batch, axis=0), y, mask, t, bad)

    np.testing.assert_array_equal(result.n_used, [t.size, t.size - 3, 10])
    np.testing.assert_array_equal(result.rank_x, [-1, -1, -1])


@pytest.mark.parametrize(
    "post_break_kept, rows, expected",
    [
        (20, _GAP_ROWS, Outcome.OK),
        (2, _GAP_ROWS, Outcome.ILL_CONDITIONED_X),
        (0, _GAP_ROWS, Outcome.RANK_DEFICIENT_X),
    ],
)
def test_effective_rank_is_per_series_because_the_mask_restricts_the_design(
    post_break_kept, rows, expected
):
    """A shared, globally full-rank X still fails for one series in a batch.

    The filter accumulates X' Sigma^-1 X only over each series' unmasked
    epochs, so the design that actually enters the solve is X restricted to
    those rows. Here the offset and rate change are fully supported globally,
    but series 2's gap removes all (or nearly all) of their post-breakpoint
    samples. On a grid point with a seasonal sea-ice dropout this is ordinary.

    The three cases separate two scientific facts the map should distinguish:
    a term with no support at all (exactly singular) and a term identified by a
    handful of samples (barely identified).

    Bug this catches: THE batched-granularity failure. np.linalg.cholesky raises
    for the whole (B, k, k) stack if one member is not positive definite, so a
    scalar outcome marks all B as failed. At B = 10^4 one such grid point
    destroys 9,999 good fits and the spatial failure map becomes a picture of
    the tile grid. Every small-B test passes, because there the batch is the
    series.
    """
    batch = 5
    rng = np.random.default_rng(21)
    y = rng.standard_normal((batch, _GAP_T.size))
    mask = np.ones_like(y, dtype=bool)
    mask[2] = _window(post_break_kept, rows)
    spec, ss, theta, t, design, _ = _gapped_setup(mask)

    obj = ConcentratedObjective(spec, ss, KalmanEngine(), Objective.ML)
    result = obj.evaluate(np.repeat(theta, batch, axis=0), y, mask, t, design)

    assert result.outcome[2] == expected.code
    if expected is Outcome.OK:
        assert np.isfinite(result.loglik[2])
    else:
        assert np.isnan(result.loglik[2])

    others = np.array([0, 1, 3, 4])
    assert np.all(result.outcome[others] == Outcome.OK.code)
    assert np.all(np.isfinite(result.loglik[others]))

    solo_design = _gapped_signal(t).design_info(t, mask[3:4])
    solo = obj.evaluate(theta, y[3:4], mask[3:4], t, solo_design)
    assert result.loglik[3] == pytest.approx(solo.loglik[0], rel=1e-12)


def test_the_conditioning_ladder_is_ordered_and_derived_from_float64():
    """Both limits come from float64 and _RANK_RTOL, and ILL sits BELOW RANK.

    Stated in one unit -- log cond(X_w), the whitened design's condition
    number -- so the two are directly comparable. The GLS solve here runs on
    the NORMAL EQUATIONS: the accumulator is X'Sigma^-1X and it is factorized
    by Cholesky, so the forward error goes like eps * cond(Gram) =
    eps * cond(X_w)^2. Half the significant digits are gone when that reaches
    sqrt(eps), i.e. at cond(X_w) = eps^(-1/4) = 8192. Rank deficiency sits
    further out at the engine's cutoff, s_min/s_max = _RANK_RTOL on the Gram,
    i.e. cond(X_w) = _RANK_RTOL^(-1/2) = 1e5. Neither number comes from a
    fixture.

    Bug this catches: THE unreachability defect. The brief set the limit so
    high (k * 30 = 90 nats, cond(X_w) ~ 1e39) that the rank cutoff at 11.5
    nats always fired first and ILL_CONDITIONED_X was dead code -- a named
    outcome the failure map could never show. Any future edit that raises the
    ill-conditioned limit past the rank limit, or lowers the rank cutoff below
    it, fails here regardless of what any fixture happens to measure.
    """
    eps = float(np.finfo(np.float64).eps)
    assert CONDITION_LOG_LIMIT == pytest.approx(-0.25 * np.log(eps), rel=1e-15)
    assert RANK_DEFICIENT_LOG_LIMIT == pytest.approx(
        -0.5 * np.log(_RANK_RTOL), rel=1e-15
    )

    # The ladder invariant itself, depending on no fixture whatsoever.
    assert CONDITION_LOG_LIMIT < RANK_DEFICIENT_LOG_LIMIT

    # And the band is wide enough to be reachable in practice, not merely
    # ordered by a rounding error.
    assert RANK_DEFICIENT_LOG_LIMIT - CONDITION_LOG_LIMIT > 1.0
    assert np.exp(CONDITION_LOG_LIMIT) == pytest.approx(8192.0, rel=1e-9)
    assert np.exp(RANK_DEFICIENT_LOG_LIMIT) == pytest.approx(1e5, rel=1e-9)


@pytest.mark.parametrize(
    "post_break_kept, expected",
    [(20, Outcome.OK), (2, Outcome.ILL_CONDITIONED_X), (0, Outcome.RANK_DEFICIENT_X)],
)
def test_the_fixture_lands_in_all_three_bands(post_break_kept, expected):
    """Each band of the derived ladder is reachable by a real masked design.

    THE FIXTURE'S JOB IS REACHABILITY, NOT CALIBRATION. The bands are the
    module constants; this measures where each case actually falls and checks
    it against those constants rather than against a pinned number, so the
    fixture can be retuned freely without touching a production threshold.

    Bug this catches: a threshold whose ILL band no observable design can enter
    -- which is what "unreachable" means concretely, and which a test asserting
    only that the OK and RANK cases work would never notice.
    """
    mask = np.ones((1, _GAP_T.size), dtype=bool)
    mask[0] = _window(post_break_kept)
    spec, ss, theta, t, design, _ = _gapped_setup(mask)

    scored = KalmanEngine().score(
        ss, theta, np.zeros((1, t.size)), mask, t, design.matrix
    )
    log_cond = _log_cond_whitened(scored.normal_equations[0, 1:, 1:])

    if expected is Outcome.OK:
        assert log_cond < CONDITION_LOG_LIMIT
    elif expected is Outcome.ILL_CONDITIONED_X:
        assert CONDITION_LOG_LIMIT < log_cond < RANK_DEFICIENT_LOG_LIMIT
    else:
        assert log_cond > RANK_DEFICIENT_LOG_LIMIT

    y = np.random.default_rng(31).standard_normal((1, t.size))
    obj = ConcentratedObjective(spec, ss, KalmanEngine(), Objective.ML)
    assert obj.evaluate(theta, y, mask, t, design).outcome[0] == expected.code


def test_the_conditioning_split_is_driven_by_support_not_by_row_count():
    """ILL_CONDITIONED_X fires on lost support at an unchanged sample count.

    Both series below keep exactly 42 rows of the same design; they differ
    only in how many of those rows fall after the breakpoint, so whatever
    separates them is the offset's SUPPORT and not the sample count. The
    measured whitened condition numbers straddle CONDITION_LOG_LIMIT, and the
    ill-conditioned one still sits strictly below RANK_DEFICIENT_LOG_LIMIT --
    which is what keeps ILL_CONDITIONED_X ("a term identified by a handful of
    samples") and RANK_DEFICIENT_X ("a term with no support at all") distinct
    outcomes rather than two names for one event. Which happened where is the
    point of the failure map.

    Bug this catches: a threshold that really measures sample size, which two
    cases differing in row count could not distinguish from one measuring
    support -- and, since the ladder is the only thing separating the two
    outcomes, would make ILL_CONDITIONED_X arbitrary.
    """
    masks = np.array([_window(20), _window(2)])
    assert masks[0].sum() == masks[1].sum() == _GAP_ROWS
    spec, ss, theta, t, design, _ = _gapped_setup(masks)

    scored = KalmanEngine().score(
        ss, np.repeat(theta, 2, axis=0), np.zeros((2, t.size)), masks, t, design.matrix
    )
    log_cond = np.array(
        [_log_cond_whitened(g) for g in scored.normal_equations[:, 1:, 1:]]
    )

    # Stated in the ladder's own units, so the two thresholds are directly
    # comparable: series 0 is below the ill limit, series 1 is inside the band
    # between the two -- barely identified, not singular.
    assert log_cond[0] < CONDITION_LOG_LIMIT
    assert CONDITION_LOG_LIMIT < log_cond[1] < RANK_DEFICIENT_LOG_LIMIT

    rng = np.random.default_rng(7)
    y = rng.standard_normal((2, t.size))
    obj = ConcentratedObjective(spec, ss, KalmanEngine(), Objective.ML)
    result = obj.evaluate(np.repeat(theta, 2, axis=0), y, masks, t, design)
    np.testing.assert_array_equal(
        result.outcome, [Outcome.OK.code, Outcome.ILL_CONDITIONED_X.code]
    )


def test_batch_level_rank_check_is_necessary_but_not_sufficient():
    """check_design passes a design that still fails per series.

    Bug this catches: believing the batch-level rank(X) is the whole story, and
    so never classifying per series at all. X here is globally full rank, so
    check_design returns OK for every series -- and one of them is nonetheless
    singular once its mask is applied.
    """
    mask = np.ones((3, _GAP_T.size), dtype=bool)
    mask[1] = _window(2)
    spec, ss, theta, t, design, _ = _gapped_setup(mask)

    # Every series' RESTRICTED design is full rank -- the mask cannot make this
    # verdict wrong, because check_design already sees it.
    assert not np.any(design.is_deficient)
    obj = ConcentratedObjective(spec, ss, KalmanEngine(), Objective.ML)
    codes = obj.check_design(design, 3)
    np.testing.assert_array_equal(codes, np.full(3, Outcome.OK.code))
    assert codes.shape == (3,)

    y = np.random.default_rng(5).standard_normal((3, t.size))
    result = obj.evaluate(np.repeat(theta, 3, axis=0), y, mask, t, design)
    assert result.outcome[1] == Outcome.ILL_CONDITIONED_X.code
    assert np.all(result.outcome[[0, 2]] == Outcome.OK.code)


# ---------------------------------------------------------------------------
# Outcome merging
# ---------------------------------------------------------------------------


def test_an_all_masked_series_stays_insufficient_data_with_a_design():
    """The engine's INSUFFICIENT_DATA survives the objective's own classification.

    An all-masked series is land or permanent ice, not a failure:
    `is_failure` is False and `is_eligible` is False, so it is excluded from
    the failure-rate denominator of design doc section 8.6. The engine poisons
    its accumulator to NaN, so the objective's own view of that series is
    "non-finite" -- and relabelling it NONFINITE_OBJECTIVE turns every land
    point into a failure and inflates precisely the denominator the exclusion
    exists to protect.

    Bug this catches: `outcome = gls.outcome`, i.e. replacing the engine's
    per-series verdict instead of merging with it.
    """
    spec, ss, theta, t, _, _, _ = _setup()
    batch = 3
    y = np.zeros((batch, t.size))
    mask = np.ones((batch, t.size), dtype=bool)
    mask[1] = False
    design = SignalSpec([Constant(), Trend()]).design_info(t, mask)

    obj = ConcentratedObjective(spec, ss, KalmanEngine(), Objective.ML)
    result = obj.evaluate(np.repeat(theta, batch, axis=0), y, mask, t, design)

    assert result.outcome[1] == Outcome.INSUFFICIENT_DATA.code
    assert not Outcome.from_code(result.outcome[1]).is_failure
    assert np.isnan(result.loglik[1])
    assert np.all(result.outcome[[0, 2]] == Outcome.OK.code)
    assert result.n_used[1] == 0


def test_an_all_masked_series_stays_insufficient_data_without_a_design():
    """The no-design branch reports the engine's verdict, not a blanket OK.

    Bug this catches: `outcome_array(batch)` on the design-free return, which
    tags an all-masked series OK while its loglik is NaN. That combination
    violates the store's bidirectional status invariant (OK implies a finite
    value) and would be read downstream as a successful fit of nothing.
    """
    spec, ss, theta, t, _, _, _ = _setup()
    batch = 2
    y = np.zeros((batch, t.size))
    mask = np.ones((batch, t.size), dtype=bool)
    mask[0] = False

    obj = ConcentratedObjective(spec, ss, KalmanEngine(), Objective.ML)
    result = obj.evaluate(np.repeat(theta, batch, axis=0), y, mask, t, None)

    assert result.outcome[0] == Outcome.INSUFFICIENT_DATA.code
    assert np.isnan(result.loglik[0])
    assert result.outcome[1] == Outcome.OK.code
    assert np.isfinite(result.loglik[1])


def test_outcome_precedence_is_the_declared_causal_ladder():
    """The ladder is a declared constant, ordered earliest-cause-first.

    Precedence is a stated property of the taxonomy, not an emergent
    consequence of which call site happens to run last. The order below is
    transcribed from the design rule -- data-level facts outrank design-level
    ones, which outrank numerical ones, which outrank OK -- rather than read
    back from the module.

    Bug this catches: expressing precedence as inline comparisons at each merge
    site, so two sites disagree and the reported cause depends on call order.
    """
    assert OUTCOME_PRECEDENCE == (
        Outcome.INSUFFICIENT_DATA,
        Outcome.NOT_ATTEMPTED,
        Outcome.RANK_DEFICIENT_X,
        Outcome.ILL_CONDITIONED_X,
        Outcome.NONFINITE_OBJECTIVE,
        Outcome.OK,
    )
    assert OUTCOME_PRECEDENCE[-1] is Outcome.OK, "OK must never outrank a cause"
    assert len(set(OUTCOME_PRECEDENCE)) == len(OUTCOME_PRECEDENCE)


@pytest.mark.parametrize(
    "codes, expected",
    [
        # Earliest cause wins, in every pairing and in both argument orders.
        ((Outcome.OK, Outcome.RANK_DEFICIENT_X), Outcome.RANK_DEFICIENT_X),
        ((Outcome.RANK_DEFICIENT_X, Outcome.OK), Outcome.RANK_DEFICIENT_X),
        (
            (Outcome.INSUFFICIENT_DATA, Outcome.NONFINITE_OBJECTIVE),
            Outcome.INSUFFICIENT_DATA,
        ),
        (
            (Outcome.NONFINITE_OBJECTIVE, Outcome.INSUFFICIENT_DATA),
            Outcome.INSUFFICIENT_DATA,
        ),
        (
            (Outcome.INSUFFICIENT_DATA, Outcome.RANK_DEFICIENT_X),
            Outcome.INSUFFICIENT_DATA,
        ),
        ((Outcome.NOT_ATTEMPTED, Outcome.RANK_DEFICIENT_X), Outcome.NOT_ATTEMPTED),
        (
            (Outcome.NONFINITE_OBJECTIVE, Outcome.ILL_CONDITIONED_X),
            Outcome.ILL_CONDITIONED_X,
        ),
        (
            (Outcome.RANK_DEFICIENT_X, Outcome.ILL_CONDITIONED_X),
            Outcome.RANK_DEFICIENT_X,
        ),
        (
            (Outcome.NONFINITE_OBJECTIVE, Outcome.NONFINITE_OBJECTIVE),
            Outcome.NONFINITE_OBJECTIVE,
        ),
        ((Outcome.OK, Outcome.OK), Outcome.OK),
        # An outcome outside the ladder is still a failure and must beat OK,
        # while never displacing a named cause.
        ((Outcome.OK, Outcome.DIAGNOSTIC_LIMIT), Outcome.DIAGNOSTIC_LIMIT),
        (
            (Outcome.INSUFFICIENT_DATA, Outcome.DIAGNOSTIC_LIMIT),
            Outcome.INSUFFICIENT_DATA,
        ),
        (
            (Outcome.NONFINITE_OBJECTIVE, Outcome.DIAGNOSTIC_LIMIT),
            Outcome.NONFINITE_OBJECTIVE,
        ),
        # Three-way, which is what `evaluate` actually calls.
        (
            (
                Outcome.INSUFFICIENT_DATA,
                Outcome.NONFINITE_OBJECTIVE,
                Outcome.RANK_DEFICIENT_X,
            ),
            Outcome.INSUFFICIENT_DATA,
        ),
        (
            (Outcome.OK, Outcome.OK, Outcome.ILL_CONDITIONED_X),
            Outcome.ILL_CONDITIONED_X,
        ),
    ],
)
def test_merge_outcomes_applies_the_precedence_ladder(codes, expected):
    """Merging is order-independent and always reports the earliest cause.

    The pairs are given in BOTH argument orders where they differ, because a
    merge implemented as "the second argument wins unless the first is special"
    is asymmetric and would pass one order while failing the other.

    Bug this catches: `outcome = gls.outcome`, i.e. replacing the engine's
    verdict instead of merging with it. That relabels an all-masked series
    (land, permanent ice) NONFINITE_OBJECTIVE, moving it from the excluded
    category into the failure NUMERATOR and inflating precisely the denominator
    `Outcome.is_eligible` exists to protect -- which would make every reported
    failure rate meaningless.
    """
    arrays = [outcome_array(4, code) for code in codes]
    merged = merge_outcomes(*arrays)
    assert merged.dtype == np.uint8
    assert merged.shape == (4,)
    np.testing.assert_array_equal(merged, np.full(4, expected.code))


def test_merge_outcomes_is_per_series_not_a_batch_verdict():
    """Each series is merged independently; one bad series marks only itself.

    Bug this catches: reducing the batch to a single worst-case verdict, which
    at B = 10^4 turns the spatial failure map into a picture of the tile grid.
    """
    engine = outcome_array(4)
    engine[1] = Outcome.INSUFFICIENT_DATA.code
    objective = outcome_array(4)
    objective[1] = Outcome.NONFINITE_OBJECTIVE.code
    objective[2] = Outcome.ILL_CONDITIONED_X.code

    np.testing.assert_array_equal(
        merge_outcomes(engine, objective),
        [
            Outcome.OK.code,
            Outcome.INSUFFICIENT_DATA.code,
            Outcome.ILL_CONDITIONED_X.code,
            Outcome.OK.code,
        ],
    )


def test_rank_x_is_carried_per_series_from_the_engine():
    """rank_x is the (B,) effective rank, not the batch design's scalar rank.

    Series 1 loses every row supporting the offset and the rate change, so its
    effective rank is 2 while `design.rank` is 4.

    Bug this catches: storing `design.rank` -- a scalar 4 for every series --
    which gives Task 9 an effective sample size `n_obs - rank(X)` that is two
    too small for the gapped series, silently, inside BIC. The -1 sentinel for
    a failed series is asserted alongside because it is NOT fail-loud under
    that subtraction and a consumer must gate on the outcome first.
    """
    y = np.random.default_rng(11).standard_normal((3, _GAP_T.size))
    mask = np.ones_like(y, dtype=bool)
    mask[1] = _window(0)
    spec, ss, theta, t, design, _ = _gapped_setup(mask)

    obj = ConcentratedObjective(spec, ss, KalmanEngine(), Objective.ML)
    result = obj.evaluate(np.repeat(theta, 3, axis=0), y, mask, t, design)

    assert result.rank_x.shape == (3,)
    assert result.rank_x.dtype == np.int64
    np.testing.assert_array_equal(result.rank_x, [4, -1, 4])
    # The engine's whitened rank and the design's own rank are DIFFERENT
    # quantities; for the healthy series they agree at 4, and for the gapped
    # one the design already knows it is 2 while the engine reports the -1
    # "not computed" sentinel.
    np.testing.assert_array_equal(design.rank, [4, 2, 4])


# ---------------------------------------------------------------------------
# Coordinates
# ---------------------------------------------------------------------------


def _frozen_rho_spec(spec):
    """Return `spec` with the Matern 1/2 term's rho frozen."""
    matern, white = spec.terms
    assert matern.kind == "matern12" and "rho" in matern.params
    pinned = TermSpec(
        kind=matern.kind,
        params={n: replace(p, fixed=(n == "rho")) for n, p in matern.params.items()},
        ordering_param=matern.ordering_param,
    )
    return ProcessSpec((pinned, white)), pinned


def test_fixed_parameter_is_pinned_and_does_not_shift_later_coordinates():
    """A frozen parameter is restored at its own slot, not by shifting the rest.

    `StateSpace` slices theta over ALL of a term's parameters while
    `free_param_index` covers only the free ones, so the free vector is one
    column short. The layout here is (matern12.sigma, matern12.rho,
    white.sigma) with rho frozen, and the free vector is (matern12.sigma,
    white.sigma).

    Bug this catches: appending the pinned default at the end rather than
    inserting it at its own position, so white.sigma lands in rho's slot and
    the default lands in white's. Every shape check still passes and the
    optimizer still converges -- to a fit of a different model. The last
    assertion pins that specifically: the shifted vector must NOT give the
    same likelihood.
    """
    spec, ss, _, t, design, _, y = _setup()
    frozen_spec, pinned = _frozen_rho_spec(spec)
    obj = ConcentratedObjective(
        frozen_spec, StateSpace.from_spec(frozen_spec), KalmanEngine(), Objective.ML
    )
    reference = ConcentratedObjective(spec, ss, KalmanEngine(), Objective.ML)

    assert free_param_index(frozen_spec) == (
        ("matern12[0]", "sigma"),
        ("white[0]", "sigma"),
    )
    assert frozen_spec.n_theta() == 2

    rho_default = pinned.params["rho"].default
    theta_free = np.array([[0.4, 6.0]])
    full = obj.hydrate(theta_free)
    assert full.shape == (1, 3)
    np.testing.assert_allclose(full[0], [0.4, rho_default, 6.0])

    mask = np.ones_like(y, dtype=bool)
    got = obj.loglik(theta_free, y, mask, t, design)[0]
    assert got == pytest.approx(
        reference.loglik(full, y, mask, t, design)[0], rel=1e-12
    )

    shifted = np.array([[0.4, 6.0, rho_default]])
    assert not np.isclose(got, reference.loglik(shifted, y, mask, t, design)[0])


def test_unconstrained_loglik_equals_the_natural_units_value_at_the_mapped_point():
    """The unconstrained entry point maps through the spec's bijectors.

    Every parameter here is Log-transformed, so `to_natural` is exp and the
    expected natural point is written out by hand.

    Bug this catches: passing `u` straight through to the likelihood, which at
    a negative coordinate hands a negative sigma to the family -- and, since
    only sigma^2 is ever used, silently fits the mirror image instead of
    raising.
    """
    spec, ss, _, t, design, _, y = _setup()
    obj = ConcentratedObjective(spec, ss, KalmanEngine(), Objective.ML)
    u = np.array([[np.log(0.4), np.log(1.2), np.log(6.0)]])
    mask = np.ones_like(y, dtype=bool)

    np.testing.assert_allclose(obj.to_natural(u), [[0.4, 1.2, 6.0]], rtol=1e-12)
    assert obj.unconstrained_loglik(u, y, mask, t, design)[0] == pytest.approx(
        obj.loglik(np.array([[0.4, 1.2, 6.0]]), y, mask, t, design)[0], rel=1e-14
    )


def test_to_unconstrained_inverts_to_natural_and_dforward_is_its_derivative():
    """The three mappings are mutually consistent and per-coordinate.

    `dforward` is compared against a central difference of `to_natural`, which
    is an independent numerical derivative rather than a second copy of the
    analytic one.

    Bug this catches: applying one coordinate's bijector to every column (the
    same class of layout bug `free_param_index` exists to prevent), which a
    round-trip alone would not see when all transforms happen to be equal, and
    which the derivative check catches as soon as the values differ.
    """
    spec, ss, _, _, _, _, _ = _setup()
    obj = ConcentratedObjective(spec, ss, KalmanEngine(), Objective.ML)
    theta = np.array([[0.4, 1.2, 6.0], [2.0, 0.5, 1.0]])

    np.testing.assert_allclose(
        obj.to_natural(obj.to_unconstrained(theta)), theta, rtol=1e-12
    )

    u = obj.to_unconstrained(theta)
    step = 1e-6
    expected = np.empty_like(u)
    for column in range(u.shape[1]):
        plus, minus = u.copy(), u.copy()
        plus[:, column] += step
        minus[:, column] -= step
        expected[:, column] = (
            obj.to_natural(plus)[:, column] - obj.to_natural(minus)[:, column]
        ) / (2.0 * step)
    np.testing.assert_allclose(obj.dforward(u), expected, rtol=1e-8)


def test_the_coordinate_maps_cover_free_parameters_only():
    """to_natural/to_unconstrained/dforward are sized by free_param_index.

    Bug this catches: sizing the flat vector by the total parameter count, so
    a spec with a frozen parameter accepts a vector one column too wide and
    interprets every entry after the frozen one as the wrong parameter.
    """
    spec, ss, _, _, _, _, _ = _setup()
    frozen_spec, _ = _frozen_rho_spec(spec)
    obj = ConcentratedObjective(
        frozen_spec, StateSpace.from_spec(frozen_spec), KalmanEngine(), Objective.ML
    )
    assert obj.to_natural(np.zeros((1, 2))).shape == (1, 2)
    with pytest.raises(ValueError, match="2 free parameters"):
        obj.to_natural(np.zeros((1, 3)))


# ---------------------------------------------------------------------------
# Documented conventions
# ---------------------------------------------------------------------------


def test_sigma_squared_is_not_profiled_out():
    """Scaling every kernel amplitude changes the concentrated value.

    A sigma^2-profiled objective is invariant to a common rescaling of the
    noise amplitudes: the profiled scale absorbs it exactly. This one is not,
    because a composite has a scale per term and Phase 1 refuses the
    cross-term shared parameter an overall amplitude would need. The
    difference below is the analytic consequence of that choice: scaling every
    amplitude by c sends Sigma -> c^2 Sigma, so log|Sigma| gains n log(c^2) and
    the profiled quadratic form y'Py is divided by c^2, giving

        l_c(c^2 Sigma) = l_c(Sigma) - 0.5 [ n log(c^2) + (1/c^2 - 1) y'Py ].

    y'Py is recovered from the oracle's own value, not from the module.

    Bug this catches: profiling sigma^2 out after all (or normalising the
    kernel), which would make the concentrated value invariant to c -- and
    drop k by one, without anyone noticing until the counting no longer
    matched Hector.
    """
    spec, ss, theta, t, design, cov, y = _setup()
    obj = ConcentratedObjective(spec, ss, KalmanEngine(), Objective.ML)
    mask = np.ones_like(y, dtype=bool)
    scale = 3.0

    base = obj.loglik(theta, y, mask, t, design)[0]
    scaled = obj.loglik(theta * np.array([[scale, 1.0, scale]]), y, mask, t, design)[0]

    n = float(t.size)
    quadratic = -2.0 * mvn_loglik(y[0], cov, design=design.matrix) - (
        n * LOG_2PI + float(np.linalg.slogdet(cov)[1])
    )
    expected = base - 0.5 * (n * np.log(scale**2) + (1.0 / scale**2 - 1.0) * quadratic)
    assert scaled == pytest.approx(expected, abs=1e-8)
    assert abs(scaled - base) > 1.0, "a profiled sigma^2 would absorb the rescaling"


def test_module_documents_the_conventions_it_pins():
    """The two conventions a future implementer must not guess are written down.

    Acceptance criteria 19 and the NaN-not-minus-inf rule are documentation
    obligations; nothing else in the suite reads the prose.

    Bug this catches: the brief's `evaluate` docstring, which promised -inf for
    a failed series while the code wrote NaN. Left in place it becomes the next
    implementer's specification, and -inf is a finite-looking sentinel that
    survives some consumers' checks.
    """
    from metamer.core import objective as module
    from metamer.core.objective import ObjectiveResult

    module_doc = module.__doc__ or ""
    assert "SIGMA-SQUARED IS NOT PROFILED OUT" in module_doc
    assert "cross-term shared parameter" in module_doc.lower()

    evaluate_doc = ConcentratedObjective.evaluate.__doc__ or ""
    assert "NaN" in evaluate_doc
    assert "-inf" not in evaluate_doc
    assert "NaN" in (ObjectiveResult.__doc__ or "")


def test_outcome_codes_are_stable():
    """The on-disk codes are the documented ones and are never renumbered.

    The expected mapping is transcribed from the schema comment in
    `outcomes.py`, not read back from `_CODES`, so a renumbering fails here
    even though every in-process comparison would still agree with itself.

    Bug this catches: inserting a new member in the middle of the enum, which
    silently reinterprets every archived uint8 status array.
    """
    expected = {
        "ok": 0,
        "iter_cap_small_grad": 1,
        "iter_cap_large_grad": 2,
        "diagnostic_limit": 3,
        "trust_radius_collapsed": 4,
        "nonfinite_objective": 5,
        "rank_deficient_x": 6,
        "degenerate_hessian": 7,
        "not_attempted": 8,
        "candidate_dropped": 9,
        "insufficient_data": 10,
        "ill_conditioned_x": 11,
    }
    assert {member.value: member.code for member in Outcome} == expected
    for value, code in expected.items():
        assert Outcome.from_code(code) == Outcome(value)
