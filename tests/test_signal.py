"""Tests for `metamer.core.signal`.

Each test states, in its docstring, the bug it would catch and (where the
expected value isn't obvious from the term's definition) how that value was
derived independently of the implementation.
"""

import numpy as np
import pytest

from metamer.core.engines.kalman import KalmanEngine
from metamer.core.signal import (
    Accel,
    Annual,
    Constant,
    DesignInfo,
    ExpDecay,
    Harmonic,
    LogDecay,
    Offset,
    RateChange,
    Regressor,
    SemiAnnual,
    SignalSpec,
    Trend,
)


def _present(t, batch=1):
    """An all-present (B, N) mask for the tests whose subject is X itself.

    `design_info` requires a mask because its derived quantities are per
    series; where a test is about the FULL design, the all-present mask is
    what makes X_r = X, and the single-series results are read at index 0.
    """
    return np.ones((batch, np.size(t)), dtype=bool)


# --- Original acceptance-criteria tests (task-7-brief.md Step 1) -----------


def test_polynomial_columns_are_powers_of_centred_time():
    """constant/trend/accel are t^0, t^1, t^2/2 about the record mean.

    Expected value determined independently: centring at t.mean() is stated in
    the docstring, so for t = [0,1,2] the trend column is [-1,0,1] and the
    acceleration column is [0.5,0,0.5].
    """
    t = np.array([0.0, 1.0, 2.0])
    x, _ = SignalSpec([Constant(), Trend(), Accel()]).design_matrix(t)
    np.testing.assert_allclose(x[:, 0], [1.0, 1.0, 1.0])
    np.testing.assert_allclose(x[:, 1], [-1.0, 0.0, 1.0])
    np.testing.assert_allclose(x[:, 2], [0.5, 0.0, 0.5])


def test_harmonic_columns_are_cosine_then_sine():
    """A harmonic contributes cos then sin at 2*pi*t/period.

    Bug this catches: swapping the column order, which silently swaps the
    reported amplitude and phase of the annual cycle.
    """
    t = np.array([0.0, 0.25, 0.5])
    x, _ = SignalSpec([Annual(period=1.0)]).design_matrix(t)
    np.testing.assert_allclose(x[:, 0], np.cos(2 * np.pi * t), atol=1e-14)
    np.testing.assert_allclose(x[:, 1], np.sin(2 * np.pi * t), atol=1e-14)


def test_offset_at_first_sample_is_all_ones():
    """An offset at or before t[0] steps the entire record.

    Bug this catches: a strict `>` comparison, which would make an offset at
    the first epoch an all-zeros column indistinguishable from a no-op.
    """
    t = np.arange(5.0)
    x, _ = SignalSpec([Offset(epoch=0.0)]).design_matrix(t)
    np.testing.assert_allclose(x[:, 0], np.ones(5))


def test_offset_after_last_sample_is_rank_deficient():
    """An out-of-record offset produces a zero column and drops the rank.

    Bug this catches: letting an all-zero column through, where log|X'S^-1X|
    is undefined and the fit returns NaN rather than a named failure.
    """
    t = np.arange(5.0)
    x, rank = SignalSpec([Constant(), Offset(epoch=99.0)]).design_matrix(t)
    np.testing.assert_allclose(x[:, 1], np.zeros(5))
    assert rank == 1


def test_rate_change_with_no_samples_after_the_break_is_zero():
    """A piecewise rate change beyond the record contributes nothing.

    Bug this catches: producing negative ramp values before the break, which
    would silently redefine the term as a two-sided hinge.
    """
    t = np.arange(5.0)
    x, _ = SignalSpec([RateChange(epoch=10.0)]).design_matrix(t)
    np.testing.assert_allclose(x[:, 0], np.zeros(5))


def test_nonlinear_terms_are_classified_and_refused():
    """Nonlinear terms exist in the taxonomy but are not implemented.

    Bug this catches: omitting the taxonomy entirely, which means retrofitting
    the linear/nonlinear dispatch later requires rewriting the fit driver.
    """
    spec = SignalSpec([Constant(), ExpDecay(epoch=0.0, tau=1.0)])
    assert spec.is_linear is False
    with pytest.raises(NotImplementedError, match="nonlinear"):
        spec.design_matrix(np.arange(5.0))


def test_semiannual_period_is_half_the_annual_period():
    """SemiAnnual defaults to half of Annual's default period.

    Expected value determined independently: 'semiannual' means twice per
    year, so period = 0.5 yr when the axis is in years.
    """
    assert SemiAnnual().period == pytest.approx(Annual().period / 2.0)


# --- Correction 4: the two rank tolerances disagree -------------------------


