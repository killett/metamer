# Phase 2f pre-flight, per task

The method lives in [the handoff](phase1-to-phase2-handoff.md) §1 and is not restated here.
**Entries are appended BEFORE each task, not after.** This file carries what the audit of each task
brief found and what each finding changed.

---

## Pre-plan — open question 24's artifact check, and what checking it found (2026-09-19)

**THE BRIEF** was the standing instruction filed by 2e: before touching `Outcome.is_eligible`,
check whether any committed artifact carries a rate computed under the current rule — the same
check 2e's Task 3 ran for `CANDIDATE_DROPPED` and found the empty set. **Four findings, and the
first one changes what open question 24 IS.**

### (a5) THE FLIP IS A GATE CHANGE WEARING A DENOMINATOR CHANGE'S CLOTHES

2e recorded the cost as *"moving it re-baselines every failure rate the project computes"*. That
undercounts it. `is_eligible` is False for exactly two members, and §12.5 says `NOT_APPLICABLE` is
**underivable today** — so `INSUFFICIENT_DATA` is the **only reachable producer** of an empty
eligible population, and `abort.py`'s `_decide` reaches `no_evidence` precisely when every
candidate's `rate is None`, which is precisely when `eligible == 0`.

**So the flip, taken naively, removes `no_evidence`'s only producer** — a mechanism decided on
2026-09-18, three commits earlier — and turns an all-`INSUFFICIENT_DATA` coarse sample from a loud
*"the sample holds no evidence"* into `continue`, *"no candidate failed above 90%"*. A clean pass
reported over a sample where nothing was fitted: the exact failure (b) was chosen to prevent,
re-entering through a different door. `tests/test_abort.py`'s fixture is built from
`np.full(INSUFFICIENT_DATA)` and nothing else, so criterion 19 would have lost its producer too.

**A report is re-baselined; a gate changes what runs do.** Recorded because the difference is the
whole reason this is a decision rather than an edit.

### THE REPAIR IS A DEFECT THE CHECK FOUND, NOT A COST OF THE CHANGE

The gate's subject is *nothing was fitted*; it was asking *nothing was eligible*. Those coincide
only under §8.6's reading. **The repair is correct independent of the flip and provable independent
of it**, which is why it lands first and in its own commit: criterion 19's fixture keeps its
producer under the *current* eligibility rule, so the repair goes green before the re-baselining
exists.

**Constructed red, before any implementation:** an all-`SCREENED_OUT` coarse sample — eligible,
not a failure — gave every candidate `0 / 20 = 0.0` and returned `continue`. `assert 'continue' ==
'no_evidence'`.

### (c5) THE PREDICATE IS ENUMERATED POSITIVELY, AND THE DIRECTION IS THE FINDING

`outcome not in {INSUFFICIENT_DATA, NOT_APPLICABLE, NOT_ATTEMPTED}` — the obvious spelling — is
(c5)-shaped twice over: it open-codes a set in `abort.py` rather than asking `Outcome`, **and** it
omits `SCREENED_OUT` and `CANDIDATE_DROPPED`, which §12.5's own table calls non-fits. So an
all-`SCREENED_OUT` sample would still have read as judged.

`Outcome.is_fit_verdict` asks the question directly and gives §12.5's grouping table a **third
consumer**. It is written as a **positive** membership test over §8.6's nine fit verdicts — the
opposite direction from its two siblings — because every member added since Phase 1 has been a
non-fit code, so a new member defaulting *into* the fit set is the dangerous direction.

### THE ARTIFACT CHECK ITSELF: THE SET IS EMPTY, AND THE INSTRUMENT THAT SAID SO BEFORE REACHED HALF OF IT

**Sixteen outcome histograms across five committed artifacts; zero carry `INSUFFICIENT_DATA`, zero
carry `NOT_APPLICABLE`.** Exactly one committed family carries a denominator reaching
`Outcome.is_eligible` — `wiring-one-measured.jsonl`'s `attempted` / `both_ok_fraction` — and there
`attempted == audited_points == 52` on both branches for all three candidates, so nothing was
excluded and the flip cannot move it. Every other committed rate uses a denominator that never
reads the property.

**And 2e's criterion-9 helper reaches 8 of those 16.** It globs `notes/*.json` for the key
`outcome_counts`; the tree also spells it `counts` (six histograms, both realdata-spike files) and
also carries histograms in `.jsonl` (two, `phase2d-difficulty-rung-measured.jsonl`) — **all inside
the criterion's own declared population**. Its conclusion stands for `CANDIDATE_DROPPED`, which
appears nowhere; its reading, *"every committed report's outcome histogram"*, overstates its reach
by half, and three of the eight it misses carry `TRUST_RADIUS_COLLAPSED`, so the positive control
was available in the unreached half too.

**This is 2e's own instrument finding 1 recurring inside the sub-phase that wrote it** — *a sweep
built from the phrasings you have found cannot reach the phrasings you have not* — and it is the
strongest available argument for why the machine-readable home was the right deliverable. **2f's
check was written independently for that reason and does not reuse the helper.**

### WHAT MOVES, STATED RATHER THAN ELIDED

No committed artifact moves. **One expected value inside 2e's own criterion-13 test does**: it
computes `live == 9` using `is_eligible` as a denominator. Recomputed and said so at the test.
"No committed artifact moves, one test's expected value does" is the honest form of "the set is
empty".

### FILED, NOT TAKEN: `audit_report`'s SURVIVAL DENOMINATOR HAS THE SAME DEFECT

`audit_report.py:1269` — `attempted = _eligible(cold_code)`, consumed by `both_ok_fraction`, whose
label reads *"both_ok_fraction over attempted cells"*. **The label says attempted; the predicate
reads eligible** — D1's tell, in a second place. It is already slightly wrong today (it counts
`NOT_ATTEMPTED` cells, never tried) and the flip widens it to cells that could never fit under
either arm, which makes the report claim conditioning-on-survival where there is none.

On `test_a_not_attempted_cell_is_in_no_flip_denominator`'s fixture: **30** today, **40** after the
flip, **20** under `is_fit_verdict`. **No committed number moves under any of the three** — the
wiring-one artifacts are all `OK` or `DEGENERATE_HESSIAN`, both fit verdicts, so 52 under all of
them.

**Raised as its own decision and not taken**, on the same rule that separated the gate from the
flip: a correction that cannot move a number and a correction that moves the audit's meaning are
different acts, and bundling them lets the second ride in on the first's evidence.

### PARKED FOR THE NEXT `src/` OR `tests/` COMMIT — TRANSCRIPTION, NOT RECOLLECTION

**Two one-line edits are owed to files whose commits cost a 1:38 sweep.** Parking the TEXT here
rather than the intention, because *"it reaches the tree with the next commit"* is a promise with
no owner and dies with the session — the same shape as a constant that "joins the do-not-move
list" that does not exist yet. Whoever makes the next `src/` or `tests/` commit transcribes these.

**1. `Outcome.is_fit_verdict`'s pattern table gains rows 4 and 5.** It currently holds three. Add,
verbatim:

| gate | it read | its subject |
|---|---|---|
| the plan-review fetch (2026-09-19) | a **cached** 404 and a **summarised** directory listing | the repository's bytes — `curl` returned HTTP 200 and 52,010 bytes on the identical URL |
| 2e's criterion-9 instrument | what one glob and one key spelling happened to walk — 8 of 16 | the committed audit numbers its claim named |

and change *"Three gates in this project"* to *"Five gates in this project"*, keeping the sentence
that all of them coincide with their subject in the common case and diverge exactly where the gate
matters.

**2. `tests/test_hashing.py::test_compat_relevance_is_an_allowlist_golden_set` gains a line saying
its reach is wider than its name.** Verbatim: *"THE NAME READS NARROWER THAN THE SUBJECT: this test
pins BOTH allowlists. `fit_payload` subsets `FIT_RELEVANT_FIELDS`, pinned above; `compat_payload`
subsets `COMPAT_RELEVANT_FIELDS`, pinned through its definition in terms of fit. `run_payload` has
no allowlist by design — it is `normalize(config)` entire, provenance only and never a gate — so
there is no third set to pin and none is missing."* Checked 2026-09-19 against `hashing.py`.

### THE HOLD ON COMMIT 2, NAMED — AND D2 IS NOT OVERSTATED

**D2's artifact check is complete and its claim stands**: sixteen histograms, zero carrying either
code, one eligibility-derived denominator at 52 of 52, and **no committed number moves under any of
the three candidate predicates** — today's `is_eligible`, the flipped `is_eligible`, or
`is_fit_verdict`. Checked, not inferred.

**The hold's subject is a different question, and it is a decision rather than a measurement:**
should `audit_report`'s survival denominator be *repaired* to read `is_fit_verdict` at the same
time, given that the flip widens a defect that is already there? Nothing in the artifact record
answers that, because no artifact distinguishes the three predicates. **Recorded here so the hold
outlives the session**; the plan's commit table points at this entry.

### WHAT THIS ENTRY CHANGED

- Open question 24 became **three commits, gate → flip → record**, from the two the brief assumed.
- `Outcome.is_fit_verdict` exists, which the brief did not call for and which D3 then reused as the
  clustering graph's population — so the unfinished-store case needs no special handling.
- `fitted` entered the persisted `early_abort.rates[]`: the verdict is decided on a quantity that
  was absent from its own record, and "no candidate had a fit verdict anywhere" is not recoverable
  from `eligible` and `rate`.
- 2e's criterion 9 gained a correction, and the handoff gained the rule that permits it.


---

## Plan Task 1 — the reader, audited before any code (2026-09-20)

**THE BRIEF** is the plan's Task 1: open a finished store read-only, refuse an unknown
`schema_version` with `DATA_INVALID`, expose labels/attrs/completion with the bitmap authoritative,
and hold an import boundary excluding matplotlib and the fit path. **Two findings, and the second
one says the plan contains a false mechanism.**

### (g) THE PLAN'S D10 NAMES AN IMPORT THAT DOES NOT WORK THAT WAY

D10 says, in the plan, on main: *"Note `import metamer.core` drags `core.fit` and every family, so
the report imports `metamer.core.outcomes` as a leaf."*

**There is no such thing as importing a submodule as a leaf.** Python executes a package's
`__init__.py` on any submodule import, and `metamer/core/__init__.py` imports `families` (a
deliberate registration side effect, documented there and load-bearing — without it
`TermSpec.engine_costs()` raises on an empty registry) and `core.fit`. **Measured, not reasoned:**

| import | seconds | modules | heavy members present |
|---|---|---|---|
| `metamer` | 0.001 | 64 | — |
| `metamer.core.outcomes` | **0.500** | **708** | `metamer.core.fit`, `scipy` |
| `metamer.batch.store` | 0.688 | 928 | + `zarr` |
| `metamer.batch.run` | 1.425 | 1002 | + **`pydantic`** |

**So Task 1's import-graph test would have failed on its first run**, against an invariant the plan
states and a mechanism that cannot hold. Found before code, which is the whole point of running the
pre-flight against the brief rather than after.

### WHAT THE INVARIANT SHOULD HAVE SAID, AND IT IS SHARPER THAN WHAT IT DID SAY

**`numba` and `matplotlib` are absent from every one of those graphs.** What `metamer.batch.run`
adds over `metamer.batch.store` is **`pydantic`** — the config machinery — and 0.74 s.

**That is the property worth holding, and it is the foreign-store claim in mechanism form:** *the
report must not import the config and run machinery.* A user with a store and no config cannot be
made to load the validator for a config they do not have. So the invariant becomes:

> **`metamer.report`'s import graph contains no `matplotlib`, no `numba`, no `pydantic`, and no
> `metamer.batch.run`.**

**`metamer.core` and `metamer.core.fit` ride along and that is stated rather than excluded**, with
its measured cost: +0.5 s and 644 modules, no JIT, no plotting stack. The taxonomy lives in
`metamer.core` and the package initialises itself; **restructuring `core/__init__.py` to avoid it
is refused** — the registration side effect is deliberate, documented, and load-bearing, and moving
`Outcome` out of `metamer.core` would be a refactor of the spine for a reader's convenience.

**The struck claim is "excludes the fit path". The kept claim is "excludes the config path".** The
second is testable, true, and is the one the foreign-store property actually needs.

### (a10) TASK 1's OWN TESTS NEED THE RULE THE SPIKE JUST PAID FOR

**The import-graph test must be demonstrated able to FAIL.** A subprocess probe that passes because
it imported nothing is (a10) instance 4 wearing a different hat — an instrument reporting its
operating point. So the test carries a **positive control**: a second subprocess that imports
something known to drag a forbidden member, asserting the probe catches it. `test_core_isolation`'s
own docstring supplies the reason the probe must be a subprocess at all — *"inside the pytest
session every one of these is already imported by some other test module"* — and that is a
statement about visibility, not about discrimination. Both are needed.

**And the completeness-disagreement fixture must be asserted able to express disagreement.** A
complete tile holding `NOT_ATTEMPTED` is **constructible but not producible by any run**, so the
fixture states its own reachability rather than implying the condition occurs in the wild.

### TRANSCRIPTION OWED WITH THIS COMMIT

Task 1 touches `src/` and `tests/`, so the two parked one-liners above are transcribed with it:
`Outcome.is_fit_verdict`'s pattern table gains rows 4 and 5 with *"Three gates"* → *"Five gates"*,
and `test_compat_relevance_is_an_allowlist_golden_set` gains its name/subject line. **Verbatim text
is parked above; this is a transcription, not a recollection.**

### ADDENDUM, 2026-09-21 — THREE RULES LANDED AFTER THIS ENTRY AND TIGHTEN IT

**This entry was written on 2026-09-20 and is not amended to look prescient.** Three things
reached the handoff and the plan after it, and each raises Task 1's standard:

1. **(a10) — before reading an instrument, demonstrate it can produce both answers.** The entry
   already asked for a positive control on the import probe, which is that rule; **what it did not
   say is that the control must use the IDENTICAL probe function with a different target**, not a
   parallel implementation of the same idea. A positive control written twice tests two things and
   proves neither.
2. **(a10.1) — a post-hoc invalidation is legitimate exactly when it would have fired the same way
   under the opposite outcome.** This governs what I may do if a Task 1 test comes back green for a
   reason I dislike: state the invalidating property, then ask whether it is computable **without**
   the result.
3. **The sweep-ordering rule.** Every tool that can write runs FIRST; the sweep runs LAST, on final
   bytes; `git write-tree` before and at commit time, asserted equal. **Task 1's commit is the first
   to follow it by construction rather than by luck.**

**AND ONE FINDING AGAINST THIS ENTRY'S OWN WORK, 2026-09-21.** The era test this pre-flight's
sibling commit produced scans `src/` with `ast` for references to `NOT_APPLICABLE`. **That is the
wrong subject** — it reads the source as a proxy for what a run writes — and it fails in the
direction that matters: §13.6 will most plausibly write the member **vectorised from a mask**, with
the code taken from a module constant, a lookup table, `flag_values` or `Outcome(n)`, and an
attribute-reference scan sees none of those. **So on the one day the test exists to go red, it stays
green.** It also cannot separate a read from a write. Replaced in Task 1's first commit by a
behavioural witness: run the fit path on all-NaN series, read back the **written** codes, assert
`INSUFFICIENT_DATA` present and `NOT_APPLICABLE` absent, with a fixture precondition asserting the
input really contains all-NaN series. **A test that reads its subject directly needs no positive
control against proxy divergence, because there is no proxy.**

### WHAT THIS ENTRY CHANGED

- **D10's invariant is rewritten** from "excludes the fit path" to "excludes the config path", with
  the false leaf-import mechanism struck and the measured graph recorded in its place.
- **Task 1 gains a positive control** on the import-graph probe, and a reachability statement on the
  completeness fixture.
- **Task 1 also carries three inherited repairs** (see the addendum): the behavioural era test, the
  PROGRESS.md pointer consolidation, and the sweep-ordering rule in handoff §2.


---

## Plan Task 2 — rates per branch and per candidate, audited before any code (2026-09-21)

**THE BRIEF** is the plan's Task 2 as amended: counts and rates per taxonomy branch and per
candidate, **both denominators printed** (`failed/fitted` and `failed/eligible`), each named at its
row, with the `fitted == 0` unavailability rule and the `domain_mask` caveat. **Three findings, and
the first is a live defect in shipped code that this task was written to prevent in a different
module.**

### (a5) THE DEFECT TASK 2 EXISTS TO PREVENT IS ALREADY SHIPPED IN 2e's LIVE COUNTERS

`progress.py`'s `LiveCounters.lines` computes, at line 149-152:

    total  = sum(self._by_branch.values())
    failed = sum(count for name, count in ... if Outcome(name).is_failure)

**`total` is every point the run touched**, including every non-fit code. **Measured, on a
constructed tally** — one tile, sixteen land points and four real failures:

    progress: tiles=1  fits=20  failed=4 (20.0%)

