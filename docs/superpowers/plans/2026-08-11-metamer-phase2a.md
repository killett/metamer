# metamer Phase 2a — the vertical slice: config → input → tiling → fit → store → resume

**Written 2026-08-11**, from the Phase 2 brainstorm recorded in `PROGRESS.md`'s
*Phase 2 brainstorm — settled decisions* section and the design-doc amendments it produced.

**Read before starting, in this order:**

1. [`docs/superpowers/notes/phase1-to-phase2-handoff.md`](../notes/phase1-to-phase2-handoff.md)
   — the pre-flight (a)–(k) with (a2) and (a3), and the standing rules.
2. `PROGRESS.md`, whole file. The brainstorm section carries the reasoning behind every
   decision below; this plan carries only the decisions.
3. Design doc §9.4, §11.1, §11.1.1, §11.3, §12, §13, §14.3.

---

## Why this plan has no code fences

**Phase 1's plan carried full implementation fences, and they were the principal vector for
its defects.** Across Tasks 8–17, nearly every substantive defect passed the brief's own
tests, because a brief-generated test validates the brief's *model* of the problem. Task 15
bound cleanly against every current signature and was wrong five ways; Task 16 bound cleanly
and shipped a serializer that hashed memory addresses.

So each task below states **behaviour, invariants, interfaces, and for every test the bug it
must catch** — and stops there. The implementer writes the code and the tests. What replaces
the fence is the pre-flight, run against the task brief *before* any code, and the explicit
statement of what each test exists to falsify.

Interfaces are given as signatures where a later task calls into an earlier one, because
pre-flight (g) needs something to bind against. Bodies are not.

## Standing requirements for every task

- **Run the (a)–(k) pre-flight against the task brief before writing code**, including (a2)
  *a name is not a gate* and (a3) *defer the feature, declare the regime*.
- **`pixi run test && pixi run typecheck && pixi run lint` before every commit**, and
  `pixi run pre-commit run --all-files`. `pixi run test-fast` is for iteration only.
- **Mark new slow tests `slow` as they land.** Tests that assert machine-specific numbers
  are also `machine`.
- **Commit after every completed task.** One writer per working tree.
- **Every test states the behaviour under test and a concrete bug that would make it fail**,
  and its expected values are derived independently of the implementation.
- **Verify each test bites** by deleting the guard it protects.

---

## Task index and dependencies

| # | task | depends on |
|---|---|---|
| 0 | Package skeleton for `metamer.batch` and `metamer.config`; new dependencies | — |
| 1 | The config model, `load()`, and the normalize/hash wiring | 0 |
| 2 | The opener registry, the zarr opener, and the time-axis contract (stage 4a) | 1 |
| 3 | `geometry_hash`: components, allowlist change, golden re-derivation | 1, 2 |
| 4 | Validation staging 1/2/3/4a, exit codes, `python -m metamer` | 1, 2, 3 |
| 5 | The thread budget: ownership, `threadpoolctl`, the observed-limits assertion | 0 |
| 6 | Tiling: `tile_side` from budget, the tile iterator, read amplification | 2, 5 |
| 7 | The store schema: creation, groups, coordinate dtypes, provenance attrs | 1, 3 |
| 8 | The ragged index builder, generic over an extent function | 7 |
| 9 | The tile write path and the status/value invariant | 6, 7, 8 |
| 10 | The completion bitmap, write ordering, and SIGTERM | 9 |
| 11 | The resume gate and its three outcomes | 3, 7, 10 |
| 12 | `--reuse-fits-from`: the recompute path | 9, 10, 11 |
| 13 | The exit-criteria suite | 1–12 |

**Task 13 is not a formality.** Six of the sixteen exit criteria are cross-process or
cross-store properties that no single task's tests can express.

---

## Task 0 — package skeleton and dependencies

**Goal.** `metamer.batch` and `metamer.config` exist and import; new dependencies are in
`pixi.toml` and the lock file is regenerated.

**Dependencies to add:** `zarr` (v3), `xarray`, `pydantic`, `threadpoolctl`. All are on
conda-forge for all four platforms; check with `pixi search --platform` per platform and use
a known-good package as a control, because `rg | head` swallows a non-zero exit and an empty
result looks identical to a failed query.

