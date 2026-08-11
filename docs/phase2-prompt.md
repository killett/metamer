# metamer Phase 2 — batch orchestration

## How to run this task

Read `docs/superpowers/notes/phase1-to-phase2-handoff.md` first, then `PROGRESS.md` and
the design doc. Everything needed is in those three files; there is no conversation
history to recover.

Then, in order:

1. **P3 and P4 below** — two outstanding items from Phase 1, each committed separately.
2. **Brainstorming**, using the superpowers brainstorming skill. The design doc already
   covers this territory (§8.6, §11, §12, §13, and the config decisions), so Phase 2 needs
   an **implementation plan, not a new design doc**. Brainstorming should settle the open
   questions in the section of that name, produce a phase list, and plan **only the first
   sub-phase** in detail.
3. **Stop for review** before implementation begins.

Run the full **(a)–(k) pre-flight** from the handoff on every task, before writing code,
not after. It exists because across Phase 1 Tasks 8–17, nearly every substantive defect
passed the brief's own tests, without a single exception. Treat every implementer
measurement as a claim to recompute.

---

## State at the start of Phase 2

Phase 1 is complete. `main` and `phase-1` are both at `cdf1100`; 597 tests; mypy strict
and ruff clean. `metamer` 0.1.0 is on PyPI.

What exists: the likelihood spine, end to end from a `ProcessSpec` to scored per-series
results under both ML and REML. Kernel algebra with a registry; the ParamSpec/Bijector
contract; GLS-concentrated linear signal models; the batched Kalman engine (path A, the
permanent numpy correctness reference) and the compiled numba engine (path B, the adopted
production backend); Richardson-extrapolated FD gradients with analytic forward-mode for
Matérn ν=1/2; the optimizer driver with its initialization ladder and failure taxonomy;
per-objective parameter counting and both effective sample sizes; the information criteria
with the engine and objective comparability guards; the static identifiability lint; and
the three-hash machinery with its compat-relevance allowlist.

What does not exist: **anything that touches a file**. No tiling, no zarr, no CLI, no
resumption. Phase 2 is that layer.

Two structural facts carried forward that Phase 2 must honour:

- **`fit_hash ⊂ compat_hash ⊂ run_hash`.** §12.8 treats a `compat_hash` mismatch with a
  matching `fit_hash` as licence to recompute the derived selection arrays from stored
  primitives **without refitting**. That is implementable because `rank_candidates` takes
  only stored primitives — never a spec, a design matrix, or the data. If any change makes
  it need the data, §12.8 becomes unimplementable and the three-hash split buys nothing.
- **The batched-equals-solo invariant** is the standing guard for the "(B, N) is the only
  code path" class. Every new batched routine keeps it green.

---

## P3 — fix the spike's iteration fixture (open question 11)

`bench/spike.py` draws its iteration sample as `standard_normal` and fits it with
`white + Matérn 1/2 + Matérn 3/2`. Under the derived `HESSIAN_COND_LIMIT` that yields
`[DEGENERATE_HESSIAN, OK, DEGENERATE_HESSIAN, OK]` at d=3, and since `mean_iterations` and
`utilization` average over `OK` only, they moved 68.7 → 90.0 and 0.64 → 0.84 — a P1 effect
surfacing inside a P2 measurement.

This is the **third** instance of one generator defect (`_plain_batch`, `_healthy_row`,
now the spike). Draw rows from the candidate's own covariance, as the other two now do.
`A:B` is immune because iterations cancel; the `ms/fit` columns are not, so re-report them.

Record the general form: **a fixture whose data does not come from the model being fitted
produces fits that are not representative of the workload**, and every statistic
conditioned on `OK` inherits that.

## P4 — reconcile the two benchmark harnesses

`bench/spike.py` and the batch sweep disagree by 0.57 on the post-fix ratio (3.84 vs 3.27)
against the ±0.15 scatter the verdict assumed, and they disagreed by **27% on an identical
quantity** before the fix. Neither number currently supports the precision the verdict
quotes.

