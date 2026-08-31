"""`metamer.bench.n2map`: the N2 arm reduced to a full-field selection map.

**WHAT THE MAP IS FOR, AND IT IS THE REASON EVERY TEST HERE IS ABOUT LOSING
NOTHING.** A smear measured against zero is a different claim from a smear
measured against the width an equal-distance random start produces. Zero is not
a floor -- it is the absence of one.

**TASK 3 DOES NOT BUILD N2.** `arm_starts` already matches the perturbation per
cell, keys the direction on the grid-global point index, shares that direction
with N1 and counts the cells it cannot run. This module **reduces** that to one
selected candidate per point, and every test below is aimed at a way the
reduction could lose one of those four properties -- or at the one thing the
reduction must add, which is the exclusion `run_arms` deliberately does not
perform.

**NO FIELD IS BUILT AND NO RUN HAPPENS.** The batches are constructed arrays at
`n_time = 24`, or 40 where the selection axis has to be live; the plan placed
Tasks 2 and 3 among the tasks that need neither a field nor a run.

**THESE TESTS ARE NOT MARKED `slow`, AND THAT IS A DECISION RATHER THAN AN
OMISSION.** They cost about 3.5 minutes against a 54-minute full sweep. The
marker's stated meaning is *"drives the real filter at PRODUCTION sizes"*, and
these drive it at toy sizes -- 4 to 12 points, 24 to 40 samples -- and are slow
only because an unconverged `matern12` wanders. Marking them would widen the
marker to mean *"anything slow"*, which is a second reading of a term of art;
and it would deselect from `test-fast` the only tests covering the exclusion
the N2 map exists to perform. **If `test-fast` becomes painful, mark them and
move this paragraph with the marker.**
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pytest
from numpy.typing import NDArray

from metamer.batch.audit import Arm, cold_starts, run_arms
from metamer.batch.store import SELECTED_UNSET
from metamer.batch.timeaxis import to_decimal_years
from metamer.bench import fields, n2map, smear
from metamer.config.candidates import parse_candidate
from metamer.core.criteria import Criterion
from metamer.core.engines.kalman import KalmanEngine
from metamer.core.terms import ProcessSpec, free_param_index

_SPECS = [parse_candidate("white"), parse_candidate("white + matern12")]
_EXTENTS = [len(free_param_index(spec)) for spec in _SPECS]
#: **THROUGH THE SHIPPED PARSER**, so the fixture and a run cannot disagree
#: about the design matrix. `k_beta` enters the penalty counts and every fit.
_SIGNAL = fields.signal_spec()
_CRITERION = Criterion.AIC
_SEED = 11

#: **THE FITS ARE CAPPED AND THAT IS DELIBERATE.** Every property under test
#: here -- the exclusion, the counts, the keying, the composition with Task 2 --
#: is a property of which START each cell was given and how the result was
#: reduced, none of which needs a converged optimum. Uncapped, a `matern12`
#: candidate on white noise wanders to the iteration cap and one call costs
#: 75 s. The oracles below pass the SAME cap, or they would be comparing a
#: different fit.
_MAX_ITER = 8

#: **AND ONE TEST CANNOT USE THE CAP**, because it needs the SELECTION to be
#: live: at `_MAX_ITER` the `matern12` candidate never reaches `OK`, so every
#: point trivially selects `white` and a map returning any arm at all would
#: agree with any other. 20 iterations on a correlated fixture is the cheapest
#: setting found at which both candidates fit AND the arms disagree.
_LIVE_MAX_ITER = 20


def _batch(
    n_normal: int = 4, n_parallel: int = 3, n_time: int = 24, seed: int = 3
) -> tuple[NDArray[np.float64], NDArray[np.bool_], NDArray[np.float64]]:
    """Observations, mask and the RUN's own time axis for one grid.

    **`to_decimal_years` ON THE ACTUAL COORDINATE, NEVER AN APPROXIMATION.** 2c
    Task 6 measured a hand-built axis moving `theta_hat` by 6.7e-05 relative,
    and the conversion is under `ALGORITHM_VERSION`.
    """
    n_points = n_normal * n_parallel
    generator = np.random.default_rng(seed)
    y = generator.standard_normal((n_points, n_time))
    mask = np.ones((n_points, n_time), dtype=np.bool_)
    origin = np.datetime64("2000-01-01")
    stamps = np.array([origin + np.timedelta64(31 * i, "D") for i in range(n_time)])
    return y, mask, to_decimal_years(stamps)


def _correlated_batch(
    n_normal: int = 2, n_parallel: int = 3, n_time: int = 40, seed: int = 5
) -> tuple[NDArray[np.float64], NDArray[np.bool_], NDArray[np.float64]]:
    """A batch the `matern12` candidate can actually win on.

    **WHITE NOISE MAKES THE SELECTION AXIS DEGENERATE**, and a test whose
    subject is the selected candidate cannot run on a fixture where one
    candidate wins everywhere by default -- (i12). The draw is an exponential
    correlation plus a white floor, which is `matern12`'s own kernel, so the
    candidate set can express the truth.
    """
    n_points = n_normal * n_parallel
    generator = np.random.default_rng(seed)
    origin = np.datetime64("2000-01-01")
    stamps = np.array([origin + np.timedelta64(31 * i, "D") for i in range(n_time)])
    t = to_decimal_years(stamps)
    lag = np.abs(t[:, None] - t[None, :])
    covariance = np.exp(-lag / 2.0) + 0.25 * np.eye(n_time)
    y = generator.multivariate_normal(
        np.zeros(n_time), covariance, size=n_points, method="cholesky"
    )
    return y, np.ones((n_points, n_time), dtype=np.bool_), t


def _cold(
    y: NDArray[np.float64],
    mask: NDArray[np.bool_],
    t: NDArray[np.float64],
    specs: list[ProcessSpec] | None = None,
) -> NDArray[np.float64]:
    """The ladder start, through the shipped path rather than rebuilt."""
    return cold_starts(
        y,
        mask,
        t,
        specs or _SPECS,
        engine=KalmanEngine(),
        objective=n2map.DEFAULT_OBJECTIVE,
    )


def _warm_near(
    cold: NDArray[np.float64],
    extents: Sequence[int] | None = None,
    *,
    delta: float = 0.35,
) -> NDArray[np.float64]:
    """A warm start a fixed displacement from cold in every free coordinate.

    Built rather than fitted, because the properties under test need a CHOSEN
    distance in a chosen cell and a fitted fixture cannot place one -- (i8).
    """
    warm = cold.copy()
    for model, width in enumerate(extents or _EXTENTS):
        warm[:, model, :width] = cold[:, model, :width] + delta
    return warm


#: A warm start for candidate 1 that is INSIDE the diagnostic box in every
#: coordinate and far enough from cold that the N2 displacement leaves it.
#: **Both halves matter.** A warm start that is itself out of limits makes
#: `fit` refuse the WARM arm and the test never reaches N2; one that is too
#: close leaves N2 inside and the fixture is vacuous. The limits are
#: `sigma (+-18.42)`, `rho (+-13.82)`, `sigma (+-18.42)` in unconstrained
#: coordinates, so `[17, 10, 17]` sits inside each and has norm 26.0 -- against
#: a largest possible in-box norm of 29.5, so almost every direction of that
#: length exits. **Every test using it asserts that it did.**
_OUT_OF_BOX_PUSH = np.array([17.0, 10.0, 17.0])

#: A displacement whose norm sits close enough to the box wall that whether N2
#: leaves it depends on the DIRECTION drawn -- and therefore on the key. That
#: makes the exclusion PATTERN an observable of the keying, at `_MAX_ITER` and
#: with no converged fit required, which is what lets the grid-growth test see
#: its own subject cheaply.
#:
#: **NORM 18.0, AND EVERY COORDINATE STILL INSIDE THE BOX.** `rho`'s wall is at
#: 13.815 and the fitted cold `rho` runs down to -3.63 on this fixture, so 11.0
#: keeps the WARM start admissible -- a warm start outside the box makes `fit`
#: refuse the warm arm and the test never reaches N2. At norm 18 the N2 start
#: exits only when the drawn direction puts enough of itself on `rho`, which is
#: what makes the pattern depend on the key rather than on the magnitude.
_MARGINAL_PUSH = np.array([10.08, 11.0, 10.08])


def _push_out_of_box(
    warm: NDArray[np.float64], cold: NDArray[np.float64], row: int
) -> NDArray[np.float64]:
    """Displace candidate 1 at `row` far enough that N2 leaves the box."""
    warm[row, 1, :3] = cold[row, 1, :3] + _OUT_OF_BOX_PUSH
    return warm


def _push_to_the_wall(
    warm: NDArray[np.float64], cold: NDArray[np.float64]
) -> NDArray[np.float64]:
    """Displace candidate 1 everywhere to where admissibility turns on direction."""
    warm[:, 1, :3] = cold[:, 1, :3] + _MARGINAL_PUSH
    return warm


def _map(
    y: NDArray[np.float64],
    mask: NDArray[np.bool_],
    t: NDArray[np.float64],
    warm: NDArray[np.float64],
    warm_valid: NDArray[np.bool_],
    *,
    grid_shape: tuple[int, int],
    specs: list[ProcessSpec] | None = None,
    seed: int = _SEED,
    max_iter: int = _MAX_ITER,
) -> tuple[NDArray[np.int16], n2map.N2Counts]:
    """`n2_field_map` with the fixture's spellings filled in once."""
    return n2map.n2_field_map(
        y,
        t,
        _SIGNAL,
        specs or _SPECS,
        _CRITERION,
        mask=mask,
        warm=warm,
        warm_valid=warm_valid,
        grid_shape=grid_shape,
        seed=seed,
        max_iter=max_iter,
    )


