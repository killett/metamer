# Phase 1 → Phase 2 handoff

**Written 2026-08-07 at the close of Phase 1.** This is the one document a fresh session
starting Phase 2 should read. It is self-contained: nothing here requires reading
`PROGRESS.md`'s history, the Phase 1 plan, or any commit message.

`PROGRESS.md` remains the running notebook and the index of active work. **This document
is the transferable part** — the method, the standing rules, and the facts that outlive
Phase 1's code.

---

## 1. The pre-flight, (a)–(k)

**Run this against any implementation brief before writing code.** It is the most valuable
artifact Phase 1 produced, and it exists because of a measured pattern: **across Tasks 8–17,
nearly every substantive defect passed the brief's own tests.** Brief-generated tests
validate the brief's *model* of the problem, so they cannot detect that the model omitted
something. A passing suite is not evidence the brief is right.

Every entry below has at least one worked instance from this project.

### (a0) A FILL VALUE A SUCCESSFUL RUN CAN PRODUCE MAKES AN EMPTY STORE READ AS A COMPLETE ONE

> **Any sparse or default-valued storage format elides values equal to its fill.** If the fill
> is a value the write path can legitimately produce, then **"never written" and "written with
> that value" are the same bytes** -- and the absence of data reads as data. **Every fill must
> be a value the writer cannot emit**, and each exception must be labelled with why it is safe.

**This is the most dangerous single defect this project has found, and it is first because it
generalizes past zarr** -- to any format with a default, a sentinel, a sparse encoding or a
"missing means" convention.

Worked instance, Phase 2a Task 8, measured. `Outcome.OK` is code **0**; zarr's default
`fill_value` for an integer array is **0**; zarr **does not write a chunk equal to the fill
value**. So a store created with the default fill and a correct one are **byte-for-byte
identical on disk -- both pure metadata, zero chunk files** -- and the defaulted one reads back
as a complete, wholly successful run over the entire grid. **It defeats precisely the
invariant that `NOT_ATTEMPTED`-as-initial-value exists to provide**, which is what makes it
worse than an ordinary plausible-number failure: the guard and the defect are the same
mechanism.

**The exception is what a good one looks like.** `/primitives/iterations` is uint16 and cannot
carry NaN; the dtype is fixed at store creation and the array feeds no arithmetic. It is
therefore **exempt, named, and given a sentinel of 65535 rather than silently left at 0** --
justified, labelled, and outside the range the writer can emit.

#### AND THE SAME RULE AT A COMPARISON: "EXCLUDED" AND "MISSING" MUST NOT BE ONE OBSERVATION

> **An exclusion list must assert the PRESENCE of the excluded keys in both artifacts.**
> Otherwise the exclusion silently covers absence, and a key that vanished from one side reads
> exactly like a key that was deliberately not compared.

**This is the fill-value rule in a new register**, and it generalizes past storage to every
comparison with a carve-out: a diff with an ignore list, a golden file with skipped fields, a
schema check with optional keys. In each, "we chose not to compare this" and "this is not there"
produce the identical result, and only one of them is intended.

Worked instance, Phase 2b Task 1. Exit criterion 1 compares two stores byte for byte; `floor` is
measured fresh every run and therefore differs between two runs of one configuration, so it is
excluded by name. **Without an assertion that `floor` is present in BOTH stores**, a change that
dropped the attr entirely would leave the criterion green — and the attr's whole purpose is to be
readable from a store later.

#### AND THE THIRD REGISTER: "REQUIRED" AND "NULLABLE" ARE INCOMPATIBLE UNDER A PRESENCE GUARD THAT TESTS FOR `None`

> **A guard that treats `None` as absence cannot express a field whose `None` is meaningful.**
> Widening the guard to accept `None` makes **every** field nullable and destroys the presence
> check for all of them. **The correct mechanism is the schema version**: a store written before
> the field existed is refused **by version**, not by inspection.

**The tempting repair is the damaging one**, which is what earns this its own line. The guard
looks like it has a small bug — one key it cannot handle — and the one-character fix (`key not in
attrs` instead of `attrs.get(key) is None`) trades a per-field problem for a whole-schema one.
The presence check is the thing protecting every *other* required key from being silently absent.

Worked instance, Phase 2b Task 3. `store.create_store` refuses on `attrs.get(key) is None`, and
`memory_budget_requested_gb` records *"the config named no budget"* as `None`. So it cannot join
`REQUIRED_ATTRS`, and the absence of the key in an older store would be read through `attrs.get`
as "the budget was defaulted" — the fill-value defect exactly. `SCHEMA_VERSION` 5 is what makes
the older store's silence a refusal instead.

> **AND THE LEDGER'S EXCEPTION IS DOCUMENTED WITH A TEST ASSERTING THE EXCEPTION, WHICH IS THE
> SHAPE THAT MATTERS.** The bump ledger's rule is *"each bump's field is a required attr"*, and
> this is the first bump where it does not hold. **An undocumented exception becomes a
> precedent; a documented one stays an exception.** The test asserts
> `"memory_budget_requested_gb" not in REQUIRED_ATTRS` with the reason beside it, so removing the
> exception fails rather than passing quietly as a tidy-up.

#### AND THE FOURTH REGISTER: A FALLBACK MAKES "DID NOT HAPPEN" AND "HAPPENED AND WAS DISCARDED" ONE OBSERVATION

> **Any rule that falls back to a default on failure erases the distinction between "the
> expensive thing was never attempted" and "it was attempted and rejected".** Both leave the
> default behind, and the default is what a fresh run writes. **Record that a mechanism was
> CONSULTED, separately from whether it produced the answer.**

**This is the fill-value rule with the fill supplied by a fallback rather than by a format**,
and it is the same class as `NOT_ATTEMPTED` versus `SCREENED_OUT` and as "excluded" versus
"missing": one observation standing in for two facts, only one of which is intended.

Worked instance, Phase 2b Task 5. A calibrated slope outside its validation band is not used
and the run records `tile_side_basis = default` — which is also what a run that never
calibrated records. **A store that spent 26.5 h measuring would have been
byte-indistinguishable from one that measured nothing.** The repair is a `calibration`
provenance block written whenever a calibration was **consulted**, carrying the measurement and
a `rejected` reason; its **absence** is what means "none was consulted", on the `source_*`
precedent. **And no schema bump is owed**, which is the other half worth recording: a bump is
for a question an older store *cannot answer*, and every earlier store's silence here is
unambiguous because nothing before that task could consult a calibration at all.

#### AND THE FIFTH REGISTER: A ZERO READING IS NOT EVIDENCE OF ABSENCE

> **A counter at zero and a counter that is not maintained are the same observation. So are
> "the effect did not happen" and "the effect has not happened YET".** Never infer that an
> instrument is dead, or that a quantity is absent, from a zero — **construct the effect and
> confirm the reading moves** (i2). A structural explanation for a zero is the most dangerous
> possible reading, because it is tidy, it sounds mechanical, and it retires the question.

**Phase 2b Task 8i, 2026-08-17, caught inside the task that would have written the bug.**
`/sys/fs/cgroup/memory.stat` read **`pgscan 0`, `pgsteal 0`** while `/proc/vmstat` showed
**7 897 171** pages stolen system-wide, and the file was demonstrably live (`anon` 673 MB,
`pgfault` 2 236 643) — which made a **structural** story fit perfectly: this container is `0::/`
with `memory.max = max`, so it never triggers cgroup-internal reclaim, so the counter is not
maintained here. **That paragraph was already half-written when the counter was tested instead:
it moved, 45 120 → 81 317, a delta of 36 197 pages.** The zero meant *"no reclaim attributed here
yet this boot"*.

**THE SAME FAMILY, THREE TIMES NOW, AND THE TELL IS ALWAYS THAT TWO STATES SHARE ONE READING:**
a zero-filled fixture that zarr never writes a chunk for, so a read served entirely from the fill
value returns correct-looking values and touches nothing; an empty store whose fill value a
successful run can also produce, so incomplete reads as complete; and now a reclaim counter whose
"nothing happened" and "nothing counted here" are the same integer. **Only constructing the
effect separates them**, and the cost of constructing it is always far below the cost of the
structural claim being wrong — here it would have sent the task to a worse instrument for a
better-sounding reason.

### (a1) RE-DERIVATION AT RESUME IS THE HAZARD, NOT AN UNHASHED ANCESTOR

> **A stored geometry READ BACK from the store is safe, however it was originally
> computed. One RE-DERIVED from current inputs is a gate, whether or not those inputs are
> hashed.** Any value that names **where** data goes — an array index, a key, a shard
> coordinate, a partition — is an identity claim; a hash governs **whether** work is reused
> and says nothing about **where it lands**.
>
> **So the repair has a default: read it back rather than re-derive it, and guard only where
> reading back is impossible.**

**This supersedes the weaker form the finding was first written in** — *"any derived index is
a gate, and must be checked even when its inputs are excluded from every hash"* — which is
true and over-broad. It sweeps in every geometry with an unhashed ancestor, most of which are
never recomputed at all, and it does not say what to do. The sharper version came out of the
sweep below: the operative condition is **re-derivation**, and the two halves of the store
divide on exactly that line.

**This sits beside (a0) rather than under (a2), and the difference is what makes it its own
line.** (a2) asks whether a *named* gate is populated by the thing it claims to identify.
This asks about a value nobody declared a gate at all — one computed on the fly, from inputs
that were **correctly** left out of the hashes, and then used to address storage.

Worked instance, Phase 2a Task 10. The completion bit is `[ty, tx]` with
`ty = y_start // tile_side`, and `tile_side` derives from **`memory_budget_gb`, which is
run-relevant and therefore in neither `fit_hash` nor `compat_hash` — deliberately, so that a
burst-to-cloud resume is a resume rather than a rerun** (§13.3, §15.5). **That exclusion is
exactly what lets the grid re-tile silently under a fully-set bitmap**: every hash matches,
the gate passes, the tiles move, some points are never written and others twice, and the
store reports itself complete.

**The repair's asymmetry is the part to record, because "refuse any change" is the tempting
rule and it is wrong.** Refusing a budget change would break the very workflow the exclusion
exists for, so the rule is over the **derived** quantity, not the input:

| stored vs derived | action | why |
|---|---|---|
| equal | proceed | — |
| **stored < derived** | **adopt the stored side** | a smaller tile subdivides the fixed shards safely and is inside the requested budget |
| **stored > derived** | **refuse**, naming both sides and the store's recorded budget | the shards were fixed at creation; adopting the larger tile would silently exceed the budget, and writing sub-shard regions would make every write a read-modify-write |

**And the sweep is what sharpened the rule.** Run over this store on 2026-08-13 — chunk and
shard shapes, the coordinate extents, the `b` axis, the `m`/`p` axes. The **chunk
subdivision** depends on a code constant in no hash and is **not** an instance, because every
write goes through the chunk grid the store already declares: it is read back, never
recomputed. The **tile side** is an instance precisely because the runner recomputes it from
the current budget, and the **candidate list** is one because `M`, `P_total` and both offset
tables are rebuilt from the requested config at every resume. Results in
[`phase2a-preflight.md`](phase2a-preflight.md); the second instance was load-bearing for
Task 11.

**Where reading back is impossible, the guard is the fallback and it needs the asymmetry
above** — the tile side cannot simply be read back and used, because the requested budget may
not hold it, which is why that one case has three arms rather than one.

### (a) Absolute vs differential — THE CANCELLATION RULE

> **Any quantity constant across the comparison axis is invisible to every test that
> compares along that axis.**

| instance | constant across | what caught it |
|---|---|---|
| REML's Harville constant `(n − rank(X))·log 2π` and `+½log\|XᵀX\|` | `θ` | review, not a test |
| `log\|XᵀX\|` under gaps | `θ` | the restricted-design contract |
| `design_rank` passed to `penalty_terms` as zeros | the **candidate** axis | a surviving mutation, then an absolute AIC recomputed by hand |
| **The hash function itself** (Task 16) | both sides of every comparison | **nothing** — six fence tests passed against a serializer that was silently unstable. Separators, sort order, digest algorithm and truncation length all cancel |

The cure is always an **absolute value, hand-derived**. Task 16 needed *three* golden
hashes, not one, because each payload builder can drift independently: a `run_payload`
filing a `None` fingerprint changed every `run_hash` while every comparison stayed green.

**AND THE RULE REACHES INSIDE A SUM: TWO ERRORS OF OPPOSITE SIGN IN ONE TOTAL ARE INVISIBLE
TO ANY CHECK ON THE TOTAL.** Verify each **term**, never the total. Worked instance, Phase 2b
F2 and F3, found together: `memory.bytes_per_series` multiplied the solver state by `B` when
the code holds it for one series at a time (**−1056 B/series**, 12.1% too high) while its
output-slot term omitted `theta_unconstrained`, `n`, an object-array `init_rung` pointer, and
an int64 rather than uint16 `n_iter` (**+648 B/series**, 33% too low). The total was within
0.5% of a measurement and **neither term was right**. The tell is a formula validated as a
sum against an instrument that also produces a sum.

**AND THE CORRECTION WAS ITSELF CARRIED AS A TOTAL, WHICH IS THE RULE FAILING ONE LEVEL UP.**
F3's magnitude was recorded as **+552 B/series (+46/candidate)** and accepted through planning
and review. Task 0 rebuilt the inventory field by field and got **+648 (+54)** — the four
omissions the finding *names* sum to 54, and 46 is that list with one 8-byte member dropped.
**The recorded number never agreed with the recorded reasoning, and nothing compared them.** So
the repair is not "verify each term once": it is **verify each term of whatever you are about to
write down, including the terms of a correction**, and write the derivation beside the number so
the next reader can do the comparison the author did not.

#### AND THE LIMIT CLAUSE: A DIFFERENTIAL CANCELS A CONSTANT, NOT A TERM THAT GROWS

> **A differential cancels a CONSTANT offset. It does not cancel a term that grows during the
> measurement window.** Allocator arenas, caches and warm-up are growth, so an **in-process**
> differential measures the process's history plus the subject.

Worked instance, Phase 2b Task 8. A per-tile resident-set measurement was taken inside pytest,
justified by this very rule: whatever the process already holds cancels across the tiles. **The
constant cancels and the growth does not.** The same sixteen tiles, four ways:

| condition | growth |
|---|---|
| in-process, run alone | 63 kB/tile |
| in-process, after its own module | 96 kB/tile |
| in-process, inside the full sweep | past any bound |
| **fresh subprocess** | **143 kB/tile, and it reads that whatever ran before** |

**Only the last is a property of the loop.** The test passed alone and failed the sweep twice
before the instrument was changed rather than the bound.

**AND THE PART THAT GENERALIZES FURTHEST IS NOT THE MEMORY.** Every other machine assertion in
this repo already used a subprocess, and `memory.py` carries a bare launcher for exactly this.
The author reasoned past an established convention with a local argument. **A local
justification that contradicts an established pattern is evidence against the justification** —
find out why the pattern exists before deciding you are the exception.

#### AND THE SECOND LIMIT CLAUSE: A DIFFERENTIAL DOES NOT CANCEL A TERM THAT DECAYS — AND DECAY IS AN INTERACTION

> **A differential cancels a constant offset. It does not cancel a term that GROWS during the
> window, and it does not cancel a term that DECAYS across it.** Any two readings separated in
> time carry **the interval** as a hidden variable, and a run whose duration correlates with its
> independent variable has that interval **confounded with the effect**.
>
> **BUT THE DECAY HERE NEEDS TWO THINGS AT ONCE: memory pressure AND elapsed time.** Neither
> alone produced any loss; both together lost **135 MB**. **The operational rule — hold run
> length constant across a ladder's points, or record it as a covariate — stands and is better
> founded. The mechanism is an INTERACTION, not a property of time.**

**Promoted at Task 8a on 2026-08-17 and CORRECTED BY TASK 8i THE SAME DAY.** The original was
generalized from a single control: two masked runs at side 48 differing only in 600 s of sleep,
giving **0.000 MB** and **92.115 MB**, on a box that happened to sit at **1906 MB available**.
**Re-run at 9307 MB available, the same 600 s gave 0.00 MB.** The 2×2 that settles it:

| | idle 0 | idle 600 |
|---|---|---|
| **no pressure** | 0.00 MB | **0.00 MB** |
| **pressure** (constructed) | 0.00 MB | **135.50 MB** |

The mechanism is reclaim, and reclaim needs a reason: the kernel takes clean file-backed pages
from a process that has stopped touching them **when something else wants the memory**. A reading
taken later is then smaller for reasons that have nothing to do with the subject — but only when
both conditions hold. The damaged run's working set ended **129.50 MB below its own floor**;
clean runs sat **+5.69 to +6.32 MB above** it.

> **AND THIS IS THE SECOND TIME IN TWO DAYS A PROMOTED RULE HAS BEEN CORRECTED BY THE NEXT TASK'S
> MEASUREMENT** — the first being the "~33%" implied headroom, at 51.29%. **That is the process
> working, not the process failing.** A rule promoted from one run is a hypothesis with a
> citation; what makes the register worth keeping is that the next task measures against it
> rather than around it. **The failure mode to fear is a rule nobody re-measures**, and it is
> invisible precisely because nothing contradicts it.

> **THE CONFOUNDING CASE IS THE DANGEROUS ONE AND IT IS THE COMMON ONE.** A ladder in batch size
> is a ladder in run length: Phase 2b Task 8's five points ran **45.6 s to 1780.1 s**,
> monotonically with B. Contamination therefore lowers the *longer* runs' peaks, which **lowers
> the fitted slope** — so its **1900.9 ± 84.1 B/series is if anything an UNDERestimate**, and the
> disagreement with the analytic 926 is **wider** than recorded rather than explained away.
> Criterion 7's crossover is not clean either: its failing point is its longest run.
>
> **The design rule that follows: hold run length constant across the points being compared, or
> measure the interval and report it as a covariate.** A ladder that varies duration with its
> abscissa is not a ladder in one variable.

### (a2) A NAME IS NOT A GATE

Three instances, each of which reads as a gate and is not one: `metamer_version` in
`FIT_RELEVANT_FIELDS` with nothing in `src/` populating it; `candidates` covered by no hash
while design doc §12.8 assumes enforcement; `data_uri` standing in for the data it names, so
that moving a file invalidated a valid resume *and* editing one in place permitted an
invalid one.

**CLASSIFY BEFORE YOU CHECK. EVERY HASHED FIELD IS ONE OF TWO KINDS, AND THE CHECK APPLIES
TO ONLY ONE OF THEM:**

> - A **REQUEST** — what the user asked for. Which variable, which objective, which seed,
>   which criteria. **Self-reported, and self-reporting is correct**: the field *is* the
>   request, and there is nothing else it could come from.
> - An **IDENTITY** — what something actually *is*. Installed code, a family registry, a
>   dataset on disk. **It must be populated by reading that thing, and self-reporting is the
>   defect.**

Getting this backwards in either direction is a mistake. Demanding an independent source for
a request is incoherent; accepting a self-reported identity is how `registry_version` sat in
the allowlist reading correctly for the wrong reason.

**For an identity field, verify four facts:** **something populates it**; **it derives from
the quantity it claims to identify**; **a change in that quantity actually moves it**; and
**the thing that populates it is not the thing being identified.**

The first three failed differently in the three instances above. The fourth came from a fifth
instance of a new shape: `registry_version` passed the first three cleanly — populated,
derived, moved — **and the value came from the user's config.** Self-reported identity is not
identity.

**THE AUDIT OF THIS PROJECT'S ALLOWLISTS IS CLOSED. Do not reopen it without a new field.**
The sort was run over all fourteen fields on 2026-08-11 and found **exactly three
identities**, all now accounted for: `algorithm_version` and `registry_version` are stamped
from the installed code, and `data_uri` was replaced by `geometry_hash` at Task 3. Everything
else is a request. The table is in
[`phase2a-preflight.md`](phase2a-preflight.md); the rule to apply to a *new* field is the
classification above, not the table.

**AND THE FOURTH FACT IS THE ONE THAT NEARLY FAILED SILENTLY AT THE ONE PLACE IT MATTERS
MOST.** Phase 2b Task 5's cache key digests *"every installed distribution, excluding nothing"*.
**Measured, not assumed: `[d for d in importlib.metadata.distributions() if "metamer" in
d.name]` is EMPTY in a source-layout tree** — metamer runs from `src/` and is not an installed
distribution — so the digest omitted **the package whose behaviour is being measured**. An
instrument whose coverage depends on how a package reached the path reports what is *installed*
and is read as reporting what is *there*, which is the complete-looking-table rule below in a
new place; and "metamer did not change" and "metamer is invisible to this instrument" produce
the identical digest, which is (a0). The map is now built from the distributions **and** from
`metamer.__version__`. **Only running the enumeration would have found it**, which is why the
rule is to measure the instrument's coverage rather than to reason about it.

