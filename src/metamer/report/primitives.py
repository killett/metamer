"""Sub-phase 2f Task 4: the single-store sections, and the run's own record.

**A FILL VALUE COUNTED AS A DATUM IS THE DEFECT SECTION 12.5's FILL TABLE
EXISTS TO PREVENT.** `/selection/n_valid` uses `-1` for "nothing wrote here"
and `/primitives/iterations` uses `65535` for "no fit ran", and both are
in-range integers that a histogram will happily bin. So they are excluded from
every distribution **and counted separately** -- excluded alone would describe
a smaller grid than the one that ran, which is the same half-a-rule the branch
table already refuses for `NOT_ATTEMPTED`.

**THE SENTINELS ARE IMPORTED, NEVER RE-SPELLED.** `N_VALID_UNSET` and
`ITERATIONS_UNSET` have one definition in `metamer.batch.store`, and a second
copy here would be the two-definitions defect this sub-phase has now paid for
twice under other names. `batch.store` costs the report nothing it has not
already paid: it is on the reader's path and carries no forbidden module --
`pydantic` arrives with `batch.run`, not with `store`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

from metamer.batch.store import ITERATIONS_UNSET, N_VALID_UNSET
from metamer.report.reader import StoreView

#: Printed where the run that wrote a store recorded no resolved-candidate
#: block. **Absence is the answer and nothing is back-filled** (D12): a store
#: written before 2f Task 4 cannot be made to say what its run resolved, and a
#: report that guessed would make it claim a resolution nobody recorded.
NOT_RECORDED = "not recorded by the run that wrote this store"


@dataclass(frozen=True)
class Distribution:
    """One integer distribution, with its fill values counted rather than binned.

    Attributes:
        counts: Value to number of cells, over the real population only.
        unset: Cells holding the fill value -- **counted, never binned**.
        population: Cells carrying a real value; the denominator of any
            fraction taken over `counts`.
    """

    counts: dict[int, int]
    unset: int
    population: int


@dataclass(frozen=True)
class PrimitiveSections:
    """Task 4's record: the two distributions and the run's own provenance.

    Attributes:
        n_valid: `/selection/n_valid`'s distribution (section 10.2).
        iterations: `/primitives/iterations`' distribution, over every
            (point, candidate) cell.
        resolved_candidates: The run's resolved-candidate block, or None where
            the run did not record one.
        resolved_at: The block's own label -- when it was resolved and against
            which registry -- or `NOT_RECORDED`.
        hashes: `fit_hash`, `compat_hash` and `run_hash` as the store carries
            them.
        registry_version: The registry the run stamped.
        tile_side_basis: Whether the tile side was measured or defaulted
            (section 13.4's vocabulary, which the store already speaks).
        calibration: The calibration block, or None where there is none.
    """

    n_valid: Distribution
    iterations: Distribution
    resolved_candidates: list[dict[str, Any]] | None
    resolved_at: str
    hashes: dict[str, str]
    registry_version: str
    tile_side_basis: str
    calibration: dict[str, Any] | None


def _distribution(values: NDArray[Any], unset: int) -> Distribution:
    """Bin an integer array, holding its fill value out of the bins.

    Args:
        values: The array, any shape.
        unset: The fill value meaning "nothing wrote here".

    Returns:
        The distribution, with the fill count beside it rather than in it.
    """
    flat = np.asarray(values).ravel()
    is_unset = flat == unset
    real = flat[~is_unset]
    found, counts = np.unique(real, return_counts=True)
    return Distribution(
        counts={int(v): int(c) for v, c in zip(found, counts, strict=True)},
        unset=int(is_unset.sum()),
        population=int(real.size),
    )


def compute(view: StoreView) -> PrimitiveSections:
    """Task 4's sections, from the store alone.

    Args:
        view: A store, read-only.

    Returns:
        The two distributions and the run's recorded provenance, with absence
        reported rather than guessed.
    """
    block = view.attrs.get("resolved_candidates")
    rows: list[dict[str, Any]] | None = None
    resolved_at = NOT_RECORDED
    if isinstance(block, dict):
        candidates = block.get("candidates")
        if isinstance(candidates, list):
            rows = candidates
        resolved_at = str(block.get("resolved_at", NOT_RECORDED))
    calibration = view.attrs.get("calibration")
    return PrimitiveSections(
        n_valid=_distribution(view.n_valid, N_VALID_UNSET),
        iterations=_distribution(view.iterations, ITERATIONS_UNSET),
        resolved_candidates=rows,
        resolved_at=resolved_at,
        hashes={
            name: str(view.attrs.get(name, NOT_RECORDED))
            for name in ("fit_hash", "compat_hash", "run_hash")
        },
        registry_version=str(view.attrs.get("registry_version", NOT_RECORDED)),
        tile_side_basis=str(view.attrs.get("tile_side_basis", NOT_RECORDED)),
        calibration=calibration if isinstance(calibration, dict) else None,
    )
