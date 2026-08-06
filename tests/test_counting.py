"""Tests for per-objective parameter counting and the two effective sample sizes.

Every expected value in this module is derived on paper and written here as the
derivation, not as a number copied out of a run of the code under test. Where a
reference computation appears it is the *definition* evaluated by an obviously
different route -- a plain double Python loop over realized pairs, or a
geometric-series closed form summed term by term -- never a second copy of the
implementation's algorithm.
"""

from __future__ import annotations

import math
import tracemalloc
from collections.abc import Callable
from dataclasses import replace

import numpy as np
import pytest

from metamer.core.capability import Objective
from metamer.core.counting import (
    _frobenius_dense,
    _frobenius_fft,
    n_eff_bic,
    n_eff_bic_closed_form,
    n_eff_trend,
    penalty_terms,
)
from metamer.core.outcomes import Outcome
from metamer.core.statespace import StateSpace
from metamer.core.terms import ProcessSpec, TermSpec, free_param_index
from tests.test_statespace import _term

OK = np.array([Outcome.OK.code], dtype=np.uint8)


def _ok(batch: int) -> np.ndarray:
    return np.full(batch, Outcome.OK.code, dtype=np.uint8)


def _i(*values: int) -> np.ndarray:
    return np.array(values, dtype=np.int64)


def _f(*values: float) -> np.ndarray:
    return np.array(values, dtype=np.float64)


# --------------------------------------------------------------------------
# Independent reference computations. Neither imports anything from counting.
# --------------------------------------------------------------------------
def _realized_pairs_frobenius(
    t_used: np.ndarray, rho_fn: Callable[[float], float]
) -> float:
    """Sum rho(t_i - t_j)^2 over every realized pair, by explicit double loop.

    This is the definition transcribed literally. It is O(n^2) in Python and
    deliberately shares no structure with the FFT or chunked implementations.
    """
    return sum(float(rho_fn(a - b)) ** 2 for a in t_used for b in t_used)


def _closed_form_frobenius_geometric(n: int, b: float) -> float:
    """||R||_F^2 for a complete regular series whose rho_k^2 is b^k.

    Derived by hand:  Sum = n + 2 * sum_{k=1}^{n-1} (n-k) b^k
                          = n + 2 * [ n*S1 - S2 ]
    with  S1 = sum_{k=1}^{M} b^k     = b(1 - b^M) / (1 - b),          M = n-1
          S2 = sum_{k=1}^{M} k b^k   = b(1 - (M+1)b^M + M b^(M+1)) / (1-b)^2.
    Both are the standard geometric and arithmetico-geometric sums.
    """
    m = n - 1
    s1 = b * (1.0 - b**m) / (1.0 - b)
    s2 = b * (1.0 - (m + 1) * b**m + m * b ** (m + 1)) / (1.0 - b) ** 2
    return n + 2.0 * (n * s1 - s2)


# --------------------------------------------------------------------------
# penalty_terms -- ML
# --------------------------------------------------------------------------
def test_ml_counts_profiled_out_beta():
    """Under ML, k includes the GLS-profiled signal parameters.

    Expected value by hand: white contributes sigma (1 free parameter) and
    matern12 contributes sigma and rho (2), so k_theta = 3. A constant+trend
    signal has 2 estimable columns, so k = 3 + 2 = 5 and n = n_obs = 630.

    Bug this catches: the single most common silent bug in concentrated-
    likelihood implementations. Profiled parameters were still estimated from
    the data and still count toward k; omitting them corrupts every selection
    decision with no visible symptom, and no differential test can see it
    because it shifts every candidate by a different constant.
    """
    spec = ProcessSpec((_term("white"), _term("matern12")))
    k, n = penalty_terms(
        spec,
        Objective.ML,
        n_obs=_i(630),
        design_rank=_i(2),
        outcome=OK,
        k_beta=2,
    )
    assert k.tolist() == [5.0]
    assert n.tolist() == [630.0]


def test_ml_k_counts_estimable_beta_not_design_columns():
    """ML's k_beta is rank(X_r), not ncol(X).

    Expected value by hand: matern12 alone gives k_theta = 2. The design has 5
    columns but rank 3, so only 3 linearly independent directions of beta are
    estimated from the data; k = 2 + 3 = 5, not 2 + 5 = 7.

    Bug this catches: counting declared design columns under ML while REML's n
    correctly uses the rank. That inconsistency inflates ML's penalty by
    (ncol - rank) at exactly the grid points where a design has collapsed --
    the points where the two objectives most need to agree about how much the
    data supports.
    """
    spec = ProcessSpec((_term("matern12"),))
    k, n = penalty_terms(
        spec,
        Objective.ML,
        n_obs=_i(100),
        design_rank=_i(3),
        outcome=OK,
        k_beta=5,
    )
    assert k.tolist() == [5.0]
    assert n.tolist() == [100.0]


# --------------------------------------------------------------------------
# penalty_terms -- REML
# --------------------------------------------------------------------------
def test_reml_excludes_beta_entirely_and_reduces_n_by_rank():
    """Under REML, beta is not a parameter of the model at all.

    Expected value by hand: REML is the likelihood of a set of error contrasts,
    a different random quantity from y. So k = k_theta = 1 + 2 = 3 and
    n = 630 - rank(X_r) = 630 - 2 = 628. This is a definition on a different
    model class, not ML's bookkeeping with an adjustment applied.

    Bug this catches: carrying k_beta into REML's k, which would make the two
    objectives' k identical and destroy the whole point of the distinction.
    """
    spec = ProcessSpec((_term("white"), _term("matern12")))
    k, n = penalty_terms(
        spec,
        Objective.REML,
        n_obs=_i(630),
        design_rank=_i(2),
        outcome=OK,
        k_beta=2,
    )
    assert k.tolist() == [3.0]
    assert n.tolist() == [628.0]


def test_reml_n_uses_rank_not_ncol():
    """REML's n subtracts rank(X_r), which is smaller than ncol when deficient.

    Expected value by hand: 100 - 3 = 97, not 100 - 5 = 95.

    Bug this catches: using ncol(X), which over-subtracts and makes the REML
    penalty wrong exactly at the grid points where an offset epoch or an
    unresolvable harmonic has collapsed a column.
    """
    spec = ProcessSpec((_term("matern12"),))
    _, n = penalty_terms(
        spec,
        Objective.REML,
        n_obs=_i(100),
        design_rank=_i(3),
        outcome=OK,
        k_beta=5,
    )
    assert n.tolist() == [97.0]


