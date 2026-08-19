"""The tile write path, the status/value invariant, and the two fixture points.

**THE INVARIANT'S UNIT TESTS RUN ON CONSTRUCTED ARRAYS, NOT ON FITS.** A fit
takes seconds per series and produces whichever outcomes it produces; the
invariant has to be exercised on pairings a fit may never emit, including the
ones it emits only when it is broken.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest
import xarray as xr

from metamer.batch import store, write
from metamer.batch.ragged import build_ragged_index, noise_extent
from metamer.batch.run import run
from metamer.config import load
from metamer.core.outcomes import Outcome
from metamer.core.transforms import Log
from tests.reader_probe import run_reader

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")

_CONFIG = """
data_uri = "{uri}"
variable = "sla"
signal_terms = ["constant", "trend", "annual"]
candidates = ["white", "white + matern12"]
criteria = ["aic", "hqic"]
memory_budget_gb = 0.01
objective = "{objective}"
"""

OK = Outcome.OK.code
DEAD = Outcome.DEGENERATE_HESSIAN.code


def _input(
    tmp_path: Path,
    *,
    n_y: int = 2,
    n_x: int = 2,
    n_time: int = 60,
    holes: dict[tuple[int, int], int] | None = None,
) -> str:
    """A real zarr input of white noise, optionally punched with gaps.

    Args:
        tmp_path: Destination directory.
        n_y: Grid rows.
        n_x: Grid columns.
        n_time: Series length.
        holes: `(y, x) -> how many leading timesteps to KEEP`; every later
            sample at that point is NaN. This is how a point gets a small
            `n_obs` without changing the design, which is shared.

    Returns:
        The store URI.
    """
    rng = np.random.default_rng(0)
    values = rng.standard_normal((n_time, n_y, n_x)).astype("float32")
    for (y, x), keep in (holes or {}).items():
        values[keep:, y, x] = np.nan
    origin = np.datetime64("2000-01-01")
    axis = np.array([origin + np.timedelta64(31 * i, "D") for i in range(n_time)])
    xr.Dataset(
        {"sla": (("time", "y", "x"), values)},
        coords={
            "time": axis,
            "y": np.arange(n_y, dtype="float64"),
            "x": np.arange(n_x, dtype="float64"),
        },
    ).to_zarr(tmp_path / "in.zarr")
    return str(tmp_path / "in.zarr")


def _config(tmp_path: Path, uri: str, *, objective: str = "ml") -> Path:
    path = tmp_path / "c.toml"
    path.write_text(_CONFIG.format(uri=uri, objective=objective))
    return path


# --------------------------------------------------------------------------
# The invariant, on constructed arrays
# --------------------------------------------------------------------------


def test_a_nan_beside_an_ok_status_is_refused() -> None:
    """A fitted candidate with a missing value is a defect, not a gap.

    Catches a write path that fills a slot it failed to compute: the store
    would carry `OK` beside NaN, and every consumer that trusts the status --
    which is what the status is for -- would treat the absence as a value.
    """
    outcome = np.array([[OK, OK]], dtype=np.uint8)

    with pytest.raises(write.InvariantError, match="NaN never coexists with OK"):
        write.check_status_invariant(outcome, {"log_lik": np.array([[-1.0, np.nan]])})


def test_a_finite_value_beside_a_failed_status_is_refused() -> None:
    """A non-OK cell must be NaN in every one of its slots.

    Catches a partially written failure -- the commonest shape of which is an
    array left holding the previous candidate's numbers, which read as valid
    and are attributed to a fit that did not happen.
    """
    outcome = np.array([[OK, DEAD]], dtype=np.uint8)

    with pytest.raises(write.InvariantError, match="degenerate_hessian"):
        write.check_status_invariant(outcome, {"log_lik": np.array([[-1.0, -2.0]])})


def test_minus_infinity_is_refused_even_where_the_status_agrees() -> None:
    """`-inf` never reaches the store, whatever the status says.

    A failed candidate at `-inf` satisfies "not finite", so the invariant's own
    two directions would both pass.

    Catches the optimizer's internal barrier value being written: it is a
    finite-looking sentinel that survives an `isfinite` check downstream, and it
    ranks as a real, very bad log-likelihood rather than as an absence.
    """
    outcome = np.array([[OK, DEAD]], dtype=np.uint8)

    with pytest.raises(write.InvariantError, match="-inf"):
        write.check_status_invariant(outcome, {"log_lik": np.array([[-1.0, -np.inf]])})


def test_the_trend_exemption_applies_only_when_the_caller_declares_it() -> None:
    """`n_eff_trend` may be NaN beside OK only if the design has no trend.

    `n_eff_trend` is documented NaN where the design carries no trend column.
    That is a designed value, not a defect -- but only under that design.

    Catches the exemption being made unconditional, which would excuse a real
    `n_eff_trend` failure at every point of every run that does have a trend;
    and catches it being omitted, which refuses every legitimate trend-free
    design.
    """
    outcome = np.array([[OK, OK]], dtype=np.uint8)
    values: dict[str, Any] = {"n_eff_trend": np.array([[np.nan, np.nan]])}

    write.check_status_invariant(
        outcome, values, exempt_when_ok=frozenset({"n_eff_trend"})
    )
    with pytest.raises(write.InvariantError, match="n_eff_trend"):
        write.check_status_invariant(outcome, values)


def test_the_exemption_does_not_reach_the_other_direction() -> None:
    """An exempt array still may not be finite where the status failed.

    Catches an exemption implemented as "skip this array", which would let a
    failed candidate carry a finite `n_eff_trend` -- a number attributed to a
    fit that did not converge.
    """
    outcome = np.array([[DEAD, DEAD]], dtype=np.uint8)

    with pytest.raises(write.InvariantError, match="n_eff_trend"):
        write.check_status_invariant(
            outcome,
            {"n_eff_trend": np.array([[1.0, np.nan]])},
            exempt_when_ok=frozenset({"n_eff_trend"}),
        )


# --------------------------------------------------------------------------
# The point-level aggregate, whose rule no document states
# --------------------------------------------------------------------------


def test_a_point_is_ok_if_any_candidate_fitted() -> None:
    """`point_outcome` answers "is this point usable", so OK wins.

    Catches a bare `merge_outcomes` over the model axis: `OUTCOME_PRECEDENCE`
    ranks OK **last**, so merging would report `degenerate_hessian` for a point
    that has a perfectly good white-noise fit -- and the failure map would show
    a disaster wherever the harder candidate struggled.
    """
    codes = np.array([[OK, DEAD], [DEAD, OK], [DEAD, DEAD]], dtype=np.uint8)

    assert list(write.point_outcomes(codes)) == [OK, OK, DEAD]


def test_a_point_where_all_candidates_failed_reports_the_earliest_cause() -> None:
    """Mixed failures resolve through the ladder already declared, not a new one.

    `OUTCOME_PRECEDENCE` puts `INSUFFICIENT_DATA` before `RANK_DEFICIENT_X`:
    too few samples is the earlier cause, and a design that is deficient
    *because* the data is absent should not be reported as a design fault.

    Catches a second precedence being invented here -- two ladders in one
    codebase disagree the first time either is extended.
    """
    codes = np.array(
        [[Outcome.RANK_DEFICIENT_X.code, Outcome.INSUFFICIENT_DATA.code]],
        dtype=np.uint8,
    )

    assert write.point_outcomes(codes)[0] == Outcome.INSUFFICIENT_DATA.code


# --------------------------------------------------------------------------
# End to end: the write path against a real store
# --------------------------------------------------------------------------


@pytest.mark.slow
def test_a_run_writes_every_group_and_the_ragged_blocks_line_up(tmp_path):
    """One run, one tile, and every group readable afterwards.

    White noise is fitted with `white` and `white + matern12`. The second
    candidate is over-parameterized for the data, so the run naturally produces
    both outcomes -- which is what makes the store worth reading.

    Hand-derived: `/noise/` is `P_total = 4` wide with model 0 occupying slot 0
    and model 1 slots 1-3, so a point whose second candidate failed has a finite
    slot 0 and three NaN, and **that NaN means the fit failed, never padding**.

    Catches the ragged un-padding being written model-major (which would put
    matern12's sigma in white's slot) and catches a group left unwritten.
    """
    uri = _input(tmp_path)
    report = run(_config(tmp_path, uri), tmp_path / "out.zarr")

    assert report.k_beta == 4
    assert report.tiles_written == 1

    status = xr.open_zarr(tmp_path / "out.zarr", group="status")
    noise = xr.open_zarr(tmp_path / "out.zarr", group="noise")
    outcome = status["outcome"].values
    assert np.any(outcome == OK)
    assert not np.any(outcome == Outcome.NOT_ATTEMPTED.code)

    theta = noise["theta"].values
    ok_first = outcome[..., 0] == OK
    assert np.all(np.isfinite(theta[ok_first, 0]))
    failed_second = outcome[..., 1] != OK
    assert np.all(np.isnan(theta[failed_second][:, 1:]))
    assert list(noise["noise_param_term"].values) == [
        "white[0]",
        "matern12[0]",
        "matern12[0]",
        "white[0]",
    ]


@pytest.mark.slow
def test_a_point_with_one_surviving_candidate_renormalizes_over_it(tmp_path):
    """The case that reads as confident selection and is not.

    Fitting `white + matern12` to white noise leaves it degenerate at most
    points, so those points have `n_valid = 1` and a weight vector that sums to
    1 over the single survivor -- an apparently unanimous model choice made from
    one candidate.

    **The recorded recipe for this point cannot work and the test says why.**
    `PROGRESS.md` prescribes an offset inside a gap, "a breakpoint with no
    support for one candidate's design". In v1 the signal spec is fixed and
    `fit.py` builds `design_info` ONCE before the candidate loop, so every
    design-derived outcome is identical for every model: a design failure
    cannot distinguish candidates. The reachable construction is an
    optimizer-stage failure, which is what this fixture uses.

    Catches weights normalized over all M rather than over the survivors, which
    would give the failed candidate a share and the survivor less than 1.
    """
    uri = _input(tmp_path)
    run(_config(tmp_path, uri), tmp_path / "out.zarr")

    selection = xr.open_zarr(tmp_path / "out.zarr", group="selection")
    n_valid = selection["n_valid"].values
    weight = selection["weight"].values

    assert np.any(n_valid == 1), "fixture produced no single-survivor point"
    single = n_valid == 1
    weights_there = weight[single][..., 0]
    assert np.allclose(np.nansum(weights_there, axis=-1), 1.0)
    assert np.count_nonzero(weights_there > 0) == np.count_nonzero(single)


@pytest.mark.slow
def test_a_point_can_be_ok_while_one_criterion_cannot_rank_it(tmp_path):
    """Every fit OK, and HQIC undefined -- the `/selection/` exemption, live.

    Under REML `n = n_obs - design_rank`. A point with **6** valid samples
    against the four-column design gives `n = 2`, and HQIC is `2k ln ln n`,
    undefined for `n <= e`. AIC does not read `n` at all and ranks the point
    fine.

    **The ML route cannot produce this and that is why REML is used.** Under ML
    `n = n_obs`, so reaching `n <= e` needs `n_obs <= 2`, and the design
    precheck refuses a series with fewer rows than its four columns long before
    anything is scored -- the point would be `INSUFFICIENT_DATA`, not `OK`.

    Catches a criterion-specific failure being folded into the outcome ladder:
    `outcome` has no `c` axis, so doing that would make a criterion-independent
    array depend on which criterion was requested.
    """
    uri = _input(tmp_path, holes={(0, 0): 6})
    run(_config(tmp_path, uri, objective="reml"), tmp_path / "out.zarr")

    status = xr.open_zarr(tmp_path / "out.zarr", group="status")
    selection = xr.open_zarr(tmp_path / "out.zarr", group="selection")
    criteria = [str(name) for name in selection["c"].values]

    assert criteria == ["aic", "hqic"]
    point = (0, 0)
    assert status["outcome"].values[point][0] == OK
    assert np.isfinite(selection["ic_best"].values[point][criteria.index("aic")])
    assert np.isnan(selection["ic_best"].values[point][criteria.index("hqic")])
    assert selection["selected"].values[point][criteria.index("hqic")] == -1


@pytest.mark.slow
def test_the_warmstart_round_trips_back_to_the_stored_natural_parameters(tmp_path):
    """`/warmstart/` is written and unread in 2a, so it gets its own guard.

    The stored unconstrained theta-hat, pushed forward through each parameter's
    own `Bijector`, must reproduce `/noise/theta`. Every shipped parameter uses
    `Log`, so the map is `exp`.

    Catches the two ways an unread array goes wrong silently: the natural
    values being written into it (the round trip would then be `exp` of an
    already-natural value), and the ragged un-padding being applied with a
    different offset table than `/noise/` got. 2c would inherit a wrong layout
    underneath a feature that has its own bugs.
    """
    uri = _input(tmp_path)
    run(_config(tmp_path, uri), tmp_path / "out.zarr")

    noise = xr.open_zarr(tmp_path / "out.zarr", group="noise")
    warmstart = xr.open_zarr(tmp_path / "out.zarr", group="warmstart")
    natural = noise["theta"].values
    unconstrained = warmstart["theta_unconstrained"].values

    assert list(noise["noise_param_transform"].values) == ["Log"] * 4
    finite = np.isfinite(natural)
    assert finite.any()
    assert np.allclose(Log().forward(unconstrained[finite]), natural[finite], rtol=1e-6)


@pytest.mark.slow
def test_the_same_fits_are_ranked_under_both_criteria_without_refitting(tmp_path):
    """C rankings from one `CandidateScores`, which is 12.8's claim in miniature.

    AIC and HQIC differ only in their penalty, so a point ranked under both must
    carry two different `ic_best` values from one set of fits.

    Catches `fit` being called once per criterion -- which at 10^7 points is a
    second full run to add a criterion, the exact thing the three-hash split
    exists to prevent -- and catches the second criterion silently reusing the
    first's ranking, which would leave the two `ic_best` slices identical.
    """
    uri = _input(tmp_path)
    run(_config(tmp_path, uri), tmp_path / "out.zarr")

    selection = xr.open_zarr(tmp_path / "out.zarr", group="selection")
    ic_best = selection["ic_best"].values
    ranked = np.isfinite(ic_best).all(axis=-1)

    assert ranked.any()
    assert not np.allclose(ic_best[ranked][:, 0], ic_best[ranked][:, 1])


@pytest.mark.slow
def test_the_runner_fits_through_the_engine_seam_it_is_given(tmp_path):
    """The `engine=` seam reaches the fit, proved by a stub that raises.

    **THIS IS THE POSITIVE CONTROL FOR EVERY LATER "no fit ran".** A stub that
    is never wired in and a stub that is never reached produce byte-identical
    green results, so Task 12's assertion is unfalsifiable until something shows
    the seam is live.

    Catches a runner that builds its engine internally from the config, which
    Task 4 deliberately avoided adding because no test there could make it bite.
    """
    uri = _input(tmp_path)
    config_path = _config(tmp_path, uri)

    from tests.conftest import RaisingStubEngine

    with pytest.raises(RuntimeError):
        run(config_path, tmp_path / "out.zarr", engine=RaisingStubEngine())


# --------------------------------------------------------------------------
# Refusals
# --------------------------------------------------------------------------


def test_a_tile_whose_point_count_disagrees_with_the_result_is_refused(tmp_path):
    """The write pairs points and series positionally, so the counts must match.

    Catches an off-by-one tile or a result assembled in a different order: the
    write would reshape without complaint and every point in the tile would
    carry a neighbour's fit -- shapes intact, values finite, nothing raised.
    """
    from metamer.batch.tiling import Tile

    uri = _input(tmp_path)
    config = load(_config(tmp_path, uri))
    index = build_ragged_index(config.process_specs(), noise_extent)

    class _Result:
        outcome = np.zeros((3, 2), dtype=np.uint8)

    with pytest.raises(ValueError, match="row-major order"):
        write.write_tile(
            tmp_path / "nowhere.zarr",
            Tile(y_start=0, y_stop=2, x_start=0, x_stop=2),
            _Result(),  # type: ignore[arg-type]
            criteria=config.criteria,
            index=index,
            has_trend=True,
        )


@pytest.mark.slow
def test_the_store_still_opens_without_metamer_after_a_run(tmp_path):
    """Exit criterion 3, against a store with data in it rather than fill.

    Task 8 checked the empty store. A store that has been written to is the one
    a consumer actually receives, and the arrays it reads are the compressed,
    sharded ones rather than pure metadata.

    Catches a write path that writes something xarray can only decode with
    metamer's help -- and the control is `tests/reader_probe.py`, which blocks
    the import rather than asserting the package happens to be absent.
    """
    uri = _input(tmp_path)
    run(_config(tmp_path, uri), tmp_path / "out.zarr")

    result = run_reader(
        """
        import sys
        import numpy as np, xarray as xr
        noise = xr.open_zarr(sys.argv[1], group="noise")
        print(int(np.isfinite(noise["theta"].values).sum()))
        print(list(noise["noise_param_name"].values))
        """,
        str(tmp_path / "out.zarr"),
    )

    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert int(lines[0]) > 0
    assert lines[1] == "['sigma', 'sigma', 'rho', 'sigma']"


def test_schema_version_moved_when_the_outcome_vocabulary_grew() -> None:
    """Adding `Outcome` members bumps the store's schema version.

    `outcomes._CODES` makes that rule explicit, and the `/status/` legend is
    written from the enum at creation, so a v1 store and a v2 store disagree
    about the vocabulary even though no 2a run can emit either new code.

    **RE-POINTED TWICE, AND THE SECOND TIME THE ASSERTION ITSELF WAS THE BUG.**
    It read `== 2`, then `== 3`, and it would have read `== 4` -- failing at
    every bump for a reason that has nothing to do with its subject, and
    teaching the next author that the fix for this test is to edit the number.
    **The subject here is "the members landed WITH a bump", so the bound is what
    it should always have been**: at or above the version that introduced them.
    The current value has one home and it is
    `test_store.py::test_the_schema_version_records_every_bump_and_what_it_was_for`.

    Catches the two members landing without the bump, which leaves two stores
    claiming the same schema and describing different code sets -- the exact
    failure the version exists to make tractable.
    """
    assert store.SCHEMA_VERSION >= 2
    assert Outcome.SCREENED_OUT.code == 12
    assert Outcome.NOT_APPLICABLE.code == 13
