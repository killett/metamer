"""Analytic bytes-per-series for the code that exists (design doc section 9.4).

    resident = B * ( N*9 + X_term + out(M, p_max, k_beta) )  +  placement_constant

**ONE FORMULA WITH A PLACEMENT PARAMETER, NOT TWO SHAPES.** Design doc section
9.4 says *"the formulas have different shapes, not just different constants"*.
That was true of the two **designs** and is false of the **code**:

- Path A's `B * (... + c_A)` described the batched trust-region of section 8.3,
  which the stage-1 spike deleted -- Task 19, deleted rather than deferred,
  under the >=3x rule. `fit.py:223` is `for b in range(batch)` around
  `optimize_series(obj, y[b:b+1], ...)`, so **every allocation the optimizer and
  the engine make is live for one series at a time.**
- Path B's `T * c_B` described a `prange`-over-series driver. `CompiledEngine`
  pranges over whatever batch `score` is handed, and `fit` hands it one series,
  so **B = 1 through `run()`** and the compiled engine's tile shape is the
  Kalman engine's.

So the two placements differ in a **constant** -- `1 * c` against `T * c` --
both independent of B. `SolverPlacement.PER_THREAD` is **declared and
unreachable** through `run()`; `test_memory.py` asserts the unreachability and
pins the arithmetic of the branch through a constructed call, because an
unreachable branch with no reachability assertion becomes reachable silently.

WHAT IS PER-SERIES, AND WHY IT IS ONLY THESE TWO THINGS.
-------------------------------------------------------
- `N*9` -- the data tile: 8 bytes of float64 `y` plus a 1-byte mask, held for
  every series in the tile at once. Data arrives float32 from disk and `core` is
  float64; the conversion happens per chunk during tile assembly, so the two
  representations never coexist.
- `X_term` -- zero when every regressor is shared (one copy, negligible), and
  `N * k_beta * 8` when **any** regressor is a per-point field. At N=630,
  k_beta=4 that is 20.2 kB/series and it moves `tile_side` by about a factor of
  two, which is why the refused regime still ships a formula branch (a3).
- `out(...)` -- the output slots `fit` preallocates and holds until the tile is
  written. See `output_slot_bytes`.

Everything else -- the filter's state blocks, the normal-equation accumulators,
the reused `[y | X]` row, scipy's L-BFGS-B workspace, the Hessian and its
inverse -- is inside `fit.py`'s per-series loop and is therefore a constant.

**WHAT THIS FORMULA IS AND IS NOT: RESIDENT, NOT PEAK.** It counts what is live
for the life of the tile. `fit` also holds **per-candidate temporaries that do
scale with B** -- `var_gls` and `var_white` at `(B,)` each, the
`np.nan_to_num(theta[:, c, :p])` copy, and `hydrate`'s `(B, p_total)` block --
all allocated inside the candidate loop and dropped at its end.

**AND THE ESTIMATE IS NOT NEGLIGIBLE, WHICH IS WHY IT IS WRITTEN DOWN RATHER
THAN WAVED AT.** `var_gls` and `var_white` alone are 16 B/series and leave the
worked example's side at 347 (8290 -> 347). The whole set is **of order 100
B/series, ~1.2%**, and at 8374 the side is **345** -- two grid points, from a
term nobody has measured. **That is an ESTIMATE, not a measurement**, and
labelling it as one is the point: Task 7 measures it, and Task 2's
`HEADROOM_FRACTION` is what must cover it. **It is a slope term rather than a
constant, which is the argument for the headroom staying a FRACTION of the
budget instead of a fixed number of bytes.**

**THE STANDING CHECK IS A TWO-SIDED BAND.** It was *"treat any factor above
~1.5x as a missing term"*, and that one-sided form would have passed all four of
this module's 2026-08-14 defects. See `slope_band`.
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from metamer.core import machine

if TYPE_CHECKING:  # pragma: no cover - import cycle; only needed for the label
    from metamer.core.engines.protocol import Engine


class SolverPlacement(StrEnum):
    """Where one live solver working set sits, relative to the series axis.

    `PER_SERIES_LIVE` is what `run()` reaches: `fit` loops `optimize_series`
    over the batch, so exactly one working set exists at a time whatever B is.
    `PER_THREAD` describes a driver that hands an engine a real batch and
    parallelizes over series -- **it does not exist**, and `bench/spike.py` is
    the only thing shaped like it.

    **The unreachable member is declared rather than deleted**, on Task 16's
    `shared_with` precedent: the day a batched driver lands, the engine's own
    workspace becomes a per-series term and it is engine-dependent, so the
    calibration key has to distinguish placements **before** the driver exists
    or the first batched measurement silently reuses a per-series-live entry.
    """

    PER_SERIES_LIVE = "per_series_live"
    PER_THREAD = "per_thread"


class MemoryEngineLabel(StrEnum):
    """Which engine's workspace a memory measurement belongs to.

    **NOT `EngineId`, AND THE DIFFERENCE IS LOAD-BEARING.**
    `CompiledEngine.engine_id` is `EngineId.KALMAN` deliberately, because the
    two engines compute the same likelihood by the same recursion and their
    scores must stay rankable against each other. `EngineId` answers *"are these
    scores comparable"*; this answers *"do these engines cost the same"*. **They
    give different answers for the same pair** -- `CompiledEngine` allocates
    `accum`, `sum_log_s`, `n_used` and `degenerate` per series inside its
    `prange`, where a batched `KalmanEngine` would hold one `(B, d, d)` block --
    so a calibration cache keyed on `EngineId` would serve one engine's slope to
    the other.
    """

    KALMAN_NUMPY = "kalman_numpy"
    KALMAN_COMPILED = "kalman_compiled"


LBFGS_MAXCOR = 10
"""scipy's `maxcor` default, and `optimize_series` does not override it.

The L-BFGS-B workspace is dominated by `11 * maxcor**2` doubles, which does
**not** depend on the parameter count -- see `_optimizer_bytes`. Read from
scipy 1.18.0's `_lbfgsb_py._minimize_lbfgsb` signature on 2026-08-14; it is a
default this module depends on, so it is named rather than inlined.
"""

HEADROOM_FRACTION = 0.15
"""POLICY. The fraction of `budget - floor` held back from the tile.

**NOT eps-derived, and nothing about float64 has an opinion here.** It exists
because peak RSS overshoots a steady-state model through transients, and this
module's formula counts what is **resident** rather than what is **peak**. What
it must absorb, named so a later reader can check whether 0.15 still covers it:

- **The per-candidate temporaries `fit` holds and this formula does not charge**
  -- `var_gls` and `var_white` at `(B,)` each, the
  `np.nan_to_num(theta[:, c, :p])` copy, and `hydrate`'s `(B, p_total)` block.
  Estimated at order 100 B/series, ~1.2%.
- **The float32 span alive during tile assembly**, before it is cast into the
  float64 destination and dropped.
- **zarr's decompression buffers** on the chunk reads that fill the tile.
- **`FloorReport.post_warm_bytes` being a LOWER bound** (the probe warms with a
  lighter spec than production), so `block_bytes` is an upper bound.

**A FRACTION AND NOT A FIXED NUMBER OF BYTES, for two independent reasons that
push the same way**: the first three items above scale with the block, and the
fourth makes the block itself an over-estimate. A constant would be right at one
budget and wrong at every other.

**THE ASYMMETRY IS THE JUSTIFICATION FOR CHOOSING CONSERVATIVELY, and it is not
a matter of taste**: too small kills the process, too large costs runtime. One
failure mode ends the run and the other slows it, so the two are not
interchangeable and the value is set from the expensive side.

**Whether 0.15 is enough is a MEASUREMENT and Task 8 is what takes it.** Until
then it is a policy constant with its components named, in
`lint.OVERLAP_RATIO`'s idiom, and it must not be dressed as derived.
"""

DEFAULT_BUDGET_FRACTION = 0.25
"""POLICY. The fraction of TOTAL RAM a config that names no budget resolves to.

**TOTAL, NEVER AVAILABLE, AND THAT IS THE WHOLE OF THE DECISION.** The derived
tile side is a function of the budget, and a resume compares the side it derives
against the one the store was built with -- so a budget that moved with ambient
load would make a second run of the same store derive a smaller side, hit
`completion.resume_tile_side`'s *stored > derived* arm and **refuse**. A resume
that fails because a browser was open defeats design doc section 15.5's
burst-and-resume argument, which is the reason `memory_budget_gb` is
run-relevant at all. `min(total, available)` is the same failure arriving less
often and therefore harder to diagnose.

Total RAM is also one of the machine fingerprint's three components, so a
total-RAM default is stable exactly where section 11.4's calibration cache is
valid; an available-RAM default would vary **within one cache key**.

**THE VALUE WAS CHOSEN AGAINST MEASUREMENTS RATHER THAN PICKED, AND THEY LIVE IN
ONE PLACE.** The availability spread this machine actually shows, the three
candidate fractions against it, and the side 0.25 derives here are in
`PROGRESS.md`'s *What Task 3 established* section -- **once**, on
`store.TILE_SIDE_BASE`'s precedent, because a measurement restated beside its
consumer is a measurement that drifts. What settles the value rather than taste:
a fraction whose budget exceeds availability on an **idle** machine warns on
every run, and a warning that always fires is not a warning. The asymmetry is
the headroom's -- too high kills the process, too low costs runtime -- so the
value is set from the expensive side.

**And a float note, stated so nobody "fixes" it.** The budget round-trips
through a GB float, so `int(default_budget_gb() * 10**9)` comes out **one byte
below `total // 4`**. Deterministic, invisible against a multi-gigabyte budget,
and not worth a special case.
"""

SLOPE_BAND_FACTOR = 1.5
"""POLICY. How far a measured slope may sit from the formula, either way.

**Two-sided, corrected 2026-08-14.** The check was *"treat any factor above
~1.5x as a missing term"*, and a measured slope **materially below** the formula
is equally a finding: the formula is then charging for something the code does
not hold, and the excess capacity hides whatever else is wrong. The one-sided
form passed every formula defect found on 2026-08-14, including two of opposite
sign that put the total within 0.5% of a measurement while neither term was
right.

**Consequence of the value, stated because it is policy and not derived.** Too
wide and a missing term reads as transients; too narrow and allocator rounding
reads as a defect. 1.5 is inherited from the one-sided form, where it was chosen
to admit per-step transients and allocator rounding while still rejecting a term
carrying an extra factor of N or `k_beta`. **And per (a), a ratio inside the
band is not evidence the terms are right** -- check the terms.
"""


SLOPE_RESOLUTION_LIMIT = 0.10
"""POLICY. Relative standard error above which a ladder reports a BOUND.

