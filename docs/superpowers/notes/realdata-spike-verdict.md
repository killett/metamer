# The real-data spike, first half — verdict (2026-09-07)

> ## THE SENTENCE A READER CAN CARRY
>
> **Real altimetry fits are HARDER than every fixture this project has ever measured — 58.89 cold
> iterations per point at `N = 396` against the benchmark's 42.08 at `N = 630` — so the warm-start
> saving is not bounded near zero, and the coherence question is live rather than moot. And one in
> ten real cells returns `DEGENERATE_HESSIAN` where the simulated field returns one in 1152.**
>
> Everything below supports that sentence. **Nothing here measures a saving.**

**THE RECORD IS [`realdata-spike-report.json`](realdata-spike-report.json)**, the predictions were
committed before the run in [`realdata-spike-predictions.json`](realdata-spike-predictions.json),
the pre-flight is [`realdata-spike-preflight.md`](realdata-spike-preflight.md), and the two
instruments are [`realdata-spike-fetch.py`](realdata-spike-fetch.py) and
[`realdata-spike-harness.py`](realdata-spike-harness.py). **None of them is restated here.**

---

## 1. THE CONTROL REPRODUCED THE ANCHOR EXACTLY, AND THAT IS WHAT MAKES THE REST READABLE

| | measured | expected | difference |
|---|---|---|---|
| cold iterations per point | **42.080729166666664** | 42.080729166666664 | **0.0** |
| OK-only per point | **42.0390625** | 42.0390625 | **0.0** |

**NOT A BAND — AN EQUALITY, AND IT HELD.** 384 points, 1152 cells, 16 159 iterations, two days
after the anchor was measured and on a tree whose `src/` has not moved.

**THIS IS THE HALF OF THE SPIKE THAT COULD FAIL.** A low real reading is exactly what a silently
broken pipeline produces, and every one of this project's fill-value findings says the two are the
same bytes. **The equality is what says the instrument was not broken, and it also says the
environment was not** — which is the return on refusing to `pixi add` a fetch dependency, since
that would have re-solved the lock this equality is asserted under.

---

## 2. THE READINGS

**All three arms are the shipped `batch.run.run` followed by `bench.fields.iteration_count`, at
`M = 3` on the shipped candidate set, `max_iter = 200`, one thread, `KalmanEngine`, ML.**

| arm | `N` | points | **per point** | OK-only per point | per cell | OK fraction | at cap |
|---|---|---|---|---|---|---|---|
| `control` — 2d easy rung, construction 2 | 630 | 384 | **42.0807** | 42.0391 | 14.0269 | 0.9991 | 0 |
| `real_ct` — DUACS, `constant + trend` | 396 | 300 | **58.8933** | 50.1200 | 19.6311 | 0.8989 | 0 |
| `real_ctas` — DUACS, `+ annual + semiannual` | 396 | 300 | **65.4800** | 59.0433 | 21.8267 | 0.9322 | 0 |

**Real difficulty against the same instrument: 1.40× the anchor on the all-cells reading and 1.19×
on the OK-only one — at a record length 37% SHORTER.** Against 2d's signal-free construction
(24.3776) it is 2.42×.

**And against 2c's record-length ladder it is further still, though that comparison crosses
instruments** (j5): the ladder's 28.27 / 35.32 / 40.79 at `N = 96 / 384 / 630` came from 2c's own
optimizer path. Real data at `N = 396` returns **58.89** where the ladder's nearest measured rung
says **35.32**. **The ladder rises with `N`; the real point sits above its top end while being
nearer its middle in record length.**

> **SO THE PLACEMENT IS AN EXTRAPOLATION AND IS REPORTED AS ONE.** P2 predicted a band of
> [28, 55] and the reading is **outside it, on the high side** — the direction the predictions
> file named as the surprise, because the whole record was braced for the other one. Every anchor
> this project owns now sits **below** the subject, so nothing here is bracketed and no
> interpolation is available.

