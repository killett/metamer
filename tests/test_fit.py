"""Tests for `fit()`, the (B, N) driver.

**Batches here are heterogeneous by default.** Task 13's surviving mutation
existed because every fixture was B = 1 and took an early batch-wide exit, so a
per-series concept implemented at batch granularity was invisible. A batch of
healthy identical series cannot test a driver whose whole job is that each
series is handled on its own terms. Where a test must be B = 1, it says why.
"""

from __future__ import annotations

import numpy as np
import pytest

from metamer.core.capability import EngineId, GradientMode, Objective
from metamer.core.criteria import Criterion, Ranking
from metamer.core.engines.kalman import KalmanEngine
from metamer.core.fit import fit
from metamer.core.objective import ConcentratedObjective
from metamer.core.optimize import (
    HESSIAN_COND_LIMIT,
    InitRung,
    hessian_at_optimum,
    optimize_series,
)
from metamer.core.outcomes import Outcome
from metamer.core.signal import Annual, Constant, SignalSpec, Trend
from metamer.core.statespace import StateSpace
from metamer.core.terms import ProcessSpec
from tests.test_kalman import _covariance
from tests.test_objective import _GAP_N, _GAP_T, _gapped_signal, _window
from tests.test_statespace import _term

# EVERY test in this module runs the real filter through the whole driver --
# five-series batches, two candidates, a full optimization each. There is no
# fast subset of it worth carving out, so the marker is module-wide.
pytestmark = pytest.mark.slow


def _candidates():
    return [
        ProcessSpec((_term("white"),)),
        ProcessSpec((_term("white"), _term("matern12"))),
    ]


def _mixed_batch():
    """A batch holding one series of each reachable outcome.

    Rows, and what makes each one what it is:
      0  OK                  full post-break window, and a REALIZATION OF THE
                             CANDIDATE PROCESS rather than white noise. It was
                             `standard_normal` until 2026-08-08, which made it
                             healthy only by luck: candidate 1 is
                             white + Matern 1/2, so with no Matern structure in
                             the data that component's amplitude collapsed
                             (measured sigma = 1.5e-4) and its rho was left
                             unidentified on a flat ridge. `cond(H) = 3.5e8`
                             against the 1e10 limit -- 28x, and a
                             finite-difference Hessian's condition number moves
                             further than that across BLAS builds, so two CI
                             runners reported DEGENERATE_HESSIAN for it while
                             this machine reported OK. Drawing from the
                             composite's own covariance identifies all three
                             parameters and puts the fit decades clear of the
                             limit; `test_the_healthy_row_has_real_margin_to_
                             the_degeneracy_limit` is what holds it there.
      1  ILL_CONDITIONED_X   two post-break samples; seed pinned because the
                             classification is theta-dependent (it is the
                             WHITENED Gram that is ill conditioned, and at this
                             mask `condition_number` is 2.68e4 for every seed
                             while the outcome is not)
      2  RANK_DEFICIENT_X    no post-break samples: the offset and rate-change
                             columns lose all support
      3  INSUFFICIENT_DATA   wholly masked -- land or permanent ice
      4  DIAGNOSTIC_LIMIT    a record whose amplitude is ~1e-11, which drives
                             sigma below its 1e-8 lower limit. The obvious
                             alternative -- a smooth series driving rho past
                             1e6 -- does NOT work here: the design carries a
                             constant, a trend, an offset and a rate change,
                             which absorb a slow cosine and leave an ordinary
                             residual. Measured: that series comes back OK.
    """
    masks = np.vstack(
        [_window(20), _window(2), _window(0), np.zeros(_GAP_N, dtype=bool), _window(20)]
    )
    rng = np.random.default_rng(31)
    y = np.vstack(
        [
            _healthy_row(),
            np.random.default_rng(0).standard_normal(_GAP_N),
            rng.standard_normal(_GAP_N),
            rng.standard_normal(_GAP_N),
            1e-12 * np.cumsum(rng.standard_normal(_GAP_N)),
        ]
    )
    return y, _GAP_T, _gapped_signal(_GAP_T), masks


