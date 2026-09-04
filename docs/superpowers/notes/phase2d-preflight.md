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

---

## Plan Task 1 — the field builder and its sources, audited before any code (2026-08-30)

**THE BRIEF** is the plan's Task 1 plus the five points carried into it at review: the plausibility
values sourced and cited **before any run** and doubling as the middle rung; `w = 0` recorded as
the design; the `32 × 12` **derivation** rather than the numbers; criterion 17's iteration count;
and the axis built by `to_decimal_years`. **Five findings, and the first one narrows a claim E1
makes.**

### (a2) AND THE STANDING LIMITATION — `ℓ` CANNOT BE SOURCED, AND IT IS THE LEVER THAT MATTERS MOST

**E1's constraint 1 says the plausibility field's parameters are sourced and cited before any run.
Checked against what a source can actually supply, it is only PARTLY satisfiable, and the
unsatisfiable part is `ℓ`.**

| the rung's parameter | can it be sourced? |
|---|---|
| **`σ_white`, and its geographic contrast** | **partly.** A published, geographically varying gridded noise field exists — Copernicus `SEALEVEL_GLO_PHY_NOISE_L4_STATIC_008_033` — and the along-track 1 Hz measurement-error literature gives levels. **But its VALUES need the product downloaded**, which is real data and outside 2d entirely |
| **Matérn `ρ` of the residual correlated noise** | **weakly.** SSH wavenumber-spectrum results constrain the *data*; nothing publishes the fitted **noise-model** timescale per point |
| **`ℓ`, the spatial coherence of the FITTED OPTIMA** | **NO. By the standing limitation, this exact quantity has never been measured** |

**AND THE OBVIOUS PROXY IS ALREADY REFUTED IN THIS PROJECT'S OWN RECORD.** SSH is spatially
coherent at the mesoscale and DUACS' own covariance model uses prescribed, geographically varying
decorrelation scales — so "use the data's coherence for `ℓ`" is the natural move. **(i2b)'s worked
case says exactly why it fails:** the ceiling arm's whole finding was *"the optimum is far less
spatially coherent than the data is."* **A data-coherence proxy for `ℓ` is not unsupported, it is
contradicted by the measurement 2c already took.**

> **SO THE PLAUSIBILITY RUNG IS PLAUSIBLE IN `Δ` AND IN PARAMETER MAGNITUDES, AND ITS `ℓ` IS
> CHOSEN.** That is a **narrowing of E1's constraint 2**, not a violation of it: a magnitude from
> that rung is *"measured on a field whose noise levels resemble altimetry and whose optimum
> coherence is a construction parameter"* — which is the standing limitation, arriving one level
> further in than it was written.
>
> **IT MUST BE RECORDED AT THE RUNG AND CARRIED INTO EVERY NUMBER QUOTED FROM IT**, or the
> magnitude reads as *"measured on a realistic field"* while its most load-bearing parameter was
> picked. **`Rung.source` becomes a per-parameter field rather than one string**, so an unsourced
> parameter is visible as unsourced instead of being covered by a citation that applies to a
> different parameter.

**THE DECISION THIS FORCES IS NOT TASK 1's TO TAKE SILENTLY** and is flagged at the report.

### (a5b) TWO CONSTRAINTS BIND THE RUNG'S PARAMETERS, AND THEY ARE SOLVED TOGETHER

**The rule promoted one task ago, applied at its first opportunity.** The rung's `σ` and `ρ` are
bound by **E1 constraint 1** (sourced) and by **E2** (the field must populate 6 point strata to 30
members each). **They are not independent:** if the sourced values make every point
white-noise-dominated, **every point selects the same candidate**, the winning-candidate axis
collapses from `M = 2` to 1, and the point strata halve before any margin bin is considered.

**So Task 1 checks both at once, before the values are fixed:** the field must produce **both
candidates winning somewhere**, and a selection margin that is **not concentrated in one bin**.
**Which is also criterion 17's neighbour** — the same field property drives the iteration count.

### (j) THE `ℓ`-RECOVERY TEST MUST NOT SHARE THE GENERATOR'S PARAMETERISATION

The plan's test says *"`coherence_length` is measured back out of the truth and matches its
parameter within a stated tolerance."* **Fitting the same functional form the field was generated
from makes the oracle a re-derivation of the generator** — (j), and it would pass for a builder
whose `ℓ` scales the wrong axis.

**The test becomes comparative rather than absolute:** at a **fixed lag**, the truth's spatial
autocorrelation is **strictly greater** for a larger `ℓ`, across the three rungs. **A monotonicity
assertion needs no shared functional form, cannot be satisfied by a mislabelled parameter, and is
the property the sweep actually relies on.** The absolute value is reported and not asserted.

### `Δ` IS NOT WELL DEFINED UNTIL IT IS RELATIVE TO THE WITHIN-REGIME VARIATION

**The field carries smooth variation everywhere AND a step across one boundary.** If the smooth
variation's range is comparable to the step, **the "sharp boundary" is not sharp in any sense the
smear estimator can use** — the profile's transition is buried in the profile's own slope.

**Nothing in E3 or E5 states the ratio**, so `Δ` names a contrast whose scale is undefined.
**`Δ` is therefore defined as a MULTIPLE of the within-regime range of the same parameter**, and
the ratio is recorded with the rung. **This is (a2d)'s shape at a lever: a magnitude whose unit is
implicit**, and two rungs could otherwise agree on `Δ = 2` and disagree on what it means.

### (a4) THE `32 × 12` DERIVATION RECOMPUTED — AND HALF OF IT IS FALSE AS STATED

**THE NORMAL AXIS SURVIVES AND IS RESTATED MORE PRECISELY.** `k = 8`, `32 = 4k`. With the boundary
at the **midpoint, index 16**, the field has **16 cells either side**, so an interior null line can
be placed **up to 16 cells — two full coarse spacings — from the boundary**, and any line in the
outer half of either side clears the one-spacing coupling range. **The claim "an interior line
sits at least 8 cells from the boundary" holds, and the placement it depends on — the boundary at
the midpoint — was never stated.** It is now.

> ## **AND THE PARALLEL AXIS'S DERIVATION IS WRONG. 12 IS NOT THE MINIMUM; 9 IS.**
>
> At `k = 8` the coarse indices on an axis of length `n` are `0, 8, 16, …< n`. **`n = 9` already
> gives `{0, 8}` — two coarse points.** So do 10 and 11. **The smallest `n` giving two coarse
> points per axis at `k = 8` is 9, not 12**, and "12 is the minimum giving two coarse points" is
> false as arithmetic. It was carried through E2, the plan, the harness and the verdict **without
> anyone multiplying it out** — including me, four times.
>
> **12 IS A CHOICE AND IT IS A GOOD ONE, SO THE REPAIR IS THE REASON, NOT THE NUMBER:**
>
> 1. **`32 × 12 = 384` points**, which is the count E2 needs to give D9's **6 point strata** a
>    chance at **30 members** each. At `32 × 9 = 288` the same six strata get 48 apiece at uniform
>    occupancy instead of 64, against a floor of 30 — **thinner where the design has least
>    margin.**
> 2. **Points exist BEYOND the last coarse index.** At `n = 12`, indices 9, 10 and 11 lie past the
>    coarse point at 8, so their nearest valid source is **behind them on one side only** — a
>    **one-sided source neighbourhood**, which `n = 9` barely exercises and which is the ordinary
>    case at any real field's edge.
>
> **So the honest statement is: the parallel axis needs at least 9 for the spiral to choose at
> all, and 12 is chosen for the point count and for the one-sided neighbourhood.** Corrected in
> E2, in the plan and at the constant, **struck rather than deleted**, because three documents
> asserted it as a derivation and a reader who finds only the fix cannot tell what was fixed.

---

## Plan Task 2 — the smear estimator and its interior null, audited before any code (2026-08-31)

**THE BRIEF** is the plan's Task 2 — a width in fine cells from a fitted map, with a floor, a
ceiling and a non-optional interior null — read together with *[what Task 2
inherits](../../../PROGRESS.md)*, which records that **Task 2's subject changed under Task 1's
rebuild** and that the estimator must therefore be **specified before it is written**. **Eight
findings. The first one rewrites what the estimator computes, and three of the plan's seven test
lines change with it.**

### THE PLAN'S ESTIMATOR IS A TRANSITION FIT AND THE SUBJECT IS NO LONGER CONTINUOUS

The plan says *"the profile is the map averaged parallel to the boundary… the width is that
profile's transition width by a named estimator."* Since Task 1 the boundary is a **change of
family** and the subject is `fields.SMEAR_SUBJECT`, **the selected candidate**, which is
categorical. **Averaging a candidate index is label arithmetic** — the mean of *"white"* and
*"white + matern32"* is not a candidate — so the plan's first sentence has no meaning under its
own subject. **This is not a detail of implementation; it is the reading.**

> ## WHAT THE ESTIMATOR COMPUTES, STATED IN FULL BEFORE A LINE OF IT EXISTS
>
> 1. **The per-point scalar is DISAGREEMENT, not the label.** `agreement_map` reduces the selected
>    candidate at each point to `0.0` if the winning candidate carries that point's true family,
>    `1.0` if it carries the other one or none, and `NaN` where nothing was selected. **This is
>    the only step that reads the truth**, and it is a separate function for that reason.
> 2. **The profile is the parallel-axis `nanmean` of that map**, so `p[i] ∈ [0, 1]` is the
>    **fraction of the line at normal index `i` that misclassifies its own regime**. It is a
>    misclassification profile and it is named as one.
> 3. **A cell is smeared when a strict majority of its line misclassifies: `p[i] > 1/2`.** Six of
>    twelve is a tie and is **not** a majority.
> 4. **The width is the length, in fine cells, of the maximal contiguous run of smeared cells that
>    contains one of the two cells adjacent to the boundary** — `boundary_index - 1` and
>    `boundary_index`. If neither is smeared the width is `0`.
> 5. **Floor:** width `0` or `1` is emitted as `≤ 1 cell` — `at_floor=True`, `cells=None`, **never
>    a number.** 6. **Ceiling:** width **greater than** `reach_cells` is refused, `cells=None`,
>    with the reach in the refusal text.
>
> **THE INSTRUMENT'S NAME CARRIES ITS THRESHOLD:** `"majority-run (> 1/2 of the parallel line)"`,
> one spelling, exported as a constant and stamped on every reading — (j8), because an adopted
> verdict makes the instrument part of the specification, and *"the smear width"* with no
> instrument is D8's pooled figure in a new place.

**WHY A MAJORITY RULE AND NOT A HALF-MAXIMUM, A THRESHOLD ON EXCESS, OR AN INTEGRATED EXCESS
MASS.** All three of those need a **baseline** — the disagreement rate the field would show with
no warm start at all — and **there is nowhere on this field to take one.** The reach is
`spiral_bound × coarse_stride = 32` fine cells and the normal axis **is** 32 cells, so every cell
of the field is inside the reach and no cell is available as an uncontaminated baseline. **An
estimator that estimates its own baseline from data the artifact may have touched is where an
estimator hides its own bias**, and 2c has already paid once for an instrument that measured
partly itself. **The majority rule needs no baseline**, which is the whole of its case.

