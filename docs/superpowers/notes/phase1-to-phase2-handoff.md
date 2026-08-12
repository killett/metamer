# Phase 1 → Phase 2 handoff

**Written 2026-08-07 at the close of Phase 1.** This is the one document a fresh session
starting Phase 2 should read. It is self-contained: nothing here requires reading
`PROGRESS.md`'s history, the Phase 1 plan, or any commit message.

`PROGRESS.md` remains the running notebook and the index of active work. **This document
is the transferable part** — the method, the standing rules, and the facts that outlive
Phase 1's code.

---

## 1. The pre-flight, (a)–(k)

**Run this against any implementation brief before writing code.** It is the most valuable
artifact Phase 1 produced, and it exists because of a measured pattern: **across Tasks 8–17,
nearly every substantive defect passed the brief's own tests.** Brief-generated tests
validate the brief's *model* of the problem, so they cannot detect that the model omitted
something. A passing suite is not evidence the brief is right.

Every entry below has at least one worked instance from this project.

### (a) Absolute vs differential — THE CANCELLATION RULE

> **Any quantity constant across the comparison axis is invisible to every test that
> compares along that axis.**

| instance | constant across | what caught it |
|---|---|---|
| REML's Harville constant `(n − rank(X))·log 2π` and `+½log\|XᵀX\|` | `θ` | review, not a test |
| `design_rank` passed to `penalty_terms` as zeros | the **candidate** axis | a surviving mutation, then an absolute AIC recomputed by hand |
| **The hash function itself** (Task 16) | both sides of every comparison | **nothing** — six fence tests passed against a serializer that was silently unstable. Separators, sort order, digest algorithm and truncation length all cancel |

The cure is always an **absolute value, hand-derived**. Task 16 needed *three* golden
hashes, not one, because each payload builder can drift independently: a `run_payload`
filing a `None` fingerprint changed every `run_hash` while every comparison stayed green.

### (a2) A NAME IS NOT A GATE

Three instances, each of which reads as a gate and is not one: `metamer_version` in
`FIT_RELEVANT_FIELDS` with nothing in `src/` populating it; `candidates` covered by no hash
while design doc §12.8 assumes enforcement; `data_uri` standing in for the data it names, so
that moving a file invalidated a valid resume *and* editing one in place permitted an
invalid one.

> **A field's presence in a hash payload is not evidence that the thing it names is
> checked.** Verify three separate facts: **something populates it**; **it derives from the
> quantity it claims to identify**; and **a change in that quantity actually moves it.**

All three failed the last clause differently. The check generalizes past hashes to every
gate made of a name — a completion bitmap, a calibration cache key, a warm-start cache key.

### (a3) DEFER THE FEATURE, DECLARE THE REGIME

> **When deferring a feature, ask separately whether its REGIME must be declared.** If any
> shipped mechanism — a memory formula, a cost projection, a validation branch — behaves
> differently under it, **the regime ships now as a declared, validated, refused branch even
> though the feature does not.** A mechanism that can only be right in one regime is not
> right; it is untested in the other.

Three deferrals of this shape in Phase 2's planning: Whittle screening, the netCDF opener,
per-point regressors. The last is the worked case — one config field moves `tile_side` from
338 to 186, a **3.3× change in tile area** — so a `--explain` that cannot report the
per-point regime is a sizing tool that is only correct in the easy case. **A sizing tool
correct only in the easy regime is worse than none, because it will be trusted.**

**A deferral in this project's idiom is a field, a formula branch, and an explicit refusal
with a test** — not a comment promising a hook.

### (b) Batch vs series

Is any per-series fact computed at batch level, or any per-candidate fact stored per point?
`moment_init`'s rung is per series; a batch-wide rung is right only when the whole batch
falls the same way.

### (c) Exit paths

Enumerate every `return` and every `raise`; does each pass through the outcome ladder?
**Enumerate, never assert a count** — an asserted count is how two bypassed exits survived
Task 8, and how a report claimed "exactly one early return" where there were four.

