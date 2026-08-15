# metamer Phase 2a — the vertical slice: config → input → tiling → fit → store → resume

**Written 2026-08-11**, from the Phase 2 brainstorm recorded in `PROGRESS.md`'s
*Phase 2 brainstorm — settled decisions* section and the design-doc amendments it produced.

**Read before starting, in this order:**

1. [`docs/superpowers/notes/phase1-to-phase2-handoff.md`](../notes/phase1-to-phase2-handoff.md)
   — the pre-flight (a0), (a1), (a)–(k) with (a2)–(a5), (c2), (c3), (g2), (i2)–(i8) and (k2), and
   the standing rules. **Read it there; this line is an index, not a copy.**
2. `PROGRESS.md`, whole file. The brainstorm section carries the reasoning behind every
   decision below; this plan carries only the decisions.
3. Design doc §9.4, §11.1, §11.1.1, §11.3, §12, §13, §14.3.

---

## Why this plan has no code fences

**Phase 1's plan carried full implementation fences, and they were the principal vector for
its defects.** Stated at its full strength: **across Tasks 8–17 the fence was wrong in every
task where a defect was found.** Not "mostly right with a bug" — the brief encoded a model
that omitted something, and its tests validated the omission. Task 15 bound cleanly against
every current signature and was wrong five ways; Task 16 bound cleanly and shipped a
serializer that hashed memory addresses. **Stating the bug each test must catch attacks
exactly that**, because a test written to catch a named defect cannot be satisfied by a
model that cannot produce it.

So each task below states **behaviour, invariants, interfaces, and for every test the bug it
must catch** — and stops there. The implementer writes the code and the tests. What replaces
the fence is the pre-flight, run against the task brief *before* any code, and the explicit
statement of what each test exists to falsify.

Interfaces are given as signatures where a later task calls into an earlier one, because
pre-flight (g) needs something to bind against. Bodies are not.

**The risk this creates, named so it is watched rather than discovered:** without a fence an
implementer has more freedom to satisfy a brief in a way the brief did not intend. Behaviour
plus invariants plus the named bug is the mitigation, and the standing requirement below is
the rest of it.

## Standing requirements for every task

- **Run the pre-flight against the task brief before writing code.** It lives in exactly one
  place — [`../notes/phase1-to-phase2-handoff.md`](../notes/phase1-to-phase2-handoff.md) §1 —
  and it has grown past what this plan was written against: **(a0), (a1), (a)–(k) plus (a2)–(a5), (c2), (c3), (g2),
  (i2)–(i8) and (k2), and five causes of a surviving mutation.** **Read it there rather than from any
  summary**, including this one; a restatement that drifts is worse than a single stale copy,
  and the two copies of it drifted once already. Append what each audit finds to
  [`../notes/phase2a-preflight.md`](../notes/phase2a-preflight.md).
- **`pixi run test && pixi run typecheck && pixi run lint` before every commit**, and
  `pixi run pre-commit run --all-files`. `pixi run test-fast` is for iteration only.
- **Mark new slow tests `slow` as they land.** Tests that assert machine-specific numbers
  are also `machine`.
- **Commit after every completed task.** One writer per working tree.
- **Every test states the behaviour under test and a concrete bug that would make it fail**,
  and its expected values are derived independently of the implementation.
- **Verify each test bites** by deleting the guard it protects.
- **If an implementation deviates from what the brief's interfaces imply, REPORT the
  deviation and why.** Phase 1's best findings came from implementers contradicting the
  brief — the `DesignInfo` narrowing contract, the fully-masked-tile precedence, the
  `_augment` block. **The point is to keep that visible, not to suppress it**, and a brief
  without a fence has more room for a silent one.

---

## Task index and dependencies

