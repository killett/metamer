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

**WHAT THIS DOES NOT DO YET.** The resume gate is Task 11, the tiling loop is
Task 6 and the store is Task 8, so a clean run today validates, fingerprints and
reports, and writes nothing. It says so on stdout rather than leaving a user to
infer it from an absent directory.

**THE ENGINE MUST STAY INJECTABLE, AND THAT LANDS AT TASK 9.** `fit(engine=...)`
is the seam the raising stub fixture is delivered through, and a runner that
builds its engine internally from the config makes every downstream "no fit ran"
assertion vacuous. Nothing here fits, so an `engine=` parameter now would be one
no test could make bite -- a hook promised in argument form. **Task 9 is the
first task that fits and is where it must arrive.**
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from metamer.batch.geometry import geometry_components, geometry_hash
from metamer.batch.input import ContractReport, open_input
from metamer.batch.input import check_contract as check_input_contract
from metamer.batch.threads import Phase, thread_budget
from metamer.batch.validation import (
    ValidationError,
    ValidationLayer,
    check_semantics,
    identifiability_warnings,
    load_config,
)
from metamer.config.model import Config
from metamer.core import machine
from metamer.core.lint import Finding


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
) -> RunReport:
    """Validate a configuration against its input and report the hashes.

    Args:
        config_path: Path to a `.toml` or `.json` config.
        store_path: Where the store goes. Echoed today; Task 8 creates it.
        memory_budget_gb: Overrides the config's `memory_budget_gb`. It is
            run-relevant, so the override reaches `run_hash` and neither gate.
        observed_thread_limits: Observed thread limit per loaded library.
            **The run observes its own by default** through
            `batch.threads.thread_budget`; supplying them overrides the
            observation and exists so a test can construct a mismatch this
            machine cannot produce.

    Returns:
        What the run established.

    Raises:
        ValidationError: Layers 1-3 -- the config. Exit code 3.
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

        return RunReport(
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
