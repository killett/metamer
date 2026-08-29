"""Reference per-series optimizer, initialization ladder, and Hessian.

SCALAR HERE IS DELIBERATE. THIS IS THE ONE PLACE IN `core` WHERE IT IS.
-----------------------------------------------------------------------
`SeriesFit` carries a scalar `Outcome`, a `float` log-likelihood and a `(1, N)`
view of one series, and none of that is a batch-granularity defect. This module
IS path A's permanent reference form: design doc §17 makes a plain scipy loop
over series path A's final shape if the stage-1 spike goes path B's way, and a
correctness reference does not need to be fast. The conversion to the `(B, M)`
uint8 codes the store and `counting`/`criteria` speak happens exactly once, in
`fit`. A later "every per-series concept must be per series" sweep will find
this module and should leave it alone — the note is here so that sweep has an
answer rather than an intuition.

THE HESSIAN IS AN OUTPUT, NOT A DIAGNOSTIC, AND IT IS COMPUTED EXPLICITLY.
--------------------------------------------------------------------------
It feeds reported parameter uncertainties, TIC, the sandwich estimator, and the
near-degeneracy condition number of design doc §4.8. **Never substitute
L-BFGS-B's `hess_inv`.** A converged quasi-Newton matrix is the right shape and
roughly the right magnitude, so nothing downstream would notice it is too
crude — which is precisely why it must not be used. The explicit cost is `2p²`
objective evaluations, about +12% on a 50-iteration fit at p = 6, paid once.

A SECOND DIFFERENCE WANTS `eps^(1/4)`, NOT `eps^(1/3)`.
-------------------------------------------------------
`fd_step` is for a FIRST difference, whose cancellation error is `eps|f|/h`.
A second central difference divides by `h²`, so its cancellation error is
`4 eps |f| / h²` and its optimum is `(eps |f| / |f''''|)^(1/4)`. Measured on
the real `matern12` filter at N = 200, relative error against a nested
Richardson oracle:

    h = 1.00e-05   4.39e-05     <- max(fd_step(scale), 1e-5), the plan's rule
    h = 6.06e-06   2.86e-05     <- eps^(1/3)
    h = 1.22e-04   2.98e-07     <- eps^(1/4), this module's rule

A factor of 147, and a sweep over ten decades puts the empirical optimum at
1e-04, which `eps^(1/4)` sits on. Reusing `fd_step` here is the single easiest
mistake in this file.

REPORTED UNCERTAINTY IS FIRST-ORDER, AND THAT IS NOT A FOOTNOTE.
----------------------------------------------------------------
The Hessian is in unconstrained coordinates; `transforms.delta_method_cov`
pushes it to natural units as `J Σ_u Jᵀ`. That is exact only to first order.
Under a `Log` transform the natural parameter is lognormal, so the true
variance exceeds the delta-method value by `(e^s − 1)e^s / s` with
`s = σ_u²`: **1.015 at σ_u = 0.1, 1.459 at 0.5, 4.671 at 1.0** — 1.5%, 46% and
367% understatement. Large `σ_u` is exactly the regime near a diagnostic limit,
so the caveat travels with the number that gets published.

THE OUTCOME PRECEDENCE, AND WHY IT IS IN THIS ORDER.
----------------------------------------------------
Each check is a different scientific fact and the order decides which one gets
reported when two apply:

  1. **Design precheck** — its own verdict, unrelabelled. A `RANK_DEFICIENT_X`
     series reported as `NONFINITE_OBJECTIVE` moves "this design is not
     identified here" into "the numerics failed": different map entry,
     different follow-up.
  2. **Non-finite objective** — nothing below can be interpreted.
  3. **Diagnostic limit** — outranks non-convergence, because "the fit ran away
     to the boundary" explains the non-convergence rather than competing with
     it.
  4. **Line-search collapse** (scipy `status == 2`) — the optimizer could not
     find a decreasing step, distinct from simply running out of iterations.
  5. **Iteration cap**, split on the gradient norm.
  6. **Degenerate Hessian** — checked LAST among the numerical outcomes,
     because curvature at a point that is not an optimum means nothing. This is
     the reverse of the plan's fence, which checked it before the cap and would
     report `DEGENERATE_HESSIAN` for a fit that had simply not converged.

Consequently the Hessian is computed only once every prior check has passed:
non-OK fits return `hessian=None`, which also saves `2p²` evaluations on
exactly the fits that were slow enough to hit the cap. `DEGENERATE_HESSIAN` is
the one non-OK outcome that keeps its matrix, because there the matrix is the
finding.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import minimize

from metamer.core.gradients import EPS, fd_gradient
from metamer.core.objective import ConcentratedObjective, merge_outcomes
from metamer.core.outcomes import Outcome, outcome_array
from metamer.core.signal import DesignInfo
from metamer.core.terms import ProcessSpec, free_param_index

GRAD_TOL: float = 5e-5
"""Relative gradient-norm tolerance, judged in unconstrained coordinates.