The check generalizes past hashes to every gate made of a name — a completion bitmap, a
calibration cache key, a warm-start cache key. **`machine_fingerprint` is the live example
of a field whose classification changes with its consumer**: self-reported at its own
boundary, harmless while it reaches `run_hash` alone (provenance, never a gate), and an
identity the moment the calibration cache key reads it.

#### AND (a2) AT THE INSTRUMENT: A GATE CAN BE BLIND BY CONSTRUCTION AND PASS EVERY TEST

> **A gate must be validated against a KNOWN-BAD reading, not merely against a known-good one
> and a threshold.** A threshold set from one measured side answers *"how far from good"* and
> never *"can this counter move at all when the thing goes wrong"*. If the quantity the gate
> reads is not caused by the failure it guards, **no value of the threshold makes it a gate** —
> and it will pass, quietly, forever.

**This is (a2) one level past Task 5's version.** There, an instrument's *coverage* was assumed
rather than enumerated. Here the coverage is total and the **causal link is absent**:
`RSS_STALL_LIMIT_US_PER_S` gates every RSS-difference test on **pressure stall information**,
and PSI `full` counts time the workload was **stalled waiting** on memory. Reclaiming clean
file-backed pages that the workload has **stopped touching** costs no stall at all, because
nobody waits for a page nobody wants. **So the gate could never have seen the failure mode it
was built for.**

Measured, Phase 2b Task 8a: the run that lost **85 MB** of resident set read **0.0876 ms/s** —
*below* the 0.9 ms/s **idle** baseline — and the 600 s control that lost **92 MB** read
**1.2489 ms/s**, forty times inside a 50 000 limit. **Both pass.** The docstring had asked, in
writing, for the rate of the next failure; two failures now answer it, and the answer is that
the rate is not the right quantity.

> **THE CONSTANT IS NOT WRONG — ITS SUBJECT IS.** It is a valid gate on **thrashing**, which is
> what it was built from, and it is not a certificate that an RSS difference is sound. So it was
> **neither widened nor narrowed**; what changed is the claim written next to it.

#### AND THE FOURTH REGISTER, MEASURED 2026-08-21: "THE INSTRUMENT IS BLIND" CAN BE "THE STATISTIC IS DILUTED"

> **Before concluding that a counter cannot see an effect, check whether the STATISTIC taken from
> it can.** A cumulative counter read as an average over a long block divides a brief, intense
> event by the block's own length; the event is in the data and the summary is what lost it.
> **A null from an instrument is a claim about the reduction as much as about the sensor.**

**Phase 2b open question 19, and it narrows (a2)-at-the-instrument above rather than overturning
it.** The claim carried since Task 8a was that PSI `full` *cannot* see quiet reclaim, with a
mechanism attached: reclaiming clean pages the workload has stopped touching costs no wait, so
there is nothing to count. Task 8i's own constructed known-bad, re-read under a **fixed one-second
window**: **0.2 ms/s as a whole-block average over 600 s, and 61.3 ms/s over its worst second.**
The reclaim burst was always in the counter. **Ten minutes of averaging divided it by about three
hundred.**

**What survives the correction is narrower and still load-bearing**: the counter is
**per-cgroup**, so a firing does not establish that the measured *process* waited, and reclaim
caused from outside the cgroup leaves it nothing to attribute. **The reclaim-shortfall witness
remains the condition that reports on the subject.** The full table is in
[`oq19-gate-validation.md`](oq19-gate-validation.md).

> **AND THE CONSTRUCTION FAILED FIRST, WHICH IS THE OTHER HALF OF THE LESSON.** The first
> known-bad re-touched **anonymous** memory under a bounded pressure generator that stops at a
> 2 GB floor — so nothing the process wanted was ever taken, and the gate read **0.13 ms/s**.
> That is (i2) at the construction rather than at the test: **a null from a fixture that does not
> build the effect is a claim about the fixture.** The working set had to be **file-backed**
> before the kernel would take it and the refault would cost a wait.

**AND REFUSING TO GATE WITH A BLIND INSTRUMENT IS THE RIGHT CALL, FOR A REASON WORTH RECORDING.**
Three `machine` tests then failed on this box. The standing rule says *"if a gated test fails,
gate it; never widen it"* — but gating them with **this** gate would convert a **visible failure
into a silent skip**, which is strictly worse than red: a red suite is read, and a skip is not.
**A known-red failure with an owner beats a green suite that stopped asking the question.**

#### A DISCOVERED CARDINALITY MUST BE FOLLOWED TO ITS CONSEQUENCES, NOT JUST RECORDED

> **When a check establishes the SIZE of a set — one field, three identities, two openers —
> ask immediately what breaks at that size.** A set of one makes every distinction defined
> over it degenerate, and **the degeneracy is invisible to any test written against the
> general case**, because such a test exercises the distinction where it still holds.

**This is the length-1-axis argument from Q2 and (i7), applied to a configuration set rather
than to a store axis** — and the two should be read together. There, an axis of length 1
makes every assertion over it pass; here, a *difference* set of size 1 makes two gates that
were designed to be independent into the same gate.

Worked instance, Phase 2a Tasks 2 and 11, and the gap between them is the finding. Q3 flagged
that the hash partition *might* be two-way plus one field; Task 2's allowlist sweep
**confirmed** it — `COMPAT_RELEVANT_FIELDS = FIT_RELEVANT_FIELDS | {"criteria"}` — and
**neither pass asked what a one-field difference does to §12.8's recompute arm.** The answer,
found nine tasks later while implementing that arm: *"`fit_hash` matches and `compat_hash`
differs"* **is** "the criterion set changed", which §12.8 refuses, so the arm has **no
reachable input at all**. The cardinality was recorded correctly and its implication went
unexamined.

The tell is a check that returns a number or a size and is filed as a fact. **The follow-up
question is one line and it is never asked by the check itself**: what is defined *over* this
set, and what happens to it at this size?

#### THE SAME RULE AT THE INSTRUMENT LEVEL: A COMPLETE-LOOKING TABLE WITH A ROW MISSING

> **An observation that a thing is ABSENT is not the same as reading the thing.** When an
> instrument's coverage depends on **program state** rather than on what is installed, its
> output is a self-report: it says what has been loaded, and a check reads it as saying what
> exists. **Force the load before observing, or the absence is self-reported.**

The tell is the dependence on state. Any check that enumerates **loaded libraries, registered
plugins, entry points, or available backends** has this shape.

Worked instance, Phase 2a Task 5, measured. `threadpoolctl.threadpool_info()` before anything
parallel has run returns **OpenBLAS alone** — not an error, not an empty result, a plausible
table with the decisive library absent. numba's `libgomp` appears only after a `prange`
function has executed, and the layer-3 determinism check runs at **startup**, which is exactly
when it is not there. Worse, `threadpool_limits` does not retroactively limit a library loaded
afterwards, **so the check would certify a state it had neither observed nor could enforce.**
The fix is to launch the layer first — `numba.get_num_threads()` does it through a public call
— and only then read the table.

**And its companion: one library must be set and observed through ITS OWN interface.** Measured
in the same sitting: inside `threadpool_limits(limits=1)`, `threadpool_info()` reports
`openblas 1, openmp 1` while `numba.get_num_threads()` still reports **4**. They are different
quantities — threadpoolctl caps the OpenMP runtime's pool, numba's mask is how many slices a
`prange` is cut into, and a `prange` reduction reassociates over numba's count. So design doc
§11.3's cross-library rule (*a precondition that holds for OpenBLAS while MKL runs
multithreaded is not a precondition that holds*) now has an **intra-layer instance**: two
instruments of the same OpenMP layer disagreeing inside one process.

### (a2b) WHEN A VALUE IS INVALID UNDER A DETECTABLE CONDITION, MAKE IT UNAVAILABLE — DO NOT EMIT IT WITH A CAVEAT

> **A caveat travels less well than the number it qualifies, and the number is what gets
> copied.** If a computed value is invalid under a condition the code can detect, **do not
> produce it.** Labelling it does not stop it being quoted.

**THIRD REGISTER OF ONE FAMILY, AND THE FIX WAS THE SAME SHAPE ALL THREE TIMES: MAKE THE WRONG
READING IMPOSSIBLE RATHER THAN DOCUMENTED.**

| register | the wrong reading | the fix |
|---|---|---|
| **(a0)** a fill value a successful run can produce | an empty store reads as a complete one | a sentinel no success can emit |
| **(a2)** a name is not a gate | a setting recorded reads as a setting enforced | observe the limit instead of requesting it |
| **(a2b)** *this one* | a caveated number reads as a number | **do not emit it** |

**The worked case is Phase 2c decision D8.** §11.2's audit reports four disagreement metrics, and
a **pooled** figure over a candidate set the identifiability lint has flagged is **invalid** —
label switching inflates parameter disagreement while selection and `|Δℓ|` stay near zero, so the
pooled number describes non-identifiability wearing hysteresis' clothes. The obvious designs were
**refuse to audit** (which denies an audit to the users most at risk) and **report both with a
label** (which leaves the misquotable artifact in existence). **The audit emits no pooled figure
at all.**

**TWO THINGS THAT MAKE THE RULE SAFE TO APPLY.**

- **CHECK THAT NOTHING CONSUMES THE VALUE FIRST.** D8 was free only because **no criterion reads a
  pooled disagreement figure** — §11.2 attaches its one threshold to the iteration saving. **Where
  a consumer does exist, withholding is a breaking change and the rule does not automatically
  win.**
- **THE UNAVAILABILITY MUST BE VISIBLE.** A missing number reads as an omission unless the output
  **says it was withheld and why.** Same argument as `RSS measurement validity` printing **at
  zero**: silence and absence are the same bytes.

**AND A CONDITIONAL VERSION OF THIS RULE IS ITSELF A HAZARD.** *"Withhold only when flagged"* means
one run emits the figure and another does not, so **two runs report different quantities under one
name.** D8 withholds **always**, which is why it is a default rather than a branch.

### (a3) DEFER THE FEATURE, DECLARE THE REGIME

> **When deferring a feature, ask separately whether its REGIME must be declared.** If any
> shipped mechanism — a memory formula, a cost projection, a validation branch — behaves
> differently under it, **the regime ships now as a declared, validated, refused branch even
> though the feature does not.** A mechanism that can only be right in one regime is not
> right; it is untested in the other.

Three deferrals of this shape in Phase 2's planning: Whittle screening, the netCDF opener,
per-point regressors. The last is the worked case — one config field moves `tile_side` from
338 to 186, a **3.3× change in tile area** — so a `--explain` that cannot report the
per-point regime is a sizing tool that is only correct in the easy case. **A sizing tool
correct only in the easy regime is worse than none, because it will be trusted.**

**A deferral in this project's idiom is a field, a formula branch, and an explicit refusal
with a test** — not a comment promising a hook.

### (a4) RECOMPUTE EVERY WORKED EXAMPLE BEFORE TRUSTING THE REQUIREMENT IT ILLUSTRATES

> **An example is authored under the same misunderstanding as the text around it, so it
> CONFIRMS the requirement rather than testing it.** Recompute every worked example in a
> brief. Where the example is the **only** statement of a quantity, it is load-bearing and
> must be derived independently.

**This is (a) at the document level:** a wrong constant that agrees with the prose is
invisible to any reader who reads the two together, because there is nothing to compare
against. The tell is a number that looks plausible and does not invite checking.

Worked instance, Phase 2a Task 7. Design doc §12.3, the 2a plan and `PROGRESS.md` all state
the `/detail/` extent as `Σ_m p_m(p_m+1)/2` and all three illustrate it as **`4 + 6 = 10`**
at p = (1, 3). The per-model sum is `1 + 6 = 7`. **10 is `P_total(P_total+1)/2` — the
triangle of the flattened total, which is precisely the one-table-reused defect the same
paragraph exists to prevent**, committed in its own example. (`4 + 6` is not 10 either, and
that went unread too.) It survived three documents and two prior audits because both 4 and
10 are plausible sizes for that axis.

#### AND THE SAME RULE ON THE REVIEW SIDE: A NUMBER IN A REPORT IS AS UNVERIFIED AS ONE IN A BRIEF

> **Recompute the arithmetic in a report before accepting its conclusion.** A reviewer who
> checks a brief's worked examples and not the implementer's own figures has applied (a4) to
> one half of the work. **The reviewer's job includes the arithmetic**, and a number that
> arrives inside an otherwise-careful argument is the one least likely to be checked.

Worked instance, Phase 2b, 2026-08-14, **found by the author on a second pass and not by the
review**. A closure boundary was reported as *"5.4 s/series × 10⁷ ≈ 1712 years"*; it is
**5.4e7 s ÷ 3.156e7 s/yr = 1.71 years**, wrong by 10³, and it was accepted as a measured
boundary by both sides of the review.

**The correction changed what the boundary meant**, which is why it mattered rather than being
a typo: 1712 years is absurd and closes the question, while **1.7 years is merely infeasible**,
and infeasible invites the comparison that absurd does not — see the §9.3 speedup gap recorded
in `PROGRESS.md`, which is now a stated, unverified claim instead of an unasked question.

**The tell is a figure that supports a conclusion nobody disputes.** Nothing was riding on
whether the number was 1.7 or 1712, so neither reader had a reason to divide.

**FOURTH INSTANCE, PHASE 2b TASK 9, AND IT SURVIVED BECAUSE IT CHANGED NOTHING DOWNSTREAM.**
The Task 9 blocker put criterion 7's implied headroom at *"~33% against the shipped 15%"*.
Asymptotically the budget's slope has to reach the peak's — `926 / (1 − h) ≥ 1900.9` — so
`h ≥ 1 − 926/1900.9 =` **0.51286**, and no derivation reproduces the 33%. At §9.4's
preconditions the two give sides of **208** and **240**.

> **AND THE REASON IT PASSED REVIEW IS THE GENERALIZABLE PART: IT LEFT THE PUBLISHED SPREAD
> UNCHANGED — BY COINCIDENCE.** The spread stayed 192–272 only because a *different* reading,
> the multiplicative one, was already the extreme. **A wrong number that does not move the
> answer is not harmless; it is unfalsified.** And knowing that it did not move the answer
> required doing the recomputation anyway — so "it probably doesn't matter" is never a reason
> to skip the arithmetic, because that judgement is the arithmetic's output, not its input.

**THE REPAIR IS A CONSTRUCTION, NOT A CORRECTION.** The figure now lives as
`PerSeriesDispute.headroom_fraction_required`, **derived from the two slopes** so it cannot
drift from them, and the test checks it against a **hand-computed literal** rather than
re-deriving it — re-deriving would be an oracle sharing its subject's derivation path (j).
Derive the field, hand-compute the check.

**AND THE FIRST RECOMPUTATION THAT CONFIRMED RATHER THAN CORRECTED IS ITSELF INFORMATION.**
Phase 2b Task 5 re-fitted Task 4's published ladder from Task 4's own table and got slope
**1050.75** against the recorded 1049, SE **223.6** against 222, excess **0.558 SE** against
0.55, ratio **1.1347** against 1.133 — every difference inside the rounding of the table's own
0.01 MB peaks, since a ±5 kB perturbation moves the slope by at most 2.7 B. **Recording a clean
check matters because the register's whole point is that nobody re-derives these**: an
unbroken run of corrections would say the practice is finding defects, and a confirmation says
what the earlier work was worth. **The check is only evidence if the negative result is
published too.**

#### AND THE THIRD REGISTER: A CORRECTION IS AN UNVERIFIED CLAIM

> **A correction arrives with the authority of the error it fixes, so its own arithmetic is
> the least likely to be checked.** Where a correction states both a **derivation** and a
> **magnitude**, verify they agree before accepting either.

**This is the same rule in its third register — brief, report, correction — and the third is
the one with a defence mechanism.** A brief's number invites suspicion because the brief is
what you are auditing. A report's number is checkable because the report is under review. A
correction's number arrives having just demonstrated that the *previous* number was wrong,
which is the strongest possible credential and says nothing at all about the new one.

Worked instance, Phase 2b F3, found at Task 0 by an implementer rebuilding the inventory. The
finding **named four omissions** — `theta_unconstrained` (+32 B), `n` (+8), an object-array
`init_rung` pointer (+8), and `n_iter` as int64 rather than uint16 (+6) — and **recorded the
magnitude as +46 B/candidate**. The four sum to **+54**. Both numbers sat inside one finding,
two lines apart, through planning and review, **and nobody divided.** The derivation was right,
the magnitude was wrong, and the correction was accepted on the strength of the defect it
exposed.

The check is one subtraction and it is available for free wherever a correction is written in
this project's idiom, because the idiom already requires the derivation to be stated beside the
number. **State both, then compare them** — a correction that gives only a magnitude has
discarded the one thing that could have caught it.

> **A DIFFERENCE THAT EQUALS A NAMED TERM IS A COINCIDENCE UNTIL THE OTHER TERMS ARE COMPUTED
> TOO. Matching a residual to the most recently-touched term is pattern recognition, and a
> correction arrives with enough authority that nobody divides.**
>
> **AND THE UNDERLYING FAULT WAS NEVER THE NUMBER — SEE (h).** Phase 2b Task 7, in two steps,
> and the shape shows only across both:
>
> 1. `memory._CHILD` runs `SignalSpec([Constant, Trend, Annual, SemiAnnual])` — **six** design
>    columns — while `data_and_workspace_bytes_per_series`'s docstring **and**
>    `test_measured_peak_rss_is_at_least_the_arrays_that_provably_exist` computed its floor at
>    **four**. **An oracle at a different configuration from its instrument**, which is (h): the
>    test exercised a default rather than the thing it names, and it survived because 6382 and
>    6550 are both plausible sizes for that axis.
> 2. The discrepancy was read as **stale prose**, on the strength of a 168 B gap that equals
>    `augmented_state` at k_β = 6 — the term Task 0 had most recently added. It is actually the
>    k_β 4→6 delta spread across **three** terms (48 + 104 + 16). **So the correction changed the
>    correct number to match the wrong oracle**, and shipped in two commits.
>
> **The check that would have caught it is the other two subtractions**, and the reason they were
> not done is that the first one already agreed. **An agreeing first check is where to be most
> suspicious, not least** — it is the moment the search stops.

**AND IT APPLIES TO YOUR OWN HAND-COUNTS, WHICH IS WHERE IT KEEPS BITING.** Phase 2b Task 2:
re-deriving four modules' fixture budgets needed `p_max`, and I counted `white + matern12` as
two free parameters by reading the candidate list. It is **three** — both sigmas and the
timescale — and `build_ragged_index`'s extents are what know it. Two budgets meant to straddle a
tile-side boundary landed on the same side, a refusal stopped firing, and the **slow** suite
caught it. **Where a structure in the tree computes the quantity, read it; a hand-count is an
unverified claim in exactly the way (a4) describes.**

#### AND THE FOURTH REGISTER: A CONCLUSION THAT SURVIVES ITS OWN CONTRADICTED DERIVATION MUST BE RE-DERIVED, NOT ASSUMED

> **When a correction destroys the reasoning under a conclusion and the conclusion still
> stands, RE-DERIVE it from the corrected reasoning before carrying it.** The replacement
> derivation almost always changes what the conclusion *implies* — its magnitude, its
> likelihood, or its regime — even when the sentence itself is unchanged.

**WHAT MAKES THIS DANGEROUS IS THAT THE CORRECTION READS AS CONFIRMATION.** A conclusion whose
derivation has just been shown wrong emerges from the correction still standing, and standing
through an audit is the strongest evidence a reader has. **"Conclusion unchanged" is a summary
that hides the whole finding.** The three registers above are about numbers; this one is about
a *sentence* surviving while everything beneath it moves.

**THIRD INSTANCE IN THIS PROJECT, AND EACH TIME THE REPLACEMENT REASONING CHANGED THE
IMPLICATION:**

| the conclusion that survived | the derivation that did not | what the replacement changed |
|---|---|---|
| `_augment` is worth keeping | it helps path A | **path B gained, not path A** — a different consumer, so a different reason to keep it |
| the probe needs a bare launcher | `peak_rss` is inherited | the operative quantity is the **peak**, not the inheritance — so the fix is where the reading is taken, not how deep the child is |
| *"you calibrate and your store stops resuming"* (Phase 2b Task 6) | *"the refusal fires when the calibrated side is larger"* | **the arm is the opposite one**, and the corrected direction makes the refusal the **expected experience rather than a corner case** — a slope above the formula is what Task 4 measured, and it buys a smaller tile |
| *"these two RSS tests failed because the box was under memory pressure"* (Phase 2b, the validity gate) | *"pages were reclaimed to swap"* | **swap was 100% full and could absorb nothing more**, and the pages that actually left were **file-backed** — mapped shared libraries, which is most of what importing numba costs, and which leave RSS with no swap at all |

