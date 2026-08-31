"""`metamer.bench.smear`: the misclassification profile, and its interior null.

**THE SUBJECT IS CATEGORICAL AND THAT IS WHY THIS MODULE EXISTS AS ITS OWN
THING.** Since Task 1 the benchmark's boundary is a change of *family*, so the
parameter that steps is not the same parameter either side of it and a width
*"of sigma"* would be a width of two different quantities. `fields.SMEAR_SUBJECT`
is the selected candidate; the estimator reduces it to a per-point agreement
indicator, averages that along the boundary into a **misclassification
profile**, and reports the width of the majority-misclassified run about the
boundary.

**EVERY TEST HERE RUNS ON A CONSTRUCTED MAP.** No field is built, no fit runs,
nothing is written. The plan placed Tasks 2 and 3 independent of everything for
exactly this reason, and a categorical estimator is *easier* to construct
adversarial inputs for than a continuous one -- a map either misclassifies a
cell or it does not, so every expected value below is an integer read off the
construction rather than a tolerance around a fit.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import numpy as np
import pytest

from metamer.bench import fields, smear
from metamer.config.model import WarmStart

_N = fields.N_NORMAL  # 32
_P = fields.N_PARALLEL  # 12
_B = fields.BOUNDARY_INDEX  # 16
_REACH = 32.0  # `spiral_bound(4) * coarse_stride(8)`, asserted in C1


def _clean(*, n_normal: int = _N, n_parallel: int = _P) -> np.ndarray:
    """A disagreement map on which every point selected its regime's truth."""
    return np.zeros((n_normal, n_parallel), dtype=np.float64)


def _with_band(
    rows: Iterable[int],
    *,
    disagreeing: int | None = None,
    n_normal: int = _N,
    n_parallel: int = _P,
) -> np.ndarray:
    """A clean disagreement map with `rows` misclassified.

    `disagreeing` is the COUNT of points on each such line that disagree, out of
    `n_parallel`. Defaulting to all of them keeps the fixtures away from the
    majority threshold except where a test is aimed at it.
    """
    m = _clean(n_normal=n_normal, n_parallel=n_parallel)
    count = n_parallel if disagreeing is None else disagreeing
    for row in rows:
        m[row, :count] = 1.0
    return m


def _width(field_map, **kwargs):
    """`smear_width` with the shipped geometry and a named map and arm."""
    kwargs.setdefault("boundary_index", _B)
    kwargs.setdefault("normal_axis", 0)
    kwargs.setdefault("reach_cells", _REACH)
    kwargs.setdefault("map_name", smear.AGREEMENT_MAP_NAME)
    kwargs.setdefault("arm", "warm")
    return smear.smear_width(field_map, **kwargs)


def _family(*, n_normal: int = _N, n_parallel: int = _P) -> np.ndarray:
    """The two regimes' true family indices, stiffer family first.

    Built here rather than taken from `fields`, so the oracle does not share a
    derivation path with the thing it checks -- (j).
    """
    truth = np.zeros((n_normal, n_parallel), dtype=np.int8)
    truth[:_B, :] = 1
    return truth


# ---------------------------------------------------------------------------
# `agreement_map` -- the one step that reads the truth
# ---------------------------------------------------------------------------


def test_a_selection_that_matches_every_points_own_regime_disagrees_nowhere():
    """A perfect classifier gives an all-zero disagreement map.

    Behaviour: the map is DISAGREEMENT -- 0 where the winning candidate carries
    the point's true family, 1 where it does not.

    Expected value determined independently: candidate 1 is
    `"white + matern12"` and family index 0 is `"matern12"`; candidate 2 is
    `"white + matern32"` and family index 1 is `"matern32"`. Selecting by that
    correspondence is correct at every point, so every entry is 0.

    Bug this catches: an INVERTED indicator -- agreement where disagreement was
    meant. Every width would then measure the band where the fit was RIGHT, and
    a clean field would read as a smear spanning the whole axis rather than as
    the floor. It is the one defect that makes every downstream number wrong in
    the alarming direction while looking like a working instrument.
    """
    family = _family()
    selected = np.where(family == 0, 1, 2).astype(np.int16)

    got = smear.agreement_map(selected, family)

    assert np.array_equal(got, np.zeros((_N, _P)))


