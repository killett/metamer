# Phase 2d — the simulated-field benchmark, and the audit's first real numbers

**Status: APPROVED 2026-08-30. TASK 0 IS DONE; TASKS 1–9 REMAIN AND NO PRODUCTION CODE EXISTS
YET.** Ten tasks, seventeen exit criteria
**each naming its reading**, plus 2b's criteria 6 and 7 which **stay FAILED** and 2c's criterion 11
which **stays REDUCED SCOPE**. The single source for this plan's status is this line.
**What each task finds beyond its brief goes in [`PROGRESS.md`](../../../PROGRESS.md)'s *What plan
Task N established*, not here.**

**The design decisions this plan implements are E1–E8** in
[`PROGRESS.md`](../../../PROGRESS.md)'s *Phase 2d brainstorm — settled decisions*. **Nothing below
re-argues one.** Where a task rests on a decision it names it and points there; where it rests on a
magnitude it points at [what 2d's tasks inherit](../../../PROGRESS.md). **A measurement stated
twice has one copy deleted, never reconciled.**

> ## THE STANDING LIMITATION, AND 2d CANNOT LIFT IT
>
> **A simulated field measures the audit's ability to detect an artifact whose magnitude is a
> CONSTRUCTION PARAMETER.** It does not measure whether warm-starting contaminates real altimetry,
> because the field's coherence is **chosen**. **2d establishes that the instrument works and what
> it can resolve. It does not close D1.**
>
> **The named closer is unchanged: a spike on a real gridded product**, same arms, same
> record-length lever. **No 2d result may be written up as though it had closed it** — and Task 8
> is where that is enforced in the artifact most likely to travel without its paragraph.

## What 2d IS, and the section boundary that says so

**2d opens design doc §16.2 item 6 — *"Warm-start hysteresis, on simulated fields"* — and nothing
else in §16.2.** Items 1–5 (selection accuracy, parameter recovery, trend-uncertainty calibration,
misspecification, ML vs REML) **are a sub-phase in themselves and are not 2d's.** Stated here
because without the sentence 2d absorbs a selection-accuracy sweep.

**Items 1–5 belong to PHASE 6 (validation suites), and §17's Phase 6 line claimed item 6 as well
until 2026-08-30.** Q11 assigned item 6 to 2d on 2026-08-11 and the line was never amended; it is
corrected in the design doc with the split stated as a table. **Found by asking who owns item 4**,
which is why Task 8's reservation has to name an owner rather than merely a gap.

**§16.2's own framing settles a question this plan would otherwise have had to:** the
simulation-recovery benchmark is *"slow, stochastic, tolerance-banded… run on demand; in CI only at
small N. Emits a reproducible report."* **So 2d's measurements are a benchmark, not a test.** They
do not run in `pixi run test`; the exit-criteria suite asserts against their **committed reports**.

> **THE SECTION NUMBER WAS WRONG IN THE RECORD UNTIL 2026-08-30 AND IS CORRECTED AT ITS SOURCE.**
> D4's constraint 3 cited **§11.2** for the two fields, the sharp boundary and the smear width;
> §11.2 specifies none of them. Q11's 2d row named the deliverable with **no section at all**.
> Both are amended in PROGRESS.md rather than only noted here. **A deliverable named with no
> section is how the wrong section gets supplied by the next reader.**

## Why this plan has no code fences

Same reason as 2a, 2b and 2c. A fenced block is read as the implementation and stops being
reviewed as a specification; the reviewer checks whether the code is right rather than whether the
behaviour is. **Interfaces appear as signatures only where a later task binds against an earlier
one**, which is a contract rather than an implementation.

## What this sub-phase inherits, and what it found before it started

**2c built the audit and it has measured nothing.** The arms, the strata, the report and the
withholding rules are built and tested; **every one has been run only on fixtures whose coherence
is a construction parameter, at record lengths that do not describe production**, and Task 7's
report ran on **8 live cells with every stratum under the 30-member floor**, so every rate was
withheld. **2d is where the audit becomes evidence rather than machinery.**

| finding | what it changed |
|---|---|
| **§16.2 item 6, not §11.2**, is the two-field spec | the section boundary above, and the corrections to D4 and Q11 |
| **the four-arm audit is an extension of item 6's two arms** | the plan says which arms run at which rung, because **N2's floor is what makes a width interpretable** |
| **the audit's four arms were being multiplied by the sweep for no reason** | E2's re-factorisation. The audit is **one rung's** cost, and at one rung it affords the whole field — which is what the 30-member floor needs |
| **`21 s/point/arm` was measured at `M = 2` and the record did not say so** | the candidate set is named in this plan (Task 1), because `M` sets **both** the price and the stratum count. **Task 0 then found the record also omits the SIGNAL SPEC and the FIXTURE, so the figure is not re-measurable at all** — it is refuted from below at `10.62 s` and the gap cannot be attributed. **(j8) at a cost model** |
| **the 1.7 / 3.0 / 6.7 h lattice figures are TWO-ARM figures** | recomputed and confirmed; the four-arm audit doubles each. Corrected at its source in the 2c close |
| **N1 is cheap in interpretation and full price in compute** | **Measured 2026-08-30: it does** — `N1/cold` iterations `1.0017`, six repeats, two runs. It is **not** in the 12.047 factor, and its two rungs are what the ceiling is sensitive to |

**And one arithmetic failure inside the brainstorm itself, promoted as (a5b).** The audit's
subsample was sized against the compute ceiling and never against the 30-member floor discussed
four paragraphs earlier in the same message. **Two constraints on one quantity, each satisfied in
the section where it was discussed.** The repair was not a compromise but a re-factorisation.

## Standing requirements for every task

- **Run the pre-flight against the task brief before code**, and append the entry to
  [`phase2d-preflight.md`](../notes/phase2d-preflight.md) **before** the task, not after. The
  method lives in exactly one place — [the handoff](../notes/phase1-to-phase2-handoff.md) §1 — and
  is not restated here.
- **`pixi run test` is the full sweep and every end-of-task verification runs it.** `test-fast` and
  `test-ci` are not evidence. **The benchmark runs are not in it**, by E7; what is in it is
  everything that asserts on their committed reports.
- **`git add` a new file before `pre-commit run --all-files`, never at commit time.** `--all-files`
  covers tracked files only.
- **Commit after every task, and check CI after every push.** Red CI is the next task. **One push
  per run**: a second push cancels the run verifying the first.
- **Every new measurement commits its predictions first**, with **refutation clauses in both
  directions** — (i11). **Arms are interleaved within one session, never compared across
  sessions.** **A ceiling arm exists wherever one does.** **The host quiet check runs first.**
- **No task moves `PUBLISHED_TILE_SIDE`, `HEADROOM_FRACTION`, `resident_bytes_per_series`,
  `output_slot_bytes`, `SVD_CHUNK_SERIES` or `ALGORITHM_VERSION`**, and **no exit-criterion verdict
  from 2a, 2b or 2c moves.** 2d adds evidence; it reopens no residency model and re-cuts no
  stratum boundary.
- **Every emitted number carries its rung** (E1 constraint 2), enforced by construction and not by
  convention.
- **Every spike carries Task 0's four**, because all four of its defects were this list's absence:
  **dtype identical on both sides of any comparison · the axis built by `to_decimal_years`, never
  by hand · fixture identity held FIXED across repeats, so a spread measures the machine and not
  the data · the quiet check GATING rather than annotating.**
- **THE PRE-DECIDED CUT, TAKEN 2026-08-30 SO IT IS NOT TAKEN UNDER TIME PRESSURE:** N1 is **held**
  at two rungs. **If the realised rate lands near the inherited 21 s/point/arm, the second N1 rung
  is what gets cut, and it is cut from the EASY rung** — N1's question is live where a magnitude
  is quoted and merely confirmatory where the artifact was built to be large. **Nothing else is
  cut and the field is not shrunk**; its geometry is derived from `k` and from the 30-member floor.

## Task index and dependencies

| # | task | depends on |
|---|---|---|
| 0 | the pricing and lever spike | — |
| 1 | the field builder, and the plausibility rung's sources | 0 |
| 2 | the smear-width estimator, and its interior null | — |
| 3 | the N2 full-field map | — |
| 4 | the benchmark driver and its reproducible report | 1, 2, 3 |
| 5 | the easy rung — the positive control, and the gate | 4 |
| 6 | the plausibility rung — criterion 12, the audit's numbers, OQ21 | 5 |
| 7 | the hard rung — the floor from below, and the monotonicity | 6 |
| 8 | the README figure, and what it is allowed to say | 6 |
| 9 | the 2d exit-criteria suite | all |

**Tasks 2 and 3 are independent of everything and of each other**, and both are falsifiable by unit
test alone on constructed maps with no field and no run. **Task 0 gates Task 1 because a cost
2× the assumed one re-plans the sub-phase rather than delaying it.**

---

## Task 0 — the pricing and lever spike

> **DONE 2026-08-30. THE VERDICT IS
> [`phase2d-spike-verdict.md`](../notes/phase2d-spike-verdict.md)** and the magnitudes are in
> [what 2d's tasks inherit](../../../PROGRESS.md). **Reading 1 refuted from below — `10.62 s` per
> point per arm, not 21 — and the inherited figure is not re-measurable because it never recorded
> its signal spec or its fixture. Reading 2 confirmed: N1 costs a full cold arm. Reading 3
> refused three times and replaced by the run's own phase accounting, which puts everything
> outside the fit phase under 1%.**
>
> **THE BUDGET IS NOW BUILT IN ITERATIONS**, because iterations are deterministic and this box's
> wall clock is not, and **Task 1 carries the gate that finalises it** — see Task 1's last test.
> **Four defects were found and all four were in the instrument; nothing in `src` was wrong.**

**Goal.** Price 2d before it is planned into existence, and measure the two premises the budget
rests on that nobody has measured. **2c's Task 0 was a whole task and it nearly collapsed the
sub-phase; that is the template.** A verdict whose *"no"* is expensive is a formality only if it is
taken after the money is spent.

> **THE PRE-FLIGHT MOVED A READING OUT OF THIS TASK, 2026-08-30, BEFORE ANY CODE.** *"Does `ℓ`
> move the saving?"* needs a field with a coherence parameter, **Task 1 owns the builder, and Task
> 0 runs first** — so measuring it here means building the field **in the harness**, which is
> **exactly the fault that made 2c's criterion 12 unmeasurable** and which 2d's entire budget
> exists to repair. **The check moves to Task 1, on the shipped builder.** The gate survives: the
> two remaining readings need **no field at all**, so they still gate Task 1 on cost.

**Three readings, and predictions committed before the harness runs.**

- **The per-point-per-arm cost through `fit`**, at 2d's candidate set (`M = 2`), at `N = 630`, on
  this machine, today, **with repeats**. The inherited `21 s` is dated 2026-08-29 and is **a claim
  to re-measure**. **It is also two single runs with no spread**, so the refutation clauses below
  are stated against the **measured** spread rather than against round numbers — (i9): a band
  narrower than the machine's own jitter cannot express its condition.
- **N1's cost against cold's.** **Prediction: equal within the measured repeat spread**, because
  `N1_EPSILON` is a displacement the optimizer cannot distinguish from zero, so N1 starts where
  cold starts and converges in cold's iteration count. **This is a NULL, and it carries the
  ceiling arm as its positive control** — see the invariants.
- **The `run`-to-`fit` per-point ratio at short `N`, forced to ≥ 2 tiles.** **The budget's unit is
  measured on `fit` and spent on `run`:** E2's 12.047 factor counts three full-field `run` passes
  and a `run_two_pass`, and only `run_arms` is `fit`-shaped. **`run` adds tiling, store writes,
  assembly and the per-tile barrier.** The overhead is per point and per tile rather than per
  iteration, so it is a **larger** fraction of a **cheaper** fit — **measuring the ratio at short
  `N` bounds it from above at `N = 630`** at a fraction of the cost. **(j6): bound the unmeasured
  region before measuring it.** **The memory budget is forced low enough to produce more than one
  tile**, or the reading covers store I/O and misses the barrier — a complete-looking table with a
  row missing.

**Invariants.**

- **All arms in one session, interleaved.** The stride sweep's spurious 15% came from re-running a
  cold arm across sessions; the cost of getting it wrong here is comparability, not drift.
- **A ceiling arm exists** — `self`, each cell started from its own converged `θ̂`. **It is now
  reading 2's positive control and it is load-bearing:** *"N1 costs what cold costs"* is
  byte-identical in the output to *"the iteration counter is not moving"*, to *"both arms silently
  ran cold"*, and to *"the perturbation never reached the optimizer"*. **If `self` does not
  collapse iterations, no cost number in this spike may be quoted.** (i2), and (i2b)'s note that
  the ceiling arm is the cheapest in the design because its input is the cold arm's own output.
- **The WARM and N2 arms' costs are NOT quoted, and the harness records why.** Reading 2 hands
  `run_arms` a **fabricated** warm array — N1's start depends on the cold start and the epsilon
  alone, so a synthetic warm serves it — which means the two arms that *do* depend on the warm
  array are numbers about a source map that does not exist. **Recorded as unquotable rather than
  emitted for a reader to find.**
- **The host quiet check runs first**, and its reading is in the verdict.
- **The predictions file is committed before the harness runs**, with refutation clauses in **both**
  directions for each of the three. **(i11), which 2c paid for: a one-sided clause could not fire
  when S2 held harder than predicted.**

**Outputs**, following 2c's Task 0 exactly: `phase2d-spike-predictions.json`,
`phase2d-spike-harness.py`, `phase2d-spike-measured.jsonl`, `phase2d-spike-verdict.md`.

**What refutes each reading, and what each refutation costs.**

- *Cost above the inherited figure by more than the measured spread, and high enough to put the
  budget over 30 h.* **The plan is re-costed before Task 1** — by dropping the hard rung's N2 map,
  **not by shrinking the field**, because the field is derived from `k` and from the audit's floor
  and neither is negotiable against a machine.
- *Cost below the inherited figure by more than the measured spread.* **Also a finding**: the
  machine or the candidate set differs from the one the 2c close priced, and **every inherited
  figure in the saving table is suspect for the same reason** — they were measured on that machine
  too.
- *`self` does not collapse iterations.* **The spike is void.** No cost reading is quotable,
  because the instrument has not been shown able to tell two arms apart by cost.
- *N1 costs materially less than cold.* The prediction is wrong and **the reason matters** — it
  would mean the optimizer's first step is not scale-invariant the way `fd_step` assumes, which is
  a finding about `optimize_series` and not about the budget.
- *N1 costs materially more than cold.* The perturbation is doing something other than displacing
  the start, and **the N1 arm's whole reading is in question** — including in 2c's four-reading
  table, where N1 non-zero is read as *"the surface is deciding"*.
- *The `run`-to-`fit` ratio bound comes back above ~1.15.* **The 27.0 h figure is not an upper
  bound**, E2 is re-costed before Task 1 rather than discovered at Task 5, and the overhead's
  source — per point or per tile — is the next thing to separate.
- *The ratio comes back below 1.0.* **The bound is not a bound** and the comparison is measuring
  something other than the same work twice; the reading is refused rather than reported as a
  speed-up.

---

## Task 1 — the field builder, and the plausibility rung's sources

**Goal.** A spatially coherent field with a **step** boundary, **in the tree**, deterministic, with
`ℓ` and `Δ` as named parameters and the plausibility rung's values **cited to a published source
before any run**.

**Behaviour** (E1, E2, E3, E4).

- **It lives in `src/metamer/bench/`**, beside `spike.py` and `references.py`, because §16.2 calls
  the benchmark a first-class component. **2c's lesson is the reason this is not a harness: the
  warm-start spike's coherent field lived in a script that is not in the tree, and it is why
  criterion 12 could not be re-measured on the shipped mechanism.**
- ~~**Three rungs as named constants**: `easy`, `plausibility`, `hard`.~~ **TWO RUNGS ARE BUILT —
  `easy` and `hard`, both ours to choose by E4 — AND `plausibility` RAISES.** Amended 2026-08-30
  at this task's pre-flight: **`ℓ` is the coherence of the fitted OPTIMA, published altimetry
  values describe the coherence of the DATA, and 2c's ceiling arm measured that these differ**
  (*"the optimum is far less spatially coherent than the data is"*), so the obvious source is
  **contradicted, not merely absent**. A request for the middle rung raises with a message naming
  what it would need. **A provisional number in that slot is a claim about the ocean and it would
  stick** — (a2b) at the one slot where that is a scientific error rather than a placeholder.
- **AND A THIRD RUNG IS OWED BACK TO THIS TASK.** E4 was re-decided to **three** rungs on
  2026-08-30 — after this module shipped two — and the middle one is **ours to choose**, not the
  retired `plausibility`. **It is a Task 1 amendment with a Task 4 deadline**; the ownership, the
  reason it is not Task 3's, and what the amendment must satisfy are recorded once, in
  [THE THIRD RUNG IS OWED](../../../PROGRESS.md), and are not restated here.
- **`source` is PER PARAMETER, not one string per rung**, so an unsourced parameter reads as
  unsourced instead of being covered by a citation that applies to a different parameter.
- **`Δ` is a MULTIPLE of the within-regime range of the same parameter**, and the ratio is
  recorded with the rung. Otherwise `Δ` names a contrast whose scale is undefined and two rungs
  agree on `Δ = 2` while disagreeing on what it means — (a2d)'s shape at a lever.
- **The true parameter field varies smoothly at coherence length `ℓ`**, plus **a step of size `Δ`
  across one boundary at a fixed index along the normal axis.** The step is **a step**: the true
  parameters' transition occupies **exactly one cell** (E3).
- **Geometry is derived from `k`, and the derivation ships with the numbers.** `n_normal = 32` is
  **`4k`**, so an interior line sits **≥ 8 cells from the boundary and outside the coupling
  range**, and **the boundary sits at the midpoint, index 16** — the placement the claim depends
  on, which was not stated until Task 1's pre-flight. ~~`n_parallel = 12` is the **minimum giving
  two coarse points per axis** at `k = 8`~~ — **FALSE: the minimum is 9**, verified by
  enumeration, and the claim went through four documents unmultiplied. **12 is a CHOICE**, for
  `32 × 12 = 384` points (D9's 6 point strata at 64 each rather than 48) and for **points beyond
  the last coarse index** — indices 9–11 source from **one side only**, the ordinary case at a
  real field's edge, which `n = 9` barely exercises. Struck rather than deleted,
  coarse at `{0, 8}`. **A later reader who finds only the numbers will round them.**
- **`N = 630`** — production length, and the only length at which §11.2's threshold applies. **An
  affordable length measures a different number rather than a weaker one.**
- **The candidate set is named in this module**, with its `M`, because **`M` sets both the price
  and the stratum count** — `3 × M` point strata and `M × 4` cell strata. It is `M = 2`, matching
  the set the `21 s` was measured over; **a different `M` moves every figure in the budget and in
  the occupancy arithmetic.**
- **The time axis comes from the shipped converter**, never hand-built. A hand-built decimal-year
  axis moved `θ̂` by **6.7e-05 relative** at 2c Task 6 — large enough to fail a bitwise comparison,
  small enough to be argued away.
- **It writes a store the ordinary opener reads**, so the benchmark goes **through** the shipped
  input path rather than around it.

**Invariants.**

- **The true parameter field is returned beside the data**, and **the boundary index is a property
  of the field**, not a constant the estimator re-derives. **(j): the oracle must not share a
  derivation path with the thing it checks.**
- **The same rung twice produces identical bytes; two rungs produce different bytes.** A rung is
  part of the fixture's identity.
- **The plausibility rung's `source` is non-empty and is recorded before any run.** E1's constraint
  1, and **E4 raises its stakes**: the plausibility field is also the sweep's middle rung, so
  retuning it after a null retunes **the sweep's geometry** as well as the magnitude. **That is
  noted at the constant, not only in the plan.**

**Interfaces** (Tasks 2, 4, 5, 6, 7 bind against these):

    class Rung: name: str; coherence_length: float; contrast: float; source: str
    RUNGS: Mapping[str, Rung]          # "easy", "plausibility", "hard"
    class FieldTruth: uri: str; boundary_index: int; normal_axis: str;
                      parameters: NDArray[np.float64]; rung: Rung
    build_field(rung: Rung, *, path: Path, n_normal: int = 32, n_parallel: int = 12,
                n_time: int = 630, seed: int) -> FieldTruth

**Tests, and the bug each catches.**

- *The true parameters' transition across the boundary occupies **exactly one cell**.* Catches a
  builder that smooths the step — for instance by generating the whole field through one smoothing
  kernel and adding the step before it rather than after. **This is the test that protects E3's
  directness**, and without it the benchmark silently becomes the `w > 0` design that was rejected,
  with every measured width a sum of two.
- *An interior line parallel to the boundary at ≥ 8 cells has **no** transition in the true
  parameters.* The paired negative for the above. Catches a builder whose smooth variation happens
  to be steepest where the null line is drawn — which would make Task 2's free negative control
  fire for a reason that is not a defect, and **an unfalsifiable alarm is worse than none.**
- *`coherence_length` is measured back out of the generated **truth** and matches its parameter
  within a stated tolerance.* Catches a builder whose `ℓ` **names a quantity it does not control**;
  E5's entire lever would then be a label and every monotonicity reading vacuous. **Measured on the
  truth and never on the fits**, because the fits are what the sweep is trying to move — (j).
- *Two rungs produce different bytes; one rung twice produces identical bytes.* The paired positive
  and negative. Catches a rung parameter that is **recorded and not used** — (a2) — which would
  make the sweep three copies of one field.
- *The field opens through the shipped opener and passes stage-4a validation, and a run over it
  fits every point.* Catches a benchmark fixture that is legal only to the benchmark, which is the
  defect that made 2c's spike unable to say anything about the shipped path.
- *The field's own iteration count per point is measured and recorded, at `N = 630`, on the
  plausibility rung.* **THE GATE TASK 0 PUT ON THIS TASK.** The budget is `cost(iterations) ×
  points × factor`, and Task 0 measured the cost model and **not** the field: the two fixtures
  actually measured differ by 2× in iterations per point (**25.3** here, **40.4** in 2c), which is
  the difference between a **15.9 h** run and a **31.5 h** one — the second over the 30 h ceiling.
  **E2's budget is finalised against this number before Task 5 spends anything**, and if the field
  lands at the expensive end **N1 drops to one rung.** Catches a benchmark that discovers its own
  cost after paying it. **And it must be recorded rather than merely acted on**: the iteration
  count is partly a fact 2d *builds*, through `ℓ` and `Δ`, so **a field quietly tuned until it is
  affordable is a field tuned with the audit's answer in view.**
- *At **short `N`** on a small lattice, a long-`ℓ` field's warm run takes **strictly fewer**
  iterations than a short-`ℓ` field's, against one cold reference each.* **Moved here from Task 0
  by its pre-flight**, because measuring it there would have built the field in a harness — 2c's
  own defect. **A SIGN, never a magnitude**: short `N` measures a different number, not a weaker
  one. **This is the cheapest check that E5's primary lever is a lever and not a label**, and it is
  the premise the entire sweep rests on. **It is distinct from the truth-side check above**: that
  one says the builder controls the *field*, this one says the field moves the *optimizer*, and
  **conflating them is exactly how a lever becomes a label.**
- *The time axis is the shipped converter's output.* Catches the 6.7e-05 relative move that reads
  as a floating-point detail.
- *The plausibility rung's `source` is non-empty, and constructing a rung without one raises.*
  Catches E1's constraint 1 decaying into a docstring. **The citation is a construction
  requirement, because a field that can be retuned after a null is not a measurement.**

---

## Task 2 — the smear-width estimator, and its interior null

**Goal.** A width **in fine cells**, with a stated floor and a stated ceiling, taken from a fitted
map — and a null line that costs nothing and is not optional.

**Behaviour** (E3, E6).

- **Input is a map over the grid** — one scalar per point — plus the boundary index and the normal
  axis. **Output is a width in fine cells with its floor**, never a bare number.
- **The profile is the map averaged parallel to the boundary**, giving a 1-D function of distance
  along the normal. **The width is that profile's transition width by a named estimator**, and
  **the estimator's name is on the reading** — (j8): when a verdict is adopted, the instrument
  becomes part of the specification.
- **The floor is 1 fine cell.** A width at or below it is emitted as **`≤ 1 cell`**, never as a
  number — (a2b), and (i9): a fixture whose window is narrower than the instrument's resolution
  cannot express its condition. **On a grid the finest resolvable width is one cell, so a width at
  the floor means *unresolved*, not *zero*.**
- **The ceiling is the spiral reach** — `spiral_bound × coarse_stride`, **read from config, never
  hard-coded**. A width above it is **refused as a reading and reported as an estimator failure**,
  because **no point can be biased by a source the spiral never reached.**
- **The interior null is emitted on every call**, not behind a flag. Same estimator, on a line
  parallel to the boundary at a stated offset where the truth has no transition.
- **The estimator reads the true parameter field for the boundary index and for nothing else.**

**Invariants.**

- **No randomness.** The same map gives the same width.
- **Every reading names the map it came from** — which scalar, which arm. ***"The smear width"* is a
  family of numbers and the naked phrase is D8's pooled-figure problem in a new place.**

**Interfaces** (Tasks 4–7 and 9 bind against these):

    class WidthReading: cells: float | None; at_floor: bool; floor_cells: float;
                        reach_cells: float; estimator: str; map_name: str; arm: str;
                        refused: str | None
    smear_width(field_map, *, boundary_index, normal_axis, reach_cells,
                map_name, arm) -> WidthReading
    interior_null(field_map, *, boundary_index, normal_axis, offset_cells,
                  reach_cells, map_name, arm) -> WidthReading

**Tests, and the bug each catches.**

- *A synthetic map that **is** a step returns `≤ 1 cell`.* The floor from the clean side. Catches an
  estimator that returns a width for a step, which would put its own bias into **every** rung's
  number.
- *A synthetic map with a constructed transition of exactly 5 cells returns 5 within tolerance.*
  **The positive control — (i2).** Catches an estimator that returns the floor for everything,
  which reads as *"no artifact"* on every field and **is the confident null this project has been
  bitten by three times.** Without this test the criterion *"the null line returns the floor"*
  passes for the worst possible reason.
- *A map whose transition exceeds the spiral reach is **refused**, not reported.* Catches a reading
  that is arithmetically fine and physically impossible being emitted as a smear.
- *The interior null returns `≤ 1 cell` on a map with a boundary, **and returns a width** on a map
  whose smooth variation is steepest at the null line.* The paired positive and negative for E6's
  gate. **Catches a null-line check that cannot fire**, which would license every downstream number
  in the sub-phase.
- *A map with a NaN column does not silently shorten the profile.* Catches a failed-fit column
  being averaged away, which narrows the profile and therefore **narrows the width — always in the
  reassuring direction.**
- *The reach is read from the config's `spiral_bound` and `coarse_stride`, and a changed
  `spiral_bound` changes the refusal boundary.* Catches 32 being frozen as a literal, which would
  survive a config change and refuse or admit the wrong readings silently.
- *A reading cannot be constructed without its estimator name, map name and arm.* Catches a width
  quoted without saying which scalar, which arm, or which instrument produced it.

---

## Task 3 — the N2 full-field map

**Goal.** The floor the smear is read against. **A smear measured against zero is a different claim
from a smear measured against the width an equal-distance random start produces.**

**Behaviour** (E7's four-arm extension).

- **The audit's N2 arm, run over every point of the field** rather than over an audited subset,
  producing a map `smear_width` can take.
- **N2's per-cell distance is matched to that cell's own warm/cold start distance** — **matched per
  cell, never on average**, exactly as 2c Task 6 built it.
- **The direction stays keyed on `(seed, GRID-GLOBAL point index, candidate)` through a
  `SeedSequence`.** Enlarging the point set must not move an existing cell's direction, or two runs
  over one field stop being comparable.
- **Inadmissible starts are excluded and counted, never run cold.** The 2c defect this protects
  against is the one-line fix that **is** the defect: setting `x0_valid` false falls back to the
  moment ladder, so the N2 arm would silently contain **cold** fits at exactly the cells where the
  perturbation was largest, and *"N2 agrees with cold"* would be true by construction.
- **It reuses the shipped `arm_starts` and `run_arms` rather than re-deriving the perturbation.**
  A second derivation of N2 is a second N2.

**Invariants.**

- **The map's N2 value and the audit's N2 value at the same rung, seed and point are the same
  value.** Two instruments computing one quantity is (j5)'s territory and the cheap fix is one
  instrument.
- **The excluded count travels with the map** and is never folded into it.

**Interfaces** (Tasks 4–7 bind against these):

    class N2Counts: excluded: int; zero_distance: int; exhausted_spiral: int
    n2_field_map(field: FieldTruth, *, warm, warm_valid, seed: int,
                 scalar: str) -> tuple[NDArray[np.float64], N2Counts]

**Tests, and the bug each catches.**

- *The map's value at a point equals `run_arms`' N2 value at that point under the same seed.*
  Catches the second derivation. **This is the test that stops the floor and the audit disagreeing
  about what N2 is** — and they would disagree quietly, since both are plausible numbers.
- *Enlarging the field does not move an existing point's N2 direction.* Catches the grid-global
  keying regressing to a row index, which is the (k) finding 2c recorded and which **recording the
  seed does not save you from.**
- *An inadmissible start is excluded from the map, appears in the count, and the map holds no cold
  fit at that cell.* Catches the fallback silently populating N2 with cold fits.
- *The excluded count is non-zero on a **constructed** field that forces exclusion.* **(i8): the
  fault class does not otherwise occur, so it must be constructed.** Catches an exclusion path that
  has never executed and whose zero count is therefore a claim about the instrument — (a2b) at a
  count.

---

## Task 4 — the benchmark driver and its reproducible report

**Goal.** §16.2's *"emits a reproducible report"*. One rung in, one report out, **every number
carrying its rung.**

**Behaviour** (E1 constraint 2, E7).

- Given a rung it **builds the field, runs the cold full-field pass, runs the shipped two-pass,
  runs the N2 map where that rung asks for one, takes the widths, and emits one report.**
- **A `Quantity` without a rung cannot be constructed.** The non-empty-scope construction from
  `audit_report.py` is **reused, not re-invented**: D8's argument is that labelling a number does
  not stop it being quoted, so **the number must not exist.** E1's constraint 2 is enforced by
  construction rather than by convention.
- **The report records the instrument**: the estimator's name, `coarse_stride`, `spiral_bound`, the
  reach in fine cells, the candidate set with its `spec_hash`es, `ALGORITHM_VERSION`, the record
  length, the geometry, and **the rung's parameters with their source.**
- **The report records the cost** — wall clock per arm and per point — so **the 27.0 h figure is
  checked against the run rather than assumed.** It is an **upper bound priced at the cold rate**;
  a run finishing early is the bound behaving, and the report says so.
- **The interior null is computed and emitted FIRST on every rung.** A rung whose null returns a
  width is marked **contaminated** and **its smear quantities are withheld with the reason** —
  (a2b), and it is E6's gate rather than an advisory note.
- **It is run on demand and is not in `pixi run test`.** Its report is committed; the suite asserts
  on the report.

**Invariants.**

- **All arms within one session, interleaved.**
- **Two runs of one rung produce identical bytes outside the timing block.** Timings are segregated
  from the reproducible part, or a bitwise comparison of two reports is impossible in principle.
- **The report is self-describing**: a reader with the report and no other file can say which
  field, which rung, which instrument and which defaults produced every number.

**Interfaces** (Tasks 5–9 bind against these):

    class RungReport: rung: Rung; contaminated: bool; null_line: WidthReading;
                      instrument: Mapping[str, object]; cost: Mapping[str, float]
        def quantities(self) -> tuple[Quantity, ...]
        def withheld(self) -> tuple[Quantity, ...]
    run_rung(rung: Rung, *, out_dir: Path, arms: Sequence[str], seed: int) -> RungReport

**Tests, and the bug each catches.**

- *A `Quantity` without a rung raises at construction.* Catches E1's constraint 2 decaying into a
  convention, which is how a control's floor gets quoted as a measurement of the ocean.
- *A rung whose interior null returns a width is marked contaminated and its smear quantities are
  in `withheld()` with the reason; **a rung whose null is clean has the same quantities present**.*
  The gate, both directions. Catches an unfalsifiable gate — **the failure that would let every
  smear number through while looking like a safety check.**
- *Two runs of one rung are byte-identical outside the timing block.* Catches a stray
  `default_rng()` or a dict iteration order. **N2 is the only randomness in the system, so this is
  the one place §11.3's traversal independence can now be lost.**
- *The report names the estimator, the stride, the bound and the reach, and a changed
  `spiral_bound` is visible in it.* Catches an adopted verdict whose instrument is not in the
  record — (j8).
- *The cost block is derived from this run and not transcribed from a constant.* Catches the `21 s`
  outliving the machine it was measured on, which is how a budget becomes a belief.
- *A withheld quantity is an object carrying its reason, never an absent field.* Catches silence
  and absence being the same bytes.

---

## Task 5 — the easy rung: the positive control, and the gate

**Goal.** Establish that the instrument fires, and take the upper end of the resolution floor.
**Nothing downstream is read until this passes.**

**Behaviour** (E4, E6).

- Run the easy rung. **Its `ℓ` and `Δ` were chosen by us for detectability and the report says so.**
  It is a demonstration and a floor; **it is never quoted as a magnitude.**
- **THE INTERIOR NULL IS READ FIRST, BEFORE ANY SMEAR NUMBER IS LOOKED AT.** If it returns a width,
  **stop and diagnose the estimator. Do not proceed to the plausibility rung.** It costs no
  compute — the same fits, a different line — it would contaminate every smear number on every
  rung, and it is the clause most expected to fire.
- **The smear width must exceed the 1-cell floor.** If it does not, **the instrument cannot resolve
  the artifact at any contrast**, the plausibility rung's null would be uninterpretable, and **that
  is 2d's finding** — reported, not worked around by widening the contrast until something appears.
- **N1 runs here** (Task 0 permitting), because separating *"the surface decides"* from *"the start
  distance decides"* needs the rung where the artifact is largest.
- Record the saving, so E6's monotonicity has its first point.

**Invariants.**

- **A retune of the easy rung after seeing its result is a new rung with a new name**, not an edit.
  The easy rung's freedom to be chosen for detectability is exactly why its numbers cannot be
  quoted, and an edited-in-place rung loses the record of what was tried.

**What this task asserts, and the bug each assertion catches.**

- *The interior null returns `≤ 1 cell`.* **The gate.** Catches a profile estimator measuring the
  field's own smoothness, which would inflate every width in the sub-phase in the direction that
  looks like a finding.
- *The smear width exceeds the floor.* **The positive control — (i2).** Catches an instrument that
  can see nothing, which would otherwise be discovered at the plausibility rung and **read as a
  scientific null about hysteresis** rather than as a fact about the instrument.
- *The saving does not reach the `self` ceiling.* Catches the source map handing points **their own
  optimum** — a defect that would look like a spectacular result and would be quoted as one.
- *N1's arm is present and its cost is within the spread Task 0 measured.* Catches a budget that
  held on one batch and not on a field.

---

## Task 6 — the plausibility rung: criterion 12, the audit's first real numbers, and OQ21

**Goal.** The one rung a magnitude is quoted from. **This is the task 2d exists for.**

**Behaviour** (E1, E2, E8).

- **The rung whose `ℓ` and `Δ` are the published values cited at Task 1**, and which is **also the
  sweep's middle rung** — so retuning it after a null retunes the sweep's geometry as well as the
  magnitude. **Noted where the values are recorded, not only here.**
- **Criterion 12's magnitude**, through the shipped mechanism at `N = 630`: **iterations and wall
  clock, both named.** This is 2c's criterion 12 closing, or not closing, on the mechanism rather
  than on a harness.
- **The audit runs over the WHOLE field at this rung** — 384 points, four arms, one batch, one
  session. Its point strata have 384 members to fill 6 bins at `M = 2`. **Whether they fill them is
  a reported outcome, not a guarantee**, and the member count ships beside every rate regardless.
- **The audit's cold arm is computed by `run_arms` and is NOT read from the criterion-12 run's
  store.** 2c Task 6's same-session rule is **not relaxed for budget**; the duplication is priced
  in E2's 4.0 factor and is deliberate.
- **OQ21's measurement, for free** (E8). Both the pre-fit and post-fit sides exist over the same
  384 points. **The pre-fit proxy is NAMED before the correlation is computed**, or the measurement
  selects its own winner — the warm-up-split trap one level up. **The correlation with each of D9's
  post-fit proxies is recorded either way, and OQ21 closes either way.**
- **The smear width and its N2 floor, side by side.** **This is the number that goes in the
  README.**

**Invariants.**

- **The standing limitation is attached to the magnitude at the point of emission**, not only in
  prose around it: a simulated field with chosen coherence is not a measurement of the ocean.
- **The audit's point-selection rule is fixed and recorded before the numbers arrive** (E8's second
  consequence). Which points are audited determines which strata reach 30 members, so a rule
  adjusted afterwards is tunable against the occupancy result — (i5) at the level of a sampling
  design. **Here the rule is "every point", which is the one rule that cannot be tuned** — and that
  is a reason for it, not merely a consequence of affording it.

**What this task asserts, and the bug each assertion catches.**

- *The saving is reported with **both** readings and neither is omitted.* Catches 2b's criteria 6
  and 7 failure mode — a criterion whose reading nobody named, underspecified for four tasks — at
  the single number 2d exists to produce.
- *No audit quantity is emitted without its member count beside it.* Catches a rate quoted over a
  stratum that did not reach 30, which D10's (a2b) handling exists for and which **a larger field
  makes newly tempting**, because most strata will now clear the floor and the exception stops
  looking like the rule.
- *The pre-fit proxy's name is recorded before the correlation is computed.* Catches OQ21 closing
  on whichever proxy happened to correlate.
- *The audit's cold arm differs in provenance from the criterion-12 run's cold arm, and they agree
  numerically.* The paired check. Catches the same-session rule being quietly dropped to save four
  hours **and** catches a genuine disagreement between two cold arms, which would be a finding
  about determinism rather than about the budget.

---

## Task 7 — the hard rung: the floor from below, and the monotonicity

**Goal.** A measured floor beside the rung where a null is expected, and E6's first prediction
closed with three points rather than two.

**Behaviour** (E4, E5, E6).

- `ℓ` and `Δ` **harder than the literature rung.** A null is expected here and that is the point.
- **Its N2 map is built**, because **a null needs a floor beside it** and this is the rung most
  likely to produce one. This is the second of E2's two N2 rungs.
- **E6's monotonicity closes here.** Three points, so a rising curve is distinguishable from a
  saturating one — D2's reason for a three-fixture lever.
- **The `ℓ`-versus-`Δ` confound is restated in this rung's report**, because this is the rung whose
  null would tempt a reader to attribute it to one lever: **the floor is a floor along the diagonal
  and says nothing about `(short ℓ, stark Δ)`.** E5's follow-up trigger is quoted with it.

**What this task asserts, and the bug each assertion catches.**

- *The saving is monotone across the three rungs, and the easy rung's is the largest.* Catches a
  lever that is a label. **Checked against Task 1's truth-side coherence measurement and not only
  against the fits**, so a monotone-looking result produced by something other than `ℓ` is visible.
- *A null at this rung is reported beside the width **N2 produces at this rung**, never beside
  zero.* Catches a null read as *"no artifact"* when it is *"no artifact this instrument can
  resolve at this contrast"* — the two are the same table row otherwise, and they are opposite
  findings.
- *No rung's saving reaches the `self` ceiling.* Repeated from Task 5 because it is cheap and
  because the defect it catches is rung-specific.

---

## Task 8 — the README figure, and what it is allowed to say

**Goal.** §16.2 item 6's deliverable: *"That figure goes in the README… it is the honest disclosure
that makes the smoothness claim credible."*

**Behaviour** (E7).

- **The figure carries the smear width at the plausibility rung, N2's width beside it, the floor,
  the reach, and the rung's parameters with their source.** A width alone is not the disclosure;
  **the width against its floor is.**
- **The caption carries the standing limitation.** **A figure is the most-quoted artifact in a
  README and it will travel without the paragraph around it** — which is why this is a task
  requirement and not a review note.
- **§16.2 says the figure goes next to the misspecification figure. That figure is §16.2 item 4 and
  is not 2d's.** The smear figure ships; **the position is reserved and the absence is stated**
  rather than silently dropped, so a later reader does not conclude item 4 was done.
- **THE RESERVATION NAMES WHAT WOULD FILL IT AND WHO OWNS IT: §16.2 item 4, the misspecification
  figure, owned by PHASE 6 (validation suites).** **A reserved position with a named owner is a
  plan; one without is a gap wearing a plan's clothing.** **And naming the owner found a defect:**
  §17's Phase 6 line claimed the spatial-field hysteresis measurement for Phase 6 while Q11 had
  assigned it to 2d on 2026-08-11, and **the line was never amended.** Corrected in the design doc
  at its source, with the item 1–5 / item 6 split stated as a table so it cannot drift again.
- **Plotting follows the project's colormap conventions.**
- **The README's existing two-pass section is swept for claims this task falsifies**, per (a6) — 2c
  Task 7 found a false sentence in that exact section by sweeping for a phrase, and this task adds
  numbers to the same section.

**What this task asserts, and the bug each assertion catches.**

- *The README's figure names its rung and its field.* Catches the figure being read as a
  measurement of altimetry — **the one thing the standing limitation forbids**, and the artifact
  most likely to do it.
- *The caption names the standing limitation and the real-data spike as the closer.* Catches 2d
  being written up as having closed D1.
- *The README states that the misspecification figure is absent and why.* Catches a reserved
  position reading as a completed one.
- *No number in the README appears without its rung.* E1's constraint 2 at the boundary where the
  project meets its readers.

---

## Task 9 — the 2d exit-criteria suite

**Goal.** One suite, each criterion asserting **a named reading**, **an independent check and not a
roll-up** — driven from outside wherever an outside exists.

> **A 27-HOUR MEASUREMENT CANNOT BE A TEST, AND ITS RECORDED OUTPUT CAN.** The criteria that rest
> on the benchmark assert against the **committed rung reports**, which are artifacts in the tree.
> **The suite fails if a report is missing, if its instrument block does not match the current
> defaults, or if a default it names has since moved** — so a report cannot quietly outlive the
> configuration that produced it. Everything else — the estimator, the builder, the N2 map, the
> driver's construction rules — is asserted directly and runs in the ordinary sweep.

| # | criterion | reading |
|---|---|---|
| 1 | The true parameter field's step occupies exactly one cell, and an interior line has no transition | the truth array, both lines |
| 2 | The builder's `ℓ` is recoverable from the truth it generates | the coherence length of the **true parameters**, not of the fits |
| 3 | The benchmark field opens through the shipped opener and every point fits | the exit code, and the fitted point count |
| 4 | The estimator returns `≤ 1 cell` on a step and 5 cells on a constructed 5-cell transition | the width in fine cells, **both sides** |
| 5 | The interior null returns `≤ 1 cell` at every rung, and a contaminated rung withholds visibly | the null reading on each committed report, and the `withheld` list |
| 6 | The smear width at the easy rung exceeds the 1-cell floor | the width, against its stated floor |
| 7 | No width exceeds the spiral reach, and a width above it is refused | the width against `spiral_bound × coarse_stride`, **read from config** |
| 8 | Every smear width is reported beside the width N2 produces at the same rung | both numbers in one report, per rung |
| 9 | The N2 map and the audit's N2 arm agree at every shared point | the per-cell value under one seed |
| 10 | The warm-start saving at the plausibility rung, `N = 630`, through the shipped mechanism | **iterations and wall clock, both named** — **2c's criterion 12** |
| 11 | The saving is monotone in `ℓ` and no rung reaches the `self` ceiling | the per-rung saving, against the ceiling figure |
| 12 | Every audit point stratum at the plausibility rung reports a rate, or its member count with the reason | the report's own `withheld` list |
| 13 | A number without a rung cannot be constructed | the construction, **both directions** |
| 14 | OQ21 closes: a **named** pre-fit proxy's correlation with each post-fit proxy | the coefficient, and the name recorded **before** it |
| 15 | The README carries the smear width with its rung, its floor, and the standing limitation in the caption, **and names §16.2 item 4 and Phase 6 as the reserved position's content and owner** | the README's own text |
| 16 | The committed reports name an instrument matching the current defaults | the report's instrument block against `Config`'s defaults |
| 17 | The benchmark field's iteration count per point is recorded, and E2's budget was finalised against it before any rung ran | the recorded count, and the factor it selected |

**Criterion 12 can fail, and it is written so that it can.** 384 points across 6 point strata is
64 each at uniform occupancy and margin bins are not uniform. **A criterion that cannot fail is not
a criterion**, and a withheld stratum reported with its member count is the honest outcome rather
than a broken one.

**And three verdicts are inherited rather than new.**

- **2b's criterion 6 stays FAILED and criterion 7 stays FAILED.** 2d does not reopen the residency
  model and **must not be read as having done so.** The check reads the verdicts out of
  `PHASE_2B_EXIT_CRITERIA` **by number**, so a renumbering fails loudly.
- **2c's criterion 11 stays REDUCED SCOPE.** `HESSIAN_COND_LIMIT` **is** D9's first `κ` boundary,
  so two bins are unreachable **by construction** and a larger field cannot populate them. **The
  check re-reads `unreachable_kappa_bins` on the plausibility rung's report**, so 2d cannot be
  credited with closing it. **Re-cutting D9's boundaries to make the axis discriminate would be
  choosing a stratification with the audit's answer in view**, which D9's fixed-constant rule
  forbids — and 2d, which finally has an answer in view, is the sub-phase most tempted.

---

## What 2d does not do

- **§16.2's items 1–5** — selection accuracy, parameter recovery, trend-uncertainty calibration,
  misspecification, ML vs REML. **A sub-phase in themselves.** 2d opens item 6 only.
- **The misspecification figure.** §16.2 item 4. Its position beside the smear figure is reserved
  and its absence is stated (Task 8).
- **Anything on real altimetry.** **The standing limitation, not an omission** — it is the
  condition D1 is authorized under, and **2d cannot lift it.**
- **Crossing `ℓ` against `Δ`.** E5, with a falsifiable trigger for when it becomes worth buying.
- **Re-cutting D9's `κ` boundaries.** Forbidden by D9's own fixed-constant rule, and 2d is the
  sub-phase most tempted.
- **`tiling.py`'s four name-based dimension sites**, where the contract is positional and **stage
  4a's own message already contradicts the implementation**. Still unowned, still not 2d's — and
  still cheapest to fix alongside open question 20.
- **Open question 20's uniformity sweep**, coordinate monotonic direction first. **2d builds the
  first deliberately anisotropic grid in this project and that closes no part of it: grid SHAPE
  and coordinate DIRECTION are different degrees of freedom**, so taking it would mean a fixture
  2d has no other use for, against machinery 2d is not touching — **scope on a shared word rather
  than a shared mechanism.** And **closing half of it while `tiling.py`'s scope decision is open
  gives a suite that covers a case the code still gets wrong**, which is worse than the gap. The
  full reasoning is at the question, decided 2026-08-30.
- **Any change to the residency model or to a prior sub-phase's exit-criterion verdict.**
