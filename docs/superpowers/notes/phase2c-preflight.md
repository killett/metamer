# Phase 2c pre-flight, per task

The (a)–(k) audit of each 2c task brief and what each finding changed. The method itself lives
in exactly one place — [`phase1-to-phase2-handoff.md`](phase1-to-phase2-handoff.md) §1 — and is
**not restated here**. Append to this file **before** each task, not after.

---

## 2c Task 0 — the warm-start spike, audited before any code

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

## 2c Task 1 — the stride curve, audited before any code

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
