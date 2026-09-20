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

### WHAT THIS ENTRY CHANGED

- Open question 24 became **three commits, gate → flip → record**, from the two the brief assumed.
- `Outcome.is_fit_verdict` exists, which the brief did not call for and which D3 then reused as the
  clustering graph's population — so the unfinished-store case needs no special handling.
- `fitted` entered the persisted `early_abort.rates[]`: the verdict is decided on a quantity that
  was absent from its own record, and "no candidate had a fit verdict anywhere" is not recoverable
  from `eligible` and `rate`.
- 2e's criterion 9 gained a correction, and the handoff gained the rule that permits it.
