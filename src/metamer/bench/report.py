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

from metamer.batch.audit_report import Quantity
from metamer.bench import fields, n2map, smear
from metamer.bench.fields import FieldTruth, Rung
from metamer.bench.smear import WidthReading
from metamer.config.model import WarmStart
from metamer.core.criteria import Criterion
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


def instrument_block(
    rung: Rung,
    *,
    n_time: int,
    n_normal: int,
    n_parallel: int,
    seed: int,
    warm: WarmStart | None = None,
    is_a_smoke_run: bool = False,
) -> Mapping[str, Any]:
    """What produced the numbers, read from the shipped constants at call time.

    Args:
        rung: The rung, whose per-parameter `sources` go in whole.
        n_time: Record length this run used.
        n_normal: Cells across the boundary.
        n_parallel: Cells along it.
        seed: The field's base seed. **With `draw_method`, this is what keys the
            drawn bytes**; either alone does not.
        warm: The warm-start settings to describe. Defaults to the shipped ones.
        is_a_smoke_run: **True marks a report that exercised the pipeline rather
            than measuring anything** -- a reduced geometry or record length.
            Task 9 must refuse such a report as a measurement, and the flag is
            in the block rather than in a filename because a filename does not
            travel with the bytes.

    Returns:
        The block.
    """
    settings = WarmStart() if warm is None else warm
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
        "criteria": list(fields.CRITERIA),
        "algorithm_version": ALGORITHM_VERSION,
        "draw_method": fields.DRAW_METHOD,
        "seed": seed,
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

    cost: dict[str, float] = {}
    iterations: dict[str, float] = {}

    cold_store = out_dir / f"{rung.name}-cold.zarr"
    started = time.perf_counter()
    run(config_path, cold_store, max_iter=max_iter)
    cost["cold_seconds"] = time.perf_counter() - started
    iterations["cold_per_point"] = fields.iteration_count(cold_store).per_point

    warm_store = out_dir / f"{rung.name}-warm.zarr"
    started = time.perf_counter()
    two_pass = run_two_pass(config_path, warm_store, max_iter=max_iter)
    cost["warm_seconds"] = time.perf_counter() - started
    iterations["warm_per_point"] = fields.iteration_count(warm_store).per_point
    if two_pass.pass1_path is None:  # pragma: no cover - warm start is on
        raise RuntimeError("the two-pass run produced no coarse pass")

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

    started = time.perf_counter()
    n2_selected, n2_counts = n2map.n2_field_map(
        block,
        truth.t,
        config.signal_spec(),
        specs,
        Criterion(config.criteria[0]),
        mask=mask,
        warm=warm_starts,
        warm_valid=sources.valid,
        grid_shape=grid_shape,
        seed=seed,
        max_iter=max_iter if max_iter is not None else DEFAULT_MAX_ITER,
    )
    cost["n2_seconds"] = time.perf_counter() - started

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
            warm=settings,
            is_a_smoke_run=is_a_smoke_run,
        )
    )
    instrument["n2_excluded"] = n2_counts.excluded
    instrument["n2_exhausted_spiral"] = n2_counts.exhausted_spiral
    instrument["n2_inadmissible"] = n2_counts.inadmissible
    instrument["n2_zero_distance"] = n2_counts.zero_distance

    return build_report(
        rung,
        null_line=null_line,
        widths=widths,
        instrument=instrument,
        cost=cost,
        iterations=iterations,
        denominator=n_normal * n_parallel,
        arms=arms,
    )


__all__ = [
    "ARMS",
    "RungContaminated",
    "RungQuantity",
    "RungReport",
    "SmearEntry",
    "build_report",
    "contamination_reason",
    "instrument_block",
    "null_is_clean",
    "require_clean",
    "run_rung",
]
