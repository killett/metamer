"""Phase 2d's seventeen exit criteria, as values, with their verdicts and readings.

**THE SHAPE IS 2b's AND 2c's, AND THE VOCABULARY IS IMPORTED RATHER THAN
RESPELLED.** `ExitCriterion` and `Verdict` come from `tests.exit_criteria_2b`;
a second definition of *"what a criterion is"* would disagree the first time
either grew a field.

**`Verdict` IS NOT EXTENDED, AND THAT IS A DECISION.** Two of 2d's criteria fail
**by construction** rather than by measurement, and a fourth enum member would
have said so more directly -- at the cost of **reinterpreting** 2b's and 2c's
records, whose three-valued verdicts would become a subset of a four-valued
vocabulary they were never written against. **Distinguish, never reinterpret**:
the same argument that made the drawn signal a NEW instrument key rather than a
redefinition of `signal_terms`. The scope string is required for every non-MET
verdict already, so the distinction lives there and costs nothing.

**EVERY CRITERION NAMES A READING AND THERE IS NO EXEMPT LIST** -- the third
(c5) instance in 2d. An exempt list is an enumeration of the members that
existed when it was written, so a criterion added later would be exempt by
default.

**THE INHERITED VERDICTS ARE NOT COPIED HERE.** 2b's criteria 6 and 7 stay
FAILED and 2c's criterion 11 stays reduced scope; `test_exit_criteria_2d.py`
reads all three **out of their own records, by number**. That makes the
restraint structural rather than a resolution -- and 2d is the sub-phase most
tempted, because it finally has an answer in view.

**IT IS NOT THE CLOSE.** The closing table with its reasoning is in
`PROGRESS.md`. What is here is the part a test can hold.
"""

from __future__ import annotations

from tests.exit_criteria_2b import ExitCriterion, Verdict

#: The readings a 2d criterion may be stated against, and the whole vocabulary.
#: Closed on purpose: a verdict quoting a reading no harness can take is a
#: verdict about nothing.
READINGS = (
    "the truth array, both lines",
    "the coherence length of the true parameters, not of the fits",
    "the exit code, and the fitted point count",
    "the width in fine cells, both sides",
    "the null reading on each committed report, and the withheld list",
    "the width, against its stated floor",
    "the width against spiral_bound x coarse_stride, read from config",
    "both numbers in one report, per rung",
    "the per-cell value under one seed",
    "iterations and wall clock, both named",
    "the per-rung saving, against the ceiling figure",
    "the report's own withheld list",
    "the construction, both directions",
    "the coefficient, and the name recorded before it",
    "the README's own text",
    "the report's instrument block against the shipped defaults",
    "the recorded count, and the factor it selected",
)

#: A criterion about the shape of code, not about a measured quantity, has no
#: outside to be driven from and says so.
NO_OUTSIDE = (
    "none exists: this is a claim about code shape, falsifiable by reading and "
    "by construction, and the tests construct rather than inspect"
)

#: The committed reports are the outside for every benchmark criterion. **A
#: 15-hour measurement cannot be a test and its recorded output can.**
THE_REPORTS = (
    "the committed rung reports, which are artifacts in the tree and are read "
    "by the suite rather than recomputed"
)

