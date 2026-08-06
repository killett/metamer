from dataclasses import replace

import numpy as np
import pytest
from scipy.linalg import expm

from metamer.core.families.matern12 import Matern12
from metamer.core.families.matern32 import Matern32, _series_coefficients
from metamer.core.families.white import White
from metamer.core.registry import kernel_registry
from metamer.core.statespace import (
    EIGEN_CONDITION_LIMIT,
    DefectiveMatrixError,
    StateSpace,
    eigen_transition,
    safe_transition,
)
from metamer.core.terms import ProcessSpec, TermSpec, free_param_index
from tests.oracles import (
    expm_transition,
    lyapunov_stationary_cov,
    matern32_process_noise_exact,
    process_noise_from_stationary,
)

SQRT3 = np.sqrt(3.0)


def _term(kind: str, *, fixed: tuple[str, ...] = (), **defaults: float) -> TermSpec:
    """Build a TermSpec from a registered family, overriding defaults."""
    family = kernel_registry[kind]()
    specs = {
        name: replace(
            spec, default=defaults.get(name, spec.default), fixed=name in fixed
        )
        for name, spec in family.param_specs().items()
    }
    return TermSpec(
        kind=kind, params=specs, ordering_param=getattr(family, "ordering_param", None)
    )


def _drift(rho: float) -> np.ndarray:
    """Matern nu=3/2 drift A, hand-typed from the SDE in the class docstring."""
    lam = SQRT3 / rho
    return np.array([[0.0, 1.0], [-(lam**2), -2.0 * lam]])


def _diffusion(sigma: float, rho: float) -> np.ndarray:
    """Matern nu=3/2 diffusion L, hand-typed from the SDE."""
    lam = SQRT3 / rho
    return np.array([[0.0], [2.0 * sigma * lam**1.5]])


# --------------------------------------------------------------------------
# Matern 3/2: the analytic triple
# --------------------------------------------------------------------------


@pytest.mark.parametrize("dt", [0.2, 1.0, 5.0])
@pytest.mark.parametrize("rho", [1.0, 12.0])
def test_matern32_transition_matches_expm(dt, rho):
    """Analytic Jordan-form F equals expm(A dt) for the defective drift.

    Bug this catches: someone 'simplifying' Matern 3/2 into the general
    root-based CARMA path. Its root is repeated, so an eigendecomposition is
    defective and silently drops the t*exp(-lambda t) term.

    Expected value determined independently: `scipy.linalg.expm` uses scaling
    and squaring, which never forms an eigenvector basis and so is unaffected
    by the defect that this family exists to handle.
    """
    theta = np.array([[1.0, rho]])
    np.testing.assert_allclose(
        Matern32().transition(theta, dt)[0],
        expm_transition(_drift(rho), dt),
        rtol=1e-11,
        atol=1e-13,
    )


def test_matern32_acvf_matches_textbook_closed_form():
    """ACVF is sigma^2 (1 + lambda|tau|) exp(-lambda|tau|), lambda = sqrt(3)/rho.

    Expected value determined independently: standard Matern nu=3/2 kernel
    (Rasmussen & Williams eq. 4.17), written out by hand.

    Bug this catches: dropping the (1 + lambda|tau|) polynomial factor, which
    turns the kernel into a Matern 1/2 with a mis-scaled timescale -- still a
    valid kernel, still converging, but the wrong smoothness class.
    """
    sigma, rho = 2.0, 3.0
    lam = SQRT3 / rho
    lags = np.array([0.0, 0.5, 4.0])
    expected = sigma**2 * (1.0 + lam * lags) * np.exp(-lam * lags)
    np.testing.assert_allclose(
        Matern32().acvf(np.array([[sigma, rho]]), lags)[0], expected, rtol=1e-12
    )


@pytest.mark.parametrize(("sigma", "rho"), [(1.0, 1.0), (2.0, 3.0), (0.5, 12.0)])
def test_matern32_stationary_cov_matches_lyapunov(sigma, rho):
    """P_inf solves A P + P A' + L L' = 0 for the family's own A and L.

    Behaviour: `families/base.py` requires each family to state its A and L,
    and P_inf is the quantity that mapping most directly determines. Matern 3/2
    had no such test at all; only F was checked.

    Expected value determined independently: `scipy.linalg.solve_continuous_lyapunov`
    on the hand-typed A and L. Also asserted by hand: P_inf[0, 0] is the
    marginal variance sigma^2, i.e. ACF(0), which is what makes `sigma` mean
    "marginal standard deviation" in this parameterization.

    SHARED ASSUMPTION, STATED DELIBERATELY: `_drift` and `_diffusion` are typed
    from the same SDE-to-matrix mapping that `Matern32` encodes,

        dx = A x dt + L dW,  A = [[0, 1], [-lam^2, -2 lam]],  L = [0, 2 sigma lam^{3/2}]',

    so a conceptual error in the mapping would appear on both sides and cancel.
    That mapping rests on an independent re-derivation recorded in the class
    docstring, not on this test.

    Bug this catches: P_inf = diag(sigma^2, sigma^2) -- dropping the lambda^2 on
    the velocity component. The position block stays right, so the ACVF test and
    the F-vs-expm test both still pass, but the filter's prior on the derivative
    is wrong by a factor 3/rho^2 and every likelihood shifts.
    """
    p_inf = Matern32().stationary_cov(np.array([[sigma, rho]]))[0]
    np.testing.assert_allclose(
        p_inf, lyapunov_stationary_cov(_drift(rho), _diffusion(sigma, rho)), atol=1e-14
    )
    assert p_inf[0, 0] == pytest.approx(sigma**2, rel=1e-15)
    assert p_inf[0, 1] == 0.0 and p_inf[1, 0] == 0.0


