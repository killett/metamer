from pathlib import Path

from metamer.core.outcomes import Outcome


def test_insufficient_data_is_not_a_failure():
    """Land and permanent-ice pixels must not inflate the failure rate.

    Bug this catches: counting INSUFFICIENT_DATA as failure, which on a global
    ocean-only run reports ~70% 'failure' and turns the number into noise
    everyone learns to ignore.
    """
    assert Outcome.INSUFFICIENT_DATA.is_failure is False
    assert Outcome.INSUFFICIENT_DATA.is_eligible is False


def test_not_attempted_is_distinct_from_failure():
    """A screened-out candidate is not a failed candidate.

    Bug this catches: collapsing 'skipped' and 'failed' into one NaN, which
    have opposite scientific meanings.
    """
    assert Outcome.NOT_ATTEMPTED.is_failure is False
    candidate_dropped: Outcome = Outcome.CANDIDATE_DROPPED
    assert candidate_dropped is not Outcome.NOT_ATTEMPTED


def test_every_real_failure_reports_is_failure():
    """All genuine failure branches are counted as failures.

    Expected value determined independently by reading the taxonomy table in
    design doc section 8.6 and listing the failure rows by hand, and the
    non-fit grouping table in section 12.5 for the codes that are decisions
    rather than verdicts. ITER_CAP_SMALL_GRAD IS a failure: section 8.6
    describes it as "flagged", and something excluded from `is_failure` is not
    flagged anywhere.

    **~~`Outcome.CANDIDATE_DROPPED`~~ LEFT THIS SET AT 2e (2026-09-14), AND IT
    WAS A CORRECTION RATHER THAN A DECISION.** Section 12.5's grouping table --
    whose heading says it is what section 14.2's denominator reads -- has
    classified `SCREENED_OUT` and `CANDIDATE_DROPPED` identically as
    **legitimate non-fits** since 2a, and this set disagreed with it for four
    sub-phases. **Nothing caught it because the member has no producer**; 2e's
    early abort is its first.

    Bug this catches: a new member defaulting into the failure set, which is
    what one does if nothing decides otherwise -- and, in the other direction, a
    real failure branch quietly leaving it. **Set equality over the whole enum
    is the shape that catches both**, which is why this test is amended rather
    than replaced.
    """
    failures = {
        Outcome.ITER_CAP_SMALL_GRAD,
        Outcome.ITER_CAP_LARGE_GRAD,
        Outcome.DIAGNOSTIC_LIMIT,
        Outcome.TRUST_RADIUS_COLLAPSED,
        Outcome.NONFINITE_OBJECTIVE,
        Outcome.RANK_DEFICIENT_X,
        Outcome.ILL_CONDITIONED_X,
        Outcome.DEGENERATE_HESSIAN,
    }
    assert {o for o in Outcome if o.is_failure} == failures


def test_iteration_cap_with_small_gradient_is_distinct_from_ok():
    """Hitting the cap with a small gradient is not full convergence.

    Bug this catches: collapsing ITER_CAP_SMALL_GRAD into OK, which would
    hide "converged slowly" fits from any downstream count of exact
    convergences.
    """
    iter_cap_small_grad: Outcome = Outcome.ITER_CAP_SMALL_GRAD
    assert iter_cap_small_grad is not Outcome.OK


def test_iter_cap_small_grad_is_a_failure():
    """ITER_CAP_SMALL_GRAD counts as a failure -- a mild one, but a failure.

    This pins task-3 brief correction 1. Design doc section 8.6 describes
    ITER_CAP_SMALL_GRAD as "probably fine, flagged" -- flagged, not excluded.
    The enum member existing at all is what makes it visible in the spatial
    failure map, and that map is the diagnostic that matters at 10^7 series:
    an outcome excluded from `is_failure` never shows up there. Only OK,
    NOT_ATTEMPTED, and INSUFFICIENT_DATA are excluded from the failure
    denominator.

    Bug this catches: excluding ITER_CAP_SMALL_GRAD from `is_failure` (the
    brief's original, incorrect text), which would silently drop a real,
    if mild, non-convergence out of the failure map entirely.
    """
    assert Outcome.ITER_CAP_SMALL_GRAD.is_failure is True


