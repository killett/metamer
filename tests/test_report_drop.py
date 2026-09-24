"""Sub-phase 2f Task 3: the drop row, over pass 1's population.

**EVERY STORE HERE IS FROM A REAL TWO-PASS RUN.** The drop row's whole subject
is the relationship between two stores -- a decision recorded in pass 2 over a
population that only pass 1 holds -- and a constructed `StoreView` cannot
express that relationship, because the thing under test is which of the two
stores the denominator came from. The verdict's ACTION is forced to `drop`
while its RATES stay the ones pass 1 actually produced, which is 2e's own
idiom (`tests/test_exit_criteria_2e.py`) and is what makes "the recomputation
agrees" a real assertion rather than a comparison of an injected number with
itself.
"""

from __future__ import annotations

import pathlib
import shutil
from dataclasses import replace
from typing import Any

import numpy as np
import pytest
import zarr

from metamer.batch import twopass
from metamer.batch.abort import CandidateFailurePolicy, abort_verdict
from metamer.batch.decimate import pass1_store_path
from metamer.batch.twopass import run_two_pass
from metamer.core.outcomes import Outcome
from metamer.report.drop import CARRIED, RECOMPUTED, describe
from metamer.report.reader import Completion, StoreView, read_store
from tests.test_early_abort import _config, _early_abort, _input, _labels, _outcome

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")


@pytest.fixture(scope="module")
def dropped_run(tmp_path_factory: pytest.TempPathFactory) -> pathlib.Path:
    """A real two-pass run whose second candidate is dropped, built once.

    The verdict is the REAL one with its action forced, so the recorded rates
    are the rates pass 1 actually produced.
    """
    base = tmp_path_factory.mktemp("drop")
    config = _config(base, _input(base))
    monkeypatch = pytest.MonkeyPatch()

    def _forced_drop(path: pathlib.Path | str, **kwargs: Any) -> Any:
        real = abort_verdict(path, **kwargs)
        target = _labels(pathlib.Path(path))[1]
        return replace(
            real, action="drop", candidates=(target,), reason="forced drop, real rates"
        )

    monkeypatch.setattr(twopass, "abort_verdict", _forced_drop)
    report = run_two_pass(
        config, base / "out.zarr", candidate_failure_policy=CandidateFailurePolicy.DROP
    )
    monkeypatch.undo()
    assert report.pass1_path is not None and report.pass2 is not None
    return pathlib.Path(report.store_path)


def test_a_real_drop_reports_the_coarse_denominator_and_pass_one_agrees(dropped_run):
    """The row's denominator is pass 1's live population, recomputed and agreeing.

    Expected values determined independently, and they are 2e's criterion 14's
    own: a 6 x 6 grid at stride 2 has a 3 x 3 coarse lattice, all data, so the
    candidate was live at **9** points; pass 2 has **36** and the drop wrote
    `CANDIDATE_DROPPED` into all of them.

    Bug this catches: D9's feedback loop -- a denominator taken from the pass-2
    store, where the run itself wrote the drop at every point, so the rate
    reads ~100% and reports the decision rather than the candidate. **9 against
    36 is the discrimination**: a row computed over pass 2 cannot produce 9.

    **AND THE RECOMPUTATION IS WHAT MAKES "CARRIED" DEFENSIBLE.** The record is
    primary because the threshold and policy exist nowhere else, but a carried
    counter nobody checks is a number that drifts silently; here pass 1's
    arrays are present, so they are read and compared.
    """
    section = describe(read_store(dropped_run))
    (row,) = section.dropped_rows

    assert section.evaluated is True
    assert section.action == "drop"
    assert len(section.rows) == 2, (
        "every judged candidate gets a row, not only the dropped one"
    )
    assert row.candidate == _labels(dropped_run)[1]
    assert row.live == 9
    assert row.denominator == "fitted"
    assert row.eligible == 9
    assert row.provenance == RECOMPUTED
    assert row.defects == ()
    assert (_outcome(dropped_run)[:, :, 1] == Outcome.CANDIDATE_DROPPED.code).all()
    assert _outcome(dropped_run)[:, :, 1].size == 36


