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
