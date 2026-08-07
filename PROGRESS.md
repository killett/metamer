# metamer — progress

## Start here (cold-start summary)

- **Branch:** `phase-1` (work here, not `main`). Both branches are pushed.
- **Remote:** https://github.com/killett/metamer — public. Run `git log --oneline -5` for the latest commit.
- **Done:** design document, Phase 1 implementation plan, two rounds of plan review applied.
  Phase 1 **Tasks 0–12** are implemented, reviewed, and committed — the likelihood spine now
  runs end to end from a `ProcessSpec` to a scored, per-series result, a candidate set can be
  ranked with the comparability guards in force, the objective is differentiable with a
  validated step rule and an adopted gradient oracle, and one family ships verified analytic
  derivatives behind a protocol that refuses an unbacked claim.
- **Pending:** Phase 1 Tasks 13–19. **Task 18 is a user gate — stop there and report.**
- **State at handoff:** Task 12 completed at `6c63451`; **442 tests pass** in ~20 s, `mypy --strict`
  clean, `pre-commit run --all-files` clean, working tree clean, local and `origin/phase-1`
  in sync. Verify with `pixi run test && pixi run typecheck`.
- **A pre-flight audit of each task brief is a required step** before dispatching an
  implementer — see [Required pre-flight](#required-pre-flight-for-every-remaining-task)
  below. Every brief audited so far carried at least one defect that verbatim transcription
  would have committed.
- **Next action:** implement **Task 13** (optimizer driver — initialization ladder,
  convergence, Hessian at optimum) from
  [`docs/superpowers/plans/2026-08-05-metamer-phase1.md`](docs/superpowers/plans/2026-08-05-metamer-phase1.md).
  The draft PR command is below and has not been run yet.
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

- **(a) Absolute vs differential.** Is any quantity entering an absolute log-likelihood
  verified only by a difference? Constants in `θ` cancel in every ΔIC and are invisible to
  every differential test.
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
| 15, 16, 18, 19 | — no calls into changed modules | — | OK |
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

### What Task 13 inherits

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

- **`celerite2` has no `osx-arm64` conda-forge build** (verified 2026-08-04). Coverage is
  split between conda-forge and PyPI with no single source covering every target platform.
  Full table in design doc §15.2.
- **`pixi search` without `--platform` reports an arbitrary subdir.** Always pass
  `--platform`, and use a known-good package (e.g. `numba`) as a control — `rg | head`
  swallows the non-zero exit, so an empty result looks identical to a failed query.
- **`gitleaks` is not on conda-forge.** Install the binary release from GitHub instead.
- **The prompt's `tile_side = sqrt(block_bytes / (n_time · itemsize))` counts only the
  float64 data.** Full accounting gives 343 instead of 445 at a 1 GB budget with a shared
  design matrix, and 187 with per-point regressor fields. Design doc §9.4.
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
- **The suite is no longer fast: ~21 s, up from ~2 s.** `tests/test_gradients.py` runs the
  real `matern32` filter at N = 5000 (373 ms per likelihood evaluation), which exit
  criterion 9 requires. One Romberg tableau plus one central difference at each of three N;
  it is not accidental repetition. **N = 5000 must stay** — it is the only point that
  discriminates the two step rules, which is exactly why the brief's version survived
  review. If the runtime becomes a problem the lever is a `slow` marker so the gradient
  tests can be deselected during rapid iteration and always run in the full sweep; **not**
  `RICHARDSON_LEVELS`, which would trade accuracy headroom for time in the one module whose
  job is accuracy.
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
5. **64-core box RAM is unknown.** Establish it before the Task 18 run.

---

## Deferred items

Design-level deferrals with their landing conditions are in design doc §19. Nothing is
deferred that is not recorded there. Phase 1 additions:

- Cross-term shared parameters (blocks σ² profiling) — refused with `NotImplementedError`.
- Per-point regressor fields — `signal.DesignInfo` carries the seam.
- Nonlinear signal terms (`ExpDecay`, `LogDecay`) — constructible, raise on use.
