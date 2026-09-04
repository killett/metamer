"""The 2d benchmark driver, and the report everything downstream asserts on.

Design doc §16.2 asks the simulation-recovery benchmark to *"emit a reproducible
report"*. **The report is the artifact and the driver is the thin part**: a
27-hour measurement cannot be a test, so Task 9's exit criteria assert against
the COMMITTED reports, and a report that cannot be checked against the
configuration that produced it is a number without an instrument.

## The instrument block is DERIVED, never transcribed

**Every value in it is read from the shipped constant it names, at call time.**
(j9)'s worst instance in this sub-phase was **an instrument block that was
itself a copy** -- the guard defeated by the defect it guards against -- so
nothing here is written twice. `instrument_block` reads `smear.ESTIMATOR`,
`fields.COARSE_STRIDE`, `WarmStart().spiral_bound`, `smear.spiral_reach_cells`,
`fields.CANDIDATES` and their `spec_hash`es, `ALGORITHM_VERSION`,
`fields.DRAW_METHOD` and the rung's own `sources`. **A test moves each of those
and asserts the block moves with it.**

**AND THE DRAW METHOD IS IN IT BECAUSE THE DRAWN BYTES ARE KEYED BY SEED AND
METHOD TOGETHER.** `build_field`'s call site records that a later change there
invalidates every committed rung report; a block carrying the seed alone
describes a field it cannot reproduce.

**WHAT THE BLOCK IS FOR:** Task 9 fails a committed report whose block no longer
matches current defaults. That is what stops a report outliving the
`spiral_bound` or `coarse_stride` that produced it -- **a recorded measurement is
a current claim only while the configuration that produced it is.**

## The null gate lives in the DRIVER, and the strong form is *not computed*

E6 makes the interior null the clause that gates the sub-phase: *"computed
first, as soon as any rung lands, before any smear number is read at all"*, and
*"if the null line returns a width, stop and diagnose the estimator rather than
proceeding"*.

**A reading that exists can be read**, so a report carrying a smear width beside
a `contaminated: true` flag has the number in it and the number is what travels.
**The ordering is therefore the mechanism rather than the flag:** the null is
taken first, and on contamination **the widths are never computed at all.** Their
quantities are withheld objects carrying the reason, and there is no hidden value
behind them because none was produced.

**THE GATE HAS TWO HALVES AT TWO LEVELS.** Within a rung, the ordering above.
Across rungs, `require_clean(report)` **raises** -- and Tasks 5 to 7 call it.
`run_rung` still RETURNS a contaminated report, deliberately: E6 says *stop and
diagnose*, and the diagnosis is made of the null's own profile. **What is refused
is proceeding, and it is refused by a separate callable rather than by a flag
someone must remember to read.**

## A floor reading and a withheld one are opposite claims

`Quantity` has two states -- a value, or a reason there is none. **A smear
reading has three**: a measured width; **at the floor**, which is a valid reading
with no number; and **refused or withheld**, which is no reading at all. Folding
the last two together makes *"the instrument looked and resolved nothing"*
indistinguishable from *"the instrument did not look"* -- (a0)'s
excluded-versus-missing register arriving at a report field.

**So the report carries the `WidthReading` beside the `Quantity`**, and the
reading's `at_floor` / `refused` / `cells` triple is what separates them. **The
profile travels either way**: Task 2's forfeit means the majority rule is blind
to a smear that never carries a cell past a half, so **a report recording
`<= 1 cell` without the profile has recorded nothing.**

## Reproducible bytes: iterations are in, seconds are out

The third rung's measurement put a number on the split. The same fixture
reproduced its **iteration counts to every digit** a day later while its
**seconds moved 15%** -- same host, same code, quiet in both runs. **So
iterations sit on the reproducible side of the line and seconds do not**, which
turns the byte-identity invariant from *"the numbers that happen not to be
timings"* into *"everything the run determines"*. The seconds are **reported and
never compared**, which is the phrase pass 2's own report already uses.

**And the cost block is derived from THIS run**, never transcribed from the
budget's rate: the budget is priced at the **cold** rate and is an upper bound,
so **a run finishing early is the bound behaving and not an error** -- a sentence
the report carries, because it is the artifact a reader meets.
"""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from metamer.batch.audit import Arm
from metamer.batch.audit_report import Quantity
from metamer.bench import fields, n2map, smear
from metamer.bench.arms import (
    arm_cost,
    iteration_ratio,
    same_iterations,
    self_arm,
    store_cost,
)
from metamer.bench.fields import FieldTruth, Rung
from metamer.bench.smear import WidthReading
from metamer.config.model import WarmStart
from metamer.core.criteria import Criterion
from metamer.core.fit import FitResult
from metamer.core.hashing import ALGORITHM_VERSION
from metamer.core.optimize import DEFAULT_MAX_ITER

