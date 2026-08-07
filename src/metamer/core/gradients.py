"""Gradient strategies: finite differences, the step rule, and the oracle.

Finite differences are the Phase 1 default because they cost zero per-family
work. Analytic forward-mode is the target (`1 + p` passes against FD's `2p`, and
exact). The third routine here, complex-step, exists to be an ORACLE -- an exact
gradient requiring no derivation, so it can catch an incorrect hand-derived
`dQ/dtheta`. FD alone cannot play that role: agreeing to 1e-8 with a wrong
analytic gradient is entirely possible. Design doc §8.2.

COMPLEX-STEP IS NOT VIABLE THROUGH THIS FILTER. RICHARDSON IS THE ORACLE.
------------------------------------------------------------------------
Measured, not assumed: complex-step through `ConcentratedObjective` returns a
gradient of exactly `[0, 0]`, a relative disagreement of `1.000e+00` against the
Romberg reference. The cause is not one of the non-analytic operations design
doc §8.2 anticipated -- no `abs`, no `min`/`max`, no comparison branch. It is an
explicit dtype cast: `ConcentratedObjective._map` does
`np.asarray(values, dtype=np.float64)` before any arithmetic, so the imaginary
perturbation is discarded at `to_natural`, before the filter is reached. Every
bijector in `transforms.py` and `KalmanEngine.score`'s own entry casts repeat it
independently, so making complex-step live is a three-layer change and not a
one-line one. Full write-up with the staged measurements:
`docs/superpowers/notes/complex-step-verdict.md`.

So `richardson_gradient` is the adopted oracle, which is the fallback design doc
§8.2 named for exactly this outcome. It reaches ~6e-14 relative on an
analytically differentiable function, against plain central differences'
~4e-11 -- a factor of ~760, and comfortably enough to catch a wrong `dQ/dtheta`,
which produces O(1) relative error rather than O(1e-7).

THE STEP RULE CARRIES A CURVATURE DENOMINATOR, AND DROPPING IT IS EXPENSIVE.
---------------------------------------------------------------------------
Central-difference error is `h^2 |l'''| / 6` (truncation) plus `eps |l| / h`
(cancellation), so the optimum is `h ~ (eps |l| / |l'''|)^(1/3)` -- design doc
§8.2 writes the same structure as `(eps |l| / |l''|)^(1/3)`. **The denominator is
not decoration.** For a log-likelihood, `|l|` and its derivatives BOTH scale with
N, so the ratio is O(1) and the optimal step barely moves with N. Measured on
`matern32` against a Romberg reference, sweeping `h` over ten decades:

    N       |loglik|    best h measured    (eps|l|)^(1/3)    (eps|l|/|l''|)^(1/3)
      100      3 178          1e-06            8.90e-05             6.06e-06
      630     23 521          1e-05            1.74e-04             6.06e-06
     5000    216 556          1e-05            3.64e-04             6.06e-06

and the resulting relative gradient error:

    N       (eps|l|)^(1/3)    this rule
      100        1.19e-08      4.28e-11
      630        4.51e-08      1.00e-10
     5000        1.98e-07      1.76e-10

Dropping the denominator puts every step in the truncation-dominated region and
costs 280x to 1100x in accuracy -- and at N = 5000 it misses the 1e-7 relative
target this task was set. The truncation branch of the sweep is identical across
N to three digits (1.501e-08, 1.498e-08, 1.497e-08 at h = 1e-4), which is the
direct evidence that `|l'''| / |l'|` does not vary with N.

STEPS ARE TAKEN IN UNCONSTRAINED COORDINATES.
---------------------------------------------
Where log and logit transforms have already made every coordinate O(1)-scaled,
one relative step serves every family -- a second dividend from the `ParamSpec`
contract (§4.1). Perturbing natural parameters instead differs by exactly the
bijector Jacobian, which is smooth, silent, and wrong: at `theta = [1, 5]` it is
a factor of five on the second component.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

import numpy as np
from numpy.typing import NDArray

from metamer.core.capability import (
    GradientMode,
    Objective,
    intersect_gradient_modes,
)
from metamer.core.families.base import supports_analytic_gradient
from metamer.core.terms import ProcessSpec

EPS: float = float(np.finfo(np.float64).eps)
"""Machine epsilon for float64, the `eps` of the step rule."""

RICHARDSON_H0: float = 1e-2
"""Starting step for the extrapolation, chosen to sit ABOVE the FD optimum.

Richardson extrapolates the TRUNCATION series, so it must start where
truncation dominates. Starting at the FD optimum extrapolates rounding noise
instead, and is measurably worse than the plain difference it was meant to
improve -- on the analytic reference: 5.80e-14 from `h0 = 1e-2`, against
5.08e-11 from `h0 = 6.06e-6` and 4.43e-11 for the plain central difference.
"""

RICHARDSON_LEVELS: int = 4
"""Halvings in the Romberg tableau. Four is enough and six is waste.