Find the cause — warm-up, timer, iteration counting, batch composition, thread pinning, or
sample generator — and either unify the two paths or document why they legitimately
measure different things. Then restate the verdict's scatter from measurement rather than
assumption.

**And correct the verdict's stated mechanism.** It says path A is memory-bound and
therefore gains most from the `_augment` fix. What was measured is that path B fell ~20%
in both harnesses and path A did not measurably move, because path B had been reading a
per-series private copy of the shared design — B copies of the same `(N, k)` bytes — while
path A's cost is in `(B, d, n_cols)` einsum temporaries the block never touched. The
conclusion survives; the reasoning does not. Record that a correct conclusion reached
through a wrong mechanism is a finding in its own right, since the next prediction built
on that reasoning would be wrong.

Note also that production `B` moved 29 000 → 114 244 with the fix, so the re-measurement's
own target moved past the sweep's 20 000 ceiling. Any restated margin must name its `B`.

---

## Mission

`metamer.batch` — the layer that takes the Phase 1 core from "fits one batch of arrays" to
"fits 10⁷ gridded series overnight on a 64-core node, and runs at all on a 16 GB laptop."

The binding constraint is **memory scalability**; speed is the goal. A configuration that
overcommits does not degrade, it dies.

Six subsystems:

1. Tiling and the calibration tile
2. Zarr region writes, the completion bitmap, and resumability
3. The two-pass coarse/fine warm-start with its barrier
4. The cold-restart hysteresis audit
5. Run-level failure reporting — live counters, end-of-run report, exit codes
6. The CLI: TOML/pydantic config, staged validation, `validate --explain`

That is too much for one sub-phase. See **Phasing** below.

---

## Settled — from the design doc and prior decisions

These are inputs, not subjects for brainstorming. Push back only if one is actually wrong,
and say so explicitly rather than designing around it.

### Tiling

- Rechunk along **time only**. Spatial rechunking creates one dask task per
  (time chunk × lat tile × lon tile) and consumes gigabytes of graph state by itself.
- `tile_side = sqrt(block_bytes / (n_time · itemsize))`; outer Python loop over tiles;
  materialize one tile at a time. Peak RAM is one tile plus one dask chunk.
- Hard cap on total dask graph chunks as a guard.
- **The tile is the batch.** No per-pixel Python loop; the compiled backend runs
  `prange` over the tile's series.
- **Parallelism is within a tile, over series — never across tiles.** That is what makes
  peak RAM independent of core count, and hence makes the same job run on 4 cores and 64.
  Across-tile parallelism is the obvious later "optimization" and it multiplies peak RAM
  by thread count, silently.
- Data arrives float32 and core is float64. Convert **per dask chunk** during tile
  assembly so both full representations never coexist.

### The calibration tile

- Analytic bytes-per-series **per backend** — path A's solver state is per-series, path
  B's is per-thread, so the formulas differ in shape, not just constants. Output slots are
  `2p + 2k_β + 4` float64 per candidate and do **not** shrink under path B.
- Measure peak RSS on a small tile at startup, derive true bytes-per-series for this
  dataset and model set, size all subsequent tiles from it.
- Cache keyed on `(fit_hash, machine fingerprint, backend)`. Fingerprint is
  (CPU model, core count, total RAM) hashed — **not** hostname, which is meaningless on
  ephemeral nodes. Provide `--recalibrate`.
- `--memory-budget` in GB is the primary knob, defaulting to a fraction of detected free
  RAM, with byte-level overrides retained.
- Post-`_augment`, resident is 8722 B/series against §9.4's 8682 — a 0.5% gap.
  `tile_side` is **338**, production `B` ≈ 114 244. The standing check stands: *does the
  memory formula describe the code, or a model of the code?* Verify against the measured
  slope of RSS against B in a fresh process; treat any factor above ~1.5× as a missing
  term.

### The store

Zarr v3, sharding on, zstd + shuffle. **Shard = tile** so a region write is one shard;
**chunk = a subdivision** so reads stay sane. Compute and record actual chunk and shard
bytes rather than leaving them implicit.

