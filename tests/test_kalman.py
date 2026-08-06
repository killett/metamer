import numpy as np
import pytest

from metamer.core.capability import EngineId, Objective
from metamer.core.engines.kalman import KalmanEngine
from metamer.core.engines.protocol import Engine, ScoredResult
from metamer.core.outcomes import Outcome
from metamer.core.statespace import StateSpace
from metamer.core.terms import ProcessSpec
from tests.oracles import mvn_loglik
from tests.test_statespace import _term


def _covariance(ss: StateSpace, theta: np.ndarray, t: np.ndarray) -> np.ndarray:
    """Build Sigma from the STATE terms' ACVF plus measurement noise on the diagonal.

    Two things are deliberate here and neither is cosmetic.

    First, only families with `state_dim > 0` contribute to the lag part. White
    noise is measurement noise: it lives in R and is never a state block, so
    summing the composite ACVF (which already places sigma^2 at lag 0) *and*
    adding `R * I` would count the white variance twice. That double count is
    invisible on a pure-Matern spec and shifts the composite log-likelihood by
    an O(1) constant.

    Second, the measurement noise is keyed on INDEX (`np.eye`), not on the lag
    being zero. Keying it on `lag == 0.0` gives two distinct observations that
    share a timestamp the same sigma^2 OFF the diagonal, i.e. perfectly
    correlated measurement error, which is not what the filter models and is not
    what a duplicated timestamp means.
    """
    lags = np.abs(t[:, None] - t[None, :])
    cov = np.zeros((t.size, t.size), dtype=np.float64)
    for family, pslice in zip(ss.families, ss.param_slices, strict=True):
        if family.state_dim == 0:
            continue
        cov = cov + family.acvf(theta[:, pslice], lags.ravel())[0].reshape(lags.shape)
    return cov + np.eye(t.size) * ss.measurement_variance(theta)[0]


# `ProcessSpec` sorts its terms canonically at construction, so the order the
# kinds are written in is NOT the order `theta` is sliced in. Kinds sort
# alphabetically, so white -- written first below, as it reads naturally --
# lands last. `test_composite_spec_orders_terms_canonically` pins this rather
# than leaving it as an assumption of the composite likelihood test.
COMPOSITE_KINDS = ["white", "matern12", "matern32"]
COMPOSITE_ORDER = ("matern12", "matern32", "white")
# matern12(sigma=1.0, rho=4.0), matern32(sigma=1.2, rho=1.5), white(sigma=0.7).
# Marginal variances 1.0, 1.44, 0.49 -- the same order of magnitude, so every
# term actually moves the likelihood. A white sigma large enough to swamp the
# state terms turns this into a white-noise test wearing a composite's name.
COMPOSITE_THETA = [1.0, 4.0, 1.2, 1.5, 0.7]


def test_composite_spec_orders_terms_canonically():
    """theta is sliced in canonical order, not in the order the kinds were written.

    Bug this catches: a composite test that hands `theta` in written order, so
    its parameters land on the wrong families -- e.g. a white sigma of 11
    arriving as a Matern amplitude while a Matern rho becomes R. The likelihood
    still matches an oracle built from the same misassignment, so the test goes
    green while exercising almost nothing.
    """
    spec = ProcessSpec(tuple(_term(k) for k in COMPOSITE_KINDS))
    assert tuple(term.kind for term in spec.terms) == COMPOSITE_ORDER

    ss = StateSpace.from_spec(spec)
    assert tuple(f.kind for f in ss.families) == COMPOSITE_ORDER
    # matern12 d=1, matern32 d=2, white d=0.
    assert ss.state_dim == 3
    theta = np.array([COMPOSITE_THETA])
    # The last slot is white's sigma, so R must be exactly its square.
    assert ss.measurement_variance(theta)[0] == pytest.approx(0.7**2, abs=1e-15)


