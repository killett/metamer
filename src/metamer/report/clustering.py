"""Sub-phase 2f Task 6: the clustering statistic and its permutation null.

**THE QUESTION IS WHETHER THE FAILURES ARE ARRANGED, NOT WHETHER THERE ARE
MANY.** A join count against a null that permutes labels among the eligible
cells **with the mask held fixed** (D5) preserves both the missing-data geometry
and the failure count, so it asks *is this arrangement unusual* rather than *is
this rate unusual*. Permuting the mask instead is the obvious alternative and it
tests a different hypothesis.

**THE POPULATION IS `Outcome.is_fit_verdict` (D3), AND THE EXCLUSION IS OVER THE
PREDICATE RATHER THAN A LIST.** Every non-fit code forms the same
contiguous-block pathology that section 14.2 makes the argument for about land:
a dropped candidate is `CANDIDATE_DROPPED` at 100% of points, which under
`is_eligible` is a perfect cluster of a decision the run took. **Five members are
excluded, not four** -- the fifth is `INSUFFICIENT_DATA`, which open question 24
made eligible and covered while leaving it outside the fit verdicts, and it is
therefore the only member a graph built on the wrong predicate would admit.

**A SECOND IMPLEMENTATION OF TASK 0's SPIKE ALGORITHM, DELIBERATELY.**
`docs/superpowers/notes/phase2f-clustering-harness.py` is the apparatus of
numbers this project still quotes and does not move -- (j8)'s third register.
The handoff names this as the stated exception to (j9): one is the current
value, the other a record of a past one, and collapsing them destroys the
record. **The divergence is closed by binding this code to the committed
artifact's own numbers**, not to the harness's source, which would only compare
a new implementation against an old one.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from metamer.core.outcomes import Outcome
from metamer.report.reader import StoreView

#: The seed for every published permutation null. **On the do-not-move list in
#: the plan's standing requirements**: moving it changes every reported p, and
#: a p that moves when nobody changed the data is not a p.
#:
#: **IT IS NOT THE SPIKE'S SEED.** Task 0's harness carries `SPIKE_SEED =
#: 20260919`, which is *a record of the draw Task 0 took* and stays where it
#: is; this keys the draws the report publishes. Two different things, and the
#: Phase 2d field-seed instance is the precedent for keeping both.
CLUSTERING_SEED = 20260927

#: Permutations per null. 999 makes the smallest reachable p exactly 1/1000.
PERMUTATIONS = 999

#: Below this many eligible points the statistic is unavailable.
#:
#: **A LADDER RUNG, NOT A BOUNDARY, AND THE DIFFERENCE IS THE WHOLE POINT.**
#: Task 0's P5-prime measured 200 non-uniform and 500 uniform, so the true
#: threshold lies in **(200, 500]** and 500 is *the smallest tested size
#: demonstrated uniform* -- not a measured threshold. Stated that way here and
#: in the unavailability reason, or a later reader takes it for a precision it
#: does not have.
ELIGIBLE_FLOOR = 500

#: Axis names this report recognises as a longitude-like `x`. **Anything else
#: is ambiguous and D4 says every ambiguous case fails toward not-wrapping**, so
#: an unrecognised name yields no span and the not-global branch.
_X_AXIS_NAMES = ("x", "longitude", "lon")


@dataclass(frozen=True)
class Arrangement:
    """One population's join count against its null, or why there is none.

    Attributes:
        available: Whether a statistic exists at all.
        reason: Why not, when it does not. **Never a z of 0**: (a2b), and a
            zero reads as "no clustering found" rather than "not computed".
        edges: Adjacent eligible pairs in the graph.
        eligible: Cells in the graph.
        failures: Cells carrying the failure indicator.
        observed: The BB join count.
        null_median: The null's median count.
        null_q95: Its 95th percentile.
        z: `(observed - mean) / sd`, or None where the null has no spread.
        p: `(1 + #{draws >= observed}) / (1 + permutations)`.
        permutations: How many draws.
        seed: The seed they were drawn from. **In the record**, so a p is
            reproducible from the report alone.
    """

    available: bool
    reason: str | None
    edges: int
    eligible: int
    failures: int
    observed: int | None = None
    null_median: float | None = None
    null_q95: float | None = None
    z: float | None = None
    p: float | None = None
    permutations: int | None = None
    seed: int | None = None


@dataclass(frozen=True)
class Clustering:
    """Task 6's record: per candidate, plus an aggregate of a different kind.

    Attributes:
        by_candidate: One arrangement per model label, in the store's axis
            order. **All of them are reported** -- a single headline would hide
            a candidate clustered alone, which is why D7 refused an
            aggregate-only statistic.
        aggregate: The arrangement over points failing under *any* candidate.
            **A second headline of a different kind, not a summary of the
            rows.**
        headline_label: What the largest z means, said at the number.
        span: The `x` span found, in degrees, or None when it could not be
            measured.
        span_note: The span as a sentence, so the not-global branch is a
            measurement rather than a policy.
        wrapped: The seam-wrapped arm, when the two-arm zone fires. **Both arms
            printed in full** (D4); a delta never stands in for the pair.
    """

    by_candidate: tuple[tuple[str, Arrangement], ...]
    aggregate: Arrangement
    headline_label: str
    span: float | None
    span_note: str
    wrapped: tuple[tuple[str, Arrangement], ...] | None


def rook_edges(
    eligible: NDArray[np.bool_], *, wrap: bool = False
) -> tuple[NDArray[np.int64], NDArray[np.int64]]:
    """Rook adjacency between eligible cells, in ELIGIBLE-INDEX space.

    Index space, not metric space: section 14.2 fixes that, and the cells of a
    lat/lon grid are not equal-area.

    **EVERY NON-ELIGIBLE CELL LEAVES THE GRAPH ENTIRELY** rather than entering
    it as a non-failure, which is D3's generalisation of section 14.2's land
    argument to every non-fit code.

    Args:
        eligible: `(rows, columns)` mask of cells in the graph.
        wrap: Close the longitude seam. **False is the shipped choice** (D4);
            True is the second arm where the two-arm zone fires.

    Returns:
        `(left, right)` index arrays, one entry per undirected edge.
    """
    index = np.full(eligible.shape, -1, dtype=np.int64)
    index[eligible] = np.arange(int(eligible.sum()), dtype=np.int64)

    pairs: list[tuple[NDArray[np.int64], NDArray[np.int64]]] = []
    vertical = eligible[:-1, :] & eligible[1:, :]
    pairs.append((index[:-1, :][vertical], index[1:, :][vertical]))
    horizontal = eligible[:, :-1] & eligible[:, 1:]
    pairs.append((index[:, :-1][horizontal], index[:, 1:][horizontal]))
    if wrap:
        seam = eligible[:, -1] & eligible[:, 0]
        pairs.append((index[:, -1][seam], index[:, 0][seam]))

    left = np.concatenate([a for a, _ in pairs])
    right = np.concatenate([b for _, b in pairs])
    return left, right


def join_count(
    failed: NDArray[np.bool_], left: NDArray[np.int64], right: NDArray[np.int64]
) -> int:
    """The BB join count: edges whose BOTH endpoints carry the indicator."""
    return int(np.count_nonzero(failed[left] & failed[right]))


def arrangement(
    failed: NDArray[np.bool_],
    left: NDArray[np.int64],
    right: NDArray[np.int64],
    *,
    seed: int,
    permutations: int = PERMUTATIONS,
) -> Arrangement:
    """The statistic against a null that holds the eligible mask fixed.

    **THE SEED IS REQUIRED AND HAS NO DEFAULT**, per the handoff: *"a value
    that KEYS THE DRAW arriving silently at a caller that never named it is the
    failure the constant exists to make visible -- a default would automate
    it."*

    **THE FOUR UNAVAILABLE CASES EACH NAME THEIR OWN REASON** rather than
    returning a zero, because a z of 0 reads as "no clustering found" and three
    of these are "not computable" (a2b).

    Args:
        failed: The indicator, one entry per eligible cell.
        left: Edge endpoints.
        right: The other endpoints.
        seed: Keys the permutation draws.
        permutations: How many draws.

    Returns:
        The arrangement, available or with its reason.
    """
    total = int(failed.size)
    hits = int(failed.sum())
    edges = int(left.size)

    if total < ELIGIBLE_FLOOR:
        return Arrangement(
            available=False,
            reason=(
                f"{total} eligible points is below the floor of "
                f"{ELIGIBLE_FLOOR}, which is a LADDER RUNG rather than a "
                "measured threshold: Task 0 measured 200 non-uniform and 500 "
                "uniform, so the true floor lies in (200, 500] and 500 is the "
                "smallest tested size demonstrated uniform"
            ),
            edges=edges,
            eligible=total,
            failures=hits,
        )
    if edges == 0:
        return Arrangement(
            available=False,
            reason="no adjacent eligible pair exists; adjacency is undefined on this mask",
            edges=0,
            eligible=total,
            failures=hits,
        )
    if hits == 0:
        return Arrangement(
            available=False,
            reason="no failures to arrange",
            edges=edges,
            eligible=total,
            failures=0,
        )
    if hits == total:
        return Arrangement(
            available=False,
            reason="every eligible point failed; there is one arrangement",
            edges=edges,
            eligible=total,
            failures=hits,
        )

    observed = join_count(failed, left, right)
    rng = np.random.default_rng(seed)
    draws = np.empty(permutations, dtype=np.int64)
    for i in range(permutations):
        draws[i] = join_count(failed[rng.permutation(total)], left, right)

    mean = float(draws.mean())
    sd = float(draws.std(ddof=1))
    at_least = int(np.count_nonzero(draws >= observed))
    return Arrangement(
        available=True,
        reason=None,
        edges=edges,
        eligible=total,
        failures=hits,
        observed=observed,
        null_median=float(np.median(draws)),
        null_q95=float(np.quantile(draws, 0.95)),
        z=None if sd == 0.0 else (observed - mean) / sd,
        p=(1 + at_least) / (1 + permutations),
        permutations=permutations,
        seed=seed,
    )


def _x_span(view: StoreView) -> float | None:
    """The `x` axis's span in degrees, or None when it cannot be measured.

    **EVERY AMBIGUOUS CASE RETURNS None, WHICH IS D4's "FAIL TOWARD NOT
    WRAPPING".** An unrecognised axis name, a store that wrote no coordinates,
    or fewer than two values all mean the span is unknown -- and an unknown
    span is not a global grid.
    """
    for name in _X_AXIS_NAMES:
        values = view.spatial.get(name)
        if values is not None and values.size >= 2:
            return float(values.max() - values.min())
    return None


def _two_arm_zone(span: float | None, columns: int) -> bool:
    """Whether both arms are computed.

    **WIDER THAN THE WRAP GATE, DELIBERATELY** (D4): both arms whenever the
    span is within a couple of cells of 360 degrees, not only when a gate says
    global. The realistic false negatives -- a global grid with masked columns,
    or one whose spacing fails a regularity check -- all land near the boundary
    in span, which is precisely where the widening reaches.
    """
    if span is None or columns < 2:
        return False
    cell = span / (columns - 1)
    return abs(span - 360.0) <= 2.0 * cell


def compute(view: StoreView, *, seed: int = CLUSTERING_SEED) -> Clustering:
    """Task 6's section: are the failures arranged, per candidate and overall.

    Args:
        view: A store, read-only.
        seed: Keys every null here. Defaults to the published constant; passed
            explicitly by anything reproducing a recorded p.

    Returns:
        The arrangements, with both arms where the two-arm zone fires.
    """
    codes = np.asarray(view.outcome, dtype=np.uint8)
    fit_verdict = np.zeros(codes.shape, dtype=np.bool_)
    failure = np.zeros(codes.shape, dtype=np.bool_)
    for member in Outcome:
        if member.is_fit_verdict:
            fit_verdict |= codes == member.code
            if member.is_failure:
                failure |= codes == member.code

    span = _x_span(view)
    zone = _two_arm_zone(span, codes.shape[1])

    def arm(wrap: bool) -> tuple[tuple[str, Arrangement], ...]:
        rows: list[tuple[str, Arrangement]] = []
        for index, label in enumerate(view.model_labels):
            eligible = fit_verdict[..., index]
            left, right = rook_edges(eligible, wrap=wrap)
            rows.append(
                (
                    label,
                    arrangement(failure[..., index][eligible], left, right, seed=seed),
                )
            )
        return tuple(rows)

    # **THE AGGREGATE IS A DIFFERENT KIND OF HEADLINE, NOT A SUMMARY** (D7). A
    # point is in its population where ANY candidate carried a fit verdict, and
    # it fails where EVERY fit verdict there failed -- the `OK`-if-any rule
    # `/status/point_outcome` already fixes, one axis over.
    any_verdict: NDArray[np.bool_] = np.asarray(
        fit_verdict.any(axis=-1), dtype=np.bool_
    )
    all_failed: NDArray[np.bool_] = (
        np.asarray((failure | ~fit_verdict).all(axis=-1), dtype=np.bool_) & any_verdict
    )
    left, right = rook_edges(any_verdict)
    aggregate = arrangement(all_failed[any_verdict], left, right, seed=seed)

    return Clustering(
        by_candidate=arm(wrap=False),
        aggregate=aggregate,
        headline_label=(f"max over {len(view.model_labels)} candidates, uncorrected"),
        span=span,
        span_note=(
            "the x span could not be measured, so this grid is not treated as "
            "global and the seam is not wrapped"
            if span is None
            else f"{span:g}° of 360°, "
            + ("global" if _two_arm_zone(span, codes.shape[1]) else "not global")
            + ", not wrapped"
        ),
        wrapped=arm(wrap=True) if zone else None,
    )
