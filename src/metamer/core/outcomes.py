"""The failure taxonomy.

Non-convergence is not one outcome. At 10^7 series nobody inspects individual
fits, so the map of *which* failure occurred *where* is itself the diagnostic.
This is an enum written to the output, never a boolean `converged` flag.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

import numpy as np
from numpy.typing import NDArray


class Outcome(StrEnum):
    """Per (point, candidate) fit outcome.

    **THE FOUR PREDICATES, IN ONE TABLE, ORDERED NARROWEST TO WIDEST.** They
    are four distinct questions, and this project's recurring defect is asking
    one of them and reading the answer as another -- section 14.1's abort gate
    asked "eligible" while meaning "fitted", and the live counters divided by
    points touched while the label said fits. **Reading them side by side is
    the only way to see that no two are the same set.**

    | member | `is_failure` | `is_fit_verdict` | `is_covered` | `is_eligible` |
    |---|---|---|---|---|
    | `OK` | no | yes | yes | yes |
    | `ITER_CAP_SMALL_GRAD` | yes | yes | yes | yes |
    | `ITER_CAP_LARGE_GRAD` | yes | yes | yes | yes |
    | `DIAGNOSTIC_LIMIT` | yes | yes | yes | yes |
    | `TRUST_RADIUS_COLLAPSED` | yes | yes | yes | yes |
    | `NONFINITE_OBJECTIVE` | yes | yes | yes | yes |
    | `RANK_DEFICIENT_X` | yes | yes | yes | yes |
    | `DEGENERATE_HESSIAN` | yes | yes | yes | yes |
    | `ILL_CONDITIONED_X` | yes | yes | yes | yes |
    | `NOT_ATTEMPTED` | no | no | no | yes |
    | `CANDIDATE_DROPPED` | no | no | yes | yes |
    | `INSUFFICIENT_DATA` | no | no | yes | yes |
    | `SCREENED_OUT` | no | no | yes | yes |
    | `NOT_APPLICABLE` | no | no | no | no |

    **THE COLUMNS NEST, LEFT TO RIGHT**: once a row says `yes` it says `yes`
    for the rest of that row. That is not a coincidence of the current members
    -- it is the invariant
    `is_failure` < `is_fit_verdict` < `is_covered` < `is_eligible`, asserted
    over the whole enum with each step proved PROPER by a named witness. Three
    rows carry the three witnesses: `OK` separates the first pair,
    `SCREENED_OUT` the second, `NOT_ATTEMPTED` the third.

    **THIS TABLE IS LOAD-BEARING, NOT DECORATIVE.** `tests/test_outcomes.py`
    parses it out of this docstring and asserts it against the four properties,
    so a member reclassified in code and not here fails the suite. It is the
    only place all four can be seen at once, which is why it lives in the
    module rather than in a test.

    **THE QUESTIONS, ONE LINE EACH:** `is_failure` -- did a fit run and come
    out bad? `is_fit_verdict` -- is the store making a claim about a fit here?
    `is_covered` -- is this point in the domain AND did the run reach it?
    `is_eligible` -- is this location one a rate is over at all?
    """

    OK = "ok"
    ITER_CAP_SMALL_GRAD = "iter_cap_small_grad"
    ITER_CAP_LARGE_GRAD = "iter_cap_large_grad"
    DIAGNOSTIC_LIMIT = "diagnostic_limit"
    TRUST_RADIUS_COLLAPSED = "trust_radius_collapsed"
    NONFINITE_OBJECTIVE = "nonfinite_objective"
    RANK_DEFICIENT_X = "rank_deficient_x"
    DEGENERATE_HESSIAN = "degenerate_hessian"
    ILL_CONDITIONED_X = "ill_conditioned_x"
    NOT_ATTEMPTED = "not_attempted"
    CANDIDATE_DROPPED = "candidate_dropped"
    INSUFFICIENT_DATA = "insufficient_data"
    SCREENED_OUT = "screened_out"
    NOT_APPLICABLE = "not_applicable"

    @property
    def is_eligible(self) -> bool:
        """Whether this LOCATION is one a rate is over at all.

        **NOT THE COVERAGE DENOMINATOR -- THAT IS `is_covered`, AND THE TWO
        DIFFER BY `NOT_ATTEMPTED`.** This predicate answers a question about
        the DOMAIN and says nothing about whether the run got there, so a rate
        over it improves the earlier an interrupted run was killed. Sub-phase
        2f Task 2 added the second predicate rather than narrowing this one:
        **these values are recorded in committed artifacts** (`abort`'s verdict
        record, `twopass`'s summary) and `audit_report.attempted` reads it under
        open question 25, so redefining it would move numbers already written.

        **SECTION 12.5's NON-FIT GROUPING TABLE IS THE CLASSIFICATION**, by its
        own declaration -- *"the grouping is what section 14.2's denominator
        reads"*. Only `NOT_APPLICABLE` leaves the denominator: **this location**
        is out of domain, land or permanent ice, and is not a point the rate is
        over.

        **`INSUFFICIENT_DATA` IS ELIGIBLE, CORRECTED 2026-09-20 (open question
        24).** ~~Section 8.6 called it "a legitimate expected outcome -- land,
        permanent ice" and excluded it from every denominator.~~ That row
        conflated two different facts and section 12.5 was written to undo the
        conflation: land and permanent ice are `NOT_APPLICABLE`, while **this
        series** having too thin a record is `INSUFFICIENT_DATA`, which section
        12.5 calls **eligible** because *"its rate is a real statement about
        record coverage"*. Collapsing them makes the failure rate
        uninterpretable, which is the failure section 14.2 exists to prevent.

        **THE DIRECTION OF THE CHANGE, BECAUSE SECTION 8.6's FEAR WAS THE
        OPPOSITE ONE.** That section worried an ocean-only run on a global grid
        would report ~70% "failure". **This cannot cause that**:
        `INSUFFICIENT_DATA` is not a failure, so it enters the denominator and
        never the numerator, and every failure rate it touches can only fall.
        The ~70% scenario needs land counted as FAILED, which is
        `RANK_DEFICIENT_X` -- the defect `OUTCOME_PRECEDENCE` exists to prevent
        and which `tests/test_objective.py` pins.

        **IT WAS CHECKED BEFORE IT WAS TAKEN, NOT AFTER.** Sixteen outcome
        histograms across five committed artifacts carry neither this member nor
        `NOT_APPLICABLE`, and the one committed family whose denominator reaches
        this property has `attempted == audited_points` on every candidate. No
        committed number moves. See
        `tests/test_outcomes.py::test_no_committed_artifact_carries_insufficient_data`,
        which is that check as an executable invariant rather than a dated claim.
        """
        return self is not Outcome.NOT_APPLICABLE

    @property
    def is_failure(self) -> bool:
        """Whether this outcome counts as a failure.

        Every member not excluded below is a failure, including
        ITER_CAP_SMALL_GRAD: design doc section 8.6 describes hitting the
        iteration cap with a small gradient as "probably fine, flagged" --
        flagged, not excluded. Excluding it here would make a real (if mild)
        non-convergence invisible in the spatial failure map, which at 10^7
        series is the diagnostic that matters.

        **THE DECIDED-SKIP GROUP IS SPECIFIED AT DESIGN DOC SECTION 12.5 AND IS
        NOT RE-ARGUED HERE.** That section's non-fit grouping table carries the
        rule -- *"the grouping is what section 14.2's denominator reads"* -- and
        classifies `SCREENED_OUT` and `CANDIDATE_DROPPED` identically, as
        **legitimate non-fits**. A code the run assigns *because the run chose
        not to fit* is eligible and is not a failure. **A future member is
        classified by that rule, at that section**; three statements of one rule
        is how a count in this project reached twelve sites.

        **`CANDIDATE_DROPPED` JOINED THE GROUP AT 2e's ~~TASK 1 GROUPING
        PASS~~ TASK 3 (2026-09-14; the task number corrected 2026-09-16), AND THAT
        WAS A CORRECTION RATHER THAN A DECISION.** It sat in the failure set from
        2a while section 12.5 said otherwise, and **nothing caught the
        disagreement because the member had no producer** -- 2e's Task 6 early
        abort is its first, as of 2026-09-16. A classification that has never been
        exercised has never been checked. The argument was also already in the
        suite, at the sibling: `SCREENED_OUT`'s test says counting a decided skip
        as a failure "would make a *cheaper* configuration report a worse failure
        rate", which is true of a dropped candidate word for word.

        **The consequence that makes it matter** is that the early abort drops a
        candidate *because* it failed, then writes `CANDIDATE_DROPPED` at every
        remaining point -- so a rate computed over those points would report the
        decision rather than the candidate, and would read louder than the
        evidence that triggered it. See the handoff's (j7b).

        ~~**`INSUFFICIENT_DATA`'s exclusion follows section 8.6, which section
        12.5 contradicts** -- open question 24, filed to 2f.~~ **CLOSED
        2026-09-20:** it is eligible, and its exclusion from `is_failure` is
        unchanged and was never in question. See `is_eligible`.
        """
        return self not in {
            Outcome.OK,
            Outcome.NOT_ATTEMPTED,
            Outcome.INSUFFICIENT_DATA,
            Outcome.SCREENED_OUT,
            Outcome.CANDIDATE_DROPPED,
            Outcome.NOT_APPLICABLE,
        }

    @property
    def is_fit_verdict(self) -> bool:
        """Whether the store is making a claim about a FIT at this cell.

        **SECTION 12.5's NON-FIT GROUPING TABLE IS THE CLASSIFICATION AND IS
        NOT RE-ARGUED HERE**, exactly as `is_failure` reads it. That table --
        *"the store's status alphabet carries codes that are **not fit
        verdicts**"* -- names five: `NOT_ATTEMPTED`, `SCREENED_OUT`,
        `CANDIDATE_DROPPED`, `NOT_APPLICABLE` and `INSUFFICIENT_DATA`. The nine
        members below are section 8.6's taxonomy, which is everything else.

        **WRITTEN AS A POSITIVE MEMBERSHIP TEST, WHICH IS THE OPPOSITE
        DIRECTION FROM ITS TWO SIBLINGS, DELIBERATELY.** `is_failure` and
        `is_eligible` exclude from the whole enum, so a new member defaults
        *into* them. Here that default is the dangerous one: every member added
        to this taxonomy since Phase 1 has been a non-fit code, and a new
        non-fit member defaulting into the fit set would silently become
        evidence -- a sample a run never fitted would read as judged. So an
        unknown member is **not** a fit verdict until someone says otherwise,
        and `tests/test_outcomes.py`'s one-table test is what makes "otherwise"
        a decision rather than an omission.

        **WHY THIS EXISTS, AND IT IS NOT A CONVENIENCE (2026-09-19, open
        question 24's artifact check).** Section 14.1's early-abort verdict
        asks *"did this sample hold any evidence?"* and was asking
        `is_eligible` -- *"is this point in a failure-rate denominator?"*.
        Those are different questions that agree only while
        `INSUFFICIENT_DATA` is excluded from denominators, which is section
        8.6's reading and which section 12.5 supersedes. `SCREENED_OUT` and
        `CANDIDATE_DROPPED` are eligible and are not fits, so the disagreement
        is constructible today and becomes reachable the moment open question
        24 lands.

        **THE PATTERN, RECORDED HERE RATHER THAN AS A THIRD ANECDOTE.** This is
        one of five instruments in this project caught keying on a proxy that
        was merely *available*:

        | gate | it read | its subject |
        |---|---|---|
        | the quiet gate (open question 22) | the host's `/proc/loadavg` | this container's CPU use |
        | the stall gate | time spent waiting | memory pressure |
        | this one | `is_eligible` | whether anything was fitted |
        | the plan-review fetch (2026-09-19) | a **cached** 404 and a **summarised** directory listing | the repository's bytes -- `curl` returned HTTP 200 and 52,010 bytes on the identical URL |
        | 2e's criterion-9 instrument | what one glob and one key spelling happened to walk -- 8 of 16 | the committed audit numbers its claim named |

        All five coincide with their subject in the common case and diverge
        exactly where the gate matters. **The tell is a gate whose predicate
        names a different quantity from its own reason string** -- section
        14.1's said "eligible" while meaning "fitted". The handoff carries the
        general form at (a10): **before reading an instrument, demonstrate it
        can produce both answers.**
        """
        return self in {
            Outcome.OK,
            Outcome.ITER_CAP_SMALL_GRAD,
            Outcome.ITER_CAP_LARGE_GRAD,
            Outcome.DIAGNOSTIC_LIMIT,
            Outcome.TRUST_RADIUS_COLLAPSED,
            Outcome.NONFINITE_OBJECTIVE,
            Outcome.RANK_DEFICIENT_X,
            Outcome.ILL_CONDITIONED_X,
            Outcome.DEGENERATE_HESSIAN,
        }

    @property
    def is_covered(self) -> bool:
        """Whether the point is IN THE DOMAIN and the run REACHED it.

        **THIS IS SECTION 14.2's COVERAGE DENOMINATOR, AND IT IS NOT
        `is_eligible`.** The two answer different questions and disagree about
        exactly one member. `is_eligible` asks *"is this location one the rate
        is over?"* -- a statement about the DOMAIN -- and its values are
        already written into committed artifacts, so it is not redefined.
        This one asks *"did the run produce information here?"*, and the
        difference is `NOT_ATTEMPTED`.

        **TWO EXCLUSIONS, TWO DIFFERENT REASONS, AND CONFLATING THEM IS THE
        DEFECT THIS PREDICATE EXISTS TO PREVENT:**

        | excluded | because |
        |---|---|
        | `NOT_APPLICABLE` | **the point is not in the domain** -- land, permanent ice. It is not a point any coverage statement is about |
        | `NOT_ATTEMPTED` | **the run never got there** -- nothing wrote here. The point is in the domain and the store has no information about it |

        **WHY THE SECOND EXCLUSION IS NOT COSMETIC.** Design doc section 12.5
        gives `NOT_ATTEMPTED` the entry *"n/a, and a finished store should hold
        none"* -- true of a finished store, and sub-phase 2f describes
        **unfinished** ones deliberately (D6, exit criterion 19). An unfinished
        store carries this member in proportion to how far the run did **not**
        get, so counting it in a coverage denominator dilutes the rate in
        proportion to the interruption: **a run killed earlier reports a better
        coverage rate.** That is the land dilution one member over, and no
        fixture that finishes can show it.

        **POSITIVE MEMBERSHIP, LIKE `is_fit_verdict` AND FOR THE SAME REASON.**
        An unknown member is not covered until someone says so. The default
        that matters here is the denominator's: a new member drifting IN
        dilutes every coverage rate silently, while a new member left OUT makes
        the rate louder and is caught by the nesting chain the moment it is
        also a fit verdict.

        **THE CHAIN IS THE INVARIANT, NOT THIS SET.** `is_failure` is inside
        `is_fit_verdict` is inside this is inside `is_eligible`, asserted over
        the whole enum by `tests/test_outcomes.py`. The middle step is what
        makes `failed/fitted` and `failed/covered` share a numerator and one
        unavailability condition.
        """
        return self in {
            Outcome.OK,
            Outcome.ITER_CAP_SMALL_GRAD,
            Outcome.ITER_CAP_LARGE_GRAD,
            Outcome.DIAGNOSTIC_LIMIT,
            Outcome.TRUST_RADIUS_COLLAPSED,
            Outcome.NONFINITE_OBJECTIVE,
            Outcome.RANK_DEFICIENT_X,
            Outcome.ILL_CONDITIONED_X,
            Outcome.DEGENERATE_HESSIAN,
            Outcome.CANDIDATE_DROPPED,
            Outcome.INSUFFICIENT_DATA,
            Outcome.SCREENED_OUT,
        }

    @property
    def code(self) -> int:
        """Stable integer code, for the batched arrays and the zarr schema."""
        return _CODES[self]

    @classmethod
    def from_code(cls, value: int) -> Outcome:
        """Invert `code`."""
        return _BY_CODE[int(value)]


@dataclass(frozen=True)
class FailureTally:
    """One census of outcome codes, reduced to the counts a rate needs.

    **THIS IS THE PROJECT'S ONE DEFINITION OF "THE FAILURE RATE", AND IT IS
    SINGLE ON PURPOSE.** The quantity was computed in two places with two
    arithmetics -- section 14.1's verdict and the live counters -- and they
    disagreed for four days without anything noticing, because **a search
    finds call sites of a FUNCTION and not computations of a QUANTITY.** The
    verdict's denominator was repaired on 2026-09-20 and the counters' was not,
    since the counters call no predicate a search for the repair could reach.

    **THE THREE COUNTS ARE THREE FACTS AND ONLY ONE IS A DENOMINATOR FOR A
    FAILURE RATE.**

    | count | what it is | what it answers |
    |---|---|---|
    | `points` | every code in the census | how big is the grid |
    | `eligible` | `Outcome.is_eligible` | which locations a rate is over at all |
    | `covered` | `Outcome.is_covered` | **section 14.2's coverage population** -- in the domain AND reached |
    | `fitted` | `Outcome.is_fit_verdict` | where a fit verdict exists |

    **~~`eligible` was described here as "section 14.2's coverage
    population"~~ -- CORRECTED 2f TASK 2.** It is not: it counts points the
    run never reached, so a rate over it improves the earlier an interrupted
    run was killed. `covered` is that population, and the two differ by
    `NOT_ATTEMPTED` alone. `eligible` is kept, unchanged, because its values
    are recorded in committed artifacts and it answers a real question --
    a different one.

    **BOTH RATES ARE FIELDS, AND THAT IS WHY THERE ARE TWO.** Where a
    denominator is contested, print both and let the difference speak rather
    than choosing one and carrying a caveat. `rate` is `failed / fitted` --
    *"is this candidate failing the fits it attempts?"* -- and `coverage_rate`
    is `failed / covered` -- *"how much of what the run reached came out
    bad?"*. **They share a numerator**, because `is_failure` is inside
    `is_fit_verdict`, so the gap between them is the denominator alone: the
    in-domain points the run reached and did not fit.

    **ONE UNAVAILABILITY CONDITION SERVES BOTH**, because `is_fit_verdict` is
    inside `is_covered`: `fitted == 0` is the only way either denominator can
    be zero. Stating it once is not a shortcut, it is the nesting chain being
    true.

    **`failed / fitted` is correct in both eras** -- before and after section
    13.6's declared domain mask -- because "is this candidate failing the fits
    it attempts" has nothing to do with how much of the grid is out of domain.
    A denominator that includes unfittable points is diluted in proportion to
    the land fraction, which is right on an ocean box and wrong on a global
    run.

    Attributes:
        points: Every code counted, fit verdict or not.
        eligible: Locations a rate is over at all -- **not** the coverage
            population; see the correction above.
        covered: Points in the domain that the run reached. **The coverage
            rate's denominator.**
        fitted: Points carrying a fit verdict. **The rate's denominator.**
        failed: Fitted points that failed, by `Outcome.is_failure`.
        rate: `failed / fitted`, or **None when nothing was fitted**.
        coverage_rate: `failed / covered`, or **None when nothing was
            fitted** -- the same condition, for the reason above.
        unavailable: Why there is no rate, or None when there is one. **Never
            a rate of 0.0 for a candidate that was never tried** -- that reads
            identically to one fitted everywhere and passing, which is the
            collapse section 14.1's `no_evidence` verdict exists to prevent,
            one granularity down.
    """

    points: int
    eligible: int
    covered: int
    fitted: int
    failed: int
    rate: float | None
    coverage_rate: float | None
    unavailable: str | None


def failure_tally(
    census: Mapping[Outcome, int] | Mapping[str, int],
) -> FailureTally:
    """Reduce a census of outcome counts to `FailureTally`.

    **PURE, AND IN THIS MODULE BECAUSE BOTH CONSUMERS ALREADY IMPORT IT.**
    `metamer.progress` cannot tally failures without `Outcome`, and
    `metamer.report` imports this module with `metamer.core` riding along, so
    one definition here adds no edge to either import graph -- checked at
    sub-phase 2f Task 2's pre-flight rather than assumed.

    **A NEW MEMBER LANDS ON THE SAFE SIDE IN EVERY CONSUMER AT ONCE**, because
    the counts are taken from `is_fit_verdict`, which is a POSITIVE membership
    test: an unclassified member is not a fit, so it cannot silently become a
    denominator.

    Args:
        census: Counts keyed by `Outcome` members or by their string values.
            Both spellings are accepted because the live counters key a
            `Counter` by value and a store reader holds members. **The type is
            a UNION of two mappings rather than one mapping of a union key**,
            because `Mapping` is invariant in its key: a caller holding a
            declared `dict[Outcome, int]` cannot pass it as a
            `Mapping[Outcome | str, int]`, and would otherwise have to widen
            its own annotation to satisfy this one.

    Returns:
        The tally, with `rate=None` and a reason where nothing was fitted.

    Raises:
        ValueError: If a key is not an outcome. **Refused rather than ignored**
            -- an unknown key that contributed only to `points` would lower
            every rate computed from the census with nothing visible to a
            reader.
    """
    points = eligible = covered = fitted = failed = 0
    for key, count in census.items():
        try:
            member = key if isinstance(key, Outcome) else Outcome(key)
        except ValueError as error:
            raise ValueError(
                f"{key!r} is not an outcome; a census with an unknown key "
                "would lower every rate computed from it and show nothing"
            ) from error
        points += int(count)
        if member.is_eligible:
            eligible += int(count)
        if member.is_covered:
            covered += int(count)
        if member.is_fit_verdict:
            fitted += int(count)
            if member.is_failure:
                failed += int(count)

    if fitted == 0:
        return FailureTally(
            points=points,
            eligible=eligible,
            covered=covered,
            fitted=0,
            failed=0,
            rate=None,
            coverage_rate=None,
            unavailable=(
                "no point was fitted, so there is no rate: 0/0 is not a score, "
                "and 0.0 would read identically to a candidate fitted "
                "everywhere that passed"
            ),
        )
    return FailureTally(
        points=points,
        eligible=eligible,
        covered=covered,
        fitted=fitted,
        failed=failed,
        rate=failed / fitted,
        # **THE SECOND DENOMINATOR IS COMPUTED HERE OR IT IS COMPUTED TWICE.**
        # `covered >= fitted > 0` is guaranteed by the nesting chain, so this
        # division is safe under the same guard as the one above -- which is
        # why there is one `unavailable` and not two.
        coverage_rate=failed / covered,
        unavailable=None,
    )


# Stable on-disk codes. NEVER renumber: they are written to the zarr store as
# uint8 and a renumbering silently reinterprets every archived run. Adding a new
# member takes the next free code and bumps the store's schema_version.
_CODES: dict[Outcome, int] = {
    Outcome.OK: 0,
    Outcome.ITER_CAP_SMALL_GRAD: 1,
    Outcome.ITER_CAP_LARGE_GRAD: 2,
    Outcome.DIAGNOSTIC_LIMIT: 3,
    Outcome.TRUST_RADIUS_COLLAPSED: 4,
    Outcome.NONFINITE_OBJECTIVE: 5,
    Outcome.RANK_DEFICIENT_X: 6,
    Outcome.DEGENERATE_HESSIAN: 7,
    Outcome.NOT_ATTEMPTED: 8,
    Outcome.CANDIDATE_DROPPED: 9,
    Outcome.INSUFFICIENT_DATA: 10,
    Outcome.ILL_CONDITIONED_X: 11,
    Outcome.SCREENED_OUT: 12,
    Outcome.NOT_APPLICABLE: 13,
}
_BY_CODE: dict[int, Outcome] = {code: member for member, code in _CODES.items()}


def outcome_array(batch: int, outcome: Outcome = Outcome.OK) -> NDArray[np.uint8]:
    """Return a per-series outcome array filled with one value.

    Outcomes are PER SERIES wherever they cross a batched boundary. A scalar
    outcome for a batch of B means one bad grid point marks all B as failed,
    which contradicts both "(B, N) is the only code path" and the output
    schema's per-(point, model) status -- and turns the spatial failure map,
    which is itself a diagnostic, into a picture of the tile grid.
    """
    return np.full(batch, outcome.code, dtype=np.uint8)
