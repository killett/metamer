"""`geometry_hash`: what it covers, what it deliberately does not, and why.

The component this module is really testing is a **limit**. A fingerprint that
covered everything would be a hash of 25 GB; one that covered too little would
let a regrid through. Most of the tests below pin one side or the other of that
boundary, and the boundary is the product.
"""

from __future__ import annotations

import hashlib

import numpy as np
import pytest
import xarray as xr

from metamer.batch import geometry
from metamer.batch.input import InputContractError, open_input
from metamer.core.hashing import canonical_json

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")


def _months(n, start="2000-01-01"):
    origin = np.datetime64(start)
    return np.array([origin + np.timedelta64(31 * i, "D") for i in range(n)])


def _dataset(
    *, n_time=12, y=None, x=None, dtype="float32", variable="sla", values=None
):
    y = np.arange(2, dtype="int64") if y is None else np.asarray(y)
    x = np.arange(3, dtype="int64") if x is None else np.asarray(x)
    payload = (
        np.zeros((n_time, y.size, x.size), dtype=dtype) if values is None else values
    )
    return xr.Dataset(
        {variable: (("time", "y", "x"), payload)},
        coords={"time": _months(n_time), "y": y, "x": x},
    )


def _mismatch(stored: object, requested: object) -> str:
    """`describe_mismatch`, asserting that it found one.

    Stronger than an `in` test on the raw result, and typed: a `None` return
    means the two geometries were judged identical, which for every caller below
    is the failure being guarded, not a message to search.
    """
    message = geometry.describe_mismatch(stored, requested)  # type: ignore[arg-type]
    assert message is not None, "expected a mismatch and got none"
    return message


def _components(tmp_path, dataset, name="x.zarr", variable="sla"):
    path = tmp_path / name
    dataset.to_zarr(path)
    return geometry.geometry_components(open_input(str(path), variable))


# --------------------------------------------------------------------------
# The limit, in both directions
# --------------------------------------------------------------------------


def test_a_value_edit_at_fixed_geometry_does_not_move_the_hash(tmp_path):
    """Rewriting every number, on the same grid, leaves the fingerprint alone.

    **THIS IS THE LIMIT MADE EXECUTABLE, AND IT IS THE HONEST DOCUMENTATION.**
    The component is named for what it covers -- geometry -- and a docstring
    saying "it does not cover value edits" does not constrain the next author.
    A test that fails when the limit is removed does.

    Expected value determined independently: none of the components is a
    function of the payload array. Hashing the payload is not an option -- about
    25 GB at 10^7 x 630 float32, read to answer a question a resume asks before
    it has budget to read anything.

    Bug this catches: someone "strengthening" the fingerprint by folding in a
    checksum of the data. It would look like a fix and would make every resume
    of a store whose input was touched -- reprocessed, recompressed,
    bit-identically rewritten -- refit 10^7 series.
    """
    rng = np.random.default_rng(0)
    zeros = _components(tmp_path, _dataset(), "a.zarr")
    edited = _components(
        tmp_path,
        _dataset(values=rng.standard_normal((12, 2, 3)).astype("float32")),
        "b.zarr",
    )
    assert geometry.geometry_hash(zeros) == geometry.geometry_hash(edited)
    assert geometry.describe_mismatch(zeros, edited) is None


def test_an_extent_preserving_regrid_does_move_the_hash(tmp_path):
    """Same first and last cell centre, different spacing, different hash.

    **THE POSITIVE CONTROL FOR THE TEST ABOVE**, and not optional: "a value edit
    does not move it" is a pure negative, satisfied equally by a correct limit
    and by a `geometry_hash` that returns a constant. This is the same call
    through the same components, moving.

    Expected value determined independently: the two grids share min, max and --
    here -- even length is not enough to save a summary, because the interior
    points differ. That is exactly the case min/max/length collapses.

    Bug it catches: fingerprinting a SUMMARY of the coordinates rather than
    their values. `(min, max, len)` is the obvious compression and it is blind
    to the commonest real geometry change there is: a regrid that preserves the
    extent. The store would resume onto a different grid with every array the
    right shape.
    """
    linear = np.linspace(0.0, 10.0, 5)
    stretched = np.array([0.0, 1.0, 3.0, 6.0, 10.0])
    assert linear.min() == stretched.min()
    assert linear.max() == stretched.max()
    assert linear.size == stretched.size

    before = _components(tmp_path, _dataset(x=linear), "a.zarr")
    after = _components(tmp_path, _dataset(x=stretched), "b.zarr")
    assert geometry.geometry_hash(before) != geometry.geometry_hash(after)
    assert "spatial coordinates" in _mismatch(before, after)