#: The arms a rung's smear width can be read from. **`n2` is the FLOOR the
#: others are read against** -- a smear measured against zero is a different
#: claim from one measured against the width an equal-distance random start
#: produces.
ARMS: tuple[str, ...] = ("cold", "warm", "n2")

#: The name under which the interior null is reported.
NULL_QUANTITY: str = "interior null width"

#: What a smear quantity is called, per arm.
SMEAR_QUANTITY: str = "smear width"


class RungContaminated(Exception):
    """A rung whose interior null did not come back clean. The sub-phase stops."""


@dataclass(frozen=True)
class RungQuantity(Quantity):
    """A `Quantity` that cannot exist without the rung it was measured on.

    **THE SCOPE CHECK IS INHERITED AND NOT RE-WRITTEN.** `Quantity` already
    refuses a scopeless quantity and a half-stated one; re-implementing either
    here would be two spellings of one validator, drifting the first time one is
    edited. This adds one required field and nothing else.

    **E1's constraint 2 -- every emitted number carries its rung -- is therefore
    enforced by CONSTRUCTION rather than by convention.** A factory returning a
    plain `Quantity` with the rung folded into its scope string was considered
    and rejected: it makes the rule *"is not usually constructed without a
    rung"*, and D8's whole argument is that labelling a number does not stop it
    being quoted.

    Attributes:
        rung: The rung this number was measured on. Keyword-only, because
            `Quantity` ends in a defaulted field and a required positional
            cannot follow one.
    """

    rung: Rung = field(kw_only=True)


@dataclass(frozen=True)
class SmearEntry:
    """One arm's smear reading, and the quantity that reports it.

    Attributes:
        arm: Which arm the map came from.
        quantity: The reporting surface Task 9 asserts over.
        reading: The estimator's own reading, or **None when no width was
            computed at all** -- which is what a contaminated rung produces.
            **None here and a refused `WidthReading` are different facts**: the
            first says the estimator never ran, the second says it ran and would
            not answer.
    """

    arm: str
    quantity: RungQuantity
    reading: WidthReading | None


@dataclass(frozen=True)
class RungReport:
    """One rung, one report, self-describing by construction.

    A reader with this report and no other file can say which field, which rung,
    which instrument and which defaults produced every number.

    Attributes:
        rung: The rung.
        contaminated: The interior null did not come back clean -- it returned a
            width, or it could not be read. **Both stop the sub-phase**, and the
            null's own `refused` field says which.
        null_line: The interior null's reading. **Present on every report**,
            including a contaminated one, because E6 says *stop and diagnose* and
            the diagnosis is made of this.
        smears: One entry per arm, in `ARMS` order.
        instrument: What produced the numbers. See the module docstring.
        cost: Wall clock. **Reported and never compared**, and excluded from
            `reproducible()`.
        iterations: Iterations per arm. **Deterministic, so it is INSIDE
            `reproducible()`** -- measured 2026-08-31, the same fixture
            reproducing every digit a day later while its seconds moved 15%.
    """

    rung: Rung
    contaminated: bool
    null_line: WidthReading
    smears: tuple[SmearEntry, ...]
    instrument: Mapping[str, Any]
    cost: Mapping[str, float]
    iterations: Mapping[str, float]
    ratios: Mapping[str, float | None] = field(default_factory=dict)
    checks: Mapping[str, Any] = field(default_factory=dict)

    def quantities(self) -> tuple[RungQuantity, ...]:
        """Every quantity that carries a value."""
        return tuple(
            entry.quantity for entry in self.smears if entry.quantity.value is not None
        )

    def withheld(self) -> tuple[RungQuantity, ...]:
        """Every quantity withheld, each carrying its reason.

        **A withheld quantity is an object, not an absent field.** Silence and
        absence are the same bytes, so a report that omitted a contaminated
        rung's widths would be indistinguishable from one whose rung was never
        run -- and a reader supplies the more flattering of the two.
        """
        return tuple(
            entry.quantity for entry in self.smears if entry.quantity.value is None
        )

    def reproducible(self) -> Mapping[str, Any]:
        """Everything this run determines, with the wall clock left out.

        **Two runs of one rung must agree here byte for byte.** N2 is the only
        randomness in the system, so this is the one place §11.3's traversal
        independence can still be lost.
        """
        return {
            "rung": {
                "name": self.rung.name,
                "coherence_length": self.rung.coherence_length,
                "contrast": self.rung.contrast,
                "sources": dict(self.rung.sources),
            },
            "contaminated": self.contaminated,
            "null_line": _reading_record(self.null_line),
            "smears": [
                {
                    "arm": entry.arm,
                    "value": entry.quantity.value,
                    "withheld": entry.quantity.withheld,
                    "denominator": entry.quantity.denominator,
                    "reading": _reading_record(entry.reading),
                }
                for entry in self.smears
            ],
            "instrument": dict(self.instrument),
            "iterations": dict(self.iterations),
            "ratios": dict(self.ratios),
            "checks": dict(self.checks),
        }


