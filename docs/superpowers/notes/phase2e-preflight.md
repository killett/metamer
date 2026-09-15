# Phase 2e pre-flight, per task

**The method lives in exactly one place** — [`phase1-to-phase2-handoff.md`](phase1-to-phase2-handoff.md)
§1 — and is not restated here. **Append each task's entry BEFORE the task, not after.**

---

## Pre-plan — the brainstorm's own audit, run against 2e's inherited brief (2026-09-12)

**THE BRIEF** was PROGRESS.md head item 3's *"NEXT ACTION: 2e"* plus head item 9(a): §14 is
unbuilt, the exit-code-1 collision now has a live producer, and 2e is the sub-phase named as its
owner. Seven findings changed the plan before a task was written. **Only what a later reader
cannot re-derive is here; the decisions themselves are in the plan and are not restated.**

### (a5) ACROSS DOCUMENTS — FOUR SITES DISAGREE ABOUT WHO OWNS `report`, AND THEY ARE NOT DISAGREEING ABOUT THE SAME THING

| site | what it says |
|---|---|
| design doc §14.2 | *"exposed as `metamer report <store>`"* |
| design doc §17's Phase 2/5 table | `report` is in **Phase 5's** commands row |
| `__main__.py`'s module docstring | `python -m` is used *"rather than in Phase 5, when `validate` and `report` are real"* |
| PROGRESS.md's phase table, 2e row | 2e owns *"reporting, `metamer report`"* |

**A majority count would have given the wrong answer.** §17 and `__main__.py` speak about the
**command tree**; §14.2 speaks about the **computation** and lists three consequences —
regenerable, independently testable, usable on a foreign store — which are properties of the
computation and not of the interface. **The documents were never in conflict about the same
thing**, and the resolution is a split rather than a correction: the computation and a minimal
entry point are 2f's, the subcommand stays Phase 5's.

**What it changed.** The 2e row is **amended to name which half**, not struck — it is the only one
of the four that names 2e and it is right about ownership and loose about scope. **The rule this
pays out on: before counting sites, check that they are making the same claim. Two documents
disagreeing about a word may be agreeing about the world.**

### (a5) THE SAME SHAPE AGAIN, ONE SECTION EARLIER, AND IT WAS FOUND ONLY BECAUSE THE FIRST ONE WAS

§14.1 puts the counters *"on a `rich` progress display"*; §17's table gives Phase 5 *"the `rich`
progress display (§14.1)"* and Phase 2 *"plain lines"*. **Identical structure: computation versus
interface, in the section next door.** Recorded as the same resolution rather than as a second
judgement call — and worth noting that it was invisible until the first one had been solved.
**A resolution is also a search pattern.**

### (a2c) AND (e) — `CANDIDATE_DROPPED.is_failure` IS `True`, AND HAS NEVER BEEN EXERCISED

`tests/test_exit_criteria.py:530` says it outright: *"`CANDIDATE_DROPPED` needs 14.1's early
abort."* Nothing in `src/` produces the code. So its classification has been carried since 2a and
**checked by nothing** — and `tests/test_outcomes.py:117–134` reasons `SCREENED_OUT` into the
exclusion set **explicitly** while `CANDIDATE_DROPPED` sits in the failure set with no argument
attached to it. **The asymmetry is the artefact of one member having a producer and the other not.**

**A classification that has never been exercised is a classification that has never been checked**,
and 2e giving it its first producer is therefore the first opportunity to find this — which is the
whole reason the finding is in a pre-flight and not in a post-mortem.

### (h4) `n_valid` IS NOT THE QUANTITY THE REPORT WANTS, AND THE CODE SAYS SO ON PURPOSE

`criteria.py:349–351`: `rankable = scored & isfinite(values)` is **narrower** than `scored`, and
`n_valid = count_nonzero(scored)`. A fit can succeed and have no finite criterion value (AICc at
`n ≤ k+1`) and is *"ranked last, not reclassified as a failure"*. **Therefore `n_valid == 1` is not
*"the selection was forced"* and `n_valid == 0` is not *"no survivor"*** — the second is
`selected == -1`, and contention is a third quantity.

(h4) is *a rule stated over "the metrics" must be checked against each KIND of metric*; here the
brief said *"selectability"* and three different stored quantities answer to that word. **Checked
before designing a section around the wrong one.**

### `/selection/n_valid` HAS ZERO PRODUCTION READERS, AND CONTENTION NEEDS NO SCHEMA CHANGE

`write.py:330` writes it; the only `n_valid` reader in `src/` is `audit_report.py:355`, which reads
the **in-memory** `Ranking`. **Nothing reads the array back out of a store.** And contention is
`count(isfinite(/selection/delta_ic))` over the model axis — `isfinite(delta_ic)` **is** `rankable`
by construction — so it is **per criterion**, strictly more informative than `n_valid`, and costs
no array. **The check that mattered was the second one:** without it the section would have been
designed around a schema addition that 2a's *"the store cannot change after data exists"* would
have had to absorb.

