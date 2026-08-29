"""The two-pass driver: decimate, fit cold, barrier, fit warm.

WHAT THIS MODULE IS FOR (design doc §11.1, decisions D1, D5, D11 and D12).
--------------------------------------------------------------------------
Pass 1 fits a coarse grid cold; pass 2 fits **every** point of the full grid,
each warm-started from its nearest valid coarse fit. **Neither pass is a new
mechanism.** Pass 1 is `run(decimate=True)` and pass 2 is
`run(warm_start_from=...)`; this module is the ORDER, the barrier between them
and the path derivation, and nothing else. That is D11's whole argument: no
second completion concept, no warm-start cache, no new tiling and no new store
schema, because **pass 1's store IS the cache** -- which is why §11.1's
`(fit_hash, candidate spec_hash)` cache key needs no implementation of its own.

DISABLING WARM-STARTING DOES NOT RUN PASS 1 AT ALL.
---------------------------------------------------
`warm_start.enabled = false` makes this exactly one cold `run` over the full
grid, with no coarse store written and no residue: byte-for-byte the run a
caller would have got from `run(config, store)` directly. **Running pass 1
anyway and then ignoring it would be worse than useless** -- it costs a
`1/k²`-sized fit and leaves a permanent artifact whose only stated purpose is
to be §11.2's cold reference for a comparison nobody asked for.

**AND THE SETTING IS FIT IDENTITY, SO IT CANNOT BE OVERRIDDEN HERE.**
`warm_start_enabled` is in `FIT_RELEVANT_FIELDS`; a driver that warm-started
anyway would write warm fits under a `fit_hash` that says they are cold.
`run` refuses that combination rather than resolving it.

A SIGTERM DURING PASS 1 IS "ABORTED EARLY", NOT "YOUR CONFIGURATION IS WRONG".
------------------------------------------------------------------------------
Pass 1 is a `run`, so it honours SIGTERM and returns with tiles outstanding.
**Calling the barrier on that store would raise a layer-3 `ValidationError` and
exit 3** -- the code that means the request was invalid -- for a run that was
preempted and is resumable, which is §14.3's exit 2. So this driver returns
after an interrupted pass 1 **without entering the barrier**, with no pass-2
report, and the same command resumes. The barrier keeps its refusal for the
case it was written for: a store that is incomplete for a reason this
invocation did not witness.

`--calibrate` MEASURES TWICE, AND THAT IS DECLARED RATHER THAN FIXED.
---------------------------------------------------------------------
The calibration cache keys on `fit_hash`, which contains `geometry_hash`, and
the two passes have different geometries by construction -- so a two-pass run
that calibrates measures the same per-series cost twice and files it under two
keys. **The per-series cost does not depend on the SPATIAL decimation**: a
coarse point is a whole series of the same length. So this is waste, not error,
and closing it means keying the calibration on something narrower than
`fit_hash` -- a decision about the cache's identity, which is not this task's.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

from metamer.batch.decimate import pass1_store_path
from metamer.batch.run import RunReport, run
from metamer.batch.tiling import Tile
from metamer.batch.validation import load_config
from metamer.core.engines.protocol import Engine
from metamer.core.memory import FloorReport


class _SharedRunKwargs(TypedDict):
    """The `run` arguments both passes take unchanged.

    A `TypedDict` rather than a plain mapping for the reason `run.TileModelKwargs`
    is one: `**mapping` erases every value's type to the union, so mypy has to
    assume a `FloorReport` might land in the `max_iter` slot. **Every argument
    `run` takes that this driver does NOT forward is absent by construction** --
    `decimate`, `warm_start_from`, `reuse_fits_from` and the two `on_tile_written`
    seams are each passed explicitly at the call site that owns them, so a future
    argument cannot be forwarded to the wrong pass by being added here.
    """

    memory_budget_gb: float | None
    observed_thread_limits: Mapping[str, int] | None
    engine: Engine | None
    floor: FloorReport | None
    max_iter: int | None
    calibrate: bool
    recalibrate: bool
    calibration_cache_path: Path | str | None
    calibration_ladder: tuple[int, ...] | None


@dataclass(frozen=True)
class TwoPassReport:
    """What a two-pass run established, one report per pass.

    Attributes:
        pass1: What the coarse pass established, or None when warm-starting is
            disabled and no coarse pass ran. **None is the fact**, on the same
            precedent as the store's own optional attrs.
        pass2: What the full-grid pass established, or None when pass 1 was
            interrupted and pass 2 never started.
        pass1_seconds: Wall clock around pass 1, or None when it did not run.
        pass2_seconds: Wall clock around pass 2, or None when it did not run.
            **Wall clock is process-local and is provenance**: it reaches no
            hash and no store, is reported and never compared, and is the one
            thing in this report that is not reproducible.
        store_path: Pass 2's store -- the output.
        pass1_path: Where pass 1's store went, or None when it did not run.
            **A PERMANENT ARTIFACT, NOT SCRATCH.** It is the only record of what
            those points fit to without a warm start, and deleting it discards a
            measurement that cannot be recovered without refitting.

            **IT IS THE AUDIT'S CROSS-CHECK AND NOT THE AUDIT'S SAMPLE** -- this
            used to say *"§11.2's only cold reference for the same points"*,
            which reads as *"the audit compares against this"* and is wrong. A
            coarse point's nearest valid source is **itself** (D12), so pass 2's
            warm fit there starts from pass 1's own optimum: convergence
            idempotence, not hysteresis. **The audit draws FINE points and
            computes its own cold arm**, and pass 1's store is what that arm is
            checked against, bitwise, at the coarse points.
    """

    pass1: RunReport | None
    pass2: RunReport | None
    pass1_seconds: float | None
    pass2_seconds: float | None
    store_path: Path
    pass1_path: Path | None

    @property
    def interrupted(self) -> bool:
        """Whether tiles remain outstanding in either pass.

        **READ OFF THE PASSES' OWN COUNTS, NOT OFF A SIGNAL**, which is the rule
        `RunReport.interrupted` already follows: a SIGTERM during the last tile
        leaves a finished store, and a run that wrote every tile finished
        whatever happened to the process. A pass that never ran is not
        outstanding -- pass 1 under `enabled = false` is a pass that was not
        owed.

        Returns:
            True if pass 1 stopped short, or pass 2 did, or pass 2 never
            started because pass 1 stopped short.
        """
        if self.pass1 is not None and self.pass1.interrupted:
            return True
        if self.pass2 is None:
            return self.pass1 is not None
        return self.pass2.interrupted


def run_two_pass(
    config_path: Path | str,
    store_path: Path | str,
    *,
    memory_budget_gb: float | None = None,
    observed_thread_limits: Mapping[str, int] | None = None,
    engine: Engine | None = None,
    on_tile_written: Callable[[Tile], None] | None = None,
    on_pass1_tile_written: Callable[[Tile], None] | None = None,
    floor: FloorReport | None = None,
    max_iter: int | None = None,
    calibrate: bool = False,
    recalibrate: bool = False,
    calibration_cache_path: Path | str | None = None,
    calibration_ladder: tuple[int, ...] | None = None,
) -> TwoPassReport:
    """Fit a coarse pass, then the full grid warm-started from it.

    Args:
        config_path: Path to a `.toml` or `.json` config. **Both passes read
            the same file**, which is what makes the cross-store gate an
            equality rather than a reconciliation.
        store_path: Where pass 2's store goes. Pass 1's is derived from it by
            `decimate.pass1_store_path` and is never passed in: a caller that
            supplied the same path for both would have pass 2 resume pass 1's
            coarse store.
        memory_budget_gb: Overrides the config's budget, for both passes. **The
            two passes derive DIFFERENT tile sides from it** -- pass 1's grid is
            `1/k²` the size -- and that is correct; §11.3 guarantees the output
            does not depend on either.
        observed_thread_limits: Observed thread limit per loaded library.
        engine: Likelihood engine, passed to both passes.
        on_tile_written: Fault-injection seam for **pass 2**, called between a
            tile's data write and its completion bit.
        on_pass1_tile_written: The same seam for **pass 1**, separate because
            the two interruptions have different consequences and a test that
            could only reach one of them could not tell them apart: a kill in
            pass 1 must stop before the barrier, and a kill in pass 2 must leave
            a store that resumes to a bitwise-identical result.
        floor: The measured process floor, passed to both passes.
        max_iter: Iteration cap per series, for both passes.
        calibrate: Measure bytes per series before tiling. **This measures
            TWICE** -- see the module docstring for why, and why that is waste
            rather than error.
        recalibrate: Measure even if the cache has an entry. Implies
            `calibrate`.
        calibration_cache_path: Where the cache lives.
        calibration_ladder: Tile sides to measure.

    Returns:
        One report per pass, with pass 2's absent when pass 1 was interrupted.

    Raises:
        ValidationError: Layers 1-3, from either pass. Exit code 3.
        InputContractError: Layer 4 -- the data. Exit code 4.
    """
    shared: _SharedRunKwargs = {
        "memory_budget_gb": memory_budget_gb,
        "observed_thread_limits": observed_thread_limits,
        "engine": engine,
        "floor": floor,
        "max_iter": max_iter,
        "calibrate": calibrate,
        "recalibrate": recalibrate,
        "calibration_cache_path": calibration_cache_path,
        "calibration_ladder": calibration_ladder,
    }

    # THE CONFIG IS READ HERE ONLY TO ANSWER "IS THERE A PASS 1?". Every other
    # use of it is inside `run`, which loads it again through the one
    # constructor a run uses -- this is not a second derivation of anything the
    # run acts on, and the layer-1 and layer-2 refusals a bad file earns are
    # still `load_config`'s and still arrive before anything is opened.
    config = load_config(config_path)
    if not config.warm_start.enabled:
        # ONE COLD PASS, AND NOTHING ELSE HAPPENS. No coarse store is written,
        # so a caller who switches warm-starting off gets the store they would
        # have got from `run` and no second directory beside it.
        started = time.perf_counter()
        only = run(config_path, store_path, on_tile_written=on_tile_written, **shared)
        return TwoPassReport(
            pass1=None,
            pass2=only,
            pass1_seconds=None,
            pass2_seconds=time.perf_counter() - started,
            store_path=Path(store_path),
            pass1_path=None,
        )

    pass1_path = pass1_store_path(store_path)
    started = time.perf_counter()
    first = run(
        config_path,
        pass1_path,
        decimate=True,
        on_tile_written=on_pass1_tile_written,
        **shared,
    )
    pass1_seconds = time.perf_counter() - started

    if first.interrupted:
        # **RETURNED BEFORE THE BARRIER, AND THE EXIT CODE IS THE REASON.** See
        # the module docstring: entering it here would report a preempted run as
        # an invalid request.
        return TwoPassReport(
            pass1=first,
            pass2=None,
            pass1_seconds=pass1_seconds,
            pass2_seconds=None,
            store_path=Path(store_path),
            pass1_path=pass1_path,
        )

    started = time.perf_counter()
    second = run(
        config_path,
        store_path,
        warm_start_from=pass1_path,
        on_tile_written=on_tile_written,
        **shared,
    )
    return TwoPassReport(
        pass1=first,
        pass2=second,
        pass1_seconds=pass1_seconds,
        pass2_seconds=time.perf_counter() - started,
        store_path=Path(store_path),
        pass1_path=pass1_path,
    )


__all__ = ["TwoPassReport", "run_two_pass"]