def test_signal_rank_and_gram_rank_disagree_at_cond_1e7():
    """SignalSpec.rank (X-thresholded) and the engine's Gram rank disagree.

    Bug this catches: conflating `X_RANK_RTOL` (thresholds X's own singular
    values) with the engine's `_RANK_RTOL` (thresholds the Gram, whose
    singular values are X's squared) -- a design `SignalSpec.rank` calls full
    rank could be silently downgraded by the engine, exactly the scenario
    Task 8's `check_design` must not be blind to.

    Expected values determined independently: X is built by SVD synthesis
    with singular values fixed at [1e7, 1e4, 1.0] (cond(X) = 1e7). At
    X_RANK_RTOL = 1e-10 all three singular values clear `1e-10 * s_max`
    (ratios 1, 1e-3, 1e-7, all above 1e-10) so SignalSpec.rank = 3. The Gram's
    singular values are the squares [1e14, 1e8, 1.0]; at the engine's
    GRAM_RANK_RTOL = 1e-10 the ratio for the third is (1e-7)**2 = 1e-14 <
    1e-10, so it is dropped and the Gram rank is 2. The Gram rank is computed
    by calling the REAL `KalmanEngine._rank` (fix round 1: the first version
    of this test reimplemented the engine's threshold rule inline, which
    would keep passing if the engine's own rule ever changed -- the one thing
    this test exists to catch) rather than restated here, so this pins actual
    engine behavior, not a copy of it.
    """
    rng = np.random.default_rng(20260805)
    u, _ = np.linalg.qr(rng.standard_normal((10, 3)))
    v, _ = np.linalg.qr(rng.standard_normal((3, 3)))
    singular_values = np.array([1e7, 1e4, 1.0])
    x = u @ np.diag(singular_values) @ v.T

    assert SignalSpec.rank(x) == 3

    gram_batch = (x.T @ x)[None, :, :]  # KalmanEngine._rank expects (B, k, k)
    gram_rank, gram_ok = KalmanEngine._rank(gram_batch)
    assert bool(gram_ok[0])
    assert int(gram_rank[0]) == 2


# --- Correction 5: zero columns vs zero rows are different failures --------


def test_design_info_zero_columns_is_not_deficient():
    """An empty SignalSpec (no terms) is trivially not rank-deficient.

    Bug this catches: a `matrix.size == 0` guard that also fires here (zero
    columns makes `matrix.size` zero regardless of row count) and happens to
    give the right answer by accident for this case -- distinguished from the
    zero-*rows* case below, where the same guard gives the WRONG answer.
    """
    t = np.arange(5.0)
    info = SignalSpec([]).design_info(t, _present(t))
    assert info.n_beta == 0
    assert info.rank[0] == 0
    assert info.gram_logdet[0] == 0.0
    assert info.is_deficient[0] is np.False_


def test_design_info_empty_time_axis_is_deficient():
    """A zero-length time axis cannot identify any column: always deficient.

    Bug this catches: `matrix.size == 0` (true here too, since matrix is
    shape (0, 1)) returning a FINITE gram_logdet = 0.0 and rank = 0 with
    is_deficient computed as `bool(matrix.size and ...)` -- `matrix.size` is
    0 (falsy) so `is_deficient` comes out False, and Task 8's planned gate
    `if design.is_deficient or not np.isfinite(design.gram_logdet)` would
    PASS a design with zero observations. Correct behavior: rank stays 0,
    n_beta is 1, so `rank < n_beta` must be True.
    """
    t = np.array([])
    info = SignalSpec([Constant()]).design_info(t, _present(t))
    assert info.n_beta == 1
    assert info.rank[0] == 0
    assert info.is_deficient[0] is np.True_
    assert not np.isfinite(info.gram_logdet[0])


# --- Task 8 correction C: DesignInfo is per series, computed from the mask --


def test_design_info_derived_quantities_are_per_series_from_the_mask():
    """rank, gram_logdet and condition_number all describe X RESTRICTED by the mask.

    The design that actually enters `X' Sigma^-1 X` for a series is X over
    that series' unmasked rows, so every theta-free quantity Harville's REML
    form needs -- `rank(X_r)` and `log|X_r'X_r|` -- belongs to X_r, not to X.
    All three expected values below come from an explicit `matrix_rank`,
    `slogdet` and `cond` on each restricted matrix, sharing no code with
    `design_info`.

    Bug this catches: computing these once for the batch and broadcasting. It
    is theta-INDEPENDENT, so it cancels in every delta-IC and no differential
    test can see it -- while the stored absolute REML log-likelihood is wrong
    for every series with a gap, which is every real series. Series 1 below
    keeps the offset's support and series 2 loses it entirely, so a batch-level
    answer is wrong for at least one of them whichever value it picks.
    """
    t = np.arange(20.0)
    spec = SignalSpec([Constant(), Trend(), Offset(epoch=15.0)])
    mask = np.ones((3, t.size), dtype=bool)
    mask[1, 5:10] = False
    mask[2, 15:] = False

    info = spec.design_info(t, mask)

    assert info.rank.shape == (3,)
    assert info.gram_logdet.shape == (3,)
    assert info.condition_number.shape == (3,)
    assert info.is_deficient.shape == (3,)
    np.testing.assert_array_equal(info.n_rows, [20, 15, 15])

    for series in (0, 1):
        rows = info.matrix[mask[series]]
        _, expected_logdet = np.linalg.slogdet(rows.T @ rows)
        assert info.rank[series] == int(np.linalg.matrix_rank(rows))
        assert info.gram_logdet[series] == pytest.approx(expected_logdet, rel=1e-10)
        assert info.condition_number[series] == pytest.approx(
            float(np.linalg.cond(rows)), rel=1e-10
        )
    assert info.gram_logdet[0] != pytest.approx(info.gram_logdet[1], abs=1e-6)

    # Series 2 loses every row supporting the offset: exactly singular.
    assert info.rank[2] == 2
    assert info.gram_logdet[2] == -np.inf
    assert info.condition_number[2] == np.inf
    np.testing.assert_array_equal(info.is_deficient, [False, False, True])


