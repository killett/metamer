"""The signal vocabulary: config strings to terms, and `k_beta`.

Blocked since Task 6 -- `k_beta` was unobtainable, so no tile could be sized and
`run()` could not iterate. These tests pin the two facts that make the unblocking
worth anything: the column count is not the term count, and the order is the
design's column order.
"""

from __future__ import annotations

import numpy as np
import pytest

from metamer.config.signal_terms import parse_signal_term, parse_signal_terms
from metamer.core.registry import signal_registry
from metamer.core.signal import (
    Annual,
    Constant,
    Offset,
    SemiAnnual,
    SignalSpec,
    Trend,
    k_beta,
)

YEARS = np.linspace(2000.0, 2020.0, 241)


def test_k_beta_counts_columns_and_not_terms() -> None:
    """2a's three signal terms are four design columns.

    `Harmonic` -- hence `Annual` -- contributes cos and sin, so
    `["constant", "trend", "annual"]` is three terms and **k_beta = 4**, which
    is design doc 9.4's worked value.

    Catches `len(spec.terms)`, which gives 3. That is not a crash but a
    plausible number: it silently shrinks `tile_side` and every memory figure
    derived from it, and 9.4's own worked example would stop reproducing.
    """
    spec = parse_signal_terms(["constant", "trend", "annual"])

    assert len(spec.terms) == 3
    assert k_beta(spec, YEARS) == 4


def test_k_beta_is_the_column_count_and_not_the_numerical_rank() -> None:
    """A rank-deficient design still has its full column count.

    `design_matrix` returns `(matrix, rank)`. Two identical annual terms give
    six columns of which only four are independent, so the count is **6** and
    the rank is 4.

    Catches taking the second element of that tuple: `k_beta` would shrink
    exactly where the design is degenerate, so the tile would grow on the
    inputs least able to afford it, and the error would look like a memory bug
    rather than a counting one.
    """
    spec = parse_signal_terms(["constant", "trend", "annual", "annual"])

    matrix, rank = spec.design_matrix(YEARS)

    assert matrix.shape[1] == 6
    assert rank == 4
    assert k_beta(spec, YEARS) == 6


def test_term_order_is_the_config_order_and_is_not_canonicalized() -> None:
    """Signal terms keep config order; noise candidates are sorted.

    `ProcessSpec` sorts canonically because a noise composition is a sum whose
    order carries no information. A signal spec's order **is** the design's
    column order, which is `beta`'s axis in the store.

    Catches a copy of the noise side's canonicalization: it would permute a
    stored `beta` against its own axis, with every array the right shape and
    every value finite -- and only for configs whose terms are written in a
    non-alphabetical order, which is most of them.
    """
    spec = parse_signal_terms(["trend", "constant", "annual"])

    assert [type(term).__name__ for term in spec.terms] == [
        "Trend",
        "Constant",
        "Annual",
    ]


def test_a_parameterized_term_takes_its_argument_after_a_colon() -> None:
    """`offset:2005.5` builds an `Offset` at that epoch.

    The `kind:argument` spelling is the one already in this config field:
    `model.PER_POINT_TERM_PREFIX` is `"regressor_field:"`.

    Catches a second syntax being invented for the same field, and catches the
    epoch being dropped -- an `Offset` at the default epoch is a step in the
    wrong place, which is a plausible design rather than an error.
    """
    term = parse_signal_term("offset:2005.5")

    assert isinstance(term, Offset)
    assert term.epoch == 2005.5


@pytest.mark.parametrize(
    ("entry", "message"),
    [
        ("offset", "requires an epoch"),
        ("offset:soon", "is not a number"),
        ("trend:2005", "takes no argument"),
        ("harmonic:0", "must be positive"),
        ("nosuch", "is not registered"),
        (":2005", "has no name"),
    ],
)
def test_each_malformed_entry_is_refused_with_its_own_diagnosis(
    entry: str, message: str
) -> None:
    """Every way an entry can be wrong names what is wrong with it.

    Expected messages are the diagnosis, never the user's own text: a message
    that quotes the input is satisfied by any error that echoes its argument.

    Catches a bare registry `KeyError` for a missing argument, and catches
    `harmonic:0`, which would otherwise divide by zero inside `columns` and
    produce a design full of NaN with no exception anywhere.
    """
    with pytest.raises(ValueError, match=message):
        parse_signal_terms([entry])


@pytest.mark.parametrize("name", ["expdecay", "logdecay", "regressor"])
def test_a_deferred_term_is_refused_as_deferred_and_not_as_a_typo(name: str) -> None:
    """The three unreachable term classes say why they are unreachable.

    `ExpDecay` and `LogDecay` are nonlinear and their `columns()` raises,
    naming Phase 4; `Regressor` needs an array, which is the per-point regressor
    regime refused at layer 3.

    Catches them being registered under reachable names: a config would parse,
    and the `NotImplementedError` would surface inside the design build, inside
    the tile loop, ten hours in. Catches equally a message calling them
    unknown, which sends the user looking for a spelling mistake.
    """
    with pytest.raises(ValueError, match="not available"):
        parse_signal_terms([name])

    assert name not in signal_registry


def test_an_empty_signal_spec_is_refused() -> None:
    """`signal_terms = []` is refused rather than producing a zero-column design.

    Catches a design with no columns, which `SignalSpec.design_info` handles
    without error -- rank 0, `gram_logdet` 0 -- so nothing downstream raises and
    the run produces a store whose `beta` axis has length zero, with no trend
    anywhere. The output the package exists to produce would simply be absent.
    """
    with pytest.raises(ValueError, match="signal_terms is empty"):
        parse_signal_terms([])


def test_the_registry_builds_the_same_terms_the_classes_do() -> None:
    """A registered factory returns the class it names, at its own defaults.

    Catches a factory wired to the wrong class -- `annual` returning
    `SemiAnnual` halves the modelled period, which fits, produces finite
    numbers, and is wrong about the seasonal cycle everywhere.
    """
    assert signal_registry["constant"](None) == Constant()
    assert signal_registry["trend"](None) == Trend()
    assert signal_registry["annual"](None) == Annual()
    assert Annual().period == 1.0
    semiannual = signal_registry["semiannual"](None)
    assert isinstance(semiannual, SemiAnnual)
    assert k_beta(SignalSpec([semiannual]), YEARS) == 2