> ## WHAT THE MAJORITY RULE IS BLIND TO, WITH THE NUMBER ATTACHED
>
> **A smear that lifts the disagreement rate to 30% across six cells reads at the floor.** Not
> *"may under-report"* — **`0.30 < 0.5` at every one of the six cells, so no cell is smeared, so
> the width is 0 and the reading is `≤ 1 cell`.**
>
> **AND THAT IS THE SHAPE A REAL ARTIFACT IS LIKELIEST TO TAKE.** A smear should **decay with
> distance** from the boundary rather than stop at an edge, so its profile is a slope and not a
> plateau; a slope crosses a half at **one** place and the majority rule converts everything below
> that crossing to nothing. **The estimator is blind to the gradual case by construction, and the
> blindness is worst exactly where the artifact is most physical.**

**SO THE PROFILE ON THE READING IS NOT *A* MITIGATION, IT IS *THE* MITIGATION**, and it only works
if someone looks at it: **a floor result is uninterpretable until its profile has been seen to be
flat rather than sloped.** That sentence goes in `WidthReading`'s docstring and not only here,
because the reading is what travels into Task 4's report and the pre-flight is not.

**THE SECOND ESTIMATOR'S TRIGGER, WRITTEN NOW; THE ESTIMATOR ITSELF IS NOT.** **If any rung's
committed profile shows a sustained elevation above its own baseline that the majority rule does
not convert to a width, that is the trigger** — buy a baseline-referenced estimator. *"Sustained"*
and *"elevated"* are read off the committed profile by eye at that point and are deliberately not
thresholds here: **a threshold written before any profile exists would be tuned against the first
profile that missed it.** What is fixed now is the **condition**, so the follow-up is falsifiable
rather than a standing worry.

> ## THE FLOOR IS A DERIVED THRESHOLD, NOT A CHOSEN ONE — AND THE RUN REQUIREMENT IS ITS OTHER HALF
>
> A line is **12 points**, so at a baseline disagreement rate `b` a single cell fires spuriously
> with probability `P(Binom(12, b) ≥ 7)`:
>
> | `b` | one cell fires | two adjacent cells fire |
> |---|---|---|
> | 0.2 | **0.39%** | 0.0000 |
> | 0.3 | **3.86%** | **0.0015** |
> | 0.4 | **15.8%** | **0.025** |
> | 0.5 | **38.7%** | 0.150 |
>
> **Below a half even at the coin-flip baseline, because the tie does not count** — which is the
> whole return on the strict inequality.
>
> **READ THE 15.8% AS A COUNT AND IT CHANGES WHAT THE FLOOR IS FOR.** At `b = 0.4` a 32-cell
> profile carries **about five spurious majority cells scattered through it**. **The floor does not
> handle five cells; it handles the isolated one.** What handles the other four is the **run
> requirement** — a spurious cell only enters the width if it is **contiguous with the boundary**,
> so five scattered fires contribute nothing unless one of them lands on a seed cell, and a
> *reportable* width needs two adjacent fires at **0.025**.
>
> **THE TWO WORK TOGETHER AND EITHER LOOKS LOCALLY SAFE TO DROP.** Drop the floor and every
> isolated seed-cell fire becomes a reported `1.0`; drop the run requirement and the width becomes
> a count of scattered noise anywhere on the axis. **Neither is defensive and neither is a style
> choice.** **This table goes in the module**, because it is the arithmetic a later reader needs
> when they propose lowering the threshold to catch a subtler smear — and by the paragraph above,
> **they will**, and they will be right about the smear and wrong about the cost.

### (j5) THE TRUTH-READING IS QUARANTINED, SO THE PLAN'S INVARIANT STAYS LITERALLY TRUE

The plan's last behaviour line is *"the estimator reads the true parameter field for the boundary
index and for nothing else."* **A categorical subject needs the truth family per point and the
candidate-to-family mapping**, so a single function taking the raw selection map would break that
line outright.

**It is not broken, it is relocated.** `agreement_map(selected, family)` reads the truth;
`smear_width` takes the map it returns and still reads **only** the boundary index. **The line
survives as written and the truth dependency has one home**, which also means the mapping from a
candidate to a family — the one piece of this that can silently collapse both Matérn candidates
into one — is unit-testable on its own.

### THE INTERIOR NULL IS THE SAME ESTIMATOR AT A FALSE BOUNDARY, AND THE LOCATION HAD TWO SPELLINGS

The plan says *"same estimator, on a line parallel to the boundary at a stated offset."* Under the
majority-run estimator that resolves exactly: **`interior_null` runs `smear_width` with the seed
pair moved to a false boundary at `boundary_index - offset_cells`.** The profile is the same
profile, the fits are the same fits, and the control costs no compute — which is what E6 promised.

**AND THE LOCATION IS ALREADY WRITTEN TWICE.** `fields.NULL_LINE_INDEX` is `4`, an **index**; the
plan's parameter is `offset_cells`, a **distance**. At `BOUNDARY_INDEX = 16` they are the same
place spelled two ways, and (j9) has fired five times in this sub-phase on exactly that shape.
**`offset_cells` is the parameter and `NULL_LINE_INDEX` is derived from it**, so the two cannot
drift; the constant's own docstring already states the distance — *"12 cells from it"* — while the
value is the index, which is the drift in miniature.

### THE INTERIOR NULL'S PREDICTION, COMMITTED HERE, BEFORE ANY RUNG RUNS

The handoff requires this and warns that **the previous expectation was formed against a
continuous subject.** It does not transfer, and the reason is specific rather than general.

**PREDICTED: the interior null returns `≤ 1 cell` and does NOT fire.** Under a continuous subject
the expectation was the opposite, because a transition fit applied to a smoothly varying profile
finds *some* slope and returns *some* number wherever it is placed — the null would fire off the
field's own smoothness. **A misclassification profile has no such slope to find.** `_family()` is
a **pure indicator**: the true family is constant within a regime by construction, so smooth
within-regime variation in `σ`, `ρ` and the white floor moves the parameters **without moving
which family is true**. A correct classifier's disagreement rate is therefore flat within a regime
up to sampling noise, and **the majority rule cannot fire off a flat profile.**

| refuted from below | refuted from above |
|---|---|
| **the null returns a width.** Two causes and they need separating, not merging: either the estimator is reading the field's structure — **E6's third row, stop the sub-phase** — or the **baseline disagreement rate itself exceeds a half away from the boundary**, which is a statement about **selection between two Matérn families at `N = 630`** and not about warm-starting at all. **The profile on the reading is what tells them apart**, and the second one invalidates the categorical subject rather than the estimator | **the null can never return a width on any input.** That is not a result, it is an unfalsifiable gate, and it is why Task 2's paired positive control — a band constructed *at* the null line — is a test and not an option |

### (a2b) THE CEILING CANNOT FIRE ON 2d's OWN FIELD, AND THAT CHANGES WHAT IT IS FOR

`spiral_bound(4) × coarse_stride(8) = 32` fine cells, and `N_NORMAL = 4 × COARSE_STRIDE = 32`.
**The reach is the entire normal axis**, so on the shipped field a width above the reach is not
merely unphysical — **it is arithmetically impossible for a correct run-length over 32 cells.**

**So the refusal is a self-check on the estimator, not a physics filter, and it is recorded as
that.** If it ever fires on a real rung the estimator has returned a run longer than the axis it
ran on. **It is still built, still read from config and still tested**, because the plan's ceiling
is written against `reach_cells` as a **parameter**. **What must not happen is the ceiling being
quietly dropped as unreachable**, which is the reading a maintainer arrives at from the geometry
alone without this paragraph.

> **AND THE CONDITION THAT MAKES IT REACHABLE IS NAMED, WITH THE TEST THAT ALREADY COVERS IT** —
> the criterion-12 treatment, because *"unreachable"* is a claim about a configuration and not
> about the code. **Either of two changes restores it to a physics filter: a `spiral_bound` below
> 4, or a normal axis longer than `spiral_bound × coarse_stride`.** **C2 exercises the first
> today** — it halves `spiral_bound` and asserts the refusal boundary moves with it — so the
> reachable case is under test even though the shipped geometry cannot produce it. **The second
> has no test and needs none while `N_NORMAL` is derived as `4 × COARSE_STRIDE`**, which pins the
> axis to the reach by construction; **a later field that sets the normal axis independently is
> the change that makes it live**, and that is a field-builder decision rather than an estimator
> one.

### (j9) THE REACH GETS ONE SPELLING, AND HALF OF IT IS ALREADY WRITTEN

`fields.COARSE_STRIDE` already reads `WarmStart().coarse_stride`. A new module reading
`WarmStart().coarse_stride` again would be **a second spelling of a shipped constant** — the
instance that has fired five times in 2d, most recently on an instrument block that was itself a
copy. **The reach is `reach_cells(warm=None)`, computed as `warm.spiral_bound ×
fields.COARSE_STRIDE`, taking the `WarmStart` as an argument** so that a test can move
`spiral_bound` without monkeypatching a module constant — a constant read once at import is
exactly the *"config change moves the physics but not the check"* bug the plan's sixth test line
names.

**A SOURCE-SCAN TEST FORBIDDING A SECOND `WarmStart().coarse_stride` WAS CONSIDERED AND DROPPED,
AND THE DROP IS RECORDED AS A LATENT INSTANCE RATHER THAN AN ABSENCE.** Two spellings that both
read the same **default** cannot disagree, so today there is no bug for such a test to catch and
C1/C2 cover everything that can move. **It becomes live the moment anything constructs a
`WarmStart` with a non-default `coarse_stride`** — a benchmark at a different stride, or a config
that sets one — because then `fields.COARSE_STRIDE` is still the default while the reach is
computed from the caller's object, and the two describe different fields. **That condition is
named in the module docstring**, so the next person to set a non-default stride meets it rather
than discovering it.

### THE `NaN` IN THE PLAN'S TEST LINE IS A SENTINEL IN THE STORE, AND IT IS THE COMMONER CASE

The plan's fifth test says *"a map with a NaN column does not silently shorten the profile."* The
map Task 4 will hand this estimator comes from **`/selection/selected`, `int16`, where `-1` means
"no winner" and `SELECTED_UNSET = -2` means "nothing wrote here"** — so the real hazard is not a
float `NaN` arriving, it is **an integer sentinel comparing unequal to the truth index and being
counted as a misclassification.** That manufactures a smear out of unwritten and undecided cells,
**and those cluster exactly where fits are hardest, which is near the boundary.** `agreement_map`
maps both sentinels to `NaN`; a test names each one separately.

**And the plan's line splits in two**, because *"column"* is ambiguous on a 2-D map and the two
readings fail in opposite directions. **An all-`NaN` line parallel to the normal axis** must leave
the profile at full length and the width unchanged — the `mean`-for-`nanmean` bug. **An all-`NaN`
normal row at the growing edge of the band** must **refuse**, because a `NaN` that terminates the
run behaves exactly like a non-majority cell and **narrows the width, always in the reassuring
direction.** A `NaN` row far from the band refuses nothing, or a partially fitted field becomes
unreadable and Task 5 reports nothing at all.