def test_a_selection_carrying_the_other_regimes_family_disagrees_everywhere():
    """The two Matern candidates are distinguishable, and the map says so.

    Behaviour: a point whose winner carries the *other* regime's family is a
    misclassification and scores 1.

    Expected value determined independently: the inverse of the correspondence
    above, applied at every point, so every entry is 1.

    Bug this catches: a candidate-to-family mapping that resolves BOTH Matern
    candidates to one family -- for instance by matching on the substring
    `"matern"`, or by taking a `ProcessSpec`'s first term after canonical
    sorting without checking its kind. The boundary in this benchmark IS the
    difference between those two candidates, so that mapping returns an
    all-zero map on every field ever built and reports the floor at every rung,
    which reads as *"no artifact"* and is the confident null this project has
    been bitten by three times.
    """
    family = _family()
    selected = np.where(family == 0, 2, 1).astype(np.int16)

    got = smear.agreement_map(selected, family)

    assert np.array_equal(got, np.ones((_N, _P)))


def test_the_family_free_candidate_disagrees_in_both_regimes():
    """Choosing `"white"` is a misclassification on both sides of the step.

    Behaviour: a winning candidate that carries neither family agrees with
    neither regime. `"white"` is in `fields.CANDIDATES`, so this is a path the
    benchmark will actually take, not a hypothetical.

    Expected value determined independently: `"white"` parses to a single
    `white` term and neither `FAMILY_KINDS` entry is among its kinds, so it
    matches no regime and scores 1 in both.

    Bug this catches: an unmatched candidate DEFAULTING to agreement -- the
    shape where a lookup misses and the code falls through to zero. That turns
    *"the fit chose the null model"* into *"the fit was right"*, and it is
    silent precisely where the data is least informative, which is where a
    warm start's influence is largest.
    """
    family = _family()
    selected = np.zeros((_N, _P), dtype=np.int16)

    got = smear.agreement_map(selected, family)

    assert np.array_equal(got[:_B], np.ones((_B, _P))), "stiff regime"
    assert np.array_equal(got[_B:], np.ones((_N - _B, _P))), "soft regime"


@pytest.mark.parametrize("sentinel", [-1, -2])
def test_a_selection_sentinel_becomes_nan_rather_than_a_verdict(sentinel):
    """`-1` (no winner) and `-2` (unwritten) are absences, not misclassifications.

    Behaviour: `/selection/selected` is `int16` and carries both sentinels. A
    cell holding one made no selection, so it contributes to neither side of
    the profile.

    Expected value determined independently: from the store's own vocabulary --
    `-1` means *"no winner"* and `SELECTED_UNSET` is `-2`. Neither is an index
    into `CANDIDATES`, so neither can agree or disagree with anything.

    Bug this catches: an integer sentinel compared straight against the truth
    index, coming out unequal, and being counted as a MISCLASSIFICATION. That
    manufactures smear out of cells where nothing was written or nothing won --
    and those cluster where fits are hardest, which is at the boundary. The
    resulting width would be largest on exactly the rungs where the artifact is
    expected, so it would confirm the hypothesis by construction.
    """
    family = _family()
    selected = np.where(family == 0, 1, 2).astype(np.int16)
    selected[_B, 0] = sentinel

    got = smear.agreement_map(selected, family)

    assert np.isnan(got[_B, 0])
    assert int(np.isnan(got).sum()) == 1, "only the sentinel cell is an absence"
    assert not np.nansum(got), "no other cell became a misclassification"