@pytest.mark.parametrize("dt", [0.25, 1.0, 4.0])
def test_matern32_process_noise_matches_lyapunov_route(dt):
    """Q equals P_inf - F P_inf F' built from expm and a Lyapunov solve.

    Behaviour: this pins the *algebra* of Q at ordinary step sizes, where the
    literal difference form is numerically sound (u = 2 lambda dt is order 1, so
    nothing cancels). It is the companion to the tiny-step test below, which
    pins the *evaluation* where the difference form collapses.

    Expected value determined independently: F from `scipy.linalg.expm` and
    P_inf from `solve_continuous_lyapunov`, neither of which knows the closed
    forms this family ships.

    Bug this catches: a wrong series coefficient or a mis-derived closed form
    for Q -- e.g. writing Q_11 with (1 - u + u^2/2) instead of (1 + u + u^2/2),
    which swaps the position and velocity expressions. At dt = 1, rho = 5 that
    reports Q_11 = 0.20 where the truth is 0.030.
    """
    sigma, rho = 2.0, 5.0
    p_inf = lyapunov_stationary_cov(_drift(rho), _diffusion(sigma, rho))
    f = expm_transition(_drift(rho), dt)
    np.testing.assert_allclose(
        Matern32().process_noise(np.array([[sigma, rho]]), dt)[0],
        process_noise_from_stationary(p_inf, f),
        rtol=1e-11,
        atol=1e-14,
    )


@pytest.mark.parametrize("rho", [0.1, 1.0, 1000.0])
@pytest.mark.parametrize(
    "dt",
    [
        1.0e-8,
        1.0e-6,
        1.0e-5,
        1.0e-4,
        1.0e-2,
        0.1,
        0.28867513459481287,  # u = 0.9999999999999999 at rho=1: series, just below
        0.2947,  # u = 1.0208707459810962 at rho=1: direct, just above
        0.5,
        2.0,
        20.0,
    ],
)
def test_matern32_process_noise_is_accurate_for_tiny_steps(rho, dt):
    """Every entry of Q keeps full relative precision as dt -> 0.

    Behaviour: Q is a variance the Kalman filter divides by, so relative
    accuracy is the requirement, not absolute. Writing u = 2 lambda dt,

        Q_11 = sigma^2 [1 - e^-u (1 + u + u^2/2)] = sigma^2 [u^3/6 - u^4/8 + ...]

    is CUBIC in u while the quantities subtracted to reach it are O(1), so the
    literal difference loses about three times the digits the nu=1/2 case lost.
    Q_22 ~ 4 sigma^2 lambda^3 dt is the same linear cancellation nu=1/2 fixed.
    Q_12 = 2 sigma^2 lambda^3 dt^2 e^-u is safe -- P_inf[0, 1] is zero, so
    nothing is subtracted from it -- and is asserted here so that a "fix" which
    quietly zeroes the off-diagonal cannot pass.

    The dt grid straddles the implementation's crossover from BOTH sides.
    2 lambda dt = 1 at dt = rho / (2 sqrt 3): at rho = 1, dt = 0.28867513459481287
    gives u = 0.9999999999999999, which is the SERIES branch, so that value alone
    tests the join only from below. dt = 0.2947 gives u = 1.0208707459810962,
    landing on the direct branch just above the switch -- which is where the
    piecewise scheme's global worst error lives (3.1e-15, measured at u = 1.021).

    Expected value determined independently of the implementation, by
    `matern32_process_noise_exact`: the literal difference P_inf - F P_inf F'
    evaluated in 60-digit Decimal arithmetic, where the cancellation costs at
    most 15 of 60 digits and the float64 round-trip is therefore exact. It does
    NOT use the series, so a wrong series coefficient fails here.

    Bug this catches, and which the plain difference form has (measured at
    sigma = rho = 1): 4.0e-5 relative error in Q_11 at dt = 1e-4, 3.9e-2 at
    dt = 1e-5, exactly 0.0 at dt = 3e-6 and -2.2e-16 at dt = 1e-6 -- a negative
    variance. `expm1` alone does not fix it: -expm1(-u) - e^-u (u + u^2/2)
    still cancels two O(u) terms against an O(u^3) answer, and measures 4.7e-2
    relative error at u = 1e-7.

    WHY THE atol IS CONFINED TO THE OFF-DIAGONAL. At rho = 0.1, dt = 20 the
    exponent is u = 692.82, which float64 can represent only to 1.17e-13
    ABSOLUTE. That error passes into exp(-u) one-for-one as a relative error,
    measured at 1.17e-13, plus 1.5e-14 from `np.exp` itself -- so Q_12 there
    disagrees with the exact value by 1.3e-13 relative no matter how Q is
    computed. It is the conditioning of exp at a large argument, not a property
    of this family, and the entry concerned is 2.2e-294 against a diagonal of
    1.2e+03.

    An earlier version applied `atol = 1e-13 * max|Q|` to the WHOLE matrix, and
    that silently destroyed this test. The maximum is set by Q_22, which exceeds
    Q_11 by a factor of 3/dt^2, so at dt = 1e-8 the tolerance was 3.0e3 times
    Q_11 itself -- for every rho tested. Replacing Q_11 with exactly 0.0 still
    passed. The series branch went untested at precisely the step where it is
    the only thing standing between the filter and a negative variance. So the
    diagonal is now checked with rtol ONLY, and the atol applies to the
    off-diagonal alone, where the exp conditioning actually lives. Where Q_12 is
    significant -- at dt = 1e-8, rho = 1 it is 4.2e-15 against an atol of
    8.3e-20 -- its relative assertion still binds, so zeroing the off-diagonal
    still fails.
    """
    sigma = 2.0
    q = Matern32().process_noise(np.array([[sigma, rho]]), dt)
    assert q.shape == (1, 2, 2)
    exact = matern32_process_noise_exact(sigma, rho, dt)

    # Diagonal: relative accuracy only. These are the cancelling entries and the
    # whole reason the series branch exists; no absolute floor may excuse them.
    np.testing.assert_allclose(
        [q[0, 0, 0], q[0, 1, 1]], [exact[0, 0], exact[1, 1]], rtol=1e-13
    )
    # Off-diagonal: rtol, floored by the matrix scale for the large-u regime
    # where exp's argument conditioning dominates. Q is exactly symmetric by
    # construction, so that is asserted rather than checked twice.
    assert q[0, 0, 1] == q[0, 1, 0]
    np.testing.assert_allclose(
        q[0, 0, 1], exact[0, 1], rtol=1e-13, atol=1e-13 * np.abs(exact).max()
    )


