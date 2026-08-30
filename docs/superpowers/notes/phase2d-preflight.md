# Phase 2d pre-flight, per task

**The method lives in exactly one place** — [`phase1-to-phase2-handoff.md`](phase1-to-phase2-handoff.md)
§1 — and is not restated here. **Append each task's entry BEFORE the task, not after.** 2c's Task 0
entry changed the measurement three times before any code was written; that is what the ordering
buys.

---

## Pre-plan — the brainstorm's own audit, run against 2d's inherited brief (2026-08-30)

**THE BRIEF** was the cold-start handoff: 2c is closed, the hysteresis audit exists and has
measured nothing, and 2d owns the coherent field that would make its numbers mean something.
Four findings changed the plan before a task was written.

### (a5) ACROSS DOCUMENTS — THE TWO-FIELD SPEC IS §16.2 ITEM 6 AND THREE SITES SAID OTHERWISE

The brief cited **§11.2** for *"two fields — smoothly varying parameters, and a sharp boundary"*
and for the boundary-smearing width. **§11.2 specifies none of them.** It is the audit itself: the
four disagreement metrics, the stratified subsample, the 30% threshold, the label-switching
confound and the fit-relevant split. **The two fields, the sharp boundary, the smear width and the
README figure are all §16.2 item 6.**

**Three sites carried the claim and they failed differently:**

| site | what it said | verdict |
|---|---|---|
| D4's constraint 3 | *"§11.2's simulated benchmark, smoothly varying with a sharp boundary"* | **wrong section** |
| Q11's 2d row | *"hysteresis audit, simulated fields, boundary-smearing width"* | **no section at all** |
| design doc §16.2 item 6 | the spec itself | correct |

**What it changed.** Both wrong sites are amended in PROGRESS.md rather than only noted. **And the
silent site is the more instructive one:** a deliverable named with no section is how the wrong
section gets supplied by the next reader — which is exactly the route the brief took. **The rule
this pays out on: a deliverable named without its source is an unowned citation, and the next
reader will own it.**

**AND THE CORRECT SECTION CHANGED THE PLAN RATHER THAN ONLY THE FOOTNOTE.** §16.2 is *"slow,
stochastic, tolerance-banded… run on demand; in CI only at small N. Emits a reproducible report."*
That settles, from the design doc rather than by argument, that 2d's measurements are **a benchmark
and not a test**, which is what criterion 12's 1.7–6.7 hours against a 39-minute suite had already
been saying without a home. **It also decided Task 9's shape**: the exit-criteria suite asserts
against committed reports, because a 27-hour measurement cannot be a test and its recorded output
can.

### (a5b) TWO CONSTRAINTS ON THE AUDIT'S SUBSAMPLE, EACH SATISFIED IN ITS OWN PARAGRAPH — SELF-CAUGHT

**Promoted to the handoff as (a5b).** The audit's subsample size was bound by the compute ceiling
(30 h → a quarter-audit, 96 of 384 points) and by D8/D10's 30-member floor (≥ 180 points, and
realistically 300+). **The recommendation took the first and never returned to the second**, in a
message whose own occupancy table put the point strata at `3 margin × M = 6` at `M = 2` — so 96
points is **16 per stratum at uniform occupancy and every one withheld.** **That is 2c's outcome
reached by choice rather than by consequence**, and 2c's was the milder failure of the two.

**What it changed.** The audit is not a fraction of anything. **The four arms were being multiplied
by the sweep for no reason**: the smear width consumes full-field **maps** at every rung and the
audit consumes **arms** at one rung. Separated, the audit affords **every point** at the rung that
needs it, which is the only rule that cannot later be tuned against the occupancy result. **Two
constraints that look like a trade-off often share a term that belongs to only one of them.**

### (a4) THE THREE LATTICE FIGURES RECOMPUTED, AND THEY ARE TWO-ARM FIGURES

`144 × 21 × 2 = 1.68 h`, `256 × 21 × 2 = 2.99 h`, `576 × 21 × 2 = 6.72 h`. **All three check out
and all three are cold-plus-warm** — the two arms criterion 12 needs. **The 2c close quotes them
without saying so**, and the four-arm audit doubles every one. Corrected at its source.

**Two more things the same recompute surfaced.** The `21 s` rate was measured over
`["white", "white + matern12"]` — **`M = 2`** — and the close states the rate without the candidate
set, **although `M` sets both the price and the stratum count**. And the close's *"the whole suite
is 39 minutes"* is **one sample quoted as a constant** beside item 5's dated measurement, which
carries its range (2840.69 s, sweeps 1698–2841 s). **One copy deleted, and the survivor is the one
carrying its range.**

### (i2) THE FIRST QUESTION IS DETECTABLE VERSUS REALISTIC, AND IT IS (i2) AT SUB-PHASE SCALE

