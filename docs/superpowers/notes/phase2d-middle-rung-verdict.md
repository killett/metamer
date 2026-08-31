# The third rung — criterion 17's third point. PREDICTION CONFIRMED

**Measured 2026-08-31, quiet host, `git HEAD = 64e4514`.** Predictions committed first, in
[`phase2d-middle-rung-predictions.json`](phase2d-middle-rung-predictions.json); the records are in
[`phase2d-middle-rung-measured.jsonl`](phase2d-middle-rung-measured.jsonl). **All three rungs were
run in ONE session and interleaved by the harness**, so nothing here is compared across sessions.

## Reading M — iterations per point at `N = 630`, all three rungs

96 points per rung, a systematic subgrid of every 2nd point, `M = 3`, family-change field,
Cholesky draw, seed `20260830`.

| rung | `ℓ` | `Δ` | **iterations/point** | sd | SE | min–max | cells OK | s/point |
|---|---|---|---|---|---|---|---|---|
| **easy** | 16.0 | 3.0 | **24.375** | 1.630 | 0.166 | 21–28 | 287/288 | 11.20 |
| **middle** | **9.798** | **1.5** | **24.333** | 1.745 | 0.178 | 20–28 | **288/288** | 11.37 |
| **hard** | 6.0 | 0.75 | **24.396** | 1.944 | 0.198 | 19–28 | 287/288 | 11.38 |

**Predicted band `[23.8, 25.0]`. Measured 24.333. CONFIRMED**, and by a wide margin: the middle
rung sits **0.052 below** the shipped pair's common value of 24.385, which is **0.3 standard
errors**. Neither refutation clause fires.

> ## THE ORDERING IS NOT A FINDING AND IS NOT REPORTED AS ONE
>
> The middle rung is numerically the **lowest** of the three, which looks like a non-monotone dip.
> **It is not:** the three means span **0.062 iterations** against standard errors of
> **0.17–0.20**, so every pairwise difference is under a third of one standard error. **The three
> rungs are indistinguishable from one another, which is what was predicted**, and reading an
> ordering out of them would be reading the noise.
>
> **The committed clause was `< 23.8`, not "lowest of the three"**, and that is why it was written
> as a band rather than as an ordering — there was no ordering in the two shipped rungs to extend.
>
> **THE CLAUSE'S FORM ANTICIPATED THIS, AND THAT IS THE PART WORTH RECORDING.** Nothing surprising
> happened here: the prediction was a null and the null held. **The discipline still paid** — had
> the clause been written as *"the middle rung lands between the two"*, this result would have
> **refuted** it, on a 0.062 spread against a 0.18 standard error, and the refutation would have
> been of the prediction's shape rather than of anything about the field. **A prediction committed
> in the wrong form manufactures a finding**, and the only place to get the form right is before
> the run, where there is nothing to fit it to.

**What it means, and it is the difficulty condition rather than the lever.** The three rungs span a
factor of **2.67 in `ℓ`** and **4 in `Δ`** and produce the same iteration count. **On this field
the cold-arm cost is set by the likelihood and the candidate set, not by either lever** — which is
what the two shipped rungs already said and what a third point now says at a setting between them.
**The budget rests on the largest of the three: 24.396, the hard rung, unchanged.**

## The free positive control: the two shipped rungs reproduced BIT-EXACTLY

**Not designed as a control and it is the strongest thing in this run.** The easy and hard rungs
were re-run from scratch — field rebuilt, fits redone — a day after their first measurement, and
came back at **24.375 and 24.395833…**, with **identical** standard deviations, identical minima
and maxima, and identical `cells_ok`. **Every digit.**

That is Task 0's finding confirmed a second time, on a different fixture and across a session
boundary: **iterations are deterministic.** It also means this run's middle-rung number is
comparable to the 2026-08-30 numbers **by demonstration rather than by assumption**, which is
exactly what *"arms interleaved within one session, never compared across sessions"* is normally
needed to buy. **Here the reproduction is the evidence.**

> **AND IT DOUBLES AS THE NULL'S POSITIVE CONTROL.** *"The middle rung costs what the others cost"*
> is byte-identical in the output to *"the rung parameter never reached the field"*. The
> predictions file named the two existing tests as the control; **this run adds a stronger one for
> free** — the builder demonstrably produced three *different* fields, because the middle rung's
> `cells_ok`, spread and minimum all differ from both neighbours' while its mean does not.

## The seconds moved 15% and the iterations did not — AND THE BUDGET RATE DOES NOT MOVE

| | 2026-08-30 | 2026-08-31 | change |
|---|---|---|---|
| **iterations/point, easy** | 24.375 | **24.375** | **0.00%** |
| **iterations/point, hard** | 24.395833… | **24.395833…** | **0.00%** |
| **s/point, easy** | 13.15 | **11.20** | **−14.8%** |
| **s/point, hard** | 13.04 | **11.38** | **−12.7%** |

**Same host, same fixture, same code, quiet check passing in both runs.** Task 0 measured this
box's wall clock spreading **11% quiet and 21% loud** on one fixture within a session; **this is
the same instability observed ACROSS sessions at 15%**, and it is now measured rather than assumed
to transfer.

> ## `13.15 s/point/arm` STANDS AS THE BUDGET RATE AND IS NOT LOWERED
>
> **A cheaper reading is not a reason to re-price.** The budget is an **upper bound** and is priced
> at the **larger** of the two readings deliberately; lowering it to 11.2 would buy 2.7 hours of
> apparent headroom out of a quantity this box has now been shown three times not to hold still.
> **19.7 h against the 30 h ceiling is unchanged.**
>
> **What DOES change is the confidence in it**, and in the right direction: the figure the budget
> uses is now known to be at the high end of a measured range rather than a single sample.
> **This is (j8)'s second register behaving as intended** — the rate carries its workload, so the
> two readings are of the same thing and their disagreement is attributable to the host.

## What this reading does not establish

- **Nothing about the saving.** This is the cold-arm iteration count. Whether `ℓ` moves the saving
  is Task 1's reading B and was not re-run.
- **The standing limitation is unchanged and is sharper for this rung than for the others:** every
  number here is measured on a field whose coherence is a construction parameter, and **the middle
  rung's is CHOSEN** — it occupies the slot a plausibility rung would have held and is not a claim
  about the ocean. Any figure quoted from it carries that sentence.
