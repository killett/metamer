# The real-data spike, SECOND half — verdict (2026-09-10)

> ## THE SENTENCE A READER CAN CARRY
>
> **On real altimetry warm-starting saves 64.72% of cold iterations — more than 2c's 42.28% — but
> PROXIMITY contributes only 4.36 of those points against 2c's 12.00. The selected candidate
> differs at 34% of points — and NOT ONE of those is a re-ranking: every single one is a candidate
> that passed the conditioning gate in one arm and failed it in the other.**
>
> **The geometry buys 6.7% of the benefit. Warm-starting does not move a single optimum's ranking
> here; it changes which candidates survive.**
>
> Everything below supports that sentence. **It is one 2.1° box of subtropical open ocean.**

**THE RECORD IS [`realdata-spike2-report.json`](realdata-spike2-report.json)**, the predictions
were committed before the run in
[`realdata-spike2-predictions.json`](realdata-spike2-predictions.json), the pre-flight is
[`realdata-spike2-preflight.md`](realdata-spike2-preflight.md) and the harness is
[`realdata-spike2-harness.py`](realdata-spike2-harness.py). The first half is
[`realdata-spike-verdict.md`](realdata-spike-verdict.md). **None is restated here.**

---

## 1. BOTH CONTROLS HELD EXACTLY, AND ONE OF THEM IS A NEW RESULT

| control | measured | expected | difference |
|---|---|---|---|
| 2d's warm arm through the shipped `run_two_pass` | **24.463541666666668** | 24.463541666666668 | **0.0** |
| its OK-only total | **9394** | 9394 | **0** |

**THE TWO-PASS PATH HAD NEVER BEEN VERIFIED AGAINST A COMMITTED NUMBER.** The first half verified
the cold path to zero difference; this verifies the warm one, which is where a warm pipeline can be
silently wrong.

> ## AND Q7 CAME BACK BIT-IDENTICAL, WHICH NOBODY HAD CHECKED
>
> **The shipped `run_two_pass` on the real box and the in-process warm arm returned the SAME
> INTEGER: 5877 iterations, relative difference 0.0.**
>
> They differ by driver, by tiling, by store round-trip and by how the warm start reaches the
> optimizer — and they agree exactly. **So (j5) does not bite between those two paths**, and a warm
> number measured either way is comparable to one measured the other way. That licence did not
> exist before this run and it is the cheapest thing in the report.

**AND THE START REACHED THE OPTIMIZER ON EVERY ARM.** `warm` recorded `InitRung.WARM_START` on
**867 of 867** valid cells, `random` on 867 of 867, `self` on 788 of 788. Task 3's finding is that
a valid warm start is not a warm start used and that the failure is byte-identical to a correct
cold run; **the accounting is in the artifact rather than assumed.**

---

## 2. THE READINGS

289 points, `N = 396`, `M = 3`, shipped candidate set, `constant + trend`, AIC, `max_iter = 200`,
one thread. **No cell hit the cap on any arm.**

| arm | per point | per cell | saving vs cold | OK fraction | `DEGENERATE_HESSIAN` | median `κ` |
|---|---|---|---|---|---|---|
| `cold` | **57.640** | 19.213 | — | 0.9089 | 79 | 2.53e6 |
| `warm` | **20.336** | 6.779 | **+64.72%** | 0.9135 | 75 | 2.90e6 |
| `random` | **22.848** | 7.616 | **+60.36%** | 0.8916 | 94 | 3.52e6 |
| `self` | **9.415** | 3.138 | +83.67% | 0.8466 | 133 | 2.59e6 |

**COLD DIFFICULTY REPRODUCES ACROSS BOXES.** 57.640 here against **58.8933** on the first half's
15° × 20° grid — **2.1% apart on completely different water**, at the same `N` and `M`. The first
half's headline was not a property of its box.

---

## 3. THE 12 POINTS: PROXIMITY SURVIVES AT A THIRD OF ITS SIZE, AND AT A TWENTIETH OF ITS SHARE

| | 2c, simulated, `N = 630` | **this box, real, `N = 396`** |
|---|---|---|
| `warm` saving | 42.28% | **64.72%** |
| `random` saving | 30.28% | **60.36%** |
| **proximity = `warm − random`** | **12.00 points** | **4.36 points** |
| proximity as a share of the saving | **28.4%** | **6.7%** |