# ---------------------------------------------------------------------------
# One instrument: the map and the audit compute the same N2
# ---------------------------------------------------------------------------


def test_the_maps_value_at_a_point_is_run_arms_own_n2_selection_there():
    """The map reduces `run_arms`; it does not re-derive N2.

    Behaviour: at the same seed and the same grid-global points, the map's value
    is the N2 arm's winning candidate at that point.

    Expected value determined independently: by calling `run_arms` in the test
    with `points = arange(n)` and reading `results[Arm.N2].ranking.best_index`.
    The oracle is the shipped arm itself, which is the point -- two instruments
    computing one quantity is (j5)'s territory and the cheap fix is one
    instrument.

    **The fixture's own vacuity is asserted, not assumed:** if the N2 and COLD
    arms selected the same candidate everywhere, this test would pass for a map
    that returned the COLD selection, which is the exact defect the exclusion
    rules exist to prevent. So the fixture is required to disagree somewhere.

    Bug this catches: a second derivation of N2 -- re-drawing the direction,
    re-computing the distance, or fitting the perturbed start through a second
    call site. It would stop the floor and the audit agreeing about what N2 is,
    and they would disagree QUIETLY, since both are plausible numbers.
    """
    grid_shape = (2, 2)
    y, mask, t = _correlated_batch(*grid_shape)
    cold = _cold(y, mask, t)
    warm = _warm_near(cold, delta=3.0)
    valid = np.ones((y.shape[0], len(_SPECS)), dtype=np.bool_)

    got, counts = _map(
        y, mask, t, warm, valid, grid_shape=grid_shape, max_iter=_LIVE_MAX_ITER
    )

    arms = run_arms(
        y,
        t,
        _SIGNAL,
        _SPECS,
        _CRITERION,
        mask=mask,
        warm=warm,
        warm_valid=valid,
        points=np.arange(y.shape[0], dtype=np.int64),
        seed=_SEED,
        max_iter=_LIVE_MAX_ITER,
    )
    expected = arms.results[Arm.N2].ranking.best_index
    assert (expected != arms.results[Arm.COLD].ranking.best_index).any(), (
        "fixture is vacuous: N2 and cold agree everywhere"
    )
    assert counts.excluded == 0
    assert np.array_equal(got.reshape(-1), expected.astype(np.int16))


