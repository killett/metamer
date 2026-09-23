# Phase 2f — the report computed from the store

**Design doc §14.2 only.** The computation and a minimal entry point,
`python -m metamer.report <store>`; the `metamer report` subcommand is Phase 5's, and §14.2
resolved that split on 2026-09-12 by the same measure/print rule §14.1 was split on. This plan
implements §14.2; it re-argues none of it, and where it departs from §14.2 it says so at the
departure and amends the section.

## What 2f IS, and the property everything else serves

**The report is computed from the stored status arrays, not from carried counters.** That is not a
style preference: §14.2 names three consequences that follow from it and are lost without it —
resumption correctness is free (a resumed run's report covers the whole run because it reads the
whole store), the report is independently testable, and it is **usable on someone else's store**.

The third is the sharpest and it constrains this sub-phase everywhere. A user with a store and no
config must be able to run the report. So:

- **The report never mutates its subject.** §14.2's own closing line asks for the scalar summary
  in root attrs, and that requirement loses to the one the section leads with — see the amendments.
- **The report's import graph excludes the fit path**, so a reader of a store does not need the
  machinery that produced it.
- **Every number says where it came from**, because a report read by someone who did not run the
  run cannot be interpreted by knowing what was typed.

## Why this plan has no code fences

Same reason as 2a through 2e. A fenced block is read as the implementation and stops being
reviewed as a specification. **Interfaces appear as signatures only where a later task binds
against an earlier one.**

## What 2f inherits, and what it does not own

**Inherited and already in the tree:** stores with `/selection/delta_ic`, `n_valid` and `selected`;
label coordinates on every group's `m` and `c`, and a `legend` with `flag_values` / `flag_meanings`
on `/status/` — so a store labels itself and the foreign-store claim is real in the bytes.
`early_abort` root attrs carrying action, threshold, policy, dropped candidates and the coarse
rates. Three subjects to count that did not exist before 2e: dropped candidates, a sixth exit code,
and a `no_evidence` verdict.

**Not 2f's:** the subcommand tree (Phase 5), `--explain` (§13.4), the two-arm audit numbers (they
are `audit_report.py`'s and already built — see amendment A2), and open question 23, which 2f gives
an instrument to without taking.

**Open question 24 is taken alongside this plan, not as a task in it — and it is IN PROGRESS, not
closed.** Three commits, not two, each provable before the next:

| # | commit | state |
|---|---|---|
| 1 | the gate reads whether anything was FITTED (D1) | **`49f3db1`, pushed, CI green** |
| 2 | `INSUFFICIENT_DATA` becomes eligible (D2) | **not written** — held on the audit-denominator decision, whose subject is recorded at [the pre-flight](../notes/phase2f-preflight.md) under *"FILED, NOT TAKEN"*. **The hold is not about D2's check, which is complete and stands**: no committed number moves, under any of the three candidate predicates. It is about whether a live instrument's denominator is repaired alongside the flip — a decision, not a measurement. |
| 3 | 2e's criterion-9 reading, corrected where it sits | **not written** |

**STATUS: TAKEN IN PART. Closer: §13.6's declared domain mask.** Not closed, and the distinction is
not bookkeeping — see D2. The flip is right about what `INSUFFICIENT_DATA` **means** and cannot fix
what it **contains**, because land is written under that member until a declared domain mask exists.
What 2f takes is the classification and the two denominators that follow from it; what remains is
un-unioning the population, which is a sub-phase (a domain mask, a config surface, a producer change
and re-validation) and not a task.

**THIS TABLE IS THE ONE PLACE THIS PLAN STATES A FACT ABOUT THE TREE, AND IT IS A STATUS LINE
RATHER THAN PROSE FOR THAT REASON.** Prose here has been wrong in the past tense **twice** — first
*"closed before this plan, taken in two commits"* while nothing was committed and the count was
three, then *"closed"* while the closer had not been built. **A status line gets edited; prose gets
re-argued**, and this paragraph is where a resuming session looks first.

---

## The decisions this sub-phase was planned on

### D1 — `no_evidence` reads whether anything was FITTED, and that is a defect OQ24's check found rather than a cost of taking OQ24

§14.1's verdict asked `rate is not None`, which is `eligible > 0` — a question about the failure-rate
**denominator**. Its subject is whether the coarse sample held a fit to judge. The two agree only
while `INSUFFICIENT_DATA` is excluded from denominators, which is §8.6's reading and which §12.5
supersedes; they disagree today on any decided skip. An all-`SCREENED_OUT` coarse sample gave every
candidate `0 / 20 = 0.0` and the verdict returned **`continue`, "no candidate failed above 90%"** —
a clean pass over a sample in which nothing was ever fitted. Reproduced red before the repair.

**`Outcome.is_fit_verdict` is the repair**, reading §12.5's non-fit grouping table, which now has
three consumers rather than a fourth statement of one rule. It is written as a **positive**
membership test over §8.6's nine fit verdicts — the opposite direction from `is_failure` and
`is_eligible`, which exclude from the whole enum — because every member added to this taxonomy
since Phase 1 has been a non-fit code, so defaulting a new member *into* the fit set is the
dangerous direction: a sample the run never fitted would read as judged.

**THE PATTERN, RECORDED AS A PATTERN AND NOT AS A THIRD ANECDOTE.** Four instances now:

| # | the gate | it read | its subject |
|---|---|---|---|
| 1 | the quiet gate (open question 22) | the host's `/proc/loadavg` | this container's CPU use |
| 2 | the stall gate | time spent waiting | memory pressure |
| 3 | §14.1's no-evidence gate | `is_eligible` | whether anything was fitted |
| 4 | the plan-review fetch, 2026-09-19 | a **cached** 404 and a **summarised** directory listing | the repository's bytes — `curl` returned HTTP 200 and 52,010 bytes on the identical URL |
| 5 | 2e's criterion-9 instrument | what one glob and one key spelling happened to walk — 8 of 16 | the committed audit numbers its claim named |

**All five coincide with their subject in the common case and diverge exactly where it matters**,
and **the tell held in every one**: a predicate naming a different quantity from its own reason
string. §14.1's said "eligible" while meaning "fitted"; the fourth said "not on main" while meaning
"not in my cache"; the fifth said *"every committed report's outcome histogram"* while meaning
*"every `outcome_counts` key in `notes/*.json`"*.

**Row 5 is why F3 is a category and not a patch to one criterion** — it is at the handoff as (c7),
with the sweep of 2a–2e's criteria that it owes.

**The fourth is why the pre-flight category is promoted**, from *never pipe a checker through a
truncating filter* to **any intermediary that can cache, summarise or truncate is not evidence;
read the bytes.** Truncation was the known form; caching is a second, and summarising a third — the
review's miss used all three at once and each agreed with the others. The category lives in the
handoff §2; the table lives at `Outcome.is_fit_verdict` and is not restated at each site. **Row 4
reaches `outcomes.py` with the next `src/` commit** — it is a docstring line and does not justify a
1:38 sweep of its own.

### D2 — `INSUFFICIENT_DATA` is eligible, and §8.6 and §12.5 were never in disagreement

**§8.6 AND §12.5 ARE INDEXED TO DIFFERENT ERAS, NOT IN CONFLICT — and reading them as competing
statements is what made a correct-looking change dangerous.** An earlier draft of this decision
resolved them by precedence: *"the design doc is authoritative on intent and §12.5 is the later,
more refined statement."* **Precedence is the wrong instrument when two statements do not
disagree.**

- **§12.5 describes what `INSUFFICIENT_DATA` MEANS**, and what it will *contain* once
  `NOT_APPLICABLE` has a producer: a series whose record is too thin to fit, eligible, because
  *"its rate is a real statement about record coverage"*.
- **§8.6 describes what it CONTAINS today**, and §8.6 is accurate: land is written
  `INSUFFICIENT_DATA`, so a rule excluding the member excludes land, which is exactly what §8.6
  says the exclusion is for.

**Both are true. So the flip is CORRECT ABOUT WHAT THE MEMBER MEANS AND WRONG ABOUT WHAT IT
CONTAINS.** Today the symbol is a **union of two populations** — genuinely thin ocean records and
land — because §12.5 itself says `NOT_APPLICABLE` is **underivable** without §13.6's declared
domain mask: nothing distinguishes land from *"every value happens to be NaN"*. **A definition
change cannot un-union them**, and that sentence is why this decision needed a second repair.

**The artifact check, run 2026-09-19 before any edit, and the set is empty.** Sixteen outcome
histograms across five committed artifacts; **zero carry `INSUFFICIENT_DATA` and zero carry
`NOT_APPLICABLE`**. Exactly one committed family carries a denominator that reaches
`Outcome.is_eligible` — `wiring-one-measured.jsonl`'s `attempted` / `both_ok_fraction`, out of
`audit_report.CandidateOutcomes` — and there `attempted == audited_points == 52` on both branches
for all three candidates, so nothing was excluded and the flip cannot move it. Every other
committed rate uses a denominator that never reads the property: the spike harnesses use
`iterations != ITERATIONS_UNSET`, five harnesses use `outcome != 8` (not `NOT_ATTEMPTED`), the
phase2d records use the raw cell count. No committed prose quotes a numeric failure rate; no store,
array or `.npy` is committed.

