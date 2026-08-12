"""The opener registry, the zarr opener, and the stage-4a contract.

Two things are being established here and they are easy to conflate. The
**registry** must have no zarr-shaped hole in it, so that netCDF is a
registration rather than a refactor. The **contract** must refuse an input that
is not what the config says it is, at the boundary, naming what it found.
"""

from __future__ import annotations

import datetime as dt

import cftime
import numpy as np
import pytest
import xarray as xr

from metamer.batch import input as batch_input
from metamer.batch.timeaxis import (
    calendar_of,
    check_strictly_increasing,
    to_decimal_years,
    unique_dt_count,
)

# `to_zarr` warns that consolidated metadata is not in the v3 spec. It is
# xarray's default and says nothing about this code.
pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")


def _dataset(time, *, variable="sla", n_y=2, n_x=3, dtype="float32"):
    return xr.Dataset(
        {
            variable: (
                ("time", "y", "x"),
                np.zeros((len(time), n_y, n_x), dtype=dtype),
            )
        },
        coords={"time": time, "y": np.arange(n_y), "x": np.arange(n_x)},
    )


def _months(n, start="2000-01-01"):
    origin = np.datetime64(start)
    return np.array([origin + np.timedelta64(31 * i, "D") for i in range(n)])


def _store(tmp_path, dataset, name="x.zarr"):
    path = tmp_path / name
    dataset.to_zarr(path)
    return str(path)


# --------------------------------------------------------------------------
# Decimal years: the absolute anchors
# --------------------------------------------------------------------------


def test_decimal_years_against_hand_computed_values():
    """Four timestamps whose decimal years are worked out by hand.

    THE ABSOLUTE ANCHOR. Every other test of the conversion is differential --
    "these two axes agree", "these two calendars differ" -- and a differential
    test cannot see a convention that is uniformly wrong. Both sides of
    `test_a_seconds_axis_and_a_datetime_axis_agree` go through this same
    function, so an off-by-one-year or a `/365.25` convention would cancel
    exactly.

    The expected values, derived from the convention and not from the code:

      - 2000-01-01 is the start of a year, so exactly 2000.0.
      - 2000-07-01 in a 366-day year: 31+29+31+30+31+30 = 182 days elapsed,
        so 2000 + 182/366.
      - 2001-07-01 in a 365-day year: 181 days elapsed, so 2001 + 181/365.
        **The two differ**, which is the leap year visible in the axis.
      - 2000-12-31T12:00 is 365.5 days into a 366-day year.

    Bug this catches: `epoch + elapsed / 365.25`, the obvious alternative. It
    gives 2000.4956 for the second case against 2000.4973 here -- a 0.6-day
    phase error that grows without bound under `noleap` and `360_day`, and the
    design matrix carries annual harmonics.
    """
    stamps = np.array(
        [
            np.datetime64("2000-01-01T00:00:00"),
            np.datetime64("2000-07-01T00:00:00"),
            np.datetime64("2001-07-01T00:00:00"),
            np.datetime64("2000-12-31T12:00:00"),
        ]
    )
    got = to_decimal_years(stamps)
    expected = np.array(
        [2000.0, 2000 + 182 / 366, 2001 + 181 / 365, 2000 + 365.5 / 366]
    )
    np.testing.assert_allclose(got, expected, rtol=0, atol=1e-12)


def test_a_calendar_year_is_exactly_one_in_every_calendar():
    """Consecutive 1 Januaries are exactly 1.0 apart, in all three calendars.

    Expected value determined independently: this IS the convention -- decimal
    year is the fraction of the actual year -- so the property is definitional
    and holds by construction if the construction is right.

    Bug this catches: dividing by a fixed year length. Under `/365.25`, a
    `360_day` calendar year measures 0.9856 decimal years, so an `Annual`
    design column drifts 5.25 days per year and is **decorrelated from the
    season after 50 years** -- 0.72 years of accumulated phase. That is not a
    small error in a fitted amplitude, it is a different signal, and nothing
    downstream would report it: the design stays full rank and every fit
    converges.
    """
    for calendar in ("proleptic_gregorian", "noleap", "360_day"):
        stamps = np.array(
            [
                cftime.datetime(2000, 1, 1, calendar=calendar),
                cftime.datetime(2001, 1, 1, calendar=calendar),
                cftime.datetime(2002, 1, 1, calendar=calendar),
            ]
        )
        years = to_decimal_years(stamps)
        np.testing.assert_allclose(np.diff(years), [1.0, 1.0], rtol=0, atol=1e-12)


