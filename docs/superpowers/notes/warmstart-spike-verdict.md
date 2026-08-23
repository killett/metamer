# The warm-start spike — verdict

**2c Task 0. Written 2026-08-23.** The pre-flight is in
[`phase2c-preflight.md`](phase2c-preflight.md); the predictions were committed before any arm
ran, in [`warmstart-spike-predictions.json`](warmstart-spike-predictions.json); the instrument is
[`warmstart-spike-harness.py`](warmstart-spike-harness.py) and the points are
[`warmstart-spike-measured.jsonl`](warmstart-spike-measured.jsonl),
[`warmstart-spike-n384-measured.jsonl`](warmstart-spike-n384-measured.jsonl) and
[`warmstart-spike-n630-measured.jsonl`](warmstart-spike-n630-measured.jsonl).

> ## THE VERDICT, TAKEN AT PRODUCTION LENGTH 2026-08-23: **WARM-STARTING PAYS AND IS NOT DROPPED.** At `N = 630` it saves **42.28% ± 0.94%** of iterations and **45.90%** of wall clock, against §11.2's **30%** threshold. The saving runs **7.80 / 31.73 / 42.28%** at `N = 96 / 384 / 630` — **it is a function of record length, and the primary fixture measured the wrong regime.**

> ## AND THE SCOPE QUESTION IS NOT THE ONE ANYONE EXPECTED. AT `N = 630` THE **RANDOM-DISTANT** ARM ALSO CLEARS THE THRESHOLD, AT **30.28% ± 1.02%**. **THE TWO-PASS GEOMETRY IS WORTH 12.00 POINTS ON TOP OF IT, NOT THE WHOLE 42.** Most of what warm-starting buys is *"any converged `θ̂` beats the moment ladder"*, which needs **no coarse grid, no stride in `fit_hash`, no spiral and no barrier.**

**THE PROVISIONAL "DROP IT" IS OVERTURNED, AND BY THE RULE THAT WAS WRITTEN BEFORE THE EVIDENCE
ARRIVED.** Everything below about the primary fixture stands as a measurement at `N = 96`; what
does **not** stand is reading it as a statement about production. **P9 existed to catch exactly
this, and it did.**

> **AND THE CEILING GOVERNS HOW ANY OF IT IS QUOTED.** Starting each point from **its own**
> converged `θ̂` saves **93.97 / 93.49 / 94.53%** of iterations at the three lengths — **a spread
> of 1.0 point while the mechanism moved 34.5.** The ceiling does not move and the neighbour's
> saving does, so what changes with record length is **how good a neighbour is**, not what the
> machinery can deliver. That is a statement about the field, and it is why the ceiling arm was
> worth its cost.

## The decision rule for P9, stated before the N = 384 fixture reported — and what it now compels

Recorded in advance so the second fixture cannot be read to suit the first.

| P9 lands | what it means | the verdict |
|---|---|---|
| **at or above 30%** | the saving depends on record length, and the primary fixture at `N = 96` does **not** describe production at `N = 630`. The headline was measured at the wrong length | **the verdict is re-taken**, at production length, before anything rests on it |
| **anywhere below 30%** | the verdict stands | **stands** — and the size of the move is **itself worth stating**, because it tells the next reader which regime the null covers |

**A move of more than 10 points that stays below 30% does not overturn the verdict**; it
narrows the claim to the record lengths measured, and that narrowing is part of the finding
rather than a caveat on it.

**IT LANDED IN THE FIRST ROW. P9 IS REFUTED BY 23.93 POINTS AGAINST A 10-POINT CLAUSE, AND THE
RE-TAKE IS COMPELLED RATHER THAN CHOSEN.** The rule was written to stop the second fixture being
read to suit the first, and it did its job in the direction I did not expect: I predicted the
saving was a property of the parameter space and therefore flat in `N`, and it is not.

## The second fixture, `N = 384` — the one that changed the answer

12 × 12 points, `N = 384` monthly, stride 4, 135 measured points, **0 excluded**, one repeat
(iterations are deterministic, so one repeat answers P9; the wall clock below therefore has **no
error bar** and is a single reading).