**Watch:** adding dependencies rewrites and stages `pixi.lock`. The local
`check-added-large-files` limit is 2000 KB and the lock file is currently 630 KB — **re-check
the number, not this note.** A dependency add can also break `mypy` in files it never
imports; re-run the whole typecheck, not the new files.

**Acceptance.** `python -c "import metamer.batch, metamer.config"` succeeds; the full suite,
typecheck and lint are green; `pixi install` solves on all four platforms.

---

## Task 1 — the config model, `load()`, and the hash wiring

**Goal.** `metamer.config.load(path) -> Config` is the only constructor a run uses, going
through `tomllib` → pydantic → `hashing.normalize` → `canonical_json` → the three hashes.

**Interfaces.**

```
metamer.config.load(path: Path) -> Config
Config.fit_hash() -> str | None      # None until stage 4a has run — see Task 3
Config.compat_hash() -> str | None
Config.run_hash() -> str
Config.to_payload() -> dict[str, Any]   # what normalize consumes
```

**Behaviour.**

- **TOML is the human format; `.json` is accepted for machine-generated configs.** The
  structured list-of-terms is canonical and the `"white + matern12"` string form desugars to
  it by restricted evaluation against the registry namespace, not a hand-rolled tokenizer.
- **Hash the validated, normalized model, not the file text**, so comments, key order,
  whitespace and explicit-vs-default all normalize away.
- `ALGORITHM_VERSION` is stamped by `normalize` and a config supplying it is refused.
- The config carries `metamer_version` as **provenance only**.

**Fields required by later tasks**, with their hash relevance decided in the brainstorm:

| field | relevance |
|---|---|
| `variable`, `signal_terms`, `objective`, `engine`, `seed` | fit (already in the allowlist) |
| `candidates` | **neither hash** — enforced positionally by Task 11 |
| `criteria` | compat |
| `data_uri` | **provenance only** after Task 3 |
| `warm_start.{enabled, coarse_stride, interpolation_rule, spiral_bound, tie_break}` | **fit** |
| `detail.{region, subsample}` | neither — fixed at creation, Task 11 refuses a change |
| `memory_budget_gb`, `threads`, `output` | run |
| `screening.*`, per-point regressor terms | present, **refused at layer 3** (Task 4) |

**Tests, and the bug each catches.**

- *Two configs differing only in comments, key order and explicit-vs-default hash
  identically.* Catches hashing the file text, which would invalidate a 10⁷-point store on a
  comment.
- *A config supplying `algorithm_version` is refused, not overridden.* Catches a silent
  override leaving a user who believed they pinned algorithm identity with a payload that
  says otherwise.
- *`warm_start.coarse_stride` moves `fit_hash`.* **This is the (a2) check for the fourth
  allowlist finding** — do not infer it from membership; assert the movement.
- *`criteria` moves `compat_hash` and not `fit_hash`; `threads` moves neither.* Catches the
  partition drifting.
- *A cross-process test that the same TOML file hashes identically under three different
  `PYTHONHASHSEED` values*, compared against a hand-derived constant. **Not two calls in one
  process** — that is the only defect class an in-process suite cannot reach, and this
  module is the one where it already happened once.

---

## Task 2 — the opener registry, the zarr opener, and stage 4a

**Goal.** A named opener registry with **one** entry (zarr, local and fsspec), and the
input-contract check that runs at store-open before any tile.

**Interfaces.**

```
metamer.batch.input.opener_registry            # name -> opener callable
metamer.batch.input.open_input(config) -> InputHandle
metamer.batch.input.check_contract(handle, config) -> ContractReport   # stage 4a
```

**Behaviour.**

- **The contract is on dataset shape, not file format:** one named variable, dims mapping to
  `(time, y, x)`, a 1-D time coordinate.
- **metamer converts the time axis to decimal years. The user never supplies them.** An
  interface that asks for decimal years invites the error Phase 1 measured — `cond(X)` from
  3.4e1 to 3.3e32, rank 7/7 to 2/7, `cos(annual)` identically 1.0, a full-rank-looking design
  that has silently lost five columns.