def test_design_info_rejects_a_mask_whose_time_axis_disagrees():
    """A mask of the wrong width is refused, not broadcast into a wrong answer.

    Bug this catches: accepting a (B, N') mask and silently zero-padding or
    broadcasting it, which produces a plausible per-series design for rows that
    do not exist.
    """
    t = np.arange(10.0)
    spec = SignalSpec([Constant(), Trend()])
    with pytest.raises(ValueError, match="mask"):
        spec.design_info(t, np.ones((2, 9), dtype=bool))
    with pytest.raises(ValueError, match="mask"):
        spec.design_info(t, np.ones(10, dtype=bool))


# --- Correction 6: is_deficient is batch-level, not per-series -------------


def test_shared_design_full_rank_but_per_series_restricted_deficient():
    """A shared design can be full rank while a masked series' rows are not.

    Bug this catches: treating `SignalSpec.design_info`'s batch-level rank as
    sufficient for a per-series verdict. Measured case: [Constant, Trend,
    Offset(15)] over t = 0..19 is full rank (3/3) globally, but a series
    masked from t = 15 onward only contributes rows t = 0..14, over which the
    Offset(15) column is identically zero -- restricted rank 2/3. This is
    exactly the design doc's "effective rank is per series" claim (SS5.2),
    and `SignalSpec` alone cannot see it because it never sees a mask.
    """
    t = np.arange(20.0)
    spec = SignalSpec([Constant(), Trend(), Offset(epoch=15.0)])
    info = spec.design_info(t, _present(t))
    assert info.rank[0] == 3
    assert info.is_deficient[0] is np.False_

    mask = t < 15.0
    restricted = info.matrix[mask]
    assert SignalSpec.rank(restricted) == 2


# --- Correction 7: identifiable-but-barely-so slips past rank -------------


def test_offset_at_last_epoch_is_not_deficient_but_is_ill_conditioned():
    """A single-sample offset is full rank but numerically fragile.

    Bug this catches: reporting only `is_deficient`, which is False here and
    gives no signal that the offset coefficient is estimated from exactly one
    observation -- the design doc's "offset epoch at a series boundary"
    example (SS5.2). `condition_number` is what distinguishes this from a
    healthy full-rank design.

    Expected condition number derived analytically (fix round 1: the original
    version of this test pinned a value obtained by running the code, at a
    tolerance tight enough to hide a difference in the last three digits from
    the true closed form -- caught in review). For t = arange(5.0) and
    Offset(epoch=4.0), X = [ones(5), offset] with offset = [0,0,0,0,1], so
    X'X = [[5, 1], [1, 1]] (col1.col1 = 5, col1.col2 = col2.col1 =
    sum(offset) = 1, col2.col2 = sum(offset^2) = 1). Its eigenvalues solve
    lambda^2 - 6*lambda + 4 = 0 (trace 6, det 5*1 - 1*1 = 4), giving
    lambda = 3 +/- sqrt(5). X's singular values are the square roots of
    X'X's eigenvalues, so cond(X) = sqrt((3+sqrt5)/(3-sqrt5)), which
    simplifies -- since (3+sqrt5)(3-sqrt5) = 9-5 = 4, so
    (3+sqrt5)/(3-sqrt5) = ((3+sqrt5)/2)^2 -- to exactly (3+sqrt5)/2 = phi^2,
    the golden ratio squared.
    """
    t = np.arange(5.0)
    spec = SignalSpec([Constant(), Offset(epoch=4.0)])
    info = spec.design_info(t, _present(t))
    assert info.rank[0] == 2
    assert info.is_deficient[0] is np.False_
    expected_condition_number = (3.0 + np.sqrt(5.0)) / 2.0
    assert info.condition_number[0] == pytest.approx(
        expected_condition_number, rel=1e-12
    )


def test_offset_after_last_sample_condition_number_is_infinite():
    """An exactly-singular design (all-zero column) has infinite condition number.

    Bug this catches: computing `condition_number` from the Gram or from a
    formula that divides by a zero singular value without guarding, which
    raises or silently returns NaN instead of the well-defined +inf a
    singular X has.
    """
    t = np.arange(5.0)
    info = SignalSpec([Constant(), Offset(epoch=99.0)]).design_info(t, _present(t))
    assert info.condition_number[0] == float("inf")