def test_two_calendars_give_different_decimal_years_for_one_raw_value():
    """`noleap` and `proleptic_gregorian` disagree, which is why the calendar is hashed.

    Expected value determined independently: 1 March follows 59 days in a
    `noleap` year and 60 in a Gregorian leap year, so the two fractions have
    both different numerators and different denominators.

    **THIS TEST IS WHAT JUSTIFIES TASK 3 PUTTING THE CALENDAR IN THE
    FINGERPRINT.** Without a measurement, "the calendar is fit identity" is an
    assertion; with one, it is a consequence. A store fitted under one reading
    of an ambiguous axis and resumed under another would reuse fits computed on
    a different time axis, with no array changing shape.

    Bug it catches: taking the calendar from the attrs STRING rather than the
    decoded object. The two decode differently; the strings may be identical.
    """
    gregorian = to_decimal_years(
        np.array([cftime.datetime(2000, 3, 1, calendar="proleptic_gregorian")])
    )
    noleap = to_decimal_years(
        np.array([cftime.datetime(2000, 3, 1, calendar="noleap")])
    )
    assert gregorian[0] != noleap[0]
    np.testing.assert_allclose(gregorian, [2000 + 60 / 366], atol=1e-12)
    np.testing.assert_allclose(noleap, [2000 + 59 / 365], atol=1e-12)


def test_the_calendar_comes_from_the_decoded_object(tmp_path):
    """`calendar_of` reads the decoded values, not the file's attributes.

    Bug this catches: `dataset['time'].attrs['calendar']`. After CF decoding
    that attribute has been CONSUMED and moved to `.encoding`, so the attrs
    read returns nothing at all -- and a fingerprint built on it would be
    constant across every calendar, which is the failure mode the whole
    component exists to prevent. Reading the decoded object asks the thing that
    actually produced the numbers.
    """
    stamps = np.array(
        [cftime.datetime(2000, 1, 1 + i, calendar="noleap") for i in range(5)]
    )
    assert calendar_of(stamps) == "noleap"
    assert calendar_of(_months(5)) == "proleptic_gregorian"


def test_a_seconds_axis_and_a_datetime_axis_give_the_same_decimal_years():
    """The same record, encoded two ways, converts identically.

    Expected value determined independently: CF decoding is what makes the two
    encodings the same record, so equality is the definition of the decoder
    working. The absolute anchor above is what stops this from passing against
    a uniformly wrong convention -- **both sides go through the same function
    here, so this test alone is blind to the convention entirely.**

    Bug it catches: passing raw numbers through as if they were years. Measured
    in Phase 1: the same 20-year monthly design on a seconds-since-1970 axis
    goes from `cond(X) = 3.4e1` to `3.3e32` and rank 7/7 to 2/7, with
    `cos(annual)` identically 1.0 -- a full-rank-looking design that has lost
    five columns, and no crash.
    """
    stamps = _months(24)
    seconds = xr.decode_cf(
        xr.Dataset(
            coords={
                "time": (
                    "time",
                    (stamps - np.datetime64("1970-01-01")) / np.timedelta64(1, "s"),
                    {"units": "seconds since 1970-01-01", "calendar": "standard"},
                )
            }
        )
    )["time"].values
    np.testing.assert_allclose(
        to_decimal_years(seconds), to_decimal_years(stamps), rtol=0, atol=1e-9
    )


def test_a_bare_numeric_axis_is_refused_naming_what_is_required():
    """No unit is ever inferred from magnitude.

    Expected value determined independently: days-since-1970 over 50 years is
    about 2e4 and years-since-0 is about 2e3. **The two overlap in order of
    magnitude on exactly the axis a heuristic would have to disambiguate**, so
    no threshold separates them.

    Bug this catches: a future "helpful" heuristic. Its failure is silent --
    both readings produce a plausible axis, and the wrong one produces the
    rank collapse measured in Phase 1.
    """
    with pytest.raises(TypeError, match="no calendar"):
        to_decimal_years(np.arange(10, dtype=float))


