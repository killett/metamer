# metamer Phase 2b — the memory formula, the floor, the calibration tile, and `--memory-budget`

**Written 2026-08-14**, from the Phase 2b brainstorm recorded in `PROGRESS.md`'s *Phase 2b
brainstorm — settled decisions* section. Sub-phase 2a is complete: Tasks 0–13, sixteen exit
criteria met, two with reduced scope. **This plan closes those two.**

**Read before starting, in this order:**

1. [`docs/superpowers/notes/phase1-to-phase2-handoff.md`](../notes/phase1-to-phase2-handoff.md)
   §1 — the pre-flight. It has grown during this brainstorm and now carries **(a0), (a1),
   (a6), (a7), (a)–(k) with (a2)–(a5), (c2), (c3), (g2), (i2)–(i9), (j2), (j3) and (k2)**, the
   five causes of a surviving mutation, and the standing rules. **Read it there; this line is
   an index, not a copy.** (a7) and (a4)'s third register were promoted out of Task 0,
   2026-08-15.
2. `PROGRESS.md`, whole file. Its 2b brainstorm section carries the reasoning behind every
   decision below; this plan carries only the decisions.
3. Design doc §9.4, §11.1, §11.1.1, §11.3, §11.4, §11.5, §12.7, §13.3, §13.4, §15.5.

---

## Why this plan has no code fences

Unchanged from 2a, and 2a's outcome is now evidence rather than argument. Phase 1's plan
carried full implementation fences and **the fence was wrong in every task where a defect was
found** — a brief-generated test validates the brief's model of the problem, so it cannot
detect that the model omitted something. 2a stated behaviour, invariants, interfaces and, for
every test, the bug it must catch; every task found defects in its own brief and none of them
was a transcription error.

Interfaces appear as signatures **only where a later task binds against an earlier one**,
because pre-flight (g) needs something to bind against. Bodies do not.

---

## What this sub-phase found before it started, and why its shape is not the brief's

The pre-flight was run against 2b's inherited brief — PROGRESS.md's *WHAT SUB-PHASE 2b
INHERITS*, design doc §9.4/§11.1/§11.4, and the live code — **before** any of the tasks below
were written. It found four defects, and they are the reason this plan begins with a
correction task rather than with the calibration tile.

**THE MAGNITUDES LIVE IN EXACTLY ONE PLACE AND IT IS NOT HERE.** `PROGRESS.md`'s
**What 2b's first tasks inherit** section carries every measured and hand-recomputed number
below — the floor ladder, the formula's error terms, the tile-side cascade's site count, the
divisor measurement, and the three closure boundaries — each dated and each a claim to
re-measure. **This section states the structural findings**, which are verifiable by reading the
source rather than by measuring, and points there for the sizes. Two copies of a measurement
drift the moment one is updated; this project has paid for that four times.

### F1 — nothing maps the budget to `block_bytes`, and exit criterion 7 is unsatisfiable because of it

Design doc §11.1 derives the tile from **`block_bytes`**:
`tile_side = sqrt(block_bytes / resident_bytes_per_series)`. `run.py:348` passes
`int(config.memory_budget_gb * 1024**3)` in as that argument. **So the budget *is* the block,
and nothing in any document defines the mapping between them.**

Exit criterion 7 asserts **peak RSS** at or below the budget, and a tile sized to the whole
budget leaves nothing for the interpreter, which holds hundreds of MB before a tile exists. The
criterion is met today only because the suite fits four series; at any tile size where the tile
is the dominant term it fails, and **it fails by the floor rather than by the formula**.

**Settled:** `--memory-budget` bounds **process peak RSS**.
`block_bytes = budget − floor − headroom`. A budget at or below the floor is refused, naming
the floor, its components, and a budget that would work.

### F2 — the formula describes the batched trust-region that Task 19 deleted

`fit.py:223` is `for b in range(batch): optimize_series(obj, y[b:b+1], mask[b:b+1], t, one, warm, max_iter)`.
So `P`/`F`/`Q`/`P∞` and the workspace copies, the augmented row, the normal-equation
accumulators, the optimizer workspace and the Hessian are **live for one series at a time**.
`memory.bytes_per_series` multiplies all of it by B.

Design doc §9.4's path-A shape `B × (… + c_A(d, k_β, p))` was correct for the **batched
trust-region of §8.3**, which the stage-1 spike deleted (Task 19, deleted not deferred, under
the ≥3× rule). The deletion was right, was recorded, and **the formula describing the deleted
architecture went with neither.**

**And the measurement that validated it validated a different workload.**
`memory.measure_evaluation_rss_slope` drives `objective.unconstrained_loglik(u, y, mask, t, design)`
on a **batch of B**, which genuinely does hold `B × (d²…)`. The instrument was sound, the
formula was sound for what the instrument did, and neither described the production path.
This is (j2), promoted during this brainstorm.

### F3 — and the output-slot term is understated, in the dangerous direction

`fit` preallocates and holds until the tile write, per `(series, candidate)`: `theta`,
**`theta_unconstrained`** and `theta_err` at `p_max` each; `beta` and `beta_err` at `k_beta`
each; `loglik`, `k`, **`n`**, `n_eff_bic`, `n_eff_trend` as float64; `outcome` as uint8;
**`init_rung` as an `object` array** — one pointer per cell; and **`n_iter` as int64**, not
the uint16 the formula charges.

`out(M, p, k_β) = M(2p + 2k_β + 4)×8 + 3M` names none of the three emphasized.

**F2 and F3 have opposite signs and partially cancel**, which is why neither has been noticed.
That is (a) inside a sum: **verify each term, never the total.**
That is the cancellation rule (a) inside a sum: two errors of opposite sign are invisible to
any check on the total. **Verify each term, never the total.**

### F4 — `Backend` names two architectures and production has neither

`CompiledEngine._filter_batch` does `for b in prange(batch)` and allocates
`(batch, n_cols, n_cols)`, so path B's shape is realized **inside `score`, at whatever B
`score` is given** — and `fit` gives it `y[b:b+1]`. **B = 1.** Through `run()` the compiled
engine pranges over a batch of one: no parallelism, one thread's state, the same resident
shape as the Kalman engine. Path B's `B × (data + out) + T × c_B` is realized only by
`bench/spike.py`, which has its own driver.

**Two engines, one production shape.** Corrected, the two placements differ **in a constant,
not in the slope**: `1 × c` against `T × c`, both independent of B. §9.4's *"the formulas have
different shapes, not just different constants"* was true of the two designs and is false of
the code.

**The consequence that keeps the distinction alive rather than deleting it:** the day a driver
hands an engine a real batch, the engine's own workspace becomes a per-series term and **it is
engine-dependent** — `CompiledEngine` allocates `accum`, `sum_log_s`, `n_used` and `degenerate`
per series, and a batched `KalmanEngine` would hold its `(B, d, d)` block. So the placement
belongs in the calibration key **before** the driver that needs it exists, on Task 16's
`shared_with` precedent: *unreachable today is never a reason to leave an identity function
incomplete.*

**And `EngineId` must not be reused for it.** `CompiledEngine.engine_id` is `EngineId.KALMAN`
deliberately, because the two compute the same likelihood by the same recursion and must stay
rankable against each other. **`EngineId` answers "are these scores comparable"; the
calibration key asks "do these engines cost the same". They give different answers for the
same pair**, so the key carries a memory-relevant engine label of its own.

### What the four findings do to the published number

**The published `tile_side` moves, and the step-by-step recomputation is in `PROGRESS.md`'s
inherit section.** Two properties of it belong here, because they govern how the tasks are
read:

- **The side gets SMALLER at the same nominal budget, and that is the correct direction.**
  Recorded so it is not read as a regression when Task 2 lands.
