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
