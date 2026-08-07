"""Tests for Matérn ν=1/2's analytic derivatives and capability resolution.

The oracle is `richardson_gradient`, not complex-step: Task 11 measured
complex-step returning exactly zero through `ConcentratedObjective`, and the
verdict note records why. Complex-step *is* exact on these closed forms — the
casts that kill it live in the objective, not in the family — so it appears
here as a corroborating second route, never as the gate.

**Tolerance.** `1e-11` throughout, and it is derived rather than round. The
oracle's own worst disagreement with the hand-differentiated forms, measured
across all three derivatives at `h0 = 1e-2`, is **6.67e-13**; `1e-11` sits 15×
above that so the gate tests the derivative and not the oracle's floor. It is
four decades below the ~1e-7 that an actual derivation error would produce, and
— the point of using this oracle at all — plain central differences resolve
only to ~4e-11, so a 1e-11 gate is one a wrong derivative could not sneak past
by agreeing with a weak reference.
"""

from __future__ import annotations

import numpy as np
import pytest

from metamer.core import gradients
from metamer.core.capability import (
    GradientMode,
    Objective,
    intersect_gradient_modes,
)
from metamer.core.engines.kalman import KalmanEngine
from metamer.core.families.base import supports_analytic_gradient
from metamer.core.families.matern12 import Matern12
from metamer.core.gradients import (
    AnalyticGradientError,
    complex_step_gradient,
    fd_gradient,
    resolve_gradient_mode,
)
from metamer.core.objective import ConcentratedObjective
from metamer.core.outcomes import Outcome
from metamer.core.terms import ProcessSpec
from tests.test_objective import _gapped_setup, _window
from tests.test_statespace import _term

RTOL = 1e-11
DT, SIGMA, RHO = 2.0, 1.3, 5.0
THETA = np.array([SIGMA, RHO])


def _oracle(scalar_fn):
    """Richardson gradient of a scalar function of (sigma, rho)."""
    return gradients.richardson_gradient(scalar_fn, THETA)


def _spec(*kinds):
    return ProcessSpec(tuple(_term(k) for k in kinds))


# --------------------------------------------------------------------------
# The three analytic derivatives
# --------------------------------------------------------------------------


def test_transition_derivative_matches_the_oracle_and_the_paper_form():
    """`dF/drho = (dt/rho^2) exp(-dt/rho)`, and `dF/dsigma` is exactly zero.

    Behaviour under test: `Matern12.dtransition`.
    Bug this catches: a sign error on the chain rule. `d/drho exp(-dt/rho)` is
    POSITIVE -- longer memory means less decay per step -- and writing
    `-(dt/rho**2) F` gives a derivative of the right magnitude pointing the
    wrong way, which no magnitude-only check would see.
    """
    got = Matern12().dtransition(THETA[None, :], DT)[0, :, 0, 0]
    paper = np.array([0.0, DT / RHO**2 * np.exp(-DT / RHO)])
    np.testing.assert_allclose(got, paper, rtol=1e-15)
    np.testing.assert_allclose(
        got, _oracle(lambda p: float(np.exp(-DT / p[1]))), rtol=RTOL
    )
    assert got[0] == 0.0  # exactly, not approximately


def test_stationary_cov_derivative_matches_the_oracle_and_the_paper_form():
    """`dP_inf/dsigma = 2 sigma`, and `dP_inf/drho` is exactly zero.

    Behaviour under test: `Matern12.dstationary_cov`.
    Bug this catches: treating `sigma` as a variance rather than a marginal
    standard deviation. The family's own docstring fixes `P_inf = sigma^2`, so
    `dP_inf/dsigma` is `2 sigma` and not `1`; the two agree only at
    `sigma = 0.5`, which is exactly the sort of value a fixture picks.
    """
    got = Matern12().dstationary_cov(THETA[None, :])[0, :, 0, 0]
    np.testing.assert_allclose(got, np.array([2.0 * SIGMA, 0.0]), rtol=1e-15)
    np.testing.assert_allclose(got, _oracle(lambda p: float(p[0] ** 2)), rtol=RTOL)
    assert got[1] == 0.0