@pytest.mark.parametrize(
    "dt", [1.0e-9, 1.0e-6, 1.0e-5, 1.0e-4, 1.0e-3, 0.1, 1.0, 10.0, 1000.0]
)
def test_matern32_process_noise_is_positive_semidefinite(dt):
    """Q has no negative eigenvalue at any step size.

    Behaviour: this is the downstream failure the cancellation actually causes.
    The Kalman filter Choleskys Q (or a covariance built from it); a Q whose
    smallest eigenvalue is -2.3e-16 is not a rounding detail, it raises.

    Expected value determined independently: Q is by construction the covariance
    of the integrated process noise over [0, dt], so it is positive
    semi-definite for every dt >= 0 as a matter of mathematics, whatever the
    parameters. The assertion is therefore on the sign, not on a magnitude.

    Bug this catches: `Q = P_inf - F P_inf F'` in float64. At sigma = rho = 1 it
    gives a minimum eigenvalue of -1.4e-16 at dt = 3e-6 and -2.3e-16 at
    dt = 1e-6. Both are covered by the sweep.
    """
    theta = np.array([[1.0, 1.0], [2.0, 0.1], [0.5, 1000.0]])
    q = Matern32().process_noise(theta, dt)
    for row in range(theta.shape[0]):
        smallest = float(np.linalg.eigvalsh(q[row]).min())
        assert smallest >= 0.0, (row, dt, smallest, q[row])
        assert smallest > 0.0, "a strictly positive step must give a nonsingular Q"


@pytest.mark.parametrize("rho", [0.5, 3.0, 40.0])
@pytest.mark.parametrize("sigma", [0.25, 2.0])
def test_matern32_at_zero_lag_is_identity_and_exactly_noiseless(sigma, rho):
    """At dt = 0, F is exactly the identity and Q is exactly zero.

    Behaviour: repeated timestamps are ordinary in real records, and any floor
    on dt or jitter added to Q for Cholesky stability injects process noise the
    model does not contain.

    Expected values derived from the mathematics: exp(A * 0) = I for any A, and
    Q(0) = P_inf - I P_inf I' = 0. Exact equality is asserted because "small" is
    not good enough -- a 1e-12 floor is exactly the bug.

    Bug this catches: `dt = max(dt, tiny)` guards, or `Q + eps I` regularisation.
    """
    theta = np.array([[sigma, rho]])
    fam = Matern32()
    np.testing.assert_array_equal(fam.transition(theta, 0.0), np.eye(2)[None])
    np.testing.assert_array_equal(fam.process_noise(theta, 0.0), np.zeros((1, 2, 2)))


def test_matern32_acvf_agrees_with_the_state_space_triple():
    """acvf(tau) equals H F(tau) P_inf H' -- the two descriptions are joined.

    Behaviour: the family ships an analytic ACVF and a state-space triple, and
    different engines use different ones. Nothing else compares them.

    Expected value determined independently of both: the stationary
    cross-covariance identity Cov(y_t, y_{t+tau}) = H F(tau) P_inf H' holds for
    any linear-Gaussian state-space model, so it restates neither the Matern
    closed form nor the SDE mapping.

    Bug this catches: a sigma-versus-sigma^2 slip in P_inf, or an H of [0, 1]
    (observing velocity rather than position) -- each half stays
    self-consistent, so only the comparison fails.
    """
    theta = np.array([[1.5, 4.0], [0.5, 0.25], [3.0, 100.0]])
    fam = Matern32()
    lags = np.array([0.0, 0.3, 1.0, 7.5, 250.0])
    h = fam.observation(theta)
    pinf = fam.stationary_cov(theta)
    from_triple = np.stack(
        [
            np.einsum("bi,bij,bjk,bk->b", h, fam.transition(theta, tau), pinf, h)
            for tau in lags
        ],
        axis=1,
    )
    assert from_triple.shape == (3, lags.size)
    np.testing.assert_allclose(fam.acvf(theta, lags), from_triple, rtol=1e-12)


def test_matern32_batch_members_do_not_share_parameters():
    """Each batch member uses its own (sigma, rho), not member 0's.

    Expected values determined by hand from the closed forms at dt = 1:
    row 0 (sigma=1, rho=1)  -> lam = sqrt(3),      P_inf = diag(1, 3)
    row 1 (sigma=2, rho=3)  -> lam = sqrt(3)/3,    P_inf = diag(4, 4/3)
    row 2 (sigma=0.5, rho=6)-> lam = sqrt(3)/6,    P_inf = diag(0.25, 1/48)

    Bug this catches: indexing theta with `[0, 1]` instead of `[:, 1]`, which
    fits the whole batch with the first series' timescale and still converges.
    """
    theta = np.array([[1.0, 1.0], [2.0, 3.0], [0.5, 6.0]])
    pinf = Matern32().stationary_cov(theta)
    assert pinf.shape == (3, 2, 2)
    np.testing.assert_allclose(pinf[:, 0, 0], [1.0, 4.0, 0.25], rtol=1e-15)
    np.testing.assert_allclose(pinf[:, 1, 1], [3.0, 4.0 / 3.0, 1.0 / 48.0], rtol=1e-15)
    f = Matern32().transition(theta, 1.0)
    assert f.shape == (3, 2, 2)
    np.testing.assert_allclose(
        f[:, 0, 1],
        [np.exp(-SQRT3), np.exp(-SQRT3 / 3.0), np.exp(-SQRT3 / 6.0)],
        rtol=1e-15,
    )


def test_matern32_is_state_noise_not_measurement_noise():
    """Matern32 observes position with H = [1, 0] and adds nothing to R.

    Expected values determined independently: the modelled signal is the state's
    first component, so H = [1, 0]; sigma already enters through P_inf and Q, so
    adding it to R would count the same variance twice.

    Bug this catches: H = [1, 1], which observes position plus velocity -- a
    different process with a different spectrum, converging cleanly to a wrong
    fit.
    """
    theta = np.array([[2.0, 5.0], [0.5, 1.0]])
    fam = Matern32()
    assert fam.state_dim == 2
    np.testing.assert_array_equal(fam.observation(theta), np.array([[1.0, 0.0]] * 2))
    np.testing.assert_array_equal(fam.measurement_variance(theta), np.zeros(2))


# --------------------------------------------------------------------------
# Composite assembly
# --------------------------------------------------------------------------


