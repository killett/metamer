"""Sub-phase 2f Task 6: is the failure map arranged, or merely dense.

**THE NULL IS THE WHOLE DESIGN.** Permuting labels among eligible cells with
the mask held fixed preserves the missing-data geometry AND the failure count,
so every test here plants two fields with the SAME number of failures and
differing only in arrangement. A statistic that answered "is this rate
unusual" would not separate them, and separating them is the only job it has.
"""

from __future__ import annotations

import json
import pathlib

import numpy as np
import pytest

from metamer.core.outcomes import Outcome
from metamer.report.clustering import (
    CLUSTERING_SEED,
    ELIGIBLE_FLOOR,
    arrangement,
    compute,
    join_count,
    rook_edges,
)
from metamer.report.reader import Completion, StoreView

#: Task 0's committed measurements. **The binding is to this artifact, not to
#: the harness that produced it** -- comparing production code against the old
#: implementation's source would only show two implementations agree; comparing
#: against its published output is what the record exists for.
_SPIKE_RECORD = (
    pathlib.Path(__file__).resolve().parents[1]
    / "docs"
    / "superpowers"
    / "notes"
    / "phase2f-clustering-measured.jsonl"
)


#: The store's own flag attributes, as `reader._legend` returns them. These
#: helpers plant an outcome cube directly rather than opening a store, so the
#: legend is supplied the same way -- from `Outcome`, which is what the writer
#: builds it from.
_LEGEND = {member.code: str(member.value) for member in Outcome}


def _seam_rows() -> list[dict[str, object]]:
    """Task 0's P4 seam records, read from the committed artifact."""
    return [
        record
        for line in _SPIKE_RECORD.read_text().splitlines()
        if (record := json.loads(line)).get("record") == "p4_seam"
    ]


def _view(
    outcome: np.ndarray, *, spatial: dict[str, np.ndarray] | None = None
) -> StoreView:
    """A view carrying a planted outcome cube and nothing else of substance."""
    rows, columns, models = outcome.shape
    return StoreView(
        path=pathlib.Path("/nonexistent"),
        outcome=outcome,
        delta_ic=np.zeros((rows, columns, models, 1), dtype=np.float32),
        selected=np.zeros((rows, columns, 1), dtype=np.int16),
        n_valid=np.zeros((rows, columns), dtype=np.int16),
        iterations=np.zeros(outcome.shape, dtype=np.uint16),
        model_labels=tuple(f"m{i}" for i in range(models)),
        criterion_labels=("aic",),
        attrs={},
        completion=Completion(complete=1, total=1),
        spatial=spatial if spatial is not None else {},
        disagreements=(),
        legend=_LEGEND,
    )


def _cube(failed: np.ndarray) -> np.ndarray:
    """One candidate's plane of OK / DEGENERATE_HESSIAN, as an outcome cube."""
    codes = np.where(failed, Outcome.DEGENERATE_HESSIAN.code, Outcome.OK.code).astype(
        np.uint8
    )
    return codes[:, :, None]


def test_a_patch_and_a_scatter_with_the_SAME_failure_count_are_told_apart():
    """The statistic measures arrangement, which is why the null holds the rate.

    Expected values determined independently by construction: both fields are
    40 x 40 = 1600 eligible cells carrying exactly 400 failures. One is a
    contiguous 20 x 20 block, the other is 400 cells drawn at random. **The
    patch's join count is near the maximum a 400-cell set can achieve and the
    scatter's is near the null's own mean**, so the first rejects and the
    second does not.

    Bug this catches: **a statistic measuring the RATE rather than the
    ARRANGEMENT** -- the null choice D5 exists to make. A null that permuted
    the mask, or any statistic derived from the failure fraction, gives the two
    fields identical answers, because by construction they have identical
    fractions. That is the one comparison this section exists to support.
    """
    rows = columns = 40
    patch = np.zeros((rows, columns), dtype=bool)
    patch[10:30, 10:30] = True
    flat = np.zeros(rows * columns, dtype=bool)
    flat[: int(patch.sum())] = True
    np.random.default_rng(4).shuffle(flat)
    scatter = flat.reshape(rows, columns)

    assert patch.sum() == scatter.sum() == 400

    eligible = np.ones((rows, columns), dtype=bool)
    left, right = rook_edges(eligible)
    clustered = arrangement(patch.ravel(), left, right, seed=CLUSTERING_SEED)
    diffuse = arrangement(scatter.ravel(), left, right, seed=CLUSTERING_SEED)

    assert clustered.available and diffuse.available
    assert clustered.z is not None and diffuse.z is not None
    assert clustered.z > 20.0, clustered.z
    assert abs(diffuse.z) < 3.0, diffuse.z
    assert clustered.p is not None and clustered.p < 0.002
    assert diffuse.p is not None and diffuse.p > 0.01


