import ast
from pathlib import Path

import pytest

from metamer.core.outcomes import Outcome, failure_tally

#: Every `src/` module whose AST mentions `Outcome`, with its count of division
#: nodes. **Measured by `ast` on 2026-09-21, not hand-counted**, and pinned
#: rather than bounded because this set changes rarely and every change is a
#: decision somebody should read.
#:
#: **NOTHING HERE IS CLASSIFIED.** `pathlib` joins are division nodes and are
#: in these counts; so are normalisations like `audit_report`'s `gap / scale`.
#: A count that moves is not by itself a defect -- it is a diff a reviewer
#: judges. The alternative was a count of "rate-shaped" divisions, and that is
#: the instrument this table replaces: it has no rule that reproduces it, so it
#: could not be re-derived by the next reader and was being maintained rather
#: than measured.
FAILURE_RATE_SITE_TABLE: dict[str, int] = {
    "metamer/batch/abort.py": 0,
    "metamer/batch/audit_report.py": 2,
    "metamer/batch/store.py": 2,
    "metamer/batch/warmstart.py": 2,
    "metamer/batch/write.py": 0,
    "metamer/bench/arms.py": 1,
    "metamer/bench/fields.py": 14,
    "metamer/bench/spike.py": 8,
    "metamer/core/__init__.py": 0,
    "metamer/core/counting.py": 6,
    "metamer/core/criteria.py": 2,
    "metamer/core/engines/compiled.py": 3,
    "metamer/core/engines/kalman.py": 2,
    "metamer/core/fit.py": 0,
    "metamer/core/objective.py": 0,
    "metamer/core/optimize.py": 3,
    # 1 -> 2 at 2f Task 2, DELIBERATELY: the second denominator's division,
    # `failed / covered`. Put here rather than in the report, because a
    # rate computed at its consumer is a second definition of it.
    "metamer/core/outcomes.py": 2,
    "metamer/progress.py": 1,
    "metamer/report/reader.py": 1,
    # ADDED DELIBERATELY at 2f Task 2, and the ZERO is the assertion.
    # The report prints; it computes nothing. Both failure rates are
    # fields of `failure_tally`, so a division appearing in this module
    # is a second definition of a quantity that has one -- which is the
    # exact defect this table exists to catch, in the exact module the
    # ruling predicted would be its first real test.
    "metamer/report/numbers.py": 0,
}


def _outcome_referencing_modules() -> dict[str, int]:
    """The scope, decided mechanically: `src/` modules whose AST names `Outcome`.

    An identifier anywhere in the tree counts -- a `Name`, an `Attribute`, an
    import alias or a definition -- because the question is whether the module
    is in the taxonomy's world at all, not how it spells its reference.
    """
    root = Path(__file__).resolve().parents[1] / "src"
    table: dict[str, int] = {}
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names: set[str] = set()
        divisions = 0
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                names.add(node.id)
            elif isinstance(node, ast.Attribute):
                names.add(node.attr)
            elif isinstance(node, ast.alias):
                names.add(node.name.rpartition(".")[2])
                if node.asname is not None:
                    names.add(node.asname)
            elif isinstance(
                node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
            ):
                names.add(node.name)
            if isinstance(node, ast.Div | ast.FloorDiv):
                divisions += 1
        if "Outcome" in names:
            table[path.relative_to(root).as_posix()] = divisions
    return table


def _predicate_table_from_docstring() -> dict[Outcome, tuple[bool, bool, bool, bool]]:
    """Parse `Outcome`'s four-predicate table out of its own docstring.

    Rows are `| `MEMBER` | yes | no | ... |` and nothing else is accepted: a
    cell that is neither `yes` nor `no`, or a member name the enum does not
    know, raises rather than being skipped. **A parser that silently drops a
    malformed row would make the table shrink and the comparison still pass**,
    which is the (c7) failure -- a reading that does not assert the size of
    what it found.
    """
    docstring = Outcome.__doc__ or ""
    table: dict[Outcome, tuple[bool, bool, bool, bool]] = {}
    for line in docstring.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 5 or not cells[0].startswith("`"):
            continue
        name = cells[0].strip("`")
        if name == "member":
            continue
        member = Outcome[name]
        flags = tuple(_yes_or_no(cell, name) for cell in cells[1:])
        assert len(flags) == 4
        table[member] = flags
    return table