def test_q_series_coefficients_match_the_hand_derivation():
    """The generated coefficients equal the fractions worked out by hand.

    Behaviour: the small-step branch of Q is a truncated Maclaurin series, and
    its coefficients are generated from a closed formula rather than typed out.
    That formula is the derivation, so it needs pinning against arithmetic done
    independently of it.

    Expected values determined by hand, by convolving exp(-u) with the quadratic
    and collecting terms (the working is in `_series_coefficients`' docstring):
        g1 = u^3/6 - u^4/8 + u^5/20 - u^6/72 + ...
        g2 = 2u - 2u^2 + 7u^3/6 - 11u^4/24 + ...
    The leading g1 coefficient 1/6 is also checkable a second way: g1(u) is
    (1/2) times the integral of t^2 e^-t from 0 to u, whose leading term is
    (1/2)(u^3/3) = u^3/6.

    Bug this catches: an off-by-one in the (n-1)(n-2) numerator -- for instance
    n(n-1), which is nonzero at n = 2 and so would make g1 start at u^2 rather
    than u^3, destroying exactly the cubic behaviour the branch exists for. It
    also pins that g1 has no u^1 or u^2 term at all, since those coefficients
    vanish identically rather than being dropped by hand.
    """
    np.testing.assert_allclose(
        _series_coefficients("g1", 6),
        [-1.0 / 72.0, 1.0 / 20.0, -1.0 / 8.0, 1.0 / 6.0],
        rtol=1e-15,
    )
    np.testing.assert_allclose(
        _series_coefficients("g2", 4),
        [-11.0 / 24.0, 7.0 / 6.0, -2.0, 2.0],
        rtol=1e-15,
    )
    assert _series_coefficients("g1", 3) == (1.0 / 6.0,)
    with pytest.raises(ValueError, match="unknown series"):
        _series_coefficients("g3", 5)


def test_canonical_term_order_places_white_last():
    """`white` sorts after both Materns, so theta's last column is white's sigma.

    Behaviour: `ProcessSpec` sorts by (kind, ordering default, canonical JSON),
    and "matern12" < "matern32" < "white" as strings. Every composite theta
    layout in this module depends on that, and a positional assumption that is
    only implied by other tests' expected values is one nobody can check.

    Expected value determined independently: by lexicographic comparison of the
    registry keys, which is what `sorted` applies to the first key element.

    Bug this catches: adding a family whose registry key perturbs the order, or
    changing `order_key`'s primary element -- either silently permutes theta.
    """
    spec = ProcessSpec((_term("white"), _term("matern32"), _term("matern12")))
    assert [t.kind for t in spec.terms] == ["matern12", "matern32", "white"]


def test_composite_state_dim_is_the_sum_of_its_terms():
    """white + matern12 + matern32 has d = 0 + 1 + 2 = 3.

    Expected value determined independently by adding the documented state
    dimensions. This is the d=3 spike configuration, and getting it wrong
    invalidates every memory figure that depends on d^2.

    Bug this catches: giving white a state dimension, which would report 4.
    """
    spec = ProcessSpec((_term("white"), _term("matern12"), _term("matern32")))
    ss = StateSpace.from_spec(spec)
    assert ss.state_dim == 3
    assert [(s.start, s.stop) for s in ss.slices] == [(0, 1), (1, 3), (3, 3)]


def test_composite_matrices_are_block_diagonal():
    """F, Q and P_inf place each term's block on the diagonal and zero elsewhere.

    Behaviour: additive kernels are independent processes, so the composite
    matrices must have exactly zero coupling. Only F was covered before; Q and
    P_inf are precisely the two quantities the cancellation work concerns.

    Expected values determined independently: the off-diagonal blocks are zero
    by the definition of an additive composition, and each diagonal block is the
    term's own matrix -- fetched from the family directly, so a block that was
    copied from the wrong term, or transposed into the wrong slot, fails.
    Exact equality (atol = 0.0) is asserted on the off-diagonals because
    "small" would accept a genuine coupling term that happened to be tiny.

    Bug this catches: assembling with a reshape instead of a block placement,
    which silently couples independent processes; or reusing one term's slice
    for both blocks, which the B=2 rows with distinct parameters also expose.
    """
    spec = ProcessSpec((_term("matern12", rho=2.0), _term("matern32", rho=9.0)))
    ss = StateSpace.from_spec(spec)
    theta = np.array([[1.0, 2.0, 1.0, 9.0], [0.5, 4.0, 2.0, 3.0]])
    dt = 1.0

    for composite, solo12, solo32 in (
        (
            ss.transition(theta, dt),
            Matern12().transition(theta[:, 0:2], dt),
            Matern32().transition(theta[:, 2:4], dt),
        ),
        (
            ss.process_noise(theta, dt),
            Matern12().process_noise(theta[:, 0:2], dt),
            Matern32().process_noise(theta[:, 2:4], dt),
        ),
        (
            ss.stationary_cov(theta),
            Matern12().stationary_cov(theta[:, 0:2]),
            Matern32().stationary_cov(theta[:, 2:4]),
        ),
    ):
        assert composite.shape == (2, 3, 3)
        np.testing.assert_array_equal(composite[:, 0, 1:], 0.0)
        np.testing.assert_array_equal(composite[:, 1:, 0], 0.0)
        np.testing.assert_array_equal(composite[:, 0:1, 0:1], solo12)
        np.testing.assert_array_equal(composite[:, 1:3, 1:3], solo32)


def test_composite_observation_concatenates_each_terms_row():
    """H is each term's observation row laid end to end, white contributing none.

    Expected value determined by hand: in canonical order (matern12, matern32,
    white) the rows are [1], [1, 0] and the empty row, so H = [1, 1, 0].

    Bug this catches: writing H as all-ones over the composite state, which
    would observe the Matern 3/2 velocity as well as its position -- a
    completely different process, and one that still fits.
    """
    spec = ProcessSpec(
        (_term("matern12"), _term("matern32"), _term("white", sigma=0.5))
    )
    ss = StateSpace.from_spec(spec)
    theta = np.array([[1.0, 2.0, 1.0, 9.0, 0.5], [2.0, 1.0, 3.0, 4.0, 0.25]])
    h = ss.observation(theta)
    assert h.shape == (2, 3)
    np.testing.assert_array_equal(h, np.array([[1.0, 1.0, 0.0]] * 2))


