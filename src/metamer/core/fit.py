"""The (B, N) fit driver. B = 1 is a shape, never a separate code path.

WHAT THIS MODULE IS FOR.
------------------------
Every per-series contract established in Tasks 8-13 has to hold here at once,
and this is the single place where the per-series scalar world of
`optimize.SeriesFit` becomes the `(B, M)` arrays the store, `counting` and
`criteria` all speak. The conversion happens **once**. Doing it at each
consumer instead means writing it three times, and a conversion written three
times is one that will disagree with itself once.

OUTCOMES ARE `(B, M)` uint8 CODES.
----------------------------------
Not an object array of `Outcome` members. The codes are what the zarr store
writes, what `counting.penalty_terms(outcome=)` gates on, and what
`criteria.CandidateScores.outcome` takes. The give-away that something is
holding members instead is a test written `outcome[b, c] is Outcome.OK`, which
is False against a uint8 and silently skips whatever it guards.

THE SELECTION LAYER IS `rank_candidates`, NOT A LOCAL ARGMIN.
-------------------------------------------------------------
Going through it is what puts the design doc §6.2 comparability guards on the
real path. A hand-rolled argmin here would leave those guards tested in
`test_criteria.py` and never executed in production, which is the same as not
having them.

BOTH EFFECTIVE SAMPLE SIZES ARE COMPUTED HERE, ONCE, AT THE OPTIMUM.
--------------------------------------------------------------------
`n_eff_bic` and `n_eff_trend` are both functions of the FITTED model, so both
are per `(point, candidate)` and neither can be computed before convergence.
They are stored primitives (design doc §12.2) and must not be left unwritten:
a primitive that quietly never appears is the failure the schema exists to
prevent, and it would first surface in Phase 2 as an all-NaN zarr array.

`n_eff_trend` is term-specific -- it is the effective sample size for
estimating THE TREND -- so it needs to know which design column that is.
`DesignInfo.trend_column` answers by name; assuming index 1 holds only for the
`[Constant, Trend, ...]` ordering fixtures use, and with `[Annual(), Trend()]`
the reported number would be a seasonal amplitude's, labelled as a trend's.
Where the design has no trend at all the value is **NaN**, not zero and not
some other column's number.

REPORTED UNCERTAINTIES ARE NATURAL-UNIT AND FIRST-ORDER.
--------------------------------------------------------
`theta_err` comes from the unconstrained Hessian pushed through
`transforms.delta_method_cov`. That is exact only to first order: under a `Log`
transform the true variance exceeds the delta-method value by
`(e^s − 1)e^s / s` with `s = σ_u²` -- **1.5% at σ_u = 0.1, 46% at 0.5, 367% at
1.0** (measured, `optimize.py`). Large `σ_u` is the regime near a diagnostic
limit, which is exactly where `Outcome.DIAGNOSTIC_LIMIT` fires -- so a
consumer reading `theta_err` should read the outcome beside it.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from metamer.core.capability import EngineId, GradientMode, Objective
from metamer.core.counting import n_eff_bic, n_eff_trend, penalty_terms
from metamer.core.criteria import CandidateScores, Criterion, Ranking, rank_candidates
from metamer.core.engines.kalman import KalmanEngine
from metamer.core.engines.protocol import Engine
from metamer.core.gradients import resolve_gradient_mode
from metamer.core.objective import ConcentratedObjective
from metamer.core.optimize import DEFAULT_MAX_ITER, InitRung, optimize_series
from metamer.core.outcomes import Outcome
from metamer.core.signal import SignalSpec
from metamer.core.statespace import StateSpace
from metamer.core.terms import ProcessSpec, free_param_index
from metamer.core.transforms import delta_method_cov


@dataclass(frozen=True)
class FitResult:
    """Results for a batch of series across a candidate set.

    Attributes:
        candidates: The noise specifications, in the order of the model axis.
        theta: Natural-unit free parameters, shape (B, M, p_max), NaN-padded
            where a candidate has fewer than `p_max` free parameters.
        theta_err: Natural-unit standard errors, same shape. First-order; see
            the module docstring.
        theta_unconstrained: The optimum in unconstrained coordinates, same
            shape. This is what Phase 2 feeds back as `x0`, **paired with an
            `x0_valid` that is false wherever `outcome` is not `OK`** -- those
            rows are all-NaN here, and a source map that marks one valid is
            refused rather than started from.
        beta: Profiled-out signal coefficients, shape (B, M, k_beta).
        beta_err: Their standard errors, same shape.
        loglik: Maximized log-likelihood, shape (B, M). NaN where not OK.
        outcome: Per-(series, candidate) outcome CODES, shape (B, M) uint8.
        init_rung: Which rung of the ladder started each fit, shape (B, M).
        n_iter: Iterations per fit, shape (B, M) int64.
        n_eff_bic: Whole-series effective count from the fitted model's ACF,
            shape (B, M). Stored primitive.
        n_eff_trend: Effective sample size for estimating the TREND, shape
            (B, M). Stored primitive, NaN where the design has no trend column.
            **Never interchangeable with `n_eff_bic`** -- one is a whole-series
            property, the other is term-specific.
        scores: The one `CandidateScores` these results were ranked from.
            **The store's `k` and `n` come from here and from nowhere else** --
            they are per-objective counts from `counting.penalty_terms`, and a
            second call at a second site is a second derivation of a stored
            primitive. It is also what ranks the same fits under a second
            criterion without refitting.
        ranking: ONE `Ranking` spanning the batch, from `rank_candidates`.
        engine: The engine every score came from.
        objective: The objective every score is on.
        gradient_mode: The resolved mode per candidate. This describes what the
            FAMILIES supply, not what the optimizer ran -- Phase 1 has no
            differentiated filter, so finite differences run either way.
    """

    candidates: tuple[ProcessSpec, ...]
    theta: NDArray[np.float64]
    theta_err: NDArray[np.float64]
    theta_unconstrained: NDArray[np.float64]
    beta: NDArray[np.float64]
    beta_err: NDArray[np.float64]
    loglik: NDArray[np.float64]
    outcome: NDArray[np.uint8]
    init_rung: NDArray[np.object_]
    n_iter: NDArray[np.int64]
    n_eff_bic: NDArray[np.float64]
    n_eff_trend: NDArray[np.float64]
    scores: CandidateScores
    ranking: Ranking
    engine: EngineId
    objective: Objective
    gradient_mode: tuple[GradientMode, ...]


def _out_of_limits(
    natural: NDArray[np.float64], limits: tuple[float, float]
) -> NDArray[np.bool_]:
    """Vectorized twin of `params.ParamSpec.at_diagnostic_limit`.

    `at_diagnostic_limit` is scalar, and calling it once per (series,
    candidate, parameter) is a Python loop over the whole tile. This is the
    same rule over an array. **Two spellings of one rule is exactly the
    duplication (j) warns about**, so the agreement is pinned by
    `test_the_vectorised_limit_rule_agrees_with_at_diagnostic_limit`, which
    sweeps both limits exactly rather than sampling near them.

    Args:
        natural: Values in natural units, any shape.
        limits: The parameter's `diagnostic_limits`.

    Returns:
        True where the value is at or beyond either limit. **NaN is False**,
        as it is in the scalar method: NaN is caught by the finiteness check,
        which is separate and runs first.
    """
    lo, hi = limits
    return np.asarray((natural <= lo) | (natural >= hi), dtype=np.bool_)


def warm_start_faults(
    x0: NDArray[np.float64], candidates: list[ProcessSpec]
) -> tuple[NDArray[np.bool_], dict[tuple[int, int], str]]:
    """Which `(series, candidate)` cells hold a start no legitimate source produces.

    **ONE DERIVATION OF THE RULE, TWO CONSUMERS, AND THE SECOND IS WHY THIS IS
    A FUNCTION.** `_check_warm_starts` below turns it into a refusal; Phase 2c's
    hysteresis audit needs it as a **mask**, because its N2 arm displaces the
    start by a real distance in a random direction and can land outside the
    diagnostic box -- at which point the refusal would abort the whole audit
    rather than lose one cell. **Writing a vectorized twin in the audit would be
    the THIRD spelling of the limits rule**: `_out_of_limits` is already the
    second, and it is pinned by a test for exactly this reason.

    **THE TWO FAULTS ARE SEPARATE AND THE ORDER BETWEEN THEM IS LOAD-BEARING.**
    `at_diagnostic_limit` returns False for NaN, so an all-NaN row -- what a
    FAILED fit legitimately writes into `theta_unconstrained` -- would pass a
    limits-only validator in silence. And an infinity fails BOTH: `forward(inf)`
    is `inf`, which is beyond every upper limit. Finiteness is therefore
    reported first, or an `inf` would be described as an out-of-range value
    rather than as a missing one.

    Only the first `p` columns of each candidate's row are inspected. The rest
    of the `p_max` width is NaN by design for any candidate narrower than the
    widest, so a validator reading the full width refuses every well-formed warm
    start but the widest candidate's.

    Args:
        x0: Warm starts in unconstrained coordinates, shape (B, M, p_max).
        candidates: The candidate set, in model-axis order.

    Returns:
        A `(B, M)` boolean admissibility mask, and a mapping from each
        INADMISSIBLE cell to a clause naming the offending parameter and both
        its values. **The mapping holds only faulty cells**, so it is empty on
        the production path and small on the audit's.

    Note:
        **Validity is NOT consulted here.** The mask describes the values, and
        whether a cell was offered as a warm start is a separate question --
        which is what lets the audit ask about cells it has not decided to use
        yet.
    """
    batch, models = x0.shape[0], x0.shape[1]
    admissible = np.ones((batch, models), dtype=np.bool_)
    faults: dict[tuple[int, int], str] = {}

    for c, spec in enumerate(candidates):
        free = free_param_index(spec)
        by_label = dict(zip(spec.labels(), spec.terms, strict=True))
        rows = x0[:, c, : len(free)]
        label = spec.spec_hash()[:12]
        for index, (term_label, name) in enumerate(free):
            param = by_label[term_label].params[name]
            column = np.asarray(rows[:, index], dtype=np.float64)

            # **`& admissible[:, c]` KEEPS THE FIRST FAULT AND DISCARDS THE
            # REST**, which is what the refusal reported when it raised on the
            # first offending parameter. Without it a cell failing two
            # parameters would have its clause overwritten by the later one.
            offending = ~np.isfinite(column) & admissible[:, c]
            for b in np.flatnonzero(offending).tolist():
                faults[(int(b), c)] = (
                    f"its warm start for {term_label}.{name} is "
                    f"{column[b]!r}, which is not finite. Candidate {c} is "
                    f"{label}. A failed fit writes NaN into "
                    f"theta_unconstrained, so a source map that marks it valid "
                    f"is a spiral bug: mark the cell invalid instead."
                )
            admissible[offending, c] = False

            # exp() of a large unconstrained coordinate overflows to inf, which
            # is the correct verdict here rather than a warning.
            with np.errstate(over="ignore"):
                natural = np.asarray(param.transform.forward(column), dtype=np.float64)
            offending = (
                _out_of_limits(natural, param.diagnostic_limits) & admissible[:, c]
            )
            for b in np.flatnonzero(offending).tolist():
                faults[(int(b), c)] = (
                    f"its warm start for {term_label}.{name} is "
                    f"{column[b]!r} in unconstrained coordinates, which is "
                    f"{natural[b]!r} in natural units -- at or beyond its "
                    f"diagnostic limits {param.diagnostic_limits}. Candidate "
                    f"{c} is {label}. An OK fit is strictly inside both limits, "
                    f"so no legitimate source produces this."
                )
            admissible[offending, c] = False

    return admissible, faults


def _check_warm_starts(
    x0: NDArray[np.float64],
    x0_valid: NDArray[np.bool_],
    candidates: list[ProcessSpec],
) -> None:
    """Refuse a warm start that a store could not have produced legitimately.

    **A warm start arriving from a store is data, not a return value.** The rule
    itself is `warm_start_faults`; this is the half that turns it into a
    refusal, and it is separate because the audit needs the other half.

    Args:
        x0: Warm starts in unconstrained coordinates, shape (B, M, p_max).
        x0_valid: Which cells carry a warm start, shape (B, M).
        candidates: The candidate set, in model-axis order.

    Raises:
        ValueError: If any cell marked valid holds a non-finite value, or one
            whose natural-unit image is at or beyond a diagnostic limit. The
            message names the series, the candidate index and its `spec_hash`.
    """
    admissible, faults = warm_start_faults(x0, candidates)
    offending = np.asarray(x0_valid, dtype=np.bool_) & ~admissible
    if not bool(np.any(offending)):
        return
    b, c = (int(index) for index in np.argwhere(offending)[0])
    raise ValueError(f"x0[{b}, {c}] is marked valid in x0_valid but {faults[(b, c)]}")


def fit(
    y: NDArray[np.float64],
    t: NDArray[np.float64],
    signal: SignalSpec,
    candidates: list[ProcessSpec],
    criterion: Criterion,
    mask: NDArray[np.bool_] | None = None,
    objective: Objective = Objective.ML,
    engine: Engine | None = None,
    x0: NDArray[np.float64] | None = None,
    x0_valid: NDArray[np.bool_] | None = None,
    max_iter: int = DEFAULT_MAX_ITER,
) -> FitResult:
    """Fit a candidate set to a batch of series and rank the candidates.

    Args:
        y: Observations, shape (B, N).
        t: Shared time axis, shape (N,), in decimal years.
        signal: The fixed signal specification; only the noise model is
            selected in v1.
        candidates: Noise specifications to compare.
        criterion: Information criterion for ranking.
        mask: Presence mask, shape (B, N). Defaults to all present.
        objective: ML (default) or REML.
        engine: Likelihood engine. Defaults to the batched Kalman filter.
        x0: Optional warm starts in UNCONSTRAINED coordinates, shape
            (B, M, p_max) -- the same layout `theta_unconstrained` comes back
            in, so a converged neighbour's solution feeds straight back. Rows
            are read to `:p` per candidate, so the NaN padding a narrower
            candidate carries is never inspected. **Requires `x0_valid`.**
        x0_valid: Which cells `x0` actually carries a warm start for, shape
            (B, M), dtype bool. A false cell receives NO warm start and takes
            the moment ladder, recorded as such in `init_rung` -- and is
            bit-identical to the same cell fit with `x0=None`, which is what
            makes the ladder a fallback rather than a third path.

            **Validity is per (series, CANDIDATE), never per series.** The
            warm-start key is `(fit_hash, candidate spec_hash)`, so a coarse
            source point can be `OK` for one candidate and failed for another;
            a per-point array would force all-or-nothing per cell and quietly
            discard usable sources.

            **The dtype gate is deliberate.** Phase 2c's source map exposes
            `index` (int64, -1 where the spiral was exhausted) beside `valid`
            (bool), and `bool(-1)` is True while `bool(0)` is False -- so a
            permissive cast would turn the swap of two adjacent arguments into
            "every exhausted cell valid, every cell sourced from coarse index
            0 invalid", with no exception and the right shapes throughout.
        max_iter: Iteration cap per series. Call-level, so it cannot vary
            within a batch. Defaults to `optimize.DEFAULT_MAX_ITER`, which is
            the one place the production cap is written down -- see there for
            why it is not a config field and why Phase 2b's calibration lowers
            it.

    Returns:
        A `FitResult`.

    Raises:
        ValueError: If `mask` does not match `y`; if exactly one of `x0` and
            `x0_valid` is supplied; if `x0` does not match the (B, M, p_max)
            layout or `x0_valid` the (B, M) one; if `x0_valid` is not boolean;
            or if a cell marked valid holds a value no `OK` fit could produce.
    """
    y = np.asarray(y, dtype=np.float64)
    t = np.asarray(t, dtype=np.float64)
    mask = np.ones_like(y, dtype=bool) if mask is None else np.asarray(mask, dtype=bool)
    if mask.shape != y.shape:
        raise ValueError(f"mask shape {mask.shape} does not match y shape {y.shape}")
    engine = KalmanEngine() if engine is None else engine

    # design_info takes the MASK, and that is not optional: rank, gram_logdet,
    # condition_number and n_rows all describe X restricted to each series'
    # unmasked rows, which is why they are (B,) and not scalars.
    design = signal.design_info(t, mask)
    k_beta = design.n_beta
    batch = int(y.shape[0])
    n_cand = len(candidates)
    p_max = max(len(free_param_index(spec)) for spec in candidates)

    # BOTH OR NEITHER, and *neither* is the existing cold path, which is
    # already correct. Defaulting `x0_valid` to all-valid would hand the caller
    # the NaN-sentinel behaviour back with no diagnostic -- "no valid source"
    # and "a failed source" as the same bytes -- which is the whole reason the
    # sentinel was rejected as a design.
    if (x0 is None) != (x0_valid is None):
        missing = "x0 was not" if x0 is None else "x0_valid was not"
        raise ValueError(
            f"x0 and x0_valid must be supplied together, but {missing} "
            f"supplied. There is no default-to-all-valid: a warm start with "
            f"no validity array cannot express section 11.3's per-cell "
            f"fallback, and omitting both is the cold path."
        )

    if x0 is not None and x0_valid is not None:
        x0 = np.asarray(x0, dtype=np.float64)
        if x0.shape != (batch, n_cand, p_max):
            raise ValueError(
                f"x0 must have shape ({batch}, {n_cand}, {p_max}) to match the "
                f"batch, the candidate set and the widest free parameter "
                f"vector, got shape {x0.shape}"
            )
        x0_valid = np.asarray(x0_valid)
        if x0_valid.dtype != np.bool_:
            raise ValueError(
                f"x0_valid must be a boolean array, got dtype "
                f"{x0_valid.dtype}. It is not cast: an int64 source-index "
                f"array passed here would read -1 (spiral exhausted) as valid "
                f"and 0 (the first coarse point) as invalid."
            )
        if x0_valid.shape != (batch, n_cand):
            raise ValueError(
                f"x0_valid must have shape ({batch}, {n_cand}) to match the "
                f"batch and the candidate set, got shape {x0_valid.shape}. The "
                f"M-axis-to-candidate correspondence is load-bearing in both "
                f"arrays and fit truncates positionally"
            )
        # Every value is checked before any fit starts, so a bad source map is
        # a refusal rather than a partly-written run.
        _check_warm_starts(x0, x0_valid, candidates)

    theta = np.full((batch, n_cand, p_max), np.nan)
    theta_u = np.full((batch, n_cand, p_max), np.nan)
    theta_err = np.full((batch, n_cand, p_max), np.nan)
    beta = np.full((batch, n_cand, k_beta), np.nan)
    beta_err = np.full((batch, n_cand, k_beta), np.nan)
    loglik = np.full((batch, n_cand), np.nan)
    outcome = np.full((batch, n_cand), Outcome.NOT_ATTEMPTED.code, dtype=np.uint8)
    rung = np.empty((batch, n_cand), dtype=object)
    n_iter = np.zeros((batch, n_cand), dtype=np.int64)
    k = np.full((batch, n_cand), np.nan)
    n = np.full((batch, n_cand), np.nan)
    eff_bic = np.full((batch, n_cand), np.nan)
    eff_trend = np.full((batch, n_cand), np.nan)
    modes: list[GradientMode] = []

    trend = design.trend_column
    white_beta_var = design.unit_variance_beta_var

    for c, spec in enumerate(candidates):
        state_space = StateSpace.from_spec(spec)
        obj = ConcentratedObjective(spec, state_space, engine, objective)
        modes.append(resolve_gradient_mode(spec, objective))
        p = len(free_param_index(spec))
        var_gls = np.full(batch, np.nan)
        var_white = np.full(batch, np.nan)

        for b in range(batch):
            # The per-cell selector. `fit` only HONOURS validity -- the policy
            # that decides it (the spiral, its bound and its exhaustion rule)
            # lives in the batch layer, where the coarse grid exists.
            warm = (
                x0[b : b + 1, c, :p]
                if x0 is not None and x0_valid is not None and bool(x0_valid[b, c])
                else None
            )
            # The design is narrowed to this series: its rank, gram_logdet
            # and n_rows are all (B,) and describe X restricted to each
            # series' own rows, so handing the full-batch object to a
            # one-series fit pairs this series' data with the whole batch's
            # diagnostics.
            one = design.series(b)
            result = optimize_series(
                obj, y[b : b + 1], mask[b : b + 1], t, one, warm, max_iter
            )
            outcome[b, c] = result.outcome.code
            rung[b, c] = result.init_rung
            n_iter[b, c] = result.n_iter
            if result.outcome is not Outcome.OK:
                continue

            loglik[b, c] = result.loglik
            theta[b, c, :p] = result.theta[0]
            if result.hessian is None:
                continue
            u_hat = obj.to_unconstrained(result.theta)[0]
            theta_u[b, c, :p] = u_hat
            # Explicit dtype: numpy 2.4's stubs give `inv` a `floating[Any]`
            # dtype where 2.5's give `float64`, and numba pins numpy<2.5.
            cov_u = np.asarray(np.linalg.inv(result.hessian), dtype=np.float64)
            cov_nat = delta_method_cov(obj.dforward(u_hat[None, :])[0], cov_u)
            theta_err[b, c, :p] = np.sqrt(np.clip(np.diag(cov_nat), 0.0, np.inf))
            # One evaluation at the optimum yields beta and beta_cov. An
            # earlier draft ran a second full filter pass purely to recover
            # quantities the objective had already computed and discarded.
            final = obj.evaluate(result.theta, y[b : b + 1], mask[b : b + 1], t, one)
            if (
                k_beta
                and final.gls is not None
                and final.gls.outcome[0] == Outcome.OK.code
            ):
                beta[b, c] = final.gls.beta[0]
                beta_err[b, c] = np.sqrt(
                    np.clip(np.diag(final.gls.beta_cov[0]), 0.0, np.inf)
                )
                if trend is not None:
                    var_gls[b] = float(final.gls.beta_cov[0][trend, trend])

        # Per candidate, over the whole batch: counting.py already returns
        # per-series arrays, and unpacking them one series at a time is
        # precisely where the design_rank / rank_x substitution and the
        # n_obs - (-1) off-by-one get reintroduced by hand.
        k[:, c], n[:, c] = penalty_terms(
            spec,
            objective,
            n_obs=design.n_rows,
            design_rank=design.rank,
            outcome=outcome[:, c],
            k_beta=k_beta,
        )
        full_theta = obj.hydrate(np.nan_to_num(theta[:, c, :p], nan=1.0))
        eff_bic[:, c] = n_eff_bic(
            state_space, full_theta, t, mask=mask, outcome=outcome[:, c]
        )
        if trend is not None:
            marginal = state_space.acvf(full_theta, np.zeros(1))[:, 0]
            var_white = marginal * white_beta_var[:, trend]
            scored = (outcome[:, c] == Outcome.OK.code) & np.isfinite(var_gls)
            eff_trend[:, c] = n_eff_trend(
                np.where(scored, var_gls, 1.0),
                np.where(scored, var_white, 1.0),
                design.n_rows,
                outcome=np.where(
                    scored, outcome[:, c], Outcome.NOT_ATTEMPTED.code
                ).astype(np.uint8),
            )

    # ONE `CandidateScores`, RANKED HERE AND RETURNED. It used to be a local,
    # which meant `k` and `n` were computed, used and discarded -- so the store's
    # `/primitives/k` and `/primitives/n` had no producer, and a writer would
    # have had to call `penalty_terms` a second time, from a different call site,
    # with nothing keeping the two derivations in step. It is also what lets a
    # caller rank the SAME fits under several criteria without refitting, which
    # is the whole of design doc 12.8's recompute claim.
    scores = CandidateScores(
        labels=tuple(spec.spec_hash()[:12] for spec in candidates),
        engines=(engine.engine_id,) * n_cand,
        objectives=(objective,) * n_cand,
        loglik=loglik,
        k=k,
        n=n,
        n_eff=eff_bic,
        outcome=outcome,
    )
    ranking = rank_candidates(scores, criterion)

    return FitResult(
        candidates=tuple(candidates),
        theta=theta,
        theta_err=theta_err,
        theta_unconstrained=theta_u,
        beta=beta,
        beta_err=beta_err,
        loglik=loglik,
        outcome=outcome,
        init_rung=rung,
        n_iter=n_iter,
        n_eff_bic=eff_bic,
        n_eff_trend=eff_trend,
        scores=scores,
        ranking=ranking,
        engine=engine.engine_id,
        objective=objective,
        gradient_mode=tuple(modes),
    )


__all__ = ["FitResult", "InitRung", "fit", "warm_start_faults"]
