"""Tests for the reference optimizer, the init ladder, and the Hessian.

**The Hessian oracle is a nested Richardson construction**, not a second
central difference. `tests/oracles.fd_hessian` and `hessian_at_optimum` are the
same stencil at different steps, so checking one against the other measures the
step choice and nothing else. The oracle here differentiates a
Richardson-extrapolated GRADIENT by Richardson — a different algorithm, whose
own self-consistency is visible as the asymmetry of the raw result: measured
**8.8e-13** on the real filter, against a 6.3e-08 disagreement with a Romberg
second-difference reference. That gap is the Romberg reference's error, not the
nested one's.

**Tolerance.** `1e-5` for the Hessian, derived. `hessian_at_optimum` with the
`eps^(1/4)` step reaches **2.98e-07** against that oracle, so 1e-5 leaves ~34×
headroom; and the plan's `max(fd_step(scale), 1e-5)` step reaches only
**4.39e-05**, which the gate rejects. A looser gate would accept both and
therefore measure nothing.
"""

from __future__ import annotations

import numpy as np
import pytest

from metamer.core import optimize as optimize_module
from metamer.core.capability import Objective
from metamer.core.engines.kalman import KalmanEngine
from metamer.core.gradients import EPS, fd_gradient, richardson_gradient
from metamer.core.objective import ConcentratedObjective
from metamer.core.optimize import (
    GRAD_TOL,
    HESSIAN_COND_LIMIT,
    InitRung,
    SeriesFit,
    hessian_at_optimum,
    hessian_condition,
    hessian_step,
    moment_init,
    optimize_series,
    outcome_for_status,
)
from metamer.core.outcomes import Outcome
from metamer.core.statespace import StateSpace
from metamer.core.terms import ProcessSpec
from metamer.core.transforms import delta_method_cov
from tests.test_kalman import _covariance
from tests.test_objective import _gapped_setup, _window
from tests.test_statespace import _term


def _ou_series(sigma=1.0, rho=8.0, n=200, seed=11):
    """Simulate an OU series from the family's own covariance."""
    spec = ProcessSpec((_term("matern12"),))
    state_space = StateSpace.from_spec(spec)
    theta = np.array([[sigma, rho]])
    t = np.arange(float(n))
    cov = _covariance(state_space, theta, t)
    rng = np.random.default_rng(seed)
    y = rng.multivariate_normal(np.zeros(n), cov)[None, :]
    return spec, state_space, theta, t, y


def _objective(spec, state_space, objective=Objective.ML):
    return ConcentratedObjective(spec, state_space, KalmanEngine(), objective)


def _nested_hessian(fn, u, levels=4):
    """Hessian as the Richardson derivative of a Richardson gradient.

    Shares no stencil with `hessian_at_optimum`: this differentiates the
    gradient, that one takes a second difference of the objective. Returns the
    symmetrized matrix and the raw asymmetry, which is a free self-consistency
    check -- an exact Hessian is symmetric, so the asymmetry bounds the
    construction's own error.
    """

    def component(index):
        return lambda v: float(richardson_gradient(fn, v, levels=levels)[index])

    raw = np.array(
        [richardson_gradient(component(i), u, levels=levels) for i in range(u.size)]
    )
    return 0.5 * (raw + raw.T), float(np.max(np.abs(raw - raw.T)))


# --------------------------------------------------------------------------
# The initialization ladder
# --------------------------------------------------------------------------


def test_moment_init_recovers_the_timescale_within_a_factor_of_three():
    """The deterministic initializer lands in the right basin.

    Behaviour under test: `moment_init`'s lag-1 estimator.
    Expected value derived independently: an OU process has lag-1
    autocorrelation `exp(-dt/rho)`, so `rho_hat = -dt / log(r1)`. The factor of
    three is deliberately loose -- this is a starting point, not an estimate.
    Bug this catches: an initializer that returns the family default whatever
    the data, making every fit a cold start from 1.0 and hiding the whole
    ladder behind a plausible number.
    """
    spec, _, _, t, y = _ou_series(rho=8.0, n=400)
    init, rungs = moment_init(spec, y, np.ones_like(y, dtype=bool), t)
    assert rungs[0] is InitRung.MOMENT
    assert init.shape == (1, spec.n_theta())
    assert 8.0 / 3.0 < init[0, 1] < 8.0 * 3.0


def test_a_zero_variance_series_falls_through_to_the_family_default():
    """A degenerate series reaches DEFAULT rather than raising.

    Behaviour under test: the bottom rung.
    Bug this catches: a divide-by-zero or NaN escaping the initializer. At 10^7
    points that aborts a tile instead of recording an outcome, and the tile is
    the unit of work -- one dead pixel would lose ~10^5 good fits.
    """
    spec = ProcessSpec((_term("matern12"),))
    t = np.arange(50.0)
    y = np.zeros((1, 50))
    init, rungs = moment_init(spec, y, np.ones_like(y, dtype=bool), t)
    assert rungs[0] is InitRung.DEFAULT
    assert np.all(np.isfinite(init))
    assert init[0, 1] == 1.0  # the family default for rho


