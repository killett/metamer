# Stage-1 spike verdict — path B adopted

**Date:** 2026-08-07 · **Decides:** design doc §9.2's staged spike, stage 1 ·
**Consequence:** Task 19 (batched trust-region) deleted, not deferred

---

## Verdict

**Path B — the compiled per-series backend (`metamer.core.engines.compiled`) — is adopted
as the default.**

**Path A — the batched numpy backend (`metamer.core.engines.kalman`) — is retained
permanently as the correctness reference**, together with the plain per-series scipy loop
in `optimize.optimize_series`. A correctness reference does not need to be fast, and path
A is the implementation every MVN-oracle test and the path-B agreement test are pinned
against. It is not deprecated and must not be deleted.

**Task 19 is deleted rather than deferred.** The batched trust-region optimizer existed
*only* to make path A fast. Path A is not the production path, so the machinery has no
purpose. Path A's permanent form is the per-series scipy loop that already exists and is
already tested.

---

## What was measured

One machine: the **Ubuntu mini PC, 4 slow cores, 16 GB RAM**. Composite
`white + matern12 + matern32` (d=3) and `white + matern12` (d=1), N = 630 on a decimal-years
axis, k_β = 4, objective ML.

`bench/minipc.json` — full sweep, B = 1000, threads {1, 4}, gaps {none, 10% scattered,
40% contiguous}. A:B ratio at **d=3**:

| threads | none | 10% scattered | 40% contiguous |
|---|---|---|---|
| 1 | 3.04 | 3.19 | 3.41 |
| 4 | 4.72 | 5.15 | 5.92 |

`bench/batch-sweep-d3-1thread-nogaps.json` — **path B's single worst cell** (d=3, one
thread, no gaps: no parallelism advantage and no gaps to skip), swept over batch size:

| batch | A:B | path A bound (ms/fit) | path B (ms/fit) |
|---|---|---|---|
| 1 000 | 3.31 | 59.9 | 18.1 |
| 5 000 | 3.15 | 56.4 | 17.9 |
| 20 000 | 3.35 | 62.3 | 18.6 |

**The ratio asymptotes; it is not still falling.** The earlier drop from **3.76 at B=200 to
3.04 at B=1000** was path A amortizing its per-timestep Python overhead as the batch grows,
and that transient has completed by B=1000. Across B = 1000 → 20 000 the ratio is flat in a
**3.15–3.35** band. Production B is ~29 000 (tile side 171 squared), so B=20 000 is close to
production scale.

> **All figures in this section are the 2026-08-07 measurement, taken while both engines
> materialized `[y | X]`.** They are kept as the baseline the re-measurement is against;
> the current numbers, and the production-scale B that replaced ~29 000, are under
> "The one condition attached to this answer" below.

Supporting measurements: ~~mean iterations 68.7 at d=3; path A active-mask utilization
**0.64**~~ — **both superseded 2026-08-10 (P3); see "The iteration sample was not the
workload" below.** They are now **32.5** and **0.637**, measured on four series that are
realizations of the fitted composite rather than on the white-noise sample these figures
came from. Canonical filter pass 0.745 ms/series; compute reference 125.6 ns per
`P = F P Fᵀ + Q` step at d=3 (1.00 GF/s); STREAM 10.59 GB/s at one thread against
12.03 GB/s total at four, i.e. **3.01 GB/s per core at full occupancy**.

---

## Why one machine is enough, and in which direction the inference runs

The gate as designed wanted the 64-core box and the MacBook. It was closed on the mini PC
alone because **both inferences are one-sided in the direction that favours path A**, and
path B won anyway:

- **Bandwidth.** Path A is memory-bound and scales with bandwidth *per core*. The mini PC
  delivers **3.01 GB/s per core at full occupancy** — high relative to a many-core box,
  where the same controller is divided among far more cores. The machine measured is
  therefore the one most favourable to path A.
- **The budget.** The 19 ms figure is core-milliseconds on slow cores. Faster cores only
  reduce path B's 17.9–18.6 ms; they cannot push it out of budget.

