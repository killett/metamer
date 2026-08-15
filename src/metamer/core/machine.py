"""Peak-RSS measurement, with a branch per platform.

`resource.getrusage(...).ru_maxrss` reports **kilobytes on Linux and bytes on
macOS** -- a factor of 1024 that would look like a plausible number of bytes on
both platforms while being wrong by three orders of magnitude on one of them.
That is the whole reason this is a module rather than an inline call: the unit
correction has to live in exactly one place, and it has to be tested against a
known allocation rather than against "is it finite".

Windows has no `resource` module. That branch is written but untested, and is
part of the "portable, unclaimed" position on Windows support.

**`ru_maxrss` is a high-water mark that never decreases.** A reading is
therefore a statement about the whole process lifetime, not about what is live
now: two measurements taken in one process cannot be compared unless the second
allocation exceeds every allocation that preceded it.

**AND IT IS INHERITED ACROSS `fork()`/`exec()` -- THE PARENT'S OWN HIGH-WATER
MARK, NOT ITS CURRENT RSS AND NOT ITS REPORTED PEAK.** Measured 2026-08-12,
reproducibly, by varying the two candidate quantities independently (MB):

    parent                      parent_peak  parent_current  child_peak
    never allocated                    73.9            74.1        73.9
    allocated 400 MiB, HELD           493.3           493.7       493.3
    allocated 400 MiB, then FREED     493.3            74.3       493.3

**The child follows the watermark.** `freed` and `held` agree while `freed`'s
current RSS is indistinguishable from a small parent's, so current RSS cannot be
what propagates -- **and freeing the memory first does not help.** So spawning a
fresh process is not enough to isolate a memory measurement, and the number is
entirely plausible either way.

**THE INHERITANCE DOES NOT COMPOUND, AND THAT IS THE LOAD-BEARING HALF.**

> `peak_rss_bytes()` returns `max(inherited, this process's own high-water)`,
> and a child inherits **only the second term.**

**The measurement that establishes it**, three generations, reproduced twice
(MB). The middle process **allocates nothing**, so whatever it reports, it
inherited:

    top (allocates 400 MiB)  reports 493.1
    middle (allocates none)  reports 493.1   current 74.3
    grandchild               reports  74.1

If a child inherited the parent's *reported* peak, the grandchild would read
493. It reads 74 -- the middle process's own high-water -- while the middle
process still reports 493. **That is the rule, and the number is why it can be
trusted**: a reader who has only the contract has no way to tell it from the
plausible alternative.

Two consequences, and neither is obvious from the contract alone. **A
measurement two processes down from a large ancestor is usable**, provided the
process that spawns it stayed small -- which is what makes design doc section
11.4's calibration tile implementable, and why `tests/test_memory.py` runs its
probes behind a bare launcher rather than straight from pytest. And the
2026-08-10 observation of a probe reading 454.8 MB whose own child reported the
probe's *current* 84.6 MB **is this rule rather than a contradiction of it**: the
probe had allocated nothing, so its own high-water was its current RSS.

Both facts are pinned by tests; open question 12 in `PROGRESS.md` records what
was believed before them, and how long the two readings sat unreconciled.

That is why `current_rss_bytes` exists. Use `peak_rss_bytes` to answer "how
much did this process ever hold", and `current_rss_bytes` to answer "how much
is resident now" -- the latter is not a watermark, so it is not inherited and
not contaminated by anything an ancestor did.
"""

from __future__ import annotations

import platform
import subprocess
import sys
from enum import StrEnum

from metamer.core.hashing import machine_fingerprint


