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
