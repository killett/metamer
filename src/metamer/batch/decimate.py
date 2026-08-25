"""Pass 1's input: the parent grid, taken every `k`-th cell on both spatial axes.

WHAT THIS MODULE IS FOR (design doc section 11.1, decision D11).
----------------------------------------------------------------
Phase 2c's two-pass warm start fits a coarse grid first and warm-starts the full
grid from it. **Pass 1 is not a new mechanism.** It is `run` over a decimated
view of the same input, with its own store, its own completion bitmap and its own
resume, and everything downstream of the open is untouched. This module is the
whole of the difference.

THE DECIMATION IS INDEX ARITHMETIC ON DATASET COORDINATES.
-----------------------------------------------------------
Not on tiles, not on chunks, not on anything the memory budget can move. That is
what makes section 11.3's guarantee survive a budget change: which points pass 1
fits is a function of the dataset and the stride alone, so two runs at different
`--memory-budget` values fit the same coarse points and a pass-2 point resolves
to the same source.

THE SPATIAL DIMENSIONS ARE TAKEN POSITIONALLY, AND THAT IS NOT COSMETIC.
------------------------------------------------------------------------
`input.check_input_contract` requires exactly three dimensions and that the first
is `time`. **It says nothing about the names of the other two** -- its own message
calls the contract "three, mapping to (time, y, x)", which is positional. Real
gridded products routinely use `latitude`/`longitude` or `lat`/`lon`.

Every fixture in this repository happens to use `("time", "y", "x")`, so a
decimation written as `isel(y=..., x=...)` passes the entire suite and raises on
the first input that does not. This one reads `array.dims[1]` and `array.dims[2]`.

**THAT DOES NOT MEAN SUCH AN INPUT WORKS END TO END, AND THE HONEST STATEMENT IS
HERE RATHER THAN IN A COMMIT MESSAGE.** `tiling.py` takes the literal names in
four places -- the span tuples, the `by_dim` lookups and `assemble_tile`'s own
`isel` -- so an input named otherwise still fails, deep in assembly, with a raw
`xarray` error rather than the staged `InputContractError` that `input.py`
requires of every stage-4a failure. **That is a pre-existing defect with two
possible closers** -- stage 4a enforces the names, or the tiling path goes
positional -- **and choosing between them was not this task's decision.** What is
in this module's control is not becoming the fifth site, which is why the
arithmetic here is correct under either closer.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from metamer.batch.input import InputHandle

PASS1_SUFFIX = ".pass1"
"""Inserted before the output store's extension to name pass 1's store.

`out.zarr` gives `out.pass1.zarr`. **Beside the output and derived from it**, so
the two are visibly one run's artifacts rather than two unrelated directories.
"""


def decimated_handle(handle: InputHandle, stride: int) -> InputHandle:
    """Return `handle` with both spatial axes taken every `stride`-th index.

    The time axis is untouched: decimation is spatial, and a coarse point is a
    whole series.

    Args:
        handle: An opened input. It need not have passed the stage-4a contract
            yet, but its variable must be three-dimensional with time first --
            which is what the contract checks, and what this relies on to take
            the spatial axes positionally.
        stride: The coarse stride `k`. `1` is legal and returns an equivalent
            view rather than a special case.

    Returns:
        A new `InputHandle` over the decimated dataset. Same variable, same
        scheme, same `uri` -- **it is the same input, differently sampled**, and
        recording a synthetic URI here would put a location that does not exist
        into the store's provenance.

    Raises:
        ValueError: If `stride` is below 1, or the variable is not
            three-dimensional with `time` first.
    """
    if stride < 1:
        raise ValueError(f"the coarse stride must be at least 1, got {stride}")
    array = handle.dataset[handle.variable]
    if array.ndim != 3 or str(array.dims[0]) != "time":
        raise ValueError(
            f"cannot decimate {handle.variable!r} with dims {array.dims}: the "
            f"decimation takes the second and third dimensions positionally, so "
            f"the variable must be three-dimensional with 'time' first"
        )
    # POSITIONAL, NOT `y=`/`x=`. See the module docstring: the contract does not
    # require those names and every fixture in this repository happens to use
    # them, so the name-based form is invisible to the whole suite.
    axes = {str(array.dims[1]): slice(None, None, stride)}
    axes[str(array.dims[2])] = slice(None, None, stride)
    return replace(handle, dataset=handle.dataset.isel(axes))


def pass1_store_path(store_path: Path | str) -> Path:
    """Return where pass 1's store goes, given pass 2's output path.

    `out.zarr` gives `out.pass1.zarr`; a path with no extension gains one, so
    `out` gives `out.pass1`.

    **PASS 1'S STORE IS A PERMANENT SECOND ARTIFACT AND MUST NOT BE DELETED WHEN
    PASS 2 COMPLETES.** It is the cold reference the section 11.2 hysteresis
    audit compares against -- there is no other record of what the same points
    fit to without a warm start -- and it is the default source for `/detail/`.
    Deleting it does not free a cache; it discards the only measurement that can
    say whether the warm start moved anything.

    **The rule is stated here, at the derivation, because a second directory
    beside an output is read as scratch unless something says otherwise**, and
    the place a reader looks is the code that named it. It is in `README.md` for
    the same reason.

    Args:
        store_path: Pass 2's output store path.

    Returns:
        Pass 1's store path, in the same parent directory.
    """
    path = Path(store_path)
    return path.with_name(path.stem + PASS1_SUFFIX + path.suffix)


__all__ = ["PASS1_SUFFIX", "decimated_handle", "pass1_store_path"]