**A 64-core measurement should widen path B's margin, not narrow it.** That is why its
absence does not block the decision.

---

## The margin is real but thin, and it should be quoted with its scope

**Do not quote this as a clean ≥3×.**

- At production-scale B in path B's worst cell the ratio sits in a **3.15–3.35** band —
  above the rule, with **little headroom**.
- **Run-to-run scatter at that cell is ~±0.15**: the full sweep measured **3.04** at
  B=1000 and the batch sweep measured **3.31** at the same B, on the same machine, minutes
  apart. The rule is met at every measurement taken, but the margin is inside the range a
  repeated measurement could move.
- ~~**Path B is inside the 19 ms budget by ~0.4 ms at B=20 000** (18.6 ms).~~
  **SUPERSEDED 2026-08-10 (P3).** That figure carried an iteration count measured on white
  noise. On a representative sample path B is **6.5 ms at B=20 000** and **7.1 ms at the
  production B = 114 244** — a 2.7× margin, not 0.4 ms. **Nothing about the ratio moved**;
  the iteration count cancels from A:B and multiplies both ms/fit columns. See below.

Where the margin is comfortable: **every other cell**. Four threads gives 4.72–5.92 at
d=3, and the ratio **rises monotonically with gappiness in all four rows** of the full
table, because the compiled loop branches past a masked update while the batched path
evaluates it and multiplies by zero. Real records are gappy, so the worst cell measured is
better than the worst cell that occurs.

---

## What this does NOT establish

| not established | why it matters | what would close it |
|---|---|---|
| **Path B at high thread occupancy** | measured at 1 and 4 threads on a 4-core box. `prange` over series at 64 threads may hit false sharing on `accum`, or saturate the controller at a different point | run `bench/spike.py` on the 64-core box at `--threads 1 --threads 4 --threads 64` |
| **The roofline model's predictive accuracy** | the compute/bandwidth pair is meant to predict one machine's result from another's. **One data point cannot validate a two-parameter fit** — nothing here tests the model, it only supplies its first point | a second machine's roofline pair plus its measured canonical filter pass, checked against the prediction |
| **arm64 portability of the toolchain** | `numba` on `osx-arm64`/`linux-aarch64` is untested here, and `celerite2` has **no `osx-arm64` conda-forge build** at all, so it is pinned to `[target.linux-64.dependencies]` | run the suite and `bench/spike.py` on the MacBook |
| ~~**Whether the 16 GB machine can hold a production tile**~~ | **UNBLOCKED 2026-08-10.** `_augment` is gone from both engines and `tile_side` is 338 at a 1 GB budget, 8722 B/series resident against §9.4's 8682 B model | — |

---

## The one condition attached to this answer — DISCHARGED 2026-08-10

**Re-measure the spike after `_augment` is fixed.** Done. `bench/minipc-streamed.json`,
same one-command harness, `--threads 1 --batch 1000 --batch 20000 --repeats 3`.

**THE FALSIFIER IS NOT MET, IN ANY CELL OR ANY HARNESS.** It was: *if the d=3, one-thread,
no-gaps ratio falls below 3× at production-scale B, the ≥3× rule is no longer satisfied and
the stage-2 decision (build the batched trust-region) is back on the table.* The lowest A:B
measured anywhere after the fix is **3.27**; at the new production-scale B it is **4.05**.
Task 19 stays deleted.

The spike harness, d=3 one thread — path B's worst cell in every column:

| gaps | A:B before | A:B after (B=1000) | A:B after (B=20 000) |
|---|---|---|---|
| none | 3.04 | 3.84 | 3.85 |
| 10% scattered | 3.19 | 3.63 | 4.06 |
| 40% contiguous | 3.41 | 4.42 | 5.03 |

The batch-sweep harness at the same cell, `bench/batch-sweep-d3-1thread-nogaps-streamed.json`:

| batch | A:B before | A:B after |
|---|---|---|
| 1 000 | 3.31 | 3.27 |
| 20 000 | 3.35 | 3.28 |
| **114 244** (the new production tile) | — | **4.05** |

