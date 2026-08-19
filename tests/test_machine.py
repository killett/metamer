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
from pathlib import Path
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


def test_available_ram_is_a_byte_reading_and_is_not_the_total():
    """`available_ram_bytes()` reports FREE memory in bytes, for a warning only.

    Expected values determined independently: `psutil` reports both figures in
    bytes, and Linux's `MemAvailable` is strictly below `MemTotal` on any
    running system -- the kernel's own structures are not available to anyone.
    Both sides are read from `psutil` here rather than from
    `machine.total_ram_bytes`, which is cgroup-aware: inside a container the
    limit can sit below the host's free memory, and this relation is about the
    reading rather than about the allowance.

    Bug this catches: `.total` where `.available` was meant -- one attribute
    apart on the same call, and the symptom is silence rather than an error,
    because the budget is a fraction of total and a warning comparing total
    against a fraction of total can never fire. And the `ru_maxrss` unit trap
    this module exists for, one function over: a kilobyte reading passed off as
    bytes would still be positive and still look plausible.
    """
    import psutil

    reading = psutil.virtual_memory()
    available = machine.available_ram_bytes()

    assert isinstance(available, int)
    assert 0 < available <= int(reading.total)
    assert available != int(reading.total)


@pytest.mark.machine
def test_this_machine_has_no_cgroup_limit_so_the_fixtures_below_are_constructed():
    """The environment cannot express the defect, so it is recorded that it cannot.

    Measured 2026-08-15: `/sys/fs/cgroup/memory.max` holds the literal `max`, so
    the host reading and the cgroup reading coincide and **every test in this
    suite would pass against a `total_ram_bytes` that ignored cgroups
    entirely.** That is the same shape as the defect being guarded, so this test
    exists to make the gap visible rather than to check a behaviour.

    Same class as `choose_core_count` (no SMT here) and `library_table` (one
    OpenBLAS here): the constructed fixtures below are the only evidence, and a
    reader who does not know that would take a green suite as coverage.
    """
    assert machine.ram_basis() == machine.RamBasis.HOST
    assert machine.total_ram_bytes() == machine._resolve_total_ram()[0]


@pytest.mark.parametrize(
    ("v2", "v1", "expected_basis"),
    [
        ("max", None, machine.RamBasis.HOST),
        (None, None, machine.RamBasis.HOST),
        ("2147483648", None, machine.RamBasis.CGROUP_V2),
        (None, "2147483648", machine.RamBasis.CGROUP_V1),
        # v1's no-limit sentinel, which needs no special case: it loses the min.
        (None, "9223372036854771712", machine.RamBasis.HOST),
        # A limit above the host's memory is not a limit that binds.
        ("1099511627776", None, machine.RamBasis.HOST),
        # Both mounted and disagreeing: the smaller one is the one that kills.
        ("4294967296", "2147483648", machine.RamBasis.CGROUP_V1),
    ],
    ids=["v2-max", "absent", "v2-limit", "v1-limit", "v1-sentinel", "generous", "both"],
)
def test_total_ram_respects_a_cgroup_limit_and_records_which_reading_won(
    tmp_path, monkeypatch, v2, v1, expected_basis
):
    """A container's allowance beats the host reading, and the basis says so.

    **CONSTRUCTED, because this machine has no limit.** Each case writes the
    file the kernel would write and asserts both the value and the basis.

    Expected values determined independently: `psutil` reads the host through
    `/proc/meminfo`, which inside a container reports the machine and not the
    allowance, so the answer is `min(host, any readable limit)`. 2 GiB is
    2 147 483 648 and is below any host this can run on; 1 TiB is above it;
    v1's no-limit sentinel is `9223372036854771712`, and it is handled by the
    same `min` rather than by naming it.

    Bug this catches: a 2 GB container on a 128 GB host sizing its tiles for
    128 GB. **The consequence is an OOM kill, not a slow run**, and nothing in
    the process would report it -- the budget default, the derived tile side and
    the provenance would all be internally consistent and all wrong.

    **And the basis is asserted beside the value in every case**, because the
    two come from one computation and a label that can drift from its number is
    a name rather than a report.
    """
    for name, value in (("CGROUP_V2_PATH", v2), ("CGROUP_V1_PATH", v1)):
        path = tmp_path / name
        if value is not None:
            path.write_text(value + "\n")
        monkeypatch.setattr(machine, name, str(path))

    import psutil

    host = int(psutil.virtual_memory().total)
    total, basis = machine._resolve_total_ram()

    if expected_basis is machine.RamBasis.HOST:
        assert total == host
    else:
        assert total == int(v2 if expected_basis is machine.RamBasis.CGROUP_V2 else v1)
        assert total < host
    assert basis == expected_basis
    # The public pair moves together, which is the whole reason they share a
    # computation: a `ram_basis` that read the filesystem again could report a
    # basis that did not produce the number recorded beside it.
    assert machine.total_ram_bytes() == total
    assert machine.ram_basis() == expected_basis


