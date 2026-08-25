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
from metamer.config.signal_terms import parse_signal_terms
from metamer.core import hashing
from metamer.core.signal import SignalSpec
from metamer.core.terms import ProcessSpec

_STAMPED_KEYS = tuple(sorted(hashing.STAMPED_IDENTITY_FIELDS))
"""The keys `load` refuses, READ FROM the classification rather than restated.

It was `(ALGORITHM_VERSION_KEY, REGISTRY_VERSION_KEY)` until 2026-08-24, which
is the same two names written twice. A third stamped identity would then have
had to be added in both places, and the failure of adding it in one is silent:
`normalize` would refuse it and `load` would not, so the refusal a user meets
would depend on whether they came through a file. Sorted for a deterministic
message order.
"""


class StampedKeyError(ValueError):
    """A config supplied a key that identifies the installed code.

    A `ValueError` subclass so nothing that already catches `ValueError` around
    `load` changes behaviour, and a distinct type so a caller can tell it apart
    from `_read`'s parse failures.

    **THE TWO WERE INDISTINGUISHABLE AND THE LAYER ATTRIBUTION NEEDS THEM
    APART.** `_read` raises a bare `ValueError` for an unrecognized suffix and
    for a parse failure, both of which are validation **layer 1** -- the file.
    This one is **layer 2** -- the schema -- because the fault it describes is a
    key that must not appear, which is what `extra="forbid"` would report as
    `extra_forbidden` if this pre-check were not here to give a better message.
    Both layers exit 3, so the exit code never depended on the distinction; the
    message did, and design doc section 13.2 requires each stage to name itself.
    """


