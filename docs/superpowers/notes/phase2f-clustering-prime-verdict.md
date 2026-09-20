# Phase 2f Task 0 — the spike extensions' verdict (2026-09-20)

The two extensions the [first verdict](phase2f-clustering-verdict.md) owed. Predictions were
committed to [`phase2f-clustering-prime-predictions.json`](phase2f-clustering-prime-predictions.json)
before the harness extension existed; readings are in
[`phase2f-clustering-prime-measured.jsonl`](phase2f-clustering-prime-measured.jsonl). The
instrument is **reused** from the first harness deliberately: the question here is about fixtures
and detectors, not about the join count, and a second implementation would make a disagreement
between the two passes ambiguous.

## The sentence a reader can carry

**P5-prime measured the floor and P4-prime measured its own fixture** — and the second outcome is
the more useful one, because it is the third instance in one spike of an instrument reporting its
operating point instead of an answer.

| prediction | verdict | reading |
|---|---|---|
| P5p precondition | **FIRED** | KS 0.717 and fraction-at-1 0.717 at n = 50, both ≥ 0.5 |
| P5p-1 | **MET** | KS 0.112 at n = 2000 (≤ 0.15); KS 0.717 at n = 50 (≥ 0.5) |
| P5p-2 | **MET** | the floor is **500**, inside the predicted {500, 1000} |
| P5p-3 | **MET** | fraction-at-1 exactly 0.000 at every n ≥ 500; 0.717 at n = 50 |
| P4p-1 | **REFUTED — and its refutation clause is NOT applied** | gap 0.000 at every rung, from a fixture with no discriminating power |
| P4p-2 | **VACUOUS** | the gap is identically zero, so "non-monotone" has nothing to describe |

---

## P5-prime — the floor is 500, and the detector proved itself first

**The precondition fired before any floor was reported.** At n = 50 — where the first pass measured
a p-median of exactly 1.000 — the replacement detector returns KS **0.717** and fraction-at-1
**0.717**, both above the required 0.5. Had it not, the harness emits `p5_prime_stopped` and
reports nothing: *a detector that cannot see the failure already in hand is not calibrated to look
for it.*

| n | KS | KS p | fraction at p = 1 | p-median | uniform? |
|---|---|---|---|---|---|
| 2000 | 0.112 | 0.090 | 0.000 | 0.561 | **yes** |
| 1000 | 0.105 | 0.134 | 0.000 | 0.571 | **yes** |
| **500** | **0.059** | **0.781** | **0.000** | 0.540 | **yes** |
| 200 | 0.188 | 0.0003 | 0.042 | 0.682 | no |
| 100 | 0.317 | 0.000 | 0.317 | 0.711 | no |
| 50 | 0.717 | 0.000 | 0.717 | 1.000 | no |
| 25 | 0.842 | 0.000 | 0.842 | 1.000 | no |

**Both detectors agree on the boundary** — KS calls 500 uniform and 200 not; fraction-at-1 is
exactly 0.000 down to 500 and first nonzero at 200. Two independent readings agreeing is what makes
this a measurement rather than one instrument's opinion (P5p-3).

### Two things stated so a later reader does not over-read the number

**THE FLOOR IS A LADDER RUNG, NOT A BOUNDARY.** 200 fails and 500 passes, so the true threshold
lies in **(200, 500]** and **500 is the smallest tested size demonstrated uniform**. Task 6's
invariant must say it that way, or a later reader takes 500 for a measured threshold with a
precision it does not have.

**THE CROSS-CHECK PASSES, AND NOT COMFORTABLY.** KS at n = 2000 is **0.112** against the
pre-registered threshold of 0.15 and against a 5% critical value of ≈ 0.124 at 120 replicates. It
passes the threshold that was registered, which is what counts, and it passes it with little room.
**P2's negative control is not impugned** — but anyone later leaning hard on P2's calibration
should **re-run at more replicates rather than cite this margin.**

**The first verdict's estimate — "useful floor near 500" — lands on the same number, and that is
not a reason to have carried it.** It was a number from a refuted instrument, and it would have
entered a shipped invariant right by luck.

---

## P4-prime — the fixture had no discriminating power, and that is the finding

| side | cluster cells | wrapped rejection | unwrapped rejection | gap |
|---|---|---|---|---|
| 4 | 16 | 1.000 | 1.000 | **0.000** |
| 6 | 36 | 1.000 | 1.000 | **0.000** |
| 8 | 64 | 1.000 | 1.000 | **0.000** |
| 10 | 100 | 1.000 | 1.000 | **0.000** |
| 12 | 144 | 1.000 | 1.000 | **0.000** |
| 14 | 196 | 1.000 | 1.000 | **0.000** |

**Both arms reject 120/120 at every rung.** The diagnostic says why:

| side | arm | observed joins | null mean | z |
|---|---|---|---|---|
| 4 | unwrapped | 20 | **0.0101** | 199.9 |
| 4 | wrapped | 24 | 0.0101 | 239.9 |
| 8 | unwrapped | 104 | **0.1910** | 234.7 |
| 8 | wrapped | 112 | 0.1910 | 252.8 |

16 failures in 32,400 cells is a background rate of **0.0005**, so the null expects **0.01 adjacent
pairs**. Against that, *any* contiguous clump is 200 standard deviations out. **The seam does
contribute real joins — 20 → 24 at side 4 — and it cannot change the decision, because both arms
are saturated.** The ladder varied cluster size; the variable detection actually turns on is the
**background failure rate**, which sets whether the null has any mass at all.

### The refutation clause is not applied, and the test that licenses that

P4p-1's clause read: *"if the maximum gap across every size is below 0.30, the seam's practical cost
is small … and D4's rejected option (b) becomes defensible."* **The claim is refuted and the
inference it licensed does not follow**, because the clause presumed a fixture able to show a gap.

**(a10.1), applied:** *a post-hoc invalidation of an instrument is legitimate exactly when it would
have fired the same way under the opposite outcome.* The invalidating property here is the
saturation, and it is **computable from the background rate alone, before the gap is looked at** —
0.0005 gives a null expectation of 0.01 joins. **Had the gap come out large, the same saturation
would have invalidated "the gap is large, so (b) is indefensible" just as completely.** The
invalidation does not know which way the result went. Legitimate.

**So the reading is INDETERMINATE — neither pass nor fail — and D4 does not reopen on this
evidence.**

### The omission, stated plainly

**The precondition P4-prime needed was written for P5-prime, in the same file, on the same day.**
P5-prime's says the detector must fire on the known-degenerate case; P4-prime's mirror — *the
fixture must have an operating point where the arms can differ* — was not written. That is (a10)'s
third instance in one spike, and the cheapest possible demonstration of how the omission happens:
the rule was applied in one half of a predictions file and forgotten in the other.

## What this verdict changes

1. **Task 6's floor invariant takes 500**, stated as *the smallest tested size demonstrated
   uniform*, with the true threshold in (200, 500].
2. **D4 does not reopen.** Its not-global branch's limitation is written **priced where priced
   (Δz = 11.02, at a saturated operating point) and named where not** — the consequence was
   attempted on two ladders and reached by neither.
3. **D4's hazard is reduced by mechanism rather than priced**: the two-arm zone widens to every
   near-global grid, so the realistic false negatives print both arms instead of relying on the
   detector being right.
4. **D4's Δz print is struck for a both-arms print.** Δz cannot distinguish *two arms agreeing
   loudly* from *two arms disagreeing quietly*, which is its only job — A1's defect inside its own
   sub-phase.
5. **P4″ is owed at a trigger, not dropped: the first time a global store exists**, carrying the
   precondition both earlier attempts lacked.
