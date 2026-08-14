"""The completion bitmap: what a bit means, when it is set, and how a run stops.

**THE BIT IS AN IDENTITY, NOT A REQUEST, AND THE FOURTH IDENTITY FACT FAILS
HERE.** `/completion/tiles[ty,tx]` claims what the *store contains*, so it must
be populated by reading the thing it identifies -- and the only independent
reader is one that re-reads every region it just wrote, at 10^7 points, per
tile. So the writer reports on itself, and what makes that safe is structural
rather than conventional:

- **`write.write_tile` has no decline path** (Task 9, deliberately), so "the
  write returned" and "every region write for this tile was issued" are the same
  event. A later "skip this tile" exit there would silently turn the bit into a
  self-report of nothing.
- **The bit is set at exactly one site**, immediately after that return, and no
  other exit sets one.

**Scope, stated rather than implied:** a set bit certifies that every region
write for the tile returned. It does not certify that the bytes survive a power
cut -- there is no `fsync`, because an `fsync` is a POSIX assumption of the kind
section 15.5 forbids in the store layer, which relies on per-object write
atomicity alone. Measured 2026-08-13: setting one bit at `chunks=(1,1)` creates
exactly one object, so no other tile's bit is read-modify-written.

**THE BIT'S INDEX IS ITSELF A NAME WHOSE MEANING CAN MOVE.** `ty` is
`y_start // tile_side`, and `tile_side` derives from `memory_budget_gb`, which is
**run-relevant and therefore in neither `fit_hash` nor `compat_hash`** -- by
design (section 13.3), so that "run locally, burst to cloud, resume" is a resume
rather than a rerun. A resume at a different budget would therefore pass every
gate and re-tile the grid, after which bit `(1,0)` names a different region than
the one it was set for: some points never written, others written twice, and the
bitmap fully set at the end. `resume_tile_side` is the guard, and its rule is
over the derived **side** rather than over the budget, because two budgets can
derive the same side and refusing on the budget would refuse a resume that is
geometrically identical.

**SIGTERM RECORDS AND RETURNS -- IT MUST NOT RAISE.** The brief asks for two
things about the same window: an injected fault between the data write and the
bit leaves the bit unset, and SIGTERM flushes rather than dying mid-region-write.
Those are consistent only if the signal is never observed *inside* that window,
so the handler sets a flag and the flag is read after the bit is written,
between tiles. A raising handler would land its exception at a point no caller
chooses, in exactly the window the other requirement protects.

**AND THE MODULE LIVES HERE RATHER THAN IN `run.py` BECAUSE OF A NAME.**
`run.run` binds `signal = config.signal_spec()`, which shadows the stdlib module
for the whole body of the function that would otherwise install the handler.
"""

from __future__ import annotations

import signal
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import FrameType
from typing import Any, Literal

import numpy as np
import zarr
from numpy.typing import NDArray

from metamer.batch.tiling import Tile
from metamer.batch.validation import ValidationError, ValidationLayer

#: A tile whose data is wholly written. The complement, 0, is the array's fill
#: value: **the one place in this store where a zero fill is the true value**,
#: because an unwritten tile really is incomplete (see `store`'s fill table).
COMPLETE = 1

#: Nothing wrote this tile. Identical to the fill, deliberately.
INCOMPLETE = 0


@dataclass
class Termination:
    """Whether a SIGTERM was recorded, and whether one could have been.

    Attributes:
        armed: True when the handler is installed. `signal.signal` works only on
            the main thread of the main interpreter, so a run driven from a
            worker thread cannot arm it -- **the regime is declared rather than
            crashed on or silently claimed**, since a caller that believes it is
            protected and is not loses a tile mid-write.
        received: True once SIGTERM has arrived. Read between tiles, never
            inside the data-then-bitmap window.
    """

    armed: bool = False
    received: bool = False


def tile_index(tile: Tile, side: int) -> tuple[int, int]:
    """Return the bitmap position covering `tile`.

    Args:
        tile: A tile `tiling.tile_grid` produced at this `side`.
        side: The tile side the store was created with.

    Returns:
        `(ty, tx)`, in that order -- the same order as
        `store.StoreShape.n_tiles_y` and `n_tiles_x`.

    Raises:
        ValueError: If `side` is not positive, or `tile` does not start on a
            tile boundary. **`tiling.assembly_spans` builds `Tile` objects for
            chunk-aligned sub-spans**, which are the same type and are not grid
            tiles; a floor division would quietly give such a span the bit of
            the tile containing it, marking a whole tile complete from a
            fraction of its data.
    """
    if side <= 0:
        raise ValueError(f"tile side must be positive, got {side}")
    if tile.y_start % side or tile.x_start % side:
        raise ValueError(
            f"({tile.y_start}, {tile.x_start}) is not the start of a tile at side "
            f"{side}; only a tile from tile_grid has a completion bit, and a "
            "chunk-aligned span is not one"
        )
    return tile.y_start // side, tile.x_start // side