def test_restricted_rank_below_full_rank_moves_both_objectives_together():
    """A design whose restricted rank is below its full rank shifts k and n.

    Two series share one 4-column design. The first has every epoch and full
    rank 4; the second has a gap that collapses an offset column, so its
    restricted rank is 3. Derived by hand, with k_theta = 2 for matern12:

        ML   series 0: k = 2 + 4 = 6, n = 200
        ML   series 1: k = 2 + 3 = 5, n = 180
        REML series 0: k = 2,         n = 200 - 4 = 196
        REML series 1: k = 2,         n = 180 - 3 = 177

    Bug this catches: taking a batch-level rank or a batch-level n_obs. Both
    are per series, and a single shared value would give series 1 the counts of
    series 0 -- an error of one parameter and 20 observations that reads as
    entirely plausible in BIC.
    """
    spec = ProcessSpec((_term("matern12"),))
    n_obs = _i(200, 180)
    ranks = _i(4, 3)
    k_ml, n_ml = penalty_terms(
        spec, Objective.ML, n_obs=n_obs, design_rank=ranks, outcome=_ok(2), k_beta=4
    )
    k_re, n_re = penalty_terms(
        spec, Objective.REML, n_obs=n_obs, design_rank=ranks, outcome=_ok(2), k_beta=4
    )
    assert k_ml.tolist() == [6.0, 5.0]
    assert n_ml.tolist() == [200.0, 180.0]
    assert k_re.tolist() == [2.0, 2.0]
    assert n_re.tolist() == [196.0, 177.0]


# --------------------------------------------------------------------------
# penalty_terms -- k_theta
# --------------------------------------------------------------------------
def test_frozen_parameters_are_not_counted():
    """A fixed parameter contributes nothing to k_theta.

    Expected value by hand: matern12 declares sigma and rho; pinning rho leaves
    one free parameter, so k_theta = 1 and, with no design at all, k = 1.

    Bug this catches: counting every declared parameter, which inflates the
    penalty for any candidate with a pinned timescale and systematically biases
    selection away from exactly the constrained candidates a user pins in order
    to stabilise a hard grid point.
    """
    term = _term("matern12")
    frozen = {
        name: replace(p, fixed=(name == "rho")) for name, p in term.params.items()
    }
    spec = ProcessSpec(
        (TermSpec(kind="matern12", params=frozen, ordering_param="rho"),)
    )
    k, n = penalty_terms(
        spec, Objective.ML, n_obs=_i(50), design_rank=_i(0), outcome=OK, k_beta=0
    )
    assert k.tolist() == [1.0]
    assert n.tolist() == [50.0]


def test_composite_terms_contribute_their_own_counts():
    """Each term contributes its own free-parameter count, and they add.

    Expected value by hand: white (sigma) = 1, matern12 (sigma, rho) = 2,
    matern32 (sigma, rho) = 2, total k_theta = 5. With 2 estimable design
    columns, ML gives k = 7. The standing invariant
    len(free_param_index(spec)) == spec.n_theta() is asserted alongside, since
    k is only meaningful if it matches the vector the optimizer searches.

    Bug this catches: counting the first term's parameters once for the whole
    composite (k = 3), or double-counting a repeated kind.
    """
    spec = ProcessSpec((_term("white"), _term("matern12"), _term("matern32")))
    assert len(free_param_index(spec)) == spec.n_theta() == 5
    k, _ = penalty_terms(
        spec, Objective.ML, n_obs=_i(400), design_rank=_i(2), outcome=OK, k_beta=2
    )
    assert k.tolist() == [7.0]


def test_shared_parameters_are_refused():
    """A spec with cross-term shared parameters cannot be counted in Phase 1.

    Bug this catches: silently counting a shared parameter once per term, which
    would overstate k_theta for exactly the specs Phase 1 refuses to fit.
    """
    term = _term("matern12")
    shared = TermSpec(
        kind="matern12",
        params=term.params,
        ordering_param="rho",
        shared_with={"rho": "matern12[0]"},
    )
    with pytest.raises(NotImplementedError, match="shared"):
        penalty_terms(
            ProcessSpec((shared,)),
            Objective.ML,
            n_obs=_i(50),
            design_rank=_i(0),
            outcome=OK,
            k_beta=0,
        )


# --------------------------------------------------------------------------
# penalty_terms -- per-series behaviour and validation
# --------------------------------------------------------------------------
def test_failed_series_carry_nan_and_do_not_touch_their_neighbours():
    """Counts are per series; a failed series gets NaN, not -inf, not a number.

    Expected value by hand: series 0 and 2 are OK, so REML gives
    n = 300 - 2 = 298 and k = 2. Series 1 failed, so both slots are NaN.

    Bug this catches: a scalar outcome gate, which would mark all three failed
    or all three scored; and using -inf as the failure sentinel, which survives
    a finiteness check in some consumers and poisons a downstream mean.
    """
    spec = ProcessSpec((_term("matern12"),))
    outcome = np.array(
        [Outcome.OK.code, Outcome.RANK_DEFICIENT_X.code, Outcome.OK.code],
        dtype=np.uint8,
    )
    k, n = penalty_terms(
        spec,
        Objective.REML,
        n_obs=_i(300, 300, 300),
        design_rank=_i(2, 2, 2),
        outcome=outcome,
        k_beta=2,
    )
    assert k[0] == 2.0 and k[2] == 2.0
    assert n[0] == 298.0 and n[2] == 298.0
    assert math.isnan(float(k[1]))
    assert math.isnan(float(n[1]))
    assert not np.isneginf(k).any() and not np.isneginf(n).any()


def test_the_rank_x_failure_sentinel_is_rejected():
    """A -1 in design_rank is the rank_x sentinel and must fail loudly.

    Bug this catches: passing ObjectiveResult.rank_x, which is -1 wherever the
    outcome is not OK, in place of design_rank. Arithmetically that yields
    n = n_obs + 1 -- a sample size larger than the number of observations --
    which is entirely plausible-looking inside BIC. design_rank carries no
    sentinel by contract, so any negative value is proof of the wrong field,
    and it is checked on every series including the failed ones (which is where
    rank_x's sentinel actually lives).
    """
    spec = ProcessSpec((_term("matern12"),))
    outcome = np.array(
        [Outcome.OK.code, Outcome.NONFINITE_OBJECTIVE.code], dtype=np.uint8
    )
    with pytest.raises(ValueError, match="design_rank"):
        penalty_terms(
            spec,
            Objective.REML,
            n_obs=_i(630, 630),
            design_rank=_i(2, -1),
            outcome=outcome,
            k_beta=2,
        )


