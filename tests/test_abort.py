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


def test_an_empty_eligible_population_aborts_rather_than_reading_as_clean(
    coarse_store, tmp_path
):
    """0/0 is a finding about the instrument, not a clean pass.

    Expected value determined independently: with no eligible point there is no
    rate to compare, so "did any candidate exceed the threshold" has no answer
    -- and the honest response to a question with no answer is not "no".

    Bug this catches: the two obvious `0/0` implementations, both of which are
    silent. `failed / eligible` raises, which since 2e's Task 1 exits 5 on a
    perfectly well-formed store; a guarded `nan` or `0.0` compares False
    against the threshold and the verdict is **continue**.

    **And that case is reachable by exactly the mistake this section exists to
    catch**: a config naming the wrong variable, or a domain entirely land,
    gives `INSUFFICIENT_DATA` everywhere. Every denominator is empty, the abort
    finds nothing to abort on, and the run spends pass 2 producing a store of
    nothing.

    **PROVED TO BITE 2026-09-14:** the empty-population branch was changed to
    return `continue` -- the exact shape a guarded `0.0` would produce -- and
    this test failed while the other ten passed.
    """
    store = _copy(coarse_store, tmp_path)
    rows, columns, models = _shape(store)
    empty = np.full((rows, columns), Outcome.INSUFFICIENT_DATA.code, np.uint8)
    _set_outcomes(store, [empty] * models)

    verdict = abort_verdict(store)

    assert verdict.action == "abort"
    assert "no point" in verdict.reason
    assert all(rate.rate is None for rate in verdict.rates)
    assert all(rate.eligible == 0 for rate in verdict.rates)


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
