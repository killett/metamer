"""Parameter counting per objective, and the two effective sample sizes.

TWO DEFINITIONS ON TWO MODEL CLASSES, NOT ONE WITH A CORRECTION.
----------------------------------------------------------------
ML and REML are not the same model counted two ways. Under REML the objective
is the likelihood of a maximal set of error contrasts `A'y` with `A'X = 0`: a
DIFFERENT random quantity from `y`, whose distribution does not involve `beta`
at all. So `beta` is not a parameter of that model and not a thing REML
estimates; and the contrast vector has `n_obs - rank(X_r)` components, which is
the sample size of the likelihood actually being maximized.

    ML:   k = k_theta + rank(X_r)      n = n_obs
    REML: k = k_theta                  n = n_obs - rank(X_r)

Writing REML's `k` as "ML's `k` minus `k_beta`" invites the reading that one of
them is a bookkeeping adjustment to the other, and that reading is how `k_beta`
ends up subtracted twice or added back at the criterion. Each line above is a
definition stated on its own model.

`k_beta` IS `rank(X_r)`, NOT `ncol(X)` -- UNDER BOTH OBJECTIVES.
----------------------------------------------------------------
The design doc requires REML's `n` to subtract `rank(X)` rather than `ncol(X)`.
This module makes ML's `k` count the same rank, for three reasons:

  * A criterion penalizes parameters ESTIMATED FROM THE DATA. When `X_r` is
    rank deficient only `rank(X_r)` independent linear combinations of `beta`
    are identified; the remaining `ncol - rank` directions are fixed by
    whatever convention the solver applies (a minimum-norm choice), not by the
    data. Counting them charges the candidate for parameters the record never
    informed.
  * The alternative is internally inconsistent: at one grid point, for one
    design, ML would assert the data supports `ncol` coefficients while REML
    asserts it supports `rank`. ML and REML differ in WHETHER `beta` is a
    parameter, not in HOW MANY of them the data can resolve.
  * The store schema (design doc section 12) holds `k[y,x,m]` -- per point AND
    per candidate. With `ncol` and a shared design, ML's `k` would be constant
    over the entire grid; it varies only because the mask changes `rank(X_r)`
    from point to point, which is exactly the per-point variation that schema
    anticipates.

CURRENT REACHABILITY. Task 8 fails a rank-deficient `X_r` (RANK_DEFICIENT_X)
before it is ever scored, so through the committed pipeline no series reaches
this module with `outcome == OK` and `design_rank < k_beta`. The ruling is
therefore not observable end to end TODAY. It is implemented and tested at this
function's own boundary because (a) `penalty_terms` is a pure function that
Task 10's criteria call directly, and (b) the moment a pseudo-inverse GLS path
or a relaxed rank policy lands, the distinction becomes live -- and a counting
rule decided at that point, under pressure, is decided wrongly.

COUNT WITH `design_rank`, NEVER WITH `rank_x`.
---------------------------------------------
`ObjectiveResult` carries two ranks. `design_rank` is `rank(X_r)`: theta-free, a
property of the design restricted to that series' unmasked rows, and the rank
Harville's `(n - rank(X)) log 2 pi` constant was computed with in `objective`.
`rank_x` is the rank of the WHITENED Gram `X_r' Sigma^-1 X_r`, theta-dependent,
and it is **-1 wherever the outcome is not OK**. That sentinel is a clean
comparison and a silent disaster under arithmetic: `n_obs - (-1)` is
`n_obs + 1`, a sample size larger than the observation count, which looks
entirely plausible inside BIC. `design_rank` carries no sentinel by contract, so
this module treats ANY negative rank as proof that the wrong field was passed
and refuses it -- on every series, including the failed ones, because the failed
ones are precisely where `rank_x`'s sentinel lives.

EVERYTHING PER SERIES.
----------------------
`n_obs`, `design_rank`, `outcome` and both effective sample sizes are `(B,)`.
`k` and `n` come back as float64 rather than int, because a failed series must
carry NaN -- not -inf, which survives some finiteness checks and poisons a
downstream mean, and not a plausible integer, which is worse. That matches the
store, where `k` is float64.
"""

from __future__ import annotations

from typing import Literal

import numpy as np
from numpy.typing import NDArray

from metamer.core.capability import Objective
from metamer.core.outcomes import Outcome
from metamer.core.statespace import UNIQUE_DT_RTOL, StateSpace
from metamer.core.terms import ProcessSpec