def test_a_cgroup_limit_moves_the_fingerprint_and_therefore_the_run_hash(
    tmp_path, monkeypatch
):
    """Two containers of different sizes no longer share a calibration key.

    **This was (a2)'s third fact failing** -- a change in the thing identified
    not moving the field. `machine.fingerprint()` takes `total_ram_bytes()`, so
    while that read the host, a 2 GB container and a 32 GB container on one host
    were the same machine as far as the fingerprint was concerned, and Task 5's
    calibration cache would serve one's measured bytes-per-series to the other.

    Expected value determined independently: the fingerprint is
    `machine_fingerprint(cpu_model, cores, total_ram_bytes)`, so changing the
    third argument must change the digest -- which the parametrized test above
    already pins for a hand-supplied value. This asserts the wiring: the change
    arrives through the *reading*, not through a caller.

    Bug this catches: `fingerprint()` keeping a separate, host-only RAM reading
    after `total_ram_bytes` became cgroup-aware, which would leave the gap
    exactly where it was while looking fixed.
    """
    host_fingerprint = machine.fingerprint()

    limited = tmp_path / "memory.max"
    limited.write_text("2147483648\n")
    monkeypatch.setattr(machine, "CGROUP_V2_PATH", str(limited))
    monkeypatch.setattr(machine, "CGROUP_V1_PATH", str(tmp_path / "absent"))

    assert machine.total_ram_bytes() == 2147483648
    assert machine.fingerprint() != host_fingerprint
    assert machine.fingerprint() == machine_fingerprint(
        machine.cpu_model(), machine.physical_cores(), 2147483648
    )


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
    "field, perturb",
    [
        ("cpu_model", lambda reading: reading + " (perturbed)"),
        ("cores", lambda reading: reading + 1),
        ("total_ram_bytes", lambda reading: reading + 1024**3),
    ],
    ids=["cpu", "cores", "ram"],
)
def test_each_of_the_three_readings_moves_the_fingerprint(field, perturb):
    """All three components reach the digest, asserted one at a time.

    Bug this catches: a component dropped from the payload -- a fingerprint
    ignoring `cpu_model` would give the same key to a 64-core Xeon and a 64-core
    EPYC with the same RAM, and section 11.4's cache would hand one machine's
    bytes-per-series to the other. **One field is not evidence about a set**, so
    each is varied on its own rather than all together.

    **THE PERTURBATION IS DERIVED FROM THE LIVE READING, NEVER A CONSTANT.**
    It used to be a literal `"AMD EPYC 7763 64-Core Processor"`, `64` cores and
    256 GiB -- and on 2026-08-19 CI ran on an EPYC 7763, where the "changed"
    payload WAS the base payload, both digests were `a4efc574e619bf2c`, and the
    test failed on a machine that had done nothing wrong. A constant asserts a
    difference only on hosts that happen not to match it; `reading + 1` asserts
    it everywhere. The assertion is unchanged in strength: the perturbed field
    still differs in exactly one component.
    """
    base: dict[str, Any] = {
        "cpu_model": machine.cpu_model(),
        "cores": machine.physical_cores(),
        "total_ram_bytes": machine.total_ram_bytes(),
    }
    changed = {field: perturb(base[field])}
    assert changed[field] != base[field]
    assert machine_fingerprint(**base) != machine_fingerprint(**{**base, **changed})


# --------------------------------------------------------------------------
# The validity instrument for RSS differences
# --------------------------------------------------------------------------


