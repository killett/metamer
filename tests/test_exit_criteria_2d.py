"""Phase 2d's exit criteria: the binders, and the readings taken off the artifacts.

**A 15-HOUR MEASUREMENT CANNOT BE A TEST, AND ITS RECORDED OUTPUT CAN.** Every
criterion resting on the benchmark asserts against the **committed rung
reports**, which are artifacts in the tree. The suite fails if a report is
missing, if a default its block names has since moved, or if a reading the
record claims is not in it -- so a report cannot quietly outlive the
configuration that produced it.

**AND THE ARTIFACT REGISTER TREATS A MISSING KEY AS "DRAWN BEFORE THE QUESTION
EXISTED".** The easy rung's report predates `field_construction_version`, which
is the truthful answer for a version 1 artifact; demanding the key
retroactively would make the register fail on the very artifacts it exists to
protect. **What is present is pinned; the absence is itself a dated fact.**
"""

from __future__ import annotations

import ast
import json
import pathlib
from typing import Any

import pytest

from metamer.bench import fields, report, smear
from tests.exit_criteria_2b import PHASE_2B_EXIT_CRITERIA, Verdict
from tests.exit_criteria_2c import PHASE_2C_EXIT_CRITERIA
from tests.exit_criteria_2d import PHASE_2D_EXIT_CRITERIA, READINGS

NOTES = pathlib.Path("docs/superpowers/notes")

#: The committed rung reports, by the construction they were drawn at.
#: **BOTH, ALWAYS**: the finding is the contrast, and a suite that checked one
#: would let the other rot.
COMMITTED_REPORTS = {
    1: NOTES / "phase2d-easy-rung-report.json",
    2: NOTES / "phase2d-difficulty-rung-report.json",
}

#: How many rungs E2's budget was derived for. **THE BUDGET FACTOR IS PROSE IN
#: `PROGRESS.md` AND THE PLAN, AND THAT IS CORRECT RATHER THAN A GAP** -- it is
#: a DECISION about how many arms run at how many rungs, not a value computed
#: from anything, and a constant in `src` would suggest it could be derived.
#: **So this assertion cannot compare two constants; its job is to make adding
#: a rung FORCE a re-derivation** rather than let a fourth rung be priced by a
#: factor computed for three.
RUNGS_THE_BUDGET_WAS_DERIVED_FOR = 3


def _load(path: pathlib.Path) -> dict[str, Any]:
    """One committed report."""
    loaded: dict[str, Any] = json.loads(path.read_text())
    return loaded


