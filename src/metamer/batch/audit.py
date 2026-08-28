"""§11.2's hysteresis audit: the arms, and the table that makes them readable.

WHAT THIS MODULE IS FOR (design doc §11.2, decision D7).
---------------------------------------------------------
Pass 2 warm-starts every point from a neighbour's converged fit, and §11.1
names the failure that buys: **converged-looking fits at the wrong optimum.**
This module measures it -- **against a designed floor, never against zero.**

**"ARM" HERE IS THE STATISTICAL SENSE, AND THE WORD IS ALREADY TAKEN.**
`reuse`, `resume`, `calibration` and `memory` all use *arm* for a branch of a
conditional -- *"the recompute arm"*, *"the stored > derived arm"*. An arm here
is an **experimental condition**: one way of starting the same fit. Declared
rather than renamed, because it is D7's word and the subject's word, and
inventing a synonym would be worse than a sentence.

THE FOUR-READING TABLE, WRITTEN BEFORE THE ARMS RUN.
-----------------------------------------------------
This is what makes each arm's result **interpretable rather than a number to be
explained afterwards**, and it is here rather than in a commit message for the
same reason a prediction is registered before a measurement.

    N1        N2        warm      the reading
    --------  --------  --------  -----------------------------------------
    non-zero  --        --        THE SURFACE IS DECIDING. No start is
                                  reliable; the disagreement is a property
                                  of the problem, not of warm-starting
    zero      non-zero  non-zero  the sensitivity is to START DISTANCE, not
                                  direction. Benign, NOT hysteresis
    zero      zero      non-zero  THE FINDING THE AUDIT EXISTS TO CATCH:
                                  directional bias toward the neighbour
    zero      zero      zero      no hysteresis at this fixture

THE ARMS, AND WHY EACH IS THE ARM IT IS.
-----------------------------------------
- **`warm`** -- the shipped mechanism: the source map's start, exactly as pass 2
  used it. **Recomputed here rather than read out of pass 2's store**, so all
  four arms come from one batch, one call site and one session; comparing a
  stored result against three fresh ones is a comparison across conditions
  (j5). It is also what makes the whole audit path checkable: the `warm` arm
  must reproduce pass 2's store bitwise at the audited points.
- **`cold`** -- the moment-ladder start, `x0=None`.
- **`N2`** -- cold, displaced by **that cell's own warm/cold start distance** in
  a **random direction**. Hysteresis is *directional bias toward the
  neighbour's answer*, so the control must move the start the same distance
  carrying **no information**. **Matched per cell, never on average.**
- **`N1`** -- the same direction at magnitude `N1_EPSILON`.

**N1 AND N2 SHARE THE DIRECTION, AND THE TABLE'S SECOND ROW IS WHY.** That row
reads *"the sensitivity is to start DISTANCE, not direction"*, and the inference
holds only if the two arms differ in **nothing but distance**. Give N1 a fixed
direction and a non-zero N2 beside a zero N1 has two available explanations --
the magnitude, or the direction N2 happened to draw. The three arms are a
**magnitude ladder along one ray**: `epsilon`, the matched distance, and the
warm start's actual displacement.

**THERE IS NO COLD-VERSUS-COLD ARM AND THE REASON IS RECORDED.** `fit` has no
stochastic component -- every arm of the Task 0 spike returned one distinct
`(n_iter, loglik)` fingerprint across three repeats -- so re-running cold
measures zero **by construction rather than by evidence**, which is not a floor.

**AND TASK 0's `random` ARM IS NOT THIS CONTROL.** It starts from **another
point's converged optimum** -- a real attractor in the same likelihood surface
-- so it **shares the property under test** rather than controlling for it. That
is (j) at the level of an experimental arm, and *"we already have a random arm"*
is the shortcut it is named to prevent.

THE SUBJECT IS FINE POINTS, AND THE COARSE SET CANNOT BE IT.
-------------------------------------------------------------
A coarse point's nearest valid source is **itself** (D12), so pass 2's `warm`
fit there starts from pass 1's own optimum for the same series and the same
candidate. Comparing them asks *"does restarting the optimizer from its own
optimum move it?"* -- **convergence idempotence, with no neighbour in the
comparison at all.** D12 measured it: `self` against `cold` agrees at
**99.58%** where fine points agree at **95.00%**.

**So an audit drawn from pass 1's points is a fixture placed exactly where the
two functions agree** (i7), and those points carry **none** of the effect rather
than merely less of it. The cold arm is therefore **computed**, not read.

**Pass 1's store keeps a narrower and better job**: a free, global, permanent
cold fit at 1/k^2 of the field, whose use is as a **cross-check on this module's
own cold arm** -- a freshly computed cold fit at a coarse point must reproduce
the stored one bitwise. That is a cross-check that passes (j5), unlike the
calibration one D5 rejected on the same test.

WHAT THIS MODULE DOES NOT DO.
------------------------------
**It does not choose the points.** Which points the audit compares is D9's
stratification question and the plan's Task 7; the arms take an explicit point
set, so a test can place cells where it needs them rather than accepting
whatever a selector returns -- and the degenerate cases below are constructible
only that way. `config.audit.subsample` still has no consumer.

**And no command line lands here**, because there is nothing to print until
Task 7 has a report, and a flag that parses and does nothing reads as supported.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

import numpy as np
from numpy.typing import NDArray

from metamer.core.capability import Objective
from metamer.core.criteria import Criterion
from metamer.core.engines.kalman import KalmanEngine
from metamer.core.engines.protocol import Engine
from metamer.core.fit import FitResult, fit, warm_start_faults
from metamer.core.gradients import fd_step
from metamer.core.objective import ConcentratedObjective
from metamer.core.optimize import DEFAULT_MAX_ITER, ladder_start
from metamer.core.signal import SignalSpec
from metamer.core.statespace import StateSpace
from metamer.core.terms import ProcessSpec, free_param_index

N1_EPSILON = fd_step(1.0)
"""N1's displacement, in UNCONSTRAINED coordinates. Derived, not picked.

