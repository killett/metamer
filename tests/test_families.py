import subprocess
import sys

import numpy as np
import pytest

from metamer.core.capability import CostClass, EngineId, GradientMode, Objective
from metamer.core.families.base import Family
from metamer.core.families.matern12 import Matern12
from metamer.core.families.matern32 import Matern32
from metamer.core.families.white import White
from metamer.core.registry import kernel_registry
from metamer.core.terms import TermSpec
from metamer.core.transforms import Log
from tests.oracles import (
    expm_transition,
    lyapunov_stationary_cov,
    process_noise_from_stationary,
)

# WHAT EACH FAMILY DECLARES, WRITTEN OUT PER FAMILY RATHER THAN DERIVED FROM
# THE ENUMS.
#
# `engine_costs` is a capability declaration, not a performance hint. A family
# that omits an engine is not "slow" there, it is ELIMINATED there:
# `intersect_engine_costs` drops any engine that a single term fails to declare,
# so one missing key removes that engine from every composite the family appears
# in. The standard for declaring an engine is therefore:
#
#     can this engine evaluate ITS OWN objective for this family's kernel,
#     without altering the kernel?
#
# That is deliberately NOT "is this engine exact in absolute terms". Whittle is
# an approximate objective by construction, but the approximation belongs to the
# engine -- which tags every score it produces, so a Whittle score is never
# compared against an exact one -- and Whittle can represent any kernel with a
# closed-form spectral density, which all three families have. What the standard
# forbids is an engine that silently substitutes a DIFFERENT kernel and reports
# the result as this model's likelihood.
#
# celerite2 is exactly that case for Matern nu=3/2. Its basis is sums of
# exp(-c tau) cos(d tau) and exp(-c tau) sin(d tau); the tau exp(-lambda tau)
# term in (1 + lambda|tau|) exp(-lambda|tau|) is not in that span, which is why
# celerite2 offers Matern 3/2 only as an approximation built by splitting the
# repeated root with a small epsilon. That repeated root is the entire point of
# the family -- it is the case that breaks eigendecomposition and that
# `statespace.eigen_transition` refuses -- so epsilon-splitting it to fit another
# engine's basis is precisely the fudge the defective-root guard exists to
# detect. matern32 therefore does NOT declare CELERITE2, and
# `test_a_matern32_composite_is_eliminated_from_celerite2` pins the consequence.
#
# White and Matern 1/2 ARE in the celerite basis exactly -- a diagonal nugget is
# celerite2's jitter term, and sigma^2 exp(-tau/rho) is a single real
# exponential with a = sigma^2, c = 1/rho, b = d = 0 -- so they keep it.
EXPECTED_ENGINE_COSTS = {
    "white": {
        EngineId.KALMAN: CostClass.LINEAR,
        EngineId.WHITTLE: CostClass.NLOGN,
        EngineId.TOEPLITZ: CostClass.CUBIC,
        EngineId.CELERITE2: CostClass.LINEAR,
    },
    "matern12": {
        EngineId.KALMAN: CostClass.LINEAR,
        EngineId.WHITTLE: CostClass.NLOGN,
        EngineId.TOEPLITZ: CostClass.CUBIC,
        EngineId.CELERITE2: CostClass.LINEAR,
    },
    "matern32": {
        EngineId.KALMAN: CostClass.LINEAR,
        EngineId.WHITTLE: CostClass.NLOGN,
        EngineId.TOEPLITZ: CostClass.CUBIC,
    },
}

# `gradient_modes`, by contrast, MUST cover every Objective: ML and REML are
# objectives over the same likelihood, not representations, so every family
# supports both and a missing key means "no gradient rule" -- a defect. The
# per-family table exists here for a different reason: Task 12 gives matern12 an
# ANALYTIC derivative, and a single global `all(mode is FINITE_DIFFERENCE)`
# assertion would then have to be loosened for every family at once, which is
# how a family comes to advertise ANALYTIC without shipping the derivatives.
EXPECTED_GRADIENT_MODES = {
    "white": {
        Objective.ML: GradientMode.FINITE_DIFFERENCE,
        Objective.REML: GradientMode.FINITE_DIFFERENCE,
    },
    "matern12": {
        Objective.ML: GradientMode.FINITE_DIFFERENCE,
        Objective.REML: GradientMode.FINITE_DIFFERENCE,
    },
    "matern32": {
        Objective.ML: GradientMode.FINITE_DIFFERENCE,
        Objective.REML: GradientMode.FINITE_DIFFERENCE,
    },
}


