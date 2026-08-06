import numpy as np
import pytest

from metamer.core.families.base import Family
from metamer.core.families.matern12 import Matern12
from metamer.core.families.white import White
from metamer.core.transforms import Log
from tests.oracles import (
    expm_transition,
    lyapunov_stationary_cov,
    process_noise_from_stationary,
)


@pytest.mark.parametrize("family", [White(), Matern12()])
def test_every_builtin_family_satisfies_the_family_protocol(family):
    """Each shipped family provides the full `Family` surface at runtime.

    Behaviour: `Family` is the contract every engine will program against, so
    a family that is missing a member is a defect in the family, not in the
    engine that trips over it.

    Expected value determined independently: the member list is read off the
    protocol declaration in `families/base.py`, which is the specification,
    and asserted member by member rather than by trusting `isinstance` alone
    -- a `runtime_checkable` protocol only tests for presence, and would keep
    passing if a member were present but not callable.

    Bug this catches: a family that omits `observation` or
    `measurement_variance` (easy to do for White, where both are degenerate).
    Statically mypy catches it only for as long as `kernel_registry` stays
    typed against `Family`; at runtime, without this test, the omission would
    first surface as an AttributeError inside the batched Kalman assembly in
    Task 6, far from its cause.
    """
    assert isinstance(family, Family)
    for member in (
        "param_specs",
        "transition",
        "process_noise",
        "stationary_cov",
        "observation",
        "measurement_variance",
        "acvf",
    ):
        assert callable(getattr(family, member)), member
    assert isinstance(family.kind, str) and family.kind
    assert isinstance(family.state_dim, int)
    assert family.engine_costs and family.gradient_modes


def test_param_specs_declaration_order_matches_theta_column_order():
    """The order of `param_specs()` is the order of theta's columns.

    Behaviour: `free_param_index` builds the optimizer's flat parameter vector
    from each term's *declared* parameter order, while the family's own
    methods index theta positionally (`[:, 0]` is sigma, `[:, 1]` is rho).
    Nothing enforces that those two agree, so it is asserted here.

    Expected values determined independently, by hand: assemble theta by name
    from sigma=3.0, rho=7.0 and use the closed forms. P_inf = sigma^2 = 9.0,
    and at dt = 7.0, F = exp(-7/7) = exp(-1). If `param_specs()` listed rho
    first, theta would be [7.0, 3.0] and the same call would yield P_inf = 49
    and F = exp(-7/3) instead.

    Bug this catches: reordering (or renaming) a family's declared parameters
    without changing its positional indexing. The optimizer would then search
    sigma while the family read it as rho -- a silent transposition that still
    converges, to a wrong fit.
    """
    values = {"sigma": 3.0, "rho": 7.0}
    fam = Matern12()
    specs = fam.param_specs()
    assert list(specs) == ["sigma", "rho"]

    theta = np.array([[values[name] for name in specs]])
    np.testing.assert_allclose(fam.stationary_cov(theta)[0, 0, 0], 9.0, rtol=1e-15)
    np.testing.assert_allclose(
        fam.transition(theta, 7.0)[0, 0, 0], np.exp(-1.0), rtol=1e-15
    )

    assert list(White().param_specs()) == ["sigma"]
    for spec in (*specs.values(), *White().param_specs().values()):
        assert isinstance(spec.transform, Log), spec.name
        assert spec.bounds[0] == 0.0, spec.name
        assert spec.default > 0.0, spec.name
    assert specs["rho"].unit == "time"


@pytest.mark.parametrize("dt", [0.1, 1.0, 7.0])
@pytest.mark.parametrize("rho", [0.5, 3.0, 40.0])
def test_matern12_transition_matches_expm(dt, rho):
    """Analytic F equals expm(A*dt) for the OU drift A = -1/rho.

    Bug this catches: a sign error or a missing reciprocal in the analytic
    form, which would invert the meaning of the correlation timescale.
    """
    fam = Matern12()
    theta = np.array([[1.0, rho]])
    drift = np.array([[-1.0 / rho]])
    np.testing.assert_allclose(
        fam.transition(theta, dt)[0], expm_transition(drift, dt), rtol=1e-12, atol=1e-14
    )


