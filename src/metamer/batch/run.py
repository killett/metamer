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
from metamer.batch.validation import (
    ValidationError,
    ValidationLayer,
    check_semantics,
    identifiability_warnings,
    load_config,
)
from metamer.config.model import Config
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
        observed_thread_limits: Observed thread limit per loaded library. Task 5
            supplies these through `threadpoolctl`; None skips the check, and
            `check_thread_limits` states what that costs.

    Returns:
        What the run established.

    Raises:
        ValidationError: Layers 1-3 -- the config. Exit code 3.
        InputContractError: Layer 4 -- the data. Exit code 4.
    """
    config = load_config(config_path)
    if memory_budget_gb is not None:
        config = _with_memory_budget(config, memory_budget_gb)

    # LAYER 3 BEFORE THE OPEN. Every check that can fail here is
    # data-independent, so a config fault is reported as a config fault even
    # when the data is also unusable.
    check_semantics(config, observed_thread_limits=observed_thread_limits)

    handle = open_input(config.data_uri, config.variable)
    contract = check_input_contract(handle)

    # The fingerprint is taken AFTER the contract, never before: section 13.7.
    components = geometry_components(handle)
    rollup = geometry_hash(components)

    # The lint needs a sampling interval, so it cannot run in a data-free layer.
    # It is a warning and cannot move the exit code, which is what makes running
    # it here safe -- see `batch.validation`'s module docstring.
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
        run_hash=config.run_hash(geometry_hash=rollup),
        warnings=warnings,
    )
