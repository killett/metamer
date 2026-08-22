"""Tiling: the grid, the assembly, and read amplification.

Three claims, and they fail in three different ways.

**The grid covers every point exactly once.** A miss writes a store with an
unwritten seam; an overlap writes some points twice. Neither raises, both produce
a complete-looking store, and the completion bitmap is per tile so it cannot see
either.

**Assembly never holds both representations of the whole tile.** Recomputed at
design doc section 9.4's worked example and `PUBLISHED_TILE_SIDE.shared` the
difference is 559 MB against 373 MB -- a 50% overshoot of the data term against
a budget the design doc calls hard. ~~863 against 575~~, at the superseded 338.

**Read amplification is measured in one set of units.** The store's bytes are
compressed and the tile's are not, so a ratio taken across that boundary measures
compression as well as amplification and can report less than 1.
"""

from __future__ import annotations

import inspect
import warnings
from collections import Counter
from typing import Any

import numpy as np
import pytest
import xarray as xr
from zarr.storage import LocalStore

from metamer.batch.input import InputContractError, open_input
from metamer.batch.store import CHUNK_TARGET_BYTES, TILE_SIDE_BASE
from metamer.batch.tiling import (
    PUBLISHED_TILE_SIDE,
    BudgetTooSmallError,
    Tile,
    assemble_tile,
    assembly_spans,
    block_bytes_for,
    budget_bytes_for_side,
    chunk_shape,
    read_amplification,
    tile_grid,
    tile_side_for,
)
from metamer.core.memory import (
    HEADROOM_FRACTION,
    SolverPlacement,
    resident_bytes_per_series,
    solver_state_bytes,
    tile_side,
)

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")

#: Design doc section 9.4's worked example, as `tile_side_for` takes it.
#:
#: **ALIASES INTO `PUBLISHED_TILE_SIDE`, NOT A SECOND DEFINITION.** These were
#: literals here until Phase 2b Task 9, which is one of the three copies of
#: section 9.4's model the tree carried -- with `validation.py`'s
#: `_WORKED_EXAMPLE` and the record itself -- and two copies of one derivation
#: drift silently, because a wrong tile side still runs. A pointer is not a
#: copy: change the record and every call site below follows.
WORKED_EXAMPLE: dict[str, Any] = {
    "d": PUBLISHED_TILE_SIDE.d,
    **PUBLISHED_TILE_SIDE.per_series_model,
}

#: **THE PUBLISHED SIDE NEEDS A PINNED FLOOR AMONG ITS PRECONDITIONS**, which it
#: never did before Phase 2b Task 2: the floor is measured with the input open,
#: so the derived side depends on the store being read -- and on **which** store,
#: measured at 1.28 MB across two inputs on 2026-08-17.
WORKED_FLOOR = PUBLISHED_TILE_SIDE.floor


def _store(tmp_path, *, n_time=12, n_y=16, n_x=16, chunks=(12, 4, 4), name="a.zarr"):
    """A real zarr store with NON-CONSTANT data.

    **Zeros would make every test here vacuous.** Zarr does not write a chunk
    equal to the fill value, so a zero-filled store serves every read from the
    fill value and the store is never touched: measured, 0 bytes and 0 keys for
    a read that returned the right number of correct-looking values.
    """
    data = np.random.default_rng(0).standard_normal((n_time, n_y, n_x))
    dataset = xr.Dataset(
        {"sla": (("time", "y", "x"), data.astype("float32"))},
        coords={
            "time": np.array(
                [
                    np.datetime64("2000-01-01") + np.timedelta64(31 * i, "D")
                    for i in range(n_time)
                ]
            ),
            "y": np.arange(n_y),
            "x": np.arange(n_x),
        },
    )
    path = tmp_path / name
    dataset.to_zarr(path, encoding={"sla": {"chunks": chunks}})
    return str(path)


class _FetchLog:
    """Records which chunk keys zarr actually asks the store for.

    **An oracle over the SET OF CHUNKS, never over bytes.** The store returns
    compressed bytes and a tile is counted decompressed, so a byte ratio taken
    across that boundary measures compression too -- measured 3112/768 = 4.05
    where the true amplification is 4, and on a compressible variable it would
    come out below 1. Chunk keys share no construction with the analytic index
    arithmetic, which is what makes this an independent check rather than the
    same formula twice.
    """

    def __init__(self):
        self.keys: list[str] = []

    def __enter__(self):
        self._original = LocalStore.get

        async def patched(store, key, prototype, byte_range=None):
            buffer = await self._original(store, key, prototype, byte_range)
            if buffer is not None and not key.endswith("zarr.json"):
                self.keys.append(key)
            return buffer

        LocalStore.get = patched  # type: ignore[method-assign,assignment]
        return self

    def __exit__(self, *exc):
        LocalStore.get = self._original  # type: ignore[method-assign]
        return False


# --------------------------------------------------------------------------
# The grid
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("n_y", "n_x", "side"),
    [(16, 16, 4), (17, 13, 5), (3, 3, 8), (1, 1, 1), (10, 1, 3)],
    ids=["exact", "ragged-both", "side-exceeds-grid", "single-point", "one-column"],
)
def test_the_grid_covers_every_point_exactly_once(n_y, n_x, side):
    """Every `(y, x)` appears in exactly one tile, ragged edges included.

    Expected value derived independently of the implementation: the multiset of
    covered points must equal the full grid, which is a statement about the
    dataset rather than about the tiling.

    Bug this catches: a miss or an overlap at a ragged edge -- `range(0, n, side)`
    with a `stop` clamped wrongly, or a half-open/closed confusion. **Neither
    raises.** A miss leaves a seam of unwritten points in a store whose
    completion bitmap is per tile and therefore cannot see it; an overlap writes
    some points twice. **Asserting the NUMBER of tiles would catch neither**, so
    the points are accumulated and compared as a multiset -- which distinguishes
    a miss from a duplicate, and they are different defects.
    """
    covered = Counter(
        (y, x)
        for tile in tile_grid(n_y, n_x, side)
        for y in range(tile.y_start, tile.y_stop)
        for x in range(tile.x_start, tile.x_stop)
    )
    expected = Counter((y, x) for y in range(n_y) for x in range(n_x))
    assert covered == expected