@pytest.mark.parametrize(
    "kinds, theta",
    [
        (["matern12"], [1.3, 4.0]),
        (["matern32"], [0.8, 6.0]),
        (COMPOSITE_KINDS, COMPOSITE_THETA),
    ],
)
def test_filter_loglik_matches_brute_force_mvn(kinds, theta):
    """The Kalman log-likelihood equals an explicit MVN density.

    The oracle is built from analytic autocovariances and an explicit
    covariance matrix, so it is independent of the entire state-space
    formulation. This is the primary correctness test for the engine.

    Bug this catches: a missing 2*pi, a dropped log|S| term, or an incorrect
    stationary initialisation -- each of which shifts the likelihood by a
    constant and silently biases every information criterion.
    """
    spec = ProcessSpec(tuple(_term(k) for k in kinds))
    ss = StateSpace.from_spec(spec)
    theta_b = np.array([theta], dtype=np.float64)
    t = np.arange(24.0)
    rng = np.random.default_rng(0)
    cov = _covariance(ss, theta_b, t)
    y = rng.multivariate_normal(np.zeros(t.size), cov)[None, :]
    mask = np.ones_like(y, dtype=bool)

    result = KalmanEngine().score(ss, theta_b, y, mask, t, design=None)
    assert result.loglik[0] == pytest.approx(mvn_loglik(y[0], cov), abs=1e-9)


def test_duplicate_timestamps_are_two_independent_measurements():
    """Two observations at the same instant share the state, not the noise.

    Duplicate timestamps are ordinary in real records (two instruments, a
    reprocessed overlap). The state is perfectly correlated across them -- the
    lag is zero -- but the measurement errors are two independent draws.

    Bug this catches: an oracle (or a filter) that keys the measurement variance
    on `lag == 0.0` rather than on the index. That puts R in the OFF-diagonal
    entry linking the duplicated pair, making Sigma model perfectly correlated
    measurement noise. Here it inflates Sigma[0,1] by R = 0.49 and moves the
    log-likelihood well outside 1e-9.
    """
    spec = ProcessSpec(tuple(_term(k) for k in COMPOSITE_KINDS))
    ss = StateSpace.from_spec(spec)
    theta = np.array([COMPOSITE_THETA], dtype=np.float64)
    t = np.array([0.0, 0.0, 1.0, 2.5, 2.5, 4.0])
    cov = _covariance(ss, theta, t)

    # The duplicated pair must differ off-diagonal from the diagonal by exactly R.
    assert cov[0, 0] - cov[0, 1] == pytest.approx(0.7**2, abs=1e-12)

    rng = np.random.default_rng(11)
    y = rng.multivariate_normal(np.zeros(t.size), cov)[None, :]
    result = KalmanEngine().score(
        ss, theta, y, np.ones_like(y, dtype=bool), t, design=None
    )
    assert result.loglik[0] == pytest.approx(mvn_loglik(y[0], cov), abs=1e-9)


def test_memoized_matrices_survive_a_non_bit_exact_grid():
    """A linspace grid filters without raising and matches the MVN oracle.

    `unique_dt` returns tolerance-clustered REPRESENTATIVES, not the raw steps.
    On `np.linspace(0, 10, 101)` there are 8 distinct float64 differences and
    exactly one representative, so any memo keyed on the raw step -- a dict
    lookup on `float(t[i] - t[i-1])` -- misses on 100 of the 100 intervals.

    Bug this catches: exactly that, a `KeyError: 0.1` on every grid that is not
    bit-exact. `np.arange` grids hide it completely, which is why every other
    test here uses one and this one does not.
    """
    t = np.linspace(0.0, 10.0, 101)
    raw = np.unique(np.diff(t))
    # Precondition: the trap is real on this axis, not merely imagined.
    assert raw.size == 8
    assert StateSpace.unique_dt(t).size == 1

    spec = ProcessSpec((_term("matern12"),))
    ss = StateSpace.from_spec(spec)
    theta = np.array([[1.1, 2.0]])
    cov = _covariance(ss, theta, t)
    rng = np.random.default_rng(3)
    y = rng.multivariate_normal(np.zeros(t.size), cov)[None, :]

    result = KalmanEngine().score(
        ss, theta, y, np.ones_like(y, dtype=bool), t, design=None
    )
    assert result.loglik[0] == pytest.approx(mvn_loglik(y[0], cov), abs=1e-9)


