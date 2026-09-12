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

import json
from typing import Any

import numpy as np
import pytest

from metamer.batch.audit import Arm
from metamer.batch.audit_report import Quantity, audit_report
from metamer.bench import arms as bench_arms
from metamer.bench import fields, report, smear
from metamer.bench.smear import WidthReading
from metamer.core.outcomes import Outcome

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
    strata: Any = None,
    arm_arrays: Any = None,
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
        strata=strata,
        arm_arrays=arm_arrays,
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
        (fields, "FIELD_CONSTRUCTION_VERSION", 99, "field_construction_version"),
        (fields, "SIGNAL_RISE_SIGMAS", 3.5, "drawn_signal_rise_sigmas"),
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

    # **(c5): THIS IS AN ENUMERATION OVER A SET THAT GROWS, AND IT DOES NOT
    # DEMAND ITS OWN COMPLETENESS.** A key added to `instrument_block` and left
    # out of this list is a key nothing requires -- so it can be deleted later
    # and every test still passes. The list has grown three times in 2d; the
    # note is here so a fourth addition meets it. **A key added to the block
    # gets its line here in the SAME edit**, and if it names a shipped constant
    # it also gets a row in the parametrized derivation test above, which is
    # what stops it being transcribed rather than read.
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
        "field_construction_version",
        "drawn_signal_terms",
        "drawn_signal_rise_sigmas",
    ):
        assert key in instrument, f"the report cannot say what {key!r} was"
    assert len(instrument["candidate_spec_hashes"]) == len(fields.CANDIDATES)


def test_the_block_says_what_the_builder_drew_and_not_only_what_the_config_fits():
    """The two signal keys are different questions, and both are answered.

    Behaviour: `signal_terms` names the terms the CONFIG FITS; the drawn-signal
    keys name the terms the BUILDER DREW. A block must answer both, and they
    must not be the same key.

    Expected values determined independently: from the two shipped constants,
    which describe different objects -- a model with a constant and a trend,
    and a drawn signal that is a trend alone because the offset was measured to
    change nothing.

    Bug this catches: **the defect wearing the report's clothes.** Three
    committed reports carry `signal_terms = constant, trend` over fields whose
    signal was identically zero, because the only signal key in the block named
    the model. A reader with the report could not tell a signal-free field from
    a signal-bearing one. This fails if the drawn keys are dropped, or if
    someone "simplifies" by making one key serve both -- which would
    reinterpret those three artifacts instead of distinguishing them.
    """
    instrument = _block()

    assert instrument["signal_terms"] == list(fields.SIGNAL_TERMS)
    assert instrument["drawn_signal_terms"] == list(fields.DRAWN_SIGNAL_TERMS)
    assert instrument["signal_terms"] != instrument["drawn_signal_terms"], (
        "the terms the config fits and the terms the builder draws are the "
        "same list, so the block cannot distinguish the model from the data"
    )


def test_the_block_reports_the_construction_that_was_built_not_the_default():
    """A rebuilt older construction is described as what it is.

    Behaviour: `instrument_block` takes the construction version of the field
    that was actually built, and only falls back to the shipped constant when
    no version is given.

    Expected value determined independently: version 1 is the signal-free
    construction the three shipped rungs were measured on, named in
    `fields.CONSTRUCTIBLE_VERSIONS`, and it is not the current default.

    Bug this catches: a block that reads the version from the constant, so that
    **a report of a rebuilt version 1 field would claim to be version 2**. That
    is the transcription failure this block exists to prevent, arriving through
    a default instead of a literal -- and it would be invisible exactly when it
    matters, since the two agree on every run that does not rebuild.
    """
    assert 1 in fields.CONSTRUCTIBLE_VERSIONS
    assert fields.FIELD_CONSTRUCTION_VERSION != 1

    rebuilt = _block(construction_version=1)

    assert rebuilt["field_construction_version"] == 1
    assert _block()["field_construction_version"] == fields.FIELD_CONSTRUCTION_VERSION


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


