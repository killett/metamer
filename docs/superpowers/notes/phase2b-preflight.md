# Phase 2b — the (a)–(k) pre-flight, per task

The audit run against each Phase 2b task brief **before** any code is written, and what each
finding changed. Same role as
[`phase2a-preflight.md`](phase2a-preflight.md) played for 2a and
[`phase2-preliminaries-preflight.md`](phase2-preliminaries-preflight.md) for P0–P4.

The method is [`phase1-to-phase2-handoff.md`](phase1-to-phase2-handoff.md) §1. Only the
findings live here; the reasoning behind the decisions being audited is in `PROGRESS.md`'s
2b brainstorm section and in the plan itself.

**Append to this file before each task, not after.** An audit written afterwards is a report
on work already done, and the whole point is that it changes the work.

---

## Pre-plan audit (run 2026-08-14, against the inherited brief)

The audit that produced the plan rather than any single task's. Its subject was
`PROGRESS.md`'s *WHAT SUB-PHASE 2b INHERITS*, design doc §9.4 / §11.1 / §11.4, and the live
code. **Four findings, F1–F4**, stated in full at the head of
[`../plans/2026-08-14-metamer-phase2b.md`](../plans/2026-08-14-metamer-phase2b.md) and
summarized in `PROGRESS.md`'s 2b brainstorm section. In one line each:

- **F1** — nothing maps the budget to `block_bytes`; exit criterion 7 is unsatisfiable at
  scale as a result. (a2) at an arithmetic boundary: a name used as though it were a gate.
- **F2** — `memory.bytes_per_series` describes the batched trust-region deleted at Task 19,
  and the measurement that validated it drove a batched evaluation. **Promoted as (j2)** and,
  with F4, as **(a6)**.
- **F3** — the output-slot term omits four things `fit` holds. With F2 it is (a) inside a sum:
  **two errors of opposite sign, invisible to any check on the total.**
- **F4** — `Backend` names two architectures and production has neither. **Promoted as (a6).**

Five pre-flight lines were promoted out of this audit and the brainstorm that followed it:
**(a6)**, **(j2)**, **(j3)**, the two-sided restatement of the standing memory check, and the
separate-commits attribution rule. All five live in the handoff, not here.

---

## Task 0 — the memory formula corrected

Run 2026-08-14 against the task brief in
[`../plans/2026-08-14-metamer-phase2b.md`](../plans/2026-08-14-metamer-phase2b.md), the live
`core/memory.py`, `core/fit.py`, `core/optimize.py` and scipy 1.18.0's own source. **Six
findings, and four of them are arithmetic in numbers this project has already accepted.**

### (a) inside a sum — the corrected output-slot term is 217 B/candidate, not 209

The brief names four things `out(M, p, k_β)` omits. Summed at the §9.4 worked example
(`p_max = 4`, `k_β = 4`) they are `theta_unconstrained` **+32**, `n` **+8**, the `init_rung`
object pointer **+8**, and `n_iter` as int64 rather than uint16 **+6** — **+54 per candidate**,
against the published formula's 163. That is **217**, and `PROGRESS.md`'s inherit table and the
plan's F3 line both say **209**, i.e. **+46**, which is the same list with one 8-byte member
dropped. Hand-built from `fit.py:197-209`, field by field:

    out(M, p_max, k_β) / M = 24·p_max + 16·k_β + 57
                           = 3·p_max·8   theta, theta_unconstrained, theta_err
                           + 2·k_β·8     beta, beta_err
                           + 5·8         loglik, k, n, n_eff_bic, n_eff_trend
                           + 8           n_iter, int64
                           + 8           init_rung, one object pointer per cell
                           + 1           outcome, uint8

At M = 12 the difference against the brief is **+96 B/series**. **This is the finding the brief's
own rule predicted**: F2 and F3 were found by verifying terms rather than the total, and the
correction to F3 was then itself carried as a total.

### (a6) four more descriptions survive the deletion, and the brief names one

The brief's *Watch* names `Backend`'s importers as `batch/tiling.py` and `batch/run.py`.
Measured: **four in `src/`** — `batch/tiling.py`, `batch/validation.py`, `batch/run.py` and
**`bench/spike.py`** — plus three test modules. `bench/spike.py` is the one that matters beyond
a count: it sits on the far side of the `bench/`-versus-`core` layering question `PROGRESS.md`
records as owed, and it is the only caller of `bytes_per_series` outside the tests.

And four more descriptions have the same subject as `Backend` and are not mentioned at all:

- **`streaming_overhead_bytes`.** Path A's `(B, 1+k_β)` row is per-series only if the engine is
  handed `B > 1`. Through `run()` it is handed `B = 1` (F4), so the row is **40 B, a constant**,
  by exactly F2's argument. It is inside the published 8722 and, since `8722 + 552 − 1056 =
  8218`, it is **still inside `PROGRESS.md`'s corrected figure** — while the plan's own corrected
  shape, `B × (N×9 + X_term + out(...)) + placement_constant`, has no room for it. The plan's
  formula and the plan's arithmetic disagree by 40 B/series.
- **`bytes_per_series`.** §9.4's model *is* the batched trust-region's shape; keeping it as "the
  model to aim at" is a description of the deleted architecture with a forwarding address.
- **`thread_state_bytes`** and **`tile_bytes`**, which exist only to carry `Backend`'s two-shape
  claim.
- **`_solver_state`'s optimizer term** — F5 below, and it is in the same function as F2.

### F5 — the optimizer term describes the deleted trust-region too, and understates by 11×

`_solver_state` charges path A `(p² + 4p)·8 = 256 B` for a *"dense quasi-Newton trust-region
model"*, which is §8.3's deleted design, and path B `22p·8 = 704 B` for an L-BFGS history.
**Production runs neither.** `optimize.py:531` is
`minimize(negative, u0, jac=jac, method="L-BFGS-B", options={"maxiter": max_iter})`, and it runs
for **both** engines, because `fit` drives `optimize_series` whichever engine it holds.

Read out of scipy 1.18.0's `_lbfgsb_py._minimize_lbfgsb`, at the default `maxcor = 10`:

    wa = zeros(2·m·n + 5·n + 11·m² + 8·m, float64)      # 1280 doubles = 10 240 B at n = 4

The **`11·m²` term dominates and does not depend on `p` at all**, so `22p·8` is not the same
quantity with a different constant — it is the wrong shape. With the bound, gradient and integer
workspaces the optimizer is **11 144 B** at the worked example and the whole placement constant
is **11 984 B against the formula's 1056 — 11.3×**.

**It is a constant, so it does not move `tile_side` measurably** (at a 10⁹ budget the side is 347
with it and 347 without). **It is exactly the term Task 4's intercept and Task 7's cross-check
measure**, so it has to be right in kind before either runs, and a 1056 B intercept model against
an ~12 kB reality is a discrepancy someone would reconcile.

### (a4) the published cascade — two of its rows do not follow from its own numbers

1. **`PROGRESS.md`'s row "corrected ≈ 8218 B → 361" is not arithmetic.**
   `floor(sqrt(10⁹/8218)) = floor(348.9) = 348`. **361 is the COMPILED backend's published
   side** at 7634 B/series (`validation.py`'s docstring, `test_validation.py:430`) — a figure
   taken from the neighbouring table rather than computed from the corrected per-series. The
   step it belongs to, *"the side gets smaller"*, is right; the number contradicts it.
2. **The cascade is headed "1 GiB" and every side in it is a 10⁹ number.** At a true 1 GiB,
   8722 B/series gives **350**, not 338. Every published side in this project — 338, 186, 361,
   189 in `validation.py`, `tiling.py`, `test_memory.py`, `test_tiling.py`, `test_validation.py`
   — is computed at `10**9`, while **`run.py:348` converts the user's budget with `1024**3`**.
   So the runner's "1 GB" is **7.4% more bytes** than the published worked example's, and the two
   have never been the same number. **Not Task 0's to fix** — the budget is Tasks 2 and 3 — but
   it is theirs to resolve, and Task 9 must not restate a side without its unit.

Recomputed here, by hand, at `d = 3, k_β = 4, p_max = 4, N = 630, M = 12`, budget `10**9`:

| step | per-series | side (shared) | side (per-point) |
|---|---|---|---|
| as published | 8722 | 338 | 186 |
| F3 corrected to 217 B/candidate | +648 | — | — |
| F2/F4/F5: solver state is a constant | −1056 | — | — |
| (a6): the streaming row is a constant too | −40 | — | — |
| **corrected** | **8274** | **347** | **187** |

### (a5) the brief's interface list contradicts the brief's behaviour

    memory.resident_bytes_per_series(*, placement, d, k_beta, p_max, n_time,
                                     n_models, per_point_design=False) -> int

Under the correction the per-series figure depends on **neither `placement` nor `d`**: `d` enters
the formula only through the solver state, and this task's whole content is moving the solver
state out of the per-series term. A signature keeping both asserts a dependence the formula
denies, and it makes *"the solver term does not scale with B"* a property of a test rather than
of the shape.

**Deviation taken: both parameters dropped from `resident_bytes_per_series`.** They stay on
`solver_state_bytes` and `resident_tile_bytes`, where they are real. **Task 2's
`tiling.tile_side_for(*, budget_bytes, floor, placement, d, ...)` keeps them and is right to** —
its block arithmetic subtracts the constant, so it needs the constant's inputs.

### (i5) the tempting repair here moves a published pair, and there is a test built on it

`test_validation.py:427-437` asserts that the two backends give **different** published pairs —
338/186 against 361/189 — and that the refusal message names which. Under the correction the
per-series figure is placement-independent, so **the subject of that test ceases to exist**, and
the repair that keeps it green is to keep a placement-dependent per-series term. That is the
defect. Replaced by its inverse — the pair is placement-**in**dependent — whose mutation is
multiplying the solver state by `batch`, and which bites.

Same class, five live assertions on the published side (`test_memory.py:582`,
`test_tiling.py:188`, `test_validation.py:391`, `:429`, `:430`). Every replacement value in this
task is re-derived by hand in the table above and the derivation is recorded beside the
assertion. **None was read off a failure.**

### (a2) the memory engine label — verified, and the pair really does collide

`kalman.py:107` and `compiled.py:208` both set `engine_id = EngineId.KALMAN`. So a memory key on
`EngineId` cannot separate two engines whose workspaces differ, which is the brief's claim,
confirmed by reading rather than assumed. `MemoryEngineLabel` is introduced with a test that the
two map to **different** memory labels while sharing one `EngineId` — falsifiable today, before
the driver that needs it exists (`shared_with` precedent).

### A per-series term the corrected formula still does not charge — an input to Tasks 2 and 7

The formula is **resident**, not peak. `fit` also holds per-candidate temporaries that **do**
scale with B, allocated inside the candidate loop and dropped at its end: `var_gls` and
`var_white` at `(B,)` each, the `np.nan_to_num(theta[:, c, :p])` copy, and `hydrate`'s
`(B, p_total)` block. **Estimated at order 100 B/series, ~1.2%** — and the estimate matters:
16 B/series leaves the worked example at 347, while 100 B/series gives **345**.

**Two grid points from a term nobody has measured**, so it is recorded as an estimate rather
than folded in. Task 7 measures it. **And it is a slope term, not a constant, which is the
argument for Task 2's headroom being a FRACTION of the budget rather than a fixed number of
bytes** — a constant headroom would be right at one B and wrong at every other.

### (c), (i2), (j2), (k) — clean, with one addition each

- **(c)** memory.py's exits enumerated: `tile_side` `ValueError`; `measure_evaluation_rss_slope`
  `ValueError`; `_measure_child` `RuntimeError`. Added: `solver_state_bytes` raises on
  `threads < 1`, since a thread count of zero silently zeroes the whole term under `PER_THREAD`.
- **(i2)** the reachability negative is paired with two positives: the same placement computed
  directly against a hand-derived number, and a real `run()` whose every `optimize_series` call
  is recorded and carries a leading dimension of 1.
- **(j2)** `data_and_workspace_bytes_per_series` and `measure_evaluation_rss_slope` drive a
  **batched evaluation** and are now labelled as measuring an instrument's workload rather than
  production's. They are kept because Task 7 needs them as the cross-check whose disagreement
  **is** F2's magnitude.
- **(k)** nothing here depends on process-local state; the formula is arithmetic. The
  measurement functions already spawn per point.

---

## Task 1 — the floor, cgroup-aware total RAM, `tile_side_basis`, `SCHEMA_VERSION` 4

Run 2026-08-15 against the task brief, `core/machine.py`, `batch/store.py`, `batch/resume.py`,
`batch/threads.py`, design doc §11.4 and §13.4, and this machine's `/sys/fs/cgroup`. **Nine
findings; three change the interface and two are other tasks' to own.**

### (i3) EVERY test the brief lists for the floor is a relation, and relations pass on two absences

*"The post-warm floor exceeds the pre-warm floor"* and *"the floor with the input open exceeds
the floor without it"* are both `a > b`. Each is satisfied by two readings that are absent, two
that are zero, and two that are wrong in the same direction — which is exactly the shape that let
`assert fit_moved == compat_moved` pass against a payload flattening that dropped the field.

**Every rung is asserted against its own absolute band first**, from the ladder recorded on
2026-08-14 (73.8 / 162.4 / 170.7 / 213.9 / 221.5 MB), `machine`-marked, and the relations are
kept as additional checks rather than as the evidence.

### The floor is measured with the WRONG INSTRUMENT if it is measured the way the brief argues

The brief requires *"every floor measurement runs behind a bare launcher"* and justifies it by
watermark inheritance — **which is a property of `peak_rss_bytes` alone.** The recorded ladder is
`current_rss`, and current RSS is not a watermark and not inherited, so under that instrument the
launcher buys nothing and the stated reason is wrong.

**But the launcher is still required, for the opposite reason.** Exit criterion 7 asserts **peak**
RSS at or below the budget, and Task 2 computes `block = budget − floor − headroom`. The quantity
that must come out of the budget is therefore the **peak** of everything that is not the tile —
import transients, numba's JIT, zarr's decompression buffers on the first chunk read — and a
current-RSS floor omits exactly those and overcommits by their size.

**Deviation: `FloorReport` carries both instruments.** The ladder stays in current RSS, so it is
comparable to the recorded series and to §11.4's own figures; `peak_bytes` is the child's own
high-water and is what Task 2 subtracts. The bare launcher is mandatory because of the second,
and the docstring says which instrument answers which question.

### (a2) `total_ram_bytes()` and `ram_basis()` are two functions over one fact, and nothing couples them

The brief's interface has them separate. Two independent readers of `/sys/fs/cgroup` can
disagree — a divergent implementation, a limit written between the two calls, a caller that
computes the basis on one machine and the bytes on another — and the failure is silent: the
store's provenance records **a basis that did not produce the number beside it.**

**This is (a2)'s fourth fact turned around.** That fact says the thing that populates an identity
must not be the thing being identified; this says **the label must be produced by the same
computation as the value**, or it is a name rather than a report.

**Deviation: one private `_resolve_total_ram() -> tuple[int, str]`**, with both public functions
delegating to it. The test is that on a constructed cgroup limit **both move together** — a
mutation that lets `ram_basis` read the filesystem independently bites.

### (i2) "the floor is never cached" has no positive control at this task, and the obvious test is unfalsifiable

No cache exists until Task 5, so *"no cache entry was written"* is satisfied by a caching
mechanism that does not exist. The falsifiable form is **"two calls re-measure"**: count the child
spawns and assert the second call spawns again. **Memoization is the mutation and it bites**,
which *"no file appeared"* never could.

### (g)/(a5) the cgroup change moves `run_hash`, and this machine cannot see it

`machine.fingerprint()` is `machine_fingerprint(cpu_model(), physical_cores(),
total_ram_bytes())`, and it reaches `run_hash`. Making `total_ram_bytes` cgroup-aware therefore
**changes `run_hash` for every store built inside a memory-limited container** — correctly, since
that is the gap the brief names, and it is a behaviour change rather than a refinement.

**And it is invisible here.** `/sys/fs/cgroup/memory.max` is `max` on this box, measured
2026-08-15, so the host and cgroup readings coincide, no golden hash moves, and **every test in
this suite would pass against a `total_ram_bytes` that ignored cgroups entirely.** That is the
same shape as the defect being fixed: the environment cannot express it, so the fixture must.
Recorded, with `psutil` reporting **16 535 728 128 B** total and **5 053 812 736 B** available
today against 7.13 GB on 2026-08-14 — available varies, total does not.

### (c) exits enumerated

`measure_floor`: one `RuntimeError`, when the child exits non-zero, with its stderr attached —
including the case where the input cannot be opened, since the open happens **inside** the child.
A silent zero here reads as a floor of nothing, which is a plausible number that would make the
whole budget available to the tile. `_resolve_total_ram`: **no raise** — an unreadable or absent
cgroup file is the host basis, not an error, because the absence is the common case.

### Blast radius of `SCHEMA_VERSION` 4, counted rather than estimated

`REQUIRED_ATTRS` gains `tile_side_basis`; `provenance_attrs` gains a parameter and has **six call
sites** (`batch/run.py`, its own definition, four in `tests/test_store.py`, plus
`tests/test_resume.py`'s fixtures); `tests/test_write.py:484` pins `SCHEMA_VERSION == 3` by name;
`resume._check_schema` needs no change but its test at `test_resume.py:307` uses
`SCHEMA_VERSION - 1` and keeps working by construction.

### Found during implementation, not by the audit: Task 1 breaks 2a's exit criterion 1

**The pre-flight did not find this and the full sweep did**, which is the honest record.
*"The floor is measured fresh every run"* plus *"both floors are recorded in provenance"* against
2a's criterion 1, *"a killed and resumed run is byte-identical to a clean one"* — two runs of one
configuration measure two different floors, the root `zarr.json` differs, and every array, chunk
and other attr is identical.

**(a5) with a new shape: the conflicting constraint is an exit criterion from an EARLIER
SUB-PHASE.** Nobody is reading 2a's closing table while writing a 2b brief, so the conflict had no
reviewer. Promoted into the handoff under (a5).

Repair: files still compared byte for byte; root attrs compared key by key against a named
`_MEASURED_ATTRS = {"floor"}`; **and the excluded key asserted present in both stores**, so the
exclusion cannot decay into an absence.

### Found during implementation: a recompute has no basis of its own

`--reuse-fits-from` reads the tile side back out of the source rather than deriving one, so
writing `DEFAULT` would claim a derivation that did not happen. The new store copies the source's
basis. **Its test is (i7)-flagged in its own docstring** — until Task 5, `DEFAULT` is the only
writable basis, so "copy the source's" and "write DEFAULT" agree on every store this suite can
build, and Task 5 owns moving the fixture off that point.

### Two findings that belong to other tasks, reported rather than carried (Task 1)

- **Design doc §11.4 says the calibration cache has *"an explicit expiry"*; the 2b plan settled
  NO expiry**, on the ground that time does not cause the change it stands in for — (a2) at a
  cache key. **A live disagreement between the design doc and an approved plan, recorded
  nowhere.** Task 5 implements it; **resolved in the document now** rather than left for an
  implementer to discover, per the precedence rule.
- **§13.4 quotes `28 882 B/series` and `tile_side` 186 for the per-point regime** — a cascade site
  Task 0's count did not list, because the count was of `338`. The corrected pair is **28 434 and
  187**. Task 9's to fix; recorded here so its count is right when it runs.

---

## Task 2 — `block_bytes`, the smooth base, and the refusal

Run 2026-08-15 against the task brief, `batch/store.py`'s chunk and shard machinery,
`batch/tiling.py`, `batch/run.py`, and a measured sweep of the divisor structure. **Seven
findings; two of them change what the task can be.**

### THE DIVISOR MEASUREMENT WAS TAKEN ON A REPRESENTATIVE ARRAY AND THE WORST IS TWICE AS BAD

`PROGRESS.md`'s divisor note computes on `theta` — float32 × `P_total` = 160 B per cell — and
reports **169 rows, a 9.1 MB chunk, 2.3× the target** at side 338. The worst array is
**`warmstart/theta_unconstrained`**, float64 × `P_total` = **320 B per cell**, and at the same
side it takes the same 169 rows for **18.3 MB — 4.57×**. Measured, per array, at M = 12, C = 2,
`k_β` = 4, `P_total` = 40:

| side | worst array | chunk | ratio |
|---|---|---|---|
| 338 | `theta_unconstrained` | 18.3 MB | **4.57×** |
| **347** (Task 0's corrected side) | `theta_unconstrained` | **38.5 MB** | **9.63×** |
| 336 | `beta` / `delta_ic` / `log_lik` | 5.42 MB | 1.35× |
| 272 (Task 2's derived side) | `beta` / `delta_ic` / `log_lik` | 7.10 MB | 1.78× |

**This is exactly what the brief warned about, confirmed by measurement rather than by argument**,
and it is why the test asserts the worst array rather than a representative one.

### AND TASK 0's CORRECTED SIDE IS PRIME, WHICH IS THE PATHOLOGICAL CASE

**347 is prime.** So is 349, and so is 353. `_chunk_side`'s own docstring names a prime tile side
as the case with no useful subdivision — its only divisors are 1 and itself — and the corrected
number landed on one. Without a base the published side gives a **38.5 MB chunk against a 4 MB
target**. The base is not a nicety here; it is what makes the corrected number usable at all.

### THE BASE IS 16, CHOSEN WITH THE MEASURED STRUCTURE IN FRONT OF IT

Swept over every derived side from 100 to 600, worst-case ratio across all arrays whose shard can
reach the target, against mean rounding loss in tile **area**:

| base | worst | median | area loss |
|---|---|---|---|
| 8 | 3.41× | 1.57× | 2.3% |
| 12 | 2.12× | 1.52× | 3.4% |
| **16** | **1.99×** | 1.49× | **4.5%** |
| 24 | 1.99× | 1.39× | 6.7% |
| 32 | 1.99× | 1.47× | 8.9% |
| 60 | 1.75× | 1.21× | 16.4% |

**16 is the smallest base that reaches the 1.99× floor**, and nothing below 60 improves on it.
24 matches its worst case with a better median and costs half again as much area. The brief's
*"16 gives a set dense low and sparse high; 12 is denser in the middle"* is true of the bases'
own divisors and **is not what decides** — the admissible window is set by the array, and the
sweep is what answers.

### THE TARGET IS UNREACHABLE FOR SEVEN OF THE EIGHTEEN ARRAYS, AND ASSERTING A BAND ON THEM FAILS CORRECTLY

`point_outcome` is one byte per cell: a whole 336-side shard is **113 kB**, so no subdivision can
reach 4 MB and `_chunk_side` correctly returns the whole side. `n_valid`, `selected`, `outcome`,
`iterations` and `ic_best` are the same shape of case. **A test asserting "achieved chunk bytes
are inside the target band" over every array fails on these for a correct reason**, so the check
partitions: arrays whose shard reaches the target are held to the band; the rest are asserted to
be exactly one chunk per shard, which is the right answer and not a fallback.

### THE BUDGET'S UNIT IS DECIDED HERE: `memory_budget_gb` IS 10⁹ BYTES

Four reasons, and the fourth is the one that settles it:

1. The field is named `_gb`, and SI GB is 10⁹. A `1024**3` field is named `_gib`.
2. Every published tile side in this project is a 10⁹ number.
3. `PROGRESS.md`'s Hardware table already reports **16.54 GB**, which is the SI reading of this
   machine's 16 535 728 128 B — so the project already speaks SI when it writes GB.
4. **Changing `run.py`'s `1024**3` to `10**9` LOWERS the budget by 7.4%**, which is the safe
   direction against a constraint the design doc calls hard. The opposite fix raises it.

**Consequence, stated rather than discovered:** a store created before this change carries a
tile side derived from 7.4% more bytes, so a resume derives a smaller side, hits
`completion.resume_tile_side`'s *stored > derived* arm and **refuses**. Harmless today for
exactly the reason `SCHEMA_VERSION` 4 was harmless — no store outside the suite predates either —
and not harmless later.

### THE FLOOR MAKES `tile_side` INPUT-DEPENDENT, WHICH IT HAS NEVER BEEN

The floor is measured **with the input open**, so the derived side now depends on the store being
read — its handles, its consolidated metadata, its chunk grid. `tile_side_for` therefore takes a
`FloorReport`, and **the published number needs a pinned floor among its preconditions.** Task 9's
precondition list grows by one, and it is the only one of them that is a measurement.

### AND THE CONSEQUENCE THE BRIEF DID NOT ANTICIPATE: EVERY FIXTURE THAT PINS A TILE SIDE BY CHOOSING A BUDGET BECOMES IMPOSSIBLE

Four test modules pin a tile side of 1 or 2 with `memory_budget_gb = 2e-6` — **2000 bytes** — by
exploiting exactly the defect F1 names: the budget *was* the block. Under
`block = (budget − floor) × (1 − headroom)` a 2000-byte budget is **below the floor and refused**,
which is correct.

**And no choice of budget can replace it.** For a side of 1 the block must land in a window about
three series wide — ~2.6 kB on these fixtures — while the measured floor varies by megabytes
between runs. **The window is a thousand times narrower than the jitter**, so a fixture that
selects a tile side through a budget cannot work against a measured floor at all.

In-process tests are already covered by `run(floor=...)` and conftest's stub. **The tests that
drive `python -m metamer` in a subprocess are not**, and criterion 1 (SIGKILL between tiles),
criterion 2 (two budgets, four tiles against one) and the preemption test all need multiple
tiles on a 2×2 grid.

**Resolution: `METAMER_FLOOR_BYTES`, read by `run()` when no floor is supplied**, documented with
its hazard — it defeats F1's guarantee, and it exists because a measured floor makes an
out-of-process fixture unable to pin a side. **It records itself**: the override produces
`components = {"override": N}` in provenance, so a store built with one is identifiable from its
own attrs with no new field. It also answers a real production case, which is why it is a
parameter rather than a test hack: a sandbox that forbids spawning cannot run the probe at all.

### (i3), (c) and (a5), briefly

- **(i3)** *"a tile at the derived side plus the floor is within the budget"* is a relation and
  passes on two zeros. The derived side is asserted against its own hand-computed value first.
- **(c)** two refusals, and their order matters: `block_bytes_for` refuses a budget at or below
  the floor **before** `tile_side` refuses a block that holds no series. The second must never be
  the one a user meets, because its message names bytes per series rather than the floor.
- **(a5)** the brief says the refusal fires on the **resolved** budget so a `None` config cannot
  bypass it. At Task 2 `memory_budget_gb` still has a pydantic default of 1.0, so there is no
  `None` to bypass with; **that test is Task 3's and is recorded as owed rather than written
  here against a state that cannot occur.**

---

## Task 3 — the `--memory-budget` default, and the unset sentinel

Run 2026-08-15 against the task brief in
[`../plans/2026-08-14-metamer-phase2b.md`](../plans/2026-08-14-metamer-phase2b.md), the live
`config/model.py`, `batch/run.py`, `batch/store.py`, `batch/completion.py`, `batch/tiling.py`,
`batch/validation.py`, `core/machine.py` and `core/hashing.py`. **Eleven findings. Two are
descriptions of a defect Task 2 closed that still name Task 3 as their owner, and one is a
store guard whose "required" and this task's sentinel cannot both hold.**

### (a6) TWO DOCSTRINGS STILL CARRY THE UNIT DEFECT AS OPEN, AND ONE OF THEM PUBLISHES A SUPERSEDED SIDE AS CURRENT

Task 2 decided the unit and corrected `run.py` to `10**9`. Two descriptions of the old state
survive it, and **both name Task 3 as a co-owner**, so a reader arriving here is told to resolve
something already resolved:

- `batch/tiling.py`'s module docstring: *"THE BUDGET'S UNIT IS AN OPEN DEFECT … `run.py`
  converts the user's `memory_budget_gb` with `1024**3` … Tasks 2 and 3 own the budget"*.
- `batch/validation.py`'s `_WORKED_EXAMPLE_BUDGET` docstring: *"`run()` converts
  `memory_budget_gb` with `1024**3` … Recorded 2026-08-14 as an open defect owned by Tasks 2
  and 3"*.

**And the same tiling docstring states the tile side as `347` shared / `187` per-point**, which
is Task 0's pre-floor pair. Since Task 2 the answer is **272 / 144** and its one home is the
handoff's §3. This is the *"source docstrings are the half a documentation sweep misses"*
instance for the third time, at the position §11.1 held when it carried the superseded 445:
**`tiling.py`'s docstring is what a tiling implementer opens first.**

Repair: strike both unit notes, and **delete the pair rather than update it** — precedence says
a measurement stated twice loses a copy, and the handoff's §3 is the copy that stays.

### (a5) AN AVAILABILITY READING MUST NOT REACH THE STORE, AND THE BRIEF DOES NOT SAY SO

The brief requires availability to be **read and reported**. It says nothing about provenance,
and provenance is where the analogous decision went wrong one task ago: Task 1 put a per-run
measurement (`floor`) in the root attrs and **broke 2a's exit criterion 1**, which cost a named
`_MEASURED_ATTRS` carve-out to repair.

Availability is worse on the two axes that matter. It is a measurement of **ambient machine
state** rather than of this process, and it has **no consumer at all** — nothing reads it, now
or in any planned task. Measured spread on this one machine: **7.13 GB (2026-08-14, the
Hardware table), 5.05 GB (2026-08-15, Task 1), 2.59 GB (2026-08-15, taken while the full sweep
was running)** — a **2.75× range in two days**, which is also the measurement that justifies the
total-RAM default rather than an argument for it.

**So: reported, never stored.** The distinction to keep is that the *total*-RAM figure the
warning compares against **is** recorded — through the resolved budget and through
`machine.fingerprint()` — because it is stable across runs on one machine. **Stable measurements
may reach a store; ambient ones may not.**

### (a0) THE SENTINEL IS `None`, AND `REQUIRED_ATTRS` READS `None` AS MISSING

`store.create_store` refuses on `attrs.get(key) is None`. So the one provenance key whose `None`
**is its meaning** — "the config did not name a budget" — **cannot be a required attr**:
"required" and "nullable" are incompatible in that guard, and adding it would refuse every
defaulted run.

That leaves absence and null indistinguishable to any reader using `attrs.get`, which is (a0)
exactly. **The mechanism that closes it is the schema version**, not the required list: a bump
makes a store written before this task **refused** rather than read as "the budget was
defaulted". So `SCHEMA_VERSION` goes to **5**, the ledger records the reason, and the ledger's
own rule — *each bump's field is a REQUIRED attr* — acquires its first stated exception, with
the exception's reason beside it.

### (a1) THE DEFAULT WIDENS THE RE-DERIVATION HAZARD, AND THE EXISTING GUARD'S MESSAGE THEN NAMES A FLAG NOBODY TYPED

The tile side is re-derived at every resume — the (a1) instance from Phase 2a Task 10. Until now
its input was in the config, so **two resumes of one config derived the same side on any
machine**. From this task the derived side is a function of the machine's **total RAM**, so a
defaulted store resumed on a smaller machine hits `completion.resume_tile_side`'s *stored >
derived* arm and refuses.

**The arm is correct and the message is not.** It reads *"the budget that produced them was
4.133932032 GB … Either raise `--memory-budget` to at least that, or write a new store"* for a
user who never typed a budget, and the number is an artefact of the *other* machine's RAM.
**(c3)'s phrasing rule, one register over**: a resolution that names an operation the user is
not performing is worse than none. The message names the default when the store records a null
request, which is what the new provenance key is for beyond bookkeeping.

### (c3) `_with_memory_budget`'s REFUSAL IS PHRASED FOR THE COMMAND LINE, AND THE DEFAULT PATH IS A SECOND CALLER

`run._with_memory_budget` re-validates an overridden budget and prefixes its layer-2 message
with `--memory-budget: `. The default resolution wants the same re-validation and **must not
borrow the phrasing**. It cannot fire today — the default is positive for any positive RAM
reading — and that is precisely the shape of message defect that ships: unreachable,
correct-looking, and wrong on the first machine that reports something strange. The caller
supplies the phrase.

### (g) THE TYPE CHANGE IS HALF OF "A `None` CANNOT BYPASS THE REFUSAL", AND IT IS THE STATIC HALF

Making the field `float | None` turns every consumer that expects a `float` into a mypy error
until it narrows. There is exactly one production consumer of the value —
`run.py`'s `int(config.memory_budget_gb * 10**9)` feeding `tile_side_for` — and it stops
type-checking until the resolution lands above it. **So the owed test is the runtime half of a
claim whose other half is checked by `pixi run typecheck`**, and both are worth having: mypy
cannot see the store's copy in `provenance_attrs`, whose value is typed `Any` the moment it
enters the attrs mapping.

**And that copy is guarded one layer up rather than directly.** `provenance_attrs` calls
`config.run_hash(...)`, which refuses an unresolved budget, so a store can never record a null
in `memory_budget_gb`. The two are cross-commented, per the doubled-guard rule.

### (a2) BOTH PROVENANCE FIELDS ARE REQUESTS, AND THE IDENTITY THEY REST ON IS ALREADY WIRED

Classified before checking, per (a2). `memory_budget_requested_gb` **is** the request, so
self-reporting is correct and there is nothing to verify. The resolved `memory_budget_gb` is
also a request — it is what the run asked the tiler for — even though its default derives from
total RAM, which is an identity. **That identity is already populated from the platform**:
`machine.fingerprint()` reads `total_ram_bytes()` and reaches `run_hash`, wired at Task 1
before the calibration cache made it a gate. **No new identity field, so (a2)'s four facts have
nothing new to check** — and the same config on two machines yielding two `run_hash`es is that
wiring working, not nondeterminism.

### (a4) THE FRACTION, THE FIGURE THE SANITY CHECK USED, AND THE SIDE IT DERIVES

The brief requires a policy fraction sanity-checked against this machine's measured available
RAM, **naming which figure was used**. It is **7.13 GB, the Hardware table's, measured
2026-08-14**.

| fraction | budget on this box | against 7.13 GB available |
|---|---|---|
| 0.5 | **8.268 GB** | **above every availability reading ever recorded here** — 7.13, 5.05 and 2.59 |
| **0.25** | **4.134 GB** | below all but the sweep-loaded 2.59 GB reading |
| 0.125 | 2.067 GB | below all three, and throws away half the usable tile |

**0.5 is what decides the value, not taste**: a default that exceeds availability on an idle
machine warns on **every** run, and a warning that always fires is not a warning. **0.25**, with
the same asymmetry the headroom has — too high kills the process, too low costs runtime.

Derived side at the default, hand-computed against this machine's **measured 228.2 MB floor**:
`(4 133 932 031 − 228 200 000) × 0.85 = 3 319 872 226`, less the 11 984 B solver constant,
÷ 8274 B/series = **401 240.1 series**, and `633² = 400 689 ≤ 401 240 < 401 956 = 634²`, so the
raw side is **633** and the base takes it to **624** (39 × 16). Brackets against Task 2's
published ladder — 4 GB → 608, 8 GB → 880 — and 4.134 GB sits just above 4 GB. **Recomputed by
hand, not read off the implementation.**

**And a float note, stated so nobody "fixes" it.** The budget round-trips through a GB float, so
`int(0.25 × 16 535 728 128 / 10⁹ × 10⁹)` is **4 133 932 031 B — one byte below `total // 4`**.
Deterministic, invisible against a 4 GB budget, and not worth a special case.

