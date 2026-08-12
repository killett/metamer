# metamer — progress

## Start here (cold-start summary)

- **Branch:** `main`. **Last commit:** see `git log --oneline -1`; the handoff below was
  written at the commit that completed Task 14.
- **`main` and `phase-1` are reconciled, and they never diverged.** Checked rather than
  assumed on 2026-08-10: `git merge-base --is-ancestor phase-1 main` succeeds and
  `git log main..phase-1` is empty, so `phase-1` held **no** commit that `main` lacked — it
  was simply a stale pointer five commits behind `main`'s publishing work (measured at
  `2372bbb`), left where the 2026-08-07 fast-forward put it. **No merge and no rebase was required, and neither was performed**; `phase-1` was
  fast-forwarded onto `main` so the two names agree, which is not a history rewrite and
  drops nothing. Everything the publishing run added (hatchling + hatch-vcs, `dynamic =
  ["version"]`, the wheel/sdist targets, the CI and release workflows) is on both.
  **All Phase 2 work happens on `main`.**
- **Done:** Phase 1 **Tasks 0–18**. Task 18 (the stage-1 gate) was closed on the mini PC
  alone — see the verdict note for why one machine suffices and in which direction the
  inference runs. **Task 19 deleted.**
- **STARTING PHASE 2? READ**
  [`docs/superpowers/notes/phase1-to-phase2-handoff.md`](docs/superpowers/notes/phase1-to-phase2-handoff.md)
  **FIRST.** It is self-contained and carries the transferable part of Phase 1: the
  eleven pre-flight categories (a)–(k) with their worked instances, the standing rules,
  the `tile_side` of 338 (**171 until P2 fixed the engines on 2026-08-10**), open
  questions 5–8, the fixture facts, and what
  Phase 2 inherits structurally. This file stays the running notebook; that one is the
  method.
- **Exit criteria:** **13 met, 3 met with reduced scope, nothing deferred** — the full
  table with reasons is at the end of the Phase 1 plan.
- **Next: Phase 2 needs an implementation plan.** Phase 1 is COMPLETE (Tasks 0–18; **Task 19
  deleted, not deferred** — path B won by ≥3×, so the batched trust-region has no purpose),
  and the three Phase 2 preliminaries **P0, P1 and P2 are done and pushed** — see the
  Phase 2 preliminaries section below. **Nothing is blocking.** Design doc §17 already
  covers Phase 2's territory, so what it needs is a plan plus a phase list with only the
  first phase detailed, and that first slice vertical as Phase 1's was.
- The stage-1 verdict, its scope, and what it does **not** establish are in
  [`docs/superpowers/notes/spike-stage1-verdict.md`](docs/superpowers/notes/spike-stage1-verdict.md)
  — read it before quoting the ≥3× result. **Its one condition is discharged**: re-measured
  after the engines were made to stream, the worst cell went 3.04 → **3.84**.
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
- **Tests:** **588 collected.** Full sweep `pixi run test` (~280 s). `pixi run test-fast` (~12 s)
  deselects the `slow` marker and is for iteration only — **a green fast run is not evidence
  a task is done.** `pixi run test-ci` reproduces what CI runs (`-m 'not machine'`); it is
  also not evidence on its own, because the `machine` marker covers exactly the tests that
  pin the RSS shim's units and the per-core bandwidth claim, and those need a known machine.
- **Verify a fresh checkout with:** `pixi run test && pixi run typecheck && pixi run lint`
- **Remote:** https://github.com/killett/metamer — public. **`main` is now the working
  branch**: `phase-1` was fast-forwarded into it on 2026-08-07 for the publishing run.
- **The package is now installable and CI runs.** `pyproject.toml` has a `hatchling` +
  `hatch-vcs` build backend, so **the version comes from the git tag and there is no version
  string to edit anywhere.** `.github/workflows/release.yml` publishes to PyPI on a `v*` tag
  via Trusted Publishing. See [`RELEASING.md`](RELEASING.md). Pushes that touch
  `.github/workflows/` need `env -u GH_TOKEN` so the stored `gh` login (which has the
  `workflow` scope) is used instead of the injected `GH_TOKEN` (which does not).
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
| Original build prompt | [`docs/phase1-prompt.md`](docs/phase1-prompt.md) — **superseded** by design doc §2 where they conflict |
| Phase 2 preliminaries pre-flight | [`docs/superpowers/notes/phase2-preliminaries-preflight.md`](docs/superpowers/notes/phase2-preliminaries-preflight.md) — the (a)–(k) audit of the P0/P1/P2 briefs and what each finding changed |

Phase list is design doc §17. Phase 1 exit criteria are §18. Do not duplicate either here.

---

## Phase 2 preliminaries (P0–P4, 2026-08-10)

Five pieces of work that had to land **before** Phase 2 planning. The (a)–(k) pre-flight
on the P0/P1/P2 briefs is in
[`docs/superpowers/notes/phase2-preliminaries-preflight.md`](docs/superpowers/notes/phase2-preliminaries-preflight.md);
only the durable conclusions are here.

### P0 — branches, and the version inside `fit_hash`

- **`main` and `phase-1` never diverged.** See the cold-start summary above. The lesson
  generalizes: **"the branches have diverged" is a claim to measure, not to act on.**
  `git merge-base --is-ancestor` and an empty `main..branch` log answer it in two commands,
  and the wrong answer here would have been a rebase of five published commits.
- **THE PACKAGE VERSION IS NO LONGER PART OF FIT IDENTITY.** `hashing.FIT_RELEVANT_FIELDS`
  carried `metamer_version`. Under `hatch-vcs` that value is derived from the git tag, so an
  untagged commit gives `0.1.1.dev3+g6a0fb3b` — **a new string on every commit** — and the
  uninstalled `PYTHONPATH=src` tree that `pixi run` uses gives the `0.0.0.dev0` sentinel.
  Either would make a finished 10⁷-point store stop resuming and silently refit.
  **The defect was latent, not live**: nothing in `src/` populated the field, so the trigger
  was one obvious line in Phase 2's config builder (`metamer_version=metamer.__version__`),
  which is the reading the field's own name invites.
- **Fit identity is now `hashing.ALGORITHM_VERSION`, a hand-bumped constant**, stamped by
  `normalize` and refused if a config supplies it. The bump rule — "this change moves
  `theta_hat` or `log_lik` for an input that previously fit" — is in its docstring and is
  step 2 of `RELEASING.md`'s checklist. `metamer_version` stays in the config as
  **provenance**, reaching `run_hash` alone. Design doc §13.3 said "metamer version" and has
  been amended; it was right when the version was a literal in `pyproject.toml`.
- **The three `GOLDEN_*` constants moved and were re-derived by hand**, and the derivation
  was verified by reversing it: putting `metamer_version` back and taking
  `algorithm_version` out reproduces `2503613d711d79f7` / `e4bbab19392f45e3` /
  `6299047df1a486bf` exactly, which proves the separators, the sort rule, the digest and the
  truncation are all unchanged and only the field set moved. **Bumping `ALGORITHM_VERSION`
  moves all three again, and that is correct** — regenerate them by hand, never from the
  failure.
- **No other VCS-derived value entered any hashed payload.** The publish flow's entire
  footprint under `src/` is `__init__.py` (the `hatch-vcs` import) and an empty `py.typed`;
  everything else it added is consumed by the build, never by `hashing.normalize`.
  `registry.REGISTRY_VERSION` is a second hand-maintained identity constant and must stay
  one.
- **A hash field the tests supply themselves is invisible to those tests** — pre-flight (a)
  at its purest. Every `test_hashing.py` fixture passed `metamer_version="0.1.0"`, so no
  test could express a defect whose whole mechanism is that the real value is not
  `"0.1.0"`. The new guard therefore varies the version *across processes*, setting
  `metamer.__version__` before `hashing` is imported so the wiring is caught whether it is
  read at import time or at call time, and asserts `run_hash` **does** move so the fixture
  can fail at all. 4/4 mutations caught.

### P1 — the constants around `HESSIAN_COND_LIMIT` (closes open question 9)

Four constants, each with its own derivation stated in its own docstring in the units of
the quantity it thresholds. **They are not one construction with four names**, and three of
them landing on `2^±26` by different routes is a hazard rather than a confirmation.

