"""The completion bitmap, the write ordering, and the SIGTERM flush.

**THE STORE CANNOT WITNESS A SKIP.** Section 11.3 makes the fits deterministic,
so a run that ignores the bitmap and rewrites every tile produces byte-identical
contents to one that skips correctly -- the cancellation rule, at the level of a
whole store. Every test below that claims something was *not* refitted therefore
observes one of two things that are not constant across that comparison: the
raising stub engine, or a marker written into the store between the two runs.

**THE MARKER IS `NOT_ATTEMPTED` WRITTEN BACK OVER A TILE'S `/status/outcome`.**
It is the one value the write path cannot produce, so a region still carrying it
was left alone and a region without it was rewritten. That is what pins *which*
tiles a resume touched, where the report's own counters are the code under test
reporting on itself.
"""

from __future__ import annotations

import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import xarray as xr
import zarr

from metamer.batch.completion import (
    COMPLETE,
    completed_tiles,
    flush_on_sigterm,
    mark_complete,
    resume_tile_side,
    tile_index,
)
from metamer.batch.run import run
from metamer.batch.tiling import Tile
from metamer.batch.validation import ExitCode, ValidationError
from metamer.core.outcomes import Outcome
from tests.conftest import RaisingStubEngine, StubEngineCalled

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")

_CONFIG = """
data_uri = "{uri}"
variable = "sla"
signal_terms = ["constant", "trend", "annual"]
candidates = ["white", "white + matern12"]
criteria = ["aic", "hqic"]
memory_budget_gb = {budget}
objective = "ml"
"""

#: `tile_side = 1` at the fixture's geometry, so a 2x2 grid is four tiles and a
#: resume has something to skip. **A one-tile fixture cannot express anything in
#: this module.** Measured 2026-08-13: `resident_bytes_per_series` is **1322 B**
#: at `d=1, k_beta=4, p=3, N=60, M=2` -- `d` is the **widest** candidate's state
#: dimension, which is `white + matern12`'s 1 and not the 3 a reading of the
#: candidate list suggests -- and `floor(sqrt(2147/1322)) = 1`.
ONE_POINT_PER_TILE = 2e-6

#: `tile_side = 2` at the same geometry: `floor(sqrt(5368/1322)) = 2`.
TWO_POINTS_PER_TILE = 5e-6

NOT_ATTEMPTED = Outcome.NOT_ATTEMPTED.code


# --------------------------------------------------------------------------
# The bit index
# --------------------------------------------------------------------------


def test_the_bit_index_is_the_tile_position_and_not_its_transpose() -> None:
    """A tile's bit is `(y_start // side, x_start // side)`, in that order.

    Hand-derived at `side = 4`: the tile starting at row 8, column 4 is the
    third tile down and the second across, so its bit is `(2, 1)`.

    Catches a transposed index, which on a square tile grid writes a real bit
    for a real tile -- the wrong one -- and is invisible to every assertion made
    on the diagonal.
    """
    tile = Tile(y_start=8, y_stop=12, x_start=4, x_stop=8)

    assert tile_index(tile, 4) == (2, 1)


def test_a_tile_not_aligned_to_the_grid_is_refused() -> None:
    """Only a tile `tile_grid` produced has a bit.

    `tiling.assembly_spans` builds `Tile` objects for chunk-aligned sub-spans of
    one tile; they are the same type and are not grid tiles. A sub-span starting
    at row 2 of a 4-point grid is not the start of any tile.

    Catches a span tile reaching the bitmap, where `2 // 4 == 0` would set the
    bit of the tile that merely *contains* it -- marking a whole tile complete
    from a fraction of its data.
    """
    span = Tile(y_start=2, y_stop=4, x_start=0, x_stop=4)

    with pytest.raises(ValueError, match="not the start of a tile"):
        tile_index(span, 4)


# --------------------------------------------------------------------------
# The SIGTERM handler
# --------------------------------------------------------------------------


