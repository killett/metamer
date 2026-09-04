# The conditioning discriminator — both bands held, 2026-09-04

**The predictions were committed before the run** at
[`phase2d-difficulty-rung-predictions.json`](phase2d-difficulty-rung-predictions.json) (readings C1
and C2), the measured records are at
[`phase2d-conditioning-probe-measured.jsonl`](phase2d-conditioning-probe-measured.jsonl), and the
harness is [`phase2d-conditioning-probe.py`](phase2d-conditioning-probe.py).

**16 points, both regimes, the whole factor range, interleaved by point, N = 630, M = 3, the shipped
`fit`.** Host quiet check: **passed, loadavg 2.37, stall 0.0 ms/s** — and it **refused an earlier
attempt at 4.46**, from which no number exists.

| # | reading | band | measured | verdict |
|---|---|---|---|---|
| **C1** | non-OK fraction, version 1 minus version 2 | `|d| <= 0.05` | **−0.0208** (0/48 against 1/48) | **HELD** |
| **C2** | median log10 `cond(H)` over OK fits, version 2 minus version 1 | `|d| <= 0.5` decades | **+0.023** | **HELD** |
| **C2b** | undefined-`cond` fraction difference | `|d| <= 0.05` | **0.0000** (zero either side) | **HELD** |

## THE STOP APPLIES CLEANLY, AND THE OBSERVATION THAT RAISED THE QUESTION DID NOT REPRODUCE

**The small fixture's 93/96 → 96/96 does not appear at production length, and its SIGN reverses.**
Version 2 has **one more** non-OK cell out of 48, not fewer — a single `DEGENERATE_HESSIAN` against
none. **So the convergence improvement was a property of `n_time = 48`, not of the signal**, and the
confound the discriminator was built to catch is **not present at the length the rung runs at**.

**Conditioning is unchanged to within a rounding error**: 0.023 decades on a median near `10^1.4`,
against a band of 0.5 that was set from the argument that an exactly absorbed column moves the path
and not the curvature. **The argument predicted the result and the observation did not** — which is
why the band came from the argument.

**CONSEQUENCE: the pre-decided stop is NOT suspended.** A null at the rung is the finding as
written, and the prepared conclusion in the predictions file is available.

## WHAT ELSE THE PROBE MEASURED, AND ONE CAUTION FOR R1

| | version 1 | version 2 |
|---|---|---|
| iterations per point | **24.69** | **40.44** |
| seconds per point | 16.28 | 31.03 |

**24.69 reproduces the signal probe's figure for 2d's own parameters exactly**, which is a
cross-check on the builder rather than a new number.

**THE CAUTION: 40.44 SITS AT THE LOWER EDGE OF R1's [40, 47] BAND.** The signal probe measured
**43.50** at `fields.BASE` alone; these 16 points sample the whole field, whose `factor` runs 0.5 to
3.0, and they come back lower. **R1 may fire from below on the rung**, and if it does, the reading is
that the per-cell scaling holds `rise/sigma` constant while `rho` in samples still varies — which was
the known residual and is worth about one iteration across the factor range, not three. **This is
recorded before the rung so that a fire is read against a prediction, not against a memory.**

## THE SECONDS HERE ARE NOT A RE-PRICE, AND SAYING SO IS (j8)'s SECOND REGISTER

**31.03 s/point against the cost basis's 20.65 is NOT evidence that the rung costs 50% more.** The
workload differs: this probe fits **one series per call** (`B = 1`), where the cost basis batched
sixteen, and it ran on a host whose load the gate passed at 2.37 rather than at rest. **A rate is a
measurement of a workload and both changed.**

**The iteration ratio is the quantity that survives:** 40.44 / 24.69 = **1.64** here, against
43.50 / 25.38 = **1.71** in the cost basis. **The rung is priced from the deterministic proxy and
converted late**, exactly as (j8) requires, and this probe does not move the price.
