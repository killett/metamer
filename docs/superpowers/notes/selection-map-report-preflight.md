# The selection-map report — pre-flight (2026-09-11)

**The estimator's subject is not in the artifact reporting on it.** The brief owes three things:
the per-point selection map for every arm, the per-cell outcome, and `κ` per cell per arm if it is
affordable — and it asks for the size question to be **answered here rather than discovered**.

**Written before any code.** Run against the brief per the standing rule, (a0)–(a9) and (a)–(k).
Nothing from [`wiring-one-preflight.md`](wiring-one-preflight.md) or
[`wiring-one-smoke.md`](wiring-one-smoke.md) is restated.

---

## S1 — TWO OF THE THREE ARE ALREADY IN THE PRODUCTION STORE, SO THIS IS A BENCHMARK-ARTIFACT DEFECT AND NOT A SCHEMA GAP

§12.2's layout already carries both:

```
/selection/  selected[y,x,c]        the per-point selection map
/status/     outcome[y,x,m]         the per-cell outcome
```

**So "the subject is not in the artifact" is true of the rung REPORT and of the spike REPORT, and
false of a production run's store.** A real run already persists the map and the outcome; what
drops them is the benchmark, which reports in JSON and keeps profiles.

**THE DISTINCTION MATTERS BECAUSE IT DECIDES THE WHOLE SHAPE OF THE WORK.** Read as a schema gap,
this task adds store fields and becomes a format migration on a 10⁷-point store. Read correctly, it
adds keys to a JSON artifact that nothing else consumes. **Only `κ` is genuinely absent from both**,
and it is the one the brief marks conditional.

---

## S2 — `κ` AT PRODUCTION SCALE IS LARGER THAN THE TERM TASK 5 REFUSED, AND THAT SETTLES THE STORE QUESTION BEFORE IT IS ASKED

The brief names the rule correctly: *"the rule that made 2d drop the source-index map was 160 MB at
10⁷ points."* Computed rather than guessed, at 10⁷ points with `M = 3`:

| field | bytes at 10⁷ | status |
|---|---|---|
| `selected[y,x,c]` int16 | **20 MB** | already stored |
| `outcome[y,x,m]` uint8 | **30 MB** | already stored |
| `hessian_cond` float64 | **240 MB** | **not stored, and not in §12.2 at all** |
| `hessian_cond` float32 | **120 MB** | same |
| *(the source-index term Task 5 refused)* | *160 MB* | *refused* |

**`κ` IN FLOAT64 IS HALF AGAIN AS LARGE AS THE TERM THAT WAS REFUSED**, and float32 is the same
order. The refusal's reason was not the absolute size: it was **the invariant that peak RAM is
derivable from the memory budget alone**, which a field-sized term carried for the length of the run
breaks regardless of its dtype. **So `κ` cannot become a full-resolution production store field on
the same reasoning, and that is decided rather than open.**

**AND THE DESIGN ALREADY CONTAINS THE PATTERN FOR EXACTLY THIS CASE**, in two places, so no new
mechanism is being invented:

- §12.2: `/detail/ ragged  full parameter covariances — **subsample / region only**`.
- §11.3: *"Record the source coarse index per point, **at least across the audit subsample**."*

**Subsample-or-region is the design's own answer to "too big at full resolution and needed where it
matters".** If `κ` is ever wanted in a store, that is the shape, and it is a separate decision from
this task.

---

> ## THE ORDER OF S2 AND S3 IS CORRECTED, 2026-09-11, AND THE RETIRED FRAMING STAYS VISIBLE
>
> **S2 LEADS WITH COST AND S3 WITH STRUCTURE, AND THAT IS THE WRONG WAY ROUND.** The reason `κ`
> per arm is not a store field is **structural — a store is one arm** — and the cost figure is a
> second fact. **Stating cost as THE reason is the weaker record**, because it reopens the moment
> somebody finds 120 MB affordable, and the structural reason never reopens. The shipped home for
> the reason is `bench.report.arm_arrays_record`'s docstring, in that order. **Both sections stand
> as written**: the arithmetic in S2 is correct and is what settles the *single-arm* store
> question, which is a real and separate question that cost does decide.

