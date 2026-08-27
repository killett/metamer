"""The two-pass driver: decimate, fit cold, barrier, fit warm.

**EVERY STORE HERE COMES FROM A REAL RUN.** The subject is the wiring between
two `run` calls and a barrier, so a hand-built store would test the fixture.

**THE CANDIDATE SET IS TWO THROUGHOUT AND THE GRID IS NOT A MULTIPLE OF THE
STRIDE.** Two candidates because the warm-start key is
`(fit_hash, candidate spec_hash)` and a per-point search cannot be told from a
per-candidate one over a single candidate; a grid that the stride does not
divide because otherwise no fine point exists with no coarse point below or to
the right of it.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pytest
import xarray as xr
import zarr

from metamer.batch.decimate import pass1_store_path
from metamer.batch.run import run
from metamer.batch.twopass import run_two_pass
from metamer.batch.validation import ExitCode, ValidationError
from metamer.core.optimize import InitRung
from tests.conftest import STUB_FLOOR_PEAK

#: Two budgets that derive DIFFERENT tile sides -- 6 and 10 -- for this
#: module's model, both giving MORE THAN ONE tile on an 11 x 7 grid.
#:
#: **BOTH HALVES ARE PRECONDITIONS AND BOTH ARE ASSERTED IN THE TEST.** Equal
#: sides would make the bitwise comparison a statement about two identical
#: traversals; a single tile per budget would make it a statement about no
#: traversal at all. Measured against the session's stubbed floor rather than
#: derived: `tile_side_for` is on the path under test, so computing the budgets
#: from its inverse would let one formula change move both sides of the
#: comparison.
_SIDE_6_BUDGET = 0.0010359
_SIDE_10_BUDGET = 0.0010764

#: The budget that puts the 6 x 6 COARSE grid in more than one tile, from
#: `tests/test_decimate.py` where it is derived and explained. A single-tile
#: pass 1 is complete after one write and cannot be interrupted usefully.
_MULTI_TILE_BUDGET = 0.0010159

_CONFIG = """
data_uri = "{uri}"
variable = "sla"
signal_terms = ["constant", "trend"]
candidates = ["white", "white + matern12"]
criteria = ["aic"]
memory_budget_gb = 1.0

