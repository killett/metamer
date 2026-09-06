# The difficulty rung on construction version 2 — the pre-decided stop fired, 2026-09-05

**The predictions were committed before the run** at
[`phase2d-difficulty-rung-predictions.json`](phase2d-difficulty-rung-predictions.json); the
measured records are [`phase2d-difficulty-rung-measured.jsonl`](phase2d-difficulty-rung-measured.jsonl),
the report is [`phase2d-difficulty-rung-report.json`](phase2d-difficulty-rung-report.json), the harness is
[`phase2d-difficulty-rung-harness.py`](phase2d-difficulty-rung-harness.py), and the conditioning
discriminator that ran first is [its own verdict](phase2d-conditioning-probe-verdict.md). **Nothing
from any of them is restated except the readings against their clauses.**

**The field: rung `easy`, field construction version 2, seed `20260830`, 32 × 12, `N = 630`, `M = 3`,
the shipped `fit`, one thread.** The artifact records the seed and the construction version — R5 —
so it can name its own field. Gate passed at loadavg 2.13 after three host-wide refusals; the run
took **15.35 h** wall clock; **the interior null came back clean and `require_clean` passed.**

## THE TWO NUMBERS FIRST

**1. The width, against the N2 floor: AT THE FLOOR ON EVERY ARM.** Cold, warm and N2 all read
`<= 1 cell`, unresolved rather than zero; **no row of any arm's profile crosses a half** — the
maximum is **0.333** on all three. **Warm's profile differs from cold's in exactly one row** (index
10, six cells inside regime A), and there warm agrees with the truth *better* — one cell moved
**toward** the truth, not away from it. **There is no smear.**

**2. The outcome distribution, against the probe's version 2 arm: R4 HELD ON BOTH ARMS.**

| arm | fitted | OK | not OK | difference from the probe's 1/48 | band | verdict |
|---|---|---|---|---|---|---|
| cold | 1152 | 1151 | 1 `DEGENERATE_HESSIAN` | **−0.020** | 0.05 | **HELD** |
| warm | 1152 | 1149 | 3 `TRUST_RADIUS_COLLAPSED` | **−0.018** | 0.05 | **HELD** |

The probe's discriminator describes the rung it was used to interpret: the field converges at
production length as cleanly with the signal as without it, on 1152 cells and not only on 48.

## EVERY READING AGAINST ITS CLAUSE