def test_masked_points_equal_genuinely_absent_points():
    """Masking a sample gives the same likelihood as deleting it.

    Bug this catches: applying the update with a zero innovation instead of
    skipping it, which adds a spurious log|S| term per gap and biases every
    fit on gappy series -- exactly the high-latitude sea-ice case.
    """
    spec = ProcessSpec((_term("matern12"),))
    ss = StateSpace.from_spec(spec)
    theta = np.array([[1.0, 5.0]])
    t_full = np.arange(20.0)
    rng = np.random.default_rng(1)
    y_full = rng.standard_normal((1, 20))
    keep = np.ones(20, dtype=bool)
    keep[[3, 4, 5, 11]] = False

    masked = KalmanEngine().score(ss, theta, y_full, keep[None, :], t_full, design=None)
    absent = KalmanEngine().score(
        ss,
        theta,
        y_full[:, keep],
        np.ones((1, int(keep.sum())), dtype=bool),
        t_full[keep],
        design=None,
    )
    assert masked.loglik[0] == pytest.approx(absent.loglik[0], abs=1e-12)


def test_masked_epochs_score_identically_to_deleted_epochs_with_a_design():
    """A masked epoch leaves P and the accumulator exactly where deletion does.

    "Mask the update, keep the prediction" is not checkable by asserting on P
    directly -- `ScoredResult` exposes no P, and a fully masked series never
    enters the update branch at all, so such a test asserts that zero work
    produces zero output. The checkable content is the equivalence: a
    PARTIALLY masked series must score exactly as the same series with those
    rows deleted, in every accumulated quantity, not only in the log-likelihood.

    Run on Matern 3/2 so d = 2 and the prediction step propagates a genuine
    2x2 covariance across the gap, and with a design so all three cross-product
    blocks (y'Sy, y'SX, X'SX) carry the assertion.

    Bug this catches: shrinking P by a gain-scaled update at a masked epoch, or
    carrying the masked row's design values into the accumulator. Both leave
    log|S| untouched at the masked epoch and so survive a log-likelihood-only
    test on d = 1.
    """
    spec = ProcessSpec((_term("matern32"),))
    ss = StateSpace.from_spec(spec)
    theta = np.array([[1.4, 3.0]])
    t = np.arange(18.0)
    rng = np.random.default_rng(7)
    y = rng.standard_normal((1, 18))
    design = np.column_stack([np.ones(18), t / 18.0, np.cos(t)])
    keep = np.ones(18, dtype=bool)
    keep[[2, 3, 4, 9, 15]] = False

    masked = KalmanEngine().score(ss, theta, y, keep[None, :], t, design=design)
    absent = KalmanEngine().score(
        ss,
        theta,
        y[:, keep],
        np.ones((1, int(keep.sum())), dtype=bool),
        t[keep],
        design=design[keep],
    )

    assert masked.n_used[0] == absent.n_used[0] == int(keep.sum())
    assert masked.loglik[0] == pytest.approx(absent.loglik[0], abs=1e-12)
    np.testing.assert_allclose(
        masked.normal_equations[0], absent.normal_equations[0], rtol=0, atol=1e-11
    )
    assert masked.rank_x[0] == absent.rank_x[0] == 3


def test_log_determinant_accumulates_only_over_unmasked_epochs():
    """sum log S counts exactly the observed epochs.

    Expected value determined independently: for white noise of variance
    sigma^2 with no state, S = sigma^2 at every epoch, so the log-likelihood
    over m observed points is -0.5*m*(log(2 pi sigma^2) + y^2/sigma^2).

    Bug this catches: accumulating log S at masked epochs, which adds a
    spurious constant per gap and biases every fit on gappy series.
    """
    spec = ProcessSpec((_term("white"),))
    ss = StateSpace.from_spec(spec)
    sigma = 2.0
    theta = np.array([[sigma]])
    t = np.arange(6.0)
    y = np.full((1, 6), 1.5)
    mask = np.array([[True, False, True, False, True, False]])

    got = KalmanEngine().score(ss, theta, y, mask, t, design=None).loglik[0]
    m = int(mask.sum())
    expected = -0.5 * m * (np.log(2 * np.pi * sigma**2) + (1.5 / sigma) ** 2)
    assert got == pytest.approx(expected, abs=1e-12)


