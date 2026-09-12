# Phase 2e — the run's own honesty

**Status: AWAITING REVIEW. No code yet.** The head of
[`PROGRESS.md`](../../../PROGRESS.md) is the single source for this plan's status; when it and
this line disagree, the head is right and this line is stale. Same shape as the 692/693 test
count and the 2b table that said *"awaiting review"* for four days after approval.

2e is the first half of design doc §14. It ships **what a run must do while it runs**: the exit
code taxonomy made to discriminate, the input path made to open an ordinary gridded product, the
live counters, and the early abort with the mechanism that produces `CANDIDATE_DROPPED`. It does
**not** ship the report. That is 2f.

## What 2e IS, and the section boundary that says so

**2e is §14.1 and §14.3.** §14.2 — the report computed from the store — is **2f's**, together with
the selectability section, the spatial clustering statistic, the PNG maps and
`python -m metamer.report`.

**The boundary is §17's own rule applied, not a scoping preference.** *"Measure in the phase that
can, print in the phase that shows"* was written into §17 after the same quantity got built twice
and the two versions disagreed — read amplification, the regressor regime with both tile sizes,
and the unique-Δt count. 2e **measures**: it creates dropped candidates, the sixth exit code, and
the abort verdict. 2f **prints**. A report written before its subjects exist is the thing that
rule forbids.

Two properties follow from the line and are worth stating because neither is obvious:

- **Everything in 2e shares a precondition.** A run that cannot open an ordinary `latitude`/
  `longitude` product cannot be honest about anything, so the tiling closer comes early even
  though it is not thematically a failure-reporting change.
- **2f is less blocked than "2e then 2f" suggests.** Stores exist today, `/selection/delta_ic` is
  stored today, `audit_report.py` exists. What 2f actually waits on is **two subjects to count** —
  dropped candidates, and a sixth code to print in the final line. The ordering stays 2e first for
  the reason above; the natural reading that 2f cannot start is wrong and is corrected here.

## Why this plan has no code fences

Same reason as 2a, 2b, 2c and 2d. A fenced block is read as the implementation and stops being
reviewed as a specification; the reviewer checks whether the code is right rather than whether the
behaviour is. **Interfaces appear as signatures only where a later task binds against an earlier
one**, which is a contract rather than an implementation.

## The decisions this sub-phase was planned on

**Fifteen, enumerated.** The count is the enumeration's length and is not asserted separately —
`decimate.py:32` is in this plan's correction list for exactly that mistake.

**D1 — the tiling closer is POSITIONAL THROUGHOUT, and the reason is the fingerprint.** The two
closers are not equivalent in more than cost. `geometry_components` builds `spatial_coordinates`
keyed by **the input's own dimension names**, and that feeds `geometry_hash` and the store's root
attrs. The pipeline order is `open → contract (4a) → geometry` (`run.py:819`, `run.py:854`), so a
rename inside `open_input` sits **upstream of the fingerprint**: every lat/lon product would be
fingerprinted as having axes named `y`/`x`, and **the store would assert a provenance its source
file does not have.** That is a different category of defect from a documentation disagreement,
and it is the one that would have survived unnoticed. Moving the rename downstream of the
fingerprint to avoid it makes it a fifth name-dependent site in the tiling path — which is the
thing being fixed.

**D2 — `decimate.py` is the precedent, and it is the second half of D1.** Its module docstring
already reads `array.dims[1]` and `array.dims[2]` specifically so as not to become *"the fifth
site"*, and records that its arithmetic is correct under either closer. **Positional-throughout
continues a choice this project already took deliberately and wrote down; rename-at-adapter makes
that choice pointless work.**

**D3 — 2e adds `INTERNAL_ERROR` as a sixth exit code, with a catch-all in `__main__`.** Python
reports an unhandled exception as 1, and §14.3 defines 1 as *completed with failures above
threshold*. Those are opposite facts about a run — one says it finished and the map is written,
the other says it did not — so a script resuming on 1 would resume from a crash. `__main__.py`'s
own module docstring already names 2e as the owner: *"Sub-phase 2e is where 1 acquires a producer
and where the two must be made distinguishable."* The weaker fallback — a test asserting exit 1
also asserts the absence of a traceback — **is refused**: it tests the symptom and leaves two
different events sharing a code, which is the collision rather than a fix for it.

**D4 — the code lands BEFORE the tiling closer, on (i2).** `tiling.py`'s `KeyError('y')` is a
**real, currently-reachable producer** of a spurious exit 1, measured twice on 2026-09-07. Closing
tiling first would leave the catch-all's only test a deliberately-raised exception — testing the
mechanism against a mutant nobody has seen in the wild. A pure negative needs a positive control,
and **the live crash is the control, available only until it is fixed.**

**D5 — and therefore the `INTERNAL_ERROR` test carries dated provenance.** Once tiling closes, the
constructed form is all that remains. It is **pinned**, and *"this test was verified against a
live producer on a named date, with its traceback"* is recorded **at the test** as a dated fact.
Same treatment as the version-1 report's missing key, reversed: there what is present is pinned
and the absence is dated; here the constructed test is pinned and its once having matched a live
crash is the dated fact. The alternative — a stub raising the same `KeyError` — is the fabricated
control the ordering exists to avoid, now with provenance attached to it.

