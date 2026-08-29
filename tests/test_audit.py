"""§11.2's audit arms: the matched floor, the shared direction, and the seed.

**THE FIXTURES ARE FINE POINTS, NEVER COARSE ONES, AND THAT IS THE FIRST WAY
THIS SUITE COULD BE VACUOUS.** A coarse point's nearest valid source is itself,
so its `warm` arm starts from its own cold optimum -- every arm agrees, every
reading is the table's fourth row, and the suite is green while measuring
nothing. Where a test runs a real two-pass store it asserts that its points are
not on the coarse lattice.

**THE CANDIDATE SET IS TWO THROUGHOUT AND THE TWO HAVE DIFFERENT `p`** -- 1 and
3 at 2a's set -- because the direction is drawn per `(point, candidate)` at that
candidate's own width. One candidate cannot show a direction drawn at the wrong
width, and a `p = 1` candidate alone cannot show one that is not a unit vector.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import xarray as xr

from metamer.batch.audit import (
    N1_EPSILON,
    Arm,
    ArmStarts,
    AuditArms,
    arm_directions,
    arm_starts,
    cold_starts,
    run_arms,
)
from metamer.batch.timeaxis import to_decimal_years
from metamer.batch.twopass import run_two_pass
from metamer.batch.warmstart import coarse_ok, read_warm_starts, source_map
from metamer.config import load
from metamer.config.model import Config
from metamer.core.capability import Objective
from metamer.core.criteria import Criterion
from metamer.core.engines.kalman import KalmanEngine
from metamer.core.gradients import EPS
from metamer.core.optimize import InitRung
from metamer.core.outcomes import Outcome
from metamer.core.terms import free_param_index

_STRIDE = 2

_CONFIG = """
data_uri = "{uri}"
variable = "sla"
signal_terms = ["constant", "trend"]
candidates = ["white", "white + matern12"]
criteria = ["aic"]
memory_budget_gb = 1.0