def test_batch_of_one_matches_batch_of_many():
    """B=1 is a shape, not a code path.

    Bug this catches: a broadcasting error that only appears at B>1, or a
    special case for B=1 that drifts from the batched path.
    """
    spec = ProcessSpec((_term("matern12"),))
    ss = StateSpace.from_spec(spec)
    rng = np.random.default_rng(2)
    theta = np.repeat(np.array([[1.0, 3.0]]), 64, axis=0)
    t = np.arange(30.0)
    y = rng.standard_normal((64, 30))
    mask = np.ones_like(y, dtype=bool)

    many = KalmanEngine().score(ss, theta, y, mask, t, design=None)
    one = KalmanEngine().score(ss, theta[:1], y[:1], mask[:1], t, design=None)
    assert many.loglik[0] == pytest.approx(one.loglik[0], abs=1e-12)
    assert many.loglik.shape == (64,)
    assert many.outcome.shape == (64,)
    assert many.n_used.shape == (64,)


def test_batched_results_equal_solo_results_series_by_series():
    """No series can influence a batch-mate, not even through a masked NaN.

    Masked slots holding NaN is the NORMAL convention for gappy data: the fill
    value under a gap is whatever the reader produced, and NaN is the usual
    choice. `accum += (w / s) * v v'` with w = 0 and v = NaN gives 0 * NaN =
    NaN, so the innovation must be zeroed under the mask before it is used,
    not merely down-weighted.

    Bug this catches: exactly that poisoning. At B=1 it is invisible because
    `if not active.any(): continue` skips the step outright; it needs one
    active series sharing the step with one masked NaN to fire. This test is
    also the standing guard for the whole per-series class -- every per-series
    concept must be per series.
    """
    spec = ProcessSpec((_term("matern12"),))
    ss = StateSpace.from_spec(spec)
    theta = np.array([[1.0, 3.0], [0.5, 7.0], [2.0, 1.0]])
    t = np.arange(12.0)
    rng = np.random.default_rng(5)
    y = rng.standard_normal((3, 12))
    mask = np.ones((3, 12), dtype=bool)
    mask[0, [2, 3, 7]] = False
    y[0, [2, 3, 7]] = np.nan

    engine = KalmanEngine()
    batched = engine.score(ss, theta, y, mask, t, design=None)

    assert np.isfinite(batched.loglik).all(), batched.loglik
    for i in range(3):
        solo = engine.score(
            ss, theta[i : i + 1], y[i : i + 1], mask[i : i + 1], t, design=None
        )
        assert batched.loglik[i] == pytest.approx(solo.loglik[0], rel=1e-13)
        assert batched.n_used[i] == solo.n_used[0]
        assert batched.outcome[i] == solo.outcome[0]
        np.testing.assert_allclose(
            batched.normal_equations[i], solo.normal_equations[0], rtol=1e-13, atol=0
        )


def test_transition_and_process_noise_are_computed_once_per_unique_dt():
    """A regular grid triggers exactly one F build and one Q build.

    Bug this catches: rebuilding F and Q inside the time loop, which discards
    the N-fold amortization that the whole performance argument rests on.
    Counting `transition` alone leaves `process_noise` -- the more expensive of
    the two for Matern 3/2 -- entirely unwatched.
    """
    spec = ProcessSpec((_term("matern12"),))
    ss = StateSpace.from_spec(spec)
    calls = {"f": 0, "q": 0}
    original_f = ss.transition
    original_q = ss.process_noise

    def counting_f(theta, dt):
        calls["f"] += 1
        return original_f(theta, dt)

    def counting_q(theta, dt):
        calls["q"] += 1
        return original_q(theta, dt)

    object.__setattr__(ss, "transition", counting_f)
    object.__setattr__(ss, "process_noise", counting_q)
    t = np.arange(50.0)
    y = np.zeros((1, 50))
    KalmanEngine().score(
        ss, np.array([[1.0, 4.0]]), y, np.ones_like(y, dtype=bool), t, design=None
    )
    assert calls == {"f": 1, "q": 1}


