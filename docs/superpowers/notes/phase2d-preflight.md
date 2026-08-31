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
