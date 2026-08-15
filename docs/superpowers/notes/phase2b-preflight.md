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