def _bitmap(store_path: Path | str, mode: Literal["r", "r+"]) -> zarr.Array[Any]:
    """Open the completion bitmap of an existing store.

    Args:
        store_path: An existing store.
        mode: A zarr open mode.

    Returns:
        The `/completion/tiles` array.

    Raises:
        ValidationError: Layer 3, if the store has no completion bitmap. A store
            written by an older schema is not resumable by this one, and reading
            an absent bitmap as "nothing is complete" would refit a finished
            store silently.
    """
    root = zarr.open_group(str(store_path), mode=mode)
    group = root.get("completion")
    array = group.get("tiles") if isinstance(group, zarr.Group) else None
    if not isinstance(array, zarr.Array):
        raise ValidationError(
            ValidationLayer.SEMANTIC,
            f"{store_path} has no /completion/tiles array, so which tiles it "
            "holds cannot be established; it was not written by this schema",
        )
    return array


def completed_tiles(store_path: Path | str) -> NDArray[np.bool_]:
    """Read the completion bitmap.

    **Read from the store on every call**, never cached across a run: the array
    is the coordination point between one process and the next, and a copy held
    in memory is correct exactly in the process that has no use for it.

    Args:
        store_path: An existing store.

    Returns:
        A boolean array shaped `(n_tiles_y, n_tiles_x)`.

    Raises:
        ValidationError: Layer 3, if the store has no completion bitmap.
    """
    bits = np.asarray(_bitmap(store_path, "r")[:], dtype=np.uint8)
    done: NDArray[np.bool_] = bits == COMPLETE
    return done


def mark_complete(store_path: Path | str, index: tuple[int, int]) -> None:
    """Set one tile's completion bit.

    **Call this only after that tile's data write has returned.** The bit's
    entire meaning is the ordering; see the module docstring.

    Args:
        store_path: An existing store.
        index: `(ty, tx)` from `tile_index`.

    Raises:
        ValidationError: Layer 3, if the store has no completion bitmap.
    """
    _bitmap(store_path, "r+")[index] = np.uint8(COMPLETE)


def resume_tile_side(
    store_path: Path | str, *, derived_side: int, grid: tuple[int, int]
) -> int:
    """Return the tile side a resume of `store_path` must use.

    The store's shards were fixed at creation, so its tile side -- not this
    run's budget -- is what its completion bits index. **The rule is over the
    derived side and never over the budget**: two budgets can derive the same
    side, and refusing on the budget would refuse a resume that is
    geometrically identical.

    Args:
        store_path: An existing store.
        derived_side: The tile side this run's memory budget gives.
        grid: `(n_y, n_x)` from the input contract.

    Returns:
        The stored side, which is at most `derived_side`.

    Raises:
        ValidationError: Layer 3, if the store's tile side does not fit this
            run's memory budget, or if its bitmap does not describe this grid.
            **Adopting a larger stored tile would silently exceed the budget the
            user set**, which is the one knob on peak RAM.
    """
    attrs = dict(zarr.open_group(str(store_path), mode="r").attrs)
    sides = attrs.get("tile_sides")
    stored = sides.get("shared") if isinstance(sides, Mapping) else None
    if not isinstance(stored, int):  # pragma: no cover - provenance invariant
        raise ValidationError(
            ValidationLayer.SEMANTIC,
            f"the store at {store_path} records no tile side, so which region "
            "each of its completion bits covers cannot be established",
        )
    budget = attrs.get("memory_budget_gb")
    if stored > derived_side:
        raise ValidationError(
            ValidationLayer.SEMANTIC,
            f"the store at {store_path} has a tile side of {stored} and this "
            f"run's memory budget gives {derived_side}. Its shards are fixed at "
            f"creation, so finishing it needs tiles of {stored} points a side "
            f"and the budget that produced them was {budget} GB. Either raise "
            "--memory-budget to at least that, or write a new store",
        )

    expected = (-(-grid[0] // stored), -(-grid[1] // stored))
    shape = tuple(int(n) for n in _bitmap(store_path, "r").shape)
    if shape != expected:
        raise ValidationError(
            ValidationLayer.SEMANTIC,
            f"the store at {store_path} has a {shape[0]}x{shape[1]} completion "
            f"bitmap and this run's {grid[0]}x{grid[1]} grid at tile side "
            f"{stored} needs {expected[0]}x{expected[1]}; the bits index "
            "different regions than the ones they were set for",
        )
    return stored


@contextmanager
def flush_on_sigterm() -> Iterator[Termination]:
    """Record SIGTERM instead of dying on it, for the duration of the block.

    **The handler does nothing but record**, so a region write in flight is
    never interrupted -- section 15.5's "handle SIGTERM by flushing rather than
    dying mid-region-write", and the reason preemption is just resumption. The
    caller reads `received` between tiles.

    **A second SIGTERM is recorded like the first and does not escalate.** An
    operator who wants the process gone immediately has SIGKILL, which is exit
    criterion 1's mechanism and which this store is already required to survive;
    a handler that restored the default disposition on the second signal would
    be a second, undocumented way to die inside the protected window.

    Yields:
        The record, live for the duration of the block.
    """
    termination = Termination()

    def handler(number: int, frame: FrameType | None) -> None:
        """Record the signal.

        Args:
            number: The signal number, unused.
            frame: The interrupted frame, unused.
        """
        termination.received = True

    try:
        previous = signal.signal(signal.SIGTERM, handler)
    except ValueError:
        # Main-thread-only, measured: "signal only works in main thread of the
        # main interpreter". An embedded run is legal and gets no handler, and
        # says so rather than claiming a protection it does not have.
        yield termination
        return

    termination.armed = True
    try:
        yield termination
    finally:
        signal.signal(signal.SIGTERM, previous)