@pytest.mark.parametrize("dt", [0.25, 2.0])
def test_matern12_process_noise_matches_lyapunov(dt):
    """Analytic Q equals P_inf - F P_inf F' with P_inf from a Lyapunov solve.

    Bug this catches: forgetting the (1 - exp(-2 dt / rho)) factor, which
    makes the process non-stationary and inflates low-frequency power.

    SHARED ASSUMPTION, STATED DELIBERATELY: the `drift` and `diffusion`
    matrices below are hand-typed from the same SDE-to-matrix mapping that
    `Matern12` itself encodes, namely

        dx = -(1 / rho) x dt + sigma sqrt(2 / rho) dW.

    That mapping is therefore NOT under test here -- a conceptual error in it
    would appear identically on both sides and cancel. What this test does
    check is that, given that mapping, the closed forms
    F = exp(-dt/rho) and Q = sigma^2 (1 - exp(-2 dt/rho)) agree with the
    general expm / continuous-Lyapunov machinery to machine precision. The
    mapping's own correctness rests on an independent re-derivation from the
    SDE (recorded in the Task 4 brief audit and restated in the `Matern12`
    class docstring), not on this test's agreement.
    """
    sigma, rho = 2.0, 5.0
    fam = Matern12()
    theta = np.array([[sigma, rho]])
    drift = np.array([[-1.0 / rho]])
    diffusion = np.array([[sigma * np.sqrt(2.0 / rho)]])
    p_inf = lyapunov_stationary_cov(drift, diffusion)
    f = expm_transition(drift, dt)
    np.testing.assert_allclose(
        fam.process_noise(theta, dt)[0],
        process_noise_from_stationary(p_inf, f),
        rtol=1e-11,
        atol=1e-13,
    )
    np.testing.assert_allclose(fam.stationary_cov(theta)[0], p_inf, rtol=1e-12)


def test_matern12_acvf_matches_textbook_closed_form():
    """ACVF is sigma^2 exp(-|tau|/rho).

    Expected value determined independently: this is the standard OU
    autocovariance (Rasmussen & Williams eq. 4.9, Matern nu=1/2), written out
    by hand rather than read off the implementation.
    """
    sigma, rho = 1.5, 4.0
    lags = np.array([0.0, 1.0, 10.0])
    expected = sigma**2 * np.exp(-np.abs(lags) / rho)
    np.testing.assert_allclose(
        Matern12().acvf(np.array([[sigma, rho]]), lags)[0], expected, rtol=1e-12
    )


@pytest.mark.parametrize("rho", [0.5, 3.0, 40.0])
@pytest.mark.parametrize("sigma", [0.25, 2.0])
def test_matern12_at_zero_lag_is_identity_and_exactly_noiseless(sigma, rho):
    """At dt = 0, F is exactly the identity and Q is exactly zero.

    Behaviour: a zero-length step must advance nothing and add nothing.
    Repeated timestamps are ordinary in real records -- two casts logged in
    the same minute, a duplicated row after a merge -- so dt = 0 is a case the
    filter will meet in production, not an exotic one.

    Expected values derived from the mathematics, not by running the code:
    F(0) = exp(-0 / rho) = exp(0) = 1, and
    Q(0) = sigma^2 (1 - exp(-0)) = sigma^2 (1 - 1) = 0,
    for every sigma and every rho.

    Bugs this catches -- any non-zero Q at dt = 0 injects process noise the
    model does not contain every time two observations share a timestamp,
    inflating the innovation variance and biasing sigma upward:
      * a step floored away from zero as a degeneracy guard, e.g.
        `dt = max(dt, 1e-12)`, which reports Q = 1.6e-12 rather than 0 for
        sigma=2, rho=5;
      * a jitter added to Q for Cholesky stability, e.g. `Q + 1e-10 I`, which
        reports exactly that floor;
      * a transition clipped or regularised away from 1, so F(0) != I and the
        state is attenuated across a zero-length step.
    The assertions are exact equality precisely because "small" is not good
    enough here.

    Checked, and NOT claimed: at d = 1 the literal difference form
    P_inf - F P_inf F' is *also* exactly zero at dt = 0 -- verified numerically
    with F both analytic and from `scipy.linalg.expm`, since expm(0) returns
    exactly I. So this test does not distinguish the factored form from the
    difference form for Matern12. That distinction only becomes testable for
    the d > 1 families, where F P_inf F' is a sum of products.
    """
    theta = np.array([[sigma, rho]])
    fam = Matern12()
    np.testing.assert_array_equal(fam.transition(theta, 0.0), np.ones((1, 1, 1)))
    np.testing.assert_array_equal(fam.process_noise(theta, 0.0), np.zeros((1, 1, 1)))