def test_every_tile_is_non_empty_and_within_the_grid():
    """No tile is empty and none runs past the edge.

    Bug this catches: a trailing empty tile from `range` arithmetic that is off
    by one. It covers the grid correctly -- so the test above passes -- and then
    the tiling loop reads a zero-width selection, which `.load()` accepts, and
    the fit driver receives `B = 0`.
    """
    for tile in tile_grid(17, 13, 5):
        assert tile.y_start < tile.y_stop <= 17
        assert tile.x_start < tile.x_stop <= 13
        assert tile.n_series == (tile.y_stop - tile.y_start) * (
            tile.x_stop - tile.x_start
        )


def test_a_side_of_zero_is_refused():
    """A non-positive tile side raises rather than yielding nothing.

    Bug this catches: `range(0, n, 0)`, which raises `ValueError` from deep
    inside the iterator with a message about `range`, and a side computed as 0
    from a budget too small to hold one series -- which `memory.tile_side`
    already refuses for the same reason, because a side of 0 is a
    plausible-looking number that holds no data.
    """
    with pytest.raises(ValueError, match="side"):
        list(tile_grid(4, 4, 0))


def test_the_tile_side_is_budgeted_against_the_resident_figure(tmp_path):
    """`tile_side_for` budgets against `resident_bytes_per_series`.

    Expected value RE-DERIVED BY HAND from the corrected formula, not read off
    a failure: the per-series cost at design doc section 9.4's worked example is
    630 * 9 = 5670 data plus 12 * 217 = 2604 output slots, so 8274, and
    10**9 / 8274 = 120 860.5 with 347**2 = 120 409 <= 120 860.5 < 121 104 =
    348**2. The side is **347**. The superseded pair is ~~338~~ (from a
    per-series figure that charged one live solver working set to every series)
    and ~~339~~ (from the section 9.4 model, now deleted).

    **AND `tile_side_for` NO LONGER TAKES A BACKEND OR A `d`.** The per-series
    cost is the data tile plus the output slots, neither of which knows which
    engine is running.

    Bug this catches: a tile side derived from anything other than what one more
    series in the tile actually costs. The two failure directions are not
    symmetric -- the section 9.4 model omitted what the engines hold and gave a
    side that was too large, which overcommits a budget the design doc calls
    hard; the superseded resident figure charged a constant per series and gave
    one too small, which is safe and wastes runtime. **Only a measurement tells
    them apart**, which is why Task 7 exists.
    """
    expected = tile_side(
        10**9,
        resident_bytes_per_series(k_beta=4, p_max=4, n_time=630, n_models=12),
    )
    assert 347**2 <= 10**9 / 8274 < 348**2
    assert expected == 347
    # ...and 347 is what a budget-IS-the-block derivation gives. What
    # `tile_side_for` returns is smaller by the floor, the headroom and the
    # rounding; see `test_the_worked_example_derives_272_from_the_whole_chain`.
    assert tile_side_for(budget_bytes=10**9, floor=WORKED_FLOOR, **WORKED_EXAMPLE) < 347


# --------------------------------------------------------------------------
# Assembly
# --------------------------------------------------------------------------


def test_the_assembled_tile_is_float64_and_matches_the_source(tmp_path):
    """The positive control: assembly returns the right numbers.

    Every assertion below is about *how* the tile is assembled, and all of them
    are satisfied by an assembler that returns garbage. This is the half that
    checks it returns the data.

    Bug this catches: a transposed or misindexed selection. The shape would be
    right, the dtype right, the peak right, and every series fitted at the wrong
    grid point -- a whole map that is correct except for where everything is.
    """
    uri = _store(tmp_path)
    handle = open_input(uri, "sla")
    tile = Tile(y_start=2, y_stop=6, x_start=3, x_stop=7)
    block = assemble_tile(handle, tile)

    assert block.dtype == np.float64
    assert block.shape == (tile.n_series, 12)
    expected = (
        handle.dataset["sla"]
        .isel(y=slice(2, 6), x=slice(3, 7))
        .values.astype(np.float64)
        .reshape(12, -1)
        .T
    )
    np.testing.assert_array_equal(block, expected)


def test_assembly_splits_the_tile_at_chunk_boundaries(tmp_path):
    """The spans partition the tile and each lies inside a single chunk.

    **The brief's two bullets conflict and the numbers decide.** One `.load()`
    over the whole tile materializes the entire float32 block, and casting it
    afterwards has both alive at once. Recomputed 2026-08-17 at section 9.4's
    worked example and `PUBLISHED_TILE_SIDE.shared` = 272, N = 630: 272**2 * 630
    = 46 609 920 points, so 186 MB of float32 beside 373 MB of float64,
    **559 MB against 373 MB, a 50% overshoot of the data term** against a budget
    the design doc calls hard. ~~At the superseded 338 the figures were 288 MB,
    575 MB and 863 MB.~~ The ratio is 3:2 by construction and does not move with
    the side; the absolute figures do, which is why they carry the side that
    produced them and are recomputed when the record moves.

    Bug this catches: `handle.dataset[var].isel(...).load().astype(float64)`,
    which is what the brief says literally. Under it the span list is one span
    covering the whole tile, and both assertions below fail.

    **What this does NOT assert, stated rather than implied:** the peak itself.
    At test scale the difference is kilobytes and RSS cannot resolve it, and the
    instruments that could -- see `tests/test_memory.py` -- are the ones this
    project has already paid to make honest. The claim asserted here is the
    mechanism the peak rests on: the spans are sub-chunk, and `assemble_tile`
    consumes exactly them.
    """
    uri = _store(tmp_path, n_y=16, n_x=16, chunks=(12, 4, 4))
    handle = open_input(uri, "sla")
    tile = Tile(y_start=2, y_stop=10, x_start=0, x_stop=8)

    spans = assembly_spans(handle, tile)
    # Every span sits inside one chunk on both axes...
    for span in spans:
        assert span.y_start // 4 == (span.y_stop - 1) // 4
        assert span.x_start // 4 == (span.x_stop - 1) // 4
    # ...and together they cover the tile exactly once, which is the same
    # multiset check the grid gets, for the same reason.
    covered = Counter(
        (y, x)
        for span in spans
        for y in range(span.y_start, span.y_stop)
        for x in range(span.x_start, span.x_stop)
    )
    assert covered == Counter(
        (y, x)
        for y in range(tile.y_start, tile.y_stop)
        for x in range(tile.x_start, tile.x_stop)
    )
    assert len(spans) > 1