# ---------------------------------------------------------------------------
# The audit's strata on a rung report -- W2, W10 and W1's top-level key
# ---------------------------------------------------------------------------


def _audit_report(batch: int = 40, *, differing: int = 0) -> Any:
    """A real `AuditReport` over constructed arms, not a stand-in.

    **CONSTRUCTED ARMS AND A REAL REPORT.** The lift under test walks whatever
    `AuditReport.quantities()` returns, so a hand-built stand-in would test the
    stand-in's shape; the point is that every quantity the SHIPPED report
    produces arrives lifted.
    """
    from tests.test_audit_report import _arms, _result

    ok = Outcome.OK.code
    cold_best = np.zeros(batch, dtype=np.int64)
    warm_best = cold_best.copy()
    warm_best[:differing] = 1
    outcome = np.full((batch, 2), ok, dtype=np.uint8)
    return audit_report(
        _arms(
            _result(batch, outcome=outcome, best_index=cold_best),
            _result(batch, outcome=outcome, best_index=warm_best),
        ),
        trend_column=1,
    )


def test_every_audit_quantity_on_a_rung_report_carries_the_rung_too():
    """W2: E1's constraint 2 covers the audit's numbers or it covers nothing.

    Behaviour under test: with an audit section attached, `quantities()` and
    `withheld()` still return only `RungQuantity`.

    Expected value determined independently: E1's constraint 2 is *"every
    emitted number carries its rung"*, enforced by construction because D8's
    own argument is that labelling a number does not stop it being quoted.
    `audit_report` emits plain `Quantity`, so an unlifted section would break
    the rule while every existing test in this module still passed.

    Bug this catches: the audit's strata serialised straight into the rung
    report, where some numbers carry their rung by construction and some carry
    it by happening to sit in a file that names one. (h4) -- a rule stated over
    "every emitted number" checked against each KIND of number.
    """
    built = _report(strata=_audit_report(batch=40, differing=8))

    emitted = built.quantities() + built.withheld()
    assert len(emitted) > len(_report().quantities() + _report().withheld())
    for quantity in emitted:
        assert isinstance(quantity, report.RungQuantity), quantity.name
        assert quantity.rung is _RUNG
        assert quantity.scope


def test_a_quantity_added_to_the_audit_report_cannot_reach_a_rung_unlifted():
    """W2/(c5): the lift is written against the SET, not against its members.

    Behaviour under test: a quantity this module has never heard of, appearing
    in `AuditReport.quantities()`, still arrives lifted.

    Expected value determined independently: (c5) -- a gate over a set that can
    grow must be written against the set. `AuditReport.quantities()` is that
    set and it has grown twice already; the stand-in adds one more member and
    the lift must cover it without being told.

    Bug this catches: a lift enumerating `cell_strata`, `point_strata` and
    `candidates` by hand. It passes every test here on the day it is written
    and silently drops the next metric anybody adds -- which is exactly how the
    criterion-12 guard came to check only a document's top level.
    """

    class _Grown:
        """Only what the lift is allowed to depend on."""

        def quantities(self) -> tuple[Quantity, ...]:
            return (
                Quantity(
                    name="a_metric_invented_after_the_lift_was_written",
                    scope="stratum=invented",
                    value=0.25,
                    denominator=4,
                ),
            )

        def withheld(self) -> tuple[Quantity, ...]:
            return ()

    built = _report(strata=_Grown())
    names = {q.name for q in built.quantities()}

    assert "a_metric_invented_after_the_lift_was_written" in names
    lifted = next(
        q
        for q in built.quantities()
        if q.name == "a_metric_invented_after_the_lift_was_written"
    )
    assert isinstance(lifted, report.RungQuantity)
    assert lifted.rung is _RUNG
    assert lifted.value == 0.25 and lifted.denominator == 4