- **This is the FOURTH instance of this project's design-doc cascade**, after `n_eff_*`'s
  `[y,x]`, the output-slot `+2`, and §11.1's superseded `tile_side` formula. **Task 9 exists so
  there is not a fifth**, and its repair is a test rather than a sweep.

---

## Standing requirements for every task

- **Run the pre-flight against the task brief before writing code.** It lives in exactly one
  place — [`../notes/phase1-to-phase2-handoff.md`](../notes/phase1-to-phase2-handoff.md) §1 —
  and **read it there rather than from any summary, including this one.** Append what each
  audit finds to [`../notes/phase2b-preflight.md`](../notes/phase2b-preflight.md), **before**
  the task rather than after.
- **`pixi run test && pixi run typecheck && pixi run lint` before every commit**, plus
  `pixi run pre-commit run --all-files`. `pixi run test-fast` is for iteration only — a green
  fast run is **not** evidence a task is done. The full sweep has twice caught what a task's
  own tests could not.
- **Mark new slow tests `slow` as they land**; anything asserting a machine-specific number is
  also `machine`. **2b produces more of both than any previous sub-phase** — every RSS
  measurement here is machine-specific by construction.
- **Every test states the behaviour under test and a concrete bug that would make it fail**,
  with expected values derived independently of the implementation. **Verify each test bites**
  by deleting the guard it protects. **Enumerate every return and raise; never assert a count.**
- **Commit after every completed task.** One writer per working tree. Never `git reset` a
  branch whose commits are pushed.
- **Two changes that could each explain a wrong result land in separate commits.** Promoted
  during this brainstorm and it governs the Task 0/1/2 split specifically.
- **If an implementation deviates from what a brief implies, REPORT the deviation and why.**
  Every substantive finding this project has is one an implementer produced by contradicting a
  brief.

---

## Task index and dependencies

| # | task | depends on |
|---|---|---|
| 0 | The memory formula corrected — F2, F3 and F4 together | — |
| 1 | The floor: measured post-warm, input open, per run; cgroup-aware total RAM; `tile_side_basis` and `SCHEMA_VERSION` 4 | 0 |
| 2 | `block_bytes = budget − floor − headroom`, and the smooth-base rounding | 0, 1 |
| 3 | The `--memory-budget` default and the unset sentinel | 1, 2 |
| 4 | The calibration measurement | 0, 1, 2, **3** |
| 5 | The calibration cache | 4 |
| 6 | The resume refusal that names calibration | 1, 2, 5 |
| 7 | Criterion 6's instrument — the linearity claim | 4 |
| 8 | Criterion 7's run, and accumulation via `--reuse-fits-from` | 2, 7 |
| 9 | The five-site cascade amendment | 7, 8 |
| 10 | The 2b exit-criteria suite | 0–9 |

**Three dependency decisions worth their reasons.**

- **Tasks 0, 1 and 2 stay apart even though they are one arithmetic path.** Task 0 is
  falsifiable **without any measurement**; Task 1 is a measurement **with no consumer**; Task 2
  is the arithmetic that joins them. Collapsed, the corrected formula would first be exercised
  through a floor that is itself new, and a wrong number at the end could be blamed on either.
  **Attribution is a property of the sequence, not of the diff** — the same argument that keeps
  the golden reversal a chain of one hop per allowlist change, and that recorded the
  271 → 307 s sweep step as undecomposed rather than explaining it.
- **Task 4 depends on Task 3**, which is not obvious. The calibration is a **capped run of the
  production path**, so it goes through `run()`, so it resolves the budget. Landing it before
  Task 3 forces the calibration to construct a budget directly — **diverging from the
  production derivation, which is F2's exact failure** — or to be rewritten at Task 3.
- **The schema change is in Task 1, not at the end.** `tile_side_basis` is a store field and
  `SCHEMA_VERSION` 4 invalidates 2a-written stores. Tasks 2–5 all write stores; landing the
  bump late means every fixture store built in between is rebuilt and every test that pinned a
  version is re-pointed rather than written correctly once. The **field** precedes its
  **diagnostic**: Task 6 adds the refusal that reads it.

---

## Task 0 — the memory formula corrected

**Goal.** `metamer.core.memory` describes the code that exists. No calibration, no floor, no
measurement — this task is falsifiable by reading and by arithmetic alone, which is why it is
first and alone.

**Behaviour.**

- **Solver state is a constant, not a slope term.** Everything `optimize_series` allocates is
  live for one series at a time (F2). The corrected shape, one formula with a **placement**
  parameter:

      resident = B × (N×9 + X_term + out(M, p_max, k_β)) + placement_constant

  where `placement_constant` is `1 × c` for the loop that exists and `T × c` for a driver that
  pranges over series. **The two placements differ in a constant, not in the slope** — say so
  in the docstring, because §9.4 says the opposite and §9.4 was describing two designs.
- **`out(...)` equals what `fit` preallocates and holds until the tile write**, term by term:
  `theta`, `theta_unconstrained`, `theta_err` at `p_max`; `beta`, `beta_err` at `k_beta`;
  `loglik`, `k`, `n`, `n_eff_bic`, `n_eff_trend` float64; `outcome` uint8; `init_rung` an
  **object** array at one pointer per cell; `n_iter` **int64**. **`p_max`, not `p_m`** —
  `fit.py:186` sizes every candidate's slot to the widest.
- **`Backend` is deleted, not aliased.** It is replaced by a placement enum with one production
  value and one declared-unreachable one. Keeping it as an alias would be the very defect (a6)
  names — a description outliving its referent.
- **The calibration key's engine label is not `EngineId`.** F4's argument: `EngineId` is
  deliberately shared by both engines so their scores stay rankable, and memory is a different
  question about the same pair.
- **The standing check becomes a two-sided band.** *"Treat any factor above ~1.5× as a missing
  term"* would have passed F2, F3 and F4. A measured slope **materially below** the formula is
  equally a finding: the formula charges for something the code does not hold, and the excess
  capacity hides whatever else is wrong.

**Invariants.**

- **Everything `optimize_series` allocates has leading dimension 1.** This is a **shape
  assertion standing in for a byte measurement**, and it is stated as such rather than
  presented as a measurement: at B = 50 the difference between "constant" and "per-series" is
  53 kB against a 221 MB floor, and at any B where it is measurable the run is not affordable.
  It fails the moment someone batches the optimizer, which is the change that would make the
  term per-series and is what §8.3 originally specified.
- **The batched placement is unreachable through `run()`**, asserted directly. An unreachable
  branch with no reachability assertion becomes reachable silently.

**Interfaces** (Tasks 2, 4, 5 and 7 bind against these):

    memory.SolverPlacement          # StrEnum: PER_SERIES_LIVE | PER_THREAD
    memory.solver_state_bytes(placement, *, d, k_beta, p, threads) -> int
    memory.output_slot_bytes(n_models, p_max, k_beta) -> int
    memory.resident_bytes_per_series(*, placement, d, k_beta, p_max, n_time,
                                     n_models, per_point_design=False) -> int
    memory.resident_tile_bytes(*, batch, placement, threads, d, k_beta, p_max,
                               n_time, n_models, per_point_design=False) -> int

> **AMENDED 2026-08-15, BY THE IMPLEMENTATION, AND THE DEVIATION IS REPORTED RATHER THAN
> ABSORBED.** `resident_bytes_per_series` shipped **without `placement` and without `d`**: under
> this task's own correction the per-series figure depends on neither, since `d` reaches the
> formula only through the solver state and the solver state is not per-series. A signature
> keeping them asserts a dependence the formula denies. They stay on `solver_state_bytes` and
> `resident_tile_bytes`, and Task 2's `tile_side_for` keeps them correctly. `solver_state_bytes`
> takes `p_max` rather than `p`, for the same reason `output_slot_bytes` does — the constant must
> bound the widest candidate. Two more names landed that this list does not have:
> `memory.MemoryEngineLabel` / `memory_engine_label(engine)`, which Task 5's `cache_key` binds
> against, and `memory.slope_band`, which is the two-sided check in executable form.

