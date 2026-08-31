"""The smear-width estimator, and the interior null that gates the sub-phase.

Design doc §16.2 item 6 asks for the width of the band a warm start smears a
sharp boundary over. **Since Task 1 the boundary is a change of FAMILY**, so the
parameter that steps is not the same parameter either side of it and a width
*"of sigma"* would be a width of two different quantities. `fields.SMEAR_SUBJECT`
names the reading: **the selected candidate**, which is categorical.

## What this module computes, in five steps

1. **`agreement_map` reduces the selection to a per-point DISAGREEMENT
   indicator** -- `0.0` where the winning candidate carries that point's true
   family, `1.0` where it carries the other one or none, `NaN` where nothing was
   selected. **This is the only function here that reads the truth**, which is
   what keeps the plan's *"the estimator reads the true parameter field for the
   boundary index and for nothing else"* literally true of `smear_width`.
2. **The profile is that map's NaN-aware mean along the parallel axis**, so
   `p[i]` is the **fraction of the line at normal index `i` that misclassifies
   its own regime**. It is a misclassification profile, not a transition.
3. **A cell is smeared when a strict majority of its line misclassifies**,
   `p[i] > 1/2`. Six of twelve is a tie and is not a majority.
4. **The width is the length, in fine cells, of the maximal contiguous run of
   smeared cells containing a cell adjacent to the boundary.**
5. **Floor at 1 cell, ceiling at the spiral reach.**

## Why a majority rule and not a half-maximum or an excess mass

Every alternative needs a **baseline** -- the disagreement rate the field would
show with no warm start -- and **there is nowhere on this field to take one.**
The reach is `spiral_bound x coarse_stride = 32` fine cells and `N_NORMAL` is
32, so **every cell of the field is inside the reach** and none is available as
an uncontaminated baseline. An estimator that estimates its own baseline from
data the artifact may have touched is where an estimator hides its own bias.
**The majority rule needs no baseline, and that is the whole of its case.**

## What the majority rule is blind to, with the number attached

**A smear that lifts the disagreement rate to 30% across six cells reads at the
floor** -- `0.30 < 0.5` at each of the six, so no cell is smeared and the width
is 0. **And that is the shape a real artifact is likeliest to take:** a smear
should decay with distance rather than stop at an edge, so its profile is a
slope, a slope crosses a half in exactly one place, and everything below the
crossing becomes nothing. **The estimator is blind to the gradual case by
construction, and worst exactly where the artifact is most physical.**

**SO `WidthReading.profile` IS NOT *A* MITIGATION, IT IS *THE* MITIGATION.** A
floor result is uninterpretable until its profile has been seen to be flat
rather than sloped.

**THE TRIGGER FOR BUYING A SECOND, BASELINE-REFERENCED ESTIMATOR, WRITTEN
BEFORE ANY PROFILE EXISTS:** if any rung's committed profile shows a sustained
elevation above its own baseline that the majority rule does not convert to a
width, buy one. *"Sustained"* and *"elevated"* are deliberately read off the
committed profile rather than fixed here, because **a threshold written now
would be tuned against the first profile that missed it.**

## The floor is a derived threshold, and the run requirement is its other half

A line is `N_PARALLEL = 12` points, so at a baseline disagreement rate `b` a
single cell fires spuriously with probability `P(Binom(12, b) >= 7)`:

| `b` | one cell fires | two adjacent cells fire |
|---|---|---|
| 0.2 | **0.39%** | 0.0000 |
| 0.3 | **3.86%** | **0.0015** |
| 0.4 | **15.8%** | **0.025** |
| 0.5 | **38.7%** | 0.150 |

Below a half even at the coin-flip baseline, **because the tie does not count**
-- the whole return on the strict inequality.

**READ THE 15.8% AS A COUNT.** At `b = 0.4` a 32-cell profile carries **about
five spurious majority cells scattered through it**. The floor does not handle
five; it handles the isolated one. What handles the rest is the **run
requirement**: a spurious cell enters the width only if it is contiguous with
the boundary, and a *reportable* width needs two adjacent fires, at **0.025**.

**THE TWO WORK TOGETHER AND EITHER LOOKS LOCALLY SAFE TO DROP.** Drop the floor
and every isolated seed-cell fire becomes a reported `1.0`; drop the run
requirement and the width becomes a count of scattered noise anywhere on the
axis. **This table is here rather than only in the pre-flight because it is the
arithmetic a later reader needs when they propose lowering the threshold to
catch a subtler smear** -- and by the paragraph above they will, and they will
be right about the smear and wrong about the cost.

## The ceiling cannot fire on 2d's own geometry, and is kept anyway

`spiral_bound(4) x coarse_stride(8) = 32` and `N_NORMAL = 4 x COARSE_STRIDE =
32`, so **the reach is the entire normal axis** and a width above it is not
merely unphysical but arithmetically impossible for a correct run length. **So
on the shipped field the refusal is a self-check on this estimator rather than a
physics filter**, and it is recorded as that rather than dropped as unreachable.
**Two changes restore it to a physics filter: a `spiral_bound` below 4** --
which `test_a_changed_spiral_bound_moves_the_reach_and_the_refusal_with_it`
exercises today -- **or a normal axis longer than the reach**, which needs no
test while `N_NORMAL` is derived from `COARSE_STRIDE` and so is pinned to it.

## One spelling of the stride, and the condition that makes a second one bite

`spiral_reach_cells` multiplies `fields.COARSE_STRIDE`, which already reads
`WarmStart().coarse_stride`; reading `WarmStart().coarse_stride` again here
would be a second spelling of a shipped constant -- (j9), five instances in this
sub-phase. **Two spellings of a DEFAULT cannot disagree, so no test forbids the
second one; the latent instance becomes live the moment anything constructs a
`WarmStart` with a non-default `coarse_stride`**, because then
`fields.COARSE_STRIDE` is still 8 while the reach is computed from the caller's
object, and the two describe different fields.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from metamer.bench.fields import (
    CANDIDATES,
    COARSE_STRIDE,
    FAMILY_KINDS,
    SMEAR_SUBJECT,
)
from metamer.config.candidates import parse_candidate
from metamer.config.model import WarmStart

#: The instrument, named once and stamped on every reading. **THE THRESHOLD IS
#: IN THE NAME** -- (j8): an adopted verdict makes the instrument part of the
#: specification, and a width reported without one is D8's pooled figure in a
#: new place.
ESTIMATOR: str = "majority-run (> 1/2 of the parallel line)"

#: The map `smear_width` is meant to be handed, named from its subject rather
#: than written again.
AGREEMENT_MAP_NAME: str = f"{SMEAR_SUBJECT} agreement"

#: On a grid the finest resolvable width is one fine cell, so a width at or
#: below this means *unresolved*, not *zero*, and is emitted as `<= 1 cell`.
FLOOR_CELLS: float = 1.0

#: A cell is smeared when MORE than this fraction of its parallel line
#: misclassifies. **Strictly more:** a dead-even line is not a majority, and the
#: false-fire table in the module docstring is computed against the strict form.
MAJORITY: float = 0.5

#: `-1` is the store's "no winner" and `-2` its "nothing wrote here". Both are
#: absences rather than verdicts, and both would compare unequal to any truth
#: index if handed straight to a comparison.
_SENTINELS: tuple[int, ...] = (-1, -2)


def spiral_reach_cells(warm: WarmStart | None = None) -> float:
    """Return the furthest a warm start can reach, in fine cells.

    Args:
        warm: The warm-start settings to describe. Defaults to the shipped
            ones. **Taken as an argument rather than read at import**, or a
            config change moves the physics and not the check.

    Returns:
        `spiral_bound * COARSE_STRIDE`, as a float, because it is compared
        against a width.
    """
    settings = WarmStart() if warm is None else warm
    return float(settings.spiral_bound * COARSE_STRIDE)


def _candidate_families(candidates: Sequence[str] = CANDIDATES) -> tuple[int, ...]:
    """Return each candidate's family index, or `-1` for a family-free one.

    **Through the shipped parser and against `FAMILY_KINDS` by kind**, never by
    substring: `"matern12"` is a prefix-free but visually close neighbour of
    `"matern32"`, and the boundary in this benchmark IS the difference between
    the two candidates carrying them.
    """
    resolved: list[int] = []
    for candidate in candidates:
        kinds = {term.kind for term in parse_candidate(candidate).terms}
        matches = [i for i, kind in enumerate(FAMILY_KINDS) if kind in kinds]
        if len(matches) > 1:  # pragma: no cover - no shipped candidate has two
            raise ValueError(
                f"candidate {candidate!r} carries more than one family: {matches}"
            )
        resolved.append(matches[0] if matches else -1)
    return tuple(resolved)


def agreement_map(
    selected: NDArray[np.integer],
    family: NDArray[np.integer],
    *,
    candidates: Sequence[str] = CANDIDATES,
) -> NDArray[np.float64]:
    """Reduce a selection map to a per-point disagreement indicator.

    **THIS IS THE ONLY FUNCTION HERE THAT READS THE TRUTH.** Keeping it separate
    is what lets `smear_width` read the boundary index and nothing else, and it
    puts the candidate-to-family mapping -- the one step that can silently
    collapse both Matern candidates into one -- under its own tests.

    Args:
        selected: Winning candidate index per point, indexing `candidates`.
            `-1` ("no winner") and `-2` (`SELECTED_UNSET`) are absences.
        family: True family index per point, indexing `FAMILY_KINDS`.
        candidates: The candidate set the indices refer to.

    Returns:
        `0.0` where the winner carries that point's true family, `1.0` where it
        does not, `NaN` at a sentinel. **A family-free winner such as `"white"`
        disagrees with both regimes**: it is a selection, and it is not the
        regime's truth.

    Raises:
        ValueError: If `selected` and `family` have different shapes, or if
            `selected` holds a non-sentinel index outside the candidate set --
            which is what a caller who forgot to pick a criterion produces.
    """
    winners = np.asarray(selected)
    truth = np.asarray(family)
    if winners.shape != truth.shape:
        raise ValueError(
            f"selected {winners.shape} and family {truth.shape} describe "
            "different grids"
        )

    present = ~np.isin(winners, _SENTINELS)
    if present.any():
        seen = winners[present]
        # **THE MESSAGE QUOTES THE OFFENDING VALUE, NOT AN EXTREMUM.** A
        # negative non-sentinel and an over-large index are different mistakes,
        # and reporting `max()` for the first names a value that is legal.
        bad = seen[(seen < 0) | (seen >= len(candidates))]
        if bad.size:
            raise ValueError(
                f"selected holds candidate index {int(bad.flat[0])} outside the "
                f"{len(candidates)}-member candidate set; a selection map is "
                "one criterion's slice of /selection/selected"
            )

    lookup = np.asarray(_candidate_families(candidates), dtype=np.int64)
    chosen_family = np.where(present, lookup[np.where(present, winners, 0)], -1)
    disagrees = chosen_family != truth

    out = np.where(disagrees, 1.0, 0.0)
    return np.asarray(np.where(present, out, np.nan), dtype=np.float64)


@dataclass(frozen=True)
class WidthReading:
    """One smear width, with everything needed to quote it.

    **A FLOOR RESULT IS UNINTERPRETABLE UNTIL ITS `profile` HAS BEEN SEEN.** The
    majority rule is blind to a smear that raises the disagreement rate without
    carrying it past a half -- which is the shape a decaying artifact takes --
    so `at_floor` means *"no majority-misclassified band"* and NOT *"nothing
    happened here"*. **Reading `cells is None` without looking at `profile` is
    how a gradual smear gets reported as an absence.** See the module docstring
    for the trigger that would buy a second estimator.

    Attributes:
        cells: The width in fine cells, or `None` when the reading is at the
            floor or refused. **Never a number at the floor**, because on a
            categorical step sub-cell resolution does not exist and a value
            below one cell could only be the estimator's own smoothing.
        at_floor: The width was at or below `floor_cells`, so it is `<= 1 cell`.
        floor_cells: The resolution floor this reading was taken against.
        reach_cells: The ceiling this reading was taken against.
        estimator: Which instrument produced it.
        map_name: Which scalar map it was taken from.
        arm: Which arm the map came from.
        refused: Why the reading is withheld, or `None`. **A refused reading is
            not a small one** -- (a2b): an invalid value is made unavailable
            rather than emitted with a caveat.
        profile: The misclassification profile the width was read off, one
            entry per normal index. Carried because E6's third row says *stop
            and diagnose*, and a diagnosis is made of this. **A profile holding
            NaN makes two otherwise identical readings compare unequal**, since
            `NaN != NaN`; compare `cells`, `at_floor` and `refused` rather than
            whole readings wherever a field may be partly unfitted.

    Raises:
        ValueError: If the estimator, map name or arm is blank. *"The smear
            width"* is a family of numbers and the naked phrase is D8's
            pooled-figure problem in a new place, so the three are construction
            requirements rather than a docstring's request.
    """

    cells: float | None
    at_floor: bool
    floor_cells: float
    reach_cells: float
    estimator: str
    map_name: str
    arm: str
    refused: str | None
    profile: tuple[float, ...]

    def __post_init__(self) -> None:
        """Refuse a reading that does not say what produced it."""
        for name in ("estimator", "map_name", "arm"):
            if not str(getattr(self, name)).strip():
                raise ValueError(
                    f"a width reading gives no {name}; every reading names its "
                    "instrument, its map and its arm, because 'the smear "
                    "width' is a family of numbers"
                )


def _profile(field_map: NDArray[np.float64], normal_axis: int) -> NDArray[np.float64]:
    """Average the map parallel to the boundary, ignoring absent points.

    Written out rather than taken from `np.nanmean` so that an all-absent
    normal index yields `NaN` **without** a runtime warning that a caller would
    have to suppress -- and so the count per index is explicit, since it is the
    denominator the majority threshold is applied to.
    """
    values = np.asarray(field_map, dtype=np.float64)
    if values.ndim != 2:
        raise ValueError(f"a field map is 2-D; got {values.ndim} dimensions")
    if normal_axis not in (0, 1):
        raise ValueError(f"normal_axis is 0 or 1; got {normal_axis}")

    parallel_axis = 1 - normal_axis
    present = np.isfinite(values)
    counted = present.sum(axis=parallel_axis)
    total = np.where(present, values, 0.0).sum(axis=parallel_axis)
    out = np.full(counted.shape, np.nan, dtype=np.float64)
    np.divide(total, counted, out=out, where=counted > 0)
    return out


def _reading(
    profile: NDArray[np.float64],
    *,
    cells: float | None,
    at_floor: bool,
    reach_cells: float,
    map_name: str,
    arm: str,
    refused: str | None,
) -> WidthReading:
    """Assemble a reading, with the instrument and floor filled in once."""
    return WidthReading(
        cells=cells,
        at_floor=at_floor,
        floor_cells=FLOOR_CELLS,
        reach_cells=reach_cells,
        estimator=ESTIMATOR,
        map_name=map_name,
        arm=arm,
        refused=refused,
        profile=tuple(float(value) for value in profile),
    )


def smear_width(
    field_map: NDArray[np.float64],
    *,
    boundary_index: int,
    normal_axis: int,
    reach_cells: float,
    map_name: str,
    arm: str,
) -> WidthReading:
    """Measure the majority-misclassified run about the boundary.

    Args:
        field_map: A disagreement map over the grid, one scalar per point --
            what `agreement_map` returns. `NaN` marks a point that made no
            selection.
        boundary_index: Where the step is, along the normal axis. **The only
            thing about the truth this function knows.**
        normal_axis: Which axis of `field_map` runs across the boundary.
        reach_cells: The spiral reach, from `spiral_reach_cells`. **Passed in
            rather than read here**, so a config change moves the check.
        map_name: Which scalar map this is.
        arm: Which arm it came from.

    Returns:
        The reading. `cells` is `None` at the floor and when refused; the two
        are told apart by `at_floor` and `refused`.

    Raises:
        ValueError: If the map is not 2-D, if `normal_axis` is not 0 or 1, or
            if the boundary has no cell on one side of it. **The last is not
            pedantry:** the seed pair is `(boundary_index - 1, boundary_index)`
            and `profile[-1]` is the LAST cell of the grid, so a boundary at 0
            would silently seed the run at the far edge and measure the
            opposite regime's interior.
    """
    profile = _profile(field_map, normal_axis)
    n = int(profile.size)
    if not 1 <= boundary_index <= n - 1:
        raise ValueError(
            f"boundary index {boundary_index} has no cell on both sides of a "
            f"{n}-cell normal axis; the seed pair is "
            "(boundary_index - 1, boundary_index) and a negative index would "
            "wrap to the far edge of the grid"
        )

    smeared = profile > MAJORITY
    seeds = (boundary_index - 1, boundary_index)

    # **THE SEEDS ARE ALWAYS A DECISION**, whether or not a run forms, so an
    # absent one withholds the reading even when the width would be 0.
    decisive: list[int] = list(seeds)
    lo = hi = None
    if smeared[seeds[0]] or smeared[seeds[1]]:
        lo = hi = seeds[0] if smeared[seeds[0]] else seeds[1]
        while lo - 1 >= 0 and smeared[lo - 1]:
            lo -= 1
        while hi + 1 < n and smeared[hi + 1]:
            hi += 1
        # The run stopped somewhere, and where it stopped is a decision too.
        decisive += [index for index in (lo - 1, hi + 1) if 0 <= index < n]

    # **THE REFUSAL IS EXACTLY THE CELLS THE RUN HAD TO DECIDE ABOUT, AND THE
    # ASYMMETRY IS THE DESIGN.** Every absent value capable of changing the
    # width refuses; no absent value incapable of changing it does. Refusing on
    # any NaN anywhere makes a partially fitted field unreadable and Task 5
    # reports nothing; refusing on none lets missing data terminate the run
    # exactly as a below-threshold cell does, which shortens the width -- always
    # in the reassuring direction, and worst where fits fail, which is at the
    # boundary. The rule reads as an arbitrary radius without this paragraph.
    absent = sorted({index for index in decisive if math.isnan(profile[index])})
    if absent:
        return _reading(
            profile,
            cells=None,
            at_floor=False,
            reach_cells=reach_cells,
            map_name=map_name,
            arm=arm,
            refused=(
                f"normal indices {absent} carry no fitted point and the run's "
                "extent depends on them; a width taken here would be shortened "
                "by missing data rather than measured"
            ),
        )

    width = 0.0 if lo is None or hi is None else float(hi - lo + 1)

    if width > reach_cells:
        return _reading(
            profile,
            cells=None,
            at_floor=False,
            reach_cells=reach_cells,
            map_name=map_name,
            arm=arm,
            refused=(
                f"width {width:g} cells exceeds the spiral reach of "
                f"{reach_cells:g} cells; no point can be biased by a source the "
                "spiral never reached, so this is an estimator failure and not "
                "a smear"
            ),
        )

    if width <= FLOOR_CELLS:
        return _reading(
            profile,
            cells=None,
            at_floor=True,
            reach_cells=reach_cells,
            map_name=map_name,
            arm=arm,
            refused=None,
        )

    return _reading(
        profile,
        cells=width,
        at_floor=False,
        reach_cells=reach_cells,
        map_name=map_name,
        arm=arm,
        refused=None,
    )


def interior_null(
    field_map: NDArray[np.float64],
    *,
    boundary_index: int,
    normal_axis: int,
    offset_cells: int,
    reach_cells: float,
    map_name: str,
    arm: str,
) -> WidthReading:
    """Run the same estimator at a false boundary, where the truth has no step.

    **THE SAME FITS, A DIFFERENT LINE**, so the control costs no compute. E6
    makes it the clause that gates the sub-phase: **it is computed first, as
    soon as any rung lands, and a width here stops the sub-phase rather than
    being noted.**

    Args:
        field_map: As `smear_width`.
        boundary_index: The REAL boundary, which the null is offset from.
        normal_axis: As `smear_width`.
        offset_cells: How far the null line sits from the boundary, towards
            index 0. **This is the parameter and `fields.NULL_LINE_INDEX` is
            derived from it**, so the location has one spelling.
        reach_cells: As `smear_width`.
        map_name: As `smear_width`.
        arm: As `smear_width`.

    Returns:
        The reading at the false boundary. **Predicted, before any rung ran, to
        be at the floor** -- a misclassification profile is flat within a regime
        because `fields` builds the true family as a pure indicator, so smooth
        variation moves the parameters without moving which family is true and
        there is no slope for the estimator to find. **If it returns a width,
        the profile is what separates the two causes:** the estimator reading
        the field's structure, or a baseline disagreement rate above a half,
        which is a statement about selection at `N = 630` and not about warm
        starting.

    Raises:
        ValueError: If the offset is within one coarse spacing of the boundary,
            or puts the null line off the grid. **A control taken inside the
            coupling range would be expected to fire**, so its passing would
            mean nothing -- which side of the range it sits on is the whole
            difference between a control and a second measurement.
    """
    if offset_cells < COARSE_STRIDE:
        raise ValueError(
            f"null-line offset {offset_cells} is within one coarse spacing "
            f"({COARSE_STRIDE}) of the boundary, so points on it may have been "
            "warm-started across the step; a control there is expected to fire "
            "and its passing means nothing"
        )
    false_boundary = boundary_index - offset_cells
    if false_boundary < 1:
        raise ValueError(
            f"null-line offset {offset_cells} from boundary {boundary_index} "
            f"lands at index {false_boundary}, which is not an interior line"
        )
    return smear_width(
        field_map,
        boundary_index=false_boundary,
        normal_axis=normal_axis,
        reach_cells=reach_cells,
        map_name=map_name,
        arm=arm,
    )
