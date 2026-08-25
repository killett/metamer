"""Tests for pass 1's decimated input and its store path.

**THE FIXTURES HERE DO NOT ALL USE `("time", "y", "x")`, AND THAT IS THE POINT
OF THE MODULE.** Every other test module in this project does, so the name-based
decimation the plan's brief spelled out would pass all of them. The
non-`y`/`x` fixture below is the first in the project.
"""

from __future__ import annotations

import os
import signal
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import xarray as xr
import zarr

from metamer.batch.completion import completed_tiles
from metamer.batch.decimate import decimated_handle, pass1_store_path
from metamer.batch.geometry import geometry_components, geometry_hash
from metamer.batch.input import InputHandle, open_input
from metamer.batch.run import run


def _handle(
    n_time: int = 6,
    n_y: int = 9,
    n_x: int = 7,
    dims: tuple[str, str, str] = ("time", "y", "x"),
) -> InputHandle:
    """An in-memory input with configurable spatial dimension names.

    Coordinates are deliberately NOT `arange`: a coordinate equal to its own
    index makes an off-by-one in the decimation invisible, because the value and
    the position agree.
    """
    dataset = xr.Dataset(
        {
            "sla": (
                dims,
                np.arange(n_time * n_y * n_x, dtype="float32").reshape(
                    n_time, n_y, n_x
                ),
            )
        },
        coords={
            dims[0]: np.arange(n_time),
            dims[1]: 100.0 + 2.5 * np.arange(n_y),
            dims[2]: 500.0 - 0.5 * np.arange(n_x),
        },
    )
    return InputHandle(dataset=dataset, variable="sla", scheme="memory", uri="mem://x")


@pytest.mark.parametrize("stride", [1, 2, 3, 4, 8])
def test_the_decimation_selects_exactly_the_isel_points(stride):
    """Every `stride`-th index on both spatial axes, and no other.

    Behaviour under test: the index arithmetic itself, against an independently
    constructed expectation. The expected coordinate values are built with
    Python slicing on a list, not with the `isel` the implementation uses, so
    the two do not share a derivation.

    Bug this catches: an off-by-one -- `1::stride` for `0::stride`, or a stride
    applied to one axis only. Either shifts every warm-start source by a cell
    and **still produces an entirely plausible answer**: the coarse grid is the
    right size, every fit converges, and nothing downstream can tell. The
    coordinates are non-integer and decreasing on one axis precisely so that a
    value cannot be confused with an index.
    """
    handle = _handle()
    parent = handle.dataset
    out = decimated_handle(handle, stride).dataset

    expected_y = list(parent["y"].values)[::stride]
    expected_x = list(parent["x"].values)[::stride]
    np.testing.assert_array_equal(out["y"].values, np.array(expected_y))
    np.testing.assert_array_equal(out["x"].values, np.array(expected_x))
    # The data must be selected with the coordinates, not merely relabelled.
    np.testing.assert_array_equal(
        out["sla"].values, parent["sla"].values[:, ::stride, ::stride]
    )
    # The time axis is untouched: a coarse point is a whole series.
    np.testing.assert_array_equal(out["time"].values, parent["time"].values)


def test_the_spatial_axes_are_taken_positionally_not_by_name():
    """A `latitude`/`longitude` input decimates on the right two axes.

    Behaviour under test: the module's central claim. `check_input_contract`
    requires only that `dims[0]` is `time`; the other two names are free, and
    its own message calls the contract "three, mapping to (time, y, x)".

    Bug this catches: `isel(y=..., x=...)` as the plan's brief literally spells
    it. **It is invisible to every other test module in this project** -- all
    sixteen input fixtures use `("time", "y", "x")` -- and it raises on the
    first real gridded product, which is the (i8) shape where the fault class
    cannot be expressed by any fixture the project owns.

    Expected values determined independently: the same Python-slice expectation
    as above, on the differently named axes.

    **This asserts the decimation, not end-to-end support.** `tiling.py` takes
    the literal names in four places, so a run over this input still fails in
    assembly. That is pre-existing and named in the module docstring.
    """
    handle = _handle(dims=("time", "latitude", "longitude"))
    parent = handle.dataset
    out = decimated_handle(handle, 3).dataset

    assert out["sla"].dims == ("time", "latitude", "longitude")
    np.testing.assert_array_equal(
        out["latitude"].values, parent["latitude"].values[::3]
    )
    np.testing.assert_array_equal(
        out["longitude"].values, parent["longitude"].values[::3]
    )
    np.testing.assert_array_equal(out["sla"].values, parent["sla"].values[:, ::3, ::3])