def _reading_record(reading: WidthReading | None) -> Mapping[str, Any] | None:
    """A reading as plain data, profile included.

    **THE PROFILE IS NOT OPTIONAL.** A floor result is uninterpretable until its
    profile has been seen to be flat rather than sloped -- the majority rule is
    blind to a smear that never carries a cell past a half, and the profile is
    the only place such a band is visible.
    """
    if reading is None:
        return None
    return {
        "cells": reading.cells,
        "at_floor": reading.at_floor,
        "floor_cells": reading.floor_cells,
        "reach_cells": reading.reach_cells,
        "estimator": reading.estimator,
        "map_name": reading.map_name,
        "arm": reading.arm,
        "refused": reading.refused,
        "profile": list(reading.profile),
    }


@dataclass(frozen=True)
class Saving:
    """The warm-start saving, in iterations, with and without pass 1.

    **A READER MEANS THE NET ONE.** D11 gives pass 1 its own store, so a saving
    read off pass 2's store alone charges the coarse fits to nobody. The
    omission is small -- 8 coarse points of 384 on this geometry -- and it is
    **always in the flattering direction**, which is the combination that
    survives review.

    Attributes:
        pass2_only: `1 - pass2 / cold`. What the report's iteration entries say
            on their own.
        net: `1 - (pass1 + pass2) / cold`. **The saving.**
        cold_total: The reference arm's iterations.
        warm_total: Pass 2's.
        pass1_total: Pass 1's.
        refused: Why there is no saving, or None. **A zero cold total gives a
            refusal and not `1.0`** -- a 100% saving is the most quotable
            number this sub-phase could emit and it would come from a run that
            fitted nothing.
    """

    pass2_only: float | None
    net: float | None
    cold_total: int
    warm_total: int
    pass1_total: int
    refused: str | None


def saving(*, cold_total: int, warm_total: int, pass1_total: int) -> Saving:
    """The saving both ways, from three iteration totals.

    Args:
        cold_total: The cold arm's iterations.
        warm_total: Pass 2's iterations.
        pass1_total: Pass 1's iterations, which the net figure charges to the
            warm arm.

    Returns:
        The saving.
    """
    if cold_total <= 0:
        return Saving(
            pass2_only=None,
            net=None,
            cold_total=int(cold_total),
            warm_total=int(warm_total),
            pass1_total=int(pass1_total),
            refused=(
                "the cold arm took no iterations, so there is nothing to save "
                "against; a ratio here would report a 100% saving for a run "
                "that fitted nothing"
            ),
        )
    return Saving(
        pass2_only=1.0 - warm_total / cold_total,
        net=1.0 - (warm_total + pass1_total) / cold_total,
        cold_total=int(cold_total),
        warm_total=int(warm_total),
        pass1_total=int(pass1_total),
        refused=None,
    )