The comparison is `||g|| < GRAD_TOL * max(|loglik|, 1)`, because `|loglik|`
scales with N and an absolute gradient tolerance would tighten with record
length for no reason.

THIS IS A MEASURED SEPARATOR, NOT AN eps-DERIVED CONSTANT, and it is labelled
as such deliberately. It cannot be derived from float64 the way
`HESSIAN_COND_LIMIT` and `objective.CONDITION_LOG_LIMIT` are, because the floor
it has to clear is not set by the arithmetic: it is set by **scipy's L-BFGS-B
stopping rule**, which halts several decades above what the finite-difference
gradient could resolve. Measured at the optimum against a nested-Richardson
gradient, the instrument's own floor is `~3e-10` relative to `|loglik|`
(`max|fd - richardson| / |loglik|` = 2.79e-10 and 3.42e-10 on two cases), and
no converged fit comes anywhere near it.

What this constant separates is a fit that hit the iteration cap essentially
done from one that hit it nowhere near, so it is bounded from BOTH sides by
measurement. Measured 2026-08-10 over six fits, two compositions
(`matern12`, `white + matern12`) and three record lengths (N = 200, 400, 630),
`||g|| / max(|loglik|, 1)`:

    converged (max_iter = 200, outcome OK)      3.46e-07 .. 2.30e-05
    genuinely unconverged (max_iter = 1, 2, 3)  1.45e-04 .. 1.84e-02

The two populations are separated by a factor of 6.3 and nothing lands
between them. `5e-5` sits 2.2x above the converged maximum and 2.9x below the
unconverged minimum, i.e. near the middle in log space.

**RE-MEASURED 2026-08-19 ON A SECOND NUMERIC STACK, AND THE SEPARATION IS NOT
6.3x.** The figures above were measured in one environment. Running the same
compositions and record lengths under PyPI wheels (numpy 2.5.2) rather than
conda-forge (numpy 2.4.6) moves the converged population's top, and widening
the stopped ladder to every `max_iter` in 1..3 at every length -- which the
line above says it covers -- finds stopped fits well below the `1.45e-04` it
records:

    conda-forge, numpy 2.4.6   converged max 2.2957e-05   stopped min 7.5363e-05
    PyPI wheels, numpy 2.5.2   converged max 2.9475e-05   stopped min 2.8898e-04

Union of the two: `2.9475e-05 .. 7.5363e-05`, a gap of **2.56x**, inside which
`5e-5` sits 1.70x above and 1.51x below. **No threshold can hold a 2x margin on
both sides of a 2.56x gap** -- the best any value achieves is 1.60x -- so the
"2-3x margin" this docstring claims was a property of one stack and one ladder,
not of the constant.

`GRAD_TOL` IS LEFT AT `5e-5` DELIBERATELY. It still separates the populations
in both environments, which is what it is for, and the log-midpoint of the
union (4.71e-05) is not a better-evidenced value: the 2026-08-10 ladder cannot
be reproduced from what is recorded here -- no seeds, no `sigma`/`rho`, and a
stopped minimum that a straightforward reading of "max_iter = 1, 2, 3" does not
reproduce -- so a retune would replace a measured constant with a differently
measured one and lose the comparison. See PROGRESS.md's open question.

CONSEQUENCE, AND WHY THE PREVIOUS `1e-5` WAS WRONG: it sat *below* the
converged population's maximum, so two of the six converged fits above
(2.30e-05 and 1.14e-05) would have been reported `ITER_CAP_LARGE_GRAD` had
they hit the cap -- a fit that was done, filed as nowhere near. That is the
"guard below the diagnostic limit of what it guards" failure, the mirror of
the clamp rule: it does not fabricate a number, it makes
`ITER_CAP_SMALL_GRAD` under-reachable and mislabels the fits that do reach it.

The stakes are lower than for `HESSIAN_COND_LIMIT`: both outcomes are
`is_failure`, so this splits one flagged category into two rather than calling
a bad fit good. That is why a margin of this size is accepted here -- 1.5x
across two stacks, having been believed to be 2-3x -- and would not be
accepted there. `test_the_iteration_cap_splits_on_the_gradient_norm_at_a
_measured_separation` pins both bounds, so the margin cannot silently erode.
"""

HESSIAN_COND_LIMIT: float = float(EPS) ** -0.5
"""Above this cond(H) the fit is reported as near-degenerate. 2**26 = 6.711e7.

