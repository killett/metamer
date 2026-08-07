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

Supporting measurements: mean iterations 68.7 at d=3; path A active-mask utilization
**0.64**, so path A's real cost sits a further ~1.6× above its own optimistic bound;
canonical filter pass 0.745 ms/series; compute reference 125.6 ns per `P = F P Fᵀ + Q` step
at d=3 (1.00 GF/s); STREAM 10.59 GB/s at one thread against 12.03 GB/s total at four, i.e.
**3.01 GB/s per core at full occupancy**.

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
- **Path B is inside the 19 ms budget by ~0.4 ms at B=20 000** (18.6 ms). That is the mini
  PC's slow cores and it is the number a faster machine improves — but on *this* machine it
  is not comfortable.

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
| **Whether the 16 GB machine can hold a production tile** | blocked on the `_augment` defect below, not on the spike | fix `_augment`, then re-measure `tile_side` |

---

## Carried into Phase 2

**`KalmanEngine._augment` materializes the augmented `[y | X]` block** — a
`(B, N, 1+k_β)` float64 array, 25 200 B/series at N=630, k_β=4, against design doc §9.4's
per-series target of 8 682 B, and it does not vanish when the design is shared. `tile_side`
at a 1 GB budget is therefore **171, not 339**, and **all Phase 2 tile arithmetic must use
`memory.resident_bytes_per_series`, not `memory.bytes_per_series`**, until the engine
streams those columns instead of concatenating them. Full note in `PROGRESS.md`.

This is the reference engine's hot loop, so fixing it means re-pinning the path-B agreement
test and the MVN oracles — Phase 2 work, deliberately not patched during Task 17.

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
