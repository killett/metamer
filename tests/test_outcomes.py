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
    design doc section 8.6 and listing the failure rows by hand. Per the
    task-3 brief's correction 1, `is_failure` excludes exactly three members
    -- OK, NOT_ATTEMPTED, INSUFFICIENT_DATA -- so the remaining nine members,
    including ITER_CAP_SMALL_GRAD, are all failures. (The brief's original
    text wrongly excluded ITER_CAP_SMALL_GRAD too; section 8.6 describes it
    as "flagged", and something excluded from `is_failure` is not flagged
    anywhere.)
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
        Outcome.CANDIDATE_DROPPED,
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


def test_outcome_has_twelve_members():
    """The taxonomy has exactly the twelve members design doc section 8.6 lists.

    Expected value determined independently by counting the rows of the
    section 8.6 table by hand: OK, ITER_CAP_SMALL_GRAD, ITER_CAP_LARGE_GRAD,
    DIAGNOSTIC_LIMIT, TRUST_RADIUS_COLLAPSED, NONFINITE_OBJECTIVE,
    RANK_DEFICIENT_X, ILL_CONDITIONED_X, DEGENERATE_HESSIAN, NOT_ATTEMPTED,
    CANDIDATE_DROPPED, INSUFFICIENT_DATA -- twelve rows.

    Bug this catches: a silently dropped or duplicated member, which would
    shift or collide the on-disk uint8 codes without anyone noticing.
    """
    assert len(Outcome) == 12


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
