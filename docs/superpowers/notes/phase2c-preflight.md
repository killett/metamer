# Phase 2c pre-flight, per task

The (a)–(k) audit of each 2c task brief and what each finding changed. The method itself lives
in exactly one place — [`phase1-to-phase2-handoff.md`](phase1-to-phase2-handoff.md) §1 — and is
**not restated here**. Append to this file **before** each task, not after.

---

## 2c brainstorm Task 0 — the warm-start spike, audited before any code

**THE BRIEF.** Measure the quantity §11.2 names as unmeasured and makes its own verdict turn on:
does starting a fit from a spatial neighbour's converged `θ̂` reduce iterations by the ~30% below
which *"the mechanism is not paying for its complexity or its hysteresis risk, and warm-starting
is dropped"*? Measure it **before** the mechanism exists, so that a "drop it" verdict costs
nothing.

**THE ARGUMENT FOR THE ORDERING, RECORDED BECAUSE IT IS THE DECISION AND NOT THE TASK.** By the
time a two-pass mechanism exists, warm-starting has store fields, a cache key keyed on
`(fit_hash, candidate spec_hash)`, a resume-gate interaction and a schema version. Deleting it
then costs a schema bump and a sixth cascade. **A verdict whose "no" is expensive is not a
verdict; it is a formality**, and the pull toward *"well, 22% is nearly 30%"* is exactly what an
expensive "no" produces. Measured first, the "no" costs one harness.

### (i7) THE OBVIOUS FIXTURE IS THE WRONG ONE, AND IT IS WRONG IN THE FLATTERING DIRECTION

Warm-starting each point from its **immediate** neighbour is not the mechanism §11.1 specifies
and it is not what production would run. The mechanism is **nearest-valid coarse point at stride
`k`, in dataset coordinates**, ties broken lowest `y` then lowest `x`, searched outward in a fixed
spiral — so a pass-2 point starts from a fit up to `k/2` cells away in each axis, not one. An
immediate-neighbour fixture measures an **upper bound on the saving** and would bias the verdict
toward building the thing. **The harness implements the design's rule at `k = 4`**, which is the
stride §11.2's own barrier arithmetic assumes (`k ≥ 4`).

### (i2) THE OBSERVABLE CAN BE AN ABSENCE, SO THE POSITIVE CONTROL IS PART OF THE MEASUREMENT

*"Warm starts save nothing"* and *"`x0` never reached the optimizer"* are byte-identical in the
output. The control is **self-warm**: start each point from **its own** converged `θ̂`, through
the same `fit(x0=…)` call. Iterations must collapse. If they do not, the null is a claim about
the instrument and not about the subject, and nothing else in the run means anything.

**This is also (a2) applied to `fit(x0=…)`.** The signature exists and is documented as *"what
Phase 2 feeds back"*; that it is honoured end to end has never been exercised by a consumer,
because there has never been one. **A parameter is not a gate.**

### (i7) AND THE DISCRIMINATING CONTROL IS THE ONE THAT DECIDES WHAT 2c OWES

A saving over the moment ladder is **not** evidence for the two-pass geometry. Two explanations
predict a saving and they are not the same mechanism:

| explanation | what it implies 2c must build |
|---|---|
| **neighbours are similar**, so a nearby converged `θ̂` is a good start | the two-pass barrier, the coarse stride in `fit_hash`, the spiral, `/warmstart/` |
| **any converged `θ̂` beats the moment ladder**, proximity irrelevant | far less — no geometry, no stride, no spiral |

**The random-distant arm separates them and is nearly free:** each pass-2 point warm-started from
a coarse point at index distance > 6, drawn under a fixed seed. If neighbour-warm ≈
random-distant-warm, the geometry is buying nothing and 2c's shape changes. **Placed where the
two explanations disagree, which the neighbour arm alone is not.**

### (h) A FIELD OF INDEPENDENT DRAWS WOULD MEASURE NOTHING

Warm-starting's benefit is entirely a claim about neighbours being similar, so the fixture must
have real spatial structure or the measurement is the same defect §11.2 already flags for
hysteresis. The field varies **smoothly in the true parameters within a regime** and carries a
**sharp regime boundary** — a change of family, not merely of scale — placed **between** coarse
columns so that cross-regime warm sources genuinely occur, and so that the lowest-`x` tie-break
is exercised. **Boundary-adjacent points are labelled and reported apart**, because the saving at
a boundary is where the mechanism is least helpful and most dangerous, and pooling hides it.

### (a) THE POOLED SAVING IS THE ONE THAT GETS QUOTED AND THE PER-CANDIDATE ONES ARE THE TRUE ONES

The warm start is per `(fit_hash, candidate spec_hash)`, so the saving may differ by family: a
stiff family may benefit where an easy one does not, and a pooled 30% can be one family saving a
lot and another saving nothing. **Reported per candidate, per regime and per boundary stratum,
never pooled alone** — §11.2's own rule for the audit, applied to the spike that stands in for it.

### (i10) THE THRESHOLD IS A BAND AND NEEDS AN UNCERTAINTY, OR "NEARLY 30%" WINS BY FEEL

A saving of 22% against a 30% threshold is a decision only if the spread is known. The saving is
reported **with a bootstrap standard error over points**, so band-versus-uncertainty is a
comparison rather than a preference.

### (a5) THE BRIEF'S THRESHOLD IS IN ITERATIONS AND ITS DECISION IS ABOUT TIME

§11.2 states the rule as *"saves less than ~30% of iterations"*. The thing that matters is wall
clock, and the two can disagree: a warm start can cut iterations while leaving the fixed per-fit
costs — `design_info`, the ACF, `n_eff`, the Hessian at the optimum — untouched, so the wall-clock
saving is bounded above by the iteration saving and can be much smaller. **Both are reported, and
where they disagree the wall clock governs. Stated before the numbers exist.**

### (j) THE DATA MUST NOT COME FROM THE CODE UNDER TEST

The cold arm is the reference for the warm arm and they share `fit` **on purpose** — the question
is about the optimizer's path through one implementation, not about correctness. But the
**simulated field** is drawn from covariance matrices written from the textbook Matérn ACF in the
harness, never from `metamer.core.statespace`, so a slip in a family's construction cannot cancel
between the fixture and the fit.

### (k) WALL CLOCK IS A PROPERTY OF THE BOX, AND ITERATIONS ARE NOT

Arms are **interleaved within each repeat** and the whole thing repeats three times, because this
box drifts within a day — the (a9) confound Tasks 8a, 8i and 8b were spent on. Threads are pinned
with `threadpool_limits(1)` so the timing comparison is not a scheduling comparison.

**AND THE ITERATION COLUMNS ARE DETERMINISTIC, WHICH IS A FREE TEST OF SOMETHING ELSE.** The same
arm re-run must return **identical** `n_iter`, `loglik` and `theta`. Asserting that across the
three repeats exercises §11.3's bitwise claim **along the warm-start path**, which is the one path
§11.3 does not yet have a consumer for.

### §11.2's CONFOUND IS DESIGNED OUT RATHER THAN MEASURED AROUND

Two same-kind terms with a free timescale are exchangeable, and parameter disagreement then reads
as hysteresis while being non-identifiability. **The candidate set is lint-clean by construction**
— no two terms of the same kind with free timescales — and the lint is **run over it and recorded**
rather than assumed, per (a2).

### (a3) THE MECHANISM IS IMPLEMENTED IN THE HARNESS AND NOWHERE ELSE

The stride, the spiral, the tie-break and the interpolation rule live in the harness. **No store
field, no cache key, no schema version, no production module changes.** That is not tidiness — it
is the property that makes the "drop it" verdict cost nothing, which is the entire argument for
running this first.

### WHAT WOULD MAKE THIS MEASUREMENT WORTHLESS, NAMED IN ADVANCE

- **The self-warm control failing to collapse** — then `x0` is inert and every other column is
  noise.
- **A fixture whose true parameters vary so slowly that every point is its own neighbour**, which
  would report a saving that no real field would reproduce. The regime boundary and the
  per-stratum reporting are what stop that reading as a global result.
- **A cold arm whose points mostly fail.** A saving computed over `n_iter` at non-`OK` points is a
  comparison of two failure paths. Outcomes are recorded per arm and the saving is computed over
  the **both-OK** intersection, with the excluded count reported.

### THE SECOND FIXTURE, AND WHY IT IS CHEAP INSURANCE

The primary field is `N = 96` so that four arms over 240 points fit in an hour. Iteration counts
are a property of the parameter space rather than of `N`, but that is a claim, so a **second
fixture at `N = 384` over a 48-point subset** runs the cold and neighbour-warm arms alone. **If the
saving moves with `N`, the primary fixture's number does not describe production**, and that is
worth knowing for the price of sixteen minutes.

---

## 2c brainstorm Task 1 — the stride curve, audited before any code

**THE BRIEF.** Measure `s(k)`, the warm-start saving as a function of the coarse stride, at
`k ∈ {2, 4, 8}`, and choose the shipped stride on a written net-cost objective rather than on
§11.2's `k ≥ 4` floor.

**WHY IT IS MEASURED RATHER THAN ASSERTED, AND THIS IS THE DECIDING ARGUMENT.** The stride is
**inside `fit_hash`** (Q9): it determines what every pass-2 point starts from. **It is therefore
the one warm-start parameter that cannot be revised later without fragmenting every store built
before the revision.** An hour now against a cascade plus every existing store later is not a
close trade — and leaving a **fit-identity field asserted** is the class of value this project has
been most consistently wrong about.

### (j4) THE MEASUREMENT IS CHEAP BECAUSE THE STRIDES NEST, AND THAT IS AN EXISTING MEASUREMENT USED AS EVIDENCE

**`k = 8`'s coarse set is a subset of `k = 4`'s, which is a subset of `k = 2`'s.** So the `N = 630`
run's pass 1 **already contains every source `k = 8` needs and every source `k = 4` needs**; only
`k = 2`'s extra 27 coarse points must be fit. **(j4) applied to a fixture rather than to a table.**

### (j5) THE THREE STRIDES MUST BE READ ON ONE POINT SET, OR THEY ARE NOT COMPARABLE

Each stride has its **own** pass-2 set — 108, 135 and 140 of 144 — so a saving computed on each
stride's own set is three savings over three different populations. **That is exactly the
comparability failure promoted as (j5) two decisions ago.**

**The measured quantity is therefore `s(k)` on the COMMON fine set** — the **108** points that are
pass-2 under all three strides — with the **same cold reference**. **The arithmetic that turns
`s(k)` into a run cost uses each stride's own `1/k²` fraction**, which is a calculation and not a
measurement. Measured lever, computed objective, and the two are not mixed.

### (a5) THE OBVIOUS OBJECTIVE IS IN SERIES AND THE DECISION IS IN TIME

`1/k² + (1 − 1/k²)·(1 − s(k))` **assumes pass 1 and pass 2 cost the same per series, and Task 0
measured that they do not** — cold is **45.90% slower in wall clock** at `N = 630`. In series-units
a larger `k` is **undervalued**, because it shifts work from the expensive arm to the cheap one.

> **THE OBJECTIVE, IN TIME, WRITTEN BEFORE THE NUMBERS EXIST:**
>
> `relative_cost(k) = (1/k²) + (1 − 1/k²) · (T_warm(k) / T_cold)`
> `net_saving(k)   = 1 − relative_cost(k)`
>
> where `T_cold` and `T_warm(k)` are **per-series wall clock on the common 108-point set**, both
> measured, not modelled. **Both arms run over the same 108 points so the ratio has no
> population difference in it.**

**AND ITS ASSUMPTIONS ARE STATED WITH IT.** It treats pass 1's work as **fungible with pass 2's**,
which the barrier makes false — see below. It ignores the assembly cost, which is identical
across strides. And it is a **whole-run** cost, so it says nothing about peak.

### THE BARRIER'S COST IS NOT IN THE OBJECTIVE, AND THAT IS STATED RATHER THAN BURIED

Pass 1 must **complete** before pass 2 starts, so it **serializes** a fraction of the run that
cannot overlap. **At `k = 2` that fraction is 25% of all points; at `k = 8` it is 1.6%.** Whether
that matters depends on the parallelism story, which is within-tile by §11.1 — but the objective
as written treats the two arms' work as interchangeable and it is not. **A stride chosen on the
objective alone is chosen ignoring the barrier**, and if `k = 2` ever wins on the arithmetic the
barrier is the reason to look again.

### (i10) AGREEMENT IS A SECOND COLUMN, NOT A FOOTNOTE

The mechanism was authorized at **90.37% selection agreement against a pre-agreed 90% stop — a
margin of one grid cell.** If agreement **degrades with `k`** — a more distant source landing in a
different basin more often — then **the net-cost optimum and the correctness optimum diverge**,
and that is a **scope decision rather than an arithmetic one**. **Both columns are reported at
every `k`, and the choice is not made on cost alone.**

### WHAT THIS CANNOT ESTABLISH, NAMED IN ADVANCE

**One fixture, one lever, three points**, at `N = 630` on one simulated field with one candidate
set. **Task 0's own history is the caution: five of nine predictions changed verdict between
fixtures**, and a single-fixture reading would have shipped a confident wrong recommendation.
**The stride chosen here is chosen for THIS field's spatial coherence**, which has never been
measured on real altimetry.

### AND THE OBJECTIVE OUTLIVES THE NUMBER

Whichever `k` wins, **the net-cost formula now exists in writing**, so a future change to either
rate — a faster optimizer, a cheaper cold path, a differentiated filter — **has a formula to
re-evaluate the stride against rather than an inherited constant.**

---

## Plan Task 0 — `fit`'s per-cell warm-start selector, audited before any code

**THE BRIEF** is the plan's Task 0: `x0` gains a companion `x0_valid` of shape `(B, M)`; a false
cell takes the moment ladder and is bit-identical to the same cell fit with `x0=None`; a NaN
sentinel is refused as a design; a non-finite value, or a value outside its `ParamSpec`'s
diagnostic limits, **inside a cell marked valid** is a refusable error naming the cell and the
candidate; `x0` without `x0_valid` is a hard error.

