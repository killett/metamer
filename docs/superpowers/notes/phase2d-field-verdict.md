# 2d plan Task 1 — the field's iteration count and the `ℓ` lever: verdict

**Run 2026-08-30 at head `e259e1e`, on a quiet host — load 0.76 against a limit of 3, stall
0.0 ms/s. Predictions committed first at the same head**, in
[`phase2d-field-predictions.json`](phase2d-field-predictions.json); measurements in
[`phase2d-field-measured.jsonl`](phase2d-field-measured.jsonl).

> ## BOTH READINGS ARE REFUTED FROM BELOW, AND THEY ARE THE SAME FINDING
>
> **THE BENCHMARK FIELD IS TOO EASY.** It converges in **14 iterations per point** where the two
> fixtures the budget was priced against took **25.3** and **40.4** — and at that cost there is
> almost nothing for a warm start to save, so **`ℓ` cannot express itself and the sweep's primary
> lever is untestable on this field.**
>
> **The lever is not shown to be a label. It is shown to have no room to act.** Those are
> different findings with different repairs, and the measurement cannot yet separate them.

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
