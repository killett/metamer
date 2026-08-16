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
            shape. This is what Phase 2 feeds back as `x0`.
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
            in, so a converged neighbour's solution feeds straight back. Phase
            2 supplies these; the signature is fixed now because it constrains
            everything downstream.
        max_iter: Iteration cap per series. Call-level, so it cannot vary
            within a batch. Defaults to `optimize.DEFAULT_MAX_ITER`, which is
            the one place the production cap is written down -- see there for
            why it is not a config field and why Phase 2b's calibration lowers
            it.

    Returns:
        A `FitResult`.

    Raises:
        ValueError: If `mask` does not match `y`, or `x0` does not match the
            (B, M, p_max) layout.
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

    if x0 is not None:
        x0 = np.asarray(x0, dtype=np.float64)
        if x0.shape != (batch, n_cand, p_max):
            raise ValueError(
                f"x0 must have shape ({batch}, {n_cand}, {p_max}) to match the "
                f"batch, the candidate set and the widest free parameter "
                f"vector, got shape {x0.shape}"
            )

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
            warm = None if x0 is None else x0[b : b + 1, c, :p]
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


__all__ = ["FitResult", "InitRung", "fit"]