| constant | was | is | why |
|---|---|---|---|
| `optimize.HESSIAN_COND_LIMIT` | `1e10`, picked | `eps^(-1/2)` = **6.7109e7** | H is inverted **once**, for `H^-1` and `theta_err`; `eps·cond(H) = √eps` |
| `signal.X_RANK_RTOL` | `1e-10`, picked | `eps^(1/2)` = **1.4901e-08** | no consumer uses X directly; they form the Gram, so the ratio is **squared** |
| `objective._NEGATIVE_REDUCTION_RTOL` | `1e-6`, picked | `eps^(1/2)` = **1.4901e-08** | `eps` × the largest `cond(Gram)` reachable before `ILL_CONDITIONED_X` fires |
| `optimize.GRAD_TOL` | `1e-5`, picked | **5e-5**, measured | NOT eps-derivable — see below |

- **`GRAD_TOL` cannot be derived from float64 and is labelled a measured separator.** Its
  floor is set by **scipy's L-BFGS-B stopping rule**, not by the arithmetic: measured at the
  optimum against a nested-Richardson gradient, the finite-difference instrument's own floor
  is ~3e-10 relative to `|loglik|`, and no converged fit comes within four decades of it.
  What it separates is measured, over six fits spanning two compositions and three record
  lengths: **converged 3.46e-07 .. 2.30e-05**, **stopped at one to three iterations
  1.45e-04 .. 1.84e-02**, two populations a factor of 6.3 apart with nothing between them.
  **The old `1e-5` sat BELOW the converged maximum**, so two of the six converged fits would
  have been filed `ITER_CAP_LARGE_GRAD` had they hit the cap — the clamp rule pointed the
  other way: a guard *below* the diagnostic limit of what it guards makes the milder outcome
  under-reachable. Both bounds are now pinned by a test that fails against `1e-5` and
  against `5e-4`.
- **THE HANDOFF'S ATTRIBUTION WAS WRONG AND IT MATTERED.**
  `objective.RANK_DEFICIENT_LOG_LIMIT` is derived from `engines.kalman._RANK_RTOL` (the
  **Gram** cutoff), not from `signal.X_RANK_RTOL`. Different modules, different matrices,
  same numeral `1e-10` — which is the whole mechanism of the misreading. Re-deriving
  `X_RANK_RTOL` alone would have left the derived constant resting on the other one.
- **`kalman._RANK_RTOL` stays at `1e-10`, and that is the "measure or document" branch of
  the rule, not the "picked" branch.** Its docstring carries a measured calibration table
  and a two-sided window: an exactly deficient design puts its null singular value at 0 or
  ~5e-17 of the leading one, while a Gram accumulated at `cond(X_w) = 1e8` has already lost
  its small singular value into float64 noise, so anything below ~1e-16 reads rounding.
- **FOUR FIXTURES MOVED. NONE WAS HEALTHY.**

  | fixture | what changed | verdict |
  |---|---|---|
  | `test_fit.py::_plain_batch` (2 tests) | one series went `OK` → `DEGENERATE_HESSIAN` at `cond(H) = 1.194e+08` | **the fixture was wrong.** It was pure white noise fitted with white + Matérn 1/2 — open question 9's own defect, in the fixture that was never fixed. Its sibling row, same generator and seed stream, sat at `cond(H) = 1.447e+03`. Now drawn from the composite's own covariance, as `_healthy_row` already was |
  | `test_signal.py::test_decimal_years_vs_seconds_since_1970` | seconds-axis rank 2 → **1** | **the constant was wrong.** The ratio that decides it is `8.182e-09`: clears `1e-10`, does not clear `√eps`, and is `6.7e-17` once squared — a numerically dead direction the old value called alive |
  | `test_signal.py::test_gram_logdet_accurate_at_cond_1e9` | rank 4 → **3**, deficient | **the constant was wrong.** `(1e-9)² = 1e-18` is below `eps`; the test's own docstring already called that Gram "deep in float64's ~1e16 precision-loss regime" |

- **A knock-on the constants did not cause but the fixture did.**
  `test_bic_neff_and_bic_disagree_end_to_end` compared the correlated candidate's ΔIC
  across criteria. On genuinely correlated data that candidate **wins** some series, and a
  winner's ΔIC is 0 under both criteria by definition, so the comparison asserted `0 < 0`.
  The winner mask is now explicit and the reason is in the test. **Generalize: a fixture
  made honest can invalidate an assertion that was only true because the fixture was
  dishonest.**
- **Every one of the four constants now has an absolute pin**, hand-worked as a power of two
  rather than by restating the module's own expression. Without it the whole family is
  invisible to its own tests: every rank, outcome and tolerance assertion compares a fixture
  against the constant, so both sides move together. That is the cancellation rule applied
  to a threshold.

### P2 — both engines stream, and `tile_side` is 338

- **PATH B WAS THE SECOND SITE OF THE SAME DEFECT AND NOTHING SAID SO.** Every note
  described `_augment` as the reference engine's problem. `CompiledEngine.score` called
  `np.ascontiguousarray(reference._augment(...))`, so **the adopted production path carried
  the same `(B, N, 1+k_β)` block plus a copy**. One `rg _augment src/` returns two call
  sites. Fixing path A alone would have published a `tile_side` no production run could
  honour, per backend, with a test pinning it.
- **`_augment` is replaced by `_design_block`**, which validates the design and returns it
  as a `(1, N, k)` **view** when shared or `(B, N, k)` when per point, copying nothing. Both
  engines read the observation out of `y` and the design columns out of that block per
  timestep — path A into one reused `(B, 1+k)` row, path B element by element.
- **`tile_side` is 338**, resident 8722 B/series against §9.4's 8682 B model, a 0.5% gap
  where it was a factor of 3.9. **Budget against `resident_bytes_per_series` regardless**;
  the gap being small is a measurement, not a guarantee.
- **Measured, not inferred.** Slope of resident RSS against B in a fresh process, sampled on
  a thread during the workload: **43 392 → 8471 B/series**, against an arithmetic floor that
  went 31 542 → 6382. Ratio to floor **1.38 → 1.33**, both inside the ~1.5× the standing
  check allows. **The fall of 34 921 B/series is larger than the 25 200 B block itself**,
  because the per-step temporaries at peak scaled with it — a term neither formula names.
  **Note what this says about the standing check:** it would never have caught the original
  defect, because the old formula described the code correctly and it was the *design* it
  disagreed with. Reading the source is what caught it.
- **BIT-IDENTICAL, not within tolerance.** The pre-fix modules were loaded straight out of
  git (`git show 29884aa:...` into a temp file, never checked out) and compared field by
  field: both engines × {shared, per-point, no design} × {`loglik`, `normal_equations`,
  `rank_x`, `outcome`, `n_used`}, on a gapped mask — thirty comparisons, all exact.
  **The path-B agreement test could not have carried this** and it is worth knowing why:
  it compares two implementations of the same recursion, and *both* were changed, so
  anything they do identically is invisible to it. The cancellation rule at the level of an
  engine.
- **THE SPIKE'S CONDITION IS DISCHARGED. The falsifier is not met in any cell or any
  harness**: the lowest A:B measured after the fix is **3.27**, and at the new
  production-scale B = 114 244 it is **4.05**. Task 19 stays deleted.
- **THE TWO HARNESSES DISAGREE ABOUT WHETHER THE RATIO MOVED, AND THAT IS THE FINDING.** At
  d=3, one thread, no gaps, B=1000 the spike says 3.04 → **3.84** and the batch sweep says
  3.31 → **3.27**. A 0.57 spread on one quantity, against the **±0.15** run-to-run scatter
  the verdict assumed — so **±0.15 understates the variation on this machine, and any
  restatement of the margin must name its harness as well as its B and thread count.**
  Absolute per-pass seconds per series separate what is resolved from what is not:
  **path B's gain is consistent — −19% (spike) and −22% (sweep)** — while **path A did not
  measurably move**: +1% by one harness, −22% by the other, and the two disagreed by **27%**
  on that identical quantity *before* the fix. The verdict's stated reasoning (path A is
  memory-bound, so path A gains most, by more than path B) is therefore **wrong on the half
  that is resolved**. The mechanism it missed: path B had been reading a **per-series
  private copy of the shared design** — B copies of the same `(N, k)` bytes competing for
  cache, a locality problem in the per-series loop — while path A's cost is the
  `(B, d, n_cols)` einsum temporaries it rebuilds every timestep, which the block never
  touched.
- **The fix moved the goalposts of its own re-measurement.** Production-scale B is tile side
  squared, so it went ~29 000 → **~114 000**. The verdict's falsifier is stated "at
  production-scale B" and its sweep topped out at 20 000, which was close to 29 000 and is
  not close to 114 000.