def test_a_non_monotone_autocovariance_does_not_produce_a_fabricated_estimate():
    """`r1 <= 0` falls to DEFAULT instead of reporting a clamped MOMENT value.

    Behaviour under test: the admissibility check on the lag-1 statistic.
    Bug this catches: clamping `r1` into `[1e-6, 1 - 1e-6]` and reporting the
    result as MOMENT. An OU process has `r1 = exp(-dt/rho)`, strictly in
    `(0, 1)`; a negative `r1` says the data are anticorrelated at lag 1, which
    this family cannot represent at all. The clamped form turns that into
    `rho = -dt / log(1e-6) = 0.0724` at `dt = 1` -- a specific, plausible,
    entirely fabricated number, reported as data-derived.
    """
    spec = ProcessSpec((_term("matern12"),))
    t = np.arange(60.0)
    y = np.asarray(np.arange(60) % 2 * 2.0 - 1.0, dtype=np.float64)[
        None, :
    ]  # r1 near -1
    init, rungs = moment_init(spec, y, np.ones_like(y, dtype=bool), t)
    assert rungs[0] is InitRung.DEFAULT
    assert init[0, 1] == 1.0
    assert init[0, 1] != pytest.approx(-1.0 / np.log(1e-6), rel=1e-6)


def _vanishing_amplitude_series(n=300, seed=5):
    """A correlated series whose amplitude sits below sigma's lower limit."""
    rng = np.random.default_rng(seed)
    return 1e-12 * np.cumsum(rng.standard_normal(n))[None, :]


def test_an_amplitude_below_the_diagnostic_limit_reports_the_clipped_rung():
    """A moment estimate outside the diagnostic limits reports CLIPPED.

    Behaviour under test: the middle rung, which exists to distinguish "the
    data gave a usable number" from "the data gave a number the model cannot
    hold".
    Bug this catches: clipping silently and reporting MOMENT. The rung is
    recorded because initialization source affects reproducibility semantics
    and is what you want when diagnosing traversal-order dependence in the
    Phase 2 hysteresis audit. The fixture is a random walk scaled to ~1e-10,
    which is correlated enough for `r1` to stay admissible -- so the ladder
    does not simply fall through to DEFAULT -- while its amplitude lands below
    `sigma`'s 1e-8 lower diagnostic limit.
    """
    spec = ProcessSpec((_term("matern12"),))
    y = _vanishing_amplitude_series()
    t = np.arange(float(y.shape[1]))
    init, rungs = moment_init(spec, y, np.ones_like(y, dtype=bool), t)
    assert rungs[0] is InitRung.CLIPPED
    assert init[0, 0] == 1e-8  # sigma's lower diagnostic limit, exactly
    assert np.std(y) < 1e-8  # the fixture really is below the limit


def test_the_rung_is_reported_per_series_not_per_batch():
    """A mixed batch gets one rung each, not one rung for all of them.

    Behaviour under test: `moment_init`'s return is `(B,)`-shaped.
    Bug this catches: a single batch-wide rung. Every condition that triggers a
    fallback is per series -- one gap-riddled or flat pixel in a tile is the
    ordinary case -- so a scalar rung is right only when the whole batch falls
    the same way, which is what a single-series fixture arranges and real data
    never does. Found by mutation: the per-series DEFAULT downgrade could be
    deleted without any test noticing, because every fixture had B = 1 and took
    an earlier batch-wide exit instead.
    """
    spec = ProcessSpec((_term("matern12"),))
    _, _, _, t, good = _ou_series(rho=8.0, n=60)
    n = good.shape[1]
    alternating = np.asarray(np.arange(n) % 2 * 2.0 - 1.0, dtype=np.float64)
    batch = np.vstack([good[0], alternating, _vanishing_amplitude_series(n=n)[0]])
    mask = np.ones_like(batch, dtype=bool)

    init, rungs = moment_init(spec, batch, mask, t)
    assert rungs == (InitRung.MOMENT, InitRung.DEFAULT, InitRung.CLIPPED)
    assert init.shape == (3, 2)
    # The MOMENT series kept its data-derived timescale; the DEFAULT one did not.
    assert init[0, 1] != 1.0
    assert init[1, 1] == 1.0


def test_every_rung_of_the_ladder_is_reachable():
    """All four rungs occur, so none is dead code.

    Behaviour under test: the ladder as a whole.
    Bug this catches: a rung that can never be reported -- which makes the
    reported field useless for the diagnosis it exists for, and which no
    single-rung test would reveal.
    """
    spec, state_space, _, t, y = _ou_series()
    mask = np.ones_like(y, dtype=bool)
    obj = _objective(spec, state_space)

    seen = set()
    seen.add(moment_init(spec, y, mask, t)[1][0])
    seen.add(moment_init(spec, np.zeros_like(y), mask, t)[1][0])
    tiny = _vanishing_amplitude_series(n=y.shape[1])
    seen.add(moment_init(spec, tiny, mask, t)[1][0])
    warm = optimize_series(obj, y, mask, t, None, x0=np.zeros((1, 2)), max_iter=2)
    seen.add(warm.init_rung)

    assert seen == set(InitRung)


def test_a_warm_start_is_used_rather_than_merely_accepted():
    """`x0` sets the starting point, not just the reported rung.

    Behaviour under test: the warm-start path.
    Bug this catches: recording WARM_START while still starting from the
    moment estimate. That makes Phase 2's warm-starting a no-op which still
    carries all of its hysteresis risk in the accounting -- the worst of both.
    Detected by capping the iterations so the fit cannot travel far from
    wherever it began, and starting it somewhere the moment estimate does not
    reach: this series has `rho ~ 8`, the warm start says 17, and one capped
    iteration cannot cross that gap in either direction.
    """
    spec, state_space, _, t, y = _ou_series(rho=8.0)
    obj = _objective(spec, state_space)
    mask = np.ones_like(y, dtype=bool)

    x0 = np.array([[np.log(3.0), np.log(17.0)]])
    warm = optimize_series(obj, y, mask, t, None, x0=x0, max_iter=0)
    cold = optimize_series(obj, y, mask, t, None, max_iter=0)

    assert warm.init_rung is InitRung.WARM_START
    assert cold.init_rung is InitRung.MOMENT
    assert warm.theta[0, 1] > 15.0
    assert cold.theta[0, 1] < 15.0