def test_measurement_variance_sums_over_terms():
    """R is the sum of every term's measurement-variance contribution.

    Expected value determined by hand: white sorts LAST (see
    `test_canonical_term_order_places_white_last`), so with
    theta = [matern12 sigma, matern12 rho, white sigma] = [1.0, 1.0, 0.5] the
    only contribution is white's, 0.5^2 = 0.25.

    Bug this catches: taking the first term's R, which drops white noise
    whenever it is not sorted first -- and white is never sorted first in any
    composite that contains a Matern.
    """
    spec = ProcessSpec((_term("white", sigma=0.5), _term("matern12")))
    ss = StateSpace.from_spec(spec)
    assert [t.kind for t in spec.terms] == ["matern12", "white"]
    theta = np.array([[1.0, 1.0, 0.5]])
    assert ss.measurement_variance(theta)[0] == pytest.approx(0.25)


def test_composite_acvf_sums_over_terms():
    """The composite ACVF is the sum of the terms' ACVFs.

    Expected values determined by hand from the closed forms at
    sigma_12 = 1, rho_12 = 2, sigma_32 = 1, rho_32 = 9, sigma_w = 0.5:
    at tau = 0, 1 + 1 + 0.25 = 2.25; at tau = 2 white contributes exactly zero,
    so it is exp(-1) + (1 + 2 lam) exp(-2 lam) with lam = sqrt(3)/9.

    Bug this catches: returning the first term's ACVF, or letting white's
    lag-zero nugget leak to nonzero lags.
    """
    spec = ProcessSpec(
        (_term("matern12", rho=2.0), _term("matern32", rho=9.0), _term("white"))
    )
    ss = StateSpace.from_spec(spec)
    theta = np.array([[1.0, 2.0, 1.0, 9.0, 0.5]])
    lam = SQRT3 / 9.0
    lags = np.array([0.0, 2.0])
    expected = [
        1.0 + 1.0 + 0.25,
        np.exp(-1.0) + (1.0 + 2.0 * lam) * np.exp(-2.0 * lam),
    ]
    np.testing.assert_allclose(ss.acvf(theta, lags)[0], expected, rtol=1e-13)


def test_state_space_slices_theta_over_fixed_parameters_too():
    """`StateSpace` expects the FULL per-term parameter vector, not the free one.

    Behaviour: `free_param_index` is the single source of truth for the vector
    the optimizer searches, and it SKIPS `fixed=True` parameters.
    `StateSpace.from_spec` deliberately slices over ALL of a term's parameters.
    Those are two different vectors, and the project's decision is that a
    free-only vector must be widened by `ConcentratedObjective.hydrate` before
    it reaches `StateSpace`. Without a test, that distinction is a comment.

    Expected values determined by hand: matern12 with rho frozen at 2.0 still
    occupies two columns, so the layout is
    [sigma_12, rho_12, sigma_32, rho_32] -- width 4 -- while
    `free_param_index` reports 3 entries. At dt = 2, block 0 of F is
    exp(-2/2) = exp(-1); if the free-only 3-vector were accepted, the Matern 3/2
    slice would be a single column.

    Bug this catches: "fixing" `from_spec` to use `n_free()` so it agrees with
    `free_param_index`. Every existing test would still pass, because none of
    them freezes a parameter; the failure would appear only once a user froze
    one, and then as a silent one-slot shift of every later coordinate.
    """
    spec = ProcessSpec(
        (_term("matern12", rho=2.0, fixed=("rho",)), _term("matern32", rho=9.0))
    )
    ss = StateSpace.from_spec(spec)

    assert len(free_param_index(spec)) == 3
    assert spec.n_theta() == 3
    assert [(s.start, s.stop) for s in ss.param_slices] == [(0, 2), (2, 4)]

    full = np.array([[1.0, 2.0, 1.0, 9.0]])
    np.testing.assert_allclose(
        ss.transition(full, 2.0)[0, 0, 0], np.exp(-1.0), rtol=1e-15
    )

    free_only = np.array([[1.0, 1.0, 9.0]])
    with pytest.raises(IndexError):
        ss.transition(free_only, 2.0)


def test_composite_process_noise_is_positive_semidefinite():
    """The assembled composite Q inherits each block's positive semi-definiteness.

    Behaviour: block-diagonal assembly means the composite spectrum is the union
    of the blocks' spectra, so a single non-PSD block poisons the whole filter.
    This is the composite-level statement of the cancellation guarantee.

    Expected value determined independently: a block-diagonal matrix's
    eigenvalues are exactly its blocks' eigenvalues, and each block is a
    covariance, so the minimum is non-negative for every dt >= 0.

    Bug this catches: a Matern 3/2 block computed by the plain difference form,
    which at dt = 1e-6 contributes an eigenvalue of about -2.3e-16.
    """
    spec = ProcessSpec((_term("matern12"), _term("matern32")))
    ss = StateSpace.from_spec(spec)
    theta = np.array([[1.0, 1.0, 1.0, 1.0]])
    for dt in (1.0e-6, 1.0e-5, 1.0e-4, 1.0e-2, 1.0):
        q = ss.process_noise(theta, dt)[0]
        assert float(np.linalg.eigvalsh(q).min()) >= 0.0, dt


# --------------------------------------------------------------------------
# unique_dt and per-step amortization
# --------------------------------------------------------------------------


def test_unique_dt_collapses_a_regular_grid():
    """A regular time axis has exactly one unique dt; an irregular one has n-1.

    Expected values determined by hand: `np.arange(0, 10, 1.0)` has 9 intervals
    all equal to 1.0; [0, 1, 3, 6] has 3 intervals, 1, 2 and 3, all distinct.

    Bug this catches: recomputing F and Q at every one of N timesteps, which
    throws away the N-fold amortization that is the dominant win.
    """
    regular = np.arange(0.0, 10.0, 1.0)
    irregular = np.array([0.0, 1.0, 3.0, 6.0])
    assert StateSpace.unique_dt(regular).size == 1
    assert StateSpace.unique_dt(irregular).size == 3
    np.testing.assert_allclose(StateSpace.unique_dt(irregular), [1.0, 2.0, 3.0])


