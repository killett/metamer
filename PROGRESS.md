# metamer — progress

## Start here (cold-start summary)

- **Branch:** `phase-1`. **Last commit:** see `git log --oneline -1`; the handoff below was
  written at the commit that completed Task 14.
- **Done:** Phase 1 **Tasks 0–18**. Task 18 (the stage-1 gate) was closed on the mini PC
  alone — see the verdict note for why one machine suffices and in which direction the
  inference runs. **Task 19 deleted.**
- **Exit criteria:** **12 met, 3 met with reduced scope, 1 deferred** — the full table
  with reasons is at the end of the Phase 1 plan. The deferred one (`celerite2`
  agreement) is the item §16.1 nominated in advance as the first cut.
- **Next:** **Phase 1 is COMPLETE.** Tasks 0–18 done; **Task 19 deleted, not deferred**
  (path B won by >=3x, so the batched trust-region has no purpose). The stage-1 verdict,
  its scope, and what it does **not** establish are in
  [`docs/superpowers/notes/spike-stage1-verdict.md`](docs/superpowers/notes/spike-stage1-verdict.md)
  — read it before quoting the >=3x result.
- **The benchmark harness is a one-command run and must stay that way.** To produce a
  second machine's numbers without reconstructing anything:

  ```
  # any machine: change --threads and --out only
  pixi run python -m metamer.bench.spike \
      --threads 1 --threads 4 --batch 1000 --repeats 3 --out bench/minipc.json
  ```

  64-core box: add `--threads 64`, `--out bench/box64.json`.
  MacBook: `--threads 1 --threads 8`, `--out bench/macbook.json`.
  Batch sweep at path B's worst cell (d=3, 1 thread, no gaps) is
  `bench/batch-sweep-d3-1thread-nogaps.json`.
- **Tests:** **583 collected.** Full sweep `pixi run test` (~280 s). `pixi run test-fast` (~12 s)
  deselects the `slow` marker and is for iteration only — **a green fast run is not evidence
  a task is done.**
- **Verify a fresh checkout with:** `pixi run test && pixi run typecheck && pixi run lint`
- **Remote:** https://github.com/killett/metamer — public, `origin/phase-1` in sync.
- **Task 18 is closed.** It was a user gate; the user closed it on 2026-08-07 by
  directing that the 64-core box and MacBook be skipped, with the reasoning
  recorded in the verdict note.

---

- **Where the work is:** the likelihood spine runs end to end from a `ProcessSpec` to a
  scored, ranked, per-series result. `fit()` is the `(B, N)` driver; the comparability
  guards are on the real path; the objective is differentiable with a validated step rule
  and an adopted gradient oracle; Matérn ν=1/2 ships verified analytic derivatives behind a
  protocol that refuses an unbacked claim.