**A NUMBER WITH A STANDARD ERROR LARGER THAN THE EFFECT IS NOT A
MEASUREMENT**, and this project has one instance of publishing one anyway:
Task 4's affordable ladder returned **1666 B/series against an analytic 926**
on its first attempt -- read as a 1.80x finding, and correctly re-read as
noise once the scatter was measured. The shipped four-point ladder came back
at **1049 +- 222**, a relative standard error of **21%**, which is why its
value claim lives in `PROGRESS.md` with its uncertainty and not in an
assertion.

**THE THRESHOLD IS ON THE RELATIVE ERROR AND NOT ON THE DISTANCE FROM ZERO**,
because a slope four standard errors from zero can still be useless: at 21%
Task 4's ladder cleared any distance-from-zero test and could not tell 926
from 1250. What a memory budget needs is a per-series cost good enough that
the tile it sizes is right, and 10% of the per-series cost is 5% of the tile
side.

**THE ASYMMETRY, since this is policy rather than derived**: too loose and a
noise-dominated ladder is published as a value, which is the failure above;
too tight and a perfectly good measurement is reported as a bound, which
costs a sentence and no correctness. **Set from the expensive side.**
"""


ACCUMULATION_TRANSIENT_FACTOR = 2.0
"""POLICY. How far the tail's growth must sit below the whole run's to be called a transient.

A tile loop pays numba's compiled entry points, zarr's metadata and the
allocator's arenas **once**, at the front. `AccumulationReport.saturating`
compares the whole-run slope against the steady state's and calls the difference
a transient when it exceeds this many times the two standard errors together.

**IT GATES A DESCRIPTION AND NEVER A LEAK TEST**, which is the whole reason it
can be a policy number at all: `saturating` says whether the whole-run slope is
safe to read, and the leak test is `tail_growth_bytes_per_tile` regardless of
what this is set to. A run can saturate and leak at once.