### (i7) THE LOW-AVAILABILITY FIXTURE MUST BE PLACED WHERE AN AVAILABLE-RAM DEFAULT WOULD DIFFER

*"A low-availability machine still derives the same side"* is satisfied for free wherever the
availability figure and the total figure round to the same side — which, with conftest's 1 MB
stub floor and a 2×3 grid, is most pairs. **The fixture carries its own positive control**: the
side `tile_side_for` gives at a budget taken from the availability figure is asserted to be
**different** from the one the run derived. Without that assertion the test passes against an
available-RAM default, which is the defect it exists to catch.

### (i2) THE AVAILABILITY WARNING NEEDS BOTH CONTROLS, AND (k) SAYS WHERE THEY RUN

*"The warning does not move the exit code"* passes when the warning never fires — the pure
negative. Paired: a run whose budget exceeds availability **prints the warning and exits 0**, and
a run whose budget is below availability **prints nothing and exits 0**.

**An exit code is a property of a process**, so both run `python -m metamer` in a subprocess —
where no monkeypatch survives. The fixture therefore moves the **budget** rather than the
availability: they are the two sides of one inequality, and `--memory-budget 100000` exceeds any
development machine's free RAM with no patching at all. The precondition is asserted in the test
rather than assumed.

### (d), (c) and (i3), briefly

- **(d)** `rg 'available'` over `src/`: **nothing reads available memory anywhere in the tree**
  — every hit is the word in prose or `tiling.block_bytes_for`'s local. The warning is the first
  reader, so there is no existing convention to match and no second definition to collide with.
  `HEADROOM_FRACTION` is the idiom a policy fraction is written in: value, asymmetry, and what it
  must cover.
- **(c)** new exits enumerated: `default_budget_gb` has one return and no raise;
  `Config.run_hash` gains one raise (unresolved budget) above its one return; `run()` gains no
  exit of its own — the default path reuses `_with_memory_budget`'s layer-2 raise rather than
  growing a second refusal for a condition no positive RAM reading produces.
- **(i3)** *"both runs derive the same side"* is a relation, and two runs failing identically
  satisfy it. The side is additionally asserted against `tile_side_for` called with the
  total-RAM budget — a second traversal of the production path, which pins the **routing**; the
  arithmetic itself is pinned by Task 2's tests and is not re-derived here.

---

## Task 4 — the calibration measurement

Run 2026-08-15 against the task brief in
[`../plans/2026-08-14-metamer-phase2b.md`](../plans/2026-08-14-metamer-phase2b.md), the live
`core/fit.py`, `core/optimize.py`, `core/memory.py`, `batch/run.py` and `batch/tiling.py`, **and
against two measurements taken before any code was written** — the capped fit's cost and the
outcome mix at each cap. **Twelve findings. The first makes the brief's ladder unexpressible and
the second makes the shipped one expensive, and neither is visible without running something.**

### (a4)/(g) THE BRIEF'S LADDER IS NOT REACHABLE THROUGH `run()` AT ALL

`B ∈ {1000, 2000, 4000}` is a ladder in **series**, and a run's B is a **tile**: `B = side²`, and
since Task 2 every derived side is a multiple of `store.TILE_SIDE_BASE` = 16. **None of the
brief's three numbers can be produced by any tile**, so a calibration that hit them would have to
bypass the tiling — which is (j2) and is the whole thing this task exists not to do. **Promoted,
with the arithmetic, as (j2)'s specification-level twin in the handoff's §1.**

**The ladder is therefore in SIDES**, and every side is a multiple of 16 by construction rather
than by choice — Task 2's rounding already guarantees it, which is the property that made it
"remove a footgun rather than document one".

### THE COST IS SET BY THE FIT, NOT BY THE MEMORY, AND IT IS THE BINDING CONSTRAINT

**Measured 2026-08-15 on this machine**, `fit` at `max_iter=1` over two candidates
(`white`, `white + matern12`), after a warm-up call, marginal cost per series:

| N | B = 32 | B = 128 |
|---|---|---|
| 60 | 195.4 ms | **197.3 ms** |
| 240 | 732.6 ms | **741.2 ms** |

**Linear in N, and flat in B** — the cost is per series, so the ladder's cost is its total series
count. Against the converged cap at N = 60: **2334 ms/series, so cap 1 is 11.8× cheaper, not
free.** The init ladder and the gradient are paid whatever the cap.

**Extrapolated** (linear in N and in M, stated as an extrapolation) to §9.4's configuration —
N = 630, M = 12 — that is **12.4 s/series**, so the four-point ladder `(16, 32, 48, 64)`,
**7680 series**, is **≈ 26.5 h on this box**. A calibration is not a minutes-scale operation at
production N and M, and **saying so here is cheaper than discovering it at Task 7.**

> **AND THE REFRAMING THAT MAKES IT ACCEPTABLE IS ARITHMETIC, NOT REASSURANCE.** 7680 series at
> cap 1 is **≈ 649 converged-series-equivalents**, against **one** production tile at side 272 of
> **73 984 series** — so the whole ladder is **0.88% of a single tile**, and a run has thousands
> of them. **Cheap relative to the job it sizes; expensive in absolute terms on this machine.**
> Both halves are true and the second is the one that will surprise someone.

### (a5) THE CALIBRATION MUST FIT ONE TILE, AND NOTHING IN THE BRIEF STOPS IT FITTING THE GRID

`run()` loops **every** tile. On the 10⁷-point grid the calibration exists to size, a capped run
fits all of it — the brief specifies the instrument and never bounds it.

