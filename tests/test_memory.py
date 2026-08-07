"""Tests for the analytic memory formula and the peak-RSS shim.

The formula's claim is about the **slope** of peak RSS against batch size, not
about an absolute peak. A process carries a large, real, per-run constant --
interpreter, numpy, numba, imports -- that is not per-series and that the
formula deliberately does not model. Comparing an absolute peak against
`B * bytes_per_series` therefore measures the constant as much as the formula.
`test_measured_peak_rss_is_at_least_the_arrays_that_provably_exist` fits a
line across three batch sizes and checks the gradient, which is the quantity
the formula actually asserts.

Two instruments, and they are not interchangeable. `peak_rss_bytes` is a
high-water mark and is **inherited across fork/exec**, so it reports an
ancestor's number whenever that ancestor was larger -- spawning a fresh
process is not enough to isolate a measurement. `current_rss_bytes` is not a
watermark and so is not contaminated; the child samples it on a thread and
keeps the maximum.
"""

from __future__ import annotations

from typing import TypedDict

import numpy as np
import pytest

from metamer.core.machine import current_rss_bytes, peak_rss_bytes
from metamer.core.memory import (
    Backend,
    _measure_child,
    augmented_block_bytes,
    bytes_per_series,
    data_and_workspace_bytes_per_series,
    measure_evaluation_rss_slope,
    output_slot_bytes,
    resident_bytes_per_series,
    thread_state_bytes,
    tile_bytes,
    tile_side,
)


class _Case(TypedDict):
    """The section 9.4 worked-example parameters.

    A TypedDict rather than a plain dict so `**CASE` type-checks: mypy
    otherwise has to assume a `dict[str, int]` might land in the `bool`
    `per_point_design` slot.
    """

    d: int
    k_beta: int
    p: int
    n_time: int
    n_models: int


# Corrected 2026-08-07: the output-slot scalar count is 4
# (log_lik, k, n_eff_trend, n_eff_bic) and not 2.
CASE: _Case = {"d": 3, "k_beta": 4, "p": 4, "n_time": 630, "n_models": 12}


# --------------------------------------------------------------------------
# The RSS shim
# --------------------------------------------------------------------------