def test_agreement_is_keyed_to_each_points_own_truth_and_not_to_one_family():
    """The comparison is per point, so one regime can be right while the other is wrong.

    Behaviour: the truth is a field, not a constant, and agreement is evaluated
    against the family true AT that point.

    Expected value determined independently: with `"white + matern32"` selected
    everywhere, the stiff regime (`family == 1`, rows below the boundary) is
    correct and the soft regime (`family == 0`) is not. So the map is 0 above
    the boundary index and 1 at and below it -- an ASYMMETRIC expectation,
    chosen because a symmetric fixture passes even when the two sides are
    swapped.

    Bug this catches: comparing against `FAMILY_KINDS[0]` -- or against the
    truth at one representative point -- everywhere. One whole regime then
    reads as 100% disagreement, the profile becomes a step rather than a band,
    and the majority run grows from the boundary to the edge of the field:
    a spectacular width on every rung, from a bug in the oracle rather than an
    artifact in the fits.
    """
    family = _family()
    selected = np.full((_N, _P), 2, dtype=np.int16)

    got = smear.agreement_map(selected, family)

    assert np.array_equal(got[:_B], np.zeros((_B, _P))), "stiff regime is correct"
    assert np.array_equal(got[_B:], np.ones((_N - _B, _P))), "soft regime is not"


def test_a_selection_index_outside_the_candidate_set_is_refused():
    """An index no candidate has is an error, not a misclassification.

    Behaviour: `selected` indexes `fields.CANDIDATES`; an index at or beyond
    `M` is not a selection this benchmark can interpret.

    Expected value determined independently: `CANDIDATES` has three members, so
    3 is the first invalid non-sentinel index.

    Bug this catches: the wrong axis being handed in. `/selection/selected` is
    `(y, x, c)` over criteria, and a caller that forgets to pick a criterion --
    or picks the wrong one from a longer axis -- produces indices that are
    arithmetically fine and semantically meaningless. Counted as
    disagreements, they would raise the profile uniformly and shift every
    width; refused, they surface at the caller.
    """
    family = _family()
    selected = np.where(family == 0, 1, 2).astype(np.int16)
    selected[0, 0] = len(fields.CANDIDATES)

    with pytest.raises(ValueError, match="candidate"):
        smear.agreement_map(selected, family)


# ---------------------------------------------------------------------------
# `smear_width` -- the floor, the run, and the ceiling
# ---------------------------------------------------------------------------


def test_a_map_with_no_misclassification_anywhere_reports_the_floor():
    """A perfect step in the selection reads as unresolved, never as a width.

    Behaviour: the width of a run that does not exist is 0, and 0 is at or
    below the 1-cell floor, so the reading is `<= 1 cell` with no number.

    Expected value determined independently: no cell exceeds the majority
    threshold, so the run about the boundary is empty.

    Bug this catches: an estimator that returns a width for a step. Its own
    bias would then be added to EVERY rung's number, and because the bias is
    the same at every rung it would survive the monotonicity check that Task 7
    reads as evidence.

    This test is vacuous on its own -- an estimator returning the floor for
    every input also passes it. The paired positive control below is what makes
    it bite.
    """
    reading = _width(_clean())

    assert reading.at_floor is True
    assert reading.cells is None
    assert reading.refused is None
    assert reading.floor_cells == 1.0


def test_a_constructed_five_cell_band_at_the_boundary_measures_five_cells():
    """The positive control: a band the estimator must resolve, and its size.

    Behaviour: the width is the length in fine cells of the majority-
    misclassified run containing a cell adjacent to the boundary.

    Expected value determined independently: rows 16, 17, 18, 19 and 20 are
    fully misclassified and nothing else is; the run containing the boundary
    cell is exactly those five, so the width is 5.0 -- EXACTLY, with no
    tolerance, because a run length is an integer count of cells.

    Bug this catches: an estimator that returns the floor for everything. That
    reads as *"no artifact"* on every field, at every rung, and it passes the
    interior-null criterion for the worst possible reason -- the gate would be
    green because the instrument is dead, not because the field is clean.
    """
    reading = _width(_with_band(range(_B, _B + 5)))

    assert reading.cells == 5.0
    assert reading.at_floor is False
    assert reading.refused is None