def _healthy_row():
    """A realization of candidate 1's own process: white + Matern 1/2.

    `rho` is set to ten sampling intervals. The scale matters in both
    directions and neither bound is arbitrary: below a couple of intervals the
    Matern component is indistinguishable from the white one and its amplitude
    collapses again, while much above the record length it is indistinguishable
    from a constant, which the design's own intercept absorbs. Ten intervals
    puts roughly four correlation lengths inside the 42-sample window, so the
    amplitude ratio and the length scale are both identified by the data.

    Drawn from the composite covariance directly rather than by iterating an
    AR(1) recursion, so the fixture shares no construction with the state-space
    machinery it is used to exercise.
    """
    spec = ProcessSpec((_term("white"), _term("matern12")))
    theta = np.array([[0.5, 1.0, 10.0 * float(_GAP_T[1] - _GAP_T[0])]])
    cov = _covariance(StateSpace.from_spec(spec), theta, _GAP_T)
    return np.random.default_rng(17).multivariate_normal(np.zeros(_GAP_N), cov)


def _plain_batch(batch=3, n=120, seed=5):
    """A small well-conditioned batch with a shared complete mask.

    EVERY ROW IS A REALIZATION OF CANDIDATE 1'S OWN PROCESS -- white +
    Matern 1/2 with `rho` at ten sampling intervals -- plus the trend the
    design carries. It was `rng.standard_normal(...) + trend` until
    2026-08-10, i.e. **pure white noise fitted with a composite that has a
    timescale**, which is the same defect open question 9 diagnosed in
    `_mixed_batch`'s row 0 and fixed there. With no Matern structure in the
    data its amplitude collapses and `rho` sits on a flat ridge: measured on
    the old fixture at `batch=2, n=200`, series 0 came out at
    `sigma_matern = 9.3e-4` with `cond(H) = 1.194e+08`, and series 1 -- same
    generator, same seed stream -- came out at `cond(H) = 1.447e+03`. One
    non-identified row and one healthy one from an identical construction is
    the signature of a fixture that is not asserting what it claims.

    That went unnoticed because `HESSIAN_COND_LIMIT` was `1e10`, under which
    `1.194e+08` reads as healthy by 84x. The limit is now the derived
    `eps^(-1/2) = 6.711e+07` and the row is correctly `DEGENERATE_HESSIAN`.
    **The lesson is open question 9's, restated: a fixture that is healthy by
    a large factor is not healthy.** `rho` at ten sampling intervals is
    `_healthy_row`'s choice and for its reasons -- far enough above the
    sampling interval that the Matern component is distinguishable from the
    white one, far enough below the record length that the design's own
    intercept does not absorb it.

    Drawn from the composite covariance directly rather than by iterating an
    AR(1) recursion, so the fixture shares no construction with the
    state-space machinery it exercises.
    """
    t = np.arange(float(n)) / 12.0
    spec = ProcessSpec((_term("white"), _term("matern12")))
    theta = np.array([[0.5, 1.0, 10.0 * float(t[1] - t[0])]])
    cov = _covariance(StateSpace.from_spec(spec), theta, t)
    rng = np.random.default_rng(seed)
    y = rng.multivariate_normal(np.zeros(n), cov, size=batch) + 0.4 * (t - t.mean())
    return y, t, SignalSpec([Constant(), Trend()]), np.ones((batch, n), dtype=bool)


# --------------------------------------------------------------------------
# The standing invariant
# --------------------------------------------------------------------------


def test_the_mixed_batch_really_holds_every_outcome_it_claims():
    """The invariant's fixture is heterogeneous, and stays that way.

    Behaviour under test: the fixture, not the driver.
    Bug this catches: the standing invariant below silently degrading to a
    batch of healthy series. Batched-equals-solo is trivially true when every
    series succeeds -- the failure paths are where a batch-wide early return,
    a scalar outcome or a stack-wide factorization actually diverge. If this
    test fails, the one below has stopped testing anything and must be fixed
    before it is trusted.
    """
    y, t, signal, mask = _mixed_batch()
    out = fit(y, t, signal, _candidates(), criterion=Criterion.AIC, mask=mask)
    seen = {Outcome.from_code(int(code)) for code in out.outcome[:, 1]}
    assert Outcome.OK in seen
    assert Outcome.ILL_CONDITIONED_X in seen
    assert Outcome.RANK_DEFICIENT_X in seen
    assert Outcome.INSUFFICIENT_DATA in seen
    assert Outcome.DIAGNOSTIC_LIMIT in seen


