import pytest

from metamer.core.capability import (
    CostClass,
    EngineId,
    GradientMode,
    IncompatibleSpecError,
    Objective,
    intersect_engine_costs,
    intersect_gradient_modes,
)


def test_cost_class_orders_by_asymptotic_cost():
    """LINEAR < NLOGN < CUBIC, so `max` picks the worst.

    Expected value determined independently: O(N) is cheaper than O(N log N)
    is cheaper than O(N^3) for all N > 1.
    """
    assert CostClass.LINEAR < CostClass.NLOGN < CostClass.CUBIC
    assert max(CostClass.LINEAR, CostClass.CUBIC) is CostClass.CUBIC


def test_intersection_keeps_only_engines_supported_by_every_term():
    """An engine survives only if every term supports it.

    Expected value determined independently: term A supports {kalman,
    whittle}, term B supports {whittle, toeplitz}; the intersection is
    {whittle} by set intersection done on paper.
    """
    a = {EngineId.KALMAN: CostClass.LINEAR, EngineId.WHITTLE: CostClass.NLOGN}
    b = {EngineId.WHITTLE: CostClass.NLOGN, EngineId.TOEPLITZ: CostClass.CUBIC}
    result = intersect_engine_costs([("a", a), ("b", b)])
    assert set(result) == {EngineId.WHITTLE}


def test_intersection_takes_the_worst_cost_per_engine():
    """A composite is as expensive as its most expensive term.

    Bug this catches: taking the min or the first cost, which would let the
    batch layer accept an O(N^3) composite at 10^7 scale.
    """
    a = {EngineId.KALMAN: CostClass.LINEAR}
    b = {EngineId.KALMAN: CostClass.CUBIC}
    result = intersect_engine_costs([("a", a), ("b", b)])
    assert result[EngineId.KALMAN] is CostClass.CUBIC


def test_empty_intersection_names_the_eliminating_term():
    """The error message identifies which term removed which engine.

    Bug this catches: a bare "no engine available", which at 12 candidates
    leaves the user guessing which term is at fault.
    """
    a = {EngineId.KALMAN: CostClass.LINEAR}
    b = {EngineId.TOEPLITZ: CostClass.CUBIC}
    with pytest.raises(IncompatibleSpecError) as excinfo:
        intersect_engine_costs([("statespace_term", a), ("exact_powerlaw", b)])
    message = str(excinfo.value)
    assert "exact_powerlaw" in message
    assert "kalman" in message


def test_three_term_intersection_names_first_term_as_bottleneck():
    """A candidate engine absent only from the *first* term is still named.

    Correction 2 to the task-3 brief: the brief's original algorithm seeded
    the candidate set from the first term's own mapping and only recorded
    eliminations caused by *later* terms. Here KALMAN is absent only from
    "first_term" -- present in both "second_term" and "third_term" -- so it
    is the entire reason the intersection is empty, yet the brief's original
    code would never mention "first_term" (or KALMAN) at all: it starts from
    {WHITTLE: NLOGN} (first_term's own mapping), which does not contain
    KALMAN to begin with, so KALMAN can never be recorded as "eliminated" by
    anything under that algorithm.

    Bug this catches: exactly the brief's original bug -- an eliminating
    first term silently missing from the error message with 3+ terms.
    """
    first = {EngineId.WHITTLE: CostClass.NLOGN}
    second = {EngineId.KALMAN: CostClass.LINEAR}
    third = {EngineId.KALMAN: CostClass.LINEAR}
    with pytest.raises(IncompatibleSpecError) as excinfo:
        intersect_engine_costs(
            [("first_term", first), ("second_term", second), ("third_term", third)]
        )
    message = str(excinfo.value)
    assert "first_term" in message
    assert "kalman" in message


def test_all_empty_engine_mappings_names_every_term():
    """Every term declaring no engines at all still names both terms.

    Before this fix, an empty per-term engine mapping made `candidates` (the
    union of engines named by any term) empty too, so the per-engine
    elimination loop never ran, `eliminated_by` stayed empty, and the raised
    message's detail was the empty string -- "No engine can evaluate this
    composite: ", naming nothing. That defeats the entire point of the
    error, which the task and every other test in this file exist to check:
    it must name the term(s) at fault.

    Expected value determined independently: with both "term_a" and
    "term_b" declaring `{}`, there is no engine for either the per-engine
    loop or a "which engine got eliminated" framing to even talk about, so
    the message must instead name the terms themselves; both must appear.

    Bug this catches: reverting to the pre-fix behaviour (empty detail
    string), or naming only one of the two equally-at-fault terms.
    """
    with pytest.raises(IncompatibleSpecError) as excinfo:
        intersect_engine_costs([("term_a", {}), ("term_b", {})])
    message = str(excinfo.value)
    assert message != "No engine can evaluate this composite: "
    assert "term_a" in message
    assert "term_b" in message


