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

from dataclasses import dataclass, field

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
