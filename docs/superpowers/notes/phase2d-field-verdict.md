# 2d plan Task 1 — the field's iteration count and the `ℓ` lever: verdict

**Run 2026-08-30 at head `e259e1e`, on a quiet host — load 0.76 against a limit of 3, stall
0.0 ms/s. Predictions committed first at the same head**, in
[`phase2d-field-predictions.json`](phase2d-field-predictions.json); measurements in
[`phase2d-field-measured.jsonl`](phase2d-field-measured.jsonl).

> ## BOTH READINGS ARE REFUTED FROM BELOW, AND THEY ARE THE SAME FINDING
>
> ~~**THE BENCHMARK FIELD IS TOO EASY.**~~ **THE COLD START IS TOO GOOD** — the subject is
> renamed in the addendum below, 2026-08-30, and the rename is the useful part: *"too easy"*
> points at the field's coherence, and the actual constraint is the **likelihood**. **The saving
> is bounded above by what the cold start leaves on the table**, so no amount of coherence in the
> truth can produce one here. **The struck version is kept because the repair was proposed under
> it and the reasoning has to stay legible.**
>
> The field converges in **14 iterations per point** where the two fixtures the budget was priced
> against took **25.3** and **40.4** — and at that cost there is almost nothing for a warm start
> to save, so **`ℓ` cannot express itself and the sweep's primary lever is untestable here.**
>
> **The lever is not shown to be a label. It is shown to have no room to act.** Those are
> different findings with different repairs. **The addendum's recovery of 2c's own cold iteration
> counts separates them**, and it needed no new run.

---

## Reading A — iterations per point. REFUTED FROM BELOW

96 points per rung, a systematic subgrid of every 2nd point, `N = 630`, `M = 2`.

| rung | `ℓ` | `Δ` | iterations/point | sd | min–max | cells OK | s/point |
|---|---|---|---|---|---|---|---|
| **easy** | 16.0 | 3.0 | **14.31** | 1.34 | 11–18 | 191/192 | 5.62 |
| **hard** | 6.0 | 0.75 | **13.98** | 1.23 | 11–17 | 192/192 | 5.61 |

**Predicted band `[25.3, 40.4]`. Measured 14.3 and 14.0 — below both, and the two rungs are
indistinguishable from each other.**

The committed clause reads: *"the field is EASIER than a plain smooth batch despite carrying more
structure. The budget is comfortable, and the same fact raises the concern the slow test
`test_both_candidates_win_somewhere_on_the_field` exists for: a field that converges instantly may
not be leaving a selection question to answer."* **Both halves fired.**

### The budget, and it stops constraining anything

**The cost model is not used, because a third point refutes it.** Task 0's two-point decomposition
gave `2.43 + 0.324 × iterations`, which predicts **7.06 s/point** here; the field **measured
5.62**. Three points now exist and the slope is not constant:

| point | iterations/point | s/point | slope to the next |
|---|---|---|---|
| `self` arm, Task 0 | 1.19 | 2.81 | **0.214** |
| **2d field, easy rung** | 14.31 | 5.62 | **0.455** |
| cold arm, Task 0 | 25.31 | 10.62 | — |

**The slope more than doubles, so the relation is not a line** — which is exactly what (a4)'s
register says two points cannot tell you, and why D2's lever needed three fixtures. **The two-point
model is retired rather than corrected**, and the budget uses the **directly measured** seconds per
point on the field it will actually run.

At **5.62 s/point/arm**, and the geometry's 384 points:

| shape | factor | budget |
|---|---|---|
| **two rungs**, N1 at both | 12.032 | **7.2 h** |
| **three rungs**, N1 at two | 14.047 | **8.4 h** |

**Against a 30 h ceiling, both are trivial and the difference between them is 1.2 hours.** **The
budget no longer constrains the two-rungs-versus-three choice at all** — it is now a question of
epistemic merit alone, which is the cleanest form that decision could have taken.

**The pre-decided cut does not fire.** It was written for a rate near 21 s/point; the field is at
5.62.

---

## Reading B — the `ℓ` lever's sign. REFUTED FROM BELOW

Two fields differing in `ℓ` **only**, contrast held at the easy rung's value, `N = 96`, through
the shipped `run` and `run_two_pass`.

| arm | `ℓ` | cold iterations | warm iterations | saving | warm-started cells |
|---|---|---|---|---|---|
| **long** | 16.0 | 6294 | 6330 | **−0.57%** | 768 |
| **short** | 6.0 | 6347 | 6315 | **+0.50%** | 768 |