def test_process_noise_derivative_matches_the_oracle_and_the_paper_form():
    """`dQ/dsigma = 2 sigma (1 - e^-2dt/rho)`, `dQ/drho = -sigma^2 e^-2dt/rho 2dt/rho^2`.

    Behaviour under test: `Matern12.dprocess_noise`.
    Bug this catches: the sign of `dQ/drho`. `Q` DECREASES with `rho` at fixed
    `dt` -- a longer timescale means less new variance injected per step -- so
    the derivative is negative. Differentiating the decay factor without the
    inner minus sign flips it.
    """
    decay = np.exp(-2.0 * DT / RHO)
    paper = np.array(
        [
            2.0 * SIGMA * -np.expm1(-2.0 * DT / RHO),
            -(SIGMA**2) * decay * (2.0 * DT / RHO**2),
        ]
    )
    got = Matern12().dprocess_noise(THETA[None, :], DT)[0, :, 0, 0]
    np.testing.assert_allclose(got, paper, rtol=1e-15)
    np.testing.assert_allclose(
        got,
        _oracle(lambda p: float(p[0] ** 2 * -np.expm1(-2.0 * DT / p[1]))),
        rtol=RTOL,
    )
    assert paper[1] < 0.0  # the sign the fixture exists to pin


def test_process_noise_derivative_keeps_precision_at_a_small_step_ratio():
    """`dQ/dsigma` is built with `-expm1`, never with `1 - exp`.

    Behaviour under test: the cancellation-safe form, in the derivative as well
    as in `Q` itself -- `process_noise` already gets this right and its
    docstring says so, which is exactly why a derivative written from the
    algebra rather than from that docstring reintroduces it.
    Bug this catches: `2 sigma (1.0 - np.exp(-x))`. Measured relative error of
    that form against `-expm1`: 1.18e-16 at `x = 2e-1`, 1.09e-10 at `2e-7`,
    **8.28e-08 at 2e-10**, 7.99e-04 at `2e-14`.

    **The ordinary fixture cannot catch this.** At `DT = 2, RHO = 5` the ratio
    `2dt/rho` is 0.8 and the two forms agree to 1.18e-16 -- three decades
    tighter than this module's own gate. Only a small ratio separates them, so
    the small ratio is the fixture. `rho`'s diagnostic limit is 1e6 and the
    caller picks the time units, so this regime is reachable, not contrived.
    """
    rho, dt = 5.0, 5e-10  # 2 dt / rho = 2e-10
    theta = np.array([[SIGMA, rho]])
    got = Matern12().dprocess_noise(theta, dt)[0, 0, 0, 0]
    exact = 2.0 * SIGMA * -np.expm1(-2.0 * dt / rho)
    forbidden = 2.0 * SIGMA * (1.0 - np.exp(-2.0 * dt / rho))

    np.testing.assert_allclose(got, exact, rtol=RTOL)
    # The two forms really do differ here, by far more than the gate allows --
    # otherwise this test would pass against the defect it names.
    assert abs(forbidden - exact) / exact > 1e-9


def test_derivatives_vanish_at_a_zero_step():
    """At `dt = 0`, `dF/dtheta` and `dQ/dtheta` are exactly zero.

    Behaviour under test: the `dt = 0` endpoint, which the family's docstring
    makes a hard requirement -- `F = I` and `Q = 0` exactly, because repeated
    timestamps are ordinary in real records.
    Bug this catches: a floor on `dt` or an epsilon added for stability. Either
    makes these derivatives small-but-nonzero, which injects a gradient
    component for a step that carries no information. Exact equality is the
    assertion, because "approximately zero" is what the defect produces.
    """
    assert np.all(Matern12().dtransition(THETA[None, :], 0.0) == 0.0)
    assert np.all(Matern12().dprocess_noise(THETA[None, :], 0.0) == 0.0)
    # P_inf does not depend on dt, so it is unaffected.
    assert Matern12().dstationary_cov(THETA[None, :])[0, 0, 0, 0] == 2.0 * SIGMA


