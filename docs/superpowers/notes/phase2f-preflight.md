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
