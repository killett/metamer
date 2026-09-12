# Wiring one — the smoke, both gate branches (2026-09-11)

> **`batch.audit` now reaches a rung report and every number on it carries its rung. Neither run is
> a measurement, criterion 12 stays reduced, and the two predictions that were refuted were both
> refuted in the directions registered as findings rather than as defects.**

**THE PRE-FLIGHT IS [`wiring-one-preflight.md`](wiring-one-preflight.md) AND NOTHING FROM IT IS
RESTATED HERE**, including W1–W12 and the twelve-test plan. The harness is
[`wiring-one-harness.py`](wiring-one-harness.py), the records are
[`wiring-one-measured.jsonl`](wiring-one-measured.jsonl), and the two reports are
`wiring-one-smoke-contaminated-report.json` and `wiring-one-smoke-clean-report.json`.

**NEITHER IS A MEASUREMENT AND BOTH SAY SO IN THEIR OWN BYTES.** `is_a_smoke_run` is `true` in each
instrument block, the geometry is **26 × 2** against the shipped **32 × 12**, and the record length
is **24** against **630**. Task 9's rule refuses a report carrying that flag as evidence for any
criterion. **Neither report is one of `COMMITTED_REPORTS`**, so criterion 12's guard does not fire
and the criterion stays reduced — which is the intended order, not an oversight.

**BOTH BRANCHES OF E6's GATE WERE RUN**, as `phase2d-driver-smoke.md` ran both. A contaminated rung
never computes its widths, so only the clean branch exercises `build_report` with widths **and**
strata; only the contaminated one exercises the decision to keep the strata when the widths are
withheld.