def test_rank_above_the_column_count_is_rejected():
    """rank(X_r) can never exceed ncol(X).

    Bug this catches: swapping the design_rank and k_beta arguments, which is
    easy at a call site where both are small integers and which silently makes
    REML's n too small and ML's k too large.
    """
    spec = ProcessSpec((_term("matern12"),))
    with pytest.raises(ValueError, match="design_rank"):
        penalty_terms(
            spec,
            Objective.ML,
            n_obs=_i(100),
            design_rank=_i(5),
            outcome=OK,
            k_beta=3,
        )


def test_reml_refuses_a_nonpositive_effective_sample_size():
    """A scored series must have n_obs - rank(X_r) > 0 under REML.

    Bug this catches: n_obs = 3 with rank 3 gives n = 0, and every criterion
    then takes log(0) = -inf, which propagates as a spuriously perfect score.
    A series with no error contrasts left has no REML likelihood at all, so
    this is a contradiction with outcome == OK, not a small number.
    """
    spec = ProcessSpec((_term("matern12"),))
    with pytest.raises(ValueError, match="error contrasts|n_obs"):
        penalty_terms(
            spec,
            Objective.REML,
            n_obs=_i(3),
            design_rank=_i(3),
            outcome=OK,
            k_beta=3,
        )


def test_a_failed_series_is_not_validated_for_its_contrast_count():
    """The outcome gate runs before the REML arithmetic, not after.

    A wholly masked series has n_obs = 0 and is INSUFFICIENT_DATA. It must not
    take down the whole batch through the n_obs - rank > 0 check.

    Bug this catches: validating unconditionally, which turns one land pixel in
    a tile of 100k into an exception and loses the entire tile.
    """
    spec = ProcessSpec((_term("matern12"),))
    outcome = np.array(
        [Outcome.INSUFFICIENT_DATA.code, Outcome.OK.code], dtype=np.uint8
    )
    k, n = penalty_terms(
        spec,
        Objective.REML,
        n_obs=_i(0, 300),
        design_rank=_i(0, 2),
        outcome=outcome,
        k_beta=2,
    )
    assert math.isnan(float(n[0])) and math.isnan(float(k[0]))
    assert n.tolist()[1] == 298.0


def test_mismatched_per_series_shapes_are_rejected():
    """n_obs, design_rank and outcome must describe the same batch.

    Bug this catches: broadcasting a length-1 design_rank across a batch of B,
    which numpy would do silently and which would give every series the first
    series' rank.
    """
    spec = ProcessSpec((_term("matern12"),))
    with pytest.raises(ValueError, match="shape"):
        penalty_terms(
            spec,
            Objective.ML,
            n_obs=_i(100, 100, 100),
            design_rank=_i(2),
            outcome=_ok(3),
            k_beta=2,
        )


def test_non_vector_per_series_arguments_are_rejected():
    """Every per-series argument must be a (B,) vector, not a grid or a scalar.

    Bug this catches: passing the (Y, X) spatial grid straight through without
    ravelling it to the batch axis. numpy would broadcast a (Y, X) n_obs
    against a (B,) design_rank in some shapes and produce a (Y, X) k that the
    caller would then write into a (B,) slot.
    """
    spec = ProcessSpec((_term("matern12"),))
    with pytest.raises(ValueError, match="n_obs must be one-dimensional"):
        penalty_terms(
            spec,
            Objective.ML,
            n_obs=np.full((2, 3), 100, dtype=np.int64),
            design_rank=_i(0),
            outcome=OK,
            k_beta=0,
        )
    with pytest.raises(ValueError, match="outcome must have shape"):
        penalty_terms(
            spec,
            Objective.ML,
            n_obs=_i(100, 100),
            design_rank=_i(0, 0),
            outcome=OK,
            k_beta=0,
        )


def test_negative_counts_are_rejected():
    """n_obs and k_beta are counts and cannot be negative.

    Bug this catches: an uninitialised or sentinel-filled n_obs slot reaching
    the criterion as a negative sample size.
    """
    spec = ProcessSpec((_term("matern12"),))
    with pytest.raises(ValueError, match="n_obs"):
        penalty_terms(
            spec, Objective.ML, n_obs=_i(-1), design_rank=_i(0), outcome=OK, k_beta=0
        )
    with pytest.raises(ValueError, match="k_beta"):
        penalty_terms(
            spec, Objective.ML, n_obs=_i(10), design_rank=_i(0), outcome=OK, k_beta=-1
        )


# --------------------------------------------------------------------------
# n_eff_bic -- analytic endpoints, driven from real families
# --------------------------------------------------------------------------
def test_n_eff_bic_is_exactly_n_used_at_zero_correlation():
    """R = I gives ||R||_F^2 = n_used, hence n_eff = n_used^2/n_used = n_used.

    Expected value by hand and EXACT, not approximate: a white-noise model has
    rho_k = 0 for every k >= 1 and rho_0 = 1, so the Frobenius sum is exactly
    the count of diagonal entries. Driven from the registered White family so
    that rho really is the model ACF and not a hand-written array.

    n_used by hand: 64 epochs, dropping every third starting at 0 removes the
    22 indices {0, 3, ..., 63} = {3j : j = 0..21}, leaving 64 - 22 = 42.

    Bug this catches: an off-by-one in the realized-pair counts, or counting
    the lag-0 pairs twice (which would give n_used/2 here).
    """
    spec = ProcessSpec((_term("white"),))
    ss = StateSpace.from_spec(spec)
    t = np.arange(64.0)
    mask = np.ones((1, 64), dtype=bool)
    mask[0, ::3] = False  # the gaps must not change the answer
    assert int(mask.sum()) == 42
    result = n_eff_bic(ss, np.array([[2.0]]), t, mask=mask, outcome=OK)
    assert result.tolist() == [42.0]


def test_n_eff_bic_is_exactly_one_at_perfect_correlation():
    """R = J (all ones) gives ||R||_F^2 = n_used^2, hence n_eff = 1.

    Expected value by hand and EXACT: a matern12 with rho = 1e300 evaluates
    exp(-tau/rho) to exactly 1.0 in float64 for every lag in this record, so
    every entry of R is exactly 1 and the sum is exactly n_used^2.

    Bug this catches: any accumulation that double-counts off-diagonal pairs
    (which would give 1/2 here) or forgets them (which would give n_used).
    """
    spec = ProcessSpec((_term("matern12"),))
    ss = StateSpace.from_spec(spec)
    t = np.arange(50.0)
    mask = np.ones((1, 50), dtype=bool)
    result = n_eff_bic(ss, np.array([[1.0, 1e300]]), t, mask=mask, outcome=OK)
    assert result.tolist() == [1.0]


