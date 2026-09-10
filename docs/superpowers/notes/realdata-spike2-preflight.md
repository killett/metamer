# The real-data spike, SECOND half — pre-flight (2026-09-09)

**The first half's pre-flight is [`realdata-spike-preflight.md`](realdata-spike-preflight.md) and
its verdict is [`realdata-spike-verdict.md`](realdata-spike-verdict.md). Neither is restated
here.** This audits the second half's brief, which is narrower than a full audit: **the 12 points,
not the 30.**

**Written before any code and before any fit of the second half.**

---

## G1 — THE BRIEF CITES A NUMBER THE RECORD WITHDREW, AND THE REAL PRIOR IS TEN POINTS LOWER

The brief says *"2d measured 99.48% agreement on a smooth simulated field. That number has no
reason to transfer."*

**`PROGRESS.md` corrected 99.48% on the day it was written**, and the correction is in the 2d close:

> *"CORRECTED THE SAME DAY: the first report said '99.48% of cells agree warm and cold'; that
> figure is the **SELF arm against cold, over points**. Warm-against-cold agreement at point level
> is **not in the artifact** — the report carries profiles and not selection maps, and the stores
> were temporary — so the differing points' positions and condition numbers **cannot be recovered
> without a ~4.4 h re-run.**"*

**SO THE PRIOR THE BRIEF NAMES IS NOT A PRIOR FOR THIS COMPARISON, AND 2d HAS NO POINT-LEVEL
WARM-VERSUS-COLD AGREEMENT FIGURE AT ALL.** What the project actually holds:

| figure | what it compares | where |
|---|---|---|
| **90.37%** — 122 of 135 | **warm against cold, selection, over points**, `N = 630` | 2c, and it is the one this half's reading is comparable to |
| 99.58% | **self** against cold, over points | D12's lattice finding |
| 95.00% | fine points against cold | D12, the other half of the lattice contrast |
| *(none)* | warm against cold at point level | **2d — the artifact defect** |

**THIS MOVES THE PREDICTION AND IT MOVES IT A LONG WAY.** 90.37% was measured **against a
pre-agreed 90% stop, and 121 of 135 would have said report and stop** — so the mechanism was
authorized with a margin of **one grid cell**, on a simulated field. A prior of 99.48% suggests
there is room to fall; the real prior is already at the threshold.

**Reported as a defect in the brief either way**, per the precedence rule: a measured, dated number
supersedes an unmeasured one wherever it lives, and a disagreement between two of them is a defect
to report.

> **AND THIS HALF MUST NOT REPEAT THE DEFECT THAT CAUSED IT.** 2d's own recorded remedy is *"a
> report must carry the map the width was read from"*, which is one of the two owed wirings. **The
> harness writes the per-point selected candidate for every arm into its artifact**, so the
> question 2d cannot answer without a 4.4 h re-run is answerable here from the file. That is not
> the general wiring — which stays owed — it is this measurement refusing to produce the same hole.

---

## G2 — (j5) ALL FOUR ARMS SHARE ONE CODE PATH, BECAUSE `warm − random` IS A DIFFERENCE

The headline quantity is **`warm − random`**, and a difference between two arms measured on two
code paths is not a difference. The shipped two-pass driver (`batch.twopass.run_two_pass`) exists
for `warm`; **nothing shipped produces `random` or `self`**, so those must be in-process `core.fit`
with hand-assembled `x0` — which is exactly what 2c did.

**So all four arms go through in-process `core.fit`**, and the **warm rule is the shipped one**:
`batch.warmstart.source_map`, at the config's `coarse_stride` and `spiral_bound`. The rule is
production's; the driver is not, and that distinction is stated rather than blurred.

**THE SHIPPED DRIVER IS RUN ANYWAY, AS A CROSS-CHECK THAT (j5) PERMITS** — same quantity, same
conditions, different route. Both paths take the same source map and call the same `fit`, so their
warm iteration totals should agree; **a disagreement would mean the two do not deliver the same
warm start, and every warm number in this project would inherit the question.** Nobody has run
that comparison.

---

## G3 — THE FIRST HALF'S BOX MEASURES COHERENCE AT EIGHT TIMES THE SEPARATION THE MECHANISM USES

The first half's fixture is **1°-spaced** — DUACS decimated by 8, chosen so 300 points spanned
several regimes and difficulty was not a property of one patch. **Applying the shipped
`coarse_stride = 8` on top of that puts coarse points 8° apart**, and a fine point's warm source up
to 4° away.