[warm_start]
coarse_stride = 2
spiral_bound = {bound}
"""


def _input(
    tmp_path: Path,
    name: str = "in.zarr",
    n_y: int = 7,
    n_x: int = 6,
    land: tuple[slice, slice] | None = None,
) -> str:
    """A real zarr input, optionally with a block of all-NaN series ("land").

    **THE DEFAULT IS THE SMALLEST GRID THAT IS STILL AWKWARD**, and each test
    that needs a larger one asks for it and says why. 7 x 6 is not square, 7 is
    not a multiple of the stride, and at tile side 6 it is two tiles -- so the
    tests that need a traversal have one. Every test here fits real series, and
    the full-grid pass costs `n_y * n_x * 2` fits; sizing every fixture for the
    strictest test cost 15.5 minutes of the suite.
    """
    origin = np.datetime64("2000-01-01")
    values = np.random.default_rng(3).standard_normal((24, n_y, n_x)).astype("float32")
    if land is not None:
        values[:, land[0], land[1]] = np.nan
    dataset = xr.Dataset(
        {"sla": (("time", "y", "x"), values)},
        coords={
            "time": np.array([origin + np.timedelta64(31 * i, "D") for i in range(24)]),
            "y": 100.0 + 2.5 * np.arange(n_y),
            "x": 500.0 - 0.5 * np.arange(n_x),
        },
    )
    path = tmp_path / name
    dataset.to_zarr(path)
    return str(path)


def _config(
    tmp_path: Path,
    uri: str,
    *,
    name: str = "c.toml",
    bound: int = 4,
    extra: str = "",
) -> Path:
    path = tmp_path / name
    path.write_text(_CONFIG.format(uri=uri, bound=bound) + extra)
    return path


def _array_of(
    store: Path | str,
    group: str,
    name: str,
    *,
    mode: Literal["r", "r+"] = "r",
) -> Any:
    """Open one array of a store, narrowed for the type checker.

    Args:
        store: The store.
        group: Group name.
        name: Array name within it.
        mode: zarr open mode.

    Returns:
        The array.
    """
    holder = zarr.open_group(str(store), mode=mode)[group]
    assert isinstance(holder, zarr.Group)
    array = holder[name]
    assert isinstance(array, zarr.Array)
    return array


def _group(path: Path | str, group: str, name: str) -> np.ndarray:
    """Read one array of a store whole, as a numpy array."""
    return np.asarray(_array_of(path, group, name)[:])


def _attrs(path: Path | str) -> dict[str, Any]:
    """The root provenance attrs of a store."""
    return dict(zarr.open_group(str(path), mode="r").attrs)


# --------------------------------------------------------------------------
# §11.3: the budget, the tiling and the traversal do not reach `θ̂`
# --------------------------------------------------------------------------


def test_two_budgets_give_the_same_signal_bit_for_bit(tmp_path):
    """A two-pass run at two memory budgets writes identical `/signal/`.

    Behaviour under test: §11.3's guarantee **on the path that could break
    it**. Until this task there was no warm-start path under that guarantee at
    all; now which coarse fit a point starts from is an extra input to its fit,
    and the whole question is whether that input is a function of the dataset or
    of the tiling.

    Expected values determined independently: the two stores are compared with
    each other, and the preconditions that make the comparison mean anything
    are asserted rather than assumed -- **different tile sides, and more than
    one tile each**.

    Bug this catches: a source map built from the tile's own extent instead of
    the full grid with a `region`. Every index is still in range and every warm
    start still finite; points near a tile boundary simply start from a
    different coarse fit, and `theta_hat` moves with `--memory-budget`. That is
    the single most likely way to lose §11.3, which is why `source_map` takes
    the full `shape` and a `region` rather than a tile.

    **`/signal/beta` rather than an outcome count**: a comparison of statuses
    would agree between two runs that converged to different optima.
    """
    # 11 x 7 EXPLICITLY: this is the one test that needs more than one tile at
    # BOTH budgets, so an axis must exceed the larger side of 10. 11 is odd, so
    # the stride still does not divide the grid.
    uri = _input(tmp_path, n_y=11, n_x=7)
    config = _config(tmp_path, uri)

    first = run_two_pass(config, tmp_path / "a.zarr", memory_budget_gb=_SIDE_6_BUDGET)
    second = run_two_pass(config, tmp_path / "b.zarr", memory_budget_gb=_SIDE_10_BUDGET)

    assert first.pass2 is not None and second.pass2 is not None
    assert first.pass2.tile_side != second.pass2.tile_side, (
        "equal sides would make this a comparison of two identical traversals"
    )
    assert first.pass2.tiles_total > 1 and second.pass2.tiles_total > 1, (
        "a single tile per budget is no traversal at all"
    )
    assert first.pass2.warm_start is not None
    assert first.pass2.warm_start.warm_started > 0, "a cold run would pass vacuously"

    for name in ("beta", "beta_err"):
        assert np.array_equal(
            _group(tmp_path / "a.zarr", "signal", name),
            _group(tmp_path / "b.zarr", "signal", name),
            equal_nan=True,
        ), name
    assert np.array_equal(
        _group(tmp_path / "a.zarr", "noise", "theta"),
        _group(tmp_path / "b.zarr", "noise", "theta"),
        equal_nan=True,
    )


def test_a_killed_and_resumed_pass_two_is_bitwise_identical(tmp_path):
    """Interrupting pass 2 and resuming reproduces the uninterrupted store.

    Behaviour under test: 2a's exit criterion 1, which 2c must not break. A
    resumed pass 2 rebuilds its source map from pass 1's store and its own
    config, so the question is whether that reconstruction is exact -- a warm
    start that depended on which tiles this process happened to fit would make
    a resumed store differ from an uninterrupted one.

    Expected values determined independently: the reference store is produced
    by a separate uninterrupted two-pass run over the same input and config.

    Bug this catches: any per-run state leaking into the source map -- a
    counter, an accumulated `coarse_ok`, a cache keyed on tile order. It also
    catches the resume path skipping the barrier and warm-starting from a store
    it has not re-checked.

    **The precondition is asserted**: the interrupted run must leave tiles
    outstanding, or the "resume" is a no-op and the comparison is between two
    complete runs.
    """
    uri = _input(tmp_path)
    config = _config(tmp_path, uri)

    reference = run_two_pass(
        config, tmp_path / "whole.zarr", memory_budget_gb=_SIDE_6_BUDGET
    )
    assert reference.pass2 is not None and not reference.interrupted

    killed = run_two_pass(
        config,
        tmp_path / "part.zarr",
        memory_budget_gb=_SIDE_6_BUDGET,
        on_tile_written=lambda _tile: os.kill(os.getpid(), signal.SIGTERM),
    )
    assert killed.pass2 is not None
    assert killed.pass2.interrupted, "an uninterrupted run makes the resume a no-op"

    resumed = run_two_pass(
        config, tmp_path / "part.zarr", memory_budget_gb=_SIDE_6_BUDGET
    )
    assert resumed.pass2 is not None
    assert not resumed.interrupted
    assert resumed.pass2.tiles_skipped > 0, "the resume must have skipped something"

    for group, name in (
        ("signal", "beta"),
        ("noise", "theta"),
        ("warmstart", "theta_unconstrained"),
        ("primitives", "log_lik"),
    ):
        assert np.array_equal(
            _group(tmp_path / "whole.zarr", group, name),
            _group(tmp_path / "part.zarr", group, name),
            equal_nan=True,
        ), f"{group}/{name}"


# --------------------------------------------------------------------------
# Warm-starting on, and warm-starting off
# --------------------------------------------------------------------------


def test_the_warm_path_runs_and_says_so_in_three_places(tmp_path):
    """A two-pass run warm-starts, records that it did, and pass 1 does not.

    Behaviour under test: the positive control every other test in this module
    needs, and the three records that make the warm path observable at all --
    the init rung on every fitted cell, the run's aggregate, and the store's
    `warm_start_used` attr.

    Expected values determined independently: the cell count is the full grid
    times the candidate count, computed here from the fixture's dimensions.
    `InitRung.WARM_START` is recorded by `optimize_series` when a warm start is
    honoured, which is a different derivation from the source map's own
    `valid`.

    Bug this catches: a driver that runs both passes and never wires the warm
    starts through -- pass 2 would fit cold, every store would look right, and
    the only symptom would be that the mechanism does not pay. It also catches
    `warm_start_used` being read off `config.warm_start.enabled`, which would
    write `true` for pass 1's own COLD store under this very config.

    **`radius_histogram[0]` is D12's lattice**, asserted rather than left to be
    discovered as a spatial signal: a coarse point's nearest valid source is
    itself, so it appears at distance 0, and a spiral that started at radius 1
    would source every coarse point from a neighbour instead.

    **THE RUNG COUNT EQUALS `warm_started` HERE AND DOES NOT IN GENERAL.** Every
    series in this fixture is fittable, so every cell the map offered a source
    to reached the optimizer with it. Where a series is refused by the design
    precheck the optimizer never runs and no warm rung is recorded although the
    map offered one -- see
    `test_an_exhausted_region_takes_the_ladder_and_is_counted`, which is where
    that was measured.
    """
    uri = _input(tmp_path)
    report = run_two_pass(_config(tmp_path, uri), tmp_path / "out.zarr")

    assert report.pass1 is not None and report.pass2 is not None
    warm = report.pass2.warm_start
    assert warm is not None
    assert warm.cells == 7 * 6 * 2
    assert warm.warm_started + warm.exhausted == warm.cells
    assert warm.warm_started > 0
    assert warm.radius_histogram[0] > 0, "D12: a coarse point sources itself"

    assert report.pass2.init_rungs.get(str(InitRung.WARM_START), 0) == warm.warm_started
    assert str(InitRung.WARM_START) not in report.pass1.init_rungs, (
        "pass 1 is COLD; a warm rung there means it started from something"
    )
    assert report.pass1.warm_start is None

    assert _attrs(report.store_path)["warm_start_used"] is True
    assert report.pass1_path is not None
    assert _attrs(report.pass1_path)["warm_start_used"] is False


def test_warm_starting_disabled_is_one_cold_pass_and_leaves_no_residue(tmp_path):
    """`enabled = false` reproduces a plain `run`, and writes no coarse store.

    Behaviour under test: the switch §11.2 requires, exercised end to end. A
    user who turns warm-starting off must get the store they would have got
    from `run` -- not a store that happens to agree, and not one with a coarse
    directory beside it.

    Expected values determined independently: the reference is a direct `run`
    over the same config and input, which is a different code path through the
    same function.

    Bug this catches: the two-pass path leaving a residue when it is switched
    off -- a pass-1 store written and then ignored, an `x0` of all-NaN passed
    with an all-false validity array, or `warm_start_used` recorded true
    because the driver was asked for two passes.

    **The discriminator is the init rung, not `theta_hat`.** Warm and cold
    `theta_hat` need not differ -- whether they do is what §11.2's audit exists
    to measure -- so a test demanding a difference would fail on a well-behaved
    fixture and pass on a broken one. What cannot be faked is that no cell was
    started from a warm start.
    """
    uri = _input(tmp_path)
    config = _config(tmp_path, uri, extra="\nenabled = false\n")
    report = run_two_pass(config, tmp_path / "off.zarr")
    cold = run(_config(tmp_path, uri, name="plain.toml"), tmp_path / "cold.zarr")

    assert report.pass1 is None and report.pass1_seconds is None
    assert report.pass2 is not None
    assert report.pass2.warm_start is None
    assert not pass1_store_path(tmp_path / "off.zarr").exists(), (
        "a coarse store nobody asked for is a permanent artifact, not scratch"
    )
    assert _attrs(tmp_path / "off.zarr")["warm_start_used"] is False
    assert str(InitRung.WARM_START) not in report.pass2.init_rungs
    assert cold.init_rungs == report.pass2.init_rungs

    for group, name in (("signal", "beta"), ("noise", "theta")):
        assert np.array_equal(
            _group(tmp_path / "off.zarr", group, name),
            _group(tmp_path / "cold.zarr", group, name),
            equal_nan=True,
        ), f"{group}/{name}"


def test_an_exhausted_region_takes_the_ladder_and_is_counted(tmp_path):
    """Where every coarse source failed, the cells fall back and are counted.

    Behaviour under test: §11.3's fallback reaching the run's own accounting.
    A cell the spiral exhausts gets no warm start and takes the moment ladder,
    and the count of such cells is the reading that says how often the bound
    bit -- which is the whole of what a large land or ice region would look
    like in real altimetry.

    Expected values determined independently: the fixture is constructed so
    that exhaustion is forced rather than hoped for -- an all-NaN block of
    series, which cannot fit, with `spiral_bound = 1` so the search reaches two
    fine cells and cannot leave the block. The count is then required to be
    positive and strictly below the total, both of which are checked.

    Bug this catches: counting `warm_started` as every cell regardless of
    validity, which is what `sources.valid.size` instead of `.sum()` gives. The
    two agree exactly when nothing is ever exhausted, which is every other
    fixture in this module -- (a0)'s fifth register, a zero reading that is not
    evidence of absence.

    **AND THE TWO COUNTS ARE NOT EQUAL HERE, WHICH IS THE FINDING THIS FIXTURE
    PRODUCED.** An earlier version of this test asserted
    `WARM_START == warm_started` and read 147 against 182. **A valid warm start
    is not the same as a warm start USED**: a series the design precheck refuses
    never reaches the optimizer, so no warm rung is recorded even though the map
    offered it one -- and this fixture is full of such series by construction.
    The relation that holds is an INEQUALITY in one direction, and an exhausted
    cell can never record a warm rung. Both are asserted; the equality is
    asserted in `test_the_warm_path_runs_and_says_so_in_three_places`, whose
    fixture has no unfittable series.
    """
    # 10 x 9 with a 7 x 7 block of all-NaN series. At stride 2 and bound 1 the
    # search reaches two fine cells, so a point in the middle of the block has
    # no OK coarse source in range -- which is what makes exhaustion forced.
    uri = _input(tmp_path, n_y=10, n_x=9, land=(slice(2, 9), slice(2, 9)))
    report = run_two_pass(_config(tmp_path, uri, bound=1), tmp_path / "land.zarr")

    assert report.pass2 is not None
    warm = report.pass2.warm_start
    assert warm is not None
    assert warm.exhausted > 0, "the fixture must force exhaustion, not hope for it"
    assert warm.warm_started > 0, "and it must not exhaust everything"
    assert warm.warm_started + warm.exhausted == warm.cells

    rungs = report.pass2.init_rungs
    warmed = rungs.get(str(InitRung.WARM_START), 0)
    assert sum(rungs.values()) == warm.cells, "every cell records a rung"
    assert 0 < warmed <= warm.warm_started, (
        "a warm rung requires a valid source, but a valid source does not "
        "require the series to be fittable"
    )
    assert warm.cells - warmed >= warm.exhausted, (
        "every exhausted cell must be among those that did NOT warm-start"
    )


# --------------------------------------------------------------------------
# The barrier, and the exit path a preempted pass 1 must take
# --------------------------------------------------------------------------


def test_a_sigterm_during_pass_one_stops_before_the_barrier(tmp_path):
    """A preempted pass 1 returns no pass 2, rather than being refused.

    Behaviour under test: **the exit path.** Pass 1 honours SIGTERM and leaves
    tiles outstanding; calling the barrier on that store raises a layer-3
    `ValidationError`, whose exit code means the request was invalid. The truth
    is §14.3's exit 2 -- aborted early, resumable -- and the two send a user to
    entirely different places.

    Expected values determined independently: the outstanding tiles are read
    from pass 1's own report, and the barrier is then shown to refuse that
    store, so the test asserts what the driver did NOT do rather than only what
    it did.

    Bug this catches: a driver that runs the barrier unconditionally after
    pass 1. Every preempted two-pass run would then report a configuration
    error, and the advice in the message -- "resume pass 1 to completion" -- is
    what the user was already doing.

    **The multi-tile budget is a precondition, asserted**: at the default the
    6 x 6 coarse grid is one tile, complete after one write, and no
    interruption can leave anything outstanding.
    """
    from metamer.batch.barrier import check_pass1_complete

    # 9 x 8 gives a 5 x 4 coarse grid, which is six tiles at this budget's
    # side of 2. The default 7 x 6 gives 4 x 3, still multi-tile, but this
    # leaves room for the kill to land before the last tile.
    uri = _input(tmp_path, n_y=9, n_x=8)
    report = run_two_pass(
        _config(tmp_path, uri),
        tmp_path / "out.zarr",
        memory_budget_gb=_MULTI_TILE_BUDGET,
        on_pass1_tile_written=lambda _tile: os.kill(os.getpid(), signal.SIGTERM),
    )

    assert report.pass1 is not None
    assert report.pass1.tiles_total > 1, "a single-tile pass 1 cannot be incomplete"
    assert report.pass1.interrupted
    assert report.pass2 is None, "pass 2 must not start from an incomplete pass 1"
    assert report.pass2_seconds is None
    assert report.interrupted
    assert not (tmp_path / "out.zarr").exists(), "no pass-2 store may be created"

    # AND THE BARRIER WOULD INDEED HAVE REFUSED, which is what makes the early
    # return a decision about the exit code rather than an accident. (i2).
    assert report.pass1_path is not None
    with pytest.raises(ValidationError, match="outstanding"):
        check_pass1_complete(report.pass1_path)

    # The same command finishes the job, which is what exit 2 promises.
    finished = run_two_pass(
        _config(tmp_path, uri),
        tmp_path / "out.zarr",
        memory_budget_gb=_MULTI_TILE_BUDGET,
    )
    assert finished.pass2 is not None and not finished.interrupted


def test_an_incomplete_pass_one_store_refuses_pass_two(tmp_path):
    """`run(warm_start_from=...)` is gated on the barrier, not on the path.

    Behaviour under test: the barrier wired into the run rather than only into
    the driver. A caller can reach `run` directly, and a partial coarse grid is
    the dangerous case: it produces a source map that is entirely well-formed --
    every index in range, every `valid` true -- whose sources are systematically
    further away in the unfitted region.

    Expected value determined independently: the store is made incomplete by a
    real SIGTERM during pass 1 and `completed_tiles` is checked in the test.

    Bug this catches: the driver holding the only barrier. Nothing downstream
    of the source map can see a partial coarse grid, and the saving it costs
    looks like the mechanism underperforming.
    """
    from metamer.batch.completion import completed_tiles

    uri = _input(tmp_path, n_y=9, n_x=8)
    config = _config(tmp_path, uri)
    coarse = tmp_path / "coarse.zarr"
    partial = run(
        config,
        coarse,
        decimate=True,
        memory_budget_gb=_MULTI_TILE_BUDGET,
        on_tile_written=lambda _tile: os.kill(os.getpid(), signal.SIGTERM),
    )
    assert partial.tiles_total > 1
    assert not completed_tiles(coarse).all()

    with pytest.raises(ValidationError, match="outstanding"):
        run(config, tmp_path / "out.zarr", warm_start_from=coarse)


# --------------------------------------------------------------------------
# Requests that contradict themselves
# --------------------------------------------------------------------------


def test_a_warm_start_source_with_the_setting_disabled_is_refused(tmp_path):
    """`enabled = false` and a supplied source are not silently reconciled.

    Behaviour under test: the refusal rather than a resolution. Either half
    could be honoured, and the two produce different runs -- so the request is
    ambiguous and the run is not one that was asked for.

    Expected value determined independently: `warm_start_enabled` is in
    `FIT_RELEVANT_FIELDS`, so honouring the source would write warm-started
    fits under a `fit_hash` that says they are cold. Asserted here rather than
    argued: the message names both halves.

    Bug this catches: a driver that overrides the config, which is the
    convenient reading -- the caller asked for a warm start, so give them one.
    The store would then carry an identity that describes a different run.

    **With the positive control**: the same source under `enabled = true` is
    accepted, so the refusal is about the contradiction and not about the call.
    """
    uri = _input(tmp_path)
    coarse = tmp_path / "coarse.zarr"
    run(_config(tmp_path, uri), coarse, decimate=True)

    off = _config(tmp_path, uri, name="off.toml", extra="\nenabled = false\n")
    with pytest.raises(ValidationError, match="warm_start.enabled = false"):
        run(off, tmp_path / "a.zarr", warm_start_from=coarse)

    run(
        _config(tmp_path, uri, name="on.toml"),
        tmp_path / "b.zarr",
        warm_start_from=coarse,
    )


def test_a_warm_start_source_with_a_decimation_is_refused(tmp_path):
    """A decimated run IS pass 1, so it cannot warm-start from one.

    Behaviour under test: the refusal. `decimate=True` and `warm_start_from`
    together describe a coarse pass that starts from a coarse pass.

    Bug this catches: a caller passing both and getting pass 1 warm-started
    from an earlier pass 1 over the same coarse grid -- every fit started from
    its own converged optimum, which converges in one iteration and reports a
    saving that is an artifact of the mistake.
    """
    uri = _input(tmp_path)
    coarse = tmp_path / "coarse.zarr"
    run(_config(tmp_path, uri), coarse, decimate=True)

    with pytest.raises(ValidationError, match="decimated run IS pass 1"):
        run(
            _config(tmp_path, uri),
            tmp_path / "a.zarr",
            decimate=True,
            warm_start_from=coarse,
        )


def test_a_warm_start_source_with_a_recompute_is_refused(tmp_path):
    """A recompute fits nothing, so there is no optimizer to start.

    Behaviour under test: the refusal, on the same rule as the two calibration
    refusals above it in `run` -- a flag that parses and does nothing reads as
    supported.

    Bug this catches: `--reuse-fits-from` alongside a warm-start source
    silently ignoring the source. The store would record `warm_start_used`
    against fits that were copied from another store.
    """
    uri = _input(tmp_path)
    config = _config(tmp_path, uri)
    coarse = tmp_path / "coarse.zarr"
    run(config, coarse, decimate=True)
    source = tmp_path / "source.zarr"
    run(config, source)

    with pytest.raises(ValidationError, match="recompute"):
        run(config, tmp_path / "a.zarr", reuse_fits_from=source, warm_start_from=coarse)


# --------------------------------------------------------------------------
# `python -m metamer --two-pass`: the user-reachable entry point
# --------------------------------------------------------------------------


def _invoke(*arguments: str) -> subprocess.CompletedProcess[str]:
    """Run `python -m metamer` in a fresh process.

    **AN EXIT CODE IS A PROPERTY OF A PROCESS**, which is why these two go
    through a subprocess rather than calling `main()`: argparse's own exits and
    an unhandled traceback are invisible to an in-process call.
    """
    return subprocess.run(
        [sys.executable, "-m", "metamer", *arguments],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "METAMER_FLOOR_BYTES": str(STUB_FLOOR_PEAK)},
    )


def test_the_command_line_runs_both_passes_and_reports_them(tmp_path):
    """`--two-pass` is the entry point D11's README debt fell due on.

    Behaviour under test: the flag existing and doing what it says. Task 2 put
    pass 1's store-path rule at the derivation and deliberately left it out of
    `README.md`, because documenting a feature nobody can invoke is worse than
    documenting it late -- **this is the commit that makes it invocable**, which
    is why the paragraph is owed here.

    Expected values determined independently: the coarse store's path is
    derived in the test by `decimate.pass1_store_path`, not read out of the
    output.

    Bug this catches: a flag that parses and does nothing, which reads as
    supported -- the rule `--reuse-fits-from` was held to at 2a Task 12. It also
    catches the report lines being printed from pass 1's report rather than
    pass 2's, since the tile counts differ between the two grids.

    **NOT TESTED HERE, AND SAID RATHER THAN LEFT TO BE ASSUMED**: the exit-2
    path for a preempted pass 1. Reaching it through a subprocess means timing a
    SIGTERM into pass 1, which is a race whose failure to reproduce proves
    nothing -- the standing reason `on_tile_written` exists at all. The driver's
    half of it is asserted in
    `test_a_sigterm_during_pass_one_stops_before_the_barrier`; the mapping from
    `pass2 is None` to `ExitCode.ABORTED_EARLY` is one branch in `main` and is
    unexercised.
    """
    uri = _input(tmp_path)
    config = _config(tmp_path, uri)
    store = tmp_path / "out.zarr"

    result = _invoke(str(config), str(store), "--two-pass")
    assert result.returncode == 0, result.stderr
    assert pass1_store_path(store).exists()
    assert _attrs(store)["warm_start_used"] is True

    assert "pass 1:" in result.stdout
    assert str(pass1_store_path(store)) in result.stdout
    assert "KEEP IT" in result.stdout, "the permanent-artifact rule must be said"
    assert "warm start:" in result.stdout
    assert f"init rungs: {InitRung.WARM_START}=" in result.stdout


def test_the_command_line_refuses_two_pass_with_a_recompute(tmp_path):
    """`--two-pass` and `--reuse-fits-from` name two different programs.

    Behaviour under test: the refusal at the parser, where a combination of
    flags belongs. `run` refuses the same pair internally; this one exists so
    the message names the two flags the user typed rather than the two
    arguments they became.

    Expected value determined independently: design doc §14.3 gives exit 3 to
    an invalid request, and `_Parser.error` is what maps a usage failure onto
    it -- argparse's own 2 means "aborted early", which a mistyped command line
    is not.

    Bug this catches: the pair being accepted and one half silently ignored,
    which would record `warm_start_used` against fits that were copied from
    another store rather than fitted at all.
    """
    uri = _input(tmp_path)
    config = _config(tmp_path, uri)
    source = tmp_path / "source.zarr"
    assert _invoke(str(config), str(source)).returncode == 0

    result = _invoke(
        str(config),
        str(tmp_path / "out.zarr"),
        "--two-pass",
        "--reuse-fits-from",
        str(source),
    )
    assert result.returncode == ExitCode.CONFIG_INVALID
    assert "--two-pass" in result.stderr and "--reuse-fits-from" in result.stderr
    assert not (tmp_path / "out.zarr").exists()