---

## 3. THE SIX PREDICTIONS, SCORED

| # | subject | verdict |
|---|---|---|
| **P1** | the control reproduces the anchor exactly | **HELD**, difference 0.0 |
| **P2** | `real_ct` in [28, 55] per point | **REFUTED, high** — 58.8933 |
| **P3** | `real_ctas < real_ct` | **REFUTED, reversed** — 65.48 against 58.89 |
| **P4** | OK ≥ 0.95 and all-cells minus OK-only < 1.0 | **REFUTED on both** — 0.8989 and 8.7733 |
| **P5** | median `κ` below `2²⁶` **and** `DEGENERATE_HESSIAN` under 5% | **SPLIT** — median held, the fraction did not |
| **P6** | the cost bands | **HELD on all three arms** — 2.92 h / 1.57 h / 1.86 h |

**FOUR OF SIX MOVED, AND THE TWO THAT HELD ARE THE TWO THAT HAD TO.** P1 is the instrument and P6
is the budget; had either failed, none of the rest would have been readable.

### P3 REVERSED, AND THE REVERSAL IS THE SAFE DIRECTION

`constant + trend` is misspecified against monthly sea level and the arm was built because that
misspecification could inflate difficulty **toward the answer this measurement exists to doubt**.

**It deflates it.** The correctly-specified model takes **6.59 more iterations per point** (8.92
more OK-only), and it also converges **more cleanly** — OK fraction 0.9322 against 0.8989, and 60
degenerate cells against 91.

> **SO THE HEADLINE READING IS IF ANYTHING AN UNDERSTATEMENT.** The contamination the arm was
> built to catch runs the other way, and the honest statement of real cold difficulty under a model
> anyone would actually fit is **65.48**, not 58.89. **The number compared against the anchors
> stays 58.89**, because that is the model every anchor used — but a reader taking one number away
> should know the better-specified one is larger.

**THE MAGNITUDE WAS INSIDE THE PREDICTED GAP BAND AND THE SIGN WAS NOT**, which is (i11) paying
for itself: a one-sided clause would have called this a miss and moved on.

### P4 REFUTED — AND THE MECHANISM ITS CLAUSE NAMED IS ABSENT

The clause read: *"capped and failed cells are carrying the headline number — a capped cell
contributes `max_iter = 200`."* **Zero cells hit the cap, on any arm.**

The gap is real and its cause is the other half of the clause:

| arm | iterations per **OK** cell | iterations per **non-OK** cell | ratio |
|---|---|---|---|
| `control` | 14.03 | 16.00 (one cell) | 1.14 |
| `real_ct` | 18.59 | **28.92** | **1.56** |
| `real_ctas` | 21.11 | **31.66** | **1.50** |

**A degenerate-Hessian cell's count is real work that ended in a conditioning verdict, not a
cap reading**, and the two would have been quoted identically under the clause as written. **The
clause was right that non-OK cells carry the headline and wrong about which ones and why**, which
is (a4) applied to one's own refutation clause: a correction arrives with the authority of the
thing it corrects.

### P5 SPLIT — AND THE CONDITIONING IS THE FINDING NOBODY ASKED FOR

| arm | `κ` median | 90th | 99th | max | cells above `2²⁶` | `DEGENERATE_HESSIAN`, store |
|---|---|---|---|---|---|---|
| `control` | **22.5** | 75.8 | 113 | **135** | 0 of 144 | **1 of 1152 (0.09%)** |
| `real_ct` | 2.02e6 | 3.13e7 | 2.69e8 | **4.02e8** | 7 of 142 | **91 of 900 (10.1%)** |
| `real_ctas` | 3.21e5 | 3.51e7 | 1.06e8 | **5.68e8** | 5 of 135 | **60 of 900 (6.7%)** |