| # | task | depends on |
|---|---|---|
| 0 | Package skeleton for `metamer.batch` and `metamer.config`; new dependencies | — |
| 1 | The config model, `load()`, and the normalize/hash wiring | 0 |
| 2 | The opener registry, the zarr opener, and the time-axis contract (stage 4a) | 1 |
| 3 | `geometry_hash`: components, allowlist change, golden re-derivation | 1, 2 |
| 4 | Validation staging 1/2/3/4a, exit codes, `python -m metamer` | 1, 2, 3 |
| 5 | The thread budget: ownership, `threadpoolctl`, the observed-limits **check** | 0 (**Task 4 wires the check into layer 3** — see below) |
| 6 | Tiling: `tile_side` from budget, the tile iterator, read amplification | 2, 5 |
| 7 | The ragged index builder, generic over an extent function | 1 |
| 8 | The store schema: creation, groups, coordinate dtypes, provenance attrs | 1, 3, **7** |
| 9 | The tile write path and the status/value invariant | 6, 7, 8 |
| 10 | The completion bitmap, write ordering, and SIGTERM | 9 |
| 11 | The resume gate and its three outcomes | 3, 8, 10 |
| 12 | `--reuse-fits-from`: the recompute path | 9, 10, 11 |
| 13 | The exit-criteria suite | 1–12 |

**Task 13 is not a formality.** Six of the sixteen exit criteria are cross-process or
cross-store properties that no single task's tests can express.

**Two dependency corrections worth their reasons, because the obvious ordering is wrong in
both cases.**

- **The ragged builder is Task 7 and the store schema is Task 8, not the reverse.** The
  schema's coordinate arrays — `noise_param_{model,name,unit,transform}[P]` and both offset
  tables — **are the builder's output**, and creating the store requires `P_total` and the
  offsets. There is no cycle, because the builder is pure arithmetic over the candidate list
  and needs no store. But a table saying the builder depends on the schema leads an
  implementer to **stub the offsets in the schema task and fix them in the builder task**,
  and a stubbed offset table written into a store is exactly the class of thing that
  survives.
- **Task 5 exposes the observed-limits check; Task 4 wires it into layer 3.** The check is
  specified as a *layer-3 validation failure*, and the staging is Task 4 — so Task 5 could
  otherwise be implemented before the layer it reports into exists, and **the check would
  ship as a bare exception with no layer attached**, satisfying exit criterion 10 with
  something that is not a layer-3 failure. Task 5 stays parallelizable against Task 0; the
  wiring is Task 4's, and it is stated in both briefs.

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

**Also in this task: the raising stub engine, as a NAMED shared test fixture.** It raises if
`score` is called, and it is the only honest way to prove a negative — **timing cannot
falsify "no fit ran"; a raising stub can.** Named here with its consumers listed, so it is
not written narrowly for one caller and re-invented twice:

| consumer | the negative it proves |
|---|---|
| Task 12 | the recompute path ran no fits |
| Task 11 | a resumed run did not refit tiles the bitmap says are complete |
| Task 11 / 12 | a compat-only rewrite touched nothing upstream of `/selection/` |

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
  candidates by spec hash, criterion/objective compatibility, the identifiability lint as
  a warning, **and Task 5's observed-vs-requested thread-limit check, wired in here.** Task 5
  exposes that check; **this task is what makes it a layer-3 failure rather than a bare
  exception**, and exit criterion 10 is satisfied only by the wired form.
  **The staging is the structure; the checks accrete.**
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
  **This task EXPOSES the check; Task 4 wires it into layer 3.** Stated in both briefs,
  because otherwise this task can be finished before the layer it reports into exists and the
  check ships as a bare exception with no layer attached — which would satisfy exit criterion
  10 with something that is not a layer-3 failure.
- **`machine_fingerprint`'s ARGUMENTS COME FROM `core.machine`, NEVER FROM THE CONFIG.**
  It takes `cpu_model`, `cores` and `total_ram_bytes` as parameters, so it is self-reported at
  its own boundary. That is harmless while it reaches `run_hash` alone — provenance, never a
  gate — and it becomes an **identity** the moment §11.4's calibration cache key reads it: a
  config-supplied fingerprint would let one machine's calibration be reused on another, which
  understates peak against a hard RAM constraint. Wire it from the platform here, before the
  cache exists, because retrofitting it means invalidating whatever the cache already holds.
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

**Forward note — the coarse-grid stride is defined here later, and it has FIVE downstream
consumers.** 2a has no pass 1, so nothing in this task defines a stride; but this is where it
lands in 2c, and nowhere else records the consumer list:

| # | consumer | section |
|---|---|---|
| 1 | the coarse warm-start source | §11.1 |
| 2 | the calibration-tile RSS measurement | §11.4 |
| 3 | the early-abort evaluation — stratified by construction, unlike a tile prefix | §14.1 |
| 4 | the **cold** reference for the hysteresis audit | §11.2 |
| 5 | the default `/detail/` subsample — the audit wants covariances at cold-fitted points | §12.2 |

**A later change to pass 1's stride or membership touches all five.**

**Tests.** *Tile geometry covers the grid exactly once, including ragged edge tiles* —
catches a store with an unwritten seam. *Read amplification is >1 for a deliberately
misaligned tile and 1 for an aligned one* — catches the metric being computed from the
request rather than the read.

---

## Task 7 — the ragged index builder

**Goal.** One builder, generic over a **per-model extent function**, not a per-model
parameter count. **Pure arithmetic over the candidate list; it needs no store**, which is
why it precedes the schema rather than following it.

**Behaviour.** `/noise/` uses `p_m`; `/detail/` will use `p_m(p_m+1)/2`. **Both offset tables
are stored as coordinate arrays, not derived at read time**, so a no-metamer read can slice
either without knowing the triangular formula. A covariance, when `/detail/` lands, is the
**packed lower triangle with its storage order in attrs**.

**Test the builder with BOTH extent functions now, even though `/detail/` is unwritten** —
`P_total = 4` against `1 + 6 = 7` at the M=2 fixture. **A design that reuses one table looks
correct at equal `p` and is wrong at unequal `p`**, which is the reason the fixture has
unequal `p` at all.

**CORRECTED 2026-08-12 DURING THE TASK, TWICE OVER.** This brief said `4 + 6 = 10`, as did
design doc §12.3 and `PROGRESS.md`. **10 is `P_total(P_total+1)/2`, the triangle of the
flattened total — the very error the sentence above warns about.** And the fixture it
prescribes **cannot see a reused offset table at all**: `p = 1` and `p = 0` are the fixed
points of `p ↦ p(p+1)/2`, so with `white` first both offset tables are `(0, 1)`. Put a model
with `p ∉ {0, 1}` first to discriminate.

---

## Task 8 — the store schema

**Goal.** Store creation with every group except `/detail/`, and provenance.

**Depends on Task 7**, whose builder produces the coordinate arrays and both offset
tables this task writes. **Do not stub the offsets here** — a stubbed offset table that
reaches a store survives.

**Layout.** `/signal/`, `/primitives/` (including `iterations` uint16), `/selection/`,
`/noise/`, `/status/`, `/warmstart/`, `/completion/`. **`/detail/` is not created** — an
uncreated group is a cleaner deferral than an empty one.

**AMENDED DURING THE TASK, 2026-08-12.** `/primitives/` also carries **`n`**, which §12.2 and
this brief both omitted: `rank_candidates` reads `loglik`, `k`, `n` and `n_eff`, and without
`n` stored, Task 12 must reopen the input and recount the mask — the condition the handoff
names as fatal to §12.8. Every fill value is a value the write path cannot produce (`OK` is
code 0 and zarr's default fill is 0, so the default makes an empty store read as a wholly
successful run, with byte-identical contents); `iterations` is exempt from the status/value
invariant because a uint16 has no NaN; the label coordinates use the v3-specified `string`
dtype rather than §12.4's `S32`, which zarr-python declares unstable; and every group carries
its own label coordinates plus `y`/`x`, because each is opened separately.

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

## Task 9 — the tile write path and the status/value invariant


**TASK 9 OWNS THE SIGNAL-TERM PARSER, ADDED 2026-08-12 AFTER TASK 6 HIT IT.** `signal_terms` is
a tuple of strings in the config and **nothing in the tree maps them to `core.signal` classes**:
`config.candidates.parse_candidate` resolves *noise* terms through `kernel_registry`, and
`core.signal` has the term classes with **no registry and no parser**. The consequence found at
Task 6 is that `k_beta` — the design column count — is unobtainable, so **no tile can be sized
and `run()` cannot iterate tiles**. What is needed: a signal-term registry and a parser mapping
config strings to `core.signal` terms, yielding a `SignalSpec` and hence `k_beta`. **Task 9 is
where it belongs** because this is the first task that fits and therefore needs the design
itself, and because deciding the signal vocabulary — which terms exist, how a parameterized one
(`offset:2005.5`, a rate change, a named regressor) is spelled — inside a task about tiling or
about a store schema is the worst available place to decide it. Tasks 7 and 8 are unaffected:
`P_total` and both offset tables come from the **candidate** list, which `Config.process_specs()`
already resolves.
**Goal.** One region write per array per tile, with the invariant wired through **every**
write path.

