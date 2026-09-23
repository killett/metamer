"""Sub-phase 2f Task 2: rates per branch and per candidate, both denominators.

**THE FIXTURES CONSTRUCT A `StoreView` DIRECTLY, AND THAT IS A DELIBERATE
BOUNDARY RATHER THAN A SHORTCUT.** `compute` takes a `StoreView`, so that is
its subject; planting outcome codes is the only way to reach censuses a real
run cannot be made to produce on demand -- an all-`SCREENED_OUT` candidate, a
store interrupted at a chosen fraction. **The risk a constructed fixture
carries is that it drifts from what the reader actually returns**, so
`test_compute_runs_on_a_real_store_and_every_cell_is_in_the_branch_table` runs
the whole path on a store a real run wrote, and the reader's own suite binds
`StoreView` to the schema.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import xarray as xr

from metamer.batch.run import run
from metamer.core.outcomes import Outcome
from metamer.report.numbers import NO_DOMAIN_MASK_CAVEAT, compute
from metamer.report.reader import Completion, StoreView, read_store

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")

_CONFIG = """
data_uri = "{uri}"
variable = "sla"
signal_terms = ["constant", "trend"]
candidates = ["white", "white + matern12"]
criteria = ["aic", "hqic"]
"""


def _plane(census: dict[Outcome, int]) -> list[int]:
    """One candidate's cells, as raw codes, from a census written by hand."""
    codes: list[int] = []
    for member, count in census.items():
        codes.extend([member.code] * count)
    return codes


def _view(
    *censuses: dict[Outcome, int],
    labels: tuple[str, ...] | None = None,
    attrs: dict[str, Any] | None = None,
    completion: tuple[int, int] = (4, 4),
) -> StoreView:
    """A `StoreView` carrying one planted census per candidate.

    Every candidate's plane is the same length, which the shape requires; the
    caller's censuses must therefore sum alike. Arrays the numbers module does
    not read are shaped correctly and left at their fill values.
    """
    planes = [_plane(census) for census in censuses]
    widths = {len(plane) for plane in planes}
    assert len(widths) == 1, f"candidates have different cell counts: {widths}"
    width = widths.pop()
    outcome = np.array(planes, dtype=np.uint8).T.reshape(1, width, len(planes))
    models = labels or tuple(f"candidate_{i}" for i in range(len(planes)))
    return StoreView(
        path=Path("/nonexistent"),
        outcome=outcome,
        delta_ic=np.zeros((1, width, len(planes), 1), dtype=np.float32),
        selected=np.full((1, width, 1), -2, dtype=np.int16),
        n_valid=np.full((1, width), -1, dtype=np.int16),
        iterations=np.full((1, width, len(planes)), 65535, dtype=np.uint16),
        model_labels=models,
        criterion_labels=("aic",),
        attrs=attrs if attrs is not None else {},
        completion=Completion(complete=completion[0], total=completion[1]),
        disagreements=(),
    )


def test_the_branch_table_reproduces_a_planted_histogram_exactly():
    """Each branch count is the number planted, and they sum to the cells.

    Expected values determined independently: `{OK: 809, DEGENERATE_HESSIAN:
    91}` is the committed real-data spike's own histogram, transcribed rather
    than invented, so this ties the counter to a number already in the tree.
    900 = 809 + 91 is the cell count of that one-candidate plane.

    Bug this catches: an off-by-one in the per-branch tally, and a census built
    from `np.unique` without `return_counts` alignment -- both of which produce
    a plausible table whose entries are wrong by one.

    **THE SUM IS ASSERTED, NOT ONLY THE ENTRIES** -- handoff (c7). A table
    whose values are right and whose population is smaller than the grid is
    what a dropped branch looks like, and only the sum sees it.
    """
    numbers = compute(_view({Outcome.OK: 809, Outcome.DEGENERATE_HESSIAN: 91}))

    assert numbers.by_branch == {Outcome.OK: 809, Outcome.DEGENERATE_HESSIAN: 91}
    assert sum(numbers.by_branch.values()) == 900
    assert numbers.aggregate.points == 900


