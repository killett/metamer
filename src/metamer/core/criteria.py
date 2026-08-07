"""Information criteria and the comparability guards.

WHY THE GUARDS ARE ERRORS AND NOT WARNINGS.
-------------------------------------------
Every score carries the engine that produced it AND the objective it is on, and
ranking across either is refused. The reason is that a Whittle score and a
Kalman score are *commensurable-looking and not commensurable*: both are
negative, both are log-likelihood-shaped, both improve as the fit improves, and
differencing them yields a number that ranks candidates plausibly and wrongly.
The same holds for ML against REML, which are likelihoods of different random
quantities entirely -- `y` in one case, a maximal set of error contrasts `A'y`
in the other. At 10^7 series nobody inspects an individual fit, so a
plausible-and-wrong delta-IC is not a wrong number, it is a wrong MAP. A
warning would be emitted once into a log that nobody reads while the map got
written anyway. Design doc section 6.2.

EVERYTHING IS `(B, M)`, BECAUSE EVERYTHING UPSTREAM ALREADY IS.
---------------------------------------------------------------
`B` is the batch of series, `M` the candidate axis. `counting.penalty_terms`
returns `(k, n)` per series; `counting.n_eff_bic` returns per series;
`ObjectiveResult.loglik` and `ObjectiveResult.outcome` are per series. A
criteria layer taking Python floats would force the caller to unpack all of
that one series at a time -- which is both a per-point Python loop over 10^7
grid points and, worse, the place where the `rank_x` / `design_rank`
substitution and the `n_obs - (-1)` off-by-one get reintroduced by hand. B = 1
is a shape here, never a separate code path.

The output shapes are the ones design doc section 12.2 declares for
`/selection/`: `delta_ic[y,x,m,c]`, `weight[y,x,m,c]`, `ic_best[y,x,c]`,
`selected[y,x,c]`, `n_valid[y,x]`. One `Ranking` is one criterion's slice.

SURVIVAL IS GATED ON `outcome == OK`, NOT ON A BOOLEAN AND NOT ON FINITENESS.
-----------------------------------------------------------------------------
`outcome` is the `(B, M)` uint8 array the pipeline already carries, so the
selection layer and the store cannot drift apart. Two rules follow, and both
matter:

  * Gating on `isfinite(loglik)` would resurrect a candidate that hit the
    iteration cap or a diagnostic limit -- those carry the last finite value
    they evaluated -- and it can then win.
  * Gating on `Outcome.is_failure` would ADMIT `INSUFFICIENT_DATA` and
    `NOT_ATTEMPTED`, which are False under that property by design (they are
    excluded from the failure-rate numerator, not from the outcome ladder). A
    wholly-masked tile would then come back with a confident-looking selection.

Exactly `OK` is admitted, which matches the store's bidirectional status
invariant: non-OK implies NaN in every value slot. Where that invariant is
violated on the way in -- `OK` beside a NaN primitive -- this module RAISES
rather than quietly dropping the cell, because a dropped cell reads downstream
as "that candidate failed here" when what actually happened is that a writer
disagreed with itself.

`n_valid` COUNTS FITS, NOT FINITE CRITERION VALUES.
---------------------------------------------------
The store holds one `n_valid[y,x]` shared by every criterion (section 12.2 --
it has no `c` axis), so it cannot be allowed to depend on which criterion was
asked for. It is therefore `count(outcome == OK)`. A candidate whose AICc is
`+inf` because `n <= k + 1` still fitted; it is ranked last with weight zero
and delta-IC `+inf`, and it still counts toward `n_valid`. Defining validity as
`isfinite(ic)` instead would make the same fits report different `n_valid`
under AIC and under AICc.

THE LOG-BASED PENALTIES HAVE DOMAINS, AND OUTSIDE THEM THE ANSWER IS NaN.
-------------------------------------------------------------------------
A criterion whose penalty is zero or negative is not a criterion -- it selects
the most complex candidate whatever the data say. Measured:

    n = 1    BIC penalty   4 ln 1        =  0.0    (no penalty at all)
    n = 1    HQIC penalty  8 ln ln 1     = -inf    (wins with weight 1)
    n = 2    HQIC penalty  8 ln ln 2     = -2.93   (rewards parameters)

These are reachable: `penalty_terms` guarantees only that REML's
`n_obs - design_rank` is at least 1. So `BIC` is defined for `n > 1`, `HQIC`
for `n > e`, `BIC_NEFF` for `n_eff > 1`, and outside those the value is NaN --
which flows into exactly the same "not rankable" path as a failed fit, rather
than into a winner. Clamping the argument instead (a floor at 2.0, say) is
worse than either: it silently answers a different question, and at `n = 2`,
`n_eff = 1.5` it makes `bic_neff` exactly EQUAL to `bic`, contradicting the
requirement that it be strictly smaller whenever `n_eff < n`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

import numpy as np
from numpy.typing import ArrayLike, NDArray

from metamer.core.capability import EngineId, Objective
from metamer.core.outcomes import Outcome


class Criterion(StrEnum):
    """Selectable information criteria.

    `BIC_NEFF` is BIC with the effective sample size `n_eff_bic` in place of
    `n`; the standard `n` penalty assumes independent observations, which is
    the assumption this whole package exists to abandon.
    """

    AIC = "aic"
    AICC = "aicc"
    BIC = "bic"
    BIC_NEFF = "bic_neff"
    HQIC = "hqic"


class ComparabilityError(ValueError):
    """Scores from different engines or objectives cannot be ranked."""


@dataclass(frozen=True)
class CandidateScores:
    """Per-series, per-candidate primitives for one tile, with provenance.

    Attributes:
        labels: Candidate labels, length M. Used to name the offending
            candidate when a comparability guard fires.
        engines: The engine that produced each candidate's log-likelihood,
            length M. Per candidate rather than per run because engine
            capability is resolved per composite spec (design doc section 4.2),
            so a candidate set genuinely can mix engines -- which is the
            situation the guard exists for.
        objectives: The objective each candidate was fitted under, length M.
        loglik: Maximized log-likelihood, shape (B, M). NaN wherever `outcome`
            is not OK.
        k: Parameter count per objective, shape (B, M) float64, from
            `counting.penalty_terms`. Varies per series because it counts
            `design_rank`, which the mask changes.
        n: Sample size per objective, shape (B, M) float64, from the same call.
        n_eff: Effective sample size for the BIC variant, shape (B, M), from
            `counting.n_eff_bic`. Read only by `Criterion.BIC_NEFF`, and
            validated only when that criterion is the one asked for -- it costs
            an O(n_used^2) sum to produce and no other criterion reads it.
        outcome: Per-series, per-candidate outcome codes, shape (B, M) uint8.
    """

    labels: tuple[str, ...]
    engines: tuple[EngineId, ...]
    objectives: tuple[Objective, ...]
    loglik: NDArray[np.float64]
    k: NDArray[np.float64]
    n: NDArray[np.float64]
    n_eff: NDArray[np.float64]
    outcome: NDArray[np.uint8]

    def __post_init__(self) -> None:
        """Check that every array and tag tuple describes the same (B, M) block.

        Raises:
            ValueError: If `loglik` is not two-dimensional; if the candidate
                axis is empty; if any other per-cell array has a different
                shape; or if any tag tuple has a length other than M.
        """
        shape = np.shape(self.loglik)
        if len(shape) != 2:
            raise ValueError(f"loglik must have shape (B, M), got shape {shape}")
        batch, n_cand = shape
        if n_cand == 0:
            raise ValueError(
                "a candidate set must hold at least one candidate; an empty "
                "model axis is a configuration error and is indistinguishable "
                "in the store from a point where every fit failed"
            )
        for name, array in (
            ("k", self.k),
            ("n", self.n),
            ("n_eff", self.n_eff),
            ("outcome", self.outcome),
        ):
            if np.shape(array) != shape:
                raise ValueError(
                    f"{name} must have shape ({batch}, {n_cand}) to match "
                    f"loglik, got shape {np.shape(array)}"
                )
        for name, tags in (
            ("labels", self.labels),
            ("engines", self.engines),
            ("objectives", self.objectives),
        ):
            if len(tags) != n_cand:
                raise ValueError(
                    f"{name} must have one entry per candidate, i.e. "
                    f"{n_cand} for this score block, got {len(tags)}"
                )


@dataclass(frozen=True)
class Ranking:
    """One criterion's ranking of a candidate set over a batch of series.

    Attributes:
        criterion: The criterion these numbers were produced with. Carried so a
            `Ranking` cannot be filed under the wrong slot of the store's
            criterion axis.
        delta_ic: `IC - IC_best` per series, shape (B, M). Zero for the winner,
            NaN for a candidate that did not fit and for every candidate at a
            point with no winner, and `+inf` for a candidate that fitted but
            whose criterion value is infinite.
        weights: `exp(-delta_ic / 2)` normalized over the rankable candidates
            of each series, shape (B, M). Exactly zero for every excluded
            candidate, and all-zero for a series with no winner.
        ic_best: The winning criterion value per series, shape (B,), NaN where
            there is no winner. Stored in float64 because raw IC values are
            ~10^3 with meaningful differences ~1 (design doc section 12.6);
            `delta_ic` is what survives float32.
        best_index: Index of the winning candidate per series, shape (B,) int64,
            **-1 where no candidate could be ranked**.
        n_valid: Number of candidates that fitted, per series, shape (B,) int64.
            Criterion-independent by construction -- see the module docstring.
    """

    criterion: Criterion
    delta_ic: NDArray[np.float64]
    weights: NDArray[np.float64]
    ic_best: NDArray[np.float64]
    best_index: NDArray[np.int64]
    n_valid: NDArray[np.int64]


def ic_value(
    criterion: Criterion | str,
    loglik: ArrayLike,
    k: ArrayLike,
    n: ArrayLike,
    n_eff: ArrayLike,
) -> NDArray[np.float64]:
    """Evaluate an information criterion from the stored primitives.

    Elementwise and broadcasting, so it evaluates a whole `(B, M)` block in one
    call. Lower is better in every case.

        AIC      = 2k - 2l
        AICc     = AIC + 2k(k+1) / (n - k - 1)
        BIC      = k ln n - 2l
        BIC_NEFF = k ln n_eff - 2l
        HQIC     = 2k ln ln n - 2l

    Args:
        criterion: Which criterion to evaluate. A plain string is accepted
            because criteria arrive from the config file (design doc section
            13.1) as strings.
        loglik: Maximized log-likelihood.
        k: Parameter count, per objective. See `counting.penalty_terms`; ML and
            REML count different things, and the difference is a definition on
            two model classes rather than an adjustment.
        n: Sample size, per objective. Read by every criterion except AIC.
        n_eff: Effective sample size. Read by `BIC_NEFF` only.

    Returns:
        The criterion value as float64, broadcast over the inputs. NaN wherever
        a primitive is missing or the criterion's penalty is outside its
        domain; `+inf` for AICc where `n - k - 1 <= 0`, which is the standard
        divergence and keeps an over-parameterized candidate from scoring
        *better* than AIC via a negative correction.

    Raises:
        ValueError: If `criterion` names no implemented criterion.
    """
    ell = np.asarray(loglik, dtype=np.float64)
    params = np.asarray(k, dtype=np.float64)
    size = np.asarray(n, dtype=np.float64)
    effective = np.asarray(n_eff, dtype=np.float64)
    fit = -2.0 * ell

    penalty: NDArray[np.float64]
    match criterion:
        case Criterion.AIC:
            penalty = 2.0 * params
        case Criterion.AICC:
            penalty = 2.0 * params + _aicc_correction(params, size)
        case Criterion.BIC:
            penalty = params * _log_above(size, 1.0)
        case Criterion.BIC_NEFF:
            penalty = params * _log_above(effective, 1.0)
        case Criterion.HQIC:
            # ln ln n is positive only for n > e; below that the "penalty"
            # rewards parameters, and at n = 1 it is -inf.
            penalty = 2.0 * params * np.log(_log_above(size, math.e))
        case _:
            raise ValueError(
                f"unknown criterion {criterion!r}; implemented criteria are "
                f"{[c.value for c in Criterion]}"
            )
    return np.asarray(penalty + fit, dtype=np.float64)


def rank_candidates(scores: CandidateScores, criterion: Criterion) -> Ranking:
    """Rank a candidate set per series, refusing incomparable scores.

    Args:
        scores: One `(B, M)` block of primitives with its per-candidate engine
            and objective tags.
        criterion: Criterion to rank by.

    Returns:
        A `Ranking` whose arrays match the `/selection/` layout of design doc
        section 12.2.

    Raises:
        ComparabilityError: If the candidate set mixes engines or objectives.
            Checked on the whole set before anything is scored, so the refusal
            does not depend on where a fit happened to fail -- otherwise the
            same misconfigured run would raise on one tile and write a wrong
            map on the next.
        ValueError: If a candidate whose outcome is OK carries a non-finite
            `loglik`, `k` or `n` -- the store's status invariant is
            bidirectional, so that combination is a defect in whatever wrote
            it -- or, for `BIC_NEFF` only, a non-finite `n_eff`.
    """
    _refuse_mixed_tags(scores.engines, scores.labels, "engine")
    _refuse_mixed_tags(scores.objectives, scores.labels, "objective")

    ell = np.asarray(scores.loglik, dtype=np.float64)
    params = np.asarray(scores.k, dtype=np.float64)
    size = np.asarray(scores.n, dtype=np.float64)
    effective = np.asarray(scores.n_eff, dtype=np.float64)
    scored = np.asarray(
        np.asarray(scores.outcome).astype(np.int64) == Outcome.OK.code, dtype=np.bool_
    )

    usable = np.isfinite(ell) & np.isfinite(params) & np.isfinite(size)
    if bool(np.any(scored & ~usable)):
        rows, cols = np.nonzero(scored & ~usable)
        raise ValueError(
            "a candidate whose outcome is OK must carry a finite loglik, k and "
            "n: the store's status invariant is bidirectional, so a non-OK "
            "status implies NaN in every value slot and an OK status implies "
            f"none. Offending (series, candidate) pairs: "
            f"{list(zip(rows.tolist(), cols.tolist(), strict=True))}"
        )
    if criterion is Criterion.BIC_NEFF and bool(
        np.any(scored & ~np.isfinite(effective))
    ):
        rows, cols = np.nonzero(scored & ~np.isfinite(effective))
        raise ValueError(
            "Criterion.BIC_NEFF needs a finite n_eff for every scored "
            "candidate; compute it once at the optimum with "
            "counting.n_eff_bic. Offending (series, candidate) pairs: "
            f"{list(zip(rows.tolist(), cols.tolist(), strict=True))}"
        )

    values = np.where(scored, ic_value(criterion, ell, params, size, effective), np.nan)
    # Rankable is narrower than scored: a fit can succeed and still have no
    # finite criterion value (AICc at n <= k + 1). Such a candidate is ranked
    # last, not reclassified as a failure -- see the module docstring on
    # n_valid.
    rankable = scored & np.isfinite(values)
    has_winner = np.any(rankable, axis=1)

    ordered = np.where(rankable, values, np.inf)
    argmin = np.argmin(ordered, axis=1)
    rows = np.arange(ordered.shape[0])
    best_index = np.where(has_winner, argmin, -1).astype(np.int64)
    ic_best = np.where(has_winner, ordered[rows, argmin], np.nan)

    delta_ic = values - ic_best[:, None]
    # The inner `where` keeps NaN and +inf out of the exponential, so the
    # weights are computed from finite exponents only and no candidate can
    # contribute a NaN to the normalization.
    weights = np.where(rankable, np.exp(-0.5 * np.where(rankable, delta_ic, 0.0)), 0.0)
    totals = np.sum(weights, axis=1)[:, None]
    weights = np.where(totals > 0.0, weights / np.where(totals > 0.0, totals, 1.0), 0.0)

    return Ranking(
        criterion=criterion,
        delta_ic=np.asarray(delta_ic, dtype=np.float64),
        weights=np.asarray(weights, dtype=np.float64),
        ic_best=np.asarray(ic_best, dtype=np.float64),
        best_index=best_index,
        n_valid=np.count_nonzero(scored, axis=1).astype(np.int64),
    )


def _refuse_mixed_tags(
    tags: tuple[EngineId, ...] | tuple[Objective, ...],
    labels: tuple[str, ...],
    kind: str,
) -> None:
    """Raise if a candidate set carries more than one distinct provenance tag.

    Args:
        tags: One tag per candidate.
        labels: Candidate labels, same length, for the error message.
        kind: The word "engine" or "objective", quoted in the message.

    Raises:
        ComparabilityError: If the tags are not all equal.
    """
    distinct = {tag.value for tag in tags}
    if len(distinct) <= 1:
        return
    detail = ", ".join(
        f"{label}={tag.value}" for label, tag in zip(labels, tags, strict=True)
    )
    raise ComparabilityError(
        f"refusing to rank across {kind} tags {sorted(distinct)}: these scores "
        "are not on a common scale, and differencing them produces a "
        f"plausible-looking wrong ranking rather than a visible failure ({detail})"
    )


def _log_above(value: NDArray[np.float64], floor: float) -> NDArray[np.float64]:
    """Return `log(value)` where `value > floor`, and NaN elsewhere.

    The comparison is done before the logarithm so that a degenerate sample
    size never reaches `np.log` -- `log(0)` is `-inf` with a runtime warning,
    and `-inf` in a penalty is a candidate that wins with weight 1.

    Args:
        value: Argument of the logarithm.
        floor: Strict lower bound of the criterion's domain.

    Returns:
        The logarithm, NaN outside the domain and wherever `value` is NaN.
    """
    admissible = np.where(value > floor, value, np.nan)
    return np.asarray(np.log(admissible), dtype=np.float64)


def _aicc_correction(
    k: NDArray[np.float64], n: NDArray[np.float64]
) -> NDArray[np.float64]:
    """Return AICc's small-sample correction `2k(k+1) / (n - k - 1)`.

    Args:
        k: Parameter count.
        n: Sample size.

    Returns:
        The correction; `+inf` where `n - k - 1 <= 0`, because a negative
        denominator would make the correction negative and score an
        over-parameterized candidate BELOW plain AIC -- the opposite of what
        AICc is for. NaN is preserved as NaN rather than collapsing to `+inf`,
        so a missing primitive stays missing instead of reading as a real,
        infinitely bad score.
    """
    denominator = n - k - 1.0
    positive = denominator > 0.0
    correction = 2.0 * k * (k + 1.0) / np.where(positive, denominator, np.nan)
    diverges = ~positive & ~np.isnan(denominator)
    return np.asarray(np.where(diverges, np.inf, correction), dtype=np.float64)