# --- Correction 3: the time-axis unit contract ------------------------------


def test_decimal_years_vs_seconds_since_1970_condition_number():
    """The stated time-axis contract (decimal years) is not decorative.

    Bug this catches: silently accepting any numeric time axis. Measured
    independently on a 20-year monthly record with [Constant, Trend, Accel,
    Annual, SemiAnnual] (task-7-report.md records the exact script and
    output): decimal years gives cond(X) ~ 3.4e1 and rank 7/7; the identical
    record in seconds since 1970 (period left un-converted, the ordinary way
    this contract gets violated) gives cond(X) > 1e30 and rank 2 of 7 --
    pinned exactly (fix round 1: the original version only asserted
    `rank < 7`, which a broken column that merely dropped rank by one, to 6,
    would also have passed). The condition-number bounds stay coarse, since
    the precise value is sensitive to the exact epoch chosen (see
    task-7-report.md for what was actually measured), but the rank collapse
    itself is deterministic for this fixed t and is pinned exactly.
    """
    n = 20 * 12
    t_years = 2000.0 + np.arange(n) / 12.0
    spec = SignalSpec([Constant(), Trend(), Accel(), Annual(), SemiAnnual()])
    years_info = spec.design_info(t_years, _present(t_years))
    assert years_info.rank[0] == 7
    assert years_info.condition_number[0] < 1e3

    seconds_per_year = 365.25 * 86400
    t_seconds = (t_years - 1970.0) * seconds_per_year
    seconds_info = spec.design_info(t_seconds, _present(t_seconds))
    assert seconds_info.rank[0] == 2
    assert seconds_info.condition_number[0] > 1e20


# --- Correction 8: frozen dataclasses holding unhashable payloads ----------


def test_regressor_equality_and_hash_do_not_touch_array_truth_value():
    """Regressor equality/hash must not trigger numpy's ambiguous-truth-value error.

    Bug this catches: the default dataclass `eq=True`, which compares
    `self.values == other.values` -- an elementwise array, not a bool -- and
    raises `ValueError: truth value of an array is ambiguous` on `==`, and
    raises `TypeError: unhashable type: 'numpy.ndarray'` on `hash()`.
    """
    a = Regressor(np.ones(5))
    b = Regressor(np.ones(5))
    assert (a == b) is False  # eq=False: identity comparison, distinct objects
    assert a == a  # identity comparison: same object is equal to itself
    assert isinstance(hash(a), int)


def test_regressor_columns_returns_supplied_values_as_one_column():
    """Regressor.columns returns the caller's values, reshaped to (n, 1).

    Bug this catches: transposing or flattening incorrectly, which would
    silently misalign a per-point regressor against the time axis.
    """
    values = np.array([1.0, 2.0, 3.0])
    t = np.arange(3.0)
    x = Regressor(values).columns(t)
    np.testing.assert_allclose(x, [[1.0], [2.0], [3.0]])


def test_regressor_length_mismatch_raises():
    """A regressor whose length disagrees with the time axis is rejected loudly.

    Bug this catches: silently broadcasting or truncating a mismatched
    regressor instead of raising, which would misalign it against unrelated
    epochs without any error.
    """
    with pytest.raises(ValueError, match="length"):
        Regressor(np.array([1.0, 2.0])).columns(np.arange(3.0))


def test_signal_spec_is_hashable():
    """SignalSpec must be hashable for Task 16's three-hash machinery.

    Bug this catches: `terms` stored as a `list` (unhashable) rather than a
    `tuple`, which raises `TypeError: unhashable type: 'list'`.
    """
    spec = SignalSpec([Constant(), Trend()])
    assert isinstance(hash(spec), int)
    assert SignalSpec([Constant(), Trend()]) == spec
    assert hash(SignalSpec([Constant(), Trend()])) == hash(spec)


def test_design_info_equality_does_not_raise_on_its_array_field():
    """DesignInfo also carries a numpy array field (matrix); same defect class as Regressor.

    Bug this catches: the default dataclass `eq=True` comparing `.matrix`
    elementwise and raising `ValueError: truth value of an array is
    ambiguous`, the identical failure Correction 8 fixed for `Regressor`.
    Not named explicitly in the brief's Correction 8 example, but the same
    defect category on the same kind of field; fixed and pinned here so it
    does not resurface as a fresh instance of the bug Correction 8 describes.
    """
    t = np.arange(5.0)
    info = SignalSpec([Constant()]).design_info(t, _present(t))
    other = SignalSpec([Constant()]).design_info(t, _present(t))
    assert (info == other) is False  # eq=False: identity comparison
    assert isinstance(hash(info), int)


# --- Correction 9: missing / weak coverage -----------------------------