# --------------------------------------------------------------------------
# The Hessian
# --------------------------------------------------------------------------


def test_hessian_step_uses_the_fourth_root_of_eps_not_the_third():
    """A second difference wants `eps^(1/4)`, a first difference `eps^(1/3)`.

    Behaviour under test: `hessian_step`.
    Bug this catches: reusing `fd_step`. A second central difference has
    cancellation error `4 eps |f| / h^2`, not `eps |f| / h`, so its optimum is
    `(eps |f| / |f''''|)^(1/4)` -- 1.221e-04, not 6.055e-06. Measured relative
    error against the nested oracle on the real filter at N = 200:

        h = 1e-05 (the plan's rule)   4.39e-05
        h = 6.06e-06 (eps^(1/3))      2.86e-05
        h = 1.22e-04 (eps^(1/4))      2.98e-07

    a factor of 147. The empirical optimum from a sweep over ten decades is
    1e-04, which `eps^(1/4)` sits on.
    """
    assert hessian_step(1.0) == pytest.approx(EPS**0.25, rel=1e-15)
    assert hessian_step(1.0) == pytest.approx(1.221e-4, rel=1e-3)
    # The curvature ratio enters as a fourth root, so 10000x gives 10x.
    assert hessian_step(1e4, 1.0) / hessian_step(1.0, 1.0) == pytest.approx(
        10.0, rel=1e-12
    )
    assert hessian_step(0.0) > 0.0


@pytest.mark.slow
def test_hessian_matches_a_nested_richardson_oracle():
    """The explicit Hessian matches an oracle built from a different algorithm.

    Behaviour under test: `hessian_at_optimum` on the real filter.
    Bug this catches: reusing L-BFGS-B's `hess_inv` quasi-Newton
    approximation. A converged BFGS matrix looks like a Hessian and is far too
    crude for TIC, the sandwich estimator, and the near-degeneracy condition
    number -- and because it is the same shape and roughly the same magnitude,
    nothing downstream would notice. Measured: the explicit Hessian reaches
    2.98e-07 against this oracle, whose own asymmetry is 8.8e-13.
    """
    spec, state_space, _, t, y = _ou_series(n=200)
    obj = _objective(spec, state_space)
    mask = np.ones_like(y, dtype=bool)

    def fn(u):
        return float(
            obj.unconstrained_loglik(np.asarray(u)[None, :], y, mask, t, None)[0]
        )

    u0 = np.array([0.0, np.log(8.0)])
    oracle, asymmetry = _nested_hessian(fn, u0)
    assert asymmetry < 1e-9, "the oracle must out-resolve the thing it checks"

    got = hessian_at_optimum(fn, u0, scale=abs(fn(u0)))
    np.testing.assert_allclose(got, oracle, rtol=1e-5)
    # ...and the plan's step would not have passed this gate.
    coarse = hessian_at_optimum(fn, u0, step=1e-5)
    assert np.max(np.abs(coarse - oracle) / np.abs(oracle)) > 1e-5


def test_the_hessian_is_symmetric_by_construction():
    """Mixed partials are computed once and mirrored.

    Behaviour under test: symmetry.
    Bug this catches: computing both off-diagonals independently and returning
    an asymmetric matrix. `np.linalg.cond` and the inverse both still work, so
    the reported uncertainties would be quietly asymmetric in a quantity that
    is symmetric by definition -- and it doubles the off-diagonal cost.
    """
    spec, state_space, _, t, y = _ou_series(n=120)
    obj = _objective(spec, state_space)
    mask = np.ones_like(y, dtype=bool)

    def fn(u):
        return float(
            obj.unconstrained_loglik(np.asarray(u)[None, :], y, mask, t, None)[0]
        )

    got = hessian_at_optimum(fn, np.array([0.0, np.log(8.0)]), scale=1e2)
    assert np.array_equal(got, got.T)


def test_hessian_refuses_a_point_that_is_not_a_vector():
    """`u` must be one-dimensional, same contract as the gradients.

    Behaviour under test: the shape guard.
    Bug this catches: passing `u[None, :]`, the shape the objectives take,
    which would build a 1x1 Hessian of the wrong quantity.
    """
    with pytest.raises(ValueError, match="one-dimensional"):
        hessian_at_optimum(lambda u: float(np.sum(u**2)), np.zeros((1, 2)))


# --------------------------------------------------------------------------
# Reported uncertainty: first-order, and it says so
# --------------------------------------------------------------------------