# --------------------------------------------------------------------------
# Components
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kwargs", "component"),
    [
        ({"n_time": 24}, "shape"),
        ({"dtype": "float64"}, "source_dtype"),
        ({"y": np.arange(4, dtype="int64")}, "shape"),
    ],
)
def test_each_component_moves_the_hash(tmp_path, kwargs, component):
    """Shape, dtype and grid size each move the fingerprint, and are each named.

    Parametrized because one component is not evidence about a set -- the same
    reasoning as the fit/compat superset test. A `geometry_components` that
    built the mapping but dropped `source_dtype` would pass a shape-only test.

    Expected value determined independently: each is a declared component, and
    `canonical_json` is injective enough that changing a value in the mapping
    changes the string.

    Bug this catches, for `source_dtype` specifically: treating float32 and
    float64 sources as one input. They are not -- the float32-to-float64
    conversion happens per chunk at the IO boundary, so the same nominal grid
    stored two ways is two different arithmetic paths into the filter.
    """
    before = _components(tmp_path, _dataset(), "a.zarr")
    after = _components(tmp_path, _dataset(**kwargs), "b.zarr")
    assert geometry.geometry_hash(before) != geometry.geometry_hash(after)
    assert component in _mismatch(before, after)


def test_the_variable_name_is_part_of_the_fingerprint(tmp_path):
    """Same URI, same geometry, different variable is a different input.

    Expected value determined independently: `variable` is a separate
    fit-relevant field already, so this is the fingerprint agreeing with the
    allowlist rather than a second opinion.

    Bug this catches: a dataset holding `sla` and `ssh` on one grid -- an
    ordinary layout -- where fitting each in turn into two stores would
    otherwise produce identical fingerprints, and a resume could not tell them
    apart on geometry alone.
    """
    dataset = _dataset()
    dataset["ssh"] = dataset["sla"]
    path = tmp_path / "two.zarr"
    dataset.to_zarr(path)

    sla = geometry.geometry_components(open_input(str(path), "sla"))
    ssh = geometry.geometry_components(open_input(str(path), "ssh"))
    assert geometry.geometry_hash(sla) != geometry.geometry_hash(ssh)
    assert "variable" in _mismatch(sla, ssh)


def test_the_calendar_is_fingerprinted_through_the_decoded_values(tmp_path):
    """A `noleap` store and a Gregorian one differ, by values and by name.

    Expected value determined independently: `tests/test_input.py` measures that
    the two calendars give different decimal years for one raw timestamp, so a
    fingerprint over decimal years cannot be blind to the calendar. **That
    measurement is what makes this a consequence rather than an assertion.**

    Bug this catches: hashing the raw coordinate numbers plus a `calendar` attrs
    STRING. The fingerprint would then inherit xarray's and cftime's parsing
    behaviour, and an upgrade that changed how an unusual spelling decodes would
    silently invalidate every store -- with the strings still matching.

    The calendar NAME is carried as well, and this asserts both halves: the
    decimal years make the difference count, the name makes it sayable. Without
    the name a calendar change reports as "the time coordinate differs", which
    is true and useless.
    """
    import cftime

    gregorian = _dataset()
    noleap = _dataset()
    noleap = noleap.assign_coords(
        time=[cftime.datetime(2000, 1 + i, 1, calendar="noleap") for i in range(12)]
    )

    before = _components(tmp_path, gregorian, "a.zarr")
    after = _components(tmp_path, noleap, "b.zarr")
    assert before["calendar"] != after["calendar"]
    assert before["time_coordinate"] != after["time_coordinate"]
    assert geometry.geometry_hash(before) != geometry.geometry_hash(after)
    assert "calendar" in _mismatch(before, after)