- **Units are never inferred from magnitude.** Time must be CF-decodable to `datetime64`, or
  the config declares its units. A bare numeric axis with neither is a stage-4a error naming
  what was found and what is required. Days-since-1970 over 50 years is ~2e4 and years-since-0
  is ~2e3, so a magnitude heuristic is ambiguous on exactly the axis it must disambiguate.
- **The conversion rule is under `ALGORITHM_VERSION`.** Changing it moves every `θ̂`.
- **Strictly increasing**, which catches a duplicate and a reversal and a single-sample axis
  in one check. A duplicate gives `Δt = 0`: an identity transition with zero process noise,
  singular, surfacing deep inside the filter rather than at the boundary.
- **Report the unique-Δt count.** A nearly-regular axis carrying float noise otherwise gives
  thousands of unique Δt and an order-of-magnitude slowdown with nothing saying why. **Record
  it in provenance** — `--explain` is Phase 5 and only prints it.

**Tests, and the bug each catches.**

- *A seconds-since-1970 axis and a decimal-years axis over the same record produce the same
  decimal-years result.* Catches passing the raw numbers through.
- *A duplicated timestamp is refused at stage 4a.* Catches the `Δt = 0` singularity being
  discovered inside the filter.
- *A bare numeric axis with no CF units and no declaration is refused, and the message names
  both.* Catches a magnitude heuristic being added later.
- *A `noleap` axis and a `proleptic_gregorian` axis with identical raw values produce
  different decimal years.* This is the fact that makes the calendar fit identity in Task 3;
  assert it here so Task 3's inclusion is justified by a measurement.
- *The unique-Δt count is 1 for a regular axis and large for one perturbed by float noise.*
  Catches the report being computed from the nominal step rather than the realized one.

---

## Task 3 — `geometry_hash`

**Goal.** `data_uri` leaves `FIT_RELEVANT_FIELDS`; `geometry_hash`, stamped by stage 4a,
replaces it.

**Why**, in one sentence to be preserved in the docstring: **the old gate was wrong in both
directions at once** — moving a file invalidated a scientifically valid resume and rewriting
one in place permitted a scientifically invalid one — and a gate wrong both ways is not a
conservative approximation of the right gate.

**Components:** dims, shape, source dtype, and the **full value arrays** of the time and
spatial coordinates through `canonical_json`, **for every input array the config names** —
not only the primary variable. The **decoded** time values, never the `calendar` attrs
string, or a `cftime` upgrade silently invalidates every store. Units, calendar and epoch
strings ride alongside as provenance.

**Named for what it covers.** It does not hash the payload array (~25 GB at 10⁷×630 float32).

**Mismatch is its own message naming the differing component** — shape, time coordinate,
spatial coordinate, calendar, dtype — because "your data changed, here is how" is actionable
and "your hash changed" is not. **Root attrs carry the components as well as the rollup**, so
the message is implementable on the resume side where only the stored store is available.

**The allowlist change moves all three `GOLDEN_*` constants.** Re-derive them **by hand** from
the declared inputs and **verify by reversal** — put `data_uri` back, take `geometry_hash`
out, and reproduce the current constants exactly. That is what proves only the field set
moved and not the separators, the sort rule, the digest or the truncation. **Never regenerate
them from the failure.**

**Tests, and the bug each catches.**

- *A value edit at fixed geometry does **not** move `geometry_hash`.* **This is the limit made
  executable rather than advisory**, and it is the honest documentation — a docstring does not
  constrain the next author.
- *A regrid that preserves extent **does** move it.* Catches min/max/length being used as the
  shortcut, which collapses exactly that case.
- *Moving the store to a new path does not move `fit_hash`.* Catches `data_uri` still being
  fit-relevant.
- *A second input array (constructed, since per-point regressors are refused) contributes to
  the hash.* Catches the fingerprint covering only the primary variable.
- *Three golden constants, hand-derived, and the reversal test.*

---

## Task 4 — validation staging, exit codes, and `python -m metamer`

**Goal.** Layers 1/2/3/4a as structure, all five exit codes as an enum and a return value,
and a runner with a process boundary.

**Behaviour.**

