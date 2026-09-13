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