def test_the_lift_changes_the_rung_and_nothing_else_about_a_quantity():
    """The adapter adds a field; it does not restate the scope.

    Behaviour under test: name, scope, value, denominator and withheld survive
    the lift unchanged, for a quantity with a value and for a withheld one.

    Expected values determined independently: the two source quantities are
    written here by hand, and `RungQuantity`'s docstring says it *"adds one
    required field and nothing else"* -- folding the rung into the scope string
    would be the second spelling of one validator.

    Bug this catches: a lift that rewrites the scope to `f"rung={rung.name}
    {scope}"`, which makes two runs' strata incomparable and defeats the reason
    the boundaries are recorded with the figures.
    """
    present = Quantity(
        name="selection_move",
        scope="winner=abc margin=margin_lt_2",
        value=0.5,
        denominator=8,
    )
    absent = Quantity(
        name="selection_dropout",
        scope="winner=abc margin=margin_ge_10",
        value=None,
        denominator=3,
        withheld="3 members is below the floor",
    )

    class _Two:
        def quantities(self) -> tuple[Quantity, ...]:
            return (present, absent)

        def withheld(self) -> tuple[Quantity, ...]:
            return (absent,)

    built = _report(strata=_Two())
    # `quantities()` carries the ones with a value and `withheld()` the ones
    # without -- a withheld quantity is absent from the first BY DEFINITION, so
    # both surfaces are read or half the lift is untested.
    valued = {q.name: q for q in built.quantities()}
    silent = {q.name: q for q in built.withheld()}

    assert valued["selection_move"].scope == present.scope
    assert valued["selection_move"].value == 0.5
    assert valued["selection_move"].denominator == 8
    assert valued["selection_move"].withheld is None
    assert isinstance(silent["selection_dropout"], report.RungQuantity)
    assert silent["selection_dropout"].rung is _RUNG
    assert silent["selection_dropout"].scope == absent.scope
    assert silent["selection_dropout"].value is None
    assert silent["selection_dropout"].denominator == 3
    assert silent["selection_dropout"].withheld == "3 members is below the floor"


def test_the_strata_are_inside_the_reproducible_record_under_that_exact_key():
    """W10 and W1: deterministic, and named so the designed guard can see it.

    Behaviour under test: `reproducible()` carries the audit section under the
    top-level key `strata`, and the wall clock is still outside it.

    Expected values determined independently: the strata read the COLD and WARM
    arms only -- no N2 direction enters any of them -- so they carry no
    randomness and belong on the deterministic side, where two runs of one rung
    must agree byte for byte. The key name is `strata` because 2d's criterion
    12 guard looks for that word, and routing around a designed guard is how a
    reduced scope goes stale.

    Bug this catches two ways: the strata left out of `reproducible()`, so two
    runs could differ in them and still compare identical; and the section
    filed under a key the criterion-12 reminder cannot see, which would let the
    wiring land without the criterion ever being re-evaluated.
    """
    built = _report(strata=_audit_report(batch=40, differing=8))
    record = built.reproducible()

    assert "strata" in record
    assert record["strata"] is not None
    assert "cost" not in record
    assert "point_strata" in record["strata"]
    assert "seed" in record["strata"]
    # A rung with no audit section says so rather than omitting the key: an
    # absent key and a null are the same bytes to a reader who expected one.
    assert _report().reproducible()["strata"] is None


