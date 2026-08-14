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

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import zarr

from metamer.batch import reuse
from metamer.batch.completion import (
    completed_tiles,
    flush_on_sigterm,
    mark_complete,
    resume_tile_side,
    tile_index,
)
from metamer.batch.geometry import geometry_components, geometry_hash
from metamer.batch.input import ContractReport, open_input
from metamer.batch.input import check_contract as check_input_contract
from metamer.batch.ragged import build_ragged_index, noise_extent
from metamer.batch.resume import check_resume, check_source
from metamer.batch.store import StoreShape, create_store, provenance_attrs
from metamer.batch.threads import Phase, thread_budget
from metamer.batch.tiling import (
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
from metamer.core.engines.protocol import Engine
from metamer.core.fit import fit
from metamer.core.lint import Finding
from metamer.core.memory import Backend
from metamer.core.signal import k_beta as signal_k_beta
from metamer.core.statespace import StateSpace


@dataclass(frozen=True)
class RunReport:
    """What a run established. Everything here reaches provenance.

    Attributes:
        config: The EFFECTIVE configuration -- the file's contents with any
            command-line override applied, because that is what the run used
            and therefore what `run_hash` must describe.
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


def _with_memory_budget(config: Config, budget_gb: float) -> Config:
    """Return `config` with its memory budget replaced, RE-VALIDATED.

    **`model_copy` would not re-validate**, so a budget of 0 or -1 typed on the
    command line would be accepted while the identical value in the file is
    refused -- the same run valid or invalid depending on where the number was
    typed. Round-tripping through `model_validate` puts the override through the
    same constraint as the field.

    Args:
        config: The configuration as loaded.
        budget_gb: The command-line budget, in GB.

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
        raise ValidationError(
            ValidationLayer.SCHEMA, f"--memory-budget: {error}"
        ) from error


def run(
    config_path: Path | str,
    store_path: Path | str,
    *,
    memory_budget_gb: float | None = None,
    observed_thread_limits: Mapping[str, int] | None = None,
    engine: Engine | None = None,
    on_tile_written: Callable[[Tile], None] | None = None,
    reuse_fits_from: Path | str | None = None,
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

    Returns:
        What the run established.

    Raises:
        ValidationError: Layers 1-3 -- the config, and a resume whose stored
            tile side this run's budget cannot hold. Exit code 3.
        InputContractError: Layer 4 -- the data. Exit code 4.
    """
    config = load_config(config_path)
    if memory_budget_gb is not None:
        config = _with_memory_budget(config, memory_budget_gb)

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
        years = to_decimal_years(handle.dataset["time"].values)
        signal = config.signal_spec()
        columns = signal_k_beta(signal, years)
        specs = list(config.process_specs())
        index = build_ragged_index(specs, noise_extent)

        # **d IS THE WIDEST CANDIDATE'S STATE DIMENSION, NOT THE FIRST'S.** The
        # tile holds whichever candidate is being fitted, so a budget taken from
        # `white` (d = 0) would size a tile the `white + matern12` pass cannot
        # hold. Same argument as budgeting against p_max.
        state_dims = [StateSpace.from_spec(spec).state_dim for spec in specs]
        side = tile_side_for(
            budget_bytes=int(config.memory_budget_gb * 1024**3),
            backend=Backend.NUMPY_BATCHED,
            d=max(state_dims),
            k_beta=columns,
            p=max(index.extents),
            n_time=contract.n_time,
            n_models=len(specs),
        )
        grid = (contract.n_y, contract.n_x)
        # THE SOURCE IS VERIFIED BEFORE ANYTHING IS READ FROM IT, and its tile
        # side is READ BACK rather than re-derived: the copied groups must be
        # byte-identical to the source, which needs identical shard geometry,
        # and the budget's rule bounds a FIT's resident set, which a recompute
        # does not have. Consequence, stated: the new store carries the source's
        # tile side, so a later fitting run against it under a smaller budget
        # refuses -- correctly, because that run would fit.
        source_attrs: dict[str, Any] | None = None
        if reuse_fits_from is not None:
            check_source(reuse_fits_from, config, geometry_hash=rollup)
            side = reuse.source_tile_side(reuse_fits_from)
            source_attrs = dict(zarr.open_group(str(reuse_fits_from), mode="r").attrs)
        # THE RESUME GATE, IN THE ENTRY CONTRACT'S ONE POSITION FOR IT: after
        # the hashes, before the tiling. **Identity first, geometry second** -- a
        # store whose fits are unusable says so before it says anything about
        # tile sizes. A store's shards, and therefore what its completion bits
        # index, were fixed when it was created, so its tile side is what a
        # resume must use.
        if Path(store_path).exists():
            check_resume(store_path, config, geometry_hash=rollup)
            side = resume_tile_side(store_path, derived_side=side, grid=grid)
        tiles = list(tile_grid(grid[0], grid[1], side))
        amplification = read_amplification(handle, tiles[0])

        attrs = provenance_attrs(
            config,
            geometry_components=components,
            thread_limits=dict(observed),
            read_amplification=amplification,
            unique_dt_count=contract.unique_dt,
            tile_sides={"shared": side},
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
