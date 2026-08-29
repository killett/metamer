"""Phase 2c's twelve exit criteria, as values, with their verdicts and readings.

**THE SHAPE IS 2b's AND THE VOCABULARY IS NOT.** `ExitCriterion` and `Verdict`
are imported rather than spelled a second time -- two definitions of "what a
criterion is" would disagree the first time either grew a field. `READINGS`
below is 2c's own, because none of 2c's readings is an RSS reading, and the two
sub-phases' `established_by` sets are bound by their own binders.

**AND 2c's RULE IS STRICTLY STRONGER THAN 2b's.** 2b asserts *"a reading, or a
statement that it has none"*, and only four of its sixteen criteria were about
a measured quantity. **Every one of 2c's twelve names a reading** -- that is the
plan's stated first requirement for this task, not a stylistic note -- so the
binder asserts it for all twelve with **no exempt list.** An exempt list is
(c5): a gate written as an enumeration of the members that happened to exist
when it was written.

**THE TWO INHERITED FAILED CRITERIA ARE NOT IN THIS TUPLE.** 2b's criteria 6
and 7 stay FAILED, and `tests/test_exit_criteria_2c.py` asserts that by reading
`PHASE_2B_EXIT_CRITERIA` -- **not by copying two booleans here.** A copy drifts
silently in the direction that matters: 2c would go on asserting they failed
after somebody fixed them. It also keeps the numbering honest; **they are 2b's
6 and 7, never 2c's 13 and 14**, or a reader reconciling the two tables finds
four criteria where there are two.

**IT LIVES IN `tests/` RATHER THAN IN `src/`**, for 2b's reason: a sub-phase's
exit criteria are a property of the development process, not of the package.

**AND IT IS NOT THE REPORT.** The closing table with its reasoning is in
`PROGRESS.md`. What is here is the part a test can hold.
"""

from __future__ import annotations

from tests.exit_criteria_2b import ExitCriterion, Verdict

#: The readings a 2c criterion may be stated against, and the whole vocabulary.
#:
#: **EVERY CRITERION NAMES ITS READING, AND THAT IS THIS TASK'S FIRST
#: REQUIREMENT.** 2b's criteria 6 and 7 read as settled through four tasks
#: because nobody wrote down whether they meant the peak, the end of a tile or
#: the end of a run -- three readings of one quantity that differ by 1.58x.
#:
#: The vocabulary is closed on purpose: a verdict quoting a reading no harness
#: can take is a verdict about nothing. Each entry is the plan's own third
#: column, verbatim enough to be checkable against it.
READINGS = (
    "theta, loglik and n_iter per cell",
    "the fit_hash, both directions",
    "the completion bitmap and the fitted index set",
    "the source map element by element, not summary statistics",
    "the recorded source index",
    "the refusal message",
    "/signal/ bytes",
    "the per-cell magnitude, and the arm's fingerprint",
    "the report's own contents",
    "binning unchanged under a warm-arm perturbation",
    "iterations and wall clock, both named",
)

#: Why a criterion about the audit's internals has no outside to be driven from.
#:
#: **THIS IS A DIFFERENT CASE FROM 2b's `NO_OUTSIDE`**, which covers a claim
#: about code shape that a subprocess could only re-derive. Here an outside is
#: *conceivable* and does not exist yet: the audit has no command line, because
#: there is nothing to print until Phase 5's `--explain`, and *"a flag that
#: parses and does nothing reads as supported"*. Saying which of the two it is
#: matters -- one closes when someone writes a flag, the other never closes.
NO_CLI_YET = (
    "none exists yet: the audit has no command line. It records arrays and "
    "Phase 5's `--explain` prints them, so the nearest outside is a library "
    "call in a second interpreter -- the same derivation, which 2b's "
    "NO_OUTSIDE already refuses as evidence. This closes when `--explain` "
    "lands, and it is listed as owed rather than as impossible"
)