**Tests, and the bug each catches.**

- *The output-slot term equals a hand-built inventory of what `fit` preallocates, asserted
  **field by field** rather than as a total.* Catches F3 recurring: a total is exactly what F2
  and F3 hid inside, and a per-field assertion is the (a) repair.
- *`resident_tile_bytes` does not grow with B in its solver term.* Catches the F2 defect
  directly — the mutation is multiplying `solver_state_bytes` by `batch`, and it must bite.
- *Everything `optimize_series` allocates has leading dimension 1*, exercised through a real
  one-series call. Catches a later batching of the optimizer silently making the constant a
  slope term.
- *The batched placement is not reachable through `run()`.* The **pure negative**, so it needs
  (i2)'s positive control: the same placement **is** reachable when constructed directly, and
  the arithmetic for it is asserted against hand-computed values. Without the pairing, "not
  reachable" is satisfied by a branch that cannot be reached at all because it does not work.
- *Both placements agree on the slope and differ only in the constant.* Catches someone
  "restoring" §9.4's two-shape claim, and it is the executable form of F4.
- *A per-point `DesignInfo` still branches the formula*, per Q7's 2a precedent — the regime
  ships tested even though the feature is refused. Catches the per-point branch rotting while
  unreachable, and keeps the two deferrals consistent.

**Watch.** `Backend` is imported by `batch/tiling.py` and `batch/run.py`. Removing it is a
signature change those tasks bind against, so (g) is live here rather than clean.

> **CORRECTED 2026-08-15: FOUR `src/` IMPORTERS, NOT TWO.** `batch/tiling.py`,
> **`batch/validation.py`**, `batch/run.py` and **`bench/spike.py`**, plus three test modules.
> `bench/spike.py` is the one that matters beyond a count — it is the only prange-over-series
> driver in the tree and the only caller of `bytes_per_series` outside the tests, and it sits on
> the far side of the `bench/`-versus-`core` layering question this plan records as still owed.
> And a **fifth defect (F5) was in the same function as F2**: the optimizer term described §8.3's
> deleted trust-region as well, and understated the constant 11.3×. See `PROGRESS.md`.

**And this task breaks live assertions on the published tile side** — `test_memory.py:582`,
`test_tiling.py:188`, `test_validation.py:391` and `:429` pin 338 and 186. **They are correct
to fail.** Re-derive each expected value **by hand** from the corrected formula and record the
derivation beside it; **do not paste the new number from the failure.** Task 9 then removes the
duplication; its site count is in `PROGRESS.md` and is larger than a documentation sweep would
suggest.

**THE COMMIT IS NOT SPLITTABLE, AND THAT IS NOT AN EXCEPTION TO THE SEPARATE-COMMITS RULE.**
Deleting `Backend` and fixing its two importers is **one change with a mechanical
consequence**, not two changes that could each explain a wrong number — so the standing rule
does not reach it. Landing the deletion without the import fixes would leave the tree
uncompilable, which is a worse property than either half is worth.

---

## Task 1 — the floor, and the store field that records its basis

**Goal.** The floor is a measured, per-run quantity; the store records which basis produced its
tile side.

**Behaviour.**

- **The floor is measured post-warm, not at import.** Task 5 established that numba's threading
  layer is invisible to `threadpool_info()` until something parallel has executed; **the same
  argument applies to its residency.** The measured ladder is in `PROGRESS.md`'s inherit
  section, and it confirms the hazard by measurement rather than by argument: an import-time
  floor understates materially.
- **Record the production floor — the WARM one, WITHOUT the compiled kernel's JIT.** Under F4
  production never reaches the compiled kernel. **That choice is a claim about F4** and is
  pinned by Task 0's reachability assertion, so the floor and the assertion move together the
  day a batched driver lands.
- **Measured with the input open.** A zarr store's handles, consolidated metadata and
  decompression buffers are resident and scale with the store rather than with the tile.
  Measuring before the open attributes them to the tile term and makes `tile_side` wrong in the
  **unsafe** direction.
- **The floor is measured fresh every run and is never cached.** Its two parts are cheap — a
  child process, an open, one chunk read — and their dependencies are the hardest to key: the
  input's contribution depends on the **chunk grid**, which Task 11's (a1) sweep classified as
  read back from the store rather than hashed. Keying on it would invent a gate the project
  deliberately does not have. **An uncached quantity has no staleness failure mode.**
- **Both pre- and post-warm floors are recorded** in provenance, so the 30% gap is visible in a
  store rather than only in this document.
- **`total_ram_bytes` respects a cgroup limit.** `psutil` reads the host; `/sys/fs/cgroup/memory.max`
  (v2) or `memory/memory.limit_in_bytes` (v1) is the container's. Take the **minimum** and
  record which basis was used. **This machine has no limit** — measured 2026-08-14,
  `memory.max` is `max` — so the environment cannot express the defect and the fixture must,
  exactly as `choose_core_count` (no SMT here) and `library_table` (one OpenBLAS here) already
  do. Same class as `platform.processor()` returning `''` on Linux: the obvious source is wrong
  on the platform that matters and the failure is silent until it is fatal.
- **`machine.total_ram_bytes` feeds `machine.fingerprint()`**, so today two containers of
  different sizes share a calibration key. That is (a2)'s third fact failing — a change in the
  thing identified does not move the field — and it is a live gap for the `cloudify` target
  even though it cannot be reproduced here.
- **`tile_side_basis` is a required root attr and `store.SCHEMA_VERSION` becomes 4.** Task 11's
  precedent governs: `detail` became required and the version moved to 3 because *a v2 store
  cannot answer the question the gate asks*. A store without the basis cannot answer "was your
  side analytic or measured?", and Task 6's refusal needs the answer. Its vocabulary is
  §13.4's: **cached, measured-this-session, or shipped-default.** 2a-written stores will not
  resume — harmless today for the same reason the 2026-08-07 golden regeneration was, and not
  harmless later.

**Interfaces** (Tasks 2, 3, 4 and 6 bind):

    memory.FloorReport            # pre_warm_bytes, post_warm_bytes, with_input_bytes, components
    memory.measure_floor(*, data_uri, variable) -> FloorReport
    machine.total_ram_bytes() -> int          # now cgroup-aware
    machine.ram_basis() -> str                # "host" | "cgroup_v1" | "cgroup_v2"
    store.TileSideBasis           # StrEnum: CACHED | MEASURED | DEFAULT

> **AMENDED 2026-08-15, BY THE IMPLEMENTATION.** Two deviations, both reported in
> `PROGRESS.md` with their reasons.
>
> **`FloorReport` gained `peak_bytes`.** This task's bare-launcher requirement is justified in
> the brief by watermark inheritance, which is a property of `peak_rss_bytes` alone — while the
> recorded ladder is `current_rss`, which is neither a watermark nor inherited. The launcher is
> still required, for the opposite reason: criterion 7 asserts **peak** RSS, so the quantity
> Task 2 subtracts is the peak of everything that is not the tile. Both instruments ship, and
> `peak_bytes` is floored at the largest rung because `ru_maxrss` updates lazily and was measured
> **below** a current reading taken an instant earlier.
>
> **`total_ram_bytes()` and `ram_basis()` delegate to one private
> `_resolve_total_ram() -> (int, RamBasis)`.** Two independent readers of `/sys/fs/cgroup` can
> disagree, and provenance would then record a basis that did not produce the number beside it —
> (a2)'s fourth fact turned around. `machine.RamBasis` is a `StrEnum`, so the `-> str` signature
> above still holds.
>
> **And `run()` grew a `floor: FloorReport | None = None` seam**, on the `observed_thread_limits`
> precedent, with `tests/conftest.py` stubbing it by default and a `real_floor` marker plus one
> paired control exercising the measured path.