def test_a_one_cell_band_is_reported_as_the_floor_and_never_as_the_number_one():
    """At the resolution limit the instrument says so instead of quoting a value.

    Behaviour: on a grid the finest resolvable width is one fine cell, so a
    measured width of 1 means *unresolved*, not *one*.

    Expected value determined independently: a single misclassified row is a
    run of length 1, which is the floor.

    Bug this catches: emitting `1.0`. A number at the resolution limit gets
    quoted downstream as a resolved measurement -- and it is the value the
    estimator is likeliest to produce from its own sampling noise, since a
    single spurious majority cell on a 12-point line is a few percent likely at
    any plausible baseline. Emitting it would put noise into the README figure
    as a measured smear.
    """
    reading = _width(_with_band([_B]))

    assert reading.at_floor is True
    assert reading.cells is None


def test_a_width_beyond_the_spiral_reach_is_refused_rather_than_reported():
    """A physically impossible width is withheld, with the reach in the reason.

    Behaviour: no point can be biased by a source the spiral never reached, so
    a run longer than `reach_cells` is not a smear and is refused as a reading.

    Expected value determined independently: a 6-cell band against a reach of
    4 cells; 6 > 4.

    Bug this catches: an arithmetically fine, physically impossible reading
    being emitted as a smear. It would be the largest number 2d produces and
    therefore the one most likely to be quoted -- and it would be evidence that
    the profile is measuring the true field's own structure, which is a defect
    report rather than a result.
    """
    reading = _width(_with_band(range(_B, _B + 6)), reach_cells=4.0)

    assert reading.cells is None
    assert reading.refused is not None
    assert "4" in reading.refused


def test_the_refusal_admits_a_width_at_the_reach_and_rejects_the_next_cell():
    """The ceiling is inclusive, and the test pins which side each case falls.

    Behaviour: `width > reach_cells` refuses; `width == reach_cells` does not.
    A source exactly at the spiral's furthest reach is reachable.

    Expected values determined independently: a 4-cell band against a reach of
    4 is admissible and measures 4.0; a 5-cell band against the same reach is
    not.

    Bug this catches: an off-by-one at the refusal boundary -- `>=` for `>`.
    That silently discards the single reading the ceiling exists to
    discriminate, the one at the reach exactly, and it fails in the direction
    that removes evidence rather than adding it, so nothing downstream would
    ever notice a missing row.
    """
    admitted = _width(_with_band(range(_B, _B + 4)), reach_cells=4.0)
    refused = _width(_with_band(range(_B, _B + 5)), reach_cells=4.0)

    assert admitted.cells == 4.0
    assert admitted.refused is None
    assert refused.cells is None
    assert refused.refused is not None


def test_seven_of_twelve_is_a_majority_and_six_of_twelve_is_not():
    """The threshold is a STRICT majority, and the tie is not one.

    Behaviour: a cell is smeared when more than half of its parallel line
    misclassifies.

    Expected value determined independently, as arithmetic and not from the
    implementation: the line is 12 points. 7/12 = 0.5833... > 1/2, so those
    cells are smeared and the run is 5 cells. 6/12 = 1/2 exactly, which is a
    DEAD HEAT and not a majority, so those cells are not smeared and the run
    about the boundary is empty.

    Bug this catches: `>=` where `>` was meant -- the natural-looking edit, and
    the one a later reader is likeliest to make. It counts a dead-even line as
    misclassified, which inflates every width on every rung. It also costs the
    threshold its best property: at a coin-flip baseline a strict majority of
    12 fires only 38.7% of the time, precisely because ties do not count, and
    `>=` raises that to 61.3%.
    """
    majority = _width(_with_band(range(_B, _B + 5), disagreeing=7))
    tie = _width(_with_band(range(_B, _B + 5), disagreeing=6))

    assert majority.cells == 5.0
    assert tie.at_floor is True
    assert tie.cells is None


