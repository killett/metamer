# Phase 2c — the two-pass warm start, its barrier, and the hysteresis audit

**Status: APPROVED 2026-08-24. TASKS 0–7 ARE DONE (0–4 on 2026-08-24, Task 5 on 2026-08-27,
Task 6 on 2026-08-28, Task 7 on 2026-08-29); Task 8 has no code. Task 8 is the next action.** The single source for this plan's status is
this line. **What each task found beyond its brief is in
[`PROGRESS.md`](../../../PROGRESS.md)'s *What plan Task N established*, not here.**

> **TASK 1 WAS AN AUDIT, NOT A BUILD, AND IT MOVED A REQUIREMENT.** Its mechanism was already
> implemented in Phase 2a; **the `ALGORITHM_VERSION` bump it claimed now belongs to Task 5**,
> where `θ̂` actually moves, and **Task 5 cannot ship without it.**

**The design decisions this plan implements are D1–D12** in
[`PROGRESS.md`](../../../PROGRESS.md)'s *Phase 2c brainstorm — settled decisions*. **Nothing below
re-argues one.** Where a task rests on a decision it names it and points there; where it rests on
a measurement it points at
[`warmstart-spike-verdict.md`](../notes/warmstart-spike-verdict.md) or at the stride sweep's
points. **A measurement stated twice has one copy deleted, never reconciled.**

