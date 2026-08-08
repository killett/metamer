"""Tests for the finite-difference gradients, the step rule, and the oracle.

The reference gradient for the real filter is **Romberg-extrapolated central
differences** -- repeated Richardson from a step well inside the
truncation-dominated region. That is the design doc's designated fallback
oracle (§8.2), adopted because complex-step is not viable through this filter;
see `docs/superpowers/notes/complex-step-verdict.md`.

Every tolerance in this module is a measured number, not a guess. The
measurements are quoted in the test that uses them so a later reader can tell a
calibrated bound from a hopeful one.
"""

from __future__ import annotations

import math
import pathlib
import warnings

import numpy as np
import pytest

from metamer.core.capability import Objective
from metamer.core.engines.kalman import KalmanEngine
from metamer.core.gradients import (
    EPS,
    RICHARDSON_H0,
    complex_step_gradient,
    fd_gradient,
    fd_step,
    richardson_gradient,
)
from metamer.core.objective import ConcentratedObjective
from metamer.core.statespace import StateSpace
from metamer.core.terms import ProcessSpec
from tests.test_statespace import _term

VERDICT_NOTE = pathlib.Path("docs/superpowers/notes/complex-step-verdict.md")


def _analytic(u):
    """A function with a NON-ZERO third derivative, so truncation error is real.

    A quadratic is useless here: its third derivative vanishes, so central
    differences are exact for any step and no step rule can be distinguished
    from any other.
    """
    return np.sin(3.0 * u[0]) + u[1] ** 3 + 0.5 * u[0] * u[1]


def _analytic_grad(u):
    """Gradient of `_analytic`, differentiated on paper."""
    return np.array(
        [3.0 * np.cos(3.0 * u[0]) + 0.5 * u[1], 3.0 * u[1] ** 2 + 0.5 * u[0]]
    )


def _filter_objective(n):
    """Build the real matern32 objective on `n` epochs, plus its scalar wrapper."""
    spec = ProcessSpec((_term("matern32"),))
    state_space = StateSpace.from_spec(spec)
    obj = ConcentratedObjective(spec, state_space, KalmanEngine(), Objective.ML)
    t = np.arange(float(n))
    rng = np.random.default_rng(7)
    y = rng.standard_normal((1, n))
    mask = np.ones_like(y, dtype=bool)

    def fn(u):
        return float(
            obj.unconstrained_loglik(np.asarray(u)[None, :], y, mask, t, None)[0]
        )

    return obj, fn, (y, mask, t)


U0 = np.array([0.0, math.log(5.0)])


# --------------------------------------------------------------------------
# The step rule
# --------------------------------------------------------------------------


def test_fd_step_is_set_by_the_curvature_ratio_not_the_objective_magnitude():
    """`fd_step` implements `(eps |l| / |l''|)^(1/3)`, both arguments.

    Behaviour under test: the denominator design doc §8.2 specifies.
    Bug this catches: dropping `|l''|` and using `(eps |l|)^(1/3)`. For a
    log-likelihood BOTH `|l|` and `|l''|` scale with N, so the ratio is O(1)
    and the step should barely move with N. Measured on the real matern32
    filter against a Romberg reference, relative gradient error:

        rule                    N=100      N=630      N=5000
        (eps |l|)^(1/3)       1.19e-08   4.51e-08   1.98e-07
        (eps |l|/|l''|)^(1/3) 4.28e-11   1.00e-10   1.76e-10

    The dropped denominator is 280x to 1100x worse, and at N=5000 it misses
    this task's own "1e-7 relative" acceptance criterion.
    """
    # Equal magnitudes are a ratio of one, so the step must not move.
    assert fd_step(1e3, 1e3) == pytest.approx(fd_step(1e6, 1e6))
    # A ratio of 1000 raises the step by its cube root, exactly 10.
    assert fd_step(1e6, 1e3) / fd_step(1e3, 1e3) == pytest.approx(10.0, rel=1e-12)
    # And the ratio is what enters, not the two magnitudes separately.
    assert fd_step(2e6, 2e3) == pytest.approx(fd_step(1e6, 1e3))