### (d) Grep for the vocabulary the task requires

"mask", "n_used", "realized" appearing **zero** times in a 234-line brief was detectable in
one command. Task 15's brief never mentioned `fixed`, `state_dim` or `white + white`.

### (e) Do the tests bite?

Delete the guard each one protects and confirm it fails. Two of Task 9's tests replaced
assertions that could not fail at all.

**A surviving mutation has three causes and they call for different responses.** Diagnose
which before acting; two of the three are not defects, and treating them as coverage gaps
leads to deleting a real guard.

| cause | tell | response |
|---|---|---|
| **No test protects the guard** | removing the guard changes nothing observable anywhere | act on it — write the test |
| **The mutated line is unreachable** because a guard *above* it fires first | removing that upper guard makes the mutation bite | defence in depth working; write the compound mutation |
| **TWO INDEPENDENT GUARDS, EITHER SUFFICIENT** | mutating **either alone** does not bite; mutating **both at once** does | the code is doubly protected and the test is fine |

**The third is now a named outcome with two instances.** Task 16's `_subset` — an explicit
`if missing: raise` above a comprehension — and Phase 2a Task 0's wholly-masked batch, where
`optimize.optimize_series`'s merged-precheck return and `objective.evaluate`'s batch-level
short-circuit each independently keep the engine unreached. **Reproducing the defect honestly
requires mutating both halves at once.**

> **The corollary, and it is the part that costs something later. Doubled guards are usually
> good, but they must be DELIBERATE.** If neither author knew the other's guard existed, a
> later simplification removes one on the grounds that it is dead — and it is dead only
> because the other is there. **Comment both, each naming the other**, so the redundancy is
> visible as a decision rather than as an accident waiting to be tidied away.

### (f) Does the brief contradict a docstring already in the tree?

`objective.py` named `design_rank` in two places and the brief still passed `rank_x`.
`terms.py` documented the `Infinity`-token trap that Task 16's fence then reintroduced.

### (g) Does every call match the module's CURRENT signature?

Check the source, not the brief's assumption. The symptom is a plausible number rather than
an error — `n_eff=float(n)` makes `BIC_NEFF` silently identical to `BIC`.

> **A CLEAN (g) MARK IS NOT A PRE-FLIGHT.** (g) clears a brief of **staleness and nothing
> else**. Task 15 bound cleanly and was wrong five ways; Task 16 bound cleanly and shipped a
> serializer that hashed memory addresses. Both were (a)–(f)/(h)–(k) failures, and (g) cannot
> see any of them.

### (h) Does the test exercise the thing it names, or a default?

Thread every parameter the behaviour depends on through as a real caller would. Task 11's
three-N step-rule test passed against a deliberately broken step rule because it left
`scale` at its default, making the numerator 1 and the denominator irrelevant.

### (i) Can the fixture fail at all?

Ask what property of the fixture makes the defect visible; if the answer is "none", the
fixture is wrong before the assertion is. A **quadratic cannot test a step rule** (third
derivative zero). A fixture at `n_eff = 12` **cannot test a floor at 2.0**.

### (i2) A PURE NEGATIVE NEEDS A POSITIVE CONTROL

> **Any assertion of the form "X did not happen" is unfalsifiable unless a paired test
> proves X CAN happen through the same wiring.** The control is not scaffolding around the
> real test — **it is the half of the test that can fail.**

(i) asks whether the fixture can express the defect. This asks something stronger and it
applies whenever the *observable is an absence*: no fit ran, no write occurred, no refit
happened, no network call was made, nothing was recompiled. An absence is produced equally
well by the thing being correctly suppressed and by the thing never being connected, and
**the two are byte-identical in the test output.**

The worked case is Phase 2a Task 0's raising stub engine. A stub wired into a run and never
reached is indistinguishable from a stub never wired in at all; every "no fit ran" assertion
downstream passes for free the moment the injection seam moves. **The pairing that fixes it
is a test that the stub DOES raise when a fittable batch goes through the same call.**