**An audit that has only ever run on a field built to make it fire has not been shown to measure
anything about fields that were not.** The two purposes pull in opposite directions and conflating
them would make every 2d number ambiguous between *"the instrument works"* and *"the artifact is
present"*.

**What it changed.** E1: two fields with different jobs, neither permitted to do the other's,
enforced by every number carrying its rung. E4 then made the pairing exact rather than
interpolated by putting the literature values **on** the sweep — **(a4)'s register, that a point
between two measured points is not measured**, applied to a resolution floor.

### (a2b) AND (i9) AT THE INSTRUMENT — THE SMEAR WIDTH HAS A FLOOR AND A CEILING AND BOTH ARE PHYSICAL

On a grid the finest resolvable width is **one fine cell**, so a width at the floor means
*unresolved*, not *zero*, and is emitted as `≤ 1 cell` rather than as a number. **And there is a
ceiling nobody had named:** no point can be biased by a source the spiral never reached, so a width
above `spiral_bound × coarse_stride` — **32 fine cells at the shipped defaults, verified
2026-08-30** — is **refused as a reading** rather than reported. **Both bounds are read from config
and neither is a literal**, or a config change moves the physics and not the check.

### (i2) THE FREE NEGATIVE CONTROL, AND WHY IT GATES THE SUB-PHASE

The same profile estimator run on **an interior line where the truth has no transition** must
return the floor. **It costs no compute — the same fits, a different line — it would contaminate
every smear number on every rung, and it is the clause most expected to fire.** So it is computed
first, as soon as the easy rung lands, and a width there **stops the sub-phase** rather than being
noted. **Its own positive control is in Task 2**: a map whose smooth variation is steepest at the
null line must make it fire, or the gate is unfalsifiable and licenses everything downstream.

### THE PREMISE THE BUDGET RESTS ON THAT NOBODY HAD MEASURED

**N1 was described as the cheap companion.** It is cheap in interpretation and **should be full
price in compute**: `N1_EPSILON = fd_step(1.0) = 6.055e-06` was chosen precisely because it is a
displacement **the optimizer cannot distinguish from zero**, so N1 starts where cold starts and
converges in cold's iteration count. **It is a prediction, it is not in the 27.0 h budget's 12.048
factor, and Task 0 measures it on one small batch before the budget is committed.** The saving is
real but comes from running N1 at **fewer rungs**, not from N1 being individually cheap.

**And the `21 s` itself is dated 2026-08-29 and is a claim to re-measure**, which is the other half
of Task 0. A cost 2× the assumed one re-plans the sub-phase rather than delaying it, which is why
Task 0 gates Task 1.

---

## Plan Task 0 — the pricing and lever spike, audited before any code (2026-08-30)

**THE BRIEF** is the plan's Task 0: three readings — the per-point-per-arm cost, N1's cost against
cold's, and whether `ℓ` moves the saving — with predictions committed first, a ceiling arm, and
the host quiet check. **Four findings, and the first one moves a reading out of the task.**

### (a2c) THE THIRD READING NEEDS TASK 1's BUILDER, AND MEASURING IT HERE REBUILDS 2c's OWN DEFECT

*"Does `ℓ` move the saving?"* needs a field with a coherence parameter. **Task 1 owns the builder
and Task 0 runs before it**, so Task 0 would have to build the field **in the harness** — which is
**exactly the fault that made 2c's criterion 12 unmeasurable.** The warm-start spike's coherent
field lived in a script that is not in the tree, so nothing it established transferred to the
shipped path, and the whole of 2d's compute budget exists to repair that.

**Worse, the verification would be duplicated and the two copies could disagree.** Task 1 ships a
builder; a harness-side `ℓ` check says nothing about it. **Task 1 would have to re-verify the same
property on the real builder**, and *"it worked in the spike"* is precisely the sentence 2c's
close spent a paragraph refusing.

> **THE READING MOVES TO TASK 1 AND THE GATE SURVIVES.** Task 0's remaining two readings **need no
> field at all** — any batch at `N = 630` prices them — so they still gate Task 1 on cost, which
> is the gate's whole purpose. **The `ℓ`-versus-saving sign check becomes a Task 1 test on the
> shipped builder**, at short `N`, asserting a **sign** and never a magnitude. Task 1 already
> carries the truth-side check that `ℓ` is recoverable from the generated parameters; **these are
> two different claims** — that the builder controls the field, and that the field moves the
> optimizer — and conflating them is how a lever becomes a label.

**AND THE RISK THIS DEFERS IS ONE TASK, NOT THE SUB-PHASE.** Discovering at Task 1 that `ℓ` does
not move the saving costs Task 1; discovering it in a harness would cost Task 1 anyway, and buy a
number nobody could quote.

