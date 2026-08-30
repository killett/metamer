# 2d plan Task 0 — the pricing spike: verdict

**Run 2026-08-30. Three runs of the harness, at heads `a730575`, `76a0c09` and `f3fb948`, all
appended to [`phase2d-spike-measured.jsonl`](phase2d-spike-measured.jsonl) and separable by the
`git_head` on each `header` record. Predictions were committed first, at `7b06740`, before the
harness existed** —
[`phase2d-spike-predictions.json`](phase2d-spike-predictions.json).

> ## THE HEADLINE IS THAT FOUR DEFECTS WERE FOUND AND ALL FOUR WERE IN THE INSTRUMENT
>
> Nothing in `src` was wrong. The harness fitted float32 on one side and float64 on the other;
> it hand-built a decimal-year axis on one side and took `to_decimal_years` on the other; its
> "repeats" drew a new fixture each time, so a spread the void clause attributes to the host was
> partly the data; and its quiet check **recorded** a loud host and then measured anyway, which
> is (a2b) inside the instrument that exists to enforce (a2b).
>
> **Each was cheap because a harness is not production code, and none would have been cheap at
> Task 5 with twenty hours spent.** This is the pre-flight arriving late, and it is recorded as
> that rather than presented as a three-run protocol.

---

## Reading 1 — the per-point-per-arm cost. REFUTED FROM BELOW, and the inherited figure cannot be reconciled

**Measured, on the third run: `10.62 s` per point per arm**, five true repeats of **one** fixture,
quiet host, `M = 2` (`["white", "white + matern12"]`), `N = 630`, `B = 16`, signal
`constant + trend`.

| repeat | s/point | iterations, all cells |
|---|---|---|
| 0 | 11.362 | 405 |
| 1 | 10.698 | 405 |
| 2 | 10.579 | 405 |
| 3 | 10.194 | 405 |
| 4 | 10.258 | 405 |

**Mean 10.618, standard deviation 0.467 (4.4%), spread 11.0%** — inside the 15% void clause, which
fired on the previous run and does not fire here. **The iteration count is identical in every
repeat**, which is `fit` having no stochastic component, restated as a by-product.

**PREDICTED BAND `[16, 26]` s. THE CLAUSE FIRES FROM BELOW.**

**And its committed reading — *"every inherited figure in the saving table becomes suspect"* — is
the one to act on, but the mechanism is NOT identified and this spike does not identify it.**

- **Iterations explain about three quarters of the gap and not all of it.** 2c measured mean
  `n_iter` **20.2** per cell against this fixture's **12.66**. Under the two-point cost
  decomposition below, 2c's iteration count predicts **15.5 s/point** against the **21.0** they
  recorded.
- **THE INHERITED FIGURE DOES NOT RECORD ITS SIGNAL SPEC OR ITS FIXTURE**, only its candidate set,
  batch and record length. **So it cannot be re-measured**, and the residual cannot be attributed
  between a harder fixture, a wider design and a busier host. **(j8) at a cost model: the verdict
  was adopted and half its instrument was written down.**

### The two-point cost decomposition, and why it is not a model

`self` costs **2.81 s/point** on **1.19** iterations per point where `cold` costs **10.62** on
**25.31**, giving

    per point per arm  ~=  2.43 s  +  0.324 s x (iterations per point)

**THIS IS TWO POINTS AND TWO POINTS CANNOT DISTINGUISH A LINE FROM A CURVE** — this project's own
(a4) register, and the reason `k = 8`'s stride sweep needed three fixtures. **It is recorded as an
observation and no budget is built on it.** What it is good for is the shape it implies and one
consequence worth carrying:

> **A FIXED PER-POINT COST OF ROUGHLY 2.4 s MEANS AN ITERATION SAVING DOES NOT CONVERT
> ONE-FOR-ONE INTO A WALL-CLOCK SAVING.** 2c measured the opposite — **42.28%** of iterations
> against **45.90%** of wall clock, a wall-clock saving *larger* than the iteration saving.
> **The two readings disagree and are recorded as disagreeing rather than reconciled.**

---

## Reading 2 — N1's cost against cold's. CONFIRMED, on six repeats across two runs

