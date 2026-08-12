"""`geometry_hash`: what the input's GEOMETRY is, read from the input.

**NAMED FOR WHAT IT COVERS.** It identifies the grid, the axes and the storage
type -- not the values. A value edit at fixed geometry does **not** move it, and
`tests/test_geometry.py` asserts exactly that, because **a test is the only
documentation this project has evidence for**: a docstring saying "this does not
cover value edits" does not constrain the next author, and a passing test that
fails when the limit is removed does.

Hashing the payload itself is not an option: about 25 GB at 10^7 x 630 float32,
read once per resume, to answer a question a resume asks before it has budget to
read anything.

**WHY IT EXISTS: `data_uri` WAS WRONG IN BOTH DIRECTIONS AT ONCE**, which is not
a conservative approximation of the right gate -- it is unrelated to it. Moving a
file invalidated a resume that is scientifically valid; editing a file in place
at a fixed URI permitted a resume that is scientifically invalid. This is the
first actual implementation of the check.

**IT IS AN IDENTITY FIELD, AND THE POINT IS WHERE IT COMES FROM.** Every
component below is read from the opened dataset. `data_uri` -- the value it
replaces -- was supplied by the config, i.e. an identity self-reported by the
thing it was supposed to identify. It was the last such field in either
allowlist.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from metamer.batch.input import InputContractError, InputHandle
from metamer.batch.timeaxis import calendar_of, to_decimal_years
from metamer.core.hashing import canonical_json

COMPONENT_ORDER: tuple[str, ...] = (
    "shape",
    "dims",
    "variable",
    "source_dtype",
    "calendar",
    "time_coordinate",
    "spatial_coordinates",
)
"""The components, in the order a mismatch reports them.