**D6 — the vocabulary change is free in the record and not free at the guards. Verified, not
inferred.** Nothing outside the test suite branches on the exit code; the `docs/` hits are
harnesses reading their **own** subprocesses' `returncode`, and **no committed JSON artifact
contains `exit_code` at all.** So no committed record is reinterpreted. Two tests will fail on the
sixth member and **that is them working**: `tests/test_validation.py:58` enumerates the full member
list by name, and `tests/test_runner.py:1001–1009` pins reachability as `{OK, CONFIG_INVALID}`.
Both get the **struck-not-deleted** amendment with the reason recorded at the test.

**D7 — `CANDIDATE_DROPPED` joins the decided skips: out of the failure rate, in its own row.**
`Outcome.is_failure` is `True` for it today and **has never been exercised, because nothing
produces it** — `tests/test_exit_criteria.py:530` says so outright. 2e gives it its first
producer, which makes 2e the first opportunity to find this. §14.1 already decided this once in
the other direction, for the same reason: it corrected `NOT_ATTEMPTED` to `SCREENED_OUT` for the
decided skip **specifically because the code must say who chose**. Having made the drop its own
code so the store records what happened, folding it back into an undifferentiated failure rate
discards exactly the distinction the code was added to preserve.

**D8 — the rule that puts it there is recorded at `Outcome`, not only here.** This is the **second**
member to move into the decided-skip group, and the rule that put `SCREENED_OUT` there is the rule
that puts this one there: *a code the run assigns because the run chose not to fit is a decided
skip, eligible and not a failure.* **A future member gets classified by that rule rather than by
precedent.** `tests/test_outcomes.py:117–134` already reasons `SCREENED_OUT` into the exclusion set
explicitly; the asymmetry that `CANDIDATE_DROPPED` was never reasoned about is kept beside the
rule, because a classification that has never been exercised is a classification that has never
been checked.

**D9 — the feedback loop is the finding, and it is promoted because it generalizes.**

> **Where a run acts on a measurement and records the action in the same field the measurement is
> computed from, the later measurement reports the action. Check every rate's population for
> outcomes the run itself assigned.**

Worked instance: a candidate dropped after failing 91% of pass 1 gets `CANDIDATE_DROPPED` written
across every remaining point, and the end-of-run rate then reads ~100% — **dominated by the
decision already taken about it, and louder than the evidence that triggered it.** The number that
looks like the strongest evidence is the one carrying the least. **Goes to the handoff §1, not
restated in PROGRESS.md.**

**D10 — the drop's row names its own denominator, and it is the first rate here whose denominator
differs between rows of one table.** The denominator is **points where the candidate was still
live**, which is per-candidate. §14.2 already requires every rate to state its denominator; this
one must state it **at the row**, or a reader compares two rows computed over different
populations and the table invites the comparison.

**D11 — computation versus interface, applied to `report`.** §14.2 says the report is *"exposed as
`metamer report <store>`"*; §17's table puts `report` in **Phase 5's** commands row;
`__main__.py`'s docstring says `python -m` is used *"rather than in Phase 5, when `validate` and
`report` are real"*. **The documents were never in conflict about the same thing.** §17 and
`__main__.py` speak about the **command tree**, which stays Phase 5's. §14.2 speaks about the
**computation** — computed from the store rather than from counters, with three consequences:
regenerable, independently testable, usable on a foreign store. Those are properties of the
computation, and **2f owns the computation and the minimal entry point; Phase 5 owns the
subcommand.** The entry point is **`python -m metamer.report <store>`** in module form: a
`--report-only` flag on the run parser would make `config` required-or-not depending on another
flag, which is precisely the argument-structure design `python -m` was chosen to defer.

**D12 — the same resolution, applied to §14.1's display.** §14.1 puts the counters *"on a `rich`
progress display"*; §17's table gives Phase 5 *"the `rich` progress display (§14.1)"* and Phase 2
*"plain lines"*. Same structure, same resolution: **2e owns the counters, Phase 5 owns the `rich`
display. 2e prints plain lines.** Recorded as the same resolution rather than as a second
judgement call.

**D13 — the early abort stays in 2e, and its verdict is a store-reading pure function.** Pass 1 is
a full `run` into its own store (`decimate.pass1_store_path`, `twopass.py:238–247`), with an
explicit seam between the passes at `twopass.py:247–266` where the barrier already sits — so the
abort does read a store. It splits in two and **only one half is a store-reader**:

- **The verdict** — pass-1 store → `{abort, drop <candidates>, continue}`. A pure function of a
  finished store, **unit-testable on a constructed pass-1 store with no run at all.** This is the
  only part of 2e with 2f's testability property, and it is a constraint on the implementation
  rather than an observation about it.
- **The action** — returning before pass 2 with `ABORTED_EARLY`, or demoting a candidate and having
  pass 2 write `CANDIDATE_DROPPED` at every remaining point. This needs `run()` to accept a
  dropped-candidate set, it changes what a run does, and it cannot be tested without one.

The pair stays in 2e **because the action is what §14.1 exists for.** Same shape as §14.2's
computed-from-the-store rule and for the same reason.