def test_two_distinct_steps_build_two_pairs_of_matrices():
    """The memo is keyed on the step, so two distinct steps cost two builds.

    Bug this catches: a memo that collapses everything to a single entry (for
    instance keying on the first interval only), which would pass the regular-grid
    counter above while filtering an irregular axis with the wrong F entirely.
    """
    spec = ProcessSpec((_term("matern12"),))
    ss = StateSpace.from_spec(spec)
    calls = {"f": 0, "q": 0}
    original_f = ss.transition
    original_q = ss.process_noise

    def counting_f(theta, dt):
        calls["f"] += 1
        return original_f(theta, dt)

    def counting_q(theta, dt):
        calls["q"] += 1
        return original_q(theta, dt)

    object.__setattr__(ss, "transition", counting_f)
    object.__setattr__(ss, "process_noise", counting_q)
    t = np.array([0.0, 1.0, 2.0, 4.0, 5.0, 7.0])
    y = np.zeros((1, 6))
    KalmanEngine().score(
        ss, np.array([[1.0, 4.0]]), y, np.ones_like(y, dtype=bool), t, design=None
    )
    assert calls == {"f": 2, "q": 2}


def test_result_carries_engine_and_objective_tags():
    """Every score is tagged with its engine AND its objective, and reports its counts.

    Bug this catches: an untagged score reaching the selection layer, where
    the comparability guard could not then refuse a cross-engine or cross-objective
    comparison; or a `n_used`/`rank_x` that is never populated, which the
    information criteria consume as k and n.
    """
    spec = ProcessSpec((_term("matern12"),))
    ss = StateSpace.from_spec(spec)
    t = np.arange(8.0)
    y = np.zeros((1, 8))
    mask = np.ones_like(y, dtype=bool)
    mask[0, 5] = False
    result = KalmanEngine().score(
        ss, np.array([[1.0, 2.0]]), y, mask, t, design=None, objective=Objective.REML
    )
    assert result.engine is EngineId.KALMAN
    assert result.objective is Objective.REML
    assert result.n_used.tolist() == [7]
    assert result.n_used.dtype == np.int64
    assert result.rank_x.tolist() == [0]
    assert result.normal_equations.shape == (1, 1, 1)
    assert result.outcome.tolist() == [Outcome.OK.code]

    default = KalmanEngine().score(ss, np.array([[1.0, 2.0]]), y, mask, t, design=None)
    assert default.objective is Objective.ML


def test_nonpositive_innovation_variance_is_classified_per_series():
    """A zero innovation variance is a tagged failure, not a silent NaN.

    With R = 0 the first update drives P to exactly 0. A repeated timestamp
    then has F(0) = I and Q(0) = 0, so S = H P H' + R = 0, log S = -inf and
    v/S = 0/0: the log-likelihood emerges as NaN with nothing to say why.
    The design doc requires this case to be in the failure taxonomy.

    Series 0 has white sigma = 0 (so R = 0) and fails; series 1 has white
    sigma = 1 and must be untouched -- the verdict is (B,)-shaped, never a
    scalar for the batch and never an exception that takes the stack down.

    Bug this catches: an unguarded division by S, and a guard that condemns the
    whole batch when one series degenerates.
    """
    spec = ProcessSpec((_term("white"), _term("matern12")))
    ss = StateSpace.from_spec(spec)
    assert tuple(term.kind for term in spec.terms) == ("matern12", "white")
    theta = np.array([[1.0, 5.0, 0.0], [1.0, 5.0, 1.0]])
    t = np.array([0.0, 0.0, 1.0])
    y = np.array([[0.5, 0.5, -0.3], [0.5, 0.5, -0.3]])
    mask = np.ones_like(y, dtype=bool)

    engine = KalmanEngine()
    result = engine.score(ss, theta, y, mask, t, design=None)

    assert np.isnan(result.loglik[0])
    assert result.outcome[0] == Outcome.NONFINITE_OBJECTIVE.code
    # Failed series carry NaN, not -inf: -inf is a finite-looking sentinel.
    assert not np.isneginf(result.loglik[0])

    assert np.isfinite(result.loglik[1])
    assert result.outcome[1] == Outcome.OK.code
    solo = engine.score(ss, theta[1:], y[1:], mask[1:], t, design=None)
    assert result.loglik[1] == pytest.approx(solo.loglik[0], rel=1e-13)