MAX_PAIR_BYTES: int = 1 << 20
"""Byte budget for ONE BLOCK of either `n_eff_bic` path. The module's one knob.

BOTH paths block against this budget, for the same reason and with the same
consequence: peak memory is a bounded multiple of it rather than a function of
the problem size. What each path blocks over differs.

**Dense path -- blocks over ROWS of the lag matrix.** The sum over realized
pairs is `O(n_used^2)` in TIME by definition, but it need not be `O(n_used^2)`
in SPACE. Measured peak (tracemalloc, matern12, complete series):

    n_used      blocked at 1 MiB      unblocked
       402             5.2 MB            6.5 MB
      1000             6.3 MB           40.0 MB
      2000             6.2 MB          160.0 MB
      4000             6.1 MB          640.0 MB

The blocked column is flat, at about six times this budget: the lag block, its
contiguous copy, and the four temporaries `StateSpace.acvf` allocates on the way
to a correlation. Six times a bounded number is bounded; `n_used^2` is not.

**FFT path -- blocks over SERIES.** Its per-series cost is small but its batch
cost is not, and the batch is the thing that scales. Measured at `N = 630`,
UNBLOCKED:

    B          peak        per series
      100      3.5 MB       35.4 kB
      500     17.7 MB       35.3 kB
     1000     35.3 MB       35.3 kB
     2000     70.6 MB       35.3 kB

Flat at 56 bytes per epoch per series, hence **3.5 GB at the 100 000-series
tile this module's own docstrings quote** -- against a 16 GB whole-job budget
(design doc section 11). Blocking over series is exact, because each series'
pair counts and autocorrelations are independent of every other's, so it costs
nothing but a loop. Without it the RARE path (dense, irregular axes) would be
the only capped one while the COMMON path (regular axes) scaled without bound,
which is precisely backwards.
"""

_FFT_BYTES_PER_EPOCH: int = 64
"""Peak bytes the FFT path holds per epoch per series, for sizing its block.

MEASURED, not derived: 56.1 B/epoch/series at `N = 630`, flat from B = 100 to
B = 2000 (see `MAX_PAIR_BYTES`). Rounded up to 64 for headroom, since the exact
count depends on how many temporaries numpy's FFT keeps live and on the term
count of the composite. Sizing a block with a measured constant is honest about
being an estimate; the test that pins the resulting peak is what makes it safe.
"""

_ACF_MAGNITUDE_TOL: float = 1e-9
"""Slack on `|rho| <= 1` before an autocorrelation is refused.

A model autocorrelation is `acvf(tau) / acvf(0)` and cannot exceed 1 in exact
arithmetic. A composite sums per-term autocovariances, so the ratio can land an
ulp or two above 1 by rounding. The tolerance absorbs that and nothing else: a
value of 1.5, which the participation ratio would happily turn into `n_eff` of
0.449 at `n = 50`, is nowhere near it.

CONSEQUENCE FOR THE ADVERTISED RANGE. The UPPER bound `n_eff <= n_used` is
structural and exact: `rho_0` is `acvf(0)/acvf(0) = 1` identically, so the
Frobenius sum is at least the `n_used` diagonal entries whatever the
off-diagonals do. The LOWER bound is not quite 1. Correlations admitted at the
tolerance ceiling give a sum up to `n_used^2 (1 + tol)^2`, hence

    n_eff >= 1 / (1 + tol)^2  ~  1 - 2 * tol  =  1 - 2e-9

so the honest range is `[1 - 2e-9, n_used]`, and exactly `[1, n_used]` for any
autocorrelation that respects `|rho| <= 1`. The two-nanosecond-wide gap is
stated rather than clamped away: clamping would silently repair an input this
module has otherwise decided to refuse, and 2e-9 is far below any scale at
which an effective sample size is read.
"""

_Path = Literal["auto", "fft", "dense"]


def _scored(outcome: NDArray[np.uint8], batch: int, name: str) -> NDArray[np.bool_]:
    """Return the per-series mask of series whose values are meaningful.

    Gating on `Outcome.OK` -- rather than on `is_failure`, which tolerates
    NOT_ATTEMPTED and INSUFFICIENT_DATA -- matches the store's bidirectional
    status invariant: non-OK implies NaN in every value slot, so a non-OK
    series has no finite quantities for this module to count with.

    Args:
        outcome: Per-series outcome codes, shape (B,) uint8.
        batch: The batch size every per-series argument must have.
        name: Argument name to quote in the error message.

    Returns:
        Boolean mask, shape (B,), True where the series was scored.

    Raises:
        ValueError: If `outcome` is not one-dimensional of length `batch`.
    """
    arr = np.asarray(outcome)
    if arr.ndim != 1 or arr.shape[0] != batch:
        raise ValueError(
            f"{name} must have shape ({batch},) to match the batch, "
            f"got shape {arr.shape}"
        )
    return np.asarray(arr.astype(np.int64) == Outcome.OK.code, dtype=np.bool_)