# --------------------------------------------------------------------------
# Strictly increasing
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("t", "expected"),
    [
        (np.array([2000.0, 2000.0, 2001.0]), "duplicate"),
        (np.array([2000.0, 2002.0, 2001.0]), "decreasing"),
    ],
)
def test_a_non_increasing_axis_is_refused_by_kind_and_index(t, expected):
    """A duplicate and a reversal are both caught, and are named apart.

    Expected value determined independently: strict monotonicity fails for both,
    and `diff == 0` distinguishes them.

    Bug this catches: `np.all(np.diff(t) >= 0)`, which accepts a duplicate. That
    gives `dt = 0` -- an identity transition with a ZERO process-noise
    covariance, singular -- and it surfaces as a Cholesky failure deep inside
    the filter, at which point the diagnostic names a matrix rather than a
    timestamp. Duplicate timestamps are ordinary in real records.

    The two are asserted separately rather than through one "not increasing"
    match, because they have different causes and a message that cannot tell
    them apart sends the user to the wrong place.
    """
    with pytest.raises(ValueError, match=expected):
        check_strictly_increasing(t)


def test_a_single_sample_axis_is_refused_by_the_same_check():
    """One timestamp has no timestep, and the same comparison catches it.

    Bug this catches: a length-1 axis reaching `np.diff`, which returns an empty
    array, so every "all steps positive" check passes vacuously -- the
    cancellation rule in its purest form, an assertion over an empty set.
    """
    with pytest.raises(ValueError, match="at least two"):
        check_strictly_increasing(np.array([2000.0]))


def test_the_increasing_check_accepts_a_valid_axis():
    """The positive control: the same check passes what it should.

    Without this, every refusal test above is satisfied by a function that
    raises unconditionally -- the pure-negative trap, one level down. Three
    tests assert that this function raises; exactly one asserts that it does not.
    """
    check_strictly_increasing(to_decimal_years(_months(12)))


# --------------------------------------------------------------------------
# The unique-Delta-t report
# --------------------------------------------------------------------------


def test_the_unique_dt_count_is_measured_on_the_realized_axis():
    """Real monthly timestamps give more than one distinct step.

    **THE BRIEF'S PREMISE WAS WRONG AND THIS IS WHERE IT IS RECORDED.** The plan
    says the count is "1 for a regular axis and large for one perturbed by float
    noise". Measured, neither half holds:

      - 50 years of month-start timestamps give **6** distinct steps, because
        calendar months are 28-31 days. Only a SYNTHETIC `2000 + arange(n)/12`
        axis gives 1, and that is what benchmarks are built from.
      - float64 rounding from the conversion is ~1e-16 of the value, far below
        `UNIQUE_DT_RTOL = 1e-9`, so it collapses and does NOT inflate the count.

    Expected values determined independently: month lengths in a 4-year leap
    cycle take a small number of distinct values, and the tolerance is a
    documented constant several decades above float64 rounding at these
    magnitudes.

    Bug this catches: computing the report from the NOMINAL step -- the config's
    idea of "monthly" -- rather than from the axis actually read. That reports 1
    forever, and the number exists precisely to be surprising.
    """
    stamps = np.array(
        [np.datetime64(f"{2000 + i // 12:04d}-{i % 12 + 1:02d}-01") for i in range(600)]
    )
    realized = unique_dt_count(to_decimal_years(stamps))
    assert realized == 6

    synthetic = unique_dt_count(2000.0 + np.arange(600) / 12.0)
    assert synthetic == 1
    assert realized > synthetic


def test_float_noise_does_not_inflate_the_count_but_real_jitter_does():
    """The hazard is sub-second jitter, not float representation.

    THE LIMIT, MADE EXECUTABLE. `UNIQUE_DT_RTOL = 1e-9` is a per-pair relative
    tolerance, so on a monthly axis it is about 2.6 ms. Perturbation below that
    collapses; above it, every step becomes distinct and `F` and `Q` are rebuilt
    once per timestep instead of a handful of times -- an order of magnitude,
    with nothing else saying why.

    Expected values determined independently: the tolerance is a declared
    constant and the monthly step is 1/12 of a year, so the crossover is
    `1e-9 / 12` years by arithmetic, not by fitting to observed behaviour.

    Bug this catches -- and it is the expensive one -- **responding to a large
    count by lowering `UNIQUE_DT_RTOL`.** That would destroy the amortization on
    every axis in order to hide a number that is telling the truth about one.
    Pinning both sides of the crossover makes the constant's role explicit, so a
    later reader sees that moving it is not a local change.
    """
    base = 2000.0 + np.arange(600) / 12.0
    rng = np.random.default_rng(0)

    tiny = np.sort(base + rng.normal(0, 1e-16 * 2000.0, base.size))
    assert unique_dt_count(tiny) == 1

    jitter = np.sort(base + rng.normal(0, 1e-10 * 2000.0, base.size))
    assert unique_dt_count(jitter) > 100


