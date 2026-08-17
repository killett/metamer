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

import dataclasses
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import TypedDict

import numpy as np
import pytest
from _pytest.outcomes import Skipped

from metamer.core import machine as machine_module
from metamer.core import memory as memory_module
from metamer.core.machine import current_rss_bytes, peak_rss_bytes
from metamer.core.memory import (
    ACCUMULATION_TRANSIENT_FACTOR,
    DEFAULT_BUDGET_FRACTION,
    LBFGS_MAXCOR,
    SLOPE_BAND_FACTOR,
    AccumulationReport,
    CalibrationPoint,
    CalibrationResult,
    FloorReport,
    LinearityReport,
    MemoryEngineLabel,
    SolverPlacement,
    accumulation_report,
    calibrate,
    data_and_workspace_bytes_per_series,
    default_budget_gb,
    linearity_report,
    measure_evaluation_rss_slope,
    measure_floor,
    measure_tile_peak,
    memory_engine_label,
    output_slot_bytes,
    resident_bytes_per_series,
    resident_tile_bytes,
    slope_band,
    solver_state_bytes,
    tile_side,
)
from tests import conftest
from tests.conftest import rss_validity


class _Case(TypedDict):
    """The section 9.4 worked-example parameters the PER-SERIES cost takes.

    A TypedDict rather than a plain dict so `**CASE` type-checks: mypy
    otherwise has to assume a `dict[str, int]` might land in the `bool`
    `per_point_design` slot.

    **`d` IS ABSENT AND THAT IS THE 2026-08-14 CORRECTION**, not an oversight:
    the state dimension reaches the formula only through the solver working
    set, and that set is live for one series at a time.
    """

    k_beta: int
    p_max: int
    n_time: int
    n_models: int


# Corrected 2026-08-07: the output-slot scalar count is 4
# (log_lik, k, n_eff_trend, n_eff_bic) and not 2. Corrected again 2026-08-14:
# it is 5, plus an object pointer and an int64, and the widths are p_max.
CASE: _Case = {"k_beta": 4, "p_max": 4, "n_time": 630, "n_models": 12}

# Design doc section 9.4's `d`, which only the tile-level functions take.
STATE_DIM = 3


# --------------------------------------------------------------------------
# The RSS shim
# --------------------------------------------------------------------------


@pytest.mark.machine
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


@pytest.mark.machine
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


_CHILD = (
    "import sys; sys.path.insert(0, 'src');"
    "from metamer.core.machine import peak_rss_bytes;"
    "print(peak_rss_bytes())"
)

_PARENT = """
import sys, subprocess
sys.path.insert(0, "src")
import numpy as np
from metamer.core.machine import peak_rss_bytes, current_rss_bytes

mode = sys.argv[1]
if mode in ("held", "freed"):
    ballast = np.ones(400 * 1024 * 1024 // 8, dtype=np.float64)
    ballast[::4096] = 2.0
    if mode == "freed":
        del ballast

out = subprocess.run([sys.executable, "-c", {child!r}], capture_output=True, text=True)
print(peak_rss_bytes(), current_rss_bytes(), out.stdout.strip())
"""


_LAUNCHER = """
import sys, subprocess
# IMPORTS NOTHING LARGE, ON PURPOSE. This process exists to break the
# inheritance chain: it is spawned by pytest and so inherits the session's
# watermark, but its OWN high-water is a bare interpreter -- and a child
# inherits only the parent's own. So the parent below starts from a known
# floor whatever the session has allocated, which is what makes this test
# order-independent instead of merely order-independent-today.
out = subprocess.run([sys.executable, "-c", {parent!r}, sys.argv[1]],
                     capture_output=True, text=True)
sys.stdout.write(out.stdout)
sys.stderr.write(out.stderr)
"""


def _generation(mode):
    """Run a controlled parent behind a bare launcher, and read it and its child.

    Three processes, and the launcher is load-bearing: see `_LAUNCHER`. Nothing
    here reads the pytest session's watermark, which is the defect that made the
    previous version of this test order-dependent.

    Args:
        mode: `small`, `held`, or `freed`.

    Returns:
        `(parent_peak, parent_current, child_peak)`, all in bytes.
    """
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            _LAUNCHER.format(parent=_PARENT.format(child=_CHILD)),
            mode,
        ],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[1],
        check=True,
    )
    parent_peak, parent_current, child_peak = result.stdout.split()
    return float(parent_peak), float(parent_current), float(child_peak)


@pytest.mark.slow
@pytest.mark.machine
def test_a_child_inherits_the_parents_own_high_water_mark_and_not_its_current_rss():
    """**OPEN QUESTION 12, CLOSED 2026-08-12.** Which value does a child inherit?

    `machine.py` and this module both said `ru_maxrss` is "inherited across
    fork/exec" without saying **which value**, and the two candidates -- the
    parent's watermark and the parent's current RSS -- are different claims.
    This varies them independently: `freed` allocates 400 MiB and drops it, so
    its watermark is high while its current RSS is back at the baseline.

    Measured, three runs, reproducible (MB):

        mode    parent_peak  parent_current  child_peak
        small          73.9            74.1        73.9
        held          493.3           493.7       493.3
        freed         493.3            74.3       493.3

    **The child follows the WATERMARK.** `freed` and `held` agree and both are
    ~6.7x `small`, while `freed`'s current RSS is indistinguishable from
    `small`'s -- so current RSS cannot be what propagates.

    Bug this catches: the reading this project was one measurement away from
    making, that spawning a fresh process isolates a peak-RSS measurement
    whenever the parent has freed its memory. It does not. The batch-size sweep
    runs each batch in a fresh subprocess for exactly that reason, and a
    contaminated parent flattens the fitted slope to ~1e-11 B/series -- a
    perfectly flat memory curve rather than an error.

    **THE BASELINE IS THIS TEST'S OWN**, which is the other half of closing the
    question. The previous version asserted `after >= 1.2 * before` with
    `before` read from the pytest session's watermark, so it failed or passed
    according to what earlier tests in the sweep had allocated -- three
    recorded instances. Every process here is spawned by the test.
    """
    small_peak, small_current, small_child = _generation("small")
    held_peak, held_current, held_child = _generation("held")
    freed_peak, freed_current, freed_child = _generation("freed")

    # The three conditions are what the test says they are. Asserted first,
    # because a `freed` parent that never allocated makes everything below
    # vacuously true -- the fixture has to be able to fail.
    assert held_peak > 3 * small_peak
    assert freed_peak > 3 * small_peak
    assert freed_current == pytest.approx(small_current, rel=0.15)

    # ...and the child follows the watermark, not the current RSS. `freed` is
    # the decisive line: its child reports a number the parent NO LONGER HOLDS.
    assert freed_child == pytest.approx(freed_peak, rel=0.05)
    assert held_child == pytest.approx(held_peak, rel=0.05)
    assert freed_child > 3 * freed_current
    assert freed_child > 3 * small_child

    # THE `small` ROW IS NOT `small_child == small_peak`, AND FINDING THAT OUT
    # HERE IS WORTH RECORDING. The small parent is itself spawned by pytest, so
    # it INHERITS pytest's watermark -- measured 99.6 MB against its own 74.2 --
    # while its child gets only the 74.2 it generated itself. That is the
    # non-compounding rule below, showing up inside this test, and it is why the
    # `small` child is compared against the parent's CURRENT RSS: for a process
    # that allocated nothing beyond its imports, current is its own high-water.
    assert small_child == pytest.approx(small_current, rel=0.10)


_GRANDCHILD = (
    "import sys; sys.path.insert(0, 'src');"
    "from metamer.core.machine import peak_rss_bytes;"
    "print(peak_rss_bytes())"
)

_MIDDLE = """
import sys, subprocess
sys.path.insert(0, "src")
from metamer.core.machine import peak_rss_bytes

# ALLOCATES NOTHING. Whatever it reports, it inherited.
out = subprocess.run([sys.executable, "-c", {grandchild!r}], capture_output=True, text=True)
print(peak_rss_bytes(), out.stdout.strip())
"""

_LAUNCHER_ONE_ARGLESS = """
import sys, subprocess
out = subprocess.run([sys.executable, "-c", {top!r}], capture_output=True, text=True)
sys.stdout.write(out.stdout)
sys.stderr.write(out.stderr)
"""

_TOP = """
import sys, subprocess
sys.path.insert(0, "src")
import numpy as np
from metamer.core.machine import peak_rss_bytes

ballast = np.ones(400 * 1024 * 1024 // 8, dtype=np.float64)
ballast[::4096] = 2.0
out = subprocess.run([sys.executable, "-c", {middle!r}], capture_output=True, text=True)
print(peak_rss_bytes(), out.stdout.strip())
"""


@pytest.mark.slow
@pytest.mark.machine
def test_the_inheritance_does_not_compound_across_a_generation():
    """What propagates is the parent's OWN high-water, not its REPORTED peak.

    The distinction is the whole reason a plain "the watermark is inherited"
    sentence is not enough, and it is what reconciles the two measurements this
    project had on record. A middle process that **allocates nothing** still
    *reports* its grandparent's 493 MB -- and its own child reports 74 MB.

    Measured, twice, reproducible (MB):

        top reported 493.1 | middle reported 493.1, current 74.3 | grandchild 74.1

    So `peak_rss_bytes()` is `max(inherited, this process's own high-water)`,
    and a child inherits only the second term. The 2026-08-10 observation
    recorded in `PROGRESS.md` -- a probe reading 454.8 MB whose own child
    reported 84.6 MB, the probe's *current* RSS -- is this, not a
    contradiction: the probe had allocated nothing, so its own high-water was
    its current RSS.

    Bug this catches: taking the inheritance as transitive and concluding that a
    measurement two processes down is unusable. It is usable, and knowing that
    is what makes the calibration tile implementable -- **section 11.4 measures
    bytes-per-series in a child, so it needs a stated rule rather than a
    warning.**
    """
    # BEHIND THE SAME BARE LAUNCHER as the test above, and for the same reason:
    # spawned straight from pytest, the top process would inherit the session's
    # watermark, and if that exceeds its own 400 MiB the first assertion below
    # compares an inherited number against a generated one.
    script = _LAUNCHER_ONE_ARGLESS.format(
        top=_TOP.format(middle=_MIDDLE.format(grandchild=_GRANDCHILD))
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[1],
        check=True,
    )
    top_peak, middle_peak, grandchild_peak = (
        float(value) for value in result.stdout.split()
    )

    assert middle_peak == pytest.approx(top_peak, rel=0.05)
    assert grandchild_peak < middle_peak / 3


# --------------------------------------------------------------------------
# The analytic formula
# --------------------------------------------------------------------------


def test_the_output_slot_term_is_the_inventory_fit_preallocates_field_by_field():
    """Every field `fit` holds until the tile write is charged, and no others.

    Expected values built by hand from `fit.py:197-209`, ASSERTED PER FIELD
    rather than as a total, because a total is precisely what hid the previous
    two errors: the solver term was 12.1% high while this one was 25% low, and
    the sum sat within 0.5% of a measurement while neither term was right.

        theta, theta_unconstrained, theta_err   3 * p_max * 8   = 96
        beta, beta_err                          2 * k_beta * 8  = 64
        loglik, k, n, n_eff_bic, n_eff_trend    5 * 8           = 40
        n_iter                                  int64           =  8
        init_rung                               object pointer  =  8
        outcome                                 uint8           =  1
                                                                 ---
                                                                  217

    so 12 * 217 = 2604 B/series at M = 12. The superseded
    `M*(2p + 2k_beta + 4)*8 + 3M` gives 12 * 163 = 1956.

    Bug this catches: the four omissions returning one at a time --
    `theta_unconstrained` (32 B), `n` (8 B), the `init_rung` object pointer
    (8 B), and `n_iter` charged as a uint16 rather than an int64 (6 B). Each is
    individually plausible and invisible in a total; each is asserted here on
    its own line. **The published magnitude of this correction was itself
    wrong**: it was recorded as +46 B/candidate, which is this list with one
    8-byte member dropped, and 217 - 163 = 54.
    """
    theta_slots = 3 * 4 * 8
    beta_slots = 2 * 4 * 8
    float_scalars = 5 * 8
    n_iter_slot = 8
    init_rung_pointer = 8
    outcome_slot = 1
    assert theta_slots == 96
    assert beta_slots == 64
    assert float_scalars == 40
    per_candidate = (
        theta_slots
        + beta_slots
        + float_scalars
        + n_iter_slot
        + init_rung_pointer
        + outcome_slot
    )
    assert per_candidate == 217

    assert output_slot_bytes(n_models=12, p_max=4, k_beta=4) == 12 * per_candidate
    assert output_slot_bytes(n_models=12, p_max=4, k_beta=4) == 2604

    # Against the superseded formula, term by term rather than as a delta.
    superseded = 12 * ((2 * 4 + 2 * 4 + 4) * 8 + 3)
    assert superseded == 1956
    assert 2604 - superseded == 12 * 54