- **Each layer names itself in its error.** "Your config is invalid" before a 10-hour job
  needs to say which layer and why.
- **Layer 3 in 2a** carries only what 2a can trigger: the screening refusal (**naming the
  missing engine specifically** — "screening requires the debiased Whittle engine (Phase 4)"),
  the per-point regressor refusal (**naming the field and both tile sizes**, 338 against 186,
  because layer 3 knows them and "not implemented" wastes context the user needs), duplicate
  candidates by spec hash, criterion/objective compatibility, and the identifiability lint as
  a warning. **The staging is the structure; the checks accrete.**
- **Exit codes:** 0 clean, 1 completed with failures above threshold, 2 aborted early, 3
  config/validation layers 1–3, 4 data-dependent layer 4. **2a can produce 0, 3 and 4**; 1 and
  2 get a constructed test each or an explicit note that their producer is 2e.
- **`python -m metamer <config.toml> <store>`**, argparse, one screen, no typer, no rich.
  Flags: `--memory-budget`, `--reuse-fits-from` (Task 12). **Not** `metamer run` via
  `console_scripts` — naming a subcommand presupposes the tree it belongs to and designs the
  argument structure before Phase 5 knows it.
- **The final line carries `fit_hash`, `compat_hash` and the store path.**

**Tests.** Each reachable exit code from a constructed condition, asserted **through a
subprocess**, not by calling `main()` — the code is a process property. Enumerate the exits;
never assert a count.

---

## Task 5 — the thread budget

**Goal.** One owner at a time, limits observed rather than requested.

**Behaviour.**

- **Assemble and fit never overlap.** Neither phase reasons about the other's threads.
  Serializing costs the idle I/O during fit and idle cores during assembly; at ~5.4 s per
  series against a tile read of order seconds, **fit dominates by orders of magnitude and the
  idle I/O is free. Record the ratio**, because if it inverts the decision needs revisiting
  and nothing else would show it.
- **`threadpoolctl` sets and reports.** Record the **observed** limit for **every** library it
  finds — OpenBLAS, MKL, OpenMP, numba's layer. `OMP_NUM_THREADS=1` in provenance records a
  *request*, and whether it took effect depends on import ordering nothing enforces.
- **Observed ≠ requested is a layer-3 failure** naming the discrepancy, not a note.
- **Thread counts reach `run_hash` only.** If they moved `fit_hash`, the hash boundary would
  be conceding that §11.3's guarantee does not hold.

**Tests.** *Provenance records a per-library table, not a scalar* — catches one number
standing for four. *A deliberately mismatched limit raises a layer-3 error* — catches the
observation being recorded and ignored.

---

## Task 6 — tiling

**Goal.** An outer Python loop over tiles, one tile materialized at a time, **no dask**.

**Behaviour.**

- `tile_side = sqrt(block_bytes / resident_bytes_per_series)`, **budgeted against
  `memory.resident_bytes_per_series` and never against `bytes_per_series`.** The two agreeing
  to 0.5% today is a measurement, not a guarantee.
- **A tile is `ds[var].isel(y=…, x=…).load()`.** Its peak is analytic; a dask graph's is
  emergent, and the calibration tile in 2b needs a formula with one term.
- **float32 → float64 conversion per chunk during assembly**, so both full representations
  never coexist.
- **Report read amplification — bytes read over bytes used — into provenance.** zarr reads
  whole chunks, so a tile straddling chunk boundaries silently reads several times what it
  needs. **This replaces the graph-chunk cap as the guard against a pathological input.**
- **Peak RAM is derivable from the memory budget alone.** No concurrency degree here is set
  by core count.

**Tests.** *Tile geometry covers the grid exactly once, including ragged edge tiles* —
catches a store with an unwritten seam. *Read amplification is >1 for a deliberately
misaligned tile and 1 for an aligned one* — catches the metric being computed from the
request rather than the read.

---

## Task 7 — the store schema

**Goal.** Store creation with every group except `/detail/`, and provenance.

**Layout.** `/signal/`, `/primitives/` (including `iterations` uint16), `/selection/`,
`/noise/`, `/status/`, `/warmstart/`, `/completion/`. **`/detail/` is not created** — an
uncreated group is a cleaner deferral than an empty one.