**IT IS THE SMALLEST DISPLACEMENT THE OPTIMIZER'S GRADIENT CAN RESOLVE.**
`optimize_series` differentiates with `fd_gradient(..., curvature=None)`, whose
ratio is one at every objective scale, so the step it actually takes **is**
`eps^(1/3)` = 6.055e-06 -- and `fd_step`'s own docstring states its result in
unconstrained coordinates, which is the space N1 perturbs. Reusing that
construction rather than naming a second constant is the standing rule: count
the differences (`m = 1`) and read the exponent off `eps^(1/(m+2))`. **Do not
reach for `X_RANK_RTOL`'s `eps^(1/2)`** because `2^-26` looks familiar; it
thresholds a squared quantity and this does not.

**AND THE DERIVATION IS WHAT MAKES THE TABLE'S FIRST ROW READABLE.** *"N1
non-zero"* means the answer moved under a displacement **the optimizer cannot
distinguish from zero** -- i.e. the surface has structure below the resolution
of the method, which is what *"the surface is deciding"* asserts. A picked
`1e-3` would make that row read *"the surface has structure at 1e-3"*, which is
an ordinary property of a likelihood and would fire everywhere.
"""


class Arm(StrEnum):
    """One way of starting the same fit. See the module docstring's table.

    **THE ARM IS THE AUDIT'S OWN LABEL AND IS NEVER READ OFF `init_rung`.**
    `optimize_series` reports `InitRung.WARM_START` whenever an `x0` is
    supplied, without asking where it came from -- so `N1` and `N2` come back
    labelled `warm_start` and only `COLD` reports a ladder rung. That is not a
    defect in `optimize_series`; it is (a2) at an experimental arm, and the
    reason the label lives here.
    """

    WARM = "warm"
    COLD = "cold"
    N1 = "n1"
    N2 = "n2"


@dataclass(frozen=True)
class ArmStarts:
    """The four starting points, and the accounting for the cells that have none.

    Every array is `(B, M[, p_max])`, aligned with `fit`'s own layout.

    Attributes:
        cold: The moment-ladder start in unconstrained coordinates. NaN in the
            padding of any candidate narrower than the widest.
        warm: The source map's start, as pass 2 used it.
        n1: `cold + N1_EPSILON * direction`.
        n2: `cold + distance * direction`.
        warm_valid: Which cells the source map gave a start.
        n1_valid: Which cells N1 may be run on -- `warm_valid` and admissible.
            **N1 needs `warm_valid` even though it does not use the warm start**:
            a cell with no warm start is a cell the audit has no hysteresis
            question about, and running the floor arms there would report a
            floor for a comparison nobody is making.
        n2_valid: The same for N2, which is stricter -- see `n2_inadmissible`.
        distance: `||warm - cold||` per cell, in unconstrained coordinates over
            that candidate's own `p` free parameters. NaN where there is no warm
            start.
        direction: The shared unit vector, NaN where there is no warm start.
        n2_inadmissible: Cells whose N2 start left the diagnostic box. **A real
            distance in a random direction is unbounded and the box is finite**,
            so this is not a corner case. They are EXCLUDED and counted, never
            run: setting `x0_valid` false instead would fall back to the moment
            ladder and fill the N2 arm with **cold** fits, so *"N2 agrees with
            cold"* would be true by construction at exactly the cells where the
            perturbation was largest -- (a0)'s fourth register.
        degenerate: Cells whose `distance` is exactly zero, where N2 collapses
            onto N1 and measures nothing. **Counted separately**, because they
            contribute *"N2 agrees"* to any pooled reading.
    """

    cold: NDArray[np.float64]
    warm: NDArray[np.float64]
    n1: NDArray[np.float64]
    n2: NDArray[np.float64]
    warm_valid: NDArray[np.bool_]
    n1_valid: NDArray[np.bool_]
    n2_valid: NDArray[np.bool_]
    distance: NDArray[np.float64]
    direction: NDArray[np.float64]
    n2_inadmissible: NDArray[np.bool_]
    degenerate: NDArray[np.bool_]


@dataclass(frozen=True)
class AuditArms:
    """One audited batch: the starts, and one `FitResult` per arm.

    Attributes:
        starts: What each arm was started from, and the accounting.
        results: One fit per arm, all four over the same batch in one call site.
        points: The GRID-GLOBAL flat index of each row, as supplied.
        seed: The seed the directions were keyed on.
        epsilon: N1's displacement, as used.
    """

    starts: ArmStarts
    results: dict[Arm, FitResult]
    points: NDArray[np.int64]
    seed: int
    epsilon: float


def _objective_for(
    spec: ProcessSpec, engine: Engine, objective: Objective
) -> ConcentratedObjective:
    """Build the concentrated objective exactly as `core.fit` builds it."""
    return ConcentratedObjective(spec, StateSpace.from_spec(spec), engine, objective)


def cold_starts(
    y: NDArray[np.float64],
    mask: NDArray[np.bool_],
    t: NDArray[np.float64],
    candidates: Sequence[ProcessSpec],
    *,
    engine: Engine,
    objective: Objective,
) -> NDArray[np.float64]:
    """The moment-ladder start for every cell, in `fit`'s `(B, M, p_max)` layout.

    **THIS IS THE POINT THE COLD ARM ACTUALLY STARTS FROM**, obtained through
    `optimize.ladder_start` -- the same function `optimize_series` calls -- so
    N1 at `epsilon = 0` is bit-identical to cold rather than approximately so.
    `FitResult` records the rung and not the start, which is why it has to be
    recomputed rather than read back.

    **`engine` AND `objective` CANNOT MOVE THE RESULT TODAY, AND THEY ARE STILL
    PASSED. MEASURED 2026-08-28.** The ladder start is `moment_init` -- which
    takes the SPEC and the data, neither an engine nor an objective -- followed
    by `to_unconstrained`, which is a per-parameter transform. Substituting
    `Objective.REML` for `Objective.ML` here reproduces the identical array,
    `max |difference| = 0.0`, so a mutation of that argument **survives every
    test in this suite and is not a coverage gap**: the mutant does not differ
    from the original on any input, which is one of (e)'s six causes.

    **They are passed anyway, and that is the (a2c) call made deliberately.**
    What is wanted is *the objective the fit being audited ran under*, and a
    parameterisation that ever became objective-dependent would otherwise make
    the floor arms perturb around a point the production fit never started
    from -- silently, since every array would still have the right shape.
    Recorded here rather than left for a reader to rediscover as a surviving
    mutation.

    Args:
        y: Observations, shape (B, N).
        mask: Presence mask, shape (B, N).
        t: Shared time axis, shape (N,).
        candidates: The candidate set, in model-axis order.
        engine: Likelihood engine.
        objective: ML or REML.

    Returns:
        `(B, M, p_max)` float64, NaN in each candidate's padding.
    """
    batch = int(np.asarray(y).shape[0])
    extents = [len(free_param_index(spec)) for spec in candidates]
    starts = np.full((batch, len(extents), max(extents)), np.nan, dtype=np.float64)
    for model, spec in enumerate(candidates):
        obj = _objective_for(spec, engine, objective)
        point, _ = ladder_start(obj, y, mask, t)
        starts[:, model, : extents[model]] = point
    return starts


def arm_directions(
    points: NDArray[np.int64], extents: Sequence[int], *, seed: int
) -> NDArray[np.float64]:
    """A unit vector per `(point, candidate)`, keyed rather than streamed.

    **DRAWN FROM A KEY, NOT FROM A STREAM, AND THAT IS STRUCTURAL RATHER THAN
    TIDY.** N2 is the only randomness in the system, so it is also the only
    place §11.3's traversal-independence can now be lost -- and one `Generator`
    consumed in a loop loses it: cell `n`'s direction would depend on how many
    cells were drawn before it, hence on the order of the point set, hence on
    tiling if the audit is ever tiled. **Recording the seed does not save that**:
    the same seed under a different order gives different directions, so the
    audit would be reproducible only under a traversal nothing enforces.

    **THE KEY IS THE GRID-GLOBAL POINT INDEX, NEVER A POSITION IN THE
    SUBSAMPLE.** Keying on the row number would make every existing cell's
    direction move when the subsample is enlarged, and two audits of one store
    would not be comparable.

    Args:
        points: Grid-global flat index per row, shape (B,).
        extents: Free-parameter count per candidate, in model-axis order.
        seed: The audit's seed, from `config.audit.seed`.

    Returns:
        `(B, M, p_max)` float64 unit vectors over each candidate's own `p`
        columns, NaN in the padding.
    """
    flat = np.asarray(points, dtype=np.int64)
    widths = list(extents)
    out = np.full((flat.size, len(widths), max(widths)), np.nan, dtype=np.float64)
    for row, point in enumerate(flat.tolist()):
        for model, width in enumerate(widths):
            generator = np.random.default_rng(
                np.random.SeedSequence([int(seed), int(point), int(model)])
            )
            draw = generator.standard_normal(width)
            norm = float(np.linalg.norm(draw))
            # Zero has probability zero in float64 and is still not impossible;
            # redrawing from the SAME generator keeps the result a pure function
            # of the key, which a fallback constant would also do but silently.
            while norm == 0.0:
                draw = generator.standard_normal(width)
                norm = float(np.linalg.norm(draw))
            out[row, model, :width] = draw / norm
    return out


def arm_starts(
    *,
    cold: NDArray[np.float64],
    warm: NDArray[np.float64],
    warm_valid: NDArray[np.bool_],
    candidates: Sequence[ProcessSpec],
    points: NDArray[np.int64],
    seed: int,
    epsilon: float = N1_EPSILON,
) -> ArmStarts:
    """Build the four arms' starting points and the accounting for the rest.

    Args:
        cold: The ladder start, `(B, M, p_max)`, from `cold_starts`.
        warm: The source map's start, `(B, M, p_max)`.
        warm_valid: Which cells the source map gave a start, `(B, M)`.
        candidates: The candidate set, in model-axis order.
        points: Grid-global flat index per row, shape (B,).
        seed: The audit's seed.
        epsilon: N1's displacement. **Zero is legal and is the test case that
            says the perturbation path adds no difference of its own.**

    Returns:
        The starts and the per-cell accounting.

    Raises:
        ValueError: If the arrays disagree about the batch or the candidate set.
    """
    extents = [len(free_param_index(spec)) for spec in candidates]
    cold = np.asarray(cold, dtype=np.float64)
    warm = np.asarray(warm, dtype=np.float64)
    valid = np.asarray(warm_valid, dtype=np.bool_)
    expected = (cold.shape[0], len(extents), max(extents))
    if cold.shape != expected or warm.shape != expected:
        raise ValueError(
            f"cold and warm must both be shape {expected} to match the batch, "
            f"the candidate set and the widest free parameter vector; got "
            f"{cold.shape} and {warm.shape}"
        )
    if valid.shape != expected[:2]:
        raise ValueError(f"warm_valid must be shape {expected[:2]}, got {valid.shape}")
    if np.asarray(points).shape != (expected[0],):
        raise ValueError(
            f"points must carry one grid-global index per row, shape "
            f"{(expected[0],)}, got {np.asarray(points).shape}"
        )

    direction = arm_directions(points, extents, seed=seed)

    # **PER CELL, OVER THAT CANDIDATE'S OWN `p`.** A norm over the full `p_max`
    # width would be NaN for every candidate but the widest, and a norm over a
    # zero-filled padding would understate the distance for the narrow ones.
    distance = np.full(expected[:2], np.nan, dtype=np.float64)
    for model, width in enumerate(extents):
        gap = warm[:, model, :width] - cold[:, model, :width]
        distance[:, model] = np.linalg.norm(gap, axis=1)
    distance[~valid] = np.nan

    scale = np.where(valid, np.nan_to_num(distance, nan=0.0), 0.0)
    n1 = cold + float(epsilon) * np.nan_to_num(direction, nan=0.0)
    n2 = cold + scale[:, :, None] * np.nan_to_num(direction, nan=0.0)
    # The padding is NaN in `cold` and must stay NaN: adding a zeroed direction
    # to NaN leaves NaN, which is what the two lines above rely on.

    admissible, _ = warm_start_faults(n2, list(candidates))
    inadmissible = valid & ~admissible
    degenerate = valid & (distance == 0.0)

    return ArmStarts(
        cold=cold,
        warm=warm,
        n1=n1,
        n2=n2,
        warm_valid=valid,
        n1_valid=valid,
        n2_valid=valid & admissible,
        distance=distance,
        direction=direction,
        n2_inadmissible=inadmissible,
        degenerate=degenerate,
    )


def run_arms(
    y: NDArray[np.float64],
    t: NDArray[np.float64],
    signal: SignalSpec,
    candidates: Sequence[ProcessSpec],
    criterion: Criterion,
    *,
    mask: NDArray[np.bool_],
    warm: NDArray[np.float64],
    warm_valid: NDArray[np.bool_],
    points: NDArray[np.int64],
    seed: int,
    objective: Objective = Objective.ML,
    engine: Engine | None = None,
    max_iter: int = DEFAULT_MAX_ITER,
    epsilon: float = N1_EPSILON,
) -> AuditArms:
    """Fit one batch four ways and return every arm.

    **ALL FOUR ARMS COME FROM ONE BATCH, ONE CALL SITE AND ONE SESSION**, which
    is the discipline that kept a spurious 15% out of the stride sweep's
    `T_warm/T_cold` when the cold arm was re-run rather than reused across
    sessions. Here the cost of getting it wrong is not drift but comparability:
    a stored `warm` beside three fresh arms is a comparison across conditions.

    Args:
        y: Observations for the audited points, shape (B, N), in the order
            `points` names them.
        t: Shared time axis, shape (N,).
        signal: The signal specification.
        candidates: The candidate set, in model-axis order.
        criterion: Information criterion, for the ranking `fit` returns.
        mask: Presence mask, shape (B, N).
        warm: The source map's starts, `(B, M, p_max)`.
        warm_valid: `SourceMap.valid` for those cells, `(B, M)`.
        points: Grid-global flat index per row, shape (B,).
        seed: `config.audit.seed`.
        objective: ML or REML.
        engine: Likelihood engine. Defaults to the batched Kalman filter, as
            `fit` does.
        max_iter: Iteration cap per series.
        epsilon: N1's displacement.

    Returns:
        The starts and one `FitResult` per arm.
    """
    specs = list(candidates)
    # **THE SAME RESOLUTION `fit` MAKES, MADE HERE TOO.** The ladder start is a
    # property of the objective, which is built around an engine, so an audit
    # whose cold arm resolved the default differently from the fit it is
    # auditing would perturb around a point the fit never started from.
    resolved = KalmanEngine() if engine is None else engine
    cold = cold_starts(y, mask, t, specs, engine=resolved, objective=objective)
    starts = arm_starts(
        cold=cold,
        warm=warm,
        warm_valid=warm_valid,
        candidates=specs,
        points=points,
        seed=seed,
        epsilon=epsilon,
    )

    def _fit(
        x0: NDArray[np.float64] | None, x0_valid: NDArray[np.bool_] | None
    ) -> FitResult:
        return fit(
            y,
            t,
            signal,
            specs,
            criterion,
            mask=mask,
            objective=objective,
            engine=engine,
            x0=x0,
            x0_valid=x0_valid,
            max_iter=max_iter,
        )

    results = {
        Arm.COLD: _fit(None, None),
        Arm.WARM: _fit(starts.warm, starts.warm_valid),
        Arm.N1: _fit(starts.n1, starts.n1_valid),
        Arm.N2: _fit(starts.n2, starts.n2_valid),
    }
    return AuditArms(
        starts=starts,
        results=results,
        points=np.asarray(points, dtype=np.int64),
        seed=int(seed),
        epsilon=float(epsilon),
    )


__all__ = [
    "N1_EPSILON",
    "Arm",
    "ArmStarts",
    "AuditArms",
    "arm_directions",
    "arm_starts",
    "cold_starts",
    "run_arms",
]