def test_the_handler_records_the_signal_rather_than_raising() -> None:
    """SIGTERM inside the guarded block sets a flag and nothing else.

    **A handler that raised would land its exception in the one window this
    task exists to protect** -- between a tile's data write and its bit -- and
    would do it at a point no test can choose. The flag is read between tiles
    instead.

    Catches a handler that raises (`KeyboardInterrupt` idiom), and a guard that
    reports `received` before any signal arrived.
    """
    with flush_on_sigterm() as termination:
        assert termination.armed
        assert not termination.received
        assert signal.getsignal(signal.SIGTERM) is not signal.SIG_DFL

        signal.raise_signal(signal.SIGTERM)

        assert termination.received


def test_the_previous_handler_is_restored_on_the_way_out() -> None:
    """The handler does not outlive the run that installed it.

    Catches a handler left installed, which makes every later SIGTERM in the
    same process land in a run that has finished -- process state set by one
    caller deciding another's behaviour.
    """
    before = signal.getsignal(signal.SIGTERM)

    with flush_on_sigterm():
        pass

    assert signal.getsignal(signal.SIGTERM) is before


def test_a_run_off_the_main_thread_declares_that_it_could_not_arm() -> None:
    """`signal.signal` is main-thread-only, and that regime is declared.

    Measured: off the main thread it raises `ValueError: signal only works in
    main thread of the main interpreter`. A library that let that escape would
    refuse a legitimate embedding; one that swallowed it would claim a
    protection it does not have.

    Catches both -- the escape, and a silent `armed = True`.
    """
    observed: list[tuple[bool, bool]] = []

    def probe() -> None:
        with flush_on_sigterm() as termination:
            observed.append((termination.armed, termination.received))

    thread = threading.Thread(target=probe)
    thread.start()
    thread.join()

    assert observed == [(False, False)]


# --------------------------------------------------------------------------
# Reading and writing the bitmap
# --------------------------------------------------------------------------


def test_a_bit_is_read_back_from_the_store_and_not_from_memory(tmp_path: Path) -> None:
    """`mark_complete` writes the bit; `completed_tiles` reads what is on disk.

    Catches a bitmap held in memory for the run's duration, which reads
    correctly inside the process that set it and is empty in the process that
    resumes -- the defect a single-process test cannot see and the reason the
    read goes through the store every time.
    """
    root = zarr.open_group(str(tmp_path / "s.zarr"), mode="w")
    group = root.create_group("completion")
    group.create_array(
        "tiles", shape=(2, 3), chunks=(1, 1), dtype="uint8", fill_value=0
    )

    assert not completed_tiles(tmp_path / "s.zarr").any()

    mark_complete(tmp_path / "s.zarr", (1, 2))

    done = completed_tiles(tmp_path / "s.zarr")
    assert done.shape == (2, 3)
    assert done[1, 2]
    assert np.count_nonzero(done) == 1
    stored = _array(tmp_path / "s.zarr", "completion", "tiles")
    assert int(np.asarray(stored[:])[1, 2]) == COMPLETE


# --------------------------------------------------------------------------
# Fixtures: a real store with four tiles
# --------------------------------------------------------------------------


def _input(directory: Path, *, n_y: int = 2, n_x: int = 2, n_time: int = 60) -> str:
    """A real zarr input of white noise.

    Args:
        directory: Destination directory.
        n_y: Grid rows.
        n_x: Grid columns.
        n_time: Series length.

    Returns:
        The store URI.
    """
    rng = np.random.default_rng(0)
    values = rng.standard_normal((n_time, n_y, n_x)).astype("float32")
    origin = np.datetime64("2000-01-01")
    axis = np.array([origin + np.timedelta64(31 * i, "D") for i in range(n_time)])
    name = f"in-{n_y}x{n_x}.zarr"
    xr.Dataset(
        {"sla": (("time", "y", "x"), values)},
        coords={
            "time": axis,
            "y": np.arange(n_y, dtype="float64"),
            "x": np.arange(n_x, dtype="float64"),
        },
    ).to_zarr(directory / name)
    return str(directory / name)