[warm_start]
coarse_stride = {stride}
spiral_bound = 4
"""


def _input(tmp_path: Path, n_y: int = 7, n_x: int = 6, n_time: int = 24) -> str:
    """A non-square input whose extent is not a multiple of the stride."""
    origin = np.datetime64("2000-01-01")
    dataset = xr.Dataset(
        {
            "sla": (
                ("time", "y", "x"),
                np.random.default_rng(23)
                .standard_normal((n_time, n_y, n_x))
                .astype("float32"),
            )
        },
        coords={
            "time": np.array(
                [origin + np.timedelta64(31 * i, "D") for i in range(n_time)]
            ),
            "y": 100.0 + 2.5 * np.arange(n_y),
            "x": 500.0 - 0.5 * np.arange(n_x),
        },
    )
    path = tmp_path / "in.zarr"
    dataset.to_zarr(path)
    return str(path)


def _config(tmp_path: Path, uri: str, *, name: str = "c.toml", extra: str = "") -> Path:
    path = tmp_path / name
    path.write_text(_CONFIG.format(uri=uri, stride=_STRIDE) + extra)
    return path


def _series(
    tmp_path: Path, n_y: int = 7, n_x: int = 6, n_time: int = 24
) -> tuple[str, np.ndarray, np.ndarray]:
    """The input's series as `(B, N)` row-major, and the RUN's own time axis.

    **`to_decimal_years` ON THE ACTUAL COORDINATE, NEVER AN APPROXIMATION OF
    IT.** A hand-built axis of `2000 + i * 31/365.25` looks right and is not what
    `run` computes; the difference showed up as a **6.7e-05 relative** gap
    between a fit here and the same fit in the store -- large enough to fail a
    bitwise comparison and small enough to read as a floating-point detail. The
    conversion is under `ALGORITHM_VERSION`, so a second derivation of it is a
    second derivation of fit identity.
    """
    uri = _input(tmp_path, n_y=n_y, n_x=n_x, n_time=n_time)
    dataset = xr.open_zarr(uri)
    values = np.asarray(dataset["sla"].values, dtype=np.float64)
    block = values.transpose(1, 2, 0).reshape(n_y * n_x, n_time)
    years = to_decimal_years(dataset["time"].values)
    return uri, block, years


# --------------------------------------------------------------------------
# The perturbation: matched per cell, one shared direction
# --------------------------------------------------------------------------


def _starts_fixture(
    seed: int = 7, epsilon: float = N1_EPSILON
) -> tuple[list[Any], list[int], np.ndarray, ArmStarts]:
    """Constructed cold and warm starts with three DISTINCT distances.

    Built rather than fitted, because the properties under test are arithmetic
    on the starts and a fitted fixture cannot place a chosen distance in a
    chosen cell -- (i8).
    """
    from metamer.config.candidates import parse_candidate

    specs = [parse_candidate("white"), parse_candidate("white + matern12")]
    extents = [len(free_param_index(spec)) for spec in specs]
    batch = 5
    cold = np.full((batch, 2, max(extents)), np.nan)
    warm = np.full((batch, 2, max(extents)), np.nan)
    for model, width in enumerate(extents):
        cold[:, model, :width] = 0.0
        warm[:, model, :width] = 0.0
    # THREE DISTINCT MAGNITUDES in rows 0-2, so a control matched on the MEAN is
    # distinguishable from one matched per cell. **Row 3 is left equal to cold**
    # -- the degenerate `r = 0` cell -- and **row 4 has no warm start at all**,
    # the exhausted one. Each of the last two looks like agreement from a pooled
    # reading, which is why the fixture carries both.
    warm[0, 0, 0] = 0.25
    warm[1, 0, 0] = 1.5
    warm[2, 0, 0] = 0.75
    warm[0, 1, :3] = [0.3, -0.4, 0.0]
    warm[1, 1, :3] = [1.0, 0.0, 0.0]
    warm[2, 1, :3] = [0.0, 0.0, 2.0]
    valid = np.ones((batch, 2), dtype=bool)
    valid[4, :] = False
    points = np.array([11, 4, 29, 7, 16], dtype=np.int64)
    starts = arm_starts(
        cold=cold,
        warm=warm,
        warm_valid=valid,
        candidates=specs,
        points=points,
        seed=seed,
        epsilon=epsilon,
    )
    return specs, extents, points, starts


def test_n2_moves_each_cell_by_that_cells_own_warm_cold_distance():
    """`||N2 - cold||` equals `||warm - cold||`, cell by cell.

    Behaviour under test: D7's first constraint, which is the whole of what
    makes the floor interpretable. The warm/cold start distance varies by cell,
    and in unconstrained coordinates it varies more than the geometric source
    radius does.

    Expected values determined independently: the fixture's distances are
    written into it by hand -- 0.25, 1.5, 0.75 for the narrow candidate and
    0.5, 1.0, 2.0 for the wide one -- and each is recomputed here from the
    starts rather than read off `ArmStarts.distance`.

    Bug this catches: a control matched on the MEAN. It is mismatched in every
    cell, and most damagingly in the cells whose distance is largest -- which
    are exactly the cells where hysteresis is most likely -- so the floor would
    be too low where it matters and too high everywhere else. A mean-matched
    control passes any aggregate assertion.

    **The fixture carries three distinct magnitudes per candidate**, asserted,
    or a per-cell match and a mean match are the same thing.
    """
    specs, extents, _, starts = _starts_fixture()

    for model, width in enumerate(extents):
        live = starts.warm_valid[:, model] & ~starts.degenerate[:, model]
        magnitudes = np.linalg.norm(
            starts.warm[live, model, :width] - starts.cold[live, model, :width], axis=1
        )
        assert len(set(np.round(magnitudes, 12))) >= 3, (
            "a fixture with one distance cannot tell a per-cell match from a "
            "match on the mean"
        )
        moved = np.linalg.norm(
            starts.n2[live, model, :width] - starts.cold[live, model, :width], axis=1
        )
        np.testing.assert_allclose(moved, magnitudes, rtol=1e-12, atol=0.0)
        np.testing.assert_allclose(
            starts.distance[live, model], magnitudes, rtol=1e-12, atol=0.0
        )


def test_n1_and_n2_share_one_direction_so_the_tables_second_row_follows():
    """The two floor arms differ in magnitude and in nothing else.

    Behaviour under test: the property the four-reading table's second row
    rests on. That row reads *"the sensitivity is to start DISTANCE, not
    direction"*, and the inference is available only if N1 and N2 moved along
    the same ray.

    Expected values determined independently: the unit direction is recovered
    from each arm by dividing its displacement by its own magnitude, and the
    two are required to agree -- neither is compared against
    `ArmStarts.direction`, so this would still bite if that array were the one
    that was wrong.

    Bug this catches: N1 given a fixed direction -- all-ones, or the first
    coordinate -- which is the obvious implementation of "perturbed by a tiny
    epsilon". A non-zero N2 beside a zero N1 would then have two available
    explanations, the magnitude and the direction, and the reading the table
    promises would be unavailable after the arms had already run.

    **And N1's magnitude is exactly `N1_EPSILON`**, which is what makes it the
    same ray at a different distance rather than a different perturbation.
    """
    _, extents, _, starts = _starts_fixture()

    for model, width in enumerate(extents):
        live = starts.warm_valid[:, model] & ~starts.degenerate[:, model]
        assert live.any(), "a fixture with no live cell would pass vacuously"
        n1_step = starts.n1[live, model, :width] - starts.cold[live, model, :width]
        n2_step = starts.n2[live, model, :width] - starts.cold[live, model, :width]

        np.testing.assert_allclose(
            np.linalg.norm(n1_step, axis=1),
            N1_EPSILON,
            rtol=1e-12,
        )
        unit_n1 = n1_step / np.linalg.norm(n1_step, axis=1)[:, None]
        unit_n2 = n2_step / np.linalg.norm(n2_step, axis=1)[:, None]
        np.testing.assert_allclose(unit_n1, unit_n2, rtol=1e-9, atol=1e-12)


def test_the_epsilon_is_the_step_the_optimizers_own_gradient_takes():
    """`N1_EPSILON` is `eps^(1/3)`, derived rather than chosen.

    Expected value determined independently: `eps^(1/3)` is computed here from
    `EPS` directly, not read from `gradients.fd_step`, and the two are required
    to agree.

    Bug this catches: a picked constant. The table's first row reads *"the
    surface is deciding"*, which is a claim about structure BELOW THE
    RESOLUTION OF THE METHOD -- and that is only what N1 measures while its
    displacement is the one the finite-difference gradient cannot distinguish
    from zero. At a picked `1e-3` the same row would read "the surface has
    structure at 1e-3", which is an ordinary property of a likelihood and would
    fire on every fixture.
    """
    assert N1_EPSILON == pytest.approx(EPS ** (1.0 / 3.0), rel=1e-15)
    assert 1e-6 < N1_EPSILON < 1e-5


# --------------------------------------------------------------------------
# The seed, and the traversal order it must not depend on
# --------------------------------------------------------------------------


def test_the_same_seed_reproduces_n2_and_a_different_seed_does_not():
    """The paired positive and negative on the one stochastic input.

    Behaviour under test: that the seed is used, and that it is the only thing
    deciding the direction.

    Expected values determined independently: two arms built from one fixture
    at one seed must be bitwise equal, and the same fixture at another seed
    must differ somewhere -- neither is compared against a stored value.

    Bug this catches: a seed that is recorded but not used -- (a2), a name that
    is not a gate. The positive half alone is satisfied by an implementation
    that ignores the seed entirely and draws the same directions every time,
    which is why the plan asks for both halves.
    """
    _, _, _, first = _starts_fixture(seed=7)
    _, _, _, again = _starts_fixture(seed=7)
    _, _, _, other = _starts_fixture(seed=8)

    np.testing.assert_array_equal(first.n2, again.n2)
    np.testing.assert_array_equal(first.direction, again.direction)
    assert not np.allclose(
        np.nan_to_num(first.direction), np.nan_to_num(other.direction)
    ), "a different seed must give different directions, or the seed is unused"


def test_the_direction_is_a_function_of_the_cell_and_not_of_the_order():
    """Permuting the point set moves each cell's direction with its point.

    Behaviour under test: **the one place §11.3's traversal-independence can
    now be lost.** N2 introduces the only randomness in the system, and the
    natural implementation -- one `Generator` consumed in a loop -- makes cell
    `n`'s direction depend on how many cells were drawn before it, hence on the
    order of the point set, hence on tiling if the audit is ever tiled.

    Expected values determined independently: the permuted run's rows are
    reordered back by the permutation and required to equal the original,
    element for element. Nothing is compared against a stored array.

    Bug this catches: a streamed RNG. **Recording the seed does not save it** --
    the same seed under a different order gives different directions, so the
    audit would be reproducible only under a traversal that nothing enforces,
    and two audits of one store could not be compared.

    **And the second half is the subsample-size property**: a cell's direction
    is keyed on its GRID-GLOBAL index, so enlarging the point set must leave
    every existing cell alone. Keyed on the row number instead, adding one
    point would move every direction after it.
    """
    points = np.array([11, 4, 29, 7], dtype=np.int64)
    extents = [1, 3]
    straight = arm_directions(points, extents, seed=5)

    order = np.array([2, 0, 3, 1])
    permuted = arm_directions(points[order], extents, seed=5)
    np.testing.assert_array_equal(permuted, straight[order])

    enlarged = arm_directions(
        np.concatenate([points, np.array([99, 100])]), extents, seed=5
    )
    np.testing.assert_array_equal(enlarged[: points.size], straight)


def test_every_direction_is_a_unit_vector_at_its_candidates_own_width():
    """Each `(point, candidate)` draw is a unit vector over that candidate's `p`.

    Behaviour under test: the width the direction is drawn at. The two
    candidates have `p` of 1 and 3, and the array is `(B, M, p_max)` with the
    narrow candidate's tail NaN by design.

    Expected values determined independently: the norm is taken here over each
    candidate's own `p`, read from `free_param_index`, and the padding is
    required to be NaN.

    Bug this catches: drawing at `p_max` for every candidate. The narrow
    candidate's direction would then be a `p_max`-vector truncated to one
    coordinate, which is not a unit vector -- so N2's displacement would be
    SHORTER than the distance it is supposed to match, by a factor that varies
    with the draw. The per-cell magnitude assertion would still pass, because
    the scale is applied after normalisation, and only the direction's own norm
    shows it.
    """
    from metamer.config.candidates import parse_candidate

    specs = [parse_candidate("white"), parse_candidate("white + matern12")]
    extents = [len(free_param_index(spec)) for spec in specs]
    assert extents == [1, 3], "the fixture needs two DIFFERENT widths"

    directions = arm_directions(np.arange(6, dtype=np.int64), extents, seed=3)
    for model, width in enumerate(extents):
        np.testing.assert_allclose(
            np.linalg.norm(directions[:, model, :width], axis=1), 1.0, rtol=1e-12
        )
        assert np.isnan(directions[:, model, width:]).all()


# --------------------------------------------------------------------------
# The cells that have no floor, each of which looks like agreement
# --------------------------------------------------------------------------


def test_an_exhausted_cell_gets_no_floor_arm_at_all():
    """A cell with no warm start is outside the question, and is excluded.

    Behaviour under test: the accounting for cells the spiral exhausted. They
    have no warm start, so no distance, so N2 is undefined -- and they are not
    warm-started in production either, so there is no hysteresis question about
    them.

    Expected values determined independently: the fixture marks row 3 invalid
    for both candidates, and that row is required to be excluded from both
    floor arms and to carry a NaN distance.

    Bug this catches: folding them in as agreement. An excluded cell that is
    silently counted as "N2 agrees with cold" inflates the floor's agreement
    with cells that were never perturbed, and the more often the spiral
    exhausts -- which is the shape of a large land or ice region -- the more it
    inflates.
    """
    _, _, _, starts = _starts_fixture()

    assert not starts.warm_valid[4].any(), "the fixture must carry an exhausted row"
    assert not starts.n1_valid[4].any()
    assert not starts.n2_valid[4].any()
    assert np.isnan(starts.distance[4]).all()
    # The DIRECTION is still drawn there -- it is keyed on the cell, not
    # gated on validity -- which is what keeps it order-independent. What is
    # absent is the arm, not the draw.
    assert np.isfinite(starts.direction[4, 0, :1]).all()
    # And the live rows really are live, or the assertions above hold for a
    # fixture in which nothing is valid at all. (i2).
    assert starts.n2_valid[:4].all()


def test_a_zero_distance_cell_is_counted_as_degenerate():
    """Where warm equals cold, N2 collapses onto cold and measures nothing.

    Behaviour under test: the third degenerate class. A cell whose warm start
    equals its ladder start has `r = 0`, so N2 IS cold -- and it contributes
    "N2 agrees" to any pooled reading while carrying no information.

    Expected value determined independently: the fixture leaves row 2's warm
    start equal to its cold start, and the distance is recomputed here.

    Bug this catches: counting a degenerate cell as a measured floor. On a
    fixture where warm starts are often near the ladder start -- which is what
    a smoothly varying field produces -- the floor would be dominated by cells
    that were not moved.
    """
    _, extents, _, starts = _starts_fixture()

    assert starts.degenerate[3].all(), "row 3 is the constructed zero-distance row"
    for model, width in enumerate(extents):
        np.testing.assert_array_equal(
            starts.n2[3, model, :width], starts.cold[3, model, :width]
        )
    assert not starts.degenerate[:3].any(), "the other live rows must be non-degenerate"


def test_an_n2_start_outside_the_diagnostic_box_is_excluded_not_run_cold():
    """A perturbation that leaves the admissible region loses ONE cell.

    Behaviour under test: the handling of an inadmissible N2 start. `r` is a
    real distance and the diagnostic box is finite, so a large enough warm/cold
    distance in an unlucky direction puts the start outside it -- and `fit`
    refuses the WHOLE call rather than losing a cell.

    Expected value determined independently: the fixture places a warm start
    far enough out that `exp` of the perturbed coordinate is beyond `rho`'s
    upper diagnostic limit, and the limit is read from the candidate's own
    `ParamSpec` rather than hardcoded.

    Bug this catches, and it is the one-line fix: setting `x0_valid` false for
    the offending cell. A false cell **falls back to the moment ladder**, so
    the N2 arm would silently contain a COLD fit -- and "N2 agrees with cold"
    would be true by construction at exactly the cells where the perturbation
    was largest. That is (a0)'s fourth register: a fallback makes "did not
    happen" and "happened and was discarded" one observation.

    **The count is separate from `n2_valid` on purpose**, so a consumer can
    tell an excluded cell from one that was never offered a warm start.
    """
    from metamer.config.candidates import parse_candidate

    specs = [parse_candidate("white"), parse_candidate("white + matern12")]
    extents = [len(free_param_index(spec)) for spec in specs]
    limits = (
        dict(zip(specs[1].labels(), specs[1].terms, strict=True))["matern12[0]"]
        .params["rho"]
        .diagnostic_limits
    )
    assert np.isfinite(limits[1])

    cold = np.full((2, 2, max(extents)), np.nan)
    warm = np.full((2, 2, max(extents)), np.nan)
    for model, width in enumerate(extents):
        cold[:, model, :width] = 0.0
        warm[:, model, :width] = 0.0
    # Row 0 is ordinary. Row 1's distance exceeds log(upper limit) in every
    # direction, so no draw can keep it inside the box.
    warm[1, 1, :3] = [0.0, 10.0 * float(np.log(limits[1])), 0.0]
    warm[0, 1, :3] = [0.1, 0.0, 0.0]
    warm[:, 0, 0] = 0.2

    starts = arm_starts(
        cold=cold,
        warm=warm,
        warm_valid=np.ones((2, 2), dtype=bool),
        candidates=specs,
        points=np.array([3, 8], dtype=np.int64),
        seed=1,
    )

    assert starts.n2_inadmissible[1, 1], "the fixture must construct the fault"
    assert not starts.n2_valid[1, 1]
    assert starts.warm_valid[1, 1], "and it must be a cell that HAS a warm start"
    # The positive control in the same array: the ordinary row survives, so the
    # exclusion is about the value and not about the call. (i2).
    assert starts.n2_valid[0].all()
    assert not starts.n2_inadmissible[0].any()


# --------------------------------------------------------------------------
# The arms, run
# --------------------------------------------------------------------------


#: How many fine points the end-to-end fixtures audit.
#:
#: **EIGHT, NOT ALL THIRTY-ONE, AND THE ONLY THING IT BUYS IS TIME.** Every
#: assertion here is per cell over whatever cells exist, and eight points across
#: two candidates is sixteen; the full set cost 148 s per test against ~35 s.
#: The tests that need a specific cell CONSTRUCT it rather than hunting for one
#: in a fitted fixture, so nothing depends on the count.
_AUDITED_POINTS = 8


@dataclass(frozen=True)
class _TwoPass:
    """One real two-pass run, shared by every end-to-end test in this module."""

    config: Config
    block: np.ndarray
    years: np.ndarray
    pass1_path: Path
    store_path: Path
    fine: np.ndarray
    warm: np.ndarray
    warm_valid: np.ndarray
    index: Any
    n_x: int


@pytest.fixture(scope="module")
def two_pass(tmp_path_factory: pytest.TempPathFactory) -> _TwoPass:
    """A two-pass run, its source map, and the FINE points to audit.

    **MODULE-SCOPED BECAUSE IT IS READ AND NEVER WRITTEN.** Three tests need the
    same store; building it three times cost 80 s and proved nothing extra.
    """
    from metamer.batch.ragged import build_ragged_index, noise_extent

    tmp_path = tmp_path_factory.mktemp("audit")
    n_y, n_x, n_time = 7, 6, 24
    uri, block, years = _series(tmp_path, n_y=n_y, n_x=n_x, n_time=n_time)
    config_path = _config(tmp_path, uri)
    config = load(config_path)
    report = run_two_pass(config_path, tmp_path / "out.zarr")
    assert report.pass1_path is not None and report.pass2 is not None

    usable = coarse_ok(report.pass1_path)
    sources = source_map(
        shape=(n_y, n_x),
        stride=_STRIDE,
        coarse_ok=usable,
        spiral_bound=4,
        region=None,
    )
    specs = list(config.process_specs())
    index = build_ragged_index(specs, noise_extent)
    warm = read_warm_starts(
        report.pass1_path,
        sources,
        index,
        coarse_shape=(usable.shape[0], usable.shape[1]),
    )

    # **FINE POINTS ONLY.** A coarse point sources itself, so every arm agrees
    # there and the whole comparison is the table's fourth row by construction.
    fine = np.array(
        [
            y * n_x + x
            for y in range(n_y)
            for x in range(n_x)
            if not (y % _STRIDE == 0 and x % _STRIDE == 0)
        ],
        dtype=np.int64,
    )[:_AUDITED_POINTS]
    assert fine.size == _AUDITED_POINTS

    return _TwoPass(
        config=config,
        block=block,
        years=years,
        pass1_path=Path(report.pass1_path),
        store_path=Path(report.store_path),
        fine=fine,
        warm=warm[fine],
        warm_valid=sources.valid[fine],
        index=index,
        n_x=n_x,
    )


def _arms(
    two_pass: _TwoPass, *, epsilon: float = N1_EPSILON, seed: int = 4
) -> AuditArms:
    """Four arms over the shared batch."""
    config = two_pass.config
    return run_arms(
        two_pass.block[two_pass.fine],
        two_pass.years,
        config.signal_spec(),
        list(config.process_specs()),
        Criterion(config.criteria[0]),
        mask=np.isfinite(two_pass.block[two_pass.fine]),
        warm=two_pass.warm,
        warm_valid=two_pass.warm_valid,
        points=two_pass.fine,
        seed=seed,
        objective=Objective(config.objective),
        epsilon=epsilon,
    )


@pytest.fixture(scope="module")
def arms(two_pass: _TwoPass) -> AuditArms:
    """The four arms at the shipped epsilon."""
    return _arms(two_pass)


@pytest.fixture(scope="module")
def arms_at_zero(two_pass: _TwoPass) -> AuditArms:
    """The four arms with N1's displacement switched off."""
    return _arms(two_pass, epsilon=0.0)