Measured against a six-level tableau on the real filter: agreement to 7.4e-13
(N = 100), 1.1e-12 (N = 630) and 6.7e-12 (N = 5000), all far below the 1e-8 at
which the step rule is judged. Six levels costs 50% more filter passes for
resolution nothing reads.
"""

_RATIO_FLOOR: float = 1.0
"""Smallest admissible `|l| / |l''|`, so a degenerate scale cannot give h = 0.

A zero step divides by zero in every gradient component. Flooring the RATIO
rather than the step keeps the rule's units honest: the floor says "assume the
objective is no flatter than its own curvature", which is the neutral
assumption, and it makes `fd_step(x)` with no curvature return `eps^(1/3)`.
"""


def fd_step(objective_scale: float, curvature_scale: float | None = None) -> float:
    """Return the central-difference step, `(eps |l| / |l''|)^(1/3)`.

    See the module docstring for why the denominator is load-bearing and for
    the measurements that fix it.

    Args:
        objective_scale: Rough magnitude of the objective, e.g. `|loglik|`.
        curvature_scale: Rough magnitude of its second derivative. Defaults to
            `objective_scale`, i.e. a ratio of one, which is the right default
            for a log-likelihood because both scale with N. Passing only
            `objective_scale` therefore gives `eps^(1/3)` = 6.055e-06, measured
            to sit inside the optimum `h in [1e-6, 1e-5]` at every N tested.

    Returns:
        A step size in unconstrained coordinates, always strictly positive.
    """
    numerator = abs(float(objective_scale))
    denominator = numerator if curvature_scale is None else abs(float(curvature_scale))
    ratio = numerator / denominator if denominator > 0.0 else 0.0
    return float((EPS * max(ratio, _RATIO_FLOOR)) ** (1.0 / 3.0))


def fd_gradient(
    fn: Callable[[NDArray[np.float64]], float],
    u: NDArray[np.float64],
    scale: float = 1.0,
    curvature: float | None = None,
    step: float | None = None,
) -> NDArray[np.float64]:
    """Central-difference gradient in unconstrained coordinates.

    Args:
        fn: Scalar objective of an unconstrained parameter vector.
        u: Point at which to differentiate, shape (p,). **Not** (1, p) -- see
            Raises.
        scale: Rough magnitude of `fn`, used to size the step.
        curvature: Rough magnitude of `fn`'s second derivative; see `fd_step`.
        step: Explicit step, overriding the rule entirely.

    Returns:
        Gradient, shape (p,). NaN components where `fn` returned a non-finite
        value: a failed evaluation must propagate, because a gradient of zero
        reads to the optimizer as a stationary point and would report a failed
        series as converged at its starting value.

    Raises:
        ValueError: If `u` is not one-dimensional. `(1, p)` is the shape every
            objective in this package wants, so it is the shape that arrives
            here by mistake, and it would iterate over one row.
    """
    point = _as_point(u)
    h = fd_step(scale, curvature) if step is None else abs(float(step))
    out = np.empty_like(point)
    for i in range(point.size):
        offset = np.zeros_like(point)
        offset[i] = h
        out[i] = (fn(point + offset) - fn(point - offset)) / (2.0 * h)
    return out


def richardson_gradient(
    fn: Callable[[NDArray[np.float64]], float],
    u: NDArray[np.float64],
    h0: float = RICHARDSON_H0,
    levels: int = RICHARDSON_LEVELS,
) -> NDArray[np.float64]:
    """Romberg-extrapolated central differences: the adopted gradient oracle.

    Repeated Richardson on the central-difference tableau. Central differences
    have an error expansion in even powers of `h`, so level `m` cancels the
    `h^(2m)` term and the deepest entry is `O(h^(2*levels))`.

    This is the oracle because complex-step is not viable through this filter
    -- see the module docstring and the verdict note.

    Args:
        fn: Scalar objective of an unconstrained parameter vector.
        u: Point at which to differentiate, shape (p,).
        h0: Starting step. Must sit in the truncation-dominated region; see
            `RICHARDSON_H0` for what happens when it does not.
        levels: Number of halvings; see `RICHARDSON_LEVELS`.

    Returns:
        Gradient, shape (p,).

    Raises:
        ValueError: If `u` is not one-dimensional, or if `levels` is below 1.
    """
    point = _as_point(u)
    if int(levels) < 1:
        raise ValueError(f"levels must be at least 1, got {levels}")
    out = np.empty_like(point)
    for i in range(point.size):
        row = [
            float(fd_gradient(fn, point, step=h0 / 2**k)[i]) for k in range(int(levels))
        ]
        for m in range(1, int(levels)):
            factor = 4.0**m
            row = [
                (factor * row[k + 1] - row[k]) / (factor - 1.0)
                for k in range(len(row) - 1)
            ]
        out[i] = row[0]
    return out


def complex_step_gradient(
    fn: Callable[[Any], Any],
    u: NDArray[np.float64],
    step: float = 1e-20,
) -> NDArray[np.float64]:
    """Complex-step derivative: exact, with no subtractive cancellation.

    **Not viable through `ConcentratedObjective` as of Task 11** -- it returns
    exactly zero there, because the objective casts to float64 before any
    arithmetic. Kept because the routine itself is correct (verified against an
    analytic function to 1e-13) and because it becomes the better oracle the
    moment the cast chain is made dtype-following. Use `richardson_gradient`
    for anything that must work today.

    Requires the whole evaluation path to be complex-analytic. `abs`, `max`,
    `min`, comparison-based branches, numpy's conjugating norms, sorting and
    clipping guards all silently return a WRONG derivative rather than raising
    -- which is why viability is measured rather than assumed.

    Args:
        fn: Objective, which must accept a complex argument and return a
            complex value. A wrapper that calls `float()` on its result throws
            the answer away before this function sees it.
        u: Point at which to differentiate, shape (p,).
        step: Imaginary step. 1e-20 is safe because there is no cancellation to
            trade against truncation.

    Returns:
        Gradient, shape (p,). All zeros if the path discarded the imaginary
        part, which is the failure mode and is not detectable from here.

    Raises:
        ValueError: If `u` is not one-dimensional.
    """
    point = _as_point(u)
    out = np.empty_like(point)
    for i in range(point.size):
        offset = np.zeros(point.size, dtype=np.complex128)
        offset[i] = 1j * step
        value = fn(point.astype(np.complex128) + offset)
        out[i] = float(np.imag(np.asarray(value, dtype=np.complex128))) / step
    return out


class AnalyticGradientError(ValueError):
    """A family declares an analytic gradient it does not implement."""


def resolve_gradient_mode(
    spec: ProcessSpec,
    objective: Objective,
    families: Sequence[object] | None = None,
) -> GradientMode:
    """Resolve a composite's gradient mode, and verify the claim.

    **The resolved mode is a reported field, never a silent decision.** A
    composite that falls back to finite differences must say so — it is a
    ~1.7× cost difference at p = 6, and an unreported fallback makes the
    wall-time projection wrong in the direction that looks fine until the 19 ms
    budget is measured.

    **What ANALYTIC means here, precisely:** every term supplies analytic
    `dF/dθ`, `dQ/dθ` and `dP∞/dθ` for this objective. It does **not** mean the
    optimizer used an analytic gradient — Phase 1 ships no differentiated
    Kalman filter, so `fd_gradient` still runs. The two are named apart on
    purpose; when the differentiated filter lands, this docstring is what has
    to change.

    Args:
        spec: The composite noise specification.
        objective: The objective being evaluated. Capability is per
            `(family, objective)`: a family may ship analytic ML gradients
            before REML ones, because the envelope theorem covers the
            concentrated ML objective and not the REML penalty.
        families: Family instances to resolve over, for testing a kernel that
            is not in the registry. Defaults to looking each term's `kind` up
            in `kernel_registry`.

    Returns:
        ANALYTIC only if every term declares and implements it for this
        objective; FINITE_DIFFERENCE otherwise.

    Raises:
        AnalyticGradientError: If a family declares ANALYTIC for this objective
            without satisfying `DifferentiableFamily`. Refused rather than
            quietly downgraded: a mode corrected behind the caller's back is
            not a reported mode, and the declaration is a bug in the kernel
            that should surface where it was made.
    """
    from metamer.core.registry import kernel_registry

    resolved = (
        list(families)
        if families is not None
        else [kernel_registry[term.kind]() for term in spec.terms]
    )
    modes: list[Mapping[Objective, GradientMode]] = []
    for family in resolved:
        declared = getattr(family, "gradient_modes", {})
        claim = declared.get(objective, GradientMode.FINITE_DIFFERENCE)
        if claim is GradientMode.ANALYTIC and not supports_analytic_gradient(family):
            raise AnalyticGradientError(
                f"family {getattr(family, 'kind', family)!r} declares "
                f"{GradientMode.ANALYTIC.value} gradients for "
                f"{objective.value} but does not implement dtransition, "
                "dprocess_noise and dstationary_cov. A declared mode that no "
                "method backs makes a composite report ANALYTIC while finite "
                "differences silently run"
            )
        modes.append(declared)
    return intersect_gradient_modes(modes, objective)


def _as_point(u: NDArray[np.float64]) -> NDArray[np.float64]:
    """Coerce a differentiation point and check that it is a vector.

    Args:
        u: Candidate point.

    Returns:
        The point as a float64 vector, shape (p,).

    Raises:
        ValueError: If `u` is not one-dimensional.
    """
    point = np.asarray(u, dtype=np.float64)
    if point.ndim != 1:
        raise ValueError(
            "the differentiation point must be one-dimensional, shape (p,); got "
            f"shape {point.shape}. A (1, p) row is the shape the objectives take, "
            "not the shape this differentiates over"
        )
    return point
