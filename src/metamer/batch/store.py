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
SCHEMA_VERSION = 3

#: Target bytes for one inner chunk, per design doc 12.7's "a few MB".
CHUNK_TARGET_BYTES = 4_000_000

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
    }
)


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
    warm_start_used: bool = False,
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
            config field moves it by 3.3x in area and a sizing figure without its
            regime is not a figure.
        warm_start_used: **A fact about the RUN, not about the config.** Reading
            it off `config.warm_start.enabled` would write `true` for a 2a run
            that cannot warm-start at all.

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

    return {
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
        "geometry_components": json.loads(hashing.canonical_json(geometry_components)),
        "geometry_hash": rollup,
        "memory_budget_gb": config.memory_budget_gb,
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
        "tile_sides": {name: int(tile_sides[name]) for name in sorted(tile_sides)},
        "unique_dt_count": int(unique_dt_count),
        "warm_start_used": bool(warm_start_used),
    }


def _chunk_side(tile_side: int, other: int, itemsize: int) -> int:
    """Choose the inner-chunk row count: the largest divisor meeting the target.

    Zarr requires the shard shape to be a whole number of chunks, so the choice
    is over **divisors** of `tile_side` and not over any row count. **A prime
    tile side therefore has no useful subdivision** -- its only divisors are 1 and
    itself -- which is a reason for 2b's calibration to prefer a composite tile
    side, recorded here because nothing else will notice.

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