def test_the_memory_stall_counter_is_cumulative_and_names_its_source() -> None:
    """A reading is microseconds since boot, and says which file it came from.

    Expected values determined independently from the kernel's PSI contract:
    `total` is a cumulative microsecond counter that never decreases, and the
    cgroup file is preferred over the host file because **on a shared host the
    host counter moves for other tenants' reasons** and cannot gate our
    measurement.

    Bug this catches: a reading that goes BACKWARDS between two calls on one
    boot -- a counter reset, a source that changes underfoot, a parse that
    picks a different field on the second call. `conftest.rss_validity`
    differences two of these, and a difference of a non-monotonic quantity is
    not a rate.

    **WHAT THIS TEST DELIBERATELY NO LONGER ASSERTS IS `value > 0`.** A quiet
    host really has accrued zero full-stall microseconds; CI hit exactly that
    on 2026-08-19 and failed against a correct reading. The `avg10`-versus-
    `total` discrimination that `> 0` stood in for now lives in
    `test_the_reading_is_the_total_field_of_the_full_line`, where the file
    content is written by hand and the right answer is known.
    """
    first = machine.memory_stall_us()
    if first is None:  # pragma: no cover - kernels without PSI
        pytest.skip("this kernel exposes no pressure stall information")
    second = machine.memory_stall_us()

    assert second is not None
    value, source = second
    assert source in {"cgroup", "host"}
    assert value >= first[0]


def test_the_reading_is_the_total_field_of_the_full_line(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`total` off the `full` line, against a file whose every field differs.

    **THIS IS WHERE THE avg10 BUG IS CAUGHT, AND IT USED TO BE NOWHERE.** The
    live test above asserted `value > 0` as a proxy for "this is a cumulative
    counter" -- but a quiet host has genuinely accrued zero full-stall
    microseconds, which is exactly what a GitHub runner reported on 2026-08-19,
    and the suite failed against a correct reading. The proxy is gone and the
    property it stood for is asserted here instead, on synthetic content where
    the answer is known rather than sampled.

    Expected value determined independently: the fixture is written by hand so
    that `total` on the `full` line is `123456789` and every other number in
    the file -- both averages on that line, and every field of the `some` line,
    including ITS total -- is different. Only one reading is correct.

    Bug this catches: reading `avg10` (which would return 4, an unusable
    percentage), reading the `some` line (987654321, which counts time ANY task
    stalled and is nonzero on any busy box), or splitting the fields wrongly.
    """
    pressure = tmp_path / "memory.pressure"
    pressure.write_text(
        "some avg10=12.34 avg60=23.45 avg300=34.56 total=987654321\n"
        "full avg10=4.00 avg60=5.00 avg300=6.00 total=123456789\n"
    )
    monkeypatch.setattr(machine, "MEMORY_PRESSURE_PATHS", (("cgroup", str(pressure)),))

    assert machine.memory_stall_us() == (123456789, "cgroup")


def test_the_cgroup_counter_is_preferred_over_the_host_counter(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """With both files readable, the cgroup one decides.

    Expected value determined independently from the reason the preference
    exists, stated in `memory_stall_us`'s own docstring: **on a shared host the
    host counter moves for other tenants' reasons**, so gating our RSS
    measurements on it would fail runs for pressure we did not cause. The two
    fixtures carry different totals so the winner is identifiable.

    Bug this catches: `MEMORY_PRESSURE_PATHS` reordered, or a loop that reads
    every path and returns the last -- either of which silently swaps the
    instrument for one that answers a different question.
    """
    cgroup = tmp_path / "cgroup.pressure"
    host = tmp_path / "host.pressure"
    cgroup.write_text("full avg10=0.00 avg60=0.00 avg300=0.00 total=111\n")
    host.write_text("full avg10=0.00 avg60=0.00 avg300=0.00 total=222\n")
    monkeypatch.setattr(
        machine,
        "MEMORY_PRESSURE_PATHS",
        (("cgroup", str(cgroup)), ("host", str(host))),
    )

    assert machine.memory_stall_us() == (111, "cgroup")

    cgroup.unlink()

    assert machine.memory_stall_us() == (222, "host")


def test_an_absent_pressure_file_reads_as_unknown_and_not_as_no_pressure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No counter is None, never zero.

    **THIS IS THE FILL-VALUE RULE AT A GATE.** Zero is the value that means "no
    pressure at all", so a missing file defaulting to zero would certify every
    RSS measurement on a kernel that cannot report pressure -- the strongest
    possible clean bill of health, issued by an instrument that read nothing.

    Expected value determined independently: PSI needs `CONFIG_PSI` and a
    cgroup-v2 mount, so its absence is a real state on real kernels rather than
    a hypothetical.

    Bug this catches: `except OSError: return 0`, which is the obvious defensive
    line and is the one that makes the gate vacuous where it matters most.
    """
    monkeypatch.setattr(machine, "MEMORY_PRESSURE_PATHS", (("cgroup", "/nonexistent"),))

    assert machine.memory_stall_us() is None