**N1 costs a full cold arm.** The prediction holds and the reading is closed; N1 was dropped from
the third run's repeats 1–4 rather than confirmed a seventh time at 200 s a go.

| run | repeat | cold iterations | N1 iterations | N1 / cold | self / cold |
|---|---|---|---|---|---|
| 1 | 0 | 394 | 395 | 1.0025 | 0.048 |
| 1 | 1 | 395 | 395 | 1.0000 | 0.061 |
| 1 | 2 | 381 | 382 | 1.0026 | 0.042 |
| 2 | 0 | 394 | 395 | 1.0025 | 0.048 |
| 2 | 1 | 395 | 395 | 1.0000 | 0.061 |
| 2 | 2 | 381 | 382 | 1.0026 | 0.042 |
| 3 | 0 | 394 | 395 | 1.0025 | 0.048 |

All over the **common cell set** — every arm summed over the same 30–31 cells, because `fit` fits
every cell and a false `x0_valid` takes the moment ladder, so per-arm OK sets would compare N1 fits
against cold fits **of which some are the same fit**.

**Predicted band `[0.90, 1.10]`. Measured `1.0017` on average and never outside `[1.0000,
1.0026]`.**

**THE POSITIVE CONTROL FIRES AND THE VERDICT DEPENDS ON IT.** `self` collapses to **4–6%** of
cold's iterations against a `<= 0.25` clause, so the instrument demonstrably tells two arms apart
by cost through the same wiring. Without it, *"N1 costs what cold costs"* is byte-identical to
*"the counter is not moving"* and to *"both arms silently ran cold"*.

**THE READING SURVIVED EVERY INSTRUMENT DEFECT**, because it is a ratio of **iteration** counts and
iterations are deterministic. The wall clock readings did not.

**CONSEQUENCE FOR THE PLAN: N1 needs a rung allocation and is not in E2's 12.047 factor.** It runs
at **the plausibility rung and the easy rung only** — its job is to separate *"the surface
decides"* from *"the start distance decides"*, and that separation does not need every rung.

---

## Reading 3 — the `run`-to-`fit` ratio. REFUSED, three times, and replaced by a better instrument

| run | ratio | `same_workload` | why it is not a reading |
|---|---|---|---|
| 1 | 1.178 | not checked | float32 in the store against float64 in the fit |
| 2 | 1.054 | **false** — 6490 vs 6376 | a hand-built axis against `to_decimal_years` |
| 3 | **0.999** | **false** — 6490 vs 6364 | residual 2% workload gap, **cause unidentified** |

**THE COMMITTED CLAUSE FIRES FROM BELOW AT RUN 3** — *"the bound is not a bound and the comparison
is measuring something other than the same work twice; the reading is REFUSED rather than reported
as a speed-up"* — **and `same_workload: false` says the same thing independently.** Two attempts
each fixed a real defect and neither closed the gap.

> **THE COMPARISON IS ABANDONED AND THE QUANTITY IS MEASURED ANOTHER WAY.** The run's own phase
> accounting needs no second path and is immune to the mismatch:
>
> | run | `run_seconds` | `phase_seconds["fit"]` | outside the fit | share |
> |---|---|---|---|---|
> | 1 | 569.36 | 563.60 | 5.76 s | 1.01% |
> | 2 | 567.80 | 564.54 | 3.26 s | 0.57% |
> | 3 | 446.81 | 443.99 | 2.82 s | 0.63% |
>
> **Validation, opening, store creation, assembly, region writes and provenance together cost
> under 1% of a run**, measured three times on 384 points. `assemble` alone is **0.013 s**.
> **(j3): an existing feature is an instrument for a property its own purpose does not concern.**

**WHAT IS STILL OPEN, STATED SO IT IS NOT READ AS CLOSED:** whether `run`'s *fit phase* costs more
per unit of work than a bare `fit` call. The refused comparison is the thing that would have said,
and **Task 4 owns it** — the driver has both paths in front of it and can compare them on
identical inputs, which this harness could not be made to do in three attempts.

**THE BUDGET DOES NOT DEPEND ON IT.** An overhead under 1% on the full-field passes moves 27.0 h by
under 20 minutes, inside the margin.

---

## What the spike established that was not a reading at all