def test_the_per_series_cost_is_the_data_tile_and_the_output_slots_only():
    """8274 B/series: nothing the optimizer or the engine holds is per-series.

    Expected value determined independently by summing what one more series in
    the tile costs: 5670 data (630 * 9, float64 `y` plus a byte of mask) + 2604
    output slots = 8274. **The solver state is not here**, because `fit.py:223`
    is `for b in range(batch): optimize_series(obj, y[b:b+1], ...)` -- one live
    working set whatever B is.

    Bug this catches: the superseded 8722, which is this sum plus 1056 B of
    solver state and 40 B of the engine's reused `[y | X]` row, both charged
    per series. It described design doc section 8.3's batched trust-region,
    which Task 19 deleted. The error is 5.4% and in the SAFE direction, which
    is why it survived a validating measurement -- and the measurement drove a
    batched evaluation, which really does hold those blocks per series.
    """
    assert resident_bytes_per_series(**CASE) == 8274
    assert 5670 + 2604 == 8274
    assert 630 * 9 == 5670
    # The superseded 8722, decomposed into the three corrections, each signed:
    # +648 of output slots it never charged, -1056 of solver state it charged
    # per series, -40 of the engine's reused row it charged per series.
    assert 8722 + 648 - 1056 - 40 == 8274


def test_both_placements_agree_on_the_slope_and_differ_only_in_the_constant():
    """One formula, one slope, two constants -- not two shapes.

    Expected values determined independently: the per-series cost takes neither
    a placement nor `d`, so it is 8274 either way; the constant is 11 984 B
    once under `PER_SERIES_LIVE` and 4 * 11 984 = 47 936 B under `PER_THREAD`
    at four threads.

    Bug this catches: someone restoring design doc section 9.4's
    *"the formulas have different shapes, not just different constants"*. That
    was true of the two DESIGNS and is false of the code -- `CompiledEngine`
    pranges over whatever batch `score` is handed and `fit` hands it one series,
    so both engines have the same tile shape. Under the superseded formula the
    two published tile sides differed (338 against 361) purely because of this
    error, and a reader planning a run against the wrong one was told to.
    """
    per_series = resident_bytes_per_series(**CASE)
    live = solver_state_bytes(
        SolverPlacement.PER_SERIES_LIVE, d=STATE_DIM, k_beta=4, p_max=4, threads=4
    )
    threaded = solver_state_bytes(
        SolverPlacement.PER_THREAD, d=STATE_DIM, k_beta=4, p_max=4, threads=4
    )
    assert per_series == 8274
    assert live == 11984
    assert threaded == 4 * 11984 == 47936

    # The slope is identical and the tiles differ by exactly the constants.
    for batch in (1, 1000, 10_000):
        both = {
            placement: resident_tile_bytes(
                batch=batch,
                placement=placement,
                threads=4,
                d=STATE_DIM,
                **CASE,
            )
            for placement in SolverPlacement
        }
        difference = (
            both[SolverPlacement.PER_THREAD] - both[SolverPlacement.PER_SERIES_LIVE]
        )
        assert difference == threaded - live
        assert difference == 3 * 11984


def test_per_point_regressors_add_the_design_matrix_per_series():
    """A per-point X adds N * k_beta * 8 bytes, and it is the one branch left.

    Expected value determined independently: 630 * 4 * 8 = 20160 by hand.
    That is roughly 2.4x the entire rest of the per-series cost, so it is not
    a rounding error -- it changes tile_side by about a factor of two and is
    the difference between a configuration fitting in 16 GB and not.

    Bug this catches: treating the design matrix as one shared copy
    unconditionally. With a shared time axis and no per-point fields that is
    correct; with a per-point regressor field (a GIA model, say) X is
    per-series. Getting it wrong understates RAM by 70% in the regime where
    the hard 16 GB constraint actually binds.

    **THE REGIME SHIPS TESTED THOUGH THE FEATURE IS REFUSED** (a3), and this is
    now the only branch the per-series formula has -- the placement branch moved
    to the tile level on 2026-08-14. A branch nothing exercises rots while
    unreachable, and `batch.validation` quotes both sides of this one in the
    refusal a user actually reads.
    """
    shared = resident_bytes_per_series(**CASE)
    per_point = resident_bytes_per_series(**CASE, per_point_design=True)
    assert per_point - shared == 20160
    assert 630 * 4 * 8 == 20160
    assert per_point == 28434


def test_tile_side_floors_and_reflects_the_full_accounting():
    """tile_side floors, and the full accounting shrinks it against data-only.

    Expected values re-derived by hand from the corrected per-series cost, at a
    10**9 budget: 10**9 / 8274 = 120 860.5 and 347**2 = 120 409 <= 120 860.5 <
    121 104 = 348**2, so the side is **347**; 10**9 / 28434 = 35 169.9 and
    187**2 = 34 969 <= 35 169.9 < 35 344 = 188**2, so the per-point side is
    **187**. The prompt's data-only formula still gives floor(sqrt(1e9/5040)) =
    445. The superseded pair is ~~338 / 186~~, from the superseded 8722.

    **NEITHER NUMBER WAS READ OFF A FAILURE.** Both bracketing squares are
    written out above precisely so the next reader can check rather than trust,
    which is the discipline the `GOLDEN_*` constants carry and the one this
    cascade exists because nobody applied.

    **THE BUDGET IS 10**9 B AND THE UNIT IS NOT DECORATION**: `run.py` converts
    `memory_budget_gb` with `1024**3`, which is 7.4% more bytes for the same
    word and gives 350 rather than 347. Tasks 2 and 3 own resolving that.

    Bug this catches: the fence asserted 187 for the per-point case while its
    own implementation floors -- sqrt(1e9/28650) is 186.83, so its expected
    value was rounded where its code truncates, and the test would have failed
    against the very implementation printed beneath it. Rounding up here
    overcommits a hard memory budget by a full tile row.
    """
    assert 347**2 <= 10**9 / 8274 < 348**2
    assert 187**2 <= 10**9 / 28434 < 188**2
    assert tile_side(10**9, 8274) == 347
    assert tile_side(10**9, 28434) == 187
    assert tile_side(10**9, 5040) == 445
    # The unit really does move the answer, so the pair carries it.
    assert tile_side(1024**3, 8274) == 360


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
        tile_side(1000, 8274)


# --------------------------------------------------------------------------
# The budget a config that names none resolves to
# --------------------------------------------------------------------------


def test_the_default_budget_is_a_fraction_of_total_ram_and_never_of_available(
    monkeypatch,
):
    """An unset budget resolves from TOTAL RAM, with free RAM nowhere in it.

    Expected values determined independently: the fraction is policy at 0.25
    and the field is in SI gigabytes, so 0.25 x 16 000 000 000 B is **4.0 GB
    exactly**. The available figure is set to a sixteenth of the total, so an
    available-RAM default gives **0.25** and `min(total, available)` gives the
    same -- both differ from the expected value by 16x, which is (i7): the
    fixture is placed where the three candidate rules disagree rather than
    where they happen to coincide.

    Both readings are moved through `psutil.virtual_memory` rather than through
    `machine.total_ram_bytes`, so a defect that reads `psutil` directly is
    caught as well as one that reads the wrong helper.

    Bug this catches: a default taken from available RAM. **Its symptom is not
    an error** -- the derived tile side moves with whatever else the machine is
    doing, so a second run against the same store derives a smaller side, hits
    `completion.resume_tile_side`'s *stored > derived* arm and refuses. A
    resume that fails because a browser was open defeats section 15.5's
    burst-and-resume argument, which is the reason the budget is run-relevant
    in the first place. The measured spread of the available figure on this one
    machine is in `PROGRESS.md`'s *What Task 3 established*, once.
    """
    import psutil

    monkeypatch.setattr(
        psutil,
        "virtual_memory",
        lambda: SimpleNamespace(total=16_000_000_000, available=1_000_000_000),
    )

    assert DEFAULT_BUDGET_FRACTION == 0.25
    assert default_budget_gb() == 4.0
    # The discriminator, stated as its own value rather than left implicit: an
    # available-RAM default is a DIFFERENT number on this fixture, so the
    # equality above is not satisfied by a machine where the two readings agree.
    assert machine_module.available_ram_bytes() == 1_000_000_000
    assert 1_000_000_000 * DEFAULT_BUDGET_FRACTION / 10**9 == 0.25


def test_the_default_budget_follows_a_cgroup_limit(tmp_path, monkeypatch):
    """Inside a container the default is a fraction of the ALLOWANCE.

    Expected value determined independently: `total_ram_bytes` is
    `min(host, any readable limit)` since Task 1, so a 2 GB limit on this
    16.5 GB host gives 2 000 000 000 B, and 0.25 of that is **0.5 GB**.
    Constructed, because this machine has no cgroup limit -- see
    `tests/test_machine.py`, where the same gap is recorded.

    Bug this catches: `default_budget_gb` reading `psutil` directly rather than
    going through the cgroup-aware helper, which sizes a 2 GB container's tiles
    from the host's 16.5 GB. **The consequence is an OOM kill, not a slow run**,
    and every number in the process -- budget, tile side, provenance -- would be
    internally consistent and all wrong.
    """
    limit = tmp_path / "memory.max"
    limit.write_text("2000000000\n")
    monkeypatch.setattr(machine_module, "CGROUP_V2_PATH", str(limit))
    monkeypatch.setattr(machine_module, "CGROUP_V1_PATH", str(tmp_path / "absent"))

    assert machine_module.total_ram_bytes() == 2_000_000_000
    assert default_budget_gb() == 0.5


# --------------------------------------------------------------------------
# The shape difference between the backends
# --------------------------------------------------------------------------


def test_the_solver_constant_is_scipys_workspace_plus_the_engines():
    """11 984 B, and scipy's L-BFGS-B workspace is 93% of it.

    Expected values determined independently, by reading the allocations rather
    than the old formula:

        engine     6*d*d*8 = 432, d*(1+k_beta)*8 = 120,
                   (k_beta*(k_beta+1)/2 + k_beta + 1)*8 = 120,
                   the reused (1, 1+k_beta) row = 40          ->    712
        optimizer  wa = (2*m*p + 5*p + 11*m*m + 8*m)*8 at m=10 ->  10 240
                   x, low_bnd, upper_bnd, g = 4*p*8           ->     128
                   nbd (p) and iwa (3p), 8 B/int              ->     128
                   dsave 29 + isave 44 + lsave 4 + task 2
                     + ln_task 2, all 8 B                     ->     648
        Hessian    p*p*8                                      ->     128
                                                                  ------
                                                                   11 984

    Bug this catches: THE SUPERSEDED OPTIMIZER TERM, which is the same defect as
    the deleted `Backend` and sat in the same function. It charged
    `(p**2 + 4p)*8 = 256 B` for section 8.3's *"dense quasi-Newton trust-region
    model"*, deleted with Task 19, and `22*p*8 = 704 B` for an L-BFGS history.
    `optimize.py:531` runs scipy L-BFGS-B for BOTH engines, and scipy's
    workspace is dominated by `11*m*m` -- **1100 doubles that do not depend on
    `p` at all** -- so `22p*8` is not the same quantity with a different
    constant, it is the wrong shape. The whole constant was understated 11.3x.

    It is a constant, so it does not move `tile_side`. It IS what Task 4's
    intercept and Task 7's cross-check measure, so a 1056 B model against an
    ~12 kB reality is a discrepancy someone would have reconciled the wrong way.
    """
    engine = 432 + 120 + 120 + 40
    workspace = (2 * 10 * 4 + 5 * 4 + 11 * 10 * 10 + 8 * 10) * 8
    vectors = 4 * 4 * 8
    integer_arrays = 4 * 4 * 8
    saves = (29 + 44 + 4 + 2 + 2) * 8
    hessian = 4 * 4 * 8
    assert engine == 712
    assert workspace == 10240
    assert saves == 648
    assert engine + workspace + vectors + integer_arrays + saves + hessian == 11984

    assert (
        solver_state_bytes(
            SolverPlacement.PER_SERIES_LIVE, d=STATE_DIM, k_beta=4, p_max=4
        )
        == 11984
    )
    # The superseded term, kept so the size of the correction is on the record.
    assert 432 + 120 + 120 + 256 + 128 == 1056