**NOTE ON NAMING.** *Task 0* now denotes two different pieces of work in this file. The entry
above is **brainstorm Task 0**, the warm-start spike. This entry is **plan Task 0**, the first
task of [`2026-08-24-metamer-phase2c.md`](../plans/2026-08-24-metamer-phase2c.md). The plan's
head calls the spike *"Task 0 of the brainstorm"*; nothing else disambiguates them, and a reader
arriving at either heading cold cannot tell which is which. **Both headings now say which.**

### (d) THE VOCABULARY EXISTS ALREADY IN THE CONFIG, AND NOT AT ALL IN `core`

`x0_valid` appears nowhere in `src/` or `tests/`. But `warm_start_enabled`,
`warm_start_coarse_stride`, `warm_start_interpolation_rule`, `warm_start_spiral_bound` and
`warm_start_tie_break` are **already config fields with tests** (`tests/test_config.py`), landed
in 2a. **Plan Task 1 adds them to `FIT_RELEVANT_FIELDS`; it does not invent them.** Recorded here
because "the config does not carry warm-start settings yet" is the obvious wrong assumption for
Task 1 and it would be discovered by a duplicate field rather than by a failure.

### (g) THERE IS EXACTLY ONE PRODUCTION CALLER OF `fit` AND IT PASSES NO `x0`

`batch/run.py:934` and `bench/spike.py:349` are the only `fit(` call sites in `src/`. Neither
passes `x0`. **So the signature change breaks no production path**, and the whole blast radius of
the hard error is test and harness code. Checked rather than assumed, because a second caller
would have made "hard error, never a default" a much more expensive decision than D3 priced it at.

### (a6) THE DOCSTRING THAT SURVIVES THE CHANGE SAYS THE SIGNATURE IS FIXED

`fit`'s own `x0` docstring reads *"Phase 2 supplies these; **the signature is fixed now** because
it constrains everything downstream."* That sentence is written under Phase 1's belief and plan
Task 0 falsifies it. **A description whose subject no longer exists reads as specification**, and
this one reads as a prohibition on the exact change the task exists to make. It is rewritten in
the same commit as the code, not swept later.

### (c3) `at_diagnostic_limit` IS THE RIGHT VALIDATOR AND IT DOES NOT REFUSE NaN

The brief asks for two refusals, and it is tempting to implement them as one call. Enumerating
what `params.ParamSpec.at_diagnostic_limit` rejects:

| input | verdict | is that what this caller wants? |
|---|---|---|
| `value <= lo` or `value >= hi` | True | yes — **at or beyond**, and an `OK` fit is strictly inside both limits by construction (`optimize_series` reports `DIAGNOSTIC_LIMIT` otherwise), so no legitimate warm-start source can sit on a limit |
| `inf` | True | yes, but reached only after the transform maps it there |
| **`nan`** | **False** | **no.** `nan <= lo` and `nan >= hi` are both False, so an all-NaN row — the single fault class D3 exists to make loud — **passes this validator silently** |

**So the finite check is a separate check and it runs first.** Folding the two into
`at_diagnostic_limit` alone would leave the sentinel defect exactly where D3 found it, behind a
validator that looks like it covers it.

### AND THE LIMITS ARE IN NATURAL UNITS WHILE `x0` IS UNCONSTRAINED

`diagnostic_limits` are natural-unit (`sigma` at `(1e-8, 1e8)`, `rho` at `(1e-6, 1e6)`); `x0` is
documented as *"warm starts in UNCONSTRAINED coordinates"*. **Comparing `x0` against
`diagnostic_limits` directly is a units error that would pass every test whose fixture sits near
`u = 0`** — `exp(0) = 1`, comfortably inside every limit, so the wrong comparison and the right one
agree over the whole healthy region. **(i7): the discriminating value is one whose unconstrained
and natural readings fall on opposite sides of a limit**, e.g. `u = log(1e7) = 16.118` for `rho`,
which is finite, inside the limits read as unconstrained, and **beyond** them read correctly.

The transform is `ParamSpec.to_natural`, applied column by column in `free_param_index` order —
which is what `ConcentratedObjective._map` does, so the validator uses the **same** per-parameter
bijector the optimizer does rather than a second path through the objective.

### (a0) THE PADDING IS A LEGITIMATE NaN AND THE VALIDATOR MUST NOT SEE IT

`x0` is `(B, M, p_max)` and `fit` slices `x0[b:b+1, c, :p]`. `p_max` is the **widest** candidate's
free-parameter count, so for any narrower candidate the columns `p:p_max` are **NaN by design** —
`FitResult.theta_unconstrained` is documented as NaN-padded and is the array that feeds back.
With this project's own `_candidates()` fixture, candidate 0 is `white` at `p = 1` against
`p_max = 3`: **two thirds of its row is legitimately NaN.**

**A validator that checks the full `p_max` width therefore raises on every well-formed warm start
for every candidate but the widest** — and it fails in the *safe-looking* direction, so it would
be "fixed" by relaxing the check rather than by narrowing it. The validator sees `:p` only, per
candidate. **This is (a0) inverted: here the fill value is legitimate and the error would be
treating it as data.**

### (a2) THE VALIDITY ARRAY MUST BE THE VALIDITY ARRAY, NOT SOMETHING THAT CASTS TO ONE

Task 3's interface is stated in the plan as three parallel `(B, M)` arrays:

    SourceMap.index    # (B, M) int64, -1 where exhausted
    SourceMap.valid    # (B, M) bool

**`bool(-1)` is `True` and `bool(0)` is `False`.** So passing `SourceMap.index` where
`SourceMap.valid` was meant, under a permissive `np.asarray(..., dtype=bool)`, marks **every
exhausted cell valid** and **every cell sourced from coarse index 0 invalid** — arrays the right
shape, values all finite, no exception, and a wrong warm start on exactly the cells the spiral
failed for. That is the Task 11 wrong-candidate-at-index-1 shape one field over, and the two
arrays will sit adjacent in Task 5's call.

**So `x0_valid` is required to be of boolean dtype and a non-boolean array is refused.** This is
an **addition to the brief**, recorded as such: the brief specifies the shape gate and not the
dtype gate. It costs one comparison and closes a silent-wrong-answer path between two tasks that
have not been written yet.

### "BOTH OR NEITHER" IS READ IN BOTH DIRECTIONS

The brief states the hard error one way — `x0` without `x0_valid` — and then states the rule as
**"Both or neither"**. `x0_valid` **without** `x0` is refused as well. It is not a harmless
no-op: it is a caller who believes they are warm-starting and is not, which is the (i2) shape —
"the mechanism did not run" and "the mechanism ran and found nothing" leaving the same output.

### (i8) THE FAULT CLASS MUST BE CONSTRUCTED, AND THIS PROJECT ALREADY OWNS THE CONSTRUCTION

*"An all-NaN row in a cell marked valid"* cannot occur through any correct code path, so a fixture
must build it. **`tests/test_fit.py::_mixed_batch` already produces it as a by-product**: rows
1–4 fail, so their `theta_unconstrained` is all-NaN across `:p`. Marking those cells valid is
literally *"a source map that marks a failed fit valid"* — the constructed defect the brief names,
built from a real failed fit rather than from hand-written NaNs.

### (i2) EVERY REFUSAL IN THIS TASK IS A PURE NEGATIVE AND GETS ITS POSITIVE CONTROL

Four of the six tests assert that something raises. **A raise is trivially producible by a
validator that raises on everything**, and this validator sits in front of the only path Tasks 3
and 5 use. Each refusal is paired with the same array minus the injected fault proceeding to a
normal fit — not merely "not raising", but returning `InitRung.WARM_START` on the cell in question.

### (a5) THE TASK DOES NOT BUMP `ALGORITHM_VERSION`, AND THE RULE WAS READ RATHER THAN RECALLED

`hashing.ALGORITHM_VERSION`'s rule is *"bump when and only when a change alters the value of
`theta_hat` or `log_lik` **for some input that previously fit**"*. Plan Task 0 leaves `x0=None`
bit-identical and leaves `x0` + all-true `x0_valid` bit-identical to today's `x0`; the only
changed input — `x0` alone — now **raises** rather than fitting differently. **No optimum moves.**
The plan assigns the bump to Task 1, where the stride does move `θ̂`. Checked because "the fit
signature changed" reads like a bump trigger and is not one.

### (k) NOTHING HERE DEPENDS ON PROCESS-LOCAL STATE

No randomness, no timing, no RSS. Every assertion in this task is exact equality or an exception.
**Plan Task 0 needs no measurement**, so none of the measurement protocol — host quiet check,
committed predictions, interleaved arms, fresh subprocess per RSS reading — applies. Stated
because the sub-phase's other tasks all do, and running it here would be ceremony.

### WHAT THIS TASK BREAKS OUTSIDE `src/`, NAMED RATHER THAN REPAIRED

Two instruments in `docs/superpowers/notes/` call `fit(x0=…)` and will raise after this change.
Neither is collected by pytest and neither is imported by `src/`, so **the suite does not see
them** — which is exactly why they are written down here instead of being discovered later.

- **`warmstart-stride-harness.py`** aborts the stride before calling `fit` if any cell is
  exhausted (`n_invalid` → `abort`), so **every cell it ever warm-starts has a source**. An
  all-true `x0_valid` reproduces its recorded numbers exactly.
- **`warmstart-spike-harness.py`** is **not** in that position. Its `self` arm passes
  `prep.theta_unconstrained` **unfiltered**, and that array is all-NaN for any cell whose prep fit
  was not `OK`. So the behaviour-preserving `x0_valid` there is *"finite over `:p`"* — and under
  D3 those cells would take the **moment ladder** instead of starting from NaN, which is a
  **different fit** from the one the recorded verdict measured.

**So neither harness is edited by this task.** Editing the stride harness is a no-op dressed as
maintenance; editing the spike harness silently changes an arm of a measurement whose verdict D1
rests on. The condition for closing this is stated instead: **whoever re-runs either harness
supplies `x0_valid`, and for the spike harness the treatment of non-`OK` prep cells is a design
choice that moves the `self` arm and must be recorded as one.**

### AND ONE EXISTING TEST ASSERTS THE OLD CONTRACT

`tests/test_fit.py::test_a_warm_start_is_recorded_and_actually_used` passes
`x0=np.nan_to_num(cold.theta_unconstrained, nan=0.0)` with no `x0_valid`. It must gain one, and
**the `nan_to_num` is the interesting part**: it exists to stop the padding NaNs reaching the
optimizer, which is the workaround D3 replaces. Under the `:p`-only validator the padding never
needs flattening at all, so the call becomes the honest one — `x0=cold.theta_unconstrained` with
an all-true `x0_valid` — and the fixture stops hiding the distinction between padding and failure.

---

## Plan Task 1 — the fit-relevant fields and the hash cascade, audited before any code

**THE BRIEF** is the plan's Task 1: `FIT_RELEVANT_FIELDS` **gains** the five warm-start settings;
the audit's settings stay out; the interpolation rule is fixed at nearest-valid, still exists and
is still hashed, with no config flag selecting it; `ALGORITHM_VERSION` is hand-bumped; and the
three `GOLDEN_*` constants **move** and are re-derived by hand and verified by reversal.

### (j4) THE FIRST FINDING IS THAT THE TASK IS ALREADY IMPLEMENTED, AND IT WAS FOUND BY GREP RATHER THAN BY `git log`

**`_WARM_START_FIT_FIELDS` has existed since 2026-08-11 — Phase 2a Task 1 — and is already unioned
into `FIT_RELEVANT_FIELDS`.** So has the audit exclusion, and so have the tests. Measured, not
read:

| change to the config payload | `fit_hash` moves? |
|---|---|
| `warm_start_coarse_stride` 8 → 16 | **yes**, `1eb1fd73…` → `30fc9d13…` |
| `warm_start_enabled` true → false | **yes**, → `df42f1bd…` |
| `warm_start_spiral_bound` 4 → 7 | **yes**, → `aefb203e…` |
| `warm_start_interpolation_rule` → a second rule | **yes**, → `a3ae05ef…` |
| `audit_subsample` 0 → 500 | **no** |
| `audit_stratify` false → true | **no** |

**The baseline reproduces `GOLDEN_FIT_HASH = 1eb1fd731b4ae8d6` exactly**, from a payload built by
hand in this pre-flight and not from the test fixture — so the golden and the live code agree
through a path that shares nothing with `tests/test_hashing.py`.

**And the tests the brief specifies already exist, in stronger form than it asks for:**
`test_the_warm_start_coarse_stride_moves_fit_hash` is the (a2) movement check;
`test_every_warm_start_setting_reaches_fit_identity` is **parametrized**, because one field is not
evidence about a set; `test_the_audit_settings_move_no_gate` is the paired negative and **names its
positive control by test name**; and `_HISTORY` in `tests/test_hashing.py` already carries the
2026-08-11 hop with the three pre-warm-start digests `faf2d107bab48b06 / bb28cb8d4bffa049 /
af313190251af95f`, reversed one hop at a time.

**This is CLAUDE.md's "verify implementation status" rule paying for itself.** A shallow
`git log` over 2c shows no warm-start-field commit, because the commit is in 2a.

### SO THE GOLDENS DO NOT MOVE, AND THE REVERSAL CHAIN GAINS NO HOP

The plan states as an invariant that *"the three `GOLDEN_*` constants move, and are re-derived by
hand and verified by reversal"*. **They move only if the hashed field set moves, and it does
not** — the field set moved on 2026-08-11, and the hop for that move is already in `_HISTORY`.
**Re-deriving them now would be regeneration with nothing to reverse against**, which is the
precise failure the reversal discipline exists to prevent. **Reported, not absorbed.**

**The one thing that WOULD move all three is an `ALGORITHM_VERSION` bump**, and
`tests/test_hashing.py` says so at the constants. Which is the next finding.

### (a5) THE BUMP BELONGS TO TASK 5, NOT TASK 1, AND THE PLAN'S OWN JUSTIFICATION IS FALSE OF TASK 1

