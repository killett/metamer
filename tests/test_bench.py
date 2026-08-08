"""Tests for the benchmark references and the stage-1 spike harness.

These guard the *shape* of the measurement, not its speed. A benchmark whose
numbers are wrong is worse than no benchmark: the stage-1 verdict is a
one-sided inference, and a bound that is not actually a bound would license
deleting path A's optimizer on the strength of a comparison that never held.
"""

from __future__ import annotations

import numpy as np
import pytest

from metamer.bench.references import (
    bandwidth_reference,
    compute_reference,
)
from metamer.bench.spike import (
    CORE_BUDGET_MS,
    GAP_CASES,
    build_spec,
    full_theta,
    gap_mask,
)
from metamer.core.statespace import StateSpace

N_TIME = 630


def test_the_spike_composite_reaches_d3_without_matern52():
    """d=3 is white + matern12 + matern32, and white contributes nothing.

    Expected value determined independently: white noise is measurement noise
    and has no state, so it is d=0; Matern nu=1/2 is d=1 and nu=3/2 is d=2,
    giving 0 + 1 + 2 = 3. Design doc section 9.2 offers "white + SHO" as the
    d=3 case, but SHO is d=2 and white adds nothing, so that composite is
    d=2 -- which is why this one is used instead.

    Bug this catches: a spike that thinks it is measuring d=3 while measuring
    d=2. Every timing in the report would be filed under the wrong state
    dimension, and the compute reference -- which is explicitly a d=3 kernel --
    would no longer match the workload it is meant to normalize.
    """
    assert StateSpace.from_spec(build_spec(1)).state_dim == 1
    assert StateSpace.from_spec(build_spec(3)).state_dim == 3
    with pytest.raises(ValueError, match="d=1 or d=3"):
        build_spec(2)


def test_full_theta_covers_fixed_parameters_too():
    """An engine takes the full vector, not the free-only search vector.

    Expected value determined independently: `white + matern12 + matern32` has
    sigma for white, (sigma, rho) for each Matern -- five parameters -- and
    `StateSpace.from_spec` slices over all of a term's parameters including
    fixed ones. Counting only free parameters would shift every later
    coordinate one slot left.

    Bug this catches: handing an engine the free-only vector, which silently
    reinterprets rho as sigma for every term after the first fixed parameter.
    The result is finite and plausible, and it is a different model.
    """
    spec = build_spec(3)
    theta = full_theta(spec, batch=7)
    assert theta.shape == (7, 5)
    assert np.all(theta[0] == theta[-1])
    StateSpace.from_spec(spec).transition(theta, 1.0)


@pytest.mark.parametrize("kind", GAP_CASES)
def test_each_gap_case_has_the_density_it_claims(kind):
    """The three sweep cases are distinguishable, by density and by run length.

    Expected value determined independently: no gaps leaves 630 epochs;
    10% scattered leaves ~567; a 40% contiguous block removes
    int(0.40 * 630) = 252, leaving exactly 378. The contiguous case is defined
    by its RUN, not its density -- that is what lets a compiled loop skip work
    and what makes it the sea-ice pattern.

    Bug this catches: a sweep whose cases differ only in name, which would
    make the three per-gap A:B ratios three measurements of one condition and
    would hide the very effect the sweep exists to expose -- that path B's
    advantage grows with gappiness.
    """
    mask = gap_mask(kind, batch=8, n_time=N_TIME)
    assert mask.shape == (8, N_TIME)
    if kind == "none":
        assert mask.all()
    elif kind == "scattered_10":
        assert 0.86 < mask.mean() < 0.94
    else:
        assert np.all(mask.sum(axis=1) == N_TIME - int(0.40 * N_TIME))


def test_an_unknown_gap_case_is_refused():
    """A typo'd case name is an error, not a silently ungapped run.

    Expected value determined independently: the sweep is defined by
    `GAP_CASES`, so anything else has no defined pattern.

    Bug this catches: falling through to an all-present mask, which would
    report the no-gap timing under a gapped label -- so the sweep would show
    no gap dependence at all and the contiguous case's advantage would vanish
    from the report.
    """
    with pytest.raises(ValueError, match="unknown gap case"):
        gap_mask("40_percent", batch=2, n_time=16)