def cpu_model() -> str:
    """Return a string naming this machine's CPU.

    **`platform.processor()` IS NOT THE SOURCE, AND THAT IS THE WHOLE POINT.**
    Measured on Linux it returns `''`, so a fingerprint built on it is the same
    string on every Linux box and differs only by core count and RAM. An
    identity field that cannot distinguish the things it identifies fails the
    third of pre-flight (a2)'s four facts -- a change in the thing identified
    must move the field.

    Sources, in order: `/proc/cpuinfo`'s model name on Linux;
    `machdep.cpu.brand_string` on macOS; `platform.processor()`; and finally
    `platform.machine()`, which names the architecture rather than the CPU and
    is the last resort rather than the default.

    Returns:
        The CPU model string, never empty.

    Raises:
        RuntimeError: If every source is empty. **Raising beats returning `""`**:
            an empty identity silently collapses every machine into one cache
            key, and section 11.4's calibration cache would then hand one
            machine's bytes-per-series to another against a hard RAM constraint.
    """
    if sys.platform == "linux":
        try:
            with open("/proc/cpuinfo") as handle:
                for line in handle:
                    if line.startswith("model name"):
                        found = line.split(":", 1)[1].strip()
                        if found:
                            return found
        except OSError:  # pragma: no cover - /proc absent
            pass
    elif sys.platform == "darwin":  # pragma: no cover - not exercised on Linux
        try:
            found = subprocess.run(
                ["/usr/sbin/sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            if found:
                return found
        except (OSError, subprocess.SubprocessError):
            pass

    for fallback in (platform.processor(), platform.machine()):
        if fallback.strip():
            return fallback.strip()
    raise RuntimeError(  # pragma: no cover - every source empty
        "no CPU model could be read from this platform; the machine "
        "fingerprint would not distinguish this machine from any other"
    )


def choose_core_count(physical: int | None, logical: int | None) -> int:
    """Pick the core count to fingerprint with, preferring the physical one.

    **A SEPARATE FUNCTION SO THE CHOICE IS TESTABLE OFF THIS MACHINE.** This box
    has no SMT -- physical and logical are both 4 -- so a test of
    `physical_cores()` here cannot distinguish the two, and the mutation
    `logical=True` survived against it. The choice is arithmetic over two
    numbers, so it is testable with constructed inputs on any host, exactly as
    `batch.threads.library_table`'s collision case is.

    Args:
        physical: Physical core count, or None where the platform cannot say.
        logical: Logical core count, or None.

    Returns:
        The physical count when known, else the logical count, else 1. A
        wrong-but-present count fragments section 11.4's cache; `None` would
        raise inside the digest, and 0 would be a plausible-looking impossibility.
    """
    return int(physical or logical or 1)


def physical_cores() -> int:
    """Return the number of physical cores.

    Physical rather than logical: the fingerprint keys a calibration measured in
    bytes per series, and two boxes differing only in SMT have the same memory
    behaviour, so the logical count would fragment the cache for nothing.

    Returns:
        The physical core count, at least 1. See `choose_core_count` for the
        fallback and for why the choice lives in its own function.
    """
    import psutil

    return choose_core_count(
        psutil.cpu_count(logical=False), psutil.cpu_count(logical=True)
    )


class RamBasis(StrEnum):
    """Which reading produced a total-RAM figure.

    A `StrEnum`, so a caller comparing against `"host"` still works and the
    value serializes into provenance unchanged.
    """

    HOST = "host"
    CGROUP_V1 = "cgroup_v1"
    CGROUP_V2 = "cgroup_v2"


CGROUP_V2_PATH = "/sys/fs/cgroup/memory.max"
"""cgroup v2's memory limit. Holds the literal `max` when there is none."""

CGROUP_V1_PATH = "/sys/fs/cgroup/memory/memory.limit_in_bytes"
"""cgroup v1's memory limit. Holds a huge sentinel when there is none.

The sentinel needs no special case here: it is far above any host's physical
memory, so the `min` below discards it for the same reason it discards a limit
that is simply generous.
"""


def _read_cgroup_limit(path: str) -> int | None:
    """Read one cgroup memory limit, or None if there is not one to read.

    Args:
        path: Where the limit lives.

    Returns:
        The limit in bytes, or None if the file is absent, unreadable, or holds
        anything that is not a positive integer -- cgroup v2 writes the literal
        `max` for "no limit", which is the common case and not an error.
    """
    try:
        with open(path) as handle:  # noqa: PTH123 - a sysfs path, not a data file
            raw = handle.read().strip()
    except OSError:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value > 0 else None


def _resolve_total_ram() -> tuple[int, RamBasis]:
    """Return total RAM and the basis that produced it, from ONE reading.

    **THE VALUE AND ITS LABEL COME OUT OF THE SAME COMPUTATION, AND THAT IS THE
    WHOLE REASON THIS FUNCTION EXISTS.** `total_ram_bytes` and `ram_basis` are
    two questions about one fact; answering them in two independent readers lets
    provenance record a basis that did not produce the number beside it, and
    nothing downstream could tell. It is (a2)'s fourth fact turned around: the
    label must be produced by the thing it labels.

    **The rule is the minimum over the host reading and any readable limit.**
    `psutil` reads the host, which is what a container sees through
    `/proc/meminfo` and is **not** what it is allowed to use. A limit at or above
    the host figure loses the `min` and the basis stays `host`, which is also how
    cgroup v1's no-limit sentinel is handled without naming it.

    Returns:
        `(bytes, basis)`.
    """
    import psutil

    host = int(psutil.virtual_memory().total)
    best, basis = host, RamBasis.HOST
    # v2 first, so a machine mounting both and reporting equal limits records
    # the modern one rather than the tie-break of whichever was read last.
    for path, candidate in (
        (CGROUP_V2_PATH, RamBasis.CGROUP_V2),
        (CGROUP_V1_PATH, RamBasis.CGROUP_V1),
    ):
        limit = _read_cgroup_limit(path)
        if limit is not None and limit < best:
            best, basis = limit, candidate
    return best, basis


def total_ram_bytes() -> int:
    """Return total RAM in bytes, respecting a container's memory limit.

    **NOT `psutil.virtual_memory().total` ALONE.** `psutil` reads the host
    through `/proc/meminfo`, which inside a container reports the machine's
    memory rather than the container's allowance -- so a 2 GB container on a
    128 GB box would size its tiles for 128 GB, and the consequence is an OOM
    kill rather than a slow run. See `_resolve_total_ram`.

    Returns:
        Total memory this process may use, in **bytes** -- `psutil` reports
        bytes, unlike `ru_maxrss`, whose kilobyte-on-Linux reading is the unit
        trap this module exists for.
    """
    return _resolve_total_ram()[0]


def available_ram_bytes() -> int:
    """Return the memory this machine reports as free right now.

    **THIS IS AMBIENT STATE AND NOTHING SIZES ANYTHING FROM IT.** It has one
    caller -- `batch.run`'s warning that the resolved budget exceeds what is
    free -- and the default budget is a fraction of `total_ram_bytes` precisely
    because this figure moves by a factor of nearly three within days on one
    machine. A default taken from it would derive a different tile side on every
    run, so a resume would refuse because something else was running. See
    `memory.DEFAULT_BUDGET_FRACTION`, and `PROGRESS.md`'s *What Task 3
    established* for the readings themselves.

    **AND IT IS NOT CGROUP-AWARE, UNLIKE `total_ram_bytes`.** `psutil` reads the
    host, while a container's own headroom is `memory.max - memory.current` --
    a different pair of files. The gap is left open deliberately rather than
    unnoticed: inside a limit this OVERSTATES what is free, so the warning fires
    less often than it should, and a warning that stays silent is a missing
    warning rather than a wrong action. **A gate here would be a different
    matter, and there is deliberately not one.**

    Returns:
        Available memory in bytes. `psutil` reports bytes, unlike `ru_maxrss`.
    """
    import psutil

    return int(psutil.virtual_memory().available)


def ram_basis() -> str:
    """Return which reading `total_ram_bytes` used.

    Returns:
        One of `host`, `cgroup_v1`, `cgroup_v2` -- a `RamBasis`, which is a
        `str`. **From the same computation as the value**, never a second
        reading; see `_resolve_total_ram`.
    """
    return _resolve_total_ram()[1]


def fingerprint() -> str:
    """Return this machine's fingerprint, read from the platform.

    **THE ARGUMENTS COME FROM HERE, NEVER FROM A CONFIG.**
    `hashing.machine_fingerprint` takes its three inputs as parameters, so it is
    self-reported at its own boundary. That is harmless while the value reaches
    `run_hash` alone -- provenance, never a gate -- and it becomes an **identity**
    the moment section 11.4's calibration cache key reads it, because a
    config-supplied fingerprint would let one machine's calibration be reused on
    another. Wiring it from the platform before the cache exists is what avoids
    invalidating whatever the cache already holds.

    **THE RAM COMPONENT BECAME CGROUP-AWARE ON 2026-08-15, AND THAT MOVES THIS
    VALUE INSIDE A CONTAINER.** Two containers of different sizes on one host
    previously shared a fingerprint -- (a2)'s third fact failing, a change in the
    thing identified not moving the field -- and they now do not. The
    consequence is a changed `run_hash` for stores built under a memory limit,
    which is the point rather than a side effect. **This machine cannot show it**
    (`/sys/fs/cgroup/memory.max` is `max`, measured 2026-08-15), so the evidence
    is a constructed test and nothing else.

    Returns:
        The 16-hex-digit fingerprint.
    """
    return machine_fingerprint(cpu_model(), physical_cores(), total_ram_bytes())


def peak_rss_bytes() -> float:
    """Return this process's peak resident set size, in bytes.

    Returns:
        Peak RSS in bytes, as a float. This is a high-water mark over the
        process's whole lifetime and never decreases.
    """
    if sys.platform == "win32":  # pragma: no cover - written, untested
        import psutil

        return float(psutil.Process().memory_info().peak_wset)

    import resource

    raw = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return raw if sys.platform == "darwin" else raw * 1024.0


def current_rss_bytes() -> float:
    """Return this process's resident set size right now, in bytes.

    Not a high-water mark, which is the entire point: `peak_rss_bytes` is
    inherited across `fork()`/`exec()` and so reports an ancestor's number
    whenever that ancestor was larger. This does not, so it is the honest
    instrument for "what does this workload hold", including inside a child
    spawned for exactly that measurement.

    Linux exposes it as `VmRSS` in `/proc/self/status`, in kilobytes.
    Elsewhere it comes from `psutil`, which reports bytes.

    Returns:
        Resident set size in bytes.
    """
    if sys.platform == "linux":
        with open("/proc/self/status") as handle:
            for line in handle:
                if line.startswith("VmRSS:"):
                    return float(line.split()[1]) * 1024.0
        raise RuntimeError("no VmRSS line in /proc/self/status")  # pragma: no cover

    import psutil  # pragma: no cover

    return float(psutil.Process().memory_info().rss)  # pragma: no cover