The third is the clearest: a reader told only that *"the conclusion survived"* would have carried
away **the opposite impression of how often this happens.** The sentence was right and everything
about how much it mattered was wrong.

**AND THE FOURTH IS THE ONE WHERE RE-DERIVING PAID IN CODE RATHER THAN IN PROSE.** *"Is there
swap"* is what the wrong mechanism suggests instrumenting, and it **could not have worked** — the
swap device was already full and static while pages were still leaving. Re-deriving the mechanism
produced a **better instrument**: pressure stall information answers *"was the kernel reclaiming
from us"* directly, per cgroup, as a cumulative counter that can be differenced across exactly the
window that produced the number. **The other three corrections improved an explanation; this one
improved what gets measured**, which is the outcome worth expecting from the re-derivation rather
than treating it as bookkeeping.

#### AND THE FIFTH: RIGHT IN KIND, WRONG IN SCALE — AND SCALE IS WHAT DECIDES WRITABILITY

> **A qualitative finding that an effect EXISTS does not establish that it MATTERS. Measure its
> magnitude against the assertion's own margin before withdrawing the assertion.** A premise
> shown false does not automatically retire everything built on it: what retires the assertion
> is the effect being large relative to the margin the assertion was written with.

**Phase 2b Task 8a established that a high-water mark can be reduced by reclaim**, which
withdrew the stated premise under four ungated tests — *"a watermark cannot be reduced by
reclaim"* — and read as though the survey's conclusions had to go with it. **Task 8i measured
the magnitude.** The same reclaim event that took **135 MB** off the working set moved `VmHWM`
by about **1 MB**:

under the same constructed known-bad tabulated above — **about a hundred and thirty times less
damage to the watermark than to the working set.**

**So peak-based criteria survive with a stated margin, and current-RSS differences across a long
window do not.** The four ungated tests carry margins of 200 MB and 400 MiB against a ~1 MB
drift, so they stay ungated — **for a different reason than the one originally written down**:
not *"reclaim cannot"* but *"reclaim can, bounded at about a megabyte, and the margin is four
hundred times that."* One test whose window is **1 MB** is at risk on exactly this arithmetic,
and it is named in the survey rather than left to be discovered.

> **THE FIRST INSTANCE IN THIS FAMILY WHERE THE CORRECTION RESTORED CAPABILITY RATHER THAN
> REMOVING IT.** The other four narrowed what could be claimed. This one showed that most of
> what had just been called into question was still assertable — and only a measurement could
> establish that, because *"the premise is false"* and *"the assertion is unsafe"* are different
> statements and the gap between them is a number.

#### A POINT BETWEEN TWO MEASURED POINTS IS NOT MEASURED

> **Interpolation between measurements is inference, and a threshold can sit between any two
> samples.** Where a brief names a specific point, **measure that point** — neighbours that
> agree say nothing about what is between them.

**This is (a4) applied to a sample rather than to a worked example**, and it is the harder half
to notice: a worked example invites recomputation because it is arithmetic, while a sample sits
inside a table of *measurements* and inherits their authority without having been taken.

Worked instance, Phase 2b Task 4. The step test runs at caps **{1, 2, 3}**, and the table
supporting it was measured at **1, 2, 32 and 200** — cap 3 was never taken, and was assumed to
behave like its neighbours. It does not: **0 of 128 fits come back `OK` at caps 1 and 2 and 15
do at cap 3**, because an `OK` needs `n_iter < max_iter` and a fit converging in two iterations
reaches it. The threshold sits exactly on the unmeasured point.

**AND THE OUTCOME WAS BETTER THAN THE DESIGN ASSUMED, WHICH IS WHY IT IS RECORDED AS EVIDENCE
RATHER THAN AS A PASSED TEST.** Peak residency was **flat across {1, 2, 3} — 227.7, 227.8,
227.7 MB — while fifteen fits reached the four allocation sites a non-`OK` outcome skips.** The
plan asserted those sites were shape `(1, …)` constants by reading the code; that is now a
**measurement**. The design had arranged the fixture to avoid the confound, and the confound
turned out to be the experiment.

**Its stated limit is what keeps it honest**: at B = 64 a *per-series* first-iteration
allocation is kilobytes and invisible here, so what the band catches is a **constant**-scale
allocation. The per-series case would show only at the ladder's top point.

### (a5) CROSS-CHECK A BRIEF'S REQUIREMENTS AGAINST ITS OWN CONSTRAINTS

> **A requirement and the constraint that forbids it can sit paragraphs apart and both read
> as correct.** The implementer satisfies the requirement, and the constraint is what the
> code violates. **Where a brief states both a fixture and a watch, apply the watch to the
> fixture first.**

**This is the document-level twin of (a4)**, and it is the second time in three tasks that a
defect was inside the brief's own *text* rather than in its model of the code. (a4) says
recompute the examples; this says **check the requirements against each other**.

Worked instance, Phase 2a Task 9. The brief required a fixture point *"where candidate 1
fails and candidate 2 succeeds -- the offset-inside-a-gap construction, a breakpoint with no
support for one candidate's design"*, and two paragraphs later warned, correctly, that
**`fit.py` computes `design_info(t, mask)` once, before the candidate loop, so a test
asserting design-failure behaviour must vary the mask, never the candidate.** The two cannot
both hold: in v1 the signal spec is fixed, so a design failure is identical for every `m` and
the prescribed construction gives **`n_valid = 0`**, which is a different test point
entirely.

**The reachable construction is an OPTIMIZER-stage failure and it must be, until joint
signal x noise search lands** -- design-stage outcomes are constant across the model axis by
construction. Fitting `white + matern12` to white noise leaves the correlated candidate
degenerate at most points while `white` fits (measured: 3 of 4).

#### (a5) EXTENDS ACROSS DOCUMENTS, AND THE CONFLICTING CONSTRAINT CAN BE ONE NOBODY HAS OPEN

> **A requirement can contradict a constraint that lives in a document nobody has open.** A
> brief is reviewed against itself and against the design doc; **an earlier sub-phase's exit
> criteria are neither, and they are still binding.** Before adding a per-run measurement to
> provenance, check it against every property already asserted **of a store** — byte identity,
> determinism, self-containment.
>
> **THE TELL IS SPECIFIC AND REUSABLE: any new value that is MEASURED rather than DERIVED and
> reaches a store is a candidate.** Determinism claims are the natural enemy of fresh
> measurement, and this project has three of them.
>
> **A MEASUREMENT OF THE PROCESS CANNOT BE PART OF A BYTE-IDENTITY CLAIM ABOUT THE OUTPUT.**
> They are claims about different subjects, and a store recording both is a store whose
> reproducibility test now fails for a correct reason. **Where both are wanted, name the measured
> keys and exclude them explicitly** — never drop the comparison wholesale, and never quietly
> remove the measurement.

The first half of (a5) is about two requirements inside one brief. This is about a new
requirement and an **already-satisfied exit criterion from an earlier sub-phase**, which is worse
in one specific way: nobody is reading the old criterion while writing the new brief, so the
conflict has no reviewer at all.

Worked instance, Phase 2b Task 1. The floor is *"measured fresh every run and never cached"* and
*"both floors are recorded in provenance"*; Phase 2a's exit criterion 1 is *"a killed and resumed
run is byte-identical to a clean one"*. Two runs of one configuration measure two different
floors, so the root document differs — **while every array, every chunk and every other attr is
identical.** Both requirements are right. Stated together, they are unsatisfiable.

**And it was invisible to the task's own tests**, because the suite stubs the probe while
criterion 1 drives the CLI in a subprocess where the stub does not reach. The full sweep caught
it — the third time it has caught what a task's own tests could not.

> **AN ORDERING CONSTRAINT THAT IS CURRENTLY UNENFORCEABLE IS STILL BINDING, AND THE TASK THAT
> MAKES IT ENFORCEABLE INHERITS THE OBLIGATION TO TEST IT.** A documented order over steps that
> cannot fail is satisfied by every arrangement, so nothing holds it — and the day one step
> becomes fallible, the order becomes load-bearing **without anyone editing it**.
>
> Worked instance, Phase 2b Task 2. §13.7 orders the entry contract *identity first, geometry
> second*, and the geometry step derived a tile side that in practice never refused — so the
> derivation sat above the gates harmlessly for a whole sub-phase. Task 2 made it refuse a budget
> below the process floor, and a run with a wrong candidate list **and** a small budget then
> reported the budget: the two send a user to different places. **The task that introduced the
> refusal is the one that owed the reordering and the test**, and neither was in its brief.



The repair keeps the criterion's force: files compared byte for byte, attrs compared key by key
against a **named** exclusion set, and **the excluded key asserted present in both stores**, so
"excluded" cannot decay into "absent".

> **AND A REASSURING SENTENCE IN A BRIEF IS A REQUIREMENT LIKE ANY OTHER: CHECK IT AGAINST THE
> GATES IT PROMISES TO SURVIVE.** The tell is a claim of the form *"X can never break Y"* —
> universally quantified, comforting, and written by whoever also wrote Y's exceptions.
>
> Worked instance, Phase 2b Task 5. The brief required the docstring sentence *"deleting the
> cache can never break a store, only cost a re-measurement"*. It is true of a **store** and
> false of a **resume**: `completion.resume_tile_side` refuses on its *stored > derived* arm,
> reachable exactly when the calibrated slope came in **below** the formula and the stored side
> is therefore the larger one. **The proof the claim was too broad is that the next task in the
> same plan exists to name that refusal.** The docstring now carries the narrow claim — never
> unreadable, incomplete or unopenable, and it costs a re-measurement — and the test of it is
> deliberately placed in the arm where the resume proceeds, with the other arm named as the
> next task's subject.

#### AN ENUMERATION OVER STATES BEATS A CONDITION INFERRED FROM TWO

> **Where a brief states a CONDITION, enumerate the state space it partitions and check the
> condition against every cell — including the cells the brief did not name.** A condition is
> written from the cases its author had in mind, so it is correct on those and unexamined
> everywhere else, and the unexamined cells are where it is wrong.

**This is (a5) at a predicate rather than at a requirement.** The first half of (a5) is about
two requirements that contradict; this is about **one** requirement that is silently partial,
which has no contradiction to notice. The tell is a condition phrased as a *difference* or a
*change* — those are inferred from two imagined states and there are usually more.

Worked instance, Phase 2b Task 6. The brief said to name calibration as a cause *"when the
store's `tile_side_basis` differs from the current run's"*. Enumerated, the space is four cells,
and calibration is a cause in **three** — one of which has the bases **equal**: two measurements
of one store both read `measured` while the sides differ, which is exactly what `--recalibrate`
produces. Since the cache has no expiry, `--recalibrate` is the **only** sanctioned route to that
state, so the inferred condition fell silent precisely where the user has most reason to suspect
the calibration.

**AND THE CELL THAT MUST STAY SILENT IS HALF THE FINDING.** Both bases `default` means calibration
is not a possible cause, and naming it there sends the user to a cache never involved — Task 3's
always-firing warning in a diagnosis rather than in a warning, and a condition that fires
everywhere carries no information. **A diagnosis that changed for every user in order to serve one
of them would be its own defect.**

#### THE SAME RULE WITHOUT A CONFLICT: TWO BEHAVIOURS OVER ONE CRITICAL SECTION

> **When a brief states two behaviours governing the same critical section, derive the
> implementation constraint their CONJUNCTION imposes and state it explicitly.** Neither
> behaviour alone implies it, so an implementer satisfying them one at a time will not find
> it — and the code that satisfies both by accident is indistinguishable, until the accident
> is tidied away.

The first half of (a5) is about requirements that **contradict**; this is about requirements
that are jointly satisfiable **only under a constraint neither one states.** The tell is the
same: two paragraphs, both correct, talking about one window.

Worked instance, Phase 2a Task 10. *"An interruption injected between the two writes leaves
the bit unset"* and *"SIGTERM flushes rather than dying mid-region-write"* both govern the
interval between a tile's data write and its completion bit, and they want opposite things
there. The constraint their conjunction imposes: **the SIGTERM handler must not raise.** It
records, returns, and the flag is read *after* the bit is written — so the signal is never
observed inside the window at all. A raising handler (the `KeyboardInterrupt` idiom, and the
first thing a reader reaches for) satisfies "stop promptly" and lands its exception in
precisely the window the other requirement protects, at a point no test can choose.

### (a6) WHEN CODE IS DELETED OR REPLACED, SWEEP FOR THE DESCRIPTIONS THAT SURVIVE IT

> **A description whose subject no longer exists reads as specification and is
> unfalsifiable, because nothing exercises the thing it describes.** After deleting or
> replacing an implementation, sweep for what described it — formulas, enums, cache keys,
> docstrings, config fields, benchmark harnesses — and delete or re-point each one.

**This is (a2) along the time axis.** (a2) asks whether a name was ever backed by the thing
it claims; this asks whether it **stopped** being backed. The tell is identical — a name that
reads as a gate and is not — and so is the failure: nothing under test, so nothing fails.

Worked instance, Phase 2b F2 and F4, and it is the **third** time a name has outlived its
referent here (`metamer_version` populated by nobody; `candidates` covered by no hash while
§12.8 assumed enforcement; and now this).

`memory.Backend` named two architectures and production had neither. Path A's
`B × (… + c_A)` described the **batched trust-region of §8.3**, which the stage-1 spike
deleted — *Task 19 was deleted, not deferred*, under the ≥3× rule, correctly and with the
decision recorded. Path B's `T × c_B` described a `prange`-over-series driver that exists
only in `bench/spike.py`. **The deletion was right, was recorded, and the formula describing
the deleted architecture went with neither.** Corrected, the two placements differ in a
**constant**, not in the slope — so §9.4's *"the formulas have different shapes, not just
different constants"* was true of two designs and false of the code.

**The repair is to delete rather than to alias.** Keeping `Backend` as a synonym for the
replacement would re-commit the defect: a name with no referent, now with a forwarding
address.