**Four failures out of four fits is 100%. It prints 20.0%, and it calls the denominator `fits`.**
The label says *fits*; the quantity is *points touched*. That is D1's tell — a name and a predicate
describing different quantities — in a **third** place, and it is on the path a user watches for ten
hours.

**It is the same arithmetic the verdict was repaired for on 2026-09-20** (D2b: 12/20 = 0.60 against
12/12 = 1.00), and the repair did not reach here because the two were never connected: 2e's Task 4
shipped the counters and 2e's Task 5 shipped the verdict, and nothing crossed them. **2c's lesson,
exactly: a term of art repeated across decisions acquires a reading nobody chose.**

**AND IT DEGRADES WITH THE THING THE REPORT IS FOR.** On this project's one ocean box the number is
right — no land, no gaps — so every test and every real run to date shows it correct. It is wrong in
proportion to how much of the grid is out of domain, which is to say **wrong exactly on the global
run §14.1's ten-hour scenario describes**.

**WHOSE IS IT?** §14.1's counters are 2e's and this is 2f's pre-flight. But the plan's own standing
requirement says no 2a–2e verdict moves, **and this moves none**: 2e's criterion 10 is *"the counters
are display-only and no decision path reaches them"*, which is about the seam and is untouched by
the arithmetic inside `lines`. **This is a correction to a shipped number, not a re-argued verdict**
— the handoff's own distinction, added 2026-09-20 — so it lands with Task 2, in its own commit,
ahead of the report so the two cannot print different rates for one run.

**THE FIX IS THE ONE TASK 2 ALREADY OWES**: the denominator is `is_fit_verdict`, the label says what
it counts, and where nothing was fitted the rate is unavailable rather than `0.0`.

### (c5) THE COUNTERS AND THE REPORT MUST NOT GROW TWO DEFINITIONS OF ONE RATE

Two modules will now compute *"the failure rate"* — `progress.py` live, `metamer.report` from the
store — and **the second is defined to be recomputable and the first is not**. If they disagree, a
user sees one number during the run and a different one after it, over the same data.

**They cannot share code**: `progress.py` is deliberately outside `metamer.batch` (2e's Task 4, an
import boundary asserted in a subprocess) and `metamer.report` must not import the run path
(Task 1). **So they share a TEST rather than a module** — one constructed tally and one constructed
store carrying the same outcome census, asserted to produce the same rate. That is the only shape
that binds two definitions without binding two import graphs.

### (a10) THE `fitted == 0` RULE NEEDS A FIXTURE THAT CAN EXPRESS BOTH OUTCOMES

The rule is that a candidate with no fits prints **unavailable**, not `0.0`. A fixture where *every*
candidate has no fits cannot show that the rule discriminates — both columns would be unavailable
for every row, which is also what a report that had simply broken would print. **The fixture carries
two candidates: one screened out everywhere, one fitted everywhere and passing.** Both print, and
they must not print alike.

### THE FLIP DID NOT CAUSE IT — MEASURED, NOT INFERRED

`progress.py` is **byte-identical at `ac3e577` (before the flip) and at HEAD**, and `is_eligible`
appears **zero times in it at either revision**. It reads a raw point count and always has. **So the
defect is 2e's from birth and commit 2's record is clean** — read with `git show`, never a checkout.

Had it read `is_eligible`, the flip would have regressed the live display yesterday and commit 2
would owe a dated note. It did not. **The wording "the quantity is points touched" suggested this;
suggesting is not measuring, and the check cost one command.**

> ## AND THE INFERENCE IS REPLACED BY A MEASUREMENT, 2026-09-21 — THE FLIP'S PROVENANCE, AS MEASURED
>
> **The two sentences above are an inference chain and they are no longer what the record rests
> on.** *"Byte-identical"* misses transitive dependence and *"`is_failure`'s body is unchanged"* is
> the same argument one level down: had `is_failure` been written as *"eligible and not OK"*, its
> body would be unchanged and its behaviour would have moved. **For a predicate over a finite enum,
> compare truth tables, not bodies** — handoff §2.
>
> **MEASURED: `is_failure`, `is_eligible` and `is_fit_verdict` over all fourteen `Outcome` members
> at `ac3e577` and at `f4eb42f`, read from two side `git worktree`s and removed afterwards, never a
> checkout of the working tree. Forty-two cells. ONE moved:
> `INSUFFICIENT_DATA.is_eligible`, False → True — and that one is the flip itself.**
>
> | predicate | cells | moved |
> |---|---|---|
> | `is_failure` | 14 | **0** |
> | `is_fit_verdict` | 14 | **0** |
> | `is_eligible` | 14 | **1** — `insufficient_data` |
>
> Both revisions carry `is_fit_verdict`, because the gate (`49f3db1`) preceded both, so all three
> predicates are comparable at both. **A behavioural run closes every transitive step at once; an
> inference has to find and close each one, and the step you have not noticed is the one that is
> open.**

### (a6) THE REPAIR LEFT A DESCRIPTION BEHIND, IN THE FUNCTION IT REPAIRED

`abort_verdict`'s own docstring still reads *"The rate is `failed / eligible`"* — at
`abort.py:167`, inside the function whose rate moved to `fitted` on 2026-09-20. **My repair changed
the code, the field docs and the dataclass docstring, and missed the description at the top of the
function.** (a6): when code is replaced, sweep for the descriptions that survive it. Fixed in this
commit.

### THE RULE THIS FINDING IS REALLY ABOUT, AND WHY F3 KEPT NEEDING RE-APPLYING

The flip's consumer enumeration searched for **callers of `is_eligible`** and found eight tests and
two modules. `LiveCounters` computes a failure rate **with its own arithmetic** and calls neither
predicate's rate path, so **no search for the predicate could ever have found it.**

> **A QUANTITY COMPUTED IN MORE THAN ONE PLACE CANNOT BE REPAIRED BY ENUMERATION, BECAUSE A SEARCH
> FINDS CALL SITES OF FUNCTIONS, NOT COMPUTATIONS OF QUANTITIES. GIVE EACH QUANTITY ONE DEFINITION,
> AND ITS NEXT REPAIR IS A SEARCH AGAIN.**

That is why F3's enumeration rule kept needing to be re-applied: **the thing being enumerated was
not the thing being repaired.** And it settles the shape of this commit — **one definition, not two
implementations policed by a census test.** A census test is the four-homes problem in code: it is
only as good as its census, and two implementations sharing a blind spot (a new `Outcome` member
each classifies differently) pass it while both are wrong.

**THE BOUNDARIES DO NOT PREVENT SHARING — CHECKED.** `progress.py` cannot tally failures without
`Outcome`, and `metamer.report` imports `metamer.core.outcomes` already (with `metamer.core` riding
along at its measured 0.5 s, recorded at Task 1). So a **pure function beside `is_fit_verdict`**,
taking a histogram and returning failed / fitted / eligible / points and a rate-or-reason, is
importable by both with no new edge in either graph. **It inherits `is_fit_verdict`'s
positive-membership default**, so a future `Outcome` member lands on the safe side in every consumer
at once.

### ~~THE ENUMERATION, WITH ITS COUNT — FIVE SITES~~ — THE DISPOSITIONS STAND, THE COUNT IS DELETED

> **CORRECTED IN PLACE 2026-09-21, AT THE FOLLOW-UP COMMIT, BECAUSE A CORRECTION RECORDED
> AWAY FROM THE CLAIM IT CORRECTS IS A SECOND VERSION OF THE CLAIM.** The table's five
> *dispositions* are still what this task does — two addressed, three filed. **Its COUNT is
> not an instrument**: *"five"* mixes three units and *"fifteen rate-shaped divisions"* has
> no rule that reproduces it, which the follow-up entry's (c7) measures. Both figures are
> **deleted rather than maintained**, and the size claim is now a golden table in
> `tests/test_outcomes.py` — the set of `src/` modules referencing `Outcome`, decided by the
> `ast`, with each module's division-node count.

| # | site | kind | disposition |
|---|---|---|---|
| 1 | `progress.py` `LiveCounters.lines` | **display** | **WRONG — fixed in this commit**, becomes the shared function's first consumer |
| 2 | `abort.py` `_rate_for` / `_decide` | **decision** | correct since 2026-09-20; moves onto the shared function, and its stale docstring is fixed |
| 3 | `audit_report.py` rescue / loss / `both_ok_fraction` | measurement | **filed as open question 25**, not touched — its denominators are `cold_failed` / `cold_ok` / `attempted`, a different question |
| 4 | committed harnesses under `notes/` — ~~**15 rate-shaped divisions**~~ **not counted; out of scope by the frozen-instrument rule** | measurement of committed artifacts | **FILED, NOT TOUCHED.** They use denominators like `outcome != 8` and `iterations != ITERATIONS_UNSET` that describe the artifacts they produced; rewriting them rewrites closed evidence — the same reason 2e's `_histograms` is frozen |
| 5 | `metamer.report` | display | **does not exist yet**; Task 2 makes it the shared function's second consumer |

**Two are display or decision sites and both are addressed here. Three are measurement sites and all
three are filed.** ~~The count is five and is asserted in a test, per (c7).~~ **It is not.** What
the test asserts is the golden table in `tests/test_outcomes.py` — a scope the `ast` decides and a
count per module,
classifying nothing — because (c7) asks for the size of what a discovery mechanism found and a
hand-drawn list of five is not a discovery mechanism. **A new site arriving in a module already
in scope moves that module's pinned count; a new module in scope has to be added deliberately.**

### WHAT THIS ENTRY CHANGED

- **Task 2 gains a commit ahead of it**: one shared definition of the failure tally, with
  `progress.py` as its first consumer and the verdict moved onto it. **Found before any code, on the
  second pre-flight in a row to change a task's size.**
- **~~A cross-module agreement test~~ is refused** in favour of one definition — a test holding two
  implementations equal is two homes for one fact, policed rather than prevented.
- **The `fitted == 0` fixture is specified as two candidates**, so the rule is shown to
  discriminate — (a10)'s head rule applied to a fixture.


---

## Task 2's repair — what the sweep caught that targeted runs did not (2026-09-21)

**THE FULL SWEEP CAME BACK RED ON A TEST I HAD NOT RUN**: `test_runner.py`'s
`test_a_recompute_run_counts_its_tiles_and_does_not_report_an_empty_run` parses `fits=` out of the
live display, and the repair renamed that field. `max()` on an empty sequence, a `ValueError`, and a
red sweep.

**I CHANGED A LABEL AND DID NOT GREP FOR ITS READERS.** `grep -rn "fits=" tests/` finds it in one
second. I had run `test_progress.py` — the module that owns the display — and stopped there, which
is a search bounded by the module I was editing rather than by the string I was changing. **Third
instance in one day of the same shape:** the flip's enumeration searched a predicate and missed a
second computation of the quantity; the regression check inspected a file and missed the transitive
step; this searched a module and missed a consumer.

> **WHEN YOU CHANGE THE TEXT OF AN OUTPUT, THE OUTPUT IS AN INTERFACE. GREP FOR THE STRING, NOT FOR
> THE MODULE.** A display is parsed by tests, by scripts and by operators, and none of them live in
> the module that emits it.

**The repair is stronger than a rename.** The test now reads **both** `points` and `fitted`: `points`
preserves its subject exactly (the seam fed the same number of codes on both branches of the tile
loop), and `fitted` is added because a recompute feeding the seam a block of NON-FIT codes would
keep `points` equal while silently dropping `fitted` to zero — an under-count this test exists to
catch and could not have seen through a single field.

### THE RUN-TIME IMPORT MEASUREMENT, AND TASK 1's CEILING WAS WRONG TWICE

Measured 2026-09-21, fixture store built in the PARENT and only read by the probe subprocess — so
the probe measures the report and not the fixture builder:

| stage | modules | forbidden present |
|---|---|---|
| `import metamer.report` | **63** | none |
| `+ from metamer.report.reader import read_store` | **930** | none |
| **after `read_store` runs** | **933** | **none** |

**No leak: the boundary holds at run time.** But Task 1's test does not establish that, and its
ceiling is wrong in both directions:

1. **`metamer/report/__init__.py` is docstring-only**, so `import metamer.report` reaches **63**
   modules — not the reader, not zarr. **The assertion "no forbidden module" is trivially true
   because nothing was imported.**
2. **The ceiling says "measured 708"**, which is the pre-flight's figure for
   `metamer.core.outcomes` — a different subject, carried across as if it described this one. **The
   real subject is 933, which is ABOVE the 900 asserted.** Had the probe targeted the right thing,
   the ceiling would have failed.

**AND THE PROBE CANNOT SEE THE FAILURE THE LAZY DESIGN CREATES.** D10 requires `matplotlib` imported
*inside* the maps function, which is invisible to a `sys.modules` check taken right after an import
— that is what lazy means. So the numbers path reaching a lazily-imported module by a shared helper
would be green at import time and red at run time. **By (a10)'s head rule the probe cannot give both
answers for the failure the boundary exists to prevent**, and the positive control does not fix it:
it shows the probe sees an *import-time* import.

**Repair, in the follow-up commit**: the subject becomes the module that exists and the path that
runs — import, then `read_store` on a parent-built fixture, then read `sys.modules`; ceiling
re-measured against that subject with the figure and its date in the docstring; the import-time
probe kept as the cheap first check. Criterion 3's reading changes with it, since it currently
names evidence that is vacuous.

---

## The queued follow-up — audited before any code (2026-09-21)

**THE BRIEF** is PROGRESS.md's five queued follow-up items, which land before any Task 2 code:
re-aim the tautological agreement test and `failure_tally`'s own tests at hand-computed values;
count the rate-computation enumeration per file or per computation; make the docstrings name
`failure_tally`; repair the run-time import probe and its ceiling; and measure the `is_failure`
truth table across the flip. **Four findings, and the first one changes the size of the follow-up.**

### (a4) TWO OF THE FIVE WERE ALREADY DONE BY THE COMMIT THAT QUEUED THEM, AND THE LIST DID NOT SAY SO

**Items 1 and 3 are landed in `7790100` and owe no code.** Read rather than recalled, and checked
mechanically rather than by reading the docstrings that claim it:

- **Item 1, the agreement test.** `test_progress.py` **neither imports nor calls** `failure_tally`
  — asserted by an `ast` walk, 0 calls, not in any `ImportFrom` — and
  `test_the_failure_count_uses_the_taxonomy_and_not_a_name_test` asserts the **literal line**
  `"progress: tiles=1  points=6  failed=2 of 3 fitted (66.7%)"` against a hand-derivation from the
  fixture's own six codes (one `OK`, two `DEGENERATE_HESSIAN`, three `CANDIDATE_DROPPED` → three
  fitted, two failed, 2/3). **It is not tautological and was never allowed to become so.**
- **Item 1, `failure_tally`'s own tests.** Six of them call it, each on a literal census with its
  expected counts derived by hand: `{INSUFFICIENT_DATA: 16, DEGENERATE_HESSIAN: 4}` → 20/20/4/4 at
  rate 1.0; `{SCREENED_OUT: 20}` → no rate with a reason; the (a10) pair that shows the rule
  **discriminates** (`None` against `0.0`); the empty census; both key spellings; and the refused
  unknown key. Every one is an external oracle in the §2 sense.
- **Item 3, the docstrings.** Both consumer sites already say the arithmetic is `failure_tally`'s
  and is **not restated** — `abort.py:253` and `progress.py:182` — and `abort_verdict`'s surviving
  *"the rate is `failed / eligible`"* was corrected in the same commit under (a6).

**THE FINDING IS ABOUT THE LIST, NOT ABOUT THE WORK.** A handoff that queues five items without
marking which ones its own commit discharged spends the next session's first hour re-deriving that
— and the cheaper failure is the other direction: **a session that trusted the list would have
"re-aimed" two tests that are already aimed**, editing a correct oracle to look like the repair the
list promised. **(a4) at a handoff's own follow-up list**: *"checked" in one's own document is a
claim*, and so is *"owed"*.

### (c7) ITEM 2's COUNT IS NOT RE-DERIVABLE, AND A PER-COMPUTATION COUNT IS THE WRONG INSTRUMENT

**"Five sites" mixes three units, which is the defect the item names. Measured today, by `ast`
rather than by grep, so the count is per COMPUTATION and reproducible:**

| population | measured |
|---|---|
| `src/` divisions producing a failure rate | **one** — `core/outcomes.py:313`, `failed / fitted` |
| `abort.py` division nodes, **any kind** | **zero** |
| `progress.py` division nodes | **one**, and it is the percentage formatter `100.0 * part / whole` at line 213 |
| `audit_report.py` rate divisions | **one** — `_rate`'s `numerator / denominator` at line 250 — serving **seven** callers: `selection_disagreement`, `selection_move`, `selection_dropout`, `ranked_fraction`, `rescue`, `loss`, `both_ok_fraction` |
| `audit_report.py` other divisions | one, `gap / scale` at 608, a normalisation and not a rate |
| division nodes under `docs/superpowers/notes/` | **184** |
| committed `.py` instruments under `notes/` | **30** |