def test_all_masked_series_scores_nan_not_zero():
    """A series with no observations scores NaN and INSUFFICIENT_DATA.

    An empty product gives loglik = -0.0, which is HIGHER than any real fit, so
    an untagged all-masked series propagates into the selection layer as the
    best candidate everywhere it occurs -- permanent ice, land, a dead sensor.

    Bug this catches: returning -0.0 with no outcome tag. Also pins NaN rather
    than -inf, which would rank last instead of first but is still a
    finite-looking sentinel that survives some consumers' checks.
    """
    spec = ProcessSpec((_term("matern12"),))
    ss = StateSpace.from_spec(spec)
    theta = np.array([[1.0, 3.0], [1.0, 3.0]])
    t = np.arange(9.0)
    rng = np.random.default_rng(4)
    y = rng.standard_normal((2, 9))
    mask = np.ones((2, 9), dtype=bool)
    mask[0] = False

    result = KalmanEngine().score(ss, theta, y, mask, t, design=None)

    assert result.n_used[0] == 0
    assert np.isnan(result.loglik[0])
    assert not np.isneginf(result.loglik[0])
    assert result.outcome[0] == Outcome.INSUFFICIENT_DATA.code

    assert result.n_used[1] == 9
    assert np.isfinite(result.loglik[1])
    assert result.outcome[1] == Outcome.OK.code


def test_normal_equations_match_the_gls_cross_products():
    """The accumulator is [y|X]' Sigma^-1 [y|X], every block of it.

    Expected values determined independently: Sigma is built from the analytic
    ACVF and inverted densely, then the three blocks are formed directly. The
    filter never forms Sigma, so this checks the innovations whitening itself --
    Sigma = L^-1 D L^-T with unit-lower-triangular L means
    z' Sigma^-1 w = sum_i e_z(i) e_w(i) / S_i, which is exactly what the loop
    accumulates.

    Bug this catches: running the design columns through a state initialised
    from the data rather than from zero, filtering X with a different gain than
    y, or transposing the y-X block. Every test that passes `design=None`
    leaves this whole branch unexercised, so without it `_augment`'s
    concatenation and `_rank` ship untested.
    """
    spec = ProcessSpec((_term("matern32"),))
    ss = StateSpace.from_spec(spec)
    theta = np.array([[1.1, 2.5]])
    t = np.arange(16.0)
    cov = _covariance(ss, theta, t)
    rng = np.random.default_rng(8)
    y = rng.multivariate_normal(np.zeros(t.size), cov)[None, :]
    design = np.column_stack([np.ones(16), t / 16.0, np.sin(t / 3.0)])

    result = KalmanEngine().score(
        ss, theta, y, np.ones_like(y, dtype=bool), t, design=design
    )

    cov_inv = np.linalg.inv(cov)
    aug = np.column_stack([y[0], design])
    expected = aug.T @ cov_inv @ aug
    assert result.normal_equations.shape == (1, 4, 4)
    np.testing.assert_allclose(result.normal_equations[0], expected, rtol=1e-9, atol=0)
    assert result.rank_x[0] == 3
    # loglik stays the y-only Gaussian density; GLS profiling is Task 8's job.
    assert result.loglik[0] == pytest.approx(mvn_loglik(y[0], cov), abs=1e-9)


