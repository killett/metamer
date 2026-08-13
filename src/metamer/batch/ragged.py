"""The ragged index: offsets, extents, and the `/noise/` coordinate columns.

**THIS BUILDER PRECEDES THE STORE SCHEMA AND NEEDS NOTHING FROM IT.** `P_total`
and the offset table are what store creation sizes the ragged axis with, so a
schema task that ran first would have to stub them -- and a stubbed offset table
written into a store survives, because every array still has a shape and every
value is still finite.

**IT IS GENERIC OVER A PER-MODEL EXTENT FUNCTION, NOT A PARAMETER COUNT.**
`/noise/` stores `p_m` values per model; a `/detail/` covariance block stores
`p_m(p_m+1)/2`. Same builder, different callable. The extent function has **no
default**, so every call site names which axis it is building.

**THE PRESCRIBED M=2 FIXTURE CANNOT TELL THE TWO TABLES APART, AND THE THREE
DOCUMENTS THAT PRESCRIBE IT GET ITS NUMBER WRONG (measured 2026-08-12).**
Design doc 12.3, the 2a plan and `PROGRESS.md` prescribe `white` (p=1) beside
`white + matern12` (p=3) as the fixture that separates the extent functions, and
illustrate it as `4 + 6 = 10`. Two things are wrong with that:

- **Both offset tables are `(0, 1)`.** `off_0` is 0 under every extent function
  and `off_1` is the first model's extent, and **`p = 1` and `p = 0` are the
  fixed points of `p -> p(p+1)/2`**. A reused table is invisible to this
  fixture's offsets and shows only in `extents` and `total`. The tests put a
  model with `p = 2` first.
- **The covariance total is `1 + 6 = 7`.** `10` is `P_total(P_total+1)/2` -- the
  triangle of the *flattened* total -- which is the one-table-reused error the
  same paragraph warns against. Corrected in all three documents.

**THE COLUMN ORDER IS `free_param_index`'s AND IS NEVER RE-DERIVED.** The slots
of a model's `/noise/` block are the entries of the vector the optimizer
searches, in that vector's order, so the columns must come from the one function
that defines it. A second nested loop agrees today and diverges the moment a
parameter is fixed or a canonical sort changes, and the symptom is that every
stored `theta` is labelled with another parameter's name -- shapes intact, values
finite, nothing raised. `ProcessSpec.n_theta()` is a deliberately independent
derivation of the same count (see its docstring), so the two are **asserted to
agree per model** rather than collapsed into one.

**FIVE COLUMNS, NOT THE DESIGN DOC'S FOUR — `term` IS SPLIT OUT.** Measured:
`white + matern12` has free parameters `matern12[0].sigma`, `matern12[0].rho`,
`white[0].sigma`, so **two slots in one model's block are named `sigma`** and a
reader selecting on `name` alone cannot tell the measurement noise from the
correlated component. Each column stays atomic and `(model, term, name)` is
unique.

**`model` IS THE SPEC'S CANONICAL LABEL, NOT THE CONFIG STRING.** The config
string is a REQUEST (what was asked for); the column is an IDENTITY (what the
model is), and it must be read from the thing it identifies. They differ in
order on 2a's own fixture: `"white + matern12"` against
`"matern12[0] + white[0]"`.

**THE COLUMNS ARE PLAIN STRINGS, AND §12.4's FIXED-WIDTH BYTES WERE MEASURED TO
BE THE UNSTABLE OPTION (2026-08-12, zarr 3.3.0 / xarray 2026.7.0).** §12.4 chose
`S32` over variable-length strings because zarr v3's string support was judged
the least stable corner of the stack. It is the other way round:

| dtype | `zarr.json` `data_type` | on creation |
|---|---|---|
| `S32` | `null_terminated_bytes` | **`UnstableSpecificationWarning` — no Zarr V3 specification, may be unreadable by other Zarr libraries, may change without warning** |
| `str` | `string` | no warning |

Both round-trip through `xr.open_zarr` today, but the writing library declares
the fixed-width one unstable **on disk**, and §12.4's whole concern is metadata
durability in an archive meant to outlive the version that wrote it. So the
store writes the v3-specified `string` dtype and §12.4's integer-code legend
stays as the redundancy — **only the dtype moved.** Fixed-width encoding, its
silent truncation and its ASCII refusal went with it: those guards existed for
a dtype nothing uses, and a refusal whose reason has evaporated reads as a
constraint the format imposes.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from metamer.core.terms import ProcessSpec, free_param_index

#: How a `/detail/` covariance block is packed. **This is the group's
#: plausible-number failure**: a consumer that unpacks row-major-lower as
#: column-major-lower gets a matrix that is still symmetric, often still positive
#: definite, and reports wrong correlations with no symptom. The string is a
#: label; `covariance_slot_pairs` is what produces the order, so the declaration
#: is a gate rather than a name.
COVARIANCE_STORAGE_ORDER = "row-major-lower"

#: A per-model extent: how many slots of a ragged axis this model occupies.
ExtentFn = Callable[[ProcessSpec], int]

_COLUMNS = ("model", "term", "name", "unit", "transform")


def model_label(spec: ProcessSpec) -> str:
    """Return a candidate's canonical label, as the store's model axis carries it.

    **AN IDENTITY, NOT THE CONFIG STRING.** The config's `"white + matern12"` is
    a request; this is what the model *is*, read off the canonically ordered
    spec, and the two differ in order on exactly that candidate. One definition,
    used by the `/noise/` columns and by every group's `m` coordinate, so the two
    cannot disagree.

    Args:
        spec: One candidate's process specification.

    Returns:
        Its term labels joined with `" + "`, in canonical order.
    """
    return " + ".join(spec.labels())


def noise_extent(spec: ProcessSpec) -> int:
    """Return `p_m`, the `/noise/` extent: one slot per free noise parameter.

    Args:
        spec: One candidate's process specification.

    Returns:
        The number of free parameters the candidate declares.

    Raises:
        NotImplementedError: If the spec declares cross-term shared parameters.
            Propagated from `ProcessSpec.n_theta`; unreachable today because no
            family declares sharing and the config path cannot express it.
    """
    return spec.n_theta()


def covariance_extent(spec: ProcessSpec) -> int:
    """Return `p_m(p_m+1)/2`, the packed-lower-triangle extent for `/detail/`.

    `/detail/` is not created in Phase 2a. The extent function ships now because
    a builder exercised with one extent function is a builder that looks correct
    at equal `p` and is wrong at unequal `p`.

    Args:
        spec: One candidate's process specification.

    Returns:
        The number of stored values in this model's packed covariance block.

    Raises:
        NotImplementedError: See `noise_extent`.
    """
    p = spec.n_theta()
    return p * (p + 1) // 2


def covariance_slot_pairs(p: int) -> tuple[tuple[int, int], ...]:
    """Enumerate the `(row, column)` pairs of a packed block, in storage order.

    This is what makes `COVARIANCE_STORAGE_ORDER` a declaration with a producer
    rather than a string in attrs. It is also the independent oracle for
    `covariance_extent`: it counts by walking the pairs, which shares no
    derivation with `p(p+1)/2`.

    Args:
        p: Number of free parameters in the model.

    Returns:
        The lower-triangle index pairs, row-major, diagonal included.
    """
    return tuple((i, j) for i in range(p) for j in range(i + 1))


@dataclass(frozen=True)
class RaggedIndex:
    """One ragged axis: where each model's block starts and how long it is.

    Attributes:
        extents: Slots occupied by each model, in candidate order.
        offsets: Start of each model's block. `offsets[m]` is the sum of the
            extents before `m`; **it is stored as a coordinate array and never
            re-derived at read time**, so a reader without metamer can slice a
            block without knowing which extent function produced it.
        total: Length of the ragged axis.
    """

    extents: tuple[int, ...]
    offsets: tuple[int, ...]
    total: int

    def block(self, model: int) -> slice:
        """Return the slice of the ragged axis belonging to one model.

        Args:
            model: Index into the candidate list.

        Returns:
            `slice(off_m, off_m + p_m)`.
        """
        start = self.offsets[model]
        return slice(start, start + self.extents[model])

    def offsets_array(self) -> NDArray[np.int32]:
        """Return the offset table as the coordinate array a store holds."""
        return np.asarray(self.offsets, dtype=np.int32)

    def extents_array(self) -> NDArray[np.int32]:
        """Return the extent table as the coordinate array a store holds."""
        return np.asarray(self.extents, dtype=np.int32)

    def model_index_array(self) -> NDArray[np.int16]:
        """Return the owning model index for every slot of the ragged axis."""
        out = np.empty(self.total, dtype=np.int16)
        for model in range(len(self.extents)):
            out[self.block(model)] = model
        return out


def build_ragged_index(specs: Sequence[ProcessSpec], extent: ExtentFn) -> RaggedIndex:
    """Build the offset table for one ragged axis over the candidate list.

    Pure arithmetic over the candidates: it opens no store and reads no data,
    which is why it precedes store creation rather than following it.

    Args:
        specs: Candidates in config order. Order is positional throughout the
            store -- Task 11's resume gate compares `stored[i] == requested[i]`
            -- so this order is the model axis.
        extent: Per-model slot count. `noise_extent` for `/noise/`,
            `covariance_extent` for `/detail/`. **Required, deliberately**: a
            default would silently build the `/noise/` table for a call site
            that meant the other one.

    Returns:
        The offsets, extents and total for this axis.

    Raises:
        ValueError: If `specs` is empty, or if `extent` returns a non-integer or
            a negative value.
        NotImplementedError: Propagated from a spec declaring shared parameters.
    """
    if not specs:
        raise ValueError(
            "a ragged index needs at least one candidate; a store with no models "
            "has an axis of length zero, and every assertion that compares along "
            "the model axis passes vacuously against it"
        )

    extents: list[int] = []
    offsets: list[int] = []
    running = 0
    for model, spec in enumerate(specs):
        value = extent(spec)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(
                f"extent function returned {value!r} of type "
                f"{type(value).__name__} for model {model}; an integer is "
                "required, and a whole-valued float propagates into the offset "
                "table and the coordinate dtype"
            )
        if value < 0:
            raise ValueError(
                f"extent function returned a negative extent {value} for model "
                f"{model}; the running sum stays consistent and every block "
                "after it addresses the wrong part of the axis"
            )
        offsets.append(running)
        extents.append(value)
        running += value

    return RaggedIndex(extents=tuple(extents), offsets=tuple(offsets), total=running)


@dataclass(frozen=True)
class NoiseParamCoordinates:
    """The `/noise/` coordinate columns, one entry per slot of the ragged axis.

    Attributes:
        index: The `/noise/` ragged index these columns describe.
        model_index: Owning model, as the integer join key to the `m` axis.
        model: Owning model's canonical label.
        term: Owning term's label within the model. Split out
            from `name` because a composition can carry two parameters with the
            same name -- `white + matern12` has two called `sigma`.
        name: Parameter name within its term.
        unit: Unit string from the `ParamSpec`, empty where none is declared.
        transform: Name of the bijector mapping this parameter between natural
            units (what `/noise/` stores) and the unconstrained coordinates
            (what `/warmstart/` stores). Without it the two groups cannot be
            reconciled by a reader without metamer.
    """

    index: RaggedIndex
    model_index: NDArray[np.int16]
    model: tuple[str, ...]
    term: tuple[str, ...]
    name: tuple[str, ...]
    unit: tuple[str, ...]
    transform: tuple[str, ...]

    def legend(self) -> dict[str, tuple[str, ...]]:
        """Return the integer-code legend design doc 12.4 carries in attrs.

        It is derived from the columns themselves; a hardcoded vocabulary agrees
        today and omits the first value a new family introduces. **With the
        columns stored as strings this is a VOCABULARY LISTING rather than a
        decode table for anything on disk** -- it says which values occur, which
        is what a reader deciding how to interpret a column needs, and it is the
        redundancy 12.4 asks for.

        Returns:
            Column name to its distinct values, sorted. A value's position in
            the tuple is its integer code.
        """
        return {
            column: tuple(sorted(set(getattr(self, column)))) for column in _COLUMNS
        }


def noise_param_coordinates(
    specs: Sequence[ProcessSpec],
) -> NoiseParamCoordinates:
    """Build the `/noise/` ragged index and its coordinate columns.

    Args:
        specs: Candidates in config order, as `Config.process_specs()` returns.

    Returns:
        The index and the five columns, one entry per slot.

    Raises:
        ValueError: If `specs` is empty, or if a model's parameter layout and its
            free-parameter count disagree.
        NotImplementedError: Propagated from a spec declaring shared parameters.
    """
    index = build_ragged_index(specs, noise_extent)

    model_labels: list[str] = []
    terms: list[str] = []
    names: list[str] = []
    units: list[str] = []
    transforms: list[str] = []

    for model, spec in enumerate(specs):
        layout = free_param_index(spec)
        if len(layout) != index.extents[model]:
            raise ValueError(
                f"model {model}: free_param_index gives {len(layout)} parameters "
                f"and n_theta gives {index.extents[model]}; the two derivations "
                "disagree, so the columns would not describe the axis they label"
            )
        by_label = dict(zip(spec.labels(), spec.terms, strict=True))
        label = model_label(spec)
        for term_label, param_name in layout:
            param = by_label[term_label].params[param_name]
            model_labels.append(label)
            terms.append(term_label)
            names.append(param_name)
            units.append("" if param.unit is None else param.unit)
            transforms.append(type(param.transform).__name__)

    return NoiseParamCoordinates(
        index=index,
        model_index=index.model_index_array(),
        model=tuple(model_labels),
        term=tuple(terms),
        name=tuple(names),
        unit=tuple(units),
        transform=tuple(transforms),
    )
