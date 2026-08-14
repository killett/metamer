"""Staged validation: which layer refused, and which exit code that becomes.

Design doc section 13.2 stages validation into four layers, and **each stage
names itself in its error**, because "your config is invalid" before a ten-hour
job needs to say which layer and why.

    1  FILE      the file parses, and it is a .toml or a .json
    2  SCHEMA    pydantic: types, ranges, enums, unrecognized keys
    3  SEMANTIC  cross-field and environment sense -- needs no data
    4  DATA      data-dependent; stage 4a is its first stage

**THE STAGING IS THE STRUCTURE; THE CHECKS ACCRETE.** Layer 3 carries exactly
what Phase 2a can trigger. Codes 3 and 4 cannot be distinguished without the
staging, which is why the split exists even where a layer holds two checks.

**LAYER 3 IS DATA-INDEPENDENT IN EVERYTHING THAT CAN FAIL, AND THE LINT IS THE
EXCEPTION THAT PROVES IT.** `lint(spec, sampling_interval)` needs a median
observation spacing -- a property of the data -- and **raises** when it is not
finite and positive, deliberately, because a diagnostic reporting "clean"
because it could not run is worse than one that stops. So the identifiability
lint cannot run before the data is open. It is a **warning**: it cannot move the
exit code, so running it after stage 4a cannot corrupt the layer-3/layer-4
attribution, and every layer-3 check that can **fail** stays upstream of the
open. That is what makes a run with both a bad config and bad data report the
config. Design doc section 13.2 heads layer 3 "Semantic, data-independent" and
lists the lint inside it; this is the resolution of that contradiction, and
splitting on *what fails* rather than on *when it runs* is what preserves the
document's intent.

**TWO EXIT CODES COLLIDE WITH CODES NOBODY WRITES, AND ONE IS FIXED HERE.**
argparse exits **2** on a usage error and 2 means "aborted early", so
`metamer.__main__` overrides `ArgumentParser.error` to exit `CONFIG_INVALID`.
Python exits **1** on an unhandled exception and 1 means "completed with
failures above threshold"; that one is not fixable inside a taxonomy with no
internal-error code. It is harmless while 1 is unreachable -- so in Phase 2a any
observed 1 is a crash -- and stops being harmless in sub-phase 2e, which is
where the requirement is recorded.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import IntEnum
from pathlib import Path

import pydantic

from metamer.batch.input import InputContractError
from metamer.config.model import PER_POINT_TERM_PREFIX, Config, StampedKeyError, load
from metamer.core.criteria import Criterion
from metamer.core.lint import Finding, lint
from metamer.core.memory import Backend, resident_bytes_per_series, tile_side

# Design doc section 9.4's worked example. The per-point refusal quotes tile
# sizes, and they are COMPUTED from these rather than written down, so a change
# to the memory formula moves the message instead of dating it.
_WORKED_EXAMPLE = {"d": 3, "k_beta": 4, "p": 4, "n_time": 630, "n_models": 12}
_WORKED_EXAMPLE_BUDGET = 10**9
_WORKED_EXAMPLE_BACKEND = Backend.NUMPY_BATCHED
"""Which backend the quoted tile sizes belong to.