**THE ASYMMETRY, since this is policy rather than derived.** Too low and
ordinary scatter between two fits reads as a warm-up, so a real constant leak
gets described as a transient -- the reassuring direction, and the one that
matters. Too high and a genuine warm-up goes undescribed, which costs a sentence
and no correctness, because the tail is published either way. **Set from the
expensive side**, and 2.0 is the same two-sigma convention every other bound in
this module uses.
"""


@dataclass(frozen=True)
class AccumulationReport:
    """What a tile loop's per-tile peaks exclude about accumulation.

    **THE SUBJECT IS PEAK AGAINST TILE INDEX, WHICH IS NOT `LinearityReport`'s
    SUBJECT.** That one fits peak against **B** across a ladder of separate
    runs and asks how much one more series costs. This one fits peak against
    **tile index** inside a single run and asks how much one more *iteration*
    costs, which the formula says is **zero**: a tile is released before the
    next is assembled. The two share arithmetic and share no question.

    **AND THE ANSWER IS AN EXCLUSION, NOT A VERDICT.** A flat line looks like
    proof, and it is the shape a measurement takes when it cannot see anything
    at all. So the number that matters is `detectable_growth` -- what this run
    would have had to leak before this run could have noticed.

    **THE WHOLE-RUN SLOPE IS NOT THE LEAK, AND MEASURING ONE TAUGHT US THAT.**
    Phase 2b Task 8's 36-tile run rose **3.81 MB across its first eighteen
    tiles and 0.16 MB across its last eighteen**: numba's compiled entry points,
    zarr's metadata and the allocator's arenas are all one-time costs paid at
    the front of a loop. A straight line through the whole run charged them to
    every tile and reported **+69 083 +- 9 523 B/tile at 7.3 sigma** -- a
    confident, significant, and entirely wrong leak. **So both halves are fitted
    and both are published**, and the split is a fixed rule rather than a
    judgement, because a warm-up boundary chosen by looking at the data is the
    analysis fitted to the answer.

    Attributes:
        tiles: How many tiles the run wrote.
        growth_bytes_per_tile: The whole-run slope, **with its sign**. Negative
            is a resident set that fell, which is a finding about the
            measurement rather than about the loop. **Read it beside
            `saturating`, never alone.**
        standard_error: The slope's standard error, from the fit's own
            residuals.
        detectable_growth: `2 * standard_error` -- the smallest per-tile leak
            the whole-run fit could have excluded.
        lower_bound_bytes_per_tile: `growth - detectable_growth`.
        upper_bound_bytes_per_tile: `growth + detectable_growth`.
        consistent_with_zero: True when the whole-run growth is inside its own
            two-sigma band, which is *"no leak was seen"* and never *"there is
            no leak"*.
        total_growth_bytes: The fitted growth across the run, `growth` times
            the index span. **What a reader actually pays**, since a per-tile
            figure at 400 tiles and one at 4 are different amounts of memory.
        excluded_total_bytes: `detectable_growth` times the span -- the total
            the whole-run fit could have excluded.
        tail_tiles: Tiles in the second half, which is the fitted steady state.
        tail_growth_bytes_per_tile: The second half's slope. **This is the
            figure that extrapolates**, because a leak is a property of the
            steady state and a warm-up is paid once.
        tail_standard_error: Its standard error.
        tail_consistent_with_zero: Whether the tail's growth is inside its own
            two-sigma band.
        saturating: True when the tail's growth is smaller than the whole
            run's by more than the two bands together -- the signature that a
            **transient is present**. **IT IS NOT A LEAK TEST AND MUST NEVER BE
            USED AS ONE.** A run can saturate and leak at once: adding a
            constant per-tile cost raises both slopes equally and leaves their
            difference, and therefore this flag, untouched. Found by the
            positive control in
            `test_reuse.py::test_the_recompute_loop_retains_nothing_that_survives_its_warm_up`,
            which injected a 1 MB/tile leak into a real run's readings and
            watched `saturating` stay True. **The leak test is
            `tail_growth_bytes_per_tile`**; this flag only says whether the
            whole-run slope is safe to read, and it never is when it is True.
        verdict: One sentence a reader can quote, built from the fields above.
    """

    tiles: int
    growth_bytes_per_tile: float
    standard_error: float
    detectable_growth: float
    lower_bound_bytes_per_tile: float
    upper_bound_bytes_per_tile: float
    consistent_with_zero: bool
    total_growth_bytes: float
    excluded_total_bytes: float
    tail_tiles: int
    tail_growth_bytes_per_tile: float
    tail_standard_error: float
    tail_consistent_with_zero: bool
    saturating: bool
    verdict: str


def accumulation_report(peaks: Sequence[float]) -> AccumulationReport:
    """Say what a run's per-tile peaks exclude about a per-tile leak.

    **THE STRAIGHT-LINE ARITHMETIC IS `linearity_report`'s, DELIBERATELY THE
    SAME**: `s**2 = SSR/(n-2)`, `SE = sqrt(s**2/Sxx)`. It is written out rather
    than shared through a helper because the two functions differ in what they
    fit it to and agree in nothing else, and a helper taking `(x, y)` would
    invite a caller to fit one subject's data with the other's interpretation.

    **THE INDEX IS THE ABSCISSA AND NOT THE TILE'S SERIES COUNT.** A ragged
    grid's edge tiles hold fewer series, so a fit against series count would
    charge the edge tiles' smaller blocks to a leak, or hide one behind them.
    The question is *"does iterating cost anything"*, and iterations are
    counted.

    **DO NOT FEED THIS A HIGH-WATER MARK.** `machine.peak_rss_bytes` is monotone
    and stops moving once the largest tile has been held, so a run with no leak
    produces a column of **identical** numbers -- zero residual, zero standard
    error, and a report that says it excluded every per-tile leak there is.
    That is the confident-from-nothing answer this module refuses elsewhere, so
    it is refused here too: **pass `current_rss_bytes` per tile**, which is the
    working set, which jitters, and in which a leak appears one tile earlier
    than in a watermark. The watermark belongs in the criterion-7 comparison
    against the budget, where monotonicity is the property that makes it right.

    Args:
        peaks: One peak per tile, in the order the tiles were written.

    Returns:
        The report.

    Raises:
        ValueError: If there are fewer than eight tiles, or if either half's
            readings sit exactly on a line. **Both are the same defect and it
            is not a small one**: with no residual the standard error is zero,
            every bound collapses to the point estimate, and the report claims
            to have excluded every leak of every size. **Eight is four in each
            half**, and four is the count below which a straight line has at
            most one residual to be wrong about -- the threshold
            `linearity_report` refuses below for the same reason one order up.
            Identical readings reach the same place by instrument, which is
            what a high-water mark produces.
    """
    import numpy as np

    count = len(peaks)
    if count < 8:
        raise ValueError(
            f"an accumulation report needs at least eight tiles and got "
            f"{count}: the second half is fitted separately as the steady "
            "state, so eight is four in each half -- and below four a straight "
            "line has one residual or none, which would let this report claim "
            "to have excluded every per-tile leak there is"
        )

    def fit(values: np.ndarray, what: str) -> tuple[float, float]:
        """Return `(slope, standard error)` for one span of readings.

        Args:
            values: The readings, in order.
            what: Which span, for the failure message.

        Returns:
            Slope in bytes per tile and its standard error.

        Raises:
            ValueError: If the readings sit exactly on a line, so the fit has
                no residual to take a standard error from.
        """
        indices = np.arange(len(values), dtype=np.float64)
        slope, intercept = np.polyfit(indices, values, 1)
        residuals = values - (slope * indices + intercept)
        centred = indices - indices.mean()
        variance = float((residuals**2).sum()) / (len(values) - 2)
        error = float(np.sqrt(variance / float((centred**2).sum())))
        # **THE THRESHOLD IS ONE BYTE AND IT IS DERIVED, NOT CHOSEN.** Resident
        # set size is counted in whole pages and reported in bytes, so a
        # standard error below a single byte means the readings are collinear
        # at the finest resolution the instrument has -- there is no residual
        # to take an uncertainty from. Testing `== 0.0` instead would miss it:
        # least squares on identical integers returns residuals of order 1e-8,
        # not zero, so an exact comparison lets exactly the reassuring case
        # through.
        if error < 1.0:
            raise ValueError(
                f"the {what} readings sit exactly on a line -- the fitted "
                f"standard error is {error:.3g} B/tile, below the one-byte "
                "resolution of the instrument -- so this report would exclude "
                "every per-tile leak of every size. A column of identical "
                "numbers is what a high-water mark produces once it has stopped "
                "moving: pass the per-tile CURRENT resident set instead"
            )
        # **CAST AT THE BOUNDARY**: numpy's scalars render differently in a
        # message and its boolean fails `is True`, so a caller asserting
        # identity against this dataclass would get a wrong answer from a right
        # computation.
        return float(slope), error

    values = np.asarray(peaks, dtype=np.float64)
    growth, error = fit(values, f"{count}")
    # **THE SPLIT IS A FIXED RULE AND NOT A JUDGEMENT.** A warm-up boundary
    # chosen by looking at the readings is the analysis fitted to the answer;
    # the second half is whatever the second half is.
    tail_values = values[count // 2 :]
    tail_growth, tail_error = fit(tail_values, "second half's")

    detectable = 2.0 * error
    span = float(count - 1)
    consistent = bool(abs(growth) <= detectable)
    tail_consistent = bool(abs(tail_growth) <= 2.0 * tail_error)
    # A transient is a whole-run slope the steady state does not support, and
    # "does not support" is the two bands failing to overlap.
    saturating = bool(
        growth - tail_growth > ACCUMULATION_TRANSIENT_FACTOR * (error + tail_error)
    )

    if consistent:
        head = (
            f"NO PER-TILE GROWTH SEEN over {count} tiles: {growth:+.0f} +- "
            f"{error:.0f} B/tile EXCLUDES per-tile growth outside "
            f"{growth - detectable:+.0f} to {growth + detectable:+.0f} B/tile, "
            f"which is {detectable * span:.0f} B across the run"
        )
    else:
        head = (
            f"PER-TILE GROWTH of {growth:+.0f} +- {error:.0f} B/tile over "
            f"{count} tiles, {abs(growth) / error:.1f} standard errors from "
            f"zero and {growth * span:+.0f} B across the run"
        )
    tail_head = (
        f"the last {len(tail_values)} tiles give {tail_growth:+.0f} +- "
        f"{tail_error:.0f} B/tile"
    )
    if saturating:
        tail_head += (
            ", SATURATING -- the whole-run slope is a one-time warm-up charged "
            "to every tile and is NOT a leak"
        )
    return AccumulationReport(
        tiles=count,
        growth_bytes_per_tile=growth,
        standard_error=error,
        detectable_growth=detectable,
        lower_bound_bytes_per_tile=growth - detectable,
        upper_bound_bytes_per_tile=growth + detectable,
        consistent_with_zero=consistent,
        total_growth_bytes=growth * span,
        excluded_total_bytes=detectable * span,
        tail_tiles=len(tail_values),
        tail_growth_bytes_per_tile=tail_growth,
        tail_standard_error=tail_error,
        tail_consistent_with_zero=tail_consistent,
        saturating=saturating,
        verdict=(
            f"{head}; {tail_head}. A flat line is what this measurement looks "
            f"like when it can see nothing, so the bound is the result and the "
            f"slope is not"
        ),
    )


@dataclass(frozen=True)
class LinearityReport:
    """What a ladder establishes about linearity, and what it cannot see.

    **NOTHING HERE RESTATES A NUMBER `CalibrationResult` ALREADY CARRIES.** The
    slope, the intercept, the residuals and the ladder live there; two copies
    of one measurement drift the moment one is updated, and this project has
    paid for that four times. This is read **beside** a result, never instead
    of one.

    Attributes:
        slope_standard_error: The fitted slope's standard error, in bytes per
            series, from the residuals of the straight-line fit.
        relative_standard_error: The above over the measured slope. **The
            statistic the resolution verdict is made on**; see
            `SLOPE_RESOLUTION_LIMIT`.
        resolved: True when the ladder measured a value rather than a bound.
        analytic_bytes_per_series: What `resident_bytes_per_series` predicts
            for the configuration measured -- supplied by the caller, because
            this function does not know the candidate set.
        ratio: Measured over analytic.
        inside_band: Whether the ratio clears `slope_band`, which is
            **two-sided**: a slope materially BELOW the formula is a finding
            about the formula, never headroom.
        curvature: The fitted `B**2` coefficient, in bytes per series squared.
            **Reported with its sign**, since a per-series cost that falls with
            B and one that rises are different defects.
        curvature_standard_error: Its standard error.
        detectable_curvature: `2 * curvature_standard_error` -- the smallest
            quadratic term this ladder could have excluded.
        detectable_variation: What that curvature would do to the per-series
            cost across the ladder, as a fraction of the measured slope.
            **THIS IS THE HALF THAT MAKES THE LINEARITY CLAIM HONEST**: an
            instrument that cannot see curvature is not evidence of its
            absence, so a residual pattern is worth nothing without the
            magnitude it could have detected.
        verdict: One sentence a reader can quote, built from the fields above.
    """

    slope_standard_error: float
    relative_standard_error: float
    resolved: bool
    analytic_bytes_per_series: float
    ratio: float
    inside_band: bool
    curvature: float
    curvature_standard_error: float
    detectable_curvature: float
    detectable_variation: float
    verdict: str


def linearity_report(
    result: CalibrationResult, *, analytic_bytes_per_series: float
) -> LinearityReport:
    """Say what a ladder established, and what magnitude of curvature it could see.

    **THE RESIDUALS ARE THE DELIVERABLE AND THE FIT IS NOT.** Three points fit
    a line through **one** residual and cannot falsify linearity -- they can
    only fail to notice -- which is why the shipped ladder has four and why
    this function refuses fewer. The question a calibration's consumer actually
    has is *"may I extrapolate this slope"*, and the answer is a residual
    pattern **together with** the curvature the ladder was capable of
    detecting.

    **THE STRAIGHT-LINE FIT'S ARITHMETIC IS THE ONE TASK 4 DID BY HAND**, so
    the two agree by construction: `s**2 = SSR/(n-2)`, `SE = sqrt(s**2/Sxx)`.
    Fed Task 4's **published** ladder -- the four peaks as printed, to 0.01 MB
    -- this returns **1051 +- 224** against the recorded **1049 +- 222**, which
    agrees inside the table's own rounding: a +-5 kB perturbation of each peak
    moves the slope by up to `sum|B - Bbar| * 5000 / Sxx` = 2.7 B/series. **The
    check is that a function and a hand computation reach the same place from
    the same numbers**, which is what makes this arithmetic reusable rather
    than a second opinion.

    **THE QUADRATIC IS FITTED ON CENTRED B, AND THE REASON IS NOT THE ONE THAT
    WAS WRITTEN HERE FIRST.** The expectation was conditioning: `B**2` reaches
    1.6e8 at the top of this ladder and 6.9e10 at a production tile, so an
    uncentred normal matrix has entries spanning 1 to `B**4` and should lose
    digits where the whole question is a small coefficient. **Measured
    2026-08-16, it does not**: recovering a known `-1e-4` coefficient through
    `np.linalg.solve`, centred and raw agree to every digit printed at this
    ladder, at production-scale B, and at a ladder four times wider. The
    mutation that removes the centring **survives every test in this module**,
    and that says nothing about the tests -- it says the two are the same
    function on every input reachable here (the fifth cause in the mutation
    taxonomy, and the one people skip diagnosing).

    **It stays because it costs one subtraction and the expectation returns at
    a wider ladder than anything this project can run**, and because a
    justification that has been checked is worth more than one that has not.
    **What must not happen is the sentence outliving the check**: it is dated,
    and it says what was measured rather than what was assumed.

    Args:
        result: A measured ladder.
        analytic_bytes_per_series: `resident_bytes_per_series` for the
            configuration the ladder ran. **Passed in rather than derived**:
            this module's formula needs the candidate set and the series
            length, and a second derivation of them here would be a second
            description of one subject.

    Returns:
        The report.

    Raises:
        ValueError: If the ladder has fewer than four points. A quadratic
            through three points is exact, so its residual is zero whatever
            the truth is and its standard error is undefined -- **the report
            would claim to have excluded every curvature.** That is worse than
            refusing, because it is a confident answer.
    """
    import numpy as np

    if len(result.points) < 4:
        raise ValueError(
            f"a linearity report needs at least four ladder points and got "
            f"{len(result.points)}: a quadratic through three is exact, so the "
            "curvature it reports has no residual and no standard error, and "
            "the report would claim to have excluded every curvature there is"
        )

    batches = np.asarray([point.batch for point in result.points], dtype=np.float64)
    peaks = np.asarray([point.peak_bytes for point in result.points], dtype=np.float64)
    count = len(batches)

    # THE LINE, AND ITS STANDARD ERROR FROM ITS OWN RESIDUALS.
    slope, intercept = np.polyfit(batches, peaks, 1)
    line_residuals = peaks - (slope * batches + intercept)
    centred = batches - batches.mean()
    sxx = float((centred**2).sum())
    line_variance = float((line_residuals**2).sum()) / (count - 2)
    slope_error = float(np.sqrt(line_variance / sxx))

    # THE QUADRATIC, ON CENTRED B, WITH THE COVARIANCE COMPUTED HERE.
    # `np.polyfit(..., cov=True)` refuses below `order + 3` points -- five for a
    # quadratic -- and a four-point ladder is the one this task ships, so the
    # ordinary least-squares covariance is written out rather than borrowed.
    design = np.stack([np.ones_like(centred), centred, centred**2], axis=1)
    normal = design.T @ design
    coefficients = np.linalg.solve(normal, design.T @ peaks)
    quadratic_residuals = peaks - design @ coefficients
    quadratic_variance = float((quadratic_residuals**2).sum()) / (count - 3)
    curvature_error = float(np.sqrt(quadratic_variance * np.linalg.inv(normal)[2, 2]))
    curvature = float(coefficients[2])

    # A `c * B**2` term is a per-series cost of `c * B`, so across the ladder it
    # moves the per-series figure by `c * (B_max - B_min)`. Reported against the
    # slope, which is the quantity a consumer extrapolates.
    detectable = 2.0 * curvature_error
    span = float(batches.max() - batches.min())
    detectable_variation = detectable * span / abs(slope) if slope else float("inf")

    # **CAST AT THE BOUNDARY, BECAUSE NUMPY'S BOOLEAN IS NOT `bool`.** A
    # comparison of numpy scalars returns `np.bool_`, which is falsy-correct and
    # fails `is True` -- so a caller asserting identity against the dataclass
    # gets a wrong answer from a right computation. The same applies to every
    # float here: `np.float64` renders differently in a message and does not
    # round-trip through JSON.
    slope = float(slope)
    slope_error = float(slope_error)
    relative_error = slope_error / abs(slope) if slope else float("inf")
    resolved = bool(relative_error <= SLOPE_RESOLUTION_LIMIT)
    low, high = slope_band(analytic_bytes_per_series)
    ratio = slope / analytic_bytes_per_series
    inside = bool(low <= slope <= high)

    if resolved:
        head = (
            f"{slope:.0f} +- {slope_error:.0f} B/series ({relative_error:.1%}), "
            f"{ratio:.3f}x the formula's {analytic_bytes_per_series:.0f} and "
            f"{'inside' if inside else 'OUTSIDE'} the "
            f"{low:.0f}-{high:.0f} B/series band"
        )
    else:
        head = (
            f"NOT RESOLVED: {slope:.0f} +- {slope_error:.0f} B/series is "
            f"{relative_error:.0%} error, above the {SLOPE_RESOLUTION_LIMIT:.0%} "
            f"limit, so this ladder EXCLUDES per-series costs outside "
            f"{slope - 2 * slope_error:.0f}-{slope + 2 * slope_error:.0f} "
            f"B/series and establishes no value. The formula predicts "
            f"{analytic_bytes_per_series:.0f}"
        )
    return LinearityReport(
        slope_standard_error=slope_error,
        relative_standard_error=relative_error,
        resolved=resolved,
        analytic_bytes_per_series=float(analytic_bytes_per_series),
        ratio=ratio,
        inside_band=inside,
        curvature=curvature,
        curvature_standard_error=curvature_error,
        detectable_curvature=detectable,
        detectable_variation=detectable_variation,
        verdict=(
            f"{head}. Curvature {curvature:+.3g} B/series^2; this ladder could "
            f"have excluded {detectable:.3g}, which is a per-series cost "
            f"varying by {detectable_variation:.1%} across B in "
            f"[{batches.min():.0f}, {batches.max():.0f}] -- anything smaller "
            f"than that it cannot see, and not seeing it is not evidence"
        ),
    )


def memory_engine_label(engine: Engine) -> MemoryEngineLabel:
    """Return the memory-relevant label for an engine instance.

    Dispatches on the concrete type rather than on `engine_id`, which both
    shipped engines deliberately share.

    Args:
        engine: A likelihood engine.

    Returns:
        The label a calibration key should carry for it.

    Raises:
        TypeError: For an engine this module has no measured shape for. A
            default would file an unmeasured engine's slope under a measured
            engine's key, which is the one failure a cache cannot detect.
    """
    from metamer.core.engines.compiled import CompiledEngine
    from metamer.core.engines.kalman import KalmanEngine

    if isinstance(engine, CompiledEngine):
        return MemoryEngineLabel.KALMAN_COMPILED
    if isinstance(engine, KalmanEngine):
        return MemoryEngineLabel.KALMAN_NUMPY
    raise TypeError(
        f"no memory label for engine {type(engine).__name__!r}: its resident "
        f"working set has not been accounted for, and defaulting would file it "
        f"under another engine's calibration key"
    )


def output_slot_bytes(n_models: int, p_max: int, k_beta: int) -> int:
    """Per-series output slots, held for every candidate until the tile writes.

    **Field by field, from `fit.py:197-209`**, per `(series, candidate)` cell:

    | field | dtype | width | bytes |
    |---|---|---|---|
    | `theta` | float64 | `p_max` | `8*p_max` |
    | `theta_unconstrained` | float64 | `p_max` | `8*p_max` |
    | `theta_err` | float64 | `p_max` | `8*p_max` |
    | `beta` | float64 | `k_beta` | `8*k_beta` |
    | `beta_err` | float64 | `k_beta` | `8*k_beta` |
    | `loglik`, `k`, `n`, `n_eff_bic`, `n_eff_trend` | float64 | 1 each | 40 |
    | `n_iter` | int64 | 1 | 8 |
    | `init_rung` | object | 1 pointer | 8 |
    | `outcome` | uint8 | 1 | 1 |

    so `24*p_max + 16*k_beta + 57` per candidate.

    **`p_max`, NOT `p_m`.** `fit.py:186` sizes every candidate's slot to the
    widest candidate's free-parameter count and NaN-pads the rest, so a
    per-candidate `p` understates the array that is actually allocated.

    **THREE FIELDS AND A DTYPE WERE MISSING, AND THE ERROR WAS INVISIBLE
    BECAUSE IT CANCELLED.** The superseded
    `M*(2p + 2k_beta + 4)*8 + 3M` named neither `theta_unconstrained` nor `n`
    nor `init_rung`, and charged `n_iter` as a uint16. It was **163 B/candidate
    against 217, 25% low**, while the solver-state term was 12% high -- and the
    total sat within 0.5% of a measurement while **neither term was right**.
    That is the cancellation rule inside a sum: **verify each term, never the
    total**, which is why this function is asserted field by field.

    Args:
        n_models: Candidate count held until the tile is written.
        p_max: Widest candidate's free noise parameter count.
        k_beta: Number of design columns.

    Returns:
        Bytes of output slots per series.
    """
    per_candidate = 3 * p_max * 8 + 2 * k_beta * 8 + 5 * 8 + 8 + 8 + 1
    return int(n_models * per_candidate)


def _engine_workspace_bytes(d: int, k_beta: int) -> int:
    """One live filter pass's working set, for the batch of one it is given.

    `P`, `F`, `Q`, `P_inf` and two workspace copies; the state augmented over
    `[y | X]`; the normal-equation accumulators; and the one reused
    `(1, 1+k_beta)` float64 row both engines index the observation and the
    design columns out of per timestep.

    **The row used to be charged per series** (`streaming_overhead_bytes`,
    deleted 2026-08-14). It is `(B, 1+k_beta)` and production's B is 1, so it is
    a constant by the same argument that moved the rest of this function out of
    the per-series term.

    Args:
        d: Composite state dimension.
        k_beta: Number of design columns.

    Returns:
        Bytes of engine working set for one live pass.
    """
    state_blocks = 6 * d * d * 8
    augmented_state = d * (1 + k_beta) * 8
    accumulators = (k_beta * (k_beta + 1) // 2 + k_beta + 1) * 8
    reused_row = (1 + k_beta) * 8
    return int(state_blocks + augmented_state + accumulators + reused_row)


def _optimizer_bytes(p_max: int) -> int:
    """The scipy L-BFGS-B workspace at `p_max` free parameters.

    **THE OPTIMIZER IS L-BFGS-B FOR BOTH ENGINES.** `optimize.py:531` is
    `minimize(negative, u0, jac=jac, method="L-BFGS-B", ...)` and `fit` drives
    `optimize_series` whichever engine it holds, so there is one optimizer term
    and it does not vary with the placement. The superseded formula charged path
    A a *"dense quasi-Newton trust-region model"* of `(p**2 + 4p)*8` -- section
    8.3's design, deleted with Task 19 -- and path B `22p*8` for an L-BFGS
    history.

    Read out of scipy 1.18.0's `_lbfgsb_py._minimize_lbfgsb` on 2026-08-14, at
    `n = p_max` and `m = LBFGS_MAXCOR`:

        wa   = zeros(2*m*n + 5*n + 11*m*m + 8*m, float64)
        iwa  = zeros(3*n, int_dtype)
        nbd  = zeros(n, int_dtype)
        low_bnd, upper_bnd, g, x                     n float64 each
        dsave = zeros(29, float64)
        isave, lsave, task, ln_task                  44 + 4 + 2 + 2 ints

    **`11*m*m` dominates and does not depend on `p` at all**, so `22p*8` was not
    the same quantity with a different constant: at p=4 it gives 704 B against
    10 240 B for `wa` alone. That is why the term is wrong in **shape** rather
    than in magnitude, and why replacing it is part of correcting the formula
    rather than a refinement of it.

    **Integers are charged 8 bytes.** scipy picks int32 unless built with ILP64;
    8 is the conservative reading and the difference is 4*(4*p_max + 52) bytes,
    which is below the resolution of anything downstream.

    Args:
        p_max: Widest candidate's free noise parameter count.

    Returns:
        Bytes of optimizer workspace for one live fit.
    """
    m = LBFGS_MAXCOR
    workspace = (2 * m * p_max + 5 * p_max + 11 * m * m + 8 * m) * 8
    vectors = 4 * p_max * 8  # x, low_bnd, upper_bnd, g
    integer_arrays = 4 * p_max * 8  # nbd (n) and iwa (3n)
    saves = 29 * 8 + (44 + 4 + 2 + 2) * 8  # dsave; isave, lsave, task, ln_task
    return int(workspace + vectors + integer_arrays + saves)


def solver_state_bytes(
    placement: SolverPlacement,
    *,
    d: int,
    k_beta: int,
    p_max: int,
    threads: int = 1,
) -> int:
    """Solver working set for a tile: one copy, or one per thread.

    The three terms are the engine's working set (`_engine_workspace_bytes`),
    scipy's L-BFGS-B workspace (`_optimizer_bytes`), and the `p_max * p_max`
    Hessian `optimize_series` returns and `fit` inverts. **None of them scales
    with B**, which is this module's whole correction: `fit.py:223` runs them
    one series at a time.

    `p_max` rather than a per-candidate `p` for the same reason
    `output_slot_bytes` takes it: the constant must bound the widest candidate,
    since the tile holds whichever candidate is being fitted.

    Args:
        placement: `PER_SERIES_LIVE` for the loop that exists, `PER_THREAD` for
            a batched driver that does not.
        d: Composite state dimension.
        k_beta: Number of design columns.
        p_max: Widest candidate's free noise parameter count.
        threads: Worker threads. Ignored under `PER_SERIES_LIVE`, by
            construction -- one loop holds one working set whatever the machine
            has.

    Returns:
        Bytes of solver state for the whole tile.

    Raises:
        ValueError: If `threads` is below 1. Zero threads zeroes the entire
            term under `PER_THREAD`, which is a plausible-looking number that
            silently removes the only thread-dependent quantity in the formula.
    """
    if threads < 1:
        raise ValueError(f"threads must be at least 1, got {threads}")
    one = (
        _engine_workspace_bytes(d, k_beta) + _optimizer_bytes(p_max) + p_max * p_max * 8
    )
    if placement is SolverPlacement.PER_THREAD:
        return int(threads * one)
    return int(one)


def resident_bytes_per_series(
    *,
    k_beta: int,
    p_max: int,
    n_time: int,
    n_models: int,
    per_point_design: bool = False,
) -> int:
    """What one more series in the tile costs.

    **Takes neither a placement nor `d`, and that is the correction rather than
    an omission.** `d` reaches the formula only through the solver state, and
    the solver state is not per-series; a signature carrying either would assert
    a dependence this formula denies. The tile-level functions
    (`solver_state_bytes`, `resident_tile_bytes`, `tiling.tile_side_for`) take
    both, where they are real.

    Args:
        k_beta: Number of design columns.
        p_max: Widest candidate's free noise parameter count.
        n_time: Series length.
        n_models: Candidate count held until the tile is written.
        per_point_design: True if any regressor is a per-point field, which
            makes X per series rather than one shared copy.

    Returns:
        Bytes per series held resident for the life of the tile.
    """
    data = n_time * 9
    x_term = n_time * k_beta * 8 if per_point_design else 0
    return int(data + x_term + output_slot_bytes(n_models, p_max, k_beta))


def resident_tile_bytes(
    *,
    batch: int,
    placement: SolverPlacement,
    threads: int,
    d: int,
    k_beta: int,
    p_max: int,
    n_time: int,
    n_models: int,
    per_point_design: bool = False,
) -> int:
    """Total bytes one tile holds resident.

    `batch * resident_bytes_per_series(...) + solver_state_bytes(...)`. The
    second term is added **once**, or once per thread under the unreachable
    placement -- never once per series. Multiplying it by `batch` is the defect
    this module was carrying, and it is worth 1056 B/series (12.1%) at the
    section 9.4 worked example.

    Args:
        batch: Series in the tile.
        placement: Where the live solver state sits.
        threads: Worker threads. Ignored under `PER_SERIES_LIVE`.
        d: Composite state dimension.
        k_beta: Number of design columns.
        p_max: Widest candidate's free noise parameter count.
        n_time: Series length.
        n_models: Candidate count held until the tile is written.
        per_point_design: True if any regressor is a per-point field.

    Returns:
        Total bytes for the tile.
    """
    per_series = resident_bytes_per_series(
        k_beta=k_beta,
        p_max=p_max,
        n_time=n_time,
        n_models=n_models,
        per_point_design=per_point_design,
    )
    return int(
        batch * per_series
        + solver_state_bytes(
            placement, d=d, k_beta=k_beta, p_max=p_max, threads=threads
        )
    )


def slope_band(formula_bytes_per_series: float) -> tuple[float, float]:
    """The two-sided band a measured per-series slope must sit inside.

    Args:
        formula_bytes_per_series: What the formula predicts.

    Returns:
        `(low, high)`, both inclusive bounds in bytes per series.

    Raises:
        ValueError: If the prediction is not positive. A band around zero
            admits every measurement, which is the one outcome a band exists to
            prevent.
    """
    if formula_bytes_per_series <= 0:
        raise ValueError(
            f"a slope band needs a positive prediction, got {formula_bytes_per_series}"
        )
    return (
        formula_bytes_per_series / SLOPE_BAND_FACTOR,
        formula_bytes_per_series * SLOPE_BAND_FACTOR,
    )


def tile_side(budget_bytes: int, per_series_bytes: float) -> int:
    """Square spatial tile side from a byte budget and the full accounting.

    Floors rather than rounds: rounding up overcommits a hard memory budget by
    a full tile row, and the 16 GB constraint is hard.

    **THIS DIVIDES WHAT IT IS GIVEN BY THE PER-SERIES COST AND SUBTRACTS
    NOTHING** -- not the process floor, not the headroom, not
    `solver_state_bytes`. **`tiling.tile_side_for` is what does all three** and
    has since Phase 2b Task 2 closed F1: it passes `block - solver_state` in
    here, where `block = (budget - floor) x (1 - headroom)`. So a caller that
    hands this function a whole budget gets an **upper bound** on the side and
    not a budget-safe number, which is what `batch.validation`'s per-point
    refusal does deliberately and says so.

    Args:
        budget_bytes: Memory budget for one tile.
        per_series_bytes: From `resident_bytes_per_series`, or a **measured**
            slope out of `calibrate`, which is a float. Neither is checked here
            -- `tiling.tile_side_for` is the caller that owns the seam and the
            guard on it.

    Returns:
        Tile side in grid points.

    Raises:
        ValueError: If the budget does not hold at least one series. A side of
            0 is a plausible-looking number that holds no data, so the caller
            would loop making no progress rather than see the problem.
    """
    side = int(math.floor(math.sqrt(budget_bytes / per_series_bytes)))
    if side < 1:
        raise ValueError(
            f"budget of {budget_bytes} B does not hold one series at "
            f"{per_series_bytes} B/series"
        )
    return side


def default_budget_gb() -> float:
    """Return the budget a configuration that names none resolves to.

    `DEFAULT_BUDGET_FRACTION` of **total** RAM, in SI gigabytes, read through
    `machine.total_ram_bytes` so a container gets a fraction of its **allowance**
    rather than of the host. See `DEFAULT_BUDGET_FRACTION` for why the reading is
    total rather than available, and for the figure the fraction was checked
    against.

    **THE ANSWER IS A PROPERTY OF THE MACHINE, SO THE SAME CONFIG FILE RESOLVES
    DIFFERENTLY ON TWO BOXES** -- and therefore hashes differently into
    `run_hash`. That is correct rather than nondeterministic: `run_hash` records
    what the run used, and the run used what the machine gave it. It is also
    already true of `run_hash` through `machine.fingerprint()`, whose RAM
    component this shares.

    Returns:
        The budget in SI gigabytes, as `memory_budget_gb` would hold it.
    """
    return machine.total_ram_bytes() * DEFAULT_BUDGET_FRACTION / 10**9


def data_and_workspace_bytes_per_series(d: int, k_beta: int, n_time: int) -> int:
    """The instrument's floor: what ONE BATCHED EVALUATION holds per series.

    **THIS IS NOT THE PRODUCTION PER-SERIES COST AND MUST NOT BE COMPARED
    AGAINST ONE.** `measure_evaluation_rss_slope` drives
    `objective.unconstrained_loglik` on a **batch of B**, which genuinely does
    hold `B * (6d^2 + ...)`; `run()` drives `fit`, which hands the engine one
    series at a time, so those blocks are a constant there. The two disagree by
    approximately `_engine_workspace_bytes(d, k_beta)` per series **by
    construction**, and that disagreement is the measurement of the deleted
    per-series solver term's magnitude -- **a quantity to state in advance, not
    a discrepancy to reconcile.**

    This function is the right floor **for the instrument**, which is why it
    survives: Task 7 uses it as the cross-check.

    **This was 31 542 B/series until 2026-08-10 and is 6550 at the
    configuration `measure_evaluation_rss_slope` actually drives** -- d = 3,
    **k_beta = 6**, N = 630 -- because 25 200 of it was a materialized
    augmented block. Measured against it, the slope of resident RSS on batch
    size went from 43 392 to **8471**, a ratio to the floor of **1.293** --
    inside `slope_band`, and that agreement was read for four months as
    confirming a formula the instrument never exercised.

    > **THE PROSE HERE SAID 6382 UNTIL 2026-08-16, AND THAT IS THIS FUNCTION AT
    > `k_beta = 4` WHILE THE INSTRUMENT RUNS `k_beta = 6`.** `_CHILD` builds
    > `SignalSpec([Constant, Trend, Annual, SemiAnnual])`, which is **six**
    > design columns, not section 9.4's four -- so the floor the instrument
    > should be measured against is **6550**, and the recorded ratio is
    > **1.293** rather than 1.33.
    >
    > **AND THE FIRST CORRECTION OF THIS WAS ITSELF WRONG, WHICH IS WHY IT IS
    > WRITTEN OUT.** It read *"the difference is exactly
    > `augmented_state = 3*7*8 = 168`, the term Task 0 added"* -- a number
    > matched to a term and a conclusion drawn from the match. The 168 is the
    > `k_beta` 4-to-6 delta spread across **three** terms (augmented +48,
    > accumulators +104, reused row +16) and it merely **coincides** with
    > `augmented_state` at k = 6. **(a4)'s third register: a correction arrives
    > with the authority of the error it just exposed, and its own arithmetic is
    > the least likely to be checked.**

    **AND IT IS A FLOOR AT N = 630 AND NOT AT N = 60. MEASURED, 2026-08-16, ON
    THIS MACHINE**, `measure_evaluation_rss_slope((0, 512, 1024, 2048))`:

    | N | measured | this function at k_beta = 6 | ratio | inside `slope_band`? |
    |---|---|---|---|---|
    | 630 | 9286 B/series | 6550 | 1.418 | yes |
    | 60 | 4036 B/series | 1420 | **2.842** | **no** |

    **The excess is ~2.7 kB/series and does not depend on N at all** (+2736 and
    +2616), so it is invisible where `n_time*9` is large and dominant where it
    is not -- (a)'s cancellation rule at a parameter value, since a term is
    checked by a measurement at a **second** parameter value and by nothing
    else. **The uncharged term belongs to `unconstrained_loglik`'s working set
    and moves no tile side**, which is why Phase 2b Task 7 recorded it rather
    than chasing it; see `PROGRESS.md`'s open questions. **Do not quote this
    function as the instrument's floor at short series.**

    Args:
        d: Composite state dimension.
        k_beta: Number of design columns.
        n_time: Series length.

    Returns:
        Bytes per series for the data tile plus engine workspace, under a
        batched evaluation.
    """
    return int(n_time * 9 + _engine_workspace_bytes(d, k_beta))


@dataclass(frozen=True)
class FloorReport:
    """What a process holds before a tile exists, measured rather than assumed.

    **THIS IS THE TERM F1 SAID NOBODY HAD.** `--memory-budget` bounds process
    peak RSS, so `block_bytes = budget - floor - headroom` and the floor has to
    be a number rather than an argument. Measured 2026-08-14, MB, current RSS:

        interpreter + numpy                          73.8
        + xarray, zarr                              162.4   (+88.6)
        + metamer.batch.run                         170.7   (+8.3)   pre-warm
        + numba imported, threading layer launched  213.9   (+43.2)
        + Kalman kernel warm                        221.5   (+7.6)   post-warm
        + compiled kernel JIT-compiled              264.3   (+42.8)

    Re-measured 2026-08-15 by this probe, MB: 74.0 / 163.0 / 171.2 / 214.4 /
    **216.9**, with the input open at 228.2 and a peak of 228.2. The first four
    rungs reproduce to under 1%. **The warm rung does not, and the reason is the
    instrument rather than the machine**: this probe warms with a one-series
    `white` fit at N=16, which is the smallest thing that drives
    `KalmanEngine.score` end to end, while the 2026-08-14 ladder's warm was a
    heavier spec. **So `post_warm_bytes` is a LOWER BOUND on the post-warm
    floor** -- stated rather than tuned, because tuning a warm until it
    reproduces a recorded number measures the tuning.

    **AN IMPORT-TIME FLOOR UNDERSTATES BY 50.8 MB -- 30%.** Task 5 established
    that numba's threading layer is invisible to `threadpool_info()` until
    something parallel has run; **its residency is invisible for the same
    reason**, and this ladder is the measurement of it.

    **THE PRODUCTION FLOOR IS THE POST-WARM ONE, NOT THE COMPILED-KERNEL ONE**,
    because under F4 production never reaches the compiled kernel. **That is a
    claim about F4**, pinned by `test_memory.py`'s reachability assertion, so
    the two move together the day a batched driver lands.

    **numba's 43.2 MB is a measured, accepted cost and is NOT TO BE "FIXED".**
    It buys the layer-3 determinism precondition, which cannot be observed until
    the layer has launched. Recorded with its justification, or someone reclaims
    a fifth of the floor and silently loses the check.

    Attributes:
        pre_warm_bytes: Current RSS after the imports and before numba's
            threading layer -- what an import-time floor would have recorded.
        post_warm_bytes: Current RSS after the layer has launched and the Kalman
            kernel has run. **The production floor.**
        with_input_bytes: Current RSS after the input is open and one chunk has
            been read. A zarr store's handles, consolidated metadata and
            decompression buffers are resident and scale with the store rather
            than with the tile; measuring before the open attributes them to the
            tile term and makes `tile_side` wrong in the **unsafe** direction.
        peak_bytes: The child's own high-water mark across the whole ladder,
            floored at the largest rung. **THIS IS WHAT TASK 2 SUBTRACTS FROM
            THE BUDGET, AND IT IS A DIFFERENT INSTRUMENT FROM THE ROWS ABOVE.**
            Exit criterion 7 asserts *peak* RSS, so what must come out of the
            budget is the peak of everything that is not the tile -- import
            transients, numba's JIT, zarr's first-chunk buffers. The current-RSS
            ladder omits exactly those, and budgeting against it overcommits by
            their size. The ladder stays in current RSS because that is the
            series the recorded figures are in and the only one comparable to
            them. **The `max` against the ladder is load-bearing**: `ru_maxrss`
            is updated lazily and was measured here at 227.7 MB against a
            current 228.2 MB read an instant earlier, so the watermark alone can
            report less than the process demonstrably held.
        components: The whole ladder, rung by rung, so the 30% gap is legible in
            a store rather than only in this docstring.
    """

    pre_warm_bytes: int
    post_warm_bytes: int
    with_input_bytes: int
    peak_bytes: int
    components: Mapping[str, int]


_FLOOR_CHILD = """
import json
from metamer.core.machine import current_rss_bytes, peak_rss_bytes