- **A P1 constant changed a P2 benchmark input, and the two are easy to conflate.**
  `mean_iterations` at d=3 went 68.7 → 90.0 and path A's utilization 0.64 → 0.84. Neither is
  a P2 effect: both are computed over the **OK series only** in a four-series sample, and
  the derived `HESSIAN_COND_LIMIT` moved one of the four to `DEGENERATE_HESSIAN`. **The A:B
  ratio is untouched** — the iteration count is common to both paths and cancels — but the
  per-fit millisecond columns carry the new count. See open question 11.

### P3 — the spike's iteration sample (closes open question 11)

Full record under open question 11. The three things that carry:

- **A fixture whose data does not come from the model being fitted produces fits that are
  not representative of the workload, and every statistic conditioned on `OK` inherits
  that.** Third instance of one defect (`_healthy_row`, `_plain_batch`, the spike). In all
  three the *verdicts* were correct and it was the *sample being averaged over* that
  silently narrowed — 4 → 2 series at d=3 here.
- **The amplitude spread was never heterogeneity, and the fixture's docstring claimed it
  was.** The Gaussian log-likelihood is scale-equivariant, so one realization at four
  amplitudes gives `n_iter = [28, 28, 28, 28]` and utilization **exactly 1.0** — the number
  the docstring said the spread existed to challenge. Rows now vary by generating
  parameters.
- `mean_iterations` at d=3 went **90.0 → 32.5** and utilization **0.84 → 0.637**; at d=1,
  43.3 → 13.0 and 0.66 → 0.929. **Every `ms/fit` column rescales; no A:B ratio moves.**
  Path B at production B = 114 244 goes **19.5 → 7.1 ms** against the 19 ms budget.

### P4 — the two benchmark harnesses, reconciled

- **THERE WAS NO HARNESS EFFECT. THE 0.57 DISAGREEMENT IS INSIDE ONE HARNESS'S OWN
  SCATTER, AND THE ±0.15 IN THE VERDICT WAS AN ASSUMPTION DRAWN FROM A SAMPLE OF TWO.**
  Measured at d=3, one thread, no gaps, B=1000, twenty-nine measurements in four
  conditions:

  | condition | A:B range | spread |
  |---|---|---|
  | eight rounds in one process, **same arrays** | 3.34 .. 3.47 | 0.13 |
  | eight rounds in one process, **fresh arrays each round** | 3.63 .. 4.08 | 0.45 |
  | eight **fresh processes**, that cell only | 3.18 .. 4.00 | 0.82 |
  | five **fresh processes**, the full sweep each | 3.07 .. 3.78 | 0.71 |

  Both published numbers (3.84, 3.27) sit inside that. The full-sweep and single-cell
  medians are 0.18 apart against a within-condition spread of 0.7–0.8, so process context
  is not the cause either.
- **THE SCATTER IS BETWEEN ALLOCATIONS, WHICH IS THE ONE PLACE `repeats` CANNOT LOOK.**
  `_time_pass` takes the best of `repeats` back-to-back passes over **one** allocation —
  the tight 0.13 row — and publishes it as if it were the last row. Re-allocating also
  moves the level: **path A is ~16% slower on fresh inputs, path B ~4%**, and the
  reallocating run was taken at a *lower* load average, so machine load is not the
  explanation and points the wrong way. **Generalize: a repeat that reuses the fixture
  measures the fixture's placement once.** If the production condition allocates, the
  benchmark must allocate inside the repeat.
- **The harnesses are now one.** `--dim` and `--gaps` are filters on `run_spike`, so the
  batch sweep is `--dim 3 --gaps none --threads 1 --batch ...` rather than a second script.
  Two entry points into one measurement is what let "which harness" become a variable.
  `--cell-repeats` (default 3) runs independent rounds on fresh allocations and the report
  carries the **median with its min and max** for both pass costs and the ratio.
- **Any restated margin must name its harness invocation, B, thread count AND cell-repeat
  count**, and should be quoted as a range. The falsifier is unaffected: it is stated
  against the lowest measurement, and the lowest anywhere is **3.07**, still clearing 3×.
- **The restated margin**, `bench/minipc-unified-d3-nogaps-1thread.json`, d=3, one thread,
  no gaps, `--repeats 3 --cell-repeats 3`, median of three rounds on fresh allocations:

  | B | A:B median [min, max] | path A bound ms/fit | path B ms/fit |
  |---|---|---|---|
  | 1 000 | 3.86 [3.70, 4.01] | 21.5 | 5.42 |
  | 20 000 | 3.80 [3.43, 4.00] | 22.4 | 6.32 |
  | **114 244** | **4.33 [4.25, 4.39]** | **25.8** | **5.88** |

  Path B is inside the 19 ms budget by **3.2×** at production B. Path A's optimistic bound
  is 1.36× over, and 2.1× over at the measured utilization of 0.637. **Three rounds report
  a range, they do not bound one** — the eight-round study is the figure to quote for
  scatter, this table for level.
- **A CORRECT CONCLUSION REACHED THROUGH A WRONG MECHANISM IS A FINDING IN ITS OWN RIGHT.**
  The verdict predicted the `_augment` fix would help path A most; measured, path B gained
  ~20% and path A did not move. The conclusion (path B wins) survived; the reasoning (path
  A is memory-bound, so it gains from any traffic reduction) did not — and **the reasoning
  is what the next prediction is built on.** A verdict that records only outcomes gives a
  later reader no way to know its mechanism failed. One clause of it is now independently
  supported: path A is ~4× more sensitive to memory placement than path B, so "path A is
  the memory-sensitive path" stands and "therefore this block helps path A most" never
  followed from it. The design doc's "why one machine is enough" argument rests on that
  clause and is left standing by P4 — but on the reallocation measurement, not on the
  prediction that failed.

---

## Phase 2 brainstorm — settled decisions (in progress, 2026-08-11)

**Live record, appended as each question is settled.** It migrates into the Phase 2
implementation plan when that exists, and is deleted from here at that point — migrate,
do not duplicate. Design-doc amendments made along the way are noted with their section.

### Q1 — the entry point and the config path

`python -m metamer <config.toml> <store>`. **Design doc §17 amended** with the Phase 2 /
Phase 5 split table; §17 previously assigned "the CLI" wholesale to Phase 5, which read as
though Phase 2 needed no config, and **a resume gate is a comparison of hashes with
nothing to hash until a config is loaded and normalized.**

- **The Python API is the unit of implementation and testing** —
  `metamer.batch.run(config, store_path)`. Everything is tested against it directly.
- **Config always comes from disk through the real path.** `metamer.config.load(path)`
  going through `tomllib` → pydantic → `normalize` → canonical JSON → the three hashes. **No
  production path constructs a `Config` inline.** Tests may build one for unit purposes;
  every integration test and every exit criterion loads from a real TOML file, because a
  `compat_hash`-only difference proves nothing unless it survived the actual normalizer.
- **`python -m`, not `metamer run <config>` via `console_scripts`.** Naming a subcommand
  presupposes the tree it belongs to and designs the argument structure now rather than in
  Phase 5 when `validate` and `report` are real. `python -m` presupposes nothing and reads
  as provisional. argparse, one screen, no typer, no rich; flags limited to
  `--memory-budget` and whatever exit criterion 7 needs.
- **All five exit codes land now**, as an enum and a return value, because retrofitting
  them means revisiting every early return — the argument that made the failure taxonomy a
  Phase 1 deliverable. Sub-phase 1 produces a subset; each of the rest gets a constructed
  test or an explicit note that it is unreachable until its producer exists.
- **Codes 3 and 4 cannot be distinguished without validation staging**, so the 1/2/3/4
  split exists in sub-phase 1 even where layer 3 holds only the two or three checks
  sub-phase 1 can trigger. **The staging is the structure; the checks accrete.**

### Q2 — store width in sub-phase 1

**M = 2 with unequal `p`, C = 2, every group written except `/detail/`.** The reasoning is
the length-1 axis entry under the fixture facts below: `M = 1` and `C = 1` are the widths
at which every array under test is constant across its own comparison axis.

- Candidates: `white` (p=1) and `white + matern12` (p=3) — unequal `p` is the load-bearing
  half, giving `off_1 = 1` and `P_total = 4`.
- Groups written: `/signal/`, `/primitives/` (including `iterations` uint16),
  `/selection/`, `/noise/`, `/status/`, `/warmstart/`, `/completion/`.
- **`/detail/` is not created.** An uncreated group is a cleaner deferral than an empty
  one, and its selection rule is still open.
- **One point must have candidate 1 failing and candidate 2 succeeding**, as a *required*
  property of the fixture and not an incidental one. Phase 1's offset-inside-a-gap
  construction gives it: a breakpoint with no support for one candidate's design and full
  support for the other's. That point has `n_valid = 1` and a weight vector renormalized
  over one survivor — **the case that reads as confident selection and is not.**
