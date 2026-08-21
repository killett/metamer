"""A stall reading whose sensitivity is set by a constant here, not by the caller.

**WHY THIS MODULE EXISTS -- OPEN QUESTION 19.** `RSS_STALL_LIMIT_US_PER_S` gates
RSS-difference measurements on pressure-stall time, and it carried three
independent defects. Two are inherent and stay: it **cannot see quiet reclaim**
(Task 8a measured a run that lost 85 MB reading 0.0876 ms/s, below idle), and its
margin over what actually occurs on this box is **1.06x**. The third is the one
this module removes: **its sensitivity depended on the caller's window.** Its two
firings were over **14.1 s and 2.5 s**, and a rate averaged over the caller's
whole block dilutes a burst by however long the caller happened to run -- so the
same box crossed the same limit on different amounts of provocation depending on
which test was asking.

**THE REPAIR IS A FIXED WINDOW.** The reading is the **maximum stall rate over
any window of at least `STALL_WINDOW_S`** inside the measurement, so the question
the number answers is one question: *did this box ever stall for more than the
limit across a whole second?* A twenty-second block with one bad second now reads
what that second read, and a two-second block with the same bad second reads the
same.

**AND A BLOCK TOO SHORT TO HOLD A WINDOW IS NOT JUDGED, WHICH IS A THIRD STATE.**
Judging a 20 ms block against a limit derived from second-scale windows would be
the same defect at the other end. The alternative -- keep sampling past the end
of the caller's block until a window exists -- was rejected because the extra
window reports on an interval the measurement did not cover. **Abstention is
reported in the terminal summary**; it is never rounded into "clean", which is
the fill-value rule at a gate.

**WHAT THIS MODULE IS NOT.** It is not a reclaim detector.
`machine.reclaim_shortfall_bytes` is, and `conftest.rss_validity` checks it
first. Nothing here narrows the gap between the two -- see open question 19 for
the survey of which assertions can supply a reference honestly.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from types import TracebackType

#: POLICY. The measurement window, in seconds. **The gate's sensitivity is set
#: HERE and by nothing else** -- that is the whole point of the constant, and a
#: caller that passes its own window has reintroduced the defect.
#:
#: **ONE SECOND, AND THE ASYMMETRY IS STATED BECAUSE BOTH DIRECTIONS COST.**
#: Shorter windows report shorter bursts, so the gate fires on transients that do
#: not corrupt a measurement -- an INDETERMINATE that costs a reading for nothing.
#: Longer windows dilute, which is the defect being repaired. A second is chosen
#: because the failure it must catch is **sustained** reclaim across a
#: measurement, and because the counter it reads is a microsecond total whose own
#: resolution is far below a second.
STALL_WINDOW_S = 1.0

#: How often the counter is read while a measurement runs. Six samples per window
#: at the shipped values, so a burst is seen whether or not it aligns with a
#: sample boundary; reading `/sys/fs/cgroup/memory.pressure` is one small file
#: read, which is why the cadence can afford to be well inside the window.
STALL_SAMPLE_INTERVAL_S = 1.0 / 6.0


def max_windowed_rate(
    samples: list[tuple[float, float]], window_s: float
) -> float | None:
    """Return the largest stall rate over any window of at least `window_s`.

    **A MAXIMUM OVER WINDOWS, NEVER A MEAN OVER THE BLOCK.** Longer spans can
    only dilute, so taking the maximum over every qualifying pair reports the
    worst full window and is monotone in the thing being guarded against.

    Args:
        samples: `(seconds, cumulative microseconds)` pairs, in time order, as
            read from the pressure counter. The absolute origin is irrelevant;
            only differences are used.
        window_s: The minimum span a pair must cover to be a window. Callers
            should pass `STALL_WINDOW_S`.

    Returns:
        Microseconds of stall per second over the worst qualifying window, or
        **None if no pair of samples spans `window_s`** -- which means the block
        was too short to judge, and is not the same answer as zero.
    """
    worst: float | None = None
    for index, (start_t, start_total) in enumerate(samples):
        for end_t, end_total in samples[index + 1 :]:
            span = end_t - start_t
            if span < window_s:
                continue
            rate = (end_total - start_total) / span
            if worst is None or rate > worst:
                worst = rate
    return worst


class StallWatch:
    """Sample the pressure counter across a block and report its worst window.

    Used as a context manager. Sampling runs on a daemon thread so the caller's
    own timing is untouched; the thread does one small file read per interval.

    Attributes:
        rate: Microseconds of stall per second over the worst window, or None
            when the block was too short to hold one.
        unjudged_reason: Why no rate is available, or None when one is.
        samples: How many readings were taken.
        window_s: The window this watch judged against.
    """

    def __init__(
        self,
        reader: Callable[[], tuple[float, str] | None],
        *,
        interval_s: float = STALL_SAMPLE_INTERVAL_S,
        window_s: float = STALL_WINDOW_S,
    ) -> None:
        """Bind a watch to a counter reader.

        Args:
            reader: Returns `(cumulative microseconds, counter name)`, or None
                where the kernel does not expose the counter. **Injected rather
                than imported** so the tests can drive a counter that moves: an
                instrument that reads nothing is indistinguishable from a quiet
                box, and that is the one failure a gate cannot report on itself.
            interval_s: Seconds between readings.
            window_s: Minimum span of a judged window. **Defaults to the module
                constant and callers should leave it alone** -- a caller-chosen
                window is the defect this module exists to remove.
        """
        self._reader = reader
        self._interval_s = interval_s
        self.window_s = window_s
        self._samples: list[tuple[float, float]] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._counter: str | None = None
        self.rate: float | None = None
        self.unjudged_reason: str | None = None
        self.samples = 0

    def _read(self) -> None:
        reading = self._reader()
        if reading is None:
            return
        self._samples.append((time.perf_counter(), float(reading[0])))
        self._counter = reading[1]

    def _loop(self) -> None:
        while not self._stop.wait(self._interval_s):
            self._read()

    def __enter__(self) -> StallWatch:
        """Start sampling and take the first reading before the caller runs."""
        self._read()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Stop sampling, take a final reading, and resolve the rate."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
        self._read()
        self.samples = len(self._samples)
        if not self._samples:
            self.unjudged_reason = (
                "the kernel does not expose a pressure counter, so no window "
                "could be measured"
            )
            return
        self.rate = max_windowed_rate(self._samples, self.window_s)
        if self.rate is None:
            span = self._samples[-1][0] - self._samples[0][0]
            self.unjudged_reason = (
                f"the measurement spanned {span:.2f} s, shorter than the "
                f"{self.window_s:.1f} s window, so its stall rate was not judged"
            )

    @property
    def counter(self) -> str | None:
        """Which pressure counter the readings came from, for the summary line."""
        return self._counter