PER_POINT_TERM_PREFIX = "regressor_field:"
"""Prefix marking a `signal_terms` entry as a PER-POINT regressor field.

`"regressor_field:gia"` declares a regressor supplied as a `(time, y, x)` field
rather than as one column shared by every series. The feature is refused at
validation layer 3 until the design builder supports it; the declaration exists
so that the refusal, the memory formula's branch and the calibration-cache key
all have the same single source of truth. See `Config.per_point_regressors`.
"""

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
        data_uri: Where the input lives. **Provenance only since Task 3**,
            which replaced it in fit identity with `geometry_hash`. It reaches
            `run_hash` and neither gate, because a URI is a location and the
            gate built on it was wrong in both directions at once -- moving a
            file invalidated a valid resume, editing one in place permitted an
            invalid one.
        variable: Name of the variable to fit.
        signal_terms: Deterministic design terms, in column order. **Order is
            data**: two orderings are two different design matrices, so
            `canonical_json` preserves list order rather than sorting it.
            **This is also where the per-point regressor REGIME is declared**,
            with `PER_POINT_TERM_PREFIX` -- see `per_point_regressors`.
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
        memory_budget_gb: Byte budget the tile size derives from, in **SI
            gigabytes -- 10**9 bytes, not 1024**3**. Run-relevant: §11.1.1
            requires peak RAM to be derivable from the budget alone.
            **IT BOUNDS PROCESS PEAK RSS, NOT THE TILE**: since Phase 2b Task 2
            the tile gets `(budget - measured floor) * (1 - headroom)`, so a
            budget at or below this release's process floor is refused naming
            the floor and a budget that would work. The unit was `1024**3`
            until 2026-08-15, i.e. 7.4% more bytes than every published tile
            side; the field is named `_gb`, and a `1024**3` field is named
            `_gib`.
            **`None` IS THE UNSET SENTINEL AND THE FIELD CANNOT DEFAULT TO A
            NUMBER.** `Field(default=1.0)` makes a config that omits the field
            byte-identical to one that specifies 1.0, so "accepted the default"
            and "chose 1 GB" are the same bytes and a defaulting rule has
            nothing to fire on. That is pre-flight (a0) at a config field, and
            it resolves the way every fill value in the store does: the
            sentinel is a value the writer cannot produce, which `gt=0.0`
            guarantees. **`run()` resolves it** to
            `memory.DEFAULT_BUDGET_FRACTION` of TOTAL RAM and hashes the
            RESOLVED value, so the same file yields different `run_hash`es on
            two machines -- correct, and stated here so it does not read as
            nondeterminism: the budget is a fact about the run, and the run
            used the number the machine gave it.
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

    # `objective` and `seed` are ALSO declared in `hashing.CONFIG_DEFAULTS`, and
    # the duplication is deliberate. `normalize` lets the config win, so once a
    # config has been through `load` these defaults are what reach the hash and
    # that mapping never applies -- which makes it look like dead code from this
    # side. It is not: it is the only thing that fills these in for a caller
    # holding a payload and no file. **The two must agree**, and
    # `test_the_hashing_defaults_agree_with_the_model_defaults` is what holds
    # them together. Change one, change the other.
    objective: Literal["ml", "reml"] = "ml"
    engine: str = "kalman"
    seed: int = 0

    warm_start: WarmStart = Field(default_factory=WarmStart)
    audit: Audit = Field(default_factory=Audit)
    detail: Detail = Field(default_factory=Detail)
    screening: Screening = Field(default_factory=Screening)

    memory_budget_gb: float | None = Field(default=None, gt=0.0)
    threads: int = Field(default=1, ge=1)
    output: str = "out.zarr"

    def per_point_regressors(self) -> tuple[str, ...]:
        """Return the per-point regressor fields declared in `signal_terms`.

        **THE REGIME LIVES INSIDE `signal_terms`, AND THAT IS THE WHOLE OF THE
        CALIBRATION-CACHE ANSWER.** `signal_terms` is already in
        `FIT_RELEVANT_FIELDS`, and a per-point regressor changes the design
        matrix and therefore `theta_hat` and `log_lik`, so a regime change moves
        `fit_hash` and invalidates a calibration cache keyed on it **by
        construction**. A sibling field -- `regressor_fields` -- would have left
        that key naming `fit_hash` while `fit_hash` said nothing about the
        regime, and a cached shared-X measurement reused for a per-point run
        understates peak bytes-per-series by ~3.3x against a hard RAM
        constraint. Design doc section 11.4.

        **THE FEATURE IS REFUSED AND THE REGIME IS DECLARED**, per pre-flight
        (a3). The memory formula's branch (`memory.per_point_design`) and the
        narrowing seam (`signal.DesignInfo.per_point`) already exist; this is
        the config half, without which the layer-3 refusal has nothing to fire
        on and its test asserts nothing.

        **The spelling is provisional; the location is not.** Which prefix names
        a per-point field is Task 6's business, when something first builds a
        design from these strings. That it must be expressed inside
        `signal_terms` rather than beside it is settled.

        Returns:
            The declared field names, without the prefix, in config order.
        """
        return tuple(
            term[len(PER_POINT_TERM_PREFIX) :]
            for term in self.signal_terms
            if term.startswith(PER_POINT_TERM_PREFIX)
        )

    def process_specs(self) -> tuple[ProcessSpec, ...]:
        """Return the candidate set as `ProcessSpec` objects, in config order.

        Returns:
            One `ProcessSpec` per candidate. Config order is preserved because
            the model axis is positional -- Task 11's resume gate compares
            candidate identity `stored[i] == requested[i]`, so reordering the
            candidate list is a different store, not the same one.
        """
        return tuple(parse_candidate(candidate) for candidate in self.candidates)

    def signal_spec(self) -> SignalSpec:
        """Return `signal_terms` as a `SignalSpec`, in config order.

        **ORDER IS PRESERVED HERE AND CANONICALIZED ON THE NOISE SIDE**, and the
        asymmetry is the point: a noise composition is a sum whose order carries
        no information, while a signal spec's order is the design's column order
        and therefore `beta`'s axis in the store.

        Returns:
            The signal specification.

        Raises:
            ValueError: If `signal_terms` is empty or any entry is malformed --
                including the per-point regressor declaration, which is refused
                at layer 3 with both tile sizes named.
        """
        return parse_signal_terms(
            [
                term
                for term in self.signal_terms
                if not term.startswith(PER_POINT_TERM_PREFIX)
            ]
        )

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

    def to_payload(self, geometry_hash: str | None = None) -> dict[str, Any]:
        """Return the flat mapping `hashing.normalize` consumes.

        Nested blocks flatten to `block_field`. The two stamped keys are absent:
        `normalize` supplies them from the installed code and refuses a payload
        that carries them.

        Args:
            geometry_hash: The input's geometry fingerprint, from stage 4a. It
                is **not** stamped by `normalize` and cannot be, because it is
                not a property of the installed code -- it is a property of an
                input that may not exist yet. Omit it and `fit_hash` and
                `compat_hash` return None.

        Returns:
            The payload. `data_uri` is present and is **provenance only** since
            2026-08-12: it reaches `run_hash` and neither gate.
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
            "threads": self.threads,
            "output": self.output,
            "metamer_version": metamer.__version__,
        }
        # **THE UNSET SENTINEL DOES NOT REACH THE PAYLOAD**, and omitting the
        # key is what makes that structural rather than a convention. A `None`
        # here hashes as JSON `null`, which is a perfectly good-looking hash of
        # a budget nobody chose -- the same shape as `geometry_hash({})` filing
        # a well-formed rollup of nothing. `run_hash` refuses the state
        # outright; the two guards are deliberate and each names the other.
        if self.memory_budget_gb is not None:
            payload["memory_budget_gb"] = self.memory_budget_gb
        for block in ("warm_start", "audit", "detail", "screening"):
            model: BaseModel = getattr(self, block)
            for name, value in model.model_dump().items():
                payload[f"{block}_{name}"] = value
        if geometry_hash is not None:
            payload[hashing.GEOMETRY_HASH_KEY] = geometry_hash
        return payload

    def fit_hash(self, geometry_hash: str | None = None) -> str | None:
        """Hash the fields determining `theta_hat` and `log_lik`.

        **NONE IS A REAL ANSWER, NOT AN ERROR, AND §13.4 DEPENDS ON IT.**
        `--explain`'s most valuable use is a config with no data staged yet --
        sizing a run before moving 25 GB -- so an unreachable input is a
        DEGRADED MODE rather than a failure. It prints compat- and run-relevant
        content and says `fit_hash: not computed (requires stage 4a)`.

        The optional return type was declared at Task 1, one task before it
        could happen, precisely so that callers were not written against `str`
        and then revisited at the moment the None case started occurring.

        Args:
            geometry_hash: From stage 4a. Omitted means no input was opened.

        Returns:
            The hash, or None if `geometry_hash` was not supplied.
        """
        if geometry_hash is None:
            return None
        return hashing.fit_hash(self.to_payload(geometry_hash))

    def compat_hash(self, geometry_hash: str | None = None) -> str | None:
        """Hash the fields determining the stored derived arrays.

        Args:
            geometry_hash: From stage 4a.

        Returns:
            The hash, or None if `geometry_hash` was not supplied -- the same
            degraded mode as `fit_hash`, since `COMPAT_RELEVANT_FIELDS` is a
            strict superset.
        """
        if geometry_hash is None:
            return None
        return hashing.compat_hash(self.to_payload(geometry_hash))

    def run_hash(
        self, machine: str | None = None, geometry_hash: str | None = None
    ) -> str:
        """Hash everything, plus runtime knobs and the machine fingerprint.

        **Computable with no input opened**, unlike the two gates. §13.4 makes an
        unreachable input a degraded mode rather than an error, because sizing a
        run before staging 25 GB is `--explain`'s most valuable use.

        **AN UNRESOLVED BUDGET IS REFUSED HERE AND NOWHERE ELSE, AND THE
        ASYMMETRY IS THE ALLOWLIST BOUNDARY MADE EXECUTABLE.**
        `memory_budget_gb` is run-relevant and in neither gate's allowlist, so
        `fit_hash` and `compat_hash` are computable without it and refusing them
        would assert a dependence the allowlists deny. This one reads it, so
        this one cannot proceed without it: a `None` would hash as JSON `null`
        and give a defaulted run a `run_hash` that the same run with the budget
        written out cannot reproduce. **Paired with `to_payload`'s omission**,
        which keeps the sentinel out of the mapping in the first place; neither
        guard is redundant, because a caller can build a payload without going
        through this method.

        Args:
            machine: Optional fingerprint from `hashing.machine_fingerprint`.
            geometry_hash: From stage 4a, when an input has been opened.

        Returns:
            The hash. **Provenance only, never a gate.**

        Raises:
            ValueError: If `memory_budget_gb` is None. The message names what
                resolves it, because the caller's fix is to resolve the budget
                rather than to remove the field.
        """
        if self.memory_budget_gb is None:
            raise ValueError(
                "memory_budget_gb is unset, so this config has no run identity: "
                "the budget is run-relevant and is resolved at run, from "
                "metamer.core.memory.default_budget_gb() when a config does not "
                "name one. Resolve it before hashing. fit_hash and compat_hash "
                "are computable in this state deliberately -- the budget is in "
                "neither allowlist"
            )
        return hashing.run_hash(self.to_payload(geometry_hash), machine)


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
        StampedKeyError: If the config supplies a stamped key. A `ValueError`
            subclass, and a distinct one so a caller can attribute it to the
            schema layer rather than to the file layer.
        ValueError: If the suffix is unrecognized or the file does not parse.
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
        raise StampedKeyError(
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