def test_a_rung_report_carries_the_unreachable_bins_and_the_membership_counts():
    """W3: what the treatment moves is membership, so the rung report says so.

    Behaviour under test: the serialised strata carry `unreachable_kappa_bins`
    and, per candidate, the per-arm `DEGENERATE_HESSIAN` counts and the
    intersection fraction.

    Expected values determined independently: `HESSIAN_COND_LIMIT` is
    `float(EPS) ** -0.5`, which IS D9's first boundary, so the two upper bins
    cannot be occupied by any cell in the both-OK intersection -- the
    stratification has ONE reachable bin on this population and a reader must
    not read a single populated bin as the axis working.

    Bug this catches: a rung report whose `κ` strata look populated and
    informative while the axis is degenerate, with the start-dependence that
    actually moved the map -- open question 23's subject -- nowhere on the page.
    """
    built = _report(strata=_audit_report(batch=40, differing=8))
    record = built.reproducible()["strata"]

    assert record["unreachable_kappa_bins"] == [
        "kappa_2^26_to_2^52",
        "kappa_ge_2^52",
    ]
    assert record["candidates"], "the membership counts are the W3 surface"
    for entry in record["candidates"]:
        assert "cold_degenerate" in entry
        assert "warm_degenerate" in entry
        assert "both_ok_fraction" in entry
    assert any("no pooled" in note.lower() for note in record["notes"])


def test_the_decomposition_reaches_the_rung_report_and_not_only_the_pooled_rate():
    """W12: the two cannot come apart in the artifact a reader quotes from.

    Behaviour under test: each serialised point stratum carries the three
    counts beside the pooled rate, and the headlines carry both new metrics.

    Expected values determined independently: the fixture gives 8 of 40 points
    a different warm winner with every candidate `OK` in both arms, so all 8
    are MOVES by construction -- `differing = 8`, `by_move = 8`,
    `by_dropout = 0`.

    Bug this catches: the decomposition computed in `audit_report`, dropped by
    the serialiser, and a committed report carrying the pooled rate alone --
    which is the exact defect this whole wiring exists to remove, surviving one
    layer further out.
    """
    built = _report(strata=_audit_report(batch=40, differing=8))
    record = built.reproducible()["strata"]

    populated = [s for s in record["point_strata"] if s["members"]]
    assert populated
    assert sum(s["differing"] for s in populated) == 8
    assert sum(s["by_move"] for s in populated) == 8
    assert sum(s["by_dropout"] for s in populated) == 0
    assert sum(s["by_both_unavailable"] for s in populated) == 0
    for stratum in populated:
        assert "selection_disagreement" in stratum
        assert "selection_move" in stratum
        assert "selection_dropout" in stratum

    names = {h["name"] for h in record["headlines"]}
    assert {"selection_disagreement", "selection_move", "selection_dropout"} <= names


def test_the_drivers_positive_control_refuses_before_anything_is_fitted():
    """W6: the control is true of the artifact, not of the test suite.

    Behaviour under test: `decomposition_selftest` raises when the rule cannot
    separate a move from a dropout, and the message says the count is a
    statement about the instrument.

    Expected value determined independently: (i2) -- `MOVE = 0` and "the rule
    cannot see a move" are the same integer. The control's construction and its
    expected `(differing, move, dropout) = (2, 1, 1)` come from the spike's
    committed addendum, which is where the zero it guards was recorded.

    Bug this catches: a broken decomposition rule shipping a `MOVE = 0` into a
    committed report. `run_rung` is excluded from `pixi run test`, so the unit
    tests of the rule never execute in the process that writes the number --
    only an in-process refusal covers that, and only if it RAISES rather than
    warns.
    """
    import metamer.batch.audit_report as audit_report_module

    # It passes on the shipped rule, or the control is asserting nothing.
    audit_report_module.decomposition_selftest()

    original = audit_report_module.selection_decomposition
    try:
        audit_report_module.selection_decomposition = lambda **kwargs: (
            audit_report_module.SelectionSplit(
                live=np.ones(3, dtype=bool),
                differs=np.array([True, True, False]),
                move=np.zeros(3, dtype=bool),
                dropout=np.array([True, True, False]),
                both_unavailable=np.zeros(3, dtype=bool),
            )
        )
        with pytest.raises(AssertionError, match="cannot separate a move"):
            audit_report_module.decomposition_selftest()
    finally:
        audit_report_module.selection_decomposition = original


# ---------------------------------------------------------------------------
# The selection-map report: the estimator's subject, in the artifact
# ---------------------------------------------------------------------------