# --------------------------------------------------------------------------
# The registry has no privileged zarr path
# --------------------------------------------------------------------------


def test_a_second_opener_drives_the_whole_path_with_no_zarr_special_case(tmp_path):
    """A registered opener under its own scheme reaches every stage.

    **THIS IS THE EXECUTABLE FORM OF "ADDING netCDF MUST BE A REGISTRATION, NOT
    A REFACTOR."** The intent is easy to state and impossible to verify by
    reading: a zarr special case in `_scheme_of`, `open_input` or
    `check_contract` would be invisible while zarr is the only opener. Driving a
    foreign scheme through the entire path is what makes the claim falsifiable.

    Bug it catches: `if uri.endswith(".zarr")` anywhere on the path, or
    `check_contract` reaching for a zarr-specific attribute. Either ships a
    registry that is a registry in name and a dispatch table with one entry in
    fact, and the cost lands on whoever adds netCDF -- who will read the seam as
    working, because the tests pass.

    The second opener exists ONLY here. Two production openers do not test the
    tiling loop twice; they test xarray twice.
    """
    dataset = _dataset(_months(24))

    def _open_memory(uri: str) -> xr.Dataset:
        assert uri.startswith("memtest://")
        return dataset

    batch_input.opener_registry.register("memtest")(_open_memory)
    try:
        handle = batch_input.open_input("memtest://anywhere", "sla")
        assert handle.scheme == "memtest"
        report = batch_input.check_contract(handle)
    finally:
        batch_input.opener_registry.unregister("memtest")

    assert report.n_time == 24
    assert report.n_y == 2
    assert report.n_x == 3
    assert report.calendar == "proleptic_gregorian"
    assert report.source_dtype == "float32"


def test_an_unknown_scheme_is_refused_listing_the_registered_openers():
    """The refusal names what is available, which is the fact a user needs.

    Bug this catches: content sniffing as a fallback. A mis-sniffed file is a
    wrong answer where an unknown scheme is a refusal, and the opener would
    become a property of the bytes rather than of the configuration.
    """
    with pytest.raises(batch_input.InputContractError, match="zarr"):
        batch_input.open_input("hdf5://somewhere/file.h5", "sla")


# --------------------------------------------------------------------------
# The contract itself
# --------------------------------------------------------------------------


def test_the_contract_reports_the_source_dtype_and_units(tmp_path):
    """`float32` on disk is reported as `float32`, and the units survive decoding.

    **THE UNITS FIELD IS WHY THIS TEST EXISTS.** CF decoding CONSUMES `units`
    and `calendar` and files them under `.encoding`, so reading `.attrs` returns
    None for every successfully decoded axis -- that is, for every axis this
    code ever sees. Measured on a round-tripped store: `.attrs` gave None while
    `.encoding` carried the real string. A provenance field that is always empty
    records nothing, and nothing else in the system would have reported it.

    Bug this also catches: reporting the dtype after conversion. Task 3 puts the
    SOURCE dtype in the geometry fingerprint, because a float32 store and a
    float64 store are not the same input -- and everything downstream of the
    tile read is float64 either way, so a post-conversion read would report
    `float64` for both.
    """
    uri = _store(tmp_path, _dataset(_months(12), dtype="float32"))
    report = batch_input.check_contract(batch_input.open_input(uri, "sla"))
    assert report.source_dtype == "float32"
    assert report.units is not None
    assert "since" in report.units


@pytest.mark.parametrize(
    ("variable", "match"),
    [("ssh", "Available"), ("sla", None)],
)
def test_a_missing_variable_is_refused_and_a_present_one_is_not(
    tmp_path, variable, match
):
    """The named variable must exist, and the message lists what does.

    The second case is the positive control: without it, this test is satisfied
    by a `check_contract` that refuses everything.
    """
    uri = _store(tmp_path, _dataset(_months(12)))
    handle = batch_input.open_input(uri, variable)
    if match is None:
        assert batch_input.check_contract(handle).n_time == 12
    else:
        with pytest.raises(batch_input.InputContractError, match=match):
            batch_input.check_contract(handle)