def test_n_eff_bic_under_a_mask_uses_realized_pairs_not_lag_indices():
    """The masked answer is the realized-pairs sum, not the closed form.

    Setup: t = 0..199 with every other sample kept, model rho(tau) =
    exp(-tau/10). The kept samples are a regular grid of step 2, so
    rho_m = exp(-2m/10) between kept samples m apart and rho_m^2 = b^m with
    b = exp(-0.4). By hand,

        n_eff = 100^2 / [100 + 2 * sum_{m=1}^{99} (100-m) b^m] = 20.2300439994

    (the bracket is evaluated below through the geometric closed form derived
    in _closed_form_frobenius_geometric, and independently through an explicit
    double loop over realized pairs). Feeding the closed form the model ACF at
    lag INDEX instead -- exp(-k/10) for k = 1..99 -- gives 10.4877050583, an
    error of -48.16%, so the two are separated by a factor of nearly two and
    the assertion cannot be satisfied by accident.

    Bug this catches: exactly the brief's implementation. Under a mask the
    pairs actually present are not the (n-k) the lag-k count implies.
    """
    spec = ProcessSpec((_term("matern12"),))
    ss = StateSpace.from_spec(spec)
    t = np.arange(200.0)
    mask = np.zeros((1, 200), dtype=bool)
    mask[0, ::2] = True

    b = math.exp(-0.4)
    expected = 100.0**2 / _closed_form_frobenius_geometric(100, b)
    by_pairs = 100.0**2 / _realized_pairs_frobenius(
        t[::2], lambda tau: math.exp(-abs(tau) / 10.0)
    )
    assert expected == pytest.approx(20.2300439994, rel=1e-11)
    assert by_pairs == pytest.approx(expected, rel=1e-12)

    result = float(n_eff_bic(ss, np.array([[1.0, 10.0]]), t, mask=mask, outcome=OK)[0])
    assert result == pytest.approx(expected, rel=1e-12)
    # And it is nowhere near the closed form fed lag indices.
    assert abs(result - 10.4877050583) > 9.0


def test_a_mask_that_halves_n_used_reduces_n_eff_by_far_less():
    """Dropping every other sample loses redundancy, not information.

    Expected values by hand from the geometric closed form. rho_k^2 = b^k with
    b = exp(-0.2) for the full series (step 1, rho_k = exp(-k/10)), and with
    b^2 = exp(-0.4) for the kept series (step 2, rho_m = exp(-2m/10)):

        n_eff(full, n=200)  = 200^2 / 1956.82856031 = 20.4412388552
        n_eff(kept, n=100)  = 100^2 /  494.31429810 = 20.2300439994
        ratio               = 0.9896681969

    n_used has halved; n_eff has fallen by 1.03%.

    Bug this catches: treating a mask as a plain shortening of the series,
    which would give a ratio near 0.5 rather than near 1.
    """
    spec = ProcessSpec((_term("matern12"),))
    ss = StateSpace.from_spec(spec)
    t = np.arange(200.0)
    theta = np.array([[1.0, 10.0]])
    full = float(
        n_eff_bic(ss, theta, t, mask=np.ones((1, 200), dtype=bool), outcome=OK)[0]
    )
    half_mask = np.zeros((1, 200), dtype=bool)
    half_mask[0, ::2] = True
    half = float(n_eff_bic(ss, theta, t, mask=half_mask, outcome=OK)[0])

    b = math.exp(-0.2)
    exp_full = 200.0**2 / _closed_form_frobenius_geometric(200, b)
    exp_half = 100.0**2 / _closed_form_frobenius_geometric(100, b * b)
    assert exp_full == pytest.approx(20.4412388552, rel=1e-11)
    assert full == pytest.approx(exp_full, rel=1e-12)
    assert half == pytest.approx(exp_half, rel=1e-12)
    assert half / full == pytest.approx(0.9896681969, rel=1e-9)
    assert half / full > 0.5


# --------------------------------------------------------------------------
# n_eff_bic -- the two evaluation paths
# --------------------------------------------------------------------------
def test_fft_and_dense_paths_agree_on_a_regular_masked_axis():
    """The two implementations of the same sum agree to float64 rounding.

    A regular axis with a 35% random mask takes the FFT path. Forcing the
    chunked dense path on the identical input must give the identical number:
    the FFT is only a fast way of counting realized pairs per lag.

    Bug this catches: a wrong zero-padding length in the FFT (which makes the
    autocorrelation circular and folds long lags onto short ones), or an
    off-by-one in the chunk boundaries of the dense path.
    """
    spec = ProcessSpec((_term("white"), _term("matern12")))
    ss = StateSpace.from_spec(spec)
    rng = np.random.default_rng(20260806)
    t = np.arange(630.0)
    mask = rng.random((1, 630)) > 0.35
    theta = np.array([[0.5, 13.0, 0.25]])  # canonical order: matern12 then white
    fft = float(n_eff_bic(ss, theta, t, mask=mask, outcome=OK, path="fft")[0])
    dense = float(n_eff_bic(ss, theta, t, mask=mask, outcome=OK, path="dense")[0])
    auto = float(n_eff_bic(ss, theta, t, mask=mask, outcome=OK)[0])
    assert fft == pytest.approx(dense, rel=1e-12)
    assert auto == fft
    assert 1.0 <= fft <= float(mask.sum())


def test_closed_form_agrees_with_both_paths_on_a_complete_regular_series():
    """With no mask the general form must reduce to the closed form.

    This is the cheapest available check that the realized-pairs machinery is
    right: the closed form's (n-k) pair counts are derivable on paper and the
    two paths must reproduce them.

    Bug this catches: a systematic pair-count error that the two general paths
    would share (they both count pairs; only the closed form asserts what the
    count should be).
    """
    spec = ProcessSpec((_term("matern12"),))
    ss = StateSpace.from_spec(spec)
    n = 64
    t = np.arange(float(n))
    theta = np.array([[1.0, 7.0]])
    mask = np.ones((1, n), dtype=bool)
    rho = np.exp(-np.arange(1.0, n) / 7.0)
    closed = n_eff_bic_closed_form(rho, n)
    b = math.exp(-2.0 / 7.0)
    assert closed == pytest.approx(
        n * n / _closed_form_frobenius_geometric(n, b), rel=1e-12
    )
    for path in ("fft", "dense"):
        got = float(n_eff_bic(ss, theta, t, mask=mask, outcome=OK, path=path)[0])
        assert got == pytest.approx(closed, rel=1e-12)


