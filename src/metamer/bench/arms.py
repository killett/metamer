"""The `self` ceiling, and arm cost read as a ratio over shared cells.

## Why this module exists at all

**E6's UPPER REFUTATION CLAUSE NAMES AN ARM THE SHIPPED AUDIT DOES NOT HAVE.**
*"Saving at any rung >= the `self` ceiling -> the warm arm is reading its own
answer back; the source map is handing points their own optimum."* `Arm` is
`WARM / COLD / N1 / N2`, and the `94.53%` the figures table offers is **2c's
fixture, at 40.79 cold iterations per point**, against 2d's field at **24.4**.
**Bounding a saving here with that number is a comparison across fixtures** --
(j5) -- at the one clause whose job is catching a defect that would otherwise
be read as a spectacular result.

**AND IT IS THE CHEAPEST ARM IN THE DESIGN**, which is why the answer is to
measure it rather than to argue about transfer: its input is the cold arm's own
converged optimum, and Task 0 measured `self` collapsing to **4-6% of cold**.

**IT IS ALSO THE VOID CONTROL.** *"N1 costs what cold costs"* is byte-identical
in the output to *"the iteration counter is not moving"* and to *"every arm
silently ran cold"*. **If `self` does not collapse, the instrument has not been
shown able to tell two arms apart by cost, and no cost reading in the run may
be quoted.** That sentence is Task 0's and it is enforced by the caller, not
here -- this module measures; refusing is the measurement's own job.

## Why the ratio is over cells OK in BOTH arms

**TWO TOTALS OVER TWO DIFFERENT SETS OF CELLS ARE TOTALS OF DIFFERENT THINGS.**
N1's reading is whether its ratio against cold sits inside `[1.0000, 1.0026]`
-- a band far narrower than one cell of a 384-point field -- so a single cell
that one arm converged on and the other did not moves the reading across the
band **without anything having happened to the perturbation.** The intersection
is the only honest denominator, and the cells each arm reached alone are
**reported**, because a shrinking intersection still produces a
plausible-looking number.

## This module adds no third cold arm

`cold_arm` is `fit(x0=None)` with the benchmark's own objective and engine --
**the same call `run_arms` makes** -- so the self arm perturbs around the point
the audit's cold arm actually starts from. A second cold arm with a different
objective, engine or cap would make the ceiling a ratio against something else,
and both numbers would look reasonable.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from metamer.bench.n2map import DEFAULT_OBJECTIVE
from metamer.core.capability import Objective
from metamer.core.criteria import Criterion
from metamer.core.engines.kalman import KalmanEngine
from metamer.core.engines.protocol import Engine
from metamer.core.fit import FitResult, fit
from metamer.core.optimize import DEFAULT_MAX_ITER
from metamer.core.outcomes import Outcome
from metamer.core.signal import SignalSpec
from metamer.core.terms import ProcessSpec

#: The arm's name, so a reading can say which arm it came from without a
#: caller spelling it.
SELF_ARM: str = "self"


@dataclass(frozen=True)
class ArmCost:
    """One arm's per-cell cost, in the unit the budget is built in.

    **ITERATIONS AND NOT SECONDS.** Iterations are deterministic -- the same
    fixture reproduced every digit a day later while its seconds moved 15% --
    so a ratio of iteration counts is a reading and a ratio of seconds is a
    reading about the host.

    Attributes:
        n_iter: Iterations per `(series, candidate)` cell.
        ok: Whether that cell reached `OK`. **A cell that did not converge has
            an iteration count that measures the cap rather than the work.**
    """

    n_iter: NDArray[np.int64]
    ok: NDArray[np.bool_]


def arm_cost(result: FitResult) -> ArmCost:
    """The cost of one arm, read off its `FitResult`.

    **THE ONLY PLACE A `FitResult` IS REDUCED TO A COST**, so the `OK` rule has
    one spelling. A second reduction would let two readings of one run disagree
    about which cells they described.
    """
    return ArmCost(
        n_iter=np.asarray(result.n_iter, dtype=np.int64),
        ok=np.asarray(result.outcome == Outcome.OK.code, dtype=np.bool_),
    )


@dataclass(frozen=True)
class IterationRatio:
    """One arm's cost against another's, over the cells both converged on.

    Attributes:
        ratio: `numerator_total / denominator_total`, or **None when there is
            no shared cell** -- which is a refusal and not a large number.
        numerator_total: Iterations summed over the shared cells.
        denominator_total: The same, for the other arm.
        cells_compared: How many cells that was.
        numerator_only: Cells the numerator reached `OK` on and the denominator
            did not. **Reported, never folded in.**
        denominator_only: The reverse.
        refused: Why there is no ratio, or None.
    """

    ratio: float | None
    numerator_total: int
    denominator_total: int
    cells_compared: int
    numerator_only: int
    denominator_only: int
    refused: str | None


def iteration_ratio(numerator: ArmCost, denominator: ArmCost) -> IterationRatio:
    """Compare two arms over the cells both of them converged on.

    Args:
        numerator: The arm under test -- N1, or `self`.
        denominator: The reference arm, which is cold.

    Returns:
        The ratio, its two totals, and the cells each arm reached alone.

    Raises:
        ValueError: If the two arms are not the same shape. **A cell-by-cell
            pairing needs cells that correspond**, and NumPy would broadcast
            some mismatches silently and return a number.
    """
    if numerator.n_iter.shape != denominator.n_iter.shape:
        raise ValueError(
            "two arms compared cell by cell must be the same shape, got "
            f"{numerator.n_iter.shape} and {denominator.n_iter.shape}; a "
            "pairing across shapes would broadcast and return a number"
        )

    shared = numerator.ok & denominator.ok
    numerator_total = int(numerator.n_iter[shared].sum())
    denominator_total = int(denominator.n_iter[shared].sum())
    cells = int(shared.sum())
    refused: str | None = None
    ratio: float | None = None
    if cells == 0:
        refused = (
            "no cell reached OK in both arms, so there is nothing to compare; "
            "a ratio here would be a division by zero reported as a cost"
        )
    elif denominator_total == 0:
        refused = (
            "the reference arm took no iterations on the shared cells, so the "
            "ratio is undefined rather than infinite"
        )
    else:
        ratio = numerator_total / denominator_total

    return IterationRatio(
        ratio=ratio,
        numerator_total=numerator_total,
        denominator_total=denominator_total,
        cells_compared=cells,
        numerator_only=int((numerator.ok & ~denominator.ok).sum()),
        denominator_only=int((denominator.ok & ~numerator.ok).sum()),
        refused=refused,
    )


@dataclass(frozen=True)
class ArmAgreement:
    """Whether two paths to one quantity produced the same numbers.

    **BOTH PATHS PRODUCE PLAUSIBLE NUMBERS, WHICH IS WHY THIS IS A READING AND
    NOT AN ASSERTION.** A cold arm computed by `run_arms` and the cold pass
    written by `run` are the same 384 fits by two code paths -- one tiled,
    assembled and written, the other a bare `fit` -- and iterations are
    deterministic, so they either agree to the digit or one of them is doing
    different work. The same holds for the rebuilt warm array against pass 2's
    own store, where a disagreement would not look like an error: **it would
    look like a smear**, because N1 and N2 are displacements from that array.

    Attributes:
        identical: Every shared cell agreed, and neither side had a cell the
            other lacked.
        cells_compared: Cells `OK` in both.
        cells_differing: Of those, how many disagreed.
        left_only: Cells `OK` on the left only.
        right_only: The reverse.
    """

    identical: bool
    cells_compared: int
    cells_differing: int
    left_only: int
    right_only: int


def same_iterations(left: ArmCost, right: ArmCost) -> ArmAgreement:
    """Compare two arms cell by cell over the cells both converged on.

    Raises:
        ValueError: If the two are not the same shape.
    """
    if left.n_iter.shape != right.n_iter.shape:
        raise ValueError(
            "two arms compared cell by cell must be the same shape, got "
            f"{left.n_iter.shape} and {right.n_iter.shape}"
        )
    shared = left.ok & right.ok
    differing = int((left.n_iter[shared] != right.n_iter[shared]).sum())
    left_only = int((left.ok & ~right.ok).sum())
    right_only = int((right.ok & ~left.ok).sum())
    return ArmAgreement(
        identical=differing == 0 and left_only == 0 and right_only == 0,
        cells_compared=int(shared.sum()),
        cells_differing=differing,
        left_only=left_only,
        right_only=right_only,
    )


def store_cost(store_path: object, n_models: int) -> ArmCost:
    """One written store's per-cell cost, in an arm's own `(B, M)` layout.

    **ROW-MAJOR, WHICH IS THE ORDER `assemble_tile` RETURNS SERIES IN** and the
    order `SourceMap`'s rows are written against -- so a store's cells line up
    with an arm's without a reindex. A permuted batch would compare the right
    number of cells in the wrong places.
    """
    import zarr

    from metamer.batch.store import ITERATIONS_UNSET

    root = zarr.open_group(str(store_path), mode="r")
    written = root["primitives/iterations"]
    outcome = root["status/outcome"]
    if not isinstance(written, zarr.Array):  # pragma: no cover - store shape
        raise TypeError("primitives/iterations is not an array")
    if not isinstance(outcome, zarr.Array):  # pragma: no cover - store shape
        raise TypeError("status/outcome is not an array")
    iterations = np.asarray(written[:]).reshape(-1, n_models)
    codes = np.asarray(outcome[:]).reshape(-1, n_models)
    return ArmCost(
        n_iter=np.asarray(iterations, dtype=np.int64),
        ok=np.asarray(
            (codes == Outcome.OK.code) & (iterations != ITERATIONS_UNSET),
            dtype=np.bool_,
        ),
    )


def self_start_validity(outcome: NDArray[np.uint8]) -> NDArray[np.bool_]:
    """Which cells have a `self` start: exactly those cold converged on.

    **`theta_unconstrained` IS ALL-NaN WHERE `outcome` IS NOT `OK`**, so this
    mask is the outcome array and nothing else. Marking every cell valid would
    hand `fit` a NaN start, which the warm-start contract refuses -- *"a source
    map that marks one valid is refused rather than started from"*.
    """
    return np.asarray(outcome == Outcome.OK.code, dtype=np.bool_)


@dataclass(frozen=True)
class SelfArm:
    """The ceiling arm's map and its cost.

    Attributes:
        selected: The selected candidate per point, as a grid, in
            `/selection/selected`'s own `int16` vocabulary -- so
            `smear.agreement_map` consumes it with no adapter, exactly as the
            N2 map does.
        cost: Its per-cell iterations and `OK` mask.
        started_from: How many cells had a start at all. **A `self` arm over
            few cells is a ceiling over few cells**, and the count is what says
            so.
    """

    selected: NDArray[np.int16]
    cost: ArmCost
    started_from: int


def cold_arm(
    y: NDArray[np.float64],
    t: NDArray[np.float64],
    signal: SignalSpec,
    candidates: Sequence[ProcessSpec],
    criterion: Criterion,
    *,
    mask: NDArray[np.bool_],
    objective: Objective = DEFAULT_OBJECTIVE,
    engine: Engine | None = None,
    max_iter: int = DEFAULT_MAX_ITER,
) -> FitResult:
    """The moment-ladder fit, through the call the audit's own cold arm makes."""
    return fit(
        y,
        t,
        signal,
        list(candidates),
        criterion,
        mask=mask,
        objective=objective,
        engine=KalmanEngine() if engine is None else engine,
        x0=None,
        x0_valid=None,
        max_iter=max_iter,
    )


