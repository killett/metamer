"""`metamer.bench.report`: the rung report, its gate and its instrument block.

**THE REPORT IS THE ARTIFACT AND THE DRIVER IS THE THIN PART.** §16.2 makes 2d's
measurements a benchmark rather than a test, so Task 9's exit criteria assert
against the COMMITTED reports -- which means the report's construction matters
more than the driver's, and it is what is tested here.

**EVERY TEST BELOW IS ON CONSTRUCTED READINGS.** `build_report` is a pure
function of the readings for exactly this reason: the driver itself cannot be
called at a testable size (384 points at 11-13 s each), and a field small enough
to be fast cannot carry the interior null at all -- the null needs
`n_normal // 2 - NULL_LINE_OFFSET_CELLS >= 1`, and the shipped offset is 12,
so `n_normal >= 26` before a legal null line exists. **`run_rung` is the benchmark
and its evidence is a committed report, not a test.**
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from metamer.batch.audit_report import Quantity
from metamer.bench import fields, report, smear
from metamer.bench.smear import WidthReading

_RUNG = fields.RUNGS["easy"]
_REACH = 32.0
_PROFILE = (0.0,) * 32


def _reading(
    *,
    cells: float | None = 5.0,
    at_floor: bool = False,
    refused: str | None = None,
    arm: str = "warm",
    profile: tuple[float, ...] = _PROFILE,
) -> WidthReading:
    """A constructed reading in any of the three states a smear can be in."""
    return WidthReading(
        cells=cells,
        at_floor=at_floor,
        floor_cells=smear.FLOOR_CELLS,
        reach_cells=_REACH,
        estimator=smear.ESTIMATOR,
        map_name=smear.AGREEMENT_MAP_NAME,
        arm=arm,
        refused=refused,
        profile=profile,
    )


_CLEAN_NULL = _reading(cells=None, at_floor=True, arm="warm")
_FIRED_NULL = _reading(cells=4.0, arm="warm")
_UNREADABLE_NULL = _reading(cells=None, refused="a row the run had to decide about")


def _block(**kwargs: Any) -> Any:
    """The instrument block at a small geometry."""
    kwargs.setdefault("n_time", 24)
    kwargs.setdefault("n_normal", 18)
    kwargs.setdefault("n_parallel", 2)
    kwargs.setdefault("seed", 7)
    return report.instrument_block(_RUNG, **kwargs)


def _report(
    *,
    null_line: WidthReading = _CLEAN_NULL,
    widths: dict[str, WidthReading] | None = None,
    cost: dict[str, float] | None = None,
    iterations: dict[str, float] | None = None,
) -> report.RungReport:
    """A report assembled from constructed readings."""
    return report.build_report(
        _RUNG,
        null_line=null_line,
        widths={} if widths is None else widths,
        instrument=_block(),
        cost={"cold_seconds": 1.5} if cost is None else cost,
        iterations={"cold_per_point": 24.375} if iterations is None else iterations,
        denominator=36,
    )


# ---------------------------------------------------------------------------
# Every number carries its rung
# ---------------------------------------------------------------------------


def test_a_quantity_without_a_rung_cannot_be_constructed():
    """E1's constraint 2, enforced by construction rather than by convention.

    Behaviour: `RungQuantity` requires the rung the number was measured on.

    Expected value determined independently: a required keyword-only field, so
    omitting it is a `TypeError` from the constructor rather than a validation
    message.

    Bug this catches: E1's constraint 2 decaying into a convention. A control's
    floor quoted without its rung reads as a statement about the ocean, and the
    easy rung exists precisely to produce numbers that must never be quoted that
    way. D8's argument is that LABELLING a number does not stop it being quoted
    -- the number must not exist.
    """
    with pytest.raises(TypeError):
        report.RungQuantity(  # type: ignore[call-arg]
            name="smear width", scope="rung=easy arm=warm", value=5.0, denominator=36
        )


def test_the_rung_quantity_inherits_the_scope_check_rather_than_restating_it():
    """One validator, not two spellings of one rule.

    Behaviour: `RungQuantity` subclasses `Quantity`, so a scopeless or
    half-stated quantity is refused by the shipped check.

    Expected value determined independently: `Quantity` refuses an empty scope
    and refuses a value beside a withheld reason; both must still refuse here,
    and a `RungQuantity` must still be a `Quantity` to everything downstream.

    Bug this catches: a 2d-local re-implementation of the scope refusal. Two
    spellings of one validator drift the first time either is edited -- (j9),
    which has fired five times in this sub-phase -- and the drift would be
    silent, because both versions accept every well-formed quantity.
    """
    assert issubclass(report.RungQuantity, Quantity)

    with pytest.raises(ValueError, match="no scope"):
        report.RungQuantity(
            name="smear width", scope="", value=5.0, denominator=36, rung=_RUNG
        )
    with pytest.raises(ValueError, match="never both and never neither"):
        report.RungQuantity(
            name="smear width",
            scope="rung=easy",
            value=5.0,
            denominator=36,
            withheld="also withheld",
            rung=_RUNG,
        )


def test_every_quantity_on_a_report_carries_the_rung_it_was_measured_on():
    """Present and withheld alike.

    Behaviour: `quantities()` and `withheld()` both return `RungQuantity`, so a
    number cannot reach a reader without its rung.

    Expected value determined independently: one arm produces a value and one is
    at the floor, so exactly one of each is expected, and both must carry the
    rung.

    Bug this catches: the withheld path building a plain `Quantity` because it
    has no value to attach a rung to. A withheld number is still reported --
    "the easy rung resolved nothing" is a claim about the easy rung -- and it is
    the half most likely to lose its label, because it looks like an absence
    rather than a result.
    """
    built = _report(
        widths={
            "cold": _reading(cells=None, at_floor=True, arm="cold"),
            "warm": _reading(cells=5.0, arm="warm"),
            "n2": _reading(cells=2.0, arm="n2"),
        }
    )

    for quantity in built.quantities() + built.withheld():
        assert isinstance(quantity, report.RungQuantity)
        assert quantity.rung is _RUNG
    assert len(built.quantities()) == 2
    assert len(built.withheld()) == 1


# ---------------------------------------------------------------------------
# The gate, both directions
# ---------------------------------------------------------------------------


def test_a_clean_null_leaves_every_smear_quantity_present():
    """The gate's negative half: a healthy rung reports its widths.

    Behaviour: a null at the floor and readable is clean, so the rung is not
    contaminated and the widths are reported.

    Expected value determined independently: a null with `at_floor` true and
    `refused` None; three arms each with a width.

    Bug this catches: an unfalsifiable gate in the OTHER direction -- one that
    marks every rung contaminated. It would look conservative and would withhold
    every number 2d produces, and because withheld quantities carry reasons the
    report would still look complete.
    """
    built = _report(widths={arm: _reading(cells=3.0, arm=arm) for arm in report.ARMS})

    assert built.contaminated is False
    assert len(built.quantities()) == len(report.ARMS)
    assert built.withheld() == ()
    assert report.require_clean(built) is built


def test_a_null_that_returns_a_width_contaminates_the_rung_and_stops_it():
    """The gate's positive half: E6's third row, which stops the sub-phase.

    Behaviour: a null that returns a width marks the rung contaminated, every
    smear quantity is withheld with the reason, and `require_clean` raises.

    Expected value determined independently: a null reading with `cells = 4.0`,
    which is neither at the floor nor refused. Three arms, so three withheld
    quantities and none present.

    Bug this catches: **a gate that cannot fire.** E6 calls this the clause most
    expected to fire and the one that gates the sub-phase; an unfalsifiable
    version licenses every smear number on every rung, which is the largest
    single failure available to 2d. Paired with the test above so neither half
    passes for a constant.
    """
    built = _report(null_line=_FIRED_NULL)

    assert built.contaminated is True
    assert built.quantities() == ()
    assert len(built.withheld()) == len(report.ARMS)
    for quantity in built.withheld():
        assert quantity.withheld is not None
        assert "interior null" in quantity.withheld

    with pytest.raises(report.RungContaminated, match="STOP AND DIAGNOSE"):
        report.require_clean(built)


def test_an_unreadable_null_also_contaminates_and_says_which_happened():
    """A refused null is not a null that passed.

    Behaviour: a null the estimator refused leaves the rung uncertified. It is
    treated as contaminated, and the reason distinguishes it from a null that
    fired.

    Expected value determined independently: a reading with `refused` set and
    `at_floor` false; the reason must mention that it could not be READ rather
    than that it returned a width.

    Bug this catches: `null_is_clean` written as `not fired` -- i.e. treating
    "the estimator would not answer" as "the estimator answered no". That is
    (a0)'s excluded-versus-missing register at a gate, and it fails in the
    permissive direction: a rung whose null could not be read would publish its
    widths.
    """
    built = _report(null_line=_UNREADABLE_NULL)

    assert built.contaminated is True
    reason = report.contamination_reason(_UNREADABLE_NULL)
    assert reason is not None
    assert "could not be read" in reason
    assert "returned a width" not in reason


def test_a_contaminated_rung_given_widths_anyway_is_refused_loudly():
    """On a contaminated rung the widths are NEVER COMPUTED, not computed and hidden.

    Behaviour: `build_report` refuses a contaminated rung that was handed
    widths, because that combination can only arise from a caller that computed
    them before checking the gate.

    Expected value determined independently: the refusal is unconditional on
    that combination; no value is inspected.

    Bug this catches: the driver computing every width and then withholding
    them. A withheld quantity would then have a real number behind it, and a
    determined reader with the object could recover it -- which is precisely the
    "a reading that exists can be read" failure the ordering exists to prevent.
    **The flag is not the mechanism; the ordering is**, and this refusal is what
    keeps the two from drifting apart.
    """
    with pytest.raises(ValueError, match="NEVER COMPUTED"):
        report.build_report(
            _RUNG,
            null_line=_FIRED_NULL,
            widths={"warm": _reading(cells=5.0)},
            instrument=_block(),
            cost={},
            iterations={},
            denominator=36,
        )


def test_the_null_reading_is_on_the_report_even_when_it_contaminated_it():
    """E6 says stop and DIAGNOSE, and a diagnosis is made of the profile.

    Behaviour: a contaminated report still carries the null's own reading,
    profile included.

    Expected value determined independently: the constructed profile is 32
    entries long and must survive onto the report and into `reproducible()`.

    Bug this catches: `run_rung` refusing to return, or the report dropping the
    null once it has set the flag. Either destroys the only evidence that would
    say WHY the null fired -- whether the estimator is reading the field's own
    structure, or the baseline disagreement rate is itself above a half, which
    are different faults with different repairs.
    """
    built = _report(null_line=_FIRED_NULL)

    assert built.null_line is _FIRED_NULL
    record = built.reproducible()["null_line"]
    assert record is not None
    assert len(record["profile"]) == 32


# ---------------------------------------------------------------------------
# A floor reading is not a withheld one
# ---------------------------------------------------------------------------


def test_a_floor_reading_and_a_refused_one_are_told_apart_on_the_report():
    """Three states, not two, and the last two are opposite claims.

    Behaviour: a width at the floor is a VALID reading with no number; a refused
    width is no reading at all. Both leave `Quantity.value` None, so the
    `WidthReading` beside it is what distinguishes them.

    Expected values determined independently: the floor entry keeps a reading
    with `at_floor` true and `refused` None; the refused entry keeps a reading
    with `refused` set; a contaminated rung's entry has **no reading at all**.

    Bug this catches: folding the two into one withheld state. "The instrument
    looked and resolved nothing" and "the instrument did not look" would then be
    the same bytes, and a reader supplies the more flattering -- which for a
    resolution floor is the one that reads as a measurement.
    """
    built = _report(
        widths={
            "cold": _reading(cells=None, at_floor=True, arm="cold"),
            "warm": _reading(cells=None, refused="beyond the reach", arm="warm"),
            "n2": _reading(cells=2.0, arm="n2"),
        }
    )
    entries = {entry.arm: entry for entry in built.smears}

    assert entries["cold"].reading is not None
    assert entries["cold"].reading.at_floor is True
    assert entries["cold"].quantity.withheld is not None
    assert "floor" in entries["cold"].quantity.withheld

    assert entries["warm"].reading is not None
    assert entries["warm"].reading.refused == "beyond the reach"
    assert entries["warm"].quantity.withheld == "beyond the reach"

    contaminated = _report(null_line=_FIRED_NULL)
    assert all(entry.reading is None for entry in contaminated.smears)


def test_a_floor_reading_carries_its_profile_or_it_has_recorded_nothing():
    """Task 2's forfeit, enforced where the artifact is built.

    Behaviour: the profile travels with every reading, floor readings included.

    Expected value determined independently: the constructed profile's length,
    32, must appear in the serialized record.

    Bug this catches: a report that records `<= 1 cell` and drops the profile.
    The majority rule is blind to a smear that never carries a cell past a half
    -- which is the shape a decaying artifact takes -- so a floor result is
    uninterpretable until its profile has been seen to be flat rather than
    sloped. Without it the report has recorded an absence of evidence as
    evidence of absence.
    """
    built = _report(
        widths={"cold": _reading(cells=None, at_floor=True, arm="cold")},
        iterations={"cold_per_point": 1.0},
    )
    record = built.reproducible()["smears"][0]

    assert record["value"] is None
    assert record["reading"] is not None
    assert len(record["reading"]["profile"]) == 32
    assert "read the profile" in record["withheld"]


# ---------------------------------------------------------------------------
# The instrument block is derived
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("module", "attribute", "replacement", "key"),
    [
        (smear, "ESTIMATOR", "some-other-estimator", "estimator"),
        (fields, "DRAW_METHOD", "svd", "draw_method"),
        (fields, "SMEAR_SUBJECT", "something else", "smear_subject"),
        (fields, "COARSE_STRIDE", 4, "coarse_stride"),
        (smear, "FLOOR_CELLS", 2.0, "floor_cells"),
        (smear, "MAJORITY", 0.75, "majority_threshold"),
    ],
)
def test_the_instrument_block_follows_the_constant_it_names(
    monkeypatch, module, attribute, replacement, key
):
    """Every value in the block is read from its source, not transcribed.

    Behaviour: moving the shipped constant moves the block.

    Expected value determined independently: the replacement value itself. Each
    pair is checked separately, so a block that derives one field and transcribes
    the next cannot pass.

    Bug this catches: **a transcribed instrument block** -- (j9)'s worst
    instance in this sub-phase was an instrument block that was itself a copy,
    the guard defeated by the defect it guards against. A transcribed block
    describes the configuration that was current when someone typed it, and
    Task 9's whole check is that a report's block still matches current
    defaults; a copy makes that check compare a literal against itself.
    """
    monkeypatch.setattr(module, attribute, replacement)

    assert _block()[key] == replacement


def test_a_changed_spiral_bound_is_visible_in_the_block_and_moves_the_reach():
    """The bound is described per run, not read once at import.

    Behaviour: `instrument_block` takes the `WarmStart` it should describe.

    Expected values determined independently: `spiral_bound = 2` with the
    shipped stride of 8 gives a reach of 16 fine cells, against 32 at the
    default.

    Bug this catches: an adopted verdict whose instrument is not in the record
    -- (j8). A report whose reach no longer describes the run that produced it
    would let a width refused under one configuration be admitted under another,
    with nothing in the artifact to show the boundary moved.
    """
    from metamer.config.model import WarmStart

    assert _block()["reach_cells"] == 32.0
    changed = _block(warm=WarmStart(spiral_bound=2))
    assert changed["spiral_bound"] == 2
    assert changed["reach_cells"] == 16.0


def test_the_block_records_the_rungs_own_per_parameter_sources():
    """The rung's provenance travels with every number drawn from it.

    Behaviour: `rung_sources` is the rung's `sources` mapping, whole.

    Expected value determined independently: `Rung.__post_init__` already
    refuses a rung without a source per parameter, so both keys must be present
    and non-empty in the block.

    Bug this catches: a block naming the rung and not its sources. The middle
    rung occupies the plausibility slot and a figure drawn from it is only
    honest while "chosen by us" travels with it -- a rung NAME does not carry
    that, and the name is what a reader would otherwise see.
    """
    block = _block()

    assert set(block["rung_sources"]) == {"coherence_length", "contrast"}
    assert all(value.strip() for value in block["rung_sources"].values())


def test_a_smoke_run_is_marked_in_the_block_and_not_in_a_filename():
    """A pipeline exercise must not be readable as a measurement.

    Behaviour: `is_a_smoke_run` is part of the instrument block.

    Expected value determined independently: the flag defaults to False and is
    True when asked for.

    Bug this catches: a reduced-geometry or short-record run being quoted. The
    flag is in the BLOCK rather than in a filename because a filename does not
    travel with the bytes -- a report copied into a document loses its name and
    keeps its contents.
    """
    assert _block()["is_a_smoke_run"] is False
    assert _block(is_a_smoke_run=True)["is_a_smoke_run"] is True


# ---------------------------------------------------------------------------
# Reproducible bytes, and the timing block that is not among them
# ---------------------------------------------------------------------------


def test_two_reports_differing_only_in_wall_clock_are_reproducibly_identical():
    """Timings are segregated, or a bitwise comparison is impossible in principle.

    Behaviour: `reproducible()` excludes `cost` and includes everything else.

    Expected value determined independently: two reports built from identical
    readings and different seconds must compare equal under `reproducible()` and
    unequal under `cost`.

    Bug this catches: wall clock leaking into the comparable part of the report.
    Every comparison of two runs would then fail for a reason that is not a
    defect, and the response to a check that always fails is to stop running it.
    """
    widths = {arm: _reading(cells=3.0, arm=arm) for arm in report.ARMS}
    first = _report(widths=dict(widths), cost={"cold_seconds": 1.0})
    second = _report(widths=dict(widths), cost={"cold_seconds": 99.0})

    assert first.reproducible() == second.reproducible()
    assert first.cost != second.cost


def test_iterations_are_on_the_reproducible_side_and_seconds_are_not():
    """The split is a measured fact, not a convention.

    Behaviour: `iterations` is inside `reproducible()`; `cost` is not.

    Expected value determined independently: measured 2026-08-31 -- the same
    fixture reproduced its iteration counts to every digit a day later while its
    seconds moved 15%, same host, same code, quiet in both runs. So iterations
    are something a later reader can check a committed report against and
    seconds are not.

    Bug this catches: putting iterations in the timing block because they are
    "performance numbers". The byte-identity invariant would then cover only the
    widths, and a change that moved every fit's iteration count -- a different
    optimizer path, a moved `ALGORITHM_VERSION` -- would not show up in a
    comparison of two reports.
    """
    reproducible = _report(iterations={"cold_per_point": 24.375}).reproducible()

    assert reproducible["iterations"] == {"cold_per_point": 24.375}
    assert "cost" not in reproducible


def test_a_report_is_self_describing_from_its_own_bytes():
    """A reader with the report and no other file can say what produced it.

    Behaviour: the serialized form names the field's geometry, the record
    length, the seed, the draw method, the candidate set with its spec hashes,
    the algorithm version, the estimator and the rung with its sources.

    Expected value determined independently: the list is the plan's own
    enumeration of what the report must record, checked key by key rather than
    by counting.

    Bug this catches: a report that is complete only alongside the code that
    wrote it. Task 9 asserts on COMMITTED reports, possibly long after; a report
    that needs the tree to interpret is a report that stops being checkable the
    moment the tree moves -- which is exactly the condition the instrument block
    exists to detect rather than to suffer.
    """
    instrument = _report().reproducible()["instrument"]

    for key in (
        "n_normal",
        "n_parallel",
        "boundary_index",
        "n_time",
        "seed",
        "draw_method",
        "candidates",
        "candidate_spec_hashes",
        "algorithm_version",
        "estimator",
        "reach_cells",
        "coarse_stride",
        "spiral_bound",
        "rung_sources",
    ):
        assert key in instrument, f"the report cannot say what {key!r} was"
    assert len(instrument["candidate_spec_hashes"]) == len(fields.CANDIDATES)


def test_an_arm_that_did_not_run_is_withheld_rather_than_absent():
    """Silence and absence are the same bytes, so neither is used.

    Behaviour: an arm named in `arms` with no reading produces a withheld
    quantity carrying the reason, not a missing entry.

    Expected value determined independently: two arms requested, one supplied,
    so two entries and one withheld.

    Bug this catches: a report that simply omits the arms a rung did not run.
    E2 allocates N1 to two rungs of three, so "this arm did not run here" is an
    ordinary and expected state -- and omitting it makes a deliberate allocation
    indistinguishable from a failure.
    """
    built = report.build_report(
        _RUNG,
        null_line=_CLEAN_NULL,
        widths={"cold": _reading(cells=3.0, arm="cold")},
        instrument=_block(),
        cost={},
        iterations={},
        denominator=36,
        arms=("cold", "n2"),
    )

    assert len(built.smears) == 2
    withheld = built.withheld()
    assert len(withheld) == 1
    assert withheld[0].withheld is not None
    assert "did not run" in withheld[0].withheld


# ---------------------------------------------------------------------------
# The saving, with pass 1 in it
# ---------------------------------------------------------------------------


def test_the_saving_is_reported_with_pass_one_and_without_it():
    """Two readings, both named, because a reader means the net one.

    Behaviour: `saving` returns the pass-2-only figure and the net figure,
    which charges pass 1's coarse fits to the warm arm.

    Expected value determined independently: hand-computed. Cold is 1000
    iterations, pass 2 is 600 and pass 1 is 40, so the pass-2-only saving is
    `1 - 600/1000 = 40%` and the net is `1 - 640/1000 = 36%`.

    Bug this catches: **a saving that omits pass 1 entirely**, which is what
    the report could express before this function existed -- D11 gives pass 1
    its own store, so `iteration_count(warm_store)` counts pass 2 alone. The
    omission is small (the coarse grid is 8 points of 384 on this geometry) and
    it is always in the flattering direction, which is the combination that
    survives review.
    """
    got = report.saving(cold_total=1000, warm_total=600, pass1_total=40)

    assert got.pass2_only == pytest.approx(0.40)
    assert got.net == pytest.approx(0.36)
    assert got.net is not None
    assert got.pass2_only is not None
    assert got.net < got.pass2_only


def test_a_saving_against_a_cold_arm_that_did_nothing_is_refused():
    """No cold work is no saving, and it is not 100%.

    Behaviour: with a zero cold total the saving is None and the refusal says
    why.

    Expected value determined independently: the degenerate input, whose ratio
    is undefined rather than large.

    Bug this catches: dividing by zero and reporting `1.0` -- a **100% saving**
    -- which is the most quotable number this sub-phase could emit and would be
    produced by a run where nothing was fitted at all. E6's upper refutation
    clause fires on a saving at or above the ceiling, so the defect would fire
    it for the one reason that is not about the source map.
    """
    got = report.saving(cold_total=0, warm_total=0, pass1_total=0)

    assert got.pass2_only is None
    assert got.net is None
    assert got.refused is not None


def test_the_deterministic_readings_travel_on_the_reproducible_side():
    """Ratios and cross-checks are things the run determines, so they are in.

    Behaviour: `reproducible()` carries the iteration ratios and the
    cross-check results; `cost` stays out of it.

    Expected value determined independently: the constructed report's own
    inputs, looked up by key.

    Bug this catches: a deterministic reading being filed with the timings,
    where the byte-identity invariant does not reach it. **The invariant is
    "everything the run determines"**, not "the numbers that happen not to be
    timings", and an N1/cold ratio that differed between two runs of one rung
    would then be invisible -- which is exactly the defect the ratio exists to
    detect in the arms.
    """
    got = report.build_report(
        _RUNG,
        null_line=_CLEAN_NULL,
        widths={},
        instrument=_block(),
        cost={"cold_seconds": 1.5},
        iterations={"cold_per_point": 24.375},
        denominator=36,
        ratios={"n1_over_cold": 1.0017, "self_over_cold": 0.05},
        checks={"cold_arm_matches_the_store": True},
    )

    record = got.reproducible()

    assert record["ratios"]["n1_over_cold"] == pytest.approx(1.0017)
    assert record["checks"]["cold_arm_matches_the_store"] is True
    assert "cost" not in record


def test_the_block_records_the_audit_seed_the_map_was_keyed_on():
    """The seed is in the instrument block, because the map is keyed on it.

    Behaviour: `instrument_block` records the audit seed it is given, beside
    the field's own seed.

    Expected value determined independently: the two constants, which differ,
    so a block that recorded one where the other belongs is visible.

    Bug this catches: a report whose N2 map cannot be reproduced. **The drawn
    directions are keyed on the audit seed**, so a block carrying only the
    field's seed describes a field it can rebuild and a floor arm it cannot --
    and exit criterion 9 compares the map against the audit's own arm, which
    reads its seed from the config.
    """
    block = _block(audit_seed=4242)

    assert block["audit_seed"] == 4242
    assert block["seed"] == 7


def test_a_fine_point_that_sources_itself_is_counted_and_a_coarse_one_is_not():
    """D12 gives a point its own optimum only where it IS the coarse fit.

    Behaviour: `_self_sourced_fine_points` counts points at source radius 0
    that are not on the coarse lattice.

    Expected value determined independently: a constructed radius array on a
    4 x 4 grid at stride 2. The coarse points are `(0,0) (0,2) (2,0) (2,2)`;
    zero radius is placed at one of them and at `(1, 1)`, which is not one, so
    the count is exactly 1.

    Bug this catches: **the source map handing fine points their own optimum**,
    which is what E6's upper refutation clause describes and which would read
    as a spectacular saving rather than as a defect -- 2c measured a
    self-sourced fit returning the cold optimum at 99.58% agreement, so the
    warm arm would look like the ceiling. Counting coarse points as offenders
    would be the mirror defect: D12 says a coarse point's source IS itself, so
    a check that flagged them would fire on every correct run.
    """
    radius = np.full((16, 1), 3, dtype=np.int64)
    radius[0 * 4 + 0] = 0  # coarse, and legitimate
    radius[1 * 4 + 1] = 0  # fine, and the defect

    offenders = report._self_sourced_fine_points(radius, (4, 4), 2)

    assert offenders == 1