The plan writes: *"`ALGORITHM_VERSION` is hand-bumped, per its docstring's rule — **this change
moves `θ̂` for an input that previously fit**."* Checked against the docstring's actual rule —
*"bump when and only when a change alters the value of `theta_hat` or `log_lik` for some input
that previously fit"* — **Task 1 alters no `θ̂`.** It has no code to write; adding a field to an
allowlist moves a **hash**, not an optimum, and the field is already there in any case.

**The change that moves `θ̂` is Task 5**, where `run` grows the two-pass mode and a default run
starts warm-starting. **Bumping at Task 1 would put the version boundary in a different place
from the behaviour boundary**, which is the same defect one task earlier: stores written between
Task 1 and Task 5 would carry the new version and cold fits, and stores after Task 5 the new
version and warm fits. **The plan's Task 5 does not currently mention the bump. That is the
correction.**

### AND THE DEFECT THIS EXPOSES IS ALREADY IN THE TREE, WITH `enabled` DEFAULTING TO TRUE

`WarmStart.enabled` defaults to **`True`**, is in `fit_hash`, and **nothing consumes it**:
`grep warm_start src/metamer/batch/run.py` returns nothing, and `run` calls `fit` with no `x0`.
So **every store written since 2026-08-11 records a fit payload carrying a warm-start REQUEST that
nothing honoured.**

> **CORRECTED 2026-08-24: this first read "asserting `warm_start_enabled: true` over fits that are
> entirely cold", which overstated it. The store is NOT silent.** `store.py` writes
> `warm_start_used` as an explicit run fact defaulting to `False` -- 2a's own pre-flight caught
> that reading it off `config.warm_start.enabled` would write `true` for a run that cannot
> warm-start -- and a test asserts it. **A reader can tell. But `warm_start_used` is an ATTR and
> not a GATE**: it is nowhere in `fit_hash`, so the resume gate cannot see it, and that is the
> half the bump closes. **Readable-and-ungated is a different defect from invisible.** After Task 5 the identical config produces warm-started
fits **under the same `fit_hash`** — converged-looking fits at a different optimum, resumed into
the same store, which is §11.1's worst failure mode arriving through the config rather than
through a stale cache.

**THE OBVIOUS REPAIR IS THE WRONG ONE, WHICH IS WHY IT IS WRITTEN DOWN.** `Screening` is *"present,
and refused at layer 3 until Phase 4"*, and mirroring that for `WarmStart` is the first thing a
reader reaches for. **It would refuse every run**, because unlike `screening.enabled` (default
`False`) this one defaults to `True`. **The closer is the `ALGORITHM_VERSION` bump at Task 5**: a
pre-bump store then mismatches on `fit_hash` and refits, which is exactly what the constant is
for. **Nothing else separates the two populations, and no store can be repaired after the fact.**

### THE REQUEST/IDENTITY CLASSIFICATION WAS MADE, AND NOTHING ENFORCED IT

> **CORRECTED 2026-08-24, same day, before Task 2. This heading first read "WAS NEVER MADE FOR
> THESE FIVE, BECAUSE THE VOCABULARY ARRIVED A DAY LATE", and that was false.** The sort was run
> over **all fourteen fields on 2026-08-11** and the five appear in its table in
> [`phase2a-preflight.md`](phase2a-preflight.md), classified `request`, source `user config`. The
> REQUEST/IDENTITY vocabulary is in the handoff's (a2) and predates them.

**What was missing was not the classification. It was any mechanism that made one compulsory.**
The classification lived in a pre-flight document; **nothing in `src/` encoded it and nothing
failed if a new field skipped it.** That is the gap this task closes, and it is (a2e).

**Found by applying this task's own promotion to itself.** (a2c) says: for each hashed field, name
the code that acts on it. Asked about a *rule* instead of a *field* — name the code that enforces
it — the answer was none.

**All five are REQUESTS**, and the distinction is about **who is authoritative**:

| class | who is authoritative | members | hazard |
|---|---|---|---|
| **REQUEST** | the config — the user is asking for something | `variable`, `signal_terms`, `objective`, `engine`, `seed`, and the five `warm_start_*` | none; the config cannot be wrong about what it asked for |
| **IDENTITY, STAMPED** | the installed code; `normalize` writes it and a config supplying it is **refused** | `algorithm_version`, `registry_version` | forgetting to bump — answered at the constant |
| **IDENTITY, MEASURED** | the input; read at stage 4a and unsupplied by any config | `geometry_hash` | none; the data cannot misreport itself |
| **IDENTITY, SELF-REPORTED** | **the config, about something outside it** | **must be empty** | `data_uri` and `metamer_version` both were this, and both were **wrong in both directions at once** |

**A CLASSIFICATION IN PROSE IS A CONVENTION AND THIS PROJECT HAS BEEN BURNED BY CONVENTIONS.**
(a2): the classification is made **executable** — the three classes are declared as constants and
a test asserts they **partition** `FIT_RELEVANT_FIELDS` exactly and are pairwise disjoint, so a
sixth field added without a classification **fails** rather than defaulting into the set. The
forbidden fourth class needs no constant: it is **whatever the partition does not cover**, and the
partition covering everything is what proves it empty.

### (a2) "NO CONFIG FLAG SELECTS IT" IS ALREADY TRUE, AND FOR A REASON WORTH NOT UNDOING

`interpolation_rule: Literal["nearest_valid"]` and `tie_break: Literal["lowest_yx"]`. The **field
exists and is hashed** — so a second rule can never silently share a store — while **no value
other than the shipped one is expressible**, which is §11.3's requirement. **Widening either
`Literal` is the change that breaks it**, and it will look like adding a feature.

**One asymmetry found, and it is small.** `test_every_warm_start_setting_reaches_fit_identity`
parametrizes four cases — `enabled`, `spiral_bound`, `coarse_stride`, `tie_break` — and **omits
`interpolation_rule`**, while its own docstring warns that *"a flattening that emitted four of the
five correctly and dropped one would sail through a single-field test"*. The field is covered by
the golden payload, where it appears by name, so nothing is unguarded — but the parametrization is
the place a reader checks for completeness, and **four of five in a test whose argument is
five-of-five is the shape that invites the wrong conclusion.** It gains the fifth case.

### THE STRIDE NOW LIVES IN TWO PLACES, AND TASK 1 OWNS ONLY ONE OF THEM

`warm_start_coarse_stride` is a **request** consumed twice: pass 2's `fit_hash` (Task 1's half,
already in place) and **pass 1's input decimation** (Task 2's). **Task 1 must not assume the two
agree because one was derived from the other** — D11 makes pass 1 a separate store with its own
identity, and the plan's **Task 4** owns the cross-store gate, which *"checks the stride explicitly
and positionally, never by assuming one was derived from the other"*. **Confirmed: Task 4's brief
already states it, so no ownership gap exists** — recorded because the hash moving on the stride
reads like the check, and it is not. A hash proves two **configs** agree; it says nothing about
what a **store on disk** was actually decimated at.

### (d) AND THE VOCABULARY CHECK, WHICH IS HOW THE FIRST FINDING WAS FOUND

`rg 'warm_start' src/metamer/config/` and `rg 'FIT_RELEVANT_FIELDS' src/metamer/core/hashing.py`,
run **before** reading the brief's behaviour clauses. Both returned the mechanism the brief
proposes to add. **Running the vocabulary grep first is what turned a task into an audit.**

---

## Plan Task 2 — pass 1 as a run over a decimated input, audited before any code

**THE BRIEF** is the plan's Task 2 (D11): pass 1 is **the existing mechanism applied to a
different input**, `isel(y=slice(0, None, k), x=slice(0, None, k))`, with its own store, its own
bitmap and its own resume; the decimation is index arithmetic on dataset coordinates and therefore
independent of tiling and of `--memory-budget`; pass 1's store records the parent's geometry
fingerprint and the stride and **is a permanent second artifact, not scratch**; everything else is
unchanged.

### (i8) THE BRIEF'S OWN `isel(y=…, x=…)` IS A NAME-BASED DECIMATION AND THE INPUT CONTRACT DOES NOT REQUIRE THOSE NAMES

**This is the finding of this pre-flight.** `input.check_input_contract` requires exactly three
dimensions and that **`array.dims[0] == "time"`**. It says nothing at all about the names of dims
1 and 2 — the contract is *"three, mapping to (time, y, x)"*, which is **positional**. A real
altimetry product routinely names them `latitude`/`longitude`, `lat`/`lon` or `nj`/`ni`.

**AND EVERY FIXTURE IN THIS REPOSITORY USES `("time", "y", "x")`.** Sixteen call sites across
`test_tiling`, `test_write`, `test_runner`, `test_resume`, `test_store`, `test_reuse`,
`test_memory`, `test_input`, `test_exit_criteria` and `test_exit_criteria_2b` — **no exceptions.**

So a name-based decimation **passes the entire suite and fails on the first real input**, with an
`xarray` `ValueError` naming a dimension the user never mentioned. That is (i8)'s first shape: the
fault class is **not constructible with any fixture the project currently owns**. **The decimation
reads `array.dims[1]` and `array.dims[2]`**, and the test that makes it bite is a fixture whose
spatial dims are named something else — the first such fixture in the project.

#### AND THE SAME SHORTCUT IS ALREADY TAKEN THROUGHOUT `tiling.py`, WHICH MAKES THIS A PRE-EXISTING DEFECT RATHER THAN ONE THIS TASK INTRODUCES

**The first draft of this entry said "checked: `assemble_tile` and `geometry_components` index
positionally, so the exposure is the decimation this task adds". That was wrong, and it was
written before the code was read.** `tiling.py` uses the literal names in four places:

    tiling.py:904-905   ("y", tile.y_start, tile.y_stop), ("x", tile.x_start, tile.x_stop)
    tiling.py:932-933   _aligned_spans(..., by_dim["y"]) / by_dim["x"]
    tiling.py:973-974   array.isel(y=slice(...), x=slice(...))

**So the whole tiling and assembly path already requires the spatial dims to be literally `y` and
`x`, while stage 4a accepts any names as long as `time` is first.** An input with
`latitude`/`longitude` **passes the contract** and then dies deep inside `assemble_tile` with a
raw `xarray` `ValueError` — **not an `InputContractError`, so not exit code 4**, which violates
`input.py`'s own stated rule that *"EVERY STAGE-4a FAILURE MUST BE AN `InputContractError`"*.

**THIS IS NOT TASK 2's TO FIX AND IT IS REPORTED RATHER THAN ABSORBED.** Two closers exist and
choosing between them is a scope decision:

| closer | cost | what it says the contract is |
|---|---|---|
| **stage 4a enforces the names** | one refusal, one message | the contract is `("time", "y", "x")` literally, and the docstring's *"mapping to"* is the thing that is wrong |
| **the tiling path goes positional** | four sites plus fixtures | the contract is positional as written, and `tiling.py` is the thing that is wrong |

**What Task 2 controls is not adding a fifth site**, so the decimation reads `array.dims[1]` and
`array.dims[2]`. That is the correct arithmetic under either closer and changes nothing for a
`y`/`x` input, so it neither pre-empts the decision nor widens the exposure. **It does not make
`latitude`/`longitude` inputs work** — tiling still refuses them — and this entry says so, because
a positional decimation sitting above a name-based assembler otherwise reads as support.

**AND THE FIXTURE THAT WOULD CATCH ANY OF THIS DOES NOT EXIST**, which is why sixteen call sites
could agree on an unrequired convention for the life of the project.

### (a5) "ITS OWN FINGERPRINT IS DERIVABLE FROM THOSE TWO" IS FALSE AS WRITTEN, AND THE TRUE VERSION IS CHEAPER

The brief says pass 1's store *"records the parent's geometry fingerprint and the stride, and its
own fingerprint is **derivable from those two**"*. **A hash is not invertible**, so nothing is
derivable from a fingerprint. What is true is one level down:

- the decimated **components** are a pure function of the parent's **components** and `k` — shape
  divides, `dims`/`variable`/`source_dtype`/`calendar`/`time_coordinate` are unchanged, and the
  spatial coordinate arrays are the parent's every `k`-th value;
- and the fingerprint is a function of the components.

**The tempting implementation is the expensive one.** `geometry_components` is already a
`REQUIRED_ATTR` and holds **full coordinate value arrays** — 10 800 numbers for a 3600 × 7200 grid
— so "record the parent's geometry so the derivation can be checked" reads as *store the parent's
components too*, doubling that for no gain. **The store records the parent's HASH (16 hex
characters) and the stride (one integer)**, which is all Task 4's cross-store gate needs; and the
**reproduction is done in a test**, which has the parent dataset and can decimate it directly.
**Derivable-in-principle and stored-for-checking are different requirements** and only the second
costs bytes.

### THE BIT'S INVARIANT HOLDS UNCHANGED, AND IT IS CONFIRMED RATHER THAN ASSUMED

*"Same mechanism, different input"* is the whole of D11's argument, which makes it exactly the
claim that turns out to have an exception. Checked at the two places a parent grid could leak in:

| mechanism | what it is bound to | verdict |
|---|---|---|
| `completion.completed_tiles` / the bitmap | the **store's** `StoreShape`, fixed at creation | a tile is a tile of whatever grid the store was created for |
| `completion.resume_tile_side(grid=…)` | *"`(n_y, n_x)` **from the input contract**"*, and it refuses *"if its bitmap does not describe this grid"* | the contract is taken from the **decimated** handle, so each store is guarded against its own grid |

**So the bit keeps its meaning — "every region write for this tile returned" — as a claim about
the decimated grid.** Nothing carries a parent grid into either. **The confirmation is the
kill-and-resume test**, not this table: a reading establishes that no parent grid is referenced,
and only a run establishes that the resume refits exactly the outstanding tiles.

### `resume_tile_side` GUARDING EACH STORE INDEPENDENTLY IS CORRECT AND READS AS WRONG

A memory-budget change between passes is **legal**, and it produces **different tile sides in the
two stores** — pass 1's grid is `1/k²` the size, so the same budget derives a different side
anyway. **Someone will read two stores with different tile sides as a bug and "fix" it by forcing
one side across both**, which would either exceed the budget in one pass or refuse a resume that
is geometrically identical. **One line where the guard is documented**, at the point the second
store's side is derived, saying that the divergence is the design.