**Tests, and the bug each catches.**

- *The post-warm floor exceeds the pre-warm floor.* Catches the floor being taken at import,
  which is the 30% error measured above and the one that makes `tile_side` too large.
- *The floor with the input open exceeds the floor without it.* Catches the input's contribution
  being attributed to the tile term.
- *Every floor measurement runs behind a bare launcher.* Catches the session's watermark
  becoming the measurement — open question 12's closure is what makes a child measurement
  trustworthy, and a probe spawned straight from pytest inherits pytest's high-water mark.
- *`total_ram_bytes` returns the cgroup limit when one is present, with the basis recorded* —
  **constructed**, because this machine has no limit. Catches a host reading being used inside
  a container, whose consequence is an OOM kill rather than a slow run.
- *A store carries `tile_side_basis` and a v3 store is refused on resume.* Catches the field
  being added without the version, which would let a v3 store answer Task 6's question with
  silence and have the silence read as agreement.

**Watch.** The floor measurement spawns processes and imports numba; it is `slow` and
`machine`. And a new test that allocates raises the session watermark and can fail a test in
another module — P4's `run_spike` took the watermark to 991.7 MB and a 400 MiB ballast in
`test_memory.py` then moved it by exactly zero.

---

## Task 2 — `block_bytes`, and the smooth-base rounding

**Goal.** The budget bounds process peak RSS, and every derived tile side is chunk-friendly by
construction.

**Behaviour.**

- **`block_bytes = budget − floor − headroom`.** F1. The budget is what the user typed and what
  criterion 7 asserts; the block is what the tile may hold.
- **A budget at or below the floor is refused**, naming the floor, **its components**, and **a
  budget that would work** — the user has no other way to find out. The refusal fires on the
  **resolved** budget, not on the request, or a `None` config bypasses it (Task 3).
- **Headroom is a POLICY constant with its consequence stated**, in `lint.OVERLAP_RATIO`'s
  idiom. Nothing about float64 has an opinion here, so it must not be dressed as eps-derived.
  It exists because peak RSS overshoots a steady-state model through transients — the
  float32→float64 conversion, zarr's decompression buffers, temporaries in the write path — and
  **its consequence is asymmetric: too small kills the process, too large costs runtime.** That
  asymmetry is the justification for choosing conservatively, and it belongs in the docstring.
- **The derived side is rounded down to a multiple of a smooth base.** Rounding down is always
  budget-safe. **"Prefer a composite side" — this file's own earlier phrasing — is wrong in both
  directions**: 338 is composite and still has no admissible divisor near the chunk target,
  while its neighbour 336 does. The divisor measurement that establishes it is in `PROGRESS.md`'s
  inherit section, and it is **the justification for the base existing at all** — without it the
  base reads as an arbitrary constant and will be tuned away.
- **The base is a policy constant chosen with the measured divisor structure in front of you.**
  16 gives a set dense low and sparse high; 12 is denser in the middle. **The admissible window
  decides, not elegance**, and the window differs per array. Loss to state: 338 → 336 is 1.2%
  of area.
- **The rounding happens inside `tile_side_for`, before the side is stored**, so the calibration
  exercises the same derivation the production run does — (j2) — and a resume reading the side
  back gets the rounded one. The two can then never disagree.
- **This removes a footgun rather than documenting one.** With every derived side a multiple of
  the base, Task 7's instrument gets smooth sides by construction and there is no deliberate
  choice of budgets for a later reader to "simplify" into round numbers. **A property that holds
  structurally beats a deliberate choice that must survive future editing.**

**Interfaces** (Tasks 3, 4, 7 and 8 bind):

    tiling.block_bytes_for(*, budget_bytes: int, floor: memory.FloorReport) -> int
    tiling.tile_side_for(*, budget_bytes, floor, placement, d, k_beta, p_max,
                         n_time, n_models, per_point_design=False) -> int
    store.TILE_SIDE_BASE          # policy constant
    memory.HEADROOM_FRACTION      # policy constant

> **AMENDED 2026-08-15, BY THE IMPLEMENTATION.** Landed as specified, plus:
> `tiling.BudgetTooSmallError`, a distinct type so the caller staging it into a layer-3 refusal
> dispatches structurally rather than on message text (c2); a `threads` parameter on
> `tile_side_for`, since the solver constant takes one; and **`run.FLOOR_OVERRIDE_ENV`
> (`METAMER_FLOOR_BYTES`)**, which the brief did not anticipate and which the task cannot be
> completed without — a measured floor makes any out-of-process fixture unable to pin a tile
> side, because the window that selects a small side is a few kB wide while the floor varies by
> megabytes. It records itself in provenance as `components={"override": N}`.
>
> **Two ordering changes fall out of the refusal being reachable.** `check_resume` and
> `check_source` now run **before** the derivation (§13.7's own order, which had nothing to
> enforce while the tiling step could not fail), and **a recompute runs no budget arithmetic at
> all** — its side is read back, and the budget's rule bounds a fit's resident set, which a
> recompute does not have.
>
> **And the base rounds only at or above itself.** Below `TILE_SIDE_BASE` no array's shard can
> reach the chunk target, so the divisor structure is provably irrelevant and the raw side passes
> through; rounding it to zero would refuse a small run for no benefit.

**Tests, and the bug each catches.**

- *A tile at the derived side, plus the floor, is within the budget* — asserted **arithmetically**
  here and by **measurement** in Task 8. Catches F1 recurring: the budget being used as the
  block.
- *A budget at or below the floor is refused, and the message names the floor, its components
  and a workable budget.* Catches a refusal that says only "too small", which is a wall rather
  than planning information.
- *Every derived side is a multiple of the base*, over a range of budgets. Catches the rounding
  being applied at a call site rather than inside the derivation, which is how the run and the
  calibration come to disagree.
- *The achieved chunk bytes are within the target band for the **worst** array, not a
  representative one.* Catches a base validated on `theta` alone and failing on a narrow array
  where the smallest admissible divisor is the side itself. **The window differs per array and
  the base must satisfy all of them at once.**
- *The published worked example reproduces through `tile_side_for`.* Catches the corrected number
  orphaning the documents again; Task 9 generalizes it.

---

## Task 3 — the `--memory-budget` default, and the unset sentinel

**Goal.** A config that does not mention the budget is distinguishable from one that names the
default, and the default comes from the machine.

**Behaviour.**

- **`memory_budget_gb: float | None = None`, resolved at run.** `Field(default=1.0)` means **a
  config omitting the field is byte-identical to one specifying 1.0** — the field cannot express
  its own absence, so "accepted the default" and "chose 1 GB" are the same bytes and a defaulting
  rule has nothing to fire on. **This is (a0) at a config field**, and it resolves the same way
  every fill value in the store does: the sentinel must be a value the writer cannot produce.
- **The default is a fraction of TOTAL RAM**, cgroup-aware via Task 1. Not available RAM: the
  derived side would move with whatever else the machine was doing, so a second run of the same
  store on a busier machine derives a smaller side, hits `completion.resume_tile_side`'s
  *stored > derived* arm and **refuses**. **A defaulting rule that makes a resume fail because a
  browser was open defeats §15.5's burst-and-resume argument**, which is the reason
  `memory_budget_gb` is run-relevant in the first place. `min(total, available)` is the same
  failure arriving less often and therefore harder to diagnose.
- **Total RAM is already one of the fingerprint's three components**, so a total-RAM default is
  stable exactly where the calibration cache is valid. An available-RAM default would vary
  **within one cache key**, so the cached slope and the derived budget would disagree about what
  machine they are on.
