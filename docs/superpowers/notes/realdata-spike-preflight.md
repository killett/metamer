# The real-data spike — pre-flight, first half only (2026-09-06)

**Written before any code and before any measurement**, against the brief this session received.
It audits the brief with the handoff's (a)–(k) categories
([`phase1-to-phase2-handoff.md`](phase1-to-phase2-handoff.md) §1) and records what each finding
changed. **Nothing here is a measurement of real data; nothing here has been run.**

**THE SPIKE HAS TWO HALVES AND ONLY THE FIRST IS IN SCOPE.** The second — the coherence of real
optima, and whether 2d's null transfers — is not begun, not designed here, and not to be started
without checking in.

---

## 0. THE BRIEF, AND WHERE IT ALREADY EXISTED

The brief this session received is not new. Its first half was written into the record on
2026-08-30, at D1's amendment, and again in
[`phase2d-field-verdict.md`](phase2d-field-verdict.md):

> **"The spike must measure two things, not one: the coherence of real optima and the cold
> iteration count of real fits. The second is cheaper, needs no warm start at all, and bounds the
> saving before any coherence question is asked."**

> **"Measure cold difficulty FIRST: if real fits converge in ~15 iterations the saving is bounded
> near zero and the coherence question is moot."**

**THE SESSION BRIEF AND THE RECORD AGREE, WHICH IS WORTH SAYING BECAUSE IT IS THE THING THIS
PRE-FLIGHT WOULD OTHERWISE HAVE TO ESTABLISH.** (a5): a requirement checked against the
constraints in a document nobody has open. Checked, with the command:
`grep -n 'real gridded product\|real-data spike' PROGRESS.md docs/superpowers/**` — twelve sites,
none of them contradicting the brief, and the two above are the only ones that *specify* it.

**What the first half must establish**, restated once so the rest of this document can point at it:

1. **Cold iterations per point and per cell** on a real gridded product, at the shipped fit, with
   the candidate set and `M` named.
2. **The comparison it is read against**, named, with the reason.
3. **Whether real fits converge cleanly** — the outcome distribution and the Hessian condition
   numbers.

---

## 1. WHAT WAS CONFIRMED AGAINST THE CODE AND THE ARTIFACTS, WITH THE COMMANDS

**(a4)'s negative-result register: *"checked" in your own pre-flight is a claim.*** Every row below
names what produced it. Nothing in this section was read out of prose.

| claim | source | reading |
|---|---|---|
| branch, tip, tree clean | `git log --oneline -8`, `git status --porcelain` | `main`, tip `e55e9bb`, clean |
| CI green at the tip | `gh run list --json headSha,conclusion,status` | `e55e9bb` → `completed` / `success`. The `failure` at `d6aa92d` is 2d's figure test, repaired by `3b7a50f` — which is what the record says it is |
| the v2 anchor | `phase2d-difficulty-rung-report.json`, key `iterations` | `cold_per_point = 42.0807`, `cold_ok_per_point = 42.0391`, `cold_ok_total = 16143` over **384 points**, `n_time = 630`, `n_normal = 32`, `n_parallel = 12` |
| the v1 anchor | `phase2d-easy-rung-report.json`, key `iterations` | `cold_per_point = 24.3776` |
| the saving | same report, key `ratios` | `saving_pass2_only = 0.41808`, `saving_net_of_pass1 = 0.39751` |
| `M = 3`, and the set | `src/metamer/bench/fields.py:191` | `CANDIDATES = ("white", "white + matern12", "white + matern32")` |
| the candidate identities | both reports, `instrument.candidate_spec_hashes` | `6aa2199c9b35b7d0`, `6442e0d4573a6854`, `eb62e0c295bd7541` — identical in both |
| 2c's two spellings | [`phase2d-preflight.md`](phase2d-preflight.md) §7 | **40.79** on 2c's own optimizer path; **43.94** on 2c's fixture under the shipped `fit`. Both dated, ~0.8 sd apart, and explicitly **not to be reconciled** — (j5) |
| the record-length ladder | `PROGRESS.md`, D1's amendment 2026-08-30 | cold iterations per point **28.27 ± 5.70 / 35.32 ± 2.94 / 40.79 ± 3.73** at `N = 96 / 384 / 630`, against savings **+7.80% / +31.73% / +42.28%** |

**NO DISAGREEMENT WAS FOUND BETWEEN ANY TWO OF THEM.** Every number the session brief quoted
reproduces from the artifact that owns it. Two things are recorded anyway, because the brief says
a disagreement is a defect to report either way:

- **`42.08` is the all-cells figure and `42.04` is the OK-only one.** They differ by 0.04 on this
  field and the brief quotes the first. See finding **F7**, where the gap is not 0.04.
- **`tiling.py`'s "four places" is six literal occurrences at three call sites today**, at lines
  904, 905, 932, 933, 974, 975; the record cites the `isel` at 973. That is line drift from later
  edits, not a substantive disagreement, and the record's claim — *the spatial dims must be
  literally `y` and `x`* — holds exactly as written.

---

## 2. THE FINDINGS

### F1 — (j5) THE ANCHOR IS 42.08, AND THE REASON IS THE INSTRUMENT, NOT THE NUMBER

The brief asks which comparison number the reading is read against, and why. **There are five
candidate anchors and four of them were produced by a different instrument.**

| anchor | instrument | comparable to a store-read after `metamer run`? |
|---|---|---|
| **42.08** (v2 rung, `N = 630`) | shipped `metamer run`, read off `/primitives/iterations` by `fields.iteration_count` | **yes — this is the same instrument** |
| 24.38 (v1 rung, `N = 630`) | same | yes, and it is the signal-free construction's value |
| 43.94 (2c's fixture) | in-process `fit`, `phase2d-2c-fixture-probe.py` | no — a different code path |
| 40.79 (2c's field, `N = 630`) | 2c's own optimizer path in `warmstart-spike-harness.py` | no |
| 14.31 (2d's first field) | in-process, superseded construction | no |

**SO THE PRIMARY COMPARISON IS AGAINST 42.08**, because it is the only figure produced by the
instrument the spike will use — the shipped run, at `M = 3`, at `N = 630`, on the shipped
candidate set, read out of the store. **24.38 is reported beside it** as the same instrument's
reading on the signal-free construction, which is what says the instrument responds to difficulty
at all.

**AND 40.79 IS NOT DELETED AND IS NOT THE COMPARATOR.** It is the abscissa of the record-length
ladder, and the ladder — not any single anchor — is what converts an iteration count into a bound
on the saving. See **F4**.

**What this changed:** the brief's *"say which one the reading is compared to and why"* is
answered before the run rather than after, and 43.94 and 40.79 are recorded as ladder context
rather than as targets. A spike that compared a store-read number to 43.94 would be comparing two
instruments (j5) and would have had no way to know.

### F2 — (a2d) PER-POINT ITERATIONS SUM OVER `M`, AND THE UNIT IS PART OF THE NUMBER

`fields.iteration_count` (`src/metamer/bench/fields.py:759`) computes `per_point = total / points`
where `total` sums the whole `(y, x, m)` array and `points` counts points with **any** live cell.
So a per-point figure at `M = 3` is about three times the per-cell figure, and **the two are the
same integer's two readings**. `per_cell` is emitted beside it for exactly this reason.

The record already carries the rule — *per-point iterations are comparable only at equal `M`*,
[`phase2d-preflight.md`](phase2d-preflight.md) §7 — and notes it was **not** safe before the
candidate set grew from two members to three.

**What this changed:** the spike runs the shipped `CANDIDATES` (`M = 3`) and **reports per point
and per cell in the same artifact**, so no later reader has to know which was meant.

### F3 — (j9) THE CONFIG HAS ONE SPELLING AND IT NAMES `variable = "sla"`

`fields.config_text` is the single source of the benchmark's config — candidate set, signal terms,
criteria, audit seed — and its docstring carries the (j9) argument for being so: *"a second
spelling of the candidate set would be a second `M`, and `M` sets both the price and D9's stratum
count."* Its template hardcodes `variable = "sla"` and `data_uri`.

`sla` is the right name for a DUACS/CMEMS gridded sea-level product, so on the canonical altimetry
product this is free. **It is not free on anything else**, and a spike that wrote its own config
for a differently-named variable would be creating the exact second spelling the record cites as
this species' fifth instance.

**Two closers, and this is a scope decision rather than a finding:**

1. **Widen the single source** — `config_text(uri, *, variable: str = "sla")`. One parameter, one
   line, keeps one spelling, and it is a `src/` change with a test.
2. **Rename the variable during the zarr conversion.** No `src/` change, and it puts a name in the
   store's `variable` attr that the product does not use — provenance then records our name for
   the data rather than its own.

**Recommended: (1).** Recorded rather than taken, because it touches `src/`.

> **CLOSED 2026-09-07 WITHOUT EITHER CLOSER: THE PRODUCT'S VARIABLE IS LITERALLY `sla`.** DUACS
> names sea level anomaly `sla`, which is the name `config_text` already renders, so the config
> for the real run is `fields.config_text(uri)` unchanged and there is no second spelling. **The
> finding stands for the next product** — it is a property of the single source, not of this
> dataset — and it is left here rather than deleted, because the next real input to arrive is
> where it bites.

### F4 — (j6)/(a4) THE READING IS PLACED ON A CURVE, AND THE CURVE IS WHAT BOUNDS THE SAVING

**A single iteration count does not bound a saving on its own.** What bounds it is 2c's own
record-length ladder, recomputed at D1's amendment from the spike's JSONL:

| `N` | cold iterations per point | `warm` saving | `random` saving |
|---|---|---|---|
| 96 | 28.27 ± 5.70 | +7.80% | −2.25% |
| 384 | 35.32 ± 2.94 | +31.73% | +18.27% |
| 630 | 40.79 ± 3.73 | +42.28% | +30.28% |

and the reattribution beside it: **the `random` arm carries no proximity information at all and
tracks the cold count just as `warm` does**, so roughly **30 of the 42.28 points are cold-start
difficulty** and **12.00 are proximity**. §11.2's threshold is **30%**.

**THE BOUND FOLLOWS FROM THE CURVE AND NOT FROM ARITHMETIC ON THE ANCHOR.** At 2c's shortest rung
— 28.27 cold iterations — the mechanism returned **+7.80%**, a quarter of the threshold. So a real
reading in that neighbourhood bounds the saving below the threshold **without measuring the saving
at all**, which is (j6): compute the maximum the unmeasured region could be worth before measuring
it.

**AND THE CURVE'S OWN LIMIT IS STATED, BECAUSE IT IS THE PLACE THIS ARGUMENT IS WEAKEST.** The
ladder moves `N` and `N` moves both quantities at once; it is not a curve of saving against
difficulty at fixed `N`. **The honest form of the bound is an interval, not a point estimate**, and
the spike says so in its verdict rather than quoting a single implied percentage.

**What this changed:** the reading's *placement*, not its value, is the deliverable. The
predictions file states bands on the reading and a decision clause for each band, and it commits
them before the run.

### F5 — (a3)/(i12) THE OPENER IS ZARR-ONLY, SO THE CONVERSION IS AN INSTRUMENT

`opener_registry` has exactly one member: `_open_zarr`, registered at
`src/metamer/batch/input.py:188`. The module docstring states netCDF is **deferred** and that the
registry exists so adding it is *"a registration and not a refactor"*. Real gridded products ship
as netCDF, or over an authenticated OPeNDAP endpoint.

**So the spike has a conversion step, and the conversion is part of the instrument**, not
preparation:

- it **chooses the chunking**, which sets `chunk_shape(handle)`, `read_amplification`, and
  `assembly_spans`' behaviour. §11.1 requires **rechunking along time only**;
- it fixes the dtype, which the record measures as a hidden fixture parameter;
- (j8)'s second register: **a rate recorded without its workload can be quoted and cannot be
  reproduced.** The chunking is part of that workload.

**What this changed:** the conversion's parameters — source file list, chunk shape, dtype, the
spatial box, any decimation — are **recorded in the spike's artifact**, and the conversion script
is committed beside it as the instrument it is.

### F6 — THE INPUT PATH BREAKS BEFORE THE STORE EXISTS, AND IT LANDS ON 2e's EXIT-CODE COLLISION

**This is the finding the brief predicted, traced to its line and its exit code — and it was
MEASURED on 2026-09-07, twice: once on a synthetic `latitude`/`longitude` fixture and once on the
real DUACS store.** The paragraphs below were written from reading; the measurement is beneath
them and it agrees, at a line number one off the one the reading predicted.

The contract, at `src/metamer/batch/input.py:308–318`, requires exactly three dimensions,
`dims[0] == "time"`, and a strictly increasing decodable time axis. **It says nothing about the
other two names**, and its own message calls the mapping positional.

`tiling.py` names them literally, at three call sites:

| line | site | form |
|---|---|---|
| 904–905 | `read_amplification` | the span tuple `("y", …), ("x", …)`, then `by_dim[dim]` |
| 932–933 | `assembly_spans` | `by_dim["y"]`, `by_dim["x"]` |
| 974–975 | `assemble_tile` | `array.isel(y=…, x=…)` |

`run.py` calls them in this order: `open_input` (815) → `check_input_contract` (816) → …
→ `read_amplification(handle, tiles[0])` (1094) → store creation (1107) → `assemble_tile` (1159).

**So the first failure is inside `read_amplification`, at `by_dim["y"]`, and it is a `KeyError` —
raised before the store is created.** `__main__` catches `(ValidationError, InputContractError)`
and nothing else (`src/metamer/__main__.py:196`), so a `KeyError` escapes as an unhandled
exception and **CPython exits 1**.

> ## AND EXIT 1 IS NOT A FREE CHOICE — IT IS THE COLLISION 2e OWNS
>
> The taxonomy defines **1** as `COMPLETED_WITH_FAILURES`: *a run that finished with a failure
> rate above threshold*, whose map is written and whose store is resumable. This run finished
> nothing and wrote no store. **A resuming script that branches on 1 would resume from a crash,
> and here there is not even a store to resume.**
>
> **THE TWO OPEN DEFECTS COMPOSE, AND NEITHER RECORD SAYS SO.** The dimension-name defect is
> filed as *"dies in assembly without exit code 4"*; the exit-code collision is filed against 2e
> as *"harmless while 1 has no producer"*. **The first is a producer of the second.** It is
> reachable today, by a user pointing the shipped CLI at an ordinary `latitude`/`longitude`
> product — which is the one input the whole package exists for.

> ## MEASURED, 2026-09-07 — AND THE READING WAS RIGHT ABOUT THE MECHANISM AND ONE LINE OUT
>
> `pixi run python -m metamer <config> <store>`, on a 60 × 4 × 4 zarr whose dims are
> `(time, latitude, longitude)`:
>
>     File "/workspace/src/metamer/batch/run.py", line 1094, in run
>       amplification = read_amplification(handle, tiles[0])
>     File "/workspace/src/metamer/batch/tiling.py", line 907, in read_amplification
>       read *= _chunk_points(start, stop, by_dim[dim], sizes[dim])
>     KeyError: 'y'
>
> **Exit code 1. No store created** — `ls` on the store path returns *No such file or directory*.
> **Stage 4a passed**, as predicted: the contract accepted the input and reported on it.
>
> **Then the same run on the real DUACS store**, 396 × 15 × 20: **byte-for-byte the same
> traceback, the same line, the same exit code, the same absent store.** The finding is not a
> property of a fixture.
>
> **THE READING SAID LINE 904/906 AND THE MEASUREMENT SAYS 907.** Recorded rather than quietly
> corrected: the record's own citation of these sites says 973 for the `isel` that is now at
> 974–975, so this file is the third document to carry a line number for this defect and the
> second to carry a stale one. **A line number is a copy of something the file already knows**,
> and every copy of it here has drifted. What does not drift is the call and the key.

**What this changed:** the spike expects this failure, records it as a reading rather than as an
accident, and **does not fix it.** Both closers named in the record — stage 4a enforces the names,
or the tiling path goes positional — are scope decisions, and (a) is unowned. See §5.

### F7 — (i2)/(a2b) THE INSTRUMENT MUST BE SHOWN ABLE TO RETURN A DIFFERENT NUMBER

**A low reading is the outcome that would end this line of work, and a low reading is exactly what
a silently broken pipeline produces.** Every point falling to a design precheck, a masked block, a
misread cap or an empty point set returns "the fits are easy" and "the instrument is not
measuring" as the same small number — (a0)'s fifth register, at a rate rather than at a counter.

**The control is a cold run through the identical harness on 2d's rebuilt version-2 field**, whose
answer is known: **42.08 per point over 384 points**, or its stride-2 subgrid over 96. The field is
rebuildable — `fields.build_field` at `FIELD_SEED = 20_260_830`, construction version 2, rung
`easy` — and the suite already carries a byte guard on its digest, so a rebuild that drifted would
fail loudly rather than quietly.

**Priced at the 96-point subgrid it costs about forty minutes** (see F8) and it is what makes a low
real reading a statement about the ocean rather than about the plumbing. **It is not optional.**

**AND THE OUTCOME HISTOGRAM IS REPORTED IN FULL, INCLUDING ITS ZEROS.** (a2b) at a count: *"zero
cases" is a claim about the instrument until proven otherwise.* Real data has land, permanent ice
and gaps; `fields.iteration_count`'s `points` counts only points with a live cell, so **"384
points" and "384 ocean points" are different facts that print the same way**. The artifact carries
the mask fraction, the counts of `NOT_ATTEMPTED` and of every non-`OK` outcome, and the number of
points that produced no fitted cell at all.

**AND `ok_only` IS A CHOICE THE ANCHOR ALREADY MADE.** `iteration_count(ok_only=…)` differs by
0.04 on the simulated field, where almost nothing fails. **A capped cell contributes `max_iter`,
which is 200** (`optimize.DEFAULT_MAX_ITER`), so on real data the two readings can separate by far
more than a rounding error, in the direction that flatters the "real fits are hard" reading. **Both
are reported, and the comparison against 42.08 uses the all-cells figure, which is what 42.08 is.**

### F8 — (a5b)/(j8) THREE CONSTRAINTS BIND THE POINT COUNT AND THE RECORD LENGTH — AND THE ONE THAT BINDS IS NOT THE COST

**Solve them together and name the one that binds**, because each is satisfiable alone in the
paragraph where it is discussed.

**Constraint 1 — cost.** From the difficulty rung's own cost block: `cold_seconds = 9949.73` for
`cold_ok_total = 16143` iterations → **0.616 s per iteration**, at `N = 630`, `M = 3`,
`KalmanEngine`, one thread, on a host the gate passed at 2.13 with a live session on the same
cores. The verdict records the seconds as running **25% over** the cost basis. **That rate belongs
to that workload** (j8's second register) and it scales with `N`. Planning arithmetic:

| points | cold iterations/point | seconds at 0.62 s/iter |
|---|---|---|
| 384 | 15 | ~1.0 h |
| 384 | 42 | ~2.8 h |
| 96 | 42 | ~0.7 h |

**Cost does not bind.** A 384-point cold run is one to three hours against a 30 h ceiling that
priced a 15-hour rung.

**Constraint 2 — comparability in `M`.** Fixed by F2: the shipped candidate set, `M = 3`.

**Constraint 3 — comparability in `N`, and this is the one that binds.** The anchor is at
`N = 630`, which at the 31-day cadence of 2d's fixture is **53.5 years**. **Satellite altimetry
begins in 1993**, so a real gridded SLA product carries about **33 years**: roughly **400 monthly
samples**, or ~12 000 daily. **`N = 630` is not reachable from real altimetry at monthly cadence
at all.**

Three ways out, and they are not equivalent:

| option | `N` | what it costs |
|---|---|---|
| **monthly, whole record** | ~384–400 | lands on the ladder's **measured middle rung** (35.32 iterations, +31.73%), which is an anchor rather than an interpolation — (a4)'s *a point between two measured points is not measured*, satisfied for free |
| **~19-day cadence, whole record** | 630 | matches the anchor's `N` exactly, but the cadence is a decimation nobody operates at, and a real product's own sampling is part of what makes real fits real |
| **daily, whole record** | ~12 000 | ~19× the cost per iteration and off every anchor. Not proposed |

**RECOMMENDED: monthly, whole record, `N ≈ 384`, comparing against the ladder's 35.32 rather than
against 42.08 — and reporting both.** The reading is then on a measured rung of 2c's own ladder,
which is the placement F4 says is the deliverable. **This is a deviation from the brief's `N = 630`
and it is named as one rather than absorbed**; the brief's own clause — *per-point iterations
compare only at equal `M`* — has an unstated twin in `N`, and the twin is the binding constraint.

> **MEASURED 2026-09-07, AND `N` IS 396.** The DUACS monthly product runs **1993-01 to 2025-12**,
> which is 396 monthly means — **3.1% longer than the ladder's measured 384 rung**, and reachable
> without decimating anything. The reading is therefore compared against **35.32 ± 2.94** as its
> nearest measured rung, with 42.08 reported beside it as the same-instrument anchor at a record
> length real altimetry does not have. **Neither comparison is an interpolation**, which is what
> (a4)'s *a point between two measured points is not measured* was asking for.

### F9 — (j5) NO INSTRUMENT YIELDS ALL THREE READINGS, SO THERE ARE TWO PASSES AND THEY ARE NOT CROSS-CHECKS

The brief asks for iterations, the outcome distribution, **and Hessian condition numbers**.

**The store carries the first two and not the third.** `store._array_specs`
(`src/metamer/batch/store.py:650–714`) declares `/primitives/iterations` (uint16, sentinel 65535),
`/status/outcome` and `/status/point_outcome` — **and no condition-number array anywhere.** `κ`
exists only as `optimize.SeriesFit.hessian_cond` / `FitResult.hessian_cond`, consumed in-process
at `batch/audit_report.py:832` (`kappa_bin(cold.hessian_cond)`).

So the spike has two passes:

| pass | instrument | reading |
|---|---|---|
| **primary** | shipped `metamer run`, cold, single pass; read with `fields.iteration_count` and a direct read of `/status/outcome` | iterations per point and per cell; the full outcome histogram |
| **secondary** | in-process `fit` over a **subsample** of the same points, same objective, same engine, same cap | `hessian_cond` per cell, and its distribution against `HESSIAN_COND_LIMIT` = 2²⁶ |

**AND THE SECOND IS NOT A CROSS-CHECK OF THE FIRST.** (j5): agreement would be unsurprising and
disagreement would be uninterpretable, because the two differ by code path — which is exactly the
40.79/43.94 gap the record already refuses to reconcile. **The secondary pass's iteration counts
are not quoted as a second reading of the primary quantity**, and the artifact says so beside
them.

**AND (h3) APPLIES TO THE `κ` READING BEFORE IT IS INTERPRETED.** `optimize.HESSIAN_COND_LIMIT` is
`eps^(-1/2) = 2²⁶`, and `optimize_series` reports `DEGENERATE_HESSIAN` rather than `OK` above it.
So a `κ` distribution taken over `OK` cells **has already been filtered at the boundary anyone
would want to cut it at**, and a reassuring "no ill-conditioned cells" is a property of the
selection. The reading is taken over **every** cell the secondary pass fits, with the
`DEGENERATE_HESSIAN` count reported as its own number.

### F10 — (i2)/(a0) THE CONVERSION MUST NOT MANUFACTURE THE FINDING AWAY

The obvious way to make a real product open is to rename its dimensions to `y` and `x` during the
conversion. **That makes F6 unreachable**, and the spike would report a clean run on a path that is
still broken for every user who does not know to rename.

**The conversion preserves the product's own dimension names.** The run that fails on them is a
reading; a run that succeeds because we renamed them is a reading about our rename.

> **MEASURED 2026-09-07: THIS PRODUCT EXERCISES ONE FREEDOM AND NOT THE OTHER.** Its dims are
> `("time", "latitude", "longitude")` — the name freedom, and F6 fires on it. Its **latitude is
> INCREASING** (20.0625 → 34.0625) and so is its longitude, so **the decreasing-latitude case
> OQ20 names first is NOT exercised here.** Recorded plainly, because a spike that reported
> *"run on a real product"* would otherwise read as having closed OQ20's first candidate, and it
> has not. A descending-latitude product remains untested by anything.

**AND THE DURABLE FIX IS A FIXTURE, NOT A CALL SITE** — (i12), and it is OQ20's own answer.
`tests/test_decimate.py` already carries the first fixture in this project whose spatial dims are
named otherwise. Nothing yet varies **coordinate monotonic direction**, and a **decreasing latitude
axis is the ordinary case in real altimetry** — so a real product is likely to exercise both
freedoms at once, and the second one *yields a plausible answer rather than an error*. **The spike
records which freedoms its product actually exercises**, which is the cheap half of OQ20's sweep
and is a by-product rather than a widening of scope.

### F11 — (a2d) THE ARTIFACT CARRIES ITS INSTRUMENT, BECAUSE THIS MEASUREMENT CANNOT BE A TEST

A one-to-three-hour run cannot be a test and its recorded output will be quoted. The artifact
therefore carries, beside every number: the product and its version or DOI; the source files; the
conversion's chunk shape and dtype; the spatial box, the stride and the resulting point count; the
**dimension and coordinate names as the product ships them**, and each coordinate's monotonic
direction; the variable name; `N` and the cadence; `M` and the three `candidate_spec_hashes`;
`signal_terms`; `criteria`; `ALGORITHM_VERSION`; `max_iter`; the engine; the **observed** thread
limits; the host reading from `bench.host.quiet_check`; and both the all-cells and OK-only
iteration figures.

**And the check that reads it fails when a named default has moved** — which is the practice 2d
recorded as owed and did not install. The spike installs it for its own artifact.

### F12 — (j8) THE QUIET GATE IS USED UNCHANGED, AND ITS SUBJECT IS STILL WRONG

`bench.host.quiet_check` gates rather than annotates, and `host.REFUSAL` is the refusal. **Open
question 22 says its subject is wrong** — `/proc/loadavg` is the host, and this container used
5–7% of four cores while the gate read 1.88 to 5.32 — and the record measures what that cost: the
difficulty rung was refused three times with the container idle, roughly **a working day of
waiting** for a 15-hour measurement.

**The gate is used unchanged.** Changing a gate on the evidence of the session it inconveniences
is how a gate becomes a formality, and the record says so in those words. What is carried instead
is the mitigation already written down: **iterations, the outcome distribution and `κ` are
host-independent; only the cost block is contaminated**, and a loud-host run still yields every
reading the brief asks for, with the seconds marked.

**The repair — read the cgroup's `cpu.stat`, keep the host reading as a secondary diagnostic — is
not taken here**, and if it is taken it gets its own validation against known-good **and**
known-bad, as the stall gate's did.

### F14 — MEASURED 2026-09-07: `unique_dt = 6`, AND A FIXTURE FACT BECOMES A MEASUREMENT

Stage 4a's own report on the real store, through `input.check_contract`:

    n_time 396   n_y 15   n_x 20   calendar proleptic_gregorian
    source_dtype float32  units "days since 1993-01-01"
    unique_dt 6  t_start 1993.0  t_end 2025.9151  median_dt 0.08470

**`unique_dt = 6` is exactly what the handoff predicted and nothing here had ever seen.** §5's
fixture facts say: *"Calendar months are 28–31 days, so 50 years of month-start timestamps give
`unique_dt = 6` … **Only a synthetic `2000 + arange(n)/12` gives 1**, and that is the shape every
synthetic fixture and the spike harness use — so any claim resting on 'F and Q are built once per
series per iteration' is a claim about the fixture, not about the workload."*

**IT WAS AN ARGUMENT AND IT IS NOW A READING**, taken through the shipped contract on the shipped
product. **This is the first real time axis this project has fed through stage 4a.**

**AND IT BEARS ON THE COST BASIS, NOT ON THE ITERATIONS.** The `F`/`Q` amortization has six
distinct timesteps to build rather than one, so the **per-iteration seconds measured on every
synthetic fixture are an underestimate for real data** — while the iteration count, which is what
the reading is, is untouched. (j8)'s second register, arriving from the fixture's side: the rate's
denominator was a property of the synthetic axis all along. **The spike's cost block says so
rather than reporting a surprise.**

### F13 — (i2b)/(i11) THE PREDICTION IS A BAND, NOT AN ORDERING, AND ITS CLAUSES FIRE BOTH WAYS

There is one field and one reading, so **there is no ordering to extend and the prediction is a
band** — the form the brief requires. The refutation clauses are stated in both directions, because
(i11): a one-sided clause forfeits half the value, and 2c's own S2 is the near miss that proves it.

**THE NUMERIC BAND IS NOT COMMITTED IN THIS DOCUMENT**, because it depends on `N` and on the
product, and both are open (§5). It is committed in
`realdata-spike-predictions.json` **after** the product is fixed and **before** the run. What is
fixed now is the decision structure, which does not depend on either:

| reading (cold iterations per point, `M = 3`, all cells) | what it means | what happens next |
|---|---|---|
| **≲ 20** | real fits are easier than 2d's *signal-free* construction. The saving is bounded near zero by the ladder; §11.2's 30% threshold cannot be met | **the coherence half is moot and is not run.** D1 goes back in play, with D6, D9 and D10 behind it |
| **20 – 32** | real difficulty sits at or below 2c's shortest rung, where the mechanism returned +7.80% | the threshold is at risk and the bound is the finding. The coherence half becomes a decision, not a default |
| **32 – 45** | real difficulty is inside 2c's and 2d's range | **the coherence half is worth its cost** — and it is still not started without checking in |
| **≳ 45** | real fits are harder than any fixture measured here | the anchors are all below the subject; the ladder's placement is an extrapolation and must be said to be one |

**AND THE SURPRISE DIRECTION IS THE HIGH ONE.** The whole record has been braced for *"real fits
are easy and the saving is bounded near zero"*; a reading above 45 would say every simulated
fixture in this project is easier than the thing it stands in for, which changes what 2d's null is
a null *about*. That clause exists because it is the one nobody is watching for.

---

## 3. WHAT THE FIRST HALF IS, IN ONE TABLE

| | |
|---|---|
| **arms** | one: **cold**. No warm start, no coarse grid, no spiral, no barrier, no N2 |
| **primary instrument** | the shipped CLI, one cold pass, `warm_start.enabled = false` — read off the store by `fields.iteration_count` |
| **secondary instrument** | in-process `fit` over a subsample, for `κ` only, explicitly not a cross-check |
| **control** | the same primary instrument on 2d's rebuilt v2 field, expected 42.08 per point |
| **readings** | iterations per point and per cell (all cells **and** OK-only); the full outcome histogram with its zeros; the `κ` distribution with its `DEGENERATE_HESSIAN` count; the mask fraction and the point count |
| **comparators** | 42.08 (same instrument, `N = 630`), 24.38 (same instrument, signal-free), and 2c's ladder 28.27 / 35.32 / 40.79 at `N = 96 / 384 / 630` for placement |
| **cost** | 1–3 h for the real run, ~0.7 h for the control, both priced in seconds **and** reported in iterations |
| **gate** | `bench.host.quiet_check`, refusing on `quiet is False`, unchanged |
| **not in scope** | the coherence half; the two owed wirings; 2e; any repair to the input path; any change to the quiet gate |

**Ordering:** control first, then the real run. The control is cheaper, and an instrument that
cannot reproduce 42.08 has nothing to say about a real field.

---

## 4. WHAT THIS SPIKE MUST NOT BE WRITTEN UP AS

Carried from the brief and from 2d's close, because it is the failure mode this particular
measurement invites:

- **A cold iteration count is a bound on the saving, not a measurement of it.** Nothing here
  measures what warm-starting does on real data.
- **A single product is a single product.** The ocean is not one regime, and a box is not the
  ocean.
- **2d's null does not transfer by being quoted.** Whether it transfers is the second half.
- **The standing limitation survives a clean result**, exactly as it survived 2d's.

---

## 5. THE PRODUCT — DECIDED 2026-09-07, AND IT NEEDED NO CREDENTIALS

**The product is CMEMS `SEALEVEL_GLO_PHY_L4_MY_008_047`, dataset
`cmems_obs-sl_glo_phy-ssh_my_allsat-l4-duacs-0.125deg_P1M-m_202411`** — the reprocessed DUACS
monthly-mean gridded sea level anomaly, 0.125°, 1993-01 to 2025-12. **This is real altimetry, so
the standing limitation is addressed as it is worded** rather than by a substitute.

**AND THE CREDENTIAL BLOCKER DISSOLVED ON MEASUREMENT.** The pre-flight expected a Copernicus
Marine account. The ARCO store's `.zmetadata` returns **200 anonymously**; only bucket *listing*
is 403, which is ordinary. So the key layout is **computed from the store's own consolidated
metadata** rather than enumerated, and nothing is authenticated.

**THE FETCH IS ITS OWN INSTRUMENT AND IT IS COMMITTED**:
[`realdata-spike-fetch.py`](realdata-spike-fetch.py), with its record in
[`realdata-spike-fetch-provenance.json`](realdata-spike-fetch-provenance.json).

**IT ADDS NO DEPENDENCY, AND THAT WAS A DECISION.** `fsspec`'s HTTP filesystem needs `aiohttp`,
which this environment does not have. `pixi add aiohttp` re-solves the lock — **the lock every
committed anchor was measured under, and whose numpy and BLAS 2d's field digests are pinned to,
with a documented failure mode saying so.** Changing the environment to obtain the fixture would
change the instrument, so the store is mirrored over `urllib` against the published zarr v2 key
layout instead. **The saving is not effort; it is that the control run's expected value survives.**

**The fixture, as built:**

| | |
|---|---|
| box | lat **20.06–34.06 °N**, lon **39.94–20.94 °W** — open subtropical North Atlantic, chosen inside one lat-chunk and one lon-chunk |
| grid | **15 × 20 = 300 points** at stride 8, so **1° spacing** |
| record | **N = 396** monthly means, 1993-01 to 2025-12, `unique_dt = 6` |
| missing | **zero.** No land, no ice, no gaps: `series_all_missing = 0`, `missing_fraction = 0.0` |
| dtype | `float32` on disk, cast from the product's int32 × 1e-4 |
| dims | `("time", "latitude", "longitude")`, both spatial axes **increasing** |
| fetched | 401 keys, 182.6 MB, digest recorded |

> **THE ZERO MISSING FRACTION IS A PROPERTY OF THE BOX, NOT OF THE OCEAN**, and it is the
> flattering direction: it removes the land-and-gap confound from the difficulty reading, and it
> also removes every `NOT_ATTEMPTED` from the outcome distribution the brief asks for. **So the
> outcome histogram this box can produce is narrower than a global run's**, and a clean one here
> is not evidence that a real global run is clean. Stated before the run, not after it.

**WHAT REMAINS OPEN IS NOT THE PRODUCT.** Two fixture decisions are still owed and both change
what the number means; they are in the session report and are not taken here.
