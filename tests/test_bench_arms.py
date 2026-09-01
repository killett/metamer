"""`metamer.bench.arms`: the `self` ceiling, and cost read as a ratio.

**THE CEILING E6's UPPER CLAUSE NAMES DOES NOT EXIST IN `src`.** *"Saving at
any rung >= the `self` ceiling -> the warm arm is reading its own answer
back"*, and the audit's arms are `WARM / COLD / N1 / N2`. The `94.53%` in the
figures table is **2c's fixture at 40.79 cold iterations per point** against
2d's field at **24.4** -- so quoting it to bound a saving here is a comparison
across fixtures, (j5), at the one clause whose job is catching a defect that
would otherwise read as a spectacular result.

**THE ARM IS THE CHEAPEST IN THE DESIGN AND THAT IS WHY THIS IS NOT A BUDGET
QUESTION.** Its input is the cold arm's own converged optimum, and Task 0
measured `self` collapsing to 4-6% of cold. It is also the **void control**: if
`self` does not collapse, the instrument has not been shown able to tell two
arms apart by cost, and no cost reading in the run may be quoted.

**AND THE RATIO IS OVER CELLS OK IN BOTH ARMS.** Two totals over two different
sets of cells is a ratio of different things, and it fails in the direction
nobody checks -- a missing cell reads as a cost difference of exactly the size
of that cell.
"""

from __future__ import annotations

import numpy as np
import pytest

from metamer.bench import arms
from metamer.core.outcomes import Outcome

# **ONE SPELLING OF THE FIXTURE.** The correlated draw and the shipped cold
# start are the N2 map's, imported rather than re-written: the draw's
# parameters are what make the selection axis live, and a second copy would
# make two test modules disagree about what "live" means.
from tests.test_bench_n2map import (  # noqa: PLC2701
    _CRITERION,
    _LIVE_MAX_ITER,
    _SIGNAL,
    _SPECS,
    _cold,
    _correlated_batch,
)


def _cost(n_iter: list[list[int]], ok: list[list[bool]]) -> arms.ArmCost:
    """A per-cell cost, constructed rather than fitted."""
    return arms.ArmCost(
        n_iter=np.asarray(n_iter, dtype=np.int64), ok=np.asarray(ok, dtype=np.bool_)
    )


# ---------------------------------------------------------------------------
# The ratio, on constructed costs
# ---------------------------------------------------------------------------


def test_the_ratio_is_taken_over_cells_ok_in_both_arms():
    """Two totals over one set of cells, or they are totals of different things.

    Behaviour: `iteration_ratio` sums both arms over the cells where **both**
    reached `OK`, and reports how many cells each arm reached alone.

    Expected value determined independently: hand-computed. The shared cells
    are `(0,0)` and `(1,1)`; the numerator sums `10 + 30 = 40` and the
    denominator `10 + 20 = 30`, so the ratio is `4/3`.

    **THE FIXTURE CARRIES A CELL EACH ARM REACHED ALONE, AND THE FIRST VERSION
    DID NOT.** Its `OK` sets were nested -- every numerator cell was also a
    denominator cell -- so summing over `numerator.ok` gave the same answer as
    summing over the intersection and the mutation survived by being invisible.
    **A surviving mutation is a question about the fixture at least as often as
    about the code**, and here it was the fixture: cell `(1,0)` is now `OK` in
    the numerator only, so the defect below changes the totals.

    Bug this catches: summing each arm over its own `OK` set. A cell that one
    arm converged on and the other did not then appears as a **cost
    difference** of exactly that cell's size -- and N1's whole reading is
    whether its ratio against cold sits inside `[1.0000, 1.0026]`, a band far
    narrower than one cell of a 384-point field. The defect moves the reading
    across the band without changing anything about the perturbation.
    """
    numerator = _cost([[10, 99], [17, 30]], [[True, False], [True, True]])
    denominator = _cost([[10, 7], [5, 20]], [[True, True], [False, True]])

    ratio = arms.iteration_ratio(numerator, denominator)

    assert ratio.cells_compared == 2
    assert ratio.numerator_total == 40
    assert ratio.denominator_total == 30
    assert ratio.ratio == pytest.approx(4.0 / 3.0)


