"""Agreement between the compiled path-B engine and the numpy reference.

**A compiled kernel that diverges from the numpy reference is the one failure
the two-implementation design exists to detect.** Everything else in the spike
is a timing measurement, and a timing measurement of a wrong answer is worse
than no measurement: it would recommend adopting path B on the strength of a
speed it only achieves by computing something else.

Every gap case is exercised, because the two paths differ precisely in how
they treat a masked epoch -- the compiled loop branches past the update, the
batched path evaluates it and multiplies by zero. That is where a divergence
would live, and a no-gap fixture cannot see it.
"""

from __future__ import annotations

from typing import NamedTuple

import numpy as np
import pytest

from metamer.core.capability import Objective
from metamer.core.engines.compiled import CompiledEngine
from metamer.core.engines.kalman import KalmanEngine
from metamer.core.outcomes import Outcome
from metamer.core.signal import Annual, Constant, SemiAnnual, SignalSpec, Trend
from metamer.core.statespace import StateSpace
from metamer.core.terms import ProcessSpec
from tests.test_statespace import _term

N_TIME = 630
BATCH = 24


def _spec() -> ProcessSpec:
    """The d=3 spike composite: white + matern12 + matern32."""
    return ProcessSpec((_term("white"), _term("matern12"), _term("matern32")))


def _theta(spec: ProcessSpec, batch: int) -> np.ndarray:
    """Full natural-unit parameter vector, one row per series.

    `StateSpace.from_spec` slices over ALL of a term's parameters including
    fixed ones, so the vector handed to an engine is the full one and not the
    free-only search vector.
    """
    values = []
    for term in spec.terms:
        for name in term.params:
            values.append(float(term.params[name].default))
    return np.tile(np.asarray(values, dtype=np.float64), (batch, 1))


def _time_axis() -> np.ndarray:
    """630 monthly samples on a decimal-years axis: 52.5 years."""
    return np.arange(N_TIME, dtype=np.float64) / 12.0


def _mask(kind: str, batch: int = BATCH) -> np.ndarray:
    """Build one of the three sweep gap patterns.

    Args:
        kind: "none", "scattered" (10% at random epochs) or "contiguous"
            (40% as one block per series, the sea-ice pattern).
        batch: Number of series.

    Returns:
        Presence mask, shape (batch, N_TIME).
    """
    rng = np.random.default_rng(11)
    mask = np.ones((batch, N_TIME), dtype=bool)
    if kind == "scattered":
        mask &= rng.random((batch, N_TIME)) >= 0.10
    elif kind == "contiguous":
        width = int(0.40 * N_TIME)
        for b in range(batch):
            start = int(rng.integers(0, N_TIME - width))
            mask[b, start : start + width] = False
    elif kind != "none":  # pragma: no cover - guards the parametrization
        raise ValueError(kind)
    return mask


class _Inputs(NamedTuple):
    """One scored-engine call, named so mypy can see the argument types."""

    state_space: StateSpace
    theta: np.ndarray
    y: np.ndarray
    mask: np.ndarray
    t: np.ndarray
    design: np.ndarray


def _inputs(gaps: str) -> _Inputs:
    """Assemble a scored-engine call for one gap case."""
    spec = _spec()
    signal = SignalSpec([Constant(), Trend(), Annual(), SemiAnnual()])
    t = _time_axis()
    mask = _mask(gaps)
    rng = np.random.default_rng(3)
    y = rng.standard_normal((BATCH, N_TIME))
    # Heterogeneous amplitudes, so a bug that happens to cancel at unit scale
    # cannot hide: series 0 is ~1e-3 and series 23 is ~1e3.
    y *= np.logspace(-3.0, 3.0, BATCH)[:, None]
    design, _rank = signal.design_matrix(t)
    return _Inputs(StateSpace.from_spec(spec), _theta(spec, BATCH), y, mask, t, design)