def test_the_healthy_row_has_real_margin_to_the_degeneracy_limit():
    """Row 0 is OK by construction, not by luck.

    Behaviour under test: the fixture again, and specifically HOW FAR row 0 sits
    from the degeneracy verdict rather than merely which side of it it lands on.

    Bug this catches: a "healthy" row that is only marginally healthy. The
    original fixture drew row 0 from `standard_normal` -- PURE WHITE NOISE --
    while candidate 1 is white + Matern 1/2. With no Matern structure present
    the component's amplitude sits at ~0 and its length scale rho is
    unidentifiable, leaving a flat ridge: measured `cond(H) = 3.5e8` on a 2x2,
    only 28x under the 1e10 limit. It passed here and reported
    DEGENERATE_HESSIAN on two GitHub Actions runners (ubuntu 3.13, then
    ubuntu 3.12), because a FINITE-DIFFERENCE Hessian's condition number moves
    by more than 1.45 decades across BLAS builds. That silently guts
    `test_batched_results_equal_solo_results_series_by_series` below, which
    shares this fixture and is meaningless without a healthy series in it.

    Expected value determined independently: the threshold is the module
    constant `HESSIAN_COND_LIMIT`, not a number recomputed from the fit. The
    margin demanded is 1e4 -- four decades -- chosen because the variation
    actually observed in CI exceeded the 1.45 decades that were there. The
    mechanism is `optimize_series`'s own `hessian_cond_limit` argument, which
    exists (per its docstring) "so the branch can be exercised without a
    fixture whose degeneracy is itself in question"; asking for OK under a
    limit tightened by 1e4 IS the margin assertion, and it duplicates no
    conditioning arithmetic from the implementation.

    This is deliberately a separate test from the one above. That one asks
    whether the fixture still spans the taxonomy; this one asks whether its
    healthy member is robustly healthy. A single test conflating them would
    not say which property broke.
    """
    y, t, signal, mask = _mixed_batch()
    spec = _candidates()[1]
    objective = ConcentratedObjective(
        spec, StateSpace.from_spec(spec), KalmanEngine(), Objective.ML
    )
    design = signal.design_info(t, mask[:1])

    strict = optimize_series(
        objective,
        y[:1],
        mask[:1],
        t,
        design,
        hessian_cond_limit=HESSIAN_COND_LIMIT / 1e4,
    )
    assert strict.outcome is Outcome.OK, (
        f"row 0 is within 1e4 of the degeneracy limit (got {strict.outcome.name}); "
        "it is healthy only by luck and will flip on other hardware"
    )


@pytest.mark.parametrize("max_iter", [200, 1])
def test_batched_results_equal_solo_results_series_by_series(max_iter):
    """STANDING INVARIANT: fitting B series together equals fitting each alone.

    Behaviour under test: every per-series contract established in Tasks 8-13,
    all at once. Asserted for the log-likelihood, the outcome, the natural-unit
    parameters, their uncertainties, the initialization rung, the iteration
    count, and both effective sample sizes -- a divergence in any one of them
    is a per-series concept implemented at batch granularity.
    Bug this catches: a batch-wide early return, a scalar outcome, a
    factorization that raises for the whole stack when one member is bad, or a
    reduction over the wrong axis. None of those is visible at B = 1, and none
    is visible in a batch where every series succeeds -- which is why the
    fixture carries one of each outcome. `max_iter=1` runs the same comparison
    with every series iteration-capped, bringing the two cap outcomes into a
    test that otherwise cannot reach them (the cap is a call-level argument, so
    it cannot vary within one batch).
    """
    y, t, signal, mask = _mixed_batch()
    cands = _candidates()
    together = fit(
        y, t, signal, cands, criterion=Criterion.AIC, mask=mask, max_iter=max_iter
    )

    for b in range(y.shape[0]):
        alone = fit(
            y[b : b + 1],
            t,
            signal,
            cands,
            criterion=Criterion.AIC,
            mask=mask[b : b + 1],
            max_iter=max_iter,
        )
        assert list(together.outcome[b]) == list(alone.outcome[0]), (
            f"outcome, series {b}"
        )
        np.testing.assert_allclose(
            together.loglik[b], alone.loglik[0], rtol=1e-12, err_msg=f"loglik {b}"
        )
        np.testing.assert_allclose(
            together.theta[b], alone.theta[0], rtol=1e-12, err_msg=f"theta {b}"
        )
        np.testing.assert_allclose(
            together.theta_err[b], alone.theta_err[0], rtol=1e-10, err_msg=f"err {b}"
        )
        np.testing.assert_allclose(
            together.n_eff_bic[b],
            alone.n_eff_bic[0],
            rtol=1e-12,
            err_msg=f"n_eff_bic {b}",
        )
        np.testing.assert_allclose(
            together.n_eff_trend[b],
            alone.n_eff_trend[0],
            rtol=1e-10,
            err_msg=f"n_eff_trend {b}",
        )
        assert list(together.init_rung[b]) == list(alone.init_rung[0]), f"rung {b}"
        assert list(together.n_iter[b]) == list(alone.n_iter[0]), f"n_iter {b}"


