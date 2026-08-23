# The warm-start spike — verdict

**2c Task 0. Written 2026-08-23.** The pre-flight is in
[`phase2c-preflight.md`](phase2c-preflight.md); the predictions were committed before any arm
ran, in [`warmstart-spike-predictions.json`](warmstart-spike-predictions.json); the instrument is
[`warmstart-spike-harness.py`](warmstart-spike-harness.py) and the points are
[`warmstart-spike-measured.jsonl`](warmstart-spike-measured.jsonl) and
[`warmstart-spike-n384-measured.jsonl`](warmstart-spike-n384-measured.jsonl).

> ## THERE IS NO VERDICT YET, AND P9 IS WHY. THE SAVING IS **7.80% ± 0.77%** AT `N = 96` AND **31.73% ± 0.99%** AT `N = 384` — IT MOVED **23.93 POINTS** AND CROSSED §11.2's THRESHOLD. BY THE RULE WRITTEN DOWN BEFORE THE SECOND FIXTURE REPORTED, **THE PRIMARY FIXTURE DOES NOT DESCRIBE PRODUCTION AND THE VERDICT IS RE-TAKEN AT `N = 630`.**

**THE PROVISIONAL "DROP IT" IS SUSPENDED, NOT CONFIRMED AND NOT REVERSED.** Everything below
about the primary fixture stands as a measurement at `N = 96`; what does **not** stand is reading
it as a statement about production. **The saving is strongly increasing in record length**, and
production is longer than either fixture measured.

> **AND THE CEILING STILL GOVERNS HOW ANY OF IT IS QUOTED.** Starting each point from **its own**
> converged `θ̂` saves **93.97% ± 0.16%** of iterations at `N = 96` and **93.49% ± 0.18%** at
> `N = 384` — flat in `N`. **The ceiling does not move and the neighbour's saving does**, so what
> changes with record length is **how good a neighbour is**, not what the machinery can deliver.
> That is a statement about the field, and it is the reason the ceiling arm was worth its cost.

## The decision rule for P9, stated before the N = 384 fixture reported — and what it now compels

Recorded in advance so the second fixture cannot be read to suit the first.

| P9 lands | what it means | the verdict |
|---|---|---|
| **at or above 30%** | the saving depends on record length, and the primary fixture at `N = 96` does **not** describe production at `N = 630`. The headline was measured at the wrong length | **the verdict is re-taken**, at production length, before anything rests on it |
| **anywhere below 30%** | the verdict stands | **stands** — and the size of the move is **itself worth stating**, because it tells the next reader which regime the null covers |

**A move of more than 10 points that stays below 30% does not overturn the verdict**; it
narrows the claim to the record lengths measured, and that narrowing is part of the finding
rather than a caveat on it.

**IT LANDED IN THE FIRST ROW. P9 IS REFUTED BY 23.93 POINTS AGAINST A 10-POINT CLAUSE, AND THE
RE-TAKE IS COMPELLED RATHER THAN CHOSEN.** The rule was written to stop the second fixture being
read to suit the first, and it did its job in the direction I did not expect: I predicted the
saving was a property of the parameter space and therefore flat in `N`, and it is not.

## The second fixture, `N = 384` — the one that changed the answer

12 × 12 points, `N = 384` monthly, stride 4, 135 measured points, **0 excluded**, one repeat
(iterations are deterministic, so one repeat answers P9; the wall clock below therefore has **no
error bar** and is a single reading).

| arm | pooled, `N = 96` | pooled, `N = 384` | move |
|---|---|---|---|
| `self` — the ceiling | +93.97% ± 0.16% | **+93.49% ± 0.18%** | **−0.5 points — flat** |
| `warm` — the mechanism | +7.80% ± 0.77% | **+31.73% ± 0.99%** | **+23.9 points** |
| `random` — distant source | −2.25% ± 0.91% | **+18.27% ± 1.03%** | **+20.5 points** |

Per candidate at `N = 384`: `white` **+13.77%**, `m12+white` **+31.07%**, `m32+white`
**+38.15%** — P3's ordering holds and every rung has risen. **Wall clock, single reading:** cold
**1488.09 s**, warm **1073.53 s** — **+27.86%**, where at `N = 96` it was **−1.19%**. `random`
**+20.15%**. `self` **+69.13%**.

**THE CEILING BEING FLAT WHILE THE MECHANISM RISES IS THE INFORMATIVE PART.** If both had risen,
the effect would be about `N` making every warm start cheaper — an instrument story. The ceiling
does not move at all (−0.5 points across a ×4 lever), so what improved is **the neighbour's value
as a source**. At longer records the optimum is better determined relative to the basin it sits
in, and a fit two cells away lands inside it.