def _per_series_int(
    value: NDArray[np.int64], batch: int, name: str
) -> NDArray[np.int64]:
    """Coerce a per-series integer argument and check its shape.

    Args:
        value: The candidate array.
        batch: Required length.
        name: Argument name to quote in the error message.

    Returns:
        The array as int64, shape (B,).

    Raises:
        ValueError: If the array is not one-dimensional of length `batch`.
    """
    arr = np.asarray(value)
    if arr.ndim != 1 or arr.shape[0] != batch:
        raise ValueError(
            f"{name} must have shape ({batch},) to match the batch, "
            f"got shape {arr.shape}"
        )
    return np.asarray(arr, dtype=np.int64)


def penalty_terms(
    spec: ProcessSpec,
    objective: Objective,
    *,
    n_obs: NDArray[np.int64],
    design_rank: NDArray[np.int64],
    outcome: NDArray[np.uint8],
    k_beta: int,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Return the per-series `(k, n)` an information criterion penalizes with.

    Two definitions, one per objective -- see the module docstring for why they
    are stated as definitions on different model classes rather than as one
    count with an adjustment:

        ML:   k = k_theta + rank(X_r)     n = n_obs
        REML: k = k_theta                 n = n_obs - rank(X_r)

    Args:
        spec: The noise specification, supplying `k_theta` through
            `ProcessSpec.n_theta`. Parameters with `fixed=True` are excluded.
        objective: `Objective.ML` or `Objective.REML`.
        n_obs: Unmasked observation count PER SERIES, shape (B,) int64. This is
            `ObjectiveResult.n_used`, which carries no sentinel.
        design_rank: `rank(X_r)` PER SERIES, shape (B,) int64. This is
            `ObjectiveResult.design_rank` and **never** `ObjectiveResult.rank_x`
            -- see the module docstring. Zero when there is no design.
        outcome: Per-series outcome codes, shape (B,) uint8. Series whose
            outcome is not OK get NaN in both returned arrays and their
            `n_obs` and `design_rank` are never used arithmetically.
        k_beta: Number of design columns, `ncol(X)`. Shared across the batch in
            Phase 1. Used only as the upper bound `design_rank <= k_beta`; the
            counts themselves use the rank.

    Returns:
        `(k, n)`, both shape (B,) float64, NaN wherever `outcome` is not OK.

    Raises:
        ValueError: If `k_beta` is negative; if the per-series arrays do not all
            have shape `(B,)`; if any `n_obs` is negative; if any `design_rank`
            is negative (which is the `rank_x` failure sentinel, not a rank) or
            exceeds `k_beta`; or if a SCORED series has no error contrasts left
            under REML, `n_obs - design_rank <= 0`, which would put `log(0)` in
            every criterion.
        NotImplementedError: If `spec` declares cross-term shared parameters.
            `ProcessSpec.n_theta` refuses them, because Phase 1 implements no
            sharing mechanism and counting a shared parameter once per term
            would overstate `k_theta`.
    """
    k_theta = spec.n_theta()
    if int(k_beta) < 0:
        raise ValueError(
            f"k_beta is a column count and cannot be negative, got {k_beta}"
        )

    counts = np.asarray(n_obs)
    batch = int(counts.shape[0]) if counts.ndim == 1 else -1
    if batch < 0:
        raise ValueError(f"n_obs must be one-dimensional, got shape {counts.shape}")
    counts = _per_series_int(counts, batch, "n_obs")
    ranks = _per_series_int(design_rank, batch, "design_rank")
    scored = _scored(outcome, batch, "outcome")

    if bool(np.any(counts < 0)):
        raise ValueError(
            "n_obs is an observation count and cannot be negative, got "
            f"{counts[counts < 0].tolist()}"
        )
    # Checked on EVERY series, not just the scored ones: design_rank carries no
    # sentinel by contract, whereas rank_x is -1 exactly on the failed series,
    # so restricting this to scored series would miss the substitution it exists
    # to catch.
    if bool(np.any(ranks < 0)):
        raise ValueError(
            "design_rank cannot be negative; a -1 is ObjectiveResult.rank_x's "
            "failure sentinel, not a rank -- pass design_rank, which carries no "
            f"sentinel. Got {ranks[ranks < 0].tolist()}"
        )
    if bool(np.any(ranks > int(k_beta))):
        raise ValueError(
            f"design_rank cannot exceed k_beta = {k_beta} columns, got "
            f"{ranks[ranks > int(k_beta)].tolist()}"
        )

    k = np.full(batch, np.nan, dtype=np.float64)
    n = np.full(batch, np.nan, dtype=np.float64)
    if objective is Objective.REML:
        contrasts = counts - ranks
        if bool(np.any(scored & (contrasts <= 0))):
            raise ValueError(
                "REML has no error contrasts left for a scored series: "
                f"n_obs - design_rank <= 0 at index "
                f"{np.flatnonzero(scored & (contrasts <= 0)).tolist()}, which "
                "puts log(0) in every criterion"
            )
        k[scored] = float(k_theta)
        n[scored] = contrasts[scored].astype(np.float64)
        return k, n

    k[scored] = float(k_theta) + ranks[scored].astype(np.float64)
    n[scored] = counts[scored].astype(np.float64)
    return k, n


def n_eff_bic_closed_form(autocorrelation: NDArray[np.float64], n: int) -> float:
    """Participation ratio for a COMPLETE, REGULARLY SAMPLED series.

    **NOT WIRED INTO `n_eff_bic`'S DISPATCH, DELIBERATELY.** This is a reference
    form and a cross-check, not a fast path: `n_eff_bic`'s FFT path is already
    `O(N)` per series and provably reduces to this expression when the mask is
    all-true (`c_k = n - k`), so routing the complete case here would buy no
    time and would add a third code path to keep in agreement. Design doc
    section 10.1 asks for the closed form to be KEPT AND CHECKED AGAINST the
    general one -- that agreement is the cheapest available evidence that the
    realized-pairs machinery is right -- which is exactly the role it has here.
    Its only callers are tests, and that is the intent.

    For a Toeplitz correlation matrix the lag-`k` off-diagonal has exactly
    `(n - k)` entries on each side, so

        ||R||_F^2 = n + 2 * sum_{k=1}^{n-1} (n - k) * rho_k^2

    and `n_eff = n^2 / ||R||_F^2` without ever forming `R`.

    **THIS FORM IS WRONG UNDER A MASK.** With gaps the pairs actually present
    are not the `(n - k)` the lag-`k` count implies. Measured at `N = 200`,
    `rho(tau) = exp(-tau/10)`, keeping every other sample: the realized-pairs
    answer is 20.2300 and this form fed the model ACF at lag INDEX gives
    10.4877, an error of -48.2%. Use `n_eff_bic` for anything with a mask; this
    function exists to be checked against it on the complete regular case,
    which is the cheapest available check that the general form is right.

    Args:
        autocorrelation: `rho_k` for k = 1 .. n-1, shape (n-1,). The MODEL
            autocorrelation at the fitted theta, not a residual statistic.
        n: Series length; the number of observations, all of them used.

    Returns:
        Effective sample size, at most `n` exactly and at least
        `1 - 2 * _ACF_MAGNITUDE_TOL`; exactly 1 for any `|rho| <= 1`.

    Raises:
        ValueError: If `n < 1`; if `autocorrelation` is not one-dimensional of
            length exactly `n - 1` (an over-long array drives `(n - k)`
            negative and the ratio with it -- measured -0.080 at n = 10 with 50
            lags of 0.9; a short one is silently zero-padded and reports the
            full `n`); or if any `|rho_k|` exceeds 1 by more than
            `_ACF_MAGNITUDE_TOL`, which no autocorrelation can and a broken fit
            can (1.5 throughout gives 0.449 at n = 50).
    """
    length = int(n)
    if length < 1:
        raise ValueError(f"n must be at least 1 observation, got {length}")
    rho = np.asarray(autocorrelation, dtype=np.float64)
    if rho.ndim != 1 or rho.size != length - 1:
        raise ValueError(
            "autocorrelation must hold rho_k for k = 1 .. n - 1, i.e. "
            f"{length - 1} values for n = {length}, got shape {rho.shape}"
        )
    _check_magnitude(rho)
    lags = np.arange(1.0, float(length))
    frobenius = float(length) + 2.0 * float(np.sum((length - lags) * rho**2))
    return float(length * length / frobenius)


def n_eff_bic(
    state_space: StateSpace,
    theta: NDArray[np.float64],
    t: NDArray[np.float64],
    *,
    mask: NDArray[np.bool_],
    outcome: NDArray[np.uint8],
    path: _Path = "auto",
    max_pair_bytes: int = MAX_PAIR_BYTES,
    rtol: float = UNIQUE_DT_RTOL,
) -> NDArray[np.float64]:
    """Effective sample size for the BIC penalty, over REALIZED pairs.

    The participation ratio `n_eff = n^2 / ||R||_F^2` on the model correlation
    matrix, evaluated in the form that stays correct under a mask and on an
    arbitrary time axis:

        n_eff = n_used^2 / sum_{i,j in used} rho(t_i - t_j)^2

    which reduces to `n_eff_bic_closed_form` when the series is complete and
    regular. Chosen because it is confined to `[1, n_used]`, always well defined,
    monotone in correlation strength, depends only on `|rho|` so negative
    correlation cannot inflate it, and degrades gracefully for a near-degenerate
    fit. The classic `n / (1 + 2 sum rho_k)` alternative is the effective size
    for estimating A MEAN, can exceed `n` or go negative, and needs windowing
    choices that would then need defending.

    **`rho` COMES FROM THE FITTED MODEL, NOT FROM THE DATA.** It is derived here
    as `state_space.acvf(theta, tau) / state_space.acvf(theta, 0)` -- the
    family's analytic autocovariance at the fitted `theta`. The `StateSpace`
    argument exists so that provenance is structural rather than a convention: a
    residual autocorrelation cannot be passed to this function. That is what
    makes `n_eff_bic` a function of the SELECTED MODEL, hence stored per
    `(point, candidate)` as `n_eff_bic[y,x,m]`.

    **NEVER CALL THIS INSIDE A FIT.** It is `O(n_used^2)` in time by definition
    -- roughly 400 000 autocovariance evaluations per series at `N = 630`.
    Compute it ONCE, after convergence, per `(point, candidate)`.

    Two evaluation paths, dispatched on whether the axis is regular:

      * **fft** (regular axis, the common case, since gaps are usually missing
        samples from an even grid). The realized pair count at lag `k` is the
        linear autocorrelation of the mask indicator, `c_k = sum_i m_i m_{i+k}`,
        obtained exactly from one zero-padded FFT; then
        `||R||_F^2 = c_0 + 2 sum_{k>=1} c_k rho_k^2`, with `c_0 = n_used`. This
        is exact, not an approximation, and reduces to the closed form's
        `(n - k)` when the mask is all-true. Peak allocation is `O(B * N)`, not
        `O(n_used^2)`: measured at 42 kB for one series at `N = 630` under a
        35% mask, and 262 kB at `N = 4000`.
      * **dense** (irregular axis). The FFT trick needs every `t_i - t_j` to be
        an integer multiple of a common step; on a genuinely irregular axis the
        lags do not bin and it is simply wrong. The fallback sums over realized
        pairs directly, BLOCKED OVER ROWS so the largest allocation is bounded
        by `max_pair_bytes` regardless of `n_used`, rather than `O(n_used^2)`.
        `StateSpace.acvf` allocates a small constant number of blocks of that
        same shape (one accumulator plus a per-term temporary), so peak memory
        is a small multiple of `max_pair_bytes` and does not grow with the
        series length.

    Regularity is decided by `StateSpace.unique_dt`, which is tolerance-aware
    for the reason given in its own docstring (a float grid rarely has
    bit-identical spacing). An axis that is regular only within `rtol` takes the
    FFT path with the cluster representative as its step, which is the same
    approximation the Kalman memoization already makes.

    Args:
        state_space: Assembled from the candidate `ProcessSpec`; supplies the
            analytic ACVF that `rho` is derived from.
        theta: Fitted NATURAL parameters, shape (B, P) -- the FULL vector
            including any `fixed=True` parameters, matching
            `StateSpace.param_slices`.
        t: Shared time axis, shape (N,), ascending.
        mask: True where a sample is used, shape (B, N). Per series.
        outcome: Per-series outcome codes, shape (B,) uint8. Series whose
            outcome is not OK get NaN and are never evaluated, so their theta
            and mask may hold anything.
        path: `"auto"` dispatches on regularity; `"fft"` and `"dense"` force a
            path, for cross-checking one against the other. `"fft"` is refused
            on an irregular axis rather than silently answering with sample
            index in place of elapsed time.
        max_pair_bytes: Byte budget for one block of EITHER path -- rows of the
            lag matrix for the dense path, series for the FFT path. The
            module's single memory knob; see `MAX_PAIR_BYTES`.
        rtol: Relative tolerance forwarded to `StateSpace.unique_dt`, and
            therefore the tolerance at which an axis counts as regular. A
            looser value routes a near-regular axis to the FFT path with the
            cluster representative as its step.

    Returns:
        Effective sample size per series, shape (B,) float64, NaN wherever
        `outcome` is not OK. The upper bound `n_eff <= n_used` is exact and
        structural; the lower bound is `1 - 2 * _ACF_MAGNITUDE_TOL` = 1 - 2e-9
        in the worst case this module admits, and exactly 1 for any
        autocorrelation satisfying `|rho| <= 1`. See `_ACF_MAGNITUDE_TOL`.

    Raises:
        ValueError: If `path` is not one of the three names; if `theta`, `mask`
            or `outcome` do not describe one batch over one time axis; if
            `path="fft"` is forced on an irregular axis; if a SCORED series is
            wholly masked (`n_used == 0` divides by zero and no effective sample
            size exists); if a scored series' marginal variance `acvf(0)` is not
            positive (the normalization would divide by zero and produce
            correlations that still sum to a plausible-looking number); or if a
            derived `|rho|` exceeds 1 beyond `_ACF_MAGNITUDE_TOL`.
    """
    if path not in ("auto", "fft", "dense"):
        raise ValueError(f"path must be 'auto', 'fft' or 'dense', got {path!r}")

    params = np.asarray(theta, dtype=np.float64)
    if params.ndim != 2:
        raise ValueError(f"theta must have shape (B, P), got shape {params.shape}")
    axis = np.asarray(t, dtype=np.float64)
    if axis.ndim != 1:
        raise ValueError(f"t must have shape (N,), got shape {axis.shape}")
    batch = int(params.shape[0])
    used = np.asarray(mask, dtype=np.bool_)
    if used.shape != (batch, axis.size):
        raise ValueError(
            f"mask must have shape ({batch}, {axis.size}) to match theta and t, "
            f"got shape {used.shape}"
        )
    scored = _scored(outcome, batch, "outcome")

    out = np.full(batch, np.nan, dtype=np.float64)
    rows = np.flatnonzero(scored)
    if rows.size == 0:
        return out

    n_used = np.count_nonzero(used[rows], axis=1).astype(np.int64)
    if bool(np.any(n_used == 0)):
        raise ValueError(
            "a scored series is wholly masked: n_used == 0 at index "
            f"{rows[n_used == 0].tolist()}, which has no effective sample size"
        )

    steps = StateSpace.unique_dt(axis, rtol=rtol)
    regular = steps.size == 0 or (steps.size == 1 and float(steps[0]) > 0.0)
    chosen = path if path != "auto" else ("fft" if regular else "dense")
    if chosen == "fft" and not regular:
        raise ValueError(
            "path='fft' needs a regular ascending axis: it counts realized "
            "pairs per integer lag index, and on an irregular axis the lags do "
            f"not bin. unique_dt found {steps.size} distinct steps"
        )

    if chosen == "fft":
        step = float(steps[0]) if steps.size else 1.0
        frobenius = _frobenius_fft(
            state_space, params[rows], axis.size, step, used[rows], max_pair_bytes
        )
    else:
        frobenius = np.array(
            [
                _frobenius_dense(
                    state_space, params[b : b + 1], axis[used[b]], max_pair_bytes
                )
                for b in rows
            ],
            dtype=np.float64,
        )

    out[rows] = n_used.astype(np.float64) ** 2 / frobenius
    return out


def n_eff_trend(
    var_trend_gls: NDArray[np.float64],
    var_trend_white: NDArray[np.float64],
    n: NDArray[np.int64],
    *,
    outcome: NDArray[np.uint8],
) -> NDArray[np.float64]:
    """Effective sample size for ESTIMATING THE TREND. Not the BIC penalty's n.

    `n * var_white / var_gls`, clipped to `[1, n]`: the number of independent
    samples that would determine the trend as precisely as this correlated
    record does. It is TERM-SPECIFIC -- a property of one estimand under the
    fitted `Sigma`, not a whole-series effective count -- so substituting it for
    `n_eff_bic` is a category error, and the two are named apart here so that
    they cannot be interchanged by accident. Design doc section 10.1. Used by
    the ML-versus-REML rule of thumb (section 16.2) and by coverage diagnostics.

    Like `n_eff_bic` this is a function of the FITTED model, through `Sigma`, so
    it is stored per `(point, candidate)` as `n_eff_trend[y,x,m]`.

    The clip is part of the definition, both ends. Strong negative correlation
    can make a trend better determined than `n` independent samples would; the
    quantity is nevertheless reported as an effective count of the record's own
    observations, so it is capped at `n`.

    Args:
        var_trend_gls: Variance of the GLS trend estimate under the fitted noise
            model, PER SERIES, shape (B,).
        var_trend_white: Variance the same trend estimate would have under white
            noise of the same marginal variance, PER SERIES, shape (B,).
        n: Unmasked observation count per series, shape (B,) int64.
        outcome: Per-series outcome codes, shape (B,) uint8. Non-OK series get
            NaN and their variances are never used arithmetically.

    Returns:
        Effective sample size per series, shape (B,) float64, in `[1, n]`, NaN
        wherever `outcome` is not OK.

    Raises:
        ValueError: If the per-series arrays do not all have shape `(B,)`; or,
            for a SCORED series, if `n < 1` (`np.clip(x, 1.0, 0.0)` has crossed
            bounds and numpy resolves that by returning the upper one, so an
            empty series would otherwise report an effective sample size of
            0.0), or if either variance is not strictly positive and finite
            (zero divides by zero; a negative one is non-physical and the clip
            would report a tidy 1.0; NaN would pass every comparison and
            silently produce NaN for a series whose outcome reads OK).
    """
    gls = np.asarray(var_trend_gls, dtype=np.float64)
    if gls.ndim != 1:
        raise ValueError(f"var_trend_gls must have shape (B,), got {gls.shape}")
    batch = int(gls.shape[0])
    white = np.asarray(var_trend_white, dtype=np.float64)
    if white.shape != (batch,):
        raise ValueError(
            f"var_trend_white must have shape ({batch},) to match "
            f"var_trend_gls, got shape {white.shape}"
        )
    counts = _per_series_int(n, batch, "n")
    scored = _scored(outcome, batch, "outcome")

    if bool(np.any(counts[scored] < 1)):
        raise ValueError(
            "n must be at least 1 observation for a scored series, got "
            f"{counts[scored][counts[scored] < 1].tolist()}"
        )
    if not bool(np.all(gls[scored] > 0.0)):
        raise ValueError(
            "var_trend_gls must be a positive finite variance for a scored "
            f"series, got {gls[scored][~(gls[scored] > 0.0)].tolist()}"
        )
    if not bool(np.all(white[scored] > 0.0)):
        raise ValueError(
            "var_trend_white must be a positive finite variance for a scored "
            f"series, got {white[scored][~(white[scored] > 0.0)].tolist()}"
        )

    out = np.full(batch, np.nan, dtype=np.float64)
    limit = counts[scored].astype(np.float64)
    ratio = limit * white[scored] / gls[scored]
    out[scored] = np.clip(ratio, 1.0, limit)
    return out


def _check_magnitude(rho: NDArray[np.float64]) -> None:
    """Refuse an autocorrelation whose magnitude exceeds 1.

    Args:
        rho: Correlations to check; may be any shape, may be empty.

    Raises:
        ValueError: If any finite entry exceeds 1 by more than the tolerance.
    """
    if rho.size == 0:
        return
    worst = float(np.max(np.abs(rho)))
    if worst > 1.0 + _ACF_MAGNITUDE_TOL:
        raise ValueError(
            "autocorrelation magnitude cannot exceed 1; the largest is "
            f"{worst!r}, which no ACF produces and a broken fit does"
        )


def _model_acf(
    state_space: StateSpace, theta: NDArray[np.float64], lags: NDArray[np.float64]
) -> NDArray[np.float64]:
    """Return `acvf(lags) / acvf(0)`, the model autocorrelation.

    Args:
        state_space: Supplies the analytic autocovariance.
        theta: Natural parameters, shape (S, P).
        lags: Lags to evaluate, shape (L,). Need not contain zero.

    Returns:
        Autocorrelations, shape (S, L).

    Raises:
        ValueError: If any series' marginal variance `acvf(0)` is not strictly
            positive and finite, or if a derived magnitude exceeds 1.
    """
    variance = state_space.acvf(theta, np.zeros(1, dtype=np.float64))[:, 0]
    if not bool(np.all(variance > 0.0)):
        raise ValueError(
            "marginal variance acvf(0) must be positive and finite to form an "
            f"autocorrelation, got {variance[~(variance > 0.0)].tolist()}"
        )
    rho = state_space.acvf(theta, lags) / variance[:, None]
    _check_magnitude(rho)
    return np.asarray(rho, dtype=np.float64)


def _lag_pair_counts(mask: NDArray[np.bool_]) -> NDArray[np.float64]:
    """Return the exact realized pair count per integer lag, `c_k`.

    `c_k = sum_i m_i * m_{i+k}` for k = 0 .. N-1, the LINEAR autocorrelation of
    the mask indicator. Computed through one FFT zero-padded to `2N`, which is
    at least the `2N - 1` needed for the circular correlation to coincide with
    the linear one; a shorter transform would fold long lags onto short ones.
    The counts are integers by construction, so the transform's rounding is
    removed with `rint` and the result is exact.

    Args:
        mask: True where used, shape (S, N).

    Returns:
        Pair counts, shape (S, N) float64, integer-valued. `c_0` is `n_used`.
    """
    length = int(mask.shape[1])
    padded = 2 * length
    spectrum = np.fft.rfft(mask.astype(np.float64), n=padded, axis=1)
    correlation = np.fft.irfft(spectrum * np.conjugate(spectrum), n=padded, axis=1)
    return np.asarray(np.rint(correlation[:, :length]), dtype=np.float64)


def _frobenius_fft(
    state_space: StateSpace,
    theta: NDArray[np.float64],
    length: int,
    step: float,
    mask: NDArray[np.bool_],
    max_pair_bytes: int = MAX_PAIR_BYTES,
) -> NDArray[np.float64]:
    """Return `||R||_F^2` over realized pairs on a REGULAR axis, per series.

    `sum_{i,j in used} rho(t_i - t_j)^2 = c_0 + 2 * sum_{k>=1} c_k * rho_k^2`,
    where `c_k` is the realized pair count at lag `k` and `rho_k` the model
    autocorrelation at elapsed lag `k * step`. Exact for any mask; reduces to
    `n + 2 sum (n-k) rho_k^2` when the mask is all-true, because then
    `c_k = n - k`.

    BLOCKED OVER SERIES against `max_pair_bytes`. Per series this path is cheap,
    but `O(B * N)` over a whole tile is not: unblocked it reaches 3.5 GB at
    100 000 series and `N = 630`. Series are independent here -- one series'
    pair counts and autocorrelations involve no other's -- so blocking is exact
    and costs only a loop. See `MAX_PAIR_BYTES` for the measurements.

    Args:
        state_space: Supplies the analytic ACVF.
        theta: Natural parameters of the scored series, shape (S, P).
        length: Number of epochs on the axis, N.
        step: The single distinct timestep of the axis.
        mask: True where used, shape (S, N).
        max_pair_bytes: Byte budget for one block of series.

    Returns:
        The Frobenius sum per series, shape (S,).

    Raises:
        ValueError: Propagated from `_model_acf` if a marginal variance is not
            positive or a derived `|rho|` exceeds 1 beyond the tolerance.
    """
    lags = np.arange(float(length)) * step
    per_series = max(1, length * _FFT_BYTES_PER_EPOCH)
    block = max(1, int(max_pair_bytes) // per_series)
    out = np.empty(theta.shape[0], dtype=np.float64)
    for start in range(0, theta.shape[0], block):
        stop = start + block
        rho = _model_acf(state_space, theta[start:stop], lags)
        counts = _lag_pair_counts(mask[start:stop])
        tail = np.sum(counts[:, 1:] * rho[:, 1:] ** 2, axis=1)
        out[start:stop] = counts[:, 0] + 2.0 * tail
    return out


def _frobenius_dense(
    state_space: StateSpace,
    theta: NDArray[np.float64],
    t_used: NDArray[np.float64],
    max_pair_bytes: int,
) -> float:
    """Return `||R||_F^2` over realized pairs for ONE series, any axis.

    The definition summed directly, blocked over rows. The block is at most
    `max_pair_bytes` regardless of `n_used`, so peak memory is bounded rather
    than `O(n_used^2)`. Measured peak is about six times the budget -- the lag
    block, its contiguous copy, and the temporaries `StateSpace.acvf` allocates
    -- and it stays there: 6.3 MB at `n_used = 1000` and 6.1 MB at 4000, where
    the unblocked sum needs 40 MB and 640 MB. See `MAX_PAIR_BYTES`.

    Args:
        state_space: Supplies the analytic ACVF.
        theta: Natural parameters for this one series, shape (1, P).
        t_used: Timestamps of the unmasked epochs, shape (n_used,).
        max_pair_bytes: Byte budget for one block of the lag matrix.

    Returns:
        The Frobenius sum for this series.

    Raises:
        ValueError: Propagated from `_model_acf` if this series' marginal
            variance is not positive or a derived `|rho|` exceeds 1 beyond the
            tolerance.
    """
    n_used = int(t_used.size)
    rows_per_block = max(1, int(max_pair_bytes) // (n_used * 8))
    total = 0.0
    for start in range(0, n_used, rows_per_block):
        block = t_used[start : start + rows_per_block, None] - t_used[None, :]
        rho = _model_acf(state_space, theta, block.ravel())[0].reshape(block.shape)
        total += float(np.sum(rho * rho))
    return total
