"""The run: config to input contract to geometry fingerprint to the hashes.

**THE PYTHON API IS THE UNIT OF IMPLEMENTATION AND TESTING.**
`python -m metamer <config.toml> <store>` is a thin argparse wrapper over `run`,
and it presupposes no command tree -- naming a subcommand would design the
argument structure now rather than in Phase 5, when `validate` and `report` are
real.

**THE ORDERING IS THE GUARD, AND IT IS TESTED RATHER THAN TRUSTED.** Design doc
section 13.7:

    layers 1-2 -> layer 3 -> open -> input contract (4a) -> geometry
    fingerprint -> fit_hash -> resume gate -> tiling

Two things fall out of that order and neither is incidental. A hash computed
before the contract check would be computed from the config alone, which is
where `data_uri`-as-proxy came from. And every layer-3 check that can *fail*
sits above the open, so a run whose config is wrong AND whose data is wrong
reports the config -- the two send a user to different places.

**THE RESUME GATE HAS ONE SITE AND TWO HALVES.** Inside the single
`if store exists` block: `resume.check_resume` compares identity -- schema
version, `fit_hash`, the candidate list positionally, the criterion set, the
`/detail/` selection, `compat_hash` -- and then `completion.resume_tile_side`
settles geometry. Identity first: a store whose fits are unusable should say so
before it says anything about tile sizes. **What this does not do is recompute
anything**: the compat-only arm has no producer (the two allowlists differ by
`criteria` alone, which refuses), so recomputation is Task 12's, into a new
store.

**DATA THEN BITMAP, AND THE BIT IS SET FROM THE FACT THAT THE WRITE RETURNED.**
`write.write_tile` has no way to decline, so there is no branch in which the bit
means something else; `completion` carries the rest of the argument. The loop
stops after a tile whose bit is written when SIGTERM has been recorded, which is
why a preemption costs at most the tile in flight.

**AND `interrupted` IS COMPUTED FROM THE TILE COUNTS, NOT FROM THE SIGNAL.** A
SIGTERM arriving during the last tile leaves nothing outstanding, and a run that
wrote every tile is a run that finished whatever else happened to the process.
The signal is a request; the store's state is the fact.

**THE ENGINE MUST STAY INJECTABLE, AND THAT LANDS AT TASK 9.** `fit(engine=...)`
is the seam the raising stub fixture is delivered through, and a runner that
builds its engine internally from the config makes every downstream "no fit ran"
assertion vacuous. Nothing here fits, so an `engine=` parameter now would be one
no test could make bite -- a hook promised in argument form. **Task 9 is the
first task that fits and is where it must arrive.**
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypedDict

import numpy as np
import zarr
from numpy.typing import NDArray

from metamer.batch import calibration as calibration_cache
from metamer.batch import reuse
from metamer.batch.completion import (
    completed_tiles,
    flush_on_sigterm,
    mark_complete,
    resume_tile_side,
    tile_index,
)
from metamer.batch.geometry import geometry_components, geometry_hash
from metamer.batch.input import ContractReport, InputHandle, open_input
from metamer.batch.input import check_contract as check_input_contract
from metamer.batch.ragged import RaggedIndex, build_ragged_index, noise_extent
from metamer.batch.resume import check_resume, check_source
from metamer.batch.store import (
    StoreShape,
    TileSideBasis,
    create_store,
    provenance_attrs,
)
from metamer.batch.threads import Phase, thread_budget
from metamer.batch.tiling import (
    BudgetTooSmallError,
    Tile,
    assemble_tile,
    read_amplification,
    tile_grid,
    tile_side_for,
)
from metamer.batch.timeaxis import to_decimal_years
from metamer.batch.validation import (
    ValidationError,
    ValidationLayer,
    check_semantics,
    identifiability_warnings,
    load_config,
)
from metamer.batch.write import check_status_invariant, write_selection, write_tile
from metamer.config.model import Config
from metamer.core import machine
from metamer.core.capability import Objective
from metamer.core.criteria import Criterion
from metamer.core.engines.kalman import KalmanEngine
from metamer.core.engines.protocol import Engine
from metamer.core.fit import fit
from metamer.core.lint import Finding
from metamer.core.memory import (
    CALIBRATION_LADDER,
    FloorReport,
    SolverPlacement,
    default_budget_gb,
    measure_floor,
    memory_engine_label,
    resident_bytes_per_series,
)
from metamer.core.memory import calibrate as measure_calibration
from metamer.core.optimize import DEFAULT_MAX_ITER
from metamer.core.signal import SignalSpec
from metamer.core.signal import k_beta as signal_k_beta
from metamer.core.statespace import StateSpace
from metamer.core.terms import ProcessSpec


@dataclass(frozen=True)
class RunReport:
    """What a run established. Everything here reaches provenance.

    Attributes:
        config: The EFFECTIVE configuration -- the file's contents with any
            command-line override applied **and the memory budget resolved**,
            because that is what the run used and therefore what `run_hash`
            must describe.
        memory_budget_requested_gb: What the configuration asked for, or None
            if it named no budget. **The request, kept apart from
            `config.memory_budget_gb`, which is what the run used.** The two
            differ exactly when the default fired, and only the pair can say
            so: the resolved value alone is indistinguishable from a request
            for the same number, and it is the machine's answer rather than
            anyone's choice.
        budget_warning: A warning that the resolved budget exceeds the memory
            this machine reports free, or None. **Never moves the exit code**;
            see `run`'s body for why availability cannot be a gate.
        calibration_warning: Why a consulted calibration did not size the tile,
            or None -- None both when none was consulted and when the one that
            was is what sized it. **The store tells those two apart**, through
            the presence of its `calibration` attr beside `tile_side_basis`;
            here they are one because a report says what a caller has to act
            on, and there is nothing to act on in either case. Never moves the
            exit code, on `budget_warning`'s grounds.
        config_path: Where the configuration came from.
        store_path: Where the store goes.
        contract: What stage 4a established about the input.
        components: The geometry fingerprint's parts, for the store's root
            attrs. A mismatch is diagnosable from the store alone only if the
            store carries the parts as well as the rollup.
        geometry_hash: The rollup.
        fit_hash: The gate on refitting.
        compat_hash: The gate on recomputing derived arrays.
        run_hash: Provenance, never a gate.
        machine: This machine's fingerprint, read from the platform.
        thread_limits: The OBSERVED thread limit per library, not the requested
            one. Design doc section 11.3's determinism precondition.
        phase_seconds: Wall-clock seconds per phase, so the ratio that justifies
            serializing assemble and fit is recorded rather than assumed.
        warnings: Identifiability findings. **Warnings never move the exit
            code**; that is what makes it safe for them to be produced after
            stage 4a.
        k_beta: Design COLUMN count -- not the term count. `Harmonic` gives two
            columns, so 2a's three signal terms are four columns, which is
            design doc 9.4's worked value and what every tile figure rests on.
        tile_side: Points per tile side. From the budget and the per-series
            resident bytes on a fresh store, and **from the store itself on a
            resume**, whose shards were fixed when it was created.
        tiles_total: Tiles in the grid, whoever wrote them.
        tiles_written: How many tiles this run fitted and wrote.
        tiles_skipped: How many the completion bitmap already held.
        interrupted: Whether tiles remain outstanding -- **read off the counts
            rather than off the signal**, because a SIGTERM during the last tile
            leaves a finished store and a run that wrote everything finished.
        sigterm_armed: Whether the SIGTERM handler was installed. False for a
            run driven off the main thread, where `signal.signal` cannot be
            called at all; the alternative to reporting it is claiming a
            protection that is not there.
    """

    config: Config
    memory_budget_requested_gb: float | None
    budget_warning: str | None
    calibration_warning: str | None
    config_path: Path
    store_path: Path
    contract: ContractReport
    components: Mapping[str, Any]
    geometry_hash: str
    fit_hash: str | None
    compat_hash: str | None
    run_hash: str
    machine: str
    thread_limits: Mapping[str, int]
    phase_seconds: Mapping[str, float]
    warnings: tuple[Finding, ...]
    k_beta: int
    tile_side: int
    tiles_total: int
    tiles_written: int
    tiles_skipped: int
    interrupted: bool
    sigterm_armed: bool


def _recompute_tile(
    source_path: Path | str,
    store_path: Path | str,
    tile: Tile,
    *,
    config: Config,
) -> None:
    """Copy one tile's fits and rank them again under the requested criteria.

    **The invariant is checked on the block this path actually consumes**, with
    the same function the fit path uses, so a corrupted source is a refusal
    rather than a new store that inherits the corruption and looks freshly
    computed. It is checked over `log_lik`, `k` and `n` rather than over every
    copied array: those are what the ranking reads, the rest were checked when
    the source was written, and exit criterion 4 checks a finished store whole.

    Args:
        source_path: The store being reused.
        store_path: The store being written.
        tile: The spatial block.
        config: The requested configuration.

    Raises:
        InvariantError: If the source's primitives violate the status/value
            invariant.
    """
    source = zarr.open_group(str(source_path), mode="r")
    destination = zarr.open_group(str(store_path), mode="r+")
    scores = reuse.read_scores(
        source, tile, engine=config.engine, objective=config.objective
    )
    rows = tile.y_stop - tile.y_start
    columns = tile.x_stop - tile.x_start
    region = (slice(tile.y_start, tile.y_stop), slice(tile.x_start, tile.x_stop))

    reuse.copy_tile(source, destination, tile)
    check_status_invariant(
        scores.outcome,
        {"log_lik": scores.loglik, "k": scores.k, "n": scores.n},
    )
    write_selection(
        destination,
        region,
        scores,
        config.criteria,
        rows,
        columns,
        len(scores.labels),
    )


class TileModelKwargs(TypedDict):
    """The five model numbers the tiling arithmetic takes.

    A `TypedDict` rather than a plain mapping so `**geometry.tile_kwargs()`
    type-checks against `tile_side_for`'s keyword-only signature -- otherwise
    mypy has to assume an `int` might land in the `placement` or
    `per_point_design` slot, which is the same narrowing `test_memory.py`'s
    `_Case` exists for.
    """

    d: int
    k_beta: int
    p_max: int
    n_time: int
    n_models: int


@dataclass(frozen=True)
class RunGeometry:
    """What a run derives from its config and its input, before it tiles.

    **ONE DERIVATION, TWO CALLERS, AND THAT IS THE WHOLE REASON THIS IS A TYPE.**
    `run()` needs all of it; Phase 2b's calibration needs `tile_kwargs()` to ask
    `tiling.budget_bytes_for_side` which budget lands on a given tile side. A
    calibration that assembled those five numbers itself would be a **second**
    derivation of the production geometry -- and a calibration measuring a tile
    the production run would not build is (j2) with extra steps.

    Attributes:
        years: The decimal-year axis, converted once. The conversion is under
            `ALGORITHM_VERSION`, so doing it twice is two derivations of fit
            identity.
        signal: The signal specification.
        k_beta: Design COLUMN count, not the term count.
        specs: The candidate set, in config order.
        index: The ragged noise index, which is what knows `p_max`.
        state_dims: Composite state dimension per candidate.
    """

    years: NDArray[np.float64]
    signal: SignalSpec
    k_beta: int
    specs: list[ProcessSpec]
    index: RaggedIndex
    state_dims: list[int]
    n_time: int

    def tile_kwargs(self) -> TileModelKwargs:
        """Return the model arguments `tile_side_for` and its inverse take.

        **`p_max` AND `d` ARE THE WIDEST CANDIDATE'S, NOT THE FIRST'S.** The
        tile holds whichever candidate is being fitted and `fit` sizes every
        output slot to the widest, so a budget taken from `white` (d = 0, p = 1)
        would size a tile the `white + matern12` pass cannot hold. **And `p_max`
        is read off the ragged index rather than counted by eye** -- Task 2
        counted `white + matern12` as two free parameters and it is three, which
        the slow suite caught two fixtures later.

        Returns:
            `d`, `k_beta`, `p_max`, `n_time` and `n_models`.
        """
        return {
            "d": max(self.state_dims),
            "k_beta": self.k_beta,
            "p_max": max(self.index.extents),
            "n_time": self.n_time,
            "n_models": len(self.specs),
        }


def run_geometry(
    config: Config, handle: InputHandle, contract: ContractReport
) -> RunGeometry:
    """Derive the model geometry a run tiles against.

    Args:
        config: The effective configuration.
        handle: An opened input, past the stage-4a contract.
        contract: What stage 4a established.

    Returns:
        The geometry.
    """
    years = to_decimal_years(handle.dataset["time"].values)
    signal = config.signal_spec()
    specs = list(config.process_specs())
    return RunGeometry(
        years=years,
        signal=signal,
        k_beta=signal_k_beta(signal, years),
        specs=specs,
        index=build_ragged_index(specs, noise_extent),
        state_dims=[StateSpace.from_spec(spec).state_dim for spec in specs],
        n_time=contract.n_time,
    )


def _with_memory_budget(config: Config, budget_gb: float, *, source: str) -> Config:
    """Return `config` with its memory budget replaced, RE-VALIDATED.

    **`model_copy` would not re-validate**, so a budget of 0 or -1 typed on the
    command line would be accepted while the identical value in the file is
    refused -- the same run valid or invalid depending on where the number was
    typed. Round-tripping through `model_validate` puts the override through the
    same constraint as the field.

    **THE MESSAGE'S PHRASING COMES FROM THE CALLER, WHICH IS (c3).** There are
    two callers -- the command-line override and the defaulting rule -- and
    `--memory-budget: ...` is right for one and absurd for the other, which
    would name a flag the user never typed. The default path cannot fire this
    today, since a fraction of any positive RAM reading is positive; that is
    exactly the shape of message defect that ships, so the phrasing is a
    parameter rather than a constant.

    Args:
        config: The configuration as loaded.
        budget_gb: The budget to install, in GB.
        source: What produced `budget_gb`, for the refusal's message.

    Returns:
        The effective configuration.

    Raises:
        ValidationError: Layer 2, if the budget violates the field's constraint.
    """
    try:
        return Config.model_validate(
            {**config.model_dump(), "memory_budget_gb": budget_gb}
        )
    except ValueError as error:
        raise ValidationError(ValidationLayer.SCHEMA, f"{source}: {error}") from error


FLOOR_OVERRIDE_ENV = "METAMER_FLOOR_BYTES"
"""Environment variable that replaces the measured floor with a fixed one.