def test_the_gap_mask_is_reproducible_across_processes():
    """Two runs of the sweep compare the same series, not merely the same rate.

    Expected value determined independently: the mask is built from a seeded
    `default_rng`, so the same seed must give bit-identical masks. Comparing
    path A and path B on different realizations would put the difference
    between two random draws into the A:B ratio.

    Bug this catches: an unseeded RNG. The per-case densities would still look
    right, every assertion above would still pass, and the ratio would carry
    an unquantified noise term that no summary statistic in the report exposes.
    """
    first = gap_mask("scattered_10", batch=4, n_time=64)
    second = gap_mask("scattered_10", batch=4, n_time=64)
    np.testing.assert_array_equal(first, second)


@pytest.mark.slow
@pytest.mark.machine
def test_the_compute_reference_runs_the_filters_arithmetic_not_a_factorization():
    """The compute reference is P = F P F' + Q at d=3, and it is not free.

    Expected value determined independently: the kernel does two d x d
    products (2*d^3 multiply-adds each), an add, and a rank-1 downdate, so at
    d=3 it is ~126 flops per step. A step must therefore take a small but
    nonzero time -- measured ~130 ns on this machine, ~1 GF/s -- and the
    reported rate must be a plausible fraction of a core's peak rather than
    absurd.

    Bug this catches: a loop the compiler deleted because its result was
    unused, which would report a near-zero time and an impossible flop rate,
    and would make every cross-machine prediction built on this reference
    meaningless. The kernel returns a checksum for exactly this reason.
    """
    timing = compute_reference(iterations=20_000, repeats=2)
    assert timing.detail["d"] == 3.0
    assert 1e-9 < timing.seconds < 1e-4
    assert 0.01 < timing.detail["gflops"] < 100.0


@pytest.mark.slow
@pytest.mark.machine
def test_single_threaded_stream_overstates_per_core_bandwidth():
    """One core cannot saturate the memory controller, and the sweep shows it.

    Expected value determined independently: STREAM is bandwidth-bound, so
    total throughput saturates at the memory system's limit while per-core
    throughput falls as threads are added. Measured on this 4-core machine:
    11.68 GB/s at 1 thread against 12.19 GB/s total at 4 threads -- i.e. the
    controller is already nearly saturated by one core -- so per-core drops to
    3.05 GB/s, a factor of 3.8.

    Bug this catches: reporting the single-thread figure as "the machine's
    bandwidth". It would overstate per-core bandwidth by that factor and
    flatter wide machines most, which is precisely backwards for predicting
    the 64-core box from the mini PC -- the machine where the budget question
    is actually decided.
    """
    one = bandwidth_reference(threads=1, mib=64, repeats=2)
    full = bandwidth_reference(threads=4, mib=64, repeats=2)
    ratio = one.detail["gb_per_s_per_core"] / full.detail["gb_per_s_per_core"]
    assert ratio > 2.0

    # NOTHING IS ASSERTED ABOUT THE DIRECTION OF *TOTAL* THROUGHPUT, and that
    # is deliberate. Two earlier versions asserted total rises with threads.
    # Measured on the unloaded box it barely does (10.59 -> 12.03 GB/s); under
    # full-suite CPU contention it FALLS (11.23 -> 8.44), because one core
    # already saturates the controller and the extra threads buy nothing while
    # costing synchronization. Both readings say the same thing about the
    # machine, so an assertion on the sign of that difference measures the
    # session's load, not the memory system. The per-core ratio above is the
    # claim the reference exists to support and it survives either reading.


def test_the_core_budget_is_the_one_from_the_design_doc():
    """19 ms per series-model fit, stated once and imported everywhere.

    Expected value determined independently: design doc section 9.2 fixes the
    per series-model core budget at 19 ms.

    Bug this catches: a second copy of the budget drifting from the first, so
    the same measurement passes in one report and fails in another.
    """
    assert CORE_BUDGET_MS == 19.0