def test_the_profile_is_taken_across_the_boundary_on_either_axis_order():
    """`normal_axis` selects the axis; the same field gives the same width.

    Behaviour: the profile is the map averaged PARALLEL to the boundary, giving
    a function of distance along the normal, whichever axis the caller stored
    the normal on.

    Expected value determined independently: the transpose of the 5-cell
    fixture, read with `normal_axis=1`, is the same field and must give 5.0.

    Bug this catches: an estimator that hard-codes axis 0. Handed a transposed
    map it would profile ALONG the boundary instead of across it, producing a
    12-long profile in which the boundary does not appear at all -- and, since
    that profile is flat, it would report the floor. A silent
    *"no artifact found"* from reading the field sideways.
    """
    reading = _width(_with_band(range(_B, _B + 5)).T, normal_axis=1)

    assert reading.cells == 5.0


def test_an_unfitted_line_parallel_to_the_normal_does_not_shorten_the_profile():
    """A missing column is averaged around, not averaged away.

    Behaviour: the profile is a NaN-aware mean along the parallel axis, so a
    line of points that produced no selection reduces the count at each normal
    index without removing any index.

    Expected value determined independently: with one of twelve parallel
    positions unfitted, a fully misclassified row is 11/11 and a clean row is
    0/11. Neither crosses the threshold differently, so the width is still 5.0
    and the profile is still 32 long.

    Bug this catches: `mean` where `nanmean` was meant, which turns the ENTIRE
    profile into NaN and reports the floor for every field; or a mask-and-
    compress that drops incomplete rows, which shortens the profile and moves
    the boundary index off the cell it names. Both fail quietly and both fail
    towards a smaller width.
    """
    field_map = _with_band(range(_B, _B + 5))
    field_map[:, 3] = np.nan

    reading = _width(field_map)

    assert reading.cells == 5.0
    assert len(reading.profile) == _N


@pytest.mark.parametrize(
    ("row", "where"),
    [(_B + 5, "just beyond the run"), (_B - 1, "a seed cell")],
)
def test_an_unfitted_row_the_run_had_to_decide_about_refuses_the_reading(row, where):
    """A NaN where the run would have grown is withheld, not treated as a stop.

    Behaviour: a normal index the run had to decide about -- a seed cell, or
    the first cell past either end of the run -- must carry a value. Missing,
    the width is not determined and the reading is refused.

    Expected value determined independently: the 5-cell band occupies rows
    16-20, so the run's growth is decided at row 21 and at the seed pair
    (15, 16). Row 21 and row 15 are each such a cell.

    Bug this catches: a NaN terminating the run exactly as a below-threshold
    cell does. The run would stop at the missing row and the width would come
    back SHORTER -- always in the reassuring direction, and indistinguishable
    in the report from a genuinely narrow smear. Failed fits are commonest
    where the artifact is largest, so the bias is strongest exactly where the
    measurement matters.
    """
    field_map = _with_band(range(_B, _B + 5))
    field_map[row, :] = np.nan

    reading = _width(field_map)

    assert reading.cells is None, where
    assert reading.refused is not None


def test_an_unfitted_row_far_from_the_band_refuses_nothing():
    """The refusal is bounded, or a partially fitted field reports nothing at all.

    Behaviour: a NaN that cannot change the width does not withhold it. Only
    the cells the run had to decide about are load-bearing.

    Expected value determined independently: row 30 is ten cells past the end
    of the 16-20 band, so no growth decision touches it; the width is still
    5.0.

    Bug this catches: the opposite failure to the test above -- a refusal so
    broad that any field with a single failed row becomes unreadable. Task 5's
    rung would then produce a refused reading rather than a number, and the
    sub-phase would stop on an instrument that was working. The asymmetry
    between this test and the one above is the whole design of the rule, and
    either test alone licenses the wrong fix.
    """
    field_map = _with_band(range(_B, _B + 5))
    field_map[30, :] = np.nan

    reading = _width(field_map)

    assert reading.cells == 5.0
    assert reading.refused is None


def test_a_band_away_from_the_boundary_is_not_the_smear():
    """The run is seeded at the boundary, not at the profile's largest feature.

    Behaviour: the width is the run containing a cell ADJACENT TO THE BOUNDARY.
    Misclassification elsewhere is not a boundary smear.

    Expected value determined independently: a 5-cell band at rows 5-9 with
    nothing at rows 15 or 16; the run about the boundary is empty, so the
    reading is the floor.

    Bug this catches: an estimator that finds the widest majority run anywhere
    on the axis. It would report the field's own structure -- or a patch of
    genuinely hard cells -- as the smear, which is exactly the contamination
    E6's third row gates against, arriving through the width rather than
    through the null. Worse, it would make the interior null unable to fail:
    both calls would find the same largest run and agree.
    """
    reading = _width(_with_band(range(5, 10)))

    assert reading.at_floor is True
    assert reading.cells is None