**What does move, stated rather than elided:** one expected value inside 2e's own criterion-13 test,
which computes `live == 9` with `is_eligible` as its denominator. Recomputed, and said so at the
test. "No committed artifact moves, one test's expected value does" is the honest form of "the set
is empty".

### D2b — the verdict's rate denominator is `fitted`, and that is correct in both eras

**MEASURED ON EXIT CRITERION 12's OWN FIXTURE, 2026-09-20**, after the flip's full sweep came back
red on it: twelve ocean points, eight land, a candidate failing **all twelve fits**.

| store | failed | eligible | **fitted** | rate over eligible | verdict |
|---|---|---|---|---|---|
| full | 12 | 20 | **12** | **0.60** | **continue** |
| cropped to ocean | 12 | 12 | **12** | **1.00** | **drop** |

Same data, two verdicts — **verbatim the defect criterion 12's docstring exists to catch**, because
the land rows are `INSUFFICIENT_DATA` and the flip put them in the denominator.

**THE REPAIR IS NOT THAT IT PRESERVES THE OLD NUMBERS.** It does — on any coarse store today
`eligible == fitted`, because `SCREENED_OUT`, `CANDIDATE_DROPPED` and `NOT_ATTEMPTED` have no
producer there — but **preserved numbers are a check on the reasoning, never its basis**, which is
the same rule that refused to let P5's estimate ride into a shipped invariant.

**The argument is that `failed / fitted` is correct in BOTH eras.** This gate asks whether a
candidate is failing the fits it **attempts**. That question has nothing to do with how much of the
box is out of domain, and it will still have nothing to do with it after §13.6 makes land
`NOT_APPLICABLE`. **A gate whose denominator is land-sensitive is broken whether or not the flip
happens; the flip only exposed it.**

**Seventh instance of one root cause: `is_eligible` was doing two jobs.** D1 moved judgeability off
it; this moves the rate off it. Said at both sites, not only here.

**And it separates a per-candidate collapse nobody had noticed:** a candidate screened out
everywhere read rate `0.0` — identical to one fitted at every point and passing. *"Nothing was
tried"* and *"everything succeeded"*, one number. Over `fitted` the first is `None`. The
no-evidence decision's collapse, at candidate granularity.

**Gate before flip, in separate commits, and the order is the argument.** The gate repair is correct
independent of OQ24 and provable independent of it: criterion 19's fixture keeps its producer under
the *current* eligibility rule, so the repair goes green before the re-baselining exists. Two
changes that could each explain a wrong number land separately.

### D3 — the clustering graph's population is `is_fit_verdict`, which generalises §14.2's one stated exclusion

§14.2 says `NOT_APPLICABLE` leaves the adjacency graph entirely, because land forms enormous
contiguous blocks and would dominate the statistic with a spurious signal. **That argument is not
about land.** Every non-fit code has the identical pathology: `CANDIDATE_DROPPED` covers 100% of
pass 2 for a dropped candidate, a perfect single cluster; `SCREENED_OUT` will cover whatever the
screening block selects, which is by construction coherent; `NOT_ATTEMPTED` on an interrupted run
covers unwritten tiles, which are literal rectangles.

So the graph is built over cells where the store records a fit verdict. **The predicate D1 added for
the gate is the predicate the graph needs**, and the unfinished-store case (D6) therefore requires no
special handling — which is the generalisation paying immediately.

**The rates keep `is_eligible`.** Two populations, each named at its use. That is not one
measurement stated twice: D1 established that they are different questions.

### D4 — join-count, rook, index-space, no seam wrap

**Join-count (BB) on the binary failure indicator**, reported as the raw count with the permutation
null's median and quantiles and a z-score — not a bare coefficient, per §14.2. **Moran's I is
refused**: on a 0/1 field it is a linear transform of the same quantity under the same weights, so
choosing it would be choosing the form §14.2 says nobody can interpret.

**Rook (4-neighbour), index-space, documented as such** — §14.2 fixes index-space; rook rather than
queen because the statistic is about contiguous patches and queen's diagonal joins make the count
more sensitive to grid anisotropy.

### ~~No wrap at the longitude seam~~ — RE-DECIDED 2026-09-19 ON TASK 0's NUMBERS

**The original decision was "never wrap, bias bounded by one column of joins", and P4 measured that
bound false by forty-fold**: Δz = **11.02** at W = 360 against a predicted < 0.25, with the edge
loss at 0.14% exactly as predicted. **The bound was computed on the denominator and the effect is
in the numerator** — not wrapping removes 16 of the *observed cluster's own* joins, because the
seam joins are precisely what make a seam-straddling cluster one cluster rather than two.

**DETECT GLOBAL COVERAGE FROM THE `x` COORDINATE AND WRAP WHEN IT IS GLOBAL**, with the detection
rule stated, tested in both directions, and printed.

- **The rule is arithmetic on stored coordinates, not a guess:** `n_x · dx` within half a cell of
  360°, on degree-like units, with regular spacing. **Every ambiguous case fails toward
  not-wrapping** — unknown or non-degree units, irregular spacing, or a span short of 360° because
  columns are missing. Auditable rather than inferred.
- **The report prints the span it found** — *"22.5° of 360°, not global, not wrapped"* — so the
  not-global branch stops being a policy and becomes a **measurement**. This is what the old
  decision's limitation statement becomes, and it is strictly better than asserting one.
- **Always-wrap is refused** and the reason is stronger than "wrong on a subset box": **every real
  store this project has produced is a subset box**, so always-wrap would manufacture adjacency on
  100% of the actual data to date, and **0% of it would be caught by a real-data check**.
- **A flag with no default is refused** as D6's flag reintroduced: it is a report refusing to run on
  a store whose owner may not have made it — the foreign-store property broken — and it gates a
  whole run on one number among many. **A declaration is available as an override on top of the
  detector, never as the mechanism.**

**AND THE DETECTOR'S OWN WEAKNESS IS MADE SELF-AUDITING RATHER THAN LEFT INVISIBLE.** A detector
can be wrong in both directions and nothing downstream would show it — so **when the question is
live, both arms are computed and BOTH ARE PRINTED IN FULL**: `z` and `p` for each, labelled
`wrapped` and `unwrapped`, with the detected arm marked as the reported one.

**~~Δz is exactly the bound on what the judgement cost.~~ STRUCK 2026-09-20, AND THE REASON IS A1's
DEFECT REAPPEARING INSIDE ITS OWN SUB-PHASE.** Δz is the wrong scalar, and Task 0's own table shows
why: wrapped 239.9 against unwrapped 199.9 is **Δz = 40 with both arms reaching the identical
conclusion**, while two arms at z = 2.1 and z = −8.9 are **Δz = 11 with opposite conclusions**. Δz
cannot distinguish those, and distinguishing them is the only job it has — **the reader is not
asking how much the seam moved the statistic, they are asking whether the arm choice changed the
answer.** A derived scalar that discards the comparison it was derived to support is exactly what
A1 struck from §14.2's closing line, one decision away and one day later. Δz may be printed
*beside* the two arms as a convenience; it never stands in for them.

**THE TWO-ARM ZONE IS WIDER THAN THE WRAP GATE, DELIBERATELY** — both arms are computed whenever
the `x` coordinate is degree-like and its span is **within a couple of cells of 360°**, not only
when the gate says global. **This removes the hazard rather than pricing it.** The false negative
bites only on the not-global branch, where one arm is computed and no comparison exists; widening
means the realistic false negatives — a global grid with masked columns, a global grid whose
spacing fails the regularity check — **all land near the boundary in span, which is precisely where
the widening reaches**, and each then prints both arms for the reader to compare. What widening
does **not** catch is a global grid in unrecognised units, which no measurement in this plan
reaches either.

**Mechanism over assertion**, the same preference as D9's structural refusal of categorical
downsampling and F5's permission-removed store over a byte comparison. **A hazard removed does not
need a number.**

Where both arms fire the cost is **2×**, against a floor of 224 s, on a report describing a run
that took days — and this project currently has **no** near-global store, so the cost is
hypothetical. A 22.5° subtropical box computes one arm and prints its span.

**THE WRAP BRANCH IS FIXTURE-TESTED ONLY, AND WILL BE UNTIL A GLOBAL STORE EXISTS.** Stated here,
at the code path, and not only in the limitations section: this is the standing geographic
limitation — every real-data number in this project is one box of subtropical open ocean — reaching
a branch of the implementation.

### The not-global branch's limitation: priced where it is priced, named where it is not

**Priced.** The seam's effect on the statistic is measured: **Δz = 11.02** at W = 360 — *at a
saturated operating point*, on a deterministic fixture, one reading per width.

**Not priced, and named rather than estimated.** The *consequence* — whether not wrapping ever
changes the verdict on a real seam-straddling cluster — **was attempted on two ladders and reached
by neither.** The first saturated because the cluster was enormous (both arms z ≈ 230); the second
saturated because the grid had no background failures, so the null expected **0.01** adjacent pairs
and any clump sat 200 SD out on both arms. **Two fixtures, both unable to express the condition
the question names.** See (a10) instances 1 and 3.

**`second-order risk` is not written here**, because that is an estimate and this project does not
carry estimates as conclusions.

