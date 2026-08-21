# Open question 19 — what the fixed-window gate reads, on both known-bads

Measured 2026-08-21 with [`oq19-gate-validation.py`](oq19-gate-validation.py), which imports the
shipped gate rather than reimplementing it. Every cell reports **both** readings from one run:
the windowed maximum the gate now uses, and the whole-block average it used before.

| cell | what it constructs | windowed max | whole-block average | reclaim shortfall |
|---|---|---|---|---|
| **clean** | the workload, no pressure | **7.5 ms/s** | 0.4 ms/s | 0.00 MB |
| **thrash** | pressure + re-touching anonymous memory | **0.13 ms/s** | 0.008 ms/s | 4.57 MB |
| **refault** | pressure + sweeping a 3 GB file-backed mapping | **76.5 ms/s** | 14.1 ms/s | 0.00 MB |
| **quiet** (Task 8i's) | pressure + 600 s idle | **61.3 ms/s** | **0.2 ms/s** | **25.35 MB** |

## THE FIXED WINDOW TURNS THE GATE'S KNOWN BLINDNESS INTO A FIRING

**Task 8a established that the gate could not see quiet reclaim** — a run that lost 85 MB read
**0.0876 ms/s**, below the idle baseline — and the mechanism given was that PSI `full` counts time
*stalled waiting* on memory, which reclaiming untouched clean pages does not cost. **The `quiet`
cell reproduces that whole-block reading almost exactly: 0.2 ms/s over 600 s.** Over its worst
single second the same run reads **61.3 ms/s**, and the gate fires.

**So the blindness was partly a DILUTION artifact and not only a definitional one.** The reclaim
is brief and intense; averaging it over a ten-minute window divided it by about three hundred.

> **AND THE CAVEAT IS LOAD-BEARING, BECAUSE THE COUNTER IS NOT PER-PROCESS.**
> `/sys/fs/cgroup/memory.pressure` reports the **cgroup**, and the pressure generator runs inside
> the same one. Some or all of the 61.3 ms/s may be the *generator* stalling as it takes 4.8 GB,
> not the measured process. **That does not weaken the operational conclusion** — a measurement
> taken while anything in this cgroup is stalling that hard is not one to assert on — **but it
> forbids the stronger claim** that the measured process itself waited. Task 8a's original case
> had no constructed pressure, so its 0.0876 ms/s remains the reading for reclaim caused from
> outside this cgroup, where the counter has nothing to attribute.

## AND THE FIRST ATTEMPT AT A KNOWN-BAD FAILED, WHICH IS WHY THE REFAULT CELL EXISTS

The `thrash` cell asks the kernel to take **anonymous** pages this process is actively touching.
The bounded generator stops at a 2 GB floor by design — measured, `held_mb=3328` with
`available_mb=2078` — so it never pushed the kernel that far, and the gate read **0.13 ms/s**
because nothing this process wanted was ever taken. **A construction that does not construct the
effect is a null about the construction, not about the gate** (i2), and the repair was to make
the working set **file-backed**: clean pages are evicted under the same pressure, reading them
back is a refault, and PSI counts exactly that. **No OOM risk, because the kernel may drop those
pages at will.**

## WHAT THE VALUE IS NOW SEPARATED BY

**Known-good 7.5 ms/s, known-bad 61.3 and 76.5 ms/s.** The shipped 50 000 us/s sits **6.7x above
the clean reading and 1.2x below the lower known-bad**, which is the first time this constant has
had a two-sided derivation instead of a multiple of idle. The full sweep's own worst *passing*
window — printed by the summary since this change — is what decides whether it stays.

---

## THE FIFTH CELL, AND IT UNDERMINES THE STATISTIC RATHER THAN THE CONSTANT

Added 2026-08-21 after the post-rework sweeps produced **two INDETERMINATE readings per run on a
settled box** — 251 and 271 ms/s, from `the floor ladder's rungs` and `peak residency across the
iteration cap`. **Both of those measurements spawn child probes that each build a ~220 MB working
set from nothing**, so the `probe` cell reproduces that with **no external pressure whatever**:
`measure_floor` in a loop for 60 s, on an idle box at 6.7 GB available.

| reading | probe cell (self-inflicted, no pressure) |
|---|---|
| windowed max, 1 s | **223.4 ms/s** |
| whole-block average, 61 s | 14.1 ms/s |
| **reclaim shortfall** | **0.00 MB** |

**And the window spectrum says no window length separates it from the known-bads:**

| window | 0.5 s | 1 s | 2 s | 5 s | 10 s | 30 s |
|---|---|---|---|---|---|---|
| self-inflicted | 102.4 | 102.4 | 102.4 | 63.5 | 38.7 | **26.7 ms/s** |

The constructed known-bads read **61.3** and **76.5 ms/s at one second**. **A process allocating
hard is at or above them at every window this box can measure**, and at 30 s the self-inflicted
case is still 26.7 ms/s while the quiet known-bad's whole 600 s average is 0.2. **The ordering
inverts as the window grows**, so there is no length at which the gate catches the failure and
spares the measurement.

> ## THE INSTRUMENT CANNOT DISTINGUISH "THIS MEASUREMENT IS ALLOCATING" FROM "THIS MEASUREMENT IS BEING SQUEEZED", AND THE WITNESS CAN.
>
> PSI `full` counts direct reclaim from **any** cause in this cgroup, and a probe ladder is a
> cause. In the same cell where the stall rate reads **223 ms/s**, `reclaim_shortfall_bytes`
> reads **0.00 MB** — correctly, because nothing was taken from this process. On Task 8i's
> known-bad the witness reads **25.35 MB** while the whole-block stall reads **0.2 ms/s**.
> **The two instruments are complementary and only one of them has the process as its subject.**

**AND THE CONSTANT IS NOT WHAT COSTS THE TWO TESTS.** At 50 000 µs/s the same sweeps would have
fired on 251, 271, 465 and 257 ms/s exactly as they did at 25 000; only one marginal reading of
25 ms/s differs. **The skip rate is a property of the windowed statistic, not of the value** —
so reverting the number would not restore those assertions, and choosing between gate and
diagnostic is the decision that would.

---

## THE SURVEY, 2026-08-21 — WHICH ASSERTIONS CAN WITNESS THEIR OWN SUBJECT

Five assertions consult `rss_validity`. The other five in Task 8i's table are ungated on margin
(200 MB to 400 MiB against a ~1 MB watermark drift) and nothing here changes them.

**Every measurement below is taken in a CHILD**, which is the constraint that made
`reference_bytes` optional in the first place: a reference read in the test process witnesses the
wrong process.

| assertion | where the measurement happens | can the measuring process read a reference? | structural or incidental | does its workload allocate hard? |
|---|---|---|---|---|
| `the floor ladder's rungs` | `memory._FLOOR_CHILD`, five rungs | **yes** — its own last rung is a figure it cannot honestly end below | **incidental**; costs a field in the floor payload, which provenance records and exit criterion 1 already excludes by name | **yes** — five child probes, each ~220 MB from nothing |
| `the floor with the input open` | the same child, twice | **yes**, same | **incidental**, same | **yes** |
| `peak residency across the iteration cap` | `memory._CALIBRATION_CHILD`, three caps | **yes** — `CalibrationPoint.baseline_bytes` is already exactly that reference, carried and unused for this purpose | **incidental**; adds a field to a schema Tasks 4, 5 and 7 pin | **yes** — three children |
| `criterion 7's peak against the budget and the grid` | an inline program **written in the test** | **yes** | **incidental, and free** — no production code involved | **yes** — two runs |
| `the recompute loop's per-tile resident set` | an inline program **written in the test** | **yes** | **incidental, and free** | **yes** — a 16-tile recompute |

### SO (c) COLLAPSES TO (b) PLUS A DIAGNOSTIC, AND THE COMPOUND RULE HAS NO PERMANENT MEMBERS

**Not one of the five is structurally unable to witness its own subject.** Two need no production
change at all; two share the floor payload; one touches a pinned schema. **And all five allocate
hard**, which is the other half: under a stall fallback every one of them would abstain routinely,
so the compound rule's fallback arm would be outcome (a) applied to whichever subset had not been
wired yet — assertions that look gated and do not run.

**The transitional set is real and is named rather than discovered.** Until a witness is wired,
an assertion is carried by its **margin**, which is the same footing Task 8i put the ungated five
on: rungs at ±25% with two >30 MB steps, the iteration cap at 16 MB, criterion 7 at 64 MB, the
recompute loop at 6 MB — all far above the ~1 MB watermark drift. **The exception is
`the floor with the input open`, whose window is >1 MB against that same drift**; Task 8i already
flagged it AT RISK, and it is therefore the one to wire first rather than last.