def test_scipys_maxcor_default_is_still_what_the_optimizer_term_assumes():
    """The dominant term is `11 * maxcor**2`, so the default is load-bearing.

    Read from scipy's own signature, which is a different construction from
    this module's arithmetic (j): the constant is not derived from the same
    place it is checked against.

    Bug this catches: scipy changing `maxcor`'s default and the optimizer term
    silently describing a workspace that no longer exists. At m=10 `wa` is 1280
    doubles; at m=20 it would be 4560, a 3.6x change in the dominant term, and
    nothing in this project's own source would move.
    """
    import inspect

    from scipy.optimize import _lbfgsb_py

    default = inspect.signature(_lbfgsb_py._minimize_lbfgsb).parameters["maxcor"]
    assert default.default == LBFGS_MAXCOR == 10


@pytest.mark.parametrize("batch", [1, 1000, 10_000])
def test_the_tile_solver_term_does_not_grow_with_batch(batch):
    """The solver state is added once per tile, never once per series.

    Expected value determined independently: `batch * 8274 + 11 984` under
    `PER_SERIES_LIVE` at any thread count, so the constant is the SAME number
    at B=1 and at B=10 000 -- 11 984 B, not 11 984 * B.

    Bug this catches: F2 directly, and the mutation is one character --
    multiplying `solver_state_bytes` by `batch`. At B = 114 244 (a 338-point
    tile side) that is 120 MB of memory the run does not hold and 12.1% of the
    per-series figure, and it survived a validating measurement because the
    instrument drove a batched evaluation which really does allocate that way.
    """
    for threads in (1, 4, 64):
        total = resident_tile_bytes(
            batch=batch,
            placement=SolverPlacement.PER_SERIES_LIVE,
            threads=threads,
            d=STATE_DIM,
            **CASE,
        )
        assert total == batch * 8274 + 11984
        assert total - batch * 8274 == 11984


def test_the_thread_term_is_the_only_thread_dependence():
    """Under the unreachable placement T scales the constant and nothing else.

    Expected value determined independently: 11 984 B per thread, so 63 extra
    threads cost 63 * 11 984 = 754 992 B whatever the batch is.

    Bug this catches: a thread term that also scaled with batch size, which
    would be per-series state wearing a thread label. **This is the (i2)
    positive control for the unreachability assertion**: without it, "the
    batched placement is not reachable through `run()`" is equally satisfied by
    a branch that does not work at all.
    """
    for batch in (1000, 10_000):
        one = resident_tile_bytes(
            batch=batch,
            placement=SolverPlacement.PER_THREAD,
            threads=1,
            d=STATE_DIM,
            **CASE,
        )
        many = resident_tile_bytes(
            batch=batch,
            placement=SolverPlacement.PER_THREAD,
            threads=64,
            d=STATE_DIM,
            **CASE,
        )
        assert one == batch * 8274 + 11984
        assert many == batch * 8274 + 64 * 11984
        assert many - one == 63 * 11984 == 754992


def test_a_thread_count_below_one_is_refused():
    """Zero threads would zero the whole term, which is a plausible number.

    Expected behaviour determined independently: `PER_THREAD` multiplies the
    constant by `threads`, so `threads=0` returns 0 -- a tile total that reads
    as "the solver costs nothing" rather than as an error.

    Bug this catches: a thread count arriving as 0 from an unresolved budget
    and silently deleting the only thread-dependent quantity in the formula.
    Both placements refuse, because the argument is wrong in both even where
    one of them ignores its value.
    """
    for placement in SolverPlacement:
        with pytest.raises(ValueError, match="threads must be at least 1"):
            solver_state_bytes(placement, d=STATE_DIM, k_beta=4, p_max=4, threads=0)


def test_the_two_engines_share_an_engine_id_and_not_a_memory_label():
    """`EngineId` answers a different question, and gives the wrong answer here.

    Expected values determined independently by reading the classes:
    `kalman.py:107` and `compiled.py:208` both set `engine_id = EngineId.KALMAN`,
    deliberately, because the two compute the same likelihood by the same
    recursion and their scores must stay rankable against each other.

    Bug this catches: a calibration cache keyed on `EngineId`, which would serve
    one engine's measured slope to the other. `CompiledEngine` allocates
    `accum`, `sum_log_s`, `n_used` and `degenerate` per series inside its
    `prange`, where a batched `KalmanEngine` would hold one `(B, d, d)` block --
    so the day a batched driver lands the two really do cost different amounts,
    and the key that must already distinguish them cannot be the one that must
    not.
    """
    from metamer.core.engines.compiled import CompiledEngine
    from metamer.core.engines.kalman import KalmanEngine

    kalman, compiled = KalmanEngine(), CompiledEngine()
    assert kalman.engine_id is compiled.engine_id
    assert memory_engine_label(kalman) is MemoryEngineLabel.KALMAN_NUMPY
    assert memory_engine_label(compiled) is MemoryEngineLabel.KALMAN_COMPILED
    assert memory_engine_label(kalman) is not memory_engine_label(compiled)


def test_an_unaccounted_engine_has_no_memory_label():
    """A default would file an unmeasured engine under a measured engine's key.

    Bug this catches: `memory_engine_label` falling back to a label rather than
    raising. The cache would then hit, the run would proceed on another engine's
    slope, and nothing anywhere would report it -- an under-measured budget
    against a hard memory constraint is an OOM kill, not a slow run.
    """

    class _Other:
        engine_id = None

    with pytest.raises(TypeError, match="no memory label"):
        memory_engine_label(_Other())  # type: ignore[arg-type]


def test_the_slope_band_is_two_sided():
    """A slope materially BELOW the formula is a finding too.

    Expected values determined independently: the band around 8274 B/series at
    a factor of 1.5 is (5516.0, 12 411.0).

    Bug this catches: the one-sided form -- *"treat any factor above ~1.5x as a
    missing term"* -- which is what the standing check said until 2026-08-14 and
    which **would have passed every formula defect found that day**. A formula
    charging for something the code does not hold reads as headroom, and the
    headroom hides whatever else is wrong.
    """
    low, high = slope_band(8274)
    assert SLOPE_BAND_FACTOR == 1.5
    assert low == pytest.approx(5516.0)
    assert high == pytest.approx(12411.0)
    assert low < 8274 < high
    # Both directions, which is the whole correction.
    assert not low <= 5000 <= high
    assert not low <= 13000 <= high
    with pytest.raises(ValueError, match="positive prediction"):
        slope_band(0)


# --------------------------------------------------------------------------
# The formula against a real measurement
# --------------------------------------------------------------------------


def test_the_reused_row_is_inside_the_constant_and_not_a_per_series_term():
    """The engine's `[y | X]` row is 40 B once, not 40 B per series.

    Expected value determined independently from the shape the engines
    allocate: both index the observation and the design columns out of one
    reused `(B, 1+k_beta)` float64 row, and `fit` gives them B = 1, so the row
    is `(1 + 4) * 8 = 40` B for the whole tile. It is inside
    `solver_state_bytes`, whose engine part is 712 = 432 + 120 + 120 + 40.

    Bug this catches TWO things. First, `streaming_overhead_bytes` returning as
    a per-series term: it charged 40 B/series on path A and 8 B/series on path
    B, which is the same defect as F2 one term over, and its 40 B is still
    inside every published 8722. Second, a return to materializing `[y | X]`,
    which is what `_augment` did until 2026-08-10 --
    `np.concatenate([y[:, :, None], x], axis=2)`, a `(B, N, 1+k_beta)` float64
    array, 25 200 B/series at N=630, k_beta=4. That one WAS per-series, it did
    not vanish when the design was shared, and it put `tile_side` at 171. The
    `np.broadcast_to` immediately above the concatenate is a view and costs
    nothing, which is exactly why the copy was easy to miss on a read.

    The guard against the second is arithmetic on the tile total rather than a
    reading of the source: at B = 1000 a returning augmented block would add
    25 200 000 B, which is three times the whole tile.
    """
    engine_part = solver_state_bytes(
        SolverPlacement.PER_SERIES_LIVE, d=STATE_DIM, k_beta=4, p_max=4
    ) - (10240 + 128 + 128 + 648 + 128)
    assert engine_part == 712
    assert engine_part - (432 + 120 + 120) == 40

    # The row does not appear in the per-series cost at any batch size.
    for batch in (1, 1000):
        total = resident_tile_bytes(
            batch=batch,
            placement=SolverPlacement.PER_SERIES_LIVE,
            threads=1,
            d=STATE_DIM,
            **CASE,
        )
        assert total == batch * 8274 + 11984

    # And a returned augmented block would be unmissable at tile scale.
    assert 1000 * 25200 > 3 * (1000 * 8274 + 11984)


