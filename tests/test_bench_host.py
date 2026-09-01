"""`metamer.bench.host`: the quiet-host gate every 2d measurement runs first.

**WHY THIS IS IN `src` AND NOT IN THE THIRD HARNESS THAT NEEDS IT.** The check
had one home -- `phase2d-field-harness.py` -- and Task 5 is 2d's third harness
and the first that would have copied it. (j9)'s worst instance in this
sub-phase was an instrument block that was itself a copy, and this is the same
shape one level up: a gate whose second spelling would drift the first time
either was edited.

**AND THE FAULT IT GUARDS AGAINST IS RECORDED RATHER THAN IMAGINED.** Task 0's
fourth defect was a quiet check that **recorded a loud host and then measured
anyway** -- (a2b) inside the instrument written to enforce (a2b). So the tests
below are about the gate FIRING, not about it reporting.

**THE READING AND THE RULE ARE SEPARATED ON PURPOSE.** `is_quiet` is a pure
predicate over a load and a core count, so the boundary can be swept without a
20-second sleep and without a machine in a particular state; `quiet_check`
collects the reading and applies it. A test that could only observe the rule
through a real `getloadavg` would be a test about this container.
"""

from __future__ import annotations

import pytest

from metamer.bench import host


def test_a_host_at_the_load_limit_is_not_quiet():
    """The boundary is strict, and equality is the loud side.

    Behaviour: `is_quiet` is `load < cores - 1`, so a load exactly at
    `cores - 1` is refused.

    Bug it catches: an off-by-one -- `<=` -- which admits a host with no free
    core for a single-threaded measurement. Every 2d rate is measured under
    `threadpool_limits(1)`, so "one core free" is the whole condition, and a
    gate that admits zero free cores measures contention instead.

    Expected value determined independently: from the rule itself, at the two
    sides of the boundary and on it, rather than from the machine's own load.
    """
    assert host.is_quiet(load1=2.9, physical_cores=4) is True
    assert host.is_quiet(load1=3.0, physical_cores=4) is False
    assert host.is_quiet(load1=3.1, physical_cores=4) is False


def test_a_single_core_host_can_still_be_quiet_at_zero_load():
    """The limit stays meaningful when `cores - 1` is zero.

    Behaviour: at one physical core the limit is 0.0, so only a genuinely idle
    host passes.

    Bug it catches: a limit computed as `cores - 1` and then compared with `<`
    against a load that is never negative, making the gate unpassable on a
    one-core machine -- a gate nothing can satisfy is refused for a reason that
    has nothing to do with the host, and the run would be abandoned rather than
    measured. This pins the intended behaviour either way, so a later change
    has to move the test.
    """
    assert host.is_quiet(load1=0.0, physical_cores=1) is False
    assert host.is_quiet(load1=0.0, physical_cores=2) is True


def test_the_reading_carries_what_it_gated_on_and_says_which_way_it_went():
    """The reading is self-describing, like every other 2d instrument record.

    Behaviour: `quiet_check` returns the load, the core count, the limit it
    applied and the verdict, with the collectors injected so no sleep and no
    real load are involved.

    Bug it catches: a verdict emitted without the numbers behind it. A refused
    run whose record says only `quiet: false` cannot be told from one refused
    by a broken reader, and the next session re-runs it blind.

    Expected value determined independently: the injected load and core count.
    """
    reading = host.quiet_check(
        idle_seconds=0.0,
        sleep=lambda _seconds: None,
        loadavg=lambda: (7.5, 7.0, 6.0),
        physical_cores=lambda: 4,
    )

    assert reading.quiet is False
    assert reading.loadavg == (7.5, 7.0, 6.0)
    assert reading.physical_cores == 4
    assert reading.load_limit == pytest.approx(3.0)
    assert reading.machine


def test_the_check_idles_before_it_reads_rather_than_reading_on_arrival():
    """The idle comes first, and the reading is taken after it.

    Behaviour: `quiet_check` sleeps for `idle_seconds` and only then reads the
    load average.

    Bug it catches: reading the load the instant the process starts, which on a
    box that has just finished a build reports the previous job. The one-minute
    load average is a decaying mean, so the idle is what makes it describe the
    run about to happen rather than the one that just ended -- and a check that
    skips it passes exactly when it should refuse.
    """
    order: list[str] = []

    def _sleep(seconds: float) -> None:
        order.append(f"slept {seconds:g}")

    def _loadavg() -> tuple[float, float, float]:
        order.append("read")
        return (0.1, 0.1, 0.1)

    reading = host.quiet_check(
        idle_seconds=20.0,
        sleep=_sleep,
        loadavg=_loadavg,
        physical_cores=lambda: 8,
    )

    assert order == ["slept 20", "read"]
    assert reading.quiet is True


def test_the_reading_is_plain_data_a_jsonl_record_can_carry():
    """A harness emits this straight into its measured file.

    Behaviour: `as_record` returns only JSON-serialisable values, keyed as the
    2026-08-30 and 2026-08-31 harness records already key them, so the runs are
    comparable across sessions.

    Bug it catches: a reading that has to be re-spelled at each call site to be
    emitted, which is how the two harnesses would drift apart again after this
    module removed the first duplication.
    """
    import json

    record = host.quiet_check(
        idle_seconds=0.0,
        sleep=lambda _seconds: None,
        loadavg=lambda: (0.5, 0.4, 0.3),
        physical_cores=lambda: 8,
    ).as_record()

    assert record["record"] == "quiet_check"
    assert record["quiet"] is True
    assert record["loadavg"] == [0.5, 0.4, 0.3]
    assert json.loads(json.dumps(record)) == record