uri, variable = {uri!r}, {variable!r}
rungs = {{}}

import numpy as np
rungs["interpreter_numpy"] = current_rss_bytes()

import xarray, zarr
rungs["xarray_zarr"] = current_rss_bytes()

import metamer.batch.run
rungs["metamer_batch_run"] = current_rss_bytes()
pre_warm = rungs["metamer_batch_run"]

# THE LAYER IS LAUNCHED THROUGH A PUBLIC CALL, not by importing numba. Task 5:
# `threadpool_info()` sees OpenBLAS alone until a prange function has executed,
# and `get_num_threads()` is what starts the runtime.
import numba
numba.get_num_threads()
rungs["numba_threading_layer"] = current_rss_bytes()

# The KALMAN kernel, deliberately, and NOT the compiled one: under F4 production
# never reaches `CompiledEngine`'s JIT, which costs a further 42.8 MB.
from metamer.core.capability import Objective
from metamer.core.engines.kalman import KalmanEngine
from metamer.core.objective import ConcentratedObjective
from metamer.core.registry import kernel_registry
from metamer.core.signal import Constant, SignalSpec, Trend
from metamer.core.statespace import StateSpace
from metamer.core.terms import ProcessSpec, TermSpec, free_param_index

family = kernel_registry["white"]()
spec = ProcessSpec((TermSpec("white", family.param_specs(),
                             getattr(family, "ordering_param", None)),))