def test_pass_one_holds_no_unreached_points_which_is_what_keeps_the_denominator_honest(
    dropped_run,
):
    """The premise under the carried denominator, asserted rather than assumed.

    Expected value determined independently: `early_abort.rates[].eligible` is
    an `is_eligible` count, written before `Outcome.is_covered` existed, and
    `is_eligible` counts `NOT_ATTEMPTED`. It is therefore a safe denominator
    only while pass 1 holds none -- true of a FINISHED pass 1, and a verdict is
    only reached after pass 1 completes.

    Bug this catches: the dilution 2f Task 2 removed from the report arriving
    through the carried record instead. If pass 1 ever holds unreached points,
    the drop rate reads LOW by exactly their share, and the row would look
    ordinary. **This is the same shape as section 12.5's "a finished store
    should hold none"** -- a number defensible under a completeness assumption
    with the assumption recorded nowhere near it.

    `describe` reports the same condition as a defect rather than raising,
    because D6 says a store is described and not refused; this asserts it on a
    store where it must hold.
    """
    pass1 = read_store(pass1_store_path(dropped_run))
    codes = pass1.outcome[..., 1].ravel().tolist()

    assert not any(Outcome.from_code(int(c)) is Outcome.NOT_ATTEMPTED for c in codes)
    assert all(
        Outcome.from_code(int(c)).is_covered == Outcome.from_code(int(c)).is_eligible
        for c in codes
    )


def test_the_row_survives_a_missing_pass_one_store_and_says_it_is_carried(
    dropped_run, tmp_path
):
    """A store shipped without its pass-1 sibling still reports, labelled.

    Expected value determined independently: the record carries `failed`,
    `eligible`, `fitted` and `rate` per candidate, so every field the row needs
    is in pass 2's attrs; only the CHECK is unavailable.

    Bug this catches: a report that fails, or silently omits the row, on a
    store someone else shipped -- which is the property section 14.2 exists
    for. **And the label is the other half**: a number presented identically
    whether or not it was verified teaches a reader that it was.
    """
    copied = tmp_path / "out.zarr"
    shutil.copytree(dropped_run, copied)
    assert not pass1_store_path(copied).exists()

    section = describe(read_store(copied))
    (row,) = section.dropped_rows

    assert row.live == 9
    assert row.provenance == CARRIED
    assert "not present" in row.provenance


def test_a_tampered_rate_disagreeing_with_pass_one_is_reported_as_a_defect(
    dropped_run, tmp_path
):
    """When the evidence is there, the carried record is not taken on trust.

    Expected value determined independently: the copied store's record is
    edited to claim `failed` one higher than pass 1's arrays produce, so the
    recomputation must disagree by exactly that and name both numbers.

    Bug this catches: an implementation that reads the record, notices pass 1
    is present, and reports "recomputed" without comparing -- which is
    indistinguishable from a real check on every store where the record
    happens to be right. **The tamper is the (a10) demonstration**: the
    agreement test above cannot tell a comparison from a constant.

    **REPORTED, NOT RAISED.** A store with a contradiction is described; a
    report that refuses one cannot be run on the store that has it.
    """
    copied = tmp_path / "out.zarr"
    shutil.copytree(dropped_run, copied)
    shutil.copytree(pass1_store_path(dropped_run), pass1_store_path(copied))

    group = zarr.open_group(str(copied), mode="a")
    record: dict[str, Any] = dict(group.attrs["early_abort"])  # type: ignore[arg-type]
    rates: list[dict[str, Any]] = [dict(r) for r in record["rates"]]
    tampered = int(rates[1]["failed"]) + 1
    rates[1]["failed"] = tampered
    record["rates"] = rates
    group.attrs["early_abort"] = record

    section = describe(read_store(copied))
    (row,) = section.dropped_rows

    assert row.provenance == RECOMPUTED
    assert row.defects, "a tampered record was reported as agreeing"
    assert any(
        f"failed={tampered}" in defect and "pass 1's arrays say" in defect
        for defect in row.defects
    )


def test_a_no_evidence_store_prints_as_itself_and_not_as_a_clean_pass(
    tmp_path, monkeypatch
):
    """A run that continued with its sample unjudged says so.

    Expected value determined independently: section 14.1's `no_evidence`
    action exists because "no candidate had a fit verdict anywhere in the
    coarse sample" and "every candidate passed" are opposite facts. The
    section must therefore expose the action, not a boolean "was anything
    dropped".

    Bug this catches: the collapse 2e's no-evidence decision was taken to
    prevent, reintroduced at the printing layer -- `no_evidence` has no
    dropped candidates, so a section that reports only rows would print it
    identically to a clean pass.
    """
    config = _config(tmp_path, _input(tmp_path))

    def _no_evidence(path: pathlib.Path | str, **kwargs: Any) -> Any:
        real = abort_verdict(path, **kwargs)
        return replace(
            real, action="no_evidence", candidates=(), reason="forced no evidence"
        )

    monkeypatch.setattr(twopass, "abort_verdict", _no_evidence)
    report = run_two_pass(
        config,
        tmp_path / "out.zarr",
        candidate_failure_policy=CandidateFailurePolicy.DROP,
    )

    section = describe(read_store(pathlib.Path(report.store_path)))

    assert section.evaluated is True
    assert section.is_no_evidence is True
    assert section.dropped_rows == ()
    assert _early_abort(pathlib.Path(report.store_path))["action"] == "no_evidence"