# --------------------------------------------------------------------------
# Read amplification
# --------------------------------------------------------------------------


def test_an_aligned_tile_reads_exactly_what_it_uses(tmp_path):
    """Amplification is 1.0 when the tile matches the chunk grid.

    Expected value derived by hand: a 4x4 tile on a 4x4 chunk grid touches one
    chunk and uses all of it.

    Bug this catches: a metric computed from the REQUEST -- tile bytes over tile
    bytes -- which is 1.0 for every input including the pathological ones. This
    test passes against that defect and the next one does not, which is why they
    are two tests.
    """
    uri = _store(tmp_path, n_y=16, n_x=16, chunks=(12, 4, 4))
    handle = open_input(uri, "sla")
    tile = Tile(y_start=0, y_stop=4, x_start=0, x_stop=4)
    assert read_amplification(handle, tile) == pytest.approx(1.0)


def test_a_straddling_tile_reports_the_amplification_it_causes(tmp_path):
    """A tile offset by half a chunk in both axes reads 4x what it uses.

    Expected value by hand: a 4x4 tile starting at (2, 2) on a 4x4 chunk grid
    overlaps 2 chunks in y and 2 in x, so zarr decompresses 4 chunks -- 64
    points -- to deliver 16. **Measured against a counting store: 4 chunk
    fetches**, matching.

    Bug this catches: the metric that reads 1.0 for everything. It is the guard
    that replaced the graph-chunk cap, so a pathological input is now visible
    only here -- and a tile straddling chunk boundaries at 10^7 points reads
    several times the archive for nothing.
    """
    uri = _store(tmp_path, n_y=16, n_x=16, chunks=(12, 4, 4))
    handle = open_input(uri, "sla")
    tile = Tile(y_start=2, y_stop=6, x_start=2, x_stop=6)
    assert read_amplification(handle, tile) == pytest.approx(4.0)


def test_the_predicted_chunk_set_is_what_zarr_actually_fetches(tmp_path):
    """The analytic prediction, checked against the store's own behaviour.

    **The oracle shares no construction with the subject.** Amplification is
    arithmetic over index ranges; this counts the keys zarr asks a patched
    `LocalStore` for. Independent in the sense (j) requires -- a different
    mechanism, not the same formula at a different tolerance.

    **Compared as CHUNK COUNTS, never as bytes.** The store returns compressed
    bytes and the tile is counted decompressed: measured 3112 store bytes for
    768 used, a ratio of 4.05 where the truth is 4, and on a compressible
    variable the same ratio would fall below 1 -- meaningless for a metric
    defined as bytes read over bytes used.

    Bug this catches: an amplification computed over the wrong axis set, or one
    that forgets that the time axis is read whole. Both give a plausible number
    that no arithmetic-only test would question.
    """
    uri = _store(tmp_path, n_y=16, n_x=16, chunks=(12, 4, 4))
    handle = open_input(uri, "sla")

    for tile, expected_chunks in (
        (Tile(y_start=0, y_stop=4, x_start=0, x_stop=4), 1),
        (Tile(y_start=2, y_stop=6, x_start=2, x_stop=6), 4),
        (Tile(y_start=0, y_stop=8, x_start=0, x_stop=4), 2),
    ):
        with _FetchLog() as log:
            handle.dataset["sla"].isel(
                y=slice(tile.y_start, tile.y_stop),
                x=slice(tile.x_start, tile.x_stop),
            ).load()
        assert len(set(log.keys)) == expected_chunks
        used = tile.n_series * 12
        assert read_amplification(handle, tile) == pytest.approx(
            expected_chunks * 12 * 4 * 4 / used
        )


def test_the_chunk_shape_is_read_from_the_store_and_not_assumed(tmp_path):
    """`chunk_shape` reports what the store was written with.

    Bug this catches: assuming the whole variable is one chunk, or reading the
    xarray *encoding* of a dataset opened with dask, where `chunks` is dask's
    graph chunking rather than the store's. The two are different numbers and
    only one of them is what zarr reads.
    """
    uri = _store(tmp_path, n_time=12, n_y=16, n_x=16, chunks=(12, 8, 2))
    handle = open_input(uri, "sla")
    assert chunk_shape(handle) == (12, 8, 2)


def test_a_tile_wider_than_the_grid_is_still_measured_correctly(tmp_path):
    """A tile clipped by the grid edge does not read chunks past the edge.

    Bug this catches: computing the touched-chunk count from the tile's nominal
    side rather than from its clipped extent, which reports amplification on
    edge tiles that the store never suffers -- and edge tiles are where the
    ragged arithmetic already lives.
    """
    uri = _store(tmp_path, n_y=10, n_x=10, chunks=(12, 4, 4))
    handle = open_input(uri, "sla")
    tile = Tile(y_start=8, y_stop=10, x_start=8, x_stop=10)
    # Rows 8-9 and columns 8-9 lie in the third chunk of each axis, which is
    # itself clipped to 2x2 by the grid. So one chunk of 2x2x12 is read to
    # deliver 2x2x12: amplification 1.0, not 4.0.
    assert read_amplification(handle, tile) == pytest.approx(1.0)


def test_warnings_are_not_used_to_report_amplification(tmp_path):
    """Amplification is a returned number, recorded into provenance.

    **Measure in the phase that can, print in the phase that shows.** 2a
    computes it; Phase 5's `--explain` prints it. A warning emitted here would
    be the second implementation, and the two would disagree.

    Bug this catches: reporting through the warnings channel, where it is
    invisible to the store's provenance and to any later comparison.
    """
    uri = _store(tmp_path, n_y=16, n_x=16, chunks=(12, 4, 4))
    handle = open_input(uri, "sla")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert (
            read_amplification(handle, Tile(y_start=2, y_stop=6, x_start=2, x_stop=6))
            > 1.0
        )