**Width: M=2 with unequal `p`, C=2.** Candidates `white` (p=1) and `white + matern12` (p=3),
so `off_1 = 1` and `P_total = 4`. Criteria **AIC and HQIC** — HQIC has the wider reachable
undefined region (`n ≤ 2` against BIC's `n ≤ 1`), so the criterion axis carries a real
asymmetry instead of two criteria that agree everywhere.

**Why not M=1, C=1:** a schema axis of length 1 makes every quantity defined *across* it
constant, so every assertion over it passes against an implementation that never normalizes,
never excludes and never writes a sentinel.

**Zarr v3, sharding on, zstd + shuffle. Shard = tile, chunk = a subdivision.** Compute and
record the actual chunk and shard bytes rather than leaving them implicit.

**Coordinate arrays use fixed-width bytes or integer codes plus a JSON legend in attrs** —
not variable-length strings.

**Natural units on disk**, delta-method push-through applied. Unconstrained `θ̂` lives in
`/warmstart/` only.

**`schema_version` in root attrs at creation.** Provenance: all three hashes, the
`geometry_hash` **components** as well as the rollup, `ALGORITHM_VERSION`, registry version,
per-candidate spec hashes, `metamer_version`, seeds, profile name, the per-library thread
table, read amplification, the unique-Δt count, and the regressor regime with both tile
sizes.

**Every store is self-contained.** No store resolves through another — not by zarr reference,
symlink, or a path in attrs a reader must follow.

---

## Task 8 — the ragged index builder

**Goal.** One builder, generic over a **per-model extent function**, not a per-model
parameter count.

**Behaviour.** `/noise/` uses `p_m`; `/detail/` will use `p_m(p_m+1)/2`. **Both offset tables
are stored as coordinate arrays, not derived at read time**, so a no-metamer read can slice
either without knowing the triangular formula. A covariance, when `/detail/` lands, is the
**packed lower triangle with its storage order in attrs**.

**Test the builder with BOTH extent functions now, even though `/detail/` is unwritten** —
`P_total = 4` against `4 + 6 = 10` at the M=2 fixture. **A design that reuses one table looks
correct at equal `p` and is wrong at unequal `p`**, which is the reason the fixture has
unequal `p` at all.

---

## Task 9 — the tile write path and the status/value invariant

**Goal.** One region write per array per tile, with the invariant wired through **every**
write path.

**The invariant, scoped.** `/status/outcome[y,x,m]` governs `/signal/`, `/noise/` and
`/primitives/`: a NaN never coexists with `OK`, and a non-`OK` status has NaN in **all** its
value slots. **`/selection/` carries its own criterion-wise validity** through NaN ΔIC and the
`-1` no-winner sentinel, and **a NaN there beside an `OK` status is legal** — it means "this
criterion could not rank this point". `outcome` has no `c` axis, so a criterion-specific
failure cannot go through the outcome ladder.

**Failed candidates carry NaN, never `-inf`** — `-inf` is a finite-looking sentinel that
survives an `isfinite` check downstream. They are excluded from weight normalization, and
`n_valid[y,x]` records how many survived.

**Status initializes to `NOT_ATTEMPTED`**, which means *nothing wrote here* — **not** "screened
out", which is `SCREENED_OUT`. Add `SCREENED_OUT` and `NOT_APPLICABLE` to `Outcome` in this
task, with the consolidated criterion-12 note naming what would make each of the three
unreachable members reachable.

**Store ΔIC, not IC.** `ic_best` float64, `delta_ic` and `weight` float32.

**Fixture requirements**, both of which must be *required* properties rather than incidental:

- **A point where candidate 1 fails and candidate 2 succeeds** — the offset-inside-a-gap
  construction, a breakpoint with no support for one candidate's design. `n_valid = 1` there,
  and the weight vector renormalizes over one survivor, **which is the case that reads as
  confident selection and is not.**
- **A point where every fit is `OK` and one criterion cannot rank it.** Take the **REML
  route**: `n = n_obs − design_rank`, so `n_obs = 6` against a rank-4 design gives `n = 2` and
  HQIC is undefined while AIC is fine. **State in the test why the ML route cannot work** —
  under ML `n = n_obs`, so with the four-column design the precheck refuses the series first
  and the point is unreachable. A test that documents which route works *and why the other
  cannot* is worth more than one that silently picks the survivor.

**Watch (cancellation rule, at the store's model axis):** in v1 `fit.py` computes
`design_info(t, mask)` **once**, before the candidate loop, so every design-derived outcome is
identical for every `m`. **A test asserting design-failure behaviour must vary the mask, never
the candidate.**

**`/warmstart/` is written but unread in 2a, so it needs its own guard:** assert a round trip
— the stored unconstrained `θ̂` reloads and maps back through the Bijector to the natural
parameters in `/noise/` — so 2c inherits a verified array instead of discovering the layout is
wrong underneath a feature that has its own bugs.

---

## Task 10 — the completion bitmap, write ordering, and SIGTERM

**Goal.** A tile's bit is set only after every array's region write for that tile has flushed.

**Behaviour.**

- **Write order is data-then-bitmap, always.** An interrupted run can never mark incomplete
  data complete.
- **No POSIX assumptions**: no file locking, no rename-based atomicity, no
  directory-listing-as-truth. Only per-object write atomicity.
- **SIGTERM flushes rather than dying mid-region-write.** Preemption is just resumption.

**Test.** *An interruption injected between the two writes leaves the bit unset*, demonstrated
by a fault-injection hook rather than by timing.

---

## Task 11 — the resume gate

**Goal.** The three outcomes, plus the positional candidate comparison.

**The entry contract, and the ordering is the guard:**

```
open → input contract (4a) → geometry fingerprint → fit_hash → resume gate → tiling
```

**Test the order, do not trust it.** A later change computing a hash before the contract check
would compute it from the config alone, which is where `data_uri`-as-proxy came from.

**Outcomes on a matching `fit_hash`:**

| what changed | outcome |
|---|---|
| nothing compat-relevant | resume: reuse completed tiles, fit the outstanding ones |
| a compat-relevant field that is not the criterion set | recompute derived arrays from stored primitives; do not refit |
| the criterion set | **refuse**, naming the stored set, the requested set, and the two resolutions |
| the `/detail/` selection | **refuse**: fixed at store creation |

**A quantity is recomputable iff it is a function of the stored primitives alone.** `log_lik`,
`k`, `n_eff` are stored; **the Hessian at the optimum is not**, so everything downstream of it
is fixed at creation.

**The candidate set is covered by no hash.** Compare spec hashes against root attrs
**positionally**: `stored[i] == requested[i]` for every `i < len(stored)`, and
`len(requested) >= len(stored)`. Refuse on the first mismatch, naming the index and both
hashes. **Do not "fix" this by adding `candidates` to the allowlist** — a hash expresses
equality and a superset must be permitted.

**Test.** *A different candidate at index 1 is refused.* Without the gate it writes candidate
B's fits into candidate A's slice: every array the right shape, every value finite, every
status `ok`, and the store wrong in a way no invariant catches. With unequal `p` it also
shifts every ragged offset, so the corruption lands in two arrays.

---

## Task 12 — `--reuse-fits-from`

**Goal.** Recompute derived arrays into a **new** store from an existing one's primitives,
without refitting.

**Behaviour.**

- Same tiling loop, same write path, same bitmap, same resume semantics; the fit step is
  replaced by a read.
- **Verify the source BEFORE the tiling loop:** `schema_version`, `fit_hash` against the
  requested config, and that the source's **completion bitmap is fully set**. Recomputing from
  a partially fitted store yields a complete-looking new store built on incomplete primitives
  — a plausible-number failure with no symptom. **An incomplete source is exit code 4.**
- **The new store writes its own provenance** — new `run_hash`, new `compat_hash`, `fit_hash`
  **equal to the source's** — and records the source's path and all three of its hashes as
  provenance fields, so a reader can verify the claim rather than trust the label.
- **Copies the groups it does not recompute.** A store that resolves through another fails the
  no-metamer read however the pointer is encoded.

**Tests.**

- *No fit ran*, proved by a **raising stub engine**, never by timing. **Put the stub in the
  shared fixtures** — the same construction proves the negative for "a resumed tile did not
  refit completed work" and "a compat-only rewrite touched nothing upstream of `/selection/`".
- *`fit_hash` equality across the two stores, asserted directly.* That equality is the entire
  claim the three-hash split makes; do not infer it from the recompute succeeding.
- *The new store opens with `xr.open_zarr` after the source is deleted.*

---

## Task 13 — the exit-criteria suite

Cross-process and cross-store properties no single task can express.

| # | criterion |
|---|---|
| 1 | Kill-and-resume (`kill -9` mid-tile) produces a **byte-identical** store |
| 2 | Bitwise-identical output across two memory budgets and two thread counts. **The budget half is currently trivial** — no cross-point dependency exists in 2a, every point is cold — and is pinned anyway because it stops being trivial in 2c, which inherits this criterion and must keep it green. **The thread-count half is not trivial even now:** a float64 reduction anywhere inside the `prange` over a tile would break it, and that is what it tests |
| 3 | The full store round-trips through plain `xr.open_zarr` **with metamer uninstalled** |
| 4 | The status/value invariant holds in both directions across a store containing every **reachable** branch, with one consolidated note for `SCREENED_OUT`, `CANDIDATE_DROPPED` and `NOT_APPLICABLE` naming what would make each reachable |
| 5 | The resume taxonomy, all five arms: recompute into a new store with no fit; criterion-set change refused; `fit_hash` mismatch refused; `/detail/` change refused; wrong-candidate-at-index-1 refused naming the index and both hashes; **and a source whose bitmap is not fully set refused with exit code 4** |
| 6 | Measured peak RSS matches the analytic per-backend formula at two or three tile sizes, against the **RSS-vs-B slope in a fresh process** |
| 7 | **A run at a formula-derived tile size, with `--memory-budget` set well below available RAM, completes with measured peak RSS at or below that budget.** The budget is the assertion; the machine is incidental. This catches a formula right per-series and wrong about what else is resident |
| 8 | The completion bitmap is never set ahead of the data, demonstrated by an interruption injected between the two writes |
| 9 | `geometry_hash` moves when the geometry changes and **does not** move on a value edit at fixed geometry |
| 10 | **Observed** thread limits match requested, **per library**; a mismatch is a layer-3 failure |
| 11 | The entry contract's ordering is tested, not trusted |
| 12 | The ragged builder is exercised with **both** extent functions, `p_m` and `p_m(p_m+1)/2` |
| 13 | A point where every fit is `OK` and one criterion cannot rank it, carrying NaN ΔIC beside an `OK` status |
| 14 | A point where candidate 1 fails and candidate 2 succeeds, `n_valid = 1`, weights renormalized over one survivor |
| 15 | **The recomputed store is self-contained**: it opens with `xr.open_zarr` with the source store deleted |
| 16 | **The recomputed store's `fit_hash` equals the source's, and its `compat_hash` and `run_hash` do not**, with the source's hashes recorded as provenance |

**Test hazards specific to this phase.**

- **Do not test tile-scale behaviour with a full fit.** `fit` costs ~5.4 s per series; a
  B=10⁴ fixture would take ~15 hours. Use a batched evaluation or a stub engine.
- **Filesystem and process state.** Anything depending on cwd, environment, file ordering or
  wall-clock is unstable across runs. Test across processes.
- **A new test that allocates raises the session watermark and can fail a test in another
  module.** P4's `run_spike` tests took the session watermark to 991.7 MB and a 400 MiB
  ballast in `test_memory.py` then moved it by exactly zero.

---

## What 2a does not do

Calibration tile and `--memory-budget` defaulting (2b, **gated by open question 12**);
two-pass warm start (2c); hysteresis audit (2d); run-level reporting, `metamer report`, early
abort and the mechanism that **produces** `CANDIDATE_DROPPED` (2e); the command tree,
`validate --explain`, profiles and `rich` (Phase 5).

**Measure in the phase that can, print in the phase that shows.** Read amplification, the
regressor regime with both tile sizes, and the unique-Δt count are computed and recorded into
provenance by 2a; `--explain` only prints them in Phase 5.