### THE TWO HARNESSES DISAGREE ABOUT WHETHER THE RATIO MOVED — RESOLVED BY P4, BELOW

**They were never measuring different things.** The 0.57 spread is inside one harness's own
between-process scatter, which is **±0.4 at this cell, not the ±0.15 this note assumed**.
See "The scatter was assumed, and it is four times what was assumed" below. The paragraphs
that follow are the state of knowledge on 2026-08-10 before that was measured, kept because
the separation they draw — path B's gain resolved, path A's not — survives.

The spike says the worst cell went 3.04 → 3.84; the sweep says 3.31 → 3.27. **A 0.57 spread
on the same quantity, against the ±0.15 run-to-run scatter this note assumed.** The ±0.15
figure understates the variation on this machine, and any future restatement of the margin
must name its harness as well as its B and thread count.

Going to absolute per-pass seconds per series (d=3, one thread, no gaps, B=1000) separates
what is resolved from what is not:

| | spike 08-07 | sweep 08-07 | spike 08-10 | sweep 08-10 |
|---|---|---|---|---|
| path A | 6.88e-4 | 8.73e-4 | 6.97e-4 | 6.79e-4 |
| path B | 2.26e-4 | 2.64e-4 | **1.82e-4** | **2.07e-4** |

- **Path B's gain is real and consistent: −19% in the spike harness, −22% in the sweep
  harness.** Both directions agree and the size agrees.
- **Path A's change is NOT resolved.** +1% by the spike, −22% by the sweep — and the two
  harnesses already disagreed by **27%** on this identical quantity *before* the fix
  (6.88e-4 against 8.73e-4), so the between-harness scatter is larger than the effect being
  asked about. **The honest answer is that path A's cost did not measurably move.**

**The reasoning written into this condition is therefore wrong on the half that is
resolved.** It predicted the fix would help **path A** most — path A being memory-bound,
the removed block being ~25 kB/series of its traffic — and *by more than it improves path
B, whose compiled loop already reads `y` and `X` with far better locality*. Measured, path
B is the engine that gained. The mechanism the prediction missed is that path B was reading
a **per-series private copy of the shared design**: B copies of the same `(N, k)` bytes
competing for cache, which is a locality problem in the per-series loop and not a bandwidth
problem in the batched one. Path A's cost is dominated by the `(B, d, n_cols)` einsum
temporaries it rebuilds every timestep, which the block never touched.

**Both machines were under load** (4 cores, load average ~3 from unrelated containers)
while these were taken, and `_time_pass` is best-of-3, which reduces but does not remove
that. A quieter re-run would tighten the numbers; it would not change the verdict, which
turns on a ≥3× threshold that the *lowest* measurement clears by 9%.

**Production-scale B moved with the fix and this note's old figure is stale.** It said
"production B is ~29 000 (tile side 171 squared)". `tile_side` is now **338**, so production
B is **~114 000** — the fix quadrupled the tile it was measured against, which is the one
way it could have invalidated its own re-measurement.

**Two supporting figures moved for a reason that is NOT this fix**, and conflating them
would be easy: `mean_iterations` at d=3 went 68.7 → 90.0 and path A's utilization 0.64 →
0.84. Both are computed over the **OK series only** in a four-series sample, and P1's
derived `HESSIAN_COND_LIMIT` moved one of those four from `OK` to `DEGENERATE_HESSIAN`
(d=3; one of four at d=1). The sample is `rng.standard_normal(...)` fitted with
white + Matérn 1/2 + Matérn 3/2 — white noise fitted with two timescales, the same fixture
defect open question 9 found twice elsewhere — so the verdict is right and the sample is
now two series wide. **The A:B ratio is unaffected**: the iteration count is common to both
paths and cancels. The per-fit millisecond columns are not, and they carry the new count.
See open question 11. **Closed by P3, below.**

---

## THE ITERATION SAMPLE WAS NOT THE WORKLOAD — P3, 2026-08-10

**A fixture whose data does not come from the model being fitted produces fits that are not
representative of the workload, and every statistic conditioned on `OK` inherits that.**