@pytest.mark.parametrize("rho", [0.5, 3.0, 40.0])
def test_matern12_at_long_lag_forgets_the_state(rho):
    """As dt/rho grows without bound, F -> 0 and Q -> P_inf.

    Behaviour: across a long gap the process forgets its state entirely, which
    is what makes a gap-heavy series behave like an independent draw across
    the gap rather than a correlated one.

    Expected values derived from the mathematics, not by running the code. At
    dt = 200 rho the exponent is exactly -200 regardless of rho, so
    F = exp(-200) = 1.4e-87, and
    Q = sigma^2 (1 - exp(-400)) = sigma^2 (1 - 1.9e-174),
    which is sigma^2 to the last bit in float64. The thresholds below are
    slack around those two hand-computed numbers.

    Bugs this catches:
      * a sign error in the exponent -- F = exp(+dt/rho) overflows to inf
        here instead of decaying to zero, and Q turns negative;
      * a non-stationary (Brownian) process noise such as
        Q = sigma^2 * 2 dt / rho, which never saturates: at this lag it would
        report 400 sigma^2 instead of sigma^2, i.e. unbounded low-frequency
        power. The dt values the brief already covers (0.1 to 7) are far too
        short for that divergence to be visible.
    """
    sigma = 1.5
    fam = Matern12()
    theta = np.array([[sigma, rho]])
    dt = 200.0 * rho

    f = fam.transition(theta, dt)
    assert f.shape == (1, 1, 1)
    assert abs(float(f[0, 0, 0])) < 1e-80

    np.testing.assert_allclose(fam.process_noise(theta, dt), [[[sigma**2]]], rtol=1e-15)
    np.testing.assert_allclose(
        fam.process_noise(theta, dt), fam.stationary_cov(theta), rtol=1e-15
    )


def test_matern12_is_state_noise_not_measurement_noise():
    """Matern12 observes its state with H = 1 and adds nothing to R.

    Behaviour: the complement of `test_white_is_measurement_noise_not_state`.
    Between them the two families partition the model: White contributes only
    to R and has no state, Matern12 contributes only state and nothing to R.
    Neither half was checked for Matern12 by the brief's tests.

    Expected values determined independently: the OU state *is* the modelled
    signal, so the observation row is [1] and sigma already enters through
    P_inf and Q. Adding it to R as well would count the same variance twice.

    Bugs this catches:
      * `measurement_variance` returning sigma^2 rather than 0 -- the marginal
        variance would be double-counted, so a fit would drive sigma to about
        1/sqrt(2) of the truth while still converging cleanly;
      * `observation` returning 0 instead of 1, which makes the state
        unobservable: every innovation collapses to the raw residual and the
        likelihood stops depending on rho at all.
    """
    theta = np.array([[2.0, 5.0], [0.5, 1.0]])
    fam = Matern12()
    assert fam.state_dim == 1
    np.testing.assert_array_equal(fam.observation(theta), np.ones((2, 1)))
    np.testing.assert_array_equal(fam.measurement_variance(theta), np.zeros(2))


def test_white_is_measurement_noise_not_state():
    """White noise has no state dimension and only sets R.

    Bug this catches: giving white a state dimension, which would make
    `white + SHO` d=3 instead of d=2 and silently change every memory figure.
    """
    fam = White()
    assert fam.state_dim == 0
    theta = np.array([[0.3]])
    assert fam.measurement_variance(theta)[0] == pytest.approx(0.09)
    assert fam.transition(theta, 1.0).shape == (1, 0, 0)