### THE FEEDBACK LOOP, PROMOTED TO THE HANDOFF §1

> **Where a run acts on a measurement and records the action in the same field the measurement is
> computed from, the later measurement reports the action. Check every rate's population for
> outcomes the run itself assigned.**

Worked instance: a candidate dropped after failing 91% of pass 1 gets `CANDIDATE_DROPPED` written
across every remaining point, and the end-of-run rate reads ~100% — **dominated by the decision
already taken about it, and louder than the evidence that triggered it.**

### §14.1 GIVES A ONE-PASS RUN NO ABORT POINT, AND READS AS THOUGH IT DOES

`twopass.py:16`: `warm_start.enabled = false` runs *"exactly one cold `run` over the full grid, with
no coarse store written"*. §14.1's whole argument is that pass 1 is *"stratified across the whole
domain by construction"* and its barrier *"costs nothing because the pass already exists."* **With
warm-starting off, neither exists**, and the only other trigger is the contiguous tile prefix §14.1
spends four paragraphs forbidding. Filed as a decision 2e must take, with three readings; **not
taken in the plan**, and Task 0 records it as open with Task 6 named as its owner.

---

## Plan Task 0 — the corrections and the §14 amendments, audited before any edit (2026-09-12)

**THE BRIEF** is the plan's Task 0: apply three corrections, amend §14.1/§14.2/§14.3, and promote
D9's rule to the handoff. **Three findings, and the first one changes the task's size.**

### (a5) THE "FOUR PLACES" CLAIM HAS SIX SITES, NOT TWO — AND IT WAS ALREADY CORRECTED ONCE

The plan's correction list named **two** sites: `decimate.py:32` and PROGRESS.md head item 9(a).
**The grep finds six**, and the sixth is the one that matters:

| # | site | what it says |
|---|---|---|
| 1 | `src/metamer/batch/decimate.py:32` | *"four places — the span tuples, the `by_dim` lookups and `assemble_tile`'s own `isel`"* |
| 2 | `PROGRESS.md:13`, head item 9(a) | *"requires the spatial dims to be literally `y` and `x` in four places"* |
| 3 | `PROGRESS.md:5978` | *"four sites plus fixtures"* |
| 4 | `docs/superpowers/notes/phase2c-preflight.md:581` | *"uses the literal names in four places"*, **above its own list of three** |
| 5 | `docs/superpowers/notes/phase2c-preflight.md:599` | *"four sites plus fixtures"* |
| 6 | **`tests/test_decimate.py:107`** | *"takes the literal names in four places"* — **in a test docstring** |
| 7 | `PROGRESS.md:5511` | *"literally `y` and `x` in **four** places"* — **found only on the second sweep** |
| 8 | `PROGRESS.md:5970` | *"Four sites — the span tuples at 904–905… `isel` at 973"* — **second sweep, and it cites the `isel` a line high** |

Two further sites carried the **knock-on**: `PROGRESS.md:5980` and
`phase1-to-phase2-handoff.md:794` both said a name-based decimation would have become *"the fifth
site"*, a number that is only meaningful under the wrong count. **De-numbered rather than
renumbered** — *"another site"* — because the number is the part that has already gone stale twice.

### (a4) ON THIS ENTRY ITSELF — THE SWEEP SAID SIX AND THE ANSWER WAS EIGHT

**The table above said six until the corrections were applied**, and applying them surfaced two
more. The first sweep matched on *"four places"* and *"four sites"*; sites 7 and 8 phrase the same
claim as *"literally `y` and `x` in **four** places"* and *"Four sites — the span tuples at…"*, and
neither contains either phrase. **A sweep is a claim about a search pattern, not about the tree.**

**This is why Task 0's deliverable is a TEST THAT READS THE TREE and not a corrected list.** A list
is a ninth site. The enumeration test counts the literal occurrences in `tiling.py` and fails when
that count moves, so the number has exactly one home and every prose mention is a pointer rather
than a copy. **The finding that the earlier correction did not propagate and the finding that my
own sweep was incomplete are the same finding at two scales**, and both are arguments for the same
fix.

**AND THE CORRECTION IS NOT NEW. `realdata-spike-preflight.md:66` MADE IT ON 2026-09-07:**
*"`tiling.py`'s 'four places' is six literal occurrences at three call sites today, at lines 904,
905, 932, 933, 974, 975."* **Five sites still said four, five days later.**

**That is a worse fact than the one the plan recorded, and it changes what Task 0 is for.** The
plan presented this as a fresh (c) finding — *enumerate, never count*. It is instead a **finding
that was already made and did not propagate**, which is a different failure: the project knew, and
the knowledge died in the file that discovered it. **A correction recorded only where it was found
is not a correction; it is a second version of the claim.**

