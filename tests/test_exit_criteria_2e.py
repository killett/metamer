"""Phase 2e's exit criteria: the record bound to the tree, and the readings taken outside.

**THE SUITE IS AN INDEPENDENT CHECK, NOT A ROLL-UP.** A criterion satisfied by
re-running the implementing task's own test verifies nothing new. The nine
criterion tests here read their subject from somewhere the implementing test
did not: a process exit code, a store's bytes, a document's text, a docstring
parsed off disk, a committed artifact, or a second store built to differ from
the first in exactly one respect.

**FOUR READINGS WERE STATED IN THE PLAN MORE STRONGLY THAN ANY TASK's TEST
TOOK THEM, AND THIS SUITE TAKES THEM AS STATED RATHER THAN SOFTENING THE
RECORD TO MATCH.** Criterion 1 names a fitted point COUNT and Task 2 compared
arrays; criterion 15 says BYTE-FOR-BYTE and Task 6 compared arrays; criterion
4 names two numbers under two namings and no test renamed a store for
`read_amplification`; criterion 16 wants both codes in ONE test and Task 6 had
them in two. Each gets the stronger test here.

**ONE CRITERION IS REDUCED AND NONE FAILED.** Criterion 14's row is section
14.2's and section 14.2 is 2f's; what 2e can read off its stores -- the
denominator, computable and equal to the recorded one -- is read.
"""

from __future__ import annotations

import ast
import inspect
import json
import pathlib
import subprocess
import sys
from dataclasses import replace
from typing import Any

import numpy as np
import pytest
import xarray as xr
import zarr

from metamer.batch import twopass
from metamer.batch.abort import CandidateFailurePolicy, abort_verdict
from metamer.batch.completion import completed_tiles
from metamer.batch.input import open_input
from metamer.batch.run import run
from metamer.batch.tiling import Tile, read_amplification
from metamer.batch.twopass import run_two_pass
from metamer.batch.validation import ExitCode
from metamer.core.outcomes import Outcome
from tests.exit_criteria_2b import PHASE_2B_EXIT_CRITERIA, Verdict
from tests.exit_criteria_2c import PHASE_2C_EXIT_CRITERIA
from tests.exit_criteria_2d import PHASE_2D_EXIT_CRITERIA
from tests.exit_criteria_2e import PHASE_2E_EXIT_CRITERIA, READINGS
from tests.test_abort import _CONFIG as _STRIDE_2_CONFIG
from tests.test_abort import _plane, _set_outcomes, _shape
from tests.test_early_abort import _INJECT, _early_abort, _labels, _outcome
from tests.test_early_abort import _config as _abort_config
from tests.test_early_abort import _input as _abort_input
from tests.test_runner import _invoke, _invoke_crashing, _months

pytestmark = [
    pytest.mark.slow,
    pytest.mark.filterwarnings("ignore::UserWarning"),
]

DESIGN_DOC = pathlib.Path("docs/superpowers/specs/2026-08-04-metamer-design.md")
NOTES = pathlib.Path("docs/superpowers/notes")
RUNNER_TESTS = pathlib.Path("tests/test_runner.py")