@pytest.mark.parametrize(
    "grid",
    [
        np.linspace(0.0, 1.0, 11),
        np.arange(0.0, 1.0, 0.1),
        np.linspace(-3.0, 7.5, 211),
        np.arange(0.0, 10.0, 1.0),
    ],
)
def test_unique_dt_is_tolerant_of_binary_representation_noise(grid):
    """A grid that is regular in exact arithmetic collapses to one step.

    Behaviour: real time axes are built with `linspace` or `arange`, and neither
    produces bit-identical differences unless the step happens to be exact in
    binary. `np.unique(np.diff(t))` therefore does NOT collapse them.

    Expected values determined independently: each grid above is regular by
    construction, so the mathematically correct answer is one unique step, and
    `np.linspace(0, 1, 11)` has step 0.1 exactly in decimal.

    Bug this catches, and which `np.unique` alone has: `np.linspace(0, 1, 11)`
    yields FOUR distinct float64 differences, and `np.arange(0, 1, 0.1)` also
    four. The brief's original test passed only because `np.arange(0, 10, 1.0)`
    is exact in binary -- an accident of the fixture, so that grid is kept here
    as a control alongside the ones that expose the bug.
    """
    steps = StateSpace.unique_dt(grid)
    assert steps.size == 1, np.unique(np.diff(grid))
    np.testing.assert_allclose(steps[0], np.diff(grid).mean(), rtol=1e-9)


def test_unique_dt_keeps_genuinely_distinct_steps_apart():
    """Steps differing by more than the tolerance are not merged.

    Behaviour: the tolerance must be tight enough to preserve real structure.
    A relative tolerance of 1e-9 has to keep two steps that differ in the eighth
    significant digit apart, or an irregular record would be silently regularised.

    Expected values determined by hand: 1.0 and 1.0 + 1e-7 differ by 1e-7, which
    is a hundred times the 1e-9 tolerance, so they are two steps; 1.0 and
    1.0 + 1e-13 differ by a hundredth of it, so they are one.

    Bug this catches: a tolerance set so loose (say 1e-6 relative, or an
    absolute one) that distinct sampling rates collapse, which would apply the
    wrong F and Q to a whole stretch of a series.
    """
    distinct = np.array([0.0, 1.0, 2.0 + 1.0e-7, 3.0 + 2.0e-7])
    assert StateSpace.unique_dt(distinct).size == 2
    merged = np.array([0.0, 1.0, 2.0 + 1.0e-13, 3.0 + 2.0e-13])
    assert StateSpace.unique_dt(merged).size == 1
    assert StateSpace.unique_dt(np.array([5.0])).size == 0


def test_unique_dt_tolerance_is_local_not_scaled_by_the_longest_gap():
    """One long gap must not regularise the rest of the axis.

    Behaviour: the tolerance has to be relative to each step being compared, not
    to the largest step in the record. A global scale means a single long gap
    inflates the tolerance for every other pair, and the ratio needed is
    ordinary -- sub-second sampling inside a multi-year record puts gap/step
    above 1e9 routinely.

    Expected values determined by hand: the steps of `[0, 1, 2, 3.003, 4e9]` are
    1.0, 1.0, 1.003 and about 4e9. Steps 1.0 and 1.003 differ by 0.003, three
    million times the 1e-9 relative tolerance at their own scale, so they are
    distinct, giving 3 steps in all. The invariant asserted alongside it is that
    the SAME axis with the gap removed gives exactly one fewer -- 2, being 1.0
    and 1.003 -- because deleting a far-away gap cannot change whether two short
    steps are the same length. That is what pins the tolerance as local: it is a
    statement about the other pairs, not about the gap.

    Bug this catches, and which `tol = rtol * max|step|` has: the global
    tolerance here is 1e-9 * 4e9 = 4.0 ABSOLUTE, so 1.0 and 1.003 merge and the
    gapped axis reports 2 steps while the ungapped one still reports 2 -- the
    counts stop differing by one. The filter would then advance a 1.003-long
    interval with the F and Q built for a 1.0-long one: a wrong transition
    applied to a whole stretch of the series, silently, with no shape or count
    to notice.
    """
    gapped = np.array([0.0, 1.0, 2.0, 3.003, 4.0e9])
    steps = StateSpace.unique_dt(gapped)
    assert steps.size == 3, steps
    np.testing.assert_allclose(steps[:2], [1.0, 1.003], rtol=1e-12)

    ungapped = np.array([0.0, 1.0, 2.0, 3.003])
    assert StateSpace.unique_dt(ungapped).size == 2
    assert steps.size == StateSpace.unique_dt(ungapped).size + 1


def test_unique_dt_handles_duplicate_and_single_timestamps():
    """An axis of repeated timestamps has one step, exactly zero; one sample has none.

    Behaviour: duplicate timestamps are ordinary in real records -- two casts
    logged in the same minute, a duplicated row after a merge -- and the whole
    dt = 0 contract (F exactly I, Q exactly zero) exists to serve them. An axis
    that is ENTIRELY duplicates drives the relative tolerance itself to zero,
    because it is scaled by the largest step, and that is the one input for
    which a relative tolerance is meaningless.

    Expected values determined by hand: `[3.0, 3.0, 3.0]` has two intervals both
    exactly 0.0, so one distinct step whose value is exactly 0.0; a one-sample
    axis has no intervals at all, so no steps and empty stacks.

    Bug this catches: dividing by the largest step (0/0 -> nan, and every step
    then compares unequal, so a duplicate-heavy axis reports n-1 distinct steps
    and the amortization vanishes exactly where it is cheapest); or an
    `np.max` over an empty array, which raises on a single-sample series.
    """
    duplicates = StateSpace.unique_dt(np.array([3.0, 3.0, 3.0]))
    assert duplicates.size == 1
    assert duplicates[0] == 0.0

    spec = ProcessSpec((_term("matern12"), _term("matern32")))
    ss = StateSpace.from_spec(spec)
    theta = np.array([[1.0, 2.0, 1.0, 9.0]])

    single = ss._step_matrices(theta, np.array([4.0]))
    assert single.steps.size == 0
    assert single.index.shape == (0,)
    assert single.transition.shape == (0, 1, 3, 3)
    assert single.process_noise.shape == (0, 1, 3, 3)

    repeated = ss._step_matrices(theta, np.array([3.0, 3.0, 3.0]))
    assert repeated.steps.size == 1
    np.testing.assert_array_equal(repeated.index, [0, 0])
    np.testing.assert_array_equal(repeated.transition[0], np.eye(3)[None])
    np.testing.assert_array_equal(repeated.process_noise[0], np.zeros((1, 3, 3)))


