"""The quiet-host gate every 2d measurement runs before it measures.

**IT GATES RATHER THAN ANNOTATES, AND THAT IS THE WHOLE POINT.** Task 0's
fourth defect was a harness whose quiet check **recorded a loud host and then
measured anyway** -- (a2b) inside the instrument written to enforce (a2b). A
caller that reads `quiet` and proceeds regardless has reproduced it, so the
refusal belongs at the call site's first branch and the reading exists to be
emitted beside it.

**ONE HOME, PROMOTED 2026-08-31 AT TASK 5's PRE-FLIGHT.** The check lived in
`phase2d-field-harness.py`, which measured criterion 17 twice; Task 5 is 2d's
third harness and the first that would have copied it. (j9) says a rule against
duplication does not prevent duplication -- the two spellings would agree until
one was edited -- and this sub-phase's worst instance was an instrument block
that was itself a copy.

**THE RULE IS `load1 < physical_cores - 1`.** Every 2d rate is measured under
`threadpool_limits(1)`, so the condition being tested is *"is a core free for a
single-threaded measurement"*, and the one-minute load average is the reading
that answers it. **Equality is the loud side**: a load of exactly `cores - 1`
leaves nothing over.

**AND THE STALL RATE IS REPORTED WITHOUT GATING.** `memory_stall_us` is a
pressure counter, not a contention one; open question 19 is why it is not a
gate, and it is carried so a refused or surprising run has the number beside
it rather than a re-run to obtain it.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from metamer.core import machine

#: How long to idle before reading the load average. **The idle is what makes
#: the reading describe the run about to happen**: the one-minute average is a
#: decaying mean, so a check taken on arrival reports the job that just ended.
QUIET_SECONDS: float = 20.0


def is_quiet(*, load1: float, physical_cores: int) -> bool:
    """Whether a host with this load has a core free for one measurement.

    Args:
        load1: The one-minute load average.
        physical_cores: Physical cores on the box.

    Returns:
        True when `load1 < physical_cores - 1`. **Equality is the loud side**,
        because a load equal to the limit leaves no core over and the rate
        being measured is a single-threaded one.
    """
    return bool(load1 < float(physical_cores) - 1.0)


@dataclass(frozen=True)
class HostReading:
    """What the gate saw, in the form a harness emits.

    Attributes:
        quiet: The verdict. **A caller refuses on False**; nothing here decides
            for it, because the refusal message belongs to the measurement.
        loadavg: The one-, five- and fifteen-minute load averages.
        physical_cores: Cores the limit was computed from.
        load_limit: `physical_cores - 1`, carried so a refused run records the
            number it was refused against rather than only the verdict.
        idle_seconds: How long the check idled before reading.
        stall_ms_per_s: Memory-stall rate over the idle, or None where the
            kernel does not expose one. **Reported, never gated on** -- open
            question 19.
        machine: The host fingerprint, so two records can be compared.
    """

    quiet: bool
    loadavg: tuple[float, float, float]
    physical_cores: int
    load_limit: float
    idle_seconds: float
    stall_ms_per_s: float | None
    machine: str

    def as_record(self) -> dict[str, Any]:
        """The reading as a JSONL record, keyed as 2d's harnesses key it.

        **The keys match the 2026-08-30 and 2026-08-31 records exactly**, so a
        Task 5 run is comparable with the criterion-17 runs without anyone
        translating between two spellings of one reading.
        """
        return {
            "record": "quiet_check",
            "idle_seconds": self.idle_seconds,
            "stall_ms_per_s": self.stall_ms_per_s,
            "loadavg": list(self.loadavg),
            "physical_cores": self.physical_cores,
            "load_limit": self.load_limit,
            "quiet": self.quiet,
            "machine": self.machine,
            "stall_is_not_a_gate": "open question 19",
        }


def quiet_check(
    *,
    idle_seconds: float = QUIET_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
    loadavg: Callable[[], tuple[float, float, float]] = os.getloadavg,
    physical_cores: Callable[[], int] = machine.physical_cores,
    stall: Callable[[], tuple[int, str] | None] = machine.memory_stall_us,
) -> HostReading:
    """Idle, then read the host, then apply the rule.

    Args:
        idle_seconds: How long to idle first. **The order is the mechanism**,
            not a courtesy: reading before idling reports the previous job.
        sleep: The idle. Injected so the rule can be tested without one.
        loadavg: The load reader.
        physical_cores: The core count reader.
        stall: The memory-stall counter reader.

    Returns:
        The reading. **The caller refuses on `quiet is False`**; this function
        does not raise, because the refusal record is part of the measurement's
        own output and only the measurement can write it.
    """
    before = stall()
    started = time.perf_counter()
    sleep(idle_seconds)
    elapsed = time.perf_counter() - started
    after = stall()
    load = tuple(float(value) for value in loadavg())
    cores = int(physical_cores())
    rate: float | None = None
    if before is not None and after is not None and elapsed > 0.0:
        rate = (after[0] - before[0]) / 1000.0 / elapsed
    return HostReading(
        quiet=is_quiet(load1=load[0], physical_cores=cores),
        loadavg=(load[0], load[1], load[2]),
        physical_cores=cores,
        load_limit=float(cores) - 1.0,
        idle_seconds=elapsed,
        stall_ms_per_s=rate,
        machine=machine.fingerprint(),
    )


#: The refusal a caller emits when the gate fires. **One wording**, so two
#: harnesses cannot describe the same refusal differently.
REFUSAL: Mapping[str, str] = {
    "record": "refused",
    "why": (
        "the host was not quiet: no core was free for a single-threaded "
        "measurement. (a2b) -- the value is made unavailable rather than "
        "emitted with a caveat."
    ),
}


__all__ = ["QUIET_SECONDS", "REFUSAL", "HostReading", "is_quiet", "quiet_check"]