- **Pending:** nothing in Phase 1. Task 19 was **deleted** under the ≥3× rule.
- **A pre-flight audit of each task brief is a required step** before writing any code —
  see [Required pre-flight](#required-pre-flight-for-every-remaining-task) below. Every
  brief audited so far carried at least one defect that verbatim transcription would have
  committed.
- **Task 14's fence was corrected in place and (g)-verified by signature binding, and it
  still did not run.** Binding is not execution. Expect the same of every remaining fence.
- The draft PR command is below and has not been run yet.
- **Execution workspace:** `.superpowers/sdd/2026-08-05-metamer-phase1/` (git-ignored) holds
  the subagent-driven-development ledger `progress.md`, per-task briefs, and reports. The
  ledger is the recovery map for a session that dies mid-task; it is deleted when the branch
  is finished, so anything worth keeping must be migrated here first.
- **Resume with:** `/superpowers-extended-cc:executing-plans docs/superpowers/plans/2026-08-05-metamer-phase1.md`
- Read this whole file before starting. The sections below hold decisions that exist
  nowhere else.

---

## Current work

| what | where |
|---|---|
| Design document | [`docs/superpowers/specs/2026-08-04-metamer-design.md`](docs/superpowers/specs/2026-08-04-metamer-design.md) |
| Phase 1 implementation plan | [`docs/superpowers/plans/2026-08-05-metamer-phase1.md`](docs/superpowers/plans/2026-08-05-metamer-phase1.md) |
| Phase 1 task tracker | `docs/superpowers/plans/2026-08-05-metamer-phase1.md.tasks.json` (native task ids 8–27) |
| Original build prompt | [`metamer-build-prompt.md`](metamer-build-prompt.md) — **superseded** by design doc §2 where they conflict |

Phase list is design doc §17. Phase 1 exit criteria are §18. Do not duplicate either here.

---

## Required pre-flight for every remaining task

Run this against the task brief **before dispatching an implementer**, and fold what it
finds into the dispatch as explicit corrections.

**Why it exists.** Across Tasks 8 and 9 every substantive defect passed the brief's own
tests: the REML constant (a differential test is blind to a constant offset), the outcome
laundering, the unmerged exit paths, and the total absence of mask handling in a module
whose seven tests all passed. **Brief-generated tests validate the brief's model of the
problem, so they cannot detect that the model omitted something.** That is the whole
argument — a passing suite is not evidence the brief is right.

- **(a) Absolute vs differential — THE CANCELLATION RULE.** Stated generally, because
  three separate instances have now landed:

  > **Any quantity that is constant across the comparison axis is invisible to every test
  > that compares along that axis.** Selection tests cannot validate `k`, `n`, or any
  > additive constant in the log-likelihood. Each requires an absolute value computed by
  > hand.

  The three instances, all of which passed every differential and selection test that
  existed at the time:

  | instance | constant across | what caught it |
  |---|---|---|
  | REML's Harville constant `(n − rank(X))·log 2π` and `+½log\|XᵀX\|` | `θ` | review, not a test |
  | `log\|XᵀX\|` under gaps | `θ` | the restricted-design contract |
  | `design_rank` passed to `penalty_terms` as zeros | the **candidate axis** | a surviving mutation, then an absolute AIC recomputed by hand |

  The third is the sharpest: `k` shifted by the same amount for every candidate at a point,
  so it cancelled in every ΔIC and left the ranking, the weights and `n_valid` all
  unchanged. **A whole category of test — every ΔIC, weight and selection assertion — is
  structurally blind to it.** The only cure is an absolute check: recompute the criterion
  value from `k = k_θ + rank(X_r)` and compare against `ic_best + delta_ic`.
- **(b) Batch vs series.** Is any per-series fact computed at batch level, or any
  per-candidate fact stored per point?
- **(c) Exit paths.** Enumerate every `return` and every `raise`; does each pass through the
  outcome ladder? **Enumerate, never assert a count** — an asserted count is how two
  bypassed exits survived Task 8, and how a report claimed "exactly one early return" where
  there were four.
- **(d) Grep for the vocabulary the task requires.** "mask", "n_used", "realized" appearing
  **zero** times in a 234-line brief was detectable in one command.
- **(e) Do the tests bite?** Delete the guard each one protects and confirm it fails. Two of
  Task 9's tests replaced assertions that could not fail at all.
- **(f) Does the brief contradict a docstring already in the tree?** `objective.py` named
  `design_rank` in two places and the brief still passed `rank_x`.
- **(g) Does every call the brief makes into an existing module match that module's
  CURRENT signature and shapes?** Check the source, not the brief's assumption. (a)–(f)
  catch a brief whose *model of the problem* is wrong; this one catches a brief that was
  correct when written and has since gone stale, because the dependency it calls did not
  exist yet and is therefore encoded as imagined. The symptom is a plausible number rather
  than an error — `n_eff=float(n)` makes `BIC_NEFF` silently identical to `BIC`. The
  forward audit below is (g) run once across every remaining task.

  > **A CLEAN (g) MARK IS NOT A PRE-FLIGHT.** (g) asks one question — does every call bind
  > against the current signature — and answers it for staleness only. It is necessary and
  > nowhere near sufficient. **Task 15 bound cleanly and was wrong five ways**: a calibrated
  > constant where a derivation existed, rules keyed on a parameter the target composition
  > does not have, a starting value read as a structural property, a ratio test that missed
  > the structural case entirely, and a silent skip where a finding was needed. Every one is
  > an (a)–(f)/(h)/(i)/(j) question, and (g) cannot see any of them.
  >
  > **Tasks 16–19 are marked "no calls into changed modules". That clears them of
  > STALENESS AND OF NOTHING ELSE.** Do not treat the audit mark as partial credit. Run the
  > full pre-flight against each brief before writing code, exactly as if the row were
  > blank.

- **(h) Does the test exercise the thing it names, or a default?** Thread every parameter
  the behaviour depends on through as a real caller would. A test that leaves a scale at 1
  cannot detect a missing numerator. **Measured on this project:** Task 11's three-N step-rule
  test passed against a deliberately broken step rule, because it called
  `fd_gradient(fn, U0)` without `scale`; with `scale = 1.0` the numerator is 1, the
  denominator is irrelevant, and deleting it changes no number.
- **(i) Can the fixture fail at all?** Ask what property of the fixture makes the defect
  visible; if the answer is "none", the fixture is wrong before the assertion is. Two
  instances so far: Task 11's brief tested a step rule on a **quadratic**, whose third
  derivative is zero, so central differences are exact at *any* step and no rule is
  distinguishable from any other; and Task 10's brief tested a `max(n_eff, 2.0)` floor with
  `n_eff = 12`, which sits above the floor and never reaches it.

- **(j) Does the oracle share a derivation path with the thing it checks?** An independent
  oracle means a **different construction**, not different constants. `tests/oracles.fd_hessian`
  and `hessian_at_optimum` are the same second-difference stencil at different steps, so
  checking one against the other measured the step choice and nothing else — the routine
  could have been wrong in any way that a wider step also is, and the test would have passed.
  This is distinct from (i): there the fixture cannot express the defect; here the fixture is
  fine and the *reference* is a reparameterized copy of the subject. Nested Richardson
  qualifies as independent; a wider step does not. The tell is that the oracle's accuracy is
  the same order as the subject's — if the reference is not at least ~100× better, it is
  probably the same algorithm.

  **Two worked examples, both from this project:**

  | subject | the bad "oracle" | why it is not one |
  |---|---|---|
  | `hessian_at_optimum` | `tests/oracles.fd_hessian` | the same second-difference stencil at a different step — it measured the step choice and nothing else |
  | `theta_err` (delta method) | `theta_err / theta` | the same quantity rescaled by the very Jacobian under test; it cannot disagree |

  The second is the more seductive because it *looks* like a derivation. Both were replaced
  by references built a different way: nested Richardson for the Hessian, and for the
  uncertainties a Hessian rebuilt from the objective and the published
  `theta_unconstrained`, which shares no code with the driver's own path.

- **(k) Does anything that must be stable ACROSS RUNS depend on process-local state?**
  Set iteration order, `id()`, the `repr` of an unordered container, dict ordering from a
  non-deterministic source, time, or the environment. **Test across processes, not within
  one.**

  **This is the only defect class so far that a perfect in-process suite cannot reach.**
  Every test in one pytest run shares a single `PYTHONHASHSEED`, so a quantity that is
  stable within a process and unstable between them is invisible to every same-process
  test — *and to mutation testing*, which runs in that same process and therefore measures
  the same frozen seed. (a)–(j) all assume the defect is observable somewhere in one run.
  This one is not.

  **(k) EXTENDS TO EVERY DELTA, RATE OR TREND.** The check as first written asks whether a
  *value* depends on process-local state. The sharper form: **any assertion on a
  difference, a rate or a trend must be checked for whether its BASELINE is set by history
  outside the test.** Two Task 17 instances, both of which passed in isolation and failed
  in the full suite:

  | assertion | why the baseline is not the test's | the fix |
  |---|---|---|
  | "allocating 256 MiB moves peak RSS by 256 MiB" | peak RSS is a **high-water mark**, so the delta is `max(0, new − whatever the session already reached)`. Measured: watermark 385 MB, allocate 256 MiB, moves **67 MB** | pin the scale against an **absolute reading taken in the same test** (`current_rss_bytes`), which is not a watermark |
  | "total STREAM throughput rises with thread count" | on a saturated controller the **sign** of the difference is the session's CPU load. Unloaded 10.59 → 12.03 GB/s; under full-suite contention **11.23 → 8.44**, i.e. it falls | assert a **ratio that survives either loading** — per-core bandwidth, ~3.5× measured against a 2× bound |

  **BOTH MODULES ALREADY DOCUMENTED THE PROPERTY THAT BROKE THE TEST.** `machine.py`'s
  docstring says in capitals that `ru_maxrss` never decreases; the test asserting a peak
  delta was written anyway, by the same author, in the same sitting. **Documentation does
  not constrain the next author — tests do.** If a property is load-bearing, the guard is a
  test that fails when it is violated, not a paragraph saying it matters.

  Also measured: **`ru_maxrss` is updated lazily and can TRAIL live RSS** — 470.8 MB against
  a live 471.3 MB read an instant *earlier*. `peak >= current` is not guaranteed
  instant-to-instant, so any comparison between the two instruments needs a few percent of
  slack — nowhere near enough to absorb the 1024× unit error such a comparison exists to
  catch.

  **The worked instance:** Task 16's fence serialized with
  `json.dumps(..., default=repr)`. Measured, `{"criteria": {"aic", "bic", "hqic"}}` renders
  as three *different* strings under `PYTHONHASHSEED` 1, 2 and 3, and an object without
  `__repr__` renders its memory address. Every one of the fence's six tests passed. The
  hash changed on every resume, refitting a finished 10⁷-point store with no exception, no
  warning and no symptom but a bill. The guard is a subprocess test across several seeds,
  compared against a hand-derived constant rather than against this process.

**(h) and (i) are refinements of (e), and mutation testing does not subsume them.** (e) asks
whether the test bites when the guard is deleted; (h) and (i) ask whether the call site and
the fixture are *capable of expressing* the defect at all. A mutation catches those two only
when it happens to interact with the default or the fixture's blind spot, which is luck —
Task 11's step-rule mutation was caught by a different test, and the three-N test that was
supposed to catch it sailed through.

Also run the brief's code if it supplies any: the two highest-yield audits did, and one
found three collection errors and six failing tests out of twelve.

### Forward audit of Tasks 11–19 (run 2026-08-06, after Task 10)

The plan's later code fences were authored before Tasks 8–10 existed, so they encode those
dependencies as imagined. This is the whole-plan sweep, done once so no later task
rediscovers it mid-implementation. **Method:** every call in Tasks 11–19 into `counting`,
`criteria`, `objective`, `signal`, `statespace`, `terms`, `engines.kalman` and `outcomes`,
checked against the committed signature for scalar-vs-`(B,)` shape, positional-vs-keyword,
and `rank_x`-where-`design_rank`-is-required; plus a targeted grep for the `n_eff = n`
degradation.

| task | what the fence assumes | current reality | state |
|---|---|---|---|
| 11 | `from metamer.core.signal import DesignInfo` written at column 0 *inside* a test body | `IndentationError` on verbatim transcription; the name is never used | fixed |
| 11 | `fd_step = (ε·\|ℓ\|)^(1/3)` | design doc §8.2 specifies `(ε·\|ℓ\|/\|ℓ''\|)^(1/3)`; the fence dropped the denominator | fixed, measured |
| 11 | `assert rel < 1e-4` for complex-step vs FD | measured `rel = 1.000e+00` — the gradient is exactly `[0, 0]` | fixed |
| 11 | `richardson_gradient` starting at `fd_step(scale)` | that step *is* the cancellation floor; extrapolating there amplifies rounding | fixed |
| 11 | `obj.unconstrained_loglik(u[None,:], y, mask, t, None)`; `ConcentratedObjective(spec, ss, KalmanEngine(), Objective.ML)`; `StateSpace.from_spec(spec)` | all match | OK |
| 12 | — no calls into changed modules | — | OK |
| 13 | `objective.check_design(design, 1)` | matches `check_design(self, design, batch)` | OK |
| 13 | `free_param_index(spec)`, `ParamSpec.default`, `ParamSpec.diagnostic_limits` | all present | OK |
| 13 | `objective.unconstrained_loglik(u[None,:], y, mask, t, design)` | matches | OK |
| 13 | `optimize_series(objective, y, mask, t, design, x0, max_iter)` and `SeriesFit` with scalar `outcome: Outcome`, `loglik: float` | per-series is deliberate here — `optimize_series` *is* path A's per-series form (§17) | OK, but see the Task 14 seam below |
| **14** | `penalty_terms(spec, objective, int(mask[b].sum()), design.rank, k_beta)` | keyword-only `n_obs=`, `design_rank=`, `outcome=`, `k_beta=`, the first three `(B,)` arrays | **flagged** |
| **14** | `signal.design_info(t)` | `design_info(self, t, mask)` — `mask` is **required**, and it is what makes `rank` per series | **flagged** |
| **14** | one `CandidateScore` per `(series, candidate)` built in a double Python loop | `CandidateScores` is a single `(B, M)` block; `rank_candidates` returns one batched `Ranking` | **flagged** |
| **14** | `n_eff=float(n)` | makes `Criterion.BIC_NEFF` silently identical to `BIC` — no error, no warning, a plausible number | **flagged** |
| **14** | `FitResult.outcome: NDArray[np.object_]` holding `Outcome` members | `penalty_terms(outcome=)` and `CandidateScores.outcome` both need `(B, M)` **uint8 codes**; the store is uint8 too | **flagged** |
| **14** | `ranking: list[Ranking]`, one per series | `Ranking` already spans the batch; the list is `B` copies of the same object shape | **flagged** |
| 15, 16, 18, 19 | — no calls into changed modules | — | **not stale.** NOT pre-flighted — see the warning under (g) |
| **16** | *(re-checked at implementation)* no calls into changed modules; `json.dumps` used directly | true | (g) clean, **and the fence shipped a serializer that hashes memory addresses and `PYTHONHASHSEED`-dependent set orderings** — the second worked proof |
| **15** | *(re-checked at implementation)* every symbol binds — `ProcessSpec.labels`, `spec.terms`, `TermSpec.params`, `ParamSpec.default` | all match | (g) clean, **and the fence was wrong five ways** — the worked proof that this table clears staleness only |
| 17 | `KalmanEngine` appears in acceptance prose only, no call | — | OK |

**Task 14's fence was corrected in place on 2026-08-06**, before implementation rather than
at implementation, while the audit and the signatures were in context. All six flagged rows
are fixed in the plan; the corrections block above the fence states each one and its reason.
**(g) was then re-run against the corrected fence**: all three Python fences parse, and every
call site into `counting`, `criteria`, `objective`, `signal` and `statespace` binds against
the live signature under `inspect.signature(...).bind(...)`. One item is deliberately left
open for Task 14 rather than guessed at — `n_eff_trend[y,x,m]` is a stored primitive (§12.2)
and is not wired, because it needs the GLS trend variance and therefore a mapping from design
column to "the trend", which `DesignInfo` does not expose. Widen `DesignInfo` or record the
deferral; do not leave the store slot quietly unwritten.

**The `n_eff = n` degradation grep found exactly one live site**: Task 14, plan line 5717.
Task 9's own fence (plan lines 4093–4290) still shows the superseded scalar
`penalty_terms(..., rank_x=..., k_beta=...)` signature, but that task is committed and the
fence is now only a historical record.

**Design-doc consistency sweep (same date).** Every occurrence of `n_eff_bic` /
`n_eff_trend` now agrees on `[y,x,m]` — §9.4's slot count (line 882), §10.1 (1008–1009),
§12.2's layout (1252) and §12.5's primitive list (1311, the one corrected after Task 10).
`rank_x` does not appear in the design doc at all; it says `rank(X)` throughout (§6 table
line 299, §5.2 lines 352–359, §17 line 1863, §19 line 1996), which is `design_rank`. No
third stale-cascade instance found.

### What Task 14 inherits

Task 14 is `fit()`, the `(B, N)` driver. **Its fence was corrected in place on 2026-08-06**
(see the forward audit above) and (g) re-run against it, so start from the fence as written
rather than from the pre-audit shape. Two things beyond that:

- **Widen `DesignInfo` with a column-to-term mapping so `n_eff_trend[y,x,m]` can be
  written.** It is a stored primitive (§12.2) and needs the GLS trend variance and its
  white-noise equivalent, which means knowing which design column is the trend.
  `counting.n_eff_trend` already exists and takes those variances; nothing supplies them.
  A stored primitive that silently goes unwritten is the failure the store schema exists to
  prevent, and the mapping is cheap while the signal taxonomy is fresh.
- **`SeriesFit` is scalar and that is correct** (see Task 13 below). `fit` is where the
  conversion to `(B, M)` uint8 codes happens, exactly once.

### What Task 15 established (done — read before touching the lint)

- **THE FORWARD AUDIT'S "OK" MEANT (g) ONLY, AND THE FENCE WAS STILL WRONG FIVE WAYS.**
  Task 15's fence makes no calls into the modules Tasks 8–14 changed, so the audit marked
  it clean — correctly. Every symbol it names binds. It nonetheless mis-modelled the
  problem in five places, listed in the corrections block above the Task 15 fence in the
  plan. **Generalize this: (g) certifies a brief will run, never that it is right.**
  Tasks 16–19 are all marked "no calls into changed modules"; none of them is thereby
  pre-flighted.
- **`ILL_CONDITIONED_X` is NOT the lint's runtime counterpart** — this file said it was.
  It is a property of the *whitened design matrix*, and the lint never sees a design.
  `optimize.HESSIAN_COND_LIMIT` → `DEGENERATE_HESSIAN` is the whole *a posteriori* half.
  Corrected in `lint.py`'s module docstring, which is where a consumer will look.
- **`ParamSpec.default` is a starting value, and the lint is the first consumer for which
  that matters.** For a free parameter it says where the optimizer begins and nothing about
  where it ends; under `fixed=True` it is the model. Reading it unconditionally — which the
  fence did — reports a search *start* as a structural property. Every finding now states
  which of the two it saw (`fixed at` vs `starts at`). Any later pass that reasons about a
  spec before data inherits this distinction.
- **A rule keyed on `rho` cannot see `white + white`**, which is the exact composition
  design doc §4.8 names. Classify on `state_dim == 0` instead: a nugget has no timescale to
  key on, and two *free* nugget scales are constrained only as a sum. One free nugget beside
  any number of pinned ones is still identified — the rule is two free scales, not two terms.
- **Same-kind terms with a FREE timescale are exchangeable at any defaults.** The sum kernel
  is symmetric under swapping them and the surface `rho_a = rho_b` (where they merge into
  one term with `σ² = σ_a² + σ_b²`) is inside the searched space; nothing reorders terms
  mid-optimization, so the symmetry is real. A ratio-of-defaults rule calls a pair 1000×
  apart clean while neighbouring grid points land in different mirror images and the
  per-term σ and ρ maps come out salt-and-pepper. Ratio comparison is correct **only** when
  both timescales are pinned.
- **`WHITE_COLLAPSE_LOG_LIMIT = −½·log(eps) = 26·log 2 = 18.0218`**, derived, not calibrated
  — correlation `2⁻²⁶ = √eps` at one sampling interval, timescale fraction `0.05549`. The
  argument is that near an optimum the log-likelihood is quadratic in the parameter, so a
  model difference below `√eps` moves it by less than `eps·|ℓ|` and no optimizer can locate
  it. Same construction and same log units as `CONDITION_LOG_LIMIT`'s `−¼·log(eps)`, which
  takes the quarter power because its solve squares the condition number. `OVERLAP_RATIO =
  1.5` is **not** of this kind — it is declared policy, and its consequence is stated so it
  cannot be quietly retuned: two Matérn ν=1/2 ACFs a factor `r` apart differ at most by
  `r^(−1/(r−1)) − r^(−r/(r−1))`, which at `r = 3/2` is exactly **4/27**.
- **A silent skip in a diagnostic is the worst available failure.** The fence's
  `if "rho" not in term.params: continue` merged `white` (skipping is right) with any future
  stateful family (skipping means never checked). An unregistered kind, a family with no
  `state_dim`, and a stateful family with no `rho` each produce a `NOT_LINTABLE` finding —
  the coverage gap is visible instead of reading as a clean bill of health. SHO, whose
  timescale is `Q/omega0`, is the concrete future case and is named in §4.8.
- **An unusable `sampling_interval` raises; a degenerate spec does not.** "Warn, do not
  block" is about the *specification*. `dt = 0` makes the limit zero, `dt < 0` makes it
  negative, NaN makes every comparison False — all three return `[]`, a diagnostic
  reporting "clean" because it could not run.
- **The lint's own claims are checked against the families' `acvf`, not against the lint.**
  The lint decides by comparing timescales; `Matern12.acvf` decides by evaluating a kernel,
  so the two share no construction — pre-flight (j). Three analytic endpoints, no tolerance
  bands: `white(3) + white(4) == white(5)` bit-for-bit; two ν=1/2 terms at a shared `ρ`
  equal one term with `σ = 5` to a few ulp (the identity is exact in ℝ, the two float64
  routes round differently — `9e + 16e` against `25e`); and the correlation at the derived
  limit is `2⁻²⁶`.
- **18/18 mutations caught, nothing survived** — one per guard, including a deletion of
  each of the five corrected behaviours, `SHORT_TIMESCALE_FRACTION` reverted to the fence's
  `0.1`, the log limit switched to `−¼·log eps`, `OVERLAP_RATIO` doubled, and the
  `* sampling_interval` factor dropped. The harness was a throwaway (snapshot, substitute,
  run `tests/test_lint.py`, restore), not kept — same as Task 13's.

### What Task 16 established (done — read before touching hashing or spec identity)

- **A HASH MODULE'S TESTS ARE ALL COMPARISONS, AND A COMPARISON CANNOT SEE THE HASH
  FUNCTION.** Separators, sort order, digest algorithm, truncation length: change any and
  both sides move together. The fence pinned **no** absolute value, so all six of its tests
  passed against a serializer that was silently unstable. This is the cancellation rule
  (pre-flight (a)) applied to a module made entirely of differences. **Three golden
  constants now, not one** — each payload builder drifts independently, and a `run_payload`
  that filed a `None` fingerprint under the machine key changed every `run_hash` while
  leaving every comparison green. Each golden is hand-derived: the canonical JSON written
  out by hand in the test file, hashed with `hashlib` directly, so it shares no
  construction with `canonical_json`.
- **`json.dumps(..., default=repr)` IS A DRIFTING HASH, AND IT LOOKS FINE.** Measured:
  `{"criteria": {"aic", "bic", "hqic"}}` renders as three *different* strings under
  `PYTHONHASHSEED` 1, 2 and 3, because a `set`'s iteration order follows `str` hashing; and
  an object without `__repr__` renders its **memory address**. Either gives a different
  hash every process, so every resume of a finished 10⁷-point store reports a mismatch and
  refits — no exception, no warning, no symptom but a bill. `criteria` is exactly the field
  a user would pass as a set. **The rule: a canonical serializer must refuse what it cannot
  represent exactly, never stringify it.** The cross-process test (three seeds, compared
  against the hand-derived constant) is the standing guard.
- **`terms.py` and `hashing.py` answer the infinity question differently, on purpose.**
  `json.dumps` emits the bare tokens `Infinity` / `NaN`, which no conforming reader
  accepts. `terms.py::_transform_args_canonical` keeps them by stringifying every float,
  because a `Logit` built with an infinite bound is legitimate. `hashing.canonical_json`
  refuses, because an infinite memory budget is a user error. Same trap, opposite correct
  answer — stated in both docstrings so a later sweep does not "fix" one into the other.
- **A SILENT SKIP IN AN ALLOWLIST IS A DEMOTION.** The fence's
  `{k: config[k] for k in fields if k in config}` drops a missing field. Combined with an
  allowlist — where membership is the whole mechanism — **one typo, `data_url` for
  `data_uri`, moves the data source to provenance-only**, and two runs over different data
  share a `fit_hash` and reuse each other's fits. Nothing else in the system is positioned
  to notice, because the typo is in the config. Raise, and name *every* missing field at
  once: a bare `config[key]` lookup also raises `KeyError`, so the message is the only
  thing distinguishing a deliberate refusal from an incidental one.
- **`fit_hash ⊂ compat_hash` is load-bearing, not tidy.** §12.8 treats a `compat_hash`
  match as licence to recompute derived arrays *without refitting*, which is sound only if
  a fit mismatch always forces a compat mismatch. Computing `compat_hash` over a disjoint
  set types identically, reads plausibly, and makes "compat matches, fit differs"
  reachable — a resume would then recompute selection over primitives from a different
  model and write a complete, confident, wrong map. Pinned by a test parametrized over
  every fit-relevant field, because one field is not evidence about a set.
- **The resume workflow is testable today even though the store is not.** `rank_candidates`
  takes *only* the stored primitives — never a spec, a design matrix or the data — so
  §12.8's "recompute and continue" is implementable from what §12.5 already stores. The
  test asserts that and that re-ranking does not mutate the primitives. **This is the
  Phase 2 store contract**; if `rank_candidates` ever needs the data, §12.8's sentence
  becomes unimplementable and the three-hash split buys nothing.
- **`shared_with` is now part of spec identity** (`TermSpec.canonical()`). It was omitted,
  and the defence — `n_free` refuses such specs before anything hashes them — is an
  argument about **reachability, not identity**. Reachability changes when sharing lands,
  and at that moment two genuinely different models would share a `spec_hash` and one would
  reuse the other's cached `expm`, warm start and fits. **Generalize: "unreachable today"
  is never a reason to leave an identity function incomplete** — identity is the one thing
  that must be right before the feature that needs it exists.
- **`sort_keys=True` sorts NESTED mappings too, which masks an unsorted nested field.**
  `spec_hash` serializes with it, so a test asserting two orderings hash the same cannot
  see whether `canonical()` sorted `shared_with` itself. Caught by a surviving mutation.
  The test that bites serializes `canonical()` *without* `sort_keys` — `canonical()`
  promises a canonical dict, so it must hold independently of how a consumer serializes it.
- **A mutation can survive because it is unreachable, not because a test is weak.** With an
  explicit missing-field guard in place, mutating the comprehension below it changes
  nothing observable. That is defence in depth working, not a gap — the honest reproduction
  of the fence's bug had to mutate **both halves at once**. Check which of the two you have
  before adding a test. **23/23 caught** after the compound mutation was written correctly.
- Coverage: `hashing.py` 100% of 66 statements, 36 tests.

### What Task 17 established (done — read before touching memory, bench or the engines)

- **THE `+2` OUTPUT-SLOT CASCADE WAS REAL AND THREE PLACES AGREED WITH EACH OTHER.**
  Design doc §9.4 contradicted itself: its formula said `2p + 2k_β + 4` and named four
  scalars, its prose two paragraphs later named three (`log_lik`, `k`, `n_eff`), and its
  worked table used `M × 18 × 8`. The plan's fence transcribed the stale half and so did
  §11.5. Corrected everywhere: **path A 8682 B/series, path B 7626 B, saving 12.2%,
  `tile_side` at 1 GB = 339 shared / 186 per-point.** The fence's own
  `tile_side(1e9, 28650) == 187` would have failed against the implementation printed
  beneath it — `floor(186.83)` is 186, and the expected value was rounded where the code
  floors. Found by running the brief's arithmetic.
- **THE LARGEST DEFECT OF PHASE 1: `_augment` MATERIALIZES THE `[y | X]` BLOCK.**
  `KalmanEngine._augment` ends in `np.concatenate([y[:, :, None], x], axis=2)`, producing
  `(B, N, 1+k_β)` float64 — **25 200 B/series at N=630, k_β=4**, against a §9.4 per-series
  target of **8 682 B**. Nearly three times the entire documented cost, in one term the
  document does not have.

  **It does not vanish when the design is shared** — the case §9.4 explicitly treats as
  free (`X_term = 0`, "one copy, negligible").

  **The mechanism, because it is why the copy reads as free on a code read:** the
  `np.broadcast_to(x, (batch, n_time, k))` on the line immediately above **is a view and
  allocates nothing**. The eye stops there and concludes the shared design is not
  replicated. The `np.concatenate` on the next line then copies that view into a real
  `(B, N, 1+k_β)` array, replicating the shared design once per series.

  **THIS IS NOT A TASK 17 BUG.** §9.4 accounts for a *streaming* filter and the engine is
  not one. Three consequences:

  1. **The formula and the implementation must be reconciled, and the ENGINE is the one
     that is wrong.** The accumulator only ever needs one row at a time —
     `cols[:, step, :]` is the sole consumer — so the augmented columns can be indexed out
     of `y` and the shared `X` per timestep with no allocation at all. That is the better
     answer and it makes §9.4's model true rather than replacing it. **Phase 2 work, not a
     Task 17 patch:** it touches the hot loop of the reference engine, which every oracle
     test and the path-B agreement test are pinned against.
  2. **`tile_side` is 171, not 339, until it is fixed** (1 GB budget, shared X, d=3,
     k_β=4, p=4, M=12). Both figures are carried deliberately and both are labelled:
     `memory.bytes_per_series` is §9.4's **target** (8 682 B → 339) and
     `memory.resident_bytes_per_series` is what the code actually holds (**33 882 B → 171**).
     **Every Phase 2 tile-arithmetic number must be budgeted against the resident figure**
     until the engine streams; using the target overcommits a hard 16 GB constraint by 3.9×,
     and the run does not degrade, it dies.
  3. **STANDING CHECK — DOES THE MEMORY FORMULA DESCRIBE THE CODE, OR A MODEL OF THE
     CODE?** This is the **second** time §9.4 was wrong in a way that three places agreed
     on (the first was the `+2` output-slot cascade, where the formula, the prose and the
     worked table disagreed with each other and the fence copied the wrong one). A formula
     validated against its own arithmetic validates nothing. **Verify against measured
     resident bytes** — the slope of RSS against B, in a fresh process, sampled during the
     workload — and treat any factor above ~1.5× as a term the formula is missing rather
     than as measurement noise.
- **`ru_maxrss` IS INHERITED ACROSS `fork()`/`exec()`.** Measured: the same child reports
  **119.95 MB** spawned from a small parent and **493.28 MB — byte-identical to the
  parent's own peak** — spawned from one holding 400 MiB. Running each batch in a fresh
  subprocess *to escape process-local state was not enough*, because the contaminating
  state is **inherited**. The symptom was a fitted slope of ~1e-11 B/series: a perfectly
  flat memory curve, not an error. Use `machine.current_rss_bytes` (resident, not a
  watermark) sampled on a thread during the workload. **This is pre-flight (k) one layer
  deeper than the check as written**, and it is the second (k) instance in one task.
- **`fit` costs ~5.4 s per series** (measured at B = 5, 20, 50; linear in B) through the
  per-series scipy loop. The fence's RSS fixture at B = 10 000 would take **~15 hours**.
  Anything that wants tile-scale memory must use a batched *evaluation*, not a fit.
- **ADDING NUMBA DOWNGRADED NUMPY 2.5.1 → 2.4.6** on all four platforms (numba pins
  `numpy<2.5`), and 2.4's type stubs infer `floating[Any]` where 2.5's infer `float64`.
  That broke `mypy` on two previously-clean files (`signal.py`, `fit.py`) with no source
  change. Fixed with explicit `np.asarray(..., dtype=np.float64)` at the three sites. **A
  dependency add can break a type check in files it never touches** — re-run the whole
  suite and the whole typecheck after any solver change, not just the new files.
- **SINGLE-THREADED STREAM OVERSTATES PER-CORE BANDWIDTH BY ~3.5× HERE.** Measured on the
  mini PC: **10.59 GB/s at 1 thread against 12.03 GB/s total at 4 threads** — the memory
  controller is already nearly saturated by one core — so per-core at full occupancy is
  **3.01 GB/s**. The design's insistence on reporting bandwidth-per-core at full occupancy
  is now measured rather than asserted, and the error would flatter wide machines most,
  which is backwards for predicting the 64-core box from this one.
- **PATH B WINS AT d=3 EVEN AT ONE THREAD, AND THE MARGIN RISES WITH GAPPINESS.** Full mini-PC
  sweep, N=630, B=1000, `bench/minipc.json`:

  | d | threads | none | 10% scattered | 40% contiguous |
  |---|---|---|---|---|
  | 3 | 1 | **3.04** | 3.19 | 3.41 |
  | 3 | 4 | 4.72 | 5.15 | **5.92** |
  | 1 | 1 | 2.83 | 3.66 | 4.51 |
  | 1 | 4 | 4.24 | 4.80 | 4.98 |

  **The monotone rise with gappiness holds in all four rows** — the predicted mechanism, the
  compiled loop *branching past* a masked update while the batched path evaluates it and
  multiplies by zero. Measuring only at 10% would have understated B exactly where the data
  is gappiest.
  **The single most conservative cell is d=3, T=1, no gaps: 3.04, only just clearing 3×.**
  At B=200 the same cell measured 3.76, so **the ratio tightens as the batch grows** — path
  A amortizes its per-timestep Python overhead better at larger B. Any restatement of the
  margin must name its B and thread count.
  Budget at d=3: path A's optimistic bound is **45.2–49.2 ms/fit against the 19 ms budget
  (2.4–2.6× over)**; path B is **8.3–15.5 ms, inside budget in every cell**. At d=1 both are
  inside. **These are mini-PC numbers: feasibility and correctness only. The budget
  comparison is valid only on the 64-core box — Task 18.**
- **TWO OF MY OWN TASK-17 TESTS PASSED IN ISOLATION AND FAILED IN THE FULL SUITE.** Both
  were order-dependent for reasons the module docstrings already stated, which is the point:
  **writing the caveat down does not stop you writing the test that violates it.**
  1. *"A 256 MiB allocation moves the peak by 256 MiB"* — false whenever the session's
     watermark is already higher. Measured: watermark 385 MB, allocate 256 MiB, watermark
     moves **67 MB**. Any peak-*delta* assertion is inherently order-dependent. Pin the shim's
     unit scale against `current_rss_bytes` instead, which is not a watermark.
  2. *"Total STREAM throughput rises with thread count"* — the direction is **noise** on a
     saturated controller. Unloaded: 10.59 → 12.03 GB/s. Under full-suite CPU contention:
     **11.23 → 8.44 GB/s**, i.e. it *falls*. Both readings say the same thing about the
     machine; an assertion on the sign measures the session's load. Assert the **per-core
     ratio** (>2×, measured ~3.5×), which survives either reading.
- **`ru_maxrss` is updated LAZILY and can trail current residency.** Measured 470.8 MB
  against a live 471.3 MB read an instant *earlier*, so `peak >= current` is not guaranteed
  instant-to-instant. Any comparison between the two instruments needs a few percent of
  slack — nowhere near enough to absorb the 1024× unit error the comparison is there to catch.
- **Path A's utilization is 0.64 at d=3** (mean 68.7 iterations against a max of 107 on a
  heterogeneous sample), so path A's real cost is a further ~1.6× above its own bound. A
  homogeneous batch would have reported 1.0 by construction, which is the number the
  measurement exists to challenge.