signal = SignalSpec([Constant(), Trend()])
warm_n = 16
warm_t = np.arange(warm_n, dtype=np.float64) / 12.0
warm_y = np.zeros((1, warm_n))
warm_mask = np.ones_like(warm_y, dtype=bool)
objective = ConcentratedObjective(
    spec, StateSpace.from_spec(spec), KalmanEngine(), Objective.ML
)
objective.unconstrained_loglik(
    np.zeros((1, len(free_param_index(spec)))),
    warm_y, warm_mask, warm_t, signal.design_info(warm_t, warm_mask),
)
rungs["kalman_kernel_warm"] = current_rss_bytes()
post_warm = rungs["kalman_kernel_warm"]

from metamer.batch.input import open_input
handle = open_input(uri, variable)
array = handle.dataset[handle.variable]
# ONE CHUNK, not the whole variable: what is being measured is the store's
# resident overhead, and reading everything would measure the data instead.
array.isel({{dim: 0 for dim in array.dims[1:]}}).values
rungs["input_open"] = current_rss_bytes()

# `max` WITH THE LADDER, AND IT IS NOT BELT-AND-BRACES. `ru_maxrss` is
# `mm->hiwater_rss` and the kernel updates it LAZILY -- measured here, 227.7 MB
# against a current 228.2 MB read an instant earlier, and measured before at
# 470.8 against 471.3. So the watermark can sit BELOW a current reading taken
# from the same process, and a floor that trusted it alone would subtract less
# than the process demonstrably held.
peak = max([peak_rss_bytes()] + list(rungs.values()))

