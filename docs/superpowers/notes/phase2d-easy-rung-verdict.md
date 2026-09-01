# The easy rung — THE GATE PASSED AND THE POSITIVE CONTROL FAILED

**Measured 2026-09-01, quiet host, `git HEAD = 0ae11a5`, 10.18 h.** Predictions committed first in
[`phase2d-easy-rung-predictions.json`](phase2d-easy-rung-predictions.json); the records are in
[`phase2d-easy-rung-measured.jsonl`](phase2d-easy-rung-measured.jsonl) and the report is
[`phase2d-easy-rung-report.json`](phase2d-easy-rung-report.json). **One rung, one session, every
arm inside one `run_rung` call.**

> ## THE RESULT IN ONE LINE
>
> **The interior null came back clean, and then all three arms returned the floor — because the
> WARM AND COLD MISCLASSIFICATION PROFILES ARE IDENTICAL AT ALL 32 INDICES.** There is no smear to
> resolve at the rung built to make one appear. **Every one of the 384 points had a valid warm
> source** (`n2_exhausted_spiral = 0`), so this is not *"nobody got a warm start"*, and the
> estimator is not blind here: it reported a 0.33 profile faithfully where one existed.
>
> **Per the plan, that is 2d's finding and the sub-phase stops for a decision. A retune of the
> easy rung is a NEW RUNG WITH A NEW NAME, never an edit.**

## What was predicted, and what happened

| # | reading | predicted | measured | verdict |
|---|---|---|---|---|
| E1 | the interior null | at the floor — Task 2's committed clause, cited not restated | **at floor**, profile max **0.33** | **HELD.** The gate passed |
| E2 | the warm smear width | **2–6 fine cells**, one-sided on the A side | **at the 1-cell floor** | **REFUTED FROM BELOW** — the clause 2d exists to be able to fire |
| E3 | warm > n2 | an ordering | **unevaluable at width level** (all three at the floor); at profile level **warm ≡ cold**, and n2 above both at exactly one index | refuted, and the informative form is the profile |
| E4 | the net saving | band **[−5%, +15%]** | **−2.45%** net, **−0.41%** pass-2-only | **HELD**, at the low end |
| E4b | warm saving < `self` saving | an ordering | −2.4% against **+91.05%** | **HELD** |
| E5 | N1/cold iterations | **[1.0000, 1.0026]** | **1.00032** | **HELD** |
| E5b | `self`/cold, the void control | ≤ 0.25 | **0.0895** | **HELD.** The instrument can tell arms apart by cost |
| E6 | the four cross-checks | all pass | **all four pass** | **HELD** — see below |

## The profiles, which are the finding

The estimator's own numbers, per normal index, as the fraction of the 12-cell parallel line whose
selected candidate carries the wrong family:

    index      10    12    16    17    18    19    20    21    22    24    26    27    28    29    31
    cold      0.08  0.08  0.25  0.08  0.17  0.08  0.33  0.17  0.17  0.08  0.08  0.25  0.08  0.08  0.08
    warm      0.08  0.08  0.25  0.08  0.17  0.08  0.33  0.17  0.17  0.08  0.08  0.25  0.08  0.08  0.08
    n2        0.08  0.08  0.25  0.08  0.17  0.08  0.33  0.33  0.17  0.08  0.08  0.25  0.08  0.08  0.08

(every index not listed is exactly 0.0 in all three arms)

**THREE THINGS FOLLOW AND THEY ARE DIFFERENT CLAIMS.**

1. **Warm and cold agree at every index.** Warm-starting moved no point's selected candidate
   anywhere on the field, to the resolution of a 12-point row mean. **This is not the majority
   rule's forfeit** — that forfeit is about a real band sitting under a half, and there is no band:
   the two arms' rows are equal, not both-small.
2. **The N2 arm moved two points in one row, and warm moved none.** An equal-distance random
   displacement changed the answer somewhere; the informative displacement did not. **The floor arm
   is doing its job and is not the thing that is silent.**
3. **The misclassification is not at the boundary. It is in region B**, indices 16–31 — the
   `matern12` regime — with region A (0–15) almost perfectly classified. That is the recorded
   fixture fact about which family is hard, arriving as a spatial pattern, and it is **not** an
   artifact of anything 2d does.

## Why: the field is too easy for warm-starting to do anything at all

**D1's 2026-08-30 reattribution predicted the saving and this run extends it to the artifact.** The
saving tracks **cold-start difficulty**: 2c measured +7.80% at 28.27 cold iterations per point,
+31.73% at 35.32 and +42.28% at 40.79. **This field runs at 24.4 — below 2c's shortest fixture** —
and the amendment says in as many words that *"a near-zero saving there is what this curve
predicts"*. It came in at **−0.4%**.