**The control earns its place by finding wrong beliefs about the code's shape, not just
wiring faults.** On its first run that one failed — the engine is handed `B = 1`, not the
tile's `B`, because `fit` drives `optimize_series` once per series. That is exactly the
class the pre-flight exists for, and **a negative-only test can never surface it**: it has no
successful path to be wrong about.

Three further shapes this covers, so it is not read as being about stubs:

| the negative | the control it needs |
|---|---|
| a completion bit is not set after an injected interruption | the same injection point, not triggered, does set it |
| a value edit does not move `geometry_hash` | a geometry edit through the same fingerprint call does move it |
| a resume refits nothing | the same resume with one outstanding tile refits exactly that tile |

### (j) Does the oracle share a derivation path with the thing it checks?

An independent oracle means a **different construction**, not different constants.

| subject | the bad "oracle" | why it is not one |
|---|---|---|
| `hessian_at_optimum` | `tests/oracles.fd_hessian` | the same second-difference stencil at a different step — it measured the step choice and nothing else |
| `theta_err` (delta method) | `theta_err / theta` | the same quantity rescaled by the very Jacobian under test |

The tell: if the reference is not at least ~100× more accurate than the subject, it is
probably the same algorithm. Nested Richardson qualifies; a wider step does not.

### (k) Does anything that must be stable across runs depend on process-local state?

Set iteration order, `id()`, the `repr` of an unordered container, time, environment.
**Test across processes, not within one.**

**This is the only category a perfect in-process suite cannot reach.** Every test in one
pytest run shares a single `PYTHONHASHSEED`, so a quantity stable within a process and
unstable between them is invisible to every same-process test **and to mutation testing**,
which runs in that same process against the same frozen seed.

Worked instance: `json.dumps(..., default=repr)` renders `{"aic","bic","hqic"}` as three
*different* strings under seeds 1, 2 and 3, and an object without `__repr__` renders its
memory address. Every fence test passed; every resume of a finished store would have refit
it, with no symptom but a bill.

**(k) extends to repeated measurement, and that is a distinct shape.**

> **A repeated measurement must vary everything the measured quantity depends on.**
> Repeats inside a fixed allocation, a fixed input, or a fixed process measure
> **precision, not accuracy** — the component held fixed outside the repeat loop is
> invisible to them by construction, and a best-of-N over one allocation, published as
> though it were fresh, reports a confidence the method cannot support.

Measured (P4): the spike's A:B spread at its worst cell is **0.13** across eight repeats
inside one allocation and **0.82** across eight fresh processes; path A also runs ~16%
slower on freshly allocated inputs (path B ~4%). The published ±0.15 scatter came from the
inner loop. The check: **list what the number depends on, then list what the repeat loop
re-creates** — anything in the first list and not the second is a systematic the
measurement cannot report. If the production condition allocates, and a tile is
materialized, fitted and dropped, the repeat must allocate inside it.

**(k) extends to every delta, rate or trend.** Any assertion on a *difference* must be
checked for whether its **baseline is set by history outside the test**:

| assertion | why the baseline is not the test's | the fix |
|---|---|---|
| "allocating 256 MiB moves peak RSS by 256 MiB" | peak RSS is a **high-water mark**; measured, a watermark at 385 MB moved **67 MB** | pin against an absolute reading in the same test (`current_rss_bytes`) |
| "total STREAM throughput rises with thread count" | on a saturated controller the **sign** is the session's CPU load: 10.59 → 12.03 GB/s unloaded, **11.23 → 8.44** under contention | assert a **ratio** that survives either loading |

And the harder lesson: **both modules already documented, in capitals, the property that
broke the test.** The violating tests were written anyway, by the same author, in the same
sitting. **Documentation does not constrain the next author — tests do.**

**(h), (i) and (k) are not subsumed by mutation testing.** (e) asks whether a test bites
when the guard is deleted; (h) and (i) ask whether the call site and fixture can *express*
the defect at all; (k) asks whether the defect is observable in one process.