**What it changes.** Task 0's correction list becomes **all six sites, enumerated**, plus a line at
the propagation site saying when the correction was first made and that it did not travel — so the
next reader learns the failure mode and not only the number.

### (a4) MY OWN ENUMERATION WAS OFF BY ONE, AND THE 2026-09-07 RECORD WAS RIGHT

The brainstorm said the `isel` names sit at **973–974**. They sit at **974–975**; line 973 is
`array.isel(` itself, which carries no name. The spike's record said 974, 975 and it was correct.

**(a4): "checked" in your own pre-flight is a claim.** The verified enumeration, by function rather
than by line because lines are what drifted the record in the first place:

| function | line | occurrences |
|---|---|---|
| `read_amplification` (860) | 904, 905 | the span tuples |
| `assembly_spans` (912) | 932, 933 | the `by_dim` lookups |
| `assemble_tile` (937) | 974, 975 | the `isel` keywords |

**Six occurrences, three functions.** The plan already says *three functions* and that form is kept
— **not because it is tidier but because it is the form that survived**: the by-line citation has
now been wrong in the record twice and the by-function one has never been wrong.

### (a6) A TEST DOCSTRING ASSERTS THE DEFECT, AND TASK 2 FALSIFIES IT

`tests/test_decimate.py:106–108` closes with *"**This asserts the decimation, not end-to-end
support.** `tiling.py` takes the literal names in four places, so a run over this input still fails
in assembly."* The test itself decimates a `latitude`/`longitude` handle and asserts the axes
survive.

**After Task 2 that caveat is false in both halves** — the count and the consequence. (a6) is *when
code is deleted or replaced, sweep for the descriptions that survive it*, and this is the
description that would have survived: it sits in a **test**, where a stale comment reads as a
specification of current behaviour and where nothing that runs will contradict it.

**What it changes.** **Task 2 owns this sweep, not Task 0** — the docstring is true until Task 2
lands, and correcting it now would make the tree say the defect is closed while it is open.
Recorded here so the sweep is a task requirement rather than something noticed later. The plan's
Task 2 gains it, and the same sweep covers `decimate.py`'s module docstring, whose *"THAT DOES NOT
MEAN SUCH AN INPUT WORKS END TO END"* paragraph becomes false at the same moment.

---

## Plan Task 1 — `INTERNAL_ERROR` and the catch-all, audited before any code (2026-09-12)

**THE BRIEF** is the plan's Task 1: append `INTERNAL_ERROR` to `ExitCode`, add a catch-all in
`__main__`, keep the staged catches' precedence, and assert that exit 1 is unreachable until Task 6.
**Five findings, and the first two change where the catch-all goes.**

### (c) ENUMERATE THE EXIT PATHS — AND THE EXISTING `try` COVERS ONLY A THIRD OF `main`

**`main()`'s exit paths, enumerated rather than counted:**

| # | path | code today |
|---|---|---|
| 1 | argparse usage error → `_Parser.error` | `SystemExit(3)` |
| 2 | `--version` / `--help` | `SystemExit(0)` |
| 3 | `--two-pass` with `--reuse-fits-from` → `parser.error` | `SystemExit(3)` |
| 4 | two-pass, pass 1 stopped short, pass 2 never started | `return ABORTED_EARLY` |
| 5 | staged failure → `exit_code_for(error)` | `return` 3 or 4 |
| 6 | `report.interrupted` after a full pass | `return ABORTED_EARLY` |
| 7 | clean | `return OK` |
| 8 | **anything else — propagates out of `main`, `sys.exit(main())` never runs** | **Python's 1** |
| 9 | **`TypeError` from `exit_code_for` raised INSIDE the `except` clause** | **Python's 1** |

**THE FINDING: `try` STARTS AT `run` AND ENDS AT THE `except`. EVERYTHING AFTER IT IS UNPROTECTED.**
The identifiability warnings, the budget and calibration warnings, the whole printed report block,
`max(warm.radius_histogram, default=0)`, the `init_rungs` join and the `report.interrupted` branch
are **all outside it** — roughly seventy lines, and precisely the lines that format values computed
elsewhere.

**So the catch-all must WRAP `main`'s body, not extend the existing `except` clause.** Appending
`except Exception` to the existing `try` is the obvious edit, it type-checks, it passes a test that
crashes inside `run`, **and it leaves every reporting path exiting 1.** **Nest, don't append.**

### (c2) THE STAGED HANDLER HAS ITS OWN CRASH PATH, WHICH IS PATH 9

