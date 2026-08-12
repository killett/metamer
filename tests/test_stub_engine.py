"""The raising stub engine, and the one case in which it proves nothing.

Task 0 defines this fixture and Task 11 is the first task to consume it. That
gap is the whole reason this module exists: a stub that is wired into a run and
never reached, and a stub that was never wired in at all, produce byte-identical
green results. The claim "no fit ran" is CONSTANT across every axis its
consumers compare, which is the cancellation rule at the level of a test
fixture, so it needs an absolute anchor rather than a differential one.

The anchor is `test_the_stub_raises_when_a_fit_reaches_the_engine`. Its
counterpart, `test_the_stub_is_silent_when_every_series_fails_the_precheck`,
makes the fixture's one blind spot executable instead of advisory -- this
project's own standing lesson being that a docstring does not constrain the next
author and a test does.
"""

from __future__ import annotations

import inspect

import numpy as np
import pytest

from metamer.core.criteria import Criterion
from metamer.core.engines.protocol import Engine
from metamer.core.fit import fit
from metamer.core.outcomes import Outcome
from metamer.core.signal import Constant, SignalSpec, Trend
from metamer.core.terms import ProcessSpec
from tests.conftest import RaisingStubEngine, StubEngineCalled
from tests.test_statespace import _term

_N = 24
_T = 2000.0 + np.arange(_N) / 12.0


def _candidates() -> list[ProcessSpec]:
    return [ProcessSpec((_term("white"),))]


def _signal() -> SignalSpec:
    return SignalSpec((Constant(), Trend()))


def test_the_stub_conforms_to_the_engine_protocol(
    raising_engine: RaisingStubEngine,
) -> None:
    """The stub satisfies `Engine` and binds the protocol's own signature.

    Bug this catches: the stub drifting from the protocol -- a renamed or added
    parameter -- so that a real caller invokes it with arguments it does not
    accept. A consumer would then see `TypeError` where it asserted
    `StubEngineCalled`, i.e. the negative it was proving would be swallowed by
    an unrelated failure.

    `isinstance` and the signature comparison are NOT substitutes for each
    other: `runtime_checkable` checks method PRESENCE and nothing about shape,
    so `isinstance` alone passes against a stub whose `score` takes no arguments
    at all. Conformance is checked with `isinstance` and never `issubclass` --
    a `runtime_checkable` protocol with a data member raises `TypeError` from
    `issubclass` by design, per `engines/protocol.py`.
    """
    assert isinstance(raising_engine, Engine)
    assert (
        list(inspect.signature(raising_engine.score).parameters)
        == list(inspect.signature(Engine.score).parameters)[1:]
    )


def test_the_stub_raises_when_a_fit_reaches_the_engine(
    raising_engine: RaisingStubEngine,
) -> None:
    """A fittable batch through the real driver reaches `score` and raises.

    THIS IS THE POSITIVE CONTROL, and it is the only test in the suite that can
    tell a wired-in stub from an unwired one. Bug it catches: the stub being
    passed somewhere that is not on the fit path -- a runner that accepts an
    `engine` argument and then constructs its own, say -- which leaves every
    "no fit ran" assertion downstream passing for free.

    The engine is threaded through `fit(..., engine=...)`, which is the
    injection seam. `fit` substitutes `KalmanEngine()` when the argument is
    omitted, so a caller that leaves it out exercises the default and not the
    stub.
    """
    rng = np.random.default_rng(0)
    y = rng.standard_normal((2, _N))

    with pytest.raises(StubEngineCalled):
        fit(
            y=y,
            t=_T,
            signal=_signal(),
            candidates=_candidates(),
            criterion=Criterion.AIC,
            engine=raising_engine,
        )

    assert raising_engine.calls, "score raised without recording the call"
    assert raising_engine.calls[0]["has_design"] is True
    # THE ENGINE SEES B = 1 HERE, NOT B = 2, AND THAT IS CORRECT. `fit` is the
    # (B, N) driver, but it drives `optimize_series` once per series, and
    # `optimize_series` is path A's permanent per-series form -- the one
    # documented exception to "(B, N) is the only code path". So the batch
    # dimension the engine is handed inside a fit is the series, not the tile.
    # Asserted rather than left implicit because a consumer reasoning about how
    # many `score` calls a run makes needs to know the loop is per series.
    assert raising_engine.calls[0]["batch"] == 1


def test_the_stub_is_silent_when_every_series_fails_the_precheck(
    raising_engine: RaisingStubEngine,
) -> None:
    """A wholly-masked batch never reaches the engine, so the stub never raises.

    THE LIMIT, MADE EXECUTABLE. It matters because it is reachable by accident:
    `fit` costs ~5.4 s per series, so a Task 11 or Task 12 test wanting to be
    cheap is drawn towards exactly this fixture -- and here the stub proves
    nothing. No fit ran because no fit COULD run, whatever engine was installed.

    TWO INDEPENDENT GUARDS STAND BETWEEN THIS INPUT AND THE ENGINE, AND EITHER
    ONE IS SUFFICIENT. Measured by mutation rather than read off the source:

      - `optimize.optimize_series` merges the data-level verdict with the design
        precheck and returns a `SeriesFit` before building anything, when the
        merge is not OK.
      - `objective.ConcentratedObjective.evaluate` returns before
        `self.engine.score` when no series in the batch passes the precheck.

    **Mutating either one alone does NOT make this test bite; mutating both at
    once does.** That is defence in depth working, not a weak test -- the same
    shape as Task 16's `_subset`, where the honest reproduction of the fence's
    bug also had to mutate both halves. Recorded because the surviving single
    mutation would otherwise be diagnosed as a coverage gap and chased.

    Both guards are deliberate and load-bearing: together they are what keeps a
    wholly-masked tile `INSUFFICIENT_DATA` rather than `RANK_DEFICIENT_X`, i.e.
    out of both the numerator and the denominator of the failure rate. So this
    is the fixture's blind spot and not a bug to fix.

    Bug this catches: both guards being removed or bypassed, which would change
    what a downstream "no fit ran" assertion means without any of those tests
    changing. The inverse bug it also catches is a consumer copying this mask
    pattern into a "no fit ran" test -- which this test names as vacuous.

    A design is required for either branch to exist at all: with no design the
    engine is called unconditionally.
    """
    rng = np.random.default_rng(0)
    y = rng.standard_normal((2, _N))
    mask = np.zeros_like(y, dtype=bool)

    result = fit(
        y=y,
        t=_T,
        signal=_signal(),
        candidates=_candidates(),
        criterion=Criterion.AIC,
        mask=mask,
        engine=raising_engine,
    )

    assert raising_engine.calls == []
    assert np.all(result.outcome == Outcome.INSUFFICIENT_DATA.code)