def test_the_same_map_gives_the_same_reading_twice():
    """No randomness. The estimator is a function of its input.

    Behaviour: the plan's first invariant.

    Expected value determined independently: equality of two calls on one
    array.

    Bug this catches: any iteration over a set, any unseeded tie-break, any
    dependence on array identity -- each of which would make a rung's committed
    report unreproducible, and the committed report is what Task 9's exit
    criteria assert against.
    """
    field_map = _with_band(range(_B, _B + 5))

    assert _width(field_map) == _width(field_map)


@pytest.mark.parametrize("blank", ["estimator", "map_name", "arm"])
def test_a_reading_cannot_be_built_without_saying_what_produced_it(blank):
    """Instrument, map and arm are construction requirements, not conventions.

    Behaviour: `"the smear width"` is a family of numbers; a reading names
    which scalar, which arm and which estimator produced it.

    Expected value determined independently: each of the three fields is
    required, so an empty one is refused -- tested one at a time so a check
    covering only the first cannot pass.

    Bug this catches: a width quoted in the README figure or the rung report
    with no instrument beside it. (j8): an adopted verdict makes the instrument
    part of the specification, and a rule stated in a docstring constrains
    nobody.
    """
    kwargs: dict[str, Any] = {
        "cells": 5.0,
        "at_floor": False,
        "floor_cells": 1.0,
        "reach_cells": _REACH,
        "estimator": smear.ESTIMATOR,
        "map_name": smear.AGREEMENT_MAP_NAME,
        "arm": "warm",
        "refused": None,
        "profile": (0.0,) * _N,
    }
    kwargs[blank] = "  "

    with pytest.raises(ValueError, match=blank):
        smear.WidthReading(**kwargs)


@pytest.mark.parametrize("boundary_index", [0, _N])
def test_a_boundary_at_the_edge_of_the_grid_is_refused(boundary_index):
    """Both seed cells must exist, and index -1 is not a seed cell.

    Behaviour: the seed pair is `(boundary_index - 1, boundary_index)`, so the
    boundary must have a cell on each side of it.

    Expected value determined independently: at `boundary_index = 0` the lower
    seed is -1; at `boundary_index = 32` the upper seed is off a 32-long
    profile.

    Bug this catches: NumPy's negative indexing. `profile[-1]` is the LAST cell
    of the field, so a boundary at 0 would silently seed the run at the far
    edge of the grid and measure the opposite regime's interior as the smear --
    a plausible number, produced from the wrong end of the field, with nothing
    in the output to show it.
    """
    with pytest.raises(ValueError, match="boundary"):
        _width(_clean(), boundary_index=boundary_index)


# ---------------------------------------------------------------------------
# `interior_null` -- the gate, and its own positive control
# ---------------------------------------------------------------------------


def test_the_interior_null_returns_the_floor_on_a_map_whose_only_band_is_at_the_boundary():
    """The negative control: away from the step, there is nothing to find.

    Behaviour: the same estimator, seeded at a false boundary `offset_cells`
    from the real one, where the truth has no transition.

    Expected value determined independently: the band is at rows 16-20; the
    false boundary is at 16 - 12 = 4, whose seed pair (3, 4) is clean. The run
    is empty, so the reading is the floor.

    Bug this catches: a null that reaches the real boundary's band -- by
    seeding at the true boundary, or by searching the whole axis for the widest
    run. It would return a width at every rung, and by E6's third row that
    STOPS THE SUB-PHASE. A gate that fires on a healthy instrument is as
    expensive as one that never fires.
    """
    reading = smear.interior_null(
        _with_band(range(_B, _B + 5)),
        boundary_index=_B,
        normal_axis=0,
        offset_cells=fields.NULL_LINE_OFFSET_CELLS,
        reach_cells=_REACH,
        map_name=smear.AGREEMENT_MAP_NAME,
        arm="warm",
    )

    assert reading.at_floor is True
    assert reading.cells is None


