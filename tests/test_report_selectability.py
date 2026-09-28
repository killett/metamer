"""Sub-phase 2f Task 5: selectability, and the three counts that are not one count.

**THE FIXTURES PLANT ARRAYS BECAUSE THE INTERESTING STATES ARE UNREACHABLE ON
DEMAND.** A point where one criterion can rank and another cannot, a store
carrying `SELECTED_UNSET`, a delta-IC that overflowed float32 -- none can be
produced by asking a real run nicely. The end-to-end arm is
`test_a_real_store_reports_its_own_denominator_and_no_defect`, which ties the
planted shape to what a run actually writes.
"""

from __future__ import annotations

import pathlib
import textwrap

import numpy as np
import pytest
import xarray as xr

from metamer.batch.run import run
from metamer.batch.store import N_VALID_UNSET, SELECTED_UNSET
from metamer.core.outcomes import Outcome
from metamer.report.reader import Completion, StoreView, read_store
from metamer.report.selectability import FLOAT32_CAVEAT, compute

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")

_CONFIG = """
data_uri = "{uri}"
variable = "sla"
signal_terms = ["constant", "trend"]
candidates = ["white", "white + matern12"]
criteria = ["aic", "hqic"]
"""


def _view(
    *,
    outcome: list[list[int]],
    n_valid: list[int],
    delta_ic: list[list[list[float]]],
    selected: list[list[int]],
    criteria: tuple[str, ...] = ("aic", "hqic"),
) -> StoreView:
    """A view over one row of points, with every selection array planted.

    `outcome` is per (point, candidate); `delta_ic` per (point, candidate,
    criterion); `selected` per (point, criterion).
    """
    codes = np.array([outcome], dtype=np.uint8)
    return StoreView(
        path=pathlib.Path("/nonexistent"),
        outcome=codes,
        delta_ic=np.array([delta_ic], dtype=np.float32),
        selected=np.array([selected], dtype=np.int16),
        n_valid=np.array([n_valid], dtype=np.int16),
        iterations=np.full(codes.shape, 65535, dtype=np.uint16),
        model_labels=tuple(f"m{i}" for i in range(codes.shape[-1])),
        criterion_labels=criteria,
        attrs={},
        completion=Completion(complete=1, total=1),
        spatial={},
        disagreements=(),
    )


def test_one_criterion_cannot_rank_a_point_and_only_its_contention_falls():
    """Converged is criterion-independent; contention is not.

    Expected values computed by hand from section 12.5's own construction:
    three candidates all `OK`, so converged is 3 under every criterion. Under
    AIC all three carry finite deltas, so contention is 3. Under HQIC one
    candidate's criterion value is undefined -- `n = n_obs - design_rank` gives
    `n = 2` at `n_obs = 6` against a rank-4 design -- so its delta is `+inf`,
    it is **ranked last rather than reclassified**, and contention is 2.

    Bug this catches: **contention computed off `n_valid`**, which is the
    conflation section 14.2 devotes a paragraph to. That implementation gives 3
    under both criteria and is indistinguishable from a correct one on any
    store where every fit happens to be rankable -- which is most of them.

    **CONVERGED MUST NOT MOVE**, and that is asserted too: a report that fixed
    contention by narrowing `n_valid` per criterion would break the store's own
    invariant, which `write.py` enforces by refusing two criteria that disagree
    about it.
    """
    ok = Outcome.OK.code
    section = compute(
        _view(
            outcome=[[ok, ok, ok]],
            n_valid=[3],
            # AIC: all finite. HQIC: the third is +inf -- scored, unrankable.
            delta_ic=[[[0.0, 0.0], [1.5, 2.0], [3.0, float("inf")]]],
            selected=[[0, 0]],
        )
    )
    aic, hqic = section.by_criterion

    assert section.converged == {3: 1}
    assert aic.contention == {3: 1}
    assert hqic.contention == {2: 1}
    assert hqic.unrankable_infinite == 1
    assert aic.unrankable_infinite == 0


def test_an_unwritten_selection_is_not_a_no_winner():
    """`-2` is "nothing wrote here" and `-1` is "nothing could be ranked".

    Expected values determined independently from the store's fill table:
    `SELECTED_UNSET` is `-2` and no-winner is `-1`, chosen to differ precisely
    so an interrupted write is distinguishable from a ranked point with no
    survivor. Two points, one of each, so each count is exactly 1.

    Bug this catches: `bool(-1)`-shaped identity-by-coincidence -- 2e's
    instrument finding 3 -- and its sibling `selected < 0`. **Both read the two
    states alike**, and both would report an interrupted run's unwritten cells
    as selection failures: an absence of information printed as a result, at
    the scale where a run is interrupted in most of the grid.
    """
    ok = Outcome.OK.code
    section = compute(
        _view(
            outcome=[[ok, ok], [ok, ok]],
            n_valid=[2, 2],
            delta_ic=[[[0.0, 0.0], [1.0, 1.0]], [[0.0, 0.0], [1.0, 1.0]]],
            selected=[[-1, -1], [SELECTED_UNSET, SELECTED_UNSET]],
        )
    )
    aic, _ = section.by_criterion

    assert aic.no_winner == 1
    assert aic.unwritten == 1