def test_stride_one_is_an_equivalent_view_and_not_a_special_case():
    """`k = 1` returns the whole grid, through the same code path.

    Behaviour under test: the absence of a branch. `1` is a legal stride and the
    config's `coarse_stride` has `ge=1`, so it must not be a corner.

    Bug this catches: a guard that returns the original handle for `k = 1`,
    which would leave the general path unexercised at the one stride a
    debugging session reaches for first.

    **THE VALUE ASSERTIONS ALONE CANNOT CATCH THAT, WHICH IS WHY THE IDENTITY
    ASSERTION IS HERE.** An early `return handle` produces exactly the same
    values -- that is what makes it tempting -- so a test asserting only the
    values would go green against the branch it names. Caught by asking what an
    early return would do to this test, before running it.
    """
    handle = _handle()
    result = decimated_handle(handle, 1)
    out = result.dataset
    np.testing.assert_array_equal(out["sla"].values, handle.dataset["sla"].values)
    np.testing.assert_array_equal(out["y"].values, handle.dataset["y"].values)
    assert result is not handle
    assert out is not handle.dataset


def test_the_handle_keeps_its_uri_variable_and_scheme():
    """Only the dataset changes; the provenance fields do not.

    Behaviour under test: it is the SAME input, differently sampled.

    Bug this catches: synthesizing a URI for the decimated view -- say
    `mem://x#stride=8` -- which would put a location that does not exist into
    the store's provenance and into `run_hash`, where a reader would take it for
    something they could open.
    """
    handle = _handle()
    out = decimated_handle(handle, 4)
    assert (out.uri, out.variable, out.scheme) == (
        handle.uri,
        handle.variable,
        handle.scheme,
    )
    assert out.dataset is not handle.dataset


@pytest.mark.parametrize("stride", [0, -1])
def test_a_stride_below_one_is_refused(stride):
    """`k = 0` and `k = -1` raise rather than producing an empty or reversed grid.

    Behaviour under test: the guard.
    Bug this catches: `slice(None, None, 0)` raises inside xarray with a message
    about slice steps, and `slice(None, None, -1)` **silently reverses both
    spatial axes** -- a full-size grid, every fit converging, and the geography
    mirrored. The second is the dangerous one and it does not raise anywhere.
    """
    with pytest.raises(ValueError, match="at least 1"):
        decimated_handle(_handle(), stride)


def test_a_variable_that_is_not_time_first_and_three_d_is_refused():
    """The positional assumption is checked rather than assumed.

    Behaviour under test: the precondition the positional indexing rests on.
    Bug this catches: taking `dims[1]` and `dims[2]` of a two-dimensional or
    time-last variable, which either raises an `IndexError` far from the cause
    or decimates the time axis. `check_input_contract` enforces this too, but
    `decimated_handle` runs before it in the two-pass driver, so relying on the
    later check would put the raise in the wrong place with the wrong message.
    """
    dataset = xr.Dataset(
        {"sla": (("y", "x"), np.zeros((3, 4), dtype="float32"))},
        coords={"y": np.arange(3), "x": np.arange(4)},
    )
    handle = InputHandle(dataset=dataset, variable="sla", scheme="m", uri="mem://y")
    with pytest.raises(ValueError, match="three-dimensional with 'time' first"):
        decimated_handle(handle, 2)


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("out.zarr", "out.pass1.zarr"),
        ("/a/b/results.zarr", "/a/b/results.pass1.zarr"),
        ("out", "out.pass1"),
        ("a.b.zarr", "a.b.pass1.zarr"),
    ],
)
def test_the_pass1_path_is_derived_from_the_output_path_by_a_stated_rule(
    given, expected
):
    """The suffix goes before the extension, and the parent directory is kept.

    Behaviour under test: the rule a user has to be able to predict, since pass
    1's store is a permanent artifact they will look for.

    Expected values determined independently: written out by hand per case, not
    computed from `PASS1_SUFFIX`, so a change to the rule fails here rather than
    following along. The multi-dot case is included because `.stem` of
    `a.b.zarr` is `a.b`, and a rule built from `split(".")` would give
    `a.pass1.b.zarr`.

    Bug this catches: appending the suffix at the end -- `out.zarr.pass1` --
    which loses the `.zarr` extension that tells a reader and their tooling what
    the directory is.
    """
    assert pass1_store_path(given) == Path(expected)


