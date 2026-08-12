"""The opener registry, the zarr opener, and the stage-4a input contract.

**THE CONTRACT IS ON DATASET SHAPE, NOT FILE FORMAT.** One named variable, dims
mapping to `(time, y, x)`, a 1-D decodable time coordinate. Everything after
`open_input` works on an `InputHandle` and never learns which opener produced it.

**ONE OPENER IS REGISTERED AND THE ZARR ENTRY HAS NO PRIVILEGED PATH.** netCDF
is deferred, and the point of the registry is that adding it must be a
**registration and not a refactor**. That is asserted rather than intended:
`tests/test_input.py` registers a second opener under its own scheme and drives
the whole of `open_input` through it, so a zarr special case anywhere in this
module fails a test. Two openers do not test the tiling loop twice -- they test
xarray twice -- which is why the second one exists only in a test.

The registry is `core.registry.Registry`, the same class the kernel families
use, so it carries the entry-point group for free: a third-party opener is a
package that registers `metamer.openers`, with nothing here to change.

**STAGE 4a IS LAYER 4's FIRST STAGE, DELIBERATELY NOT A FIFTH LAYER.** Otherwise
it becomes one by accident when pass 1 lands and layer 4 acquires its
"runs against pass 1" home.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import numpy as np
from numpy.typing import NDArray

from metamer.batch.timeaxis import (
    calendar_of,
    check_strictly_increasing,
    to_decimal_years,
    unique_dt_count,
)
from metamer.core.registry import Registry

if TYPE_CHECKING:  # pragma: no cover - import cost only
    import xarray as xr

Opener = Callable[[str], "xr.Dataset"]

opener_registry: Registry[Opener] = Registry(
    "opener_registry", entry_point_group="metamer.openers"
)
"""Scheme name -> opener. **Declared, never sniffed.**