print(json.dumps({{"pre_warm": pre_warm, "post_warm": post_warm,
                   "with_input": rungs["input_open"],
                   "peak": peak,
                   "components": rungs}}))
"""


_BARE_LAUNCHER = """
import subprocess, sys
# IMPORTS NOTHING LARGE, ON PURPOSE. `peak_rss_bytes` is inherited across
# fork/exec -- the parent's OWN high-water, and the inheritance does not compound
# -- so a probe spawned straight from a large process reports that process's
# watermark. This one exists solely to break the chain: its own high-water is a
# bare interpreter, so the probe below starts from a known floor whatever the
# caller has allocated. Load-bearing only for `peak`; the current-RSS ladder is
# not a watermark and is not contaminated either way.
out = subprocess.run([sys.executable, "-c", {probe!r}], capture_output=True,
                     text=True)
sys.stdout.write(out.stdout)
sys.stderr.write(out.stderr)
sys.exit(out.returncode)
"""


def measure_floor(*, data_uri: str, variable: str) -> FloorReport:
    """Measure this release's process floor, with the input open.

    **MEASURED FRESH EVERY RUN AND NEVER CACHED**, which is a decision rather
    than an omission. Its two parts are cheap -- one child process, one open,
    one chunk read -- and their dependencies are the hardest thing in this
    project to key on: the input's contribution depends on the **chunk grid**,
    which Task 11's (a1) sweep classified as read back from the store rather
    than hashed. Keying on it would invent a gate the project deliberately does
    not have. **An uncached quantity has no staleness failure mode**, and that is
    the whole argument.

    Args:
        data_uri: The input to open, so its resident cost is inside the floor.
        variable: Which variable to read one chunk of.

    Returns:
        A `FloorReport`.

    Raises:
        RuntimeError: If the probe fails, with its stderr attached -- including
            when the input cannot be opened, since the open happens inside the
            child. **A silent zero here is a floor of nothing**, which reads as
            "the whole budget is available to the tile" and is a plausible
            number rather than an error.
    """
    probe = _FLOOR_CHILD.format(uri=data_uri, variable=variable)
    # S603: the argv is this module's own template with the configured URI and
    # variable substituted in as Python literals, run under this interpreter.
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", _BARE_LAUNCHER.format(probe=probe)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"the floor probe failed for {data_uri!r} / {variable!r}: {result.stderr}"
        )
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    return FloorReport(
        pre_warm_bytes=int(payload["pre_warm"]),
        post_warm_bytes=int(payload["post_warm"]),
        with_input_bytes=int(payload["with_input"]),
        peak_bytes=int(payload["peak"]),
        components={name: int(value) for name, value in payload["components"].items()},
    )


_CHILD = """
import json, threading, time
import numpy as np
from metamer.core.capability import Objective
from metamer.core.engines.kalman import KalmanEngine
from metamer.core.machine import current_rss_bytes, peak_rss_bytes
from metamer.core.objective import ConcentratedObjective
from metamer.core.registry import kernel_registry
from metamer.core.signal import Annual, Constant, SemiAnnual, SignalSpec, Trend
from metamer.core.statespace import StateSpace
from metamer.core.terms import ProcessSpec, TermSpec, free_param_index

batch, n_time = {batch}, {n_time}


def _term(kind):
    family = kernel_registry[kind]()
    return TermSpec(kind, family.param_specs(), getattr(family, "ordering_param", None))


# Sample RESIDENT size during the evaluation and keep the maximum. Reading it
# once at the end misses the peak entirely -- the engine's working set is local
# to `score` and is freed the moment it returns -- and reading `ru_maxrss`
# instead reports whatever high-water mark this process inherited from its
# parent across fork/exec.
high = [current_rss_bytes()]
stop = threading.Event()


def _sample():
    while not stop.is_set():
        high[0] = max(high[0], current_rss_bytes())
        time.sleep(0.002)


spec = ProcessSpec((_term("white"), _term("matern12"), _term("matern32")))
signal = SignalSpec([Constant(), Trend(), Annual(), SemiAnnual()])
objective = ConcentratedObjective(
    spec, StateSpace.from_spec(spec), KalmanEngine(), Objective.ML
)
# Decimal years -- 630 monthly samples is 52.5 yr, and Annual/SemiAnnual
# already default to 1.0 and 0.5 in those units.
t = np.arange(n_time, dtype=np.float64) / 12.0
baseline = current_rss_bytes()
sampler = threading.Thread(target=_sample, daemon=True)
sampler.start()
if batch:
    y = np.random.default_rng(0).standard_normal((batch, n_time))
    mask = np.ones_like(y, dtype=bool)
    design = signal.design_info(t, mask)
    u = np.zeros((batch, len(free_param_index(spec))))
    objective.unconstrained_loglik(u, y, mask, t, design)
    high[0] = max(high[0], current_rss_bytes())