```
/signal/       dense    beta[y,x,m,b], beta_err[y,x,m,b]
/primitives/   dense    log_lik[y,x,m], k[y,x,m], n_eff_bic[y,x,m], n_eff_trend[y,x,m]
/selection/    dense    delta_ic[y,x,m,c] f32, weight[y,x,m,c] f32,
                        ic_best[y,x,c] f64, selected[y,x,c], n_valid[y,x]
/noise/        ragged   theta[y,x,P_total], theta_err[y,x,P_total]
                        + noise_param_{model,name,unit,transform}[P]
/status/       dense    outcome[y,x,m] uint8
/detail/       ragged   full covariances — configurable subsample or region only
/warmstart/    dense    θ̂ in unconstrained coordinates — machine state, deletable
/completion/   dense    tiles[ty,tx] uint8
```

- **Ragged encoding is the flattened-with-index form.** One axis of length
  `P_total = Σ_m p_m`; model `m` occupies the contiguous slice `[off_m : off_m + p_m]`. No
  padding, so no padding-NaN/failure-NaN ambiguity; one chunk policy shared with the dense
  arrays; region writes uniform across every array. Write the flattening machinery
  **generically** over "a ragged axis with an index" so `/signal/` can adopt it unchanged
  when joint signal × noise search lands.
- Coordinate arrays use **fixed-width bytes or integer codes plus a JSON legend in attrs**
  — not variable-length strings. The acceptance criterion is a round-trip read through
  plain `xr.open_zarr` with metamer **not installed**.
- **Store ΔIC, not IC.** Raw IC is ~10³ with meaningful differences ~1, so float32 IC
  loses the signal; ΔIC in float32 keeps it. `ic_best` is float64.
- Store all M while M ≲ 32; document the threshold, defer top-k.
- Store `log_lik`, `k`, `n_eff` as **primitives**, with engine and objective tags as
  attrs, so a criterion can be recomputed without refitting 10⁷ series. This is what makes
  §12.8 work.
- **Natural units on disk**, delta-method push-through already applied. The store is an
  earth-science data product and must be readable without the library. Unconstrained θ̂
  lives in `/warmstart/` only.
- **Status is per (point, model)**, initialized to `NOT_ATTEMPTED` — not to zero/OK, so an
  interrupted write reads as unattempted rather than as success. `NOT_ATTEMPTED`
  (legitimately skipped) is distinct from failure and from
  `INSUFFICIENT_DATA` / `NOT_APPLICABLE`.
- **Bidirectional status invariant:** a NaN never coexists with an OK status, **and** a
  non-OK status has NaN in its value slots. Failed candidates carry NaN, never `-inf` —
  `-inf` is a finite-looking sentinel that survives an `isfinite` check downstream.
- Failed candidates get `ΔIC = NaN`, are excluded from weight normalization, and
  `n_valid[y,x]` records how many survived. A point where 11 of 12 failed has a weight
  vector that reads as confident selection and is nothing of the sort.
- `schema_version` in root attrs, written at creation, checked on resume and on read.
- Provenance in attrs: all three hashes, `ALGORITHM_VERSION`, registry version, per-
  candidate spec hashes, `metamer_version`, seeds, profile name, calibration provenance.

### Resumption

- **Write order is data-then-bitmap, always.** A tile's completion bit is set only after
  every array's region write for that tile has flushed. An interrupted run can never mark
  incomplete data complete.
- **`fit_hash` must match to reuse fits.** A `compat_hash` mismatch with matching
  `fit_hash` recomputes the derived `/selection/` arrays from stored primitives and
  continues — it does not refuse, and it does not refit.
- No POSIX assumptions: no file locking, no rename-based atomicity, no
  directory-listing-as-truth. The store must work over fsspec to object storage, which
  relies only on per-object write atomicity.
- Handle SIGTERM by flushing rather than dying mid-region-write. Preemption is just
  resumption.

### Warm-starting — two passes with a barrier

- **Pass 1**: a coarse subsample defined in **dataset coordinates, not tile coordinates**,
  fitted cold, fully parallel. This is what decouples the result from available RAM.
  Pass 1 also carries the calibration measurement, the cold reference for the audit, and
  the abort evaluation.
