"""Tiling: the grid, the assembly, and read amplification.

**THE TILE IS THE BATCH.** No inner loop over pixels — the batched engine
advances all `tile_side**2` series together, and `B = 1` is a shape rather than a
code path.

**PARALLELISM IS WITHIN A TILE, OVER SERIES, NEVER ACROSS TILES.** Both engines
already work this way and it is written here because **across-tile parallelism is
the obvious later optimization and it multiplies peak RAM by thread count**,
silently breaking the 16 GB constraint. Within-tile parallelism is what makes
peak RAM independent of core count, and hence what lets the same job run on 4
cores and on 64. The general form, stronger than the ban and design doc §11.1.1's
own words:

> **Peak RAM must be derivable from the memory budget alone.** Any concurrency
> whose degree is set by core count, thread count or worker count reintroduces
> the dependency, **regardless of which subsystem hosts it.**

**PREFETCHING TILE `N+1` DURING TILE `N`'s FIT IS DEFERRED, AND ITS COST IS THAT
IT DOUBLES THE TILE TERM IN THE MEMORY FORMULA.** It arrives with a formula
update or it does not arrive. It is not merely documented: `ThreadBudget.phase`
raises when assemble and fit overlap, so the first attempt fails a test rather
than silently doubling peak RAM.

**NO DASK.** A tile is `isel(...).load()` against zarr and zarr does the chunk
reads. `.load()`'s peak is analytic where a graph's is emergent, which is what
lets 2b's calibration tile turn the memory formula from a model into a
measurement.

**A TILE SIDE IS NOT A NUMBER WITHOUT ITS PRECONDITIONS**, and the ones it needs
changed on 2026-08-14. At §9.4's worked example (d=3, k_β=4, p_max=4, N=630,
M=12) under a **10⁹** budget the side is **347** shared / **187** per-point,
recomputed by hand from the corrected formula. The superseded pair is
~~338 / 186~~ and the superseded backend-specific pair is ~~361 / 189~~.

**AND THE SIDE NO LONGER CARRIES A BACKEND**, which is the visible half of the
correction: the two engines' published pairs differed only because the formula
charged one live solver working set to every series. `fit` runs one series at a
time, so the per-series cost is the data tile plus the output slots — neither of
which knows which engine is running — and the placement moves a **constant**.
~~`NUMPY_BATCHED` gives 338 / 186 and `COMPILED` gives 361 / 189~~, struck
2026-08-14.

**THE BUDGET'S UNIT IS AN OPEN DEFECT.** Every published side here is computed
at `10**9`, while `run.py` converts the user's `memory_budget_gb` with
`1024**3` — 7.4% more bytes for the same word. Tasks 2 and 3 own the budget and
own resolving it; do not restate a side without saying which unit produced it.

**FORWARD NOTE — PASS 1's COARSE STRIDE LANDS HERE IN 2c AND HAS FIVE DOWNSTREAM
CONSUMERS.** 2a defines no stride. Nowhere else records the list, so a later
change to the stride or its membership has one place to look:

    1  the coarse warm-start source                              §11.1
    2  the calibration-tile RSS measurement                      §11.4
    3  the early-abort evaluation, stratified by construction    §14.1
    4  the COLD reference for the hysteresis audit               §11.2
    5  the default `/detail/` subsample, wanting cold-fit points §12.2
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from metamer.batch.input import InputContractError, InputHandle
from metamer.core.memory import resident_bytes_per_series, tile_side


@dataclass(frozen=True)
class Tile:
    """A contiguous spatial block of whole series, half-open in both axes.

    Attributes:
        y_start: First row, inclusive.
        y_stop: Last row, exclusive.
        x_start: First column, inclusive.
        x_stop: Last column, exclusive.
    """

    y_start: int
    y_stop: int
    x_start: int
    x_stop: int

    @property
    def n_series(self) -> int:
        """Number of series in this tile.

        Returns:
            The batch size the engine will see.
        """
        return (self.y_stop - self.y_start) * (self.x_stop - self.x_start)


def tile_grid(n_y: int, n_x: int, side: int) -> Iterator[Tile]:
    """Yield tiles covering the grid exactly once, ragged edges included.

    **COVERAGE IS THE ONE PLACE AN OFF-BY-ONE IS SILENT.** A miss leaves a seam
    of unwritten points in a store whose completion bitmap is per tile and
    therefore cannot see it; an overlap writes some points twice. Neither
    raises, and both produce a store that looks complete.

    Args:
        n_y: Grid rows.
        n_x: Grid columns.
        side: Tile side, from `tile_side_for`.

    Yields:
        One `Tile` per block, row-major.

    Raises:
        ValueError: If `side` is not positive, or the grid is empty. A side of 0
            is a plausible-looking number that holds no data — the same refusal
            `memory.tile_side` makes, for the same reason.
    """
    if side <= 0:
        raise ValueError(f"tile side must be positive, got {side}")
    if n_y <= 0 or n_x <= 0:
        raise ValueError(f"grid must be non-empty, got {n_y} x {n_x}")
    for y_start in range(0, n_y, side):
        for x_start in range(0, n_x, side):
            yield Tile(
                y_start=y_start,
                y_stop=min(y_start + side, n_y),
                x_start=x_start,
                x_stop=min(x_start + side, n_x),
            )


def tile_side_for(
    *,
    budget_bytes: int,
    k_beta: int,
    p_max: int,
    n_time: int,
    n_models: int,
    per_point_design: bool = False,
) -> int:
    """Return the square tile side a byte budget allows.

    `sqrt(budget_bytes / resident_bytes_per_series)`, floored.

    **NOT `sqrt(block_bytes / (n_time * itemsize))`**, which is the prompt's
    formula: it counts only the float64 data and overestimates, giving 445 where
    the full accounting gives 347. Design doc §11.1 carried it until 2026-08-12
    while §9.4 rejected it, and §11.1 is the section a tiling implementer opens
    first.

    **NO PLACEMENT AND NO `d`, AS OF 2026-08-14.** The per-series cost is the
    data tile plus the output slots and nothing else; the solver state is one
    live working set whatever B is, so it is a constant and `d` reaches the
    arithmetic only through it. **The constant is not subtracted here** — that
    is F1, and Task 2 owns it, together with the process floor and the headroom.
    Until then this is an upper bound on the side rather than a budget-safe one,
    and it will grow a `floor`, a `placement` and a `d` argument when it becomes
    one.

    Args:
        budget_bytes: The memory budget for one tile.
        k_beta: Number of design columns.
        p_max: Widest candidate's free noise parameter count. The tile holds
            whichever candidate is being fitted and `fit` sizes every slot to
            the widest, so a per-candidate `p` understates the allocation.
        n_time: Series length.
        n_models: Candidate count held until the tile is written.
        per_point_design: True if any regressor is a per-point field.

    Returns:
        The tile side in grid points.

    Raises:
        ValueError: If the budget does not hold one series.
    """
    return tile_side(
        budget_bytes,
        resident_bytes_per_series(
            k_beta=k_beta,
            p_max=p_max,
            n_time=n_time,
            n_models=n_models,
            per_point_design=per_point_design,
        ),
    )


def chunk_shape(handle: InputHandle) -> tuple[int, ...]:
    """Return the store's own chunk shape for the handle's variable.

    Read from the array's encoding, which for a dataset opened with
    `chunks=None` is the on-disk chunking. **A dataset opened through dask
    reports dask's graph chunking there instead**, which is a different number
    and is not what zarr reads — one more reason 2a stays off dask.

    Args:
        handle: An opened input, past the stage-4a contract.

    Returns:
        Chunk shape, in the variable's dimension order.

    Raises:
        InputContractError: If the array declares no chunking. Guessing one
            would make read amplification a number about an assumption.
    """
    array = handle.dataset[handle.variable]
    chunks = array.encoding.get("chunks") or array.encoding.get("preferred_chunks")
    if not chunks:
        raise InputContractError(
            f"{handle.uri!r}: variable {handle.variable!r} declares no chunk "
            "shape, so read amplification cannot be measured. Rechunk the store "
            "or open it through a reader that reports its chunking"
        )
    if isinstance(chunks, dict):
        chunks = tuple(chunks[str(dim)] for dim in array.dims)
    return tuple(int(size) for size in chunks)


def _chunk_points(start: int, stop: int, chunk: int, extent: int) -> int:
    """Points zarr decompresses on one axis to deliver `[start, stop)`.

    Args:
        start: First index, inclusive.
        stop: Last index, exclusive.
        chunk: Chunk length on this axis.
        extent: Axis length, so the last chunk is counted clipped.

    Returns:
        The decompressed point count on this axis.
    """
    first = start // chunk
    last = (stop - 1) // chunk
    return min((last + 1) * chunk, extent) - first * chunk


def read_amplification(handle: InputHandle, tile: Tile) -> float:
    """Return bytes read over bytes used for one tile, both decompressed.

    zarr reads whole chunks, so a tile straddling chunk boundaries silently
    reads several times what it needs. **This replaces the dask graph-chunk cap
    as the guard watching for a pathological input**, and tile geometry should
    align with input chunk geometry where possible.

    **THE UNITS ARE THE TRAP.** A store's bytes are compressed and a tile's are
    not, so a ratio taken across that boundary measures compression as well as
    amplification — measured, 3112 store bytes for 768 used where the true
    amplification is 4 — and on a compressible variable it would report a value
    **below 1**, which is meaningless for a metric defined as bytes read over
    bytes used. Both sides here are decompressed point counts.

    **Measured in the phase that can, printed by the phase that shows.** 2a
    computes and records it; Phase 5's `--explain` prints it. Computing it twice
    is how the two versions come to disagree, so this returns a number rather
    than warning.

    Args:
        handle: An opened input, past the stage-4a contract.
        tile: The tile about to be assembled.

    Returns:
        Bytes read divided by bytes used. 1.0 when the tile aligns with the
        chunk grid; never below 1.

    Raises:
        InputContractError: If the variable declares no chunk shape.
    """
    array = handle.dataset[handle.variable]
    chunks = chunk_shape(handle)
    sizes = {
        str(dim): int(size) for dim, size in zip(array.dims, array.shape, strict=True)
    }
    by_dim = {str(dim): size for dim, size in zip(array.dims, chunks, strict=True)}

    # The time axis is read WHOLE for every tile, so it contributes its full
    # extent to both sides and cancels -- but it is written out rather than
    # dropped, because it stops cancelling the moment a time-chunked read lands.
    read = _chunk_points(0, sizes["time"], by_dim["time"], sizes["time"])
    used = sizes["time"]
    for dim, start, stop in (
        ("y", tile.y_start, tile.y_stop),
        ("x", tile.x_start, tile.x_stop),
    ):
        read *= _chunk_points(start, stop, by_dim[dim], sizes[dim])
        used *= stop - start
    return read / used


def assembly_spans(handle: InputHandle, tile: Tile) -> list[Tile]:
    """Split a tile into sub-blocks, each lying inside one chunk.

    **THIS IS WHAT MAKES "BOTH FULL REPRESENTATIONS NEVER COEXIST" TRUE**, and
    it is public so it can be asserted rather than described. `assemble_tile`
    materializes these one at a time into a preallocated float64 destination, so
    at most one span's float32 is ever alive.

    Args:
        handle: An opened input, past the stage-4a contract.
        tile: The tile to split.

    Returns:
        The spans, in row-major order. They partition the tile exactly.
    """
    array = handle.dataset[handle.variable]
    chunks = chunk_shape(handle)
    by_dim = {str(dim): size for dim, size in zip(array.dims, chunks, strict=True)}
    return [
        Tile(y_start=y_from, y_stop=y_to, x_start=x_from, x_stop=x_to)
        for y_from, y_to in _aligned_spans(tile.y_start, tile.y_stop, by_dim["y"])
        for x_from, x_to in _aligned_spans(tile.x_start, tile.x_stop, by_dim["x"])
    ]


def assemble_tile(handle: InputHandle, tile: Tile) -> NDArray[np.float64]:
    """Materialize one tile as an `(n_series, n_time)` float64 block.

    **ASSEMBLED PER CHUNK-ALIGNED SPAN, WHICH IS A DEVIATION FROM THE BRIEF's
    LITERAL FIRST BULLET AND IS REQUIRED BY ITS SECOND.** One `.load()` over the
    whole tile materializes the entire float32 block, and casting that has both
    full representations alive at once -- which "float32 to float64 conversion
    per chunk, so both full representations never coexist" exists to forbid.
    Recomputed at design doc section 9.4's worked example on 2026-08-14, at the
    corrected `tile_side` of **347** (was 338) and N = 630: 347**2 * 630 =
    75 857 670 points, so the float32 tile is **303 MB** and the float64 tile
    **607 MB**, and the one-call form peaks at **910 MB against 607 MB -- a 50%
    overshoot of the data term** against a budget the design doc calls hard.
    The ratio is 3:2 by construction and does not move with the side; the
    absolute figures do, which is why they carry the side that produced them.

    So the float64 destination is allocated once and each span from
    `assembly_spans` is loaded, cast into its slice, and dropped.

    Args:
        handle: An opened input, past the stage-4a contract.
        tile: Which block to materialize.

    Returns:
        `(n_series, n_time)` float64, series in row-major grid order.
    """
    array = handle.dataset[handle.variable]
    n_time = int(array.shape[0])
    block = np.empty((tile.n_series, n_time), dtype=np.float64)
    width = tile.x_stop - tile.x_start

    for span in assembly_spans(handle, tile):
        piece = (
            array.isel(
                y=slice(span.y_start, span.y_stop),
                x=slice(span.x_start, span.x_stop),
            )
            .values.astype(np.float64)
            .reshape(n_time, -1)
            .T
        )
        rows = np.arange(span.y_start - tile.y_start, span.y_stop - tile.y_start)
        columns = np.arange(span.x_start - tile.x_start, span.x_stop - tile.x_start)
        block[(rows[:, None] * width + columns[None, :]).ravel()] = piece
        del piece
    return block


def _aligned_spans(start: int, stop: int, chunk: int) -> Iterator[tuple[int, int]]:
    """Split `[start, stop)` at chunk boundaries.

    Args:
        start: First index, inclusive.
        stop: Last index, exclusive.
        chunk: Chunk length on this axis.

    Yields:
        Half-open spans, each inside one chunk.
    """
    edge = start
    while edge < stop:
        nxt = min(int(math.floor(edge / chunk) + 1) * chunk, stop)
        yield edge, nxt
        edge = nxt


__all__ = [
    "Tile",
    "assemble_tile",
    "assembly_spans",
    "chunk_shape",
    "read_amplification",
    "tile_grid",
    "tile_side_for",
]