- **The fraction is a POLICY constant** with the same asymmetry as the headroom: too high kills
  the process, too low costs runtime. **Sanity-check the derived budget against this machine's
  measured available RAM — the figure in `PROGRESS.md`'s Hardware table, not the stale "~10 GB
  free" it replaced — and record which figure the check used.**
- **The RESOLVED value reaches `run_hash`; the request is recorded separately.** The `None` must
  not reach the payload. **The same config file therefore yields different `run_hash`es on two
  machines — correct, and stated so it does not read as nondeterminism.** `memory_budget_gb`
  stays run-relevant and out of both gates.
- **Availability is read and reported as a warning when it is below the derived budget**, naming
  the derived budget, the observed available, and the flag to set. **Never a gate, and the reason
  is recorded in the code**: a gate there makes a resume depend on ambient machine state, which
  is the failure that ruled out an available-RAM default.

**Tests, and the bug each catches.**

- *A config omitting the field and a config naming the resolved value produce the **same**
  `run_hash`, and provenance distinguishes them.* Catches the `None` reaching the payload, and
  catches the resolution being a name — without this test nothing asserts the resolved value is
  what the run used.
- *The refusal from Task 2 fires on the resolved value for a `None` config.* Catches a `None`
  config bypassing the floor check, which would be the one path where a budget below the floor
  proceeds.
- *A low-availability machine still derives the same side.* Catches an available-RAM default
  creeping in, whose symptom is an unresumable store rather than an error.
- *The availability warning does not move the exit code.* Catches it being promoted to a gate,
  which someone will attempt on the grounds that overcommitting is bad.

**LANDED 2026-08-15, WITH THREE THINGS THIS BRIEF DID NOT ASK FOR AND ONE IT COULD NOT.** The
findings are in `PROGRESS.md`'s *What Task 3 established*; in one line each:

- **A second provenance key and `SCHEMA_VERSION` 5.** *"Provenance distinguishes them"* needs a
  place to put the request, and `memory_budget_requested_gb` cannot join `REQUIRED_ATTRS` —
  `create_store` refuses on `attrs.get(key) is None`, and this key's `None` **is its meaning**.
  The version bump is the only mechanism left that stops an older store's silence reading as
  "the budget was defaulted".
- **`Config.run_hash` refuses an unresolved budget**, while `fit_hash` and `compat_hash` still
  compute. That asymmetry **is** the allowlist boundary made executable: the budget is in
  neither gate, so refusing there would assert a dependence the allowlists deny.
- **`completion.resume_tile_side`'s message names the default** when the store records a null
  request. The brief did not anticipate that a machine-dependent default makes the existing
  refusal tell a user to raise a flag they never set — (c3)'s phrasing rule.
- **The availability reading does NOT reach provenance**, which the brief left open. It is an
  *ambient* per-run measurement with no consumer, and Task 1's (a5) instance is the precedent:
  a per-run measurement in the root attrs broke 2a's byte-identity criterion.

---

## Task 4 — the calibration measurement

**Goal.** A measured slope and intercept for this dataset, model set, placement and machine,
produced by the production path.

**Behaviour.**

- **The instrument is a capped-iteration run of `run()` itself** — same entry point, same tile
  loop, same budget derivation, same batch shape — with the optimizer's iteration cap lowered.
  **A purpose-built harness would approximate the tile loop and validate the approximation**,
  which is F2 exactly.
- **The cap must reach `run()`, and it does not today.** `fit(..., max_iter: int = 200)` exists
  and `run()` does not pass it. **The seam is `run(..., max_iter=...)`**, and it is the same
  argument as `engine=` and `on_tile_written=`: a calibration that constructs its own loop to
  get a cap is (j2) by construction. Convergence is well inside the default — `mean_iterations`
  is 32.5 at d=3 (P3) against a cap of 200 — so the cap is a calibration knob and never a
  production one.
- **The shipped calibration measures a fixed small-B ladder**, not the requested budget's B —
  **B ∈ {1000, 2000, 4000} as the shipped default, which is a policy choice and carries its
  reason**: three points give one residual, which is enough to *detect* gross non-linearity but
  not to characterize it, and characterizing it is Task 7's job, once. The slope is a
  **per-series** quantity, so it does not need production B; **what needs production B is the
  claim that it is LINEAR there.** The assumption is **named in the cache entry**, so a later
  reader knows which of the two measurements established what.
- **A fresh child per point, behind a bare launcher.** Open question 12's closure is what makes
  this trustworthy: `peak_rss = max(inherited, own high-water)`, inheritance does not compound,
  so a child spawned from a bare launcher starts from a known floor whatever the parent
  allocated.
- **The fixture carries at least one non-OK point, and it must be an OPTIMIZER-stage failure.**
  A fixture where every series converges never allocates what the failure paths allocate, and the
  taxonomy has a dozen members. **The design is shared and built once before the candidate loop**
  (`fit.py:182`), so a design-stage failure hits every candidate and gives `n_valid = 0` — the
  construction Task 9 of 2a established: `white + matern12` on white noise is degenerate at most
  points while `white` fits (measured, 3 of 4). **This holds until a joint signal × noise search
  lands.**
- **The cap must not hide the converged path, and the resolution is not "raise the cap".**
  `fit.py:237` is `if result.outcome is not Outcome.OK: continue`, so a capped run reaching
  `ITER_CAP_*` skips **four allocation sites**: the `theta` write, `np.linalg.inv(hessian)`,
  `delta_method_cov`, and the second `obj.evaluate` at the optimum. Every one of them is inside
  `for b in range(batch)` on `y[b:b+1]`, so each allocates shape `(1, …)` — **they are
  constants, not slope terms** (F2), and they belong to the intercept. The capped run therefore
  measures the slope correctly and under-measures the floor, which is the safe direction and
  must not be silent.
- **The converged-path constant is measured separately**, by differencing a small-B run at a
  converging cap against the same B capped at 1.

**Invariants, and the one the whole method rests on.**

- **Residency is iteration-independent**, and it is verified by a **step test, not a slope
  test**. A three-point fit through caps {1, 5, 32} would catch an *accumulating* allocation and
  would read the likelier defect — an allocation on a path a cap of 1 never reaches — as a small
  positive slope, which the eye calls noise. **The discriminating measurement is peak RSS at
  fixed B for caps {1, 2, 3}**: flat if residency is iteration-independent; a **step at 1 → 2
  and flat at 2 → 3** if a first-iteration path allocates, which is a signature rather than a
  slope. **Keep one high point, cap 32 at the same B**, as the accumulation check. Four points,
  two questions, stated separately.
- **If the step test fails, this instrument is dead and must say so loudly** rather than being
  patched with a higher cap.

**Interfaces** (Tasks 5, 7 and 8 bind):

    memory.CalibrationResult   # slope_bytes_per_series, intercept_bytes, residuals,
                               #   ladder, linearity_basis, placement, engine_label
    memory.calibrate(*, config_path, ladder, floor) -> CalibrationResult
    memory.CALIBRATION_LADDER               # policy constant, (1000, 2000, 4000)
    run(..., calibrate: bool = False, recalibrate: bool = False,
        max_iter: int | None = None) -> RunReport

**Tests, and the bug each catches.**

- *The step test: peak at caps {1, 2, 3} is flat within the noise floor, and cap 32 adds nothing.*
  Catches an allocation on a first-iteration path being missed by the cap, which would make every
  calibrated slope too small — the unsafe direction.
- *The calibration drives `run()`, not a private loop.* Catches (j2) recurring. The executable
  form: the calibration's derived side equals `tile_side_for`'s for the same inputs.
- *The fixture contains a non-OK point, and it is an optimizer-stage failure.* Catches a
  best-case slope, and catches the design-stage construction the 2a brief prescribed and that
  cannot work.