@pytest.mark.parametrize("family", [White(), Matern12(), Matern32()])
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
    # Asserted against the per-family table above, NOT against `set(EngineId)`.
    # Requiring every family to declare every engine forces a family to claim an
    # engine that cannot evaluate it -- Matern 3/2 and celerite2 is the concrete
    # case, see the table's comment -- and a family declaring an engine it
    # cannot evaluate exactly is the bug this guards. Declaring too FEW is
    # equally a bug, since an omitted engine is eliminated from every composite
    # the family joins, so equality is asserted rather than a subset either way.
    declared = family.engine_costs
    assert declared == EXPECTED_ENGINE_COSTS[family.kind], family.kind
    assert declared, "a family declaring no engine cannot be fitted at all"
    assert all(isinstance(e, EngineId) for e in declared), family.kind
    assert all(isinstance(c, CostClass) for c in declared.values()), family.kind
    # Phase 1 implements only KALMAN, so a family that could not be evaluated
    # there would be unfittable today whatever else it declares.
    assert EngineId.KALMAN in declared, family.kind

    modes = family.gradient_modes
    assert modes == EXPECTED_GRADIENT_MODES[family.kind], family.kind
    assert set(modes) == set(Objective), family.kind
    assert all(isinstance(o, Objective) for o in modes), family.kind
    assert all(isinstance(m, GradientMode) for m in modes.values()), family.kind


def test_param_specs_declaration_order_matches_theta_column_order():
    """The order of `param_specs()` is the order of theta's columns.

    Behaviour: `free_param_index` builds the optimizer's flat parameter vector
    from each term's *declared* parameter order, while the family's own
    methods index theta positionally (`[:, 0]` is sigma, `[:, 1]` is rho).
    Nothing enforces that those two agree, so it is asserted here.

    Expected values determined independently, by hand: assemble theta by name
    from sigma=3.0, rho=7.0 and use the closed forms. For Matern12,
    P_inf = sigma^2 = 9.0, and at dt = 7.0, F = exp(-7/7) = exp(-1). If
    `param_specs()` listed rho first, theta would be [7.0, 3.0] and the same
    call would yield P_inf = 49 and F = exp(-7/3) instead.

    For Matern32 the same substitution is caught by P_inf[1, 1], which is
    sigma^2 lambda^2 = 9 * 3/49 = 27/49; with the columns swapped it would be
    49 * 3/9 = 49/3, a factor of 88 out. Its P_inf[0, 0] is again sigma^2 = 9.0,
    since `sigma` is the marginal standard deviation in both families.

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

    fam32 = Matern32()
    specs32 = fam32.param_specs()
    assert list(specs32) == ["sigma", "rho"]
    theta32 = np.array([[values[name] for name in specs32]])
    p_inf32 = fam32.stationary_cov(theta32)[0]
    np.testing.assert_allclose(p_inf32[0, 0], 9.0, rtol=1e-15)
    np.testing.assert_allclose(p_inf32[1, 1], 27.0 / 49.0, rtol=1e-15)

    assert list(White().param_specs()) == ["sigma"]
    for spec in (*specs.values(), *specs32.values(), *White().param_specs().values()):
        assert isinstance(spec.transform, Log), spec.name
        assert spec.bounds[0] == 0.0, spec.name
        assert spec.default > 0.0, spec.name
    assert specs["rho"].unit == "time"
    assert specs32["rho"].unit == "time"


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

    Checked, and NOT claimed: the literal difference form P_inf - F P_inf F'
    is *also* exactly zero here -- verified numerically with F both analytic
    and from `scipy.linalg.expm`. That holds at any state dimension, not just
    d = 1: if F is exactly I then F P_inf F' is exactly P_inf and the
    subtraction is exact, whatever the size of the block. So dt = 0 does not
    distinguish the two forms at all. The difference form's real weakness is
    small *nonzero* dt, at every d, and that is what
    `test_matern12_process_noise_is_accurate_for_tiny_steps` covers.
    """
    theta = np.array([[sigma, rho]])
    fam = Matern12()
    np.testing.assert_array_equal(fam.transition(theta, 0.0), np.ones((1, 1, 1)))
    np.testing.assert_array_equal(fam.process_noise(theta, 0.0), np.zeros((1, 1, 1)))