**Production is 0.125° with stride 8: coarse points 1° apart, warm sources at most 0.5°.**

**COHERENCE FALLS WITH DISTANCE, SO REUSING THE FIRST HALF'S GRID WOULD UNDERSTATE PROXIMITY** —
and understating proximity biases toward *"the machinery does not earn its cost"*, which is a
conclusion this half could reach wrongly and expensively. **The second half re-cuts at native
resolution**, from the mirror already on disk, so no new download is needed.

**The cost of the re-cut is that the two halves are on different water**, 15° × 20° against
2.1° × 2.1°. The cold arm re-measures difficulty on the new box, so both readings exist and the
comparison is available rather than assumed away.

---

## G4 — THE GEOMETRY WAS CHOSEN BY MEASUREMENT AGAINST 2c's INSTRUMENT, NOT BY ARGUMENT

`warmstart.source_map` at the shipped stride and bound, on two candidate grids of the same cost:

| grid | points | coarse | warm radius mean | max | far-pool min at `DISTANT_MIN = 6` |
|---|---|---|---|---|---|
| **17 × 17** | **289** | **3 × 3 = 9** | **2.602** | **4** | **5** |
| 15 × 20 | 300 | 2 × 3 = 6 | 3.040 | 6 | 2 |

**2c's own fine-point mean radius was 2.556.** The 17 × 17 grid reproduces it to **1.8%**, which
makes `warm` the same *kind* of arm 2c measured rather than a nominally-similar one — and its max
radius of 4 sits clear of `DISTANT_MIN = 6`, where the 15 × 20 grid's max radius **collides** with
it. (i7): a discriminating fixture must be placed outside where the two functions agree, and on
the wider grid the nearest and the "distant" arm would meet.

**`DISTANT_MIN = 6` IS 2c's OWN CONSTANT AND IS NOT RE-CHOSEN**, which keeps the instrument.

---

### G4b — FOUND AT THE SMOKE, 2026-09-09: THE GEOMETRIC RADIUS IS NOT THE RADIUS

**G4's 2.602 / max 4 was measured with `coarse_ok` all true.** The smoke ran the real coarse fits
and got **mean 2.980, max 8** — because **one coarse cell of 27 came back non-`OK`**, and the
spiral had to search past it.

**MAX RADIUS 8 IS BEYOND `DISTANT_MIN = 6`.** On those cells the `warm` source is *as far away as a
distant one*, so the two arms are **not separated there** and their difference is contaminated
toward zero — (i7), arriving through the OK filter rather than through the geometry.

**IT IS NOT REPAIRED BY MOVING A CONSTANT.** Raising `DISTANT_MIN` after seeing the data is
choosing a threshold with the answer in view, and with nine coarse points the far pool would start
emptying. **What is owed is that the affected cells are counted and the reading is given both
ways**: the headline over all cells, which is what the shipped mechanism actually does, and a
stratified reading over cells whose source the OK filter did not push out.

**THE STRATUM IS BINNED BY A QUANTITY THE TREATMENT CANNOT MOVE** — the warm radius follows from
the coarse grid and the **cold** coarse fits — so (j7) is satisfied and this is not conditioning on
the outcome.

**AND 2c's `ok_changed` IS THE SAME QUANTITY**, which its harness emitted and called *"whether the
OK filter CHANGED the choice, which is what makes the spiral load-bearing rather than
defensive"*. It is emitted here too, so the two runs are comparable on it.

## G5 — 2c's DISCRIMINATING CONTROL HAS A SILENT FALLBACK, AND IT IS (a0) AT AN ARM

`warmstart-spike-harness.py`:

    rand_src[b, c] = int(rng.choice(far)) if far else int(idx)

**When no coarse point is far enough, the `random` arm silently takes the `warm` source.** So
*"there was no distant source"* and *"the distant source behaved exactly like the near one"*
produce the identical reading — and the contamination runs one way: it pulls `random` toward
`warm`, **shrinking `warm − random`, which is the headline quantity, toward zero without saying
so.**

**It cannot fire on this geometry** — the far-pool minimum is 5 — **and the harness asserts that
rather than relying on it.** A count of fallbacks is emitted and a nonzero count refuses.