### (i2) READING 2 IS A NULL, AND ITS CEILING ARM IS NOW LOAD-BEARING FOR A DIFFERENT REASON

**The prediction is that N1 costs the SAME as cold.** That is an assertion of no difference, and
*"N1 costs what cold costs"* is byte-identical in the output to **"the iteration counter is not
moving"**, to **"both arms silently ran cold"**, and to **"the perturbation never reached the
optimizer"**. The plan attached the `self` ceiling arm to the third reading; **the third reading
has left and the ceiling arm must stay**, now as **reading 2's positive control**.

`self` — each cell started from its own converged `θ̂` — collapsed iterations by **93.97–94.53%**
across three record lengths in 2c. **If `self` does not collapse here, no cost number in this
spike may be quoted**, because the instrument cannot distinguish two arms by cost at all. **(i2b):
the ceiling arm is the cheapest arm in the design, because its input is the cold arm's own
output.**

### (j2) THE BUDGET'S UNIT IS MEASURED ON `fit` AND SPENT ON `run`, AND NOTHING HAS CHECKED THE GAP

**The `21 s` was measured through `core.fit` on one batch.** E2's 12.048 factor counts **three
full-field `run` passes, a two-pass `run_two_pass`, and one `run_arms`.** Only the last is
`fit`-shaped. **`run` adds tiling, store writes, assembly and the per-tile barrier**, and *"the
overhead is probably negligible at 21 s a point"* is exactly the sentence a pre-flight exists to
delete. **A measurement validates the code path the instrument exercises, not the one the formula
describes.**

**IT IS BOUNDED RATHER THAN MEASURED, WHICH IS CHEAPER AND SUFFICIENT — (j6).** The overhead is
**per point and per tile**, not per iteration, so it is a **larger** fraction of a **cheaper** fit.
**Measuring the `run`-to-`fit` per-point ratio at short `N` therefore bounds it from above at
`N = 630`**, at a fraction of the cost. **The memory budget is set low enough to force more than
one tile**, or the reading covers store I/O and misses the barrier entirely — which would be a
complete-looking table with a row missing.

**If the bound comes back above ~1.15, the 27.0 h figure is not an upper bound and E2 is
re-costed** before Task 1 rather than discovered at Task 5.

### (i10) AND (a9) — THE INHERITED COST HAS NO SPREAD, SO THE REFUTATION CLAUSES HAVE NO SCALE

The plan's clauses are *"above ~26 s"* and *"below ~16 s"*. **The inherited figure is two single
runs — 23.1 s at `B = 8` and 21.0 s at `B = 16` — with no repeat and therefore no spread**, so
both thresholds are guesses against an unmeasured quantity, and a reading between them would be
called agreement on no evidence. **2c's own protocol used three independent repeats per cell.**

**So reading 1 takes repeats and the clauses are restated against the measured spread**, not
against round numbers. **A band narrower than the machine's own jitter cannot express its
condition** — (i9), and this project has paid for it once already.

### (a4) THE BUDGET ARITHMETIC, RECOMPUTED BEFORE IT IS DEFENDED

`2.015625 = 1 + 1/64 + 1` for cold plus two-pass; `3 × 2.015625 + 2 × 1 + 1 × 4 = 12.046875`,
which the plan rounds to **12.048**. `21 × 384 × 12.046875 = 97 146 s = 26.99 h`. **The figure
stands and the rounding is upward, which is the safe direction for an upper bound.** Recorded
because the plan quotes `12.048` and the exact value is `12.046875`; **the discrepancy is 9
seconds and it is stated rather than left for someone to rediscover as a discrepancy.**

### WHAT THIS TASK MEASURES, AFTER THE AUDIT

| # | reading | why it is here |
|---|---|---|
| **1** | per-point-per-arm cost through `fit`, at `M = 2`, `N = 630`, **with repeats** | the 27.0 h budget's unit, dated 2026-08-29 and a claim to re-measure |
| **2** | **N1's cost against cold's**, with **`self` as the positive control** | N1 is not in the 12.048 factor; if it costs a full arm it needs a rung allocation |
| **3** | the **`run`-to-`fit` per-point ratio at short `N`**, forced to ≥ 2 tiles | **bounds** the gap between the unit measured and the unit spent — (j6) |

**Moved out:** the `ℓ`-versus-saving sign check, to Task 1, on the shipped builder.

**Not measured and stated so:** the WARM and N2 arms' costs. Reading 2 hands `run_arms` a
**fabricated** warm array, because N1's start depends on the cold start and the epsilon alone and
not on the warm array's contents — so the two arms that *do* depend on it produce numbers about a
source map that does not exist. **They are not quoted, and the harness records why** rather than
emitting them for a reader to find.
