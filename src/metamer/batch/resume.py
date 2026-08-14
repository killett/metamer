"""The resume gate: whether a store's fits may be reused, and what refuses.

**THE REACHABLE OUTCOMES ARE PROCEED AND REFUSE. THERE IS NO RECOMPUTE ARM
HERE, AND ITS ABSENCE IS MEASURED RATHER THAN CHOSEN.**
`hashing.COMPAT_RELEVANT_FIELDS` is `FIT_RELEVANT_FIELDS | {"criteria"}` -- the
two allowlists differ by exactly one field -- so *"`fit_hash` matches and
`compat_hash` differs"* **is** "the criterion set changed", and design doc 12.8
refuses that in place because growing `c` is a whole-store rewrite with no
completion bitmap of its own. Every input that could reach the recompute arm is
consumed by the row above it. **Recomputing derived arrays from stored
primitives is Task 12's `--reuse-fits-from`, which writes a NEW store**, and
that is where the three-hash split is cashed.

A compat difference that is *not* the criterion set is therefore unreachable
today and is **refused explicitly rather than fallen through** -- the regime
declared without the feature. A later field that changes derived arrays without
moving `theta-hat` makes it reachable, and the task that adds one implements
the arm.

**THE TWO COMPARISONS NO HASH COVERS ARE THE ONES THAT MATTER MOST.**

- **`candidates`** is in neither allowlist, deliberately, because 12.8 permits
  extension and a hash can only express equality. The comparison is
  **positional**: `stored[i] == requested[i]` for every `i < len(stored)`. A
  set or sorted comparison accepts a **permutation**, which is precisely the
  case that writes each candidate's fits into the other's slice of the model
  axis -- every array the right shape, every value finite, every status `ok`,
  and at unequal `p` every ragged offset shifted as well.
- **The `/detail/` selection** is in no hash either, and is **neither
  fit-relevant nor recomputable**: a covariance derives from the Hessian at the
  optimum, which is not stored. Until Task 11 the store did not record it at
  all, so the refusal 12.8 specifies had nothing to compare against -- a name
  rather than a gate. `store.SCHEMA_VERSION` is 3 because of it.

**AND `len(requested) >= len(stored)` IS NECESSARY AND NOT SUFFICIENT.** A
strict superset resizes the `m` and `p` axes, which is the same whole-store
rewrite the criterion set is refused for -- **and the completion bitmap has no
model axis**, so there is no state in which a tile is complete for candidates
0..M-1 and outstanding for M. The extension stays legal at the hash boundary,
which is what keeps it available to a new store and to section 11.1's
`(fit_hash, candidate spec_hash)` warm-start key; it is refused **in place**.

**ORDERING INSIDE THE GATE: IDENTITY FIRST, THEN THE UNHASHED AXES, THEN
GEOMETRY.** A store whose fits are unusable should say so before it says
anything about candidate lists or tile sizes, and the fields no hash covers are
checked before the ones a hash already summarizes so that the message names the
field rather than a digest.

Every refusal names **what differs and what resolves it**, which is the same
discipline as staged validation naming its layer: a refusal that says only
"the configuration changed" leaves the user to find which field, and a refusal
with no resolution is a wall rather than planning information.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

import zarr

from metamer.batch.store import SCHEMA_VERSION
from metamer.batch.validation import ValidationError, ValidationLayer

if TYPE_CHECKING:  # pragma: no cover - typing only
    from metamer.config.model import Config


def _refuse(message: str) -> ValidationError:
    """Build a layer-3 refusal.

    Exit code 3 is design doc 14.3's *"config/validation error -- resuming will
    not help"*, which is true of every refusal here: each one is a difference
    between the request and a store that already exists, and none of them is
    fixed by running again.

    Args:
        message: What differs and what resolves it.

    Returns:
        The error to raise.
    """
    return ValidationError(ValidationLayer.SEMANTIC, message)


def _sequence(attrs: Mapping[str, Any], key: str) -> list[str]:
    """Read a stored list of strings.

    **The JSON boundary is where `tuple` stops equalling `list`.**
    `Config.criteria` and `candidate_spec_hashes()` are tuples and come back out
    of zarr's attrs as lists, so both sides are normalized here rather than at
    each comparison -- a comparison that missed it would refuse every resume,
    including the correct one.

    Args:
        attrs: Root attrs.
        key: Which entry.

    Returns:
        The stored values.

    Raises:
        ValidationError: Layer 3, if the entry is absent or not a list.
    """
    value = attrs.get(key)
    if not isinstance(value, Sequence) or isinstance(value, str):
        raise _refuse(
            f"the store records no {key}, so a resume cannot establish what it "
            "was built to answer; write a new store"
        )
    return [str(item) for item in value]


def _check_candidates(attrs: Mapping[str, Any], config: Config) -> None:
    """Compare candidate spec hashes positionally.

    Args:
        attrs: Root attrs.
        config: The requested configuration.

    Raises:
        ValidationError: Layer 3, on a prefix mismatch or a strict superset.
    """
    stored = _sequence(attrs, "candidate_spec_hashes")
    requested = list(config.candidate_spec_hashes())

    for index, (was, now) in enumerate(zip(stored, requested, strict=False)):
        if was != now:
            raise _refuse(
                f"candidate {index} differs: the store holds {was} and this "
                f"configuration asks for {now}. The model axis is positional, "
                "so resuming would write this candidate's fits into the stored "
                f"candidate's slice -- and at unequal parameter counts it would "
                "shift every offset on the ragged /noise/ axis as well. Restore "
                f"the candidate at index {index}, or write a new store"
            )

    if len(requested) < len(stored):
        raise _refuse(
            f"the store holds {len(stored)} candidates and this configuration "
            f"asks for {len(requested)}. Dropping a candidate resizes the model "
            "axis, which is fixed at store creation; write a new store"
        )
    if len(requested) > len(stored):
        raise _refuse(
            f"this configuration adds {len(requested) - len(stored)} candidate(s) "
            f"to the {len(stored)} the store holds. Extension is legal -- the "
            "candidate set is in no hash for exactly that reason -- but not in "
            "place: it resizes the m and p axes, and the completion bitmap has "
            "no model axis, so a tile cannot be complete for the stored "
            "candidates and outstanding for the new one. Write a new store"
        )


def check_resume(store_path: Path | str, config: Config, *, geometry_hash: str) -> None:
    """Refuse a resume the existing store cannot serve.

    Args:
        store_path: An existing store.
        config: The requested configuration, past stage 4a.
        geometry_hash: This run's geometry rollup, from the opened input.

    Raises:
        ValidationError: Layer 3, naming what differs and what resolves it, for
            a schema-version difference, a `fit_hash` difference, a candidate
            prefix mismatch, a candidate-list length change, a criterion-set
            change, a `/detail/` change, or a `compat_hash` difference that is
            none of the above.
    """
    attrs = dict(zarr.open_group(str(store_path), mode="r").attrs)

    stored_schema = attrs.get("schema_version")
    if stored_schema != SCHEMA_VERSION:
        raise _refuse(
            f"the store at {store_path} declares schema version "
            f"{stored_schema} and this release writes {SCHEMA_VERSION}. Stored "
            "code meanings, fill values and provenance keys are fixed at "
            "creation, so its arrays cannot be read with this vocabulary; write "
            "a new store"
        )

    # THIS REFUSAL IS ALSO THE UPSTREAM HALF OF A DOUBLE GUARD, and the pair is
    # cross-commented so a later simplification sees both. `geometry_hash`
    # carries the grid and is fit-relevant, so a changed grid is refused here by
    # name -- which makes `completion.resume_tile_side`'s bitmap-shape refusal
    # unreachable through a configuration, and leaves it covering the case this
    # one cannot see: a store whose bitmap does not describe its own grid.
    requested_fit = config.fit_hash(geometry_hash)
    stored_fit = attrs.get("fit_hash")
    if stored_fit != requested_fit:
        raise _refuse(
            f"the store's fit_hash is {stored_fit} and this configuration and "
            f"input give {requested_fit}. The stored fits were produced under a "
            "different likelihood, signal, input geometry or algorithm version "
            "and are not reusable: restore the configuration that made them, or "
            "write a new store"
        )

    _check_candidates(attrs, config)

    stored_criteria = _sequence(attrs, "criteria")
    if stored_criteria != list(config.criteria):
        raise _refuse(
            f"the store ranks by {stored_criteria} and this configuration asks "
            f"for {list(config.criteria)}. That resizes the c axis, which is a "
            "whole-store rewrite with no completion bitmap of its own -- an "
            "interruption mid-resize would leave a store that is neither shape. "
            "Recompute the derived arrays into a new store, or rerun"
        )

    stored_detail = attrs.get("detail")
    requested_detail = config.detail.model_dump()
    if stored_detail != requested_detail:
        raise _refuse(
            f"the store's /detail/ selection is {stored_detail} and this "
            f"configuration asks for {requested_detail}. It is fixed at store "
            "creation: it moves nothing about the fits, and it cannot be "
            "recomputed either, because a parameter covariance derives from the "
            "Hessian at the optimum and the Hessian is not stored. Restore the "
            "selection, or write a new store"
        )

    requested_compat = config.compat_hash(geometry_hash)
    if attrs.get("compat_hash") != requested_compat:
        # UNREACHABLE THROUGH A CONFIG IN THIS RELEASE, and refused rather than
        # ignored: the two allowlists differ by `criteria` alone, which the
        # comparison above already settled. A later compat-relevant field would
        # land here, and falling through would resume against derived arrays
        # computed under a policy the configuration no longer requests.
        raise _refuse(
            f"the store's compat_hash is {attrs.get('compat_hash')} and this "
            f"configuration gives {requested_compat}, while its fit_hash and "
            "criterion set both match. No field in this release can produce "
            "that, so the store was written by a different one; write a new "
            "store"
        )