PHASE_2C_EXIT_CRITERIA: tuple[ExitCriterion, ...] = (
    ExitCriterion(
        number=1,
        statement=(
            "`fit` warm-starts exactly the cells `x0_valid` marks, and a false "
            "cell is bit-identical to the same cell fit with `x0=None`"
        ),
        verdict=Verdict.MET,
        reading="theta, loglik and n_iter per cell",
        scope="",
        established_by=(
            "test_x0_valid_selects_the_warm_started_cells_one_by_one",
            "test_an_invalid_cell_is_bit_identical_to_the_same_cell_fit_cold",
            "test_criterion_1_an_unwarmed_cell_matches_a_cold_run_on_disk",
        ),
        outside=(
            "a real two-pass run whose spiral exhausts over land, read back "
            "against a plain cold run of the same input: the STORED theta and "
            "n_iter at the exhausted cells, off disk, with no call to `fit`"
        ),
    ),
    ExitCriterion(
        number=2,
        statement=(
            "The coarse stride moves `fit_hash`; every audit setting moves neither gate"
        ),
        verdict=Verdict.MET,
        reading="the fit_hash, both directions",
        scope="",
        established_by=(
            "test_the_warm_start_coarse_stride_moves_fit_hash",
            "test_every_audit_setting_moves_run_hash_and_neither_gate",
            "test_criterion_2_the_stride_moves_the_stored_hash_and_the_audit_does_not",
        ),
        outside=(
            "the `fit_hash` attr read off three written stores, which is what "
            "a resume actually compares -- not `Config.fit_hash()`, which is "
            "the function under test"
        ),
    ),
    ExitCriterion(
        number=3,
        statement=(
            "A decimated pass-1 run fits exactly the points `isel` selects, and "
            "resumes after a kill"
        ),
        verdict=Verdict.MET,
        reading="the completion bitmap and the fitted index set",
        scope="",
        established_by=(
            "test_a_decimated_run_fits_exactly_the_points_isel_selects",
            "test_a_kill_during_pass_one_resumes_pass_one",
            "test_the_decimation_selects_exactly_the_isel_points",
        ),
        outside=(
            "a real `run(decimate=...)` and a SIGTERM: the completion bitmap "
            "and the fitted set are both read back off the store"
        ),
    ),
    ExitCriterion(
        number=4,
        statement="The source map is identical at two tile sides",
        verdict=Verdict.MET,
        reading="the source map element by element, not summary statistics",
        scope="",
        established_by=(
            "test_the_map_is_identical_however_the_grid_is_divided_into_regions",
            "test_criterion_4_the_recorded_source_index_is_identical_at_two_tile_sides",
        ),
        outside=(
            "two full runs at two memory budgets deriving DIFFERENT tile "
            "sides, compared on the source index arrays each wrote to disk"
        ),
    ),
    ExitCriterion(
        number=5,
        statement="A coarse point's source is itself, at radius 0",
        verdict=Verdict.MET,
        reading="the recorded source index",
        scope="",
        established_by=(
            "test_a_coarse_points_own_source_is_itself_at_radius_zero",
            "test_criterion_5_a_coarse_points_recorded_source_on_disk_is_itself",
        ),
        outside=(
            "the source index array a real two-pass run wrote, indexed at the "
            "lattice points -- geometry read back rather than recomputed"
        ),
    ),
    ExitCriterion(
        number=6,
        statement=(
            "An incomplete or mismatched pass-1 store refuses pass 2, naming "
            "what would lift the refusal"
        ),
        verdict=Verdict.MET,
        reading="the refusal message",
        scope="",
        established_by=(
            "test_an_incomplete_pass_one_store_refuses_and_names_the_outstanding_tiles",
            "test_a_stride_mismatch_refuses_and_says_what_it_would_do",
            "test_a_fit_identity_difference_the_gate_never_enumerated_still_refuses",
            "test_an_incomplete_pass_one_store_refuses_pass_two",
            "test_criterion_6_the_refusal_reaches_a_user_as_an_exit_code_and_a_message",
        ),
        outside=(
            "`python -m metamer` in a subprocess: the exit code and stderr, "
            "which is what a user gets and what a resuming script branches on"
        ),
    ),
    ExitCriterion(
        number=7,
        statement="A two-pass run is bitwise identical across two memory budgets",
        verdict=Verdict.MET,
        reading="/signal/ bytes",
        scope="",
        established_by=("test_two_budgets_give_the_same_signal_bit_for_bit",),
        outside=(
            "two complete runs at two budgets, compared on the raw `/signal/` "
            "bytes off disk"
        ),
    ),
    ExitCriterion(
        number=8,
        statement=(
            "A killed-and-resumed pass 2 is bitwise identical to an "
            "uninterrupted run -- 2a's criterion 1, which 2c must not break"
        ),
        verdict=Verdict.MET,
        reading="/signal/ bytes",
        scope="",
        established_by=(
            "test_a_killed_and_resumed_pass_two_is_bitwise_identical",
            "test_criterion_1_a_killed_and_resumed_run_is_byte_identical",
        ),
        outside=(
            "a real SIGTERM mid-run and a resume, compared on the raw "
            "`/signal/` bytes against an uninterrupted run"
        ),
    ),
    ExitCriterion(
        number=9,
        statement=("`N2` is matched per cell and reproduces under its recorded seed"),
        verdict=Verdict.MET,
        reading="the per-cell magnitude, and the arm's fingerprint",
        scope="",
        established_by=(
            "test_n2_moves_each_cell_by_that_cells_own_warm_cold_distance",
            "test_the_same_seed_reproduces_n2_and_a_different_seed_does_not",
            "test_the_direction_is_a_function_of_the_cell_and_not_of_the_order",
        ),
        outside=NO_CLI_YET,
    ),
    ExitCriterion(
        number=10,
        statement=(
            "The audit emits no pooled figure on any metric, and withholds "
            "strata below 30 members visibly"
        ),
        verdict=Verdict.MET,
        reading="the report's own contents",
        scope="",
        established_by=(
            "test_no_reported_number_exists_without_a_stratum_to_quote_it_with",
            "test_a_quantity_reported_over_everything_cannot_be_constructed",
            "test_the_thirty_member_boundary_on_a_RATE_reports_one_and_withholds_the_other",
            "test_a_withheld_stratum_is_present_in_the_output_carrying_its_count",
        ),
        outside=NO_CLI_YET,
    ),
    ExitCriterion(
        number=11,
        statement="`κ` bins by the cold arm",
        verdict=Verdict.MET_WITH_REDUCED_SCOPE,
        reading="binning unchanged under a warm-arm perturbation",
        scope=(
            "the BINNING is met and the AXIS is degenerate on the population "
            "it stratifies. `optimize.HESSIAN_COND_LIMIT` is `float(EPS) ** "
            "-0.5`, which IS D9's first boundary, and a fit above it reports "
            "DEGENERATE_HESSIAN and leaves the both-OK intersection -- so bins "
            "`[2**26, 2**52)` and `>= 2**52` are unreachable by construction "
            "and `undefined` was empty in fact (8 live cells, all in the first "
            "bin, measured 2026-08-29). The report ships "
            "`unreachable_kappa_bins` beside the boundaries so the emptiness "
            "reads as selection rather than as a finding about the field"
        ),
        established_by=(
            "test_kappa_binning_is_unchanged_when_only_the_warm_arms_kappa_moves",
            "test_the_winning_candidate_stratum_reads_the_cold_arm_too",
            "test_the_report_reads_real_arms_and_no_cell_reaches_an_upper_kappa_bin",
            "test_every_ok_cell_bins_under_the_first_kappa_boundary_and_the_padding_is_nan",
        ),
        outside=(
            "the real-arms test reads a two-pass store off disk and bins the "
            "cold arm's stored condition numbers; the (j7) guard itself has no "
            "outside for NO_CLI_YET's reason"
        ),
    ),
    ExitCriterion(
        number=12,
        statement=(
            "The warm-start saving at production length is at or above §11.2's 30%"
        ),
        verdict=Verdict.MET_WITH_REDUCED_SCOPE,
        reading="iterations and wall clock, both named",
        scope=(
            "MET AT PRODUCTION LENGTH ON THE SPIKE HARNESS -- 42.28% +/- 0.94% "
            "of iterations and 45.90% of wall clock at N = 630, 2026-08-23 -- "
            "and NOT RE-MEASURED ON THE SHIPPED MECHANISM. The two differ "
            "where it matters: the harness chose its own warm source, while "
            "the shipped path goes through `source_map`'s nearest-valid "
            "spiral, and which neighbour a point starts from is what sets its "
            "iteration count. Three obstacles, each sufficient: 21 s per point "
            "per arm measured 2026-08-29, so the smallest non-degenerate k = 8 "
            "lattice is 1.7 hours against a 39-minute suite; no spatially "
            "coherent fixture exists in the tree, and (h) says a field of "
            "independent draws measures nothing; and the saving is 7.80 / "
            "31.73 / 42.28% at N = 96 / 384 / 630, so any affordable length "
            "measures a different number rather than a weaker one. What IS "
            "established here is the SIGN, on a coherent field at short "
            "record length, which separates 'not measured' from 'inert'. "
            "CLOSER: 2d's simulated-field benchmark, which owns the coherent "
            "field"
        ),
        established_by=(
            "test_criterion_12_the_shipped_mechanism_saves_iterations_on_a_coherent_field",
            "test_the_warm_path_runs_and_says_so_in_three_places",
        ),
        outside=(
            "two complete runs of the same input -- one `--two-pass`, one "
            "plain -- compared on the `n_iter` each wrote to its store. The "
            "MAGNITUDE claim has no outside because it has no measurement"
        ),
    ),
)