**THE 184 IS THE FINDING.** A per-computation count over the harnesses is **dominated by
`pathlib`** — `work / f'store_{tag}.zarr'`, `fixtures / 'control2' / 'easy.toml'` — so the `/`
operator is not the subject at all there. **So "fifteen rate-shaped divisions in the committed
harnesses" has no rule that reproduces it**, and it must not be carried as a number: it is a
hand-count of a population whose enumeration rule was never written down, which is the shape (c7)
exists for one level up from where it was applied.

**AND THE `audit_report` ROW CORRECTS THE SITE LIST'S OWN ARITHMETIC IN THE OTHER DIRECTION.** The
test's docstring names *"`audit_report`'s rescue/loss denominators"* — two quantities. The division
is **one** and the quantities are **seven**. So the same list over-counts the harnesses and
under-counts the audit, which is what a mixed unit does.

**THE POPULATIONS ARE TWO AND THE LIST TREATS THEM AS ONE.** Live code that must agree about a
quantity, and **frozen instruments that must not be touched** — (j8)'s third register, the same
rule that froze 2e's `_histograms`. A harness is out of scope **by a stated rule**, which is a
different statement from *"counted as one site"*: the first survives a thirty-first harness landing
next sub-phase, the second silently absorbs it. **(a5b): two constraints that look like a
trade-off often share a term that belongs to neither.**

**AND THE ASSERTION THE CURRENT TEST CANNOT MAKE.** `test_every_failure_rate_in_src_comes_from_the_one_definition`
pins the **member list** of `failure_tally`'s consumers, so it sees a site added *that calls
`failure_tally`* and is blind to a third site that computes the rate **with its own arithmetic** —
which is the only failure it exists to catch, and is exactly what happened between 2e's Task 4 and
Task 5. **The division-node counts above are the mechanical form of that claim**: `abort.py` at
zero and `progress.py` at one-and-it-is-the-formatter fail the moment either grows an arithmetic
beside the shared call.

### ITEM 4 CONFIRMED, AND ONE OF ITS OWN FIGURES CORRECTED

**Re-measured 2026-09-21**, fixture store built in the **parent** and only read by the probe
subprocess, so the reading describes the report and not the fixture builder:

| stage | modules | forbidden present |
|---|---|---|
| `import metamer.report` | **65** | none |
| `+ from metamer.report.reader import read_store` | **930** | none |
| **after `read_store` runs** | **933** | **none** |

**THE BOUNDARY HOLDS AT RUN TIME. THE TESTS DO NOT ESTABLISH IT.** `metamer/report/__init__.py` is
docstring-only, so both of Task 1's assertions are taken at the 65-module stage: *"no forbidden
module"* is trivially true because nothing was imported, and *"under a ceiling of 900"* passes on
65. **Against the real subject the ceiling FAILS — 933 > 900** — so the one assertion that could
have caught a heavy arrival was both vacuous and wrong.

**THE HANDOFF SAID 63 AND I MEASURE 65, AND THE DIFFERENCE RECONCILES EXACTLY RATHER THAN BEING
LEFT AS SCATTER.** Task 1's own docstring records `metamer` alone at **64**; a docstring-only
`metamer/report/__init__.py` adds exactly itself, giving **65**. The 63 was taken under a probe that
had not yet imported `json` and `sys`. **Recorded because a two-module gap nobody explains is how a
figure becomes unquotable** — and because the ceiling's whole defect was a figure carried from
another subject.

**AND THE CEILING'S ORIGINAL ARGUMENT IS NO LONGER AVAILABLE, WHICH IS A CONSEQUENCE RATHER THAN A
CHOICE.** It was *"comfortably above the measurement, well below `metamer.batch.run`'s 1002"*. The
real subject is **933** and the discriminating bound is still **1002**, so the whole window is
**69 modules — 7%**. A ceiling inside it discriminates a heavy arrival and trips on ordinary
growth; one above it discriminates nothing. **That is the decision below, and it is a decision
because no measurement chooses between a tripwire and a wall.**

**THE PROBE'S STRUCTURAL LIMIT IS RESTATED AT THE REPAIR, NOT ONLY IN THE PLAN.** A `sys.modules`
check **cannot see a lazy import by construction** — that is what lazy means — and D10 requires
`matplotlib` imported *inside* the maps function. So even the repaired probe is silent about the
one design D10 chose, and the numbers path reaching a lazily-imported module through a shared
helper would be green at import time and red at run time. **(a10) at the repaired instrument:** it
gives both answers for an import-time violation and only one for a run-time one, and the positive
control does not fix that, because the control demonstrates the probe sees an *import-time* import.
**Calling `read_store` is what narrows the gap** — the numbers path is then exercised rather than
hoped about — and the residue is stated rather than priced.

### ITEM 5 MEASURED: `is_failure`'s TRUTH TABLE DID NOT MOVE, AND ONE CELL OF THE WHOLE TABLE DID

**Fourteen members, three predicates, two revisions, read from two side `git worktree`s and
removed afterwards — never a checkout of the working tree.** `ac3e577` is the last commit before
the flip; `f4eb42f` is the flip. Both carry `is_fit_verdict`, since the gate (`49f3db1`) preceded
both, so all three predicates are comparable at both revisions.

| predicate | cells | moved |
|---|---|---|
| `is_failure` | 14 | **0** |
| `is_fit_verdict` | 14 | **0** |
| `is_eligible` | 14 | **1** — `insufficient_data`, False → True |

**So the inference is replaced by a measurement, and it holds.** The record said *"byte-identical,
and `is_failure`'s body is unchanged"*; an identical body is not identical behaviour if what it
calls changed, and now it does not have to be. **Exactly one cell of forty-two moved and it is the
flip's own**, so the live display — which reads `is_failure` and a raw point count and never
`is_eligible` — could not have regressed through it. **A behavioural run closes every transitive
step at once; an inference has to find each one, and the step you have not noticed is the one that
is open.**

### ~~TWO DECISIONS THIS ENTRY RAISES AND DOES NOT TAKE~~ — BOTH RULED 2026-09-21

~~1. **ITEM 2's UNIT.** The queued item offers *"per file or per computation"* and the measurement
says neither alone works: per computation is the right unit for `src/` (one division) and the
wrong one for the harnesses (184, mostly `pathlib`). **The proposal is two enumerations with two
units** — live sites per computation, frozen instruments per file and out of scope by the
frozen-instrument rule — rather than one count of five. That is a reframe of the item rather
than a choice between its two options, so it is raised.
2. **THE CEILING'S VALUE, given a 69-module window.** 933 measured against 1002 discriminating.~~

**Struck rather than deleted: the proposal was NEITHER of the offered units AND NOT the one ruled.**
Both of my framings kept a count of a population I could not classify — (a) per computation over
`src/` plus per file over `notes/`, with the *classification* of a division left to the counter. The
ruling removes the classification instead of choosing its unit, which neither option offered.

**BOTH RULINGS ARE RECORDED VERBATIM BELOW.** They are Dr. Twinklebrane's words and are not
paraphrased, because a ruling restated is a ruling re-argued.

> **RULING, ITEM 2: NEITHER UNIT. DON'T COUNT WHAT YOU CAN'T CLASSIFY; PIN WHAT YOU CAN
> OBSERVE.**
>
> Delete "five sites" and "fifteen" — (d)'s instinct is right: an unverifiable claim is
> removed, not maintained. Replace them with a golden table.
>
> - Scope: every src/ module that references Outcome. Which modules those are is a
>   mechanical fact from the ast.
> - The test asserts two things: the set of those modules, and each module's count of
>   division nodes.
> - Classify nothing. Pathlib joins count too; a reviewer judges any change.
> - A third arithmetic anywhere in scope changes a pinned count.
> - A new Outcome-referencing module, which Task 2's report code will be, has to be added
>   to the table deliberately, with its count.
>
> This is (a)'s pin extended from two hand-picked modules to a scope defined mechanically.
> That is the difference between enumerating the modules you named and catching new ones.
>
> Frozen instruments under notes/ are excluded by the frozen-instrument rule, and the test
> states that exclusion and its reason. Forward rule for handoff §2: new harness code that
> reports a failure rate calls failure_tally, checked at its pre-flight. Name the gap: the
> suite does not enforce this.
>
> audit_report's docstring says two quantities and the measurement shows seven. Correct
> it. That is a known defect, not OQ25's open question. Note the correction in OQ25.
>
> Residual gap, named: a rate computed by comparing raw integer codes without referencing
> Outcome. D1 already forbids that, and nothing in the suite catches it.

> **RULING, THE CEILING (the second ruling you were going to bring): IT IS A BACKSTOP FOR
> UNNAMED DEPENDENCIES, NOT A SECOND COPY OF THE DENYLIST.**
>
> batch.run and pydantic are already caught by name, so batch.run's 1002 is not the number
> the ceiling has to discriminate against. The principle that reconciles this with item 2:
> PIN EXACTLY WHERE CHANGE IS RARE AND MEANINGFUL; BOUND WITH A MARGIN WHERE HARMLESS DRIFT
> IS COMMON. Module counts shift with lockfile updates and with platform, so a ceiling tight
> enough to fire on routine updates becomes a number people bump without reading it. That is
> D6's flag argument again.
>
> - Set the ceiling 5% above the measured figure: about 980. That also happens to sit below
>   batch.run's 1002.
> - The assertion message prints the measured count.
> - After the first CI run, record CI's count next to the local 933. If they differ
>   materially, set the margin from the larger of the two.

### WHAT THE RULINGS CHANGE, AND THE FIGURES THE NEXT SESSION WRITES CODE AGAINST

**ITEM 2 — a golden table, not a count.** Scope is *every `src/` module that references `Outcome`*,
which the `ast` decides; the test asserts **the set of those modules** and **each module's division-node
count**; nothing is classified, so `pathlib` joins are in the counts and a reviewer judges any
movement. The measured seeds for that table are in this entry's (c7) section — `abort.py` **0**,
`progress.py` **1**, `core/outcomes.py` **1** — and the rest of the scope is enumerated when the
table is written. **`metamer.report`'s numbers module will be a new row and must be added
deliberately, with its count**, which is the property that catches a module the previous list would
not have named.

**ITEM 4 — the probe's subject and the ceiling's margin.** The figures, re-measured 2026-09-21 with
the fixture built in the parent: **65** modules after `import metamer.report`, **930** after
`from metamer.report.reader import read_store`, **933** after `read_store` has run, with **no
forbidden module at any stage**. The ceiling is **980** — 5% above 933 — its assertion message
prints the measured count, and **CI's own count is recorded beside the local 933 after the first
run**, with the margin taken from the larger of the two if they differ materially.

**ITEM 5 — recorded where the flip's provenance lives**, at *"THE FLIP DID NOT CAUSE IT"* in Task
2's entry above, as **measured**: forty-two cells, one moved, and that one is the flip itself. **The
inference is struck there rather than here**, because a correction recorded away from the claim it
corrects is a second version of the claim.

**AND THE TWO LESSONS THIS SESSION EARNED GO TO THE HANDOFF, NOT HERE** — queue reconciliation and
the cold-start read list, with pin-versus-bound and the forward harness rule beside them. They are
rules about how any handoff is written, so they belong in §2 where the method lives, and PROGRESS.md
points at them rather than restating them.


### ~~PARKED FOR ITEM 2's COMMIT — TRANSCRIPTION, NOT RECOLLECTION~~ — TRANSCRIBED AND DISCHARGED

> **BOTH LANDED AT THE FOLLOW-UP COMMIT, 2026-09-21, AND THIS SECTION IS SPENT.** Kept rather
> than deleted because it is the record of what was owed and by whom; **marked here so the
> next session does not transcribe it a second time**, which is the queue-reconciliation rule
> applied to this document's own parked text. Item 1 is the rewritten docstring of
> `test_every_failure_rate_in_src_comes_from_the_one_definition` plus the new
> `test_the_rate_site_table_is_pinned_over_every_outcome_referencing_module`; item 2 is the
> `audit_report` count, now stated as **one `_rate` division serving seven quantities** in the
> golden table test's docstring.

**This session is docs-only, so the two `tests/` corrections the rulings call for are parked as
TEXT rather than as intentions** — the same idiom as the pre-plan entry's two parked one-liners, and
for the same reason: *"it reaches the tree with the next commit"* is a promise with no owner and
dies with the session. Whoever writes item 2 transcribes these; neither is a recollection.

**1. `test_every_failure_rate_in_src_comes_from_the_one_definition` loses its count and gains the
golden table.** Its docstring currently says *"five places compute a failure-like rate"* and names
*"`audit_report`'s rescue/loss denominators"*. **Both figures go.** The replacement claim, to be
written in the task's own words against the table it asserts:

- the scope is **every `src/` module that references `Outcome`**, decided by the `ast`;
- the test asserts **the set of those modules** and **each module's division-node count**;
- **nothing is classified** — `pathlib` joins are in the counts, and a reviewer judges any movement;
- **frozen instruments under `docs/superpowers/notes/` are excluded**, and the test states the
  exclusion **and its reason**: a harness is the apparatus of a number somebody is still quoting, so
  rewriting it rewrites closed evidence — (j8)'s third register;
- the two gaps are named **in the test**: the suite does not enforce that a new harness calls
  `failure_tally`, and a rate computed by comparing **raw integer codes** without referencing
  `Outcome` is outside the scope entirely — D1 forbids it and nothing catches it.

**2. The `audit_report` count, verbatim.** Wherever that module's rate helper is described, the
figure is *"**one** division — `_rate` — serving **seven** quantities: `selection_disagreement`,
`selection_move`, `selection_dropout`, `ranked_fraction`, `rescue`, `loss`, `both_ok_fraction`"*,
**not** *"rescue/loss"*. Measured by `ast` on 2026-09-21. **The denominator itself stays filed as
open question 25**; only the count is corrected, because a miscount of a known set is a defect and
not an open question.

**AND THE MEASURED SEEDS FOR THE TABLE, SO THE NEXT SESSION WRITES CODE AND NOT A MEASUREMENT
HARNESS:** `src/metamer/batch/abort.py` **0**, `src/metamer/progress.py` **1**,
`src/metamer/core/outcomes.py` **1**. **The rest of the scope is enumerated when the table is
written** — the `ast` decides which modules reference `Outcome`, and that enumeration is the
deliverable rather than a figure to transcribe from here.

### ADDENDUM, 2026-09-21 — WHAT WRITING ITEMS 2 AND 4 TURNED UP THAT THE RULINGS DID NOT COVER

**The rulings were followed, not re-argued. Three things the code found are recorded because they
are not in them.**

**1. THE RULING'S OWN RECORDING MECHANISM HAD NO SOURCE ON A GREEN RUN, WHICH IS THE ONE STATE IT
WAS WRITTEN FOR.** The ceiling ruling asks for *"the assertion message prints the measured count"*
and *"after the first CI run, record CI's count next to the local 933"* — and those two sentences
do not compose: **an assertion message is emitted only when the assertion FIRES**, so a passing CI
run prints nothing and the figure the second sentence asks for has nowhere to come from. The fix is
the channel the suite already has for exactly this: `conftest.DIAGNOSTIC_LINES`, whose own docstring
says it is *"the only channel that reaches a CI log from a passing test"* because pytest hides a
passing test's stdout. The count is appended there **and** kept in the assertion message, so the
number is readable in both states rather than in neither.

> **THE SHAPE IS (a2c)'s, ONE REGISTER OUT: A VALUE THE MECHANISM COMPUTES AND DOES NOT PERSIST.**
> The count was measured, used for a comparison, and dropped — and the artifact built to answer
> *"what does CI load?"* would not have carried its own subject. It reads as complete: the ceiling
> passes, the message exists, and nothing looks partial until somebody goes looking for CI's
> number and finds a green log.

**2. THE SCOPE IS NINETEEN MODULES, AND THE THREE SEEDS ARE ITS SMALLEST COUNTS.** *"Classify
nothing"* was ruled with `pathlib` in view; what the enumeration actually shows is that the table is
**dominated by modules with no rate in them** — `bench/fields.py` at 14, `bench/spike.py` at 8,
`core/counting.py` at 6 — against the seeds' 0, 1 and 1. **That is the ruling working rather than
failing**: those counts are the noise a classifier would have had to judge, and judging them is
precisely what could not be reproduced. The table is in
`tests/test_outcomes.py::FAILURE_RATE_SITE_TABLE` and **is not copied here**.

**AND `metamer/report/reader.py` IS ALREADY A ROW, AT 1.** The ruling anticipated *"`metamer.report`'s
numbers module is a new row and must be added deliberately"* as a future event; Task 1's reader
references `Outcome` and is in scope **today**, so the deliberate-addition property was exercised by
the commit that wrote the table rather than deferred to the one that will grow it.

**3. BOTH REPAIRED INSTRUMENTS WERE SHOWN TO PRODUCE BOTH ANSWERS, AND THE THIRD IS PERMANENT.**
(a10) applied to instruments whose whole defect was that they could not:

| instrument | the demonstration | reading |
|---|---|---|
| the golden table | a division node appended to `abort.py`, reverted from a scratchpad copy — **never a `git checkout`** | `{'metamer/batch/abort.py': 1} != {'metamer/batch/abort.py': 0}` |
| the ceiling | the bound temporarily lowered, to read the count the passing form hides | *"reading a store now loads **933** modules"* — the pre-flight's figure, from the shipped instrument |
| the run-time probe | `test_the_runtime_probe_can_see_a_violation`, **kept in the suite**: one injected import into the identical probe source | `pydantic` at both readings, and a strictly larger module count |

**The third is a test and the first two are not**, which is a real asymmetry: the probe's control
costs a subprocess, while pinning "the table fails when a division arrives" would mean committing a
mutation of `src/`. **The demonstration is recorded here instead of asserted there**, and that is
the weaker form — it establishes the instrument bit on 2026-09-21 and not on every run.

**AND THE FIRST FINDING PAID FOR ITSELF WITHIN ONE RUN, 2026-09-22.** CI run `35698698743` was green
on all four environments, so **the assertion message said nothing in all four** — and the
`DIAGNOSTIC_LINES` copy produced **four different counts**, which are recorded at the ceiling test's
own docstring and **are not repeated here**. Two things follow, and only the second was foreseen:

1. **The ceiling stays at 980.** The ruling says take the margin from the larger, and the larger is
   the local reading the bound was already set from.
2. **The quantity drifts across environments that all pass** — several modules across interpreter
   versions, and a larger gap between local and CI **on the same interpreter**, which is the
   environment rather than the language. **A pin would have fired on three of the four green runs.**
   Pin-versus-bound was ruled on the expectation of drift; this measures it, and the two figures a
   reader needs to see that are the local one and CI's, side by side, which is why the obligation to
   record CI's was worth a mechanism at all.

---

## Task 2's pre-flight, REFRESHED before its code (2026-09-22)

**Task 2's entry above was written on 2026-09-21 and its findings stand** — the live-counter defect
it found was fixed at `7790100`, and the cross-module agreement test it refused stayed refused.
**What follows is the re-audit owed because the entry predates both that commit and the follow-up's
golden table.** Four findings, and the first is a contradiction inside the plan's own Task 2.

### (f) THE PLAN'S TASK 2 DESCRIBES `is_eligible` WRONGLY, AND THREE OTHER PLACES SETTLE THE BEHAVIOUR

The plan says, in consecutive sentences:

> The eligible-point denominator is `Outcome.is_eligible` — which after D2 includes
> `INSUFFICIENT_DATA` and excludes `NOT_APPLICABLE` only. […] `NOT_ATTEMPTED` is out of both: it is
> the absence of information.

**Both cannot hold, and the tree says which is which.** Measured over all fourteen members today:
**`NOT_ATTEMPTED.is_eligible` is `True`.** The predicate excludes `NOT_APPLICABLE` only, exactly as
the first sentence says, **so the second sentence is not a description of it.**

**THE SECOND SENTENCE IS THE REQUIREMENT AND THE FIRST IS THE DEFECT.** Three places carry the
behaviour and only one carries the parenthetical:

| source | what it says about `NOT_ATTEMPTED` |
|---|---|
| the plan's own test list | *"excludes it from every denominator while still **counting** it in the branch table"* |
| design doc §12.5's grouping table | **"n/a, and a finished store should hold none"** — the store is saying *nothing wrote here* |
| `Outcome.is_eligible` in the tree | **eligible**, because the predicate's rule is *"`NOT_APPLICABLE` leaves the denominator"* and nothing else does |

**So no decision is owed: the denominator excludes it, and what is wrong is one clause describing
how.** Recorded rather than silently worked around, because the next reader meets the clause before
they meet the test list.

### AND THE PREMISE THAT MADE IT "n/a" IS THE PREMISE 2f WAS WRITTEN TO BREAK

§12.5 can call `NOT_ATTEMPTED`'s eligibility *n/a* because **a finished store should hold none**.
**D6 and exit criterion 19 make 2f describe UNFINISHED stores deliberately** — *"an unfinished store
is described, not refused"* — and an unfinished store holds `NOT_ATTEMPTED` **in proportion to how
far the run did not get.**

**So counting it eligible dilutes `failed / eligible` in proportion to PROGRESS.** That is the same
shape as the land dilution the two-column print exists to expose, arriving through a different
member, and **it is invisible on every fixture that finishes** — which is every fixture in the tree.
**(a5): a constraint checked against the brief's finished-store case is not checked at all**, since
the sub-phase's own D6 says the unfinished case is in scope.

### (i) "AN ALL-OCEAN STORE REPORTS THEM EQUAL" IS NOT A PROPERTY OF OCEAN

The plan's fixture rule reads *"a store with land reports `failed/fitted` and `failed/eligible`
differing, and an all-ocean store reports them equal"*. **Equality needs `eligible == fitted`, and
FOUR members are eligible without being fitted** — measured, not recalled: `NOT_ATTEMPTED`,
`CANDIDATE_DROPPED`, `INSUFFICIENT_DATA`, `SCREENED_OUT`.

**So the all-ocean fixture reports them equal only if it also holds none of those four**, and a
fixture that happens to carry one `SCREENED_OUT` fails a test whose stated subject is land. **The
fixture rule is a statement about the census, not about the geography**, and the test says so or it
will be debugged as a land bug the first time it fires. Criterion 12's 12-ocean/8-land store gives
`1.00` against `0.60` **because its twenty points are otherwise all fit verdicts**, which is a
property of that store worth writing down beside the numbers.

### (g) THE ONE DEFINITION CARRIES ONE RATE, AND TASK 2 PRINTS TWO