The scheme comes from `data_uri`, so `zarr://`, `s3://.../x.zarr` and a bare
path all resolve through a name the config states. Content sniffing would make
the opener a property of the bytes rather than of the configuration, and a
mis-sniffed file is a wrong answer where an unknown scheme is a refusal.
"""


class InputContractError(ValueError):
    """A stage-4a violation: the data is not what the config says it is.

    **Layer 4, not layer 3.** It is data-dependent, so it cannot be raised from
    a config alone and it must not be reported as a config error -- Task 4's
    exit code 4 against exit code 3. The distinction is the whole reason
    validation is staged: "your config is wrong" and "your data is wrong" send a
    user to different places.
    """


@dataclass(frozen=True)
class InputHandle:
    """An opened dataset plus the facts the rest of the run needs from it.

    Attributes:
        dataset: The opened `xarray.Dataset`.
        variable: Name of the variable being fitted.
        scheme: Registry key of the opener that produced this.
        uri: The `data_uri` it was opened from.
    """

    dataset: Any
    variable: str
    scheme: str
    uri: str


@dataclass(frozen=True)
class ContractReport:
    """What stage 4a established. Everything here reaches provenance.

    **MEASURE IN THE PHASE THAT CAN, PRINT IN THE PHASE THAT SHOWS.**
    `unique_dt` in particular is computed here and printed by `--explain` in
    Phase 5; computing it twice is how the two versions come to disagree.

    Attributes:
        n_time: Length of the time axis.
        n_y: Length of the first spatial axis.
        n_x: Length of the second spatial axis.
        calendar: The DECODED calendar, never the attrs string.
        source_dtype: The stored dtype of the variable, as a string. Part of the
            geometry fingerprint at Task 3, because float32 and float64 sources
            are not the same input.
        units: The `units` attribute as found, or None. **Provenance only** --
            the calendar above is what the conversion actually used.
        unique_dt: Number of distinct timesteps, from `StateSpace.unique_dt`.
            See `timeaxis.unique_dt_count` for what this number is and, more
            usefully, what it is not.
        t_start: First timestamp in decimal years.
        t_end: Last timestamp in decimal years.
        median_dt: Median gap between adjacent timestamps, in decimal years.
            **The identifiability lint's `sampling_interval` is this number**,
            and it is measured here because this is where the decoded axis
            already exists -- measure in the phase that can. It is the MEDIAN
            of the realized gaps, not `(t_end - t_start) / n_time`: the latter
            is off by `(n-1)/n` on a regular axis and is silently wrong on a
            gapped one, and a lint comparing a timescale against it would
            report on a sampling that never happened.
    """

    n_time: int
    n_y: int
    n_x: int
    calendar: str
    source_dtype: str
    units: str | None
    unique_dt: int
    t_start: float
    t_end: float
    median_dt: float


def _scheme_of(uri: str) -> str:
    """Return the registry key for a `data_uri`.

    A bare filesystem path has no scheme, and its extension is the only
    declaration available -- so `/data/ssh.zarr` resolves to `zarr` by suffix.
    That is still a declaration in the config rather than a property of the
    bytes.

    Args:
        uri: The configured `data_uri`.

    Returns:
        The registry key.

    Raises:
        InputContractError: If no scheme can be determined. The message lists
            the registered openers, which is the fact a user needs.
    """
    parsed = urlparse(uri)
    if parsed.scheme in opener_registry:
        return parsed.scheme
    suffix = uri.rstrip("/").rsplit(".", 1)
    if len(suffix) == 2 and suffix[1] in opener_registry:
        return suffix[1]
    raise InputContractError(
        f"cannot determine an opener for data_uri {uri!r}. Registered openers: "
        f"{', '.join(opener_registry)}. Name one as the URI scheme "
        "(e.g. 'zarr://path') or use a matching suffix"
    )


def _open_zarr(uri: str) -> xr.Dataset:
    """Open a zarr store, leaving the time axis decoded and the data lazy.

    `decode_times=True` is the default and is relied on: CF decoding is what
    turns a numeric axis with `units` into datetimes, and it is the ONLY route
    by which a time axis becomes usable. A store whose axis does not decode is
    refused at stage 4a rather than guessed at.

    `chunks=None` keeps this out of dask deliberately -- 2a materializes one
    tile at a time with `.load()`, whose peak is analytic where a graph's is
    emergent.

    Args:
        uri: Path or URL, with any `zarr://` prefix already meaningful to fsspec.

    Returns:
        The opened dataset.
    """
    import xarray as xr

    location = uri[len("zarr://") :] if uri.startswith("zarr://") else uri
    dataset: xr.Dataset = xr.open_zarr(location, chunks=None, decode_times=True)
    return dataset


opener_registry.register("zarr")(_open_zarr)


def open_input(uri: str, variable: str) -> InputHandle:
    """Open `uri` through the registered opener for its scheme.

    Args:
        uri: The configured `data_uri`.
        variable: Name of the variable to fit.

    Returns:
        The handle.

    Raises:
        InputContractError: If no opener matches, or the opener fails.
    """
    scheme = _scheme_of(uri)
    opener = opener_registry[scheme]
    try:
        dataset = opener(uri)
    except InputContractError:
        raise
    except Exception as error:  # noqa: BLE001 - re-raised with the URI named
        raise InputContractError(
            f"the {scheme!r} opener could not open {uri!r}: {error}"
        ) from error
    return InputHandle(dataset=dataset, variable=variable, scheme=scheme, uri=uri)


def decimal_year_axis(handle: InputHandle) -> NDArray[np.float64]:
    """Return the handle's time axis in decimal years.

    Args:
        handle: An opened input.

    Returns:
        Decimal years, shape `(n_time,)`.

    Raises:
        InputContractError: If the axis is missing, not one-dimensional, or was
            not decoded to timestamps.
    """
    dataset = handle.dataset
    if "time" not in dataset.coords and "time" not in dataset.variables:
        raise InputContractError(
            f"{handle.uri!r} has no 'time' coordinate; the contract is one named "
            "variable over dims mapping to (time, y, x)"
        )
    coordinate = dataset["time"]
    if coordinate.ndim != 1:
        raise InputContractError(
            f"'time' has {coordinate.ndim} dimensions; it must be 1-D"
        )
    try:
        return to_decimal_years(coordinate.values)
    except TypeError as error:
        units = coordinate.attrs.get("units")
        raise InputContractError(
            f"{handle.uri!r}: the time axis did not decode to timestamps "
            f"(dtype {coordinate.dtype}, units attribute {units!r}). "
            "**No unit is inferred from magnitude**: days-since-1970 over 50 "
            "years is about 2e4 and years-since-0 is about 2e3, so a "
            "magnitude heuristic is ambiguous on exactly the axis it must "
            "disambiguate. Supply a CF-decodable 'units' attribute "
            "(e.g. 'days since 1970-01-01') and a 'calendar'"
        ) from error


def _source_units(coordinate: xr.DataArray) -> str | None:
    """Return the source `units` string of a decoded time coordinate.

    **`.encoding` FIRST, AND THAT IS NOT A DETAIL.** CF decoding CONSUMES the
    `units` and `calendar` attributes and files them under `.encoding`, so
    reading `.attrs` alone returns None for every successfully decoded axis --
    i.e. for every axis this code ever sees. Measured: a round-tripped zarr
    store reported `units=None` from `.attrs` while its encoding carried
    `days since 2000-01-01`. A provenance field that is always empty is a name
    that records nothing, and nothing else would have said so.

    `.attrs` remains the fallback for an axis that arrived already decoded and
    never went through the CF path.

    Args:
        coordinate: The decoded time coordinate.

    Returns:
        The source units string, or None if there genuinely is not one.
    """
    units = coordinate.encoding.get("units")
    if units is None:
        units = coordinate.attrs.get("units")
    return None if units is None else str(units)


def check_contract(handle: InputHandle) -> ContractReport:
    """Stage 4a: verify the dataset's shape and time axis, and report on them.

    Runs at store-open, before any tile. The ordering is the guard -- §13.7 puts
    this before the geometry fingerprint and therefore before `fit_hash`, because
    a hash computed before the contract check would be computed from the config
    alone, which is where `data_uri`-as-proxy came from.

    Args:
        handle: An opened input.

    Returns:
        What stage 4a established, for provenance.

    Raises:
        InputContractError: If the variable is missing, the dims are not
            three, or the time axis is unusable.
    """
    dataset = handle.dataset
    if handle.variable not in dataset.variables:
        available = ", ".join(sorted(map(str, dataset.data_vars)))
        raise InputContractError(
            f"{handle.uri!r} has no variable {handle.variable!r}. Available: "
            f"{available}"
        )
    array = dataset[handle.variable]
    if array.ndim != 3:
        raise InputContractError(
            f"variable {handle.variable!r} has {array.ndim} dimensions "
            f"{array.dims}; the contract is three, mapping to (time, y, x)"
        )
    if array.dims[0] != "time":
        raise InputContractError(
            f"variable {handle.variable!r} has dims {array.dims}; 'time' must be "
            "the first, so a tile is a contiguous spatial block of whole series"
        )

    t = decimal_year_axis(handle)
    # EVERY STAGE-4a FAILURE MUST BE AN `InputContractError`, INCLUDING THE ONES
    # RAISED BY HELPERS. `check_strictly_increasing` lives in `timeaxis`, which
    # knows nothing about validation staging, so it raises a plain `ValueError`
    # -- and a plain `ValueError` escaping stage 4a is an unhandled error rather
    # than Task 4's exit code 4. Caught by the duplicate-timestamp test, which
    # asked for the staged type and got the bare one.
    try:
        check_strictly_increasing(t)
    except ValueError as error:
        raise InputContractError(f"{handle.uri!r}: {error}") from error
    if t.size != array.shape[0]:
        raise InputContractError(
            f"the time coordinate has {t.size} entries and "
            f"{handle.variable!r} has {array.shape[0]} along 'time'"
        )

    return ContractReport(
        n_time=int(array.shape[0]),
        n_y=int(array.shape[1]),
        n_x=int(array.shape[2]),
        calendar=calendar_of(dataset["time"].values),
        source_dtype=str(array.dtype),
        units=_source_units(dataset["time"]),
        unique_dt=unique_dt_count(t),
        t_start=float(t[0]),
        t_end=float(t[-1]),
        median_dt=float(np.median(np.diff(t))),
    )
