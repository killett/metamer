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

### THE ENUMERATION, WITH ITS COUNT — FIVE SITES

| # | site | kind | disposition |
|---|---|---|---|
| 1 | `progress.py` `LiveCounters.lines` | **display** | **WRONG — fixed in this commit**, becomes the shared function's first consumer |
| 2 | `abort.py` `_rate_for` / `_decide` | **decision** | correct since 2026-09-20; moves onto the shared function, and its stale docstring is fixed |
| 3 | `audit_report.py` rescue / loss / `both_ok_fraction` | measurement | **filed as open question 25**, not touched — its denominators are `cold_failed` / `cold_ok` / `attempted`, a different question |
| 4 | committed harnesses under `notes/` — **15 rate-shaped divisions** | measurement of committed artifacts | **FILED, NOT TOUCHED.** They use denominators like `outcome != 8` and `iterations != ITERATIONS_UNSET` that describe the artifacts they produced; rewriting them rewrites closed evidence — the same reason 2e's `_histograms` is frozen |
| 5 | `metamer.report` | display | **does not exist yet**; Task 2 makes it the shared function's second consumer |

**Two are display or decision sites and both are addressed here. Three are measurement sites and all
three are filed.** The count is five and is asserted in a test, per (c7).

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