def test_peak_rss_tracks_a_known_allocation():
    """The shim reports bytes, and reports them on the right scale.

    Expected value determined independently: allocating 256 MiB of float64
    and touching every page must move a peak-RSS reading by ~256 MiB. The
    bound below is deliberately one-sided and loose (at least 200 MiB), since
    the allocator may round up and the garbage collector may not have released
    anything else.

    Bug this catches: `ru_maxrss` unit confusion. Linux reports kilobytes and
    macOS reports bytes -- a factor of 1024 -- so a shim that returns the raw
    number would be right on one platform and wrong by three orders of
    magnitude on the other, while both still look like "a plausible number of
    bytes". Under the error the peak reads 1024x too small, which the lower
    bound rejects, or 1024x too large, which the upper bound rejects.

    THE SCALE IS PINNED AGAINST `current_rss_bytes`, NOT AGAINST A DELTA IN THE
    PEAK. An earlier version asserted that a 256 MiB allocation moves the peak
    by 256 MiB, and it failed in the full suite: a watermark rises only by
    however much the new peak EXCEEDS the old, so with the session's watermark
    already at 385 MB the allocation moved it 67 MB. That is the same property
    this module documents and it makes any peak-delta assertion inherently
    order-dependent. Resident size is not a watermark, so it tracks the
    allocation whatever ran first.
    """
    before = current_rss_bytes()
    block = np.ones(256 * 1024 * 1024 // 8, dtype=np.float64)
    block[::4096] = 2.0
    live = current_rss_bytes()
    peak = peak_rss_bytes()
    del block
    assert np.isfinite(peak) and np.isfinite(live)
    assert live - before >= 200 * 1024 * 1024
    # Same units. The lower bound carries a 10% slack because `ru_maxrss` is
    # `mm->hiwater_rss`, which the kernel updates LAZILY -- measured, it read
    # 470.8 MB against a live 471.3 MB taken an instant earlier, so the
    # watermark can trail current residency by a fraction of a percent. The
    # slack is nowhere near enough to absorb a 1024x unit error, which is
    # what this is for.
    assert 0.9 * live <= peak <= 100 * live


def test_current_rss_falls_after_a_release_and_the_watermark_does_not():
    """The two shims answer different questions, and only one is a watermark.

    Expected value determined independently: `ru_maxrss` is documented as a
    maximum over the process lifetime, so it cannot decrease; resident set
    size is what is mapped now, so freeing 256 MiB must bring it down. The
    bound is one-sided and loose because the allocator need not return pages
    to the OS immediately -- but numpy frees a block this size outright.

    Bug this catches: using `peak_rss_bytes` where `current_rss_bytes` is
    meant. The peak is the right instrument for "how much did this ever hold"
    and the wrong one for "how much does this workload hold", and the two
    agree right up until something earlier in the process allocated more --
    at which point the peak silently reports that earlier number instead.
    """
    block = np.ones(256 * 1024 * 1024 // 8, dtype=np.float64)
    block[::4096] = 2.0
    live = current_rss_bytes()
    watermark = peak_rss_bytes()
    del block
    released = current_rss_bytes()
    assert live - released >= 200 * 1024 * 1024
    assert peak_rss_bytes() >= watermark


@pytest.mark.slow
def test_a_child_measurement_is_not_contaminated_by_a_large_parent():
    """A fresh subprocess does NOT isolate a peak-RSS measurement.

    Expected value determined independently, and measured: `fork()` copies the
    parent's `mm->hiwater_rss` and `exec()` does not reset it on this kernel,
    so a child inherits the parent's high-water mark as a floor. Measured, the
    same child reports 119.95 MB spawned from a small parent and 493.28 MB --
    byte-identical to the parent's own peak -- spawned from one holding
    400 MiB. Resident set size is not a watermark, so it is unaffected.

    Bug this catches: THE ONE THAT ACTUALLY HAPPENED. The batch-size sweep
    below runs each batch in a fresh subprocess precisely to escape
    process-local state, and that was not enough: with a 256 MiB allocation
    earlier in the same pytest session, all three children reported the
    parent's watermark, the fitted slope collapsed to ~1e-11 B/series, and the
    number looked like a perfectly flat memory curve rather than an error.
    Pre-flight (k) again, one layer deeper than the check as written -- the
    contaminating state is INHERITED, so changing process is not escape.
    """
    before = peak_rss_bytes()
    lean_child = _measure_child(batch=1000)
    ballast = np.ones(400 * 1024 * 1024 // 8, dtype=np.float64)
    ballast[::4096] = 2.0
    after = peak_rss_bytes()
    heavy_child = _measure_child(batch=1000)
    del ballast

    # Stated against the PARENT's own watermark rather than against absolute
    # sizes, so the test says what it means and does not depend on what any
    # earlier test in this session happened to allocate.
    # The watermark rises only by however much the new peak EXCEEDS the old,
    # so a 400 MiB ballast need not move it by 400 MiB if this session already
    # allocated and freed something large. All that is required is that the
    # two watermarks are far enough apart for the 5% comparisons below to
    # discriminate between them.
    assert after >= 1.2 * before
    assert lean_child["watermark"] == pytest.approx(before, rel=0.05)
    assert heavy_child["watermark"] == pytest.approx(after, rel=0.05)
    # ...while the resident-size instrument reports the same child either way.
    assert heavy_child["peak"] == pytest.approx(lean_child["peak"], rel=0.05)


# --------------------------------------------------------------------------
# The analytic formula
# --------------------------------------------------------------------------


def test_output_slots_carry_four_scalars_not_two():
    """Both n_eff variants are per candidate, so the scalar count is 4.

    Expected value determined independently, by hand from design doc section
    9.4: per candidate the stored slots are theta-hat and its error (p each),
    beta and its error (k_beta each), then log_lik, k, n_eff_trend and
    n_eff_bic as float64, plus iterations (uint16) and status (uint8). At
    M=12, p=4, k_beta=4 that is 12 * (8 + 8 + 4) * 8 + 12 * 3 = 1920 + 36 =
    1956 B. Under the superseded count of 2 scalars it is 12 * 18 * 8 + 36 =
    1764 B, so the correction is worth exactly 192 B per series.

    Bug this catches: THE SUPERSEDED `2p + 2k_beta + 2`, which design doc
    section 9.4 still carried in its worked table while its own formula three
    paragraphs earlier said 4, and which the plan's fence transcribed. It
    propagates into bytes_per_series, tile_side and every downstream RAM
    projection. Nothing downstream can see it: 1764 and 1956 are both
    plausible, both scale the same way with B, and the error cancels out of
    every path-A-against-path-B comparison because it is common to both.
    """
    assert output_slot_bytes(n_models=12, p=4, k_beta=4) == 1956
    assert output_slot_bytes(n_models=12, p=4, k_beta=4) - 1764 == 192


def test_path_a_matches_the_corrected_worked_example():
    """Path A is 8682 B/series at the documented configuration.

    Expected value determined independently by summing design doc section
    9.4's table by hand: 5670 data (630 * 9) + 1956 output + 432 d-squared
    terms (6 * 9 * 8) + 120 augmented x (3 * 5 * 8) + 120 accumulators
    ((10 + 4 + 1) * 8) + 256 trust-region ((16 + 16) * 8) + 128 Hessian
    (16 * 8) = 8682.

    Bug this catches: the fence's 8490, which is this sum with the superseded
    output-slot count. Asserted as an absolute total AND term by term, so a
    failure says which term moved rather than only that the total did.
    """
    assert bytes_per_series(Backend.NUMPY_BATCHED, **CASE) == 8682
    assert 5670 + 1956 + 432 + 120 + 120 + 256 + 128 == 8682


def test_path_b_drops_only_the_per_series_solver_state():
    """Path B is 7626 B/series: data plus output slots only.

    Expected value determined independently: 5670 + 1956 = 7626, and the
    difference from path A is exactly path A's solver state, 1056 B. The
    saving is 1056 / 8682 = 12.16%.

    Bug this catches: claiming path B's memory advantage is transformative and
    letting that drive the stage-1 decision. It is 12.2%, because data and
    output slots are already 88% of the total -- so the reason to prefer path
    B is speed and the collapse of the ragged cliff, not memory. A backend
    formula that dropped the output slots too would report a far larger and
    entirely fictional saving.
    """
    path_a = bytes_per_series(Backend.NUMPY_BATCHED, **CASE)
    path_b = bytes_per_series(Backend.COMPILED, **CASE)
    assert path_b == 7626
    assert path_a - path_b == 1056
    assert (path_a - path_b) / path_a == pytest.approx(0.1216, abs=0.0005)
    assert (5670 + 1956) / path_a == pytest.approx(0.878, abs=0.001)


def test_per_point_regressors_add_the_design_matrix_per_series():
    """A per-point X adds N * k_beta * 8 bytes to both backends.

    Expected value determined independently: 630 * 4 * 8 = 20160 by hand.
    That is roughly 2.4x the entire rest of the per-series cost, so it is not
    a rounding error -- it changes tile_side by about a factor of two and is
    the difference between a configuration fitting in 16 GB and not.

    Bug this catches: treating the design matrix as one shared copy
    unconditionally. With a shared time axis and no per-point fields that is
    correct; with a per-point regressor field (a GIA model, say) X is
    per-series. Getting it wrong understates RAM by 70% in the regime where
    the hard 16 GB constraint actually binds.
    """
    for backend in Backend:
        shared = bytes_per_series(backend, **CASE)
        per_point = bytes_per_series(backend, **CASE, per_point_design=True)
        assert per_point - shared == 20160


def test_tile_side_floors_and_reflects_the_full_accounting():
    """tile_side floors, and the full accounting shrinks it against data-only.

    Expected value determined independently: floor(sqrt(1e9 / 8682)) =
    floor(339.4) = 339 with shared X, floor(sqrt(1e9 / 28842)) = floor(186.2)
    = 186 with per-point X, against the prompt's data-only
    floor(sqrt(1e9 / 5040)) = floor(445.4) = 445.

    Bug this catches: the fence asserted 187 for the per-point case while its
    own implementation floors -- sqrt(1e9/28650) is 186.83, so its expected
    value was rounded where its code truncates, and the test would have failed
    against the very implementation printed beneath it. Rounding up here
    overcommits a hard memory budget by a full tile row.
    """
    assert tile_side(10**9, 8682) == 339
    assert tile_side(10**9, 28842) == 186
    assert tile_side(10**9, 5040) == 445


def test_a_tile_that_does_not_fit_its_budget_is_refused():
    """A budget smaller than one series is an error, not a zero-wide tile.

    Expected value determined independently: floor(sqrt(budget / bytes)) is 0
    whenever the budget holds fewer than one series, and a tile of side 0
    holds no data at all -- the caller would loop forever making no progress.

    Bug this catches: returning 0 and letting the caller discover it. The
    number is plausible (a small budget really does not fit), so it flows into
    tiling arithmetic and produces an empty run rather than an error naming
    the budget.
    """
    with pytest.raises(ValueError, match="budget"):
        tile_side(1000, 8682)


# --------------------------------------------------------------------------
# The shape difference between the backends
# --------------------------------------------------------------------------


def test_thread_state_is_per_thread_and_absent_from_the_per_series_cost():
    """Path B's solver state is per thread, which is the whole shape change.

    Expected value determined independently, from design doc section 9.4's
    table with path B's L-BFGS optimizer term: 432 d-squared + 120 augmented
    x + 120 accumulators + 704 L-BFGS history (22 * 4 * 8) + 128 Hessian =
    1504 B per thread. At T=4 that is ~6 kB and at T=64 ~96 kB -- negligible
    either way, which is the point.

    Bug this catches: folding thread state into the per-series figure, which
    would make it appear 64 times over at T=64 and inflate path B's projected
    tile RAM by ~96 kB per series instead of ~96 kB per tile.
    """
    assert thread_state_bytes(d=3, k_beta=4, p=4) == 1504
    assert 432 + 120 + 120 + 704 + 128 == 1504
    per_series = bytes_per_series(Backend.COMPILED, **CASE)
    assert per_series == 7626
    assert thread_state_bytes(d=3, k_beta=4, p=4) not in (per_series - 7626,)


@pytest.mark.parametrize("threads", [1, 4, 64])
def test_peak_tile_memory_is_independent_of_thread_count_on_path_a(threads):
    """Path A's tile cost does not depend on how many threads run it.

    Expected value determined independently: path A's formula is
    B * per_series with no thread term at all, so the total at B=1000 is
    8 682 000 B whatever T is. Path B's is B * per_series + T * 1504, so it
    grows by exactly 1504 B per thread -- 94 752 B more at T=64 than at T=1.

    Bug this catches: a formula in which peak RAM scales with core count.
    Parallelism is within a tile and over series, never across tiles, and that
    is precisely what keeps peak RAM independent of T. A formula that
    multiplied the per-series solver state by T would make the 64-core box
    look like it needed 64x the RAM, and the 16 GB machine like it could not
    run at all.
    """
    assert tile_bytes(Backend.NUMPY_BATCHED, batch=1000, threads=threads, **CASE) == (
        1000 * 8682
    )
    expected_b = 1000 * 7626 + threads * 1504
    assert (
        tile_bytes(Backend.COMPILED, batch=1000, threads=threads, **CASE) == expected_b
    )


def test_path_b_thread_term_is_the_only_thread_dependence():
    """The T-dependence is 1504 B per thread and nothing else.

    Expected value determined independently: 1504 B per thread from the table
    above, so 63 extra threads cost 63 * 1504 = 94 752 B.

    Bug this catches: a thread term that also scaled with batch size, which
    would be per-series state wearing a thread label -- the exact confusion
    the two-formula shape exists to prevent.
    """
    one = tile_bytes(Backend.COMPILED, batch=1000, threads=1, **CASE)
    many = tile_bytes(Backend.COMPILED, batch=1000, threads=64, **CASE)
    assert many - one == 63 * 1504
    big_one = tile_bytes(Backend.COMPILED, batch=10_000, threads=1, **CASE)
    big_many = tile_bytes(Backend.COMPILED, batch=10_000, threads=64, **CASE)
    assert big_many - big_one == 63 * 1504


# --------------------------------------------------------------------------
# The formula against a real measurement
# --------------------------------------------------------------------------


def test_the_augmented_block_is_the_dominant_resident_term():
    """The engine materializes [y | X], and section 9.4 does not account for it.

    Expected value determined independently: `KalmanEngine._augment` ends in
    `np.concatenate([y[:, :, None], x], axis=2)`, producing a
    `(B, N, 1+k_beta)` float64 array. At N=630, k_beta=4 that is
    630 * 5 * 8 = 25 200 B/series, computed by hand from the shape. Section
    9.4's per-series total is 8682 B, so the block alone is 2.9x the entire
    documented cost and the true resident figure is 33 882 B.

    Bug this catches: budgeting a 10^7-point run against the streaming
    formula. `tile_side` at a 1 GB budget drops from 339 to 171, so a tile
    sized by section 9.4 needs about 3.9x the RAM it was allotted -- and the
    16 GB machine is a hard constraint, so the run does not degrade, it dies.
    The `np.broadcast_to` immediately above the concatenate is a view and
    costs nothing, which is exactly why the copy is easy to miss on a read.
    """
    assert augmented_block_bytes(n_time=630, k_beta=4) == 25200
    target = bytes_per_series(Backend.NUMPY_BATCHED, **CASE)
    resident = resident_bytes_per_series(Backend.NUMPY_BATCHED, **CASE)
    assert resident - target == 25200
    assert resident == 33882
    assert tile_side(10**9, resident) == 171
    assert tile_side(10**9, target) == 339


@pytest.mark.slow
def test_measured_peak_rss_is_at_least_the_arrays_that_provably_exist():
    """Measured peak RSS grows with B at the rate the accounting predicts.

    Expected value determined independently: the arrays are named and their
    shapes are known, so the per-series floor is arithmetic --
    `y` (630*8) + mask (630) + the augmented block (630*5*8) + the engine's
    O(d^2) working set (672) = 31 542 B/series. That is a FLOOR, not an
    estimate: every one of those arrays demonstrably exists and is
    simultaneously live during the evaluation. The upper bound is 2x, which
    admits per-step transients and allocator rounding while still rejecting a
    term that scales with an extra factor of N or k_beta.

    Measured on this machine: 43 392 B/series against the 31 542 floor,
    intercept ~76 MB. The ~12 kB residual is per-step temporaries at peak.

    Each batch size runs in a FRESH SUBPROCESS. `ru_maxrss` is a high-water
    mark that never decreases, so an in-process reading is contaminated by
    every allocation any earlier test made, and a later smaller batch reads as
    a delta of zero -- pre-flight (k), a quantity whose meaning depends on
    process-local state.

    Bug this catches: an accounting wrong by a factor, which the section 11.4
    calibration tile would otherwise inherit as a black box. It is asserted as
    a slope rather than an absolute peak because a process carries a large
    real per-run constant -- interpreter, numpy, imports -- that is not
    per-series; comparing absolute peaks would measure that constant as much
    as the formula.
    """
    measured, intercept = measure_evaluation_rss_slope(
        batches=(1000, 3000, 5000), n_time=630
    )
    floor = data_and_workspace_bytes_per_series(d=3, k_beta=4, n_time=630)
    assert floor == 31542
    print(
        f"\nfloor {floor} B/series, measured {measured:.0f} B/series, "
        f"intercept {intercept / 1e6:.1f} MB"
    )
    assert floor <= measured <= 2.0 * floor