def test_fd_step_defaults_to_the_cube_root_of_eps():
    """With no curvature supplied the ratio is one, giving `eps^(1/3)`.

    Behaviour under test: the default.
    Bug this catches: a default that folds the objective magnitude in anyway.
    Expected value from the formula: `(eps * 1)^(1/3) = 6.055e-06`, which the
    sweep found sits inside the measured optimum `h in [1e-6, 1e-5]` at every
    N tested.
    """
    assert fd_step(1.0) == pytest.approx(EPS ** (1.0 / 3.0), rel=1e-15)
    assert fd_step(2.4e5) == pytest.approx(EPS ** (1.0 / 3.0), rel=1e-15)
    assert fd_step(2.4e5) == pytest.approx(6.055e-6, rel=1e-3)


def test_fd_step_never_returns_a_step_of_zero():
    """A degenerate scale still yields a usable step.

    Behaviour under test: the floor on the ratio.
    Bug this catches: `objective_scale = 0.0` (a flat or unevaluated objective)
    giving `h = 0`, and every gradient component then dividing by zero.
    """
    assert fd_step(0.0) > 0.0
    assert fd_step(0.0, 0.0) > 0.0
    assert fd_step(-1e6, 1e3) == pytest.approx(fd_step(1e6, 1e3))


# --------------------------------------------------------------------------
# fd_gradient
# --------------------------------------------------------------------------


def test_fd_gradient_matches_an_analytic_gradient():
    """Central differences recover a known gradient.

    Behaviour under test: the central-difference formula.
    Bug this catches: a forward difference (error O(h), ~1e-6 here, not 1e-9),
    or dividing by `h` instead of `2h`, which halves every component.
    Expected value differentiated on paper in `_analytic_grad`.
    """
    got = fd_gradient(_analytic, U0)
    np.testing.assert_allclose(got, _analytic_grad(U0), rtol=1e-9)


def test_fd_gradient_takes_its_steps_in_unconstrained_coordinates():
    """The gradient is `dl/du`, which is `dl/dtheta * dtheta/du`.

    Behaviour under test: the coordinates the step is taken in -- the
    acceptance criterion "one relative step serves every family".
    Bug this catches: perturbing natural parameters instead. The two differ by
    exactly the bijector Jacobian, which at `theta = [1, 5]` here is
    `dforward = [1, 5]` -- a factor of five on the second component, silently
    wrong and perfectly smooth. Verified independently: the unconstrained
    Romberg gradient equals the natural-coordinate Romberg gradient times
    `obj.dforward(u)` to 5.3e-13 relative.
    """
    obj, fn_u, (y, mask, t) = _filter_objective(64)
    theta0 = obj.to_natural(U0[None, :])[0]

    def fn_theta(theta):
        return float(
            obj.loglik(obj.hydrate(np.asarray(theta)[None, :]), y, mask, t, None)[0]
        )

    grad_u = richardson_gradient(fn_u, U0)
    grad_theta = richardson_gradient(fn_theta, theta0)
    jacobian = obj.dforward(U0[None, :])[0]

    assert jacobian[1] == pytest.approx(5.0)  # the factor that would be missed
    np.testing.assert_allclose(grad_u, grad_theta * jacobian, rtol=1e-9)


def test_a_nonfinite_objective_gives_a_nonfinite_gradient():
    """A failed evaluation propagates, rather than becoming a number.

    Behaviour under test: NaN propagation.
    Bug this catches: any `nan_to_num`-style cleanup. A gradient of 0.0 reads
    to the optimizer as a stationary point, so a series whose likelihood
    failed would be reported converged at its starting value.
    """
    got = fd_gradient(lambda u: float("nan"), U0)
    assert np.all(np.isnan(got))


def test_fd_gradient_refuses_a_point_that_is_not_a_vector():
    """`u` must be one-dimensional.

    Behaviour under test: the shape guard.
    Bug this catches: passing `u[None, :]` -- the shape every objective in this
    package actually wants -- which would iterate over one row and return a
    single perturbed direction instead of `p` of them.
    """
    with pytest.raises(ValueError, match="one-dimensional"):
        fd_gradient(_analytic, U0[None, :])


# --------------------------------------------------------------------------
# The oracle
# --------------------------------------------------------------------------


