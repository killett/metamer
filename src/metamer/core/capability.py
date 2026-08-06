"""Engine, objective, and gradient capability, resolved by intersection."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from enum import IntEnum, StrEnum


class EngineId(StrEnum):
    """Likelihood engines. Only KALMAN is implemented in Phase 1."""

    KALMAN = "kalman"
    WHITTLE = "whittle"
    TOEPLITZ = "toeplitz"
    CELERITE2 = "celerite2"


class CostClass(IntEnum):
    """Asymptotic evaluation cost, ordered cheapest to most expensive."""

    LINEAR = 1
    NLOGN = 2
    CUBIC = 3


class Objective(StrEnum):
    """Which likelihood is being maximized."""

    ML = "ml"
    REML = "reml"


class GradientMode(StrEnum):
    """How the gradient is obtained. ANALYTIC beats FD when available."""

    ANALYTIC = "analytic"
    FINITE_DIFFERENCE = "fd"


class IncompatibleSpecError(ValueError):
    """No engine can evaluate the composite specification."""


def intersect_engine_costs(
    per_term: Iterable[tuple[str, Mapping[EngineId, CostClass]]],
) -> dict[EngineId, CostClass]:
    """Resolve a composite's engine capability by intersection.

    An engine survives only if every term supports it, and the composite's
    cost for that engine is the worst cost across terms.

    The candidate set is the union of engines named by *any* term, not just
    the first. This matters with three or more terms: an engine the first
    term does not support can still be the entire reason nothing survives,
    and it must be nameable in the error even though the first term's own
    mapping never mentions it. Each candidate's eliminator is the first term
    (in input order) whose mapping lacks it.

    Args:
        per_term: Pairs of (term label, that term's engine cost mapping).

    Returns:
        Mapping from surviving engine to composite cost class.

    Raises:
        IncompatibleSpecError: If no engine survives. The message names every
            candidate engine together with the term that eliminated it. If
            every term declares an empty engine mapping, `candidates` itself
            is empty and there is no per-engine elimination to report; the
            message instead names every term responsible.
    """
    items = list(per_term)
    if not items:
        return {}

    candidates: set[EngineId] = set()
    for _, costs in items:
        candidates.update(costs)

    if not candidates:
        # The union of every term's engine set is empty, which is only
        # possible if every term's own mapping is empty -- there is no
        # per-engine elimination to report here (the loop below never runs),
        # so naming *which* term(s) declared no engines at all is the only
        # way this error stays informative instead of reading "... : ".
        labels = ", ".join(label for label, _ in items)
        raise IncompatibleSpecError(
            "No engine can evaluate this composite: no term declared any "
            f"supported engines ({labels})"
        )

    surviving: dict[EngineId, CostClass] = {}
    eliminated_by: dict[EngineId, str] = {}
    for engine in candidates:
        eliminator = next(
            (label for label, costs in items if engine not in costs), None
        )
        if eliminator is not None:
            eliminated_by[engine] = eliminator
        else:
            surviving[engine] = max(costs[engine] for _, costs in items)

    if not surviving:
        detail = ", ".join(
            f"{engine.value} eliminated by {label}"
            for engine, label in sorted(
                eliminated_by.items(), key=lambda pair: pair[0].value
            )
        )
        raise IncompatibleSpecError(f"No engine can evaluate this composite: {detail}")
    return surviving


def intersect_gradient_modes(
    per_term: Iterable[Mapping[Objective, GradientMode]], objective: Objective
) -> GradientMode:
    """Resolve the composite gradient mode for one objective.

    A composite has an analytic gradient only if every term does, for that
    objective. Gradient availability differs by objective because the REML
    penalty is not covered by the envelope theorem.

    Args:
        per_term: Each term's per-objective gradient mode.
        objective: The objective being evaluated.

    Returns:
        ANALYTIC if every term supplies it, otherwise FINITE_DIFFERENCE.
    """
    modes = [m.get(objective, GradientMode.FINITE_DIFFERENCE) for m in per_term]
    if modes and all(m is GradientMode.ANALYTIC for m in modes):
        return GradientMode.ANALYTIC
    return GradientMode.FINITE_DIFFERENCE
