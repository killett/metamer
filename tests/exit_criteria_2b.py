"""Phase 2b's sixteen exit criteria, as values, with their verdicts and readings.

**THE TABLE HAS ALWAYS LIVED IN PROSE AND THAT IS HOW A VERDICT WENT STALE.**
Criterion 6 read *"MET as written"* through Tasks 8, 9 and 8a while the
measurement under it was being withdrawn, because nothing connected the
sentence to anything executable. Here it is data, and
`tests/test_exit_criteria_2b.py` binds it: every criterion names the tests that
establish it and those tests must exist; every criterion about a measured
quantity names **which reading** of it; and the two verdicts that depend on the
published record move with that record or the suite fails.

**IT LIVES IN `tests/` RATHER THAN IN `src/`** because a sub-phase's exit
criteria are a property of the development process and not of the package. The
wheel should not carry them, and `tests/test_packaging.py` would be right to
object if it did.

**AND IT IS NOT THE REPORT.** The closing table with its reasoning is in
`PROGRESS.md` and in the plan. What is here is the part a test can hold.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

#: The readings a peak-or-residency criterion may be stated against, and the
#: whole vocabulary of them.
#:
#: **A CRITERION OVER A MEASURED QUANTITY MUST NAME ITS READING**, because one
#: run yields several and criteria 6 and 7 were written as though it yielded
#: one. Measured at Task 8b on a single duration-controlled ladder: the working
#: set at end of run is **970.6 +/- 47.6 B/series**, at end of tile **1504.1 +/-
#: 21.4**, and the peak **2410.0 +/- 46.0** -- a factor of 2.5 between the
#: extremes, against an analytic 926 and a band of 617.3-1389.0. **Criterion 6
#: is met on the first and failed on the other two**, and until Task 8b it did
#: not say which it meant.
#:
#: The vocabulary is closed on purpose: a verdict quoting a reading no harness
#: can take is a verdict about nothing.
READINGS = (
    "working set at end of run",
    "working set at end of tile, block alive",
    "peak",
)


class Verdict(StrEnum):
    """What a sub-phase can honestly say about one of its exit criteria.

    **THREE VALUES AND NOT TWO.** A criterion that passes only inside a stated
    scope is neither met nor failed, and collapsing it either way loses the
    thing the next reader needs -- 2a's closing table already needed the middle
    value and expressed it in prose.
    """

    MET = "met"
    MET_WITH_REDUCED_SCOPE = "met with reduced scope"
    FAILED = "failed"


@dataclass(frozen=True)
class ExitCriterion:
    """One criterion, its verdict, and what the verdict rests on.

    Attributes:
        number: Its number in the plan's table.
        statement: What it asserts, in one line.
        verdict: Met, met with reduced scope, or failed.
        reading: Which reading of the measured quantity the verdict is about,
            drawn from `READINGS`. **None only where the criterion is not about
            a measured quantity at all** -- and that is a claim a test checks,
            not a default.
        scope: For a reduced-scope verdict, what it does and does not cover; for
            a failure, **the regime it fails in**. Never empty.
        established_by: The tests that establish it, as function names. **Bound
            to the collected suite**, so a criterion whose evidence is renamed
            or deleted fails rather than standing on nothing.
        outside: What the criterion is driven from, or **why no outside exists**
            -- "driven from outside wherever an outside exists" has a clause
            people drop, and for a criterion about code shape there is none.
    """

    number: int
    statement: str
    verdict: Verdict
    reading: str | None
    scope: str
    established_by: tuple[str, ...]
    outside: str


NO_OUTSIDE = (
    "none exists: this is a claim about code shape, falsifiable by reading and "
    "by arithmetic. A subprocess around the same call is the same derivation in "
    "a second interpreter, and it would read as stronger evidence than the "
    "in-module test while being identical to it"
)

PHASE_2B_EXIT_CRITERIA: tuple[ExitCriterion, ...] = (
    ExitCriterion(
        number=1,
        statement=(
            "`resident_bytes_per_series` describes the code: the output-slot "
            "term matches what `fit` preallocates field by field, and the "
            "solver term does not scale with B"
        ),
        verdict=Verdict.MET,
        reading=None,
        scope=(
            "the INVENTORY is met and its total is not the check -- F2 and F3 "
            "had opposite signs and cancelled to within 0.5% of a measurement "
            "while neither term was right, so the test compares terms"
        ),
        established_by=(
            "test_the_output_slot_term_is_the_inventory_fit_preallocates_field_by_field",
            "test_the_tile_solver_term_does_not_grow_with_batch",
        ),
        outside=NO_OUTSIDE,
    ),
    ExitCriterion(
        number=2,
        statement="Everything `optimize_series` allocates has leading dimension 1",
        verdict=Verdict.MET,
        reading=None,
        scope="",
        established_by=(
            "test_everything_the_optimizer_drives_has_a_leading_dimension_of_one",
        ),
        outside=NO_OUTSIDE,
    ),
    ExitCriterion(
        number=3,
        statement=(
            "The batched placement is unreachable through `run()`, with its "
            "arithmetic asserted through a constructed call"
        ),
        verdict=Verdict.MET,
        reading=None,
        scope=(
            "unreachability is a property of today's driver. Its landing "
            "condition is recorded in the plan: when a driver hands an engine a "
            "real batch the engine's workspace becomes a per-series term"
        ),
        established_by=(
            "test_the_batched_placement_is_not_reachable_through_run",
            "test_both_placements_agree_on_the_slope_and_differ_only_in_the_constant",
        ),
        outside=NO_OUTSIDE,
    ),
    ExitCriterion(
        number=4,
        statement=(
            "The floor is measured post-warm with the input open, behind a bare "
            "launcher; pre- and post-warm are both recorded and differ"
        ),
        verdict=Verdict.MET,
        reading="working set at end of run",
        scope=(
            "the floor is INPUT-DEPENDENT by construction -- `measure_floor` "
            "takes a `data_uri`, and three inputs measured 1.28 MB apart at "
            "Task 9 -- so a pinned floor without its input is not reproducible"
        ),
        established_by=(
            "test_the_floor_ladder_reproduces_the_recorded_rungs",
            "test_a_run_measures_its_own_floor_when_none_is_supplied",
        ),
        outside=(
            "the probe is a bare launcher by construction, and the store's own "
            "`floor` attr is read back off disk"
        ),
    ),
    ExitCriterion(
        number=5,
        statement=(
            "A budget at or below the floor is refused, naming the floor, its "
            "components, and a budget that would work"
        ),
        verdict=Verdict.MET,
        reading=None,
        scope="",
        established_by=(
            "test_a_budget_below_the_process_floor_is_a_layer_three_refusal",
            "test_criterion_5_the_refusal_reaches_a_user_as_exit_code_three",
            "test_criterion_5_the_workable_budget_the_refusal_names_actually_works",
        ),
        outside=(
            "`python -m metamer` in a subprocess: the exit code and stderr, "
            "which is what a user gets and what a resuming script branches on"
        ),
    ),
    ExitCriterion(
        number=6,
        statement=(
            "Measured slope and intercept match the corrected formula within a "
            "two-sided band at four or five sides, residuals reported"
        ),
        verdict=Verdict.FAILED,
        reading="peak",
        scope=(
            "FAILS ON THE PEAK at 2410.0 +/- 46.0 against a band of "
            "617.3-1389.0, ratio 2.603, outside by 22 sigma; fails on the "
            "end-of-tile working set at 1504.1 +/- 21.4, ratio 1.624; and is "
            "MET on the end-of-run working set at 970.6 +/- 47.6, ratio 1.048. "
            "Three readings of one run and the criterion never said which it "
            "meant. Task 7's 1021.6 and Task 8's 1900.9 are both withdrawn as "
            "underestimates -- each ladder's run length grew with its abscissa"
        ),
        established_by=(
            "test_the_dispute_states_its_direction_its_owner_and_its_spread",
            "test_criterion_6_and_7_move_with_the_published_record",
        ),
        outside=(
            "the measurement is not in the suite, by Tasks 4, 7, 8 and 8b's "
            "precedent -- a 1.7 h ladder is a deliverable, not a test. What the "
            "suite holds is the verdict, bound to the record it rests on"
        ),
    ),
    ExitCriterion(
        number=7,
        statement=(
            "A run at a formula-derived side under a budget well below "
            "available RAM has peak RSS at or below the budget"
        ),
        verdict=Verdict.FAILED,
        reading="peak",
        scope=(
            "FAILS above roughly B = 1500 at all three fixtures measured, and "
            "the margin grows with both B and n_time: at N = 60, M = 2 it "
            "passes at B = 256 and 1024 and fails from 2304 (+1.0 MB) to 9216 "
            "(+11.0 MB); at N = 60, M = 6 and at N = 240, M = 2 it passes at "
            "B = 256 only, failing by 11.2 MB and 61.1 MB at B = 9216. Budgets "
            "are the minimal budget per side, which is Task 8's convention. "
            "Not closed by a correction because the peak-to-analytic ratio is "
            "1.888 / 2.603 / 3.850 across those fixtures, so no coefficient "
            "fits all three. Owned by open question 18"
        ),
        established_by=(
            "test_criteria_6_and_7_peak_rss_is_bounded_and_does_not_track_the_grid",
            "test_criterion_6_and_7_move_with_the_published_record",
        ),
        outside=(
            "a fresh child behind a bare launcher, per point; the failing "
            "regime was measured by hand and is not re-run here"
        ),
    ),
    ExitCriterion(
        number=8,
        statement=(
            "Peak RSS does not grow with tile count over 10^5-10^6 points, nor "
            "with tile index within a fitted run"
        ),
        verdict=Verdict.MET_WITH_REDUCED_SCOPE,
        reading="peak",
        scope=(
            "the suite test bounds TOTAL growth at 6 MB over sixteen tiles with "
            "an injected positive control, so it catches a leak of 400 kB/tile "
            "and nothing finer. The 45 B/tile figure is reachable only by the "
            "400-tile hand run, and a finite run's tail is an UPPER BOUND that "
            "falls with run length -- measured, 26x between 36 and 400 tiles"
        ),
        established_by=(
            "test_the_recompute_loop_retains_nothing_that_survives_its_warm_up",
        ),
        outside="a fresh subprocess, because an in-process differential measures the process's history plus the subject",
    ),
    ExitCriterion(
        number=9,
        statement=(
            "Every derived side is a multiple of the base, and the achieved "
            "chunk bytes for the worst array are inside the target band"
        ),
        verdict=Verdict.MET_WITH_REDUCED_SCOPE,
        reading=None,
        scope=(
            "the band holds for the arrays wide enough to reach the target. "
            "Seven of eighteen are narrow enough that a whole shard cannot "
            "reach it -- `point_outcome` is one byte per cell -- so one chunk "
            "per shard is the RIGHT answer there and the population is "
            "partitioned rather than the band widened"
        ),
        established_by=(
            "test_the_achieved_chunk_bytes_are_in_band_for_the_worst_array_not_a_typical_one",
            "test_criterion_9_the_worst_array_on_disk_is_inside_the_band",
        ),
        outside="a store written by a real run and read back with `zarr.open_group`, worst array chosen by measurement rather than named",
    ),
    ExitCriterion(
        number=10,
        statement=(
            "A config omitting `memory_budget_gb` and one naming the resolved "
            "value produce the same `run_hash`, and provenance distinguishes them"
        ),
        verdict=Verdict.MET,
        reading=None,
        scope="",
        established_by=(
            "test_a_config_omitting_the_budget_hashes_as_one_naming_the_resolved_value",
        ),
        outside="two stores on disk, compared attr by attr, with a third run as the control",
    ),
    ExitCriterion(
        number=11,
        statement="`total_ram_bytes` respects a cgroup limit when one exists",
        verdict=Verdict.MET_WITH_REDUCED_SCOPE,
        reading=None,
        scope=(
            "CONSTRUCTED: `/sys/fs/cgroup/memory.max` is `max` on this box, so "
            "the branch cannot be exercised by the environment and the fixture "
            "must build it. Same shape as `choose_core_count` with no SMT here "
            "and `library_table` with one OpenBLAS"
        ),
        established_by=(
            "test_total_ram_respects_a_cgroup_limit_and_records_which_reading_won",
        ),
        outside=NO_OUTSIDE,
    ),
    ExitCriterion(
        number=12,
        statement=(
            "`--calibrate` writes a cache entry, a default run does not, and a "
            "second process reads it and derives the calibrated side, which "
            "differs measurably from the analytic one"
        ),
        verdict=Verdict.MET,
        reading=None,
        scope="",
        established_by=(
            "test_a_second_process_derives_the_calibrated_side_from_the_cache",
        ),
        outside="a second process, which the criterion names and the test uses",
    ),
    ExitCriterion(
        number=13,
        statement="The versions digest moves when any installed distribution's version moves",
        verdict=Verdict.MET,
        reading=None,
        scope="",
        established_by=("test_the_digest_moves_when_any_distributions_version_moves",),
        outside="constructed: no distribution's version moves during a run, so the change is injected",
    ),
    ExitCriterion(
        number=14,
        statement="Deleting the cache leaves the store openable and resumable",
        verdict=Verdict.MET_WITH_REDUCED_SCOPE,
        reading=None,
        scope=(
            "the narrow claim holds -- never unreadable, incomplete or "
            "unopenable, and it costs a re-measurement. It is FALSE of a resume "
            "whose stored side is larger than the re-derived one, which "
            "`completion.resume_tile_side` refuses; that arm is criterion 15's"
        ),
        established_by=(
            "test_deleting_the_cache_leaves_the_store_openable_and_resumable",
        ),
        outside="the store is reopened and resumed after the cache file is removed from disk",
    ),
    ExitCriterion(
        number=15,
        statement=(
            "A store records `tile_side_basis`, and a resume across a basis "
            "change names calibration in its refusal"
        ),
        verdict=Verdict.MET,
        reading=None,
        scope=(
            "the diagnosis fires in three of the four cells of the basis "
            "cross-product, including the one where both bases read `measured` "
            "and the sides differ, which is what `--recalibrate` produces; it "
            "is SILENT where both are `default`, and that silence is half the "
            "finding -- a condition that fires everywhere carries no information"
        ),
        established_by=(
            "test_a_run_records_the_basis_that_produced_its_tile_side",
            "test_a_refusal_after_a_calibration_names_it_and_both_bases",
            "test_a_refusal_between_two_analytic_runs_says_nothing_about_calibration",
        ),
        outside="two runs, the second reading the first's `tile_side_basis` off disk",
    ),
    ExitCriterion(
        number=16,
        statement=(
            "The documented tile side equals `tile_side_for` of its documented inputs"
        ),
        verdict=Verdict.MET_WITH_REDUCED_SCOPE,
        reading=None,
        scope=(
            "a CONSISTENCY test, not a correctness one: its oracle is the "
            "implementation, so both sides move together and a wrong formula "
            "passes it. What it catches is the cascade -- a correction "
            "orphaning four documents and five docstrings. "
            "`test_the_worked_example_derives_272_from_the_whole_chain` is the "
            "independent oracle and stays"
        ),
        established_by=(
            "test_the_published_side_equals_tile_side_for_its_own_arguments",
            "test_the_worked_example_derives_272_from_the_whole_chain",
        ),
        outside=(
            "none needed: the number is a value in the tree and the test "
            "recomputes it. Re-asserting it in a closing suite is the roll-up "
            "in its purest form"
        ),
    ),
)