@pytest.mark.slow
@pytest.mark.machine
def test_measured_peak_rss_is_at_least_the_arrays_that_provably_exist():
    """Measured peak RSS grows with B at the rate the accounting predicts.

    Expected value determined independently: the arrays are named and their
    shapes are known, so the per-series floor is arithmetic -- `y` (630*8) +
    mask (630) + the engine's O(d^2) working set + the one reused `[y | X]`
    row. That is a FLOOR, not an estimate: every one of those arrays
    demonstrably exists and is simultaneously live during the evaluation. The
    upper bound is 2x, which admits per-step transients and allocator rounding
    while still rejecting a term that scales with an extra factor of N or
    k_beta.

    **THE ORACLE'S `k_beta` MUST BE THE ONE THE CHILD RUNS, AND IT WAS NOT
    UNTIL 2026-08-16.** `memory._CHILD` builds
    `SignalSpec([Constant, Trend, Annual, SemiAnnual])` -- **six** design
    columns -- while this test computed its floor at **four**, section 9.4's
    figure, which is the number every other fixture in this module uses. The
    two differ by 168 B/series (712 against 880 of engine workspace), so the
    floor is **6550** and not 6382, and the recorded ratio is **1.293** and not
    1.33. **An oracle at a different configuration from its instrument is (h):
    the test exercised a default rather than the thing it names**, and it
    survived because both numbers are plausible sizes for that axis.

    Measured on this machine after the streaming fix: **8471 B/series against
    the 6550 floor, a ratio of 1.293**, intercept ~77 MB. Before it, the floor
    was 31 542 -- the extra 25 200 being the materialized augmented block --
    and the measured slope was 43 392. **The measurement fell by 34 921
    B/series, more than the block itself**, because the per-step temporaries
    at peak scaled with it.

    THE 1.33 IS THE POINT AND IT IS WHY THIS TEST IS A SLOPE. The standing
    check asks whether the formula describes the code or a model of the code,
    and answers it against measured resident bytes, treating anything above
    ~1.5x as a term the formula is missing rather than as noise. 1.33 clears
    that; 43 392 against 8682 did not, and nothing in the suite said so until
    this measurement existed.

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
    # `k_beta=6`, because that is what `_CHILD`'s signal spec produces --
    # Constant, Trend, Annual and SemiAnnual are 1 + 1 + 2 + 2 columns. Section
    # 9.4's four is the wrong number for this instrument and was used here
    # until 2026-08-16.
    floor = data_and_workspace_bytes_per_series(d=STATE_DIM, k_beta=6, n_time=630)
    assert floor == 6550
    print(
        f"\nfloor {floor} B/series, measured {measured:.0f} B/series, "
        f"intercept {intercept / 1e6:.1f} MB"
    )
    assert floor <= measured <= 2.0 * floor

    # AND THE INSTRUMENT'S DISAGREEMENT WITH PRODUCTION IS STATED IN ADVANCE,
    # NOT RECONCILED (j2). This drives `unconstrained_loglik` on a batch of B,
    # which genuinely holds the engine's blocks per series; `run()` drives
    # `fit`, which hands the engine one series at a time. So this slope MUST
    # exceed the production per-series cost's engine content, and the amount is
    # the measurement of the deleted term's size rather than a second opinion.
    assert floor - 630 * 9 == 880
    assert measured > resident_bytes_per_series(**CASE) - output_slot_bytes(
        n_models=12, p_max=4, k_beta=4
    )


# --------------------------------------------------------------------------
# The floor -- what a process holds before a tile exists
# --------------------------------------------------------------------------


def _floor_input(tmp_path):
    """A small real zarr input for the floor probe to open.

    Args:
        tmp_path: pytest's temporary directory.

    Returns:
        The store URI, as a string.
    """
    import xarray as xr

    n_time, n_y, n_x = 24, 4, 4
    origin = np.datetime64("2000-01-01")
    time = np.array([origin + np.timedelta64(31 * i, "D") for i in range(n_time)])
    path = tmp_path / "floor-in.zarr"
    xr.Dataset(
        {"sla": (("time", "y", "x"), np.zeros((n_time, n_y, n_x), dtype="float32"))},
        coords={
            "time": time,
            "y": np.arange(n_y, dtype="float64"),
            "x": np.arange(n_x, dtype="float64"),
        },
    ).to_zarr(path, mode="w", consolidated=True)
    return str(path)


@pytest.mark.slow
@pytest.mark.machine
def test_the_floor_ladder_reproduces_the_recorded_rungs(tmp_path):
    """Each rung against its own absolute band, then the relations.

    **THE ABSOLUTES COME FIRST AND THAT IS THE POINT.** Every test the brief
    proposed for this was a relation -- `post > pre`, `with_input > without` --
    and a relation is satisfied by two absent readings, two zeros, and two
    mistakes in the same direction. That is (i3), and it is the shape that let
    `assert fit_moved == compat_moved` pass against a payload that dropped the
    field entirely.

    Expected values, MB, current RSS, measured 2026-08-14 and re-measured
    2026-08-15 by this probe:

        interpreter + numpy                     73.8 / 74.0
        + xarray, zarr                         162.4 / 163.0
        + metamer.batch.run                    170.7 / 171.2   pre-warm
        + numba imported, layer launched       213.9 / 214.4
        + Kalman kernel warm                   221.5 / 216.9   post-warm

    The bands below are +/-25% of the 2026-08-15 readings, wide enough to
    survive an interpreter or numpy release and far too narrow to admit a
    missing rung: the smallest step in the ladder is 8 MB and the largest is 89.

    **The warm rung is a LOWER BOUND and is asserted as one.** This probe warms
    with a one-series `white` fit at N=16 -- the smallest thing that drives
    `KalmanEngine.score` end to end -- while the 2026-08-14 ladder used a
    heavier spec. Tuning the warm until it reproduced 221.5 would have measured
    the tuning.

    Bug this catches: a floor taken at import time. It reads 171 against 217, so
    it understates by **27%** and the entire difference is charged to the tile --
    which is the unsafe direction, since the tile is what the budget then
    oversizes.
    """
    with rss_validity("the floor ladder's rungs"):
        report = measure_floor(data_uri=_floor_input(tmp_path), variable="sla")
        rungs = report.components
        expected = {
            "interpreter_numpy": 74.0e6,
            "xarray_zarr": 163.0e6,
            "metamer_batch_run": 171.2e6,
            "numba_threading_layer": 214.4e6,
            "kalman_kernel_warm": 216.9e6,
        }
        print("\n" + "\n".join(f"{k:28s} {v / 1e6:7.1f} MB" for k, v in rungs.items()))
        for name, value in expected.items():
            assert 0.75 * value <= rungs[name] <= 1.25 * value, name

        # ...and only now the relations, as additional checks rather than as the
        # evidence. The pre/post gap is what justifies measuring post-warm at all.
        assert report.post_warm_bytes > report.pre_warm_bytes
        assert report.post_warm_bytes - report.pre_warm_bytes > 30e6
        assert report.pre_warm_bytes == rungs["metamer_batch_run"]
        assert report.post_warm_bytes == rungs["kalman_kernel_warm"]
        # numba's threading layer is a fifth of the floor and is an ACCEPTED cost:
        # the layer-3 determinism precondition cannot be observed until it launches.
        assert rungs["numba_threading_layer"] - rungs["metamer_batch_run"] > 30e6


@pytest.mark.slow
@pytest.mark.machine
def test_the_floor_with_the_input_open_exceeds_the_floor_without_it(tmp_path):
    """A zarr store's residency belongs to the floor, not to the tile term.

    Expected value determined independently: an opened zarr store holds its
    handles, its consolidated metadata and a decompression buffer for the chunk
    that was read, and none of those scale with the tile. Measured 2026-08-15 on
    a 24x4x4 input: **11.3 MB**, from 216.9 to 228.2.

    The bound below is one-sided and loose (at least 1 MB) because the size is a
    property of the store rather than of this code, and a bigger input moves it.
    **What is being pinned is the sign**, and the sign is what decides which
    term the bytes are charged to.

    Bug this catches: measuring the floor before the open. Those bytes are then
    inside neither the floor nor the per-series formula, so they are effectively
    charged to the tile -- and `tile_side` comes out too large, which is the
    unsafe direction against a budget the design doc calls hard.
    """
    with rss_validity("the floor with the input open"):
        report = measure_floor(data_uri=_floor_input(tmp_path), variable="sla")

        assert report.with_input_bytes > report.post_warm_bytes
        assert report.with_input_bytes - report.post_warm_bytes > 1e6
        assert report.components["input_open"] == report.with_input_bytes
        # The peak is never below the largest current reading. `ru_maxrss` is
        # updated lazily -- measured here at 227.7 MB against a current 228.2 read
        # an instant earlier -- so a floor trusting the watermark alone would
        # subtract less than the process demonstrably held.
        assert report.peak_bytes >= max(report.components.values())
        assert report.peak_bytes >= report.with_input_bytes


@pytest.mark.slow
def test_the_floor_is_measured_fresh_every_call_and_never_cached(tmp_path):
    """Two calls both measure. Counting the probes is what makes it falsifiable.

    **"NOTHING WAS CACHED" IS A PURE NEGATIVE, AND THE OBVIOUS TEST FOR IT IS
    UNFALSIFIABLE HERE** -- **the floor has no cache of its own and deliberately
    never will**, so *"no cache entry appeared"* is satisfied by a caching
    mechanism that does not exist. Phase 2b Task 5's cache does not change that:
    it holds the calibration's SLOPE and nothing else, and looking in it for a
    floor entry would be looking in the wrong place. Counting child spawns is
    the form that can fail: **memoization is the mutation, and under it the
    second call spawns nothing.**

    Expected value determined independently: `measure_floor` runs exactly one
    child per call, so two calls run two.

    Bug this catches: an `lru_cache` added for speed. The floor's dependencies
    are the hardest thing here to key on -- the input's contribution depends on
    the chunk grid, which Task 11's (a1) sweep classified as read back from the
    store rather than hashed -- so a cache would need a gate the project
    deliberately does not have. **An uncached quantity has no staleness failure
    mode**, and this is what holds it uncached.
    """
    import subprocess

    uri = _floor_input(tmp_path)
    calls: list[object] = []
    real_run = subprocess.run

    def counting_run(*args, **kwargs):
        calls.append(args[0])
        return real_run(*args, **kwargs)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(subprocess, "run", counting_run)
        first = measure_floor(data_uri=uri, variable="sla")
        assert len(calls) == 1
        second = measure_floor(data_uri=uri, variable="sla")
        assert len(calls) == 2

    # Both calls returned a real ladder, so the count above is not satisfied by
    # two failures -- the (i2) positive half.
    for report in (first, second):
        assert report.post_warm_bytes > report.pre_warm_bytes > 0
        assert len(report.components) == 6


@pytest.mark.slow
def test_a_floor_probe_that_cannot_open_the_input_raises_rather_than_returning_zero(
    tmp_path,
):
    """The open happens inside the child, so its failure is the child's exit.

    Expected behaviour determined independently: `measure_floor` checks the
    child's return code and raises with its stderr attached, so a URI no opener
    can handle surfaces as an error naming the URI.

    Bug this catches: a bare `except` or an unchecked return code producing a
    floor of zero. **Zero is a plausible number**: it reads as "the process
    holds nothing", which makes the entire budget available to the tile and
    produces an oversized tile rather than an error.
    """
    with pytest.raises(RuntimeError, match="floor probe failed"):
        measure_floor(data_uri=str(tmp_path / "does-not-exist.zarr"), variable="sla")


# --------------------------------------------------------------------------
# The shapes the formula rests on: B = 1 through the optimizer, and through
# `run()`. These drive `core.fit` and `batch.run` from a test named for
# `core.memory` on purpose -- the claim being checked is the memory formula's,
# and it is a claim about what the driver does.
# --------------------------------------------------------------------------


class _ShapeRecorder:
    """An engine that records the leading dimension of everything it is given.

    Wraps a real engine rather than stubbing one: a stub that never computes
    cannot tell "the batch is 1" from "the engine was never reached", and the
    difference is the whole point of the assertion.

    Attributes:
        engine_id: Delegated, so `fit` files the scores as the real engine's.
        batches: One entry per `score` call, the leading dimension of each
            array argument.
    """

    def __init__(self, inner):
        self.inner = inner
        self.engine_id = inner.engine_id
        self.batches: list[tuple[int, ...]] = []

    def score(self, state_space, theta, y, mask, t, design, objective=None):
        """Record the batch shapes, then delegate.

        Args:
            state_space: Passed through.
            theta: Passed through.
            y: Passed through.
            mask: Passed through.
            t: Passed through.
            design: Passed through.
            objective: Passed through when supplied.

        Returns:
            Whatever the wrapped engine returns.
        """
        self.batches.append(
            (
                int(np.shape(theta)[0]),
                int(np.shape(y)[0]),
                int(np.shape(mask)[0]),
            )
        )
        if objective is None:
            return self.inner.score(state_space, theta, y, mask, t, design)
        return self.inner.score(state_space, theta, y, mask, t, design, objective)


def test_everything_the_optimizer_drives_has_a_leading_dimension_of_one():
    """A shape assertion standing in for a byte measurement, stated as such.

    At B = 50 the difference between "the solver state is a constant" and "it
    is per series" is 50 * 11 984 = 599 kB against a 221.5 MB process floor --
    0.27%, which no RSS instrument on this machine resolves. At any B where it
    IS resolvable the run is not affordable: `fit` costs ~5.4 s/series, so a
    B where the term reaches 1% of the floor is hours. **So the invariant is
    checked as a shape and labelled a shape**, rather than presented as a
    measurement it is not.

    Expected value determined independently from `fit.py:223`, which reads
    `optimize_series(obj, y[b:b+1], mask[b:b+1], t, one, warm, max_iter)`: the
    slices are one series wide, so every array reaching an engine through the
    optimizer has leading dimension 1 whatever B is.

    Bug this catches: someone batching the optimizer -- which is exactly what
    design doc section 8.3 originally specified and what Task 19 deleted. That
    change makes the solver state a per-series term again, and this module's
    entire correction wrong, and **nothing else in the suite would notice**,
    because the results would be identical.
    """
    from metamer.core.criteria import Criterion
    from metamer.core.engines.kalman import KalmanEngine
    from metamer.core.fit import fit
    from metamer.core.registry import kernel_registry
    from metamer.core.signal import Constant, SignalSpec, Trend
    from metamer.core.terms import ProcessSpec, TermSpec

    def _spec(*kinds):
        return ProcessSpec(
            tuple(
                TermSpec(
                    kind,
                    kernel_registry[kind]().param_specs(),
                    getattr(kernel_registry[kind](), "ordering_param", None),
                )
                for kind in kinds
            )
        )

    n_time = 60
    t = np.arange(n_time, dtype=np.float64) / 12.0
    y = np.random.default_rng(0).standard_normal((4, n_time))
    recorder = _ShapeRecorder(KalmanEngine())
    fit(
        y,
        t,
        SignalSpec([Constant(), Trend()]),
        [_spec("white"), _spec("white", "matern12")],
        Criterion.AIC,
        engine=recorder,
        max_iter=2,
    )

    # THE POSITIVE HALF FIRST: the engine really did run. An empty list
    # satisfies every "leading dimension is 1" assertion for free (i2).
    assert recorder.batches
    assert set(recorder.batches) == {(1, 1, 1)}


@pytest.mark.slow
def test_the_batched_placement_is_not_reachable_through_run(tmp_path):
    """`run()` fits one series at a time, so `PER_THREAD` has no producer.

    Driven through `run()` rather than through `fit` because the claim is about
    the production entry point: `CompiledEngine` realizes path B's shape at
    whatever B `score` is given, and what decides that is the driver above it,
    not the engine.

    Expected value determined independently from `fit.py:223` -- see the test
    above -- and the grid here is 2 x 3, so a per-series claim and a per-tile
    claim give 6 and 1 and are distinguishable.

    Bug this catches: a driver change making the batched placement reachable
    without the memory formula, the floor, or the calibration key following.
    **An unreachable branch with no reachability assertion becomes reachable
    silently**, and this one carries a 64x thread multiplier on a term the
    budget arithmetic treats as a constant.

    ITS (i2) POSITIVE CONTROLS ARE TWO, AND BOTH ARE ELSEWHERE IN THIS MODULE:
    `test_the_thread_term_is_the_only_thread_dependence` computes the
    unreachable branch directly against hand-derived numbers, so "not reached"
    is not satisfied by a branch that cannot work; and the assertion above that
    the engine ran at all.
    """
    import xarray as xr

    from metamer.batch.run import run
    from metamer.core.engines.kalman import KalmanEngine

    n_time, n_y, n_x = 24, 2, 3
    origin = np.datetime64("2000-01-01")
    time = np.array([origin + np.timedelta64(31 * i, "D") for i in range(n_time)])
    values = np.random.default_rng(1).standard_normal((n_time, n_y, n_x))
    source = tmp_path / "in.zarr"
    xr.Dataset(
        {"sla": (("time", "y", "x"), values.astype("float32"))},
        coords={
            "time": time,
            "y": np.arange(n_y, dtype="float64"),
            "x": np.arange(n_x, dtype="float64"),
        },
    ).to_zarr(source, mode="w", consolidated=True)

    config = tmp_path / "c.toml"
    config.write_text(
        f'data_uri = "{source}"\n'
        'variable = "sla"\n'
        'signal_terms = ["constant", "trend"]\n'
        'candidates = ["white", "white + matern12"]\n'
        'criteria = ["aic"]\n'
    )

    recorder = _ShapeRecorder(KalmanEngine())
    run(config, tmp_path / "out.zarr", engine=recorder)

    assert recorder.batches
    assert set(recorder.batches) == {(1, 1, 1)}
    # The grid holds six series, so "one per tile" and "one per series" are
    # different numbers here and the fixture can tell them apart.
    assert n_y * n_x == 6
    assert max(batch for batch, _, _ in recorder.batches) == 1


# --------------------------------------------------------------------------
# The linearity report: what a ladder establishes, and what it cannot see
# --------------------------------------------------------------------------

#: The ladder Phase 2b Task 7 ran by hand: sides (16, 48, 80, 112) on a base-16
#: grid, so `B = side**2`. **A 49x lever arm in B**, which is what separates the
#: slope from the intercept -- a ladder whose top is a small multiple of its
#: bottom fits the intercept and reports the residue as a slope.
_LADDER_BATCHES = (256, 2304, 6400, 12544)

#: The analytic per-series cost at that ladder's fixture -- N = 60, M = 2,
#: k_beta = 4, p_max = 3 -- hand-derived as `60*9 + 2*(24*3 + 16*4 + 57)`
#: = `540 + 386`. It is the figure `resident_bytes_per_series` returns and is
#: written out here so the tests below do not take their oracle from the
#: function under comparison.
_LADDER_ANALYTIC = 926


def _ladder(
    peaks: tuple[float, ...], batches: tuple[int, ...] = _LADDER_BATCHES
) -> CalibrationResult:
    """A `CalibrationResult` carrying chosen peaks, for the analysis to read."""
    points = tuple(
        CalibrationPoint(
            side=int(batch**0.5),
            derived_side=int(batch**0.5),
            batch=batch,
            peak_bytes=peak,
            baseline_bytes=228_200_000.0,
            ok=0,
            attempted=batch * 2,
        )
        for batch, peak in zip(batches, peaks, strict=True)
    )
    return CalibrationResult(
        slope_bytes_per_series=0.0,
        intercept_bytes=0.0,
        residuals=(),
        points=points,
        max_iter=1,
        linearity_basis="constructed for tests/test_memory.py",
        placement=SolverPlacement.PER_SERIES_LIVE,
        engine_label=MemoryEngineLabel.KALMAN_NUMPY,
        floor_peak_bytes=228_200_000,
    )


def _straight(
    slope: float, intercept: float = 2.28e8, scatter: float = 0.0
) -> tuple[float, ...]:
    """Peaks on a line, with an alternating residual of `scatter`."""
    signs = (1.0, -1.0, 1.0, -1.0)
    return tuple(
        intercept + slope * batch + scatter * sign
        for batch, sign in zip(_LADDER_BATCHES, signs, strict=True)
    )


def test_a_noiseless_ladder_resolves_its_slope_and_excludes_every_curvature():
    """The positive control: exact data gives an exact slope and no curvature.

    Expected values determined independently -- the peaks are constructed from
    `228 MB + 926 B x B`, so the slope is 926 by construction, every residual is
    zero, and a zero residual means the ladder could have excluded a curvature
    of zero. **That last consequence is the one worth pinning**: the detectable
    curvature falls out of the scatter, so a noiseless instrument sees
    everything and a noisy one sees nothing, and the report must say which it
    was rather than reporting the residuals alone.

    Bug this catches: a detectable-curvature figure that is a constant, or one
    computed from the ladder's spacing alone. Either would report the same
    sensitivity for a clean ladder and a hopeless one, which is exactly the
    claim (i2) says an absence cannot support -- "no curvature was seen" is
    satisfied by an instrument that cannot see any.
    """
    report = linearity_report(
        _ladder(_straight(_LADDER_ANALYTIC)),
        analytic_bytes_per_series=_LADDER_ANALYTIC,
    )

    assert report.slope_standard_error < 1.0
    assert report.relative_standard_error < 1e-3
    assert report.resolved
    assert report.ratio == pytest.approx(1.0, abs=1e-6)
    assert report.inside_band
    assert report.curvature == pytest.approx(0.0, abs=1e-9)
    assert report.detectable_curvature == pytest.approx(0.0, abs=1e-9)
    assert report.detectable_variation == pytest.approx(0.0, abs=1e-9)
    assert "Curvature" in report.verdict


def test_a_curved_ladder_reports_the_curvature_with_its_sign():
    """A quadratic term is recovered, and its sign is part of the answer.

    Expected value determined independently: the peaks are built as
    `228 MB + 926 B x B - 0.01 x B**2`, and four points determine a quadratic
    exactly, so the fitted coefficient must be **-0.01** to float precision.

    **The SIGN is asserted because the two directions are different defects.**
    A per-series cost that falls with B is an allocator or a buffer being
    amortized; one that rises is a term the formula does not charge, and at
    production B it is the one that exceeds the budget. A report carrying only
    a magnitude cannot tell a consumer which of those it is looking at.

    Bug this catches: a quadratic term dropped, halved, or recovered with the
    wrong sign -- the fit reporting the line's residual pattern rather than a
    coefficient.

    **AND THE BUG IT DOES *NOT* CATCH IS RECORDED HERE, BECAUSE THE MUTATION
    WAS RUN.** This test was written believing it pinned the **centring** of
    the design matrix. It does not: removing the centring leaves it green, and
    measurement says why -- centred and raw fits recover a known `-1e-4`
    coefficient identically at this ladder, at production-scale B, and at a
    ladder four times wider. **The mutation is not a defect on any reachable
    input**, which is the fifth cause in the taxonomy and the one that says
    nothing about the test. The claim was removed from
    `memory.linearity_report`'s docstring rather than left as an untested
    justification.
    """
    curved = tuple(
        peak - 0.01 * batch**2
        for peak, batch in zip(
            _straight(_LADDER_ANALYTIC), _LADDER_BATCHES, strict=True
        )
    )

    report = linearity_report(
        _ladder(curved), analytic_bytes_per_series=_LADDER_ANALYTIC
    )

    assert report.curvature == pytest.approx(-0.01, rel=1e-9)
    # The straight-line fit through curved data has residuals, so its own
    # standard error is inflated -- the line is the wrong model and says so.
    assert report.slope_standard_error > 0.0


def test_a_ladder_dominated_by_scatter_is_published_as_a_bound():
    """A number whose standard error swamps the effect is not a measurement.

    **THIS IS THE FAILURE THIS PROJECT HAS ALREADY MADE ONCE.** Task 4's first
    affordable ladder returned 1666 B/series against an analytic 926 and was
    read as a 1.80x finding; the scatter was +-0.3 MB against 0.43 MB of
    signal, and the correct reading was noise.

    Expected values computed by hand from the construction: peaks are
    `228 MB + 926 B x B` with an alternating +-1 MB residual, which gives a
    fitted slope of **833.0** and a standard error of **135.6** -- a relative
    error of **16.3%**, above the 10% limit. The ladder's 2-sigma exclusion is
    therefore 833 +- 271, i.e. **562 to 1104 B/series**, and the analytic 926
    sits inside it: this ladder **cannot** distinguish the formula from a value
    20% away from it.

    Bug this catches: `resolved` keyed on distance from zero rather than on
    relative error. 833 +- 136 is six standard errors from zero and still
    useless, which is precisely how a noise-dominated ladder gets published as
    a value.
    """
    report = linearity_report(
        _ladder(_straight(_LADDER_ANALYTIC, scatter=1e6)),
        analytic_bytes_per_series=_LADDER_ANALYTIC,
    )

    assert report.slope_standard_error == pytest.approx(135.578, rel=1e-4)
    assert report.relative_standard_error == pytest.approx(0.16276, rel=1e-4)
    assert not report.resolved
    assert "NOT RESOLVED" in report.verdict
    assert "562" in report.verdict and "1104" in report.verdict
    assert "establishes no value" in report.verdict


def test_the_detectable_curvature_is_set_by_the_scatter_and_not_by_the_ladder():
    """Ten times the scatter, ten times the curvature the ladder cannot see.

    Expected values computed by hand from the same construction as above: at
    +-1 MB of scatter the curvature's standard error is **0.0551804** and at
    +-0.1 MB it is **0.00551804**, so the detectable curvature is 0.110361 and
    0.0110361. **Each is asserted absolutely before the relation between them**
    -- a ratio passes when both sides are zero, both absent, or both wrong in
    the same direction (i3), and this is the assertion that would otherwise be
    written as `noisy > clean` and pass against a constant.

    Bug this catches: a detectable curvature derived from the ladder's spacing
    alone. The spacing is identical in both cases here, so such a figure would
    be equal in both -- and it would report the same sensitivity for a ladder
    that saw nothing and one that saw everything.
    """
    noisy = linearity_report(
        _ladder(_straight(_LADDER_ANALYTIC, scatter=1e6)),
        analytic_bytes_per_series=_LADDER_ANALYTIC,
    )
    cleaner = linearity_report(
        _ladder(_straight(_LADDER_ANALYTIC, scatter=1e5)),
        analytic_bytes_per_series=_LADDER_ANALYTIC,
    )

    assert noisy.curvature_standard_error == pytest.approx(0.0551804, rel=1e-4)
    assert cleaner.curvature_standard_error == pytest.approx(0.00551804, rel=1e-4)
    assert noisy.detectable_curvature == pytest.approx(0.110361, rel=1e-4)
    assert cleaner.detectable_curvature == pytest.approx(0.0110361, rel=1e-4)
    assert noisy.detectable_curvature == pytest.approx(
        10 * cleaner.detectable_curvature, rel=1e-6
    )
    # And the fraction it corresponds to, which is what a reader quotes: the
    # per-series cost may vary by this much across the ladder unnoticed.
    assert noisy.detectable_variation == pytest.approx(1.628, rel=1e-3)
    assert cleaner.detectable_variation == pytest.approx(0.147934, rel=1e-3)


def test_the_band_is_two_sided_so_a_slope_below_the_formula_is_a_finding():
    """A measured cost materially below the formula is not headroom.

    Expected values derived by hand from `SLOPE_BAND_FACTOR = 1.5` against 926:
    the band is 617.3 to 1389.0, so 926 is inside, 1500 is outside above and
    600 is outside below.

    Bug this catches: a one-sided check. A slope below the formula means the
    formula charges for something the code does not hold, and the excess
    capacity then hides whatever else is wrong -- which is how two errors of
    opposite sign put F2 and F3's total within 0.5% of a measurement while
    neither term was right.
    """
    for slope, inside in ((926.0, True), (1500.0, False), (600.0, False)):
        report = linearity_report(
            _ladder(_straight(slope)), analytic_bytes_per_series=_LADDER_ANALYTIC
        )
        assert report.inside_band is inside, f"{slope} B/series"
        assert report.ratio == pytest.approx(slope / _LADDER_ANALYTIC, rel=1e-6)


def test_a_three_point_ladder_cannot_report_a_curvature_at_all():
    """Refused, because a quadratic through three points has no residual.

    Expected value determined independently: three points determine three
    coefficients exactly, so the residual is zero whatever the truth is and the
    standard error is 0/0. A report built from it would say the ladder excluded
    **every** curvature -- a confident answer, which is worse than a refusal.

    Bug this catches: the guard being absent, or being written as "at least
    two" by analogy with the slope. Two points fit a line and three fit a
    parabola; the number that matters here is the residual degrees of freedom,
    and it is zero at three.
    """
    with pytest.raises(ValueError, match="at least four"):
        linearity_report(
            _ladder(_straight(926.0)[:3], batches=_LADDER_BATCHES[:3]),
            analytic_bytes_per_series=_LADDER_ANALYTIC,
        )


def test_the_analysis_reproduces_task_fours_hand_computed_ladder():
    """The same numbers through a function reach where a hand computation did.

    **THIS IS THE ONE PLACE THE ARITHMETIC MEETS AN INDEPENDENT DERIVATION**
    (j). Phase 2b Task 4's ladder was fitted by hand and published in
    `PROGRESS.md` as **1049 +- 222 B/series**; the peaks it was fitted from are
    published beside it, to 0.01 MB. Feeding those printed peaks back through
    this function must land in the same place, or one of the two is wrong.

    Expected values, and the tolerance derived rather than chosen: from the
    published table this returns **1050.75 +- 223.6**. That is not identical to
    the recorded pair because the table is rounded to 0.01 MB, and a +-5 kB
    perturbation of each peak moves the slope by at most
    `sum|B - Bbar| * 5000 / Sxx` = `4624 * 5000 / 8.454e6` = **2.7 B/series**.
    1050.75 is 1.75 away from 1049, inside that.

    **AND THE RESOLUTION VERDICT IS THE POINT OF USING THIS LADDER HERE**: at
    21.3% relative error it is **not resolved**, which is exactly how
    `PROGRESS.md` reads it -- the value claim lives there with its uncertainty
    and never in an assertion.

    Bug this catches: a standard error computed with the wrong divisor. `n`,
    `n-1` and `n-2` give 158, 182 and 224 here, all plausible, and only one is
    the standard error of a slope fitted with two parameters.
    """
    peaks = (227.86e6, 227.73e6, 230.29e6, 231.46e6)
    report = linearity_report(
        _ladder(peaks, batches=(256, 1024, 2304, 4096)),
        analytic_bytes_per_series=926,
    )

    assert report.slope_standard_error == pytest.approx(223.6, rel=1e-3)
    assert abs(report.ratio * 926 - 1049) < 2.7
    assert report.relative_standard_error == pytest.approx(0.213, rel=1e-2)
    assert not report.resolved
    assert report.inside_band


def test_the_report_restates_no_measurement_the_result_already_carries():
    """One home per measurement, enforced by a test rather than by a docstring.

    The slope, the intercept, the residuals and the ladder live on
    `CalibrationResult`. **Two copies of a measurement drift the moment one is
    updated**, and this project has paid for that four times -- the published
    tile side, F3's magnitude, the sweep timing, and
    `data_and_workspace_bytes_per_series`'s own docstring, which still
    published a floor at `k_beta = 4` for an instrument running 6.

    Bug this catches: a later reader adding `slope_bytes_per_series` to the
    report "for convenience", after which a result and its report can disagree
    about what was measured and nothing compares them.
    """
    fields = {field.name for field in dataclasses.fields(LinearityReport)}

    assert "slope_bytes_per_series" not in fields
    assert "intercept_bytes" not in fields
    assert "residuals" not in fields
    assert "points" not in fields
    # What it does carry is derived, and every one of them is absent from
    # `CalibrationResult` -- so the two types partition the answer.
    result_fields = {field.name for field in dataclasses.fields(CalibrationResult)}
    assert not (fields & result_fields)


# --------------------------------------------------------------------------
# The calibration: a capped run of the production path
# --------------------------------------------------------------------------


def _calibration_input(directory: Path, *, n_time: int = 24, side: int = 8) -> str:
    """A real zarr input wide enough for the ladder's largest full tile.

    White noise rather than zeros: a record of exact zeros drives sigma to its
    lower diagnostic limit and every fit comes back `DIAGNOSTIC_LIMIT`, which is
    a different allocation path from the `ITER_CAP_*` one a capped run is
    supposed to exercise.
    """
    import xarray as xr

    rng = np.random.default_rng(0)
    dataset = xr.Dataset(
        {
            "sla": (
                ("time", "y", "x"),
                rng.standard_normal((n_time, side, side)).astype("float32"),
            )
        },
        coords={
            "time": np.array(
                [
                    np.datetime64("2000-01-01") + np.timedelta64(31 * i, "D")
                    for i in range(n_time)
                ]
            ),
            "y": np.arange(side),
            "x": np.arange(side),
        },
    )
    path = directory / "in.zarr"
    dataset.to_zarr(path)
    return str(path)


def _calibration_config(directory: Path, uri: str) -> str:
    path = directory / "calibration.toml"
    path.write_text(
        f'data_uri = "{uri}"\n'
        'variable = "sla"\n'
        'signal_terms = ["constant", "trend", "annual"]\n'
        'candidates = ["white", "white + matern12"]\n'
        'criteria = ["aic"]\n'
    )
    return str(path)


#: The floor every calibration test pins. **Pinned rather than measured**, and
#: the value is this machine's 2026-08-15 reading so a reader recognizes it: the
#: derived side is a function of the floor, and a floor that moved by megabytes
#: between ladder points would put each point on a different side than the one it
#: asked for -- the fixture failure Task 2 found and that cost four modules their
#: budgets.
_PINNED_FLOOR = FloorReport(
    pre_warm_bytes=171_200_000,
    post_warm_bytes=216_900_000,
    with_input_bytes=228_200_000,
    peak_bytes=228_200_000,
    components={"pinned": 228_200_000},
)


@pytest.fixture(scope="module")
def small_calibration(tmp_path_factory: pytest.TempPathFactory) -> CalibrationResult:
    """One two-point calibration, shared by the structural tests below.

    Module-scoped because each point is a fresh child that imports numba and
    fits a tile, and the tests that read it are about the ladder's STRUCTURE --
    which sides it landed on, what it recorded about itself -- rather than about
    any number in it.
    """
    directory = tmp_path_factory.mktemp("calibration")
    uri = _calibration_input(directory)
    return calibrate(
        config_path=_calibration_config(directory, uri),
        floor=_PINNED_FLOOR,
        ladder=(4, 8),
        max_iter=1,
    )


@pytest.mark.slow
@pytest.mark.machine
def test_the_calibration_lands_on_the_sides_it_asked_for(small_calibration):
    """The ladder is in SIDES, and the run derives the side it was aimed at.

    **THIS IS THE EXECUTABLE FORM OF "IT DRIVES THE PRODUCTION PATH" (j2).** The
    calibration does not choose its own B: it asks
    `tiling.budget_bytes_for_side` which budget lands on a side, hands that
    budget to `run()`, and reads back the side `run()` actually derived. If the
    two disagree, the calibration measured a tile the production path would not
    have built.

    Expected values determined independently: `B = side**2` for a tile that is
    not clipped, and the fixture's grid is 8x8, so sides 4 and 8 give batches of
    16 and 64. Below `store.TILE_SIDE_BASE` the base is inert and every side is
    reachable, which is why a suite-affordable ladder can exist at all.

    **THE `ok` COUNT IS THE REGIME CONTROL, AND IT IS ASSERTED AS A MINORITY
    RATHER THAN AS ZERO.** A cap does not forbid convergence:
    `optimize.py:592` classifies a fit as capped when `n_iter >= max_iter`, so a
    series that converges in **fewer** iterations than the cap is genuinely
    `OK` -- at a cap of 1 that means stopping at `n_iter = 0`, with the moment
    initialization already inside the gradient tolerance. Measured through
    `run()` on these fixtures: **0 of 128 at caps 1 and 2, and 15 of 128 at cap
    3**, so the count is a property of the cap and the data rather than
    something a cap of 1 guarantees. What matters for comparability is that the
    capped regime is *predominantly* non-OK.

    Bug this catches: an inverse that lands one side low or high -- silent,
    because the ladder still runs and every point sits at a B nobody asked for,
    and the slope then describes tiles that were never built.
    """
    assert [point.side for point in small_calibration.points] == [4, 8]
    assert [point.derived_side for point in small_calibration.points] == [4, 8]
    assert [point.batch for point in small_calibration.points] == [16, 64]
    assert [point.attempted for point in small_calibration.points] == [32, 128]
    assert small_calibration.max_iter == 1
    for point in small_calibration.points:
        assert point.ok * 2 < point.attempted


@pytest.mark.slow
@pytest.mark.machine
def test_the_calibration_records_what_its_slope_is_licensed_for(small_calibration):
    """The result states the range it was measured over and what it is not.

    **A NUMBER WITHOUT ITS PRECONDITIONS IS NOT A MEASUREMENT**, and this
    project has paid for that four times -- a `tile_side` without its backend, a
    divisor ratio without its array, a floor without its instrument. A slope
    measured at four small sides and cached forever is the next instance
    waiting, so the result carries the sides it saw, the cap it ran under, and
    the statement that linearity **beyond** them is Task 7's claim rather than
    this one's.

    **AND THE INTERCEPT IS NOT THE PRODUCTION FLOOR**, which is the half a
    reader will get wrong: it carries what the measuring child holds and a
    production run does not, minus the four allocation sites a capped fit never
    reaches. That is stated in `CalibrationResult`'s own docstring and the
    pinned floor is recorded beside the intercept so the two are comparable.

    Bug this catches: a cache entry claiming more than the measurement supports
    -- the discipline every stale number in this project has lacked.
    """
    basis = small_calibration.linearity_basis
    assert "max_iter=1" in basis
    assert "(4, 8)" in basis
    assert "(16, 64)" in basis
    assert "Task 7" in basis
    # **THE FIT IS OVER THE ACHIEVED BATCH, AND THIS IS WHAT SAYS SO.** Slope,
    # intercept and residuals are one fit or they are three numbers; asserting
    # that they reproduce each measured peak from its own `batch` catches a fit
    # taken against the requested SIDE instead -- which differs by a square, is
    # silent, and would make every cached bytes-per-series figure a
    # bytes-per-side one.
    for point, residual in zip(
        small_calibration.points, small_calibration.residuals, strict=True
    ):
        predicted = (
            small_calibration.slope_bytes_per_series * point.batch
            + small_calibration.intercept_bytes
        )
        assert predicted + residual == pytest.approx(point.peak_bytes, rel=1e-9)
    assert small_calibration.floor_peak_bytes == _PINNED_FLOOR.peak_bytes
    assert small_calibration.placement is SolverPlacement.PER_SERIES_LIVE
    assert small_calibration.engine_label is MemoryEngineLabel.KALMAN_NUMPY
    assert len(small_calibration.residuals) == len(small_calibration.points)


def test_a_ladder_of_one_point_is_refused():
    """Two points make a line; one makes an assumption.

    Bug this catches: a single-point ladder returning a slope of whatever
    `polyfit` does with one observation -- a number with no relation in it at
    all, which would then be cached and reused as though it had been measured.
    """
    with pytest.raises(ValueError, match="at least two ladder points"):
        calibrate(config_path="unused.toml", floor=_PINNED_FLOOR, ladder=(16,))


@pytest.mark.slow
@pytest.mark.machine
def test_peak_residency_does_not_move_with_the_iteration_cap(tmp_path):
    """The step test: caps {1, 2, 3} at one B, and what it can and cannot see.

    **A STEP TEST AND NOT A SLOPE TEST, AND THE DIFFERENCE IS THE WHOLE POINT.**
    A three-point fit through caps {1, 5, 32} would read the likelier defect --
    an allocation on a path a cap of 1 never reaches -- as a small positive
    slope, which the eye calls noise. A **step at 1 -> 2 that is flat at
    2 -> 3** is a signature instead.

    **WHAT THIS RESOLVES, STATED RATHER THAN IMPLIED.** At B = 64 a per-series
    allocation is kilobytes and is invisible here; what the band catches is a
    **constant**-scale allocation -- an optimizer workspace, a JIT compile, an
    import triggered on a converging path -- which is what a first-iteration
    allocation in this system actually looks like. A per-series first-iteration
    allocation would show at the shipped ladder's top point, where 926 B/series
    over 4096 series is 3.8 MB. The band below is 16 MB, against a spread of
    ~0.3 MB measured between fresh children at fixed workload on 2026-08-15.

    **THE OUTCOME MIX IS NOT CONSTANT ACROSS {1, 2, 3}, WHICH THE BRIEF ASSUMED
    IT WOULD BE, AND THE MEASUREMENT IS BETTER FOR IT.** Measured 2026-08-15
    through `run()` at side 8, N = 60: **cap 1 and cap 2 give 0 `OK` of 128 and
    cap 3 gives 15** -- convergence begins at 3, because an `OK` needs
    `n_iter < max_iter` and a fit converging in two iterations reaches it. So at
    cap 3 fifteen series **do** reach the four allocation sites `fit` skips on a
    non-OK outcome, and the peak does not move: 227.7, 227.8, 227.7 MB. That is
    direct evidence for the claim the plan made by code-reading -- those sites
    are shape `(1, ...)` constants rather than slope terms -- rather than an
    assumption the fixture was arranged to protect.

    Bug this catches, and it is the one that would make every calibrated slope
    too small: an allocation reached only after the first iteration, which a
    cap-1 calibration never pays for and a production run always does. **If this
    fails, the instrument is dead and must say so** rather than be patched with
    a higher cap.
    """
    with rss_validity("peak residency across the iteration cap"):
        uri = _calibration_input(tmp_path, n_time=60, side=8)
        config_path = _calibration_config(tmp_path, uri)
        peaks = {}
        for cap in (1, 2, 3):
            point = measure_tile_peak(
                config_path=config_path, side=8, floor=_PINNED_FLOOR, max_iter=cap
            )
            # NOT `ok == 0`: a fit whose moment init already meets the gradient
            # tolerance stops at `n_iter = 0`, which is below the cap and therefore
            # genuinely converged. What makes the three caps comparable is that the
            # regime is predominantly capped at all of them, and that is asserted.
            assert point.ok * 2 < point.attempted
            assert point.batch == 64
            peaks[cap] = (point.peak_bytes, point.ok)
        print(
            "\nstep test, (cap, peak MB, ok): "
            f"{[(cap, round(peak / 1e6, 1), ok) for cap, (peak, ok) in peaks.items()]}"
        )

        assert abs(peaks[2][0] - peaks[1][0]) < 16e6
        assert abs(peaks[3][0] - peaks[2][0]) < 16e6


@pytest.mark.slow
@pytest.mark.machine
def test_a_converging_cap_reaches_a_regime_a_capped_one_does_not(tmp_path):
    """Cap 32 is a different question from caps {1, 2, 3}, and confounds two.

    **THE HIGH POINT IS NOT A CLEAN ACCUMULATION CHECK AND SAYING SO IS THE
    FINDING.** Measured 2026-08-15: at cap 32, 83 of 128 fits come back `OK`
    where at caps 1 and 2 none do. So the difference between cap 32 and cap 1 is
    accumulation **plus** the four allocation sites `fit.py` skips on a non-OK
    outcome -- one measurement over two unknowns.

    The separation is arithmetic rather than a second cap: every skipped site is
    shape `(1, ...)` inside the per-series loop, so the converged path is a
    **constant** and accumulation would scale with B. This test establishes the
    regime change -- the control that says which unknowns are in play -- and the
    magnitudes belong to Task 7, whose ladder can resolve them.

    Expected value determined independently: `mean_iterations` is 32.5 (P3), and
    a **mean is not a maximum**, so a cap at the mean leaves a substantial
    fraction unconverged. Both counts are asserted, in both directions.

    **AND THE CAPPED SIDE IS NOT ASSERTED TO BE ZERO**, because a cap of 1 does
    not forbid convergence: a fit that stops at `n_iter = 0` never reaches the
    cap. The claim is the *change* -- more fits converge at 32 than at 1, and
    not all of them do at either.

    Bug this catches: reading the cap-32 point as accumulation, which would
    attribute a per-series constant to a slope and inflate every cached
    bytes-per-series figure derived from it.
    """
    uri = _calibration_input(tmp_path, n_time=60, side=4)
    config_path = _calibration_config(tmp_path, uri)
    capped = measure_tile_peak(
        config_path=config_path, side=4, floor=_PINNED_FLOOR, max_iter=1
    )
    converging = measure_tile_peak(
        config_path=config_path, side=4, floor=_PINNED_FLOOR, max_iter=32
    )

    assert converging.ok > capped.ok
    assert converging.ok > 0
    assert converging.ok < converging.attempted
    assert capped.attempted == converging.attempted == 32
    print(
        f"\nregime: capped ok={capped.ok} peak={capped.peak_bytes / 1e6:.1f} MB, "
        f"converging ok={converging.ok} peak={converging.peak_bytes / 1e6:.1f} MB"
    )


def test_the_validity_gate_fires_and_records_why(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The positive control: an indeterminate measurement is reachable and loud.

    **"0 INDETERMINATE" IS A PURE NEGATIVE** (i2), and every sweep so far has
    printed it. Without this, that line is satisfied equally by a quiet machine
    and by a gate that cannot fire at all -- and the second is indistinguishable
    from the first in the summary.

    Expected values derived by hand: the stubbed counter advances by 10 s of
    stall across a window of at most a few milliseconds, which is a rate far
    above the 50 ms/s limit however long the block takes.

    Bug this catches: a gate wired to a counter that never moves, or a
    comparison whose sense is inverted -- both leave every run reporting zero
    indeterminate measurements, which reads as evidence the machine was quiet.
    """
    from metamer.core import machine as machine_module

    readings = iter([(0, "cgroup"), (10_000_000, "cgroup")])
    monkeypatch.setattr(machine_module, "memory_stall_us", lambda: next(readings))
    before = len(conftest.INDETERMINATE_RSS)

    with pytest.raises(Skipped) as skipped:
        with rss_validity("a constructed stall"):
            pass

    assert "a constructed stall" in str(skipped.value)
    assert "ms/s of full memory stall" in str(skipped.value)
    # AND IT IS RECORDED, NOT ONLY RAISED: the summary is what makes an
    # indeterminate outcome visible rather than a skip nobody reads.
    assert len(conftest.INDETERMINATE_RSS) == before + 1
    assert "a constructed stall" in conftest.INDETERMINATE_RSS[-1]
    conftest.INDETERMINATE_RSS.pop()


