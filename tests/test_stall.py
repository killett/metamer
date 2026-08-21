"""The stall gate's window arithmetic, which is what makes its threshold mean one thing.

**WHY THESE EXIST.** `RSS_STALL_LIMIT_US_PER_S` fired twice in two days, over
windows of **14.1 s and 2.5 s**, and open question 19 records why that is a
defect rather than noise: a rate averaged over whatever block the caller happens
to bracket is **a different gate per caller**, and no value of the constant fixes
that. The repair is a fixed measurement window, and `stall.max_windowed_rate` is
where it lives.

Every test below names the bug it catches. The expected values are hand-computed
from the sample arithmetic and never by running the function.
"""

from __future__ import annotations

import time

import pytest

from tests.stall import STALL_WINDOW_S, StallWatch, max_windowed_rate


def test_a_burst_inside_a_long_block_is_not_diluted_by_the_block() -> None:
    """The maximum over a window, not the average over the caller's block.

    Bug this catches: reverting to `(end - start) / elapsed`, which is what the
    gate did through both of its firings. Twenty seconds carrying one second of
    50 000 us of stall averages to **2 500 us/s** and passes a 50 000 limit by
    twenty times, while the second that actually stalled is at the limit.
    """
    samples = [(float(second), 0.0) for second in range(10)]
    samples += [(10.0, 0.0), (11.0, 50_000.0)]
    samples += [(float(second), 50_000.0) for second in range(12, 21)]

    assert max_windowed_rate(samples, 1.0) == pytest.approx(50_000.0)


def test_one_constant_rate_reads_the_same_at_three_seconds_and_at_thirty() -> None:
    """The reading is a property of the box, not of how long the caller ran.

    Bug this catches: the defect open question 19 names. Under whole-block
    averaging these two are also equal -- so this test alone is not the
    discriminator, and it is here because the pair with the burst test above is:
    an implementation may only satisfy both by using a fixed window.
    """
    short = [(t / 10.0, t * 100.0) for t in range(31)]
    long_run = [(t / 10.0, t * 100.0) for t in range(301)]

    assert max_windowed_rate(short, 1.0) == pytest.approx(1000.0)
    assert max_windowed_rate(long_run, 1.0) == pytest.approx(1000.0)


def test_a_span_shorter_than_the_window_cannot_be_judged_and_says_so() -> None:
    """Too short to judge is `None`, and `None` is not zero.

    Bug this catches: falling back to the whole-block rate when no full window
    exists. That is the fill-value rule at a gate -- "not measured" and "measured
    clean" become one observation, and the caller cannot tell them apart.
    """
    assert max_windowed_rate([(0.0, 0.0), (0.5, 900.0)], 1.0) is None
    assert max_windowed_rate([(0.0, 0.0)], 1.0) is None
    assert max_windowed_rate([], 1.0) is None


def test_a_span_of_exactly_one_window_is_admissible() -> None:
    """The boundary is inclusive.

    Bug this catches: `span > window` instead of `span >= window`, which returns
    `None` for a block exactly one window long -- disabling the gate on precisely
    the shortest blocks it is meant to judge, and doing it silently.
    """
    assert max_windowed_rate([(0.0, 0.0), (1.0, 4_000.0)], 1.0) == pytest.approx(4000.0)


def test_the_rate_uses_timestamps_and_not_sample_indices() -> None:
    """Sampling is not guaranteed regular, and a loaded box is when it is not.

    Bug this catches: dividing by `count * interval`. Samples at 0.0, 0.1 and
    3.0 with 30 000 us arriving at the last one give 30 000 / 2.9 =
    **10 344.83 us/s** from the 0.1 s sample and 10 000.0 from the 0.0 s one; an
    index-based implementation reports 15 000 (two intervals of one second).
    """
    samples = [(0.0, 0.0), (0.1, 0.0), (3.0, 30_000.0)]

    assert max_windowed_rate(samples, 1.0) == pytest.approx(30_000.0 / 2.9)


def test_no_stall_over_a_long_enough_span_is_zero_rather_than_unjudgeable() -> None:
    """A quiet box returns a number.

    Bug this catches: returning `None` whenever the counter did not move, which
    would make every clean measurement indistinguishable from an unjudgeable one
    and quietly stop the gate from ever passing anything.
    """
    assert max_windowed_rate([(0.0, 7.0), (2.0, 7.0)], 1.0) == 0.0


def test_the_watch_sees_a_counter_that_moves() -> None:
    """The positive control: an instrument that reads nothing looks like a quiet box.

    Bug this catches: a watch wired to a reader it never calls, or one whose
    samples never reach `max_windowed_rate`. Both produce "clean" forever, which
    is the failure mode a gate cannot report on itself. The reader here is a
    stand-in for `/sys/fs/cgroup/memory.pressure` -- a true external boundary --
    and it advances by 100 000 us per sample, so any window at all must come back
    positive.
    """
    ticks = [0.0]

    def reader() -> tuple[float, str]:
        ticks[0] += 100_000.0
        return ticks[0], "test"

    with StallWatch(reader=reader, interval_s=0.01, window_s=0.05) as watch:
        time.sleep(0.3)

    assert watch.rate is not None
    assert watch.rate > 0.0
    assert watch.samples >= 5


def test_the_watch_abstains_on_a_block_shorter_than_its_window() -> None:
    """Abstention is a third state and it is reported, never rounded to clean.

    Bug this catches: a watch that judges a 20 ms block against a limit derived
    from second-scale windows. That is the caller-dependent sensitivity open
    question 19 exists to remove, reappearing at the short end.
    """
    with StallWatch(
        reader=lambda: (0.0, "test"), interval_s=0.01, window_s=5.0
    ) as watch:
        time.sleep(0.05)

    assert watch.rate is None
    assert watch.unjudged_reason is not None
    assert "window" in watch.unjudged_reason


def test_the_shipped_window_is_a_second_and_the_constant_is_what_sets_it() -> None:
    """The policy value is a constant here, not a literal at each call site.

    Bug this catches: a caller passing its own window, which is the original
    defect wearing new clothes -- sensitivity would again be set by the caller.
    `StallWatch`'s default must be the module constant.
    """
    assert STALL_WINDOW_S == 1.0
    with StallWatch(reader=lambda: (0.0, "test"), interval_s=0.01) as watch:
        time.sleep(0.01)

    assert watch.window_s == STALL_WINDOW_S
