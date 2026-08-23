# The warm-start spike — verdict

**2c Task 0. Written 2026-08-23.** The pre-flight is in
[`phase2c-preflight.md`](phase2c-preflight.md); the predictions were committed before any arm
ran, in [`warmstart-spike-predictions.json`](warmstart-spike-predictions.json); the instrument is
[`warmstart-spike-harness.py`](warmstart-spike-harness.py) and the points are
[`warmstart-spike-measured.jsonl`](warmstart-spike-measured.jsonl) and
[`warmstart-spike-n384-measured.jsonl`](warmstart-spike-n384-measured.jsonl).

> **THE HEADLINE, AND IT MUST NEVER BE QUOTED WITHOUT THE CEILING BESIDE IT.** Warm-starting a
> pass-2 point from its nearest valid coarse neighbour, under §11.3's own rule at stride 4, saves
> **7.80% ± 0.77%** of iterations against §11.2's **30%** threshold — and **nothing measurable in
> wall clock**. Starting the same points from **their own** converged `θ̂` saves **93.97% ±
> 0.16%** of iterations and **62.18%** of wall clock. **The machinery is not weak. The source
> is.** The optimum is far less spatially coherent than the data is.

## The decision rule for P9, stated before the N = 384 fixture reported

Recorded in advance so the second fixture cannot be read to suit the first.

| P9 lands | what it means | the verdict |
|---|---|---|
| **at or above 30%** | the saving depends on record length, and the primary fixture at `N = 96` does **not** describe production at `N = 630`. The headline was measured at the wrong length | **the verdict is re-taken**, at production length, before anything rests on it |
| **anywhere below 30%** | the verdict stands | **stands** — and the size of the move is **itself worth stating**, because it tells the next reader which regime the null covers |

**A move of more than 10 points that stays below 30% does not overturn the verdict**; it
narrows the claim to the record lengths measured, and that narrowing is part of the finding
rather than a caveat on it.

## The primary fixture

16 × 16 points, `N = 96` monthly, stride 4, 240 measured points, **0 excluded**, three repeats.
Candidate set `[white]`, `[matern12 + white]`, `[matern32 + white]` — **lint-clean by
construction**, so parameter disagreement between the arms cannot be label switching in
hysteresis' clothes. Coarse points **100% OK**, and the OK filter **never** changed a source, so
the spiral is defensive rather than load-bearing. **Every arm returned bit-identical `n_iter` and
`loglik` across all three repeats**, which is a free exercise of §11.3's determinism claim along
the warm-start path — the one path §11.3 has never had a consumer for.

| arm | pooled | `white` | `m12+white` | `m32+white` | same-regime | cross-regime |
|---|---|---|---|---|---|---|
| `self` — the ceiling | **+93.97% ± 0.16%** | +97.78 | +93.48 | +92.97 | +93.91 | +94.64 |
| `warm` — the mechanism | **+7.80% ± 0.77%** | +2.31 | +6.31 | +11.64 | +9.75 | **−16.27** |
| `random` — distant source | **−2.25% ± 0.91%** | −4.16 | −2.13 | −1.60 | −2.04 | −4.76 |

**Wall clock**, mean of three interleaved repeats with threads pinned: cold **474.01 ± 12.42 s**,
warm **479.64 ± 25.29 s** — a **−1.19%** "saving", which is inside the noise and is not a saving.
`random` **−8.04%**. `self` **+62.18%**.

## The three things this establishes beyond the number

**1. THE GEOMETRY IS REAL AND INSUFFICIENT, WHICH IS MORE USEFUL THAN "IT DOES NOT WORK".**
A distant converged `θ̂` is **worse than the moment ladder** (−2.25%); a nearby one is better
(+7.80%). **Proximity is worth 10.05 points** — and that is the refutation of P4, the horn I
doubted, by 0.05 of a point against its own clause. So the two-pass geometry buys something
real. It buys 10 points on a quantity that needs 30.