def test_the_map_composes_with_the_smear_estimator_with_no_adapter():
    """Task 3 produces exactly what Task 2 consumes.

    Behaviour: the map is a selection map in the store's vocabulary, so
    `agreement_map` takes it directly and `smear_width` reads the result.

    Expected value determined independently: `agreement_map` requires indices
    into `fields.CANDIDATES` or a sentinel, so a map of the shipped candidate
    set must pass its range check and produce a finite 0/1 array; and a reading
    off it names the shipped estimator.

    Bug this catches: an adapter being needed between the two tasks -- a float
    map, a differently-ordered candidate axis, or a third spelling of the
    subject. (j9) has fired five times in this sub-phase, and an adapter is
    where the sixth would live.
    """
    grid_shape = (4, 2)
    specs = fields.candidate_specs()
    y, mask, t = _batch(*grid_shape)
    cold = _cold(y, mask, t, specs)
    extents = [len(free_param_index(spec)) for spec in specs]
    warm = _warm_near(cold, extents)
    valid = np.ones((y.shape[0], len(specs)), dtype=np.bool_)

    got, _ = _map(y, mask, t, warm, valid, grid_shape=grid_shape, specs=specs)

    truth = np.zeros(grid_shape, dtype=np.int8)
    truth[:2, :] = 1
    agreement = smear.agreement_map(got, truth)
    reading = smear.smear_width(
        agreement,
        boundary_index=2,
        normal_axis=0,
        reach_cells=smear.spiral_reach_cells(),
        map_name=smear.AGREEMENT_MAP_NAME,
        arm=str(Arm.N2),
    )

    assert set(np.unique(agreement[np.isfinite(agreement)])) <= {0.0, 1.0}
    assert reading.estimator == smear.ESTIMATOR
    assert reading.arm == "n2"