- **The compiled engine carries the SAME `EngineId` as the numpy path, deliberately.** Both
  compute the same exact Gaussian likelihood by the same recursion, so they are
  commensurable; tagging them apart would make the selection layer refuse to rank a resumed
  run against the tile before it — the cross-machine workflow the determinism guarantee
  exists to permit.
- **The Gram must be compared against its own scale, not entry by entry.** Its entries span
  ~1e-11 to ~5e1 within one matrix because off-diagonal cross-products between
  near-orthogonal design columns cancel, so a per-entry `rtol` measures the cancellation.
  Measured largest disagreement between the two engines: 4.1e-15 absolute against a matrix
  maximum of ~5e1 — 8e-17 of scale, against a 1e-12 bound.

### What Task 17 inherits

Task 17 is the memory formula, the RSS shim, the three benchmark references, the spike
harness and the numba backend. **It is the largest remaining task — start it with a full
context window.** Its fence is marked "no calls into changed modules"; per Task 15's first
finding that clears it of staleness and of nothing else.

- **It adds `numba` and `celerite2` to `pixi.toml`, which rewrites `pixi.lock` and stages
  it.** Verified cleared: `.pre-commit-config.yaml` carries a local `check-added-large-files`
  at 2000 KB and the lock file is currently 630 KB. Re-check the number, not the note.
  `celerite2` has no `osx-arm64` conda-forge build and belongs under
  `[target.linux-64.dependencies]`.
