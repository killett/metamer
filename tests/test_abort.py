"""Section 14.1's abort verdict: a pure function of a finished pass-1 store."""

from __future__ import annotations

import shutil
import textwrap
from pathlib import Path

import numpy as np
import pytest
import xarray as xr
import zarr

from metamer.batch.abort import (
    DEFAULT_FAILURE_THRESHOLD,
    CandidateFailurePolicy,
    abort_verdict,
)
from metamer.batch.run import run
from metamer.batch.validation import ValidationError
from metamer.core.outcomes import Outcome

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")

_CONFIG = """
data_uri = "{uri}"
variable = "sla"
signal_terms = ["constant", "trend", "annual"]
candidates = ["white", "white + matern12"]
criteria = ["aic", "hqic"]

[warm_start]
coarse_stride = 2
"""


def _months(n: int) -> np.ndarray:
    origin = np.datetime64("2000-01-01")
    return np.array([origin + np.timedelta64(31 * i, "D") for i in range(n)])


@pytest.fixture(scope="module")
def coarse_store(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One REAL pass-1 store, built once and copied per test.

    A real store rather than a hand-built directory: the verdict reads the
    schema, the labels and the completion bitmap, and a fabricated store would
    let all three drift from what a run actually writes. **Only
    `/status/outcome` is overwritten by the tests below**, which is the one
    thing whose values they need to control and the one thing a fit cannot be
    asked to produce on demand.
    """
    base = tmp_path_factory.mktemp("coarse")
    # 10 x 8 AT STRIDE 2 GIVES A 5 x 4 COARSE GRID -- TWENTY POINTS, AND THE
    # TWENTY IS LOAD-BEARING. The boundary test needs `0.9 * total` to be a
    # whole number, so that "exactly at the threshold" is a case the fixture can
    # express at all; an 8 x 8 input gives sixteen coarse points, 0.9 * 16 =
    # 14.4, and the test would have compared 14/16 = 0.875 against 0.9 while
    # calling itself a boundary test. **Do not shrink this grid**; the test
    # asserts the arithmetic and will say so.
    dataset = xr.Dataset(
        {"sla": (("time", "y", "x"), np.zeros((24, 10, 8), dtype="float32"))},
        coords={"time": _months(24), "y": np.arange(10), "x": np.arange(8)},
    )
    uri = base / "in.zarr"
    dataset.to_zarr(uri)
    config = base / "c.toml"
    config.write_text(textwrap.dedent(_CONFIG.format(uri=uri)))
    store = base / "coarse.zarr"
    run(config, store, decimate=True)
    return store


def _copy(coarse_store: Path, tmp_path: Path) -> Path:
    """A private copy of the module's store."""
    destination = tmp_path / "pass1.zarr"
    shutil.copytree(coarse_store, destination)
    return destination


def _set_outcomes(store: Path, planes: list[np.ndarray]) -> None:
    """Overwrite `/status/outcome`, one `(y, x)` plane per candidate."""
    root = zarr.open_group(str(store), mode="r+")
    status = root["status"]
    assert isinstance(status, zarr.Group)
    array = status["outcome"]
    assert isinstance(array, zarr.Array)
    block = np.stack(planes, axis=2).astype(np.uint8)
    assert block.shape == array.shape, (block.shape, array.shape)
    array[:] = block


def _plane(shape: tuple[int, int], failing: float, *, fill: Outcome) -> np.ndarray:
    """A plane whose first `failing` fraction of points is DEGENERATE_HESSIAN.

    Expected rates are computed from the COUNT this returns, never from the
    fraction asked for, so a rounding difference cannot make a test agree with
    the code by accident.
    """
    total = shape[0] * shape[1]
    bad = int(round(failing * total))
    flat = np.full(total, fill.code, dtype=np.uint8)
    flat[:bad] = Outcome.DEGENERATE_HESSIAN.code
    return flat.reshape(shape)


def _shape(store: Path) -> tuple[int, int, int]:
    root = zarr.open_group(str(store), mode="r")
    status = root["status"]
    assert isinstance(status, zarr.Group)
    array = status["outcome"]
    assert isinstance(array, zarr.Array)
    return (int(array.shape[0]), int(array.shape[1]), int(array.shape[2]))


# --------------------------------------------------------------------------
# The verdict
# --------------------------------------------------------------------------


def test_a_clean_coarse_pass_continues(coarse_store, tmp_path):
    """The positive control every refusal below needs.

    Bug this catches: a verdict that aborts on everything, under which each
    threshold test here passes for the wrong reason. (i2), and it is not
    optional -- most of this module asserts that something stops.
    """
    store = _copy(coarse_store, tmp_path)
    rows, columns, models = _shape(store)
    _set_outcomes(store, [np.full((rows, columns), Outcome.OK.code, np.uint8)] * models)

    verdict = abort_verdict(store)

    assert verdict.action == "continue"
    assert verdict.candidates == ()
    assert all(rate.rate == 0.0 for rate in verdict.rates)


def test_one_candidate_above_the_threshold_is_dropped_under_the_drop_policy(
    coarse_store, tmp_path
):
    """The useful action: demote one candidate and keep the rest.

    Expected values determined independently from the constructed counts: one
    plane is 95% DEGENERATE_HESSIAN and the other 5%, on a grid whose size the
    test reads from the store rather than assuming.

    Bug this catches: a verdict that treats any failing candidate as an
    all-candidate failure, which would abort a run that section 14.1 says
    should continue with the rest -- and at ten hours that is the expensive
    direction.
    """
    store = _copy(coarse_store, tmp_path)
    rows, columns, _ = _shape(store)
    _set_outcomes(
        store,
        [
            _plane((rows, columns), 0.05, fill=Outcome.OK),
            _plane((rows, columns), 0.95, fill=Outcome.OK),
        ],
    )

    verdict = abort_verdict(store, policy=CandidateFailurePolicy.DROP)

    assert verdict.action == "drop"
    assert len(verdict.candidates) == 1
    assert verdict.candidates[0] == verdict.rates[1].candidate
    assert verdict.rates[0].rate is not None and verdict.rates[0].rate < 0.5


def test_every_candidate_above_the_threshold_aborts_whatever_the_policy(
    coarse_store, tmp_path
):
    """All-candidate failure is a config or data error, not a demotion.

    Expected value determined independently: section 14.1's table gives
    "**all candidates** > 90% failure" its own row, with **abort** and no
    policy attached -- dropping every candidate would continue a run with
    nothing left to fit.

    Bug this catches: the all-candidate branch folded into the single-candidate
    one, so `--on-candidate-failure=drop` demotes everything and the run
    proceeds to write a store in which every point is `CANDIDATE_DROPPED`.
    """
    store = _copy(coarse_store, tmp_path)
    rows, columns, models = _shape(store)
    _set_outcomes(store, [_plane((rows, columns), 0.95, fill=Outcome.OK)] * models)

    for policy in CandidateFailurePolicy:
        verdict = abort_verdict(store, policy=policy)
        assert verdict.action == "abort", policy
        assert "every candidate" in verdict.reason


def test_the_threshold_is_strictly_greater_and_exactly_at_it_continues(
    coarse_store, tmp_path
):
    """The boundary's side, asserted on all three of its cases.

    Expected values determined independently: section 14.1 says "> 90%
    failure", so **exactly** 90% continues. The grid is sized so that 90% is an
    exact count -- read from the store and asserted -- because a boundary tested
    only at 89.9 and 90.1 never touches the case the two readings differ on.

    Bug this catches: `>=` where the design doc says `>`. It is invisible on
    every realistic fixture, it silently lowers the abort threshold, and the
    direction is the expensive one: a run that section 14.1 would have let
    continue is stopped at hour nine.

    **PROVED TO BITE 2026-09-14**, and the fixture guard above proved itself
    first: on an 8 x 8 input the coarse grid is sixteen points, `0.9 * 16` is
    14.4, and the assertion refused the run rather than comparing 0.875 against
    0.9 while calling itself a boundary test. With the grid resized, changing
    `>` to `>=` fails here at exactly `failed=18, eligible=20, rate=0.9` and
    nowhere else in the module.
    """
    store = _copy(coarse_store, tmp_path)
    rows, columns, _ = _shape(store)
    total = rows * columns
    exact = int(round(DEFAULT_FAILURE_THRESHOLD * total))
    assert exact / total == pytest.approx(DEFAULT_FAILURE_THRESHOLD), (
        "the fixture cannot express an exact threshold; resize the grid"
    )

    for bad, expected in (
        (exact - 1, "continue"),
        (exact, "continue"),
        (exact + 1, "drop"),
    ):
        flat = np.full(total, Outcome.OK.code, dtype=np.uint8)
        flat[:bad] = Outcome.DEGENERATE_HESSIAN.code
        failing = flat.reshape((rows, columns))
        clean = np.full((rows, columns), Outcome.OK.code, np.uint8)
        _set_outcomes(store, [clean, failing])

        verdict = abort_verdict(store, policy=CandidateFailurePolicy.DROP)
        assert verdict.action == expected, (bad, verdict.rates[1])


def test_ineligible_points_change_neither_numerator_nor_denominator(
    coarse_store, tmp_path
):
    """A mostly-land grid gives the same verdict as its ocean.

    Expected values determined independently: `INSUFFICIENT_DATA` and
    `NOT_APPLICABLE` are both `is_eligible = False` per design doc section
    12.5, so a plane of nine ineligible points plus one failure has the same
    rate as a plane of one failure alone -- 1/1, not 1/10.

    Bug this catches: a rate over ALL points rather than eligible ones. On a
    global ocean-only run that reports ~70% "failure" and the number becomes
    noise everyone learns to ignore -- which is the failure design doc section
    8.6's denominator rule exists to prevent, here reaching a DECISION rather
    than a report.

    **PROVED TO BITE 2026-09-14:** the eligibility filter was removed so every
    point entered the denominator, and three tests in this module failed --
    this one, the empty-population one, and the per-candidate denominator one.
    **A rate over all points is a different quantity, and it shows up in three
    places at once.**
    """
    store = _copy(coarse_store, tmp_path)
    rows, columns, _ = _shape(store)
    plane = np.full((rows, columns), Outcome.INSUFFICIENT_DATA.code, np.uint8)
    plane.flat[0] = Outcome.DEGENERATE_HESSIAN.code
    clean = np.full((rows, columns), Outcome.OK.code, np.uint8)
    _set_outcomes(store, [clean, plane])

    verdict = abort_verdict(store, policy=CandidateFailurePolicy.DROP)

    assert verdict.rates[1].eligible == 1
    assert verdict.rates[1].failed == 1
    assert verdict.rates[1].rate == 1.0
    assert verdict.action == "drop"


def test_a_decided_skip_is_in_the_denominator_and_not_in_the_numerator(
    coarse_store, tmp_path
):
    """`SCREENED_OUT` counts as a point, not as a failure.

    Expected values determined independently: design doc section 12.5 groups it
    as a legitimate non-fit -- eligible, not a failure -- so a plane that is
    entirely `SCREENED_OUT` has a full denominator and a zero numerator.

    Bug this catches: the decided-skip group applied to one member and not
    another, which is the asymmetry 2e's Task 3 closed for `CANDIDATE_DROPPED`.
    Counting a screened candidate as failing would abort a run for being
    **cheaper** than it could have been.
    """
    store = _copy(coarse_store, tmp_path)
    rows, columns, _ = _shape(store)
    screened = np.full((rows, columns), Outcome.SCREENED_OUT.code, np.uint8)
    clean = np.full((rows, columns), Outcome.OK.code, np.uint8)
    _set_outcomes(store, [clean, screened])

    verdict = abort_verdict(store)

    assert verdict.rates[1].eligible == rows * columns
    assert verdict.rates[1].failed == 0
    assert verdict.rates[1].rate == 0.0
    assert verdict.action == "continue"


def test_an_empty_eligible_population_is_no_evidence_not_clean_and_not_abort(
    coarse_store, tmp_path
):
    """0/0 is a finding about the instrument -- and the finding is `no_evidence`.

    Expected value determined independently: with no eligible point there is no
    rate to compare, so "did any candidate exceed the threshold" has no answer
    -- and the honest response to a question with no answer is not "no". Nor is
    it "every candidate failed": that is a statement about a sample, and this
    sample holds nothing. Section 14.1, decided 2026-09-18: the verdict is its
    own third outcome and the run continues loudly.

    **INVERTED 2026-09-18, NOT DELETED.** This test pinned reading (a) -- abort
    -- from 2026-09-14, and (a) was decided against on 2026-09-18 for three
    reasons recorded at section 14.1: the abort was a gate reading the wrong
    subject (an empty coarse sample is a statement about the SAMPLE, and 2c's
    criterion-1 fixture has land on every stride-2 row while the fine grid
    holds data); a wrong abort is recovered only by `--no-early-abort`, which
    disables the mechanism everywhere, while a wrong continue costs one run
    that section 14.2 then describes; and section 14.1 aborts only on
    near-total failure PATTERNS, and an empty sample is no pattern at all.

    Bug this catches: the two obvious `0/0` implementations, both silent.
    `failed / eligible` raises, which since 2e's Task 1 exits 5 on a perfectly
    well-formed store; a guarded `nan` or `0.0` compares False against the
    threshold and the verdict is **continue** -- indistinguishable from a clean
    pass. And the third, since 2026-09-18: the (a) abort still standing.

    **PROVED TO BITE 2026-09-14:** the empty-population branch was changed to
    return `continue` -- the exact shape a guarded `0.0` would produce -- and
    this test failed while the other ten passed. The inversion keeps that
    mutant fatal: `continue` is still not `no_evidence`.

    **THE PREDICATE UNDER THIS FIXTURE MOVED ON 2026-09-19, AND THE FIXTURE
    DID NOT.** This test pinned `no_evidence` while the gate asked
    `eligible > 0`; the gate now asks `fitted > 0`, by
    `Outcome.is_fit_verdict` and section 12.5's non-fit grouping table. **The
    two predicates now genuinely differ**, so that this fixture still reaches
    `no_evidence` is a fact to check and not a carry-over: it does, because
    `INSUFFICIENT_DATA` is a non-fit under section 12.5 as well as ineligible
    under section 8.6 -- it is in BOTH excluded sets, which is why it is the
    one member that cannot tell the two predicates apart. **The member that
    does tell them apart is `SCREENED_OUT`**, and the sibling test named for it
    is the one that would have caught the old predicate. Checked green here
    before and after the change, 2026-09-19.
    """
    store = _copy(coarse_store, tmp_path)
    rows, columns, models = _shape(store)
    empty = np.full((rows, columns), Outcome.INSUFFICIENT_DATA.code, np.uint8)
    _set_outcomes(store, [empty] * models)

    verdict = abort_verdict(store)

    assert verdict.action == "no_evidence"
    assert verdict.candidates == ()
    assert "no evidence" in verdict.reason
    assert "--no-early-abort" not in verdict.reason, (
        "nothing is blocked under (b); a message naming a lift is a wrong instruction"
    )
    assert all(rate.rate is None for rate in verdict.rates)
    assert all(rate.eligible == 0 for rate in verdict.rates)


def test_a_coarse_sample_of_decided_skips_is_no_evidence_and_not_a_clean_pass(
    coarse_store, tmp_path
):
    """`no_evidence` asks whether anything was FITTED, not whether anything was eligible.

    Expected value determined independently: section 12.5's non-fit grouping
    table says `SCREENED_OUT` is *"a decision was taken not to fit this
    candidate"* and calls it a **legitimate non-fit** -- a decided skip, not a
    verdict about a series. Section 14.1's 2026-09-18 decision says a sample
    holding no evidence is not a pass. A sample in which every point is a
    decided skip holds exactly as much evidence about the candidates as an
    empty one: none. So the verdict is `no_evidence`.

    **THIS IS THE DEFECT OPEN QUESTION 24's ARTIFACT CHECK FOUND, AND IT IS
    INDEPENDENT OF THAT QUESTION'S ANSWER (2026-09-19).** The gate's subject is
    *nothing was fitted*; it was asking *nothing was eligible*. The two
    coincide only under section 8.6's reading of `INSUFFICIENT_DATA`, which
    section 12.5 supersedes -- so the predicate was a proxy that agreed with
    its subject in the common case and diverged exactly where the gate matters.
    **The tell is a gate whose predicate names a different quantity from its
    own reason string**, and this one's reason said "eligible" in section 8.6's
    vocabulary. Same shape as open question 22's quiet gate reading the host's
    `loadavg` because `loadavg` was available, and as the stall gate reading
    time-waiting because PSI was available. Third instance; recorded as the
    pattern at `Outcome.is_fit_verdict`.

    Bug this catches: the shipped predicate, `rate is not None` -- which is
    `eligible > 0`. `SCREENED_OUT` is eligible and is not a failure, so an
    all-`SCREENED_OUT` coarse sample gives every candidate `0 / 20 = 0.0`, and
    the verdict returns **`continue`, "no candidate failed above 90%"** -- a
    clean pass reported over a sample in which no candidate was ever fitted.
    The assertion below fails on that code and passes only when the gate reads
    fits.

    **REACHABILITY, STATED RATHER THAN IMPLIED:** `SCREENED_OUT` has no
    producer today (section 12.5 lists the debiased Whittle engine and the
    screening config block as what would give it one), so this plane is
    constructed. That makes the defect unreachable in production **today** and
    does not make the predicate right -- and open question 24's flip gives it a
    reachable producer immediately, because `INSUFFICIENT_DATA` becomes
    eligible while remaining a non-fit.
    """
    store = _copy(coarse_store, tmp_path)
    rows, columns, models = _shape(store)
    skipped = np.full((rows, columns), Outcome.SCREENED_OUT.code, np.uint8)
    _set_outcomes(store, [skipped] * models)

    verdict = abort_verdict(store)

    assert verdict.action == "no_evidence"
    assert verdict.candidates == ()
    assert all(rate.fitted == 0 for rate in verdict.rates)
    assert all(rate.eligible == rows * columns for rate in verdict.rates), (
        "the point of this fixture is that the sample IS eligible and is still "
        "not evidence; an eligible count of zero would make it a restatement "
        "of the empty-population test"
    )


def test_an_empty_sample_and_an_all_failing_sample_are_different_verdicts(
    coarse_store, tmp_path
):
    """The case the abort exists for, and the case it must not mistake for it.

    Expected values determined independently from section 14.1's table: every
    candidate failing above 90% is the config-or-data-error row, `abort`; no
    candidate with any eligible point is the no-evidence row, `no_evidence`.
    Same store, two fills, and the two verdicts must differ.

    Bug this catches: a collapse in EITHER direction, asserted as one
    property. The empty guard placed AFTER the all-candidates check -- `_decide`
    tests `len(over) == len(judgeable)`, and with no judgeable candidate both
    are empty, so `0 == 0` reports "every candidate failed above 90%" for a
    sample in which nothing was judged, the (a2b) collapse that opened this
    question at Task 5 -- fails here on the `empty` key. And the abort's own
    case going quiet -- an all-failing sample reading as `no_evidence` -- fails
    here on the `failing` key. Each single-case test above guards one side;
    this one binds both to one fixture so they cannot be edited apart.
    """
    rows, columns, models = _shape(coarse_store)

    empty = _copy(coarse_store, tmp_path / "empty")
    _set_outcomes(
        empty,
        [np.full((rows, columns), Outcome.INSUFFICIENT_DATA.code, np.uint8)] * models,
    )
    failing = _copy(coarse_store, tmp_path / "failing")
    _set_outcomes(failing, [_plane((rows, columns), 1.0, fill=Outcome.OK)] * models)

    actions = {
        "empty": abort_verdict(empty).action,
        "failing": abort_verdict(failing).action,
    }

    assert actions == {"empty": "no_evidence", "failing": "abort"}
    assert abort_verdict(failing).candidates != ()
    assert abort_verdict(empty).candidates == ()


def test_each_candidate_carries_its_own_denominator(coarse_store, tmp_path):
    """Two candidates, two populations, and the table says so.

    **THIS CASE IS CONSTRUCTED BECAUSE NO FIXTURE IN THIS PROJECT CAN PRODUCE
    IT.** `fit.py` computes `design_info(t, mask)` once, before the candidate
    loop, so the design-derived outcomes -- `INSUFFICIENT_DATA` and
    `RANK_DEFICIENT_X` -- are constant along the model axis in v1 and every
    fitted store has equal denominators. That is an implementation property,
    not a contract: it holds until a joint signal x noise search lands. (i12) --
    a uniform fixture set cannot test a freedom the contract leaves open, so the
    outcome array is written rather than fitted.

    Expected values determined independently by construction: candidate 0 is
    eligible everywhere, candidate 1 at one point only.

    Bug this catches: one denominator computed for the table and reused for
    every row. Today that is invisible; the moment the model axis carries
    per-candidate eligibility it silently rescales every rate but one, and the
    verdict is taken on the rescaled ones.
    """
    store = _copy(coarse_store, tmp_path)
    rows, columns, _ = _shape(store)
    wide = np.full((rows, columns), Outcome.OK.code, np.uint8)
    narrow = np.full((rows, columns), Outcome.NOT_APPLICABLE.code, np.uint8)
    narrow.flat[0] = Outcome.OK.code
    _set_outcomes(store, [wide, narrow])

    verdict = abort_verdict(store)

    assert verdict.rates[0].eligible == rows * columns
    assert verdict.rates[1].eligible == 1
    assert verdict.rates[0].eligible != verdict.rates[1].eligible


def test_an_incomplete_pass_one_store_is_refused(coarse_store, tmp_path):
    """A rate over a partial store is a rate over a spatial prefix.

    Expected value determined independently: tiles are processed in spatial
    order, so an unfinished store holds a geographically contiguous region --
    section 14.1 spends four paragraphs on why that is not a sample.

    Bug this catches: a verdict taken from a killed pass 1, which would compute
    a real-looking rate over one basin and abort or continue the whole run on
    it. The message names the count so the reader knows it is not a config
    fault.
    """
    store = _copy(coarse_store, tmp_path)
    root = zarr.open_group(str(store), mode="r+")
    completion = root["completion"]
    assert isinstance(completion, zarr.Group)
    tiles = completion["tiles"]
    assert isinstance(tiles, zarr.Array)
    bits = np.asarray(tiles[:])
    bits.flat[0] = 0
    tiles[:] = bits

    with pytest.raises(ValidationError, match="outstanding"):
        abort_verdict(store)


def test_the_verdict_is_a_function_of_the_store_and_nothing_else(
    coarse_store, tmp_path, monkeypatch
):
    """Same store, same verdict -- twice, and from another directory.

    Expected value determined independently: a verdict that a resuming operator
    cannot reproduce from the artifact is not auditable, and section 11.3's
    reproducibility guarantee is about exactly this shape.

    Bug this catches: process-local state leaking into a decision -- a cached
    lookup built at import, a relative path resolved against the cwd, anything
    read from the environment. (k): test across a change of process state, not
    only across two calls.
    """
    store = _copy(coarse_store, tmp_path)
    rows, columns, _ = _shape(store)
    _set_outcomes(
        store,
        [
            _plane((rows, columns), 0.05, fill=Outcome.OK),
            _plane((rows, columns), 0.95, fill=Outcome.OK),
        ],
    )

    first = abort_verdict(store, policy=CandidateFailurePolicy.DROP)
    monkeypatch.chdir(tmp_path)
    second = abort_verdict(store, policy=CandidateFailurePolicy.DROP)

    assert first == second


def test_the_policy_decides_what_a_single_failing_candidate_does(
    coarse_store, tmp_path
):
    """All three policies, on one population.

    Expected values determined independently from section 14.1: abort is the
    default, drop demotes, continue keeps -- and `--no-early-abort` is a
    separate flag that disables the mechanism rather than a fourth policy.

    Bug this catches: a policy argument that is parsed and ignored -- (a2c),
    populated but nothing acts on it. All three would look correct in a test
    that only ever passed the default.
    """
    store = _copy(coarse_store, tmp_path)
    rows, columns, _ = _shape(store)
    _set_outcomes(
        store,
        [
            _plane((rows, columns), 0.05, fill=Outcome.OK),
            _plane((rows, columns), 0.95, fill=Outcome.OK),
        ],
    )

    actions = {
        policy: abort_verdict(store, policy=policy).action
        for policy in CandidateFailurePolicy
    }

    assert actions == {
        CandidateFailurePolicy.ABORT: "abort",
        CandidateFailurePolicy.DROP: "drop",
        CandidateFailurePolicy.CONTINUE: "continue",
    }