# ---------------------------------------------------------------------------
# The exclusion the audit deliberately does not perform
# ---------------------------------------------------------------------------


def test_run_arms_really_does_fit_an_inadmissible_cell_cold():
    """The fault the map removes is shown to occur before the map is credited.

    Behaviour: `arm_starts` marks an inadmissible N2 start `n2_valid = False`,
    `run_arms` passes that as `x0_valid`, and `fit` FALLS BACK TO THE MOMENT
    LADDER -- which is the cold start. So the N2 arm's own result at that cell
    is a cold fit.

    Expected value determined independently: at the offending cell the N2 arm's
    optimum must equal the COLD arm's, because both started from the ladder and
    `fit` has no stochastic component.

    Bug this catches: the map's exclusion being defensive against a fault that
    does not occur. Without this test, "the map holds no cold fit" is a claim
    about a fallback nobody has observed, and the exclusion path's count would
    be a statement about the INSTRUMENT rather than about the field -- (a2b) at
    a count, (i8) for a fault class that must be constructed.
    """
    grid_shape = (2, 2)
    y, mask, t = _batch(*grid_shape)
    cold = _cold(y, mask, t)
    warm = _warm_near(cold)
    _push_out_of_box(warm, cold, 1)
    valid = np.ones((y.shape[0], len(_SPECS)), dtype=np.bool_)

    arms = run_arms(
        y,
        t,
        _SIGNAL,
        _SPECS,
        _CRITERION,
        mask=mask,
        warm=warm,
        warm_valid=valid,
        points=np.arange(y.shape[0], dtype=np.int64),
        seed=_SEED,
        max_iter=_MAX_ITER,
    )

    assert arms.starts.n2_inadmissible[1, 1], "fixture failed to leave the box"
    n2_theta = arms.results[Arm.N2].theta_unconstrained[1, 1]
    cold_theta = arms.results[Arm.COLD].theta_unconstrained[1, 1]
    assert np.array_equal(n2_theta, cold_theta, equal_nan=True)