> ## THE STANDING LIMITATION, AND IT IS FIRST BECAUSE EVERY TASK BELOW INHERITS IT
>
> **NO 2c NUMBER COMES FROM REAL DATA.** Warm-starting was authorized on a **simulated field whose
> spatial coherence is a construction parameter** — smoothly varying by construction, sharp
> boundary by construction. **The spatial coherence of real altimetry optima has never been
> measured.** A field with **weaker** coherence gives a **smaller** saving, and **§11.2's 30%
> threshold could fail on real data.**
>
> **THE CLOSER IS NAMED, so this is a condition rather than a worry: a spike on a real gridded
> product — same three arms (cold, warm, self-ceiling), same record-length lever.** Until it runs,
> **D1 is authorized on simulation.**
>
> **AND IF IT EVER MOVES D1, FOUR DECISIONS FALL, NOT TWELVE.** D1 → D6 (the stride) → D9 (the
> strata) and D10 (the count check). **D3, D4, D5, D7, D8, D11 and D12 stand**: they rest on the
> completion bitmap's semantics, on `fit.py:227`, on the two-axis pass-1/pass-2 difference, on the
> absence of a stochastic component, on per-family disagreement, and on the self-arm measurement —
> **none of which is a function of how large the saving is.** The full statement is in
> [what 2c's tasks inherit](../../../PROGRESS.md).

## Why this plan has no code fences

Same reason as 2a and 2b. A fenced block is read as the implementation and stops being reviewed
as a specification; the reviewer checks whether the code is right rather than whether the
behaviour is. **Interfaces appear as signatures only where a later task binds against an earlier
one**, which is a contract rather than an implementation.

## What this sub-phase found before it started

**2c opened with two measurements, not with a brief.** §11.2 makes warm-starting's survival
conditional on a number it calls unmeasured, so **Task 0 of the brainstorm measured it before the
mechanism existed** — a verdict whose "no" is expensive is a formality. The stride was then
measured for the same reason: it sits in `fit_hash` and cannot be revised without fragmenting
every store built before the revision.

> **THE MAGNITUDES ARE NOT HERE.** Every figure 2c rests on lives once, in
> [what 2c's tasks inherit](../../../PROGRESS.md) — the saving curve and its ceiling, the stride
> curve and the bound that closed it, the self-arm result and the lattice, the agreement margin,
> and the two findings that put candidate ahead of geography. **This section states only what each
> finding CHANGED**; a magnitude repeated here would be the copy that drifts.

| finding | what it changed |
|---|---|
| warm-starting pays, **at production length only** | the mechanism is built. **No figure from a short record describes production** — the first fixture said *drop it* |
| **the geometry is not what pays** | D1 chose §11.1's mechanism anyway, on a **guarantee** rather than on the points the geometry adds: the cheap variant puts tile geometry, and therefore `--memory-budget`, inside `θ̂` |
| the stride optimum is **`k = 8`** | D6. The curve is still rising and the question is closed **by a bound**, not by another fixture — (j6) |
| **disagreement is per-family, not geographic** | D4 and D9. **Candidate is a primary audit axis; geography is reported and never gated** |
| the mechanism was **authorized with a margin of one grid cell** | **the audit is mandatory in fact**, and D7 gives it a named first hypothesis |

**And one Phase 1 interface constraint surfaced at its first real consumer.** `fit.py:227` reads
`warm = None if x0 is None else x0[b : b + 1, c, :p]`, so `x0` is **call-level all-or-nothing**
while §11.3's spiral fallback is **per cell**. That is Task 0.

## Standing requirements for every task

- **Run the pre-flight against the task brief before code**, and append the entry to
  [`phase2c-preflight.md`](../notes/phase2c-preflight.md) **before** the task, not after. The
  method lives in exactly one place and is not restated here.
- **`pixi run test` is the full sweep and every end-of-task verification runs it.** `test-fast`
  and `test-ci` are not evidence.
- **Commit after every task**, and **check CI after every push.** Red CI is the next task.
- **Every new measurement commits its predictions first**, with **refutation clauses in both
  directions** — (i11), which 2c paid for.
- **No task moves `PUBLISHED_TILE_SIDE`, `HEADROOM_FRACTION`, `resident_bytes_per_series`,
  `output_slot_bytes` or `SVD_CHUNK_SERIES`.** 2c inherits the residency model with its stated
  limitation and does not reopen it.

## Task index and dependencies

| # | task | depends on |
|---|---|---|
| 0 | `fit`'s per-cell warm-start selector | — |
| 1 | the fit-relevant fields, and the hash cascade | — |
| 2 | pass 1 as a run over a decimated input | 1 |
| 3 | the source map: spiral, tie-break, bound, exhaustion | 0, 2 |
| 4 | the barrier and the cross-store gate | 2 |
| 5 | the two-pass driver | 3, 4 |
| 6 | the audit's arms, and the four-reading table | 5 |
| 7 | the audit's strata and its report | 6 |
| 8 | the 2c exit-criteria suite | all |

**Tasks 0 and 1 are independent of everything and of each other**, which is why they are first:
each is falsifiable by reading and by unit test alone, with no store and no run.

---

## Task 0 — `fit`'s per-cell warm-start selector

**Goal.** `fit` can be told *"warm-start this cell, ladder that one"*. Today it cannot, and
§11.3's *"on exhaustion fall back to the moment-init ladder with the rung recorded as such"* has
no expressible implementation. ~~**This is the only `metamer.core` change 2c requires.**~~

> **THAT LAST SENTENCE WAS FALSIFIED AT TASK 7, 2026-08-29, AND IS STRUCK RATHER THAN DELETED.**
> D9 stratifies the audit by the cold arm's `cond(H)` and **no such value existed**:
> `optimize_series` computed it to decide `OK` against `DEGENERATE_HESSIAN` and discarded the
> number, and `fit` inverted the matrix once for `theta_err` and discarded that. So `SeriesFit`
> and `FitResult` gained `hessian_cond`, and `FitResult` gained `theta_err_unconstrained` —
> §11.2's parameter metric is specified in unconstrained coordinates and the only SE in
> `FitResult` was natural. **Both are additive diagnostics; `ALGORITHM_VERSION` does not move.**
> The full argument is in PROGRESS.md's *What plan Task 7 established*.

**Behaviour** (D3).

- **`x0` gains a companion `x0_valid` of shape `(B, M)`.** A cell whose validity is false receives
  **no** warm start and takes the moment ladder, and `optimize_series` already records that
  distinction as `InitRung` — **the fallback rung becomes reachable for the first time**, which is
  a per-cell fact the batch layer can aggregate into *"how often did the spiral find nothing"*.
- **Validity is `(B, M)` and never `(B,)`.** The spiral runs **per candidate**, because the
  warm-start key is `(fit_hash, candidate spec_hash)` and a coarse point can be `OK` for one
  candidate and failed for another. A per-point array would force all-or-nothing per cell and
  **quietly discard usable sources**.
- **A NaN sentinel is refused as a design.** An all-NaN row in `x0[b, c, :p]` **is what a failed
  fit legitimately produces**, so *"no valid source"* and *"a failed source"* would be **the same
  bytes** — and the spiral exists precisely to never do the second. **(a0) in a new place.**
- **A non-finite value inside a cell marked valid is a refusable error**, naming the cell **and**
  the candidate. So is a value outside its `ParamSpec`'s diagnostic limits. **A warm start
  arriving from a store is data, not a return value**, and is validated as such.
- **`x0` without `x0_valid` is a hard error, not a default-to-all-valid.** Defaulting hands the
  caller the sentinel behaviour back with no diagnostic. **Both or neither** — and *neither* is
  the existing cold path, which is already correct.

**Invariants.**

- **Shape agreement between `x0`, `x0_valid` and the candidate set is asserted once at entry, not
  per cell.** The `M`-axis-to-candidate correspondence is now load-bearing in **two** arrays where
  it was load-bearing in one, and `fit` truncates positionally at `:p`.
- **A cell with `x0_valid` false is bit-identical to the same cell fit with `x0=None`.** This is
  the property that makes the fallback a fallback rather than a third path.

**Interfaces** (Tasks 3 and 5 bind against these):

    fit(y, t, signal, candidates, criterion, mask=None, objective=..., engine=None,
        x0=None, x0_valid=None, max_iter=...) -> FitResult

**Tests, and the bug each catches.**

- *A batch with `x0_valid` false on some cells and true on others produces `InitRung.WARM_START`
  exactly on the true cells.* Catches the all-or-nothing behaviour surviving the signature change
  — the defect this task exists to remove, and it is invisible in any fixture where validity is
  uniform.
- *A false cell is **bit-identical** to the same cell fit with `x0=None`.* Catches a fallback that
  ladders from a perturbed or partially-applied start. **Compare `theta`, `loglik` and `n_iter`,
  not just `outcome`.**
- *An all-NaN row in a cell marked **valid** raises, and the message names the cell and the
  candidate.* **The fault class does not otherwise occur**, so per (i8) it must be **constructed**
  — a source map that marks a failed fit valid. **This is the check that converts a spiral bug
  from silent to loud, and it is the reason the sentinel design was rejected.**
- *An `inf`, and a finite value outside its `ParamSpec`'s diagnostic limits, raise on the same
  path.* Catches a validator that tests `isnan` alone.
- *`x0` supplied without `x0_valid` raises.* Catches the default-to-all-valid convenience being
  added later "for symmetry with the old signature".
- *`x0_valid` with a wrong `M` raises at entry.* Catches the two-array misalignment silently
  warm-starting candidate `i` from candidate `j`'s optimum — the Task 11 positional shape.

---

## Task 1 — the fit-relevant fields, and the hash cascade

**Goal.** The warm-start settings that can move `θ̂` are **inside `fit_hash`**, and the ones that
cannot are **outside** it. §11.2 states the split; nothing implements it.

> ## CORRECTED 2026-08-24 AT THE TASK'S OWN PRE-FLIGHT. THE MECHANISM WAS ALREADY BUILT, IN 2a.
>
> **`_WARM_START_FIT_FIELDS` has been part of `FIT_RELEVANT_FIELDS` since 2026-08-11, Phase 2a
> Task 1**, together with the audit exclusion and the tests below. Verified by measurement, not
> by reading: the stride, `enabled`, the spiral bound and the interpolation rule each move
> `fit_hash`; the audit settings move neither gate. **Three clauses of this task were therefore
> already satisfied when it was written**, and two more are corrected here:
>
> - **The `GOLDEN_*` constants DO NOT move**, because the hashed field set does not. It moved on
>   2026-08-11 and `_HISTORY` already carries that hop. **Re-deriving them now would be
>   regeneration with nothing to reverse against** — the exact failure the reversal discipline
>   exists to prevent.
> - **`ALGORITHM_VERSION` is NOT bumped here. It is bumped at Task 5**, and the reason is below.
>
> **What this task actually delivered is the classification** — see *What plan Task 1
> established* in [`PROGRESS.md`](../../../PROGRESS.md).

**Behaviour.**

- ~~**`hashing.FIT_RELEVANT_FIELDS` gains: warm start enabled/disabled, the coarse stride, the
  interpolation rule, and the spiral bound and tie-break order.**~~ **ALREADY TRUE since
  2026-08-11.** Each **selects the source point or the start**, so each is fit identity by
  definition — and each is a **REQUEST**, a value the config is authoritative for, never an
  identity it self-reports.
- **The audit's own settings stay out.** Subsample size, stratification, and whether the audit ran
  at all **do not move `θ̂`** — and putting them in would make **re-running an audit invalidate
  the store it audits**, reintroducing exactly what the fit/compat split exists to prevent.
- **The interpolation rule is fixed at nearest-valid and the field still exists and is hashed.**
  A second rule can then never silently share a store. **No config flag selects it** (§11.3): the
  rule moves `θ̂`, so a flag would fragment stores and every switch would invalidate a 10⁷-point
  run.
- ~~**`ALGORITHM_VERSION` is hand-bumped**, per its docstring's rule — this change moves `θ̂` for
  an input that previously fit.~~ **MOVED TO TASK 5, 2026-08-24.** The docstring's rule is *"bump
  when and only when a change alters `theta_hat` or `log_lik` for some input that previously
  fit"*, and **Task 1 alters no `θ̂`** — it writes no fitting code, and adding a field to an
  allowlist moves a **hash**, not an optimum. **The change that moves `θ̂` is Task 5**, where a
  default run begins warm-starting. Bumping here would put the version boundary in a different
  place from the behaviour boundary, which is the same defect one task earlier.
- **A NEW ENTRANT IS CLASSIFIED BEFORE IT IS ADDED**, and the classification is executable rather
  than prose. `FIT_RELEVANT_FIELDS` is the union of `REQUEST_FIELDS`, `STAMPED_IDENTITY_FIELDS`
  and `MEASURED_IDENTITY_FIELDS` and has **no members of its own**, so a field cannot be added
  without choosing a class. **The forbidden fourth class — an identity the config self-reports,
  which `data_uri` and `metamer_version` both were — is declared nowhere**: it is whatever the
  three do not cover, and the three covering everything is what proves it empty.

**Invariants.**

- **Changing the coarse stride moves `fit_hash`**, asserted directly rather than inferred from
  the field being in the allowlist. **(a2): the allowlist is a name, and the hash is the gate.**
  **Already asserted since 2a** by `test_the_warm_start_coarse_stride_moves_fit_hash`.
- ~~**The three `GOLDEN_*` constants move, and are re-derived by hand and verified by reversal** —
  **never regenerated from the failure**.~~ **THEY DO NOT MOVE.** The rule stands and is why:
  a golden is re-derived only when the field set moves, and reversing a hop that did not happen
  proves nothing. `_HISTORY`'s 2026-08-11 hop is the one that covers these fields.

**Tests, and the bug each catches.**

- *Two configs differing only in the coarse stride produce different `fit_hash` and the same
  `run_hash` components that should not move.* Catches the field being added to the allowlist
  without reaching the hash — the defect (a2) is named for.
- *Two configs differing only in audit subsample size produce the **same** `fit_hash`.* The
  **paired negative**, and without it the test above passes for a hash that simply includes
  everything.
- *A stale warm-start source under a changed stride is **refused**, not used.* Needs a
  **positive control** beside it — the same source under an unchanged stride **is** used — or the
  refusal is indistinguishable from a source that never loaded. **(i2).**
  **DEFERRED TO TASK 4, 2026-08-24: it needs a pass-1 store to be stale, and no store exists
  until Task 2.** A hash proves two **configs** agree; it says nothing about what a **store on
  disk** was decimated at, so this test was never Task 1's to write. Task 4's brief already owns
  it and already says the check is **positional and explicit, never inferred**.
- *Each `GOLDEN_*` constant round-trips its hand-derivation.* Catches the constants being
  regenerated from the new failure, which makes the golden test assert only self-consistency.
  **Already present as `test_the_goldens_reverse_through_the_allowlist_history`**, walking
  `_HISTORY` one hop at a time.
- *No field can enter `FIT_RELEVANT_FIELDS` without a classification, and no field carries two.*
  **The disjointness is the assertion**; the coverage is true by construction, because the
  allowlist is the union and has no members of its own. Catches `geometry_hash` being added to
  `REQUEST_FIELDS` on the reasoning that *"the config names the data anyway"* — the `data_uri`
  defect restated as a taxonomy, which moves no hash and fails nothing else.
- *Every request field is reachable from a config file, and no stamped identity is.* Catches the
  `warm_start` flattening dropping a key, checked over the **class** so a sixth setting fails
  even if the per-field parametrization is not extended. **It must not run through `fit_payload`**:
  `_subset` raises on any missing allowlisted field, so through that path the assertion is dead.

---

## Task 2 — pass 1 as a run over a decimated input

**Goal.** Pass 1 is **the existing mechanism applied to a different input** (D11), not a new one.
`isel(y=slice(0, None, k), x=slice(0, None, k))`, its own store, its own bitmap, its own resume.

**Behaviour.**

- **The decimation is index arithmetic on dataset coordinates**, so it is independent of tiling
  and therefore of `--memory-budget` — which is what makes §11.3's guarantee survive a budget
  change.
- **Pass 1's store records the parent's geometry fingerprint and the stride**, and its own
  fingerprint is **derivable from those two**. Otherwise the two stores have unrelated identities
  and **only a filesystem path binds them.**
- **Pass 1's store is a permanent second artifact, not scratch.** It is the **cold audit
  reference** (§11.2) and the `/detail/` default source, so **it cannot be deleted after pass 2
  completes.** Its path is derived from the output path by a stated rule, and the rule is in the
  user-facing documentation, because *"temporary"* is how a second directory is read otherwise.
- **Everything else is unchanged**: tiling, `resume_tile_side`, the completion bitmap, the
  three-hash machinery, `flush_on_sigterm`. **The bit keeps its meaning** — *"every region write
  for the tile returned"* — because pass 1 completes whole tiles of the decimated grid.

**Invariants.**

- **`resume_tile_side` guards each store independently, and a memory-budget change between passes
  is legal.** It produces **different tile sides in the two stores**, which is correct and reads
  as wrong. **One line where the guard is documented**, or someone will "fix" it.
- **No pass-1 code path writes into pass 2's store**, asserted.

**Tests, and the bug each catches.**

- *The decimated store's geometry fingerprint is reproduced from the parent's plus the stride.*
  Catches the two stores being related only by a path — the copy-not-reference invariant's
  opposite failure.
- *A kill during pass 1 resumes pass 1 and refits exactly the outstanding tiles.* Catches pass 1
  being un-resumable, which at 10⁷ points is 156 000 fits.
- *A pass-1 store at one budget resumes at another budget with the same derived side, and refuses
  at a different derived side.* Catches `resume_tile_side` being applied to the budget rather than
  to the side — a resume that is geometrically identical would be refused.
- *A decimated run at stride `k` fits exactly the points `isel` selects, compared against an
  independently constructed index list.* Catches an off-by-one in the decimation, which would
  shift every warm-start source by one cell **and still produce a plausible answer**.

---

## Task 3 — the source map: spiral, tie-break, bound, exhaustion

**Goal.** §11.3's rule, implemented once, in the batch layer, where the coarse grid exists.

**Behaviour** (D3, D12).

- **Nearest valid coarse point in index space**, ties broken **lowest `y`, then lowest `x`**,
  searched outward in a **fixed spiral** until a coarse point with an `OK` fit **for that
  candidate** is found. The tie-break is what makes the choice independent of iteration order,
  hence of tiling, hence of `--memory-budget`.

  > **SETTLED 2026-08-24 AT THE TASK'S PRE-FLIGHT, BECAUSE "IN INDEX SPACE" IS THREE DIFFERENT
  > RULES.** The distance is **CHEBYSHEV**, `max(|dy|, |dx|)`, in **fine** index units, and the
  > radius is **INCLUSIVE** — both taken from `spiral_source`, the instrument that measured D1 and
  > D6, and stated in **no** other document. Euclidean and Manhattan pick different sources, and
  > Chebyshev makes a diagonal neighbour **equidistant** with an axis one, so it is the metric
  > under which the tie-break fires at all.
  >
  > **AND `spiral_bound` COUNTS COARSE INDEX STEPS, NOT FINE CELLS** — the config's docstring is
  > the specification, and `max_fine_radius = spiral_bound * stride`. **The harness searched in
  > FINE units, unbounded, so D1 and D6 describe a run in which the bound never bit.** The unit is
  > fit identity: `warm_start_spiral_bound` is in `FIT_RELEVANT_FIELDS`, so two runs agreeing on
  > the integer and disagreeing on what it counts move `θ̂` under one `fit_hash`.
- **A coarse point's nearest valid coarse point is itself, at radius 0** — a property of the
  geometry, **not an exception in the rule**. Every pass-2 point is warm-started by the same rule
  and **there is no branch for coarse points** (D12).
- **The spiral is bounded and exhaustion is a reported outcome.** On exhaustion the cell is marked
  **invalid** — `x0_valid` false — and takes the moment ladder with the rung recorded. **The
  policy lives here; `fit` only honours validity.**
- **The source coarse index is recorded per point**, which §11.3 asks for and which D12 makes
  load-bearing: it is what lets a downstream reader **filter to self-sourced points and test the
  lattice directly** rather than discovering it as a spatial signal.

**Invariants.**

- **The source map depends on dataset coordinates alone.** Asserted by constructing it at two
  tile sides and comparing **element by element**. This is §11.3's guarantee at the point where it
  could most easily be lost.
- **A cell is never handed a source whose fit is not `OK`.** The paired assertion to Task 0's
  constructed failure.

**Interfaces** (Task 5 binds against these):

    warmstart.source_map(*, shape, stride, coarse_ok, max_radius) -> SourceMap
    SourceMap.index    # (B, M) int64, -1 where exhausted
    SourceMap.valid    # (B, M) bool, the array Task 0's `fit` takes
    SourceMap.radius   # (B, M) int64, for the exhaustion and radius diagnostics

**Tests, and the bug each catches.**

- *At equal distance the lower `y` wins, then the lower `x`.* Constructed at a point equidistant
  from two coarse sources. Catches a tie-break that depends on iteration order, which makes `θ̂`
  depend on tiling and **breaks §11.3 silently** — the run still completes.
- *The map is identical at two tile sides.* Catches the source map being built from tile-local
  indices, which is the single most likely way to lose the reproducibility guarantee.
- *A candidate failed at every coarse point within the bound marks the cell invalid and the fit
  records the ladder rung.* Catches exhaustion falling through to a degraded source instead.
- *A coarse point's own source is itself, at radius 0.* Catches a spiral that starts at radius 1
  — which would make every coarse point neighbour-sourced and **invert the lattice artifact**
  (D12), and which no aggregate saving figure would reveal.
- *The recorded source index reproduces the map.* Catches the diagnostic drifting from the thing
  it describes, which would make the lattice untestable downstream.

---

## Task 4 — the barrier and the cross-store gate

**Goal.** Pass 2 may not start until pass 1 is complete, and may not consume a pass-1 store that
is not the one its configuration describes.

**Behaviour.**

- **The barrier is `completed_tiles(pass1_store).all()`** — an existing, tested predicate. **No
  new completion concept.**
> ## AMENDED 2026-08-24 AT THE TASK'S PRE-FLIGHT: THE GATE IS NOT AN ENUMERATION
>
> The three checks below name **three of `FIT_RELEVANT_FIELDS`' twelve members**, and a warm start
> from a store fitted under a different `objective` is exactly as wrong as one at a different
> stride. **The gate is `parent_fit_hash == config.fit_hash(this run's rollup)`** — one equality
> over the whole allowlist, with the decimated-versus-parent geometry difference **subtracted
> rather than special-cased**. The checks below stay, because they **name** the common cases;
> they no longer constitute the gate.

- **The gate checks the stride explicitly and positionally, never by assuming one was derived from
  the other.** A pass-1 store built at stride 4 consumed by a pass-2 run configured for stride 8
  is a **silently wrong warm start**: every array the right shape, every value finite, every
  status `ok` — the Task 11 wrong-candidate-at-index-1 shape.
- **The gate checks the parent geometry fingerprint and the candidate set**, the latter
  **positionally** (`stored[i] == requested[i]`), reusing the resume gate's rule. A set or sorted
  comparison accepts a permutation.
- **Refusals name what would lift them.** A refusal that says what would lift it is planning
  information; one that does not is a wall.

**Invariants.**

- **An incomplete pass-1 store refuses pass 2 rather than warm-starting from a partial coarse
  grid.** A partial grid produces a *valid-looking* source map with systematically distant
  sources.

**Tests, and the bug each catches.**

- *A pass-1 store missing one tile refuses pass 2, naming the outstanding tiles.* Catches the
  barrier reading "the store exists" rather than "the store is complete".
- *A stride mismatch refuses.* **With a positive control**: a matching stride proceeds. Catches
  the check being present but never reached — (i2).
- *A permuted candidate set refuses.* Catches the positional comparison degrading to a set
  comparison, which writes each candidate's warm start into another's slot.
- *A parent-geometry mismatch refuses.* Catches two unrelated stores being joined by path.

---

## Task 5 — the two-pass driver

**Goal.** `run` grows a two-pass mode: decimate, fit cold, barrier, fit warm. **No new tiling, no
new store schema, no warm-start cache** — pass 1's store **is** the cache (D11), which is why
§11.1's `(fit_hash, candidate spec_hash)` cache key needs no separate implementation.

**Behaviour.**

- **Pass 2 fits every point of the full grid**, warm-started per Task 3's map, **including the
  coarse points** (D12).
- **Warm-starting is disableable by config**, and **whether it was used is recorded in
  provenance**, because it changes the meaning of the output (§11.2).
- **`ALGORITHM_VERSION` IS HAND-BUMPED HERE, IN ITS OWN COMMIT, AND THIS TASK CANNOT SHIP WITHOUT
  IT** (moved from Task 1, 2026-08-24). This is the commit at which `θ̂` moves for an input that
  previously fit, which is the constant's stated trigger.

  **THE BUMP IS UNCONDITIONAL. It is not contingent on `warm_start.enabled`**, and reading it off
  the config is the mistake to avoid. A user who **disables** warm-starting after this task gets
  cold fits again — and their **pre-Task-5 store also holds cold fits, under a `fit_hash` computed
  from the same field values**, so the two would collide. **`ALGORITHM_VERSION` separates ERAS,
  not configurations**, which is the whole reason it is a code constant rather than a config
  field.

  > **THE PARAGRAPH ABOVE IS WRONG AND IS LEFT STANDING WITH THIS CORRECTION, 2026-08-27.** The
  > two populations it names are **both cold and bit-identical**, so a conditional bump would have
  > let them share a `fit_hash` **correctly**. The collision is at the **default**, where
  > `enabled` is `True`. Unconditionality rests on `ALGORITHM_VERSION` being a stamped identity the
  > installed code is authoritative for, on a config-conditional stamp being a second copy of
  > `warm_start_enabled`, and on the bump rule being about a **change** rather than a run. Full
  > form at the constant and in [`PROGRESS.md`](../../../PROGRESS.md)'s *What plan Task 5
  > established*.

  **It closes a defect that has been in the tree since 2026-08-11.** `WarmStart.enabled` defaults
  to **`True`** and is in `fit_hash`, while nothing consumed it. **The store is not silent about
  it** — `store.py` writes `warm_start_used` as an explicit run fact defaulting to `False`, so a
  reader can tell — **but `warm_start_used` is an attr and not a gate**: it is nowhere in
  `fit_hash`, so the resume gate cannot see it. Without the bump, the same config after this task
  produces **warm-started fits under the same `fit_hash`**, a pre-Task-5 store resumes clean, and
  the two populations mix in one store: converged-looking fits at a different optimum, §11.1's
  worst failure mode arriving through the config rather than through a stale cache.

  **The obvious alternative repair is wrong and is named so it is not tried.** `Screening` is
  *"refused at layer 3 until Phase 4"*, and mirroring that for `WarmStart` **would refuse every
  run** — `screening.enabled` defaults to `False` and this defaults to `True`. **Only the bump
  separates the two populations**, and no store can be repaired after the fact.

  **It moves all three `GOLDEN_*` constants**, which is what invalidating stored fits looks like.
  They are **re-derived by hand and verified by reversal**, and `_HISTORY` gains a hop —
  **never regenerated from the failure**. This is the golden movement Task 1 was written to
  expect and did not owe.
- **`--explain` reporting is Phase 5's.** 2c **computes and records** the source-index array, the
  exhaustion count, the ladder-rung distribution and the two passes' wall clocks; §13.4 prints
  them. **Measure in the phase that can, print in the phase that shows.**

**Invariants.**

- **Peak RAM is derivable from the memory budget alone**, unchanged. The two-pass mode adds no
  concurrency whose degree is set by core count. **Pass 1's store is read one tile's worth of
  sources at a time**, not loaded whole — otherwise the source read is a term that grows with the
  field and §11.1's general form is broken through a new door.
- **Output is bitwise identical regardless of memory budget, tile size, thread count and traversal
  order** — §11.3, now with a warm-start path under it for the first time.

**Tests, and the bug each catches.**

- *A two-pass run at two memory budgets produces bitwise-identical `/signal/`.* The guarantee
  §11.3 states, exercised on the path that could break it. Catches a source map or a tile-local
  index leaking the budget into `θ̂`.
- *A killed-and-resumed pass 2 is bitwise identical to an uninterrupted one.* Exit criterion 1 of
  2a, which 2c must not break.
- *Warm-starting disabled produces the same `θ̂` as a cold single-pass run.* Catches the two-pass
  path leaving a residue when it is switched off.
- *Pass 1's store is not loaded whole*, asserted by peak RSS against a bound at a field size where
  whole-loading would be visible. Catches the source read becoming a field-sized term.

---

## Task 6 — the audit's arms, and the four-reading table

**Goal.** Measure hysteresis against a **designed floor**, not against zero.

**Behaviour** (D7). **The four-reading table is written into the audit's own documentation before
the audit runs**, because it is what makes each arm's result interpretable rather than a number
to be explained afterwards.

- **`warm`** — the shipped mechanism.
- **`N2`, the first arm** — cold, started from a perturbation whose **magnitude equals that
  cell's own warm/cold start distance in unconstrained coordinates** and whose **direction is
  random**. Hysteresis is **directional bias toward the neighbour's answer**, so the control must
  move the start the same distance carrying **no information**. **Matched per cell, never on
  average.**
- **`N1`** — cold, started from the moment-ladder start perturbed by a tiny ε.
- **A cold-versus-cold arm does not exist and the reason is recorded**: `fit` has **no stochastic
  component** — every arm of the spike returned one distinct `(n_iter, loglik)` fingerprint across
  three repeats — so re-running cold measures zero **by construction rather than by evidence**.

| `N1` | `N2` | `warm` | the reading |
|---|---|---|---|
| non-zero | — | — | **the surface is deciding.** No start is reliable; the disagreement is a property of the problem |
| zero | non-zero | non-zero | the sensitivity is to **start distance**, not direction. **Benign, not hysteresis** |
| zero | zero | non-zero | **the finding the audit exists to catch** |
| zero | zero | zero | no hysteresis at this fixture |

**Invariants.**

- **`N2`'s seed is recorded.** It introduces the **only randomness in the system**, so it is the
  one place reproducibility can now be lost. It is fit-relevant **for the audit arm** and for
  nothing else.
- **Task 0's `random` arm is not this control and the plan says so**, because *"we already have a
  random arm"* is the obvious wrong shortcut: it starts from **another point's converged
  optimum**, a real attractor in the same likelihood surface, so it **shares the property under
  test** — (j) at the level of an experimental arm.

**Tests, and the bug each catches.**

- *`N2`'s per-cell perturbation magnitude equals that cell's warm/cold start distance*, asserted
  cell by cell rather than in aggregate. Catches a control matched on the mean and mismatched
  everywhere, which would make the floor uninterpretable in exactly the cells that matter.
- *The same seed reproduces `N2` bitwise; a different seed does not.* The paired positive and
  negative. Catches a seed that is recorded but not used — (a2).
- *`N1` at ε = 0 is bit-identical to cold.* Catches the perturbation path adding a difference of
  its own.

---

## Task 7 — the audit's strata and its report

**Goal.** Report per stratum, on fixed boundaries, with nothing that can be quoted out of context.

**Behaviour** (D8, D9, D10).

- **Each metric crosses only axes at its own granularity** — (h2). **Selection disagreement** is
  per **point**, crossed with **selection margin × winning candidate**. **`|Δℓ|`, parameter
  distance and signed-trend disagreement** are per **cell**, crossed with **candidate × `κ`**.
  **Nothing is crossed that does not share a granularity**, which is what dissolved the 81-cell
  problem rather than trading it away.
- **Boundaries are fixed constants sourced from outside this project.** `κ` at **`2²⁶`** and
  **`2⁵²`** — `1/√eps` and `1/eps` for float64 — plus a fourth bin for **`κ` undefined**, because
  a non-positive-definite Hessian falling into the worst bin is **a category error reading as a
  severity**. Selection margin at **2** and **10**, Burnham & Anderson. **A quantile boundary
  means something different in every run**, which is the pooled-number problem one level in.
- **`κ` bins by the COLD arm's value**, stated **at the point of use** and not only in D9.
  Binning by the warm arm would let **the mechanism under test move cells between strata** —
  conditioning on a post-treatment variable, (j7).
- **There is no pooled mean, ever. The headline scalar is the maximum over strata.** A mean
  dilutes and a maximum cannot understate. **Nothing consumes a pooled disagreement figure** —
  §11.2 attaches its one threshold to the iteration saving — **which was checked before the
  decision, not assumed.**
- **A stratum below 30 members reports its member count in place of a rate** — (a2b) for the third
  time. `n = 30` has a binomial standard error of ~9% at `p = 0.5`: **enough to tell rare from
  common, not enough to quote a rate.** The withholding is **visible, never silent**.
- **Failure status is not a stratum, it is a partition.** Inside the both-OK intersection the axis
  is degenerate. What varies is the **outcome flip**, and each rate carries **its own denominator
  at the definition**: **rescue rate** over **cold-failed** cells, **loss rate** over **cold-OK**
  cells, both per candidate.
- **The both-OK intersection's size is reported as a fraction, per candidate.** If warm and cold
  disagree most on hard cells and hard cells fail more often, restricting to both-OK **removes
  exactly the population where disagreement lives** — so every disagreement figure states whether
  it is conditioned on survival.
- **A lint-flagged candidate set is audited, not refused**, and its flagged candidates sit in
  their own stratum. Refusing would deny an audit to the users most at risk; since there is **no
  pooled figure at all**, there is **nothing for label switching to contaminate**.

**Invariants.**

- **The strata definitions are stable across runs.** Candidate identity by `spec_hash`; every
  continuous boundary a constant recorded with the report. **Otherwise per-stratum figures are no
  more comparable than the pooled one was.**

**Tests, and the bug each catches.**

- *No output path emits a pooled mean.* Catches it being reintroduced "for convenience", which is
  how the artifact returns.
- *A 29-member stratum reports a count and no rate; a 30-member stratum reports a rate.* The
  boundary, both sides. Catches an off-by-one that quotes a rate over 29 members.
- *A withheld stratum is visible in the output.* Catches silence and absence being the same bytes
  — the `RSS measurement validity` argument.
- *`κ` binning is unchanged when the warm arm's `κ` is perturbed and the cold arm's is not.*
  Catches (j7) directly. **This is the one most likely to be got wrong later, because both values
  are sitting right there.**
- *The rescue and loss rates use their stated denominators*, asserted against hand-computed values
  on a constructed fixture with known flips. Catches a single "flip rate" over an unstated base.
- *A lint-flagged candidate set produces a per-stratum report with the flagged candidates
  separated.* With a **positive control**: a lint-clean set produces the same report shape.

---

## Task 8 — the 2c exit-criteria suite

**Goal.** One suite, each criterion asserting **a named reading**.

> **2b's criteria 6 and 7 were underspecified for four tasks because nobody wrote down which
> reading they meant** — peak, end-of-tile or end-of-run. **Every criterion below names its
> reading.** That is this task's first requirement, not a stylistic note.

| # | criterion | reading |
|---|---|---|
| 1 | `fit` warm-starts exactly the cells `x0_valid` marks; a false cell is bit-identical to `x0=None` | `theta`, `loglik`, `n_iter` per cell |
| 2 | The coarse stride moves `fit_hash`; the audit's settings do not | the hash, both directions |
| 3 | A decimated pass-1 run fits exactly the `isel` points, and resumes after a kill | the completion bitmap and the fitted index set |
| 4 | The source map is identical at two tile sides | element by element, not summary statistics |
| 5 | A coarse point's source is itself at radius 0 | the recorded source index |
| 6 | An incomplete or mismatched pass-1 store refuses pass 2, naming what would lift it | the refusal message |
| 7 | A two-pass run is bitwise identical across two memory budgets | `/signal/` bytes |
| 8 | A killed-and-resumed pass 2 is bitwise identical to an uninterrupted run | `/signal/` bytes — 2a's criterion 1, which 2c must not break |
| 9 | `N2` is matched per cell and reproduces under its recorded seed | the per-cell magnitude, and the arm's fingerprint |
| 10 | The audit emits no pooled mean, and withholds strata below 30 members visibly | the report's own contents |
| 11 | `κ` bins by the cold arm | binning unchanged under a warm-arm perturbation |
| 12 | The warm-start saving at production length is at or above §11.2's 30% | **iterations and wall clock, both named**, on the shipped mechanism |

**And two criteria are inherited rather than new.** 2b's criterion 6 stays **FAILED** and
criterion 7 stays **FAILED**; 2c does not reopen the residency model and **must not be read as
having done so.**

---

## What 2c does not do

- **The modelling sub-phase.** Closed 2026-08-22 and re-taken 2026-08-23; 2c proceeds on the
  residency model with its stated limitation.
- **`--explain`'s printing.** Phase 5. 2c records the arrays; §13.4 prints them.
- **The Whittle screening pass.** Phase 4; pass 1 ships without screening and the config's
  screening block is refused at layer 3 with a message naming the missing engine.
- **Nested-model chaining within a point.** Deferred with its condition: it has the same
  hysteresis pathology in a different axis and needs its own audit.
- **A multi-level V-cycle.** §11.1 allows it if one level proves insufficient; one level has not.
- **Anything on real altimetry.** Stated once, at the head of this plan, as the standing
  limitation rather than as an omission — **it is the condition D1 is authorized under**, not a
  task 2c declined.