> **THE NEW PART IS THAT THE ARTIFACT FOLLOWS THE SAME CURVE.** Hysteresis is the optimizer keeping
> the neighbour's answer; at 24 iterations from a moment-ladder start it reaches the same optimum
> from either start, so there is nothing to keep. **The lever that produces an artifact is the
> LIKELIHOOD's difficulty, not the boundary's starkness** — and `Delta` only makes the boundary
> stark. E5 named `l` and `Delta` as the two levers; this rung says the axis that matters for the
> artifact is neither.

**AND THAT PROPAGATES TO THE OTHER TWO RUNGS BEFORE THEY ARE RUN.** All three rungs are
indistinguishable in cold iterations — **24.375 / 24.333 / 24.396**, measured 2026-08-31 — so they
are all at this difficulty. The middle and hard rungs have **weaker** contrast than this one. **A
null at the easy rung with a stark boundary is not evidence that a fainter boundary will produce
one**, and running them as planned would spend ~20 h measuring the same null with less contrast.

## The cost, measured — and E2 does not fit any more

| component | seconds | per point | per point per arm |
|---|---|---|---|
| the cold `run` pass | 5 370.3 | **13.98 s** | 13.98 |
| the shipped two-pass | 5 640.1 | 14.69 s | 14.69 |
| the N2 map (**four arms**) | 23 156.9 | 60.30 s | **15.08** |
| the `self` arm | 2 471.5 | 6.44 s | — |
| **total** | **36 639** | | **10.18 h** |

**THE REALISED RATE IS 14–15 s/point/arm AGAINST THE 13.15 THE BUDGET IS PRICED AT.** One rung
costs **10.18 h**, so **three rungs is 30.5 h — over the 30 h ceiling** (28.5 h without the `self`
arm). The 25.3 h re-price filed at Task 5's pre-flight used 13.15 s and is now itself superseded by
a measurement. **Reported rather than absorbed: it is a scope decision, not a rounding.**

> ## AND A COST-MODEL FINDING THE BUDGET'S UNIT HIDES
>
> **The `self` arm collapses 11× in ITERATIONS and only 2.2× in SECONDS** — `0.0895` against
> `0.460`. Per iteration it is **5.1× more expensive** than the cold arm, because a fit pays a
> fixed per-cell cost — state space, ladder start, scoring, ranking — that does not shrink when the
> optimizer stops early. **A budget built in iterations under-prices a fast arm by that factor**,
> and Task 0's *"self is 4–6% of cold"* would have mis-predicted its wall clock by five times.
> **Iterations are the right unit for reproducibility and the wrong one for money.**

## The four cross-checks, all of them free, all of them passing

| check | result | what it closes |
|---|---|---|
| the map's COLD arm against the cold `run` **store** | **identical**, 1 150 cells, **0 differing** | **Task 0's third reading, open since 2026-08-30**: `run`'s tiled fit phase does bit-identically the work a bare `fit` does. The budget's unit is measured on `fit` and spent on `run`, and that gap is now closed rather than bounded |
| the map's WARM arm against **pass 2's store** | **identical**, 1 152 cells, 0 differing | the driver's REBUILT warm array **is** the one pass 2 used. N1 and N2 are displacements from it, so this was the one way every arm could have been keyed to a start no run made |
| criterion 17's committed figure, off this run's store | **2340 iterations, 24.375 per point, 287 of 288 cells** — exact | this field **is** the fixture the committed figure describes, and the two paths agree to the digit |
| fine points sourcing themselves | **0** | D12's structural half of E6's upper refutation clause, at no cost |

**AND THE SELECTION AXIS IS LIVE**: both correlated candidates win somewhere, `white` never wins,
so no width here is a statement about the iteration cap. That gate was written because at a low cap
`matern12` never reaches `OK` and every point selects `white`.

## What this run does NOT establish

- **No magnitude, and this rung could never have supplied one.** Its `l` and `Delta` were chosen by
  us for detectability; it is a demonstration and a floor.
- **Nothing about real altimetry.** The field's coherence and contrast are construction parameters,
  and its cold difficulty is *below* 2c's field at its shortest record length. **The standing
  limitation is unchanged and the named closer is still a spike on a real gridded product** — whose
  cheaper half, per D1's amendment, is to measure real cold-start difficulty FIRST.
- **Not that warm-starting is safe.** It says that **at this difficulty** it does nothing —
  neither a saving nor a bias. 2c measured +42.28% at 40.79 iterations per point, where there is
  something to keep and therefore something to smear.

## One defect in this harness, found in its own output

**`selection_axis`'s `counts` enumerates `range(len(winners))` rather than the candidate set**, so
with winners `[1, 2]` it reported counts for candidates 0 and 1 and never for candidate 2. The
verdict above rests on `winners` and `both_regimes_win`, which are correct; the counts are
incomplete. **(c5) in my own instrument — a gate over a set that can grow, written against an
enumeration of its members** — and it is fixed in the harness rather than only noted here.