**TASK 9 BUMPS `store.SCHEMA_VERSION`, AND THE COUPLING IS NOT OPTIONAL.** Adding
`SCREENED_OUT` and `NOT_APPLICABLE` to `Outcome` changes the store's stored code meanings and
the `flag_values` / `flag_meanings` legend written into `/status/` at creation, and
`outcomes._CODES`'s own docstring already carries that rule. Task 8 deliberately did **not**
add the members: their `is_failure` and `is_eligible` semantics belong to the task that owns
the failure-rate denominator, and adding a member without deciding those is a name with no
gate.

**AND `iterations` IS EXEMPT FROM THE INVARIANT.** A uint16 has no NaN; its "no fit ran"
value is 65535. Name the exemption in the invariant check rather than rediscovering it.

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

- **A point where candidate 1 fails and candidate 2 succeeds.** `n_valid = 1` there, and the
  weight vector renormalizes over one survivor, **which is the case that reads as confident
  selection and is not.** ~~The offset-inside-a-gap construction, a breakpoint with no support
  for one candidate's design~~ — **CORRECTED 2026-08-13: that cannot work, and the "Watch"
  paragraph below says why.** In v1 the design is shared and built once before the candidate
  loop, so a design failure hits every candidate and gives `n_valid = 0`. The reachable
  construction is an **optimizer-stage** failure, **and must be one until joint signal x noise
  search lands**: `white + matern12` fitted to white noise is degenerate at most points while
  `white` fits (measured: 3 of 4). **This is pre-flight (a5)** -- the brief's own "Watch"
  paragraph forbade the fixture the brief required, two paragraphs apart.
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

**AMENDED 2026-08-13, ON IMPLEMENTING IT. Three things this brief did not say, and Task 11
inherits all three.**

- **The bit's *index* is a gate made of a name, and it is reachable today.** `ty` is
  `y_start // tile_side`, and `tile_side` comes from `memory_budget_gb` — run-relevant, so in
  **neither** gate, deliberately, so that §15.5's burst-to-cloud resume works. A resume at a
  different budget therefore re-tiles the grid and every bit names a different region.
  Refusing a budget change breaks the workflow the exclusion exists for, so the rule is over
  the **derived side**: equal, proceed; **stored < derived, adopt the stored side**; **stored >
  derived, refuse** naming both sides and the store's recorded budget.
  `completion.resume_tile_side` sits between the hashes and the tiling — **the resume gate's
  position, which Task 11's comparisons now join rather than establish.**
- **The two behaviours above prescribe opposite treatments of the same window**, and are
  consistent only because the handler *records and returns*: the flag is read after the bit,
  between tiles. A raising handler would land in the window the fault-injection test protects.
- **A flushed SIGTERM exits `ABORTED_EARLY` (2)**, which is §14.3's "aborted early —
  resumable". That gives code 2 its first producer, ahead of 2e's early-abort mechanism;
  `validation.ExitCode`'s docstring said it had none and is amended.

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
| ~~a compat-relevant field that is not the criterion set~~ | ~~recompute derived arrays from stored primitives; do not refit~~ — **NO PRODUCER, corrected 2026-08-13** |
| the criterion set | **refuse**, naming the stored set, the requested set, and the two resolutions |
| a strict superset of the candidate set | **refuse**, naming the resolution — **added 2026-08-13** |
| the `/detail/` selection | **refuse**: fixed at store creation |

**CORRECTED 2026-08-13, BEFORE IMPLEMENTING. `COMPAT_RELEVANT_FIELDS` is
`FIT_RELEVANT_FIELDS | {"criteria"}`**, measured, so *"`fit_hash` matches and `compat_hash`
differs"* **is** "the criterion set changed" and the recompute row has no reachable input.
Design doc §12.8 carries that finding already, dated 2026-08-11, and this brief did not
follow it. **Task 11 therefore implements no recompute**; the recompute path is Task 12's,
into a new store. An unrecognized compat difference is refused explicitly rather than falling
through, so the arm a later compat-only field would reach is declared rather than assumed.