### PASS 1'S STORE IS PERMANENT, AND THE NAMING IS WHERE THAT GETS DECIDED

It is the **cold audit reference** (§11.2) and the `/detail/` default source, so **it cannot be
deleted after pass 2 completes**. A second directory beside an output is read as scratch unless
something says otherwise, and the place a reader looks is **the name and the code that derives
it** — not a design document. **The rule is stated at the derivation, in the docstring of the
helper that performs it, and in the user-facing README.**

### (a0)'s THIRD REGISTER: THE TWO NEW ATTRS ARE OPTIONAL, AND NO SCHEMA BUMP IS OWED

`create_store` refuses on `attrs.get(key) is None` for `REQUIRED_ATTRS`, so a new **required**
attr would refuse every store written before it. `parent_geometry_hash` and `coarse_stride` are
present **only on a decimated store**, and their **absence means "not a pass-1 store"** — the
`source_*` and `calibration` precedent.

**A bump is for a question an older store CANNOT ANSWER, and every earlier store's silence here is
unambiguous: nothing before this task could produce a decimated store at all.** Same reasoning,
and same conclusion, as the calibration provenance block. **Stated because "new attr, therefore
bump" is the reflex**, and `SCHEMA_VERSION` 5 exists because the opposite reflex was wrong once.

### (a2c) APPLIED IMMEDIATELY: THE RECORDED STRIDE MUST BE THE ONE THE CODE ACTED ON

The rule this sub-phase just promoted — *for each hashed or recorded field, name the code that
acts on it* — applies to the field this task adds. **The stride is read from
`config.warm_start.coarse_stride` and the same value performs the decimation and is written to the
attrs**, so there is exactly one source and no within-run mismatch is expressible. Passing a
stride as a separate parameter would create a second source that could disagree with the config
the store's `fit_hash` was computed from, which is the defect one layer up.

**The CROSS-store mismatch remains possible and is not this task's** — a pass-1 store built under
one config consumed by a pass-2 run configured differently. **Task 4 owns it and already specifies
the check as explicit and positional**, never inferred from one having been derived from the other.

### AND PASS 1'S OWN `fit_hash` CARRIES WARM-START SETTINGS THAT DID NOT APPLY TO IT

Pass 1 is a **cold** run whose `fit_hash` includes `warm_start_enabled: true`. **That is (a2c)
again, one level down, and it is benign here for a reason worth stating rather than assuming:**
the stride *did* act on pass 1 — it chose the decimation, hence the grid, hence which points were
fit — and that effect is independently captured in pass 1's own `geometry_hash`. `enabled` is
genuinely inert for pass 1, and what separates a pass-1 store from a pass-2 store is the presence
of `parent_geometry_hash`, not a hash field. **After Task 5's unconditional bump,
`algorithm_version` separates the eras regardless.**

---

## Plan Task 3 — the source map, audited before any code

**THE BRIEF** is the plan's Task 3 (D3, D12): §11.3's rule implemented once, in the batch layer.
Nearest valid coarse point in index space, ties **lowest `y` then lowest `x`**, searched outward in
a **fixed spiral** until a coarse point with an `OK` fit **for that candidate** is found; a coarse
point's own source is **itself at radius 0**, as a property of the geometry and not an exception;
the spiral is **bounded** and exhaustion marks the cell **invalid**; and the **source coarse index
is recorded per point.**

### (j2) THE MEASURED INSTRUMENT IS THE SPECIFICATION HERE, AND IT SAYS TWO THINGS NO OTHER DOCUMENT DOES

`warmstart-spike-harness.py::spiral_source` is what produced D1's verdict and D6's stride curve.
**Whatever it did IS the mechanism those numbers describe**, so any production rule that differs
from it makes the measurements describe something that was never built. Two of its choices appear
in **no** other document — not the plan, not the design doc, not the config:

1. **THE DISTANCE IS CHEBYSHEV.** `max(abs(r - tr), abs(c - tc))`. The plan says only *"nearest
   valid coarse point in index space"*, which reads equally as Euclidean or Manhattan — and the
   three disagree about which source a point gets. At a target diagonally between two coarse
   points, Chebyshev calls a diagonal neighbour and an axis neighbour **equidistant** where
   Euclidean does not, so the **tie-break fires in cases Euclidean never reaches.** Since the
   tie-break exists to make `θ̂` independent of tiling, choosing the metric silently would change
   which cells that guarantee is even exercised on.
2. **THE RADIUS IS INCLUSIVE.** `range(max_radius + 1)`.

**Both are now stated in the implementation's own docstring and pinned by a test**, because they
were recoverable only by reading a file under `docs/`.

### (a5) AND THE BOUND'S UNIT DISAGREES BETWEEN THE CONFIG AND THE INSTRUMENT

`WarmStart.spiral_bound` is documented as *"Maximum search radius, **in coarse index steps**,
before the search gives up"*, default **4**. The harness's `max_radius` is in **fine index units**
and was passed **`n_side`** — the whole field — at both fixtures.

| | unit | value used |
|---|---|---|
| shipped config field | coarse index steps | 4 |
| the instrument that measured D1 and D6 | fine index units | `n_side`, i.e. **unbounded** |

**THE UNIT IS FIT IDENTITY**, because `warm_start_spiral_bound` is in `FIT_RELEVANT_FIELDS`: two
runs agreeing on the integer 4 and disagreeing on what it counts produce different `θ̂` under one
`fit_hash`. **It has to be pinned, and the config's reading wins** — it is the shipped field and
its docstring is the specification; the harness's argument was a convenience, not a decision. The
conversion is `max_fine_radius = spiral_bound * stride`, which makes a bound of 4 mean **four
coarse rings**, and is what the words "coarse index steps" mean.

> **AND THE CONSEQUENCE FOR THE MEASURED NUMBERS IS STATED RATHER THAN LEFT IMPLICIT: D1 AND D6
> WERE MEASURED WITH NO EFFECTIVE BOUND.** So they describe a run in which **the bound never
> bit**, and they say nothing about behaviour where it does. At `k = 8`, `bound = 4` reaches 32
> fine cells, so the bound bites only where a 9 x 9 coarse neighbourhood — 81 coarse points — is
> **entirely failed for that candidate**. **That is a rare regime, not an impossible one**: a
> large ice-covered or land region is exactly that shape. **The exhaustion count is therefore a
> reported outcome and not a diagnostic afterthought**, which is what the plan already asks for,
> and this is the reason.

### (i7) THE SEARCH IS PER CANDIDATE, AND A UNIFORM `coarse_ok` CANNOT TEST IT

`ok[i, cand]` in the harness; `x0_valid` is `(B, M)` for the same reason. **A coarse point can be
`OK` for one candidate and failed for another**, and a per-point search would collapse to
all-or-nothing and discard usable sources.

**A fixture whose `coarse_ok` is uniform across the candidate axis cannot distinguish a per-cell
search from a per-point one** — this is (i12) at the level of one array rather than a fixture set.
**The fixture makes candidate 0 and candidate 1 fail at DIFFERENT coarse points**, so a
per-point implementation returns the wrong source for at least one of them.

### THE TWO ARRAYS ARE CONSTRUCTED TOGETHER, BECAUSE TASK 0 ALREADY PAID FOR THEM DISAGREEING

`SourceMap.index` is `int64` with **-1 where exhausted**; `SourceMap.valid` is `bool`. Task 0
required `x0_valid` to be of boolean dtype precisely because **`bool(-1)` is True and `bool(0)` is
False**, so passing `index` where `valid` was meant inverts the array's meaning in both
directions.

**The dtype gate catches the SWAP. It cannot catch the two arrays disagreeing at source**, which
is a different defect: an `index` of -1 beside a `valid` of True is a cell the fit will be handed
a source for that does not exist. **So `valid` is DERIVED from `index` in one expression
(`index >= 0`) rather than accumulated in parallel**, and a test asserts the identity holds
element by element. Two arrays maintained by two loops is how they come to disagree.

### THE INDEX'S REFERENT IS THE COARSE GRID, NOT THE FINE ONE, AND IT IS NOT STATED ANYWHERE

The plan says *"the source coarse index is recorded per point"* without saying what it indexes.
Two candidates: a flat row-major index into the **coarse** grid, or one into the **fine** grid.
**It must be the coarse grid**: that is what indexes pass 1's store, which is the array Task 5
reads the warm start out of. A fine-grid index would need dividing by the stride at every use, and
the division is exactly where an off-by-one enters.

**AND D12 MAKES THE CHOICE LOAD-BEARING**: the recorded index is what lets a downstream reader
**filter to self-sourced points and test the lattice directly**, rather than discovering it as a
spatial signal. A self-sourced fine point `(y, x)` with `y % k == x % k == 0` must record
`(y // k) * n_coarse_x + (x // k)` at radius 0 — an equality a test can assert, and cannot if the
referent is ambiguous.

### (k) TILE-INDEPENDENCE IS MADE STRUCTURAL RATHER THAN TESTED INTO EXISTENCE

The plan's invariant — *"the source map depends on dataset coordinates alone, asserted by
constructing it at two tile sides and comparing element by element"* — is the guarantee §11.3
rests on, and *"the single most likely way to lose the reproducibility guarantee"* is building the
map from **tile-local** indices.

**A test comparing two tile sides catches it; a construction that cannot express it is better.**
So the coarse geometry is derived from the **full fine grid shape**, always, and the region being
mapped is a separate argument that shifts **which** points are answered and never **what** the
answer is. The search runs in absolute fine-grid coordinates. **The test stays**, because a
structural argument is a claim until something fails when it is untrue.

### (a7) THE OBVIOUS IMPLEMENTATION IS THE HARNESS'S AND IT IS UNUSABLE AT PRODUCTION SCALE

The harness rebuilds the candidate ring by **scanning every coarse point** at every radius:
`O(n_coarse)` per ring, per point, per candidate. At `n_side = 96` that is fine. At `10^7` fine
points with `k = 8` there are `1.56 x 10^5` coarse points, and the same code is `~10^12`
operations. **It was a correct instrument and it is not an implementation** — (a3)'s bargain
running the other way, and worth stating because "the harness already does this" is the obvious
shortcut.

**The structure that makes it cheap is a property of the lattice: only `k²` distinct residue
classes exist.** A fine point's offsets to the coarse lattice depend only on `(y % k, x % k)`, and
within a ring, ordering by **absolute** `(y, x)` is the same as ordering by **offset**, because
every candidate shares the target's base. So the ordered offset list is precomputed once per
residue class — at `k = 8, bound = 4` that is 64 lists of at most 81 entries — and each point
walks its class's list. **The ordering is identical to the harness's by construction, and a test
compares the two implementations point by point on a fixture the harness can still afford.**

### WHAT WOULD MAKE THIS TASK'S TESTS VACUOUS, NAMED IN ADVANCE

- **A fixture where every coarse point is `OK`.** Exhaustion is then unreachable, the bound is
  never tested, and radius is 0 or 1 everywhere. **The fixture has a failed region large enough to
  force a multi-ring search, and a second one large enough to exhaust.**
- **A stride that divides the grid exactly.** Then the last coarse point sits on the last fine
  row and the edge case where a fine point has **no coarse point below or right of it** never
  occurs. **The fixture's grid size is deliberately not a multiple of the stride.**
- **A square grid.** `n_y == n_x` makes a transposed index and a correct one agree. **Not square.**

---

## Plan Task 4 — the barrier and the cross-store gate, audited before any code

**THE BRIEF** is the plan's Task 4: pass 2 may not start until pass 1 is complete, and may not
consume a pass-1 store that is not the one its configuration describes. The barrier is
`completed_tiles(pass1_store).all()` — **an existing, tested predicate, no new completion
concept**. The gate checks the **stride explicitly and positionally**, the **parent geometry
fingerprint**, and the **candidate set positionally**. Refusals **name what would lift them**.

### (a5) THE BRIEF ENUMERATES THREE CHECKS AND THE FIT IDENTITY HAS TWELVE FIELDS

The gate as specified compares the stride, the parent geometry and the candidate set. **It says
nothing about the other nine members of `FIT_RELEVANT_FIELDS`** — `objective`, `engine`, `seed`,
`variable`, `signal_terms`, `algorithm_version`, `registry_version`, and the **four remaining
warm-start settings.**

**A warm start taken from a store fitted under a different objective is exactly as wrong as one
taken at a different stride**, and it is wrong in the same silent way: every array the right
shape, every value finite, every status `ok`, and `θ̂` at an optimum of a different likelihood.
**An enumerated gate is a denylist wearing an allowlist's clothes** — it protects the fields
somebody thought of, and the ones added later default to unprotected. That is the shape (a2e) was
promoted for.

> **AND THIS TASK'S OWN FINDING FROM TASK 3 IS THE PROOF.** `spiral_bound`'s unit was ambiguous
> until yesterday. **If pass 1 and pass 2 disagree about what `spiral_bound` counts, the warm
> starts are wrong** — and a gate that checks only the stride would pass that through. Whatever
> the gate checks about the stride it must check about **every** fit-relevant field, and the only
> construction that survives a field being added is one derived from the allowlist rather than
> from a list somebody maintains.

### THE COMPLETE CHECK IS ONE EQUALITY, AND THE GEOMETRY DIFFERENCE CANCELS EXACTLY

The obvious complete gate — *compare the two stores' `fit_hash`* — **always fails**, because
pass 1's `fit_hash` is computed over the **decimated** `geometry_hash` and pass 2's over the
**parent's**. That difference is the whole point of pass 1 and is not a mismatch.

**The cancellation is available and it is exact.** Both passes can compute
`config.fit_hash(parent_geometry_hash)`: pass 1 knows the parent rollup because it opened the
parent before decimating, and pass 2 computes it directly. **So pass 1 records
`parent_fit_hash = config.fit_hash(parent_rollup)`, and the gate is `parent_fit_hash ==
config.fit_hash(this run's rollup)`.** One equality, covering **every** field in the allowlist —
including ones nobody enumerated and ones not yet added — with the geometry difference subtracted
rather than special-cased.