def test_insufficient_data_is_inside_both_denominators():
    """A thin record is in the domain and the run reached it.

    Expected values computed by hand: 2 failed and 6 OK give 8 fit verdicts;
    12 `INSUFFICIENT_DATA` are covered without being fitted. So fitted = 8,
    covered = 20, and the two rates are 2/8 = 0.25 and 2/20 = 0.1.

    Bug this catches: a regression to design doc section 8.6's rule, which
    excluded this member from every denominator on the grounds that it meant
    "land, permanent ice". **That is the whole of D2**: land is
    `NOT_APPLICABLE`, and *this series* having too thin a record is a real
    statement about record coverage, which is exactly what the coverage
    denominator is for.
    """
    numbers = compute(
        _view(
            {
                Outcome.DEGENERATE_HESSIAN: 2,
                Outcome.OK: 6,
                Outcome.INSUFFICIENT_DATA: 12,
            }
        )
    )
    tally = numbers.aggregate

    assert (tally.fitted, tally.covered, tally.eligible) == (8, 20, 20)
    assert tally.rate == pytest.approx(0.25)
    assert tally.coverage_rate == pytest.approx(0.1)


def test_not_applicable_is_outside_both_denominators():
    """Out of domain leaves the denominator entirely, by section 12.5.

    Expected values computed by hand: 3 failed of 5 fitted, plus 15
    `NOT_APPLICABLE`. Land is in neither denominator, so both rates read 3/5 =
    0.6 and the counts stop at 5.

    Bug this catches: the collapse section 12.5 says makes a failure rate
    uninterpretable -- a denominator containing land reports a number that is
    part failure rate and part land fraction, and on a global grid the second
    part dominates. **It is still COUNTED in the branch table**, which is the
    other half: the report must say how much of the grid was out of domain.
    """
    numbers = compute(
        _view(
            {
                Outcome.RANK_DEFICIENT_X: 3,
                Outcome.OK: 2,
                Outcome.NOT_APPLICABLE: 15,
            }
        )
    )
    tally = numbers.aggregate

    assert (tally.fitted, tally.covered, tally.eligible) == (5, 5, 5)
    assert tally.rate == pytest.approx(0.6)
    assert tally.coverage_rate == pytest.approx(0.6)
    assert numbers.by_branch[Outcome.NOT_APPLICABLE] == 15
    assert tally.points == 20


def test_not_attempted_is_counted_in_the_branch_table_and_in_no_denominator():
    """The absence of information is reported and never divided by.

    Expected values computed by hand: 1 failed of 4 fitted, plus 16
    `NOT_ATTEMPTED`. Covered excludes them because the run never reached them,
    so both rates read 1/4 = 0.25 -- and the branch table still carries all 16.

    Bug this catches: "excluded means missing". A report that dropped this
    member from the table would describe an interrupted run's grid as smaller
    than the one that ran, which is precisely the fact an unfinished store
    exists to communicate (D6). **`eligible` still counts them**, and that is
    not a contradiction: `is_eligible` answers a question about the DOMAIN and
    its values are in committed artifacts, which is why the coverage
    denominator is its own predicate rather than a redefinition of it.
    """
    numbers = compute(
        _view({Outcome.ILL_CONDITIONED_X: 1, Outcome.OK: 3, Outcome.NOT_ATTEMPTED: 16})
    )
    tally = numbers.aggregate

    assert numbers.by_branch[Outcome.NOT_ATTEMPTED] == 16
    assert (tally.fitted, tally.covered) == (4, 4)
    assert tally.eligible == 20
    assert tally.rate == pytest.approx(0.25)
    assert tally.coverage_rate == pytest.approx(0.25)


def test_the_dilution_is_proportional_to_how_far_the_run_did_not_get():
    """An interrupted run does not report a better rate for being killed early.

    Expected values computed by hand from three stores whose FITTED cells are
    identical -- 3 failed of 4 -- and which differ only in how many cells the
    run never reached: 0, 16 and 96. The coverage rate is 0.75 in all three.
    Had the denominator been `eligible`, they would read 0.75, 0.15 and 0.03:
    **the less the run did, the better it would look.**

    Bug this catches: `NOT_ATTEMPTED` inside the coverage denominator. That is
    not a hypothetical shape -- it is what `is_eligible` returns today, and the
    plan's own Task 2 text described the denominator as `is_eligible` "which
    excludes `NOT_APPLICABLE` only". A reader deciding whether to restart a
    killed ten-hour run would have been shown a number that improves with the
    interruption.

    **THE THREE ARMS ARE THE DISCRIMINATION** -- (a10). One store proves
    nothing: any denominator yields some number. Only the ladder shows the
    number does not move with the thing it must not move with, and the ladder
    is monotone in the wrong direction under the wrong denominator, which is
    what makes the failure legible rather than merely detectable.
    """
    fitted_part: dict[Outcome, int] = {Outcome.DEGENERATE_HESSIAN: 3, Outcome.OK: 1}
    rates = [
        compute(_view(fitted_part | ({Outcome.NOT_ATTEMPTED: n} if n else {})))
        for n in (0, 16, 96)
    ]

    assert [r.aggregate.coverage_rate for r in rates] == [
        pytest.approx(0.75),
        pytest.approx(0.75),
        pytest.approx(0.75),
    ]
    assert [r.aggregate.covered for r in rates] == [4, 4, 4]
    assert [r.aggregate.eligible for r in rates] == [4, 20, 100]
    assert [r.by_branch.get(Outcome.NOT_ATTEMPTED, 0) for r in rates] == [0, 16, 96]


