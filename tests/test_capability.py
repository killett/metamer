import pytest

from metamer.core.capability import (
    CostClass,
    EngineId,
    IncompatibleSpecError,
    intersect_engine_costs,
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