def test_n1_at_epsilon_zero_is_bit_identical_to_the_cold_arm(arms_at_zero):
    """The perturbation path adds no difference of its own.

    Behaviour under test: that N1's machinery -- recomputing the ladder start,
    supplying it as an explicit `x0`, and going round `fit`'s warm-start
    validation -- lands the optimizer on exactly the point the cold arm starts
    from. If it does not, every N1 reading is a mixture of the perturbation and
    an offset nobody intended.

    Expected values determined independently: the cold arm is produced by the
    same call with `x0=None`, which is a different code path through
    `optimize_series` -- the ladder is computed inside it rather than supplied.

    Bug this catches: the audit recomputing `moment_init` and
    `to_unconstrained` itself instead of calling `optimize.ladder_start`. Two
    spellings agree today and diverge the first time either moves, and the
    symptom is a floor that is quietly non-zero everywhere.

    **`init_rung` is deliberately NOT compared.** `optimize_series` reports
    `WARM_START` whenever an `x0` is supplied, so N1 at epsilon zero is
    labelled warm and cold is labelled `moment` -- which is (a2) and is exactly
    why the arm's identity lives in `Arm` and not in the rung.
    """
    cold = arms_at_zero.results[Arm.COLD]
    n1 = arms_at_zero.results[Arm.N1]
    live = arms_at_zero.starts.n1_valid

    assert live.any(), "no live cell would make this vacuous"
    np.testing.assert_array_equal(n1.theta[live], cold.theta[live])
    np.testing.assert_array_equal(n1.loglik[live], cold.loglik[live])
    np.testing.assert_array_equal(n1.n_iter[live], cold.n_iter[live])
    np.testing.assert_array_equal(n1.outcome[live], cold.outcome[live])
    # And the rung differs, which is the (a2) fact this suite pins rather than
    # works around.
    assert np.all(n1.init_rung[live] == InitRung.WARM_START)
    assert np.all(cold.init_rung[live] != InitRung.WARM_START)