def test_a_delta_that_overflowed_float32_is_counted_unrankable_with_the_caveat():
    """The storage dtype can manufacture an unrankable, and the report says so.

    Expected value determined independently: `/selection/delta_ic` is float32
    and the ranker computes in float64, so a delta above ~3.4e38 becomes `inf`
    on write -- measured, with a `RuntimeWarning` and no error. The value
    planted here is finite in float64 and infinite once stored, so contention
    counts it out.

    Bug this catches: a contention count quietly biased by the storage dtype,
    which section 14.2 says is worth a test rather than a schema change. **And
    the caveat is the other half**: the store cannot tell this apart from a
    genuine `+inf`, so a report that counted it out silently would present a
    dtype artefact as a property of the data.

    **REACHABILITY IS NOT ESTABLISHED AND THE CAVEAT SAYS SO.** Whether real
    data produces a delta-IC above 3.4e38 has not been measured; this test
    plants one. A test for an unobserved state that does not say it is
    unobserved invites a later reader to reason about real stores from it --
    the same standing as the domain mask's true arm.
    """
    ok = Outcome.OK.code
    huge = 1e39  # finite in float64, `inf` once stored as float32
    with pytest.warns(RuntimeWarning):
        view = _view(
            outcome=[[ok, ok]],
            n_valid=[2],
            delta_ic=[[[0.0, 0.0], [huge, huge]]],
            selected=[[0, 0]],
        )
    assert np.isinf(view.delta_ic[0, 0, 1, 0]), "the fixture did not overflow"

    section = compute(view)
    aic, _ = section.by_criterion

    assert section.converged == {2: 1}
    assert aic.contention == {1: 1}
    assert aic.unrankable_infinite == 1
    assert section.caveat == FLOAT32_CAVEAT
    assert "has not been established" in section.caveat


def test_a_near_forced_choice_reads_clean_in_every_branch_count():
    """The failure mode section 14 names at its top, and why this section exists.

    Expected values computed by hand: twelve candidates, eleven failing the
    conditioning gate (`ILL_CONDITIONED_X`) and one `OK`. Every per-branch
    count is exactly what it should be and nothing about them is alarming --
    the point HAS a selection, and the winner converged. **Selectability is the
    only section that shows the choice was between one candidate and nothing.**

    Bug this catches: the report that section 14 was written to prevent -- a
    point where the selection is technically valid and effectively forced, and
    every other number on the page reads normal. `converged == 1` with twelve
    candidates offered is the signal, and it exists nowhere else.

    **AND `converged == 1` IS NOT PRINTED AS "FORCED"**, which the plan states
    as an invariant: this asserts the numbers, and what they mean is the
    reader's to judge with the denominator beside them.
    """
    ok = Outcome.OK.code
    bad = Outcome.ILL_CONDITIONED_X.code
    deltas = [[0.0, 0.0]] + [[float("nan"), float("nan")]] * 11
    section = compute(
        _view(
            outcome=[[ok] + [bad] * 11],
            n_valid=[1],
            delta_ic=[deltas],
            selected=[[0, 0]],
        )
    )
    aic, _ = section.by_criterion

    assert section.converged == {1: 1}
    assert aic.contention == {1: 1}
    assert aic.no_winner == 0
    assert aic.unrankable_not_scored == 11
    assert section.defects == ()


def test_the_identity_binds_this_section_to_the_per_candidate_table():
    """`converged == fitted - failed`, at every in-domain point.

    Expected values computed by hand: four candidates, one `OK`, two
    `DEGENERATE_HESSIAN`, one `SCREENED_OUT`. `is_fit_verdict` covers the first
    three, so fitted is 3 and failed is 2, giving `fitted - failed = 1` -- and
    `n_valid` must be 1. The planted store says 2.

    Bug this catches: the two sections describing different runs. Task 2's
    table and this one draw on different arrays, and nothing else compares
    them; a reader who subtracts one from the other and gets a surprise has no
    way to tell which is wrong. **The identity is exact because
    `is_fit_verdict` partitions into OK and the eight failures with no third
    case**, so this is arithmetic rather than a tolerance.

    **REPORTED, NOT RAISED** -- D6: a store with a contradiction is described.
    """
    planted = compute(
        _view(
            outcome=[
                [
                    Outcome.OK.code,
                    Outcome.DEGENERATE_HESSIAN.code,
                    Outcome.DEGENERATE_HESSIAN.code,
                    Outcome.SCREENED_OUT.code,
                ]
            ],
            n_valid=[2],
            delta_ic=[[[0.0, 0.0]] * 4],
            selected=[[0, 0]],
        )
    )

    assert planted.defects, "a store contradicting the per-candidate table read clean"
    assert "describing different runs" in planted.defects[0]
    assert "n_valid is 2" in planted.defects[0]