## S3 — `κ` PER ARM CANNOT BE A STORE FIELD AT ALL, AND THAT IS WHY THE BENCHMARK IS WHAT OQ23 NEEDS

**A store is one arm.** It records the run that produced it. Arms are experimental conditions that
exist only inside `audit.run_arms`, which fits one batch four ways in one process and returns
`FitResult`s. **So "κ per cell per arm" is not a quantity a production store can hold in any
dtype** — the question is not affordability, it is that the object does not exist there.

**OQ23's subject is therefore intrinsically a benchmark artifact**, and the brief's instinct is
right: *"the benchmark is what OQ23 needs."* This is the (h2) distinction one level out — a
quantity may only be recorded where it is defined.

---

## S4 — THE SIZE AT RUNG SCALE, COMPUTED: 142 KB OF ARRAYS ONTO A REPORT THIS SESSION ALREADY GREW FIVEFOLD

At 384 points, `M = 3`, five arms (cold, warm, N1, N2, self) and two run stores, serialised as JSON:

| array | one copy | how many | total |
|---|---|---|---|
| selection map, `int16` | 1 290 B | 7 (5 arms + 2 stores) | 9 KB |
| outcome grid, `(P, M)` `uint8` | 4 224 B | 5 arms | 21 KB |
| `κ` grid, `(P, M)` `float64` | 23 067 B | 5 arms | 113 KB |
| **`κ` at 6 significant figures instead** | *12 448 B* | *5 arms* | *61 KB* |
| | | **total** | **142 KB** |

**AND THE BASELINE IS NOT WHAT IT WAS THIS MORNING.** The committed rung reports were **8.9 KB**;
the strata that landed this session took the smoke reports to **44 KB**, a **fivefold** growth.
Adding the arrays gives **~185 KB**. That is affordable and it is not nothing, so it is stated
rather than waved through — *"small arrays"* and *"small artifact"* are different claims once a
float64 grid is rendered as decimal text.

> **`κ` AT SIX SIGNIFICANT FIGURES HALVES THE COST AND IS REFUSED ANYWAY.** A condition number is
> compared against `HESSIAN_COND_LIMIT = 2²⁶` and OQ23 is a question about *why the value moves
> between arms*; truncating the quantity whose movement is the open question is (a2d) at a
> recorded value. **Full float64 repr, and the 61 KB saved is not worth the question it forecloses.**

> ## THIS TABLE AND Q1 ARE SUPERSEDED BY MEASUREMENT, 2026-09-11 — AND Q1 WAS WRONG TWICE
>
> **THE ESTIMATE ABOVE IS COMPACT JSON AT 384 POINTS. THE ARTIFACT IS INDENTED JSON, AND THE
> SMOKE RUNS AT 52.** Both errors are mine and neither is in the direction that flatters:
>
> | | | |
> |---|---|---|
> | (i) **Q1 quoted the 384-point figure "at the smoke geometry"** | the smoke is **26 × 2 = 52 points** | (a4) — a worked example applied to a case it was not recomputed for |
> | (ii) **the table costs compact `json.dumps`** | the report is written `indent=2`, which is **2.94×** on nested numeric lists | the serialisation format, not the arrays, dominates |
>
> **MEASURED, and these are the numbers that stand:** the `arm_arrays` section is **14 544 B
> compact / 42 784 B indented** at 52 points. Scaled to the shipped 384: **107 KB compact,
> 316 KB indented.** Against the table's predicted 142 KB the *compact* projection is **35% LOW**,
> because **21.4% of `κ` entries are `null`** — four characters where the table assumed an
> eighteen-character float repr, which is the `kappa_undefined` population showing up in the file
> size.
>
> **THE AFFORDABILITY HALF OF THE `κ` ARGUMENT MOVES BY 2.2× AND THE STRUCTURAL HALF DOES NOT** —
> which is the whole value of having ordered them that way. 316 KB is still a benchmark artifact
> and still trivially affordable, so nothing is decided differently; but the *number* was wrong by
> more than a factor of two, and a decision resting on it alone would now be resting on a
> superseded figure.
>
> **`indent=2` IS KEPT.** A compact arrays section inside an indented document would save 209 KB
> at rung scale and would add a second serialisation path to this module. **Optimising against a
> number I have just been wrong about, for a size that is not a problem, is the wrong trade** —
> and the whole report stays two orders of magnitude under `check-added-large-files`' 2000 KB.

