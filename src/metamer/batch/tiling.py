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

**A TILE SIDE IS NOT A NUMBER WITHOUT ITS PRECONDITIONS, AND THIS DOCSTRING NO
LONGER STATES ONE.** The current pair and its full precondition list — budget,
measured floor, headroom, base, and §9.4's model — live in
`docs/superpowers/notes/phase1-to-phase2-handoff.md` §3, **once**. Every
superseded pair is struck there rather than deleted, so a reader meeting one in
an old note can date it. This file carried ~~347 shared / 187 per-point~~ until
2026-08-15, which was Task 0's corrected per-series cost divided into the
**whole** budget — the defect F1 names, and Task 2 fixed. **A second copy here
is how the two came to disagree**, and the source docstring is the half a
documentation sweep misses: this is the position §11.1 held while it carried the
superseded 445.

**AND THE SIDE NO LONGER CARRIES A BACKEND**, which is the visible half of the
correction: the two engines' published pairs differed only because the formula
charged one live solver working set to every series. `fit` runs one series at a
time, so the per-series cost is the data tile plus the output slots — neither of
which knows which engine is running — and the placement moves a **constant**.
~~`NUMPY_BATCHED` gives 338 / 186 and `COMPILED` gives 361 / 189~~, struck
2026-08-14.

**THE BUDGET'S UNIT IS SETTLED: `memory_budget_gb` IS 10⁹ BYTES.** It was
`1024**3` in `run.py` until Phase 2b Task 2 — 7.4% more bytes for the same word
— and correcting it LOWERS the budget, which is the safe direction against a
constraint the design doc calls hard. The field is named `_gb` and SI GB is
10⁹; a `1024**3` field is named `_gib`. **The value itself is resolved at run**
since Task 3: a config that omits it is distinguishable from one that names a
number, and the omission resolves to a fraction of TOTAL RAM.

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
from metamer.batch.store import TILE_SIDE_BASE
from metamer.core.memory import (
    HEADROOM_FRACTION,
    FloorReport,
    SolverPlacement,
    resident_bytes_per_series,
    solver_state_bytes,
    tile_side,
)

_INVERSE_WALK_LIMIT = 64
"""How far `budget_bytes_for_side` may walk from its closed form, in bytes.

The closed form and `block_bytes_for` are the same arithmetic in opposite
directions, so they can disagree only by float rounding -- a byte or two. The
limit is generous against that and tiny against any real error, which is what
makes it a guard: see `budget_bytes_for_side`.
"""


class BudgetTooSmallError(ValueError):
    """A memory budget that does not leave a usable block.

    **A DISTINCT TYPE RATHER THAN A BARE `ValueError`**, so the caller that
    stages it into a layer-3 refusal dispatches structurally instead of on
    message text -- (c2). `memory.tile_side` also raises `ValueError`, for the
    different condition "the block holds no series", and the two must never be
    told apart by their wording.
    """


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


def block_bytes_for(*, budget_bytes: int, floor: FloorReport) -> int:
    """Return what a tile may hold, out of what the process may hold.

    **`block_bytes = budget - floor - headroom`, AND THE BUDGET IS THE PROCESS,
    NOT THE TILE.** `--memory-budget` bounds process peak RSS -- that is what
    exit criterion 7 asserts -- and until 2026-08-15 the budget was passed
    straight in as the block, so a tile was sized to the whole budget and the
    interpreter's hundreds of megabytes had nowhere to live. At a 1 GB budget
    the tile came out at **996 MB, 92.8% of it, against a 221.5 MB floor**: the
    criterion was met only because the suite fits four series.

    **The floor taken is `peak_bytes`**, not the post-warm current reading,
    because criterion 7 is about a peak: what must come out of the budget is the
    high-water mark of everything that is not the tile. See `memory.FloorReport`.

    **The headroom is a FRACTION of what is left after the floor**, not of the
    budget: what it absorbs scales with the block. See `memory.HEADROOM_FRACTION`
    for the four things it covers and for the asymmetry that sets its value.

    Args:
        budget_bytes: The resolved process memory budget, in bytes.
        floor: The measured process floor.

    Returns:
        Bytes a tile may hold.

    Raises:
        BudgetTooSmallError: If the budget does not clear the floor and the
            headroom. **The message names the floor, its components and a budget
            that would work**, because the user has no other way to find out --
            a refusal that says only "too small" is a wall, and this one is
            planning information against a hard constraint.
    """
    available = budget_bytes - floor.peak_bytes
    block = int(available * (1.0 - HEADROOM_FRACTION))
    if block < 1:
        ladder = ", ".join(
            f"{name} {value / 1e6:.1f} MB"
            for name, value in sorted(floor.components.items())
        )
        workable = int((floor.peak_bytes + 1) / (1.0 - HEADROOM_FRACTION)) + 1
        raise BudgetTooSmallError(
            f"a memory budget of {budget_bytes / 1e9:.4g} GB ({budget_bytes} B) "
            f"leaves nothing for a tile: this process holds "
            f"{floor.peak_bytes / 1e6:.1f} MB before a tile exists, and "
            f"{HEADROOM_FRACTION:.0%} of what is left is held back for "
            f"transients. The floor, rung by rung: {ladder}. A budget above "
            f"{workable / 1e9:.4g} GB ({workable} B) leaves a positive block; a "
            f"useful one is several times that, since the tile is what the "
            f"budget is for"
        )
    return block