def test_the_denominator_excludes_points_out_of_domain_and_says_how_many():
    """Land is not a point a selection statement is about.

    Expected values computed by hand: three points, one of which is
    `NOT_APPLICABLE` for every candidate. So the denominator is 2 and the
    excluded population is 1.

    Bug this catches: a contention or no-winner fraction taken over the whole
    grid, which on a global run is dominated by land and reports a selection
    problem that is really a coastline. **The excluded count is printed too**,
    because a denominator that shrinks silently is the defect the branch table
    already refuses for `NOT_ATTEMPTED`.
    """
    ok = Outcome.OK.code
    na = Outcome.NOT_APPLICABLE.code
    section = compute(
        _view(
            outcome=[[ok, ok], [ok, ok], [na, na]],
            n_valid=[2, 2, N_VALID_UNSET],
            delta_ic=[[[0.0, 0.0], [1.0, 1.0]]] * 3,
            selected=[[0, 0], [0, 0], [SELECTED_UNSET, SELECTED_UNSET]],
        )
    )

    assert section.in_domain == 2
    assert section.out_of_domain == 1
    assert section.converged == {2: 2}
    assert section.unset == 0


def test_an_unwritten_n_valid_is_counted_and_never_binned_as_a_count():
    """`-1` is not a count of minus one converged candidates.

    Expected values computed by hand: two in-domain points, one written with
    2 and one never written. So the distribution holds only the written point
    and the unset count is 1.

    Bug this catches: `-1` binned as a value, which puts a negative key in a
    distribution of counts -- the same fill-value defect the primitives
    sections refuse for `n_valid` and `iterations`, arriving one section over.
    **A negative count is not a count**, which the plan states as an invariant.
    """
    ok = Outcome.OK.code
    section = compute(
        _view(
            outcome=[[ok, ok], [ok, ok]],
            n_valid=[2, N_VALID_UNSET],
            delta_ic=[[[0.0, 0.0], [1.0, 1.0]]] * 2,
            selected=[[0, 0], [SELECTED_UNSET, SELECTED_UNSET]],
        )
    )

    assert section.converged == {2: 1}
    assert section.unset == 1
    assert all(count >= 0 for count in section.converged)


def test_a_real_store_reports_its_own_denominator_and_no_defect():
    """The end-to-end arm: a run's own store, through the reader.

    Expected value determined independently: the config names two criteria, so
    the section carries two entries, and the grid is 4x4 with every point in
    domain. **The identity must hold on a store a run actually wrote** -- if it
    does not, the check is wrong rather than the store.

    Bug this catches: a planted-fixture shape the reader never returns, which
    would make every other test in this file green against a store nothing
    produces. **It is also the only arm that exercises the identity against
    real outcome codes**, where the OK/failure split is whatever the fits
    produced rather than whatever I typed.
    """
    section = compute(read_store(_real.path))

    assert len(section.by_criterion) == 2
    assert section.in_domain + section.out_of_domain == 16
    assert section.defects == (), section.defects
    assert sum(section.converged.values()) + section.unset == section.in_domain


class _Real:
    path: pathlib.Path


_real = _Real()


@pytest.fixture(scope="module", autouse=True)
def _build(tmp_path_factory: pytest.TempPathFactory) -> None:
    """One real store, built once for the end-to-end arm."""
    base = tmp_path_factory.mktemp("selectability")
    origin = np.datetime64("2000-01-01")
    times = np.array([origin + np.timedelta64(31 * i, "D") for i in range(24)])
    xr.Dataset(
        {"sla": (("time", "y", "x"), np.zeros((24, 4, 4), dtype="float32"))},
        coords={"time": times, "y": np.arange(4), "x": np.arange(4)},
    ).to_zarr(base / "in.zarr")
    config = base / "c.toml"
    config.write_text(textwrap.dedent(_CONFIG.format(uri=base / "in.zarr")))
    store = base / "out.zarr"
    run(config, store)
    _real.path = store