**AND THE `N = 96` TAIL IS FIXTURE-SPECIFIC, WHICH CORRECTS THIS DOCUMENT'S OWN EARLIER
READING.** At `N = 384` warm and cold agree at **100.00%** on selection, **100.00%** at
`|Δℓ| < 0.01` with a **maximum of 8.95e-07**, and **100.00%** within 0.25 SE with a maximum
parameter distance of **0.001**. **There is no tail at all.** The ~2% of cells landing elsewhere
at `N = 96` is a property of that fixture's short records, not of warm-starting — so it is
**evidence about `N = 96`**, and the paragraph below that reads it as part of the case against
the mechanism is **wrong and is struck there**.

**P5's SHAPE SURVIVES AND ITS SIGN DOES NOT.** Cross-regime **+2.92% ± 2.89%** against
same-regime **+34.95% ± 0.82%** — still **32 points** below, so the boundary is still where the
mechanism is worth least, but at `N = 384` it no longer actively harms. **(i2c) stands as a rule
and its worked magnitude is now fixture-dependent**, which is recorded rather than smoothed.

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

**1. THE GEOMETRY IS REAL, AND HOW FAR IT GETS YOU DEPENDS ON RECORD LENGTH.**
A distant converged `θ̂` is **worse than the moment ladder** at `N = 96` (−2.25%); a nearby one is
better (+7.80%). **Proximity is worth 10.05 points there** — the refutation of P4, the horn I
doubted, by 0.05 of a point against its own clause. **At `N = 384` proximity is worth 13.46
points** (31.73 against 18.27), so the geometry's contribution is roughly stable while the
overall level is not. **The two-pass geometry buys something real at both lengths; what changes
is whether the total clears 30%.**

**2. THE REGIME BOUNDARY IS ALWAYS THE WORST STRATUM, AND §11.1 HAS NO POLICY FOR IT.**
At `N = 96`, same-regime **+9.75%** against cross-regime **−16.27%** — a 26-point swing onto the
wrong side of zero. At `N = 384`, **+34.95%** against **+2.92%** — 32 points, and no longer
negative. **The sign is fixture-dependent; the ordering is not, and the gap widens with `N`.** The
mechanism is worth least exactly where spectral shape changes, which is where the scientific
interest is and where §11.2 says hysteresis concentrates. **This matters under a PASSING pooled
number, not only under a failing one:** at 31.73% pooled the boundary stratum sits at 2.92%, so a
design that ships warm-starting ships a mechanism that does nothing at its most interesting
points — and §11.1's two-pass warm start **has no notion of regime boundaries at all.** Promoted
as (i2c); the rule stands and its worked magnitude is now known to move with the fixture.

**3. ~~THE ~2% TAIL IS EVIDENCE FOR THE DECISION~~ — STRUCK 2026-08-23 BY THE SECOND FIXTURE.**
P6 passed at its pre-agreed thresholds on both fixtures, so permitted outcome 3 was never
triggered and that was fixed in advance rather than judged after. **But the tail is a property of
`N = 96`, not of warm-starting.** At `N = 96`: selection agreement 95.00%, `|Δℓ| < 0.01` at
97.90%, max `|Δℓ|` **8.31**, max parameter distance **10.2 SE**. At `N = 384`: **100.00%,
100.00%, max `|Δℓ|` 8.95e-07, max distance 0.001.** **The tail vanishes entirely.** Reading it as
part of the case against the mechanism was wrong, and it is struck here rather than quietly
dropped: **at longer records warm and cold land in the same place, to seven decimal places.**

## The predictions

| # | claim | outcome |
|---|---|---|
| P1 | the ceiling arm collapses iterations by ≥ 70% | **HELD at both fixtures** — +93.97% and +93.49% pooled, ≥ 89.63% on every candidate |
| P2 | pooled saving positive and under 30%, ~18% | **HELD at `N = 96`** (7.80%, low in its 5–30% band) and **REFUTED at `N = 384`** (31.73%). The prediction had no `N` clause, which is the defect P9 caught |
| P3 | saving ordered by parameter count, `white` under 5% | **HELD on ordering at both** — 2.31 / 6.31 / 11.64 and 13.77 / 31.07 / 38.15. **The `white < 5%` clause is REFUTED at `N = 384`** (13.77%) |
| P4 | warm and random differ by < 5 points | **REFUTED at both** — 10.05 points at `N = 96`, by 0.05 over its own clause, and 13.46 at `N = 384`. **Proximity pays, at both lengths** |
| P5 | cross-regime ≥ 10 points below same-regime | **HELD at both** — 26 points below and negative at `N = 96`, 32 points below and positive at `N = 384` |
| P6 | warm and cold land at the same optimum | **HELD at both**, and the `N = 96` tail **does not survive**: `N = 384` agrees 100.00% with max `\|Δℓ\|` 8.95e-07 |
| P7 | wall-clock saving 0.5–1.0× the iteration saving | **REFUTED at `N = 96`** (−1.19%, indistinguishable from zero) and **HELD at `N = 384`** (27.86% against 31.73% = 0.88×). The band was right about the mechanism and wrong about the fixture |
| P8 | the spiral is defensive | **HELD at both** — the OK filter changed the source at 0.000 of cells, coarse points 100% OK. Its metric was **mis-specified before the run and corrected in the open**: "steps beyond radius 0" is true by construction |
| P9 | the saving is within 10 points at `N = 384` | **REFUTED BY 23.93 POINTS, AND IT IS THE PREDICTION THAT MATTERED.** Every other number here is conditional on it |