def test_a_cell_one_arm_reached_and_the_other_did_not_is_counted_and_not_summed():
    """The excluded cells are a reading, not silence.

    Behaviour: cells `OK` in exactly one arm are excluded from both totals and
    counted per side.

    Expected value determined independently: the constructed masks -- one cell
    `OK` only in the numerator, one only in the denominator.

    Bug this catches: dropping the disagreement silently. **A ratio taken over
    a shrinking intersection is still a valid-looking number**, and the count
    is the only thing that says how much of each arm it describes. (a2b) at a
    count: zero here is a claim about the arms, so it has to be reported rather
    than assumed.
    """
    numerator = _cost([[10, 12], [5, 30]], [[True, True], [False, True]])
    denominator = _cost([[10, 7], [5, 20]], [[True, False], [True, True]])

    ratio = arms.iteration_ratio(numerator, denominator)

    assert ratio.cells_compared == 2
    assert ratio.numerator_only == 1
    assert ratio.denominator_only == 1


def test_a_ratio_with_no_shared_cell_is_refused_rather_than_infinite():
    """No shared cell is no reading, and it says so.

    Behaviour: with an empty intersection, `ratio` is None and the refusal
    names the reason.

    Expected value determined independently: disjoint `OK` masks, so the
    intersection is empty by construction.

    Bug this catches: dividing by a zero denominator and emitting `inf` or
    `nan` as a cost. A cost of `inf` is read as a catastrophic arm; a cost of
    `nan` propagates into a verdict and disappears into a formatted table.
    **The distinction between "the instrument looked and found nothing to
    compare" and "the arms differ enormously" is the whole reading.**

    **THE MESSAGE IS MATCHED, NOT MERELY ITS PRESENCE.** The first version
    asserted `refused is not None` and a mutation that removed this guard
    survived it -- **the zero-denominator guard below fires on the same input**
    and produced a different refusal for a different reason. That is (e3)'s
    shape: a green assertion passing off another guard's work. The phrase
    matched here is used by this branch alone.
    """
    numerator = _cost([[10, 12]], [[True, False]])
    denominator = _cost([[10, 7]], [[False, True]])

    ratio = arms.iteration_ratio(numerator, denominator)

    assert ratio.cells_compared == 0
    assert ratio.ratio is None
    assert ratio.refused is not None
    assert "in both arms" in ratio.refused


def test_the_two_arms_must_be_the_same_shape_or_the_pairing_is_meaningless():
    """A cell-by-cell pairing needs cells that correspond.

    Behaviour: mismatched shapes raise.

    Bug this catches: pairing a `(B, M)` arm against a `(B,)` reduction, or
    against an arm from a different batch. NumPy would broadcast some of those
    silently and return a number.
    """
    with pytest.raises(ValueError, match="same shape"):
        arms.iteration_ratio(
            _cost([[10, 12]], [[True, True]]),
            _cost([[10, 12], [1, 2]], [[True, True], [True, True]]),
        )


# ---------------------------------------------------------------------------
# The self arm, on real fits
# ---------------------------------------------------------------------------