**AND THE SWEEP IS THE HALF THAT PAYS, BECAUSE THE PLAN'S OWN SWEEP WAS SHORT BY HALF.** The
2b plan named two importers of `Backend`; there were **four** in `src/` — the two named, plus
`batch/validation.py` and **`bench/spike.py`**, the latter on the far side of a layering
boundary the project has an open question about. Four **more** descriptions of the same deleted
subject were in the module and named by nobody: `bytes_per_series` (the "model" *was* the
deleted architecture's shape), `tile_bytes`, `thread_state_bytes`, and
`streaming_overhead_bytes`, whose 40 B/series charged a `(B, 1+k_β)` row per series when the
driver hands the engine B = 1.

**Worst of them was inside the function the finding was already about.** `_solver_state` — the
subject of F2 — also charged a *"dense quasi-Newton trust-region model"* optimizer term for the
same deleted §8.3 design, while production runs scipy L-BFGS-B for **both** engines, whose
workspace is dominated by `11·maxcor²` doubles that do not depend on the parameter count at all.
The constant was understated **11.3×** — and it is (a7) as well as (a6).

> **SO THE SWEEP IS TWO MECHANICAL STEPS, NOT A READING.** A reading finds what the reader
> already suspects, which is how a sweep comes out at half the true count.
>
> 1. **`rg` for every importer of the deleted name**, and count them. The 2b plan's Watch named
>    two; there were four in `src/` and three more test modules.
> 2. **Enumerate every function in the DEFINING module** and ask of each whether its subject
>    still exists. Four more descriptions of the deleted architecture were in `memory.py` —
>    `bytes_per_series`, `tile_bytes`, `thread_state_bytes`, `streaming_overhead_bytes` — and
>    the worst was inside the very function the finding was about.
>
> **The descriptions cluster where the subject was defined**, which is exactly the region a
> reader's eye has already accepted as understood.

**AND THE CHEAPEST INSTANCE IS THE ONE CAUGHT BEFORE IT EXISTS.** Phase 2b Task 6 needed *"this
run's basis, or the source's if this is a recompute"* at a **second** site; the first was an
inline conditional in a call's argument list. The obvious implementation writes it twice, and two
copies of one derivation drift — silently, because a wrong tile side still runs. Resolved once
above both consumers instead. **A second description is easiest to prevent in the commit that
would have created it**, and it costs one variable there against a sweep later.

### (a7) A CONSTANT CHARGED AS IF IT SCALED IS A SHAPE ERROR, NOT A CONSTANT ERROR

> **Before correcting a term's MAGNITUDE, verify its VARIABLES.** A term with the wrong
> dependence produces a plausible number at the fixture's parameter values and diverges
> everywhere else — **and fitting a coefficient to the fixture makes it worse**, because the
> fit is now anchored at the one point where the wrong shape was right.

**(a) is about a term that cancels; this is about a term that varies with the wrong thing.**
The failure modes differ: a cancelling term is invisible to every differential check, while a
mis-shaped term is visible to *any* check run at a second parameter value and to none run at
one. The tell is a term whose docstring names a quantity its formula does not contain, or
contains one the code never varies.

Worked instance, Phase 2b Task 0. `memory._solver_state` charged an L-BFGS history as
**`22 * p * 8`** — 704 B at p = 4. scipy's `_minimize_lbfgsb` allocates
`wa = 2*m*n + 5*n + 11*m*m + 8*m` float64, and **`11*m*m` dominates: 1100 doubles that depend
only on `maxcor` and not on the parameter count at all.** The term was wrong in its
*dependence*: it charged per parameter for something that does not vary with parameters, and
the whole constant came out **11.3× low**.

**And it would have survived the obvious repair.** Every fixture in this project sits at
p = 4, and every candidate the shipped registry can build has p between 1 and 4, so a
coefficient tuned to make 704 into 11 144 at p = 4 would have read as a successful correction
and been wrong at every other `p` — and *right* for the wrong reason at the only `p` anyone
measures. **The question is never "is this number too small"; it is "what is this number a
function of".**

#### A RATIO THAT IS NOT CONSTANT ACROSS FIXTURES REFUTES EVERY MULTIPLIER, AND MEASURING IT IS CHEAPER THAN NAMING THE TERM

> **Measure the model's error at a SECOND and THIRD fixture before correcting it. If the ratio of
> measured to predicted moves, no coefficient exists** — one that fits any fixture is wrong at the
> others — **and that is established without knowing what the missing term is.**

**This is (a7) turned into a test you can run.** (a7) says verify a term's variables before its
magnitude, which requires understanding the term. This gets the same verdict from outside: a
multiplicative correction predicts a **constant** ratio, so three fixtures falsify it whether or
not anyone can say what the omission is. **It is the cheapest possible check on the shape of a
correction and it comes before any inventory.**

Worked instance, Phase 2b Task 8b. Peak against `resident_bytes_per_series`, three fixtures on one
harness, fifteen points each:

| fixture | analytic | measured peak | ratio |
|---|---|---|---|
| N = 60, M = 6 | 1698 | 3205.2 ± 51.3 | **1.888** |
| N = 60, M = 2 | 926 | 2410.0 ± 46.0 | **2.603** |
| N = 240, M = 2 | 2546 | 9801.3 ± 40.9 | **3.850** |

**Two-fold spread, and each ratio is pinned to under 2% by its own standard error.** So no
multiplier and no single added constant reproduces all three, and the correction that would have
made exit criterion 7 pass at the fixture it was measured at would have been wrong at both others.

**THIRD INSTANCE OF SHAPE-BEFORE-MAGNITUDE, AND THE FIRST WHERE THE CORRECT ACTION WAS TO CHANGE
NOTHING.** F5's `22p·8` was wrong in its dependence; F3's slot inventory was wrong in its terms;
this one is wrong in a way **no available correction fixes**. Recorded because refusing was the
harder call: **a coefficient was available, it was one edit, and it would have turned a failing
acceptance criterion into a passing one.** Nothing external would have caught it — the criterion
would have read *met*, at the only fixture anybody had measured.

> **AND THE SPREAD IS EVIDENCE THAT HAS TO BE KEPT ALIVE, NOT JUST REPORTED.**
> `PUBLISHED_TILE_SIDE`'s record carries the three ratios as a field with a test asserting they
> stay more than 2× apart — so if a later measurement ever brings them together, **the multiplier
> hypothesis is back and the suite is what says so.** A refutation that lives only in a report is
> a refutation nobody re-checks.

#### AND THE REASON A TERM CAN REFUSE EVERY SHAPE: A MAXIMUM IS AN ARGMAX AS WELL AS A VALUE

> **When a fitted term refuses to take a shape across fixtures, check whether the quantity being
> fitted is the same physical event at each point.** A maximum over a run carries a *location* as
> well as a magnitude, and **an unstable argmax means the samples are drawn from different
> populations.** Instrument the location before fitting the magnitude.

**THIS IS THE FINDING UNDER THE FINDING ABOVE, AND IT IS WHY NO COEFFICIENT COULD HAVE WORKED.**
The section above says a moving ratio refutes every multiplier. This says what to do next, and it
is not "find a better functional form": **there was no single quantity to fit.** A regression over
a maximum silently assumes the maximum is produced by the same allocation at every point, and
nothing in the fit can report that it is not — the residuals look like noise or like curvature.

Worked instance, Phase 2b Task 8b. The transient — peak above end-of-tile residency — went
**905.9 B/series** at N = 60, M = 2, **−39.9** at N = 60, M = 6 and **6985.8** at N = 240, M = 2.
No constant, no `n_time` multiple, no candidate multiple fits three points. **The sampler's
timestamp says why in one column**, and there are indeed **two allocations wearing one name** —
~~at M = 2 tile assembly and at M = 6 the store write~~, **struck 2026-08-19: both labels were
wrong**, and which two they are is the corollary below.

#### AND ITS COROLLARY, MEASURED THE HARD WAY: A TIMESTAMP IS NOT A LOCATION

> **An argmax in seconds is not a location until something records where the phase boundaries
> are.** Reading a phase off a timestamp is an inference made by whoever knows what the code does,
> and it is made at precisely the moment the code is not doing what they think. **Timestamp the
> boundaries and take a maximum per phase.**

**Phase 2b OQ18 Task A, and BOTH of the labels above were wrong.** With the boundaries actually
recorded — assemble, fit, write, callback, pad, completion bit, tail — the M = 2 argmax is inside
**`fit`** (every point at side ≥ 48) and the M = 6 argmax is inside the **pad**, a window in which
the workload is asleep. The 1.6–2.3 s had been read as assembly because assembly comes first;
assembly at those sides takes **about two milliseconds**.

> **AND THE SECOND HALF OF THIS RULE COST A SECOND CORRECTION, THIS TIME OF THE TASK'S OWN
> REPORT.** *"The argmax is in the pad"* was then read as *"the store write is not the dominant
> allocation"*, which does not follow and is false: the trace **rises during `write` by
> 0.97–4.15 MB** at M = 6 and the pad adds **0.007–0.139 MB** on top. The write builds the
> plateau; the pad is where a flat trace's last noise tick lands. **A maximum has a location only
> where the trace has a slope** — so the fix is not "trust the phase label instead of the
> timestamp", it is **read the phase MAXIMA, not the argmax**, whenever the quantity plateaus.
> Task 8b's *"45.02 s at every side"* and Task A's scatter from 3.99 s to 45.02 s are the same
> reading of the same flat plateau, and neither is evidence about an allocation.

**The cost of the wrong labels was a task's framing, twice.** OQ18's first hypothesis — free the
block before the store write — was derived from *"the peak is at the store write"*, which is true
at M = 6 and false at production B, where the peak is `fit`'s and the block is alive by necessity.
**The hypothesis was refutable, worth running, and held where its premise held**; what the labels
cost was knowing in advance which regime it applied to.

> **AND THE SYMPTOM WAS ALREADY VISIBLE AS AN IMPOSSIBLE STATISTIC.** The same measurement, split
> by chunking, returned curvature of **+0.054 ± 0.010 (5.3σ)** and **−0.037 ± 0.013 (2.8σ)** —
> **opposite signs, both "significant", on two arms of one experiment.** That is not a result
> about curvature; it is a fit reporting the transition between two regimes as a shape parameter,
> which is (k)'s *"a linear fit to a saturating process reports the transient as a rate"* one
> register out. **Two arms disagreeing about a coefficient's sign at high significance is a
> diagnostic, not a puzzle: it says the model is wrong, not that the data are noisy.**

**AND IT IS WHY AN L-SHAPED DESIGN COULD NOT HAVE WORKED.** Task 8b varied `n_time` at fixed
`n_models` and `n_models` at fixed `n_time` — three fixtures on two arms of an **L**, which
determines a two-parameter additive shape and **aliases every interaction into the corner point**.
Here the interaction *is* which allocation dominates, so the design could not see the one thing
that explains the data. **A crossed 2 × 2 costs one more fixture and is the minimum whenever the
quantity might change regime**, which is exactly when a term refuses a shape.

### (a8) TWO INDEPENDENT LINES CONVERGING ON ONE PATHOLOGICAL CASE IS EVIDENCE, NOT COINCIDENCE

> **When a guard's own documentation names a failure mode and an unrelated correction lands
> squarely on it, that convergence IS the guard's justification.** Record it as such. A later
> reader proposing to remove the guard then has to answer a measured number rather than a
> preference, and the guard stops looking like a tuning parameter.

Worked instance, Phase 2b Tasks 0 and 2, from two directions that never met:

- `store._chunk_side` picks a **divisor** of the tile side, and its docstring had said since 2a
  that **a prime side has no useful subdivision** — written as a caution, with no instance.
- Task 0's formula correction moved the published side from 338 to **347, which is prime.** So
  is 349, and so is 353.

Measured at the convergence: the worst array's chunk goes from 18.3 MB at 338 to **38.5 MB at
347 — 9.63× a 4 MB target.** **`TILE_SIDE_BASE` is therefore not a tuning parameter; it is what
makes the corrected arithmetic usable at all**, and dropping it costs a tenfold chunk on every
tile. The caution and the correction are independent, which is exactly why their meeting is
evidence.

### (a9) A DISAGREEMENT BETWEEN TWO INSTRUMENTS CAN BE ONE MECHANISM ACTING ON BOTH

> **Before treating two measurements as rival estimates, ask whether a shared confound explains
> the gap.** Two instruments biased by the same mechanism to different degrees look exactly like
> two instruments disagreeing — and the repair is **not to choose between them** but to control
> the confound and re-measure both.

**THIS IS TOP-LEVEL BECAUSE IT INVERTS THE NATURAL FRAMING.** A gap between two numbers presents
itself as a question about *which one is right*, and that question absorbs a task: it recruits a
better instrument, a tie-breaker, a third measurement. **The question that dissolves it is whether
the two are the same measurement made twice under different amounts of one bias.** The tell is
that the two disagree along an axis they also *differ* along — and any variable that both
instruments' designs let vary with the abscissa is that axis.

Worked instance, Phase 2b Task 8b, and the tell was available a day in advance. Task 7's ladder
gave **1021.6 ± 134.7 B/series**, Task 8's gave **1900.9 ± 84.1**, and the project spent three
tasks (8a, 8i, 8b) on the 1.86×. **Both ladders had run length monotonic with B** — Task 8's from
45.6 s to 1780.1 s, Task 7's further — and Task 8a had already established that a long run under
memory pressure loses working set and **predicted the direction**. Neither figure was wrong about
its own points; both fits were dragged down by their longest ones.

**THE ARITHMETIC THAT SETTLES IT USES NEITHER A NEW INSTRUMENT NOR A NEW RUN.** Refit Task 8's own
published table over the three points that ran under 440 s: **2584.3 ± 127.0**. A
duration-controlled ladder at the same fixture and the same three sides: **2574.9 ± 236.1**. The
same number, 0.4% apart. **The ladders never disagreed; the confound did.**

> **AND THE COROLLARY IS WHAT MAKES IT CHEAP: A CONFOUND THAT VARIES ACROSS A LADDER'S POINTS CAN
> BE CONTROLLED BY DISCARDING POINTS, NOT ONLY BY RE-RUNNING.** If the confounded variable is
> recorded per point — and a wall-clock column usually is — then the subset where it cannot have
> acted is a clean measurement already in hand. **(j4) says to check whether a published table
> answers the question. This says to check whether a SUBSET of it does**, which is the register
> (j4) did not have and the one that resolved this dispute.

### (b) Batch vs series

Is any per-series fact computed at batch level, or any per-candidate fact stored per point?
`moment_init`'s rung is per series; a batch-wide rung is right only when the whole batch
falls the same way.

### (c) Exit paths

Enumerate every `return` and every `raise`; does each pass through the outcome ladder?
**Enumerate, never assert a count** — an asserted count is how two bypassed exits survived
Task 8, and how a report claimed "exactly one early return" where there were four.

**AND THE ENUMERATION EARNS ITS KEEP IN THE DESIGN, NOT ONLY IN THE AUDIT.** Phase 2b Task 6 had
to decide what a *reporting* function does with a corrupt field — an unrecognized
`tile_side_basis` from a foreign writer. Parsing it into the enum adds a **fourth raise** to a
function whose job is to explain a refusal; reading it as a string lets the bad value appear
**verbatim in the message**, which shows the corruption to the one person who can act on it. The
exit count is what makes that a visible trade rather than a reflex, and the function kept **one
return and three raises**.

### (c2) DOES DISPATCHING ON EXCEPTION TYPE ACTUALLY DISCRIMINATE?

> **When you dispatch on exception type across a boundary you defined, verify the types are
> actually disjoint.** A third-party exception subclassing a builtin you also catch is the
> common case, and it fails toward the **earlier clause** — which is the more confident and
> more wrong answer.

(c) enumerates the exits. This asks whether the *handler* can tell them apart, and it is a
different question: every exit can be enumerated correctly while two of them land in one
clause.

Worked instance (Phase 2a Task 4). Validation staging exists to name **which layer** refused.
`pydantic.ValidationError` subclasses `ValueError`, and so did the config module's stamped-key
refusal, so a layer-1 `except ValueError` clause written above the schema clause reported
**"layer 1 (file)" for a file that parsed perfectly**. Measured on the test's first run. The
defect attacked the feature's only purpose, and nothing in either module's source hints at it —
the subclass relationship lives in a dependency.

Two responses, and they are not equivalent. Ordering the clauses correctly is necessary and is
**incidental disjointness**: it holds until someone reorders them. Introducing a distinct type
— `config.model.StampedKeyError` — makes the disjointness **structural**. Prefer the second
wherever you own one side of the boundary.

### (c3) BEFORE REUSING A VALIDATOR, ENUMERATE WHAT IT REFUSES AND CHECK EACH REFUSAL AGAINST THE NEW CALLER'S PURPOSE

> **A gate is defined by what it REJECTS, and a rejection that is correct for one caller can
> be the defining feature of another.** Enumerate a validator's refusals before reusing it,
> and check each one against what the new caller is *for* — the incompatibility lives in the
> intent, not in the implementation, so nothing about the code will look wrong.
>
> **And shared refusals must take their resolution phrasing from the caller.** "Write a new
> store" is right for a resume and absurd for the command whose whole job is writing one; a
> resolution that names the operation the user is already performing is worse than none.

(c) enumerates a function's exits. (c2) asks whether a handler can tell two exits apart.
This asks whether a refusal *should fire at all* for a caller that was not there when it was
written — and it is the one the other two cannot reach, because the code is correct in both
places and only the purposes differ.

Worked instance, Phase 2a Task 12. `resume.check_resume` is a correct resume gate, and one
of its six refusals is **a criterion-set change** — which is the entire reason to run
`--reuse-fits-from`. Reusing it for the source store looked obviously right: same fields,
same store type, same comparisons. It would have made the feature refuse its own primary use.
The source check now shares three of the comparisons and omits three, each omission recorded
with its reason.

**A DELIBERATE ABSENCE NEEDS A TEST THAT FAILS WHEN SOMEONE ADDS THE MISSING CHECK.**
Otherwise the next reader restores it as an oversight — the gap looks exactly like a
forgotten line. The mutation that pins it is "the source check also compares criteria", and
it bites. **Same discipline as cross-commenting a doubled guard, applied to a gap rather than
to a duplicate**: the redundancy and the omission are both decisions, and both are invisible
unless something fails when they are undone.

### (c4) A VALIDATOR MUST BE SPECIFIED IN THE COORDINATES AND THE EXTENT THE VALIDATED OBJECT ACTUALLY HAS

> **A check written in the READER'S natural units agrees with the correct one across the whole
> healthy region, so no ordinary fixture separates them.** State a gate in the coordinate system,
> the units and the extent of the thing being validated — not the ones the brief describes it in.

**(c3) asks whether an existing validator's refusals suit a new caller. This asks whether a NEW
validator is even looking at the right numbers**, and it is the harder of the two to see, because
the wrong version is not wrong anywhere you would think to test.

**Phase 2c plan Task 0, 2026-08-24: FOUR gates, all four specified in the reader's units rather
than the operative ones, and every one of them passes on healthy data.** The brief said each in a
sentence that reads correctly in English:

| the brief's phrasing | the operative reading | why the wrong one is invisible |
|---|---|---|
| *"outside its `ParamSpec`'s diagnostic limits"* | **plus a separate finiteness check, first** | `at_diagnostic_limit` returns **False for NaN** — `nan <= lo` and `nan >= hi` are both False — so a limits-only gate passes the all-NaN row, which is the one fault the gate exists for |
| *"outside its diagnostic limits"* | **map through the parameter's bijector first** — limits are natural-unit, `x0` is unconstrained | the two readings agree over the entire healthy region, because `exp(0) = 1` is inside every limit |
| *"a non-finite value inside a cell marked valid"* | **over `:p` per candidate**, not the full `p_max` width | the padding beyond `p` is a legitimate NaN, and a fixture whose candidates all have `p = p_max` cannot tell |
| *"a companion `x0_valid` of shape `(B, M)`"* | **and of boolean dtype**, refused rather than cast | an int64 array of the right shape casts silently, and every value in it is "valid-looking" |

**THE THIRD IS THE ONE THAT FAILS IN THE FLATTERING DIRECTION, WHICH IS (i5) ARRIVING INSIDE A
VALIDATOR.** A full-width validator refuses **every well-formed warm start except the widest
candidate's**, so the suite goes red on the healthy path — and **the repair that makes it green is
relaxing the check**, not narrowing the window. The tempting fix and the damaging one are again
the same edit.

**THE FOURTH IS THE ONE WORTH COPYING, BECAUSE IT IS FORWARD-LOOKING RATHER THAN DIAGNOSTIC.**
The defect it guards does not exist yet: Phase 2c's `SourceMap` exposes `index` (int64, **-1 where
the spiral was exhausted**) adjacent to `valid` (bool), and a later task passes them together.
**`bool(-1)` is True and `bool(0)` is False**, so swapping the two arguments marks **every
exhausted cell valid** and **every cell sourced from index 0 invalid** — correct shapes, finite
values, no exception, and the damage lands precisely on the cells the mechanism could not serve.
**Requiring the dtype now costs one comparison and closes a defect two tasks away.** Generalized:
**when two arrays of the same shape and different meaning will be passed adjacently, make the
type system or a gate distinguish them before the caller exists.**

### (d) Grep for the vocabulary the task requires

"mask", "n_used", "realized" appearing **zero** times in a 234-line brief was detectable in
one command. Task 15's brief never mentioned `fixed`, `state_dim` or `white + white`.

### (e) Do the tests bite?

Delete the guard each one protects and confirm it fails. Two of Task 9's tests replaced
assertions that could not fail at all.

**A surviving mutation has six causes and they call for different responses.** Diagnose
which before acting; five of the six are not defects, and treating them as coverage gaps
leads to deleting a real guard.

| cause | tell | response |
|---|---|---|
| **No test protects the guard** | removing the guard changes nothing observable anywhere | act on it — write the test |
| **The mutated line is unreachable** because a guard *above* it fires first | removing that upper guard makes the mutation bite | defence in depth working; write the compound mutation |
| **TWO INDEPENDENT GUARDS, EITHER SUFFICIENT** | mutating **either alone** does not bite; mutating **both at once** does | the code is doubly protected and the test is fine |
| **GUARDED ONE LAYER UP** | the mutation is semantically real and the test is sound, but an **earlier layer already normalized the input**, so the mutated code cannot see the difference | **rewrite the assertion** — see below |
| **THE MUTATION IS NOT A DEFECT** | the mutated code is **semantically identical** to the original on every reachable input | **correct the mutation, not the test** — see below |
| **NEUTRALIZED FROM BELOW** | the mutated value really is different, and **a consumer downstream never reads the part that changed** | **correct the mutation, not the test** — see below |

**THE FIFTH SAYS NOTHING ABOUT THE TEST AT ALL, AND THAT IS WHY IT IS LISTED.** A survivor is
evidence about a test only once the mutation is known to be a real behaviour change, and that
is a step people skip because writing the mutation feels like the check. **Verify the mutated
code is semantically different before concluding anything.**

Worked instance (Phase 2a Task 4): `if observed is None: return` mutated to
`if observed is None: observed = {}` left every test green — correctly, because an empty table
has no offenders, so the two are the same function. The reachable defect is deleting the guard
outright, so `observed.items()` runs against `None`; that mutation bites. A test written to
catch the first version would have been a test of an equivalence.

**THE FOURTH IS THE ONLY ONE OF THE FIVE WHERE THE CORRECT RESPONSE IS TO CHANGE THE TEST.**
The other four end in "leave it", "write a compound mutation" or "correct the mutation". This one
means the test was pointed at a defect that is **not reachable**, so the question is not whether
to accept the survivor — it is **what the mutation should have been**.

Worked instance (Phase 2a Task 3): mutating `geometry_hash`'s time component from decimal
years to `str()` of the decoded values left every test green, *including the two-calendar test
written to catch exactly that*. Decoding happens in the **opener**, so any representation taken
downstream is post-decode and already distinguishes calendars; the hazard the test named is
guarded a layer up by `calendar_of`. **The reachable defect was different**: decimal years must
be the component because they move when the **conversion rule** moves — the conversion is under
`ALGORITHM_VERSION`, so a change to it must invalidate stored fits — and because `str()` of a
datetime is a **repr**, i.e. a library-version artefact, which is (k). The assertion that bites
pins the representation, not the difference.

**The third is now a named outcome with two instances.** Task 16's `_subset` — an explicit
`if missing: raise` above a comprehension — and Phase 2a Task 0's wholly-masked batch, where
`optimize.optimize_series`'s merged-precheck return and `objective.evaluate`'s batch-level
short-circuit each independently keep the engine unreached. **Reproducing the defect honestly
requires mutating both halves at once.**

> **The corollary, and it is the part that costs something later. Doubled guards are usually
> good, but they must be DELIBERATE.** If neither author knew the other's guard existed, a
> later simplification removes one on the grounds that it is dead — and it is dead only
> because the other is there. **Comment both, each naming the other**, so the redundancy is
> visible as a decision rather than as an accident waiting to be tidied away.

### (e2) BEFORE RECORDING A SURVIVING MUTATION, PROVE THE MUTANT DIFFERS FROM THE ORIGINAL ON SOME INPUT

> **A mutation neutralized by code below it produces a green suite and a FALSE COVERAGE GAP,
> and the false gap points at the TEST rather than at the MUTATION.**

**THE DIRECTION IS WHAT MAKES THIS ONE HARD TO CATCH.** Every other entry in (e)'s table ends
with you **over-trusting** a test or a guard. This one makes you **distrust a test that is fine**,
and the work it invites — *"the fixture cannot express this, write a stronger one"* — is spent
against a defect that was never there. **A green suite is evidence about the mutation until the
mutation is known to be a behaviour change.**

**IT IS THE SIXTH CAUSE AND NOT THE FIFTH, AND THE DIFFERENCE IS WHERE THE NEUTRALIZER SITS.**
The fifth is semantically identical **by construction** — visible in the mutated statement alone
(`return` versus `observed = {}` on an empty table). This one is semantically identical **because
of a consumer the mutator did not look at**, and the mutated statement reads as a real change in
isolation. **The fifth is caught by re-reading the line. This one is caught only by tracing the
value to its reader**, which is why it survives a careful mutator.

Worked instance, Phase 2c plan Task 0, 2026-08-24. The pre-flight's third finding was that
`fit`'s warm-start validator must read `:p` per candidate rather than the full `p_max` width,
because the padding beyond `p` is a **legitimate** NaN. The mutation written to confirm the tests
covered it widened the slice:

    rows = x0[:, c, : len(free)]        ->        rows = x0[:, c, :]

**The whole suite stayed green**, and the honest-looking conclusion was *"finding 3 is untested"*.
It is not. The loop beneath iterates `enumerate(free)` and therefore **never indexes `rows` past
`p`**, so the extra columns are never read. `rows` genuinely changed shape — **this is not the
fifth cause, the mutated statement really is a different statement** — and the function did not
change behaviour on any input. **Rewritten as the defect a real implementation would carry** — a
wholesale `np.isfinite(x0[:, c, :]).all(axis=1)` guard placed *before* the per-parameter loop,
which is how someone would actually write it — **six tests fail.**

**The discriminator is one line: construct an input on which the two versions disagree, and print
both. If you cannot, the mutation is not a mutation.**

### (f) Does the brief contradict a docstring already in the tree?

`objective.py` named `design_rank` in two places and the brief still passed `rank_x`.
`terms.py` documented the `Infinity`-token trap that Task 16's fence then reintroduced.

### (g) Does every call match the module's CURRENT signature?