stop.set()
sampler.join()
print(json.dumps({{"baseline": baseline, "peak": high[0],
                  "watermark": peak_rss_bytes()}}))
"""


def _measure_child(batch: int, n_time: int = 630) -> dict[str, float]:
    """Run one batched evaluation in a fresh process, returning its RSS report.

    Returns both instruments so a caller can see the contamination directly:
    `peak` is resident set size (not a watermark, not inherited) and
    `watermark` is `ru_maxrss` (a watermark, and inherited from the parent
    across fork/exec).

    Args:
        batch: Series in the tile. Zero measures the import-only baseline.
        n_time: Series length.

    Returns:
        Mapping with `baseline`, `peak` and `watermark`, all in bytes.

    Raises:
        RuntimeError: If the child fails, with its stderr attached -- a silent
            zero here would look like a perfectly flat memory curve, which is
            indistinguishable from a formula that predicts nothing.
    """
    code = _CHILD.format(batch=batch, n_time=n_time)
    # S603: the argv is this module's own template with two integers
    # substituted in, run under this interpreter. No external input reaches it.
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise RuntimeError(f"peak-RSS child failed for batch={batch}: {result.stderr}")
    return {
        key: float(value)
        for key, value in json.loads(result.stdout.strip().splitlines()[-1]).items()
    }


def _measure_one(batch: int, n_time: int) -> float:
    """Run one batched evaluation in a fresh process, returning peak RSS.

    Args:
        batch: Series in the tile. Zero measures the import-only baseline.
        n_time: Series length.

    Returns:
        Peak RSS of the child process, in bytes.

    Raises:
        RuntimeError: If the child fails, with its stderr attached -- a silent
            zero here would look like a perfectly flat memory curve, which is
            indistinguishable from a formula that predicts nothing.
    """
    return _measure_child(batch, n_time)["peak"]


def measure_evaluation_rss_slope(
    batches: tuple[int, ...], n_time: int
) -> tuple[float, float]:
    """Measure bytes-per-series as the slope of peak RSS against batch size.

    **THE WORKLOAD IS A BATCHED EVALUATION, NOT A FIT.** Its oracle is
    `data_and_workspace_bytes_per_series`; see that function for why it is not
    the production per-series cost and what the two are expected to disagree by.

    **The formula's claim is about the gradient, not the absolute peak.** A
    process carries a large per-run constant -- interpreter, numpy, imports --
    that is real and is not per-series. Fitting a line separates the two and
    compares the formula against the quantity it actually asserts.

    Each batch runs in a **fresh subprocess**, because `ru_maxrss` is a
    high-water mark that never decreases: two readings in one process are not
    comparable unless the later allocation exceeds every earlier one. That is
    pre-flight (k) -- a quantity whose meaning depends on process-local state.

    Args:
        batches: Batch sizes to measure, at least two and ideally three.
        n_time: Series length.

    Returns:
        `(slope_bytes_per_series, intercept_bytes)`.

    Raises:
        ValueError: If fewer than two batch sizes are given, since a slope
            needs two points.
    """
    if len(batches) < 2:
        raise ValueError(f"need at least two batch sizes to fit a slope, got {batches}")
    import numpy as np

    sizes = np.asarray(batches, dtype=np.float64)
    peaks = np.asarray(
        [_measure_one(int(b), n_time) for b in batches], dtype=np.float64
    )
    slope, intercept = np.polyfit(sizes, peaks, 1)
    return float(slope), float(intercept)


CALIBRATION_LADDER: tuple[int, ...] = (16, 32, 48, 64)
"""POLICY. The tile SIDES a calibration measures, in points.

**SIDES AND NOT SERIES, BECAUSE A RUN'S BATCH IS A TILE.** `B = side**2`, and
since Phase 2b Task 2 every derived side is a multiple of
`store.TILE_SIDE_BASE` = 16 -- so the reachable batches are
`{256, 1024, 2304, 4096, ...}` and the brief's `B in {1000, 2000, 4000}` names
three batches no tile can have (`sqrt(1000) = 31.6`). A ladder in series would
have to bypass the tiling to hit its own points, which is (j2) and is the
defect this whole task exists not to repeat.

**FOUR POINTS, BECAUSE THREE FIT A LINE THROUGH ONE RESIDUAL** and one residual
cannot falsify linearity -- it can only fail to notice. The four are equally
spaced in side, which is quadratic in B, so the top point carries most of the
leverage; that is deliberate, since the top point is also the only one whose
signal clears the noise floor at small per-series costs.

**THE COST IS THE FIT, NOT THE MEMORY, AND IT IS THE BINDING CONSTRAINT.**
Measured 2026-08-15 on this machine, `fit` at `max_iter=1` over two candidates:
**197 ms/series at N = 60** and **741 ms/series at N = 240** -- linear in N, flat
in B, and only **11.8x** cheaper than the converged cap rather than free, because
the init ladder and the gradient are paid whatever the cap is. This ladder is
**7680 series**, so at design doc section 9.4's configuration (N = 630, M = 12,
extrapolated at 12.4 s/series) it is **~26.5 h here**.

**AND THE REFRAMING THAT MAKES THAT ACCEPTABLE IS ARITHMETIC.** 7680 capped
series is about **649 converged-series-equivalents**, against **one** production
tile at `tiling.PUBLISHED_TILE_SIDE.shared` -- 272 when this was written, so
**73 984** series -- and the whole ladder is **0.88% of a single tile**, and a
run has thousands of them. **The percentage moves with the record**; the
conclusion survives any side this project has published. Cheap against the job it sizes;
expensive in absolute terms on a four-core box. Both are true and the second is
the one that surprises people.
"""


@dataclass(frozen=True)
class CalibrationPoint:
    """One ladder point: what was asked for, what ran, and what it held.

    Attributes:
        side: The tile side this point targeted.
        derived_side: The side the run actually derived from the budget it was
            given. **Equal to `side` unless the inverse is wrong**, and it is
            recorded rather than assumed because the budget was chosen with
            `resident_bytes_per_series` -- the quantity under calibration. The
            fit uses `batch`, computed from this, so a wrong analytic formula
            moves the ladder rather than corrupting the slope.
        batch: Series in the first tile, `min(side, n_y) * min(side, n_x)`.
            **The first tile, not `side**2`**: a grid smaller than the side is
            clipped, and the calibration stops after one tile.
        peak_bytes: Maximum resident set size sampled during the run.
        baseline_bytes: Resident set size before the run started.
        ok: Fits that came back `OK`. **The control for which regime this point
            is in**: at a cap of 1 or 2 it is zero, and a nonzero count means
            the four allocation sites `fit.py` skips on a non-OK outcome were
            reached.
        attempted: Fits that were attempted at all.
    """

    side: int
    derived_side: int
    batch: int
    peak_bytes: float
    baseline_bytes: float
    ok: int
    attempted: int


@dataclass(frozen=True)
class CalibrationResult:
    """A measured per-series cost, with everything needed to judge it.

    **THE INTERCEPT IS NOT THE PRODUCTION FLOOR AND MUST NOT BE READ AS ONE.**
    It is the floor under the *calibration's* conditions: the pinned floor, plus
    what the measuring child holds and a production run does not -- the sampling
    thread, the temporary store, the JSON payload -- minus the four allocation
    sites a capped fit never reaches (`theta`'s write, the Hessian inverse, the
    delta-method covariance, and the second evaluation at the optimum). Every
    one of those is shape `(1, ...)` inside `fit`'s per-series loop, so they are
    **constants rather than slope terms** and they belong here rather than in
    `slope_bytes_per_series`.

    Attributes:
        slope_bytes_per_series: The measured per-series cost, in bytes.
        intercept_bytes: The fitted intercept. See above for what it is of.
        residuals: Measured peak minus fitted peak, per ladder point, in bytes.
            **Reported rather than reduced to one number**, because the question
            the ladder answers is whether the relation is linear and a single
            residual norm cannot say where it is not.
        points: The ladder, in the order measured.
        max_iter: The cap every point ran under.
        linearity_basis: What the slope is licensed to be extrapolated over,
            stated because the ladder is small: the sides measured, and the fact
            that linearity **beyond** them is Task 7's claim and not this one's.
        placement: Where the live solver working set sat.
        engine_label: Which engine's workspace the number belongs to. **Not
            `EngineId`** -- see `MemoryEngineLabel`.
        floor_peak_bytes: The pinned floor every point ran against, so the
            intercept is comparable to something.
    """

    slope_bytes_per_series: float
    intercept_bytes: float
    residuals: tuple[float, ...]
    points: tuple[CalibrationPoint, ...]
    max_iter: int
    linearity_basis: str
    placement: SolverPlacement
    engine_label: MemoryEngineLabel
    floor_peak_bytes: int


_CALIBRATION_GEOMETRY_CHILD = """
import json
from metamer.batch.input import check_contract, open_input
from metamer.batch.run import run_geometry
from metamer.batch.tiling import budget_bytes_for_side
from metamer.batch.validation import load_config
from metamer.core.memory import FloorReport

floor = FloorReport(pre_warm_bytes={peak}, post_warm_bytes={peak},
                    with_input_bytes={peak}, peak_bytes={peak}, components={{}})
config = load_config({config_path!r})
handle = open_input(config.data_uri, config.variable)
contract = check_contract(handle)
model = run_geometry(config, handle, contract).tile_kwargs()

# THE BUDGET PER SIDE, COMPUTED WHERE THE PRODUCTION GEOMETRY IS, AND IN A
# PROCESS THAT MEASURES NOTHING. Doing it inside the measuring child would put
# an extra open input and a second parse inside the number being measured.
print(json.dumps({{
    "budgets": {{str(side): budget_bytes_for_side(side=side, floor=floor, **model)
                 for side in {ladder!r}}},
    "n_y": contract.n_y, "n_x": contract.n_x, "model": model,
}}))
"""


_CALIBRATION_CHILD = """
import json, os, shutil, signal, tempfile, threading, time
from metamer.core.machine import current_rss_bytes, peak_rss_bytes
from metamer.core.memory import FloorReport

peak_value = {peak}
floor = FloorReport(pre_warm_bytes=peak_value, post_warm_bytes=peak_value,
                    with_input_bytes=peak_value, peak_bytes=peak_value,
                    components={{}})