**P4″ IS OWED AT A TRIGGER, NOT DROPPED: the first time a global store exists.** At that point the
branch stops being hypothetical and the measurement acquires a real subject and real geometry
instead of a synthetic ladder — and **it will carry the precondition both earlier attempts lacked**:
demonstrate an operating point where the wrapped arm's rejection rate sits strictly inside
(0.2, 0.8), *asserted before the arms are compared*, or the comparison is INDETERMINATE rather than
negative. (a10)'s one sentence, applied in advance.

### D5 — the null permutes labels among eligible points with the mask held fixed

This is the load-bearing decision of the statistic. Holding the mask fixed preserves the
missing-data geometry **and** the failure count, so the null asks **"is this arrangement unusual"**
rather than **"is this rate unusual"**. The other permutation is the obvious one and it tests a
different hypothesis. Said at the null, not only here.

**999 permutations**, a stated constant: p = (1 + #{null ≥ observed}) / 1000, so the floor is 0.001.
More permutations buy **resolution at the floor and nothing else** — power comes from the data, not
the null's size — so 9999 is warranted only where a p sitting at the floor is load-bearing. **The
seed is a stated constant, printed in the report, overridable by flag**, and once set it joins the
do-not-move list: moving it changes every reported p.

### D6 — an unfinished store is described, not refused

§12.5's *"a finished store should hold none"* is a fact about finished stores, not a definition of
this command's subject. The report's subject is a store; whether it is finished is a property the
report **describes**.

§14.1's motivating case decides it: that section exists because discovering at hour 9 that ten hours
were wasted is the expensive outcome, so a report refusing to run on exactly the store that
discovery produces would be the mechanism declining its own use case. A `--allow-incomplete` flag is
worse than refusing: a flag whose only effect is to permit the common case trains the user to pass
it always, at which point the default has no consumer and the caveat rides on a flag nobody reads.
**And this project's whole reporting idiom is compute-and-qualify** — INDETERMINATE, withheld rates,
the 30-member floor, "excluded is not missing". Refusing here would be the one place it inverts.

**Completeness is read from `/completion/tiles`, never inferred from `NOT_ATTEMPTED`.** Two different
questions — the bitmap says which tiles were written, the outcome says what a cell holds, and a tile
can be complete with `NOT_ATTEMPTED` cells. 2a's data-then-bitmap invariant makes the bitmap
authoritative. **A disagreement between the two is reported as a defect, never resolved silently.**

`N` and `M` are **numbers in the record**, not a banner, so the markdown renders them beside every
denominator and a quoted rate travels with its population.

**The statistic on an unfinished store keeps its own word:** unwritten tiles are rectangles, so the
eligible mask has rectangular holes — and because the null holds the mask fixed (D5), it correctly
conditions on that geometry. The statistic is valid and its interpretation narrows to *"is the
arrangement unusual given what was fitted"*, not *"given the domain"*. Stated, because a reader
will otherwise take a z-score on a half-finished run as a statement about the field.

### D7 — per candidate, with the aggregate as a second headline of a different kind

The statistic is computed **per candidate** on `outcome[y,x,m]`. The point-level aggregate is `OK` if
**any** candidate is `OK` (§12.5's rule), so an aggregate-only statistic reports "no clustering" for
a store where one candidate fails in a coherent patch everywhere — and that geography is what §12.5
calls a diagnostic. A statistic that cannot see the thing its section names is not the conservative
choice.

**Two headlines with different subjects, and the family is summarised by its maximum.** 2d settled
max-over-strata rather than mean, because a mean can understate and a maximum cannot; that rule
applies **within** the candidate family. It does not reach the aggregate, which is different in
kind: a candidate's indicator says *this candidate failed here* (a selectability fact), the
aggregate's says *no candidate produced a usable fit here* (a coverage fact — a hole in the output).
The aggregate is **not** a member of the family and is not summarised by it.

**AND THE DEFAULT REPORT IS A FAMILY OF TESTS, WHICH D8 GUARDS ON THE FLAG AND THIS DECISION MUST
GUARD ON THE PATH EVERYONE READS.** D8 gives the per-branch capability a multiple-comparison caveat
because *"a family of tests reported without a correction invites reading the largest z as the
finding"*. **M per-candidate statistics summarised by their maximum is that same family**, in the
default report, with the correction riding on a flag only the person asking open question 23 will
set. **2d's rule does not transfer**: max-over-strata was chosen for a **descriptive** summary,
where a mean can understate and a maximum cannot, and a maximum over M **inferential** statistics
has inflated type I error — a different argument, which this plan does not make and will not make.

**So the report prints all M z-scores.** M is small and they are computed per candidate anyway, so
there is nothing to save by hiding them; and any single headline is labelled **"max over M
candidates, uncorrected"** *at the number*, not in a note beside it.

### D8 — per-branch statistics are a named capability with a trigger, not a deferral

*"Is `DEGENERATE_HESSIAN` clustered?"* is open question 23's own question, and the maps already carry
the geography per branch. So the per-branch statistic is **available on request** under one flag,
documented as *"compute this when asking open question 23's question"*, carrying its own
multiple-comparison caveat — because a family of tests reported without a correction invites reading
the largest z as the finding. That gives OQ23 an instrument without 2f owing a correction on every
ordinary run. **A closer, not a gap.**

### D9 — maps are per branch because they are binary, and binary because the honest reduction is a fraction

**§14.2's two halves are load-bearing together, and the amendment anyone would make breaks them.**
The plan that was nearly written amended *"downsampled PNG map per branch"* to categorical
per-candidate maps, colour = outcome, legend from the store's own `flag_meanings`. It is wrong:

**A categorical code array has no honest arithmetic reduction.** Downsampling outcome codes by mean
turns code 7 (`DEGENERATE_HESSIAN`) and code 11 (`ILL_CONDITIONED_X`) into code 9, which is
`CANDIDATE_DROPPED` — a real, different, **valid-looking** code. A downsampled categorical map does
not produce a wrong picture, it produces a **plausible** one.

The obvious escape was checked rather than assumed: reuse `merge_outcomes` and `OUTCOME_PRECEDENCE`
for the block reduction, as §12.5 did for the point aggregate. **It does not work** — that ladder
holds six members and `DEGENERATE_HESSIAN` is not among them ("the outcomes *this module* can
combine"), so it cannot rank the most common real failure, and inventing a second precedence is what
§12.5 warns against by name.

So a downsampled map must be **per branch**, because a per-branch map is binary and its honest block
reduction is the **fraction** of the block carrying that code. §14.2 was right and the reason is now
visible.

**Map inventory:** one map per (branch present × candidate), plus one per branch for the point-level
aggregate. Bounded by what occurred rather than by the 14-member alphabet — real stores so far show
`{OK, DEGENERATE_HESSIAN, TRUST_RADIUS_COLLAPSED}`.

**INVARIANT: map and statistic are never computed over different things.** The comparability rule,
applied inside one report.

**Colours.** Fractions do not cross zero → `viridis`; `n_valid` and iteration maps likewise
sequential; anything crossing zero → `RdBu_r` with symmetric limits. No `cmocean` map applies and
`cmcrameri` is not added for `batlow`: these are **diagnostics about fitting, not geophysical
variables**, and a matplotlib built-in that is perceptually uniform and colourblind-safe does the
job without a dependency inside an optional extra.

**FIXED COLOUR LIMITS, `vmin=0` AND `vmax=1`, ON EVERY FRACTION MAP — AND THIS IS THE SAME DEFECT
CLASS ONE LEVEL DOWN.** matplotlib autoscales `vmin`/`vmax` to the data, so a branch present at 0.01
to 0.03 everywhere renders as a full-range dramatic map, and two stores with different fraction
ranges are not comparable. **An autoscaled fraction map is the mean-of-codes defect with a
colourbar**: it does not produce a wrong picture, it produces a *plausible* one, which is this
decision's own argument in continuous form.

**~~Fixed code-to-colour across runs, and a legend from the store's own `flag_meanings`.~~** Struck,
not deleted, because it is what an earlier draft of this decision carried and the mistake is
instructive: **those are properties of the categorical design this decision refuses.** On a binary
fraction map in `viridis` a branch has no colour — it has a map — and `flag_meanings` supplies the
**title**, not a legend. Rejecting a design and keeping two of its requirements is how a refused
design survives in its own replacement.

### D10 — matplotlib behind a `[report]` extra, lazily imported, enforced by an import-graph test

§14.2 requires the maps from the shipped entry point, so deferring them fails the section. Putting
matplotlib in `[batch]` makes every headless compute node running a fit install a plotting stack,
which is not what that extra means. So: a new `[report]` extra; `maps.py` the only importer and
imported **inside the function**; the numbers path dependency-free, because that is the half that has
to work on someone else's store.

**This has a receipt.** `tests/test_readme_figure.py`'s docstring records that importing the figure
generator dragged matplotlib into the suite, *"which is in the dev environment and not in the
dependency set CI installs, so this file passed locally and failed in CI on its first push"*.

**Enforcement is a subprocess import-graph test**, on `test_core_isolation.py`'s precedent — which
exists because *"inside the pytest session every one of these is already imported by some other test
module"*. That measures the import graph rather than what happens to be installed, which is both
stronger and cheaper than a second CI environment.

**~~The report imports `metamer.core.outcomes` as a leaf, because `import metamer.core` drags
`core.fit` and every family.~~ STRUCK 2026-09-20 AT TASK 1's PRE-FLIGHT: THERE IS NO SUCH THING AS
A LEAF SUBMODULE IMPORT.** Python executes a package's `__init__.py` on any submodule import, and
`metamer/core/__init__.py` imports `families` — a deliberate, documented, load-bearing registration
side effect — and `core.fit`. **This plan stated a mechanism that cannot hold, and Task 1's own test
would have failed on its first run.**

**MEASURED AT THE PRE-FLIGHT, AND THE REPLACEMENT INVARIANT IS SHARPER THAN THE STRUCK ONE:**

| import | seconds | modules | heavy members |
|---|---|---|---|
| `metamer` | 0.001 | 64 | — |
| `metamer.core.outcomes` | 0.500 | 708 | `metamer.core.fit`, `scipy` |
| `metamer.batch.store` | 0.688 | 928 | + `zarr` |
| `metamer.batch.run` | 1.425 | 1002 | + **`pydantic`** |

`numba` and `matplotlib` appear in **none** of them. What `batch.run` adds over `batch.store` is
**the config machinery**. So:

> **`metamer.report`'s import graph contains no `matplotlib`, no `numba`, no `pydantic`, and no
> `metamer.batch.run`.**

**That is the foreign-store property in mechanism form** — a user with a store and no config cannot
be made to load the validator for a config they do not have — and it is testable, true, and the one
the property actually needs. **`metamer.core` and `core.fit` ride along**, stated with their
measured cost (+0.5 s, no JIT, no plotting stack) rather than excluded by a claim that cannot hold.
Restructuring `core/__init__.py` is refused: the registration side effect is load-bearing, and
moving `Outcome` out of the spine for a reader's convenience is not a trade this sub-phase makes.

### D11 — the drop row: carried record primary, recomputed and asserted when pass 1 is present

§14.2 reasons about *"a candidate dropped after failing 91% of pass 1 has `CANDIDATE_DROPPED`
written across every **remaining** point"* — a mid-run drop. **2e implemented the drop between
passes**: `dropped` goes into pass 2's `run`, so in the output store the candidate is
`CANDIDATE_DROPPED` at **100%** of points and "points where the candidate was still live" is
**zero** there.

The row is computable anyway, and the reading is stated rather than hidden: **the row reports a
decision the run took, and a decision's evidence is what the run saw when it took it** — which is
not recoverable from the output store, because the mechanism overwrites the population it judged.
That is the same reason pass 1 keeps its real outcomes.

`early_abort.rates[]` is written into **pass 2's** root attrs, and `_verdict_attrs`' own docstring
records that *"the rates are recomputable from pass 1's store, which is permanent; the THRESHOLD and
the POLICY are command-line flags and exist nowhere else"*. So: **read the carried record as primary;
when `out.pass1.zarr` is present, recompute from its arrays and assert agreement; label the number
as carried when it is not.** A carried counter verified against the store whenever the store is
there. "Computed from the store" is a claim about reproducibility, and a persisted decision record
is reproducible.

### D12 — the run records the resolved candidate table; the report reads it

§14.2's *"per-candidate resolved engine, cost class, gradient mode, and objective"* is **not
computable from the store**. Root attrs carry `engine` and `objective` run-level,
`registry_version`, and `candidate_spec_hashes` — hashes, which are one-way. The only per-candidate
identity is the `m` label, and `model_label` is `" + ".join(spec.labels())` with **no inverse
anywhere in the tree**.

**This is a missing record, not a wrong home**, and the distinction matters: a bullet whose home is
wrong moves (A2); a bullet whose record is missing needs the record written, and deferring it only
relocates the absence. **Deferring to Phase 5 does not work**, because `--explain` reads a config and
a registry: the resolved engine, cost class and gradient mode are decided at run time by §4.2's
capability intersection, so Phase 5 would have to re-resolve from the config — answering *"what would
this config resolve to now"*, not *"what was run"* — or read a record that does not exist.

**A label→spec inverse is refused explicitly, because it is the cheapest to reach and will be
proposed again.** It is a permanent round-trip contract binding every future registry entry, bought
for a printing convenience, **and it answers the wrong question**: an inverse recovers the spec, not
what the run resolved it to, and the resolution depends on the engine capabilities at the time —
exactly what is not recoverable.

**So the run records it**, in the same shape and on the same rule as 2e's two instances: `threshold`
and `policy` into `early_abort` attrs because they are flags existing nowhere else, and `fitted`
into the persisted record because the verdict was decided on a quantity absent from its own record.
**Third instance of §17's measure/print rule; it cites them rather than re-arguing.**

Three constraints hold it:

- **Absence is the answer for older stores.** A store written before the block carries no block and
  the report says so; **nothing is back-filled**, because a back-fill makes an old store claim a
  resolution nobody recorded — the same refusal as `field_construction_version` on a version-1
  report, and the `calibration` / `decimation` precedent.
- **Additive, and it moves no hash — confirmed structurally, not assumed.** The three hashes hash
  `normalize(config)` subset to allowlisted fields. The block records what was **resolved**, which is
  an output of resolution and never a config field, **so it cannot enter any payload**. That is the
  whole argument and it carries the conclusion alone. The precedent by name is `hashing.py`'s own:
  *"the audit's settings MEASURE a run; they are not inputs to it, so they are outside this set"* —
  the same shape exactly. Provenance, not identity, like `max_iter`, `floor`, `read_amplification`
  and `thread_limits` already in root attrs.
  **AND `hashing.py`'s FIT-RELEVANCE TEST IS NOT CITED HERE, DELIBERATELY.** *"A field is
  fit-relevant if changing it can move `theta_hat` or `log_lik` for any input"* ranges over **inputs**
  and is **ill-posed on an output**: an output cannot be changed independently of what produced it,
  and the resolved table correlates perfectly with fields that do move `theta_hat`. Applying it here
  would reach the right conclusion by an argument that does not hold. **The test governs config
  fields; outputs are excluded structurally, one step earlier.** Recorded because this decision is
  building precedent, and a precedent that propagates a bad citation propagates the bad citation.
- **The write-path touch is a stated deviation.** 2f's property is that **the report** reads and does
  not mutate — and this is **the run** writing, which preserves it exactly. Said at the change,
  because "2f touched the write path" will otherwise read as the property being broken.

### D13 — exit codes: reuse `ExitCode`, and a report's code describes the report

One published table, not a second. **Producible:** 0; 3 (usage, as `_Parser.error` already maps);
4 (the store is unreadable, is not a metamer store, or carries an unknown `schema_version` — "data"
is the store here); 5. **Not producible, each with its reason recorded:** 1 is defined as *a two-pass
run whose verdict found a candidate above threshold and which completed anyway* — a property of a
run, and the report is not a run; 2 is *aborted early, resumable*, and a report is not resumable.

**THE RULE: a report's exit code describes the report, never the run it describes.** That is 2e's
instrument finding 7 — *where a tool reports on something else, its exit code describes the tool* —
for the fourth time, and **the first time it has been written down before something was bitten by
it.** Its three earlier instances all cost a wrong reading first: the `&&` chain, the `| tail` pipe,
the early-returning watcher.

---

## The §14.2 amendments this sub-phase owes

**§14.2 has four bullets the store cannot answer as written, and they are three different defects.**
All four were found by checking the section against the store rather than against itself.

- **A1 — the scalar summary into root attrs: conflicting requirements, and the later one wins.**
  §14.2's closing line asks the report to write its summary into the store's root attrs. §14.2's
  lead property is that the report is **usable on someone else's store**. A report that mutates its
  subject cannot be run on a store you do not own. The amendment strikes the attrs write and records
  the conflict; **nothing is lost**, since the summary is in the report file and the store's own
  arrays are what a consumer reads.
- **A2 — the two audit bullets: wrong home.** *"§11.2 audit numbers: disagreement rates overall and
  per difficulty stratum"* and *"mean iterations warm vs cold against the ≥30% threshold"* need two
  arms. `python -m metamer.report <store>` takes one store by construction. They live in
  `audit_report.py`, a benchmark instrument, already built and already wired — and §14.2 says where,
  so a reader does not go looking for them in the report.
- **A3 — the resolved candidate table: missing record.** D12. The section keeps the bullet; the run
  gains the record.
- **A4 — the drop row's population.** §14.2 describes a mid-run drop; the implemented mechanism
  drops between passes. D11's reading is recorded at the bullet.

And two clarifications that are not defects:

- **A5 — the adjacency graph's population is every non-fit code**, not `NOT_APPLICABLE` alone (D3),
  with §14.2's own argument extended rather than replaced.
- **A6 — "downsampled" and "per branch" are load-bearing together** (D9), recorded at the bullet
  because the amendment that breaks them is the one anyone would make.

---

## Standing requirements for every task

- **Run the pre-flight against the task brief before code**, appending to
  [`phase2f-preflight.md`](../notes/phase2f-preflight.md) **before** the task, not after. The method
  lives in exactly one place — [the handoff](../notes/phase1-to-phase2-handoff.md) §1 — and is not
  restated here.
- **`pixi run test` is the full sweep and every end-of-task verification runs it**, to a file, read
  on its own status. `test-fast` and `test-ci` are not evidence. **Never pipe a checker through a
  truncating filter** — `| tail` has hidden a failing test, a failing hook and a wrapper's exit code
  in three forms in 2e alone.
- **`git add` a new file before `pre-commit run --all-files`**, which covers tracked files only, and
  stage anything a tool may restore.
- **Commit after every task; check CI after every push, by the until-loop on the run's own `status`
  matched to HEAD's `headSha`** — never by position in `gh run list`, never by a wrapper's exit code.
  **One push per run.** Red CI is the next task.
- **No exit-criterion verdict from 2a–2e moves — AND THAT RULE NEEDS A DISTINCTION IT HAS NEVER
  CARRIED, because 2f is about to act correctly against its surface reading.**

  > **A verdict's RECORD may be corrected when the correction is a finding about what was actually
  > read. A verdict's VALUE is not re-argued by a later phase.** The first is provenance and is
  > always allowed; the second is what this rule forbids.

  Without it, a later session reading "no verdict moves" either fails to notice a stale reading or
  refuses a correct repair. **This goes into the handoff's §2 as well as here**, because the rule is
  quoted from there.

  The inherited verdicts stay visible: **2b's 6 and 7 FAILED, 2c's 11 reduced, 2d's 6, 11 and 14
  failed with 12 reduced, 2e's 14 reduced, and 2e's 9 CORRECTED — reading narrowed, verdict
  unchanged** (see below). 2e's 14 is the drop row, which is 2f's Task 3.

  **WHY 2e's 9 IS RECORDED AS CORRECTED RATHER THAN REDUCED, ARGUED RATHER THAN ASSUMED.** Review
  proposed MET → MET WITH REDUCED SCOPE, on the ground that the criterion was met on a narrower
  reading than the one recorded. The reach is not in dispute: the helper globs `notes/*.json` for the
  key `outcome_counts` and reaches **8 of 16**, missing six in `notes/*.json` spelled `counts` and
  two in `notes/*.jsonl` — all inside its own declared `outside`, *"the committed reports under
  `docs/superpowers/notes/`"*. What is in dispute is which field moves.

  **In this project's vocabulary a reduced scope means the criterion was achieved over a narrower
  SUBJECT than stated** — 2e's own 14 is the model: the drop row was not delivered at all and became
  2f's. Criterion 9's subject is the claim *"no committed audit number moves under the
  reclassification"*, and that claim **is true over the full population**, established by 2f's
  independent scan of all sixteen on 2026-09-19. Marking it reduced would record the project as
  holding **less** evidence than it holds, at the moment the evidence got wider.

  So: **verdict MET; the reading corrected to what the helper walked; a dated note recording that at
  2e's close the instrument reached 8 of 16, so the criterion as closed rested on narrower evidence
  than its reading claimed, and the full population was checked on 2026-09-19 with the conclusion
  unchanged.** The over-claim stays visible — which is the half of review's finding that must not be
  lost — without recording a reduction that no longer exists. **If you read the field differently,
  say so and it becomes REDUCED**; this is the one finding of the ten I did not take as written.
- **No task moves** `PUBLISHED_TILE_SIDE`, `resident_bytes_per_series`, `output_slot_bytes`,
  `SVD_CHUNK_SERIES`, `HEADROOM_FRACTION`, `ALGORITHM_VERSION`, `FIELD_SEED`, `HESSIAN_COND_LIMIT`,
  or any `Outcome` code. **2f adds no `Outcome` member.**
- **The report never writes to the store it reads.** Task 4's write-path change is the run's, not the
  report's, and says so.
- **Every rate names its denominator at the row**, and every unavailable quantity names its reason
  rather than reporting a zero.

## Task index and dependencies

| # | task | depends on | gates |
|---|---|---|---|
| 0 | the clustering spike — cost, calibration, floor, seam | — | **Tasks 5 and 6**; a cost 10× the assumed one re-plans them |
| 1 | the reader, the import boundary, and completeness | — | every later task |
| 2 | rates per branch and per candidate, with denominators | 1 | 3 |
| 3 | the drop row, and 2e's criterion 14 | 2 | — |
| 4 | the primitives sections, and the run's resolved-candidate record | 1 | — |
| 5 | selectability — the section §14.2 leads with | 1 | — |
| 6 | the clustering statistic and its null | 0, 1 | 7 |
| 7 | the maps, the `[report]` extra, and the no-matplotlib path | 6 | — |
| 8 | the entry point, the exit codes, and render-from-record | 1–7 | — |
| 9 | open question 23's capability | 6, 7 | — |
| 10 | the 2f exit-criteria suite | all | — |

**Task 0 gates Tasks 5 and 6 and is not a formality.** 2d's Task 0 was a whole task and nearly
collapsed the sub-phase; 2e's pre-flights changed the size or shape of five of eight tasks. **The
prediction on the record is that 2f does not need open question 22's repair**, because every
measurement that has cost this project days was a *fitting* measurement and 2f fits nothing — but
that is a prediction, and P1 is what settles it.

---

## Task 0 — the clustering spike

**Goal.** Price the permutation null, calibrate it in both directions, measure the seam, and measure
the floor — **before** the statistic has an implementation to defend.

**Predictions are committed to `phase2f-clustering-predictions.json` before the harness runs**, with
refutation clauses in both directions. The harness writes `phase2f-clustering-measured.jsonl`; the
verdict is `phase2f-clustering-verdict.md`.

- **P1 — cost.** 999 permutations, rook graph, eligible fraction 0.7, at 64² / 256² / 1024².
  **Refutation:** if 1024² exceeds 600 s, the permutation count or the implementation is re-planned
  — not the sub-phase. **This is what decides whether 2f needs open question 22's repair.**
- **P2 — negative control.** Failures placed by independent Bernoulli draws at the observed rate;
  over 200 replicates the rejection rate at α = 0.05 lands in **[0.02, 0.09]**. **Below it the null
  is mis-specified and conservative; above it the statistic over-rejects. Both directions fail the
  task.**
- **P3 — positive control.** A planted contiguous patch of the **same total count** rejects at the
  p-floor in ≥ 95% of replicates. **P2 and P3 together are the instrument's calibration**, and
  numeric bands on both are what make a null result readable.
- **P4 — the seam, with a predicted magnitude and a named consumer.** A genuine cluster straddling
  the antimeridian, on a global grid of `W` columns, wrapped against not. **Prediction: the
  non-wrapped join count is lower by at most `2·H` joins out of `≈2·W·H` — one column of vertical
  joins — so the relative loss is bounded by `1/W`, and the z-score difference is under 0.25 at
  `W ≥ 360`. Refutation, both directions:** above 0.25 the no-wrap choice of D4 is not free and the
  seam must be detected or the limitation restated as material; **below 0.01 the measurement is too
  weak to be worth printing** and the caveat becomes a static sentence rather than a number.
  **Its consumer is Task 6's invariant** — the report prints the seam caveat carrying this measured
  magnitude — because P4 is the sole evidence behind D4's no-wrap choice, and **a measurement with
  no consumer gets made and forgotten.**
- **P5 — the floor.** The smallest eligible-point count at which P2's calibration breaks. **The floor
  is measured, not picked** — which is where 2d's 30-member floor was weaker, that number coming from
  a binomial SE argument and this one from where the calibration actually fails.
- **P6 — the zero-edge mask.** A checkerboard eligible mask must come back **unavailable with its
  reason**, not as a number. (i12): the fixture is asserted able to express clustering before any
  assertion about clustering.
- **Reproducibility** in iterations: same seed → identical z three times. **Cost in seconds.**
- **The quiet-host check gates P1 only**, and P2–P6 are marked host-independent explicitly, the way
  the real-data spike marked `seconds_are_the_contaminated_half`.
- **The control that reproduces a committed number exactly:** a constructed store carrying the
  real-data spike's committed `real_ct` histogram — `{OK: 809, DEGENERATE_HESSIAN: 91}` — must make
  the report's own counter produce 91 and 809 before it produces any new number.

**Exit.** The verdict names each prediction met or refuted, and says in one sentence whether Tasks 5
and 6 proceed as planned.

---

## Task 1 — the reader, the import boundary, and completeness

**Behaviour.** `metamer.report.reader` opens a finished store **read-only** and returns a labelled
view: the status, selection and primitive arrays; the `m` and `c` labels; the root attrs; and the
completion state as `(complete_tiles, total_tiles)` read from `/completion/tiles`. An unknown
`schema_version` is refused with `ExitCode.DATA_INVALID` and a message naming the version it found
and the versions it knows.

**Invariants.**

- **The store is never opened for writing**, anywhere in `metamer.report`.
- **Completeness comes from the bitmap, never from `NOT_ATTEMPTED`** (D6), and a disagreement — a
  complete tile holding `NOT_ATTEMPTED` where no candidate was screened, or an incomplete tile
  holding fit verdicts — is **reported as a defect in the report itself**, not resolved.
- **The import graph excludes matplotlib and the fit path** (D10).

**Interface Tasks 2–8 bind against.** `read_store(path) -> StoreView`, where `StoreView` exposes
`outcome`, `delta_ic`, `selected`, `n_valid`, `iterations`, `model_labels`, `criterion_labels`,
`attrs`, `completion`.

**Tests, each with the bug it must catch.**

- A store written by the current writer round-trips every array and both label axes — catches a
  reader keyed on a group name the writer does not use, which no unit test of the writer can see.
- An unknown `schema_version` exits `DATA_INVALID` and names both versions — catches a reader that
  silently reads a future layout and reports numbers off misaligned axes.
- A directory that is not a zarr store, and a zarr store that is not a metamer store, both exit
  `DATA_INVALID` — catches a bare `KeyError` escaping as `INTERNAL_ERROR`, which tells a script the
  report is broken when the input is.
- **The import-graph test, in a subprocess**: importing `metamer.report` leaves `matplotlib`,
  `numba`, `pydantic` and `metamer.batch.run` absent from `sys.modules` — catches the convenience
  import that makes the report unusable where a store is readable, which is the failure
  `test_readme_figure.py` records CI already having had once, and the config import that would
  break the foreign-store property.
- **Its positive control, in a second subprocess**: a probe that imports a module known to drag a
  forbidden member must report it. **(a10)** — a probe that passes because it imported nothing is an
  instrument reporting its operating point, and the subprocess isolation that makes the first test
  meaningful is about *visibility*, not about *discrimination*. Both are needed.
- A store with an incomplete bitmap reports `(N, M)` with `N < M` and does not raise — catches a
  reader that treats incompleteness as an error, which is D6 inverted.
- A complete tile holding `NOT_ATTEMPTED` is reported as a disagreement — catches the silent
  resolution, which would let a partially-written tile read as a screened candidate. **The fixture
  states its own reachability**: this state is constructible and **not producible by any run**, so
  the test does not imply the condition occurs in the wild.

---

## Task 2 — rates per branch and per candidate, with denominators

**Behaviour.** Counts and rates per taxonomy branch and per candidate, each rate carrying **its own
denominator at the row**.

**BOTH DENOMINATORS ARE PRINTED, PER CANDIDATE, AND THE GAP BETWEEN THEM IS THE DIAGNOSTIC.**
`failed / fitted` **and** `failed / eligible`, each named at its row. This is D4's
wrapped-and-unwrapped two-arm print applied to denominators: **where a denominator is contested,
print both and let the difference speak** rather than choosing one and carrying a caveat.

**The reason is D2b's measurement, one layer up.** Repairing the *gate* and leaving the *report* on
`eligible` alone would ship a failure rate whose denominator contains land — *"60%"* where a third
of the denominator is out of domain, which is a statement about record coverage **plus land
fraction**, exactly the uninterpretable quantity §12.5's separation exists to prevent. **On this
project's one ocean box the two numbers are identical, which is precisely why it would have
shipped**: the thing with a test got fixed and the thing without one did not.

A reader on an ocean box sees two identical numbers and learns the exposure is nil. A reader on a
global run sees **1.00 against 0.60** and learns everything.

~~The eligible-point denominator is `Outcome.is_eligible` — which after D2 includes
`INSUFFICIENT_DATA` and excludes `NOT_APPLICABLE` only.~~ **CORRECTED IN PLACE 2026-09-22, AT TASK
2's PRE-FLIGHT: THIS CLAUSE WAS WRONG, AND IT CONTRADICTED THE SENTENCE AFTER IT.** `is_eligible`
does exclude `NOT_APPLICABLE` only — measured over all fourteen members — so it **includes**
`NOT_ATTEMPTED`, and the next sentence requires that member out of both denominators. The behaviour
the next sentence states is the requirement; the description of which predicate delivers it was the
defect.

**THE SECOND DENOMINATOR IS `Outcome.is_covered`, A PREDICATE OF ITS OWN** — *in the domain **and**
the run reached it* — added at Task 2 and **not** a narrowing of `is_eligible`, whose values are
already in committed artifacts and whose `audit_report` reader is open question 25's filed subject.
It excludes `NOT_APPLICABLE` because the point is not in the domain and `NOT_ATTEMPTED` because the
run never got there: **two exclusions, two different reasons, stated at its table.** The fitted
denominator is `Outcome.is_fit_verdict`. **`NOT_ATTEMPTED` is out of both denominators and COUNTED
in the branch table**: it is the absence of information, and an interrupted run must say how much of
its grid it never reached.

> **AND THE REASON THIS IS NOT A TIDY-UP.** §12.5 gives `NOT_ATTEMPTED` the entry *"n/a, and a
> finished store should hold none"* — true of a finished store, and **D6 and criterion 19 put
> UNFINISHED stores in scope deliberately.** There the member scales with how far the run did not
> get, so counting it in a coverage denominator makes **a run killed earlier report a better rate**.
> No fixture that finishes can show it, which is why Task 2 carries a three-arm interruption ladder.

**THE FOUR PREDICATES NEST**: `is_failure` ⊂ `is_fit_verdict` ⊂ `is_covered` ⊂ `is_eligible`,
asserted over the whole enum with each step proved proper by a named witness. That chain is what
makes the two rates share a numerator, and what makes `fitted == 0` their single shared
unavailability condition.

**Invariants.**

- **`branch` means taxonomy branch** — an `Outcome` member — as `progress.py`'s `by_branch` and §14.1
  already fix it. Not a candidate.
- **WHEN `fitted == 0`, BOTH RATES ARE UNAVAILABLE, EACH NAMING "nothing fitted", AND THE ELIGIBLE
  COUNT APPEARS AS A COUNT RATHER THAN AS A DENOMINATOR.** D1 carried through the two-column print:
  the verdict's move to `fitted` separated *"nothing was tried"* from *"everything succeeded"* in
  the **fitted** column, and the **eligible** column still reads `0/N = 0.0` — *"0% of the eligible
  domain failed"*, literally true and **a perfect score for a candidate that tried nothing**. That
  is the same false inference D1 was repaired to prevent, arriving in the report's own table. **The
  general form: a failure rate over the eligible domain is a coverage statement only when there are
  fits to judge.**
- Counts over all branches present sum to the cell count; **rates do not sum to 1** and the table
  says why.
- Every rate's denominator is a number in the record, beside it.
- The incompleteness `(N, M)` is a field, rendered beside every denominator (D6).

**Tests, each with the bug it must catch.**

- A constructed store with a planted histogram reproduces each count exactly, including
  `{OK: 809, DEGENERATE_HESSIAN: 91}` from the committed real-data spike — catches an off-by-one in
  the per-branch tally and ties the counter to a number already in the tree.
- A store containing `INSUFFICIENT_DATA` produces a failure rate whose denominator **includes** it —
  catches a regression to §8.6's rule, which is the whole of D2.
- A store containing `NOT_APPLICABLE` produces a denominator that **excludes** it — catches the
  collapse §12.5 says makes the failure rate uninterpretable.
- A store containing `NOT_ATTEMPTED` excludes it from every denominator while still **counting** it
  in the branch table — catches "excluded means missing", which would make an interrupted run's
  report silently describe a smaller grid.
- Two candidates with different eligible populations produce two different denominators — catches a
  shared denominator, which invites a comparison that is not available.
- **A store with land reports `failed/fitted` and `failed/eligible` differing, and an all-ocean
  store reports them equal** — catches a report that prints one denominator, which on a global run
  is a rate contaminated by land fraction and on this project's fixtures is indistinguishable from
  a correct one. The constructed store is criterion 12's: 12 ocean, 8 land, **1.00 against 0.60**.
- **A candidate screened out at every point reports BOTH columns unavailable, both naming "nothing
  fitted", with its eligible count printed as a count** — catches the eligible column reporting
  **0.0** for a candidate that was never tried, which reads as a clean pass and is the D1 collapse
  surviving into the report. The fixture is the one that surfaced it: an all-`SCREENED_OUT` plane,
  whose sibling candidate was fitted everywhere and passed, so the two must not print alike.
- **The caveat beside the eligible rate is present when the store records no domain mask and absent
  when it records one** — catches a hard-coded caveat, which is wrong the day after §13.6 lands,
  and a missing one, which is wrong today.

---

## Task 3 — the drop row, and 2e's criterion 14

**Behaviour.** `CANDIDATE_DROPPED` gets its own row, outside the failure rate, with its own
denominator named at the row (D11). The `early_abort` attrs are read for action, threshold, policy
and the coarse rates; when `out.pass1.zarr` is present beside the store, the rates are **recomputed
from its arrays and asserted to agree**; when it is absent the number is **labelled as carried**.

**This closes 2e's criterion 14**, which was met with reduced scope because the row was 2f's.

**Invariants.**

- The row's denominator is **never** the pass-2 population, where a dropped candidate is
  `CANDIDATE_DROPPED` at 100% and the rate reads ~100% — dominated by the decision already taken.
- A one-pass store (`early_abort.evaluated == false`, reason naming the one-pass run) and a
  `--no-early-abort` store print their own line, not an empty drop row.
- **A `no_evidence` verdict prints as itself** — a run that continued with its coarse sample unjudged
  — and is never folded into a clean pass.

**Tests, each with the bug it must catch.**

- A store from a real two-pass drop shows the row with the coarse denominator, and the recomputation
  from pass 1 agrees exactly — catches a row computed over pass 2, which is the ~100% reading §14.2
  names.
- The same store with `out.pass1.zarr` removed still prints the row, labelled carried — catches a
  report that fails on a store someone else shipped without its pass-1 sibling.
- A tampered `early_abort.rates[]` disagreeing with pass 1's arrays is **reported as a defect** —
  catches an assertion that trusts the carried record when the evidence is present to check it.
- A `no_evidence` store prints its own line and no clean-pass line — catches the collapse 2e's
  no-evidence decision was taken to prevent, reintroduced at the printing layer.
- A one-pass store prints neither a drop row nor a verdict rate — catches a report inventing a
  verdict a one-pass run cannot have reached.

---

## Task 4 — the primitives sections, and the run's resolved-candidate record

**Behaviour.** Two halves, and the first is a **write-path change made by the run, not the report**
(D12). `store.py` gains an additive root-attrs block recording, per candidate: label, spec hash,
resolved engine, cost class, gradient mode, objective — **and, beside it, a `domain_mask`
provenance field recording whether a declared domain mask was applied.**

**THE `domain_mask` FIELD IS WHAT MAKES THE ERA READABLE FROM THE STORE**, which the foreign-store
property requires: a reader of someone else's store has no other way to know which rule produced
it. **Absent or false**, `INSUFFICIENT_DATA` unions thin records and land, and Task 2's report says
so beside the eligible-denominator rate. **True**, the caveat drops. **A report that always prints
the caveat is wrong the day after §13.6 lands; one that never prints it is wrong today** — so it is
derived from the store rather than hard-coded. Absence is the answer for older stores, same rule as
the resolved-candidate block, and **nothing is back-filled**. The report prints it, and prints
*"not recorded by the run that wrote this store"* when the block is absent. The second half is
single-store computable and cheap: the `n_valid` distribution (§10.2), the iteration histogram from
`iterations[y,x,m]`, and the resolved config, all three hashes, profile name and calibration
provenance.

**Invariants.**

- **The block moves no hash** — asserted, not assumed (D12).
- **Nothing is back-filled.** An older store's silence is the answer.
- `n_valid`'s `-1` (unset) and `iterations`' `65535` (no fit ran) are excluded from their
  distributions and **counted separately**, because a fill value counted as a datum is the defect
  §12.5's fill table exists to prevent.

**Tests, each with the bug it must catch.**

- A store written before the block reports its absence and every other section still renders —
  catches a report that requires the newest writer, which breaks the foreign-store property.
- The three hashes of a store carrying the block equal those of the same config without it —
  catches the block reaching a hash payload, which would invalidate every existing store's resume.
- `n_valid == -1` and `iterations == 65535` appear in neither distribution — catches a histogram with
  a spike at the fill value, which reads as a real population.
- The recorded resolved engine differs from the run-level `engine` attr for a candidate whose
  capability intersection narrows it — catches a block that records the **request** rather than the
  **resolution**, which is the whole reason the bullet exists.

---

## Task 5 — selectability, the section §14.2 leads with

**Behaviour.** Three quantities, all stored or derivable, no schema change: **fits** from
`/selection/n_valid` (criterion-independent); **contention** as `count(isfinite(delta_ic))` over the
model axis, **per criterion**; **no winner** as `selected == -1`, per criterion. Denominators
excluding `NOT_APPLICABLE`, stated.

**This section leads the report**, per §14.2's 2026-09-12 amendment: the real-data spike measured
§11.2's hysteresis fear **absent** — zero re-ranked points in 289, positive-controlled — and measured
selectability differences **present**. A report leading with hysteresis would lead with the thing
this project has measured as not happening.

**Invariants.**

- **These are three facts, not one.** `n_valid` counts **fits**; contention counts **rankable** fits,
  and §10.2's rule makes them deliberately different — a fit can succeed and have no finite criterion
  value and is ranked last rather than reclassified. **So `n_valid == 1` is not "the selection was
  forced" and `n_valid == 0` is not "no survivor"**, and the report never says either.
- **`selected == -2` is `SELECTED_UNSET`** — *nothing wrote here* — and is never counted as a
  no-winner.
- `n_valid` is `int16` with `-1` for unset; a negative count is not a count.

**Tests, each with the bug it must catch.**

- A constructed point where every fit is `OK` and one criterion cannot rank it shows `n_valid`
  unchanged and contention lower **for that criterion only** — catches contention computed off
  `n_valid`, which is the conflation §14.2 devotes a paragraph to. §12.5 names the construction:
  under REML `n = n_obs − design_rank`, so `n_obs = 6` against a rank-4 design gives `n = 2`, HQIC
  undefined and AIC fine.
- A store with `selected == -2` somewhere reports it as unwritten, not as no-winner — catches
  `bool(-1)`-shaped identity-by-coincidence, which 2e's instrument finding 3 names.
- **The float32 caveat, as a constructed test**: a `delta_ic` finite in float64 that overflows to
  `inf` on write is counted **unrankable**, and the report states the caveat — catches a contention
  count quietly biased by the storage dtype, which §14.2 says is worth a test rather than a schema
  change.
- A point where eleven of twelve candidates failed the conditioning gate returns a selection and
  **every per-branch count reads clean**, while selectability shows the near-forced choice — catches
  the exact failure mode §14 names at its top, and is the reason this section exists.

---

## Task 6 — the clustering statistic and its null

**Behaviour.** Join-count (BB) on the binary failure indicator, rook adjacency in index space, over
the `is_fit_verdict` population (D3), per candidate with the aggregate as a second headline of a
different kind (D7), against a permutation null that holds the eligible mask fixed (D5). Reported as
raw count, null median and quantiles, z, and p — never a bare coefficient.

**Invariants.**

- **Map and statistic are computed over the same population** (D9's invariant).
- The three degenerate cases are **unavailable with their reason**, never a z of 0: no failures to
  arrange; every eligible point failing, so one arrangement exists; and no adjacent eligible pair, so
  adjacency is undefined on this mask.
- **Below 500 eligible points the statistic is unavailable and names the floor** — measured by
  P5-prime with a detector that fired on the known-degenerate case first. **500 is a LADDER RUNG,
  not a boundary**: 200 failed and 500 passed, so the true threshold lies in **(200, 500]** and 500
  is *the smallest tested size demonstrated uniform*. The invariant says it that way, or a later
  reader takes it for a measured threshold with a precision it does not have.
- The seed and the permutation count are in the record.
- **Where the two-arm zone fires, BOTH arms are printed in full** — `z` and `p` each, labelled,
  detected arm marked as reported — so the global case is self-auditing per store and needs no
  external calibration to interpret. **Δz never stands in for the pair** (D4).
- **Where it does not fire, the report prints the span it found** — *"22.5° of 360°, not global,
  not wrapped"* — so the not-global branch is a measurement rather than a policy.
- **All M per-candidate z-scores are printed**, and any single headline is labelled "max over M
  candidates, uncorrected" at the number (D7).

**Task 6's exit includes adding `CLUSTERING_SEED` to the handoff's do-not-move list.** D5 says the
seed "joins" that list; the list is enumerated in the standing requirements and **cannot contain a
constant that does not exist yet**, so until this task lands, "joins" is a promise with no owner.
The task is not done until the constant is on the list.

**Tests, each with the bug it must catch.**

- A planted contiguous patch rejects and a Bernoulli field does not, on the same failure count —
  catches a statistic measuring the **rate** rather than the **arrangement**, which is the null
  choice D5 exists to make.
- A store whose failures are confined to one candidate shows that candidate clustered and the
  aggregate clean — catches an aggregate-only statistic, which is why (b) was refused, and it fails
  on the `OK`-if-any rule directly.
- A checkerboard eligible mask returns unavailable naming zero edges — catches a graph built without
  checking it has any, which would divide by zero or return a spurious z.
- A candidate with zero failures returns unavailable naming *no failures to arrange* — catches a z of
  0 reading as "no clustering found", which is (a2b).
- The same seed gives an identical z twice and a different seed gives a z within the null's own SE —
  catches an unseeded null, which makes every reported p irreproducible.
- `NOT_APPLICABLE`, `CANDIDATE_DROPPED`, `SCREENED_OUT` and `NOT_ATTEMPTED` cells are all absent from
  the graph — catches the graph built on `is_eligible`, under which a dropped candidate's 100%
  coverage is a perfect cluster.

---

## Task 7 — the maps, the `[report]` extra, and the no-matplotlib path

**Behaviour.** One PNG per (branch present × candidate) plus one per branch for the point-level
aggregate; the value at a downsampled block is the **fraction** of that block's cells carrying the
code (D9). `viridis`; fixed code-to-colour; legend from the store's own `flag_meanings`. matplotlib
behind `[report]`, imported inside the function (D10).

**Invariants.**

- **No arithmetic is ever applied to outcome codes.** The reduction is over a binary indicator.
- Without matplotlib the report emits **every number** and states in the report file that maps were
  not drawn and which extra draws them.
- The map's population matches the statistic's.

**Tests, each with the bug it must catch.**

- Downsampling a block of mixed codes produces a fraction in [0, 1] per branch and **never a code** —
  catches the mean-of-codes defect directly: `mean(7, 11) == 9 == CANDIDATE_DROPPED`, a real,
  different, valid-looking code.
- With matplotlib made unimportable the report exits 0, emits the JSON and markdown, and names the
  extra — catches a hard dependency smuggled in, which is D10's receipt.
- The set of maps equals the set of (branch present × candidate) pairs the statistic covers —
  catches map and statistic drifting onto different populations.
- **Every fraction map's colourbar limits are exactly 0 and 1, whatever the observed range** —
  catches matplotlib's autoscale, under which a branch present at 0.01–0.03 everywhere renders
  full-range and 3% looks like 100%, and two stores with different ranges are not comparable. The
  test asserts the limits, not the image.
- The map's title names the branch from the store's own `flag_meanings` — catches a title written
  from a hard-coded name table, which drifts from the store's alphabet.

---

## Task 8 — the entry point, the exit codes, and render-from-record

**Behaviour.** `python -m metamer.report <store>` writes markdown, JSON and PNGs beside the store, or
to `--out <dir>`. **Writability is checked up front**, before the permutation null runs. The markdown
is **rendered from the JSON record**, on `bench/report.py`'s precedent, so "the same numbers as JSON"
is structural rather than promised.

**Invariants.**

- Exit codes per D13, with 1 and 2 not producible and the reason recorded.
- No write to the store, asserted byte-for-byte.
- Every number in the markdown exists in the record.

**Tests, each with the bug it must catch.**

- **The full report runs against a store directory with write permission removed, and exits 0** —
  this is the read-only guarantee's *mechanism* rather than a sample of its consequences. The byte
  comparison catches a write that changes bytes **on the one path the test exercised**; it does not
  catch an attrs write of identical content, a rewrite with reordered JSON keys, a write to a
  sibling path, a write on a path the test did not run (matplotlib-absent, incomplete-store), or a
  write rolled back on error. A store that **raises** on any write catches all of them, on every
  path, for free — and Task 1 already carries "opened read-only" as an invariant, so this turns the
  invariant into a mechanism. **A fixture precondition that refuses to run beats an assertion that
  passes**, which is this project's own rule and was not applied here until review.
- Running the report leaves the store **byte-for-byte identical** — kept as the cheap **positive
  control** for the permission test: it proves the report ran and wrote its output somewhere, so a
  green permission test cannot be a report that silently did nothing.
- An unwritable output directory fails **before** the statistic runs — catches a report that computes
  for minutes and then cannot save, which is the one failure that wastes the user's time entirely.
- A usage error exits 3 and an unreadable store exits 4 — catches the two collapsing into 5, which
  tells a script the report is broken when the input is.
- Every numeric token in the markdown appears in the JSON — catches a rendered number computed at
  render time, which is how two artifacts of one run come to disagree.
- The report runs on a store built by a **different** process with no config present — catches any
  dependence on the config, which is the foreign-store property.

---

## Task 9 — open question 23's capability

**Behaviour.** One flag computes the per-branch statistic and the per-branch-per-candidate maps,
documented as *"compute this when asking open question 23's question"*, and prints its own
multiple-comparison caveat (D8).

**Invariants.** Off by default. The caveat is printed by the capability, not left to the reader. **It
does not reason about why a member fires** — 2e's contribution to OQ23 was deliberately negative and
2f's is an instrument, not a story. Why the condition number moves is **not established**.

**Tests.** The flag produces a statistic per branch present and the caveat text; without it neither
appears — catches a capability that leaks into the default report, which would owe a correction on
every run.

---

## Task 10 — the 2f exit-criteria suite

`tests/exit_criteria_2f.py` and `tests/test_exit_criteria_2f.py`, in 2e's shape: **every criterion
names its reading**, names the tests that establish it, and names what it is driven from or why no
outside exists. The binding test takes readings from somewhere the implementing task's test did not.

**And it does not reuse 2e's criterion-9 helper**, whose reach is keyed on one spelling
(`outcome_counts`) and one extension (`.json`) and reaches 8 of the 16 committed histograms. OQ24's
check was written independently for that reason.

**WHICH LEAVES TWO NEAR-IDENTICAL READERS, SO THIS TASK STATES WHICH IS AUTHORITATIVE RATHER THAN
LEAVING THE NEXT PHASE A COIN FLIP.** **2f's scanner is authoritative for every future phase**: it
enumerates by a rule, is spelling-independent and extension-independent, and covers the whole
artifact population. **2e's helper is frozen as the reader of 2e's frozen artifacts** — it is the
instrument that produced a closed criterion's evidence and rewriting it would rewrite that
evidence. It gains a one-line docstring saying exactly that, and pointing here.

---

## Exit criteria

| # | criterion | reading |
|---|---|---|
| 1 | `python -m metamer.report <store>` produces a report from a store with no config present | the exit code, and the report file's existence and section set |
| 2 | The report never writes to the store | the store's bytes, before and after |
| 3 | `metamer.report`'s import graph excludes matplotlib and the fit path | the subprocess's `sys.modules`, by name — **read after `read_store` has been IMPORTED AND CALLED on a store built by the parent, never after `import metamer.report` alone. THE EVIDENCE FOR THIS CRITERION WAS VACUOUS FROM `3f04f68` UNTIL THE FOLLOW-UP COMMIT**: `metamer/report/__init__.py` is docstring-only, so the probe stopped at 65 modules having reached neither the reader nor zarr, *"no forbidden module"* was true because nothing had been imported, and the ceiling beside it — 900, cited from another subject — would have **failed** against the real 933. A positive control proves the detector; it cannot show what the detector is aimed at. **And the residual limit is part of the reading**: a `sys.modules` check cannot see a lazy import by construction, which is exactly what D10's maps design requires, so this criterion gives both answers for an import-time violation and only one for a run-time one |
| 4 | The failure-rate denominator includes `INSUFFICIENT_DATA` and excludes `NOT_APPLICABLE` | the denominator on a store constructed to contain both |
| 5 | No committed artifact's rate moved under D2, over an enumeration that re-derives itself | **the enumeration first** — a spelling-independent glob over the artifact directories yielding exactly sixteen histograms across the five named families — **then** those sixteen and the one eligibility-derived denominator, recomputed |
| 6 | `no_evidence` reads whether anything was fitted | the verdict on an all-`SCREENED_OUT` coarse store, against the same store all-`INSUFFICIENT_DATA` |
| 7 | Every rate carries its own denominator | the record's fields, per row |
| 8 | The drop row is outside the failure rate and names the coarse population | the row and its denominator, on a real two-pass drop |
| 9 | The drop row survives a missing pass-1 store, labelled carried | the row, with the sibling removed |
| 10 | Selectability's three quantities are three facts | `n_valid`, contention and no-winner on a point where every fit is `OK` and one criterion cannot rank it |
| 11 | A float32 overflow is counted unrankable and the caveat is stated | the contention count, and the report's text |
| 12 | The clustering statistic measures arrangement, not rate | the two stores of equal failure count, planted and Bernoulli |
| 13 | The adjacency graph excludes every non-fit code | the graph's node count against `is_fit_verdict` on a store carrying all four |
| 14 | Degenerate cases are unavailable with their reason | the three constructed masks, each naming its own reason |
| 15 | The null is reproducible from its recorded seed | two runs' z, and the seed in the record |
| 16 | Maps and statistic cover the same population | the two sets, compared |
| 17 | No arithmetic reaches an outcome code | the downsampled block's values against the code space |
| 18 | The report runs without matplotlib and says so | the exit code, the JSON, and the report's own sentence |
| 19 | An unfinished store is described, not refused | `(N, M)` in the record, the exit code, and a denominator beside a rate |
| 20 | Completeness comes from the bitmap | a store whose bitmap and outcomes disagree, reported as a defect |
| 21 | The run records the resolved candidate table and it moves no hash | the block, and the three hashes with and without it, **plus `tests/test_hashing.py::test_compat_relevance_is_an_allowlist_golden_set`, cited by name.** That test is the standing guard against the defect this criterion cannot reach on its own: a later change promoting a resolved field INTO the config namespace, where it enters a payload legitimately, moves `compat_hash`, and invalidates every stored run's resume by an edit nobody thought was semantic. **Its reach covers all three payloads, checked 2026-09-19 and stated here because its NAME reads narrower than its subject — there are only TWO allowlists.** `fit_payload` subsets `FIT_RELEVANT_FIELDS`; `compat_payload` subsets `COMPAT_RELEVANT_FIELDS`, which the same test pins through `COMPAT == FIT | {"criteria"}` and `FIT < COMPAT`; `run_payload` is `normalize(config)` entire, with **no allowlist by design** — provenance only, never a gate — so there is no third set to pin, and its `_subset` call is a validation whose result is discarded. **And because it hashes everything, a resolved field promoted into the config namespace would move `run_hash` BEFORE it reached either allowlist**, which strengthens the guard rather than evading it. No new test is owed. |
| 22 | A report's exit code describes the report | the codes produced across usage, unreadable-store and internal-error cases, and 1 and 2 absent |
| 23 | The markdown is rendered from the record | every numeric token in the markdown, found in the JSON |

---

## What 2f does not settle

- **Open question 23** gets an instrument and no story. Why `cond(H)` moves is not established, and
  its closer is unchanged: measure `cond(H)`'s own scatter at a fixed θ̂ reached by two paths before
  touching `HESSIAN_COND_LIMIT`. The repair is not a wider limit.
- **Open question 20's second half** — coordinate monotonic direction — stays open and unowned.
- **Open question 22's repair** is unowned unless Task 0's P1 refutes its prediction.
- **The standing geographic limitation.** Every real-data number in this project is one box of
  subtropical open ocean — no land, no ice, no gaps. A saving there is a saving there, and no report
  produced from it is evidence about a global run.
