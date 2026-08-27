"""§11.3's source map: the spiral, the tie-break, the bound and exhaustion.

**THE FIXTURE IS DELIBERATELY AWKWARD IN THREE WAYS, EACH CLOSING A WAY THESE
TESTS COULD BE VACUOUS.** The grid is **not square**, so a transposed index and
a correct one disagree. Its size is **not a multiple of the stride**, so fine
points exist with no coarse point below or to the right of them. And
`coarse_ok` is **not uniform across the candidate axis**, so a per-point search
cannot masquerade as a per-candidate one.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pytest
import xarray as xr
import zarr

from metamer.batch.geometry import geometry_components
from metamer.batch.input import open_input
from metamer.batch.ragged import build_ragged_index, noise_extent
from metamer.batch.run import run
from metamer.batch.store import (
    StoreShape,
    TileSideBasis,
    create_store,
    provenance_attrs,
)
from metamer.batch.warmstart import (
    SourceMap,
    coarse_ok,
    read_warm_starts,
    source_map,
)
from metamer.config import load
from metamer.config.model import Config
from metamer.core.memory import FloorReport
from metamer.core.outcomes import Outcome
from tests.conftest import STUB_FLOOR_PEAK, rss_validity


def _reference(
    target: tuple[int, int],
    coarse: list[tuple[int, int]],
    ok: np.ndarray,
    model: int,
    max_fine_radius: int,
) -> tuple[int | None, int | None]:
    """§11.3's rule as the SPIKE HARNESS implements it, transcribed.

    This is `warmstart-spike-harness.py::spiral_source`, which is the instrument
    that produced D1's verdict and D6's stride curve -- so it is not a second
    opinion, it is **the specification those numbers describe**. It rescans
    every coarse point at every radius, which is why it is an oracle and not the
    implementation: at 10^7 fine points that is ~1e12 operations.

    Kept as a transcription rather than an import because the harness lives
    under `docs/` and is a dated record of a completed measurement; importing it
    would make a change there silently change what this suite asserts.
    """
    ty, tx = target
    for distance in range(max_fine_radius + 1):
        ring = [
            (i, (y, x))
            for i, (y, x) in enumerate(coarse)
            if max(abs(y - ty), abs(x - tx)) == distance and ok[i, model]
        ]
        if ring:
            best = min(ring, key=lambda item: (item[1][0], item[1][1]))
            return best[0], distance
    return None, None


def _coarse_points(n_y: int, n_x: int, stride: int) -> list[tuple[int, int]]:
    """The coarse points in fine coordinates, row-major -- the harness's order."""
    return [(y, x) for y in range(0, n_y, stride) for x in range(0, n_x, stride)]


def _ok(
    n_y: int, n_x: int, stride: int, failed: dict[int, set[tuple[int, int]]]
) -> np.ndarray:
    """`(n_cy, n_cx, M)` validity with a different failed set per candidate."""
    n_cy, n_cx = len(range(0, n_y, stride)), len(range(0, n_x, stride))
    ok = np.ones((n_cy, n_cx, len(failed)), dtype=bool)
    for model, cells in failed.items():
        for i, j in cells:
            ok[i, j, model] = False
    return ok


# --------------------------------------------------------------------------
# The rule, against the instrument that measured it
# --------------------------------------------------------------------------