**Whether it fired in 2c's own run is not recoverable from the committed JSONL**, which records
`n_measured`, `n_excluded` and the source-map summary but no fallback count. Recorded as a
question about 2c's 12.00 points rather than answered; **the direction is known even though the
magnitude is not, and it is the direction that would have understated the number 2c published.**

---

## G6 — CONSTRAINT 1: A VALID WARM START IS NOT A WARM START USED, AND THE HARNESS REFUSES ON IT

Task 3's finding, and §5 of the handoff: **validity is a property of the SOURCE** — the spiral
found an `OK` coarse fit within the bound — **usage is a property of the FIT**, recorded as
`InitRung.WARM_START`. Measured 2026-08-27 on a fixture with all-NaN series: **147 warm rungs
against 182 valid sources**, and `used ≤ valid` with equality only where every series is fittable.

**AND THE FAILURE MODE IS BYTE-IDENTICAL TO A CORRECT NULL:** every point warm-started with
`x0_valid` all false produces a run indistinguishable from cold. `FitResult.init_rung` is what
separates them.

**So the harness counts `WARM_START` rungs per arm and refuses when the count is not what the
source map implies**, and the count is in the artifact beside every saving.

---

## G7 — CONSTRAINT 3: THE INTERSECTION IS A SELECTION AND ITS SIZE IS A READING

The first half measured **91 of 900 cells non-`OK`** on real data against **1 of 1152** on the
simulated field. §11.2's audit compares on the **both-`OK` intersection**, so on real data the
comparison loses about a tenth of the population per arm before it starts — and 2d's own finding
is that an intersection is a selection effect if disagreement concentrates on hard cells.

**Reported per arm pair: the intersection's size, the flip counts in each direction, and whether
the flips are symmetric.** An outcome flip — a fit appearing or vanishing rather than moving — is
**a different quantity with its own denominator** (h2/D9), and it has never had a real population
before.

---

## G8 — THE CONTROL IS THE WARM PATH, BECAUSE THE COLD ONE IS ALREADY VERIFIED

Constraint 1 is right that a warm pipeline has more ways to be silently wrong. **The cold half of
the control was verified to zero difference on 2026-09-07** and re-running it costs 2.92 h to
re-establish something no longer in doubt.

**What has never been verified is the two-pass path.** So the control is `run_two_pass` on 2d's
rebuilt easy rung at `FIELD_SEED`, construction 2, asserting **exactly**:

| quantity | committed value | source |
|---|---|---|
| `warm_per_point` | **24.463541666666668** | `phase2d-difficulty-rung-report.json` |
| `warm_ok_total` | **9394** | same |

**`src/` must still be unchanged since the anchor** — `git log f409b7f..HEAD -- src/` — and the
harness records the answer rather than assuming it.

---

## G9 — CONSTRAINT 2: THE GEOGRAPHY IS NARROWER THAN THE FIRST HALF'S, NOT WIDER

The box is **2.125° × 2.125°** of subtropical open North Atlantic: no land, no ice, no gaps, one
regime. The first half's was 15° × 20° and its verdict already says a clean outcome histogram
there is a property of the box.

**This box is narrower still, and the verdict says so in its head rather than its footnotes.**
Real coherence varies with the ocean; a saving measured here is **a saving there**. The Southern
Ocean, a shelf, a western boundary current and the Rossby transition are all unmeasured, and a
single box cannot speak for them.

---

## G10 — THE HORN, NAMED IN ADVANCE, AND THE TWO SIGNS IT PREDICTS

At 58.89 cold iterations the optimizer has further to travel than on any fixture here. Two
readings follow and they are not the same:

- **a near start helps MORE** — the saving is large and selection agreement stays high. Warm-starting
  buys **time and not bias** on real data, which is the sentence 2d earned on a simulated field.
- **the surface is rough enough that a near start lands in a DIFFERENT BASIN** — the saving is also
  large, and **selection agreement falls.** The iterations are saved by converging somewhere else,
  and the saving is partly bought with bias.

**BOTH PREDICT A LARGE SAVING. THEY DIFFER ONLY IN THE AGREEMENT READING**, which is why the
agreement reading is not a secondary metric here — it is the discriminator, and a run that reported
only the saving could not tell the two apart.

**AND `warm − random` IS ORTHOGONAL TO BOTH.** A near start and a distant converged start can each
land in a different basin; what separates them is whether *proximity* buys anything beyond *being
converged*. That is the 12 points, and it is the question this half exists for.
