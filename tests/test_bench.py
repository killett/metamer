"""Tests for the benchmark references and the stage-1 spike harness.

These guard the *shape* of the measurement, not its speed. A benchmark whose
numbers are wrong is worse than no benchmark: the stage-1 verdict is a
one-sided inference, and a bound that is not actually a bound would license
deleting path A's optimizer on the strength of a comparison that never held.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys

import numpy as np
import pytest

from metamer.bench.references import (
    bandwidth_reference,
    compute_reference,
)
from metamer.bench.spike import (
    CORE_BUDGET_MS,
    GAP_CASES,
    ITERATION_ROWS,
    MATERN32_RHO_MULTIPLE,
    _process_covariance,
    build_spec,
    full_theta,
    gap_mask,
    iteration_sample,
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


def test_the_iteration_covariance_is_the_analytic_matern12_plus_a_nugget():
    """Sigma at d=1 is exp(-|tau|/rho) on the lags plus sigma_w^2 on the diagonal.

    Expected value determined independently: written out here as the closed
    form for Matern nu=1/2 -- `sigma^2 exp(-|tau|/rho)` -- plus measurement
    noise keyed on INDEX, not on the lag being zero. The comparison is against
    an expression, not against a stored number, so it is an analytic endpoint
    and the tolerance is a statement about rounding rather than an agreement
    band: a genuine disagreement here is O(1), not O(1e-16).

    Bugs this catches, all of which leave a plausible covariance behind:
    summing the white term into the lag part as well (double-counting the
    nugget, which shifts every drawn row's variance by sigma_w^2); keying the
    nugget on `lag == 0.0`, which would put sigma_w^2 off-diagonal for two
    observations sharing a timestamp; and slicing `theta` in written rather
    than canonical order, which swaps rho for the white sigma.
    """
    t = np.arange(48, dtype=np.float64) / 12.0
    rho, white_sigma = 4.0 * float(t[1] - t[0]), 0.30
    state_space = StateSpace.from_spec(build_spec(1))
    theta = np.array([[1.0, rho, white_sigma]])

    lags = np.abs(t[:, None] - t[None, :])
    expected = np.exp(-lags / rho) + np.eye(t.size) * white_sigma**2

    np.testing.assert_allclose(
        _process_covariance(state_space, theta, t), expected, rtol=1e-15, atol=0.0
    )


def test_every_iteration_row_carries_the_correlation_it_was_drawn_from():
    """The sample comes from the candidate's own process, not from white noise.

    Expected value determined independently: a realization of
    `matern12 + white` has lag-1 autocorrelation
    `exp(-dt/rho) / (1 + sigma_w^2)` -- 0.71, 0.76, 0.72, 0.62 for the four
    d=1 rows -- while `standard_normal`, the generator this sample used until
    2026-08-10, has zero at every nonzero lag. Measured, the four white rows
    the old fixture drew sit at -0.017, 0.033, 0.065, -0.019 and the four rows
    here at 0.67, 0.84, 0.60, 0.43. The threshold below sits in that gap; it
    is not a tolerance on the analytic value, because a single 630-point
    realization of a process with a 32-interval correlation time carries
    roughly ten independent samples and its sample autocorrelation is
    therefore worth about +/- 0.3.

    Bug this catches: THE DEFECT ITSELF -- drawing the iteration sample from a
    distribution the fitted composite cannot produce. White noise fitted with
    a free timescale leaves the timescale on a flat ridge, so the fit is
    reported `DEGENERATE_HESSIAN` and drops out of `mean_iterations` and
    `utilization`, both of which average over `OK` only. It is the third
    instance of one generator defect.
    """
    t = np.arange(630, dtype=np.float64) / 12.0
    for dim in (1, 3):
        sample = iteration_sample(dim, t)
        assert sample.shape == (len(ITERATION_ROWS[dim]), t.size)
        for row in sample:
            centred = row - row.mean()
            lag_one = float(centred[:-1] @ centred[1:] / (centred @ centred))
            assert lag_one > 0.35


def test_the_iteration_rows_differ_by_parameters_and_not_by_amplitude():
    """Rows carry four parameter sets, so the fits differ in difficulty.

    Expected value determined independently: the Gaussian log-likelihood is
    scale-equivariant -- scaling a series by `c` scales every sigma by `c` and
    leaves the shape of the surface alone -- so an amplitude spread cannot
    move the iteration count. Measured directly: one realization at four
    amplitudes gives `n_iter = [28, 28, 28, 28]` and utilization exactly 1.0.
    Heterogeneity therefore has to come from the generating parameters, and
    the marginal variance is what shows it is NOT coming from amplitude: every
    state amplitude is 1.0 and only the timescale and the nugget move.

    Bug this catches: reintroducing `* logspace(-1, 1, 4)`, which the previous
    fixture used and its docstring described as what made the batch
    heterogeneous. Utilization would then be 1.0 by construction, which is the
    number the measurement exists to challenge, and nothing in the report
    would say so.
    """
    for dim, rows in ITERATION_ROWS.items():
        rho_intervals = [rho for rho, _ in rows]
        white_sigmas = [sigma for _, sigma in rows]
        assert len(set(rho_intervals)) == len(rows)
        assert len(set(white_sigmas)) == len(rows)
        # Timescales stay clear of each other so no row sits on the
        # exchangeability ridge design doc section 4.8 describes.
        if dim == 3:
            assert MATERN32_RHO_MULTIPLE >= 1.5


def test_the_iteration_sample_is_reproducible_across_processes():
    """A fresh interpreter draws the same sample, so two runs are comparable.

    Expected value determined independently: `default_rng(seed)` is specified
    to be reproducible, so the digest of the drawn array is a property of the
    seed alone. This runs the draw in a SUBPROCESS rather than twice in this
    one, because that is the only place the defect is observable: every test
    in one pytest run shares a single `PYTHONHASHSEED` and a single global RNG
    state, so a generator that depended on either would agree with itself
    here and disagree between runs.

    Bug this catches: seeding from entropy, or from a module-level RNG another
    caller has already drawn from. `mean_iterations` multiplies both paths'
    ms/fit columns, so a sample that moved between runs would move the 19 ms
    budget comparison with it -- and the A:B ratio, where the iteration count
    cancels, would keep reading clean.
    """
    code = (
        "import hashlib, numpy as np;"
        "from metamer.bench.spike import iteration_sample;"
        "t = np.arange(64, dtype=np.float64) / 12.0;"
        "print(hashlib.sha256(iteration_sample(1, t).tobytes()).hexdigest())"
    )
    env = {**os.environ, "PYTHONHASHSEED": "7"}
    out = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    t = np.arange(64, dtype=np.float64) / 12.0
    here = hashlib.sha256(iteration_sample(1, t).tobytes()).hexdigest()
    assert out.stdout.strip() == here


@pytest.mark.slow
def test_every_iteration_row_fits_with_margin_to_the_degeneracy_limit():
    """All four d=3 rows come back OK, and none of them is OK by a whisker.

    Expected value determined independently: each row is a realization of the
    very composite it is fitted with, at parameters that are identified by a
    630-point record -- timescales 4 to 13.5 sampling intervals with the
    second term a factor of six above the first, and signal-to-noise from 3.3
    down to 1.3. A fit of a process by its own generator should converge, and
    its curvature at the optimum should be nowhere near singular. Measured:
    `cond(H) = 5.3e2, 3.8e2, 6.0e3, 1.6e4` against `HESSIAN_COND_LIMIT =
    6.71e7`, the tightest a factor of 4188.

    **The margin is asserted, not just the side of the threshold.** A fixture
    healthy by 28x is not healthy: that is exactly how the CI flake of
    2026-08-08 got in, and how this sample's own defect survived under the old
    `1e10` limit.

    Bug this catches: the previous `standard_normal` sample, which came back
    `[DEGENERATE_HESSIAN, OK, DEGENERATE_HESSIAN, OK]` at d=3 -- so
    `mean_iterations` and `utilization` were averages over two series while
    the report gave no denominator. It also catches a future widening of
    `ITERATION_ROWS` that puts a row on the exchangeability ridge, which
    reports as a plausible iteration count rather than as an error.
    """
    from metamer.core.capability import Objective
    from metamer.core.engines.compiled import CompiledEngine
    from metamer.core.objective import ConcentratedObjective
    from metamer.core.optimize import HESSIAN_COND_LIMIT, optimize_series
    from metamer.core.outcomes import Outcome
    from metamer.core.signal import Annual, Constant, SemiAnnual, SignalSpec, Trend

    t = np.arange(N_TIME, dtype=np.float64) / 12.0
    sample = iteration_sample(3, t)
    spec = build_spec(3)
    state_space = StateSpace.from_spec(spec)
    present = np.ones((sample.shape[0], t.size), dtype=bool)
    design = SignalSpec([Constant(), Trend(), Annual(), SemiAnnual()]).design_info(
        t, present
    )
    objective = ConcentratedObjective(spec, state_space, CompiledEngine(), Objective.ML)

    for b in range(sample.shape[0]):
        fitted = optimize_series(
            objective, sample[b : b + 1], present[b : b + 1], t, design.series(b)
        )
        assert fitted.outcome is Outcome.OK
        assert fitted.hessian is not None
        assert np.linalg.cond(fitted.hessian) < HESSIAN_COND_LIMIT / 1e3