PHASE_2D_EXIT_CRITERIA: tuple[ExitCriterion, ...] = (
    ExitCriterion(
        number=1,
        statement=(
            "The true parameter field's step occupies exactly one cell, and an "
            "interior line has no transition"
        ),
        verdict=Verdict.MET,
        reading="the truth array, both lines",
        scope="",
        established_by=(
            "test_the_truth_jumps_at_the_boundary_and_the_jump_dominates_every_other",
            "test_an_interior_line_away_from_the_boundary_has_no_transition",
        ),
        outside=NO_OUTSIDE,
    ),
    ExitCriterion(
        number=2,
        statement="The builder's coherence length is recoverable from the truth it generates",
        verdict=Verdict.MET,
        reading="the coherence length of the true parameters, not of the fits",
        scope="",
        established_by=(
            "test_the_coherence_length_orders_the_spatial_autocorrelation",
        ),
        outside=NO_OUTSIDE,
    ),
    ExitCriterion(
        number=3,
        statement=(
            "The benchmark field opens through the shipped opener and every point fits"
        ),
        verdict=Verdict.MET,
        reading="the exit code, and the fitted point count",
        scope="",
        established_by=(
            "test_the_field_opens_through_the_shipped_opener_and_fits_every_point",
        ),
        outside="the shipped opener and stage 4a, driven as a run rather than as a call",
    ),
    ExitCriterion(
        number=4,
        statement=(
            "The estimator returns <= 1 cell on a step and 5 cells on a "
            "constructed 5-cell transition"
        ),
        verdict=Verdict.MET,
        reading="the width in fine cells, both sides",
        scope="",
        established_by=(
            "test_a_one_cell_band_is_reported_as_the_floor_and_never_as_the_number_one",
            "test_a_constructed_five_cell_band_at_the_boundary_measures_five_cells",
        ),
        outside=NO_OUTSIDE,
    ),
    ExitCriterion(
        number=5,
        statement=(
            "The interior null returns <= 1 cell at every rung, and a "
            "contaminated rung withholds visibly"
        ),
        verdict=Verdict.MET,
        reading="the null reading on each committed report, and the withheld list",
        scope="",
        established_by=(
            "test_the_interior_null_returns_the_floor_on_a_map_whose_only_band_is_at_the_boundary",
            "test_a_null_that_returns_a_width_contaminates_the_rung_and_stops_it",
            "test_criterion_5_every_committed_report_has_a_clean_interior_null",
        ),
        outside=THE_REPORTS,
    ),
    ExitCriterion(
        number=6,
        statement="The smear width at the easy rung exceeds the 1-cell floor",
        verdict=Verdict.FAILED,
        reading="the width, against its stated floor",
        scope=(
            "FAILED ON ITS OWN TERMS, AND THE CRITERION DID ITS JOB. The width was "
            "predicted at 2-6 fine cells and came back AT THE 1-CELL FLOOR -- "
            "refuted from below -- on every arm and at BOTH field constructions, "
            "on a field where the mechanism ran to completion with every point "
            "warm-started. It is not reinterpreted, because reinterpreting it "
            "would delete the finding: at 2c's own difficulty a 42% saving moves "
            "no selected candidate. What would close it is an artifact appearing "
            "somewhere -- a rung, a construction or a real field where warm and "
            "cold disagree -- and 2d looked in the two places it could."
        ),
        established_by=("test_criterion_6_no_committed_width_exceeds_the_floor",),
        outside=THE_REPORTS,
    ),
    ExitCriterion(
        number=7,
        statement="No width exceeds the spiral reach, and a width above it is refused",
        verdict=Verdict.MET,
        reading="the width against spiral_bound x coarse_stride, read from config",
        scope="",
        established_by=(
            "test_the_spiral_reach_is_computed_from_the_shipped_warm_start_defaults",
            "test_a_changed_spiral_bound_moves_the_reach_and_the_refusal_with_it",
        ),
        outside=NO_OUTSIDE,
    ),
    ExitCriterion(
        number=8,
        statement=(
            "Every smear width is reported beside the width N2 produces at the same rung"
        ),
        verdict=Verdict.MET,
        reading="both numbers in one report, per rung",
        scope="",
        established_by=(
            "test_criterion_8_every_committed_width_has_its_n2_floor_beside_it",
        ),
        outside=THE_REPORTS,
    ),
    ExitCriterion(
        number=9,
        statement="The N2 map and the audit's N2 arm agree at every shared point",
        verdict=Verdict.MET,
        reading="the per-cell value under one seed",
        scope="",
        established_by=(
            "test_the_maps_value_at_a_point_is_run_arms_own_n2_selection_there",
            "test_the_n2_map_is_the_field_arms_reduction_and_not_a_second_one",
        ),
        outside=NO_OUTSIDE,
    ),
    ExitCriterion(
        number=10,
        statement=(
            "The warm-start saving at N = 630 through the shipped mechanism -- "
            "2c's criterion 12"
        ),
        verdict=Verdict.MET,
        reading="iterations and wall clock, both named",
        scope=(
            "RE-POINTED 2026-09-06. As written it named the plausibility rung, "
            "and Task 6 was decided against, so that rung does not exist. The "
            "reading is taken at the field construction 2 rung, which is where "
            "2c's difficulty was reached: 41.81% of pass-2 iterations, 39.75% "
            "net of pass 1, against 2c's 42.28%, with the wall clock beside it "
            "and its preconditions marked. The criterion is MET at a rung the "
            "plan did not name rather than unevaluated at one it did."
        ),
        established_by=(
            "test_criterion_10_the_saving_is_reported_with_iterations_and_seconds",
        ),
        outside=THE_REPORTS,
    ),
    ExitCriterion(
        number=11,
        statement=(
            "The saving is monotone in the coherence length, and no rung reaches "
            "the self ceiling"
        ),
        verdict=Verdict.FAILED,
        reading="the per-rung saving, against the ceiling figure",
        scope=(
            "FAILED BY CONSTRUCTION, FOR TWO SEPARATE REASONS, AND NOT QUIETLY "
            "DROPPED. (a) THE LEVER IS NOT A LEVER: `parameters = factor x BASE` "
            "holds white/sigma constant on every rung and amplitude is free under "
            "a concentrated likelihood, so the sweep moved a quantity the fit "
            "cannot see -- measured at E5, and the three rungs cost 24.375 / "
            "24.333 / 24.396 iterations per point. A criterion asserting a "
            "relationship the project has since shown CANNOT EXIST is a finding "
            "about the plan. (b) ONE RUNG EVER PRODUCED A SAVING, so monotonicity "
            "has a single point to be monotone through. The self-ceiling half is "
            "separately satisfied -- self/cold is 0.053 at the version 2 rung and "
            "0.089 at the signal-free one, both far below 1 -- but a criterion is "
            "not half met. Recorded here so a later reader meets the measurement "
            "instead of reinstating the sweep."
        ),
        established_by=(
            "test_criterion_11_the_three_signal_free_rungs_sit_at_one_difficulty",
            "test_criterion_11_no_rung_reaches_the_self_ceiling",
        ),
        outside=THE_REPORTS,
    ),
    ExitCriterion(
        number=12,
        statement=(
            "Every audit point stratum reports a rate, or its member count with the reason"
        ),
        verdict=Verdict.MET_WITH_REDUCED_SCOPE,
        reading="the report's own withheld list",
        scope=(
            "IT HAS NO READING AT ALL, AND THAT IS THE STANDING STATE RATHER THAN "
            "A 2d SHORTFALL. The rung report carries checks, ratios, smears, the "
            "null line, iterations and cost -- and NO STRATA. The stratified "
            "report, its withholding rules, its 30-member floor and its "
            "per-stratum-only output are 2c's `batch.audit` machinery, and the 2d "
            "driver never invoked them. SO THE STRATA REMAIN UNEXERCISED ON REAL "
            "OUTPUT AFTER TWO SUB-PHASES: 2c built them and measured nothing with "
            "them; 2d measured something and did not run them. What closes it is "
            "a driver that runs `batch.audit` over a rung's arms -- a small piece "
            "of wiring against a large piece of already-built machinery."
        ),
        established_by=("test_criterion_12_no_committed_report_carries_a_stratum",),
        outside=THE_REPORTS,
    ),
    ExitCriterion(
        number=13,
        statement="A number without a rung cannot be constructed",
        verdict=Verdict.MET,
        reading="the construction, both directions",
        scope="",
        established_by=(
            "test_a_quantity_without_a_rung_cannot_be_constructed",
            "test_every_quantity_on_a_report_carries_the_rung_it_was_measured_on",
        ),
        outside=NO_OUTSIDE,
    ),
    ExitCriterion(
        number=14,
        statement=(
            "Open question 21 closes: a named pre-fit proxy's correlation with "
            "each post-fit proxy"
        ),
        verdict=Verdict.FAILED,
        reading="the coefficient, and the name recorded before it",
        scope=(
            "NOT MEASURED, AND THE ROUTE IS GONE RATHER THAN THE QUESTION. E8 had "
            "this closing as a BY-PRODUCT of the plausibility rung's stratified "
            "subsample, and Task 6 was decided against on 2026-09-01. So no proxy "
            "was named, no coefficient was taken, and OQ21 stays open WITH ITS "
            "ORIGINAL CLOSER INTACT -- the question is unchanged; only the free "
            "route to answering it is gone. Recorded FAILED rather than reduced "
            "because nothing partial was measured."
        ),
        established_by=(
            "test_criterion_14_open_question_21_is_still_open_in_the_record",
        ),
        outside=THE_REPORTS,
    ),
    ExitCriterion(
        number=15,
        statement=(
            "The README carries the smear width with its rung, its floor and the "
            "standing limitation in the caption, and names section 16.2 item 4 "
            "and Phase 6 as the reserved position's content and owner"
        ),
        verdict=Verdict.MET,
        reading="the README's own text",
        scope="",
        established_by=(
            "test_the_figure_section_names_the_field_it_was_measured_on",
            "test_the_caption_carries_the_standing_limitation_and_names_its_closer",
            "test_the_reserved_position_names_its_content_and_its_owner",
        ),
        outside="the README as committed, read as text rather than rendered",
    ),
    ExitCriterion(
        number=16,
        statement="The committed reports name an instrument matching the current defaults",
        verdict=Verdict.MET,
        reading="the report's instrument block against the shipped defaults",
        scope="",
        established_by=(
            "test_criterion_16_every_committed_block_matches_the_shipped_defaults",
        ),
        outside=THE_REPORTS,
    ),
    ExitCriterion(
        number=17,
        statement=(
            "The benchmark field's iteration count per point is recorded, and "
            "E2's budget was finalised against it before any rung ran"
        ),
        verdict=Verdict.MET,
        reading="the recorded count, and the factor it selected",
        scope="",
        established_by=(
            "test_the_iteration_reading_reads_a_real_store",
            "test_criterion_17_the_budget_covers_every_rung_that_exists",
        ),
        outside=THE_REPORTS,
    ),
)