def test_an_inadmissible_cell_excludes_its_point_and_is_counted():
    """An excluded point carries no value, and the count says why.

    Behaviour: a point with an inadmissible N2 start in any candidate is
    excluded from the map, appears in `inadmissible`, and holds the unset
    sentinel rather than a fit.

    Expected value determined independently: the fixture puts one cell beyond
    `rho`'s upper diagnostic limit, so exactly one point of four is excluded for
    that reason and none for exhaustion.

    Bug this catches: the fallback silently populating the N2 map with COLD
    fits. "N2 agrees with cold" would then be true by construction at exactly
    the cells where the perturbation was largest, and the floor the smear is
    read against would be the cold arm's own width -- which is zero, which is
    the comparison this arm exists to replace.
    """
    grid_shape = (2, 2)
    y, mask, t = _batch(*grid_shape)
    cold = _cold(y, mask, t)
    warm = _warm_near(cold)
    _push_out_of_box(warm, cold, 1)
    valid = np.ones((y.shape[0], len(_SPECS)), dtype=np.bool_)

    got, counts = _map(y, mask, t, warm, valid, grid_shape=grid_shape)

    assert got.reshape(-1)[1] == SELECTED_UNSET
    assert counts.inadmissible == 1
    assert counts.exhausted_spiral == 0
    assert counts.excluded == 1


def test_one_contaminated_candidate_excludes_the_whole_point():
    """The reduction from cells to points is ANY, not ALL.

    Behaviour: the selected candidate is decided by comparing every candidate's
    score, so a point where one candidate fell back to the ladder has a winner
    chosen partly by a cold fit.

    Expected value determined independently: the fixture makes candidate 1
    inadmissible at one point and leaves candidate 0 admissible there. Under an
    `any` reduction that point is excluded; under `all` it is kept.

    Bug this catches: an `all()` reduction. It keeps exactly the MIXED points --
    the ones whose value is neither N2's nor cold's -- and nothing downstream
    could identify them, because a mixed winner is an ordinary candidate index.
    Being the subtler of the two reductions, it is also the one that looks
    conservative.
    """
    grid_shape = (2, 2)
    y, mask, t = _batch(*grid_shape)
    cold = _cold(y, mask, t)
    warm = _warm_near(cold)
    _push_out_of_box(warm, cold, 2)
    valid = np.ones((y.shape[0], len(_SPECS)), dtype=np.bool_)

    got, counts = _map(y, mask, t, warm, valid, grid_shape=grid_shape)

    arms = run_arms(
        y,
        t,
        _SIGNAL,
        _SPECS,
        _CRITERION,
        mask=mask,
        warm=warm,
        warm_valid=valid,
        points=np.arange(y.shape[0], dtype=np.int64),
        seed=_SEED,
        max_iter=_MAX_ITER,
    )
    assert arms.starts.n2_inadmissible[2, 1], "candidate 1 must be inadmissible"
    assert not arms.starts.n2_inadmissible[2, 0], "candidate 0 must be fine"
    assert got.reshape(-1)[2] == SELECTED_UNSET
    assert counts.inadmissible == 1


def test_a_point_with_no_warm_source_is_counted_as_an_exhausted_spiral():
    """The two exclusion reasons are named apart, because they are different faults.

    Behaviour: a point some candidate has no warm source for has no distance to
    match, so N2 is undefined there. It is excluded under `exhausted_spiral`,
    never under `inadmissible`.

    Expected value determined independently: `SourceMap.valid` is `index >= 0`
    and `index` is `-1` only where the spiral was exhausted, so "no warm source"
    and "the spiral was exhausted" are the same cells. The fixture withholds a
    source at one point of four.

    Bug this catches: the two reasons merged into one count. A field failing
    because the source map could not reach its points would then read as an N2
    geometry problem, sending the next reader at `spiral_bound` instead of at
    the field's own coverage -- and both are plausible causes of an empty map.
    """
    grid_shape = (2, 2)
    y, mask, t = _batch(*grid_shape)
    cold = _cold(y, mask, t)
    warm = _warm_near(cold)
    valid = np.ones((y.shape[0], len(_SPECS)), dtype=np.bool_)
    # **ONE CANDIDATE, NOT THE POINT.** Withholding every candidate's source
    # makes an `any`/`all` swap on this reduction unobservable -- both spell
    # "excluded" -- so the fixture withholds exactly one and the reduction is
    # what decides.
    valid[3, 1] = False

    got, counts = _map(y, mask, t, warm, valid, grid_shape=grid_shape)

    assert valid[3, 0], "candidate 0 must still have a source"
    assert got.reshape(-1)[3] == SELECTED_UNSET
    assert counts.exhausted_spiral == 1
    assert counts.inadmissible == 0
    assert counts.excluded == 1