def test_richardson_must_start_above_the_cancellation_floor():
    """Extrapolating from the optimal FD step is no better than not doing it.

    Behaviour under test: `RICHARDSON_H0` sits in the truncation-dominated
    region, not at the V-curve minimum.
    Bug this catches: `h0 = fd_step(scale)`, which is what the plan's fence
    used. Richardson extrapolates the *truncation* series; at the optimum
    truncation is no longer dominant, so it extrapolates rounding noise.
    Measured on `_analytic`, relative error against the paper gradient:

        h0 = 1e-2   (4 levels)   5.80e-14
        h0 = 6.06e-6 (4 levels)  5.08e-11
        plain central at 6.06e-6 4.43e-11

    i.e. starting at the FD optimum is *worse* than the plain difference it
    was supposed to improve, and 875x worse than starting high.
    """
    truth = _analytic_grad(U0)
    high = richardson_gradient(_analytic, U0, h0=RICHARDSON_H0)
    low = richardson_gradient(_analytic, U0, h0=fd_step(1.0))
    plain = fd_gradient(_analytic, U0)

    rel = lambda g: float(np.max(np.abs(g - truth) / np.abs(truth)))  # noqa: E731
    assert rel(high) < 1e-12
    assert rel(low) > rel(plain)
    assert rel(high) < rel(low) / 100.0


def test_richardson_is_a_stronger_oracle_than_the_gradient_it_checks():
    """The oracle must out-resolve the thing under test, or it proves nothing.

    Behaviour under test: the accuracy gap between `richardson_gradient` and
    `fd_gradient`.
    Bug this catches: an oracle no better than its subject, which would make
    every downstream agreement test vacuous. Measured: 5.80e-14 against
    4.43e-11, a factor of ~760.
    """
    truth = _analytic_grad(U0)
    oracle = richardson_gradient(_analytic, U0)
    subject = fd_gradient(_analytic, U0)
    rel_oracle = float(np.max(np.abs(oracle - truth) / np.abs(truth)))
    rel_subject = float(np.max(np.abs(subject - truth) / np.abs(truth)))
    assert rel_oracle < 1e-12
    assert rel_oracle < rel_subject / 100.0


def test_richardson_refuses_a_tableau_with_no_rows():
    """`levels` below one is refused rather than indexed into.

    Behaviour under test: the `levels` guard.
    Bug this catches: `levels=0` building an empty tableau and failing with
    `IndexError: list index out of range` from inside the extrapolation loop,
    several frames from the caller that chose the value.
    """
    with pytest.raises(ValueError, match="levels"):
        richardson_gradient(_analytic, U0, levels=0)


@pytest.mark.slow
@pytest.mark.parametrize("n", [100, 630, 5000])
def test_the_step_rule_holds_against_the_oracle_at_three_values_of_n(n):
    """Exit criterion 9: the step rule validated against the oracle at three N.

    Behaviour under test: `fd_gradient`'s accuracy on the REAL filter as
    `|loglik|` grows -- 3.2e3 at N=100, 2.4e4 at N=630, 2.2e5 at N=5000.
    Bug this catches: a step rule that folds `|l|` in without dividing by
    `|l''|`. Measured relative error against the Romberg oracle:

        N        this rule    (eps |l|)^(1/3)
        100      4.28e-11         1.19e-08
        630      1.00e-10         4.51e-08
        5000     1.76e-10         1.98e-07

    The 1e-8 gate below passes for the first column at every N and fails for
    the second at every N. A quadratic test function cannot make this
    distinction at all: its third derivative is zero, so every step is exact.

    **`scale` is passed explicitly, as a real caller would.** Leaving it at the
    default makes this test blind to the very thing it is for: with `scale=1.0`
    the numerator is 1 and the denominator is irrelevant, so deleting the
    denominator changes no number and the test passes against the defect.
    Verified by mutation -- the three-N test passed with the denominator
    removed until `scale` was threaded through.
    """
    _, fn, _ = _filter_objective(n)
    magnitude = abs(fn(U0))
    oracle = richardson_gradient(fn, U0)

    def rel_error(gradient):
        return float(
            np.max(np.abs(gradient - oracle) / np.maximum(np.abs(oracle), 1e-30))
        )

    assert rel_error(fd_gradient(fn, U0, scale=magnitude)) < 1e-8
    # The rule without its denominator, stated as an executable measurement
    # rather than only as a docstring claim.
    naive = fd_gradient(fn, U0, step=(EPS * magnitude) ** (1.0 / 3.0))
    assert rel_error(naive) > 1e-8