def test_the_delta_method_is_exact_to_first_order_and_degrades_with_curvature():
    """`J Sigma_u J^T` is first-order, and the error is quantified here.

    Behaviour under test: the push-through from unconstrained covariance to
    natural units, and the size of the approximation it makes.
    Bug this catches: presenting the delta-method standard error as exact.
    Under a `Log` transform the natural parameter is lognormal, so the true
    variance is `rho^2 (e^s - 1) e^s` with `s = sigma_u^2`, while the delta
    method gives `rho^2 s`. The ratio `(e^s - 1)e^s / s` is derived on paper
    here and is **1.015 at sigma_u = 0.1, 1.459 at 0.5, and 4.671 at 1.0** --
    i.e. 1.5%, 46% and 367% understatement. A parameter pinned near a
    diagnostic limit is exactly where `sigma_u` is large, so this is not a
    corner case; it is the regime the DIAGNOSTIC_LIMIT outcome flags.
    """
    rho = 8.0
    for sigma_u, expected_ratio in ((0.1, 1.0151), (0.5, 1.4588), (1.0, 4.6708)):
        jacobian = np.array([[rho]])  # d rho / d u = rho for a Log transform
        delta = delta_method_cov(jacobian, np.array([[sigma_u**2]]))[0, 0]
        exact = rho**2 * (np.exp(sigma_u**2) - 1.0) * np.exp(sigma_u**2)
        assert delta == pytest.approx(rho**2 * sigma_u**2, rel=1e-12)
        assert exact / delta == pytest.approx(expected_ratio, rel=1e-3)
    # And it really is first-order-correct: the ratio goes to 1 as s goes to 0.
    tiny = 1e-4
    assert (np.exp(tiny**2) - 1.0) * np.exp(tiny**2) / tiny**2 == pytest.approx(
        1.0, rel=1e-7
    )


# --------------------------------------------------------------------------
# The outcome taxonomy
# --------------------------------------------------------------------------


@pytest.mark.slow
def test_the_optimizer_recovers_simulated_parameters():
    """A clean fit converges near the truth and reports OK.

    Behaviour under test: the happy path, end to end.
    Bug this catches: an optimizer descending the wrong surface -- a sign
    error on `negative`, or a gradient in the wrong coordinates. Recovery
    within 30% at N = 200 is a weak but honest check; it is the taxonomy tests
    below that carry the weight.
    """
    spec, state_space, _, t, y = _ou_series(sigma=1.0, rho=8.0, n=400)
    obj = _objective(spec, state_space)
    got = optimize_series(obj, y, np.ones_like(y, dtype=bool), t, None)
    assert got.outcome is Outcome.OK
    assert got.theta[0, 1] == pytest.approx(8.0, rel=0.3)
    assert got.hessian is not None
    assert np.isfinite(got.loglik)


def test_the_iteration_cap_splits_on_the_gradient_norm():
    """Cap-with-small-gradient and cap-with-large-gradient are distinct.

    Behaviour under test: the two cap outcomes.
    Bug this catches: collapsing both into one "not converged" flag. They are
    different scientific facts -- a slow fit that is essentially done, and a
    fit that is nowhere near -- and the map of which occurred where is the
    diagnostic. At 10^7 series nobody re-inspects the individual fit.
    `ITER_CAP_SMALL_GRAD` still counts as a failure under `Outcome.is_failure`
    ("probably fine, flagged" -- flagged, not excluded), which is asserted
    here so the taxonomy and the reporting rule cannot drift apart.
    """
    spec, state_space, _, t, y = _ou_series()
    obj = _objective(spec, state_space)
    capped = optimize_series(obj, y, np.ones_like(y, dtype=bool), t, None, max_iter=1)
    assert capped.outcome in {Outcome.ITER_CAP_SMALL_GRAD, Outcome.ITER_CAP_LARGE_GRAD}
    assert capped.outcome.is_failure
    assert capped.n_iter <= 1


def test_the_hessian_cond_limit_is_the_single_inversion_eps_bound():
    """`HESSIAN_COND_LIMIT` is derived from float64 and counts ONE inversion.

    Behaviour under test: the VALUE of the constant. Every other test of
    `DEGENERATE_HESSIAN` asserts an outcome that holds over a wide band of it.

    Expected value worked out by hand rather than by restating the module's
    own expression: the Hessian is inverted exactly once, to produce `H^-1`
    and hence `theta_err`; the forward error of that inversion goes like
    `eps * cond(H)`; half the significant digits are gone when that reaches
    `sqrt(eps)`, i.e. at `cond(H) = eps^(-1/2) = (2^-52)^(-1/2) = 2^26 =
    67108864` exactly.

    Bug this catches: the previous `1e10`, picked, 149x more permissive, and
    the reason design doc section 4.8's a-posteriori half was looser than its
    a-priori half -- a composite `lint.py` flags statically could come back
    `OK` from the fit. It also catches the far more tempting error of copying
    `objective.CONDITION_LOG_LIMIT`'s exponent: that constant takes a FOURTH
    root because its solve forms the normal equations and so sees
    `cond(X_w)^2`. Nothing is squared on the way to `H^-1`.
    """
    assert HESSIAN_COND_LIMIT == 2.0**26
    assert HESSIAN_COND_LIMIT == 67108864.0
    # The other half of the derivation: eps * cond == sqrt(eps) at the limit.
    assert EPS * HESSIAN_COND_LIMIT == pytest.approx(EPS**0.5, rel=1e-12)


def _composite_series(sigma_white=0.5, sigma=1.0, rho=8.0, n=200, seed=11):
    """Simulate white + Matern 1/2 from the composite's own covariance."""
    spec = ProcessSpec((_term("white"), _term("matern12")))
    state_space = StateSpace.from_spec(spec)
    theta = np.array([[sigma_white, sigma, rho]])
    t = np.arange(float(n))
    cov = _covariance(state_space, theta, t)
    rng = np.random.default_rng(seed)
    return spec, state_space, t, rng.multivariate_normal(np.zeros(n), cov)[None, :]