def test_the_warm_arm_reproduces_pass_twos_store_bitwise(two_pass, arms):
    """The audit's `warm` arm IS the shipped mechanism, checked against it.

    Behaviour under test: that the whole audit path -- the source map, the
    reader, the ragged unpacking and the fit -- reproduces what pass 2 actually
    wrote. This is the single assertion that makes the other three arms
    comparisons against the shipped answer rather than against a fourth thing
    the audit computed.

    Expected values determined independently: pass 2's store is read here and
    compared element by element with the arm's own `theta`, at the audited
    points only.

    Bug this catches: an audit that reconstructs the warm start differently
    from the run -- a different stride, a bound read from the wrong place, a
    source map built over the wrong grid. Every arm would still fit, every
    number would be finite, and the audit would report hysteresis in a
    mechanism nobody shipped.

    **THE POINTS ARE FINE POINTS, ASSERTED.** At a coarse point the warm arm
    starts from that point's own cold optimum, so this comparison would hold
    for a much weaker implementation.
    """
    fine, n_x, index = two_pass.fine, two_pass.n_x, two_pass.index
    stored = np.asarray(
        xr.open_zarr(two_pass.store_path, group="noise")["theta"].values,
        dtype=np.float64,
    )

    assert not any(
        (point // n_x) % _STRIDE == 0 and (point % n_x) % _STRIDE == 0
        for point in fine.tolist()
    ), "a coarse point sources itself and would make this hold trivially"

    warm = arms.results[Arm.WARM]
    for model, extent in enumerate(index.extents):
        got = warm.theta[:, model, :extent]
        want = stored.reshape(-1, stored.shape[-1])[fine][:, index.block(model)]
        np.testing.assert_array_equal(got.astype(np.float32), want.astype(np.float32))


def test_the_four_arms_are_all_produced_over_one_batch(two_pass, arms):
    """Every arm returns a fit for every audited cell, from one call site.

    Behaviour under test: the positive control the whole module needs. Four
    arms that each ran, over the same batch, in one session -- which is what
    makes them comparable at all (j5), and what kept a spurious 15% out of the
    stride sweep when its cold arm was re-run rather than reused.

    Expected values determined independently: the batch's shape comes from the
    point set constructed in the fixture.

    Bug this catches: an arm that silently did not run -- an empty result, or
    one arm's results being another's object. Without this every "arm A agrees
    with arm B" assertion elsewhere could be satisfied by two references to one
    fit.

    **And it asserts the arms are DISTINCT objects with distinct starts**, so a
    module that returned the cold fit four times would fail here rather than
    reading as perfect agreement.
    """
    fine = two_pass.fine

    assert set(arms.results) == set(Arm)
    for arm, result in arms.results.items():
        assert result.outcome.shape == (fine.size, 2), arm
        assert (result.outcome != Outcome.NOT_ATTEMPTED.code).any(), arm

    live = arms.starts.n2_valid & ~arms.starts.degenerate
    assert live.any()
    # The warm and N2 arms started from genuinely different points, or "they
    # agree" is a statement about one fit. (i2).
    assert not np.allclose(
        np.nan_to_num(arms.starts.n2), np.nan_to_num(arms.starts.warm)
    )
    assert arms.seed == 4
    assert arms.epsilon == N1_EPSILON


def test_the_cold_arm_reproduces_pass_ones_store_at_a_coarse_point(two_pass):
    """Pass 1's surviving job: a free cold reference, used as a cross-check.

    Behaviour under test: that the audit's computed cold arm is the same
    quantity pass 1 already holds. This is the (j5)-clean cross-check -- same
    code, same config, same series, differing only in when it ran -- and it is
    what is left of "pass 1 is the audit's cold reference" once D12 rules the
    coarse set out as the audit's SUBJECT.

    Expected values determined independently: pass 1's store is read here and
    compared against a cold fit computed in this process.

    Bug this catches: a cold arm that is not cold -- an `x0` leaking in from
    the warm path, or a ladder start computed under a different objective or
    engine. The audit's floor would then be measured against a start the
    production run never used.

    **This is the one place the coarse points belong in the audit**, and the
    reason is the opposite of the reason they are excluded as its subject:
    there is a stored answer to compare against precisely because they were
    fitted cold.
    """
    n_y, n_x = 7, two_pass.n_x
    block, years, config = two_pass.block, two_pass.years, two_pass.config

    coarse_rows = [
        (y // _STRIDE, x // _STRIDE, y * n_x + x)
        for y in range(0, n_y, _STRIDE)
        for x in range(0, n_x, _STRIDE)
    ]
    flat = np.array([point for _, _, point in coarse_rows], dtype=np.int64)
    specs = list(config.process_specs())

    cold = cold_starts(
        block[flat],
        np.isfinite(block[flat]),
        years,
        specs,
        engine=KalmanEngine(),
        objective=Objective(config.objective),
    )
    assert np.isfinite(cold[:, 0, :1]).all(), "the ladder must produce a start"

    from metamer.core.fit import fit as core_fit

    fresh = core_fit(
        block[flat],
        years,
        config.signal_spec(),
        specs,
        Criterion(config.criteria[0]),
        mask=np.isfinite(block[flat]),
        objective=Objective(config.objective),
    )
    stored = np.asarray(
        xr.open_zarr(two_pass.pass1_path, group="noise")["theta"].values,
        dtype=np.float64,
    )
    index = two_pass.index
    for model, extent in enumerate(index.extents):
        want = np.array(
            [stored[i, j, index.block(model)] for i, j, _ in coarse_rows],
            dtype=np.float64,
        )
        np.testing.assert_array_equal(
            fresh.theta[:, model, :extent].astype(np.float32), want.astype(np.float32)
        )


# --------------------------------------------------------------------------
# The report, on the arms this module already builds
# --------------------------------------------------------------------------


def test_the_report_reads_real_arms_and_no_cell_reaches_an_upper_kappa_bin(
    two_pass, arms
):
    """§11.2's report on a real two-pass store, and the `κ` axis on real fits.

    Behaviour under test: three things the constructed fixtures in
    `tests/test_audit_report.py` cannot show, because they build their own
    `FitResult`s.

    First, `FitResult.hessian_cond` **arrives populated through the whole
    path** -- `optimize_series` to `fit` to `run_arms` to the report. A field
    that is populated and one that nothing acts on look identical from inside
    the module that populates it.

    Second, and this is the Task 7 pre-flight finding on data rather than on
    argument: **no cell lands in `[2**26, 2**52)` or `>= 2**52`**. That is not
    a property of this fixture. `optimize.HESSIAN_COND_LIMIT` IS the first
    boundary, so a fit above it reports `DEGENERATE_HESSIAN` and leaves the
    both-OK intersection; the two upper bins are unreachable on every store
    this report will ever be run against, and the report says so in its notes.

    Third, that a real audit at an affordable size puts **every** stratum under
    the 30-member floor, so every rate is withheld -- which is why the
    boundary itself is tested on constructed counts and cannot be tested here.

    Expected values determined independently: the stratum counts are
    `M x 4` and `M x 3` from D9's own tables, and the audited cells are
    `_AUDITED_POINTS x M`.

    Bug this catches: the report reading `theta_err` or a recomputed
    curvature rather than the arrays `fit` now publishes -- which would show
    up here as an all-`undefined` `κ` axis or an exception, and nowhere in the
    constructed suite, whose `FitResult`s are hand-built and always
    well-formed.
    """
    from metamer.batch.audit_report import KAPPA_BINS, KappaBin, audit_report, kappa_bin

    config = two_pass.config
    mask = np.isfinite(two_pass.block[two_pass.fine])
    design = config.signal_spec().design_info(two_pass.years, mask)

    report = audit_report(arms, trend_column=design.trend_column)
    cold = arms.results[Arm.COLD]

    n_cand = len(config.process_specs())
    assert len(report.cell_strata) == n_cand * len(KAPPA_BINS)
    assert len(report.point_strata) == n_cand * 3

    live = (cold.outcome == Outcome.OK.code) & (
        arms.results[Arm.WARM].outcome == Outcome.OK.code
    )
    assert live.any(), "no both-OK cell would make every assertion below vacuous"
    assert np.any(np.isfinite(cold.hessian_cond[live])), (
        "hessian_cond must arrive populated through fit and run_arms; an "
        "all-NaN axis is a field nothing acted on"
    )

    bins = {KAPPA_BINS[code] for code in kappa_bin(cold.hessian_cond[live])}
    assert bins <= {KappaBin.WELL_CONDITIONED, KappaBin.UNDEFINED}, (
        f"an OK fit cannot exceed HESSIAN_COND_LIMIT, which IS the first kappa "
        f"boundary, so the two upper bins are unreachable here; got {bins}"
    )
    assert report.unreachable_kappa_bins == (
        KappaBin.HALF_PRECISION,
        KappaBin.SINGULAR,
    )

    occupied = sum(s.members for s in report.cell_strata)
    assert occupied == int(np.count_nonzero(live))
    assert all(s.members < report.min_stratum_members for s in report.cell_strata), (
        "this fixture is 8 points and cannot populate a stratum to 30; the "
        "boundary is tested on constructed counts in tests/test_audit_report.py"
    )
    assert report.withheld(), "every rate here is below the floor"
    for quantity in report.quantities():
        assert quantity.scope
    assert any("No pooled disagreement figure" in note for note in report.notes)