@pytest.mark.parametrize(
    ("rho", "dt"),
    [
        (1.0e6, 1.0e-4),
        (1.0e3, 1.0e-11),
        (5.0, 1.0e-13),
        (1.0e6, 1.0e-11),
    ],
)
def test_matern12_process_noise_is_accurate_for_tiny_steps(rho, dt):
    """Q keeps full relative precision as dt/rho -> 0, and stays strictly positive.

    Behaviour: Q(dt) must be accurate *relatively*, not just absolutely. It is
    a variance that the Kalman filter divides by, so a Q that is 0.08% low --
    or zero -- is not a rounding detail, it is a wrong innovation variance.

    This regime is reachable, not contrived: `rho`'s diagnostic upper limit is
    1e6 and the user chooses the time units, so rho = 1e6 with a sub-second
    step is an ordinary combination. It is also exactly the near-duplicate
    timestamp case that
    `test_matern12_at_zero_lag_is_identity_and_exactly_noiseless` argues is
    ordinary in real records -- dt = 0 is handled exactly, and it would be
    incoherent for dt = 1e-11 to be handled badly.

    Expected value determined independently of the implementation, from the
    Maclaurin series 1 - e^-x = x - x^2/2 + x^3/6 - ... with x = 2 dt / rho.
    Every x here is below 1e-9, so the truncation error after the cubic term
    is under x^4/24 < 1e-37 relative -- far below double precision. The series
    is therefore an exact reference in this regime, and crucially it never
    forms the difference `1 - (something near 1)`.

    Bug this catches: computing Q as `sigma^2 * (1.0 - np.exp(-2 dt / rho))`.
    exp(-x) is near 1 for small x, so the subtraction is catastrophic
    cancellation. Measured against the series above: 8.3e-8 relative error at
    x = 2e-10, 8.0e-4 at x = 2e-14, and at x = 2e-17 exp(-x) rounds to exactly
    1.0 so Q flushes to exactly 0 -- zero process noise on a nonzero step,
    i.e. the filter told the state evolves deterministically. `-expm1(-x)` is
    the standard remedy and reproduces the series to the last bit.
    """
    sigma = 2.0
    x = 2.0 * dt / rho
    expected = sigma**2 * (x - x**2 / 2.0 + x**3 / 6.0)

    q = Matern12().process_noise(np.array([[sigma, rho]]), dt)
    assert q.shape == (1, 1, 1)
    assert q[0, 0, 0] > 0.0, "a strictly positive step must give strictly positive Q"
    np.testing.assert_allclose(q[0, 0, 0], expected, rtol=1e-14)


def test_acvf_agrees_with_the_state_space_triple():
    """acvf(tau) equals H F(tau) P_inf H' -- the two routes are joined by a test.

    Behaviour: a family ships two descriptions of the same process, an
    analytic autocovariance and a state-space triple (H, F, P_inf), and the
    engines use both. Until now they were joined only by a derivation written
    in a docstring: `test_matern12_acvf_matches_textbook_closed_form` checks
    the ACF against the literature, and the expm/Lyapunov tests check the
    triple, but nothing checked the two against *each other*.

    Expected value determined independently of both: the stationary
    cross-covariance identity Cov(y_t, y_{t+tau}) = H F(tau) P_inf H' is a
    property of any linear-Gaussian state-space model, not of this family, and
    is written here in terms the family exposes. It does not restate the OU
    closed form, and it does not go near the SDE-to-matrix mapping that the
    Lyapunov test has to assume -- so it is independent of that shared
    assumption too.

    Bug this catches: a sigma-versus-sigma^2 slip between the two routes --
    for instance P_inf = sigma (a std where a variance belongs) while the ACF
    correctly returns sigma^2 exp(-|tau|/rho). Each half stays
    self-consistent and every existing test still passes; only the comparison
    between them fails. The result would be a Kalman likelihood and a
    Toeplitz/Whittle likelihood that disagree for the same fitted parameters.
    """
    theta = np.array([[1.5, 4.0], [0.5, 0.25], [3.0, 100.0]])
    fam = Matern12()
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
    np.testing.assert_allclose(fam.acvf(theta, lags), from_triple, rtol=1e-13)