---

## S5 — WHAT `run_rung` HOLDS AND DROPS, WHICH IS ALL OF IT

The brief says *"the driver holds it and drops it — same shape as `median_dt`, computed, used and
not persisted."* Enumerated, so the fix is written against the set rather than against the two
examples anybody remembers:

| held | where it comes from | what it is used for | persisted |
|---|---|---|---|
| cold selection map | `_selection_map(cold_store, …)` | the smear width | **no** |
| warm selection map | `_selection_map(warm_store, …)` | the smear width and the interior null | **no** |
| N2 selection map | `field_arms(...).selected` | the floor arm's width | **no** |
| self selection map | `self_arm(...).selected` | one agreement check | **no** |
| outcome, 4 arms | `arms.results[arm].outcome` | the strata, the flip partition | **no** |
| `hessian_cond`, 4 arms | `arms.results[arm].hessian_cond` | `kappa_bin`, **cold only** | **no** |

**THE COLD-ONLY LINE IS THE SHARPEST ONE.** `kappa_bin` reads the cold arm because of (j7), so the
other three arms' `κ` is computed by the fit, carried in memory, and **never looked at by
anything** — which is (a2c), and it is precisely the array OQ23 needs.

---

## S6 — THE SPIKE'S REPORT ALREADY CARRIES PER-ARM SELECTION MAPS; WHAT IT LACKS IS THE PER-CELL OUTCOME, AND THAT IS THE 4-HOUR RE-FIT

Verified against the committed artifact rather than taken from the brief:

- `realdata-spike2-report.json` carries `cold_selection_map` (289 entries) **and**
  `comparisons.<arm>.selection_map_arm` (289 each) for `warm`, `random` and `self`. **The per-arm
  map requirement is already met there.**
- It carries `outcome_counts` — a **histogram** — and no per-cell outcome.
- It carries `kappa_median`, `kappa_max`, `kappa_above_limit` — **summaries** — and no per-cell `κ`.

**SO THE DECOMPOSITION ADDENDUM'S RE-FIT WAS CAUSED BY EXACTLY ONE MISSING ARRAY**, and the
addendum's own docstring says so: *"carries the per-point selection map for every arm — which is
what 2d lacked — but not the per-CELL outcome, so 'warm selected a different candidate' cannot be
split."* **A histogram is not a map**, and the difference cost four hours of re-fitting.

> **THIS IS THE (a2b) SHAPE AT AN ARTIFACT: A SUMMARY IS AVAILABLE WHERE THE SUBJECT IS NOT.**
> `kappa_median` and `kappa_above_limit` are exactly the reading that makes OQ23 visible and
> exactly the reading that cannot answer it — the table in open question 23 is built from those
> three summaries, and every follow-up question about *which* cells moved needs the array.

---

## S7 — THE DECOMPOSITION IS NOW COMPUTED IN `audit_report`, SO AN ARTIFACT CARRYING THE OUTCOME MAKES IT RE-DERIVABLE — AND THAT IS A CHECKABLE CLAIM

`selection_decomposition` takes four arrays and nothing else: two outcome grids and two
`best_index` vectors. **A report carrying the per-arm selection map and the per-arm outcome carries
exactly its inputs.** So the claim *"this artifact makes the decomposition a lookup rather than a
re-fit"* is not a hope; it is testable by feeding the artifact back through the shipped rule and
comparing against the counts the report already carries.

**That test is the whole justification for the task and it must exist**, or the artifact grows by
142 KB on an argument nobody checked.

---

## S8 — THE MAP'S VOCABULARY TRAVELS WITH IT OR `-1` AND `-2` READ AS MODEL INDICES

