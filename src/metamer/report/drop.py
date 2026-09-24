"""Sub-phase 2f Task 3: the drop row, and what the early-abort verdict recorded.

**THE ROW REPORTS A DECISION THE RUN TOOK, AND A DECISION'S EVIDENCE IS WHAT
THE RUN SAW WHEN IT TOOK IT** (D11). Design doc section 14.2 reasons about a
candidate dropped mid-pass, with `CANDIDATE_DROPPED` written across every
*remaining* point; 2e implemented the drop **between** passes, so in the output
store the candidate is `CANDIDATE_DROPPED` at **100%** of points and "points
where the candidate was still live" is zero there. **A rate over pass 2 would
report the decision rather than the candidate**, which is why the denominator
is pass 1's and never pass 2's.

**CARRIED RECORD PRIMARY, RECOMPUTED WHEN THE EVIDENCE IS PRESENT.** The
threshold and the policy are command-line flags and exist nowhere but the
record; the rates are recomputable from pass 1's store, which is permanent. So
the record is read, and when `<store>.pass1.<ext>` is beside the store its
arrays are recomputed and compared. **A carried counter verified against the
store whenever the store is there.**

**NOTHING HERE REFUSES A STORE.** Disagreements are reported and never
resolved, exactly as the reader reports its own -- D6's rule is that an
incomplete or inconsistent store is *described*, and a report that raises on a
store someone else shipped is a report that cannot be run on it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from metamer.batch.decimate import pass1_store_path
from metamer.core.outcomes import Outcome, failure_tally
from metamer.report.reader import StoreView, read_store

#: Said when pass 1's store is not beside the output store.
CARRIED = "carried: pass 1's store is not present, so the record is unchecked"

#: Said when pass 1 was read and agreed with the record.
RECOMPUTED = "recomputed from pass 1 and agreed"


@dataclass(frozen=True)
class DropRow:
    """One candidate the verdict judged, over the population it judged it on.

    **THE DENOMINATOR PRINTED HERE IS THE ONE THE GATE USED, AND NOTHING
    ELSE.** D11: a decision's evidence is what the run saw when it made the
    decision. Since `f4eb42f` the gate thresholds on `failed / fitted` (D2b),
    so a row printing `failed / eligible` shows a rate the decision never used
    -- on criterion 12's own fixture that is **12/12 = 1.00 dropped at a
    threshold of 0.90, reported as 12/20 = 0.60**, a dropped candidate shown
    BELOW the threshold that dropped it. Any reader concludes the gate is
    broken. That is D2b's defect again, on the one row whose job is to report
    that decision.

    Attributes:
        candidate: The candidate the verdict judged.
        failed: Failed fits in pass 1's coarse sample.
        live: **The denominator the GATE used**, and the one `rate` is over.
            Pass 1's population either way -- never pass 2's, where the
            candidate is `CANDIDATE_DROPPED` everywhere and a rate reads ~100%
            because the decision already wrote it.
        denominator: Which population `live` counts, named at the row:
            `"fitted"` for a store written after the gate moved, `"eligible"`
            for an older one, whose gate really did threshold on that.
        eligible: The coverage population, **as a count and not as this rate's
            denominator**. Printed because the gap between it and `fitted` is
            a real statement about the coarse sample.
        fitted: Fit verdicts in the coarse sample, from the record.
        rate: The rate the verdict was decided on, or None where it had none.
        dropped: Whether this candidate is one the verdict demoted.
        provenance: Whether the numbers were recomputed or are carried.
        defects: Contradictions found while checking, **reported and never
            resolved**. Empty when everything agreed.
    """

    candidate: str
    failed: int
    live: int
    denominator: str
    eligible: int
    fitted: int
    rate: float | None
    dropped: bool
    provenance: str
    defects: tuple[str, ...]


@dataclass(frozen=True)
class EarlyAbortSection:
    """What the store records about the early-abort verdict.

    Attributes:
        evaluated: Whether a verdict was reached at all. **False for a
            one-pass run and for `--no-early-abort`**, which print their own
            line rather than an empty drop row: an empty table reads as "no
            candidate was dropped", and "the question was never asked" is a
            different statement.
        reason: The store's own reason string, whatever the case.
        action: `"continue"`, `"abort"`, `"drop"` or `"no_evidence"`, or None
            when no verdict was reached.
        rows: **One row per candidate the verdict judged**, dropped or not --
            each carrying `dropped`. The printed drop row is the dropped
            subset (`dropped_rows`); the kept rows are here because the
            consistency check must cover them, and a check that ran only on
            dropped candidates could not see a kept one shown a rate that says
            it should have been dropped.
        defects: Section-level contradictions, reported and never resolved.
    """

    evaluated: bool
    reason: str
    action: str | None
    rows: tuple[DropRow, ...]
    defects: tuple[str, ...]

    @property
    def is_no_evidence(self) -> bool:
        """Whether the run continued with its coarse sample unjudged.

        **PRINTED AS ITSELF AND NEVER FOLDED INTO A CLEAN PASS.** Section
        14.1's `no_evidence` verdict exists because "no candidate had a fit
        verdict anywhere in the coarse sample" and "every candidate passed"
        are opposite facts that a single "continue" would print alike.
        """
        return self.action == "no_evidence"

    @property
    def dropped_rows(self) -> tuple[DropRow, ...]:
        """The rows the report prints as the drop row."""
        return tuple(row for row in self.rows if row.dropped)


def gate_denominator(record: dict[str, Any]) -> str:
    """Which population the gate that wrote this store thresholded on.

    **THE STORE SHOULD SAY, AND UNTIL IT DOES THIS INFERS.** The `fitted`
    field arrived at `49f3db1` and the gate's denominator moved at `f4eb42f`,
    so **a store written between those two commits carries `fitted` and was
    decided on `eligible`** -- field presence cannot separate those two cases.
    The ambiguity is stated rather than hidden, and it is safe in practice
    because no committed store comes from that one-day window.

    **THE FIX IS A RECORDED NAME, OWED AT TASK 4's ADDITIVE WRITE**: the
    verdict writes its own denominator's name, exactly as it already writes
    the threshold and the policy -- facts that exist nowhere else in the
    store. When the name is present it is used and nothing is inferred.

    Args:
        record: The `early_abort` attrs.

    Returns:
        `"fitted"` or `"eligible"`.
    """
    named = record.get("denominator")
    if isinstance(named, str) and named:
        return named
    rates = record.get("rates", [])
    if rates and isinstance(rates[0], dict) and "fitted" in rates[0]:
        return "fitted"
    # No `fitted` anywhere: the store predates `49f3db1`, and `eligible` is
    # the only denominator any gate used before `f4eb42f`.
    return "eligible"


def _carried_rows(
    records: list[dict[str, Any]], dropped: set[str], denominator: str
) -> list[DropRow]:
    """One row per candidate the verdict judged, from the store's own record.

    **EVERY CANDIDATE, NOT ONLY THE DROPPED ONES.** The consistency check below
    asks whether the displayed rate reproduces the recorded decision, and a
    check that ran only on dropped candidates could not see a kept one being
    shown a rate that says it should have been dropped.
    """
    rows: list[DropRow] = []
    for record in records:
        candidate = str(record.get("candidate", ""))
        eligible = int(record.get("eligible", 0))
        fitted = int(record.get("fitted", eligible))
        rows.append(
            DropRow(
                candidate=candidate,
                failed=int(record.get("failed", 0)),
                live=fitted if denominator == "fitted" else eligible,
                denominator=denominator,
                eligible=eligible,
                fitted=fitted,
                rate=None if record.get("rate") is None else float(record["rate"]),
                dropped=candidate in dropped,
                provenance=CARRIED,
                defects=(),
            )
        )
    return rows


def _decision_defects(
    row: DropRow, *, threshold: float, above: set[str] | None
) -> tuple[str, ...]:
    """Does the rate this row displays reproduce the decision the store records?

    **THE GATE'S OWN COMPARISON, WHICH IS STRICT.** `abort._decide` drops a
    candidate when `rate > threshold`, and a candidate with no rate is never
    above it. Re-applying that comparison to the displayed rate and comparing
    against the recorded `above_threshold` is what makes the row's consistency
    a property of **someone else's store** rather than of our fixtures.

    **REPORTED, NEVER RESOLVED** -- D6's rule for the bitmap disagreement,
    applied here. A report that silently corrected the number would hide the
    only evidence that something is wrong.

    Args:
        row: The row as it will be displayed.
        threshold: The recorded threshold.
        above: The recorded `above_threshold` set, or None when the store does
            not carry one and the check cannot be made.

    Returns:
        The mismatch, or empty when the row reproduces the decision.
    """
    if above is None:
        return ()
    shown_above = row.rate is not None and row.rate > threshold
    recorded_above = row.candidate in above
    if shown_above == recorded_above:
        return ()
    verb = "above" if shown_above else "at or below"
    was = "was" if recorded_above else "was not"
    return (
        f"{row.candidate}: the row shows {row.rate} over {row.live} "
        f"{row.denominator}, which is {verb} the threshold of {threshold}, "
        f"but the store records that this candidate {was} above it -- the "
        "displayed rate does not reproduce the recorded decision",
    )


def _pass1_defects(pass1: StoreView, row: DropRow) -> tuple[str, ...]:
    """Compare one carried row against pass 1's arrays.

    **AND CHECK THE PREMISE THAT MAKES THE CARRIED DENOMINATOR SAFE.** The
    record carries `eligible` and predates `Outcome.is_covered`, so the drop
    row's denominator counts `NOT_ATTEMPTED` -- harmless only while pass 1
    holds none, which is true of a FINISHED pass 1 and is the premise nobody
    wrote down. A verdict is only reached after pass 1 completes, so the
    premise should hold; **if it ever does not, the denominator is diluted and
    this says so** rather than reading low.

    Args:
        pass1: Pass 1's store, read back.
        row: The carried row for this candidate.

    Returns:
        Every disagreement found, empty when the record and the arrays agree.
    """
    if row.candidate not in pass1.model_labels:
        return (
            f"{row.candidate}: the verdict names a candidate pass 1's store "
            f"does not carry ({', '.join(pass1.model_labels)})",
        )
    index = pass1.model_labels.index(row.candidate)
    plane = pass1.outcome[..., index]
    counted: dict[Outcome, int] = {}
    for member in Outcome:
        found = int((plane == member.code).sum())
        if found:
            counted[member] = found
    tally = failure_tally(counted)

    defects: list[str] = []
    for name, carried, recomputed in (
        ("failed", row.failed, tally.failed),
        ("eligible", row.live, tally.eligible),
        ("fitted", row.fitted, tally.fitted),
    ):
        if carried != recomputed:
            defects.append(
                f"{row.candidate}: the record says {name}={carried} and pass "
                f"1's arrays say {recomputed}"
            )
    if tally.covered != tally.eligible:
        defects.append(
            f"{row.candidate}: pass 1 holds {tally.eligible - tally.covered} "
            "points the run never reached, so the carried `eligible` "
            "denominator is diluted by them -- the drop rate reads LOW"
        )
    return tuple(defects)


def describe(view: StoreView) -> EarlyAbortSection:
    """The early-abort section, from the store and its pass-1 sibling.

    Args:
        view: The output store, read-only.

    Returns:
        What the run recorded, with each dropped candidate's row over pass 1's
        population.
    """
    record = view.attrs.get("early_abort")
    if not isinstance(record, dict):
        return EarlyAbortSection(
            evaluated=False,
            reason="this store carries no early-abort record",
            action=None,
            rows=(),
            defects=(),
        )
    if not record.get("evaluated"):
        return EarlyAbortSection(
            evaluated=False,
            reason=str(record.get("reason", "no verdict was reached")),
            action=None,
            rows=(),
            defects=(),
        )

    action = str(record.get("action", ""))
    rates = [r for r in record.get("rates", []) if isinstance(r, dict)]
    dropped = {str(name) for name in record.get("dropped", [])}
    denominator = gate_denominator(record)
    rows = _carried_rows(rates, dropped, denominator)

    threshold = float(record.get("threshold", 0.0))
    listed = record.get("above_threshold")
    above = {str(name) for name in listed} if isinstance(listed, list) else None

    defects: list[str] = []
    pass1_path = pass1_store_path(view.path)
    pass1 = read_store(pass1_path) if rows and pass1_path.exists() else None
    rows = [
        DropRow(
            **{
                **row.__dict__,
                "provenance": CARRIED if pass1 is None else RECOMPUTED,
                "defects": (() if pass1 is None else _pass1_defects(pass1, row))
                + _decision_defects(row, threshold=threshold, above=above),
            }
        )
        for row in rows
    ]
    if above is None and rates:
        defects.append(
            "this store records no `above_threshold`, so the rows cannot be "
            "checked against the decision they report"
        )
    missing = dropped - {row.candidate for row in rows}
    if missing:
        defects.append(
            "the verdict dropped "
            + ", ".join(sorted(missing))
            + " and the record carries no rate for "
            + ("it" if len(missing) == 1 else "them")
        )
    return EarlyAbortSection(
        evaluated=True,
        reason=str(record.get("reason", "")),
        action=action,
        rows=tuple(rows),
        defects=tuple(defects),
    )