def test_the_outcome_vocabulary_and_its_codes_are_enumerated():
    """Every member and its on-disk code, written out.

    **THIS REPLACED A COUNT ON 2026-08-13**, when Task 9 added two members and
    the count assertion failed in the one way a count can: by being right about
    the number and blind to everything else. The standing rule is enumerate,
    never count -- a count cannot see a rename, and cannot see two members
    swapping codes, which is the defect that silently reinterprets every
    archived store.

    Expected values determined independently: design doc section 8.6's table
    for the first twelve, in the order the codes were assigned, plus the two
    Task 9 added at the next free codes. `_CODES`'s docstring forbids
    renumbering, so these literals are permanent.

    Catches a dropped, renamed, duplicated or renumbered member.
    """
    assert {member.value: member.code for member in Outcome} == {
        "ok": 0,
        "iter_cap_small_grad": 1,
        "iter_cap_large_grad": 2,
        "diagnostic_limit": 3,
        "trust_radius_collapsed": 4,
        "nonfinite_objective": 5,
        "rank_deficient_x": 6,
        "degenerate_hessian": 7,
        "not_attempted": 8,
        "candidate_dropped": 9,
        "insufficient_data": 10,
        "ill_conditioned_x": 11,
        "screened_out": 12,
        "not_applicable": 13,
    }


def test_the_three_deferred_outcomes_are_skips_and_not_failures():
    """`SCREENED_OUT`, `CANDIDATE_DROPPED` and `NOT_APPLICABLE` sit outside it.

    **RENAMED AT 2e, NOT EDITED IN PLACE (2026-09-14).** It was
    `test_the_two_deferred_outcomes_are_skips_and_not_failures`; a count in a
    test's name is the same hazard as a count in prose, and this project has
    already paid for that once this sub-phase.

    Neither is reachable in 2a -- there is no screening block and no declared
    domain mask -- so the semantics are decided by the task that owns the
    denominator rather than by whichever task first emits one.

    `SCREENED_OUT` is a deliberate skip, like `NOT_ATTEMPTED`: the run chose not
    to fit, so counting it as a failure would make a *cheaper* configuration
    report a worse failure rate. `NOT_APPLICABLE` is a declared domain mask --
    land, permanent ice -- so like `INSUFFICIENT_DATA` it is **not eligible**
    either: it is not a point the failure rate is over.

    Catches either defaulting into the failure set, which is what a new member
    does if nothing decides otherwise: at 10^7 points a screened-out ocean
    basin would read as a catastrophic failure map.

    **AND THE ARGUMENT ABOVE IS WHY `CANDIDATE_DROPPED` BELONGS HERE.** *"The
    run chose not to fit, so counting it as a failure would make a cheaper
    configuration report a worse failure rate"* is true of a dropped candidate
    word for word -- a drop is exactly a configuration made cheaper by a
    decision the run took. **That sentence sat beside the member that did not
    need it and was never applied to the member that did**, because
    `CANDIDATE_DROPPED` had no producer until 2e. (j4) at a classification: an
    existing statement is evidence, and the sibling of the thing you are
    classifying is where to look first.
    """
    assert Outcome.SCREENED_OUT.is_failure is False
    assert Outcome.SCREENED_OUT.is_eligible is True
    assert Outcome.CANDIDATE_DROPPED.is_failure is False
    assert Outcome.CANDIDATE_DROPPED.is_eligible is True
    assert Outcome.NOT_APPLICABLE.is_failure is False
    assert Outcome.NOT_APPLICABLE.is_eligible is False


def test_rank_deficient_and_ill_conditioned_are_distinct_outcomes():
    """Exactly-singular and barely-identified are different scientific facts.

    Bug this catches: collapsing RANK_DEFICIENT_X and ILL_CONDITIONED_X into
    one outcome, which destroys the entire point of the failure map -- which
    of the two happened, and where -- per the project's own cross-cutting
    rule that these stay distinct outcomes.
    """
    rank_deficient: Outcome = Outcome.RANK_DEFICIENT_X
    assert rank_deficient is not Outcome.ILL_CONDITIONED_X


def test_is_eligible_is_not_trivially_constant():
    """is_eligible excludes INSUFFICIENT_DATA but not every other member.

    Bug this catches: an `is_eligible` implementation that always returns the
    same value regardless of member (e.g. always True, or always False),
    which would make the eligible-count denominator either meaningless or
    always zero. Pairing a known-False case (INSUFFICIENT_DATA) with a
    known-True case (OK) is what catches a constant stub that either always
    passes or always fails would otherwise slip past a single-value check.
    """
    assert Outcome.INSUFFICIENT_DATA.is_eligible is False
    assert Outcome.OK.is_eligible is True