def test_derivatives_are_evaluated_per_series():
    """Each row of `theta` gets its own derivative, shape `(B, p, d, d)`.

    Behaviour under test: batching over the leading axis.
    Bug this catches: computing from `theta[0]` and broadcasting, which is
    right only when every series shares parameters -- true in a test fixture
    and false everywhere else, since theta is what the optimizer varies.
    """
    batch = np.array([[1.0, 2.0], [1.3, 5.0], [0.5, 40.0]])
    got = Matern12().dtransition(batch, DT)
    assert got.shape == (3, 2, 1, 1)
    for b in range(3):
        solo = Matern12().dtransition(batch[b : b + 1], DT)
        np.testing.assert_allclose(got[b], solo[0], rtol=1e-15)
    # And the rows genuinely differ, so the loop above could fail.
    assert got[0, 1, 0, 0] != got[1, 1, 0, 0]


def test_complex_step_corroborates_on_the_closed_forms():
    """Complex-step is exact HERE, which localizes Task 11's verdict.

    Behaviour under test: nothing new in the family -- this is the control.
    Bug this catches: reading Task 11's verdict as "complex-step is broken".
    It is not; `complex_step_gradient` reproduces these derivatives to 1e-16.
    What is broken is the float64 cast chain in `ConcentratedObjective._map`,
    and keeping that distinction executable is what stops a later session from
    trying to fix the wrong thing.
    """
    got = Matern12().dprocess_noise(THETA[None, :], DT)[0, :, 0, 0]
    oracle = complex_step_gradient(
        lambda p: p[0] ** 2 * -np.expm1(-2.0 * DT / p[1]), THETA
    )
    np.testing.assert_allclose(got, oracle, rtol=1e-14)


# --------------------------------------------------------------------------
# Capability resolution
# --------------------------------------------------------------------------


def test_gradient_capability_is_per_objective():
    """Matérn ν=1/2 ships analytic ML gradients and finite-difference REML.

    Behaviour under test: the per-objective split.
    Bug this catches: one flag for both. Under ML the envelope theorem removes
    the `d beta_hat / d theta` term exactly; the REML penalty
    `-0.5 log|X' Sigma^-1 X|` is not covered by that argument, so its analytic
    gradient is strictly more work and is not claimed here.
    """
    modes = Matern12().gradient_modes
    assert modes[Objective.ML] is GradientMode.ANALYTIC
    assert modes[Objective.REML] is GradientMode.FINITE_DIFFERENCE


def test_a_composite_falls_back_when_any_term_lacks_analytic_gradients():
    """`matern12 + matern32` resolves to FINITE_DIFFERENCE under both objectives.

    Behaviour under test: `resolve_gradient_mode` over a real `ProcessSpec`,
    not a hand-built mapping -- the registry lookup is part of what can break.
    Bug this catches: a composite reporting ANALYTIC while running FD, which is
    a ~1.7x cost difference at p=6 and makes the wall-time projection wrong in
    the direction that looks fine until the 19 ms budget is measured.
    """
    mixed = _spec("matern12", "matern32")
    assert resolve_gradient_mode(mixed, Objective.ML) is GradientMode.FINITE_DIFFERENCE
    assert (
        resolve_gradient_mode(mixed, Objective.REML) is GradientMode.FINITE_DIFFERENCE
    )


def test_a_composite_of_analytic_terms_resolves_analytic_under_ml_only():
    """`matern12 + matern12` is ANALYTIC under ML and FINITE_DIFFERENCE under REML.

    Behaviour under test: intersection carries the per-objective split through
    a composite.
    Bug this catches: resolving once and reusing the answer for both
    objectives, which would claim an analytic REML gradient nothing supplies.
    """
    both = _spec("matern12", "matern12")
    assert resolve_gradient_mode(both, Objective.ML) is GradientMode.ANALYTIC
    assert resolve_gradient_mode(both, Objective.REML) is GradientMode.FINITE_DIFFERENCE