def _arm_arrays(batch: int = 40, *, differing: int = 0, dropouts: int = 0) -> Any:
    """A real `arm_arrays_record` over constructed arms.

    The first `differing` points select differently in the warm arm; of those,
    the first `dropouts` are dropouts by construction -- the warm arm lost the
    candidate cold selected -- and the rest are moves by construction.
    """
    from tests.test_audit_report import _arms, _result

    ok, bad = Outcome.OK.code, Outcome.DEGENERATE_HESSIAN.code
    cold_best = np.zeros(batch, dtype=np.int64)
    warm_best = cold_best.copy()
    warm_best[:differing] = 1
    cold_outcome = np.full((batch, 2), ok, dtype=np.uint8)
    warm_outcome = np.full((batch, 2), ok, dtype=np.uint8)
    warm_outcome[:dropouts, 0] = bad

    cold = _result(batch, outcome=cold_outcome, best_index=cold_best)
    warm = _result(batch, outcome=warm_outcome, best_index=warm_best)
    arms = _arms(cold, warm)
    return report.arm_arrays_record(
        arms=arms,
        self_result=cold,
        grid_shape=(batch, 1),
        models=[spec.spec_hash() for spec in cold.candidates],
        store_maps={"cold_store": np.asarray(cold_best, dtype=np.int16)},
    )


def test_the_decomposition_is_re_derivable_from_the_artifact_alone():
    """U1: the arrays are a lookup, not a claim. The whole justification.

    Behaviour under test: feeding the artifact's per-arm maps and outcomes back
    through the SHIPPED `selection_decomposition` reproduces, per stratum, the
    `differing` / `by_move` / `by_dropout` / `by_both_unavailable` counts the
    report computed in memory.

    Expected values determined independently: the report's counts come from
    `audit_report`'s `_point_strata`, which walks `FitResult` objects; the
    round-trip walks JSON-shaped lists. **Two paths, one answer** -- and the
    fixture is built with 8 differing points of which 3 are dropouts by
    construction and 5 are moves by construction, so the expected split is
    known before either path runs.

    Bug this catches: an artifact carrying arrays nobody can reconstruct the
    finding from -- 142 KB spent on an argument rather than a lookup, which is
    the exact failure the size question exists to prevent. **The rule is not
    respelled here**: a second spelling would make this a comparison of the
    artifact against itself.
    """
    batch, differing, dropouts = 40, 8, 3
    from tests.test_audit_report import _arms, _result

    ok, bad = Outcome.OK.code, Outcome.DEGENERATE_HESSIAN.code
    cold_best = np.zeros(batch, dtype=np.int64)
    warm_best = cold_best.copy()
    warm_best[:differing] = 1
    cold_outcome = np.full((batch, 2), ok, dtype=np.uint8)
    warm_outcome = np.full((batch, 2), ok, dtype=np.uint8)
    warm_outcome[:dropouts, 0] = bad
    cold = _result(batch, outcome=cold_outcome, best_index=cold_best)
    warm = _result(batch, outcome=warm_outcome, best_index=warm_best)
    arms = _arms(cold, warm)

    in_memory = audit_report(arms, trend_column=1)
    record = report.arm_arrays_record(
        arms=arms,
        self_result=cold,
        grid_shape=(batch, 1),
        models=[spec.spec_hash() for spec in cold.candidates],
        store_maps={},
    )
    round_trip = report.decomposition_from_record(record)

    expected = {
        (s.candidate, str(s.margin)): (
            s.differing,
            s.by_move,
            s.by_dropout,
            s.by_both_unavailable,
        )
        for s in in_memory.point_strata
        if s.members
    }
    assert round_trip == expected
    # The fixture must actually carry both kinds, or the agreement is vacuous.
    assert sum(v[1] for v in expected.values()) == differing - dropouts
    assert sum(v[2] for v in expected.values()) == dropouts