**Also: run the brief's code.** The two highest-yield audits did. Task 17's fence asserted
`tile_side(1e9, 28650) == 187` against an implementation that floors — `floor(186.83)` is
186, and the test would have failed against the code printed beneath it.

---

## 2. Standing rules

### eps-derived constants — one construction, three instances

A numerical threshold here is **derived, not chosen**: from float64's precision and **how
many times the quantity is squared or differenced on its way to the objective.**

| constant | path to the objective | rule | value |
|---|---|---|---|
| `lint.WHITE_COLLAPSE_LOG_LIMIT` | ℓ is quadratic in θ near the optimum, so a model difference is resolvable only above `√eps` — one squaring | `−½·log eps` | 18.0218 |
| `objective.CONDITION_LOG_LIMIT` | the solve runs on the normal equations, so the Cholesky sees `cond(X_w)²` | `−¼·log eps` | 9.0109 |
| `gradients.fd_step` / `hessian_step` | an `m`-th difference divides by `h^m` | `eps^(1/(m+2))` | 6.055e-06 / 1.221e-04 |
| `optimize.HESSIAN_COND_LIMIT` | H is inverted **once**, for `H^-1` and `theta_err` | `eps^(-1/2)` | 6.7109e7 = 2²⁶ |
| `signal.X_RANK_RTOL` | every consumer forms the Gram, so the ratio is squared | `eps^(1/2)` | 1.4901e-08 = 2⁻²⁶ |
| `objective._NEGATIVE_REDUCTION_RTOL` | `eps` × the largest `cond(Gram)` reachable before `ILL_CONDITIONED_X` | `eps · eps^(-1/2)` | 1.4901e-08 = 2⁻²⁶ |

**The last three landed 2026-08-10 (P1) and all three replaced picked values.** They come
out at `2^±26` by three different routes, which is a hazard in itself: state each
derivation separately and never reach for the neighbour's exponent because the answer
looks familiar.

State each in the **units of the quantity it thresholds** so they are comparable. **When a
fourth is needed, count the squarings and differences and read the exponent off — do not
pick a round number and do not copy a neighbouring constant.** Copying the neighbour is the
measured default mistake: 147× at the Hessian step, 280×–1100× at the gradient.

**A constant that genuinely cannot be derived is POLICY and must be labelled as such, with
its consequence stated.** `lint.OVERLAP_RATIO = 1.5` says in its own docstring that two
Matérn ν=1/2 ACFs a factor `r` apart differ at most by `r^(−1/(r−1)) − r^(−r/(r−1))`, which
at `r = 3/2` is exactly **4/27**.

**~~Still picked, flagged:~~ CLOSED 2026-08-10 (P1).** `optimize.HESSIAN_COND_LIMIT` and
`signal.X_RANK_RTOL` are both derived now; see the table above and open question 9 in
`PROGRESS.md` for which fixtures moved.

**Two corrections to what this section originally said, both worth carrying:**

- **`RANK_DEFICIENT_LOG_LIMIT` is NOT derived from `signal.X_RANK_RTOL`.**
  `objective.py` imports `_RANK_RTOL` from `engines.kalman` — the **Gram** cutoff — and
  derives from that. The two constants live in different modules, threshold different
  matrices, and both happened to hold the numeral `1e-10`, which is the entire mechanism of
  the misreading. Re-deriving `X_RANK_RTOL` alone would have left
  `RANK_DEFICIENT_LOG_LIMIT` resting on the other one regardless.
- **`kalman._RANK_RTOL` is deliberately left at `1e-10`, and that is not a picked value.**
  Its docstring carries a measured calibration table and a window bounded from both sides:
  an exactly deficient design puts its null singular value at 0 or ~5e-17 of the leading
  one, decades below any candidate threshold, while a Gram accumulated at `cond(X_w) = 1e8`
  has already lost its small singular value into float64 noise, so a threshold below
  ~1e-16 would be reading rounding error. That is the "measure, or document explicitly"
  branch of the rule, satisfied, not the "picked" branch.