**IT IS NOT A SELF-REPORTED IDENTITY** (a2). It is a hash of the config pass 1 **actually ran
under**, paired with the geometry of the input pass 1 **actually opened**. Both are facts about
pass 1, recorded by pass 1.

### BUT A HASH CANNOT NAME WHAT DIFFERS, AND THE PLAN REQUIRES THAT IT DOES

*"Refusals name what would lift them. A refusal that says what would lift it is planning
information; one that does not is a wall."* **A digest mismatch is a wall.**

So pass 1 records **`parent_fit_payload`** as well — the allowlist subset of its own payload with
the parent rollup substituted, about a dozen small values — and the gate diffs it **key by key**
to name the first difference. **This is a deliberate duplication and the store already contains
its precedent**: `geometry_components` sits beside `geometry_hash` for exactly this reason, §13.3
requiring that *"a mismatch has to be diagnosable from the store alone"*. **A test asserts
`digest(parent_fit_payload) == parent_fit_hash`**, so the two cannot drift.

**And the key SETS are compared before the values**, or a field present in the allowlist and
absent from the stored payload is a comparison that silently does not happen — (a0)'s
excluded-versus-missing register, at a diff with a carve-out.

### THE STRIDE KEEPS ITS OWN NAMED REFUSAL, AND THE REDUNDANCY IS DELIBERATE

The key-by-key diff would already name `warm_start_coarse_stride`. **The stride is checked
separately anyway**, because the two refusals carry different information: a generic diff says
*"this field differs"*, while the stride's own message can say **what it does** — a pass-1 store
built at stride 4 consumed by a run configured for stride 8 produces **a valid-looking source map
with every index in range and every warm start taken from the wrong cell**, which is the Task 11
wrong-candidate-at-index-1 shape one field over.

**Both guards are cross-commented, each naming the other**, per the standing rule: a later
simplification will otherwise remove one on the grounds that it is dead, and it is dead only
because the other is there.

### (a0) AND TASK 2's `coarse_stride` ATTR BECOMES A SECOND COPY, SO IT GOES

Task 2 recorded `coarse_stride` as a standalone attr. Once `parent_fit_payload` carries
`warm_start_coarse_stride`, **the store holds the stride twice** — and two copies of one value
drift the moment either is written from a different place. **The standalone attr is removed and
the payload is the single source.** No store exists yet, so nothing is invalidated; Task 2's test
moves with it.

**Recorded rather than done quietly**, because it edits a decision made one task ago.

### THE BARRIER IS THE EXISTING PREDICATE, CONFIRMED BY READING RATHER THAN ASSUMED

D11's whole argument is that **nothing acquires a second meaning**, so the barrier must be
`completion.completed_tiles(pass1_store).all()` and not a reimplementation. Checked: the function
exists, is tested, and reads the store's own bitmap — and the bits are bound to the store's
`StoreShape`, which for pass 1 is the decimated grid. **So "complete" means the same thing it
means everywhere else, about a different grid.**

**The refusal names the OUTSTANDING TILES, not the count.** A count is a wall; a list of tile
indices tells the user which region to re-run and is what makes *"resume pass 1"* actionable.

### (i2) EVERY REFUSAL HERE IS A PURE NEGATIVE AND NEEDS ITS POSITIVE CONTROL

Five refusals, and each one is trivially producible by a gate that refuses everything. **Each is
paired with the same fixture minus the injected difference proceeding** — not merely "not
raising", but the gate returning and the consuming run reaching the warm-start path. The plan
already demands this for the stride; it applies to all five.

### WHAT WOULD MAKE THIS TASK'S TESTS VACUOUS, NAMED IN ADVANCE

- **A pass-1 store built by hand rather than by `run(decimate=True)`.** Then the attrs are
  whatever the test wrote, and the gate is checked against a fixture rather than against the
  thing it will actually meet. **The fixtures come from real runs.**
- **A single-tile pass-1 store.** `completed_tiles(...).all()` on a one-tile store is `True` after
  one write, so an incomplete store cannot be constructed. **The barrier fixture is multi-tile**,
  which Task 2 already had to solve — the coarse grid fits in one tile at the default budget.
- **A candidate set of one.** A permuted candidate list is the same list when there is one
  candidate, so the positional comparison cannot be distinguished from a set comparison.

---

## Plan Task 5 — the two-pass driver, audited before any code

**THE BRIEF** is the plan's Task 5 plus [*What plan Task 5 inherits*](../../../PROGRESS.md):
`run` grows a two-pass mode — decimate, fit cold, barrier, fit warm — with no new tiling, no new
store schema and no warm-start cache. Warm-starting is disableable by config and its use is
recorded in provenance. `ALGORITHM_VERSION` is hand-bumped here, unconditionally, in its own
commit, moving all three `GOLDEN_*` constants. 2c computes and records the source-index array,
the exhaustion count, the ladder-rung distribution and the two passes' wall clocks. Pass 1's
store is read one tile's worth of sources at a time and never loaded whole, asserted by peak RSS.
README's two-pass documentation falls due here.

### (a4) THE BRIEF'S WORKED EXAMPLE FOR UNCONDITIONALITY DOES NOT DEMONSTRATE A COLLISION

The requirement is right and is implemented as written. **Its stated justification is not**, and
recomputing it is what (a4) is for.

The brief says: *"A user who disables warm-starting after Task 5 gets cold fits again — and their
pre-Task-5 store also holds cold fits, under a `fit_hash` computed from the same field values, so
a conditional bump lets the two collide."* Walk it. A pre-Task-5 store written with
`warm_start.enabled = false` holds cold fits under `algorithm_version = "1"`. The same
configuration after this task, under a bump made conditional on `enabled`, would not bump, so it
also holds cold fits under `"1"`. **The two populations are therefore bit-identical** — nothing on
the cold path moves in this task; Task 0 already established that a false validity cell is
bit-identical to `x0=None` — **so their sharing one `fit_hash` is correct reuse and not a
collision.** The example describes the one case in which a conditional bump would be right.

**WHERE THE COLLISION ACTUALLY IS: `enabled` DEFAULTS TO `True`.** A pre-Task-5 store written at
the default holds **cold** fits under `algorithm_version = "1"`; the same configuration after this
task produces **warm-started** fits, and with **no** bump the resume gate accepts the store and the
two populations mix inside it — converged-looking fits at two different optima. That is the
failure, it arrives through the default rather than through a user disabling anything, and it is
closed by *any* bump.

**SO UNCONDITIONALITY NEEDS A DIFFERENT ARGUMENT, AND THERE ARE THREE.**

1. **`ALGORITHM_VERSION` is a `STAMPED_IDENTITY_FIELD`, and the installed code is authoritative
   for it.** Reading it off `warm_start_enabled` makes the installed code's identity a function of
   a **request** — the self-reported-identity class `FIT_RELEVANT_FIELDS` names as the fourth class
   and says must stay empty. `data_uri` and `metamer_version` were both that.
2. **It would be a second copy of a value already in the payload.** `warm_start_enabled` is in
   `FIT_RELEVANT_FIELDS` in its own right, so a version string that varies with it records one
   fact twice, and two copies drift the moment either is written from a different place.
3. **The constant's own docstring is a statement about a CHANGE, not about a run**: *"when and only
   when a change alters the value of `theta_hat` or `log_lik` for some input that previously fit."*
   Some input previously fit does move. That is the whole test, and it has no configuration in it.

**THE COST IS OVER-INVALIDATION, AND THAT IS WHAT "SEPARATES ERAS" MEANS.** A store built before
this task with `enabled = false` holds fits this task does not move, and the bump invalidates it
anyway. **That is accepted, not overlooked**: an era boundary is coarser than the set of values
that actually changed, which is the price of a hand-bumped constant over a per-field one.

### (a5) THE GOLDENS ARE FIVE AND THEY LIVE IN TWO FILES, NOT THREE IN ONE

The brief says the bump *"moves all three `GOLDEN_*` constants"*. Grepped:

| file | constants | payload strings |
|---|---|---|
| `tests/test_hashing.py` | `GOLDEN_FIT_HASH`, `GOLDEN_COMPAT_HASH`, `GOLDEN_RUN_HASH` | `GOLDEN_FIT_PAYLOAD`, `GOLDEN_COMPAT_PAYLOAD`, `GOLDEN_RUN_PAYLOAD` |
| `tests/test_config.py` | `GOLDEN_FIT_HASH`, `GOLDEN_COMPAT_HASH` | `_GOLDEN_FIT_PAYLOAD`, `_GOLDEN_COMPAT_PAYLOAD` |

**Five hashes and five hand-written strings move, not three and three.** The two files' *fit*
goldens are deliberately the same value — that identity is the claim `test_config.py` exists to
make, that a config off disk produces the same payload as a hand-built mapping — but the two
*compat* goldens are **different values**, because the two modules' fixtures name different
criterion sets. Neither is a copy of the other, so neither can be updated by copying.

**AND THE REVERSAL DISCIPLINE EXISTS IN ONE FILE ONLY.** `_HISTORY` and
`test_the_goldens_reverse_through_the_allowlist_history` are `test_hashing.py`'s;
`tests/test_config.py` has no chain, so *"`_HISTORY` gains a hop"* leaves its two goldens
re-derived and **unreversed**. A pasted value is indistinguishable from a derived one there.
**Closed here rather than recorded**: `test_config.py` gains its own one-hop reversal, asserting
that substituting `"algorithm_version":"1"` back into each of its two hand-written strings
reproduces `1eb1fd731b4ae8d6` and `8e7c1e4c82d36022` exactly. That is the same evidence `_HISTORY`
provides, at the two constants `_HISTORY` does not reach.

### (a7) "THE SOURCE-INDEX ARRAY" IS A FIELD-SIZED TERM AND THIS TASK'S OWN INVARIANT FORBIDS ONE

The `--explain` bullet asks 2c to *"compute and record the source-index array, the exhaustion
count, the ladder-rung distribution and the two passes' wall clocks"*. Three of those four are
scalars or small histograms. **The first is `(B, M)` over the whole grid**: at 10⁷ points with
M = 2 candidates and int64 indices, 10⁷ × 2 × 8 = **160 MB** retained for the length of the run —
against the same task's invariant that *"peak RAM is derivable from the memory budget alone"* and
its refusal of a source read that *"grows with the field"*. **The bullet and the invariant cannot
both be satisfied**, and the invariant is the one the design doc states.

**RESOLUTION: THE AGGREGATES ARE RECORDED AND THE PER-POINT ARRAY IS NOT RETAINED.** The source
map is built per tile, consumed by that tile's fit, and dropped; what survives is the exhaustion
count, the source-radius histogram, the init-rung distribution and the per-pass wall clock — all
`O(1)` in the field. A per-point source map is a **spatial** diagnostic and its home is the store,
which this task's own Goal forbids extending.

**AND THE STORE'S ROOT ATTRS CANNOT HOLD THE AGGREGATES EITHER, WHICH IS A FORCED ANSWER RATHER
THAN A PREFERENCE.** `create_store(attrs=...)` writes the root attrs **once, at creation, before
any tile is fitted**, and a resumed run does not rewrite them. Counts accumulated during the tile
loop therefore have no honest slot there: writing them at creation records zeros, and writing them
at the end either overwrites the previous run's counts or needs a merge rule — a new durability
problem in a task whose Goal is *"no new store schema"*. **So they go in `RunReport`**, alongside
`tiles_written`, and they are a fact about the **run** rather than about the store: on a resume
they cover the tiles this run fitted and no others, exactly as `tiles_written` does.

`warm_start_used` is different and stays in attrs: it is known **before** the loop, which is why
`store.provenance_attrs` could already take it.

### THE INVARIANT SAYS "NEVER LOADED WHOLE" AND ONE ARRAY STILL MUST BE

Task 3's `source_map` takes `coarse_ok` over the **full** coarse grid and validates its shape
against the full fine `shape`. That is not incidental: *"building the map from tile-local indices
is named in the plan as the single most likely way to lose §11.3's guarantee"*, and a full-grid
`coarse_ok` with absolute coarse indices is what makes tile-independence structural rather than
tested into existence. **So pass 1's `/status/outcome` is read whole, and the invariant as written
forbids that.**

**THE MAGNITUDES, BECAUSE A DEVIATION WITHOUT ONE IS NOT REVIEWABLE.** At design doc §9.4's
3600 × 7200 grid with `k = 8` the coarse grid is `len(range(0, 3600, 8)) = 450` by
`len(range(0, 7200, 8)) = 900`, i.e. **405 000 coarse points**. At 2a's fixture candidate set
(`white`, `white + matern12`: M = 2, `p_total` = 4):

| array | dtype | whole-store bytes |
|---|---|---|
| `/status/outcome` | uint8 × M | 405 000 × 2 = **810 kB** |
| `/warmstart/theta_unconstrained` | float64 × `p_total` | 405 000 × 4 × 8 = **12.96 MB** |
| one fine tile, for scale | float64, side 272, N = 630 | 272² × 630 × 8 = **372.9 MB** |

**This task reads the second per tile and the first whole**, so the term it removes is 16× the
term it leaves. **The residual is real and still grows linearly with the field**, and it is
recorded rather than fixed: narrowing it means passing `source_map` a halo slice with translated
indices, which is the tile-local-index construction Task 3 was written to prevent. **Changing that
contract is Task 3's decision, not this task's.** Deferred item, with its magnitude.

### (i8) THE PLAN'S RSS ASSERTION CANNOT BE WRITTEN AGAINST A WHOLE RUN, AND THE OBSTACLE IS ABSOLUTE SIZE

*"Pass 1's store is not loaded whole, asserted by peak RSS against a bound at a field size where
whole-loading would be visible."* Whole-loading exceeds one fine tile when
`(n_y n_x / k²) · p_total > side² · n_time`, which a small grid satisfies easily — at `k = 2`,
`p_total = 4`, `n_time = 24` and `side = 4` it holds above 384 fine points. **But the ratio is not
the difficulty; the absolute figure is.** On a 32 × 32 fine grid the whole coarse
`theta_unconstrained` is 256 × 4 × 8 = **8 kB**, which no RSS difference can see, and a fine grid
large enough to make it megabytes is hours of fitting.