# --------------------------------------------------------------------------
# The accumulation report: what a tile loop's peaks exclude, and what they do not
# --------------------------------------------------------------------------


def _peaks(
    growth: float, tiles: int = 4, intercept: float = 2.31e8, scatter: float = 0.0
) -> tuple[float, ...]:
    """Per-tile peaks on a line, with a residual pattern that fits a flat line.

    The signs are `(+, -, -, +)` and not `(+, -, +, -)` deliberately: an
    alternating pattern over an EVEN number of points correlates with the index
    and shifts the fitted slope, so a fixture meant to be flat would arrive
    tilted. This pattern is orthogonal to the index, so the slope it produces is
    exactly `growth`.

    Args:
        growth: Bytes per tile.
        tiles: How many tiles.
        intercept: Peak at tile zero.
        scatter: Residual magnitude.

    Returns:
        One peak per tile.
    """
    signs = [1.0, -1.0, -1.0, 1.0]
    return tuple(
        intercept + growth * index + scatter * signs[index % 4]
        for index in range(tiles)
    )


def test_a_flat_run_reports_no_growth_and_the_leak_it_could_have_excluded():
    """Zero growth is not the answer on its own; the sensitivity is.

    Expected values derived by hand from the four peaks, not from the code.
    Indices 0-7 have mean 3.5, so `Sxx = 2*(3.5^2 + 2.5^2 + 1.5^2 + 0.5^2) =
    42`. The residual pattern `(+1, -1, -1, +1)` repeated twice is orthogonal
    to the index, so `Sxy = 0` and the slope is exactly 0. The residuals are
    then the pattern itself: `SSR = 8e10`, `s^2 = SSR / (8 - 2)`, and
    `SE = sqrt(8e10 / (6 * 42)) = 17 817.42` B/tile. Twice that is **35 634.83**
    B/tile, and across the run's seven-tile span it is **249 443.8 B**.

    Bug this catches: a detectable-leak figure computed from the tile count or
    from the peaks' spread instead of from the fit's own residuals. A four-tile
    run and a four-hundred-tile run would then advertise the same sensitivity,
    and the accumulation claim would be strongest exactly where it rests on
    least evidence.
    """
    report = accumulation_report(_peaks(0.0, tiles=8, scatter=1e5))

    assert report.growth_bytes_per_tile == pytest.approx(0.0, abs=1e-6)
    assert report.standard_error == pytest.approx(17_817.416, rel=1e-6)
    assert report.detectable_growth == pytest.approx(35_634.832, rel=1e-6)
    assert report.excluded_total_bytes == pytest.approx(249_443.82, rel=1e-6)
    assert report.consistent_with_zero is True
    # The bound is two-sided and centred on the fit, which is what makes it an
    # exclusion rather than a one-sided reassurance.
    assert report.lower_bound_bytes_per_tile == pytest.approx(-35_634.832, rel=1e-6)
    assert report.upper_bound_bytes_per_tile == pytest.approx(35_634.832, rel=1e-6)
    # The second half is four points with Sxx = 5 and the same +-1e5 residual,
    # so `SE = sqrt(4e10 / (2 * 5)) = 63 245.55` -- a flat run is not saturating
    # because there is nothing for the steady state to fall short of.
    assert report.tail_tiles == 4
    assert report.tail_growth_bytes_per_tile == pytest.approx(0.0, abs=1e-6)
    assert report.tail_standard_error == pytest.approx(63_245.553, rel=1e-6)
    assert report.tail_consistent_with_zero is True
    assert report.saturating is False