`FailureTally` is `points / eligible / fitted / failed / rate / unavailable`, where `rate` is
`failed / fitted` and `unavailable` is its single reason. **Task 2's amendment needs `failed /
eligible` beside it, at every row.** Computing that division in the report would be **a second
arithmetic for a rate, in a module the follow-up's golden table now scopes** — D1's prohibition and
the table's tripwire pointing the same way. **So the second denominator is a field of the one
definition**, and `core/outcomes.py`'s pinned division count moves deliberately, with the table
updated in the same commit.

**TWO CONTAINMENTS MEASURED RATHER THAN ASSUMED, AND EACH BUYS SOMETHING:**

| measured over all 14 members | consequence |
|---|---|
| `is_fit_verdict` ⊆ `is_eligible` — **no member is fitted without being eligible** | `fitted > 0` implies `eligible ≥ fitted > 0`, so **the eligible column cannot divide by zero while the fitted column can compute.** The two share exactly ONE unavailability condition, `fitted == 0` — which is what the amendment already states, now as a fact rather than a hope |
| `is_failure` ⊆ `is_fit_verdict` — **no failure lies outside a fit verdict** | **the numerator is common to both rates**, so they differ in the denominator alone. That is what makes *"the gap between them is the store's land exposure"* a true statement rather than a slogan: any other difference would put two quantities in one subtraction |

### AND THE NAME `eligible` IS ALREADY SPOKEN FOR, SO THE NEW COUNT IS AN ADDITION

`FailureTally.eligible` is read in three places and **divided by in none**: `abort.py:270` and
`twopass.py:440` record it in an artifact, `__main__.py:474` prints it as *"eligible coarse
points"*. **Redefining it to drop `NOT_ATTEMPTED` would move a number in a committed verdict
record** — and `audit_report`'s `attempted`, the same predicate's other reader, is **open question
25's filed subject**, which 2f does not reopen.

**So Task 2 ADDS a named count and does not redefine one.** (a2)'s register: the fix for a name
doing two jobs is a second name, not a quieter definition of the first.

### WHAT THIS ENTRY CHANGES, BEFORE ANY CODE

- **Task 2's denominator comes from `core.outcomes`, not from a division in the report.** One
  definition, two rates, two reasons.
- **One test the plan does not list is owed**: the eligible denominator excludes `NOT_ATTEMPTED`
  **on an UNFINISHED store**, where the dilution is proportional to progress. The plan's
  `NOT_ATTEMPTED` test is written on a store that merely contains the member; this one is written
  where it is a large fraction, which is the case D6 put in scope.
- **The all-ocean fixture's equality is stated as a census property**, with the four
  eligible-but-unfitted members named at the fixture.
- **Two golden-table rows move deliberately in Task 2's commit** — `core/outcomes.py` for the
  second rate, and `metamer/report`'s numbers module as a new row with its measured count.

---

## Task 2, as built (2026-09-22) — what the ruling changed and what the code then found

**THE RULING SETTLED THE MECHANISM, AND I HAD CALLED IT SETTLED WHEN IT WAS NOT.** My refreshed
entry said the `NOT_ATTEMPTED` finding needed no ruling because the plan's *behaviour* was settled
three ways. **That reasoning was right about the behaviour and wrong about what it forces at the
call site**: the only way to get the required denominator without a new predicate is to hand-exclude
a member where the row is computed, which is a second definition of a denominator **two days after
the last one was removed**, in a module the golden table now scopes. The behaviour being settled did
not make the mechanism settled, and the mechanism was the part with a choice in it.

### WHAT LANDED

**`Outcome.is_covered`, positively defined and enumerated member by member**, meaning *in the domain
**and** the run reached it*. Two exclusions with two different reasons stated at its own table:
`NOT_APPLICABLE` because the point is not in the domain, `NOT_ATTEMPTED` because nothing wrote
there. Its docstring says in one line that it is **not** `is_eligible` and why — that predicate
answers a question about the domain and its values are in committed artifacts.

**`failure_tally` returns BOTH rates.** `rate = failed / fitted`, `coverage_rate = failed / covered`,
and **one** `unavailable` reason, because the chain makes `fitted == 0` the only condition either
can fail under. **`report/numbers.py` computes nothing** — the golden table records it at **zero**
division nodes, which is that claim in mechanical form.

**The chain is asserted with each step proved PROPER by a named witness** — `OK`, `SCREENED_OUT`,
`NOT_ATTEMPTED`. Containment alone would pass if two predicates were the same set, which is exactly
the collapse this taxonomy keeps suffering: §14.1 asked `is_eligible` while meaning `is_fit_verdict`
*because they agreed on every member anyone had looked at*.

### THE TABLE IS IN THE MODULE AND IS PARSED BY THE TEST, WHICH IS MORE THAN WAS ASKED FOR

The ruling asked that the four be readable together, one table, predicates as columns. **A docstring
table and a test dict would have been the same fact in two places**, and the one that drifts is the
one nobody runs. So the table lives in `Outcome`'s docstring and
`test_every_member_is_classified_by_every_predicate_in_one_table` **parses it out of
`Outcome.__doc__`** and asserts it against the four properties. Documentation that fails the suite
when it lies. **Demonstrated to bite**: one cell flipped in the docstring, 13 rows identical, 1
differing, reverted from a scratchpad copy rather than by `git checkout`.

### THREE THINGS THE CODE FOUND THAT THE RULING DID NOT NAME

**1. THE GAP BETWEEN THE TWO RATES IS NOT LAND, AND THE PLAN'S WORDING INVITES THAT READING.**
*"The gap between them is the store's land exposure"* — but true land is `NOT_APPLICABLE`, which is
outside **both** denominators and therefore **cannot separate them at all**. What opens the gap is
an in-domain point the run **reached and did not fit**, which on a global run is dominated by thin
records. D2b's own `1.00 against 0.60` reconciles only this way: its eight non-ocean points are
`INSUFFICIENT_DATA`, not land. **The fixture rule follows the census, not the geography** — and
"an all-ocean store reports them equal" is true only of a store that also holds none of the four
covered-but-unfitted members, which is stated at the test rather than left to be debugged as a land
bug the first time a stray `SCREENED_OUT` fires.

**2. THE INTERRUPTION LADDER IS THREE ARMS, NOT TWO.** Two stores show the coverage rate unchanged;
**three show that it does not move with the thing it must not move with**, and that the wrong
denominator is *monotone in the wrong direction* — 0.75, 0.15, 0.03 as the run is killed earlier.
**The failure is then legible rather than merely detectable**, which is what a reader needs from a
test that fires in five years.

**3. BOTH TRIPWIRES FIRED ON THE FIRST RUN OF THE NEW CODE, AND NEITHER WAS A FALSE ALARM.** The
golden table caught `core/outcomes.py` moving 1 → 2 (the second division) and `report/numbers.py`
arriving at 0; the consumer-set test caught the third `failure_tally` caller. **Both were exactly
the deliberate additions the ruling said must be deliberate**, and both were updated with their
reason at the row. The table did its job before it was needed and then again the moment it was.

### AND ONE DESCRIPTION THAT SURVIVED THE CHANGE, FOUND BY SWEEPING FOR IT

`FailureTally`'s own docstring table called `eligible` *"section 14.2's coverage population"* — which
is now precisely what it is **not**. Corrected where it sits, with the struck text kept: `covered` is
that population. `is_eligible`'s summary line said *"whether this point counts toward a failure-rate
denominator"*, equally true of both and therefore useless for telling them apart; it now says which
question it answers and names its sibling. **(a6): when code is replaced, sweep for the descriptions
that survive it** — and a predicate's docstring is the description most likely to be read *instead*
of the code.

### WHAT THE SWEEP CAUGHT AND THE TARGETED RUNS DID NOT — A RENAME, FOR THE SECOND TIME

**`tests/test_exit_criteria_2e.py::test_every_criterion_names_evidence_that_exists` failed on the
first full sweep of Task 2's code**, alone, after 36 green tests in the two files I had been running.
2e's **criterion 8** names its evidence by test name, and Task 2 renamed that test — three properties
to four — so a **closed criterion pointed at a test that did not exist.**

**THIS IS THE HANDOFF'S OWN FOURTH INSTANCE OF ONE SHAPE**, and the table there already predicts it:
*the display's rename missed a reader of the STRING, found by the full sweep.* **An output is an
interface, and a test name read by a criterion's record is an output.** A search bounded by "what
does this test assert" cannot reach a record in another file that merely spells it.

**AND IT HAD HAPPENED BEFORE, TO THE SAME NAME, FOR THE SAME REASON.** The comment sitting beside
the record describes the 2026-09-19 edit: `..._by_both_properties_...` became
`..._by_all_three_properties_...` when `is_fit_verdict` arrived. **So the repair was not to make that
edit a second time.**

> **A NAME THAT CARRIES A COUNT OF A GROWING SET IS RENAMED EVERY TIME THE SET GROWS, AND EVERY
> RENAME SILENTLY BREAKS EVERY RECORD THAT NAMES IT.** The count is now out of the name —
> `test_every_member_is_classified_by_every_predicate_in_one_table` — which is true at any width.
> Two breakages, each found by the full sweep and by nothing else, are enough evidence that the
> third was coming.

**THE VERDICT DID NOT MOVE AND WAS NOT RE-ARGUED.** Criterion 8's reading stays *"both properties,
enumerated"* — that is what 2e read, and a later sub-phase adding a column does not retroactively
widen a met criterion. Only the pointer was repaired, which is the handoff's provenance-versus-value
distinction doing exactly the work it was written for.

**AND IT IS THE NINTH THING THE FULL SWEEP HAS CAUGHT THAT A FAST RUN COULD NOT.**

---

## Plan Task 3 — the drop row, audited before any code (2026-09-23)

**THE BRIEF** is the plan's Task 3 as amended by the ruling of 2026-09-23: `CANDIDATE_DROPPED` gets
its own row outside the failure rate with its own denominator (D11); the carried record is primary
and is recomputed from `out.pass1.zarr` when present; **the covered-population composition is
printed by member rather than as one gap figure with an interpretation**; and a dropped candidate
must not print as *"nothing fitted"*. **Four findings, and the first two are corrections to things
already written — one of them mine, in shipped code.**

### (a5) "THE GAP IS THE LAND EXPOSURE" IS THE ERA ERROR, AND I SHIPPED IT IN TASK 2's MODULE DOCSTRING

The ruling corrects its own earlier wording, and **the same sentence is in `report/numbers.py`,
which I wrote two days after finding the defect in the plan**: *"the gap between them is the store's
own exposure: on a box with no land and a finished run they are identical."*

**IT IS ONLY TRUE BECAUSE OF WHAT TODAY'S DATA HAPPENS TO CONTAIN.** Land reaches the covered
population as `INSUFFICIENT_DATA` until §13.6's mask lands, so "the gap is land" describes the
current *contents* of a label rather than the label's *meaning* — **which is exactly the conflation
D2's reframing was written to undo**, and the reason `INSUFFICIENT_DATA` was mis-classified for four
sub-phases. I found that defect in the plan's Task 2 text on 2026-09-22 and reproduced it in my own
module docstring on the same day.

**STATED CORRECTLY, THE GAP IS `covered - fitted`, AND IT IS THREE POPULATIONS WITH THREE CAUSES:**

| member | why it is covered and not fitted |
|---|---|
| `INSUFFICIENT_DATA` | the record is too thin to fit — **plus land, until §13.6 declares a mask** |
| `SCREENED_OUT` | a decision was taken not to fit this candidate here |
| `CANDIDATE_DROPPED` | the early-abort verdict demoted the candidate run-wide |

**SO THE REPAIR IS NOT A BETTER SENTENCE, IT IS A DIFFERENT OUTPUT.** A single gap figure carrying
an interpretation is how a stray `SCREENED_OUT` gets debugged as a land bug; **print the
composition, by member, with counts, and let the reader interpret three named causes.** Computed
inside `failure_tally` so there is still one definition, derived from counts alone so it keeps
working on someone else's store — and the report still computes nothing.

> **(a6) SWEEP THE DESCRIPTIONS, INCLUDING THE ONES YOU JUST WROTE.** Task 2's module docstring, its
> `ReportNumbers` prose and the test named
> `test_the_two_rates_separate_where_a_reached_point_carries_no_fit_verdict` all carry the "exposure"
> reading to some degree. The test's own name is already right — *a reached point carrying no fit
> verdict* — which is the correct statement, so the defect is in the prose around a test whose
> subject was never wrong.

### (c5) A DROPPED CANDIDATE READS AS "NOTHING FITTED", WHICH IS THE `no_evidence` COLLAPSE IN REVERSE

In pass 2 a dropped candidate is `CANDIDATE_DROPPED` at **every** point, so `fitted == 0` and both
rates are unavailable under the shared condition — with the reason *"no point was fitted"*.
**Literally true and misleading: it presents a DECISION THE RUN TOOK as a LACK OF EVIDENCE.**

**D1 stopped "unjudged" from printing as a clean pass; this is the mirror**, and the mirror needs
saying because the two failures look nothing alike from inside the code that produces them — one is
a rate of `0.0`, the other is no rate at all. **Both are a report describing the run's own decision
as a property of the data.**

**ONE CALCULATION SERVES BOTH BRANCHES**, which is why this is the same finding as the one above and
not a second feature: the covered-population composition is what makes *"nothing fitted: 900
`CANDIDATE_DROPPED`"* different from *"nothing fitted: 900 `SCREENED_OUT`"*, and it is the same
breakdown printed beside the rates when `fitted > 0`.

**THE THREE TESTS, EACH WITH ITS BUG**, from the ruling and written here so they are owed before the
code: a dropped candidate's pass-2 row **names `CANDIDATE_DROPPED`** (catches the verdict
disappearing into "nothing fitted"); a candidate screened out everywhere **still names
`SCREENED_OUT`** (catches the new reason overwriting the old case); a mixed covered population
**lists every member with its count** (catches a reason naming only the largest member).

### AND THE DROP ROW'S DENOMINATOR RESTS ON A PREMISE NOBODY HAS WRITTEN DOWN

**The carried record predates `is_covered` and cannot be repaired retroactively.**
`twopass._verdict_attrs` writes, per candidate, `failed` / `eligible` / `fitted` / `rate` — **no
`covered`**, because the predicate did not exist when 2e wrote it. 2e's criterion 14 establishes the
drop row's denominator as *"pass 1's eligible points for that candidate … what the recorded
verdict's `eligible` equals"*.

**SO THE DROP ROW'S DENOMINATOR IS `eligible`, AND `eligible` IS THE ONE WE JUST PROVED DILUTES.**
It counts `NOT_ATTEMPTED`. The carried number is safe only while **pass 1 holds no `NOT_ATTEMPTED`**
— true of a *finished* pass 1, and a verdict is only reached after pass 1 completes.

> **THAT IS THE SAME SHAPE AS §12.5's "a finished store should hold none", WHICH IS THE PREMISE THIS
> SUB-PHASE ALREADY BROKE ONCE.** A number defensible under a completeness assumption, with the
> assumption stated nowhere near it. **So state it and assert it**: when `out.pass1.zarr` is
> present, the recomputation asserts `covered == eligible` on pass 1 alongside asserting the rates
> agree. If that ever fails, the drop row's denominator is diluted and it fails loudly instead of
> reading low. When pass 1 is absent the row is labelled carried and the premise is **unchecked**,
> which the label already says and which is now said about the denominator too.

### 2e's CRITERION 14 DOES NOT FLIP TO MET — RULED 2026-09-23

The plan says Task 3 *"closes 2e's criterion 14"* and the standing requirement says no 2a–2e verdict
moves. **Read as a flip, those conflict; read under the 2026-09-20 distinction, they do not.** A
verdict's RECORD may be corrected; its VALUE is not re-argued.

**2e's 14 records what 2e DELIVERED, and 2e did not deliver the drop row. It stays
`MET_WITH_REDUCED_SCOPE`.** Its record gains a dated forward pointer naming where the scope was
completed — **2f's criteria 8 and 9** — and whether the drop row now exists is answered by 2f's own
criterion, not by editing 2e's. **Otherwise "what 2e delivered" becomes a statement that is
historically false**, and a reader reconstructing the project's sequence from its records is misled
by the records themselves.

**THE PLAN'S TASK 3 TEXT CARRIES THE FORWARD-POINTER FORM** so *"closes"* cannot be read the other
way, and the standing requirements' inherited list reads **"2e's 14 reduced, scope completed in
2f"** — the entry stays visible rather than being dropped once it is satisfied.

**THE SHA HAS ONE OWNER**: 2f's criteria record, written at Task 10, is where 2f's verdicts are
taken and where the delivering commit is stable and knowable. The forward pointer names the criteria
now; **Task 10 fills the sha**, and that obligation is on Task 10's row rather than floating.

### THE EVIDENCE-NAME GUARD ALREADY EXISTS IN EVERY SUITE THAT HAS RECORDS, AND IT FIRED

**The ruling's premise is that criterion 8's pointer "broke silently". It did not break silently —
it broke LOUDLY, and the guard the ruling asks for is the test that caught it.**

`test_every_criterion_names_evidence_that_exists` exists in **2b, 2c, 2d and 2e**, one per suite,
each `ast`-parsing every `tests/test_*.py` for `def test_…` and asserting every name in every
criterion's `established_by` resolves. 2e's own docstring says it catches *"a test renamed during a
refactor"* and names two earlier renames. **Nothing is missing and nothing needs adding for the
phases that have records.**

**THE SILENCE WAS MINE, AND IT WAS A PROCESS FAILURE RATHER THAN A COVERAGE ONE.** I ran
`tests/test_outcomes.py` and `tests/test_report_numbers.py` — the files I was editing — and the
guard lives in a file I was not editing. **That is the whole point of the sweep running last**, and
the sweep did its job on the first attempt. The lesson is not "add a guard"; it is that **a rename
is a change whose blast radius is every file that spells the name**, which the handoff already
states as *an output is an interface — grep for the string, not for the module*.

**2a IS NOT A GAP EITHER**: its suite has no `established_by` records at all — its criteria ARE test
functions named `test_criterion_N_…` by convention, so there is no pointer that can dangle.

**TWO RESIDUAL GAPS ARE REAL AND BOTH BELONG TO TASK 10:**

1. **2f has no criteria suite yet**, so 2f's own records are guarded by nothing until Task 10 writes
   them. The guard must ship WITH the records, not after.
2. **A test named in PROSE is invisible to the guard, which reads `established_by` only.** Measured
   today across all four record modules: 26 / 34 / 29 / 44 structured names, and **zero** names that
   appear only in prose — so there is no live instance. **But 2f's plan already has one**: criterion
   21's reading cites `tests/test_hashing.py::test_compat_relevance_is_an_allowlist_golden_set` by
   name, in prose. **It must land in `established_by` at Task 10 or the guard will not see it.**

### (a10) THE DOCSTRING-TABLE TEST FAILS FOR TWO REASONS WITH ONE MESSAGE

`test_every_member_is_classified_by_every_predicate_in_one_table` can fail because **the table is
unparseable** or because **the table disagrees with a predicate**. One message for two causes
teaches the reader to fix the parser when the table is wrong — **the same trap as a fixture builder
whose failure reads as the subject failing**, and the documented end state is a check that gets
loosened. Split: a parse failure names the line it could not read; a disagreement names the member,
the predicate, the table's value and the code's.

### TASK 3, AS BUILT (2026-09-23) — AND ONE CORRECTION TO THIS ENTRY'S OWN PROPOSAL

**THE PRE-FLIGHT SAID "ASSERT `covered == eligible` ON PASS 1". THE CODE REPORTS IT INSTEAD.**
An assertion inside `describe` would make the report **refuse** a store whose pass 1 holds unreached
points, and **D6 says an unfinished or inconsistent store is DESCRIBED, not refused** — a report
that raises cannot be run on the store that has the problem, which is the property §14.2 exists for.
So the premise is a **named defect** in the section's output and an **assertion in the test**, where
refusing is the right behaviour. **Two homes for one check, each doing what its context allows** —
and the pre-flight's wording was the wrong one for the half that ships.

**WHAT LANDED**: `report/drop.py`, at **zero** division nodes in the golden table like its sibling.
The row's denominator is pass 1's live population (**9** on the criterion-14 fixture, against pass
2's **36** — a row computed over pass 2 cannot produce 9). The carried record is primary; when the
pass-1 sibling is present its arrays are recomputed and compared, and disagreements are reported and
never resolved. `no_evidence` prints as itself; a store with no verdict prints its reason and no
empty drop table, because *"the question was never asked"* and *"nobody was dropped"* are different
facts and an empty table cannot distinguish them.

**THE TAMPER TEST IS THE (a10) HALF THAT THE AGREEMENT TEST CANNOT PROVIDE.** A `describe` that
reads the record, sees pass 1 present, and stamps *"recomputed"* without comparing passes the
agreement test on every store whose record is right. One field edited by +1 is what tells a
comparison from a constant.

### AND THE IMPORT BOUNDARY WAS AIMED AT THE READER ALONE, WHICH TASK 3 MADE VISIBLE

`report/drop.py` imports `metamer.batch.decimate` for the pass-1 path convention — **a
`metamer.batch` submodule, which is exactly the kind of arrival the boundary exists to notice** —
and the run-time probe only ever imported `read_store`. **It would have been silent.** Measured
before writing the import: `metamer.batch.decimate` is **712** modules with no forbidden member, so
reusing the convention is safe and the alternative — the report deriving the path itself — would
have been a second definition of it.

**The probe now imports and calls both report modules**, and the docstring says every new report
module is added to it. *A control proves the detector, not what it is pointed at*, one sub-phase
after that rule was written, in the instrument it was written about.

> **AND THE READING MOVED 933 → 935, WHICH IS NOT DRIFT AND MUST NOT BE READ AS IT.** The ceiling's
> re-derivation rule is about a reading moving **under a fixed subject**; here the SUBJECT grew by a
> module. **A band describes a subject**, so it is RE-MEASURED rather than compared against, and the
> distinction is stated at the test: a number that would have been a rule violation under one
> reading is an expected re-baseline under the other, and only the docstring can tell them apart.
> **CI's three readings on the new subject are owed at the next green run.**

---

## Task 3's DEFECT — the drop row showed a rate the gate never used (2026-09-23)

**FOUND BY THE USER, THE DAY TASK 3 LANDED, AND MY OWN "PREMISE" CHECK WALKED PAST IT.** I found
that the drop row's carried denominator is `eligible`, established that `eligible` counts
`NOT_ATTEMPTED`, and guarded the case where pass 1 holds unreached points. **That guard is real and
it is about dilution. It is not the larger problem sitting in the same field.**

### THE DEFECT

**Since `f4eb42f` the gate decides on `failed / fitted` (D2b). The row printed the recorded `rate`
— which IS the gate's — beside `live = eligible`, which is NOT the rate's denominator.** The rate
and the number under it described different populations.

On criterion 12's own fixture: **the gate drops a candidate at 12/12 = 1.00 against a threshold of
0.90, and the row reports 12/20 = 0.60.** A dropped candidate displayed **below the threshold that
dropped it**. Any reader concludes the gate is broken.

> **THIS IS D2b's DEFECT, ON THE ONE ROW WHOSE JOB IS TO REPORT THAT DECISION.** D11 already states
> the principle — *a decision's evidence is what the run saw when it made the decision* — and I
> implemented the row against D11 while breaking exactly that sentence. **A principle quoted in a
> docstring is not a principle applied**, and the check that would have caught it is the one now
> added: re-apply the gate's own comparison to the displayed rate and confirm it reproduces the
> recorded decision.

### WHAT LANDED, IN THREE PARTS

**(1) The row shows the denominator the WRITING GATE used**, named at the row: `fitted` for a store
written after the move, `eligible` for an older one — **correct for that store, because its gate
really did threshold on `eligible`**. `eligible` is still printed, as a count, because the gap
between it and `fitted` is a real statement about the coarse sample; it is simply not this rate's
denominator.

**(2) The denominator is INFERRED today and must be RECORDED tomorrow.** `fitted` arrived at
`49f3db1` and the gate moved at `f4eb42f`, so **a store written between them carries `fitted` and
was decided on `eligible` — field presence cannot separate those two cases.** The ambiguity is
stated at `gate_denominator` rather than hidden, and is safe only because no committed store comes
from that one-day window. **Task 4's additive write owes the recorded name**, which has the same
shape as `threshold` and `policy`: a fact that exists nowhere else in the store.

**(3) The report checks itself against the decision, at run time.** For every judged candidate — not
only the dropped ones — the displayed rate is compared to the recorded threshold using **the gate's
own strict `>`**, and the result checked against the recorded `above_threshold`. A mismatch is a
named defect, never silently resolved. **That makes the invariant hold on someone else's store
rather than on our fixtures**, which is the only place it matters.

**AND THE MISMATCH IS ONE-DIRECTIONAL, WHICH IS WHY THE DROPPED CASE IS THE DANGEROUS ONE.**
`eligible >= fitted` by the nesting chain, so `failed / eligible <= failed / fitted`: a wrong
denominator can only make a rate look **smaller**. A kept candidate stays below the threshold either
way; a dropped one can be shown below it. **The check covers both anyway** — "which direction can it
fail in" is an argument, and an argument is not a test.

### AND THE PROBE'S SCOPE WAS A HAND-PICKED LIST, WHICH IS THE GOLDEN TABLE'S LESSON UNLEARNED

Yesterday the probe was aimed at the reader and missed `drop.py`; I repaired it by **naming both
modules**, which misses `maps.py` exactly as surely. **The scope is now discovered** —
`pkgutil.walk_packages` over `metamer.report`, every module imported, the numbers path then run —
and **the discovered set is asserted against the directory**, because a walk that returned nothing
would make the whole probe vacuous in precisely the way the 65-module ceiling was. **Task 8's entry
point replaces it with `python -m metamer.report <store>`**, which needs no list at all.

**THE READING MOVED 935 → 936, THE SECOND SUBJECT CHANGE IN ONE DAY.** Recorded with what changed,
because only the docstring can distinguish a re-baseline from the drift the re-derivation rule is
about. **CI's readings on the drop subject came in at 914/915/922 — exactly the +2 predicted** —
which is the first evidence that the local-versus-CI gap is a constant offset rather than something
that moves with the subject.

---

## Plan Task 4 — the primitives sections and the resolved-candidate record, audited before any code (2026-09-25)

**THE BRIEF** is the plan's Task 4: an additive root-attrs block written by the RUN recording, per
candidate, the resolved engine / cost class / gradient mode / objective, plus a `domain_mask`
provenance field; and the report's single-store sections — `n_valid`'s distribution, the iteration
histogram, the resolved config with its three hashes. **Plus one thing the plan does not list: the
`denominator` name Task 3's defect fix left owed.** Five findings, and the first is a live defect in
code I wrote three days ago.

### (a5) THE `domain_mask` CAVEAT TESTS PRESENCE AND THE PLAN REQUIRES THE VALUE — THE ERA ERROR, THIRD INSTANCE

`report/numbers.py` decides the caveat with

    caveat=None if "domain_mask" in view.attrs else NO_DOMAIN_MASK_CAVEAT

— **presence**. The plan says: *"**Absent or false**, `INSUFFICIENT_DATA` unions thin records and
land … **True**, the caveat drops."* Those agree on every store that exists **because no store
carries the field at all**, so presence and truth are the same question today.

**TASK 4 IS THE COMMIT THAT SEPARATES THEM.** It writes the field — including `false`, for a run
with no declared mask, which is every run until §13.6 lands. **On that day the caveat silently
drops while the denominator is still approximate**, and the report claims an exactness it does not
have. That is the defect the caveat exists to prevent, arriving **through the field added to fix
it**.

> **THIS IS THE SAME SHAPE AS "THE GAP IS THE LAND EXPOSURE" AND AS `NOT_ATTEMPTED`'s ELIGIBILITY:
> code that is right only because of what the data currently CONTAINS.** Three instances in four
> days, two of them mine, and the tell is identical each time — **a predicate that agrees with its
> subject on every value anyone has seen.** The repair is the same shape too: test the thing you
> mean. `attrs.get("domain_mask") is True`, with `False` and absence both keeping the caveat and
> **saying which**, because *"the run declared no mask"* and *"the run that wrote this store did not
> record whether it had one"* are different sentences and D6's vocabulary already distinguishes
> them.

**AND MY TASK 2 TEST CANNOT CATCH IT**, which is why it is (a5) and not a typo:
`test_the_caveat_is_present_without_a_domain_mask_and_absent_with_one` passes
`{"domain_mask": "declared"}` — a truthy string. It exercises presence twice and the value never.
**Both arms of a two-arm test can sit on the same side of the distinction the test is named for.**

### THE ADDITIVE BLOCK HAS A PRECEDENT IN THE TREE, ARGUED, AND IT IS CITED RATHER THAN RE-ARGUED

`store.py`'s `decimation` block already carries the exact argument Task 4 needs, in its own comment:
**not in `REQUIRED_ATTRS`** (which "would refuse every store written before this task"), **absence
is the answer**, and **no schema bump is owed** — *"a bump is for a question an older store CANNOT
answer, and every earlier store's silence here is unambiguous"*. `calibration` is the second
instance and `source_*` the third.

**So D12's three constraints are already implemented twice and the work is to follow the pattern,
not to invent it.** The one thing to check rather than assume: `create_store` refuses on
`REQUIRED_ATTRS`, so **adding either new key there would refuse every existing store** — the block
and the `domain_mask` field are optional by construction.

### THE HASH ASSERTION IS OWED EVEN THOUGH THE STRUCTURAL ARGUMENT IS SOUND

The three hashes are computed from `normalize(config)`, not from attrs, and the block records what
resolution **produced** rather than what the config **said** — so it cannot reach a payload. **D12
says "asserted, not assumed" and it is right to**: the argument is about where the block comes from,
and a later change that derived a block field from a config field would break it silently. The test
is the three hashes of a store carrying the block against the same config without it, and 2f's
criterion 21 additionally cites `tests/test_hashing.py::test_compat_relevance_is_an_allowlist_golden_set`
by name — **in prose, where the evidence-name guard cannot see it**, which is Task 10's second owed
item.

### THE FILL CONSTANTS HAVE ONE DEFINITION AND THE REPORT MUST IMPORT IT

`N_VALID_UNSET = -1` and `ITERATIONS_UNSET = 65535` live in `metamer.batch.store`. **Re-spelling
either in the report is a second definition of a sentinel**, which is the defect this sub-phase has
now paid for twice under a different name. Measured before relying on it: `metamer.batch.store` is
**928** modules and carries no forbidden member — `pydantic` arrives with `batch.run`, not with
`store` — so importing the constants costs the report nothing it has not already paid.

**AND THE EXCLUSION IS ONLY HALF THE RULE.** The plan says the fill values are excluded from the
distributions **and counted separately**: a histogram with a spike at 65535 reads as a real
population, and a histogram that silently drops them reads as a smaller grid. Both halves are the
same defect the branch table already solved for `NOT_ATTEMPTED` — **counted, never divided by**.

### AND TASK 3's FIX LEFT AN OWED WRITE, WHICH BELONGS IN THIS TASK'S ADDITIVE CHANGE

`gate_denominator` infers which population the early-abort gate thresholded on, from field presence,
because `fitted` arrived at `49f3db1` and the gate moved at `f4eb42f` — **a store written between
them carries `fitted` and was decided on `eligible`, and presence cannot separate those.** Task 4
writes the name into `early_abort` attrs, on the same rule as `threshold` and `policy`: **a fact
that exists nowhere else in the store.** §17's measure/print rule, fourth instance.

**IT IS A SECOND WRITE SITE, NOT THE SAME ONE** — `_verdict_attrs` in `twopass.py`, not
`provenance_attrs` in `store.py` — and it inherits the same three constraints: additive, absent on
older stores, and absence means `eligible`. **When the name is present nothing is inferred**, and
the ambiguity window closes for every store written after this task.

### (e) THE PLAN'S FOURTH TEST CANNOT BE BUILT AS WRITTEN, AND WHAT REPLACES IT BITES HARDER

The plan wants a test where *"the recorded resolved engine differs from the run-level `engine` attr
for a candidate whose capability intersection narrows it"*. **Measured against the tree: the run
never narrows the engine.** `run.py` passes `engine=config.engine` into the fit path and `fit()`
uses it; **`engine_costs()` has no consumer anywhere outside `terms.py` and `capability.py`** — no
batch module calls it. So `resolved engine == requested engine` for every candidate, always, and a
test asserting they differ would have to fabricate the condition it checks.

**WHAT DOES NARROW PER CANDIDATE IS THE OTHER TWO, AND THEY NARROW FOR DIFFERENT REASONS:**

| field | narrows? | by what rule |
|---|---|---|
| engine | **no** — the request passes straight through | nothing in the batch path intersects it |
| **cost class** | **yes** | `intersect_engine_costs` takes the **worst** cost across terms, so a composite is dearer than its cheapest term |
| **gradient mode** | **yes** | `ANALYTIC` only if **every** term declares *and implements* it; one finite-difference term makes the composite finite-difference |
| objective | no | run-level, recorded per candidate for completeness |

**So the test is rewritten onto the fields that can actually move**: a single-term candidate and a
composite over the same config, whose recorded cost class and gradient mode differ from each other.
**That catches the defect the plan's bullet was aimed at** — a block recording the request rather
than the resolution — and it catches it on a fixture the tree can produce.

> **AND THE ENGINE ROW IS A FINDING RATHER THAN A GAP TO FILL HERE.** §4.2's capability intersection
> exists and the batch path does not consult it, so a candidate whose surviving set excludes the
> requested engine is run on it anyway. **That is not 2f's to fix** — 2f reports what the run did —
> but recording the resolved engine beside the requested one is what would make it VISIBLE, which is
> the measure/print rule's whole point. Filed as an observation with the block, not taken.

### AND THE RESOLUTION IS COMPUTED PER FIT AND THROWN AWAY — (a2c)'s FIFTH INSTANCE

`FitResult` carries `engine`, `objective` and `gradient_mode`, resolved inside `fit()` by
`resolve_gradient_mode`. **`gradient_mode` appears nowhere in `src/metamer/batch/` at all.** The run
resolves it, records it in the result, and drops it before the store — *a value the driver holds and
does not persist*, which is exactly why D12 is right that §14.2's bullet is not computable from the
store.

**THAT SETTLES WHERE THE BLOCK'S NUMBERS COME FROM, AND IT IS A REAL CHOICE.** `provenance_attrs`
runs at store creation, **before any fit**, so the block cannot copy a `FitResult`. It must resolve
from `(spec, requested engine, objective, registry)` — and D12 refuses exactly that shape for Phase
5, on the ground that it answers *"what would this config resolve to NOW"*.

**THE TWO ARE DIFFERENT AND THE DIFFERENCE IS THE REGISTRY.** Phase 5 would re-resolve against
*a later* registry; the block resolves inside the run, against **the registry the fits are about to
use**, whose version is already in root attrs beside it. The resolution is deterministic in those
four inputs and none of them moves during a run, so the block's answer is the answer the fits
produce. **That is an argument, and an argument is not a test** — so the binding test asserts the
block's recorded resolution **equals what `FitResult` carries** for the same candidate on a real
run. If the two ever disagree, the block is describing something the run did not do, which is the
whole risk D12 names.

### TASK 4, AS BUILT (2026-09-26) — AND THE BOUNDARY MOVED THE SHARED DEFINITION

**THE ENGINE COLUMN IS FILLED THROUGH THE RESOLUTION PATH OR NOT AT ALL.**
`core/resolution.py` computes each candidate's resolution **from the spec alone** — it never receives
`config.engine` — and the engine column carries `ENGINE_NOT_RESOLVED`, *"requested; not resolved per
candidate in this version"*. The two columns that genuinely narrow today are asserted to differ on a
fixture that makes them: **`matern32` withholds `celerite2`**, so `white` survives on four engines
and `white + matern32` on three. **The gradient-mode column does not discriminate on that fixture**
— no family in the set implements analytic gradients — and the test says so rather than leaving it
to be discovered.

**THE ENGINE-NARROWING TEST IS FILED AT A TRIGGER**, in PROGRESS beside P4″: the second engine.

### NO RUNTIME PATH MOVES A SERIES' RESOLUTION, AND THAT IS WHY THE PRE-FIT LABEL IS THE WHOLE TRUTH

The ruling asked for this to be established rather than assumed. **Four pieces of evidence, none of
them a docstring's say-so:**

| checked | found |
|---|---|
| where the gradient mode is resolved | `fit()` calls `resolve_gradient_mode(spec, objective)` **once per candidate, before the per-series loop** — it cannot vary by series |
| whether it can downgrade | it **raises** `AnalyticGradientError` rather than downgrading, and says why: *"a mode corrected behind the caller's back is not a reported mode"* |
| whether the engine can swap | bound once per `fit()` call from the caller's argument; `run.py` passes one engine for the whole run |
| whether any per-series fallback exists | **one does** — the starting-value rung, explicitly *"per series"* — **and it is a different quantity, already persisted per (series, candidate)** |

**So the label is `"run start, against registry version N"` and it is complete.** Had a fallback
existed, the binding test's fixture would have had to trigger it, the test would have failed on that
series, and **that failure would have been the correct signal** — the label would then have read
*"plan at run start; per-series fallback not recorded"* with the missing record filed as a gap. It
does not, so it does not.

> **AND THE BINDING TEST'S LIMIT IS WRITTEN AT THE TEST.** It binds the block to the RESOLVER; what
> binds the resolver to the fit path is the finding above. **If a runtime fallback is ever added the
> test keeps passing and the label becomes false**, so the finding lives where the label is rather
> than in this document alone.

### THE THRESHOLD COMPARISON HAD THREE SPELLINGS BEFORE I ADDED A FOURTH

The ruling said to import the gate's comparison rather than re-spell it. **Measured: it was already
spelled three times** — `abort._decide` as `(rate.rate or 0.0) > threshold`, and
`twopass._verdict_attrs` and `__main__` as `rate.rate is not None and rate.rate > threshold`. Two
spellings, three modules, one rule. They agree for every threshold in [0, 1], **and agreeing is not
being one rule**.

**AND THE IMPORT BOUNDARY REFUSED THE OBVIOUS HOME, WHICH IS THE FINDING.** The ruling expected
`abort` to be importable — *"abort isn't on the forbidden list, and your walked-package probe will
confirm"*. **The probe's logic confirmed the opposite, before the commit**: importing
`metamer.batch.abort` pulls **`pydantic`** transitively, through `batch.completion` and
`batch.resume`, taking the graph to 999 modules with a forbidden member present. So the gate's own
rule **could not live in the gate's own module and still have one definition**. It went to
`core.outcomes`, beside `failure_tally`, for exactly the reason `failure_tally` is there — and all
four consumers now call it.

### THE CEILING DOCSTRING IS A BASIS AGAIN, NOT A CHANGELOG

The per-subject table and its CI triples are gone. What stays: **the spread (~21 modules across four
environments, measured on two subjects, moving together)** and the rule that the margin must exceed
it. The diagnostic line now prints `headroom` alongside the count, so **every run states its own
margin** and no figure is transcribed into a docstring that five more tasks would each have to edit.
Re-derivation triggers are the ruled ones, **plus one deliberate re-derivation at Task 8** when the
subject becomes the entry point.

### WHAT THE SWEEP CAUGHT IN TASK 4 — PROVENANCE THAT DEPENDED ON `PYTHONHASHSEED`

**One failure, in a file I had not touched**:
`tests/test_store.py::test_the_root_attrs_are_byte_identical_across_processes`. The
resolved-candidate block's `engine_costs` mapping comes from `intersect_engine_costs`, which builds
it **from set iteration** — so its key order varies with the interpreter's hash seed. **Measured at
three seeds: three different orders for identical content.** Two runs of one config therefore wrote
byte-different root attrs.

**IT IS THE (k) SHAPE, AND (k) IS WHY THE GUARD THAT CAUGHT IT IS CROSS-PROCESS.** The order is a
property of a *different* process, and no amount of testing inside one process reaches it — every
one of Task 4's own seven tests passed, because they all drew whatever order their single process
happened to draw. **The store's cross-process test is the only thing in the tree that could see
it**, and it is in a file this task never opened.

**The fix is two lines and the lesson is not.** `as_record` sorts by engine name; verified
byte-identical across four seeds afterwards. The lesson is that **a mapping handed to provenance is
not data until its order is decided** — `sorted` at the boundary where bytes are produced, not
hoped for from the producer.

> **AND IT IS THE TENTH THING THE FULL SWEEP HAS CAUGHT THAT A FAST RUN COULD NOT.** The previous
> one was a renamed test a closed criterion named as its evidence; this one is a hash-seed
> dependency. **Neither was in a file the task had opened**, which is the property that makes the
> sweep's cost worth paying and the reason it runs last rather than being sampled.

---

## Plan Task 5 — selectability, audited before any code (2026-09-27)

**THE BRIEF** is the plan's Task 5: three quantities from stored arrays — **fits** from
`/selection/n_valid`, **contention** as `count(isfinite(delta_ic))` per criterion, **no winner** as
`selected == -1` per criterion — with denominators excluding `NOT_APPLICABLE`. **Four findings, and
the first would have shipped two different quantities under one word in one report.**

### (a5) "FITS" IS ALREADY TAKEN IN THIS REPORT, AND IT MEANS SOMETHING ELSE

Measured in the tree rather than read off the plan:

| quantity | definition | where |
|---|---|---|
| `n_valid` | **`count_nonzero(outcome == OK)`** per point | `criteria.py:373`, criterion-independent by construction and by a runtime check in `write.py` |
| Task 2's `fitted` | `count(Outcome.is_fit_verdict)` — **OK plus the eight failure codes** | `core.outcomes.failure_tally`, shipped at `c15e74e` |
| contention | `scored & isfinite(values)` — **narrower than `n_valid`** | `criteria.py:349` |

**The plan calls `n_valid` "fits". Task 2's report already prints a column called `fitted` that
means something strictly larger.** On any store where a candidate failed, the selectability section
and the per-candidate table would print different numbers for what a reader reasonably takes to be
one quantity — **in the same document**. That is D1's tell, and it is not hypothetical wording: the
tree already carries it at `criteria.py:211`, where `n_valid`'s own attribute doc reads *"Number of
candidates that **fitted**"* for a count of `OK`.

**SO THE SECTION DOES NOT USE THE WORD.** `n_valid` is *candidates that converged*; `fitted` stays
Task 2's `is_fit_verdict` count; and the section states the relationship rather than leaving a
reader to discover it by subtracting two numbers that look like they should match.

### AND THE RELATIONSHIP IS AN IDENTITY, SO IT IS ASSERTED RATHER THAN DESCRIBED

`is_fit_verdict` partitions into `OK` and the eight failures — exactly, with no third case, which is
Task 2's nesting chain read at one point instead of over the enum. So **per point:**

    n_valid == fitted − failed

**That binds the two sections to each other.** If either drifts — a new member classified into
`is_fit_verdict` but not into the OK/failure split, or a selectability section that starts counting
`rankable` — the identity breaks and says so. **A relationship stated in prose is a claim; this one
is arithmetic over two sections' own outputs**, which is the strongest form available and costs one
assertion.

### THE THREE QUANTITIES NEST, AND THAT IS WHY THE PLAN SAYS "THREE FACTS, NOT ONE"

    rankable (contention) ⊆ n_valid (converged) ⊆ fitted (fit verdict)

**Both inclusions can be strict and each strictness has its own cause.** `rankable ⊂ n_valid` when a
fit succeeds and its criterion value is not finite — §12.5's construction, AICc at `n ≤ k + 1`,
which is why the same point can be contended under AIC and not under HQIC. `n_valid ⊂ fitted` when a
candidate produced a fit verdict that failed. **The plan's own invariant — "`n_valid == 1` is not
'the selection was forced'" — is this nesting stated at one value**, and the report must not collapse
it: a point with `n_valid == 1` may have had ten rankable candidates under another criterion.

### THE FLOAT32 CAVEAT IS CONSTRUCTIBLE, SILENT, AND WARNED — ALL THREE MEASURED

`/selection/delta_ic` is **float32** and the ranker computes in **float64**, so a delta finite in
float64 and larger than ~3.4e38 becomes `inf` on write. **Measured: `np.float32` takes 1e39 to
`inf`, emitting a `RuntimeWarning` and no error.** So a contention count taken over the stored array
is biased by the storage dtype, silently, in the direction of *fewer* rankable candidates.

**REACHABILITY IS STATED RATHER THAN ASSUMED, AS IT WAS FOR THE DOMAIN MASK'S TRUE ARM.** The test
plants the value; whether real data reaches 1e39 in a delta-IC is **not established here** and the
test says so. §14.2 calls this worth a test rather than a schema change, and a test for a state
nobody has observed must say that nobody has observed it — otherwise a later reader reasons about
real stores from a branch nothing has ever written.

### AND `selected` HAS THREE STATES, TWO OF WHICH ARE NEGATIVE

`-1` is *no winner* and `-2` is `SELECTED_UNSET`, *nothing wrote here*. **Any test of "is this a
no-winner point" written as a truthiness or a sign check reads them alike** — `bool(-1)` and
`bool(-2)` are both `True`, and `< 0` catches both. The store's own fill-value table exists because
this distinction is load-bearing: an interrupted run is full of `-2`, and counting those as
no-winner would report a selection failure that is really an absence of information. **The same
shape as `NOT_ATTEMPTED` in the branch table**, one array over.

---

## Plan Task 6 — the clustering statistic and its null, audited before any code (2026-09-27)

**THE BRIEF** is the plan's Task 6: join-count on the binary failure indicator, rook adjacency in
index space, over the `is_fit_verdict` population (D3), per candidate with an aggregate (D7),
against a permutation null holding the eligible mask fixed (D5), reported as count / null median and
quantiles / z / p. **Four findings, and the first is an enumeration that is one member short of the
population it describes.**

### (c5) THE LAST TEST NAMES FOUR NON-FIT MEMBERS AND `is_fit_verdict` EXCLUDES FIVE

The plan's final test says *"`NOT_APPLICABLE`, `CANDIDATE_DROPPED`, `SCREENED_OUT` and
`NOT_ATTEMPTED` cells are all absent from the graph"*. **§12.5's grouping table names five non-fit
codes, and the fifth is `INSUFFICIENT_DATA`** — confirmed against `Outcome`'s own predicate table,
where it reads `is_fit_verdict: no`.

**AND IT IS THE ONE MOST LIKELY TO BE GOT WRONG, WHICH IS WHY THE OMISSION MATTERS.** It is the
member open question 24 moved: `is_eligible` went False → True on 2026-09-20, and it is now
**eligible, covered, and not a fit verdict** — the only member with that combination. A graph built
on `is_eligible` rather than `is_fit_verdict` admits it, which is precisely the failure the test
exists to catch, and **the test as written would not look for it.** The enumeration is over the
predicate, not a list: every member with `is_fit_verdict: no` is absent, asserted as a set.

### THE ALGORITHM ALREADY EXISTS IN A FROZEN HARNESS, AND A SECOND IMPLEMENTATION IS CORRECT HERE

`docs/superpowers/notes/phase2f-clustering-harness.py` carries `rook_edges`, `join_count` and
`permutation_null` — Task 0's apparatus, and **the apparatus of numbers this project is still
quoting**. (j8)'s third register: rewriting it rewrites closed evidence, so it does not move and
production code is written beside it in `src`.

**THAT IS A SECOND SPELLING OF ONE ALGORITHM, AND THE HANDOFF NAMES THIS AS THE EXCEPTION TO (j9)
RATHER THAN A VIOLATION OF IT**: *"one is the current value, the other is a record of a past value.
Collapsing them destroys the record."* The test of which you are looking at is whether changing the
production code **should** change the harness — it should not.

**SO THE DIVERGENCE IS CLOSED THE WAY PHASE 2d CLOSED IT: BY BINDING THE NEW CODE TO THE COMMITTED
RECORD.** `phase2f-clustering-measured.jsonl` carries **deterministic, RNG-free** quantities —
`unwrapped_edges = 12798` and `unwrapped_observed = 340` at `height = 90` in the P4 seam record — so
the production `rook_edges` and `join_count` reproduce a number **taken from the committed artifact,
not from the harness's source**. A binding that read the harness would be comparing the new
implementation against the old implementation; this compares it against the old implementation's
published output, which is what the record is for.

### `CLUSTERING_SEED` IS A TASK-6 EXIT ITEM AND IT IS MECHANICAL

The do-not-move list is in the plan's **standing requirements** and currently reads
`PUBLISHED_TILE_SIDE`, `resident_bytes_per_series`, `output_slot_bytes`, `SVD_CHUNK_SERIES`,
`HEADROOM_FRACTION`, `ALGORITHM_VERSION`, `FIELD_SEED`, `HESSIAN_COND_LIMIT`, or any `Outcome` code.
**Task 6 is not done until `CLUSTERING_SEED` is on it**, because D5's *"joins that list"* is a
promise with no owner while the constant does not exist.

**AND IT IS A NEW CONSTANT, NOT `SPIKE_SEED`.** The harness's `SPIKE_SEED = 20260919` is a **record
of the draw Task 0 took**; the production seed keys every p the report will publish. Two different
things, and the 2d field-seed instance is the precedent for keeping both: consolidating the current
value into `src` was right, rewriting the harnesses to import it was not.

> **AND THE BUILDER TAKES ITS SEED EXPLICITLY**, per the same handoff paragraph: *"a value that KEYS
> THE DRAW arriving silently at a caller that never named it is the failure the constant exists to
> make visible — a default would automate it."* So the null's entry point requires the seed rather
> than defaulting to the constant, and the report passes it.

### THE FLOOR'S WORDING IS THE FINDING, NOT THE FLOOR

500 is **a ladder rung, not a boundary**: 200 failed and 500 passed, so the true threshold lies in
**(200, 500]** and 500 is *the smallest tested size demonstrated uniform*. **The invariant is stated
that way in the code, or a later reader takes it for a measured threshold with a precision it does
not have** — the same discipline as a constant that names which side of it was measured.

**AND THE UNAVAILABILITY MESSAGE NAMES THE FLOOR AND ITS PROVENANCE**, because an unavailable
quantity that does not say why is the (a2b) defect this sub-phase has refused four times already.

### TASK 6, AS BUILT (2026-09-28) — TWO THINGS THE CODE TURNED UP

**1. THE READER DID NOT EXPOSE A COORDINATE, AND THE TWO-ARM ZONE IS DEFINED IN DEGREES.** D4 fires
both arms when the `x` span is *within a couple of cells of 360°* — a measurement in the grid's own
units — and `StoreView` carried no spatial coordinates at all. They exist in the store (`/status/x`,
`/status/y`, keyed by **this store's own axis names**, with `spatial_coordinates_written` in root
attrs) and nothing in the report had ever needed one, so nothing surfaced one.

**The reader gained the field rather than clustering opening the store itself**, which would have
been a second reader of the same bytes — the defect this sub-phase has now refused under three
different names. It is additive: absent coordinates yield an empty mapping, which is the answer and
not a failure.

> **AND THE AMBIGUITY RULE WAS ALREADY DECIDED, WHICH MADE THE REST MECHANICAL.** D4 says *every
> ambiguous case fails toward not-wrapping* — so an unrecognised axis name, a store with no
> coordinates, or fewer than two values all yield **no span**, and an unknown span is not a global
> grid. The report prints which of those it found instead of asserting a policy.

**2. A TOLERANCE PICKED BY EYE FAILED, AND THE FIX WAS TO DERIVE IT.** The seed-reproducibility test
first asserted that two seeds' `z` agree within **5%**; the measured difference was **5.5%**, and my
reflex was that the bound was nearly right. **It was not derived at all.**

`z = (observed - mean) / sd`, so at large `z` the relative error is dominated by the relative error
in the null's `sd`, whose sampling standard deviation over `P` draws is `1 / sqrt(2(P - 1))`. Two
independent seeds differ by `sqrt(2)` times that: at `P = 999`, one sigma is **3.2%** and three
sigma is **9.5%**. The measured 5.5% is **1.7 sigma — an ordinary draw.**

> **A TOLERANCE THAT CANNOT BE DERIVED IS ONE THAT GETS LOOSENED UNTIL IT PASSES, AND THE LOOSENING
> IS INDISTINGUISHABLE FROM THE DEFECT.** This is the eps-derived-constants rule arriving in a test
> rather than in `src`: count what the quantity is made of and read the exponent off, rather than
> picking a round number and tuning it when it fires. **The failing run is what made it visible** —
> a 5% bound that happened to pass would have shipped as a number nobody could justify.

**AND THE GOLDEN TABLE RECORDS THE FIRST REPORT MODULE THAT IS NOT ZERO.** `clustering.py` has
**three** divisions — the z, the p, and the cell width the span is measured in. **None is a failure
rate**, which is the quantity that table protects, and the row says so: a fourth division appearing
there should be read as one until shown otherwise.

---

## Plan Task 7 — the maps and the no-matplotlib path, audited before any code (2026-09-28)

**THE BRIEF** is the plan's Task 7: one PNG per (branch present × candidate) plus one per branch for
the point-level aggregate, the value at a downsampled block being the **fraction** of that block's
cells carrying the code (D9); `viridis`, fixed code-to-colour, legend from the store's own
`flag_meanings`; matplotlib behind a `[report]` extra, imported inside the function (D10). **Four
findings, and two of them are things that do not exist yet.**

### THE `[report]` EXTRA DOES NOT EXIST, AND THE PACKAGING GUARD MAKES IT MANDATORY RATHER THAN TIDY

`pyproject.toml` declares **`test`** and **`batch`** and no `report`. D10 has assumed it since the
plan was written, and `tests/test_report_reader.py`'s `FORBIDDEN` table already documents matplotlib
as *"lives behind the `[report]` extra"* — **a description of something that is not there.**

**AND `tests/test_packaging.py` TURNS THAT INTO A HARD STOP, WHICH IS THE USEFUL PART.** Its
`_third_party_imports` walks every `.py` under `src/metamer` with `ast.walk` — **so it finds imports
inside FUNCTION BODIES, not only at module scope.** A lazily imported matplotlib is therefore a
declared-dependency question exactly like an eager one, and the guard fails naming the module unless
it is added to `_MODULE_TO_DISTRIBUTION` *and* to `pyproject.toml`: *"a new third-party dependency
must be routed through this test rather than around it."*

> **SO D10's LAZY IMPORT DOES NOT EVADE THE DECLARATION, AND IT WAS NEVER MEANT TO.** Lazy import
> buys *portability at run time* — the numbers path works where matplotlib is absent. Declaration is
> a different claim, about what the distribution asks for, and the extra is what makes both true at
> once. Task 7 adds: the extra, the `_MODULE_TO_DISTRIBUTION` row, and nothing else to the base
> dependency set.

### CORRECTION, FOUND WHILE WRITING THE CODE — THE BRIEF CONTRADICTS ITS OWN DECISION, AND THIS ENTRY COPIED THE STALE HALF

**Task 7's *Behaviour* paragraph says *"`viridis`; fixed code-to-colour; legend from the store's own
`flag_meanings`"*. D9 STRIKES BOTH OF THOSE, BY NAME, AND SAYS WHY:** *"those are properties of the
categorical design this decision refuses. On a binary fraction map in `viridis` a branch has no
colour — it has a map — and `flag_meanings` supplies the **title**, not a legend."* Task 7's own
test list agrees with D9 — its last test reads *"the map's title names the branch from the store's
own `flag_meanings`"*. **So the Behaviour line is the stale one and the decision plus the tests are
the live brief.**

> **AND THIS ENTRY REPEATED THE STALE HALF, WHICH IS THE EXACT FAILURE D9 CLOSES WITH.** The
> paragraph below originally opened *"the plan requires the legend to come from the store's own
> `flag_meanings`"* — the struck requirement, carried forward as though it were live. D9's closing
> sentence is *"rejecting a design and keeping two of its requirements is how a refused design
> survives in its own replacement"*, and a pre-flight written from the Behaviour paragraph instead
> of from the decision is precisely that mechanism. **(f) is the rule — does the brief contradict
> something already settled — and the answer was yes, in the brief's own document.**

**WHAT IS BUILT: no legend, no fixed code-to-colour, and `flag_meanings` supplies the title.** The
reader still needs the legend arrays, because the title needs the meanings — so T7-3 stands
unchanged, and only the consumer of its field moves.

### THE READER DOES NOT EXPOSE `flag_meanings`, AND THIS IS THE SECOND TASK RUNNING TO FIND THAT

**The title** must come from *the store's own `flag_meanings`*. The store writes it —
`store.py:959`, into the `/status/` arrays' attrs, built from the enum — but **it is an ARRAY
attribute, not a root one**, and `StoreView.attrs` carries only root attrs. So it is unreachable
through the reader, exactly as the spatial coordinates were one task ago.

**THAT IS A PATTERN NOW AND IT IS WORTH NAMING BEFORE TASK 8 MEETS IT AGAIN.** The reader was built
at Task 1 against Task 1's needs, which were the arrays and the completion bitmap. **Every task
since that needed a fact about the store has found the reader does not carry it** — Task 6 the `x`
coordinate, Task 7 the flag legend — and each time the right repair was to widen the reader rather
than let the consumer open the store. The alternative compounds: two readers of one store is the
defect this sub-phase has refused under three names, and a third consumer opening zarr directly
would make it four.

> **THE COST IS ONE FIELD PER TASK AND THE ALTERNATIVE IS A SECOND READER PER TASK.** Stated here so
> Task 8's entry point, which needs the whole record, starts from "what does the reader not carry
> yet" rather than discovering it mid-implementation.

### THE MEAN-OF-CODES DEFECT IS REAL, AND THE EXACT MEMBERS MAKE IT WORSE THAN THE PLAN SAYS

Verified against the enum rather than taken on trust: `DEGENERATE_HESSIAN` is **7**,
`ILL_CONDITIONED_X` is **11**, and `mean(7, 11) == 9` — which is **`CANDIDATE_DROPPED`**.

**SO AVERAGING TWO GENUINE FAILURES PRODUCES A DECISION.** Not merely "a different valid-looking
code", as the plan puts it, but a code from the other side of §12.5's grouping table entirely: the
two cells say *this fit failed twice over* and their mean says *the run chose not to fit this
candidate here*. A map rendered that way is not noisy, it is **articulate and wrong** — and on a
downsampled global map it would be wrong across whole regions while every legend entry remained a
real member of the alphabet.

**The reduction is over a BINARY INDICATOR per branch and the test asserts the output is a fraction
in [0, 1]**, which is the mechanical form of "no arithmetic ever reaches a code".

### THE IMPORT PROBE NOW COVERS THE MODULE-SCOPE CASE FOR FREE, AND ONLY THE LAZY ONE IS BLIND

The probe walks `metamer.report` with `pkgutil` and imports **every** module, so `maps.py` is
covered on the day it lands with no edit — the third dividend from making that scope mechanical. A
module-scope `import matplotlib` there would put matplotlib in `sys.modules` and fail the forbidden
check immediately.

**WHAT STAYS BLIND IS THE LAZY IMPORT, WHICH IS EXACTLY WHAT D10 REQUIRES** — a `sys.modules` check
cannot see an import that has not happened. **So the instrument and the design are aligned rather
than in tension**: the probe enforces the half that must not happen (module scope) and is silent
about the half that must (inside the function). The half it is silent about is covered by a
different test — the no-matplotlib path, which makes the module unimportable and asserts the report
still exits 0 with every number present.

> **AND THE WALK ITSELF BECOMES A SECOND ASSERTION ONCE `maps.py` EXISTS.** In an environment
> without matplotlib the walk must still import `maps.py` successfully. That is the lazy import's
> own requirement, checked by the instrument that was built for something else — (j3): an existing
> feature is an instrument for a property its own purpose does not concern.

### THE CLOSING SECTION — RULINGS RECEIVED 2026-10-02, VERBATIM

**T7-1. A BLOCK'S FRACTION IS DIVIDED BY THE FIT-VERDICT CELLS IN THAT BLOCK, NOT BY ALL ITS
CELLS.** This is the denominator defect in map form, and nobody has named it yet. D9's rule says the
map and the statistic always cover the same population, and D3 sets that population to
`is_fit_verdict`. If a block's fraction is divided by all its cells, a coastal block that is half
land shows half its real failure fraction. That's D2b's dilution again, drawn as a map.

- A block with zero fit-verdict cells is MASKED and drawn in a distinct "no data" colour. It is
  never drawn as 0, because 0 is the bottom of viridis and reads as "no failures." This is the
  `fitted == 0` rule applied to maps.
- Every map states its population in its title or caption.
- Non-fit branches, if they are mapped at all, are COVERAGE maps over covered cells, and are
  labelled as coverage maps, not failure maps.

Tests:

- A block half-filled with `INSUFFICIENT_DATA` shows the fit-verdict fraction, not a diluted one.
- A block with no fit-verdict cells renders as masked.
- With vmin 0 and vmax 1 fixed, a masked block and a block with 0% failures come out different
  colours.

**T7-2. BOTH ENVIRONMENTS IN CI, ONE IN EACH JOB.** CI currently has no matplotlib. That's why
`test_readme_figure` failed in CI on its first push. So in CI today the maps path either skips or is
never exercised. Have one CI job install `[report]`, so maps are drawn and checked, and leave the
others without it, so the no-matplotlib path and its "maps not drawn" sentence are checked. Then CI
covers both by construction. If you won't do this, the maps tests must not skip silently. The skip
gets counted and named in the run's output, the same way INDETERMINATE is.

**T7-3. WIDEN THE READER ONCE, AND STOP THE PATTERN.** Add the legend (`flag_values` and
`flag_meanings`) to `StoreView` as a typed field. Then fix why this keeps happening, before Task 8
runs into it a third time. Add a coverage table comparing what the writer writes with what the
reader exposes:

- every attribute and array the store writes, listed against what `StoreView` carries;
- deliberate exclusions pinned, each with its reason;
- the test fails when the writer gains a field and nobody decides whether the reader should expose
  it.

This is F3's rule (assert what the enumeration found) applied to the reader.

---

### THE DERIVATION CHECK ORDERED WITH THE RULINGS — THE COMMITTED NUMBERS ARE RIGHT, THE CONVERSATIONAL ACCOUNT WAS NOT

**Checked rather than taken either way, because the ruling's premise was that the shipped docstring
might carry the bad numbers. IT DOES NOT.** `tests/test_report_clustering.py:240` reads
*"`1 / sqrt(2 (P - 1))`. Two independent seeds differ by `sqrt(2)` times that, so at `P = 999` one
standard deviation of `|dz| / |z|` is `sqrt(2 / 1996) = 3.2%`"* — and `sqrt(2/1996)` **is** the
two-seed form, written as an expression rather than as a figure, so the √2 is applied exactly once
and in the right place. Recomputed: per seed **2.238%**, two-seed **3.165%**, 3σ **9.496%**, and the
measured 5.5% is **1.74σ**. The assertion is `bound == approx(0.0950)` and it is correct.

**SO THE ERROR WAS CONFINED TO THE PREVIOUS SESSION'S PROSE — *"3.2% per seed, 4.5% for two"* — AND
PROSE IS WHERE IT DOES THE DAMAGE.** Both figures are √2 too large, and the ruling's test for that
is the one that matters: they contradict the same account's own conclusions, since 3 × 4.5% = 13.5%
rather than 9.5%, and 5.5 / 4.5 = 1.22σ rather than 1.7σ. **A derivation wrong in the middle and
right at the end is more dangerous than one wrong throughout**, because the end agrees with the code
and invites a reader to repair the code to match the middle.

> **THE REPAIR IS THEREFORE TO STATE THE PER-SEED FIGURE, WHICH NEITHER THE DOCSTRING NOR THIS NOTE
> EVER DID.** 2.238% appears nowhere; only `sqrt(2/1996)` does. A number that exists only inside an
> expression is a number the next reader re-derives, and re-derivation is where the √2 went missing.

**AND THE NORMAL ASSUMPTION IS NOW MEASURED RATHER THAN ASSERTED.** `1 / sqrt(2(P - 1))` holds for a
normal null; a skewed, sparse-failure null has a standard error larger by `sqrt((κ - 1) / 2)`. The
ruling asked for the fixture's regime to be stated, so it was measured on the fixture itself — the
20×20 patch in a 40×40 all-true mask, P = 999:

| quantity | measured | normal reference |
|---|---|---|
| background rate | **0.25** | — (this is why: dense, not sparse) |
| null mean / sd | 194.60 / 10.334 | — |
| skewness | **+0.0135** | 0 |
| kurtosis κ | **2.8932** | 3 |
| inflation `sqrt((κ-1)/2)` | **0.9729** | 1 |
| 3σ two-seed bound | **9.24%** | 9.50% |

**THE FIXTURE IS VERY SLIGHTLY PLATYKURTIC, SO THE SHIPPED BOUND IS CONSERVATIVE BY 1.028× — THE
SAFE DIRECTION, AND BY A MARGIN THAT IS ITSELF WITHIN SAMPLING ERROR OF κ.** The regime satisfies the
assumption because the background rate is 0.25: the sparse-failure case the inflation factor warns
about is the one a real store will present, and **this fixture is not it.** That is the limit worth
writing down — the bound is derived for *this* fixture's regime, and a map-scale store with a 0.5%
failure rate would need the inflation factor computed rather than dismissed.

> **OWED, WITH ITS TRIGGER NAMED SO IT DOES NOT LIVE ONLY HERE: Task 7's code commit carries the
> docstring amendment** — the per-seed 2.238%, the normal assumption, the measured κ, and the
> sparse-regime limit. It is a `tests/` byte change and therefore needs the sweep, which is why it
> does not ride in this docs-only commit. **The ruling that forbids deliberate state living in a
> session's context applies to this paragraph too.**

---

### THE MATERN32 ENGINE QUESTION — NOT IN TASK 5's PRE-FLIGHT, SO IT WAS ESTABLISHED BY RUNNING IT (2026-10-02)

**THE RULING ASKED FOR IT "FROM TASK 5's PRE-FLIGHT" AND IT IS NOT THERE.** Task 5's entry is four
findings about `fits`, the nesting, the float32 delta-IC and `selected`'s three states; it never
mentions an engine. The `matern32`-withholds-`celerite2` fixture belongs to **Task 4's** entry, where
it exists to make the engine-cost column discriminate. So the question was answered against the live
objects instead.

**THE ANSWER: `kalman`, WHICH `matern32` DECLARES — SO THE HYPOTHESISED DEFECT IS NOT PRESENT.**

| checked | found |
|---|---|
| what `fit()` binds when nothing is injected | `fit.py:385` — `engine = KalmanEngine() if engine is None else engine` |
| that engine's id | `KalmanEngine().engine_id == "kalman"` |
| what `matern32` declares | `matern32.py:184` — `KALMAN: LINEAR`, `WHITTLE: NLOGN`, `TOEPLITZ: CUBIC` |
| what it withholds | `CELERITE2` only, and **deliberately**: `matern32.py:159` says `engine_costs` names engines that evaluate the kernel *without altering it* |
| whether the withheld engine could run at all | `EngineId` has four members and **`capability.py:10` says only KALMAN is implemented in Phase 1** |

**SO THE CANDIDATE RAN ON AN ENGINE ITS TERM DECLARES, AND THE WITHHELD ONE HAS NO IMPLEMENTATION TO
RUN ON.** The `white + matern32` composite surviving on three engines rather than four is a statement
about the intersection, not about anything the run did.

#### BUT THE PROBE FOUND AN ADJACENT DEFECT THAT IS REAL, AND IT IS FILED RATHER THAN FIXED HERE

**`engine` IS AN UNVALIDATED `str` IN THE CONFIG, TWO LINES BELOW AN `objective` THAT IS A `Literal`.**
`config/model.py:301-302`:

    objective: Literal["ml", "reml"] = "ml"
    engine: str = "kalman"

Measured, on a config otherwise valid — every one of these is **accepted**:

    engine='kalman'        ACCEPTED -> stored as 'kalman'
    engine='celerite2'     ACCEPTED -> stored as 'celerite2'
    engine='whittle'       ACCEPTED -> stored as 'whittle'
    engine='toeplitz'      ACCEPTED -> stored as 'toeplitz'
    engine='not_an_engine' ACCEPTED -> stored as 'not_an_engine'
    engine='KALMAN'        ACCEPTED -> stored as 'KALMAN'

**AND THE ACCEPTED STRING IS LOAD-BEARING IN THREE PLACES.** It is written to root attrs
(`store.py:490`, `"engine": config.engine`); it is a **REQUIRED_ATTR** (`store.py:223`), so a store
cannot exist without it; and it **reaches `fit_hash`** — measured, `fit_hash` differs between
`engine="kalman"` and `engine="celerite2"` on an otherwise identical config. Meanwhile every fit runs
on `KalmanEngine`, and `fit.py:579`/`606` record `engine.engine_id` — the engine **actually used**.

> **SO A STORE CAN CONTRADICT ITSELF, AND NOTHING TODAY NOTICES.** Root attrs would say `celerite2`
> while the per-fit record says `kalman`. That is D1's tell once more — a name saying one thing while
> the value is another — in the one field Task 4 went to trouble to keep honest *per candidate*,
> left unguarded *per run*.

**THE SHARP EDGE IS FORWARD, NOT TODAY, WHICH IS WHY IT IS FILED AND NOT FIXED MID-TASK.** Because
`engine` reaches `fit_hash`, a store written under `engine: "celerite2"` carries kalman fits under a
celerite2 fit-hash. **When Phase 3 lands a real second engine, that stale store's `fit_hash` will
match a genuine celerite2 run's and be reused** — kalman numbers served as celerite2 numbers, past a
gate whose whole job is to refuse exactly that. `reuse.py:150` then manufactures
`engines=(EngineId(engine),) * models` from the run-level string, so the reused block asserts the
engine rather than reading it.

**Today nothing is wrong** — the default is `kalman`, `EngineId("not_an_engine")` would raise on the
reuse path, and no second engine exists. **The trigger is the second engine**, which is the same
trigger the engine-narrowing test is already filed at, beside P4″. **Filed as OQ26**, with this
paragraph as its evidence; the repair is one line (`Literal` or an `EngineId` coercion at the config
boundary) and the reason it is not taken here is that a config-validation change belongs to a task
that sweeps config, not to the maps task.

---

## TASK 7, AS BUILT (2026-10-03) — FIVE THINGS THE RULINGS DID NOT COVER

**T7-1, T7-2 and T7-3 are implemented as written.** What follows is only what the code turned up
beyond them, per the instruction to add to the pre-flight for nothing else.

### 1. TWO MEMBERS ARE IN NEITHER POPULATION, AND MAPPING THEM OVER COVERED CELLS IS A SECOND FORM OF THE SAME DEFECT

T7-1 gives two populations — fit-verdict cells for failure maps, covered cells for coverage maps.
**Checked against the enum rather than assumed, and `NOT_ATTEMPTED` (8) and `NOT_APPLICABLE` (13) are
neither `is_fit_verdict` nor `is_covered`.** The first draft of `plan_maps` sent every non-fit branch
down the coverage path, which for those two computes `0 / covered` in **every block** — an all-zero
map of a branch that is **present**, rendering under fixed limits as uniform dark purple and reading
as *this never happens*.

> **AND THE BRANCH IT HAPPENS TO IS THE ONE AN INTERRUPTED STORE IS FULL OF.** `NOT_ATTEMPTED` is
> what a killed run leaves behind, so the map that would have lied is exactly the map somebody reads
> to find out how far a run got. **This is the mean-of-codes defect's shape reached through the
> denominator instead of the numerator** — not a wrong picture, a plausible one — which is why the
> repair is to refuse the map and **name the branch in `unmapped` with its reason**, rather than to
> pick a third denominator. Dropping it silently is the same error one step quieter.

### 2. THE PLAN CONTRADICTS ITS OWN DECISION, AND THIS PRE-FLIGHT HAD COPIED THE STALE HALF

Recorded in full at the correction above. Task 7's **Behaviour** paragraph still says *"fixed
code-to-colour; legend from the store's own `flag_meanings`"*; **D9 strikes both by name** and says
`flag_meanings` supplies the **title**. Task 7's own test list agrees with D9. **The decision and the
tests are the live brief; the Behaviour line is stale** — and the entry written before the code had
carried the stale line forward, which is (f) answered yes inside a single document.

### 3. THE READER's LEGEND IS READ THROUGH CONSOLIDATED METADATA, WHICH A TEST FOUND BY FAILING

The mismatched-pair test mutated `/status/outcome`'s attrs through `zarr.open_group(mode="r+")` and
then **read the original legend back**. The store carries **consolidated metadata** and the reader
opens the group plainly, so the root's consolidated copy of the array attrs is what it sees; an edit
to the array alone leaves the stale pair in place. The test re-consolidates, and the finding is
recorded at the test.

> **THE PROPERTY THIS IMPLIES IS NOT TESTED AND IS NAMED HERE RATHER THAN LEFT IMPLICIT:** a store
> whose consolidated metadata disagrees with its arrays will have the report describe the
> **consolidated** copy. That is one more instance of *a store is described, not repaired* (D6), and
> nothing in the suite asserts the two agree. **Filed for Task 8's `_disagreements`**, which already
> exists to report contradictions between two records in one store and is the right owner.

### 4. A `pyyaml` IMPORT IN A TEST WAS THE `test_readme_figure` TRAP, THIRD INSTANCE

T7-2's matrix is held in place by a test that **reads the workflow**, which needs `yaml`. `pyyaml`
6.0.3 is in the pixi environment as a transitive dependency of `pre-commit` and is a dependency of
**nothing in the `[test]` extra** — measured with `importlib.metadata`, and `pytest` does not require
it. **So the test passed locally and would have died in CI on `ModuleNotFoundError: No module named
'yaml'`**, which is the failure this project has already had twice: `build`/`hatchling`, and
`test_readme_figure`'s matplotlib. Declared in `[test]` with that reasoning at the entry.

### 5. A GITHUB ACTIONS `include` WHOSE KEYS ARE ALL NEW COLLAPSES THE MATRIX, AND IT ALMOST SHIPPED

The first version of T7-2's matrix moved `python-version` **out** of the base matrix and listed it
only under `include`, one entry per version with its extras. **That does not produce three jobs.** An
`include` entry whose keys are all new is merged into *every* existing combination, so with a base of
`{os: [ubuntu-latest]}` the three entries compete to set one key on one job — **and the two-environment
coverage T7-2 exists to create would have silently become one environment.** The version is back in
the base matrix so each `include` entry *matches* an existing combination and attaches `extras` to it.

> **THE TEST ASSERTS THE EXPANDED JOB COUNT, NOT THE `include` COUNT**, which is the only form that
> tells the two apart: three include entries are present in both the working and the broken version.
> **A silent skip in every job is indistinguishable from a pass**, which is T7-2's own argument, and
> this is that argument one level down in the configuration that implements it.

### AND THE SKIP CHANNEL IS BUILT EVEN THOUGH THE CI JOB MAKES IT OPTIONAL

T7-2 offered the skip-counting as the alternative to the second environment. **Both are built**,
because the `skipif` marks stay in the source: a matrix that stopped installing the extra — a rename,
a dropped row, a typo — would skip every drawing test and stay green. So every run now prints
`maps environment: matplotlib PRESENT|ABSENT` **on both branches**, beside the RSS section, under
handoff §2's rule that a measurement surfacing only on failure is not a record.

### 6. THE SWEEP FAILED AGAIN IN A FILE THE TASK NEVER OPENED, AND THE GOLDEN TABLE FOUND TWO BLIND SPOTS IN ITSELF

**`pixi run test`: 1 failed, 1592 passed, 1:41:30** — and the one failure was
`test_the_rate_site_table_is_pinned_over_every_outcome_referencing_module`, in `tests/test_outcomes.py`,
which Task 7 never touched. **That is the golden table working exactly as designed**: `maps.py`
references `Outcome`, so it enters the scope mechanically and its division count must be pinned
deliberately. **Fourth consecutive task whose first full sweep failed in a file it did not open**, and
(k) again.

**BUT THE COUNT IS 4 AND THE MODULE's ONLY REAL DIVISION IS NOT AMONG THEM.** Enumerated with `ast`
rather than read off the diff:

| line | node | what it actually is |
|---|---|---|
| 106 | `FloorDiv` | `-(-length // MAX_BLOCKS)` — ceil division, a downsampled shape |
| 150 | `FloorDiv` | `-(-rows // side[0])` — same |
| 150 | `FloorDiv` | `-(-columns // side[1])` — same |
| 441 | `Div` | **`out_dir / f"{stem}.png"` — `pathlib.Path.__truediv__`, a path join, not arithmetic** |

**AND THE BLOCK FRACTION — the one quantity in this module a reader would want that table to see — IS
INVISIBLE TO IT.** It is written `np.divide(counts, totals, out=..., where=...)`, an `ast.Call` and not
an `ast.BinOp`, so the walker never counts it. **The pinned count would be identical if that line were
deleted.**

> **SO THE INSTRUMENT HAS A FALSE POSITIVE AND A FALSE NEGATIVE IN ONE MODULE, AND THEY NEARLY
> CANCEL.** A reader told *"4 divisions in `maps.py`"* would reasonably conclude four arithmetic
> divisions exist; three are shape arithmetic, one is a filesystem path, and the real division is
> unseen. **The number is still worth pinning** — the table's discipline is *don't count what you
> can't classify; pin what you can observe*, and it does catch the module entering scope, which is
> what made this failure useful. **What was missing is the statement of what the number is made of**,
> which the row now carries.

**THE THIRD NAMED GAP IN THAT TABLE'S SCOPE**, beside *"the suite does not enforce that a new harness
calls `failure_tally`"* and *"a rate over raw integer codes never referencing `Outcome`"*: **a division
expressed as a function call** — every `np.divide`, `np.true_divide` and `operator.truediv` — is
outside the table's reach. Named rather than repaired: widening the walker to count calls would require
deciding which calls are divisions, which is the classification the table exists to avoid, and an
unnamed gap is indistinguishable from an absent one.

**The sweep's other readings:** 6 RSS measurements, **0 INDETERMINATE**, 4 above the 25 ms/s stall
diagnostic (which skips nothing — open question 19); the report module graph at **941 of a 980
ceiling**, headroom 39, with `maps.py` present and no `matplotlib` in it, which is D10's lazy import
measured rather than asserted; and the new channel printing `maps environment: matplotlib PRESENT`.