def test_rate_change_nonzero_hinge_hand_computed():
    """RateChange produces a real ramp, not just the all-zeros degenerate case.

    Bug this catches: `return np.zeros_like(t)` passes every other test in
    this suite (only the all-zeros-beyond-the-record case was previously
    tested) but fails this one. Expected values hand-computed independently:
    max(t - 2, 0) for t = [0,1,2,3,4] is [0,0,0,1,2].
    """
    t = np.arange(5.0)
    x = RateChange(epoch=2.0).columns(t)
    np.testing.assert_allclose(x[:, 0], [0.0, 0.0, 0.0, 1.0, 2.0])


def test_rate_change_is_continuous_and_zero_at_epoch():
    """A rate change is a one-sided hinge: exactly 0 at t == epoch, continuous.

    Bug this catches: an off-by-one epoch comparison that would make the
    ramp start one sample early or late, which is invisible from the
    all-zeros or the general hand-computed test alone since both use whole
    integers where "at" and "just after" coincide with sampling.
    """
    t = np.array([1.5, 2.0, 2.5])
    x = RateChange(epoch=2.0).columns(t)
    np.testing.assert_allclose(x[:, 0], [0.0, 0.0, 0.5])


def test_offset_pinned_at_exactly_epoch_non_boundary():
    """Offset is an inclusive step: exactly 1 at t == epoch, at an interior epoch.

    Bug this catches: the existing first-sample and after-last-sample tests
    both pin boundary behavior; neither would catch a comparison bug that
    only misfires for an interior epoch (e.g. `t > epoch` instead of `t >=
    epoch`, which happens to still give the right column at the very first
    sample if epoch equals t[0] exactly, but not at an interior epoch tested
    independently here).
    """
    t = np.arange(5.0)
    x = Offset(epoch=2.0).columns(t)
    np.testing.assert_allclose(x[:, 0], [0.0, 0.0, 1.0, 1.0, 1.0])


def test_log_decay_is_constructible_and_raises_from_every_entry_point():
    """LogDecay exists, is constructible, and is refused at every code path.

    Bug this catches: `LogDecay` named in the acceptance criteria but never
    imported or exercised at all -- this project's own audit found it
    entirely untested. Also checks the "un-bypassable" requirement: raising
    from `columns` alone would not stop `design_info` or `n_beta`, which
    build the matrix a different way.
    """
    term = LogDecay(epoch=0.0, tau=3.0)
    assert term.epoch == 0.0
    assert term.tau == 3.0
    assert term.linear is False

    spec = SignalSpec([Constant(), term])
    t = np.arange(5.0)
    with pytest.raises(NotImplementedError, match="nonlinear"):
        term.columns(t)
    with pytest.raises(NotImplementedError, match="nonlinear"):
        spec.design_matrix(t)
    with pytest.raises(NotImplementedError, match="nonlinear"):
        spec.design_info(t, _present(t))
    with pytest.raises(NotImplementedError, match="nonlinear"):
        spec.n_beta(t)


def test_exp_decay_carries_a_timescale():
    """ExpDecay's nonlinear parameter (tau) is present in the constructor.

    Bug this catches: shipping ExpDecay with only `epoch`, which would force
    Phase 4 (joint optimization over the timescale) to change the
    constructor signature -- exactly the retrofit this task exists to avoid.
    """
    term = ExpDecay(epoch=5.0, tau=2.5)
    assert term.epoch == 5.0
    assert term.tau == 2.5
    with pytest.raises(NotImplementedError, match="nonlinear"):
        term.columns(np.arange(3.0))


def test_harmonic_at_period_other_than_one():
    """A generic Harmonic honors an arbitrary period, not just P = 1.0.

    Bug this catches: dividing by a hardcoded 1.0 or omitting the `/period`
    divisor entirely, which is invisible at P = 1.0 (the only period the
    original suite tested) since dividing by 1 is a no-op.

    Expected values hand-computed independently: period = 2.0, so phase =
    pi * t. At t = [0, 0.5, 1.0], phase = [0, pi/2, pi], giving cos =
    [1, 0, -1] and sin = [0, 1, 0].
    """
    t = np.array([0.0, 0.5, 1.0])
    x = Harmonic(period=2.0).columns(t)
    np.testing.assert_allclose(x[:, 0], [1.0, 0.0, -1.0], atol=1e-14)
    np.testing.assert_allclose(x[:, 1], [0.0, 1.0, 0.0], atol=1e-14)


def test_semiannual_columns_at_specific_times():
    """SemiAnnual's actual columns are checked, not just its default period.

    Bug this catches: the original suite only pinned `SemiAnnual().period`;
    a broken `columns` override (or an accidentally-inherited wrong period at
    call time) would pass that test and still be wrong. Expected values
    hand-computed independently: period = 0.5, so phase = 4*pi*t. At t =
    [0, 0.125, 0.25], phase = [0, pi/2, pi], giving cos = [1, 0, -1] and sin =
    [0, 1, 0].
    """
    t = np.array([0.0, 0.125, 0.25])
    x = SemiAnnual().columns(t)
    np.testing.assert_allclose(x[:, 0], [1.0, 0.0, -1.0], atol=1e-14)
    np.testing.assert_allclose(x[:, 1], [0.0, 1.0, 0.0], atol=1e-14)