**SO THE SUBJECT OF THE MEASUREMENT IS THE READER, NOT THE RUN.** The assertion is on the function
that reads a tile's warm starts, measured in a child process against a pass-1 store whose whole
`theta_unconstrained` is **20.48 MB** — 800 × 800 coarse points, `p_total` = 4, float64 — where one
tile's sources at fine tile side 64, `k = 2` and `spiral_bound = 4` cover a 40 × 40 coarse
footprint, **51.2 kB, a factor of 400 below.** The bound sits between the two.

**THAT STORE IS BUILT BY `create_store` AND DIRECT ARRAY WRITES, NOT BY A RUN, AND THE BARRIER'S
DISCIPLINE DOES NOT EXTEND TO IT.** `tests/test_barrier.py` requires every pass-1 store to come
from a real `run(decimate=True)` because **its** subject is the attrs a writer records. This
subject is **byte volume**, about which a hand-built store of the right shapes and dtypes is the
same object; and 640 000 coarse series cannot be fitted in a test. The positive control is the
same child reading `array[:]` and breaching the bound (i2), so the fixture is shown to be able to
express the defect it is placed against.

### (c) A SIGTERM DURING PASS 1 MUST EXIT 2, AND THE BARRIER WOULD MAKE IT EXIT 3

Pass 1 is a `run`, so it honours SIGTERM and returns `interrupted=True` with tiles outstanding.
**If the driver then calls the barrier, `check_pass1_complete` raises `ValidationError` and the
command exits 3 — "your configuration is wrong" — for a run that was preempted and is resumable.**
The two send a user to entirely different places, and 14.3's exit 2 is *"aborted early —
resumable"*, which is exactly what happened. **The driver returns after an interrupted pass 1
without entering the barrier**, with no pass-2 report, and the command line maps that to
`ABORTED_EARLY`. The barrier keeps its refusal for the case it was written for: a pass-1 store
that is incomplete for a reason this invocation did not witness.

### (a5) `warm_start.enabled = false` AND A SUPPLIED SOURCE MUST NOT BE SILENTLY RECONCILED

`run(warm_start_from=...)` with `config.warm_start.enabled` false is a request that contradicts
itself, and either half could be honoured. **Refused at layer 3, naming both**, on the standing
precedent of the `--calibrate`-with-`--reuse-fits-from` and `--calibrate`-with-`engine=` refusals:
a flag that parses and does nothing reads as supported. The config's `false` is what makes the
whole two-pass path a single cold run; it is not an argument the driver may quietly override.

### (a2c) TWO OF THE FIVE WARM-START FIT FIELDS GAIN CONSUMERS HERE, AND TWO STILL HAVE NONE

Grepped for each of `_WARM_START_FIT_FIELDS`' five config sources:

| field | consumer before this task | after |
|---|---|---|
| `coarse_stride` | `run.py`, the decimation | unchanged |
| `enabled` | **none** — the defect the bump closes | the driver's cold/warm branch |
| `spiral_bound` | **none** in production; `source_map`'s parameter had only test callers | passed by the tile loop |
| `interpolation_rule` | none | none |
| `tie_break` | none | none |

**The last two are not (a2c) defects and the reason is their type.** Both are single-member
`Literal`s, so no second value exists for a consumer to discriminate — they are declared regimes
(a3), and `warmstart.py` implements exactly `nearest_valid` with a `lowest_yx` tie-break. **Stated
because the handoff names `enabled` alone and the sweep found `spiral_bound` beside it**, which is
the field whose unit Task 3 had to settle.

### (a6) `pass1_store_path`'s DOCSTRING ALREADY CLAIMS README CARRIES THE RULE

`decimate.pass1_store_path` says of the permanent-artifact rule: *"It is in `README.md` for the
same reason."* **It is not.** Task 2 deliberately deferred the README paragraph — there was no
user-reachable two-pass entry point — but the docstring was written in the present tense against a
fact that had not happened. This task creates the entry point and writes the paragraph, which
makes the sentence true; recorded because a claim that shipped ahead of its fact is the same shape
as a comment describing code nobody wrote.

**AND README'S STATUS BLOCK IS STALE IN THREE PLACES, NOT ONE.** *"Phase 1 complete"*, *"588
tests"* and *"Not yet built: `metamer.batch` and `metamer.cli`"* in **Status**; *"Only the first
exists today"* in **Planned structure**; and **Where to look** lists no Phase 2 document at all.
The handoff says this must not *silently* become Task 5's scope and must not be left uncorrected.
**Both are satisfied by doing it loudly and separately**: the sweep lands in its own commit, named
as the (a6) debt it is, and not folded into the two-pass paragraph.

### THE CANDIDATE-SUPERSET HAZARD IS CLOSED BY AN EXISTING GATE, READ RATHER THAN RECALLED

Pass 1's `theta_unconstrained` is unpadded onto a **ragged** axis whose blocks come from pass 1's
candidate list. If pass 2 could run with a **superset** — which §12.8 permits in general, and which
is the stated reason `candidates` is in no allowlist — then `RaggedIndex.block(m)` for an added
candidate would address past the end of pass 1's axis. **Checked in the code rather than assumed**:
`resume._check_candidates` refuses a requested list that is shorter **and** one that is longer, the
second naming that extension *"needs fits that do not exist"*. The barrier imports that same
comparison, so the two stores always share a candidate count and pass 1's ragged index **is**
pass 2's. Nothing is owed here; the hazard is recorded so a later loosening of that gate knows what
else it would move.

### (k) NOTHING NEW DEPENDS ON PROCESS-LOCAL STATE, WITH ONE NAMED EXCEPTION

The source map is a pure function of the full grid, the stride, the bound and `coarse_ok`; the warm
start values are float64 in a store; `fit` reads `x0[b : b+1, c, :p]` per series. **Neither tile
side nor traversal order nor thread count can reach `θ̂` through this path**, which is what the
two-budget bitwise test asserts. The exception is the per-pass wall clock, which is process-local
by definition — it is provenance, reaches no hash and no store, and is reported and never compared.

### (e2)/(i2) THE MUTATIONS TO RUN, AND EACH MUST BE SHOWN TO DIFFER FIRST

Before any of these is recorded as caught, the mutant is shown to change some output — a surviving
mutation that could not have changed anything is not evidence about the suite.

1. **The source map built from the tile's own extent** rather than the full grid with a `region`.
   Differs wherever a tile boundary does not fall on a coarse point; caught by the two-budget
   bitwise test.
2. **`x0_valid` rebuilt as `index >= 0` at the call site** instead of taken from `SourceMap.valid`.
   Cannot differ today — it is the same expression — so it is **not** a mutation this suite can
   catch, and saying otherwise would be (e2) exactly. Recorded as unprovable rather than as caught.
3. **The barrier dropped from the driver.** Differs on a partial pass-1 store; caught by the
   incomplete-pass-1 test.
4. **`warm_start_used` read off `config.warm_start.enabled`.** Differs on pass 1's own store, which
   is cold under a config whose `enabled` is true; caught by asserting pass 1's attr is false.
5. **The whole-array read in the source reader.** Differs by 20.4 MB of peak RSS; caught by the
   reader's bound, with the whole-read as its own positive control.

### WHAT WOULD MAKE THIS TASK'S TESTS VACUOUS, NAMED IN ADVANCE

- **A single-tile pass 2 in the two-budget test.** One tile per budget makes "the tiling does not
  reach `θ̂`" a statement about two identical traversals. **Both budgets are asserted multi-tile and
  asserted to derive DIFFERENT sides** — equal sides would make the comparison vacuous in the other
  direction, and neither is visible from a green suite.
- **A fixture in which no point is warm-started at all.** Every assertion about the warm path then
  passes against the cold one. **The init-rung distribution is asserted to contain
  `InitRung.WARM_START`** in the enabled run and **not to** in the disabled one; that is the one
  discriminator that cannot be satisfied by a cold run.
- **Asserting that warm and cold `θ̂` DIFFER.** They need not: agreement is the property §11.2's
  audit exists to measure, and a test demanding disagreement would fail on a well-behaved fixture
  and pass on a broken one. The rung distribution is the discriminator instead.
- **A pass-1 store with every coarse fit `OK`.** Exhaustion is then unreachable and the count is
  asserted at zero forever. The count's arithmetic is exercised at unit level against a constructed
  source map with `-1` entries, and the end-to-end case asserts zero **with** that unit control
  beside it — a zero reading is not evidence of absence, (a0)'s fifth register.
- **A pass-1 store whose grid is a multiple of the stride**, or **square**. Both were named at
  Task 3 and both apply again wherever a coarse index is turned back into a `(row, column)` pair:
  `n_cx` and `n_cy` are interchangeable on a square grid, so a transposed decode reads correct.
  **The fixtures stay non-square and not stride-aligned.**

---

## Plan Task 6 — the audit's arms and the four-reading table, audited before any code

**THE BRIEF** is the plan's Task 6 and D7: measure hysteresis against a **designed floor** rather
than against zero. Three arms beside `warm` — **N2**, cold from a perturbation whose magnitude
equals that cell's own warm/cold start distance in unconstrained coordinates and whose direction is
random, matched **per cell**; **N1**, cold from the moment-ladder start perturbed by a tiny ε; and
**no cold-versus-cold arm**, because `fit` has no stochastic component and re-running cold measures
zero by construction. The four-reading table is written into the audit's own documentation
**before** the arms run. N2's seed is recorded. Task 0's `random` arm is **not** this control.

### (i7) THE AUDIT'S SUBJECT CANNOT BE THE COARSE POINTS, AND THREE RECORDED DECISIONS ASSUME IT IS

**This is the finding that decides what Task 6 builds**, and it is a collision between decisions
rather than a gap in one.

D5 lists *"cold audit reference"* among pass 1's four surviving jobs. D6's table calls it **"THE
BINDING CHECK"** on the stride. D10 discharges that check with an occupancy table computed over
**the coarse point count** — `10⁷ / 64 = 156 250`, and `156 250 / 30 = 1 in 5 208`. **All three
read the audit's subject as pass 1's coarse set, with pass 1's store as the free cold arm.**

**D12 makes that set the one place the effect cannot appear.** A coarse point's nearest valid
coarse source is **itself**, at radius 0 — geometry, not a special case — so pass 2's `warm` fit at
a coarse point starts from **pass 1's own converged optimum for the same series and the same
candidate**. Comparing the two there asks *"does restarting the optimizer from its own optimum move
it?"*, which is **convergence idempotence, not hysteresis**: there is no neighbour in the
comparison at all.

**AND D12 ALREADY MEASURED IT, WHICH IS WHY THIS IS ARITHMETIC RATHER THAN AN ARGUMENT.** `self`
against `cold` is **239/240 = 99.58%** with `|Δℓ|` **exactly zero at 43%** of cells and a maximum of
**1.24e-07**, against **95.00%** for fine points — *"the lattice signal is ≈ 4.6 percentage points
of excess cold-likeness"*. **An audit drawn from the coarse set is a fixture placed exactly where
the two functions agree** — (i7), and in its strongest form: those points carry **none** of the
effect, not merely less of it.

**SO THE SUBJECT IS A SUBSAMPLE OF FINE POINTS AND THE COLD ARM IS COMPUTED, NOT READ.** No cold
fit exists on disk for a fine point, and the one that does exist is at the unrepresentative points.
**63 of every 64 shipped answers are neighbour-sourced**, and those are what §11.2 asks about.

> **THREE CONSEQUENCES, AND ALL THREE POINT THE SAME WAY, SO NOTHING MOVES.**
>
> 1. **The stride stops binding the audit.** D6's *"binding check"* rests on the audit drawing from
>    the coarse set. It does not, so `k` constrains the audit's sample size **not at all** — the
>    size is `audit.subsample`, chosen. **`k = 8` is strengthened, not threatened.**
> 2. **D10's occupancy table becomes conservative by a factor of `k²`.** Its members were coarse
>    points; the real population is the whole grid, **64× larger**, so every threshold in that
>    table is 64× easier to clear. Its conclusion — *"stratum adequacy is a property of FIELD SIZE,
>    not of the stride"* — holds **a fortiori**, and the 30-member rule with (a2b)'s
>    unavailable-rather-than-caveated handling is unaffected.
> 3. **Pass 1's "cold audit reference" job survives in a narrower and still useful form.** It is a
>    **free, global, permanent** cold fit at 1/64 of the field, and its use is as a **cross-check
>    on the audit's own cold arm**: a freshly computed cold fit at a coarse point must reproduce
>    pass 1's stored one bitwise. That is a genuine cross-check by **(j5)** — same quantity, same
>    conditions, same code — unlike the calibration cross-check D5 rejected on exactly that test.

**Recorded in D5, D6 and D10 rather than only here**, because three decisions carry a reading of
one word — *"the audit's sample"* — that this task is the first to have to act on.

### N1 AND N2 MUST SHARE THE RANDOM DIRECTION, OR THE TABLE'S SECOND ROW DOES NOT FOLLOW