- **The memory formula is per backend, not one formula with different constants.** Path A's
  solver state is per series; path B's is per thread. Output slots are
  `2p + 2k_beta + 4` float64 per candidate and **do not shrink under path B**.
- **Parallelism is within a tile, over series — never across tiles.** That is what makes
  peak RAM independent of core count.
- **Three benchmark references, each answering a different question.** The canonical filter
  pass (one likelihood evaluation, N=630, d=3, single-threaded, fixed θ) normalizes the
  budget comparison and carries zero proxy risk because it *is* the workload. The compute
  reference is a fixed-iteration loop of `P = F P Fᵀ + Q` at d=3, **not a 6×6 LU** — the
  filter has no matrix factorization, because the scalar observation makes the innovation
  variance scalar. The bandwidth reference is a STREAM triad past L3, measured at 1 thread
  **and** at full thread count, reporting bandwidth **per core at full occupancy**:
  single-threaded STREAM measures one core's outstanding-miss capacity, not the memory
  system.
- **The mini PC sweeps {1, 4} threads, not {8, full}** — 4 cores, so 8 measures the
  scheduler.
- Mark the new benchmarks `slow` **as they land**, not afterwards.

### Fixture facts that a fresh session will otherwise get wrong

Every one of these was discovered by building a fixture that could not fail. They are
gathered here rather than left in the task sections because the failure they prevent is
**writing a new fixture with the same blind spot**, which is a thing every remaining task
will do.

- **`DIAGNOSTIC_LIMIT` in a DESIGNED fit is reached through `sigma`'s lower limit (1e-8),
  not `rho`'s upper one (1e6).** The obvious construction — a smooth series driving `rho`
  up — does not work: a design carrying a constant, trend, offset and rate change absorbs a
  slow cosine and leaves an ordinary residual. Measured, that series comes back `OK`. What
  works is a record whose amplitude is ~1e-11. (`rho`'s upper limit *is* reachable with **no
  design**, which is how `test_optimize.py` gets there.)
- **`BIC_NEFF`'s looser penalty does not show up in `ic_best`.** The winner is normally the
  white candidate, whose `n_eff` equals `n` exactly, so its criterion value is identical
  under both criteria. The difference lives on the *correlated* candidate's ΔIC — measured
  7.823 → 7.677 at `n_eff = 194.25` against `n = 200`. A test comparing `ic_best` tests
  nothing.
- **Under white noise GLS is OLS, so `n_eff_trend` is `n` for every design column.** Any
  test meaning to pin *which* column is the trend must use a **correlated** candidate.
  Verified: the white-candidate version of that test passes against a hardcoded index 1.
- **`ILL_CONDITIONED_X` is theta-dependent**, because it is the *whitened* Gram that is ill
  conditioned, not `X_r`. Measured across five seeds at one mask: `design.condition_number`
  is 2.68e4 every time while the outcome is `ill_conditioned_x` for two and `ok` for three.
  Pin the seed, and never assert `design.condition_number` as a proxy.
- **A quadratic cannot test a step rule** (third derivative zero), and **a fixture sitting
  above a floor cannot test the floor** (`n_eff = 12` against a floor at 2.0).
- **AN IDENTITY EXACT IN ℝ NEED NOT BE EXACT IN FLOAT64, AND THE EXACT CASE IS WHAT MAKES
  THE OVER-GENERALIZATION LOOK SAFE.** Task 15 asserted `array_equal` for both halves of
  the additive-variance identity. `white(3) + white(4) == white(5)` **is** bit-exact: at
  lag 0 it is `9 + 16` against `25`, integers in binary, and at every other lag it is
  `0 + 0` against `0`. That one passed. The Matérn version at a shared ρ is
  `9·e + 16·e` against `25·e` — two different roundings of the same real number, so it
  failed by an ulp. **Ask which arithmetic the identity survives before choosing the
  assertion**: exact where the operands are representable and the operation is one
  addition, a few ulp wherever a common factor is distributed. The tolerance is then a
  statement about rounding, not a fitted agreement band — a genuine disagreement here would
  be O(1), not O(1e-16). Same shape as the σ-rescaling invariance of `cond(X_w)`: the
  useful move is knowing *which* identities the arithmetic preserves, not measuring each
  one and hoping.

### What Task 14 established (done — read before touching the driver)

- **THE `DesignInfo` NARROWING CONTRACT.** `rank`, `gram_logdet`, `condition_number`,
  `n_rows` and `unit_variance_beta_var` are all `(B,)` and describe **X restricted to each
  series' unmasked rows**. **Any consumer taking one series must call `DesignInfo.series(b)`
  first.** Handing the full-batch object to a per-series routine pairs one series' data with
  the whole batch's diagnostics: the arrays are the right dtype, sign and order of
  magnitude, so an off-by-one series lands in the store looking exactly like a fit. It is a
  plausible-number failure, not a crash. **This is what running the fence found and
  signature binding could not** — every call bound correctly and the code still did not
  work. The contract is stated in `signal.py`'s module docstring, which is where a consumer
  will actually be looking; this entry is the pointer, not the source.
- **`fit` is the single conversion point** from `optimize.SeriesFit`'s scalar world to the
  `(B, M)` uint8 arrays the store, `counting` and `criteria` speak. Not at each consumer:
  three copies of a conversion is one that disagrees with itself once.
- **`DIAGNOSTIC_LIMIT` in a designed fit is reached through sigma's lower limit, not rho's
  upper one.** A slow cosine does not do it: the design's constant, trend, offset and rate
  change absorb it and leave an ordinary residual — measured, that series comes back `OK`. A
  record whose amplitude is ~1e-11 drives sigma below 1e-8 and does.
- **`BIC_NEFF`'s looser penalty does not show up in `ic_best`.** The winner is usually the
  white candidate, whose `n_eff` equals `n` exactly, so its criterion value is identical
  under both and comparing `ic_best` tests nothing. The difference appears on the
  *correlated* candidate's ΔIC — measured 7.823 → 7.677 at `n_eff = 194.25` against
  `n = 200`.
- **A `k` that is wrong by the same amount for every candidate is invisible to every
  delta-IC test.** Feeding `penalty_terms` zeros in place of `design_rank` left the ranking,
  the weights and `n_valid` all unchanged, because the shift cancels in the difference. It
  is caught only by an ABSOLUTE check — recomputing the criterion value by hand from
  `k = k_theta + rank(X_r)` and comparing against `ic_best + delta_ic`. This is pre-flight
  (a) at the driver level, and it survived the first mutation pass.
- **A white candidate cannot distinguish design columns.** Under white noise GLS is OLS, so
  `var_gls = sigma^2 (X_r'X_r)^-1[j,j]` for every column `j` and `n_eff_trend` comes back as
  `n` for all of them. Any test that means to pin *which* column the trend is must use a
  CORRELATED candidate — verified, the white-candidate version passes against a hardcoded
  index 1.
- **`ILL_CONDITIONED_X` is theta-dependent.** It is the *whitened* Gram that is ill
  conditioned, not `X_r`. Measured across five seeds at one mask,
  `design.condition_number` is 2.68e4 every time while the outcome is `ill_conditioned_x`
  for two of them and `ok` for three. Any fixture that wants that outcome must pin its seed,
  and one asserting only `design.condition_number` is testing the wrong quantity.

### What Task 13 established (done — read before touching the optimizer)