def self_arm(
    y: NDArray[np.float64],
    t: NDArray[np.float64],
    signal: SignalSpec,
    candidates: Sequence[ProcessSpec],
    criterion: Criterion,
    *,
    mask: NDArray[np.bool_],
    cold: FitResult,
    grid_shape: tuple[int, int],
    objective: Objective = DEFAULT_OBJECTIVE,
    engine: Engine | None = None,
    max_iter: int = DEFAULT_MAX_ITER,
) -> SelfArm:
    """Refit every cell from its **own** converged optimum.

    Args:
        y: Observations, shape `(B, N)`, in row-major grid order.
        t: The shared time axis.
        signal: The signal specification.
        candidates: The candidate set, in model-axis order.
        criterion: The information criterion.
        mask: Presence mask.
        cold: The cold arm, whose `theta_unconstrained` **is** this arm's
            start. Passed in rather than refitted, because a second cold arm
            would make the ceiling a ratio against something else.
        grid_shape: `(n_normal, n_parallel)`, for the returned map.
        objective: ML or REML.
        engine: Likelihood engine.
        max_iter: Iteration cap per series.

    Returns:
        The arm.
    """
    valid = self_start_validity(np.asarray(cold.outcome, dtype=np.uint8))
    result = fit(
        y,
        t,
        signal,
        list(candidates),
        criterion,
        mask=mask,
        objective=objective,
        engine=KalmanEngine() if engine is None else engine,
        x0=np.asarray(cold.theta_unconstrained, dtype=np.float64),
        x0_valid=valid,
        max_iter=max_iter,
    )
    n_normal, n_parallel = grid_shape
    selected = np.asarray(result.ranking.best_index, dtype=np.int64)
    return SelfArm(
        selected=selected.astype(np.int16).reshape(n_normal, n_parallel),
        cost=arm_cost(result),
        started_from=int(valid.sum()),
    )


__all__ = [
    "SELF_ARM",
    "ArmAgreement",
    "ArmCost",
    "IterationRatio",
    "SelfArm",
    "arm_cost",
    "cold_arm",
    "iteration_ratio",
    "same_iterations",
    "self_arm",
    "self_start_validity",
    "store_cost",
]