**`optimize.GRAD_TOL` is the one constant here that is NOT eps-derived, deliberately.** Its
floor is set by scipy's L-BFGS-B stopping rule, several decades above what the
finite-difference gradient could resolve (measured instrument floor ~3e-10 relative to
`|loglik|`), so float64 has nothing to say about it. It is a **measured separator** between
two populations — converged fits at `3.46e-07 .. 2.30e-05` and fits stopped at one to three
iterations at `1.45e-04 .. 1.84e-02` — and both bounds are pinned by a test. Its previous
`1e-5` sat *below* the converged population's maximum.

### The development environment cannot test the shipped artifact

> **`pixi run` executes off `PYTHONPATH=src` inside an environment that already has
> everything, so a dependency the package fails to DECLARE is invisible to every test run
> that way.** The property that must hold is a property of a *different process* — one that
> has only what the distribution asked for — and no amount of testing in this one reaches
> it. **This is the same argument as (k)**, one layer out from `PYTHONHASHSEED`.

**It fails only for users, never for you**, and it recurs at *every* task that adds a
dependency, which is what makes it a standing requirement rather than a finding. Phase 2a
Task 0 is the worked instance: `xarray` and `pydantic` sat in `pixi.toml` while
`pyproject.toml`'s `dependencies` named neither, and `tests/test_core_isolation.py` had been
documenting a `[batch]` extra that did not exist since Phase 1.

The guard is `tests/test_packaging.py`, in the full sweep: **build the wheel, install it into
a clean virtual environment, and check the artifact from inside that environment** — that
every module the package claims to ship is importable there, and that every third-party
import under `src/` is named in the *wheel's own* metadata rather than in `pyproject.toml`.
Its limits are stated in its own docstrings; read them before trusting it further than they go.

### The other standing rules

- **Oracles must not share a derivation path** — see (j).
- **A recorded measurement carries its measurement date**, because a quoted figure drifts
  and a stale one reads exactly like a fresh one. Two instances: `pixi.lock` was quoted at
  645 KB, then 630 KB, and measured 635.6 KB when Phase 2a Task 0 re-checked it; and the
  `tile_side` of 171 survived in notes after the engines were fixed. **Re-check the number,
  never the note** — and date the number so the next reader knows whether re-checking is due.
- **Heterogeneous batches by default.** A homogeneous batch cannot expose a
  batch-granularity defect. Task 13's only real finding came from the one mutation that
  survived because every fixture had `B = 1`. Task 17's utilization measurement uses a
  heterogeneous sample because a homogeneous one reports 1.0 by construction — the number
  the measurement exists to challenge.
- **Enumerate exits, never count them** — see (c).
- **A CLAMP, FLOOR OR EPSILON GUARD ABOVE THE DIAGNOSTIC LIMIT OF WHAT IT GUARDS IS A
  FABRICATION MACHINE.** It converts a reportable fact into a plausible number *and* makes
  the rung that would have reported it unreachable, so no test can see the loss.
  `sqrt(maximum(var, 1e-12))` gives `sigma = 1e-6` against sigma's own `1e-8` limit, so the
  diagnostic clip never fires and `InitRung.CLIPPED` becomes dead code. A tree-wide sweep
  (2026-08-06) found no further instances.
- **Prefer analytic endpoints to tolerance bands.** And know which identities survive
  float64: `white(3) + white(4) == white(5)` is bit-exact (integers at lag 0, zeros
  elsewhere); the Matérn version at a shared ρ is `9e + 16e` against `25e` and misses by an
  ulp. Exact in ℝ ≠ exact in float64, and **the exact case is what makes the
  over-generalization look safe.**
- **`(B, N)` is the only code path.** `B = 1` is a shape, never a separate implementation.
- **Failed series carry NaN, never −inf**, in anything destined for the store. `−inf` is a
  finite-looking sentinel that survives some consumers' checks; it is the optimizer's
  internal barrier value only.