`measure_mean_iterations` drew `rng.standard_normal((4, N)) * logspace(-1, 1, 4)` and fitted
it with a composite carrying one or two free timescales. This was the **third** instance of
one generator defect — `test_fit.py`'s `_healthy_row` (open question 9) and `_plain_batch`
(P1) were the first two, and both were fixed by drawing from the candidate's own covariance.
The sample now does the same, with one parameter set per row.

**Two things came out of the fix, and only one of them was expected.**

**1. The workload is 2.8× cheaper than reported.** Every `ms/fit` column in this note and in
`bench/*-streamed.json` was `pass_seconds × mean_iterations`, so correcting the iteration
count rescales both paths by the same factor and **leaves every A:B ratio, and the falsifier,
exactly where they were.**

| | old (white-noise sample) | new (drawn from the candidate) |
|---|---|---|
| `mean_iterations` d=3 | 90.0, over **2** OK series of 4 | **32.5**, over **4** of 4 |
| `mean_iterations` d=1 | 43.3, over 3 of 4 | **13.0**, over 4 of 4 |
| utilization d=3 | 0.84 | **0.637** |
| utilization d=1 | 0.66 | **0.929** |

Re-reported `ms/fit` at d=3, one thread, no gaps — recomputed from the stored per-pass
seconds, which a fixture change cannot touch:

| harness | B | path A bound | path B | A:B |
|---|---|---|---|---|
| spike | 1 000 | 62.7 → **22.7** | 16.3 → **5.9** | 3.84 |
| spike | 20 000 | 68.9 → **24.9** | 17.9 → **6.5** | 3.85 |
| sweep | 1 000 | 61.1 → **22.1** | 18.7 → **6.7** | 3.27 |
| sweep | 20 000 | 70.2 → **25.4** | 21.4 → **7.7** | 3.28 |
| sweep | **114 244** | 79.1 → **28.6** | 19.5 → **7.1** | 4.05 |

**The verdict's conclusion strengthens and its numbers all move.** Path B is inside the
19 ms budget by 2.7× at production B rather than being marginally outside it at 19.5 ms.
Path A's *optimistic bound* is still 1.5× over budget, and at the measured utilization of
0.637 its realistic cost is ~44.8 ms, **2.4× over**. Both statements are the same shape as
before; the margins are wider.

**2. THE AMPLITUDE SPREAD WAS NEVER HETEROGENEITY, AND THE FIXTURE'S OWN DOCSTRING SAID IT
WAS.** The Gaussian log-likelihood is scale-equivariant: scaling a series by `c` scales every
σ by `c` and leaves the shape of the surface alone. Measured — one realization at four
amplitudes — `n_iter = [28, 28, 28, 28]` and utilization **exactly 1.0**, which is precisely
the number the docstring said the spread existed to challenge. Whatever heterogeneity the old
figures carried came from the noise realizations and, at d=3, from two of the four fits
failing. Rows now differ by **generating parameters** — timescale and nugget, at a fixed unit
state amplitude — which is what actually varies across a grid.

**Scope, stated rather than assumed.** The iteration sample is four ungapped series on one
machine. It is not a claim about the iteration count under 40% contiguous gaps, and the
per-fit columns above inherit that. Widening it is affordable only at ~5.4 s per series.

---

## THE SCATTER WAS ASSUMED, AND IT IS FOUR TIMES WHAT WAS ASSUMED — P4, 2026-08-10

The two harnesses disagreed by **0.57** on the A:B ratio at d=3, one thread, no gaps,
B=1000 (spike 3.84, sweep 3.27), and by **27%** on path A's per-pass seconds at that cell
before the streaming fix. This note's stated run-to-run scatter was **±0.15**, and that
figure was an assumption — it came from two measurements taken minutes apart, which is a
sample of two.

**Measured, on the mini PC, at exactly that cell.** Four conditions, twenty-nine
measurements:

| condition | A:B range | spread | path A range |
|---|---|---|---|
| eight rounds in one process, **same arrays** (rounds 1–7) | 3.34 .. 3.47 | **0.13** | 3.7% |
| eight rounds in one process, **fresh arrays each round** | 3.63 .. 4.08 | **0.45** | 7.6% |
| eight **fresh processes**, that cell only | 3.18 .. 4.00 | **0.82** | 18% |
| five **fresh processes**, the full sweep each | 3.07 .. 3.78 | **0.71** | 26% |

**There is no harness effect to find.** Both published numbers — 3.84 and 3.27 — sit inside
the range a single harness produces from identical code, identical seeds and identical
inputs. The full-sweep and single-cell contexts have overlapping distributions and medians
0.18 apart, against a within-condition spread of 0.7–0.8.

**What the cause IS.** The scatter is between allocations, and the level moves with them
too: path A is **~16% slower on freshly allocated inputs than on reused ones**, path B
**~4%** — so path A is about four times as sensitive to where its inputs land. The
reallocating run was taken at a *lower* load average than the reusing run (1.4–1.5 against
1.8–2.0), so machine load is not the explanation and points the wrong way.

**`repeats` cannot see any of this, by construction.** `_time_pass` takes the best of
`repeats` back-to-back passes over **one** allocation — the tight 0.13 row — and reports it
as though it were the last row. Increasing `repeats` tightens a number that was never the
uncertain one.

**What changed.** `run_spike` re-allocates its inputs per round, runs `--cell-repeats`
independent rounds, and reports the **median with its min and max** for the pass costs and
for the ratio. Fresh allocations are the production condition: a tile is materialized,
fitted and dropped. A point estimate whose scatter has to be assumed is what produced the
±0.15.

**Consequences for how the margin is quoted.** It must name its **harness invocation, B,
thread count and cell-repeat count**, and it should be quoted as a range. The falsifier is
unaffected — it is stated against the *lowest* measurement, and the lowest measurement
anywhere across all twenty-nine of the above is **3.07**, still clearing 3×, at B=1000
rather than at production scale.

### THE RESTATED MARGIN — one harness, measured scatter, named scope

`bench/minipc-unified-d3-nogaps-1thread.json`. Mini PC, d=3, **one thread, no gaps** —
path B's worst cell in every column — `--repeats 3 --cell-repeats 3`, so each row is the
**median of three independent rounds on freshly allocated inputs**, with the round-to-round
min and max beside it. `mean_iterations = 32.5` over 4 of 4 `OK`, utilization 0.637.

| B | A:B median | A:B [min, max] | path A bound ms/fit | path B ms/fit |
|---|---|---|---|---|
| 1 000 | 3.86 | [3.70, 4.01] | 21.5 | 5.42 |
| 20 000 | 3.80 | [3.43, 4.00] | 22.4 | 6.32 |
| **114 244** (production tile) | **4.33** | [4.25, 4.39] | **25.8** | **5.88** |

- **Path B is inside the 19 ms budget by 3.2× at production B** (5.88 ms), where the
  pre-P3 figure had it at 19.5 ms, i.e. marginally outside.
- **Path A's optimistic bound is 25.8 ms, 1.36× over budget**, and at the measured
  utilization of 0.637 its realistic cost is ~40.5 ms, **2.1× over**. Same conclusion as
  before, wider margins.
- **A min/max over three rounds brackets less than the eight-round study above does**, and
  the numbers show it: [4.25, 4.39] at B=114 244 against a spread of 0.82 measured over
  eight fresh processes at B=1000. **Three rounds report a range, they do not bound one.**
  Quote the eight-round figure when what is wanted is the scatter, and this table when what
  is wanted is the level.

### A CORRECT CONCLUSION REACHED THROUGH A WRONG MECHANISM IS A FINDING IN ITS OWN RIGHT

This note predicted that removing the materialized `[y | X]` block would help **path A**
most, path A being memory-bound and the block being ~25 kB/series of its traffic. Measured,
**path B is the engine that gained** (−19% and −22% in the two harnesses) and path A did not
measurably move. The mechanism the prediction missed is that path B had been reading a
per-series private copy of the shared design — B copies of the same `(N, k)` bytes competing
for cache, a locality problem in a per-series loop, not a bandwidth problem in a batched one.