def test_the_two_exclusion_reasons_are_disjoint_and_sum_to_the_total():
    """`excluded == exhausted_spiral + inadmissible`, on a fixture carrying both.

    Behaviour: the reasons partition the excluded set. Exhaustion takes
    precedence, so a point that would qualify under both is counted once.

    Expected value determined independently: the fixture excludes one point for
    exhaustion and one, a different one, for inadmissibility -- so the total is
    2 and the identity is checked against a case where the two are distinct
    rather than against a fixture where one of them is zero.

    Bug this catches: double counting. If a point excluded for exhaustion also
    passed the inadmissibility test, the identity would break and the two
    reasons would overlap -- so a report totalling them would exceed the number
    of missing cells, and a reader reconciling the map against the counts would
    find more excuses than absences.
    """
    grid_shape = (2, 3)
    y, mask, t = _batch(*grid_shape)
    cold = _cold(y, mask, t)
    warm = _warm_near(cold)
    _push_out_of_box(warm, cold, 4)
    _push_out_of_box(warm, cold, 1)
    valid = np.ones((y.shape[0], len(_SPECS)), dtype=np.bool_)
    # **ROW 1 QUALIFIES UNDER BOTH REASONS** -- candidate 0 has no source AND
    # candidate 1's N2 start leaves the box. That is the only input on which
    # precedence is observable: with the two reasons applied independently it
    # is counted twice and the identity breaks.
    valid[1, 0] = False

    got, counts = _map(y, mask, t, warm, valid, grid_shape=grid_shape)

    assert counts.exhausted_spiral == 1
    assert counts.inadmissible == 1
    assert counts.excluded == counts.exhausted_spiral + counts.inadmissible
    assert int((got == SELECTED_UNSET).sum()) == counts.excluded


def test_the_unset_cells_in_the_map_are_exactly_the_excluded_count():
    """The map and the accounting cannot disagree about how many cells are gone.

    Behaviour: every excluded point holds `SELECTED_UNSET` and no other point
    does. `-1` -- "a fit ran and no candidate won" -- is a different fact and
    stays available for it.

    Expected value determined independently: the fixture excludes two points, so
    the map holds exactly two `-2` cells.

    Bug this catches: spending `-1` on an absence. Both sentinels become NaN in
    `agreement_map`, so the distinction is LOST at the next step and can only be
    got right here; with `-1` used for exclusion, a point where every candidate
    genuinely failed would be indistinguishable from one that was never fitted,
    and this identity -- the only thing that would notice -- would silently
    over-count.
    """
    grid_shape = (2, 3)
    y, mask, t = _batch(*grid_shape)
    cold = _cold(y, mask, t)
    warm = _warm_near(cold)
    valid = np.ones((y.shape[0], len(_SPECS)), dtype=np.bool_)
    valid[0, :] = False
    valid[5, :] = False

    got, counts = _map(y, mask, t, warm, valid, grid_shape=grid_shape)

    assert counts.excluded == 2
    assert int((got == SELECTED_UNSET).sum()) == 2
    assert int((got == -1).sum()) == 0


# ---------------------------------------------------------------------------
# The degenerate cell: counted, and kept
# ---------------------------------------------------------------------------