**The instrument that already exists is the SIGTERM path, which is (j3).** `on_tile_written`
fires between a tile's data write and its completion bit, and the loop already stops after a
marked tile when a SIGTERM has been recorded. So the calibration raises the signal from that
callback and needs **no new seam and no new branch in the tile loop** — the "must not change the
path when unset" constraint is satisfied by adding **nothing**. A `max_tiles` parameter would put
a branch in the loop for a condition production never meets.

### THE `max_iter` SEAM: RESOLVED ONCE ABOVE THE LOOP, FROM ONE SOURCE

`fit(..., max_iter: int = 200)` and `optimize_series(..., max_iter: int = 200)` both carry the
default as a literal. `run()` passing `200` of its own would be a **third** copy that drifts the
day either moves. **One named default (`fit.DEFAULT_MAX_ITER`), used as the parameter default and
resolved once in `run()` above the tile loop**, so the unset path passes exactly what the loop
passes today and no branch enters the loop. **Not a config field**: a cap in the config reaches
`fit_hash`, and the calibration would then key on a different fit identity from the run whose
memory it measures — which destroys the cache key's meaning at Task 5.

### (i2) THE CAP'S REACHABILITY PAIR IS ALREADY OBSERVABLE IN THE STORE

*"The calibration used the production path"* is a pure negative. The pair needs no stub:
`/primitives/iterations` and `/status/outcome` record it. A capped run stores iterations at the
cap and **no `OK`**; a default run stores more and does. Measured below, so the assertion has its
expected values before the test is written.

### THE STEP TEST AND THE ACCUMULATION POINT ARE DIFFERENT EXPERIMENTS, AND CAP 32 CONFOUNDS TWO UNKNOWNS

**Measured 2026-08-15**, 64 series × 2 candidates = 128 fits, N = 60, white noise:

| cap | outcomes | wall |
|---|---|---|
| 1 | ITER_CAP_LARGE_GRAD 114, ITER_CAP_SMALL_GRAD 14, **OK 0** | 14.1 s |
| 2 | ITER_CAP_LARGE_GRAD 110, ITER_CAP_SMALL_GRAD 18, **OK 0** | 16.9 s |
| 32 | **OK 83**, DEGENERATE_HESSIAN 32, ITER_CAP_LARGE_GRAD 11, ITER_CAP_SMALL_GRAD 2 | 129.7 s |
| 200 | **OK 87**, DEGENERATE_HESSIAN 41 | 149.4 s |

**At caps {1, 2} the outcome mix is constant and no series converges**, so the step test is a
clean iteration-residency test — which is exactly why it is the discriminator and a slope is not.
**At cap 32 the mix changes**, so the difference against cap 1 is *accumulation* **plus** the four
allocation sites `fit.py:237` skips on a non-`OK` outcome. **One measurement, two unknowns.**

> **CORRECTED DURING IMPLEMENTATION, 2026-08-15: THE MIX IS NOT CONSTANT ACROSS {1, 2, 3}.**
> The table above was measured by calling `fit` directly at caps 1, 2, 32 and 200 and **never at
> 3** — the brief's own ladder point, taken on trust between two measured ones. An `OK` needs
> `n_iter < max_iter` (`optimize.py:592`), so a fit converging in two iterations is genuinely
> converged at a cap of 3, and at a cap of 1 the only way through is `n_iter = 0`. **Convergence
> begins exactly at the unmeasured point.**
>
> **The step test is better for it rather than damaged**, and it is evidence rather than a passed
> test: the peak is flat across all three caps **while** fifteen fits at cap 3 reach the four
> allocation sites, where the plan had only a code-reading. **Promoted as (a4)'s sample-level
> twin — "a point between two measured points is not measured" — and the counts and the three
> peaks live there, once.**

The separation is arithmetic rather than a second cap: **every skipped site is shape `(1, …)`**
— `theta[b, c, :p]`, `np.linalg.inv(result.hessian)`, `delta_method_cov`, the second
`obj.evaluate` — so the converged path is a **constant**, not a slope (F2 again). Accumulation
would scale with B; the constant does not. **So the accumulation question is answered by
B-dependence, and the constant is measured independently** by differencing cap 200 against cap 1
at small B. **The `OK` count is recorded at every ladder point as the control**, so a reader can
see which regime each number came from.

**And the brief's own justification for the cap needs one word changed.** *"`mean_iterations` is
32.5 (P3) against a cap of 200"* is right and is a **mean**: at a cap of 32, measured above,
**a third of the fits are still unconverged.** The cap is a calibration knob and never a
production one — that conclusion holds — but a reader taking 32.5 as "converged by 32" will
misread the high point.

### THE FIXTURE'S NON-OK POINT EXISTS AND IS AN OPTIMIZER-STAGE FAILURE — MEASURED, NOT ASSUMED

At the converging cap the standard fixture gives **87 `OK` and 41 `DEGENERATE_HESSIAN`** out of
128. That is a post-optimization failure, not a design-stage one, and it is **not constant across
the model axis** — which is the condition 2a Task 9 established and the reason a design-stage
construction cannot work (`fit.py:182` builds the design once, before the candidate loop, so a
design failure hits every candidate and gives `n_valid = 0`).

### (j) THE LADDER'S B IS CHOSEN BY THE FORMULA UNDER CALIBRATION, AND IS READ BACK FROM THE RUN

To land on side `s` the calibration must invert the budget arithmetic, which uses
`resident_bytes_per_series` — **the quantity being calibrated.** That is fixture *selection* and
not an oracle, and the circularity is closed by taking B from **the run's achieved tile side**
rather than from the target: if the analytic formula is wrong the achieved side differs, and the
fit is still a fit of what actually ran. Stated, or the next reader finds (j) here and is right.

### THE FLOOR IS PINNED ACROSS THE LADDER, AND `run(floor=…)` ALREADY DOES IT

The derived side is a function of the measured floor, which varies by megabytes between runs,
while the budget window that selects one multiple of 16 is narrower than that — Task 2's finding,
which cost four modules' fixtures. So the floor is measured **once** for the whole calibration and
passed to every point. That makes the ladder deterministic **and** makes the intercept a floor
under stated conditions rather than an emergent number.

### THE INTERCEPT IS THE FLOOR UNDER THE CALIBRATION'S CONDITIONS, AND IT IS NOT THE PRODUCTION FLOOR

It carries the pinned floor **plus** what the calibration child holds and a production run does
not — the sampling thread, the payload, a store written to a temporary path — **minus** the four
allocation sites the cap skips. **Stated in `CalibrationResult` rather than discovered at Task 7**,
because an intercept quoted as "the floor" is the same defect as a `tile_side` quoted without its
backend.

### (a3)/(a5) `calibrate=` AND `recalibrate=` ARE NOT THIS TASK'S

The brief's interface block lists both on `run()`, and **there is no cache until Task 5**. A flag
that parses and does nothing reads as supported — the rule `--reuse-fits-from` was held to at 2a
Task 12 and `engine=` at 2a Task 9. **Only `max_iter` lands here**, and the deviation is reported
rather than silently absorbed.

### (k), (c) and (d), briefly

- **(k)** a fresh child per ladder point, behind `memory._BARE_LAUNCHER`: `peak_rss_bytes` is
  inherited and does not compound, so a probe two processes below pytest starts from a known
  floor. The tile's peak is transient, so the child samples `current_rss_bytes` on a thread, as
  `_CHILD` already does — a reading taken at the end misses the peak entirely.
- **(c)** `calibrate` has one return and one raise (a failed child, with its stderr attached —
  a silent zero is a perfectly flat memory curve, which is indistinguishable from a formula that
  predicts nothing). `run(max_iter=…)` adds no exit.
- **(d)** `rg max_iter`: present in `fit` and `optimize_series` with the literal default 200 in
  both, and **absent from `batch/`** — so nothing in the run path mentions it today, and the seam
  really is missing rather than misspelled.

---

## Task 5 — the calibration cache

Run 2026-08-15 against the task brief in
[`../plans/2026-08-14-metamer-phase2b.md`](../plans/2026-08-14-metamer-phase2b.md), design doc
§11.4 (twice amended), the live `core/memory.py`, `core/machine.py`, `core/hashing.py`,
`batch/run.py`, `batch/tiling.py`, `batch/store.py` and `batch/completion.py`, **and against two
measurements taken before any code was written** — the cost of the versions digest, and a
recomputation of Task 4's published ladder from its own table. **Twelve findings. The first says
the brief's five interfaces cannot move a tile side at all, and the second says the first consumer
of a measured number has no rule for a bad one.**

### (g)/(a5) NOTHING IN THE BRIEF'S INTERFACE BLOCK CAN MOVE A TILE SIDE

`cache_path`, `cache_key`, `versions_digest`, `load` and `store` produce and persist a
`CalibrationResult`. **No one of them, and no combination of them, changes any number a run
uses.** `tiling.tile_side_for` calls `memory.resident_bytes_per_series` **internally**
(`tiling.py:292`) and takes no per-series argument, so a slope loaded out of the cache has nowhere
to go.

The brief's own last test names the consequence without noticing it: *"a stale entry under a
changed digest is **not used**"* presupposes an entry that **is** used, and the brief specifies no
path by which one could be. **The seam is `tile_side_for(..., per_series_bytes=None)`**, resolved
where the analytic figure is computed today, so the calibrated and the analytic paths differ in
**one argument** and not in a second derivation of the side — (a6)'s shape arriving by a new route
is what a separate calibrated derivation would be. **Reported as a deviation from the brief.**

**And the variable substituted is the SLOPE and never the intercept**, which is (b) at a
regression: `CalibrationResult`'s own docstring records that the intercept is *not* the production
floor — it carries the sampling thread, the temporary store and the JSON payload, minus the four
allocation sites a capped fit never reaches. The floor stays measured fresh (Task 1). Only the
per-series term is a per-series term.

### (a5)/(i9)/(i2) THE FIRST CONSUMER OF A MEASURED SLOPE HAS NO RULE FOR A BAD ONE

The brief has no acceptance criterion for the number it caches, and **two failure modes are
reachable, not hypothetical**:

- **A non-positive slope.** `memory.tile_side` computes `sqrt(budget / per_series)`; at a
  negative slope that is a domain error and at zero a division error, so the symptom is a
  traceback from arithmetic rather than a diagnosis. Task 4 measured **±0.3 MB of scatter between
  fresh children against 0.43 MB of signal** at the sides a suite can afford, and its published
  ladder's first two peaks *decrease* with B (227.86 → 227.73 MB). **A two-point ladder there is a
  coin flip on the sign.**
- **A small positive slope**, which raises no error at all and sizes an enormous tile against a
  constraint the design doc calls hard. This is the dangerous half: 5 B/series is a plausible
  number and nothing in the arithmetic objects to it.

**THE RULE ALREADY EXISTS AND IS THE DESIGN DOC'S OWN.** §11.4 requires the calibration to be
*"validated against §9.4's analytic formula"*, and `memory.slope_band` is that validation — the
two-sided 1.5× band Task 4 passed for the first time against the production path. **So a
calibrated slope outside the band is not used**: the run falls back to the analytic formula,
records `TileSideBasis.DEFAULT`, and warns naming both numbers.

> **FALLBACK RATHER THAN REFUSAL, AND THE REASON IS NOT KINDNESS.** A refusal after a
> multi-hour measurement, on a criterion the user cannot influence, converts a
> usable-but-conservative outcome into no outcome — and **the fallback target is exactly what the
> same run does without `--calibrate`**, so nothing is degraded relative to every run shipped so
> far. **The decisive half is (i9) at the RULE rather than at a window**: under a refusal, a
> suite-affordable `--calibrate` run fails on roughly half of executions on the sign of a
> noise-dominated slope, and (i2)'s positive control — *"`--calibrate` produces an entry"* —
> becomes a test that cannot be written deterministically. A rule whose outcome is set by the
> machine's jitter is not a rule.

**THE COST OF THE BAND IS STATED RATHER THAN HIDDEN: a calibration can move the per-series cost by
at most 1.5× and therefore the tile side by at most √1.5 = 1.22×.** A genuine disagreement larger
than that is a finding about the formula — Task 7's subject — and not a tile size. It reaches the
user as a warning, which is where a finding belongs.

### (a0) "NEVER CALIBRATED" AND "CALIBRATED AND REJECTED" MUST NOT BE ONE OBSERVATION

Under the fallback above, `tile_side_basis` reads `default` in **both** cases, so **a store that
spent 26.5 h measuring is byte-indistinguishable from one that measured nothing** — the fill-value
rule in its fourth register, arriving through a repair rather than through a schema.

The repair is the `source_*` precedent: **a `calibration` provenance block is written whenever a
calibration was CONSULTED**, carrying the measurement, the key, the contributing versions and —
when the band refused it — the reason. **Its absence is what means "no calibration was
consulted"**, and that absence is a fact about the run rather than a gap. `rejected` is not
redundant with the basis: the basis says which arithmetic produced the side, and this says why the
other one did not.

**No `SCHEMA_VERSION` bump, and the ledger's own test is why.** A bump is owed when an older store
**cannot answer a question a new gate asks**. Task 6's refusal reads `tile_side_basis`, which every
v4+ store carries. A v5 store's silence about `calibration` is unambiguous — **nothing before this
task could consult a calibration at all** — so its absence is correct rather than unanswerable.

### (a5) "DELETING THE CACHE CAN NEVER BREAK A STORE" IS TRUE OF A STORE AND FALSE OF A RESUME

The brief requires that sentence in a docstring. `completion.resume_tile_side` refuses when
**stored > derived**, and a calibrated slope **below** the analytic one gives a **larger** stored
side — so a later resume that cannot reach the cache derives a smaller side and is refused. The
claim is too strong as written, **and Task 6 exists because it is**: *"the resume refusal that
names calibration"* is precisely this case.

The narrowed claim, which is what goes in the docstring: **deleting the cache never makes a store
unreadable, incomplete or unresumable-in-principle, and it costs a re-measurement; where the
calibrated side was larger than the analytic one, a resume that cannot reach the cache is refused
by the tile-side gate, and naming that refusal is Task 6's.**

**So the delete-the-cache test must be placed in the direction where the resume proceeds** —
calibrated side **smaller** than analytic, where the gate's *"stored < derived → adopt the stored
side"* arm runs. (i7) a second time in one task: the two arms of the gate agree nowhere, and a
fixture that landed in the other one would test Task 6's subject under Task 5's name.

### (i7) THE CONSTRUCTED FIXTURE, WITH ITS ARITHMETIC DERIVED BY HAND

Task 4 makes the (i7) hazard concrete: on the measured ladder the analytic and calibrated figures
agree to **0.55 standard errors**, so a fixture that merely calibrates lands where the two
functions coincide and every cache test passes against a cache nothing reads. **The difference is
engineered, and the band above caps how far it can be engineered.**

Fixture: an 8×8 grid, N = 24, `["white", "white + matern12"]`, `["constant", "trend", "annual"]`.

| step | value |
|---|---|
| per-series, by hand: `24·9 + 2·(24·3 + 16·4 + 57)` | `216 + 386` = **602 B** |
| floor, pinned via `METAMER_FLOOR_BYTES` / `run(floor=…)` | **228 200 000 B** |
| budget | **228 267 295 B** (0.228267295 GB, which round-trips through `int(gb·10⁹)`) |
| available | 67 295 |
| block = `int(67 295 × 0.85)` | 57 200 |
| minus the solver constant at d = 1, k_β = 4, p_max = 3 | 57 200 − 11 200 = **46 000 usable** |
| **analytic**: `√(46 000 / 602)` = √76.41 = 8.74 | **side 8** — one tile on an 8×8 grid |
| **constructed slope 900**: `√(46 000 / 900)` = √51.11 = 7.15 | **side 7** — 2×2 = **four tiles** |

**900 / 602 = 1.495, inside the band and deliberately not on its edge** (the inclusive bound is
903.0). The difference is measurable twice over — `tile_sides` in the attrs, and the tile count in
the report — and it is the largest the band admits.

### (a2) THE KEY'S FIVE COMPONENTS, CLASSIFIED BEFORE THEY ARE CHECKED

| component | kind | what makes it right |
|---|---|---|
| `fit_hash` | identity + request | already populated by reading the data (`geometry_hash`) and the fit-relevant request. The regressor regime rides inside it by construction — §11.4 checked that rather than assuming it |
| placement | request | one reachable value; in the key on the `shared_with` precedent |
| engine label | request | **`MemoryEngineLabel`, never `EngineId`** — both shipped engines share `EngineId.KALMAN` so their scores stay rankable |
| machine fingerprint | **identity** | **the live example of a field whose classification changes with its consumer.** Harmless self-reported provenance while it reached `run_hash` alone; an identity the moment this key reads it. `machine.fingerprint()` reads the platform, wired at Task 1 **for exactly this** |
| versions digest | **identity** | read from the environment through `importlib.metadata`, never from `pixi.toml`, whose ranges give one digest across every version they permit |

**The fourth fact for an identity — the thing that populates it is not the thing being identified —
holds for the digest:** `importlib.metadata` reads what is installed, not what metamer declares.
That is the same distinction that made `registry_version` a self-reported identity.

**AND THE CAP IS NOT IN THE KEY, WHICH IS A CARDINALITY OF ONE RATHER THAN A DECISION.** Every
calibration runs at `max_iter = 1` today, so two measurements at different caps cannot collide.
The result records its own cap, so the collision is diagnosable the day a second cap exists —
recorded here rather than guarded, because a guard over a one-element set is untestable.

### (k) THE DIGEST'S ORDER IS PROCESS-LOCAL AND THE WHOLE ARTIFACT IS CROSS-PROCESS

`importlib.metadata.distributions()` yields in `sys.path` and directory order, so a digest taken
over that order is stable within a process and unstable between them — invisible to every
same-process test **and to mutation testing**, which is (k)'s defining shape and how
`json.dumps(default=repr)` shipped. **Sorted `(name, version)` pairs through
`hashing.canonical_json`**, which already refuses a `set` for this exact reason.

**Measured 2026-08-15 on this machine: 194 distributions, no duplicate names, no nameless
distribution, 1.99 s cold.** Two consequences: the digest is computed **only when a calibration is
consulted** and never on an ordinary run; and a duplicate name is not constructible here, so the
join rule for one is written and exercised against a **constructed** mapping rather than against
the environment — (i8)'s third shape, a fault class no fixture here can build.

### (c3)/(a3) `--calibrate` WITH `--reuse-fits-from` IS REFUSED RATHER THAN IGNORED

A recompute **derives no side**: `run.py:661` reads it back from the source (a1), and the budget
arithmetic is skipped entirely because the rule bounds a **fit's** resident set. A calibration
alongside it would measure for hours and change nothing. **Refused at layer 3**, on the precedent
that a flag which parses and does nothing reads as supported — the rule `--reuse-fits-from` itself
was held to at 2a Task 12 and `engine=` at 2a Task 9.

### (a6) SIX DESCRIPTIONS IN `src/` AND `tests/` SAY THIS CACHE DOES NOT EXIST

