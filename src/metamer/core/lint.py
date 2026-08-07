"""Static identifiability lint over a composite specification.

Compositional freedom lets users specify structurally non-identifiable models
(design doc section 4.8). This pass flags the known-degenerate patterns at
construction time, before any data. **Warn, do not block -- but say it out
loud.**

It is the *a priori* half of a pair. The *a posteriori* half already exists:
`optimize.HESSIAN_COND_LIMIT` reports `DEGENERATE_HESSIAN` for a fitted
solution whose curvature is near-singular, which is the same phenomenon
observed after the fact. Where the two overlap they should agree, and a
composite that lints clean but reports `DEGENERATE_HESSIAN` everywhere is a
gap in this module, not a run-time accident. (`ILL_CONDITIONED_X` is *not* the
counterpart: it is a property of the whitened design matrix, and this pass
never sees a design.)

Near-degeneracy is a geography, not a per-fit accident. Every rule here is a
statement about the *searched space*, so it depends on which parameters are
free:

- `ParamSpec.default` is a starting value. For a free parameter it says where
  the optimizer begins and nothing about where it ends; for `fixed=True` it is
  the value the model is pinned to for the whole fit. Findings say which of
  the two they saw, because they are different claims.
- Two terms of the same kind with a free timescale are exchangeable whatever
  their defaults: the sum kernel is symmetric under swapping them, so every
  optimum has a mirror image, and the surface where the two timescales
  coincide -- on which they merge into one term -- lies inside the searched
  region. Nothing reorders terms mid-optimization, so that symmetry is real.

Two constants govern the numeric rules, and they are not the same kind of
number. `WHITE_COLLAPSE_LOG_LIMIT` is derived from float64 and is a statement
about what any optimizer can resolve. `OVERLAP_RATIO` is declared policy: it
sets how loud the lint is about pinned timescales, and its consequence on the
kernel is stated below so that changing it means re-deriving that consequence.
Neither may be calibrated by loosening a test until a hand-built case fires.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

import numpy as np

from metamer.core.registry import kernel_registry
from metamer.core.terms import ProcessSpec, TermSpec

WHITE_COLLAPSE_LOG_LIMIT = -0.5 * math.log(float(np.finfo(np.float64).eps))
"""Largest `dt/rho` at which a timescale is still resolvable: 26*log(2).

Derived, not calibrated. A Matern nu=1/2 term contributes a correlation
`exp(-dt/rho)` at the shortest sampling interval, and that correlation is the
entire amplitude by which the term differs from white noise. Near the optimum
the log-likelihood is quadratic in the parameter, so a model difference below
`sqrt(eps)` moves it by less than `eps*|l|` and no optimizer can locate it --
the standard "a minimum is only locatable to `sqrt(eps)`" argument. Setting
`exp(-dt/rho) = sqrt(eps)` gives `dt/rho = -0.5*log(eps)`, and float64's
`eps = 2**-52` makes that `26*log(2) = 18.0218`, at a correlation of `2**-26`.

Same construction and same units as `objective.CONDITION_LOG_LIMIT`, which
takes `-0.25*log(eps)` because its solve squares the condition number.
"""

WHITE_TIMESCALE_FRACTION = 1.0 / WHITE_COLLAPSE_LOG_LIMIT
"""Multiple of the sampling interval below which a term reads as white: 0.0555."""

OVERLAP_RATIO = 1.5
"""Ratio within which two *pinned* same-kind timescales may be inseparable.

Policy, not a float64 consequence, and stated here so the number carries a
meaning. Two Matern nu=1/2 ACFs with timescales `rho` and `r*rho` differ most
at `tau* = rho*r*log(r)/(r-1)`, where the gap is
`r**(-1/(r-1)) - r**(-r/(r-1))`. At `r = 3/2` the exponents are 2 and 3, so
the gap is `(2/3)**2 - (2/3)**3 = 4/27 = 0.1481`: two terms closer than this
never separate by more than about a seventh of their own amplitude anywhere on
the lag axis. Changing the ratio means re-deriving that number.
"""

TIMESCALE_PARAM = "rho"
"""The parameter name this pass understands as a timescale.