- **`/warmstart/` is written but unread in sub-phase 1, and therefore needs its own
  guard**: nothing else will notice if it is written wrong. Assert a round trip — the
  stored unconstrained `θ̂` reloads and maps back through the Bijector to the natural
  parameters in `/noise/` — so 2c inherits a verified array instead of discovering the
  layout is wrong underneath a feature that has its own bugs.

### §12.8 narrowed, and the allowlist finding

**Design doc §12.8 amended.** A `compat_hash` mismatch licenses recomputing derived arrays
from stored primitives; it does **not** license resizing an axis in place. Adding a
criterion is refused, with a message naming the stored set, the requested set, and the two
resolutions. Reasons, in full, are in §12.8: a resize is a whole-store rewrite with no
completion bitmap of its own; recomputing into a new store is arithmetic and avoids the
refit either way; and an in-place resize is the one operation that breaks "every write is a
region write into a fixed geometry".

**Measured against the code, not assumed:**
`hashing.COMPAT_RELEVANT_FIELDS == FIT_RELEVANT_FIELDS | {"criteria"}` — **the two sets
differ by exactly one field.** So every constructible compat-only mismatch is a
criterion-set change, every criterion-set change is now refused, and **§12.8's middle row
has no reachable in-place input.** The split is not vacuous (`criteria` is the field §13.3
exists to separate) but the partition is two-way plus one field, and the recompute path
must be exercised **into a new store**. Inventing a config field to make the test
constructible would be backwards.

**Confirmed against the golden test's own hardcoded set** (`tests/test_hashing.py:606–626`),
not against the module: `FIT_RELEVANT_FIELDS` is eight fields and `criteria` is the only
addition. **One adjacent fact falls out of the same assertion:** `candidates` is asserted
*not* compat-relevant, so **the candidate set is a store property no hash covers.** §12.8's
superset rule assumes it is compared and no hash enforces that — the resume gate must
compare it explicitly against the per-candidate spec hashes in root attrs.

### Q3 — the recompute path lands in sub-phase 1

`python -m metamer <config.toml> <new-store> --reuse-fits-from <old-store>`. A flag on the
one runner: read `/primitives/` for a tile, call `rank_candidates`, region-write
`/selection/`, set the completion bit. **Same tiling loop, same write path, same bitmap,
same resume semantics** — the fit step is replaced by a read.

Decided on three arguments, the second decisive:

1. **A refusal naming a command that does not exist is a defect committed on purpose**, and
   it survives, because nobody grep-audits error strings.
2. **The three-hash split has been carried since Task 16 on containment tests and an
   in-memory contract.** Deferring the recompute path leaves it untested through Phase 2's
   largest sub-phase, and the recompute path is where `fit_hash` either does what it claims
   or does not.
3. Cost is one flag and one branch — the least important argument, because **a cheap thing
   that is never exercised is not cheap.**

`--reuse-fits-from` over `--recompute`: it names a **source**, a fact about the invocation,
rather than an **operation**, which presupposes a verb the command tree has not chosen.
Same reasoning as `python -m` over a subcommand.

**Exit criterion 5 splits three ways, all constructible at C=2:**

- **5a** — recompute into a new store with a different criterion set: `/primitives/`,
  `/noise/`, `/signal/`, `/status/` byte-identical to the source, `/selection/` differs,
  **and no fit ran**, asserted by a stub engine that raises if called, never by timing.
- **5b** — an in-place resume with a changed criterion set is refused, both sets named.
- **5c** — a `fit_hash` mismatch is refused.

**Four requirements on the path:**

1. **The raising stub engine goes in the shared fixtures, not in one test module.** Timing
   cannot falsify "no fit ran"; a raising stub proves it. The same construction proves the
   negative in at least two other places — that a resumed tile did not refit completed
   work, and that a compat-only rewrite touched nothing upstream of `/selection/`.
2. **The recompute path writes its own provenance and does not inherit the source's.** New
   `run_hash`, new `compat_hash`, `fit_hash` **equal to the source's** — and that equality
   is the entire claim. Record the source store's path and all three of its hashes as
   provenance fields, so a reader can verify the claim instead of trusting the label and a
   test can assert `fit_hash` equality across the two stores directly. That assertion is
   the cleanest available statement of what the split bought.
3. **Verify the source BEFORE the tiling loop, not after.** Check `schema_version`,
   `fit_hash` against the requested config, and that the source's **completion bitmap is
   fully set**. Recomputing from a partially fitted store yields a complete-looking new
   store built on incomplete primitives — a plausible-number failure with no symptom. An
   incomplete source is a layer-4 validation error, **exit code 4**.
4. **Status does not simply copy — and it does not go through the ladder either.**
   Fit-stage outcomes transfer unchanged. Recompute-stage failures are criterion-specific
   and **`outcome[y,x,m]` has no `c` axis**, so folding them into the precedence ladder
   would make a criterion-independent array depend on the criterion requested. They live in
   `/selection/`: NaN ΔIC excluded from normalization, `-1` in `selected[y,x,c]`. **Design
   doc §12.5 amended** with the scoped invariant and the two routes to the fit-OK /
   criterion-undefined test point.