**FIVE ORDERS OF MAGNITUDE BETWEEN THE SIMULATED FIELD AND THE OCEAN**, on the median. The
predicted median held on both real arms; the predicted degenerate fraction did not, by 2× and
1.3×.

> ## AND IT SHARPENS (h3) RATHER THAN OVERTURNING IT
>
> D9 cuts the audit's `κ` strata at `2²⁶` and `2⁵²`, and (h3) established that
> `optimize.HESSIAN_COND_LIMIT` **is** `2²⁶`, so the taxonomy refuses `OK` above it and three of
> four bins were unreachable before any data landed. **That is still true.** The cells this run
> found above `2²⁶` are exactly the cells that came back `DEGENERATE_HESSIAN`.
>
> **WHAT CHANGED IS THE SIZE OF THE POPULATION BEING FILTERED AWAY: 0.09% on the simulated field,
> 10.1% on the ocean — a hundredfold.** §11.2's audit compares on the **both-OK intersection**, so
> on real data roughly a fifth of cells leave the comparison before it starts, and which fifth is
> not random: it is the ill-conditioned geography §11.2 says hysteresis concentrates in.
>
> **THE AUDIT'S SUBJECT IS THEREFORE NARROWER ON REAL DATA THAN ANY FIXTURE HAS SHOWN**, and the
> outcome-flip reporting D9 specifies stops being a formality. Recorded against the audit, not
> against this spike.

**`TRUST_RADIUS_COLLAPSED` APPEARED ONCE**, on `real_ctas`. One cell of 900, and it is the first
time this project has seen that code outside a constructed fixture.

### P6 HELD, AND ONE STATED EXPECTATION INSIDE IT WAS WRONG

The bands held. **The `known_bias` note attached to them did not**, and it is recorded as wrong
rather than absorbed — the handoff's rule for a predicted precision.

It said: `unique_dt = 6` on the real axis against `1` on every synthetic fixture means `F` and `Q`
are built six times per series per iteration, so **the real arms' seconds should run high** against
a naive `N`-scaling.

| arm | `N` | seconds per iteration |
|---|---|---|
| `control` | 630 | **0.6511** |
| `real_ct` | 396 | **0.3199** |
| `real_ctas` | 396 | 0.3403 |

Linear in `N`, the control's rate predicts **0.409** at `N = 396`. The measurement is **0.320 —
22% FASTER**, not slower. **The amortization argument pointed the wrong way and the gap is not
attributed here**; the six-timestep rebuild is evidently small against the filter recursion, and
what else differs between the two workloads has not been decomposed. **A rate whose direction was
predicted wrongly is a rate whose mechanism is not understood**, and it is left that way rather
than given a story.

---

## 4. WHAT THIS DECIDES, AND WHAT IT DOES NOT

**THE DECISION CLAUSE FIRES AT `≥ 45`:** real fits are harder than any fixture measured here.

> ## THE ORDERING'S PURPOSE IS DISCHARGED, AND THE ANSWER IS "PROCEED"
>
> The first half existed to answer one question cheaply: *"if real fits converge in ~15 iterations
> the saving is bounded near zero and the coherence question is moot."*
>
> **They converge in 58.89. The saving is not bounded near zero. The coherence half is live.**

**AND THE BOUND IT LIFTS IS ONLY HALF THE MECHANISM.** D1's amendment reattributed 2c's 42.28%:
the `random` arm — a distant converged optimum carrying **no proximity information at all** —
recovered **+30.28%**, so roughly **30 points are cold-start difficulty and 12.00 points are
proximity**. This spike measures difficulty and says the 30-point component has more to work with
on real data than on any fixture, not less.

**THE 12 POINTS ARE STILL UNMEASURED, AND THEY ARE WHAT THE SHIPPED MECHANISM EXISTS TO BUY.** The
coarse grid, the barrier, the spiral, the stride inside `fit_hash` and the `/warmstart/` group all
deliver **proximity**. Whether real optima are spatially coherent enough to deliver it is the
second half, and **nothing here bears on it.**