def test_a_two_dimensional_variable_is_refused(tmp_path):
    """The contract is three dims mapping to (time, y, x).

    Bug this catches: accepting a `(time, station)` dataset, which is a perfectly
    reasonable thing to have and is not what the tiling loop reads. It would
    surface as a shape error inside the tile iterator, where the diagnostic names
    an index rather than the input.
    """
    dataset = xr.Dataset(
        {"sla": (("time", "y"), np.zeros((12, 4), dtype="float32"))},
        coords={"time": _months(12), "y": np.arange(4)},
    )
    uri = _store(tmp_path, dataset)
    with pytest.raises(batch_input.InputContractError, match="three"):
        batch_input.check_contract(batch_input.open_input(uri, "sla"))


def test_an_undecodable_time_axis_is_refused_naming_the_ambiguity(tmp_path):
    """A bare numeric time axis is a stage-4a error, not a guess.

    Bug this catches: silently treating the numbers as decimal years, which is
    the single most catastrophic input error in the system and produces no
    exception -- a full-rank-looking design that has lost its harmonics.

    The message names both what was found and what is required, because a
    refusal that does not say what would lift it is a wall.
    """
    dataset = xr.Dataset(
        {"sla": (("time", "y", "x"), np.zeros((12, 2, 3), dtype="float32"))},
        coords={
            "time": np.arange(12, dtype=float),
            "y": np.arange(2),
            "x": np.arange(3),
        },
    )
    uri = _store(tmp_path, dataset)
    with pytest.raises(batch_input.InputContractError, match="magnitude"):
        batch_input.check_contract(batch_input.open_input(uri, "sla"))


def test_a_duplicated_timestamp_is_refused_at_the_boundary(tmp_path):
    """Stage 4a catches `dt = 0` before the filter can.

    Bug this catches: the duplicate reaching the state-space construction, where
    a zero process-noise covariance is singular and reports as a numerical
    failure of the fit rather than as a property of the input.
    """
    stamps = _months(12)
    stamps[5] = stamps[4]
    uri = _store(tmp_path, _dataset(stamps))
    with pytest.raises(batch_input.InputContractError, match="strictly increasing"):
        batch_input.check_contract(batch_input.open_input(uri, "sla"))


def test_a_cftime_calendar_survives_the_round_trip(tmp_path):
    """A `noleap` store reports `noleap`, from the decoded values.

    Bug this catches: the calendar being lost or defaulted on the way through
    the opener, which would make every store report `proleptic_gregorian` and
    make Task 3's fingerprint blind to exactly the difference it exists to
    catch -- while `test_two_calendars_give_different_decimal_years` keeps
    passing, because that one never touches a file.
    """
    stamps = np.array(
        [cftime.datetime(2000, 1 + i, 1, calendar="noleap") for i in range(12)]
    )
    uri = _store(tmp_path, _dataset(stamps))
    report = batch_input.check_contract(batch_input.open_input(uri, "sla"))
    assert report.calendar == "noleap"


def test_the_reported_span_is_in_decimal_years(tmp_path):
    """`t_start` and `t_end` are years, not raw numbers.

    Bug this catches: reporting the raw coordinate. A span of `9.4e8` to
    `1.0e9` in provenance reads as a valid number and is seconds since 1970 --
    the exact confusion the conversion exists to remove, reintroduced in the
    record of it.
    """
    uri = _store(tmp_path, _dataset(_months(24)))
    report = batch_input.check_contract(batch_input.open_input(uri, "sla"))
    assert 1900.0 < report.t_start < 2100.0
    assert report.t_end > report.t_start


def test_datetime_objects_and_datetime64_agree():
    """A python `datetime` axis converts identically to a `datetime64` one.

    Bug this catches: the microsecond cast in `to_decimal_years`. `datetime64[ns]`
    `.astype(object)` yields plain INTEGERS rather than datetimes -- silently --
    and the resulting "years" are about 1e18. Casting to microseconds first is
    what makes the object path real, and this is the test that notices if the
    cast is removed.
    """
    stamps = _months(6)
    objects = np.array([d.item() for d in stamps.astype("datetime64[us]")])
    assert isinstance(objects[0], dt.datetime)
    np.testing.assert_allclose(
        to_decimal_years(objects), to_decimal_years(stamps), rtol=0, atol=1e-12
    )