---

## 3. The number every Phase 2 tile calculation inherits

**`tile_side` is 338. It was 171 for the whole of Phase 1, and the engines were fixed on
2026-08-10 (P2).**

| figure | what it is | use it for |
|---|---|---|
| **339** (8 682 B/series) | design doc §9.4's **model** — the streaming filter the document describes. `memory.bytes_per_series` | reading §9.4 |
| **338** (8 722 B/series) | what the code **actually holds** on path A. `memory.resident_bytes_per_series` | **every Phase 2 tile calculation** |
| ~~171~~ (33 882 B/series) | what it held while `_augment` materialized `[y \| X]` | **nothing. Any Phase 1 note quoting 171 predates the fix** |

At a 1 GB budget, shared X, d=3, k_β=4, p=4, M=12. Path B's resident figure is 8 B/series
above its own model rather than 40, because its extra term is a `(B,)` index array and not
a row of columns.

**What the defect was, kept because the mechanism is the transferable part.**
`KalmanEngine._augment` ended in `np.concatenate([y[:, :, None], x], axis=2)`, materializing
a `(B, N, 1+k_β)` float64 array — **25 200 B/series at N=630**, nearly three times §9.4's
entire per-series total, and it **did not vanish when the design was shared**, the case
§9.4 treats as free. The `np.broadcast_to` on the line above **is a view and allocates
nothing**, which is exactly why the copy read as free on a code read. The accumulator only
ever needed one row, so both engines now index the observation out of `y` and the design
columns out of a `(1, N, k)` or `(B, N, k)` block, per timestep. **§9.4 was right and the
engines were wrong**; the fix made the document true rather than replacing it.

**The measurement, because the fix is only worth what it measures.** The slope of resident
RSS against B, in a fresh process, sampled on a thread during the workload, went
**43 392 → 8 471 B/series** — a fall of 34 921, *more than the block itself*, because the
per-step temporaries at peak scaled with it. Against the arithmetic floor of 6 382 B/series
that is a ratio of **1.33**, inside the ~1.5× below.

**And the standing check that produced that number:** *does the memory formula describe the
code, or a model of the code?* §9.4 was wrong twice in ways three places agreed on.
**Verify against measured resident bytes** — the slope of RSS against B, in a fresh process,
sampled during the workload — and treat any factor above ~1.5× as a missing term rather than
measurement noise. It was 5.0× before the fix and nothing in the suite said so until the
measurement existed.

---

## 4. Open questions 5–8

| # | question | what would close it |
|---|---|---|
| **5** | **64-core box RAM is unknown.** The stage-1 gate was closed without that machine, but its RAM is needed before any tile-sizing run there | run `free -g` on it and record the figure |
| **6** | **Roofline validation across machines.** One data point cannot validate a two-parameter fit; the mini PC supplies the model's first point and tests nothing. **Blocks the `cloudify` cost projection (§15.5)** — projecting spend on an unvalidated roofline is projecting a guess | a second machine's roofline pair plus its measured canonical filter pass, checked against the prediction |
| **7** | **Path B at high thread occupancy.** Measured at 1 and 4 threads on a 4-core box. `prange` over series at 64 threads may hit false sharing on the per-series `accum` block, or saturate the controller elsewhere | `bench/spike.py --threads 1 --threads 4 --threads 64` on the 64-core box |
| **8** | **`numba` and `celerite2` on arm64.** `celerite2` has no `osx-arm64` conda-forge build and is pinned to `[target.linux-64.dependencies]`; `numba` on arm64 has never been run here | the suite plus `bench/spike.py` on the MacBook |

Questions 1–4 and 9 are in `PROGRESS.md`. **9 (`HESSIAN_COND_LIMIT`) was closed on
2026-08-10**, before Phase 2 planning as it required: the limit is now the derived
`eps^(-1/2) = 6.711e7`, and §4.8's two halves are on the same footing.