# --------------------------------------------------------------------------
# Shapes, tags, and the store's dtypes
# --------------------------------------------------------------------------


def test_fit_returns_a_result_per_series_and_candidate():
    """The result grid is (B, M) everywhere it should be.

    Behaviour under test: the output shapes.
    Bug this catches: collapsing the candidate axis, which makes delta-IC and
    the whole ranking meaningless.
    """
    y, t, signal, mask = _plain_batch(batch=3)
    out = fit(y, t, signal, _candidates(), criterion=Criterion.AIC, mask=mask)
    assert out.outcome.shape == (3, 2)
    assert out.loglik.shape == (3, 2)
    assert out.n_iter.shape == (3, 2)
    assert out.init_rung.shape == (3, 2)
    assert out.n_eff_bic.shape == (3, 2)
    assert out.n_eff_trend.shape == (3, 2)
    assert out.theta.shape[:2] == (3, 2)
    assert out.beta.shape == (3, 2, 2)
    assert len(out.candidates) == 2


def test_outcomes_are_uint8_codes_not_enum_objects():
    """`outcome` is what the store writes and what counting/criteria consume.

    Behaviour under test: the dtype at the seam.
    Bug this catches: an object array of `Outcome` members. It would need
    converting at three separate boundaries -- `penalty_terms(outcome=)`,
    `CandidateScores.outcome`, and the zarr write -- and a conversion written
    three times is one that will disagree with itself once. The give-away in a
    test is `outcome[b, c] is Outcome.OK`, which is False against a uint8 and
    silently skips whatever it guards.
    """
    y, t, signal, mask = _plain_batch()
    out = fit(y, t, signal, _candidates(), criterion=Criterion.AIC, mask=mask)
    assert out.outcome.dtype == np.uint8
    assert out.outcome[0, 0] == Outcome.OK.code
    assert out.outcome[0, 0] is not Outcome.OK  # the trap, made explicit


def test_results_carry_all_three_provenance_tags():
    """engine, objective and the resolved gradient mode are all reported.

    Behaviour under test: provenance.
    Bug this catches: an untagged result reaching selection, or a silent
    finite-difference fallback that makes the wall-time projection wrong in the
    direction that looks fine until the 19 ms budget is measured.
    """
    y, t, signal, mask = _plain_batch()
    out = fit(y, t, signal, _candidates(), criterion=Criterion.AIC, mask=mask)
    assert out.engine is EngineId.KALMAN
    assert out.objective is Objective.ML
    assert len(out.gradient_mode) == 2
    # white has no analytic gradient, so neither candidate resolves ANALYTIC.
    assert all(mode is GradientMode.FINITE_DIFFERENCE for mode in out.gradient_mode)


def test_selection_goes_through_rank_candidates():
    """The ranking is one batched `Ranking`, and `n_valid` counts the fits.

    Behaviour under test: the seam to `criteria`, so the comparability guards
    are in force on the real path.
    Bug this catches: a hand-rolled argmin in the driver, which would bypass
    the engine and objective tag checks entirely -- the guards would still be
    tested in `test_criteria.py` and still never run in production.
    """
    y, t, signal, mask = _mixed_batch()
    out = fit(y, t, signal, _candidates(), criterion=Criterion.AIC, mask=mask)
    assert isinstance(out.ranking, Ranking)
    assert out.ranking.criterion is Criterion.AIC
    assert out.ranking.delta_ic.shape == out.loglik.shape
    assert out.ranking.n_valid.shape == (y.shape[0],)
    expected = (out.outcome == Outcome.OK.code).sum(axis=1)
    np.testing.assert_array_equal(out.ranking.n_valid, expected)
    # A point with no surviving candidate reports no selection rather than
    # naming an arbitrary winner.
    dead = np.flatnonzero(expected == 0)
    assert dead.size, "the mixed batch must contain a fully failed point"
    assert np.all(out.ranking.best_index[dead] == -1)


