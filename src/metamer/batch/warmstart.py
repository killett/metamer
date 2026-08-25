"""§11.3's source map: which coarse fit each fine point warm-starts from.

WHAT THIS MODULE IS FOR (design doc §11.3, decisions D3 and D12).
------------------------------------------------------------------
Pass 2 fits every point of the full grid, each warm-started from a coarse point
pass 1 already fitted. **This module decides which one, and nothing else does.**
The policy -- the spiral, its tie-break, its bound and what exhaustion means --
lives here, in the batch layer, where the coarse grid exists. `core.fit` only
**honours** the validity array this produces.

THE RULE, AND THE TWO PARTS OF IT NO OTHER DOCUMENT STATES.
-----------------------------------------------------------
Nearest valid coarse point, searched outward, ties broken **lowest `y` then
lowest `x`**. Two choices are load-bearing and were recoverable only from
`docs/superpowers/notes/warmstart-spike-harness.py`, the instrument that
measured D1's verdict and D6's stride curve:

- **THE DISTANCE IS CHEBYSHEV**, `max(|dy|, |dx|)` in FINE index units. The plan
  says "nearest ... in index space", which reads equally as Euclidean or
  Manhattan, and the three disagree about which source a point gets. Chebyshev
  calls a diagonal neighbour and an axis neighbour **equidistant** where
  Euclidean does not, so **the tie-break fires in cases Euclidean never
  reaches** -- and the tie-break is the whole mechanism by which `θ̂` stops
  depending on traversal order.
- **THE RADIUS IS INCLUSIVE.** A bound of `r` searches distance `r`.

**Departing from either makes D1's and D6's measurements describe a mechanism
that was never built** -- (j2).

THE BOUND IS IN COARSE INDEX STEPS, WHICH IS NOT WHAT THE INSTRUMENT USED.
---------------------------------------------------------------------------
`config.warm_start.spiral_bound` is documented as *"maximum search radius, in
coarse index steps"*, default 4. The harness's `max_radius` was in **fine**
units and was passed the whole field, i.e. **unbounded**. The unit is fit
identity -- `warm_start_spiral_bound` is in `FIT_RELEVANT_FIELDS` -- so two runs
agreeing on the integer 4 and disagreeing on what it counts produce different
`θ̂` under one `fit_hash`. **The config's reading is the specification**, so the
conversion is `max_fine_radius = spiral_bound * stride`.

**CONSEQUENCE, STATED SO IT IS NOT DISCOVERED LATER: D1 AND D6 WERE MEASURED
WITH NO EFFECTIVE BOUND**, so they describe a run in which the bound never bit.
At `k = 8` and `bound = 4` the search reaches 32 fine cells, so exhaustion needs
a 9x9 coarse neighbourhood -- 81 coarse points -- **entirely failed for that
candidate**. Rare, and exactly the shape of a large land or ice region.

A COARSE POINT'S SOURCE IS ITSELF, AND THAT IS GEOMETRY RATHER THAN A BRANCH.
-----------------------------------------------------------------------------
At radius 0 the only coarse point at distance 0 from a coarse point is itself,
so D12 needs no special case and there is none here. **A spiral that started at
radius 1 would make every coarse point neighbour-sourced and invert the lattice
artifact**, which no aggregate saving figure would reveal.

WHY THIS IS NOT THE HARNESS'S IMPLEMENTATION.
----------------------------------------------
`spiral_source` rebuilds the candidate ring by scanning **every** coarse point
at every radius. At `n_side = 96` that is free; at `10^7` fine points with
`k = 8` there are 1.56e5 coarse points and the same code is ~1e12 operations.
**It was a correct instrument and it is not an implementation.**

The lattice makes it cheap: a fine point's offsets to the coarse grid depend
only on `(y % k, x % k)`, so there are just `k²` distinct search orders. And
**within a ring, ordering by ABSOLUTE `(y, x)` is the same as ordering by
OFFSET**, because every candidate shares the target's base -- which is what lets
one precomputed order serve every point in a residue class. The orders are
identical to the harness's by construction, and
`tests/test_warmstart.py` compares the two implementations point by point.

**MEASURED RATHER THAN ASSERTED, 2026-08-24**, because "this is cheap enough" in
a docstring is a claim like any other: one 338x338 tile at `k = 8`,
`bound = 4`, `M = 2`, 5% of coarse points failed -- **0.163 s, i.e. 1.43 us per
point**, extrapolating to **~14 s over 10^7 points**. Against a per-point fit
this is not a term worth optimizing further. **Indicative only**: one run, one
fixture, no host quiet check, and no claim about how it scales with `bound`,
whose search order grows as `(2*bound + 1)²`.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True)
class SourceMap:
    """Which coarse fit each `(fine point, candidate)` warm-starts from.

    Every array is `(B, M)` with `B` the mapped points in **row-major grid
    order** -- the order `tiling.assemble_tile` returns series in, so a row of
    one lines up with a row of the other without a reindex.

    Attributes:
        index: Flat **row-major index into the COARSE grid**, `-1` where the
            spiral was exhausted. **The coarse grid, not the fine one**: this is
            what indexes pass 1's store, which is the array a warm start is read
            out of, and a fine-grid index would need dividing by the stride at
            every use. It is also what makes D12's lattice testable by equality
            -- a self-sourced point records `(y // k) * n_coarse_x + (x // k)`
            -- rather than discoverable as a spatial signal.
        valid: `index >= 0`. **Derived, never accumulated in parallel.** Task 0
            made `fit` refuse a non-boolean `x0_valid` because `bool(-1)` is
            True, which catches the two arrays being SWAPPED; nothing catches
            them DISAGREEING, and two arrays maintained by two loops is how that
            happens. One expression, so it cannot.
        radius: Chebyshev distance in **fine** index units to the chosen source,
            `-1` where exhausted. `0` exactly at the coarse points.
    """

    index: NDArray[np.int64]
    valid: NDArray[np.bool_]
    radius: NDArray[np.int64]


@cache
def _search_order(
    stride: int, max_fine_radius: int, residue_y: int, residue_x: int
) -> tuple[tuple[int, int, int], ...]:
    """Coarse-index offsets for one residue class, in search order.

    A fine point at `(y, x)` sits `(residue_y, residue_x) = (y % k, x % k)` past
    the coarse point at or above-left of it. Its candidate sources are the
    coarse points at offsets `(di, dj)` from that one, and their Chebyshev
    distances depend on the residues alone -- so every point in a residue class
    shares one search order.

    **Ordered by `(distance, di, dj)`, which is the harness's
    `(radius, y, x)`.** Within a ring, ordering by absolute `y` is ordering by
    `di`, because every candidate shares the target's base.

    Args:
        stride: The coarse stride `k`.
        max_fine_radius: Inclusive search bound, in FINE index units.
        residue_y: `y % stride`.
        residue_x: `x % stride`.

    Returns:
        `(di, dj, distance)` triples, nearest first.
    """
    reach = max_fine_radius // stride + 1
    offsets = []
    for di in range(-reach, reach + 1):
        for dj in range(-reach, reach + 1):
            distance = max(abs(di * stride - residue_y), abs(dj * stride - residue_x))
            if distance <= max_fine_radius:
                offsets.append((di, dj, distance))
    offsets.sort(key=lambda item: (item[2], item[0], item[1]))
    return tuple(offsets)


def source_map(
    *,
    shape: tuple[int, int],
    stride: int,
    coarse_ok: NDArray[np.bool_],
    spiral_bound: int,
    region: tuple[int, int, int, int] | None = None,
) -> SourceMap:
    """Build §11.3's source map for a region of the fine grid.

    Args:
        shape: The **FULL** fine grid, `(n_y, n_x)`. Always the full grid, never
            a tile's: the coarse geometry is derived from it, so the answer for
            a point cannot depend on which tile it was asked about. **That is
            what makes §11.3's guarantee structural rather than tested into
            existence** -- building the map from tile-local indices is named in
            the plan as the single most likely way to lose it.
        stride: The coarse stride `k`, matching pass 1's decimation.
        coarse_ok: `(n_coarse_y, n_coarse_x, M)` bool -- whether each coarse
            point's fit is `OK` **for that candidate**. Per candidate and never
            per point: the warm-start key is `(fit_hash, candidate spec_hash)`,
            so a coarse point can be usable for one candidate and failed for
            another, and collapsing the axis discards usable sources.
        spiral_bound: Maximum search radius **in coarse index steps**, inclusive.
            Converted to `spiral_bound * stride` fine cells -- see the module
            docstring for why the unit is fit identity and why the config's
            reading is the one that governs.
        region: `(y_start, y_stop, x_start, x_stop)` half-open, in FULL-grid
            coordinates. Defaults to the whole grid. It chooses **which points
            are answered** and never **what the answer is**.

    Returns:
        A `SourceMap` whose arrays are `(B, M)` with
        `B = (y_stop - y_start) * (x_stop - x_start)`, row-major.

    Raises:
        ValueError: If the stride or bound is below 1, if `coarse_ok` does not
            match the coarse grid `shape` and `stride` imply, or if `region`
            falls outside `shape`.
    """
    n_y, n_x = int(shape[0]), int(shape[1])
    if stride < 1:
        raise ValueError(f"the coarse stride must be at least 1, got {stride}")
    if spiral_bound < 1:
        raise ValueError(f"the spiral bound must be at least 1, got {spiral_bound}")

    ok = np.asarray(coarse_ok)
    if ok.dtype != np.bool_:
        raise ValueError(
            f"coarse_ok must be a boolean array, got dtype {ok.dtype}. It is not "
            f"cast: an outcome-code array would read every non-OK code as True "
            f"and OK -- which is 0 -- as False, inverting it exactly."
        )
    # `len(range(0, n, k))` rather than `ceil`: this is the count `isel(::k)`
    # produces, which is what pass 1's store actually has, and the two must not
    # be derived separately.
    n_cy, n_cx = len(range(0, n_y, stride)), len(range(0, n_x, stride))
    if ok.ndim != 3 or ok.shape[:2] != (n_cy, n_cx):
        raise ValueError(
            f"coarse_ok has shape {ok.shape}; a {n_y}x{n_x} grid at stride "
            f"{stride} gives a {n_cy}x{n_cx} coarse grid, so the expected shape "
            f"is ({n_cy}, {n_cx}, M)"
        )
    n_models = int(ok.shape[2])

    y_start, y_stop, x_start, x_stop = (
        (0, n_y, 0, n_x) if region is None else tuple(int(v) for v in region)
    )
    if not (0 <= y_start <= y_stop <= n_y and 0 <= x_start <= x_stop <= n_x):
        raise ValueError(
            f"region {(y_start, y_stop, x_start, x_stop)} is not inside a "
            f"{n_y}x{n_x} grid"
        )

    height, width = y_stop - y_start, x_stop - x_start
    index = np.full((height * width, n_models), -1, dtype=np.int64)
    radius = np.full((height * width, n_models), -1, dtype=np.int64)
    max_fine_radius = int(spiral_bound) * int(stride)

    ys = np.arange(y_start, y_stop, dtype=np.int64)
    xs = np.arange(x_start, x_stop, dtype=np.int64)
    # The coarse cell at or above-left of each fine point, and the offset past
    # it. Floor division, so a fine point BELOW the last coarse row still has a
    # base -- the search then reaches it at a negative `di`.
    base_i, residue_y = np.divmod(ys, stride)
    base_j, residue_x = np.divmod(xs, stride)

    for row in range(height):
        ry = int(residue_y[row])
        bi = int(base_i[row])
        for column in range(width):
            rx = int(residue_x[column])
            bj = int(base_j[column])
            point = row * width + column
            for model in range(n_models):
                for di, dj, distance in _search_order(stride, max_fine_radius, ry, rx):
                    i, j = bi + di, bj + dj
                    if 0 <= i < n_cy and 0 <= j < n_cx and bool(ok[i, j, model]):
                        index[point, model] = i * n_cx + j
                        radius[point, model] = distance
                        break

    return SourceMap(index=index, valid=index >= 0, radius=radius)


__all__ = ["SourceMap", "source_map"]