@pytest.mark.parametrize("rho", [0.5, 3.0, 40.0])
def test_matern12_at_long_lag_forgets_the_state(rho):
    """As dt/rho grows without bound, F -> 0 and Q -> P_inf.

    Behaviour: across a long gap the process forgets its state entirely, which
    is what makes a gap-heavy series behave like an independent draw across
    the gap rather than a correlated one.

    Expected values derived from the mathematics, not by running the code. At
    dt = 200 rho the exponent is exactly -200 regardless of rho, so
    F = exp(-200) = 1.3838965267367376e-87, and
    Q = sigma^2 (1 - exp(-400)) = sigma^2 (1 - 1.9151695967140057e-174),
    which is sigma^2 to the last bit in float64.

    F is pinned to that value rather than bounded below some threshold. A
    bound like `< 1e-80` is satisfied by exp(-400) = 1.9e-174 too, so it would
    not notice a doubled exponent -- and doubling is the specific confusion
    available here, since Q legitimately carries the factor 2 that F does not.

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
    np.testing.assert_allclose(f[0, 0, 0], 1.3838965267367376e-87, rtol=1e-13)

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


def test_importing_metamer_core_registers_the_builtin_families():
    """`import metamer.core` is enough to populate `kernel_registry`.

    Behaviour: `TermSpec.engine_costs()` resolves `kind` through
    `kernel_registry`, so every family must be registered before any spec can
    be costed. Registration happens as an import side effect of
    `metamer.core.families`, and *something* has to trigger that import.

    Run in a subprocess, like `test_core_imports_without_batch_dependencies`,
    because this module's own top-level imports of `Matern12` and `White`
    already register both families. In-process the assertion would pass no
    matter where (or whether) the triggering import lives -- it would be a
    test of this file's import list, not of the package.

    Bug this catches, and which was live until this commit: nothing in `src/`
    imported `metamer.core.families` and no `metamer.kernels` entry points
    were declared, so a fresh interpreter had an empty registry and
    `TermSpec(kind="matern12", params={}).engine_costs()` raised
    `KeyError: kernel_registry: unknown key 'matern12'. Available: ` -- with
    the available list empty. Every test passed regardless, because the test
    modules imported the families directly.

    `metamer.core` is the right trigger rather than the top-level
    `metamer`: `terms.py` and `registry.py` both live under `metamer.core`,
    so `import metamer.core` alone must yield a working registry.
    """
    code = (
        "import metamer.core\n"
        "from metamer.core.registry import kernel_registry\n"
        "from metamer.core.terms import TermSpec\n"
        "missing = {'white', 'matern12', 'matern32'} - set(kernel_registry)\n"
        "assert not missing, (missing, sorted(kernel_registry))\n"
        "costs = TermSpec(kind='matern12', params={}).engine_costs()\n"
        "assert costs, costs\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("kind", ["white", "matern12", "matern32"])
def test_registry_lookup_returns_a_conforming_family(kind):
    """A registry lookup yields a real `Family`, and costing a term works.

    Behaviour: the registry's contract is that `kernel_registry[kind]()`
    returns something satisfying `Family`. Every other registry test uses a
    throwaway probe -- `lambda: 1`, `lambda: "kernel"`, `_FakeFamily` -- and
    each of those now carries a `# type: ignore`, so before this test nothing
    exercised the registry with a conforming family at all.

    Expected value determined independently: the engine cost mapping comes from
    `EXPECTED_ENGINE_COSTS`, which is written out per family from the capability
    standard rather than read off the class. `intersect_engine_costs` over a
    single term is the identity, so a one-term spec must report exactly that
    mapping -- including matern32's three-engine mapping, so this test also
    checks that a family with a SHORTER declaration survives the intersection
    intact rather than being padded back out to the full enum.

    Bug this catches: a registration that stores the instance rather than the
    class (so the lookup returns a `Family`, and calling it raises
    `TypeError: 'White' object is not callable`), or a `kind` string that does
    not match the registry key it is filed under -- which would make
    `TermSpec(kind=...)` unresolvable for that family alone.
    """
    family = kernel_registry[kind]()
    assert isinstance(family, Family)
    assert family.kind == kind

    expected = EXPECTED_ENGINE_COSTS[kind]
    assert family.engine_costs == expected
    assert TermSpec(kind=kind, params={}).engine_costs() == expected


def test_a_matern32_composite_is_eliminated_from_celerite2():
    """Any composite containing Matern 3/2 loses celerite2, keeping the rest.

    Behaviour: this is the whole consequence of matern32 not declaring
    CELERITE2, and until now it was asserted only on the family in isolation.
    `intersect_engine_costs` drops an engine that any single term fails to
    declare, so `matern12 + matern32` -- where matern12 DOES support celerite2
    exactly -- must still be refused celerite2, because the composite kernel
    contains a term celerite2 cannot represent without altering it.

    Expected values determined independently, by intersecting the two tables by
    hand: matern12 declares four engines, matern32 three, and the intersection
    is matern32's three. The cost classes are the elementwise maxima, which for
    identical declarations are those values unchanged.

    Bugs this catches:
      * re-adding CELERITE2 to matern32 "for consistency with the other
        families", which would let a nu=3/2 composite be routed to an engine
        that returns an epsilon-split approximation and report it as this
        model's likelihood;
      * an `intersect_engine_costs` that unions rather than intersects, which
        would keep celerite2 alive because one term happens to support it --
        the failure mode that matters, since the engine would then be selected
        precisely when the model is cheapest-looking and least representable.
    """
    spec = TermSpec(kind="matern12", params={}) + TermSpec(kind="matern32", params={})
    costs = spec.engine_costs()
    assert EngineId.CELERITE2 not in costs
    assert costs == EXPECTED_ENGINE_COSTS["matern32"]

    solo = TermSpec(kind="matern12", params={}) + TermSpec(kind="white", params={})
    assert EngineId.CELERITE2 in solo.engine_costs()
