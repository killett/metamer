# Wiring one — pre-flight (2026-09-11)

**A driver that runs `batch.audit` over a rung's arms.** The brief is
[`PROGRESS.md`'s WIRING ONE section](../../../PROGRESS.md), the machinery is 2c's
`batch.audit` / `batch.audit_report`, the population is 2d's `bench.report.run_rung`, and the
urgency is the real-data spike's second half. **Nothing from the two spike verdicts, from 2c's
D7–D12 or from §11.2 is restated here.**

**Written before any code.** Run against the brief per the standing rule, (a0)–(a9) and (a)–(k).

The state it was written against: branch `main`, working tree clean, **1388 tests collected**, the
tip (`49e71bf`, docs-only) with a run **in flight** at the time of writing.

---

## W1 — CRITERION 12's REMINDER IS WRITTEN AGAINST TOP-LEVEL KEYS ONLY, SO THIS WIRING CAN LAND WITHOUT FIRING IT

The brief's claim is that *"its test fails the day a committed report carries a stratum — which is
exactly when the criterion should be re-evaluated."* **The test does not check what that sentence
says.** `test_criterion_12_no_committed_report_carries_a_stratum` reads a committed report and
asserts:

```python
assert "strata" not in committed
assert not any("stratum" in key or "strata" in key for key in committed)
```

`for key in committed` iterates the **top level** of the JSON. The report's top level is
`rung / contaminated / null_line / smears / instrument / iterations / ratios / checks` (+ `cost` on
the difficulty rung). **A stratified reading landed under `checks`, under `instrument`, or under a
top-level key called `audit`, `hysteresis` or `disagreement` passes this assertion unchanged** —
and the reduced scope it guards would go stale silently, which is the exact failure the test was
written to prevent.

**This is (c5) at a guard: written against the members that existed rather than against the set.**
It is also (a0)'s sixth register one level up — a check that never reached the nesting prints the
same word as one that did.

**RESOLUTION, AND IT IS DELIBERATE RATHER THAN CONVENIENT.** Two things, both:

1. **The driver's top-level key is `strata`.** Not `audit`, not `hysteresis`. The guard was
   designed to fire on that word and the cheapest way to keep a designed guard honest is to not
   route around it.
2. **The guard is widened to walk the document**, not the top level, in the same commit that
   re-evaluates criterion 12 — because a guard that only ever worked by the caller's courtesy is
   not a guard. Widening it is not loosening it: it can only make the absence assertion stricter.

**Do not widen it and leave the wiring for later.** A widened guard over unchanged reports still
passes, so the two can be separated — but then the record carries a guard nobody has seen fail,
which is (e) at the guard itself. **Prove the widened guard fails on a report carrying a nested
stratum before recording it as a guard.**

---

## W2 — THE RUNG REPORT'S NUMBERS CARRY A RUNG BY CONSTRUCTION AND THE AUDIT'S DO NOT

`bench.report.RungQuantity` subclasses `batch.audit_report.Quantity` and adds a required `rung`
field, and 2d's exit criterion 13 — *"a number without a rung cannot be constructed"* — is
established by `test_a_quantity_without_a_rung_cannot_be_constructed` and
`test_every_quantity_on_a_report_carries_the_rung_it_was_measured_on`. **`audit_report` emits plain
`Quantity`.** Every per-stratum rate, mean and maximum it produces has a scope and no rung.

**So the wiring puts E1's constraint 2 and D8's construction in direct collision**, and it does it
at the only place the two record systems touch. It is (h4): a rule stated over *"every emitted
number"* checked against each KIND of number, and the audit's kind was never in view when the rule
was written.

**THE OPTION THAT LOOKS CHEAPEST IS THE ONE TO REFUSE.** Serialising the audit report's quantities
into the rung report as plain dicts satisfies every current test — `RungReport.quantities()` walks
`self.smears` and nothing else, so it would not even see them — and ships a report in which some
numbers carry their rung by construction and some carry it by the fact that they happen to be
inside a file that names one. **That is precisely the "labelled, not constructed" position D8
rejects**, restated one level out.

**RESOLUTION.** One adapter, in `bench.report`, that lifts a `Quantity` into a `RungQuantity` for
the rung it was measured on, applied to **every** quantity `AuditReport.quantities()` returns, and
`RungReport.quantities()` / `.withheld()` extended to walk the lifted set as well as `smears`. Two
properties to test in both directions:

- every number reachable from a `RungReport` is a `RungQuantity` — including the withheld ones,
  because a withheld quantity is an object and D8's visibility argument covers it;
- the lift is **total**: a quantity added to `AuditReport` later cannot reach a rung report
  unlifted. Written against `AuditReport.quantities()` rather than against an enumeration of the
  strata kinds — (c5), the rule W1 is about, applied where it was learned.

**AND THE LIFT MUST NOT RE-STATE THE SCOPE.** `Quantity.__post_init__` already refuses a scopeless
quantity; the lift adds a field and changes nothing else. Folding the rung into the scope string
instead would be the second spelling of one validator that `RungQuantity`'s own docstring was
written to prevent.

---

## W3 — THE `κ` STRATA ARE NOT LIVE, AND THE BRIEF SAYS THEY ARE. REPORTED AS A DEFECT

The brief's second addition reads: ***"`κ` NOW HAS LIVE STRATA AND THEY ARE START-DEPENDENT, SO
(j7)'s COLD-ARM BINDING IS DOING REAL WORK FOR THE FIRST TIME."***

**That disagrees with three committed records, all of which agree with each other:**

| record | what it says |
|---|---|
| (h3), in the handoff | `HESSIAN_COND_LIMIT` **is** `2²⁶`, which **is** D9's first `κ` boundary, by the same derivation |
| 2c exit criterion 11's scope | the binning is met and **the axis is degenerate on the population it stratifies** — 8 live cells, all in the first bin, 2026-08-29 |
| open question 23's own closing note | *"(h3)'s conclusion still holds"* — the upper bins stay unreachable |

A cell above `HESSIAN_COND_LIMIT` reports `DEGENERATE_HESSIAN`, is not `OK`, and therefore is not
in the both-OK intersection the strata are computed over. **`_both_ok` reads `COLD` and `WARM`
only, and `kappa_bin` reads the cold arm's `hessian_cond`.** So on the population the report
covers, the reachable bins are `kappa_lt_2^26`, `kappa_undefined`, and `kappa_2^26_to_2^52` by
exact equality alone. **Two arms moving their median `κ` does not make a second bin reachable**;
it moves cells **out of the population entirely.**

**SO THE (j7) CHECK THE BRIEF ASKS FOR IS OWED, AND IT IS A DIFFERENT CHECK THAN THE ONE IT
NAMES.** Binning by the cold arm cannot be wrong about bin assignment here, because there is one
bin. What the treatment moves is **membership**, and a selection effect the treatment can move is
(j7) at the population rather than at a stratum — which is what OQ23's own closing paragraph
already says and what the brief's phrasing loses.

**RESOLUTION.** The report states the degeneracy on its own output rather than leaving a reader to
infer it from an empty bin, and it states the thing that actually moves:

- `unreachable_kappa_bins` already ships beside the boundaries — **keep it, and do not read a
  populated single bin as the axis working.**
- **Report the per-arm `DEGENERATE_HESSIAN` count and the size of the both-OK intersection beside
  the strata**, at the same granularity as the strata, so *"which cells were in the population"* is
  on the same page as *"what the population did"*. `CandidateOutcomes` already carries
  `attempted / cold_ok / cold_failed / both_ok / both_ok_fraction` per candidate and its
  `both_ok_fraction < 1.0` note already fires — **that is the start-dependence surface, and it
  exists.** The wiring's job is to make sure it is emitted and read, not to build it.
- **No second binning is added.** A second reported binning by the warm arm's `κ` would be
  conditioning on a post-treatment variable to check whether conditioning on a post-treatment
  variable matters — (j) at the oracle. The check is the membership count, not a rebinning.

---

## W4 — THE POOLED QUANTITY IS `PointStratum.selection_disagreement`, AND THAT IS THE WHOLE DEFECT, NAMED AT ITS LINE

`_point_strata` computes `disagree = both & (cold_best != warm_best)` and reports it as
`selection_disagreement` per `margin × winner` stratum. **On the real-data population that rate is
100% outcome flip and 0% re-ranking**, so the number §11.2 calls *"most directly about the
smoothness artifact"* would contain none of the artifact. D9 already separates the two quantities
and gives them their own denominators; nothing prints the separation because nothing prints
anything.

**RESOLUTION — THE DECOMPOSITION ATTACHES AT THE POINT GRANULARITY, WHICH IS THE ONE IT HAS.**
(h2): a metric may only be stratified by axes defined at its own granularity, and move/dropout is a
property of a **point** — it asks whether each arm's winner was `OK` in the other arm. So it
belongs beside `selection_disagreement` in `PointStratum`, under the same `margin × winner`
stratification, with its own denominators:

| quantity | numerator | denominator |
|---|---|---|
| `selection_disagreement` | points where the winners differ | stratum members, both ranked |
| `selection_move` | differing points where **both** winners were `OK` in **both** arms | stratum members, both ranked |
| `selection_dropout` | differing points where **exactly one** arm's winner was not `OK` in the other | stratum members, both ranked |
| `selection_both_unavailable` | differing points where **neither** winner was available in the other | stratum members, both ranked |

**Four quantities over one denominator, and the last three sum to the first.** That identity is a
test, not a comment (see T6).

**THE RULE IS `decompose()`'s, MOVED AND NOT REWRITTEN.** It is committed, it ran, and it produced
the spike's reading. Three specific properties of it that a rewrite would lose and that the port
must keep:

- **a point can be neither a move nor a dropout**, and those are counted separately rather than
  assigned to whichever bin is tested first;
- **`live = (cold_sel >= 0) & (other_sel >= 0)`** — `-1` compares unequal to everything, and a
  decomposition without the membership mask calls every unranked point a disagreement. This is the
  same trap `_point_strata`'s deliberately-redundant `both &` is documented against; the two must
  agree, and T5 asserts they do rather than trusting that they will.
- **it reads `outcome` and `ranking.best_index` and nothing else**, which is what lets the positive
  control fabricate a pair without running a fit.

**AND THE POOLED RATE IS NOT DELETED.** D8's rule is that no figure exists over everything; it
never said the flip rate is wrong. It is wrong **alone**. `selection_disagreement` stays, per
stratum, with the three components beside it in the same object so that the four travel together
the way the spike's four readings do.

---

## W5 — THE DRIVER'S POPULATION IS SIMULATED, AND THE POPULATION THAT MADE POOLING WRONG IS REAL

The brief's urgency is real-altimetry: 100% flip, 0% re-ranking, ~10% of cells `DEGENERATE_HESSIAN`
and which 10% depends on the start. **`run_rung` fits `bench.fields`' constructed field**, where
the same outcome was 1 cell in 1152.

**So the most likely reading this wiring produces is a near-empty differing population and a
decomposition of almost nothing** — and every rate over it withheld by the 30-member floor. That is
a correct result and it is not a refutation of the brief. **It must be predicted before the run
rather than explained after it** (P1–P5 below), because the alternative is a session that measures
a null on a simulated field and reads it as *"the decomposition finds no dropouts"*.

**AND IT IS THE STANDING LIMITATION ONE TURN ON.** The limitation is no longer *simulated versus
real* and no longer only *geographic*: it is that **the instrument is now being validated on the
population where the effect is smallest.** That is (i7) — a fixture placed where the two functions
agree — and it is acceptable here **only because the purpose of this run is to exercise the
machinery, not to measure the effect.** The report must say so in its own bytes, not in a commit
message.

---

## W6 — THE POSITIVE CONTROL RUNS BEFORE THE GATE, AND IN THE SHIPPED PATH THERE IS NO GATE

The brief: *"with its positive control running before the quiet gate on every invocation."*

**`run_rung` has no quiet gate.** `host.quiet_check()` is called by the harnesses under
`docs/superpowers/notes/`, and `phase2d-easy-rung-harness.py` calls it **first**, before the wiring
smoke and before any fit. The decomposition addendum's own `main()` is the shape the brief means:
`selftest()` is emitted **before** `host.quiet_check()`, with the comment *"before the gate,
because it costs nothing and gates everything."*

**Two separate obligations, and satisfying one does not satisfy the other:**

1. **In the harness** — `selftest()` is the first record emitted, before the gate reading. A
   control that runs only after the gate passes does not run on a refused invocation, and a refused
   invocation is the cheapest opportunity to discover the rule is broken.
2. **In the shipped code path** — `run_rung` is **not in `pixi run test`** (E7), so a unit test of
   the decomposition rule does not execute in the process that produces the committed number.
   **The driver therefore runs the control itself and refuses on failure**, in-process, before the
   arms are fitted. It costs microseconds: three fabricated points, no fit.

**A unit test is also written, and it is not a substitute for either.** (i2): `MOVE = 0` and *"the
rule cannot see a move"* are the same integer, and the reading that is comfortable is the one that
needs the control.

---

## W7 — `lint_findings` CANNOT BE BUILT FROM THE FUNCTION `audit_report`'s DOCSTRING NAMES

`audit_report(..., lint_findings=)` wants `Mapping[str, Sequence[str]]` — `spec_hash` → the rules
that fired — and its docstring sources it *"from `validation.identifiability_warnings`' own `lint`
calls."* **`identifiability_warnings` returns `tuple[Finding, ...]`, flattened across candidates**,
and `Finding` carries `rule`, `terms` and `message` and **no candidate identity**. The mapping is
not reconstructible from its return value. (g): a call checked against the module's current
signature.

**RESOLUTION.** The driver calls `core.lint.lint(spec, sampling_interval)` per spec — which is what
`identifiability_warnings` itself does — and keys the result by `spec.spec_hash()`. No change to
`validation`; the docstring's provenance sentence is accurate about the *rule source* and wrong
about the *call*, and is corrected to name `lint`.

**THE SAMPLING INTERVAL IS `ContractReport.median_dt` AND NOT A RECOMPUTED MEDIAN.** `input.py`
states it explicitly: the lint's interval is that number, the **median of realized gaps**, not
`(t_end - t_start) / n_time`, which is off by `(n-1)/n` on a regular axis and silently wrong on a
gapped one. It is not persisted in the store — `run` computes it, uses it and drops it — so the
driver obtains it from `check_input_contract` on the same handle, the shipped function, one
construction.

**AND `None` IS A REAL OPTION, WITH A REAL COST.** Passing `lint_findings=None` makes the report
print *"the lint was NOT run … that is not the same as clean."* That is honest and it is cheap.
**It is refused anyway**, because §11.2 names the lint as the cheap way to know whether the
label-switching confound is even present, and the bench candidate set is three fixed specs: the
answer is discoverable once, permanently, for the cost of three calls. Shipping the note instead
would be choosing the caveat over the measurement — (a2b) inverted.

---

## W8 — `trend_column` COMES FROM THE SHIPPED CONSTRUCTION, AND THE FAILURE MODE IS NAMED

`audit_report` takes `trend_column` rather than deriving it, *"because building a second
`DesignInfo` here would be a second derivation of which column the trend is, and the failure mode
is a seasonal amplitude reported as a trend."* `fit` gets it from `signal.design_info(t, mask)`.

**The driver calls that same method on the same `signal`, `t` and `mask` the arms were fitted
under.** That is one construction used twice, not two constructions. The thing to refuse is
`trend_column = 1` or any index arithmetic — `core/fit.py`'s own docstring records that assuming
index 1 holds only for a particular design.

Signed-trend disagreement is §11.2's *"actual scientific payload"*. If the bench signal has no
trend column the report says so per stratum, and that is a property of the signal spec rather than
a measurement of zero — already implemented, already noted. **T8 asserts the column is found for
the shipped bench signal**, because *"absent for a good reason"* and *"absent because the lookup
broke"* print identically.

---

## W9 — THE WIRING IS FREE AND CLOSING CRITERION 12 IS NOT: THE COST IS A RUNG RE-RUN

**`run_rung` already fits the arms.** `n2map.field_arms` returns `FieldArms.arms`, a full
`AuditArms` over every point of the field, and `run_rung` already keeps all four because *"returning
only the N2 map means paying for three full-field arms and discarding them."* **`audit_report` over
those arms is arithmetic over arrays that are already in memory.** The strata cost nothing.

**What costs is producing a COMMITTED report that carries them**, because criterion 12 is asserted
over `COMMITTED_REPORTS`, and those are the easy and difficulty rung artifacts. Re-running a rung is
the price, and the easy rung's measured total is in
[`phase2d-easy-rung-verdict.md`](phase2d-easy-rung-verdict.md)'s cost table — **10.18 h**, against
an E2 budget that the same verdict records as **already over its ceiling at three rungs**.

**SO IT IS A SCOPE DECISION AND IT IS REPORTED RATHER THAN ABSORBED.** The ordering that costs
least:

1. **Wire it and validate on the smoke geometry** — 26 × 2, `n_time = 24`, `is_a_smoke_run: true`,
   both gate branches already exercised there. A smoke report is **not** in `COMMITTED_REPORTS`, so
   this proves the path end to end **without** closing criterion 12 and without firing its
   reminder. That is the right order: the reminder should fire on a real reading.
2. **Then decide** whether the easy rung is re-run. That decision belongs to whoever owns the
   budget, with the 10.18 h and the current ceiling in view. **This session does not take it
   silently by starting a rung.**

**The quiet gate's measured cost (OQ22) applies to step 2 and not to step 1**: a rung run is
gated, refused on a loud host, and the refusals have cost roughly a working day before. The repair
is named at OQ22 and is **not** taken here — validating a gate repair against known-good and
known-bad is its own task, and taking it in the session it would have convenienced is how a gate
becomes a formality.

---

## W10 — THE STRATA ARE DETERMINISTIC, SO THEY GO INSIDE `reproducible()`

`RungReport.reproducible()` is *"everything this run determines, with the wall clock left out"*,
and its docstring names N2 as the one place §11.3's traversal independence can still be lost.

**The audit report's numbers read the `COLD` and `WARM` arms only** — `_both_ok`, `kappa_bin`,
`abs_delta_loglik`, `parameter_distance`, `signed_trend_difference`, `_point_strata` and
`_candidate_outcomes` every one of them. **No N2 direction enters any stratum**, so the strata
carry no randomness at all, keyed or otherwise. They are on the deterministic side of the line and
belong in `reproducible()`, where two runs of one rung must agree byte for byte.

`seed` is already on `AuditReport` and stays, as a record of what the arms were keyed on, not
because a stratum depends on it.

---

## W11 — CI AND THE ONE-PUSH-PER-RUN RULE, WHICH IS THE ONE THAT HAS BROKEN THREE TIMES

The tip's run was **in flight** when this was written. The rule that has broken three times is
*commit again before the previous run is green*, and the mechanism is the post-commit hook
publishing instantly. **This pre-flight is not committed until the tip's run is green**, and every
subsequent commit in this session waits the same way. Verified by `headSha` with conclusions, never
by position.

---

## W12 — THE FOUR READINGS TRAVEL TOGETHER, AND A DRIVER IS A PLACE THEY CAN COME APART

The spike's four readings *"only make sense together"*: the saving, the geometry's 6.7% share of
it, zero re-rankings, and 34% of points selecting differently by conditioning alone. A reader
taking the first alone ships the two-pass architecture.

**A per-stratum report that prints a saving beside a decomposition is exactly where the first
reading can be taken alone.** The rung report already carries `saving_pass2_only` and
`saving_net_of_pass1` in `ratios`. **The decomposition must not be filed as a footnote to them.**
Nothing in this wiring quotes a saving without its selection consequence in the same object, and
the standing limitation of W5 is on the report itself.

**And the audit is not licensed away by a clean result.** §11.2's inserted block already says it:
one clean box of subtropical open ocean does not license deleting the detector, and a simulated
rung licenses even less.

---

# THE TEST PLAN

**Presented before any test code.** Each line names the bug it catches; expected values are
determined independently of the implementation. Anything without such a sentence is not on the
list.

| # | test | behaviour under test | expected value, determined independently | bug it catches |
|---|---|---|---|---|
| **T1** | `test_a_nested_stratum_is_found_by_the_committed_report_guard` | the widened criterion-12 guard walks the document, not the top level | a hand-built dict with `{"checks": {"point_strata": [...]}}` must be refused; the two currently-committed reports must still pass | **W1.** The guard passing over a report that carries strata three levels down — the reduced scope going stale invisibly, which is the precise thing the original assertion exists to prevent |
| **T2** | `test_every_number_a_rung_report_can_reach_carries_its_rung` | `quantities()` and `withheld()` over a report **with** an audit section return only `RungQuantity` | build a report carrying both a smear and an audit section; every returned object's type is checked, not its fields | **W2.** An audit quantity reaching a reader with a scope and no rung — E1's constraint 2 holding for one kind of number and not the other, (h4) |
| **T3** | `test_a_quantity_added_to_the_audit_report_cannot_reach_a_rung_report_unlifted` | the lift is written against `AuditReport.quantities()`, not against an enumeration of stratum kinds | a stub `AuditReport` whose `quantities()` yields one extra quantity the lift was never told about; it must still arrive lifted | **W2/(c5).** A gate written against the members that existed — the defect W1 is itself an instance of |
| **T4** | `test_the_decomposition_separates_a_move_from_a_dropout_on_a_fabricated_pair` | the ported rule reports `move = 1, dropout = 1` on the committed three-point construction | the counts are the addendum's own, and the construction is copied from `selftest()` rather than re-invented | **W6/(i2).** The pure negative: a rule that cannot report a move, whose `MOVE = 0` is indistinguishable from a true zero |
| **T5** | `test_an_unranked_point_is_not_a_disagreement_and_is_not_a_dropout` | `best_index == -1` in either arm excludes the point from all four point quantities | a fixture with one arm unranked at a point; the stratum's members and all four numerators exclude it | **W4.** `-1` comparing unequal to everything — the trap `_point_strata`'s redundant `both &` is documented against, re-entering through the decomposition that did not inherit the comment |
| **T6** | `test_the_three_components_sum_to_the_selection_disagreement_in_every_stratum` | move + dropout + both-unavailable == differing, per stratum, including empty ones | arithmetic identity over a constructed set with all three kinds present in one stratum | **W4.** A point silently assigned to two bins, or to none — the decomposition and the pooled rate drifting apart while both look plausible |
| **T7** | `test_a_stratum_below_the_floor_withholds_all_four_and_reports_the_count` | the 30-member floor covers the three new quantities exactly as it covers the old one | 29 members withholds, 30 reports — the boundary, both sides, on each of the four | **W4.** A new rate shipped past the floor because the floor was applied where it was written rather than to the kind of quantity it governs — (h4) again, at `MIN_STRATUM_MEMBERS` |
| **T8** | `test_the_bench_signal_has_a_trend_column_and_the_driver_finds_it` | `signal.design_info(t, mask).trend_column` is not None for the shipped bench signal, and the driver passes that value | the column is located by name in `column_terms`, never by index | **W8.** A signed-trend metric silently unavailable on every stratum, reported as a property of the signal spec when it is a broken lookup — the two print identically |
| **T9** | `test_the_lint_mapping_is_keyed_by_spec_hash_and_covers_every_candidate` | the driver's mapping has one entry per candidate, keyed by `spec_hash()` | the three bench candidates' hashes, computed from the specs in the test | **W7.** A mapping built from `identifiability_warnings`' flat tuple — findings attributed to the wrong candidate, or every candidate reading clean because the mapping is empty |
| **T10** | `test_the_report_states_the_kappa_axis_is_degenerate_on_its_own_population` | `unreachable_kappa_bins` and the intersection sizes are present on the emitted rung report | the two unreachable bins are `KappaBin.HALF_PRECISION` and `KappaBin.SINGULAR`, from `HESSIAN_COND_LIMIT == 2**26` | **W3.** A single populated `κ` bin read as the stratification working, and a start-dependent population change read as a stratum effect |
| **T11** | `test_the_driver_refuses_when_its_own_positive_control_fails` | the in-process control gates the run, and its failure is a refusal rather than a warning | monkeypatch the rule to return `move = 0` on the fabricated pair; the driver must raise/refuse before fitting | **W6.** A control that runs, fails and is logged — the arms fitted anyway and a `MOVE = 0` recorded from an instrument already known to be broken |
| **T12** | `test_the_audit_section_is_inside_the_reproducible_record_and_the_cost_is_not` | `reproducible()` contains the strata and contains no seconds | key membership, asserted both ways | **W10.** Wall clock entering the byte-for-byte comparison, or the strata being left out of it and two runs agreeing while their strata differ |

**Not on the list, and why.** A test that the strata *values* equal particular numbers on the
smoke geometry: the smoke run is `is_a_smoke_run: true` and Task 9's rule already refuses a report
carrying that flag as evidence for any criterion. Asserting its magnitudes would be manufacturing
the evidence the flag exists to deny.

---

# PREDICTIONS, COMMITTED BEFORE THE RUN

**Registered here, before the wiring exists, with a refutation clause in both directions and in the
right form.** Scored against the smoke run first and the rung run only if W9's step 2 is taken.

- **P1 — the `κ` axis will have exactly one populated bin, `kappa_lt_2^26`.**
  *Refuted upward* by any live cell in `kappa_undefined` — which is **reachable**, since the
  taxonomy thresholds `cond` and never tests positive definiteness, so this would be a real finding
  about the field and not a defect. *Refuted downward* by a live cell in either unreachable bin,
  which would refute (h3) and is a defect in `HESSIAN_COND_LIMIT`'s relationship to D9, not a
  finding.
- **P2 — on the simulated rung, differing points will be a small single-digit percentage of ranked
  points, against 34% on real altimetry.** *Refuted upward* by a rate approaching the real-data
  figure, which would say the simulated field is harder than 2d measured it to be. *Refuted
  downward* by exactly zero differing points, which would make the decomposition's denominator zero
  and the reading a null — reportable, and W5 is why it is expected rather than explained.
- **P3 — of whatever differs, dropouts will outnumber moves, but the population will be too small
  to quote a rate.** *Refuted* by a move-dominated decomposition, which would be the first evidence
  in the project of an actual re-ranking and would change §11.2's inserted block. *Also refuted* by
  a population large enough to pass the 30-member floor in any stratum, which would mean the
  simulated field carries the effect after all.
- **P4 — most or all point strata will withhold, reporting member counts.** 384 points on the easy
  rung across up to 9 `margin × winner` strata, with a 30-member floor. *Refuted* by every stratum
  reporting a rate, which would mean the strata are concentrated in one or two cells and the
  stratification is not separating anything.
- **P5 — the `both_ok_fraction < 1.0` note will fire for at least one candidate.** That note is the
  start-dependence surface W3 relocates the check to. *Refuted* by a perfect intersection on every
  candidate, which would say the simulated field has no start-dependent selectability at all — and
  would make the rung a fixture placed exactly where the two functions agree (i7), which is a fact
  worth recording about the fixture rather than about the mechanism.

---

# WHAT THIS WIRING DOES NOT DO

- **It does not repair open question 23.** Its cause is not established, a stratified audit is not
  the instrument that would settle it, and a structural-sounding explanation is the most dangerous
  possible reading.
- **It does not touch `HESSIAN_COND_LIMIT`, `FIELD_SEED`, `ALGORITHM_VERSION` or any
  exit-criterion verdict** — except criterion 12's, which is re-evaluated on its own evidence when
  and only when a committed report carries a stratum.
- **It does not take OQ22's gate repair**, which needs its own validation against known-good and
  known-bad.
- **It does not close open question 21.** The rung's arms are a **census** of the field, not a
  subsample, so *"how does the audit select its points"* is not answered — it is not asked. The
  question stays open with its original closer intact.
- **It does not start a rung run.** W9 step 2 is a budget decision, stated rather than taken.
