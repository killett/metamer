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