> **THE ASYMMETRY IS WHAT STOPS THE REFUSAL BEING EITHER USELESS OR TOTAL, AND ITS BOUNDARY IS A
> JUDGEMENT, SO IT IS STATED AT THE CHECK AND NOT ONLY HERE.** **A `NaN` row refuses exactly when
> it is a cell the run had to decide about** — a seed cell, or the first cell beyond either end of
> the run — **and is ignored everywhere else.** That is the smallest set with the property that
> matters: **every `NaN` capable of changing the width refuses, and no `NaN` incapable of changing
> it does.** Refusing on any `NaN` anywhere makes a partially fitted field unreadable; refusing on
> none lets missing data narrow the width. **Written beside the check, because a year from now the
> rule reads as an arbitrary radius unless the property it was chosen for is next to it.**

### DEVIATIONS FROM THE BRIEF, STATED RATHER THAN ABSORBED

| the plan says | what ships | why |
|---|---|---|
| `smear_width(field_map, …)` is the whole estimator | plus `agreement_map(selected, family)` ahead of it | the categorical subject needs the truth; quarantining it keeps *"reads the boundary index and nothing else"* true |
| *"the map averaged parallel to the boundary… its transition width"* | a **misclassification profile** and a **majority-run** width | a candidate index has no mean |
| *"a constructed transition of exactly 5 cells returns 5 **within tolerance**"* | returns **exactly** `5.0` | a run length is integral; a tolerance would only hide an off-by-one |
| `WidthReading` has nine fields | plus `profile: tuple[float, ...]` | E6's third row says *"stop and diagnose"*, and the profile is what a diagnosis is made of. It is also the only way a sub-majority band is visible at all |
| the null's location is *"a stated offset"* | `offset_cells` is the parameter; `fields.NULL_LINE_INDEX` derives from it | one location, one spelling |

### THREE THINGS FOUND OUTSIDE TASK 2, NONE OF THEM TASK 2's TO FIX

1. **THE THIRD RUNG IS DECIDED AND NOT SHIPPED.** E4 was re-decided to **three rungs** on
   2026-08-30 and the 19.7 h budget's `14.047` factor counts three; **`fields.RUNGS` holds two**,
   `easy` and `hard`, and the middle rung — *"ours to choose, on the same diagonal, and it must
   say so in its `sources`"* — has no entry. **The docs commit deciding it landed after the code
   commit that would have carried it.** Task 2 does not need it; **Task 4 cannot run without it**,
   and the budget is quoted against it today.
2. **2d HAS NO *"What plan Task 1 established"* SECTION.** The plan's own standing requirement
   sends each task's findings there; Task 1's live in `phase2d-field-verdict.md` and in item 4 of
   *what Task 2 inherits* instead. **Not a contradiction — a missing home**, and the next reader
   looking for Task 1 by the documented route finds nothing.
3. **CI HAD A RED RUN AT `7ff7763` THAT THE ENUMERATION LINE DOES NOT MENTION.** Run
   `33338155827`, `test (ubuntu-latest, 3.12)`, `1 failed, 1211 passed … 1965.46 s`, and the
   failure is **the already-recorded flake** — `test_a_preempted_command_exits_aborted_early_and_resumes`,
   `GroupNotFoundError`, cold-start item 9(c). The commit is docs-only and the tip is green, so
   nothing is blocked. **What is wrong is the record:** *"every `src`-touching commit green; the
   rest docs-only"* is true and **reads as "and the rest were green"**, which they were not.
   **A colour stated for one subset silently claims nothing about the other**, and the enumeration
   exists precisely so that no run's colour is supplied by the reader.

---

## Plan Task 3 — the N2 full-field map, audited before any code (2026-08-31)

**THE BRIEF** is the plan's Task 3 — the audit's N2 arm run over every point of the field, giving
the floor a smear width is read against — plus the four points carried in with it: **the
perturbation matched per cell and never on average; the seed recorded and keyed, and it is
`audit.seed`; an inadmissible start excluded and counted, never marked `x0_valid=False`; and N1
and N2 sharing the direction.** **All four are already true of the shipped `arm_starts`, which is
the finding that reshapes this task: Task 3's job is not to build N2, it is to REDUCE it to a
map without losing any of the four.** Seven findings, and the first two change the interface.

### THE PLAN'S `scalar: str` IS CONTINUOUS-SUBJECT RESIDUE, AND IT REINTRODUCES WHAT TASK 2 REMOVED

The plan's signature ends `..., scalar: str) -> tuple[NDArray[np.float64], N2Counts]` — a
**float** map of a **named scalar**, which is the interface a continuous subject needs. **Task 2
settled that the subject is `fields.SMEAR_SUBJECT`, the selected candidate, and that a width *"of
sigma"* is a width of two different quantities across a change of family.** A free scalar name
here would let a caller ask for the N2 floor of `sigma` — a number `smear_width` cannot read and
`agreement_map` has no meaning for.

> **THE MAP IS THE SELECTION MAP, `int16`, IN THE STORE'S OWN VOCABULARY.** `agreement_map` and
> `smear_width` then consume it **unchanged**, which is the test that the two tasks compose: Task
> 3 produces exactly what Task 2 consumes, with no adapter between them and therefore no third
> place for the subject to be respelled.

**AND THE ABSENT CELLS GET `-2`, NOT `-1`.** `-1` is the store's *"a fit ran and no candidate
won"*; an excluded point **had no N2 fit at all**, which is `SELECTED_UNSET = -2`, *"nothing wrote
here"*. Both become `NaN` in `agreement_map`, so nothing downstream can tell them apart — **which
is exactly why the map must not spend the wrong one**: the distinction is lost at the next step
and can only be got right here.

### THE EXCLUSION IS PER CELL, THE MAP IS PER POINT, AND THE REDUCTION IS **ANY**, NOT **ALL**

**The plan does not state this and it is the largest specification decision in the task.**
`ArmStarts`' accounting is `(B, M)` — per `(point, candidate)`. The selected candidate is `(B,)` —
per point, from `ranking.best_index`, which **compares all `M` candidates' scores against each
other.**

> **SO ONE CONTAMINATED CANDIDATE CONTAMINATES THE POINT.** If candidate 1's N2 start was
> inadmissible and fell back to the ladder while candidates 0 and 2 ran N2, the winner was decided
> **partly by a cold fit**, and the point's selection is not the N2 arm's selection. **A point is
> excluded if ANY of its candidates is**, and an `all()` here would keep exactly the mixed points
> — which are the ones whose value is neither N2's nor cold's and which no later reader could
> identify.

### `run_arms` **DOES** RUN THE EXCLUDED CELLS COLD, AND THE PLAN'S WORDING HIDES IT

The plan says *"inadmissible starts are excluded and counted, never run cold"*, and
`ArmStarts.n2_inadmissible`'s docstring says they are *"EXCLUDED and counted, never run"*. **Read
against the code, that describes the ACCOUNTING and not the FIT.** `arm_starts` sets
`n2_valid = valid & admissible`, `run_arms` passes it as `x0_valid`, and `fit` **falls back to the
moment ladder wherever `x0_valid` is false** — which is the ladder, which is cold. **So
`run_arms`' N2 `FitResult` contains cold fits at precisely the cells the accounting excludes.**

**THIS IS NOT A DEFECT IN `run_arms`.** Refusing there would abort the audit over one cell, which
is the reason `warm_start_faults` exists as a mask rather than a refusal. **It means the exclusion
the plan demands is the CONSUMER's, and Task 3 is that consumer** — the first one. A reader who
checks `run_arms` for the guarantee finds a docstring that appears to give it.

> **AND THE MASKING MUST BE SHOWN TO BE LOAD-BEARING RATHER THAN DEFENSIVE — (i8), (a2b) AT A
> COUNT.** A test asserts that `run_arms`' raw N2 selection at an inadmissible cell **equals the
> cold arm's**, so the fallback is demonstrated to happen on a constructed input before the map is
> credited with removing it. Without that test, *"the map holds no cold fit"* is a claim about a
> fault nobody has seen occur, and the exclusion path's zero count would be a statement about the
> instrument.

### `N2Counts` GAINS `inadmissible`, AND THE FOUR NUMBERS BECOME AN IDENTITY

The plan's `excluded / zero_distance / exhausted_spiral` leaves the inadmissible count as
`excluded - exhausted_spiral` — **derivable, and a reader has to know to subtract.** The two
exclusion reasons are two different defects and are named separately.

| field | meaning |
|---|---|
| `excluded` | points with **no N2 value** in the map. **`== exhausted_spiral + inadmissible`, asserted** |
| `exhausted_spiral` | excluded because some candidate had **no warm source**, so there is no distance to match |
| `inadmissible` | excluded because some candidate's N2 start **left the diagnostic box**. Counted only where the point is not already excluded for exhaustion, **so the two are disjoint and the identity holds** |
| `zero_distance` | **NOT excluded.** Reported |

**AND `zero_distance` IS REPORTED RATHER THAN EXCLUDED, WHICH IS A DECISION.** At a matched
distance of exactly zero the equal-distance random start **is** the cold start, so the cell's N2
value is the floor at that cell — a correct reading, not a missing one. **Dropping it would be
discarding cells for having an inconvenient answer**, which is the shape D8 refuses. It is counted
because it contributes *"N2 agrees with cold"* **by construction**, and a floor built largely from
such cells is a floor about the field's degeneracy rather than about random starts.

### `exhausted_spiral` IS NAMED FOR THE ONLY THING THAT MAKES `SourceMap.valid` FALSE

`SourceMap.valid` is `index >= 0` and `index` is `-1` **only** where the spiral was exhausted, so
*"no warm source"* and *"the spiral was exhausted"* are the same cells — **today, and by
construction rather than by coincidence.** The count is therefore honest and the contract is on
`SourceMap`: **a caller passing a differently-derived validity array mislabels its own cells**, and
the docstring says so rather than leaving the name to be trusted.

### (k) THE GRID-GLOBAL KEY IS STABLE ONLY UNDER GROWTH IN THE SLOWEST-VARYING AXIS

The plan's test is *"enlarging the field does not move an existing point's N2 direction"*, against
the (k) finding 2c recorded. **Checked against the arithmetic, it is true of one axis and false of
the other.** The key is the row-major flat index `iy * n_parallel + ix`. **Adding rows leaves every
existing point's index untouched; adding COLUMNS moves all of them but the first row's.**

> **THAT IS A PROPERTY OF THE KEY AND NOT A DEFECT, AND IT IS RECORDED BECAUSE THE PLAN'S SENTENCE
> CLAIMS MORE THAN THE KEY DELIVERS.** A flat index into a 2-D grid cannot be invariant to a change
> in the grid's stride; the alternative — keying on `(iy, ix)` — is not available, because
> `arm_directions` takes the flat index that `SourceMap` and pass 1's store are both written
> against, and inventing a second key here would be a second N2. **2d's field never grows in either
> axis, so nothing is at risk today.** The test asserts the guarantee that exists — growth along
> the normal axis — and the docstring states the one that does not.

### `field: FieldTruth` IS REPLACED BY THE BATCH ARRAYS AND THE GRID SHAPE

**`FieldTruth` carries no observations.** It has `uri`, `parameters`, `family`, `boundary_index`,
`t` and `rung`; the fits need `y` and `mask`, so a `FieldTruth`-shaped signature would have to
**re-open the store** — a second read path for data the caller already holds, and a second place
for the point ORDER to be got wrong. **It would also make every test build a field**, at minutes
per test, when the plan placed this task among the two that need no field and no run.