# **THE SAMPLER IS NOT LOAD-BEARING HERE TODAY, AND SAYING SO IS THE POINT.**
# `_CHILD` above samples because a batched evaluation's working set is freed
# the moment `score` returns, so a reading taken afterwards misses the peak
# entirely. A tile is different: `run()` still holds the block and the fit
# results in its frame when it returns, so an end-of-run reading is very nearly
# the peak. Measured -- a sampler that records nothing leaves every assertion in
# `tests/test_memory.py` green, which is (i8)'s third shape: the fault class is
# not constructible at the scales this suite can afford. It stays because it
# costs nothing and because the regime it guards is Task 8's, where the tile
# dominates the floor rather than the other way round.
high = [current_rss_bytes()]
stop = threading.Event()


def _sample():
    while not stop.is_set():
        high[0] = max(high[0], current_rss_bytes())
        time.sleep(0.002)


# IMPORTED INSIDE THE MEASURED PROCESS, deliberately: the run's imports are part
# of what a production process holds, and the floor this is compared against was
# measured the same way.
from metamer.batch.run import run

baseline = current_rss_bytes()
workspace = tempfile.mkdtemp(prefix="metamer-calibration-")
sampler = threading.Thread(target=_sample, daemon=True)
sampler.start()
try:
    # **ONE TILE, AND THE INSTRUMENT THAT STOPS IT IS THE PREEMPTION PATH.**
    # `run()` loops every tile, so on the grid a calibration exists to size this
    # would fit all of it. `on_tile_written` fires between a tile's data write
    # and its completion bit, and the loop already stops after a marked tile
    # when a SIGTERM has been recorded -- so raising the signal here needs no
    # new seam and puts no branch in the tile loop. (j3): an existing feature is
    # an instrument for a property its own purpose does not concern.
    report = run(
        {config_path!r},
        os.path.join(workspace, "calibration.zarr"),
        memory_budget_gb={budget} / 10 ** 9,
        floor=floor,
        max_iter={max_iter},
        on_tile_written=lambda tile: os.kill(os.getpid(), signal.SIGTERM),
    )
    high[0] = max(high[0], current_rss_bytes())
    stop.set()
    sampler.join()

    import zarr
    outcome = zarr.open_group(
        os.path.join(workspace, "calibration.zarr"), mode="r"
    )["status"]["outcome"][:]
    side = int(report.tile_side)
    print(json.dumps({{
        "derived_side": side,
        "batch": min(side, report.contract.n_y) * min(side, report.contract.n_x),
        "peak": high[0],
        "baseline": baseline,
        "watermark": peak_rss_bytes(),
        "ok": int((outcome == 0).sum()),
        "attempted": int((outcome != 8).sum()),
    }}))
finally:
    stop.set()
    shutil.rmtree(workspace, ignore_errors=True)
"""


def _run_child(source: str, *, what: str) -> dict[str, Any]:
    """Run one probe behind the bare launcher and return its JSON payload.

    Args:
        source: The probe's source.
        what: What the probe was measuring, for the failure message.

    Returns:
        The parsed payload.

    Raises:
        RuntimeError: If the probe fails, with its stderr attached. **A silent
            zero here is a perfectly flat memory curve**, which is
            indistinguishable from a formula that predicts nothing.
    """
    # S603: the argv is this module's own template with literals substituted in,
    # run under this interpreter.
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", _BARE_LAUNCHER.format(probe=source)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"the calibration probe failed for {what}: {result.stderr}")
    payload: dict[str, Any] = json.loads(result.stdout.strip().splitlines()[-1])
    return payload


def _budgets_for(
    config_path: str, floor: FloorReport, ladder: tuple[int, ...]
) -> dict[str, Any]:
    """Return the budget landing on each side, from the production geometry.

    Args:
        config_path: The configuration being calibrated.
        floor: The pinned floor.
        ladder: The tile sides wanted.

    Returns:
        The geometry child's payload: budgets by side, and the grid it read.

    Raises:
        RuntimeError: If the probe fails, with its stderr attached.
    """
    return _run_child(
        _CALIBRATION_GEOMETRY_CHILD.format(
            config_path=config_path, peak=floor.peak_bytes, ladder=list(ladder)
        ),
        what="the ladder's budgets",
    )


def _measure_point(
    *, config_path: str, side: int, budget: int, floor: FloorReport, max_iter: int
) -> CalibrationPoint:
    """Measure one tile's peak residency in a fresh child.

    Args:
        config_path: The configuration being calibrated.
        side: The tile side this point targets.
        budget: The budget that lands on that side.
        floor: The pinned floor, passed to `run()` so the side is deterministic.
        max_iter: The iteration cap.

    Returns:
        The measured point.

    Raises:
        RuntimeError: If the probe fails, with its stderr attached.
    """
    payload = _run_child(
        _CALIBRATION_CHILD.format(
            config_path=config_path,
            peak=floor.peak_bytes,
            budget=budget,
            max_iter=max_iter,
        ),
        what=f"tile side {side}",
    )
    return CalibrationPoint(
        side=side,
        derived_side=int(payload["derived_side"]),
        batch=int(payload["batch"]),
        peak_bytes=float(payload["peak"]),
        baseline_bytes=float(payload["baseline"]),
        ok=int(payload["ok"]),
        attempted=int(payload["attempted"]),
    )


def measure_tile_peak(
    *, config_path: str, side: int, floor: FloorReport, max_iter: int = 1
) -> CalibrationPoint:
    """Measure ONE tile's peak residency, at one side and one cap.

    **`calibrate` IS THIS IN A LOOP PLUS A LINE FIT**, and the two questions are
    separate: a ladder answers *"how many bytes per series"*, while a single
    point at a fixed side answers *"does this cap change what the process
    holds"*. The step test needs the second and would otherwise have to run a
    two-point ladder to get one number, paying for a point it never reads.

    Args:
        config_path: The configuration to measure against.
        side: The tile side. It must be reachable -- below
            `store.TILE_SIDE_BASE` any side is, at or above it only multiples.
        floor: The pinned floor.
        max_iter: The iteration cap. 1 by default.

    Returns:
        The measured point, including the `ok` count that says which regime it
        is in.

    Raises:
        RuntimeError: If either probe fails, with its stderr attached.
    """
    geometry = _budgets_for(config_path, floor, (side,))
    return _measure_point(
        config_path=config_path,
        side=side,
        budget=int(geometry["budgets"][str(side)]),
        floor=floor,
        max_iter=max_iter,
    )


def calibrate(
    *,
    config_path: str,
    floor: FloorReport,
    ladder: tuple[int, ...] = CALIBRATION_LADDER,
    max_iter: int = 1,
    placement: SolverPlacement = SolverPlacement.PER_SERIES_LIVE,
    engine_label: MemoryEngineLabel = MemoryEngineLabel.KALMAN_NUMPY,
) -> CalibrationResult:
    """Measure bytes per series by running the production path, capped.

    **THE INSTRUMENT IS `run()` ITSELF** -- same entry point, same budget
    derivation, same tile loop, same batch shape -- with the optimizer's
    iteration cap lowered. A purpose-built harness would approximate the tile
    loop and then validate the approximation, which is (j2) and is exactly the
    defect F2 already was: the measurement that validated the old formula drove
    a batched evaluation the production path never performs.

    **THE FLOOR IS PINNED ACROSS THE LADDER AND MEASURED ONCE.** The derived side
    is a function of the floor, which is measured fresh per run and varies by
    megabytes, while the budget window that selects one multiple of the base is
    narrower than that -- so an unpinned floor would land each point on a
    different side than the one it asked for.

    **EACH POINT RUNS IN A FRESH CHILD BEHIND THE BARE LAUNCHER**, because
    `peak_rss_bytes` is inherited across `fork`/`exec` and does not compound: a
    probe two processes below the caller starts from a known floor whatever the
    caller allocated. The child samples `current_rss_bytes` on a thread, since
    a tile's peak is transient and a reading taken at the end misses it.

    Args:
        config_path: The configuration to calibrate for. Its dataset, candidate
            set and objective are what the slope belongs to.
        floor: The pinned floor. Measure it once, with `measure_floor`.
        ladder: Tile sides to measure. Defaults to `CALIBRATION_LADDER`.
        max_iter: The iteration cap. **1 by default**, which is the cheapest
            point at which every allocation the tile loop makes has been made.
        placement: Recorded on the result; one value is reachable.
        engine_label: Recorded on the result. Not `EngineId`.

    Returns:
        The measured slope, intercept, residuals and ladder.

    Raises:
        ValueError: If the ladder has fewer than two points, since a slope needs
            two -- and fewer than four cannot falsify linearity, which the
            result says in its own `linearity_basis`.
        RuntimeError: If any probe fails, with its stderr attached.
    """
    if len(ladder) < 2:
        raise ValueError(f"a slope needs at least two ladder points, got {ladder}")

    import numpy as np

    budgets = _budgets_for(config_path, floor, ladder)["budgets"]

    points = [
        _measure_point(
            config_path=config_path,
            side=side,
            budget=int(budgets[str(side)]),
            floor=floor,
            max_iter=max_iter,
        )
        for side in ladder
    ]

    # THE FIT IS OVER THE ACHIEVED BATCH, NOT THE REQUESTED SIDE. The budget was
    # chosen with `resident_bytes_per_series`, which is the quantity being
    # calibrated, so a wrong analytic figure must move the LADDER and not the
    # answer -- that is what closes the circularity (j).
    batches = np.asarray([point.batch for point in points], dtype=np.float64)
    peaks = np.asarray([point.peak_bytes for point in points], dtype=np.float64)
    slope, intercept = np.polyfit(batches, peaks, 1)
    fitted = slope * batches + intercept
    return CalibrationResult(
        slope_bytes_per_series=float(slope),
        intercept_bytes=float(intercept),
        residuals=tuple(float(value) for value in peaks - fitted),
        points=tuple(points),
        max_iter=max_iter,
        linearity_basis=(
            f"measured at tile sides {tuple(point.derived_side for point in points)}, "
            f"i.e. batches {tuple(point.batch for point in points)}, at max_iter="
            f"{max_iter}. Linearity BEYOND this range is not established here: "
            "the slope is a per-series quantity and does not need production B, "
            "while the claim that it stays linear there is Task 7's."
        ),
        placement=placement,
        engine_label=engine_label,
        floor_peak_bytes=int(floor.peak_bytes),
    )