def test_the_pass1_path_is_not_the_output_path():
    """The two never collide, which is what keeps pass 2 from overwriting pass 1.

    Behaviour under test: the separation the whole two-pass design rests on.
    Bug this catches: an empty or mis-derived suffix, under which pass 2 would
    open pass 1's store, find it complete for a different grid, and either
    refuse confusingly or overwrite the audit's only cold reference.
    """
    for path in ("out.zarr", "out", "/tmp/x/y.zarr"):
        assert pass1_store_path(path) != Path(path)


# --------------------------------------------------------------------------
# The decimated run: `run(decimate=True)` end to end
# --------------------------------------------------------------------------


def _zarr_input(tmp_path: Path, *, n_time: int = 24, n_y: int = 9, n_x: int = 7) -> str:
    """A real zarr input on disk, with coordinates distinct from their indices."""
    origin = np.datetime64("2000-01-01")
    dataset = xr.Dataset(
        {
            "sla": (
                ("time", "y", "x"),
                np.random.default_rng(11)
                .standard_normal((n_time, n_y, n_x))
                .astype("float32"),
            )
        },
        coords={
            "time": np.array(
                [origin + np.timedelta64(31 * i, "D") for i in range(n_time)]
            ),
            "y": 100.0 + 2.5 * np.arange(n_y),
            "x": 500.0 - 0.5 * np.arange(n_x),
        },
    )
    path = tmp_path / "in.zarr"
    dataset.to_zarr(path)
    return str(path)


#: A budget that puts the 6x6 coarse grid in FOUR tiles rather than one.
#:
#: **The default budget gives `tile_side = 1600` and one tile**, under which a
#: kill leaves nothing outstanding and every resume assertion below is vacuous.
#: Measured against the session's stubbed floor (`tests/conftest.py`), not
#: derived: `tile_side_for` is the thing these tests exercise, so computing the
#: budget from its inverse would let one formula change move both sides of the
#: comparison. The tests assert `tiles_total > 1` so a drift fails loudly rather
#: than quietly restoring the vacuous case.
_MULTI_TILE_BUDGET = 0.0010159

#: Two DIFFERENT budgets that derive the SAME tile side (4) on that grid.
#:
#: This is the pair `resume_tile_side`'s rule exists for: the guard is over the
#: derived side and never over the budget, so a resume at either must be
#: accepted. A single budget could not express it.
_SAME_SIDE_BUDGETS = (0.0010203, 0.00102)

_RUN_CONFIG = """
data_uri = "{uri}"
variable = "sla"
signal_terms = ["constant", "trend"]
candidates = ["white"]
criteria = ["aic"]
memory_budget_gb = 1.0
"""


def _run_config(
    tmp_path: Path, uri: str, extra: str = "", name: str = "c.toml"
) -> Path:
    path = tmp_path / name
    path.write_text(_RUN_CONFIG.format(uri=uri) + extra)
    return path


def test_a_decimated_run_records_the_parents_fingerprint_and_the_stride(tmp_path):
    """Pass 1's store is bound to its parent by content, not by a path.

    Behaviour under test: the two stores' identities are related. Without this
    the only thing joining a coarse store to the grid it decimates is where
    somebody put it on disk.

    Expected values determined independently: the parent's fingerprint is
    recomputed in this test from the UNDECIMATED input via `geometry_components`
    and `geometry_hash`, and the decimated store's own fingerprint is recomputed
    by decimating the parent dataset here and hashing that -- neither is read
    back out of the store it is being compared to.

    **THE REPRODUCTION IS DONE FROM THE DATASET, NOT FROM THE STORED HASH**, and
    the plan's phrase "its own fingerprint is derivable from those two" cannot
    mean otherwise: a hash is not invertible. What is derivable is the
    COMPONENTS, from the parent's components and `k`.

    Bug this catches: a pass-1 store carrying no record of its parent, so a
    later cross-store gate can only compare paths -- under which any coarse
    store in the right place is accepted for any parent grid.
    """
    uri = _zarr_input(tmp_path)
    out = tmp_path / "coarse.zarr"
    run(
        _run_config(tmp_path, uri, "\n[warm_start]\ncoarse_stride = 3\n"),
        out,
        decimate=True,
    )

    attrs = dict(zarr.open_group(str(out), mode="r").attrs)
    handle = open_input(uri, "sla")
    parent_rollup = geometry_hash(geometry_components(handle))
    assert attrs["parent_geometry_hash"] == parent_rollup
    assert attrs["coarse_stride"] == 3

    decimated = geometry_hash(geometry_components(decimated_handle(handle, 3)))
    assert attrs["geometry_hash"] == decimated
    # And the two are genuinely different, or the assertion above is satisfied
    # by a run that never decimated anything. (i2).
    assert attrs["geometry_hash"] != parent_rollup