def test_the_self_arm_returns_cold_s_own_answer_for_strictly_less_work():
    """A fit restarted from its own optimum returns it, cheaply.

    Behaviour: `self_arm` fits every cell from the cold arm's own
    `theta_unconstrained` and returns the same selected candidate at every
    point where cold converged, with **strictly fewer** iterations in total.

    Expected value determined independently: the cold `FitResult` itself, which
    is the oracle for both halves -- its selection, and its own iteration
    total as the thing the self arm must come in under. 2c measured `self`
    against `cold` agreeing at 99.58% and Task 0 measured it at 4-6% of cold's
    cost; neither number is asserted here, because those are readings of a
    field and this is a property of the arm.

    Bug this catches: **an `x0` that is not actually used.** If `x0_valid` came
    back all-false -- or the starts were passed in the wrong coordinates and
    rejected -- `fit` falls back to the moment ladder and the arm silently
    becomes a second cold arm. That is byte-identical in the output to *"self
    costs what cold costs"*, which is the reading this arm exists to refute,
    and it would void the run's whole cost block while looking like a
    measurement of it.
    """
    y, mask, t = _correlated_batch(2, 2)
    cold_result = arms.cold_arm(
        y, t, _SIGNAL, _SPECS, _CRITERION, mask=mask, max_iter=_LIVE_MAX_ITER
    )

    arm = arms.self_arm(
        y,
        t,
        _SIGNAL,
        _SPECS,
        _CRITERION,
        mask=mask,
        cold=cold_result,
        grid_shape=(2, 2),
        max_iter=_LIVE_MAX_ITER,
    )

    converged = cold_result.outcome == Outcome.OK.code
    assert converged.any(), "fixture is vacuous: cold converged nowhere"
    assert arm.cost.n_iter[converged].sum() < cold_result.n_iter[converged].sum()
    assert np.array_equal(
        arm.selected.reshape(-1), cold_result.ranking.best_index.astype(np.int16)
    )


def test_the_self_arm_starts_only_from_cells_cold_converged_on():
    """A start that is NaN is not a start.

    Behaviour: `self_arm`'s validity array is exactly `cold.outcome == OK`.

    Expected value determined independently: `FitResult.theta_unconstrained` is
    documented as all-NaN wherever `outcome` is not `OK`, so the mask is the
    outcome array and nothing else.

    Bug this catches: marking every cell valid. The warm-start contract is that
    `x0_valid` is false wherever the source did not converge, and *"a source
    map that marks one valid is refused rather than started from"* -- so the
    defect surfaces as a refusal or, worse, as a fit from NaN. It is the same
    (a2b) shape as the N2 arm's inadmissible cells: the cell has no start, and
    saying so is the reading.
    """
    y, mask, t = _correlated_batch(2, 2)
    cold_result = arms.cold_arm(
        y, t, _SIGNAL, _SPECS, _CRITERION, mask=mask, max_iter=_LIVE_MAX_ITER
    )
    forced = cold_result.outcome.copy()
    forced[0, 0] = Outcome.ITER_CAP_LARGE_GRAD.code

    valid = arms.self_start_validity(forced)

    assert valid[0, 0] is np.False_ or not bool(valid[0, 0])
    assert bool(valid[1, 0]) == (forced[1, 0] == Outcome.OK.code)
    assert valid.shape == forced.shape


def test_the_cold_arm_here_is_the_audits_cold_arm_and_not_a_second_one():
    """One cold start, one cold fit, one spelling.

    Behaviour: `cold_arm` fits with `x0=None` through the same `fit` call the
    audit's `COLD` arm uses, so the self arm perturbs around the point the
    audit's cold arm actually starts from.

    Expected value determined independently: `run_arms`' own `COLD` result on
    the same batch, compared cell by cell on iterations and selection.

    Bug this catches: a second cold arm with a different objective, engine or
    cap. The `self` ceiling is a ratio against cold, so a cold arm that is not
    the audit's makes the ceiling a ratio against something else -- and both
    numbers would be plausible.
    """
    from metamer.batch.audit import Arm, run_arms

    y, mask, t = _correlated_batch(2, 2)
    cold_start = _cold(y, mask, t)
    warm = cold_start + 0.5
    valid = np.ones((y.shape[0], len(_SPECS)), dtype=np.bool_)

    mine = arms.cold_arm(
        y, t, _SIGNAL, _SPECS, _CRITERION, mask=mask, max_iter=_LIVE_MAX_ITER
    )
    theirs = run_arms(
        y,
        t,
        _SIGNAL,
        _SPECS,
        _CRITERION,
        mask=mask,
        warm=warm,
        warm_valid=valid,
        points=np.arange(y.shape[0], dtype=np.int64),
        seed=11,
        max_iter=_LIVE_MAX_ITER,
    ).results[Arm.COLD]

    assert np.array_equal(mine.n_iter, theirs.n_iter)
    assert np.array_equal(mine.ranking.best_index, theirs.ranking.best_index)