def instrument_block(
    rung: Rung,
    *,
    n_time: int,
    n_normal: int,
    n_parallel: int,
    seed: int,
    audit_seed: int = fields.AUDIT_SEED,
    warm: WarmStart | None = None,
    is_a_smoke_run: bool = False,
    construction_version: int | None = None,
) -> Mapping[str, Any]:
    """What produced the numbers, read from the shipped constants at call time.

    Args:
        rung: The rung, whose per-parameter `sources` go in whole.
        n_time: Record length this run used.
        n_normal: Cells across the boundary.
        n_parallel: Cells along it.
        seed: The field's base seed. **With `draw_method`, this is what keys the
            drawn bytes**; either alone does not.
        audit_seed: What the N2 arm's DIRECTIONS are keyed on --
            `config.audit.seed`, never the field's. **A block carrying only the
            field's seed describes a field it can rebuild and a floor arm it
            cannot**, and exit criterion 9 compares this map against the
            audit's own arm, which reads its seed from the config.
        warm: The warm-start settings to describe. Defaults to the shipped ones.
        is_a_smoke_run: **True marks a report that exercised the pipeline rather
            than measuring anything** -- a reduced geometry or record length.
            Task 9 must refuse such a report as a measurement, and the flag is
            in the block rather than in a filename because a filename does not
            travel with the bytes.
        construction_version: Which construction BUILT the field. Defaults to
            the shipped one. **A run that rebuilds an older construction must
            pass its own**, or the block describes the default that was current
            when the block was written rather than the field that was drawn --
            which is the transcription this block exists to prevent, arriving
            through a parameter instead of a literal.

    Returns:
        The block.
    """
    settings = WarmStart() if warm is None else warm
    version = (
        fields.FIELD_CONSTRUCTION_VERSION
        if construction_version is None
        else construction_version
    )
    return {
        "estimator": smear.ESTIMATOR,
        "smear_subject": fields.SMEAR_SUBJECT,
        "map_name": smear.AGREEMENT_MAP_NAME,
        "floor_cells": smear.FLOOR_CELLS,
        "majority_threshold": smear.MAJORITY,
        "reach_cells": smear.spiral_reach_cells(settings),
        "coarse_stride": fields.COARSE_STRIDE,
        "spiral_bound": settings.spiral_bound,
        "candidates": list(fields.CANDIDATES),
        "candidate_spec_hashes": [
            spec.spec_hash() for spec in fields.candidate_specs()
        ],
        "signal_terms": list(fields.SIGNAL_TERMS),
        # **`signal_terms` NAMES WHAT THE CONFIG FITS. THESE THREE NAME WHAT THE
        # BUILDER DRAWS.** They are separate keys, added 2026-09-03, and NOT a
        # redefinition of the one above: three committed reports carry
        # `signal_terms = constant, trend` over fields that had neither, and
        # redefining the key would REINTERPRET those artifacts where the whole
        # point is to DISTINGUISH them. A reader of an old report sees these
        # keys missing, which is the truthful answer to "which construction was
        # this?" -- the answer being "one from before the question existed".
        "field_construction_version": version,
        "drawn_signal_terms": list(fields.DRAWN_SIGNAL_TERMS),
        "drawn_signal_rise_sigmas": fields.SIGNAL_RISE_SIGMAS,
        "criteria": list(fields.CRITERIA),
        "algorithm_version": ALGORITHM_VERSION,
        "draw_method": fields.DRAW_METHOD,
        "seed": seed,
        "audit_seed": audit_seed,
        "n_time": n_time,
        "n_normal": n_normal,
        "n_parallel": n_parallel,
        "boundary_index": n_normal // 2,
        "null_line_offset_cells": fields.NULL_LINE_OFFSET_CELLS,
        "within_regime_range": fields.WITHIN_REGIME_RANGE,
        "rung_sources": dict(rung.sources),
        "is_a_smoke_run": is_a_smoke_run,
        "cost_is_an_upper_bound": (
            "the budget is priced at the COLD rate, so a run finishing early is "
            "the bound behaving and not an error"
        ),
    }


def null_is_clean(reading: WidthReading) -> bool:
    """Whether the interior null passed.

    **Clean means at the floor AND readable.** A refused null is not a null that
    fired, but it is equally not a null that passed: the estimator could not
    answer, so the rung is uncertified. Folding the two into "not clean" is
    correct; the reading's own `refused` field is what tells a diagnostician
    which happened.
    """
    return reading.at_floor and reading.refused is None


def contamination_reason(reading: WidthReading) -> str | None:
    """Why the rung is contaminated, or None when it is not."""
    if null_is_clean(reading):
        return None
    if reading.refused is not None:
        return (
            "the interior null could not be read, so this rung is uncertified: "
            f"{reading.refused}"
        )
    return (
        f"the interior null returned a width of {reading.cells} cells where the "
        "truth has no transition, so the profile estimator is measuring the "
        "field's own structure rather than the smear, and every smear number on "
        "this rung would be contaminated (E6's third row)"
    )


