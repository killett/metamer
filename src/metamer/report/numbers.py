"""Sub-phase 2f Task 2: counts and rates, per branch and per candidate.

**EVERY RATE CARRIES ITS OWN DENOMINATOR, AND WHERE THE DENOMINATOR IS
CONTESTED BOTH ARE PRINTED.** Design doc section 14.2's failure rate has two
defensible populations -- the points that carried a fit verdict, and the
points the run reached inside the domain -- and choosing one silently is how a
rate becomes uninterpretable. So this module reports both, side by side, with
**the gap between them broken down BY MEMBER**.

**~~"The gap is the store's land exposure"~~ -- STRUCK 2026-09-23, AND IT WAS
WRITTEN HERE TWO DAYS AFTER THE SAME DEFECT WAS FOUND IN THE PLAN.** True land
is `NOT_APPLICABLE` and sits outside BOTH denominators, so it cannot separate
them at all; the reading looked right only because land reaches the covered
population as `INSUFFICIENT_DATA` until design doc section 13.6 declares a
mask. **That is a claim about what a label currently CONTAINS wearing the
clothes of a claim about what it MEANS** -- the conflation D2's reframing
exists to undo.

**Stated correctly, the gap is `covered - fitted`, and it is three populations
with three causes**: a record too thin to fit, a decision not to fit, and an
early-abort verdict. `failure_tally` returns the breakdown by member and this
module prints it, because a single figure invites the gloss and a gloss is how
a stray `SCREENED_OUT` gets debugged as a land bug.

**THIS MODULE COMPUTES NO RATE.** Every division lives at
`metamer.core.outcomes.failure_tally`, which is the project's one definition of
the quantity. A rate computed at its consumer is a second definition of it, and
this project has already paid for that once: section 14.1's verdict and the
live counters each had their own arithmetic and disagreed for four days over
the same data, because a search finds call sites of a function and not
computations of a quantity.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

from metamer.core.outcomes import FailureTally, Outcome, failure_tally
from metamer.report.reader import StoreView

#: Said when the run recorded that it applied NO declared domain mask.
#: **Present by default, because every run lacks a mask** until design doc
#: section 13.6's lands: a caveat that has to be switched on is one nobody
#: switches on.
NO_DOMAIN_MASK_CAVEAT = (
    "the run that wrote this store applied no declared domain mask, so "
    "out-of-domain points are distinguishable from unreached ones only where "
    "it wrote NOT_APPLICABLE; the coverage denominator is a lower bound on "
    "the domain"
)

#: Said when the store does not record the question either way.
#: **NOT THE SAME SENTENCE AS THE ONE ABOVE, AND THE DIFFERENCE IS THE POINT.**
#: "The run declared no mask" is a fact about the run; "this store does not say"
#: is a fact about the record, and only the second can be resolved by a newer
#: writer. Collapsing them would make a store written before Task 4 claim
#: something its writer never decided -- the back-fill D12 refuses, arriving
#: through a caveat instead of through an attr.
UNRECORDED_DOMAIN_MASK_CAVEAT = (
    "the run that wrote this store did not record whether it applied a "
    "declared domain mask, so the coverage denominator is a lower bound on "
    "the domain and no newer reading can settle it for this store"
)


@dataclass(frozen=True)
class CandidateNumbers:
    """One candidate's census and its two rates.

    Attributes:
        candidate: The model label, as the store's `m` axis carries it.
        tally: Counts and both rates, from the one definition.
        by_branch: This candidate's census, every branch present.
    """

    candidate: str
    tally: FailureTally
    by_branch: dict[Outcome, int]


@dataclass(frozen=True)
class ReportNumbers:
    """Task 2's record: the branch table, the per-candidate rows, and both rates.

    Attributes:
        by_branch: The whole store's census, keyed by taxonomy branch.
            **`branch` means an `Outcome` member**, as `progress.py`'s
            `by_branch` and section 14.1 already fix it -- never a candidate.
        by_candidate: One row per model label, in the store's own axis order.
        aggregate: The census over every candidate at once. **A second headline
            of a different kind** (D7), not a summary of the rows: a point
            failing under one candidate and fitting under another is one cell
            in each row and two cells here.
        complete: Tiles written, from the completion bitmap.
        total: Tiles in the bitmap. **`complete of total` is rendered beside
            every denominator** (D6) -- a rate quoted without its population is
            what a reader carries away.
        caveat: Why the coverage denominator is approximate, or None when the
            store declares a domain mask.
    """

    by_branch: dict[Outcome, int]
    by_candidate: tuple[CandidateNumbers, ...]
    aggregate: FailureTally
    complete: int
    total: int
    caveat: str | None


def _census(codes: NDArray[np.uint8]) -> dict[Outcome, int]:
    """Count outcome codes into a branch census.

    **EVERY BRANCH PRESENT APPEARS, INCLUDING THE ONES OUTSIDE EVERY
    DENOMINATOR.** `NOT_ATTEMPTED` is counted here and divided by nowhere:
    dropping it from the table would make an interrupted run's report describe
    a smaller grid than the one that ran, which is the opposite of what an
    unfinished store needs to say about itself.

    Args:
        codes: Raw outcome codes, any shape.

    Returns:
        Counts keyed by member, ordered as the taxonomy declares them.
    """
    counted = Counter(np.asarray(codes, dtype=np.uint8).ravel().tolist())
    return {member: counted[member.code] for member in Outcome if counted[member.code]}


def _domain_mask_caveat(attrs: dict[str, Any]) -> str | None:
    """Whether the coverage denominator is caveated, and why.

    **THE VALUE IS THE SUBJECT, NOT THE KEY.** Deciding on `"domain_mask" in
    attrs` agrees with the truth on every store that exists today -- because no
    store carries the field at all -- and stops agreeing the moment Task 4
    writes it, which it does as `false` for every run until section 13.6
    lands. **The caveat would drop on the day the field arrived**, and the
    report would claim an exactness it does not have, through the field added
    to give it one. Three states, three answers.

    **ONLY `True` DROPS IT.** Not a truthy string, not a number: the field is a
    boolean by the plan's own wording, so anything else is a store saying
    something this report does not understand, and the conservative reading is
    the caveat.

    Args:
        attrs: The store's root attrs.

    Returns:
        The caveat, or None when a mask was declared.
    """
    if "domain_mask" not in attrs:
        return UNRECORDED_DOMAIN_MASK_CAVEAT
    return None if attrs["domain_mask"] is True else NO_DOMAIN_MASK_CAVEAT


def compute(view: StoreView) -> ReportNumbers:
    """Task 2's numbers, from a store the report never writes to.

    Args:
        view: A store, read-only.

    Returns:
        The branch table, one row per candidate with both rates, and the
        aggregate -- each rate's denominator beside it.
    """
    by_branch = _census(view.outcome)
    per_candidate = [
        (label, _census(view.outcome[..., index]))
        for index, label in enumerate(view.model_labels)
    ]
    rows = tuple(
        CandidateNumbers(
            candidate=label,
            tally=failure_tally(census),
            # **THE SAME CENSUS OBJECT THE TALLY WAS TAKEN FROM**, not a second
            # walk of the same plane. Two walks are two chances to disagree,
            # and a row whose table and whose rate describe different censuses
            # is the two-definitions defect at the granularity of one row.
            by_branch=census,
        )
        for label, census in per_candidate
    )
    return ReportNumbers(
        by_branch=by_branch,
        by_candidate=rows,
        aggregate=failure_tally(by_branch),
        complete=view.completion.complete,
        total=view.completion.total,
        caveat=_domain_mask_caveat(view.attrs),
    )
