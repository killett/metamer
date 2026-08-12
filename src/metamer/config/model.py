"""The run configuration, and the only path from a file to a set of hashes.

`load(path)` is the sole constructor a run uses:

    tomllib -> pydantic -> hashing.normalize -> canonical_json -> three hashes

**NO PRODUCTION PATH CONSTRUCTS A `Config` INLINE.** Tests may build one for
unit purposes; every integration test and every exit criterion loads from a real
file, because a `compat_hash`-only difference proves nothing unless it survived
the actual normalizer.

**THE MODEL IS HASHED, NOT THE FILE TEXT.** Comments, key order, whitespace and
explicit-versus-default all normalize away. Hashing the bytes would invalidate a
10^7-point store on a comment.

**THE PAYLOAD IS FLAT, AND NESTED BLOCKS ARE FLATTENED TO `block_field`.**
Compat relevance is an allowlist and membership is the entire mechanism, so a
nested mapping under one allowlisted key would make membership implicit for
everything inside it -- add a field to that block later and it becomes fit
identity by accident. The five fit-relevant warm-start settings are five names
in `FIT_RELEVANT_FIELDS`; the audit settings are their own block and appear in
neither allowlist.
"""

from __future__ import annotations

import json
import tomllib
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

import metamer
from metamer.config.candidates import parse_candidate
from metamer.core import hashing
from metamer.core.terms import ProcessSpec

_STAMPED_KEYS = (hashing.ALGORITHM_VERSION_KEY, hashing.REGISTRY_VERSION_KEY)

_STRICT = ConfigDict(extra="forbid", frozen=True)
"""Every block refuses unknown keys.

**THIS IS THE SECOND OF TWO DELIBERATE GUARDS AGAINST THE SAME DEFECT, AND THE
REDUNDANCY IS THE POINT.** `hashing._subset` raises when an allowlisted field is
ABSENT; `extra="forbid"` raises when an unrecognized field is PRESENT. The
failure they jointly close is one typo: `data_url` for `data_uri` demotes the
data source to provenance-only, at which point two runs over different data
share a `fit_hash` and reuse each other's fits.

Either guard alone catches it here, so a mutation of one alone will not bite.
**That is defence in depth, not dead code** -- do not remove one on the grounds
that the other covers it. They are cross-referenced in both directions so a
later simplification sees both.
"""


class WarmStart(BaseModel):
    """Warm-start settings; every field here is fit identity.

    §11.1 settles it: a stale warm start produces converged-looking fits at the
    wrong optimum, the worst failure mode in the system. All five reach
    `FIT_RELEVANT_FIELDS` as flattened `warm_start_*` keys.

    **The audit settings are NOT here, and that is structural rather than
    tidy.** Read loosely, the same argument sweeps them in, and then re-running
    a hysteresis audit at a different subsample size invalidates the store it is
    auditing. Keeping them in a separate block means the flattening cannot
    gather them by accident. See `Audit`.

    Attributes:
        enabled: Whether pass 2 warm-starts from pass 1 at all.
        coarse_stride: Pass 1's stride in dataset index space.
        interpolation_rule: How a fine point picks its coarse source. Only
            `nearest_valid` exists, and it is hashed anyway so a second rule
            cannot silently share a store with the first.
        spiral_bound: Maximum search radius, in coarse index steps, before the
            search gives up and the moment-init ladder runs with its rung
            recorded.
        tie_break: Ordering among equidistant coarse points.
    """

    model_config = _STRICT

    enabled: bool = True
    coarse_stride: int = Field(default=8, ge=1)
    interpolation_rule: Literal["nearest_valid"] = "nearest_valid"
    spiral_bound: int = Field(default=4, ge=1)
    tie_break: Literal["lowest_yx"] = "lowest_yx"


class Audit(BaseModel):
    """Hysteresis-audit settings; none of these is fit identity.

    They govern how the §11.2 audit MEASURES a store, not how any fit was
    computed, so an audit re-run at a different subsample size must leave the
    store it audits resumable. `tests/test_config.py` asserts that changing
    either moves neither `fit_hash` nor `compat_hash`, which is what makes the
    boundary against `WarmStart` executable rather than a claim.

    Attributes:
        subsample: How many points the audit compares.
        stratify: Whether the subsample is stratified across the grid.
    """

    model_config = _STRICT

    subsample: int = Field(default=0, ge=0)
    stratify: bool = False


class Detail(BaseModel):
    """`/detail/` selection. Fixed at store creation; Task 11 refuses a change.

    Neither fit-relevant nor recomputable -- the category the design doc lacked
    until Q10. A change here does not move `theta_hat`, and it cannot be
    satisfied from stored primitives either, because the Hessian at the optimum
    is not stored. So there is no resolution available and the only correct
    answer is to refuse.

    Attributes:
        region: Named region in dataset coordinates, or None.
        subsample: Deterministic subsample selector. Defaults to pass 1's coarse
            grid, because §11.2's audit wants covariances at COLD-fitted points
            and pass-1 points are cold by construction.
    """

    model_config = _STRICT

    region: str | None = None
    subsample: Literal["pass1", "none"] = "pass1"