**The point set has no freedom and is therefore not a parameter.** A full-field map is every point
in row-major order, so `points` is `arange(n_normal * n_parallel)` and is **derived rather than
accepted** — a caller cannot hand in a permuted set. **The shape check catches a wrong COUNT and
not a wrong ORDER**, and that limitation is stated at the argument rather than implied by its
absence: the row-major precondition is `SourceMap`'s and `assemble_tile`'s, and it is inherited.

### WHY THE ARM EXISTS, WRITTEN WHERE THE MAP IS DEFINED

**A smear measured against zero is a different claim from a smear measured against the width an
equal-distance random start produces.** Zero is not a floor — it is the absence of one, and a
width read against it silently asserts that a random start of the same magnitude would have
produced none. **That sentence goes in the module docstring**, because the map is the only artifact
that carries it into Task 5's report, and a floor whose purpose is not beside it reads as one more
arm.

---

## Plan Task 1, AMENDED — the third rung, audited before it is added (2026-08-31)

**THE BRIEF** is E4's re-decision of 2026-08-30: **three rungs, not two**, with the middle one
**ours to choose**, its `ℓ` and `Δ` **between the two shipped rungs on the same diagonal**, and
criterion 17 **re-measured** for it rather than interpolated. **It is a Task 1 amendment and not
new work**, because a rung is a field-builder object and adding one re-opens Task 1's own
`ℓ`-monotonicity test. **Four findings, and two of them fired inside this task's own repairs.**

### THE DIAGONAL IS GEOMETRIC, AND THE REASON IS THE QUANTITIES' KIND RATHER THAN THE NUMBERS

*"Between the two shipped rungs on the same diagonal"* does not by itself say **in what
coordinates**, and arithmetic and geometric midpoints differ: `(11.0, 1.875)` against
`(9.798, 1.5)`. **The criterion is stated before the values are computed**, or this becomes a
choice justified by the answer it gives.

**`coherence_length` is a LENGTH SCALE** — what matters about it is its **ratio** to
`COARSE_STRIDE`, not its difference from it; that is how both shipped rungs' own sources are
written (*"2× the coarse stride"*, *"below the coarse stride"*). **`contrast` is already defined
as a MULTIPLE of `WITHIN_REGIME_RANGE`.** Both are ratio-scale, so **evenly spaced means evenly
spaced in the logarithm**, and the geometric midpoint is the one that makes the three a curve.

> **THE VALUES FOLLOW AND ARE NOT CHOSEN:** `ℓ = √(16 × 6) = 9.7980` fine cells, `Δ = √(3 × 0.75)
> = 1.5` **exactly**. **Recorded as consequences rather than as reasons**, in this order
> deliberately: `Δ` makes the three a **factor-of-two ladder** 3.0 / 1.5 / 0.75, and `ℓ` is
> **1.22 × COARSE_STRIDE** — between the easy rung's `2k` and the hard rung's `0.75k`, so the
> middle rung is the one whose coarse neighbour sits *just* inside one correlation length. **Both
> are pleasing and neither was the argument.**
>
> **AND THE RUNG IS COMPUTED FROM ITS NEIGHBOURS IN THE CODE, NOT WRITTEN AS A LITERAL** — (a2e),
> encode a classification as a construction. `ℓ = 10.0` is 2% off the line, looks like a tidier
> number, and would make the spacing unequal in the coordinate the effect is expected to be
> smooth in; a non-monotone result at the middle rung could then no longer be read as a finding
> about the lever rather than about the placement. **A test asserts the geometric identity**, so
> replacing the computation with a literal is caught.

### THE MONOTONICITY TEST IS REWRITTEN AGAINST THE SET, AND (c5) FIRED TWICE IN ONE FILE

The shipped test asserted `correlation_at(easy) > correlation_at(hard)` — **a pairwise assertion,
which passes for a middle rung placed anywhere at all**, including off the diagonal or equal to
one of its neighbours. It is now an ordering over **every** rung in `RUNGS`, sorted by `ℓ`, with
each adjacent pair checked and **distinct coherence lengths asserted** so three rungs cannot
secretly be two.

> **AND THE SECOND INSTANCE IS THE INSTRUCTIVE ONE, BECAUSE IT BROKE RATHER THAN WEAKENED.**
> `test_the_plausibility_rung_is_absent_and_asking_for_it_raises` opened with
> `assert set(fields.RUNGS) == {"easy", "hard"}` — **an enumeration of the members standing in for
> a property about the set** — and it failed the moment a third rung landed. **A true statement
> about the members had become a false gate about the property.** The property is that the
> **plausibility slot stays empty**, which is indifferent to how many rungs exist; it now reads
> `"plausibility" not in fields.RUNGS`.
>
> **(c5) is normally a rule about gates that silently pass. This is its other failure mode: a
> gate that loudly fails for the wrong reason**, and the loud one is the lucky one — the same
> enumeration inside the **harness** (`for name in ("easy", "hard")`) would have measured two
> rungs of three and emitted a complete-looking table. **It is now written against `RUNGS`.**

### CRITERION 17 IS RE-MEASURED, AND THE REASON IS SHARPER THAN "A POINT BETWEEN TWO POINTS"

(a4)'s register says a point between two measured points is not measured. **Here the temptation is
stronger than usual and that is worth naming:** the two shipped rungs came back at **24.375 and
24.396** — a difference of **0.021** against a standard error of about **0.19** on each mean, so
they are **indistinguishable**. *"Both endpoints agree, so the middle must too"* is a much more
persuasive argument than an interpolation between two different numbers, **and it is the same
argument.** The budget rests on the **largest** of the three.

**So the prediction is a NULL, and a null needs its positive control named.** *"The middle rung
costs what the others cost"* is byte-identical in the output to *"the rung parameter never reached
the field"*. **The control already exists as a test rather than as a reading** — the
autocorrelation ordering, and *"one rung twice is identical and two rungs differ"* — and the
predictions file says that if either fails, no number from this reading may be quoted.

### THE BAND IS SET FROM THE MEASURED SPREAD, NOT FROM ROUND NUMBERS

`24.385 ± 3 × 0.198 = [23.79, 24.98]`, rounded outward to **`[23.8, 25.0]`** — (i10) and (a9),
after Task 0's clauses were guesses against an unmeasured quantity. **Both refutation clauses are
written and they differ in consequence, not only in sign:** below the band and above it are the
same refutation of monotonicity, **but only the upper one re-prices the sub-phase**, because the
budget is built on the largest rung. The lower clause carries an explicit *"do not re-place the
rung to make the curve monotone"*, which is the repair a reader would reach for and is tuning the
sweep against its own result.

---

## Plan Task 4 — the driver and its reproducible report, audited before any code (2026-08-31)

**THE BRIEF** is the plan's Task 4 — build the field, run the cold pass, run the shipped two-pass,
take the N2 map and the widths, emit one report — **plus the four points carried in with it: the
instrument block DERIVED rather than transcribed; Task 9 asserting against committed reports and
failing when a default has moved; the Cholesky note making the draw method part of the block; and
a floor reading distinguished from a measured width, with the profile carried either way.**
**Seven findings. The first is where the gate lives, and the second is that the report cannot be
built out of `Quantity` alone.**

### WHERE THE NULL GATE LIVES: THE DRIVER, AND THE STRONGER FORM IS *NOT COMPUTED* RATHER THAN *WITHHELD*

The question was driver or report. **The driver** — and the reason the alternative is bad is
sharper than *"a marked reading invites proceeding"*: **a reading that exists can be read.** A
report carrying a smear width beside a `contaminated: true` flag has the number in it, and the
number is what travels.

> **SO THE ORDERING IS THE MECHANISM, NOT THE FLAG.** `run_rung` computes the interior null
> **before any smear width is taken**, and on contamination **the widths are never computed at
> all.** The report's smear entries are then withheld objects carrying the reason — which is what
> the plan asks for — **and there is no hidden value behind them**, because none was produced.
> (a2b) at its strongest: not *"made unavailable"* but *"never made"*.

**THE GATE HAS TWO HALVES AND THEY SIT AT DIFFERENT LEVELS**, which the plan does not separate:

| half | where | what it does |
|---|---|---|
| **within a rung** | `run_rung` | the null is ordered first; widths are not computed; their quantities are withheld with the reason |
| **across rungs** | `require_clean(report)`, called by Tasks 5–7 | **raises.** The sub-phase stops rather than proceeding to the next rung |

**`run_rung` STILL RETURNS THE REPORT ON A CONTAMINATED RUNG, AND THAT IS DELIBERATE.** E6 says
*"stop and diagnose"*, and **a diagnosis needs the null's profile**, which only the report carries.
Refusing to return would destroy the evidence the gate exists to surface. **What is refused is
proceeding, and it is refused by a separate callable rather than by a flag someone must remember
to read.**

### THE REPORT CANNOT BE BUILT OUT OF `Quantity` ALONE: IT HAS TWO STATES AND THE SMEAR HAS THREE

`Quantity` carries `value: float | None` with `withheld` present exactly when the value is None —
**two states, and they are the right two for a rate.** A smear reading has **three**:

| state | means | `Quantity` would say |
|---|---|---|
| **a measured width** | `cells = 5.0` | value present |
| **at the floor** | **a valid reading with no number** — `≤ 1 cell`, the resolution limit | value None + a reason |
| **refused or withheld** | **no reading at all** — past the reach, or the rung is contaminated | value None + a reason |

**The second and third would be indistinguishable**, and they are opposite claims: *"the instrument
looked and resolved nothing"* against *"the instrument did not look"*. **That is (a0)'s
excluded-versus-missing register arriving at a report field.**

> **SO THE REPORT CARRIES THE `WidthReading` ITSELF BESIDE THE `Quantity`**, and the reading's own
> `at_floor` / `refused` / `cells` triple is what distinguishes them. The `Quantity` exists for the
> uniform reporting surface Task 9 asserts over; **the reading is what makes the row
> interpretable, and Task 2 already settled that a floor result is uninterpretable until its
> profile has been seen.** **A report recording `≤ 1 cell` without the profile has recorded
> nothing**, and that sentence is in `WidthReading`'s docstring rather than only here.

### `Quantity` WITHOUT A RUNG: A SUBCLASS WITH A KEYWORD-ONLY FIELD, SO THE CHECK IS REUSED AND NOT RE-WRITTEN

The plan says the non-empty-scope construction is **reused, not re-invented**. **Re-implementing
the scope refusal in a 2d type would be (j9) at a validator** — two spellings of one rule, drifting
the first time one is edited. `RungQuantity` therefore **subclasses `Quantity`** and adds
`rung: Rung` as a **keyword-only** field, so `Quantity.__post_init__`'s scope and half-stated
checks run unchanged and every 2d number is a `Quantity` to everything downstream.

**A factory returning a plain `Quantity` was considered and rejected**: it puts the rung in the
scope string by convention, and *"cannot be constructed without a rung"* becomes *"is not usually
constructed without a rung"*. **D8's whole argument is that labelling a number does not stop it
being quoted.**

### THE DRAW METHOD IS PART OF THE FIXTURE'S IDENTITY AND IS CURRENTLY A LITERAL AT THE CALL SITE

`build_field` passes `method="cholesky"` inline, with a comment saying a later change there
**invalidates every committed rung report**. **The instrument block cannot name it without
transcribing it**, which is precisely the defect the block exists to prevent — and (j9)'s worst 2d
instance was an instrument block that was itself a copy.

