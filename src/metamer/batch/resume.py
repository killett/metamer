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

from metamer.batch.completion import completed_tiles
from metamer.batch.input import InputContractError
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


def _sequence(attrs: Mapping[str, Any], key: str, *, subject: str) -> list[str]:
    """Read a stored list of strings.

    **The JSON boundary is where `tuple` stops equalling `list`.**
    `Config.criteria` and `candidate_spec_hashes()` are tuples and come back out
    of zarr's attrs as lists, so both sides are normalized here rather than at
    each comparison -- a comparison that missed it would refuse every resume,
    including the correct one.

    Args:
        attrs: Root attrs.
        key: Which entry.
        subject: How to name the store in a message.

    Returns:
        The stored values.

    Raises:
        ValidationError: Layer 3, if the entry is absent or not a list.
    """
    value = attrs.get(key)
    if not isinstance(value, Sequence) or isinstance(value, str):
        raise _refuse(
            f"{subject} records no {key}, so what it was built to answer cannot "
            "be established; write a new store"
        )
    return [str(item) for item in value]


def _check_candidates(
    attrs: Mapping[str, Any], config: Config, *, subject: str, resolution: str
) -> None:
    """Compare candidate spec hashes positionally.

    **THE SAME COMPARISON SERVES A RESUME AND A SOURCE STORE**, because the model
    axis is positional in both: reusing one candidate's primitives under
    another's label is the same defect whichever store the values came from.
    Only the wording differs, and it differs because a resolution that names the
    operation the user is already performing is worse than none -- "write a new
    store" is the right advice for an in-place resume and absurd for a command
    whose whole job is writing one.

    Args:
        attrs: Root attrs of the store being compared against.
        config: The requested configuration.
        subject: How to name that store in a message.
        resolution: What the user can do about a difference.

    Raises:
        ValidationError: Layer 3, on a prefix mismatch or a length change.
    """
    stored = _sequence(attrs, "candidate_spec_hashes", subject=subject)
    requested = list(config.candidate_spec_hashes())

    for index, (was, now) in enumerate(zip(stored, requested, strict=False)):
        if was != now:
            raise _refuse(
                f"candidate {index} differs: {subject} holds {was} and this "
                f"configuration asks for {now}. The model axis is positional, "
                f"so this would pair one candidate's fits with another's label "
                "-- and at unequal parameter counts it would shift every offset "
                "on the ragged /noise/ axis as well. Restore the candidate at "
                f"index {index}, or {resolution}"
            )

    if len(requested) < len(stored):
        raise _refuse(
            f"{subject} holds {len(stored)} candidates and this configuration "
            f"asks for {len(requested)}. Dropping a candidate resizes the model "
            f"axis, which is fixed at store creation; {resolution}"
        )
    if len(requested) > len(stored):
        raise _refuse(
            f"this configuration adds {len(requested) - len(stored)} candidate(s) "
            f"to the {len(stored)} {subject} holds. Extension is legal -- the "
            "candidate set is in no hash for exactly that reason -- but it needs "
            "fits that do not exist: it resizes the m and p axes, and the "
            "completion bitmap has no model axis, so a tile cannot be complete "
            f"for the stored candidates and outstanding for the new one. "
            f"{resolution[0].upper()}{resolution[1:]}"
        )


def _check_schema(attrs: Mapping[str, Any], *, subject: str) -> None:
    """Refuse a store written by another schema version.

    Args:
        attrs: Root attrs.
        subject: How to name the store in a message.

    Raises:
        ValidationError: Layer 3, if the versions differ.
    """
    stored = attrs.get("schema_version")
    if stored != SCHEMA_VERSION:
        raise _refuse(
            f"{subject} declares schema version {stored} and this release "
            f"writes {SCHEMA_VERSION}. Stored code meanings, fill values and "
            "provenance keys are fixed at creation, so its arrays cannot be "
            "read with this vocabulary; write a new store"
        )