class Screening(BaseModel):
    """Candidate screening. Present, and refused at layer 3 until Phase 4.

    The FEATURE is deferred; the REGIME is declared, per pre-flight (a3). The
    block validates so a config carrying it gets a refusal naming the missing
    engine specifically -- "screening requires the debiased Whittle engine
    (Phase 4)" -- rather than an unknown-key error that says nothing about what
    would lift it. **A refusal that says what would lift it is planning
    information; one that does not is a wall.**

    Task 4 owns the refusal. This block owning the shape is what stops Task 4
    inventing one.

    Attributes:
        enabled: Whether screening is requested.
        keep: How many candidates survive screening per point.
    """

    model_config = _STRICT

    enabled: bool = False
    keep: int = Field(default=0, ge=0)


class Config(BaseModel):
    """A validated run configuration.

    Attributes:
        data_uri: Where the input lives. **Fit-relevant until Task 3**, which
            replaces it with `geometry_hash` and demotes it to provenance. The
            gate is wrong in both directions today -- moving a file invalidates
            a valid resume, editing one in place permits an invalid one -- and a
            gate wrong both ways is not a conservative approximation of the
            right gate.
        variable: Name of the variable to fit.
        signal_terms: Deterministic design terms, in column order. **Order is
            data**: two orderings are two different design matrices, so
            `canonical_json` preserves list order rather than sorting it.
        objective: ML or REML.
        engine: Likelihood engine key.
        seed: Seed for anything stochastic.
        criteria: Information criteria to rank by. Compat-relevant and not
            fit-relevant: AIC versus BIC changes the derived arrays and changes
            nothing about where the optimizer lands.
        candidates: Noise models to compare, as sum expressions or term lists.
            **Covered by NO hash, deliberately** -- see `candidate_spec_hashes`.
        warm_start: See `WarmStart`. Fit identity.
        audit: See `Audit`. Not fit identity.
        detail: See `Detail`. Fixed at store creation.
        screening: See `Screening`. Refused at layer 3.
        memory_budget_gb: Byte budget the tile size derives from. Run-relevant:
            §11.1.1 requires peak RAM to be derivable from the budget alone.
        threads: Thread count. **Run-relevant only.** If it moved `fit_hash` the
            hash boundary would be conceding that §11.3's determinism guarantee
            does not hold -- the guarantee and the boundary are the same claim
            stated twice, and they must not drift apart.
        output: Where the store goes.
    """

    model_config = _STRICT

    data_uri: str
    variable: str
    signal_terms: tuple[str, ...]
    candidates: tuple[str | tuple[str, ...], ...]
    criteria: tuple[str, ...]

    objective: Literal["ml", "reml"] = "ml"
    engine: str = "kalman"
    seed: int = 0

    warm_start: WarmStart = Field(default_factory=WarmStart)
    audit: Audit = Field(default_factory=Audit)
    detail: Detail = Field(default_factory=Detail)
    screening: Screening = Field(default_factory=Screening)

    memory_budget_gb: float = Field(default=1.0, gt=0.0)
    threads: int = Field(default=1, ge=1)
    output: str = "out.zarr"

    def process_specs(self) -> tuple[ProcessSpec, ...]:
        """Return the candidate set as `ProcessSpec` objects, in config order.

        Returns:
            One `ProcessSpec` per candidate. Config order is preserved because
            the model axis is positional -- Task 11's resume gate compares
            candidate identity `stored[i] == requested[i]`, so reordering the
            candidate list is a different store, not the same one.
        """
        return tuple(parse_candidate(candidate) for candidate in self.candidates)

    def candidate_spec_hashes(self) -> tuple[str, ...]:
        """Return each candidate's `spec_hash`, in config order.

        **THE CANDIDATE SET IS COVERED BY NO HASH, AND THAT IS DELIBERATE.**
        §12.8 permits resuming with a SUPERSET of the stored candidates -- same
        candidates in the same order, possibly more -- and **a hash can only
        express equality**, so putting `candidates` in either allowlist would
        forbid the extension workflow outright.

        The enforcement is Task 11's positional comparison of these hashes
        against the ones in the store's root attrs: `stored[i] == requested[i]`
        for every `i < len(stored)`, and `len(requested) >= len(stored)`.

        **DO NOT "FIX" THE OMISSION BY ADDING `candidates` TO THE ALLOWLIST.**
        Its absence is what makes extension legal; the positional comparison is
        what makes it safe. Without that comparison nothing stops a resume
        writing candidate B's fits into candidate A's slice of the model axis --
        every array the right shape, every value finite, every status `ok`, and
        the store wrong in a way no invariant catches.

        Returns:
            The per-candidate spec hashes.
        """
        return tuple(spec.spec_hash() for spec in self.process_specs())

    def to_payload(self) -> dict[str, Any]:
        """Return the flat mapping `hashing.normalize` consumes.

        Nested blocks flatten to `block_field`. The two stamped keys are absent:
        `normalize` supplies them from the installed code and refuses a payload
        that carries them.

        Returns:
            The payload.
        """
        payload: dict[str, Any] = {
            "data_uri": self.data_uri,
            "variable": self.variable,
            "signal_terms": list(self.signal_terms),
            "objective": self.objective,
            "engine": self.engine,
            "seed": self.seed,
            "criteria": list(self.criteria),
            "candidates": list(self.candidate_spec_hashes()),
            "memory_budget_gb": self.memory_budget_gb,
            "threads": self.threads,
            "output": self.output,
            "metamer_version": metamer.__version__,
        }
        for block in ("warm_start", "audit", "detail", "screening"):
            model: BaseModel = getattr(self, block)
            for name, value in model.model_dump().items():
                payload[f"{block}_{name}"] = value
        return payload

    def fit_hash(self) -> str | None:
        """Hash the fields determining `theta_hat` and `log_lik`.

        Returns:
            The hash, or None once Task 3 makes `geometry_hash` a component and
            no input has been opened. **At Task 1 it is never None**, because
            `data_uri` is still the fit-relevant stand-in for the data. The
            optional return type is fixed now rather than widened later: every
            caller would otherwise be written against `str` and need revisiting
            at exactly the moment the None case starts happening.
        """
        return hashing.fit_hash(self.to_payload())

    def compat_hash(self) -> str | None:
        """Hash the fields determining the stored derived arrays.

        Returns:
            The hash, subject to the same Task 3 caveat as `fit_hash`.
        """
        return hashing.compat_hash(self.to_payload())

    def run_hash(self, machine: str | None = None) -> str:
        """Hash everything, plus runtime knobs and the machine fingerprint.

        Args:
            machine: Optional fingerprint from `hashing.machine_fingerprint`.

        Returns:
            The hash. **Provenance only, never a gate.**
        """
        return hashing.run_hash(self.to_payload(), machine)