> **`DRAW_METHOD` becomes a module constant in `fields.py` and the call site reads it.** Then the
> block names the constant, a change moves both, and the artifact check has something to compare.
> **The drawn bytes are keyed by seed AND method**, so a block carrying the seed alone describes a
> field it cannot reproduce.

### THE FIELD'S GEOMETRY IS MODULE CONSTANTS, SO NOTHING CAN RUN THE DRIVER AT A TESTABLE SIZE

`N_NORMAL` and `N_PARALLEL` are constants and `build_field` takes no geometry, so **every driver
run is 384 points × `M = 3`**. At the measured 11–13 s per point that is over an hour for one
rung's cold arm alone. **A test cannot call `run_rung` at all**, and a task whose only test is the
benchmark it is not allowed to run in the suite has no tests.

**AND SHRINKING THE FIELD DOES NOT RESCUE IT, WHICH IS THE PART WORTH KNOWING BEFORE TRYING.** The
interior null needs `n_normal // 2 - NULL_LINE_OFFSET_CELLS ≥ 1`, and the shipped offset is
**12** — not the coarse stride's 8 — so **`n_normal ≥ 26`** before a legal null line exists at all.
**A field small enough to be fast cannot carry the control**, and one that carries it is not fast.

> **THE FIRST VERSION OF THIS PARAGRAPH SAID 18, AND IT WAS WRONG BY THE SAME MOVE (a4) EXISTS
> FOR.** 18 comes from the offset having to exceed one **coarse spacing**, which is the constraint
> on where the null line may be PLACED; the binding constraint is the offset actually shipped,
> which is 12. **The two are different numbers for different reasons and the smaller one was the
> one already in mind.** Corrected before it sized anything.

> **SO THE DRIVER IS DECOMPOSED SO THAT EVERYTHING ASSERTABLE IS A PURE FUNCTION OF THE READINGS.**
> The report assembly — the gate's decision, the instrument block, the quantities, the withholding,
> the reproducible/timing split — takes readings and timings as **arguments** and is tested on
> **constructed** ones, exactly as Tasks 2 and 3 were. `run_rung` is then the thin part that
> produces those readings from a real field, and it is the benchmark rather than a test.
>
> **`build_field` gains optional `n_normal` / `n_parallel`**, defaulting to the constants, so one
> end-to-end test can run at the smallest legal geometry. **The risk is a run at a non-shipped
> geometry whose numbers get quoted**, and the mitigation is the instrument block: **the geometry
> is in it, and Task 9 asserts a committed report's geometry equals the shipped constants.**
> **That is the block earning its keep rather than decorating the file.**

### TWO RUNS BYTE-IDENTICAL OUTSIDE THE TIMING BLOCK — AND ITERATIONS BELONG ON THE REPRODUCIBLE SIDE

The plan segregates timings so a bitwise comparison is possible in principle. **The third rung's
measurement makes the split sharper than "timings are not reproducible":** the same fixture
reproduced its **iteration counts to every digit** a day later while its **seconds moved 15%**.

> **SO ITERATIONS GO ON THE REPRODUCIBLE SIDE OF THE LINE AND SECONDS DO NOT.** That strengthens
> the byte-identity test from *"the numbers that happen not to be timings"* to *"everything the
> run determines"*, and it gives the cost block a component that a later reader can actually check
> a committed report against. **The seconds are reported and never compared** — the phrase pass 2's
> own report already uses for wall clock.

### THE COST BLOCK IS DERIVED FROM THIS RUN, AND THE UPPER-BOUND SENTENCE TRAVELS WITH IT

Measured per arm and per point by this run, never transcribed from `13.15`. **And the report says
what the figure is:** the budget is priced at the **cold** rate, so **a run finishing early is the
bound behaving and not an error** — the sentence is in the report because that is the artifact a
reader meets, and *"why is this 30% under budget"* is otherwise a question someone answers wrongly.

---

## Plan Task 5 — the easy rung, audited before any run (2026-08-31)

**THE BRIEF** is the plan's Task 5 — run the easy rung, read the interior null **first**, establish
that the smear width exceeds the 1-cell floor, run N1, record the saving — **plus the eight things
the cold-start handoff carries in**, of which three are load-bearing here: the cold arm's width is
not zero and the reading is warm **against the N2 floor**; a firing null has two causes and the
profile separates them; and **the gate can fail as a finding**, with a retune being a new rung
rather than an edit.