def test_a_store_with_no_verdict_prints_its_reason_and_no_drop_row(tmp_path):
    """ "The question was never asked" is not "nobody was dropped".

    Expected value determined independently: `_verdict_attrs` writes
    `{"evaluated": False, "reason": "--no-early-abort"}` when no verdict was
    reached, and a one-pass run records the same shape with its own reason.

    Bug this catches: a report inventing a verdict a one-pass run cannot have
    reached, and -- the other direction -- an empty drop table, which reads as
    "the verdict ran and dropped nobody". Those are different facts and a
    reader cannot recover which from an empty table.
    """
    store = tmp_path / "out.zarr"
    zarr.open_group(str(store), mode="w").attrs["early_abort"] = {
        "evaluated": False,
        "reason": "--no-early-abort",
    }
    section = describe(_bare_view(store))

    assert section.evaluated is False
    assert section.action is None
    assert section.rows == ()
    assert section.dropped_rows == ()
    assert section.reason == "--no-early-abort"


def _bare_view(store: pathlib.Path) -> StoreView:
    """A view carrying only what the early-abort section reads.

    The no-verdict case is a property of the ATTRS alone -- no outcome array is
    consulted when no verdict was reached -- so building a whole two-pass run
    to assert it would be testing the run rather than the section. **This is
    the one case in this file that does not need two stores**, and it says so.
    """
    return StoreView(
        path=store,
        outcome=np.zeros((1, 1, 1), dtype=np.uint8),
        delta_ic=np.zeros((1, 1, 1, 1), dtype=np.float32),
        selected=np.zeros((1, 1, 1), dtype=np.int16),
        n_valid=np.zeros((1, 1), dtype=np.int16),
        iterations=np.zeros((1, 1, 1), dtype=np.uint16),
        model_labels=("only",),
        criterion_labels=("aic",),
        attrs=dict(zarr.open_group(str(store), mode="r").attrs),
        completion=Completion(complete=1, total=1),
        disagreements=(),
    )


#: Criterion 12's fixture, as the gate records it. **Transcribed from 2e's own
#: `test_criterion_12_...`, which asserts these exact numbers off two real
#: stores**: candidate 0 fails 12 of 12 fitted with 8 land points carrying no
#: fit verdict, so `eligible` is 20; candidate 1 fails 3 of 12.
CRITERION_12_RECORD: dict[str, Any] = {
    "evaluated": True,
    "population": "pass 1 coarse grid",
    "action": "drop",
    "dropped": ["white"],
    "above_threshold": ["white"],
    "threshold": 0.90,
    "policy": "drop",
    "reason": "criterion 12's fixture",
    "rates": [
        {"candidate": "white", "failed": 12, "eligible": 20, "fitted": 12, "rate": 1.0},
        {
            "candidate": "matern",
            "failed": 3,
            "eligible": 20,
            "fitted": 12,
            "rate": 0.25,
        },
    ],
}


def _planted(store: pathlib.Path, record: dict[str, Any]) -> StoreView:
    """A view carrying a planted early-abort record and nothing else.

    **THE ARITHMETIC IS WHAT IS UNDER TEST, AND IT IS THE REPORT'S.** The
    numbers here are the ones 2e's criterion-12 test measured off two real
    stores; what this file adds is what the REPORT does with them, which is a
    property of the attrs alone. `dropped_run` above is the real-store arm that
    ties the planted shape to what a run actually writes.
    """
    zarr.open_group(str(store), mode="w").attrs["early_abort"] = record
    return _bare_view(store)


def test_the_drop_row_shows_the_rate_the_gate_decided_on_not_the_wider_one(tmp_path):
    """12 failed of 12 fitted is 1.00, above a threshold of 0.90.

    Expected values computed by hand from the literal counts in
    `CRITERION_12_RECORD`: 12 / 12 = 1.0 on the gate's denominator, and
    12 / 20 = 0.6 on the eligible population. **The threshold is 0.90, so the
    two readings fall on OPPOSITE SIDES of it.**

    Bug this catches: the row showing **0.60 for a candidate dropped at
    0.90** -- a dropped candidate displayed below the threshold that dropped
    it, from which any reader concludes the gate is broken. Since `f4eb42f`
    the gate thresholds on `failed / fitted` (D2b), so a row over `eligible`
    shows a rate **the decision never used**. That is D2b's defect arriving on
    the one row whose whole job is to report that decision.

    **THE 8-POINT GAP IS STILL PRINTED, AS A COUNT.** `eligible` is a real
    statement about the coarse sample; it is simply not this rate's
    denominator.
    """
    section = describe(_planted(tmp_path / "out.zarr", CRITERION_12_RECORD))
    (row,) = section.dropped_rows

    assert row.rate == 12 / 12
    assert row.live == 12
    assert row.denominator == "fitted"
    assert row.rate is not None and row.rate > CRITERION_12_RECORD["threshold"]
    assert row.eligible == 20
    assert row.eligible - row.fitted == 8
    assert row.defects == ()


