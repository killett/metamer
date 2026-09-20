# Phase 2f Task 0 — the clustering spike's verdict (2026-09-19)

**Predictions were committed first**, to
[`phase2f-clustering-predictions.json`](phase2f-clustering-predictions.json); readings are in
[`phase2f-clustering-measured.jsonl`](phase2f-clustering-measured.jsonl); the instrument is
[`phase2f-clustering-harness.py`](phase2f-clustering-harness.py) and is **throwaway** — Task 6's
implementation is checked against these numbers as a control.

## The sentence a reader can carry

**The statistic works and is cheap, and the two predictions that failed are the two that mattered:
the seam is not a negligible bias, and the floor cannot be found with the detector I chose.**

| prediction | verdict | reading |
|---|---|---|
| P1 — cost | **MET** | 0.057 s / 0.922 s / 23.50 s at 64² / 256² / 1024², quiet host |
| P2 — negative control | **MET** | rejection 0.045 at α = 0.05, p-median 0.499, 200/200 evaluated |
| P3 — positive control | **MET** | rejection 1.000, **all 200 replicates at the p-floor**, same failure count as P2 |
| P4 — the seam | **REFUTED, high side** | z difference **11.02** at W = 360 against a predicted **< 0.25** |
| P5 — the floor | **REFUTED — the detector was wrong** | rejection rate stays in band at every size; p-median marches 0.476 → 1.000 |
| P6 — zero edges | **MET** | unavailable, naming zero edges; no number returned; fixture precondition holds |
| reproducibility | **MET** | three identical z under one seed; a second seed 0.053 away against a null SD of 8.70 |
| the committed-number control | **MET** | 809 / 91 / 900, exact, no tolerance |

---

## P1 — cost: 2f does not need open question 22's repair

| grid | cells | edges | seconds | predicted |
|---|---|---|---|---|
| 64² | 4,096 | 3,973 | **0.057** | < 1 |
| 256² | 65,536 | 63,902 | **0.922** | < 10 |
| 1024² | 1,048,576 | 1,026,297 | **23.50** | < 120 |

Quiet gate passed (load1 = 0.367) and the low-side refutation clause did not fire: the graph is
non-empty at every size, so this is not a fast wrong answer.

**THE LADDER IS NOT LINEAR IN EDGES, AND THE EXTRAPOLATION IS A FLOOR RATHER THAN AN ESTIMATE.**
64² → 256² is 16× the points and **16.2×** the time — linear. 256² → 1024² is 16× the points and
**25.5×** the time — **1.6× superlinear**, which reads as the working set leaving cache. A linear
extrapolation from the last point assumes the superlinearity stops exactly where the measuring
stopped, and 10⁷ cells is another **9.5×** beyond it.

So: **10⁷ points is ≥ 224 s, a FLOOR and not an estimate.** Carrying the measured superlinear
factor through the remaining 0.81 of a decade-step gives ≈ 325 s, and even at **5× the floor** it is
under twenty minutes — on a report describing a run that took days.

**The consequence is the one the prediction was written to decide, and it survives the caveat
easily. Open question 22's quiet-gate repair is not needed by 2f**, and the working day per session
it was predicted to cost is not spent. The prediction on the record was that every measurement that
has cost this project days was a *fitting* measurement and 2f fits nothing; that held.

> **`≈ 235 s` was what this section first said, flat.** A number travelling without its population
> is what this project's whole discipline is against, and the number was mine. It is a floor,
> quoted as one.

**This does not close open question 22**, which remains named and unowned. It removes 2f as a
reason to take it.

## P2 and P3 — the instrument is calibrated in both directions

P2's p-values are uniform: median **0.499** against an ideal 0.5, rejection **0.045** against
α = 0.05, and **none** at the p-floor. P3, on the **same failure count** with only the arrangement
changed, puts **every one of 200 replicates at the floor**.

**Both bands were numeric and both are met**, which is what makes a null result readable later: a
non-rejection now means something because P3 shows the statistic can reject, and a rejection means
something because P2 shows it does not reject on noise.

## P4 — REFUTED, and the reasoning was wrong in a way worth keeping

| width | wrapped z | unwrapped z | **z difference** | joins lost | relative edge loss | predicted bound |
|---|---|---|---|---|---|---|
| 72 | 105.94 | 101.24 | **4.70** | 90 | 0.70% | 1/72 = 1.39% |
| 360 | 239.83 | 228.81 | **11.02** | 90 | 0.14% | 1/360 = 0.28% |

**The edge-count halves of the prediction were met and the z half was refuted by forty-fold.** Both
edge bounds held — the loss is exactly `H` joins, tighter than the `2H` predicted, and the relative
loss is under `1/W` at both widths. **And the z difference is 11.02 where < 0.25 was predicted.**

**THE ERROR IS THAT I PREDICTED ON THE DENOMINATOR AND THE EFFECT IS IN THE NUMERATOR.** The z is
`(observed − null_mean) / null_sd`. Not wrapping removes 0.14% of the *edges* — and it removes
**16 of the observed cluster's own joins** (356 → 340), because the joins at the seam are precisely
the ones that make a seam-straddling cluster **one** cluster rather than two. The null's mean and
spread barely move (the implied null SD is ≈ 1.45 joins), so a 0.14% edge loss lands as an 11-SD
shift in the statistic.

> **The general form, which is this project's shape again: a bias reasoned about on the wrong
> denominator.** The lost joins are not a random sample of edges. They are the specific edges the
> hypothesis is about. **Any argument that bounds an effect by the fraction of a population removed
> must first check whether the removal is independent of the effect** — here it is maximally
> dependent, by construction.