- *A calibration measured at the small-B ladder records that it assumed linearity.* Catches the
  cache entry claiming more than the measurement supports — the discipline every stale number in
  this project has lacked.
- *A capped run under-reports the converged constant, and the difference is measured.* Catches
  the four skipped allocation sites being forgotten rather than accounted for.

**LANDED 2026-08-15. THREE OF THIS BRIEF'S NUMBERS DID NOT SURVIVE CONTACT AND THE FOURTH IS
NOW MEASURED.** In full in `PROGRESS.md`'s *What Task 4 established*; in one line each:

- **`B ∈ {1000, 2000, 4000}` is unreachable.** A run's batch is a tile, so `B = side²` on a
  base-16 grid and none of the three is a tile. **The ladder is in SIDES**,
  `CALIBRATION_LADDER = (16, 32, 48, 64)`, and `tiling.budget_bytes_for_side` is what lands on
  one. **Promoted**, with its arithmetic, as (j2)'s specification-level twin.
- **The outcome mix is NOT constant across {1, 2, 3}.** An `OK` needs `n_iter < max_iter`, so
  convergence begins at cap 3 — a point this brief named and nobody measured. **The step test is
  stronger for it**: the peak is flat across all three **while** fifteen fits reach the four
  allocation sites, which turns "those sites are constants" from a code reading into a
  measurement. **Promoted** as (a4)'s sample-level twin, with the counts.
- **`calibrate=` and `recalibrate=` did not land.** There is no cache until Task 5, and a flag
  that parses and does nothing reads as supported. Only `max_iter` is here.
- **The slope is measured, and its uncertainty is the point**: it clears the two-sided band on
  the production path for the first time, and the excess over the analytic figure is **inside
  one standard error and is therefore not a measurement of the uncharged temporaries**, however
  well it agrees with Task 0's estimate. The figures are in `PROGRESS.md`, once.

**And two things the brief did not bound.** `run()` loops every tile, so a calibration on a
production grid would fit all of it — the run is stopped after one tile through
`on_tile_written` and the existing SIGTERM path, which adds no seam and no branch (j3). And the
cap is in no hash, so a capped store shares all three hashes with an uncapped one; the resolved
cap is written to provenance as `max_iter`, with no schema bump because the outcome codes
already answer the question.

---

## Task 5 — the calibration cache

**Goal.** A measured slope is reused across runs on the same machine, and is invalidated by the
thing that actually changes it.

**Behaviour.**

- **The cache is a sibling object at a path derived from the store path**, overridable, written
  before store creation and read before store creation. §11.4 and §15.5 require it to live with
  the store rather than in local scratch, and §12.4 requires every store to be self-contained;
  both hold because of one property, which must be written into the docstring:

  > **The store never resolves through the cache.** The cache is an input to store creation and
  > nothing reads it afterwards — a resume reads the side back out of the store (a1). Deleting
  > the cache can never break a store, only cost a re-measurement.

  Inside the store's root attrs would be self-contained and useless: **a fresh store has no attrs
  yet**, so the cache would only ever serve resumes, and a resume already reads the side back.
- **Key: `(fit_hash, placement, engine label, machine fingerprint, versions digest)`.** The
  engine label is memory-relevant and is **not** `EngineId` (F4). The placement has one reachable
  value today and is in the key anyway, on the `shared_with` precedent.
- **The versions digest is read from the environment, never from the declaration** —
  `importlib.metadata` over **every installed distribution**, excluding nothing for being
  obviously irrelevant. `pixi.toml`'s ranges would give one digest across every version they
  permit, which is the whole hazard, and a curated list has the `cftime` hole by construction:
  Task 2 of 2a established that a dependency reached for **through** another library is invisible
  to any static import scan. **Over-invalidating costs minutes; under-invalidating costs a bad
  projection against a hard memory constraint.** The asymmetry decides it.
- **No expiry, and not even as a backstop.** Time does not cause the change it stands in for —
  (a2) at a cache key. A backstop firing on a schedule unrelated to the hazard re-measures when
  nothing changed and stays silent when something did, **and its presence makes the real gate
  look optional.** `--recalibrate` is the manual override, and it is honest: it fires when a
  human has reason to believe the measurement is stale, which is the only signal an expiry was
  approximating.
- **The contributing versions are recorded in the cache entry and in the store's provenance**,
  not only their digest, so a mismatch names the package that moved. Same discipline as
  `geometry_hash` storing its components beside the rollup.
- **Only the slope is cached. The floor is measured fresh** (Task 1).
- **Calibration is opt-in: `--calibrate`, plus `--recalibrate` to force past a hit.** Without it
  the corrected analytic formula is used and **the basis is recorded**. §13.4's vocabulary
  already exists for this state and anticipated it before 2b did: each constant is labelled
  **(a) cached, (b) measured this session, or (c) a shipped default — and in case (c) a range,
  not a point estimate.** Under Task 2 the analytic path is conservative rather than optimistic,
  so (c) is now an honest estimate. **A run that silently spends twenty minutes measuring before
  it starts is behaviour a user cannot predict**; the tradeoff is reported by `--explain`
  (Phase 5) rather than decided by a threshold.

**Interfaces** (Tasks 6, 8 and 10 bind):

    calibration.cache_path(store_path: Path) -> Path
    calibration.cache_key(*, fit_hash, placement, engine_label, machine, versions) -> str
    calibration.versions_digest() -> tuple[str, dict[str, str]]     # digest, contributors
    calibration.load(path, key) -> CalibrationResult | None
    calibration.store(path, key, result) -> None

**Tests, and the bug each catches.**

- *Deleting the cache leaves the store openable and resumable.* Catches a store acquiring a
  dependency on the cache. **It asserts the absence of a dependency, which is otherwise
  unfalsifiable.**
- *A second process reads the entry and derives the calibrated side*, on a fixture where the
  **analytic and calibrated sides differ measurably.* Catches the cache never being read: a
  calibration consumed only in the session that produced it never exercises it, and **if the two
  sides agree on the fixture every cache test passes against a cache nothing reads.** This is
  (i7) — the fixture must be placed off the point where the two agree, deliberately.
- *`--calibrate` produces an entry and a default run does not.* The pure negative and its (i2)
  positive control, paired: "no calibration ran" is otherwise satisfied by a mechanism that
  cannot run at all.
- *The digest moves when any distribution's version moves*, from two constructed version maps.
  Catches the digest being a name — (a2)'s third fact, made executable.
- *A stale entry under a changed digest is not used.* Catches the key being computed and then
  ignored, which is the `observed`-recorded-and-ignored shape Task 5 of 2a already found once.

**LANDED 2026-08-15. THE INTERFACE BLOCK ABOVE CANNOT MOVE A TILE SIDE, AND THE FIRST CONSUMER
OF A MEASURED NUMBER NEEDED A RULE FOR A BAD ONE.** In full in `PROGRESS.md`'s *What Task 5
established*; in one line each:

- **`tiling.tile_side_for(..., per_series_bytes=None)` is the seam, and it is a deviation.**
  Nothing in the five interfaces changes any number a run uses: `tile_side_for` computes the
  per-series cost internally. **Only the SLOPE goes through it** — the intercept is the floor
  under the calibration's conditions and not the production floor.
- **A measured slope outside `memory.slope_band` is NOT USED**: the run falls back to the
  analytic formula, records `DEFAULT`, and warns. §11.4 already requires the calibration to be
  *validated against §9.4's analytic formula*, and two failure modes make it necessary rather
  than tidy — a non-positive slope is a domain error out of `sqrt`, and a small positive one
  sizes an enormous tile with no error at all. **Fallback rather than refusal**, because a
  refusal after a multi-hour measurement makes (i2)'s positive control depend on the sign of a
  noise-dominated number.