**ON SEPARATED CELLS ALONE IT IS 5.31 POINTS** — the 818 cells of 867 whose warm source the OK
filter did not push beyond `DISTANT_MIN`. The 49 unseparated cells drag the all-cell figure down,
as the pre-flight said they would, and the two readings are given together rather than one being
chosen.

**Q3's BAND WAS [3, 20] AND 4.36 IS INSIDE IT** — so the prediction held. **But the decision
clause's wording is generous and the verdict declines it**: *"proximity buys what 2c said it
buys"* is false. 2c said 12.00 and this is 4.36.

> ## WHAT THE MACHINERY BUYS, STATED AS THE ARCHITECTURE SEES IT
>
> The coarse grid, the barrier, the spiral, the stride inside `fit_hash` and the `/warmstart/`
> group exist to deliver **proximity**. On this box **a distant converged optimum already gets
> 60.36 of the 64.72 points — 93.3% of the benefit** — and everything the two-pass architecture
> adds is the remaining **6.7%**.
>
> **D1 DECLINED THE CHEAP VARIANT FOR A STATED REASON AND THAT REASON IS UNTOUCHED:** the cheap
> variant puts tile geometry, and therefore `--memory-budget`, inside `θ̂`. **What has changed is
> the price of that guarantee.** 2c's record already said *"the expensive half buys the smaller
> half of the benefit"*; on real data it buys a fifteenth of it.

---

## 4. THE AGREEMENT, AND THE CEILING THAT REFRAMES IT

**Q4 PREDICTED [85%, 99%] AND THE READING IS 65.74%. REFUTED, far on the low side.**

| comparison | selection agreement | disagreement |
|---|---|---|
| `self` vs cold — **the ceiling** | **84.78%** (245/289) | 15.22% |
| `warm` vs cold | **65.74%** (190/289) | **34.26%** |
| `random` vs cold | **61.59%** (178/289) | 38.41% |

**2c's WARM-VS-COLD AGREEMENT WAS 90.37%, MEASURED AGAINST A PRE-AGREED 90% STOP THAT 121 OF 135
WOULD HAVE FAILED.** This box returns **65.74%**.

> ## THE CEILING IS THE FINDING, AND WITHOUT IT THE 34% WOULD HAVE BEEN MISREAD
>
> (i2b): a reading without a ceiling is ambiguous between a weak mechanism and a weak source.
> **Starting each point at ITS OWN converged cold optimum still changes the selection at 15.22% of
> points.** D12 measured that same arm at **99.58%** on 2c's simulated field.
>
> **SO THE INSTRUMENT'S OWN FLOOR HAS MOVED FROM 0.4% TO 15.2%**, and a large part of the
> warm-vs-cold disagreement is not about proximity, not about basins, and not about the coarse
> grid: **on real data the selection is unstable under ANY warm start, including the exact
> answer.**
>
> Decomposed against that ceiling: of `warm`'s 34.26 points of disagreement, **15.22 are reachable
> with the exact optimum as the start** and **4.15 separate `warm` from the most distant start.**
>
> **A verdict quoting 34% without the ceiling beside it would have blamed the coarse grid for a
> property of the estimator.**

**AND THE SELF ARM'S OUTCOME COLUMN SAYS WHERE TO LOOK.** It has the **most** `DEGENERATE_HESSIAN`
cells of any arm — 133 against cold's 79 — the **fewest** `OK`, and it **loses 54 OK cells while
gaining none.** A fit started at its own optimum stops almost immediately (9.4 iterations against
57.6) and is classified degenerate more often. ~~**Whether that is what moves its selections is not
established by this run**~~ — **ESTABLISHED BY THE ADDENDUM IN §9: it is the whole of it.**

---

## 5. THE PREDICTIONS, SCORED

| # | subject | verdict |
|---|---|---|
| **Q1** | the control reproduces 2d's warm arm exactly | **HELD** — difference 0, total 9394 |
| **Q2** | the warm start reached the optimizer | **HELD** — 867/867, 867/867, 788/788 |
| **Q3** | `warm − random` in [3, 20] points | **HELD at the low end** — 4.36, or 5.31 separated |
| **Q4** | warm-vs-cold agreement in [85%, 99%] | **REFUTED, low** — 65.74% |
| **Q5** | `self / cold` in [0.03, 0.25] | **HELD** — 0.1633 |
| **Q6** | intersection ≥ 85%, flips symmetric | **SPLIT** — 83.6% of cells; flips +67/−63, ratio 1.06 |
| **Q7** | shipped within 1% of in-process | **HELD, and stronger** — bit-identical, 5877 = 5877 |
| **Q8** | the cost bands | **FOUR OF SIX CAME IN LOW** |