`exit_code_for` is documented to **raise `TypeError` if the exception is not one of the staged
types**, and it is called *from inside* `except (ValidationError, InputContractError)`. An
exception raised in an except clause propagates. **The handler for the honest failures can itself
crash**, and only an outer `try` sees it. (c2) asks whether dispatching on exception type actually
discriminates; here it does, and the discriminator is the thing that can fail.

### (k2) THE CATCH MUST BE `Exception`, NEVER `BaseException` — AND THE VOCABULARY SAYS WHY

`_Parser.error` raises **`SystemExit(ExitCode.CONFIG_INVALID)`** and `--version` raises
`SystemExit(0)`; both are `BaseException`, not `Exception`. **A catch-all on `BaseException` would
convert `--version` into an internal error and swallow `KeyboardInterrupt`** — turning the two
paths that work correctly today into the one code that means *the run did not finish*. The narrow
catch is not a stylistic preference here; it is what keeps paths 1–3 intact.

### WHERE IT GOES: INSIDE `main`, NOT AT `if __name__ == "__main__"`

Both placements produce the right exit code. The tiebreaker is `main`'s own docstring — *"Returns:
One of `ExitCode`"* — which is **false today** for paths 8 and 9 and stays false under the
call-site placement. Wrapping `main`'s body makes the docstring true, keeps `sys.exit(main())`
trivial, and leaves the behaviour reachable from an in-process call as well as a subprocess.
**The traceback is still printed explicitly**, so the code carries the fact and the traceback
carries the detail — (i2): an absence is not a signal, so the detail must be emitted rather than
merely permitted.

### (k2) WHERE IT IS TESTED IS ALREADY DECIDED, AND THE RECORD SAYS SO

`tests/test_runner.py`'s module docstring: *"**An exit code is a property of a PROCESS**, so every
exit-code assertion runs `python -m metamer` in a subprocess and reads `returncode`. Calling
`main()` in-process tests the mapping function — worth doing, and not the same claim: `sys.exit`
semantics, argparse's own exits **and an unhandled traceback** are all invisible to an in-process
call."*

**This was written before 2e existed and it decides Task 1's test placement without re-deriving
it.** The live-producer test, the unreachability test and the staged-precedence test are all
**subprocess** tests. An in-process `main()` call may test the mapping and must not be the evidence
for any exit code.

### (i2) "EVERY FAILING PATH" IS UNBOUNDED UNTIL IT IS ENUMERATED

The plan's unreachability test says *"every failing path is run and none produces 1."* **Without
the table above that sentence has no stopping condition**, and a test satisfying it with two paths
would read identically to one satisfying it with seven. **The test runs paths 1, 3, 5 (both codes),
4 and 6** — the reachable non-zero paths — and asserts none returns 1. Paths 8 and 9 are the ones
being closed; path 2 and path 7 are not failures.

**And the test is expected to invert at Task 6**, where path 8's code becomes reachable *only* from
the threshold. The pair is named at both ends so neither half is edited alone.

### THE LIVE PRODUCER, MEASURED BEFORE IT WAS CLOSED (2026-09-12)

**Captured before any of Task 1's code existed**, because Task 2 destroys it and a control that is
gone cannot be re-taken. A synthetic `latitude`/`longitude` store through the shipped entry point:

    EXIT CODE: 1
      File "/workspace/src/metamer/batch/run.py", line 1094, in run
        amplification = read_amplification(handle, tiles[0])
      File "/workspace/src/metamer/batch/tiling.py", line 907, in read_amplification
        read *= _chunk_points(start, stop, by_dim[dim], sizes[dim])
    KeyError: 'y'

**This reproduces head item 9(a)'s 2026-09-07 reading** — same function, same key, same code — by
a separate instrument on a separately built fixture, two days after the record was last touched.
**The reading is not restated at the test**; the test carries the dated fact and this entry carries
the traceback, which is the one place a later reader can check that the two agree.

**After Task 1's catch-all, the same input exits 5 with the same traceback**, plus the line naming
it a defect in metamer rather than in the user's configuration or data. Both halves were run; the
`--version`, `--help`, no-args and missing-config paths were re-run beside them and still exit
0, 0, 3 and 3 — the (k2) check that the catch is `Exception` and not `BaseException`, taken as a
measurement rather than as a reading of the source.

---

## Plan Task 2 — the tiling closer, audited before any code (2026-09-12)

**THE BRIEF** is the plan's Task 2: make `tiling.py` take the spatial dimensions positionally in its
three functions, leave `time` name-based, leave stage 4a's message unchanged so it becomes true, and
sweep the descriptions the fix falsifies. **Four findings, and the first one adds a deliverable.**

### (i5) AND (a2b) — THE POSITIONAL REWRITE INTRODUCES A SILENT WRONG ANSWER, AND THE CONTRACT DOES NOT STOP IT