# --------------------------------------------------------------------------
# The primitives the store needs
# --------------------------------------------------------------------------


def test_n_eff_bic_is_computed_from_the_model_and_is_not_the_sample_size():
    """`n_eff_bic` is a fitted-model quantity, not `n` under another name.

    Behaviour under test: the wiring to `counting.n_eff_bic`.
    Bug this catches: passing `n_eff = n`. It makes `Criterion.BIC_NEFF`
    silently identical to `BIC` -- no error, no warning, a plausible number --
    and it is exactly what the plan's fence did. The correlated candidate must
    report an effective count strictly below its observation count, and
    strictly below the white candidate's, because it is the one that says the
    samples are not independent.
    """
    y, t, signal, mask = _plain_batch(batch=2, n=200)
    out = fit(y, t, signal, _candidates(), criterion=Criterion.AIC, mask=mask)
    ok = out.outcome == Outcome.OK.code
    assert ok.all(), "this fixture is meant to succeed everywhere"
    n_used = mask.sum(axis=1)
    assert np.all(out.n_eff_bic <= n_used[:, None] + 1e-9)
    assert np.all(out.n_eff_bic >= 1.0 - 1e-8)
    # white (candidate 0) is uncorrelated, so its n_eff is the full count;
    # white + matern12 (candidate 1) must be strictly smaller.
    np.testing.assert_allclose(out.n_eff_bic[:, 0], n_used, rtol=1e-9)
    assert np.all(out.n_eff_bic[:, 1] < out.n_eff_bic[:, 0])


def test_bic_neff_and_bic_disagree_end_to_end():
    """The two criteria give different numbers through the real driver.

    Behaviour under test: `n_eff_bic` actually reaching the criterion.
    Bug this catches: the degradation above, caught at the level a user would
    notice it -- BIC and BIC_NEFF returning identical delta-IC maps. Testing
    `n_eff` alone would not: the driver could compute it correctly and still
    hand `n` to the ranking.
    """
    y, t, signal, mask = _plain_batch(batch=2, n=200)
    cands = _candidates()
    strict = fit(y, t, signal, cands, criterion=Criterion.BIC, mask=mask)
    loose = fit(y, t, signal, cands, criterion=Criterion.BIC_NEFF, mask=mask)
    assert np.all(np.isfinite(loose.ranking.ic_best))
    assert not np.allclose(strict.ranking.delta_ic, loose.ranking.delta_ic)
    # The looser penalty shows up on the CORRELATED candidate, whose n_eff is
    # below n. The white candidate's n_eff equals n exactly, so its criterion
    # value is identical under both and comparing `ic_best` would test nothing.
    #
    # THE WINNER MASK IS LOAD-BEARING, and it became so when `_plain_batch`
    # started drawing from candidate 1's own process on 2026-08-10. On white
    # noise the white candidate won every series and the correlated candidate's
    # delta-IC was always positive; on data that really is correlated, the
    # correlated candidate wins some of them, and where it wins its delta-IC is
    # ZERO BY DEFINITION under both criteria. Comparing those series asserts
    # `0 < 0` and fails for a reason that has nothing to do with the criterion.
    # Measured at batch=2, n=200: series 0 moves 1.6888 -> 1.0057, series 1 is
    # the winner and sits at 0.0 under both.
    correlated = loose.n_eff_bic[:, 1] < loose.n_eff_bic[:, 0]
    assert correlated.any(), "no candidate reported a reduced effective count"
    moved = correlated & (strict.ranking.delta_ic[:, 1] > 0.0)
    assert moved.any(), "the correlated candidate won everywhere; nothing to compare"
    assert np.all(loose.ranking.delta_ic[moved, 1] < strict.ranking.delta_ic[moved, 1])