| arm | pooled, `N = 96` | pooled, `N = 384` | move |
|---|---|---|---|
| `self` — the ceiling | +93.97% ± 0.16% | **+93.49% ± 0.18%** | **−0.5 points — flat** |
| `warm` — the mechanism | +7.80% ± 0.77% | **+31.73% ± 0.99%** | **+23.9 points** |
| `random` — distant source | −2.25% ± 0.91% | **+18.27% ± 1.03%** | **+20.5 points** |

Per candidate at `N = 384`: `white` **+13.77%**, `m12+white` **+31.07%**, `m32+white`
**+38.15%** — P3's ordering holds and every rung has risen. **Wall clock, single reading:** cold
**1488.09 s**, warm **1073.53 s** — **+27.86%**, where at `N = 96` it was **−1.19%**. `random`
**+20.15%**. `self` **+69.13%**.

**THE CEILING BEING FLAT WHILE THE MECHANISM RISES IS THE INFORMATIVE PART.** If both had risen,
the effect would be about `N` making every warm start cheaper — an instrument story. The ceiling
does not move at all (−0.5 points across a ×4 lever), so what improved is **the neighbour's value
as a source**. At longer records the optimum is better determined relative to the basin it sits
in, and a fit two cells away lands inside it.

**AND THE `N = 96` TAIL IS FIXTURE-SPECIFIC, WHICH CORRECTS THIS DOCUMENT'S OWN EARLIER
READING.** At `N = 384` warm and cold agree at **100.00%** on selection, **100.00%** at
`|Δℓ| < 0.01` with a **maximum of 8.95e-07**, and **100.00%** within 0.25 SE with a maximum
parameter distance of **0.001**. **There is no tail at all.** The ~2% of cells landing elsewhere
at `N = 96` is a property of that fixture's short records, not of warm-starting — so it is
**evidence about `N = 96`**, and the paragraph below that reads it as part of the case against
the mechanism is **wrong and is struck there**.

**P5's SHAPE SURVIVES AND ITS SIGN DOES NOT.** Cross-regime **+2.92% ± 2.89%** against
same-regime **+34.95% ± 0.82%** — still **32 points** below, so the boundary is still where the
mechanism is worth least, but at `N = 384` it no longer actively harms. **(i2c) stands as a rule
and its worked magnitude is now fixture-dependent**, which is recorded rather than smoothed.

## The re-take at `N = 630` — the fixture the verdict rests on