| # | reading | clause | measured | verdict |
|---|---|---|---|---|
| **C1, C2** | conditioning, version 1 against 2 | bands | held before the run — [the probe's verdict](phase2d-conditioning-probe-verdict.md) | **HELD → the stop is NOT suspended** |
| **R1** | cold iterations per point | **[40, 47]**; the stop is stated against **43.94** | **42.08** (OK-only 42.04) | **HELD.** The lower-edge caution did not fire. **THE STOP'S REFERENT MOVED FROM `BASE` TO THE FIELD, AND A READER COMPARING 42.08 TO 43.94 WILL OTHERWISE SEE A 4% MISS.** 43.94 is 2c's fixture under the shipped `fit`, and 43.50 was this construction at `BASE` alone; **the rung measures the whole field**, whose `factor` runs 0.5 to 3.0 and whose `rho` in samples therefore varies, and the field's own number is 42.08. **The stop asks whether the field is at 2c's difficulty, and 42.08 inside [40, 47] says it is** — so the stop was evaluated against 42.08, not against a number the field never produced |
| **R2** | the interior null, read first | does not fire (Task 2's committed prediction) | at floor, clean, `contaminated: false` | **HELD** — the gate passed |
| **R3** | saving **and** width, in that order | saving rises toward 2c's range, **and** a width appears above the 1-cell floor | **saving pass-2-only 41.81%, net of pass 1 39.75%** — 2c's own range; **width at the floor on every arm** | **THE FIRST HALF HELD AND THE SECOND WAS REFUTED FROM BELOW: warm equals cold at every index, at R1's difficulty, with C1 and C2 inside their bands. THE PRE-DECIDED STOP.** |
| **R4** | outcome distribution in situ | \|d\| ≤ 0.05 from the probe's version 2 | −0.020 cold, −0.018 warm | **HELD** |
| **R5** | the artifact names its field | seed and construction version in the block | `seed: 20260830`, `field_construction_version: 2`, `drawn_signal_terms: ["trend"]`, `16.0` | **HELD** |

## THE PRE-DECIDED STOP, AND THE PREPARED CONCLUSION IS AVAILABLE

**No artifact appears at 2c's difficulty, on a field carrying what 2c's carried, on the shipped
mechanism, with conditioning comparable to the signal-free construction's.** Every condition the
prepared conclusion was made contingent on is met: C1 and C2 held before the run, R1 landed inside
its band, the null was clean, and R4 confirmed the probe described the rung.

**AND THE SAVING APPEARED — AT 2c's OWN SIZE.** Warm-starting saved **41.81%** of pass-2 iterations
(24.46 warm against 42.08 cold per point) and **39.75%** net of pass 1's cost, against **2c's
42.28%**. The three signal-free rungs saved nothing because there was nothing to save — 24.4 cold
iterations is where a warm start has nothing to improve. **On the corrected builder the saving is
real and it is 2c's**, and **selection did not move with it**: the warm and cold profiles agree on 31
of 32 rows and differ on one by exactly one twelfth, in the direction of the truth.

> **CORRECTED 2026-09-05, THE SAME DAY, BEFORE ANYONE BUILT ON IT.** The first draft of this
> paragraph said *"99.48% of cells select the same candidate warm and cold, and the 0.52% that
> differ do not form a band."* **That figure is the SELF arm against cold** —
> `self_arm_agrees_with_cold_selection`, 382 of 384 points — **not warm against cold**, and it is
> over points, not cells. **The warm-against-cold agreement is not a number in the artifact at all.**
> The report carries each arm's PROFILE (per-row misclassification fraction) and not its SELECTION
> MAP, and the run's stores were temporary; so the point-level statement that can be supported is
> exactly the one above — one row moved by one twelfth — and **the positions and condition numbers
> of the differing points cannot be recovered from what was kept.** That is a defect in the
> artifact, filed below, not a fact about the field.

**THE FINDING IN ITS STRONGEST HONEST FORM.** D1 said warm-starting saves 42.28% and reattributed
most of that to *"any converged optimum"*. **The audit was built on the assumption that a saving of
that size might be buying bias** — smooth maps by an illegitimate mechanism. This rung says: at 2c's
own difficulty, on a field carrying what 2c's carried, on the shipped mechanism, **a 42% saving moves
no row of the selection profile past a half and moves one row by one twelfth, toward the truth.**
**The audit exists to catch hysteresis and found none where the saving is largest.**

**AND IT IS A NULL WITH A POSITIVE CONTROL BESIDE IT, WHICH IS WHAT MAKES THE INSTRUMENT'S SILENCE
A READING.** The three-rung result at 24.4 iterations shows the audit reads *warm equals cold* when
there is **nothing to save**; this shows it reads the same when there is **42% to save**. **The
audit's instrument is not blind: it has measured two regimes and reported the same answer with the
mechanism demonstrably active in one.** That does not lift the standing limitation, and this verdict
must not be read as though it does — it is a null on this construction at this difficulty. But it
is no longer a null that could be the instrument's.

**THAT IS THE READING WRITTEN IN ADVANCE, AND IT IS NOW A MEASUREMENT RATHER THAN A PREPARATION.**
D1's 42.28% saving and the absence of any artifact at the difficulty where it was measured now sit
side by side, and the thing that connects them is: **a warm start that saves two fifths of the
iterations while moving no selected candidate is buying TIME and not BIAS.** That is the good case
for warm-starting — the one 2c's own measurements could not distinguish from the bad one, because
2c never had a floor arm and never had a signal-free comparison. **2d has both, and they agree.**

**THE CONTRAST WITH THE THREE-RUNG NULL IS THE FINDING, AS THE DECISION SAID IT WOULD BE.** Two
constructions, differing in exactly the term whose absence was the defect: one where warm equals
cold in *iterations* because there is nothing to save, one where warm saves 42% — **and in both,
warm equals cold in *selection*.** The artifact §16.2 item 6 was built to measure did not appear in
either population, and the second population is the one where it had something to appear in.

## WHAT THIS DOES NOT SAY, STATED WITH THE SAME CARE

- **Nothing here comes from real altimetry and no magnitude is quoted.** The standing limitation is
  unchanged: the spatial coherence of real optima has never been measured, and the named closer is
  a spike on a real gridded product. **A null on this construction at this difficulty is a statement
  about this construction at this difficulty.**
- **The width floor is 1 cell and the profile is the primary reading.** A smear must carry a row
  past a half to register; **no row reached 0.5 on any arm**, and the highest reading, 0.333, is
  identical across cold, warm and N2 — it is the field's own baseline misclassification on the
  regime-B side, present with no warm start at all.
- **No further rungs.** That is the branch Task 1 wrote and Task 5b's brief carried: *"No further
  rungs. That is the branch Task 1 already wrote, and it makes the finding a statement about
  warm-starting rather than about this field."*

## THE COST BLOCK, WITH ITS PRECONDITIONS MARKED

| phase | seconds | hours |
|---|---|---|
| cold | 9 950 | 2.76 |
| warm | 5 856 | 1.63 |
| N2 | 36 729 | **10.20** |
| self | 2 727 | 0.76 |
| **total wall clock** | | **15.35** against **~13.2** priced |

**The seconds are the contaminated half and the block says so**: one thread, **a live agent session
on the same four cores for the whole run**, loadavg 2.13 at the gate against a limit of 3.0, and a
gate whose input is host-wide (open question 22). **The cold arm ran at 25.9 s/point against the
cost basis's 20.65** — 25% over, which is the host and the session and not the field: **the
iteration ratio 42.08 / 24.69 = 1.70 reproduces the cost basis's 1.71** to two digits. **N2 is two
thirds of the wall clock**, which is a fact about pricing the audit's floor arm and is recorded
for Task 8's figure and for whoever prices the next one.
