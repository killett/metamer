"""What a candidate spec RESOLVES TO, as opposed to what a config asked for.

**DESIGN DOC SECTION 14.2 WANTS THE RESOLUTION AND THE STORE ONLY HAD THE
REQUEST.** Root attrs carry `engine` and `objective` run-level and
`candidate_spec_hashes` -- hashes, which are one-way -- so the per-candidate
resolution was not recoverable from a finished store at all (D12). This module
is the one place that computes it, and `batch.store` records what it returns.

**IT NEVER SEES THE REQUESTED ENGINE, AND THAT IS THE POINT.** A block whose
engine column is filled from `config.engine` records the REQUEST under the name
`resolved` -- D1's tell, a name saying one thing while the value is another --
and it passes every test until a second engine exists, because with one engine
the two are equal. Phase 3's Whittle engine is when they stop being equal, and
a column already wired to the wrong source would start lying silently. So the
resolution is computed from the spec alone, and the engine column says plainly
that it is not resolved per candidate yet.
"""

from __future__ import annotations

from dataclasses import dataclass

from metamer.core.capability import CostClass, EngineId, GradientMode, Objective
from metamer.core.gradients import resolve_gradient_mode
from metamer.core.terms import ProcessSpec

#: What the engine column says while only one engine exists.
#:
#: **SECTION 4.2's INTERSECTION NARROWS ENGINES PER CANDIDATE AND THE BATCH
#: PATH DOES NOT CONSULT IT**: `run.py` passes `config.engine` into `fit` and
#: `ProcessSpec.engine_costs()` has no caller outside `terms` and `capability`.
#: With one engine there is nothing to narrow, so nothing is wrong today --
#: **and the honest record of "we did not resolve this" is not the request.**
ENGINE_NOT_RESOLVED = "requested; not resolved per candidate in this version"


@dataclass(frozen=True)
class CandidateResolution:
    """One candidate's resolved capabilities, from its spec alone.

    Attributes:
        label: The `m`-axis label, as the store spells it.
        spec_hash: The spec's stable hash, so the row is identifiable even if
            the label spelling ever changes.
        engine: **Not resolved per candidate in this version**; see
            `ENGINE_NOT_RESOLVED`. Never the configured engine.
        engine_costs: The surviving engines and this composite's cost for each,
            by section 4.2's intersection -- **the worst cost across terms**,
            which is what makes the cost class a per-candidate fact rather than
            a per-family one.
        gradient_mode: `ANALYTIC` only if every term declares *and implements*
            it for this objective; `FINITE_DIFFERENCE` otherwise. The second
            per-candidate fact that genuinely narrows.
        objective: The objective this resolution was taken under.
    """

    label: str
    spec_hash: str
    engine: str
    engine_costs: dict[EngineId, CostClass]
    gradient_mode: GradientMode
    objective: Objective

    def as_record(self) -> dict[str, object]:
        """A JSON-safe row for the store's root attrs."""
        return {
            "label": self.label,
            "spec_hash": self.spec_hash,
            "engine": self.engine,
            # **SORTED, BECAUSE PROVENANCE MUST NOT DEPEND ON
            # `PYTHONHASHSEED`.** `intersect_engine_costs` builds its mapping
            # from SET iteration, so the key order varies between processes --
            # measured at three seeds, three different orders for identical
            # content. Unsorted, two runs of one config write byte-different
            # root attrs, which `test_the_root_attrs_are_byte_identical_across_processes`
            # refuses and which the full sweep is what caught. **The (k) shape:
            # a property of a different process that no test in this one
            # reaches.**
            "engine_costs": {
                engine.value: cost.value
                for engine, cost in sorted(
                    self.engine_costs.items(), key=lambda item: item[0].value
                )
            },
            "gradient_mode": self.gradient_mode.value,
            "objective": self.objective.value,
        }


def resolve_candidate(
    spec: ProcessSpec, label: str, objective: Objective
) -> CandidateResolution:
    """Resolve one candidate's capabilities from its spec.

    Args:
        spec: The candidate's process specification.
        label: Its `m`-axis label.
        objective: The run's objective.

    Returns:
        The resolution, with the engine column explicitly unresolved.
    """
    return CandidateResolution(
        label=label,
        spec_hash=spec.spec_hash(),
        engine=ENGINE_NOT_RESOLVED,
        engine_costs=spec.engine_costs(),
        gradient_mode=resolve_gradient_mode(spec, objective),
        objective=objective,
    )