**Measured, 2026-09-12.** xarray **permits duplicate dimension names** — it warns at construction
and allows it — and stage 4a checks only `ndim == 3` and `dims[0] == "time"`. **So an input with
dims `("time", "x", "x")` passes the contract today.** On such an array:

    dims                ('time', 'x', 'x')   shape (2, 3, 4)
    {str(d): s for d, s in zip(dims, shape)}  ->  {'time': 2, 'x': 4}
                                                  three dims collapse to two keys,
                                                  and 'x' keeps the LAST value, 4, not 3
    isel({dims[1]: y_slice, dims[2]: x_slice})  ->  {'x': x_slice}
                                                  the y-slice is silently DROPPED
    result shape        (12, 1, 1)  where (12, 2, 1) was asked for

**CORRECTED THE SAME DAY, (a4) ON THIS ENTRY.** The first draft measured `(2, 3, 4)` and reported
that the collapsed dict *"keeps the LAST value, 4, not 3"*. **That witness is unreachable**:
`xr.Dataset` refuses inconsistent sizes for one dimension name, so an unequal pair cannot be built,
written or read, and the test written from it died in its own fixture. **The reachable witness has
EQUAL extents** — `(12, 3, 3)` — which removes the size-collapse half and leaves the slice-dropping
half, measured above. **The mechanism is unchanged and the hazard is unchanged; one of the two
symptoms was an artefact of an impossible fixture.** Such a store writes through `to_zarr` and
reopens through `open_zarr` with its duplicate dims intact, so the path is real end to end.

**TODAY THIS FAILS LOUDLY** — `by_dim["y"]` raises `KeyError`, which since Task 1 is exit 5 with a
traceback. **Under the naive positional rewrite it succeeds and returns the wrong block.** That is
a regression in the worst available direction: a crash becomes a plausible number, on a path where
nothing downstream can tell.

**SO TASK 2 GAINS A DELIVERABLE IT DID NOT HAVE: stage 4a refuses duplicate spatial dimension
names**, with `InputContractError` and therefore exit 4. It belongs in this task rather than being
filed, **because this task creates the hazard** — the check is not tidying, it is the precondition
that makes the rewrite safe. (a2b): make the invalid value **unavailable** rather than caveated.

**AND IT IS A SECOND INSTANCE OF OPEN QUESTION 20**, which asks what else is uniform across all
sixteen input fixtures and unconstrained by the contract. The question named coordinate monotonic
direction; **duplicate dimension names is a second answer, found by trying to close a different
defect.** Recorded at the question, because the question's value is the list.

### (a6) EVERY DESCRIPTION OF THIS DEFECT BECOMES FALSE AT ONCE, AND THERE ARE TEN

Task 0 corrected the **count** at eight sites and left the **consequence** clauses standing, because
they were true. This task falsifies all of them simultaneously. The sweep is therefore not two
docstrings but every site that says the defect is open:

`decimate.py`'s module docstring (*"THAT DOES NOT MEAN SUCH AN INPUT WORKS END TO END"*, and its
two-closers paragraph, which now has an answer) · `tests/test_decimate.py:106-108` (*"this asserts
the decimation, not end-to-end support"*) · `tests/test_runner.py`'s `_latlon_store` helper
(*"the only LIVE producer"*) · PROGRESS head item 9(a)'s surviving half · `PROGRESS.md:5511` ·
`PROGRESS.md:5970` · `PROGRESS.md:5978` · `phase2c-preflight.md`'s two entries ·
`phase1-to-phase2-handoff.md:792`.

**The lesson Task 0 paid for applies here and is why this list is written before the edit**: a
correction recorded only where it was found is a second version of the claim.

### THE HANDOVER IS A PRECONDITION, NOT A CONSEQUENCE

Task 1's live-producer test asserts a `latitude`/`longitude` store exits `INTERNAL_ERROR` with
`tiling.py` in the traceback. **This task makes that store run**, so the test stops describing
anything. **Its constructed replacement must be green BEFORE this task's rewrite lands**, and it
inherits the dated provenance — *verified against a live producer on 2026-09-12, `KeyError: 'y'` at
`read_amplification`* — which is what keeps it from becoming a test of itself.

### (i2) THE POSITIVE CONTROL IS INVARIANCE, NOT ABSENCE OF A CRASH

*"The lat/lon store runs"* is a negative: it passes if the run does nothing interesting. **The
positive control is that a renamed store produces the SAME FITS as the `y`/`x` store it was renamed
from** — identical stored values, point for point. A positional rewrite that transposes the two
spatial axes passes every "it runs" test, passes read-amplification arithmetic (which is symmetric
in the two axes on a square tile), and returns a **plausible wrong map**.

**And one thing must NOT be invariant, which is the same assertion from the other side:** the
`geometry_hash` **differs** between the two stores, because `geometry_components` keys
`spatial_coordinates` by the input's own dimension names. That is D1's fingerprint argument as a
test — **if the hashes matched, the rename closer would have been taken by accident.**


### THE FIX EXPOSES A SECOND DEFECT ONE LEVEL DOWN, AND IT IS A SCOPE DECISION (measured 2026-09-12)

**With the tiling path positional, a `latitude`/`longitude` store runs to exit 0 for the first
time — and the store it writes is not self-describing.**

`store.py` declares every data array's `dimension_names` as `("y", "x", ...)`, which is **the output
store's own schema** and is correct: metamer's product names its own axes. But it writes the
**coordinate arrays** under the keys of `geometry_components["spatial_coordinates"]`, which are the
**input's** dimension names. Nothing ever reconciled the two **because no input could previously
produce a store with different ones.**

Measured, same fits, two namings:

| store | `status/outcome` dims | coordinate arrays | xarray sizes |
|---|---|---|---|
| `y`/`x` input | `('y','x','m')` | `m, x, y` | `{y:2, x:3, m:2}` — coherent |
| `latitude`/`longitude` input | `('y','x','m')` | `latitude, longitude, m` | **`{y:2, x:3, m:2, latitude:2, longitude:3}`** |

**Five dimensions instead of three.** The data array's `y` and `x` axes have **no coordinates at
all**, and `latitude`/`longitude` are orphan dimensions attached to nothing. A downstream consumer
— design doc section 1.1 names one — reads `outcome(y, x, m)` and cannot say where any point is.

**The geometry hashes differ between the two runs** (`bfdeaf96…` against `fa9c528d…`), which is D1's
fingerprint argument holding exactly as intended: the provenance records the input's real names.
**So the information is not lost; it is in the attrs. What is wrong is the axis labelling.**

**And the selection between the two coordinate arrays is by LENGTH, not position:**
`if len(values) in {shape.n_y, shape.n_x}` — which on a square grid cannot tell the two axes apart
and maps them by name alone. **That is the same defect class this task just removed from
`tiling.py`**, one module over: a name-or-length guess standing where position is the truth.

**THIS IS A CHANGE TO `store.py`, WHICH 2a FROZE, SO IT IS NOT TAKEN UNILATERALLY.** It is raised as
a scope decision with the measurement beside it, exactly as the tiling closer was.

### (a5) THE SWEEP WAS INCOMPLETE FOR THE THIRD TIME, AND THE PATTERN IS NOW THE FINDING

The pre-flight listed **ten** sites describing this defect as open. The sweep found **twelve**:
`realdata-spike-verdict.md:229` and `realdata-spike-preflight.md:231` both carry the
*"dies in assembly without exit code 4"* phrasing, and neither contains any string the first two
patterns matched.

**Three times in one sub-phase, at three different scales:**

| when | claimed | actual | what the pattern missed |
|---|---|---|---|
| Task 0, first pass | 2 sites | 6 | *"literally `y` and `x` in **four** places"* — no matching phrase |
| Task 0, second pass | 6 sites | 8 | *"Four sites — the span tuples at…"* — a different sentence shape |
| Task 2 | 10 sites | 12 | *"dies in assembly without exit code 4"* — a **consequence** phrasing, not a count |

**The three misses are not the same miss.** The first two were paraphrases of a count; the third
was the defect described by its **effect** rather than by its size, in documents that never
mentioned a number at all. **A sweep built from the phrasings you already found cannot reach the
phrasings you have not** — so each pass finds the near-synonyms of its own seed and stops.

**THE STRUCTURAL ANSWER IS THE ONE TASK 0 ALREADY TOOK AND IT IS WORTH SAYING TWICE: the count has
one machine-readable home and the prose points at it.** `tests/test_dimension_name_sites.py` cannot
go stale, and no number of prose sites can make it wrong. **What prose still owns — "this defect is
open" — has no such home**, which is why the third miss was the effect-phrasing rather than the
count. The honest mitigation is to sweep by **subject** (`tiling`, `latitude`, `assembly`) rather
than by remembered wording, and to expect the list to grow on the last pass.

### TWO PROCESS SLIPS FROM TASK 2's VERIFICATION, BOTH WORKED INSTANCES OF RULES ALREADY WRITTEN

**1. `pixi run test 2>&1 | tail -25` REPORTED EXIT CODE 0 WITH A TEST FAILING.** The code belonged
to `tail`. This is the handoff §2 rule — *where a tool reports on something else, its exit code
describes the tool* — which already has the `&&` chain and `gh run watch --exit-status` as
instances. **This is its third, committed by the person who had just quoted it**, and it was caught
only because the summary line *"1 failed, 1424 passed"* was read as text. **Had the failure been
earlier in the output, `tail -25` would have hidden it and the exit code would have agreed.** Run
the sweep to a file and read pytest's own status.

**2. A KNOWN CONSEQUENCE WAS OBSERVED AND NOT ACTED ON.** While writing Task 2 it was noted, in
writing, that `test_exit_one_is_unreachable…` used the `latitude`/`longitude` store as its crash
path and that *"after the rewrite that store will run fine, so that entry breaks"* — and the fix
was not made. It surfaced as the sweep's only failure, 69 minutes later. **The handover from a live
control to a constructed one had TWO sites, not one**; the pre-flight's handover section named the
live-producer test and stopped there. **(c) again: enumerate the consumers of the thing you are
destroying, not just the one you were thinking about.**

---

## Plan Task 3 — `CANDIDATE_DROPPED` joins the decided skips, audited before any code (2026-09-14)

**THE BRIEF** is the plan's Task 3 and decision D7: flip `CANDIDATE_DROPPED.is_failure` to `False`,
keep it eligible, record the rule at `Outcome`. **Three findings, and the first one changes what
this task IS.**

### (a5) THE DESIGN DOC ALREADY DECIDED THIS, AND THE CODE HAS DISAGREED WITH IT SINCE 2a

D7 was written as a decision with a recommendation. **It is not a decision. It is a correction.**

Design doc §12.5 carries a table under the heading **"THE NON-FIT CODES ARE A GROUP, AND THE
GROUPING IS WHAT §14.2's DENOMINATOR READS"** — so it is the authoritative classification, by its
own declaration — and it says:

| code | the store is saying | eligible? |
|---|---|---|
| `SCREENED_OUT` | a decision was taken not to fit this candidate | **legitimate non-fit** |
| `CANDIDATE_DROPPED` | this candidate was demoted run-wide after early abort (§14.1) | **legitimate non-fit** |

**The same cell value, for both.** And `Outcome.is_failure` excludes `SCREENED_OUT` and includes
`CANDIDATE_DROPPED`. **The code and the design doc have contradicted each other since 2a**, in a
table written specifically to settle this question, and nothing caught it **because the member has
no producer.**

**PROGRESS.md's precedence rule decides the rest:** *the design doc is authoritative on INTENT*. So
Task 3 does not need D7's argument to justify the change — the argument was already made, one
section away from where the plan looked. **The plan's own reasoning (§14.1's `NOT_ATTEMPTED` →
`SCREENED_OUT` correction) was right and was the weaker of the two available.**