def _config(directory: Path, uri: str, *, budget: float, name: str = "c.toml") -> Path:
    """Write a run configuration.

    Args:
        directory: Destination directory.
        uri: The input store.
        budget: `memory_budget_gb`, which is what sets the tile side.
        name: File name, so one directory can hold several.

    Returns:
        The config path.
    """
    path = directory / name
    path.write_text(_CONFIG.format(uri=uri, budget=budget))
    return path


def _array(store: Path, group: str, name: str) -> zarr.Array[Any]:
    """Open one array of a store, narrowed for the type checker.

    Args:
        store: The store.
        group: Group name.
        name: Array name.

    Returns:
        The array, opened for writing.
    """
    holder = zarr.open_group(str(store), mode="r+")[group]
    assert isinstance(holder, zarr.Group)
    array = holder[name]
    assert isinstance(array, zarr.Array)
    return array


def _clear_bit(store: Path, index: tuple[int, int]) -> None:
    """Mark one tile outstanding again.

    Args:
        store: The store.
        index: `(ty, tx)`.
    """
    _array(store, "completion", "tiles")[index] = np.uint8(0)


def _outcome(store: Path) -> np.ndarray:
    """Read `/status/outcome` as a plain array.

    Args:
        store: The store to read.

    Returns:
        Shape `(n_y, n_x, m)`.
    """
    return np.asarray(xr.open_zarr(store, group="status")["outcome"].values)


def _blank(store: Path) -> None:
    """Write `NOT_ATTEMPTED` back over every point's status.

    **This is the marker that makes a skip observable.** The fits are
    deterministic, so a resumed store and a rewritten one are byte-identical and
    no comparison between them can see whether a tile was skipped. A status of
    `NOT_ATTEMPTED` is a value the write path cannot produce, so afterwards a
    region carrying it was left alone and a region without it was rewritten.

    The store is deliberately left inconsistent by this (finite values beside a
    non-`OK` status); nothing reads it again except these tests.

    Args:
        store: The store to mark.
    """
    _array(store, "status", "outcome")[:] = np.uint8(NOT_ATTEMPTED)