Check the source, not the brief's assumption. The symptom is a plausible number rather than
an error — `n_eff=float(n)` makes `BIC_NEFF` silently identical to `BIC`.

### (g2) BIND EVERY CONSUMER'S SIGNATURE AGAINST THE STORED FIELD LIST

> **For each consumer a store claims to serve without the original data, bind its signature
> against the list of fields actually stored.** A precondition of that shape is a property of
> two lists, not a promise, and nothing checks it unless something compares them.

(g) binds a *call* against a signature. This binds a **schema** against one, and it is the
only way the gap is found before the task that needs it.

Worked instance, Phase 2a Task 8. Design doc §12.8 licenses recomputing derived arrays from
stored primitives without refitting, and the handoff states the precondition: *if any future
change makes `rank_candidates` need the data, §12.8 becomes unimplementable and the three-hash
split buys nothing.* `criteria.CandidateScores` requires `loglik`, `k`, **`n`** and `n_eff`;
§12.2's `/primitives/` listed every one of those **but `n`**, which is not derivable from
anything stored -- it comes from the mask, which is data. Task 12 would have discovered it four
tasks later, when the schema could no longer change.

**Make it executable rather than documentary.** The check is now a standing test:
`CandidateScores`'s per-cell field names are a subset of `/primitives/`'s arrays plus
`/status/`'s. It survives a change to either side, which a docstring does not.

> **A CLEAN (g) MARK IS NOT A PRE-FLIGHT.** (g) clears a brief of **staleness and nothing
> else**. Task 15 bound cleanly and was wrong five ways; Task 16 bound cleanly and shipped a
> serializer that hashed memory addresses. Both were (a)–(f)/(h)–(k) failures, and (g) cannot
> see any of them.

### (h) Does the test exercise the thing it names, or a default?

Thread every parameter the behaviour depends on through as a real caller would. Task 11's
three-N step-rule test passed against a deliberately broken step rule because it left
`scale` at its default, making the numerator 1 and the denominator irrelevant.

### (h2) A METRIC MAY ONLY BE STRATIFIED BY AXES DEFINED AT ITS OWN GRANULARITY

> **Crossing a per-point metric with a per-cell axis either aggregates the axis away or
> duplicates the metric, and both produce a number whose subject is ambiguous. The crossing
> question answers itself once granularity is checked.**

**This is stronger than "decide which axes cross", because it removes the judgement.** The
worked case is Phase 2c decision D9. §11.2 names three difficulty proxies and D4 added
candidate, which at three bins each is **81 cells before any data lands** — a number that
invites an arbitrary trim.

**The axes are not all at one granularity, and neither are the metrics.** Candidate and Hessian
condition are per **cell** `(point, candidate)`; ΔIC-to-next-best is per **point**. Selection
disagreement is per **point**; `|Δℓ|`, parameter distance and signed-trend disagreement are per
**cell**. So each metric crosses **exactly the two axes at its own granularity** — `3 × M` and
`M × 4`, **36 and 48 cells at `M = 12`, and neither was chosen.**

**AND THE SAME CHECK RETIRED A FOURTH AXIS OUTRIGHT.** Failure-taxonomy status looked like a
stratum until granularity was checked: the audit runs on the **both-OK intersection**, so inside
it the axis is **degenerate**. What varies is the **outcome flip** — a fit appearing or
vanishing rather than moving — **a different quantity, with its own denominators, reported
separately.** A stratum that is constant within the population is not a stratum, and the tell is
that it has no granularity **there**.

### (j7) NEVER STRATIFY BY A QUANTITY THE TREATMENT CAN MOVE — BIN BY THE REFERENCE ARM

> **If the mechanism under test can change which stratum a unit falls into, the strata are not
> fixed and the comparison is conditioned on the outcome.** Assign the bin from the **reference**
> arm.

**The worked case is D9's `κ` axis, and the tell is that both values are sitting right there.**
Hessian condition is measured **per arm**: a cell can be well-conditioned cold and
ill-conditioned warm, or the reverse. **Binning by the warm arm's `κ` would let warm-starting —
the thing being measured — move cells between strata**, so a stratum's membership would depend on
the treatment's effect on it. **The bin is assigned from the COLD arm**, which is the reference
and is by construction independent of the mechanism.

**The general form is conditioning on a post-treatment variable**, and it is easy to walk into
because the treated arm's value is usually the more convenient one to hand. **The question to ask
is not "which value is better" but "can the treatment move it".**

### (i) Can the fixture fail at all?

Ask what property of the fixture makes the defect visible; if the answer is "none", the
fixture is wrong before the assertion is. A **quadratic cannot test a step rule** (third
derivative zero). A fixture at `n_eff = 12` **cannot test a floor at 2.0**. And **a fixture of
zeros cannot test a read**: zarr does not write a chunk equal to the fill value, so a
zero-filled store serves every read from the fill value — measured, **0 bytes and 0 keys** for a
read that returned the right number of correct-looking values (Phase 2a Task 6).

### (i10) A PASSING CRITERION CAN BE WEAKER THAN IT APPEARS, AND THE COMPARISON THAT REVEALS IT IS BAND-VERSUS-UNCERTAINTY

> **When a measurement is checked against a tolerance, compare the tolerance to the
> measurement's own uncertainty. If the band is not several times the 2σ interval, the check
> discriminates only gross error, and "met" must be recorded with that scope.**

**This is the (i) family applied to an ACCEPTANCE CRITERION rather than to a fixture.** (i)
asks whether a fixture can express the defect; this asks whether a *criterion* can be failed
at all by the instrument that reports on it. **A band wide enough that the instrument cannot
fall outside it is a criterion that cannot fail**, and it passes looking exactly like a
criterion that was tested.

The tell is a criterion whose tolerance was chosen from the *quantity's* plausible range —
"within 1.5×", "within 10%" — with no reference to how precisely the quantity can be measured.
The two are set by different people at different times and nothing compares them.

Worked instance, Phase 2b Task 7. Exit criterion 6 is *"measured slope and intercept match the
corrected formula within a two-sided band at four or five sides, residuals reported"*. All four
clauses hold: **1021.6 ± 134.7 B/series against an analytic 926, ratio 1.103, inside the
617.3–1389.0 band.** But the band is a **2.25× window** and the measurement's own 2σ interval
is **752–1291** — nearly as wide as the band it is being checked against. **The criterion
discriminates a gross formula error and not a marginal one**, and that scope is now recorded
beside the criterion rather than only in the task that ran it.

> **AND THE SCOPE BELONGS NEXT TO THE CRITERION, NOT ONLY IN THE TASK SECTION.** A criterion
> whose band is wider than its instrument's uncertainty is **a criterion about the
> instrument**, and the next reader meets the criterion first.

#### AND ITS COMPANION: A CRITERION OVER A MEASURED QUANTITY MUST NAME THE READING, NOT JUST THE QUANTITY

> **One run yields several readings of "the same" quantity, and a criterion that names the
> quantity without naming the reading is met on whichever reading the next measurer happens to
> take.** Name the instrument, the moment, and what is alive when the number is taken.

**(i10) asks whether a criterion's band is wide enough to be unfailable. This asks something
prior: whether the criterion identifies WHAT is being compared to the band at all.** The tell is a
criterion phrased in the units of a quantity — bytes per series, milliseconds, resident set — with
no clause saying *when* it is read or *what is still allocated at that moment*. Such a criterion
is not loose; it is **several criteria wearing one sentence**, and nothing makes the choice
between them visible.

Worked instance, Phase 2b Task 8b. Exit criterion 6 is *"measured slope and intercept match the
corrected formula within a two-sided band"*. **One duration-controlled ladder yields three
readings**, fifteen points and three repeats each:

| reading | slope, B/series | ratio to the analytic 926 | inside `slope_band` (617.3–1389.0)? |
|---|---|---|---|
| working set at **end of run** | **970.6 ± 47.6** | 1.048 | **yes** |
| working set at **end of tile**, block alive | **1504.1 ± 21.4** | 1.624 | no |
| **peak** | **2410.0 ± 46.0** | 2.603 | no, by 22σ |

**Met on one of three, and the criterion does not say which.** Worse, *"peak RSS"* and
*"resident bytes per series"* were treated as the same thing through Tasks 4, 7, 8 and 8a —
criterion 7 asserts the **peak** against a budget derived from `resident_bytes_per_series`, and
nothing anywhere states that those are different readings of different moments.

> **AND THE MODEL IS RIGHT ABOUT WHAT IT MODELS, WHICH IS HOW THE AMBIGUITY SURVIVED.** The
> difference between the two working-set readings is **533.5 B/series** against a charged
> `n_time · 9` = **540** — the data term, exactly. `resident_bytes_per_series` charges the block
> correctly and is **silent about everything else**, so every check pointed at residency agreed
> and every check pointed at the peak was off by 2.6×. **A model that is exact on its own subject
> and mute on the rest is the hardest kind to catch**, because its agreements are real.

**The repair is one clause per criterion**: which instrument, at which moment, with what alive.
It costs a line and it is what makes the verdict a fact rather than a choice.

### (i9) A FIXTURE WHOSE WINDOW IS NARROWER THAN THE MACHINE'S JITTER CANNOT EXPRESS ITS CONDITION

> **When a test asserts that something happened DURING a window, size the window against the
> machine rather than against the logic.** A window a few units wide is not a window on a loaded
> box; the test then fails for a reason unrelated to its subject, and it fails **rarely**, which
> is worse than failing always.

(i) asks whether the fixture can express the defect. This asks whether it can express it **under
the conditions it actually runs in** — and the tell is a test that passes in isolation, passes
under synthetic load, and fails once in a full sweep.

Worked instance, Phase 2b Task 2.
`test_a_preempted_command_exits_aborted_early_and_resumes` sends SIGTERM once the store reports
its first completed tile and asserts the run was **mid-loop**: `partial.any()` and
`not partial.all()`. On a 2×2 grid that window is **three tiles wide**, while the parent polls
every 20 ms and competes with its own child for four cores. It failed once in a sweep, and would
not reproduce in isolation or under six busy loops. Widening the grid to 4×4 makes the window
fifteen tiles wide at about twice the runtime.

**The repair is the fixture, never the assertion.** Loosening it to `partial.any()` would delete
the claim — a run that finished everything also satisfies that — which is (i5) one register over:
the tempting fix removes the thing being tested.

#### AND THE SAME RULE ONE LEVEL UP: A RULE WHOSE TEST CANNOT BE WRITTEN DETERMINISTICALLY IS NOT A RULE YOU CAN HOLD

> **When choosing between a refusal and a fallback for a MEASURED quantity, ask what the test
> for each looks like.** A refusal keyed on a value the machine's noise controls fires on some
> runs and not others, so the behaviour cannot be asserted at all — and an unassertable rule
> decays into whatever the code happens to do.

(i9) asks whether a **fixture's window** is wider than the machine's jitter. This asks the same
question of a **decision rule**, and the answer decides the design rather than the test. The
tell is a rule whose input is a measurement rather than a request.

Worked instance, Phase 2b Task 5. A calibrated slope that fails its validation band could
refuse the run or fall back to the analytic formula. At the ladder sizes a suite can afford the
slope is noise — Task 4 measured ±0.3 MB of scatter against 0.43 MB of signal — so **under a
refusal roughly half of suite-affordable `--calibrate` runs fail on the SIGN of the slope**, and
(i2)'s positive control for *"`--calibrate` produces an entry"* could not be written. The
fallback's target is what the same run does without the flag, so nothing is degraded, and the
behaviour is deterministic in both directions.

> **RECORD THE COST WITH THE DECISION, AND CROSS-REFERENCE IT, BECAUSE IT IS A CONSEQUENCE OF A
> CONSTANT SOMEONE MAY LATER MOVE.** The band is `memory.SLOPE_BAND_FACTOR = 1.5`, so a
> calibration can move the per-series cost by at most 1.5× and the tile side by at most
> **√1.5 = 1.22×**. That is why the (i7) fixture in `tests/test_calibration.py` sits at **8
> against 7** and cannot sit wider. **If the band ever widens, that fixture must be
> rechecked** — it is placed against the band, not against the arithmetic, and nothing else
> connects them.

### (i7) A DISCRIMINATING FIXTURE MUST BE PLACED OUTSIDE WHERE THE TWO FUNCTIONS AGREE

> **When a fixture must distinguish two functions, first identify where they AGREE** — fixed
> points, identity regions, degenerate inputs, saturating ranges — **and place the fixture
> outside that set deliberately.** Two functions that differ in general can be identical on
> the values a fixture happens to use.

(i) asks whether the fixture can express the defect at all. This asks the sharper version:
the fixture *looks* built for the comparison, satisfies a stated and correct-sounding
condition, and still lands where the comparison is vacuous.

Worked instance, Phase 2a Task 7. The requirement was **"unequal `p`"**, and it is necessary
and **not sufficient**. `off_0` is 0 under every extent function and `off_1` is the first
model's extent, and **`p = 0` and `p = 1` are the fixed points of `p ↦ p(p+1)/2`** — so
`white` (p=1) first gives **`(0, 1)` under both extent functions**, and a builder that
computes one offset table and reuses it for the other axis passes every offset assertion the
fixture can make. **The discriminating fixtures, which exit criterion 12 must use:**
`matern32` (p=2) first gives **`(0, 2)` against `(0, 3)`** at M=2, and
`white / white + matern12 / matern32` gives **`(0, 1, 4)` against `(0, 1, 7)`**.

**The general failure is specifying a condition without verifying it discriminates.** Ask
what the two functions do on the fixture's *actual* values, not on the property the fixture
was chosen for.

### (i8) THREE SHAPES OF A FIXTURE THAT CANNOT EXPRESS THE DEFECT

> **When a mutation survives, the first question is not "is the assertion weak" but "can this
> fixture produce the defect at all".** Three shapes recur, they are distinguishable, and each
> has its own repair.

Measured in one sitting, Phase 2a Task 12: **three survivors, all three of them fixtures**,
none of them a weak assertion.

| shape | tell | repair |
|---|---|---|
| **The parameter under test is at a fixed point** | the mutated and original expressions agree *on this input* | move the fixture off the fixed point — (i7) at a scalar. *Both* tile sides were 1, so "read back" and "re-derive" returned the same number |
| **The wrong value is read only by a consumer the fixture does not exercise** | output is byte-identical, and the mutated line is genuinely reached | exercise that consumer. `n_eff` is read by `bic_neff` **alone**, so under AIC and HQIC the wrong array changes nothing |
| **THE FAULT CLASS DOES NOT OCCUR ANYWHERE IN THE MODULE** | the guard's input state is never constructed by any fixture | construct it. Every source store in the module was written by this code, so the corrupt-source check had nothing to catch |

**The third deserves its own name: a guard against a condition your fixtures never construct
is untested however many tests run.** It is the most comfortable of the three, because the
suite is green *and* the code is defensive, and the guard's own reason for existing — a store
handed over by someone else — is precisely what a self-generated fixture cannot be.

**And the repair for the second one carries a bonus worth taking: prefer a second production
path to a hand-computed constant.** The `bic_neff` test asserts the recomputed ranking equals
**the fit path's own values for that criterion** — a different derivation reaching the store
by a different route, which is (j) satisfied with something stronger than a literal.

### (i6) WHEN ESTABLISHING A CONTRACT, YOUR INTUITIONS ABOUT IT ARE PRE-CONTRACT

> **A test written to establish a contract cannot assume the contract.** Every expectation in
> it was formed before the measurement existed, so each one is itself a claim to measure —
> including the ones that feel like restatements of the thing being established.

(i) asks whether the fixture can express the defect. This asks about the **assertions**, in the
one situation where the usual source of expected values — the documented behaviour — does not
yet exist.