**D14 — selectability is a first-class section of EVERY run's report, and the amendment is taken
here while 2f implements it.** §14.2's own opening sentence is the argument: *"a run that quietly
succeeds on 97% of points and returns 0 is the failure mode this section exists to prevent."* A
point where most candidates failed the conditioning gate and the survivor was selected **is that
failure mode** — it returns a selection, the selection was nearly forced, and every per-branch
count reads clean. The decisive property is that this is **visible from a single run's store with
no second arm anywhere**; a design surfacing it only under arm comparison hides it from every
ordinary run, which is all the runs a user will do. The audit is a benchmark instrument; this is a
property of any fit. Putting it in the audit section instead would give the audit a concept that
is not audit-specific, which is how a concept ends up with one consumer and no home.

**And the reason for the reframing goes at §14.2, not only in a record:** the real-data spike
measured §11.2's fear **absent** — zero re-rankings in 289 points, on every arm, positive-
controlled — and measured a **different thing present**: 34% of points selecting differently,
entirely by dropout, start-dependent. A report emphasising the first would emphasise what this
project has shown does not happen, while the thing it did measure has no headline at all.

**D15 — contention is derivable, so no schema change.** `n_valid` counts **fits**; contention
counts **rankable** fits, and `criteria.py:349–351` makes them deliberately different — a fit can
succeed with a non-finite criterion value (AICc at `n ≤ k+1`) and is *"ranked last, not
reclassified as a failure"*. So **`n_valid == 1` is not "the selection was forced"** and
**`n_valid == 0` is not "no survivor"**. All three facts are already reachable:

| quantity | where | granularity |
|---|---|---|
| fits | `/selection/n_valid`, stored | criterion-independent |
| contention | `count(isfinite(/selection/delta_ic))` over `m` | **per criterion** |
| no winner | `/selection/selected == -1` (`-2` is `SELECTED_UNSET`) | per criterion |

`isfinite(delta_ic)` **is** `rankable`, because `delta_ic = values − ic_best` and `rankable =
scored & isfinite(values)`. No array is added, no compat break, and nothing 2a's *"the store cannot
change after data exists"* has to absorb. **`/selection/n_valid` currently has zero production
readers** — `write.py:330` writes it and the only `n_valid` reader in `src/` is
`audit_report.py:355`, which reads the **in-memory** `Ranking`. So 2f adds a reader, not a
measurement.

**The float32 caveat goes at the derivation, not only in a brief.** `delta_ic` is stored float32,
so a finite float64 value can overflow to `inf` on write and be miscounted as unrankable. It is a
claim about the **derived count only**, bounded to catastrophically-bad candidates, and it is
worth a constructed test rather than a schema change — **a derived quantity with a known failure
mode carries that mode where it is derived.**

## The corrections this sub-phase owes

Three, all of the same family, and all found by the pre-flight rather than by a test.

1. **`decimate.py:32` says `tiling.py` takes the literal names *"in four places — the span tuples,
   the `by_dim` lookups and `assemble_tile`'s own `isel`"*.** A count of **four** against an
   enumeration of **three**, inside one sentence, against **six literal occurrences in three
   functions** in the tree. **(c): enumerate, never count.** Corrected to name the three functions.
2. **PROGRESS.md head item 9(a) repeats the "four places" figure.** Corrected at the same time, or
   the two copies drift — which this project has already paid for.
3. **PROGRESS.md's phase table 2e row says 2e owns "`metamer report`".** It is **the only one of the
   four documents that names 2e**, and it is right about ownership and loose about scope. **Amended
   to name which half** — 2e owns the run-time half of §14; 2f owns §14.2's computation and
   `python -m metamer.report`; Phase 5 owns the subcommand. **Amended, not struck:** striking it
   would remove the only correct ownership statement of the four.

## The one decision 2e must take that this plan does not take for it

**A one-pass run has no abort point, and §14.1 reads as though every run gets one.**

`twopass.py:15–21`: `warm_start.enabled = false` runs **exactly one cold `run` over the full grid,
with no coarse store written**. §14.1's entire argument for evaluating on pass 1 is that pass 1 is
*"stratified across the whole domain by construction"* and its barrier is *"a natural decision
point [that] costs nothing because the pass already exists."* **With warm-starting disabled,
neither the stratification nor the barrier exists** — and the only alternative trigger is the
geographically contiguous tile prefix that §14.1 spends four paragraphs forbidding, for reasons
that are correct.

Three readings, and the design doc does not say which:

- **(i) The abort is two-pass-only, and says so.** **The expected survivor.** Pass 1's five jobs all
  exist because pass 1 exists for warm-starting; a probe pass run purely to have something to abort
  on has **one** job and pays a full coarse fit for it.
- **(ii) A one-pass run gets a decimated probe pass** solely to have a stratified sample to abort on.
- **(iii) §14.1's guarantee is weakened for one-pass runs**, and the weakening is stated.

**If (i) survives contact, the limitation is stated in §14.1 itself, not only in 2e's record** —
§14.1 currently reads as though every run gets an early abort, and that is a documented limitation
rather than a feature.

## Standing requirements for every task

- **Run the pre-flight against the task brief before code**, and append the entry to
  `phase2e-preflight.md` **before** the task, not after. The method lives in exactly one place —
  [the handoff](../notes/phase1-to-phase2-handoff.md) §1 — and is not restated here.