### Q6 CARRIES A UNIT SLIP IN MY OWN PREDICTIONS FILE

It predicted *"the both-OK intersection ≥ 85% **of points**"* and the harness reports **cells**:
725 of 867 = **83.6%**. **The prediction and the instrument are in different units**, which is
(a2d) — a value's unit is part of its identity — committed in a file written to be careful about
exactly that. **The point-level figure is not in the report**, and it is in the addendum.

**The flip half held cleanly**: `warm` gains 67 OK cells and loses 63, a ratio of 1.06, so
warm-starting does not systematically change convergence outcomes. **`self` is the exception and it
is strongly asymmetric** — 0 gained, 54 lost.

### Q8: THE SECONDS RAN LOW AND THE REASON IS NOT ESTABLISHED

| arm | measured | predicted band |
|---|---|---|
| control (warm) | 1.24 h | 1.2 – 2.5 ✓ |
| cold | **1.07 h** | 1.2 – 2.2 ✗ low |
| warm | **0.50 h** | 0.6 – 1.8 ✗ low |
| random | **0.53 h** | 1.0 – 2.2 ✗ low |
| self | 0.35 h | < 0.4 ✓ |
| shipped cross-check | **0.54 h** | 0.6 – 1.8 ✗ low |

Per iteration the cold arm ran **0.2303 s** against the first half's **0.3199 s** at the same `N`,
`M` and thread count. **The bands were built on the first half's rate and the rate moved 28%.**
The first half ran with a live session on the same cores and this ran overnight at a load average
of 1.94, so contention is the obvious candidate — **and it is not established here, and it is not
given a story.** (j8)'s second register: the seconds are the contaminated half, the iterations are
not, and **every iteration reading above is unaffected.**

---

## 6. THE CONDITIONING, CARRIED FORWARD

The first half found real fits ill-conditioned where the simulated field was not. This box agrees:
median `κ` of **2.53e6** on cold against the simulated field's **22.5**, and **79 of 867 cells
(9.1%)** returning `DEGENERATE_HESSIAN` against **1 in 1152**.

**AND THE ARMS DIFFER IN IT**, which is new: `random` is the worst-conditioned arm (94 degenerate,
median `κ` 3.52e6) and `self` has the most degenerate cells of all (133). **A warm start changes
how often a fit is classified degenerate**, and that is a different channel from moving an optimum.

**The both-OK intersection is 83.6% of cells for `warm` and 81.5% for `random`**, so §11.2's audit
would compare on roughly four fifths of the population here — **and the fifth that leaves is not
random**, since it is the ill-conditioned geography §11.2 says hysteresis concentrates in.

---

## 7. WHAT THIS DECIDES, AND THE GEOGRAPHY IT DECIDES IT IN

**THE 12 POINTS SURVIVE AND ARE WORTH 4.36.** Proximity is real, measurable, and about a third of
what the simulated field said. **Its share of the benefit falls from 28% to 7%**, because the
cold-start difficulty component the first half found — the 30 — is worth far more on real data than
it was on 2c's field.

**AND THE SELECTION READING IS THE ONE THAT SHOULD DECIDE ANYTHING.** The selected candidate
differs at **34% of points**, where 2c authorized the mechanism at 10% and would have stopped at
10.4%.

> ~~**A saving that moves a third of the answers is not "buying time and not bias"** — the sentence
> 2d earned on a simulated field does not transfer, and this run is why that sentence was written
> with "on a simulated field" attached.~~
>
> **STRUCK 2026-09-10 BY THE ADDENDUM, AND LEFT STANDING BECAUSE IT IS THE READING A REPORT WITHOUT
> THE DECOMPOSITION INVITES.** Not one of those points is a re-ranking. **In the sense §11.2 means
> it — the optimizer landing at a different optimum and ranking the candidates differently —
> warm-starting produced ZERO hysteresis on this box.** The sentence 2d earned transfers; what does
> not transfer is the SELECTION MAP's stability, for a different reason, through a different
> mechanism, with a different repair. See §9.