def test_the_components_are_recorded_alongside_the_rollup(tmp_path):
    """Every component the mismatch message names is in the mapping itself.

    Expected value determined independently: §13.3 requires root attrs to carry
    the components as well as the rollup, and the reason is implementability --
    on the resume side the store is the only thing available, so a message
    naming WHICH component differs exists only if the store kept the parts.

    Bug this catches: storing the rollup alone. The refusal then degrades to
    "hash mismatch", which is the failure mode the component was introduced to
    end: `data_uri` told a user their data had moved when it had been
    regridded, and told them nothing when it had been rewritten in place.
    """
    components = _components(tmp_path, _dataset())
    assert set(components) == {
        "variable",
        "arrays",
        "calendar",
        "time_coordinate",
        "spatial_coordinates",
    }
    assert set(components["arrays"]["sla"]) == {"dims", "shape", "source_dtype"}
    assert set(components["spatial_coordinates"]) == {"y", "x"}


def test_an_integer_coordinate_is_serializable(tmp_path):
    """`y` and `x` as int64 do not raise, which `list()` would have.

    **THE TRAP THIS CLOSES IS ASYMMETRIC AND THEREFORE INVISIBLE ON A FLOAT
    FIXTURE.** `canonical_json` refuses `np.ndarray` and `np.int64` and ACCEPTS
    `np.float64`, because that one subclasses `float`. So `list(array)` works on
    a float coordinate and raises on an integer one -- and index coordinates are
    routinely integers. A fingerprint built that way passes every test written
    against a float grid and fails on the first real store.

    Bug this catches: `list(...)` where `.tolist()` is required. Both read as
    "make it a list".
    """
    components = _components(tmp_path, _dataset(y=np.arange(2, dtype="int64")))
    assert components["spatial_coordinates"]["y"] == [0, 1]
    assert all(isinstance(v, int) for v in components["spatial_coordinates"]["y"])
    canonical_json(components)


def test_the_digest_shares_its_construction_with_the_config_hashes(tmp_path):
    """`geometry_hash` is `canonical_json` plus sha256 truncated to 16, as elsewhere.

    Expected value determined independently: computed here from the components
    with `hashlib` directly, which is the same construction `hashing.digest`
    uses and shares no code with it.

    Bug this catches: the two drifting apart -- a different truncation, a
    different serializer, a `sort_keys=False`. They would each be
    self-consistent and the store would carry two incompatible notions of
    canonical, which is exactly the failure `canonical_json` was centralized to
    prevent.
    """
    components = _components(tmp_path, _dataset())
    expected = hashlib.sha256(canonical_json(components).encode("utf-8")).hexdigest()[
        :16
    ]
    assert geometry.geometry_hash(components) == expected
    assert len(expected) == 16


def test_a_missing_variable_is_refused_by_name(tmp_path):
    """Fingerprinting a variable the dataset lacks fails at the boundary."""
    path = tmp_path / "x.zarr"
    _dataset().to_zarr(path)
    handle = open_input(str(path), "sla")
    with pytest.raises(InputContractError, match="ssh"):
        geometry.geometry_components(handle, ["ssh"])