**The refutation clause fires as written**: *"a z difference above 0.25 means the no-wrap choice is
NOT free and D4 must either detect global coverage or restate its limitation as material rather
than negligible."*

**And this fixture understates the hazard rather than overstating it.** Both arms reject
overwhelmingly here (z ≈ 229 and 240), so no decision flips: the cluster is enormous. **The
untested case is the dangerous one** — a *small* cluster existing only at the seam, where wrapped
detects and unwrapped may not. This spike did not measure that, and says so rather than
extrapolating.

**A SECOND LIMITATION, FOUND BY ruff RATHER THAN BY ME.** The seam fixture creates a random
generator and never uses it — `F841`, caught at the commit — which means **the placement is
deterministic and each width is ONE reading, not a distribution.** So 11.02 is a point measurement
on a fixed fixture, not a central value with a spread. It is enough to refute a predicted bound of
0.25 by forty-fold, and it is not enough to characterise the effect. **P4-prime replicates 120
times per size; this did not.** Recorded because a linter found a limitation in a measurement's
design, which is not what linters are for and is worth noticing.

**D4 must change. The decision is not Task 0's to take** and was raised with its numbers;
**taken 2026-09-19 as (a) plus a Δz print** — see the plan's D4, which this verdict does not
restate.

## P5 — REFUTED, and the detector rather than the design is what failed

| target eligible | side | rejection at α = 0.05 | **p-median** | at p-floor |
|---|---|---|---|---|
| 2000 | 53 | 0.058 | **0.476** | 0.008 |
| 1000 | 38 | 0.025 | **0.559** | 0.000 |
| 500 | 27 | 0.033 | **0.569** | 0.000 |
| 200 | 17 | 0.017 | **0.699** | 0.000 |
| 100 | 12 | 0.025 | **0.700** | 0.008 |
| 50 | 8 | 0.025 | **1.000** | 0.000 |
| 25 | 6 | 0.025 | **1.000** | 0.000 |

**The prediction was that the rejection rate would leave [0.02, 0.09] at or below 50 eligible
points. It does not leave the band at any size** — the single dip, 0.017 at target 200, is inside
the noise of 120 replicates (SE ≈ 0.014 at 0.05) and is not a break.

**What actually degrades is visible in a column the prediction did not name.** The p-median marches
monotonically from 0.476 — ideal uniformity — to **1.000**, where the observed join count sits at or
below every one of 999 null draws in most replicates. **The test does not become mis-calibrated; it
becomes conservative and then degenerate**, and *a rejection rate at a fixed α is structurally blind
to that*, because a test that never rejects has a low rejection rate and a low rejection rate is
what "well-calibrated" looks like from below.

> **(c7)'s shape at a measurement rather than at a criterion: the detector was keyed on the
> quantity that was easy to compute rather than on the property being measured.** Calibration is a
> statement about the whole p-value distribution; the rejection rate is one quantile of it, and the
> one least sensitive to the failure mode that actually occurs.

**So the floor is not yet measured, and Task 6 cannot consume a number from this run.** What the
readings do establish, and what a second pass must confirm with a detector chosen for it:

- uniformity is intact at **2000** and already drifting at **1000**;
- the degenerate regime — p-median 1.000 — begins between **100 and 50**;
- the useful floor is therefore somewhere near **500**, and that is an estimate from a mis-aimed
  instrument, **not a measurement**.

**P5-prime is owed before Task 6**, with its own predictions committed first and a detector that
measures the distribution: the KS distance of the p-values from Uniform(0, 1), and the fraction of
replicates at p = 1.0, at the same sizes.

## P6, reproducibility, and the committed-number control

P6: a checkerboard eligible mask yields **zero rook edges**, the statistic returns **unavailable**
naming that reason, and **no number is returned**. The fixture precondition — that a checkerboard
genuinely has no adjacent eligible pair — is asserted separately and holds, so the result is not an
artefact of a fixture that could not express the condition.

Reproducibility: three runs under one seed give **bit-identical** z (1.5792328059765177); a second
seed gives 1.5257, a distance of 0.053 against a null SD of **8.70**.

The committed-number control reproduces the real-data spike's `real_ct` histogram **exactly** —
809 OK, 91 `DEGENERATE_HESSIAN`, 900 cells, no tolerance — so the counter reproduced a number
already in the tree before producing any new one.

## What this verdict changes

1. **Tasks 5 and 6 proceed**, and the permutation null is affordable at production scale. **P1's
   gate is passed.**
2. **Open question 22's repair is not needed by 2f.** It stays named and unowned.
3. **D4 must be re-decided** on P4's numbers — wrap detection, or a limitation restated as material
   for seam-straddling clusters. Not Task 0's decision.
4. **P5-prime is owed before Task 6's floor invariant**, with a distributional detector and its own
   committed predictions. Task 6's unavailability rule keeps its other two cases meanwhile.
   **The estimate above is NOT carried forward.** *"Useful floor near 500"* comes from the
   instrument this verdict refutes, and Task 6's invariant consumes the floor — **taking a number
   from a refuted instrument into a shipped invariant is the exact defect this project keeps
   catching**, and P1 shows the re-run costs seconds.
5. **P4-prime is owed too**, and it is the case this spike correctly refused to extrapolate: a
   *small* cluster existing only at the seam, sized near the detection boundary, rejection rate
   wrapped against unwrapped. One number doing two jobs — it makes the not-global branch's
   limitation honest rather than hand-waved, and it prices the false negative that D4's detector
   trades for. **This spike's fixture rejected overwhelmingly on both arms, so it measured a case
   where nothing was at stake.**
5. **The harness stays** as Task 6's control, labelled throwaway.