def test_the_interior_null_fires_on_a_map_whose_band_sits_on_the_null_line():
    """The paired positive: the gate CAN fail, so its passing means something.

    Behaviour: the null uses the same estimator, so a band at the null line is
    measured exactly as a band at the boundary would be.

    Expected value determined independently: rows 3, 4 and 5 misclassified; the
    false boundary at index 4 has seed pair (3, 4), both smeared, and the run
    is those three rows. So the width is 3.0.

    Bug this catches: a null-line check that cannot fire -- one that returns
    the floor unconditionally, or that reads a different quantity from the one
    it gates. E6 calls this the clause most expected to fire and the one that
    gates the sub-phase; an unfalsifiable version of it would license every
    smear number on every rung, which is the largest single failure available
    to 2d.
    """
    reading = smear.interior_null(
        _with_band([3, 4, 5]),
        boundary_index=_B,
        normal_axis=0,
        offset_cells=fields.NULL_LINE_OFFSET_CELLS,
        reach_cells=_REACH,
        map_name=smear.AGREEMENT_MAP_NAME,
        arm="warm",
    )

    assert reading.cells == 3.0
    assert reading.at_floor is False


def test_the_null_reading_names_its_instrument_map_and_arm_like_any_other():
    """A control is reported in the same currency as a measurement.

    Behaviour: `interior_null` returns a `WidthReading`, carrying the same
    estimator name, map name and arm.

    Expected value determined independently: the constants passed in, and
    `smear.ESTIMATOR`.

    Bug this catches: a control whose output cannot be told from a measurement
    once both are in the report -- or one that quietly uses a different
    estimator, which would make the gate a check on some other instrument than
    the one producing the widths.
    """
    reading = smear.interior_null(
        _with_band(range(_B, _B + 5)),
        boundary_index=_B,
        normal_axis=0,
        offset_cells=fields.NULL_LINE_OFFSET_CELLS,
        reach_cells=_REACH,
        map_name=smear.AGREEMENT_MAP_NAME,
        arm="n2",
    )

    assert reading.estimator == smear.ESTIMATOR
    assert reading.map_name == smear.AGREEMENT_MAP_NAME
    assert reading.arm == "n2"


@pytest.mark.parametrize(
    ("offset_cells", "why"),
    [
        (4, "inside one coarse spacing of the boundary"),
        (_B, "off the grid"),
        (_B + 4, "past the grid"),
    ],
)
def test_a_null_line_that_is_not_a_control_raises_rather_than_reading(
    offset_cells, why
):
    """The null must be outside the coupling range and on the grid.

    Behaviour: the offset is at least one coarse spacing -- no point on the
    null line can then have been warm-started across the step -- and the
    resulting index must have a cell on each side of it.

    Expected values determined independently: `COARSE_STRIDE` is 8, so 4 is
    inside the coupling range; the boundary is at 16, so an offset of 16 puts
    the false boundary at index 0, whose lower seed does not exist, and 20 puts
    it at -4.

    Bug this catches: a control silently taken INSIDE the coupling range. The
    truth has no transition there, but the warm start's influence does reach,
    so the control would be expected to fire and its passing would mean
    nothing -- an unfalsifiable gate wearing the appearance of a measured one.
    Which side of the range the null sits on is the entire difference between
    a control and a second measurement.
    """
    with pytest.raises(ValueError):
        smear.interior_null(
            _clean(),
            boundary_index=_B,
            normal_axis=0,
            offset_cells=offset_cells,
            reach_cells=_REACH,
            map_name=smear.AGREEMENT_MAP_NAME,
            arm="warm",
        )


# ---------------------------------------------------------------------------
# The reach, read from config
# ---------------------------------------------------------------------------