**FIVE OF THE NINE CHANGED THEIR VERDICT BETWEEN THE TWO FIXTURES.** P2, P3's threshold clause,
P6's tail and P7 all read one way at `N = 96` and the other way at `N = 384`. **A single-fixture
spike would have produced a confident, documented, wrong recommendation** — and it would have
been wrong in the expensive direction, because "drop it" is the outcome nobody re-opens.

## What 2c becomes — and this section is now conditional

**NOTHING IS RETIRED YET.** The paragraphs below were written for the "drop it" outcome and are
kept because they are what that outcome would mean; **they take effect only if the `N = 630`
re-take lands under 30%.**

**Under a "drop it" outcome, this retires one of pass 1's five jobs and not pass 1.** §11.1 lists
the coarse subsample as serving the warm-start source, the calibration-tile RSS measurement, the
early-abort evaluation, the **cold** reference for the hysteresis audit, and the default
`/detail/` subsample. **Only the first would be decided.** Whether the remaining four justify pass
1 on their own — and whether §11.4's claim that pass 1 doubles as the calibration tile survives,
which 2b already flagged as questionable — **is the next scope question either way, and is
separate from this verdict.**

**And under "drop it" the hysteresis audit's subject goes with the mechanism.** §11.2 exists
because warm-starting biases each point toward its neighbour's answer; with no warm-starting
there is no inter-point coupling to audit, and cold is what ships.

**UNDER A "BUILD IT" OUTCOME, THREE THINGS ARE ALREADY OWED AND ARE WRITTEN DOWN HERE SO THEY ARE
NOT REDISCOVERED.** `fit`'s `x0` is **call-level all-or-nothing** (`fit.py:227`), so §11.3's
spiral fallback needs a **per-cell warm-start selector** that no plan currently owns. The **regime
boundary has no policy** and is the stratum where the mechanism is worth least at both fixtures.
And the **hysteresis audit becomes mandatory rather than hypothetical**, with §11.2's four
metrics and its stratification — on a candidate set the lint has cleared, which this spike had by
construction and production will not.

## What is NOT established

Stated plainly rather than generalized:

- **One machine.** The mini PC, `threadpool_limits(1)`, one BLAS.
- **Two record lengths**, `N = 96` and `N = 384`, **both short of production's `N = 630`** — and
  the saving **moves 23.93 points between them**, so this is not a caveat but the reason the
  verdict is held. **No value at `N = 630` may be interpolated, extrapolated or assumed from
  these two points.** Two points determine a line and this project has already recorded, twice,
  what a two-point line is worth: the 240 B/candidate slope through two `M` values had zero
  residual and had never tested linearity at all.
- **Two grid sizes, and they differ between the fixtures** — 16 × 16 at `N = 96` and 12 × 12 at
  `N = 384`. The stride and therefore the source-distance distribution are identical, and the
  same-regime strata (+9.75% against +34.95%) move by the same 25 points as the pooled figures,
  so the grid size does not explain the effect. **Recorded because it is a difference the
  comparison did not control.**
- **One repeat at `N = 384`**, so its wall-clock column is a single reading with no error bar.
  The iteration columns are deterministic and need none.
- **One candidate set**, three candidates, deliberately lint-clean. A set with exchangeable
  same-kind terms was excluded by construction and is not covered.
- **A simulated field.** The parameters vary smoothly by construction and the boundary is sharp
  by construction. **The spatial coherence of real altimetry optima has not been measured**, and
  a field whose optima are more coherent than this one's could give a different answer. That is
  the one measurement that would properly overturn this verdict, and it needs real data.
- **Nothing about the barrier's cost at 10⁷ points**, about label switching, or about pass 1 as
  the calibration tile.

## The re-take, and what it costs

**`N = 630`, 12 × 12, stride 4, one repeat.** Same harness, same candidate set, same rule — only
the record length moves, so the three-point series `96 / 384 / 630` is one instrument's reading
of one lever. At `N = 384` the cold arm took **1488 s for 135 points**, so `N = 630` is roughly
**18 s a point**, **~41 minutes an arm**, and **about 3.6 hours** for pass 1, the prep and the
four arms.

**THE THIRD POINT IS THE WHOLE VALUE.** With two points there is no shape and no way to tell a
saturating curve from a rising one — and the difference decides the verdict, because production
sits at 630 and the curve could plausibly have flattened by 384 or still be climbing.

**AND THE DECISION RULE IS THE ONE ALREADY WRITTEN**: at or above 30% at `N = 630`, the mechanism
pays at production length and 2c proceeds to build it with the three owed items above; below
30%, warm-starting is dropped and the record-length dependence is stated as part of the finding.
**No new rule is invented after the number arrives.**
