"""Sub-phase 2f Task 5: selectability, the section design doc section 14.2 leads with.

**THIS SECTION LEADS THE REPORT**, per section 14.2's 2026-09-12 amendment: the
real-data spike measured section 11.2's hysteresis fear **absent** -- zero
re-ranked points in 289, positive-controlled -- and measured selectability
differences **present**. A report leading with hysteresis would lead with the
thing this project has measured as not happening.

**THREE QUANTITIES, THREE FACTS, AND THE WORD "FITS" APPEARS NOWHERE.** It is
already spoken for: Task 2's per-candidate table prints `fitted`, meaning
`Outcome.is_fit_verdict` -- OK **plus the eight failure codes**. `n_valid` is
`count(outcome == OK)`, strictly smaller wherever anything failed. Printing both
under one word would put two quantities behind one name in a single document,
which is this project's signature defect. So `n_valid` is **converged** here,
and the relationship to Task 2's column is an identity this module checks rather
than a sentence it asserts:

    converged == fitted - failed        (per point, exactly)

**AND THE THREE NEST**, each inclusion strict for its own reason:

    rankable (contention) ⊆ converged (OK) ⊆ fitted (fit verdict)

`rankable ⊂ converged` when a fit succeeds and its criterion value is not finite
-- section 12.5's construction, AICc at `n <= k + 1` -- which is why one point
can be contended under AIC and not under HQIC. `converged ⊂ fitted` when a
candidate produced a fit verdict that failed. **So `converged == 1` is not "the
selection was forced"**, and this module never says it is.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from metamer.batch.store import N_VALID_UNSET, SELECTED_UNSET
from metamer.core.outcomes import Outcome
from metamer.report.reader import StoreView

#: Said beside every contention count. **The store cannot tell a genuine
#: unrankable from a float32 overflow**, because `/selection/delta_ic` is
#: float32 and the ranker computes in float64: a delta finite in float64 and
#: larger than ~3.4e38 becomes `inf` on write, with a `RuntimeWarning` and no
#: error. Both read as `inf` afterwards. **Whether real data reaches that
#: magnitude is NOT established** -- section 14.2 calls this worth a caveat and
#: a test rather than a schema change, and the caveat says which part is
#: measured and which is not.
FLOAT32_CAVEAT = (
    "an infinite delta-IC is counted unrankable, and this store cannot "
    "distinguish a genuine one (AICc where n <= k + 1) from a float64 value "
    "that overflowed float32 on write; whether real data reaches that "
    "magnitude has not been established"
)


@dataclass(frozen=True)
class CriterionSelectability:
    """One criterion's view of how contended the selection was.

    Attributes:
        criterion: The criterion's label, as the store's `c` axis carries it.
        contention: How many points had each count of **rankable** candidates.
            Rankable is narrower than converged, per criterion.
        no_winner: Points where the criterion could rank nothing --
            `selected == -1`.
        unwritten: Points where **nothing wrote** -- `selected == -2`. **Never
            counted as a no-winner**: an interrupted run is full of these, and
            reporting them as selection failures would describe an absence of
            information as a result.
        unrankable_infinite: Fit verdicts whose delta-IC is infinite. **Split
            out from the not-scored count** because the two have different
            causes and only this one carries the float32 caveat.
        unrankable_not_scored: Cells with no delta-IC at all, which is what a
            candidate that did not converge leaves behind.
    """

    criterion: str
    contention: dict[int, int]
    no_winner: int
    unwritten: int
    unrankable_infinite: int
    unrankable_not_scored: int


@dataclass(frozen=True)
class Selectability:
    """Task 5's record: how much choice the selection actually had.

    Attributes:
        converged: How many in-domain points had each count of converged
            candidates -- `/selection/n_valid`, criterion-independent by
            construction and by a check in the writer. **Called converged and
            not "fits"**; see the module docstring.
        unset: In-domain points whose `n_valid` was never written.
        in_domain: The denominator. Points where **any** candidate is something
            other than `NOT_APPLICABLE` -- a point out of domain for every
            candidate is not a point a selection statement is about.
        out_of_domain: Points excluded from that denominator, reported so the
            excluded population is visible rather than implied.
        by_criterion: One entry per criterion, in the store's own axis order.
        caveat: Why an infinite delta-IC is ambiguous.
        defects: Contradictions found while checking, **reported and never
            resolved** -- D6's rule, as the reader and the drop row already
            follow it.
    """

    converged: dict[int, int]
    unset: int
    in_domain: int
    out_of_domain: int
    by_criterion: tuple[CriterionSelectability, ...]
    caveat: str
    defects: tuple[str, ...]


def _counts(values: NDArray[np.int64]) -> dict[int, int]:
    """Bin a small integer array into a plain dict, ordered by value."""
    counted = Counter(int(v) for v in values.ravel().tolist())
    return {value: counted[value] for value in sorted(counted)}


def _identity_defects(view: StoreView, in_domain: NDArray[np.bool_]) -> tuple[str, ...]:
    """Check `converged == fitted - failed` at every in-domain point.

    **THE TWO SECTIONS ARE BOUND BY ARITHMETIC, NOT BY PROSE.**
    `Outcome.is_fit_verdict` partitions exactly into `OK` and the eight failure
    codes -- Task 2's nesting chain read at one point instead of over the enum
    -- so `n_valid` and Task 2's per-point counts are related by an identity.
    If either side ever drifts, **this says so at the point where they
    disagree** rather than leaving two plausible numbers in one report.

    Args:
        view: The store.
        in_domain: Which points the denominator covers.

    Returns:
        Up to one defect, naming the first point that disagrees and by how
        much. **Reported, never raised**: a store with a contradiction is
        described (D6).
    """
    codes = np.asarray(view.outcome, dtype=np.uint8)
    fitted = np.zeros(codes.shape[:-1], dtype=np.int64)
    failed = np.zeros(codes.shape[:-1], dtype=np.int64)
    for member in Outcome:
        if not member.is_fit_verdict:
            continue
        present = (codes == member.code).sum(axis=-1)
        fitted += present
        if member.is_failure:
            failed += present

    written = np.asarray(view.n_valid, dtype=np.int64) != N_VALID_UNSET
    subject = in_domain & written
    disagrees = subject & (np.asarray(view.n_valid, dtype=np.int64) != fitted - failed)
    if not bool(disagrees.any()):
        return ()
    first = tuple(int(axis[0]) for axis in np.nonzero(disagrees))
    y, x = first[0], first[1]
    return (
        f"at point {first}: n_valid is {int(view.n_valid[y, x])} and the "
        f"outcome array gives fitted - failed = {int(fitted[y, x] - failed[y, x])}; "
        "the selectability section and the per-candidate table are describing "
        "different runs",
    )


def compute(view: StoreView) -> Selectability:
    """Task 5's section, from stored arrays with no schema change.

    Args:
        view: A store, read-only.

    Returns:
        The three quantities, each over a stated denominator.
    """
    codes = np.asarray(view.outcome, dtype=np.uint8)
    in_domain = ~(codes == Outcome.NOT_APPLICABLE.code).all(axis=-1)

    n_valid = np.asarray(view.n_valid, dtype=np.int64)
    written = in_domain & (n_valid != N_VALID_UNSET)

    rows: list[CriterionSelectability] = []
    for index, label in enumerate(view.criterion_labels):
        delta = np.asarray(view.delta_ic[..., index], dtype=np.float64)
        finite = np.isfinite(delta)
        selected = np.asarray(view.selected[..., index], dtype=np.int64)
        rows.append(
            CriterionSelectability(
                criterion=label,
                contention=_counts(finite.sum(axis=-1)[in_domain]),
                # **`== -1`, NOT `< 0` AND NOT A TRUTHINESS TEST.** `-2` is
                # SELECTED_UNSET and `bool(-1) == bool(-2) == True`, so either
                # shortcut would report an interrupted run's unwritten cells as
                # selection failures -- an absence of information printed as a
                # result.
                no_winner=int((selected[in_domain] == -1).sum()),
                unwritten=int((selected[in_domain] == SELECTED_UNSET).sum()),
                unrankable_infinite=int(np.isinf(delta[in_domain]).sum()),
                unrankable_not_scored=int(np.isnan(delta[in_domain]).sum()),
            )
        )

    return Selectability(
        converged=_counts(n_valid[written]),
        unset=int((in_domain & ~written).sum()),
        in_domain=int(in_domain.sum()),
        out_of_domain=int((~in_domain).sum()),
        by_criterion=tuple(rows),
        caveat=FLOAT32_CAVEAT,
        defects=_identity_defects(view, in_domain),
    )