def test_the_spiral_reach_is_computed_from_the_shipped_warm_start_defaults():
    """32 fine cells, derived rather than written.

    Behaviour: the ceiling is `spiral_bound * coarse_stride`, both from config.

    Expected value determined independently: `WarmStart()` ships
    `spiral_bound = 4` and `coarse_stride = 8`, so the reach is 32 fine cells.
    The assertion checks both the product and the value, because the value
    alone would pass for a literal.

    Bug this catches: 32 frozen as a literal. It would survive a config change
    and then refuse or admit the wrong readings silently -- a physics bound
    that no longer describes the physics, in a check whose whole purpose is to
    refuse readings the physics forbids.
    """
    warm = WarmStart()

    assert smear.spiral_reach_cells() == float(warm.spiral_bound * fields.COARSE_STRIDE)
    assert smear.spiral_reach_cells() == 32.0


def test_a_changed_spiral_bound_moves_the_reach_and_the_refusal_with_it():
    """The bound is read from the config given, not from one read at import.

    Behaviour: `spiral_reach_cells` takes the `WarmStart` it should describe,
    and the refusal boundary follows it.

    Expected values determined independently: at `spiral_bound = 2` the reach
    is 2 * 8 = 16 fine cells. A constructed 20-cell band is admissible against
    the shipped reach of 32 and inadmissible against 16.

    Bug this catches: the reach captured once at import into a module constant.
    A config change would then move the physics and not the check -- and this
    is the only test that would notice, since on the shipped geometry the
    ceiling is unreachable and the refusal never fires on a real field.
    """
    warm = WarmStart(spiral_bound=2)
    assert smear.spiral_reach_cells(warm) == 16.0

    tall = _with_band(range(32, 52), n_normal=64)
    admitted = _width(tall, boundary_index=32, reach_cells=32.0)
    refused = _width(
        tall, boundary_index=32, reach_cells=smear.spiral_reach_cells(warm)
    )

    assert admitted.cells == 20.0
    assert refused.cells is None
    assert refused.refused is not None


def test_the_agreement_maps_name_is_built_from_the_subject_it_reads():
    """One spelling of the subject, in the name that reaches the report.

    Behaviour: `AGREEMENT_MAP_NAME` is derived from `fields.SMEAR_SUBJECT`
    rather than written again.

    Expected value determined independently: `SMEAR_SUBJECT` is
    `"selected candidate"`, so the map name contains it.

    Bug this catches: a second spelling of the subject appearing in the report
    -- (j9), which has fired five times in this sub-phase, most recently on an
    instrument block that was itself a copy. Two names for one map is how a
    reader concludes there were two maps.
    """
    assert fields.SMEAR_SUBJECT in smear.AGREEMENT_MAP_NAME

    reading = _width(_clean())

    assert reading.map_name == smear.AGREEMENT_MAP_NAME


def test_the_null_lines_index_and_offset_are_one_quantity():
    """`NULL_LINE_INDEX` is derived from the offset, not written beside it.

    Behaviour: the null line has one location. The offset is the parameter the
    estimator takes; the index is what that offset lands on.

    Expected value determined independently: the boundary is at 16 and the
    offset is 12, so the index is 4 -- and 12 exceeds `COARSE_STRIDE` of 8, so
    the line is outside the coupling range.

    Bug this catches: the two drifting. Before this task the constant was
    `NULL_LINE_INDEX = 4` with a docstring saying *"12 cells from it"* -- an
    index and a distance, the same place spelled twice, and moving the boundary
    would have moved one and not the other. (j9)'s exact shape.

    What this test CANNOT distinguish, stated so it is not read as more: a
    derived `NULL_LINE_INDEX` from a literal `4`, since both satisfy the
    identity today. It fires when any of the three constants moves, which is
    the drift it was written for; that the index is derived rather than
    coincidentally right is enforced by the module and not by this assertion.
    """
    assert (
        fields.NULL_LINE_INDEX
        == fields.BOUNDARY_INDEX - fields.NULL_LINE_OFFSET_CELLS
        == 4
    )
    assert fields.NULL_LINE_OFFSET_CELLS > fields.COARSE_STRIDE
