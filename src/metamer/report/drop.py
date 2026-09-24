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
    """One dropped candidate, with the population the decision was taken over.

    Attributes:
        candidate: The candidate the verdict demoted.
        failed: Failed fits in pass 1's coarse sample.
        live: **The denominator, and it is pass 1's** -- the points where this
            candidate was still live when the verdict was taken. Never pass
            2's, where the candidate is `CANDIDATE_DROPPED` everywhere and a
            rate reads ~100% because the decision already wrote it.
        fitted: Fit verdicts in the coarse sample, from the record.
        rate: The rate the verdict was decided on, or None where it had none.
        provenance: Whether the numbers were recomputed or are carried.
        defects: Contradictions found while checking, **reported and never
            resolved**. Empty when pass 1 agreed or was absent.
    """

    candidate: str
    failed: int
    live: int
    fitted: int
    rate: float | None
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
        rows: One row per dropped candidate, empty unless `action == "drop"`.
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


def _carried_rows(records: list[dict[str, Any]], dropped: set[str]) -> list[DropRow]:
    """The dropped candidates' rows, straight from the store's own record."""
    return [
        DropRow(
            candidate=str(record.get("candidate", "")),
            failed=int(record.get("failed", 0)),
            live=int(record.get("eligible", 0)),
            fitted=int(record.get("fitted", 0)),
            rate=None if record.get("rate") is None else float(record["rate"]),
            provenance=CARRIED,
            defects=(),
        )
        for record in records
        if str(record.get("candidate", "")) in dropped
    ]


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
    rows = _carried_rows(rates, dropped) if action == "drop" else []

    defects: list[str] = []
    pass1_path = pass1_store_path(view.path)
    if rows and pass1_path.exists():
        pass1 = read_store(pass1_path)
        rows = [
            DropRow(
                **{
                    **row.__dict__,
                    "provenance": RECOMPUTED,
                    "defects": _pass1_defects(pass1, row),
                }
            )
            for row in rows
        ]
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
