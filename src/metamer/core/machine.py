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

**AND IT IS INHERITED ACROSS `fork()`/`exec()`.** Measured on this kernel: a
child spawned from a parent holding 400 MiB reports a peak of 493.28 MB --
byte-identical to the parent's -- against 119.95 MB for the same child spawned
from a small parent. `fork()` copies the parent's `mm->hiwater_rss` and `exec()`
does not reset it, so **spawning a fresh process is not enough to isolate a
memory measurement**: the child reports whichever high-water mark is larger,
and the number is entirely plausible either way.

That is why `current_rss_bytes` exists. Use `peak_rss_bytes` to answer "how
much did this process ever hold", and `current_rss_bytes` to answer "how much
is resident now" -- the latter is not a watermark, so it is not inherited and
not contaminated by anything an ancestor did.
"""

from __future__ import annotations

import sys


def peak_rss_bytes() -> float:
    """Return this process's peak resident set size, in bytes.

    Returns:
        Peak RSS in bytes, as a float. This is a high-water mark over the
        process's whole lifetime and never decreases.
    """
    if sys.platform == "win32":  # pragma: no cover - written, untested
        import psutil  # type: ignore[import-untyped]

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

    import psutil  # type: ignore[import-untyped]  # pragma: no cover

    return float(psutil.Process().memory_info().rss)  # pragma: no cover