def test_an_input_that_declares_no_chunking_is_refused(tmp_path):
    """A dataset with no chunk shape raises rather than being guessed at.

    Reachable through the opener registry, which is what makes this testable:
    an opener returning an in-memory dataset produces a handle whose variable
    has no `encoding["chunks"]` -- and that is not hypothetical, it is what any
    non-chunked backend registered later will hand back.

    Bug this catches: falling back to the array's shape, i.e. "the whole
    variable is one chunk". Read amplification would then read 1.0 for every
    input including the pathological ones -- **and this metric replaced the
    graph-chunk cap as the only guard watching for a pathological input**, so a
    silent 1.0 removes the guard rather than weakening it.
    """
    from metamer.batch import input as batch_input

    dataset = xr.Dataset(
        {"sla": (("time", "y", "x"), np.ones((4, 2, 2), dtype="float32"))},
        coords={
            "time": np.array(
                [
                    np.datetime64("2000-01-01") + np.timedelta64(31 * i, "D")
                    for i in range(4)
                ]
            ),
            "y": np.arange(2),
            "x": np.arange(2),
        },
    )
    batch_input.opener_registry.register("memchunkless")(lambda uri: dataset)
    try:
        handle = open_input("memchunkless://none", "sla")
        with pytest.raises(InputContractError, match="no chunk shape"):
            chunk_shape(handle)
        with pytest.raises(InputContractError, match="no chunk shape"):
            read_amplification(handle, Tile(y_start=0, y_stop=2, x_start=0, x_stop=2))
    finally:
        batch_input.opener_registry.unregister("memchunkless")


# --------------------------------------------------------------------------
# The budget, the block, and the smooth base (Phase 2b Task 2)
# --------------------------------------------------------------------------


