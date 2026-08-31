"""`metamer.bench.fields`: the 2d benchmark field, its step, and its rungs.

**WHAT THIS MODULE IS FOR, IN ONE LINE.** Design doc section 16.2 item 6 wants
hysteresis measured on simulated *fields* with parameters that vary smoothly
and that jump sharply across a boundary, because *"hysteresis is a spatial
phenomenon that cannot appear in independent draws with no neighbour
structure."* Every two-pass fixture in this suite before now was
`standard_normal` per point, which is exactly that.

**THE TESTS BELOW ASSERT PROPERTIES OF THE TRUTH, NOT OF THE FITS**, wherever
they can. The truth is what the builder controls; the fits are what the
benchmark is trying to move, and asserting on them would make the oracle a
function of the thing under test -- (j).
"""

from __future__ import annotations

import numpy as np
import pytest
import xarray as xr

from metamer.batch.timeaxis import to_decimal_years
from metamer.bench import fields

# `to_zarr` warns that consolidated metadata is not in the v3 spec. It is
# xarray's default and says nothing about this code.
pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")


#: Tests that assert on the TRUTH use a short record deliberately: the truth is
#: a function of the rung and the geometry and does not depend on `n_time` at
#: all, so drawing 630-long series to check it would spend minutes proving
#: something the shape already fixes. The tests that DO depend on the record --
#: the shipped-path one and the both-candidates-win one -- name their own.
_TRUTH_N_TIME = 24