def test_n_eff_trend_is_written_when_the_design_has_a_trend():
    """`n_eff_trend[y,x,m]` is a stored primitive and is populated.

    Behaviour under test: the `DesignInfo.trend_column` wiring.
    Bug this catches: leaving the store slot unwritten. A primitive that
    quietly never appears is the failure the schema exists to prevent, and it
    would only surface in Phase 2 when a zarr array came back all-NaN. It must
    also be TERM-SPECIFIC and distinct from `n_eff_bic`: substituting one for
    the other is a category error, so they are asserted to differ.
    """
    y, t, signal, mask = _plain_batch(batch=2, n=200)
    out = fit(y, t, signal, _candidates(), criterion=Criterion.AIC, mask=mask)
    assert np.all(np.isfinite(out.n_eff_trend))
    assert np.all(out.n_eff_trend >= 1.0)
    assert np.all(out.n_eff_trend <= mask.sum(axis=1)[:, None])
    assert not np.allclose(out.n_eff_trend, out.n_eff_bic)


def test_n_eff_trend_is_nan_where_the_design_has_no_trend_column():
    """No trend column means no trend effective sample size, and it says so.

    Behaviour under test: the absent-trend path.
    Bug this catches: reporting a number anyway -- whichever column happened to
    sit at index 1, or a zero. NaN is the honest answer and it matches the
    store's rule that an absent value is NaN rather than a sentinel.
    """
    y, t, _, mask = _plain_batch(batch=2, n=120)
    out = fit(
        y,
        t,
        SignalSpec([Constant()]),
        _candidates(),
        criterion=Criterion.AIC,
        mask=mask,
    )
    assert np.all(np.isnan(out.n_eff_trend))
    assert np.all(np.isfinite(out.n_eff_bic))


def test_the_trend_column_is_found_by_name_not_by_position():
    """A design whose trend is not column 1 still reports the trend's n_eff.

    Behaviour under test: `trend_column` used rather than a hardcoded index.
    Bug this catches: index 1, which is the trend only for the
    `[Constant, Trend, ...]` ordering every fixture uses. With
    `[Annual(), Trend()]` the trend is column 2, and the reported number would
    be a seasonal amplitude's effective sample size labelled as a trend's --
    plausible, wrong, and identical in dtype and range.
    """
    y, t, _, mask = _plain_batch(batch=2, n=240)
    shifted = SignalSpec([Annual(), Trend()])
    assert shifted.design_info(t, mask).trend_column == 2
    out = fit(y, t, shifted, _candidates(), criterion=Criterion.AIC, mask=mask)
    ok = out.outcome == Outcome.OK.code
    assert np.all(np.isfinite(out.n_eff_trend[ok]))


# --------------------------------------------------------------------------
# Warm starts and uncertainties
# --------------------------------------------------------------------------


def test_a_warm_start_is_recorded_and_actually_used():
    """`x0` sets the starting point and reports WARM_START.

    Behaviour under test: the Phase 2 seam, fixed here because the signature
    constrains everything downstream.
    Bug this catches: accepting `x0` and ignoring it, which makes warm-starting
    a no-op that still carries all its hysteresis risk in the accounting. The
    zero-iteration cap is what separates "used" from "recorded": with no
    iterations the returned theta can only be where it started.
    """
    y, t, signal, mask = _plain_batch(batch=2, n=120)
    cands = _candidates()
    cold = fit(y, t, signal, cands, criterion=Criterion.AIC, mask=mask)
    assert np.all(cold.init_rung != InitRung.WARM_START)
    assert np.all(cold.outcome == Outcome.OK.code)

    # Feeding a converged solution straight back is the Phase 2 use, and it is
    # the observable one: a warm start AT the optimum must take strictly fewer
    # iterations than a cold start from the moment estimate. Recording the rung
    # without using x0 leaves the iteration counts identical.
    warm = fit(
        y,
        t,
        signal,
        cands,
        criterion=Criterion.AIC,
        mask=mask,
        x0=np.nan_to_num(cold.theta_unconstrained, nan=0.0),
    )
    assert np.all(warm.init_rung == InitRung.WARM_START)
    assert np.all(warm.outcome == Outcome.OK.code)
    assert np.all(warm.n_iter < cold.n_iter)
    np.testing.assert_allclose(warm.loglik, cold.loglik, rtol=1e-6)

    with pytest.raises(ValueError, match="x0 must have shape"):
        fit(
            y, t, signal, cands, criterion=Criterion.AIC, mask=mask, x0=np.zeros((2, 1))
        )