> ## THE FOUR READINGS TOGETHER, WHICH IS THE ONLY HONEST WAY TO TAKE THEM
>
> 1. **Warm-starting saves a lot** — 64.72%, more than any simulated figure.
> 2. **Almost none of that is the expensive geometry** — 6.7%, the rest is available from any
>    converged start.
> 3. **It re-ranks nothing.** Zero moves, on every arm, including the most distant start.
> 4. **It changes which candidates survive the conditioning gate**, at 34% of points — and 15 of
>    those points change under the exact optimum as the start, so a chunk of it is the estimator
>    rather than the warm start.
>
> **A reader taking (1) alone would ship the two-pass architecture. (1) and (2) would ship the
> cheap variant. (3) would call warm-starting safe. (4) is the one that needs a decision**, and it
> is not a decision about warm-starting: it is about whether a `DEGENERATE_HESSIAN` verdict that
> depends on the starting point may govern which models are selectable.

**CONSTRAINT 2, IN ITS OWN WORDS AND NOT A FOOTNOTE.** This is **2.125° × 2.125° of subtropical
open North Atlantic: no land, no ice, no gaps, one regime**, and it is *narrower* than the first
half's box. Real coherence varies with the ocean. **Whatever the saving is, it is a saving there.**
The Southern Ocean, a shelf, a western boundary current and the Rossby transition are unmeasured;
so is any geography where the coarse fits fail more often than the 3.7% they failed here.

**AND NOTHING HERE MEASURES A SMEAR WIDTH.** That is 2d's subject, it needs a regime boundary, and
this box does not have one.

---

## 8. WHAT IS OWED, AND ONE THING THIS RUN CANNOT ANSWER

**A CHANGED SELECTION IS EITHER AN OPTIMUM THAT MOVED OR A CANDIDATE THAT DROPPED OUT, AND THE
REPORT CANNOT TELL THEM APART.** It carries the per-point selection map for every arm — which is
what 2d lacked and what made 2d's own agreement figure unrecoverable — **but not the per-cell
outcome**, so *"warm selected a different candidate"* cannot be split into optimizer hysteresis
and D9's outcome flip. **Those are different quantities with different denominators and only one
is hysteresis.**

**That is the same class of defect this verdict criticises 2d for**, found in its own artifact, and
it is being closed rather than recorded: `realdata-spike2-decompose.py` re-fits the four arms,
**asserts the committed totals before reporting anything**, and writes the decomposition with the
per-cell outcomes and per-point selections beside it. Its result appends to this verdict.

---

## 9. THE ADDENDUM: EVERY DISAGREEMENT IS A DROPOUT AND NOT ONE IS A RE-RANKING

**Run 2026-09-10, `realdata-spike2-decompose.py`, and it reproduced all four arms exactly before
reporting anything** — `cold` 16658, `warm` 5877, `random` 6603, `self` 2721, every total
identical to the committed report. **That is the second exact reproduction of this measurement**
and it is what makes the decomposition a decomposition *of that run* rather than a second one.

**THE RULE, STATED BEFORE THE COUNTS.** A differing point is a **MOVE** when each arm's selected
candidate was `OK` in the other arm too — both were available, and the optimizer ranked them
differently. It is a **DROPOUT** when one arm's winner was not `OK` in the other and so could never
have been selected there.

| arm | points compared | differing | **MOVE** | DROPOUT | both unavailable |
|---|---|---|---|---|---|
| `warm` | 289 | 99 | **0** | 93 | 6 |
| `random` | 289 | 111 | **0** | 105 | 6 |
| `self` | 289 | 44 | **0** | 44 | 0 |

> ## ZERO. ON EVERY ARM, INCLUDING THE MOST DISTANT START.
>
> **Wherever warm and cold had the same candidates available, they ranked them identically — at
> every one of 289 points.** Every selection difference in this spike is a candidate that passed
> the conditioning gate in one arm and failed it in the other.

**AND A COUNT OF ZERO IS THE INSTRUMENT UNTIL PROVEN OTHERWISE** — (i2), and this one is a pure
negative of exactly the comfortable kind. **The rule is run against a fabricated pair in which a
move exists by construction, and the harness refuses if it does not find it**: three points, one
re-ranked with both candidates available, one with the winner dropped, one identical. It returns
`move = 1, dropout = 1`. **The self-test runs before the quiet gate on every invocation**, so the
zero cannot be reported by an instrument that could not have found anything else.