`/selection/selected` is `int16` with **two** sentinels: `-1` is *"a fit ran and no candidate won"*
and `SELECTED_UNSET = -2` is *"nothing wrote here"*. `n2map` reuses that vocabulary deliberately so
`smear.agreement_map` needs no adapter.

**IN JSON THEY ARE JUST NEGATIVE NUMBERS.** A consumer reading the artifact without the vocabulary
gets two distinct failure states silently merged, and merged into a *model index* if it indexes
with them. **The artifact records the vocabulary beside the maps** — (a2d): a recorded value's
meaning is part of its identity.

---

## S9 — ORDER IS PART OF THE ARRAY AND THE EXISTING SHAPE CHECK CANNOT SEE IT

`field_arms`' own docstring states the limit: rows are in **row-major grid order**, and *"the shape
check below catches a wrong COUNT and not a wrong ORDER — a permuted batch produces a silently
mis-keyed map."*

**A flat list of 384 integers in a JSON file has no order but the one it is documented to have.**
So the artifact carries the grid shape and names the order, and the reader that re-derives the
decomposition (S7) reshapes with it rather than assuming. **Otherwise the first consumer to plot
the map gets a picture, and a wrong one.**

---

## S10 — WHAT THIS TASK MUST NOT DO

- **It must not add a store field.** §12.2 is a format on a 10⁷-point store; `selected` and
  `outcome` are already there and `κ` is settled by S2 as subsample-or-region **if ever**, which is
  a separate decision.
- **It must not repair open question 23.** It makes OQ23 *answerable from artifacts*, which is the
  opposite of answering it. A structural-sounding explanation remains the most dangerous reading.
- **It must not re-run a rung.** Criterion 12's closer changed on 2026-09-11 and the population
  that exercises the strata is the spike's committed arms, not a rung.
- **It must not quietly become the OQ23 measurement.** The arrays make the question askable; asking
  it is a measurement with its own pre-flight and its own predictions.

---

# THE TEST PLAN

Each line names the bug it catches; expected values determined independently of the implementation.

| # | test | behaviour under test | expected value, determined independently | bug it catches |
|---|---|---|---|---|
| **U1** | `test_the_decomposition_is_re_derivable_from_the_committed_artifact` | feeding the artifact's per-arm maps and outcomes back through `selection_decomposition` reproduces the report's own `by_move` / `by_dropout` / `by_both_unavailable` | the counts are already on the report, written by a different code path at run time | **S7.** An artifact that carries arrays nobody can reconstruct the finding from — 142 KB spent on an argument, which is the failure the size question exists to prevent |
| **U2** | `test_a_selection_map_carries_its_grid_shape_and_its_order` | the artifact names the shape and the row-major convention, and reshaping by it round-trips | `field_arms` documents row-major; the shape is `(n_normal, n_parallel)` | **S9.** A flat list read in the wrong order — the shape check catches a wrong count and not a wrong order, so nothing else would notice |
| **U3** | `test_the_two_selection_sentinels_survive_the_artifact_distinctly` | `-1` and `-2` come back as themselves, and the artifact names both | `SELECTED_UNSET = -2` is "nothing wrote here", `-1` is "no candidate won" — two different facts | **S8.** Two failure states merged, or used as model indices by a consumer that never saw the vocabulary |
| **U4** | `test_every_arm_the_driver_fits_reaches_the_artifact` | the set of arms in the artifact equals the set `run_rung` fits — written against the set, not an enumeration | `Arm` plus the `self` arm; the driver's own results dict is the set | **S5/(c5).** A sixth arm added later and silently absent from the artifact, which is how `κ` for three arms came to be computed and never looked at |
| **U5** | `test_the_kappa_array_is_full_precision_and_not_a_summary` | `κ` round-trips to the value the fit produced, bit for bit | `float64` repr round-trips exactly; 6 s.f. does not | **S4.** A truncated `κ` — halving the artifact by foreclosing the question the array exists for, (a2d) |
| **U6** | `test_an_arm_with_no_kappa_records_absence_rather_than_a_number` | a cell whose Hessian is not positive definite records `null`, not `0.0` or a fill | `kappa_undefined` is a live bin — the smoke populated it on both seeds — so NaN cells are the ordinary case, not the corner | **(a0).** A fill value a successful run can produce: `0.0` is the most well-conditioned value there is, and it would read as the opposite of what it means |
| **U7** | `test_the_artifact_grows_by_the_arrays_and_nothing_else` | the report's non-array keys are unchanged when the arrays are added | the committed reports' key sets are the expected value | **S1.** The task quietly becoming a schema change — a new summary, a new ratio, a new check smuggled in beside the arrays |

