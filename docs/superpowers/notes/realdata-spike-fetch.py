#!/usr/bin/env python
"""Fetch a box of CMEMS DUACS monthly gridded SLA and write it as a local zarr.

**THIS IS AN INSTRUMENT, NOT PREPARATION.** The pre-flight's finding F5 is that
`metamer`'s opener registry has exactly one member -- `_open_zarr` -- and that
netCDF is deferred, so a real product reaches the shipped run only through a
conversion. **The conversion chooses the chunking**, which sets `chunk_shape`,
`read_amplification` and `assembly_spans`; it chooses the dtype; and it chooses
which points exist at all. (j8)'s second register: a rate recorded without its
workload can be quoted and cannot be reproduced, and every one of those choices
is part of the workload. So this script is committed beside the measurement it
feeds, and it writes a provenance record naming each choice.

## What it does NOT do, deliberately

**IT DOES NOT RENAME THE DIMENSIONS.** The product ships `(time, latitude,
longitude)` and the local store keeps those names. Renaming them to `y`/`x` is
the one edit that would make the run succeed, and it would do so by making the
pre-flight's finding F6 unreachable -- a clean result about a path that is still
broken for every user who does not know to rename. (i2) at a conversion: an
absence produced by correct behaviour and an absence produced by our own
workaround are the same green.

**IT ADDS NO DEPENDENCY.** `fsspec`'s HTTP filesystem needs `aiohttp`, which
this environment does not have, and `pixi add` re-solves the lock -- the same
lock every committed anchor was measured under, and whose numpy and BLAS the
2d field's byte digests are pinned to. **Changing the environment to obtain the
fixture would change the instrument**, so the store is mirrored with `urllib`
against the zarr v2 key layout the store publishes in its own `.zmetadata`.

## The two-step shape, and why the mirror is not the deliverable

A partial mirror is a store whose unfetched chunks read back as the fill value,
which is (a0) exactly: "never written" and "written as fill" are the same bytes,
and a global array with three chunks present would read as a mostly-empty ocean
rather than as an incomplete download. **So the mirror is a scratch artifact**:
the script asserts the requested box lies wholly inside the fetched chunks, cuts
the box out, and writes a fresh store in which every point is real.

Usage:
    realdata-spike-fetch.py <out-dir> [--lat0 20 --lat1 35 --lon0 -40 --lon1 -20]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import xarray as xr

#: The STAC item this store is published under. **Recorded rather than derived
#: from the URL**, because the URL carries a bucket number that is an operator's
#: choice and the item id is the product's own name for itself.
STAC_ITEM = (
    "https://stac.marine.copernicus.eu/metadata/SEALEVEL_GLO_PHY_L4_MY_008_047/"
    "cmems_obs-sl_glo_phy-ssh_my_allsat-l4-duacs-0.125deg_P1M-m_202411/"
    "dataset.stac.json"
)

#: The ARCO zarr v2 store, read anonymously. **Anonymous access was measured,
#: not assumed**: `.zmetadata` returns 200 with no credentials, while a bucket
#: listing returns 403 -- which is ordinary and is why the key layout below is
#: computed rather than enumerated.
STORE = (
    "https://s3.waw3-1.cloudferro.com/mdl-arco-time-045/arco/"
    "SEALEVEL_GLO_PHY_L4_MY_008_047/"
    "cmems_obs-sl_glo_phy-ssh_my_allsat-l4-duacs-0.125deg_P1M-m_202411/"
    "timeChunked.zarr"
)

#: The variable, which is what `bench.fields.config_text` already names. The
#: pre-flight's F3 asked whether the single-source config could express this
#: product's variable name; for DUACS it can, unchanged.
VARIABLE = "sla"

#: Arrays the local store keeps. The product also carries `lat_bnds`,
#: `lon_bnds` and `climatology_bnds` on an `nv` axis; they are dropped, and the
#: drop is recorded rather than silent. `check_contract` reads the VARIABLE's
#: rank, so they would not have refused the input -- they are dropped because a
#: store carrying axes nothing fits is a store whose geometry components say
#: more than the run used.
KEEP = (VARIABLE,)

_TIMEOUT = 60.0


def _get(url: str) -> bytes:
    """One anonymous GET over https, with the status left to raise.

    **THE SCHEME IS CHECKED RATHER THAN SUPPRESSED.** `urlopen` accepts `file:`
    and any registered handler, so a URL assembled from metadata could read the
    local filesystem and return it as though it came from the store -- which is
    the same class as the opener registry's own rule that a scheme is declared
    and never sniffed. The guard is what makes the `noqa` below honest.

    Args:
        url: The absolute https URL to fetch.

    Returns:
        The response body.

    Raises:
        ValueError: If the URL is not https.
    """
    if not url.startswith("https://"):
        raise ValueError(f"refusing a non-https fetch: {url!r}")
    with urllib.request.urlopen(url, timeout=_TIMEOUT) as response:  # noqa: S310
        payload: bytes = response.read()
    return payload


def _ensure(destination: Path, key: str) -> bytes:
    """Return the bytes for one store key, fetching it only if absent.

    **THE BYTES ARE READ BACK EITHER WAY, WHICH IS WHAT KEEPS A RE-RUN HONEST.**
    A cheap re-run that skipped the digest would make "fetched now" and "fetched
    on some earlier run under some earlier box" the same record -- (a0) at a
    provenance field. The digest is always taken over what is actually on disk.

    Args:
        destination: The mirror root.
        key: The zarr key, relative to the store.

    Returns:
        The key's bytes.
    """
    target = destination / key
    if not (target.exists() and target.stat().st_size > 0):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(_get(f"{STORE}/{key}"))
    return target.read_bytes()


@dataclass(frozen=True)
class Box:
    """The requested box, in degrees and then in index space.

    Attributes:
        lat0: Southern edge, degrees north.
        lat1: Northern edge, degrees north.
        lon0: Western edge, degrees east.
        lon1: Eastern edge, degrees east.
        i0: First latitude index inside the box.
        i1: One past the last latitude index.
        j0: First longitude index inside the box.
        j1: One past the last longitude index.
    """

    lat0: float
    lat1: float
    lon0: float
    lon1: float
    i0: int
    i1: int
    j0: int
    j1: int


def resolve_box(
    latitude: np.ndarray,
    longitude: np.ndarray,
    *,
    lat0: float,
    lat1: float,
    lon0: float,
    lon1: float,
) -> Box:
    """Turn a degree box into half-open index ranges.

    **Resolved against the COORDINATE ARRAYS, never against the documented
    step.** The STAC metadata states a 0.125 step and a first cell centre; a box
    computed from those two numbers is a second derivation of the grid, and it
    agrees with the store until one of them moves. (j9).

    Args:
        latitude: The store's own latitude values.
        longitude: The store's own longitude values.
        lat0: Southern edge, degrees north.
        lat1: Northern edge, degrees north.
        lon0: Western edge, degrees east.
        lon1: Eastern edge, degrees east.

    Returns:
        The box, in degrees and index space.

    Raises:
        ValueError: If either range selects no cells.
    """
    rows = np.flatnonzero((latitude >= lat0) & (latitude <= lat1))
    columns = np.flatnonzero((longitude >= lon0) & (longitude <= lon1))
    if rows.size == 0 or columns.size == 0:
        raise ValueError(
            f"box lat [{lat0}, {lat1}] lon [{lon0}, {lon1}] selects "
            f"{rows.size} rows and {columns.size} columns; both must be > 0"
        )
    return Box(
        lat0=lat0,
        lat1=lat1,
        lon0=lon0,
        lon1=lon1,
        i0=int(rows[0]),
        i1=int(rows[-1]) + 1,
        j0=int(columns[0]),
        j1=int(columns[-1]) + 1,
    )


def mirror(destination: Path, *, box: Box, metadata: dict[str, Any]) -> dict[str, Any]:
    """Copy the metadata and the chunks the box needs into a local zarr v2 tree.

    Args:
        destination: Directory to create the mirror in.
        box: The resolved box.
        metadata: The store's consolidated `.zmetadata` payload.

    Returns:
        A record of what was fetched: the chunk grid, the key count and the
        total bytes, plus a digest over the fetched chunk bytes in key order.

    Raises:
        ValueError: If the box does not lie wholly inside the fetched chunks.
    """
    destination.mkdir(parents=True, exist_ok=True)
    entries: dict[str, Any] = metadata["metadata"]

    # EVERY METADATA KEY IS COPIED, INCLUDING THE ARRAYS WE DROP LATER. The
    # mirror has to be a readable zarr group before anything can be cut out of
    # it, and a group whose `.zmetadata` lists an array with no `.zarray` is not.
    for key, value in entries.items():
        target = destination / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(value))
    (destination / ".zmetadata").write_text(json.dumps(metadata))

    spec = entries[f"{VARIABLE}/.zarray"]
    n_time, n_lat, n_lon = (int(size) for size in spec["shape"])
    chunk_t, chunk_lat, chunk_lon = (int(size) for size in spec["chunks"])

    lat_chunks = range(box.i0 // chunk_lat, (box.i1 - 1) // chunk_lat + 1)
    lon_chunks = range(box.j0 // chunk_lon, (box.j1 - 1) // chunk_lon + 1)
    time_chunks = range((n_time + chunk_t - 1) // chunk_t)

    covered_lat = (
        lat_chunks[0] * chunk_lat,
        min((lat_chunks[-1] + 1) * chunk_lat, n_lat),
    )
    covered_lon = (
        lon_chunks[0] * chunk_lon,
        min((lon_chunks[-1] + 1) * chunk_lon, n_lon),
    )
    if not (
        covered_lat[0] <= box.i0
        and box.i1 <= covered_lat[1]
        and covered_lon[0] <= box.j0
        and box.j1 <= covered_lon[1]
    ):  # pragma: no cover - arithmetic above makes this unreachable
        raise ValueError("the requested box is not covered by the fetched chunks")

    digest = hashlib.sha256()
    fetched = 0
    total = 0

    # THE ONE-DIMENSIONAL ARRAYS ARE FETCHED WHOLE. They are one chunk each here
    # (1440, 2880 and 372/396 values), and a coordinate axis with a hole in it is
    # the fill-value defect at the place it would be least visible.
    for name in ("time", "latitude", "longitude", "nv"):
        array = entries.get(f"{name}/.zarray")
        if array is None:
            continue
        counts = [
            (int(size) + int(chunk) - 1) // int(chunk)
            for size, chunk in zip(array["shape"], array["chunks"], strict=True)
        ]
        for flat in range(int(np.prod(counts))):
            index = np.unravel_index(flat, counts)
            key = f"{name}/" + ".".join(str(int(value)) for value in index)
            payload = _ensure(destination, key)
            digest.update(payload)
            fetched += 1
            total += len(payload)

    for it in time_chunks:
        for ilat in lat_chunks:
            for ilon in lon_chunks:
                payload = _ensure(destination, f"{VARIABLE}/{it}.{ilat}.{ilon}")
                digest.update(payload)
                fetched += 1
                total += len(payload)
        if it % 48 == 0:
            print(f"  ... {it + 1}/{len(time_chunks)} time chunks", flush=True)

    return {
        "variable_shape": [n_time, n_lat, n_lon],
        "variable_chunks": [chunk_t, chunk_lat, chunk_lon],
        "lat_chunks": list(lat_chunks),
        "lon_chunks": list(lon_chunks),
        "keys_fetched": fetched,
        "bytes_fetched": total,
        "fetched_sha256": digest.hexdigest(),
    }


def cut(
    mirror_path: Path, store_path: Path, *, box: Box, stride: int
) -> dict[str, Any]:
    """Cut the box out of the mirror and write a store where every point is real.

    **THE STRIDE IS A SAMPLING CHOICE AND IT IS RECORDED AS ONE.** Cold fits are
    independent per series, so decimating changes which points are measured and
    not how hard any of them is -- but the point set is the population every
    reported rate is a rate over.

    Args:
        mirror_path: The partial mirror.
        store_path: Where to write the clean store.
        box: The resolved box.
        stride: Take every `stride`-th point on each spatial axis.

    Returns:
        The store's own description: grid, record length, missing fraction.
    """
    source = xr.open_zarr(
        mirror_path, chunks=None, decode_times=True, consolidated=True
    )
    cut_out = source[list(KEEP)].isel(
        latitude=slice(box.i0, box.i1, stride),
        longitude=slice(box.j0, box.j1, stride),
    )
    # DROP EVERY COORDINATE THE VARIABLE DOES NOT USE. `geometry_components`
    # iterates the VARIABLE's dims, so a stray `nv` would not reach the
    # fingerprint -- but it would reach the store, and a store carrying an axis
    # nothing fits invites the next reader to ask what fits it.
    cut_out = cut_out.drop_vars(
        [name for name in cut_out.coords if name not in cut_out[VARIABLE].dims]
    )
    cut_out = cut_out.load()

    # STRIP THE INHERITED ENCODING BEFORE WRITING, AND THAT IS NOT A TIDY-UP.
    # The source is zarr v2 and carries a numcodecs Blosc compressor on every
    # array; `to_zarr` at v3 re-uses it and refuses it as "not a BytesBytesCodec".
    # Leaving it would also mean the local store's codec was chosen by the
    # product rather than by us, which is a conversion parameter arriving
    # silently -- so it is cleared and the chunking below is the only encoding
    # this store has.
    for name in (*cut_out.data_vars, *cut_out.coords):
        cut_out[name].encoding.clear()

    # FLOAT32 ON DISK, WHICH IS THE PROJECT'S INPUT CONVENTION AND NOT A
    # ROUNDING. `bench.fields.build_field` writes `float32` and section 9.4's
    # per-series arithmetic charges a float32 source cast into a float64
    # destination per chunk-aligned span. The product stores int32 with a 1e-4
    # scale factor, so xarray decodes to float64 and a store written that way
    # would double the data term against every figure the tiling is sized by --
    # a fixture difference wearing the name of a dtype.
    cut_out[VARIABLE] = cut_out[VARIABLE].astype("float32")

    values = np.asarray(cut_out[VARIABLE].values)
    n_time = int(values.shape[0])
    finite = np.isfinite(values)

    if store_path.exists():
        shutil.rmtree(store_path)
    # RECHUNKED ALONG TIME ONLY, which is section 11.1's requirement and the
    # shape `assemble_tile` reads: one chunk holds every timestep of a spatial
    # block, so a tile is a whole-series read.
    encoding = {VARIABLE: {"chunks": (n_time, values.shape[1], values.shape[2])}}
    cut_out.to_zarr(store_path, encoding=encoding, consolidated=True)

    latitude = np.asarray(cut_out["latitude"].values, dtype=float)
    longitude = np.asarray(cut_out["longitude"].values, dtype=float)
    return {
        "n_time": n_time,
        "n_latitude": int(values.shape[1]),
        "n_longitude": int(values.shape[2]),
        "points": int(values.shape[1] * values.shape[2]),
        "stride": stride,
        # THE NAMES AS THE PRODUCT SHIPS THEM, and each axis's direction. A
        # decreasing latitude axis is open question 20's first candidate and it
        # yields a plausible answer rather than an error, so the direction is
        # recorded whether or not this product exercises it.
        "dims": [str(dim) for dim in cut_out[VARIABLE].dims],
        "latitude_increasing": bool(np.all(np.diff(latitude) > 0)),
        "longitude_increasing": bool(np.all(np.diff(longitude) > 0)),
        "latitude_range": [float(latitude[0]), float(latitude[-1])],
        "longitude_range": [float(longitude[0]), float(longitude[-1])],
        "time_first": str(cut_out["time"].values[0]),
        "time_last": str(cut_out["time"].values[-1]),
        "dtype": str(values.dtype),
        # (a2b) AT A COUNT: a series that is wholly missing is a point the
        # optimizer never reaches, and "384 points" and "384 OCEAN points" print
        # the same way. Both are reported.
        "series_all_missing": int((~finite).all(axis=0).sum()),
        "series_any_missing": int((~finite).any(axis=0).sum()),
        "missing_fraction": float((~finite).mean()),
    }


def main(argv: list[str] | None = None) -> int:
    """Fetch, cut, and write the provenance record.

    Args:
        argv: Arguments, defaulting to `sys.argv[1:]`.

    Returns:
        Process exit status.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path, help="directory for the mirror and store")
    parser.add_argument("--lat0", type=float, default=20.0)
    parser.add_argument("--lat1", type=float, default=35.0)
    parser.add_argument("--lon0", type=float, default=-40.0)
    parser.add_argument("--lon1", type=float, default=-20.0)
    parser.add_argument("--stride", type=int, default=8)
    arguments = parser.parse_args(argv)

    out: Path = arguments.out
    out.mkdir(parents=True, exist_ok=True)

    print(f"reading {STORE}/.zmetadata", flush=True)
    metadata = json.loads(_get(f"{STORE}/.zmetadata"))

    # THE COORDINATE ARRAYS COME FIRST AND FROM THE STORE, so the box is
    # resolved against the grid rather than against the documented step.
    probe = out / "axes"
    probe.mkdir(parents=True, exist_ok=True)
    for key, value in metadata["metadata"].items():
        target = probe / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(value))
    (probe / ".zmetadata").write_text(json.dumps(metadata))
    for name in ("latitude", "longitude", "time"):
        (probe / f"{name}/0").write_bytes(_get(f"{STORE}/{name}/0"))
    axes = xr.open_zarr(probe, chunks=None, decode_times=False, consolidated=True)
    latitude = np.asarray(axes["latitude"].values, dtype=float)
    longitude = np.asarray(axes["longitude"].values, dtype=float)

    box = resolve_box(
        latitude,
        longitude,
        lat0=arguments.lat0,
        lat1=arguments.lat1,
        lon0=arguments.lon0,
        lon1=arguments.lon1,
    )
    print(f"box: lat[{box.i0}:{box.i1}] lon[{box.j0}:{box.j1}]", flush=True)

    mirror_path = out / "mirror.zarr"
    fetched = mirror(mirror_path, box=box, metadata=metadata)
    print(
        f"fetched {fetched['keys_fetched']} keys, "
        f"{fetched['bytes_fetched'] / 1e6:.1f} MB",
        flush=True,
    )

    store_path = out / "duacs-monthly.zarr"
    described = cut(mirror_path, store_path, box=box, stride=arguments.stride)

    record = {
        "record": "realdata_spike_fetch",
        "stac_item": STAC_ITEM,
        "store_url": STORE,
        "variable": VARIABLE,
        "kept_arrays": list(KEEP),
        "dropped_arrays": ["lat_bnds", "lon_bnds", "climatology_bnds", "nv"],
        "box": asdict(box),
        "source": fetched,
        "store": described,
        "store_path": str(store_path),
    }
    (out / "fetch-provenance.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(described, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
