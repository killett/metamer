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
from pathlib import Path
from typing import Any

import numpy as np
import zarr
from numpy.typing import NDArray

from metamer.batch.ragged import RaggedIndex
from metamer.core.outcomes import Outcome


def _array(root: zarr.Group, group: str, name: str) -> zarr.Array[Any]:
    """Return one array of an opened store, narrowed for the type checker.

    A third spelling of `write._array` and `reuse._array`. **Left duplicated
    deliberately rather than consolidated in a feature commit**: hoisting it
    would edit two modules this task otherwise does not touch, and a refactor
    landing beside a behaviour change is how one of them comes to explain the
    other's failure.

    Args:
        root: An opened store.
        group: Group name.
        name: Array name within it.

    Returns:
        The array.

    Raises:
        TypeError: If either name does not hold what the schema says it does.
    """
    holder = root[group]
    if not isinstance(holder, zarr.Group):  # pragma: no cover - store invariant
        raise TypeError(f"{group} is not a group")
    array = holder[name]
    if not isinstance(array, zarr.Array):  # pragma: no cover - store invariant
        raise TypeError(f"{group}/{name} is not an array")
    return array


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


def coarse_ok(pass1_path: Path | str) -> NDArray[np.bool_]:
    """Read pass 1's per-candidate usability mask over the whole coarse grid.

    **`OK` IS THE RIGHT PREDICATE AND IT WAS CHECKED RATHER THAN ASSUMED.** The
    question a source map asks is *"does this coarse cell hold a warm start a
    fit could legitimately start from?"*, and `fit` refuses one that is
    non-finite or at a diagnostic limit. `optimize_series` returns
    `DIAGNOSTIC_LIMIT` before it can return `OK`, and returns `OK` only with a
    Hessian in hand -- which is the branch `core.fit` writes
    `theta_unconstrained` under. So `outcome == OK` implies a finite
    unconstrained optimum strictly inside both limits, which is exactly the
    contract `_check_warm_starts` enforces on the other side.

    **THIS IS THE ONE ARRAY OF PASS 1 THAT IS READ WHOLE, AND IT IS DELIBERATE
    RATHER THAN OVERLOOKED.** `source_map` takes `coarse_ok` over the FULL
    coarse grid and answers in absolute coarse indices, which is what makes
    §11.3's tile-independence structural instead of tested into existence; a
    halo slice would need translated indices, the construction that module
    exists to avoid. **The cost is a term that grows with the field**: at design
    doc §9.4's 3600 x 7200 grid with `k = 8` the coarse grid is 450 x 900, so at
    two candidates this is 810 kB of uint8 -- against 12.96 MB for the same
    store's `theta_unconstrained` at `p_total = 4`, which `read_warm_starts`
    does NOT read whole, and against 372.9 MB for one fine tile at side 272 and
    N = 630. Recorded in `PROGRESS.md` with those figures.

    Args:
        pass1_path: A complete pass-1 store, past the barrier and the gate.

    Returns:
        `(n_coarse_y, n_coarse_x, M)` bool, the shape and dtype `source_map`
        requires. **Boolean, never the outcome codes**: `source_map` refuses a
        non-boolean array because an outcome array reads every non-`OK` code as
        True and `OK` -- which is 0 -- as False, inverting it exactly.
    """
    root = zarr.open_group(str(pass1_path), mode="r")
    outcome = np.asarray(_array(root, "status", "outcome")[:], dtype=np.uint8)
    return np.asarray(outcome == Outcome.OK.code, dtype=np.bool_)


def read_warm_starts(
    pass1_path: Path | str,
    sources: SourceMap,
    index: RaggedIndex,
    *,
    coarse_shape: tuple[int, int],
) -> NDArray[np.float64]:
    """Read one tile's warm starts out of pass 1, in `fit`'s `(B, M, p_max)` layout.

    **ONE TILE'S SOURCES, NOT THE STORE.** The read is a single rectangle: the
    bounding box of the coarse cells this tile's source map actually names,
    which the spiral bounds at the tile's own coarse footprint plus
    `spiral_bound` coarse steps on each side. At fine tile side 272 with
    `k = 8` and `bound = 4` that is 42 x 42 = 1764 coarse points, **56 kB at
    `p_total = 4`**, and it does not move when the field grows. Loading the
    array whole instead would put a field-sized term under §11.1.1's
    peak-RAM-from-the-budget guarantee, which is the door §11.1's general form
    breaks through.

    **THE RAGGED AXIS IS UNPACKED WITH THE RUN'S OWN INDEX, NOT A SECOND ONE.**
    `/warmstart/theta_unconstrained` is `(y, x, P_total)`: each candidate's free
    parameters concatenated, with no padding, because on the ragged axis a NaN
    means the fit failed and nothing else (§12.3). Re-padding to `(B, M, p_max)`
    is `RaggedIndex.block(m)` per candidate, and the index handed in is the one
    the run tiles against -- **the two stores share a candidate count**, which
    `resume._check_candidates` enforces in both directions from inside the
    cross-store gate.

    Args:
        pass1_path: A complete pass-1 store, past the barrier and the gate.
        sources: This tile's source map, `(B, M)`, in row-major grid order --
            the order `tiling.assemble_tile` returns series in.
        index: The run's `/noise/` ragged index, whose extents are the per
            candidate free-parameter counts.
        coarse_shape: `(n_coarse_y, n_coarse_x)`, needed to turn a flat coarse
            index back into a row and a column. **Taken from `coarse_ok`'s own
            shape by the caller** rather than recomputed from the grid and the
            stride: two derivations of the coarse extent is how one of them
            comes to disagree with the store that has it.

    Returns:
        `(B, M, p_max)` float64. **NaN wherever `sources.valid` is false**, and
        NaN in the padding of any candidate narrower than the widest -- the
        layout `fit` reads to `:p` per candidate and never inspects beyond.
    """
    n_cx = int(coarse_shape[1])
    batch, models = sources.index.shape
    p_max = max(index.extents)
    warm = np.full((batch, models, p_max), np.nan, dtype=np.float64)
    if not bool(sources.valid.any()):
        return warm

    flat = sources.index[sources.valid]
    rows, columns = np.divmod(flat, n_cx)
    # THE BOUNDING BOX OF WHAT THIS TILE ASKED FOR, which is what makes the read
    # a function of the tile rather than of the field. It is taken from the
    # indices themselves rather than from the tile plus the bound, so a change
    # to the spiral's reach cannot leave this reading the wrong rectangle.
    row_start, row_stop = int(rows.min()), int(rows.max()) + 1
    column_start, column_stop = int(columns.min()), int(columns.max()) + 1

    root = zarr.open_group(str(pass1_path), mode="r")
    stored = _array(root, "warmstart", "theta_unconstrained")
    block = np.asarray(
        stored[row_start:row_stop, column_start:column_stop, :], dtype=np.float64
    )

    for model, extent in enumerate(index.extents):
        selected = np.asarray(sources.valid[:, model], dtype=np.bool_)
        if not bool(selected.any()):
            continue
        chosen = sources.index[selected, model]
        i = chosen // n_cx - row_start
        j = chosen % n_cx - column_start
        warm[selected, model, :extent] = block[i, j][:, index.block(model)]
    return warm


__all__ = ["SourceMap", "coarse_ok", "read_warm_starts", "source_map"]