def test_step_matrices_evaluates_each_unique_step_once():
    """F and Q are built once per unique step and indexed back to the intervals.

    Behaviour: this is the memoization the acceptance criterion names. On a
    regular grid of n points there are n-1 intervals but ONE distinct step, so
    exactly one F and one Q are built; `index` maps every interval onto it.

    Expected values determined independently: the number of stacked matrices is
    asserted to equal the number of unique steps (1 for a 501-point regular
    grid, 3 for the irregular fixture), and each stacked matrix is compared
    against the family's own `transition`/`process_noise` at that interval's
    own step -- so a cache that returned the wrong entry for some interval
    fails even though the count is right.

    Bug this catches: returning n-1 matrices on a regular grid (no amortization
    at all -- 500x the work and 500x the memory here), or an off-by-one in the
    interval-to-step index, which would advance the filter with the wrong step.
    """
    spec = ProcessSpec((_term("matern12"), _term("matern32")))
    ss = StateSpace.from_spec(spec)
    theta = np.array([[1.0, 2.0, 1.0, 9.0], [0.5, 4.0, 2.0, 3.0]])

    regular = np.linspace(0.0, 5.0, 501)
    steps = ss._step_matrices(theta, regular)
    assert steps.steps.size == 1
    assert steps.transition.shape == (1, 2, 3, 3)
    assert steps.process_noise.shape == (1, 2, 3, 3)
    assert steps.index.shape == (500,)
    np.testing.assert_array_equal(steps.index, 0)

    irregular = np.array([0.0, 1.0, 3.0, 6.0, 7.0])
    steps = ss._step_matrices(theta, irregular)
    assert steps.steps.size == 3
    assert steps.transition.shape == (3, 2, 3, 3)
    np.testing.assert_array_equal(steps.index, [0, 1, 2, 0])
    for interval, dt in enumerate(np.diff(irregular)):
        np.testing.assert_allclose(
            steps.transition[steps.index[interval]],
            ss.transition(theta, float(dt)),
            rtol=1e-14,
        )
        np.testing.assert_allclose(
            steps.process_noise[steps.index[interval]],
            ss.process_noise(theta, float(dt)),
            rtol=1e-14,
        )


# --------------------------------------------------------------------------
# The defective-root guard
# --------------------------------------------------------------------------


def test_eigen_transition_refuses_a_near_defective_matrix():
    """The guard fires before the eigen route returns a quietly wrong answer.

    Bug this catches: silent precision loss as two roots coalesce. There is no
    exception from numpy here -- the eigenvector matrix simply becomes
    ill-conditioned and the result degrades continuously.

    Expected value determined independently: the drift below is an exact Jordan
    block perturbed by 1e-12, whose eigenvector matrix has condition number
    about 2/eps = 2e12 by hand (the two eigenvectors differ by O(eps)), which is
    four decades above the 1e8 limit.
    """
    eps = 1e-12
    drift = np.array([[-1.0, 1.0], [0.0, -1.0 - eps]])
    with pytest.raises(DefectiveMatrixError):
        eigen_transition(drift, 1.0, cond_threshold=1e8)


@pytest.mark.parametrize("rho", [1.0, 10.0])
def test_eigen_transition_refuses_the_defective_matern32_drift(rho):
    """The CALIBRATION CASE: the exactly-defective Matern 3/2 drift is refused.

    Behaviour: `EIGEN_CONDITION_LIMIT` has no independently correct value, so it
    must be specified by the case it has to catch rather than have that case
    loosened to fit it. The Matern 3/2 drift is exactly defective by
    construction -- a repeated root at -lambda with a one-dimensional
    eigenspace -- so it is the case the guard must never miss.

    Measured `cond(V)` from `np.linalg.eig` on this machine (numpy 2.x, OpenBLAS
    LAPACK): 2.029181e+08 at rho = 1 and 4.576471e+08 at rho = 10, against a
    limit of 1e8. That is a factor of 2.0 and 4.6 of margin -- under one decade
    -- and it is LAPACK-dependent, which is exactly why this assertion exists
    rather than a comment. rho = 0.1 gives 1.8e+16 and rho = 100 gives inf, so
    the tight cases are the ones pinned here.

    Bug this catches: raising the limit "to reduce false positives" past the
    2.03e8 measured at rho = 1, which would send the single most defective
    matrix in the library down the eigen route and return a silently wrong F.
    """
    lam = SQRT3 / rho
    drift = np.array([[0.0, 1.0], [-(lam**2), -2.0 * lam]])
    _, vectors = np.linalg.eig(drift)
    cond = float(np.linalg.cond(vectors))
    assert cond > EIGEN_CONDITION_LIMIT, (
        f"cond(V) = {cond:.6e} no longer exceeds the {EIGEN_CONDITION_LIMIT:.1e} "
        "limit; the guard has stopped protecting its own calibration case"
    )
    with pytest.raises(DefectiveMatrixError, match="condition number"):
        eigen_transition(drift, 1.0)