def build_report(
    rung: Rung,
    *,
    null_line: WidthReading,
    widths: Mapping[str, WidthReading],
    instrument: Mapping[str, Any],
    cost: Mapping[str, float],
    iterations: Mapping[str, float],
    denominator: int,
    arms: Sequence[str] = ARMS,
    ratios: Mapping[str, float | None] | None = None,
    checks: Mapping[str, Any] | None = None,
) -> RungReport:
    """Assemble one rung's report from readings that already exist.

    **PURE, AND THAT IS WHAT MAKES TASK 4 TESTABLE AT ALL.** Everything
    assertable about the report -- the gate's decision, the withholding, the
    reproducible/timing split, the rung on every quantity -- is a function of
    the readings, so it is tested on constructed ones rather than behind an
    hour-long run.

    Args:
        rung: The rung.
        null_line: The interior null's reading, taken FIRST.
        widths: One reading per arm. **Empty on a contaminated rung**, because
            the widths are never computed there.
        instrument: From `instrument_block`.
        cost: Wall clock per arm, in seconds.
        iterations: Iterations per point per arm.
        denominator: Points the widths were read over.
        arms: Which arms this rung ran.
        ratios: Deterministic cost ratios between arms -- N1 against cold,
            `self` against cold. **On the reproducible side**, because they are
            made of iterations.
        checks: The run's own cross-checks, each a fact the run determined.
            **Also reproducible**, and a check that moved between two runs of
            one rung is exactly what the byte-identity invariant is for.

    Returns:
        The report.

    Raises:
        ValueError: If a width is supplied for a contaminated rung. **That is a
            programming error rather than a data condition**: computing a width
            and then discarding it is exactly the "hidden value behind the flag"
            this design exists to prevent, so it is refused loudly.
    """
    reason = contamination_reason(null_line)
    contaminated = reason is not None
    if contaminated and widths:
        raise ValueError(
            f"rung {rung.name!r} is contaminated and was given "
            f"{sorted(widths)} anyway; on a contaminated rung the widths are "
            "NEVER COMPUTED, so that no value exists behind the withheld "
            "quantity for a determined reader to recover"
        )

    entries: list[SmearEntry] = []
    for arm in arms:
        reading = widths.get(arm)
        if contaminated:
            withheld = reason
            value = None
        elif reading is None:
            withheld = f"the {arm!r} arm did not run at this rung"
            value = None
        elif reading.refused is not None:
            withheld = reading.refused
            value = None
        elif reading.at_floor:
            withheld = (
                f"at or below the {reading.floor_cells:g}-cell floor, so the "
                "width is unresolved rather than zero and is reported as "
                "'<= 1 cell'; read the profile before concluding there is no "
                "band, because the majority rule is blind to one that never "
                "carries a cell past a half"
            )
            value = None
        else:
            withheld = None
            value = reading.cells
        entries.append(
            SmearEntry(
                arm=arm,
                quantity=RungQuantity(
                    name=f"{SMEAR_QUANTITY} ({fields.SMEAR_SUBJECT})",
                    scope=f"rung={rung.name} arm={arm}",
                    value=value,
                    denominator=denominator,
                    withheld=withheld,
                    rung=rung,
                ),
                reading=reading,
            )
        )

    return RungReport(
        rung=rung,
        contaminated=contaminated,
        null_line=null_line,
        smears=tuple(entries),
        instrument=dict(instrument),
        cost=dict(cost),
        iterations=dict(iterations),
        ratios={} if ratios is None else dict(ratios),
        checks={} if checks is None else dict(checks),
    )


def require_clean(report: RungReport) -> RungReport:
    """Refuse to proceed past a contaminated rung.

    **THE ACROSS-RUNG HALF OF E6's GATE.** Tasks 5 to 7 call this between rungs;
    `run_rung` does not, because a contaminated report is the diagnosis and
    destroying it would remove the evidence the gate exists to surface.

    Args:
        report: The rung's report.

    Returns:
        The report, unchanged, when the rung is clean.

    Raises:
        RungContaminated: When it is not, with the null's reason.
    """
    reason = contamination_reason(report.null_line)
    if reason is not None:
        raise RungContaminated(
            f"rung {report.rung.name!r}: {reason}. STOP AND DIAGNOSE THE "
            "ESTIMATOR rather than proceeding to the next rung; the null's "
            "profile is on the report"
        )
    return report


def _selection_map(
    store_path: Path | str, grid_shape: tuple[int, int], criterion: int = 0
) -> NDArray[np.int16]:
    """One criterion's slice of a store's `/selection/selected`, as a grid."""
    import zarr

    root = zarr.open_group(str(store_path), mode="r")
    holder = root["selection"]
    if not isinstance(holder, zarr.Group):  # pragma: no cover - store invariant
        raise TypeError("selection is not a group")
    array = holder["selected"]
    if not isinstance(array, zarr.Array):  # pragma: no cover - store invariant
        raise TypeError("selection/selected is not an array")
    selected = np.asarray(array[:])[..., criterion]
    return np.asarray(selected, dtype=np.int16).reshape(grid_shape)


