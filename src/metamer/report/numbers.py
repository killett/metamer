"""Sub-phase 2f Task 2: counts and rates, per branch and per candidate.

**EVERY RATE CARRIES ITS OWN DENOMINATOR, AND WHERE THE DENOMINATOR IS
CONTESTED BOTH ARE PRINTED.** Design doc section 14.2's failure rate has two
defensible populations -- the points that carried a fit verdict, and the
points the run reached inside the domain -- and choosing one silently is how a
rate becomes uninterpretable. So this module reports both, side by side, and
**the gap between them is the store's own exposure**: on a box with no land
and a finished run they are identical, and the reader learns that the exposure
is nil rather than learning nothing.

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

import numpy as np
from numpy.typing import NDArray

from metamer.core.outcomes import FailureTally, Outcome, failure_tally
from metamer.report.reader import StoreView

#: Said beside the coverage rate when the store declares no domain mask.
#: **Present by default, because every store in existence lacks the field**
#: until design doc section 13.6's mask lands: a caveat that has to be switched
#: on is one nobody switches on.
NO_DOMAIN_MASK_CAVEAT = (
    "this store declares no domain mask, so out-of-domain points are "
    "distinguishable from unreached ones only where the run wrote "
    "NOT_APPLICABLE; the coverage denominator is a lower bound on the domain"
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
        caveat=None if "domain_mask" in view.attrs else NO_DOMAIN_MASK_CAVEAT,
    )