**The conclusion survived and the reasoning did not, and that is worth recording as its own
finding**, because the reasoning is what the *next* prediction is built on. The next
prediction built on "path A is memory-bound, so path A gains from any traffic reduction"
would have been wrong in the same way, and a verdict that only records outcomes gives a
later reader no way to know it.

**What the reasoning is worth after P4.** One clause of it is now supported by an
independent measurement: path A really is about **four times more sensitive to memory
placement** than path B (16% against 4% on reallocation). So "path A is the
memory-sensitive path" stands; "therefore removing this particular block helps path A
most" did not, and did not follow. **This matters beyond the postmortem**: the "why one
machine is enough" argument above rests on path A scaling with bandwidth per core, and
that argument is left standing by P4 rather than undermined by it — but it is standing on
the reallocation measurement now, not on the `_augment` prediction that failed.

## Carried into Phase 2 — RESOLVED 2026-08-10

~~**`KalmanEngine._augment` materializes the augmented `[y | X]` block**~~ — it did: a
`(B, N, 1+k_β)` float64 array, 25 200 B/series at N=630, k_β=4, against design doc §9.4's
per-series model of 8 682 B, and it did not vanish when the design was shared, which put
`tile_side` at **171 rather than 339**.

**Both engines now stream.** `_augment` is replaced by `_design_block`, which validates the
design and hands back a `(1, N, k)` view when it is shared; each engine reads the
observation out of `y` and the design columns out of that block per timestep, into one
reused row. `tile_side` at a 1 GB budget is **338**, resident 8722 B/series against the
8682 B model.

**Path B was the second site of the same defect and this note did not say so** — it called
`_augment` and then `np.ascontiguousarray` on the result, so the adopted production path
carried the block *and* a copy. Fixing path A alone would have reported a `tile_side` no
production run could honour.

**The standing rule survives the fix:** all Phase 2 tile arithmetic uses
`memory.resident_bytes_per_series`, never `memory.bytes_per_series`. The two agreeing to
0.5% today is a measurement, not a guarantee.

Re-pinned rather than argued: the fix is **bit-identical** to the pre-fix engines — both
paths, shared / per-point / no design, gapped masks, across `loglik`, `normal_equations`,
`rank_x`, `outcome` and `n_used`, compared against the modules loaded out of git at
`29884aa`. Not a tolerance; the same digits.

---

## Reproducing

The harness is a one-command run and must stay that way. Nothing below needs
reconstructing:

```bash
# full sweep on any machine (change --threads and --out only)
pixi run python -m metamer.bench.spike \
    --threads 1 --threads 4 \
    --batch 1000 --repeats 3 \
    --out bench/minipc.json
```

For the 64-core box add `--threads 64`; for the MacBook use `--threads 1 --threads 8` (or
its real core count) and `--out bench/macbook.json`. Output is self-describing JSON: machine
fingerprint, the three references, mean iterations and utilization per state dimension, and
one row per (d, batch, gap case, thread count).

The 2026-08-10 re-measurement was:

```bash
pixi run python -m metamer.bench.spike \
    --threads 1 --batch 1000 --batch 20000 --repeats 3 \
    --out bench/minipc-streamed.json
```

~~**The batch sweep is not a CLI flag and never was**~~ — **it is one now, as of P4,
2026-08-10.** It was a short script over the same harness functions, and having two
entry points into one measurement is what let "which harness" become a variable in the
first place. `--dim` and `--gaps` are filters on the sweep, so the batch sweep is:

```bash
pixi run python -m metamer.bench.spike \
    --dim 3 --gaps none --threads 1 \
    --batch 1000 --batch 20000 --batch 114244 \
    --repeats 3 --cell-repeats 3 \
    --out bench/minipc-unified-d3-nogaps-1thread.json
```

`B = 114244` is `tile_side(1e9, resident_bytes_per_series(...))` squared — the production
tile at a 1 GB budget — and it needs ~1 GB of RAM to run. **Recompute it rather than
copying it** if the memory accounting ever changes again; that number moved from ~29 000 to
~114 000 when the engines started streaming.
