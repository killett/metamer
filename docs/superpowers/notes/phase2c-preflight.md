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
So **every store written since 2026-08-11 records a fit payload asserting `warm_start_enabled:
true` over fits that are entirely cold.** After Task 5 the identical config produces warm-started
fits **under the same `fit_hash`** — converged-looking fits at a different optimum, resumed into
the same store, which is §11.1's worst failure mode arriving through the config rather than
through a stale cache.

**THE OBVIOUS REPAIR IS THE WRONG ONE, WHICH IS WHY IT IS WRITTEN DOWN.** `Screening` is *"present,
and refused at layer 3 until Phase 4"*, and mirroring that for `WarmStart` is the first thing a
reader reaches for. **It would refuse every run**, because unlike `screening.enabled` (default
`False`) this one defaults to `True`. **The closer is the `ALGORITHM_VERSION` bump at Task 5**: a
pre-bump store then mismatches on `fit_hash` and refits, which is exactly what the constant is
for. **Nothing else separates the two populations, and no store can be repaired after the fact.**

### THE REQUEST/IDENTITY CLASSIFICATION WAS NEVER MADE FOR THESE FIVE, BECAUSE THE VOCABULARY ARRIVED A DAY LATE

The five entered on **2026-08-11**. `data_uri` was named *"the last self-reported identity in
either allowlist"* on **2026-08-12**. **So the five are the only members of `FIT_RELEVANT_FIELDS`
that were never classified**, and the classification is what the audit of the existing fields
closed with.

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