def test_intersection_is_over_every_term_not_only_the_first():
    """A lacking term anywhere in the composite decides the answer.

    Behaviour under test: the intersection's reach.
    Bug this catches: checking `terms[0]` only. Canonical ordering means the
    analytic family may well sort first, so a first-term-only check returns
    ANALYTIC for exactly the composites that need FD.
    """
    has = {Objective.ML: GradientMode.ANALYTIC}
    lacks = {Objective.ML: GradientMode.FINITE_DIFFERENCE}
    assert (
        intersect_gradient_modes([has, has, lacks], Objective.ML)
        is GradientMode.FINITE_DIFFERENCE
    )
    assert (
        intersect_gradient_modes([has, has, has], Objective.ML) is GradientMode.ANALYTIC
    )


def test_a_stub_family_exercises_resolution_without_shipping_a_family():
    """Resolution is testable against a family that exists only for the test.

    Behaviour under test: the resolution path for a third-party kernel.
    Bug this catches: logic exercised only through the two real families, so a
    bug in it stays hidden until someone registers a kernel out of tree --
    which is the whole point of the registry being extensible.
    """

    class _Stub:
        gradient_modes = {
            Objective.ML: GradientMode.ANALYTIC,
            Objective.REML: GradientMode.ANALYTIC,
        }

        def dtransition(self, theta, dt): ...
        def dprocess_noise(self, theta, dt): ...
        def dstationary_cov(self, theta): ...

    stub = _Stub()
    assert supports_analytic_gradient(stub)
    assert (
        intersect_gradient_modes(
            [stub.gradient_modes, Matern12().gradient_modes], Objective.REML
        )
        is GradientMode.FINITE_DIFFERENCE
    )
    assert (
        intersect_gradient_modes(
            [stub.gradient_modes, stub.gradient_modes], Objective.REML
        )
        is GradientMode.ANALYTIC
    )


def test_a_family_claiming_analytic_without_implementing_it_is_refused():
    """A declared mode that no method backs is a hard error, not a downgrade.

    Behaviour under test: `resolve_gradient_mode` verifies the claim against
    the implementation.
    Bug this catches: trusting `gradient_modes` alone. A kernel that declares
    ANALYTIC and ships no `dtransition` would have the composite report
    ANALYTIC while FD silently runs -- the *inverse* of a silent fallback and
    just as invisible. Downgrading quietly would be no better: the acceptance
    criterion is that the mode is reported, and a mode that was corrected
    behind the caller's back is not reported.
    """

    class _Liar:
        kind = "liar"
        gradient_modes = {
            Objective.ML: GradientMode.ANALYTIC,
            Objective.REML: GradientMode.FINITE_DIFFERENCE,
        }

    assert not supports_analytic_gradient(_Liar())
    with pytest.raises(AnalyticGradientError, match="liar"):
        resolve_gradient_mode(_spec("matern12"), Objective.ML, families=[_Liar()])


def test_matern12_actually_implements_what_it_declares():
    """The shipped family passes the same check the stub fails.

    Behaviour under test: the guard is not vacuous.
    Bug this catches: a `supports_analytic_gradient` that returns False for
    everything, which would make the test above pass for the wrong reason and
    make the real family unusable.
    """
    assert supports_analytic_gradient(Matern12())
    assert (
        resolve_gradient_mode(_spec("matern12"), Objective.ML) is GradientMode.ANALYTIC
    )


def test_the_reported_mode_describes_the_family_not_the_optimizer_path():
    """ANALYTIC here means "the family supplies dF, dQ, dP_inf" -- nothing more.

    Behaviour under test: the documented boundary of Task 12. Phase 1 ships no
    differentiated Kalman filter, so the optimizer still calls `fd_gradient`
    even where this resolves to ANALYTIC.
    Bug this catches: a reader taking a reported ANALYTIC as evidence that
    finite differences were not used -- and, more usefully, going stale. If
    someone lands a likelihood-level analytic gradient, this assertion fails
    and forces the boundary to be restated rather than quietly outgrown.
    """
    assert (
        resolve_gradient_mode(_spec("matern12"), Objective.ML) is GradientMode.ANALYTIC
    )
    assert not hasattr(gradients, "analytic_loglik_gradient")


