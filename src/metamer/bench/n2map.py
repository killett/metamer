"""The audit's N2 arm, over every point of the field: the floor for a smear.

## Why this arm exists, stated where the map is defined

**A SMEAR MEASURED AGAINST ZERO IS A DIFFERENT CLAIM FROM A SMEAR MEASURED
AGAINST THE WIDTH AN EQUAL-DISTANCE RANDOM START PRODUCES.** Zero is not a
floor; it is the **absence** of one, and a width read against it silently
asserts that a random start of the same magnitude would have produced none.
N2 is that assertion turned into a measurement: **cold, displaced by that
cell's own warm/cold distance in a random direction** -- the same distance
carrying no information about the neighbour's answer.

This module is the only artifact that carries the sentence into Task 5's
report, so the sentence is here rather than in a plan.

## What this module does NOT do, which is most of N2

**`arm_starts` ALREADY BUILDS N2 AND ALREADY GETS THE FOUR HARD THINGS RIGHT.**
The perturbation is matched **per cell, never on average**; the direction is
drawn from a **key** -- `SeedSequence([audit.seed, GRID-GLOBAL point, model])`
-- rather than streamed, so it is independent of traversal order; **N1 and N2
share that direction**, without which the four-reading table's second row does
not follow; and the cells N2 cannot run are counted rather than silently
substituted.

**So this module REDUCES rather than derives.** A second derivation of N2 would
be a second N2, and the floor and the audit would disagree about what N2 is --
quietly, since both would be plausible numbers.

## The one thing the reduction must ADD: the exclusion

**`run_arms` FITS THE EXCLUDED CELLS COLD, AND THAT IS NOT A DEFECT IN IT.**
`arm_starts` sets `n2_valid = warm_valid & admissible`; `run_arms` passes that
as `x0_valid`; and `fit` **falls back to the moment ladder wherever `x0_valid`
is false** -- which is the cold start. So the N2 `FitResult` contains cold fits
at exactly the cells the accounting excludes. Refusing inside `run_arms` would
abort a whole audit over one cell, which is why `warm_start_faults` exists as a
mask and not as a refusal.

**The exclusion is therefore the CONSUMER's, and this is the first consumer.**
`ArmStarts.n2_inadmissible`'s docstring says such cells are *"EXCLUDED and
counted, never run"*; read against the code that describes the **accounting**,
not the fit, and a reader who checks `run_arms` for the guarantee finds a
sentence that appears to give it. **`tests/test_bench_n2map.py` asserts the
fallback really happens** before this module is credited with removing it, or
*"the map holds no cold fit"* would be a claim about a fault nobody has seen.

## Cells are excluded; the map is per point; the reduction is ANY

`ArmStarts`' accounting is `(B, M)`. The selected candidate is `(B,)`, from
`ranking.best_index`, which **compares every candidate's score against every
other**. So a point where candidate 1 fell back to the ladder while candidates
0 and 2 ran N2 has a winner decided **partly by a cold fit**, and its selection
is not the N2 arm's.

**A point is excluded if ANY of its candidates is.** An `all()` reduction keeps
exactly the mixed points -- whose value is neither N2's nor cold's -- and
nothing downstream could identify them, because a mixed winner is an ordinary
candidate index.

## The counts, which are an identity rather than three numbers

    excluded == exhausted_spiral + inadmissible

**Exhaustion takes precedence**, so the two reasons are disjoint and a point
qualifying under both is counted once. `zero_distance` is **reported and not
excluded**: at a matched distance of exactly zero the equal-distance random
start **is** the cold start, so the cell's N2 value is the floor at that cell --
a correct reading, not a missing one, and dropping it would be discarding cells
for having an inconvenient answer. It is counted because such cells contribute
*"N2 agrees with cold"* **by construction**, and a floor built largely from them
is a floor about the field's degeneracy rather than about random starts.

## The key is grid-global, and that guarantees ONE axis

The direction's key is the row-major flat index `iy * n_parallel + ix`.
**Adding rows -- growing along the normal axis -- leaves every existing point's
index untouched.** Adding **columns** changes the **stride** and therefore moves
every existing point's index but the first row's, and with it its direction.

**That is a property of the key, not a defect**, and it is stated because the
plan's *"enlarging the field does not move an existing point's direction"*
claims more than a flat index can deliver. The alternative -- keying on
`(iy, ix)` -- is unavailable: `arm_directions` takes the flat index that
`SourceMap` and pass 1's store are both written against, so a second key here
would be a second N2. **2d's field never grows in either axis.**
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from metamer.batch.audit import (
    N1_EPSILON,
    Arm,
    AuditArms,
    arm_directions,
    cold_starts,
    run_arms,
)
from metamer.batch.store import SELECTED_UNSET
from metamer.core.capability import Objective
from metamer.core.criteria import Criterion
from metamer.core.engines.kalman import KalmanEngine
from metamer.core.engines.protocol import Engine
from metamer.core.optimize import DEFAULT_MAX_ITER
from metamer.core.signal import SignalSpec
from metamer.core.terms import ProcessSpec, free_param_index

#: The objective the benchmark's fits run under, named once so a caller
#: building a cold start by hand and this module cannot disagree about the
#: point the floor arms perturb around.
DEFAULT_OBJECTIVE: Objective = Objective.ML


@dataclass(frozen=True)
class N2Counts:
    """Why the map is missing the points it is missing.

    **THE COUNT TRAVELS WITH THE MAP AND IS NEVER FOLDED INTO IT.** An excluded
    point holds `SELECTED_UNSET`, and how many there are and why is a separate
    reading -- a map alone cannot say whether an absence was the source map's
    fault or the perturbation's, and those send a reader to different places.

    **"EXCLUDED" MEANS EXCLUDED FROM THIS MAP, NOT ABSENT FROM THE FIT.** Those
    cells **were fitted** -- `fit` fell back to the moment ladder and produced a
    COLD result for them, which is exactly why the map has to drop them. A
    reader who takes `excluded` as a count of unfitted cells will look for them
    in the store and find ordinary fits there. The count is about the ARM's
    accounting; the fit happened.

    Attributes:
        excluded: Points with no N2 value **in this map**. **Equal to
            `exhausted_spiral + inadmissible`**, which a test asserts.
        exhausted_spiral: Excluded because some candidate had **no warm
            source**, so there is no distance to match. Named for the only
            thing that makes `SourceMap.valid` false -- it is `index >= 0` and
            `index` is `-1` only where the spiral was exhausted. **A caller
            passing a validity array derived some other way mislabels its own
            cells**, and this sentence is the contract.
        inadmissible: Excluded because some candidate's N2 start **left the
            diagnostic box**. Counted only where the point is not already
            excluded for exhaustion, so the two are disjoint.
        zero_distance: Points where some candidate's warm/cold distance is
            exactly zero. **NOT excluded** -- see the module docstring.
    """

    excluded: int
    exhausted_spiral: int
    inadmissible: int
    zero_distance: int


def point_directions(
    grid_shape: tuple[int, int], extents: Sequence[int], *, seed: int
) -> NDArray[np.float64]:
    """The N2 direction for every point of a grid, keyed on its flat index.

    **A THIN WRAPPER OVER `arm_directions`, AND THAT IS THE POINT.** It exists
    so the grid-to-key arithmetic has one home and can be tested without
    fitting anything; it derives no direction of its own.

    Args:
        grid_shape: `(n_normal, n_parallel)`.
        extents: Free-parameter count per candidate, in model-axis order.
        seed: The audit's seed, `config.audit.seed`.

    Returns:
        `(n_normal * n_parallel, M, p_max)` unit vectors, in row-major point
        order.
    """
    n_normal, n_parallel = grid_shape
    points = np.arange(n_normal * n_parallel, dtype=np.int64)
    return arm_directions(points, list(extents), seed=seed)


@dataclass(frozen=True)
class FieldArms:
    """The N2 map, its accounting, **and the three arms the call also fitted**.

    **THE CALL RUNS FOUR ARMS AND USED TO RETURN ONE.** `run_arms` fits `COLD`,
    `WARM`, `N1` and `N2` over the whole field; the map is a reduction of the
    last. Discarding the other three meant **paying for three full-field arms
    and throwing them away**, which is the opposite of the usual trade -- and
    each is a reading 2d is otherwise short of:

    | arm | what it answers |
    |---|---|
    | `N1` | its cost against cold's, which is 2d's separation of *"the surface decides"* from *"the start distance decides"*. There is no other N1 in the benchmark |
    | `COLD` | the same 384 fits the driver's cold `run` writes to a store, **by a second code path** -- so `run`'s tiled fit phase against a bare `fit`, bit-exact, because iterations are deterministic |
    | `WARM` | the only check that the driver's REBUILT warm array is the one pass 2 actually used. **N1 and N2 are displacements from that array**, so a wrong rebuild is not visible as an error -- it is visible as a smear |

    Attributes:
        selected: The N2 selection map, `SELECTED_UNSET` where excluded.
        counts: The exclusion accounting.
        arms: Every arm, as `run_arms` returned it. **Not a copy and not a
            reduction** -- a second reduction of one fit is a second spelling of
            it, and the consumers here want different things from the same
            object.
    """

    selected: NDArray[np.int16]
    counts: N2Counts
    arms: AuditArms


def n2_field_map(
    y: NDArray[np.float64],
    t: NDArray[np.float64],
    signal: SignalSpec,
    candidates: Sequence[ProcessSpec],
    criterion: Criterion,
    *,
    mask: NDArray[np.bool_],
    warm: NDArray[np.float64],
    warm_valid: NDArray[np.bool_],
    grid_shape: tuple[int, int],
    seed: int,
    objective: Objective = DEFAULT_OBJECTIVE,
    engine: Engine | None = None,
    max_iter: int = DEFAULT_MAX_ITER,
    epsilon: float = N1_EPSILON,
) -> tuple[NDArray[np.int16], N2Counts]:
    """The N2 map and its counts alone: a view of `field_arms`, not a second run.

    Every argument is `field_arms`', and the reduction happens exactly once --
    two entry points, one exclusion rule, because `excluded ==
    exhausted_spiral + inadmissible` is asserted as an identity in one place
    and a second copy would hold until one of them was edited.

    Returns:
        The map and the accounting. **Callers that want the arms the call
        already fitted use `field_arms`**; this one exists because most
        callers do not, and because it is the signature Tasks 2 and 3 bound
        against.
    """
    result = field_arms(
        y,
        t,
        signal,
        candidates,
        criterion,
        mask=mask,
        warm=warm,
        warm_valid=warm_valid,
        grid_shape=grid_shape,
        seed=seed,
        objective=objective,
        engine=engine,
        max_iter=max_iter,
        epsilon=epsilon,
    )
    return result.selected, result.counts


def field_arms(
    y: NDArray[np.float64],
    t: NDArray[np.float64],
    signal: SignalSpec,
    candidates: Sequence[ProcessSpec],
    criterion: Criterion,
    *,
    mask: NDArray[np.bool_],
    warm: NDArray[np.float64],
    warm_valid: NDArray[np.bool_],
    grid_shape: tuple[int, int],
    seed: int,
    objective: Objective = DEFAULT_OBJECTIVE,
    engine: Engine | None = None,
    max_iter: int = DEFAULT_MAX_ITER,
    epsilon: float = N1_EPSILON,
) -> FieldArms:
    """Run the audit's arms over a whole field and reduce N2 to a map.

    **THE MAP IS THE SELECTED CANDIDATE**, `fields.SMEAR_SUBJECT`, in
    `/selection/selected`'s own `int16` vocabulary -- so `smear.agreement_map`
    consumes it with no adapter between the two tasks, which is where a third
    spelling of the subject would otherwise live.

    Args:
        y: Observations for **every point of the field**, shape `(B, N)`, in
            **row-major grid order** -- the order `tiling.assemble_tile`
            returns series in and the order `SourceMap`'s rows are written
            against. **The shape check below catches a wrong COUNT and not a
            wrong ORDER**, and that limitation is stated rather than implied:
            a permuted batch produces a silently mis-keyed map.
        t: Shared time axis, shape `(N,)`. **From `to_decimal_years` of the
            store's own coordinate, never hand-built** -- the conversion is
            under `ALGORITHM_VERSION`.
        signal: The signal specification.
        candidates: The candidate set, in model-axis order.
        criterion: Information criterion, for the ranking.
        mask: Presence mask, shape `(B, N)`.
        warm: The source map's starts, `(B, M, p_max)`.
        warm_valid: `SourceMap.valid` for those cells, `(B, M)`.
        grid_shape: `(n_normal, n_parallel)`. **The point set is derived from
            it** -- a full-field map is every point in row-major order, so
            there is no freedom in it and it is not a parameter a caller can
            get wrong.
        seed: `config.audit.seed`. **Not `Config.seed`**: `fit` has no
            stochastic component, so N2 is the only randomness in the system
            and this is the one place reproducibility can be lost.
        objective: ML or REML.
        engine: Likelihood engine. Defaults to the batched Kalman filter.
        max_iter: Iteration cap per series.
        epsilon: N1's displacement. Passed through because N1 and N2 share the
            direction and `run_arms` builds both.

    Returns:
        The `(n_normal, n_parallel)` `int16` selection map, `SELECTED_UNSET`
        at every excluded point, the accounting, **and every arm the call
        fitted**. **`-1` stays available for its own meaning** -- *"a fit ran
        and no candidate won"* -- because both sentinels become NaN in
        `agreement_map` and the distinction can only be got right here.

    Raises:
        ValueError: If the batch is not the whole grid.
    """
    n_normal, n_parallel = grid_shape
    n_points = int(n_normal) * int(n_parallel)
    observations = np.asarray(y, dtype=np.float64)
    if observations.shape[0] != n_points:
        raise ValueError(
            f"a full-field map is every point of the grid: {grid_shape} is "
            f"{n_points} points, got a batch of {observations.shape[0]}. The "
            "point set is derived from the grid, so a partial batch would be "
            "keyed against positions its data does not occupy"
        )

    specs = list(candidates)
    arms = run_arms(
        observations,
        t,
        signal,
        specs,
        criterion,
        mask=mask,
        warm=warm,
        warm_valid=warm_valid,
        points=np.arange(n_points, dtype=np.int64),
        seed=seed,
        objective=objective,
        engine=engine,
        max_iter=max_iter,
        epsilon=epsilon,
    )
    starts = arms.starts

    # **ANY, NOT ALL, AND THE REDUCTION IS THE SPECIFICATION RATHER THAN A
    # DETAIL.** `best_index` compares EVERY candidate's score against every
    # other, so one candidate that fell back to the ladder makes the winner
    # partly a cold fit -- the point's value is then neither N2's nor cold's.
    #
    # **`any` READS AS THE PERMISSIVE CHOICE AND IS THE STRICT ONE HERE**, which
    # is the whole reason this comment exists: `all` sounds conservative and
    # keeps exactly the MIXED points, the only ones nothing downstream could
    # identify, because a mixed winner is an ordinary candidate index. The plan
    # was silent on the reduction; the silence is what made it worth writing
    # down rather than the choice.
    no_source = ~np.asarray(starts.warm_valid, dtype=np.bool_).all(axis=1)
    left_the_box = np.asarray(starts.n2_inadmissible, dtype=np.bool_).any(axis=1)
    # Exhaustion takes precedence, so the two reasons are disjoint and
    # `excluded == exhausted_spiral + inadmissible` is an identity rather than
    # an approximation that holds on fixtures where one of them is zero.
    inadmissible = left_the_box & ~no_source
    excluded = no_source | inadmissible
    degenerate = np.asarray(starts.degenerate, dtype=np.bool_).any(axis=1) & ~excluded

    selected = np.asarray(
        arms.results[Arm.N2].ranking.best_index, dtype=np.int64
    ).copy()
    selected[excluded] = SELECTED_UNSET

    counts = N2Counts(
        excluded=int(excluded.sum()),
        exhausted_spiral=int(no_source.sum()),
        inadmissible=int(inadmissible.sum()),
        zero_distance=int(degenerate.sum()),
    )
    return FieldArms(
        selected=selected.astype(np.int16).reshape(n_normal, n_parallel),
        counts=counts,
        arms=arms,
    )


def field_cold_starts(
    y: NDArray[np.float64],
    mask: NDArray[np.bool_],
    t: NDArray[np.float64],
    candidates: Sequence[ProcessSpec],
    *,
    engine: Engine | None = None,
    objective: Objective = DEFAULT_OBJECTIVE,
) -> NDArray[np.float64]:
    """The ladder start for a whole field, through the audit's own path.

    **THE SAME RESOLUTION `run_arms` MAKES, MADE HERE TOO.** A caller building
    the warm array as a displacement from cold must displace from the point the
    audit's cold arm actually starts from, or the distance N2 matches is a
    distance from somewhere else.

    Args:
        y: Observations, shape `(B, N)`.
        mask: Presence mask, shape `(B, N)`.
        t: Shared time axis, shape `(N,)`.
        candidates: The candidate set, in model-axis order.
        engine: Likelihood engine. Defaults to the batched Kalman filter.
        objective: ML or REML.

    Returns:
        `(B, M, p_max)` float64, NaN in each candidate's padding.
    """
    resolved = KalmanEngine() if engine is None else engine
    return cold_starts(
        y, mask, t, list(candidates), engine=resolved, objective=objective
    )


def candidate_extents(candidates: Sequence[ProcessSpec]) -> list[int]:
    """Free-parameter count per candidate, in model-axis order."""
    return [len(free_param_index(spec)) for spec in candidates]


__all__ = [
    "DEFAULT_OBJECTIVE",
    "FieldArms",
    "N2Counts",
    "candidate_extents",
    "field_arms",
    "field_cold_starts",
    "n2_field_map",
    "point_directions",
]
