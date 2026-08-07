"""The kernel algebra: TermSpec, ProcessSpec, canonical form, and hashing."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from metamer.core.params import ParamSpec
from metamer.core.transforms import Bijector

if TYPE_CHECKING:
    from metamer.core.capability import CostClass, EngineId


def _transform_args_canonical(transform: Bijector) -> dict[str, str]:
    """Render a bijector's constructor arguments into a JSON-safe dict.

    Applies the same `repr(float(...))` stringification that `_param_canonical`
    applies to `default`, `bounds`, and `diagnostic_limits`. Without it, a
    `Logit` built with an infinite bound would embed a raw `float("inf")`,
    which `json.dumps` renders as the non-standard `Infinity` token and
    breaks the "canonical() round-trips through json.dumps" invariant.

    Args:
        transform: The bijector instance backing a ParamSpec.

    Returns:
        A dict from sorted argument name to its `repr(float(...))` string.
    """
    raw: dict[str, Any] = getattr(transform, "__dict__", {})
    return {name: repr(float(raw[name])) for name in sorted(raw)}


def _param_canonical(spec: ParamSpec) -> dict[str, Any]:
    """Render a ParamSpec into a JSON-safe canonical dict."""
    return {
        "name": spec.name,
        "default": repr(float(spec.default)),
        "transform": type(spec.transform).__name__,
        "transform_args": _transform_args_canonical(spec.transform),
        "bounds": [repr(float(b)) for b in spec.bounds],
        "diagnostic_limits": [repr(float(b)) for b in spec.diagnostic_limits],
        "fixed": bool(spec.fixed),
        "unit": spec.unit,
    }


def _refuse_shared(term: TermSpec, label: str | None = None) -> None:
    """Raise if `term` declares cross-term shared parameters.

    Both `TermSpec.n_free` and `free_param_index` must refuse the same specs
    the same way -- one feeds `k` in every information criterion, the other
    defines the optimizer's search vector, and letting them diverge on
    shared-parameter handling would let `n_theta()` silently count a shared
    parameter as independent while `free_param_index` refuses it.

    Args:
        term: Term to check.
        label: The term's stable label, included in the message when the
            caller has one. `TermSpec.n_free` does not have a label to give
            (labels are a `ProcessSpec`-level concept), so it is optional.

    Raises:
        NotImplementedError: If `term.shared_with` is truthy. Design doc
            section 4.7 requires counting to handle cross-term sharing;
            Phase 1 implements no sharing mechanism, so such a term must be
            refused rather than silently counted as independent.
    """
    if term.shared_with:
        prefix = f"{label}: " if label is not None else ""
        raise NotImplementedError(
            f"{prefix}cross-term shared parameters {sorted(term.shared_with)} are "
            "not implemented in Phase 1; see design doc section 4.7"
        )


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

    def order_key(self) -> tuple[str, float, str]:
        """Return the canonical sort key for this term.

        The key is `(kind, ordering-parameter default, canonical JSON)`. The
        first two elements alone are not a total order: two terms of the same
        kind with an identical ordering-parameter default (but different
        other parameters, e.g. `sigma`) would tie, and Python's stable sort
        would then fall back to construction order -- silently reintroducing
        the order-dependence in `spec_hash()` and in label-to-term
        association that this task exists to eliminate. Appending the term's
        own canonical serialization makes the key total: two terms tie under
        it only when they are canonically identical, in which case
        construction order carries no information anyway.
        """
        ordering_default = (
            0.0
            if self.ordering_param is None
            else float(self.params[self.ordering_param].default)
        )
        canonical_json = json.dumps(
            self.canonical(), sort_keys=True, separators=(",", ":")
        )
        return (self.kind, ordering_default, canonical_json)

    def n_free(self) -> int:
        """Count parameters this term contributes to k_theta.

        Raises:
            NotImplementedError: If this term declares shared parameters --
                see `_refuse_shared`.
        """
        _refuse_shared(self)
        return sum(1 for p in self.params.values() if not p.fixed)

    def canonical(self) -> dict[str, Any]:
        """Render to a JSON-safe canonical dict with sorted parameter keys.

        `shared_with` is included because `canonical()` defines spec identity
        and a shared-parameter declaration changes what the model is -- design
        doc section 4.7 counts a shared parameter once rather than twice, so
        two terms differing only in this field have different `k`. It is
        unreachable today, because `n_free` refuses such a spec before
        anything hashes it, but that is an argument about REACHABILITY and not
        about identity, and reachability changes the moment sharing is
        implemented. At that point two genuinely different models would share
        a `spec_hash` and one would silently reuse the other's cached `expm`,
        warm start and fits. Keys are sorted for the same reason every other
        mapping here is: the hash must not depend on the order a user wrote
        the pairs in.
        """
        return {
            "kind": self.kind,
            "ordering_param": self.ordering_param,
            "params": {
                name: _param_canonical(self.params[name])
                for name in sorted(self.params)
            },
            "shared_with": (
                None
                if self.shared_with is None
                else {name: self.shared_with[name] for name in sorted(self.shared_with)}
            ),
        }

    def engine_costs(self) -> dict[EngineId, CostClass]:
        """Return this term's per-engine cost classes from its family."""
        from metamer.core.registry import kernel_registry

        return kernel_registry[self.kind]().engine_costs

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
        """Count free noise parameters across all terms.

        Derived independently from `free_param_index`: this sums each term's
        own `n_free()` rather than computing `len(free_param_index(self))`,
        so the two stay separate checks on the same invariant instead of one
        masquerading as the other.

        Raises:
            NotImplementedError: If any term declares shared parameters --
                see `TermSpec.n_free`.
        """
        return sum(term.n_free() for term in self.terms)

    def canonical(self) -> dict[str, Any]:
        """Render the whole composition to a JSON-safe canonical dict."""
        return {"terms": [term.canonical() for term in self.terms]}

    def engine_costs(self) -> dict[EngineId, CostClass]:
        """Resolve composite engine capability by intersection across terms."""
        from metamer.core.capability import intersect_engine_costs

        return intersect_engine_costs(
            zip(self.labels(), (t.engine_costs() for t in self.terms), strict=True)
        )

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
        _refuse_shared(term, label)
        for name, param in term.params.items():
            if not param.fixed:
                out.append((label, name))
    return tuple(out)
