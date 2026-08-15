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

The check generalizes past hashes to every gate made of a name — a completion bitmap, a
calibration cache key, a warm-start cache key. **`machine_fingerprint` is the live example
of a field whose classification changes with its consumer**: self-reported at its own
boundary, harmless while it reaches `run_hash` alone (provenance, never a gate), and an
identity the moment the calibration cache key reads it.

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

#### AND THE CONFLICT CAN BE WITH A CRITERION THAT IS ALREADY MET

> **A MEASUREMENT OF THE PROCESS CANNOT BE PART OF A BYTE-IDENTITY CLAIM ABOUT THE OUTPUT.**
> They are claims about different subjects, and a store that records both is a store whose
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

The repair keeps the criterion's force: files compared byte for byte, attrs compared key by key
against a **named** exclusion set, and **the excluded key asserted present in both stores**, so
"excluded" cannot decay into "absent".

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

### (b) Batch vs series

Is any per-series fact computed at batch level, or any per-candidate fact stored per point?
`moment_init`'s rung is per series; a batch-wide rung is right only when the whole batch
falls the same way.

### (c) Exit paths

Enumerate every `return` and every `raise`; does each pass through the outcome ladder?
**Enumerate, never assert a count** — an asserted count is how two bypassed exits survived
Task 8, and how a report claimed "exactly one early return" where there were four.

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

### (d) Grep for the vocabulary the task requires

"mask", "n_used", "realized" appearing **zero** times in a 234-line brief was detectable in
one command. Task 15's brief never mentioned `fixed`, `state_dim` or `white + white`.

### (e) Do the tests bite?

Delete the guard each one protects and confirm it fails. Two of Task 9's tests replaced
assertions that could not fail at all.

**A surviving mutation has five causes and they call for different responses.** Diagnose
which before acting; four of the five are not defects, and treating them as coverage gaps
leads to deleting a real guard.

| cause | tell | response |
|---|---|---|
| **No test protects the guard** | removing the guard changes nothing observable anywhere | act on it — write the test |
| **The mutated line is unreachable** because a guard *above* it fires first | removing that upper guard makes the mutation bite | defence in depth working; write the compound mutation |
| **TWO INDEPENDENT GUARDS, EITHER SUFFICIENT** | mutating **either alone** does not bite; mutating **both at once** does | the code is doubly protected and the test is fine |
| **GUARDED ONE LAYER UP** | the mutation is semantically real and the test is sound, but an **earlier layer already normalized the input**, so the mutated code cannot see the difference | **rewrite the assertion** — see below |
| **THE MUTATION IS NOT A DEFECT** | the mutated code is **semantically identical** to the original on every reachable input | **correct the mutation, not the test** — see below |

**THE FIFTH SAYS NOTHING ABOUT THE TEST AT ALL, AND THAT IS WHY IT IS LISTED.** A survivor is
evidence about a test only once the mutation is known to be a real behaviour change, and that
is a step people skip because writing the mutation feels like the check. **Verify the mutated
code is semantically different before concluding anything.**

Worked instance (Phase 2a Task 4): `if observed is None: return` mutated to
`if observed is None: observed = {}` left every test green — correctly, because an empty table
has no offenders, so the two are the same function. The reachable defect is deleting the guard
outright, so `observed.items()` runs against `None`; that mutation bites. A test written to
catch the first version would have been a test of an equivalence.

**THE FOURTH IS THE ONLY ONE OF THE FOUR WHERE THE CORRECT RESPONSE IS TO CHANGE THE TEST.**
The other three end in "leave it" or "write a compound mutation". This one means the test was
pointed at a defect that is **not reachable**, so the question is not whether to accept the
survivor — it is **what the mutation should have been**.

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

### (i) Can the fixture fail at all?

Ask what property of the fixture makes the defect visible; if the answer is "none", the
fixture is wrong before the assertion is. A **quadratic cannot test a step rule** (third
derivative zero). A fixture at `n_eff = 12` **cannot test a floor at 2.0**. And **a fixture of
zeros cannot test a read**: zarr does not write a chunk equal to the fill value, so a
zero-filled store serves every read from the fill value — measured, **0 bytes and 0 keys** for a
read that returned the right number of correct-looking values (Phase 2a Task 6).

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

### (j) Does the oracle share a derivation path with the thing it checks?

An independent oracle means a **different construction**, not different constants.

| subject | the bad "oracle" | why it is not one |
|---|---|---|
| `hessian_at_optimum` | `tests/oracles.fd_hessian` | the same second-difference stencil at a different step — it measured the step choice and nothing else |
| `theta_err` (delta method) | `theta_err / theta` | the same quantity rescaled by the very Jacobian under test |

The tell: if the reference is not at least ~100× more accurate than the subject, it is
probably the same algorithm. Nested Richardson qualifies; a wider step does not.

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

**`tile_side` is 347, and it has now been wrong three times.** It was 171 for the whole of
Phase 1, 338 from 2026-08-10 (P2) to 2026-08-14, and **347 since Phase 2b Task 0**.

| figure | what it is | use it for |
|---|---|---|
| **347** (8 274 B/series) | what the code **actually holds**, one live solver working set excluded because `fit` runs one series at a time. `memory.resident_bytes_per_series` | **every Phase 2 tile calculation** |
| ~~339~~ (8 682 B/series) | §9.4's **model** — and the model was the batched trust-region §8.3 specified and Task 19 deleted. `memory.bytes_per_series`, **deleted** | **nothing** |
| ~~338~~ (8 722 B/series) | the model plus a per-series charge for the engine's reused row, with the solver state still per series | **nothing after 2026-08-14** |
| ~~171~~ (33 882 B/series) | what it held while `_augment` materialized `[y \| X]` | **nothing. Any Phase 1 note quoting 171 predates the fix** |

At a **10⁹ B** budget, shared X, d=3, k_β=4, p_max=4, M=12, N=630. Per-point X gives **187**.
**The unit is not decoration**: `run.py` converts `memory_budget_gb` with `1024**3`, which gives
360 at the same nominal budget, and resolving that is Phase 2b Tasks 2 and 3.

**AND THE SIDE NO LONGER CARRIES A BACKEND.** ~~Path B's resident figure is 8 B/series above
its own model rather than 40~~ — the per-series cost is the data tile plus the output slots,
neither of which knows which engine is running, so the two published pairs (338/186 against
361/189) differed **only** because of the per-series solver charge. The placement moves a
constant. **A `tile_side` still needs its preconditions — budget and unit, N, M, k_β, p_max and
the regressor regime — it just does not need an engine.**

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