def test_every_named_array_contributes_not_only_the_primary_variable(tmp_path):
    """A second input array moves the fingerprint.

    **CONSTRUCTED, BECAUSE PER-POINT REGRESSORS ARE REFUSED IN 2a**, which is
    exactly why it is worth testing now: the components mapping is keyed by
    variable, so adding the second source is data rather than a shape change --
    and that claim is checkable today and would be discovered false later.

    Expected value determined independently: a per-point regressor is a second
    data source with its own grid, so a GIA field silently regridded under a
    fixed URI is the same hole one level out from the one this component closes.

    Bug this catches: fingerprinting only the primary variable, which reads as
    complete while the deferred feature's whole risk sits outside it.
    """
    dataset = _dataset()
    dataset["gia"] = dataset["sla"]
    path = tmp_path / "two.zarr"
    dataset.to_zarr(path)
    handle = open_input(str(path), "sla")

    one = geometry.geometry_components(handle, ["sla"])
    both = geometry.geometry_components(handle, ["sla", "gia"])
    assert geometry.geometry_hash(one) != geometry.geometry_hash(both)
    assert set(both["arrays"]) == {"sla", "gia"}


def test_identical_raw_values_under_two_calendars_fingerprint_differently(tmp_path):
    """The same NUMBERS, decoded two ways, give different time components.

    **THIS IS THE TEST THAT MAKES "FINGERPRINT THE DECODED CALENDAR" MEAN
    SOMETHING, AND THE OBVIOUS VERSION OF IT DOES NOT.** Comparing a
    `datetime64` store against a `cftime` store varies the raw representation as
    well as the calendar, so it passes whether the component hashes decoded
    values or raw ones -- measured: mutating `time_coordinate` to the raw values
    left that test green. The fixture could not express the defect.

    Here the stored numbers are **bit-identical** and only the `calendar`
    attribute differs, so the raw arrays are indistinguishable and the decoded
    ones are not: day 59 after 2000-01-01 is 29 February under `standard` and
    1 March under `noleap`, and they fall at different fractions of years of
    different lengths.

    Expected value determined independently: `tests/test_input.py` measures the
    two conversions separately; this asserts the fingerprint inherits that.

    Bug it catches: hashing the raw coordinate numbers and carrying the calendar
    as an attrs string alongside. Two stores over one file read under two
    calendar declarations would then share a time component -- and, worse, the
    fingerprint would inherit xarray's and cftime's parsing, so an upgrade
    changing how a spelling decodes silently invalidates every store while the
    strings still match.
    """
    raw = np.arange(0, 360, 30, dtype="int64")
    components = []
    for calendar in ("standard", "noleap"):
        dataset = xr.Dataset(
            {"sla": (("time", "y", "x"), np.zeros((raw.size, 2, 3), dtype="float32"))},
            coords={
                "time": (
                    "time",
                    raw,
                    {"units": "days since 2000-01-01", "calendar": calendar},
                ),
                "y": np.arange(2, dtype="int64"),
                "x": np.arange(3, dtype="int64"),
            },
        )
        path = tmp_path / f"{calendar}.zarr"
        xr.decode_cf(dataset).to_zarr(path)
        components.append(geometry.geometry_components(open_input(str(path), "sla")))

    standard, noleap = components
    assert standard["time_coordinate"] != noleap["time_coordinate"]
    assert geometry.geometry_hash(standard) != geometry.geometry_hash(noleap)

    # AND THE COMPONENT IS DECIMAL YEARS, NOT A RENDERING OF THE TIMESTAMPS.
    # This is the assertion that bites, and finding out why took a mutation that
    # did NOT bite. Hashing `str(v)` of the decoded values also distinguishes
    # the two calendars -- decoding happens in the opener, so ANY representation
    # taken here is post-decode -- so the calendar half of this test cannot tell
    # the two apart. What separates them is that decimal years are the quantity
    # the fit actually sees:
    #
    #   - they move when the CONVERSION RULE moves, and the conversion is under
    #     ALGORITHM_VERSION, so a change to it must invalidate stored fits. A
    #     rendering of the timestamps would not move at all.
    #   - `str()` of a datetime64 or a cftime date is a repr, and a repr is a
    #     library-version artefact -- pre-flight (k), the same hazard that made
    #     `default=repr` a drifting hash in Task 16.
    for value in standard["time_coordinate"]:
        assert isinstance(value, float)
        assert 1990.0 < value < 2010.0