def test_design_info_gram_logdet_matches_hand_computation():
    """gram_logdet is log|X'X| for a simple, hand-checkable design.

    Bug this catches: `DesignInfo`, `design_info`, and `gram_logdet` had zero
    tests despite Task 8 consuming all of them. Expected value hand-computed
    independently: for t = [0,1,2], X = [Constant, Trend] is
    [[1,-1],[1,0],[1,1]], so X'X = [[3,0],[0,2]] (cross term is
    sum(trend) = 0), det = 6, log(6) = 1.791759469228055.
    """
    t = np.array([0.0, 1.0, 2.0])
    info = SignalSpec([Constant(), Trend()]).design_info(t, _present(t))
    assert info.gram_logdet[0] == pytest.approx(np.log(6.0), rel=1e-12)
    assert info.rank[0] == 2
    assert info.n_beta == 2
    assert info.is_deficient[0] is np.False_
    assert info.per_point is False


def test_design_info_n_beta_counts_columns_not_rank():
    """n_beta is the column count of the design, independent of its rank.

    Bug this catches: confusing n_beta with rank, which would make a
    rank-deficient design silently report the wrong number of parameters --
    exactly the "silent bug in concentrated-likelihood implementations" the
    design doc warns about for k-counting.
    """
    t = np.arange(5.0)
    info = SignalSpec([Constant(), Offset(epoch=99.0)]).design_info(t, _present(t))
    assert info.n_beta == 2
    assert info.rank[0] == 1


def test_design_info_per_point_field_defaults_false():
    """per_point defaults False; Task 8 branches on it to detect the SEAM widening.

    Bug this catches: a missing or mis-defaulted `per_point` field, which
    would make Task 8's shared-vs-per-point dispatch silently take the wrong
    branch for every ordinary (non-SEAM) design.
    """
    matrix = np.ones((3, 1))
    info = DesignInfo(
        matrix,
        rank=np.array([1]),
        gram_logdet=np.array([0.0]),
        condition_number=np.array([1.0]),
        n_rows=np.array([3]),
    )
    assert info.per_point is False
    assert info.batch == 1


# --- Fix round 1 (external review): Important 1-3 ---------------------------


def test_numerically_deficient_design_has_finite_gram_logdet():
    """A numerically (not exactly) deficient design has a FINITE gram_logdet.

    Bug this catches (Important 1): the pre-fix `design_info` docstring
    claimed `gram_logdet` is -inf for a rank-deficient design. That claim is
    false, and a caller (Task 8) gating on the -inf sentinel rather than on
    `is_deficient` would silently accept a deficient design whose Gram
    determinant merely happens to still be nonzero to float64 precision.

    Expected values determined independently: X is built by SVD synthesis
    with singular values fixed at [1, 1e-2, 1e-11]. At X_RANK_RTOL = 1e-10
    the ratio 1e-11/1 = 1e-11 is below tolerance, so rank = 2 of 3
    (deficient), but log|X'X| = 2*sum(log(s)) = 2*(log(1) + log(1e-2) +
    log(1e-11)) = -59.867..., a large negative but perfectly finite number,
    not -inf.
    """
    rng = np.random.default_rng(1)
    u, _ = np.linalg.qr(rng.standard_normal((3, 3)))
    v, _ = np.linalg.qr(rng.standard_normal((3, 3)))
    singular_values = np.array([1.0, 1e-2, 1e-11])
    x = u @ np.diag(singular_values) @ v.T
    expected_gram_logdet = 2.0 * np.sum(np.log(singular_values))

    t = np.arange(3.0)
    info = SignalSpec([Regressor(x[:, i]) for i in range(3)]).design_info(
        t, _present(t)
    )
    assert info.rank[0] == 2
    assert info.n_beta == 3
    assert info.is_deficient[0] is np.True_  # THE gate
    assert np.isfinite(info.gram_logdet[0])  # NOT -inf, despite being deficient
    assert info.gram_logdet[0] == pytest.approx(expected_gram_logdet, rel=1e-6)