def test_two_candidates_get_two_denominators():
    """Each row's rate is over that row's own population.

    Expected values computed by hand. Candidate `white` fits all 20 with 4
    failures: 4/20 = 0.2 on both denominators. Candidate `matern` fits 10, 5 of
    them failing, and is `SCREENED_OUT` at the other 10: 5/10 = 0.5 fitted and
    5/20 = 0.25 covered. **Four numbers, no two of which are interchangeable.**

    Bug this catches: a shared denominator across rows, which invites a
    comparison that is not available -- two candidates screened at different
    points have not been asked the same question, and a table that hides that
    reads as if they had.
    """
    numbers = compute(
        _view(
            {Outcome.DEGENERATE_HESSIAN: 4, Outcome.OK: 16},
            {Outcome.DEGENERATE_HESSIAN: 5, Outcome.OK: 5, Outcome.SCREENED_OUT: 10},
            labels=("white", "matern"),
        )
    )
    white, matern = numbers.by_candidate

    assert (white.candidate, matern.candidate) == ("white", "matern")
    assert (white.tally.fitted, white.tally.covered) == (20, 20)
    assert white.tally.rate == pytest.approx(0.2)
    assert white.tally.coverage_rate == pytest.approx(0.2)
    assert (matern.tally.fitted, matern.tally.covered) == (10, 20)
    assert matern.tally.rate == pytest.approx(0.5)
    assert matern.tally.coverage_rate == pytest.approx(0.25)


def test_the_two_rates_separate_where_a_reached_point_carries_no_fit_verdict():
    """Criterion 12's store: 1.00 against 0.60, and what actually opens the gap.

    Expected values determined independently, from D2b's own measurement: 12
    fitted cells all failing and 8 cells the run reached but could not fit give
    12/12 = 1.00 and 12/20 = 0.60.

    **THE GAP IS NOT LAND, AND THE PLAN'S WORDING INVITES THAT READING.** True
    land is `NOT_APPLICABLE` and is outside BOTH denominators, so it cannot
    separate them at all -- `test_not_applicable_is_outside_both_denominators`
    is the proof. What opens the gap is an in-domain point the run REACHED and
    did not fit, which on a global run is dominated by thin records. The
    second arm says the same thing from the other side: an all-fit store
    reports the two rates equal, **and that is a property of its census rather
    than of its geography** -- four members are covered without being fitted,
    so a store carrying any of them separates the rates whatever its coastline.

    Bug this catches: a report that prints one denominator. On this project's
    one ocean box the two numbers coincide, so every fixture and every real run
    to date would show a single-denominator report as correct -- which is
    exactly why it would have shipped.
    """
    exposed = compute(
        _view({Outcome.DEGENERATE_HESSIAN: 12, Outcome.INSUFFICIENT_DATA: 8})
    )
    all_fit = compute(_view({Outcome.DEGENERATE_HESSIAN: 12, Outcome.OK: 8}))

    assert exposed.aggregate.rate == pytest.approx(1.0)
    assert exposed.aggregate.coverage_rate == pytest.approx(0.6)
    assert all_fit.aggregate.rate == pytest.approx(0.6)
    assert all_fit.aggregate.coverage_rate == pytest.approx(0.6)


