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
