"""The kernel algebra: TermSpec, ProcessSpec, canonical form, and hashing."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from metamer.core.params import ParamSpec


def _param_canonical(spec: ParamSpec) -> dict[str, Any]:
    """Render a ParamSpec into a JSON-safe canonical dict."""
    return {
        "name": spec.name,
        "default": repr(float(spec.default)),
        "transform": type(spec.transform).__name__,
        "transform_args": getattr(spec.transform, "__dict__", {}),
        "bounds": [repr(float(b)) for b in spec.bounds],
        "diagnostic_limits": [repr(float(b)) for b in spec.diagnostic_limits],
        "fixed": bool(spec.fixed),
        "unit": spec.unit,
    }


@dataclass(frozen=True)
class TermSpec:
    """One additive kernel term.

    Attributes:
        kind: Registry key naming the family.
        params: Parameter specifications, keyed by name.
        ordering_param: Parameter used as the secondary canonical sort key.
            Terms without one sort only by kind.
    """

    kind: str
    params: Mapping[str, ParamSpec]
    ordering_param: str | None = None
    shared_with: Mapping[str, str] | None = None

    def order_key(self) -> tuple[str, float]:
        """Return the canonical sort key for this term."""
        if self.ordering_param is None:
            return (self.kind, 0.0)
        return (self.kind, float(self.params[self.ordering_param].default))

    def n_free(self) -> int:
        """Count parameters this term contributes to k_theta."""
        return sum(1 for p in self.params.values() if not p.fixed)

    def canonical(self) -> dict[str, Any]:
        """Render to a JSON-safe canonical dict with sorted parameter keys."""
        return {
            "kind": self.kind,
            "ordering_param": self.ordering_param,
            "params": {
                name: _param_canonical(self.params[name])
                for name in sorted(self.params)
            },
        }

    def __add__(self, other: TermSpec | ProcessSpec) -> ProcessSpec:
        """Compose with another term or process."""
        return ProcessSpec((self,)) + other


@dataclass(frozen=True)
class ProcessSpec:
    """An additive composition of kernel terms, canonically ordered.

    Canonicalization happens here, at construction, and again when results are
    packed. It must never happen mid-optimization: re-sorting between optimizer
    iterations permutes the parameter vector under stored curvature and
    corrupts it.
    """

    terms: tuple[TermSpec, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        """Sort `terms` into canonical order immediately after construction."""
        ordered = tuple(sorted(self.terms, key=lambda t: t.order_key()))
        object.__setattr__(self, "terms", ordered)

    def __add__(self, other: TermSpec | ProcessSpec) -> ProcessSpec:
        """Compose with another term or process."""
        if isinstance(other, TermSpec):
            return ProcessSpec(self.terms + (other,))
        return ProcessSpec(self.terms + other.terms)

    def __radd__(self, other: TermSpec) -> ProcessSpec:
        """Support TermSpec + ProcessSpec."""
        return ProcessSpec((other,)) + self

    def labels(self) -> tuple[str, ...]:
        """Return stable per-term labels, disambiguating repeated kinds."""
        counts: dict[str, int] = {}
        out: list[str] = []
        for term in self.terms:
            index = counts.get(term.kind, 0)
            counts[term.kind] = index + 1
            out.append(f"{term.kind}[{index}]")
        return tuple(out)

    def n_theta(self) -> int:
        """Count free noise parameters across all terms."""
        return sum(term.n_free() for term in self.terms)

    def canonical(self) -> dict[str, Any]:
        """Render the whole composition to a JSON-safe canonical dict."""
        return {"terms": [term.canonical() for term in self.terms]}

    def spec_hash(self) -> str:
        """Return a stable 16-character hash of the canonical form."""
        encoded = json.dumps(self.canonical(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def free_param_index(spec: ProcessSpec) -> tuple[tuple[str, str], ...]:
    """Return the layout of the flat parameter vector, free parameters only.

    THIS IS THE SINGLE SOURCE OF TRUTH for the ordering of the parameter vector
    the optimizer searches. Everything that packs or unpacks that vector --
    `objective.to_natural`, `to_unconstrained`, `dforward`, the diagnostic-limit
    check in `optimize`, the gradient routines, and the memory formula -- calls
    this rather than re-deriving the layout with its own nested loop.

    The convention is: canonical term order (already applied by ProcessSpec),
    then each term's declared parameter order, skipping any parameter with
    `fixed=True`.

    The invariant `len(free_param_index(spec)) == spec.n_theta()` ties this
    layout to the count that feeds `k` in every information criterion. If the
    two ever disagree, selection is corrupted with no visible symptom.

    Args:
        spec: The composite specification.

    Returns:
        Ordered (term_label, param_name) pairs, one per free parameter.

    Raises:
        NotImplementedError: If any term declares a shared parameter. Design
            doc section 4.7 requires counting to handle cross-term sharing;
            Phase 1 implements no sharing mechanism, so such a spec must be
            refused rather than silently counted as independent.
    """
    out: list[tuple[str, str]] = []
    for label, term in zip(spec.labels(), spec.terms, strict=True):
        if term.shared_with:
            raise NotImplementedError(
                f"{label}: cross-term shared parameters {sorted(term.shared_with)} are "
                "not implemented in Phase 1; see design doc section 4.7"
            )
        for name, param in term.params.items():
            if not param.fixed:
                out.append((label, name))
    return tuple(out)