def test_a_leaking_run_reports_the_leak_and_clears_its_own_noise():
    """A leak larger than the scatter is reported as a leak, with its sign.

    Expected values derived by hand over eight tiles. The `(+, -, -, +)`
    pattern repeated twice is orthogonal to the index across eight points, so
    the fitted slope is exactly the constructed 65 536 B/tile. Then
    `Sxx = 2*(3.5^2 + 2.5^2 + 1.5^2 + 0.5^2) = 42`, `SSR = 8 * (1e5)^2 = 8e10`,
    `s^2 = 8e10/6`, and `SE = sqrt(8e10 / (6 * 42)) = 17 817.42` B/tile. The
    slope is **3.68** standard errors from zero, so the leak clears its own
    noise, and the run's total is `7 * 65 536 = 458 752 B`.

    Bug this catches: a fit taken on the wrong axis, which returns the
    reciprocal, or an `abs()` on the slope. The second is the dangerous one --
    it makes a leak and a shrinking resident set the same observation, and a
    resident set that shrinks under reclaim is precisely the reading
    `rss_validity` exists to refuse.
    """
    report = accumulation_report(_peaks(65_536.0, tiles=8, scatter=1e5))

    assert report.growth_bytes_per_tile == pytest.approx(65_536.0, rel=1e-9)
    assert report.standard_error == pytest.approx(17_817.416, rel=1e-6)
    assert report.consistent_with_zero is False
    assert report.tiles == 8
    # Seven steps between eight tiles, so the run's total growth is 7 * 65 536.
    assert report.total_growth_bytes == pytest.approx(458_752.0, rel=1e-9)