**Not on the list, and why.** A test asserting particular `κ` values or particular map contents: a
smoke run carries `is_a_smoke_run` and Task 9's rule refuses it as evidence for any criterion.
Asserting its magnitudes would manufacture the evidence the flag exists to deny.

---

# PREDICTIONS, COMMITTED BEFORE THE RUN

- **Q1 — the artifact lands between 150 KB and 250 KB at the smoke geometry**, against 44 KB today.
  *Refuted upward* by anything over 500 KB, which would mean something field-sized is being written
  that the table in S4 does not account for. *Refuted downward* by anything under 100 KB, which
  would mean an array is missing.

  > **SCORED 2026-09-11: REFUTED DOWNWARD, AND THE REFUTATION CLAUSE'S OWN READING WAS WRONG.**
  > Measured **93 332 B** (clean) and **89 970 B** (contaminated), under the 100 KB floor — but the
  > clause says that means *an array is missing*, and no array is missing: all five arms are
  > present and the decomposition round-trips. **The clause was written against a band computed at
  > 384 points for a run that happens at 52**, so it could not have been satisfied by a correct
  > run. **A refutation clause is only as good as the quantity it is stated over**, and this one
  > names the right direction over the wrong population. See the correction in S4.
- **Q2 — the decomposition re-derived from the artifact reproduces the report's counts exactly**,
  because it is the same rule on the same arrays. *Refuted* by any difference, which would be a
  serialisation defect and is the single most valuable thing this task can find.
- **Q3 — `κ` will be `null` on some cells in every arm**, because `kappa_undefined` was populated on
  both smoke seeds. *Refuted downward* by no nulls anywhere, which would contradict the smoke and
  mean the absence is being written as a number.
- **Q4 — the per-arm `κ` arrays will NOT move in one direction between arms**, matching the smoke's
  per-arm `DEGENERATE_HESSIAN` counts, which went both ways. *Refuted* by a uniform direction,
  which would be the first structured signal about OQ23 — **and would still not be an explanation**,
  which is the thing this task must not supply.

---

# WHAT IS ANSWERED HERE RATHER THAN LEFT TO BE DISCOVERED

**The size question, both halves, as the brief asked:**

- **A benchmark artifact**: all three arrays, every arm, full precision — **142 KB onto a 44 KB
  report**, affordable, and it is what OQ23 needs.
- **A production store field**: `selected` and `outcome` **already are** ones. `κ` is **not**, and
  at 240 MB in float64 it is larger than the term Task 5 refused, so it does not become one at full
  resolution. If it is ever wanted there, the design's own answer is `/detail/`'s
  **subsample-or-region**, and that is a separate decision with its own memory-budget argument.

**They are different answers because they are different objects**: a store records one arm, and the
quantity OQ23 is about only exists where there are four. **That is the reason; the 240 MB is a
second fact beside it.**

**AND THE TWO ARTIFACTS DIVERGE DELIBERATELY.** The rung report gains the section through shipped
code; **the committed spike reports do not gain it retroactively**, because the spike is closed and
retrofitting them would need a four-hour refit to produce an artifact of a run that did not happen.
**What converges is the BUILDER** — `arm_arrays_record` is shipped so the next harness needing
per-arm arrays imports it rather than hand-rolling JSON, which is what the spike harness did and is
why its report has maps and no outcomes. The artifact register's key-pinning gains the section's
vocabulary in the same commit, conditional on the section being present, **with a positive control
proving that clause fires** — it is otherwise a pure negative, since no committed report carries the
section yet.