Deliberately a single declared name rather than a guess. A stateful family
without it -- SHO, whose timescale is `Q/omega0` -- is reported as unchecked
rather than skipped, so the lint's coverage gap is visible instead of reading
as a clean bill of health.
"""


class Rule(StrEnum):
    """The degeneracy each finding reports."""

    NO_NOISE_TERMS = "no_noise_terms"
    NUGGET_COLLAPSE = "nugget_collapse"
    WHITE_COLLAPSE = "white_collapse"
    TIMESCALE_UNIDENTIFIED = "timescale_unidentified"
    SAME_KIND_FREE_TIMESCALES = "same_kind_free_timescales"
    SAME_KIND_PINNED_OVERLAP = "same_kind_pinned_overlap"
    NOT_LINTABLE = "not_lintable"


@dataclass(frozen=True)
class Finding:
    """One lint finding.

    Attributes:
        rule: Which degeneracy fired. Machine-readable, so callers filter on
            this rather than on substrings of `message`.
        terms: Labels of the terms responsible, drawn from
            `ProcessSpec.labels()`. Empty only for `NO_NOISE_TERMS`, which is
            a statement about the composition rather than about any term.
        message: Human-readable report. Names every label in `terms`.
    """

    rule: Rule
    terms: tuple[str, ...]
    message: str


@dataclass(frozen=True)
class _Timescale:
    """A term's timescale as the spec pins it.

    Attributes:
        value: The value in `ParamSpec.default`.
        pinned: True if the parameter is `fixed`, i.e. `value` describes the
            model rather than the optimizer's starting point.
    """

    value: float
    pinned: bool

    def phrase(self) -> str:
        """Render the value with the claim it supports."""
        where = "is fixed at" if self.pinned else "starts at"
        return f"{TIMESCALE_PARAM} {where} {self.value:g}"


@dataclass(frozen=True)
class _Term:
    """A term classified for linting.

    Attributes:
        label: Stable label from `ProcessSpec.labels()`.
        kind: Registry key.
        is_nugget: True if the family declares `state_dim == 0`, i.e. it has
            no memory and enters only the measurement equation.
        has_free_param: True if any parameter is not `fixed`.
        timescale: The declared timescale, or None for a nugget.
    """

    label: str
    kind: str
    is_nugget: bool
    has_free_param: bool
    timescale: _Timescale | None


def _classify(label: str, term: TermSpec) -> _Term | Finding:
    """Classify one term, or report why it cannot be linted.

    Every lookup that could raise happens here, so the rules downstream run on
    values that are already known good. `Registry.__getitem__` raises KeyError
    for an unknown key and `Family` is a Protocol rather than a base class, so
    neither the kind nor the attribute is guaranteed by the type system.

    Args:
        label: The term's stable label.
        term: The term to classify.

    Returns:
        A `_Term` if the term can be linted, otherwise a `NOT_LINTABLE`
        finding naming what is missing. Skipping instead would report a spec
        that cannot even be built as clean, which is the one answer a
        diagnostic must never give.
    """
    if term.kind not in kernel_registry:
        return Finding(
            rule=Rule.NOT_LINTABLE,
            terms=(label,),
            message=(
                f"{label}: kind {term.kind!r} is not registered, so this term "
                "was not checked for identifiability"
            ),
        )
    family = kernel_registry[term.kind]()
    state_dim = getattr(family, "state_dim", None)
    if state_dim is None:
        return Finding(
            rule=Rule.NOT_LINTABLE,
            terms=(label,),
            message=(
                f"{label}: family {term.kind!r} declares no state_dim, so this "
                "term was not checked for identifiability"
            ),
        )
    has_free_param = any(not p.fixed for p in term.params.values())
    if int(state_dim) == 0:
        return _Term(label, term.kind, True, has_free_param, None)
    if TIMESCALE_PARAM not in term.params:
        return Finding(
            rule=Rule.NOT_LINTABLE,
            terms=(label,),
            message=(
                f"{label}: family {term.kind!r} has state but no "
                f"{TIMESCALE_PARAM!r} parameter, so its timescale is not one "
                "this pass knows how to read and the term was not checked"
            ),
        )
    param = term.params[TIMESCALE_PARAM]
    timescale = _Timescale(float(param.default), bool(param.fixed))
    return _Term(label, term.kind, False, has_free_param, timescale)


def _nugget_collapse(terms: list[_Term]) -> list[Finding]:
    """Report nugget scales that only ever appear as a sum.

    Nugget terms contribute `sigma_i**2` to the variance and nothing else, so
    the record constrains `sum_i sigma_i**2` and no individual term. One free
    scale beside any number of pinned ones is still identified -- the pinned
    contributions are known -- so the rule needs two *free* nuggets, not two
    nuggets.

    Args:
        terms: Classified terms.

    Returns:
        At most one finding, naming every free nugget.
    """
    free = [t for t in terms if t.is_nugget and t.has_free_param]
    if len(free) < 2:
        return []
    labels = tuple(t.label for t in free)
    listed = ", ".join(labels)
    return [
        Finding(
            rule=Rule.NUGGET_COLLAPSE,
            terms=labels,
            message=(
                f"{listed}: these terms have no state, so the record "
                "constrains only the sum of their variances; their individual "
                "scales are not identified"
            ),
        )
    ]


def _white_collapse(
    terms: list[_Term], sampling_interval: float, nuggets: tuple[str, ...]
) -> list[Finding]:
    """Report stateful terms whose timescale is below the resolvable limit.

    Below `WHITE_TIMESCALE_FRACTION * sampling_interval` the term's
    correlation at the shortest sampling interval is under `sqrt(eps)`, so the
    likelihood is flat in the timescale. What else is lost depends on the
    company it keeps: alone, the amplitude is still estimable from the
    variance and only the timescale goes; beside a nugget, the two scales
    appear only as a sum and the composition is `white + white`.

    Args:
        terms: Classified terms.
        sampling_interval: Median observation spacing.
        nuggets: Labels of every nugget term in the spec.

    Returns:
        One finding per offending term.
    """
    limit = WHITE_TIMESCALE_FRACTION * sampling_interval
    findings: list[Finding] = []
    for term in terms:
        if term.timescale is None or term.timescale.value >= limit:
            continue
        head = (
            f"{term.label}: {term.timescale.phrase()}, below {limit:g} "
            f"(sampling interval {sampling_interval:g} / "
            f"{WHITE_COLLAPSE_LOG_LIMIT:.4f}), so its correlation at one "
            "sampling interval is under sqrt(eps)"
        )
        if nuggets:
            findings.append(
                Finding(
                    rule=Rule.WHITE_COLLAPSE,
                    terms=(term.label, *nuggets),
                    message=(
                        f"{head}; with {', '.join(nuggets)} present the "
                        "composition collapses to white + white and neither "
                        "scale is identified"
                    ),
                )
            )
        else:
            findings.append(
                Finding(
                    rule=Rule.TIMESCALE_UNIDENTIFIED,
                    terms=(term.label,),
                    message=(
                        f"{head}; the likelihood is flat in "
                        f"{TIMESCALE_PARAM}, though the amplitude is still "
                        "estimable from the variance"
                    ),
                )
            )
    return findings


def _same_kind(terms: list[_Term]) -> list[Finding]:
    """Report same-kind pairs that can merge onto one another.

    Two terms of the same kind sum to one term wherever their timescales
    coincide. Whether that is reachable is decided by which timescales are
    free:

    - Either one free: the coincidence surface is inside the searched region,
      and the sum kernel is symmetric under swapping the pair, so the optimum
      is not unique. The defaults are irrelevant -- reporting on their ratio
      would call a factor of 1000 clean while per-term maps come out
      salt-and-pepper as neighbouring points land in different mirror images.
    - Both pinned: the model is fixed away from the surface, and separability
      is decided by how far away, i.e. by `OVERLAP_RATIO`.

    Args:
        terms: Classified terms.

    Returns:
        One finding per offending pair, in label order.
    """
    findings: list[Finding] = []
    scaled = [(t, t.timescale) for t in terms if t.timescale is not None]
    for i, (first, a) in enumerate(scaled):
        for second, b in scaled[i + 1 :]:
            if first.kind != second.kind:
                continue
            pair = (first.label, second.label)
            if not (a.pinned and b.pinned):
                findings.append(
                    Finding(
                        rule=Rule.SAME_KIND_FREE_TIMESCALES,
                        terms=pair,
                        message=(
                            f"{first.label} and {second.label} are both "
                            f"{first.kind} with a free {TIMESCALE_PARAM}; the "
                            "optimizer can drive their timescales together, "
                            "where the two merge into one term, and swapping "
                            "them leaves the likelihood unchanged, so their "
                            "individual parameters are not identified"
                        ),
                    )
                )
                continue
            hi, lo = max(a.value, b.value), min(a.value, b.value)
            if lo <= 0.0 or hi / lo >= OVERLAP_RATIO:
                continue
            findings.append(
                Finding(
                    rule=Rule.SAME_KIND_PINNED_OVERLAP,
                    terms=pair,
                    message=(
                        f"{first.label} and {second.label} are both "
                        f"{first.kind} with timescales within a factor of "
                        f"{hi / lo:.3f}, closer than {OVERLAP_RATIO:g}; these "
                        "terms may collapse onto each other and the resulting "
                        "IC weights would not be meaningful"
                    ),
                )
            )
    return findings


def lint(spec: ProcessSpec, sampling_interval: float) -> list[Finding]:
    """Report structurally degenerate patterns in a composition.

    Warns, never blocks: a degenerate specification comes back as findings, so
    a user who knowingly wants that model can still fit it. That promise is
    about the *specification*. An unusable `sampling_interval` is a caller
    error and raises, because the alternative -- comparing every timescale
    against a limit of zero, or against NaN -- returns an empty finding list,
    and a diagnostic that reports "clean" because it could not run is worse
    than one that stops.

    Args:
        spec: The composite specification.
        sampling_interval: Median observation spacing, in the same time units
            as the timescale parameters.

    Returns:
        A list of findings, empty if the composition lints clean.

    Raises:
        ValueError: If `sampling_interval` is not finite and positive.
    """
    if not math.isfinite(sampling_interval) or sampling_interval <= 0.0:
        raise ValueError(
            f"sampling_interval must be finite and positive, got {sampling_interval}"
        )
    if not spec.terms:
        return [
            Finding(
                rule=Rule.NO_NOISE_TERMS,
                terms=(),
                message=(
                    "the specification has no noise terms, so its covariance "
                    "is identically zero and nothing is identified"
                ),
            )
        ]

    findings: list[Finding] = []
    classified: list[_Term] = []
    for label, term in zip(spec.labels(), spec.terms, strict=True):
        result = _classify(label, term)
        if isinstance(result, Finding):
            findings.append(result)
        else:
            classified.append(result)

    nuggets = tuple(t.label for t in classified if t.is_nugget)
    findings.extend(_nugget_collapse(classified))
    findings.extend(_white_collapse(classified, sampling_interval, nuggets))
    findings.extend(_same_kind(classified))
    return findings