Worked instance (open question 12's closure). The test establishing that a child inherits the
parent's high-water mark asserted, among its conditions, `small_child == small_peak`: for a
parent that allocated nothing, surely the child reads what the parent reads. **It fails.** The
small parent is itself spawned by pytest and therefore *reports* the session's watermark, while
its child gets only the 74 MB it generated itself — which is the **non-compounding** rule, the
very thing the next test was written to establish, appearing inside the test written to
establish its premise. The assertion is now `small_child == small_current`, with the reason in
the test.

The tell is a test whose subject is "what does X actually do" and which contains an assertion
justified by "obviously". Measure that one too.

### (i3) A RELATION BETWEEN OBSERVATIONS IS NOT A SUBSTITUTE FOR THE OBSERVATIONS

> **An assertion comparing two derived values passes when both are absent, both are wrong in
> the same direction, or both are degenerate.** Assert each value against its own expected
> result **first**; assert the relation between them only as an additional check.

**This is the cancellation rule (a) in a new location** — a relation is *constant* across any
change that moves both sides identically, so it is invisible to exactly the defects that move
both sides.

The cleanest instance is Phase 2a Task 1's `assert fit_moved == compat_moved`, written to
check that a warm-start setting reaches fit identity. `(False, False)` satisfies it, so it
passed against a payload flattening that **dropped the field entirely** — the one defect it
existed to catch. The fix is one expected triple per case, spelled out.

The shape recurs wherever the natural assertion is an equality, a ratio or an ordering between
two computed things: `a == b`, `before < after`, `len(x) == len(y)`. Each is satisfied by two
empties, two zeros, or two identical mistakes.

### (i4) AN ERROR MESSAGE MATCHING THE INPUT IS NOT EVIDENCE THE INPUT WAS DIAGNOSED

> **Any library that quotes user input back in its error text will satisfy a `match=` on that
> input regardless of which error actually fired.** Assert the error **type** and the specific
> failure mode, not the presence of the user's own string.

Worked instance: `pytest.raises(ValidationError, match="data_url")`, written to check that a
misspelled config key is refused as an unrecognized field. Under `extra="ignore"` the typo is
dropped, the *required* key is then simply missing, and pydantic renders the offered mapping
in its `input_value=` echo — so `data_url` appears in the message of an error that never saw
it. Measured: the mutation to `extra="ignore"` left the test green.

The assertion that bites reads the structured error: `errors()[i]["type"] == "extra_forbidden"`
with `loc == ("data_url",)`. Same principle without structured errors: match a phrase the
*diagnosis* owns, never one the input supplies.

### (i5) WHEN A FIXTURE CANNOT EXPRESS THE DEFECT, ASK WHETHER THE OBVIOUS REPAIR IS LOCAL

> **If the tempting fix for a failing assertion moves a SHARED CONSTANT, the fixture is not
> merely weak — it is a trap.** A local test failure then buys a global regression, and the
> commit that does it looks like a test fix.

(i) asks whether the fixture can express the defect. This asks what happens *when the answer
is no*, and it is the first instance in this project where the wrong repair is worse than the
wrong test.

Worked case: the Phase 2a plan asked for a test that the unique-Δt count is "large for an axis
perturbed by float noise". It is not — `UNIQUE_DT_RTOL = 1e-9` sits decades above float64
rounding, so the perturbation collapses and the assertion fails. **The obvious repair is to
lower `UNIQUE_DT_RTOL` until the fixture behaves**, which destroys the `F`/`Q` amortization on
every axis in the system to satisfy one test — a global performance regression whose commit
message would say "fix flaky time-axis test".

The check: when an assertion will not go green, name what would have to change. If that thing
is shared — a module constant, a tolerance, a schema default — stop and fix the fixture.

### (i2) A PURE NEGATIVE NEEDS A POSITIVE CONTROL

> **Any assertion of the form "X did not happen" is unfalsifiable unless a paired test
> proves X CAN happen through the same wiring.** The control is not scaffolding around the
> real test — **it is the half of the test that can fail.**

(i) asks whether the fixture can express the defect. This asks something stronger and it
applies whenever the *observable is an absence*: no fit ran, no write occurred, no refit
happened, no network call was made, nothing was recompiled. An absence is produced equally
well by the thing being correctly suppressed and by the thing never being connected, and
**the two are byte-identical in the test output.**

The worked case is Phase 2a Task 0's raising stub engine. A stub wired into a run and never
reached is indistinguishable from a stub never wired in at all; every "no fit ran" assertion
downstream passes for free the moment the injection seam moves. **The pairing that fixes it
is a test that the stub DOES raise when a fittable batch goes through the same call.**

**The control earns its place by finding wrong beliefs about the code's shape, not just
wiring faults.** On its first run that one failed — the engine is handed `B = 1`, not the
tile's `B`, because `fit` drives `optimize_series` once per series. That is exactly the
class the pre-flight exists for, and **a negative-only test can never surface it**: it has no
successful path to be wrong about.

Three further shapes this covers, so it is not read as being about stubs:

| the negative | the control it needs |
|---|---|
| a completion bit is not set after an injected interruption | the same injection point, not triggered, does set it |
| a value edit does not move `geometry_hash` | a geometry edit through the same fingerprint call does move it |
| a resume refits nothing | the same resume with one outstanding tile refits exactly that tile |

#### WHEN AN INSTRUMENT REPORTS "NO EFFECT FOUND", CONSTRUCT THE EFFECT AND CONFIRM IT SEES IT

> **A null result is a claim about the instrument before it is a claim about the subject.**
> Build the effect the instrument says is absent, feed it through the same wiring, and check
> that it shows up.

**Three defects in ONE instrument, found in one task, and the direction is the pattern: every
one of them produced a confident null.** Phase 2b Task 8's accumulation report:

| defect | the confident null it produced |
|---|---|
| fed a **monotone high-water mark**, which stops moving | identical readings, zero residual, zero standard error — *"this run excluded every per-tile leak of every size"* |
| the guard written as `variance == 0.0` | least squares on identical integers returns residuals of order **1e-8**, so the exact comparison lets precisely that case through |
| `saturating` read as *"no leak"* | a run can saturate **and** leak: a constant per-tile cost raises both slopes equally and leaves their difference, and the flag, untouched |

**The second was caught by a positive control inside the task**, not a task later: a 1 MB/tile
leak injected into a real run's own readings, which is (i2) paying for itself in the sitting
that wrote the bug. **A null result nobody tried to break is an untested branch.**

#### AN INTERFACE BLOCK THAT PRODUCES A VALUE NO CONSUMER TAKES IS A MECHANISM WITH NO EFFECT

> **Before implementing a brief, trace its output to the consumer that reads it. If no
> existing signature can accept the value, the brief describes a producer with no consumer,
> and every test of it will pass while the mechanism does nothing.** The tell is a brief whose
> tests all concern the artifact's **contents** rather than its **effect**.

**This is (i2) applied to a TASK rather than to a test**, and the two failures are the same
one at different scales. (i2) says an absence is produced equally well by correct suppression
and by a thing never wired in. This says a *presence* — a file, a record, a well-formed
artifact — is produced equally well by a mechanism that works and by one that is connected to
nothing, and a suite that only opens the artifact cannot tell them apart.

Worked instance, Phase 2b Task 5. The brief specified `cache_path`, `cache_key`,
`versions_digest`, `load` and `store`, which between them produce and persist a
`CalibrationResult`. **`tiling.tile_side_for` computes the per-series cost internally and takes
no per-series argument**, so no slope out of that cache could reach any number a run uses.
Every one of the brief's tests would have passed.

**The sharpest form of the tell was inside the brief's own test list, and it is worth quoting
verbatim**: *"a stale entry under a changed digest is **not used**"* — an assertion that
presupposes an entry that **is** used, in a brief that describes no path by which one could
be. **A brief that tests the negative of an effect it never provides is telling you the effect
is missing.**

The repair is a **parameter on the existing consumer**, not a second derivation at the
producer's call site: a calibrated path that re-did the arithmetic would drift silently,
because a wrong tile side still runs. **That is the third time (a6)'s shape has arrived by a
new route** — after `Backend` outliving its architecture and the inverse that could have
re-derived rather than round-tripped — and the routes keep differing while the shape does not.

#### (i2b) A HIGH-CEILING CONTROL CONVERTS A NULL INTO A LOCATED NULL

> **When measuring whether a mechanism helps, include an arm that supplies the mechanism's
> BEST POSSIBLE input.** A null without a ceiling is ambiguous between a weak mechanism and a
> weak source, and **only the second is a finding about the domain.**

This is (i2) generalized one step: the positive control asks *"can the instrument see
anything"*, and this asks *"how much is there to see"*. The first makes a null trustworthy; the
second makes it **interpretable**.

**The worked case is 2c Task 0, the warm-start spike.** Warm-starting a pass-2 point from its
nearest valid coarse neighbour saved **7.80% ± 0.77%** of iterations against a threshold of 30%,
and **nothing** in wall clock. Read alone that is *"warm-starting does not help here"* — a
sentence that could equally mean `x0` was mishandled, the harness was wrong, or the optimizer
does not respond to its start at all.

**The ceiling arm removes all three readings at once.** Starting each point from **its own**
converged `θ̂`, through the same call, saved **93.97% ± 0.16%** of iterations and **62.18%** of
wall clock. So the machinery delivers when the start is right, and the finding is not about the
plumbing:

> **the optimum is far less spatially coherent than the data is.**

That is a statement about the science, and it is the one a future session needs. **A reader
proposing warm-starting again must see 94% next to 7.8%**, or they will read the 7.8% as a bug
to be fixed rather than as a property of the field.

**The ceiling arm is usually the cheapest arm in the design**, because the best possible input
is normally already lying around — here it was the cold arm's own output.

#### (i2c) A SIGN-UNSTABLE BENEFIT IS WORSE THAN A SMALL ONE, AND THE STRATUM THAT FLIPS IS THE FINDING

> **Report the stratum where a mechanism's benefit changes SIGN, not just its pooled
> magnitude.** A mechanism that helps on average and harms somewhere specific needs a policy
> for that somewhere — and a pooled number cannot tell you the policy is missing.

Same task. Same-regime warm starts saved **+9.75%**; warm starts whose source lay across the
field's regime boundary cost **−16.27%** — a 26-point swing, and the wrong side of zero.

**The mechanism harms exactly where spectral shape changes**, which is where the scientific
interest is and where §11.2 says hysteresis concentrates. **This would have mattered even under
a passing pooled number:** at a 30% pooled saving the design would still have needed a boundary
policy, and §11.1's two-pass warm start **has no notion of regime boundaries at all.** The
measurement did not merely size the benefit — it named a piece of the design that was never
specified.

### (j) Does the oracle share a derivation path with the thing it checks?

An independent oracle means a **different construction**, not different constants.

| subject | the bad "oracle" | why it is not one |
|---|---|---|
| `hessian_at_optimum` | `tests/oracles.fd_hessian` | the same second-difference stencil at a different step — it measured the step choice and nothing else |
| `theta_err` (delta method) | `theta_err / theta` | the same quantity rescaled by the very Jacobian under test |

The tell: if the reference is not at least ~100× more accurate than the subject, it is
probably the same algorithm. Nested Richardson qualifies; a wider step does not.

#### (j5) A SECOND INSTRUMENT IS A CROSS-CHECK ONLY IF IT MEASURES THE SAME QUANTITY UNDER THE SAME CONDITIONS

> **When two instruments differ BY CONSTRUCTION, their disagreement has no interpretation —
> and reporting it invites someone to reconcile two numbers that were never comparable.**

(j) asks whether a second instrument is *independent enough*. This asks the prior question:
whether it is measuring **the same thing at all**. An instrument can be beautifully
independent and still worthless as a check.

**The test is symmetric and it is the whole rule:** if **agreement would be a coincidence**
and **disagreement would be expected**, the comparison is uninterpretable in both directions
and should not be built.

**The two genuine cross-checks in this project both pass it, and they pass it the same way —
same quantity, different route:**

| cross-check | same quantity | different route |
|---|---|---|
| brute-force MVN against `celerite2` | one likelihood | a dense Σ against a semiseparable solver |
| the residue's two eliminations, **618.4 ± 24.2** and **618.3 ± 30.5** | one residency term | the tensor **bounded by chunking** against the tensor **never built** (tier 2) |

**The rejected one fails it on the first column.** Phase 2c decision D5 considered reporting
pass 1's RSS reading beside 2b's standalone calibration. Pass 1 fits a **coarse subsample** —
a fraction of a production tile's batch — and is **cold** where pass 2 is **warm-started**, a
42% iteration and 46% wall-clock difference per series at `N = 630`. **Two axes of difference,
neither modelled**, so the two readings are different quantities and the comparison was not
built.

**AND THIS PROJECT HAS ALREADY PAID FOR THE MISTAKE TWICE, WHICH IS WHY IT IS A RULE.** The
193-versus-240 reconciliation compared a **charge** against a **slope of the excess over that
charge** and called them *"two provenances 24% apart"*; G5's H5 compared **13 allocation sites
seen during a fit** against **counts of named `FitResult` fields** because one record mentioned
both. **Both were two counts of two different things, compared because they sat near each
other.** The rule above is what would have stopped all three.

#### (j6) BOUND THE UNMEASURED REGION BEFORE MEASURING IT — SOMETIMES THE BOUND CLOSES THE QUESTION

> **Before measuring another point on a curve, compute the maximum the unmeasured region
> COULD be worth. Where that bound is smaller than the decision's margin, the question is
> closed by arithmetic and the measurement is not worth taking.**

**This is (j4) applied FORWARD** — to measurements not yet taken, rather than to tables already
published.

**The worked case is 2c Task 1, the stride curve.** Net saving came in at **32.95 / 37.69 /
38.71%** for `k = 2 / 4 / 8`, still rising at the largest stride measured — which normally
argues for a `k = 16` fixture, and this project had already been punished once for stopping a
lever at two points. **The bound says otherwise.** The objective is
`1/k² + (1 − 1/k²)·r`, and at `k = 8` the pass-1 fraction is already **1.6%**, so the **entire**
remaining prize from `k → ∞` is `(1/64)·(1 − r) ≈ **0.61 points**` — **and any degradation in
`s(k)` beyond 8 subtracts from it directly.** `k = 8` is therefore within 0.61 points of the best
achievable stride, whatever it is. **A `k = 16` fixture could not change the answer**, and the
~2 h it would have cost was not spent.

**THE BOUND IS ONLY AVAILABLE BECAUSE THE OBJECTIVE WAS WRITTEN DOWN FIRST.** Without a formula
there is nothing to take a limit of, and the honest move would have been another fixture.

#### (i11) STATE REFUTATION CLAUSES IN BOTH DIRECTIONS — THE SURPRISE LIVES WHERE YOU WERE NOT LOOKING

> **A refutation clause that can only fire one way halves the value of the prediction.**

**2c Task 1's S2 is the worked case, and it is a near miss rather than a failure.** It predicted
`s(8)` at 35–40% and wrote its clause for **degradation** — *"below 32% refutes this"*. The
measurement came in at **42.42%**, **above** the band, so the band was missed and **the clause
could not fire.** The claim held harder than predicted, which is a good outcome **reached by a
prediction that could not have caught the opposite.**

**This project's prediction record is strong precisely because refutations have been
informative** — A-double-prime's C2, A-triple-prime's D2 and D6, P4, P9. **A one-sided clause
forfeits half of that**, and the direction you did not fear is the one worth insuring.

### (j2) A MEASUREMENT VALIDATES THE CODE PATH THE INSTRUMENT EXERCISES, NOT THE ONE THE FORMULA CLAIMS TO DESCRIBE

> **Before trusting a validating measurement, verify the instrument drives the production
> path** — same entry point, same loop structure, same batch shape. **A benchmark that
> approximates the workload validates the approximation.**

**This is worse than an unvalidated formula, because the validation is what makes it
trusted.** (j) asks whether the oracle shares a derivation path with its subject; this asks
something narrower and easier to miss — an instrument built from the **formula's**
assumptions rather than from the **code's** is an oracle sharing a derivation path, and it
will agree.

Worked instance, Phase 2b F2. `memory.bytes_per_series` described a batched optimizer;
`fit.py:223` loops `optimize_series` over one series at a time; and the confirming
measurement, `measure_evaluation_rss_slope`, drove `unconstrained_loglik` on a **batch of B**,
which genuinely does hold `B × (d²…)`. **The measurement was sound, the formula was sound for
what the instrument did, and neither described production.** The agreement — 8471 B/series
measured against a 6382 B floor, a ratio of 1.33, inside the ~1.5× band — was read as
confirmation for four months.

The check is one question: *what does this instrument call, and is it what the run calls?*
Where the answer is "not quite", the instrument's disagreement with the production path is a
**quantity to measure and name in advance**, never a discrepancy to reconcile.

#### A LADDER SPECIFIED IN THE WRONG VARIABLE IS UNREACHABLE, AND HITTING IT REQUIRES THE DIVERGENCE THE MEASUREMENT EXISTS TO AVOID

> **Specify a measurement's independent variable in the units the production path can actually
> take.** A ladder in a **derived** quantity forces the instrument off the production path to
> reach its own points — which is the failure the instrument was built to avoid.

**This is (j2) one step earlier, at the specification rather than at the harness.** (j2) asks
whether the instrument drives the production path; this asks whether the *points it was told to
measure* are on that path at all. A brief can pass (j2) as written and still be unimplementable,
because the divergence is smuggled in through the axis rather than through the code.

Worked instance, Phase 2b Task 4. The brief's ladder was **B ∈ {1000, 2000, 4000}** — a ladder
in **series**. A run's batch is a **tile**, so `B = side²` on a base-16 grid and the reachable
values are {256, 1024, 2304, 4096, …}: **√1000 = 31.6**, and none of the three is a tile.
Reaching them would have meant bypassing the tiling — **(j2) in the exact dimension under
measurement**, since the tiling arithmetic is what the calibration exists to check.

**THE REPAIR IS THE TRANSFERABLE PART: A ROUND TRIP, NOT A RE-DERIVATION.** The ladder is in
sides, and `tiling.budget_bytes_for_side` seeds a closed form and then **asks
`block_bytes_for`** whether that budget buys the block it needs. So the inverse cannot disagree
with production about what a budget buys. **An inverse that re-derived the arithmetic instead
would be a second description of one subject** — (a6)'s shape, arriving by a new route — and it
would drift silently, because a ladder at the wrong B still runs and still fits a line.

> **AND BOUND THE ROUND TRIP.** An unbounded correction loop repairs *any* wrong closed form,
> one step at a time, and reports nothing. Measured: with the walk unbounded, a mutation that
> dropped the headroom from the closed form still returned the right answer — after ~10⁸
> single-byte steps, turning a 2.4 s module into a 21.5 s one, with every assertion green. The
> bound is what turns the round trip from a repair into a **check**.

### (j3) AN EXISTING FEATURE CAN BE AN INSTRUMENT FOR A PROPERTY ITS OWN PURPOSE DOES NOT CONCERN

> **Before building a harness, enumerate the code paths that already exercise the loop under
> test with the expensive part absent.** A cheap instrument found this way **drives the
> production path by construction**, which is exactly what (j2) says a purpose-built harness
> does not.

The pairing with (j2) is the point: this is not an efficiency. A bespoke harness for the same
property would approximate the loop and then validate the approximation.

Worked instance, Phase 2b Task 8. The claim is *peak RSS does not grow with tile count*, which
needs many tiles, and fitting them is prohibitive — 5.4 s/series. **`--reuse-fits-from` is the
tile loop with the fit removed**: same loop, same write path, same completion bitmap, no
optimizer. A recompute over 10⁵–10⁶ points runs in minutes and exercises the production loop
rather than a copy of it. It was cheap all along and was built for something else entirely.

**State what such an instrument does NOT cover**, or it reads as a stronger claim than it is:
a recompute holds less than a fit does, so it witnesses no accumulation *in the loop* and says
nothing about what the engines or the optimizer retain.

#### (j4) AN EXISTING MEASUREMENT IS EVIDENCE, NOT HISTORY

> **Before measuring, check whether a table you already have answers the question.** A prior
> task's published numbers are **inputs**, not a record of what happened, and **the cheapest
> possible instrument is arithmetic on data already in hand.**

(j3) finds an existing **feature** that can serve as an instrument; this is one step earlier and
finds an existing **measurement** that is already the answer. Worked instance, Phase 2b Task 8:
exit criterion 7 asserts *"peak RSS at or below the budget"*, and `budget_bytes_for_side` had
chosen every budget in Task 7's published ladder. **The criterion was four subtractions from a
table that had been in `PROGRESS.md` for a day, and nobody performed them — through a task and
a review.** The peaks were read as a record of a completed measurement rather than as data.

**The tell is a criterion phrased as a comparison between two quantities you can both already
name.** Write the subtraction before you plan the run.

#### AND ITS COROLLARY: A CHEAP INSTRUMENT CAN NEED AN EXPENSIVE INPUT, SO PRICE BOTH

(j3) prices the instrument. **Price what the instrument has to be fed.** `--reuse-fits-from`
reads its tile side from the **source** store and refuses one whose completion bitmap is not
full, so the cheap recompute needs a complete **fitted** store at the same scale — hours of the
work the instrument exists to avoid. The brief priced the first and not the second.

**The repair generalizes and is worth reaching for: make the expensive input degenerate rather
than small.** A wholly-masked series short-circuits before any design or optimizer is built, so
a mostly-masked input produces a **complete store of the right geometry for almost nothing**,
and the loop under test moves identical bytes because the copy is shaped by the arrays and never
by the outcomes. **Keep a live fraction** so the successful path stays reachable, and **state
what the degeneracy skips.**

### (k) Does anything that must be stable across runs depend on process-local state?

Set iteration order, `id()`, the `repr` of an unordered container, time, environment.
**Test across processes, not within one.**

**This is the only category a perfect in-process suite cannot reach.** Every test in one
pytest run shares a single `PYTHONHASHSEED`, so a quantity stable within a process and
unstable between them is invisible to every same-process test **and to mutation testing**,
which runs in that same process against the same frozen seed.

Worked instance: `json.dumps(..., default=repr)` renders `{"aic","bic","hqic"}` as three
*different* strings under seeds 1, 2 and 3, and an object without `__repr__` renders its
memory address. Every fence test passed; every resume of a finished store would have refit
it, with no symptom but a bill.

**(k) extends to repeated measurement, and that is a distinct shape.**

> **A repeated measurement must vary everything the measured quantity depends on.**
> Repeats inside a fixed allocation, a fixed input, or a fixed process measure
> **precision, not accuracy** — the component held fixed outside the repeat loop is
> invisible to them by construction, and a best-of-N over one allocation, published as
> though it were fresh, reports a confidence the method cannot support.

> **AND A PREDICTED PRECISION IS A CLAIM, WITH THE SAME PRECONDITIONS AS THE MEASUREMENT IT
> COMES FROM.** Scatter is a property of **an instrument on a fixture**, not of an instrument.
> Carrying a scatter figure to a different fixture is carrying a measurement without its
> conditions, which is the rule above pointed at the error bar rather than at the value.
>
> Worked instance, Phase 2b Task 7. The pre-flight predicted **SE ≈ 32 B/series** for its
> ladder, from Task 4's **±0.3 MB** between-child scatter. The measured RMS residual was
> **0.88 MB** on a different fixture — a 160×160 grid with a larger input to open and tile —
> so the prediction was **wrong by 4×** and the ladder returned a bound where a value was
> expected.
>
> **THE COUNTERPART IS WHAT MAKES IT INSTRUCTIVE: the TIMING prediction from the same planning
> pass was right to 2%** — 290.3 ms/series measured against 283.8 predicted. **One prediction
> transferred and one did not, and the difference is that the timing figure was measured on
> the fixture it was used for and the scatter figure was not.** Record a predicted precision as
> wrong rather than absorbing it: the next estimate is only checkable if the last one's error
> is on the record.

Measured (P4): the spike's A:B spread at its worst cell is **0.13** across eight repeats
inside one allocation and **0.82** across eight fresh processes; path A also runs ~16%
slower on freshly allocated inputs (path B ~4%). The published ±0.15 scatter came from the
inner loop. The check: **list what the number depends on, then list what the repeat loop
re-creates** — anything in the first list and not the second is a systematic the
measurement cannot report. If the production condition allocates, and a tile is
materialized, fitted and dropped, the repeat must allocate inside it.

**(k) extends to every delta, rate or trend.** Any assertion on a *difference* must be
checked for whether its **baseline is set by history outside the test**:

| assertion | why the baseline is not the test's | the fix |
|---|---|---|
| "allocating 256 MiB moves peak RSS by 256 MiB" | peak RSS is a **high-water mark**; measured, a watermark at 385 MB moved **67 MB** | pin against an absolute reading in the same test (`current_rss_bytes`) |
| "total STREAM throughput rises with thread count" | on a saturated controller the **sign** is the session's CPU load: 10.59 → 12.03 GB/s unloaded, **11.23 → 8.44** under contention | assert a **ratio** that survives either loading |

And the harder lesson: **both modules already documented, in capitals, the property that
broke the test.** The violating tests were written anyway, by the same author, in the same
sitting. **Documentation does not constrain the next author — tests do.**

#### AND A LINEAR FIT TO A SATURATING PROCESS REPORTS THE TRANSIENT AS A RATE

> **A one-time cost charged across N observations comes back as a per-observation rate, and its
> significance grows with the size of the transient.** High sigma is not protection — it is the
> symptom.

Worked instance, Phase 2b Task 8. A tile loop pays numba's entry points, zarr's metadata and the
allocator's arenas **once, at the front**. A straight line through all 36 tiles returned
**+69 083 ± 9 523 B/tile at 7.3σ** — confident, significant, and entirely fabricated;
extrapolated to a production grid it invents 690 MB of leak that does not exist.

**AND THE TAIL IS AN UPPER BOUND, NEVER A VALUE, BECAUSE THE BOUND FALLS WITH RUN LENGTH.**
Measured on one loop, the excluded bound fell **26×** between a 36-tile run and a 400-tile one —
the figures are in `PROGRESS.md`'s Task 8 section and are not repeated here. At 36 tiles **even
the second half was still transient.** So a saturation claim carries **the run length it was
measured at**, and a longer run is entitled to a smaller bound. Fit both halves, publish the tail, and split them on a **fixed rule** — a
warm-up boundary chosen by looking at the readings is the analysis fitted to the answer.

### (k2) THE RUNTIME'S OWN CODES ARE PART OF YOUR VOCABULARY WHETHER YOU CHOSE THEM OR NOT

> **When defining a coded vocabulary that crosses a process boundary — exit codes, signal
> numbers, HTTP statuses, error codes — enumerate the values the RUNTIME and its libraries
> already emit before assigning your own.** A collision with a value you did not choose is
> invisible in your source and appears only under a condition you did not test.

The (k) family, one level out again: (k) is about state the process owns, this is about
*symbols* the process emits that you never wrote. **Both instances below were found by
enumerating the emitters, not by reading the code**, because there is nothing in the code to
read — the emitting line is in argparse and in CPython's top level.

Worked instances, Phase 2a Task 4's five-code exit taxonomy:

| the runtime's code | what the taxonomy says it means | outcome |
|---|---|---|
| **argparse exits 2** on a usage error | `ABORTED_EARLY` — a run that started, evaluated its abort criterion and stopped | **fixable**: `ArgumentParser.error` overridden to exit 3 |
| **CPython exits 1** on an unhandled exception | `COMPLETED_WITH_FAILURES` — a run that finished with a failure rate above threshold | **not fixable inside a taxonomy with no internal-error code** |

**The second is the instructive one, and living with it is a decision rather than a
consequence.** An unhandled exception and "completed with failures above threshold" are
**opposite facts about a run**: the second says the run finished and the map is written, the
first says it did not. A caller that resumes on 1 resumes from a crash. The alias is harmless
only while 1 has no producer, so the honest fix when it acquires one is a **distinct
`INTERNAL_ERROR` code**, not a convention about tracebacks. Recorded against sub-phase 2e in
`PROGRESS.md`.

**(h), (i) and (k) are not subsumed by mutation testing.** (e) asks whether a test bites
when the guard is deleted; (h) and (i) ask whether the call site and fixture can *express*
the defect at all; (k) asks whether the defect is observable in one process.

**Also: run the brief's code.** The two highest-yield audits did. Task 17's fence asserted
`tile_side(1e9, 28650) == 187` against an implementation that floors — `floor(186.83)` is
186, and the test would have failed against the code printed beneath it.

---

## 2. Standing rules

### eps-derived constants — one construction, three instances

A numerical threshold here is **derived, not chosen**: from float64's precision and **how
many times the quantity is squared or differenced on its way to the objective.**

| constant | path to the objective | rule | value |
|---|---|---|---|
| `lint.WHITE_COLLAPSE_LOG_LIMIT` | ℓ is quadratic in θ near the optimum, so a model difference is resolvable only above `√eps` — one squaring | `−½·log eps` | 18.0218 |
| `objective.CONDITION_LOG_LIMIT` | the solve runs on the normal equations, so the Cholesky sees `cond(X_w)²` | `−¼·log eps` | 9.0109 |
| `gradients.fd_step` / `hessian_step` | an `m`-th difference divides by `h^m` | `eps^(1/(m+2))` | 6.055e-06 / 1.221e-04 |
| `optimize.HESSIAN_COND_LIMIT` | H is inverted **once**, for `H^-1` and `theta_err` | `eps^(-1/2)` | 6.7109e7 = 2²⁶ |
| `signal.X_RANK_RTOL` | every consumer forms the Gram, so the ratio is squared | `eps^(1/2)` | 1.4901e-08 = 2⁻²⁶ |
| `objective._NEGATIVE_REDUCTION_RTOL` | `eps` × the largest `cond(Gram)` reachable before `ILL_CONDITIONED_X` | `eps · eps^(-1/2)` | 1.4901e-08 = 2⁻²⁶ |

**The last three landed 2026-08-10 (P1) and all three replaced picked values.** They come
out at `2^±26` by three different routes, which is a hazard in itself: state each
derivation separately and never reach for the neighbour's exponent because the answer
looks familiar.

State each in the **units of the quantity it thresholds** so they are comparable. **When a
fourth is needed, count the squarings and differences and read the exponent off — do not
pick a round number and do not copy a neighbouring constant.** Copying the neighbour is the
measured default mistake: 147× at the Hessian step, 280×–1100× at the gradient.

**A constant that genuinely cannot be derived is POLICY and must be labelled as such, with
its consequence stated.** `lint.OVERLAP_RATIO = 1.5` says in its own docstring that two
Matérn ν=1/2 ACFs a factor `r` apart differ at most by `r^(−1/(r−1)) − r^(−r/(r−1))`, which
at `r = 3/2` is exactly **4/27**.

**~~Still picked, flagged:~~ CLOSED 2026-08-10 (P1).** `optimize.HESSIAN_COND_LIMIT` and
`signal.X_RANK_RTOL` are both derived now; see the table above and open question 9 in
`PROGRESS.md` for which fixtures moved.

**Two corrections to what this section originally said, both worth carrying:**

- **`RANK_DEFICIENT_LOG_LIMIT` is NOT derived from `signal.X_RANK_RTOL`.**
  `objective.py` imports `_RANK_RTOL` from `engines.kalman` — the **Gram** cutoff — and
  derives from that. The two constants live in different modules, threshold different
  matrices, and both happened to hold the numeral `1e-10`, which is the entire mechanism of
  the misreading. Re-deriving `X_RANK_RTOL` alone would have left
  `RANK_DEFICIENT_LOG_LIMIT` resting on the other one regardless.
- **`kalman._RANK_RTOL` is deliberately left at `1e-10`, and that is not a picked value.**
  Its docstring carries a measured calibration table and a window bounded from both sides:
  an exactly deficient design puts its null singular value at 0 or ~5e-17 of the leading
  one, decades below any candidate threshold, while a Gram accumulated at `cond(X_w) = 1e8`
  has already lost its small singular value into float64 noise, so a threshold below
  ~1e-16 would be reading rounding error. That is the "measure, or document explicitly"
  branch of the rule, satisfied, not the "picked" branch.

**`optimize.GRAD_TOL` is the one constant here that is NOT eps-derived, deliberately.** Its
floor is set by scipy's L-BFGS-B stopping rule, several decades above what the
finite-difference gradient could resolve (measured instrument floor ~3e-10 relative to
`|loglik|`), so float64 has nothing to say about it. It is a **measured separator** between
two populations — converged fits at `3.46e-07 .. 2.30e-05` and fits stopped at one to three
iterations at `1.45e-04 .. 1.84e-02` — and both bounds are pinned by a test. Its previous
`1e-5` sat *below* the converged population's maximum.

#### AND THE EXTENSION TO A CONSTANT THAT CANNOT BE DERIVED: STATE WHAT IT HAS NOT BEEN VALIDATED AGAINST, IN THE CONSTANT

> **Where a threshold can be neither eps-derived nor separated between two measured
> populations, record which side of it was measured and which side was not.** A constant
> anchored on one side is not a bad constant; a constant that does not say so is.

**This is the same discipline one register out.** `GRAD_TOL` is defensible because **both**
populations were measured and it sits between them. `RSS_STALL_LIMIT_US_PER_S` has only the
good side: 0.9 ms/s idle and **5.3 ms/s during a measurement whose answer was correct**, so
50 ms/s is roughly ten times known-good — **and the rate during the failing sweep was never
recorded, so it has never been checked against a known-bad reading.** That sentence is in the
constant's own docstring, next to the number, with the instruction that the next failure
should record its rate.

**The alternative is what makes it worth the paragraph:** a threshold with one measured side
and a confident docstring is indistinguishable from `GRAD_TOL` to a later reader, who will
treat it as settled and tune around it. **Naming the missing half is what keeps it a
provisional number rather than a fact.**

### The development environment cannot test the shipped artifact

> **`pixi run` executes off `PYTHONPATH=src` inside an environment that already has
> everything, so a dependency the package fails to DECLARE is invisible to every test run
> that way.** The property that must hold is a property of a *different process* — one that
> has only what the distribution asked for — and no amount of testing in this one reaches
> it. **This is the same argument as (k)**, one layer out from `PYTHONHASHSEED`.

**It fails only for users, never for you**, and it recurs at *every* task that adds a
dependency, which is what makes it a standing requirement rather than a finding. Phase 2a
Task 0 is the worked instance: `xarray` and `pydantic` sat in `pixi.toml` while
`pyproject.toml`'s `dependencies` named neither, and `tests/test_core_isolation.py` had been
documenting a `[batch]` extra that did not exist since Phase 1.

The guard is `tests/test_packaging.py`, in the full sweep: **build the wheel, install it into
a clean virtual environment, and check the artifact from inside that environment** — that
every module the package claims to ship is importable there, and that every third-party
import under `src/` is named in the *wheel's own* metadata rather than in `pyproject.toml`.
Its limits are stated in its own docstrings; read them before trusting it further than they go.

**Writing that guard produced (i2) applied to itself, which is the strongest demonstration
the category has.** The clean environment was not clean: `PYTHONPATH=src` is inherited by
subprocesses, so `metamer` resolved out of the development tree while every assertion passed,
and the isolation control checked only that *numpy* was absent — which it genuinely was. Two
independent leaks with different causes, and the control saw one of them. A guard against a
class of defect is itself a member of that class.

**And a general trap it turned up: `importlib.util.find_spec` IS NOT A NON-EXECUTING CHECK.**
It locates a module without running it and **runs every parent package on the way**. In a
dependency-free environment `find_spec("pkg.sub.mod")` raises whatever `pkg/__init__.py` and
`pkg/sub/__init__.py` raise — measured here as `ModuleNotFoundError: No module named 'numpy'`
raised from inside `find_spec`. Anywhere module *presence* must be checked without importing
its dependencies, it is a filesystem question, walked outward from a package `__file__` that
is safe to import.

### An aggregate over a precedence ladder needs its own rule, not the ladder

> **A precedence order defined for one axis does not transfer to a reduction over another
> axis.** State the reduction rule explicitly and separately, and **test it at the case where
> the two disagree** -- one member OK, another failed.

`objective.OUTCOME_PRECEDENCE` ranks `OK` **last** because it encodes *causal priority for a
single fit*: when two classifiers describe the same series, the earliest cause wins.
Reducing across **candidates** with that same ladder inverts the answer -- it reports a
disaster wherever the harder candidate struggled, when **a point at which any candidate
succeeded is a point that succeeded.**

So `/status/point_outcome` is defined separately (Phase 2a Task 9): **`OK` if any candidate is
`OK`, otherwise `merge_outcomes` over the model axis**, which reuses the declared ladder for
the only part that needs one. The OK-wins half is load-bearing and is what the mutation test
pins.

### A constraint justified by "otherwise the test is vacuous" belongs on the test, never on the product

> **The tell is a refusal whose stated reason is about assertions rather than about data.**

Worked instance, Phase 2a Task 8: `create_store` refused fewer than two candidates and fewer
than two criteria, on the ground that a length-1 axis makes every assertion over it pass. That
is **true of tests and false of the format** -- fitting one candidate under one criterion is
coherent, and `delta_ic = 0` with `weight = 1` are the correct answers there. It was a
**fixture rule enforced against users**, and it refused a legitimate single-candidate run. The
fix is to relax the product and assert the width **of the suite's own fixture**.

**And how it was found is the argument for the gate.** The full sweep caught it, together with
a second copy of the outcome code table in another module -- **two defects the task's own
tests could not see.** `pixi run test-fast` would have shipped both.

### The other standing rules

- **Oracles must not share a derivation path** — see (j).
- **A QUANTITY ASSUMED TO CANCEL IN A RATIO MUST BE MEASURED TO CANCEL**, because the
  assumption is precisely what a ratio cannot reveal. This is the cancellation rule (a)
  applied to a benchmark rather than to a criterion, and it has now failed twice: the P3
  iteration fixture (`mean_iterations` was assumed common to both paths — it was, but the
  *sample* it averaged over had silently narrowed), and the synthetic time axis (open
  question 14, where `unique_dt = 1` against a real axis's 6 is assumed to affect both paths
  equally). **Both times the assumption was reasonable and neither was checked.** The
  measurement is cheap: vary the quantity and confirm the ratio does not move.
- **A DEPENDENCY REACHED FOR BY ANOTHER LIBRARY IS INVISIBLE TO ANY STATIC IMPORT SCAN.**
  `tests/test_packaging.py` compares what `src/` imports against what the wheel declares, so
  it guards "imported but undeclared" and cannot see "needed but never imported here" —
  `cftime`, which xarray reaches for to decode any non-standard calendar, is the worked case.
  **The guard has a stated hole rather than an unknown one**, and such dependencies are
  declared by hand with a comment saying why.
- **A MEASUREMENT'S SUBJECT IS A PRECONDITION, AND THE SPREAD ACROSS SUBJECTS IS NOT SMALL.**
  *"The divisor ratio is 2.3×"* without naming the array is the same defect as a `tile_side`
  without its backend. Measured, Phase 2b Task 2: on `noise/theta` (float32 × `P_total`) it is
  **2.3×**; on `warmstart/theta_unconstrained` (float64, the **same** `P_total`) it is **4.57×**.
  One dtype apart, twice as bad, and the published note had picked the representative one.
  **Measure the worst case and say which it is**, or the number describes a case nobody
  operates at.
  > **AND A BAND ASSERTION THAT FAILS FOR A CORRECT REASON MEANS THE POPULATION IS NOT
  > HOMOGENEOUS. PARTITION IT — NEVER WIDEN THE BAND.** Seven of eighteen store arrays are
  > narrow enough that a whole shard cannot reach the chunk target at all (`point_outcome` is one
  > byte per cell), so one chunk per shard is the **right** answer there and not a fallback. A
  > band held over all eighteen fails on those seven; widening it to accommodate them would
  > destroy the check for the eleven it exists for.
- **A STABLE MACHINE MEASUREMENT MAY REACH A STORE; AN AMBIENT ONE MAY NOT.**
  > **The test is one question: does re-running on the same machine reproduce it?** Total RAM
  > yes, availability no, the process floor no.

  This generalizes Phase 2b Task 1's (a5) instance rather than restating it. A determinism claim
  about a store's bytes and a fresh measurement of the *process* are claims about different
  subjects, so the question to ask of any new value on its way into provenance is whether the
  machine answers it the same way twice.

  **And the floor shows the middle case, which is why the rule is about reproducibility rather
  than about banning measurements.** It is ambient by this test and it is **kept** in provenance,
  because Task 6 reads it — so it is **excluded by name from the byte-identity comparison**
  instead of being kept out of the store. The pairing is the whole rule: *record it, and name it
  in the exclusion set*, never *drop it from the comparison wholesale* and never *quietly remove
  it from the store*.

  > **THE PAIR IMPLIES A THIRD CATEGORY: a measurement that is ambient AND unread is not
  > provenance at all — it is a log line.** Available RAM qualifies twice over, so Phase 2b
  > Task 3 reports it and stores nothing. The question *"what reads this?"* is the second half
  > of the test and it is cheaper than the first.

- **A WARNING THAT ALWAYS FIRES IS EQUIVALENT TO NO WARNING**, and it is the same failure as a
  metric whose neutral value is its failure value (below): the signal and its absence become
  indistinguishable to the reader, so the guard is destroyed by the condition it was meant to
  report. **A default whose warning condition is met on an idle machine is therefore not a
  default**, which is what decided `memory.DEFAULT_BUDGET_FRACTION` at 0.25 rather than 0.5 —
  0.5 exceeds every availability reading ever recorded on this box. **Check a new threshold
  against the measurements it will actually see before choosing it**, or the warning ships
  already worthless.
- **A recorded measurement carries its measurement date AND ITS PRECONDITIONS**, because a
  quoted figure drifts and a stale one reads exactly like a fresh one — and a figure quoted
  without the conditions that produced it is not a measurement, it is a number. **Three
  instances, one family:** `pixi.lock` was quoted at 645 KB, then 630 KB, and measured
  635.6 KB when Phase 2a Task 0 re-checked it; the `tile_side` of 171 survived in notes after
  the engines were fixed; and `tile_side` **338 / 186** is quoted in design doc §13.4, the 2a
  plan and `PROGRESS.md` with **no backend attached**, while the compiled path gives
  **361 / 189** and a 3.65× area ratio against 3.30× (measured 2026-08-12). `PROGRESS.md` also
  carried 693 and 692 as the test count twelve lines apart, both undated. **Re-check the
  number, never the note** — date it, and state what it is a measurement *of*. **A
  `tile_side` without its backend is not a number**, and an A:B ratio without its harness, B
  and thread count is the same defect one subsystem over (P4).

  > **AND THE SHARPEST FORM, PROMOTED AT PHASE 2b TASK 9: TWO MEASUREMENTS OF THE SAME NAMED
  > QUANTITY ARE NOT COMPARABLE UNLESS THEY SHARE A RECORDED PRECONDITION SET.** A difference
  > between them is **not a change in the quantity** — it is **undecomposed** until the
  > preconditions match. **Withdraw the inference, not the reading.**
  >
  > Worked instance, and it is the whole reason the clause is worded that way. `measure_floor`
  > takes a `data_uri`, so the process floor is **input-dependent by construction**; Task 7
  > pinned **228.2 MB** and Task 8 measured **232.00 ± 0.468 over ten runs**, and neither
  > recorded which input was open. The difference was written down as *"a 4.4 MB level shift,
  > not scatter"* — a claim about the quantity, drawn from two numbers with no common
  > precondition. Measured 2026-08-17 across three fixtures, the input's own contribution is
  > **1.28 MB**, eleven times the within-fixture span: real, and not the effect being explained.
  >
  > **THE READING SURVIVES, THE INFERENCE DOES NOT, AND THAT ORDER IS THE DISCIPLINE.** Ten runs
  > at σ = 0.468 is not scatter around 228.6, so **232.00 stands and something unrecorded
  > explains it**. Refusing to withdraw a measurement you *cannot* explain is harder than
  > refusing to withdraw one you can — the tempting move is to call the unexplained reading an
  > outlier, which converts a missing precondition into a discarded fact.
  >
  > **AND THE CONSTANT ATTRACTING THE CORRECTION IS ITSELF A SIGNAL.** This is the **second**
  > `WORKED_FLOOR` correction refused on measurement: the first was the k_β = 4 oracle at
  > Task 7, where the "fix" changed the number that was already right. A constant that keeps
  > attracting corrections which do not survive checking is one whose **preconditions are
  > under-recorded**, not one that keeps being wrong. Fix the recording.
  >
  > **AND THE RULE APPLIES TO BOUNDS EXACTLY AS IT APPLIES TO VALUES, WHICH IS WHERE IT KEEPS
  > BEING FORGOTTEN.** A bound reads as a *property of the phenomenon* — "at most a megabyte",
  > "no more than 152 B/series" — where a value visibly belongs to a run. **It does not. A bound
  > measured at one fixture is a bound at that fixture**, and quoting it without its fixture
  > converts a local observation into a general guarantee, which is worse than doing the same to
  > a value because downstream reasoning is built on the guarantee rather than on the number.
  >
  > **TWO INSTANCES, BOTH CORRECTED BY THE NEXT TASK'S MEASUREMENT, 2026-08-17 TO 2026-08-19:**
  >
  > | the bound | where it came from | measured later |
  > |---|---|---|
  > | Task 8i: *"a watermark degrades by ~1 MB where a working set degrades by ~135"*, so peak-based criteria survive | one constructed known-bad, side 48, masked, one fixture | **−2.74 MB at 1048 s and −8.32 MB at 2060 s**, no constructed pressure. Right in kind, **low in scale by 8×** |
  > | Task 8a: *"transient ≤ 152 B/series"*, which excluded the headroom explanation as **sufficient** | one run's `peak − current_end` at side 96, on a ladder point since shown to be contaminated | **905.9 B/series** at the duration-controlled fixture — **6× the bound**, and 37.6% of the peak against a shipped 15% headroom. **The exclusion is withdrawn** |
  >
  > **THAT IS THE THIRD AND FOURTH CORRECTION OF A PROMOTED RULE BY ITS OWN SUCCESSOR TASK IN FOUR
  > DAYS** — after the "~33%" implied headroom (51.29%) and 8a's decay rule (an interaction, not a
  > main effect). **The pattern is not that the rules were careless; it is that a bound derived
  > from one fixture is a hypothesis with a citation, and the register is worth keeping precisely
  > because the next task measures against it rather than around it.** The failure mode to fear is
  > a rule nobody re-measures, and it is invisible exactly because nothing contradicts it.
