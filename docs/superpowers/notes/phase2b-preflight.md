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