**Cheapest and most diagnostic first.** A shape difference explains a coordinate
difference, so reporting the coordinate would bury the cause; and "your grid is
1440x720, the store's is 720x360" is a sentence a user can act on where "your
hash changed" is not.
"""


def _values(array: object) -> list[Any]:
    """Render a coordinate array as JSON-safe Python scalars.

    **`.tolist()`, NOT `list()`, AND THE DIFFERENCE IS NOT COSMETIC.**
    `canonical_json` refuses `np.ndarray` and `np.int64` and ACCEPTS
    `np.float64`, because that one subclasses `float`. So `list(array)` works on
    a float coordinate and raises on an integer one -- and `y`/`x` index
    coordinates are routinely integers. A fingerprint built that way passes
    every test written against a float grid and fails on the first real store.
    `.tolist()` converts to Python scalars uniformly.

    Args:
        array: A coordinate array.

    Returns:
        Plain Python scalars.
    """
    return np.asarray(array).tolist()  # type: ignore[no-any-return]


def geometry_components(
    handle: InputHandle, variables: Sequence[str] | None = None
) -> dict[str, Any]:
    """Read the geometry components of an opened input.

    **EVERY INPUT ARRAY THE CONFIG NAMES, NOT ONLY THE PRIMARY VARIABLE.** A
    per-point regressor field is a second data source with its own grid, and a
    GIA field silently regridded under a fixed URI is the same hole one level
    out. Per-point regressors are refused in 2a, so `variables` has one entry
    today -- but the component is a mapping keyed by variable, so adding the
    second is data rather than a shape change.

    **THE COORDINATE VALUE ARRAYS IN FULL, NOT A SUMMARY.** Min, max and length
    collapse an extent-preserving regrid -- the same first and last cell centre
    with different spacing between them -- which is the commonest real geometry
    change there is. The arrays are 1-D per axis, so a 3600 x 7200 grid
    contributes 10 800 numbers and not 2.6e7; the cost objection applies to
    curvilinear 2-D coordinates, which the stage-4a contract does not admit.

    **THE TIME COORDINATE IS HASHED AS DECIMAL YEARS**, i.e. after the
    conversion, which is what makes the DECODED calendar part of the
    fingerprint: `noleap` and `proleptic_gregorian` produce different numbers for
    the same raw value. Hashing the raw values plus a `calendar` attrs STRING
    would instead inherit xarray's and cftime's parsing behaviour, so a
    dependency upgrade that changed how an unusual spelling decodes would
    silently invalidate every store.

    The calendar name is carried separately **as well**, and that redundancy is
    deliberate: the decimal years make it *count*, and the name makes a mismatch
    *sayable*. Without the name, a calendar change reports as "time coordinate
    differs", which is true and useless.

    Args:
        handle: An opened input, already past the stage-4a contract.
        variables: Names of every input array to cover. Defaults to the
            handle's own variable.

    Returns:
        The components, ready for `geometry_hash` and for root attrs.

    Raises:
        InputContractError: If a named variable is absent.
    """
    dataset = handle.dataset
    names = tuple(variables) if variables is not None else (handle.variable,)

    arrays: dict[str, dict[str, Any]] = {}
    for name in sorted(names):
        if name not in dataset.variables:
            raise InputContractError(
                f"{handle.uri!r} has no variable {name!r} to fingerprint"
            )
        array = dataset[name]
        arrays[name] = {
            "dims": list(array.dims),
            "shape": list(int(size) for size in array.shape),
            "source_dtype": str(array.dtype),
        }

    time = dataset["time"]
    spatial = {
        str(dim): _values(dataset[dim].values)
        for dim in dataset[names[0]].dims
        if dim != "time" and dim in dataset.coords
    }

    return {
        "variable": sorted(names),
        "arrays": arrays,
        "calendar": calendar_of(time.values),
        "time_coordinate": _values(to_decimal_years(time.values)),
        "spatial_coordinates": spatial,
    }


def geometry_hash(components: Mapping[str, Any]) -> str:
    """Digest the components through the canonical serializer.

    **THROUGH `canonical_json`, WHICH IS THE (k) HALF OF THIS.** Float formatting
    must be canonical or the fingerprint is platform- and process-dependent, and
    a fingerprint that drifts between runs invalidates a 10^7-point store on
    every resume with no symptom but a bill. It also refuses what JSON cannot
    represent exactly, so a NaN in a coordinate array is a loud error rather than
    a non-standard token that no conforming reader accepts.

    The construction is `hashing._digest`'s, deliberately: same serializer, same
    digest, same truncation, so the three config hashes and this one cannot drift
    apart in their notion of canonical.

    Args:
        components: The mapping from `geometry_components`.

    Returns:
        A 16-hex-digit digest.

    Raises:
        TypeError: If a component is not JSON-representable.
        ValueError: If a coordinate carries a non-finite value.
    """
    return hashlib.sha256(canonical_json(components).encode("utf-8")).hexdigest()[:16]


def describe_mismatch(
    stored: Mapping[str, Any], requested: Mapping[str, Any]
) -> str | None:
    """Name which component differs, or None if none does.

    **"YOUR DATA CHANGED, HERE IS HOW" IS ACTIONABLE AND "YOUR HASH CHANGED" IS
    NOT.** Same reasoning as staged validation naming its layer. This is also
    why the components go into root attrs beside the rollup: on the resume side
    the store is the only thing available, so a message naming the difference is
    implementable **only** if the store carries the parts.

    Args:
        stored: Components recorded in the store's root attrs.
        requested: Components read from the input this run opened.

    Returns:
        A sentence naming the first differing component, or None.
    """
    for component in COMPONENT_ORDER:
        if component == "shape" or component == "dims" or component == "source_dtype":
            for name in sorted(
                set(stored.get("arrays", {})) | set(requested.get("arrays", {}))
            ):
                was = stored.get("arrays", {}).get(name, {}).get(component)
                now = requested.get("arrays", {}).get(name, {}).get(component)
                if was != now:
                    return (
                        f"{component} of variable {name!r} differs: the store was "
                        f"written with {was!r} and this run's input has {now!r}"
                    )
            continue
        was = stored.get(component)
        now = requested.get(component)
        if was == now:
            continue
        if component in ("time_coordinate", "spatial_coordinates"):
            return (
                f"the {component.replace('_', ' ')} differs from the one the "
                "store was written with. The values are compared in full, so "
                "this includes a regrid that preserves the extent"
            )
        return (
            f"{component} differs: the store was written with {was!r} and this "
            f"run's input has {now!r}"
        )
    return None