- **ONE LIBRARY REFUSES LOUDLY, THE OTHER LIES QUIETLY — AND ONLY THE SECOND IS DANGEROUS.**
  The whole argument for **observing** rather than asserting, delivered by measurement rather
  than by reasoning. Requesting 1000 threads on a 4-core box (Phase 2a Task 5, 2026-08-12):
  `numba.set_num_threads(1000)` raises `ValueError: The number of threads must be between 1 and
  4`, while `threadpool_limits(limits=1000)` leaves **OpenBLAS reporting 128** — its build-time
  `NUM_THREADS` — and OpenMP reporting 1000. The loud refusal costs a staged error message; the
  quiet clamp writes a number into provenance that was never true, and the determinism
  guarantee rests on it.
  **This is the answer to anyone who later proposes dropping the observation because "we set
  the environment variable".** A request is not a result, and the library that ignores you is
  precisely the one that will not say so.
- **A METRIC WHOSE NEUTRAL VALUE IS ALSO ITS FAILURE VALUE MUST FAIL LOUDLY, NEVER RETURN THE
  VALUE.** Otherwise **the guard is removed by exactly the condition it exists to detect** —
  the metric reports "nothing to see" for an input it could not measure at all, and the two are
  indistinguishable downstream.
  Worked instance (Phase 2a Task 6): read amplification is 1.0 for a perfectly chunk-aligned
  tile, and a store that declares no chunking would also read 1.0 if the shape were used as a
  fallback. **That metric replaced the dask graph-chunk cap as the only guard watching for a
  pathological input**, so the fallback does not weaken the guard, it deletes it. The store is
  refused instead.
  **Two companions from the same measurement.** *Both sides of a ratio must be in the same
  unit*: the store's bytes are compressed and a tile's are not, which gave **4.05 where the
  truth is 4**, and on a compressible variable the same ratio falls **below 1** — a value below
  the neutral one is the tell that the units are crossed. And *a counting oracle over the set of
  chunks fetched beats measuring bytes*, because it shares no construction with the arithmetic
  it checks (j).