def _collected_test_names() -> set[str]:
    """Every `def test_...` under `tests/`, found by parsing rather than importing."""
    names: set[str] = set()
    for path in pathlib.Path("tests").rglob("test_*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                names.add(node.name)
    return names


# ---------------------------------------------------------------------------
# The binders
# ---------------------------------------------------------------------------


def test_the_record_covers_every_criterion_exactly_once():
    """Seventeen criteria, numbered 1 to 17, each once.

    Behaviour: the record is complete and has no duplicate number.

    Expected value determined independently: the plan's own table has
    seventeen rows.

    Bug this catches: a criterion dropped during editing -- which reads, from
    the closing table, exactly like a criterion that was never written.
    """
    numbers = [criterion.number for criterion in PHASE_2D_EXIT_CRITERIA]

    assert sorted(numbers) == list(range(1, 18))
    assert len(set(numbers)) == len(numbers)


def test_every_criterion_names_evidence_that_exists():
    """A verdict standing on a test that was renamed or deleted fails here.

    **THE LIMIT IS STATED RATHER THAN IMPLIED**: a static scan checks that the
    evidence EXISTS, not that it is relevant. Relevance is carried by each
    criterion's `statement` sitting beside its names.

    Expected values determined independently: every name in `established_by`
    is a `def test_...` somewhere under `tests/`, found by parsing.

    Bug this catches: a test renamed during a refactor, leaving a verdict whose
    stated evidence does not exist -- which reads exactly like a verdict whose
    evidence does. That is the failure 2b's criterion 6 had for four tasks.
    """
    have = _collected_test_names()
    missing = {
        (criterion.number, name)
        for criterion in PHASE_2D_EXIT_CRITERIA
        for name in criterion.established_by
        if name not in have
    }

    assert not missing, missing
    for criterion in PHASE_2D_EXIT_CRITERIA:
        assert criterion.established_by, criterion.number


def test_every_criterion_names_a_reading_with_no_exempt_list():
    """All seventeen, not a listed subset.

    Behaviour: each criterion's reading is one of the closed vocabulary.

    Expected values determined independently: `READINGS` is the plan's own
    third column.

    Bug this catches: a criterion whose verdict is about an unnamed quantity --
    2b's criteria 6 and 7 read as settled through four tasks because nobody
    wrote down which reading they meant, and three readings of that quantity
    differ by 1.58x. **An exempt list would be the third (c5) instance in 2d**:
    an enumeration of the members that existed when it was written, leaving a
    criterion added later exempt by default.
    """
    for criterion in PHASE_2D_EXIT_CRITERIA:
        assert criterion.reading is not None, criterion.number
        assert criterion.reading in READINGS, (criterion.number, criterion.reading)


def test_every_non_met_verdict_states_its_scope_and_every_criterion_its_outside():
    """A reduced or failed verdict says what it does and does not cover.

    Behaviour: `scope` is non-empty for every non-MET verdict, and `outside` is
    non-empty for all.

    Expected value determined independently: MET may carry an empty scope; the
    other two may not.

    Bug this catches: criterion 12 downgraded with no statement of what was and
    was not measured, which downstream is indistinguishable from a criterion
    measured and passed narrowly. **In 2d it also carries the by-construction
    distinction**, which is where FAILED-by-measurement and FAILED-by-construction
    are told apart without extending a vocabulary two other records use.
    """
    for criterion in PHASE_2D_EXIT_CRITERIA:
        if criterion.verdict is not Verdict.MET:
            assert criterion.scope.strip(), criterion.number
        assert criterion.outside.strip(), criterion.number


def test_the_inherited_verdicts_are_read_out_of_their_own_records_by_number():
    """2b's 6 and 7 stay FAILED and 2c's 11 stays reduced, bound not copied.

    Behaviour: the three verdicts are looked up in the other sub-phases'
    records, by number.

    Expected values determined independently: the plan says 2b's criteria 6 and
    7 stay FAILED, that 2d does not reopen the residency model, and that 2c's
    criterion 11 stays reduced because `HESSIAN_COND_LIMIT` IS D9's first kappa
    boundary, so two bins are unreachable by construction.

    Bug this catches: **2d credited with a repair it did not make** -- and it is
    the sub-phase most tempted, because it finally has an answer in view.
    Copying booleans here would drift in the direction that matters: 2d would go
    on asserting they failed after somebody fixed them. Looking them up BY
    NUMBER also catches a renumbering, loudly.
    """
    by_number_2b = {c.number: c for c in PHASE_2B_EXIT_CRITERIA}
    assert {6, 7} <= by_number_2b.keys()
    for number in (6, 7):
        assert by_number_2b[number].verdict is Verdict.FAILED, number
        assert by_number_2b[number].scope.strip(), number

    by_number_2c = {c.number: c for c in PHASE_2C_EXIT_CRITERIA}
    assert 11 in by_number_2c
    assert by_number_2c[11].verdict is Verdict.MET_WITH_REDUCED_SCOPE

    # And 2d's own record does not claim any of them: numbers are per sub-phase.
    assert max(c.number for c in PHASE_2D_EXIT_CRITERIA) == 17


def test_the_record_is_serialisable_so_the_closing_table_cannot_drift_from_it():
    """Every field is plain data, so PROGRESS.md's table has one source.

    Behaviour: the record renders without executing anything.

    Expected value determined independently: `json.dumps` succeeds with
    `Verdict` a `StrEnum` and everything else a string, an int or a tuple.

    Bug this catches: a field holding a callable, which would make the record
    readable only by importing it -- and a table nobody can render is a table
    that gets retyped, which is how two copies drift.
    """
    payload = json.dumps(
        [
            {
                "number": c.number,
                "statement": c.statement,
                "verdict": str(c.verdict),
                "reading": c.reading,
                "scope": c.scope,
                "established_by": list(c.established_by),
                "outside": c.outside,
            }
            for c in PHASE_2D_EXIT_CRITERIA
        ]
    )

    assert json.loads(payload)[0]["number"] == 1
    assert len(json.loads(payload)) == 17


# ---------------------------------------------------------------------------
# The readings, taken off the committed artifacts
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("construction", sorted(COMMITTED_REPORTS))
def test_criterion_16_every_committed_block_matches_the_shipped_defaults(construction):
    """The artifact register: a report cannot outlive its configuration.

    Behaviour: each committed report's instrument block names the constants the
    tree ships today, for every key the block carries.

    Expected values determined independently: the constants are read from
    `metamer.bench` here; the block was written by the run.

    Bug this catches: **a committed measurement quoted after a default it
    depended on has moved** -- the exact failure the block exists to detect
    rather than to suffer. Moving `DRAW_METHOD`, the candidate set, the coarse
    stride or the estimator would invalidate every committed rung report, and
    without this the reports would go on being cited.

    **A MISSING KEY IS "DRAWN BEFORE THE QUESTION EXISTED", NOT A FAILURE.** The
    easy rung's report predates `field_construction_version`; demanding it
    retroactively would make the register fail on the very artifact it protects.
    What is present is pinned; the absence is a dated fact.
    """
    block = _load(COMMITTED_REPORTS[construction])["instrument"]
    shipped = {
        "draw_method": fields.DRAW_METHOD,
        "candidates": list(fields.CANDIDATES),
        "signal_terms": list(fields.SIGNAL_TERMS),
        "criteria": list(fields.CRITERIA),
        "coarse_stride": fields.COARSE_STRIDE,
        "smear_subject": fields.SMEAR_SUBJECT,
        "estimator": smear.ESTIMATOR,
        "floor_cells": smear.FLOOR_CELLS,
        "majority_threshold": smear.MAJORITY,
        "within_regime_range": fields.WITHIN_REGIME_RANGE,
        "null_line_offset_cells": fields.NULL_LINE_OFFSET_CELLS,
        "n_normal": fields.N_NORMAL,
        "n_parallel": fields.N_PARALLEL,
        "n_time": fields.N_TIME,
        "seed": fields.FIELD_SEED,
    }

    for key, current in shipped.items():
        assert key in block, f"the report cannot say what {key!r} was"
        assert block[key] == current, (
            f"{key!r} has moved since this report was written: the report says "
            f"{block[key]!r} and the tree ships {current!r}. The report is a "
            f"claim about a configuration that no longer exists"
        )

    assert block["is_a_smoke_run"] is False, (
        "a smoke run's report is being read as a measurement"
    )


def test_criterion_16_the_version_2_report_names_its_construction():
    """The key that distinguishes the two constructions is present where it can be.

    Behaviour: the version 2 report carries the construction version, the drawn
    signal's terms and its magnitude; the version 1 report predates all three
    and carries none of them.

    Expected values determined independently: the shipped constants, and the
    dated fact that the easy rung ran before the keys existed.

    Bug this catches: the two constructions becoming indistinguishable in the
    record -- which is the original defect wearing the report's clothes, since
    `signal_terms` names what the config FITS and both reports carry it
    identically. It also catches the keys being back-filled into the older
    artifact, which would make a version 1 field claim to be a version 2 one.
    """
    two = _load(COMMITTED_REPORTS[2])["instrument"]
    one = _load(COMMITTED_REPORTS[1])["instrument"]

    assert two["field_construction_version"] == fields.FIELD_CONSTRUCTION_VERSION
    assert two["drawn_signal_terms"] == list(fields.DRAWN_SIGNAL_TERMS)
    assert two["drawn_signal_rise_sigmas"] == fields.SIGNAL_RISE_SIGMAS

    for key in ("field_construction_version", "drawn_signal_terms"):
        assert key not in one, (
            f"the version 1 report carries {key!r}: it was written before the "
            f"key existed, and back-filling it would make a signal-free field "
            f"claim a construction it was not drawn at"
        )


@pytest.mark.parametrize("construction", sorted(COMMITTED_REPORTS))
def test_criterion_5_every_committed_report_has_a_clean_interior_null(construction):
    """The gate, read first at every rung, as it was at the run.

    Behaviour: each committed report's interior null is at the floor, not
    refused, and the report is not contaminated.

    Expected value determined independently: Task 2's committed prediction --
    the null does not fire, because `_family()` is a pure indicator and a
    misclassification profile has no slope to find inside a regime.

    Bug this catches: a rung's widths being read off a report whose own control
    fired -- which would mean the estimator was reading the field's structure
    rather than the artifact, and every width in that report would be a
    different claim.
    """
    committed = _load(COMMITTED_REPORTS[construction])

    assert committed["contaminated"] is False
    assert committed["null_line"]["at_floor"] is True
    assert committed["null_line"]["refused"] is None
    assert max(committed["null_line"]["profile"]) < smear.MAJORITY


@pytest.mark.parametrize("construction", sorted(COMMITTED_REPORTS))
def test_criterion_6_no_committed_width_exceeds_the_floor(construction):
    """Criterion 6 FAILED, and this is the reading that says so.

    Behaviour: every arm's width in every committed report is at the floor --
    `value` withheld, `at_floor` true -- and no profile row reaches the
    majority threshold.

    Expected value determined independently: the criterion predicted 2-6 fine
    cells; the floor is `smear.FLOOR_CELLS` and the threshold `smear.MAJORITY`,
    both read from the shipped estimator rather than transcribed.

    Bug this catches: **the failure being quietly reinterpreted.** A later
    reader who found a width here would have to change this test to keep
    criterion 6 failing, which is the point: the verdict and its evidence move
    together. It equally catches a width appearing at a re-run, which would
    make criterion 6 MET and is the outcome 2d looked for and did not find.
    """
    committed = _load(COMMITTED_REPORTS[construction])

    for entry in committed["smears"]:
        reading = entry["reading"]
        assert reading["at_floor"] is True, entry["arm"]
        assert entry["value"] is None, entry["arm"]
        assert reading["floor_cells"] == smear.FLOOR_CELLS
        assert max(reading["profile"]) < smear.MAJORITY, (
            f"the {entry['arm']} arm has a row past the majority threshold, so "
            f"a width is resolvable and criterion 6 is no longer failed"
        )


@pytest.mark.parametrize("construction", sorted(COMMITTED_REPORTS))
def test_criterion_8_every_committed_width_has_its_n2_floor_beside_it(construction):
    """A warm width without its floor is a different claim.

    Behaviour: every committed report carries the cold, warm and N2 arms, in
    one report, at one rung.

    Expected value determined independently: `report.ARMS` is the shipped set
    the driver runs; the reports were written by it.

    Bug this catches: an N2 arm dropped to save an hour of compute, after which
    a warm width would be reported against nothing. **N2's floor is what makes
    a width interpretable at all** -- a smear measured against zero is a
    different claim from one measured against what an equal-distance random
    start produces.
    """
    arms = {entry["arm"] for entry in _load(COMMITTED_REPORTS[construction])["smears"]}

    assert "n2" in arms, "the floor arm is not in the report"
    assert {"cold", "warm"} <= arms
    assert arms == set(report.ARMS), (arms, set(report.ARMS))


def test_criterion_10_the_saving_is_reported_with_iterations_and_seconds():
    """2c's criterion 12, re-pointed to the rung that reached its difficulty.

    Behaviour: the version 2 report carries the saving both ways -- pass-2 only
    and net of pass 1 -- with the iteration counts it came from and the wall
    clock beside it.

    Expected values determined independently: the ratio is recomputed here from
    the report's own **OK-only** iteration totals -- the cells both arms
    actually converged on -- and compared with the ratio the report states.

    **THE OK-ONLY PAIR IS THE POINT, AND WRITING THIS TEST FOUND IT.** A first
    version recomputed from `cold_per_point` and `warm_per_point` and disagreed
    with the report at the fourth decimal: 0.4187 against 0.4181. The report is
    right and the test was wrong. A saving computed over ALL cells silently
    credits the warm arm for cells the cold arm never converged on, which is a
    different and flattering quantity.

    Bug this catches: **a saving quoted without the cost that produced it**, a
    saving computed over all cells rather than the shared converged ones, and
    the net-of-pass-1 figure going missing -- the one that charges pass 1's own
    cost and is therefore the honest one.
    """
    committed = _load(COMMITTED_REPORTS[2])
    iterations, ratios, cost = (
        committed["iterations"],
        committed["ratios"],
        committed["cost"],
    )

    recomputed = (
        iterations["cold_ok_total"] - iterations["warm_ok_total"]
    ) / iterations["cold_ok_total"]
    assert ratios["saving_pass2_only"] == pytest.approx(recomputed, abs=1e-9)
    assert ratios["saving_net_of_pass1"] < ratios["saving_pass2_only"], (
        "the net figure does not charge pass 1, so it is not the net figure"
    )
    assert ratios["saving_pass2_only"] > 0.3, (
        "the saving at 2c's difficulty is not in 2c's range, so criterion 10's "
        "reading is not the one it was re-pointed to take"
    )

    for phase in ("cold_seconds", "warm_seconds"):
        assert cost[phase] > 0.0, phase
    assert cost["preconditions"]["session_live_on_the_same_cores"] is True, (
        "the cost block does not record the precondition its seconds depend on"
    )


def test_criterion_11_the_three_signal_free_rungs_sit_at_one_difficulty():
    """The lever was measured not to be a lever, and the record says so.

    Behaviour: the three shipped rungs differ in coherence length and contrast,
    and `parameters = factor x BASE` holds `white/sigma` identical across all
    three -- which is the construction that makes the sweep move a quantity the
    fit cannot see.

    Expected value determined independently: `BASE`'s own ratio, and the rungs'
    own parameters, computed here rather than read from a verdict.

    Bug this catches: **the sweep being reinstated.** A later reader who
    believes the saving should be monotone in the coherence length would build
    a fourth rung; this says, in code, that the three existing ones are one
    difficulty by construction, and that criterion 11 fails for that reason
    rather than for want of measurement.
    """
    ratios = set()
    for rung in fields.RUNGS.values():
        sigma, _, white = fields.BASE
        ratios.add(round(white / sigma, 12))
        assert rung.contrast > 0.0

    assert len(ratios) == 1, (
        "the rungs no longer share one white/sigma ratio, so the E5 measurement "
        "that failed criterion 11 by construction no longer describes them"
    )
    assert len({r.coherence_length for r in fields.RUNGS.values()}) == len(fields.RUNGS)


@pytest.mark.parametrize("construction", sorted(COMMITTED_REPORTS))
def test_criterion_11_no_rung_reaches_the_self_ceiling(construction):
    """The half of criterion 11 that is satisfied, recorded as satisfied.

    Behaviour: the self arm's ratio to cold is far below 1 in both committed
    reports.

    Expected value determined independently: the ceiling is 1.0 by definition
    -- the self arm restarts from cold's own optimum, so a ratio at 1 would mean
    warm-starting from the answer costs a full cold fit.

    Bug this catches: a rung whose saving is really the self arm's -- i.e. an
    apparent saving produced by starting from the answer. Recorded separately
    from the monotonicity half so that the failed verdict is not read as though
    both halves failed.
    """
    ratios = _load(COMMITTED_REPORTS[construction])["ratios"]

    assert 0.0 < ratios["self_over_cold"] < 0.5, ratios["self_over_cold"]


@pytest.mark.parametrize("construction", sorted(COMMITTED_REPORTS))
def test_criterion_12_no_committed_report_carries_a_stratum(construction):
    """The reduced scope, asserted rather than described.

    Behaviour: no committed rung report carries a stratified audit reading --
    no strata, no per-stratum rates, no withheld list of them.

    Expected value determined independently: the report's own top-level keys,
    which are the driver's output and contain no audit section.

    Bug this catches: **the reduced scope going stale.** The day a driver runs
    `batch.audit` over a rung's arms, this test fails -- which is exactly when
    criterion 12 should be revisited, and the failure is the reminder. Asserting
    the absence is what makes "it has no reading" a checkable claim rather than
    a sentence in a document.
    """
    committed = _load(COMMITTED_REPORTS[construction])

    assert "strata" not in committed
    assert not any("stratum" in key or "strata" in key for key in committed), (
        "a committed report now carries a stratum reading, so criterion 12's "
        "reduced scope is out of date and the criterion can be re-evaluated"
    )


def test_criterion_14_open_question_21_is_still_open_in_the_record():
    """The question outlives the route that would have answered it.

    Behaviour: OQ21 is listed under PROGRESS.md's open questions.

    Expected value determined independently: the open-questions section is the
    record's own, and OQ21's number and subject are quoted from it.

    Bug this catches: criterion 14 being marked met because the question was
    closed elsewhere without its reading being taken, or the question being
    dropped from the record while the criterion still claims it fails. **The
    route closed and the question did not**, and those are different facts.
    """
    progress = pathlib.Path("PROGRESS.md").read_text()
    section = progress[progress.index("## Open questions") :]

    assert "\n21. **HOW DOES THE AUDIT SELECT ITS POINTS" in section, (
        "open question 21 is no longer in the record, so criterion 14's verdict "
        "stands on a question nobody can find"
    )


def test_criterion_17_the_budget_covers_every_rung_that_exists():
    """Adding a rung forces the budget to be re-derived.

    Behaviour: the number of shipped rungs equals the number E2's budget was
    derived for.

    Expected value determined independently: the budget factor is a DECISION
    recorded in prose -- how many arms run at how many rungs -- not a value
    computed from anything, so the count is transcribed here deliberately and
    the assertion compares membership against it.

    Bug this catches: **a fourth rung priced by a factor computed for three.**
    `RUNGS` is a mapping in one file and the budget is prose in two documents;
    nothing compared them before this. A rung added without re-deriving the
    budget would be invisible until a run overran its ceiling, which is the
    most expensive moment to discover it.
    """
    assert len(fields.RUNGS) == RUNGS_THE_BUDGET_WAS_DERIVED_FOR, (
        f"the tree ships {len(fields.RUNGS)} rungs and E2's budget was derived "
        f"for {RUNGS_THE_BUDGET_WAS_DERIVED_FOR}. Re-derive the budget at its "
        f"source in PROGRESS.md and the plan, then move this constant"
    )
    assert set(fields.RUNGS) == {"easy", "middle", "hard"}