def test_every_member_is_classified_by_both_properties_in_one_table():
    """The whole taxonomy in one place, rather than two exclusion lists.

    Expected values determined independently: design doc section 8.6's taxonomy
    table for the fit verdicts, and section 12.5's non-fit grouping table -- the
    one whose heading says it is what section 14.2's denominator reads -- for the
    codes that are decisions rather than verdicts. Read off both by hand.

    **The decided-skip group is the middle block and it is the one that keeps
    being got wrong:** `NOT_ATTEMPTED`, `SCREENED_OUT` and `CANDIDATE_DROPPED`
    are all "the run did not fit this, on purpose", all eligible, none a
    failure. `INSUFFICIENT_DATA` and `NOT_APPLICABLE` are the other shape --
    not failures and **not eligible either**, because they are not points the
    rate is over.

    Bug this catches: a new member landing in neither group or in both. The two
    properties are implemented as separate exclusion sets, so a member added to
    one and forgotten in the other is a single-line omission that reads as
    complete -- and there is no single place, other than this table, where the
    two can be seen together.

    **`INSUFFICIENT_DATA`'s row follows section 8.6, which section 12.5
    contradicts** -- open question 24, filed to 2f. This table pins what the code
    does today so the question is about a known value.

    **PROVED TO BITE 2026-09-14:** `CANDIDATE_DROPPED` was put back into the
    failure set and FOUR tests failed -- this one, the set-equality guard, the
    decided-skip guard, and the vectorised arithmetic in
    `tests/test_audit_report.py`. **The fourth is the one that matters**: the
    property and the lookup table are two things, and only that test asserts the
    half that reaches a report.
    """
    expected = {
        Outcome.OK: (False, True),
        Outcome.ITER_CAP_SMALL_GRAD: (True, True),
        Outcome.ITER_CAP_LARGE_GRAD: (True, True),
        Outcome.DIAGNOSTIC_LIMIT: (True, True),
        Outcome.TRUST_RADIUS_COLLAPSED: (True, True),
        Outcome.NONFINITE_OBJECTIVE: (True, True),
        Outcome.RANK_DEFICIENT_X: (True, True),
        Outcome.ILL_CONDITIONED_X: (True, True),
        Outcome.DEGENERATE_HESSIAN: (True, True),
        Outcome.NOT_ATTEMPTED: (False, True),
        Outcome.SCREENED_OUT: (False, True),
        Outcome.CANDIDATE_DROPPED: (False, True),
        Outcome.INSUFFICIENT_DATA: (False, False),
        Outcome.NOT_APPLICABLE: (False, False),
    }

    assert {m: (m.is_failure, m.is_eligible) for m in Outcome} == expected


def test_no_committed_report_carries_a_decided_skip():
    """The "nothing moves" claim, as a check rather than an inference.

    Moving `CANDIDATE_DROPPED` out of the failure set changes every rate
    computed over a population containing it. **The claim that no committed
    number moves rests on that population being empty**, which is a statement
    about the artifacts and not about the enum -- and "zero cases" is a claim
    about the instrument until something proves otherwise.

    Expected value determined independently: `CANDIDATE_DROPPED` has no producer
    in `src/` -- 2e's early abort is its first -- so no run that has ever
    happened could have written one.

    Bug this catches: a future committed artifact containing a decided-skip
    outcome, which would silently make the reclassification retroactive and this
    project's committed rates incomparable across it. **The right response to
    this test failing is not to loosen it**; it is to recompute the artifact and
    say so, because two rates computed under different denominators cannot be
    quoted beside each other.

    It scans every JSON under the notes directory rather than a list, because a
    gate over a set that can GROW must be written against the set -- (c5).
    """
    skips = {
        member.value
        for member in Outcome
        if not member.is_failure and member.is_eligible and member is not Outcome.OK
    }
    assert skips  # the group exists; an empty one would make this vacuous

    notes = Path(__file__).resolve().parents[1] / "docs" / "superpowers" / "notes"
    scanned = 0
    for path in sorted(notes.glob("*.json")):
        text = path.read_text(encoding="utf-8")
        scanned += 1
        for name in skips:
            assert name not in text, f"{path.name} carries {name!r}"
    assert scanned > 0, "no committed reports were scanned; the check is vacuous"
