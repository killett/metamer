"""Phase 2e's nineteen exit criteria, as values, with their verdicts and readings.

**THE SHAPE IS 2b's, 2c's AND 2d's, AND THE VOCABULARY IS IMPORTED RATHER THAN
RESPELLED.** `ExitCriterion` and `Verdict` come from `tests.exit_criteria_2b`;
a second definition of *"what a criterion is"* would disagree the first time
either grew a field. **`Verdict` is not extended** -- 2d's decision, for 2d's
reason: a fourth member would reinterpret three records that were written
against three values. A criterion that failed by construction says so in its
scope string, and no 2e criterion did.

**EVERY CRITERION NAMES A READING AND THERE IS NO EXEMPT LIST** -- the plan's
own third column, verbatim enough to be checked against it. An exempt list is
(c5): an enumeration of the members that existed when it was written.

**THE INHERITED VERDICTS ARE NOT COPIED HERE.** 2b's criteria 6 and 7 stay
FAILED; 2c's 11 stays reduced; 2d's 6, 11 and 14 stay FAILED and its 12 stays
reduced. `tests/test_exit_criteria_2e.py` reads all seven **out of their own
records, by number**, so the restraint is structural -- 2e reopens no residency
model, re-cuts no boundary, and re-runs no rung.

**ONE CRITERION IS REDUCED, AND THE REDUCTION IS THE SECTION BOUNDARY.**
Criterion 14's subject is a ROW of section 14.2's report, and section 14.2 is
2f's -- the plan's own opening sentence draws that line as section 17's
measure/print rule and not as a scoping preference. What 2e establishes is
that the row's denominator is DEFINED and COMPUTABLE from the stores a
two-pass run leaves; what it does not establish is a row, because none is
printed yet.

**THE NINETEENTH IS THE NO-EVIDENCE DECISION, AND WHY IT IS NINETEENTH RATHER
THAN FOLDED INTO AN EXISTING ONE IS RECORDED HERE.** The eighteen were approved
as a set on 2026-09-12, before the question existed, and a criterion added by
the implementer during the close reads as scope drift unless the addition is a
decision. This one was -- taken by Dr. Twinklebrane on 2026-09-18, after the
suite was first written without it and the omission stated. Three properties
make it criterion-shaped: it was taken on evidence (2c's criterion 1 proving
the coarse sample can be empty while the grid holds data); it changed shipped
behaviour (abort -> continue loudly); and it has a reading no other criterion
covers -- the run continues to pass 2, the final line names the verdict, and
**the exit code is 0**. That last reading is the load-bearing one: it is the
only place where *"continued because there was nothing to judge"* and
*"continued because everything passed"* are asserted to produce the SAME code
for DIFFERENT reasons, which is a claim about the exit vocabulary rather than
about the mechanism.

**IT IS NOT THE CLOSE.** The closing table with its reasoning is in
`PROGRESS.md`. What is here is the part a test can hold.
"""

from __future__ import annotations

from tests.exit_criteria_2b import ExitCriterion, Verdict

#: The readings a 2e criterion may be stated against, and the whole vocabulary.
#: Closed on purpose: a verdict quoting a reading no test can take is a verdict
#: about nothing.
READINGS = (
    "the exit code, and the fitted point count",
    "the enumeration of sites, by function and by occurrence",
    "spatial_coordinates' keys for a lat/lon store, against the file",
    "the two numbers, same store, two namings",
    "the exit code and the traceback's presence",
    "the enumerated member list, by name and value",
    "the dated provenance at the test",
    "both properties, enumerated",
    "the `outcome_counts` histograms under `notes/*.json` — 8 of the 16 committed, the rest checked independently at 2f",
    "the construction, both directions",
    "the verdict on a constructed pass-1 store, with no run",
    "the same store, cropped to its ocean",
    "the store's outcome array for that candidate",
    "the row, and the denominator beside it",
    "the two stores, byte-for-byte",
    "both exit codes, in one test",
    "the inversion of Task 1's unreachability test, both directions",
    "the run's behaviour, and the design doc's own sentence",
    "the pass-2 store, the final line and the exit code -- 0 for a different reason than a clean pass",
)

#: A criterion about the shape of code has no outside to be driven from and
#: says so -- 2b's constant, 2b's reason.
NO_OUTSIDE = (
    "none exists: this is a claim about code shape, falsifiable by reading and "
    "by enumeration. A subprocess around the same call is the same derivation "
    "in a second interpreter"
)

#: The exit code is a property of a PROCESS, so every criterion about one is
#: driven from `python -m metamer` or an injected entry point in a subprocess.
A_PROCESS = (
    "a subprocess: the exit code and stderr, which is what a user gets and what "
    "a resuming script branches on"
)