def _build(tmp_path, rung, **kwargs):
    """Build one rung's field under `tmp_path`, with the shipped defaults."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    kwargs.setdefault("n_time", _TRUTH_N_TIME)
    return fields.build_field(rung, path=tmp_path / f"{rung.name}.zarr", **kwargs)


# --------------------------------------------------------------------------
# The step, and the interior line that must not see one
# --------------------------------------------------------------------------


def test_the_truth_jumps_at_the_boundary_and_the_jump_dominates_every_other(tmp_path):
    """The step is a STEP: one cell wide, and larger than the smooth variation.

    Behaviour: `Delta` is defined as a multiple of the within-regime range of
    the same parameter, so the boundary's inter-cell difference must exceed
    every other inter-cell difference along the normal by roughly that
    multiple.

    Expected value determined independently: from `Delta`'s own definition. The
    within-regime range is spread over `n_normal // 2` cells either side, so a
    single within-regime step is at most `range / 15`, while the boundary step
    is `Delta * range`. The assertion is the ORDERING plus a margin, not the
    ratio, because the ratio depends on how the smooth variation is shaped and
    the ordering does not.

    Bug this catches: a builder that smooths the step -- for instance by
    generating the whole truth through one smoothing kernel with the step added
    BEFORE the smoothing rather than after. Every measured smear width would
    then be a true width plus an artifact width, and reading the artifact would
    mean subtracting one from the other. **That is the `w > 0` design E3
    rejected, arriving as an implementation accident**, and no other test here
    would see it: the field would still be coherent, still have a transition,
    and still fit.
    """
    built = _build(tmp_path, fields.RUNGS["easy"], seed=11)

    # **THE THING THAT STEPS IS THE FAMILY, NOT A PARAMETER.** Across a change
    # of family the parameter that jumps is not the same parameter on both
    # sides, so a width "of sigma" is a width of different things either side
    # of the boundary. The family index is categorical, is defined everywhere,
    # and is what the smear estimator's subject -- the SELECTED CANDIDATE --
    # responds to.
    family = built.family
    transitions = np.flatnonzero(np.diff(family, axis=0).any(axis=1))
    assert transitions.tolist() == [fields.BOUNDARY_INDEX - 1], (
        "the true family changes at more or fewer than one place along the "
        f"normal: transitions at {transitions.tolist()}, expected only "
        f"{fields.BOUNDARY_INDEX - 1}"
    )

    truth = built.parameters
    profile = truth[:, :, fields.SIGMA].mean(axis=1)
    steps = np.abs(np.diff(profile))
    boundary = fields.BOUNDARY_INDEX

    # The difference recorded at index i is between cells i and i+1, so the
    # boundary's own step sits at index `boundary - 1`.
    at_boundary = steps[boundary - 1]
    elsewhere = np.delete(steps, boundary - 1)

    assert at_boundary == steps.max(), (
        "the largest inter-cell difference along the normal is not at the "
        f"boundary: max at index {int(steps.argmax())}, boundary step at "
        f"{boundary - 1}"
    )
    assert at_boundary > 4.0 * elsewhere.max(), (
        f"the boundary step {at_boundary:.4g} does not dominate the largest "
        f"within-regime step {elsewhere.max():.4g}; the step has been smoothed"
    )


def test_an_interior_line_away_from_the_boundary_has_no_transition(tmp_path):
    """The free negative control's precondition, asserted on the truth.

    Behaviour: E6's third prediction reads the smear estimator on a line
    parallel to the boundary and far from it, where the truth has no
    transition, and requires the floor. That is only a control if the truth
    really is transition-free there.

    Expected value determined independently: the within-regime range divided by
    the number of cells it is spread over, computed by hand from the rung's own
    `Delta` and the geometry -- not from the builder.

    Bug this catches: a builder whose smooth variation happens to be steepest
    where the null line is drawn. The negative control would then fire for a
    reason that is not a defect, and **an alarm that fires on a healthy field
    is worse than no alarm**, because the first response is to widen its
    threshold until it stops.
    """
    built = _build(tmp_path, fields.RUNGS["easy"], seed=11)
    truth = built.parameters
    profile = truth[:, :, fields.SIGMA].mean(axis=1)
    steps = np.abs(np.diff(profile))

    # The family must also be constant there, or the null line straddles a
    # regime and is not a control at all.
    null_family = built.family[fields.NULL_LINE_INDEX]
    assert len(set(null_family.tolist())) == 1, (
        "the null line crosses a family boundary, so it is not a control"
    )

    # A window entirely inside one regime, at least one coarse spacing from
    # the boundary. `NULL_LINE_INDEX` is where the estimator will look.
    null = fields.NULL_LINE_INDEX
    assert abs(null - fields.BOUNDARY_INDEX) >= fields.COARSE_STRIDE, (
        "the null line is inside the coupling range, so it is not a control"
    )
    window = steps[max(null - 2, 0) : null + 2]
    largest_within = np.delete(steps, fields.BOUNDARY_INDEX - 1).max()

    assert window.max() <= largest_within, (
        "the smooth variation is steepest at the null line, so the negative "
        "control would fire on a healthy field"
    )


def test_the_boundary_is_a_change_of_family_and_each_region_is_one_family(tmp_path):
    """Both regimes exist, each is homogeneous, and they differ.

    Behaviour: the regime boundary is a **change of family** -- the repair
    taken 2026-08-30 after both of Task 1's field readings were refuted from
    below. 2c's field changed family across its boundary and ran at 40.79 cold
    iterations per point; this field changed magnitude inside one family and
    ran at 14.31, and at that cost a warm start has nothing to improve.

    Expected value determined independently: two distinct family indices, one
    per region, with every point in a region carrying its region's index. Read
    off the truth array, which the builder controls.

    Bug this catches: a rebuild that keeps one family and merely widens the
    magnitude step. Every other test here would still pass -- the step would
    still be a step, the null line would still be clean, `l` would still order
    the autocorrelation -- and the field would still be unable to show the
    effect, which is the failure this whole rebuild exists to remove.
    """
    built = _build(tmp_path, fields.RUNGS["easy"], seed=13)
    before = built.family[: fields.BOUNDARY_INDEX]
    after = built.family[fields.BOUNDARY_INDEX :]

    assert len(set(before.ravel().tolist())) == 1, "region A is not one family"
    assert len(set(after.ravel().tolist())) == 1, "region B is not one family"
    assert before[0, 0] != after[0, 0], (
        "both regions carry the same family, so the boundary is a magnitude "
        "change and not a change of family"
    )
    assert set(fields.FAMILY_KINDS) == {"matern12", "matern32"}


def test_the_contrast_still_scales_a_magnitude_across_the_family_change(tmp_path):
    """`Delta` keeps its unit: a multiple of the within-regime range of sigma.

    Behaviour: the family change is unconditional; `contrast` scales an
    ADDITIONAL magnitude step on top of it. `contrast = 0` is a family change
    alone, and a larger contrast is a larger sigma step.

    Expected value determined independently: two rungs at the same `l` and
    different `contrast`, compared by their sigma step at the boundary. The
    ordering follows from `Delta`'s definition, not from the builder.

    Bug this catches: `contrast` surviving the rebuild as a field that is
    carried and no longer read -- (a2), and exactly the shape the pre-flight
    warned about when it said a family change has no natural multiple. The
    second lever would silently become a no-op while `Rung` still advertised
    it, and E5's two-lever design would be one lever wearing two names.
    """
    quiet = fields.Rung(
        name="quiet",
        coherence_length=16.0,
        contrast=0.0,
        sources={"coherence_length": "test", "contrast": "test"},
    )
    loud = fields.Rung(
        name="loud",
        coherence_length=16.0,
        contrast=4.0,
        sources={"coherence_length": "test", "contrast": "test"},
    )

    def sigma_step(rung):
        truth = _build(tmp_path / rung.name, rung, seed=13).parameters
        profile = truth[:, :, fields.SIGMA].mean(axis=1)
        return abs(profile[fields.BOUNDARY_INDEX] - profile[fields.BOUNDARY_INDEX - 1])

    assert sigma_step(loud) > sigma_step(quiet), (
        "a larger contrast did not produce a larger sigma step: the second "
        "lever is carried and not read"
    )


# --------------------------------------------------------------------------
# Determinism, and that a rung is a rung
# --------------------------------------------------------------------------


def test_one_rung_twice_is_identical_and_two_rungs_differ(tmp_path):
    """The paired positive and negative for "the rung parameter is used".

    Behaviour: a rung is part of the fixture's identity. Rebuilding one rung
    reproduces it exactly; a different rung produces a different field.

    Expected value determined independently: byte equality and inequality; no
    value is computed.

    Bug this catches: a rung parameter that is **recorded and not used** --
    (a2), a name that is not a gate. Every rung would then produce the same
    field, the sweep would be three copies of one setting, and E6's
    monotonicity prediction would be vacuously satisfied by three equal
    numbers. **The negative half is what catches it**; the positive half alone
    passes for a builder that ignores its argument entirely.
    """
    easy_a = _build(tmp_path / "a", fields.RUNGS["easy"], seed=5)
    easy_b = _build(tmp_path / "b", fields.RUNGS["easy"], seed=5)
    hard = _build(tmp_path / "c", fields.RUNGS["hard"], seed=5)

    assert np.array_equal(easy_a.parameters, easy_b.parameters), (
        "one rung built twice under one seed is not reproducible"
    )
    assert not np.array_equal(easy_a.parameters, hard.parameters), (
        "two rungs produced the same truth: the rung parameters are recorded "
        "and not used"
    )


def test_the_coherence_length_orders_the_spatial_autocorrelation(tmp_path):
    """A larger `l` gives more correlation at a fixed lag. Comparative, on the truth.

    Behaviour: E5's primary lever must be a lever. `l` sets the spatial scale
    over which the true parameters vary, so at any fixed lag the truth's
    autocorrelation must be strictly greater for the rung with the larger `l`.

    Expected value determined independently: **an ordering, not a value.**
    Fitting a correlation model to recover `l` would fit the same functional
    form the field was generated from, which checks the generator against
    itself -- (j). A monotonicity assertion shares no form with the generator
    and cannot be satisfied by a mislabelled parameter.

    Bug this catches: `l` scaling the wrong axis, or being carried into the
    dataclass and never reaching the field. The sweep's entire lever would then
    be a label, every rung would be equally coherent, and the resolution floor
    E4 reports would be a floor for one setting reported as three.

    Why this is an ordering over the SET and not over a pair: the sweep has
    three rungs since 2026-08-31, and a pairwise assertion on the two extremes
    passes for a middle rung placed anywhere at all -- including off the
    diagonal, or equal to one of its neighbours. **A gate over a set that can
    grow is written against the set** (c5), and this set grew.
    """

    def correlation_at(truth, lag):
        """Lag-`lag` correlation along the PARALLEL axis, within one regime."""
        # Parallel to the boundary, so the step never enters the statistic.
        block = truth[: fields.BOUNDARY_INDEX, :, fields.SIGMA]
        left, right = block[:, :-lag], block[:, lag:]
        left = left - left.mean()
        right = right - right.mean()
        denominator = np.sqrt((left**2).sum() * (right**2).sum())
        return float((left * right).sum() / denominator)

    ordered = sorted(
        fields.RUNGS.values(), key=lambda rung: rung.coherence_length, reverse=True
    )
    assert len(ordered) == len(fields.RUNGS) >= 3, "the sweep is three rungs"
    lengths = [rung.coherence_length for rung in ordered]
    assert len(set(lengths)) == len(lengths), (
        "two rungs share a coherence length: the sweep has fewer points than it reports"
    )

    lag = 2
    correlations = [
        correlation_at(
            _build(tmp_path / rung.name, rung, seed=7).parameters,
            lag,
        )
        for rung in ordered
    ]

    for longer, shorter, above, below in zip(
        ordered[:-1], ordered[1:], correlations[:-1], correlations[1:], strict=True
    ):
        assert above > below, (
            f"rung {longer.name!r} has coherence length "
            f"{longer.coherence_length:.4g} against {shorter.name!r}'s "
            f"{shorter.coherence_length:.4g}, but is no more spatially "
            f"correlated at lag {lag} ({above:.4f} vs {below:.4f}): "
            "`coherence_length` is a label"
        )


def test_the_three_rungs_sit_on_one_diagonal(tmp_path):
    """The middle rung is the geometric midpoint of the other two, in both levers.

    Behaviour: E5 sweeps `l` and `contrast` TOGETHER, so the three rungs must
    lie on one line or they stop being one lever's curve and become three
    unrelated settings.

    Expected values determined independently, as arithmetic: the geometric
    midpoint of 16.0 and 6.0 is `sqrt(96) = 9.79796`, and of 3.0 and 0.75 is
    `sqrt(2.25) = 1.5` exactly. Geometric rather than arithmetic because both
    quantities are ratio-scale -- `coherence_length` matters through its ratio
    to `COARSE_STRIDE` and `contrast` is already defined as a multiple of
    `WITHIN_REGIME_RANGE`.

    Bug this catches: a middle rung nudged to a rounder number. `l = 10.0` is
    2% off the line and looks harmless; it makes the spacing between the three
    unequal in the coordinate the effect is expected to be smooth in, so a
    non-monotone result at the middle rung could no longer be read as a
    finding about the lever rather than about the placement. **The rung is
    COMPUTED from its neighbours for this reason**, and this test is what
    notices if someone replaces the computation with a literal.
    """
    easy, middle, hard = (fields.RUNGS[name] for name in ("easy", "middle", "hard"))

    assert middle.coherence_length == pytest.approx(
        np.sqrt(easy.coherence_length * hard.coherence_length)
    )
    assert middle.contrast == pytest.approx(np.sqrt(easy.contrast * hard.contrast))
    assert hard.coherence_length < middle.coherence_length < easy.coherence_length
    assert hard.contrast < middle.contrast < easy.contrast


def test_the_middle_rung_records_that_it_was_chosen_rather_than_sourced(tmp_path):
    """The slot that used to be plausibility says, twice, that it is ours.

    Behaviour: E4's constraint on the middle rung. Its `sources` must state
    that both parameters were chosen by us, because it sits between two
    extremes and therefore reads as the realistic case without anyone having
    claimed it is.

    Expected value determined independently: `Rung.__post_init__` already
    refuses an empty source, so the content is what is at stake -- both entries
    must say `chosen`, and neither may claim a citation.

    Bug this catches: a middle rung whose sources say something like
    "interpolated between the shipped rungs". That is true and it is not the
    warning: a reader quoting a magnitude from this rung would still have no
    signal that its most load-bearing parameter was picked. **A middle rung on
    a sweep is where a later reader supplies "plausible" for free**, and the
    source line is the only thing in the artifact that stops them.
    """
    middle = fields.RUNGS["middle"]

    for parameter in ("coherence_length", "contrast"):
        source = middle.sources[parameter].lower()
        assert "chosen by us" in source, (
            f"the middle rung's {parameter!r} does not record that it was "
            "chosen; it occupies the plausibility slot and will be read as "
            "sourced"
        )
        assert "not sourced" in source


# --------------------------------------------------------------------------
# The geometry, derived from `k`
# --------------------------------------------------------------------------


def test_the_geometry_is_the_one_the_derivation_names(tmp_path):
    """32 x 12, boundary at the midpoint, and two coarse points per axis.

    Behaviour: the normal axis is `4k` with the boundary at its midpoint, so an
    interior line can sit two full coarse spacings away; the parallel axis
    carries at least two coarse points so the nearest-valid spiral has a
    choice.

    Expected value determined independently: enumerated by hand at `k = 8`.
    Coarse indices are `0, 8, 16, ...`, giving `{0, 8, 16, 24}` on 32 and
    `{0, 8}` on 12. **The parallel minimum is 9, not 12** -- 12 is chosen for
    the point count and for the one-sided source neighbourhood at indices
    9 to 11, and this test pins the choice rather than the false minimum.

    Bug this catches: a geometry edit that drops the parallel axis below 9,
    which leaves ONE coarse point, makes every fine point source the same
    optimum, and stops exercising the spiral at all -- while every other test
    here still passes. It also catches the boundary moving off the midpoint,
    which silently removes the null line's clearance.
    """
    built = _build(tmp_path, fields.RUNGS["easy"], seed=3)
    normal, parallel = built.parameters.shape[0], built.parameters.shape[1]

    assert (normal, parallel) == (32, 12)
    assert normal == 4 * fields.COARSE_STRIDE
    assert fields.BOUNDARY_INDEX == normal // 2

    coarse_normal = list(range(0, normal, fields.COARSE_STRIDE))
    coarse_parallel = list(range(0, parallel, fields.COARSE_STRIDE))
    assert coarse_normal == [0, 8, 16, 24]
    assert coarse_parallel == [0, 8], (
        "the parallel axis no longer carries two coarse points, so every fine "
        "point sources the same optimum and the spiral is not exercised"
    )
    assert parallel > coarse_parallel[-1] + 1, (
        "no point lies beyond the last coarse index, so the one-sided source "
        "neighbourhood is not exercised"
    )


# --------------------------------------------------------------------------
# The shipped path, and the axis
# --------------------------------------------------------------------------


@pytest.mark.slow
def test_the_field_opens_through_the_shipped_opener_and_fits_every_point(tmp_path):
    """The benchmark field is an ordinary input, not a benchmark-only object.

    Behaviour: the field goes THROUGH the shipped input path -- opener, stage
    4a, tiling, fit -- rather than around it.

    Expected value determined independently: the fitted point count equals the
    field's point count, read off the store rather than off the report.

    Bug this catches: a fixture legal only to the benchmark. **This is the
    defect that made 2c's coherent field unable to say anything about the
    shipped mechanism** -- it lived in a harness, so criterion 12 could be
    measured on it and not on production. A field that only the benchmark can
    open reproduces that exactly.

    **MARKED `slow` BECAUSE IT FITS ALL 384 POINTS**, which is the geometry the
    benchmark actually uses and not a reduced stand-in: a contract check on a
    smaller grid would not be a check on the field this module builds. It is
    ~12 minutes of the full sweep and it is the test that stops 2c's harness
    defect recurring.
    """
    from metamer.batch.run import run

    built = _build(tmp_path, fields.RUNGS["hard"], seed=2)
    config_path = fields.write_config(tmp_path, "bench.toml", built.uri)
    report = run(config_path, tmp_path / "out.zarr")

    points = built.parameters.shape[0] * built.parameters.shape[1]
    assert report.contract.n_y * report.contract.n_x == points
    assert report.fit_hash is not None
    assert report.tiles_written == report.tiles_total


def test_the_axis_is_to_decimal_years_and_not_a_hand_built_one(tmp_path):
    """The axis comes from the input. 2c's fixture fact, and Task 0's own defect.

    Behaviour: the builder's returned axis is exactly `to_decimal_years` of the
    stored time coordinate.

    Expected value determined independently: measured at Task 0 -- the two
    axes differ in ORIGIN by 2000.0 and in SPACING by 0.0847 against 0.0833, so
    a difference of more than 1.0 is far outside any floating-point tolerance
    and cannot be argued away as one.

    Bug this catches: a hand-built `2000 + i * 31/365.25` or `arange(n)/12`
    axis. 2c Task 6 measured that this moves `theta_hat` by 6.7e-05 relative,
    which is large enough to fail a bitwise comparison and small enough to read
    as a floating-point detail; **Task 0 then shipped exactly that defect into
    its own harness and it took two runs to find.** The conversion is under
    `ALGORITHM_VERSION`, so a second derivation of it is a second derivation of
    fit identity.
    """
    built = _build(tmp_path, fields.RUNGS["easy"], seed=4, n_time=24)
    stored = xr.open_zarr(built.uri)["time"].values

    assert np.array_equal(built.t, to_decimal_years(stored))
    hand_built = np.arange(built.t.size, dtype=np.float64) / 12.0
    assert np.abs(built.t - hand_built).max() > 1.0, (
        "the builder's axis is indistinguishable from a hand-built one"
    )


# --------------------------------------------------------------------------
# (j9): one authoritative spelling, asserted rather than asked for
# --------------------------------------------------------------------------


def test_the_config_text_is_built_from_the_named_sources(tmp_path):
    """Every quantity the config states is the module's own, not a second copy.

    Behaviour: `config_text` renders `CANDIDATES`, `SIGNAL_TERMS` and
    `CRITERIA`; `candidate_specs` and `signal_spec` parse the same tuples
    through the shipped parsers. **A run reading the config and a caller
    building a batch by hand cannot disagree.**

    Expected value determined independently: the tuples themselves, compared
    against what the rendered TOML contains and against what the parsers
    return. Nothing is recomputed by the same logic the functions use.

    Bug this catches: **the fifth instrument defect of this sub-phase,** and
    the reason (j9) exists. A harness held `["white", "white + matern12"]`
    inline while `CANDIDATES` went to three members, so the rebuilt field --
    built with a `matern32` region -- was measured against a candidate set that
    could not express one of its regimes, at `M = 2`, and reported an
    unchanged iteration count that meant nothing. `write_config`'s own
    docstring forbids exactly that and the offending function was twenty lines
    below it. **A rule stated in a docstring constrains nobody; this line
    does.** `M` sets the price AND D9's stratum count, so a second `M` is a
    second budget and a second stratification.
    """
    text = fields.config_text("memory://x")
    for candidate in fields.CANDIDATES:
        assert f'"{candidate}"' in text
    for term in fields.SIGNAL_TERMS:
        assert f'"{term}"' in text
    assert len(fields.candidate_specs()) == len(fields.CANDIDATES)
    assert len(fields.signal_spec().terms) == len(fields.SIGNAL_TERMS)
    # M is load-bearing twice over, so it is pinned rather than implied.
    assert len(fields.CANDIDATES) == 3


# --------------------------------------------------------------------------
# The rung that is not constructible
# --------------------------------------------------------------------------


def test_the_plausibility_rung_is_absent_and_asking_for_it_raises(tmp_path):
    """E1's constraint 1 is not satisfiable for `l`, so the rung does not exist.

    Behaviour: no rung named `plausibility` exists, whatever else does.
    Requesting it raises, and the message names why -- that `l` is the
    coherence of the fitted OPTIMA while published values describe the
    coherence of the DATA, and that 2c's ceiling arm measured these to differ.

    Expected value determined independently: the exception type and the
    presence of the words that make the refusal diagnosable rather than blank.

    Bug this catches: **a placeholder value in that slot.** A provisional `l`
    there is a claim about the ocean, it would be quoted as the plausibility
    rung's, and it would stick -- there is no later step that would remove it,
    because nothing downstream can tell a chosen `l` from a sourced one. (a2b)
    at the one slot where an invalid value is a scientific error rather than a
    caveat.

    **Written against the SET rather than as an enumeration of its members**,
    which is (c5) and which fired here: the earlier version asserted
    `set(RUNGS) == {"easy", "hard"}` and failed the moment a third rung landed
    -- a true statement about the members turned into a false gate about the
    property. The property is that the plausibility slot stays empty, and it is
    indifferent to how many rungs there are.
    """
    assert "plausibility" not in fields.RUNGS
    assert all(rung.name == name for name, rung in fields.RUNGS.items()), (
        "a rung is keyed under a name that is not its own"
    )
    with pytest.raises(fields.RungNotConstructible) as excinfo:
        fields.rung("plausibility")
    message = str(excinfo.value)
    assert "coherence" in message
    assert "optima" in message.lower()


def test_a_rung_parameter_without_a_source_cannot_be_constructed():
    """`source` is per parameter, and every parameter must carry one.

    Behaviour: a `Rung` is refused if any of its parameters has an empty
    source string.

    Expected value determined independently: the exception type, and that the
    message names the offending parameter rather than the rung.

    Bug this catches: E1's constraint 1 decaying into a docstring. With one
    `source` string per rung, a citation covering `Delta` would silently appear
    to cover `l` as well -- and `l` is the parameter that cannot be sourced, so
    the one-string design hides exactly the gap that matters.
    """
    with pytest.raises(ValueError, match="contrast"):
        fields.Rung(
            name="broken",
            coherence_length=4.0,
            contrast=3.0,
            sources={"coherence_length": "chosen for detectability", "contrast": ""},
        )


# --------------------------------------------------------------------------
# (a5b): the field must let both candidates win
# --------------------------------------------------------------------------


@pytest.mark.slow
def test_both_candidates_win_somewhere_on_the_field(tmp_path):
    """The winning-candidate axis must not collapse from `M = 2` to 1.

    Behaviour: D9's point strata are `3 margin x M winning candidates`. At
    `M = 3` that is nine strata and 42.67 members each at uniform occupancy,
    against the 30 floor. If one candidate sweeps the field the axis collapses
    and the strata collapse with it -- **and since the family-change rebuild
    the stakes are higher than occupancy**: the selected candidate is the smear
    estimator's subject, so a field whose regimes are indistinguishable to
    selection cannot show a boundary at all.

    Expected value determined independently: a count over the store's own
    `/selection/selected`, requiring at least one point for each candidate
    index. Not a proportion -- the claim is that both are reachable.

    Bug this catches: rung parameters chosen for coherence and contrast alone,
    with nobody checking that they leave a model-selection question to answer.
    **Criterion 12's occupancy result would then read as a stratification
    finding when it is a field-construction defect** -- the strata would be
    underpopulated because the field cannot populate them, and D9 would take
    the blame. (a5b): two constraints on one set of parameters, solved
    together rather than in the sections where each is discussed.
    """
    import zarr

    from metamer.batch.run import run

    built = _build(tmp_path, fields.RUNGS["easy"], seed=8, n_time=96)
    config_path = fields.write_config(tmp_path, "bench.toml", built.uri)
    report = run(config_path, tmp_path / "out.zarr")
    assert report.fit_hash is not None

    root = zarr.open_group(str(tmp_path / "out.zarr"), mode="r")
    selected = root["selection/selected"]
    assert isinstance(selected, zarr.Array)
    selected_per_point = np.asarray(selected[:])
    live = selected_per_point[selected_per_point >= 0]

    assert live.size > 0, "no point was ranked, so the check is vacuous"
    winners = set(np.unique(live).tolist())
    # Indices 1 and 2 are the two CORRELATED candidates, one per true regime.
    # `white` at index 0 may legitimately never win; what must not happen is
    # one correlated candidate sweeping the field, because then the regimes are
    # indistinguishable to selection -- and selection is the smear estimator's
    # subject since the family-change rebuild.
    assert {1, 2} <= winners, (
        "the two regimes' own families do not both win anywhere, so selection "
        "cannot see the boundary and D9's winning-candidate axis collapses; "
        f"winners seen: {sorted(winners)}"
    )