def test_condition_number_infinite_for_more_columns_than_rows():
    """cond(X) is +inf when X is structurally singular (more columns than rows).

    Bug this catches (Important 2): `np.linalg.svdvals` on a "wide" (n < k)
    matrix returns only `min(n, k) = n` singular values -- the `k - n`
    structurally-zero ones simply never appear in that array -- so reading
    s_min from it alone computes a FINITE ratio and misses the singularity
    entirely. Before this fix, n=2, k=3 gave a finite `cond(X) ~ 2.0`, flatly
    contradicting `rank(2) < n_beta(3)` on the very same DesignInfo.

    Columns chosen independently of any rank computation (three arbitrary,
    non-proportional 2-vectors); the only fact this test relies on is
    n_rows=2 < n_cols=3, which alone forces rank <= 2 < 3 for ANY choice of
    columns.

    Checks `_condition_number` directly (the method Important 2 names) as
    well as `design_info`'s output (the actual production hot path, which
    computes the same answer via the batched `_diagnostics` route instead of
    calling `_condition_number` again, to avoid a second SVD -- Important 3):
    both must independently agree the design is infinitely conditioned.
    """
    x = np.array([[1.0, 3.0, 2.0], [2.0, 1.0, 5.0]])
    assert SignalSpec._condition_number(x) == float("inf")

    t = np.arange(2.0)
    spec = SignalSpec([Regressor(x[:, i]) for i in range(3)])
    info = spec.design_info(t, _present(t))
    assert info.n_beta == 3
    assert info.rank[0] == 2
    assert info.is_deficient[0] is np.True_
    assert info.condition_number[0] == float("inf")


def test_condition_number_direct_finite_and_zero_singular_value_cases():
    """`_condition_number`'s two non-structural branches, exercised directly.

    Bug this catches: `design_info` no longer calls `_condition_number` (it
    routes through `_restricted_singular_values` and `_diagnostics`, which
    share one SVD across cond, log|X'X| and rank, Important 3),
    so without a direct test `_condition_number`'s ordinary finite-ratio
    return and its `values[-1] == 0.0` guard would be unreachable dead code --
    a correctly-fixed method nobody actually exercises. `np.eye(3)` has all
    singular values equal to 1, so cond = 1 exactly (an independently obvious
    fact, not derived from running the code); a column of zeros makes the
    smallest singular value exactly 0, hence cond = +inf.
    """
    assert SignalSpec._condition_number(np.eye(3)) == pytest.approx(1.0)

    x_with_zero_column = np.array([[1.0, 0.0], [1.0, 0.0], [1.0, 0.0]])
    assert SignalSpec._condition_number(x_with_zero_column) == float("inf")


def test_gram_logdet_accurate_at_cond_1e9_slogdet_route_fails():
    """gram_logdet stays accurate at cond(X) = 1e9; slogdet(X'X) does not.

    Bug this catches (Important 3): computing gram_logdet via `slogdet(X'X)`
    instead of `2 * sum(log(svdvals(X)))`. Forming the Gram squares the
    condition number (X'X's condition number is cond(X)^2 = 1e18, deep in
    float64's ~1e16 precision-loss regime), and `slogdet`'s LU factorization
    inherits that loss. At the fixed seed used here it does not merely lose a
    few digits: `np.linalg.slogdet` returns a NEGATIVE sign for this exactly
    positive-semidefinite Gram matrix -- which the pre-fix `design_info`
    (`float(logdet) if sign > 0 else float("-inf")`) would have turned into
    `gram_logdet = -inf`, misclassifying a design that is actually full rank
    (4 of 4, since s_min/s_max = 1e-9 clears X_RANK_RTOL = 1e-10) as exactly
    singular -- a far worse failure than an imprecise-but-finite number.

    Expected value determined independently, on paper, not by running the
    code under test: X is built by SVD synthesis with singular values fixed
    at [1e9, 1e6, 1e3, 1.0] (cond(X) = 1e9), so log|X'X| = 2 * sum(log(s)) =
    2 * (9 + 6 + 3 + 0) * ln(10) = 36 * ln(10) exactly -- X'X = V diag(s^2) V'
    is a similarity transform of diag(s^2), whose determinant is the product
    of the s_i^2 regardless of the orthogonal U, V used to build X.
    """
    rng = np.random.default_rng(1090)
    u, _ = np.linalg.qr(rng.standard_normal((20, 4)))
    v, _ = np.linalg.qr(rng.standard_normal((4, 4)))
    singular_values = np.array([1e9, 1e6, 1e3, 1.0])
    x = u @ np.diag(singular_values) @ v.T
    expected_gram_logdet = 36.0 * np.log(10.0)

    t = np.arange(20.0)
    info = SignalSpec([Regressor(x[:, i]) for i in range(4)]).design_info(
        t, _present(t)
    )
    assert info.rank[0] == 4
    assert info.is_deficient[0] is np.False_
    assert info.gram_logdet[0] == pytest.approx(expected_gram_logdet, rel=1e-6)

    # Confirm the slogdet route this fix replaces actually fails, deliberate
    # breakage evidence rather than a bare assertion: at this conditioning it
    # does not reproduce the analytic answer AND flips to a spurious negative
    # sign for a matrix that is genuinely positive semidefinite.
    sign, slogdet_value = np.linalg.slogdet(x.T @ x)
    assert not (sign > 0 and abs(slogdet_value - expected_gram_logdet) < 1.0)


# --------------------------------------------------------------------------
# Column-to-term mapping (Task 14: n_eff_trend needs to find the trend column)
# --------------------------------------------------------------------------