def test_per_series_design_matches_a_shared_design():
    """A (B, N, k) design broadcast of a (N, k) design gives identical results.

    Bug this catches: the `ndim == 3` branch of `_augment` mis-ordering its axes
    -- it is unreachable from every design=None test, and a (B, N, k) array
    concatenated on the wrong axis silently produces a different, plausible
    accumulator.
    """
    spec = ProcessSpec((_term("matern12"),))
    ss = StateSpace.from_spec(spec)
    theta = np.array([[1.0, 3.0], [0.6, 5.0]])
    t = np.arange(14.0)
    rng = np.random.default_rng(9)
    y = rng.standard_normal((2, 14))
    mask = np.ones((2, 14), dtype=bool)
    shared = np.column_stack([np.ones(14), t / 14.0])
    per_series = np.broadcast_to(shared, (2, 14, 2)).copy()

    engine = KalmanEngine()
    a = engine.score(ss, theta, y, mask, t, design=shared)
    b = engine.score(ss, theta, y, mask, t, design=per_series)
    np.testing.assert_allclose(
        a.normal_equations, b.normal_equations, rtol=1e-14, atol=0
    )

    # And a genuinely per-series design must NOT match the shared one, or this
    # test would pass on an implementation that ignores the third axis entirely.
    varied = per_series.copy()
    varied[1, :, 1] = np.cos(t)
    c = engine.score(ss, theta, y, mask, t, design=varied)
    np.testing.assert_allclose(
        c.normal_equations[0], a.normal_equations[0], rtol=1e-14, atol=0
    )
    assert not np.allclose(c.normal_equations[1], a.normal_equations[1])


def test_rank_x_drops_when_a_column_loses_all_support_behind_a_gap():
    """Effective rank is per series: a gap can delete a column's entire support.

    A globally full-rank X is still singular for a series whose gap removes
    every row where a column is non-zero -- an offset epoch inside a seasonal
    dropout is the ordinary case, not an exotic one.

    Bug this catches: reporting the batch-level rank of X instead of the rank
    of the accumulated X' Sigma^-1 X per series, which lets Task 8's GLS solve
    a singular system and label the result converged.
    """
    spec = ProcessSpec((_term("matern12"),))
    ss = StateSpace.from_spec(spec)
    theta = np.array([[1.0, 4.0], [1.0, 4.0]])
    t = np.arange(12.0)
    rng = np.random.default_rng(10)
    y = rng.standard_normal((2, 12))
    step = np.zeros(12)
    step[[4, 5]] = 1.0
    design = np.column_stack([np.ones(12), step])

    mask = np.ones((2, 12), dtype=bool)
    mask[1, [4, 5]] = False  # series 1 loses every row supporting column 1

    result = KalmanEngine().score(ss, theta, y, mask, t, design=design)
    assert result.rank_x.tolist() == [2, 1]
    # The dead column's whole Gram row is exactly zero, not merely small.
    assert result.normal_equations[1, 2, 2] == 0.0


def test_rank_x_detects_a_duplicated_column():
    """A repeated design column is rank deficient however well conditioned Sigma is.

    Bug this catches: a rank routine that counts columns, or one whose tolerance
    is so tight that the exactly-zero second singular value of a duplicated
    column is still counted (floating-point noise puts it at ~1e-16 of the
    leading value, not at 0).
    """
    spec = ProcessSpec((_term("matern12"),))
    ss = StateSpace.from_spec(spec)
    theta = np.array([[1.0, 4.0]])
    t = np.arange(15.0)
    rng = np.random.default_rng(12)
    y = rng.standard_normal((1, 15))
    col = np.sin(t / 4.0) + 2.0
    design = np.column_stack([col, np.ones(15), col])

    result = KalmanEngine().score(
        ss, theta, y, np.ones_like(y, dtype=bool), t, design=design
    )
    assert result.rank_x.tolist() == [2]