# --------------------------------------------------------------------------
# Complex-step: the verdict
# --------------------------------------------------------------------------


def test_complex_step_reproduces_the_analytic_gradient_on_an_analytic_function():
    """The mechanism itself is correct.

    Behaviour under test: `complex_step_gradient` on a path that really is
    complex-analytic.
    Bug this catches: dividing by the wrong step, or taking the real part
    instead of the imaginary one. This test establishes that a zero result
    from the filter is the filter's fault and not the routine's -- without it
    the verdict below would be unattributable.
    """
    got = complex_step_gradient(_analytic, U0)
    np.testing.assert_allclose(got, _analytic_grad(U0), rtol=1e-13)


def test_complex_step_loses_the_imaginary_part_at_the_first_transform():
    """The diagnosis: an explicit float64 cast, not a non-analytic operation.

    Behaviour under test: where analyticity is actually lost.
    Bug this catches: recording the verdict as "something non-analytic is in
    the filter" -- `abs`, `min/max`, a comparison branch -- and hunting for it.
    It is none of those. `ConcentratedObjective._map` casts with
    `np.asarray(values, dtype=np.float64)` before any arithmetic happens, so
    the perturbation is gone at `to_natural`, before the filter is even
    reached. Every bijector in `transforms.py` and the engine's own entry casts
    repeat it independently.
    """
    obj, _, _ = _filter_objective(64)
    perturbed = U0.astype(np.complex128)
    perturbed[0] += 1j * 1e-20
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        natural = obj.to_natural(perturbed[None, :])
    assert natural.dtype == np.float64
    assert np.max(np.abs(np.imag(natural))) == 0.0
    assert any(w.category is np.exceptions.ComplexWarning for w in caught)


def test_complex_step_is_not_viable_through_the_filter():
    """The recorded verdict, pinned as an assertion: the gradient is zero.

    Behaviour under test: complex-step through the real matern32 objective.
    Bug this catches: two things. First, "fixing" the plan's fence by loosening
    its `rel < 1e-4` assertion -- the measured disagreement is 1.000e+00,
    because the gradient comes back exactly `[0, 0]`, which is a total failure
    and not a tolerance question. Second, and the reason this is an equality
    rather than an inequality: if someone later makes the cast chain
    dtype-following, complex-step starts working and THIS TEST FAILS, forcing
    the verdict note to be rewritten rather than silently going stale.
    """
    _, fn, _ = _filter_objective(64)
    oracle = richardson_gradient(fn, U0)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", np.exceptions.ComplexWarning)
        got = complex_step_gradient(fn, U0)

    assert np.all(got == 0.0)
    assert np.all(np.abs(oracle) > 1.0)  # the true gradient is nowhere near zero
    rel = np.abs(got - oracle) / np.abs(oracle)
    assert float(np.max(rel)) == pytest.approx(1.0)


def test_the_complex_step_verdict_note_exists_and_records_its_numbers():
    """Exit criterion 8: the verdict is recorded WITH NUMBERS.

    Behaviour under test: the note is a deliverable, not a formality.
    Bug this catches: shipping the code with the decision living only in a
    commit message. The note must name the measured agreement, the adopted
    fallback, and the located cause; a reader who cannot see the number cannot
    tell a measured verdict from an assumed one.
    """
    assert VERDICT_NOTE.exists(), f"{VERDICT_NOTE} is required by exit criterion 8"
    # encoding is explicit because the default is locale-dependent: on Windows it
    # is cp1252, which cannot decode this file (it died on byte 0x81 in CI).
    text = VERDICT_NOTE.read_text(encoding="utf-8")
    assert "1.000e+00" in text or "1.0" in text
    assert "Richardson" in text
    assert "_map" in text or "float64" in text
    assert "not viable" in text.lower()