def test_an_ordinary_run_carries_no_decimation_attrs(tmp_path):
    """Absence is what says "not a pass-1 store", so absence is asserted.

    Behaviour under test: the (a0) third-register decision -- these are optional
    attrs and their absence is meaningful, rather than required attrs that would
    refuse every store written before this task.

    Bug this catches: writing the keys unconditionally with a `None` or a `0`
    stride. Then "not decimated" and "decimated at an unrecorded stride" become
    the same bytes, and a cross-store gate reading `attrs.get("coarse_stride")`
    cannot tell an ordinary store from a coarse one.

    The paired positive is the test above: the same `run`, one flag apart, does
    write them.
    """
    uri = _zarr_input(tmp_path)
    out = tmp_path / "full.zarr"
    run(_run_config(tmp_path, uri), out)
    attrs = dict(zarr.open_group(str(out), mode="r").attrs)
    assert "parent_geometry_hash" not in attrs
    assert "coarse_stride" not in attrs


def test_a_decimated_run_fits_exactly_the_points_isel_selects(tmp_path):
    """The fitted grid is the coarse grid, cell for cell.

    Behaviour under test: the decimation reaching the store, not merely the
    handle. The store's spatial extent and its coordinates must be the coarse
    ones.

    Expected values determined independently: the expected shape is computed
    with `len(range(0, n, k))` and the expected coordinates with a Python slice
    on the parent's coordinate list -- neither uses `isel`.

    Bug this catches: an off-by-one in the decimation, which shifts every
    warm-start source by one cell and **still produces a plausible answer** --
    right-sized grid, converged fits, nothing downstream able to tell.
    """
    n_y, n_x, stride = 9, 7, 3
    uri = _zarr_input(tmp_path, n_y=n_y, n_x=n_x)
    out = tmp_path / "coarse.zarr"
    report = run(
        _run_config(tmp_path, uri, f"\n[warm_start]\ncoarse_stride = {stride}\n"),
        out,
        decimate=True,
    )

    assert (report.contract.n_y, report.contract.n_x) == (
        len(range(0, n_y, stride)),
        len(range(0, n_x, stride)),
    )
    status = xr.open_zarr(str(out), group="status")
    assert status["outcome"].shape[:2] == (
        len(range(0, n_y, stride)),
        len(range(0, n_x, stride)),
    )

    stored: Any = dict(zarr.open_group(str(out), mode="r").attrs)["geometry_components"]
    parent = xr.open_zarr(uri)
    expected_y = list(parent["y"].values)[::stride]
    assert stored["spatial_coordinates"]["y"] == pytest.approx(expected_y)