**What this changes about the task:** the commit is *"the code catches up with §12.5"*, not
*"a classification is reconsidered"*. **And the entry at `Outcome` should cite §12.5 rather than
re-argue it**, or the project acquires a third statement of one rule.

### THE ARGUMENT WAS ALSO ALREADY IN THE TEST SUITE, AT THE SIBLING MEMBER

`tests/test_outcomes.py:117-134`, on `SCREENED_OUT`: *"a deliberate skip, like `NOT_ATTEMPTED`: the
run chose not to fit, so counting it as a failure would make a **cheaper configuration report a
worse failure rate**."*

**That sentence is true of `CANDIDATE_DROPPED` word for word** — a dropped candidate is precisely a
configuration made cheaper by a decision the run took. The reasoning sat beside the member that did
not need it and was never applied to the member that did. **A classification that has never been
exercised has never been checked**, and the check here was not even a measurement — it was reading
the sibling's docstring.

### (c) THE GUARDS THAT MOVE, ENUMERATED

- **`tests/test_outcomes.py:26`, `test_every_real_failure_reports_is_failure`** — asserts
  `{o for o in Outcome if o.is_failure} == failures` with `CANDIDATE_DROPPED` **listed explicitly**
  in the expected set. **Set equality over the whole enum, which is the right shape**: it fails on
  this change and would fail on any future member defaulting into the failure set. Amended
  struck-not-deleted.
- **`tests/test_outcomes.py:115`, `test_the_two_deferred_outcomes_are_skips_and_not_failures`** —
  becomes *three* deferred outcomes. Renamed rather than edited, on the same rule as 2e's earlier
  count-in-a-name.
- **`audit_report.py:556-568`** consumes both properties through a lookup table and needs no
  change; **that it needs none is the assertion** — a second place that classifies outcomes is a
  second place that can disagree.

### AND A LARGER DISAGREEMENT FOUND ON THE WAY, WHICH IS **NOT** TASK 3's TO FIX

**`INSUFFICIENT_DATA` is classified three ways by three documents.**

| source | says |
|---|---|
| design doc **§8.6** | *"A legitimate expected outcome, **excluded from every failure-rate denominator**"* |
| design doc **§12.5** | *"**eligible**; its rate is a real statement about record coverage"* |
| `Outcome.is_eligible` | **excluded** — follows §8.6 |