DERIVED FROM float64, NOT PICKED. It was `1e10` until 2026-08-10, which was
picked, and the gap mattered: `lint.py`'s static half of design doc section 4.8
is derived from `eps` while this, its a-posteriori half, was ~150x more
permissive, so a composition the lint flags could come back `OK`. Two halves of
one diagnostic sitting on different footings is exactly the band in which a
near-degenerate fit reports as healthy.

UNITS: the 2-norm condition number of the Hessian of the negative
log-likelihood in unconstrained coordinates, as `np.linalg.cond` returns it --
not its log, and not the Gram of anything.

THE DERIVATION. COUNT THE INVERSIONS: the Hessian is inverted exactly once, to
produce the parameter covariance `H^-1` from which `theta_err` follows. The
forward error of that inversion goes like `eps * cond(H)`, and roughly half the
significant digits are gone when it reaches `sqrt(eps)`:

    eps * cond(H) = sqrt(eps)   =>   cond(H) = eps^(-1/2) = 2**26 = 6.7109e7

ONE inversion, so the exponent is -1/2. Contrast `objective.CONDITION_LOG_LIMIT`,
whose solve runs on the normal equations and therefore sees `cond(X_w)^2`,
taking the fourth root instead. Copying that neighbour's exponent here -- or
this one's there -- is the measured default mistake the eps-constant rule exists
to prevent.

CONSEQUENCE, STATED SO IT IS NOT QUIETLY RETUNED: this is 149x tighter than the
old value, so fits whose curvature is resolvable to fewer than half the
available digits now report `DEGENERATE_HESSIAN` where they previously reported
`OK`. That is the intended direction. The worked case is in PROGRESS.md's open
question 9: a white-noise series fitted with white + Matern 1/2 measured
`cond(H) = 3.525e8`, which is degenerate under this limit and was `OK` under
`1e10` -- and the verdict `DEGENERATE_HESSIAN` was arguably right, the fixture
having been calling a near-degenerate series healthy by 28x.
"""

DEFAULT_MAX_ITER: int = 200
"""The production iteration cap, and the ONE place it is written down.

**IT HAS TWO CALLERS AND IS ABOUT TO HAVE A THIRD**, which is why it stopped
being a literal. `optimize_series` and `fit` both carried `max_iter: int = 200`,
and Phase 2b Task 4 adds `run(..., max_iter=...)`: a third copy would drift the
day any one of them moved, and the drift would be silent -- a run capped at a
stale default converges to the same optimum for most series and to a different
one for the hard ones, which is the failure mode section 11.1 calls the worst in
the system.

**IT IS A CALIBRATION KNOB AND NEVER A PRODUCTION ONE.** Convergence is well
inside it -- P3 measured `mean_iterations` at **32.5** at d = 3 -- so lowering it
is how Phase 2b's calibration makes a real tile affordable. **A MEAN IS NOT A
MAXIMUM**, and the difference is what a reader taking 32.5 as "converged by 32"
gets wrong: measured 2026-08-15 at a cap of 32 over 128 fits, **83 came back
`OK` and 45 did not**. At a cap of 1 or 2, **none** do.

**And it is not a config field**, deliberately. A cap in the config would reach
`fit_hash`, so a capped calibration would key on a different fit identity from
the run whose memory it measures -- which is precisely what section 11.4's cache
key must not do.
"""

_RATIO_FLOOR: float = 1.0
"""Smallest admissible `|f| / |f''''|`, so a degenerate scale cannot give h = 0."""

_STATUS_OUTCOMES: dict[int, Outcome] = {
    0: Outcome.OK,
    1: Outcome.ITER_CAP_LARGE_GRAD,
    2: Outcome.TRUST_RADIUS_COLLAPSED,
}
"""scipy L-BFGS-B termination status to outcome.