**WHAT IS EXPLICITLY NOT ESTABLISHED:**

- **No saving is measured.** A cold iteration count is a bound, and this one lifts a bound rather
  than establishing a benefit.
- **2d's null has not been shown to transfer.** It was a null about warm-versus-cold *selection* on
  a simulated field; nothing here fits a warm start at all.
- **One box is not the ocean.** 20–34 °N, 40–21 °W is subtropical open water with **no land, no
  ice and no gaps**, chosen so the difficulty reading carried no mask confound. That choice makes
  the outcome histogram narrower than a global run's: `NOT_ATTEMPTED` is unreachable here by
  construction, so **a clean histogram in this box is not evidence that a global run is clean** —
  and the 10.1% degenerate rate was measured in the *easiest* geography available.
- **`N = 396` is not `N = 630`**, and every same-instrument anchor is at 630. The comparison is
  made across record lengths deliberately, because 630 monthly samples is 52.5 years and satellite
  altimetry has 33.
- **The input path was renamed to run at all.** See §5.

---

## 5. THE INPUT PATH, WHICH BROKE FIRST EXACTLY AS THE BRIEF EXPECTED

**Measured twice** — on a synthetic `latitude`/`longitude` fixture and on the real DUACS store,
byte-for-byte the same traceback:

    File "src/metamer/batch/run.py", line 1094, in run
      amplification = read_amplification(handle, tiles[0])
    File "src/metamer/batch/tiling.py", line 907, in read_amplification
      read *= _chunk_points(start, stop, by_dim[dim], sizes[dim])
    KeyError: 'y'

**Stage 4a passes. No store is created. The process exits 1** — which §14.3 defines as
`COMPLETED_WITH_FAILURES`, *a run that finished with a failure rate above threshold, whose map is
written*.

> **THE TWO OPEN DEFECTS COMPOSE, AND NEITHER RECORD SAID SO.** The dimension-name defect is filed
> as *"dies in assembly without exit code 4"*; the exit-code collision is filed against 2e as
> *"harmless while 1 has no producer"*. **The first is a producer of the second**, it is reachable
> today by pointing the shipped CLI at an ordinary gridded product, and a resuming script that
> branches on 1 would resume from a crash that left nothing to resume.

**THE SPIKE DID NOT FIX IT.** It fitted a renamed copy, and the un-renamed store's failure is the
reading. Both closers — stage 4a enforces the names, or the tiling path goes positional — remain
scope decisions, and (a) remains unowned.

**AND THIS PRODUCT EXERCISES ONE OF OQ20's FREEDOMS AND NOT THE OTHER.** Its dims are
`(time, latitude, longitude)`; **both spatial axes increase.** A **decreasing latitude axis — OQ20's
first candidate, and the one that yields a plausible answer rather than an error — is still
exercised by nothing.**

**ONE FIXTURE FACT BECAME A MEASUREMENT:** `unique_dt = 6` on the real axis, through the shipped
contract, against `1` for every synthetic fixture and the spike harness. The handoff predicted the
number from the calendar; this is the first real time axis fed through stage 4a.

---

## 6. WHAT THE SECOND HALF INHERITS

- **A real fixture in the tree's reach, fetched with no credentials and no dependency**, with its
  conversion committed as an instrument and its provenance recorded.
- **A control that reproduces the benchmark anchor to zero difference**, so a later session can
  establish in under three hours that its instrument and environment are the ones these numbers
  came from.
- **A difficulty reading that lifts the bound the ordering existed to test**, and an
  arm-difference saying the reading understates the correctly-specified case.
- **A conditioning finding that belongs to the audit rather than to the spike:** the both-OK
  intersection loses a hundredfold more cells on real data than on any fixture.
- **The standing limitation, narrowed and not lifted.** *No number in this project about
  warm-STARTING comes from real altimetry* — that is still true. What is no longer true is that
  **no number about real difficulty** does.