**2. THE BENEFIT CHANGES SIGN AT A REGIME BOUNDARY, AND §11.1 HAS NO POLICY FOR THAT.**
Same-regime **+9.75%** against cross-regime **−16.27%** — a 26-point swing onto the wrong side of
zero. The mechanism **harms** exactly where spectral shape changes, which is where the scientific
interest is and where §11.2 says hysteresis concentrates. **This would have mattered even if the
pooled number had passed:** a 30% saving would still have needed a boundary policy, and the
two-pass warm start as specified has no notion of regime boundaries at all. **The measurement
named a missing piece of the design, not just a magnitude.** Promoted as (i2c).

**3. THE ~2% TAIL IS EVIDENCE FOR THE DECISION, NOT A CAVEAT ON IT.**
P6 passes at its pre-agreed thresholds — selection agreement **95.00%**, `|Δℓ| < 0.01` at
**97.90%**, parameter distance < 0.25 SE at **97.90%** — so permitted outcome 3 is **not**
triggered, and that was fixed in advance rather than judged after. But the tail is real: max
`|Δℓ|` **8.31** and max parameter distance **10.2 SE**. Under a "build it" outcome that tail was
the hysteresis audit's whole subject. Under "drop it" it reads as part of the case: **the
mechanism buys 7.8% of iterations and moves about 2% of cells to different optima.**

## The predictions

| # | claim | outcome |
|---|---|---|
| P1 | the ceiling arm collapses iterations by ≥ 70% | **HELD** — +93.97% pooled, ≥ 92.97% on every candidate |
| P2 | pooled saving positive and under 30%, ~18% | **HELD**, low in its 5–30% band at 7.80% |
| P3 | saving ordered by parameter count, `white` under 5% | **HELD** — 2.31 / 6.31 / 11.64, ordered exactly |
| P4 | warm and random differ by < 5 points | **REFUTED at 10.05 points**, by 0.05 over its own clause. Proximity pays |
| P5 | cross-regime ≥ 10 points below same-regime | **HELD, hard** — 26 points below, and negative |
| P6 | warm and cold land at the same optimum | **HELD** at every threshold, with a named ~2% tail |
| P7 | wall-clock saving 0.5–1.0× the iteration saving | **REFUTED on its band** — measured −1.19%, indistinguishable from zero. Direction held, magnitude did not |
| P8 | the spiral is defensive | **HELD** — the OK filter changed the source at 0.000 of cells. Its metric was **mis-specified before the run and corrected in the open**: "steps beyond radius 0" is true by construction |
| P9 | the saving is within 10 points at `N = 384` | *see below* |

## What 2c becomes

**This verdict retires one of pass 1's five jobs. It does not retire pass 1.** §11.1 lists the
coarse subsample as serving the warm-start source, the calibration-tile RSS measurement, the
early-abort evaluation, the **cold** reference for the hysteresis audit, and the default
`/detail/` subsample. **Only the first is decided here.** Whether the remaining four justify pass
1 on their own — and whether §11.4's claim that pass 1 doubles as the calibration tile survives,
which 2b already flagged as questionable — **is the next scope question and is separate from this
verdict.**

**And the hysteresis audit's subject goes with the mechanism.** §11.2 exists because
warm-starting biases each point toward its neighbour's answer. With no warm-starting there is no
inter-point coupling to audit, and cold is what ships. The audit's *machinery* — the four
disagreement metrics, the stratified subsample, the per-term reporting — is not wasted thinking,
but it has no subject in 2c.

## What is NOT established

Stated plainly rather than generalized:

- **One machine.** The mini PC, `threadpool_limits(1)`, one BLAS.
- **Two record lengths**, `N = 96` and `N = 384`, both short of production's `N = 630`.
- **One candidate set**, three candidates, deliberately lint-clean. A set with exchangeable
  same-kind terms was excluded by construction and is not covered.
- **A simulated field.** The parameters vary smoothly by construction and the boundary is sharp
  by construction. **The spatial coherence of real altimetry optima has not been measured**, and
  a field whose optima are more coherent than this one's could give a different answer. That is
  the one measurement that would properly overturn this verdict, and it needs real data.
- **Nothing about the barrier's cost at 10⁷ points**, about label switching, or about pass 1 as
  the calibration tile.
