"""The ragged index builder: offsets, extents, and the coordinate columns.

**EVERY EXPECTED TABLE HERE IS WRITTEN OUT BY HAND.** `offsets[-1] + extents[-1]
== total` is a relation two consistently-wrong tables satisfy, and `np.cumsum` is
the builder's own construction -- see (i3) and (j) in the pre-flight.

**THE M=2 STORE FIXTURE CANNOT DISCRIMINATE THE TWO EXTENT FUNCTIONS' OFFSETS.**
`off_0` is 0 under every extent function and `off_1` is the first model's extent,
and `p = 1` is a fixed point of `p -> p(p+1)/2` (so is `p = 0`). At
`white` (p=1) beside `white + matern12` (p=3) both offset tables are `(0, 1)`.
The fixtures that separate them put a model with `p = 2` first.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import cast

import numpy as np
import pytest

import metamer
from metamer.batch.ragged import (
    COVARIANCE_STORAGE_ORDER,
    build_ragged_index,
    covariance_extent,
    covariance_slot_pairs,
    noise_extent,
    noise_param_coordinates,
)
from metamer.config.candidates import parse_candidate
from metamer.core.params import ParamSpec
from metamer.core.terms import ProcessSpec, TermSpec
from metamer.core.transforms import Identity, Log

# The 2a store fixture: design doc 12.3's M=2 with unequal p. `white` is p=1 and
# `white + matern12` is p=3, and the candidate strings are deliberately written in
# the order a user would write them rather than in canonical order.
STORE_CANDIDATES = ("white", "white + matern12")

# M=3, first model p=1: separates the two offset tables from the second model on.
THREE_CANDIDATES = ("white", "white + matern12", "matern32")

# M=2 with p=2 first: the smallest fixture whose offset tables differ, because 2 is
# not a fixed point of the triangular map.
CORRELATED_FIRST = ("matern32", "white")


def specs(candidates: tuple[str, ...]) -> tuple[ProcessSpec, ...]:
    """Parse candidate expressions the way `Config.process_specs()` does."""
    return tuple(parse_candidate(c) for c in candidates)


def test_noise_offsets_are_the_running_sum_of_free_parameter_counts() -> None:
    """The `/noise/` table at M=3, hand-derived from the parameter counts.

    `white` has one free parameter, `white + matern12` has three (matern12's
    sigma and rho, white's sigma), `matern32` has two. So the extents are
    (1, 3, 2), the offsets are (0, 1, 4) and P_total is 6.

    Catches `off_m = m * extents[0]` -- which is right at equal `p` and wrong
    here -- and an extent taken from `len(term.params)` rather than from the
    free-parameter count.
    """
    index = build_ragged_index(specs(THREE_CANDIDATES), noise_extent)

    assert index.extents == (1, 3, 2)
    assert index.offsets == (0, 1, 4)
    assert index.total == 6


def test_covariance_offsets_differ_from_noise_offsets_at_the_same_candidates() -> None:
    """The packed-lower-triangle table at M=3, hand-derived.

    A covariance block for a model with `p` free parameters stores `p(p+1)/2`
    values: 1 for p=1, 6 for p=3, 3 for p=2. So the extents are (1, 6, 3), the
    offsets are (0, 1, 7) and the total is 10.

    Catches one offset table computed and reused for both ragged axes. Both
    tables start (0, 1) here, so the discrimination is at the third model.
    """
    index = build_ragged_index(specs(THREE_CANDIDATES), covariance_extent)

    assert index.extents == (1, 6, 3)
    assert index.offsets == (0, 1, 7)
    assert index.total == 10


def test_the_extent_functions_separate_at_the_first_offset_when_p_is_not_one() -> None:
    """With `matern32` (p=2) first, the two tables differ from `off_1` onward.

    Hand-derived: noise extents (2, 1), offsets (0, 2), total 3; covariance
    extents (3, 1), offsets (0, 3), total 4.

    Catches a reused offset table at the earliest position it can be caught,
    which is what the prescribed `white`-first fixture cannot do: `off_1` is the
    first model's extent, and `p = 1` and `p = 0` are the fixed points of
    `p -> p(p+1)/2`.
    """
    noise = build_ragged_index(specs(CORRELATED_FIRST), noise_extent)
    covariance = build_ragged_index(specs(CORRELATED_FIRST), covariance_extent)

    assert noise.offsets == (0, 2)
    assert noise.extents == (2, 1)
    assert noise.total == 3
    assert covariance.offsets == (0, 3)
    assert covariance.extents == (3, 1)
    assert covariance.total == 4


def test_the_store_fixture_tables_and_the_total_the_documents_get_wrong() -> None:
    """The M=2 fixture Task 8 writes, both extent functions, hand-derived.

    `P_total = 4` for `/noise/`. The covariance total is `1 + 6 = 7`, NOT the
    `4 + 6 = 10` carried by design doc 12.3, the 2a plan and PROGRESS.md: 10 is
    `P_total(P_total+1)/2`, the triangle of the flattened total, which is the
    one-table-reused error those documents exist to warn about.

    Catches Task 8 sizing a `/detail/` axis from the documents' number, and
    pins the values Task 8's store creation consumes.
    """
    noise = build_ragged_index(specs(STORE_CANDIDATES), noise_extent)
    covariance = build_ragged_index(specs(STORE_CANDIDATES), covariance_extent)

    assert noise.extents == (1, 3)
    assert noise.offsets == (0, 1)
    assert noise.total == 4
    assert covariance.extents == (1, 6)
    assert covariance.offsets == (0, 1)
    assert covariance.total == 7


def test_covariance_extent_equals_the_enumerated_lower_triangle() -> None:
    """`covariance_extent` counts exactly the pairs `covariance_slot_pairs` yields.

    The enumeration shares no derivation with `p(p+1)/2` -- it walks the index
    pairs a packer would visit -- so it is an independent oracle for the formula
    (pre-flight (j)).

    Catches `p(p-1)/2` (the strict triangle, which drops the diagonal and is
    right only at p=0) and an off-by-one in either.
    """
    for p, expected in ((0, 0), (1, 1), (2, 3), (3, 6), (4, 10), (5, 15)):
        assert covariance_extent(_spec_with_free_params(p)) == expected
        assert len(covariance_slot_pairs(p)) == expected


def test_covariance_slot_pairs_produce_the_declared_storage_order() -> None:
    """The declared order is produced by code, not merely named in a string.

    Row-major lower triangle at p=3 is (0,0), (1,0), (1,1), (2,0), (2,1), (2,2).

    Catches the storage order being an attrs string with nothing producing it --
    which is the failure design doc 12.3 names as this group's worst, because a
    consumer unpacking row-major-lower as column-major-lower gets a matrix that
    is still symmetric, often still positive definite, and wrong with no symptom.
    """
    assert COVARIANCE_STORAGE_ORDER == "row-major-lower"
    assert covariance_slot_pairs(3) == (
        (0, 0),
        (1, 0),
        (1, 1),
        (2, 0),
        (2, 1),
        (2, 2),
    )


def test_block_returns_the_contiguous_slice_a_reader_would_take() -> None:
    """Model m's block is `theta[..., off_m : off_m + p_m]`.

    At M=3 the blocks are slice(0, 1), slice(1, 4), slice(4, 6).

    Catches `slice(off, p)` -- which is correct only for model 0 and silently
    returns a short or empty block for every other model.
    """
    index = build_ragged_index(specs(THREE_CANDIDATES), noise_extent)

    assert index.block(0) == slice(0, 1)
    assert index.block(1) == slice(1, 4)
    assert index.block(2) == slice(4, 6)


def test_an_empty_candidate_list_is_refused() -> None:
    """M = 0 is refused rather than producing an empty index.

    A store with no models makes every array constant across the axis every
    downstream assertion compares along -- the cancellation rule applied to an
    axis length.

    Catches an empty index reaching store creation, where the resulting
    zero-length model axis makes the whole selection suite vacuously green.
    """
    with pytest.raises(ValueError, match="at least one candidate"):
        build_ragged_index((), noise_extent)


def test_a_negative_extent_is_refused() -> None:
    """An extent function returning a negative value is refused.

    Catches negative offsets: the running sum stays arithmetically consistent,
    `block()` returns a reversed slice, and a region write silently addresses the
    wrong part of the ragged axis.
    """
    with pytest.raises(ValueError, match="negative"):
        build_ragged_index(specs(STORE_CANDIDATES), lambda spec: -1)


def test_a_non_integral_extent_is_refused() -> None:
    """An extent function returning a float is refused even when it is whole.

    Catches `p * (p + 1) / 2` written with true division: it is exact for these
    sizes, so every total is right and every offset is a float, and the
    coordinate arrays land in a float dtype that no integer index can slice with.
    """

    def whole_valued_float(spec: ProcessSpec) -> int:
        """Model an extent written with `/` rather than `//`, exact at this size."""
        return cast("int", 3.0)

    with pytest.raises(ValueError, match="integer"):
        build_ragged_index(specs(STORE_CANDIDATES), whole_valued_float)


def _spec_with_free_params(p: int) -> ProcessSpec:
    """Build a spec with exactly `p` free parameters, for the extent oracle.

    Args:
        p: Number of free parameters the returned spec declares.

    Returns:
        A single-term process spec whose term has `p` free parameters.
    """
    params = {
        f"a{i}": ParamSpec(
            name=f"a{i}",
            default=1.0,
            transform=Log(),
            bounds=(0.0, np.inf),
            diagnostic_limits=(1e-8, 1e8),
        )
        for i in range(p)
    }
    return ProcessSpec((TermSpec(kind="synthetic", params=params),))


def test_slot_order_follows_the_optimizer_vector_and_not_the_config_string() -> None:
    """The columns describe `free_param_index`'s layout, term by term.

    `ProcessSpec` sorts `matern12` before `white`, so `"white + matern12"` has
    free parameters (matern12 sigma, matern12 rho, white sigma) in that order --
    measured against `free_param_index`, which is the single source of truth for
    the vector `fit` produces.

    Catches a builder that walks the config expression or `sorted(term.params)`:
    every array keeps its shape and every `theta` slot is labelled with another
    parameter's name, which is the whole failure this group can have.
    """
    coords = noise_param_coordinates(specs(STORE_CANDIDATES))

    assert coords.term == ("white[0]", "matern12[0]", "matern12[0]", "white[0]")
    assert coords.name == ("sigma", "sigma", "rho", "sigma")


def test_the_model_column_is_the_canonical_label_not_the_config_string() -> None:
    """`noise_param_model` is an identity read off the spec, not the request.

    The config asks for `"white + matern12"`; the spec's canonical label is
    `"matern12[0] + white[0]"`. They differ in order on this fixture, which is
    what makes the distinction testable at all.

    Catches the config string being copied through: a builder that never looks
    at a `ProcessSpec` passes every count assertion and mislabels the model any
    time canonicalization reorders a composition.
    """
    coords = noise_param_coordinates(specs(STORE_CANDIDATES))

    assert coords.model == (
        "white[0]",
        "matern12[0] + white[0]",
        "matern12[0] + white[0]",
        "matern12[0] + white[0]",
    )


def test_model_index_joins_each_slot_to_the_model_axis() -> None:
    """`noise_param_model_index` is the integer join key to the `m` axis.

    Hand-derived from the extents (1, 3): slot 0 belongs to model 0 and slots
    1-3 to model 1.

    Catches an index derived from the label rather than from the block
    boundaries -- two candidates with the same canonical label would then share
    a key, and the store's `m` axis is positional.
    """
    coords = noise_param_coordinates(specs(STORE_CANDIDATES))

    assert list(coords.model_index) == [0, 1, 1, 1]
    assert coords.model_index.dtype == np.dtype(np.int16)


def test_unit_and_transform_are_read_from_the_param_spec() -> None:
    """Both columns come from the `ParamSpec`, not from a table keyed on name.

    Measured on the shipped families: every parameter uses `Log`, and only `rho`
    declares a unit (`"time"`), so sigma's unit is the empty string. The
    constructed spec then varies both away from those values.

    Catches a hardcoded mapping: it agrees with the families as they stand today
    and silently mislabels the first family that declares anything else.
    """
    coords = noise_param_coordinates(specs(STORE_CANDIDATES))

    assert coords.unit == ("", "", "time", "")
    assert coords.transform == ("Log", "Log", "Log", "Log")

    constructed = ProcessSpec(
        (
            TermSpec(
                kind="synthetic",
                params={
                    "level": ParamSpec(
                        name="level",
                        default=0.0,
                        transform=Identity(),
                        bounds=(-np.inf, np.inf),
                        diagnostic_limits=(-1e8, 1e8),
                        unit="K",
                    )
                },
            ),
        )
    )
    other = noise_param_coordinates((constructed,))

    assert other.unit == ("K",)
    assert other.transform == ("Identity",)


def test_a_fixed_parameter_occupies_no_slot() -> None:
    """A `fixed=True` parameter is excluded from the extent and the columns.

    Two declared parameters with one fixed gives extent 1 and a single column
    entry naming the free one.

    Catches an extent taken from `len(term.params)`: `P_total` would then exceed
    the length of the vector `fit` returns, and every slot after the fixed one
    would be written one place to the right.
    """
    spec = ProcessSpec(
        (
            TermSpec(
                kind="synthetic",
                params={
                    "free": ParamSpec(
                        name="free",
                        default=1.0,
                        transform=Log(),
                        bounds=(0.0, np.inf),
                        diagnostic_limits=(1e-8, 1e8),
                    ),
                    "frozen": ParamSpec(
                        name="frozen",
                        default=1.0,
                        transform=Log(),
                        bounds=(0.0, np.inf),
                        diagnostic_limits=(1e-8, 1e8),
                        fixed=True,
                    ),
                },
            ),
        )
    )

    coords = noise_param_coordinates((spec,))

    assert coords.index.extents == (1,)
    assert coords.name == ("free",)


def test_a_long_or_non_ascii_value_survives_intact() -> None:
    """Coordinate values are plain strings, so neither is truncated or refused.

    MEASURED 2026-08-12: `np.array(["x" * 40], dtype="S32")` returns a 32-byte
    value with no error, and `np.array(["\u00b5m"], dtype="S32")` raises
    `UnicodeEncodeError`. The store writes the v3-specified `string` dtype rather
    than fixed-width bytes -- see the module docstring -- so both hazards are
    gone and this pins their absence.

    Catches a fixed-width encoding creeping back in: a 33-character kind would
    come back truncated to 32, which still reads as a valid label, and a
    micrometre unit would raise instead of round-tripping.
    """
    long_kind = "k" * 33
    spec = ProcessSpec(
        (
            TermSpec(
                kind=long_kind,
                params={
                    "sigma": ParamSpec(
                        name="sigma",
                        default=1.0,
                        transform=Log(),
                        bounds=(0.0, np.inf),
                        diagnostic_limits=(1e-8, 1e8),
                        unit="\u00b5m",
                    )
                },
            ),
        )
    )

    coords = noise_param_coordinates((spec,))

    assert coords.term == (f"{long_kind}[0]",)
    assert len(coords.term[0]) == 36
    assert coords.unit == ("\u00b5m",)


def test_a_layout_disagreeing_with_the_count_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The two independent derivations of `p_m` are asserted to agree.

    `ProcessSpec.n_theta()` sums each term's `n_free()`; `free_param_index()`
    builds the list. `n_theta`'s docstring says the separation is deliberate, so
    the builder checks them against each other rather than collapsing them. The
    disagreement is forced here because nothing in the tree can produce it.

    Catches the check's absence: a coordinate column shorter than the ragged axis
    it describes, so every slot after the divergence is labelled with the next
    parameter's name -- shapes intact, values finite, nothing raised.
    """
    import metamer.batch.ragged as ragged

    monkeypatch.setattr(ragged, "free_param_index", lambda spec: ())

    with pytest.raises(ValueError, match="disagree"):
        noise_param_coordinates(specs(STORE_CANDIDATES))


def test_the_legend_enumerates_each_column_from_the_column_itself() -> None:
    """The legend's codes are positions in the distinct sorted values.

    Hand-derived for the M=2 fixture: transforms are all `Log`, units are the
    empty string and `time`, names are `rho` and `sigma`.

    Catches a legend assembled from a hardcoded vocabulary rather than from the
    arrays it explains -- it would agree today and silently omit the first value
    a new family introduces, and the legend is the redundancy a reader without
    metamer falls back on.
    """
    legend = noise_param_coordinates(specs(STORE_CANDIDATES)).legend()

    assert legend["transform"] == ("Log",)
    assert legend["unit"] == ("", "time")
    assert legend["name"] == ("rho", "sigma")
    assert legend["term"] == ("matern12[0]", "white[0]")
    assert legend["model"] == ("matern12[0] + white[0]", "white[0]")


@pytest.mark.slow
def test_the_columns_are_byte_identical_across_processes() -> None:
    """The five columns do not depend on `PYTHONHASHSEED`.

    These columns are written once at store creation and never re-derived, and
    the store is resumed by a different process, so a seed-dependent order is
    invisible to every same-process test and to mutation testing, which shares
    one frozen seed.

    Catches a set or a hash-ordered mapping entering the layout: two runs would
    label the same `theta` differently with no error anywhere.
    """
    program = textwrap.dedent(
        """
        from metamer.batch.ragged import noise_param_coordinates
        from metamer.config.candidates import parse_candidate

        coords = noise_param_coordinates(
            tuple(parse_candidate(c) for c in ("white", "white + matern12"))
        )
        print(
            "|".join(
                ",".join(column)
                for column in (
                    coords.model,
                    coords.term,
                    coords.name,
                    coords.unit,
                    coords.transform,
                )
            )
        )
        """
    )
    # MEASURED: inheriting the environment is not enough. pytest resolves its
    # `pythonpath = ["src"]` against the rootdir, while the ambient `PYTHONPATH=src`
    # pixi sets is relative to the CWD -- so this subprocess passed from /workspace
    # and failed from /tmp while every in-process test stayed green. The path is
    # taken from the imported package instead, which is cwd-independent and works
    # whether metamer is on the path or installed.
    source_root = str(Path(metamer.__file__).resolve().parents[1])
    runs = [
        subprocess.run(
            [sys.executable, "-c", program],
            capture_output=True,
            text=True,
            check=True,
            env={**os.environ, "PYTHONHASHSEED": seed, "PYTHONPATH": source_root},
        ).stdout
        for seed in ("1", "2")
    ]

    assert runs[0] == runs[1]
    assert runs[0].startswith("white[0],matern12[0] + white[0]")