def test_a_zero_distance_point_is_counted_and_kept_with_its_cold_value():
    """At a matched distance of zero the random start IS the cold start.

    Behaviour: `degenerate` cells are reported, not excluded. Their N2 value is
    a correct floor reading -- an equal-distance random start of distance zero
    -- and it necessarily equals cold's.

    Expected values determined independently: with `warm == cold` at a point the
    distance is exactly 0, so `n2 = cold + 0 * direction = cold` and the fit is
    bit-identical to the cold arm's; the point is counted once under
    `zero_distance` and not at all under `excluded`.

    Bug this catches, in both directions. Excluding degenerate cells discards a
    correct reading for having an inconvenient answer, which is the shape D8
    refuses. NOT counting them hides a floor built largely from cells that agree
    with cold BY CONSTRUCTION -- which would read as "a random start reproduces
    the selection", the strongest possible floor, from a fixture that never
    moved.
    """
    grid_shape = (2, 2)
    y, mask, t = _batch(*grid_shape)
    cold = _cold(y, mask, t)
    warm = _warm_near(cold)
    for model, width in enumerate(_EXTENTS):
        warm[0, model, :width] = cold[0, model, :width]
    valid = np.ones((y.shape[0], len(_SPECS)), dtype=np.bool_)

    got, counts = _map(y, mask, t, warm, valid, grid_shape=grid_shape)

    arms = run_arms(
        y,
        t,
        _SIGNAL,
        _SPECS,
        _CRITERION,
        mask=mask,
        warm=warm,
        warm_valid=valid,
        points=np.arange(y.shape[0], dtype=np.int64),
        seed=_SEED,
        max_iter=_MAX_ITER,
    )
    assert arms.starts.degenerate[0].all(), "fixture failed to be degenerate"
    assert counts.zero_distance == 1
    assert counts.excluded == 0
    assert got.reshape(-1)[0] != SELECTED_UNSET
    assert got.reshape(-1)[0] == arms.results[Arm.COLD].ranking.best_index[0]


# ---------------------------------------------------------------------------
# The key: grid-global, and what that does and does not guarantee
# ---------------------------------------------------------------------------


def test_adding_rows_does_not_move_an_existing_points_n2_direction():
    """The direction is keyed on the grid-global index, not on a row number.

    Behaviour: growing the field along the NORMAL axis leaves every existing
    point's row-major flat index unchanged, so its N2 start, and therefore its
    map value, does not move.

    Expected value determined independently: the flat index is
    `iy * n_parallel + ix`; adding rows changes neither term for an existing
    point. The two maps are built from the same observations for the shared
    points, so their values must agree there.

    Bug this catches: the keying regressing to a position in the batch -- the
    (k) finding 2c recorded. **Recording the seed does not save you from it**:
    the same seed under a different point set gives different directions, so
    two maps over one field would stop being comparable while both remained
    perfectly reproducible.

    **THE OBSERVABLE IS THE EXCLUSION PATTERN, NOT THE SELECTION, AND THAT IS
    WHAT MAKES THIS TEST ABLE TO SEE ITS OWN SUBJECT.** On white noise every
    point selects `white` whatever it started from, so a map compared value by
    value is a constant and a re-keyed direction changes nothing observable --
    the test would pass while the directions moved underneath it. Found by
    mutation: renumbering the point set left the earlier version green. The
    warm start is therefore pushed to the box WALL, where whether N2 remains
    admissible depends on the direction drawn and therefore on the key, so the
    pattern of excluded points is a direct readout of the keying -- and it
    needs no converged fit.
    """
    small_shape, large_shape = (2, 2), (4, 2)
    y_large, mask_large, t = _batch(*large_shape)
    shared = small_shape[0] * small_shape[1]
    y_small, mask_small = y_large[:shared], mask_large[:shared]

    cold_large = _cold(y_large, mask_large, t)
    warm_large = _push_to_the_wall(_warm_near(cold_large), cold_large)
    valid_large = np.ones((y_large.shape[0], len(_SPECS)), dtype=np.bool_)

    cold_small = _cold(y_small, mask_small, t)
    warm_small = _push_to_the_wall(_warm_near(cold_small), cold_small)
    valid_small = np.ones((shared, len(_SPECS)), dtype=np.bool_)

    large, large_counts = _map(
        y_large, mask_large, t, warm_large, valid_large, grid_shape=large_shape
    )
    small, small_counts = _map(
        y_small, mask_small, t, warm_small, valid_small, grid_shape=small_shape
    )

    missing_small = small.reshape(-1) == SELECTED_UNSET
    missing_large = large.reshape(-1)[:shared] == SELECTED_UNSET
    assert 0 < int(missing_small.sum()) < shared, (
        "fixture is vacuous: the shared points are all excluded or none are, "
        "so a re-keyed direction would change nothing observable"
    )
    assert np.array_equal(missing_small, missing_large)
    assert np.array_equal(small.reshape(-1), large.reshape(-1)[:shared])
    assert small_counts.excluded <= large_counts.excluded