### WHAT THIS CHANGES, AND IT IS NOT A SOFTENING

**IN THE SENSE §11.2 MEANS IT, WARM-STARTING PRODUCED NO HYSTERESIS ON THIS BOX.** §11.2's fear is
written down precisely: *"initializing each point from its neighbour's answer biases every point
toward its neighbour's answer, producing spatially smooth maps"* — a **different optimum**, ranked
differently. **Zero points.** 2d's sentence — a warm start that saves iterations while moving no
selected candidate is buying **time and not bias** — **transfers to real data in the ranking
sense, and now has a positive-controlled zero behind it rather than a profile-level null.**

**AND IT REPLACES ONE FINDING WITH A SHARPER AND LESS COMFORTABLE ONE.** The selected-model map
still differs at 34% of points, and the mechanism is now named: **`DEGENERATE_HESSIAN` is
start-dependent.** A cell's conditioning verdict depends on the path the optimizer took to get
there, so which models are *selectable* at a point depends on how the fit was started.

**THE EVIDENCE IS IN THE ARMS' OWN OUTCOME COLUMNS AND IT IS MONOTONE IN THE WRONG DIRECTION:**

| arm | iterations per point | `DEGENERATE_HESSIAN` cells | dropout points |
|---|---|---|---|
| `cold` | 57.640 | 79 | — |
| `warm` | 20.336 | 75 | 99 |
| `random` | 22.848 | 94 | 111 |
| `self` | **9.415** | **133** | 44 |

**THE ARM THAT DOES THE LEAST WORK HAS THE MOST DEGENERATE CELLS.** `self` starts at the answer,
converges in a sixth of cold's iterations, and is classified degenerate **68% more often than
cold**. It gains no `OK` cell and loses 54. **A fit that stops sooner gets a worse-conditioned
Hessian estimate**, and the taxonomy turns that into a refusal.

> **THAT IS A FINDING ABOUT THE ESTIMATOR, NOT ABOUT WARM-STARTING, AND IT IS WHY THE CEILING ARM
> EARNED ITS PLACE TWICE.** 44 of `warm`'s 99 dropout points are reachable with the exact optimum
> as the start. **Any mechanism that makes fits converge faster will move this map** — a better
> initializer, a looser gradient tolerance, a faster engine. Warm-starting is one instance of a
> class, and the class is "anything that shortens the path to the optimum".

### WHAT IS OWED, AND IT IS NOT THIS SPIKE'S

- **`DEGENERATE_HESSIAN`'s START-DEPENDENCE IS A DEFECT WITH NO OWNER.** `optimize.hessian_condition`
  is evaluated at the optimum, and the optimum is the same in both arms wherever both converged —
  so the *condition number* should not depend on the start, and it does: median `κ` moves 2.53e6 →
  2.90e6 → 3.52e6 → 2.59e6 across the arms and `kappa_above_limit` moves 48 → 37 → 46 → 71. **Why
  is not established here.** The candidates are a finite-difference Hessian at a numerically
  slightly different point, and a limit at `eps^-0.5` on a quantity whose own estimate is noisy at
  that scale. **A gate whose verdict depends on the path is (i9) at a threshold rather than at a
  fixture**, and the repair is not a wider limit — it is knowing what the quantity's own scatter is.
- **§11.2's AUDIT SHOULD REPORT THE DECOMPOSITION, NOT THE POOLED RATE.** D9 already separates the
  outcome flip from the selection disagreement and calls it *"a different quantity, with its own
  denominators, reported separately"*. **On this data the pooled selection-disagreement rate is
  100% outcome flip**, so a report that pools them says "hysteresis" about a number containing none.
  That is (h4) at the audit's headline, and it is one of the two owed wirings' subjects.
- **THE POINT-LEVEL BOTH-OK INTERSECTION**, which Q6's unit slip left unmeasured, is in
  [`realdata-spike2-decomposition.json`](realdata-spike2-decomposition.json)'s per-cell outcomes
  along with every arm's selection map. **The artifact now answers the question the main report
  could not**, which is the whole point of closing the defect rather than recording it.