def _relative_gradient_norm(obj, y, mask, t, fit):
    """`||g|| / max(|loglik|, 1)` at a fit's reported parameters."""

    def negative(u):
        return -float(obj.unconstrained_loglik(u[None, :], y, mask, t, None)[0])

    scale = max(abs(fit.loglik), 1.0)
    point = obj.to_unconstrained(fit.theta)[0]
    return float(np.linalg.norm(fd_gradient(negative, point, scale=scale))) / scale


@pytest.mark.slow
def test_grad_tol_separates_converged_from_unconverged_with_margin():
    """`GRAD_TOL` sits strictly between two measured populations.

    Behaviour under test: the VALUE of `GRAD_TOL`, which nothing else pins.
    Every other test here asserts an outcome that holds over a wide band of
    the constant.

    Expected values determined independently by measurement, recorded in the
    constant's own docstring: over six fits spanning two compositions and
    three record lengths, converged fits reach `||g|| / max(|loglik|, 1)` in
    `3.46e-07 .. 2.30e-05` and fits stopped at one to three iterations sit in
    `1.45e-04 .. 1.84e-02`. The two cases used here are the TIGHT ends of
    those ranges -- the slowest-converging composite, and the shortest
    unconverged gradient -- so the assertions are against the boundary rather
    than against a comfortable middle.

    Bug this catches: `GRAD_TOL` set anywhere outside that gap, in either
    direction, which no outcome-level test can see. The previous `1e-5` was
    BELOW the converged population's maximum, so a fit that was done would be
    filed `ITER_CAP_LARGE_GRAD` -- and this test fails against `1e-5`, which
    is how the defect was confirmed rather than argued. A value above
    `1.45e-04` fails the other assertion. The margin factors are asserted
    separately from the inequalities because "on the right side of the
    threshold" and "not about to cross it" are different facts, and open
    question 9's lesson is that only the second one means healthy.

    **THE MARGIN FACTOR IS 1.5, NOT 2.0, AND THAT IS A MEASUREMENT RATHER THAN
    A CONCESSION.** These two cases were re-run on 2026-08-19 under both numeric
    stacks the project is built against:

        conda-forge, numpy 2.4.6   converged 2.2957e-05   stopped 1.4524e-04
        PyPI wheels, numpy 2.5.2   converged 2.9475e-05   stopped 4.3841e-04

    so the converged margin is 2.18x on one and **1.70x** on the other -- and CI,
    which installs the PyPI stack, failed this test at 1.70x on its first run
    that ever reached the suite. Widening the ladder to every cap at every
    length puts the two populations 2.56x apart across the union, and **no
    threshold holds 2x on both sides of a 2.56x gap**. 1.5 is under the tighter
    measured margin with room, and still fails against any `GRAD_TOL` that
    drifts toward either population. What was lost is the claim that the margin
    is 2x; that claim was never true off one machine.
    """
    spec, state_space, t, y = _composite_series()
    obj = _objective(spec, state_space)
    mask = np.ones_like(y, dtype=bool)
    converged = optimize_series(obj, y, mask, t, None)
    assert converged.outcome is Outcome.OK
    converged_norm = _relative_gradient_norm(obj, y, mask, t, converged)

    spec, state_space, _, t, y = _ou_series(sigma=2.0, rho=20.0, n=630, seed=7)
    obj = _objective(spec, state_space)
    mask = np.ones_like(y, dtype=bool)
    stalled = optimize_series(obj, y, mask, t, None, max_iter=2)
    assert stalled.outcome is Outcome.ITER_CAP_LARGE_GRAD
    stalled_norm = _relative_gradient_norm(obj, y, mask, t, stalled)

    assert converged_norm < GRAD_TOL
    assert stalled_norm > GRAD_TOL
    assert GRAD_TOL / converged_norm > 1.5
    assert stalled_norm / GRAD_TOL > 1.5


@pytest.mark.slow
def test_a_runaway_parameter_reports_the_diagnostic_limit():
    """A series driven into the degenerate direction reports DIAGNOSTIC_LIMIT.

    Behaviour under test: diagnostic limits are REPORTED, never silently
    clipped -- the bijector guarantees `rho > 0`, it does nothing to stop
    `log rho` marching to 14.
    Bug this catches: returning a confident fit sitting at the boundary. A
    near-deterministic series fitted with an OU kernel wants infinite
    correlation length; measured, the optimizer lands at `rho = 1.08e6`,
    past the 1e6 diagnostic limit. Reported as OK, that is a converged fit
    with a finite Hessian and plausible error bars for a model the data do
    not identify at all.
    """
    spec = ProcessSpec((_term("matern12"),))
    state_space = StateSpace.from_spec(spec)
    obj = _objective(spec, state_space)
    n = 200
    t = np.arange(float(n))
    y = np.cos(np.arange(n) / 300.0)[None, :]
    got = optimize_series(obj, y, np.ones_like(y, dtype=bool), t, None)
    assert got.outcome is Outcome.DIAGNOSTIC_LIMIT
    assert got.hessian is None
    assert got.theta[0, 1] >= 1e6