def test_uncertainties_are_reported_in_natural_units():
    """`theta_err` is in natural units, via the delta method.

    Behaviour under test: the push-through from the unconstrained Hessian.
    Bug this catches: reporting the unconstrained standard error directly.
    Under a `Log` transform the two differ by a factor of theta itself, so the
    error bar on a timescale of 8 would be reported as if it were 1 -- the
    exact class of plausible, wrong error bar this package exists to remove.
    Checked by comparison against the unconstrained value the same fit carries.
    """
    y, t, signal, mask = _plain_batch(batch=2, n=300)
    out = fit(
        y,
        t,
        signal,
        [ProcessSpec((_term("matern12"),))],
        criterion=Criterion.AIC,
        mask=mask,
    )
    ok = out.outcome[:, 0] == Outcome.OK.code
    assert ok.any(), "this fixture is meant to produce at least one OK fit"
    errs = out.theta_err[ok, 0, :]
    assert np.all(np.isfinite(errs))
    assert np.all(errs > 0.0)
    # Natural-unit sigma error scales with sigma; an unconstrained-space error
    # would not, and for these fits theta is far from 1.
    theta = out.theta[ok, 0, :]
    assert not np.allclose(errs, errs / theta, rtol=1e-6)


def test_a_failed_candidate_carries_nan_not_a_stale_number():
    """Every value slot of a non-OK (series, candidate) is NaN.

    Behaviour under test: the store's bidirectional status invariant, at the
    boundary that writes it.
    Bug this catches: a partially written failure leaving stale numbers from a
    previous candidate in `theta`, `beta` or `theta_err`. They read as valid,
    and the status array is the only thing that would say otherwise -- which is
    why the invariant is asserted in both directions rather than one.
    """
    y, t, signal, mask = _mixed_batch()
    out = fit(y, t, signal, _candidates(), criterion=Criterion.AIC, mask=mask)
    bad = out.outcome != Outcome.OK.code
    assert bad.any(), "the mixed batch must contain a failure"
    for b, c in zip(*np.nonzero(bad), strict=True):
        assert np.all(np.isnan(out.theta[b, c])), f"theta {b},{c}"
        assert np.all(np.isnan(out.theta_err[b, c])), f"theta_err {b},{c}"
        assert np.all(np.isnan(out.beta[b, c])), f"beta {b},{c}"
        assert np.isnan(out.loglik[b, c]), f"loglik {b},{c}"
        assert np.isnan(out.n_eff_bic[b, c]), f"n_eff_bic {b},{c}"


def test_the_criterion_value_itself_is_right_not_only_its_differences():
    """`ic_best` matches AIC recomputed by hand from the published primitives.

    Behaviour under test: `k` and `n`, in ABSOLUTE terms.
    Bug this catches: `penalty_terms` given the wrong `design_rank` -- zeros,
    say, or `rank_x`. **Every delta-IC test in this file is blind to it**: `k`
    shifts by the same amount for every candidate at a point, so the shift
    cancels in the difference and the ranking, the weights and `n_valid` are
    all unchanged. Found by mutation, which is the only reason this test
    exists. Expected value derived independently: `k = k_theta + rank(X_r)`
    under ML, so with `[Constant, Trend]` at full rank a white candidate has
    `k = 1 + 2 = 3` and `AIC = 2k - 2l`.
    """
    y, t, signal, mask = _plain_batch(batch=2, n=150)
    cands = _candidates()
    out = fit(y, t, signal, cands, criterion=Criterion.AIC, mask=mask)
    assert np.all(out.outcome == Outcome.OK.code)

    design = signal.design_info(t, mask)
    assert np.all(design.rank == 2), "the fixture must be full rank for this to bite"
    for c, spec in enumerate(cands):
        k = spec.n_theta() + 2  # k_theta + rank(X_r), the ML definition
        expected = 2.0 * k - 2.0 * out.loglik[:, c]
        got = out.ranking.delta_ic[:, c] + out.ranking.ic_best
        np.testing.assert_allclose(got, expected, rtol=1e-12)


