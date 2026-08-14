"""The recompute path: derived arrays from a finished store's primitives.

**THIS IS THE ONLY CONSUMER OF THE THREE-HASH SPLIT.** Task 11 established that
the in-place recompute arm of design doc 12.8 has no reachable input -- the two
allowlists differ by `criteria` alone, so a compat-only mismatch *is* a
criterion-set change, which refuses. So `--reuse-fits-from` is the single place
`fit_hash` is used to reuse work, and therefore the single demonstration that it
identifies anything.

**THE OPERATION: copy everything the fits produced, rank the primitives again,
write a NEW store.** The fit step of the tiling loop is replaced by a read; the
write path, the completion bitmap and the resume semantics are the same ones.

**THE NEW STORE'S GEOMETRY IS READ BACK FROM THE SOURCE, NOT RE-DERIVED FROM
THE BUDGET**, which is pre-flight (a1) in its sharpened form -- a stored
geometry that can be read back is not a gate, and re-deriving it is what makes
one. Two reasons agree:

- **Exit criterion 5a wants the copied groups byte-identical to the source**,
  and identical bytes need identical chunk and shard geometry, which is
  `tile_side`.
- **The memory budget's rule does not apply here, because no fit runs.** A tile
  of primitives is a few `(B, M)` float64 arrays, not a tile of filter state, so
  refusing a source whose tile side exceeds what the budget would hold for a
  *fit* would block the cheap operation on precisely the small machine that
  most wants to run it.

**Stated so it is not discovered: the new store carries the source's tile
side**, so a later *fitting* run against it under a smaller budget refuses --
correctly, because that run would fit.

**THE COPY IS DERIVED FROM THE SOURCE'S OWN LISTING.** A hand-written list of
arrays goes stale the moment the schema grows, and the failure is silent: the
new array keeps its fill value, which for every float array is NaN and reads as
"this point failed" rather than as "nobody copied this".
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import zarr

from metamer.core.capability import EngineId, Objective
from metamer.core.criteria import CandidateScores

if TYPE_CHECKING:  # pragma: no cover - typing only
    from metamer.batch.tiling import Tile

#: Groups the recompute copies verbatim. `/selection/` is recomputed and
#: `/completion/` belongs to the new run; every other group is what the fits
#: produced and is transferred unchanged -- including `/status/`, because a
#: recompute-stage failure is criterion-specific and `outcome` has no `c` axis.
COPIED_GROUPS = ("signal", "primitives", "noise", "status", "warmstart")


def _group(root: zarr.Group, name: str) -> zarr.Group:
    """Return one group, narrowed for the type checker.

    Args:
        root: The store root.
        name: Group name.

    Returns:
        The group.
    """
    group = root[name]
    if not isinstance(group, zarr.Group):  # pragma: no cover - store invariant
        raise TypeError(f"{name} is not a group")
    return group


def _array(root: zarr.Group, group: str, name: str) -> zarr.Array[Any]:
    """Return one array, narrowed for the type checker.

    Args:
        root: The store root.
        group: Group name.
        name: Array name.

    Returns:
        The array.
    """
    array = _group(root, group)[name]
    if not isinstance(array, zarr.Array):  # pragma: no cover - store invariant
        raise TypeError(f"{group}/{name} is not an array")
    return array


def gridded_arrays(root: zarr.Group) -> Iterator[tuple[str, str]]:
    """Yield `(group, name)` for every array the recompute must copy.

    **Selected by DIMENSIONS rather than by name**, so a coordinate is excluded
    because it is not gridded and a data array added to the schema later is
    included without anyone remembering to add it.

    Args:
        root: An opened store.

    Yields:
        Group and array name, in listing order.
    """
    for group_name in COPIED_GROUPS:
        for name, array in _group(root, group_name).arrays():
            dims = tuple(getattr(array.metadata, "dimension_names", None) or ())
            if dims[:2] == ("y", "x"):
                yield group_name, name


def copy_tile(source: zarr.Group, destination: zarr.Group, tile: Tile) -> None:
    """Copy one tile of every gridded array outside `/selection/`.

    Args:
        source: The store being reused.
        destination: The store being written.
        tile: The spatial block to transfer.
    """
    region = (slice(tile.y_start, tile.y_stop), slice(tile.x_start, tile.x_stop))
    for group_name, name in gridded_arrays(source):
        _array(destination, group_name, name)[region] = _array(
            source, group_name, name
        )[region]


def read_scores(
    source: zarr.Group, tile: Tile, *, engine: str, objective: str
) -> CandidateScores:
    """Rebuild one tile's `CandidateScores` from a store.

    **Five fields come from arrays, one from a coordinate, and two from root
    attrs.** The last two are sound because `engine` and `objective` are both
    fit-relevant: `fit_hash` equality, checked before anything is read, is what
    makes this run's values equal the ones the stored fits were produced under.
    Taking them from the caller is the same values by a checked identity, not a
    shortcut.

    Args:
        source: The store being reused.
        tile: The spatial block to read.
        engine: The engine key, from this run's configuration.
        objective: The objective, from this run's configuration.

    Returns:
        The block, flattened to `(B, M)` in row-major order -- the order
        `tiling.assemble_tile` produces and the write path pairs positionally.
    """
    region = (slice(tile.y_start, tile.y_stop), slice(tile.x_start, tile.x_stop))

    def block(group: str, name: str) -> np.ndarray:
        """Read one array's tile and flatten its spatial axes.

        Args:
            group: Group name.
            name: Array name.

        Returns:
            Shape `(B, M)`.
        """
        values = np.asarray(_array(source, group, name)[region])
        return values.reshape(tile.n_series, -1)

    labels = [
        str(name) for name in np.asarray(_array(source, "status", "m")[:]).tolist()
    ]
    models = len(labels)
    return CandidateScores(
        labels=tuple(labels),
        engines=(EngineId(engine),) * models,
        objectives=(Objective(objective),) * models,
        loglik=block("primitives", "log_lik").astype(np.float64),
        k=block("primitives", "k").astype(np.float64),
        n=block("primitives", "n").astype(np.float64),
        n_eff=block("primitives", "n_eff_bic").astype(np.float64),
        outcome=block("status", "outcome").astype(np.uint8),
    )


def source_tile_side(source_path: Path | str) -> int:
    """Return the tile side the new store must be created with.

    Args:
        source_path: The store being reused.

    Returns:
        The source's tile side, read from its provenance.
    """
    attrs = dict(zarr.open_group(str(source_path), mode="r").attrs)
    sides = attrs.get("tile_sides")
    side = sides.get("shared") if isinstance(sides, Mapping) else None
    if not isinstance(side, int):  # pragma: no cover - provenance invariant
        raise ValueError(
            f"{source_path} records no tile side, so the new store cannot be "
            "created with the geometry its copied arrays require"
        )
    return side