def test_a_failed_design_is_refused_before_the_optimizer_runs():
    """A rank-deficient design short-circuits with the precheck's own outcome.

    Behaviour under test: the first exit path.
    Bug this catches: relabelling the precheck's verdict. A RANK_DEFICIENT_X
    series reported as NONFINITE_OBJECTIVE moves it from "this design cannot
    be identified here" to "the numerics failed", which are different entries
    in the failure map and different follow-up actions.
    """
    mask = np.ones((1, _gapped_setup()[3].size), dtype=bool)
    mask[0] = _window(0)
    spec, state_space, _, t, design, _ = _gapped_setup(mask)
    obj = _objective(spec, state_space)
    got = optimize_series(obj, np.zeros((1, t.size)), mask, t, design)
    assert got.outcome is Outcome.RANK_DEFICIENT_X
    assert np.all(np.isnan(got.theta))
    assert np.isnan(got.loglik)
    assert got.hessian is None
    assert got.n_iter == 0


def test_a_nonfinite_objective_is_reported_not_returned_as_a_number():
    """A fit whose objective never becomes finite reports NONFINITE_OBJECTIVE.

    Behaviour under test: the non-finite exit.
    Bug this catches: letting the `+inf` barrier out of the optimizer. `-inf`
    and `+inf` are finite-looking to some consumers and poison a downstream
    mean; results destined for the store carry NaN. The barrier value is legal
    only inside `negative()`.
    """
    spec, state_space, _, t, y = _ou_series(n=60)
    obj = _objective(spec, state_space)
    mask = np.zeros_like(y, dtype=bool)  # nothing observed: no finite likelihood
    got = optimize_series(obj, y, mask, t, None)
    assert got.outcome is not Outcome.OK
    assert not np.isfinite(got.loglik)
    assert np.isnan(got.loglik), "-inf is not an acceptable store value"


def test_every_scipy_termination_status_maps_to_a_named_outcome():
    """The status mapping is total, and line-search collapse has its own entry.

    Behaviour under test: `outcome_for_status`.
    Bug this catches: an unmapped status falling through to OK. scipy's
    `status == 2` is ABNORMAL_TERMINATION_IN_LNSRCH -- the optimizer could not
    find a step that decreases the objective, which is the line-search analogue
    of a collapsed trust region and is the only route by which
    `TRUST_RADIUS_COLLAPSED` is producible in Phase 1 at all. It is tested at
    this function's boundary rather than through a constructed fit because
    L-BFGS-B on a smooth likelihood does not readily produce it -- the same
    argument, and the same treatment, as `counting.penalty_terms`' contract
    test for the ML `k_beta = rank` rule.
    """
    assert outcome_for_status(0) is Outcome.OK
    assert outcome_for_status(1) is Outcome.ITER_CAP_LARGE_GRAD
    assert outcome_for_status(2) is Outcome.TRUST_RADIUS_COLLAPSED
    # Anything unrecognized is a failure, never a silent success.
    for status in (3, 7, -1):
        assert outcome_for_status(status).is_failure
        assert outcome_for_status(status) is not Outcome.OK


def test_a_degenerate_hessian_is_reported_with_the_matrix_attached():
    """Above the condition limit the fit reports DEGENERATE_HESSIAN.

    Behaviour under test: the near-degeneracy check, and that the offending
    matrix is still returned.
    Bug this catches: discarding the Hessian on that branch. The condition
    number IS the diagnostic -- design doc §4.8's near-degenerate geography --
    so throwing the matrix away removes the only evidence of how degenerate.
    Driven here through the public entry point with the limit lowered, rather
    than by constructing a pathological series, so the branch is exercised
    without a fixture whose degeneracy is itself in question.
    """
    spec, state_space, _, t, y = _ou_series(n=200)
    obj = _objective(spec, state_space)
    got = optimize_series(
        obj, y, np.ones_like(y, dtype=bool), t, None, hessian_cond_limit=1.0
    )
    assert got.outcome is Outcome.DEGENERATE_HESSIAN
    assert got.hessian is not None
    assert float(np.linalg.cond(got.hessian)) > 1.0
    # The same fit at the production limit is fine, so the fixture is not
    # degenerate on its own account -- only against the lowered limit.
    healthy = optimize_series(obj, y, np.ones_like(y, dtype=bool), t, None)
    assert healthy.outcome is Outcome.OK
    assert healthy.hessian is not None
    assert float(np.linalg.cond(healthy.hessian)) < HESSIAN_COND_LIMIT


def test_a_non_ok_fit_never_carries_a_hessian_computed_off_the_optimum():
    """Capped and limit-hit fits return `hessian=None`.

    Behaviour under test: the precedence between "did it converge" and "what
    is the curvature".
    Bug this catches: computing `hessian_at_optimum` at a point that is not an
    optimum, and reporting uncertainties from it. It also costs 2p^2 extra
    filter passes on exactly the fits that were already slow enough to hit the
    cap. DEGENERATE_HESSIAN is the one non-OK outcome that keeps its matrix,
    because there the matrix is the finding.
    """
    spec, state_space, _, t, y = _ou_series()
    obj = _objective(spec, state_space)
    capped = optimize_series(obj, y, np.ones_like(y, dtype=bool), t, None, max_iter=1)
    assert capped.outcome is not Outcome.OK
    assert capped.hessian is None


def test_series_fit_is_deliberately_scalar():
    """`SeriesFit` holds scalars, and that is correct at this boundary.

    Behaviour under test: the documented exception to "(B, N) is the only code
    path".
    Bug this catches: a later batch-granularity sweep "fixing" this into
    arrays. `optimize_series` IS path A's per-series reference form -- design
    doc §17 makes it the permanent shape if the spike goes path B's way -- so
    a scalar outcome here is the design, not an oversight. The conversion to
    `(B, M)` uint8 codes happens once, in `fit`.
    """
    spec, state_space, _, t, y = _ou_series(n=80)
    obj = _objective(spec, state_space)
    got = optimize_series(obj, y, np.ones_like(y, dtype=bool), t, None)
    assert isinstance(got, SeriesFit)
    assert isinstance(got.outcome, Outcome)
    assert isinstance(got.loglik, float)
    assert isinstance(got.n_iter, int)
    assert isinstance(got.init_rung, InitRung)
    assert got.theta.shape == (1, 2)