12 × 12 points, `N = 630` monthly (production's record length), stride 4, 135 measured points,
**0 excluded**, one repeat. Coarse points **100% OK**; the OK filter **never** changed a source.
Wall clock is a single reading and has no error bar; the iteration columns are deterministic.

| arm | `N = 96` | `N = 384` | `N = 630` | wall clock at `N = 630` |
|---|---|---|---|---|
| `self` — the ceiling | +93.97% ± 0.16% | +93.49% ± 0.18% | **+94.53% ± 0.14%** | **+74.75%** |
| `warm` — the mechanism | +7.80% ± 0.77% | +31.73% ± 0.99% | **+42.28% ± 0.94%** | **+45.90%** |
| `random` — distant source | −2.25% ± 0.91% | +18.27% ± 1.03% | **+30.28% ± 1.02%** | **+31.03%** |

Per candidate at `N = 630`: `white` **+34.78%**, `m12+white` **+40.95%**, `m32+white`
**+46.56%** — P3's ordering holds at all three lengths and every rung has risen again.

**THE CURVE HAS NOT SATURATED.** 96 → 384 is a ×4 lever and gained 23.93 points; 384 → 630 is a
×1.64 lever and gained 10.55. **Three points, one instrument, one lever** — and the third point
is what distinguishes a rising curve from a flattening one, which two points could not.
**No value beyond `N = 630` is claimed**, and none is needed: 630 is production.

**AND THE CEILING IS FLAT ACROSS ALL THREE** — 93.97 / 93.49 / 94.53, a spread of 1.0 point
against the mechanism's 34.5. **What record length changes is how good a neighbour is, not what
the machinery can deliver.** That is the (i2b) reading, and it survived a third fixture.

### The decomposition, which is the finding that changes 2c's shape

| step | iteration saving | what it costs to build |
|---|---|---|
| moment ladder → **any converged `θ̂`** | **+30.28%** | a start, from anywhere. No geometry |
| → **a NEAR converged `θ̂`** | **+12.00 more** | the coarse grid, the stride inside `fit_hash`, the spiral, the tie-break, the barrier, `/warmstart/` |
| → **the point's OWN converged `θ̂`** | **+52.25 more** | unreachable by construction |

**THE EXPENSIVE HALF OF §11.1 BUYS THE SMALLER HALF OF THE BENEFIT.** The two-pass geometry is
real — P4 is refuted at all three lengths and proximity pays 10.05 / 13.46 / 12.00 points — but
**§11.2's threshold is already cleared without it.** A design that warm-starts from any prior
converged fit clears the bar at 30.28% and skips the cascade, the `fit_hash` boundary and the
barrier entirely. **That is a design question this spike has opened and has not answered**, and
it belongs to the brainstorm rather than to this verdict.

### The agreement margin, and it is the thing to watch

| | `N = 96` | `N = 384` | `N = 630` |
|---|---|---|---|
| selection agreement, `warm` | 95.00% | 100.00% | **90.37% (122/135)** |
| selection agreement, `random` | 97.08% | 100.00% | **92.59% (125/135)** |
| `\|Δℓ\| < 0.01`, `warm` | 97.90% | 100.00% | **97.27%** |
| max `\|Δℓ\|`, `warm` | 8.31 | 8.95e-07 | **204.0** |
| max parameter distance, `warm` | 10.2 SE | 0.001 | **154 SE** |

**PERMITTED OUTCOME 3 IS NOT TRIGGERED, AND THE MARGIN IS ONE GRID CELL.** The pre-agreed trigger
was *"selection agreement below 90%, or `|Δℓ| > 0.01` at more than 10%"*. Measured: **90.37%** and
**2.73%**. Neither fires. **But 90.37% is 122 of 135, and 121 of 135 is 89.63%** — one more
disagreeing cell and the rule would have said *report and stop*. **That is recorded as a pass by
0.37 of a point, not as a pass.**

**AND THE DISAGREEMENT IS NOT MONOTONE IN `N`, WHICH MEANS IT IS NOT SIMPLY A LENGTH EFFECT.** It
is worst at `N = 630`, absent at `N = 384`, and mild at `N = 96`. **No shape is claimed for it
from three points** — that is this project's own standing refusal — but it is the quantity the
hysteresis audit exists to measure, and it is at its worst at production length.

**ONE READING POINTS THE WRONG WAY FOR THE MECHANISM AND IS REPORTED BECAUSE OF THAT.** At
`N = 630` the **near** start disagrees with cold **more** than the **distant** start does — 122
against 125 of 135. That is the direction §11.2 predicts for hysteresis: initializing from a
neighbour biases toward the neighbour's answer. **Three cells is not evidence**, and it is
written here as a hypothesis for the audit to test rather than as a finding.

## The primary fixture

16 × 16 points, `N = 96` monthly, stride 4, 240 measured points, **0 excluded**, three repeats.
Candidate set `[white]`, `[matern12 + white]`, `[matern32 + white]` — **lint-clean by
construction**, so parameter disagreement between the arms cannot be label switching in
hysteresis' clothes. Coarse points **100% OK**, and the OK filter **never** changed a source, so
the spiral is defensive rather than load-bearing. **Every arm returned bit-identical `n_iter` and
`loglik` across all three repeats**, which is a free exercise of §11.3's determinism claim along
the warm-start path — the one path §11.3 has never had a consumer for.

| arm | pooled | `white` | `m12+white` | `m32+white` | same-regime | cross-regime |
|---|---|---|---|---|---|---|
| `self` — the ceiling | **+93.97% ± 0.16%** | +97.78 | +93.48 | +92.97 | +93.91 | +94.64 |
| `warm` — the mechanism | **+7.80% ± 0.77%** | +2.31 | +6.31 | +11.64 | +9.75 | **−16.27** |
| `random` — distant source | **−2.25% ± 0.91%** | −4.16 | −2.13 | −1.60 | −2.04 | −4.76 |

**Wall clock**, mean of three interleaved repeats with threads pinned: cold **474.01 ± 12.42 s**,
warm **479.64 ± 25.29 s** — a **−1.19%** "saving", which is inside the noise and is not a saving.
`random` **−8.04%**. `self` **+62.18%**.

## The three things this establishes beyond the number

**1. THE GEOMETRY IS REAL, AND HOW FAR IT GETS YOU DEPENDS ON RECORD LENGTH.**
A distant converged `θ̂` is **worse than the moment ladder** at `N = 96` (−2.25%); a nearby one is
better (+7.80%). **Proximity is worth 10.05 points there** — the refutation of P4, the horn I
doubted, by 0.05 of a point against its own clause. **At `N = 384` proximity is worth 13.46
points** (31.73 against 18.27), so the geometry's contribution is roughly stable while the
overall level is not. **The two-pass geometry buys something real at both lengths; what changes
is whether the total clears 30%.**

**2. THE REGIME BOUNDARY IS ALWAYS THE WORST STRATUM, AND §11.1 HAS NO POLICY FOR IT.**
At `N = 96`, same-regime **+9.75%** against cross-regime **−16.27%** — a 26-point swing onto the
wrong side of zero. At `N = 384`, **+34.95%** against **+2.92%** — 32 points, and no longer
negative. **The sign is fixture-dependent; the ordering is not, and the gap widens with `N`.** The
mechanism is worth least exactly where spectral shape changes, which is where the scientific
interest is and where §11.2 says hysteresis concentrates. **This matters under a PASSING pooled
number, not only under a failing one:** at 31.73% pooled the boundary stratum sits at 2.92%, so a
design that ships warm-starting ships a mechanism that does nothing at its most interesting
points — and §11.1's two-pass warm start **has no notion of regime boundaries at all.** Promoted
as (i2c); the rule stands and its worked magnitude is now known to move with the fixture.

**3. ~~THE ~2% TAIL IS EVIDENCE FOR THE DECISION~~ — STRUCK 2026-08-23 BY THE SECOND FIXTURE.**
P6 passed at its pre-agreed thresholds on both fixtures, so permitted outcome 3 was never
triggered and that was fixed in advance rather than judged after. **But the tail is a property of
`N = 96`, not of warm-starting.** At `N = 96`: selection agreement 95.00%, `|Δℓ| < 0.01` at
97.90%, max `|Δℓ|` **8.31**, max parameter distance **10.2 SE**. At `N = 384`: **100.00%,
100.00%, max `|Δℓ|` 8.95e-07, max distance 0.001.** **The tail vanishes entirely.** Reading it as
part of the case against the mechanism was wrong, and it is struck here rather than quietly
dropped: **at longer records warm and cold land in the same place, to seven decimal places.**

## The predictions

| # | claim | outcome |
|---|---|---|
| P1 | the ceiling arm collapses iterations by ≥ 70% | **HELD at both fixtures** — +93.97% and +93.49% pooled, ≥ 89.63% on every candidate |
| P2 | pooled saving positive and under 30%, ~18% | **HELD at `N = 96`** (7.80%, low in its 5–30% band) and **REFUTED at `N = 384`** (31.73%). The prediction had no `N` clause, which is the defect P9 caught |
| P3 | saving ordered by parameter count, `white` under 5% | **HELD on ordering at both** — 2.31 / 6.31 / 11.64 and 13.77 / 31.07 / 38.15. **The `white < 5%` clause is REFUTED at `N = 384`** (13.77%) |
| P4 | warm and random differ by < 5 points | **REFUTED at both** — 10.05 points at `N = 96`, by 0.05 over its own clause, and 13.46 at `N = 384`. **Proximity pays, at both lengths** |
| P5 | cross-regime ≥ 10 points below same-regime | **HELD at both** — 26 points below and negative at `N = 96`, 32 points below and positive at `N = 384` |
| P6 | warm and cold land at the same optimum | **HELD at both**, and the `N = 96` tail **does not survive**: `N = 384` agrees 100.00% with max `\|Δℓ\|` 8.95e-07 |
| P7 | wall-clock saving 0.5–1.0× the iteration saving | **REFUTED at `N = 96`** (−1.19%, indistinguishable from zero) and **HELD at `N = 384`** (27.86% against 31.73% = 0.88×). The band was right about the mechanism and wrong about the fixture |
| P8 | the spiral is defensive | **HELD at both** — the OK filter changed the source at 0.000 of cells, coarse points 100% OK. Its metric was **mis-specified before the run and corrected in the open**: "steps beyond radius 0" is true by construction |
| P9 | the saving is within 10 points at `N = 384` | **REFUTED BY 23.93 POINTS, AND IT IS THE PREDICTION THAT MATTERED.** It compelled the `N = 630` re-take, which overturned the provisional verdict. Every number from the primary fixture is conditional on it |

**AND THE THIRD FIXTURE IS WHERE EVERY PREDICTION IS FINALLY READ.** At `N = 630`: P1 held
(+94.53%), P2's 30% clause is **refuted** (42.28%), P3's ordering held and its `white < 5%` clause
is refuted again (34.78%), P4 is refuted a third time (12.00 points), P5 held (34 points below),
P6 held **by 0.37 of a point**, P7 held (45.90% against 42.28% = 1.09×, its first reading above
1.0), P8 held.

**FIVE OF THE NINE CHANGED THEIR VERDICT BETWEEN THE TWO SHORTER FIXTURES.** P2, P3's threshold clause,
P6's tail and P7 all read one way at `N = 96` and the other way at `N = 384`. **A single-fixture
spike would have produced a confident, documented, wrong recommendation** — and it would have
been wrong in the expensive direction, because "drop it" is the outcome nobody re-opens.

## What 2c becomes — resolved 2026-08-23 by the re-take

**WARM-STARTING IS BUILT. PASS 1 KEEPS ALL FIVE JOBS.** The `N = 630` re-take clears §11.2's
threshold on both readings — 42.28% of iterations, 45.90% of wall clock — and P6's pre-agreed
thresholds hold, so permitted outcome 1 is met and the mechanism proceeds.

**FOUR THINGS ARE OWED, AND THEY ARE WRITTEN HERE SO THEY ARE NOT REDISCOVERED IN THE PLAN.**

1. **The scope question the decomposition opened.** `random` alone clears the threshold at
   **30.28%**; the geometry adds **12.00**. **Whether §11.1's full two-pass machinery is the right
   purchase for those 12 points is a design decision that has never been taken with numbers in
   front of it**, and it must be taken before the plan is written — not settled by the fact that
   §11.1 already describes the expensive version.
2. **`fit`'s `x0` is call-level all-or-nothing** (`fit.py:227`), so §11.3's *"on exhaustion fall
   back to the moment-init ladder with the rung recorded as such"* has no expressible
   implementation. **A per-cell warm-start selector is a signature change nothing in the plan
   owns.**
3. **The regime boundary has no policy.** Cross-regime is the worst stratum at every length —
   −16.27 / +2.92 / **+11.40%** against same-regime +9.75 / +34.95 / **+45.62%**, a gap that
   **widens** with `N` to 34 points. §11.1's two-pass warm start has no notion of regime
   boundaries at all.
4. **The hysteresis audit is now mandatory in fact, not only in §11.2's wording**, and it has a
   named first hypothesis: at `N = 630` the near start disagreed with cold more than the distant
   one did.

### What the "drop it" branch would have meant, kept because the reasoning is the transferable part

**Under a "drop it" outcome, this would have retired one of pass 1's five jobs and not pass 1.**
§11.1 lists
the coarse subsample as serving the warm-start source, the calibration-tile RSS measurement, the
early-abort evaluation, the **cold** reference for the hysteresis audit, and the default
`/detail/` subsample. **Only the first would be decided.** Whether the remaining four justify pass
1 on their own — and whether §11.4's claim that pass 1 doubles as the calibration tile survives,
which 2b already flagged as questionable — **is the next scope question either way, and is
separate from this verdict.**

**And under "drop it" the hysteresis audit's subject goes with the mechanism.** §11.2 exists
because warm-starting biases each point toward its neighbour's answer; with no warm-starting
there is no inter-point coupling to audit, and cold is what ships.

**UNDER A "BUILD IT" OUTCOME, THREE THINGS ARE ALREADY OWED AND ARE WRITTEN DOWN HERE SO THEY ARE
NOT REDISCOVERED.** `fit`'s `x0` is **call-level all-or-nothing** (`fit.py:227`), so §11.3's
spiral fallback needs a **per-cell warm-start selector** that no plan currently owns. The **regime
boundary has no policy** and is the stratum where the mechanism is worth least at both fixtures.
And the **hysteresis audit becomes mandatory rather than hypothetical**, with §11.2's four
metrics and its stratification — on a candidate set the lint has cleared, which this spike had by
construction and production will not.

## What is NOT established

Stated plainly rather than generalized:

- **One machine.** The mini PC, `threadpool_limits(1)`, one BLAS.
- **Three record lengths**, `N = 96`, `384` and `630`, the last of which is production's. **The
  saving moves 34.48 points across them and has not saturated**, so the number is a function of
  record length and not a constant. **No value beyond `N = 630` is claimed, and no value between
  the measured points is interpolated.** Two points would have determined a line and this project
  has already recorded, twice, what a two-point line is worth — the 240 B/candidate slope through
  two `M` values had zero residual and had never tested linearity at all. **The third point is
  why the verdict is a verdict.**
- **Two grid sizes** — 16 × 16 at `N = 96`, 12 × 12 at both `N = 384` and `N = 630`. The stride
  and therefore the source-distance distribution are identical everywhere, the two longer fixtures
  share a grid, and the same-regime strata move with the pooled figures throughout, so grid size
  does not explain the effect. **Recorded because it is a difference the comparison did not
  control.**
- **One repeat at `N = 384` and at `N = 630`**, so their wall-clock columns are single readings
  with no error bars. The iteration columns are deterministic and need none; every arm of the
  three-repeat primary returned bit-identical `n_iter` and `loglik`.
- **The agreement margin is not a measured trend.** Selection agreement runs 95.00 / 100.00 /
  90.37% across the three lengths, which is not monotone. **No shape is claimed from three
  points**, and the hysteresis audit is what would establish one.
- **One candidate set**, three candidates, deliberately lint-clean. A set with exchangeable
  same-kind terms was excluded by construction and is not covered.
- **A simulated field.** The parameters vary smoothly by construction and the boundary is sharp
  by construction. **The spatial coherence of real altimetry optima has not been measured**, and
  a field whose optima are more coherent than this one's could give a different answer. That is
  the one measurement that would properly overturn this verdict, and it needs real data.
- **Nothing about the barrier's cost at 10⁷ points**, about label switching, or about pass 1 as
  the calibration tile.

## The re-take: what it cost, and the instrument check it carried

**`N = 630`, 12 × 12, stride 4, one repeat**, run 2026-08-23 in **3 h 25 min** — pass 1 198 s,
prep 2984 s, cold 2792 s, warm 1511 s, self 705 s, random 1926 s. Same harness, same candidate
set, same rule; only the record length moved.

**AND THE HARNESS WAS CHECKED AGAINST THE RUN IT LAUNCHED.** `ruff-format` and `mypy` asked for
changes after the primary fixture was already running, so the committed file differed from the
launched one by formatting, a `TextIO` annotation, two `int()` narrowings and an `if`/`elif`
rewrite of `matern_cov`. **The committed harness reproduces the launched run's pass 1
bit-identically** — 471 iterations and a `loglik` sum of `-4866.477960533184`, exact — so the
published numbers and the committed instrument are the same instrument. **Checked rather than
argued**, which is what this project's own rule about post-hoc edits requires.