def _yes_or_no(cell: str, row: str) -> bool:
    """One table cell, refused rather than guessed."""
    if cell not in {"yes", "no"}:
        raise ValueError(f"row {row}: {cell!r} is neither 'yes' nor 'no'")
    return cell == "yes"


def test_insufficient_data_is_not_a_failure():
    """A thin record is not a failure -- and since 2026-09-20 it IS in the denominator.

    Bug this catches: counting INSUFFICIENT_DATA as failure, which on a global
    ocean-only run reports ~70% 'failure' and turns the number into noise
    everyone learns to ignore.

    **~~`is_eligible is False`~~ INVERTED 2026-09-20, open question 24.** The
    exclusion followed design doc section 8.6, which described this member as
    "land, permanent ice" -- the conflation section 12.5 was written to undo.
    Land is `NOT_APPLICABLE`; **this series** having too thin a record is this
    member, and section 12.5 calls it eligible because *"its rate is a real
    statement about record coverage"*.

    **The ~70% fear in the paragraph above is NOT what this change causes**,
    and the direction is worth stating because it looks like the same subject:
    this member is not a failure, so it enters the denominator and never the
    numerator, and every rate it touches can only FALL. Land counted as failed
    is `RANK_DEFICIENT_X`, which `tests/test_objective.py` pins.
    """
    assert Outcome.INSUFFICIENT_DATA.is_failure is False
    assert Outcome.INSUFFICIENT_DATA.is_eligible is True
    assert Outcome.NOT_APPLICABLE.is_eligible is False


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
    always zero. Pairing a known-False case with a known-True case is what
    catches a constant stub that a single-value check would let through.

    **THE KNOWN-FALSE CASE MOVED ON 2026-09-20 AND THE TEST WOULD OTHERWISE
    HAVE GONE VACUOUS.** It was `INSUFFICIENT_DATA`, which open question 24
    made eligible; the only remaining ineligible member is `NOT_APPLICABLE`.
    A triviality guard whose False case becomes True stops guarding anything
    while still passing -- which is why this file's one-table test asserts the
    whole enum and this one asserts the pair.
    """
    assert Outcome.NOT_APPLICABLE.is_eligible is False
    assert Outcome.OK.is_eligible is True


def test_every_member_is_classified_by_every_predicate_in_one_table():
    """The whole taxonomy in one place, read out of the module's own docstring.

    Expected values determined independently: design doc section 8.6's taxonomy
    table for the fit verdicts, and section 12.5's non-fit grouping table -- the
    one whose heading says it is what section 14.2's denominator reads -- for the
    codes that are decisions rather than verdicts. Read off both by hand into
    `Outcome`'s docstring, which this test parses and compares against what the
    four properties actually return.

    **THE ORACLE IS THE DOCSTRING AND THAT IS THE POINT.** The previous form of
    this test carried the table as a dict in the test file, where it was correct
    and invisible -- nobody reading `outcomes.py` could see all the
    classifications at once, which is precisely the reading that prevents asking
    one predicate and meaning another. Moving the table into the module and
    asserting against it makes the documentation load-bearing: a member
    reclassified in code and not in the table fails here, and so does a table
    edited without the code.

    **The decided-skip group is the middle block and it is the one that keeps
    being got wrong:** `NOT_ATTEMPTED`, `SCREENED_OUT` and `CANDIDATE_DROPPED`
    are all "the run did not fit this", all eligible, none a failure -- **and
    they are no longer alike in the fourth column.** `SCREENED_OUT` and
    `CANDIDATE_DROPPED` are decisions taken AT a point the run reached;
    `NOT_ATTEMPTED` means nothing wrote there at all, which is why it is the
    one member outside `is_covered` but inside `is_eligible`.

    Bug this catches: a new member landing in some columns and not others. The
    properties are four separate membership sets, so a member added to one and
    forgotten in another is a single-line omission that reads as complete.

    **PROVED TO BITE 2026-09-14** (as the three-column form): `CANDIDATE_DROPPED`
    was put back into the failure set and FOUR tests failed -- this one, the
    set-equality guard, the decided-skip guard, and the vectorised arithmetic in
    `tests/test_audit_report.py`. **The fourth is the one that matters**: the
    property and the lookup table are two things, and only that test asserts the
    half that reaches a report.
    """
    table = _predicate_table_from_docstring()

    assert len(table) == len(Outcome), (
        f"the docstring table has {len(table)} rows and the enum has "
        f"{len(Outcome)} members; a member was added without a row, or a row "
        "names something that is not a member"
    )
    assert table == {
        member: (
            member.is_failure,
            member.is_fit_verdict,
            member.is_covered,
            member.is_eligible,
        )
        for member in Outcome
    }


def test_the_four_predicates_form_one_nesting_chain_with_no_step_collapsed():
    """`is_failure` < `is_fit_verdict` < `is_covered` < `is_eligible`, strictly.

    Expected values determined independently from what each predicate ASKS,
    not from its membership set: a failure is a kind of fit verdict; a fit
    verdict can only exist where the run reached an in-domain point; a point
    the run reached is in the domain, which is all `is_eligible` requires.

    **THE CHAIN IS LOAD-BEARING IN THREE WAYS, WHICH IS WHY IT IS PINNED
    RATHER THAN LEFT AS A PROPERTY THAT HAPPENS TO HOLD:**

    1. `is_failure` inside `is_fit_verdict` makes the NUMERATOR common to both
       failure rates, so `failed/fitted` and `failed/covered` differ in their
       denominator alone. That is what makes "the gap between them is the
       store's exposure" a fact rather than a slogan -- any other difference
       would put two quantities into one subtraction.
    2. `is_fit_verdict` inside `is_covered` means `fitted > 0` implies
       `covered > 0`, so the coverage column can never divide by zero while
       the fitted column computes. **The two share exactly ONE unavailability
       condition**, which is why `FailureTally` states it once.
    3. A future member that breaks the chain fails HERE, rather than landing
       in one population and not another and being found by a rate that moved.

    Bug this catches: a new `Outcome` member added to `is_fit_verdict` and
    forgotten in `is_covered`, which would put a fit verdict outside the
    coverage denominator -- `failed/covered` could then exceed 1.0, a rate
    above 100% that no assertion on either predicate alone would catch.

    **EACH STEP IS ASSERTED STRICT, WITH ITS WITNESS.** A containment test
    alone passes when two predicates are the SAME set, which is exactly the
    collapse this taxonomy keeps suffering -- section 14.1 asked `is_eligible`
    while meaning `is_fit_verdict` precisely because they agreed on every
    member anyone had looked at.
    """
    for member in Outcome:
        if member.is_failure:
            assert member.is_fit_verdict, f"{member} fails without a fit verdict"
        if member.is_fit_verdict:
            assert member.is_covered, f"{member} is a fit verdict the run did not reach"
        if member.is_covered:
            assert member.is_eligible, f"{member} is covered but not eligible"

    # The witnesses that keep each step PROPER. Named individually: a count
    # would pass on the wrong member.
    assert Outcome.OK.is_fit_verdict and not Outcome.OK.is_failure
    assert Outcome.SCREENED_OUT.is_covered and not Outcome.SCREENED_OUT.is_fit_verdict
    assert Outcome.NOT_ATTEMPTED.is_eligible and not Outcome.NOT_ATTEMPTED.is_covered


def test_not_attempted_is_the_only_member_between_covered_and_eligible():
    """The one member the two denominators disagree about, named.

    Expected value determined independently: `is_eligible` excludes
    `NOT_APPLICABLE` alone, and `is_covered` excludes that member plus
    `NOT_ATTEMPTED`. The difference is therefore exactly one member, by
    construction of the two sets rather than by counting them.

    Bug this catches: a second member drifting into the gap -- at which point
    "the gap between the two rates is the run's unreached fraction" stops
    being true and the coverage rate silently answers a third question.
    **`test_the_dilution_is_proportional_to_how_far_the_run_did_not_get` in
    `tests/test_report_numbers.py` is the behavioural half of this claim**;
    this is the structural half, and it is the one that fails the day a member
    is added.
    """
    covered = {m for m in Outcome if m.is_covered}
    eligible = {m for m in Outcome if m.is_eligible}

    assert eligible - covered == {Outcome.NOT_ATTEMPTED}


def test_no_committed_artifact_carries_insufficient_data():
    """Open question 24's artifact check, as an invariant rather than a date.

    Moving `INSUFFICIENT_DATA` into the failure-rate denominator changes every
    rate computed over a population containing it. **The claim that no
    committed number moved rests on that population being empty**, which is a
    statement about the artifacts and not about the enum.

    Expected value determined independently: every committed JSON and JSONL
    artifact under `docs/superpowers/notes/` and `bench/` was scanned on
    2026-09-19 and none carries this member, across sixteen outcome histograms
    in five families.

    Bug this catches: a future committed artifact containing the member, which
    would silently make the re-baselining retroactive and two committed rates
    incomparable. **The right response to this failing is not to loosen it**;
    it is to recompute the artifact and say so.

    **IT SCANS BOTH EXTENSIONS AND DOES NOT KEY ON A HISTOGRAM SPELLING**, and
    that is the point rather than an implementation detail. 2e's criterion-9
    helper globbed `*.json` for the key `outcome_counts` and reached 8 of the
    16 committed histograms -- six are spelled `counts` and two live in
    `.jsonl`. Searching the raw text for the member's own value is immune to
    both. **(a10):** the positive control below is what demonstrates the scan
    can see an outcome name at all, so a pass is not merely a scan that found
    nothing because it was looking in the wrong place.
    """
    root = Path(__file__).resolve().parents[1]
    scanned = 0
    saw_an_outcome_name = False
    for directory in (root / "docs" / "superpowers" / "notes", root / "bench"):
        for pattern in ("*.json", "*.jsonl"):
            for path in sorted(directory.glob(pattern)):
                text = path.read_text(encoding="utf-8")
                scanned += 1
                assert Outcome.INSUFFICIENT_DATA.name not in text, path.name
                assert Outcome.INSUFFICIENT_DATA.value not in text, path.name
                saw_an_outcome_name |= Outcome.DEGENERATE_HESSIAN.name in text

    assert scanned > 0, "no committed artifact was scanned; the check is vacuous"
    assert saw_an_outcome_name, (
        "no committed artifact carried ANY outcome member name, so this scan "
        "has not been shown able to find one -- a pass would mean nothing"
    )


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


# ---------------------------------------------------------------------------
# The failure tally -- ONE definition of a quantity computed in several places
# ---------------------------------------------------------------------------


def test_the_failure_rate_is_over_fitted_points_and_not_over_points_touched():
    """The denominator is fits, and land does not dilute it.

    Expected values determined independently by hand from the census below:
    twenty points, sixteen of them `INSUFFICIENT_DATA` (which is what a run
    writes for land until design doc section 13.6 lands) and four
    `DEGENERATE_HESSIAN`. Four of the four points that were FITTED failed, so
    the rate is 4/4 = 1.0. The eligible population is all twenty, because open
    question 24 put `INSUFFICIENT_DATA` in it; the points touched are twenty.

    Bug this catches: `failed / points`, which reports **0.20** on this census
    -- the exact number `LiveCounters.lines` printed from 2e until 2026-09-21,
    under the label `fits=20`. A candidate failing every fit it attempted reads
    as failing one in five, and it degrades in proportion to how much of the
    grid is out of domain, so it is right on this project's one ocean box and
    wrong on the global run section 14.1's ten-hour scenario is about.

    **THE THREE COUNTS ARE THREE FACTS.** `points` is what the run touched,
    `eligible` is section 14.2's coverage population, `fitted` is where a fit
    verdict exists -- and only the third is a denominator for a failure rate.
    """
    census = {
        Outcome.INSUFFICIENT_DATA.value: 16,
        Outcome.DEGENERATE_HESSIAN.value: 4,
    }

    tally = failure_tally(census)

    assert tally.points == 20
    assert tally.eligible == 20
    assert tally.fitted == 4
    assert tally.failed == 4
    assert tally.rate == 1.0
    assert tally.unavailable is None


def test_a_candidate_that_was_never_fitted_has_no_rate_and_says_why():
    """0/0 is not a score, and "nothing fitted" is not 0.0.

    Expected value determined independently: design doc section 12.5 calls
    `SCREENED_OUT` a decided skip -- eligible, not a failure, and not a fit --
    so a candidate screened everywhere has a full eligible population and no
    fit to judge.

    Bug this catches: the rate reported as **0.0**, which is what a candidate
    fitted at every point and passing reports. "Nothing was tried" and
    "everything succeeded" are opposite facts and would print alike -- the
    collapse design doc section 14.1's no-evidence decision fixed at SAMPLE
    granularity, appearing at CANDIDATE granularity.
    """
    tally = failure_tally({Outcome.SCREENED_OUT.value: 20})

    assert tally.points == 20
    assert tally.eligible == 20
    assert tally.fitted == 0
    assert tally.failed == 0
    assert tally.rate is None
    assert tally.unavailable is not None
    assert "fitted" in tally.unavailable


def test_nothing_fitted_and_everything_passed_do_not_print_alike():
    """The discrimination the rule exists for, as one assertion over two censuses.

    Expected values determined independently: a candidate fitted at twenty
    points with no failures is 0/20 = 0.0; a candidate screened out at twenty
    points has no rate at all.

    Bug this catches: a fixture that cannot show the rule DISCRIMINATES. If
    every candidate in a test has no fits, "unavailable everywhere" is also
    what a tally that had simply broken would produce -- (a10), before reading
    an instrument demonstrate it can produce both answers. Pairing the two
    censuses in one test is what makes the `None` mean something.
    """
    screened = failure_tally({Outcome.SCREENED_OUT.value: 20})
    passing = failure_tally({Outcome.OK.value: 20})

    assert (screened.rate, passing.rate) == (None, 0.0)
    assert screened.fitted == 0 and passing.fitted == 20
    assert screened.unavailable is not None and passing.unavailable is None


def test_an_empty_census_is_unavailable_rather_than_an_error():
    """A tile with nothing recorded yet has no rate and does not raise.

    Bug this catches: a `ZeroDivisionError` on the first tile of a run, before
    anything has been tallied -- which `LiveCounters` must survive because it
    prints per tile from the start.
    """
    tally = failure_tally({})

    assert (tally.points, tally.eligible, tally.fitted, tally.failed) == (0, 0, 0, 0)
    assert tally.rate is None
    assert tally.unavailable is not None


def test_the_tally_accepts_outcome_members_as_keys_as_well_as_their_values():
    """Both spellings, because two callers hold two shapes.

    `LiveCounters` keys its `Counter` by the enum's string VALUE; a caller
    reading a store holds `Outcome` members. Accepting both is what lets one
    definition serve both without either converting at the boundary and
    getting it subtly wrong.

    Bug this catches: a tally that silently counts nothing because its keys
    were members where it expected strings -- which reports `fitted=0` and
    therefore "unavailable", a plausible-looking answer rather than a crash.
    """
    by_value = failure_tally({Outcome.OK.value: 3, Outcome.DEGENERATE_HESSIAN.value: 1})
    by_member = failure_tally({Outcome.OK: 3, Outcome.DEGENERATE_HESSIAN: 1})

    assert by_value == by_member
    assert by_member.rate == 0.25


def test_an_unknown_outcome_name_is_refused_rather_than_ignored():
    """A key the taxonomy does not know stops the tally.

    Bug this catches: a misspelled or renamed member silently contributing to
    `points` and to nothing else, which lowers every rate computed from the
    census without changing anything a reader can see. Refusing is the (a2b)
    treatment: unavailable with a reason beats a plausible number.
    """
    with pytest.raises(ValueError, match="not_a_real_outcome"):
        failure_tally({"not_a_real_outcome": 1})


def test_both_denominators_come_from_one_call_and_differ_by_the_unreached():
    """Both rates, both denominators, one function -- and the gap is readable.

    Expected values computed BY HAND from the census below, which is written to
    make the two rates different rather than to exercise a code path: 4 failed,
    2 OK, so 6 fit verdicts; plus 2 `SCREENED_OUT` (covered, not fitted), 3
    `NOT_ATTEMPTED` (eligible, NOT covered) and 5 `NOT_APPLICABLE` (neither).
    So fitted = 6, covered = 6 + 2 = 8, eligible = 8 + 3 = 11, points = 16.
    `failed/fitted` = 4/6 = 0.666..., `failed/covered` = 4/8 = 0.5.

    Bug this catches: a coverage denominator built by subtracting one member at
    a call site rather than by asking `is_covered`. Such a site agrees with
    this function on a census like this one and diverges the moment a member is
    added -- which is the two-definitions failure that cost four days between
    the verdict and the live counters, arriving in a new place.

    **THE REPORT COMPUTES NOTHING; IT PRINTS.** Both rates are fields, so the
    division lives at the one definition and a module that wants the second
    denominator cannot get it by dividing for itself.
    """
    tally = failure_tally(
        {
            Outcome.DEGENERATE_HESSIAN: 4,
            Outcome.OK: 2,
            Outcome.SCREENED_OUT: 2,
            Outcome.NOT_ATTEMPTED: 3,
            Outcome.NOT_APPLICABLE: 5,
        }
    )

    assert (tally.points, tally.eligible, tally.covered, tally.fitted) == (16, 11, 8, 6)
    assert tally.failed == 4
    assert tally.rate == pytest.approx(4 / 6)
    assert tally.coverage_rate == pytest.approx(0.5)
    assert tally.unavailable is None


def test_a_census_the_run_never_reached_does_not_flatter_the_coverage_rate():
    """The dilution, at the one definition: unreached points are not a denominator.

    Expected values computed by hand from two censuses that differ ONLY in how
    far the run got. Both have 3 failed of 4 fitted. The first adds no
    unreached points; the second adds 96 `NOT_ATTEMPTED`. **Both must report
    the same two rates**, because neither rate is about points the run never
    reached.

    Bug this catches: `NOT_ATTEMPTED` inside the coverage denominator, which is
    what `is_eligible` would have given -- the second census would then report
    3/100 = 3% where the truth is 75%, and **the earlier a run was killed the
    better it would look.** An interrupted ten-hour run would report a
    flattering number precisely when a reader is deciding whether to restart
    it.

    **THE TWO ARMS ARE THE DISCRIMINATION** -- (a10). A single census cannot
    show this: any denominator produces *some* number, and only the pair shows
    that the number does not move with the interruption.
    """
    finished = failure_tally({Outcome.DEGENERATE_HESSIAN: 3, Outcome.OK: 1})
    interrupted = failure_tally(
        {Outcome.DEGENERATE_HESSIAN: 3, Outcome.OK: 1, Outcome.NOT_ATTEMPTED: 96}
    )

    assert finished.coverage_rate == pytest.approx(0.75)
    assert interrupted.coverage_rate == pytest.approx(0.75)
    assert interrupted.covered == 4
    assert interrupted.eligible == 100, "eligible still counts them, by its own rule"
    assert interrupted.points == 100


def test_when_nothing_was_fitted_BOTH_rates_are_unavailable_for_one_stated_reason():
    """One unavailability condition, because the chain says there is only one.

    Expected value determined independently from the nesting: `is_fit_verdict`
    is inside `is_covered`, so `fitted == 0` is the only way either denominator
    can be zero while the other is not. A census of nothing but decided skips
    has covered = 20 and fitted = 0.

    Bug this catches: the coverage column reporting **0.0** for a candidate
    that was never tried -- 0/20 is arithmetically fine and reads as a perfect
    score. That is the same collapse section 14.1's `no_evidence` verdict
    exists to prevent, one granularity down, and it is the defect that would
    have shipped if only the fitted column had been repaired.

    **AND THE COUNT SURVIVES THE RATE'S ABSENCE.** `covered` is still 20, so a
    reader sees the size of what was skipped rather than a blank.
    """
    tally = failure_tally({Outcome.SCREENED_OUT: 20})

    assert tally.fitted == 0
    assert tally.covered == 20
    assert tally.rate is None
    assert tally.coverage_rate is None
    assert tally.unavailable is not None
    assert "fitted" in tally.unavailable


def test_every_failure_rate_in_src_comes_from_the_one_definition():
    """The quantity has ONE definition, and these are exactly its consumers.

    Expected value determined independently by an `ast` walk of `src/`:
    **three** modules call `failure_tally` -- `progress.LiveCounters.lines`,
    `abort._rate_for`, and, since 2f Task 2, `report.numbers.compute`. The
    third arrived with **both** rates rather than dividing for itself, which is
    why the golden table records it at zero divisions.

    Bug this catches: a consumer REMOVED, which means it has grown its own
    arithmetic. Section 14.1's verdict and the live counters each had one, the
    verdict's denominator was repaired on 2026-09-20 and the display's was not,
    because **a search finds call sites of a FUNCTION and cannot find
    computations of a QUANTITY**; they disagreed for four days over the same
    data.

    **WHAT THIS TEST CANNOT SEE IS THE SIZE OF THE POPULATION IT IS DRAWN
    FROM** -- handoff (c7). A third site computing the rate with its own
    arithmetic calls nothing this walk can find. That claim is
    `test_the_rate_site_table_is_pinned_over_every_outcome_referencing_module`
    below, and the two are read together: this one says the shared definition
    is used, that one says no arithmetic grew beside it.
    """
    root = Path(__file__).resolve().parents[1] / "src"
    callers = sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*.py")
        if path.name != "outcomes.py"
        and "failure_tally(" in path.read_text(encoding="utf-8")
    )

    assert callers == [
        "metamer/batch/abort.py",
        "metamer/progress.py",
        "metamer/report/numbers.py",
    ], (
        "the set of failure_tally consumers moved. If a site was ADDED, check "
        "it is not a third arithmetic for the same quantity; if one was "
        "REMOVED, it has grown its own"
    )


def test_the_rate_site_table_is_pinned_over_every_outcome_referencing_module():
    """The SIZE claim the caller-set test cannot make, as a golden table.

    Scope is every `src/` module that references `Outcome`, decided by the
    `ast` rather than named by hand; the assertion is the set of those modules
    AND each module's count of division nodes. **Nothing is classified** --
    `pathlib` joins are in the counts -- so a moved count is a diff a reviewer
    judges rather than a verdict this test reaches.

    Expected values measured by `ast` on 2026-09-21 and recorded in
    `FAILURE_RATE_SITE_TABLE`. Three of them were cross-derived at the
    follow-up's pre-flight the same day, by a separate walk: `abort.py` 0,
    `progress.py` 1 (the percentage formatter), `core/outcomes.py` 1
    (`failed / fitted`), and `audit_report.py` 2 -- `_rate`'s
    `numerator / denominator`, which serves **seven** quantities
    (`selection_disagreement`, `selection_move`, `selection_dropout`,
    `ranked_fraction`, `rescue`, `loss`, `both_ok_fraction`), plus the
    `gap / scale` normalisation, which is not a rate.

    Bug this catches: **a third arithmetic for the failure rate, written
    anywhere in scope.** A module computing `failed / eligible` for itself
    instead of calling `failure_tally` moves its pinned count, which is the
    exact failure that shipped between 2e's Task 4 and Task 5 and that a
    caller enumeration structurally cannot see. It also catches a NEW
    `Outcome`-referencing module arriving unannounced: 2f's report modules
    each have to be added here deliberately, with their count.

    **FROZEN INSTRUMENTS UNDER `docs/superpowers/notes/` ARE OUT OF SCOPE, BY
    A STATED RULE AND NOT BY OMISSION** -- handoff (j8)'s third register. A
    committed harness is the experimental apparatus of a number somebody is
    still quoting, so rewriting it rewrites closed evidence. The rule survives
    a thirty-first harness landing next sub-phase in a way that "counted as one
    site" would not; a per-computation count over them is 184 nodes and
    dominated by `pathlib` joins, which is why they are excluded by kind and
    not by threshold.

    **TWO GAPS, NAMED HERE RATHER THAN PAPERED OVER:**

    1. Nothing in this suite enforces that NEW harness code reporting a
       failure rate calls `failure_tally`. That is a pre-flight obligation with
       an owner (handoff section 2), and a harness written next sub-phase can
       grow a fourth arithmetic with nothing failing.
    2. A rate computed by comparing **raw integer codes**, without referencing
       `Outcome` at all, falls outside this scope entirely -- such a module
       would not be in the table. Sub-phase 2f's D1 forbids it (a predicate
       must read its subject, not an available proxy) and nothing catches it.
    """
    assert _outcome_referencing_modules() == FAILURE_RATE_SITE_TABLE, (
        "the rate-site table moved. A module ADDED to the scope must be added "
        "here deliberately, with its count; a COUNT that moved is a new "
        "division node in a module that knows about Outcome -- check it is not "
        "a second arithmetic for a quantity failure_tally already defines"
    )