def test_white_broadcasts_over_the_batch_axis_with_distinct_parameters():
    """White at B=3 keeps each member's own sigma and its (B, 0, 0) state blocks.

    Behaviour: acceptance criterion 5 requires *every* family method to take
    theta of shape (B, p) and return leading batch axes. White is the family
    where that is easiest to get wrong, because its state blocks are
    zero-dimensional: an implementation that builds them as `np.zeros((0, 0))`
    or with a hard-coded leading 1 loses the batch axis without any *value*
    ever being wrong, so a values-only test would pass. Hence the shapes are
    asserted alongside the values, and B > 1 with a different sigma per member
    so that a single-member broadcast cannot masquerade as correct.

    Bugs this catches:
      * `measurement_variance` returning `theta[0, 0] ** 2` broadcast across
        the batch -- every pixel fitted with the first pixel's noise level,
        which converges to a plausible wrong answer rather than crashing;
      * transition / process_noise / stationary_cov / observation collapsing
        the batch axis on the zero-dimensional block, which would silently
        misalign the state blocks when White is composed with a d > 0 family.

    Expected values determined independently: white noise contributes
    R = sigma^2, so sigma = [0.3, 2.0, 0.5] gives [0.09, 4.0, 0.25] by hand.
    Uncorrelated noise has ACVF sigma^2 at lag 0 and exactly 0 at every other
    lag, by definition of independence.
    """
    theta = np.array([[0.3], [2.0], [0.5]])
    fam = White()

    np.testing.assert_allclose(
        fam.measurement_variance(theta), [0.09, 4.0, 0.25], rtol=1e-15
    )
    assert fam.measurement_variance(theta).shape == (3,)

    assert fam.transition(theta, 1.0).shape == (3, 0, 0)
    assert fam.process_noise(theta, 1.0).shape == (3, 0, 0)
    assert fam.stationary_cov(theta).shape == (3, 0, 0)
    assert fam.observation(theta).shape == (3, 0)

    np.testing.assert_allclose(
        fam.acvf(theta, np.array([0.0, 1.0, 5.0])),
        [[0.09, 0.0, 0.0], [4.0, 0.0, 0.0], [0.25, 0.0, 0.0]],
        rtol=1e-15,
    )


def test_families_broadcast_over_the_batch_axis():
    """theta of shape (B, p) yields leading batch axes everywhere.

    Bug this catches: a family written for a single series, which would force
    a Python loop over pixels at the exact place the design forbids one.
    """
    theta = np.array([[1.0, 2.0], [2.0, 8.0], [0.5, 1.0]])
    fam = Matern12()
    assert fam.transition(theta, 1.0).shape == (3, 1, 1)
    assert fam.process_noise(theta, 1.0).shape == (3, 1, 1)
    assert fam.stationary_cov(theta).shape == (3, 1, 1)
    assert fam.acvf(theta, np.array([0.0, 1.0])).shape == (3, 2)


def test_matern12_batch_members_do_not_share_parameters():
    """Each batch member of Matern12 uses its own (sigma, rho), not member 0's.

    Behaviour: the shape-only broadcast test above passes even if every row of
    the output is computed from theta[0], so the values are pinned here too.

    Expected values determined independently, by hand from the closed forms
    F = exp(-dt/rho) and P_inf = sigma^2 with dt = 1:
    row 0 (sigma=1, rho=2)   -> F = exp(-0.5),   P_inf = 1.0
    row 1 (sigma=2, rho=8)   -> F = exp(-0.125), P_inf = 4.0
    row 2 (sigma=0.5, rho=1) -> F = exp(-1.0),   P_inf = 0.25

    Bug this catches: indexing theta with `[0, 1]` instead of `[:, 1]`, i.e.
    fitting the whole batch with the first series' timescale -- a bug that
    produces correctly-shaped, converged, wrong results.
    """
    theta = np.array([[1.0, 2.0], [2.0, 8.0], [0.5, 1.0]])
    fam = Matern12()
    np.testing.assert_allclose(
        fam.transition(theta, 1.0)[:, 0, 0],
        [np.exp(-0.5), np.exp(-0.125), np.exp(-1.0)],
        rtol=1e-15,
    )
    np.testing.assert_allclose(
        fam.stationary_cov(theta)[:, 0, 0], [1.0, 4.0, 0.25], rtol=1e-15
    )