def test_a_candidate_that_fitted_nothing_reports_both_columns_unavailable():
    """Nothing fitted is not a clean pass, in either column.

    Expected values determined independently: a candidate `SCREENED_OUT` at all
    20 cells has fitted = 0, so neither rate exists; its sibling fits all 20
    with 2 failures and reports 0.1 twice. **Both rows print and they must not
    print alike.**

    Bug this catches: the coverage column reporting **0.0** for a candidate
    that was never tried. 0/20 is arithmetically fine and reads as a perfect
    score -- better than the sibling that actually ran -- which is section
    14.1's `no_evidence` collapse arriving one granularity down, in the
    report's own table.

    **THE COUNT SURVIVES THE RATE'S ABSENCE**: `covered` is still 20, so the
    row says how much was skipped rather than going blank. And the fixture is
    two candidates on purpose -- one where every row is unavailable cannot
    distinguish a rule that discriminates from a report that has simply
    broken.
    """
    numbers = compute(
        _view(
            {Outcome.SCREENED_OUT: 20},
            {Outcome.DEGENERATE_HESSIAN: 2, Outcome.OK: 18},
            labels=("dropped", "fitted"),
        )
    )
    dropped, fitted = numbers.by_candidate

    assert dropped.tally.rate is None
    assert dropped.tally.coverage_rate is None
    assert dropped.tally.unavailable is not None
    assert "fitted" in dropped.tally.unavailable
    assert dropped.tally.covered == 20
    assert fitted.tally.rate == pytest.approx(0.1)
    assert fitted.tally.coverage_rate == pytest.approx(0.1)


def test_the_caveat_is_present_without_a_domain_mask_and_absent_with_one():
    """The caveat tracks the store, not the calendar.

    Expected value determined independently: design doc section 13.6's declared
    domain mask is Task 4's field, so **every store in existence lacks it**
    today and the caveat applies to all of them; a store that declares one does
    not need it.

    Bug this catches: a hard-coded caveat, which is wrong the day after section
    13.6 lands and then stays wrong -- and a missing one, which is wrong today.
    Both arms are asserted because a caveat that is always present and one that
    is correct are indistinguishable on today's stores.
    """
    without = compute(_view({Outcome.OK: 4}))
    with_mask = compute(_view({Outcome.OK: 4}, attrs={"domain_mask": "declared"}))

    assert without.caveat == NO_DOMAIN_MASK_CAVEAT
    assert with_mask.caveat is None


def test_the_incompleteness_travels_with_the_numbers():
    """`complete of total` is a field, beside every denominator (D6).

    Expected value determined independently: the completion bitmap's own
    counts, which the reader already reports and which this record carries
    rather than recomputing.

    Bug this catches: a rate rendered without its population. Two reports over
    different fractions of a grid are not comparable, and a reader who cannot
    see the fraction has no way to know that.
    """
    numbers = compute(_view({Outcome.OK: 4}, completion=(3, 16)))

    assert (numbers.complete, numbers.total) == (3, 16)


def test_compute_runs_on_a_real_store_and_every_cell_is_in_the_branch_table():
    """The constructed fixtures are tied to what a real run actually writes.

    Expected value determined independently: the store's own outcome array
    size, which is the grid times the candidate axis, compared against the
    branch table's sum.

    Bug this catches: a `StoreView` the tests construct in a shape the reader
    never returns -- a transposed candidate axis, a dtype the census miscounts
    -- which would make every other test in this file green against a fixture
    nothing produces. **This is the only test here that cannot be satisfied by
    a hand-built object.**
    """
    view = read_store(_real_store.path)
    numbers = compute(view)

    assert sum(numbers.by_branch.values()) == view.outcome.size
    assert len(numbers.by_candidate) == len(view.model_labels)
    assert numbers.total > 0


class _RealStore:
    """Holder so the real store is built once for the module."""

    path: Path


_real_store = _RealStore()


@pytest.fixture(scope="module", autouse=True)
def _build_real_store(tmp_path_factory: pytest.TempPathFactory) -> None:
    """One real store from a real run, built once for the end-to-end test."""
    base = tmp_path_factory.mktemp("numbers")
    origin = np.datetime64("2000-01-01")
    times = np.array([origin + np.timedelta64(31 * i, "D") for i in range(24)])
    dataset = xr.Dataset(
        {"sla": (("time", "y", "x"), np.zeros((24, 4, 4), dtype="float32"))},
        coords={"time": times, "y": np.arange(4), "x": np.arange(4)},
    )
    uri = base / "in.zarr"
    dataset.to_zarr(uri)
    config = base / "c.toml"
    config.write_text(textwrap.dedent(_CONFIG.format(uri=uri)))
    store = base / "out.zarr"
    run(config, store)
    _real_store.path = store