def test_the_round_trip_fails_on_a_REORDERED_array_and_not_only_a_missing_one():
    """U1's teeth. A round-trip that only catches absence is the pure negative.

    Behaviour under test: permuting one arm's selection map -- same length,
    same multiset of values, same keys present -- changes the re-derived
    counts.

    Expected value determined independently: the artifact records
    `ARM_ARRAY_ORDER` because `field_arms`' own shape check catches a wrong
    COUNT and not a wrong ORDER. If a permutation did not move these counts,
    that documentation would be guarding nothing.

    Bug this catches: a serialiser that writes the arrays in tile order, or a
    reader that reshapes column-major. Both preserve every length and every
    value and silently re-key the map -- and the first consumer to plot it gets
    a picture, and a wrong one.
    """
    record = _arm_arrays(batch=40, differing=8, dropouts=3)
    good = report.decomposition_from_record(record)

    warm = dict(record["per_arm"][str(Arm.WARM)])
    warm["selected"] = list(reversed(warm["selected"]))
    permuted = dict(record)
    permuted["per_arm"] = dict(record["per_arm"]) | {str(Arm.WARM): warm}

    assert sorted(warm["selected"]) == sorted(
        record["per_arm"][str(Arm.WARM)]["selected"]
    ), "the permutation must preserve the multiset, or it is a content change"
    assert report.decomposition_from_record(permuted) != good


def test_the_round_trip_fails_on_a_TRUNCATED_array_and_says_so():
    """U1's other tooth: a short array must not quietly decompose a prefix.

    Behaviour under test: dropping the last entries of one arm's outcome grid
    raises rather than returning counts over whatever aligned.

    Expected value determined independently: numpy's own broadcasting rule --
    an `(n-1, M)` outcome grid cannot be indexed by `n` rows -- so the failure
    is structural rather than a length check somebody remembered to write.

    Bug this catches: a truncated write that still parses. Counts over a prefix
    are plausible, smaller than the truth, and wrong in the flattering
    direction; nothing else in this module compares lengths.
    """
    record = _arm_arrays(batch=40, differing=8, dropouts=3)
    warm = dict(record["per_arm"][str(Arm.WARM)])
    warm["outcome"] = warm["outcome"][:-5]
    truncated = dict(record)
    truncated["per_arm"] = dict(record["per_arm"]) | {str(Arm.WARM): warm}

    with pytest.raises(IndexError):
        report.decomposition_from_record(truncated)


def test_the_artifact_names_its_grid_shape_and_its_order():
    """U2: a flat list has no order but the one it is documented to have.

    Behaviour under test: the record carries `grid_shape` and `order`, and
    reshaping a per-arm map by that shape round-trips to the grid.

    Expected values determined independently: `field_arms` documents row-major
    over `(n_normal, n_parallel)`; the shape is the one the record was built
    with.

    Bug this catches: a consumer reshaping column-major, or a grid shape absent
    so the consumer guesses. `field_arms`' shape check catches a wrong count
    and not a wrong order, so nothing upstream would notice.
    """
    record = _arm_arrays(batch=12)

    assert record["grid_shape"] == [12, 1]
    assert "row-major" in record["order"]
    flat = record["per_arm"][str(Arm.COLD)]["selected"]
    assert np.asarray(flat).reshape(record["grid_shape"]).shape == (12, 1)


def test_the_two_selection_sentinels_survive_distinctly_and_are_named():
    """U3: `-1` and `-2` are two facts, and in JSON they are two numbers.

    Behaviour under test: a store map carrying both sentinels round-trips with
    both intact, and the record names each.

    Expected values determined independently: `store.SELECTED_UNSET` is -2 and
    means "nothing wrote here"; -1 means "a fit ran and no candidate won".

    Bug this catches: the two merged, or a consumer indexing the model axis
    with either and getting a model. The vocabulary travels with the values
    because a recorded value's meaning is part of its identity.
    """
    from tests.test_audit_report import _arms, _result

    cold = _result(6)
    arms = _arms(cold, cold)
    record = report.arm_arrays_record(
        arms=arms,
        self_result=cold,
        grid_shape=(6, 1),
        models=[spec.spec_hash() for spec in cold.candidates],
        store_maps={"cold_store": np.array([0, -1, -2, 1, -1, -2], dtype=np.int16)},
    )

    assert record["stores"]["cold_store"] == [0, -1, -2, 1, -1, -2]
    assert record["selection"]["-1"] != record["selection"]["-2"]
    assert "no candidate won" in record["selection"]["-1"]
    assert "nothing wrote here" in record["selection"]["-2"]