- **Barrier**, then **pass 2**: every remaining point warm-started from the interpolated
  coarse solution, also fully parallel because all its inputs already exist.
- Warm-start cache key is `(fit_hash, candidate spec_hash)` — per candidate, because θ̂ is
  per candidate. Refuse on mismatch; never silently reuse. Store it with the store, not in
  local scratch.
- Warm start carries θ̂ in unconstrained coordinates **only** — not L-BFGS curvature
  history, which is fragile across points and deepens hysteresis coupling.
- **Reproducibility guarantee, stated with its preconditions:** for a given
  (data, config, metamer version), output is bitwise identical regardless of memory
  budget, tile size, thread count, and traversal order. Preconditions: a fixed,
  order-independent coarse-to-fine interpolation; deterministic or excluded global
  reductions; `fastmath` off; BLAS threading pinned. State the scope; do not overclaim.
- Warm-starting is disableable and whether it was used is recorded, because it changes the
  meaning of the output.

### The hysteresis audit — mandatory, not optional

Warm-starting biases every point toward its neighbour's answer, which produces spatially
smooth maps. Spatial smoothness is what this package is trying to achieve — **earned via
IC weights and model averaging**. Optimizer hysteresis produces a visually identical
result by an illegitimate mechanism, and it would look like the design working.

- Re-fit a **stratified** subsample cold after the warm run. Stratify by difficulty —
  Hessian condition number, small ΔIC to next-best, failure status — because hysteresis
  concentrates exactly where the likelihood is multimodal or flat. A uniform random sample
  is dominated by easy points and reports a reassuringly low rate.
- Four disagreement metrics, reported separately: **selection** (different model chosen),
  **objective** (|Δℓ| — distinguishes "different optimum" from "same optimum, different
  precision"), **parameters** (distance in unconstrained coordinates normalized by
  standard error), and **signed trend** (the scientific payload — a zero-mean disagreement
  is noise, a biased one is contamination). **Cold is the reference.**
- Report **mean iterations warm vs cold**. If warm-starting saves less than ~30% of
  iterations it is not paying for its complexity or its hysteresis risk, and the audit
  must be able to conclude "don't do this."
- **The confound (§11.2):** two same-kind terms with a free timescale are exchangeable
  across the whole searched space. Canonical ordering fixes reporting *within* one fit and
  nothing *between* fits. Across grid points that produces large parameter disagreement
  with near-zero selection, objective and signed-trend disagreement — a signature the
  audit would read as benign hysteresis when it is non-identifiability. Report per-term
  parameter disagreement separately from the aggregate, and **do not measure hysteresis on
  a lint-flagged candidate set and quote the number as hysteresis.** `core.lint` is the
  cheap pre-check.
- Benchmarking hysteresis needs **simulated fields with known spatial structure**, not
  independent series — a smoothly varying field and a sharp-boundary field. The
  boundary-smearing width is the direct measurement of the artifact, and that figure
  belongs in the README.

### Run-level reporting

- **Live**: per-tile tallies by taxonomy branch and by candidate. **Early abort evaluated
  on pass 1**, which is a stratified global sample by construction — not on the first 1%
  of tiles, which is a geographically contiguous strip and therefore biased.
  All-candidates-failing → abort. Single-candidate-failing → abort by default, with
  `--on-candidate-failure={abort,drop,continue}`; a dropped candidate gets a distinct
  status code across all remaining points and a headline line in the report.
- **End of run**: computed **from the store**, not from carried counters, so a resumed
  run's report covers the whole run. Exposed as `metamer report <store>` so it is
  regenerable and independently testable.
  - Counts and rates per branch and per candidate, **with the eligible-point denominator
    stated explicitly**. `INSUFFICIENT_DATA` / `NOT_APPLICABLE` — land, permanent ice,
    series below a minimum sample count — is a legitimate expected outcome and must be
    excluded from every failure rate. Without that, an ocean-only run on a global grid
    reports ~70% "failure."
  - **A spatial clustering statistic** on the failure indicator, with a permutation
    baseline. 3% scattered is fine; 3% concentrated in the Southern Ocean is a finding,
    and a scalar rate cannot distinguish them. Exclude `NOT_APPLICABLE` points from the
    adjacency graph entirely — land forms enormous contiguous blocks and would dominate.
    State whether adjacency is index-space or metric-space.
  - Downsampled PNG map per branch. The map is the diagnostic in this domain.
  - The `n_valid` distribution; the audit numbers overall and per stratum; iteration-count
    histogram; resolved config; all hashes; calibration provenance.
  - Per-candidate resolved engine, cost class, gradient mode, and objective — the same
    table `--explain` prints.