**Consequence for the C=2 choice: the pair is AIC and HQIC, not AIC and BIC.** HQIC has the
wider reachable undefined region (`n ≤ 2` against BIC's `n ≤ 1`), so the criterion axis
carries a real asymmetry rather than two criteria that agree everywhere.

**Store invariant added to design doc §12.4: every store is self-contained.** No store
resolves through another — not by zarr reference, symlink, or a path in attrs a reader must
follow. Provenance records a source store's hashes; it never depends on that store being
present. The recompute path therefore **copies** the groups it does not recompute.

**The fit-OK / criterion-undefined test point takes the REML route**, and the test says why
the other cannot work: under ML `n = n_obs`, so with the four-column design the precheck
refuses the series before scoring and the point is unreachable. **A test that documents
which route works AND why the other cannot is worth more than one that silently picks the
survivor.**

### THE CANDIDATE SET IS COVERED BY NO HASH — a sub-phase 1 requirement, not an open question

**The larger finding of Q3, and the same shape as `metamer_version` sitting in
`FIT_RELEVANT_FIELDS` with nothing populating it: a gate that reads as present and is not.**
§12.8's superset rule was enforced by nothing. Nothing stopped a resume with a *different*
candidate at index 1 from writing candidate B's fits into candidate A's slice of the model
axis — every array the right shape, every value finite, every status `ok`, and the store
wrong in a way no invariant catches.

- **The resume gate compares candidate spec hashes positionally** against root attrs:
  `stored[i] == requested[i]` for every `i < len(stored)`, and
  `len(requested) >= len(stored)`. A mismatch at any position is refused, naming the index
  and both hashes.
- **Deliberately NOT folded into `compat_hash`**, because a superset must be permitted and
  **a hash can only express equality**. Recorded in `hashing.FIT_RELEVANT_FIELDS`'s own
  docstring so a later reader does not "fix" the omission by adding `candidates` to the
  allowlist and thereby forbid the extension workflow.
- **The wrong-candidate-at-index-1 case is a required test.** It interacts with the M=2
  unequal-`p` choice usefully: swapping `white` (p=1) with `white + matern12` (p=3) shifts
  every offset on the ragged axis too, so the failure shows up in two arrays rather than one.

### Q4 — input adapters and the time-axis contract

**Design doc §13.6 added, and §13.2 layer 4 gains stage 4a.**

- **A declared opener set through a named registry**, chosen from the `data_uri` scheme.
  **zarr only in sub-phase 1**; netCDF is a registration, not a refactor. Two openers do not
  test the tiling loop twice, they test xarray twice. **The contract is on dataset shape,
  not file format.**
- **metamer converts to decimal years; the user never supplies them.** An interface that
  asks for decimal years invites the most catastrophic input error in the system, and Phase
  1 measured its consequence: `cond(X)` 3.4e1 → 3.3e32, rank 7/7 → 2/7, `cos(annual)`
  identically 1.0 — a full-rank-looking design that has lost five columns without a crash.
  **An interface that cannot be used wrongly beats a validator that catches it.**
- **Never infer units from magnitude.** Days since 1970 over 50 years is ~2e4 and years
  since 0 is ~2e3 — ambiguous on exactly the axis it most needs to disambiguate. CF-decodable
  datetime64, or an explicit declaration; a bare numeric axis with neither is refused.
- **The conversion rule is `ALGORITHM_VERSION`, and its inputs are fit identity too.** The
  calendar is the sharp one: `proleptic_gregorian`, `noleap` and `360_day` give **different
  decimal years for the same timestamp**, so the calendar reaches the hashed payload and not
  only the attrs. Provenance also records the source units string and the epoch.
- **Stage 4a is layer 4's first stage, deliberately not a fifth layer** — otherwise it
  becomes one by accident when pass 1 lands and layer 4 acquires its "runs against pass 1"
  home.
- **Strictly increasing, not monotonic.** The strict form catches a duplicate as well as a
  reversal, and a duplicate gives `Δt = 0` — an identity transition with a zero
  process-noise covariance, singular, surfacing deep inside the filter rather than at the
  boundary. Same check catches a single-sample axis.
- **A non-uniform axis is legal and its unique-Δt count is reported**, by stage 4a and by
  `--explain`. A nearly-regular axis carrying float noise otherwise yields thousands of
  unique Δt and an order-of-magnitude slowdown with nothing saying why.

### Q5 — `data_geometry_fingerprint` replaces `data_uri` in `fit_hash`

**Design doc §13.3 amended; §13.4 gains a degraded mode; §13.7 added.** `data_uri` is
demoted to provenance in `run_hash`.

**The gate was wrong in both directions at once**, which is not a conservative approximation
of the right gate — it is unrelated to it. Moving a file invalidated a resume that is
scientifically valid; editing a file in place at a fixed URI permitted a resume that is
scientifically invalid. **The fingerprint is the first actual implementation of the check.**

Six constraints, all in §13.3:

1. **Named for what it covers** — geometry, not data. It does not hash the payload array
   (~25 GB at 10⁷×630 float32), so it catches regridding, re-chunking, axis edits and a
   dtype change, and **not** a value edit at fixed geometry. **A test asserting a value edit
   does NOT move it makes the limit executable**, which is the only documentation this
   project has evidence for.
2. **Hash the coordinate VALUES**, through `canonical_json` so float formatting is canonical
   and the result is not platform-dependent — pre-flight (k). Min/max/length collapses an
   extent-preserving regrid.
3. **Fingerprint the DECODED calendar, not the attrs string**, or the fingerprint inherits
   xarray's and cftime's parsing behaviour and an upgrade silently invalidates every store.
   Units, calendar and epoch strings ride alongside as provenance.
4. **Source dtype is in it.** The variable *name* needs nothing added — **`variable` is
   already a separate fit-relevant field**, which is half of this point already satisfied.
5. **A mismatch is its own message, not "`fit_hash` mismatch"** — name the differing
   component (shape, time coordinate, spatial coordinate, calendar, dtype). Same reasoning
   as staged validation naming its layer.
6. **Root attrs carry the components as well as the rollup**, so a mismatch is diagnosable
   from the store alone, which is what makes 5 implementable on the resume side.

**§13.4: unreachable data is a degraded mode, not an error.** `--explain`'s most valuable
use is a config with no data yet — sizing a run before staging 25 GB. It prints
compat- and run-relevant content always and prints `fit_hash: not computed (…requires stage
4a)` otherwise.

**§13.7, the entry contract — the ordering is the guard.**
`open → input contract (4a) → geometry fingerprint → fit_hash → resume gate (hashes, then
the positional candidate comparison) → tiling`. A later change computing a hash before the
contract check would compute it from the config alone, which is where `data_uri`-as-proxy
came from. **Test the order, do not trust it.**

**Plan task:** this is an allowlist change — deliberate by that docstring's own words — and
it moves all three `GOLDEN_*` constants. Re-derive them **by hand** from the declared inputs
and verify by reversal (put `data_uri` back, take the fingerprint out, reproduce the current
constants exactly), as P0 did. Never regenerate them from the failure.

### Q6 — the thread budget, and no dask in sub-phase 1

**Design doc §11.1 corrected, §11.1.1 added, §11.3's preconditions rewritten.**

- **§11.1's "peak RAM is one tile plus one dask chunk" was true at `W = 1` and false
  otherwise**, and if `W` tracks core count then peak RAM tracks core count — the identical
  failure the across-tile ban exists to prevent, arriving through the assembly door. **The
  general form now sits beside it, and it is stronger than the ban, which is one instance
  of it:**

  > **Peak RAM must be derivable from the memory budget alone.** Any concurrency whose
  > degree is set by core count, thread count or worker count reintroduces the dependency,
  > **regardless of which subsystem hosts it.** Concurrency degree is derived from a byte
  > budget; only the budget is a knob.

- **One owner at a time, never both.** Assemble and fit never overlap, so neither reasons
  about the other's threads. **The cost is recorded as a decision, not assumed:** each phase
  idles the other's resource, and at ~5.4 s per series against a tile read of order seconds
  fit dominates by orders of magnitude, so the idle I/O is free. **Record the ratio** — if it
  inverts (cheaper model, slower store, object storage over a network) the decision needs
  revisiting and nothing else would show it.
- **Prefetching tile `N+1` during tile `N`'s fit is deferred with its cost named: it doubles
  the tile term in the memory formula.** It arrives with a formula update or not at all.
- **No dask in sub-phase 1** — `ds[var].isel(y=…, x=…).load()` against zarr. **Dask's value
  here is unproven and its cost is certain**: it buys graph scheduling of awkward chunk
  geometries, and costs a second concurrency system whose interaction with `prange` is the
  open question, plus a graph-chunk guard bounding a thing you would not otherwise have.
  **Removing it deletes the problem rather than deferring it.** And `.load()`'s peak is
  analytic where a graph's is emergent — which matters because the calibration tile is the
  mechanism that turns the memory formula from a model into a measurement.
- **`--explain` reports read amplification (bytes read / bytes used)**, since zarr reads
  whole chunks and a tile straddling chunk boundaries silently reads several times what it
  needs. **This replaces the graph-chunk cap as the guard against a pathological input**, and
  tile geometry should align with input chunk geometry where possible.
- **The determinism precondition is OBSERVED, not requested.** `OMP_NUM_THREADS=1` in
  provenance records a *request*, and whether it took effect depends on import ordering that
  nothing enforces — set after numpy is imported it does nothing, silently. That is
  name-is-not-a-gate at its sharpest. **`threadpoolctl` reports the observed limit per loaded
  library**; record every one it finds (OpenBLAS, MKL, OpenMP, numba's layer), because **a
  precondition that holds for OpenBLAS while MKL runs multithreaded is not a precondition
  that holds.** Observed ≠ requested is a **layer-3 validation failure**, not a note.
- **Thread counts reach `run_hash` only.** If they moved `fit_hash` the hash boundary would
  be conceding the determinism guarantee does not hold. **The guarantee and the hash boundary
  are the same claim stated twice**, and they must not drift apart.

### Q7 — per-point regressors: defer the feature, declare the regime

**Handoff pre-flight gains (a3).** The store schema does not change — `beta[y,x,m,b]` is
shape-identical under either regime — so the *feature* is out of sub-phase 1 by the brief's
own expensive-after-data-exists criterion. The *regime* is not, because the memory formula
and the calibration tile both behave differently under it.

**Measured rather than quoted** (d=3, k_β=4, p=4, N=630, M=12, 1 GB budget):

| regime | resident B/series | `tile_side` | production B |
|---|---|---|---|
| shared X | 8 722 | **338** | 114 244 |
| per-point X | 28 882 | **186** | 34 596 |

**One config field moves the tile by 3.3× in area**, which is the whole argument.

- **The layer-3 refusal names the field AND the consequence.** Layer 3 knows both tile
  sizes; a message saying "not implemented" wastes context the user needs for planning.
- **`--explain` prints both regimes' numbers when the config declares per-point**, with the
  refusal noted. The formula already branches, so it costs nothing, and it is the planning
  value the regime is being kept for.
- **The formula's per-point branch is tested NOW**, against a directly constructed
  `per_point=True` `DesignInfo` rather than through the config path — otherwise it is
  untested live code inside the mechanism sub-phase 1 exists to establish, and the first
  person to enable the feature discovers the formula was wrong all along. **That test is
  also what makes the table above durable**: those numbers belong in an assertion, not in a
  session report.
- **THE REGIME LIVES INSIDE `signal_terms`, and that is the whole of the calibration-cache
  answer.** `signal_terms` is already in `FIT_RELEVANT_FIELDS`, and a per-point regressor
  changes the design matrix and therefore `θ̂` and `log_lik`, so it is genuinely fit-relevant.
  The calibration cache — keyed on `fit_hash` + backend + machine fingerprint — then
  invalidates on a regime change **by construction**. A sibling field (`regressor_fields`)
  would have left the key naming `fit_hash` while `fit_hash` said nothing about the regime,
  and a cached shared-X measurement reused for a per-point run understates peak by 3.3×
  against a hard 16 GB constraint. **Name-is-not-a-gate, avoided by construction rather than
  by a check.**
- **Consequence for Q5 that Q5 did not cover: the geometry fingerprint covers EVERY input
  array, not only the primary variable.** A per-point regressor is a second data source with
  its own grid, and a GIA field silently regridded under a fixed URI is the same hole one
  level out.

### Q9 — nearest valid coarse point, and warm-start settings are fit identity

**Design doc §11.1 and §11.3 amended; §13.3 gains the consolidated allowlist finding;
`hashing.FIT_RELEVANT_FIELDS`'s docstring gains the positive rule.**

**Nearest valid coarse point**, index space, ties broken lowest `y` then lowest `x`, spiral
outward until a coarse point with an `OK` fit **for that candidate**. Fine→coarse is index
arithmetic on **dataset** coordinates, so it survives a memory-budget change.

**THE DECISIVE ARGUMENT IS §4.5's EXCHANGEABILITY AND IT IS NOT OBVIOUS** — recorded in full
in §11.3 because someone reading only the practical arguments concludes bilinear is a strict
improvement:

> Neighbouring coarse points can converge to **different mirror images of the same optimum**.
> Bilinear then averages parameter vectors **not in a common labelling**, and the average of
> two mirror images is a point between them that is **neither**, near the saddle separating
> them. So bilinear is **worse than either corner**, and it degrades precisely where the
> likelihood is flat — where warm-starting is supposed to help and where §11.2 says
> hysteresis concentrates. Nearest-valid is immune: one source point supplies the whole `θ̂`.

Practical arguments agreeing: a bilinear stencil with 1–3 failed corners needs a
renormalization indexed by **which** corner failed, so the rule becomes a family of rules;
and a stencil straddling a coastline initializes an ocean point partly from land, **wrong
scientifically before it is wrong numerically**.

- **The spiral is bounded and exhaustion is reported.** Cap the radius; on exhaustion fall
  back to the moment-init ladder **with the rung recorded**, so "no warm start here" is a
  reported fact rather than an invisible degradation, reusing §8.4's existing reporting.
- **Record the source coarse index per point**, at least across the audit subsample —
  otherwise diagnosing an audit disagreement means re-running the spiral. It makes the audit
  **diagnosable** rather than only measurable.
- **No config flag selects the rule**: it changes `θ̂`, so it is fit identity, so a flag
  would fragment stores.

**WARM-START SETTINGS ARE FIT-RELEVANT — the fourth allowlist finding.** §11.1's own words
settle it: a stale warm-start cache produces converged-looking fits at the wrong optimum,
*the worst failure mode in the system*. **The boundary matters**, because read loosely it
sweeps in the audit settings and then re-running an audit at a different subsample size
invalidates the store it is auditing:

| fit-relevant (moves `θ̂`) | not fit-relevant |
|---|---|
| warm start enabled/disabled | audit subsample size and stratification |
| coarse stride | whether the audit ran at all |
| interpolation rule (fixed, but hashed so a second rule cannot silently share a store) | |
| spiral bound and tie-break order | |

**Two things to verify rather than assume:** that changing the **coarse stride** moves
`fit_hash` and the warm-start cache — keyed `(fit_hash, candidate spec_hash)` — therefore
refuses the stale entry; and the three `GOLDEN_*` constants, **re-derived by hand and
verified by reversal**.

**FOUR ALLOWLIST FINDINGS FROM FOUR QUESTIONS, ONE CAUSE.** `FIT_RELEVANT_FIELDS` was
assembled at Task 16 **before the mechanisms that populate it existed**, so membership
tracked what was known then rather than what determines `θ̂`: `metamer_version` (present,
unpopulated), `candidates` (absent and unaddable — a hash expresses equality, a superset
must be permitted), `data_uri` (a location, wrong in both directions), warm-start settings
(absent, and they can move `θ̂` to a different optimum). **The positive rule now lives in the
docstring:**

> **A field is fit-relevant if changing it can move `θ̂` or `log_lik` for any input.** The
> test for a new field is that question, **not precedent.**

### Q8 — screening, and `NOT_ATTEMPTED` meaning two things

**Design doc §8.6, §11.1, §12.5 and §14.1 amended.** The screening *feature* is deferred
(no Whittle engine; §17 places it in Phase 4) and its *regime* is declared per (a3): the
config block is validated and **refused at layer 3 naming the missing engine specifically**
— "screening requires the debiased Whittle engine (Phase 4)" — because a refusal that says
what would lift it is planning information and one that does not is a wall. **Elimination is
per-point in pass 2**, §11.1's safer branch and the one matching the premise that spectral
shape varies spatially; a global mode would need unanimity across coarse points plus the
eliminated set in root attrs.

**THE FINDING: `NOT_ATTEMPTED` was carrying two incompatible meanings.** §12.5 initializes
status to it so an interrupted write reads as unattempted — *nothing wrote here*; §8.6 and
§14.1 used it to mean *screened out*, which is a verdict. **They are opposites in the only
way that matters — the absence of information against information — and they were sharing a
stored `uint8` whose meaning cannot change after data exists.** The completion bitmap
separates them only at tile granularity and only while a run is unfinished, i.e. **precisely
until the store is worth keeping**. `SCREENED_OUT` is added; both wordings corrected.

**`NOT_APPLICABLE` is separated from `INSUFFICIENT_DATA` now, one sub-phase early**, because
the reporting sub-phase will write against stores sub-phase 1 produced. They coincide in the
common case and are not synonyms: **a shelf pixel with a genuine but short record is
`INSUFFICIENT_DATA` and eligible; a land pixel is not eligible at all**, so they sit on
opposite sides of §14.2's denominator and collapsing them makes the failure rate
uninterpretable.

**`NOT_APPLICABLE` is UNDERIVABLE today, not merely unreachable.** The mask comes from the
data, so a land pixel is all-NaN → all-masked → `INSUFFICIENT_DATA`, and nothing can
distinguish land from every-value-happens-to-be-NaN. Reaching it needs **a declared
domain-mask variable in §13.6's input contract** — a second data source with its own
geometry-fingerprint entry, exactly like a per-point regressor. Three members are unreachable
in sub-phase 1 (`SCREENED_OUT`, `CANDIDATE_DROPPED`, `NOT_APPLICABLE`) and take **one
consolidated criterion-12 note** listing what would make each reachable.

**PUSHBACK THAT WAS CHECKED AND STOOD: `INSUFFICIENT_DATA` is NOT candidate-dependent in
v1.** `fit.py:175` computes `design_info(t, mask)` **once**, before the candidate loop at
line 208, because §12.1 fixes the signal spec and selects only the noise model. So every
design-derived outcome is identical for every `m`. The location/series distinction survives
— it is **location eligibility vs record adequacy** — but the "a 4-parameter design may be
insufficient where a 1-parameter one is fine" reason becomes true only under joint
signal × noise search (§19). **Consequence: the cancellation rule reaches the store's model
axis** — a test asserting design-failure behaviour must vary the **mask**, never the
candidate.

**THE (a2) CHECK CAME BACK CLEAN, AND THAT IS WORTH RECORDING.** Every prior seam check in
this project found the seam imagined or stale. This one found `DesignInfo.per_point` with
`series()` and `window()` branching on it, `memory.py`'s `X_term`, an explicit refusal in
`objective.evaluate`, and a test at `test_objective.py:457` pinning the refusal. **Recording
a clean result is what makes the checks credible rather than ritual.**

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

  **(k) EXTENDS TO REPEATED MEASUREMENT, AND THAT IS A DISTINCT SHAPE.**

  > **A repeated measurement must vary everything the measured quantity depends on.**
  > Repeats inside a fixed allocation, a fixed input, or a fixed process measure
  > **precision, not accuracy** — the component held fixed outside the repeat loop is
  > invisible to them by construction, and a best-of-N over one allocation, published as
  > though it were fresh, reports a confidence the method cannot support.

  **Measured (P4):** at the spike's worst cell the A:B spread is **0.13** across eight
  repeats inside one allocation and **0.82** across eight fresh processes. The dominant
  term was the one the repeats could not see, and `_time_pass`'s `repeats` argument
  tightens only the small one. The published ±0.15 scatter came from that loop.

  The check to run: **list what the number depends on, then list what the repeat loop
  re-creates.** Anything in the first list and not the second is a systematic the
  measurement cannot report — allocation, process, input realization, machine state, and
  in this project's history all four at once.

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

- **THE GOLDEN CONSTANTS WERE REGENERATED ON 2026-08-07, AND EVERY HASH IDENTITY MOVED
  WITH THEM.** The payload carries a version field whose key was renamed. Canonical JSON
  sorts keys, so the field changed position, which changed the serialized bytes, which
  changed every digest derived from them: `fit_hash`, `compat_hash` and `run_hash` are all
  different from what the same inputs produced before that date. The three
  `GOLDEN_*_HASH` constants in `tests/test_hashing.py` were re-derived by hand from the
  declared inputs — not copied from failing output — and the derivation was checked by
  renaming the key back, which reproduces the previous constants exactly and so proves the
  field set, the values, the separators, the sort rule, the digest and the truncation are
  all unchanged. **Consequence for anyone resuming old work: a store written before
  2026-08-07 carries hashes that no longer match, so it will report a mismatch and refit.**
  No store existed when the change was made, so nothing was invalidated in practice.
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
  2. ~~**`tile_side` is 171, not 339, until it is fixed**~~ **SUPERSEDED 2026-08-10 (P2):
     `tile_side` is 338.** Both engines now stream, `resident_bytes_per_series` is 8 722 B
     on path A against §9.4's 8 682 B model, and the two agree to 0.5%. **Every Phase 2 tile
     calculation uses 338; any Phase 1 note quoting 171 predates the fix.** The rule that
     survives is the labelling: budget against `resident_bytes_per_series`, never against
     `bytes_per_series`, because the gap being small today is a measurement rather than a
     guarantee. Historical figures, kept because the mechanism is the transferable part:
     the resident cost was 33 882 B/series → 171, against the 8 682 B → 339 model, and using
     the model would have overcommitted a hard 16 GB constraint by 3.9× — the run does not
     degrade, it dies.
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
- **A NAME IS NOT A GATE.** Three instances in three sittings, each reading as a gate and
  being none: `metamer_version` in `FIT_RELEVANT_FIELDS` with nothing in `src/` populating
  it (P0); `candidates` covered by no hash while §12.8 assumes enforcement (Q3);
  `data_uri` standing in for the data it names (Q5).

  > **A field's presence in a hash payload is not evidence that the thing it names is
  > checked.** Verify three separate facts: **something populates it**; **it derives from
  > the quantity it claims to identify**; and **a change in that quantity actually moves
  > it.**

  All three failed that last clause differently — nothing wrote it, nothing compared it, and
  it identified a location rather than a content. **Expect more of these in Phase 2**, which
  adds a store, a bitmap, a calibration cache and a warm-start cache, each of which is a
  gate made of a name.
- **A SCHEMA AXIS OF LENGTH 1 IS THE CANCELLATION RULE APPLIED TO A SCHEMA.** Every
  quantity *defined across* that axis is constant, so every assertion over it passes
  against an implementation that never normalizes, never excludes, and never writes a
  sentinel. **Minimum meaningful width for an axis under test is 2, and 2 with UNEQUAL
  extent where the axis is ragged.** At `M = 1`: `delta_ic ≡ 0`, `weight ≡ 1`,
  `best_index ≡ 0`, `n_valid ∈ {0, 1}`, and a point where one candidate fails while
  another succeeds is unconstructible. **Unequal `p` is the load-bearing half** — `white`
  (p=1) beside `white + matern12` (p=3) gives `off_1 = 1` and `P_total = 4`, which is the
  minimum that can falsify a "`/signal/` adopts this flattening unchanged" claim. At
  `M = 1` the offset arithmetic is exercised only at the value where it cannot be wrong.
- **HETEROGENEITY MUST COME FROM A PARAMETER THE LIKELIHOOD IS NOT EQUIVARIANT IN.**
  Timescale, mixing ratio, mask pattern, series length. **Varying an equivariant parameter
  produces a fixture that looks diverse and is identical.** The worked case is amplitude:
  a Gaussian log-likelihood is equivariant in it — scaling a series by `c` scales every σ
  by `c` and leaves the shape of the surface alone — so `* logspace(-1, 1, k)` contributes
  exactly nothing. Measured on the spike's iteration sample, one realization at four
  amplitudes: `n_iter = [28, 28, 28, 28]`, utilization **exactly 1.0**, which is the number
  that fixture's own docstring said the spread existed to challenge. Three separate
  fixtures used the construction and described it as what made the batch heterogeneous.
  **A fixture's stated mechanism of heterogeneity is a claim to measure**: hold everything
  but that mechanism fixed and see whether the statistic moves. Before writing the
  fixture, ask which of its varying quantities the objective is *invariant* under.
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
  `bd51413` (fixture-calibrated threshold), B built on A's tree and committed `c2c669e`
  (derived thresholds, per-series `DesignInfo`), then B reset to `43617a7` and re-committed
  the identical tree as `e6f829b` to get a clean single-commit history — taking two
  already-pushed commits off the branch. Reconciled with `git merge -s ours origin/phase-1`
  (`27bf419`): tree unchanged, both commits ancestors again, nothing force-pushed.
  **A behaviour-level diff of `bd51413` against HEAD found exactly one thing B had lost** —
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
  (`-m "not slow"`, 552 of 588) is for iteration only. What is marked and why:
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
- **A NEW TEST THAT ALLOCATES RAISES THE SESSION WATERMARK AND CAN FAIL A TEST IN ANOTHER
  MODULE.** P4's new `run_spike` tests called `bandwidth_reference` at its default
  `mib=256` — three vectors, so ~768 MiB — which took the pytest session's watermark to
  **991.7 MB** before `test_memory.py` ran. `test_a_child_measurement_is_not_contaminated_by_a_large_parent`
  then asserted `after >= 1.2 * before` after a fixed 400 MiB ballast, and the ballast
  moved the watermark by **exactly zero**. Fixed at the source: `run_spike` takes
  `bandwidth_mib` and the tests pass 64. **This is the delta-with-an-external-baseline
  hazard the module's own docstring describes, arriving from a different file** — the
  baseline is the whole session, so any test anywhere can set it.
- **The RSS shim's inheritance contract is under-specified — see open question 12.**
- Per user global instructions: never do investigative `git checkout <sha>` inside the
  working tree. Use `git show <sha>:<path>`, `git worktree add`, or `git diff <sha>`.

---

## Open questions

Still open. **A new session must not assume these were settled.**

1. **CI.** ~~Not specified anywhere.~~ **CLOSED 2026-08-07** by the publishing run.
   `.github/workflows/test.yml` runs lint plus **ubuntu-latest × 3.12/3.13/3.14**, the full
   sweep with `slow` included and `machine` deselected. The celerite2 agreement test **is**
   exercised — celerite2 is in the `test` extra. The `workflow` token scope was obtained via
   a device-flow `gh auth login`; `GH_TOKEN` in the environment cannot be refreshed and must
   be bypassed with `env -u GH_TOKEN` for pushes that touch `.github/workflows/`.
   **Windows and macOS are NOT claimed**, and the trove classifiers now assert no operating
   system at all. Both were tried and removed — see open question 10.
2. **Index-space vs area-weighted adjacency** for the failure clustering statistic (design
   doc §14.2). Index-space is recommended; not final.
3. **Which REML convention Hector uses** (see decisions above). Needed before the external
   cross-validation can attribute any discrepancy.
4. ~~**`requires-python = ">=3.12,<3.14"` carries an upper cap.**~~ **CLOSED 2026-08-07.**
   Published metadata is `requires-python = ">=3.12"` with no cap. The supported ceiling
   lives in the CI matrix and the classifiers instead. `pixi.toml` still pins
   `python = ">=3.12,<3.14"` for the development environment, which is a separate thing:
   CI tests 3.14 through `actions/setup-python`, so 3.14 is exercised but never locally.
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
   `bench/spike.py` on the MacBook. **Partial evidence 2026-08-07:** on **PyPI** (not
   conda-forge) celerite2 0.3.3 does ship `macosx_11_0_arm64` wheels, and a macOS CI job
   installed and imported it fine. That says nothing about conda-forge or about
   `linux-aarch64`.

9. ~~**`test_the_mixed_batch_really_holds_every_outcome_it_claims` fails intermittently in
   CI.**~~ **CLOSED 2026-08-08. It was the fixture, not the driver** — the first of the two
   readings below. Kept in full because the measurement is worth not repeating.

   Seen twice in four ubuntu jobs across two runs: 31239373295 (3.13) and 31240252583
   (3.12), each time with the sibling minors passing. Never seen locally.

   ```
   AssertionError: assert <Outcome.OK: 'ok'> in {DEGENERATE_HESSIAN, DIAGNOSTIC_LIMIT,
       ILL_CONDITIONED_X, INSUFFICIENT_DATA, RANK_DEFICIENT_X}
   ```

   Five outcomes for five rows with `OK` replaced by `DEGENERATE_HESSIAN`, so row 0 — the
   healthy one — was being failed on the curvature check. **Measured margin: `cond(H) =
   3.525382e+08` against `HESSIAN_COND_LIMIT = 1e10`. 28x. 1.45 decades.** A
   finite-difference Hessian's condition number moves further than that between BLAS
   builds, which is the whole mechanism.

   Root cause: row 0 was `rng.standard_normal(_GAP_N)` — **pure white noise** — while
   candidate 1 is white + Matérn 1/2. With no Matérn structure in the data its amplitude
   collapsed (fitted `sigma = 1.46e-4`) and `rho` sat on a flat ridge, unidentified. The
   verdict `DEGENERATE_HESSIAN` was arguably *correct*; the fixture was calling a
   near-degenerate series healthy and getting away with it only because 1e10 is generous.

   Fix: row 0 is now drawn from the composite's own covariance with `rho` at ten sampling
   intervals (`_healthy_row()`), which identifies all three parameters. **`cond(H)` went
   3.525382e+08 → 7.617468e+02, i.e. 1.45 decades of headroom → 7.12.** The threshold was
   not raised and no assertion was loosened.
   `test_the_healthy_row_has_real_margin_to_the_degeneracy_limit` now fails if row 0 ever
   comes within 1e4 of the limit again; it reproduced the CI failure locally before the fix,
   which is how the diagnosis was confirmed rather than inferred.

   **The lesson worth keeping: a fixture that is "healthy" by 28x is not healthy.** Any
   fixture asserting a clean outcome should be checked for its margin, not just its side of
   the threshold — and the two are separate tests, because conflating them does not say
   which property broke.

10. **macOS and Windows support.** Both were added to CI on 2026-08-07 and removed the same
    day. What failed was **not** the library: `tests/test_memory.py`'s RSS assertions
    (`assert 121667584.0 == 692469760.0 ± 3.5e+07` on both) and `test_bench.py`'s hard-coded
    `threads=4` against a 3-core macOS runner. `core/machine.py`'s win32 branch is still
    marked `# pragma: no cover - written, untested` and is now known to be *insufficient*
    rather than merely untested. Supporting either platform means first deciding what the
    RSS accounting should mean there — peak vs current, and what `ru_maxrss` has no
    equivalent for on Windows. Closed by that decision plus a green run on both.
11. ~~**`bench/spike.py`'s iteration sample is white noise fitted with two timescales, and it
    is now mostly `DEGENERATE_HESSIAN`.**~~ **CLOSED 2026-08-10 (P3).** The sample is now
    drawn from the candidate's own covariance, one parameter set per row, and all four rows
    come back `OK` at both d=1 and d=3 with the tightest `cond(H)` a factor of **4188** below
    `HESSIAN_COND_LIMIT`. `mean_iterations` at d=3 is **32.5** (was 90.0 on two series) and
    utilization **0.637**; at d=1, **13.0** and **0.929**. **Every `ms/fit` column in the
    verdict note and in `bench/*-streamed.json` is rescaled by 32.5/90.0 = 0.361 at d=3 and
    13.0/43.3 = 0.300 at d=1**, recomputed from the stored per-pass seconds rather than
    re-run; **no A:B ratio moves**, because the iteration count is common to both paths.
    Path B at production B = 114 244 goes 19.5 → **7.1 ms** against the 19 ms budget.

    **Two findings, one of them not the one being looked for.**

    - **The general form, which is what carries:** *a fixture whose data does not come from
      the model being fitted produces fits that are not representative of the workload, and
      every statistic conditioned on `OK` inherits that.* Three instances of the one defect
      now — `_healthy_row`, `_plain_batch`, the spike — and in all three the *verdicts* were
      correct while the *sample the statistics averaged over* silently narrowed.
    - **THE AMPLITUDE SPREAD WAS NEVER HETEROGENEITY, AND THE DOCSTRING CLAIMED IT WAS.**
      The Gaussian log-likelihood is scale-equivariant, so `* logspace(-1, 1, 4)` cannot
      move an iteration count. Measured, one realization at four amplitudes gives
      `n_iter = [28, 28, 28, 28]` and utilization **exactly 1.0** — the number the same
      docstring said the spread existed to challenge. Rows now differ by **generating
      parameters** (timescale and nugget at a fixed unit state amplitude), which is what
      varies across a grid. **Generalize: a fixture's stated mechanism of heterogeneity is a
      claim to measure**, and the cheap measurement is to hold everything but that mechanism
      fixed and see whether the statistic moves at all.

    The original record, kept because the diagnosis is the transferable part:
    `measure_mean_iterations` built
    `rng.standard_normal((4, N)) * logspace(-1, 1, 4)` and fits it with
    `white + Matérn 1/2 + Matérn 3/2` at d=3. Under the derived `HESSIAN_COND_LIMIT`,
    measured 2026-08-10: **d=3 reports `['DEGENERATE_HESSIAN', 'OK', 'DEGENERATE_HESSIAN',
    'OK']` and d=1 reports one degenerate of four.** The verdicts are correct — white noise
    cannot identify two timescales, which is open question 9's defect for the third time in
    a third fixture — but `mean_iterations` and `utilization` are computed over the OK
    subset only, so both are now measured on **two series** at d=3 (68.7 → 90.0 and
    0.64 → 0.84). **The A:B ratio is unaffected**: the iteration count is common to both
    paths and cancels. Recommended fix, deliberately NOT applied during P2 so the
    re-measurement compares like with like: draw each row from the candidate's own
    covariance with `rho` at ~10 sampling intervals, keeping the amplitude spread that makes
    the batch heterogeneous, exactly as `test_fit.py::_healthy_row` and `_plain_batch` now
    do. **Until then, treat the utilization figure as provisional** — PROGRESS's Task 17
    entry quoting 0.64 was measured on three series and the note quoting 0.84 on two.
    *(The recommendation's second half — "keeping the amplitude spread" — was wrong, and
    measuring it is what closed this. See above.)*

12. **WHAT VALUE DOES A CHILD INHERIT AS ITS WATERMARK — THE PARENT'S WATERMARK, OR THE
    PARENT'S CURRENT RSS AT SPAWN?** `machine.py` and `test_memory.py` both say
    `ru_maxrss` is *inherited* across `fork()`/`exec()`. Neither says **which value**, and
    the two are different claims. Measured 2026-08-10 while chasing an unrelated failure:
    a probe spawned from pytest read `before = 454.8 MB`, and that probe's own child —
    spawned while the probe held only ~85 MB resident — reported **84.6 MB**, i.e. the
    probe's *current* RSS and not the 454.8 MB it had itself inherited. If that is the
    rule, then `test_a_child_measurement_is_not_contaminated_by_a_large_parent` passes
    because pytest's inherited watermark and its current RSS happen to be close at the
    moment it runs, which nothing guarantees, and its `after >= 1.2 * before` assertion
    has a baseline set by the whole session (see the gotcha above, where a 400 MiB ballast
    moved that watermark by exactly zero).

    **Deliberately left open rather than fixed inside P4.** Restating the test means
    pinning the shim's inheritance contract, and pinning a contract in passing, inside a
    task about something else, is the change this project keeps paying for.

    **What would close it:** a standalone cross-process probe that varies the parent's
    current RSS and the parent's watermark *independently* — allocate, free, then spawn —
    and reports which one the child's `ru_maxrss` follows, on Linux and on macOS. Then
    state the answer in `machine.py`'s docstring, and restate the test against whichever
    quantity is actually inherited. **Both instruments are load-bearing for Phase 2's
    calibration tile**, which measures bytes-per-series in a child process, so this closes
    before the calibration work rather than before the store work.

9. ~~**`optimize.HESSIAN_COND_LIMIT = 1e10` is picked, not derived.**~~ **CLOSED 2026-08-10
   (P1), before Phase 2 planning as it required.** `HESSIAN_COND_LIMIT` is now
   `eps^(-1/2) = 2**26 = 6.7109e7` — one inversion, so one square root — and §4.8's two
   halves are on the same footing. Three related constants moved with it; the full record,
   including which fixtures flipped and why none of them was healthy, is in the **Phase 2
   preliminaries** section above.

---

## Deferred items

Design-level deferrals with their landing conditions are in design doc §19. Nothing is
deferred that is not recorded there. Phase 1 additions:

- Cross-term shared parameters (blocks σ² profiling) — refused with `NotImplementedError`.
- Per-point regressor fields — `signal.DesignInfo` carries the seam.
- Nonlinear signal terms (`ExpDecay`, `LogDecay`) — constructible, raise on use.
