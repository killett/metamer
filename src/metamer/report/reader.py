"""Open a store for reading, and say what it is.

**THIS MODULE IS THE ONLY PLACE IN `metamer.report` THAT KNOWS THE ON-DISK
LAYOUT.** Every other module takes a `StoreView`. That is not layering for its
own sake: the store schema is versioned and a foreign store may be written by a
different release, so the version check and the group names belong together at
one boundary rather than spread across five consumers.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import zarr
from numpy.typing import NDArray

from metamer.batch.input import InputContractError
from metamer.batch.store import SCHEMA_VERSION
from metamer.core.outcomes import Outcome

__all__ = ["Completion", "StoreView", "read_store"]


@dataclass(frozen=True)
class Completion:
    """How much of the grid was written, from `/completion/tiles`.

    **COUNTED TILES, NOT A BOOLEAN, BECAUSE SECTION 14.2 MUST PRINT `N of M`
    BESIDE EVERY DENOMINATOR.** A rate quoted without its population is what a
    reader carries away, and two reports over different populations are not
    comparable unless each says which population it had.

    Attributes:
        complete: Tiles whose completion bit is set.
        total: Tiles in the bitmap.
    """

    complete: int
    total: int

    @property
    def is_finished(self) -> bool:
        """Whether every tile was written."""
        return self.complete == self.total


@dataclass(frozen=True)
class StoreView:
    """A finished store's arrays, labels and provenance, read-only.

    Attributes:
        path: The store this was read from.
        outcome: `/status/outcome`, `(y, x, m)` uint8.
        delta_ic: `/selection/delta_ic`, `(y, x, m, c)` float32.
        selected: `/selection/selected`, `(y, x, c)` int16, `-1` no winner and
            `-2` nothing wrote here.
        n_valid: `/selection/n_valid`, `(y, x)` int16, `-1` unset.
        iterations: `/primitives/iterations`, `(y, x, m)` uint16, `65535` no
            fit ran.
        model_labels: The `m` axis's labels, as the store carries them.
        criterion_labels: The `c` axis's labels.
        attrs: The root attributes.
        completion: The bitmap's counts.
        disagreements: Contradictions between two records in this store,
            **reported and never resolved** -- see `_disagreements`.
    """

    path: Path
    outcome: NDArray[np.uint8]
    delta_ic: NDArray[np.float32]
    selected: NDArray[np.int16]
    n_valid: NDArray[np.int16]
    iterations: NDArray[np.uint16]
    model_labels: tuple[str, ...]
    criterion_labels: tuple[str, ...]
    attrs: dict[str, Any]
    completion: Completion
    disagreements: tuple[str, ...]


def _array(root: zarr.Group, path: str) -> zarr.Array[Any]:
    """One array, by its path, refusing a store that does not carry it.

    Args:
        root: The opened root group.
        path: A `group/name` path.

    Returns:
        The array.

    Raises:
        InputContractError: If it is missing or is not an array.
            **`InputContractError` AND NOT `ValidationError`, WHICH IS THE
            CODEBASE'S OWN CONVENTION RATHER THAN A CHOICE.** `validation.py`
            reserves `ValidationError` for layers 1-3 -- config failures, exit
            3 -- and `layer_of` maps `InputContractError` to layer 4, exit 4.
            **For this entry point the STORE is the data**: there is no config,
            so every refusal here is "your data is wrong" and must not reach a
            user as "your config is wrong". Mapping it to `INTERNAL_ERROR`
            instead would tell a scripting user the report is broken when their
            input is -- the collision 2e's Task 1 separated exit 5 from exit 1
            to prevent.
    """
    try:
        node = root[path]
    except KeyError as error:
        raise InputContractError(
            f"{root.store} carries no {path!r}; it is not a metamer store, or "
            "it was written by a version this reader does not know"
        ) from error
    if not isinstance(node, zarr.Array):
        raise InputContractError(f"{path!r} is not an array")
    return node


def _disagreements(
    outcome: NDArray[np.uint8], tiles: NDArray[np.uint8], side: int
) -> tuple[str, ...]:
    """Contradictions between the completion bitmap and the outcome array.

    **THE BITMAP IS AUTHORITATIVE AND THIS FUNCTION DOES NOT RESOLVE ANYTHING.**
    2a's write path lands the data and THEN sets the bit, so the bit is the
    stronger record -- but the two answer different questions, and the
    difference is not always a defect: the bitmap says which tiles were
    WRITTEN, the outcome says what a cell HOLDS, and a complete tile may
    legitimately hold `NOT_ATTEMPTED` once a candidate can be screened out.

    What IS a contradiction is a tile the bitmap calls complete that holds
    **any** `NOT_ATTEMPTED` cell. Section 12.5 is explicit: that code means
    *"nothing wrote here -- the absence of information"*, and *"a finished
    store should hold none"*. **A decided skip is `SCREENED_OUT`, which is the
    OPPOSITE member** -- information against its absence -- so a screened
    candidate is not an exception to this and never makes one.

    **`any`, NOT `all`, AND THE FIRST DRAFT OF THIS FUNCTION HAD IT WRONG.**
    Requiring every cell in the tile to be unwritten answers "was this tile
    written at all", which the bitmap already answers; the question here is
    whether the tile was written COMPLETELY, and one unwritten cell in a
    complete tile is exactly the partial write the check exists to surface.

    **Reported, never repaired**, because a reader that silently picks one
    record lets a partially-written tile read as a screened candidate -- and
    because section 14.2's report is the artifact that survives, so a defect it
    hides is a defect nobody sees.

    Args:
        outcome: `(y, x, m)` codes.
        tiles: The completion bitmap, `(ty, tx)`.
        side: The tile side, in cells.

    Returns:
        One note per contradicting tile, empty when there are none.
    """
    notes: list[str] = []
    unwritten = outcome == Outcome.NOT_ATTEMPTED.code
    for ty, tx in zip(*np.nonzero(tiles), strict=True):
        block = unwritten[
            int(ty) * side : (int(ty) + 1) * side,
            int(tx) * side : (int(tx) + 1) * side,
            :,
        ]
        if block.size and bool(block.any()):
            notes.append(
                f"tile ({int(ty)}, {int(tx)}) is marked complete in "
                f"/completion/tiles while {int(block.sum())} of its "
                f"{int(block.size)} cells read NOT_ATTEMPTED; "
                "the bitmap is authoritative (data is written before the bit is "
                "set) and this contradiction is reported rather than resolved"
            )
    return tuple(notes)


def read_store(path: Path | str) -> StoreView:
    """Open a finished store for READING and return its labelled arrays.

    **OPENED `mode="r"` THROUGHOUT.** The report never mutates its subject:
    section 14.2's decisive property is that it is usable on someone else's
    store, and a report that writes cannot be run on a store you do not own.

    Args:
        path: The store directory.

    Returns:
        Its arrays, labels, attributes and completion state.

    Raises:
        InputContractError: Layer 4, so `DATA_INVALID`, if the path is not a
            readable zarr group, is not a metamer store, or carries a
            `schema_version` this reader does not know.
    """
    store = Path(path)
    try:
        root = zarr.open_group(str(store), mode="r")
    except Exception as error:  # noqa: BLE001 - every zarr failure is one case
        raise InputContractError(
            f"{store} could not be opened as a zarr group: {error}"
        ) from error

    attrs = dict(root.attrs)
    version = attrs.get("schema_version")
    # **A ZARR ATTRIBUTE IS ANY JSON VALUE, SO THE TYPE IS CHECKED AND NOT
    # ASSUMED.** A foreign store may carry `"5"` or a mapping under this key,
    # and `int()` on either is a `TypeError` escaping as `INTERNAL_ERROR` --
    # the report claiming it is broken when the input is. mypy refused the
    # unguarded `int(version)` and was right to.
    if not isinstance(version, int) or isinstance(version, bool):
        raise InputContractError(
            f"{store} has no usable schema_version attribute (found "
            f"{version!r}); it is a zarr group but not a metamer store"
        )
    if version != SCHEMA_VERSION:
        # BOTH VERSIONS ARE NAMED. "Unsupported schema" sends a user looking at
        # their store; what they need is which writer made it and which reader
        # they are holding.
        raise InputContractError(
            f"{store} declares schema_version {version}; this reader "
            f"knows schema_version {SCHEMA_VERSION}"
        )

    outcome = np.asarray(_array(root, "status/outcome")[:], dtype=np.uint8)
    tiles = np.asarray(_array(root, "completion/tiles")[:], dtype=np.uint8)
    side = int(np.ceil(outcome.shape[0] / tiles.shape[0])) if tiles.size else 0

    return StoreView(
        path=store,
        outcome=outcome,
        delta_ic=np.asarray(_array(root, "selection/delta_ic")[:], dtype=np.float32),
        selected=np.asarray(_array(root, "selection/selected")[:], dtype=np.int16),
        n_valid=np.asarray(_array(root, "selection/n_valid")[:], dtype=np.int16),
        iterations=np.asarray(
            _array(root, "primitives/iterations")[:], dtype=np.uint16
        ),
        model_labels=tuple(
            str(name) for name in np.asarray(_array(root, "status/m")[:]).tolist()
        ),
        criterion_labels=tuple(
            str(name) for name in np.asarray(_array(root, "selection/c")[:]).tolist()
        ),
        attrs=attrs,
        completion=Completion(
            complete=int(np.count_nonzero(tiles)), total=int(tiles.size)
        ),
        disagreements=_disagreements(outcome, tiles, side),
    )