Counted with `rg`, not read for: `store.py:242` (`DEFAULT` is *"the only reachable value until
Phase 2b Task 5"*), `store.py:132` (the v4 ledger entry), `machine.py:323` (*"before the cache
exists"*), `run.py:696` (*"DEFAULT IS THE ONLY BASIS AN ORDINARY RUN CAN REACH UNTIL TASK 5"*),
`tests/test_runner.py:617`, `tests/test_reuse.py:663`, `tests/test_memory.py:1116`. Each is
re-pointed rather than deleted, because each records **why** the state was unreachable.

`tests/test_memory.py:1116` is the one that stays almost as it is: a cache now exists, and **the
floor still has none, deliberately** — so counting child spawns remains the falsifiable form and
only its justifying clause moves.

### (f) `store._chunk_side`'s DOCSTRING CONTRADICTS `TILE_SIDE_BASE`'s, IN THE SAME FILE

`_chunk_side` (line 481) still says a prime side is *"a reason for 2b's calibration to prefer a
composite tile side"*. `TILE_SIDE_BASE` (line 172), 300 lines above, says that phrasing **is wrong
in both directions** — 338 is composite and still 4.57× the target — and that the property wanted
is a divisor inside the admissible window. **And the calibration does not choose a side at all**:
it asks for one, and `budget_bytes_for_side` lands on it, always a multiple of 16 since Task 2.
The advice names an agent that does not exist and recommends a property that does not help.
Repaired here, pointing at the base.

### (a4) TASK 4's PUBLISHED LADDER, RECOMPUTED FROM ITS OWN TABLE

The number Task 5's (i7) placement rests on is *"the two agree to 0.55 standard errors"*, so it is
recomputed rather than transcribed. Least squares over the four published points:

| quantity | recomputed | recorded |
|---|---|---|
| slope | 1050.75 B/series | 1049 |
| SE | 223.6 | 222 |
| residuals | +273.4, −663.5, +551.5, −161.4 kB | +272, −660, +548, −160 |
| excess over the analytic 926 | 124.8 B = **0.558 SE** | 123 B = 0.55 SE |
| ratio | 1.1347 | 1.133 |

**Consistent.** The peaks are published to 0.01 MB, and a ±5 kB perturbation of each moves the
slope by up to `Σ|B−B̄|·5000/Sxx` = 2.7 B — every difference above is inside the table's own
rounding. **The check is recorded as having been run**, which is the point: the figure supports a
conclusion nobody disputes, and that is exactly the shape (a4)'s review-side register describes.

### (i2), (c), (d) and (h), briefly

- **(i2)** the pure negative is *"a default run writes no cache entry"*, and its control is
  *"`--calibrate` writes one"* **through the same wiring** — which is what the fallback rule above
  makes deterministic. A second pair: *"the store never resolves through the cache"* is a negative
  whose control is that the same store, with the cache present, derives the calibrated side.
- **(c)** `load` returns an entry or `None` and raises nothing — an unreadable or unparseable
  cache is a **miss**, because re-measuring is the safe direction and a truncated cache is exactly
  what §15.5's preemptible instance produces. `store` writes through a temporary and `os.replace`,
  and **replaces an unparseable file wholesale**, which is the asymmetry stated rather than
  discovered: the entries it would be preserving are unreadable anyway.
- **(d)** `rg` for the vocabulary: `cache_path`, `cache_key`, `versions_digest`, `recalibrate` and
  `importlib.metadata` appear **nowhere** in `src/` outside `core/registry.py`'s `entry_points`,
  so nothing is being re-implemented under another name.
- **(h)** every cache test threads a real budget, a pinned floor and a real config through `run()`;
  the analytic side must be **asserted as 8** in the same fixture that asserts the calibrated 7,
  or the comparison is a relation between two derived values with no absolute anchor — (i3).

### (a0)/(a2) THE PACKAGE UNDER MEASUREMENT IS THE ONE DISTRIBUTION `importlib.metadata` CANNOT SEE

**Measured 2026-08-15: `[d for d in importlib.metadata.distributions() if "metamer" in d.name]`
is EMPTY in this tree.** metamer runs from `src/` on the path and is not an installed
distribution, so *"every installed distribution, excluding nothing"* excludes **the one package
whose memory behaviour is being measured** — the `cftime` hole the brief warns about, in the
mirror: not a dependency reached through another library, but the subject itself, invisible for a
different reason.

**It is the (a0) shape at a digest**: "metamer did not change" and "metamer is not visible to this
instrument" produce the identical digest, and only one of them is intended. And it is (a2)'s
fourth fact — *the thing that populates the field must not be the thing being identified* —
holding in an awkward direction: the only available reading of metamer's version is metamer's own
`__version__`.

**So the map is built from the distributions AND from `metamer.__version__`**, through the same
duplicate-name join rule, so an installed metamer shadowed by a source tree shows **both** values
rather than one of them silently winning.

**AND THE COST IS REAL AND IS RECORDED RATHER THAN GLOSSED.** `metamer.__version__` here is
`0.1.1.dev63+gde10b6a7c.d20260816` — VCS-derived, so **it moves on every commit** and a developer
re-measures after each one. That is the correct side to fail on: a slope measured by a different
build of the thing being measured is exactly the under-invalidation the brief calls unacceptable,
`--calibrate` is opt-in, and in a released install the version is stable, so the churn is a
development-tree artifact rather than shipped behaviour.

### (a4) THE ASYMMETRY THAT DECIDED THE DIGEST'S BREADTH IS PRICED AT "MINUTES", AND TASK 4 MEASURED 26.5 h

The brief settles the digest's breadth with *"over-invalidating costs **minutes**; under-invalidating
costs a bad projection against a hard memory constraint"*. **Task 4 measured the ladder at ~26.5 h
at §9.4's configuration on this box** — the figure lives in *What Task 4 established*, once — so
the cheap side of the asymmetry is wrong by three orders of magnitude.

**The conclusion survives and the reasoning does not, which is the register (a4) says to check.**
The other side is a wrong tile against a constraint the design doc calls hard, on a run measured
in days; a re-measurement is a bounded, visible, opt-in cost and an OOM at hour forty is not. But
*"costs minutes"* is the sentence a future reader would use to justify narrowing the digest, and
it would be justified by a number nobody re-derived.

---

## Task 6 — the resume refusal that names calibration

Run 2026-08-15 against the task brief in
[`../plans/2026-08-14-metamer-phase2b.md`](../plans/2026-08-14-metamer-phase2b.md), the live
`batch/completion.py`, `batch/resume.py`, `batch/run.py`, `batch/store.py` and the three existing
direct callers in `tests/test_completion.py`. **Six findings. The first inverts both of the
brief's named test cases, and it is visible by reading the brief's own previous sentence.**

### (a5)/(a4) THE BRIEF INVERTS THE ARM IT QUOTES, ONE SENTENCE AFTER QUOTING IT

The brief states Task 10's rule correctly — *"equal proceeds, **stored < derived** adopts the
stored side, **stored > derived** refuses"* — and then, in the next clause: *"if the calibrated
side is **larger** the resume **refuses**."*

**A store built analytically supplies `stored`; the calibration supplies `derived`.** A larger
calibrated side is `derived > stored`, which is the **adopt** arm. So the refusal fires when the
calibrated side is **smaller**, and **both of the brief's first two tests name the wrong
direction**:

| brief's test | what the code does |
|---|---|
| *calibrated side **larger** → refuses and names calibration* | **adopts the stored side**, no refusal, no message |
| *calibrated side **smaller** → proceeds on the stored side* | **refuses** |

**THE NARRATIVE SURVIVES AND THE ARITHMETIC DOES NOT, WHICH IS WHY THIS IS WORTH THE PARAGRAPH.**
*"You measured more accurately and now your store will not resume"* is not only reachable, it is
the **likely** direction: Task 4 measured the slope **above** the analytic figure (1049 against
926), and a higher per-series cost buys a **smaller** tile. The brief reached the right conclusion
about the user's experience through arithmetic that says the opposite.

Worked at Task 5's fixture, where 46 000 B is usable and the analytic cost is 602 B/series:

| per-series | side | against a stored 8 |
|---|---|---|
| 602 (analytic) | `floor(sqrt(76.41))` = **8** | equal — proceeds |
| 900 (calibrated high) | `floor(sqrt(51.11))` = **7** | **stored 8 > derived 7 → REFUSES** |
| 400 (calibrated low) | `floor(sqrt(115.0))` = **10** | stored 8 < derived 10 → adopts 8 |

### (a2) "THE BASES DIFFER" IS THE WRONG CONDITION, AND IT MISSES `--recalibrate` EXACTLY

The brief says to name calibration *"when the store's `tile_side_basis` differs from the current
run's"*. Enumerated over the four reachable states, that test is wrong in one cell and the cell is
the one the cache's only override produces:

| stored | this run | calibration a cause? | bases differ? |
|---|---|---|---|
| `default` | `default` | **no** — the budget, the floor or the formula moved | no ✓ |
| `default` | `cached`/`measured` | yes | yes ✓ |
| `cached`/`measured` | `default` | yes — the cache was not consulted this time | yes ✓ |
| `measured` | `measured` | **yes** — `--recalibrate`, or a moved digest, gave a different slope | **no ✗** |

**So the condition is "either basis is not `DEFAULT`", not "the bases differ".** The last row is
not exotic: `--recalibrate` is the cache's **only** override, so it is the sanctioned way to get
two different measurements for one store, and it leaves both bases reading `measured`.

**And the first row is the half that must stay silent.** Naming calibration for two analytic runs
sends a user to a cache that was never involved — the same defect as telling them to raise a
budget they never typed, which is the precedent Task 3 already set in this exact function.

### (c3) THE RESOLUTION MUST NAME THE OPERATION THE USER PERFORMED

One refusal now has two causes, and the existing resolution — *"Either raise `--memory-budget` to
at least that, or write a new store"* — is right for the budget and the **wrong lever** for a
calibration: the user typed `--calibrate`, and telling them to raise a memory budget in response
is an answer to a question they did not ask.

**The calibration resolution is to make the two runs agree on a basis**: drop `--calibrate` to
resume on the analytic side, or supply the cache the store was built with. The budget lever stays,
because it is also true — a larger budget does buy the stored side back — but it goes second.
**Task 3 applied this same rule to this same message once already**, which makes the precedent
binding rather than analogous.

### (a6) THE EFFECTIVE BASIS IS COMPUTED INSIDE THE `provenance_attrs` CALL, AND TASK 6 NEEDS IT EARLIER

`run.py` resolves *"this run's basis, or the source's if this is a recompute"* as an inline
conditional in the argument list of `provenance_attrs(...)`. `resume_tile_side` runs **above**
that and needs the same value, so the obvious implementation computes it twice — **two
descriptions of one subject, which is the shape three separate findings in this sub-phase already
had.** Resolved once above the tiling and passed to both. Prevented rather than found, and
recorded because the second copy is what a reader would have added without noticing.

### (h)/(a0) `derived_basis` TAKES NO DEFAULT, ON `provenance_attrs`'s OWN PRECEDENT

`provenance_attrs`'s `tile_side_basis` is *"required, and required with no default, because a
default is a self-report: the one basis a caller would omit is the one it is least sure of"*. The
argument transfers verbatim. There are **three existing direct callers** in
`tests/test_completion.py`, and each having to state a basis is the point rather than the cost —
a defaulted parameter would let the refusal's new half go untested by every one of them.

### THE SCHEMA QUESTION, ANSWERED: NO BUMP, AND THE BASIS DOES NOT HAVE THE NULLABLE CHARACTER

Task 3's finding is about a field whose **`None` is meaningful**, which therefore cannot join
`REQUIRED_ATTRS` — because `create_store` refuses on `attrs.get(key) is None` — leaving the
version as the only mechanism that makes an older store's silence a refusal.

**`tile_side_basis` is the opposite in every respect.** It is a three-valued `StrEnum`, never
null, **already in `REQUIRED_ATTRS` since v4**, and `resume._check_schema` refuses on **exact
inequality** with `SCHEMA_VERSION` — so every store this code can read carries it and carries one
of the three values. Task 6 adds **no field at all**, so there is nothing that needs a version to
be found by.

**AND THE ADJACENT QUESTION, CHECKED RATHER THAN ASSUMED, BECAUSE TASK 5 IS WHERE IT COULD HAVE
GONE WRONG.** Task 5 added the `calibration` attr **without** a bump, so a v5 store written before
Task 5 and one written after are distinguishable only by inspection — which is precisely the
condition Task 3 names as a defect. It is not one here, and the test is whether either era's
absence is ambiguous: **nothing before Task 5 could consult a calibration at all**, so an absent
`calibration` means "none was consulted" in both eras and reads correctly either way. Task 6 reads
`tile_side_basis` and never `calibration`, so it does not depend on the distinction.

### (i7), (i2), (c), (d) and (g), briefly

- **(i7)** the refusal fixture must sit where the sides differ **and** a basis differs, and Task
  5's constructed cache is what supplies it: a store built analytically at side **8**, resumed
  with the cache at 900 B/series giving **7**. A fixture built by calibrating for real would land
  wherever the noise put it, including on the adopt arm.
- **(i2)** the pair is *refuses and names calibration* against *proceeds on the stored side*, and
  the third test — same basis, same side, unaffected — is the one that catches the real
  regression: a new comparison that refuses the ordinary case, which is Task 11's `tuple != list`
  defect where the natural comparison refused every resume including the correct one.
- **(c)** `resume_tile_side` has **one return and three raises** today (no recorded tile side —
  `pragma: no cover`, a provenance invariant; *stored > derived*; a bitmap that does not describe
  the grid). Task 6 adds **no exit**: it changes the text of one existing raise.
- **(d)** `rg tile_side_basis`: `store.py`, `run.py` and four test modules. **`completion.py` does
  not mention it at all**, so the field written at Task 1 still has no reader — which is exactly
  what Task 1 said it was doing and what this task is here to end.
- **(g)** four callers of `resume_tile_side`: one in `run.py`, three direct in
  `tests/test_completion.py`.

---

## Task 7 — criterion 6's instrument, the linearity claim

Run 2026-08-16 against the task brief in
[`../plans/2026-08-14-metamer-phase2b.md`](../plans/2026-08-14-metamer-phase2b.md), the live
`core/memory.py`, and **against three measurements taken before any code was written** — one
ladder point for the cost, and the evaluation instrument at two series lengths. **Six findings.
Two of them make the brief's cross-check unusable as specified, and one of those is a number the
module publishes about itself.**

### (f) THE BRIEF'S CROSS-CHECK CONTRADICTS A DOCSTRING ALREADY IN THE TREE, AND THE DOCSTRING IS RIGHT

The brief: *"the two must disagree by approximately `solver_state_bytes` per series."*
`data_and_workspace_bytes_per_series`, in the tree since Task 0: *"the two disagree by
approximately `_engine_workspace_bytes(d, k_beta)` per series **by construction**."*

**The docstring is right and the brief is wrong, because `unconstrained_loglik` never constructs
an optimizer.** `solver_state_bytes` is the engine workspace **plus** scipy's L-BFGS-B workspace
**plus** the `p_max²` Hessian, and the evaluation instrument runs no optimization at all. At the
instrument's own configuration the two differ by **14×**:

| term at d = 3, k_β = 6, p_max = 5 | bytes |
|---|---|
| `_engine_workspace_bytes` | **880** |
| `_optimizer_bytes` | 11 408 |
| Hessian, `p_max²·8` | 200 |
| **`solver_state_bytes`** | **12 488** |

### AND THE DISAGREEMENT IS A DIFFERENCE OF TWO TERMS, NOT ONE, SO ITS SIGN IS NOT THE BRIEF'S EITHER

Even corrected to the engine workspace, *"the evaluation instrument holds more"* is only half the
accounting. **Each instrument holds a per-series term the other does not:**

- the evaluation instrument holds the **engine workspace** per series, because it is handed a
  batch of B — production's `fit` hands the engine one series at a time;
- production holds the **output slots** per series — `theta`, `theta_unconstrained`, `beta`, the
  errors, the outcome codes — which a bare likelihood evaluation never allocates.

At the calibration fixture (d = 1, k_β = 4, p_max = 3, N = 60, M = 2): engine workspace **248**,
output slots **386**, so the predicted disagreement is **production − evaluation = +138 B/series**,
against a production per-series cost of 926. **It is small, it is positive, and the brief predicts
a negative number eighty times larger.**

### AND THE INSTRUMENT DOES NOT MATCH ITS OWN ORACLE AT SHORT SERIES — MEASURED, TWICE

`measure_evaluation_rss_slope((0, 512, 1024, 2048))`, 2026-08-16, this machine:

| N | measured slope | `data_and_workspace_bytes_per_series` | ratio | inside `slope_band`? | excess |
|---|---|---|---|---|---|
| 630 | 9286 B/series | 6550 | 1.418 | **yes** | +2736 |
| 60 | 4036 B/series | 1420 | **2.842** | **no** | +2616 |

**THE EXCESS IS ~2.7 kB/SERIES AND DOES NOT DEPEND ON N.** The oracle's N-dependent part is
`n_time·9` — `y` at 8 B and the mask at 1 — so a term that stays at 2.7 kB while N moves by 10×
is invisible at N = 630, where it is 42% of a figure inside a 1.5× band, and **dominant at
N = 60, where it is 184% and outside it.** This is (a)'s cancellation rule at a parameter value:
*a term is checked by a measurement at a second parameter value and by nothing else.*

**WHAT THIS DOES TO THE BRIEF'S CROSS-CHECK: it cannot be run at the calibration fixture's
configuration.** The quantity to be measured is 138 B/series and the instrument carries an
unmodelled 2616 B/series at that N — **nineteen times the effect.** The cross-check is reported as
what it is, a finding about the instrument, and **it is not used as evidence about production's
per-series cost.**

> **NOT CHASED HERE, AND THE REASON IS SCOPE RATHER THAN DIFFICULTY.** The uncharged term belongs
> to `unconstrained_loglik`'s working set, not to `run()`'s, so it moves no tile side and no
> memory budget. It is recorded as an open item with both measurements, because the next person
> to quote `data_and_workspace_bytes_per_series` needs to know it is a floor at N = 630 and not
> at N = 60.

### (a4)/(h) AN ORACLE AT A DIFFERENT CONFIGURATION FROM ITS INSTRUMENT

> **AMENDED 2026-08-16, AND THE AMENDMENT IS THE MORE INSTRUCTIVE HALF.** This entry first read
> *"the module publishes a number about itself that its own function no longer returns"*, and
> attributed the 168 B gap to `augmented_state`, the term Task 0 added — a number matched to a
> term. **It is not that.** `memory._CHILD` runs `SignalSpec([Constant, Trend, Annual,
> SemiAnnual])`, **six** design columns, while both the docstring and
> `test_measured_peak_rss_is_at_least_the_arrays_that_provably_exist` computed the floor at
> **four**. The 168 is the k_β 4→6 delta across **three** terms (48 + 104 + 16) and coincides with
> `augmented_state` at k_β = 6. **(a4)'s third register, caught on my own correction.** The floor
> is 6550, the ratio 1.293, and the test's oracle now takes the instrument's k_β.

**THE WRONG VERSION, KEPT STRUCK THROUGH, BECAUSE THE FAILURE MODE IS THE TRANSFERABLE PART:**

> ~~`data_and_workspace_bytes_per_series`'s docstring says *"is now 6382"* and the function returns
> **6550** at the configuration the sentence describes. The difference is **168 B**, which is
> exactly `augmented_state = d·(1+k_β)·8 = 3·7·8` — the term Task 0 added. **The prose is a
> pre-Task-0 figure carried through a correction that moved it.**~~

**Both halves were wrong and one of them was checkable in one line.** The function does **not**
return 6550 "at the configuration the sentence describes" — it returns 6382 at k_β = 4 and 6550 at
k_β = 6, and the sentence named no k_β at all, which is what let a reader supply one. And the 168
was matched to a term rather than derived: it is the k_β delta across **three** terms.

**THE TELL, FOR NEXT TIME: A DIFFERENCE THAT EQUALS A NAMED TERM IS A COINCIDENCE UNTIL THE OTHER
TERMS ARE ALSO COMPUTED.** Three terms moved and one of them happened to equal the total; checking
the remaining two costs one line and was not done. **(a4)'s third register, on my own
correction** — it arrived with the authority of the error it had just exposed.

### THE COST IS MEASURED, AND IT IS NOT TASK 4's FIGURE BECAUSE IT IS NOT THE SAME QUANTITY

One ladder point, measured 2026-08-16 on a 160×160 grid at N = 60, M = 2, `max_iter = 1`:

    side 32, B = 1024, peak 231.54 MB, 2048 fits attempted, 0 OK, 290.6 s
    => 283.8 ms per series

Task 4 measured **197 ms/series** for `fit` alone at the same N and cap. **The two are not in
conflict and must not be reconciled**: Task 4 timed the optimizer's entry point, and this times a
whole `measure_tile_peak` — child spawn, numba import, input open, tile assembly, the fit, the
store write. **44% overhead is what a ladder point costs beyond its fits**, and the ladder is
planned against the larger number because that is what the wall clock will do.

**THE LADDER, CHOSEN AGAINST THAT MEASUREMENT: sides (16, 48, 80, 112), B = (256, 2304, 6400,
12544).**

- **The lever arm is 49× in B**, which is the property that separates the slope from the
  intercept. A ladder whose top is a small multiple of its bottom fits the intercept and reports
  the residue as a slope; Task 4's was 16× and this is the reason to spend the extra points at the
  ends rather than in the middle.
- **21 504 series at 283.8 ms is 6103 s ≈ 1.70 h**, against the brief's 1.5 h estimate at
  B ≈ 3000–12 000. The top of the ladder is inside the brief's range; the total is 13% over its
  time.
- **Five points were priced and rejected**: adding side 96 costs another 9216 series — **2.42 h**,
  a 42% increase for one more residual degree of freedom.
- **The signal at the top is 12 544 × 926 B = 11.6 MB against ±0.3 MB of between-child scatter**,
  a signal-to-noise of ~39, where Task 4's affordable ladder had 0.43 MB against ±0.3 MB and was
  correctly called noise. **Predicted SE on the slope is ~32 B/series, 3.5% of 926** — so this
  ladder is expected to resolve, and if it does not the honest output is a bound.

### (a5) A 1.7 h TEST CANNOT LIVE IN A SUITE THAT RUNS BEFORE EVERY COMMIT

The brief says *"marked `slow` and `machine`"*, which puts a 1.7 h measurement inside
`pixi run test` — and the standing requirement is that the **full sweep runs before every
commit**. The sweep is currently **942 s**; the brief's instruction would take it to **~2.2 h**,
and every later task pays that on every commit. The two requirements are stated in different
documents and are jointly unsatisfiable, which is (a5)'s cross-document register.

**The precedent is Task 4's and it is exact**: the four-point ladder was *"the deliverable, run
once by hand"*, and the suite asserts **structure** — the sides landed on, the batch read back,
the fit's self-consistency — while **the value claim lives in `PROGRESS.md` with its
uncertainty.** Task 7 does the same, and what the suite gets instead is the **analysis**: the
residual arithmetic, the curvature bound and the resolution verdict are pure functions of a
`CalibrationResult` and are tested against **constructed** ladders, exactly and cheaply.

### RESIDUALS ARE THE DELIVERABLE, SO WHAT THE LADDER CANNOT SEE IS PART OF THE RESULT

**An instrument that cannot detect curvature is not evidence of its absence**, and four points
with two residual degrees of freedom cannot detect much. So the report carries, beside the
residuals, **the smallest quadratic term the ladder could have excluded at 2σ** — expressed as
the percentage by which the per-series cost may vary across the ladder without this measurement
noticing. A linearity claim without that number is an assertion.

**AND IF THE SLOPE DOES NOT RESOLVE, THE OUTPUT IS A BOUND.** Task 4's affordable ladder returned
1666 B/series against an analytic 926 and was correctly called noise rather than a 1.80× finding.
The report therefore states `resolved` from the slope's own standard error against the analytic
prediction, and a slope whose SE exceeds the effect is published as *"this measurement excludes X
and does not establish a value"*.

### (c), (d), (k) and the three boundaries, briefly

- **(c)** `calibrate` is unchanged: one return, one raise. The analysis function adds one return
  and one raise (fewer than three points, where a quadratic has no residual at all).
- **(d)** `rg`: `linearity_basis` exists on `CalibrationResult` and is a **sentence**, not an
  analysis — nothing in the tree computes a residual pattern, a curvature bound or a resolution
  verdict today, so none of this is being re-implemented under another name.
- **(k)** a fresh child per point is already what `calibrate` does, behind `_BARE_LAUNCHER`, and
  the floor is pinned across the ladder for the reason Task 4 recorded.
- **THE THREE CLOSURE BOUNDARIES ARE UNTOUCHED BY WHATEVER THIS ESTABLISHES**, and saying so is
  part of the deliverable: a converged fit at a memory-relevant B (85.5 h, runnable nowhere), the
  per-thread placement (no batched driver exists — F4), and a 10⁷-point run (1.7 years here). **A
  linearity result at N = 60 and M = 2 on one four-core box is this machine's**, and extrapolating
  it to §9.4's configuration is exactly the step the report must decline to take.

---

## Task 8 — criterion 7's run, and accumulation across tiles

Run 2026-08-16 against the task brief in
[`../plans/2026-08-14-metamer-phase2b.md`](../plans/2026-08-14-metamer-phase2b.md), the live
`batch/tiling.py`, `batch/reuse.py` and `batch/run.py`, and **against two measurements taken
before any code was written** — the process floor, and a two-rung reproduction of Task 7's
ladder. **Seven findings. The first needs no new measurement at all: criterion 7 is already
contradicted by Task 7's own published table, and the comparison that shows it is four
subtractions nobody performed.**

### (a4) TASK 7's FOUR PUBLISHED PEAKS ALL EXCEED THE BUDGET THAT SIZED THEM

`budget_bytes_for_side` returns *"the smallest budget whose derived tile side is exactly
`side`"*, and it is the function that chose every budget in Task 7's ladder. So each rung has a
budget, and criterion 7 — *"peak RSS at or below the budget"* — is a subtraction away. **It was
never done.** At the pinned floor of 228.2 MB:

| side | budget for that side | Task 7's peak | peak − budget |
|---|---|---|---|
| 16 | 228 492 066 | 231.31 MB | **+2.82 MB** (+1.23%) |
| 48 | 230 723 182 | 231.11 MB | **+0.39 MB** (+0.17%) |
| 80 | 235 185 412 | 235.81 MB | **+0.62 MB** (+0.27%) |
| 112 | 241 878 758 | 243.14 MB | **+1.26 MB** (+0.52%) |

**Every rung is over.** The brief opens *"peak RSS is a property of ONE TILE"* and proposes a new
run to establish it; four measurements of exactly that quantity already exist, and they say the
criterion fails at its most adversarial budget. **(a4): recompute every worked example before
trusting the requirement it illustrates** — here the example is a whole published ladder.

**THE EXCESS IS NOT THE OVERAGE, AND THE DIFFERENCE MATTERS.** With `peak = floor + tile + ε` and
`budget = floor + tile/0.85`, the overage is `ε − 0.17647·tile`, so:

| side | tile bytes | 0.17647·tile (the headroom) | implied ε |
|---|---|---|---|
| 16 | 248 256 | 0.04 MB | **2.86 MB** |
| 48 | 2 144 704 | 0.38 MB | **0.77 MB** |
| 80 | 5 937 600 | 1.05 MB | **1.67 MB** |
| 112 | 11 626 944 | 2.05 MB | **3.31 MB** |

ε averages **2.15 MB** with no trend in side, which is what Task 7's own figures predict: an
intercept of 229.85 MB against a 228.2 MB pinned floor is **1.65 MB** of unmodelled residency,
and the RMS residual is **0.88 MB**. **The unmodelled term is the finding; the sign of the
subtraction is a consequence of it.**

**AND THE MEASURING CHILD IS A CANDIDATE EXPLANATION THAT MUST NOT BE ASSUMED.**
`CalibrationResult`'s own docstring says the intercept is the pinned floor **plus what the
measuring child holds and a production run does not** — a sampling thread, a temporary store, a
JSON payload. So ε may be the instrument rather than production. **That is (j2), and it is
exactly why Task 8's run must be a plain `run()` and not a calibration point.**

### (a4)/(a5) THE BRIEF'S BUDGET AND THE BRIEF'S GRID DESCRIBE DIFFERENT RUNS

The brief: *"One capped run at side ≥ 192 under a 0.5 GiB budget"*, and separately *"The capped
run at side 192 iterates several tiles, so assert peak against tile index there too — same run,
second assertion."*

**At a 0.5 GiB budget the derived tile side is 528.** Computed through the production path
(`tiling.tile_side_for`, floor 228.2 MB, d = 1, k_β = 4, p_max = 3, N = 60, M = 2):

    block  = (536 870 912 − 228 200 000) × 0.85 = 262 370 275 B
    raw    = floor(sqrt((262 370 275 − 11 200) / 926)) = 532
    side   = 528 after rounding down to a multiple of TILE_SIDE_BASE

**528 > 192, so a 192×192 grid is ONE tile** and the second assertion has no subject. The two
sentences are not both satisfiable by one run.

**AND THE BUDGET IS THE NUMBER THAT IS RIGHT.** A 528-point tile holds 258.1 MB, which finally
**exceeds the 228.2 MB floor** — the goal's *"a scale where the tile, not the interpreter, is the
subject"*, reached exactly. It is the grid that is wrong, and it is wrong by 2.75×: the run the
budget describes has a grid of **528**, not 192.

### (a4) "~1.7 h" IS THE COST OF A SIDE-144 RUN, AND THE BUDGET'S OWN RUN IS 22.5 h

Task 7 measured **290.3 ms/series** over 21 504 series. Against it:

| run | series | predicted wall clock |
|---|---|---|
| the brief's stated cost | — | **~1.7 h** |
| grid 144 (what 1.7 h buys) | 20 736 | 1.67 h |
| grid 192 (what the brief says) | 36 864 | **2.97 h** |
| grid 528 (what the brief's budget means) | 278 784 | **22.5 h** |

**The estimate is Task 7's ladder total carried across as if it were one run's cost.** It is
1.75× short of the brief's own grid and 13× short of the brief's own budget.

### THE FIFTH CLOSURE BOUNDARY: THE TILE OUTWEIGHS THE INTERPRETER ONLY AT 22 h A TILE

Four boundaries are recorded; this is a fifth, and it is the goal sentence of this very task.
`tile > floor` needs `side² · 926 > 228.2e6`, so `side ≥ 512` — **262 144 series in ONE tile,
21.1 h at the measured rate**, and the brief's own 528 is 22.5 h. Criterion 6's ladder wants four
such rungs. **On this machine the interpreter outweighs the tile at every affordable scale**, and
that is a property of a 228 MB floor sitting under a 926 B/series tile, not of the code.

### (i10) CRITERION 7's MARGIN IS THE HEADROOM CONSTANT, AND IT IS 17.6% OF THE TILE

`budget = floor + tile/0.85` makes the slack `budget − (floor + tile)` equal to
`0.17647 · tile` **exactly** — the headroom, and nothing else. So criterion 7 at the minimal
budget is a test of one question: **is unmodelled residency smaller than 17.6% of the tile?**

With ε ≈ 2.15 ± 0.88 MB from the table above, the criterion turns over at a tile of
**12.2 MB — side 115** — and needs side ≥ 160 to clear it by 2σ. This is (i10) at a second
criterion, found the same way: by comparing the criterion's window against the measurement's own
uncertainty.

> **THIS PREDICTION WAS SUPERSEDED BY THE MEASUREMENT AND IS LEFT VISIBLE.** The ε it rests on
> comes from two rungs against a stale floor pin. The five-point ladder put the crossover at
> **side ≈ 70**, not 115, and resolved the slope rather than bounding it — see `PROGRESS.md`'s
> *What Task 8 established*, which is the only home for the figures. **The reasoning was right and
> its input was two points**, which is the whole reason the task ran five.

**At a generous budget the criterion is vacuous instead.** At 0.5 GiB with a 192 grid the peak is
~262 MB against a 536.9 MB budget: it clears by 274 MB, of which 228 MB is block the grid never
fills. **A criterion that fails at the tight end and is vacuous at the loose end is a criterion
about the headroom constant**, and reporting it without saying so would be closing it rather than
meeting it.

### (f) THE RECOMPUTE READS ITS TILE SIDE FROM THE SOURCE, SO THE CHEAP INSTRUMENT NEEDS AN EXPENSIVE INPUT

The brief calls `--reuse-fits-from` *"the tile loop with the fit removed … so a recompute over
10⁵–10⁶ points runs in minutes"*, and (j3) credits it as an instrument found rather than built.
**Both are true of the recompute and neither is true of getting one to run.** `reuse.py`, in the
tree since 2a Task 12: *"THE NEW STORE'S GEOMETRY IS READ BACK FROM THE SOURCE, NOT RE-DERIVED
FROM THE BUDGET"*, and `run.py:822` is `side = reuse.source_tile_side(reuse_fits_from)`. So:

- the recompute's **tile count is a property of the source store**, not of this run's budget;
- `resume.check_source` **refuses a source whose completion bitmap is not fully set**;
- therefore a 10⁵-point recompute needs a **complete 10⁵-point fitted store**, which at
  290.3 ms/series is **8.1 h**, and 10⁶ points is **80.6 h**.

**The instrument is cheap and its input is not.** The brief prices the first and not the second.

**THE REPAIR, AND IT IS A FIXTURE RATHER THAN A COMPROMISE.** A wholly-masked series
short-circuits in `optimize.py:517` at the data-level check — before any design is built and
before an optimizer exists — and is written as `INSUFFICIENT_DATA`. So a mostly-masked input
produces a **complete store of the right geometry for almost nothing**, and the recompute over it
copies, re-ranks and writes exactly the same bytes: `copy_tile` and `read_scores` are shaped by
the arrays, never by the outcomes. **A fraction of live series keeps the OK path reachable in the
source**, so the store being read is not uniformly degenerate.

**WHAT IT DOES NOT COVER IS THE SAME LIST THE BRIEF ALREADY WROTE**, plus one entry: a masked
source's `/selection/` write ranks nothing, so any allocation conditional on a scored series is
not reached. The live fraction is what keeps that from being the whole store.

### (j3) THE PER-TILE SEAM EXISTS ALREADY, AND THE WATERMARK REMOVES THE SAMPLER

`run(on_tile_written=...)` fires **inside the loop, between a tile's data write and its
completion bit** (`run.py:959`), and it fires on **both** arms — the fit at 934 and
`_recompute_tile` at 958 share it. So *"assert peak against tile index"* needs no new seam, on
either path. This is the same (j3) the calibration used to stop after one tile.

**AND THE PEAK PER TILE IS `VmHWM`, NOT A SAMPLED MAXIMUM.** `_CALIBRATION_CHILD` runs a 2 ms
sampler because a batched evaluation frees its working set before `score` returns; a tile loop
has no such window, and the kernel already keeps the process high-water exactly.
`machine.peak_rss_bytes()` read in the callback is monotone by construction, so *"peak stops
growing"* is read directly off it — **and a sampler thread inside the process whose residency is
the subject is the contamination this task exists to avoid**. `current_rss_bytes()` is recorded
beside it, because a watermark cannot fall and a leak is visible in the working set first.

### (c), (d), (h), (k) and the boundaries, briefly

- **(c) the refusal has TWO arms, and "below the floor" is only the first.**
  `tiling.py:212` fires when the budget does not clear floor + headroom; `tiling.py:329` fires
  when it does but the remaining block will not hold one series at the base. **Both name the
  floor**, and a test that asserts only the first leaves the second unreached — *enumerate every
  raise, never assert a count*.
- **(d)** `rg`: nothing in the tree computes growth-per-tile, a per-tile residual or an
  accumulation bound today. `linearity_report` fits peak against **B** and takes a
  `CalibrationResult`; peak against **tile index** is a different subject and cannot be reached
  through it without inventing a ladder that does not exist.
- **(h)** the fixture must state its own geometry rather than take the module defaults, which is
  what put `memory._CHILD` at six design columns while its oracle used four.
- **(k)** every peak is read in a fresh process behind a bare launcher, for the reason `memory`
  has one: `peak_rss_bytes` is inherited across fork/exec, so a child spawned from a large
  process reports the parent's watermark.
- **THE STALL RATE IS RECORDED BESIDE EVERY PEAK**, which Task 7's ladder did not do and which is
  why `RSS_STALL_LIMIT_US_PER_S` has never been checked against a known-bad reading.

### THE THREE MEASUREMENTS THIS PRE-FLIGHT RAN, AND THE FIRST TWO CONTRADICT WHAT IT PLANNED WITH

**Two of Task 7's rungs, reproduced on Task 7's own instrument and fixture, and the floor measured
ten times.** Every figure is in [`PROGRESS.md`](../../../PROGRESS.md)'s *What Task 8 established*
and **is not repeated here** — this section records what the audit concluded from them, which is
the part that belongs to the audit.

- **THE COST MODEL DOES NOT TRANSFER**, and two points separate the reason from the rate: solving
  `t = a + b·B` on the pair splits a marginal per-series cost from a fixed per-child cost, and
  Task 7's published figure is a ladder total over a ladder's series with its own four fixed costs
  inside it. **Task 7's rule applies to Task 7's own number** — *a predicted cost is a claim with
  the same preconditions as the measurement it came from.* The run planned here was resized
  accordingly, and then the rate failed to transfer a third time.
- **THE FLOOR HAS MOVED SINCE TASK 7 PINNED IT**, and the movement is a level shift rather than
  scatter. **`FLOOR_OVERRIDE_ENV`'s docstring says the measured floor "varies by megabytes between
  runs"; the measurement says half a megabyte** — the sentence overstates the jitter and says
  nothing about the drift, which is the larger effect and the one that invalidates a stale pin.

### AND THAT CORRECTS THIS PRE-FLIGHT'S OWN ε TABLE, WHICH IS (a4)'s THIRD REGISTER ON ME

The ε table above computes `peak − (floor + tile)` against Task 7's **228.2 MB** pin and concludes
criterion 7 fails at every rung. **The arithmetic is right for Task 7's ladder, which pinned that
floor. The conclusion does not carry to production, which measures its floor in the run that uses
it.** Against a contemporaneous floor the same two rungs give one sign each way, both inside the
floor's own scatter — so the honest statement was never *"criterion 7 fails"* but *"ε is not
separable from the floor's measurement noise at these tile sizes"*. **A correction arrives with
the authority of the error it has just exposed**, so this one was written with the measurement
that forced it and not on its own.

**AND THE TASK THEN MEASURED PAST IT.** With five one-tile runs rather than two rungs, ε is not
noise at all: it grows with B at roughly twice the rate the formula charges, and criterion 7
acquires a crossover. **The pre-flight's job was to stop the wrong measurement being run, and its
own first conclusion would have been the wrong measurement.**

### SO CRITERION 7 IS DECIDABLE ONLY ABOVE A TILE SIZE, AND THE THRESHOLD IS COMPUTABLE

The margin at the minimal budget is `0.17647 · tile` **exactly** — the headroom and nothing else —
while the noise is a floor reading against a peak reading. Setting the first above twice the
second is what picks the smallest tile whose answer means anything, and it landed on **side 96**:
affordable at under an hour, where the brief's side 192 is 3.6 h and the side its own budget
implies is 27 h — **both at the re-measured marginal rate**, which is why they exceed the figures
computed from Task 7's rate two sections above.

**So the plan for this task became two runs over ONE 96×96 grid** — same series, same fitting
work, differing only in tile side — **side 16 for accumulation in the fit path and side 96 for
criterion 7**, plus a third prediction the pairing gives free: *"peak is a property of one tile"*
puts the two peaks `(9216 − 256) · 926` apart. **A prediction that large from a fixture pairing
that costs nothing extra is worth more than either run alone**, and it is what turned into the
five-point ladder once the pair proved confounded — Run A's 36 tiles accumulate a warm-up that
Run B's single tile does not, so `grid = side` replaced it.

---

## Task 9 (narrowed) — the cascade mechanism, ahead of the disputed value

Run 2026-08-17, against the **narrowed** brief agreed after Task 8 blocked the task as written:
land the single-source mechanism and the sites that are wrong under every hypothesis, leave the
**value** frozen until 8a/8b resolve the 1.86x disagreement. The plan's Task 9 section is
otherwise unchanged and is still the brief.

### (a4) THE FLOOR CORRECTION THIS TASK WAS ASKED TO LAND DOES NOT SURVIVE ITS OWN MEASUREMENT

The narrowed brief included one correction that looked free: `WORKED_FLOOR` pins **228 200 000**
while Task 8 measured **232.00 MB, sigma 0.468, over ten runs**, and the published side is
**272 either way** because the base-16 round-down absorbs the difference. A stale constant that
currently changes nothing is the cheapest possible correction -- so it was checked before it was
made, and **the premise is not established.**

**`measure_floor` TAKES A `data_uri`, SO THE FLOOR IS INPUT-DEPENDENT BY CONSTRUCTION**, and
**neither number was recorded with its input.** Measured today on a quiet box -- 20 s idle at
**0.0397 ms/s**, every probe window at **0.0000**, swap 100% full (2047/2047 MB) and 5094 MB
available, three fixtures, three `measure_floor` runs each:

| fixture opened | `peak_bytes`, MB | span |
|---|---|---|
| 12 x 16 x 16 | 228.37, 228.68, 228.93 | 0.56 |
| 60 x 160 x 160 (Task 7's ladder fixture) | 228.66, 228.54, 228.63 | 0.11 |
| 630 x 64 x 64 (section 9.4's N) | 229.95, 229.83, 229.89 | 0.11 |

**The input does move the floor -- +1.28 MB from the ladder fixture to section 9.4's N, eleven
times the within-fixture span -- so a floor quoted without its input is not reproducible.** That
is the same rule as handoff section 3's *"a published side needs a pinned floor beside it"*, one
level down, and it is why the published record pins the whole `FloorReport` rather than a number.

**But 1.28 MB is not 3.8, so the input does not explain the gap.** Nine readings today bracket
**228.37-229.95**; Task 8's own five-point ladder intercept is **228.042 MB**, measured on the day
it recorded 232.00. **Three lines land at 228-230 and one at 232.** So `WORKED_FLOOR` is **not
established stale, and it does not move in this task.** Recorded as a disagreement to report,
per the precedence rule, and it is (a8) inverted: two independent lines converging is evidence,
and here it is the **third** line that fails to converge.

**AND THE 232.00 READING IS NOT WITHDRAWN EITHER** -- it is ten runs at sigma 0.468, which is not
scatter around 228.6. What is withdrawn is the *inference*: "the floor has moved" was drawn from
two numbers whose common precondition was never recorded, which is (a) at a parameter value.

### (j4) AND THE SAME CHECK PAID OFF ON THE BLOCKER ITSELF, ONE SESSION EARLIER

Two of the three surviving explanations were narrowed **before** any new measurement, out of
numbers already in `PROGRESS.md`: Task 8's side-96 watermark sitting **1.4 MB above the
end-of-tile current reading** bounds the transient at **<= 152 B/series** of the 975 B/series
excess -- **an upper bound, so it excludes the headroom explanation as SUFFICIENT without
establishing it as zero**, and the direction must be stated wherever it is quoted. Open question
16's table is the second: an N-independent excess (+2736 at N = 630, +2616 at N = 60) at a
different instrument and a different magnitude, so it is a **prior for additive rather than
evidence for it**, and it stays open rather than being folded in (a5).

### AND THE BLOCKER'S OWN FRAMING WAS WRONG, WHICH IS (a4) ON THE REVIEW SIDE

`PROGRESS.md`'s Task 9 inherit section said the two explanations *"both predict exactly what was
observed, because the observation is a single line through peak against B and either term moves
it."* **`HEADROOM_FRACTION` does not move peak.** Task 8's ladder forced `grid = side`, so the
tile geometry is fixed by the fixture and not by the budget; the 1900.9 +/- 84.1 B/series is a fit
through **peak RSS**, and the headroom enters only the budget column. The headroom explanation
survives only if the excess is a **transient**, which is a different claim with a different and
much cheaper discriminator. **The blocker was written from the task's conclusion rather than from
its method, and the method fixes the geometry the alternative hypothesis would have needed to
move.**

### (a6) A SECOND DESCRIPTION OF SECTION 9.4's MODEL EXISTS ALREADY, AND THIS TASK WOULD HAVE MADE A THIRD

Two copies of the worked example are in the tree today: `validation.py:57`'s `_WORKED_EXAMPLE`
(plus `_WORKED_EXAMPLE_BUDGET` and `_WORKED_EXAMPLE_STATE_DIM`) and
`tests/test_tiling.py:56`'s `WORKED_EXAMPLE` / `WORKED_FLOOR`. **A published record added beside
them is the third**, and it is the one every document would then point at -- so the model
parameters and the pinned floor move **into** the record and both existing copies read it.
(a6)'s own corollary: a second description is cheapest to prevent in the commit that would have
created it.

### (a5) BUT VALIDATION'S SIDES ARE NOT THE PUBLISHED SIDE, AND UNIFYING THEM WOULD PUBLISH A FOURTH

`_WORKED_EXAMPLE_BUDGET`'s docstring already refuses this: layer 3 runs **before the input is
open and therefore before the floor is measured**, so its sides divide the **whole** budget --
an upper bound and the pre-Task-2 arithmetic -- and what the refusal is for is the **ratio**,
which the floor does not move. **Share the model parameters; never share the answer.** A "one
source" repair that gave validation the published side would publish a fourth tile side into a
project that has had four, which is the failure this task exists to end.

### (j) CRITERION 16's TEST CHECKS CONSISTENCY, NOT CORRECTNESS, AND MUST SAY SO

*The documented number equals `tile_side_for(documented inputs)`* has the implementation as its
own oracle. **It catches the next formula correction orphaning the documents -- which is the
whole cascade -- and it cannot catch a wrong formula**, because both sides move together.
`test_the_worked_example_derives_272_from_the_whole_chain`'s hand-derivation is the independent
oracle and **stays**, re-pointed at the record rather than replaced by it. Two tests, two
subjects.

### (g2) THE PRECONDITION LIST BINDS AGAINST THE WHOLE SIGNATURE, NOT THE REQUIRED PARAMETERS

`tile_side_for` takes eleven keyword parameters; handoff section 3's precondition table names
seven things and omits `placement` and `threads` entirely. **A parameter added with a default
would move the published number with nothing to see it**, so the binding is
`set(record arguments) | {the two the record varies deliberately} == set(signature parameters)`.
The two are `per_point_design` (the record publishes both branches) and `per_series_bytes` (the
calibration seam -- and its being `None` is exactly the "analytic, not calibrated" precondition
the dispute is about).

### (i5) THE TEMPTING REPAIR IS HERE, AND THE DISPUTE MAKES IT CHEAPER RATHER THAN DEARER

The plan already calls this the one place where the easy fix is undetectable: when an assertion
will not go green, the thing that would have to change is the published constant. **The open
dispute adds an excuse the plan did not anticipate -- "the number is under revision anyway".**
Every expected value in this task is derived by hand from the corrected formula with the
derivation recorded beside it, and the four hypothesis sides are computed the same way.

### AND THE CAVEAT MUST NOT OUTLIVE THE DISPUTE — (a6) IN A NEW REGISTER

A number published with its dispute is honest; a **caveat whose subject has been resolved** is
(a6) exactly -- a description surviving its subject, and unfalsifiable because nothing exercises
it. So the dispute is a **field of the record, not prose**: structured, with its owner, its two
measured slopes and its hypothesis sides **recomputed by the same test that recomputes the
value**. 8b deletes the field in the edit that moves the number, and a stale caveat fails a test
rather than reading as current.

### (d), (e), (f) briefly

- **(d)** `rg`: nothing in the tree publishes a tile side as a value-plus-preconditions record
  today. The vocabulary this task needs -- a published number, its derivation, its preconditions
  -- exists only as prose in handoff section 3 and `PROGRESS.md`, neither of which any test reads.
- **(e)** the mutations that must bite: change the record's value away from `tile_side_for`'s
  answer; drop a key from the arguments; add a defaulted parameter to `tile_side_for`; leave the
  dispute field present with a hypothesis side that no longer reproduces.
- **(f)** the brief says "five source docstrings"; the count today is **four files** --
  `tiling.py` (module docstring and `tile_side_for`), `store.py` (two module comments and one
  docstring), `validation.py`, `memory.py` -- and the stale-number occurrences in `src/` are
  already struck-through annotations rather than live claims. **The live stale statements are in
  the design doc**, which has never been updated past 338/445/186: sections 2.5, 9.4's table,
  11.1 and 13.4.

---

## Task 8a — the discriminator, audited against a brief I wrote myself

Run 2026-08-17. **The brief is mine, written at the end of Task 9, so this audit is (a4)'s third
register applied to my own work: a correction arrives with the authority of the error it just
exposed.** Four findings, and the first changes the measurement.

### (i7) ARM A's FIXTURE WAS PLACED WHERE THE TWO HYPOTHESES AGREE

The brief chose sides **16/32/48** for Arm A because they are cheap. **The discriminating
quantity is `peak - current` — the transient — and it scales with B**, so cheapness is bought
directly out of the signal:

| B (side) | H_resident predicts | H_transient predicts | separation |
|---|---|---|---|
| 256 (16) | 0.04 MB | 0.25 MB | **0.21 MB** |
| 2 304 (48) | 0.35 MB | 2.25 MB | 1.90 MB |
| 4 096 (64) | 0.62 MB | 4.00 MB | 3.38 MB |
| 9 216 (96) | 1.40 MB | 8.99 MB | **7.60 MB** |

taking H_resident at the 152 B/series the existing bound allows and H_transient at the full
974.9. **At side 16 the separation is 0.21 MB against a floor whose own sigma is 0.468 MB** —
the fixture cannot express the effect, which is (i8)'s first shape, and the run would have come
back "neither excluded" **by construction rather than by evidence.** Corrected: Arm A runs at
**side 96, where the existing bound came from, and side 48 as the low anchor.**

### AND THE COST FOLLOWS THE FIXTURE, SO THE BRIEF'S "~11 min" IS VOID

Re-derived from Task 8's own wall clocks at this exact fixture — side 96 took **1780.1 s**
(193 ms/series) and side 48 **438.8 s** — Arm A is **~37 minutes, not 11.** The estimate was
built on the design (i7) has just rejected, which is the honest reason it was wrong rather than
a fourth failure of the cost model. **The cost model has failed to transfer three times, so
these are Task 8's measured numbers at Task 8's fixture and not an extrapolation.**

### (j3) THE SEAM EXISTS AND YIELDS BOTH READINGS AT ONCE, SO NO INSTRUMENT IS BUILT

`run(on_tile_written=...)` fires between a tile's data write and its completion bit, on both
arms, and **with `grid = side` there is exactly one tile**, so it fires once — at end of tile.
`machine.peak_rss_bytes()` (`VmHWM`, monotone, what criterion 7 compares to the budget) and
`machine.current_rss_bytes()` read there give the pair. **The store's root attrs carry the
run's own `floor`**, measured with that input open, which is what the Task 9 comparability rule
now requires of every floor. Nothing new is written.

### ARM C MOVES AHEAD OF ARM A, AND IT MAKES ARM A's NUMBER INTERPRETABLE

A mostly-masked run at the **same side** gives the same `(peak, current)` pair with the fit
removed, for about 1% of the cost. Run first, it turns Arm A's single reading into a
**differential**: full minus masked at one B is the fit path's contribution, and that is the
decomposition that stops 8b fitting a coefficient to a fixture — **Task 0's F5, where `22p*8`
was wrong in its dependence and not its magnitude, and tuning the coefficient would have made
it worse.**

> **(a)'s LIMIT CLAUSE ON THIS DIFFERENTIAL, STATED BEFORE IT IS TAKEN.** Masking changes
> values, not shape: a wholly-masked series still occupies its row in the data tile and still
> gets its output slots, so the floor, the data tile and the slots cancel. **What does not
> cancel is anything sized by the count of LIVE series** — the selection write ranks nothing
> for a masked point, so an allocation conditional on a scored series is absent rather than
> cancelled. A live fraction keeps that path reachable, and the differential is read as *"the
> fit path's per-series retention"* only to the extent that it is.

### (i2) THE NEGATIVE RESULT IS THE EXPECTED ONE, SO IT NEEDS A POSITIVE CONTROL

Arm A's likely finding is *"`peak - current` is small at both B"* — a **pure negative** about
the transient, and the shape of answer an instrument gives when it sees nothing at all. **So
the effect is constructed and the instrument confirmed to see it**: a run whose callback
allocates and frees a known block inside the tile must show it in `peak - current`. Without
that, "the transient is small" and "the reading is at the wrong moment" are one observation —
which is exactly the `current_end` bias the brief already names.

### (d), (a5) AND THE PREDICTIONS

- **(d)** `rg`: nothing computes `peak - current` per tile today. `accumulation_report` fits
  **current against tile index**, `linearity_report` fits **peak against B**; the transient is
  neither, and reaching it through either would need a ladder that does not exist (j2).
- **(a5) Arm B's `n_models` lever moves the cost model as well as the signal.** M = 12 is six
  times the candidates and therefore about six times the per-series time, which is why it stays
  at small sides — where, unlike Arm A's question, the signal is the **per-series slope** and
  grows with the fixture rather than with B. **`per_point_design`'s reachability through
  `run()` is checked before it is relied on**: Q7 deferred the feature and declared the regime,
  so the formula branch exists and the path may not.
- **THE PREDICTIONS ARE COMMITTED BEFORE THE RUN, AS DATA THE ANALYSIS READS** — not as a
  paragraph a reader compares by eye. A prediction that has to be matched up by hand is one the
  analysis can drift toward, and this project has recorded a conclusion surviving its own
  contradicted derivation once already.

### WHAT TASK 8a ACTUALLY MEASURED, AND WHY BOTH ARMS RETURN "NEITHER EXCLUDED"

Run 2026-08-17 on a box measured quiet — 20 s idle at **0.0000 ms/s** of cgroup full stall, load
0.93. Every point in
[`task-8a-measured.jsonl`](task-8a-measured.jsonl), the harness in
[`task-8a-harness.py`](task-8a-harness.py), the predictions in
[`task-8a-predictions.json`](task-8a-predictions.json) — **committed before any arm ran.**

**THE INSTRUMENT MEASURES ELAPSED TIME, NOT THE TRANSIENT, AND A CONTROL PROVES IT.** Two masked
runs at side 48, identical fixture, identical code path, differing **only** in 600 s of idle
inside the callback before the reading:

| run | wall | `peak − current` |
|---|---|---|
| masked side 48 | 55.2 s | **0.000 MB** |
| masked side 48, +600 s idle | 668.8 s | **92.115 MB** |

**Time alone produces the entire effect the arm exists to detect.** The full-fit run at side 48
took 4072.9 s and read a working set **85 MB below its own measured floor** — 144.7 MB against
229.7 MB — which is reclaim of the floor's own pages, not a tile transient. **(i2) discipline in
both directions: the positive control passed (64 MB injected, 66.59 MB seen) and the negative
control — vary time, hold everything else — reproduced the "signal" from nothing.**

### AND THE STALL GATE CANNOT SEE THIS, WHICH IS THE FINDING THAT OUTLIVES THE TASK

`RSS_STALL_LIMIT_US_PER_S`'s docstring says it has never been checked against a known-bad
reading and that the next failure should record its rate. **Here are two.** The run that lost
85 MB read **0.0876 ms/s** — *below* the 0.9 ms/s known-good idle rate — and the 600 s control
that lost 92 MB read **1.2489 ms/s**, forty times inside the 50 ms/s limit. **Both would pass the
gate.** PSI `full` counts time the workload was *stalled waiting* on memory; reclaiming clean
file-backed pages the workload has stopped touching costs **no stall at all**. So the gate
catches thrashing and is **blind to quiet reclaim over a long window**, which is the failure mode
that matters for a tile loop.

### SO ARM A IS "NEITHER EXCLUDED", AND THE EXISTING BOUND SURVIVES UNCHANGED

The decision rule would have read side 48's 84.005 MB gap as TRANSIENT. **It is not a verdict, it
is the clock.** What does survive: the contamination **inflates** `peak − current`, so Task 8's
1.4 MB at side 96 remains an **upper** bound and **transient ≤ 152 B/series** still holds — the
headroom explanation stays excluded as *sufficient*, exactly as before, and is now excluded with
its mechanism understood rather than on one reading.

### ARM C's LADDER IS CLEAN AND ITS COMPARISON IS NOT

The masked ladder is short-running and uncontaminated: side 48 and side 96 give **2750.8
B/series** at this fixture. **Two points, so no residual and no standard error** — stated rather
than papered over. But the differential Arm C exists to take is masked **against full**, and
every full-fit run at these B is long enough to be contaminated: the side-48 full run's peak sits
**0.97 MB below its own floor**. **The subtraction cannot be done, so Arm C is "neither excluded"
too.**

### ARM B DOES NOT RUN, BY THE RULE COMMITTED BEFORE THE RUN

It was gated on Arm A returning RESIDENT. Arm A returned neither. **8b stays blocked.**

### AND TASK 8's LADDER HAS AN UNCONTROLLED VARIABLE CONFOUNDED WITH B

Its five points ran **45.6 s to 1780.1 s** — a **39× spread in run length, monotonically
increasing with B**, which is precisely the variable just shown to move an RSS reading by tens of
megabytes. **The direction matters and is stated:** contamination *lowers* the peak of the longer
runs, which *lowers* the fitted slope, so **1900.9 ± 84.1 is if anything an UNDERestimate.** This
does not rescue the formula — it widens the disagreement — but the ladder is no longer a clean
measurement of anything, and neither is criterion 7's crossover, whose failing point is its
longest run.

### AND TASK 8's FIXTURE CANNOT BE REBUILT FROM WHAT WAS RECORDED — THE COMPARABILITY RULE, DAY ONE

Rebuilt from the recorded description (N = 60, M = 2, k_β = 4, p_max = 3, `grid = side`), this
fixture is **7–9× more expensive per series** — side 48 took **4072.9 s against Task 8's
438.8 s** — and its **masked** peak at side 96, 255.09 MB, **exceeds Task 8's full-fit peak of
245.36 MB** at the same side. **A masked run cannot hold more than the live run it is a subset
of**, so these are not the same fixture. What the record omits: the data distribution, the input
**chunking**, the criteria list, and whether an iteration cap was applied. **The rule promoted
yesterday fired within a day, on the measurement the whole dispute rests on.**

---

## Task 8i — the instrument, audited before it is built

Run 2026-08-17, against the brief I wrote at the end of 8a. **Four findings, and two of them
correct claims in that brief — one of which I had already half-written into a promotion.**

### THE BOX REBOOTED, AND THE THREE RED TESTS ARE GREEN AGAIN

Uptime is **1:56** against Task 8a's ten days, and available RAM is **9046 MB** against the
**1906 MB** that task ended on. Re-run on the rebooted box, **all three failures pass** —
`test_a_child_inherits_the_parents_own_high_water_mark_and_not_its_current_rss`,
`test_peak_residency_does_not_move_with_the_iteration_cap` and
`test_the_recompute_loop_retains_nothing_that_survives_its_warm_up`, 119.5 s, three passed.

**So they are not "known-red": they are AMBIENT-CONDITIONAL, and that is a different deliverable.**
Calling them known-red would be a claim with an unrecorded precondition, which is the
comparability rule the project promoted two days ago. **The same code and the same tests give
green or red depending on a variable the validity gate cannot see, and the gate reported
`0 indeterminate` in BOTH directions** — which is exactly the observation INDETERMINATE exists to
make and exactly the one it failed to make.

### I NEARLY RECORDED A FALSE STRUCTURAL CLAIM ABOUT THE CANDIDATE, AND (i2) IS WHAT STOPPED IT

`/sys/fs/cgroup/memory.stat` read **`pgscan 0`, `pgsteal 0`** while `/proc/vmstat` showed
**7 897 171** pages stolen system-wide. The tempting conclusion — and I had begun writing it — was
**structural**: this container is `0::/` with `memory.max = max`, so it never triggers
cgroup-internal reclaim, so the counter is not maintained and the named candidate is dead on this
box. The file is demonstrably live (`anon` 673 MB, `file` 165 MB, `pgfault` 2 236 643), which
made the story tidier still.

**Measured instead of concluded: the counter moves.** Across the reproduction run below it went
**45 120 → 81 317**, a delta of **36 197 pages ≈ 141 MB**. The zero meant *"no reclaim attributed
here yet this boot"*, not *"not counted here"*. **(a0) on my own reading — a counter at zero and a
counter that is not maintained are the same observation — and the resolution is (i2): construct
the effect and confirm the instrument sees it.** A structural claim from a single zero would have
sent 8i to a worse instrument for a better-sounding reason.

### THE KNOWN-BAD REPRODUCES WITHOUT MEMORY PRESSURE, WHICH I SET OUT TO FALSIFY

The brief calls the 600 s idle run *"a known-bad on demand — the first this project has had"*.
**I expected that to be false**, because Task 8a produced it on a box with 1906 MB available and
reclaim needs pressure. Re-run on the rebooted box with **9307 MB available**:

| | Task 8a (1906 MB free) | Task 8i (9307 MB free) |
|---|---|---|
| `peak − current` | 92.115 MB | **86.344 MB** |
| wall | 668.8 s | 671.1 s |
| stall rate | 1.2489 ms/s | **0.0067 ms/s** |

**The claim stands and is now measured on both sides of the ambient variable it was suspected of
depending on.** Reclaim here is not driven by shortage — `pswpout` is 467 718 with 9 GB free, so
anonymous pages are being paged out regardless. **Recorded because the audit set out to break the
claim and failed**; a confirmation is only evidence if the attempt to refute it is published too.

> **AND THE STALL RATE FELL BY 186× WHILE THE DAMAGE STAYED THE SAME.** 1.2489 ms/s against
> 0.0067 ms/s for 92 MB against 86 MB lost. **The gate's quantity is not merely insensitive to
> this failure; it is uncorrelated with it.** That is stronger than what (a2)'s new
> instrument-level register claims, and it is the sharpest evidence in the project that a
> threshold on the wrong quantity cannot be rescued by any value.

### SO THERE ARE THREE CANDIDATES, NOT ONE, AND THE THIRD IS THIS PROJECT'S OWN IDIOM

- **(A) cgroup `memory.stat` `pgsteal`.** Live and moving, per-cgroup. **Not per-process:** it
  says reclaim happened somewhere in this cgroup during the window. Conservative for a gate —
  false INDETERMINATE, never false clean — which the asymmetry rule already prefers.
- **(B) `/proc/vmstat` `pgsteal_*`.** Always maintained, **system-wide**, moved by 1 342 132
  pages during the same window. Broadest coverage, weakest attribution. **Risks a gate that
  always fires**, which the standing rule says is equivalent to no gate.
- **(C) THE PROCESS'S OWN WORKING SET AGAINST ITS OWN MEASURED FLOOR.** `current_end` **below**
  the floor is impossible while a tile is allocated unless pages were taken: 148.8 MB against a
  229.9 MB floor here, and 235.9 MB against 229.8 MB on the clean 55 s run. **Per-process, needs
  no kernel interface, discriminates on both points already measured, and is one-sided by
  construction** — it detects large reclaim and is silent on small. It is the shape
  `FloorReport` already has a consumer for.

**Whatever is chosen returns `None` where its counter is absent, never `0`** — the rule
`machine.memory_stall_us` already follows, and the one my own near-miss above would have
violated.

### (a5), (d), AND WHAT THE BRIEF ASKS FOR THAT CANNOT BE DELIVERED YET

- **(d)** `rg`: nothing in the tree reads `memory.stat`, `/proc/vmstat`, or compares a run's
  end-of-window RSS against its floor. `machine.memory_stall_us` reads `memory.pressure` only.
- **(a5) the brief's fourth deliverable and its first are in tension.** *"The suite goes green,
  or the failures are recorded as known-red with owners"* assumed the failures were stable. They
  are not: they are green today. **A gate cannot be validated against a failure that will not
  hold still**, so the known-bad the gate is tuned against must be the **constructed** one — the
  600 s idle run — and not the three tests. The tests are then a **separate** question: whether
  their assertions can survive an ambient variable at all, which is deliverable two.
- **The box's own state is a variable and the reboot proved it**, so every number 8i records
  carries `MemAvailable` and the reclaim counters beside it, exactly as Task 8's peaks were
  supposed to carry their stall rate.

---

## Task 8b — the correction, audited before the fixture is built

Run 2026-08-19, against the brief in the plan plus the cold-start handoff in `PROGRESS.md`'s
*What Task 8b inherits*. State confirmed first: branch `main`, `HEAD` = `c407320` = `origin/main`,
working tree clean, **1067 tests collected**, which is the count the cold-start head records.
Latest CI run green.

**THE BRIEF SAYS THE FIRST ACT IS A COMPLETELY RECORDED FIXTURE AND NOT A MEASUREMENT. THIS
AUDIT SAYS THE FIRST ACT IS CHEAPER THAN THAT AND IT IS (j4).** Two of the four things the
dispute needs were computable from the tree and from the two published ladders, with no run at
all, and one of them **excludes the explanation this audit set out to confirm**.

### (j4) THE TWO DISPUTED LADDERS USED TWO DIFFERENT INSTRUMENTS, AND NO RUN HAS EVER REPORTED BOTH

The record states both choices and never compares them, so the comparison has never been made:

| | Task 7's ladder | Task 8's ladder |
|---|---|---|
| what "peak" is | **the maximum of `current_rss_bytes()` sampled every 2 ms on a thread inside the measured process** (`memory._CALIBRATION_CHILD`, `_sample`) | **`machine.peak_rss_bytes()`, i.e. `ru_maxrss`** — a kernel watermark |
| grid | 160 x 160, one tile taken by SIGTERM | `grid = side`, the whole grid is one tile |
| iteration cap | `max_iter = 1` | **not recorded** |
| slope | **1021.6 +/- 134.7** | **1900.9 +/- 84.1** |
| ratio to the analytic 926 | **1.103** | **2.053** |

**A SAMPLER CANNOT SEE A TRANSIENT SHORTER THAN ITS PERIOD AND A WATERMARK ALWAYS CAN**, so the
two instruments measure different quantities whenever the peak is transient — and Task 8 already
established that this peak *is* transient, at side 96, by 1.4 MB. **Task 7's 1021.6 sits within
10% of the analytic 926, which is the resident term alone**, and Task 8's 1900.9 is 2.05x it.
That is the signature of one instrument seeing a transient and the other not, and it is the
hypothesis no measurement in this project has yet been pointed at.

> **AND IT IS ALREADY VISIBLE IN THE ONE REPRODUCTION THE RECORD HAS.** Task 8 re-ran two of Task
> 7's rungs on **Task 7's own instrument and fixture** and got +0.33 MB at rung 16 and **+4.19 MB
> at rung 48** — the same instrument, the same fixture, twice, disagreeing by four megabytes at
> one rung and not at the other. **That is what a stochastic instrument looks like**, and the
> record reads it as *"Task 7's value rests on a rung that does not reproduce"* — true, and it
> does not say why. `_CALIBRATION_CHILD`'s own comment says the sampler *"is not load-bearing
> here today"* and that a sampler recording nothing leaves every assertion in `test_memory.py`
> green, which is the same fact from the other side: **nothing in the suite can tell the two
> instruments apart.**

### (j4) AND THE DISCRIMINATING READING IS ALREADY COMPUTED IN THE TREE AND THROWN AWAY

`memory._CALIBRATION_CHILD` prints `"watermark": peak_rss_bytes()` beside its sampled `"peak"`
(`memory.py:1724`). **`_measure_point` parses five of the six fields and drops that one**, because
`CalibrationPoint` has no place to put it. So the measurement that separates the two disputed
instruments **costs one dataclass field, not a run** — every calibration this project has ever
executed took both readings and recorded one.

**That is the wiring the handoff already flagged as 8b's**, for the reclaim witness rather than
for this: *"8b's probes should read it in the child and return it beside the peak — the one
wiring Task 8i deliberately did not do, because it touches `CalibrationPoint`'s schema, which
Tasks 4, 5 and 7 pin."* The same edit now carries two witnesses, and the reason to make it is
stronger than the reason recorded for it.

### (a7) THE OMITTED TERM IS `assemble_tile`'s SPAN TRANSIENT — AND FOUR MULTIPLICATIONS EXCLUDE IT AS THIS DISPUTE'S CAUSE

`tiling.assemble_tile` loads each chunk-aligned span as `.values` (**float32**, measured) and
`.astype(np.float64)`, so within one span the float32 and the float64 are alive **together**,
alongside the float64 destination block. Its docstring's guarantee — *"both full representations
never coexist"* — is a claim about **spans**, and it is exactly as strong as the chunking makes
it. At N = 60 the coexistence is `4*60 + 8*60 =` **720 B per series of the span**, against a
formula that charges `n_time * 9 =` **540 B per series of the tile** for the block and its mask
and nothing at all for the load.

**AND THE CHUNKING WAS NEVER RECORDED FOR EITHER LADDER, SO IT WAS MEASURED FROM THE FIXTURES'
OWN CONSTRUCTION.** Default `to_zarr` chunking on `(n_time, grid, grid)` float32, read back
through `tiling.chunk_shape`:

| ladder | side | B | chunk shape | spans | largest span, series |
|---|---|---|---|---|---|
| Task 8, `grid = side` | 16 | 256 | (60, 16, 16) | 1 | 256 |
| | 32 | 1 024 | (60, 32, 32) | 1 | 1 024 |
| | 48 | 2 304 | (30, 48, 48) | 1 | 2 304 |
| | 64 | 4 096 | (30, 32, 64) | **2** | **2 048** |
| | 96 | 9 216 | (30, 48, 48) | **4** | **2 304** |
| Task 7, grid 160 | 16 | 256 | (15, 80, 80) | 1 | 256 |
| | 48 | 2 304 | (15, 80, 80) | 1 | 2 304 |
| | 80 | 6 400 | (15, 80, 80) | 1 | 6 400 |
| | 112 | 12 544 | (15, 80, 80) | **4** | **6 400** |

**THE LARGEST SPAN IS NOT MONOTONIC IN B ON EITHER LADDER, AND ON TASK 8's IT FALLS BETWEEN ITS
LAST TWO POINTS** while B more than doubles. So the chunking is a **second** variable that moved
with the abscissa and was recorded by nobody — the same defect as the run length, in a quantity
the fixture list does name.

**AND THEN THE ARITHMETIC KILLS THE STORY.** Fitting `peak = 926*B + 720*largest_span + c` over
each ladder's own points:

| ladder | model slope, 720 B/span-series | model slope, with a contiguity copy at 1200 | **measured** |
|---|---|---|---|
| Task 7 | **1286.0** | 1526.0 | **1021.6** |
| Task 8 | **1056.2** | 1142.9 | **1900.9** |

**The model puts Task 7 ABOVE Task 8. The measurement puts it 1.86x BELOW.** The span transient
is real, it is omitted from the formula, and **it is not what these two ladders disagree about** —
its own sign is wrong. Four multiplications, before any fixture was built, retired an explanation
that was mechanical, chunk-shaped, and exactly the kind of thing this audit was hoping to find.

> **(a4)'s third register, pre-emptively, on this audit.** The story was half-written — a named
> function, a stated docstring guarantee shown vacuous, a magnitude of 720 that brackets the
> observed 975 B/series excess when the span is the whole tile (1646 and 2126 against 1900.9) —
> and **the bracketing is what made it feel finished.** It survives only under the assumption
> that every span is the whole tile, which the measured chunking above says is false at four of
> the nine published points. **An agreeing first check is where the search stops**, and the check
> that agreed here was the magnitude; the checks that disagreed were the two orderings.

### SO THE EXCESS GROWS WITH B AND IS NOT IN THE LOAD, AND TASK 8a ALREADY SAID WHERE TO LOOK

If the span transient cannot produce a slope of 1900.9 — its span saturates at 2304 series while
Task 8's B reaches 9216 — then something else per-series and watermark-visible is unaccounted.
**Task 8a's Arm C measured a wholly-masked ladder at 2750.8 B/series**, which short-circuits
before any design or optimizer exists, so its per-series cost is **the tile plus the output slots
plus the store path, with the fit removed** — and it is *higher* than 1900.9, not lower. Two
points, no standard error, a different fixture: it settles nothing and it points somewhere. **The
excess is in the tile/store path rather than in the fit path**, which is the location Arm C
existed to name and could not, because its comparison arm was contaminated.

### (a) RUN LENGTH, AND WHY THE FIX IS PADDING AND NOT A SHORTER LADDER

The second limit clause requires run length held constant across the points being compared. A
ladder in B is a ladder in run length by construction, so the constancy has to be **built**:

- **Hold the LIVE-series count constant across the points**, not the total. A wholly-masked series
  short-circuits in `optimize.py:517`, so the fit cost is `L * cost_per_fit` with `L` fixed while
  `B = side^2` varies. The tile, the slots and the store path are shaped by the arrays and never
  by the outcomes, so **the per-series terms under measurement are untouched by masking**.
- **Then pad the remainder to a constant wall clock** inside the tile callback, because the masked
  path still costs roughly 24 ms/series (8a: 55.2 s at B = 2304, 223.6 s at B = 9216) and that is
  not flat. Padding at the short points, never truncation at the long ones.
- **Task 8i's 2x2 licenses the padding**: idle alone lost 0.00 MB at every duration measured; idle
  **under memory pressure** lost 135 MB. So padding is safe exactly while the box is quiet, and
  quietness is now checkable per point rather than assumed — `reclaim_shortfall_bytes` read **in
  the child**, which is where 8i said it must be read.

**AND THE COST OF NOT PADDING IS KNOWN RATHER THAN FEARED**: it is what makes 1900.9 an
underestimate of unknown size, which is the state the dispute is in today.

### (i2) THE POSITIVE CONTROL IS THE CHUNKING, AND IT IS FREE

The span transient is now a **term with a predicted magnitude and a stated dependence** — on the
chunk, not on B — so it supplies the control the instrument comparison needs. Two ladders at
identical sides, live counts, run lengths and models, differing **only** in the input's chunk
shape:

- **fine, `(n_time, 16, 16)`**: every span is 256 series whatever the tile, so the transient is a
  **constant** and belongs in the intercept.
- **whole-grid, `(n_time, side, side)`**: one span, so the transient is `720 B/series` and belongs
  in the **slope**.

The pair predicts a slope difference of **+720 B/series** and an intercept difference of about
`-720 * 256 =` **-184 kB**. If the watermark sees that difference and the sampler does not, both
questions are answered by one pair of ladders — **which instrument is right, and where the
omitted term lives** — and if neither sees it, the transient hypothesis is dead on its own
positive control rather than on an argument.

### (d), (e), (g2), (i5) AND THE STANDING CHECKS

- **(d)** `rg`: nothing in the tree records a watermark on a `CalibrationPoint`, records a
  reclaim shortfall from inside a measured child, or sets an input's chunking anywhere outside a
  test fixture. `assembly_spans` is public and asserted in `tests/test_tiling.py`; **no test binds
  a span count to a memory figure.**
- **(e)/(i5)** the tempting repair when a corrected slope will not match a published side is to
  move `PUBLISHED_TILE_SIDE`, which is the cascade. **The value freeze happens in its own commit,
  after the term moves, and the `dispute` field is deleted in the same edit that moves the
  value** — a test recomputes every figure in it, so a caveat left behind fails.
- **(g2)** `CalibrationPoint` is pinned by Tasks 4, 5 and 7 and by `CalibrationResult`'s
  consumers; adding a field is additive, and every consumer's construction site must be bound
  against the new field list rather than assumed keyword-complete.
- **(a5)** the brief says *"one term moves, alone, in its own commit"*. **This audit has already
  found two candidate terms** — the load transient and whatever the store path holds — so the
  rule bites immediately: they cannot land together, and neither lands before the ladder says
  which one the slope needs.
- **A PERMITTED OUTCOME REMAINS "NEITHER RESOLVED — REPORT AND STOP"**, and after the span model
  was excluded above it is a live possibility rather than a formality.

### WHAT THE RUNS FOUND, AND FOUR OF THIS AUDIT'S SEVEN PREDICTIONS WERE WRONG

Every measurement is in [`task-8b-measured.jsonl`](task-8b-measured.jsonl) — 80 points, each
carrying its whole fixture — and the numbers are in `PROGRESS.md`'s *What Task 8b established*
rather than here. **What belongs to the audit is which of its own predictions survived**, and the
score is the reason this section exists:

| # | prediction | outcome |
|---|---|---|
| P1 | three instrument levels, watermark > at-tile > at-end | **held**, 2410 / 1504 / 971 |
| P2 | `current_end` ≈ 926, and at-tile minus at-end ≈ `n_time·8` | **held**, 970.6 and 533.5 |
| P3 | the sampler and the watermark do NOT differ by 1.86× | **held**, 93 ± 67 B/series apart |
| P4 | whole-grid chunking adds +720 ± 250 B/series | **WRONG**, −35 ± 60 — no effect at all |
| P5 | the fit path retains nothing per fitted series | **held at three sides and untestable at two**, because the full-live arm's own run length damaged its top two points |
| P6 | the reclaim witness reads below 600 kB throughout | **wrong in detail**: 795 kB on a clean 30 s run, which is the floor measurement's own between-process scatter and is the witness's **noise floor** — a thing `reclaim_shortfall_bytes`'s docstring does not mention |
| P7 | no ladder here reproduces 1900.9, and that is not a failure | **wrong, and wrong in the most useful direction**: Task 8's ladder reproduces *point by point* at every side its run length did not damage, to ±0.76 MB |

**AND THE FOUR-MULTIPLICATION EXCLUSION ABOVE WAS RIGHT FOR THE WRONG REASON.** The span model was
retired because it inverted the two ladders' ordering. Measured, the chunking moves the slope by
**nothing** — so the model was not merely mis-signed, its effect is absent, and the arithmetic that
retired it would have retired it even if the effect had been real and small. **A correct verdict
from an argument that could not have distinguished the cases is a lucky verdict**, and the
distinguishing evidence was one 9-minute ladder that this audit only planned as a positive control.

### (j4), THREE TIMES IN ONE TASK, AND THE THIRD IS THE ONE THAT SETTLES THE DISPUTE

The audit found two readings already in hand. The run found a third, and it is the largest:

- **Task 8's iteration cap divides out of its own published wall-clock column.** 178.1, 190.0,
  190.5, 189.1, 193.2 ms/series across a **36× range in B** — flat, therefore per-series, therefore
  the `max_iter = 1` rate `CALIBRATION_LADDER`'s docstring measured at 197 ms/series. Task 8a's
  rebuild ran at **1767.8 ms/series, 9.28×**, against the 11.8× that docstring records for the
  converged cap. **The "7–9× too expensive, therefore not the same fixture" conclusion WAS the
  cap**, and one division of a column already in `PROGRESS.md` recovers it.
- **The chunking reads back out of the fixtures' own construction**, so *"never recorded"* was
  true of the note and false of the artifact.
- **THE LADDER ITSELF IS IN THE PUBLISHED TABLE.** Fitting Task 8's five points gives 1900.9;
  fitting the three that ran under 440 s gives **2584.3 ± 127.0**, and the new duration-controlled
  ladder gives **2574.9 ± 236.1** over those same three sides. **The measurement that resolves the
  dispute was a three-point refit of a table that had been in `PROGRESS.md` since 2026-08-16.**
  Everything else this task ran was needed to know *which* three points to keep — but the answer
  was already there, and (j4) says to look before measuring, which this audit did and did not find
  it. **What the audit checked was whether a published table answered the question as printed. It
  did not ask whether a SUBSET of it did.**

### AND THE COST MODEL FAILED TO TRANSFER A FOURTH TIME, IN THE CHEAP DIRECTION (Task 8b)

The plan and this audit both sized the replacement against Task 8a's masked runs — 55.2 s at
side 48, 223.6 s at side 96, i.e. ~24 ms/series. **A masked point at side 96 with a constant live
count costs 6.7 s in the child**, ~0.7 ms/series, thirty times cheaper. That is what made three
fixtures, two chunkings and three repeats affordable in one session, and it is why the fourth
closure boundary — *"linearity cannot be established on this machine at any affordable cost"* —
needs re-reading: it was priced against a **full-live** ladder.

---

## Task 10 — the 2b exit-criteria suite, audited before it is written

Run 2026-08-19, against the brief in the plan plus the two deliverables added when 8b closed:
a per-criterion verdict naming its **reading**, and a statement of what 2c inherits.

### (j4) EVERY ONE OF THE SIXTEEN ALREADY HAS COVERAGE, SO THE DEFAULT OUTCOME OF THIS TASK IS A ROLL-UP

`rg` over `tests/`, per criterion: **all sixteen are asserted somewhere already**, in the module
its own task landed. 2a's Task 13 stated the failure mode in its own first paragraph — *"a
criterion checked by calling the helper the implementing task's test called shares its whole
derivation with the subject"* — and **this sub-phase is more exposed to it than 2a was**, because
six of 2b's criteria are about a *number* rather than a behaviour, and a number re-read from the
constant that published it agrees with itself by construction.

**So the first act is the partition, and it is the deliverable that stops this being a formality:**

| criterion | is there an OUTSIDE? | what the outside is |
|---|---|---|
| 1, 2, 3 | **no** | pure code shape, falsifiable by reading and by arithmetic. **Stating that there is no outside is the honest answer**, not a gap to paper over with a subprocess that proves nothing |
| 4 | yes | the floor probe is a bare launcher by construction; the criterion is that **both** floors are recorded and **differ** |
| 5 | yes | the CLI in a subprocess, and the refusal read out of **stderr and an exit code** rather than an exception type |
| 6, 7 | **verdicts, not runs** | the measurements are not in the suite (Tasks 4, 7, 8, 8b precedent). What the suite can hold is the **verdict with its reading**, and a test that fails if the record and the constant disagree |
| 8 | yes | a fresh subprocess over many tiles; Task 8's suite test already bounds total growth at 6 MB with an injected positive control |
| 9 | yes | a store **read back from disk**, worst array chosen by measurement rather than named |
| 10 | yes | **two stores on disk**, compared attr by attr |
| 11 | constructed | no cgroup limit on this box, so the branch must be built |
| 12 | yes, and the criterion says so | **a second process** reads a cache it did not write |
| 13 | yes | the digest moves when a distribution's version moves — constructed, since no version moves during a run |
| 14 | yes | delete the cache, then **resume in a subprocess** |
| 15 | yes | two runs, the second reading the first's `tile_side_basis` off disk |
| 16 | **met at Task 9** | five tests already recompute it; re-asserting here is the roll-up in its purest form |

**Six have a genuine cross-boundary component that no single task's module can express** — 5, 9,
10, 12, 14, 15 — which is the same count 2a's suite had, arrived at independently.

### (a5) THE BRIEF'S "DRIVEN FROM OUTSIDE WHEREVER AN OUTSIDE EXISTS" HAS A CLAUSE PEOPLE DROP

The clause is *"wherever an outside exists"*, and for criteria 1, 2 and 3 it does not. **A
subprocess wrapped around a call to `resident_bytes_per_series` is not an outside**; it is the
same derivation in a second interpreter, and it would read as stronger evidence than the in-module
test while being identical to it. **Where there is no outside, the criterion is closed by the
task's own falsifiable-by-reading test and this suite records that it is**, with the reason.

### (a4) THE VERDICT TABLE IS ITSELF A WORKED EXAMPLE AND ITS ARITHMETIC MUST BE RECOMPUTED

The closing table states, per criterion, met / met-with-reduced-scope / failed. **Every figure it
quotes is a number this sub-phase measured, and (a4) says a number in a report is as unverified as
one in a brief** — this has fired four times here. So the table quotes **no figure that is not
either recomputed by a test or carried in a record a test recomputes**, and criteria 6 and 7 carry
their **reading** in the same sentence as their verdict, which is the ambiguity that let them read
as settled through four tasks.

### (i2) THE SUITE'S OWN POSITIVE CONTROL, AND IT IS THE ONE A CLOSING SUITE MOST NEEDS

A closing suite is almost all assertions of the form *"the property holds"*, and a suite whose
fixtures cannot express the violation passes for free. **Each cross-boundary test here carries the
construction that makes it fail** — a store written at a different basis, a cache deleted, a
second process with no cache, a budget below the floor — rather than only the passing arm.

### (d) AND THE VOCABULARY THE BRIEF NEEDS THAT THE TREE DOES NOT HAVE

`rg`: nothing in the tree records an exit-criterion verdict as a value, and nothing binds a
verdict to the test that establishes it. **The closing table has lived in `PROGRESS.md` and the
plan only** — which is exactly how criterion 6 came to read *"MET as written"* for three tasks
after the measurement under it had been withdrawn.

### COST, BECAUSE THE SWEEP IS 1274 s AND THIS TASK ADDS SUBPROCESSES

2a's Task 13 uses **one input and one config for the whole module** and the session-scoped floor
stub (`METAMER_FLOOR_BYTES`, 1 MB) that makes a `run()` cheap. Task 10 follows both. **The budget
constants must be re-derived at 2b's arithmetic rather than copied from 2a's module** — 2a's
`ONE_POINT_PER_TILE` was already re-derived once at Task 2 when the budget stopped being the
block, and its comment records that the old value silently fell below the floor.

---

## OQ18 Task A — the pipeline hypothesis, audited before the harness exists

**THE BRIEF.** Free the tile block before the store write and measure whether the peak moves.
**It is a hypothesis test and not a repair**: it succeeds if the peak moves and it succeeds if it
does not, because the second outcome says the peak is not where the sampler was read as saying it
is dominated, and that redirects the crossed measurement rather than licensing one.

### (j4) THE TABLE IN HAND ALREADY DECIDES TWO OF THE THREE FIXTURES, AND THEY BECOME CONTROLS

Task 8b's own columns answer part of this before anything runs. **At N = 60, M = 2 and at
N = 240, M = 2 the peak's argmax is 1.6-2.3 s, which is tile assembly** -- earlier than the
earliest moment a free after `fit` could occur. **A maximum already attained cannot be lowered by
an allocation released afterwards**, so at both M = 2 fixtures the predicted effect on the peak is
exactly zero, by arithmetic rather than by expectation. They are therefore the **control arm** of
this experiment and not two more chances for the hypothesis to succeed.

**The whole hypothesis lives at N = 60, M = 6**, whose argmax is the only one that sits after the
write path.

### (a4)/(a6) AND THE LABEL ON THAT ARGMAX IS AN INFERENCE, NOT A READING

OQ18 records the M = 6 peak as landing at *"store finalisation (45.02 s at every side)"*. Read
against `task-8b-harness.py`: **45.0 s is `target_s`, the pad's own target**, the pad runs
**inside `on_tile_written`**, and `run.py` calls that callback at line 959 -- **after `write_tile`
has returned** at line 945. So 45.02 s is the end of the pad, and the store write finished some
twenty-eight seconds earlier at the `at_tile` timestamp of 14.1-17.0 s. **The timestamp says
"the last moment the trace ticked up", and "the store write" was read into it.**

**This matters to the test's design rather than being a footnote.** With the transient at M = 6
measured at **-39.9 B/series**, that fixture's peak is its at-tile residency to within noise, so
what A does there is remove **480 B/series of block from a residency**, and whether that lowers
the *peak* depends on whether the assemble/fit window ever sat higher -- which no reading in hand
reports. **The pre-flight's own leading expectation is therefore recorded as undetermined**, and
the per-phase maxima this harness adds are what settle it.

### (a7) THE PREDICTIONS ARE STATED AS A DEPENDENCE, BECAUSE ONE FIXTURE CANNOT REFUTE A SHAPE

The block is `n_series x n_time` float64, so it is **`n_time * 8` B/series exactly** -- 480 at
N = 60 and 1920 at N = 240. Every predicted magnitude below is written in those terms rather than
as a byte count, so a result that moves by the wrong *amount* at one fixture is distinguishable
from one that moves with the wrong *variable* across three. **A prediction stated at one fixture
is not falsifiable in the way that matters here**, which is the whole lesson of 8b's three ratios.

### (j2) THE INSTRUMENT DOES NOT EDIT `run.py`, AND WHAT THAT COVERS IS STATED

The free is applied by wrapping `batch.run.write_tile` and **rebinding the caller's frame local**
through PEP 667's write-through proxy, which this interpreter supports -- verified before the
harness was written: an 80 MB array, `x is None` in the caller afterwards, and **80.0 MB off the
resident set**. Deletion is refused by the proxy (`cannot remove local variables`); rebinding to
`None` is not, and it is the same effect as the `block = None` a production edit would insert.

**The equivalence is a claim about two line ranges and was checked by reading them.** Between
`fit` returning at run.py:944 and `write_tile` at 945 there is nothing at all; after `write_tile`
the loop body reaches the callback and `mark_complete`, and **neither takes `block`**. What the
simulation does **not** cover: the multi-tile path, where the change alters the block's lifetime
in every iteration rather than once -- this harness is one tile by construction (`grid = side`),
which is what makes its peak attributable.

### (i2) THE FREE IS AN ABSENCE, SO IT NEEDS ITS OWN POSITIVE CONTROL -- AND ONE FIXTURE CANNOT HAVE IT

"The RSS did not rise" and "the free never happened" are the same reading, which is the fifth
register of (a0). Two fields separate them: **`freed_bytes`**, what the wrapper actually saw and
released, and the **working set read immediately before and after the rebinding** in the same
frame. A zero drop with a nonzero `freed_bytes` is the allocator, not a failed free.

**And the exception is predicted rather than discovered.** At side 16, N = 60 the block is
`256 * 60 * 8` = **122 880 B, below glibc's 128 kB mmap threshold**, so its free returns to the
arena and need not leave the resident set at all. **That point is named in advance as the one
where a null is uninformative**; at N = 240 the same side is 491 520 B and above the threshold.

### (e) THE ARM MUST NOT CHANGE THE RESULT, AND THAT IS THE SAFETY CHECK CONSTRAINT 3 ASKS FOR

Read for retained views before measuring anything: **`FitResult` holds fourteen freshly allocated
arrays and no view of `y` or `mask`** -- `theta`, `beta`, the two error arrays, `loglik`,
`outcome`, `init_rung`, `n_iter`, both `n_eff` arrays and `scores`'s five, each allocated inside
`fit` at the batch's shape. `write_tile`'s signature takes `store_path`, `tile`, `result`,
`criteria`, `index`, `has_trend` and **no block**. And `mask=np.isfinite(block)` at run.py:940 is
an **inline temporary**, so it is already released when `fit` returns -- which is independently
corroborated by 8b's data term fitting at **7.89 B/time-step against a charged 9**, the mask's
byte being the one not resident.

**So the static answer is that freeing is safe, and the run-time answer is asserted rather than
assumed**: every point digests the store's `outcome` and `theta` arrays, and the two arms at one
point must produce identical digests. A crash or a silently different result is what the reading
would be worth nothing against.

### (a5) WHAT A'S SUCCESS WOULD COST, STATED BEFORE IT IS MEASURED

If the free collapses peak onto residency, **`resident_bytes_per_series` becomes wrong in the
other direction**: its `n_time * 9` term charges a block that would no longer be resident at the
tile boundary, and 8b measured that term as the one thing the model gets exactly right (533.5
against 540). **A repair that fixes the criterion by invalidating the model's one exact term is
not a free win**, and saying so now is what stops it being discovered as a surprise in the task
that lands it.

### (k) AND THE ARMS ARE INTERLEAVED, BECAUSE THIS BOX DRIFTS WITHIN A DAY

8b's available RAM fell across its own measuring day, and 8i's 2x2 established that damage needs
pressure **and** time. So the two arms are run **back to back at each (fixture, side, repeat)**
rather than as two blocks, which is what stops the arm being confounded with the hour. Run length
is held at 8b's own targets -- 30 s at N = 60, M = 2 and 45 s at the other two -- so the off arm
is also a reproduction of 8b's ladder, and every point carries stall rate, reclaim shortfall read
**in the child**, and available RAM on both sides.

### COST

Ninety points: three fixtures x five sides x three repeats x two arms, at 8b's own prices --
about **63 minutes**, against the crossed 2 x 2 that B would need. That ratio is the second
reason A goes first.

### WHAT THE RUNS FOUND, AND THIS AUDIT'S OWN LEADING CANDIDATE WAS AMONG THE REFUTED

Four of ten predictions were refuted and one could not be tested; the table and the numbers are in
`PROGRESS.md`'s *What OQ18 Task A established* and are not repeated here. **What this audit got
right was that the M = 2 fixtures are controls rather than chances**, and that OQ18's
*"store finalisation"* label is an inference. **What it got wrong is the shape of the same
mistake it had just diagnosed**: it accepted 8b's *"tile assembly"* label for the M = 2 argmax
while rejecting the M = 6 one, on no better evidence — and the phase boundaries put that argmax
in **`fit`**, with assembly measured at about two milliseconds at those sides. Rejecting one
inference and keeping its twin is where a partial audit lands.

**And P3 is the instructive refutation.** It predicted that a free below glibc's 128 kB mmap
threshold returns nothing and that everything above it returns the block. Measured: nothing is
returned below about 1.5 MB **inside a run**, while a fresh interpreter returns every one of the
same sizes. **The threshold is dynamic and the process's own history moves it**, so an allocator
prediction read out of a manual page is a prediction about a program with no history.

---

## OQ18 Task A-prime — naming the fit transient, audited before the harness exists

**THE BRIEF.** Task A left the production peak inside `fit` and unnamed. A′ names it. **The
precondition it establishes for B is not a number**: if the transient is several allocations, a
crossed 2 × 2 measures their sum and no shape fits it — 8b's failure, one level in.

### (j4) THE SUSPECT IS NAMED IN A DOCSTRING ALREADY IN THE TREE, WITH ITS MAGNITUDE

`SignalSpec._restricted_singular_values` has three tiers and says so: the third builds
`x[None] * mask[..., None]` for `svdvals` and **"the batched route allocates `B * N * k * 8`
bytes (320 MB at B = 10⁴, N = 10³, k = 4)"**. At this project's fixtures that is **1920 B/series
at N = 60 and 7680 at N = 240**, against Task A's measured transient of **1017 and 6974**. **The
tell that this is (j4) rather than a hypothesis: the number was written down before anyone
measured the transient, and nobody compared them.**

**AND THE FIXTURE SELECTS THE TIER, WHICH IS WHY THIS PROJECT SEES TIER 3 AT ALL.** Sixteen live
series and the rest wholly masked is precisely *"masks differ"*. **A production run is the same
shape** — real data has gaps that differ per series — so this is not an artefact of the harness.

### (a7) THE HARNESS MEASURES THE TENSOR RATHER THAN COMPUTING IT

`B * N * k * 8` is an arithmetic claim about an allocation, and Task A's own P3 is what happens to
arithmetic claims about allocations. So the wrapper reads **`nbytes` off `svdvals`'s argument at
the call**: that object *is* the allocation. The dependence then falls out of two fixtures without
being assumed — and if the reading disagrees with `B * N * k * 8`, the reading wins.

### (i2) THE POSITIVE CONTROL IS A TIER, AND IT IS FREE

`live = 0` masks every series identically, so tier 2 fires and no per-series tensor exists. **The
discriminator is the B-slope, not the level**: sixteen series of optimizer work is a constant in B
and the tensor is not. The two arms also differ in whether any fit runs, which is why the slope
and not the difference is what is read.

### (j2) AND THE NAMING INSTRUMENT IS QUARANTINED BEFORE IT IS USED

`tracemalloc` keeps a frame record per live allocation, so its arm's resident set is not a
measurement of this program. It is flagged in the payload, its RSS is not published, and its
snapshot is taken at the one moment the temporary can be attributed — inside the `svdvals` call
that holds it, gated to calls above 1 MB so the per-series calls cannot bury it.

### (e) WHAT THE SMOKE POINT ALREADY BIT, AND IT IS AN INSTRUMENT DEFECT

Side 48, N = 60, `live = 16`: the fit phase's maximum is **inside `design_info`**, the resident
set rises **4.5 MB across the `svdvals` call against a predicted 4.42 MB tensor** and comes back
down — a before/after difference across `design_info` sees only **+0.27 MB** of it — and RSS
across the batch is **flat to 0.15 MB over 4608 `optimize_series` calls**, so there is no
accumulation. **And the first version of the wrapper recorded the LAST `svdvals` call rather than
the largest**, so a `(1, 4, 4)` call from inside the objective stood where the `(2304, 60, 4)`
tensor belonged: **128 bytes in the slot where 4.42 MB belongs.** Recorded here because the fix
is the reason the ladder's numbers mean anything, and because a smoke point that changes an
instrument is the smoke point earning its keep.

### WHAT THE RUNS FOUND, AND ALL EIGHT PREDICTIONS HELD

The numbers are in `PROGRESS.md`'s *What OQ18 Task A-prime established*. **The audit's own
suspect was right and its magnitudes were right**, which is the first time in this sub-phase that
has happened — and the reason is worth recording rather than celebrating: **the suspect was
already documented in the tree, with its size, in the docstring of the function that allocates
it.** (j4) says an existing measurement is evidence rather than history; this is the same rule at
a *description*, and the cost of not having read it was Task A.

**The one prediction that needed its own caveat is the one that shows the instrument's limit.**
B6 predicted `tracemalloc`'s top site would be signal.py's tier-3 line, and wrote down that the
ranking might be dominated by Python-object sites instead. Measured: **top at N = 240 (70.78 MB
in 3 blocks) and second at N = 60**, behind 31.74 MB of import machinery spread over 206 860
blocks. **The block count is what separates them** — three blocks is an array, two hundred
thousand is an interpreter — and a ranking by size alone would have read the second as a rival.

---

## OQ18 Task A-double-prime — the characterisation, audited before the ladder

**THE BRIEF, AND IT IS ONE QUESTION.** With the tier-3 tensor chunked, does the fit-phase
maximum fall to the modelled residency, or does a second allocation become dominant? **Not a
study**: the term's size is already known exactly — `B · N · k_beta · 8`, read off the argument
at a ratio of 1.000 across six cells — so what is unknown is only what remains once it is
bounded.

### (j4) THE MEASUREMENT THIS IS COMPARED AGAINST IS ALREADY IN HAND

Task A-prime's tier-3 arm at N = 60, M = 2 — sides 48, 64, 96, three repeats, same harness, same
fixture, same masked duration-controlled construction. **So this ladder is one arm, not two**,
and the comparison costs nothing beyond running it. The A-prime arm's fit-phase excess above the
start of `fit` was **1996.0 ± 0.3 B/series against a 1920 B tensor.**

### (a7) THE SHAPE IS KNOWN, WHICH IS WHY A CROSSED DESIGN IS THE WRONG INSTRUMENT HERE

B was specified to characterize a term whose shape refused three fixtures. **That was the
transient, and the transient is now named.** A crossed 2 × 2 over a term whose dependence is
`n_time · k_beta · 8` per series, verified at a ratio of 1.000, would be measuring a known
quantity at four points — and it would say nothing about what this measurement asks, which is
about the *residue*.

### (i2) THE CHUNKING'S OWN POSITIVE CONTROL LANDED BEFORE THE LADDER

*"The results are identical"* is satisfied by never chunking, so the suite records every
`svdvals` call and asserts **five batched calls of at most five series at a chunk of five**.
Without it the equality test is an equality between one implementation and itself. **It caught
its own first assertion** — `design_info` also takes a two-dimensional `svdvals` of the
unrestricted design, so the count came back 6 against 5.

### (k) AND THE RUNTIME COST IS MEASURED RATHER THAN ARGUED, BECAUSE THE TRADE IS THE DECISION

A memory repair that doubles fit time is a different trade from one that costs nothing, and the
fit is expensive. Measured at B = 9216 across chunk sizes 64 to 9216: **flat at N = 60, and at
N = 240 chunking is faster than not** — 121.3 ms at 512 against 161.2 ms whole. **The constant is
therefore chosen for the bound and not for the clock**, which is only sayable because the clock
was measured first.

### WHAT WOULD MAKE THIS MEASUREMENT WORTHLESS, NAMED IN ADVANCE

The fixture must reach **tier 3**. Sixteen live series among wholly-masked ones makes the masks
differ, which is what selects the batched path — a fixture whose masks are uniform would measure
tier 1 or 2 and return a null that says nothing about the change. **The A-prime arm this is
compared against used exactly that fixture**, and the `svdvals_max_input_bytes` field is what
proves the path was taken at every point rather than assumed.

---

## OQ18 Task A-triple-prime — naming the residue, audited before the ladder

**THE BRIEF.** Name the **618.4 ± 24.2 B/series** fit-phase residue that survived bounding the
tensor, and which criterion 7's remaining **+4.63 MB** is made of.

### (a7) THE SHAPE IS ALREADY CONSTRAINED BEFORE ANY CANDIDATE IS PROPOSED

A-prime's tier-2 arm gave **618.3 ± 30.5 at N = 60** and **514.3 ± 74.2 at N = 240** — 1.3σ
apart, so the residue is **`n_time`-independent**. That excludes every data-shaped term outright:
the block, the mask, the design tensor, anything charged per time step. **What is left is
per-candidate and per-series**, which is the shape of `fit`'s preallocated output arrays — and
also the shape of the slot term 8b measured at **≈ 240 B per candidate per series against a
charged 193.**

### THE TIER-2 ARM IS PROMOTED FROM CONTROL TO SUBJECT, AND IT IS ALSO THE CHEAPER ONE

`live = 0` makes every mask identical, so tier 2 fires and **no per-series tensor exists at
all** — the residue is isolated without the chunking in the picture and without 17.69 MB sitting
on top of it. **A-double-prime used tier 2 to check tier 3; this reverses that**, and the bounded
tier-3 arm becomes the confirmation.

### (j2)/(a7) THE SIZES ARE READ, AND THE SMOKE POINT ALREADY READ THEM

Two instruments, both reading rather than fitting: `np.full`/`np.empty`/`np.zeros` recorded
during the fit call **with the caller's file and line**, and every array `FitResult` carries
summed by `nbytes` **deduped by identity**. Measured at side 48, N = 60, M = 2 before this audit
was written:

| what | B/series |
|---|---|
| `fit.py:200-211` — the preallocated output block, twelve arrays | **368** |
| `signal.py:509` — a `(B, k_beta)` float64 inside `design_info` | **32** |
| **named total** | **400** |
| **measured residue** | **618.4 ± 24.2** |
| **unexplained** | **≈ 218** |

**AND THE DEDUPE WAS NOT COSMETIC.** `FitResult.loglik` and `scores.loglik` are one allocation
under two names; summing both inflated the inventory by **18 B/series** and would have made the
residue look better explained than it is. **(a) at an inventory**, caught by the smoke point.

### (i2) WHAT WOULD MAKE THIS MEASUREMENT WORTHLESS

An instrument patched in one module namespace and read in another comes back empty and reads as
an absence. `run` looks `fit` up in **its own** namespace, so the counter is installed in both —
and the smoke point's nonzero `allocation_count` is what proves it fired rather than the fixture
being quiet.

### THE LEVER, AND IT IS THE DISCRIMINATOR THIS TASK TURNS ON

The named block scales with the **candidate count**: hand-derived, `193·M + 16` per series, so
**400 at M = 2 and 1190 at M = 6**. The unexplained ~218 either scales with M or does not, and
those give **1790** against **1390** at M = 6. **One ladder at M = 6 chooses between them**, and
neither answer is the one I would assume.