def test_adding_columns_does_move_the_key_and_the_module_says_so():
    """The guarantee is one axis wide, and the limitation is pinned.

    Behaviour: the key is a flat index into a 2-D grid, so it depends on the
    grid's stride. Growing along the PARALLEL axis moves every existing point's
    index but the first row's, and therefore its direction.

    Expected value determined independently: the GRID POSITION `(1, 0)` has
    flat index `1 * 3 + 0 = 3` in a 3-wide grid and `1 * 4 + 0 = 4` in a 4-wide
    one. Different keys give different directions, hence different N2 starts.
    Position `(0, 0)` is index 0 in both, so the first row is unaffected.

    Bug this catches: the module docstring claiming an invariance the key does
    not have. This test asserts the CURRENT, DOCUMENTED behaviour rather than a
    desired one -- so a later change to the key breaks it and forces the
    docstring to move with the code, which is the only way a stated limitation
    stays true. A flat index cannot be invariant to a change in stride, and the
    alternative key is unavailable: `arm_directions` takes the index that
    `SourceMap` and pass 1's store are both written against, so a second key
    here would be a second N2.
    """
    narrow_shape, wide_shape = (2, 3), (2, 4)
    narrow = n2map.point_directions(narrow_shape, _EXTENTS, seed=_SEED)
    wide = n2map.point_directions(wide_shape, _EXTENTS, seed=_SEED)

    # Grid position (1, 0): flat index 3 when the grid is 3 wide, 4 when it is 4.
    assert not np.array_equal(narrow[3], wide[4], equal_nan=True), (
        "the same grid position must get a different key once the stride moves"
    )
    # Grid position (0, 0): flat index 0 in both, so the first row is unmoved.
    assert np.array_equal(narrow[0], wide[0], equal_nan=True)
    assert n2map.__doc__ is not None
    assert "stride" in n2map.__doc__, "the limitation must be stated at the module"


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_a_batch_that_is_not_the_whole_grid_is_refused():
    """A full-field map is every point, so the count is checked.

    Behaviour: `n2_field_map` derives its point set as
    `arange(n_normal * n_parallel)`, so a batch of a different size is not the
    field it claims to be.

    Expected value determined independently: a `(4, 3)` grid is 12 points; a
    10-row batch is not.

    Bug this catches: a caller handing in a subset and receiving a map whose
    points are keyed against positions the data does not occupy. Every array
    would still have a shape and every value would still be a candidate index,
    so the map would be silently mis-keyed and the audit's N2 at a given point
    would no longer be the map's.
    """
    grid_shape = (4, 3)
    y, mask, t = _batch(*grid_shape)
    cold = _cold(y, mask, t)
    warm = _warm_near(cold)
    valid = np.ones((y.shape[0], len(_SPECS)), dtype=np.bool_)

    with pytest.raises(ValueError, match="full-field map is every point"):
        _map(y[:10], mask[:10], t, warm[:10], valid[:10], grid_shape=grid_shape)


def test_the_map_carries_the_grids_shape_and_the_stores_dtype():
    """The map is a grid of candidate indices, not a flat batch of them.

    Behaviour: the return is shaped `grid_shape` and typed `int16`, which is
    `/selection/selected`'s own dtype and the one whose sentinel vocabulary the
    map uses.

    Expected values determined independently: the grid is `(4, 3)`, and `int16`
    is the store's declared type for the selection array.

    Bug this catches: returning the flat batch. `smear_width` takes a 2-D map
    and a `normal_axis`, so a flat array would raise there rather than here --
    at a call site whose error would describe the estimator rather than the
    map's shape, sending the next reader at the wrong module.
    """
    grid_shape = (3, 2)
    y, mask, t = _batch(*grid_shape)
    cold = _cold(y, mask, t)
    warm = _warm_near(cold)
    valid = np.ones((y.shape[0], len(_SPECS)), dtype=np.bool_)

    got, _ = _map(y, mask, t, warm, valid, grid_shape=grid_shape)

    assert got.shape == grid_shape
    assert got.dtype == np.int16