- **The cost of that band, stated:** a calibration moves the per-series cost by at most 1.5× and
  therefore the side by at most √1.5 = **1.22×**, which is what places the (i7) fixture at 8
  against 7 rather than anywhere wider.
- **A `calibration` provenance block is written whenever a calibration was CONSULTED**, used or
  not. Without it a store that spent 26.5 h measuring and one that measured nothing both read
  `tile_side_basis = default` — the fill-value shape at a provenance key. **No schema bump**: a
  v5 store's silence is unambiguous, because nothing before this task could consult one.
- **metamer is not an installed distribution in a source tree**, measured, so *"every installed
  distribution"* omits the package being measured. The map is built from the distributions **and**
  from `metamer.__version__`.
- **`--calibrate` is refused alongside `--reuse-fits-from` and alongside an injected engine.** A
  recompute derives no side, and a calibration's children build their own engine.

**And one thing this brief asserted that is not true as written.** *"Deleting the cache can never
break a store, only cost a re-measurement"* is true of the **store** and false of a **resume**:
where the calibrated side was larger than the analytic one, `completion.resume_tile_side` refuses
on its *stored > derived* arm. The docstring carries the narrow claim, and **naming that refusal
is Task 6** — which is the evidence the broad claim was wrong.

---

## Task 6 — the resume refusal that names calibration

**Goal.** A resume whose side moved because someone calibrated says so.

**Behaviour.**

- **A cache hit changes `tile_side`, and `tile_side` is gated by Task 10 of 2a's rule** — equal
  proceeds, *stored < derived* adopts the stored side, *stored > derived* refuses. So a store
  created from an analytic side and resumed after `--calibrate` derives a different side, and if
  the calibrated side is **larger** the resume **refuses** — correctly by the rule, while the
  user's action was "measure more accurately" and the consequence is "your store is now
  unresumable."
- **That is a stated consequence, not a discovered one.** When the store's `tile_side_basis`
  differs from the current run's, the refusal **names calibration as a cause** and names both
  bases. The field is Task 1's; this task is its only reader.

**Tests, and the bug each catches.**

- *A store built analytically, resumed with a calibrated side that is larger, refuses and names
  calibration and both bases.* Catches the message describing only the sides, which sends the
  user to the budget when the cause was the cache.
- *A store built analytically, resumed with a calibrated side that is smaller, proceeds on the
  stored side.* The (i2) positive control for the refusal, and it pins that Task 10's asymmetry
  survives the new cause.
- *A resume at the same basis and the same side is unaffected.* Catches the new comparison
  refusing the ordinary case — Task 11's `tuple != list` lesson, where the natural comparison
  refused every resume including the correct one.

**LANDED 2026-08-15. THIS BRIEF INVERTS THE ARM IT QUOTES, ONE CLAUSE AFTER QUOTING IT.** In full
in `PROGRESS.md`'s *What Task 6 established*; in one line each:

- **The refusal fires when the calibrated side is SMALLER, not larger.** The store supplies
  `stored` and the calibration supplies `derived`, so *"if the calibrated side is larger the resume
  refuses"* names the **adopt** arm — and both of this brief's first two tests are the wrong way
  round. **The conclusion survives**: a smaller side is what a slope **above** the formula buys,
  and Task 4 measured the slope above the formula, so *"I measured more accurately and my store
  will not resume"* is the expected experience rather than a corner.
- **"When the store's basis differs from the current run's" is the wrong condition**, and the cell
  it misses is `--recalibrate`: two measurements of one store both read `measured` while the sides
  differ. **The condition is "either basis is not `DEFAULT`"**, and the both-`default` case must
  stay silent, on the same grounds that stopped this message naming a budget nobody typed.
- **Three situations, three resolutions (c3).** "Omit `--calibrate`" is advice to stop doing
  something the run that lost its cache never did.
- **The effective basis is resolved once above the tiling** and read by the gate and by provenance,
  rather than computed inline at each — the second copy is what a reader would have added.
- **No schema bump, and the check is recorded rather than assumed:** `tile_side_basis` is a
  non-nullable required attr since v4 and this task adds no field, so Task 3's *required-and-
  nullable* mechanism does not apply. The adjacent question — Task 5 adding `calibration` without
  a bump — is safe for a different reason, that nothing before Task 5 could consult a calibration,
  so an absent key means the same thing in both eras.
- **The no-calibration message is byte-for-byte what it was.** A diagnosis that changed for every
  user in order to serve one of them would be its own defect.

---

## Task 7 — criterion 6's instrument: the linearity claim

**Goal.** The measured slope matches the corrected formula, and the linearity the shipped
calibration assumes is established once and pinned.

**Behaviour.**

- **Four or five tile sides, not three.** Three points fit a line through **one residual** and
  cannot falsify linearity. If the relationship has curvature — and it might, since zarr's read
  buffers and the float32→float64 conversion need not scale linearly with tile side — three
  points fit it well and report a wrong slope confidently. **Report the residuals, not just the
  fit.**
- **The sides are multiples of Task 2's base**, which they are by construction rather than by a
  deliberate choice of budgets.
- **A fresh child per side, behind a bare launcher**, capped per Task 4.
- **The comparison against the formula is the two-sided band from Task 0**, and a slope
  materially **below** the formula is reported as a finding rather than as headroom.
- **Cross-check with the batched-evaluation instrument, and name the disagreement in advance.**
  `measure_evaluation_rss_slope` holds `B × (d²…)` and the production loop does not, so the two
  **must** disagree by approximately `solver_state_bytes` per series. **That disagreement is the
  measurement of F2's magnitude, not a second opinion** — stating it in advance is what stops
  someone reconciling them.
- Marked `slow` and `machine`. **Cost estimate, to be re-measured:** B ≈ 3 000–12 000 keeps the
  tile term resolvable at ~50 MB against the measured floor, for roughly 1.5 h.

**Tests, and the bug each catches.**

- *Slope and intercept against the corrected formula, within the two-sided band, with residuals
  reported.* Catches both directions of a wrong formula, which the old one-sided check could not.
- *The evaluation instrument disagrees by approximately the solver-state term.* Catches F2 being
  silently reintroduced, and it is the only test that measures F2's size rather than asserting
  its shape.
- *The residuals do not show curvature over the ladder.* Catches the shipped calibration's
  linearity assumption being false, which would make every small-B calibration wrong at
  production B in a way no cheap measurement could see.

---

## Task 8 — criterion 7's run, and accumulation across tiles

**Goal.** Close exit criteria 6 and 7 at a scale where the tile, not the interpreter, is the
subject.

**Behaviour.**

- **Peak RSS is a property of ONE TILE.** A 10⁶-point grid at a small budget has the same peak as
  a 10⁴-point grid at the same budget. **PROGRESS's stated closer — "one run at 10⁶–10⁷ points" —
  is the wrong quantity for two of the three claims**, and that is why the criterion looked
  unclosable and is not. The three claims decompose:
  - **Peak under a budget.** One capped run at side ≥ 192 under a 0.5 GiB budget, which is *well
    below* this machine's measured available RAM, as the criterion asks. ~1.7 h.
  - **The slope against the formula.** Task 7.
  - **No accumulation across tiles.** This is the only one that genuinely needs grid size, and it
    has an instrument nobody had noticed: **`--reuse-fits-from` is the tile loop with the fit
    removed** — same loop, same write path, same bitmap, no optimizer — so a recompute over
    10⁵–10⁶ points runs in minutes. **This is (j3):** a cheap instrument found among existing
    features drives the production path by construction, where a purpose-built accumulation
    harness would have approximated the tile loop and validated the approximation.