def test_an_irregular_axis_takes_the_dense_path_and_is_right():
    """On an irregular axis the lags do not bin, so the FFT trick is invalid.

    Expected value from an explicit double loop over realized pairs, which is
    the definition and shares no structure with the chunked implementation.
    Forcing the FFT path on the same axis must be refused rather than answered,
    because that path can only count pairs per integer lag index and an axis
    whose spacing varies by a factor of five has no such binning.

    Bug this catches: dispatching to the FFT unconditionally, or a regularity
    test that calls an irregular axis regular -- either of which silently
    substitutes sample index for elapsed time.
    """
    spec = ProcessSpec((_term("matern12"),))
    ss = StateSpace.from_spec(spec)
    rng = np.random.default_rng(7)
    t = np.cumsum(rng.uniform(0.5, 2.5, size=120))
    assert StateSpace.unique_dt(t).size > 1
    theta = np.array([[1.0, 4.0]])
    mask = np.ones((1, 120), dtype=bool)
    mask[0, 10:20] = False

    used = t[mask[0]]
    expected = used.size**2 / _realized_pairs_frobenius(
        used, lambda tau: math.exp(-abs(tau) / 4.0)
    )
    auto = float(n_eff_bic(ss, theta, t, mask=mask, outcome=OK)[0])
    dense = float(n_eff_bic(ss, theta, t, mask=mask, outcome=OK, path="dense")[0])
    assert auto == pytest.approx(expected, rel=1e-12)
    assert auto == dense
    with pytest.raises(ValueError, match="irregular"):
        n_eff_bic(ss, theta, t, mask=mask, outcome=OK, path="fft")


def test_the_dense_path_is_chunked_and_matches_across_chunk_sizes():
    """Chunking must not change the sum, only the peak memory.

    A byte budget forcing single-row chunks must give the same number as one
    forcing a single chunk. The budget bounds the lag block, not n_used^2.

    Bug this catches: a chunk loop that drops the final partial chunk, or one
    that recomputes the diagonal in every chunk.
    """
    spec = ProcessSpec((_term("matern12"),))
    ss = StateSpace.from_spec(spec)
    rng = np.random.default_rng(11)
    t = np.cumsum(rng.uniform(0.5, 2.5, size=200))
    theta = np.array([[1.0, 6.0]])
    mask = rng.random((1, 200)) > 0.2
    one_row = float(
        n_eff_bic(ss, theta, t, mask=mask, outcome=OK, path="dense", max_pair_bytes=8)[
            0
        ]
    )
    one_chunk = float(
        n_eff_bic(
            ss, theta, t, mask=mask, outcome=OK, path="dense", max_pair_bytes=1 << 24
        )[0]
    )
    assert one_row == pytest.approx(one_chunk, rel=1e-13)


def test_the_dense_path_peak_memory_is_bounded_by_the_budget():
    """The budget bounds peak allocation, not just the answer.

    Chunk-invariance of the SUM cannot catch a missing block loop -- deleting
    the blocking entirely leaves every sum unchanged. Only a measurement of
    peak allocation distinguishes "blocked" from "not blocked", so this asserts
    on tracemalloc directly.

    Expected magnitudes by hand: n_used = 600 unmasked epochs means a full
    600 x 600 float64 lag matrix is 600^2 * 8 = 2.88 MB, and the ACVF needs
    several temporaries of that same shape. A 64 KiB budget admits
    65536 // (600 * 8) = 13 rows, so each block is 62.4 kB and peak should be a
    single-digit multiple of that -- two orders of magnitude below the
    unblocked figure.

    Bug this catches: `rows_per_block = n_used`, i.e. removing the blocking.
    That leaves every assertion about the VALUE untouched and reintroduces the
    O(n_used^2) allocation this budget exists to prevent.
    """
    spec = ProcessSpec((_term("matern12"),))
    ss = StateSpace.from_spec(spec)
    rng = np.random.default_rng(31)
    t = np.cumsum(rng.uniform(0.5, 2.5, size=600))
    theta = np.array([[1.0, 9.0]])
    full_matrix_bytes = 600 * 600 * 8

    tracemalloc.start()
    try:
        tracemalloc.reset_peak()
        blocked = _frobenius_dense(ss, theta, t, 1 << 16)
        peak_blocked = tracemalloc.get_traced_memory()[1]
        tracemalloc.reset_peak()
        unblocked = _frobenius_dense(ss, theta, t, 1 << 30)
        peak_unblocked = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()

    assert blocked == pytest.approx(unblocked, rel=1e-13)
    # The unblocked call must really allocate the full matrix, or the bound
    # below would be trivially satisfied.
    assert peak_unblocked > full_matrix_bytes
    # The blocked call must stay far below it: 10x the 64 KiB budget is still
    # under a quarter of one full matrix.
    assert peak_blocked < 10 * (1 << 16)


def test_the_fft_path_peak_memory_is_bounded_over_the_batch():
    """The FFT path is capped over SERIES, which is the axis that scales.

    Per series the FFT path is cheap; over a tile it is not. Measured at
    N = 630 it holds 56 bytes per epoch per series, so an uncapped batch of
    100 000 series would reach 3.5 GB against a 16 GB whole-job budget. The cap
    blocks over series, which is exact because no series' pair counts involve
    any other's.

    Expected magnitudes by hand: B = 400 at N = 630 is about 400 * 35.3 kB =
    14 MB uncapped. A 1 MiB budget at 64 estimated bytes per epoch per series
    admits 1048576 // (630 * 64) = 26 series per block, so peak should land
    near 26 * 35.3 kB = 0.9 MB.

    Bug this catches: dropping the series loop from `_frobenius_fft`, which
    changes no value anywhere and silently restores the 3.5 GB tile.
    """
    spec = ProcessSpec((_term("matern12"),))
    ss = StateSpace.from_spec(spec)
    batch, length = 400, 630
    theta = np.tile([[1.0, 13.0]], (batch, 1))
    mask = np.ones((batch, length), dtype=bool)

    tracemalloc.start()
    try:
        tracemalloc.reset_peak()
        capped = _frobenius_fft(ss, theta, length, 1.0, mask, 1 << 20)
        peak_capped = tracemalloc.get_traced_memory()[1]
        tracemalloc.reset_peak()
        uncapped = _frobenius_fft(ss, theta, length, 1.0, mask, 1 << 30)
        peak_uncapped = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()

    np.testing.assert_allclose(capped, uncapped, rtol=1e-13)
    assert peak_uncapped > 8 * (1 << 20)  # the uncapped batch really is large
    assert peak_capped < 4 * (1 << 20)  # and the cap really binds