**AND THE `/detail/` REFUSAL HAD NOTHING TO READ.** `provenance_attrs` did not record the
selection, so that arm was a name with no gate. `detail` is now a required root attr and
`store.SCHEMA_VERSION` is **3**.

**AND A STRICT SUPERSET IS REFUSED IN PLACE**, which §12.8 permitted until 2026-08-13: it
resizes `m` and `p` — the argument that refuses a criterion-set change — **and the completion
bitmap has no model axis**, so a tile cannot be complete for some candidates and outstanding
for others. `len(requested) >= len(stored)` stays *necessary and not sufficient*, and the two
faults get different messages.

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

**AMENDED 2026-08-13, ON IMPLEMENTING IT.**

- **The source check is NOT `check_resume`.** That gate refuses a criterion-set change,
  which is the reason this command exists; reusing it wholesale makes the feature refuse its
  own primary use. `resume.check_source` shares schema version, `fit_hash` and the positional
  candidate comparison, adds *bitmap fully set*, and omits `criteria`, `compat_hash` (which
  is `fit_hash` plus the criterion set) and `/detail/` (2a creates no such group; **the
  regime is declared** for the task that does).
- **The new store's tile side is READ BACK from the source**, not re-derived from the budget:
  byte-identical copied groups need identical shard geometry, and the budget rule bounds a
  *fit's* resident set. Consequence stated rather than discovered — the new store carries the
  source's tile side.
- **The copy is derived from the source's own array listing, by dimensions**, so a schema
  addition is copied without anyone remembering it.
- **`write.write_selection` is now shared** by the fit and recompute paths, so `/selection/`
  has one producer rather than two that were written to agree.

**Tests.**

- *No fit ran*, proved by the **raising stub engine defined in Task 0**, never by timing.
  Do not define a local one — Task 0 lists its three consumers precisely so it is written
  once.
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
| 3 | The full store round-trips through plain `xr.open_zarr` **with metamer uninstalled**, and **"plain" means WARNING-FREE**: "it opened" and "it opened cleanly" are different acceptance bars and only the second means self-describing. An unconsolidated store opens and warns, telling the reader to pass a keyword |
| 4 | The status/value invariant holds in both directions across a store containing every **reachable** branch, with one consolidated note for `SCREENED_OUT`, `CANDIDATE_DROPPED` and `NOT_APPLICABLE` naming what would make each reachable |
| 5 | The resume taxonomy, all five arms: recompute into a new store with no fit; criterion-set change refused; `fit_hash` mismatch refused; `/detail/` change refused; wrong-candidate-at-index-1 refused naming the index and both hashes; **and a source whose bitmap is not fully set refused with exit code 4** |
| 6 | Measured peak RSS matches the analytic per-backend formula at two or three tile sizes, against the **RSS-vs-B slope in a fresh process** |
| 7 | **A run at a formula-derived tile size, with `--memory-budget` set well below available RAM, completes with measured peak RSS at or below that budget.** The budget is the assertion; the machine is incidental. This catches a formula right per-series and wrong about what else is resident |
| 8 | The completion bitmap is never set ahead of the data, demonstrated by an interruption injected between the two writes |
| 9 | `geometry_hash` moves when the geometry changes and **does not** move on a value edit at fixed geometry |
| 10 | **Observed** thread limits match requested, **per library**; a mismatch is a layer-3 failure |
| 11 | The entry contract's ordering is tested, not trusted |
| 12 | The ragged builder is exercised with **both** extent functions, `p_m` and `p_m(p_m+1)/2`, **on a fixture that discriminates them.** The M=2 store fixture does NOT: `p = 0` and `p = 1` are the fixed points of `p ↦ p(p+1)/2`, so `white` first gives `(0, 1)` under both. Use `matern32` first — `(0, 2)` against `(0, 3)` — or M=3 `white / white + matern12 / matern32` — `(0, 1, 4)` against `(0, 1, 7)`. See pre-flight (i7) |
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

