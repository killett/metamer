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
import time
from collections.abc import Iterator
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

#: POLICY. Microseconds of full memory stall per second of wall clock above
#: which an RSS-difference reading is INDETERMINATE rather than pass or fail.
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
#: **THE VALUE IS SET FROM A MEASUREMENT AND ITS LIMIT IS STATED.** On this box,
#: 20 s idle gave a cgroup full-stall rate of **0.9 ms/s**, and a 17.7 s
#: `measure_floor` whose answer was CORRECT gave **5.3 ms/s** -- five times
#: idle, from our own allocations. So a nonzero stall is normal and the gate
#: must be a rate. **50 ms/s is 5% of wall clock and roughly ten times the
#: known-good rate.**
#:
#: **AND THE KNOWN-BAD READINGS ARRIVED AT PHASE 2b TASK 8a, 2026-08-17: THE
#: GATE DOES NOT SEE THIS FAILURE MODE AT ALL.** Two one-tile runs lost most of
#: their resident set to reclaim and both read far INSIDE the limit -- a 4073 s
#: fit whose working set ended **85 MB below its own measured floor** read
#: **0.0876 ms/s**, which is below the 0.9 ms/s idle rate, and a control that
#: added 600 s of idle and lost **92 MB** read **1.2489 ms/s**. **Both would
#: pass.** The mechanism is in the counter's definition: PSI `full` counts time
#: the workload was **stalled waiting** on memory, and reclaiming clean
#: file-backed pages the workload has stopped touching costs **no stall at
#: all**. So this gate catches **thrashing** and is **blind to quiet reclaim
#: over a long window**.
#:
#: **THE NUMBER IS THEREFORE NOT WIDENED AND NOT NARROWED -- ITS SUBJECT IS.**
#: It is a valid gate on the failure it was built from and it is not a
#: certificate that an RSS difference is sound. **A long-running RSS difference
#: needs its own control**: hold the fixture and vary only elapsed time, which
#: is what exposed this. See `PROGRESS.md`'s *What Task 8a established*.
#:
#: **THE ASYMMETRY IS UNUSUAL BECAUSE BOTH DIRECTIONS COST SOMETHING.** Too
#: loose and a corrupted measurement is asserted as a fact. Too tight and these
#: tests stop running, which is how a `machine` test decays into a test nobody
#: notices. **The tie is broken by making INDETERMINATE loud**: a gate that is
#: too tight announces itself in the summary and gets re-run, and a gate that is
#: too loose is silent -- so the bias is toward tight.
#:
#: **AND IT FIRED FOR THE FIRST TIME ON 2026-08-19, WHICH IS THE READING THIS
#: DOCSTRING HAS BEEN ASKING FOR SINCE IT WAS WRITTEN.**
#: `test_the_floor_ladder_reproduces_the_recorded_rungs` went INDETERMINATE at
#: **53 ms/s of cgroup full stall over 14.1 s**, on a box down to **3.4 GB
#: available** after a day of measurement -- against 0.9 ms/s idle and 5.3 ms/s
#: during a `measure_floor` whose answer was correct. **The gate behaved exactly
#: as designed: it refused to judge, said so in the summary, and cost one
#: reading rather than asserting a corrupted one.** The suite was otherwise
#: green at 1074 passed, 0 failed.
#:
#: **DO NOT READ THIS AS THE KNOWN-BAD THE CONSTANT STILL LACKS.** It is a
#: THRASHING reading, which is the failure mode the number was built from and
#: is valid for; the failure mode it is blind to is the one above, and Task 8i
#: shipped `machine.reclaim_shortfall_bytes` for that. What this datum settles
#: is narrower and worth having: **at 53 ms/s the limit is close enough to a
#: real sweep's worst window to fire about once a day on a loaded box**, so the
#: 10x margin over known-good is roughly 1.06x over what actually occurs. **If
#: it starts firing on most runs the repair is the box or the fixture, never the
#: number** -- widening it is how the tests stop running.
RSS_STALL_LIMIT_US_PER_S = 50_000

#: Every indeterminate measurement this session, for the terminal summary.
#: **A SKIP NOBODY SEES IS HOW A MACHINE-MARKED TEST DECAYS INTO ONE THAT NEVER
#: RUNS**, so the count and the reasons are reported at the end of the run.
INDETERMINATE_RSS: list[str] = []


@contextlib.contextmanager
def rss_validity(what: str, *, reference_bytes: float | None = None) -> Iterator[None]:
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

    start = machine.memory_stall_us()
    started = time.perf_counter()
    yield
    elapsed = max(time.perf_counter() - started, 1e-9)
    end = machine.memory_stall_us()

    # **CHECKED FIRST, BECAUSE IT IS THE CONDITION THAT CAN SEE THE FAILURE.**
    # The stall gate below missed a run that lost 85 MB; this one is what Task 8i
    # validated against both sides. Ordering matters only for which reason gets
    # reported, and the more specific one is worth more to the reader.
    if reference_bytes is not None:
        shortfall = machine.reclaim_shortfall_bytes(reference_bytes)
        if shortfall > 0:
            reason = (
                f"{what}: this process's working set ended "
                f"{shortfall / 1e6:.1f} MB BELOW a reference it cannot honestly "
                f"be under, so pages were reclaimed from it during the window "
                f"and every RSS difference taken across that window understates "
                f"by an unknown amount"
            )
            INDETERMINATE_RSS.append(reason)
            pytest.skip(reason)

    if start is None or end is None:
        # **THE KERNEL DOES NOT EXPOSE PSI, SO THE CONDITION CANNOT BE CHECKED.**
        # Reported rather than assumed clean: "unknown" and "fine" are the same
        # observation otherwise, which is the fill-value rule at a gate.
        INDETERMINATE_RSS.append(f"{what}: memory-pressure counter unavailable")
        return

    rate = (end[0] - start[0]) / elapsed
    if rate > RSS_STALL_LIMIT_US_PER_S:
        reason = (
            f"{what}: {rate / 1000:.0f} ms/s of full memory stall over "
            f"{elapsed:.1f} s ({end[1]} counter), above the "
            f"{RSS_STALL_LIMIT_US_PER_S / 1000:.0f} ms/s limit -- pages were "
            f"being reclaimed, so an RSS difference understates by an unknown "
            f"amount"
        )
        INDETERMINATE_RSS.append(reason)
        pytest.skip(reason)


def pytest_terminal_summary(terminalreporter: Any) -> None:
    """Report every indeterminate RSS measurement, or say there were none.

    **BOTH BRANCHES PRINT.** A section that appears only on failure trains a
    reader to see nothing and conclude nothing happened; the line that says
    "0 indeterminate" is what makes the silence evidence.
    """
    terminalreporter.write_sep("=", "RSS measurement validity")
    if not INDETERMINATE_RSS:
        terminalreporter.write_line(
            "0 indeterminate: every RSS-difference measurement ran under a "
            f"full-stall rate below {RSS_STALL_LIMIT_US_PER_S / 1000:.0f} ms/s, "
            "and every one that supplied a reference ended at or above it"
        )
        return
    terminalreporter.write_line(
        f"{len(INDETERMINATE_RSS)} INDETERMINATE -- neither passed nor failed:"
    )
    for reason in INDETERMINATE_RSS:
        terminalreporter.write_line(f"  - {reason}")