`2` is ABNORMAL_TERMINATION_IN_LNSRCH: the line search could not find a step
that decreases the objective. That is the line-search analogue of a collapsed
trust region, and mapping it here is the only route by which
`Outcome.TRUST_RADIUS_COLLAPSED` is producible in Phase 1 at all — the batched
trust-region that would produce it directly is Task 19, which may be deleted
rather than built. `1` is the iteration cap and is refined by the gradient norm
before it is reported.
"""


class InitRung(StrEnum):
    """Which rung of the initialization ladder produced the starting point.

    Recorded on every result because the initialization source affects
    reproducibility semantics, and it is what you want when diagnosing
    traversal-order dependence in the Phase 2 warm-start hysteresis audit.
    """

    WARM_START = "warm_start"
    MOMENT = "moment"
    CLIPPED = "clipped"
    DEFAULT = "default"


@dataclass(frozen=True)
class SeriesFit:
    """One series' fit result. Scalar by design — see the module docstring.

    Attributes:
        theta: Natural-units free parameters, shape (1, p). NaN throughout when
            the design precheck refused the series.
        loglik: Maximized log-likelihood. **NaN, never -inf**, when the fit
            failed: the barrier value is legal only inside `negative()`.
        outcome: The taxonomy verdict; see the module docstring for precedence.
        n_iter: Iterations the optimizer reported.
        init_rung: Which rung of the ladder supplied the starting point.
        hessian: The explicit Hessian of the NEGATIVE log-likelihood in
            unconstrained coordinates, or None. Present for `OK` and for
            `DEGENERATE_HESSIAN`; None for every other outcome, because
            curvature away from an optimum is not a number worth reporting.
        hessian_cond: `cond(H)`, or NaN where it is undefined. **This is the
            number the `DEGENERATE_HESSIAN` verdict was taken on**, recorded
            here rather than recomputed by a caller so the two cannot disagree.

            **NaN MEANS UNDEFINED AND HAS TWO CAUSES, WHICH IS (a2b) RATHER
            THAN A SHORTCUT.** There is no Hessian at all, or there is one and
            it is **not positive definite** -- at which point it is not a
            curvature and its condition number describes nothing. `np.linalg.
            cond` is finite for an indefinite matrix, so a caller reading the
            ratio alone would file such a fit under a severity when what it has
            is a category. **The value is made unavailable, not caveated.**

            **THE POSITIVE-DEFINITENESS TEST DOES NOT MOVE ANY VERDICT.** The
            taxonomy thresholds `cond` and has never tested definiteness; that
            is unchanged here, deliberately, because changing it would move
            `outcome` for some input that previously fit.
    """

    theta: NDArray[np.float64]
    loglik: float
    outcome: Outcome
    n_iter: int
    init_rung: InitRung
    hessian: NDArray[np.float64] | None
    hessian_cond: float


def outcome_for_status(status: int) -> Outcome:
    """Map a scipy termination status to a taxonomy outcome.

    Args:
        status: `OptimizeResult.status`.

    Returns:
        The mapped outcome. An unrecognized status maps to
        `NONFINITE_OBJECTIVE` rather than to `OK`, so a scipy version that
        grows a new code degrades to "something went wrong" instead of to
        silent success.
    """
    return _STATUS_OUTCOMES.get(int(status), Outcome.NONFINITE_OBJECTIVE)


def hessian_step(objective_scale: float, curvature_scale: float | None = None) -> float:
    """Return the second-difference step, `(eps |f| / |f''''|)^(1/4)`.

    **Not `fd_step`.** See the module docstring for the measurements; the
    fourth root rather than the cube root is the whole content of this
    function.

    Args:
        objective_scale: Rough magnitude of the objective, e.g. `|loglik|`.
        curvature_scale: Rough magnitude of its fourth derivative. Defaults to
            `objective_scale`, giving `eps^(1/4)` = 1.221e-04, which a sweep
            over ten decades found sitting on the empirical optimum.

    Returns:
        A step size in unconstrained coordinates, always strictly positive.
    """
    numerator = abs(float(objective_scale))
    denominator = numerator if curvature_scale is None else abs(float(curvature_scale))
    ratio = numerator / denominator if denominator > 0.0 else 0.0
    return float((EPS * max(ratio, _RATIO_FLOOR)) ** 0.25)


def hessian_at_optimum(
    fn: Callable[[NDArray[np.float64]], float],
    u: NDArray[np.float64],
    scale: float = 1.0,
    curvature: float | None = None,
    step: float | None = None,
) -> NDArray[np.float64]:
    """Explicit Hessian by second central differences on the objective.

    Symmetric by construction: each mixed partial is computed once and
    mirrored, which halves the off-diagonal cost and makes the result exactly
    symmetric rather than symmetric to rounding.

    Args:
        fn: Scalar objective of an unconstrained parameter vector.
        u: Point at which to differentiate, shape (p,).
        scale: Rough magnitude of `fn`, used to size the step.
        curvature: Rough magnitude of `fn`'s fourth derivative; see
            `hessian_step`.
        step: Explicit step, overriding the rule.

    Returns:
        The Hessian, shape (p, p).

    Raises:
        ValueError: If `u` is not one-dimensional.
    """
    point = np.asarray(u, dtype=np.float64)
    if point.ndim != 1:
        raise ValueError(
            "the differentiation point must be one-dimensional, shape (p,); got "
            f"shape {point.shape}"
        )
    h = hessian_step(scale, curvature) if step is None else abs(float(step))
    size = point.size
    out = np.zeros((size, size), dtype=np.float64)
    for i in range(size):
        for j in range(i, size):
            ei = np.zeros(size)
            ej = np.zeros(size)
            ei[i] = h
            ej[j] = h
            value = (
                fn(point + ei + ej)
                - fn(point + ei - ej)
                - fn(point - ei + ej)
                + fn(point - ei - ej)
            ) / (4.0 * h * h)
            out[i, j] = out[j, i] = value
    return out


def hessian_condition(hessian: NDArray[np.float64] | None) -> float:
    """`cond(H)` where that describes a curvature, and NaN where it does not.

    **THE STRATIFICATION AXIS OF THE §11.2 HYSTERESIS AUDIT (D9), AND IT LIVES
    HERE RATHER THAN IN THE AUDIT FOR ONE REASON.** `optimize_series` already
    computes `np.linalg.cond` on this matrix to decide `OK` against
    `DEGENERATE_HESSIAN`, and `fit` discards the matrix after inverting it once
    for `theta_err`. An audit that recomputed the curvature from
    `theta_unconstrained` would be binning cells by a number that is **not
    provably the number the outcome verdict was taken on** -- so a cell could
    report `OK` and bin as ill-conditioned, with nothing in the tree able to
    say which was right.

    **NaN IS "UNDEFINED", AND IT HAS TWO CAUSES.** No Hessian at all, or a
    Hessian that is **not positive definite**. `np.linalg.cond` is a ratio of
    singular values, so it returns a perfectly finite number for an indefinite
    matrix -- and a finite-difference Hessian at a converged optimum with one
    near-zero eigenvalue can come back indefinite. Reporting its ratio would
    file a **category** under a **severity**, which is D9's own argument for
    giving `undefined` a bin of its own instead of letting it fall into the
    worst one. (a2b): the value is made unavailable rather than caveated.

    **THIS MOVES NO VERDICT.** The taxonomy thresholds `np.linalg.cond`
    directly and has never tested definiteness. Routing that threshold through
    this function would reclassify every indefinite Hessian as `OK`, since
    `nan > limit` is False -- which is a change to `outcome` for input that
    previously fit, i.e. exactly what a diagnostic is not allowed to be.

    Args:
        hessian: The explicit Hessian of the negative log-likelihood in
            unconstrained coordinates, or None.

    Returns:
        The 2-norm condition number, or NaN where it is undefined.
    """
    if hessian is None:
        return float("nan")
    matrix = np.asarray(hessian, dtype=np.float64)
    if not np.all(np.isfinite(matrix)):
        return float("nan")
    # Cholesky rather than an eigenvalue sign test: it is the definition of
    # positive definiteness for a symmetric matrix, it is cheaper, and it does
    # not need a tolerance -- which would be a picked constant sitting between
    # this function and D9's fixed boundaries.
    try:
        np.linalg.cholesky(matrix)
    except np.linalg.LinAlgError:
        return float("nan")
    return float(np.linalg.cond(matrix))


def moment_init(
    spec: ProcessSpec,
    y: NDArray[np.float64],
    mask: NDArray[np.bool_],
    t: NDArray[np.float64],
) -> tuple[NDArray[np.float64], tuple[InitRung, ...]]:
    """Deterministic moment-based starting point, with a fallback ladder.

    Deterministic rather than random multi-start: reproducible, seed-free, and
    the precursor of the Whittle screening pass. Random multi-start is a
    straight multiplier on a budget with little headroom.

    Ladder, worst rung reached is the one reported:
    `moment` → `clipped` (a usable estimate the model cannot hold) → `default`
    (no usable estimate at all).

    **`r1` outside `(0, 1)` falls to the default rather than being clamped.**
    An OU process has `r1 = exp(-dt/rho)`, strictly inside that interval; a
    non-positive `r1` says the data are anticorrelated at lag 1, which this
    family cannot represent. Clamping to `1e-6` instead yields
    `rho = -dt/log(1e-6) = 0.0724` at `dt = 1` — a specific, plausible,
    entirely fabricated number reported as data-derived.

    **THE RUNG IS PER SERIES.** It is reported per `(series, candidate)` on the
    way to the store, and the conditions that trigger a fallback are per series
    -- one gap-riddled pixel in a tile is the ordinary case, not the exception.
    A single batch-wide rung would be right only when every series in the batch
    falls the same way, which is exactly the situation a test fixture creates
    and real data does not.

    Args:
        spec: The noise specification. Note this takes the SPEC, not the state
            space: parameter defaults and the free-parameter layout both come
            from the spec, and reading them from `family.param_specs()` instead
            is a second, independent ordering source that nothing keeps in sync
            with `free_param_index`.
        y: Observations, shape (B, N).
        mask: Presence mask, shape (B, N).
        t: Shared time axis, shape (N,).

    Returns:
        The starting theta, shape (B, p_free) in natural units, and one rung
        per series, length B. The rung reported is the WORST reached for that
        series: `DEFAULT` if any parameter had no usable data-derived estimate,
        `CLIPPED` if one was produced but had to be constrained to a diagnostic
        limit, `MOMENT` otherwise.
    """
    free = free_param_index(spec)
    by_label = dict(zip(spec.labels(), spec.terms, strict=True))
    defaults = np.array(
        [by_label[label].params[name].default for label, name in free], dtype=np.float64
    )
    batch = y.shape[0]
    start = np.repeat(defaults[None, :], batch, axis=0)

    rungs = [InitRung.MOMENT] * batch

    present = np.asarray(mask, dtype=np.bool_)
    kept = present.sum(axis=1)
    finite = np.where(present, np.asarray(y, dtype=np.float64), np.nan)
    # Restricted to rows with at least two kept samples rather than computed
    # everywhere and masked afterwards: `np.nanvar` of an all-NaN row emits
    # "Degrees of freedom <= 0 for slice", and a wholly-masked series is the
    # ordinary land/ice case, not an anomaly worth a warning on every tile.
    enough = kept > 1
    var = np.zeros(batch, dtype=np.float64)
    if bool(np.any(enough)):
        var[enough] = np.nanvar(finite[enough], axis=1)
    usable_var = enough & np.isfinite(var) & (var > 0.0)

    # Same restriction as the variance, for the same reason: `np.nanmean` of a
    # wholly-masked row warns "Mean of empty slice", and a wholly-masked series
    # is land or permanent ice, which every tile has.
    means = np.zeros((batch, 1), dtype=np.float64)
    observed = kept > 0
    if bool(np.any(observed)):
        means[observed, 0] = np.nanmean(finite[observed], axis=1)
    centred = np.where(present, finite - means, 0.0)
    numerator = np.sum(centred[:, 1:] * centred[:, :-1], axis=1)
    denominator = np.sum(centred**2, axis=1)
    r1 = np.divide(
        numerator, denominator, out=np.zeros_like(numerator), where=denominator > 0
    )
    # An OU process has r1 = exp(-dt/rho), strictly inside (0, 1). Outside it
    # there is no moment estimate to be had, and clamping into [1e-6, 1-1e-6]
    # instead fabricates rho = 0.0724 at dt = 1 and reports it as data-derived.
    usable_rho = usable_var & (r1 > 0.0) & (r1 < 1.0)

    dt = float(np.median(np.diff(t))) if t.size > 1 else 1.0
    with np.errstate(divide="ignore", invalid="ignore"):
        rho = np.where(usable_rho, -dt / np.log(np.where(usable_rho, r1, 0.5)), np.nan)

    for index, (label, name) in enumerate(free):
        param = by_label[label].params[name]
        derived = np.zeros(batch, dtype=np.bool_)
        if name == "sigma":
            # No hidden floor here. `np.sqrt(np.maximum(var, 1e-12))` would
            # report sigma = 1e-6 for ANY series below 1e-12 variance -- above
            # sigma's own 1e-8 lower diagnostic limit, so the clip never fires
            # and the CLIPPED rung becomes unreachable for the
            # vanishing-amplitude case. A floor that pre-empts a diagnostic
            # limit converts a reportable fact into a fabricated number.
            start[usable_var, index] = np.sqrt(var[usable_var])
            derived = usable_var
        elif name == "rho":
            start[usable_rho, index] = rho[usable_rho]
            derived = usable_rho
        clipped = np.clip(start[:, index], *param.diagnostic_limits)
        changed = clipped != start[:, index]
        start[:, index] = clipped
        for series in range(batch):
            if not derived[series]:
                rungs[series] = InitRung.DEFAULT
            elif changed[series] and rungs[series] is InitRung.MOMENT:
                rungs[series] = InitRung.CLIPPED

    unusable = ~np.all(np.isfinite(start), axis=1)
    if bool(np.any(unusable)):
        start[unusable] = defaults
        for row in np.flatnonzero(unusable).tolist():
            rungs[row] = InitRung.DEFAULT
    return start, tuple(rungs)


def ladder_start(
    objective: ConcentratedObjective,
    y: NDArray[np.float64],
    mask: NDArray[np.bool_],
    t: NDArray[np.float64],
) -> tuple[NDArray[np.float64], tuple[InitRung, ...]]:
    """The COLD starting point, in unconstrained coordinates, and its rungs.

    **EXTRACTED SO THERE IS ONE DERIVATION, NOT TWO.** `optimize_series` used to
    inline these two lines, which was fine while it was the only thing that
    needed them. Phase 2c's hysteresis audit needs the same point to build its
    perturbed arms from -- N1 starts at this point plus a tiny epsilon and N2 at
    this point plus a matched displacement -- and `FitResult` records the *rung*
    but not the *start*, so there is no way to read it back afterwards.

    **A second spelling in the audit would be two lines that must stay
    bit-identical**, and the test that depends on it (*"N1 at epsilon = 0 is
    bit-identical to cold"*) would fail the first time either line moved, for a
    reason that is not a defect. Same argument as `_out_of_limits` being pinned
    against `at_diagnostic_limit`, resolved the cheaper way: one function.

    Args:
        objective: The concentrated objective, which owns the transforms.
        y: Observations, shape (B, N).
        mask: Presence mask, shape (B, N).
        t: Shared time axis, shape (N,).

    Returns:
        The start in unconstrained coordinates, shape (B, p_free), and one rung
        per series. **Unconstrained, not natural**: this is what the optimizer
        is handed and what a perturbation has to be expressed in.
    """
    start_natural, rungs = moment_init(objective.spec, y, mask, t)
    return objective.to_unconstrained(start_natural), rungs


def optimize_series(
    objective: ConcentratedObjective,
    y: NDArray[np.float64],
    mask: NDArray[np.bool_],
    t: NDArray[np.float64],
    design: DesignInfo | None,
    x0: NDArray[np.float64] | None = None,
    max_iter: int = DEFAULT_MAX_ITER,
    hessian_cond_limit: float = HESSIAN_COND_LIMIT,
) -> SeriesFit:
    """Fit one series. The batch driver in `fit.py` loops over this.

    Args:
        objective: The concentrated objective.
        y: Observations, shape (1, N).
        mask: Presence mask, shape (1, N).
        t: Shared time axis, shape (N,).
        design: The built design matrix and its theta-free quantities, or None.
        x0: Optional warm start in unconstrained coordinates, shape (1, p).
            When supplied it IS the starting point, not merely a reported rung.
        max_iter: Iteration cap.
        hessian_cond_limit: Condition number above which the fit is reported
            `DEGENERATE_HESSIAN`. Exposed so the branch can be exercised
            without a fixture whose degeneracy is itself in question.

    Returns:
        A `SeriesFit` carrying theta in natural units and a taxonomy outcome.
        See the module docstring for the precedence between outcomes.
    """
    # p is the FREE parameter count, from the single source of truth. Using
    # len(term.params) here would size the vector to include frozen parameters
    # and silently shift every later coordinate.
    free = free_param_index(objective.spec)
    p = len(free)
    # Every early return carries an UNDEFINED condition number, because every
    # early return is a fit with no Hessian. See `hessian_condition`.
    nan = float("nan")

    # The DATA-LEVEL fact is established first and merged with the design
    # precheck through the module's own declared precedence, never decided by
    # which check happens to run first. A wholly-masked series has an all-zero
    # restricted design, so `check_design` calls it RANK_DEFICIENT_X and is not
    # wrong on its own terms -- but land and permanent ice are EXPECTED, and
    # `Outcome.INSUFFICIENT_DATA` keeps them out of both the numerator and the
    # denominator of the section 8.6 failure rate. Short-circuiting on the
    # precheck alone put every land pixel into both.
    data_level = outcome_array(1, Outcome.OK)
    if int(np.count_nonzero(mask)) == 0:
        data_level[0] = Outcome.INSUFFICIENT_DATA.code
    precheck = (
        objective.check_design(design, 1)
        if design is not None and design.matrix.size
        else outcome_array(1, Outcome.OK)
    )
    merged = merge_outcomes(data_level, precheck)
    if int(merged[0]) != Outcome.OK.code:
        return SeriesFit(
            np.full((1, p), np.nan),
            float("nan"),
            Outcome.from_code(int(merged[0])),
            0,
            InitRung.DEFAULT,
            None,
            float("nan"),
        )

    if x0 is None:
        starts, rungs = ladder_start(objective, y, mask, t)
        rung = rungs[0]
        u0 = starts[0]
    else:
        u0, rung = np.asarray(x0, dtype=np.float64)[0], InitRung.WARM_START

    scale = float(max(int(np.count_nonzero(mask)), 1))

    def negative(u: NDArray[np.float64]) -> float:
        # NaN (a failed evaluation) and -inf both become +inf here. This is the
        # ONLY place -inf-as-barrier is used: results destined for the store
        # carry NaN, because -inf is a finite-looking sentinel that survives
        # some consumers' checks and poisons a downstream mean.
        value = objective.unconstrained_loglik(u[None, :], y, mask, t, design)[0]
        return float(np.inf) if not np.isfinite(value) else float(-value)

    def jac(u: NDArray[np.float64]) -> NDArray[np.float64]:
        return fd_gradient(negative, u, scale=scale)

    result = minimize(
        negative, u0, jac=jac, method="L-BFGS-B", options={"maxiter": max_iter}
    )
    theta = objective.to_natural(np.atleast_2d(result.x))
    loglik = -float(result.fun)
    n_iter = int(result.nit)

    if not np.isfinite(loglik):
        # ASK THE OBJECTIVE WHAT IT FAILED OF; do not assert NONFINITE_OBJECTIVE.
        # `evaluate` runs the full ladder -- data level, design precheck, the
        # engine's verdict and the GLS solve, merged by declared precedence --
        # and it is the only thing that can tell ILL_CONDITIONED_X ("barely
        # identified by a handful of post-break samples") from a genuine
        # numerical failure. Measured: the 2-post-break design passes the
        # precheck at full rank 4 with cond(X_r) = 2.68e4 and is classified
        # inside the whitened solve, so the optimizer sees only +inf and would
        # report NONFINITE_OBJECTIVE -- erasing the distinction that outcome was
        # split out to preserve. One extra filter pass, on the failing path only.
        verdict = objective.evaluate(theta, y, mask, t, design).outcome
        failed = (
            Outcome.from_code(int(verdict[0]))
            if int(verdict[0]) != Outcome.OK.code
            else Outcome.NONFINITE_OBJECTIVE
        )
        return SeriesFit(theta, float("nan"), failed, n_iter, rung, None, nan)

    by_label = dict(zip(objective.spec.labels(), objective.spec.terms, strict=True))
    if any(
        by_label[label].params[name].at_diagnostic_limit(float(theta[0, index]))
        for index, (label, name) in enumerate(free)
    ):
        return SeriesFit(
            theta, loglik, Outcome.DIAGNOSTIC_LIMIT, n_iter, rung, None, nan
        )

    status = outcome_for_status(result.status)
    if status is Outcome.TRUST_RADIUS_COLLAPSED:
        return SeriesFit(theta, loglik, status, n_iter, rung, None, nan)

    if status is Outcome.ITER_CAP_LARGE_GRAD or n_iter >= max_iter:
        magnitude = float(np.linalg.norm(jac(result.x)))
        capped = (
            Outcome.ITER_CAP_SMALL_GRAD
            if magnitude < GRAD_TOL * max(abs(loglik), 1.0)
            else Outcome.ITER_CAP_LARGE_GRAD
        )
        return SeriesFit(theta, loglik, capped, n_iter, rung, None, nan)

    if status is not Outcome.OK:
        return SeriesFit(theta, loglik, status, n_iter, rung, None, nan)

    hessian = hessian_at_optimum(negative, result.x, scale=abs(loglik))
    condition = hessian_condition(hessian)
    # **THE VERDICT IS TAKEN ON `np.linalg.cond` AND NOT ON `condition`.** They
    # differ by exactly one thing -- `condition` is NaN for an indefinite
    # matrix -- and `nan > limit` is False, so routing the threshold through it
    # would silently reclassify every indefinite Hessian as `OK`. That is a
    # taxonomy change, which this diagnostic is not allowed to be.
    if float(np.linalg.cond(hessian)) > float(hessian_cond_limit):
        return SeriesFit(
            theta,
            loglik,
            Outcome.DEGENERATE_HESSIAN,
            n_iter,
            rung,
            hessian,
            condition,
        )
    return SeriesFit(theta, loglik, Outcome.OK, n_iter, rung, hessian, condition)