PHASE_2E_EXIT_CRITERIA: tuple[ExitCriterion, ...] = (
    ExitCriterion(
        number=1,
        statement=(
            "A `latitude`/`longitude` store runs end to end through the shipped "
            "entry point"
        ),
        verdict=Verdict.MET,
        reading="the exit code, and the fitted point count",
        scope="",
        established_by=(
            "test_criterion_1_a_latlon_store_exits_ok_and_every_point_is_fitted",
            "test_a_renamed_store_produces_the_same_fits_and_a_different_fingerprint",
        ),
        outside=(
            "`python -m metamer` in a subprocess on a lat/lon store, and the "
            "output store's outcome array read back off disk"
        ),
    ),
    ExitCriterion(
        number=2,
        statement=(
            "No literal input dimension name outside `time` remains in the tiling path"
        ),
        verdict=Verdict.MET,
        reading="the enumeration of sites, by function and by occurrence",
        scope="",
        established_by=(
            "test_the_tiling_path_addresses_its_spatial_axes_by_position",
            "test_the_enumerator_reads_the_source_it_is_given",
            "test_the_decimation_is_positional_and_stays_positional",
        ),
        outside=NO_OUTSIDE,
    ),
    ExitCriterion(
        number=3,
        statement="The geometry fingerprint records the input's own dimension names",
        verdict=Verdict.MET,
        reading="spatial_coordinates' keys for a lat/lon store, against the file",
        scope="",
        established_by=(
            "test_criterion_3_the_fingerprint_keys_a_latlon_store_by_its_own_names",
            "test_a_renamed_store_produces_the_same_fits_and_a_different_fingerprint",
        ),
        outside=(
            "the `geometry_components` attr read off a store written by a "
            "subprocess, compared against the coordinates in the input file"
        ),
    ),
    ExitCriterion(
        number=4,
        statement="Read amplification is invariant under renaming the spatial axes",
        verdict=Verdict.MET,
        reading="the two numbers, same store, two namings",
        scope="",
        established_by=(
            "test_criterion_4_read_amplification_is_one_number_under_two_namings",
            "test_a_straddling_tile_reports_the_amplification_it_causes",
        ),
        outside=(
            "two zarr files on disk with the same data, chunking and tile, "
            "differing only in what the spatial axes are called"
        ),
    ),
    ExitCriterion(
        number=5,
        statement="An unhandled exception exits `INTERNAL_ERROR`, with its traceback",
        verdict=Verdict.MET,
        reading="the exit code and the traceback's presence",
        scope="",
        established_by=(
            "test_an_unhandled_exception_exits_internal_error_and_keeps_its_traceback",
            "test_a_crash_after_the_run_succeeds_also_exits_internal_error",
            "test_the_staged_codes_still_win_over_the_catch_all",
        ),
        outside=A_PROCESS,
    ),
    ExitCriterion(
        number=6,
        statement="The six exit codes are the six the taxonomy names",
        verdict=Verdict.MET,
        reading="the enumerated member list, by name and value",
        scope="",
        established_by=("test_the_six_exit_codes_are_the_six_the_taxonomy_names",),
        outside=NO_OUTSIDE,
    ),
    ExitCriterion(
        number=7,
        statement=(
            "`INTERNAL_ERROR`'s guard names the live producer it was verified against"
        ),
        verdict=Verdict.MET,
        reading="the dated provenance at the test",
        scope="",
        established_by=(
            "test_criterion_7_the_internal_error_guard_carries_its_dated_live_producer",
            "test_an_unhandled_exception_exits_internal_error_and_keeps_its_traceback",
        ),
        outside=(
            "the test file's own text, parsed rather than imported: the provenance "
            "is a docstring, and a docstring is an artifact on disk"
        ),
    ),
    ExitCriterion(
        number=8,
        statement=(
            "`CANDIDATE_DROPPED` is outside the failure rate and inside the "
            "eligible denominator"
        ),
        verdict=Verdict.MET,
        reading="both properties, enumerated",
        scope="",
        # THE FIRST NAME MOVED ON 2026-09-19 AND THE VERDICT DID NOT. 2f's
        # gate repair added a third property, `Outcome.is_fit_verdict`, to the
        # one-table test, and a count in a name is renamed rather than edited
        # -- so `..._by_both_properties_...` became
        # `..._by_all_three_properties_...`. **Criterion 8's reading stays "both
        # properties, enumerated"**, because that is what 2e read and a later
        # sub-phase adding a column does not retroactively widen a met
        # criterion. This edit keeps the name pointing at evidence that exists;
        # it is not a re-reading.
        established_by=(
            "test_every_member_is_classified_by_all_three_properties_in_one_table",
            "test_the_three_deferred_outcomes_are_skips_and_not_failures",
            "test_a_dropped_candidate_is_outside_the_failure_rate_and_inside_the_denominator",
        ),
        outside=NO_OUTSIDE,
    ),
    ExitCriterion(
        number=9,
        statement="No committed audit number moves under the reclassification",
        verdict=Verdict.MET,
        # READING CORRECTED 2026-09-20, VERDICT UNCHANGED. The helper globs
        # `notes/*.json` for the key `outcome_counts` and reaches 8 of the 16
        # committed histograms: six are spelled `counts` and two live in
        # `.jsonl`, ALL INSIDE THIS CRITERION'S OWN DECLARED `outside`. The
        # reach was found by open question 24's artifact check, which was
        # written independently BECAUSE this helper's spelling-dependence was
        # already suspected -- not by re-running this test.
        #
        # THE VERDICT STAYS MET AND IS NOT REDUCED. A reduced scope in this
        # project means a criterion achieved over a narrower SUBJECT -- 2e's
        # own 14, where the drop row was not delivered at all. This claim, "no
        # committed audit number moves", is TRUE over the full population: 2f
        # checked all sixteen on 2026-09-19 and found the member in none. The
        # defect was EVIDENTIAL REACH, not scope, and marking it reduced would
        # record the project as holding less evidence at the moment it got
        # more. The durable repair is not this note: it is 2f's criterion 5,
        # which asserts the ENUMERATION's size and so cannot silently go stale
        # as the artifact set grows -- handoff (c7).
        reading="the `outcome_counts` histograms under `notes/*.json` — 8 of the 16 committed, the rest checked independently at 2f",
        scope="",
        established_by=(
            "test_criterion_9_every_committed_histogram_recomputes_unchanged",
            "test_no_committed_report_carries_a_decided_skip",
        ),
        outside=(
            "the committed reports under `docs/superpowers/notes/`, which are "
            "artifacts in the tree and are read rather than recomputed from a run"
        ),
    ),
    ExitCriterion(
        number=10,
        statement="The counters are display-only and no decision path reaches them",
        verdict=Verdict.MET,
        reading="the construction, both directions",
        scope="",
        established_by=(
            "test_criterion_10_the_decision_path_cannot_see_the_counters_in_either_direction",
            "test_the_batch_package_never_imports_the_counters",
            "test_the_approximation_lives_in_the_counters_and_nowhere_else",
        ),
        outside=(
            "a subprocess import of the decision path, so the check measures the "
            "import graph rather than the test session"
        ),
    ),
    ExitCriterion(
        number=11,
        statement="The abort verdict is a pure function of a finished store",
        verdict=Verdict.MET,
        reading="the verdict on a constructed pass-1 store, with no run",
        scope="",
        established_by=(
            "test_one_candidate_above_the_threshold_is_dropped_under_the_drop_policy",
            "test_every_candidate_above_the_threshold_aborts_whatever_the_policy",
            "test_the_verdict_is_a_function_of_the_store_and_nothing_else",
            "test_an_incomplete_pass_one_store_is_refused",
            "test_a_second_process_reaches_the_same_verdict_on_the_same_store",
        ),
        outside=(
            "a second driver invocation over the same frozen pass-1 store, which "
            "must reach the same verdict -- purity read as resume-consistency"
        ),
    ),
    ExitCriterion(
        number=12,
        statement="The verdict is invariant to the eligible-excluded population",
        verdict=Verdict.MET,
        reading="the same store, cropped to its ocean",
        scope="",
        established_by=(
            "test_criterion_12_a_store_and_its_ocean_crop_reach_one_verdict",
            "test_ineligible_points_change_neither_numerator_nor_denominator",
        ),
        outside=(
            "two pass-1 stores written by two real decimated runs -- one over a "
            "grid whose lower half is land, one over that grid's ocean alone"
        ),
    ),
    ExitCriterion(
        number=13,
        statement=(
            "A candidate above threshold on pass 1 is dropped, and pass 2 records "
            "`CANDIDATE_DROPPED` everywhere remaining"
        ),
        verdict=Verdict.MET,
        reading="the store's outcome array for that candidate",
        scope="",
        established_by=(
            "test_a_dropped_candidate_is_dropped_everywhere_and_moves_no_hash",
            "test_a_drop_keeps_pass_one_evidence_and_records_its_rule",
            "test_the_verdict_reaches_the_process_exit_code",
        ),
        outside=(
            "the pass-2 store off disk after a real driver run, and the process "
            "exit code of the `drop` row"
        ),
    ),
    ExitCriterion(
        number=14,
        statement=(
            "The drop's reported rate names its own denominator and excludes the "
            "dropped points"
        ),
        verdict=Verdict.MET_WITH_REDUCED_SCOPE,
        reading="the row, and the denominator beside it",
        scope=(
            "THE DENOMINATOR IS ESTABLISHED AND THE ROW IS NOT, BECAUSE THE ROW IS "
            "2f's. Section 14.2's drop row -- 'points where the candidate was "
            "still live', per candidate, the first denominator in this project "
            "that differs between rows of one table -- is part of the report, and "
            "the plan's own section boundary puts the report in 2f. What 2e "
            "establishes, and the criterion test reads off the two stores: the "
            "live population IS pass 1's eligible points for that candidate; it "
            "is what the recorded verdict's `eligible` equals; and it is strictly "
            "smaller than the pass-2 population the drop wrote into, so a rate "
            "over pass 2 would report the decision (D9). No row is printed, so "
            "no row is read; the reduction closes when 2f prints one"
        ),
        established_by=(
            "test_criterion_14_the_live_denominator_is_pass_ones_and_is_computable",
            "test_a_drop_keeps_pass_one_evidence_and_records_its_rule",
        ),
        outside=(
            "the pass-1 and pass-2 stores off disk after a real driver run whose "
            "verdict carried the real rates; the ROW has no outside because it "
            "does not exist yet"
        ),
    ),
    ExitCriterion(
        number=15,
        statement="`--no-early-abort` changes the decision and not the computation",
        verdict=Verdict.MET,
        reading="the two stores, byte-for-byte",
        scope="",
        established_by=(
            "test_criterion_15_no_early_abort_and_a_continue_verdict_write_the_same_bytes",
            "test_no_early_abort_disables_a_decision_and_not_a_computation",
        ),
        outside=(
            "every file under the two output stores, compared as bytes; the one "
            "file permitted to differ is the root metadata and the one key in it "
            "is the recorded verdict"
        ),
    ),
    ExitCriterion(
        number=16,
        statement=(
            "`COMPLETED_WITH_FAILURES` and `INTERNAL_ERROR` are produced by "
            "different events"
        ),
        verdict=Verdict.MET,
        reading="both exit codes, in one test",
        scope="",
        established_by=(
            "test_criterion_16_a_thresholded_run_and_a_crashed_run_exit_different_codes",
            "test_the_verdict_reaches_the_process_exit_code",
            "test_an_unhandled_exception_exits_internal_error_and_keeps_its_traceback",
        ),
        outside=A_PROCESS,
    ),
    ExitCriterion(
        number=17,
        statement="Exit 1 is reachable, and only from the threshold path",
        verdict=Verdict.MET,
        reading="the inversion of Task 1's unreachability test, both directions",
        scope="",
        established_by=(
            "test_exit_one_comes_from_no_path_but_the_threshold",
            "test_the_verdict_reaches_the_process_exit_code",
        ),
        outside=A_PROCESS,
    ),
    ExitCriterion(
        number=18,
        statement=(
            "A one-pass run's abort behaviour is the decided one, and section 14.1 "
            "states it"
        ),
        verdict=Verdict.MET,
        reading="the run's behaviour, and the design doc's own sentence",
        scope="",
        established_by=(
            "test_criterion_18_the_design_doc_states_the_one_pass_decision_and_the_open_note_is_gone",
            "test_a_one_pass_run_has_no_verdict_and_says_so",
            "test_warm_starting_disabled_is_one_cold_pass_and_leaves_no_residue",
        ),
        outside=(
            "the design document on disk, read as text; and the one-pass store's "
            "root attrs, which record that no verdict was evaluated"
        ),
    ),
    ExitCriterion(
        number=19,
        statement=(
            "A coarse sample with no eligible point continues loudly as its own "
            "verdict, `no_evidence`, and exits 0 for a different reason than a "
            "clean pass"
        ),
        verdict=Verdict.MET,
        reading=(
            "the pass-2 store, the final line and the exit code -- 0 for a "
            "different reason than a clean pass"
        ),
        scope="",
        established_by=(
            "test_criterion_19_no_evidence_and_a_clean_pass_exit_zero_for_different_reasons",
            "test_an_empty_coarse_sample_continues_loudly_when_the_fine_grid_has_data",
            "test_a_no_evidence_run_exits_ok_with_the_headline_on_the_final_line",
            # RENAMED 2026-09-20, AND THE OLD NAME BECAME FALSE RATHER THAN
            # MERELY DATED. Open question 24 made `INSUFFICIENT_DATA` eligible,
            # so the fixture's population is no longer an "empty eligible
            # population" -- it is a fully eligible one that holds no fit. The
            # verdict is untouched; the test's SUBJECT is unchanged and its
            # name now describes it.
            "test_an_unfitted_coarse_sample_is_no_evidence_not_clean_and_not_abort",
            "test_an_empty_sample_and_an_all_failing_sample_are_different_verdicts",
        ),
        outside=(
            "two `python -m metamer` subprocesses -- one over the empty-sample "
            "fixture with the real verdict, one under an injected clean verdict "
            "-- read on their exit codes, their stderr, and the `early_abort` "
            "attrs of the two stores they wrote"
        ),
    ),
)
