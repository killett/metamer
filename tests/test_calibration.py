"""`metamer.batch.calibration`: the cache, its key, and the rule for using it.

**THE CACHE IS A CROSS-PROCESS ARTIFACT AND ITS TESTS SAY SO.** A calibration
consumed only in the session that produced it never exercises a cache at all, so
the read-back claim is tested by writing in one process and reading in another --
(k), the one category a perfect in-process suite cannot reach.

**AND THE FIXTURE IS PLACED OFF THE POINT WHERE THE TWO ARITHMETICS AGREE.** On
Phase 2b Task 4's measured ladder the analytic and calibrated figures agree to
**0.55 standard errors**, so a fixture that merely calibrates lands where the two
functions coincide and every cache test passes against a cache nothing reads
(i7). Every side comparison below therefore runs against a **constructed** slope,
with the arithmetic derived by hand in the test that uses it.
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import xarray as xr

from metamer.batch import calibration
from metamer.batch.run import TileModelKwargs, run
from metamer.batch.tiling import tile_side_for
from metamer.batch.validation import ValidationError
from metamer.core.memory import (
    CalibrationPoint,
    CalibrationResult,
    FloorReport,
    MemoryEngineLabel,
    SolverPlacement,
)

# `to_zarr` warns that consolidated metadata is not in the v3 spec. It is
# xarray's default and says nothing about this code.
pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")


# --------------------------------------------------------------------------
# The constructed fixture, derived by hand
# --------------------------------------------------------------------------

#: The floor every run below pins, so a side is a function of the budget alone.
#: **Pinned rather than measured**: `block = (budget - floor) x (1 - headroom)`,
#: and the window that selects one side is a few kB wide while a measured floor
#: moves by megabytes between runs -- a thousand times the window (i9).
_FLOOR_BYTES = 228_200_000

_FLOOR = FloorReport(
    pre_warm_bytes=_FLOOR_BYTES,
    post_warm_bytes=_FLOOR_BYTES,
    with_input_bytes=_FLOOR_BYTES,
    peak_bytes=_FLOOR_BYTES,
    components={"pinned": _FLOOR_BYTES},
)

#: The budget that puts the ANALYTIC side at exactly 8 on the fixture below.
#: Derived by hand, and every step is checkable:
#:
#: * per-series = `24*9 + 2*(24*3 + 16*4 + 57)` = `216 + 386` = **602 B**
#: * available  = 228 267 295 - 228 200 000 = **67 295 B**
#: * block      = `int(67 295 * 0.85)` = **57 200 B**
#: * usable     = 57 200 - 11 200 (the solver constant at d=1, k_beta=4,
#:                p_max=3) = **46 000 B**
#: * analytic   = `floor(sqrt(46 000 / 602))` = `floor(sqrt(76.41))` =
#:                `floor(8.74)` = **8**
#: * at 900     = `floor(sqrt(46 000 / 900))` = `floor(sqrt(51.11))` =
#:                `floor(7.15)` = **7**
#:
#: It round-trips through `int(gb * 10**9)`, checked below, because the budget
#: reaches `run()` as gigabytes.
_BUDGET_BYTES = 228_267_295

#: A slope that is 900/602 = **1.495x** the analytic figure: inside
#: `memory.SLOPE_BAND_FACTOR`'s two-sided band, and deliberately not on its
#: inclusive edge of 903.0. **The band is what caps how far this fixture can be
#: placed** -- 1.5x in slope is sqrt(1.5) = 1.22x in side, so 8 against 7 is the
#: largest separation a usable calibration can produce here.
_CONSTRUCTED_SLOPE = 900.0

_ANALYTIC_SIDE = 8
_CALIBRATED_SIDE = 7

_CONFIG = """
data_uri = "{uri}"
variable = "sla"
signal_terms = ["constant", "trend", "annual"]
candidates = ["white", "white + matern12"]
criteria = ["aic"]
memory_budget_gb = {budget}
"""


def _input(directory: Path, *, n_time: int = 24, side: int = 8) -> str:
    """A real zarr input, white noise rather than zeros.

    A record of exact zeros drives sigma to its lower diagnostic limit and every
    fit comes back `DIAGNOSTIC_LIMIT`, which is a different allocation path from
    the one a capped run is supposed to exercise.
    """
    rng = np.random.default_rng(0)
    dataset = xr.Dataset(
        {
            "sla": (
                ("time", "y", "x"),
                rng.standard_normal((n_time, side, side)).astype("float32"),
            )
        },
        coords={
            "time": np.array(
                [
                    np.datetime64("2000-01-01") + np.timedelta64(31 * i, "D")
                    for i in range(n_time)
                ]
            ),
            "y": np.arange(side),
            "x": np.arange(side),
        },
    )
    path = directory / "in.zarr"
    dataset.to_zarr(path)
    return str(path)


def _config(directory: Path, uri: str, *, name: str = "c.toml") -> Path:
    path = directory / name
    path.write_text(
        textwrap.dedent(
            _CONFIG.format(uri=uri, budget=repr(_BUDGET_BYTES / 10**9))
        ).lstrip()
    )
    return path


def _result(slope: float, *, intercept: float = 227_000_000.0) -> CalibrationResult:
    """A `CalibrationResult` with a chosen slope and a plausible everything else.

    The ladder is Task 4's shape at the two sides this fixture can afford. Only
    the slope is ever read by the tiling, which is the whole point of caching
    only the slope.
    """
    points = tuple(
        CalibrationPoint(
            side=side,
            derived_side=side,
            batch=side * side,
            peak_bytes=intercept + slope * side * side,
            baseline_bytes=float(_FLOOR_BYTES),
            ok=0,
            attempted=side * side * 2,
        )
        for side in (4, 8)
    )
    return CalibrationResult(
        slope_bytes_per_series=slope,
        intercept_bytes=intercept,
        residuals=(0.0, 0.0),
        points=points,
        max_iter=1,
        linearity_basis="constructed for tests/test_calibration.py",
        placement=SolverPlacement.PER_SERIES_LIVE,
        engine_label=MemoryEngineLabel.KALMAN_NUMPY,
        floor_peak_bytes=_FLOOR_BYTES,
    )


def _entries(path: Path) -> dict[str, Any]:
    return dict(json.loads(path.read_text())["entries"])


def _rewrite_slope(path: Path, slope: float) -> str:
    """Replace the slope of the cache's one entry, leaving its key alone.

    **THE KEY IS NEVER COMPUTED BY A TEST.** It is written by the production
    path and read back by the production path; only the measured number is
    replaced, which is what puts the fixture off the point where the analytic
    and calibrated sides agree (i7). A test that derived the key itself would
    pass against a run that computed a different one.
    """
    payload = json.loads(path.read_text())
    (key,) = payload["entries"]
    payload["entries"][key]["result"]["slope_bytes_per_series"] = slope
    path.write_text(json.dumps(payload))
    return str(key)


# --------------------------------------------------------------------------
# The cache path
# --------------------------------------------------------------------------


def test_the_cache_is_a_sibling_of_the_store_and_never_inside_it(tmp_path):
    """The cache lives beside the store, in the same prefix, outside the group.

    Expected value determined independently from design doc 11.4 and 15.5: the
    cache must survive on object storage beside the store rather than in local
    scratch, and 12.4 requires every store to be self-contained. Both hold only
    if the cache is in the store's parent and is not a member of the group.

    Bug this catches: a cache written INSIDE the store directory. It would be
    compared by Phase 2a's exit criterion 1 -- which walks the store byte for
    byte -- so two runs of one configuration would stop being byte-identical;
    it would appear as an unrecognized member of the zarr group; and deleting
    it would mean editing the store.
    """
    store = tmp_path / "nested" / "out.zarr"
    path = calibration.cache_path(store)

    assert path.parent == store.parent
    assert store not in path.parents
    assert path != store
    assert path.suffix == ".json"
    # Two stores in one prefix get two caches: the path is derived from the
    # store's name and not from its directory.
    assert calibration.cache_path(tmp_path / "nested" / "other.zarr") != path


# --------------------------------------------------------------------------
# The versions digest
# --------------------------------------------------------------------------


def test_the_digest_moves_when_any_distributions_version_moves():
    """Two constructed maps differing in one version give two digests.

    Expected values determined independently: a digest is a function of its
    input, so two inputs differing anywhere must give two outputs; the maps here
    differ in one character of one value.

    Bug this catches: the digest being a NAME -- (a2)'s third fact, that a change
    in the thing identified must actually move the field. A digest over the
    distribution names alone, or a constant, reads exactly like a real one and
    invalidates nothing. It is the failure a cache cannot detect: every entry
    stays a hit forever, and the slope it serves was measured against different
    code.
    """
    before = {"numpy": "2.3.4", "scipy": "1.18.0", "zarr": "3.1.0"}
    after = {"numpy": "2.3.4", "scipy": "1.18.1", "zarr": "3.1.0"}

    first, first_map = calibration.versions_digest(before)
    second, second_map = calibration.versions_digest(after)

    assert first != second
    assert len(first) == 16
    # The contributors come back so a mismatch can name the package that moved.
    assert first_map == before
    assert second_map == after
    # A removed distribution moves it too, and so does an added one: absence and
    # presence are both changes to what is installed.
    assert calibration.versions_digest({"numpy": "2.3.4"})[0] != first
    assert calibration.versions_digest({**before, "cftime": "1.6.4"})[0] != first


def test_the_digest_does_not_depend_on_the_order_the_environment_reports():
    """One environment reported in two orders gives one digest.

    `importlib.metadata.distributions` yields in `sys.path` and directory order,
    so the same environment can be reported differently by two processes, and a
    key that differed between them would make every second-process read a miss
    -- stable within one process, so invisible to every same-process test AND to
    mutation testing, which shares the interpreter and its hash seed.

    **THE FIXTURE CARRIES A DUPLICATED NAME BECAUSE THE MAPPING CASE IS GUARDED
    A LAYER UP, AND BOTH GUARDS ARE NAMED HERE SO NEITHER IS TIDIED AWAY.**
    `hashing.canonical_json` renders with `sort_keys=True`, so a *mapping's*
    insertion order cannot reach a digest whatever this module does -- measured:
    mutating the sort out of `_pairs` leaves a mapping-only fixture green. What
    survives that guard is the **join order of a duplicated name**: unsorted,
    one process digests `pkg 2.0,1.0` and another `pkg 1.0,2.0` for one
    environment. That is the reachable defect, so that is what is asserted.

    Expected values determined independently: both orderings describe one
    environment, so both must give the map `{"a": "1", "pkg": "1.0,2.0"}` and
    one digest.
    """
    forward = [("a", "1"), ("pkg", "2.0"), ("pkg", "1.0")]
    backward = [("pkg", "1.0"), ("a", "1"), ("pkg", "2.0")]

    first, first_map = calibration.versions_digest(forward)
    second, second_map = calibration.versions_digest(backward)

    assert first_map == {"a": "1", "pkg": "1.0,2.0"}
    assert second_map == first_map
    assert first == second
    # The mapping half, kept for the same environment expressed as a mapping.
    assert (
        calibration.versions_digest({"a": "1", "b": "2"})[0]
        == (calibration.versions_digest({"b": "2", "a": "1"})[0])
    )


def test_the_environment_reading_names_metamer_itself():
    """The package being measured is in the map, however it reaches the path.

    Expected value determined independently and MEASURED 2026-08-15: in this
    tree `[d for d in importlib.metadata.distributions() if "metamer" in d.name]`
    is **empty** -- metamer runs from `src/` and is not an installed
    distribution -- so a digest over installed distributions alone omits exactly
    the package whose memory behaviour the slope describes.

    Bug this catches: "every installed distribution, excluding nothing" taken
    literally, which silently excludes the subject of the measurement. It is the
    fill-value shape at a digest: "metamer did not change" and "metamer is
    invisible to this instrument" produce the identical value.
    """
    import metamer

    digest, versions = calibration.versions_digest()

    assert len(digest) == 16
    assert versions["metamer"] == metamer.__version__
    # It is a real environment reading and not a hand-written stub: the runtime
    # dependencies this project cannot run without are in it too.
    assert {"numpy", "scipy", "zarr", "xarray"} <= set(versions)


def test_two_versions_of_one_distribution_are_both_recorded():
    """A duplicated name keeps both versions rather than one winning silently.

    **THE FAULT CLASS IS NOT CONSTRUCTIBLE FROM THIS ENVIRONMENT** -- measured
    2026-08-15, 194 distributions and no duplicate name -- so it is constructed
    (i8's third shape). It occurs when an installed distribution is shadowed by
    a source tree on the path, which is exactly metamer's own situation here.

    Expected value determined independently: `dict(pairs)` keeps the last of a
    duplicated key, so the rule has to be stated rather than inherited from the
    container. Both versions, sorted and joined, is the statement.

    Bug this catches: the second reading overwriting the first, so an
    ambiguous environment digests as an unambiguous one and the digest does not
    move when the shadowed copy changes.
    """
    digest, versions = calibration.versions_digest(
        [("pkg", "2.0"), ("other", "1.0"), ("pkg", "1.0")]
    )

    assert versions == {"other": "1.0", "pkg": "1.0,2.0"}
    assert digest != calibration.versions_digest({"other": "1.0", "pkg": "1.0"})[0]
    assert digest != calibration.versions_digest({"other": "1.0", "pkg": "2.0"})[0]


# --------------------------------------------------------------------------
# The key
# --------------------------------------------------------------------------


def _key(**overrides: str) -> str:
    arguments: dict[str, str] = {
        "fit_hash": "0123456789abcdef",
        "placement": str(SolverPlacement.PER_SERIES_LIVE),
        "engine_label": str(MemoryEngineLabel.KALMAN_NUMPY),
        "machine": "fedcba9876543210",
        "versions": "aaaabbbbccccdddd",
    }
    arguments.update(overrides)
    return calibration.cache_key(**arguments)


def test_the_key_moves_with_every_one_of_its_five_components():
    """Each component is enumerated and changed alone.

    **ENUMERATED, NEVER COUNTED.** A test asserting "the key has five
    components" passes against a key built from four of them and a constant.
    Each of the five is varied on its own line below, and the whole set of six
    keys must be distinct.

    Expected values determined independently from design doc 11.4 as amended:
    the key is `(fit_hash, placement, engine label, machine fingerprint,
    versions digest)`, and each names a thing that changes bytes per series.

    Bug this catches, one per line: a component dropped from the payload. The
    dangerous ones are `machine` -- one machine's slope served to another, which
    11.4 calls out as the reason the fingerprint exists -- and `engine_label`,
    where `EngineId` would collapse the two engines that deliberately share it.
    """
    baseline = _key()
    moved = {
        "fit_hash": _key(fit_hash="ffffffffffffffff"),
        "placement": _key(placement=str(SolverPlacement.PER_THREAD)),
        "engine_label": _key(engine_label=str(MemoryEngineLabel.KALMAN_COMPILED)),
        "machine": _key(machine="0000000000000000"),
        "versions": _key(versions="1111222233334444"),
    }

    for name, key in moved.items():
        assert key != baseline, f"the key ignores {name}"
    assert len({baseline, *moved.values()}) == 6
    assert baseline == _key()
    assert len(baseline) == 16


# --------------------------------------------------------------------------
# The store and the load
# --------------------------------------------------------------------------


def test_an_entry_is_read_back_only_under_the_key_it_was_written_with(tmp_path):
    """A stale entry under a changed digest is not served.

    Expected value determined independently: a cache is a mapping, and a lookup
    under an absent key is a miss whatever else the mapping holds.

    Bug this catches: the key being computed and then ignored -- `load` handing
    back the only entry it has, or the newest one, because "there is a
    calibration here" reads as "there is a calibration for this". That is the
    `observed`-recorded-and-ignored shape 2a Task 5 already found once, and here
    it would serve a slope measured under different code against a hard memory
    constraint.
    """
    path = calibration.cache_path(tmp_path / "out.zarr")
    written = _result(1234.0)
    fresh = _key()
    stale = _key(versions="1111222233334444")

    calibration.store(path, fresh, written, versions={"numpy": "2.3.4"})

    assert calibration.load(path, stale) is None
    # The positive control for the miss: the same file, the same call, the key
    # the entry was written under. Without it, "returns None" is satisfied by a
    # `load` that always returns None.
    served = calibration.load(path, fresh)
    assert served is not None
    assert served.slope_bytes_per_series == 1234.0


def test_a_result_survives_the_round_trip_field_by_field(tmp_path):
    """Everything a later reader needs to judge the number comes back.

    Expected values determined independently: they are the fields Task 4 put on
    `CalibrationResult` because a cache entry must say what the number is
    licensed for -- the placement, the engine label, the linearity basis, the
    cap, the pinned floor and the ladder itself.

    Bug this catches: a serializer that stores the slope alone. The entry then
    reads as a measurement of the current configuration whatever it was measured
    under, and `linearity_basis` -- the one field that says the slope is not
    licensed beyond its ladder -- is exactly the one a "just the number" cache
    drops.
    """
    path = calibration.cache_path(tmp_path / "out.zarr")
    written = _result(1234.5)

    calibration.store(path, _key(), written, versions={"numpy": "2.3.4"})
    read = calibration.load(path, _key())

    assert read is not None
    assert read == written
    assert read.points == written.points
    assert read.placement is SolverPlacement.PER_SERIES_LIVE
    assert read.engine_label is MemoryEngineLabel.KALMAN_NUMPY
    assert read.linearity_basis == written.linearity_basis
    assert read.max_iter == 1
    assert read.floor_peak_bytes == _FLOOR_BYTES


def test_a_second_entry_does_not_evict_the_first(tmp_path):
    """One file, many keys: two machines or two configs share a store's cache.

    Expected value determined independently from design doc 11.4: the key exists
    so heterogeneous nodes each get their own entry automatically. A cache that
    held one entry would make the key decorative -- every second machine would
    evict the first and then miss.

    Bug this catches: `store` writing `{key: entry}` rather than merging into
    what is there. Two nodes resuming one store would then re-measure on every
    alternation, which is invisible except as a bill.
    """
    path = calibration.cache_path(tmp_path / "out.zarr")
    first = _key()
    second = _key(machine="0000000000000000")

    calibration.store(path, first, _result(111.0), versions={"numpy": "2.3.4"})
    calibration.store(path, second, _result(222.0), versions={"numpy": "2.3.4"})

    first_read = calibration.load(path, first)
    second_read = calibration.load(path, second)
    assert first_read is not None and second_read is not None
    assert first_read.slope_bytes_per_series == 111.0
    assert second_read.slope_bytes_per_series == 222.0
    assert len(_entries(path)) == 2


def test_an_unreadable_cache_is_a_miss_and_a_write_replaces_it(tmp_path):
    """A truncated cache costs a re-measurement rather than the run.

    Expected value determined independently from design doc 15.5: the cache
    lives beside the store on a preemptible instance, so a half-written file is
    a state that occurs. Re-measuring is the safe direction; refusing to run
    because a *cache* is damaged is not.

    The asymmetry is stated rather than discovered: `store` replaces an
    unparseable file wholesale, and the entries it would be preserving are
    unreadable anyway.

    Bug this catches: an unhandled `JSONDecodeError` out of `load`, which turns a
    damaged cache into a failed run -- and does it at the start of a job that was
    resuming precisely because the machine went away mid-write.
    """
    path = calibration.cache_path(tmp_path / "out.zarr")
    path.write_text('{"format": 1, "entries": {"abc": ')

    assert calibration.load(path, _key()) is None

    calibration.store(path, _key(), _result(333.0), versions={"numpy": "2.3.4"})

    repaired = calibration.load(path, _key())
    assert repaired is not None
    assert repaired.slope_bytes_per_series == 333.0
    absent = calibration.cache_path(tmp_path / "absent.zarr")
    assert calibration.load(absent, _key()) is None


# --------------------------------------------------------------------------
# The rule for using a measured number
# --------------------------------------------------------------------------


def test_a_slope_inside_the_band_is_usable_and_one_outside_it_is_not():
    """The design doc's own validation decides whether a measurement sizes a tile.

    Design doc 11.4 requires the calibration to be *validated against section
    9.4's analytic formula*, and `memory.slope_band` is that validation: a
    two-sided 1.5x band. Expected values derived by hand from
    `SLOPE_BAND_FACTOR = 1.5` against an analytic 602 B/series: the band is
    [401.33, 903.0], so 900 is inside and 904 is not, and so is 401.

    **THE PAIRING IS THE TEST** (i2). "This slope is refused" is satisfied by a
    rule that refuses everything, which would make every calibration decorative;
    the usable case is the half that can fail.

    Bug this catches: no acceptance rule at all. A non-positive slope makes
    `memory.tile_side` take the square root of a negative, and a small positive
    one raises nothing and sizes an enormous tile against a constraint the
    design doc calls hard -- 5 B/series is a plausible number and the arithmetic
    does not object to it.
    """
    analytic = 602

    assert calibration.unusable_reason(_result(900.0), analytic=analytic) is None
    assert calibration.unusable_reason(_result(402.0), analytic=analytic) is None

    for slope in (904.0, 401.0, 5.0, 0.0, -1200.0):
        reason = calibration.unusable_reason(_result(slope), analytic=analytic)
        assert reason is not None, f"{slope} B/series was accepted"
        assert str(analytic) in reason
        assert f"{slope:g}" in reason


def test_the_tiling_refuses_a_non_positive_per_series_cost():
    """The second of two deliberate guards, and each names the other.

    `calibration.unusable_reason` refuses a non-positive slope by the band --
    the band's lower bound is positive -- so nothing in the run path can reach
    this. **It is not dead code**: `tile_side_for` is public and its per-series
    override is the seam a calibration reaches it through, so a caller that
    skips the band arrives here. Removing either guard on the grounds that the
    other covers it removes the coverage as well.

    Expected value determined independently: `sqrt(x / 0)` and `sqrt(x / -1)`
    are a division error and a domain error, and neither names the calibration.

    Bug this catches: the override reaching the arithmetic unchecked, where the
    symptom is a traceback out of `math` rather than a diagnosis.
    """
    model: TileModelKwargs = {
        "d": 1,
        "k_beta": 4,
        "p_max": 3,
        "n_time": 24,
        "n_models": 2,
    }

    assert (
        tile_side_for(budget_bytes=_BUDGET_BYTES, floor=_FLOOR, **model)
        == _ANALYTIC_SIDE
    )
    assert (
        tile_side_for(
            budget_bytes=_BUDGET_BYTES,
            floor=_FLOOR,
            per_series_bytes=_CONSTRUCTED_SLOPE,
            **model,
        )
        == _CALIBRATED_SIDE
    )

    for bad in (0.0, -1.0):
        with pytest.raises(ValueError, match="per-series"):
            tile_side_for(
                budget_bytes=_BUDGET_BYTES,
                floor=_FLOOR,
                per_series_bytes=bad,
                **model,
            )


def test_the_constructed_budget_reaches_the_run_as_the_bytes_it_was_derived_for():
    """The fixture's budget round-trips through gigabytes without moving a side.

    `run()` takes a budget in GB and computes `int(gb * 10**9)`, and the window
    that selects one side here is a few kB wide. One byte lost to float
    formatting is not visible in the number and is visible in the side.

    Expected value determined independently: 228 267 295 has 9 significant
    digits and a float64 carries 15, so the round trip is exact.

    Bug this catches: a fixture whose two runs derive different sides for a
    reason that has nothing to do with the cache.
    """
    assert int((_BUDGET_BYTES / 10**9) * 10**9) == _BUDGET_BYTES


# --------------------------------------------------------------------------
# Through `run()`: the reachability pair, and the second process
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def calibrated(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """One real `--calibrate` run, shared by the tests that need its KEY.

    **THE MEASURED SLOPE IS NOT USED BY ANY TEST AND CANNOT BE.** At the sides a
    suite can afford the whole signal is 0.43 MB against +-0.3 MB of scatter
    between fresh children (Task 4), so its value is noise -- it may be refused
    by the band, and its sign is not guaranteed. What this fixture produces that
    nothing else can is a cache entry **under the key the production path
    computes**, which the tests below rewrite the slope of.

    Module-scoped because each ladder point is a fresh child that imports numba
    and fits a tile.
    """
    directory = tmp_path_factory.mktemp("calibrated")
    uri = _input(directory)
    config = _config(directory, uri)
    store = directory / "measured.zarr"

    run(
        config,
        store,
        floor=_FLOOR,
        max_iter=1,
        calibrate=True,
        calibration_ladder=(4, 8),
    )

    return {"directory": directory, "config": config, "store": store, "uri": uri}


@pytest.mark.slow
def test_a_calibrating_run_writes_an_entry_and_a_default_run_does_not(
    calibrated, tmp_path
):
    """The pure negative and its positive control, through the same wiring.

    *"A default run does not calibrate"* is an absence, and an absence is
    produced equally well by the thing being correctly suppressed and by a
    mechanism that cannot run at all (i2). The control is a run of the same
    function over the same configuration with the flag set.

    Expected values determined independently: the cache path is a function of
    the store path, so each run has its own; a run that never calibrates has no
    reason to create a file, and one that does must leave an entry keyed for
    this machine.

    Bug this catches, in the negative half: an ordinary run paying for a
    calibration nobody asked for -- 26.5 h at design doc 9.4's configuration on
    this box, and the design doc is explicit that a run which silently spends
    twenty minutes measuring before it starts is behaviour a user cannot
    predict. In the positive half: `--calibrate` parsing and doing nothing,
    which is the rule `--reuse-fits-from` and `engine=` were both held to.
    """
    default_store = tmp_path / "default.zarr"
    run(_config(tmp_path, calibrated["uri"]), default_store, floor=_FLOOR, max_iter=1)

    assert not calibration.cache_path(default_store).exists()
    assert calibration.cache_path(calibrated["store"]).exists()

    entries = _entries(calibration.cache_path(calibrated["store"]))
    assert len(entries) == 1
    (entry,) = entries.values()
    assert entry["result"]["max_iter"] == 1
    assert [point["derived_side"] for point in entry["result"]["points"]] == [4, 8]
    # The contributing versions, not only their digest, so a later mismatch can
    # name the package that moved.
    assert entry["versions"]["numpy"] == calibration.versions_digest()[1]["numpy"]
    assert len(entry["versions_digest"]) == 16


@pytest.mark.slow
def test_a_second_process_derives_the_calibrated_side_from_the_cache(
    calibrated, tmp_path
):
    """Written by one process, read by another, and the two sides differ.

    **THIS IS THE CACHE'S ONLY REASON TO EXIST** and it is unfalsifiable in one
    process: a calibration consumed in the session that produced it never reads
    a cache. (k), the category a same-process suite cannot reach.

    Expected values derived by hand and recorded on `_BUDGET_BYTES`: the
    analytic per-series cost is 602 B and gives side **8**, one tile on an 8x8
    grid; the constructed 900 B gives side **7**, four tiles. Both are asserted
    absolutely rather than only against each other -- a relation between two
    derived values passes when both are wrong in the same direction (i3).

    **The fixture is placed off the point where the two agree, deliberately**
    (i7): Task 4 measured the analytic and calibrated figures agreeing to 0.55
    standard errors, so a fixture that merely calibrates tests a cache nothing
    reads.

    Bug this catches: the cache never being read -- the run re-measuring, or
    ignoring the entry and falling through to the analytic formula. Either
    leaves side 8, one tile and basis `default`, and every other assertion in
    this module still passes.
    """
    source = calibration.cache_path(calibrated["store"])
    store = tmp_path / "cached.zarr"
    cache = calibration.cache_path(store)
    cache.write_text(source.read_text())
    _rewrite_slope(cache, _CONSTRUCTED_SLOPE)

    config = _config(tmp_path, calibrated["uri"])
    program = textwrap.dedent(
        """
        import json, sys
        from metamer.batch.run import run
        from metamer.core.memory import FloorReport
        floor = FloorReport(pre_warm_bytes={floor}, post_warm_bytes={floor},
                            with_input_bytes={floor}, peak_bytes={floor},
                            components={{"pinned": {floor}}})
        report = run(sys.argv[1], sys.argv[2], floor=floor, calibrate=True,
                     max_iter=1)
        print(json.dumps({{"side": report.tile_side, "tiles": report.tiles_total,
                           "warning": report.calibration_warning}}))
        """
    ).format(floor=_FLOOR_BYTES)
    completed = subprocess.run(
        [sys.executable, "-c", program, str(config), str(store)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout.strip().splitlines()[-1])

    assert payload["warning"] is None
    assert payload["side"] == _CALIBRATED_SIDE
    assert payload["tiles"] == 4
    stored = xr.open_zarr(str(store)).attrs
    assert stored["tile_side_basis"] == "cached"
    assert stored["tile_sides"]["shared"] == _CALIBRATED_SIDE
    assert stored["calibration"]["slope_bytes_per_series"] == _CONSTRUCTED_SLOPE
    assert stored["calibration"]["rejected"] is None

    # THE CONTROL, AND IT IS THE HALF THAT MAKES "differ measurably" A CLAIM.
    # Same config, same budget, same floor, no cache consulted.
    analytic = tmp_path / "analytic.zarr"
    report = run(config, analytic, floor=_FLOOR, max_iter=1)
    assert report.tile_side == _ANALYTIC_SIDE
    assert report.tiles_total == 1
    assert xr.open_zarr(str(analytic)).attrs["tile_side_basis"] == "default"
    assert "calibration" not in xr.open_zarr(str(analytic)).attrs


@pytest.mark.slow
def test_deleting_the_cache_leaves_the_store_openable_and_resumable(
    calibrated, tmp_path
):
    """The store never resolves through the cache, and the proof is deletion.

    The invariant is an ABSENCE of a dependency, which nothing else can assert:
    a docstring saying "the store does not read the cache" is unfalsifiable
    while the cache happens to be present in every test.

    Expected values derived by hand: the constructed slope of 900 B gives side
    **7** and four tiles on an 8x8 grid; the analytic 602 B gives **8**. So
    after the cache is deleted the resume derives 8 against a stored 7 and takes
    `completion.resume_tile_side`'s *stored < derived -> adopt the stored side*
    arm, finishing the outstanding tiles at 7.

    **THE PLACEMENT IS DELIBERATE AND ITS LIMIT IS STATED** (i7). The other arm
    -- a calibrated side LARGER than the analytic one, which happens when the
    measured slope comes in BELOW the formula -- is refused by that same gate,
    so *"deleting the cache can never break a store"* is true of the store and
    false of a resume. Naming that refusal is Phase 2b Task 6's task, and a
    fixture that landed in that arm would be testing Task 6 under Task 5's name.

    Bug this catches: a store acquiring a dependency on the cache -- a resume
    that reads the side back out of the cache rather than out of the store, or a
    store whose creation records a pointer to a cache path. Design doc 12.4
    requires every store to be self-contained; a cache on object storage that
    the store resolves through is a store that stops opening when a lifecycle
    rule expires a sibling object.
    """
    import signal

    store = tmp_path / "resumed.zarr"
    cache = calibration.cache_path(store)
    cache.write_text(calibration.cache_path(calibrated["store"]).read_text())
    _rewrite_slope(cache, _CONSTRUCTED_SLOPE)
    config = _config(tmp_path, calibrated["uri"])

    import os

    first = run(
        config,
        store,
        floor=_FLOOR,
        calibrate=True,
        max_iter=1,
        on_tile_written=lambda tile: os.kill(os.getpid(), signal.SIGTERM),
    )
    assert first.tile_side == _CALIBRATED_SIDE
    assert first.tiles_total == 4
    assert first.interrupted
    assert xr.open_zarr(str(store)).attrs["tile_side_basis"] == "cached"

    cache.unlink()
    assert not cache.exists()

    resumed = run(config, store, floor=_FLOOR, max_iter=1)

    assert resumed.tile_side == _CALIBRATED_SIDE
    assert not resumed.interrupted
    assert resumed.tiles_written + resumed.tiles_skipped == 4
    # The store still says what produced its side: the basis was written at
    # creation and a resume neither rewrites nor re-derives it.
    assert xr.open_zarr(str(store)).attrs["tile_side_basis"] == "cached"


@pytest.mark.slow
def test_a_measurement_the_band_refuses_is_recorded_rather_than_silent(
    calibrated, tmp_path
):
    """ "Never calibrated" and "calibrated and rejected" are two facts.

    Under the fallback rule a rejected measurement leaves `tile_side_basis` at
    `default`, which is also what a run that never calibrated writes -- so
    without a second field a store that spent hours measuring is
    indistinguishable from one that measured nothing. The fill-value rule at a
    provenance key: the absence of `calibration` is what means "no calibration
    was consulted".

    Expected values derived by hand: 2000 B/series is 3.32x the analytic 602 and
    outside the [401.33, 903.0] band, so the side falls back to the analytic
    **8** and one tile.

    Bug this catches: the fallback being silent. The run would then look exactly
    like a run that never calibrated, and the user who waited for the
    measurement would have no way to learn it was discarded -- while the cache
    on disk says a calibration happened.
    """
    store = tmp_path / "rejected.zarr"
    cache = calibration.cache_path(store)
    cache.write_text(calibration.cache_path(calibrated["store"]).read_text())
    _rewrite_slope(cache, 2000.0)

    report = run(
        _config(tmp_path, calibrated["uri"]),
        store,
        floor=_FLOOR,
        calibrate=True,
        max_iter=1,
    )

    assert report.tile_side == _ANALYTIC_SIDE
    assert report.tiles_total == 1
    assert report.calibration_warning is not None
    assert "2000" in report.calibration_warning

    stored = xr.open_zarr(str(store)).attrs
    assert stored["tile_side_basis"] == "default"
    assert stored["calibration"]["slope_bytes_per_series"] == 2000.0
    assert stored["calibration"]["rejected"] == report.calibration_warning


@pytest.mark.slow
def test_a_recompute_copies_a_calibrated_sources_basis(calibrated, tmp_path):
    """A recompute derives no side, so it claims no basis of its own.

    **THIS IS `tests/test_reuse.py`'s (i7)-FLAGGED TEST, MOVED OFF ITS FIXED
    POINT, WHICH IS WHY IT IS HERE RATHER THAN THERE.** Until this task, nothing
    could write a basis other than `default`, so *"copy the source's"* and
    *"write DEFAULT"* agreed on every store that suite could build and the
    assertion could not fail for its own reason. A calibrated source is the
    second writable basis, and it lives where the cache fixture is.

    Expected values derived by hand and recorded on `_BUDGET_BYTES`: the
    constructed 900 B/series gives side **7**, so the source is built at 7 with
    basis `cached`, and the recompute -- which reads the side back out of the
    source (a1) rather than deriving one -- must carry both.

    Bug this catches: a recompute writing `TileSideBasis.DEFAULT`, which claims
    it derived the side analytically when it derived nothing. Task 6 compares
    bases across a resume, so it would read a basis change that never happened
    and send the user to a cache that was never involved.
    """
    source = tmp_path / "source.zarr"
    cache = calibration.cache_path(source)
    cache.write_text(calibration.cache_path(calibrated["store"]).read_text())
    _rewrite_slope(cache, _CONSTRUCTED_SLOPE)
    config = _config(tmp_path, calibrated["uri"])

    built = run(config, source, floor=_FLOOR, max_iter=1, calibrate=True)
    assert built.tile_side == _CALIBRATED_SIDE
    assert xr.open_zarr(str(source)).attrs["tile_side_basis"] == "cached"

    new = tmp_path / "new.zarr"
    recomputed = run(
        _config(tmp_path, calibrated["uri"], name="new.toml"),
        new,
        floor=_FLOOR,
        reuse_fits_from=source,
    )

    assert recomputed.tile_side == _CALIBRATED_SIDE
    assert xr.open_zarr(str(new)).attrs["tile_side_basis"] == "cached"
    # And it copies the BASIS without copying the calibration: the new store
    # consulted none, so it records none. The two facts are separate.
    assert "calibration" not in xr.open_zarr(str(new)).attrs


def test_a_calibration_alongside_a_recompute_is_refused(tmp_path):
    """A recompute derives no side, so there is nothing for a calibration to size.

    `--reuse-fits-from` reads the tile side back out of the source store (a1)
    and skips the budget arithmetic entirely, because the rule bounds a FIT's
    resident set and a recompute has none. A calibration alongside it would
    measure for hours and change nothing.

    Expected value determined independently from the project's own rule: a flag
    that parses and does nothing reads as supported, which is why
    `--reuse-fits-from` was absent until it worked and why `engine=` landed with
    the path that could reach it.

    Bug this catches: the two flags being silently compatible. The user waits
    26.5 h at design doc 9.4's configuration for a number that cannot move any
    side in the run they asked for.
    """
    uri = _input(tmp_path)
    config = _config(tmp_path, uri)
    source = tmp_path / "source.zarr"
    run(config, source, floor=_FLOOR, max_iter=1)

    with pytest.raises(ValidationError, match="recompute"):
        run(
            _config(tmp_path, uri, name="new.toml"),
            tmp_path / "new.zarr",
            floor=_FLOOR,
            reuse_fits_from=source,
            calibrate=True,
        )


@pytest.mark.parametrize("flag", ["--calibrate", "--recalibrate"])
def test_both_command_line_flags_reach_the_run(tmp_path, flag):
    """The flags are wired through, and `--recalibrate` implies `--calibrate`.

    **THE REFUSAL IS THE INSTRUMENT, AND THAT IS WHY THIS IS AFFORDABLE.** A
    flag that parses and does nothing reads as supported -- the rule
    `--reuse-fits-from` was held to at 2a Task 12 -- and asserting the flag by
    running a real calibration through the command line would cost the ladder.
    Pairing it with `--reuse-fits-from`, which `run` refuses when a calibration
    is asked for, makes the refusal observable proof that the flag arrived, for
    the price of no measurement at all.

    **An exit code is a property of a PROCESS**, so this runs `python -m
    metamer` and reads `returncode` rather than calling `main()`.

    Expected values determined independently: 3 is `ExitCode.CONFIG_INVALID`,
    which is what a layer-3 semantic refusal maps to, and the message is the one
    `run` raises. Under argparse's own exit for an unknown option the code would
    also be 3 -- `_Parser.error` overrides it -- so the MESSAGE is what
    discriminates "the flag was refused for its meaning" from "the flag was not
    recognized at all".

    Bug this catches: `--calibrate` parsed into a namespace nobody reads, and
    `--recalibrate` accepted while leaving `calibrate` false, so forcing past a
    hit would silently do nothing at all.
    """
    uri = _input(tmp_path)
    source = tmp_path / "source.zarr"
    run(_config(tmp_path, uri), source, floor=_FLOOR, max_iter=1)

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "metamer",
            str(_config(tmp_path, uri, name="new.toml")),
            str(tmp_path / "new.zarr"),
            "--reuse-fits-from",
            str(source),
            flag,
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 3, completed.stderr
    assert "a recompute derives no tile side" in completed.stderr
    assert not (tmp_path / "new.zarr").exists()