- **Heterogeneous batches by default.** A homogeneous batch cannot expose a
  batch-granularity defect. Task 13's only real finding came from the one mutation that
  survived because every fixture had `B = 1`. Task 17's utilization measurement uses a
  heterogeneous sample because a homogeneous one reports 1.0 by construction — the number
  the measurement exists to challenge.
- **TWO CHANGES THAT COULD EACH EXPLAIN A WRONG RESULT MUST LAND IN SEPARATE COMMITS, OR
  NEITHER CAN BE BLAMED. Attribution is a property of the sequence, not of the diff.**
  Three instances of one principle: the golden reversal is a **chain, one hop per allowlist
  change**, because two hops reversed together give two ways to be wrong that cancel; the
  271 → 307 s sweep step was recorded as **undecomposed** rather than explained, because two
  changes had landed together; and Phase 2b splits the formula correction, the floor
  measurement and the arithmetic that joins them into three tasks — the first falsifiable
  with no measurement, the second a measurement with no consumer, the third the join — so a
  wrong number has exactly one new input.
- **Enumerate exits, never count them** — see (c).
- **A CLAMP, FLOOR OR EPSILON GUARD ABOVE THE DIAGNOSTIC LIMIT OF WHAT IT GUARDS IS A
  FABRICATION MACHINE.** It converts a reportable fact into a plausible number *and* makes
  the rung that would have reported it unreachable, so no test can see the loss.
  `sqrt(maximum(var, 1e-12))` gives `sigma = 1e-6` against sigma's own `1e-8` limit, so the
  diagnostic clip never fires and `InitRung.CLIPPED` becomes dead code. A tree-wide sweep
  (2026-08-06) found no further instances.
- **Prefer analytic endpoints to tolerance bands.** And know which identities survive
  float64: `white(3) + white(4) == white(5)` is bit-exact (integers at lag 0, zeros
  elsewhere); the Matérn version at a shared ρ is `9e + 16e` against `25e` and misses by an
  ulp. Exact in ℝ ≠ exact in float64, and **the exact case is what makes the
  over-generalization look safe.**
- **`(B, N)` is the only code path.** `B = 1` is a shape, never a separate implementation.
- **Failed series carry NaN, never −inf**, in anything destined for the store. `−inf` is a
  finite-looking sentinel that survives some consumers' checks; it is the optimizer's
  internal barrier value only.

---

## 3. The number every Phase 2 tile calculation inherits

**`tile_side` IS `batch.tiling.PUBLISHED_TILE_SIDE`, AND IT HAS BEEN WRONG FOUR TIMES.** 171 for the whole of Phase 1;
338 from 2026-08-10 (P2); 347 after Phase 2b Task 0 corrected the per-series formula; and **272
since Phase 2b Task 2 stopped treating the budget as the block.** Every superseded figure is
struck rather than deleted, so a reader meeting one in an old note can date it: ~~171~~ (while
`_augment` materialized `[y | X]`), ~~338~~ and ~~339~~ (the model and the resident figure, both
charging one live solver working set to every series), ~~347~~ (the corrected per-series cost
divided into the **whole** budget).

**THE CURRENT NUMBER AND ITS PRECONDITIONS LIVE IN CODE, AND THIS DOCUMENT NO LONGER CARRIES A
COPY OF EITHER** — `batch.tiling.PUBLISHED_TILE_SIDE`, since Phase 2b Task 9. The table that
stood here (budget, floor, headroom, base, model, answer) is now that record's fields, and
`tests/test_tiling.py` **recomputes the answer from `tile_side_for`** and **binds the
precondition list against its signature**. That is exit criterion 16, and it is the only repair
that survives the next correction: this table was a copy, every copy of this number has gone
stale, and a copy cannot be tested.

**AND THE PER-SERIES COST IS UNDER DISPUTE BY 1.86× — the record says so in the same sentence
that states the value**, with the live readings spanning 192 to 272 and Phase 2b Task 8a owning
the measurement that separates them. When 8a and 8b resolve it, the `dispute` field is deleted
in the edit that moves the value, because a test recomputes every figure in it.

**THE FLOOR IS THE ONLY PRECONDITION THAT IS A MEASUREMENT**, it is measured **with the input
open**, and — measured 2026-08-17 — **it depends on which input**: 228.61 MB opening a
60 × 160 × 160 store against 229.89 MB opening a 630 × 64 × 64 one, 1.28 MB apart against a
0.11 MB within-fixture span, at 0.0000 ms/s of full stall. So a pinned floor needs its **input**
recorded beside it, exactly as a published side needs its floor; `PublishedTileSide.floor_basis`
is where that goes.

**AND THE SIDE DOES NOT CARRY A BACKEND.** The per-series cost is the data tile plus the output
slots, neither of which knows which engine is running, so the two published pairs
(~~338/186~~ against ~~361/189~~) differed **only** because of the per-series solver charge.
The placement moves a constant.

The step-by-step correction — which term moved and by how much — is in `PROGRESS.md`'s
**What 2b's first tasks inherit** section and is not repeated here.

**What the defect was, kept because the mechanism is the transferable part.**
`KalmanEngine._augment` ended in `np.concatenate([y[:, :, None], x], axis=2)`, materializing
a `(B, N, 1+k_β)` float64 array — **25 200 B/series at N=630**, nearly three times §9.4's
entire per-series total, and it **did not vanish when the design was shared**, the case
§9.4 treats as free. The `np.broadcast_to` on the line above **is a view and allocates
nothing**, which is exactly why the copy read as free on a code read. The accumulator only
ever needed one row, so both engines now index the observation out of `y` and the design
columns out of a `(1, N, k)` or `(B, N, k)` block, per timestep. **§9.4 was right and the
engines were wrong**; the fix made the document true rather than replacing it.

**The measurement, because the fix is only worth what it measures.** The slope of resident
RSS against B, in a fresh process, sampled on a thread during the workload, went
**43 392 → 8 471 B/series** — a fall of 34 921, *more than the block itself*, because the
per-step temporaries at peak scaled with it. Against the arithmetic floor of 6 382 B/series
that is a ratio of **1.33**, inside the ~1.5× below.

**And the standing check that produced that number:** *does the memory formula describe the
code, or a model of the code?* §9.4 was wrong twice in ways three places agreed on.
**Verify against measured resident bytes** — the slope of RSS against B, in a fresh process,
sampled during the workload. It was 5.0× before the fix and nothing in the suite said so
until the measurement existed.

**THE CHECK IS A TWO-SIDED BAND, CORRECTED 2026-08-14.** It was stated as *"treat any factor
above ~1.5× as a missing term"*, and **that one-sided form would have passed all three of
Phase 2b's formula defects.** A measured slope **materially below** the formula is equally a
finding: the formula charges for something the code does not hold, and the excess capacity
hides whatever else is wrong. Read a ratio outside the band in **either** direction as a term
that is wrong, never as measurement noise — and per (a), check the **terms** rather than the
sum, because two errors of opposite sign land the total inside the band.

**And per (j2), check the instrument before checking the ratio.** The 1.33 that cleared this
band in 2026-08-10 was measured on a batched evaluation against a formula for a per-series
loop; a ratio computed from the wrong workload is not evidence in either direction.

---

## 4. Open questions 5–8

| # | question | what would close it |
|---|---|---|
| **5** | **64-core box RAM is unknown.** The stage-1 gate was closed without that machine, but its RAM is needed before any tile-sizing run there | run `free -g` on it and record the figure |
| **6** | **Roofline validation across machines.** One data point cannot validate a two-parameter fit; the mini PC supplies the model's first point and tests nothing. **Blocks the `cloudify` cost projection (§15.5)** — projecting spend on an unvalidated roofline is projecting a guess | a second machine's roofline pair plus its measured canonical filter pass, checked against the prediction |
| **7** | **Path B at high thread occupancy.** Measured at 1 and 4 threads on a 4-core box. `prange` over series at 64 threads may hit false sharing on the per-series `accum` block, or saturate the controller elsewhere | `bench/spike.py --threads 1 --threads 4 --threads 64` on the 64-core box |
| **8** | **`numba` and `celerite2` on arm64.** `celerite2` has no `osx-arm64` conda-forge build and is pinned to `[target.linux-64.dependencies]`; `numba` on arm64 has never been run here | the suite plus `bench/spike.py` on the MacBook |

Questions 1–4 and 9 are in `PROGRESS.md`. **9 (`HESSIAN_COND_LIMIT`) was closed on
2026-08-10**, before Phase 2 planning as it required: the limit is now the derived
`eps^(-1/2) = 6.711e7`, and §4.8's two halves are on the same footing.

---

## 5. Fixture facts a fresh session will otherwise get wrong

Every one of these was discovered by building a fixture that could not fail.

- **`DIAGNOSTIC_LIMIT` in a DESIGNED fit is reached through `sigma`'s lower limit (1e-8),
  not `rho`'s upper one (1e6).** A slow cosine does not do it — a design carrying constant,
  trend, offset and rate change absorbs it and leaves an ordinary residual; measured, that
  series comes back `OK`. What works is a record whose amplitude is ~1e-11.
- **`BIC_NEFF`'s looser penalty does not show up in `ic_best`.** The winner is normally the
  white candidate, whose `n_eff` equals `n` exactly. The difference lives on the
  *correlated* candidate's ΔIC — measured 7.823 → 7.677 at `n_eff = 194.25` against `n = 200`.
- **Under white noise GLS is OLS, so `n_eff_trend` is `n` for every design column.** Any
  test meaning to pin *which* column is the trend must use a **correlated** candidate.
- **`ILL_CONDITIONED_X` is theta-dependent** — it is the *whitened* Gram that is ill
  conditioned, not `X_r`. Across five seeds at one mask, `design.condition_number` is
  2.68e4 every time while the outcome is `ill_conditioned_x` for two and `ok` for three.
  Pin the seed; never assert `design.condition_number` as a proxy.
- **`cond(X_w)` is invariant under a uniform rescale of Σ**, so you cannot make a design
  ill-conditioned by shrinking σ. Analytic, not empirical. What does move it is giving the
  design more post-breakpoint degrees of freedom than the post-breakpoint samples carry.
- **The time axis is decimal years.** In seconds since 1970 the same 20-year monthly design
  goes from `cond(X) = 3.4e1` to `3.3e32` and rank 7/7 to 2/7.
- **NUMPY SCALAR TYPES ARE NOT INTERCHANGEABLE AT A SERIALIZATION BOUNDARY, AND A FIXTURE'S
  DTYPE IS A HIDDEN PARAMETER.** `canonical_json` **accepts `np.float64` and refuses
  `np.int64`**, because the first subclasses `float` and the second subclasses nothing JSON
  knows; `np.ndarray` is refused too. So `list(array)` works on a float coordinate and raises
  on an integer one — and index coordinates are routinely integers. **A fingerprint built that
  way passes every test written on a float grid and fails on the first real store.**
  `.tolist()` converts uniformly and reads identically to `list()`.
  **Swept 2026-08-12 for other callers**: `hashing.digest` receives config payloads whose
  numbers come from `tomllib`/pydantic as Python scalars, and `ContractReport` already casts
  every count with `int(...)` and every year with `float(...)` — those casts are load-bearing,
  not cosmetic. `terms.py` serializes with its own `json.dumps` and never reaches here.
  `tests/test_hashing.py` pins the asymmetry so it cannot be "tidied" into symmetry.
- **A TYPE DECLARED WIDER THAN CURRENTLY NEEDED IS THE COUNTER-EXAMPLE WORTH KEEPING.**
  `Config.fit_hash()` was declared `str | None` at Task 1, when it could never return None.
  Two tasks later `geometry_hash` made the None case real, and **no caller needed revisiting**
  — where a `str` return would have had every caller written against it and then rewritten at
  exactly the moment the None case started happening. Widening later is the expensive order.
- **A REAL MONTHLY AXIS HAS SEVERAL DISTINCT TIMESTEPS, NOT ONE.** Calendar months are 28–31
  days, so 50 years of month-start timestamps give `unique_dt = 6` (mid-month 8, daily 2).
  **Only a synthetic `2000 + arange(n)/12` gives 1**, and that is the shape every synthetic
  fixture and the spike harness use — so any claim resting on "F and Q are built once per
  series per iteration" is a claim about the fixture, not about the workload.
- **A quadratic cannot test a step rule**, and **a fixture above a floor cannot test the
  floor.**
- **NO SHIPPED FAMILY DECLARES A `fixed=True` PARAMETER**, so *declared* and *free* parameter
  counts are equal on every fixture built from the registry. **Any test of that distinction
  needs a constructed spec** — measured at Task 7, where replacing the free count with
  `len(term.params)` failed exactly one test and it was the constructed one. Same shape as
  `machine.choose_core_count` (no SMT on this host) and `library_table` (one OpenBLAS here):
  **the environment cannot express the defect, so the fixture must.**
- **HETEROGENEITY MUST COME FROM A PARAMETER THE LIKELIHOOD IS NOT EQUIVARIANT IN** —
  timescale, mixing ratio, mask pattern, series length. **Varying an equivariant parameter
  produces a fixture that looks diverse and is identical.** Amplitude is the worked case:
  a Gaussian log-likelihood is equivariant in it, so `* logspace(-1, 1, k)` contributes
  nothing. Measured on the spike's iteration sample, one realization at four amplitudes:
  `n_iter = [28, 28, 28, 28]`, utilization **exactly 1.0** — the number that fixture's own
  docstring said the spread existed to challenge. Ask which of a fixture's varying
  quantities the objective is *invariant* under, before writing it.
- **`fit` costs ~5.4 s per series** through the per-series scipy loop, linear in B. Anything
  wanting tile-scale behaviour must use a batched *evaluation*, not a fit.
- **`ru_maxrss` is inherited across `fork()`/`exec()` and updated lazily.** A child spawned
  from a 400 MiB parent reports the parent's peak byte-for-byte; and the watermark can
  *trail* live RSS (470.8 MB against a live 471.3 MB read an instant earlier).
- **`numba` pins `numpy<2.5`**, so installing it downgraded numpy 2.5.1 → 2.4.6, and 2.4's
  type stubs infer `floating[Any]` where 2.5's infer `float64`. `mypy` then reports errors
  in files nobody touched. An environment fact, not a regression.

---

## 6. What Phase 2 inherits structurally

- **The three-hash separation, awaiting a store.** `fit_hash ⊂ compat_hash ⊂ run_hash` is
  built, tested, and pinned by golden constants. **The contract Phase 2 must honour:**
  §12.8 treats a `compat_hash` match with a `fit_hash` match as licence to **recompute the
  derived arrays from stored primitives without refitting**. That is implementable because
  `rank_candidates` takes *only* the stored primitives — never a spec, a design matrix or
  the data — and `test_hashing.py` pins exactly that. **If any future change makes
  `rank_candidates` need the data, §12.8 becomes unimplementable and the three-hash split
  buys nothing.** Not yet tested: an actual resume, and "a `fit_hash` mismatch is refused",
  both of which need the store.
- **The batched-equals-solo invariant.** `test_batched_results_equal_solo_results_series_by_series`
  is the standing guard for the entire "(B, N) is the only code path" class. Every new
  batched routine must keep it green. `np.linalg.cholesky` raises for the *whole stack* if
  one member fails, so validity is classified with the non-raising batched `slogdet` first
  and only the valid subset is factorized.
- **The label-switching / hysteresis confound (§11.2).** Two same-kind terms with a free
  timescale are exchangeable across the whole searched space; canonical ordering at result
  packing fixes the reporting **within one fit and nothing between fits**. Across grid points
  that produces large parameter disagreement with near-zero selection, objective and
  signed-trend disagreement — **a signature the warm-start hysteresis audit would read as
  benign hysteresis when it is non-identifiability.** Two consequences are recorded in
  §11.2: report per-term parameter disagreement separately from the aggregate, and decide
  whether the audit refuses lint-flagged candidate sets outright or reports the two strata
  apart. **Do not measure hysteresis on a lint-flagged candidate set and quote the number as
  hysteresis.**
- **The identifiability lint is the cheap pre-check for that confound.** `core.lint` runs on
  a `ProcessSpec` before any data and flags exactly those compositions.
- **Path A is the permanent correctness reference.** `engines/kalman.py` plus
  `optimize.optimize_series`. It is not deprecated and must not be deleted; every MVN
  oracle and the path-B agreement test are pinned against it. ~~The stage-1 verdict carries
  one condition: re-measure after `_augment` is fixed~~ — **discharged 2026-08-10.** The
  falsifier is not met in any cell or any harness, so Task 19 stays deleted.
  ~~**But the two harnesses disagree about whether the ratio moved**~~ — **CLOSED by P4,
  2026-08-10: there was no harness effect.** The 0.57 spread (spike 3.84, sweep 3.27) is
  inside a single harness's own between-process scatter, measured at **±0.4** at that cell
  over twenty-nine runs, against the **±0.15** the verdict had assumed from a sample of two.
  **The scatter lives between allocations, which is the one place `repeats` cannot look**:
  `_time_pass` takes the best of N passes over *one* allocation (spread 0.13) and publishes
  it as if it were a fresh one (spread 0.82). Path A is ~16% slower on freshly allocated
  inputs, path B ~4%. The two harnesses are now one — `--dim` and `--gaps` are filters, so
  the batch sweep is a flag combination — and every cell reports a median with its min and
  max. **Any restated margin must name its harness invocation, B, thread count and
  cell-repeat count.** What was already resolved and still is: **path B's per-pass cost fell
  ~20%**, because it had been reading a per-series private copy of the shared design, and
  **path A did not measurably move**, which contradicts the condition's stated reasoning.
  See [`spike-stage1-verdict.md`](spike-stage1-verdict.md).
- **A CORRECT CONCLUSION REACHED THROUGH A WRONG MECHANISM IS A FINDING IN ITS OWN RIGHT.**
  The verdict predicted the `_augment` fix would help path A most; path B is what gained.
  The conclusion survived, the reasoning did not, and **the reasoning is what the next
  prediction is built on** — a note that records only outcomes gives a later reader no way
  to know its mechanism failed.
- **The path-B agreement test cannot carry a change made to both engines.** It compares two
  implementations of the same recursion, so anything both do identically is invisible to
  it — the cancellation rule at the level of an engine. What pins the values is
  `test_kalman.py`'s MVN oracle, which builds the covariance explicitly. For the streaming
  change the available check was stronger than either: **bit-identical** output against the
  pre-fix modules loaded out of git, across both engines and all three design regimes.
- **The benchmark harness is a one-command run and must stay that way**, so a later session
  can produce `box64.json` or `macbook.json` without reconstructing anything.
