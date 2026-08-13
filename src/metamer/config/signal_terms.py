"""The signal vocabulary: config strings to `core.signal` terms.

**BLOCKED SINCE TASK 6, AND THIS IS WHY IT MATTERS.** Nothing mapped
`signal_terms` to `core.signal` classes, so `k_beta` -- the design column count --
was unobtainable, **no tile could be sized**, and `run()` could not iterate. The
noise side has had this since Phase 1 (`config.candidates.parse_candidate`
through `kernel_registry`); this is its counterpart.

**THE REGISTRY IS SHARED MACHINERY AND THE PARSER DELIBERATELY IS NOT.** A noise
candidate is a **sum expression of bare names** -- `"white + matern12"` -- and
`parse_candidate` refuses a call, an attribute, a subscript and a literal by
name. A signal term is **constructed with an argument** and `signal_terms` is a
**list**, with no `+` in it at all. One grammar admitting both would have to
accept arguments inside a sum expression and `+` inside an argument, which is how
a vocabulary stops being testable. `core.registry.Registry` is what they share,
and it brings the entry-point group with it.

**THE SPELLING WAS ALREADY HALF-DECIDED IN THE TREE.** Task 4 added
`model.PER_POINT_TERM_PREFIX = "regressor_field:"` -- a `kind:argument` form
**already living inside `signal_terms`** -- so a parameterized term is
`offset:2005.5`. Inventing a second idiom would put two syntaxes inside one
config field.

**A DECLARED-BUT-REFUSED TERM IS NOT AN UNKNOWN ONE.** `regressor_field:` is the
per-point regressor regime, refused at layer 3 with both tile sizes named; it
must not be reported as a typo. `expdecay` and `logdecay` are nonlinear and
Phase 4's, and they are **not registered at all**: a name a config can reach
would turn a refusal that belongs at layer 3 into a `NotImplementedError` raised
inside the design build, inside the tile loop, ten hours in.
"""

from __future__ import annotations

from collections.abc import Sequence

from metamer.core.registry import signal_registry
from metamer.core.signal import SignalSpec, SignalTerm

#: Separates a term's name from its argument: `offset:2005.5`. The same
#: character `PER_POINT_TERM_PREFIX` already uses inside this field.
ARGUMENT_SEPARATOR = ":"

#: Names that exist as classes and are deliberately unreachable from a config,
#: with the reason a user needs. Reported as deferrals rather than as typos.
DEFERRED_TERMS = {
    "expdecay": "nonlinear in its timescale; joint optimization is Phase 4",
    "logdecay": "nonlinear in its timescale; joint optimization is Phase 4",
    "regressor": (
        "an external regressor is the per-point regressor regime, declared as "
        "'regressor_field:<name>' and refused at layer 3"
    ),
}


def parse_signal_term(entry: str) -> SignalTerm:
    """Build one signal term from its config spelling.

    Args:
        entry: `"trend"`, or `"offset:2005.5"`.

    Returns:
        The term.

    Raises:
        ValueError: If the name is empty, is a deferred term, or is unknown; or
            if the argument is missing, malformed or supplied where none is
            taken. The factories own the argument rules, so each message comes
            from beside the class it describes.
    """
    name, separator, argument = entry.partition(ARGUMENT_SEPARATOR)
    name = name.strip()
    supplied = argument.strip() if separator else None

    if not name:
        raise ValueError(
            f"signal term {entry!r} has no name; write a registered term, "
            "optionally with an argument, e.g. 'trend' or 'offset:2005.5'"
        )
    if name in DEFERRED_TERMS:
        raise ValueError(
            f"signal term {name!r} is not available: {DEFERRED_TERMS[name]}"
        )
    if name not in signal_registry:
        raise ValueError(
            f"signal term {name!r} is not registered; available terms are "
            f"{sorted(signal_registry)}"
        )
    term = signal_registry[name](supplied)
    if not isinstance(term, SignalTerm):
        raise ValueError(  # pragma: no cover - guards a third-party registration
            f"signal term {name!r} produced {type(term).__name__}, which is not "
            "a SignalTerm"
        )
    return term


def parse_signal_terms(entries: Sequence[str]) -> SignalSpec:
    """Build the signal specification from a config's `signal_terms`.

    **ORDER IS PRESERVED, UNLIKE THE NOISE SIDE.** `ProcessSpec` sorts its terms
    canonically because a noise composition is a sum whose order carries no
    information. A signal spec's order **is** the design's column order, and the
    column order is `beta`'s axis in the store -- so reordering the config would
    silently permute a stored `beta` against its own labels.

    Args:
        entries: The config's `signal_terms`, in config order.

    Returns:
        The specification, terms in config order.

    Raises:
        ValueError: If the list is empty -- a design with no columns leaves the
            trend, the entire scientific payload, undefined -- or if any entry
            is malformed. See `parse_signal_term`.
    """
    if not entries:
        raise ValueError(
            "signal_terms is empty; a design with no columns has no trend to "
            "estimate, which is the output this package exists to produce"
        )
    return SignalSpec([parse_signal_term(entry) for entry in entries])
