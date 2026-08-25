"""The pass-1 barrier and the cross-store gate.

WHAT THIS MODULE IS FOR (design doc §11.1, decision D11).
----------------------------------------------------------
Pass 2 warm-starts from pass 1's store. Two things must hold before it may:
**pass 1 is COMPLETE**, and **the store is the one this configuration
describes**. Neither is checkable from a path, and both fail silently if
unchecked -- a partial coarse grid produces a *valid-looking* source map with
systematically distant sources, and a store built under a different
configuration produces converged fits at another optimum.

THE BARRIER IS THE EXISTING PREDICATE, AND THAT IS D11's WHOLE ARGUMENT.
-------------------------------------------------------------------------
`completion.completed_tiles(...).all()`. **No new completion concept**: the bits
are bound to the store's own `StoreShape`, which for pass 1 is the decimated
grid, so *"complete"* means exactly what it means everywhere else, about a
different grid. A second notion of completeness is the thing D11 was chosen to
avoid.

THE GATE IS ONE EQUALITY OVER THE WHOLE ALLOWLIST, NOT AN ENUMERATION.
-----------------------------------------------------------------------
**An enumerated gate is a denylist wearing an allowlist's clothes.** The plan
names three checks -- the stride, the parent geometry, the candidate set --
while `FIT_RELEVANT_FIELDS` has twelve members, and **a warm start taken from a
store fitted under a different `objective` is exactly as wrong as one taken at a
different stride.** Fields added later would default to unprotected, which is
the shape (a2e) was promoted for.

**The complete check is available because the geometry difference cancels
exactly.** Comparing the two stores' own `fit_hash` always fails -- pass 1's is
over the decimated geometry, pass 2's over the parent's -- and that difference
is the point of pass 1 rather than a mismatch. Both passes can compute
`config.fit_hash(parent_rollup)`, so pass 1 records it and the gate compares it
with pass 2's. **One comparison, every field, including the ones nobody listed.**

AND A DIGEST CANNOT NAME WHAT DIFFERS, SO THE PAYLOAD IS STORED BESIDE IT.
---------------------------------------------------------------------------
*"A refusal that says what would lift it is planning information; one that does
not is a wall."* The stored `parent_fit_payload` is diffed **key by key** to name
the first difference. **Key SETS are compared before values**, or a field in the
allowlist and absent from the payload is a comparison that silently does not
happen -- (a0)'s excluded-versus-missing register at a diff with a carve-out.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import zarr

from metamer.batch.completion import completed_tiles
from metamer.batch.resume import _check_candidates, _refuse
from metamer.config.model import Config
from metamer.core.hashing import FIT_RELEVANT_FIELDS, digest, fit_payload

#: How many outstanding tiles a refusal lists before it truncates.
#:
#: **A COUNT IS A WALL AND A LIST IS PLANNING INFORMATION**, so the indices go in
#: -- but a wholly unfitted 10^7-point grid has 156 000 of them, and a message
#: that long is unreadable, which is a wall of a different kind. The count is
#: always stated; the first few indices are what make it actionable.
OUTSTANDING_SHOWN = 8


def check_pass1_complete(pass1_path: Path | str) -> None:
    """Refuse pass 2 unless every tile of pass 1 is written.

    Args:
        pass1_path: The pass-1 store.

    Raises:
        ValidationError: Layer 3, naming the outstanding tiles and how many.

    Note:
        **A PARTIAL COARSE GRID IS THE DANGEROUS CASE, NOT AN EMPTY ONE.** An
        absent store fails loudly at open; a store missing one tile produces a
        source map that is entirely well-formed -- every index in range, every
        `valid` true -- whose sources are **systematically further away** in one
        region of the grid. Nothing downstream can see that, and the saving it
        costs looks like the mechanism underperforming.
    """
    done = completed_tiles(pass1_path)
    if bool(done.all()):
        return
    outstanding = [tuple(int(v) for v in pair) for pair in np.argwhere(~done)]
    shown = ", ".join(str(tile) for tile in outstanding[:OUTSTANDING_SHOWN])
    more = (
        ""
        if len(outstanding) <= OUTSTANDING_SHOWN
        else f", and {len(outstanding) - OUTSTANDING_SHOWN} more"
    )
    raise _refuse(
        f"pass 1 at {pass1_path} has {len(outstanding)} of {done.size} tiles "
        f"outstanding: {shown}{more}. Pass 2 warm-starts from it, and a partial "
        f"coarse grid gives a valid-looking source map whose sources are "
        f"systematically distant in the unfitted region. Resume pass 1 to "
        f"completion first"
    )


def check_pass1_store(
    pass1_path: Path | str, config: Config, *, geometry_hash: str
) -> None:
    """Refuse a pass-1 store this configuration does not describe.

    Args:
        pass1_path: The pass-1 store.
        config: The requested configuration, past stage 4a.
        geometry_hash: **This run's** geometry rollup, from the opened input --
            i.e. the PARENT's, since pass 2 runs over the undecimated grid.

    Raises:
        ValidationError: Layer 3, naming what differs and what would lift it,
            for a store that is not a pass-1 store at all, a parent-geometry
            mismatch, a stride mismatch, a candidate mismatch, or any other
            fit-identity difference.
    """
    subject = f"the pass-1 store at {pass1_path}"
    attrs = dict(zarr.open_group(str(pass1_path), mode="r").attrs)

    if "parent_geometry_hash" not in attrs or "parent_fit_hash" not in attrs:
        raise _refuse(
            f"{subject} records no parent geometry, so it was not written by a "
            f"decimated run and cannot be pass 1 for anything. Its absence is "
            f"the answer rather than a missing field: an ordinary store carries "
            f"no such key. Run pass 1 into this path first"
        )

    if str(attrs["parent_geometry_hash"]) != geometry_hash:
        raise _refuse(
            f"{subject} was decimated from an input with geometry "
            f"{attrs['parent_geometry_hash']} and this run's input is "
            f"{geometry_hash}. The two stores would then be joined by a path "
            f"and nothing else. Point this run at the input pass 1 read, or "
            f"re-run pass 1 over this one"
        )

    raw = attrs.get("parent_fit_payload")
    if not isinstance(raw, Mapping):
        raise _refuse(
            f"{subject} records a parent_fit_payload that is not a mapping, so "
            f"its fit identity cannot be read. The store is malformed; write a "
            f"new one"
        )
    stored: dict[str, Any] = dict(raw)
    requested = fit_payload(config.to_payload(geometry_hash))

    # THE KEY SETS FIRST. A field in the allowlist and absent from the stored
    # payload is a comparison that silently does not happen, which is exactly
    # "excluded" and "missing" being one observation.
    missing = sorted(FIT_RELEVANT_FIELDS - set(stored))
    if missing:
        raise _refuse(
            f"{subject} records no {missing} in its parent fit payload, so "
            f"those fields cannot be compared and the store's fit identity "
            f"cannot be established. It predates a field this build treats as "
            f"fit identity; re-run pass 1"
        )

    # **THE STRIDE GETS ITS OWN REFUSAL, BEFORE THE GENERIC DIFF, AND THE
    # REDUNDANCY IS DELIBERATE.** The key-by-key diff below would name the same
    # field; what it cannot say is what a stride mismatch DOES. Both guards
    # stay, and each names the other so a later simplification sees both.
    stride_key = "warm_start_coarse_stride"
    if stored[stride_key] != requested[stride_key]:
        raise _refuse(
            f"{subject} was built at coarse stride {stored[stride_key]} and "
            f"this run is configured for {requested[stride_key]}. Every source "
            f"index would still be in range and every warm start finite, taken "
            f"from the wrong cell -- nothing downstream can see it. Set "
            f"warm_start.coarse_stride to {stored[stride_key]}, or re-run pass "
            f"1 at {requested[stride_key]}"
        )

    # **THE CANDIDATE SET COMES FROM THE STORE'S OWN ATTR, NOT FROM THE FIT
    # PAYLOAD**, because `candidates` is in NEITHER allowlist: §12.8 permits
    # resuming with a superset and a hash can only express equality. So the
    # digest comparison below does not cover it and cannot be made to.
    #
    # **AND THE COMPARISON IS THE RESUME GATE'S, IMPORTED RATHER THAN
    # RESTATED.** It is the same rule about the same positional model axis --
    # only the resolution wording differs, which is why that is a parameter.
    # Two implementations of a positional comparison is how one of them comes
    # to accept a permutation.
    _check_candidates(
        attrs,
        config,
        subject=subject,
        resolution="restore the candidate order, or re-run pass 1",
    )

    # AND THE COMPLETE CHECK, WHICH IS WHY THE THREE ABOVE DO NOT HAVE TO BE
    # EXHAUSTIVE. Everything in FIT_RELEVANT_FIELDS is covered here, including
    # fields added after this function was written; the checks above exist to
    # NAME the common cases, not to enumerate the gate.
    if digest(stored) != str(attrs["parent_fit_hash"]):
        raise _refuse(
            f"{subject} has a parent fit payload that does not hash to its own "
            f"recorded parent_fit_hash. The store is internally inconsistent "
            f"and nothing about it can be trusted; write a new store"
        )
    if digest(stored) != digest(requested):
        differing = sorted(
            key for key in FIT_RELEVANT_FIELDS if stored[key] != requested[key]
        )
        detail = ", ".join(
            f"{key}: pass 1 has {stored[key]!r}, this run asks for {requested[key]!r}"
            for key in differing
        )
        raise _refuse(
            f"{subject} does not share this run's fit identity. {detail}. A "
            f"warm start from it would be a converged fit at another "
            f"configuration's optimum. Align the configuration, or re-run pass 1"
        )


__all__ = ["OUTSTANDING_SHOWN", "check_pass1_complete", "check_pass1_store"]