@pytest.mark.parametrize("stride", [2, 3, 4])
def test_the_map_reproduces_the_spike_harness_point_by_point(stride):
    """Every cell agrees with the instrument D1 and D6 were measured on.

    Behaviour under test: the whole rule at once -- Chebyshev distance,
    inclusive radius, outward search, lowest-`y`-then-lowest-`x` tie-break --
    against a transcription of `spiral_source`.

    **This is the test that keeps the measurements meaningful.** If the shipped
    map differs from the harness anywhere, D1's 42.28% saving and D6's stride
    curve describe a mechanism that was never built -- (j2), an instrument
    validating the code path it exercises rather than the one the formula
    claims to describe.

    Bug this catches: any of the four choices drifting. A Euclidean metric
    reorders diagonal against axis neighbours; an exclusive radius shifts every
    bound-limited answer; a `min` on `(x, y)` instead of `(y, x)` inverts the
    tie-break; and starting at radius 1 makes every coarse point
    neighbour-sourced. **Each is silent** -- the run completes, every fit
    converges, and only a comparison against the reference shows it.
    """
    n_y, n_x = 11, 8
    # Cells chosen to exist at EVERY parametrized stride: stride 4 gives the
    # smallest coarse grid here, 3x2, so no index may exceed (2, 1).
    failed = {0: {(0, 1), (1, 1), (2, 0)}, 1: {(1, 0), (2, 1)}}
    ok = _ok(n_y, n_x, stride, failed)
    got = source_map(shape=(n_y, n_x), stride=stride, coarse_ok=ok, spiral_bound=4)

    coarse = _coarse_points(n_y, n_x, stride)
    n_cx = len(range(0, n_x, stride))
    flat_ok = ok.reshape(-1, ok.shape[2])
    for y in range(n_y):
        for x in range(n_x):
            point = y * n_x + x
            for model in range(ok.shape[2]):
                position, distance = _reference(
                    (y, x), coarse, flat_ok, model, 4 * stride
                )
                if position is None:
                    assert got.index[point, model] == -1
                    continue
                cy, cx = coarse[position]
                expected = (cy // stride) * n_cx + (cx // stride)
                assert got.index[point, model] == expected, (y, x, model)
                assert got.radius[point, model] == distance, (y, x, model)


def test_at_equal_distance_the_lower_y_wins_then_the_lower_x():
    """The tie-break, on a point constructed to be equidistant from four.

    Behaviour under test: the ordering that makes `θ̂` independent of iteration
    order, hence of tiling, hence of `--memory-budget`.

    Expected value determined independently: at stride 4 the fine point (2, 2)
    is Chebyshev distance 2 from the coarse points (0,0), (0,4), (4,0) and
    (4,4) -- all four, since Chebyshev makes the diagonal no further than the
    axes. Lowest `y` then lowest `x` selects (0, 0), which is coarse index 0.
    Hand-derived from the rule, not read from the implementation.

    Bug this catches: a tie-break that depends on iteration order -- for
    instance `argmin` over an array whose order comes from the traversal. `θ̂`
    then depends on tiling and **§11.3 breaks silently**: the run completes and
    two budgets give different answers.

    **The four-way tie is the point.** A fixture equidistant from two would be
    satisfied by a rule that breaks ties on `x` first, since with two
    candidates one comparison decides.
    """
    ok = _ok(9, 9, 4, {0: set()})
    got = source_map(shape=(9, 9), stride=4, coarse_ok=ok, spiral_bound=4)
    n_cx = len(range(0, 9, 4))

    assert got.index[2 * 9 + 2, 0] == 0
    assert got.radius[2 * 9 + 2, 0] == 2
    # And the tie is real: all four are at distance 2, so the assertion above
    # is a choice among them rather than the only reachable answer. (i2).
    for cy, cx in [(0, 0), (0, 4), (4, 0), (4, 4)]:
        assert max(abs(cy - 2), abs(cx - 2)) == 2
    assert 0 == (0 // 4) * n_cx + (0 // 4)


def test_a_coarse_points_own_source_is_itself_at_radius_zero():
    """D12's lattice property, asserted by equality rather than by a signal.

    Behaviour under test: that radius 0 is searched, so a coarse point resolves
    to itself with no special case in the rule.

    Expected value determined independently: the fine point `(y, x)` with
    `y % k == x % k == 0` is the coarse point `(y // k, x // k)`, whose flat
    coarse index is `(y // k) * n_cx + (x // k)`. Written from the definition.

    Bug this catches: a spiral starting at radius 1, which would make **every**
    coarse point neighbour-sourced and **invert the lattice artifact** D12
    records -- and which no aggregate saving figure would reveal, because the
    saving would simply be slightly worse everywhere.

    **This is also what makes the lattice testable downstream**: a reader can
    filter to self-sourced points by an index equality instead of hunting for a
    1-in-`k²` spatial periodicity.
    """
    n_y, n_x, stride = 11, 8, 3
    ok = _ok(n_y, n_x, stride, {0: set(), 1: set()})
    got = source_map(shape=(n_y, n_x), stride=stride, coarse_ok=ok, spiral_bound=4)
    n_cx = len(range(0, n_x, stride))

    seen = 0
    for y in range(0, n_y, stride):
        for x in range(0, n_x, stride):
            point = y * n_x + x
            for model in (0, 1):
                assert got.radius[point, model] == 0, (y, x)
                assert got.index[point, model] == (y // stride) * n_cx + (x // stride)
            seen += 1
    assert seen == len(range(0, n_y, stride)) * n_cx
    # A fine point that is NOT coarse must not be at radius 0, or the assertion
    # above is satisfied by a map that returns 0 everywhere.
    assert got.radius[1 * n_x + 1, 0] > 0


def test_the_search_is_per_candidate_and_a_uniform_fixture_could_not_show_it():
    """One coarse point failed for candidate 0 and usable for candidate 1.

    Behaviour under test: the `M` axis being searched independently. The
    warm-start key is `(fit_hash, candidate spec_hash)`, so a coarse point can
    be `OK` for one candidate and failed for another.

    Expected values determined independently: at stride 4 on an 8x8 grid the
    fine point (0, 0) IS coarse point (0, 0). With (0,0) failed for candidate 0
    only, candidate 1 keeps radius 0 at index 0, while candidate 0 must move to
    the nearest other coarse point -- which by the tie-break is (0, 4), coarse
    index 1, at distance 4.

    Bug this catches: a per-POINT search, which would collapse the two
    candidates onto one answer and **quietly discard usable sources**. A fixture
    whose `coarse_ok` is uniform across the candidate axis cannot distinguish
    the two implementations at all -- (i12) at the level of one array.
    """
    ok = _ok(8, 8, 4, {0: {(0, 0)}, 1: set()})
    got = source_map(shape=(8, 8), stride=4, coarse_ok=ok, spiral_bound=4)

    assert got.index[0, 1] == 0 and got.radius[0, 1] == 0
    assert got.index[0, 0] == 1 and got.radius[0, 0] == 4
    assert got.valid[0, 0] and got.valid[0, 1]


# --------------------------------------------------------------------------
# The bound, and exhaustion
# --------------------------------------------------------------------------


def test_exhaustion_marks_the_cell_invalid_rather_than_degrading_the_source():
    """A candidate failed everywhere within the bound gets `-1`, not a far source.

    Behaviour under test: the pairing that makes Task 0's validator meaningful.
    `fit` refuses a failed source **loudly**; the spiral must therefore never
    hand it one, and on exhaustion it must say so rather than reaching further.

    Expected values determined independently: with every coarse point failed
    for candidate 0, no radius contains a usable source, so the answer is `-1`
    at every point. Candidate 1 keeps every point valid, which is the paired
    positive -- without it, `-1` everywhere is also what a map that never ran
    would produce. (i2).

    Bug this catches: exhaustion falling through to a degraded source -- the
    nearest point regardless of its outcome, or the last one examined. `fit`
    would then raise on a cell the spiral said was valid, which is the
    constructed fault Task 0 exists to make loud, arriving from the one place
    that should never produce it.
    """
    n_y, n_x, stride = 11, 8, 3
    every = {
        (i, j)
        for i in range(len(range(0, n_y, stride)))
        for j in range(len(range(0, n_x, stride)))
    }
    ok = _ok(n_y, n_x, stride, {0: every, 1: set()})
    got = source_map(shape=(n_y, n_x), stride=stride, coarse_ok=ok, spiral_bound=4)

    assert np.all(got.index[:, 0] == -1)
    assert not np.any(got.valid[:, 0])
    assert np.all(got.radius[:, 0] == -1)
    assert np.all(got.valid[:, 1]), "the positive control: the map did run"


def test_the_bound_is_in_coarse_steps_and_is_inclusive():
    """`spiral_bound` counts coarse rings, and a source exactly at the bound is used.

    Behaviour under test: the unit and the inclusivity, both of which are fit
    identity -- `warm_start_spiral_bound` is in `FIT_RELEVANT_FIELDS`, so two
    runs agreeing on the integer and disagreeing on what it counts produce
    different `θ̂` under one `fit_hash`.

    Expected values determined independently: on a 9x9 grid at stride 4 the
    coarse points are at fine (0,0), (0,4), (0,8), (4,0) ... The fine point
    (0, 0) with only (0, 8) usable needs fine distance 8, which is 2 coarse
    steps. So `spiral_bound = 2` must find it and `spiral_bound = 1` -- reaching
    4 fine cells -- must not.

    Bug this catches two ways. Reading the bound as FINE units makes
    `spiral_bound = 2` reach only 2 cells and find nothing, which is what the
    spike harness's argument would have implied. And an exclusive radius makes
    the source at exactly `2 * stride` unreachable, shifting every
    bound-limited answer by one ring.
    """
    n_cy = n_cx = len(range(0, 9, 4))
    ok = np.zeros((n_cy, n_cx, 1), dtype=bool)
    ok[0, 2, 0] = True  # the coarse point at fine (0, 8), and nothing else

    reached = source_map(shape=(9, 9), stride=4, coarse_ok=ok, spiral_bound=2)
    assert reached.index[0, 0] == 2
    assert reached.radius[0, 0] == 8

    short = source_map(shape=(9, 9), stride=4, coarse_ok=ok, spiral_bound=1)
    assert short.index[0, 0] == -1, "a bound of 1 coarse step reaches 4 cells"


# --------------------------------------------------------------------------
# The reproducibility guarantee, and the array contract
# --------------------------------------------------------------------------


@pytest.mark.parametrize("side", [3, 4, 5])
def test_the_map_is_identical_however_the_grid_is_divided_into_regions(side):
    """Region by region equals the whole grid, element by element.

    Behaviour under test: §11.3's guarantee at the point it could most easily
    be lost. A pass-2 point's warm start must not depend on which tile it fell
    in, or `θ̂` depends on `--memory-budget`.

    Expected value determined independently: the whole-grid map, computed once
    and sliced -- so the comparison is against the same rule over a different
    decomposition rather than against a second implementation.

    Bug this catches: the map being built from **tile-local** indices, which the
    plan names as the single most likely way to lose the guarantee. The
    construction makes it structural -- the coarse geometry comes from the full
    `shape` and `region` only chooses which points are answered -- but a
    structural argument is a claim until something fails when it is untrue.

    **Element by element, not summary statistics**: a mean radius or a valid
    count agrees between a correct map and one whose sources are permuted.
    """
    n_y, n_x, stride = 11, 8, 3
    ok = _ok(n_y, n_x, stride, {0: {(0, 1), (2, 2)}, 1: {(1, 0)}})
    whole = source_map(shape=(n_y, n_x), stride=stride, coarse_ok=ok, spiral_bound=4)

    for y0 in range(0, n_y, side):
        for x0 in range(0, n_x, side):
            y1, x1 = min(y0 + side, n_y), min(x0 + side, n_x)
            piece = source_map(
                shape=(n_y, n_x),
                stride=stride,
                coarse_ok=ok,
                spiral_bound=4,
                region=(y0, y1, x0, x1),
            )
            rows = [y * n_x + x for y in range(y0, y1) for x in range(x0, x1)]
            np.testing.assert_array_equal(piece.index, whole.index[rows])
            np.testing.assert_array_equal(piece.radius, whole.radius[rows])
            np.testing.assert_array_equal(piece.valid, whole.valid[rows])


def test_valid_is_derived_from_index_and_cannot_disagree_with_it():
    """`valid` is exactly `index >= 0`, everywhere, including where exhausted.

    Behaviour under test: the invariant that keeps the two arrays consistent.
    Task 0's dtype gate catches `index` being passed where `valid` was meant,
    because `bool(-1)` is True; **nothing catches the two disagreeing at
    source**, and an `index` of -1 beside a `valid` of True hands `fit` a source
    that does not exist.

    Bug this catches: `valid` being accumulated in a second loop beside
    `index`, which is how two arrays come to disagree on the one cell where a
    branch was missed.

    The fixture contains both exhausted and resolved cells, asserted, so the
    identity is checked on both sides rather than over an array that is all one
    value.
    """
    n_y, n_x, stride = 11, 8, 3
    every = {
        (i, j)
        for i in range(len(range(0, n_y, stride)))
        for j in range(len(range(0, n_x, stride)))
    }
    ok = _ok(n_y, n_x, stride, {0: every, 1: {(0, 0)}})
    got = source_map(shape=(n_y, n_x), stride=stride, coarse_ok=ok, spiral_bound=4)

    np.testing.assert_array_equal(got.valid, got.index >= 0)
    assert got.valid.dtype == np.bool_
    assert got.index.dtype == np.int64
    assert got.radius.dtype == np.int64
    assert not got.valid.all() and got.valid.any(), "both branches must occur"


def test_the_arrays_are_row_major_over_the_region():
    """`B` indexes points in the order `assemble_tile` returns series.

    Behaviour under test: the layout contract Task 5 binds against. A `(B, M)`
    array whose `B` axis is column-major lines up with nothing, and every value
    in it is finite and plausible.

    Expected value determined independently: on a NON-SQUARE grid the point at
    fine `(1, 0)` is row `1 * n_x + 0 = 8`, and the point at `(0, 1)` is row 1.
    A transposed layout swaps them; on a square grid it would not.

    Bug this catches: the map being built column-major, which pairs every
    series with another series' warm start -- the Task 11
    wrong-candidate-at-index-1 shape, one axis over.
    """
    n_y, n_x, stride = 11, 8, 4
    ok = _ok(n_y, n_x, stride, {0: set()})
    got = source_map(shape=(n_y, n_x), stride=stride, coarse_ok=ok, spiral_bound=4)
    assert got.index.shape == (n_y * n_x, 1)
    # (0, 4) is a coarse point; (4, 0) is a different one. Row-major puts the
    # first at 4 and the second at 32, and column-major swaps them.
    n_cx = len(range(0, n_x, stride))
    assert got.index[0 * n_x + 4, 0] == 1
    assert got.index[4 * n_x + 0, 0] == 1 * n_cx


# --------------------------------------------------------------------------
# Refusals
# --------------------------------------------------------------------------


def test_a_coarse_ok_of_the_wrong_shape_is_refused_naming_the_expected_one():
    """A validity array for a different grid raises at entry.

    Behaviour under test: the shape agreement between the coarse grid the fine
    shape implies and the array pass 1's store supplied.

    Bug this catches: a `coarse_ok` built at the wrong stride -- the pass-1
    store built at 4 consumed by a run configured for 8. **The cross-store gate
    is Task 4's**, but the shapes disagree here first and a silent broadcast
    would resolve every point against the wrong coarse grid, with every index
    in range and every value plausible.

    Expected value determined independently: `len(range(0, n, k))` per axis --
    the count `isel(::k)` produces, which is what pass 1's store actually has.
    """
    ok = _ok(11, 8, 4, {0: set()})
    with pytest.raises(ValueError, match=r"4x3 coarse grid"):
        source_map(shape=(11, 8), stride=3, coarse_ok=ok, spiral_bound=4)


def test_a_non_boolean_coarse_ok_is_refused_rather_than_cast():
    """An outcome-code array is not silently truth-tested.

    Behaviour under test: the same dtype discipline Task 0 put on `x0_valid`,
    at the array that feeds it.

    Bug this catches: passing `/status/outcome` straight in. `Outcome.OK` is
    code **0**, so a cast would read **OK as False and every failure as True** --
    the array inverted exactly, producing a map that sources every point from a
    failed fit and marks the usable ones exhausted. Every index in range, no
    exception.
    """
    ok = _ok(11, 8, 4, {0: set()}).astype(np.uint8)
    with pytest.raises(ValueError, match="coarse_ok must be a boolean array"):
        # mypy flags this, which is the point: the annotation catches the swap
        # in any typed caller and the runtime gate catches it in the rest. The
        # ignore is what lets the runtime gate be tested at all.
        source_map(
            shape=(11, 8),
            stride=4,
            coarse_ok=ok,  # type: ignore[arg-type]
            spiral_bound=4,
        )


@pytest.mark.parametrize(
    ("stride", "bound", "message"),
    [
        (0, 4, "coarse stride must be at least 1"),
        (-1, 4, "coarse stride must be at least 1"),
        (4, 0, "bound must be at least 1"),
        (4, -1, "bound must be at least 1"),
    ],
)
def test_a_stride_or_bound_below_one_is_refused(stride, bound, message):
    """Neither may be zero or negative.

    Behaviour under test: the guards.
    Bug this catches: `spiral_bound = 0` searching radius 0 only, which would
    silently reduce the mechanism to "coarse points warm-start themselves and
    nothing else does" -- a run that completes with almost every cell exhausted
    and a saving near zero, **indistinguishable from warm-starting not
    helping**, which is the conclusion §11.2 attaches a threshold to.

    The stride guard is separate from `decimate`'s: this function is called
    with a stride the caller supplies, and relying on the decimation having
    refused first would put the raise in the wrong place with the wrong
    message.
    """
    ok = _ok(11, 8, 4, {0: set()})
    with pytest.raises(ValueError, match=message):
        source_map(shape=(11, 8), stride=stride, coarse_ok=ok, spiral_bound=bound)


def test_a_region_outside_the_grid_is_refused():
    """A tile that does not fit the stated shape raises rather than clipping.

    Behaviour under test: the region contract.
    Bug this catches: silent clipping, which returns fewer rows than the caller
    expects and misaligns every downstream `(B, M)` array against the block
    `assemble_tile` produced -- shapes that broadcast, values that are finite.
    """
    ok = _ok(11, 8, 4, {0: set()})
    with pytest.raises(ValueError, match="not inside"):
        source_map(
            shape=(11, 8),
            stride=4,
            coarse_ok=ok,
            spiral_bound=4,
            region=(0, 12, 0, 8),
        )


def test_the_source_map_is_a_frozen_dataclass_of_three_arrays():
    """The interface Task 5 binds against, pinned.

    Behaviour under test: the three names and their presence, so a later
    refactor that renames one fails here rather than at the consumer.
    Bug this catches: `SourceMap` growing a fourth array that a consumer starts
    depending on before anyone decides it is part of the contract.
    """
    ok = _ok(11, 8, 4, {0: set()})
    got = source_map(shape=(11, 8), stride=4, coarse_ok=ok, spiral_bound=4)
    assert isinstance(got, SourceMap)
    assert set(got.__dataclass_fields__) == {"index", "valid", "radius"}
    with pytest.raises(AttributeError):
        got.index = got.index  # type: ignore[misc]


# --------------------------------------------------------------------------
# Reading the sources: `coarse_ok` and `read_warm_starts`
# --------------------------------------------------------------------------
#
# **THESE FIXTURES ARE REAL `run(decimate=True)` STORES, WITH ONE STATED
# EXCEPTION.** The subject is what a pass-1 store actually contains -- the
# ragged packing, the outcome codes, the NaN a failed fit leaves -- and a
# hand-assembled store would carry whatever the test wrote. The exception is the
# residency measurement at the bottom, whose subject is BYTE VOLUME and whose
# fixture is 640 000 coarse series; that one says so where it is.


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


_READER_CONFIG = """
data_uri = "{uri}"
variable = "sla"
signal_terms = ["constant", "trend"]
candidates = ["white", "white + matern12"]
criteria = ["aic"]
memory_budget_gb = 1.0

[warm_start]
coarse_stride = 2
spiral_bound = 4
"""


def _reader_input(tmp_path: Path, n_y: int = 9, n_x: int = 7) -> str:
    """A non-square input whose extent is not a multiple of the stride."""
    origin = np.datetime64("2000-01-01")
    dataset = xr.Dataset(
        {
            "sla": (
                ("time", "y", "x"),
                np.random.default_rng(17)
                .standard_normal((24, n_y, n_x))
                .astype("float32"),
            )
        },
        coords={
            "time": np.array([origin + np.timedelta64(31 * i, "D") for i in range(24)]),
            "y": 100.0 + 2.5 * np.arange(n_y),
            "x": 500.0 - 0.5 * np.arange(n_x),
        },
    )
    path = tmp_path / "in.zarr"
    dataset.to_zarr(path)
    return str(path)


def _reader_pass1(tmp_path: Path) -> tuple[Path, Config, str]:
    """A complete pass-1 store from a real decimated run, its config and input."""
    uri = _reader_input(tmp_path)
    config_path = tmp_path / "c.toml"
    config_path.write_text(_READER_CONFIG.format(uri=uri))
    store = tmp_path / "coarse.zarr"
    run(config_path, store, decimate=True)
    return store, load(config_path), uri


def test_coarse_ok_is_boolean_and_marks_exactly_the_ok_fits(tmp_path):
    """Pass 1's usability mask is `outcome == OK`, as a bool array.

    Behaviour under test: the predicate a source map searches over. `fit`
    refuses a warm start that is non-finite or at a diagnostic limit, and `OK`
    is the outcome that guarantees neither -- `optimize_series` returns
    `DIAGNOSTIC_LIMIT` before it can return `OK`, and returns `OK` only with a
    Hessian, which is the branch `core.fit` writes `theta_unconstrained` under.

    Expected values determined independently: the store's `/status/outcome` is
    read here and compared against `Outcome.OK.code` in the test, not read back
    out of the function under test.

    Bug this catches: **returning the outcome codes themselves.** `source_map`
    refuses a non-boolean array precisely because an outcome array reads every
    failure code as True and `OK` -- which is 0 -- as False, inverting the mask
    exactly, with every shape intact and no exception anywhere.

    **With the fixture guard that makes it non-vacuous:** the mask is asserted
    to contain both values. An all-True mask cannot tell this function from one
    that returns `np.ones`, and a zero reading is not evidence of absence.
    """
    store, _, _ = _reader_pass1(tmp_path)
    mask = coarse_ok(store)
    stored = np.asarray(_array_of(store, "status", "outcome")[:], dtype=np.uint8)

    assert mask.dtype == np.bool_
    assert mask.shape == stored.shape
    assert np.array_equal(mask, stored == Outcome.OK.code)
    assert mask.any() and not mask.all(), (
        "a uniform mask cannot distinguish this from a constant, and it would "
        "also leave the per-candidate search untested"
    )


def test_the_reader_returns_the_stored_optimum_of_each_chosen_source(tmp_path):
    """Every warm cell carries its source's `theta_unconstrained`, re-padded.

    Behaviour under test: the join. Pass 1 stores the unconstrained optimum
    **unpadded on a ragged axis** -- each candidate's free parameters
    concatenated -- and `fit` wants `(B, M, p_max)` with NaN padding. The reader
    is the only place that inversion happens.

    Expected values determined independently: the whole array is read here, the
    flat coarse index is decoded here, and each expected row is sliced with the
    ragged index built here from the config. Nothing is compared against a
    second call of the function under test.

    Bug this catches: the ragged offsets applied to the wrong candidate. Every
    array keeps its shape and every value stays finite, and the warm start for
    `white` would be `matern12`'s `sigma` -- which is a legal starting point, so
    the fit converges and the only symptom is a different optimum. It also
    catches the flat index being decoded with `n_coarse_y` instead of
    `n_coarse_x`, which agrees on a square coarse grid and this one is 5 x 4.

    **And the padding is asserted NaN**, because `fit` reads each candidate's
    row to `:p` and a number in the padding of the narrower candidate would mean
    the reader had written past its extent.
    """
    store, config, uri = _reader_pass1(tmp_path)
    specs = list(config.process_specs())
    index = build_ragged_index(specs, noise_extent)
    mask = coarse_ok(store)
    n_cy, n_cx = mask.shape[0], mask.shape[1]
    assert (n_cy, n_cx) == (5, 4), "the coarse grid must not be square"

    sources = source_map(
        shape=(9, 7),
        stride=2,
        coarse_ok=mask,
        spiral_bound=4,
        region=(2, 7, 1, 6),
    )
    warm = read_warm_starts(store, sources, index, coarse_shape=(n_cy, n_cx))

    stored = np.asarray(
        _array_of(store, "warmstart", "theta_unconstrained")[:], dtype=np.float64
    )
    assert warm.shape == (5 * 5, len(specs), max(index.extents))
    assert bool(sources.valid.any()), "no warm cell would make this vacuous"

    for point in range(warm.shape[0]):
        for model, extent in enumerate(index.extents):
            row = warm[point, model]
            if not bool(sources.valid[point, model]):
                assert np.isnan(row).all()
                continue
            flat = int(sources.index[point, model])
            expected = stored[flat // n_cx, flat % n_cx, index.block(model)]
            assert np.array_equal(row[:extent], expected)
            assert np.isnan(row[extent:]).all(), "padding beyond p must stay NaN"


def test_the_reader_leaves_an_exhausted_cell_entirely_unwarmed(tmp_path):
    """A `-1` source index produces an all-NaN row, never a neighbour's values.

    Behaviour under test: exhaustion carried through the read. `fit` is handed
    `x0` and `x0_valid` together and skips the warm start where validity is
    false, but it never inspects `x0` there -- so a reader that filled an
    exhausted row with whatever was adjacent in the read block would be
    invisible until someone flipped a validity bit.

    Expected values determined independently: the map is CONSTRUCTED here with
    known `-1` entries rather than produced by a spiral, because a fixture whose
    exhaustion depends on which coarse fits happened to fail cannot place one
    where the test wants it -- (i8), a fixture that cannot express the defect.

    Bug this catches: indexing the read block with `-1`, which numpy accepts as
    "the last element". The row would then be a real optimum from the far corner
    of the coarse grid, finite and plausible, and `_check_warm_starts` would
    pass it.

    **With the positive control in the same array**: the valid cell beside it is
    asserted to carry its source's values, so an all-NaN return would fail.
    """
    store, config, _ = _reader_pass1(tmp_path)
    specs = list(config.process_specs())
    index = build_ragged_index(specs, noise_extent)
    mask = coarse_ok(store)
    n_cx = int(mask.shape[1])
    live = int(np.flatnonzero(mask[:, :, 0].ravel())[0])

    constructed = SourceMap(
        index=np.array([[live, -1], [-1, -1]], dtype=np.int64),
        valid=np.array([[True, False], [False, False]], dtype=np.bool_),
        radius=np.array([[0, -1], [-1, -1]], dtype=np.int64),
    )
    warm = read_warm_starts(
        store, constructed, index, coarse_shape=(mask.shape[0], mask.shape[1])
    )

    stored = np.asarray(
        _array_of(store, "warmstart", "theta_unconstrained")[:], dtype=np.float64
    )
    expected = stored[live // n_cx, live % n_cx, index.block(0)]
    assert np.array_equal(warm[0, 0, : index.extents[0]], expected)
    assert not np.isnan(expected).any(), "the control must carry real values"
    assert np.isnan(warm[0, 1]).all()
    assert np.isnan(warm[1]).all()


#: Coarse points in the residency fixture's pass-1 store: 800 x 800.
#:
#: **CHOSEN SO THE WHOLE ARRAY IS TENS OF MEGABYTES, WHICH IS THE ONLY THING
#: THAT MAKES THE DEFECT VISIBLE.** At `p_total = 4` and float64 this is
#: 640 000 x 4 x 8 = **20.48 MB**; one tile's sources are 51.2 kB. The plan asks
#: for the assertion "at a field size where whole-loading would be visible", and
#: the obstacle is absolute size rather than ratio: a 32 x 32 fine grid already
#: makes whole-loading exceed one fine tile, and 8 kB is invisible to any RSS
#: difference.
_RESIDENCY_COARSE_SIDE = 800

#: Its tile side, and therefore its chunk side. `_chunk_side` cannot subdivide
#: below the 4 MB target here, so the chunk is `(64, 64, 4)` float64 = 131 kB --
#: which is what actually bounds a windowed read, since zarr materializes whole
#: chunks. **A store with one chunk per array would make the rectangle
#: irrelevant**, and that is a property of the store's geometry rather than of
#: the reader.
_RESIDENCY_TILE_SIDE = 64

#: Bytes of resident growth the windowed read may not exceed.
#:
#: **PLACED BETWEEN TWO MEASUREMENTS RATHER THAN CHOSEN.** On 2026-08-27, three
#: fresh interpreters each: the windowed read grew **1.39, 1.43 and 1.44 MB**;
#: loading the same array whole grew **26.96, 27.11 and 27.35 MB**. Eight
#: megabytes is **5.5x the first and 3.4x below the second**, so it catches a
#: read that becomes field-sized and says nothing finer.
_RESIDENCY_BOUND_BYTES = 8e6


def _residency_store(tmp_path: Path) -> tuple[Path, Path, int]:
    """A pass-1 store of 640 000 coarse points, built WITHOUT fitting.

    **THIS IS THE ONE FIXTURE IN THIS MODULE THAT IS NOT A REAL RUN, AND THE
    EXCEPTION IS DELIBERATE.** `tests/test_barrier.py` requires every pass-1
    store to come from `run(decimate=True)` because ITS subject is the attrs a
    writer records, and a hand-built store carries whatever the test wrote. The
    subject here is **byte volume**: shapes, dtypes and chunk geometry, about
    which a store built by `create_store` is the same object that a run would
    produce. Fitting 640 000 coarse series to find that out is hours.

    **The attrs describe the small input this opens rather than the 800 x 800
    grid**, which is harmless and is stated rather than hidden: the reader opens
    two arrays and reads no attr at all, and the gate that does read them is
    `barrier.check_pass1_store`, tested against real runs elsewhere.

    Returns:
        The config path, the store path, and the store's `P_total`.
    """
    origin = np.datetime64("2000-01-01")
    dataset = xr.Dataset(
        {"sla": (("time", "y", "x"), np.zeros((6, 4, 4), dtype="float32"))},
        coords={
            "time": np.array([origin + np.timedelta64(31 * i, "D") for i in range(6)]),
            "y": np.arange(4.0),
            "x": np.arange(4.0),
        },
    )
    uri = tmp_path / "in.zarr"
    dataset.to_zarr(uri)
    config_path = tmp_path / "big.toml"
    config_path.write_text(_READER_CONFIG.format(uri=uri))
    config = load(config_path)
    specs = list(config.process_specs())
    index = build_ragged_index(specs, noise_extent)

    floor = FloorReport(
        pre_warm_bytes=STUB_FLOOR_PEAK,
        post_warm_bytes=STUB_FLOOR_PEAK,
        with_input_bytes=STUB_FLOOR_PEAK,
        peak_bytes=STUB_FLOOR_PEAK,
        components={"override": STUB_FLOOR_PEAK},
    )
    attrs = provenance_attrs(
        config,
        geometry_components=geometry_components(open_input(str(uri), "sla")),
        thread_limits={"numba": 1},
        read_amplification=1.0,
        unique_dt_count=1,
        tile_sides={"shared": _RESIDENCY_TILE_SIDE},
        tile_side_basis=TileSideBasis.DEFAULT,
        memory_budget_requested_gb=1.0,
        max_iter=200,
        floor=floor,
    )
    store = tmp_path / "big.pass1.zarr"
    create_store(
        store,
        specs=specs,
        criteria=list(config.criteria),
        shape=StoreShape(
            n_y=_RESIDENCY_COARSE_SIDE,
            n_x=_RESIDENCY_COARSE_SIDE,
            n_beta=2,
            tile_side=_RESIDENCY_TILE_SIDE,
        ),
        attrs=attrs,
    )
    unconstrained = _array_of(store, "warmstart", "theta_unconstrained", mode="r+")
    outcome = _array_of(store, "status", "outcome", mode="r+")
    generator = np.random.default_rng(1)
    band = 200
    for start in range(0, _RESIDENCY_COARSE_SIDE, band):
        unconstrained[start : start + band] = generator.standard_normal(
            (band, _RESIDENCY_COARSE_SIDE, index.total)
        )
        outcome[start : start + band] = np.full(
            (band, _RESIDENCY_COARSE_SIDE, len(specs)), Outcome.OK.code, dtype=np.uint8
        )
    return config_path, store, index.total


_RESIDENCY_PROGRAM = """
import json, sys
import numpy as np, zarr
from metamer.batch.ragged import build_ragged_index, noise_extent
from metamer.batch.warmstart import coarse_ok, read_warm_starts, source_map
from metamer.config import load
from metamer.core.machine import current_rss_bytes, reclaim_shortfall_bytes

mode, config_path, store = sys.argv[1], sys.argv[2], sys.argv[3]
config = load(config_path)
index = build_ragged_index(list(config.process_specs()), noise_extent)
usable = coarse_ok(store)
sources = source_map(
    shape=(1600, 1600), stride=2, coarse_ok=usable, spiral_bound=4,
    region=(0, 64, 0, 64),
)
# READ IN THE CHILD, which is the process the difference below is taken in.
reference = current_rss_bytes()
before = current_rss_bytes()
if mode == "tile":
    warm = read_warm_starts(
        store, sources, index, coarse_shape=(usable.shape[0], usable.shape[1])
    )
    checksum = float(np.nansum(warm))
else:
    # THE SAME WARM STARTS, BUILT THE OTHER WAY. This is the mutant: identical
    # output, whole-array read. The re-padding below is `read_warm_starts`'
    # own, so the only difference between the two branches is what was loaded.
    array = zarr.open_group(store, mode="r")["warmstart"]["theta_unconstrained"]
    whole = np.asarray(array[:], dtype=np.float64)
    n_cx = int(usable.shape[1])
    warm = np.full(
        (sources.index.shape[0], sources.index.shape[1], max(index.extents)), np.nan
    )
    for model, extent in enumerate(index.extents):
        selected = sources.valid[:, model]
        chosen = sources.index[selected, model]
        warm[selected, model, :extent] = whole[chosen // n_cx, chosen % n_cx][
            :, index.block(model)
        ]
    checksum = float(np.nansum(warm))
print(json.dumps({
    "delta": current_rss_bytes() - before,
    "checksum": checksum,
    "cells": int(sources.valid.sum()),
    "shortfall": reclaim_shortfall_bytes(reference),
}))
"""


def _residency_reading(mode: str, config_path: Path, store: Path) -> dict[str, float]:
    """Run one measurement in a FRESH interpreter and return its JSON."""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            textwrap.dedent(_RESIDENCY_PROGRAM),
            mode,
            str(config_path),
            str(store),
        ],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "METAMER_FLOOR_BYTES": str(STUB_FLOOR_PEAK)},
    )
    assert result.returncode == 0, result.stderr
    parsed: dict[str, float] = json.loads(result.stdout.splitlines()[-1])
    return parsed


@pytest.mark.machine
def test_the_reader_does_not_load_pass_ones_store_whole(tmp_path):
    """One tile's warm starts cost a rectangle, not the coarse field.

    Behaviour under test: the invariant §11.1's general form breaks through if
    it fails. Peak RAM must be derivable from the memory budget alone, and a
    source read proportional to the FIELD is a second term the budget cannot
    see -- invisible at test sizes and 12.96 MB at design doc §9.4's grid, still
    invisible, and unbounded above that.

    Expected values determined independently, by measurement rather than from
    the code: see `_RESIDENCY_BOUND_BYTES` for the six readings the bound sits
    between.

    Bug this catches: `array[:]` in the reader instead of a windowed read. It
    produces identical warm starts -- the control below has the same checksum
    restricted to the same points -- so nothing except residency can see it.

    **THE POSITIVE CONTROL IS THE WHOLE-ARRAY READ ITSELF** (i2), in its own
    fresh interpreter. A pure "under 8 MB" assertion is satisfied by a fixture
    too small to breach any bound; this one shows the same fixture breaching it
    when the read is done the other way.

    **AND WHAT BOUNDS THE WINDOWED READ IS THE STORE'S CHUNK GEOMETRY, NOT THE
    RECTANGLE.** zarr materializes whole chunks, so the read costs
    `(chunks touched) x (chunk bytes)` -- and both are properties of pass 1's
    tile side, which comes from its memory budget. That is exactly the shape
    §11.1.1 asks for: a term the budget bounds, rather than one the grid does.
    """
    config_path, store, p_total = _residency_store(tmp_path)
    whole_bytes = _RESIDENCY_COARSE_SIDE**2 * p_total * 8
    # FIXTURE GUARD: a store whose whole array is small cannot express the
    # defect, and shrinking it later would make this test pass for that reason.
    assert whole_bytes > 20e6, f"the fixture must be tens of MB, got {whole_bytes}"

    witnessed: dict[str, float] = {}
    with rss_validity(
        "one tile's warm starts against the whole coarse field",
        witness=lambda: witnessed.get("shortfall", 0.0),
    ):
        windowed = _residency_reading("tile", config_path, store)
        witnessed["shortfall"] = float(windowed["shortfall"])
        assert windowed["cells"] == 64 * 64 * 2, "every cell must have a source"
        assert windowed["delta"] < _RESIDENCY_BOUND_BYTES

        control = _residency_reading("whole", config_path, store)
        assert control["checksum"] == windowed["checksum"], (
            "the control must produce the SAME warm starts, or it is not a "
            "control on how they were read"
        )
        assert control["delta"] > _RESIDENCY_BOUND_BYTES