**THIS DEFEATS F1's GUARANTEE AND IS PROVIDED ANYWAY, FOR TWO REASONS.**

The first is production: `measure_floor` spawns two processes and imports numba.
A sandbox that forbids spawning cannot run the probe at all, and without an
override every run there fails at a step that has nothing to do with the fit.

The second is that a measured floor makes an **out-of-process** fixture unable to
pin a tile side. `block = (budget - floor) x (1 - headroom)`, so selecting a
side of 1 means landing the block inside a window about three series wide --
a few kB -- while the measured floor varies by megabytes between runs. **The
window is a thousand times narrower than the jitter.** In-process tests have
`run(floor=...)`; a test that must drive `python -m metamer` in a subprocess has
nothing else.

**IT RECORDS ITSELF AND NEEDS NO NEW FIELD.** An overridden floor writes
`components = {"override": N}` into the store's provenance, so a store built
with one says so in its own attrs -- which is the difference between a seam and
a hole.
"""


def _resolve_floor(config: Config) -> FloorReport:
    """Return the floor for this run: the override if set, else a measurement.

    Args:
        config: The effective configuration, for the input to open.

    Returns:
        The floor.

    Raises:
        ValidationError: Layer 2, if the override is set to something that is
            not a positive integer. **Refused rather than ignored**: a
            misspelled value silently falling back to a measurement would give a
            different tile side from the one the caller arranged, and the
            symptom would be an unexplained refusal several steps later.
    """
    raw = os.environ.get(FLOOR_OVERRIDE_ENV)
    if raw is None:
        return measure_floor(data_uri=config.data_uri, variable=config.variable)
    try:
        value = int(raw)
    except ValueError as error:
        raise ValidationError(
            ValidationLayer.SCHEMA,
            f"{FLOOR_OVERRIDE_ENV}={raw!r} is not an integer number of bytes",
        ) from error
    if value < 1:
        raise ValidationError(
            ValidationLayer.SCHEMA,
            f"{FLOOR_OVERRIDE_ENV}={raw!r} must be positive; a floor of zero "
            "says the process holds nothing before a tile exists, which is a "
            "plausible number and never a true one",
        )
    return FloorReport(
        pre_warm_bytes=value,
        post_warm_bytes=value,
        with_input_bytes=value,
        peak_bytes=value,
        # ONE RUNG NAMED `override`, so the store's own provenance distinguishes
        # an overridden floor from a measured one without a schema change.
        components={"override": value},
    )


def run(
    config_path: Path | str,
    store_path: Path | str,
    *,
    memory_budget_gb: float | None = None,
    observed_thread_limits: Mapping[str, int] | None = None,
    engine: Engine | None = None,
    on_tile_written: Callable[[Tile], None] | None = None,
    reuse_fits_from: Path | str | None = None,
    floor: FloorReport | None = None,
    max_iter: int | None = None,
    calibrate: bool = False,
    recalibrate: bool = False,
    calibration_cache_path: Path | str | None = None,
    calibration_ladder: tuple[int, ...] | None = None,
) -> RunReport:
    """Validate a configuration, fit every tile, and write the store.

    Args:
        config_path: Path to a `.toml` or `.json` config.
        store_path: Where the store goes. Created if absent.
        memory_budget_gb: Overrides the config's `memory_budget_gb`. It is
            run-relevant, so the override reaches `run_hash` and neither gate.
        observed_thread_limits: Observed thread limit per loaded library.
            **The run observes its own by default** through
            `batch.threads.thread_budget`; supplying them overrides the
            observation and exists so a test can construct a mismatch this
            machine cannot produce.
        engine: Likelihood engine, passed straight to `fit`. **THE SEAM TASK 4
            DELIBERATELY DID NOT ADD**, because no test there could make it
            bite: a runner that builds its engine internally makes every
            downstream "no fit ran" assertion vacuous, since a stub that is
            never wired in and a stub that is never reached are byte-identical
            in the test output. The write path is the first caller that can
            reach an engine, so the seam lands here.
        on_tile_written: Called between a tile's data write and its completion
            bit. **THE FAULT-INJECTION SEAM, AND IT IS THE ONLY WAY EXIT
            CRITERION 8 CAN BE DEMONSTRATED**: the property is that an
            interruption in that window leaves the bit unset, and an
            interruption arranged by timing is a race whose failure to reproduce
            proves nothing. Same argument as `engine=` -- a seam a test cannot
            reach makes the assertion vacuous.
        reuse_fits_from: A finished store to recompute from, rather than
            fitting. **The fit step becomes a read and nothing else about the
            loop changes.** The new store writes its own provenance with the
            source's path and hashes recorded, and is self-contained: it opens
            with the source deleted.
        floor: The measured process floor. **Measured fresh here when omitted,
            and never cached** -- an uncached quantity has no staleness failure
            mode, and the alternative would key on the input's chunk grid, which
            Task 11's (a1) sweep established is read back rather than hashed.
            Supplying one overrides the measurement, on the same grounds as
            `observed_thread_limits`: the probe costs a child process, a numba
            import and an open, and a test that is not about the floor should not
            pay for one. **The default path is exercised by its own test**, or
            the seam would make every floor assertion vacuous.
        max_iter: Iteration cap per series, defaulting to
            `optimize.DEFAULT_MAX_ITER`. **THE SEAM PHASE 2b's CALIBRATION IS,
            AND IT IS A `run()` ARGUMENT RATHER THAN A CONFIG FIELD ON PURPOSE.**
            The calibration is a capped run of *this* function -- same entry
            point, same tile loop, same budget derivation -- because a
            purpose-built harness would approximate the loop and then validate
            the approximation, which is (j2) and is the defect F2 already was.
            A cap in the config would reach `fit_hash`, and the calibration
            would then key on a different fit identity from the run whose memory
            it measures.
            **The unset path is the default value and not a branch**: it is
            resolved once, above the loop, into the same argument `fit` already
            takes, so a run that does not cap allocates and orders exactly what
            it did before the seam existed. **The cost is that a capped store
            shares all three hashes with an uncapped one** -- the cap is in no
            payload -- so the resolved value is written into provenance as
            `max_iter`, which is the only thing that tells the two apart without
            reading every outcome code.
        calibrate: Measure bytes per series before tiling, reusing a cached
            measurement when one is filed under this run's key. **OPT-IN, AND
            THE COST IS WHY**: at design doc 9.4's configuration the shipped
            ladder is ~26.5 h on the development machine (Phase 2b Task 4), and
            13.4 is explicit that a run which silently spends a long time
            measuring before it starts is behaviour a user cannot predict.
            Without it the corrected analytic formula sizes the tile and the
            store records `TileSideBasis.DEFAULT` -- 13.4's case (c), which
            since Task 2 is an honest estimate rather than a guess.
        recalibrate: Measure even if the cache has an entry, and overwrite it.
            Implies `calibrate`. **It is the ONLY override, and a cache with no
            expiry needs exactly one**: time does not cause the change an expiry
            stands in for, so `--recalibrate` fires when a human has reason to
            believe the measurement is stale, which is the only signal an expiry
            was ever approximating.
        calibration_cache_path: Where the cache lives, defaulting to
            `calibration.cache_path(store_path)` -- a sibling in the store's own
            prefix. Overridable because 15.5 puts the store in object storage
            and a caller may have a different arrangement for the sibling.
        calibration_ladder: Tile sides to measure, defaulting to
            `memory.CALIBRATION_LADDER`. **The seam that makes a calibration
            affordable in a test**: the shipped ladder is 7680 fitted series,
            and a suite that could not choose its own could not exercise this
            path at all -- which would leave *"a default run does not
            calibrate"* as a pure negative with no positive control (i2).

    Returns:
        What the run established.

    Raises:
        ValidationError: Layers 1-3 -- the config, a resume whose stored tile
            side this run's budget cannot hold, and a calibration asked for
            alongside a recompute or an injected engine. Exit code 3.
        InputContractError: Layer 4 -- the data. Exit code 4.
    """
    # RESOLVED ONCE, ABOVE EVERYTHING, so the tile loop keeps exactly the call
    # it had before the seam existed. A branch inside the loop would put a
    # condition on the production path for the sake of a calibration.
    iteration_cap = DEFAULT_MAX_ITER if max_iter is None else max_iter

    # **REFUSED RATHER THAN IGNORED, AND BOTH REFUSALS ARE THE SAME RULE**: a
    # flag that parses and does nothing reads as supported, which is what
    # `--reuse-fits-from` was held to at 2a Task 12 and `engine=` at 2a Task 9.
    #
    # A recompute DERIVES no side -- it reads the source's back (a1) and skips
    # the budget arithmetic entirely, because the rule bounds a FIT's resident
    # set and a recompute has none -- so a calibration alongside one would
    # measure for hours and change nothing. An injected engine is worse than
    # useless: the calibration re-runs the production path in child processes,
    # which build their own engine, so the measurement would be filed under the
    # injected engine's label having measured the default one.
    wants_calibration = calibrate or recalibrate
    if wants_calibration and reuse_fits_from is not None:
        raise ValidationError(
            ValidationLayer.SEMANTIC,
            "a recompute derives no tile side -- it reads the source store's "
            "back -- so there is nothing for a calibration to size. Drop "
            "--calibrate, or fit rather than recompute",
        )
    if wants_calibration and engine is not None:
        raise ValidationError(
            ValidationLayer.SEMANTIC,
            "a calibration re-runs this configuration in child processes, "
            "which build their engine themselves, so an injected engine would "
            "not reach the measurement and its slope would be filed under that "
            "engine's calibration key having measured another one",
        )

    config = load_config(config_path)
    if memory_budget_gb is not None:
        config = _with_memory_budget(config, memory_budget_gb, source="--memory-budget")

    # **THE REQUEST AND THE BUDGET ARE TWO FACTS AND THE ORDER HERE IS WHAT
    # KEEPS THEM APART.** `None` means the configuration named no budget, which
    # `Field(default=1.0)` could not express: a config omitting the field would
    # be byte-identical to one specifying 1.0, so a defaulting rule would have
    # nothing to fire on. The request is read before the resolution overwrites
    # it, and both reach provenance.
    #
    # **A FRACTION OF TOTAL RAM, NEVER AVAILABLE.** An available-RAM default
    # varies with whatever else the machine is doing, so a second run against
    # the same store derives a smaller side and `resume_tile_side` refuses --
    # a resume failing because a browser was open, which defeats 15.5's
    # burst-and-resume argument. See `memory.DEFAULT_BUDGET_FRACTION`.
    requested_budget_gb = config.memory_budget_gb
    resolved_budget_gb = requested_budget_gb
    if resolved_budget_gb is None:
        resolved_budget_gb = default_budget_gb()
        config = _with_memory_budget(
            config,
            resolved_budget_gb,
            source="the default memory budget (a fraction of total RAM)",
        )
    budget_bytes = int(resolved_budget_gb * 10**9)

    # **READ AND REPORTED, NEVER A GATE.** A refusal here would make a run's
    # success depend on ambient machine state -- a store that resumed this
    # morning refusing this afternoon -- which is the same failure that ruled
    # out an available-RAM default. `available_ram_bytes` is not cgroup-aware
    # and says so, so inside a limit this warns less often than it should; a
    # missing warning is the safe direction for something that must not act.
    available_bytes = machine.available_ram_bytes()
    budget_warning = None
    if available_bytes < budget_bytes:
        budget_warning = (
            f"the memory budget is {resolved_budget_gb:g} GB ({budget_bytes} B) "
            f"and this machine reports {available_bytes / 1e9:.3g} GB available "
            "right now, so this run may swap or be killed by the OOM killer. "
            "Set --memory-budget below the available figure to size the tile "
            "for what is free. The budget defaults to a fraction of TOTAL RAM, "
            "so that the tile side a resume derives does not move with whatever "
            "else is running"
        )

    # THE BUDGET IS ESTABLISHED BEFORE LAYER 3, because layer 3 is where the
    # observed-versus-requested check reports, and it can only report on limits
    # that have been set. Entering it can itself raise a layer-3 error: numba
    # refuses a request larger than the machine allows.
    with thread_budget(config.threads) as budget:
        observed = (
            budget.observed
            if observed_thread_limits is None
            else observed_thread_limits
        )

        # LAYER 3 BEFORE THE OPEN. Every check that can fail here is
        # data-independent, so a config fault is reported as a config fault even
        # when the data is also unusable.
        check_semantics(config, observed_thread_limits=observed)

        with budget.phase(Phase.ASSEMBLE):
            handle = open_input(config.data_uri, config.variable)
            contract = check_input_contract(handle)

            # The fingerprint is taken AFTER the contract, never before: 13.7.
            components = geometry_components(handle)
            rollup = geometry_hash(components)

        # The lint needs a sampling interval, so it cannot run in a data-free
        # layer. It is a warning and cannot move the exit code, which is what
        # makes running it here safe -- see `batch.validation`'s docstring.
        warnings = identifiability_warnings(config, contract.median_dt)

        # The decimal-year axis is what every downstream consumer needs and
        # `ContractReport` carries only its endpoints, so it is converted once
        # here rather than per tile -- the conversion is under ALGORITHM_VERSION
        # and doing it twice would be two derivations of fit identity.
        geometry = run_geometry(config, handle, contract)
        years = geometry.years
        signal = geometry.signal
        columns = geometry.k_beta
        specs = geometry.specs
        index = geometry.index

        # MEASURED AFTER THE OPEN AND BEFORE THE STORE, in a child of its own:
        # the input's handles, consolidated metadata and decompression buffers
        # are resident and scale with the store rather than with the tile, so a
        # floor taken before the open attributes them to the tile term.
        measured_floor = floor if floor is not None else _resolve_floor(config)
        grid = (contract.n_y, contract.n_x)

        # **IDENTITY FIRST, GEOMETRY SECOND -- AND THE ORDER MATTERS MORE SINCE
        # TASK 2 THAN IT DID BEFORE IT.** The tiling step used to be infallible
        # in practice, so deriving a side above the gates was harmless. Now
        # `tile_side_for` refuses a budget that does not clear the floor, and a
        # derivation above the gates makes a run with a wrong candidate list AND
        # a small budget report the budget -- sending the user to the wrong
        # question. Design doc 13.7 already prescribes this order; it simply had
        # nothing to enforce until the geometry step could fail.
        source_attrs: dict[str, Any] | None = None
        if reuse_fits_from is not None:
            check_source(reuse_fits_from, config, geometry_hash=rollup)
            source_attrs = dict(zarr.open_group(str(reuse_fits_from), mode="r").attrs)
        if Path(store_path).exists():
            check_resume(store_path, config, geometry_hash=rollup)

        # **THE CALIBRATION RUNS AFTER THE IDENTITY GATES AND BEFORE THE
        # GEOMETRY, WHICH IS 13.7's ORDER AND MATTERS MORE HERE THAN ANYWHERE
        # ELSE.** It is the geometry step's input -- it produces the per-series
        # cost the side derives from -- and it is the most expensive thing this
        # function can do, ~26.5 h at 9.4's configuration on the development
        # box. A run with a wrong candidate list must be refused before it
        # spends that, not after.
        tile_side_basis = TileSideBasis.DEFAULT
        calibration_record: dict[str, Any] | None = None
        calibration_warning: str | None = None
        calibrated_bytes_per_series: float | None = None
        if wants_calibration:
            fit_identity = config.fit_hash(rollup)
            if fit_identity is None:  # pragma: no cover - narrowing
                raise ValidationError(
                    ValidationLayer.SEMANTIC,
                    "a calibration keys on fit identity and this run has none",
                )
            versions_rollup, versions = calibration_cache.versions_digest()
            key = calibration_cache.cache_key(
                fit_hash=fit_identity,
                placement=str(SolverPlacement.PER_SERIES_LIVE),
                # THE SAME RESOLUTION `fit` MAKES. An injected engine is refused
                # above, so this reads the engine the calibration's children
                # will build rather than one this run was handed.
                engine_label=str(memory_engine_label(KalmanEngine())),
                # **READ FROM THE PLATFORM, NEVER FROM THE CONFIG.** The
                # fingerprint is self-reported at its own boundary and that is
                # harmless while it reaches `run_hash` alone; the moment this
                # key reads it, it is an identity, and a config-supplied one
                # would let one machine's calibration be reused on another.
                machine=machine.fingerprint(),
                versions=versions_rollup,
            )
            cache = (
                calibration_cache.cache_path(store_path)
                if calibration_cache_path is None
                else Path(calibration_cache_path)
            )
            cached = None if recalibrate else calibration_cache.load(cache, key)
            calibration_result = cached
            if calibration_result is None:
                calibration_result = measure_calibration(
                    config_path=str(config_path),
                    floor=measured_floor,
                    ladder=(
                        CALIBRATION_LADDER
                        if calibration_ladder is None
                        else calibration_ladder
                    ),
                )
                calibration_cache.store(
                    cache, key, calibration_result, versions=versions
                )
            # **THE REFERENCE IS THE FIGURE THE TILING WOULD HAVE USED**, taken
            # from the same `tile_kwargs()` the derivation below reads, not
            # reassembled from the geometry's fields. Two spellings of the
            # analytic per-series cost would eventually be two numbers, and the
            # band would then be checked against one the run never uses.
            model = geometry.tile_kwargs()
            calibration_warning = calibration_cache.unusable_reason(
                calibration_result,
                analytic=resident_bytes_per_series(
                    k_beta=model["k_beta"],
                    p_max=model["p_max"],
                    n_time=model["n_time"],
                    n_models=model["n_models"],
                ),
            )
            if calibration_warning is None:
                calibrated_bytes_per_series = calibration_result.slope_bytes_per_series
                tile_side_basis = (
                    TileSideBasis.CACHED
                    if cached is not None
                    else TileSideBasis.MEASURED
                )
            calibration_record = calibration_cache.provenance(
                key=key,
                result=calibration_result,
                digest=versions_rollup,
                versions=versions,
                rejected=calibration_warning,
            )

        # **p_max IS THE WIDEST CANDIDATE'S FREE PARAMETER COUNT AND d IS THE
        # WIDEST CANDIDATE'S STATE DIMENSION, NEITHER THE FIRST'S.** The tile
        # holds whichever candidate is being fitted and `fit` sizes every output
        # slot to the widest, so a budget taken from `white` (d = 0) would size a
        # tile the `white + matern12` pass cannot hold.
        #
        # **THE BUDGET IS 10**9 BYTES PER `memory_budget_gb`, NOT 1024**3.** The
        # field is named `_gb` and SI GB is 10**9; every published tile side in
        # this project is a 10**9 number; and the Hardware table already reports
        # this machine as 16.54 GB, which is the SI reading. It was `1024**3`
        # until 2026-08-15, i.e. 7.4% more bytes than the published example, and
        # correcting it LOWERS the budget -- the safe direction against a
        # constraint the design doc calls hard.
        #
        # **A RECOMPUTE DERIVES NOTHING AND MUST NOT BE REFUSED FOR ITS BUDGET.**
        # Its tile side is READ BACK from the source -- the copied groups must be
        # byte-identical, which needs identical shard geometry -- and **the
        # budget's rule bounds a FIT's resident set, which a recompute does not
        # have.** Running the budget arithmetic anyway would refuse a legitimate
        # recompute on a machine too small to have fitted the source, which is
        # exactly the case `--reuse-fits-from` exists to serve. Consequence,
        # stated: the new store carries the source's tile side, so a later
        # FITTING run against it under a smaller budget refuses -- correctly.
        if reuse_fits_from is not None:
            side = reuse.source_tile_side(reuse_fits_from)
        else:
            try:
                side = tile_side_for(
                    # THE RESOLVED VALUE, WHICH IS WHY A `None` CONFIG CANNOT
                    # BYPASS THE REFUSAL BELOW: there is one budget in this
                    # function and every consumer reads it.
                    budget_bytes=budget_bytes,
                    floor=measured_floor,
                    # None on every path but a calibration whose slope cleared
                    # the band, and then it is the ONE thing the measurement
                    # changes. The intercept stays out: it is the floor under
                    # the calibration's conditions and not the production one,
                    # which `memory.CalibrationResult` says in its own docstring.
                    per_series_bytes=calibrated_bytes_per_series,
                    **geometry.tile_kwargs(),
                )
            except BudgetTooSmallError as error:
                # STAGED AS LAYER 3, NOT LEFT AS A ValueError. It is a
                # cross-field sense failure -- this budget against this machine's
                # floor -- and exit code 3 is what a caller uses to tell "your
                # request is wrong" from "your data is wrong". Dispatching on the
                # distinct type rather than on the message is (c2).
                raise ValidationError(ValidationLayer.SEMANTIC, str(error)) from error
        # THE RESUME GATE'S GEOMETRY HALF. Its identity half ran above, before
        # the derivation; a store's shards -- and therefore what its completion
        # bits index -- were fixed when it was created, so its tile side is what
        # a resume must use, and the derived side is only what that is compared
        # against.
        # **THE BASIS IS 13.4's THREE-STATE VOCABULARY AND ALL THREE ARE
        # REACHABLE SINCE TASK 5**: `cached` when this run read a calibration
        # out of the cache, `measured` when it took one this session, `default`
        # when the analytic formula sized the tile -- which includes a run whose
        # measurement the band refused.
        #
        # **RESOLVED ONCE AND READ TWICE, WHICH IS THE POINT OF THE VARIABLE.**
        # The resume gate names calibration as a cause and the store records
        # which basis produced its side; both need the same answer, and
        # computing it inline at each site would be two descriptions of one
        # subject -- the shape three separate findings in this sub-phase had.
        #
        # **A RECOMPUTE COPIES THE SOURCE'S BASIS, AND THAT IS NOT A THIRD
        # STATE.** `--reuse-fits-from` READS the side back out of the source
        # (a1) rather than deriving one, so the side in this store is literally
        # the source's and so is its provenance. Writing DEFAULT would claim
        # this run derived the side analytically when it derived nothing -- and
        # the resume gate, comparing bases, would read a basis change that never
        # happened. A valid source is v5 by `check_source`'s schema gate, so the
        # key is always there.
        effective_basis = (
            tile_side_basis
            if source_attrs is None
            else TileSideBasis(source_attrs["tile_side_basis"])
        )
        if Path(store_path).exists():
            side = resume_tile_side(
                store_path,
                derived_side=side,
                grid=grid,
                derived_basis=effective_basis,
            )
        tiles = list(tile_grid(grid[0], grid[1], side))
        amplification = read_amplification(handle, tiles[0])

        attrs = provenance_attrs(
            config,
            geometry_components=components,
            thread_limits=dict(observed),
            read_amplification=amplification,
            unique_dt_count=contract.unique_dt,
            tile_sides={"shared": side},
            # Resolved above, once, and read by the resume gate as well. See
            # `effective_basis` for why a recompute carries the SOURCE's.
            tile_side_basis=effective_basis,
            calibration=calibration_record,
            memory_budget_requested_gb=requested_budget_gb,
            max_iter=iteration_cap,
            floor=measured_floor,
            source=None
            if source_attrs is None
            else {
                "path": reuse_fits_from,
                "fit_hash": source_attrs["fit_hash"],
                "compat_hash": source_attrs["compat_hash"],
                "run_hash": source_attrs["run_hash"],
            },
        )
        if not Path(store_path).exists():
            create_store(
                store_path,
                specs=specs,
                criteria=config.criteria,
                shape=StoreShape(
                    n_y=grid[0], n_x=grid[1], n_beta=columns, tile_side=side
                ),
                attrs=attrs,
            )

        has_trend = any(type(term).__name__ == "Trend" for term in signal.terms)
        done = completed_tiles(store_path)
        written = 0
        skipped = 0
        with flush_on_sigterm() as termination:
            for tile in tiles:
                position = tile_index(tile, side)
                if done[position]:
                    skipped += 1
                    continue
                if reuse_fits_from is None:
                    with budget.phase(Phase.ASSEMBLE):
                        block = assemble_tile(handle, tile)
                    with budget.phase(Phase.FIT):
                        result = fit(
                            block,
                            years,
                            signal,
                            specs,
                            Criterion(config.criteria[0]),
                            mask=np.isfinite(block),
                            objective=Objective(config.objective),
                            engine=engine,
                            max_iter=iteration_cap,
                        )
                    write_tile(
                        store_path,
                        tile,
                        result,
                        criteria=config.criteria,
                        index=index,
                        has_trend=has_trend,
                    )
                else:
                    # THE FIT STEP IS REPLACED BY A READ, and nothing else about
                    # the loop changes -- same write path for /selection/, same
                    # bitmap, same ordering. `engine` is deliberately unused
                    # here, which is what the raising stub proves.
                    _recompute_tile(reuse_fits_from, store_path, tile, config=config)
                if on_tile_written is not None:
                    on_tile_written(tile)
                # THE ONE SITE THAT SETS A BIT, AND IT IS REACHED ONLY BY
                # `write_tile` RETURNING. There is no branch above it that
                # writes some of a tile and arrives here.
                mark_complete(store_path, position)
                written += 1
                # AFTER THE BIT, NEVER BETWEEN THE TWO WRITES. The handler
                # records and returns, so this is the first moment a recorded
                # SIGTERM can act, and acting here loses no tile.
                if termination.received:
                    break

        return RunReport(
            k_beta=columns,
            tile_side=side,
            tiles_total=len(tiles),
            tiles_written=written,
            tiles_skipped=skipped,
            interrupted=written + skipped < len(tiles),
            sigterm_armed=termination.armed,
            config=config,
            memory_budget_requested_gb=requested_budget_gb,
            budget_warning=budget_warning,
            calibration_warning=calibration_warning,
            config_path=Path(config_path),
            store_path=Path(store_path),
            contract=contract,
            components=components,
            geometry_hash=rollup,
            fit_hash=config.fit_hash(rollup),
            compat_hash=config.compat_hash(rollup),
            run_hash=config.run_hash(
                machine=machine.fingerprint(), geometry_hash=rollup
            ),
            machine=machine.fingerprint(),
            thread_limits=dict(observed),
            phase_seconds={
                phase.value: seconds for phase, seconds in budget.seconds.items()
            },
            warnings=warnings,
        )
