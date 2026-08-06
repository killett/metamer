# metamer — progress

## Start here (cold-start summary)

- **Branch:** `phase-1` (work here, not `main`). Both branches are pushed.
- **Remote:** https://github.com/killett/metamer — public. Run `git log --oneline -5` for the latest commit.
- **Done:** design document, Phase 1 implementation plan, two rounds of plan review applied.
  Phase 1 **Tasks 0–7** are implemented, reviewed, and committed — the likelihood spine now
  runs end to end from a `ProcessSpec` to a scored, per-series result.
- **Pending:** Phase 1 Tasks 8–19.
- **A pre-flight audit of each task brief is now a standing step**, run before dispatching an
  implementer. Every brief audited so far carried at least one defect that verbatim
  transcription would have committed — a test contradicting its own implementation, an
  implementation violating two of its acceptance criteria, an enum property contradicting
  design doc §8.6, a registry never populated at runtime, and two separate catastrophic
  cancellations. It is far cheaper than a fix round and catches what post-hoc review cannot,
  because by then the defect is already the code.
- **Next action:** implement **Task 8** (GLS profiling, ML and REML objectives) from
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
- **Counting is per objective**: ML `k = k_θ + k_β`, `n = n_obs`; REML `k = k_θ`,
  `n = n_obs − rank(X)`. Two definitions on two model classes, not one with an adjustment.
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