def tile_side_for(
    *,
    budget_bytes: int,
    floor: FloorReport,
    placement: SolverPlacement = SolverPlacement.PER_SERIES_LIVE,
    d: int,
    threads: int = 1,
    k_beta: int,
    p_max: int,
    n_time: int,
    n_models: int,
    per_point_design: bool = False,
) -> int:
    """Return the square tile side a memory budget allows.

    `sqrt((block_bytes - solver_state) / resident_bytes_per_series)`, floored,
    then rounded **down** to a multiple of `store.TILE_SIDE_BASE`.

    **NOT `sqrt(block_bytes / (n_time * itemsize))`**, which is the prompt's
    formula: it counts only the float64 data and overestimates, giving 445 where
    the full accounting gives 272. Design doc §11.1 carried it until 2026-08-12
    while §9.4 rejected it, and §11.1 is the section a tiling implementer opens
    first.

    **THE ROUNDING HAPPENS HERE, BEFORE THE SIDE IS STORED**, and that placement
    is the point rather than a detail. A calibration that rounded at its own call
    site would exercise a derivation the production run does not, which is (j2);
    and a resume reads the side back out of the store, so the stored value must
    already be the rounded one or the two derivations disagree by construction.

    **AND IT REMOVES A FOOTGUN RATHER THAN DOCUMENTING ONE.** With every derived
    side a multiple of the base, Task 7's instrument gets chunk-friendly sides
    **by construction**, and there is no deliberate choice of awkward budgets for
    a later reader to "simplify" into round numbers. A property that holds
    structurally beats one that must survive future editing.

    Args:
        budget_bytes: The resolved process memory budget, in bytes.
        floor: The measured process floor.
        placement: Where the live solver state sits. One reachable value.
        d: Composite state dimension, the widest candidate's. It reaches the
            arithmetic only through the solver constant.
        threads: Worker threads. Ignored under the reachable placement.
        k_beta: Number of design columns.
        p_max: Widest candidate's free noise parameter count. The tile holds
            whichever candidate is being fitted and `fit` sizes every slot to
            the widest, so a per-candidate `p` understates the allocation.
        n_time: Series length.
        n_models: Candidate count held until the tile is written.
        per_point_design: True if any regressor is a per-point field.

    Returns:
        The tile side in grid points: a multiple of `store.TILE_SIDE_BASE`, or a
        raw side below the base, where the base is provably inert.

    Raises:
        BudgetTooSmallError: If the budget does not clear the floor and the
            headroom, or if what is left does not hold one series at the base.
            **Both arms are this type**, because both are the same question to
            the user -- "your budget is too small, here is one that works" --
            and dispatching on which arithmetic step ran out is the caller's
            problem rather than theirs.
    """
    block = block_bytes_for(budget_bytes=budget_bytes, floor=floor)
    constant = solver_state_bytes(
        placement, d=d, k_beta=k_beta, p_max=p_max, threads=threads
    )
    per_series = resident_bytes_per_series(
        k_beta=k_beta,
        p_max=p_max,
        n_time=n_time,
        n_models=n_models,
        per_point_design=per_point_design,
    )
    if block - constant < per_series:
        raise BudgetTooSmallError(
            f"a memory budget of {budget_bytes / 1e9:.4g} GB leaves a block of "
            f"{block} B, of which {constant} B is the live solver working set, "
            f"so {block - constant} B remain against {per_series} B for one "
            f"series. The process floor is {floor.peak_bytes / 1e6:.1f} MB and "
            f"{HEADROOM_FRACTION:.0%} of what is above it is held back for "
            f"transients"
        )
    raw = tile_side(block - constant, per_series)
    # **BELOW THE BASE THE BASE IS INERT, SO THE SIDE PASSES THROUGH.** The base
    # exists because `store._chunk_side` picks a DIVISOR of the side, and that
    # only matters once some array's shard can reach `CHUNK_TARGET_BYTES`. The
    # widest array is `warmstart/theta_unconstrained` at `8 * P_total` bytes per
    # cell, so a shard reaches the target at
    # `side >= sqrt(CHUNK_TARGET_BYTES / (8 * P_total))` -- 112 at P_total = 40,
    # and a side below 16 would need P_total above 2200 to get there. **So for
    # every side under the base, every array is already one chunk per shard and
    # the divisor structure is irrelevant.** Rounding such a side to zero would
    # refuse a small run for no benefit at all.
    if raw < TILE_SIDE_BASE:
        return raw
    return (raw // TILE_SIDE_BASE) * TILE_SIDE_BASE


def budget_bytes_for_side(
    *,
    side: int,
    floor: FloorReport,
    placement: SolverPlacement = SolverPlacement.PER_SERIES_LIVE,
    d: int,
    threads: int = 1,
    k_beta: int,
    p_max: int,
    n_time: int,
    n_models: int,
    per_point_design: bool = False,
) -> int:
    """Return the smallest budget whose derived tile side is exactly `side`.

    **`tile_side_for` INVERTED, IN THE SAME MODULE AND OFF THE SAME CONSTANTS**,
    because a calibration cannot choose its own B. A run's batch is a **tile**,
    so `B = side**2`, and since Task 2 every derived side is a multiple of
    `store.TILE_SIDE_BASE` -- which is why Phase 2b's calibration ladder is a
    ladder in **sides** and not in series, and why the brief's
    `B in {1000, 2000, 4000}` names three batches no tile can have
    (`sqrt(1000) = 31.6`).

    **THE INVERSE LIVES BESIDE THE FORWARD FUNCTION DELIBERATELY.** Split across
    modules the two drift, and the drift is silent: the ladder still runs and
    every point sits at a B nobody asked for. `tests/test_tiling.py` asserts the
    round trip rather than any hand-written budget, which is the executable form
    of "the calibration uses the production derivation" (j2).

    Args:
        side: The tile side wanted. Below `store.TILE_SIDE_BASE` the base is
            inert and any side is reachable; at or above it, only multiples of
            the base are, and a non-multiple raises.
        floor: The measured process floor. **Pin it across a ladder**: it is
            measured fresh per run and varies by megabytes, while the budget
            window selecting one multiple of the base is narrower than that.
        placement: Where the live solver working set sits.
        d: Composite state dimension, the widest candidate's.
        threads: Worker threads. Ignored under the reachable placement.
        k_beta: Number of design columns.
        p_max: Widest candidate's free noise parameter count.
        n_time: Series length.
        n_models: Candidate count held until the tile is written.
        per_point_design: True if any regressor is a per-point field.

    Returns:
        The budget in bytes.

    Raises:
        ValueError: If `side` is not positive, or is at or above the base and
            not a multiple of it -- **a request no budget can satisfy**, and
            returning the nearest reachable side instead would hand the caller a
            B it did not ask for, which is the defect this function exists to
            make impossible.
    """
    if side < 1:
        raise ValueError(f"tile side must be positive, got {side}")
    if side >= TILE_SIDE_BASE and side % TILE_SIDE_BASE:
        raise ValueError(
            f"no budget derives a tile side of {side}: every side at or above "
            f"{TILE_SIDE_BASE} is rounded down to a multiple of it, so the "
            f"reachable sides near {side} are "
            f"{(side // TILE_SIDE_BASE) * TILE_SIDE_BASE} and "
            f"{(side // TILE_SIDE_BASE + 1) * TILE_SIDE_BASE}"
        )
    block = side * side * resident_bytes_per_series(
        k_beta=k_beta,
        p_max=p_max,
        n_time=n_time,
        n_models=n_models,
        per_point_design=per_point_design,
    ) + solver_state_bytes(placement, d=d, k_beta=k_beta, p_max=p_max, threads=threads)
    # **THE CLOSED FORM IS THE STARTING POINT AND `block_bytes_for` IS THE
    # ARBITER.** Inverting `int((budget - floor) * (1 - headroom))` in floats
    # gets the answer right to within a byte or two and wrong in a direction
    # that depends on the rounding, and a byte here is a whole tile side. So the
    # closed form seeds a walk that asks the forward function -- **the inverse
    # is verified against the function it inverts rather than against a second
    # piece of float reasoning** (j), and the result is exactly minimal.
    budget = floor.peak_bytes + int(math.ceil(block / (1.0 - HEADROOM_FRACTION)))
    for _ in range(_INVERSE_WALK_LIMIT):
        if block_bytes_for(budget_bytes=budget, floor=floor) >= block:
            return budget
        budget += 1
    # **BOUNDED, AND THE BOUND IS A GUARD RATHER THAN A SAFETY NET.** An
    # unbounded walk repairs a closed form that is wrong by any amount -- it
    # just takes a byte at a time, so a seed that omitted the headroom would
    # still return the right answer after ~10**8 iterations and nothing would
    # fail. Measured: that mutation left every round-trip test green and turned
    # a 2.4 s module into a 21.5 s one, which is a defect no assertion here was
    # looking at. With the bound, a closed form that disagrees with
    # `block_bytes_for` by more than rounding says so.
    raise ValueError(
        f"the closed form for a tile side of {side} disagrees with "
        f"block_bytes_for by more than {_INVERSE_WALK_LIMIT} bytes; the two are "
        "the same arithmetic and one of them has changed"
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
    "budget_bytes_for_side",
    "assemble_tile",
    "assembly_spans",
    "chunk_shape",
    "read_amplification",
    "tile_grid",
    "tile_side_for",
]