def _width_for(
    selected: NDArray[np.int16],
    truth: FieldTruth,
    *,
    arm: str,
    reach_cells: float,
) -> WidthReading:
    """The smear width of one arm's selection map."""
    agreement = smear.agreement_map(selected, truth.family)
    return smear.smear_width(
        agreement,
        boundary_index=truth.boundary_index,
        normal_axis=0,
        reach_cells=reach_cells,
        map_name=smear.AGREEMENT_MAP_NAME,
        arm=arm,
    )


def _store_agreement(
    result: FitResult, store_path: Path, n_models: int
) -> Mapping[str, Any]:
    """One arm against the store a `run` wrote, cell by cell.

    **TWO PATHS TO ONE QUANTITY, AND BOTH PRODUCE PLAUSIBLE NUMBERS.** The
    budget's unit is measured on `fit` and spent on `run`, so this is the
    boundary the cost model crosses -- and iterations are deterministic, so the
    comparison is exact rather than tolerance-banded.
    """
    agreement = same_iterations(arm_cost(result), store_cost(store_path, n_models))
    return {
        "identical": agreement.identical,
        "cells_compared": agreement.cells_compared,
        "cells_differing": agreement.cells_differing,
        "ok_in_the_arm_only": agreement.left_only,
        "ok_in_the_store_only": agreement.right_only,
    }


def _self_sourced_fine_points(
    radius: NDArray[np.int64], grid_shape: tuple[int, int], stride: int
) -> int:
    """Count fine points whose warm source is themselves; D12 says there are none.

    A source at radius 0 is the point's own coarse fit, which D12 gives to
    coarse points and to nobody else. **A fine point sourcing itself is exactly
    the defect E6's upper refutation clause describes** -- the source map
    handing points their own optimum, which would look like a spectacular
    saving -- and it is readable here with no fits at all.
    """
    n_normal, n_parallel = grid_shape
    at_zero = np.asarray(radius == 0, dtype=np.bool_)
    per_point = at_zero.any(axis=1).reshape(n_normal, n_parallel)
    rows, columns = np.indices((n_normal, n_parallel))
    coarse = (rows % stride == 0) & (columns % stride == 0)
    return int((per_point & ~coarse).sum())