@pytest.mark.parametrize(
    "drift",
    [
        np.array([[-1.0, 0.0], [0.0, -3.0]]),
        np.array([[-1.0, 0.5], [0.25, -4.0]]),
    ],
)
def test_eigen_transition_accepts_a_well_conditioned_drift(drift):
    """The guard does NOT fire on a comfortably diagonalizable drift.

    Behaviour: a guard that refuses everything is not a guard, it is a rename of
    the fallback. The acceptance criterion says frequent firing is a bug signal,
    so the negative control is as load-bearing as the positive one.

    Expected values determined independently, by mathematics rather than by
    running `np.linalg.cond` and writing down what it said. `np.linalg.eig`
    returns unit-norm eigenvectors, so V has unit columns and V^H V = [[1, c],
    [c*, 1]] with c the Hermitian inner product of the two. Its eigenvalues are
    1 +- |c|, so the singular values of V are sqrt(1 +- |c|) and

        cond_2(V) = sqrt((1 + |c|) / (1 - |c|)).

    That identity is asserted here. For `diag(-1, -3)` the eigenvectors are
    orthogonal, c = 0, and it gives exactly 1. For the generic matrix it gives
    1.084394792, agreeing with `np.linalg.cond` to nine decimals -- but the
    assertion is on the identity, so it characterises cond(V), not the fixture.

    The property that actually matters is asserted separately: both drifts sit
    at least six decades below the limit, which is what makes them a negative
    control rather than a coincidence. The returned F is checked against
    `scipy.linalg.expm`, which shares no code with the eigen route.

    Bug this catches: a threshold accidentally written as a lower bound, or
    `np.linalg.cond` called on the wrong matrix (the drift rather than its
    eigenvectors), which for `diag(-1, -3)` would report 3 rather than 1 -- and
    for a stiff but perfectly diagonalizable drift would report a huge number
    and fire on every well-behaved model.
    """
    _, vectors = np.linalg.eig(drift)
    np.testing.assert_allclose(np.linalg.norm(vectors, axis=0), 1.0, rtol=1e-15)
    # numpy 2's `eig` returns complex128 unconditionally, so the inner product
    # must be the Hermitian one -- which is also the form the identity needs.
    cosine = abs(np.vdot(vectors[:, 0], vectors[:, 1]))
    cond = float(np.linalg.cond(vectors))
    assert cond == pytest.approx(np.sqrt((1.0 + cosine) / (1.0 - cosine)), rel=1e-12)
    assert cond < EIGEN_CONDITION_LIMIT / 1e6

    np.testing.assert_allclose(
        eigen_transition(drift, 0.7), expm(drift * 0.7), rtol=1e-12, atol=1e-14
    )


def test_safe_transition_counts_the_fallback_and_matches_expm():
    """On a defective drift, `safe_transition` falls back, counts it, and is right.

    Behaviour: the fallback rate is a diagnostic -- frequent firing means the
    model is drifting into a non-identifiable region -- so the count has to be
    real, and the fallback's answer has to be usable, not merely produced.

    Expected values determined independently: the Matern 3/2 drift at rho = 1 is
    exactly defective, so the counter must reach 1; the well-conditioned drift
    must leave it absent. The result is compared to `scipy.linalg.expm` at
    rtol 1e-12, and separately to the family's own analytic Jordan form, which
    is derived by hand rather than computed -- so agreement is not circular.

    Bug this catches: a fallback that swallows the exception and returns the
    ill-conditioned eigen result anyway, or a counter incremented on every call
    (which would make the diagnostic useless by always screaming).
    """
    counter: dict[str, int] = {}
    lam = SQRT3
    defective = np.array([[0.0, 1.0], [-(lam**2), -2.0 * lam]])
    result = safe_transition(defective, 0.4, counter)
    assert counter == {"fallback": 1}
    np.testing.assert_allclose(result, expm(defective * 0.4), rtol=1e-12, atol=1e-14)
    np.testing.assert_allclose(
        result, Matern32().transition(np.array([[1.0, 1.0]]), 0.4)[0], rtol=1e-11
    )

    healthy = np.array([[-1.0, 0.5], [0.25, -4.0]])
    np.testing.assert_allclose(
        safe_transition(healthy, 0.4, counter), expm(healthy * 0.4), rtol=1e-12
    )
    assert counter == {"fallback": 1}


def test_safe_transition_forwards_the_condition_threshold():
    """`cond_threshold` reaches `eigen_transition` instead of being hard-coded.

    Behaviour: the brief's `safe_transition` called `eigen_transition(drift, dt)`
    with no threshold, so 1e8 was unconfigurable and the parameter on
    `eigen_transition` was unreachable from the only caller.

    Expected values determined independently: `diag(-1, -3)` has cond(V) = 1
    exactly, so a threshold of 0.5 must reject it and a threshold of 1e8 must
    accept it. The Matern 3/2 drift at rho = 1 has cond(V) = 2.03e8, so a
    threshold of 1e9 must accept it where the default 1e8 rejects it. Both
    directions are asserted, because a `safe_transition` that ignored the
    argument entirely would pass a one-directional test.

    Bug this catches: dropping the forwarding again, which leaves the guard
    permanently pinned to a constant whose only justification is one measured
    condition number with a factor-of-two margin.
    """
    counter: dict[str, int] = {}
    healthy = np.array([[-1.0, 0.0], [0.0, -3.0]])
    safe_transition(healthy, 1.0, counter, cond_threshold=0.5)
    assert counter == {"fallback": 1}
    safe_transition(healthy, 1.0, counter, cond_threshold=1e8)
    assert counter == {"fallback": 1}

    lam = SQRT3
    defective = np.array([[0.0, 1.0], [-(lam**2), -2.0 * lam]])
    safe_transition(defective, 1.0, counter, cond_threshold=1e9)
    assert counter == {"fallback": 1}
    safe_transition(defective, 1.0, counter)
    assert counter == {"fallback": 2}


def test_white_contributes_no_state_block_to_the_composite():
    """A d=0 term occupies an empty slice and never writes into the state matrices.

    Behaviour: white is the only zero-dimensional family, and `_assemble` skips
    it explicitly. If that skip were removed, `out[:, 3:3, 3:3] = zeros((B,0,0))`
    would happen to succeed, so the guard is not obviously load-bearing -- but
    the parameter slice would still be consumed, and that is what is pinned.

    Expected values determined by hand: white sorts last, so its block is the
    empty slice(3, 3) and its parameter slice is the last column; the state
    dimension stays 3.

    Bug this catches: giving white a state dimension, which shifts every later
    block and silently changes every d^2 memory figure.
    """
    spec = ProcessSpec(
        (_term("white", sigma=0.5), _term("matern12"), _term("matern32"))
    )
    ss = StateSpace.from_spec(spec)
    assert ss.state_dim == 3
    assert [(s.start, s.stop) for s in ss.slices] == [(0, 1), (1, 3), (3, 3)]
    assert [(s.start, s.stop) for s in ss.param_slices] == [(0, 2), (2, 4), (4, 5)]
    theta = np.array([[1.0, 1.0, 1.0, 1.0, 0.5]])
    assert ss.transition(theta, 1.0).shape == (1, 3, 3)
    assert White().state_dim == 0