The brief specifies N2's direction as random and says only *"perturbed by a tiny ε"* of N1. **The
table's second row reads `N1 zero, N2 non-zero → the sensitivity is to start DISTANCE, not
direction`**, and that inference is valid only if the two arms differ in **nothing but distance.**

Give N1 a fixed direction — all-ones, or the first coordinate — and a non-zero N2 beside a zero N1
has two available explanations: the magnitude, or the fact that N2 happened to move in a direction
the surface is sensitive to and N1 did not. **The reading the table promises is then unavailable,
and the arms were run anyway.**

**So N1 is N2's direction at magnitude ε.** One draw per cell, two magnitudes. The three arms are
then a **magnitude ladder along one ray** — `ε`, `r`, and the warm start's actual displacement —
which is exactly what rows 1 and 2 discriminate, and it costs nothing.

### THE ε IS DERIVED, NOT PICKED, AND ITS DERIVATION SETTLES WHAT ROW 1 MEANS

`ε = gradients.fd_step(1.0) = eps^(1/3) = 6.055e-06`, **in unconstrained coordinates**, which is
the space N1 perturbs and the space `fd_step`'s own docstring states its result in.

**It is not a small number chosen to be small.** It is **the smallest displacement the optimizer's
gradient can resolve**: `optimize_series` differentiates with `fd_gradient(..., curvature=None)`,
whose ratio is one at every scale, so the step it actually takes **is** `eps^(1/3)`. A start moved
by less than that is a start the first gradient evaluation cannot distinguish from the unmoved one.

**That is what makes row 1 readable.** *"N1 non-zero"* then means the answer moved under a
displacement the optimizer cannot see — i.e. **the surface has structure below the resolution of
the method**, which is precisely *"the surface is deciding, no start is reliable"*. A picked ε of
`1e-3` would make row 1 mean *"the surface has structure at 1e-3"*, which is an ordinary property
of a likelihood and would fire everywhere.

**Per the standing rule, the exponent is read off the path and not copied from a neighbour**: this
is a first difference (`m = 1`), so `eps^(1/(m+2))`, the same construction as `fd_step` and **not**
`X_RANK_RTOL`'s `eps^(1/2)`, which thresholds a squared quantity and happens to be the familiar
`2⁻²⁶`.

### (k) A SEQUENTIAL RNG MAKES THE AUDIT DEPEND ON TRAVERSAL ORDER, WHICH IS THE ONE PROPERTY 2c PROTECTS

N2 is *"the only randomness in the system"*, so it is also the only place §11.3's
traversal-independence can now be lost — and the natural implementation loses it. **Draw from one
`Generator` in a loop and cell `n`'s direction depends on how many cells were drawn before it**,
hence on the subsample's order, hence on tiling if the audit ever tiles. Recording the seed does
**not** save it: the same seed with a different order gives different directions, so the audit
would be reproducible only under a fixed traversal that nothing enforces.

**The direction is keyed, not streamed.** Each cell's generator is seeded from
`(seed, global point index, candidate index)` through a `SeedSequence`, so the draw is a **pure
function of the cell** — order-independent, subsample-size-independent, and reproducible from the
recorded seed alone. **The point index is the GRID-GLOBAL flat index, never a position within the
subsample**, or enlarging the subsample changes every existing cell's direction and two audits of
one store cannot be compared.

**This is `source_map`'s tile-independence argument at a second mechanism**, and it is structural
in the same way: there is no traversal for the answer to depend on.

### (a2) THE ARM'S IDENTITY CANNOT COME FROM `init_rung`, BECAUSE N1 AND N2 REPORT `warm_start`

`optimize_series` sets `rung = InitRung.WARM_START` **whenever `x0` is supplied**, without asking
where it came from. N1 and N2 supply an explicit `x0`, so **all three perturbed arms come back
labelled `warm_start`** and the cold arm comes back `moment`/`clipped`/`default`.

**That is not a defect in `optimize_series`** — from its side "a start was supplied" is exactly what
the rung means — but it makes `init_rung` **unusable as the arm label**, which is the obvious
shortcut. The arm is the audit's own; `init_rung` is recorded beside it as what the fit reported
and is never read back as identity. **(a2), a name that is not a gate**, one layer out from the
place this project keeps finding it.

### (c3) THE ADMISSIBILITY RULE ALREADY EXISTS AND MUST NOT BE WRITTEN A THIRD TIME

**N2's start can leave the admissible region, and then `fit` REFUSES THE WHOLE CALL.**
`_check_warm_starts` raises `ValueError` if any cell marked valid is non-finite or at or beyond a
diagnostic limit — so a single unlucky direction at a large `r` aborts the entire audit rather than
losing one cell. The perturbation is unbounded in principle: `r` is a real distance and the
diagnostic box is finite.

**Enumerating what that validator refuses, against this caller's purpose** — (c3):

| it refuses | right for N2? |
|---|---|
| non-finite in a valid cell | **yes** — a start that is not a number is not a start |
| natural-unit value at or beyond a diagnostic limit | **yes, and for the audit's own reason**: a start there is one no legitimate source produces, so a fit from it measures the validator's absence rather than the surface |
| only the first `p` columns per candidate | **yes** — the padding is NaN by design |

**So the rule is reused, and the repair is to give it one derivation with two consumers.** The
predicate is factored out of `_check_warm_starts` into a `(B, M)` admissibility computation that
the refusal uses to decide **and** to build its message; the audit takes the mask. Writing a
vectorised twin in the audit would be the **third** spelling of the limits rule — `_out_of_limits`
already exists as the second, and it is pinned by a test for exactly this reason.

**AND AN INADMISSIBLE CELL MUST NOT BE HANDLED BY SETTING `x0_valid = False`**, which is the
one-line fix and is (a0)'s fourth register: a false cell **falls back to the moment ladder**, so the
N2 arm would silently contain **cold** fits and *"N2 agrees with cold"* would be true by
construction at exactly the cells where the perturbation was largest. **One array is built —
admissibility — and it is both what `x0_valid` is derived from and what masks the results
afterwards**, so the two cannot disagree. The count is reported.

### THE DEGENERATE CELLS, NAMED IN ADVANCE BECAUSE EACH LOOKS LIKE AGREEMENT

- **`r = 0`.** A cell whose warm start equals its ladder start has **N2 ≡ N1(ε) ≡ cold** up to the
  ε step. It contributes *"N2 agrees"* while measuring nothing. **Counted separately.**
- **The spiral exhausted the cell.** No warm start, so no distance, so **N2 is undefined** — and
  the cell is not warm-started either, so it is outside the question. **Excluded and counted**, not
  folded in as agreement.
- **A cell whose `warm` or `cold` fit did not return `OK`.** The comparison has no operands. This is
  the fixture fact promoted at Task 5 one level on: **a valid warm start is not a warm start used**,
  and here an arm that ran is not an arm that produced a comparable answer.

### THE WARM ARM IS RECOMPUTED, NOT READ, AND THAT BUYS A CROSS-CHECK

Reading pass 2's stored `θ̂` is cheaper and is the wrong choice: the other three arms come from a
fresh `fit` call in this process, and comparing a stored result against three fresh ones is a
comparison across conditions — **(j5)**. All four arms come from the **same batch, the same call
site and the same session**, which is the discipline that saved the stride sweep from a spurious
15% when cold was re-run rather than reused across sessions.

**And because it is recomputed, it can be checked**: the audit's `warm` arm must reproduce pass 2's
store **bitwise** at the audited points. That single assertion validates the whole audit path
against the shipped one — the source map, the reader, the ragged unpacking and the fit — and it is
free.

### (a5) THE SUBSAMPLE SELECTOR IS NOT THIS TASK'S, AND SAYING SO KEEPS THE ARMS TESTABLE

`Audit.subsample` is *"how many points the audit compares"* and **has no consumer** — (a2c), and it
stays that way after this task. **Which** points is D9's stratification question and the plan's
Task 7. So the arms take an **explicit point set** from their caller: the selection policy is not
baked into the arms, and a test can place points where it needs them rather than accepting whatever
a selector returns. **A fixture that cannot choose its own cells could not construct the degenerate
cases above.**

**No CLI flag lands here either.** There is nothing to print until Task 7 has a report, and *"a flag
that parses and does nothing reads as supported"* is the rule `--reuse-fits-from` and `engine=` were
both held to.

### (c6), ONE DAY AFTER PROMOTING IT: THE AUDIT-BOUNDARY TEST ENUMERATES TWO FIELDS

`Audit` needs a **seed** — D7 requires it recorded, and it is an audit setting, so it must reach
`run_hash` and **neither gate**. `tests/test_config.py::test_the_audit_settings_move_no_gate` is
what enforces that boundary, and it is written as

    _WITH + "\n[audit]\nsubsample = 500\nstratify = true\n"

— **an enumeration of the two fields that existed when it was written.** Adding `seed` leaves it
uncovered, and the test still passes: the mechanism only ever ran where it was installed. **The
repair is to derive the field list from `Audit`'s own model fields**, so a field added later is
covered without a second edit — (c5)'s construction at a test rather than at a gate.

### (d) THE VOCABULARY, AND ONE COLLISION WORTH DECLARING

Grepped: **`N1`, `N2` and "hysteresis" as an implemented thing appear nowhere in `src/`** — the
audit's vocabulary is entirely new, so nothing is being reused under a different meaning.

**But "arm" is already taken.** `reuse.py`, `resume.py`, `calibration.py` and `memory.py` all use it
for a **branch of a conditional** — *"the recompute arm"*, *"the stored > derived arm"*. The audit
uses it in the **statistical** sense, which is D7's word and the one the subject needs.
**Declared in the audit module's docstring rather than renamed**: two meanings of one word in one
codebase is worth a sentence, and inventing a synonym for the plan's own term is worse.

### (g) AND ONE INTERFACE THIS TASK NEEDS THAT DOES NOT EXIST YET

**The ladder start is not obtainable from any public path.** `optimize_series` computes it inline —
`moment_init(spec, y, mask, t)` then `objective.to_unconstrained(start_natural)[0]` — and
`FitResult` records the **rung** but not the **start**. N1 and N2 both need it.

**Recomputing those two lines in the audit is a second derivation of the thing the test
`N1 at ε = 0 is bit-identical to cold` depends on**, and it would fail for a reason that is not a
defect the first time either line moves. **So the two lines are extracted into `optimize.py` and
`optimize_series` calls the extraction** — one derivation, two callers, the pattern `RunGeometry`
already carries. It is a change in `core/` inside a task about the audit, and it is stated here
rather than made quietly.

### WHAT WOULD MAKE THIS TASK'S TESTS VACUOUS, NAMED IN ADVANCE

- **An audit run over coarse points only.** Every arm agrees, every reading is row 4, and the suite
  is green — the (i7) finding above, as a test fixture. **The fixture's points are fine points**,
  and that they are is asserted.
- **A fixture whose warm/cold distances are all equal.** N2's per-cell match is then
  indistinguishable from a match on the mean, which is the exact defect the plan names. **The
  fixture is asserted to carry more than one distinct `r`.**
- **A fixture where every `r` is small.** N2 then never leaves the admissible box, the inadmissible
  path never runs, and its handling is untested. **Its own constructed case**, with an `r` large
  enough to push a start past a diagnostic limit.
- **Asserting N2's magnitude in aggregate.** `‖perturbation‖ == r` is asserted **cell by cell**, as
  the plan requires; a mean over cells is satisfied by a control that is wrong everywhere and right
  on average.
- **A one-candidate fixture.** The direction is drawn per `(point, candidate)` and `p` differs
  between candidates — 1 and 3 at 2a's set — so a single candidate cannot show a direction drawn
  at the wrong width, and a `p = 1` candidate alone cannot show a direction that is not a unit
  vector.
- **Testing the seed with one seed.** *"The same seed reproduces N2 bitwise"* is satisfied by an
  implementation that ignores the seed entirely; the paired negative — **a different seed gives a
  different N2** — is what makes it bite, and the plan asks for both.

### (a2c) AND THE SEED THE AUDIT MUST NOT USE IS THE ONE ALREADY CALLED `seed`

`Config.seed` exists, is documented as *"seed for anything stochastic"*, defaults to 0 — **and is
in `FIT_RELEVANT_FIELDS`.** Grepped: **nothing in `src/` reads it.** `fit` has no stochastic
component, which is D7's own reason a cold-versus-cold arm cannot exist, so the field has had no
consumer since it was declared — (a2c), populated with nothing acting on it.

**THE AUDIT IS THE FIRST THING IN THIS PROJECT THAT NEEDS RANDOMNESS, AND `config.seed` IS THE
OBVIOUS FIELD TO REACH FOR. IT IS THE WRONG ONE.** It is fit identity, so N2's seed reaching it
would mean **re-running the audit at a different seed invalidates the store the audit is
auditing** — precisely the failure `_WARM_START_FIT_FIELDS`' boundary exists to prevent, and which
`tests/test_config.py` already asserts against for `subsample` and `stratify`. D7 says the seed is
*"fit-relevant for the audit arm and for nothing else"*, which is the audit block and not the top
level.

**So the field is `audit.seed`, and `config.seed` is left alone.** Filling in an unused field
because it has the right name is (a2) — a name is not a gate — and it would be the second time a
plausible-looking value entered fit identity through its name rather than through its role, after
`data_uri` and `metamer_version`.

---

## Plan Task 7 — the audit's strata and its report, audited before any code

**THE BRIEF** is the plan's Task 7 with D8, D9 and D10: each metric crosses only axes at its own
granularity — selection disagreement per **point** by margin × winning candidate, `|Δℓ|` /
parameter distance / signed-trend per **cell** by candidate × `κ`. Fixed external boundaries, `κ`
binned by the **cold** arm, failure status a partition rather than a stratum, the outcome flip with
its own denominators per candidate, the both-OK intersection reported as a fraction, per-stratum
only with a max-over-strata headline, and a stratum below 30 members reporting its count instead of
a rate — visibly.

### (i7) THE `κ` AXIS IS DEGENERATE ON THE POPULATION IT STRATIFIES, AND THE BOUNDARY IS THIS PROJECT'S OWN OK/FAILED CUT

**This is the finding that decides what Task 7 can honestly report, and it is arithmetic rather
than a judgement.**

Four facts, each read off the tree rather than recalled:

1. `optimize.HESSIAN_COND_LIMIT = float(EPS) ** -0.5`. **Measured: `67108864.0`, and
   `== 2.0**26` is `True`.**
2. `optimize_series` returns `Outcome.DEGENERATE_HESSIAN` — **not `OK`** — for every fit whose
   `float(np.linalg.cond(hessian)) > hessian_cond_limit` (`optimize.py:667`).
3. `fit` writes `loglik`, `theta`, `theta_unconstrained` and `theta_err` **only** where
   `result.outcome is Outcome.OK`; everything else stays NaN (`fit.py:449`).
4. D9's per-cell metrics are defined on the **both-OK intersection**, and D9's first `κ` boundary
   is **`2²⁶`**.

**So the first `κ` boundary and the OK/`DEGENERATE_HESSIAN` cut are the same number, derived the
same way, from the same `eps`.** Every cell the audit can compute `|Δℓ|` on has a cold `κ` of at
most `2²⁶`. **Bin `[2²⁶, 2⁵²)` can hold only a cell whose `cond(H)` is exactly `2²⁶`** — `>` is
strict — **and bin `≥ 2⁵²` is strictly empty.** Two of the four bins are unreachable by
construction, not by fixture.

**THE `undefined` BIN IS NOT EMPTY, AND THAT IS WHAT SAVES THE AXIS FROM BEING A NO-OP.** D9 defines
it as a **non-positive-definite** Hessian, and `optimize_series` never tests positive definiteness —
it thresholds `cond`, which is a ratio of singular values and is finite for an indefinite matrix.
A finite-difference Hessian at a converged optimum with one near-zero eigenvalue can come back
indefinite and well-conditioned, be reported `OK`, and reach the audit. **So the axis is really
binary — well-conditioned-and-PD against not-PD — and it must be reported as four bins anyway,
because D9 fixes the boundaries and Task 7 implements them rather than choosing them.**

> **WHAT IS OWED IS THE VISIBILITY, NOT A NEW BIN.** *"Zero cells in the two ill-conditioned bins"*
> reads as a fact about the field and is a fact about `HESSIAN_COND_LIMIT`. **The report records,
> beside the boundaries, that bins 2 and 3 are unreachable given the outcome taxonomy** — same
> argument as `RSS measurement validity` printing at zero, and the same argument D8 makes for the
> withheld pooled figure. **Nothing about D9 moves**; a decision is not re-taken because its
> implementation exposed an arithmetic consequence.

### (g) AND `κ` HAS NO PRODUCER: `FitResult` THROWS THE HESSIAN AWAY

`SeriesFit.hessian` exists, `fit` inverts it once for `theta_err` (`fit.py:460`) and **keeps neither
the matrix nor its condition number.** `Detail`'s own docstring already says so in as many words —
*"the Hessian at the optimum is not stored"*. **D9's stratification axis has no value to read.**

Two ways to get it, and the choice is not stylistic:

- **Recompute in the audit** via `hessian_at_optimum` at `theta_unconstrained`. It is a second call
  site for a number `optimize_series` already computed and discarded, and — the deciding
  objection — **the number the audit bins by would no longer be provably the number the
  OK/`DEGENERATE_HESSIAN` verdict was made on.** A cell could be `OK` and bin as ill-conditioned.
- **Surface it from where the threshold is applied.** `SeriesFit` gains `hessian_cond`, `FitResult`
  gains a `(B, M)` array of it. **One derivation, at the site that already owns the rule**, so the
  bin and the outcome cannot disagree by construction.

**The second, and it is a `core/` change inside a task about the audit — stated here rather than
made quietly.** The plan's own line *"this is the only `metamer.core` change 2c requires"* (Task 0)
is **false as of this task**, and that is a deviation reported rather than absorbed.

**IT DOES NOT BUMP `ALGORITHM_VERSION`, AND THE RULE WAS READ RATHER THAN RECALLED.** The constant's
docstring says bump *"when and only when a change alters the value of `theta_hat` or `log_lik` for
some input that previously fit"*, and explicitly excludes *"the reporting layer"*. `hessian_cond` is
computed from a matrix the optimizer already built, is fed back into nothing, and moves no optimum.
**No bump.** Both new fields also acquire a consumer in this same task, so neither is (a2c).

### §11.2's PER-TERM PARAMETER DISAGREEMENT IS MANDATORY AND APPEARS IN NEITHER D9 NOR THE BRIEF

§11.2 states it as a consequence, not a suggestion: *"The audit must report per-term parameter
disagreement separately from the aggregate, or a pure label-switching signal is averaged into the
parameter-disagreement metric and attributed to warm starting."* **D9's per-cell row says
"parameter distance" and stops**, and the plan's Task 7 brief repeats D9.

**The design doc is authoritative on INTENT and this is intent**, so the per-term split ships. It
costs one more axis on one metric — per `(candidate, κ bin, free parameter)` — and without it the
audit's single most alarming published number, **max parameter distance 154 SE**, has no way to be
told apart from a label-switching artifact.

### §11.2's PARAMETER DISTANCE IS IN UNCONSTRAINED COORDINATES AND THE ONLY SE IN `FitResult` IS NATURAL

*"Distance in unconstrained coordinates, normalized by estimated standard error."* `theta_err` is
the **natural-unit** standard error — `cov_u` pushed through `delta_method_cov` (`fit.py:461`).
**Dividing an unconstrained distance by a natural-unit SE is a unit error**, and it is the kind that
produces a plausible number: both arrays have the same shape and neither is NaN.

`fit` already holds `cov_u = inv(result.hessian)` on the line above. **`sqrt(diag(cov_u))` is the
unconstrained SE and is one line at a site that already has the matrix** — so `FitResult` gains
`theta_err_unconstrained` beside `hessian_cond`, and the metric is computed in one coordinate
system throughout. (a2d) at a metric rather than at a hash: the **unit** is part of what the number
means.

### THE FOUR METRICS ARE NOT ALL RATES, AND THE 30-MEMBER RULE IS ABOUT THE ONES THAT ARE

D8's 30 is derived from **a binomial standard error of ~9% at `p = 0.5`**. That derivation applies
to a proportion and to a mean; **it does not apply to a maximum**, which is an exact statement about
the members present rather than an estimate of a population parameter.

| metric | per-stratum statistic | 30-member rule |
|---|---|---|
| selection disagreement | **rate** | applies |
| rescue / loss | **rate** | applies |
| `\|Δℓ\|` | **maximum** | does not — a max over 3 members is a true max over 3 members |
| parameter distance (SE), aggregate and per term | **maximum** | does not |
| signed-trend disagreement | **mean signed difference** | applies |

**THE MEAN SIGNED DIFFERENCE IS COVERED BY D8's RULE RATHER THAN BY AN EXTENSION OF IT.** Its
standard error scales as `1/√n` for exactly the reason a rate's does, so it is *"a value invalid
under a condition the code can detect"* — (a2b), made unavailable and replaced by the count.

**AND `|Δℓ|` IS REPORTED AS A MAXIMUM RATHER THAN AS A THRESHOLDED RATE, WHICH IS A DEPARTURE FROM
§11.2's WORDING.** §11.2 says *"`|ℓ_warm − ℓ_cold|` above a threshold"*; **no such threshold exists
anywhere in this project**, the spike harness's `0.01` was picked and its code is not in the tree,
and inventing one here would be a quantile boundary by another name — a constant chosen with the
audit's answer in view, which D9's whole boundary argument forbids. **The maximum answers §11.2's
question — *"different optimum or same optimum to different precision"* — strictly more
informatively than a rate against a threshold, and it needs no constant.** Recorded as a departure
from the wording, in service of the intent.

### THE SIGNED HEADLINE CANNOT BE A MAXIMUM OVER SIGNED VALUES

D8's argument for the max is *"a mean dilutes and a maximum cannot understate"*. **That is false of a
signed quantity**: a max over strata of a mean signed difference returns the most positive stratum
and is blind to a stratum with an equally large negative bias, which §11.2 calls *"systematic
contamination"* in either direction. **The headline for signed trend is the maximum over strata of
the ABSOLUTE per-stratum mean**, and the per-stratum values keep their signs. Stated because
"maximum over strata" applied literally to five metrics would get exactly one of them wrong.

### (a2b) THE SELECTION MARGIN IS UNDEFINED AT A POINT WITH FEWER THAN TWO RANKABLE CANDIDATES

The margin is *ΔIC to next-best*, and `Ranking.delta_ic` is zero at the winner and **NaN for every
candidate at a point with no winner**; `best_index` is **−1** there and `n_valid` counts how many
fitted. **At `n_valid ≤ 1` there is no next-best and no margin**, and `np.nanmin` over an empty
selection returns NaN with a warning rather than a bin. **Those points are excluded and counted**,
never binned — the third (a2b) in this decision line, and the same shape as Task 6's inadmissible
N2 start. A point where the two arms disagree about *whether there is a winner at all* is a
selection disagreement and is counted as one; a point where neither arm has a winner is neither.

### THE BOTH-OK INTERSECTION IS PER CELL AND ONE OF THE METRICS IS PER POINT

D9 reports the intersection *"as a fraction of all attempted cells, per candidate"*, which is the
conditioning statement for `|Δℓ|`, parameter distance and signed trend. **Selection disagreement is
per POINT and is not conditioned on that set** — it is conditioned on both arms having a winner,
which is a different partition and has a different denominator. **Reporting one fraction and letting
it cover both metrics would attach the wrong conditioning statement to the more interpretable
number.** Two fractions, each at the granularity of the metrics it qualifies.

### (a5) ACROSS DECISIONS, IN `src` THIS TIME: A FOURTH SITE CARRIES THE RETIRED READING

Task 6 moved D5, D6 and D10 off *"the audit's members are pass 1's points"*. **`config/model.py`'s
`Detail.subsample` docstring still carries it**: *"Defaults to pass 1's coarse grid, because §11.2's
audit wants covariances at COLD-fitted points and pass-1 points are cold by construction."*

**The default may still be right for `/detail/`** — a coarse-grid selection for stored covariances
is a defensible thing on its own terms — **but the reason given for it is now false**, and a reason
is what a later reader re-derives the default from. The docstring is corrected; the field is not
touched. (a5)'s across-decisions register reaching code rather than prose.

### AND §11.2's STRATIFIED SUBSAMPLE IS NOT CONSTRUCTIBLE FOR THE POPULATION THE AUDIT NOW DRAWS FROM

§11.2: *"The audit subsample is stratified, not uniform random ... Stratify by a post-fit difficulty
proxy — Hessian condition number, ΔIC to next-best, or failure-taxonomy status."* **Every one of
those three is post-fit.** While the audit's subject was pass 1's coarse set, they were free:
pass 1's store holds a cold fit at every candidate point. **Task 6 moved the subject to FINE points,
where no cold fit exists until the audit computes one** — so selecting a stratified sample requires
the fits that selecting the sample was supposed to precede.

**This is a real consequence of Task 6's move that nobody has recorded, and it is why Task 7 does
not build a selector.** The plan's Task 7 brief specifies strata and a report and never mentions
point selection; Task 6's pre-flight sentence *"which points is D9's stratification question and the
plan's Task 7"* **conflates two things that share a word** — §11.2's stratification of the
**sample** (`Audit.stratify`) and D9's stratification of the **report**. Task 7 implements the
second. **`Audit.subsample` and `Audit.stratify` still have no consumer after this task**, and that
is filed as an open question rather than closed by an unbriefed sampler built on a circularity the
design doc never resolved.

### D4's GEOGRAPHIC STRATUM HAS NO PRODUCER AND D9 DOES NOT CARRY IT

D4 constraint 1: the regime axis is *"a column in the audit"*. **D9's two strata tables do not have
it**, and neither does the plan's Task 7 brief. **D4's own constraint 3 is the resolution rather
than the conflict**: *"Real data carries no regime label, so the geographic axis exists on simulated
fields and not on real ones."* Nothing in `src` — no config field, no store array — carries a regime
label, so there is no value to put in the column. **No regime column ships**, and the disagreement
between D4 and D9 is reported rather than silently resolved either way.

### (d) THE VOCABULARY, AND ONE IDIOM THAT FITS RATHER THAN COLLIDES

Grepped: **`stratum`, `strata` and `kappa` appear nowhere in `src/`.** The reporting vocabulary is
entirely new.

**`Report` is already an idiom here and that is the reason to use it, not to avoid it.**
`memory.py` has `FloorReport`, `AccumulationReport` and `LinearityReport`; `twopass.py` has
`TwoPassReport`. Each is a frozen dataclass of measured quantities returned by the function that
measured them. `AuditReport` is the same construction and reads as one.

**And `arm` stays in the statistical sense Task 6 declared it in**, since this module consumes
`AuditArms` directly.

### WHAT WOULD MAKE THIS TASK'S TESTS VACUOUS, NAMED IN ADVANCE

- **A fixture where every stratum is under 30 members.** Every rate is then withheld, no rate is
  ever computed, and a binner that puts every cell in one stratum passes. **The boundary is tested
  from both sides with counts CONSTRUCTED at 29 and at 30**, not sampled from a fitted run — a real
  audit fixture at this scale cannot reach 30 members in a stratum at all.
- **A fixture whose cold and warm `κ` fall in the same bin.** The (j7) test then passes under an
  implementation that bins by the warm arm. **The warm-arm perturbation is constructed to cross a
  boundary**, and that it crosses one is asserted before the binning is compared.
- **Testing (j7) by perturbing both arms.** A binner reading either arm is then unchanged, which is
  the null the test is supposed to break. **Only the warm arm moves, and the cold arm is asserted
  byte-identical.**
- **A one-candidate fixture.** The candidate axis is then degenerate, per-candidate denominators
  cannot be told apart from pooled ones, and a rescue rate computed over the wrong base looks right.
  **Two candidates with different `p` throughout**, as Task 6's suite already requires for the
  direction's width.
- **A flip fixture with no flips, or with flips in one direction only.** *"The rescue and loss rates
  use their stated denominators"* is satisfied by `0/0` handled any way at all. **The constructed
  fixture carries both a rescue and a loss, and the two denominators DIFFER**, so a single flip rate
  over a common base gives a different number and the assertion separates them.
- **Asserting "no pooled mean" by grepping the source.** That tests the spelling, not the output.
  **The assertion is over the report's own emitted fields**, so a pooled figure reintroduced under
  any name fails it.
- **A withheld stratum tested by its absence.** Silence and absence are the same bytes. **The test
  asserts the withheld stratum is PRESENT in the output with its count and with no rate**, which is
  the `RSS measurement validity` argument at a stratum.
- **A hand-built decimal-year axis.** Task 6's fixture fact, unchanged: `2000 + i * 31/365.25` moves
  `θ̂` by **6.7e-05 relative** against `to_decimal_years`, and the conversion is under
  `ALGORITHM_VERSION`. **Every fixture takes its axis from the input.**