def test_uncertainties_are_the_delta_method_push_through_not_the_raw_hessian():
    """`theta_err` equals `theta * sigma_u`, recomputed independently.

    Behaviour under test: `delta_method_cov` actually applied.
    Bug this catches: reporting `sqrt(diag(inv(H)))` directly. Under a `Log`
    transform the Jacobian is `theta` itself, so the two differ by exactly
    that factor -- an error bar on a timescale of 8 reported as if it were 1.
    The reference here is rebuilt from the objective and the published
    `theta_unconstrained`, so it shares no code with the driver's own path.
    """
    y, t, signal, mask = _plain_batch(batch=2, n=250)
    spec = ProcessSpec((_term("matern12"),))
    out = fit(y, t, signal, [spec], criterion=Criterion.AIC, mask=mask)
    ok = np.flatnonzero(out.outcome[:, 0] == Outcome.OK.code)
    assert ok.size, "this fixture is meant to produce at least one OK fit"

    state_space = StateSpace.from_spec(spec)
    obj = ConcentratedObjective(spec, state_space, KalmanEngine(), Objective.ML)
    for b in ok:
        one = signal.design_info(t, mask).series(int(b))

        def fn(u, b=b, one=one):
            return float(
                obj.unconstrained_loglik(
                    np.asarray(u)[None, :], y[b : b + 1], mask[b : b + 1], t, one
                )[0]
            )

        def negative(u, fn=fn):
            return -fn(u)

        u_hat = out.theta_unconstrained[b, 0]
        hessian = hessian_at_optimum(negative, u_hat, scale=abs(fn(u_hat)))
        sigma_u = np.sqrt(np.diag(np.linalg.inv(hessian)))
        # Log transform: d(theta)/d(u) = theta, so the natural-unit error is
        # theta * sigma_u and the raw unconstrained one is sigma_u.
        np.testing.assert_allclose(
            out.theta_err[b, 0], out.theta[b, 0] * sigma_u, rtol=1e-3
        )
        assert not np.allclose(out.theta_err[b, 0], sigma_u, rtol=1e-2)


def test_the_reported_trend_effective_size_is_the_trend_column_s():
    """`n_eff_trend` is recomputed from the published outputs, for column 2.

    Behaviour under test: the trend column is used, by value not by shape.
    Bug this catches: a hardcoded index 1. With `[Annual(), Trend()]` that is
    the annual SINE column, whose effective sample size is finite, positive and
    in `[1, n]` -- so any assertion that only checks those properties passes
    against the defect. Found by mutation. Expected value derived from the
    definition: `clip(n * var_white / var_gls, 1, n)` with
    `var_gls = beta_err[trend]^2` and `var_white = sigma^2 * (Xr'Xr)^-1[trend]`,
    all of which the result and the design already publish.
    """
    y, t, _, mask = _plain_batch(batch=2, n=240)
    shifted = SignalSpec([Annual(), Trend()])
    design = shifted.design_info(t, mask)
    assert design.trend_column == 2
    # A CORRELATED candidate is required. Under a white noise model GLS is
    # OLS, so `var_gls` is `sigma^2 (Xr'Xr)^-1[j,j]` for EVERY column j and the
    # ratio is 1 everywhere -- n_eff_trend comes back as n for all of them and
    # no column can be distinguished from any other. Verified: with a white
    # candidate this test passes against the hardcoded-index defect.
    spec = ProcessSpec((_term("white"), _term("matern12")))
    out = fit(y, t, shifted, [spec], criterion=Criterion.AIC, mask=mask)
    ok = out.outcome[:, 0] == Outcome.OK.code
    assert ok.all()

    n_used = design.n_rows.astype(float)
    state_space = StateSpace.from_spec(spec)
    obj = ConcentratedObjective(spec, state_space, KalmanEngine(), Objective.ML)
    p_free = spec.n_theta()
    marginal = state_space.acvf(obj.hydrate(out.theta[:, 0, :p_free]), np.zeros(1))[
        :, 0
    ]
    for column, should_match in ((2, True), (1, False)):
        var_gls = out.beta_err[:, 0, column] ** 2
        var_white = marginal * design.unit_variance_beta_var[:, column]
        expected = np.clip(n_used * var_white / var_gls, 1.0, n_used)
        close = np.allclose(out.n_eff_trend[:, 0], expected, rtol=1e-8)
        assert close is should_match, f"column {column}"


def test_a_mask_of_the_wrong_shape_is_refused():
    """The mask must match `y` exactly.

    Behaviour under test: the shape guard.
    Bug this catches: a mask broadcasting against `y`. A `(1, N)` mask against
    a `(B, N)` batch would silently apply one series' gaps to all of them, and
    every derived per-series quantity -- rank, n_rows, n_eff -- would be that
    one series' answer wearing the whole batch's shape.
    """
    y, t, signal, mask = _plain_batch(batch=3, n=120)
    with pytest.raises(ValueError, match="mask shape"):
        fit(y, t, signal, _candidates(), criterion=Criterion.AIC, mask=mask[:1])