**§12.5 is the later and more refined statement**: it explicitly separates land and permanent ice
(`NOT_APPLICABLE`) from a genuinely thin record (`INSUFFICIENT_DATA`), says *"collapsing them makes
the failure rate uninterpretable"*, and corrects §14.1's wording in the same passage. §8.6's row
still describes `INSUFFICIENT_DATA` as *"too few valid samples — land, permanent ice"*, **which is
the conflation §12.5 was written to undo.** So §8.6 is stale and the code follows the stale one.

**THIS IS NOT TASK 3's, AND THE REASON IS NOT SCOPE TIDINESS.** Unlike `CANDIDATE_DROPPED`,
`INSUFFICIENT_DATA` **has producers and occurs in real data**, so changing `is_eligible` moves the
denominator of every failure rate this project computes. **A correction that cannot move a number
and a correction that moves all of them are different acts**, and bundling them would let the
second ride in on the first's evidence. Recorded here, raised as its own decision.

---

## Plan Task 4 — the live counters, audited before any code (2026-09-14)

**THE BRIEF** is the plan's Task 4: point-granularity tallies by branch and by candidate,
accumulated and displayed per tile, **display-only with no decision reading them**, plain lines
rather than `rich`. **Four findings, and the third is a defect the brief would have shipped.**

### THE STRUCTURAL ENFORCEMENT IS HALF FREE ALREADY, AND THE PRECEDENT FOR THE OTHER HALF IS IN THE TREE

*"No decision may read them"* is the kind of claim a comment cannot hold. Two mechanisms exist:

1. **The seam's type already forbids the run consuming a value.** `on_tile_written` is
   `Callable[[Tile], None]` — it returns `None`, so nothing the callback computes can flow back
   into `run`. **A counter hung off this seam cannot influence the run through its return value**,
   whatever anybody later intends.
2. **`tests/test_core_isolation.py` is the precedent for the rest**, and its own docstring supplies
   the method: it asserts an import boundary **in a subprocess**, because *"inside the pytest
   session every one of these is already imported by some other test module, so an in-process
   check would pass against any core module at all — it would be measuring the session, not the
   import graph."* **The same reasoning applies exactly**: a test that `metamer.batch` never
   imports the counters must run in a fresh interpreter or it measures the test session.

**So the counters live OUTSIDE `metamer.batch`** — the display layer owns them, `batch` never
imports them, and the isolation test enforces it. That makes *"no decision may read them"* a
property of the import graph rather than of anyone's restraint, which is what §14.1 asks for when
it says the obvious future change *"will look like a free optimization"*.

### (j3) §14.1's "APPROXIMATE UNDER A RESUME" IS EVIDENCE ABOUT THE IMPLEMENTATION, NOT A CAVEAT

§14.1 says the counters' *"inevitable approximation under a resume"* is harmless. **That sentence
settles a design question the brief leaves open.** If the counters were computed by re-reading each
tile's region from the store they would be **exact** under a resume — the store holds every tile,
including the ones a previous process wrote. **They are approximate only if they are ACCUMULATED
from what this process fitted.**

So the counters are carried, not re-read — **and therefore the seam must carry the outcomes**,
because `on_tile_written(tile)` hands over a `Tile` and nothing else. An existing statement about a
property constrained the implementation; (j3), at a design doc sentence rather than at a feature.

### (b) AND (c) — TWO PATHS REACH THAT SEAM AND ONLY ONE OF THEM HAS THE OUTCOMES

`run`'s tile loop has two branches. The fit branch computes `result` and calls `write_tile`; the
recompute branch calls `_recompute_tile(...) -> None`, which **copies fits from the source store
and re-ranks them**, and returns nothing. **Both then call `on_tile_written(tile)`.**

**A seam widened to carry `result.outcome` is `None` on the recompute path**, so a
`--reuse-fits-from` run would display counters that silently under-count — or, worse, read as
though nothing failed. **The brief says nothing about this**, and the display is exactly where an
absence looks like a zero.

Two honest shapes, and the choice is Task 4's to take with the reason recorded: **widen
`_recompute_tile` to return what it wrote**, so both branches supply the same thing; or **have the
counters read the tile's region back from the store**, which is exact and costs a read per tile —
and which **contradicts §14.1's "approximate under a resume"**, so taking it means amending that
sentence rather than quietly diverging from it.

### `on_tile_written` IS DOCUMENTED AS A FAULT-INJECTION SEAM, AND TESTS BIND AGAINST IT

`run.py` calls it *"Called between a tile's data write and its completion"*; `twopass.py` calls it
*"Fault-injection seam for pass 2"*. **Reusing it for display broadens a seam whose stated purpose
is testing**, and `test_completion.py` binds against it to preempt runs mid-tile. Widening its
signature touches every binder. **Whether the display gets this seam or its own is a decision, not
a detail** — and the (a3) rule applies: defer the feature, declare the regime. A second seam with
one caller is cheaper to reason about than one seam with two unrelated purposes, and the fault
injectors must keep working either way.
