# THE FIELD BUILDER HAS NO SIGNAL — the defect, dated 2026-09-02

**`src/metamer/bench/fields.py` draws every series as noise alone**, and the config it writes
fits **`constant + trend`**. So every 2d rung so far has fitted a two-parameter signal model to
data whose signal is **identically zero** — on a field built to benchmark a trend-estimation
package, for a design-doc section whose subject is **trend uncertainty**, standing in for
altimetry that has **sea-level rise**.

> **THIS IS A DEFECT IN THE FIELD BUILDER, NOT A RUNG PARAMETER.** It was found while looking for
> a difficulty knob, and the difficulty was the **symptom**. Filed as a defect because the repair
> is owed whatever 2d decides about rungs.

## The measurement that localised it

`build_field` at `values[:, iy, ix] = generator.multivariate_normal(...)` — no mean, no trend.
2c's harness at `rows.append(draw + 2.0 + 0.3 * (t - t.mean()))` — both.

**Two probes, 16 points each, `N = 630`, the shipped `fit` and the shipped candidate set.**

| field | iterations/point | misclassified |
|---|---|---|
| 2c's, as its harness builds it | **43.94** | 0.375 |
| 2c's, **with the signal removed** | **25.69** | 0.250 |
| 2c's, on 2d's time axis | 43.50 | 0.375 |
| 2d's own parameters | **24.69** | 0.000 |
| **2d's own parameters, plus 2c's signal** | **43.50** | **0.062** |

**The signal accounts for 18.25 of the 19.25-iteration gap — 95%.** Everything else 2c differs in
— `white/sigma` 0.35–0.71 against 0.40, `rho` 0.42–1.04 against 0.8, the `sigma` levels, the
within-regime spread — accounts for **1.0 iteration** between them. **The time axis accounts for
0.44.**

**AND THE REPAIR COSTS NOTHING IN SEPARABILITY ON 2d's PARAMETERS: 0.062 misclassified with the
signal, 0.062 without.** 2c's 0.375 is its **noise floor's** doing, not its signal's — which is
why the noise-floor route the difficulty ladder was built for turns out to be unnecessary.

## The signal probe, read against its committed predictions

| # | reading | predicted | measured | verdict |
|---|---|---|---|---|
| S1 | difficulty from the signal alone | **[38, 48]** iterations/point | **43.50** — against 2c's own 43.94 | **HELD** |
| S2 | separability at `white/sigma = 0.40` | **<= 0.25** misclassified | **0.062**, unchanged from 0.062 with no signal | **HELD, and better than predicted** |
| S3 | which half does the work | the trend; the offset little | **the offset does NOTHING** — 43.50 both ways, sd 3.01 both ways | **HELD in its strongest form** |

**S2 IS THE ONE THAT CHANGES THE PLAN.** The signal buys **+18.1 iterations at zero cost in
separability**, so **the noise-floor route the difficulty ladder was built for is unnecessary** —
and 2c's 0.375 misclassification is attributable to its noise floor rather than to its signal,
which the ladder had already implied and this confirms on 2d's own parameters.

## What it retroactively explains — three findings, one cause

1. **The easy rung's null.** Warm equalled cold at all 32 indices at 24.4 cold iterations per
   point. **On a signal-bearing field the same construction sits at 43.5**, which is where 2c
   measured a **42.28% saving** — i.e. where a warm start has something to improve and therefore
   something to bias.
2. **E5's diagonal being invariant.** `parameters = factor × BASE` holds `white/sigma` constant,
   and amplitude is free under a concentrated likelihood (**23.50 against 23.62** under a 2.5×
   rescale). The sweep moved a quantity the fit cannot see — **and the field it moved it on had
   no signal to make any of it matter.**
3. **The difficulty that no noise-floor setting could reach.** The ladder tops out at **32.8** at
   `white/sigma = 1.4`, short of 2c's 40.79, and the missing distance was never in the noise
   floor. **One term explains all three.**

## What it invalidates, stated narrowly

**THE THREE-RUNG NULL STANDS AS A MEASURED RESULT.** It is not withdrawn. **Its scope is
narrowed:** it is a null *on a field with no signal, at 24.4 cold iterations per point*, and
**whether it transfers to a signal-bearing field is exactly what a rung would test.** Every number
in the easy rung's report remains what it was measured to be; what changes is the population it
describes.

**AND CRITERION 17's LADDER IS UNAFFECTED AS A MEASUREMENT** — 24.375 / 24.333 / 24.396 are what
those three fields cost — **while its interpretation moves**: it is the cost of three
signal-free fields, and it is now understood as three samples of one difficulty rather than a
sweep.

## What the builder's new term should be, specified rather than transcribed

**COPYING `2.0 + 0.3 × (t - t̄)` WOULD MAKE 2d's FIELD INHERIT A CONSTANT NOBODY CHOSE**, and a
later reader could not tell a measured choice from a transcription. So:

| | what ships | why |
|---|---|---|
| **which terms** | **A TREND ONLY. NO OFFSET.** | **Measured: the offset does nothing, to every digit.** Trend-only came back at **43.50, sd 3.01**, and trend-plus-offset at **43.50, sd 3.01** — bit-identical. A constant is one column of the design matrix and is absorbed **exactly**; carrying 2c's `2.0` would be transcribing a number that changes no reading |
| **magnitude, in a portable unit** | **the trend's RISE OVER THE RECORD, as a multiple of `sigma`.** Recommended **16 sigma**, which is 2c's own | **A bare coefficient of 0.3 is not portable across record lengths or noise levels** — it is `0.3 x 53.4 yr / sigma 1.0` here and something else at any other `N`. The ladder is linear in it: **0 sigma to 25.38, 8 sigma to 33.62, 16 sigma to 43.50**, about **1.13 iterations per sigma of rise**. 16 lands at 2c's measured difficulty rather than beyond it, which keeps the rung inside the range any saving has been measured at |
| **fixed or per rung** | **RECOMMENDED FIXED — a property of every field, not a rung's lever** | A trend-estimation benchmark carrying no trend is the defect; every field should have one, and the rung's lever stays whatever the rung's lever is. **Recorded as a decision, because it is one** |

> ## THE FIXED-VERSUS-PER-RUNG CHOICE CHANGES THE SCOPE QUESTION, AND BOTH READINGS ARE HERE
>
> **If FIXED:** the three shipped rungs become fields that lacked something **every** field should
> have. That **strengthens the case for re-running them** rather than narrowing their scope — and
> it re-prices 2d, because three re-runs at the signal-bearing rate are **not** three re-runs at
> the old one: **20.65 s/point/arm against 10.89**, so a rung goes from ~10 h to **~13.2 h** and
> three of them to **~40 h**, which does not fit any remaining ceiling.
>
> **If PER RUNG:** the three stand as-is with their scope narrowed to *"signal-free fields"*, one
> new rung carries the signal, and 2d reports a **contrast between two populations** rather than a
> ladder within one. **Cheaper by ~26 h and weaker as evidence**, because the comparison is then
> across two field constructions rather than within one.
>
> **TAKEN 2026-09-03: FIXED, AND THE THREE SHIPPED RUNGS ARE NOT RE-RUN.** Not on the price — on
> comparability: their result is already correct for what it measures, and repeating it on a
> different construction would make it a different measurement wearing the same name. **One rung on
> the corrected builder replaces the three re-runs, and the contrast between the two constructions
> is the finding**, because the difference between them is exactly the term whose absence was the
> defect. **The decision, its constraint on the three rungs' bytes and what 2d then reports are in
> `PROGRESS.md`; this note stays the home of the numbers and does not restate the reasoning.**