def test_a_shrinking_run_is_reported_as_shrinking_and_not_as_no_accumulation():
    """A falling resident set is a finding, not a pass.

    Expected values derived by hand: the same eight-tile fixture as above with
    the growth negated, so the slope is exactly -50 000 B/tile against the same
    17 817.42 standard error -- 2.81 errors from zero, outside the two-sigma
    band, so it is not consistent with zero either.

    Bug this catches: reporting `abs(growth)` or clamping at zero. Under
    reclaim the resident set falls while the process holds the same pages, so a
    report that cannot express a negative slope turns the one in-band symptom
    of an invalid measurement into a clean bill of health -- which is criterion
    7 passing for the wrong reason, moved to the accumulation half.
    """
    report = accumulation_report(_peaks(-50_000.0, tiles=8, scatter=1e5))

    assert report.growth_bytes_per_tile == pytest.approx(-50_000.0, rel=1e-9)
    assert report.consistent_with_zero is False
    assert "-50000" in report.verdict.replace(" ", "")


def test_readings_that_sit_exactly_on_a_line_are_refused_not_reported():
    """A watermark that has stopped moving is no evidence, and says so.

    Expected behaviour determined independently: `machine.peak_rss_bytes` is a
    high-water mark, so once the largest tile has been held every later reading
    is the SAME INTEGER. A least-squares line through identical numbers has
    zero residual, hence zero standard error, hence a two-sigma band of zero
    width -- the report would state that it excluded every per-tile leak of
    every size, from a run in which the instrument simply stopped responding.

    Bug this catches: the accumulation measurement being fed the watermark
    instead of the current resident set. It is the easy mistake -- the
    watermark is the number criterion 7 wants two lines earlier in the same
    callback -- and it fails **silently and in the reassuring direction**,
    which is the combination this project refuses everywhere else.
    """
    with pytest.raises(ValueError) as caught:
        accumulation_report((2.31e8,) * 8)

    assert "exactly on a line" in str(caught.value)
    assert "high-water mark" in str(caught.value)
    assert "one-byte resolution" in str(caught.value)
    # And a genuinely sloped-but-noiseless column is refused for the same
    # reason, so the guard is about the residual and not about flatness.
    with pytest.raises(ValueError, match="standard error"):
        accumulation_report(_peaks(1000.0, tiles=8))