- **`pixi run test` is the full sweep and every end-of-task verification runs it.** `test-fast` and
  `test-ci` are not evidence; the full sweep has caught eight things a fast run could not.
- **`git add` a new file before `pre-commit run --all-files`, never at commit time.** `--all-files`
  covers tracked files only. **And stage anything a tool may restore**: `git checkout -- <file>`
  restores from the index, so an unstaged edit in a file any tool touches is silently reset to
  `HEAD` with no error.
- **Commit after every task, and check CI after every push.** Red CI is the next task. **One push
  per run** — a second push cancels the run verifying the first, and that rule has been broken
  three times. **Wait for green before the next commit whenever the previous one is still in
  flight**, and verify by the until-loop on the run's own `status`, never by `gh run watch
  --exit-status` and never by position in `gh run list`.
- **No exit-criterion verdict from 2a, 2b, 2c or 2d moves.** 2e adds behaviour; it reopens no
  residency model, re-cuts no stratum boundary, and closes no inherited failure.
- **No task moves `PUBLISHED_TILE_SIDE`, `HEADROOM_FRACTION`, `resident_bytes_per_series`,
  `output_slot_bytes`, `SVD_CHUNK_SERIES` or `ALGORITHM_VERSION`.**
- **No `Outcome` member is renumbered.** The codes are written to the zarr store; a new member takes
  the next free code and bumps the store's schema version. **2e adds no member** — the alphabet is
  2a's and is complete.
- **Every changed classification states what it moves and what it does not**, verified against the
  committed artifacts rather than inferred from them.

## Task index and dependencies

| # | task | depends on | state |
|---|---|---|---|
| 0 | the corrections, and the §14 amendments | — | pending |
| 1 | `INTERNAL_ERROR`, the catch-all, and the live producer as its control | 0 | pending |
| 2 | the tiling closer — positional throughout | 1 | pending |
| 3 | `CANDIDATE_DROPPED` joins the decided skips | 0 | pending |
| 4 | the live counters — point-granularity, display-only, plain lines | — | pending |
| 5 | the abort verdict — a pure function of a pass-1 store | — | pending |
| 6 | the abort action, the `CANDIDATE_DROPPED` producer, and the one-pass decision | 3, 5 | pending |
| 7 | the 2e exit-criteria suite | all | pending |

**Task 1 before Task 2 is D4 and is not negotiable by convenience** — the ordering exists so the
catch-all has a live producer to be verified against, and Task 2 destroys it.

---

## Task 0 — the corrections, and the §14 amendments

**Goal.** The documents say what the tree does and what this sub-phase decided, **before** any code
changes either.

**Behaviour.**

- **The three corrections above are applied**: `decimate.py:32`'s count against its enumeration,
  PROGRESS.md head item 9(a)'s repetition of it, and the phase table's 2e row amended to name which
  half of §14 2e owns.
- **§14.2 gains the selectability section** (D14), with the reason recorded there: the spike
  measured §11.2's fear absent and a different thing present, and a report emphasising the first
  would emphasise what this project has shown does not happen. **The three quantities and their
  denominators are named**; the implementation is 2f's.
- **§14.1 gains the resolution of its own display sentence** (D12) and, once Task 6 takes it, the
  one-pass limitation.
- **§14.3 gains `INTERNAL_ERROR`** as intent, with the collision it closes stated.
- **D9's rule goes to the handoff §1**, with its worked instance. **Not restated in PROGRESS.md.**

**Invariants.**

- **No measurement is stated twice.** Any number appearing in both the design doc and a record has
  one copy **deleted**, never reconciled.
- **A retired argument stays visible.** Struck, not removed, wherever the reasoning is the
  transferable part.

**Tests, and the bug each catches.**

- *The tiling path's name-dependent sites are enumerated by a test that reads the tree, and the
  enumeration matches the documents.* Catches exactly the defect being corrected — a count
  maintained by hand against a tree that moved. **(a0)'s sixth register: a check that never read
  the file prints the same word as one that did**, so this test must fail when a site is added.

---

## Task 1 — `INTERNAL_ERROR`, the catch-all, and the live producer as its control

**Goal.** An unhandled exception and a thresholded run stop sharing a code, verified against a
crash that is real today.

**Behaviour** (§14.3, D3, D4, D5).

- **`ExitCode` gains `INTERNAL_ERROR`** at the next free value, **appended** — no member is
  renumbered, because the numbers are a published interface a shell script may already branch on.
- **`__main__` gains a catch-all** that maps any exception not already staged to `INTERNAL_ERROR`,
  **and the traceback is still printed.** A traceback can be suppressed and an absence is not a
  signal — (i2) — so the code carries the fact and the traceback carries the detail.
- **The staged catches keep precedence.** `ValidationError` and `InputContractError` continue to
  produce 3 and 4; the catch-all is the last clause, never the first.
- **Argparse's usage error keeps exiting `CONFIG_INVALID`.** `_Parser.error` is unchanged.

**Invariants.**

- **The six codes are the six the taxonomy names**, enumerated member by member, never counted.
- **`COMPLETED_WITH_FAILURES` still has no producer after this task.** It acquires one at Task 6.
  Until then any observed 1 is still a crash — but now a crash exits `INTERNAL_ERROR`, so an
  observed 1 is a **defect in this task**, which is a stronger statement than the one it replaces.

**Interfaces** (Tasks 6 and 7 bind against these):

    class ExitCode(IntEnum): OK; COMPLETED_WITH_FAILURES; ABORTED_EARLY;
                             CONFIG_INVALID; DATA_INVALID; INTERNAL_ERROR

**Tests, and the bug each catches.**

- ***The live producer, before Task 2 closes it.*** A run against a `latitude`/`longitude` store
  exits `INTERNAL_ERROR` and prints a traceback naming `tiling.py`. **This is the positive
  control and it is available only in this task** — Task 2 removes the crash. Catches a catch-all
  that is never reached because a staged clause swallows the error first, which no constructed test
  would find.
- *The same test records its provenance: the date it was verified against the live producer, and
  the traceback's own frame.* **Catches the constructed replacement drifting into a test of
  itself.** Without this, the guard that remains after Task 2 is a mechanism checked only against a
  mutant it was written alongside.
- *The six exit codes are the six the taxonomy names, enumerated by name and value.* Catches a
  member renumbered, added or dropped. **The amendment to `tests/test_validation.py:58` is
  struck-not-deleted**, with the reason at the test.
- *Reachability is re-enumerated.* `tests/test_runner.py:1001–1009` pinned `{OK, CONFIG_INVALID}`;
  it now pins whatever is reachable **and says why each is or is not**, struck-not-deleted. Catches
  a code becoming reachable without anyone noticing which.
- *A `ValidationError` still exits 3 and an `InputContractError` still exits 4.* Catches a catch-all
  placed above the staged clauses, which would collapse the whole taxonomy into one code and pass
  every test that only checks the new one.

---

## Task 2 — the tiling closer: positional throughout

**Goal.** The implementation matches the contract as stated, and an ordinary gridded product runs
end to end.

**Behaviour** (D1, D2, head item 9(a)).

- **`tiling.py` takes the spatial dimensions positionally** — `array.dims[1]` and `array.dims[2]` —
  in all three functions that currently take them by name: `read_amplification`'s span tuples and
  `by_dim` lookups, `assembly_spans`' `by_dim` lookups, and `assemble_tile`'s `isel`.
- **`time` stays name-based.** `time`-first **is** the contract, `input.py:313` enforces it, and
  nothing here relaxes it.
- **Stage 4a's message is unchanged** — *"the contract is three, mapping to (time, y, x)"* — and
  **becomes true.** No amendment to §13.6 is needed, and that outcome is available only under this
  closer.
- **`Tile`'s `y_start`/`x_start` vocabulary is unchanged.** Those name **axis 1 and axis 2 of the
  output store**, which is metamer's own product with its own schema, and they are not claims about
  the input.
- **Nothing renames the input.** The geometry fingerprint continues to record the names the source
  file has.

**Invariants.**

- **No literal input dimension name outside `time` remains in the tiling path**, checked by
  enumeration rather than by review.
- **`geometry_components` is untouched**, so a lat/lon store fingerprints as `latitude`/`longitude`.
- **Every existing `y`/`x` fixture still passes.** The change is a widening; a narrowing anywhere is
  a defect.

**Tests, and the bug each catches.**

- *A synthetic `latitude`/`longitude` store runs end to end and exits `OK`, with the fitted point
  count asserted.* The case measured as broken on 2026-09-07. Catches the closure being partial —
  three sites fixed and one missed reads as success until the fourth is reached.
- *The same store's `geometry_hash` inputs record `latitude` and `longitude`.* **Catches the rename
  closer being taken by accident**, which would pass every functional test and write a false
  provenance. This is D1's argument as an assertion.
- *A `lat`/`lon` store and a `y`/`x` store both run, and their geometry hashes differ.* Catches a
  fingerprint that normalizes names away, which would make two different inputs claim one identity.
- *A two-dimensional input and a `time`-last input are still refused with `InputContractError` and
  exit 4.* Catches positional access being mistaken for "no contract", which would turn a staged
  refusal into an `IndexError` and, after Task 1, into `INTERNAL_ERROR`.
- *`read_amplification` returns the same number for a store renamed from `y`/`x` to
  `latitude`/`longitude` with no other change.* **The invariance that says the quantity is about
  the data and not the labels.** Catches a positional rewrite that silently transposes the axes —
  which would give a plausible wrong number rather than an error.
- *The enumeration test from Task 0 now finds zero name-dependent sites.* Catches the correction
  being applied to the documents and not to the tree.

---

## Task 3 — `CANDIDATE_DROPPED` joins the decided skips

**Goal.** A code the run assigns because the run chose not to fit stops being counted as a fit that
failed — and the rule that decides that is written down where the next member will be classified.

**Behaviour** (D7, D8, D9, D10).

- **`Outcome.CANDIDATE_DROPPED.is_failure` becomes `False`.** It stays `is_eligible is True`: the
  point was a real candidate for fitting, and excluding it from the denominator would hide the drop
  rather than report it.
- **The rule is recorded at `Outcome`**, not only in this plan: *a code the run assigns because the
  run chose not to fit is a decided skip — eligible, and not a failure.* **`SCREENED_OUT` and
  `CANDIDATE_DROPPED` are its two members, and a future member is classified by the rule rather
  than by precedent.**
- **The asymmetry is kept beside the rule.** `SCREENED_OUT` was reasoned into the exclusion set
  explicitly; `CANDIDATE_DROPPED` was not, and nothing noticed **because nothing produces it**. A
  classification that has never been exercised is a classification that has never been checked.
- **The drop is reported in its own row, with its own denominator named at the row** — *points where
  the candidate was still live*. **This is the first rate in this project whose denominator differs
  between rows of one table**, and the table says so, or a reader compares two rows computed over
  different populations. The row itself is 2f's; the denominator's definition is fixed here because
  Task 6 is what makes it computable.

**Invariants.**

- **No committed number moves.** Verified rather than inferred: no committed JSON artifact contains
  `candidate_dropped`, `is_failure` or any `is_failure`-derived field, and the only committed
  outcome histogram — `realdata-spike2-report.json` — contains exactly `{OK, DEGENERATE_HESSIAN}`.
  **The set this reclassification partitions is empty in every committed store.**
- **`audit_report.py`'s lookup table picks the change up automatically** and is not special-cased.
  A second place that classifies outcomes is a second place that can disagree.

**Tests, and the bug each catches.**

- *`CANDIDATE_DROPPED.is_failure is False` and `.is_eligible is True`, both asserted.* Catches a
  half-move — out of the failure set and out of the denominator too — which would make a drop
  **invisible** rather than separately reported, and would read as an improvement.
- *Every `Outcome` member's two properties are enumerated in one table.* Catches a future member
  landing in neither group or in both, and makes the decided-skip group readable at a glance rather
  than derivable from two exclusion lists.
- *A constructed outcome array containing `CANDIDATE_DROPPED` yields a failure rate that ignores it
  and an eligible count that includes it.* **The arithmetic, not the properties.** Catches a lookup
  table built once at import and not rebuilt, which is how the property and the behaviour come
  apart.
- *The committed audit reports' numbers are recomputed under the new classification and are
  unchanged.* **Catches the "nothing moves" claim being an inference.** This is the check D6 and
  note 1 both require, and it is cheap because the partitioned set is empty.

---

## Task 4 — the live counters: point-granularity, display-only, plain lines

**Goal.** A long run says what it is doing, and nothing can ever decide on what it says.

**Behaviour** (§14.1, D12).

- **Counters are point-granularity, accumulated and displayed per tile**, by taxonomy branch and by
  candidate. A tile-granularity verdict is meaningless at ~10⁵ points per tile.
- **They are DISPLAY-ONLY, and the code says so.** No decision may read them. **Marked deliberate in
  the code**, because the obvious future change — *"we already have these tallies, let's abort on
  them"* — reintroduces the tile-prefix bias §14.1 exists to avoid, and **it will look like a free
  optimization.**
- **Plain lines, not `rich`.** §17's table gives Phase 2 plain lines and Phase 5 the `rich`
  progress display. 2e owns the counters; Phase 5 owns the display.
- **Their approximation under a resume is harmless and is stated as such**, because the abort reads
  pass 1's stored status and §14.2's report is computed from the store — the counters sit in **no
  decision path.**

**Invariants.**

- **No module outside the display imports the counters.** Enforced by construction, not by comment.
- **A resumed run's counters may be wrong and nothing depends on them.** Said once, in the code.

**Tests, and the bug each catches.**

- *The counter object is not reachable from the abort verdict or from any run-control path.* Catches
  the free-optimization change the moment it is written, rather than at the review that misses it.
- *Counters accumulate per point, not per tile.* Catches a tile-granularity tally that would read as
  a plausible progress display and be useless at the scale it exists for.
- *A resumed run's counters differ from an uninterrupted run's, and no asserted outcome does.*
  **The positive control on "harmless"** — (i2). Catches the counters being quietly made
  resume-exact, which would suggest something depends on them.
- *The display writes plain lines and imports no `rich` symbol.* Catches Phase 5's interface being
  pulled forward, which would design the progress display before `validate --explain` exists to say
  what it should look like.

---

## Task 5 — the abort verdict: a pure function of a pass-1 store

**Goal.** The decision, separable from the run that acts on it, and testable without one.

**Behaviour** (§14.1, D13).

- **Input is a finished pass-1 store. Output is a verdict**: `continue`, `abort`, or `drop` with the
  candidate set named.
- **Thresholds are calibrated to catch bugs, not to second-guess science.** All candidates above 90%
  failure → **abort**, a config or data error. A single candidate above 90% → **abort by default**,
  subject to the policy Task 6 wires.
- **The rate is `Outcome.is_failure` over `Outcome.is_eligible`**, the definitions already shipped
  and already consumed by `audit_report.py:556–568`. **2e does not invent a second one.**
- **The verdict names its own numbers** — per candidate: the failure count, the eligible
  denominator, and the rate — so the reason a run stopped is readable without recomputing it.
- **It is a pure function.** No clock, no filesystem beyond the store it is given, no process state.

**Invariants.**

- **Determinism.** The same store gives the same verdict.
- **The verdict is computed over the whole pass-1 store**, never over a prefix of tiles. Pass 1 is
  stratified across the domain by construction; a prefix is a geographically contiguous strip, and
  on a global grid that is a polar band or a single basin.
- **An incomplete pass-1 store yields no verdict**, it raises — a rate over a partial store is a
  rate over a spatial prefix wearing a whole-domain name.

**Interfaces** (Task 6 binds against these):

    class CandidateRate: candidate: str; failed: int; eligible: int; rate: float
    class AbortVerdict: action: Literal["continue", "abort", "drop"];
                        candidates: tuple[str, ...]; rates: tuple[CandidateRate, ...];
                        threshold: float; reason: str
    abort_verdict(pass1_store, *, threshold, policy) -> AbortVerdict

**Tests, and the bug each catches.**

- *A constructed pass-1 store with one candidate at 95% and the rest at 5% yields `drop` naming that
  candidate.* **The core case, with no run anywhere.** Catches a verdict that can only be exercised
  through a full two-pass run, which would make every later test of it expensive and therefore rare.
- *A constructed store with every candidate at 95% yields `abort`, not `drop`.* Catches the
  all-candidates branch being folded into the single-candidate one, which would demote every
  candidate and continue with none — a run that proceeds having decided nothing can be fitted.
- *A store at 89.9% and one at 90.1% land on opposite sides.* Catches an inclusive/exclusive slip at
  the threshold, which is invisible on any realistic fixture.
- *`INSUFFICIENT_DATA` and `NOT_APPLICABLE` points change neither numerator nor denominator, and a
  store that is 99% land yields the same verdict as the same store cropped to its ocean.* **Catches
  a rate dominated by land**, which is the failure §14.2's denominator rule exists for, and which
  would make every global run abort.
- *`SCREENED_OUT` points are in the denominator and not in the numerator.* Catches the decided-skip
  group being applied to one member and not the other — the exact asymmetry Task 3 exists to close.
- *An incomplete pass-1 store raises rather than returning a verdict.* Catches a rate computed over
  a spatial prefix and reported as a whole-domain number.
- *The verdict is unchanged when the same store is passed twice, and no attribute of it depends on
  the working directory, the clock or the process.* (k) — catches process-local state leaking into
  a decision that must be reproducible from an artifact.

---

## Task 6 — the abort action, the `CANDIDATE_DROPPED` producer, and the one-pass decision

**Goal.** The verdict changes what the run does, the store records what happened, and a one-pass
run's behaviour is decided rather than accidental.

**Behaviour** (§14.1, §14.3, D13, D10).

- **The verdict is evaluated at the barrier**, between pass 1 and pass 2, at `twopass.py`'s existing
  seam. It is not evaluated on a prefix of tiles, and there is no second decision point.
- **`abort` returns `ABORTED_EARLY`**, which §14.3 defines as resumable, with the verdict's numbers
  on the final line.
- **`drop` demotes the named candidates and continues.** Pass 2 writes **`CANDIDATE_DROPPED` at
  every remaining point** for them — not `NOT_ATTEMPTED`, which means *nothing wrote here*.
- **`--on-candidate-failure={abort,drop,continue}`** selects the single-candidate policy;
  **`--no-early-abort`** disables the whole mechanism for datasets where high failure is genuinely
  expected.
- **`COMPLETED_WITH_FAILURES` acquires its producer here.** A run that completes with a failure rate
  above threshold and was not aborted exits 1 — **and after Task 1 that is no longer the code a
  crash produces.**
- **A SIGTERM during pass 1 still returns without entering the barrier**, with no verdict and no
  pass-2 report. The existing behaviour is unchanged: a preempted run is exit 2, and calling the
  barrier on it would raise a layer-3 error and exit 3.
- **The one-pass decision is taken here**, from the three readings above, and **whichever is taken is
  written into §14.1** — because §14.1 currently reads as though every run gets an early abort.

**Invariants.**

- **A dropped candidate's points are `CANDIDATE_DROPPED` and nothing else.** No point gets it in
  pass 1, which is where the evidence came from.
- **The drop is a headline, not a buried counter.** The final line names the dropped candidates.
- **`--no-early-abort` runs the same fits as a run whose verdict was `continue`** — byte-for-byte.
  The flag disables a decision, not a computation.
- **No `Outcome` member is added.** `CANDIDATE_DROPPED` is 2a's and its code is 9.

**Tests, and the bug each catches.**

- *A two-pass run whose pass 1 fails one candidate above threshold completes, and that candidate's
  pass-2 points are all `CANDIDATE_DROPPED` while the others are fitted.* The mechanism end to end.
  Catches a drop that stops the run, and a drop that silently fits the candidate anyway.
- *The dropped candidate's points are `CANDIDATE_DROPPED` and not `NOT_ATTEMPTED`.* Catches the
  correction §14.1 already made being undone — *nothing wrote here* and *we decided not to* are
  different facts, and the store is where they are distinguished.
- *That run's per-candidate failure rate excludes the dropped points, and its drop row reports the
  count over "points where the candidate was still live".* **Catches D9's feedback loop**: a rate
  computed over points whose outcome was set by the decision about that rate's subject measures the
  decision. Without this test the candidate reads ~100% and the number looks like the strongest
  evidence while carrying the least.
- *A run with every candidate above threshold exits `ABORTED_EARLY`, and the store is resumable.*
  Catches an abort that leaves an unresumable store, which would make exit 2 a lie in the one place
  a script branches on it.
- *`--no-early-abort` on the same fixture completes, and its store is byte-for-byte identical to the
  same run under a `continue` verdict.* **The positive control on "the flag disables a decision, not
  a computation"** — catches the flag changing what is fitted.
- *`--on-candidate-failure=continue` keeps the candidate and fits it; `=abort` stops.* Catches a
  policy argument that is parsed and ignored — (a2c), populated but nothing acts on it.
- *A run that completes with a failure rate above threshold exits `COMPLETED_WITH_FAILURES`, and a
  run that crashes exits `INTERNAL_ERROR`.* **The two codes asserted in one test**, because the
  whole point of Task 1 is that they are different facts. Catches the collision being reintroduced
  by a later catch clause.
- *A SIGTERM during pass 1 exits `ABORTED_EARLY` with no verdict computed.* Catches the barrier
  being entered on an incomplete store, which Task 5 raises on and which would surface as exit 3 —
  *"your configuration is wrong"* for a run that was preempted.
- *The one-pass behaviour matches the decision taken, in both directions* — if two-pass-only, a
  one-pass run performs no abort **and says so**; if a probe pass, it runs and its cost is asserted.
  Catches the decision being taken in a document and not in the code.

---

## Task 7 — the 2e exit-criteria suite

**Goal.** One suite, one verdict per criterion, each naming the reading that decides it.

**Behaviour.** Each criterion below gets a test whose name is the criterion, whose assertion is the
named reading, and which **fails loudly rather than skipping** when its subject is absent. A
criterion met with reduced scope says so in the closing table with the reduction named; a failed
criterion stays **FAILED** and is not quietly re-scoped.

| # | criterion | reading |
|---|---|---|
| 1 | A `latitude`/`longitude` store runs end to end through the shipped entry point | the exit code, and the fitted point count |
| 2 | No literal input dimension name outside `time` remains in the tiling path | the enumeration of sites, **by function and by occurrence** |
| 3 | The geometry fingerprint records the input's own dimension names | `spatial_coordinates`' keys for a lat/lon store, against the file |
| 4 | Read amplification is invariant under renaming the spatial axes | the two numbers, same store, two namings |
| 5 | An unhandled exception exits `INTERNAL_ERROR`, with its traceback | the exit code **and** the traceback's presence |
| 6 | The six exit codes are the six the taxonomy names | the enumerated member list, by name and value |
| 7 | `INTERNAL_ERROR`'s guard names the live producer it was verified against | the dated provenance **at the test** |
| 8 | `CANDIDATE_DROPPED` is outside the failure rate and inside the eligible denominator | both properties, enumerated |
| 9 | No committed audit number moves under the reclassification | every committed report's outcome histogram, recomputed |
| 10 | The counters are display-only and no decision path reaches them | the construction, **both directions** |
| 11 | The abort verdict is a pure function of a finished store | the verdict on a constructed pass-1 store, **with no run** |
| 12 | The verdict is invariant to the eligible-excluded population | the same store, cropped to its ocean |
| 13 | A candidate above threshold on pass 1 is dropped, and pass 2 records `CANDIDATE_DROPPED` everywhere remaining | the store's outcome array for that candidate |
| 14 | The drop's reported rate names its own denominator and excludes the dropped points | the row, and the denominator beside it |
| 15 | `--no-early-abort` changes the decision and not the computation | the two stores, byte-for-byte |
| 16 | `COMPLETED_WITH_FAILURES` and `INTERNAL_ERROR` are produced by different events | both exit codes, in one test |
| 17 | A one-pass run's abort behaviour is the decided one, and §14.1 states it | the run's behaviour, **and the design doc's own sentence** |

**Two criteria are inherited rather than new, and 2e does not close them.**

**2b's criterion 6 stays FAILED** — peak RSS 2410.0 ± 46.0 against a 617.3–1389.0 band, outside by
22σ. **2b's criterion 7 stays FAILED** — the budget fails above roughly `B = 1500` at all three
fixtures. **2e does not reopen the residency model and must not be read as having closed either.**
2c did not; 2d did not; 2e does not.

**Invariants.**

- **No criterion is met by a test that cannot fail.** Every one names the bug it catches.
- **A criterion whose subject was removed by a later task carries its provenance** — criterion 7 is
  the worked case, and it is the reason Task 1 precedes Task 2.

---

## What 2f inherits

- **Two subjects to count**: dropped candidates, and a sixth exit code to print in the final line.
- **A run that opens an ordinary gridded product**, so a report can be pointed at this project's
  only real dataset rather than at a renamed copy.
- **A decided-skip group with a rule**, so the report's rates partition outcomes the same way the
  run does.
- **Three selectability quantities already stored or derivable** — fits, contention, no-winner —
  with their denominators named and the float32 caveat sited at the derivation.
- **§14.2 amended to lead with selectability**, with the reason recorded there: the spike measured
  §11.2's fear absent and a different thing present.
- **`python -m metamer.report <store>` as the entry point**, in module form, with the command tree
  still Phase 5's.