def test_n_eff_bic_is_per_series_with_its_own_mask_theta_and_outcome():
    """Each series gets its own model ACF, its own mask, and its own verdict.

    Expected values by hand: series 0 is white noise over 20 unmasked epochs,
    so n_eff = 20 exactly. Series 1 failed, so NaN. Series 2 is perfectly
    correlated, so n_eff = 1 exactly.

    Bug this catches: computing one n_eff for the batch from series 0's mask,
    or evaluating a failed series' garbage theta and returning a number for it.
    """
    spec = ProcessSpec((_term("matern12"),))
    ss = StateSpace.from_spec(spec)
    t = np.arange(20.0)
    theta = np.array([[1.0, 1e-300], [np.nan, np.nan], [1.0, 1e300]])
    mask = np.ones((3, 20), dtype=bool)
    mask[1, :] = False
    outcome = np.array(
        [Outcome.OK.code, Outcome.INSUFFICIENT_DATA.code, Outcome.OK.code],
        dtype=np.uint8,
    )
    got = n_eff_bic(ss, theta, t, mask=mask, outcome=outcome)
    assert got[0] == 20.0
    assert math.isnan(float(got[1]))
    assert got[2] == 1.0


# --------------------------------------------------------------------------
# n_eff_bic -- validation
# --------------------------------------------------------------------------
def test_n_eff_bic_refuses_a_wholly_masked_scored_series():
    """n_used = 0 is a division by zero, not an effective sample size.

    Bug this catches: the brief's ZeroDivisionError on an all-masked series,
    and worse, any variant that returns nan silently while the outcome still
    reads OK -- a contradiction that should fail loudly.
    """
    spec = ProcessSpec((_term("matern12"),))
    ss = StateSpace.from_spec(spec)
    with pytest.raises(ValueError, match="n_used|wholly masked"):
        n_eff_bic(
            ss,
            np.array([[1.0, 5.0]]),
            np.arange(10.0),
            mask=np.zeros((1, 10), dtype=bool),
            outcome=OK,
        )


def test_n_eff_bic_refuses_a_nonpositive_marginal_variance():
    """rho = acvf(tau)/acvf(0) needs acvf(0) > 0.

    Bug this catches: a degenerate fit with every sigma driven to zero, where
    the normalisation divides by zero and produces nan or inf correlations that
    then sum to a plausible-looking n_eff.
    """
    spec = ProcessSpec((_term("white"),))
    ss = StateSpace.from_spec(spec)
    with pytest.raises(ValueError, match="variance"):
        n_eff_bic(
            ss,
            np.array([[0.0]]),
            np.arange(10.0),
            mask=np.ones((1, 10), dtype=bool),
            outcome=OK,
        )


def test_n_eff_bic_handles_a_single_epoch_axis():
    """One epoch has no timesteps at all, and an effective sample size of 1.

    Expected value by hand and EXACT: the realized pairs are the single pair
    (t_0, t_0), so the Frobenius sum is rho(0)^2 = 1 and n_eff = 1^2/1 = 1.
    This is the one axis on which unique_dt returns nothing, so the regularity
    test has no step to inspect.

    Bug this catches: indexing unique_dt's result unconditionally, which raises
    IndexError on a one-epoch series rather than returning 1.
    """
    spec = ProcessSpec((_term("matern12"),))
    ss = StateSpace.from_spec(spec)
    got = n_eff_bic(
        ss,
        np.array([[1.0, 5.0]]),
        np.array([3.5]),
        mask=np.ones((1, 1), dtype=bool),
        outcome=OK,
    )
    assert got.tolist() == [1.0]


def test_n_eff_bic_rejects_malformed_batch_shapes():
    """theta, t and mask must describe one batch over one time axis.

    Bug this catches: passing a single series' theta as (P,) rather than
    (1, P), which numpy would happily index and which would silently make the
    batch size P; and passing a (B, N) time grid, which would make every lag a
    different series' timestamp.
    """
    spec = ProcessSpec((_term("matern12"),))
    ss = StateSpace.from_spec(spec)
    good_t = np.arange(10.0)
    good_mask = np.ones((1, 10), dtype=bool)
    with pytest.raises(ValueError, match="theta must have shape"):
        n_eff_bic(ss, np.array([1.0, 5.0]), good_t, mask=good_mask, outcome=OK)
    with pytest.raises(ValueError, match="t must have shape"):
        n_eff_bic(
            ss,
            np.array([[1.0, 5.0]]),
            np.tile(good_t, (1, 1)),
            mask=good_mask,
            outcome=OK,
        )
    with pytest.raises(ValueError, match="mask must have shape"):
        n_eff_bic(
            ss,
            np.array([[1.0, 5.0]]),
            good_t,
            mask=np.ones((1, 9), dtype=bool),
            outcome=OK,
        )


def test_n_eff_bic_returns_all_nan_when_nothing_was_scored():
    """A tile of wholly failed series produces NaN, not an exception.

    Every series here is INSUFFICIENT_DATA with an all-false mask, which would
    divide by zero if it were evaluated. Land and permanent ice make whole
    tiles look like this, so the batch must come back cleanly.

    Bug this catches: running the wholly-masked check before the outcome gate,
    which would turn an entirely-land tile into a crash.
    """
    spec = ProcessSpec((_term("matern12"),))
    ss = StateSpace.from_spec(spec)
    got = n_eff_bic(
        ss,
        np.full((3, 2), np.nan),
        np.arange(10.0),
        mask=np.zeros((3, 10), dtype=bool),
        outcome=np.full(3, Outcome.INSUFFICIENT_DATA.code, dtype=np.uint8),
    )
    assert got.shape == (3,)
    assert bool(np.all(np.isnan(got)))