def test_a_candidate_clustered_alone_is_not_hidden_by_a_clean_aggregate():
    """All M are reported, which is why D7 refused an aggregate-only statistic.

    Expected values determined by construction: two candidates over 40 x 40.
    The first fails in a contiguous block; the second succeeds everywhere. A
    point enters the aggregate's failure set only where EVERY fit verdict
    there failed -- the `OK`-if-any rule -- so the aggregate has **no
    failures at all** and is unavailable for that reason.

    Bug this catches: an aggregate-only statistic, which reports this store as
    clean while one candidate is entirely clustered. **The aggregate being
    unavailable here is the correct answer and the per-candidate row is the
    finding**, which is exactly the asymmetry D7 names.
    """
    rows = columns = 40
    bad = np.zeros((rows, columns), dtype=bool)
    bad[5:25, 5:25] = True
    cube = np.concatenate([_cube(bad), _cube(np.zeros_like(bad))], axis=2)

    section = compute(_view(cube))
    (first_label, first), (_, second) = section.by_candidate

    assert first.available and first.z is not None and first.z > 20.0
    assert second.available is False
    assert second.reason == "no failures to arrange"
    assert section.aggregate.available is False
    assert section.aggregate.reason == "no failures to arrange"
    assert section.headline_label == "max over 2 candidates, uncorrected"
    assert first_label == "m0"