def _read(path: Path) -> dict[str, Any]:
    """Parse a config file by suffix.

    Args:
        path: The file to read.

    Returns:
        The raw mapping.

    Raises:
        ValueError: If the suffix is neither `.toml` nor `.json`, or the file
            does not parse. The message names the suffix found and both
            accepted, because "invalid config" before a ten-hour job is not
            actionable.
    """
    if path.suffix == ".toml":
        try:
            return tomllib.loads(path.read_text())
        except tomllib.TOMLDecodeError as error:
            raise ValueError(f"{path}: invalid TOML: {error}") from error
    if path.suffix == ".json":
        try:
            parsed = json.loads(path.read_text())
        except json.JSONDecodeError as error:
            raise ValueError(f"{path}: invalid JSON: {error}") from error
        if not isinstance(parsed, dict):
            raise ValueError(f"{path}: top level must be a mapping")
        return parsed
    raise ValueError(
        f"{path}: unrecognized config suffix {path.suffix!r}; expected '.toml' "
        "(the human format) or '.json' (for machine-generated configs)"
    )


def load(path: Path | str) -> Config:
    """Load, validate and return a configuration.

    **The only constructor a run uses.** A `Config` built inline has not been
    through `tomllib`, pydantic or the flattening, so a hash computed from it is
    evidence about the object and not about the file.

    Args:
        path: Path to a `.toml` or `.json` config.

    Returns:
        The validated configuration.

    Raises:
        FileNotFoundError: If `path` does not exist.
        ValueError: If the suffix is unrecognized, the file does not parse, or
            the config supplies a stamped key.
        pydantic.ValidationError: If the config does not satisfy the model,
            including an unrecognized key -- see `_STRICT`.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"{path}: no such config file")
    raw = _read(path)

    # Refused HERE as well as in `normalize`, and with a message naming the
    # file, because by the time `normalize` sees the payload there is nothing
    # left to point at. `normalize` stays the authority -- it is what every
    # caller goes through, including ones that never touch a file.
    supplied = sorted(set(_STAMPED_KEYS) & set(raw))
    if supplied:
        raise ValueError(
            f"{path}: {supplied} identifies the installed code and must not "
            "appear in a config. It is refused rather than overridden, so a "
            "config that tries to pin it fails loudly instead of being ignored"
        )
    return Config.model_validate(raw)


def normalize_candidates(candidates: Sequence[str | Sequence[str]]) -> tuple[str, ...]:
    """Return each candidate's `spec_hash`, for callers holding raw config data.

    Args:
        candidates: Candidate expressions or term lists.

    Returns:
        The per-candidate spec hashes, in the order given.
    """
    return tuple(parse_candidate(candidate).spec_hash() for candidate in candidates)