def test_single_epoch_series_scores_from_the_stationary_covariance():
    """One observation is a valid series: no interval, so no F or Q at all.

    Expected value determined independently: with a single point Sigma is the
    1x1 matrix k(0) = sigma^2 + R, so the log-likelihood is
    -0.5*(log(2 pi) + log k(0) + y^2 / k(0)).

    Bug this catches: an index map built over zero intervals that still gets
    indexed, or a `np.clip(..., 0, -1)` on an empty step array -- N = 1 is what
    a series reduced to a single valid sample by masking looks like, which is
    ordinary at the edge of a sea-ice record.
    """
    spec = ProcessSpec((_term("white"), _term("matern12")))
    ss = StateSpace.from_spec(spec)
    theta = np.array([[1.5, 4.0, 0.5]])  # matern12 sigma, rho; white sigma
    t = np.array([2.0])
    y = np.array([[0.75]])

    result = KalmanEngine().score(
        ss, theta, y, np.ones_like(y, dtype=bool), t, design=None
    )
    k0 = 1.5**2 + 0.5**2
    expected = -0.5 * (np.log(2 * np.pi) + np.log(k0) + 0.75**2 / k0)
    assert result.n_used[0] == 1
    assert result.loglik[0] == pytest.approx(expected, abs=1e-13)
    assert result.outcome[0] == Outcome.OK.code


@pytest.mark.parametrize(
    "bad_design, match",
    [
        (np.zeros((5,)), "must be"),
        (np.zeros((2, 5, 3, 1)), "must be"),
        (np.zeros((4, 3)), "does not match"),
        (np.zeros((3, 5, 2)), "does not match"),
    ],
)
def test_design_with_the_wrong_shape_is_refused(bad_design, match):
    """A misshaped design raises rather than broadcasting into nonsense.

    Bug this catches: a (k, N) design silently transposed by broadcasting, or a
    per-series design whose batch axis disagrees with y -- both of which would
    produce a plausible accumulator built from the wrong columns, and neither
    of which any oracle downstream would notice.
    """
    spec = ProcessSpec((_term("matern12"),))
    ss = StateSpace.from_spec(spec)
    theta = np.array([[1.0, 3.0], [1.0, 3.0]])
    t = np.arange(5.0)
    y = np.zeros((2, 5))
    with pytest.raises(ValueError, match=match):
        KalmanEngine().score(
            ss, theta, y, np.ones_like(y, dtype=bool), t, design=bad_design
        )


def test_kalman_engine_satisfies_the_engine_protocol():
    """KalmanEngine is an Engine at runtime, checked with isinstance.

    `issubclass` RAISES on this protocol -- `engine_id` is a non-method member,
    and `runtime_checkable` supports only isinstance for those. Pinned here so
    the next author does not "fix" this test into a TypeError.

    Bug this catches: an engine that drops `engine_id` or renames `score`,
    which the driver would only discover at call time.
    """
    assert isinstance(KalmanEngine(), Engine)
    with pytest.raises(TypeError):
        issubclass(KalmanEngine, Engine)  # type: ignore[misc]


def test_scored_result_is_frozen():
    """A score cannot be mutated after it is tagged.

    Bug this catches: a consumer rewriting `loglik` or `engine` in place, which
    would defeat the comparability guard the tags exist for.
    """
    spec = ProcessSpec((_term("matern12"),))
    ss = StateSpace.from_spec(spec)
    t = np.arange(5.0)
    y = np.zeros((1, 5))
    result = KalmanEngine().score(
        ss, np.array([[1.0, 2.0]]), y, np.ones_like(y, dtype=bool), t, design=None
    )
    assert isinstance(result, ScoredResult)
    with pytest.raises(AttributeError):
        # mypy sees the violation statically; the point is that it also fails
        # at runtime, for consumers that are not type checked.
        result.engine = EngineId.WHITTLE  # type: ignore[misc]