- **The accumulation test states what it covers and what it does not.** It covers the tile loop,
  the write path, the bitmap and zarr's buffers. It does **not** cover anything `optimize_series`
  or the engines retain, because a recompute holds less than a fit does. Otherwise it reads as
  "no accumulation" when it means "no accumulation in the loop". **The capped run at side 192
  iterates several tiles, so assert peak against tile index there too** — same run, second
  assertion, and it covers the fit path.
- **One budget below the floor is in the test set**, asserting Task 2's refusal. The boundary is
  cheap to test and it is the one a user with 16 GB and a large model will actually hit.
- **The three boundaries are recorded as measured numbers with instruments named**, which is what
  makes this a specification rather than a hedge. **The numbers, the arithmetic and the
  unverified §9.3 gap live in `PROGRESS.md`'s
  [what 2b's first tasks inherit](../../../PROGRESS.md) section and are not restated here** — one
  home per measurement, which is the rule this sub-phase's own cascade exists to teach. What
  this task owes is that each boundary is written down **with the instrument that would close it
  and the machine that could run it**, so "reduced scope" is a specification rather than a hedge.

**Tests, and the bug each catches.**

- *A run at a formula-derived side under a budget well below available RAM has peak RSS at or
  below the budget.* **Exit criterion 7.** Catches a formula that is right per-series and wrong
  about what else is resident — which is exactly what F1 was.
- *Peak does not grow with tile index within that run.* Catches a per-tile leak in the fit path,
  which the recompute instrument cannot see.
- *Peak does not grow with tile count over 10⁵–10⁶ points via `--reuse-fits-from`.* Catches a
  leak in the loop, the write path or zarr's buffers.
- *A budget below the floor is refused.* Catches the refusal being unreachable in practice
  because every test budget is generous.

---

## Task 9 — the tile-side cascade amendment

**Goal.** The published tile side is stated once, with its derivation and its preconditions, and
a test recomputes it.

**Sequenced last on purpose.** The number is not final until the floor is measured and criterion
7 has run; amending the sites to a number that then moves again is the cascade repeating at
higher speed.

**THE SPREAD WAS COUNTED RATHER THAN ESTIMATED, AND IT IS NOT FIVE DOCUMENTS.** The count, by
category, is in `PROGRESS.md`'s inherit section — four categories, twenty-plus occurrences,
including **five source docstrings** and **live test assertions**, and **§9.4 is not among them
because it quotes 339**, the model figure.

**THE (i5) REPAIR IS MANDATORY, NOT ADVISORY, AND THIS IS THE ONE PLACE IN THIS PLAN WHERE THE
TEMPTING FIX IS BOTH EASY AND UNDETECTABLE.** When those assertions will not go green, the thing
that would have to change is *the published constant*. **Re-derive every expected value by hand
from the corrected formula and record the derivation beside it. Never paste a number from the
failure** — the same discipline the three `GOLDEN_*` constants carry, and for the same reason: a
value copied from a failing run proves only that the code agrees with itself.

**Behaviour.**

- **One source, N pointers.** The number is stated **once** with its derivation; the design-doc
  sections, the source docstrings, the 2a plan and `PROGRESS.md` reference it. **A set of
  consistent copies is the wrong repair** — 2a's duplicate sweep established that reconciling
  copies treats the symptom, and the `pixi.lock` size held the oldest of three figures through
  three updates.
- **The source docstrings are part of the cascade and are the half most likely to be missed**,
  because a documentation sweep looks at documents. `tiling.py`'s module docstring is what a
  tiling implementer reads first — which is exactly the position §11.1 held when it carried the
  superseded 445.
- **The derivation prints beside the number.** A bare 272 is exactly as stale-able as 338 was.
  The derivation is what lets the next reader check rather than trust, and it is what would have
  caught `4 + 6 = 10`.
- **The number carries its preconditions**: placement, engine label, budget, floor, headroom,
  base, `P_total`, M, C, `k_beta`, N and dtype. **A `tile_side` without them is not a number**,
  and this cascade is why that rule exists.
- **The old figures are struck rather than deleted**, with their date and what superseded them,
  so a reader meeting 338 in an old note can tell which document is current.

**Tests, and the bug each catches.**

- *The documented number equals `tile_side_for(documented inputs)`.* **The only durable fix for
  this cascade, and it is available because the derivation is code.** Catches the next formula
  correction silently orphaning five documents — it fails instead.
- *The documented preconditions are the parameters `tile_side_for` actually takes.* Catches the
  precondition list drifting from the signature, which is how "338" came to be quoted with no
  backend attached.

---

## Task 10 — the 2b exit-criteria suite

Cross-process and cross-store properties no single task can express. **Driven from outside
wherever an outside exists**, per 2a's Task 13: a fresh child, a store read back from disk, a
cache read by a process that did not write it.

| # | criterion |
|---|---|
| 1 | `resident_bytes_per_series` describes the code: the output-slot term matches what `fit` preallocates **field by field**, and the solver term does not scale with B |
| 2 | Everything `optimize_series` allocates has leading dimension 1 |
| 3 | The batched placement is unreachable through `run()`, with its arithmetic asserted through a constructed call |
| 4 | The floor is measured post-warm with the input open, behind a bare launcher; pre- and post-warm are both recorded and differ |
| 5 | A budget at or below the floor is refused, naming the floor, its components, and a budget that would work |
| 6 | Measured slope and intercept match the corrected formula within a two-sided band at four or five sides, residuals reported — **closes 2a criterion 6** |
| 7 | A run at a formula-derived side under a budget well below available RAM has peak RSS at or below the budget — **closes 2a criterion 7** |
| 8 | Peak RSS does not grow with tile count over 10⁵–10⁶ points, nor with tile index within a fitted run |
| 9 | Every derived side is a multiple of the base, and the achieved chunk bytes for the **worst** array are inside the target band |
| 10 | A config omitting `memory_budget_gb` and one naming the resolved value produce the same `run_hash`, and provenance distinguishes them |
| 11 | `total_ram_bytes` respects a cgroup limit when one exists — **constructed; this machine has none** |
| 12 | `--calibrate` writes a cache entry, a default run does not, and a **second process** reads it and derives the calibrated side, which **differs measurably** from the analytic one |
| 13 | The versions digest moves when any installed distribution's version moves |
| 14 | Deleting the cache leaves the store openable and resumable |
| 15 | A store records `tile_side_basis`, and a resume across a basis change names calibration in its refusal |
| 16 | The documented tile side equals `tile_side_for` of its documented inputs |

---

## What 2b does not do

- **The batched driver, and therefore path B in production.** F4. Its landing condition is
  recorded: when a driver hands an engine a real batch, the engine's workspace becomes a
  per-series term and it is engine-dependent, so the calibration key must already distinguish
  placements and engines — which is why it does, before the driver exists.
- **`--explain`.** Phase 5. **Measure in the phase that can, print in the phase that shows**:
  2b computes and records the floor, the slope, the basis, the versions and the achieved chunk
  bytes; §13.4 prints them.
- **Pass 1 and the coarse-grid stride.** 2c. **And a correction 2c inherits: §11.4 says pass 1
  doubles as the calibration tile, which is questionable and must not be taken as settled.**
  Pass 1 fits a coarse subsample, so its batch is a fraction of a production tile even though it
  assembles a full one — its peak does not measure pass 2's. 2b's calibration is deliberately
  standalone, and 2c may make pass 1 a **caller** of it, never a substitute for it.
- **The `bench/` layering question**, still owed and owned by no sub-phase. Until it closes, **no
  test may read the ambient thread mask as a baseline.**
- **The exit-code-1 collision** — 2e's, with `INTERNAL_ERROR` the recommended fix.
- **Open questions 5, 10, 13 and 14** stay open: the 64-core box's RAM, macOS/Windows RSS
  semantics, the packaging guard's `--no-deps` install, and the benchmarks' synthetic time axis
  at `unique_dt = 1` against a real monthly axis's 6.