def test_a_run_of_seven_tiles_or_fewer_is_refused_rather_than_reported():
    """Below eight tiles the tail's exclusion would rest on one residual or none.

    Expected behaviour determined independently: the second half is fitted
    separately as the steady state, so eight tiles is four in each half. A
    straight line through two points is exact, so its residual sum is zero
    whatever the truth is and its standard error is undefined -- the report
    would exclude every leak there is. Three points leave one residual degree
    of freedom, so the whole exclusion is set by a single reading. Four is the
    first count with two, and it is the threshold `linearity_report` refuses
    below for the same reason one order up.

    Bug this catches: a report that accepts four tiles and hands back a tail
    fitted through two of them. That is not a weak answer, it is a confident
    wrong one -- "this run excludes every per-tile leak" from a steady state
    that was never measured.
    """
    for tiles in (4, 7):
        with pytest.raises(ValueError) as caught:
            accumulation_report(_peaks(0.0, tiles=tiles, scatter=1e5))
        assert str(tiles) in str(caught.value)
        assert "residual" in str(caught.value)
        assert "eight" in str(caught.value)


def test_the_verdict_states_the_exclusion_rather_than_asserting_a_result():
    """What a reader quotes has to carry the bound, not the point estimate.

    Expected content determined independently from the hand-computed figures in
    `test_a_flat_run_reports_no_growth_and_the_leak_it_could_have_excluded`:
    the two-sigma band is +/-126 491 B/tile.

    Bug this catches: a verdict that says "no accumulation" from a slope
    consistent with zero. Task 7's ladder was published as a bound for exactly
    this reason, and an accumulation instrument is more prone to the error, not
    less -- a flat line looks like proof.
    """
    report = accumulation_report(_peaks(0.0, tiles=8, scatter=1e5))

    assert "EXCLUDES" in report.verdict
    assert "-35635" in report.verdict.replace(" ", "")
    assert "+35635" in report.verdict.replace(" ", "")
    assert "8 tiles" in report.verdict


def test_a_warm_up_is_not_published_as_a_leak():
    """A one-time cost charged to every tile is the error this field exists for.

    Expected values derived by hand. The readings rise by 1e6 across the first
    four tiles and then hold, plus the same `(+1, -1, -1, +1)` residual at 1e4.
    Over the whole run, `Sxx = 42` and `Sxy = 17.0e6`, so the fitted slope is
    `17.0e6 / 42 = 404 761.9` B/tile -- large, and an artefact. The second half
    is flat: the residual pattern is orthogonal to its index, so its slope is
    exactly 0, and with `SSR = 4e8`, `s^2 = 2e8` and `Sxx = 5` its standard
    error is `sqrt(4e7) = 6324.56` B/tile.

    Bug this catches: reporting the whole-run slope alone. **Measured on this
    project's own 36-tile run**, which rose 3.81 MB across its first eighteen
    tiles and 0.16 MB across its last eighteen; one line through all of it gave
    `+69 083 +- 9 523 B/tile at 7.3 sigma`, which is a confident, significant
    and entirely fictional leak. numba's compiled entry points, zarr's metadata
    and the allocator's arenas are paid once, and a per-tile figure that
    includes them extrapolates a fixed cost as if it recurred.
    """
    signs = [1.0, -1.0, -1.0, 1.0]
    rise = [0.0, 1e6, 2e6, 3e6, 3e6, 3e6, 3e6, 3e6]
    readings = [
        2.31e8 + step + 1e4 * signs[index % 4] for index, step in enumerate(rise)
    ]

    report = accumulation_report(readings)

    assert report.growth_bytes_per_tile == pytest.approx(404_761.905, rel=1e-6)
    assert report.consistent_with_zero is False
    assert report.tail_tiles == 4
    assert report.tail_growth_bytes_per_tile == pytest.approx(0.0, abs=1e-6)
    assert report.tail_standard_error == pytest.approx(6324.555, rel=1e-6)
    assert report.tail_consistent_with_zero is True
    # The two bands do not overlap, so the steady state does not support the
    # whole-run slope -- which is what makes the whole-run slope a transient.
    assert report.saturating is True
    assert "SATURATING" in report.verdict
    assert "NOT a leak" in report.verdict


def test_a_constant_leak_is_not_reported_as_saturating():
    """The negative control for `saturating`, without which it means nothing.

    Expected values determined independently: a genuine per-tile leak has the
    same slope in both halves, so the whole-run and tail fits agree and the
    difference between them is nowhere near their bands. The fixture is the
    eight-tile 65 536 B/tile leak from above, whose whole-run slope is exactly
    the constructed one.

    Bug this catches: `saturating` computed from the whole-run slope alone --
    for instance "any slope above some threshold is warm-up". It would then
    label every leak a transient, which is the same reassuring-direction
    failure as the watermark, one level up.
    """
    report = accumulation_report(_peaks(65_536.0, tiles=8, scatter=1e5))

    assert report.growth_bytes_per_tile == pytest.approx(65_536.0, rel=1e-9)
    assert report.tail_growth_bytes_per_tile == pytest.approx(65_536.0, rel=1e-9)
    assert report.saturating is False
    assert "SATURATING" not in report.verdict


def test_a_run_that_both_warms_up_and_leaks_still_reports_saturating():
    """`saturating` says a transient is present, never that there is no leak.

    Expected behaviour determined independently: adding a constant per-tile
    cost raises the whole-run slope and the tail slope by the SAME amount and
    changes neither residual, so their difference -- which is all `saturating`
    compares -- is untouched. The fixture is the warm-up readings from
    `test_a_warm_up_is_not_published_as_a_leak` with 1e6 per tile added, so its
    whole-run slope is `404 761.9 + 1e6` and its tail slope is `0 + 1e6`, both
    shifted by exactly 1e6 from the values hand-derived there.

    Bug this catches: a caller -- or a future edit to this module's own
    docstring -- reading `saturating is True` as "no per-tile leak". This
    exact mistake was made while writing Task 8's suite test, and the positive
    control in `test_reuse.py` is what caught it: a 1 MB/tile leak injected
    into a real 16-tile run left the flag True. The leak test is the tail's
    magnitude and this pins that it has to be.
    """
    signs = [1.0, -1.0, -1.0, 1.0]
    rise = [0.0, 1e6, 2e6, 3e6, 3e6, 3e6, 3e6, 3e6]
    readings = [
        2.31e8 + step + 1e4 * signs[index % 4] + 1e6 * index
        for index, step in enumerate(rise)
    ]

    report = accumulation_report(readings)

    assert report.growth_bytes_per_tile == pytest.approx(1_404_761.905, rel=1e-6)
    assert report.tail_growth_bytes_per_tile == pytest.approx(1e6, rel=1e-9)
    assert report.saturating is True
    # And the tail -- the figure that IS the leak test -- has moved by the
    # whole leak, which is the difference between the two readings.
    assert report.tail_consistent_with_zero is False


def test_the_accumulation_report_keeps_no_copy_of_the_readings_it_was_given():
    """One home per measurement, at the second report as at the first.

    `linearity_report`'s equivalent partitions its fields against
    `CalibrationResult`. This one has no result type to partition against, so
    the rule takes its other form: **the readings belong to the run that took
    them, and the report carries only what it derived.**

    Expected behaviour determined independently from the rule itself, which
    this project has paid for four times -- the published tile side, F3's
    magnitude, the sweep timing, and a docstring publishing a floor at
    `k_beta = 4` for an instrument running six.

    Bug this catches: a later reader adding `readings` or `peaks` to the report
    "so the caller can see what it fitted". After that a run's readings exist
    in two places, a re-measurement updates one, and the growth figure can be
    quoted beside numbers it was never computed from with nothing comparing
    them.
    """
    fields = {field.name for field in dataclasses.fields(AccumulationReport)}

    for copied in ("peaks", "readings", "values", "residuals", "indices"):
        assert copied not in fields
    # What it does carry is derived, and `tiles` is a count rather than a copy
    # -- the one number a caller cannot recover from the report without it.
    assert "tiles" in fields
    assert "tail_growth_bytes_per_tile" in fields


def test_the_transient_factor_is_read_from_the_constant_rather_than_inlined(
    monkeypatch,
):
    """The documented policy has to be the thing the code consults.

    Expected behaviour determined independently: `saturating` is
    `gap > FACTOR * (SE + tail SE)`, so raising the factor far enough makes any
    finite gap fail the comparison. The fixture is the warm-up readings from
    `test_a_warm_up_is_not_published_as_a_leak`, which saturate at 2.0; at 1e6
    nothing can.

    **The exact value is NOT derived and is pinned here on purpose**, the way
    this module pins `SLOPE_RESOLUTION_LIMIT` and `SLOPE_BAND_FACTOR`: it is a
    policy number with a stated asymmetry, so changing it must be a deliberate
    edit that updates a test rather than a silent one.

    Bug this catches: the factor written as a literal `2.0` in the comparison
    while the constant sits above it carrying a docstring. The policy would
    then be decoration -- editing it would change the documentation and not the
    behaviour -- which is the same defect as a docstring that outlives the code
    it describes, in the direction where the reader trusts it.
    """
    assert ACCUMULATION_TRANSIENT_FACTOR == 2.0

    signs = [1.0, -1.0, -1.0, 1.0]
    rise = [0.0, 1e6, 2e6, 3e6, 3e6, 3e6, 3e6, 3e6]
    readings = [
        2.31e8 + step + 1e4 * signs[index % 4] for index, step in enumerate(rise)
    ]
    # FIXTURE GUARD: it saturates at the shipped factor, so the flip below is
    # the constant doing it and not the data.
    assert accumulation_report(readings).saturating is True

    monkeypatch.setattr(memory_module, "ACCUMULATION_TRANSIENT_FACTOR", 1e6)
    assert accumulation_report(readings).saturating is False