---

## 5. Fixture facts a fresh session will otherwise get wrong

Every one of these was discovered by building a fixture that could not fail.

- **`DIAGNOSTIC_LIMIT` in a DESIGNED fit is reached through `sigma`'s lower limit (1e-8),
  not `rho`'s upper one (1e6).** A slow cosine does not do it — a design carrying constant,
  trend, offset and rate change absorbs it and leaves an ordinary residual; measured, that
  series comes back `OK`. What works is a record whose amplitude is ~1e-11.
- **`BIC_NEFF`'s looser penalty does not show up in `ic_best`.** The winner is normally the
  white candidate, whose `n_eff` equals `n` exactly. The difference lives on the
  *correlated* candidate's ΔIC — measured 7.823 → 7.677 at `n_eff = 194.25` against `n = 200`.
- **Under white noise GLS is OLS, so `n_eff_trend` is `n` for every design column.** Any
  test meaning to pin *which* column is the trend must use a **correlated** candidate.
- **`ILL_CONDITIONED_X` is theta-dependent** — it is the *whitened* Gram that is ill
  conditioned, not `X_r`. Across five seeds at one mask, `design.condition_number` is
  2.68e4 every time while the outcome is `ill_conditioned_x` for two and `ok` for three.
  Pin the seed; never assert `design.condition_number` as a proxy.
- **`cond(X_w)` is invariant under a uniform rescale of Σ**, so you cannot make a design
  ill-conditioned by shrinking σ. Analytic, not empirical. What does move it is giving the
  design more post-breakpoint degrees of freedom than the post-breakpoint samples carry.
- **The time axis is decimal years.** In seconds since 1970 the same 20-year monthly design
  goes from `cond(X) = 3.4e1` to `3.3e32` and rank 7/7 to 2/7.
- **A quadratic cannot test a step rule**, and **a fixture above a floor cannot test the
  floor.**
- **HETEROGENEITY MUST COME FROM A PARAMETER THE LIKELIHOOD IS NOT EQUIVARIANT IN** —
  timescale, mixing ratio, mask pattern, series length. **Varying an equivariant parameter
  produces a fixture that looks diverse and is identical.** Amplitude is the worked case:
  a Gaussian log-likelihood is equivariant in it, so `* logspace(-1, 1, k)` contributes
  nothing. Measured on the spike's iteration sample, one realization at four amplitudes:
  `n_iter = [28, 28, 28, 28]`, utilization **exactly 1.0** — the number that fixture's own
  docstring said the spread existed to challenge. Ask which of a fixture's varying
  quantities the objective is *invariant* under, before writing it.
- **`fit` costs ~5.4 s per series** through the per-series scipy loop, linear in B. Anything
  wanting tile-scale behaviour must use a batched *evaluation*, not a fit.
- **`ru_maxrss` is inherited across `fork()`/`exec()` and updated lazily.** A child spawned
  from a 400 MiB parent reports the parent's peak byte-for-byte; and the watermark can
  *trail* live RSS (470.8 MB against a live 471.3 MB read an instant earlier).
- **`numba` pins `numpy<2.5`**, so installing it downgraded numpy 2.5.1 → 2.4.6, and 2.4's
  type stubs infer `floating[Any]` where 2.5's infer `float64`. `mypy` then reports errors
  in files nobody touched. An environment fact, not a regression.

---

## 6. What Phase 2 inherits structurally

- **The three-hash separation, awaiting a store.** `fit_hash ⊂ compat_hash ⊂ run_hash` is
  built, tested, and pinned by golden constants. **The contract Phase 2 must honour:**
  §12.8 treats a `compat_hash` match with a `fit_hash` match as licence to **recompute the
  derived arrays from stored primitives without refitting**. That is implementable because
  `rank_candidates` takes *only* the stored primitives — never a spec, a design matrix or
  the data — and `test_hashing.py` pins exactly that. **If any future change makes
  `rank_candidates` need the data, §12.8 becomes unimplementable and the three-hash split
  buys nothing.** Not yet tested: an actual resume, and "a `fit_hash` mismatch is refused",
  both of which need the store.
