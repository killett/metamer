"""The machine identity that `machine_fingerprint` is supposed to be built from.

`machine_fingerprint` answers "what machine is this", so it is an **IDENTITY**
and not a request: it must be populated by reading the machine. Until this task
nothing in `src/` populated it and its three arguments were whatever a caller
passed -- the same shape as `registry_version` before Task 1, and the reason the
allowlist sweep exists.

It reaches `run_hash` alone today, where it is provenance. Design doc section
11.4's calibration cache key reads it, and **at that moment it becomes a gate**:
two machines sharing a fingerprint means one machine's measured bytes-per-series
is reused on the other, against a hard RAM constraint.
"""

from __future__ import annotations

import platform
from typing import Any

import pytest

from metamer.core import machine
from metamer.core.hashing import machine_fingerprint


def test_the_cpu_model_is_a_real_reading_and_not_an_empty_string():
    """`cpu_model()` returns something that names a CPU.

    Bug this catches: `platform.processor()` as the source. **Measured on this
    box it returns `''`** -- as it does on Linux generally -- so every Linux
    machine would share a fingerprint differing only by core count and RAM.
    That fails (a2)'s third fact for an identity field: a change in the thing
    identified must move the field, and a constant cannot.

    The assertion is deliberately about the *property* rather than about this
    host's string, so it holds on any machine the suite runs on.
    """
    model = machine.cpu_model()
    assert isinstance(model, str)
    assert model.strip() != ""


@pytest.mark.machine
def test_the_cpu_model_did_not_fall_back_to_the_architecture():
    """On a Linux box with `/proc/cpuinfo`, the model name is what is read.

    `platform.machine()` -- `'x86_64'` here -- is the last-resort fallback, and
    it is the same string on every x86 machine in the world. If the fallback is
    what fires on an ordinary Linux box then the primary source is broken and
    the fingerprint is again near-constant.

    Marked `machine` because it asserts about the host: a runner without
    `/proc/cpuinfo`, or one whose CPU genuinely reports its architecture as its
    model name, would fail it for a reason that is not a defect.
    """
    if platform.system() != "Linux":
        pytest.skip("the /proc/cpuinfo source is Linux-only")
    assert machine.cpu_model() != platform.machine()


def test_the_core_count_is_physical_and_at_least_one():
    """`physical_cores()` is a usable positive count.

    Bug this catches: `logical=True`, which counts hyperthreads. The fingerprint
    keys a calibration measured in bytes per series, and two boxes with the same
    physical cores and different SMT settings have the same memory behaviour --
    so the logical count would fragment the cache for no reason, and on a box
    where `psutil` returns None for the physical count it would fragment it
    against `None`.
    """
    cores = machine.physical_cores()
    assert isinstance(cores, int)
    assert cores >= 1


@pytest.mark.parametrize(
    ("physical", "logical", "expected"),
    [
        (8, 16, 8),
        (None, 16, 16),
        (None, None, 1),
        (0, 16, 16),
    ],
    ids=["smt-box", "physical-unknown", "both-unknown", "zero-physical"],
)
def test_the_core_count_choice_prefers_physical_and_is_testable_off_this_box(
    physical, logical, expected
):
    """The physical-over-logical choice, on constructed counts.

    **THIS BOX HAS NO SMT** -- `psutil` reports 4 physical and 4 logical -- so a
    test of `physical_cores()` here cannot tell the two apart, and the mutation
    `logical=True` **survived** against one. The choice is arithmetic over two
    numbers, so it moves into its own function and is exercised with the inputs
    an SMT machine would supply.

    Bug this catches: `logical=True`, which on a 32-thread 16-core box
    fingerprints 32 and gives that machine a different section 11.4 cache key
    from an identical box with SMT disabled -- same memory behaviour, two
    calibrations. And `0` as a physical reading falling through as `0`, which is
    a plausible-looking impossibility that would key a cache entry.
    """
    assert machine.choose_core_count(physical, logical) == expected


def test_the_ram_reading_is_a_plausible_total():
    """`total_ram_bytes()` reports total system RAM in BYTES.

    Bug this catches: a kilobyte reading passed off as bytes, which is the
    `ru_maxrss` unit trap one module over. A machine with less than 256 MB of
    total RAM cannot run this package at all, so a reading below that is a unit
    error rather than a small machine.
    """
    total = machine.total_ram_bytes()
    assert isinstance(total, int)
    assert total > 256 * 1024**2


def test_the_fingerprint_is_wired_from_the_platform_and_not_from_a_caller():
    """`machine.fingerprint()` is `machine_fingerprint` over the three readings.

    Bug this catches: a fingerprint built from constants, or from a config. Both
    produce a well-formed 16-hex digest that identifies nothing, which is what
    an identity field self-reported by its consumer looks like from the outside.
    """
    assert machine.fingerprint() == machine_fingerprint(
        machine.cpu_model(), machine.physical_cores(), machine.total_ram_bytes()
    )
    assert len(machine.fingerprint()) == 16


@pytest.mark.parametrize(
    "changed",
    [
        {"cpu_model": "AMD EPYC 7763 64-Core Processor"},
        {"cores": 64},
        {"total_ram_bytes": 256 * 1024**3},
    ],
    ids=["cpu", "cores", "ram"],
)
def test_each_of_the_three_readings_moves_the_fingerprint(changed):
    """All three components reach the digest, asserted one at a time.

    Bug this catches: a component dropped from the payload -- a fingerprint
    ignoring `cpu_model` would give the same key to a 64-core Xeon and a 64-core
    EPYC with the same RAM, and section 11.4's cache would hand one machine's
    bytes-per-series to the other. **One field is not evidence about a set**, so
    each is varied on its own rather than all together.
    """
    base: dict[str, Any] = {
        "cpu_model": machine.cpu_model(),
        "cores": machine.physical_cores(),
        "total_ram_bytes": machine.total_ram_bytes(),
    }
    assert machine_fingerprint(**base) != machine_fingerprint(**{**base, **changed})