- Markdown + PNGs beside the store, the same numbers as JSON, scalar summary into root
  attrs.
- **Exit codes**: 0 clean; 1 completed with failures above threshold; 2 aborted early;
  3 config/validation error (layers 1–3); 4 data-dependent validation error (layer 4). A
  script that resumes on failure must distinguish "aborted, resumable" from "config
  rejected, resuming won't help." The final line carries the `compat_hash` and the store
  path.
- `iterations[y,x,m]` must be stored (dense uint16) or the report cannot regenerate the
  iteration histogram. It is independently useful as a proxy for likelihood difficulty.

### Config and validation

- **TOML** as the human format, **pydantic** as the schema, **canonical JSON** as the
  hashed form. `.json` also accepted for machine-generated configs. Structured
  list-of-terms is canonical; `"white + matern32 + sho"` is sugar that desugars to it.
- **Hash the validated, normalized model, not the file text**, so comments, key order,
  whitespace and explicit-vs-default all normalize away.
- Compat-relevance is an **allowlist** on fields. New fields default to provenance-only;
  promoting one is deliberate and covered by the golden test.
- **Staged validation, each stage naming itself in its error:**
  1. Syntax — TOML/JSON parse.
  2. Schema — pydantic types, ranges, enums.
  3. Semantic, data-independent — empty engine-capability intersection naming which term
     eliminated which engine; REML with a varying-X candidate set; REML with nonlinear
     signal terms; cost class incompatible with series count; duplicate candidates by spec
     hash; MCMC above threshold; **gradient-capability resolution across composite terms**;
     criterion/objective compatibility; identifiability lint as a warning.
  4. Data-dependent — epochs inside the record, harmonics resolvable by the sampling,
     regressor alignment, `rank(X_r)`. Runs at startup against pass 1, not at parse time.
- **`metamer validate <config> --explain`** is first-class: runs layers 1–3 (4 if data is
  reachable), then prints the resolved canonical config, all hashes, resolved engine, cost
  class and gradient mode per candidate, estimated ms per series-model, and projected wall
  time and peak RSS. **Print the provenance of the projections inline** — measured on this
  machine from cache, measured this session, or shipped defaults — and in the last case
  print a range, not a point estimate. Offer `--explain --calibrate`.
- Profiles are **flat named presets** applied before validation, never an inheritance
  chain. The resolved config is what gets hashed; the profile **name** is recorded
  separately, because "this run used the screening profile" is the human-legible fact
  someone needs six months later.

---

## Open questions for brainstorming

These are genuinely undecided.

- **Which vertical slice is sub-phase 1.** See Phasing.
- **Dask and numba threading interact badly by default.** Dask workers × `prange` threads
  oversubscribes. How is the thread budget owned, and by whom?
- **The screening pass.** §6 folds Whittle screening into pass 1, but no Whittle engine
  exists — it is Phase 3 work. Does pass 1 ship without screening, and if a candidate is
  ever eliminated on the coarse grid, is elimination global (a strong assumption, given
  the premise that spectral shape varies spatially) or per-point?
- **Per-point regressors.** Design becomes `(B, N, k)` and rank becomes `(B,)`, and the
  memory term is potentially dominant. In sub-phase 1, or deferred with the seam kept?
- **The coarse-to-fine interpolation rule**, which the bitwise guarantee depends on.
- **Input adapters.** What does metamer accept — any xarray-openable store, or a declared
  set? Where does the time-axis contract (decimal years) get enforced?
- **`/detail/` selection.** Subsample, named region, or both, and how specified.
- **The failure taxonomy at tile granularity** versus point granularity in the live
  counters.