**2d's field is a SINGLE TILE at every legal budget, and this is a measurement.**

| | measured |
|---|---|
| process floor before a tile exists | **~229 MB**; a budget leaving nothing for a tile is refused at layer 3 |
| smallest legal tile side, `N = 96` | **176** |
| smallest legal tile side, `N = 630` | **80** |
| tile side, `N = 630`, default budget (4.134 GB) | **736** |
| tiles for 2d's `32 x 12` field | **1** |

**So the per-tile barrier is not part of 2d's cost**, and a single-tile overhead reading is the
correct scope rather than a compromise. **The predictions file's void clause for reading 3 said the
opposite** — *"void if the run produced fewer than 2 tiles"* — and is **superseded in the record
with the measurement that caused it**, never reinterpreted. The harness emits both.

**AND `tests/test_twopass.py` REACHES MULTIPLE TILES ONLY AGAINST A STUBBED FLOOR**, at budgets
around 0.001 GB that a real run refuses at layer 3. **Those budgets are not evidence that a real
multi-tile run is affordable**, and they read as though they were.

---

## THE RE-COSTING, AND THE GATE ON TASK 1

**E2's budget is rebuilt in ITERATIONS, because iterations are deterministic and this box's wall
clock is not.** The unit is a cost per point per arm; what it multiplies is the field's own
iteration count, **which is Task 1's to report on the actual benchmark field.**

Factor unchanged at **12.047** for three rungs, plus **2.0** if N1 runs at two rungs → **14.047**.

| cost per point per arm | source | 12.047 | **14.047, N1 at two rungs** |
|---|---|---|---|
| **10.62 s** | measured here, 5 true repeats, quiet host | 13.6 h | **15.9 h** |
| **21.0 s** | inherited 2026-08-29, instrument half-recorded | 27.0 h | **31.5 h** |

> **THE PLAN'S 27.0 h SURVIVES AS AN UPPER BOUND UNDER THE MORE EXPENSIVE OF THE TWO FIXTURES
> ACTUALLY MEASURED, AND THE LIKELY COST IS ABOUT HALF.** **But adding N1's two rungs at the
> inherited rate gives 31.5 h, which is OVER the 30 h ceiling.** That combination — the pessimistic
> rate **and** N1 at two rungs — is the only one that breaks it.
>
> **SO TASK 1 CARRIES A GATE: it reports the benchmark field's own iteration count per point, and
> E2's budget is finalised against that number before Task 5 spends anything.** If the field lands
> near this fixture's 25.3 iterations per point, the budget is ~16 h and the ceiling is not close.
> If it lands near 2c's 40.4, N1 drops to one rung.

**AND THE CHEAPEST WAY TO NOT NEED THE GATE IS ALREADY IN THE PLAN:** the field's difficulty is
`Δ` and `ℓ`, which Task 1 chooses. The iteration count is not a fact 2d receives; it is partly a
fact 2d builds — **and that is exactly why it must be measured and recorded rather than assumed,
because a field tuned until it is affordable is a field tuned with the audit's answer in view.**

---

## Verdicts against the committed clauses

| reading | clause | outcome |
|---|---|---|
| 1 | band `[16, 26]` s | **REFUTED FROM BELOW** at 10.62 s. Mechanism unidentified; the inherited figure is not re-measurable |
| 1 | void if spread >= 15% | **did not fire** at 11.0% on true repeats. **It DID fire at 21.0% on the previous run**, which is what exposed the repeats not repeating |
| 2 | N1/cold in `[0.90, 1.10]` | **CONFIRMED** at 1.0017, six repeats, two runs |
| 2 | void if `self`/cold > 0.25 | **did not fire** — 0.042 to 0.061. The instrument sees cost differences |
| 3 | ratio in `[1.00, 1.15]` | **REFUSED.** `same_workload` false in every run that checked |
| 3 | void if fewer than 2 tiles | **SUPERSEDED** by the production-geometry measurement, in the record, with its cause |

**Nothing moved in `src`. No constant, no exit-criterion verdict, and no figure in the 2c saving
table was edited on the strength of this spike** — the saving table's numbers are ratios of
iteration counts, which is the one thing this spike found to be stable.