# ---------------------------------------------------------------------------
# Two paths to one quantity
# ---------------------------------------------------------------------------


def test_two_paths_that_agree_cell_by_cell_are_reported_as_identical():
    """Agreement is per cell, not per total.

    Behaviour: `same_iterations` compares cell by cell over the shared `OK`
    cells and reports `identical` only when none differed and neither side had
    a cell the other lacked.

    Expected value determined independently: two constructed arms, one equal to
    the other, and one differing in a single cell whose totals still match.

    Bug this catches: comparing totals instead of cells. **Two arms that differ
    at two cells in opposite directions have the same total**, and the check
    would pass on a store and an arm that disagree everywhere in compensating
    ways -- which is precisely what a permuted batch produces.
    """
    left = _cost([[10, 20], [30, 40]], [[True, True], [True, True]])
    same = _cost([[10, 20], [30, 40]], [[True, True], [True, True]])
    swapped = _cost([[20, 10], [30, 40]], [[True, True], [True, True]])

    assert arms.same_iterations(left, same).identical is True
    assert arms.same_iterations(left, swapped).identical is False
    assert arms.same_iterations(left, swapped).cells_differing == 2
    assert left.n_iter.sum() == swapped.n_iter.sum()


def test_a_cell_one_path_converged_on_and_the_other_did_not_is_not_identical():
    """A disagreement about WHICH cells converged is a disagreement.

    Behaviour: cells `OK` on one side only make `identical` false and are
    counted per side.

    Expected value determined independently: constructed masks differing in one
    cell, with equal iteration counts everywhere.

    Bug this catches: intersecting the `OK` masks and then declaring agreement
    over what is left. **The intersection is the right denominator for a
    RATIO** -- two arms genuinely differ in what they converge on -- but for
    *"the same fits by two code paths"* a differing `OK` set is the finding,
    since the two paths ran identical work.
    """
    left = _cost([[10, 20]], [[True, True]])
    right = _cost([[10, 20]], [[True, False]])

    agreement = arms.same_iterations(left, right)

    assert agreement.identical is False
    assert agreement.left_only == 1
    assert agreement.right_only == 0


def test_a_stores_cost_lines_up_with_an_arms_own_layout(tmp_path):
    """The store is `(y, x, M)` and an arm is `(B, M)`, row-major.

    Behaviour: `store_cost` reshapes the store's arrays into the arm layout and
    marks a cell `OK` only when its outcome is `OK` **and** its iteration slot
    was written.

    Expected value determined independently: a constructed store whose value
    encodes its own position, so the row-major flattening can be named --
    point `(1, 0)` of a `2 x 2` grid is row 2 of the batch.

    Bug this catches: a column-major flattening, which compares the right
    number of cells in the wrong places. On a square grid it is invisible in
    the shapes and produces a plausible disagreement count; on this benchmark's
    `32 x 12` field it would report every cell as differing, which reads as a
    broken `run` rather than a broken comparison.
    """
    from tests.test_bench_fields import _written_store

    values = np.arange(8, dtype=np.uint16).reshape(2, 2, 2)
    path = _written_store(tmp_path / "s.zarr", values, [(1, 0, 1)])

    cost = arms.store_cost(path, 2)

    assert cost.n_iter.shape == (4, 2)
    assert list(cost.n_iter[2]) == [4, 5]
    assert bool(cost.ok[2, 1]) is False
    assert bool(cost.ok[2, 0]) is True