def run_rung(
    rung: Rung,
    *,
    out_dir: Path,
    seed: int,
    n_time: int = fields.N_TIME,
    n_normal: int = fields.N_NORMAL,
    n_parallel: int = fields.N_PARALLEL,
    arms: Sequence[str] = ARMS,
    max_iter: int | None = None,
    is_a_smoke_run: bool = False,
) -> RungReport:
    """Build a field, run the arms, take the widths, and emit one report.

    **THE THIN PART.** Everything assertable is in `build_report`, which takes
    readings; this produces them. It is the benchmark and is not in
    `pixi run test` -- E7.

    Args:
        rung: Which rung.
        out_dir: Where the field, the config and the stores go.
        seed: The field's base seed.
        n_time: Record length. Defaults to production.
        n_normal: Cells across the boundary.
        n_parallel: Cells along it.
        arms: Which arms to read a width from.
        max_iter: Iteration cap per series, or None for the default.
        is_a_smoke_run: Marks the report as having exercised the pipeline
            rather than measured anything.

    Returns:
        The report. **Returned even when contaminated** -- call `require_clean`
        to refuse to proceed.
    """
    import xarray as xr

    from metamer.batch.ragged import build_ragged_index, noise_extent
    from metamer.batch.run import run
    from metamer.batch.twopass import run_two_pass
    from metamer.batch.warmstart import coarse_ok, read_warm_starts, source_map
    from metamer.config.model import load

    out_dir.mkdir(parents=True, exist_ok=True)
    grid_shape = (n_normal, n_parallel)
    settings = WarmStart()
    reach = smear.spiral_reach_cells(settings)

    truth = fields.build_field(
        rung,
        path=out_dir / f"{rung.name}-field.zarr",
        n_time=n_time,
        seed=seed,
        n_normal=n_normal,
        n_parallel=n_parallel,
    )
    config_path = fields.write_config(out_dir, f"{rung.name}.toml", truth.uri)
    config = load(config_path)
    # **ONE READ, USED BY THE MAP AND BY THE BLOCK.** The N2 arm's directions
    # are keyed on `config.audit.seed` and NOT on the field's seed -- 2c Task
    # 6's recorded trap -- and taking it once here is what stops the block
    # naming a seed the map did not use.
    audit_seed = int(config.audit.seed)
    n_models = len(config.candidates)

    cost: dict[str, float] = {}
    iterations: dict[str, float] = {}

    cold_store = out_dir / f"{rung.name}-cold.zarr"
    started = time.perf_counter()
    run(config_path, cold_store, max_iter=max_iter)
    cost["cold_seconds"] = time.perf_counter() - started
    cold_reading = fields.iteration_count(cold_store, ok_only=True)
    iterations["cold_per_point"] = fields.iteration_count(cold_store).per_point
    iterations["cold_ok_total"] = float(cold_reading.total)
    iterations["cold_ok_per_point"] = cold_reading.per_point

    warm_store = out_dir / f"{rung.name}-warm.zarr"
    started = time.perf_counter()
    two_pass = run_two_pass(config_path, warm_store, max_iter=max_iter)
    cost["warm_seconds"] = time.perf_counter() - started
    warm_reading = fields.iteration_count(warm_store, ok_only=True)
    iterations["warm_per_point"] = fields.iteration_count(warm_store).per_point
    iterations["warm_ok_total"] = float(warm_reading.total)
    iterations["warm_ok_per_point"] = warm_reading.per_point
    if two_pass.pass1_path is None:  # pragma: no cover - warm start is on
        raise RuntimeError("the two-pass run produced no coarse pass")
    # **PASS 1'S FITS ARE CHARGED TO THE WARM ARM, OR THE SAVING OMITS THEM.**
    # D11 gives pass 1 its own store, so a saving read off pass 2's store alone
    # leaves the coarse fits with nobody -- 8 points of 384 on this geometry,
    # always in the flattering direction.
    pass1_reading = fields.iteration_count(two_pass.pass1_path, ok_only=True)
    iterations["pass1_ok_total"] = float(pass1_reading.total)
    iterations["pass1_points"] = float(pass1_reading.points)

    # **THE WARM ARRAY IS REBUILT THROUGH THE SHIPPED FUNCTIONS, NOT DERIVED
    # AGAIN.** `run_two_pass` does not expose the starts it used, and a second
    # derivation of them would be a second warm start; `coarse_ok`,
    # `source_map` and `read_warm_starts` are the same three calls pass 2 makes,
    # with the stride and the bound read from the config rather than written.
    usable = coarse_ok(two_pass.pass1_path)
    sources = source_map(
        shape=grid_shape,
        stride=config.warm_start.coarse_stride,
        coarse_ok=usable,
        spiral_bound=config.warm_start.spiral_bound,
        region=None,
    )
    specs = list(config.process_specs())
    warm_starts = read_warm_starts(
        two_pass.pass1_path,
        sources,
        build_ragged_index(specs, noise_extent),
        coarse_shape=(usable.shape[0], usable.shape[1]),
    )

    values = np.asarray(xr.open_zarr(truth.uri)["sla"].values, dtype=np.float64)
    block = values.transpose(1, 2, 0).reshape(n_normal * n_parallel, n_time)
    mask = np.isfinite(block)

    # **THE MAP RUNS FOUR ARMS, SO ALL FOUR ARE KEPT.** `run_arms` fits COLD,
    # WARM, N1 and N2 over the whole field; returning only the N2 map means
    # paying for three full-field arms and discarding them, and each of the
    # three is a reading 2d is otherwise short of. See `n2map.FieldArms`.
    cap = max_iter if max_iter is not None else DEFAULT_MAX_ITER
    started = time.perf_counter()
    field_result = n2map.field_arms(
        block,
        truth.t,
        config.signal_spec(),
        specs,
        Criterion(config.criteria[0]),
        mask=mask,
        warm=warm_starts,
        warm_valid=sources.valid,
        grid_shape=grid_shape,
        seed=audit_seed,
        max_iter=cap,
    )
    cost["n2_seconds"] = time.perf_counter() - started
    n2_selected, n2_counts = field_result.selected, field_result.counts
    audit_cold = field_result.arms.results[Arm.COLD]

    # **THE CEILING E6's UPPER CLAUSE IS READ AGAINST, MEASURED ON THIS FIELD.**
    # Its input is the cold arm's own optimum, so it is the cheapest arm in the
    # design -- and it is the void control: if `self` does not collapse, the
    # instrument has not been shown able to tell two arms apart by cost.
    started = time.perf_counter()
    ceiling = self_arm(
        block,
        truth.t,
        config.signal_spec(),
        specs,
        Criterion(config.criteria[0]),
        mask=mask,
        cold=audit_cold,
        grid_shape=grid_shape,
        max_iter=cap,
    )
    cost["self_seconds"] = time.perf_counter() - started

    cold_cost = arm_cost(audit_cold)
    n1_ratio = iteration_ratio(arm_cost(field_result.arms.results[Arm.N1]), cold_cost)
    self_ratio = iteration_ratio(ceiling.cost, cold_cost)

    selection = {
        "cold": _selection_map(cold_store, grid_shape),
        "warm": _selection_map(warm_store, grid_shape),
        "n2": n2_selected,
    }

    # **THE NULL FIRST, BEFORE ANY WIDTH.** On contamination the widths below are
    # never computed, so no value exists behind the withheld quantity.
    null_line = smear.interior_null(
        smear.agreement_map(selection["warm"], truth.family),
        boundary_index=truth.boundary_index,
        normal_axis=0,
        offset_cells=fields.NULL_LINE_OFFSET_CELLS,
        reach_cells=reach,
        map_name=smear.AGREEMENT_MAP_NAME,
        arm="warm",
    )

    widths: dict[str, WidthReading] = {}
    if null_is_clean(null_line):
        for arm in arms:
            widths[arm] = _width_for(selection[arm], truth, arm=arm, reach_cells=reach)

    instrument = dict(
        instrument_block(
            rung,
            n_time=n_time,
            n_normal=n_normal,
            n_parallel=n_parallel,
            seed=seed,
            audit_seed=audit_seed,
            warm=settings,
            is_a_smoke_run=is_a_smoke_run,
            # **FROM THE FIELD THAT WAS BUILT, NEVER FROM THE CONSTANT.** The
            # truth object knows which construction drew it; the constant only
            # knows what the default is now. They agree today and would not
            # agree in the one case this key exists for.
            construction_version=truth.construction_version,
        )
    )
    instrument["n2_excluded"] = n2_counts.excluded
    instrument["n2_exhausted_spiral"] = n2_counts.exhausted_spiral
    instrument["n2_inadmissible"] = n2_counts.inadmissible
    instrument["n2_zero_distance"] = n2_counts.zero_distance

    earned = saving(
        cold_total=int(iterations["cold_ok_total"]),
        warm_total=int(iterations["warm_ok_total"]),
        pass1_total=int(iterations["pass1_ok_total"]),
    )
    ratios = {
        "n1_over_cold": n1_ratio.ratio,
        "self_over_cold": self_ratio.ratio,
        "saving_pass2_only": earned.pass2_only,
        "saving_net_of_pass1": earned.net,
    }
    checks = {
        "n1_cells_compared": n1_ratio.cells_compared,
        "self_cells_compared": self_ratio.cells_compared,
        "self_started_from_cells": ceiling.started_from,
        "saving_refused": earned.refused,
        # **THE THREE CROSS-CHECKS THE MAP'S OWN ARMS MAKE FREE.** Each is a
        # comparison of two paths to one quantity, and each fails silently:
        # the store and the arm are both plausible numbers.
        "cold_arm_reproduces_the_run_store": _store_agreement(
            audit_cold, cold_store, n_models
        ),
        "warm_arm_reproduces_pass_2_store": _store_agreement(
            field_result.arms.results[Arm.WARM], warm_store, n_models
        ),
        "self_arm_agrees_with_cold_selection": float(
            np.mean(ceiling.selected == selection["cold"])
        ),
        # D12: a coarse point's source is itself and **no fine point's is**.
        # A source map handing a fine point its own optimum is exactly the
        # defect E6's upper clause describes, and it is readable here with no
        # fits at all.
        "fine_points_sourcing_themselves": _self_sourced_fine_points(
            sources.radius, grid_shape, config.warm_start.coarse_stride
        ),
    }

    return build_report(
        rung,
        null_line=null_line,
        widths=widths,
        instrument=instrument,
        cost=cost,
        iterations=iterations,
        ratios=ratios,
        checks=checks,
        denominator=n_normal * n_parallel,
        arms=arms,
    )


__all__ = [
    "ARMS",
    "RungContaminated",
    "RungQuantity",
    "RungReport",
    "SmearEntry",
    "Saving",
    "build_report",
    "contamination_reason",
    "instrument_block",
    "null_is_clean",
    "require_clean",
    "run_rung",
    "saving",
]