- **The batched-equals-solo invariant.** `test_batched_results_equal_solo_results_series_by_series`
  is the standing guard for the entire "(B, N) is the only code path" class. Every new
  batched routine must keep it green. `np.linalg.cholesky` raises for the *whole stack* if
  one member fails, so validity is classified with the non-raising batched `slogdet` first
  and only the valid subset is factorized.
- **The label-switching / hysteresis confound (§11.2).** Two same-kind terms with a free
  timescale are exchangeable across the whole searched space; canonical ordering at result
  packing fixes the reporting **within one fit and nothing between fits**. Across grid points
  that produces large parameter disagreement with near-zero selection, objective and
  signed-trend disagreement — **a signature the warm-start hysteresis audit would read as
  benign hysteresis when it is non-identifiability.** Two consequences are recorded in
  §11.2: report per-term parameter disagreement separately from the aggregate, and decide
  whether the audit refuses lint-flagged candidate sets outright or reports the two strata
  apart. **Do not measure hysteresis on a lint-flagged candidate set and quote the number as
  hysteresis.**
- **The identifiability lint is the cheap pre-check for that confound.** `core.lint` runs on
  a `ProcessSpec` before any data and flags exactly those compositions.
- **Path A is the permanent correctness reference.** `engines/kalman.py` plus
  `optimize.optimize_series`. It is not deprecated and must not be deleted; every MVN
  oracle and the path-B agreement test are pinned against it. ~~The stage-1 verdict carries
  one condition: re-measure after `_augment` is fixed~~ — **discharged 2026-08-10.** The
  falsifier is not met in any cell or any harness, so Task 19 stays deleted.
  ~~**But the two harnesses disagree about whether the ratio moved**~~ — **CLOSED by P4,
  2026-08-10: there was no harness effect.** The 0.57 spread (spike 3.84, sweep 3.27) is
  inside a single harness's own between-process scatter, measured at **±0.4** at that cell
  over twenty-nine runs, against the **±0.15** the verdict had assumed from a sample of two.
  **The scatter lives between allocations, which is the one place `repeats` cannot look**:
  `_time_pass` takes the best of N passes over *one* allocation (spread 0.13) and publishes
  it as if it were a fresh one (spread 0.82). Path A is ~16% slower on freshly allocated
  inputs, path B ~4%. The two harnesses are now one — `--dim` and `--gaps` are filters, so
  the batch sweep is a flag combination — and every cell reports a median with its min and
  max. **Any restated margin must name its harness invocation, B, thread count and
  cell-repeat count.** What was already resolved and still is: **path B's per-pass cost fell
  ~20%**, because it had been reading a per-series private copy of the shared design, and
  **path A did not measurably move**, which contradicts the condition's stated reasoning.
  See [`spike-stage1-verdict.md`](spike-stage1-verdict.md).
- **A CORRECT CONCLUSION REACHED THROUGH A WRONG MECHANISM IS A FINDING IN ITS OWN RIGHT.**
  The verdict predicted the `_augment` fix would help path A most; path B is what gained.
  The conclusion survived, the reasoning did not, and **the reasoning is what the next
  prediction is built on** — a note that records only outcomes gives a later reader no way
  to know its mechanism failed.
- **The path-B agreement test cannot carry a change made to both engines.** It compares two
  implementations of the same recursion, so anything both do identically is invisible to
  it — the cancellation rule at the level of an engine. What pins the values is
  `test_kalman.py`'s MVN oracle, which builds the covariance explicitly. For the streaming
  change the available check was stronger than either: **bit-identical** output against the
  pre-fix modules loaded out of git, across both engines and all three design regimes.
- **The benchmark harness is a one-command run and must stay that way**, so a later session
  can produce `box64.json` or `macbook.json` without reconstructing anything.