def test_gradient_modes_all_analytic_resolve_to_analytic():
    """Every term ANALYTIC for the objective resolves to ANALYTIC.

    Expected value determined independently: both terms supply ANALYTIC for
    Objective.ML, so by the "only if every term does" rule stated in the
    function's own docstring, the composite must resolve to ANALYTIC.

    Bug this catches: intersect_gradient_modes defaulting to
    FINITE_DIFFERENCE even when every term supplies an analytic gradient,
    which would force every fit onto the slow FD path unnecessarily.
    """
    per_term = [
        {Objective.ML: GradientMode.ANALYTIC},
        {Objective.ML: GradientMode.ANALYTIC},
    ]
    assert intersect_gradient_modes(per_term, Objective.ML) is GradientMode.ANALYTIC


def test_gradient_modes_one_fd_term_forces_finite_difference():
    """One FD term among otherwise-ANALYTIC terms forces the composite to FD.

    Expected value determined independently: a composite has an analytic
    gradient only if *every* term does; with two ANALYTIC terms and one FD
    term, that condition is false by definition, so the result must be
    FINITE_DIFFERENCE regardless of how many terms are ANALYTIC.

    Bug this catches: an `any` instead of `all` check, which would let a
    single analytic term make the whole composite look analytic even though
    one term's gradient must be finite-differenced.
    """
    per_term = [
        {Objective.ML: GradientMode.ANALYTIC},
        {Objective.ML: GradientMode.FINITE_DIFFERENCE},
        {Objective.ML: GradientMode.ANALYTIC},
    ]
    assert (
        intersect_gradient_modes(per_term, Objective.ML)
        is GradientMode.FINITE_DIFFERENCE
    )


def test_gradient_modes_differ_by_objective_for_the_same_term():
    """The same per-term data resolves differently depending on `objective`.

    This is the divergence case the `objective` parameter exists for: design
    doc section 8 gives the reason gradient availability differs by
    objective as "the REML penalty is not covered by the envelope theorem",
    so a term can be analytic for ML while only finite-differenceable for
    REML. Asserting both objectives against the *same* per_term data in one
    test is what catches a resolution that silently ignores its `objective`
    argument -- a stub hardcoded to always resolve against one objective
    would pass whichever single-objective assertion matches that hardcoded
    value and fail the other.

    Bug this catches: intersect_gradient_modes ignoring the `objective`
    parameter and resolving every objective identically.
    """
    per_term = [
        {
            Objective.ML: GradientMode.ANALYTIC,
            Objective.REML: GradientMode.FINITE_DIFFERENCE,
        }
    ]
    assert intersect_gradient_modes(per_term, Objective.ML) is GradientMode.ANALYTIC
    assert (
        intersect_gradient_modes(per_term, Objective.REML)
        is GradientMode.FINITE_DIFFERENCE
    )


def test_gradient_modes_missing_objective_defaults_to_finite_difference():
    """A term whose mapping omits the requested objective defaults to FD.

    Expected value determined independently from the `.get(objective,
    GradientMode.FINITE_DIFFERENCE)` default stated in the function's own
    implementation contract: a term that never declares a gradient mode for
    an objective is treated the same as an explicit FD entry for it, not as
    an error or as an implicit ANALYTIC.

    Bug this catches: a `KeyError` on a term that only declares gradients
    for one objective, or defaulting to ANALYTIC instead of FD, either of
    which would mishandle a term that never made a claim about REML at all.
    """
    per_term = [{Objective.ML: GradientMode.ANALYTIC}]
    assert (
        intersect_gradient_modes(per_term, Objective.REML)
        is GradientMode.FINITE_DIFFERENCE
    )


def test_gradient_modes_empty_composite_is_finite_difference():
    """An empty composite (no terms at all) is never reported as analytic.

    `all(...)` over zero terms is vacuously True in Python, so a composite
    with no terms and no explicit guard would report ANALYTIC purely because
    there is nothing to disagree with it -- an empty ProcessSpec claiming an
    analytic gradient it has zero terms' worth of evidence for. The
    function's `if modes and all(...)` guard exists specifically to close
    this vacuous-truth trap.

    Bug this catches: dropping the `modes and` guard, which would make an
    empty composite silently claim ANALYTIC instead of the safe FD default.
    """
    assert intersect_gradient_modes([], Objective.ML) is GradientMode.FINITE_DIFFERENCE