**`saving(long ℓ) = −0.57% < saving(short ℓ) = +0.50%`. The ordering is BACKWARDS**, and the
committed clause fires: *"THE LEVER IS A LABEL. E6's first prediction — the saving rises
monotonically with `ℓ` — is dead before the sweep runs, and Task 1's rung design has to change
rather than the sweep's."*

**THE VOID CLAUSE DID NOT FIRE AND THAT MATTERS.** All **768 cells** were warm-started on both
fields, so the mechanism ran end to end — this is not (a2c), the warm starts computed and not
used. **The mechanism worked and had nothing to do.**

### The two readings are one finding, and the magnitudes say so

**Both savings are within half a percent of zero**, against **+7.80%** measured by 2c's spike at
the same record length on its own coherent field. **This field produces essentially no warm-start
saving at all.**

> **AT 16.4 COLD ITERATIONS PER POINT THERE IS ALMOST NOTHING TO SAVE.** A warm start that skips
> one or two iterations out of sixteen is a sub-percent effect, and the sign of a sub-percent
> effect is not a lever's ordering — it is whatever the two fields happen to do. **So reading B
> did not test `ℓ`; it tested a field that had no room to answer.**

**THE HONEST STATEMENT OF WHAT IS REFUTED.** Not *"coherence does not drive the saving"* — 2c
already measured that it does, across three record lengths, with a ceiling arm to locate it.
**What is refuted is that THIS field can show it.**

---

## The likely cause, stated as a hypothesis with what would test it

**2c's field changed FAMILY across its boundary; this one changes MAGNITUDE.** The spike's regions
were *"Matérn ν=3/2 plus white"* against *"Matérn ν=1/2 plus white"* — *"a change of family, not
merely of scale"*, in its own words — over a **three**-candidate set including `matern32`, the
member 2c called the stiffest and where all eleven of its large-`|Δℓ|` disagreements landed.

**This field is `matern12 + white` everywhere**, with a multiplicative jump in the parameters, over
a **two**-candidate set. A magnitude change inside one family is a much easier likelihood, and the
moment-init ladder start — which is data-driven — already lands close to the optimum. **A cold
start that is already good leaves a warm start nothing to improve, regardless of how coherent the
optima are.**

**This is a hypothesis and the measurement does not establish it.** What would: rebuild the field
with a **family change** across the boundary and re-run reading B. If the saving appears and orders
with `ℓ`, the diagnosis holds; if it does not, the problem is elsewhere and the sweep's premise is
in real trouble.

**AND THE REPAIR IS NOT TASK 1's TO TAKE ALONE**, because it moves three things at once:

1. **`M` changes from 2 to 3** if `matern32` joins the candidate set — which moves **the price**
   *and* **D9's stratum count** (`3 × M` point strata, `M × 4` cell strata), and `M = 2` is what
   every figure in the budget and the occupancy arithmetic assumes.
2. **The step becomes a change of family**, which is still a step — E3 survives — but
   `Rung.contrast` currently scales a magnitude. **A family change has no natural multiple**, so
   `Δ`'s definition as *"a multiple of the within-regime range"* would need re-deriving or the
   second lever loses its unit again.
3. **`PRIMARY` names one parameter for the smear width to be a width OF.** Across a family change
   the parameter that steps is not the same parameter on both sides, so the smear estimator's
   subject has to be re-chosen — plausibly the **selected candidate** rather than a parameter,
   which is §11.2's own most-interpretable metric.

---

## Verdicts against the committed clauses

| reading | clause | outcome |
|---|---|---|
| A | band `[25.3, 40.4]` iterations/point | **REFUTED FROM BELOW** — 14.31 and 13.98 |
| A | above 55 → budget crosses 30 h, cut fires | **did not fire.** Budget is 7.2–8.4 h |
| A | budget uses the larger rung | applied: `easy` at 14.31, and the two are within 2% |
| B | `saving(long ℓ) > saving(short ℓ)` | **REFUTED FROM BELOW** — −0.57% against +0.50% |
| B | `saving(long ℓ) ≥ 94.53%` self ceiling | did not fire; nowhere near |
| B | void if zero warm-started cells | **did not fire — 768 of 768 on both.** The mechanism ran |

