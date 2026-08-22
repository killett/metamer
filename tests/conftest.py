"""Shared fixtures for the whole suite.

`RaisingStubEngine` lives here rather than inside one test module because three
separate Phase 2a consumers need the identical construction, and three copies of
a stub is one that disagrees with itself once:

  - Task 12: the ``--reuse-fits-from`` recompute path ran no fits.
  - Task 11: a resumed run did not refit tiles the completion bitmap says are
    already complete.
  - Task 11/12: a compat-only rewrite touched nothing upstream of ``/selection/``.

**Why a stub and not a timer.** All three claims are negatives, and timing cannot
falsify a negative -- a run that is merely fast is indistinguishable from a run
that fitted nothing, and the difference is exactly what these tasks exist to
establish. A raising stub turns the negative into an exception.

**THE INJECTION SEAM IS ``fit(..., engine=...)``.** ``fit`` takes
``engine: Engine | None = None`` and substitutes ``KalmanEngine()`` when it is
None, so a test that leaves the argument out proves nothing about the stub --
it exercises the default. Any later runner that obtains its engine internally
from the config instead of accepting an injected one makes this fixture
undeliverable, so the seam is a requirement on those tasks and not an
implementation detail of this one.

**THE STUB IS SILENT WHEN THE ENGINE IS NEVER REACHED**, which is not a defect
in the stub and is not hypothetical -- see
``tests/test_stub_engine.py`` for the measured case and for the guard that keeps
the limit executable rather than advisory.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pytest
from numpy.typing import NDArray

from metamer.core.capability import EngineId, Objective
from metamer.core.engines.protocol import ScoredResult
from metamer.core.statespace import StateSpace


class StubEngineCalled(RuntimeError):
    """Raised by `RaisingStubEngine.score`, so "no fit ran" is falsifiable."""


@dataclass
class RaisingStubEngine:
    """An `Engine` whose `score` always raises.

    TAGGED `EngineId.KALMAN` DELIBERATELY. Every score carries an engine tag and
    ranking across tags is a hard error rather than a warning, so a stub tagged
    with some other member would make a consumer's test fail inside that refusal
    instead of inside the assertion it was written for -- and a test that fails
    for the wrong reason still passes review. The stub stands in for the engine
    it replaces, so it wears that engine's tag.

    `calls` records every invocation's argument names, so a test that wants to
    assert *which* call was reached has something to read. It is appended to
    before the raise, because after it there is no after.

    Attributes:
        engine_id: The protocol's non-method member. Check conformance with
            `isinstance`, never `issubclass` -- a `runtime_checkable` protocol
            with a data member raises `TypeError` from the latter by design.
        calls: One entry per `score` call, in order.
    """

    engine_id: EngineId = EngineId.KALMAN
    calls: list[dict[str, object]] = field(default_factory=list)

    def score(
        self,
        state_space: StateSpace,
        theta: NDArray[np.float64],
        y: NDArray[np.float64],
        mask: NDArray[np.bool_],
        t: NDArray[np.float64],
        design: NDArray[np.float64] | None,
        objective: Objective = Objective.ML,
    ) -> ScoredResult:
        """Record the call and raise.

        Args:
            state_space: The state space being scored.
            theta: Natural-coordinate parameters, shape (B, p).
            y: Observations, shape (B, N).
            mask: Presence mask, shape (B, N).
            t: Time axis, shape (N,), in decimal years.
            design: The design matrix, or None when there is no design. This is
                an ARRAY, not a `DesignInfo` -- the narrowing object never
                reaches an engine.
            objective: ML or REML.

        Returns:
            Never returns.

        Raises:
            StubEngineCalled: Always.
        """
        self.calls.append(
            {
                "batch": int(y.shape[0]),
                "n_time": int(y.shape[1]),
                "objective": objective,
                "has_design": design is not None,
            }
        )
        raise StubEngineCalled(
            f"a fit reached the engine: batch={y.shape[0]}, "
            f"objective={objective.value}, has_design={design is not None}"
        )


@pytest.fixture
def raising_engine() -> RaisingStubEngine:
    """A fresh `RaisingStubEngine` per test, so `calls` never leaks between them."""
    return RaisingStubEngine()


#: The floor a test gets unless it asks for the real one.
#:
#: **1 MB, WHICH NO PROCESS THAT IMPORTS NUMPY COULD EVER HOLD** -- the measured
#: floor is ~228 MB -- so a value read from here can never be mistaken for a
#: measurement, and an assertion that accidentally depends on one fails review
#: rather than passing as evidence.
#:
#: **AND IT IS SMALL ON PURPOSE, NOT ARBITRARILY.** Since Phase 2b Task 2 the
#: block is `(budget - floor) x (1 - headroom)`, so the floor sets the smallest
#: budget a fixture can ask for. A realistic 228 MB stub would push every
#: tile-side fixture's budget into that range and bury the arithmetic those
#: fixtures exist to express.
STUB_FLOOR_PEAK = 1_000_000

STUB_FLOOR_COMPONENTS = {
    "interpreter_numpy": 400_000,
    "xarray_zarr": 600_000,
    "metamer_batch_run": 700_000,
    "numba_threading_layer": 800_000,
    "kalman_kernel_warm": 900_000,
    "input_open": STUB_FLOOR_PEAK,
}


@pytest.fixture(scope="session", autouse=True)
def _stub_the_floor_probe_for_the_session():
    """Patch the floor probe for the whole session, before any fixture runs.

    **SESSION-SCOPED BECAUSE MODULE-SCOPED FIXTURES BUILD STORES.** A
    function-scoped autouse fixture is ordered *after* every higher-scoped one,
    so `test_resume.py`'s module-scoped store was built with the real probe and
    its budget -- chosen against the stub floor -- was refused. Measured, and it
    is the ordering rule rather than a race.

    Yields:
        Nothing; the patch is undone at session end.
    """
    from metamer.batch import run as run_module
    from metamer.core.memory import FloorReport

    stub = FloorReport(
        pre_warm_bytes=STUB_FLOOR_COMPONENTS["metamer_batch_run"],
        post_warm_bytes=STUB_FLOOR_COMPONENTS["kalman_kernel_warm"],
        with_input_bytes=STUB_FLOOR_COMPONENTS["input_open"],
        peak_bytes=STUB_FLOOR_PEAK,
        components=dict(STUB_FLOOR_COMPONENTS),
    )
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(run_module, "measure_floor", lambda **_kwargs: stub)
        # **AND THE SAME NUMBER OUT OF PROCESS.** A subprocess inherits the
        # environment but not the patch, and since Task 2 the tile side is a
        # function of the floor -- so a CLI-driven test would derive a different
        # side from the in-process one, and no choice of budget could fix it:
        # the window that selects a small side is a few kB wide while a measured
        # floor varies by megabytes. `run()` reads this variable when no floor is
        # supplied, and an overridden floor records itself in provenance as
        # `components={"override": N}`.
        patch.setenv(run_module.FLOOR_OVERRIDE_ENV, str(STUB_FLOOR_PEAK))
        yield


@pytest.fixture(autouse=True)
def _stub_the_floor_probe(request, monkeypatch):
    """Restore `run()`'s real floor probe for a test that asks for it.

    **THE PROBE IS A CHILD PROCESS THAT IMPORTS NUMBA AND OPENS THE INPUT**, and
    `run()` measures one per call because the floor is deliberately never
    cached. There are ~80 `run()` call sites in this suite and almost none of
    them are about the floor; paying ~10 s each would put ~15 minutes on the
    sweep to re-measure one number eighty times.

    **A DEFAULT-STUBBED SEAM IS THE (i2) HAZARD IN PERSON**, so it is paired:
    `test_memory.py` drives the real `measure_floor` directly -- it imports from
    `metamer.core.memory` and is untouched by this patch -- and
    `test_runner.py::test_a_run_measures_its_own_floor_when_none_is_supplied`
    carries `@pytest.mark.real_floor` and asserts the DEFAULT path produces a
    plausible ladder and puts it in provenance. Without that pair, "the floor
    reached the store" would be satisfied by a probe that never runs.

    Args:
        request: pytest's request, read for the `real_floor` marker.
        monkeypatch: pytest's patcher.
    """
    if request.node.get_closest_marker("real_floor") is None:
        return

    # THE OPT-OUT, AND IT IS THE HALF THAT CAN FAIL. Undo the session patch for
    # this test only, so `run()` spawns its real probe and the seam is exercised
    # rather than merely present.
    import metamer.core.memory as memory_module
    from metamer.batch import run as run_module

    monkeypatch.setattr(run_module, "measure_floor", memory_module.measure_floor)
    monkeypatch.delenv(run_module.FLOOR_OVERRIDE_ENV, raising=False)


# --------------------------------------------------------------------------
# The validity gate for RSS-difference measurements
# --------------------------------------------------------------------------

#: POLICY. **A THRASHING GATE, READ OVER A FIXED WINDOW.** Microseconds of full
#: memory stall per second above which an RSS-difference reading is INDETERMINATE
#: rather than pass or fail, taken as the **maximum over any
#: `stall.STALL_WINDOW_S` window inside the measurement** -- never as an average
#: over whatever block the caller brackets, which is the defect open question 19
#: removed. One limit, one meaning, at every call site.
#:
#: **WHAT IT CAN AND CANNOT SEE, CORRECTED 2026-08-21 AND WEAKER THAN IT WAS
#: WRITTEN.** Task 8a established that quiet reclaim costs no stall and concluded
#: the gate is blind to it; the constructed known-bad reproduces that reading
#: whole-block -- **0.2 ms/s over 600 s** -- and reads **61.3 ms/s over its worst
#: second**. **So the blindness was partly DILUTION and not only definition.**
#: What still holds: the counter is **per-cgroup**, so a firing does not
#: establish that the measured PROCESS waited, and reclaim caused from outside
#: this cgroup leaves it nothing to attribute. `rss_validity`'s
#: `reference_bytes` remains the condition that witnesses the subject itself,
#: and the two are not interchangeable.
#:
#: **AN RSS DIFFERENCE HAS A VALIDITY CONDITION AND THESE TESTS USED TO ASSUME
#: IT.** Resident set size counts what a process currently holds; reclaim takes
#: pages away without the process acting, so a difference of two readings
#: understates by whatever left in between. Observed 2026-08-16: two
#: `machine`-marked tests failed inside a 3502 s sweep at host load 12-16 with
#: swap **100% full** -- the floor ladder measured numba's threading layer at
#: **5.8 MB against a recorded 43.2**, and two peaks that must agree within
#: 16 MB came out **36.1 MB** apart -- and both passed in isolation minutes
#: later on the same box.
#:
#: **THE VALUE IS NOW BOUNDED ON BOTH SIDES BY MEASUREMENT, WHICH IS NEW.** Every
#: earlier version of this number was a multiple of idle -- a distance from
#: known-good with nothing on the other side. The four cells and their readings
#: are in [`oq19-gate-validation.md`](../docs/superpowers/notes/oq19-gate-validation.md),
#: once; in one line, **a full clean sweep's worst window is 0.2 ms/s and the two
#: constructed known-bads are 61.3 and 76.5 ms/s.** 25 ms/s sits **125x above the
#: sweep** and **2.5x below the nearer known-bad**.
#:
#: **THE ASYMMETRY, AND BOTH DIRECTIONS STILL COST SOMETHING.** Too loose and a
#: corrupted measurement is asserted as a fact. Too tight and these tests stop
#: running, which is how a `machine` test decays into one nobody notices. **The
#: tie is broken by making INDETERMINATE loud** -- a gate that is too tight
#: announces itself in the summary and gets re-run, a gate that is too loose is
#: silent -- so the bias is toward tight, and 25 000 is the tighter of the two
#: values the measurements admit.
#:
#: **EXPECT IT TO FIRE MORE OFTEN THAN THE OLD ONE DID, AND THAT IS THE REPAIR
#: WORKING.** The firings of 2026-08-19 and 2026-08-20 read 53 and 58 ms/s as
#: whole-block averages over 14.1 s and 2.5 s; the same events under a windowed
#: maximum read far higher. **If it starts firing on most runs the repair is the
#: box or the fixture, never the number** -- widening it is how the tests stop
#: running.
#:
#: **AND IF YOU ARE HERE TO MAKE IT A GATE AGAIN, READ THIS FIRST.** Two full
#: sweeps of the same suite on the same box, hours apart, no code between them:
#: `the floor ladder's rungs` read **0.4 ms/s** in one and **576.0 ms/s** in the
#: other, **and its assertion passed both times.** A statistic that swings three
#: orders of magnitude on an unchanged workload, while the thing it is supposed
#: to be reporting on does not move, cannot decide whether a measurement is
#: sound. **That is the datum the demotion rests on** -- not the argument about
#: cgroup attribution, which only explains it.
RSS_STALL_LIMIT_US_PER_S = 25_000

#: Every indeterminate measurement this session, for the terminal summary.
#: **A SKIP NOBODY SEES IS HOW A MACHINE-MARKED TEST DECAYS INTO ONE THAT NEVER
#: RUNS**, so the count and the reasons are reported at the end of the run.
INDETERMINATE_RSS: list[str] = []


@dataclass
class RssMeasurement:
    """One bracketed measurement, its governing gate, and its stall diagnostic.

    **PER ASSERTION AND NOT PER COUNT.** A summary that reports *"2
    INDETERMINATE"* says how many and never which, so an assertion that has not
    run for three sweeps is indistinguishable from one that skipped once. The
    name is carried so the reader can tell a permanent abstention from a
    transient one.

    Attributes:
        what: The measurement's name, as the caller gave it.
        gate: `witness` where a reference was supplied and the reclaim witness
            governs, `margin` where none was and the assertion is carried by the
            size of its own window.
        stall_us_per_s: The worst windowed rate, or None when the block was too
            short to hold a window.
        stall_flagged: Whether that rate is above `RSS_STALL_LIMIT_US_PER_S`.
            **Never a verdict** -- see the constant's docstring for why the stall
            statistic cannot tell an allocator from a victim.
        indeterminate: Whether the witness refused to judge.
        reason: The witness's reason, when it refused.
    """

    what: str
    gate: str
    stall_us_per_s: float | None
    stall_flagged: bool
    indeterminate: bool
    reason: str | None = None


#: Every bracketed measurement this session, in order.
RSS_MEASUREMENTS: list[RssMeasurement] = []

#: Lines a test wants in the terminal summary whatever its verdict.
#:
#: **THE ONLY CHANNEL THAT REACHES A CI LOG FROM A PASSING TEST.** pytest hides
#: stdout for tests that pass, so a diagnostic printed inside one is invisible
#: exactly where it is needed -- on hardware nobody can attach to. The summary
#: hook prints unconditionally, which is what makes a number measurable on a
#: runner rather than only on a box someone owns.
DIAGNOSTIC_LINES: list[str] = []


@contextlib.contextmanager
def rss_validity(
    what: str,
    *,
    reference_bytes: float | None = None,
    witness: Callable[[], float] | None = None,
) -> Iterator[None]:
    """Bracket an RSS-difference measurement and refuse to judge an invalid one.

    **INDETERMINATE IS NOT PASS AND NOT FAIL**, which is the same shape as
    `calibration.unusable_reason`: a measurement outside its validity range is
    recorded, not used. The assertions inside the block never run when the
    condition fails, so a reading taken under reclaim can neither confirm nor
    refute what it was measuring.

    **TWO CONDITIONS, BECAUSE ONE OF THEM IS BLIND TO THE FAILURE THAT MATTERS.**
    The stall rate below is a gate on **thrashing** and Phase 2b Task 8a measured
    that it cannot see **quiet reclaim**: a run that lost 85 MB read 0.0876 ms/s,
    below the idle baseline. `reference_bytes` adds the condition that can --
    `machine.reclaim_shortfall_bytes`, validated in Task 8i against a 2x2 over
    memory pressure and elapsed time, where clean runs sat 5.69-6.32 MB **above**
    their reference and the damaged one 129.50 MB **below** it.

    **IT IS OPTIONAL BECAUSE MOST CALLERS CANNOT SUPPLY IT HONESTLY.** The
    witness must be read **in the process that took the measurement**, and this
    repo's RSS measurements are taken in children; a reference here describes the
    *test* process. So it is supplied only where the assertion is about this
    process, and the survey in `PROGRESS.md`'s *What Task 8i established* records
    which of the nine RSS tests can have one and which need their subject moved
    into the child first. **Passing this from the wrong process would be worse
    than omitting it** -- a gate reporting on something other than its subject is
    the defect this whole line of work found.

    **THE CONDITION IS CHECKED ACROSS THE MEASUREMENT AND NOT BEFORE IT.** A box
    that is quiet when a test starts and stalls during it produces exactly the
    corrupted reading this exists to catch, so the counter is read on both sides
    and the rate is over the window that produced the number.

    Args:
        what: What was being measured, for the summary line.
        reference_bytes: A resident-set figure THIS process cannot honestly be
            below during the window -- its own pre-workload baseline. Omitted
            where the measurement happens in a child, because a reference read
            here would witness the wrong process.

    Yields:
        Nothing; the caller's assertions run inside.
    """
    from metamer.core import machine
    from tests.stall import StallWatch

    with StallWatch(reader=machine.memory_stall_us) as watch:
        yield

    flagged = watch.rate is not None and watch.rate > RSS_STALL_LIMIT_US_PER_S
    gate = (
        "witness" if (reference_bytes is not None or witness is not None) else "margin"
    )

    # **THE WITNESS IS THE GATE, AND IT IS THE ONLY GATE.** It answers whether
    # THIS process lost working set, which is the question every RSS assertion
    # actually asks. The stall rate answers whether anything in the cgroup waited
    # on memory -- measured 2026-08-21, a `measure_floor` ladder allocating
    # nothing but its own probes reads 223 ms/s with a witness of 0.00 MB -- so
    # it cannot tell an allocator from a victim, and it skips nothing.
    if reference_bytes is not None or witness is not None:
        shortfall = (
            witness()
            if witness is not None
            else machine.reclaim_shortfall_bytes(float(reference_bytes or 0.0))
        )
        if shortfall > 0:
            reason = (
                f"{what}: this process's working set ended "
                f"{shortfall / 1e6:.1f} MB BELOW a reference it cannot honestly "
                f"be under, so pages were reclaimed from it during the window "
                f"and every RSS difference taken across that window understates "
                f"by an unknown amount"
            )
            INDETERMINATE_RSS.append(reason)
            RSS_MEASUREMENTS.append(
                RssMeasurement(what, gate, watch.rate, flagged, True, reason)
            )
            pytest.skip(reason)

    RSS_MEASUREMENTS.append(RssMeasurement(what, gate, watch.rate, flagged, False))


def pytest_terminal_summary(terminalreporter: Any) -> None:
    """Report every RSS measurement by name, with its gate and its diagnostic.

    **PER ASSERTION, BECAUSE A COUNT HIDES A PERMANENT ABSTENTION.** "2
    INDETERMINATE" tells a reader how many and never which, so a criterion that
    has not run for three sweeps looks exactly like one that skipped once. Every
    bracketed measurement prints a line whether it passed, abstained or was never
    judged.

    **AND BOTH BRANCHES PRINT.** A section that appears only on failure trains a
    reader to see nothing and conclude nothing happened.

    Args:
        terminalreporter: pytest's reporter, which owns the section.
    """
    from tests.stall import STALL_WINDOW_S

    terminalreporter.write_sep("=", "RSS measurement validity")
    if not RSS_MEASUREMENTS:
        terminalreporter.write_line("no RSS-difference measurement ran this session")
        # **NO EARLY RETURN.** Diagnostics are printed by the loop at the end and
        # are not conditional on an RSS measurement having run -- an early return
        # here dropped them silently, which the channel's own test caught.
        _write_diagnostics(terminalreporter)
        return

    for record in RSS_MEASUREMENTS:
        if record.stall_us_per_s is None:
            stall = f"stall not judged (under the {STALL_WINDOW_S:.0f} s window)"
        else:
            stall = f"stall {record.stall_us_per_s / 1000:.1f} ms/s"
            if record.stall_flagged:
                stall += " HIGH"
        verdict = "INDETERMINATE" if record.indeterminate else "asserted"
        terminalreporter.write_line(
            f"  {record.what}: gate={record.gate}, {verdict}, {stall}"
        )

    indeterminate = [r for r in RSS_MEASUREMENTS if r.indeterminate]
    on_margin = [r for r in RSS_MEASUREMENTS if r.gate == "margin"]
    flagged = [r for r in RSS_MEASUREMENTS if r.stall_flagged]
    terminalreporter.write_line(
        f"{len(RSS_MEASUREMENTS)} measured, {len(indeterminate)} INDETERMINATE "
        f"(the reclaim witness refused), {len(on_margin)} carried by their margin "
        f"with no witness, {len(flagged)} above the "
        f"{RSS_STALL_LIMIT_US_PER_S / 1000:.0f} ms/s stall diagnostic"
    )
    if flagged:
        # **A DIAGNOSTIC AND NOT A VERDICT**, said in the summary as well as in
        # the constant's docstring, because a HIGH line next to a passing
        # assertion is exactly where a reader would otherwise infer a gate.
        terminalreporter.write_line(
            "  a HIGH stall reading skips nothing: the counter is per-cgroup and "
            "cannot tell a measurement that allocates hard from one that is "
            "being squeezed -- see open question 19"
        )
    for record in indeterminate:
        terminalreporter.write_line(f"  - {record.reason}")

    _write_diagnostics(terminalreporter)


def _write_diagnostics(terminalreporter: Any) -> None:
    """Write every diagnostic line, whatever else the summary reported.

    **PRINTED UNCONDITIONALLY.** These are readings a test wants on the record
    whatever its verdict, and the summary is the only channel that survives a
    PASSING test into a CI log.

    Args:
        terminalreporter: pytest's reporter, or anything with `write_line`.
    """
    for line in DIAGNOSTIC_LINES:
        terminalreporter.write_line(line)