def test_the_worked_example_derives_272_from_the_whole_chain():
    """Every step of `budget -> block -> side -> rounded side`, by hand.

    Expected values derived independently, at design doc section 9.4's worked
    example under a 10**9 B budget and this machine's measured floor:

        floor.peak                                   228 200 000 B
        available = budget - floor                   771 800 000 B
        block     = available * (1 - 0.15)           656 030 000 B
        block - solver_state(11 984)                 656 018 016 B
        / 8274 B per series                              79 285.5
        sqrt                                                281.6
        floor()                                               281
        round down to a multiple of 16                    **272**

    Bug this catches: F1 recurring -- the budget used as the block. That gave
    **347** here, a tile of 996 MB against a 1 GB budget with a 228 MB floor
    already spent, and exit criterion 7 was unsatisfiable by arithmetic. It
    also catches the rounding being dropped: 281 is prime-adjacent enough to
    matter, and 272 = 16 x 17 is what makes the store's chunks land near target.

    **AND THE FLOOR IS A PRECONDITION OF THE PUBLISHED NUMBER NOW**, which it
    never was: the floor is measured with the input open, so the side depends on
    the store being read. `WORKED_FLOOR` pins it.
    """
    available = 10**9 - WORKED_FLOOR.peak_bytes
    assert available == 771_800_000
    block = block_bytes_for(budget_bytes=10**9, floor=WORKED_FLOOR)
    assert block == int(available * (1 - HEADROOM_FRACTION)) == 656_030_000

    constant = solver_state_bytes(
        SolverPlacement.PER_SERIES_LIVE, d=3, k_beta=4, p_max=4
    )
    per_series = resident_bytes_per_series(k_beta=4, p_max=4, n_time=630, n_models=12)
    assert constant == 11_984
    assert per_series == 8_274
    raw = tile_side(block - constant, per_series)
    assert 281**2 <= (block - constant) / per_series < 282**2
    assert raw == 281

    side = tile_side_for(budget_bytes=10**9, floor=WORKED_FLOOR, **WORKED_EXAMPLE)
    assert side == 272
    assert side == (raw // TILE_SIDE_BASE) * TILE_SIDE_BASE
    # Per-point X, the other branch of the same worked example.
    assert (
        tile_side_for(
            budget_bytes=10**9,
            floor=WORKED_FLOOR,
            per_point_design=True,
            **WORKED_EXAMPLE,
        )
        == 144
    )


def test_a_tile_at_the_derived_side_plus_the_floor_fits_inside_the_budget():
    """The arithmetic criterion 7 asserts, checked here and measured in Task 8.

    Expected values determined independently: the tile holds
    `side**2 * per_series + solver_state`, and that plus the floor must sit
    inside the budget with the headroom still unspent.

    **THE ABSOLUTE COMES FIRST AND THE RELATION SECOND** -- (i3). "The tile plus
    the floor is within the budget" is satisfied by a side of zero, by a floor of
    zero, and by both being wrong in the same direction, so the derived side is
    asserted against its own hand-computed value before any inequality is.

    Bug this catches: F1 recurring at any budget rather than only at the
    documented one. Under the defect the tile alone was 92.8% of the budget with
    the floor unaccounted for, so the check below fails by a factor of four.
    """
    for budget in (10**9, 2 * 10**9, 4 * 10**9, 8 * 10**9):
        side = tile_side_for(budget_bytes=budget, floor=WORKED_FLOOR, **WORKED_EXAMPLE)
        tile = side * side * resident_bytes_per_series(
            k_beta=4, p_max=4, n_time=630, n_models=12
        ) + solver_state_bytes(SolverPlacement.PER_SERIES_LIVE, d=3, k_beta=4, p_max=4)
        assert tile + WORKED_FLOOR.peak_bytes <= budget
        # ...and the headroom really is still unspent, which is what makes this
        # a bound rather than a coincidence at the rounding.
        assert tile <= block_bytes_for(budget_bytes=budget, floor=WORKED_FLOOR)
    assert [
        tile_side_for(budget_bytes=b, floor=WORKED_FLOOR, **WORKED_EXAMPLE)
        for b in (10**9, 2 * 10**9, 4 * 10**9, 8 * 10**9)
    ] == [272, 416, 608, 880]


def test_a_budget_at_or_below_the_floor_is_refused_with_planning_information():
    """The refusal names the floor, its rungs, and a budget that would work.

    Expected behaviour determined independently: at a budget equal to the floor
    the available bytes are zero, so the block is zero and no tile exists.

    Bug this catches: a refusal that says only "too small". The user has no
    other way to discover the floor -- it is a property of this release on this
    machine with this input open, and it is measured rather than documented -- so
    a bare refusal is a wall while this one is planning information against a
    hard constraint.
    """
    with pytest.raises(BudgetTooSmallError) as caught:
        block_bytes_for(budget_bytes=WORKED_FLOOR.peak_bytes, floor=WORKED_FLOOR)

    message = str(caught.value)
    assert "228.2 MB" in message  # the floor
    assert "input_open" in message  # its components, by rung
    assert "15%" in message  # what else was held back
    # A budget that would work, and it really does.
    workable = int(WORKED_FLOOR.peak_bytes / (1 - HEADROOM_FRACTION)) + 2
    assert f"{workable / 1e9:.4g} GB" in message
    assert block_bytes_for(budget_bytes=workable, floor=WORKED_FLOOR) >= 1


def test_a_budget_that_clears_the_floor_but_holds_no_series_is_refused_too():
    """Both arms of "too small" are the same refusal type, and say the same thing.

    Expected behaviour determined independently: a budget just above the floor
    leaves a positive block that is still smaller than the 11 984 B solver
    working set plus 8274 B for one series.

    Bug this catches: the second arm escaping as `memory.tile_side`'s bare
    `ValueError`, whose message names bytes per series and never mentions the
    floor -- so the user reads "your series are too big" when the answer is
    "your budget is 228 MB of interpreter". Same question, so the same type
    (c2), dispatched structurally rather than on wording.
    """
    just_above = WORKED_FLOOR.peak_bytes + 10_000
    block = block_bytes_for(budget_bytes=just_above, floor=WORKED_FLOOR)
    assert block == 8500
    assert block < 11_984 + 8_274  # the solver working set plus one series
    with pytest.raises(BudgetTooSmallError, match="one series"):
        tile_side_for(budget_bytes=just_above, floor=WORKED_FLOOR, **WORKED_EXAMPLE)


def test_every_derived_side_at_or_above_the_base_is_a_multiple_of_it():
    """Over a wide range of budgets, not at one documented point.

    Expected behaviour determined independently: `tile_side_for` rounds down to
    a multiple of `TILE_SIDE_BASE`, and passes a raw side below the base through
    because below the base the base is provably inert -- the widest array is
    `8 * P_total` bytes per cell, so no shard can reach the chunk target until
    the side is around 112.

    Bug this catches: the rounding applied at a call site rather than inside the
    derivation. That is how a calibration and a production run come to disagree
    about the side for one configuration -- (j2) -- and how a resume reads back
    a side its own derivation would not have produced.
    """
    sides = []
    for budget in range(300_000_000, 20_000_000_000, 311_000_000):
        try:
            side = tile_side_for(
                budget_bytes=budget, floor=WORKED_FLOOR, **WORKED_EXAMPLE
            )
        except BudgetTooSmallError:
            continue
        sides.append(side)
        assert side < TILE_SIDE_BASE or side % TILE_SIDE_BASE == 0, (budget, side)
    # The fixture has to be able to fail: a range that produced only sides below
    # the base would satisfy the assertion without exercising the rounding.
    assert len(sides) > 40
    assert max(sides) > 1000
    assert any(side % TILE_SIDE_BASE == 0 and side > 0 for side in sides)


def _chunk_bytes(side, trailing_bytes):
    """Bytes in one inner chunk, mirroring `store._chunk_side`'s divisor rule.

    Args:
        side: Tile side.
        trailing_bytes: Bytes per grid cell for this array.

    Returns:
        Achieved chunk bytes.
    """
    for rows in range(1, side + 1):
        if side % rows == 0 and rows * side * trailing_bytes >= CHUNK_TARGET_BYTES:
            return rows * side * trailing_bytes
    return side * side * trailing_bytes


def test_the_achieved_chunk_bytes_are_in_band_for_the_worst_array_not_a_typical_one():
    """The base is validated on the array with the least data per cell.

    Expected values measured 2026-08-15 at M=12, C=2, k_beta=4, P_total=40. The
    per-cell widths span 1 byte (`status/point_outcome`) to 320
    (`warmstart/theta_unconstrained`, float64 x P_total), and the **widest** one
    is the worst case for the divisor search because it needs the fewest rows
    and therefore lands hardest on a coarse divisor set:

        side 338 (composite)   theta_unconstrained   18.3 MB   4.57x
        side 347 (PRIME)       theta_unconstrained   38.5 MB   9.63x
        side 272 (base 16)     beta / delta_ic        7.1 MB   1.78x

    **THE PUBLISHED DIVISOR NOTE WAS TAKEN ON `theta`** -- float32 x P_total,
    160 B/cell -- and reported 2.3x at side 338. The worst array is exactly
    twice as bad. That is why this asserts over every array rather than a
    representative one.

    **AND THE ARRAYS PARTITION.** Seven of them are narrow enough that a whole
    shard cannot reach the 4 MB target at all -- `point_outcome` is one byte per
    cell, so a 272-side shard is 74 kB -- and for those one chunk per shard is
    the right answer, not a fallback. Holding them to the band would fail for a
    correct reason.

    Bug this catches: a base validated on `theta` alone, or on a side that
    happens to factor well. Under a base that leaves prime sides reachable the
    worst array's chunk is ten times the target, which is read amplification on
    every tile and a decompression buffer to match.
    """
    widths = {
        "beta": 4 * 12 * 4,
        "delta_ic": 4 * 12 * 2,
        "ic_best": 8 * 2,
        "selected": 2 * 2,
        "n_valid": 2,
        "log_lik": 8 * 12,
        "iterations": 2 * 12,
        "theta": 4 * 40,
        "outcome": 1 * 12,
        "point_outcome": 1,
        "theta_unconstrained": 8 * 40,
    }
    side = tile_side_for(budget_bytes=10**9, floor=WORKED_FLOOR, **WORKED_EXAMPLE)
    assert side == 272

    reachable, capped = [], []
    for name, width in widths.items():
        got = _chunk_bytes(side, width)
        if side * side * width < CHUNK_TARGET_BYTES:
            capped.append(name)
            # One chunk per shard, which is the whole array.
            assert got == side * side * width, name
        else:
            reachable.append(name)
            assert CHUNK_TARGET_BYTES <= got <= 2 * CHUNK_TARGET_BYTES, (name, got)

    # BOTH HALVES ARE NON-EMPTY, or the partition is doing no work and one of
    # the two assertions above never ran.
    assert set(reachable) == {
        "beta",
        "delta_ic",
        "log_lik",
        "theta",
        "theta_unconstrained",
    }
    assert "point_outcome" in capped and "n_valid" in capped

    # ...and the base is what buys it: the unrounded side is prime.
    assert all(281 % d for d in range(2, 17))
    assert _chunk_bytes(281, 8 * 40) / CHUNK_TARGET_BYTES > 6
    # ...and worse still at Task 0's published 347, which is also prime.
    assert all(347 % d for d in range(2, 19))
    assert _chunk_bytes(347, 8 * 40) / CHUNK_TARGET_BYTES > 9


def test_the_solver_constant_comes_out_of_the_block_before_the_side_is_derived():
    """The tile is `B x per_series + solver_state`, so the constant is not free.

    Expected values determined independently: at `per_series = 8274` and
    `solver_state = 11 984`, a block of 40 000 B holds
    `(40 000 - 11 984) / 8274 = 3.39` series -- a side of 1 -- while the same
    block without the subtraction holds 4.83, a side of 2.

    **THE FIXTURE HAS TO BE THIS SMALL AND THAT IS THE FINDING.** At the worked
    example the constant is 11 984 B against a block of 656 030 000 -- 0.002% --
    so it moves the raw side by less than one and the rounding to a multiple of
    16 erases it entirely. **Deleting the subtraction there changes nothing
    observable**, which is (i8)'s first shape: the parameter under test sits at a
    fixed point. Measured: the mutation survived every other test in this module.

    Bug this catches: `tile_side(block, per_series)` -- the block spent entirely
    on series, with the live solver working set overcommitted on top. It is
    12 kB at production budgets and it is the whole block at the boundary, which
    is exactly where a user with a hard constraint operates.
    """
    per_series = resident_bytes_per_series(k_beta=4, p_max=4, n_time=630, n_models=12)
    constant = solver_state_bytes(
        SolverPlacement.PER_SERIES_LIVE, d=3, k_beta=4, p_max=4
    )
    assert (per_series, constant) == (8274, 11984)

    block = 40_000
    assert 1**2 <= (block - constant) / per_series < 2**2
    assert 2**2 <= block / per_series < 3**2

    budget = WORKED_FLOOR.peak_bytes + int(block / (1 - HEADROOM_FRACTION)) + 1
    assert block_bytes_for(budget_bytes=budget, floor=WORKED_FLOOR) >= block
    assert tile_side_for(budget_bytes=budget, floor=WORKED_FLOOR, **WORKED_EXAMPLE) == 1


def test_a_budget_derived_for_a_side_derives_that_side_back():
    """`budget_bytes_for_side` is `tile_side_for`'s inverse, exactly.

    **THE CALIBRATION CANNOT CHOOSE ITS OWN B, AND THIS IS WHY IT NEEDS AN
    INVERSE.** A run's batch is a tile, so `B = side**2`, and since Task 2 every
    derived side is a multiple of `TILE_SIDE_BASE`. So a calibration ladder is a
    ladder in **sides**, and to land on one the calibration has to ask what
    budget produces it -- inverting the same arithmetic rather than a copy of
    it, which is what keeps the measurement on the production derivation (j2).

    Expected values determined independently: the round trip is the property,
    and it is asserted at sides **below** the base (where `tile_side_for`
    passes the raw side through), **at** the base, and at four multiples of it
    including the published 272. A hand-written budget per side would be a
    second derivation of the thing under test.

    Bug this catches: an inverse that forgets the solver constant or the
    headroom, which lands one side low at small budgets -- exactly the boundary
    Task 2 found the solver constant mattering at -- and an inverse that rounds
    the wrong way, which lands a side high and makes the calibration measure a
    B it did not ask for. **Both are silent**: the ladder still runs, and every
    point is at the wrong B.
    """
    for side in (4, 8, 16, 32, 48, 64, 272):
        budget = budget_bytes_for_side(side=side, floor=WORKED_FLOOR, **WORKED_EXAMPLE)
        assert (
            tile_side_for(budget_bytes=budget, floor=WORKED_FLOOR, **WORKED_EXAMPLE)
            == side
        )
        # AND IT IS THE SMALLEST SUCH BUDGET, which is what makes the ladder's
        # cost minimal rather than merely correct: one byte less and the side
        # drops. Asserted only at and above the base, since below it the raw
        # side passes through and the step is one point rather than sixteen.
        if side >= TILE_SIDE_BASE:
            assert (
                tile_side_for(
                    budget_bytes=budget - 1, floor=WORKED_FLOOR, **WORKED_EXAMPLE
                )
                < side
            )


def test_a_side_no_budget_can_derive_is_refused_with_its_neighbours():
    """A non-multiple of the base at or above it is unreachable, and says so.

    **THE FAULT CLASS IS CONSTRUCTED HERE BECAUSE NOTHING ELSE BUILDS IT.**
    Every side the ladder and the round-trip test use is reachable by
    construction, so a guard against an unreachable one is untested however many
    tests run -- (i8)'s third shape, and the most comfortable of the three
    because the suite is green *and* the code is defensive.

    Expected values determined independently: `tile_side_for` rounds **down** to
    a multiple of `TILE_SIDE_BASE` = 16, so 20 rounds to 16 and no budget
    produces 20. The reachable neighbours are 16 and 32.

    Bug this catches: returning the nearest reachable side instead of refusing.
    The calibration would then measure a tile it did not ask for, and every
    ladder point would be silently at the wrong B -- which is exactly the
    failure `derived_side` is recorded to detect, one layer earlier.
    """
    with pytest.raises(ValueError, match="no budget derives a tile side of 20"):
        budget_bytes_for_side(side=20, floor=WORKED_FLOOR, **WORKED_EXAMPLE)
    with pytest.raises(ValueError, match="tile side must be positive"):
        budget_bytes_for_side(side=0, floor=WORKED_FLOOR, **WORKED_EXAMPLE)

    message = str(
        pytest.raises(
            ValueError,
            budget_bytes_for_side,
            side=20,
            floor=WORKED_FLOOR,
            **WORKED_EXAMPLE,
        ).value
    )
    assert "16" in message
    assert "32" in message


# --------------------------------------------------------------------------
# The published tile side, its preconditions and its dispute (Phase 2b Task 9)
# --------------------------------------------------------------------------


def test_the_published_side_equals_tile_side_for_its_own_arguments():
    """Exit criterion 16: the documented number is the derived number.

    **THIS IS A CONSISTENCY TEST AND NOT A CORRECTNESS TEST, AND THE
    DISTINCTION IS THE REASON THE HAND-DERIVATION ABOVE STAYS.** Its oracle is
    the implementation, so both sides move together and a wrong formula passes
    it. What it catches is the whole subject of this task: the next formula
    correction leaving four documents and five docstrings quoting a number
    nothing derives any more. `tile_side` has been wrong four times -- 171, 338,
    347, and whatever 8b makes of 272 -- and every one of those was found by a
    reader, never by a test.

    Expected values derived independently, at the published preconditions:

        available = 10**9 - 228 200 000                    771 800 000 B
        block     = int(available * (1 - 0.15))            656 030 000 B
        block - solver_state(11 984)                       656 018 016 B
        / 8274 B per series                                    79 285.5
        sqrt -> floor                                               281
        round down to a multiple of 16                          **272**

    and the per-point branch, whose per-series cost gains `n_time * k_beta * 8`
    = 20 160 B: 656 018 016 / 28 434 = 23 070.2, sqrt 151.9, floor 151, rounded
    **144**.

    Bug this catches: the record and the function disagreeing at all -- which is
    what every previous cascade was, discovered by hand months later.
    """
    record = PUBLISHED_TILE_SIDE
    # The two preconditions that are module constants rather than arguments.
    # Pinned as literals in the record, so this compares two derivations rather
    # than a value with itself.
    assert record.headroom_fraction == HEADROOM_FRACTION
    assert record.smooth_base == TILE_SIDE_BASE
    assert tile_side_for(**record.arguments) == record.shared == 272
    assert (
        tile_side_for(**record.arguments, per_point_design=True)
        == record.per_point
        == 144
    )


def test_the_published_arguments_are_exactly_what_tile_side_for_takes():
    """The precondition list binds against the signature, not against prose.

    **(g2), AND THE OMISSION IT CATCHES IS ALREADY IN THE TREE.** The handoff's
    precondition table names budget, floor, headroom, base and the model, and
    says nothing about `placement` or `threads` -- both parameters of
    `tile_side_for`, both defaulted, either of which moves the published number
    if its default moves. "338" came to be quoted with no backend attached by
    exactly this route: a precondition dropped from a list is invisible, because
    a list does not know what is missing from it.

    Expected values determined independently by reading the signature:
    `tile_side_for` takes eleven keyword parameters. The record supplies nine of
    them and deliberately varies two -- `per_point_design`, because it publishes
    both branches, and `per_series_bytes`, whose being `None` is the "analytic,
    not calibrated" precondition the dispute is about.

    Bug this catches: a parameter added with a default. The published number
    then depends on something no document names, and nothing fails.
    """
    parameters = inspect.signature(tile_side_for).parameters
    assert all(p.kind is p.KEYWORD_ONLY for p in parameters.values())
    assert set(PUBLISHED_TILE_SIDE.arguments) | {
        "per_point_design",
        "per_series_bytes",
    } == set(parameters)


def test_the_published_model_is_exactly_what_the_per_series_formula_takes():
    """The same binding one level down, where the model actually lands.

    `resident_bytes_per_series` is what `validation.py` calls with this model to
    build its per-point refusal, so the model has two consumers with different
    arithmetic and one description. A parameter added there moves the refusal's
    ratio as well as the published side.

    Expected values determined independently: the formula takes `k_beta`,
    `p_max`, `n_time`, `n_models` and `per_point_design`; the record supplies
    the first four and varies the fifth. It does **not** take `d` -- that is
    Task 0's correction, and `d` reaches the arithmetic only through the solver
    constant.

    Bug this catches: `d` creeping back into the per-series term, which is the
    F2/F4 defect and the one that made the published side carry a backend.
    """
    parameters = inspect.signature(resident_bytes_per_series).parameters
    assert set(PUBLISHED_TILE_SIDE.per_series_model) | {"per_point_design"} == set(
        parameters
    )
    assert "d" not in PUBLISHED_TILE_SIDE.per_series_model
    assert PUBLISHED_TILE_SIDE.per_series_model["n_time"] == 630


def test_the_disputes_hypothesis_sides_are_recomputed_and_not_transcribed():
    """The caveat is arithmetic, so it cannot outlive its subject silently.

    **(a6) IN A NEW REGISTER: A DESCRIPTION WHOSE SUBJECT HAS BEEN RESOLVED.**
    A number published with its dispute is honest; a dispute still attached
    after 8b settles it is a description of nothing, and unfalsifiable in
    exactly the way `Backend` was. Recomputing each hypothesis here means the
    field cannot be left behind: 8b deletes it in the edit that moves the value,
    or this test fails.

    Expected values derived independently, all at the published preconditions
    and the same 656 018 016 B block unless stated. The block is
    `(10**9 - 228 200 000) x 0.85 - 11 984`, and it does not depend on the
    per-series cost, so only the divisor moves between rows:

        published, 8274 B/series                      79 286.7 -> 281 -> **272**
        additive, 8274 + 542.8 = 8816.8               74 405.5 -> 272 -> **272**
        multiplicative, 8274 x 1468.8/926 = 13 124.0  49 986.0 -> 223 -> **208**
        headroom 36.955%, block 771 800 000 x 0.63045
                          - 11 984 = 486 566 720      58 806.7 -> 242 -> **240**

    ~~Under the 1900.9 reading these were 272 / 256 / 192 / 208; under 2410.0
    they were 272 / 256 / 160 / 176~~, struck 2026-08-22: the peak was
    re-measured at **1468.8 +/- 18.4** after `SVD_CHUNK_SERIES` bounded the fit
    phase's maximum, and the 2410.0 reading describes code that no longer runs.
    **The spread narrows, 160 to 208**, and the additive row now lands on the
    published side itself -- which is a narrowed spread, NOT agreement: that
    hypothesis is refuted by the other two fixtures, where the excess is 192.4
    and 1347.5 B/series against its 542.8.

    Bug this catches: a hypothesis side transcribed from a report rather than
    derived -- (a4)'s review-side register, which has fired three times here --
    and the whole record going stale after the next measurement.
    """
    dispute = PUBLISHED_TILE_SIDE.dispute
    assert dispute is not None, (
        "the per-series dispute is resolved, so this test and "
        "`test_the_dispute_states_its_direction_its_owner_and_its_spread` go "
        "with the field, in the same commit that moves the published value. "
        "Failing here rather than passing vacuously is the point: a test that "
        "skipped when the dispute went away would let the caveat outlive it"
    )
    for name, hypothesis in dispute.hypotheses.items():
        derived = tile_side_for(
            **PUBLISHED_TILE_SIDE.arguments,
            per_series_bytes=hypothesis.per_series_bytes,
        )
        assert derived == hypothesis.side, name

    # The headroom explanation moves a multiplier rather than a per-series term,
    # so it is not one of the hypotheses above. The field is DERIVED from the
    # two slopes on purpose -- it cannot drift from them -- so re-deriving it
    # here would be an oracle sharing its subject's derivation path (j). The
    # check that bites is the hand-computed value: criterion 7 asymptotically
    # needs the budget's slope to reach the peak's, `926 / (1 - h) >= 1468.8`,
    # so `h >= 1 - 926/1468.8 = 0.36955`. ~~0.51286 against 1900.9; 0.61577
    # against 2410.0~~, struck 2026-08-22 with the peak re-measurement.
    # **THE REQUIRED HEADROOM FELL AND THE SHIPPED ONE DID NOT MOVE**: 36.955%
    # against a shipped `headroom_fraction` of 15%, where it was 61.577%. That
    # gap closing by 25 points is what `SVD_CHUNK_SERIES` bought, and it is
    # still a gap -- the shipped fraction is a policy constant and this is a
    # measurement, so they are not the same kind of number and the second does
    # not license moving the first.
    assert dispute.headroom_fraction_required == pytest.approx(0.36955, abs=5e-6)


def test_the_dispute_states_its_direction_its_owner_and_its_spread():
    """What the sentence beside the number has to contain to be worth printing.

    A bare "disputed" is worse than nothing: it warns without letting a reader
    act. Three things make it actionable -- who owns what is left, how far apart
    the readings are, and **what the evidence actually says**.

    Expected values determined independently, from Task 8b's ladders:

      - the peak is 1468.8 B/series and the process still holds 1470.9 at the
        end of the tile, so the transient is `1468.8 - 1470.9 =` **-2.1** by
        subtraction -- **inside both fits' standard errors, 18.4 and 16.2, so
        it is zero to this instrument.** The transient this record carried at
        905.9 is gone: `SVD_CHUNK_SERIES` bounded the allocation that was it.
        **Every figure comes from the one arm** -- ten fine-chunked points at a
        constant 30 s -- because a peak from one arm minus a residency from
        another is a difference of two fixtures.
      - the ratio is `1468.8 / 926 = 1.586`, and it is **not** the ratio at the
        other two fixtures -- 1.794 at M = 6 and 1.076 at N = 240 -- which is
        the whole reason no term has moved.
      - the spread is 208 to 272, the extremes of the hypothesis sides.
      - the owner is nobody. 8a and 8b answered the question they were given.

    **THE SPREAD ASSERTION CHANGED ITS FORM AND NOT ITS CLAIM, AND THAT IS THE
    POINT OF THIS PARAGRAPH.** It used to require the ratios to sit more than
    **2x** apart. Post-bounding they sit **1.667x** apart -- 1.794 against 1.076
    -- so the old proxy fires, exactly as its own message said it would. **The
    claim underneath is that no SINGLE multiplier reproduces three fixtures, and
    that claim is stronger than ever**: the ratios disagree by **48.3% of their
    mean** while this instrument's precision at the measured fixture is
    **1.25%** (18.4 on 1468.8), so they are tens of standard errors apart. The
    threshold below is therefore derived from the INSTRUMENT -- ten times its
    precision -- rather than from the observed spread, which is what stops it
    being a number chosen to make the suite green.

    Bug this catches: the record still naming 8a as the owner and 1900.9 as the
    measurement after 8b, and a ratio published as though it were a constant of
    the code when three fixtures say it is not -- which is the multiplier
    correction (a7) forbids, arriving as a field rather than as an edit.
    """
    dispute = PUBLISHED_TILE_SIDE.dispute
    assert dispute is not None, "resolved -- see the sibling test's message"
    assert "8a" not in dispute.owner
    assert "unowned" in dispute.owner
    sides = [h.side for h in dispute.hypotheses.values()]
    assert min(sides) == 208
    assert max(sides) == PUBLISHED_TILE_SIDE.shared == 272
    assert dispute.transient_bytes_per_series == pytest.approx(-2.1)
    assert dispute.resident_at_tile_bytes_per_series == pytest.approx(1470.9)
    assert (
        dispute.measured_bytes_per_series - dispute.resident_at_tile_bytes_per_series
        == pytest.approx(dispute.transient_bytes_per_series, abs=0.05)
    )
    assert (
        round(dispute.measured_bytes_per_series / dispute.analytic_bytes_per_series, 3)
        == 1.586
    )
    ratios = dispute.peak_to_analytic_by_fixture
    assert set(ratios) == {"N=60 M=2", "N=60 M=6", "N=240 M=2"}
    assert min(ratios.values()) == 1.076
    assert max(ratios.values()) == 1.794
    spread = max(ratios.values()) - min(ratios.values())
    mean_ratio = sum(ratios.values()) / len(ratios)
    # **THE THRESHOLD IS THE INSTRUMENT'S, NOT THE DATA'S.** The measured
    # standard error is 18.4 on 1468.8 = 1.25%, so ratios produced by one
    # multiplier would agree to a few percent. Ten times that precision is the
    # bar; the observed disagreement is 48.3% of the mean, so this passes by a
    # factor of nearly four and would fail long before the fixtures converged.
    assert spread / mean_ratio > 0.125, (
        "the three fixtures' ratios must disagree by more than ten times this "
        "instrument's precision, because that disagreement is the evidence "
        "that a multiplicative correction is the wrong shape. If a later "
        "measurement brings them together, the multiplier hypothesis is back "
        "and this assertion is what says so. **It previously required a 2x "
        "ratio between the extremes and fired when the bounding narrowed them "
        "to 1.667x** -- the proxy went stale, the claim did not, and the "
        "replacement is derived from the measurement's own error rather than "
        "from the spread it is testing"
    )
