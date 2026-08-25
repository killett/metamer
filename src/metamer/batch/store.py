"""Store creation: groups, dtypes, fill values, coordinates and provenance.

**EVERY CHOICE HERE IS UNCHANGEABLE ONCE DATA EXISTS**, which is why the fill
values, the dtypes and the stored code meanings are stated in one place with
their reasons attached rather than left to the call that happens to create the
array.

**EVERY FILL VALUE IS A VALUE THE WRITE PATH CANNOT PRODUCE.** Measured
2026-08-12: `outcomes._CODES` puts **`OK` at 0**, zarr's default `fill_value` for
an integer array is **0**, and **zarr does not write a chunk equal to the fill
value** -- so a store created with the default fill is byte-for-byte identical on
disk to a correct one (both are pure metadata, zero chunk files) and reads back
as a completed, wholly successful run over the entire grid. **The defect is
invisible in the bytes and inverts the store's meaning.**

    /status/outcome        NOT_ATTEMPTED (8)   nothing in 2a writes that code
    every float array      NaN                 a non-OK slot is NaN anyway
    /primitives/iterations 65535               the cap is 200
    /selection/n_valid     -1                  a count is never negative
    /selection/selected    -2                  -1 already means "no winner"
    /completion/tiles      0                   THE DELIBERATE EXCEPTION

**The exception is stated because otherwise it gets "fixed".** An unwritten tile
*is* incomplete, so for that one array the neutral value is the true one; every
other zero-looking fill in this store is a defect.

**`iterations` IS EXEMPT FROM THE STATUS/VALUE INVARIANT AND IT IS THE ONLY
MEMBER THAT CAN BE.** The invariant reads "a non-`OK` status has NaN in all
corresponding value slots" and is stated over `/primitives/` -- which holds
`iterations`, specified as uint16 in three documents. **A uint16 has no NaN.**
`k` and `n` are unaffected because `CandidateScores` already carries both as
float64. `iterations` is also the only member that feeds no arithmetic, so it
keeps its dtype and carries 65535 for "no fit ran". Task 9's invariant check
must name this exemption rather than rediscover it.

**`/primitives/` CARRIES `n`, WHICH DESIGN DOC 12.2 OMITTED.**
`criteria.rank_candidates` reads `loglik`, `k`, **`n`** and `n_eff`; without `n`
stored, Task 12's recompute path would have to re-open the input and recount the
mask, which is exactly the condition the handoff names as fatal to 12.8. It is
stored per model although v1 makes it constant along `m` -- the design is built
once, before the candidate loop -- for the reason 12.3 gives `/signal/` a model
axis: a shape change later is a format migration on a 10^7-point store.

**LABEL COORDINATES USE THE V3-SPECIFIED `string` DTYPE, NOT 12.4's `S32`.**
Measured 2026-08-12 with zarr 3.3.0: `S32` writes `null_terminated_bytes` and
raises `UnstableSpecificationWarning` -- "does not have a Zarr V3 specification
... may be unreadable by other Zarr libraries ... may change without warning" --
while `str` writes `string` with no warning. The dtype 12.4 chose is the unstable
one and the alternative it rejected is the specified one. 12.4's integer-code
legend stays in attrs as the redundancy; **only the dtype moved.**

**THE METADATA IS CONSOLIDATED AT CREATION, AND THAT IS A COPY.** Plain
`xr.open_zarr` warns on an unconsolidated store, and the acceptance criterion is
a round-trip through *plain* `xr.open_zarr` -- a reader who must first discover a
keyword is not the reader 12.4 has in mind. **Consolidated metadata duplicates
every array's metadata and every attr, so anything that later creates an array or
writes an attr must re-consolidate.** Nothing in 2a does: provenance is written
here and every later write is chunk data.

**SPATIAL COORDINATES ARE WRITTEN, WHICH 12.2's LAYOUT DOES NOT MENTION.** A
store of trends with no `y`/`x` values cannot be plotted, regridded or joined to
anything -- and 12.4's whole acceptance criterion is that a consumer without
metamer can open it. The values come from the geometry components already in
provenance, so there is one source and no second copy to drift. An input whose
grid carries no coordinate variables leaves them out, and says so in attrs.

**THE `b` AXIS HAS NO LABELS IN 2a, AND THAT IS THE SIGNAL-TERM BLOCKER.**
Nothing maps `signal_terms` to `core.signal` classes, so the design column names
are unobtainable; Task 9 owns the parser and the labels arrive with it. The axis
exists at full width regardless -- it is the scientific payload's axis, and its
width is a caller argument for the same reason `tile_side` is.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import zarr
from zarr.codecs import BloscCodec

import metamer
from metamer.batch.geometry import geometry_hash
from metamer.batch.ragged import (
    NoiseParamCoordinates,
    model_label,
    noise_param_coordinates,
)
from metamer.core import hashing
from metamer.core.outcomes import Outcome
from metamer.core.registry import REGISTRY_VERSION

if TYPE_CHECKING:  # pragma: no cover - typing only
    from metamer.config.model import Config
    from metamer.core.memory import FloorReport
    from metamer.core.terms import ProcessSpec

#: Keys `geometry.geometry_components` always produces. Their absence means the
#: caller never opened the input -- and an empty mapping hashes to a well-formed
#: rollup, so nothing downstream would notice.
_GEOMETRY_KEYS = frozenset(
    {"variable", "arrays", "calendar", "time_coordinate", "spatial_coordinates"}
)

#: On-disk schema identity, stamped from the installed code and never from a
#: config. **Bump it when the layout, a dtype, a fill value or a stored code
#: meaning changes** -- including when a member is added to `Outcome`, whose own
#: docstring carries that rule. **Task 9 adds `SCREENED_OUT` and
#: `NOT_APPLICABLE`, so Task 9 bumps this.**
#:
#: **v2 (2026-08-13, Task 9): `Outcome` gained `SCREENED_OUT` (12) and
#: `NOT_APPLICABLE` (13).** No 2a run can emit either, but the `flag_values` /
#: `flag_meanings` legend written into `/status/` at creation comes from the enum,
#: so a v1 store and a v2 store disagree about the vocabulary.
#:
#: **v3 (2026-08-13, Task 11): root attrs gained `detail`.** The `/detail/`
#: selection is **in no hash** -- it moves neither `theta_hat` nor the derived
#: arrays -- so the resume gate's refusal of a change to it can only be made by
#: comparing against a recorded value, and a v2 store carries none. **A bump for
#: an added attr rather than an added array**, because the test is what a reader
#: can be asked: a v2 store cannot answer the question the v3 gate asks, and
#: treating its silence as agreement would pass every `/detail/` change.
#:
#: **v4 (2026-08-15, Phase 2b Task 1): root attrs gained `tile_side_basis` and
#: `floor`.** The v3 test applied to a new question: a v3 store cannot answer
#: *"was your tile side analytic, measured this session, or read from a
#: calibration cache?"*, and Task 6's resume refusal needs the answer to name
#: calibration as the cause when a side moves. **The field lands before its only
#: reader** -- every store written in between would otherwise be unable to answer
#: and its silence would read as agreement -- and it lands beside Task 0's
#: corrected arithmetic, so no store is ever written under the new formula
#: without recording which basis produced its side.
#:
#: **v5 (2026-08-15, Phase 2b Task 3): root attrs gained
#: `memory_budget_requested_gb`.** `memory_budget_gb` became `float | None` with
#: `None` meaning *the config named no budget*, resolved at run to a fraction of
#: total RAM -- so the recorded budget is no longer evidence that anybody asked
#: for it, and `completion.resume_tile_side` quotes it back at a user whose
#: resume was refused.
#:
#: **v5 ALSO GAINED `calibration` (2026-08-15, Phase 2b Task 5) WITHOUT A BUMP,
#: AND THE REASON IS RECORDED BECAUSE THE GENERAL RULE SAYS OTHERWISE.** Two v5
#: stores from different eras are therefore distinguishable only by inspection --
#: one written before Task 5 cannot carry the key, one written after may -- which
#: is exactly the condition the entry below calls a defect. **It is safe here for
#: a specific reason and not a general one: nothing before Task 5 could consult a
#: calibration at all**, so an absent `calibration` means *"none was consulted"*
#: in both eras and reads correctly either way. A bump is owed when an older
#: store **cannot answer** a question a new gate asks; this one answers it.
#:
#: **AND THIS BUMP'S FIELD IS THE FIRST THAT IS NOT A REQUIRED ATTR, WHICH IS
#: WHY THE BUMP IS LOAD-BEARING RATHER THAN TIDY.** `create_store` refuses on
#: `attrs.get(key) is None`, so a key whose `None` **is its meaning** cannot be
#: required without refusing every defaulted run. The version is therefore the
#: only mechanism left that makes an older store's silence a refusal: a v4 store
#: is rejected by the gate rather than read through `attrs.get`, which would
#: answer `None` and be indistinguishable from "nobody asked for this budget".
SCHEMA_VERSION = 5

#: Target bytes for one inner chunk, per design doc 12.7's "a few MB".
CHUNK_TARGET_BYTES = 4_000_000

#: POLICY. Every derived tile side is rounded DOWN to a multiple of this.
#:
#: **THIS IS NOT A TUNING PARAMETER AND A READER PROPOSING TO DROP IT HAS TO
#: ANSWER 9.63x.** `_chunk_side` picks a **divisor** of the tile side, so the
#: achievable chunk sizes are set by the side's factorization -- and this
#: function's own docstring has warned since 2a that **a prime side has no useful
#: subdivision**, with no instance to point at. Phase 2b Task 0's formula
#: correction then moved the published side to ~~**347, which is prime**~~ --
#: superseded by Task 2, and the current value with its preconditions is
#: `tiling.PUBLISHED_TILE_SIDE`; the argument below is unchanged by that, because
#: what it rests on is the *reachability* of a prime side and not on which one
#: was published the day it was written. So are 349 and 353.
#: **Two independent lines meeting on the same pathological case is
#: evidence, not coincidence**, and the measurement at the meeting is that the
#: worst array's chunk goes from 18.3 MB at side 338 to **38.5 MB at 347 --
#: 9.63x the 4 MB target**. Without the base, the corrected arithmetic is not
#: usable.
#:
#: *"Prefer a composite side"* -- this project's own earlier phrasing -- is wrong
#: in both directions: 338 is composite and still gives 4.57x. The property
#: wanted is a divisor inside the admissible window, and that window differs per
#: array, so **the value was chosen by sweeping every derived side from 100 to
#: 600 rather than by elegance.** The sweep table lives in `PROGRESS.md`'s
#: *What Task 2 established* section, once.
#:
#: **THE ASYMMETRY, since this is policy rather than a derived value:** a base
#: too small leaves the prime and near-prime sides in, whose chunks are ten times
#: the target -- read amplification on every tile and a decompression buffer to
#: match. A base too large throws away tile area, which costs runtime linearly.
#: **Rounding DOWN is always budget-safe**, which is why the loss is the only
#: cost worth trading against.
TILE_SIDE_BASE = 16

#: "No fit ran" for `/primitives/iterations`, which cannot carry NaN. Above any
#: reachable iteration count: the cap is 200.
ITERATIONS_UNSET = 65535

#: "Nothing wrote here" for `/selection/n_valid`; a real count is never negative.
N_VALID_UNSET = -1

#: "Nothing wrote here" for `/selection/selected`, which uses -1 for "no winner"
#: -- so the unwritten value must differ from it or an interrupted write reads as
#: a point that was ranked and had no winner.
SELECTED_UNSET = -2

#: Provenance keys a store cannot be created without. Each is either a gate the
#: resume path reads or an identity of the code that produced the fits.
REQUIRED_ATTRS = frozenset(
    {
        "algorithm_version",
        "candidate_spec_hashes",
        "compat_hash",
        "criteria",
        "detail",
        "engine",
        "fit_hash",
        "geometry_components",
        "geometry_hash",
        "metamer_version",
        "objective",
        "registry_version",
        "run_hash",
        "schema_version",
        "tile_side_basis",
    }
)


class TileSideBasis(StrEnum):
    """How the tile side in a store's attrs was arrived at.

    **THE VOCABULARY IS DESIGN DOC 13.4's AND IT PREDATES THE NEED FOR IT.**
    13.4 requires every printed constant to be labelled *(a) measured on this
    machine from a cached calibration, (b) measured on this machine in this
    session, or (c) a default shipped with the package* -- written for
    `--explain`, and exactly the three states a stored tile side can be in.
    Reusing it rather than inventing a second vocabulary is what keeps the store
    and the eventual report saying the same thing about the same run.

    **In case (c), 13.4 also requires a RANGE rather than a point estimate**, and
    that requirement is now weaker than it was: since Phase 2b Task 2 the
    analytic path is conservative rather than optimistic, so `DEFAULT` is an
    honest estimate and not a guess dressed as one.

    **ALL THREE ARE REACHABLE SINCE PHASE 2b TASK 5**, through `--calibrate`
    and `--recalibrate`.

    Attributes:
        CACHED: Derived from a calibration read out of the cache.
        MEASURED: Derived from a calibration measured in this session.
        DEFAULT: Derived from the shipped analytic formula. **It is also what a
            run whose measurement was REFUSED records** -- see
            `batch.calibration.unusable_reason` -- which is why the store's
            `calibration` attr exists beside this field: without it, a run that
            spent hours measuring and a run that never measured would be one
            observation.
    """

    CACHED = "cached"
    MEASURED = "measured"
    DEFAULT = "default"


@dataclass(frozen=True)
class StoreShape:
    """The axis lengths a store is created with.

    `m`, `c` and `p` are deliberately absent: they come from the candidate list
    and the criterion list at creation, and a second statement of them here is a
    quantity that can disagree with the arrays it describes.

    Attributes:
        n_y: Grid rows.
        n_x: Grid columns.
        n_beta: Signal parameter count, the `b` axis. A caller argument because
            `k_beta` needs the signal-term parser Task 9 owns.
        tile_side: Shard side, in points. **Shard = one spatial tile**, so a
            region write is exactly one shard per array (12.7).
    """

    n_y: int
    n_x: int
    n_beta: int
    tile_side: int

    def __post_init__(self) -> None:
        """Refuse a degenerate axis.

        Raises:
            ValueError: If any length is below 1.

        Note:
            **A LENGTH-1 AXIS IS LEGAL AND A LENGTH-1 FIXTURE IS NOT.** Fitting
            one candidate under one criterion against a one-column design is a
            perfectly good thing to ask for, and `delta_ic = 0` with
            `weight = 1` is the correct answer there. What a length-1 axis
            cannot do is *test* anything defined across it, so the requirement
            is on the **suite's** fixtures (M=2 with unequal p, C=2) and not on
            the format. **It was a refusal here until 2026-08-13**, where it
            refused a legitimate single-candidate run: a fixture rule enforced
            against users, caught by the full sweep.
        """
        for name in ("n_y", "n_x", "tile_side"):
            if getattr(self, name) < 1:
                raise ValueError(
                    f"{name} must be at least 1, got {getattr(self, name)}"
                )
        if self.n_beta < 1:
            raise ValueError(f"n_beta must be at least 1, got {self.n_beta}")

    @property
    def n_tiles_y(self) -> int:
        """Number of tile rows, the completion bitmap's first axis."""
        return -(-self.n_y // self.tile_side)

    @property
    def n_tiles_x(self) -> int:
        """Number of tile columns, the completion bitmap's second axis."""
        return -(-self.n_x // self.tile_side)


def provenance_attrs(
    config: Config,
    *,
    geometry_components: Mapping[str, Any],
    thread_limits: Mapping[str, int],
    read_amplification: float,
    unique_dt_count: int,
    tile_sides: Mapping[str, int],
    tile_side_basis: TileSideBasis,
    memory_budget_requested_gb: float | None,
    max_iter: int,
    floor: FloorReport,
    warm_start_used: bool = False,
    source: Mapping[str, Any] | None = None,
    calibration: Mapping[str, Any] | None = None,
    decimation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the root attrs of a store.

    Args:
        config: The loaded configuration, past stage 4a.
        geometry_components: `geometry.geometry_components` output. The rollup is
            computed here from the same mapping, so the components and the hash
            in attrs cannot disagree -- 13.3 requires both, because a mismatch
            has to be diagnosable from the store alone.
        thread_limits: Observed per-library limits, never requested ones.
        read_amplification: Bytes read over bytes used for the tile geometry.
        unique_dt_count: Distinct timesteps on the realized axis.
        tile_sides: Tile side per regressor regime, both branches, because one
            config field moves it by 3.44x in area and a sizing figure without
            its regime is not a figure.
        decimation: For a PASS-1 store only: `parent_geometry_hash`, the
            fingerprint of the **undecimated** input; `parent_fit_hash`,
            `config.fit_hash(parent_geometry_hash)`; and `parent_fit_payload`,
            the allowlist subset that digest was taken over. **Omitted entirely
            for an ordinary store, and the absence is what says "not a pass-1
            store"** -- these are not in `REQUIRED_ATTRS` and no schema bump is
            owed, because nothing before Phase 2c Task 2 could produce a
            decimated store.

            **`parent_fit_hash` IS THE CROSS-STORE GATE, AND THE GEOMETRY
            DIFFERENCE CANCELS EXACTLY.** Comparing the two stores' own
            `fit_hash` always fails -- pass 1's is over the DECIMATED geometry
            and pass 2's over the parent's -- and that difference is the point
            of pass 1 rather than a mismatch. Substituting the parent rollup on
            both sides subtracts it, leaving **one equality that covers every
            field in `FIT_RELEVANT_FIELDS`**, including the ones an enumerated
            gate would not have listed.

            **The parent's HASH, not its components.** `geometry_components` is
            already a required attr holding full coordinate value arrays --
            10 800 numbers for a 3600 x 7200 grid -- and "record the parent's
            geometry so the derivation can be checked" reads as storing those
            twice. Reproducing the decimated fingerprint from the parent's is a
            test's job, and a test has the dataset.
        tile_side_basis: Which of 13.4's three states produced those sides.
            **Required, and required with no default**, because a default is a
            self-report: the one basis a caller would omit is the one it is least
            sure of, and a store that cannot answer Task 6's question would have
            its silence read as agreement.
        memory_budget_requested_gb: What the CONFIGURATION asked for, or None
            when it named no budget. **A different fact from `config`'s
            resolved budget**, which is always a number by the time a store is
            built: a defaulted run records the machine's answer beside a null
            request, and the pair is what lets a later reader tell "the user
            wanted 4.13 GB" from "this box had 16.5 GB". **No default here
            either**, and for the sharper version of the same reason: `None` is
            a legitimate value, so an omitted argument and a deliberate `None`
            would be one observation -- the caller has to say which it means.
            It is deliberately **not** in `REQUIRED_ATTRS`, which refuses on
            `None`; `SCHEMA_VERSION` 5 is what enforces its presence.
        max_iter: The iteration cap the run's fits used. **Recorded because it
            is in no hash**: a run capped for Phase 2b's calibration shares
            `fit_hash`, `compat_hash` and `run_hash` with an uncapped run over
            the same config, while its fits are all `ITER_CAP_*`. Not required
            and not a schema bump -- the outcome codes already answer the
            question, and this answers it without reading them.
        floor: The measured process floor. **Both the pre- and post-warm
            readings go in**, not just the one the budget uses, so the 30% gap
            between them is visible in a store rather than only in a docstring --
            and so a later reader can tell an import-time floor from a warm one
            without re-running anything.
        warm_start_used: **A fact about the RUN, not about the config.** Reading
            it off `config.warm_start.enabled` would write `true` for a 2a run
            that cannot warm-start at all.
        source: A `--reuse-fits-from` source's root attrs, or None for an
            ordinary run. **Recorded, never resolved**: 12.4 requires every
            store to be self-contained, so the path and the three hashes go in
            as provenance a reader can *verify* -- the new store's `fit_hash`
            equals the recorded `source_fit_hash` -- and never as a pointer a
            reader must follow. The keys are absent for a run that fitted its
            own primitives, and that absence is itself the fact.
        calibration: `batch.calibration.provenance`'s mapping, or None for a
            run that consulted no calibration. **Written whenever one was
            CONSULTED, used or not**: a measurement the band refused leaves
            `tile_side_basis` at `default`, which is also what a run that never
            calibrated writes, so without this key a store that spent 26.5 h
            measuring is indistinguishable from one that measured nothing --
            the fill-value shape at a provenance key. **The absence of the key
            is what means "no calibration was consulted"**, on `source`'s
            precedent, and the `rejected` field inside it says why a consulted
            measurement did not produce the side.

            **No `SCHEMA_VERSION` bump, and the ledger's own test is why.** A
            bump is owed when an older store cannot answer a question a new gate
            asks; Task 6's refusal reads `tile_side_basis`, which every v4+
            store carries, and a v5 store's silence here is unambiguous because
            nothing before Phase 2b Task 5 could consult a calibration at all.

    Returns:
        The attrs mapping, JSON-safe and with sorted keys throughout.

    Raises:
        ValueError: If `geometry_components` is not a real fingerprint of an
            opened input. **`geometry_hash({})` returns a perfectly good-looking
            hash of nothing**, so a caller that has not opened the input gets a
            store whose `fit_hash` is well-formed and matches every other store
            made the same way -- a gate that reads as present and is not. The
            entry contract's ordering (open, contract, fingerprint, hashes,
            resume, tiling) is what this enforces at the one place a store is
            born.
    """
    missing = sorted(_GEOMETRY_KEYS - set(geometry_components))
    if missing or not geometry_components["arrays"]:
        raise ValueError(
            f"geometry_components is not a fingerprint of an opened input "
            f"(missing {missing or ['arrays']}); an empty mapping still hashes to "
            "a well-formed rollup, so the store's fit_hash would match every "
            "other store built without opening the data. Run stage 4a first -- "
            "see design doc section 13.7"
        )

    rollup = geometry_hash(geometry_components)
    fit = config.fit_hash(rollup)
    compat = config.compat_hash(rollup)
    if fit is None or compat is None:  # pragma: no cover - unreachable narrowing
        raise ValueError("fit_hash and compat_hash require a geometry hash")

    attrs: dict[str, Any] = {
        "algorithm_version": hashing.ALGORITHM_VERSION,
        "candidate_spec_hashes": list(config.candidate_spec_hashes()),
        "compat_hash": compat,
        "criteria": list(config.criteria),
        # THE `/detail/` SELECTION IS IN NO HASH, so the resume gate's refusal of
        # a change to it has nothing to compare against unless it is recorded
        # here. It moves neither `theta_hat` (not fit-relevant) nor the derived
        # arrays (not compat-relevant), and it is not recomputable either -- a
        # covariance derives from the Hessian at the optimum and the Hessian is
        # not stored -- so the store's own copy of the request is the only
        # available evidence of what it was built to answer.
        "detail": json.loads(config.detail.model_dump_json()),
        "engine": config.engine,
        "fit_hash": fit,
        # THE LADDER, NOT JUST THE FIGURE THE BUDGET USED. `peak` is what Task 2
        # subtracts; the other three are what make it checkable from the store.
        "floor": {
            "pre_warm_bytes": int(floor.pre_warm_bytes),
            "post_warm_bytes": int(floor.post_warm_bytes),
            "with_input_bytes": int(floor.with_input_bytes),
            "peak_bytes": int(floor.peak_bytes),
            "components": {
                name: int(floor.components[name]) for name in sorted(floor.components)
            },
        },
        "geometry_components": json.loads(hashing.canonical_json(geometry_components)),
        "geometry_hash": rollup,
        # THE BUDGET THE RUN USED, AND -- SEPARATELY -- WHAT WAS ASKED FOR.
        # `config` is the EFFECTIVE configuration, so the first is a number
        # whenever a store is built at all: `run_hash` below refuses an
        # unresolved budget, which is the guard that keeps a null out of this
        # mapping without a second check here.
        "memory_budget_gb": config.memory_budget_gb,
        "memory_budget_requested_gb": memory_budget_requested_gb,
        # **THE CAP IS IN NO HASH, SO THIS IS THE ONLY DIRECT RECORD OF IT.**
        # A capped run and an uncapped one over one config share all three
        # hashes and produce entirely different fits, and the cap is a `run()`
        # argument rather than a config field deliberately -- see `run`. **No
        # schema bump**: a v5 store can already answer "were these fits capped?"
        # from `/primitives/iterations` and `/status/outcome`, so its silence is
        # not a defect and this key makes the answer direct rather than
        # inferential.
        "max_iter": int(max_iter),
        "metamer_version": metamer.__version__,
        "objective": config.objective,
        "read_amplification": float(read_amplification),
        "registry_version": REGISTRY_VERSION,
        "run_hash": config.run_hash(geometry_hash=rollup),
        "schema_version": SCHEMA_VERSION,
        "seed": config.seed,
        "thread_limits": {
            name: int(thread_limits[name]) for name in sorted(thread_limits)
        },
        "tile_side_basis": str(TileSideBasis(tile_side_basis)),
        "tile_sides": {name: int(tile_sides[name]) for name in sorted(tile_sides)},
        "unique_dt_count": int(unique_dt_count),
        "warm_start_used": bool(warm_start_used),
    }
    if calibration is not None:
        attrs["calibration"] = json.loads(hashing.canonical_json(calibration))
    if decimation is not None:
        # **PRESENT ONLY ON A PASS-1 STORE, AND ITS ABSENCE IS THE ANSWER.**
        # A store without these keys is not a decimated one, on the `source_*`
        # and `calibration` precedent -- so they are NOT in `REQUIRED_ATTRS`,
        # which would refuse every store written before this task.
        #
        # **AND NO SCHEMA BUMP IS OWED**, which is the reflex worth resisting.
        # A bump is for a question an older store CANNOT answer, and every
        # earlier store's silence here is unambiguous: nothing before Phase 2c
        # Task 2 could produce a decimated store at all. Same reasoning as the
        # `calibration` block, and the opposite of `memory_budget_requested_gb`,
        # whose `None` is meaningful and therefore needed v5.
        #
        # **THE PAYLOAD AND ITS DIGEST BOTH GO IN, WHICH IS A DELIBERATE
        # DUPLICATION WITH A PRECEDENT DIRECTLY ABOVE**: `geometry_components`
        # sits beside `geometry_hash` because 13.3 requires a mismatch to be
        # diagnosable from the store alone. The digest is the complete gate --
        # it covers every allowlisted field, including ones added later -- and
        # the payload is what lets the refusal NAME the field that differs. A
        # digest mismatch on its own is a wall.
        #
        # **THE STRIDE IS NOT ALSO A TOP-LEVEL ATTR.** It was, until this task;
        # it is in `parent_fit_payload` under `warm_start_coarse_stride`, and
        # two copies of one value drift the moment either is written from a
        # different place.
        parent_payload = dict(decimation["parent_fit_payload"])
        attrs.update(
            {
                "parent_geometry_hash": str(decimation["parent_geometry_hash"]),
                "parent_fit_hash": str(decimation["parent_fit_hash"]),
                "parent_fit_payload": json.loads(
                    hashing.canonical_json(parent_payload)
                ),
            }
        )
    if source is not None:
        attrs.update(
            {
                "source_store": str(source["path"]),
                "source_fit_hash": str(source["fit_hash"]),
                "source_compat_hash": str(source["compat_hash"]),
                "source_run_hash": str(source["run_hash"]),
            }
        )
    return attrs


def _chunk_side(tile_side: int, other: int, itemsize: int) -> int:
    """Choose the inner-chunk row count: the largest divisor meeting the target.

    Zarr requires the shard shape to be a whole number of chunks, so the choice
    is over **divisors** of `tile_side` and not over any row count. **A prime
    tile side therefore has no useful subdivision** -- its only divisors are 1 and
    itself.

    **AND "PREFER A COMPOSITE SIDE" -- WHAT THIS DOCSTRING SAID UNTIL
    2026-08-15 -- IS WRONG IN BOTH DIRECTIONS**, which `TILE_SIDE_BASE` above
    records with the measurement: 338 is composite and still gives 4.57x the
    target. The property wanted is a **divisor inside the admissible window**,
    and that window differs per array, which is why the base is chosen by a
    sweep rather than by elegance. It also named an agent that does not exist:
    a calibration does not choose a side, it asks `tiling.budget_bytes_for_side`
    for the budget that lands on one, and every derived side is a multiple of
    the base by construction.

    Args:
        tile_side: Shard side in points.
        other: Product of every non-`y` axis length in the array.
        itemsize: Bytes per element.

    Returns:
        Rows per inner chunk.
    """
    for rows in range(1, tile_side + 1):
        if tile_side % rows == 0 and rows * other * itemsize >= CHUNK_TARGET_BYTES:
            return rows
    return tile_side


@dataclass(frozen=True)
class _ArraySpec:
    """One array's shape, dtype and fill value, before it is created."""

    name: str
    dims: tuple[str, ...]
    shape: tuple[int, ...]
    dtype: str
    fill_value: Any


def _spatial_shard(spec: _ArraySpec, tile_side: int) -> tuple[tuple[int, ...], ...]:
    """Return `(chunks, shards)` for an array whose first two dims are `y`, `x`.

    Args:
        spec: The array being created.
        tile_side: Shard side in points.

    Returns:
        The chunk shape and the shard shape.
    """
    trailing = spec.shape[2:]
    shard = (
        min(tile_side, spec.shape[0]),
        min(tile_side, spec.shape[1]),
        *trailing,
    )
    other = int(np.prod((shard[1], *trailing))) if trailing else shard[1]
    rows = _chunk_side(shard[0], other, np.dtype(spec.dtype).itemsize)
    return (rows, shard[1], *trailing), shard


def _array_specs(
    shape: StoreShape, n_models: int, n_criteria: int, p_total: int
) -> dict[str, tuple[_ArraySpec, ...]]:
    """Return every group's arrays, with the dtype and fill each is created with.

    Args:
        shape: Grid and tile geometry.
        n_models: Length of the model axis.
        n_criteria: Length of the criterion axis.
        p_total: Length of the ragged noise axis.

    Returns:
        Group name to its array specifications.
    """
    y, x, b = shape.n_y, shape.n_x, shape.n_beta
    nan = float("nan")
    ym = ("y", "x", "m")
    return {
        "signal": (
            _ArraySpec(
                "beta", ("y", "x", "m", "b"), (y, x, n_models, b), "float32", nan
            ),
            _ArraySpec(
                "beta_err", ("y", "x", "m", "b"), (y, x, n_models, b), "float32", nan
            ),
        ),
        "selection": (
            _ArraySpec(
                "delta_ic",
                ("y", "x", "m", "c"),
                (y, x, n_models, n_criteria),
                "float32",
                nan,
            ),
            _ArraySpec(
                "weight",
                ("y", "x", "m", "c"),
                (y, x, n_models, n_criteria),
                "float32",
                nan,
            ),
            _ArraySpec("ic_best", ("y", "x", "c"), (y, x, n_criteria), "float64", nan),
            _ArraySpec(
                "selected", ("y", "x", "c"), (y, x, n_criteria), "int16", SELECTED_UNSET
            ),
            _ArraySpec("n_valid", ("y", "x"), (y, x), "int16", N_VALID_UNSET),
        ),
        "primitives": (
            _ArraySpec("log_lik", ym, (y, x, n_models), "float64", nan),
            _ArraySpec("k", ym, (y, x, n_models), "float64", nan),
            _ArraySpec("n", ym, (y, x, n_models), "float64", nan),
            _ArraySpec("n_eff_trend", ym, (y, x, n_models), "float64", nan),
            _ArraySpec("n_eff_bic", ym, (y, x, n_models), "float64", nan),
            _ArraySpec("iterations", ym, (y, x, n_models), "uint16", ITERATIONS_UNSET),
        ),
        "noise": (
            _ArraySpec("theta", ("y", "x", "p"), (y, x, p_total), "float32", nan),
            _ArraySpec("theta_err", ("y", "x", "p"), (y, x, p_total), "float32", nan),
        ),
        "status": (
            _ArraySpec(
                "outcome", ym, (y, x, n_models), "uint8", Outcome.NOT_ATTEMPTED.code
            ),
            _ArraySpec(
                "point_outcome",
                ("y", "x"),
                (y, x),
                "uint8",
                Outcome.NOT_ATTEMPTED.code,
            ),
        ),
        "warmstart": (
            _ArraySpec(
                "theta_unconstrained", ("y", "x", "p"), (y, x, p_total), "float64", nan
            ),
        ),
    }


def _write_labels(
    group: zarr.Group, name: str, dim: str, values: Sequence[str]
) -> None:
    """Create one string label array.

    Args:
        group: Destination group.
        name: Array name.
        dim: Its single dimension.
        values: The labels.
    """
    array = group.create_array(
        name, shape=(len(values),), dtype=str, dimension_names=(dim,)
    )
    array[:] = list(values)


def create_store(
    path: str | Path,
    *,
    specs: Sequence[ProcessSpec],
    criteria: Sequence[str],
    shape: StoreShape,
    attrs: Mapping[str, Any],
) -> None:
    """Create an empty store: every group except `/detail/`, and provenance.

    The store is pure metadata when this returns -- every array is entirely fill
    value, and zarr writes no chunk equal to the fill value -- so **nothing about
    a correct store is observable in its bytes.** What is observable is what
    reads back.

    Args:
        path: Destination. Must not exist.
        specs: Candidates in config order, as `Config.process_specs()` returns.
            The ragged index and the `/noise/` columns are built from these here,
            so no caller can pair a store with a different index.
        criteria: Criterion names, in config order.
        shape: Grid and tile geometry.
        attrs: Root provenance, from `provenance_attrs`.

    Raises:
        FileExistsError: If `path` exists. A store is created once; silently
            overwriting a finished 10^7-point run is unrecoverable, and the
            resume path -- not this function -- is what reopens one.
        ValueError: If `specs` or `criteria` is empty, or if a required
            provenance key is missing or None. **A length-1 axis is legal**: see
            `StoreShape.__post_init__`'s note -- fitting one candidate under one
            criterion is coherent, and the vacuity argument is about the suite's
            fixtures rather than about the format.
        NotImplementedError: Propagated from a spec declaring shared parameters.
    """
    destination = Path(path)
    if destination.exists():
        raise FileExistsError(
            f"{destination} exists; a store is created once and reopened by the "
            "resume path, never recreated over"
        )
    if not specs or not criteria:
        raise ValueError(
            "a store needs at least one candidate and one criterion, got "
            f"{len(specs)} and {len(criteria)}"
        )
    missing = sorted(key for key in REQUIRED_ATTRS if attrs.get(key) is None)
    if missing:
        raise ValueError(
            f"provenance is missing required key(s) {missing}; build attrs with "
            "provenance_attrs rather than by hand"
        )

    coordinates = noise_param_coordinates(specs)
    labels = tuple(model_label(spec) for spec in specs)
    spatial = {
        axis: values
        for axis, values in _spatial_values(attrs).items()
        if len(values) in {shape.n_y, shape.n_x}
    }

    root = zarr.create_group(store=str(destination))
    root.attrs.update({key: attrs[key] for key in sorted(attrs)})
    root.attrs["spatial_coordinates_written"] = sorted(spatial)

    specs_by_group = _array_specs(
        shape, len(specs), len(criteria), coordinates.index.total
    )
    recorded: dict[str, dict[str, list[int]]] = {}
    for group_name, array_specs in specs_by_group.items():
        group = root.create_group(group_name)
        for spec in array_specs:
            chunks, shards = _spatial_shard(spec, shape.tile_side)
            array = group.create_array(
                spec.name,
                shape=spec.shape,
                chunks=chunks,
                shards=shards,
                dtype=spec.dtype,
                fill_value=spec.fill_value,
                dimension_names=spec.dims,
                compressors=[BloscCodec(cname="zstd", shuffle="shuffle")],
            )
            itemsize = np.dtype(spec.dtype).itemsize
            recorded[f"{group_name}/{spec.name}"] = {
                "chunk_bytes": [int(np.prod(chunks)) * itemsize],
                "shard_bytes": [int(np.prod(shards)) * itemsize],
            }
            if "m" in spec.dims:
                _attach(array, ("m",))
            if "p" in spec.dims:
                _attach(
                    array,
                    tuple(
                        f"noise_param_{c}"
                        for c in ("model", "term", "name", "unit", "transform")
                    ),
                )
        _write_axis_labels(group, array_specs, labels, criteria, coordinates, spatial)

    _create_completion(root, shape)
    root.attrs["array_bytes"] = {
        name: {key: value[0] for key, value in entry.items()}
        for name, entry in sorted(recorded.items())
    }
    zarr.consolidate_metadata(str(destination))


def _attach(array: zarr.Array[Any], names: tuple[str, ...]) -> None:
    """Advertise non-dimension coordinates through the CF `coordinates` attr.

    Args:
        array: The data array.
        names: Coordinate variable names in the same group.
    """
    existing = str(array.attrs.get("coordinates", "")).split()
    array.attrs["coordinates"] = " ".join(sorted({*existing, *names}))


def _write_axis_labels(
    group: zarr.Group,
    array_specs: tuple[_ArraySpec, ...],
    labels: tuple[str, ...],
    criteria: Sequence[str],
    coordinates: NoiseParamCoordinates,
    spatial: Mapping[str, Sequence[float]],
) -> None:
    """Write the label coordinates every group needs to stand on its own.

    **Each group is opened separately by `xr.open_zarr(group=...)`, so a group
    without its own labels is not self-describing.** The arrays are tiny and are
    all built from one call here, so there is no second source to drift.

    Args:
        group: Destination group.
        array_specs: What that group holds, so only the needed axes are written.
        labels: Model labels, in config order.
        criteria: Criterion names, in config order.
        coordinates: Task 7's ragged index and `/noise/` columns.
        spatial: Grid coordinate values by axis name, possibly empty.
    """
    dims = {dim for spec in array_specs for dim in spec.dims}
    if "m" in dims:
        _write_labels(group, "m", "m", labels)
    if "c" in dims:
        _write_labels(group, "c", "c", list(criteria))
    if "p" in dims:
        for column in ("model", "term", "name", "unit", "transform"):
            _write_labels(
                group, f"noise_param_{column}", "p", getattr(coordinates, column)
            )
        index_array = group.create_array(
            "noise_param_model_index",
            shape=(coordinates.index.total,),
            dtype="int16",
            dimension_names=("p",),
        )
        index_array[:] = coordinates.model_index
        offsets = group.create_array(
            "noise_offset", shape=(len(labels),), dtype="int32", dimension_names=("m",)
        )
        offsets[:] = coordinates.index.offsets_array()
        extents = group.create_array(
            "noise_extent", shape=(len(labels),), dtype="int32", dimension_names=("m",)
        )
        extents[:] = coordinates.index.extents_array()
        if "m" not in dims:
            _write_labels(group, "m", "m", labels)
        group.attrs["legend"] = {
            column: list(values) for column, values in coordinates.legend().items()
        }
    for axis, values in spatial.items():
        array = group.create_array(
            axis, shape=(len(values),), dtype="float64", dimension_names=(axis,)
        )
        array[:] = np.asarray(values, dtype=np.float64)
    if "outcome" in {spec.name for spec in array_specs}:
        members = sorted(Outcome, key=lambda member: member.code)
        for name in ("outcome", "point_outcome"):
            group[name].attrs["flag_values"] = [member.code for member in members]
            group[name].attrs["flag_meanings"] = " ".join(
                str(member.value) for member in members
            )


def _spatial_values(attrs: Mapping[str, Any]) -> dict[str, list[float]]:
    """Read the grid coordinate values out of the provenance components.

    **One source, not two.** The values are already in `geometry_components`,
    which the fingerprint is computed from, so taking them from anywhere else
    would let the store's coordinates disagree with the geometry its `fit_hash`
    rests on.

    Args:
        attrs: Root provenance.

    Returns:
        Axis name to its values; empty when the input declares no grid
        coordinates, which is legal and is recorded in attrs.
    """
    components = attrs.get("geometry_components", {})
    spatial = components.get("spatial_coordinates", {}) if components else {}
    return {str(axis): list(values) for axis, values in spatial.items()}


def _create_completion(root: zarr.Group, shape: StoreShape) -> None:
    """Create the completion bitmap, one chunk per tile.

    **One chunk per tile deliberately, and not one shard for the array.** The bit
    for a tile is written after that tile's data has flushed, so grouping the bits
    into one object would make every tile's write a read-modify-write of every
    other tile's bit -- and an interruption mid-write would then be able to lose a
    bit that was already set. At 10^7 points the bitmap is of order 100 elements,
    so the object count is not a concern here.

    Args:
        root: The store root.
        shape: Grid and tile geometry.
    """
    group = root.create_group("completion")
    tiles = group.create_array(
        "tiles",
        shape=(shape.n_tiles_y, shape.n_tiles_x),
        chunks=(1, 1),
        dtype="uint8",
        fill_value=0,
        dimension_names=("tile_y", "tile_x"),
    )
    tiles.attrs["flag_values"] = [0, 1]
    tiles.attrs["flag_meanings"] = "incomplete complete"