def test_a_kept_candidate_is_checked_too_and_shows_as_kept(tmp_path):
    """The consistency check covers every judged candidate, not just the dropped.

    Expected values computed by hand: candidate `matern` fails 3 of 12 fitted,
    so 3 / 12 = 0.25, which is at or below the threshold of 0.90 and is
    therefore kept -- and the store's `above_threshold` lists only `white`.

    Bug this catches: a check that runs only over `dropped`, which would be
    blind to a kept candidate whose displayed rate says it should have been
    dropped. **The row exists for every candidate the verdict judged**, which
    is what makes that check possible at all.

    **AND THE MISMATCH IS ONE-DIRECTIONAL, WHICH IS WHY THE DROPPED CASE IS
    THE DANGEROUS ONE.** `eligible >= fitted` always -- the nesting chain --
    so `failed / eligible <= failed / fitted`: a wrong denominator can only
    make a rate look SMALLER. A kept candidate stays below the threshold
    either way; a dropped one can be shown below it. The check covers both
    because "which direction can it fail in" is an argument, and an argument
    is not a test.
    """
    section = describe(_planted(tmp_path / "out.zarr", CRITERION_12_RECORD))
    kept = [row for row in section.rows if not row.dropped]

    assert [row.candidate for row in kept] == ["matern"]
    assert kept[0].rate == 3 / 12
    assert kept[0].rate is not None
    assert kept[0].rate <= CRITERION_12_RECORD["threshold"]
    assert kept[0].defects == ()


def test_a_row_that_does_not_reproduce_the_decision_is_reported_as_a_defect(tmp_path):
    """A displayed rate that contradicts the recorded decision is named.

    Expected value determined independently: the record is edited so `white`'s
    rate reads 0.10 while the store still records it as dropped and above a
    threshold of 0.90. 0.10 is not above 0.90, so the displayed rate cannot
    reproduce the decision, and the defect must name both facts.

    Bug this catches: a consistency check that exists on paper and never runs
    -- which is indistinguishable from a working one on every store where the
    record happens to be self-consistent, including all of ours. **This is the
    (a10) half**: the two tests above cannot tell a real comparison from a
    function that returns no defects.

    **REPORTED, NOT RESOLVED**, and not raised: D6's rule for the bitmap
    disagreement applies here too, and a report that quietly recomputed the
    number would destroy the only evidence that something is wrong.
    """
    record = {
        **CRITERION_12_RECORD,
        "rates": [{**CRITERION_12_RECORD["rates"][0], "rate": 0.10}],
    }
    section = describe(_planted(tmp_path / "out.zarr", record))
    (row,) = section.dropped_rows

    assert row.defects, "a row contradicting its own decision was reported as clean"
    assert any("does not reproduce the recorded decision" in d for d in row.defects)
    assert any("0.9" in d for d in row.defects)


def test_a_store_predating_the_fitted_field_is_read_on_its_own_denominator(tmp_path):
    """An older store's gate really did threshold on `eligible`.

    Expected value determined independently: before `49f3db1` the record
    carried no `fitted` field at all, and `eligible` is the only denominator
    any gate used before `f4eb42f`. So a record without `fitted` is read on
    `eligible` -- 19 / 20 = 0.95 here -- and that is CORRECT for that store.
    **The fixture is self-consistent on its own terms**: 0.95 is above the
    0.90 threshold, so the recorded drop is exactly what that gate would have
    done, and the consistency check passes for the right reason rather than
    because both sides happen to say "not above".

    Bug this catches: applying today's denominator to yesterday's record,
    which would misreport an old store exactly as reading `eligible` today
    misreports a new one. **The rule is the same in both directions: show the
    rate that corresponds to the recorded decision.**

    **THE AMBIGUITY THIS CANNOT RESOLVE IS STATED AT `gate_denominator`**: a
    store written between `49f3db1` and `f4eb42f` carries `fitted` and was
    decided on `eligible`, and field presence cannot separate those. The fix
    is a recorded denominator name, owed at Task 4's additive write.
    """
    record = {
        **CRITERION_12_RECORD,
        "rates": [
            {"candidate": "white", "failed": 19, "eligible": 20, "rate": 19 / 20}
        ],
    }
    section = describe(_planted(tmp_path / "out.zarr", record))
    (row,) = section.dropped_rows

    assert row.denominator == "eligible"
    assert row.live == 20
    assert row.rate == 19 / 20
    assert row.rate is not None and row.rate > CRITERION_12_RECORD["threshold"]
    assert row.defects == ()