@pytest.fixture(scope="module")
def four_tiles(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """A complete store of four one-point tiles, and the config that made it.

    The fits cost seconds per series, so the whole module shares one run and
    each test copies the store it needs.

    Args:
        tmp_path_factory: pytest's session-scoped directory factory.

    Returns:
        `(config path, store path)`.
    """
    base = tmp_path_factory.mktemp("completion")
    config = _config(base, _input(base), budget=ONE_POINT_PER_TILE)
    store = base / "done.zarr"
    report = run(config, store)
    # A FIXTURE GUARD, NOT AN ASSERTION ABOUT THE PRODUCT: one tile would make
    # every skip, index and resume assertion below vacuous.
    assert report.tile_side == 1
    assert report.tiles_total == 4
    assert report.tiles_written == 4
    return config, store


@pytest.fixture
def resumable(four_tiles: tuple[Path, Path], tmp_path: Path) -> tuple[Path, Path]:
    """A private copy of the complete store.

    Args:
        four_tiles: The module's completed run.
        tmp_path: This test's directory.

    Returns:
        `(config path, store path)`.
    """
    config, store = four_tiles
    copy = tmp_path / "out.zarr"
    shutil.copytree(store, copy)
    return config, copy


# --------------------------------------------------------------------------
# Write ordering
# --------------------------------------------------------------------------


@pytest.mark.slow
def test_a_fault_between_the_two_writes_leaves_the_bit_unset(tmp_path: Path) -> None:
    """Data then bitmap, always -- shown by a fault, never by timing.

    The hook fires between a tile's data write and its bit. It returns for the
    first tile and raises for the second, so one run carries both the negative
    and its control **through the same injection point**: tile (0,0) has data
    and a bit, tile (0,1) has data and no bit.

    The oracle is `/status/outcome`, not the bitmap -- reading the bitmap to
    check the data was written shares its whole derivation with the thing under
    test.

    Catches the bitmap being written first, or written from anywhere other than
    the write's return: either would mark tile (0,1) complete over a region an
    interruption left partly written.
    """
    config = _config(tmp_path, _input(tmp_path), budget=ONE_POINT_PER_TILE)
    store = tmp_path / "out.zarr"
    seen: list[Tile] = []

    def hook(tile: Tile) -> None:
        seen.append(tile)
        if len(seen) == 2:
            raise RuntimeError("preempted between the two writes")

    with pytest.raises(RuntimeError, match="preempted"):
        run(config, store, on_tile_written=hook)

    done = completed_tiles(store)
    assert done[0, 0]
    assert not done[0, 1]
    assert not done[1, 0]
    assert not done[1, 1]

    outcome = _outcome(store)
    assert np.all(outcome[0, 0] != NOT_ATTEMPTED)
    assert np.all(outcome[0, 1] != NOT_ATTEMPTED)
    assert np.all(outcome[1, 0] == NOT_ATTEMPTED)
    assert np.all(outcome[1, 1] == NOT_ATTEMPTED)


# --------------------------------------------------------------------------
# Resume
# --------------------------------------------------------------------------


@pytest.mark.slow
def test_a_resume_rewrites_exactly_the_tile_whose_bit_is_clear(
    resumable: tuple[Path, Path],
) -> None:
    """The bitmap decides what is refitted, and the index decides which tile.

    Every point's status is set back to `NOT_ATTEMPTED` and **one off-diagonal
    bit** is cleared. The tile grid here is square, so a transposed index picks
    a real bit for a real tile -- the wrong one -- and only an off-diagonal
    fixture can see it (pre-flight (i7)).

    Catches: a run that ignores the bitmap (all four regions rewritten), a run
    that skips everything (none rewritten), and `(tx, ty)` (tile (1,0)
    rewritten instead of (0,1)).
    """
    config, store = resumable
    _blank(store)
    _clear_bit(store, (0, 1))

    report = run(config, store)

    assert report.tiles_written == 1
    assert report.tiles_skipped == 3
    outcome = _outcome(store)
    assert np.all(outcome[0, 1] != NOT_ATTEMPTED)
    assert np.all(outcome[0, 0] == NOT_ATTEMPTED)
    assert np.all(outcome[1, 0] == NOT_ATTEMPTED)
    assert np.all(outcome[1, 1] == NOT_ATTEMPTED)
    assert completed_tiles(store).all()


def test_a_resume_of_a_complete_store_runs_no_fit(
    resumable: tuple[Path, Path], raising_engine: RaisingStubEngine
) -> None:
    """Nothing outstanding, so nothing reaches the engine.

    The claim is a pure negative, so it is proved by a stub that raises rather
    than by a timing. Its control is the test below, which reaches the same
    engine through the same seam once one bit is clear.

    Catches a run that rewrites every tile on every invocation -- which is what
    the runner did before this task, and which no comparison of the store's
    contents can detect, because the fits are deterministic.
    """
    config, store = resumable

    report = run(config, store, engine=raising_engine)

    assert report.tiles_written == 0
    assert report.tiles_skipped == 4
    assert raising_engine.calls == []


def test_the_same_resume_reaches_the_engine_for_an_outstanding_tile(
    resumable: tuple[Path, Path], raising_engine: RaisingStubEngine
) -> None:
    """The control for the negative above: one clear bit does reach the engine.

    Without it, "no fit ran" passes equally well when the seam is disconnected,
    when the tiling loop never runs, and when the store cannot be opened.

    Catches an `engine=` that stops being threaded to `fit`, and a resume that
    skips every tile regardless of its bit.
    """
    config, store = resumable
    _clear_bit(store, (1, 0))

    with pytest.raises(StubEngineCalled):
        run(config, store, engine=raising_engine)

    assert raising_engine.calls != []


# --------------------------------------------------------------------------
# SIGTERM
# --------------------------------------------------------------------------


@pytest.mark.slow
def test_sigterm_finishes_the_current_tile_and_the_resume_takes_the_rest(
    tmp_path: Path,
) -> None:
    """Preemption is just resumption, and it costs at most nothing.

    SIGTERM is delivered **inside the window between the data write and the
    bit** -- the worst available moment, and the one a timing-based test cannot
    choose. The run must still write that tile's bit and only then stop.

    Catches a handler that raises (the tile would be lost with its data on
    disk and no bit), and a loop that ignores the flag (all four tiles written
    and the preemption deadline missed).
    """
    config = _config(tmp_path, _input(tmp_path), budget=ONE_POINT_PER_TILE)
    store = tmp_path / "out.zarr"

    def hook(tile: Tile) -> None:
        # The assertion comes first deliberately: if the handler is not
        # installed, this fails the test rather than killing the session.
        assert signal.getsignal(signal.SIGTERM) is not signal.SIG_DFL
        signal.raise_signal(signal.SIGTERM)

    report = run(config, store, on_tile_written=hook)

    assert report.sigterm_armed
    assert report.interrupted
    assert report.tiles_written == 1
    assert report.tiles_skipped == 0
    done = completed_tiles(store)
    assert done[0, 0]
    assert np.count_nonzero(done) == 1
    assert np.all(_outcome(store)[0, 0] != NOT_ATTEMPTED)

    again = run(config, store)

    assert again.tiles_skipped == 1
    assert again.tiles_written == 3
    assert not again.interrupted
    assert completed_tiles(store).all()
    assert np.all(_outcome(store) != NOT_ATTEMPTED)


@pytest.mark.slow
def test_a_signal_on_the_last_tile_leaves_a_finished_run_finished(
    tmp_path: Path,
) -> None:
    """`interrupted` is read off the tile counts, never off the signal.

    A one-tile grid takes the signal in the same window as the test above, and
    there is nothing outstanding afterwards. **A run that wrote every tile
    finished**, whatever else happened to the process, so the store is complete
    and the report says so.

    Catches `interrupted = termination.received`, which reports an abort and
    exits 2 over a finished store -- telling a resuming script to resume a run
    with nothing left to do, and, at scale, doing it on every preemption that
    happens to land near the end.
    """
    config = _config(
        tmp_path, _input(tmp_path, n_y=1, n_x=1), budget=ONE_POINT_PER_TILE
    )
    store = tmp_path / "out.zarr"

    def hook(tile: Tile) -> None:
        signal.raise_signal(signal.SIGTERM)

    report = run(config, store, on_tile_written=hook)

    assert report.tiles_total == 1
    assert report.tiles_written == 1
    assert not report.interrupted
    assert completed_tiles(store).all()


@pytest.mark.slow
def test_a_preempted_command_exits_aborted_early_and_resumes(tmp_path: Path) -> None:
    """The whole thing across a process boundary, with a real signal.

    A signal handler, an exit code and a store handed from one process to
    another are all things an in-process test cannot reach -- pre-flight (k).
    The signal is sent once the store reports its first completed tile, so the
    run is genuinely mid-loop rather than merely started.

    Exit code 2 is design doc 14.3's "aborted early -- resumable", which is
    exactly what a preempted run is. Catches an exit of 0 (which would tell a
    resuming script the store is finished) and death by unhandled signal (-15,
    which would leave the tile in flight unfinished).
    """
    config = _config(tmp_path, _input(tmp_path), budget=ONE_POINT_PER_TILE)
    store = tmp_path / "out.zarr"
    command = [sys.executable, "-m", "metamer", str(config), str(store)]
    child = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    deadline = time.monotonic() + 120.0
    while time.monotonic() < deadline:
        # A store under construction has a directory before it has a bitmap, so
        # the poll tolerates the refusal rather than reading the directory as
        # truth.
        try:
            if store.exists() and completed_tiles(store).any():
                break
        except ValidationError:
            pass
        if child.poll() is not None:
            break
        time.sleep(0.02)
    child.send_signal(signal.SIGTERM)
    child.communicate(timeout=120)

    assert child.returncode == ExitCode.ABORTED_EARLY
    partial = completed_tiles(store)
    assert partial.any()
    assert not partial.all()

    finished = subprocess.run(command, capture_output=True, check=False)

    assert finished.returncode == ExitCode.OK
    assert completed_tiles(store).all()
    assert np.all(_outcome(store) != NOT_ATTEMPTED)


# --------------------------------------------------------------------------
# The tile side a resume must use
# --------------------------------------------------------------------------


def test_a_bigger_budget_adopts_the_stored_tile_side(
    resumable: tuple[Path, Path], raising_engine: RaisingStubEngine
) -> None:
    """The shards are fixed at creation, so the store's side wins.

    A resume on a machine with more RAM is design doc 15.5's headline workflow,
    so a budget change must not be refused. It must also not re-tile: at a side
    of 77 the four bits of this store would index regions no tile covers.

    Catches a resume that re-derives the tiling from its own budget -- every
    array the right shape, some points never written, others written twice, and
    the bitmap fully set at the end.
    """
    config, store = resumable

    report = run(config, store, memory_budget_gb=0.01, engine=raising_engine)

    assert report.tile_side == 1
    assert report.tiles_total == 4
    assert report.tiles_skipped == 4
    assert raising_engine.calls == []


@pytest.mark.slow
def test_a_budget_too_small_for_the_stored_tile_is_refused(tmp_path: Path) -> None:
    """The one direction that cannot be adopted, refused with both numbers.

    A stored tile of 2 points a side cannot be written under a budget that holds
    1, and writing sub-tile regions instead would make every write a
    read-modify-write of a shard.

    The assertion reads a phrase the **diagnosis** owns, not one the input
    supplies: a message quoting the store path would match whatever error fired.

    Catches silently honouring the smaller budget, and silently exceeding the
    requested one.
    """
    uri = _input(tmp_path, n_y=1, n_x=1)
    store = tmp_path / "out.zarr"
    run(_config(tmp_path, uri, budget=TWO_POINTS_PER_TILE), store)

    with pytest.raises(ValidationError, match="shards are fixed at creation"):
        run(
            _config(tmp_path, uri, budget=ONE_POINT_PER_TILE, name="small.toml"),
            store,
        )


def test_a_bitmap_that_does_not_describe_this_grid_is_refused(
    resumable: tuple[Path, Path],
) -> None:
    """A bit is a region, and the region depends on the grid as well as the side.

    **RE-POINTED AT TASK 11, AND THE REASON IS THE INTERESTING PART.** This test
    used to reach the guard through `run()` with the same configuration pointed
    at a 4x2 input. It cannot any more: a grid change moves `geometry_hash`,
    which is fit-relevant, so `resume.check_resume` refuses on `fit_hash` first
    and this refusal is **unreachable through a configuration** -- the
    defence-in-depth outcome from the mutation taxonomy, not a dead guard.

    The two guards are cross-commented in the source so a later simplification
    sees both, and the test now calls this one directly, which is what remains
    reachable: a store whose bitmap does not describe its own grid, from a
    truncated copy or a foreign writer.

    Catches indexing a smaller bitmap with a bigger grid, where half the tiles
    raise nothing and simply reuse another tile's bit.
    """
    _config_path, store = resumable

    with pytest.raises(ValidationError, match="completion bitmap"):
        resume_tile_side(store, derived_side=1, grid=(4, 2))


def test_a_store_without_a_bitmap_is_refused(tmp_path: Path) -> None:
    """An absent bitmap is not "nothing is complete".

    Catches a resume that reads a missing array as an empty one and refits a
    finished store, and a `KeyError` escaping as an unhandled exception -- exit
    code 1, which the taxonomy already spends on "completed with failures".
    """
    zarr.open_group(str(tmp_path / "bare.zarr"), mode="w")

    with pytest.raises(ValidationError, match="no /completion/tiles"):
        completed_tiles(tmp_path / "bare.zarr")

    with pytest.raises(ValidationError, match="no /completion/tiles"):
        mark_complete(tmp_path / "bare.zarr", (0, 0))