**THE PUBLISHED 338 AND 186 ARE PATH A's NUMBERS AND NOTHING SAID SO.**
Recomputed 2026-08-12: `NUMPY_BATCHED` gives 338 shared / 186 per-point, a 3.30x
change in tile area, while `COMPILED` gives 361 / 189 and 3.65x. Design doc
section 13.4, the Phase 2a plan and PROGRESS all quote the first pair without
naming a backend. This is the backend `fit()` actually defaults to today
(`KalmanEngine`), so it is the pair a 2a run would plan against -- and the
message names it, because a tile size without its backend is the same shape of
claim as a benchmark ratio without its harness.
"""


class ValidationLayer(IntEnum):
    """Which stage refused. Numbered as design doc section 13.2 numbers them."""

    FILE = 1
    SCHEMA = 2
    SEMANTIC = 3
    DATA = 4


class ExitCode(IntEnum):
    """The process exit codes, as an enum and a return value.

    **All five land now**, even though sub-phase 1 produces only three of them,
    because retrofitting an exit code means revisiting every early return -- the
    argument that made the failure taxonomy a Phase 1 deliverable.

    **`ABORTED_EARLY` ACQUIRED A PRODUCER AT TASK 10, AHEAD OF THE MECHANISM
    THIS DOCSTRING ORIGINALLY NAMED.** It said both 1 and 2 waited on sub-phase
    2e's failure-rate threshold and early-abort criterion. Design doc 14.3
    defines 2 more broadly than that mechanism -- *"aborted early --
    resumable"*, whose stated purpose is to let a resuming script tell an
    abort apart from a rejected config -- and **a run flushed by SIGTERM is
    exactly that case**: its completed tiles are on disk with their bits set and
    the same command finishes them. Exiting 0 there would report a store as
    complete when it is not. 2e's early abort becomes the second producer.

    `COMPLETED_WITH_FAILURES` still has none: it needs the failure-rate
    threshold, which is 2e's. It is pinned as an interface rather than tested
    through a run, and while it has no producer, an observed 1 is CPython's
    unhandled-exception code -- the collision named in `__main__`.
    """

    OK = 0
    COMPLETED_WITH_FAILURES = 1
    ABORTED_EARLY = 2
    CONFIG_INVALID = 3
    DATA_INVALID = 4


class ValidationError(Exception):
    """A staged validation failure that names its own layer.

    Layer 4 has its own type -- `InputContractError`, from Task 2 -- and is not
    reported through this one. Exit code 4 rests on that type being raised for
    every stage-4a failure including the ones helpers raise, so folding the two
    into one class would remove the distinction the ordering relies on.

    Attributes:
        layer: Which stage refused.
    """

    def __init__(self, layer: ValidationLayer, message: str) -> None:
        """Build the error, prefixing the message with its layer.

        Args:
            layer: Which stage refused.
            message: What it refused and why.
        """
        self.layer = layer
        super().__init__(f"layer {layer.value} ({layer.name.lower()}): {message}")


def layer_of(error: BaseException) -> ValidationLayer:
    """Return the validation layer an exception belongs to.

    **THE STAGED TYPES ARE ENUMERATED, AND EVERYTHING ELSE IS REFUSED.** A
    mapping written as "anything that is not a `ValidationError` is a data
    error" would file an internal `KeyError` -- an unknown candidate kind
    produces one, from the kernel registry -- as "your data is wrong", sending
    the user to inspect a perfectly good input.

    Args:
        error: The exception to classify.

    Returns:
        Its layer.

    Raises:
        TypeError: If the exception is not one of the staged types.
    """
    if isinstance(error, ValidationError):
        return error.layer
    if isinstance(error, InputContractError):
        return ValidationLayer.DATA
    raise TypeError(
        f"{type(error).__name__} is not a staged validation failure; the staged "
        "types are ValidationError (layers 1-3) and InputContractError (layer 4)"
    )


def exit_code_for(error: BaseException) -> ExitCode:
    """Return the process exit code a staged failure becomes.

    Args:
        error: A staged validation failure.

    Returns:
        `CONFIG_INVALID` for layers 1-3, `DATA_INVALID` for layer 4. The split
        is the whole reason validation is staged: "your config is wrong" and
        "your data is wrong" send a user to different places.

    Raises:
        TypeError: If the exception is not one of the staged types.
    """
    if layer_of(error) is ValidationLayer.DATA:
        return ExitCode.DATA_INVALID
    return ExitCode.CONFIG_INVALID


def load_config(path: Path | str) -> Config:
    """Run validation layers 1 and 2 over a config file.

    Every failure `metamer.config.load` can produce is attributed here, and the
    two layers are distinguished by exception type rather than by message.

    Args:
        path: Path to a `.toml` or `.json` config.

    Returns:
        The validated configuration.

    Raises:
        ValidationError: Layer 1 if the file is missing, has an unrecognized
            suffix, or does not parse; layer 2 if it does not satisfy the model
            or supplies a stamped key.
    """
    try:
        return load(path)
    except FileNotFoundError as error:
        raise ValidationError(ValidationLayer.FILE, str(error)) from error
    # **BOTH SCHEMA CLAUSES SIT ABOVE THE FILE CLAUSE, AND THAT ORDER IS THE
    # WHOLE OF THE ATTRIBUTION.** `pydantic.ValidationError` is a `ValueError`
    # subclass and so is `StampedKeyError`, so a `ValueError` clause written
    # first swallows every layer-2 failure and names the file layer for a file
    # that parsed perfectly. Measured: written that way, a misspelled field
    # reported "layer 1 (file)". The two schema clauses are enumerated rather
    # than caught as one, because `StampedKeyError` is refused before pydantic
    # ever sees the mapping.
    except pydantic.ValidationError as error:
        raise ValidationError(ValidationLayer.SCHEMA, str(error)) from error
    except StampedKeyError as error:
        raise ValidationError(ValidationLayer.SCHEMA, str(error)) from error
    except ValueError as error:
        raise ValidationError(ValidationLayer.FILE, str(error)) from error


def check_thread_limits(requested: int, observed: Mapping[str, int] | None) -> None:
    """Refuse a run whose thread limits were not honoured, per library.

    **THE DETERMINISM PRECONDITION IS OBSERVED, NOT REQUESTED.**
    `OMP_NUM_THREADS=1` in provenance records a *request*, and whether it took
    effect depends on import ordering that nothing enforces -- set after numpy
    is imported it does nothing, silently. A precondition that holds for
    OpenBLAS while MKL runs multithreaded is not a precondition that holds, so
    the check is per library and the message names the offenders.

    **TASK 5 EXPOSES THE OBSERVATION; THIS IS WHAT MAKES IT A LAYER-3 FAILURE.**
    Without the attribution it ships as a bare exception with no layer attached,
    which would satisfy exit criterion 10 with something that is not a layer-3
    failure.

    Args:
        requested: The thread count the config asked for.
        observed: Observed limit per loaded library, or None when nothing has
            observed them yet. **None SKIPS THE CHECK**, and that vacuity is
            deliberate and temporary: `threadpoolctl` is Task 5's, and until it
            lands the runner has nothing to pass. It is pinned by a test so the
            state is visible in the suite rather than believed.

    Raises:
        ValidationError: Layer 3, if any observed limit differs from `requested`.
    """
    if observed is None:
        return
    offenders = {
        library: limit for library, limit in observed.items() if limit != requested
    }
    if not offenders:
        return
    detail = ", ".join(
        f"{library} reports {limit}" for library, limit in sorted(offenders.items())
    )
    raise ValidationError(
        ValidationLayer.SEMANTIC,
        f"the run requested {requested} thread(s) and the limit was not honoured: "
        f"{detail}. A limit that holds for one library while another runs "
        "multithreaded is not a limit that holds, and section 11.3's determinism "
        "guarantee rests on the OBSERVED limit rather than on the requested one",
    )


def _per_point_tile_sides() -> tuple[int, int]:
    """Return `(shared, per_point)` tile sides at the worked example.

    Computed from `memory` rather than quoted, so the refusal message cannot
    date: a change to the per-series accounting moves both numbers here.

    Returns:
        Tile side under a shared design, and under a per-point one.
    """
    return tuple(  # type: ignore[return-value]
        tile_side(
            _WORKED_EXAMPLE_BUDGET,
            resident_bytes_per_series(
                _WORKED_EXAMPLE_BACKEND, **_WORKED_EXAMPLE, per_point_design=per_point
            ),
        )
        for per_point in (False, True)
    )


def check_semantics(
    config: Config, *, observed_thread_limits: Mapping[str, int] | None = None
) -> None:
    """Run validation layer 3: cross-field and environment sense, no data.

    The checks, in the order they run. A config tripping two reports the first,
    which is deterministic and is the whole reason the order is written down.

    1. **Screening** -- refused naming the missing engine specifically, because
       a refusal that says what would lift it is planning information and one
       that does not is a wall.
    2. **Per-point regressors** -- refused naming the field and both tile
       sizes, because layer 3 knows them and "not implemented" wastes context
       the user needs to plan against a hard RAM constraint.
    3. **Candidates** -- parsed here, since `load` does not parse them, and
       refused for a malformed expression, an unknown kernel kind, or a
       duplicate by spec hash.
    4. **Criteria** -- refused for a criterion no implementation can compute.
    5. **Thread limits** -- see `check_thread_limits`.

    Args:
        config: A configuration that has passed layers 1 and 2.
        observed_thread_limits: Observed limit per loaded library, from Task 5.

    Raises:
        ValidationError: Layer 3, naming the check that refused.
    """
    if config.screening.enabled:
        raise ValidationError(
            ValidationLayer.SEMANTIC,
            "screening requires the debiased Whittle engine (Phase 4), which is "
            "not implemented. Remove the [screening] block or set "
            "screening.enabled = false to run without it",
        )

    per_point = config.per_point_regressors()
    if per_point:
        shared_side, per_point_side = _per_point_tile_sides()
        raise ValidationError(
            ValidationLayer.SEMANTIC,
            f"signal_terms declares per-point regressor field(s) "
            f"{list(per_point)} with the {PER_POINT_TERM_PREFIX!r} prefix, and "
            "per-point regressors are not implemented. **The regime is not a "
            "detail of the design matrix**: at design doc section 9.4's worked "
            f"example ({_WORKED_EXAMPLE['d']=}, {_WORKED_EXAMPLE['k_beta']=}, "
            f"{_WORKED_EXAMPLE['p']=}, {_WORKED_EXAMPLE['n_time']=}, "
            f"{_WORKED_EXAMPLE['n_models']=}, a "
            f"{_WORKED_EXAMPLE_BUDGET / 10**9:g} GB budget, backend "
            f"{_WORKED_EXAMPLE_BACKEND.value}) it takes tile_side from "
            f"{shared_side} to {per_point_side}, a "
            f"{(shared_side / per_point_side) ** 2:.2f}x change in tile area "
            "from one declaration. Drop the declaration to fit with a shared "
            "design",
        )

    try:
        spec_hashes = config.candidate_spec_hashes()
    except (ValueError, KeyError) as error:
        # BOTH TYPES, AND THE `KeyError` IS THE ONE THAT WOULD HAVE ESCAPED.
        # A malformed expression is a `ValueError` from the restricted AST walk;
        # an unknown kernel kind is a `KeyError` from the registry. An unstaged
        # `KeyError` is an unhandled exception, which Python reports as exit
        # code 1 -- "completed with failures above threshold" in this taxonomy.
        raise ValidationError(
            ValidationLayer.SEMANTIC,
            f"a candidate could not be resolved: {error}",
        ) from error

    seen: dict[str, int] = {}
    for index, spec_hash in enumerate(spec_hashes):
        if spec_hash in seen:
            raise ValidationError(
                ValidationLayer.SEMANTIC,
                f"candidates {seen[spec_hash]} ({config.candidates[seen[spec_hash]]!r}) "
                f"and {index} ({config.candidates[index]!r}) are the same model: both "
                f"have spec_hash {spec_hash}. The model axis is positional, so a "
                "duplicate is a wasted slice of every stored array rather than a "
                "second opinion",
            )
        seen[spec_hash] = index

    implemented = {member.value for member in Criterion}
    unknown = [name for name in config.criteria if name not in implemented]
    if unknown:
        raise ValidationError(
            ValidationLayer.SEMANTIC,
            f"criteria {unknown} name no implemented criterion. Computable "
            f"criteria are {sorted(implemented)}, under either objective. "
            "(Design doc section 13.2's other examples -- TIC, which needs a "
            "Hessian, and cross-validation, which needs a splitting strategy -- "
            "are not implemented at all, so no criterion is objective-specific "
            "today.)",
        )

    check_thread_limits(config.threads, observed_thread_limits)


def identifiability_warnings(
    config: Config, sampling_interval: float
) -> tuple[Finding, ...]:
    """Run the identifiability lint over every candidate, as warnings only.

    Design doc section 4.8's *a priori* half. It warns and never blocks: a user
    who knowingly wants a degenerate model can still fit it, and the *a
    posteriori* half (`optimize.HESSIAN_COND_LIMIT` reporting
    `DEGENERATE_HESSIAN`) reports the same phenomenon after the fact.

    **IT RUNS AFTER STAGE 4a BECAUSE IT NEEDS A SAMPLING INTERVAL**, which is a
    property of the data. Since it cannot move the exit code, running it there
    cannot make a data fault report as a config fault -- see this module's
    docstring for why that is the resolution rather than a compromise.

    Args:
        config: A configuration that has passed layer 3.
        sampling_interval: Median observation spacing in decimal years, from
            stage 4a's contract report.

    Returns:
        Every finding, across every candidate, in candidate order.

    Raises:
        ValidationError: Layer 4, if the sampling interval is unusable. The
            lint raises rather than returning an empty list, because a
            diagnostic that reports "clean" because it could not run is worse
            than one that stops -- and an unusable interval is a fact about the
            data, so it is layer 4 and not layer 3.
    """
    findings: list[Finding] = []
    for spec in config.process_specs():
        try:
            findings.extend(lint(spec, sampling_interval))
        except ValueError as error:
            raise ValidationError(ValidationLayer.DATA, str(error)) from error
    return tuple(findings)