def test_design_info_names_the_term_behind_every_column():
    """`column_terms` labels each column with the term that produced it.

    Behaviour under test: the column-to-term mapping.
    Bug this catches: a mapping built from `len(terms)` rather than from each
    term's own column count. `Harmonic` contributes TWO columns (sine and
    cosine) while `Constant` contributes one, so a per-term mapping is off by
    one from `Annual` onward -- and silently, because the labels are still
    plausible strings in plausible positions.
    """
    t = np.arange(24.0) / 12.0
    spec = SignalSpec([Constant(), Trend(), Annual(), Accel()])
    info = spec.design_info(t, np.ones((1, t.size), dtype=bool))
    assert info.column_terms == ("Constant", "Trend", "Annual", "Annual", "Accel")
    assert len(info.column_terms) == info.n_beta


def test_design_info_locates_the_trend_column():
    """`trend_column` is the index of the Trend column, or None.

    Behaviour under test: the lookup `n_eff_trend` needs.
    Bug this catches: assuming the trend is column 1. It is column 1 only for
    the `[Constant, Trend, ...]` ordering a fixture happens to use; with
    `[Annual(), Trend()]` it is column 2, and `n_eff_trend` computed from the
    wrong column reports the effective sample size of a seasonal amplitude
    while calling it a trend.
    """
    t = np.arange(24.0) / 12.0
    mask = np.ones((1, t.size), dtype=bool)
    assert SignalSpec([Constant(), Trend()]).design_info(t, mask).trend_column == 1
    assert SignalSpec([Annual(), Trend()]).design_info(t, mask).trend_column == 2
    assert SignalSpec([Constant()]).design_info(t, mask).trend_column is None
    assert SignalSpec([]).design_info(t, mask).trend_column is None


def test_design_info_reports_the_white_noise_trend_variance_per_series():
    """`unit_variance_beta_var` is `(Xr' Xr)^-1` diagonal, per series.

    Behaviour under test: the white-noise reference variance `n_eff_trend`
    divides into. It is per series because the mask changes which rows enter.
    Expected value derived independently: for `[Constant]` on `n` unmasked
    rows, `X'X = n` so the diagonal is `1/n`.
    Bug this catches: computing it from the full design rather than the masked
    one, which for a half-masked series reports `1/n` where the truth is
    `2/n` -- an effective sample size wrong by exactly the mask fraction, in
    the flattering direction.
    """
    t = np.arange(40.0)
    mask = np.ones((2, t.size), dtype=bool)
    mask[1, 20:] = False
    info = SignalSpec([Constant()]).design_info(t, mask)
    got = info.unit_variance_beta_var
    assert got.shape == (2, 1)
    assert got[0, 0] == pytest.approx(1.0 / 40.0)
    assert got[1, 0] == pytest.approx(1.0 / 20.0)


def test_unit_variance_beta_var_is_nan_for_a_rank_deficient_series():
    """A deficient restricted design has no white-noise reference variance.

    Behaviour under test: the rank gate on the inverse.
    Bug this catches: calling `np.linalg.inv` on a singular Gram, which either
    raises and takes down the tile or returns a huge finite number that becomes
    a confident-looking effective sample size for a design the record does not
    identify.
    """
    t = np.arange(40.0)
    mask = np.zeros((1, t.size), dtype=bool)
    mask[0, :1] = True  # one row cannot support two columns
    info = SignalSpec([Constant(), Trend()]).design_info(t, mask)
    assert bool(info.is_deficient[0])
    assert np.all(np.isnan(info.unit_variance_beta_var[0]))


def test_design_info_slices_to_a_single_series():
    """`series(b)` yields the one-series DesignInfo an inner loop needs.

    Behaviour under test: the per-series view. `optimize_series` fits one
    series at a time against a `(B,)`-wide design, so something has to narrow
    it; doing that at the call site by hand is how the wrong row gets paired
    with the wrong data.
    Bug this catches: slicing the derived fields but not the mask, or the mask
    but not the derived fields. Either pairs a series' rank with another
    series' rows, and the mismatch is silent because both are the right shape
    and the right dtype.
    """
    t = np.arange(40.0)
    mask = np.ones((3, t.size), dtype=bool)
    mask[1, 20:] = False
    mask[2] = False
    info = SignalSpec([Constant(), Trend()]).design_info(t, mask)

    for b in range(3):
        one = info.series(b)
        assert one.batch == 1
        assert one.rank[0] == info.rank[b]
        assert one.n_rows[0] == info.n_rows[b]
        assert one.gram_logdet[0] == info.gram_logdet[b]
        assert one.condition_number[0] == info.condition_number[b]
        assert one.column_terms == info.column_terms
        assert one.mask is not None
        np.testing.assert_array_equal(one.mask[0], mask[b])
        np.testing.assert_allclose(
            one.unit_variance_beta_var[0], info.unit_variance_beta_var[b]
        )
    # The rows really do differ, so the loop above could fail.
    assert info.n_rows[0] != info.n_rows[1]
    assert bool(info.is_deficient[2])