# --------------------------------------------------------------------------
# Failed fits
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "post_break_kept, expected, precheck",
    [
        (2, Outcome.ILL_CONDITIONED_X, Outcome.OK),
        (0, Outcome.RANK_DEFICIENT_X, Outcome.RANK_DEFICIENT_X),
    ],
)
def test_a_gradient_through_a_failed_fit_is_not_a_plausible_number(
    post_break_kept, expected, precheck
):
    """A design that fails the ladder yields NaN gradients, not finite ones.

    Behaviour under test: the seam between the outcome ladder and the gradient
    routines. `evaluate` returns NaN log-likelihood for a series whose design
    is ill-conditioned or rank-deficient, and NaN minus NaN over `2h` is NaN.
    Bug this catches: any place that substitutes a finite value for a failed
    evaluation -- a `nan_to_num`, a barrier constant leaking out of the
    optimizer, or a fallback that reuses the last good likelihood. All three
    give the optimizer a real-looking descent direction computed from a fit
    that does not exist, and at 10^7 series nobody inspects the one that went
    wrong.

    **The two bands reach NaN by DIFFERENT ROUTES, which is why both are here
    rather than one standing in for the other.** Measured on this fixture:
    keeping 0 post-break samples gives `rank(X_r) = 2` of 4 and the
    design PRECHECK refuses it before the engine runs; keeping 2 gives full
    rank 4 with `cond(X_r) = 2.68e4`, so the precheck passes and the series is
    classified ILL_CONDITIONED_X inside the whitened solve instead. That is
    the recorded rule that `check_design`'s batch-level rank is necessary but
    not sufficient -- a gradient routine that handled only the early-return
    path would look correct against the rank-deficient case alone.
    """
    mask = np.ones((1, _gapped_setup()[3].size), dtype=bool)
    mask[0] = _window(post_break_kept)
    spec, state_space, theta, t, design, _ = _gapped_setup(mask)
    obj = ConcentratedObjective(spec, state_space, KalmanEngine(), Objective.ML)

    assert np.all(obj.check_design(design, 1) == precheck.code)

    result = obj.evaluate(theta, np.zeros((1, t.size)), mask, t, design)
    assert result.outcome[0] == expected.code
    assert np.isnan(result.loglik[0])

    u0 = obj.to_unconstrained(theta)[0]

    def fn(u):
        return float(
            obj.unconstrained_loglik(
                u[None, :], np.zeros((1, t.size)), mask, t, design
            )[0]
        )

    got = fd_gradient(fn, u0, scale=1e4)
    assert np.all(np.isnan(got)), f"failed fit produced a finite gradient: {got}"


def test_the_failed_fit_fixture_would_notice_a_working_gradient():
    """The same call on a HEALTHY design returns finite, nonzero components.

    Behaviour under test: the fixture above is capable of distinguishing.
    Bug this catches: a gradient that is NaN for every design -- a broken
    wrapper, say -- which would make the failed-fit test pass while proving
    nothing at all.
    """
    spec, state_space, theta, t, design, mask = _gapped_setup()
    obj = ConcentratedObjective(spec, state_space, KalmanEngine(), Objective.ML)
    assert np.all(obj.check_design(design, 1) == Outcome.OK.code)

    rng = np.random.default_rng(11)
    y = rng.standard_normal((1, t.size))
    u0 = obj.to_unconstrained(theta)[0]

    def fn(u):
        return float(obj.unconstrained_loglik(u[None, :], y, mask, t, design)[0])

    got = fd_gradient(fn, u0, scale=abs(fn(u0)))
    assert np.all(np.isfinite(got))
    assert np.any(np.abs(got) > 1e-6)


def test_derivatives_of_a_failed_series_are_still_well_defined_at_the_family():
    """The FAMILY derivatives do not know about outcomes, and should not.

    Behaviour under test: the boundary. `dtransition` is a property of the
    closed form at a given theta; it is finite wherever theta is finite,
    whatever the design did.
    Bug this catches: pushing outcome handling down into the families, which
    would put the failure ladder in `p` places instead of one and let a family
    disagree with `objective.evaluate` about whether a series failed.
    """
    got = Matern12().dtransition(np.array([[1e-8, 1e6]]), DT)
    assert np.all(np.isfinite(got))
    got_nan = Matern12().dtransition(np.array([[np.nan, RHO]]), DT)
    assert np.isfinite(got_nan[0, 1, 0, 0])  # drho does not involve sigma