- **A second difference wants `eps^(1/4)`; `fd_step` is for a FIRST difference.** Its
  cancellation error is `4ε|f|/h²`, not `ε|f|/h`. Measured on the real filter at N = 200
  against a nested Richardson oracle: `h = 1e-5` (the plan's rule) → **4.39e-05**,
  `eps^(1/3)` → 2.86e-05, `eps^(1/4) = 1.221e-04` → **2.98e-07**. A factor of 147, and the
  empirical optimum from a ten-decade sweep is 1e-04. `hessian_step` is a separate function
  from `fd_step` for exactly this reason.
- **An oracle that shares a stencil with its subject measures only the step.**
  `tests/oracles.fd_hessian` and `hessian_at_optimum` are the same second difference at
  different steps. The Hessian oracle is instead a **nested Richardson** construction —
  the Richardson derivative of a Richardson gradient — whose asymmetry (8.8e-13) is a free
  self-consistency check, against a 6.3e-08 disagreement with a Romberg second-difference
  reference. That gap is Romberg's error, not the nested route's.
- **Never substitute L-BFGS-B's `hess_inv`.** A converged quasi-Newton matrix is the right
  shape and roughly the right magnitude, so nothing downstream notices it is too crude —
  and it feeds reported uncertainties, TIC, the sandwich estimator and the §4.8
  near-degeneracy condition number.
- **Curvature at a non-optimum means nothing, so the Hessian is computed LAST.** The plan's
  fence checked it before the iteration cap and would report `DEGENERATE_HESSIAN` for a fit
  that had simply not converged. Non-OK fits return `hessian=None`; `DEGENERATE_HESSIAN` is
  the one exception, because there the matrix is the finding.
- **`TRUST_RADIUS_COLLAPSED` is reachable only through scipy `status == 2`**
  (ABNORMAL_TERMINATION_IN_LNSRCH), the line-search analogue of a collapsed trust region.
  Without that mapping the member is unreachable once Task 19 is deleted, and §18
  criterion 12 — every taxonomy branch reachable by a constructed test — becomes
  unsatisfiable. Tested at `outcome_for_status`'s boundary, same precedent as
  `counting.penalty_terms`' contract test.
- **Two hidden clamps in the initializer each fabricated a plausible number.**
  `np.clip(r1, 1e-6, 1 - 1e-6)` turns "anticorrelated at lag 1, which this family cannot
  represent" into `rho = 0.0724` at `dt = 1`, reported as MOMENT. `np.sqrt(np.maximum(var,
  1e-12))` reports `sigma = 1e-6` for any series below 1e-12 variance — **above sigma's own
  1e-8 diagnostic limit, so the clip never fires and the CLIPPED rung is unreachable for
  the vanishing-amplitude case.** The general rule: **a floor that sits above a diagnostic
  limit converts a reportable fact into a fabricated one**, and it makes the rung that
  would have reported it dead code.
- **The delta method's error is quantified, not assumed.** `J Σ_u Jᵀ` under a `Log`
  transform understates the true lognormal variance by `(e^s − 1)e^s/s`, `s = σ_u²`:
  **1.5% at σ_u = 0.1, 46% at 0.5, 367% at 1.0**. Large `σ_u` is the regime near a
  diagnostic limit, i.e. exactly where `DIAGNOSTIC_LIMIT` fires — so the caveat belongs
  with the headline number rather than in a footnote.
- **`SeriesFit`'s scalar shape is the one correct exception to "(B, N) is the only code
  path"**, and it is documented as such in the module docstring so a later (b) sweep does
  not "fix" it. `moment_init`, by contrast, IS batched and its **rung is per series** — one
  gap-riddled or flat pixel in a tile is the ordinary case, so a single batch-wide rung is
  right only when the whole batch falls the same way. Found by a surviving mutation: the
  per-series DEFAULT downgrade could be deleted with no test noticing, because every fixture
  had B = 1 and took an earlier batch-wide exit instead. **A mutation that survives is worth
  more than one that is caught** — this one was the only evidence that the ladder had a
  batch-granularity defect at all.

### What Task 13 inherited

Task 13 builds the optimizer driver: the initialization ladder, convergence in unconstrained
coordinates, and the Hessian at the optimum. Its fence was **audited clean** in the forward
sweep — every call matches — so the pre-flight there is about (a)–(f), (h) and (i), not (g).
Points a fresh session cannot reconstruct:

- **`optimize_series` being per series is deliberate, not a batch-granularity defect.** It
  *is* path A's permanent form if the spike goes B's way (design doc §17), so its scalar
  `SeriesFit.outcome: Outcome` and `loglik: float` are correct at that boundary. The
  conversion to `(B, M)` uint8 codes happens in `fit`, once — see the corrected Task 14
  fence.
- **`-inf` as a barrier value is legal ONLY inside `optimize_series`'s `negative()`**, never
  in anything destined for the store. Failed series carry NaN. `-inf` is a finite-looking
  sentinel that survives some consumers' checks.
- **Convergence is judged in unconstrained coordinates** — relative gradient norm plus
  relative function change, with an iteration cap producing an explicit non-convergence
  outcome. `ITER_CAP_SMALL_GRAD` still counts as a failure in the §8.6 taxonomy ("probably
  fine, **flagged**"), so do not exclude it from the numerator.
- **`fd_gradient` now takes `scale` and `curvature`.** Pass the actual `|ℓ|` — a call that
  leaves `scale` at its default silently gets `ε^(1/3)` regardless of the objective's
  magnitude, which is right for a log-likelihood but only by coincidence, and it makes any
  test of the rule vacuous (pre-flight (h)).
- **No reordering, reparameterization, or preconditioner refresh mid-optimization** without
  an explicit curvature-history reset.

### What Task 12 established (done — read before touching families or gradients)

- **The kernel protocol carries a gradient hook: `DifferentiableFamily` in
  `families/base.py`**, with `dtransition`, `dprocess_noise`, `dstationary_cov`, all
  `(B, p, d, d)`. Separate from `Family` rather than optional methods on it, because
  declining must stay cheaper than complying — Matérn ν=3/2 ships none. Design doc §8.2
  calls the hook non-retrofittable.
- **A declared ANALYTIC mode that no method backs is a hard error**, raised by
  `gradients.resolve_gradient_mode` as `AnalyticGradientError`. Not a quiet downgrade: a
  mode corrected behind the caller's back is not a reported mode, and the failure it
  prevents — a composite reporting ANALYTIC while FD silently runs — is the *inverse* of a
  silent fallback and just as invisible. `test_families` asserts it for every family.
- **`resolve_gradient_mode` reports FAMILY capability, not what the optimizer ran.** Phase 1
  ships no differentiated Kalman filter, so `fd_gradient` runs even where this returns
  ANALYTIC. `test_the_reported_mode_describes_the_family_not_the_optimizer_path` pins the
  boundary and fails the moment a likelihood-level analytic gradient lands.
- **`-expm1` is required in the DERIVATIVE too, not only in `Q`.** `dQ/dσ` written as
  `2σ(1 − exp(−x))` has measured relative error 1.09e-10 at `2Δt/ρ = 2e-7`, 8.28e-08 at
  2e-10, 7.99e-04 at 2e-14. **The ordinary fixture is blind to it**: at `Δt = 2, ρ = 5` the
  ratio is 0.8 and the two forms agree to 1.2e-16. Every later family with an exponential
  `Q` inherits both the rule and the need for a small-ratio fixture.
- **`σ` is the marginal standard deviation, so `dP∞/dσ = 2σ`.** Reading it as a variance
  gives 1, and the two agree only at `σ = 0.5` — exactly the value a fixture picks.
- **Sign conventions worth not re-deriving:** `dF/dρ = (Δt/ρ²)e^{−Δt/ρ}` is **positive**
  (longer memory, less decay per step); `dQ/dρ = −σ²e^{−2Δt/ρ}(2Δt/ρ²)` is **negative**
  (longer timescale, less new variance per step). Both have the right magnitude with the
  wrong sign under the obvious slip.
- **The two failed-fit bands reach NaN by different routes.** Measured on the gapped
  fixture: 0 post-break samples gives `rank(X_r) = 2` of 4 and the design **precheck**
  refuses it; 2 post-break samples gives full rank 4 with `cond(X_r) = 2.68e4`, passes the
  precheck, and is classified `ILL_CONDITIONED_X` **inside the whitened solve**. A routine
  that handled only the early-return path would look correct against the rank-deficient case
  alone. This is the concrete form of "`check_design`'s batch-level rank is necessary but
  not sufficient".

### What Task 12 inherited

Task 12 builds analytic forward-mode gradients for **Matérn ν=1/2 only** plus the
gradient-capability resolution machinery (`resolve_gradient_mode`, defined in the plan's
Task 12 fence, not Task 11's). Points a fresh session cannot reconstruct:

- **`richardson_gradient` is the oracle Task 12 must check its analytic `dQ/dθ` against**,
  because complex-step is dead — see the Task 11 findings below and
  [`docs/superpowers/notes/complex-step-verdict.md`](docs/superpowers/notes/complex-step-verdict.md).
  It resolves to ~6e-14 relative, and a wrong hand-derived derivative produces O(1)
  relative error, so the oracle is far stronger than the job needs.
- **Exit criterion 10 needs one family WITH an analytic gradient and one WITHOUT**, which is
  why ν=1/2 gets analytic gradients and a **test-only stub family** exists purely to
  exercise the resolution logic. Design doc §18's "Note on criterion 10". Shipping analytic
  gradients per family is explicitly *not* a Phase 1 obligation.
- **`capability.intersect_gradient_modes` already exists and is tested** — Task 12 wires it
  up, it does not re-derive it. A composite is ANALYTIC only if every term is, per
  objective, because the REML penalty is not covered by the envelope theorem.
- **Compare in unconstrained coordinates or apply `dforward` explicitly.** The two differ by
  exactly the bijector Jacobian; at `theta = [1, 5]` that is a factor of five on the second
  component — smooth, silent, wrong. `test_fd_gradient_takes_its_steps_in_unconstrained_coordinates`
  is the standing guard.

### What Task 11 established (done — read before touching gradients or the filter dtype)

- **Complex-step is not viable through this filter, and the failure is total.** Measured
  `rel = 1.000e+00`; the gradient comes back exactly `[0, 0]`. **The cause is not a
  non-analytic operation** — there is no `abs`, `min`/`max`, comparison branch or
  conjugating norm in the path, which is what design doc §8.2 expected. It is an explicit
  dtype cast, and the earliest one is `ConcentratedObjective._map`
  (`objective.py:1010`): `arr = np.asarray(values, dtype=np.float64)`, which discards the
  perturbation at `to_natural`, before the filter is ever reached. Two further layers repeat
  it — every bijector in `transforms.py` (lines 41–118) and `KalmanEngine.score`'s entry
  casts and buffer allocations (`engines/kalman.py:142–160`). Making complex-step live is
  therefore a three-layer change that puts a complex dtype through the whole hot path, not a
  one-line fix. `np.where` masking (kalman lines 185–204) is holomorphic and is *not* the
  problem.
- **The step rule's curvature denominator is load-bearing.** `h = (ε·|ℓ|/|ℓ''|)^(1/3)`, per
  design doc §8.2 — **not** `(ε·|ℓ|)^(1/3)`. Both `|ℓ|` and its derivatives scale with N, so
  the ratio is O(1) and the optimum barely moves: measured best `h ∈ [1e-6, 1e-5]` across
  `|ℓ|` from 3.2e3 (N=100) to 2.2e5 (N=5000), with `ε^(1/3) = 6.055e-06` inside that window
  at every N. The direct evidence is that the truncation branch of the sweep is
  N-independent to three digits (1.501e-08, 1.498e-08, 1.497e-08 at `h = 1e-4`). Dropping
  the denominator costs 280×–1100×: 1.19e-08 / 4.51e-08 / **1.98e-07** relative error at
  N = 100 / 630 / 5000, against 4.28e-11 / 1.00e-10 / 1.76e-10.
- **Richardson must start in the truncation-dominated region.** `RICHARDSON_H0 = 1e-2`, not
  `fd_step(scale)`. It extrapolates the truncation series, so starting at the V-curve
  minimum extrapolates rounding noise — measured 5.08e-11 from `h0 = 6.06e-6` against
  5.80e-14 from `h0 = 1e-2`, and the former is *worse* than the plain central difference it
  was meant to improve (4.43e-11). Four levels suffice: against six levels on the real
  filter, 7.4e-13 / 1.1e-12 / 6.7e-12 at N = 100 / 630 / 5000.
- **A quadratic cannot test a step rule.** Its third derivative is zero, so central
  differences are exact at any step and every rule is indistinguishable from every other.
  The reference function is `sin(3u₀) + u₁³ + 0.5·u₀u₁`.
- **A test that does not pass `scale` cannot see the step rule.** With `scale` at its
  default the numerator is 1 and the denominator is irrelevant. Caught by mutation: the
  three-N test passed with the denominator deleted until `scale` was threaded through. The
  general form — **a test can exercise a default instead of the thing it names** — is worth
  checking whenever a rule lives behind an optional argument.

### What Task 10 established (done — read only if you touch selection)

- **`k` and `n` are objective-dependent, as definitions rather than adjustments.**
  ML: `k = k_θ + k_β`, `n = n_used`. REML: `k = k_θ`, `n = n_used − design_rank`. `k_β` is
  `rank(X_r)` under both — see the `k_β` entry below. Two definitions on two model classes;
  there is no single formula with a correction term.
- **Every score carries an `engine` tag AND an `objective` tag, and ranking across either is
  a hard error — not a warning, not a coerced comparison.**
- **The reason, which is the part that does not survive without being written down:** a
  Whittle score and a Kalman score are *commensurable-looking and not commensurable*. Both
  are log-likelihoods, both are negative, both move the right way with fit quality — and
  differencing them produces a number that ranks candidates plausibly and wrongly. The
  same holds for ML against REML, which are likelihoods of different quantities entirely.
  At 10⁷ series nobody inspects an individual fit, so a plausible-and-wrong ΔIC becomes a
  plausible-and-wrong *map*. The guard is the only thing standing between those two
  outcomes, which is why it refuses rather than warns.
- `penalty_terms` in `counting.py` is a pure function `criteria.py` composes with directly;
  it carries the ML `k_β = rank` contract test that the pipeline cannot currently reach.

**The Phase 1 branch point:** Task 18 is a user gate needing runs on the 64-core box and
the MacBook. **Task 19 is built only if Task 18's verdict is "inconclusive"** — if path B
wins by ≥3× at d=3, Task 19 is *deleted, not deferred*, because a correctness reference
does not need to be fast and path A's permanent form is then the plain per-series scipy
loop already built in Task 13.

---

## Durability: push after every task commit

- A local `post-commit` hook (`.git/hooks/post-commit`, untracked) pushes the current
  branch after every commit. It pushes **that branch only** — never `--all`, never
  `--tags` — and never fails a commit if the push fails.
- Hooks are not tracked by git, so **a fresh clone will not have it.** Recreate it or push
  manually.
- Never push tags without deciding to: a `v*` tag is the release trigger.

### Open the draft PR right after Task 0's first commit

It cannot be opened before then — GitHub refuses a PR with no commits between branches:

```
gh pr create --draft --base main --head phase-1 --title "Phase 1: likelihood spine" --body "Tracks execution of docs/superpowers/plans/2026-08-05-metamer-phase1.md."
```

---

## Decisions made in conversation (not derivable from the design doc)

These came out of review rounds and exist only here and in the plan. A fresh session
cannot reconstruct them.

- **d=3 comes from a composite, not Matérn 5/2.** Design doc §9.2 offers "white + SHO" as
  the d=3 spike case, but **white is measurement noise and contributes 0 to the state**, so
  white + SHO is d=2. Phase 1 implements white (d=0), Matérn ν=1/2 (d=1), Matérn ν=3/2
  (d=2), and reaches d=3 via `white + matern12 + matern32` — which also exercises
  composition, block-diagonal assembly, and canonical ordering in the same test.
- **Thread sweep is {1, 4} on the mini PC, not {8, full}.** The mini PC has 4 cores, so 8
  threads would oversubscribe and measure the scheduler rather than memory bandwidth. At 1
  thread path B loses its parallelism advantage entirely, so a B win there is the strongest
  form of the conservative-for-A inference.
- **The spike is staged.** Stage 1 measures compiled path B against path A's *optimistic
  bound* (filter cost × mean iterations, zero optimizer overhead, 100% utilization) — a
  performance A can never exceed. The bound is one-sided, so "B wins even against A's best
  conceivable case" is safe; the converse needs the real measurement, which is stage 2.
- **≥3× at d=3 on the 64-core box decides it.** The mini PC establishes feasibility and
  correctness only; **the 19 ms budget comparison is valid only on the 64-core box.** The
  MacBook is the adversarial case — unified memory gives high bandwidth per core, so if
  path A wins anywhere it wins there.
- **REML uses the Harville (1974) convention**, pinned in `objective.py`'s docstring:
  constant is `(n − rank(X))·log(2π)`, and the basis-invariance term `+½log|XᵀX|` is
  included. Both corrections are constant in θ, so they cancel in ΔIC and **no differential
  test can detect their absence** — which is how the wrong constant survived a review.
  **OPEN: verify which convention Hector uses.** If it differs, the cross-validation carries
  a documented offset rather than a mystery.
- **σ² is deliberately NOT profiled out.** Standard GLS profiles the overall scale, and most
  geodesy does. A composite kernel has a scale *per term*, so an overall amplitude would be
  amplitude × a simplex of per-term weights — i.e. a **cross-term shared parameter**, which
  Phase 1 does not implement. This is a real comparability difference against Hector, on top
  of the REML convention. Revisit when shared parameters land; it is a Phase 3+ change to
  the kernel algebra, not a flag flip.
- **Cross-term parameter sharing is refused, not silently miscounted.** Design doc §4.7
  requires counting to handle it; nothing implements it, so `terms.free_param_index` raises
  `NotImplementedError` — same discipline as nonlinear signal terms.
- **celerite2 is optional and test-only**, and is the designated first cut if Phase 1 proves
  too large. It has no `osx-arm64` conda-forge build, so it is pinned under
  `[target.linux-64.dependencies]` and its agreement test skips elsewhere. MVN is the
  primary oracle because it validates the state-space construction (bespoke); celerite2
  validates the ACF (textbook).

---

## Cross-cutting decisions most likely to be violated by accident

- **`(B, N)` is the only code path.** `B=1` is a shape, never a separate implementation.
- **Every per-series concept must be per series.** Outcomes are shape `(B,)` `uint8`, never
  scalar. `np.linalg.cholesky` raises for the *whole stack* if one member fails, so
  validity is classified with the non-raising batched `slogdet` first and only the valid
  subset is factorized. `test_batched_results_equal_solo_results_series_by_series` is the
  standing guard for this entire class.
- **Effective rank is per series even when the design is shared.** The filter accumulates
  `XᵀΣ⁻¹X` only over each series' unmasked epochs, so the design entering the solve is X
  restricted to those rows. A globally full-rank X still yields a singular system wherever
  a gap removes all support for a column — an offset or rate-change epoch inside a seasonal
  sea-ice dropout is the ordinary case. **`check_design`'s batch-level rank is necessary but
  not sufficient**; the per-series classification happens in `gls_solution`.
- **`RANK_DEFICIENT_X` and `ILL_CONDITIONED_X` are distinct outcomes.** Exactly singular
  (a term with no support) and barely identified (a handful of samples) are different
  scientific facts, and the point of the failure map is which one happened where.
  `CONDITION_LOG_LIMIT` has no independently correct value — calibrate it against the
  two-post-breakpoint-samples test case rather than loosening that test.
- **A fully-masked tile must stay `INSUFFICIENT_DATA`, and the short-circuit is where it
  gets lost.** `objective.evaluate` returns early when no series passes the precheck, so the
  engine never runs and its `INSUFFICIENT_DATA` never enters the outcome merge. Measured: a
  tile where *every* series is all-masked comes back `RANK_DEFICIENT_X` with
  `is_failure=True` and `is_eligible=True` — every land pixel in both the numerator and the
  denominator of the §8.6 failure rate, which is the exact corruption the precedence ladder
  exists to prevent. It hides from any test that masks only *some* series, because then
  `np.any(precheck == OK)` is True and the branch is never entered. The Antarctic interior is
  an ordinary whole-tile case, not an edge case.
- **There are two ranks and they are not interchangeable.** `ObjectiveResult.design_rank` is
  the **design-level** `rank(X_r)` — the design restricted to that series' unmasked epochs.
  It is what Harville's constant uses and what REML's `n = n_used − rank` must use.
  `ObjectiveResult.rank_x` is the **whitened-Gram** rank the engine reports, and it carries
  the `-1` failed-series sentinel. They are equal on every passing path today, which is
  exactly why the distinction is written down and pinned by a test asserting they *can*
  differ — "equal in practice" is how an off-by-one reaches BIC. Count with `design_rank`.
- **`rank_x = -1` is the failed-series sentinel, and it is a trap for Task 9.** `rank_x` is an
  integer, so NaN is unavailable and `-1` is used instead. It is unambiguous as a *check*
  (real ranks are non-negative) but it is **not fail-loud under arithmetic**: REML's effective
  sample size is `n_obs − rank(X)`, and `n_obs − (−1)` silently gives `n_obs + 1` — a sample
  size larger than the number of observations, entirely plausible-looking, feeding straight
  into BIC. Gate on `outcome == OK` before doing arithmetic on `rank_x`, never after.
- **Failed series carry NaN, not −inf,** in anything destined for the store. −inf is a
  finite-looking sentinel that survives some consumers' checks. It is the optimizer's
  internal barrier value only.
- **`terms.free_param_index` is the single source of truth** for the flat parameter vector.
  Never re-derive the layout locally. `len(free_param_index(spec)) == spec.n_theta()` is the
  invariant that keeps the searched vector and `k` in agreement.
- **`StateSpace` slices `theta` over all of a term's parameters**, so a free-only vector
  must go through `ConcentratedObjective.hydrate` first, or a frozen parameter shifts every
  later coordinate one slot left.
- **No reordering, reparameterization, or preconditioner refresh mid-optimization** without
  an explicit curvature-history reset.
- **Never interpolate gaps** — mask the update, keep the prediction.
- **The white-noise nugget is keyed on exact `lag == 0.0`, which is a trap for Task 8.**
  When the objective builds Σ from `|t_i − t_j|`, two *distinct* observations that share a
  timestamp both get σ² placed **off-diagonal** — perfectly correlated measurement noise
  rather than two independent draws. Duplicate timestamps are ordinary in real records
  (the Matérn ν=1/2 `Δt = 0` case exists precisely because of them), so this is reachable,
  not hypothetical. Whatever builds Σ must key the nugget on *index* identity, not on the
  lag being zero.
- **`cond(X_w)` is invariant under a uniform rescale of Σ — so you cannot make a design
  ill-conditioned by shrinking σ.** This is analytic, not empirical, and the derivation is
  what stops the retry: `X_w = Σ^{-1/2}X`, so `Σ → cΣ` sends `X_w → c^{-1/2}X_w`, and
  `cond(αA) = cond(A)` for any `α ≠ 0` because every singular value scales by `|α|` while
  the ratio does not. Where white noise dominates, `Σ ≈ σ²I`, so changing σ *is* that
  uniform rescale to within the other terms' contribution. What does move the conditioning
  is giving the design more post-breakpoint degrees of freedom than the post-breakpoint
  samples can carry. Do not go looking for a σ that works; there isn't one.
- **The conditioning thresholds are derived from float64, not calibrated against a fixture**,
  and both are stated in `log cond(X_w)` units so they are directly comparable:
  `CONDITION_LOG_LIMIT = −¼·log(eps) = 9.0109` (cond 8.2e3) and
  `RANK_DEFICIENT_LOG_LIMIT = −½·log(_RANK_RTOL) = 11.5129` (cond 1e5). The exponent is
  **−1/4, not −1/2**, because the solve runs on the normal equations so the Cholesky sees
  `cond(X_w)²`. Taking `1/√eps ≈ 6.7e7` literally puts the ill-conditioned boundary *above*
  the rank cutoff and makes `ILL_CONDITIONED_X` unreachable — which is the defect the
  import-time ordering invariant now guards. A fixture's job is only to prove all three
  bands are **reachable**; it must never specify a production constant, because tuning a
  threshold until a hand-built case fires specifies nothing.
- **Condition number grows with record span even for a well-supported design**, so the
  false-positive direction is real. Measured on full-support
  `[Constant, Trend, Accel, Annual, SemiAnnual]` monthly data: `cond(X_w)` = 2.8 (5 yr),
  33.9 (20 yr), 76.0 (30 yr), 210.6 (50 yr), 840.7 (100 yr). Against the derived 8.2e3 the
  century-long worst case clears by about 10×; against a calibrated 1e3 it cleared by
  0.17 nats. Re-measure against real records before Phase 2.
- **Never take `log|XᵀX|` via `slogdet(XᵀX)`.** Forming the Gram squares the condition number,
  and `slogdet` then returns a **negative sign** for a design that is genuinely full rank —
  measured at `cond(X) = 1e9`, where the `sign > 0 else -inf` idiom produced `gram_logdet =
  -inf` for a 4/4-rank design, i.e. a spurious `RANK_DEFICIENT_X`. Use `2 · Σ log s` from
  `svdvals(X)` instead: it is accurate to ~1e-8 absolute at that conditioning and needs one
  fewer decomposition. The same trap applies anywhere a Gram log-determinant is wanted.
- **The time axis is decimal years.** In seconds since 1970 the same 20-year monthly design
  goes from `cond(X) = 3.4e1` to `3.3e32` and from rank 7/7 to 2/7 — `cos(annual)` becomes
  identically 1.0 and the sine columns lose all float64 phase. Design columns are
  deliberately **not** auto-scaled: normalising shifts `gram_logdet` by `2 Σ log s_j`, which
  corrupts the REML constant unless the scale vector is carried and unwound in the objective.
- **numpy 2's `np.linalg.eig` returns `complex128` unconditionally**, even for a real matrix
  with real eigenvalues. Any inner product on its eigenvectors must be Hermitian
  (`np.vdot`, not `@`), or the imaginary part is silently truncated with a `ComplexWarning`.
- **Compute `1 − e^{−x}` as `-np.expm1(-x)`, never as `1.0 - np.exp(-x)`.** In the Matérn
  ν=1/2 `Q(Δt) = σ²(1 − e^{−2Δt/ρ})` the naive form loses all significant digits for small
  `Δt/ρ`: measured relative error 8e-8 at `Δt/ρ = 1e-10`, 8e-4 at 1e-14, and `Q` flushes to
  exactly zero below ~5e-17. `ρ`'s diagnostic limit is 1e6 and the user chooses the time
  units, so this is reachable. Every later family with an exponential `Q` inherits the rule.
- **Analytic `F`, `Q`, `P∞` per family.** The general `expm`/Lyapunov path is a test
  reference and a degeneracy fallback; frequent firing is a bug signal.
- **THE eps-DERIVED CONSTANT, IN GENERAL FORM. THREE CONSTANTS, ONE CONSTRUCTION.**
  A numerical threshold in this codebase is not chosen. It is derived from float64's
  precision and **the number of times the quantity is squared or differenced on its way to
  the objective**. Each squaring halves the exponent; each difference of order `m` divides
  by `h^m` and moves the optimum to `eps^(1/(m+2))`.

  | constant | path to the objective | rule | value |
  |---|---|---|---|
  | `lint.WHITE_COLLAPSE_LOG_LIMIT` | ℓ is quadratic in θ near the optimum, so a model difference is resolvable only above `√eps` — one squaring | `−½·log eps` | 18.0218 (cond 2⁻²⁶) |
  | `objective.CONDITION_LOG_LIMIT` | the solve runs on the normal equations, so the Cholesky sees `cond(X_w)²` — one squaring | `−¼·log eps` | 9.0109 (cond 8.2e3) |
  | `gradients.fd_step` / `hessian_step` | an `m`-th difference divides by `h^m` | `eps^(1/(m+2))` | 6.055e-06 / 1.221e-04 |

  All three are stated in the **same units as the quantity they threshold** (log-cond for
  the first two) so they are directly comparable, and none may be moved by loosening a test
  until a fixture fires. **When a fourth threshold is needed, ask how many squarings and how
  many differences sit between it and ℓ, then read the exponent off that — do not pick a
  round number and do not copy a neighbouring constant.** Copying the neighbour is the
  measured default mistake: it cost 147× at the Hessian step and 280×–1100× at the gradient.

  **A constant that genuinely cannot be derived is POLICY and must be labelled as such,
  with its consequence stated** — `lint.OVERLAP_RATIO = 1.5` is the worked example: it says
  in its own docstring that two Matérn ν=1/2 ACFs a factor `r` apart differ at most by
  `r^(−1/(r−1)) − r^(−r/(r−1))`, which at `r = 3/2` is exactly 4/27. Changing the number
  means re-deriving that consequence.

  **Tree-wide sweep run 2026-08-06** over every module-level numeric constant in
  `src/metamer/`. Derived or measured, no action: `EIGEN_TARGET_ACCURACY` (and
  `EIGEN_CONDITION_LIMIT`, which divides it by eps), `UNIQUE_DT_RTOL` (sized between two
  stated scales), `_ACF_MAGNITUDE_TOL` (ulp slack, with a counterexample showing what it
  does *not* absorb), `Q_SERIES_CROSSOVER` (measured against a 60-digit `Decimal` oracle on
  a 6000-point grid), `_Q_SATURATION_U` (documented bit-identical wherever it fires),
  `MAX_PAIR_BYTES` / `_FFT_BYTES_PER_EPOCH` (measured budget), `RICHARDSON_LEVELS`
  (measured, 4 against 6), `_UNRANKED` (derived from the ladder length). **Four flagged as
  picked:**

  | constant | state |
  |---|---|
  | **`optimize.HESSIAN_COND_LIMIT = 1e10`** | **the clear instance.** A one-line docstring, no derivation, no measurement. The Hessian is inverted once for the delta-method covariance, so the same construction as row 1 above gives `1/√eps = 6.7e7` — the current value is ~150× looser. It also gates `DEGENERATE_HESSIAN`, which is the identifiability lint's runtime counterpart, so the two halves of §4.8 are calibrated on different footings. **Open — do not change it in passing; it moves a reported outcome and needs its own test work.** |
  | `signal.X_RANK_RTOL = 1e-10` | documented by *contrast* with the engine's Gram threshold, which is the derivation of the relationship but not of the root value. numpy's own default is `max(M,N)·eps ≈ 1e-15`. `RANK_DEFICIENT_LOG_LIMIT` is derived from this, so the derived constant rests on a picked one. |
  | `optimize.GRAD_TOL = 1e-5` | the docstring derives the *form* (relative, scaled by `max(\|ℓ\|, 1)`) and not the value. Legitimately policy — "how converged is converged" — but unlabelled as such. |
  | `objective._NEGATIVE_REDUCTION_RTOL = 1e-6` | one line, no derivation. Policy-ish; small blast radius. |

- **THE FINITE-DIFFERENCE STEP RULE, IN GENERAL FORM.** An `m`-th order difference divides
  by `h^m`, so its cancellation error is `O(ε|f|/h^m)`, its truncation error is `O(h²)`, and
  the optimal step scales as **`ε^(1/(m+2))`**:

  | derivative | optimal step | value |
  |---|---|---|
  | first (`fd_step`) | `(ε·\|f\|/\|f''\|)^(1/3)` | 6.055e-06 at ratio 1 |
  | second (`hessian_step`) | `(ε·\|f\|/\|f''''\|)^(1/4)` | 1.221e-04 at ratio 1 |

  **Two independent measurements agree with it.** Task 11: using `(ε|ℓ|)^(1/3)` — the cube
  root with no curvature denominator — cost 280×–1100× relative gradient accuracy on the real
  filter at N = 100/630/5000. Task 13: reusing the *first*-difference step for a second
  difference cost **147×** (4.39e-05 against 2.98e-07 at N = 200). Both were the plan fence's
  proposal, and in both cases the empirical optimum from a ten-decade sweep landed on the
  formula. **A third instance should be recognized, not rediscovered** — if a routine takes an
  `m`-th difference, its step is `ε^(1/(m+2))`, and reusing a neighbouring rule is the default
  mistake. Keep each order's rule in its own named function so reuse is not the path of least
  resistance.
- **A CLAMP, FLOOR OR EPSILON GUARD SITTING ABOVE THE DIAGNOSTIC LIMIT OF THE QUANTITY IT
  GUARDS IS A FABRICATION MACHINE.** It does two things at once: converts a reportable fact
  into a plausible number, and makes the outcome or rung that would have reported it
  **unreachable**, so no test can see the loss. The clean case: `sqrt(maximum(var, 1e-12))`
  gives `sigma = 1e-6` against sigma's own `1e-8` lower diagnostic limit, so the diagnostic
  clip never fires and `InitRung.CLIPPED` becomes dead code for the vanishing-amplitude case.
  The second instance in the same function: `clip(r1, 1e-6, 1-1e-6)` turns "anticorrelated at
  lag 1, which this family cannot represent" into `rho = 0.0724` at `dt = 1`, reported as
  `MOMENT`. **Rule:** every guard must be checked against the diagnostic limit of what it
  guards; if it sits above, it is deleting a diagnosis.
  **Tree-wide sweep run 2026-08-06** over `np.clip`, `np.maximum`, `np.minimum` and bare
  epsilon constants in `src/metamer/core/`: **no further instances.** Every other guard is
  either the diagnostic clip itself (`optimize.py:361`), part of a stated definition
  (`counting.n_eff_trend`'s `clip(ratio, 1, n)`), a scale for a *relative* tolerance
  (`objective.py:521`, `statespace.py:239`), an index bound (`kalman.py:301`), a
  mathematically-correct basis function (`signal.py:188`, `RateChange`'s ramp), or a
  provably-inactive saturation (`matern32._Q_SATURATION_U = 60.0`, documented bit-identical
  wherever it fires). Also checked: every family's parameter `default` lies inside its own
  `diagnostic_limits`, and every `diagnostic_limits` inside its `bounds` — a default outside
  its limits would report `CLIPPED` on every cold start.
- **Scores carry an engine tag AND an objective tag**; ranking across either is a hard error.
  The tags are **per candidate**, not per run: engine capability is resolved per composite
  spec (design doc §4.2), so a candidate set genuinely can mix engines — which is the
  situation the guard exists for. The guards run on the whole candidate set *before*
  anything is scored, because deriving the tag sets from the surviving subset would make the
  same misconfigured run raise on one tile and write a wrong map on the next.
- **The criteria layer is `(B, M)` like everything else.** `CandidateScores` holds `loglik`,
  `k`, `n`, `n_eff` and `outcome` as `(B, M)`; `rank_candidates` returns `delta_ic` and
  `weights` as `(B, M)` and `ic_best`, `best_index`, `n_valid` as `(B,)`, which is the
  `/selection/` layout of §12.2. `best_index = -1` is the no-winner sentinel. The plan's
  Task 10 fence proposed a scalar `CandidateScore` per candidate per point; that is a
  per-point Python loop over 10⁷ grid points, and it makes the caller unpack
  `penalty_terms`' arrays by hand, which is precisely where the `rank_x` / `design_rank`
  substitution gets reintroduced.
- **Selection survival is `outcome == OK`, never `isfinite(loglik)` and never
  `not Outcome.is_failure`.** An iteration-capped or diagnostic-limited candidate still
  carries the last finite log-likelihood it evaluated, so a finiteness gate resurrects a fit
  the failure ladder rejected — and it can win. `is_failure` is False for
  `INSUFFICIENT_DATA` and `NOT_ATTEMPTED` **by design** (they are excluded from the failure
  *numerator*, not from the outcome ladder), so gating on it admits land and permanent ice
  into the ranking and a wholly-masked tile reports a confident selection.
- **A criterion whose penalty is ≤ 0 is not a criterion.** Measured: at `n = 1` BIC's penalty
  is exactly `0.0` and HQIC's is `−inf`; at `n = 2` HQIC's is `−2.93`, i.e. it *rewards*
  parameters. All three hand the win to the most complex candidate whatever the data say,
  and `n = 1` is reachable because `penalty_terms` guarantees only
  `n_obs − design_rank ≥ 1`. So `BIC` is defined for `n > 1`, `HQIC` for `n > e`,
  `BIC_NEFF` for `n_eff > 1`, and outside those `ic_value` returns **NaN**, which flows into
  the same "not rankable" path as a failed fit. **Do not clamp the argument instead** — a
  floor at 2.0 silently answers a different question, and at `n = 2`, `n_eff = 1.5` it makes
  `bic_neff` exactly *equal* to `bic`, contradicting the requirement that it be strictly
  smaller whenever `n_eff < n`.
- **`n_valid` counts fits, not finite criterion values.** The store holds one `n_valid[y,x]`
  shared by every criterion (§12.2 gives it no `c` axis), so it must not depend on which
  criterion was asked for. An AICc of `+inf` at `n ≤ k + 1` is ranked last with weight `0`
  and `ΔIC = +inf` and still counts as valid; defining validity as `isfinite(ic)` would make
  the same fits report different `n_valid` under AIC and under AICc.
- **AICc diverges rather than turning its correction negative.** At `n < k + 1` the
  denominator `n − k − 1` is negative and `2k(k+1)/(n−k−1)` is negative, so AICc would score
  an over-parameterized candidate *below* plain AIC — the opposite of what AICc is for. NaN
  must be preserved as NaN there rather than collapsing to `+inf`, or a missing primitive
  reads as a real, infinitely bad score.
- **Counting is per objective**: ML `k = k_θ + k_β`, `n = n_obs`; REML `k = k_θ`,
  `n = n_obs − rank(X)`. Two definitions on two model classes, not one with an adjustment.
- **`k_β` is `rank(X_r)`, not `ncol(X)`, under *both* objectives.** A criterion's `k` is the
  dimension of the identified parameter space, and the log-likelihood is flat in the
  `ncol − rank` unidentified directions, so charging for them penalises what no record
  informed. `ncol` under ML beside `rank` under REML would also have the two objectives
  asserting different answers to "how many coefficients does this design resolve".
  Precedent: R's `extractAIC.lm` / `logLik.lm` use `rank`. The plan's criterion 13 mandates
  rank-not-`ncol` for REML's `n` and is **silent** on ML's `k` — this resolves that silence.
  Unreachable today, because Task 8 fails a deficient `X_r` before scoring, so the test that
  pins it is a contract test on `penalty_terms` (a pure function Task 10 calls directly),
  not integration coverage. That is the right place for it: the function boundary is the
  only place the rule can be stated.
- **`n_eff_bic`'s closed form is invalid under a mask** and its `ρ` is a model quantity, not
  a data statistic. See design doc §10.1, corrected 2026-08-06: the realized-pairs form
  `n_used² / Σ_{i,j∈used} ρ(t_i−t_j)²` is exact for any mask and any axis; the lag-index
  closed form is a fast path for the complete regular case only. Measured error from using
  the closed form under a half-mask: **−48.16%**. Both `n_eff` variants are per
  `(point, candidate)` because both are functions of the fitted model.
- **`n_eff_bic` is computed once at the optimum, never inside the objective.** The
  realized-pairs sum is `O(n_used²)` — about 400 000 evaluations per series at `N = 630`.
  Anything that calls it in a fit loop is a bug.
- **The FFT pair-count path is refused on an irregular axis, not approximated.** Exact
  integer pair counts per lag come from an FFT autocorrelation of the mask indicator, which
  is valid only when every `t_i − t_j` lands on an integer multiple of a common step.
  Measured on `t = cumsum(U[0.5, 2.5])` using the step `unique_dt` actually picks:
  **−61.07%**. Regularity is decided by `statespace.unique_dt` (reused, not re-rolled); an
  irregular axis falls back to a chunked dense sum with a stated memory bound. Both paths
  are capped by `max_pair_bytes` — the FFT path blocks over *series*, which is exact because
  series are independent there (peak flat at 1.06 MB from B=100 to B=4000 against 141 MB
  uncapped, values bit-identical).
- **The memory formula's output-slot count is `M × (2p + 2k_β + 4) × 8 + M × 3`.** The `4`
  is `log_lik`, `k`, `n_eff_trend`, `n_eff_bic` as float64 — it was `2` while both `n_eff`
  variants were believed per-point. **Task 17 consumes this**; the tile-size arithmetic in
  design doc §9.4 changes with it. Design doc **§12.5's primitive list still said
  `n_eff_trend[y,x]` / `n_eff_bic[y,x]`** after §10.1 was corrected on 2026-08-06 — i.e. the
  document contradicted itself, and §12.5 is exactly the sentence Task 17 would have read.
  Corrected to `[y,x,m]` on 2026-08-06 to match §12.2's layout block.
- **float64 throughout `core`**; float32 only at the batch/IO boundary, converted per dask
  chunk so both representations never coexist.
- **Parallelism is within a tile, never across tiles** — that is what keeps peak RAM
  independent of core count.

---

## Hardware

| machine | threads | role |
|---|---|---|
| Ubuntu mini PC — 4 slow cores, 16 GB RAM (~10 GB free) | {1, 4} | primary development; correctness, oracles, memory formula. **Cannot answer the budget question.** |
| Linux box, 64 cores (RAM unknown — establish before use) | {1, 4, full} | **the decisive measurement**; only valid place for the 19 ms budget comparison |
| Apple Silicon MacBook, 32 GB | {1, full} | adversarial case for path A; arm64 smoke test |
| SkyPilot via a forthcoming `cloudify` skill | — | future; design doc §15.5 |

Machine plan and the two normalization instruments (canonical filter pass for the budget
question; compute/bandwidth roofline pair for cross-machine prediction) are in design doc §9.2.

---

## Gotchas discovered

- **`numba` PINS `numpy<2.5`, SO ADDING IT DOWNGRADED NUMPY 2.5.1 → 2.4.6** on all four
  platforms (Task 17, 2026-08-07). **numpy 2.4's type stubs infer `floating[Any]` where
  2.5's infer `float64`**, so `mypy` began reporting errors in `signal.py` and `fit.py` —
  **files nobody had touched**, with no source change between the clean run and the failing
  one. If a future session sees `Returning Any from function declared to return
  ndarray[..., float64]` or an `arg-type` mismatch on a `floating[Any]`, this is why; it is
  an environment fact, not a regression in the code. Fixed with explicit
  `np.asarray(..., dtype=np.float64)` at the three affected sites (`Trend.columns`,
  `Accel.columns`, `fit.py`'s `np.linalg.inv`). **General rule: a dependency add can break a
  type check in files it never imports — re-run the whole suite AND the whole typecheck
  after any solver change, not just the new files.**
- **`celerite2` has no `osx-arm64` conda-forge build** (verified 2026-08-04). Coverage is
  split between conda-forge and PyPI with no single source covering every target platform.
  Full table in design doc §15.2.
- **`pixi search` without `--platform` reports an arbitrary subdir.** Always pass
  `--platform`, and use a known-good package (e.g. `numba`) as a control — `rg | head`
  swallows the non-zero exit, so an empty result looks identical to a failed query.
- **`gitleaks` is not on conda-forge.** Install the binary release from GitHub instead.
- **The prompt's `tile_side = sqrt(block_bytes / (n_time · itemsize))` counts only the
  float64 data.** Full accounting gives **339** instead of 445 at a 1 GB budget with a
  shared design matrix, and **186** with per-point regressor fields. Design doc §9.4.
  (Was 343 / 187 while the output-slot scalar count was 2; corrected with the rest of the
  `+4` cascade on 2026-08-07 — see the Task 17 findings.)
- **Per-point regressor fields (e.g. GIA) cost `N × k_β × 8` per series** — 20.2 kB at
  N=630, k_β=4, ~2.4× everything else combined. `signal.DesignInfo` exists so that widening
  is a shape change rather than a signature rewrite.
- **`pixi.lock` (645 KB) exceeds the `check-added-large-files` 500 KB limit.** It is
  already tracked, so ordinary commits pass — but **Task 0 adds `psutil` to `pixi.toml`,
  which rewrites the lock file, stages it, and the pre-commit hook will fail the commit.**
  Task 17 does the same with `numba` and `celerite2`. Fix before Task 0 by raising the
  limit in `.pre-commit-config.yaml`:

  ```yaml
  - id: check-added-large-files
    args: ['--maxkb=2000']
  ```

  A lock file is legitimately large; raising the limit is correct, excluding the file is not.

  **VERIFIED CLEARED 2026-08-06, not merely flagged.** `.pre-commit-config.yaml` line 38–40
  carries a local reimplementation with `max=2000000` bytes and the hook is named
  `check-added-large-files (limit 2000 KB)`; `pixi.lock` is currently **630 KB**. Task 17
  adds `numba` and `celerite2`, which will rewrite and stage it — that is expected and will
  pass. Re-check the number, not the note, if the lock file grows past ~2 MB.
- **The GitHub token has no `workflow` scope.** Any push adding `.github/workflows/` is
  rejected outright.
- **A global pre-commit `PreToolUse` hook blocks `git commit` while any native task is
  `in_progress`.** `pre-commit-check-tasks.sh` counts in-progress tasks by replaying
  `TaskUpdate` calls from the **controlling session's** transcript, so marking a task
  `in_progress` before dispatching an implementation subagent locks that subagent out of
  committing — and nothing the subagent does to the task board can clear it, because its
  own `TaskUpdate` calls land in a different transcript. It also counts a `TaskUpdate` that
  was itself rejected by another hook. Leave a task `pending` while its implementer works
  and mark it `completed` after the commit lands. Never work around this with `--no-verify`
  or by editing `settings.json`.
- **`ruff format .` at the repo root used to rewrite the plan document.** ruff 0.16 formats
  Python code fences inside markdown when it walks a directory, and this plan's fences are
  the specification — they are extracted verbatim into per-task briefs and transcribed into
  code, so reformatting them silently changes what gets implemented. Verified by copying the
  plan and running the formatter on the copy: "1 file reformatted". Fixed by
  `extend-exclude = ["*.md"]` under `[tool.ruff]` in `pyproject.toml`; re-verified after.
  The pre-commit hooks were never affected — they are `types: [python]`-filtered.
- **`psutil` added no `pixi.lock` diff** (Task 0): it was already resolved on all four
  platforms as a transitive dependency. The lock-size limit raise still matters — Task 17
  adds `numba` and `celerite2`, which will genuinely rewrite it.
- **Two implementation agents were run against this one working tree at once, and one reset
  the branch over the other's pushed commits.** Task 8 was built twice: A committed
  `36fca08` (fixture-calibrated threshold), B built on A's tree and committed `ed0b15f`
  (derived thresholds, per-series `DesignInfo`), then B reset to `5b6c5ab` and re-committed
  the identical tree as `d7d69c1` to get a clean single-commit history — taking two
  already-pushed commits off the branch. Reconciled with `git merge -s ours origin/phase-1`
  (`0134154`): tree unchanged, both commits ancestors again, nothing force-pushed.
  **A behaviour-level diff of `36fca08` against HEAD found exactly one thing B had lost** —
  see the fully-masked-tile entry above. B's version otherwise dominates: it merges strictly
  more outcomes, its `DesignInfo` widening removes θ-free work A repeated every iteration,
  its `eigvalsh` route classifies a negative-definite Gram that A's `svdvals` route could not
  see at all (singular values are absolute eigenvalues, so they cannot tell `−I` from `+I`),
  and its 72 tests subsume A's 62 with no assertion lost. Constraints against a recurrence
  are now in the user's global `CLAUDE.md`: one writer per working tree, and never rewind a
  branch whose commits have been pushed.
- **Task 14's code fence is stale against Tasks 9 and 10 and must be corrected before it is
  implemented.** Three ways: it calls `penalty_terms(spec, objective, int(mask[b].sum()),
  design.rank, k_beta)`, a scalar positional signature that Task 9 replaced with keyword-only
  per-series arrays (`n_obs=`, `design_rank=`, `outcome=`, `k_beta=`); it builds one
  `CandidateScore` per `(series, candidate)` inside a double Python loop, which `criteria.py`
  no longer accepts; and it passes `n_eff=float(n)`, so `n_eff_bic` is never called and
  `Criterion.BIC_NEFF` would silently degrade to `BIC`. The pattern is general — **the plan's
  later fences were written against the pre-Task-9 scalar model**, so every remaining fence
  that touches `counting` or `criteria` should be diffed against the committed signatures
  before transcription, not after.
- **The suite is ~255 s, and the `slow` marker is now in place.** `pixi run test` is the
  full sweep and is what every end-of-task verification must run; `pixi run test-fast`
  (`-m "not slow"`, 540 of 583) is for iteration only. What is marked and why:
  **all of `tests/test_fit.py`** (module-wide — every test drives the real filter through
  the whole driver on five-series batches, so there is no fast subset worth carving out),
  the N = 5000 gradient step-rule case, and four `tests/test_optimize.py` tests that run
  real optimizations. **None of it is optional.** Exit criterion 9 requires the three widely
  separated N, and the standing batched-equals-solo invariant is meaningless on a batch of
  healthy series — the heterogeneous batch is *why* `test_fit.py` is slow.
  Do **not** reach for `RICHARDSON_LEVELS` to buy time: that trades accuracy headroom in the
  one module whose job is accuracy. Task 17 adds a compiled backend and machine benchmarks,
  so mark those `slow` as they land rather than after.
- **A SURVIVING MUTATION IS NOT ALWAYS A TEST GAP — IT CAN BE UNREACHABLE CODE.** Two
  causes, and the response differs:
  1. *No test protects the guard* — the ordinary case, and the one worth acting on. Task
     13's per-series DEFAULT downgrade is the example.
  2. *The mutated line cannot be reached* — defence in depth working as intended. Task 16's
     `_subset` has an explicit `if missing: raise` above a `{key: config[key] ...}`
     comprehension; mutating the comprehension to the fence's `if key in config` filter
     changes nothing observable, because the guard fires first. **The honest reproduction
     of the fence's bug had to mutate BOTH halves at once**, and then it was caught.

  **Diagnose which before chasing it as a coverage gap.** The tell is whether removing the
  guard *above* the mutation makes the mutation bite: if it does, the survivor is
  unreachable code, not a weak test. Writing a compound mutation is the correct fix, and
  the resulting count (23/23) means more than a 22/23 with a misdiagnosed survivor.
- **A mutation-testing script that restores from a snapshot will silently revert edits made
  while it runs.** The Task 13 bite script captures the file at start and writes that text
  back after every mutation; two annotation fixes made during the ~17-minute run were undone
  by it, and `mypy` then reported errors against a file that looked correct in the editor.
  Do not edit a file while a mutation run is rewriting it, and re-run `typecheck` **after**
  the run rather than during. The tell is a mypy error whose line does not match what the
  file now says.
- **`pixi run test-cov <path>` measures the wrong thing and runs the whole suite.** pixi
  appends task arguments, so `pixi run test-cov tests/test_lint.py` becomes
  `pytest --cov tests/test_lint.py`; `--cov` takes an *optional* value, so the path is
  consumed as `--cov=tests/test_lint.py`, no test path remains, and the full 516-test sweep
  runs while coverage measures a module it never imports. It exits 0 and prints a plausible
  report. Put a flag first — `pixi run test-cov -q --cov-report=term-missing <path>` — so
  `--cov` is followed by something starting with `-`. (`pixi run test --cov=<module>` is not
  a way out: it fails with `ImportError: cannot load module more than once per process`.)
- **A test helper can produce the failure it is meant to construct.** Task 10's `_scores`
  helper wrote `np.full(shape, np.nan) + k` where it meant `np.full(shape, k)`, so every
  `k` and `n` came out NaN and twelve tests failed against a correct implementation. It was
  the implementation's own `OK`-beside-NaN guard that reported it, by name and by index —
  which is the argument for making that guard raise rather than silently drop the cell.
- Per user global instructions: never do investigative `git checkout <sha>` inside the
  working tree. Use `git show <sha>:<path>`, `git worktree add`, or `git diff <sha>`.

---

## Open questions

Still open. **A new session must not assume these were settled.**

1. **CI.** Not specified anywhere. Determines whether Tier-2 platforms and the optional
   celerite2 agreement test are exercised, and whether Windows could ever be claimed.
   Blocked in practice by the missing `workflow` token scope.
2. **Index-space vs area-weighted adjacency** for the failure clustering statistic (design
   doc §14.2). Index-space is recommended; not final.
3. **Which REML convention Hector uses** (see decisions above). Needed before the external
   cross-validation can attribute any discrepancy.
4. **`requires-python = ">=3.12,<3.14"` carries an upper cap.** Caps poison downstream
   resolvers; drop before the PyPI stage ever runs.
5. **64-core box RAM is unknown.** Kept open: the stage-1 gate was closed without that
   machine (see the verdict note), but its RAM is still needed before any tile-sizing
   run there.
6. **Roofline validation across machines.** The compute/bandwidth pair is meant to predict
   one machine's result from another's, and **one data point cannot validate a
   two-parameter fit** — the mini PC supplies the model's first point and tests nothing.
   **Blocks the `cloudify` cost projection (design doc §15.5):** projecting spend on an
   unvalidated roofline is projecting a guess. Closed by a second machine's roofline pair
   plus its measured canonical filter pass, checked against the prediction.
7. **Path B at high thread occupancy.** Measured at 1 and 4 threads on a 4-core box only.
   `prange` over series at 64 threads may hit false sharing on the per-series `accum`
   block, or saturate the controller at a different point. Closed by
   `bench/spike.py --threads 1 --threads 4 --threads 64` on the 64-core box.
8. **`numba` and `celerite2` on arm64.** Untested. `celerite2` has **no `osx-arm64`
   conda-forge build** and is pinned to `[target.linux-64.dependencies]`; `numba` on
   `osx-arm64` / `linux-aarch64` has never been run here. Closed by the suite plus
   `bench/spike.py` on the MacBook.
9. **`optimize.HESSIAN_COND_LIMIT = 1e10` is picked, not derived**, while its static
   counterpart in `lint.py` is derived from float64 — so the two halves of §4.8 sit on
   different footings. The eps rule gives `1/√eps = 6.7e7` for a single inversion.
   **BLOCKING for the point where the identifiability machinery is actually used, which is
   the start of Phase 2 — close it before, not at.** `1e10` against `6.7e7` is precisely the
   band in which a near-degenerate fit reports as healthy, so the *a posteriori* half is
   currently more permissive than the *a priori* half by ~150×, and a candidate the lint
   flags can come back `OK`. Changing it moves a reported outcome (`DEGENERATE_HESSIAN`),
   so it needs its own tests, not a drive-by edit. **When it is resolved, re-derive
   `signal.X_RANK_RTOL = 1e-10` in the same pass rather than keeping it** —
   `RANK_DEFICIENT_LOG_LIMIT` is derived *from* it, and a derived constant resting on a
   picked one inherits the arbitrariness it was supposed to remove. See the
   eps-derived-constant sweep above.

---

## Deferred items

Design-level deferrals with their landing conditions are in design doc §19. Nothing is
deferred that is not recorded there. Phase 1 additions:

- Cross-term shared parameters (blocks σ² profiling) — refused with `NotImplementedError`.
- Per-point regressor fields — `signal.DesignInfo` carries the seam.
- Nonlinear signal terms (`ExpDecay`, `LogDecay`) — constructible, raise on use.