def test_every_arm_the_driver_fits_reaches_the_artifact():
    """U4/(c5): written against the set of arms, not an enumeration of it.

    Behaviour under test: the record's arm keys are exactly the audit's four
    plus the ceiling arm.

    Expected value determined independently: `Arm` is the audit's own
    enumeration and `SELF_ARM` is the benchmark's fifth; both are read from the
    shipped constants here rather than typed out.

    Bug this catches: a sixth arm added later and silently absent from the
    artifact -- which is exactly how `κ` for three of four arms came to be
    computed by the fit and read by nothing.
    """
    record = _arm_arrays(batch=10)
    expected = {str(arm) for arm in Arm} | {bench_arms.SELF_ARM}

    assert set(record["per_arm"]) == expected
    for arm in expected:
        assert set(record["per_arm"][arm]) == {"selected", "outcome", "hessian_cond"}


def test_the_kappa_array_is_full_precision_and_absence_is_null_not_zero():
    """U5 and U6 together: the array OQ23 needs, and the fill that would ruin it.

    Behaviour under test: a finite condition number round-trips to the exact
    float, and a NaN one becomes `null`.

    Expected values determined independently: `float.hex` round-trips exactly
    for float64; `0.0` is the most well-conditioned value there is, so a zero
    fill would read as the exact opposite of "no positive-definite Hessian".
    The `kappa_undefined` bin was populated on both smoke seeds, so NaN is the
    ordinary case here and not a corner.

    Bug this catches two ways: `κ` truncated to six significant figures, which
    halves the artifact by foreclosing the question it exists for; and NaN
    written as `0.0`, which is (a0) -- a fill value a successful run can
    produce.
    """
    from tests.test_audit_report import _arms, _result

    awkward = 12345678.901234567
    cond = np.full((4, 2), awkward)
    cond[1, 0] = np.nan
    cold = _result(4, hessian_cond=cond)
    record = report.arm_arrays_record(
        arms=_arms(cold, cold),
        self_result=cold,
        grid_shape=(4, 1),
        models=[spec.spec_hash() for spec in cold.candidates],
        store_maps={},
    )
    kappa = record["per_arm"][str(Arm.COLD)]["hessian_cond"]

    assert kappa[0][0] == awkward
    assert kappa[0][0].hex() == awkward.hex()
    assert kappa[1][0] is None
    assert json.loads(json.dumps(kappa))[1][0] is None


def test_the_arrays_are_in_the_reproducible_record_and_add_no_other_key():
    """U7: the task adds arrays and does not become a schema change.

    Behaviour under test: `reproducible()` gains `arm_arrays` and nothing else,
    and the section is None on a report that took no arrays.

    Expected value determined independently: the committed reports' top-level
    key set, plus `strata` from this session's wiring, plus `arm_arrays`.

    Bug this catches: a new summary, ratio or check smuggled in beside the
    arrays -- the task quietly becoming the schema change S1 says it is not.
    Also catches the section being omitted rather than null, which a reader
    cannot tell from a rung that never ran it.
    """
    built = _report(arm_arrays=_arm_arrays(batch=10))
    record = built.reproducible()

    assert set(record) == {
        "rung",
        "contaminated",
        "null_line",
        "smears",
        "instrument",
        "iterations",
        "ratios",
        "checks",
        "strata",
        "arm_arrays",
    }
    assert record["arm_arrays"] is not None
    assert _report().reproducible()["arm_arrays"] is None
