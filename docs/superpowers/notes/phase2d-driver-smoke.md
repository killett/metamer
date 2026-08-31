# The driver's two smoke runs — both branches of E6's gate, on real runs

**NEITHER IS A MEASUREMENT AND BOTH SAY SO IN THEIR OWN BYTES.** `is_a_smoke_run` is `true` in
each instrument block, the geometry is **26 × 2** against the shipped **32 × 12**, and the record
length is **24** against **630**. **Task 9 must refuse a report carrying that flag as evidence for
any criterion.** What they establish is that the pipeline runs end to end and that the gate has
both branches — which no unit test on constructed readings can establish, because the readings are
what it constructs.

**Why 26 and not something smaller.** The interior null needs
`n_normal // 2 − NULL_LINE_OFFSET_CELLS ≥ 1` and the shipped offset is 12, so **26 is the smallest
normal axis on which a legal null line exists at all.** A field small enough to be fast cannot
carry the control.

| | contaminated run | clean run |
|---|---|---|
| `max_iter` | **8** | **default** |
| null line | **width 26.0**, not at floor | **at floor**, `cells = None` |
| `contaminated` | **true** | **false** |
| smear widths | **all withheld** | cold **13.0** · warm **14.0** · n2 **14.0** |
| N2 excluded | **52 of 52**, all `exhausted_spiral` | **0** |
| iterations/point | cold 19.90 · warm 19.98 | cold 51.96 · warm 52.23 |

## The contaminated run, and the profile did exactly the job it is carried for

**The null returned 26.0 cells — the entire normal axis — and the gate stopped the rung.** Task 2's
pre-flight named two causes for a firing null and said the profile is what separates them: the
estimator reading the field's own structure, or **the baseline disagreement rate itself above a
half**, which is a statement about selection rather than about warm-starting.

> **THE PROFILE IS FLAT AT 1.0 AT EVERY ONE OF THE 26 INDICES.** Not a band, not a slope — every
> point misclassifies, everywhere. **That is unambiguously the second cause**, and `cells = 26.0`
> alone could not have told it from the first.

**And the cause is the recorded fixture fact.** At `max_iter = 8` the Matérn candidates never reach
`OK`, so `white` wins at every point and disagrees with both regimes; `coarse_ok` then finds no
usable coarse fit, the spiral is exhausted at all 52 points, and the N2 map is empty. **One
low iteration cap produced a degenerate selection axis, an empty floor arm and a firing null**, and
the three are the same fact.

## The clean run, and one observation that is NOT a finding

Uncapped, the null comes back at the floor, the rung is not contaminated, all three arms produce
widths and the N2 map excludes nothing.

> **COLD'S WIDTH IS 13.0, WHICH IS NOT ZERO — AND THAT IS THE ARGUMENT FOR THE N2 ARM, ARRIVING
> AS A MEASUREMENT.** A cold arm has no warm start, so its width is misclassification near the
> boundary and nothing else. **A smear read as warm's absolute width would be reading 14.0 where
> 13.0 of it is not hysteresis.** This is what *"a smear measured against zero is a different
> claim from one measured against the width an equal-distance random start produces"* looks like
> when the numbers exist.
>
> **IT IS AN OBSERVATION AND NOT A FINDING, AND THE DIFFERENCE MATTERS.** At `n_parallel = 2` the
> majority threshold is over **two points**, so the profile is nearly binary and a single cell
> decides each index; at `n_time = 24` almost nothing is well determined. **No magnitude here
> transfers to the shipped geometry**, and the ordering warm ≥ n2 ≥ cold is three numbers on a
> fixture built to be small. **Tasks 5 to 7 measure this; the smoke run only shows the arithmetic
> is wired up.**

## What these two runs establish, stated narrowly

1. **The driver runs end to end** — field, cold pass, two-pass, warm-start rebuild through the
   shipped `coarse_ok`/`source_map`/`read_warm_starts`, N2 map, agreement maps, null, widths,
   report.
2. **E6's gate has both branches on real data**, not only on constructed readings.
3. **The withheld path produces objects carrying reasons**, and on the contaminated run no width
   was computed at all — the reports differ in that the contaminated one's `reading` fields are
   `null`, not merely its values.
4. **Nothing about any magnitude.** See the flag in the block.