def test_a_wholly_masked_series_stays_insufficient_data():
    """Land and permanent ice never enter the failure numerator.

    Behaviour under test: the data-level fact outranks the design precheck.
    Bug this catches: reporting `RANK_DEFICIENT_X`. An all-masked series has an
    all-zero restricted design, so `check_design` calls it rank deficient and
    is not wrong on its own terms -- but `objective.evaluate` already has the
    ladder that settles which fact is REPORTED, and the answer is the
    data-level one. Measured before the fix: a wholly-masked series came back
    `RANK_DEFICIENT_X`, `is_failure=True`, `is_eligible=True`, putting every
    land pixel into both the numerator and the denominator of the design doc
    section 8.6 failure rate. `optimize_series` short-circuited on
    `check_design` alone and never let `evaluate`'s merge run.
    """
    mask = np.ones((1, _gapped_setup()[3].size), dtype=bool)
    mask[0] = False
    spec, state_space, _, t, design, _ = _gapped_setup(mask)
    obj = _objective(spec, state_space)
    got = optimize_series(obj, np.zeros((1, t.size)), mask, t, design)
    assert got.outcome is Outcome.INSUFFICIENT_DATA
    assert not got.outcome.is_failure
    assert not got.outcome.is_eligible
    # Also with no design at all, where there is no precheck to short-circuit.
    plain = ProcessSpec((_term("matern12"),))
    bare = _objective(plain, StateSpace.from_spec(plain))
    assert (
        optimize_series(bare, np.zeros((1, t.size)), mask, t, None).outcome
        is Outcome.INSUFFICIENT_DATA
    )


@pytest.mark.slow
def test_an_ill_conditioned_design_is_not_laundered_into_nonfinite():
    """A fit that fails numerically reports what `evaluate` says it failed of.

    Behaviour under test: the non-finite exit consults the objective's own
    merged verdict instead of asserting its own.
    Bug this catches: blanket `NONFINITE_OBJECTIVE`. The 2-post-break design
    passes the precheck at full rank 4 with `cond(X_r) = 2.68e4` and is
    classified `ILL_CONDITIONED_X` inside the whitened solve, so every
    evaluation returns NaN and the optimizer sees only `+inf`. Measured before
    the fix: `nonfinite_objective`, which moves "barely identified by a handful
    of post-break samples" into "the numerics failed" -- different map entry,
    different follow-up, and it erases the distinction `ILL_CONDITIONED_X` was
    split out to preserve.
    """
    mask = np.ones((1, _gapped_setup()[3].size), dtype=bool)
    mask[0] = _window(2)
    spec, state_space, _, t, design, _ = _gapped_setup(mask)
    obj = _objective(spec, state_space)
    # The seed is pinned because the classification is THETA-dependent: it is
    # the whitened Gram X_r' Sigma^-1 X_r that is ill conditioned, not X_r.
    # Measured across five seeds at this mask, design.condition_number is
    # 2.68e4 every time while the outcome is ill_conditioned_x for seeds 0 and
    # 1 and ok for 2, 3 and 4. A fixture that varied the seed would be flaky
    # and a fixture asserting only design.condition_number would test the
    # wrong quantity.
    y = np.random.default_rng(0).standard_normal((1, t.size))
    got = optimize_series(obj, y, mask, t, design)
    assert got.outcome is Outcome.ILL_CONDITIONED_X
    assert np.isnan(got.loglik)
    assert got.hessian is None


# --------------------------------------------------------------------------
# `hessian_condition` -- D9's kappa axis, and the two causes of "undefined"
# --------------------------------------------------------------------------


def test_an_indefinite_hessian_has_no_condition_number_although_cond_returns_one():
    """A non-positive-definite Hessian reports UNDEFINED, not a severity.

    Behaviour under test: `hessian_condition`'s definiteness test, which is
    the whole difference between it and `np.linalg.cond`.

    Expected values determined independently: `diag(1, -4)` is symmetric with
    eigenvalues 1 and -4, so it is indefinite by inspection; `np.linalg.cond`
    of it is the singular-value ratio 4.0, computed here to show that the
    naive implementation returns a perfectly ordinary number.

    Bug this catches: `hessian_condition` implemented as `np.linalg.cond`
    alone. D9 gives `undefined` a bin of its own precisely so a
    non-positive-definite Hessian does not fall into the worst conditioning
    bin -- a category reported as a severity. The defect is invisible in any
    output the audit produces: the cell lands in a real bin with a real
    number.
    """
    indefinite = np.diag([1.0, -4.0])
    assert np.isclose(float(np.linalg.cond(indefinite)), 4.0), (
        "the naive implementation must return a finite ordinary number here, "
        "or this test is not showing what it claims to"
    )
    assert np.isnan(hessian_condition(indefinite))

    # The paired positive: the same ratio on a POSITIVE definite matrix is
    # reported, so the NaN above is the definiteness test and not a blanket
    # refusal.
    assert hessian_condition(np.diag([1.0, 4.0])) == 4.0