class _ImpossibleAcvf:
    """A state space whose ACVF exceeds its own variance at non-zero lag.

    Fault injection, not a mock of a collaborator: no registered family can
    produce `|rho| > 1`, so the only way to reach the guard through the public
    `n_eff_bic` entry point is to supply an ACVF that violates the definition.
    That is exactly the state a broken family or a degenerate fit would create,
    and it is what the guard exists for.
    """

    def acvf(self, theta: np.ndarray, lags: np.ndarray) -> np.ndarray:  # noqa: D102 - see class docstring
        out = np.full((np.shape(theta)[0], np.size(lags)), 1.5, dtype=np.float64)
        out[:, np.asarray(lags) == 0.0] = 1.0
        return out


@pytest.mark.parametrize("path", ["fft", "dense"])
def test_n_eff_bic_rejects_an_impossible_autocorrelation_on_both_paths(path):
    """|rho| > 1 is refused through the state-space route, not just the array one.

    Expected behaviour by hand: an ACVF of 1.0 at lag 0 and 1.5 elsewhere gives
    rho = 1.5, which no autocorrelation can take. Left unguarded the
    participation ratio would still return a plausible positive number -- the
    brief's code gives 0.449 at n = 50 for a constant rho of 1.5 -- rather than
    anything recognisably wrong.

    Bug this catches: validating the magnitude only inside
    `n_eff_bic_closed_form`, so that the path actually used in production
    accepts a broken family's output. Parametrized over both paths because they
    reach the shared check by different routes (one lag vector, one lag block).
    """
    t = np.arange(20.0) if path == "fft" else np.cumsum(np.arange(1.0, 21.0))
    with pytest.raises(ValueError, match="magnitude"):
        n_eff_bic(
            _ImpossibleAcvf(),  # type: ignore[arg-type]
            np.array([[1.0, 5.0]]),
            t,
            mask=np.ones((1, 20), dtype=bool),
            outcome=OK,
            path=path,
        )


def test_rtol_decides_which_path_a_near_regular_axis_takes():
    """The regularity tolerance is a real parameter, and it changes the dispatch.

    The axis below is arange(100) with a single 1e-6 perturbation, so its steps
    are 1.0 and 1.000001. At the default rtol of 1e-9 those are two distinct
    steps and the axis is irregular; at rtol = 1e-5 they cluster into one and it
    is regular. The dispatch must follow, which is asserted by matching the auto
    result against the forced path on each side.

    Bug this catches: ignoring the rtol argument and always consulting
    unique_dt at its own default, which would silently route every near-regular
    axis -- the common case for real instrument records -- to the slow path.
    """
    spec = ProcessSpec((_term("matern12"),))
    ss = StateSpace.from_spec(spec)
    t = np.arange(100.0)
    t[50:] += 1e-6
    theta = np.array([[1.0, 8.0]])
    mask = np.ones((1, 100), dtype=bool)
    assert StateSpace.unique_dt(t).size == 2
    assert StateSpace.unique_dt(t, rtol=1e-5).size == 1

    with pytest.raises(ValueError, match="irregular"):
        n_eff_bic(ss, theta, t, mask=mask, outcome=OK, path="fft")
    loose = float(n_eff_bic(ss, theta, t, mask=mask, outcome=OK, rtol=1e-5)[0])
    forced_fft = float(
        n_eff_bic(ss, theta, t, mask=mask, outcome=OK, path="fft", rtol=1e-5)[0]
    )
    tight = float(n_eff_bic(ss, theta, t, mask=mask, outcome=OK)[0])
    forced_dense = float(
        n_eff_bic(ss, theta, t, mask=mask, outcome=OK, path="dense")[0]
    )
    assert loose == forced_fft
    assert tight == forced_dense


def test_n_eff_bic_rejects_an_unknown_path():
    """The dispatch keyword is closed, not free text.

    Bug this catches: a typo like path="ftt" silently falling through to the
    default and hiding which algorithm actually ran.
    """
    spec = ProcessSpec((_term("matern12"),))
    ss = StateSpace.from_spec(spec)
    with pytest.raises(ValueError, match="path"):
        n_eff_bic(
            ss,
            np.array([[1.0, 5.0]]),
            np.arange(10.0),
            mask=np.ones((1, 10), dtype=bool),
            outcome=OK,
            path="ftt",  # type: ignore[arg-type]  # the point is the runtime guard
        )


# --------------------------------------------------------------------------
# n_eff_bic_closed_form -- the complete-regular fast path
# --------------------------------------------------------------------------
def test_closed_form_endpoints_are_exact():
    """Zero correlation gives exactly n; perfect correlation gives exactly 1.

    Expected values by hand: ||R||_F^2 = n for R = I giving n^2/n = n, and
    ||R||_F^2 = n^2 for the all-ones R giving 1. Both are exact in float64
    because the sums are of exactly representable terms.

    Bug this catches: an implementation that omits the lag-0 diagonal (giving
    inf at zero correlation) or that sums lags 0..n-1 instead of 1..n-1.
    """
    n = 50
    assert n_eff_bic_closed_form(np.zeros(n - 1), n) == 50.0
    assert n_eff_bic_closed_form(np.ones(n - 1), n) == 1.0


def test_closed_form_handles_a_single_observation():
    """n = 1 has no lags at all and an effective sample size of exactly 1.

    Expected value by hand: R is the 1x1 matrix [1], so ||R||_F^2 = 1 and
    n_eff = 1^2/1 = 1. The correlation array is legitimately empty here, which
    is the one case where a zero-length rho must be accepted rather than
    refused as too short.

    Bug this catches: a length check that demands a non-empty array, which
    would reject the shortest valid series outright.
    """
    assert n_eff_bic_closed_form(np.zeros(0), 1) == 1.0


def test_closed_form_is_monotone_in_correlation_strength():
    """Stronger correlation gives a smaller effective sample size.

    Bug this catches: an estimator that can exceed n or go negative -- the
    classic n/(1 + 2 sum rho_k) form does both, which is why it is not used.
    """
    n = 200
    lags = np.arange(1.0, float(n))
    weak = n_eff_bic_closed_form(0.3**lags, n)
    strong = n_eff_bic_closed_form(0.9**lags, n)
    assert 1.0 <= strong < weak <= n


def test_closed_form_depends_only_on_the_magnitude_of_the_correlation():
    """Negative correlation enters squared, so it cannot inflate n_eff.

    Expected value by hand and EXACT: rho^2 is bit-identical for x and -x in
    IEEE-754, so rho_k = (-0.8)^k and rho_k = 0.8^k must give the same float.
    The classic n/(1 + 2 sum rho_k) form gives 1 + 2*(-0.8/1.8) = 0.111 here,
    i.e. about 9n -- nine times the number of observations.

    Bug this catches: summing signed correlations anywhere in the accumulation.
    """
    n = 50
    lags = np.arange(1.0, float(n))
    negative = n_eff_bic_closed_form((-0.8) ** lags, n)
    positive = n_eff_bic_closed_form(0.8**lags, n)
    assert negative == positive
    assert 1.0 <= negative <= n