**ELEVEN FINDINGS. The first re-prices the sub-phase, and the second is that the run Task 5 is
about to pay for already computes three arms and throws them away.** Nothing below re-argues E1–E8
or restates a magnitude that lives in
[what 2d's tasks inherit](../../../PROGRESS.md); every figure here is either derived in place from
those or is new.

### 1. THE N2 MAP COSTS FOUR ARMS AND THE BUDGET PRICED ONE — E2's FACTOR IS 18.047, NOT 14.047

`report.run_rung` calls `n2map.n2_field_map`, which calls **`audit.run_arms`**, which runs
**four full-field fits** — `COLD`, `WARM`, `N1`, `N2` — and `n2_field_map` returns **the N2
selection map and the counts only.** That is the design Task 3 was right to choose (*"a second
derivation of N2 is a second N2"*), and **it means the map is a four-arm object priced in E2 as a
one-arm one.**

| line | E2's factor | what the shipped code costs |
|---|---|---|
| cold full-field pass + two-pass, per rung | 2.016 | 2.016 |
| the N2 full-field map | **1.0 × 2 rungs** | **4.0 × 3 rungs** — `run_rung` runs the map unconditionally, and its `arms=` argument selects only which widths are **read** |
| the four-arm audit, one rung | 4.0 | **0 — it is the middle rung's own map**, same batch, same session, same seed |
| N1, two rungs | 2.0 | **0 — N1 is inside every map** |

> **THE CORRECTED FACTOR, THE HOURS, AND THE VARIANT THAT DOES NOT FIT LIVE IN ONE PLACE —
> [the budget box](../../../PROGRESS.md), which declares itself the single home for every 2d rate.**
> **This entry is the derivation and not a second copy of the number**, which is the rule that
> deleted a copy rather than reconciling one. What belongs here is why it survived: the reuse
> `n2_field_map` performs is Task 3's own design and is right, and **the reading that priced it
> was taken off the call's signature.**
>
> **WHAT THIS COSTS TASK 5 SPECIFICALLY: 6.016 arms = 8.44 h** at `13.15 s/point/arm` over 384
> points, **7.3 h** at `11.38`, against the **4.016 arms ≈ 5.6 h** the plan's Task 5 line implies.
> Plus the field build — 384 Cholesky draws at `0.209 s` ≈ **80 s** — which is noise at this scale
> and is stated so nobody re-derives it.

**AND THE PRE-DECIDED CUT NOW HAS NOTHING TO CUT.** *"If the realised rate lands near 21 s, the
second N1 rung is cut, and it is cut from the EASY rung"* was written when N1 was a separate 1.0
line. **N1 is computed inside every N2 map**, so cutting it saves nothing and would only mean
discarding a reading already paid for. **The cut is not taken and it is not re-decided under time
pressure — it is retired as inapplicable, which is a different thing and is recorded as one.**

### 2. THE THREE ARMS THE MAP DISCARDS ARE THREE OF TASK 5's OWN READINGS

`n2_field_map` builds an `AuditArms` with four `FitResult`s and returns a map made of one of them.
The other three die at the end of the call, and **each is a reading this task is otherwise short
of:**

| discarded arm | what it answers | why it cannot be got more cheaply |
|---|---|---|
| **N1** | *"N1's arm is present and its cost is within the spread Task 0 measured"* — the plan's fourth assertion | there is **no other N1 in the driver**; the only alternative is a second `run_arms` call, which is a second N1 at a full arm's price |
| **COLD** | **Task 0's third reading, still open and owned by Task 4**: does `run`'s fit **phase** cost more per unit work than a bare `fit`? | the driver's cold `run` store and this arm are the **same 384 fits by two paths**, and iterations are deterministic, so the comparison is **bit-exact and free** |
| **WARM** | the audit's own invariant — *"the `warm` arm must reproduce pass 2's store bitwise at the audited points"* | **nothing has ever checked the driver's REBUILT warm array against the one pass 2 actually used.** N1 and N2 are displacements **from that array**, so if the rebuild is wrong every arm in every 2d report is keyed to a warm start no run ever made |

> **THE THIRD IS THE ONE THAT WOULD BE EXPENSIVE TO FIND LATE.** `run_rung` rebuilds the warm array
> through `coarse_ok` / `source_map` / `read_warm_starts` because `run_two_pass` does not expose
> the starts it used. **That is the right construction and it is unverified**, and a silent
> disagreement would not look like an error — it would look like a smear.

### 3. CRITERION 8 SAYS EVERY RUNG AND E2's FACTOR PRICED TWO

Exit criterion 8 is *"every smear width is reported beside the width N2 produces at the same
rung"*, and E2's own deliverable table says the maps are consumed **at every rung**; **the budget
line beneath it counts `2 rungs × 1.0`.** The shipped driver runs the map at all three. **(a5)
across documents, at a number the budget depends on** — and the two readings differ by 4.0 factor
points once finding 1 is applied. **Criterion 8 wins on precedence** (it is the specification of a
reading; the factor is an estimate of a cost), so the map runs at three rungs and the factor moves.

### 4. THE N2 MAP'S SEED IS THE FIELD SEED, AND `config.audit.seed` IS WHERE IT LIVES

`run_rung` passes its own `seed` — the field's draw seed — to `n2_field_map`, whose docstring says
the argument is **`config.audit.seed`, "Not `Config.seed`"**, the exact trap 2c Task 6 recorded.
`fields.write_config` writes no `[audit]` section, so **`config.audit.seed` is 0** on every
benchmark config while the map is keyed on `20_260_830` or whatever the caller passes.

> **THE CONSEQUENCE IS EXIT CRITERION 9**, *"the N2 map and the audit's N2 arm agree at every
> shared point"*: two `run_arms` calls at two different seeds draw **different directions**, so the
> criterion fails at Task 9 for a reason that has nothing to do with either instrument. **And the
> repair invalidates any report committed before it**, because the map's values move with the key.
> **So it is taken BEFORE the 8-hour run, not after** — the whole argument for a pre-flight
> existing.

### 5. E6's UPPER REFUTATION CLAUSE NAMES A CEILING THAT DOES NOT EXIST ON THIS FIELD

*"Saving at any rung ≥ the `self` ceiling → the warm arm is reading its own answer back."* **There
is no `self` arm in `src`.** `Arm` is `WARM / COLD / N1 / N2`, and the `94.53% ± 0.14%` in the
figures table is **2c's fixture, at 40.79 cold iterations per point**, against this field's 24.4 —
**so quoting it here is a comparison across fixtures, which is (j5) at the one clause whose job is
catching a spectacular-looking defect.**

> **AND THE ARM IS THE CHEAPEST IN THE DESIGN, WHICH IS WHY THIS IS NOT A BUDGET QUESTION.** Its
> input is the cold arm's own output — `FitResult.theta_unconstrained` from the map's own `COLD`
> arm, with `x0_valid` the `OK` mask — and Task 0 measured `self` collapsing to **4–6% of cold**.
> **One extra fit at roughly 5% of an arm, in the same batch and the same session**, converts a
> cross-fixture clause into a same-session one **and** supplies the positive control Task 0's void
> rule demands: *if `self` does not collapse, no cost reading in this run may be quoted.*
>
> **THE STRUCTURAL HALF IS FREE AND IS TAKEN AS WELL**, because it catches the named defect
> exactly: **no FINE point's source may be itself.** D12 gives coarse points themselves and nobody
> else, so a `source_map` handing a fine point its own index is the defect the clause describes,
> readable off `SourceMap.index` with no fits at all. **The two are not redundant** — one catches
> the map, the other catches everything else that could make warm look like self.

### 6. THE SAVING THE REPORT CAN EXPRESS OMITS PASS 1, AND `1/64` IS `1/48` ON THIS GEOMETRY

`RungReport.iterations` carries `cold_per_point` and `warm_per_point`, and the warm figure is
`iteration_count(warm_store)` — **pass 2's store.** D11 gives pass 1 **its own** store, so the
saving computed from the report alone is **pass 2 against cold, with pass 1's fits free.**

**And the coarse fraction is not `1/64`.** At `stride = 8` on `32 × 12` the coarse indices are
`{0,8,16,24} × {0,8}` — **8 points of 384, `1/48` = 2.08%**, not the `1/k² = 1.56%` E2's arithmetic
assumed. **The gap is small and the point is not its size:** the budget's 2.016 and the saving's
denominator are the same quantity spelled twice, and only one of them was multiplied out.

> **SO THE SAVING IS REPORTED TWICE, BOTH NAMED**: `pass 2 against cold`, and **`(pass 1 + pass 2)
> against cold`, which is the one a reader means by "the saving".** Both come from
> `fields.iteration_count` on the two stores, so neither is a new instrument.

### 7. THE WIDTH PREDICTION HAS A GEOMETRIC MECHANISM, IT IS ONE-SIDED, AND THE ESTIMATOR IS ANCHORED AT THE BOUNDARY PAIR

**The boundary index is 16 and 16 is itself a coarse index** — `{0,8,16,24}` — so **coarse row 16
is the first row of region B** and it is the nearest coarse source for the **A-side** rows nearest
the step. Rows **13, 14, 15** are 1–3 cells from row 16 and 5–7 from row 8, so their warm start
comes from **across the step, in the wrong family**; row 12 is equidistant and its source is a
tie-break. **On the B side there is no such pull at all**: rows 17–23 source from 16, which is
their own regime. **The predicted smear is one-sided, on the A side, and about 3 cells wide.**

> **AND `smear_width` SEEDS ITS RUN AT `(boundary_index - 1, boundary_index)` = (15, 16)**, growing
> outward only from a seed that is itself over the majority threshold. **A smear that does not
> touch row 15 or row 16 is invisible by construction** — width 0, reported at the floor. Rows
> 13–15 include 15, so the mechanism above is exactly the case the estimator can see; **this is
> stated because it is also how a real one-sided artifact displaced by one cell would read as a
> null.**

**THE N2 FLOOR IS EXPECTED TO BE ELEVATED IN THE SAME PLACE, AND THAT IS THE ARM'S WHOLE POINT.**
N2 displaces the cold start by **that cell's own warm/cold distance**, which is **largest exactly
where the warm source is from the other regime** — near the boundary. **So the interpretable
quantity is warm's width against N2's width at this rung, never against zero and never against
cold**, and cold's own width is a third number that is not a floor for either.

### 8. THE SAVING'S BAND COMES FROM D1's REATTRIBUTION, AND IT PREDICTS A SMALL NUMBER

D1's 2026-08-30 amendment reattributes the saving's climb to **cold-start difficulty** rather than
to coherence, on 2c's own `random` arm:

| 2c's `N` | cold iterations/point | `warm` saving |
|---|---|---|
| 96 | 28.27 | **+7.80%** |
| 384 | 35.32 | +31.73% |
| 630 | 40.79 | +42.28% |

**2d's field runs at 24.4 iterations per point at `N = 630` — below 2c's SHORTEST fixture**, where
the saving was 7.80%. **The curve predicts a small saving here, possibly zero**, and the amendment
says so in as many words: *"a near-zero saving there is what this curve predicts."* **The
prediction is therefore a band and not an ordering** — there is one rung, so there is nothing to
order — and E6's monotonicity closes at Task 7 with three points, where an ordering is what was
predicted. **The clean smoke run had warm ABOVE cold** (52.23 against 51.96 iterations per point);
no magnitude transfers from a 26 × 2 fixture at `n_time = 24`, but it is not evidence for a large
saving either.

### 9. THE COST BLOCK IS COMPARABLE TO THE BUDGET ONLY AT THE THREAD SETTING THE RATE WAS MEASURED AT

`13.15` and `11.20–11.38 s/point/arm` were all measured under **`threadpool_limits(1)`**, in
`phase2d-field-harness.py`. **The driver's `run` takes its thread budget from the config**, so an
unpinned Task 5 run produces a `seconds_per_point` that is **not** the budget's quantity, and the
report's own *"a run finishing early is the bound behaving"* sentence would then be read over a
number that is early for a different reason. **The setting is pinned and recorded in the verdict**;
it costs nothing, and the alternative is a cost block that cannot be compared to the only figure
anyone will compare it to.

### 10. THE HOST QUIET CHECK WOULD GET ITS SECOND SPELLING HERE

`quiet_check()` — idle 20 s, `loadavg[0] < physical_cores - 1`, **gating** — lives in
`phase2d-field-harness.py` and has one home. **Task 5 is 2d's third harness and the first that
would copy it**, and (j9)'s worst instance in this sub-phase was an instrument block that was
itself a copy. **It is promoted into `src/metamer/bench/` with a test**, so the gate has one
implementation and the two harnesses that already exist can be pointed at it rather than diverging
from it.

### 11. WHAT COSTS NOTHING AND IS CHECKED ANYWAY

- **The easy rung's cold iterations reproduce criterion 17's committed number.** The 2026-08-30 and
  2026-08-31 runs both measured `2340` iterations over the 96-point subgrid, mean `24.375`, sd
  `1.630`, min–max `21–28`, `287/288` cells OK, at `seed = 20_260_830`. **The cold store holds
  every point, so the same 96 are extractable from it** — and the comparison is bit-exact because
  iterations are deterministic. **So Task 5's field seed is `20_260_830`**, or the check is
  unavailable for no gain.
- **Memory is not a question at `B = 384` and it is worth one line rather than an assumption.**
  `run_arms` fits the whole field as **one batch, outside the tiling path**; 2b measured criterion
  7 failing above roughly `B = 1500`, and Task 0 measured this geometry at **one tile**, so the
  batch is well inside a bound that has been measured rather than assumed.
- **Every arm in one session, interleaved by construction**, because they are all inside one
  `run_rung` call — which is what the driver was built for and is not a thing Task 5 arranges.

### DEVIATIONS FROM THE BRIEF, STATED RATHER THAN ABSORBED

**THE HANDOFF SAYS TASK 5 IS A CALLER AND NOT A BUILDER, AND THREE OF ITS OWN ASSERTIONS CANNOT BE
MADE BY A CALLER.** The changes below are surgical and each is tied to an assertion the brief
requires or to an artifact the run would otherwise invalidate. **None of them is a second gate**:
`require_clean` stays the only across-rung gate and the ordering inside `run_rung` stays the
within-rung one.

| change | why it is not optional |
|---|---|
| `n2_field_map` **returns the arms it already computed** (or their per-arm iteration totals and selection maps) | finding 2 — the plan's fourth assertion has no other source, and two of the three cross-checks are otherwise unavailable at any price below a full extra arm |
| the benchmark config **writes `audit.seed`** and `run_rung` **passes `config.audit.seed`** to the map | finding 4 — exit criterion 9 cannot pass otherwise, and the repair after the run would invalidate the report the run exists to produce |
| a **`self` arm** at this rung, from the map's own cold `theta_unconstrained` | finding 5 — E6's upper clause names it, it is ~5% of an arm, and it is Task 0's void control |
| `quiet_check` **promoted into `src/metamer/bench/`** | finding 10 — otherwise it is copied, which is (j9) |

**AND ONE WORDING CORRECTION IN THE BRIEF ITSELF.** *"N1's arm is present and its cost is within
the spread Task 0 measured"* — **Task 0's spread is in ITERATIONS** (`N1/cold = 1.0017`, never
outside `[1.0000, 1.0026]`, six repeats over two runs), and this box's wall clock has now been
shown three times not to hold still. **The reading is the iteration ratio; the seconds are reported
and never compared.**

**WHAT TASK 5 DOES NOT DO.** It does not retune the easy rung — **a retune is a new rung with a new
name**, and the easy rung's numbers are a floor and a demonstration and are never quoted as a
magnitude. It does not move `RUNGS`, `PUBLISHED_TILE_SIDE`, `HEADROOM_FRACTION`,
`resident_bytes_per_series`, `output_slot_bytes`, `SVD_CHUNK_SERIES` or `ALGORITHM_VERSION`, and it
re-cuts no exit-criterion verdict. It does not read anything downstream until `require_clean`
returns.

---

## Plan Task 5b — the difficulty rung, audited before any value is chosen (2026-09-01)

> ## SUPERSEDED 2026-09-03, AND KEPT WHOLE SO THE ARGUMENT STAYS VISIBLE
>
> **This entry audits a brief whose lever was wrong.** The difficulty was the symptom of a defect
> in the field builder, not a setting of the noise floor, and everything below about `white/sigma`
> is the retired route. **Its findings 1 and 2 are still measurements and still hold**; what does
> not hold is the conclusion they were pointing at. **The current entry is
> [the 2026-09-03 one](#plan-task-5b--the-difficulty-rung-re-audited-on-the-corrected-builder-2026-09-03)**,
> and one sentence in finding 5 below is false — corrected in place, there.

**THE BRIEF** is one rung, not a sweep, taken after Task 5's null: **is there a difficulty at which
the artifact appears?** If yes, the audit is demonstrably an instrument and 2d has its positive
control. If no, that is a much larger finding about warm-starting and it belongs beside D1. **Three
constraints came in with it:** the rung's target is **2c's difficulty (40.79 cold iterations per
point), not more contrast**; the lever is **named before values are chosen**; and it is a **new
rung with a new name** — the easy rung is not retuned, because the three shipped rungs and their
null are what make the new rung's contrast interpretable.

**FIVE FINDINGS. The first says the lever the sweep has been moving is not one, and the second
names the one that is — both measured rather than argued.**

### 1. `Δ` IS MOSTLY AN AMPLITUDE RESCALE, AND A CONCENTRATED LIKELIHOOD IS INVARIANT TO IT

`build_field` computes `parameters = factor × BASE`, so a single factor multiplies `sigma`, `rho`
**and** `white` together. **`white/sigma` is therefore constant everywhere on every rung by
construction**, and at `contrast = 3` region B is `(2.5, 2.0, 1.0)` against region A's
`(1.0, 0.8, 0.4)` — the same series, 2.5× larger, on a 2.5× longer timescale.

> **MEASURED, 8 series at `N = 630`, the shipped candidate set and the shipped `fit`:**
>
> | setting | `rho` in samples | iterations/point | s/point |
> |---|---|---|---|
> | region A, as the rungs build it | 9.4 | **23.62** | 13.70 |
> | **the same data × 2.5 — pure amplitude** | 9.4 | **23.50** | 14.49 |
> | region B, what `contrast = 3` produces | 23.6 | 24.62 | 16.47 |
> | `rho` 0.8 → 0.30 yr — 2c's own region B | 3.5 | 24.75 | 16.78 |
> | **`white/sigma` 0.4 → 0.8** | 9.4 | **28.75** | **26.48** |
> | both together | 3.5 | 26.00 | 26.13 |
>
> **Amplitude is free** — 23.50 against 23.62 — as a concentrated likelihood requires. **`rho` in
> samples is worth about one iteration** across a factor of 6.7. **The noise floor is worth five**,
> and it nearly doubles the seconds.

**SO THE THREE RUNGS BEING INDISTINGUISHABLE IS A PROPERTY OF THE LEVER, NOT A COINCIDENCE**
(24.375 / 24.333 / 24.396). **The sweep held difficulty fixed and moved an amplitude**, and no
value of `contrast` on this construction could have done otherwise. That is the sharpest available
answer to *"why did the easy rung produce nothing"*, and it is recorded here rather than in the
new rung's verdict because **it is a fact about the existing three.**

### 2. THE LEVER IS THE NOISE FLOOR RELATIVE TO THE CORRELATED AMPLITUDE, AND 2c's OWN FIXTURE SAYS SO

**2c's field IS recoverable — `warmstart-spike-harness.py` is in the tree** — and comparing its
`true_params` against `fields.BASE` puts a number on the gap that the 40.79-against-24.4 comparison
could not:

| | 2c region A | 2c region B | 2d region A | 2d region B (`contrast = 3`) |
|---|---|---|---|---|
| family | matern32 | matern12 | matern32 | matern12 |
| `sigma` | 1.0–1.5 | 0.7–1.1 | ~1.0 | ~2.5 |
| `white` | 0.4 | **0.5** | 0.4 | 1.0 |
| **`white/sigma`** | 0.27–0.40 | **0.45–0.71** | **0.40** | **0.40** |
| `rho` in samples | 9.6–24 | **3.6–7.2** | 9.4 | 23.6 |

**2c's hard regime is noisier AND shorter-correlated; 2d's is neither, and cannot be, because the
one factor moves `white` with `sigma`.** The probe says the noise floor is what the optimizer
feels. **So the lever is `white/sigma`, and it is a new field parameter rather than a new value of
an existing one** — the existing ones cannot express it.

> **AND A CORRECTION TO A CLAIM THIS SUB-PHASE HAS REPEATED:** `fields.py`'s docstring says *"the
> warm-start spike's coherent field lived in a script that is not in the tree"*. **The script is in
> the tree**, at `docs/superpowers/notes/warmstart-spike-harness.py`, and its field is fully
> specified there. What was true is that the field was **not in `src`**, so criterion 12 could not
> be re-measured **on the shipped mechanism** — which is the argument that actually mattered.
> **Corrected at the docstring, with this task's code** — the pre-flight is docs-only and the
> correction is a `src` edit, which ships under the same sweep as the new rung parameter. It is
> recorded here because a reader who checks the stronger claim finds it false and then doubts the
> argument that rests on it.

### 3. TWO CONSTRAINTS BIND THE RUNG'S VALUE AND THEY ARE SOLVED TOGETHER — (a5b)

*"Land near 40.79 iterations"* and *"fit what is left of the 30 h ceiling"* are constraints on **one
number**, and the probe says they pull against each other: **at `white/sigma = 0.8` the seconds
nearly double while the iterations rise 22%.** One rung is `6.016 arms × 384 points`, so it costs
**10.2 h at the easy rung's 13.98 s/point and 17.0 h at 26.5 s/point.** With 10.18 h already spent,
**the remaining ceiling is 19.8 h.**

**A THIRD CONSTRAINT IS EASY TO MISS AND WOULD VOID THE RUNG: THE BASELINE MUST STAY UNDER A HALF.**
A noisier field makes the two Matérn families harder to tell apart, so misclassification rises
everywhere — and **a baseline disagreement rate above 1/2 is the second cause of a firing interior
null**, which invalidates the *subject* rather than the estimator and would stop the rung before any
width was read. **The calibration therefore measures misclassification at every setting, not only
iterations**, and the value is chosen subject to it.

### 4. THE CALIBRATION IS A SPIKE WITH ITS OWN PREDICTIONS, AND IT PRICES THE RUNG AS WELL AS CHOOSING IT

**D2: Task 0's method is the template for every remaining premise that is unmeasured.** The spike
sweeps `white/sigma` over a small ladder at `N = 630` on both families, and reports **iterations
per point, seconds per point, and the misclassification rate against the truth** at each. It buys
three things at once:

- **the value**, chosen as the highest difficulty whose baseline stays well under a half and whose
  implied rung cost fits the remaining ceiling;
- **the rung's price**, from measured seconds at the chosen setting rather than from the easy
  rung's rate — which the same probe has already shown does not transfer across difficulty;
- **a third point for the cost model**, which currently has two and therefore cannot tell a line
  from a curve — D2's own reason for a three-fixture lever, and the rule Task 0's retired
  `2.43 + 0.324 × iterations` was retired under.

### 5. WHAT THE RUNG MUST NOT DO, AND ONE THING IT MUST CARRY

**It does not retune `easy`, `middle` or `hard`**, and it does not change `BASE`, `WITHIN_REGIME_RANGE`
or the geometry — the three shipped rungs' null is the comparison that gives this rung its meaning,
and editing any of them destroys it. ~~**The new parameter is per-rung and defaults to the shipped
value**, so every existing rung's bytes are unchanged and a test asserts they are.~~

> **THE STRUCK SENTENCE IS FALSE, AND IT WAS LOAD-BEARING. Corrected 2026-09-03.** No test asserted
> it. `tests/test_bench_fields.py` compared `FieldTruth.parameters` — the truth array — which a
> signal added after the draw leaves untouched, **so the cited guard would have printed green
> through exactly the change it was cited against.** This is (a0)'s register **at a citation rather
> than at a value**: the existence of a mechanism was asserted instead of checked. The guard now
> exists and is at
> `test_the_shipped_rungs_fields_are_the_ones_their_recorded_numbers_describe`.

**AND ITS `sources` MUST SAY WHAT IT IS**: chosen by us, against a calibration, to sit near 2c's
measured difficulty — **not a claim about the ocean**. The middle rung's slot is the recorded
example of what happens to a rung whose provenance is left to a reader.

---

## Plan Task 5b — the difficulty rung, re-audited on the corrected builder (2026-09-03)

**THE BRIEF**, as amended: one rung on a builder whose missing signal has been repaired, targeting
2c's difficulty, read against the three shipped rungs' null. **The lever is the signal.** The
decision behind it — signal FIXED for every field, three rungs NOT re-run — is in `PROGRESS.md`,
and every measurement it rests on is in [`phase2d-signal-defect.md`](phase2d-signal-defect.md).
**Neither is restated here.**

**EIGHT FINDINGS. The first is a citation in my own brief that named a mechanism which did not
exist, and the constraint built on it was load-bearing.**

### 1. THE BYTE GUARD THE CONSTRAINT RESTS ON DID NOT EXIST — (a0) AT A CITATION

The brief said *"every existing rung's drawn bytes stay identical — a test asserts it."* **No test
asserted that.** `tests/test_bench_fields.py::test_one_rung_twice_is_identical_and_two_rungs_differ`
compares `FieldTruth.parameters`, and `FieldTruth`'s own docstring says so: *"This is what the tests
assert on."* Nothing in the suite compared a drawn series or a stored value.

**A signal added after the draw leaves `parameters` untouched**, so the cited guard **prints green
through exactly the change it was cited against**. (a0)'s sixth register — a check that never read
the file prints the same word as one that did — **arriving at a citation rather than at a value**:
the existence of a mechanism was asserted instead of checked.

**The guard was written, run green on the unchanged builder, and committed BEFORE the builder
moves.** That ordering is the finding's other half: **a guard written after the change is a guard
fitted to the outcome.**

### 2. DRAWN NOISE AND FIELD VALUES SEPARATE, AND THE VERSION MARKER FIRES

`build_field` draws `multivariate_normal(zeros, covariance)` per cell under
`default_rng([seed, iy, ix])`. **A trend added after that draw leaves the RNG stream
bit-identical** and **moves every stored value on all four rungs.** The two objects are not the
same, and an assertion over the first says nothing about the second.

**So the marker is a FIELD-CONSTRUCTION VERSION, not a signal flag** — and the reason is that the
signal is not the first thing to move the drawn bytes. **The Cholesky change is a prior instance of
the same class**, and its call site already records that a later change there invalidates every
committed rung report. A marker narrow to the signal would not cover it; a construction version
covers both and any third.

**Version 1 is defined, and the Cholesky question is CHECKED rather than assumed.** `ed8f39b`,
**2026-08-30 19:03**, introduced the Cholesky draw. The earliest committed rung measurement is
`64e4514` / `d2c57bc`, **2026-08-31 12:01 / 12:59** — **after it.** So **the Cholesky change
predates every committed rung number and is part of what version 1 already is**; version 0 is the
SVD draw and no committed number depends on it, which is what the call-site comment claimed and is
now verified rather than believed.

**AND THE MARKER'S TEST IS REACHABILITY, NOT LABELLING:** can the three shipped rungs' exact fields
be rebuilt after the change? **The guard at finding 1 is what answers it**, and a marker that
labels without making version 1 constructible is insufficient whatever it is called.

### 3. THE SIZING UNIT WAS AMBIGUOUS, AND THE TWO READINGS BUILD DIFFERENT FIELDS — PER-CELL SIGMA

`parameters = factor × BASE`, and `factor` **steps at the boundary**, so *"16 sigma"* means one
thing per cell and another against a field-level `BASE`.

- **`BASE`-scaled** puts **rise/sigma** — the only part of the signal the fit can see — **at a step
  across the boundary**, and difficulty steps with it. **That is a difficulty step on the boundary
  whose only step is supposed to be in the covariance.**
- **Per-cell-scaled** gives every cell the same rise/sigma. **Difficulty is uniform**, and it is the
  value the probe measured, since the probe measured at `BASE` alone.

**PER-CELL, AND THE ARGUMENT IS THE PROJECT'S OWN MEASUREMENT RATHER THAN A PREFERENCE.** Amplitude
is free under a concentrated likelihood — E5's measured pair — so the fit responds to rise/sigma and
not to rise. **Per-cell adds no structure in any quantity the fit can see; `BASE`-scaling adds
one.** The apparent objection, that per-cell makes the mean's slope jump at the boundary, is
answered by the same measurement: the absolute slope jumps, and so does sigma, and the fit sees only
the ratio.

**The second argument is as strong: per-cell keeps the field `dimensionless truth × BASE`, which is
what the construction already is.** `BASE`-scaling bolts a dimensional term onto a scale-free
construction, and **that asymmetry is where a later reader's confusion lives.**

**AND THE CONSEQUENCE IS THE CHECK THAT THE SWEEP'S RETIREMENT WAS NOT PREMATURE:** `Δ` still moves
nothing the fit can see, **even corrected**. So the corrected builder does **not** resurrect the
rung sweep, and **one rung remains the right shape** — the decision agreeing with the measurement
rather than being strained by it.

### 4. THE TWO CONSTRUCTIONS SHARE A FIT IDENTITY

`batch/geometry.py` states it at the top: the fingerprint is over **the type, not the values**, and
*"a value edit at fixed geometry does not move it."* **So a signal-free and a signal-bearing field
at one rung and one geometry share `geometry_hash`, hence `fit_hash`.**

**Correct for the production package** — data lives at a URI and identity covers geometry —
**wrong-shaped for a constructed fixture, whose construction IS part of its identity and is
unhashed.** The rung must not use fit identity to tell the two constructions apart, and **any resume
or reuse path keyed on it can cross them silently.** Promoted to the gotchas, because it is not
5b's alone.

### 5. THE INSTRUMENT BLOCK NAMES THE TERMS THE CONFIG FITS, NOT THE TERMS THE BUILDER DRAWS

`report.instrument_block` emits `"signal_terms": list(fields.SIGNAL_TERMS)` — `constant, trend`,
which is **the model**. **The committed easy-rung report carries exactly that**, so **three
committed reports already read as though their fields carried a constant and a trend.** The defect
wearing the report's clothes.

**The drawn signal needs its own NEW key, never a redefinition of `signal_terms`** — redefining it
would **reinterpret** three committed artifacts where the point is to **distinguish** them.

### 6. (c5) AT THE REPORT'S OWN COMPLETENESS CHECK

`tests/test_bench_report.py` checks **key presence over a hand-written enumeration**, so a new key
is not required by it — the exact *"gate over a set that can grow"* shape. **The new key needs its
own assertion**, and the enumeration needs the note.

**And a fact rather than a finding: no test reads any committed 2d rung report.** The artifact
register is a documented practice here, not an installed mechanism; it is owed at Task 9. **The
guard at finding 1 is the first test to read one**, because it needs the seed.

### 7. THE TARGET HAS TWO SPELLINGS FROM TWO INSTRUMENTS — THE RUNG AIMS AT 43.94

The plan aimed at **40.79**, recovered from 2c's own JSONL on **2c's own optimizer path**. The probe
measures 2c's fixture at **43.94** under the **shipped `fit`**. Both dated, both measured, about
0.8 sd apart — **(j5): a second instrument is a cross-check only if it measures the same quantity
under the same conditions**, and these do not.

**THE RUNG AIMS AT 43.94, AND ITS PRE-DECIDED STOP IS STATED RELATIVE TO 43.94 IN THE PREDICTIONS
FILE, EXPLICITLY** — the stop was written against *"2c's difficulty"* and that phrase now has two
referents. **40.79 IS NOT DELETED**: it stands as 2c's own reading on its own path, and **the gap
between the two is a recorded fact about the two instruments, not a discrepancy to reconcile.**

**AND THE UNIT WAS CHECKED BEFORE THE COMPARISON WAS TRUSTED: per-point iterations are comparable
only at equal `M`.** Both readings are at `M = 3`, so this one is safe — **but it was not before the
candidate set grew from two to three**, and the field verdict's own per-point/per-cell split says
the third candidate is worth roughly 1.5× on its own.

### 8. THE SEED HAS FOUR SPELLINGS, NO HOME IN `src`, AND CRITERION 17's ARTIFACTS DO NOT RECORD IT

`20_260_830` appears as `FIXTURE_SEED` in the spike harness, as `FIELD_SEED` in the easy-rung
harness, and as **two bare literals** — and **nowhere in `src`.** A quantity with one authoritative
source has four spellings and no source.

**Worse: criterion 17's own artifacts record geometry, candidates and signal terms but NOT the
seed.** So **the three-rung ladder's numbers describe fields that cannot be rebuilt from their own
artifact** — only from a harness literal. **The only committed artifact carrying the seed is
`phase2d-easy-rung-report.json`**, which is why the guard reads it from there rather than adding a
fifth spelling. **Consolidating the seed into `src` is owed with the builder change**, and is not
done here because this commit does not touch `src`.

### THE GUARD, AND WHY IT HAS TWO ASSERTIONS OF DIFFERENT KINDS

One test, **marked `slow`**, at the shipped geometry and `n_time`, over all three rungs at the
recorded seed. **Not a reduced-geometry twin** — that would pin a field nobody measured and give the
same guarantee a second spelling. **CI runs `-m "not machine"`, so `slow` runs there**, and it cost
**5 m 17 s** for the three rungs.

| assertion | what it catches | how its expected value was fixed |
|---|---|---|
| the stored `sla` hashes to its committed digest, per rung | any builder change that moves a shipped rung's field, **including one invisible to every other test in the suite** | a **pin**, frozen from the builder and committed. Its independence is that it is never recomputed |
| the field carries **no trend** — median per-cell rise over the record, in that cell's sigma, **< 1.0** | a signal landing in version 1 **by accident**, where updating the digest to match would ratify the bug. **A trend cannot be pinned away** | an **argument**: at `rho = 0.8 yr` over 53.4 years there are ~66 effectively independent samples, so a fitted rise has se ≈ 0.43 sigma and a median near 0.67 of that. **Set before the run; the three rungs measure 0.42–0.47** |

**BOTH WERE PROVEN TO BITE BEFORE BEING RECORDED AS GUARDS** — (e2), prove the mutant differs.
Against a version-2 field built exactly as specified (trend only, 16 sigma per cell, added after the
draw): **the digest differs, and the median rise reads 15.93 against the 1.0 limit.** The mutant was
constructed and measured, not argued.

**ONE KNOWN FAILURE MODE, STATED SO IT IS NOT MISREAD.** The digests are exact bytes from a Cholesky
factorisation, so a change of BLAS, numpy or platform can move them **without the builder moving**.
**That is a different finding, not a reason to loosen the assertion** — it would mean the shipped
rungs are not rebuildable off this machine, which is precisely what a reachability guard exists to
surface. The failure message names both causes so the next reader looks at the right one.

### DEVIATIONS FROM THE BRIEF, STATED RATHER THAN ABSORBED

- **The brief cited a guard that did not exist** (finding 1). The one that would have been absorbed.
- **The brief's sizing unit did not determine the field** (finding 3); a choice was owed.
- **The brief's target number had two spellings from two instruments** (finding 7).
- **The brief's new parameter was described as per-rung**; the decision makes the signal **fixed**,
  a property of the builder, and the rung's lever stays whatever the rung's lever is.

---

## Plan Task 5b — the rung itself, audited before the measurement (2026-09-04)

**THE BRIEF**, as it now stands: one rung on field construction version 2, at 2c's difficulty, read
against the three shipped rungs' null on signal-free fields. **The predictions are committed before
either run, at
[`phase2d-difficulty-rung-predictions.json`](phase2d-difficulty-rung-predictions.json), and are not
restated here.** The builder audit is [the 2026-09-03 entry](#plan-task-5b--the-difficulty-rung-re-audited-on-the-corrected-builder-2026-09-03).

**FOUR FINDINGS, AND THE FIRST RETIRES A CONSTRAINT THAT WAS CORRECT WHEN IT WAS WRITTEN.**

### 1. THERE IS NO NEW RUNG NAME, AND ASKING FOR ONE WOULD PRODUCE A SECOND SPELLING

The constraint said **a new rung with a new name**, and it was right for the lever it was written
against: a noise-floor rung needed parameters the existing rungs could not express. **The lever is
now the SIGNAL, and the signal is FIXED for every field** — so a rung carrying the easy rung's own
`(coherence_length, contrast)` would differ from `easy` in **nothing**, and at the same seed would
draw a **byte-identical field under a different name**. That is (j9)'s second spelling, arriving
through a constraint rather than through carelessness.

**WHAT DISTINGUISHES THIS MEASUREMENT IS THE CONSTRUCTION VERSION, AND IT IS A BETTER IDENTIFIER
THAN A NAME WOULD BE** — it names what actually differs, it is in the instrument block, and it is
the thing the byte guard tests. **The constraint's purpose is untouched:** `easy`, `middle` and
`hard` are not retuned, `BASE`, `WITHIN_REGIME_RANGE` and the geometry do not move, and the three
shipped rungs' fields are still rebuildable at version 1.

### 2. THE CONFOUND IS REAL, AND THE RUNG CANNOT ANSWER IT — SO A PROBE RUNS FIRST

**The signal does two things and only one was predicted:** it raises iterations, and on the small
fixture it moved convergence from **93/96 to 96/96**. So a null at 43.94 has two readings — no
hysteresis at 2c's difficulty, or **a better-conditioned field with less to be hysteretic about** —
and the pre-decided stop was written as though only the first existed.

**THE RUNG RUNS VERSION 2 ALONE, SO NO COLUMN ADDED TO IT CAN SETTLE THIS.** The comparison needs
both constructions, interleaved in one session; that is a probe, not a column. **And the version 1
rung cannot supply the other half from the record:** its committed report carries iterations, ratios
and smears and **no outcome distribution at all**, and its store was temporary. **It costs about 11
minutes against the rung's 13.2 h**, so it runs **first** — if conditioning has moved, that is known
before the thirteen hours, not inside their report.

**IT IS A READING WITH ITS OWN CLAUSE, NOT A CAVEAT.** C1 and C2 fire, and when they fire **the
pre-decided stop is suspended** and a null is reported as two candidate readings rather than one
conclusion.

### 3. `hessian_cond` EXISTS AND IS NOT IN THE STORE, WHICH DECIDES WHERE THE READING IS TAKEN

`FitResult.hessian_cond` is the number the `DEGENERATE_HESSIAN` verdict is taken on, recorded on the
result rather than recomputed. **It is not written to the store**, so a store-mediated arm cannot
report it, while `bench/arms.py` — which imports `FitResult` and `fit` directly — can. **This is why
the κ half of the discriminator is in-process and the outcome half comes from the store**, and it is
a fact about where each reading is available rather than a preference.

**NaN IS UNDEFINED AND HAS TWO CAUSES** — no Hessian, or one that is not positive definite — so NaN
fits are **counted and reported**, never dropped into a median. A median over the fits that happened
to be well-behaved would answer a question nobody asked.

### 4. THE ARTIFACT MUST NAME ITS OWN FIELD, AND THE DEFECT IT WOULD INHERIT IS IN THE TREE

**Criterion 17's artifacts record geometry, candidates and signal terms and NOT the seed**, so the
three-rung ladder's numbers are rebuildable only from a harness literal. **The version marker does
not fix that for them** — it makes version 1 constructible; it does not make those artifacts
self-describing. **This rung records the SEED and the CONSTRUCTION VERSION**, or it starts life with
the same defect.

### WHAT IS CHECKED BEFORE THE RUN AND COSTS NOTHING

**The byte guard runs against version 1 first** — that is the marker's test, and a guard run after
the measurement is a guard fitted to the outcome. **The quiet-host check GATES.** **Arms are
interleaved within one session.** **Cost is priced in seconds off the named 16-point fixture**, with
iterations kept as the reproducible unit and converted late.

### DEVIATIONS FROM THE BRIEF, STATED RATHER THAN ABSORBED

- **No new rung name** (finding 1). The constraint's purpose is met by the construction version; its
  letter would have produced a byte-identical field under a second name.
- **The conditioning discriminator is a separate probe that runs BEFORE the rung**, not a column of
  it (finding 2). The rung cannot compare two constructions when only one of them is present.
- **The κ reading is in-process and the outcome reading is from the store** (finding 3), because
  that is where each number exists.