- **Whether the CLI is in sub-phase 1 or last.** It is the natural driver, and also the
  thing most likely to churn.

---

## Phasing

Sub-phase 1 must be a **vertical slice**, not a horizontal layer — Phase 1's lesson was
that a horizontal phase gives no feedback until much later and hides interface mistakes
until they are expensive.

My recommendation, to be argued with: **tiling → fit → zarr write → resume**, at the
narrowest possible width. One input dataset, one candidate, one criterion, no
warm-starting, no audit, no reporting, no CLI beyond a bare entry point. What it must
prove is the store schema and the completion-bitmap contract, because **the store is the
most expensive thing to change after data exists**, and resumability cannot be retrofitted.

Everything else — the two-pass barrier, the audit, reporting, the full CLI — accretes onto
a working store.

Two things that cannot be retrofitted and must land in sub-phase 1 regardless of which
slice is chosen: the **status/value bidirectional invariant** wired through every write
path, and the **`fit_hash` resume gate**.

---

## Testing

Same discipline as Phase 1. Follow the `test-design` skill: before each test, state the
behaviour under test and a concrete bug that would make it fail, and determine expected
values independently of the implementation. Prefer analytic endpoints to tolerance bands.
Verify every test bites by deleting the guard it protects. Enumerate exits; never assert a
count. Default to heterogeneous batches.

Phase 2 adds test hazards Phase 1 did not have:

- **Filesystem and process state.** Under (k): anything depending on cwd, environment,
  file ordering, or wall-clock is unstable across runs. Test across processes.
- **Kill-and-resume is the headline test.** `kill -9` mid-tile, then resume, and assert the
  resulting store is **byte-identical** to an uninterrupted run.
- **Bitwise determinism** across two memory budgets and two thread counts, within the
  stated preconditions.
- **The no-metamer read.** Open the full store with plain `xr.open_zarr` in an environment
  where metamer is not installed. That is the actual acceptance criterion for
  "self-describing."
- **Every taxonomy branch present in one store**, with the bidirectional status invariant
  asserted in both directions across it.
- **Do not test tile-scale behaviour with a full fit.** `fit` costs ~5.4 s per series;
  a B=10⁴ fixture would take ~15 hours. Use a batched evaluation, or a stub engine.

---

## Exit criteria for sub-phase 1

Draft; brainstorming should finalize.

1. Kill-and-resume produces a byte-identical store.
2. Bitwise-identical output across two memory budgets and two thread counts.
3. Full store round-trips through plain `xr.open_zarr` with metamer uninstalled.
4. Status/value invariant holds in both directions across a store containing every branch.
5. A `fit_hash` mismatch on resume is refused; a `compat_hash`-only mismatch recomputes
   derived arrays without refitting.
6. Measured peak RSS matches the analytic per-backend formula within tolerance at two or
   three tile sizes, verified against the RSS-vs-B slope in a fresh process.
7. A run completes on a 16 GB machine with ≤10 GB free at a tile size derived from the
   calibration measurement.
8. Completion bitmap is never set ahead of the data, demonstrated by an interruption
   injected between the two writes.

---

## Practicalities

- Apache-2.0, Python ≥3.12, `src/` layout, `metamer` on PyPI at 0.1.0.
- `pixi run test` is the full sweep (~255 s and rising) and is what every end-of-task
  verification runs. `pixi run test-fast` is for iteration only — **a green fast run is
  not evidence a task is done.** Mark new slow tests as they land, not after.
- `numba` pins `numpy<2.5`; 2.4's stubs infer `floating[Any]` where 2.5's infer `float64`,
  so mypy reports errors in files nobody touched. Environment fact, not a regression.
- One writer per working tree. Never `git reset` a branch whose commits are pushed.
- `bench/spike.py` stays a one-command run so `box64.json` or `macbook.json` can be
  produced later without reconstructing anything.
- Open questions 5–8 remain open: the 64-core box's RAM, roofline validation across
  machines (blocks the cloudify cost projection), path B at high thread occupancy, and
  numba/celerite2 on arm64.
- **Do not publish.** Publication is handled separately.