@pytest.mark.slow
@pytest.mark.parametrize("gaps", ["none", "scattered", "contiguous"])
def test_the_compiled_engine_agrees_with_the_numpy_reference(gaps):
    """Both engines compute the same likelihood on identical input.

    Expected value determined independently: the reference IS the independent
    determination. `KalmanEngine` is the numpy implementation validated in
    Task 8 against an MVN oracle, so agreeing with it to 1e-10 relative is a
    statement that the compiled recursion is the same recursion. The two share
    only `_design_block`, `_step_matrices` and `_rank` -- the design validation
    and the post-processing -- so what is being compared is the loop, which is
    the part that was rewritten.

    THIS TEST CANNOT SEE ANYTHING BOTH ENGINES DO IDENTICALLY, which is why it
    is not on its own the guard for the 2026-08-10 streaming change: both
    engines were changed. `tests/test_kalman.py`'s MVN oracle is what pins the
    values, and it builds the covariance matrix explicitly rather than
    filtering.

    1e-10 is far looser than the reordering-free arithmetic should need and far
    tighter than any real divergence would be: a transposed F, a dropped Q, a
    gain applied to the wrong column or an off-by-one on the step index all
    produce O(1) relative error. It is a tolerance on summation order, not an
    agreement band.

    Bug this catches: THE ONE THE TWO-IMPLEMENTATION DESIGN EXISTS FOR. Every
    other number in the spike is a timing, and a timing of a wrong answer would
    recommend adopting path B for a speed it achieves by computing something
    else. Parametrized over all three gap cases because the two paths differ
    precisely in how they treat a masked epoch -- compiled branches past it,
    batched multiplies by zero -- so a no-gap fixture cannot see a mask bug.
    """
    state_space, theta, y, mask, t, design = _inputs(gaps)
    reference = KalmanEngine().score(
        state_space, theta, y, mask, t, design, Objective.ML
    )
    compiled = CompiledEngine().score(
        state_space, theta, y, mask, t, design, Objective.ML
    )

    np.testing.assert_array_equal(compiled.outcome, reference.outcome)
    np.testing.assert_array_equal(compiled.n_used, reference.n_used)
    np.testing.assert_array_equal(compiled.rank_x, reference.rank_x)
    ok = reference.outcome == Outcome.OK.code
    assert ok.any(), "fixture produced no OK series, so it cannot compare anything"
    np.testing.assert_allclose(
        compiled.loglik[ok], reference.loglik[ok], rtol=1e-10, atol=0.0
    )
    # The Gram is compared against ITS OWN per-series scale, not entry by
    # entry. Its entries span ~1e-11 to ~5e1 within a single matrix, because
    # the off-diagonal cross-products between orthogonal-ish design columns
    # cancel to near zero -- and a relative tolerance on an entry that cancelled
    # is a measurement of the cancellation, not of the implementation. Measured,
    # the largest disagreement is 4.1e-15 absolute against a matrix maximum of
    # ~5e1, i.e. 8e-17 of scale; the 1e-12 below leaves four orders of headroom
    # and still rejects any real divergence, which would be O(1) of scale.
    scale = np.abs(reference.normal_equations[ok]).max(axis=(1, 2), keepdims=True)
    np.testing.assert_allclose(
        compiled.normal_equations[ok] / scale,
        reference.normal_equations[ok] / scale,
        rtol=0.0,
        atol=1e-12,
    )


@pytest.mark.slow
def test_the_gap_fixtures_actually_remove_the_epochs_they_claim():
    """The sweep's three cases are distinguishable before anything is timed.

    Expected value determined independently: 10% scattered leaves ~90% of
    630 epochs, and a 40% contiguous block leaves exactly 60% -- 378 present
    epochs per series, since the block width is `int(0.40 * 630)` = 252 and
    every series gets one. The contiguous case is also the one with a long run
    of consecutive absences, which is what makes it the sea-ice pattern rather
    than merely a lower density.

    Bug this catches: a gap sweep whose cases all look the same to the
    engines, which would make the per-gap A:B ratios three measurements of one
    condition. Density alone is not enough -- scattered and contiguous at the
    same density would still differ in run length, and it is the RUN that lets
    a compiled loop skip work.
    """
    none, scattered, contiguous = (
        _mask(k) for k in ("none", "scattered", "contiguous")
    )
    assert none.all()
    assert 0.86 < scattered.mean() < 0.94
    assert np.all(contiguous.sum(axis=1) == N_TIME - int(0.40 * N_TIME))

    def longest_run(row):
        best = run = 0
        for present in row:
            run = 0 if present else run + 1
            best = max(best, run)
        return best

    assert max(longest_run(r) for r in scattered) < 20
    assert min(longest_run(r) for r in contiguous) == int(0.40 * N_TIME)


@pytest.mark.slow
def test_a_fully_masked_series_is_insufficient_data_on_both_paths():
    """The all-masked case agrees too, and it is not an edge case.

    Expected value determined independently: an all-masked series has an empty
    product, which scores -0.0 -- HIGHER than any real fit, so it would rank
    first everywhere it occurred. Both engines must diagnose
    INSUFFICIENT_DATA, poison the log-likelihood to NaN and set `rank_x` to
    the -1 "not computed" sentinel, while leaving `n_used` un-poisoned at 0
    because a count of unmasked epochs is true regardless of how the fit went.

    Bug this catches: a compiled kernel that returns zeros for an empty series
    and lets the classification upstream read them as a real fit. The Antarctic
    interior is an ordinary whole-series case, not a contrived one, and the
    failure is silent: -0.0 is finite, plausible, and wins.
    """
    state_space, theta, y, mask, t, design = _inputs("none")
    mask = mask.copy()
    mask[0] = False
    reference = KalmanEngine().score(
        state_space, theta, y, mask, t, design, Objective.ML
    )
    compiled = CompiledEngine().score(
        state_space, theta, y, mask, t, design, Objective.ML
    )
    assert compiled.outcome[0] == Outcome.INSUFFICIENT_DATA.code
    assert compiled.outcome[0] == reference.outcome[0]
    assert np.isnan(compiled.loglik[0])
    assert compiled.n_used[0] == 0
    assert compiled.rank_x[0] == -1
    ok = reference.outcome == Outcome.OK.code
    np.testing.assert_allclose(
        compiled.loglik[ok], reference.loglik[ok], rtol=1e-10, atol=0.0
    )