@pytest.mark.parametrize(
    ("rho", "n", "match"),
    [
        (np.full(59, 0.9), 20, "n - 1"),  # longer than n-1: (n-k) goes negative
        (np.zeros(3), 50, "n - 1"),  # shorter than n-1: silently zero-padded
        (np.full(49, 1.5), 50, "magnitude"),  # |rho| > 1 from a broken fit
        (np.zeros(0), 0, "at least 1"),  # empty series
    ],
)
def test_closed_form_validates_its_correlation_array(rho, n, match):
    """The docstring promises rho_k for k = 1..n-1 in [-1, 1]; enforce it.

    Bug this catches, case by case: an over-long array makes (n - lags) go
    negative and the participation ratio follows it (measured -0.080 for
    n=10 with 50 lags at rho=0.9); a short array is silently zero-padded and
    reports n_eff = n for a strongly correlated series; |rho| > 1 from a bad
    fit gives 0.449 at n=50 rather than failing; n = 0 divides by zero.
    """
    with pytest.raises(ValueError, match=match):
        n_eff_bic_closed_form(rho, n)


# --------------------------------------------------------------------------
# n_eff_trend
# --------------------------------------------------------------------------
def test_n_eff_trend_is_the_variance_ratio():
    """n * var_white / var_gls, per series.

    Expected value by hand: 100 * 1 / 4 = 25. The GLS trend estimate has four
    times the variance it would have under white noise, so the trend is
    determined as well as 25 independent samples would determine it.

    Bug this catches: inverting the ratio, which would report 400 -- four times
    the number of observations -- and read as a suspiciously good record.
    """
    got = n_eff_trend(_f(4.0), _f(1.0), _i(100), outcome=OK)
    assert got.tolist() == [25.0]


def test_n_eff_trend_clips_to_the_closed_interval():
    """The ratio is clipped into [1, n], both ends.

    Expected values by hand: 100 * 1 / 0.5 = 200 clips down to n = 100;
    100 * 1 / 1e6 = 1e-4 clips up to 1.

    Bug this catches: reporting more effective samples than observations, which
    would let a BIC variant penalise less than the unadjusted criterion.
    """
    got = n_eff_trend(
        np.array([0.5, 1e6]), np.array([1.0, 1.0]), _i(100, 100), outcome=_ok(2)
    )
    assert got.tolist() == [100.0, 1.0]


def test_n_eff_trend_rejects_malformed_batch_shapes():
    """The two variances must be (B,) vectors describing the same batch.

    Bug this catches: passing the (Y, X) grid of GLS variances directly, or a
    var_white of a different length, either of which numpy would broadcast into
    a result the caller cannot write back per series.
    """
    with pytest.raises(ValueError, match="var_trend_gls must have shape"):
        n_eff_trend(
            np.full((2, 3), 4.0), np.full(6, 1.0), _i(*([100] * 6)), outcome=_ok(6)
        )
    with pytest.raises(ValueError, match="var_trend_white must have shape"):
        n_eff_trend(_f(4.0, 4.0), _f(1.0), _i(100, 100), outcome=_ok(2))


def test_n_eff_trend_and_n_eff_bic_differ_on_the_same_series():
    """The two effective sample sizes are different numbers, and must stay so.

    Expected values by hand for one series: t = 0..199 with rho(tau) =
    exp(-tau/10) gives n_eff_bic = 200^2/1956.82856031 = 20.4412388552, while a
    GLS trend variance four times its white-noise counterpart gives
    n_eff_trend = 200/4 = 50.0. They differ by a factor of 2.45.

    Bug this catches: a refactor that collapses the two into one function.
    Asserting each in isolation at different n, as the brief does, would not
    fail if they were merged; asserting both on the SAME series does.
    """
    spec = ProcessSpec((_term("matern12"),))
    ss = StateSpace.from_spec(spec)
    t = np.arange(200.0)
    bic = float(
        n_eff_bic(
            ss,
            np.array([[1.0, 10.0]]),
            t,
            mask=np.ones((1, 200), dtype=bool),
            outcome=OK,
        )[0]
    )
    trend = float(n_eff_trend(_f(4.0), _f(1.0), _i(200), outcome=OK)[0])
    assert bic == pytest.approx(20.4412388552, rel=1e-10)
    assert trend == 50.0
    assert trend != pytest.approx(bic, rel=0.1)


def test_n_eff_trend_carries_nan_for_a_failed_series():
    """Failed series get NaN, and their inputs are never used arithmetically.

    Bug this catches: a failed series whose variance slots were never written
    (and so hold 0.0) taking down the batch through the positivity check.
    """
    outcome = np.array(
        [Outcome.OK.code, Outcome.TRUST_RADIUS_COLLAPSED.code], dtype=np.uint8
    )
    got = n_eff_trend(
        np.array([4.0, 0.0]), np.array([1.0, 0.0]), _i(100, 100), outcome=outcome
    )
    assert got[0] == 25.0
    assert math.isnan(float(got[1]))


@pytest.mark.parametrize(
    ("var_gls", "var_white", "n", "match"),
    [
        (0.0, 1.0, 100, "var_trend_gls"),  # ZeroDivisionError in the brief
        (-4.0, 1.0, 100, "var_trend_gls"),  # clipped to 1.0 in the brief
        (4.0, 0.0, 100, "var_trend_white"),  # clipped to 1.0 in the brief
        (4.0, 1.0, 0, "at least 1"),  # np.clip(x, 1.0, 0.0) returns 0.0
    ],
)
def test_n_eff_trend_validates_its_inputs(var_gls, var_white, n, match):
    """Variances are positive and n is at least one.

    Bug this catches, case by case: var_gls = 0 divides by zero; var_gls < 0 is
    non-physical and the brief's clip silently reports 1.0; var_white <= 0 is
    likewise hidden by the clip; and n = 0 makes np.clip's bounds cross, which
    numpy resolves by taking the upper bound, so the brief returns 0.0 -- an
    effective sample size of zero reported for an empty series instead of an
    error.
    """
    with pytest.raises(ValueError, match=match):
        n_eff_trend(_f(var_gls), _f(var_white), _i(n), outcome=OK)