def _collected_test_names() -> set[str]:
    """Every `def test_...` under `tests/`, found by parsing rather than importing."""
    names: set[str] = set()
    for path in pathlib.Path("tests").rglob("test_*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                names.add(node.name)
    return names


def _attrs(store: pathlib.Path) -> dict[str, Any]:
    """A store's root attrs, off disk, through JSON so nothing lazy survives."""
    value: dict[str, Any] = json.loads(
        json.dumps(dict(zarr.open_group(str(store), mode="r").attrs))
    )
    return value


# ---------------------------------------------------------------------------
# The binders
# ---------------------------------------------------------------------------


def test_the_record_covers_every_criterion_exactly_once():
    """Nineteen criteria, numbered 1 to 19, each once.

    Expected value determined independently: the plan's own table has eighteen
    rows, and the nineteenth was added by decision on 2026-09-18.

    Bug this catches: a criterion dropped during editing -- which reads, from
    the closing table, exactly like a criterion that was never written.
    """
    numbers = [criterion.number for criterion in PHASE_2E_EXIT_CRITERIA]

    assert sorted(numbers) == list(range(1, 20))
    assert len(set(numbers)) == len(numbers)


def test_every_criterion_names_evidence_that_exists():
    """A verdict standing on a test that was renamed or deleted fails here.

    The limit is stated rather than implied: a static scan checks that the
    evidence EXISTS, not that it is relevant. Relevance is carried by each
    criterion's `statement` sitting beside its names.

    Bug this catches: a test renamed during a refactor, leaving a verdict whose
    stated evidence does not exist -- which reads exactly like a verdict whose
    evidence does. Two of 2e's own tests were renamed rather than edited (the
    six-exit-codes test, the positional-tiling test) and both are named here
    under their new names.
    """
    have = _collected_test_names()
    missing = {
        (criterion.number, name)
        for criterion in PHASE_2E_EXIT_CRITERIA
        for name in criterion.established_by
        if name not in have
    }

    assert not missing, missing
    for criterion in PHASE_2E_EXIT_CRITERIA:
        assert criterion.established_by, criterion.number


def test_every_criterion_names_a_reading_with_no_exempt_list():
    """All nineteen, not a listed subset.

    Expected values determined independently: `READINGS` is the plan's own
    third column.

    Bug this catches: a criterion whose verdict is about an unnamed quantity.
    An exempt list would be (c5): an enumeration of the members that existed
    when it was written, leaving a criterion added later exempt by default.
    """
    for criterion in PHASE_2E_EXIT_CRITERIA:
        assert criterion.reading is not None, criterion.number
        assert criterion.reading in READINGS, (criterion.number, criterion.reading)


def test_every_non_met_verdict_states_its_scope_and_every_criterion_its_outside():
    """A reduced or failed verdict says what it does and does not cover.

    Expected value determined independently: MET may carry an empty scope; the
    other two may not, and every criterion says what it is driven from or why
    nothing outside exists.

    Bug this catches: criterion 14 reduced with no statement of what was and
    was not established, which downstream is indistinguishable from a criterion
    measured and passed narrowly.
    """
    for criterion in PHASE_2E_EXIT_CRITERIA:
        if criterion.verdict is not Verdict.MET:
            assert criterion.scope.strip(), criterion.number
        assert criterion.outside.strip(), criterion.number


def test_the_inherited_verdicts_are_read_out_of_their_own_records_by_number():
    """2b's 6 and 7, 2c's 11, and 2d's 6, 11, 12 and 14 stay as recorded.

    Expected values determined independently: the plan says 2b's criteria 6 and
    7 stay FAILED and 2e does not reopen the residency model; 2c's 11 stays
    reduced; and 2d's 6, 11 and 14 stay FAILED with 12 reduced, because 2e
    re-runs no rung and re-cuts no boundary.

    Bug this catches: 2e credited with a repair it did not make. Copying
    booleans here would drift in the direction that matters -- 2e would go on
    asserting they failed after somebody fixed them -- so they are looked up by
    number, which also catches a renumbering, loudly.
    """
    by_number_2b = {c.number: c for c in PHASE_2B_EXIT_CRITERIA}
    for number in (6, 7):
        assert by_number_2b[number].verdict is Verdict.FAILED, number
        assert by_number_2b[number].scope.strip(), number

    by_number_2c = {c.number: c for c in PHASE_2C_EXIT_CRITERIA}
    assert by_number_2c[11].verdict is Verdict.MET_WITH_REDUCED_SCOPE

    by_number_2d = {c.number: c for c in PHASE_2D_EXIT_CRITERIA}
    for number in (6, 11, 14):
        assert by_number_2d[number].verdict is Verdict.FAILED, number
        assert by_number_2d[number].scope.strip(), number
    assert by_number_2d[12].verdict is Verdict.MET_WITH_REDUCED_SCOPE

    # And 2e's own record does not claim any of them: numbers are per sub-phase.
    assert max(c.number for c in PHASE_2E_EXIT_CRITERIA) == 19


def test_the_record_is_serialisable_so_the_closing_table_cannot_drift_from_it():
    """Every field is plain data, so PROGRESS.md's table has one source.

    Expected value determined independently: `json.dumps` succeeds with
    `Verdict` a `StrEnum` and everything else a string, an int or a tuple.

    Bug this catches: a field holding a callable, which would make the record
    readable only by importing it -- and a table nobody can render is a table
    that gets retyped, which is how two copies drift.
    """
    payload = json.dumps(
        [
            {
                "number": c.number,
                "statement": c.statement,
                "verdict": str(c.verdict),
                "reading": c.reading,
                "scope": c.scope,
                "established_by": list(c.established_by),
                "outside": c.outside,
            }
            for c in PHASE_2E_EXIT_CRITERIA
        ]
    )

    assert json.loads(payload)[0]["number"] == 1
    assert len(json.loads(payload)) == 19


# ---------------------------------------------------------------------------
# Criteria 1 and 3 -- one lat/lon run through the shipped entry point
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def latlon_run(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """One real `python -m metamer` over a `latitude`/`longitude` store.

    Seeded normal data rather than zeros: zarr serves a zero-filled store from
    the fill value without touching a chunk, and a fit over constants is not
    the fit this criterion is about.
    """
    base = tmp_path_factory.mktemp("latlon")
    n_time, n_y, n_x = 24, 3, 4
    values = np.random.default_rng(7).normal(size=(n_time, n_y, n_x))
    dataset = xr.Dataset(
        {"sla": (("time", "latitude", "longitude"), values.astype("float32"))},
        coords={
            "time": _months(n_time),
            "latitude": np.linspace(-30.0, -28.0, n_y),
            "longitude": np.linspace(150.0, 153.0, n_x),
        },
    )
    source = base / "latlon.zarr"
    dataset.to_zarr(source)
    config = base / "c.toml"
    config.write_text(
        f'data_uri = "{source}"\nvariable = "sla"\n'
        'signal_terms = ["constant", "trend", "annual"]\n'
        'candidates = ["white", "white + matern12"]\ncriteria = ["aic", "hqic"]\n'
    )
    store = base / "out.zarr"
    result = _invoke(str(config), str(store), "--no-progress")
    return {
        "result": result,
        "store": store,
        "source": source,
        "shape": (n_y, n_x),
    }


def test_criterion_1_a_latlon_store_exits_ok_and_every_point_is_fitted(latlon_run):
    """Exit 0 from the shipped entry point, and every point carries a fit outcome.

    Expected values determined independently: the exit code is section 14.3's
    0, and the grid is 3 x 4 with no masked cell and two candidates, so the
    fitted point count is 3 x 4 x 2 = 24 -- every outcome is one a FIT wrote
    (success or a taxonomy failure), none is `NOT_ATTEMPTED` and none is a
    skip the run assigned without fitting.

    Bug this catches: the closure being partial -- a lat/lon store that exits 0
    because the run wrote nothing, or fitted a subset. 'It runs' is a negative;
    the count is the positive control.
    """
    result = latlon_run["result"]
    assert result.returncode == ExitCode.OK, result.stderr
    assert "Traceback" not in result.stderr

    store = latlon_run["store"]
    assert bool(completed_tiles(store).all())
    codes = _outcome(store)
    n_y, n_x = latlon_run["shape"]
    assert codes.shape[:2] == (n_y, n_x)

    unfitted = {
        Outcome.NOT_ATTEMPTED.code,
        Outcome.CANDIDATE_DROPPED.code,
        Outcome.SCREENED_OUT.code,
        Outcome.INSUFFICIENT_DATA.code,
        Outcome.NOT_APPLICABLE.code,
    }
    fitted = int(np.isin(codes, list(unfitted), invert=True).sum())
    assert fitted == n_y * n_x * codes.shape[2] == 24
    assert int((codes == Outcome.OK.code).sum()) > 0


def test_criterion_3_the_fingerprint_keys_a_latlon_store_by_its_own_names(latlon_run):
    """`spatial_coordinates` is keyed `latitude`/`longitude`, with the file's values.

    Expected values determined independently: the keys are the input file's own
    dimension names and the values are its coordinate arrays, read back from
    the file with xarray rather than from anything metamer computed.

    Bug this catches: the rename closer taken by accident -- a fingerprint that
    normalises the names to `y`/`x`, which passes every functional test and
    makes the store assert a provenance its source file does not have (D1).
    """
    components = _attrs(latlon_run["store"])["geometry_components"]
    spatial = components["spatial_coordinates"]
    source = xr.open_zarr(str(latlon_run["source"]))

    assert set(spatial) == {"latitude", "longitude"}
    assert "y" not in spatial and "x" not in spatial
    for name in ("latitude", "longitude"):
        np.testing.assert_allclose(
            np.asarray(spatial[name], dtype=float), source[name].values
        )


# ---------------------------------------------------------------------------
# Criterion 4 -- read amplification under two namings
# ---------------------------------------------------------------------------


def test_criterion_4_read_amplification_is_one_number_under_two_namings(tmp_path):
    """The same data, chunking and tile give the same amplification whatever the names.

    Expected value determined independently by hand, on a deliberately
    NON-SQUARE chunking of (12, 4, 8): a 4 x 4 tile at rows 2-6 and columns
    6-10 straddles the row boundary at 4 and the column boundary at 8, touches
    2 x 2 = 4 chunks of 4 x 8 = 32 cells each, and uses 16 -- 128 / 16 = 8.0.
    Both namings must give 8.0, not merely agree: two wrong numbers can agree.

    Bug this catches: a positional rewrite that silently transposes the axes.
    On a square chunking a transpose gives the same number; here it reads the
    chunk shape as (8, 4), the tile sits inside one 8-row chunk and straddles
    two 4-column chunks, and the answer is 64 / 16 = 4.0 -- a plausible wrong
    number rather than an error, which is why the chunking is not square.
    """
    n_time, n_y, n_x = 12, 16, 16
    data = np.random.default_rng(0).standard_normal((n_time, n_y, n_x))
    chunks = (12, 4, 8)

    def _write(dims: tuple[str, str]) -> str:
        dataset = xr.Dataset(
            {"sla": (("time", *dims), data.astype("float32"))},
            coords={
                "time": _months(n_time),
                dims[0]: np.arange(n_y, dtype=float),
                dims[1]: np.arange(n_x, dtype=float),
            },
        )
        path = tmp_path / f"{dims[0]}.zarr"
        dataset.to_zarr(path, encoding={"sla": {"chunks": chunks}})
        return str(path)

    # 4 x 4 at (2, 6): straddles the y boundary at 4 (chunks 0 and 1 on y) and
    # the x boundary at 8 (chunks 0 and 1 on x): 4 chunks x (4 x 8) = 128 read
    # over 16 used = 8.0. Transposed -- y chunk 8, x chunk 4 -- the tile would
    # sit inside one 8-row chunk and straddle two 4-column chunks: 64 / 16 = 4.0.
    tile = Tile(y_start=2, y_stop=6, x_start=6, x_stop=10)
    plain = read_amplification(open_input(_write(("y", "x")), "sla"), tile)
    renamed = read_amplification(
        open_input(_write(("latitude", "longitude")), "sla"), tile
    )

    assert plain == pytest.approx(8.0)
    assert renamed == pytest.approx(8.0)
    assert plain == renamed


# ---------------------------------------------------------------------------
# Criterion 7 -- the provenance is at the test, as text on disk
# ---------------------------------------------------------------------------


def test_criterion_7_the_internal_error_guard_carries_its_dated_live_producer():
    """The guard's docstring names the date, the frame and the store it once matched.

    Expected values determined independently from the record: the live
    producer was `KeyError: 'y'` in `read_amplification` on a
    `latitude`/`longitude` store, verified 2026-09-12 before Task 2 closed it.

    Bug this catches: the provenance tidied out of the docstring, after which
    the constructed exception is a mechanism checked only against a mutant it
    was written alongside -- (i2), with nothing left to say it was ever more.
    Parsed off disk rather than imported so the check reads the file.
    """
    tree = ast.parse(RUNNER_TESTS.read_text())
    guards = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and node.name
        == "test_an_unhandled_exception_exits_internal_error_and_keeps_its_traceback"
    ]
    assert len(guards) == 1
    docstring = ast.get_docstring(guards[0]) or ""

    assert "2026-09-12" in docstring
    assert "read_amplification" in docstring
    assert "KeyError: 'y'" in docstring
    assert "latitude" in docstring and "longitude" in docstring


# ---------------------------------------------------------------------------
# Criterion 9 -- every committed histogram, recomputed under both rules
# ---------------------------------------------------------------------------


def _histograms(document: Any) -> list[dict[str, int]]:
    """Every `outcome_counts` mapping anywhere in a decoded JSON document."""
    found: list[dict[str, int]] = []
    if isinstance(document, dict):
        for key, value in document.items():
            if key == "outcome_counts" and isinstance(value, dict):
                found.append({str(k): int(v) for k, v in value.items()})
            else:
                found.extend(_histograms(value))
    elif isinstance(document, list):
        for item in document:
            found.extend(_histograms(item))
    return found


def _member(name: str) -> Outcome:
    """Resolve a histogram key to an `Outcome`, loudly."""
    if name in Outcome.__members__:
        return Outcome[name]
    return Outcome(name)


def test_criterion_9_every_committed_histogram_recomputes_unchanged():
    """Failed and eligible counts agree under the old rule and the new, per report.

    Expected values determined independently: under the pre-Task-3 rule
    `CANDIDATE_DROPPED` counted as a failure; under section 12.5 it does not.
    The two rules give different counts on exactly the histograms that contain
    the member, so agreement on every committed histogram IS the claim that no
    committed number moved -- checked, not inferred.

    Bug this catches: a committed report that quietly contains the member, so
    the reclassification is retroactive and two rates in the record are
    computed under different denominators. The positive control is that the
    arithmetic ran on a histogram carrying a real failure: the recount must
    see at least one `DEGENERATE_HESSIAN`.
    """
    old_failures = {m for m in Outcome if m.is_failure} | {Outcome.CANDIDATE_DROPPED}
    seen = 0
    failures_seen = 0
    for path in sorted(NOTES.glob("*.json")):
        for histogram in _histograms(json.loads(path.read_text())):
            seen += 1
            new_failed = new_eligible = old_failed = old_eligible = 0
            for name, count in histogram.items():
                member = _member(name)
                if member.is_eligible:
                    new_eligible += count
                    old_eligible += count
                    new_failed += count if member.is_failure else 0
                    old_failed += count if member in old_failures else 0
                    failures_seen += count if member.is_failure else 0
            assert (new_failed, new_eligible) == (old_failed, old_eligible), path.name
    assert seen > 0, "no committed histogram was recounted; the check is vacuous"
    assert failures_seen > 0, "no committed failure was recounted; the check is vacuous"


# ---------------------------------------------------------------------------
# Criterion 10 -- the counters, both directions
# ---------------------------------------------------------------------------


def test_criterion_10_the_decision_path_cannot_see_the_counters_in_either_direction():
    """The verdict and the driver never import the counters, and the seam returns None.

    Expected values determined independently: from the direction of the
    dependency. The display reads the run's output and the run must not read
    the display -- so importing the whole decision path (`abort`, `twopass`,
    `run`) must not load `metamer.progress`, and the seam the counters hang off
    is typed to return `None`, so nothing they compute has a way back in.

    Bug this catches: the free-looking optimisation -- 'we already have these
    tallies, let's abort on them' -- in either of its two forms: a `batch`
    module importing the counters, or a seam widened to return a value the run
    then reads. Run in a subprocess for the reason `test_progress.py` gives:
    in-session the module is already imported by the test file.

    **PROVED TO BITE 2026-09-18:** a `from metamer.progress import LiveCounters`
    was added to `abort.py` and the subprocess half failed, naming the leak.
    """
    code = (
        "import metamer.batch.abort, metamer.batch.twopass, metamer.batch.run, sys; "
        "leaked = [m for m in sys.modules if m == 'metamer.progress']; "
        "assert not leaked, leaked"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr

    seam = inspect.signature(run).parameters["on_tile_progress"].annotation
    assert isinstance(seam, str)  # `from __future__ import annotations`
    assert seam.replace(" ", "").endswith("None]|None"), seam


# ---------------------------------------------------------------------------
# Criterion 12 -- the same store, cropped to its ocean
# ---------------------------------------------------------------------------


def _ocean_and_land(
    tmp_path: pathlib.Path,
) -> tuple[pathlib.Path, pathlib.Path]:
    """Two real pass-1 stores: a 10 x 8 grid whose lower half is land, and its ocean.

    The ocean rows carry IDENTICAL values in both inputs, so the only difference
    between the stores is the land the first one also has.
    """
    n_time, n_y, n_x = 24, 10, 8
    values = np.random.default_rng(3).normal(size=(n_time, n_y, n_x)).astype("float32")
    full = values.copy()
    full[:, 5:, :] = np.nan
    crop = values[:, :5, :].copy()

    def _write(array: np.ndarray, name: str) -> str:
        dataset = xr.Dataset(
            {"sla": (("time", "y", "x"), array)},
            coords={
                "time": _months(n_time),
                "y": np.arange(array.shape[1]),
                "x": np.arange(array.shape[2]),
            },
        )
        dataset.to_zarr(tmp_path / name)
        return str(tmp_path / name)

    stores = []
    for array, name in ((full, "full"), (crop, "crop")):
        config = tmp_path / f"{name}.toml"
        config.write_text(_STRIDE_2_CONFIG.format(uri=_write(array, f"{name}.zarr")))
        store = tmp_path / f"{name}.pass1.zarr"
        run(config, store, decimate=True)
        stores.append(store)
    return stores[0], stores[1]


def test_criterion_12_a_store_and_its_ocean_crop_reach_one_verdict(tmp_path):
    """A pass-1 store and the same store cropped to its ocean carry one verdict.

    Expected values determined independently: stride 2 over 10 x 8 gives a
    5 x 4 coarse grid whose rows 3 and 4 (fine rows 6 and 8) are land and were
    written ineligible BY THE RUN; the crop is 5 x 8 and gives 3 x 4. The same
    outcome pattern is planted on the twelve ocean points of each -- candidate
    0 failing at all twelve (12/12 = 1.0, above 0.9), candidate 1 at three
    (3/12 = 0.25, below) -- so under `drop` the verdict is `drop` naming
    candidate 0, with `failed`, `eligible` and `rate` equal in both stores.

    Bug this catches: a rate over ALL points rather than eligible ones -- the
    full store would read 12/20 = 0.6 for candidate 0 and continue where the
    crop drops. On a global run that is every verdict dominated by land.

    **PROVED TO BITE 2026-09-18:** the eligibility filter in `_rate_for` was
    replaced by `if True` and this test failed on the rates -- the full store
    read 3/20 = 0.15 for candidate 1 against the crop's 3/12 = 0.25.
    """
    full, crop = _ocean_and_land(tmp_path)
    rows, columns, models = _shape(full)
    assert (rows, columns, models) == (5, 4, 2)
    assert _shape(crop) == (3, 4, 2)

    # The land rows were written by the run, not planted, and are ineligible.
    written = _outcome(full)
    for code in np.unique(written[3:, :, :]):
        assert not Outcome.from_code(int(code)).is_eligible, int(code)

    pattern = [
        _plane((3, 4), 1.0, fill=Outcome.OK),
        _plane((3, 4), 0.25, fill=Outcome.OK),
    ]
    planted = written.copy()
    for column, plane in enumerate(pattern):
        planted[:3, :, column] = plane
    _set_outcomes(full, [planted[:, :, m] for m in range(models)])
    _set_outcomes(crop, pattern)

    whole = abort_verdict(full, policy=CandidateFailurePolicy.DROP)
    ocean = abort_verdict(crop, policy=CandidateFailurePolicy.DROP)

    assert whole.rates == ocean.rates
    assert whole.rates[0].eligible == 12 and whole.rates[0].failed == 12
    assert whole.rates[1].eligible == 12 and whole.rates[1].failed == 3
    assert whole.action == ocean.action == "drop"
    assert whole.candidates == ocean.candidates == (whole.rates[0].candidate,)


# ---------------------------------------------------------------------------
# Criterion 14 -- the live denominator, off the two stores
# ---------------------------------------------------------------------------


def test_criterion_14_the_live_denominator_is_pass_ones_and_is_computable(
    tmp_path, monkeypatch
):
    """'Points where the candidate was still live' is pass 1's eligible set, and it is recorded.

    Expected values determined independently: a 6 x 6 grid at stride 2 has a
    3 x 3 coarse lattice, all data, so the candidate was live at 9 points; pass
    2 has 36 points and the drop writes into all of them. The verdict is the
    REAL one with its action forced to `drop`, so the recorded rates are the
    rates pass 1 actually produced and not an injected number.

    Bug this catches: D9's feedback loop -- a denominator taken from the pass-2
    store, where the run itself wrote `CANDIDATE_DROPPED` at every point, so
    any rate over it reports the decision. The recorded `eligible` must equal
    the pass-1 count and be strictly smaller than the pass-2 population.
    """
    config = _abort_config(tmp_path, _abort_input(tmp_path))

    def _forced_drop(path: pathlib.Path | str, **kwargs: Any) -> Any:
        real = abort_verdict(path, **kwargs)
        target = _labels(pathlib.Path(path))[1]
        return replace(
            real, action="drop", candidates=(target,), reason="forced drop, real rates"
        )

    monkeypatch.setattr(twopass, "abort_verdict", _forced_drop)
    report = run_two_pass(
        config,
        tmp_path / "out.zarr",
        candidate_failure_policy=CandidateFailurePolicy.DROP,
    )
    assert report.pass1_path is not None and report.pass2 is not None

    pass1 = _outcome(report.pass1_path)[:, :, 1]
    live = int(sum(Outcome.from_code(int(c)).is_eligible for c in pass1.ravel()))
    recorded = _early_abort(report.store_path)
    row = recorded["rates"][1]
    pass2 = _outcome(report.store_path)[:, :, 1]

    assert live == 9
    assert row["candidate"] == _labels(report.store_path)[1]
    assert row["eligible"] == live
    assert recorded["population"] == "pass 1 coarse grid"
    assert (pass2 == Outcome.CANDIDATE_DROPPED.code).all()
    assert not (pass1 == Outcome.CANDIDATE_DROPPED.code).any()
    assert live < pass2.size == 36


# ---------------------------------------------------------------------------
# Criterion 15 -- byte-for-byte
# ---------------------------------------------------------------------------


def _files(root: pathlib.Path) -> dict[pathlib.Path, bytes]:
    """Every file under a store, by relative path, as bytes."""
    return {
        path.relative_to(root): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_criterion_15_no_early_abort_and_a_continue_verdict_write_the_same_bytes(
    tmp_path, monkeypatch
):
    """Every file under the two stores is identical except the recorded verdict.

    Expected values determined independently: the flag disables a decision and
    not a computation, so the two runs write the same chunks, the same
    metadata and the same attrs -- except `early_abort`, which one records as
    not evaluated and the other as `continue`. That single key in the root
    metadata is the ONLY permitted difference, and it is asserted to be
    present so the comparison cannot pass on two empty stores.

    Bug this catches: the flag changing what is fitted, or what is written
    beside the fits -- an array comparison (Task 6's) passes against a store
    that differs in a chunk the comparison did not name.
    """
    from metamer.batch.abort import AbortVerdict

    config = _abort_config(tmp_path, _abort_input(tmp_path))

    def _forbidden(*_: object, **__: object) -> AbortVerdict:
        raise AssertionError("--no-early-abort must not consult the verdict")

    monkeypatch.setattr(twopass, "abort_verdict", _forbidden)
    off = run_two_pass(config, tmp_path / "off.zarr", early_abort=False)
    monkeypatch.setattr(
        twopass,
        "abort_verdict",
        lambda path, **_: AbortVerdict("continue", (), (), 0.90, "clean"),
    )
    kept = run_two_pass(config, tmp_path / "kept.zarr")

    mine = _files(off.store_path)
    theirs = _files(kept.store_path)
    assert set(mine) == set(theirs)
    assert len(mine) > 1
    differing = {path for path in mine if mine[path] != theirs[path]}
    assert differing == {pathlib.Path("zarr.json")}, sorted(map(str, differing))

    left = json.loads(mine[pathlib.Path("zarr.json")])
    right = json.loads(theirs[pathlib.Path("zarr.json")])
    assert left["attributes"].pop("early_abort") == {
        "evaluated": False,
        "reason": "--no-early-abort",
    }
    assert right["attributes"].pop("early_abort")["action"] == "continue"
    assert left == right


# ---------------------------------------------------------------------------
# Criterion 16 -- both codes, one test
# ---------------------------------------------------------------------------


def test_criterion_16_a_thresholded_run_and_a_crashed_run_exit_different_codes(
    tmp_path,
):
    """A run that finished past a failing candidate exits 1; a run that crashed exits 5.

    Expected values determined independently from section 14.3: 1 is
    'completed with failures above threshold' and 5 is 'internal error -- the
    run did not finish'. Opposite facts about a run, so the codes differ, the
    traceback appears only with 5, and the coarse-pass caveat only with 1.

    Bug this catches: the collision reintroduced by a later catch clause -- a
    crash reported as 1, which a resuming script would resume from. Both in
    one test because the whole point of Task 1 is that they are different
    events, and two tests can be edited apart.

    **PROVED TO BITE 2026-09-18:** exit 1's branch in `__main__` was disabled
    and the thresholded run came back 0 while the crashed run stayed 5.
    """
    config = _abort_config(tmp_path, _abort_input(tmp_path))
    thresholded = subprocess.run(
        [
            sys.executable,
            "-c",
            _INJECT,
            "drop",
            "1",
            str(config),
            str(tmp_path / "thresholded.zarr"),
            "--two-pass",
            "--on-candidate-failure=drop",
            "--no-progress",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    crashed = _invoke_crashing(str(config), str(tmp_path / "crashed.zarr"))

    codes = {"thresholded": thresholded.returncode, "crashed": crashed.returncode}
    assert codes == {
        "thresholded": ExitCode.COMPLETED_WITH_FAILURES,
        "crashed": ExitCode.INTERNAL_ERROR,
    }, (thresholded.stderr, crashed.stderr)
    assert "Traceback" in crashed.stderr
    assert "Traceback" not in thresholded.stderr
    assert "COARSE pass" in thresholded.stderr
    assert "COARSE pass" not in crashed.stderr


# ---------------------------------------------------------------------------
# Criterion 18 -- the design doc's own sentence
# ---------------------------------------------------------------------------


def test_criterion_18_the_design_doc_states_the_one_pass_decision_and_the_open_note_is_gone():
    """Section 14.1 carries reading (i), section 14.3 carries its consequence, and Task 0's note is replaced.

    Expected values determined independently from the plan: Task 0 recorded
    the gap as open with the sentence 'this section does not yet choose' and
    said Task 6 'replaces this note with the answer'; Task 6 took reading (i)
    and, because exit 1's producer is the verdict, wrote beside code 1 that a
    one-pass run can never exit 1.

    Bug this catches: the decision taken in the code and not in the document,
    or the answer written BESIDE the open note rather than in its place -- the
    stale-document shape the plan's Task 0 was designed to avoid.
    """
    text = DESIGN_DOC.read_text()
    section_14_1 = text[text.index("### 14.1") : text.index("### 14.2")]
    section_14_3 = text[text.index("### 14.3") : text.index("## 15.")]

    assert "READING (i): THE EARLY ABORT IS TWO-PASS" in section_14_1
    assert "A ONE-PASS RUN CAN NEVER EXIT 1" in section_14_3
    assert "does not yet choose" not in text
    assert "replaces this note with the answer" not in text


# ---------------------------------------------------------------------------
# Criterion 19 -- the same code for different reasons
# ---------------------------------------------------------------------------


def test_criterion_19_no_evidence_and_a_clean_pass_exit_zero_for_different_reasons(
    tmp_path,
):
    """Two runs exit 0; the stores and the final lines say which reason each had.

    Expected values determined independently from section 14.3 as amended
    2026-09-18: exit 1 is the verdict finding a candidate above threshold, and
    neither of these verdicts found one, so both are 0. The first run is the
    empty-sample fixture -- every even row masked, stride 2, so the coarse
    lattice has no eligible point while the odd rows carry data -- under the
    REAL verdict; the second is the same shape of run under an injected clean
    verdict. Only the first carries the headline, and the two stores record
    `no_evidence` and `continue` respectively.

    Bug this catches: the exit vocabulary collapsing the two reasons in either
    direction -- `no_evidence` given its own non-zero code (a script would then
    treat a run with a complete map as failed or resumable), or the verdict
    recorded as `continue` so the store cannot say the sample held nothing.
    This is the one place the same-code-different-reason claim is asserted,
    so it is asserted on both halves in one test.

    **PROVED TO BITE 2026-09-18:** `__main__` was given a branch returning 1
    for a `no_evidence` verdict and this test failed on the pair of codes
    while the clean half stayed 0.
    """
    masked = _abort_config(
        tmp_path,
        _abort_input(tmp_path, masked_rows=slice(None, None, 2)),
        name="m.toml",
    )
    no_evidence = _invoke(
        str(masked), str(tmp_path / "no_evidence.zarr"), "--two-pass", "--no-progress"
    )
    clean = subprocess.run(
        [
            sys.executable,
            "-c",
            _INJECT,
            "continue",
            "-1",
            str(
                _abort_config(tmp_path, _abort_input(tmp_path / "full"), name="c.toml")
            ),
            str(tmp_path / "clean.zarr"),
            "--two-pass",
            "--no-progress",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert (no_evidence.returncode, clean.returncode) == (ExitCode.OK, ExitCode.OK), (
        no_evidence.stderr,
        clean.stderr,
    )
    assert "Traceback" not in no_evidence.stderr and "Traceback" not in clean.stderr
    assert "early abort: no evidence" in no_evidence.stderr
    assert "early abort: no evidence" not in clean.stderr
    recorded = {
        "no_evidence": _early_abort(tmp_path / "no_evidence.zarr"),
        "clean": _early_abort(tmp_path / "clean.zarr"),
    }
    assert recorded["no_evidence"]["action"] == "no_evidence"
    assert recorded["clean"]["action"] == "continue"
    assert all(rate["eligible"] == 0 for rate in recorded["no_evidence"]["rates"])
    assert bool(completed_tiles(tmp_path / "no_evidence.zarr").all())