**RE-RUN 2026-09-11 WITH THE ARM ARRAYS ADDED, AND THE SELECTION COUNTS REPRODUCED EXACTLY** — see
[the second run](#the-second-run-2026-09-11--the-arrays-and-a-free-reproduction) below. The sizes in
this table are the FIRST run's and are superseded there; every other figure reproduced.

| | contaminated (seed 20260830) | clean (seed 20260831) |
|---|---|---|
| wall clock | 531 s | 443 s |
| `contaminated` | **true** | **false** |
| null line | **7.0 cells**, not at floor | **at floor**, `cells = None` |
| smear widths | all withheld | cold 4.0 · warm 4.0 · n2 7.0 |
| populated point strata | 3 of 9 | 5 of 9 |
| differing / move / dropout | **4 / 4 / 0** | **1 / 1 / 0** |
| populated `κ` bins | `< 2²⁶` and **`undefined`** | `< 2²⁶` and **`undefined`** |

## The wiring, which is what this establishes and all it establishes

Every line joining the audit to the rung report runs here or nowhere: `run_rung` is excluded from
`pixi run test` (E7), so no unit test executes in the process that writes a report.

| fact | both branches |
|---|---|
| the section is at the TOP LEVEL under the key `strata` | **true** |
| every quantity the report can reach is a `RungQuantity` carrying its rung | **true**, 104 of 104 |
| `move + dropout + both_unavailable == differing`, in **every** stratum | **true** |
| the strata's seed is the one the instrument block names | **true** |
| the floor is the shipped `MIN_STRATUM_MEMBERS` | **true**, 30 |
| the identifiability lint RAN rather than being skipped | **true**, no candidate flagged |
| the two upper `κ` bins are named unreachable | **true** |
| the decomposition's positive control ran BEFORE the host gate | **true**, first record in the file |

## A free control nobody planned, on a path this change does not touch

**THE NULL CAME BACK AT 7.0 CELLS, WHICH IS THE EASY-RUNG HARNESS'S OWN SMOKE READING AT THE SAME
SEED**, recorded before any of this existed. The null is read off the warm **selection map** and the
strata are a different measurement over the same arms, so an unchanged reading is evidence the
wiring moved nothing it was not meant to. The clean seed reproduces the committed clean smoke's
branch in the same way: at floor, `cells = None`.

## P1 REFUTED UPWARD: `kappa_undefined` IS POPULATED, ON BOTH SEEDS

**The pre-flight predicted exactly one populated `κ` bin and named this as the refutation that would
be a finding rather than a defect** — the `undefined` bin is reachable because the taxonomy
thresholds `cond` and never tests positive definiteness. It is populated on both seeds: 12–24 live
cells per candidate, against 2c's criterion 11 recording it "empty in fact" on **8 live cells**.

**(h3) IS UNTOUCHED AND THAT IS THE HALF THAT MATTERS.** The two *upper* bins stay unreachable,
because `HESSIAN_COND_LIMIT` **is** the first boundary. What is refuted is the pre-flight's own
stronger claim in W3 that the axis is **degenerate** on this population. It is not, and it is
separating something: the `max_parameter_distance_se` headline comes from a `kappa_undefined`
stratum on **both** branches — 350.0 against 8.02 in the well-conditioned bin on one, 193.4 against
its own well-conditioned figure on the other.

> **IT IS NOT ACTED ON, AND THE REASON IS THE FIXTURE.** At `n_time = 24` almost nothing is well
> determined and a Hessian that is not positive definite is cheap to produce, so this may be a
> property of a 24-epoch record rather than of the field. **A smoke run cannot be evidence for a
> criterion and this is not offered as any.** 2c's criterion 11 is NOT amended. What is recorded is
> that **the first real run must check whether `undefined` is populated at production record
> length**, because if it is, the `κ` axis has two live bins and W3's framing needs correcting in
> the design record rather than only here.

## P3 REFUTED: EVERY DIFFERENCE IS A MOVE, WHICH IS THE OPPOSITE OF REAL ALTIMETRY

The pre-flight predicted dropouts would outnumber moves. **Five differing points across two seeds,
five moves, zero dropouts** — against the real-data box's zero moves in 289 points, where every
difference was a dropout.

**THAT CONTRAST IS THE ARGUMENT FOR THE DECOMPOSITION, ARRIVING AS A MEASUREMENT RATHER THAN AS A
PREDICTION.** The pooled selection-disagreement rate is the same quantity in both places and it
decomposes the opposite way in each. A report carrying the pooled rate alone would have described
these two populations identically. **It also means the `move` branch is not dead code**: the rule
reported moves on real fits, not only on the fabricated control.

**Both numbers are tiny and neither transfers.** One differing point of 52 is not a rate.

## P4 HELD, AND IT VALIDATED THE SHAPE OF THE OUTPUT

**ON THE CLEAN BRANCH EVERY POINT STRATUM IS BELOW THE FLOOR** — the largest holds 22 members — so
all three selection headlines are **withheld** and there is no quotable selection number at all.
The counts are what is reported instead, which is exactly why the decomposition's counts are plain
integers beside the `Quantity` objects rather than being `Quantity` objects themselves.

**THIS IS THE SCOPE CALL'S OWN ARGUMENT, MEASURED.** 52 points across 9 strata produce nothing
quotable. A 10.18 h rung re-run would put 384 points across the same 9 strata with a differing
population of the same order, and would have bought a report whose selection strata were still
withheld.

## P5 HELD

`both_ok_fraction` is below 1.0 on two candidates in each branch — 0.923 / 0.962 and 0.942 / 0.981 —
so the survival-conditioning note fires, which is the surface W3 relocates the start-dependence
check to. **The per-arm `DEGENERATE_HESSIAN` counts do not move in one direction**: warm exceeds
cold on one candidate and cold exceeds warm on another. Consistent with open question 23 being
unexplained, and not evidence about it either way at this size.

## What these two runs do NOT establish

- **No magnitude here transfers to the shipped geometry.** 26 × 2 at `n_time = 24`.
- **They close no criterion.** Criterion 12 stays reduced with its closer changed to a population
  that has a live differing set.
- **They say nothing about open question 23**, whose subject is a population an order of magnitude
  larger than anything here.
- ~~**They are not a reproducibility check.** The two branches use different seeds, so neither is a
  repeat of the other.~~ **SUPERSEDED 2026-09-11 BY THE SECOND RUN**, which re-ran both seeds in a
  separate invocation and returned the selection counts to the integer. The argument — that the
  strata read the `COLD` and `WARM` arms only, so no N2 direction enters them — is now a
  measurement as well as an argument. **The line is struck rather than deleted**, because what it
  says about the two BRANCHES is still true: they are different seeds and neither is a repeat of
  the other.


---

## THE SECOND RUN, 2026-09-11 — THE ARRAYS, AND A FREE REPRODUCTION

**THE SAME TWO SEEDS, THE SAME GEOMETRY, A SEPARATE INVOCATION, WITH `arm_arrays` ADDED.** What it
establishes beyond the arrays themselves:

- **THE SELECTION COUNTS REPRODUCED EXACTLY** — `differing / move / dropout` came back **4 / 4 / 0**
  and **1 / 1 / 0**, the first run's figures to the integer. **The first run was explicitly NOT a
  reproducibility check** and said so; this one is, and it is free. The strata read the `COLD` and
  `WARM` arms only and no N2 direction enters them, which was the *argument* for putting them
  inside `reproducible()`; this is the measurement.
- **THE DECOMPOSITION ROUND-TRIPS THROUGH THE FILE, ON BOTH BRANCHES.** The report is written to
  disk, **re-read from disk**, and fed back through the shipped `selection_decomposition` via
  `decomposition_from_record`; the per-stratum counts match the ones computed in memory from
  `FitResult` objects — 3 populated strata on one branch, 5 on the other. **The unit tests prove
  the rule; this proves the file**, and the harness refuses rather than reports if it fails.
- **ALL FIVE ARMS ARE IN THE ARTIFACT** — `cold`, `warm`, `n1`, `n2`, `self`. The ceiling arm is
  there because `SelfArm` was changed to keep its `FitResult`; until 2026-09-11 it dropped it, and
  an artifact built to answer open question 23 would have carried every arm but the one with **133
  degenerate cells against cold's 79**.
- **`κ` IS `null` ON 21.4% OF CELLS**, which is the `kappa_undefined` population arriving in the
  file rather than in a bin count — and the reason the absence is `null` and never `0.0`, which
  is the most well-conditioned value there is.

### The size, measured, and the prediction it refutes

| | contaminated | clean |
|---|---|---|
| whole report on disk | **89 970 B** | **93 332 B** |
| of which `arm_arrays` (indented) | 42 784 B* | **42 784 B** |
| `arm_arrays` compact | — | **14 544 B** |

\* indented figure measured on the clean branch; the two differ only in their null counts.

**THE PRE-FLIGHT'S 142 KB WAS WRONG TWICE AND THE CORRECTION IS AT ITS OWN S4**, not restated here.
The short form: the estimate was compact JSON at 384 points, the artifact is `indent=2` at 52.
**Scaled to the shipped 384 points the arrays are 107 KB compact and 316 KB indented.**

> **THE AFFORDABILITY HALF OF THE `κ` ARGUMENT MOVED BY 2.2× AND THE STRUCTURAL HALF DID NOT.**
> That is the payoff of recording *a store is one arm* as the reason and the byte count as a second
> fact: the number that moved was the one that was not load-bearing. Had cost been the recorded
> reason, this measurement would have reopened a settled decision.