**Nothing in `src` is shown to be wrong.** The builder does what its tests say: the step is a step,
the null line is clean, `ℓ` orders the truth's autocorrelation, the rungs differ, the field opens
through the shipped path. **What is wrong is that a field whose TRUTH is coherent does not, at
these settings, produce OPTIMA whose coherence the mechanism can exploit** — which is (i2b)'s
finding arriving from the other direction, on a field we built rather than one we measured.

---

# ADDENDUM, 2026-08-30 — the subject was misnamed, and 2c's own data settles it

## THE FIELD IS NOT TOO EASY. THE COLD START IS TOO GOOD

**"Too easy" names the wrong subject.** At 16.4 cold iterations per point the moment-init ladder
is already landing close enough that a warm start has nothing to improve. **That is a property of
the LIKELIHOOD, not of the field's coherence** — and it means **no amount of coherence in the
truth can produce a saving here, because the saving is bounded above by what the cold start leaves
on the table.**

**The repair is therefore right for a different reason than the one it was proposed under.** A
family change is the right repair because it makes the **likelihood harder**, not because it makes
the truth less smooth.

## 2c's FIELD'S COLD ITERATION COUNT, RECOVERED FROM ITS OWN JSONL — THE GAP IS THE DIAGNOSIS

**Recomputed from `warmstart-spike{,-n384,-n630}-measured.jsonl`, cold arm, OK cells only.** No
re-run was needed; the numbers were already in the tree.

| field | `N` | cold iterations **per point** | **per cell** | candidates |
|---|---|---|---|---|
| 2c's | 96 | **28.27** ± 5.70 | 9.49 | 3 |
| 2c's | 384 | **35.32** ± 2.94 | 11.77 | 3 |
| 2c's | 630 | **40.79** ± 3.73 | 13.60 | 3 |
| **2d's** | **630** | **14.31** ± 1.34 | **7.16** | **2** |

**2.85× harder per point; 1.90× harder per cell.** The per-point gap is larger because of the
third candidate, so **the repair's two legs are separately supported**: `M = 2 → 3` buys roughly
the 1.5×, and a harder per-cell likelihood buys the rest.

> **AND THE SHARPEST FORM OF IT: 2d's FIELD AT PRODUCTION LENGTH IS EASIER THAN 2c's FIELD AT ITS
> SHORTEST.** 14.31 against 28.27 — and at 28.27, **2c's saving was only +7.80%.** A saving of
> ≈0% on 2d's field is not an anomaly; **it is what 2c's own curve predicts.**

## AND THE SAME DATA GENERALIZES THE STANDING LIMITATION IN A DIRECTION NOBODY HAS STATED

2c's record-length lever moved coherence **and** cold-start difficulty together. Its own arms
separate them, and the separation was never read this way:

| cold iterations/point | `warm` saving | **`random` saving** |
|---|---|---|
| 28.27 (`N = 96`) | +7.80% | **−2.25%** |
| 35.32 (`N = 384`) | +31.73% | **+18.27%** |
| 40.79 (`N = 630`) | +42.28% | **+30.28%** |
| **14.31 (2d's field)** | **≈ 0%** | — |

**`random` starts from a DISTANT converged optimum and carries no proximity information at all.**
It gains **30.28 points** at `N = 630`. So of the headline **42.28%**, roughly **72% is
attributable to starting at a converged optimum rather than at the moment ladder**, and only the
**12.00 points** 2c already recorded come from the neighbour being near.

> ## THE CONSEQUENCE FOR D1, STATED PLAINLY
>
> **If production altimetry's cold fits converge in ~15 iterations, warm-starting buys little
> there REGARDLESS of spatial coherence** — and 2c's 42.28% would then be largely a statement
> about how poor the moment-init start is on **that fixture at that record length**, rather than
> about the ocean's spatial coherence.
>
> **This is a sharper form of "the real-data spike is the closer".** The spike must measure **two**
> things, not one: the coherence of real optima **and the cold iteration count of real fits.** The
> second is cheaper, needs no warm start at all, and **bounds the saving before any coherence
> question is asked.** Recorded as a requirement on that spike.

---

# THE REBUILD'S THREE OUTCOMES, PRE-DECIDED BEFORE THE RE-RUN (2026-08-30)

**Two branches were obvious and the third is the awkward one, so it is named before the number
arrives rather than after.**

| outcome | reading | what 2d does |
|---|---|---|
| **iterations rise AND the saving appears, ordered by `ℓ`** | the diagnosis holds: difficulty was the constraint | proceed. Reading B's clause is satisfied and the sweep has a field that can answer |
| **iterations stay near 14** | the family change is not what makes a likelihood hard | **NOT another rebuild.** It would mean the moment-init start is simply good on any well-posed field of this shape, and 2d cannot construct one that shows the effect — a finding about warm-starting, not about the builder |
| **iterations rise to 2c's range AND the saving stays near zero** | **difficulty is NECESSARY AND NOT SUFFICIENT** | **report it and stop rebuilding.** Something else about 2c's field — its coherence, its boundary placement, its three candidates in a different arrangement — carries the effect, and 2d reports that a field can be made as hard as 2c's without showing the lever |

> **THE THIRD IS PRE-DECIDED BECAUSE IT IS WHERE THE TEMPTATION TO REBUILD AGAIN IS STRONGEST.**
> It neither confirms nor kills the hypothesis, and a third build would be chosen with the
> answer in view. **It is recorded against D1**, and it is a more interesting finding than a
> successful third build: it would say the 42.28% needs something 2d has not identified, on a
> mechanism whose production value already rests on a reattributed number.

---

# THE REBUILT FIELD'S NUMBERS (2026-08-30, family change, `M = 3`, Cholesky draw)

**Quiet host — load 2.88 against a limit of 3, stall 5.0e-05 ms/s. The gate passed but not
comfortably**, so the wall-clock figures carry that; **the iteration counts do not, being
deterministic.**

## Reading A — iterations per point. STILL REFUTED FROM BELOW, BUT AT THE EDGE

| rung | `ℓ` | `Δ` | iterations/point | sd | min–max | per cell | cells OK | s/point |
|---|---|---|---|---|---|---|---|---|
| **easy** | 16.0 | 3.0 | **24.38** | 1.63 | 21–28 | 8.12 | 287/288 | 13.15 |
| **hard** | 6.0 | 0.75 | **24.40** | 1.94 | 19–28 | 8.13 | 287/288 | 13.04 |

**Against the committed band `[25.3, 40.4]`: 24.4 is below it by 0.9 iterations — 3.6%.** The
clause fires **from below and only just**, and it is reported that way rather than rounded into
the band. **The field is now level with Task 0's smooth batch (25.31) and still well under 2c's
40.79.**

| | `M = 2`, magnitude step | **`M = 3`, family change** |
|---|---|---|
| iterations/point | 14.31 | **24.38** — **1.70×** |
| per cell | 7.16 | **8.12** |

**Most of the gain is the third candidate and some is the stiffer family**, exactly as the
decomposition predicted.

## Reading B — the `ℓ` lever's sign. **CONFIRMED**

| arm | `ℓ` | cold iterations | warm iterations | **saving** | warm-started cells |
|---|---|---|---|---|---|
| **long** | 16.0 | 10245 | 9850 | **+3.86%** | 1152 |
| **short** | 6.0 | 10298 | 10030 | **+2.60%** | 1152 |

**`saving(long ℓ) = +3.86% > saving(short ℓ) = +2.60%`, both positive, both far below the 94.53%
`self` ceiling, and 1152 of 1152 cells warm-started on both fields.** Every clause on this
reading is satisfied and none of the three void or refutation branches fired.

> **THE DIAGNOSIS HOLDS, AND IT WAS THE LIKELIHOOD RATHER THAN THE COHERENCE.** The same builder,
> the same `ℓ` values and the same contrast produced **−0.57% against +0.50%** before the family
> change and **+3.86% against +2.60%** after. **What changed was how hard the cold fit is** —
> nothing about the truth's smoothness moved.
>
> **AND THE FIELD IS NOW COMPARABLE TO 2c's WHERE IT MATTERS.** At `N = 96` this field's cold arm
> runs at **26.7 iterations per point** against 2c's **28.27**, and shows **+3.86%** against 2c's
> **+7.80%** — the same regime, about half the saving.

## Outcome, against the branches pre-decided before the run

**Outcome 1: iterations rose AND the saving appeared, ordered by `ℓ`.** Neither the
stay-near-14 branch nor the awkward third branch applies. **2d proceeds, and it does not rebuild
again.**

## The budget, re-derived on the field that will actually run

**Directly measured, never modelled** — the cost model stayed retired.

| shape | factor | s/point | budget |
|---|---|---|---|
| **two rungs**, N1 at both | 12.032 | 13.15 | **16.9 h** |
| **three rungs**, N1 at two | 14.047 | 13.15 | **19.7 h** |

Using the **larger** rung's rate, as committed. **Both clear the 30 h ceiling; the difference is
2.8 hours.** The pre-decided N1 cut does not fire.
