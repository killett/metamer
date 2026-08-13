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


def test_the_two_deferred_outcomes_are_skips_and_not_failures():
    """`SCREENED_OUT` and `NOT_APPLICABLE` sit outside the failure rate.

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
    """
    assert Outcome.SCREENED_OUT.is_failure is False
    assert Outcome.SCREENED_OUT.is_eligible is True
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