def test_a_kill_during_pass_one_resumes_pass_one(tmp_path):
    """An interrupted decimated run refits exactly the outstanding tiles.

    Behaviour under test: that pass 1 inherits the resume, rather than being a
    one-shot. At 10^7 points and `k = 8` a coarse pass is still 156 000 fits,
    so an un-resumable pass 1 is a real cost, not a corner.

    Bug this catches: the decimated path bypassing the completion bitmap -- for
    instance by deriving tiles from the parent grid while writing bits indexed
    on the coarse one. The second run would then either redo everything or skip
    tiles it never wrote.

    Expected values determined independently: the two runs' `tiles_written`
    must sum to the total tile count, with neither being zero, and the final
    bitmap must be wholly set.
    """
    uri = _zarr_input(tmp_path, n_y=12, n_x=12)
    out = tmp_path / "coarse.zarr"
    config = _run_config(tmp_path, uri, "\n[warm_start]\ncoarse_stride = 2\n")

    first = run(
        config,
        out,
        decimate=True,
        memory_budget_gb=_MULTI_TILE_BUDGET,
        on_tile_written=lambda tile: os.kill(os.getpid(), signal.SIGTERM),
    )
    # **THE FIXTURE PRECONDITION IS ASSERTED, NOT ASSUMED.** The coarse grid is
    # 6x6 and the default budget puts all of it in ONE tile -- under which the
    # kill leaves nothing outstanding and the resume below is vacuous. Written
    # after exactly that happened.
    assert first.tiles_total > 1, "a single-tile fixture cannot express a resume"
    done = completed_tiles(out)
    assert first.tiles_written >= 1
    assert not done.all(), "the kill must leave work outstanding"

    second = run(config, out, decimate=True, memory_budget_gb=_MULTI_TILE_BUDGET)
    assert completed_tiles(out).all()
    assert second.tiles_written == int((~done).sum())
    assert second.tiles_skipped == int(done.sum())


def test_a_pass_one_store_resumes_at_a_budget_giving_the_same_side(tmp_path):
    """`resume_tile_side` guards the coarse store on its own derived side.

    Behaviour under test: the rule is over the DERIVED SIDE and not over the
    budget, on the coarse grid as on the full one -- two budgets that derive the
    same side must both resume.

    Bug this catches: the guard being applied to the budget, which would refuse
    a resume that is geometrically identical. On a decimated store this is
    likelier to bite than on a full one, because the coarse grid is small enough
    that a wide range of budgets all derive the same side.

    The refusing direction has its own coverage in `tests/test_resume.py`; what
    is new here is that a DECIMATED store is guarded the same way.
    """
    uri = _zarr_input(tmp_path, n_y=12, n_x=12)
    out = tmp_path / "coarse.zarr"
    config = _run_config(tmp_path, uri, "\n[warm_start]\ncoarse_stride = 2\n")
    first = run(config, out, decimate=True, memory_budget_gb=_SAME_SIDE_BUDGETS[0])
    second = run(config, out, decimate=True, memory_budget_gb=_SAME_SIDE_BUDGETS[1])
    assert _SAME_SIDE_BUDGETS[0] != _SAME_SIDE_BUDGETS[1], "the budgets must differ"
    assert second.tile_side == first.tile_side
    assert second.tiles_written == 0
    assert second.tiles_skipped == first.tiles_total


def test_pass_one_and_pass_two_stores_are_separate_and_neither_writes_the_other(
    tmp_path,
):
    """A coarse run and a full run over one config touch different directories.

    Behaviour under test: the separation the two-pass design rests on, asserted
    on the artifacts rather than on the code path.

    Bug this catches: the decimated run writing into the output store -- after
    which pass 2 resumes a store whose bitmap describes the coarse grid, and
    either refuses confusingly or, if the grids happened to be compatible,
    reports coarse fits as full ones.

    Expected values determined independently: the two stores' `geometry_hash`
    attrs must differ, because they describe different grids, and the coarse
    store's mtime must not move when the full run executes.
    """
    uri = _zarr_input(tmp_path, n_y=9, n_x=7)
    config = _run_config(tmp_path, uri, "\n[warm_start]\ncoarse_stride = 3\n")
    coarse = pass1_store_path(tmp_path / "out.zarr")
    full = tmp_path / "out.zarr"

    run(config, coarse, decimate=True)
    before = sorted(
        (p.relative_to(coarse), p.stat().st_mtime_ns)
        for p in coarse.rglob("*")
        if p.is_file()
    )
    assert before, "the coarse store must contain files to compare"

    run(config, full)
    after = sorted(
        (p.relative_to(coarse), p.stat().st_mtime_ns)
        for p in coarse.rglob("*")
        if p.is_file()
    )
    assert after == before, "the full run must not touch pass 1's store"

    coarse_attrs = dict(zarr.open_group(str(coarse), mode="r").attrs)
    full_attrs = dict(zarr.open_group(str(full), mode="r").attrs)
    assert coarse_attrs["geometry_hash"] != full_attrs["geometry_hash"]
    assert coarse.name != full.name
