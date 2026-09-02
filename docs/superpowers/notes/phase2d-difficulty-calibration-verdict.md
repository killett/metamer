# The difficulty ladder — the lever works, and it does not reach 2c

**Measured 2026-09-02, `git HEAD = 01a833b`.** Predictions committed first in
[`phase2d-difficulty-calibration-predictions.json`](phase2d-difficulty-calibration-predictions.json);
records in
[`phase2d-difficulty-calibration-measured.jsonl`](phase2d-difficulty-calibration-measured.jsonl).
**16 series per family per setting, `N = 630`, the shipped `fit` and the shipped candidate set,
`sigma` and `rho` held at `BASE` so the ladder moves one quantity.**

| `white/sigma` | family | iterations/point | sd | misclassified | s/point |
|---|---|---|---|---|---|
| **0.4** — the shipped value | matern12 | 25.62 | 1.45 | **0.000** | 14.04 |
| | matern32 | 24.06 | 1.91 | 0.062 | 14.38 |
| **0.7** | matern12 | 27.88 | 1.59 | 0.062 | 20.04 |
| | matern32 | 28.69 | 2.21 | 0.125 | 21.27 |
| **1.0** | matern12 | 30.44 | 2.45 | 0.188 | 23.98 |
| | matern32 | 30.62 | 2.58 | 0.250 | 21.65 |
| **1.4** | matern12 | 33.31 | 5.08 | 0.250 | 24.06 |
| | matern32 | 32.31 | 3.61 | **0.375** | 22.74 |

## The verdict against the committed clauses

**The lever is a lever: iterations rise monotonically, 24.8 → 28.3 → 30.5 → 32.8.** Neither
refutation clause fires — the lower one required `< 30` at the top of the ladder and the upper one
required a setting reaching 35 iterations, which none did.

> **AND THE PREDICTED BAND WAS MISSED LOW: `[35, 60]` against 32.8.** That is not a refutation and
> the predictions file says so in advance — *"a monotone rise that stops short of 40.79 while
> staying separable"* is listed under what would **not** refute anything, with its action already
> chosen. **The band and the refutation clause did not meet, and the gap between them is where this
> landed**; the file covered the gap explicitly, which is the only reason this reads as a result
> rather than as an unclaimed interval.

## What the ladder says about the gap to 2c, which is the part that matters

**2c's hard regime runs at `white/sigma` 0.45–0.71**, which on this ladder is **≈ 28 iterations**.
**2c measured 40.79.** So **the noise floor accounts for roughly 3.5 of the 16.4-iteration gap and
something else accounts for the remaining ~12.** Candidates, from the recovered harness: the
**signal** — 2c's series carry `2.0 + 0.3 × (t - t̄)`, a trend of 15.6 over the record against
`sigma ≈ 1`, and 2d's field carries **none** — the **`rho` range**, the **parameter spread within a
regime**, or the record's structure.

> **SO THE RUNG IS NOT BUILT YET, AND THE NEXT MEASUREMENT IS A PROBE RATHER THAN A RUNG.** A rung
> at `white/sigma = 1.0` would sit at **30.5 iterations — still well below 2c's 40.79** — and a null
> there would leave open whether one appears at 40.79. **The pre-decided stop was written against
> *"difficulty reaches 2c's range"* and would not cleanly apply.** 2c's fixture is **in the tree**;
> probing it directly costs under an hour and either makes the rung unambiguous or shows that 2d's
> builder cannot reach that difficulty at all — which is itself the answer. **(j4): an existing
> measurement is evidence, and approaching a number is more expensive than reading it.**

## The setting the constraints would have chosen, recorded because it is the fallback

**`white/sigma = 1.0`**, and **separability is what rules out 1.4, not cost.**

| | at 1.0 | at 1.4 |
|---|---|---|
| iterations/point | 30.5 | 32.8 |
| baseline misclassification | **0.22** | **0.31**, and 0.375 on matern32 |
| `P(row of 12 exceeds a half)` | `P(Binom(12, 0.25) ≥ 7) ≈ 1.4%` | `P(Binom(12, 0.375) ≥ 7) ≈ 17%` |
| one rung's cost at `6.016 arms × 384 points` | **14.6 h** | 15.0 h |

**1.4 buys 2.3 iterations for roughly a 6× higher chance that the interior null fires and voids a
15-hour rung** — and the null reads **two** seed rows, so the per-rung risk is higher than the
per-row figure. **Cost is not the discriminator here; the second cause of a firing null is.**

> ## AND AT ANY RAISED NOISE FLOOR THE PROFILE IS THE PRIMARY READING, NOT THE WIDTH
>
> **At a baseline of 0.22 a smear must push a row from 0.22 past 0.5 to register as a width at
> all.** Task 2's recorded forfeit — the majority rule is blind to a band that never carries a cell
> past a half — **stops being a caveat and becomes a design constraint the moment the baseline is
> lifted off zero.** The easy rung had a baseline near 0.05 and the same forfeit applied silently;
> here it is quantified. **So the rung's verdict reads the profile first and the width second**, and
> a floor result with a visible band at the boundary is a positive finding rather than a null.

## Two notes on comparability, because both affect how these seconds may be used

**THE QUIET GATE FIRED ON THE FIRST ATTEMPT AND REFUSED TO MEASURE** — load **5.12** against a limit
of 3.0, from this session's own leftover background jobs. **No number was produced and none had to
be discarded.** That is Task 0's fourth defect not repeating: the harness that recorded a loud host
and measured anyway.

**AND THE SECONDS HERE ARE LESS COMPARABLE THAN THE ITERATIONS.** The easy rung was measured at
load **1.38** and this ladder at **2.40**; both pass the gate, both readings travel with their load,
and **iterations are deterministic while seconds are not**. The `s/point` column is used here only
to price a rung, which is what it is for — **a difference of a few percent between these seconds and
the easy rung's is the host, not the fixture.**

## What this does not establish

- **Nothing about hysteresis.** It measures how hard the fit is, not whether a warm start biases it.
- **Nothing about the field.** Independent series, no boundary, no neighbours, no warm starts.
- **No 2d result.** No number here may be quoted as one.