def test_a_checkerboard_mask_has_no_adjacent_pair_and_says_so():
    """Zero edges is unavailable with a reason, never a z.

    Expected value determined by construction: on a checkerboard no eligible
    cell is rook-adjacent to another, so the edge count is exactly zero --
    asserted directly rather than inferred from the statistic being absent.

    Bug this catches: a graph built without checking it has any edges, which
    divides by zero or returns a spurious z from an empty draw. **And the
    reason matters as much as the unavailability**: "adjacency is undefined on
    this mask" is a statement about the mask, where a z of 0 would be a false
    statement about the data.
    """
    rows = columns = 40
    ys, xs = np.indices((rows, columns))
    eligible = (ys + xs) % 2 == 0
    cube = np.where(eligible, Outcome.OK.code, Outcome.NOT_APPLICABLE.code).astype(
        np.uint8
    )[:, :, None]
    # Make half the eligible cells failures so the emptiness is the graph's,
    # not the indicator's.
    failed = eligible & (xs < columns // 2)
    cube[failed, 0] = Outcome.DEGENERATE_HESSIAN.code

    left, right = rook_edges(eligible)
    assert left.size == 0

    ((_, only),) = compute(_view(cube)).by_candidate

    assert only.available is False
    assert only.edges == 0
    assert "adjacency is undefined" in (only.reason or "")


def test_every_point_failing_leaves_one_arrangement_and_is_unavailable():
    """One arrangement is not evidence of clustering.

    Expected value determined by construction: every eligible cell fails, so
    every permutation produces the identical join count and the null has no
    spread at all.

    Bug this catches: a z computed from a zero-variance null, which is either a
    division by zero or a spurious infinity -- and, if it were reported as 0,
    would read as "no clustering found" for the most clustered field possible.
    """
    rows = columns = 40
    cube = _cube(np.ones((rows, columns), dtype=bool))

    ((_, only),) = compute(_view(cube)).by_candidate

    assert only.available is False
    assert only.reason == "every eligible point failed; there is one arrangement"
    assert only.z is None


def test_a_small_mask_names_the_floor_as_a_ladder_rung_not_a_threshold():
    """The floor's provenance is in the message, because its precision matters.

    Expected value determined independently from Task 0's P5-prime: 200 failed
    and 500 passed, so the true floor lies in (200, 500] and 500 is the
    smallest tested size demonstrated uniform. A 20 x 20 grid has 400 eligible
    cells -- **inside that interval**, which is why it is the right size to
    test with.

    Bug this catches: a message reading "below the measured floor of 500",
    which a later reader takes for a threshold measured to the point. It was
    not: the ladder had rungs at 200 and 500 and nothing between them was ever
    tried. **A constant that does not say which side of it was measured is
    indistinguishable from one that was measured on both.**
    """
    cube = _cube(np.zeros((20, 20), dtype=bool))
    cube[0:5, 0:5, 0] = Outcome.DEGENERATE_HESSIAN.code

    ((_, only),) = compute(_view(cube)).by_candidate

    assert only.eligible == 400 < ELIGIBLE_FLOOR
    assert only.available is False
    reason = only.reason or ""
    assert "LADDER RUNG" in reason
    assert "(200, 500]" in reason
    assert "smallest tested size demonstrated uniform" in reason


def test_the_same_seed_repeats_and_a_different_seed_lands_within_the_nulls_spread():
    """A published p is reproducible from the record alone.

    Expected values determined independently, and **the tolerance is DERIVED
    from the permutation count rather than picked.** `z = (observed - mean) /
    sd`, so for a large z the relative error in z is dominated by the relative
    error in the null's `sd`, whose sampling standard deviation over `P` draws
    is `1 / sqrt(2 (P - 1))` -- **2.238% for ONE seed at `P = 999`.** Two
    independent seeds differ by `sqrt(2)` times that, so one standard deviation
    of `|dz| / |z|` is `sqrt(2 / 1996) = 3.165%` and a 3-sigma bound is
    **9.496%**. That is the number asserted, and it is a bound on sampling error
    rather than a threshold fitted to an observed run.

    **THE PER-SEED FIGURE IS SPELLED OUT BECAUSE ITS ABSENCE CAUSED AN ERROR.**
    An account of this derivation written from `sqrt(2 / 1996)` alone reported
    "3.2% per seed, 4.5% for two" -- each `sqrt(2)` too large, and each
    contradicting the same account's own conclusions, since three times 4.5% is
    13.5% rather than 9.5% and 5.5 / 4.5 is 1.22 sigma rather than 1.7. **A
    derivation wrong in the middle and right at the end is more dangerous than
    one wrong throughout**, because the end agrees with the code and invites a
    reader to repair the code to match the middle. Both figures appear here now,
    so neither has to be re-derived.

    **AND THE FORMULA ASSUMES A NORMAL NULL, WHICH THIS FIXTURE SATISFIES --
    MEASURED, NOT ASSERTED.** `1 / sqrt(2 (P - 1))` is the normal case; a skewed,
    sparse-failure null has a standard error larger by `sqrt((kappa - 1) / 2)`
    for kurtosis `kappa`. On this fixture -- a 20x20 patch in a 40x40 all-true
    mask -- the null measures **background rate 0.25, skewness +0.0135,
    kappa 2.8932**, so the inflation factor is **0.9729** and the bound is
    conservative by 1.028x. Slightly platykurtic, which is the safe direction.

    **THE LIMIT, SO NOBODY GENERALISES THIS BOUND:** 0.25 is dense. The sparse
    regime the inflation factor warns about is what a real store presents -- a
    map-scale grid with a 0.5% failure rate -- and there the factor must be
    computed rather than dismissed. This tolerance is derived for this fixture's
    regime only.

    Bug this catches: an unseeded null, which makes every reported p
    irreproducible and every comparison between two reports meaningless.
    **Both halves are needed**: identical-on-repeat alone is satisfied by a
    constant that ignores the seed, and the second seed is what shows a draw
    actually happened.

    **AND A PERCENTAGE PICKED BY EYE WOULD HAVE BEEN WRONG.** The first
    version of this test asserted 5% and failed at a measured 5.5% -- which is
    1.7 sigma, an ordinary draw. A tolerance that cannot be derived is a
    tolerance that gets loosened until it passes, and the loosening is
    indistinguishable from the defect.
    """
    rows = columns = 40
    patch = np.zeros((rows, columns), dtype=bool)
    patch[10:30, 10:30] = True
    left, right = rook_edges(np.ones((rows, columns), dtype=bool))

    first = arrangement(patch.ravel(), left, right, seed=CLUSTERING_SEED)
    again = arrangement(patch.ravel(), left, right, seed=CLUSTERING_SEED)
    other = arrangement(patch.ravel(), left, right, seed=CLUSTERING_SEED + 1)

    assert first.z == again.z
    assert first.p == again.p
    assert first.seed == CLUSTERING_SEED
    assert first.z is not None and other.z is not None
    # 3 sigma on |dz| / |z| at P = 999; see the derivation above.
    bound = 3.0 * (2.0 / (2 * (first.permutations or 0) - 2)) ** 0.5
    assert bound == pytest.approx(0.0950, abs=5e-4)
    assert abs(first.z - other.z) < bound * abs(first.z)


def test_every_non_fit_member_is_absent_from_the_graph():
    """The population is the PREDICATE, and it excludes five members not four.

    Expected values determined from `Outcome`'s own predicate table: five
    members read `is_fit_verdict: no` -- `NOT_ATTEMPTED`, `SCREENED_OUT`,
    `CANDIDATE_DROPPED`, `NOT_APPLICABLE` **and `INSUFFICIENT_DATA`**. The
    graph's cell count must equal the number of fit-verdict cells and nothing
    more.

    Bug this catches: the graph built on `is_eligible`, under which a dropped
    candidate's 100% coverage is a perfect cluster of a decision the run took.
    **And the fifth member is the one that makes it bite**: open question 24
    left `INSUFFICIENT_DATA` eligible AND covered while keeping it outside the
    fit verdicts, so it is the only member the two predicates disagree about
    that a graph would admit. The plan's own test named four and would have
    missed it.

    **ASSERTED OVER THE PREDICATE, NOT A LIST**, so a sixth non-fit member
    added later is covered on the day it lands.
    """
    non_fit = [member for member in Outcome if not member.is_fit_verdict]
    assert len(non_fit) == 5
    assert Outcome.INSUFFICIENT_DATA in non_fit

    # One row per non-fit member, plus enough OK to clear the floor.
    rows, columns = 30, 30
    codes = np.full((rows, columns), Outcome.OK.code, dtype=np.uint8)
    for offset, member in enumerate(non_fit):
        codes[offset, :] = member.code
    cube = codes[:, :, None]
    expected = int((rows - len(non_fit)) * columns)

    ((_, only),) = compute(_view(cube)).by_candidate

    assert only.eligible == expected, "a non-fit member entered the graph"


def test_rook_edges_reproduces_task_zeros_committed_edge_counts():
    """The binding to the frozen harness, through its published output.

    Expected values read from `phase2f-clustering-measured.jsonl`, Task 0's own
    committed artifact: at height 90 the P4 seam records carry
    `unwrapped_edges` and `wrapped_edges` for two widths, and the wrapped arm
    adds exactly one seam edge per row. **These are pure geometry and involve
    no draw**, so they are reproducible exactly rather than within a tolerance.

    Bug this catches: a production `rook_edges` that disagrees with the one
    Task 0 measured with -- at which point every number the spike published
    describes a different graph from the one the report counts, and nothing
    else in the tree would notice. **The harness itself is frozen** ((j8)'s
    third register), so this binds to the RECORD rather than to its source:
    comparing two implementations shows they agree, while comparing against
    the published output is what makes the old numbers still true of the new
    code.
    """
    records = _seam_rows()
    assert records, "the committed spike record carries no seam rows"

    for record in records:
        height = int(str(record["height"]))
        width = int(str(record["width"]))
        eligible = np.ones((height, width), dtype=bool)

        unwrapped, _ = rook_edges(eligible, wrap=False)
        wrapped, _ = rook_edges(eligible, wrap=True)

        assert unwrapped.size == int(str(record["unwrapped_edges"]))
        assert wrapped.size == int(str(record["wrapped_edges"]))
        assert wrapped.size - unwrapped.size == int(str(record["joins_lost"]))


def test_join_count_is_the_number_of_edges_with_both_ends_failing():
    """The statistic itself, on a field small enough to count by hand.

    Expected value computed by hand: a 2 x 3 all-eligible grid has 2 vertical
    and 3... no -- 1 vertical join per column (3) and 2 horizontal per row (4),
    seven edges. Failing the whole first row gives exactly the two horizontal
    joins within it and no vertical join, so the count is 2.

    Bug this catches: a join count that counts each undirected edge twice, or
    counts a single failing endpoint. **Both produce a plausible number that
    scales the right way**, which is why the value is counted by hand rather
    than compared against a second implementation.
    """
    eligible = np.ones((2, 3), dtype=bool)
    left, right = rook_edges(eligible)
    assert left.size == 7

    failed = np.array([True, True, True, False, False, False])

    assert join_count(failed, left, right) == 2


def test_an_unmeasurable_span_is_not_global_and_says_which():
    """D4: every ambiguous case fails toward not wrapping.

    Expected value determined independently: a store that wrote no spatial
    coordinates gives no span, and an unknown span is not a global grid -- so
    one arm is computed and the note says the span could not be measured.

    Bug this catches: treating an unmeasurable span as global, which would wrap
    the seam on a regional box and join two edges that are thousands of
    kilometres apart. **And the note is the other half**: the not-global branch
    is a measurement the reader can check, not a policy they have to trust.
    """
    cube = _cube(np.zeros((30, 30), dtype=bool))
    section = compute(_view(cube))

    assert section.span is None
    assert section.wrapped is None
    assert "could not be measured" in section.span_note


def test_a_global_span_fires_the_two_arm_zone_and_both_arms_are_reported():
    """Where the zone fires, both arms are printed in full (D4).

    Expected value determined by construction: 360 columns spanning 0 to 359
    degrees is 359 degrees over 359 cells, one cell short of 360 -- **inside
    the two-arm zone, which is deliberately wider than the wrap gate** so a
    global grid with a masked column still gets the comparison.

    Bug this catches: a report that prints one arm on a global store, leaving
    the reader unable to tell whether the arm choice changed the answer. A
    delta never stands in for the pair, so both arms are asserted present and
    the wrapped arm must have strictly more edges.
    """
    rows, columns = 30, 360
    cube = _cube(np.zeros((rows, columns), dtype=bool))
    cube[5:20, 5:40, 0] = Outcome.DEGENERATE_HESSIAN.code
    section = compute(
        _view(cube, spatial={"longitude": np.arange(columns, dtype=np.float64)})
    )

    assert section.span == pytest.approx(359.0)
    assert section.wrapped is not None
    assert len(section.wrapped) == len(section.by_candidate)
    ((_, unwrapped),) = section.by_candidate
    ((_, wrapped),) = section.wrapped
    assert wrapped.edges == unwrapped.edges + rows
    assert "360°" in section.span_note