def test_no_hessian_and_a_nonfinite_hessian_are_both_undefined():
    """The other two causes of NaN, each on its own.

    Behaviour under test: `None` and a matrix carrying NaN both report
    undefined rather than raising or returning `inf`.

    Bug this catches: `float(np.linalg.cond(None))`, which raises, and
    `np.linalg.cond` of a NaN-carrying matrix, which returns NaN from LAPACK
    on some builds and raises `LinAlgError` on others -- a platform-dependent
    audit. Every early return in `optimize_series` supplies `None` here.
    """
    assert np.isnan(hessian_condition(None))
    assert np.isnan(hessian_condition(np.array([[np.nan, 0.0], [0.0, 1.0]])))


def test_the_recorded_condition_number_travels_with_the_verdict_it_was_taken_on():
    """`DEGENERATE_HESSIAN` keeps its matrix AND its number.

    Behaviour under test: `hessian_cond` is populated on the one non-OK
    outcome that carries a curvature, and on OK, and the fit that is healthy at
    the production limit is the same fit that degenerates under a lowered one
    -- so the number the audit bins by is the number the verdict was taken on.

    Expected value determined independently: the limit is driven below the
    fixture's own recorded condition number, through `optimize_series`'s
    `hessian_cond_limit` argument, which exists (per its docstring) so the
    branch can be exercised without a fixture whose degeneracy is itself in
    question.

    Bug this catches: `hessian_cond` recorded only on the OK path. D9 bins the
    audit's cells by the COLD arm's value, and a cold arm that failed with
    `DEGENERATE_HESSIAN` would then carry NaN for a curvature that exists and
    was measured -- the `undefined` bin absorbing a cell that belongs in the
    worst real one, which is the same category error read backwards.
    """
    spec, state_space, _, t, y = _ou_series(n=200)
    obj = _objective(spec, state_space)
    mask = np.ones_like(y, dtype=bool)

    healthy = optimize_series(obj, y, mask, t, None)
    assert healthy.outcome is Outcome.OK, "the fixture must fit before it degenerates"
    assert np.isfinite(healthy.hessian_cond)
    assert healthy.hessian is not None
    assert healthy.hessian_cond == float(np.linalg.cond(healthy.hessian))

    degenerate = optimize_series(
        obj, y, mask, t, None, hessian_cond_limit=healthy.hessian_cond / 2.0
    )
    assert degenerate.outcome is Outcome.DEGENERATE_HESSIAN
    assert degenerate.hessian is not None
    assert np.isfinite(degenerate.hessian_cond)


def test_an_indefinite_hessian_is_ok_with_an_undefined_kappa_and_still_degenerates(
    monkeypatch,
):
    """The verdict reads `np.linalg.cond`; the audit's axis reads definiteness.

    Behaviour under test: the two disagree on exactly one class of matrix, and
    each keeps its own rule. This is the branch that decides whether adding the
    diagnostic moved a verdict.

    **THE HESSIAN IS SUBSTITUTED BECAUSE NO FIXTURE IN THIS TREE PRODUCES AN
    INDEFINITE ONE THROUGH `optimize_series`**, and constructing a series that
    did would be a fixture whose definiteness is itself in question. Exactly
    one collaborator is replaced -- the curvature -- and everything asserted
    is downstream of it.

    Expected values determined independently: `diag(1, -4, ...)` is indefinite
    by inspection with `np.linalg.cond` equal to 4.0, so under the production
    limit of 2**26 the taxonomy must say `OK`, and under a limit of 1.0 it must
    say `DEGENERATE_HESSIAN`. `hessian_condition` must say `undefined` in both.

    Bug this catches: `if hessian_condition(hessian) > limit`, the obvious
    tidy-up once the function exists. `nan > 1.0` is False, so the second call
    below would come back `OK` -- every indefinite Hessian silently
    reclassified as healthy, with `theta_err` published from an inverse that is
    not a covariance. It ALSO catches the reverse tidy-up, `hessian_cond`
    assigned from `np.linalg.cond` at the call site: the first call would then
    report a finite 4.0 for a matrix that has no condition number, and D9's
    `undefined` bin would never receive a member.
    """
    spec, state_space, _, t, y = _ou_series(n=200)
    obj = _objective(spec, state_space)
    mask = np.ones_like(y, dtype=bool)

    def indefinite(fn, u, scale=1.0, curvature=None, step=None):
        width = np.asarray(u).size
        eigenvalues = np.ones(width)
        eigenvalues[-1] = -4.0
        return np.diag(eigenvalues)

    monkeypatch.setattr(optimize_module, "hessian_at_optimum", indefinite)

    ok = optimize_series(obj, y, mask, t, None)
    assert ok.outcome is Outcome.OK, (
        "cond(diag(1, ..., -4)) is 4.0, far under the production limit, so the "
        "taxonomy must still call this fit OK"
    )
    assert np.isnan(ok.hessian_cond), (
        "an indefinite Hessian has no condition number, so D9's `undefined` bin "
        "is reachable on an OK cell -- which is the only reason that bin is not "
        "empty by construction the way the two upper ones are"
    )

    forced = optimize_series(obj, y, mask, t, None, hessian_cond_limit=1.0)
    assert forced.outcome is Outcome.DEGENERATE_HESSIAN, (
        "the verdict is taken on np.linalg.cond, which is 4.0 > 1.0; routing it "
        "through hessian_condition would compare nan > 1.0 and return OK"
    )
    assert np.isnan(forced.hessian_cond)