## Exit criteria — the closing table (2026-08-14)

**Checked by `tests/test_exit_criteria.py`**, which drives from outside the code that
satisfies each property wherever an outside exists: a killed subprocess, a store read back
from disk, a plain `xr.open_zarr` in an environment where metamer is genuinely absent.

| # | criterion | verdict |
|---|---|---|
| 1 | kill-and-resume is byte-identical | **met** — `kill -9` mid-run, resumed, every file's SHA-256 equal to an uninterrupted run's |
| 2 | bitwise-identical across two budgets and two thread counts | **met**, and the budget half is **trivial today**: no cross-point dependency exists in 2a. It stops being trivial in 2c, which inherits this criterion |
| 3 | plain, warning-free `xr.open_zarr` with metamer uninstalled | **met** — subprocess, `PYTHONPATH` stripped, `find_spec` control inside the child, warnings promoted to errors |
| 4 | the status/value invariant, both directions | **met** — the same function the write path uses, over the finished store read back from disk |
| 5 | the resume taxonomy, all arms | **met** — criterion set, `fit_hash`, `/detail/`, wrong candidate at index 1 naming the index, an incomplete source at exit code 4, and the recompute with no fit |
| 6 | peak RSS against the analytic formula at two or three tile sizes | **met with reduced scope** — measured in a fresh process at two tile sizes and asserted not to track the grid. The criterion is about a 10⁷-point run; this suite fits four series, and peak RSS is dominated by the interpreter at that scale |
| 7 | a run under a budget well below available RAM stays under it | **met with reduced scope**, same reason. **What would close both: one run at 10⁶–10⁷ points with the RSS-vs-B slope measured in a fresh process** — 2b's calibration tile is the natural place |
| 8 | the bitmap is never set ahead of the data | **met** — Task 10's injected fault chooses the moment; the suite checks the resulting invariant over a store killed at a moment nobody chose |
| 9 | `geometry_hash` moves with the geometry, not with a value edit | **met** — both halves through `run`, not through the hashing function |
| 10 | observed thread limits match requested, per library | **met** — the run observes; the mismatch arm uses the injection seam, since this machine cannot produce one |
| 11 | the entry contract's ordering is tested | **met** — a config that fails stage 4a **and** would fail the gate reports layer 4 |
| 12 | the ragged builder with both extent functions, on a discriminating fixture | **met** — M=3 `white / white + matern12 / matern32`: `(0, 1, 4)` against `(0, 1, 7)` |
| 13 | a point `OK` under every fit that one criterion cannot rank | **met** — REML, `n = 2`, HQIC undefined beside an `OK` status |
| 14 | a point with one surviving candidate, weights renormalized | **met** — `n_valid = 1` from an optimizer-stage failure |
| 15 | the recomputed store is self-contained | **met** — source deleted, opened in a subprocess without metamer |
| 16 | the recomputed store's `fit_hash` equals the source's; `compat_hash` and `run_hash` do not | **met** — with the source's three hashes recorded as provenance |

**Nothing is deferred.** Two are met with reduced scope, both for the same reason and both
with the same closer.

---

## What 2a does not do

Calibration tile and `--memory-budget` defaulting (2b — ~~gated by open question 12~~
**question 12 closed 2026-08-12, planned 2026-08-14 in
[`2026-08-14-metamer-phase2b.md`](2026-08-14-metamer-phase2b.md)**);
two-pass warm start (2c); hysteresis audit (2d); run-level reporting, `metamer report`, early
abort and the mechanism that **produces** `CANDIDATE_DROPPED` (2e); the command tree,
`validate --explain`, profiles and `rich` (Phase 5).

**Measure in the phase that can, print in the phase that shows.** Read amplification, the
regressor regime with both tile sizes, and the unique-Δt count are computed and recorded into
provenance by 2a; `--explain` only prints them in Phase 5.

**And 2a defines no coarse-grid stride, which is the thing 2c's pass 1 will add.** Its five
downstream consumers are listed in Task 6's forward note rather than left to be rediscovered:
warm-start source, calibration measurement, early-abort evaluation, cold audit reference, and
the `/detail/` subsample default.
