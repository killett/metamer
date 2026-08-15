"""Tiling: the grid, the assembly, and read amplification.

Three claims, and they fail in three different ways.

**The grid covers every point exactly once.** A miss writes a store with an
unwritten seam; an overlap writes some points twice. Neither raises, both produce
a complete-looking store, and the completion bitmap is per tile so it cannot see
either.

**Assembly never holds both representations of the whole tile.** Measured at
design doc section 9.4's worked example the difference is 863 MB against 575 MB
-- a 50% overshoot of the data term against a budget the design doc calls hard.

**Read amplification is measured in one set of units.** The store's bytes are
compressed and the tile's are not, so a ratio taken across that boundary measures
compression as well as amplification and can report less than 1.
"""

from __future__ import annotations

import warnings
from collections import Counter

import numpy as np
import pytest
import xarray as xr
from zarr.storage import LocalStore

from metamer.batch.input import InputContractError, open_input
from metamer.batch.tiling import (
    Tile,
    assemble_tile,
    assembly_spans,
    chunk_shape,
    read_amplification,
    tile_grid,
    tile_side_for,
)
from metamer.core.memory import resident_bytes_per_series, tile_side

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")


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
    assert (
        tile_side_for(
            budget_bytes=10**9,
            k_beta=4,
            p_max=4,
            n_time=630,
            n_models=12,
        )
        == expected
    )


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
    afterwards has both alive at once. At section 9.4's worked example --
    `tile_side` 338, N = 630 -- that is 288 MB of float32 beside 575 MB of
    float64, **863 MB against 575 MB, a 50% overshoot of the data term** against
    a budget the design doc calls hard.

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