def _check_fit_hash(
    attrs: Mapping[str, Any], config: Config, geometry_hash: str, *, subject: str
) -> None:
    """Refuse a store whose fits this configuration did not produce.

    **THIS REFUSAL IS ALSO THE UPSTREAM HALF OF A DOUBLE GUARD**, and the pair is
    cross-commented so a later simplification sees both. `geometry_hash` carries
    the grid and is fit-relevant, so a changed grid is refused here by name --
    which makes `completion.resume_tile_side`'s bitmap-shape refusal unreachable
    through a configuration, and leaves it covering the case this one cannot
    see: a store whose bitmap does not describe its own grid.

    Args:
        attrs: Root attrs.
        config: The requested configuration.
        geometry_hash: This run's geometry rollup.
        subject: How to name the store in a message.

    Raises:
        ValidationError: Layer 3, if the hashes differ.
    """
    requested = config.fit_hash(geometry_hash)
    stored = attrs.get("fit_hash")
    if stored != requested:
        raise _refuse(
            f"{subject} has fit_hash {stored} and this configuration and input "
            f"give {requested}. Its fits were produced under a different "
            "likelihood, signal, input geometry or algorithm version and are "
            "not reusable: restore the configuration that made them, or write a "
            "new store"
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
    subject = f"the store at {store_path}"
    attrs = dict(zarr.open_group(str(store_path), mode="r").attrs)

    _check_schema(attrs, subject=subject)
    _check_fit_hash(attrs, config, geometry_hash, subject=subject)
    _check_candidates(attrs, config, subject=subject, resolution="write a new store")

    stored_criteria = _sequence(attrs, "criteria", subject=subject)
    if stored_criteria != list(config.criteria):
        raise _refuse(
            f"{subject} ranks by {stored_criteria} and this configuration asks "
            f"for {list(config.criteria)}. That resizes the c axis, which is a "
            "whole-store rewrite with no completion bitmap of its own -- an "
            "interruption mid-resize would leave a store that is neither shape. "
            "Recompute the derived arrays into a new store with "
            "--reuse-fits-from, or rerun"
        )

    stored_detail = attrs.get("detail")
    requested_detail = config.detail.model_dump()
    if stored_detail != requested_detail:
        raise _refuse(
            f"{subject} has the /detail/ selection {stored_detail} and this "
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
            f"{subject} has compat_hash {attrs.get('compat_hash')} and this "
            f"configuration gives {requested_compat}, while its fit_hash and "
            "criterion set both match. No field in this release can produce "
            "that, so the store was written by a different one; write a new "
            "store"
        )


def check_source(
    source_path: Path | str, config: Config, *, geometry_hash: str
) -> None:
    """Refuse a `--reuse-fits-from` source that cannot serve the request.

    **THREE OF THE RESUME GATE'S COMPARISONS APPLY AND THREE DO NOT, AND WHICH
    IS WHICH IS THE WHOLE DESIGN OF THIS COMMAND.**

    - **`criteria` is omitted deliberately**: a criterion-set change is the
      reason to run this command, and reusing the resume gate wholesale would
      make the feature refuse its own primary use.
    - **`compat_hash` is omitted because it is `fit_hash` plus the criterion
      set**, so comparing it would refuse exactly what the omission above
      permits.
    - **The `/detail/` selection is omitted because 2a creates no `/detail/`
      group in either store**, so a new store recording a different selection
      claims nothing false. **The regime is declared for the task that creates
      the group**: a recompute cannot produce `/detail/` -- the Hessian at the
      optimum is not stored -- so once it exists, a source that lacks the
      requested selection must be refused here.

    **And the completion bitmap must be FULLY set**, which is this function's own
    check and the one that is layer 4: recomputing from a partially fitted store
    yields a complete-looking new store built on fill values.

    Args:
        source_path: The store named by `--reuse-fits-from`.
        config: The requested configuration, past stage 4a.
        geometry_hash: This run's geometry rollup, from the opened input.

    Raises:
        InputContractError: Layer 4, exit code 4, if the source does not exist
            or its completion bitmap is not fully set. **Both are facts about
            data on disk rather than about the configuration**, which is what
            puts them on the other side of the layer boundary from everything
            else here -- and `InputContractError` is not a `ValidationError`, so
            the two cannot land in one clause.
        ValidationError: Layer 3, exit code 3, for a schema-version difference,
            a `fit_hash` difference, or a candidate mismatch.
    """
    if not Path(source_path).exists():
        raise InputContractError(
            f"--reuse-fits-from names {source_path}, which does not exist. The "
            "recompute path reads its primitives from that store"
        )

    subject = f"the source store at {source_path}"
    attrs = dict(zarr.open_group(str(source_path), mode="r").attrs)

    _check_schema(attrs, subject=subject)
    _check_fit_hash(attrs, config, geometry_hash, subject=subject)
    _check_candidates(
        attrs,
        config,
        subject=subject,
        resolution="fit the requested candidates instead of reusing these",
    )

    done = completed_tiles(source_path)
    if not done.all():
        outstanding = int(done.size - done.sum())
        raise InputContractError(
            f"{subject} has {outstanding} of {done.size} tiles unset in its "
            "completion bitmap. Recomputing from a partially fitted store would "
            "produce a complete-looking new store whose primitives are fill "
            "values at those tiles -- numbers that read as failed fits and were "
            "never attempted. Finish the source run first"
        )
