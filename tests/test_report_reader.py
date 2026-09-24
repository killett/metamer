"""Sub-phase 2f Task 1: the reader, the import boundary, and completeness.

**THE PROPERTY EVERY TEST HERE SERVES IS "USABLE ON SOMEONE ELSE'S STORE"**
(design doc section 14.2). A user with a store and no config must be able to
run the report, which makes the import boundary a correctness requirement
rather than a tidiness one, and makes the reader's refusals part of the
contract.
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import numpy as np
import pytest
import xarray as xr
import zarr

from metamer.batch.input import InputContractError
from metamer.batch.run import run
from metamer.batch.validation import ExitCode, exit_code_for
from metamer.core.outcomes import Outcome
from metamer.report.reader import read_store
from tests import conftest

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")

_CONFIG = """
data_uri = "{uri}"
variable = "sla"
signal_terms = ["constant", "trend"]
candidates = ["white", "white + matern12"]
criteria = ["aic", "hqic"]
"""

#: The modules `metamer.report` must not drag in, each with WHY it is listed.
#: **The four are not the same kind of claim and the distinction is
#: load-bearing** -- a later reader who cannot tell them apart will either
#: over-protect the soft ones or relax the hard ones.
FORBIDDEN: dict[str, str] = {
    # PORTABILITY. Lives behind the [report] extra, so it may genuinely be
    # ABSENT on a machine that can read a store. Importing it at module scope
    # makes the numbers path unusable where the store is readable -- the
    # failure `tests/test_readme_figure.py` records CI having had once.
    "matplotlib": "portability",
    # PORTABILITY. A [batch] dependency, and a JIT compiler is the most
    # expensive import in the tree.
    "numba": "portability",
    # BOUNDARY. Ships with metamer, so a user who can import metamer can
    # import pydantic: excluding it buys a design boundary and 0.74 s, NOT
    # portability. It is the config machinery, and "usable on someone else's
    # store" means a user with a store and NO CONFIG -- who must not be made
    # to load the validator for a config they do not have.
    "pydantic": "boundary",
    # BOUNDARY. The run driver. A reader of a store does not need the machinery
    # that produced it.
    "metamer.batch.run": "boundary",
}


def _months(n: int) -> np.ndarray:
    origin = np.datetime64("2000-01-01")
    return np.array([origin + np.timedelta64(31 * i, "D") for i in range(n)])


@pytest.fixture(scope="module")
def finished_store(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One REAL store from a real run, built once.

    A real store rather than a hand-built directory: the reader's subject is
    the schema, the label axes and the completion bitmap, and a fabricated
    store would let all three drift from what a run actually writes. This is
    the fixture class that caught two defects a planted-outcome fixture could
    not -- see the module docstring of `tests/test_abort.py`.
    """
    base = tmp_path_factory.mktemp("finished")
    dataset = xr.Dataset(
        {"sla": (("time", "y", "x"), np.zeros((24, 4, 4), dtype="float32"))},
        coords={"time": _months(24), "y": np.arange(4), "x": np.arange(4)},
    )
    uri = base / "in.zarr"
    dataset.to_zarr(uri)
    config = base / "c.toml"
    config.write_text(textwrap.dedent(_CONFIG.format(uri=uri)))
    store = base / "out.zarr"
    run(config, store)
    return store


# ---------------------------------------------------------------------------
# The import boundary
# ---------------------------------------------------------------------------

#: **ONE PROBE, TWO TARGETS.** The test and its positive control call this with
#: different `target`s; a control written as a second implementation of the same
#: idea tests two things and proves neither.
_PROBE = textwrap.dedent(
    """
    import json, sys
    import {target}
    print(json.dumps(sorted(m for m in sys.modules if m in {forbidden!r})))
    """
)


#: **THE RUN-TIME PROBE: ONE SOURCE, TWO PREAMBLES.** It imports `read_store`
#: and CALLS it on a store built by the PARENT -- build the fixture inside the
#: probe and the reading describes the fixture builder, which is a `run()` and
#: drags in everything the boundary excludes. The subject and its positive
#: control differ by the injected `preamble` alone.
#:
#: **THE SCOPE IS DISCOVERED BY WALKING THE PACKAGE, NOT HAND-PICKED.** The
#: probe was aimed at the reader alone and would have been silent about 2f
#: Task 3's `metamer.report.drop`, which imports `metamer.batch.decimate` --
#: exactly the kind of arrival this boundary exists to notice. **A hand-picked
#: list misses the NEXT module as surely as it missed that one**, which is the
#: golden table's lesson one instrument over: define the scope mechanically and
#: a new member is covered on the day it lands rather than the day somebody
#: remembers. `pkgutil.walk_packages` decides the set; the numbers-path
#: functions are then called on the parent-built fixture.
#:
#: **WHEN TASK 8 ADDS THE ENTRY POINT THIS BECOMES `python -m metamer.report
#: <store>`**, which exercises the whole path by construction and needs no
#: list at all.
_RUNTIME_PROBE = textwrap.dedent(
    """
    import importlib, json, pkgutil, sys
    {preamble}
    import metamer.report
    # **THE SCOPE IS DISCOVERED, NOT LISTED.** Every module under the package,
    # walked and imported, so the next one is covered on the day it lands.
    discovered = sorted(
        name
        for _, name, _ in pkgutil.walk_packages(
            metamer.report.__path__, "metamer.report."
        )
    )
    for name in discovered:
        importlib.import_module(name)
    at_import = sorted(m for m in sys.modules if m in {forbidden!r})
    from metamer.report.drop import describe
    from metamer.report.numbers import compute
    from metamer.report.reader import read_store
    view = read_store({store!r})
    compute(view)
    describe(view)
    print(json.dumps({{
        "at_import": at_import,
        "after_call": sorted(m for m in sys.modules if m in {forbidden!r}),
        "modules": len(sys.modules),
        "discovered": discovered,
    }}))
    """
)


def _reads(store: Path, preamble: str = "") -> dict[str, object]:
    """Forbidden modules and graph size after `read_store` has actually RUN.

    Two readings from one subprocess: at the moment `read_store` is imported,
    and after it has been called. **The second is the one the boundary is
    about** -- a convenience import inside the function body is invisible to
    the first, and `metamer/report/__init__.py` being docstring-only means the
    package-level probe is invisible to both.
    """
    source = _RUNTIME_PROBE.format(
        preamble=preamble, forbidden=set(FORBIDDEN), store=str(store)
    )
    result = subprocess.run(
        [sys.executable, "-c", source],
        capture_output=True,
        text=True,
        env={"PYTHONPATH": "src", "PATH": "/usr/bin:/bin"},
        check=False,
    )
    assert result.returncode == 0, result.stderr
    reading: dict[str, object] = json.loads(result.stdout)
    return reading


@pytest.fixture(scope="module")
def runtime_reading(finished_store: Path) -> dict[str, object]:
    """The clean run-time reading, taken once and asserted by two tests."""
    return _reads(finished_store)


def _imports(target: str) -> list[str]:
    """Which forbidden modules are in `sys.modules` after importing `target`.

    **In a SUBPROCESS, and that answers a different question from the control
    below.** `tests/test_core_isolation.py` supplies the reason: inside the
    pytest session every one of these is already imported by some other test
    module, so an in-process check measures the session and not the target.
    That is about VISIBILITY. Whether the probe can see a violation AT ALL is
    about DISCRIMINATION, and no amount of subprocess isolation establishes it.
    """
    source = _PROBE.format(target=target, forbidden=set(FORBIDDEN))
    result = subprocess.run(
        [sys.executable, "-c", source],
        capture_output=True,
        text=True,
        env={"PYTHONPATH": "src", "PATH": "/usr/bin:/bin"},
        check=False,
    )
    assert result.returncode == 0, result.stderr
    loaded: list[str] = json.loads(result.stdout)
    return loaded


def test_the_report_package_imports_no_config_or_plotting_machinery():
    """`metamer.report` drags in neither the config path nor a plotting stack.

    **THIS IS THE CHEAP FIRST CHECK AND IT IS NOT THE BOUNDARY CLAIM.**
    `metamer/report/__init__.py` is docstring-only, so this probe stops at
    **65** modules (measured 2026-09-21) having reached neither the reader nor
    zarr, and "no forbidden module" is true here because nothing was imported.
    A positive control proves the DETECTOR; it cannot show what the detector is
    aimed at. The boundary is established by
    `test_reading_a_store_imports_no_forbidden_module` below, which imports
    `read_store` and calls it. This one is kept because it is a hundredth of
    the cost and fails first on a module-scope arrival in the package itself.

    Expected values determined independently by measuring each candidate import
    at Task 1's pre-flight, 2026-09-20: `metamer` alone is 64 modules,
    `metamer.core.outcomes` 708, `metamer.batch.store` 928, and
    `metamer.batch.run` 1002 -- and what the last adds over the one before it
    is `pydantic`, the config machinery. `numba` and `matplotlib` appear in
    none of them.

    Bug this catches: a convenience import -- `from metamer.batch.run import
    run` for one constant, or a module-scope `import matplotlib` in the maps
    module -- which makes the report unusable exactly where a store is
    readable. That is the failure CI already had once, recorded in
    `tests/test_readme_figure.py`.

    **`metamer.core` AND `metamer.core.fit` RIDE ALONG AND ARE NOT LISTED**,
    which is a correction to this plan's own D10. It claimed the report could
    import `metamer.core.outcomes` "as a leaf"; there is no such thing --
    Python executes a package's `__init__.py` on any submodule import, and
    `metamer/core/__init__.py` deliberately imports `families` (a load-bearing
    registration side effect) and `core.fit`. The cost is +0.5 s and no JIT.
    """
    assert _imports("metamer.report") == []


def test_the_import_probe_can_see_a_violation():
    """THE POSITIVE CONTROL, and it uses the identical probe with another target.

    Expected value determined independently: `metamer.batch.run` imports the
    config machinery, so `pydantic` is in its graph -- measured at the
    pre-flight, and true by construction since `run` validates a config.

    Bug this catches: a probe that reports nothing because it never imported
    anything, or because the forbidden set is misspelled, or because
    `sys.modules` is being read wrong. **All three pass the test above and all
    three make it worthless.** (a10): before reading an instrument, demonstrate
    it can produce both answers -- and the subprocess isolation that makes the
    test above meaningful says nothing about whether the probe DISCRIMINATES.

    **It calls `_imports`, not a parallel implementation**, because a control
    written twice tests two things and proves neither.
    """
    assert "pydantic" in _imports("metamer.batch.run")


def test_every_forbidden_module_declares_whether_it_is_portability_or_boundary():
    """The four exclusions are not one kind of claim, and the table says which.

    Expected values determined independently: a module behind an optional extra
    may be ABSENT, so excluding it is a portability guarantee; a module that
    ships with `metamer` is always importable, so excluding it is a design
    boundary bought for a reason other than portability.

    Bug this catches: a later reader treating all four alike -- relaxing
    `matplotlib` because "pydantic is only a boundary", or hard-blocking
    `pydantic` on portability grounds that do not exist. A list without classes
    invites both.
    """
    assert set(FORBIDDEN) == {
        "matplotlib",
        "numba",
        "pydantic",
        "metamer.batch.run",
    }
    assert set(FORBIDDEN.values()) == {"portability", "boundary"}
    assert FORBIDDEN["matplotlib"] == "portability"
    assert FORBIDDEN["pydantic"] == "boundary"


def test_reading_a_store_imports_no_forbidden_module(runtime_reading):
    """The boundary, measured on the SUBJECT: `read_store` imported and CALLED.

    Expected values determined independently by re-measuring on 2026-09-21
    with the fixture store built in the parent: **930** modules once
    `read_store` is imported, **933** once it has run, and **no forbidden
    module at either stage**. The 65-module package probe above reconciles
    exactly with Task 1's measured 64 for `metamer` alone plus a
    docstring-only `metamer/report/__init__.py`, which adds itself.

    Bug this catches: a convenience import the package probe structurally
    cannot see -- `from metamer.batch.run import run` for one constant inside
    `read_store`, or a module-scope `import matplotlib` in a helper the reader
    reaches only at call time. That is the failure CI already had once, in
    `tests/test_readme_figure.py`.

    **THE PROBE'S STRUCTURAL LIMIT, STATED RATHER THAN PRICED.** A
    `sys.modules` check cannot see a lazy import by construction -- that is
    what lazy means -- and D10 requires `matplotlib` imported INSIDE the maps
    function. So this test is silent about the one design D10 chose: it gives
    both answers for an import-time violation and only one for a run-time one
    in a branch nothing here calls. **Calling `read_store` is what narrows the
    gap** rather than closing it; the numbers path is exercised instead of
    hoped about.
    """
    assert runtime_reading["at_import"] == []
    assert runtime_reading["after_call"] == []

    # **(c7): ASSERT THE SIZE OF WHAT THE DISCOVERY MECHANISM FOUND.** A
    # `walk_packages` that returned nothing would make every assertion above
    # trivially true -- the same vacuity the ceiling had when it read 65
    # modules. The oracle is the directory, listed here rather than inside the
    # probe, so the walk is checked against something that did not do the walk.
    package = Path(__file__).resolve().parents[1] / "src" / "metamer" / "report"
    on_disk = sorted(
        f"metamer.report.{path.stem}"
        for path in package.glob("*.py")
        if path.stem != "__init__"
    )
    assert runtime_reading["discovered"] == on_disk, (
        "the package walk and the directory disagree about which report "
        "modules exist; a walk that finds fewer makes this whole probe vacuous"
    )
    assert len(on_disk) >= 3, on_disk


def test_the_runtime_probe_can_see_a_violation(finished_store):
    """THE POSITIVE CONTROL for the run-time probe, on both of its readings.

    Expected value determined independently: `pydantic` is in `FORBIDDEN` and
    importing it puts it in `sys.modules` -- true by construction -- and it
    arrives with dependencies, so the graph is strictly larger than the clean
    reading.

    Bug this catches: a probe that reports nothing because the forbidden set
    is misspelled, because `sys.modules` is read wrong, or because the count
    is a constant. **All three pass the two tests above and all three make
    them worthless.** (a10): before reading an instrument, demonstrate it can
    produce both answers -- and the SIZE reading needs that demonstration as
    much as the name reading does, which is why this control asserts both.

    **It injects one import into the identical probe source**, rather than
    reimplementing it; a control written twice tests two things and proves
    neither.
    """
    clean = _reads(finished_store)
    tripped = _reads(finished_store, preamble="import pydantic")

    assert tripped["at_import"] == ["pydantic"]
    assert tripped["after_call"] == ["pydantic"]
    assert isinstance(tripped["modules"], int)
    assert isinstance(clean["modules"], int)
    assert tripped["modules"] > clean["modules"]


def test_the_report_module_graph_stays_under_its_ceiling(runtime_reading):
    """A SIZE assertion, because a denylist cannot see a fifth arrival.

    Expected value determined independently: **936** modules after every module
    under `metamer.report` has been imported and the numbers path run on a real
    store, measured 2026-09-23.
    The ceiling is **980**, and the margin's basis is the OBSERVED SPREAD
    rather than a round percentage -- this project does not carry an estimate
    where it has a measurement.

    **THE SUBJECT CHANGED TWICE ON 2026-09-23 AND NEITHER MOVE IS DRIFT.** The
    probe read **933** while it exercised the reader alone; **935** once it
    imported and called `metamer.report.drop`, which brings
    `metamer.batch.decimate`; and **936** once the scope became a
    `pkgutil` walk of the package rather than a hand-picked list. **A band
    describes a SUBJECT**, so when the subject grows the band is RE-MEASURED,
    not compared against -- the re-derivation rule below is about a reading
    moving under a FIXED subject, which is a different event and means
    something different. Only this docstring can tell the two apart, which is
    why each move is recorded with what changed.

    **~~"comfortably above the measurement, well below `metamer.batch.run`'s
    1002"~~ -- THAT ARGUMENT IS GONE, AND THE CEILING IS A BACKSTOP FOR
    UNNAMED DEPENDENCIES RATHER THAN A SECOND COPY OF THE DENYLIST.**
    `pydantic` and `metamer.batch.run` are caught BY NAME, so `batch.run`'s
    1002 is not the figure this bound has to discriminate against; it exists
    for the fifth arrival nobody listed. The margin is 5% because module
    counts drift with a lockfile update and with the platform, and **a bound
    tight enough to fire on routine drift becomes a number people bump without
    reading it** -- the old 900 was such a number in the other direction: it
    passed on 65 while the real subject stood at 933.

    Bug this catches: the failure the four named modules structurally cannot.
    `metamer/core/__init__.py`'s registration side effect is load-bearing and
    is staying, which makes this graph hostage to the spine: anyone adding a
    heavy dependency there or to `families/` lands it in the report silently.

    **Handoff (c7) reaching a new place**: assert the SIZE of what a discovery
    mechanism found, not only the values it found. An unasserted enumeration
    is a silent denominator.

    **FOUR ENVIRONMENTS, FOUR COUNTS -- measured 2026-09-22 from CI run
    35698698743, every one of them GREEN:**

    | environment | reader only | + drop | + package walk |
    |---|---|---|---|
    | CI, 3.12 | 912 | 914 | **owed: next green run** |
    | CI, 3.13 | 913 | 915 | **owed** |
    | CI, 3.14 | 920 | 922 | **owed** |
    | local, 3.13 | 933 | 935 | **936** |

    **CI's SECOND COLUMN CAME IN AT EXACTLY +2, AS PREDICTED** (run
    `35954296638`, all green), which is the first evidence that the
    environment gap is a constant offset rather than something that moves with
    the subject.

    **THE MARGIN IS DERIVED FROM THE SPREAD, AND HERE IS THE ARITHMETIC.** On
    each subject the band has spanned **21-22** modules across four
    environments that all pass, and each subject change has moved every
    reading by the same small amount. The ceiling sits **44** above the
    highest reading -- **twice the observed spread** -- which is why it holds:
    drift of the kind already seen cannot reach it, and an arrival larger than
    everything drift has ever done can. **CI's three readings on the walked
    subject are owed at the next green run**, and are expected at about +1.

    **WHAT THE SPREAD IS MADE OF**: 8 modules across interpreter versions, and
    **20 between local 3.13 and CI 3.13 -- the same interpreter, so that gap is
    the ENVIRONMENT** (a dev environment against the declared dependency set),
    and it is the larger half.

    **A PIN WOULD HAVE FAILED THREE OF THESE FOUR GREEN RUNS.**
    Pin-versus-bound was ruled on an *expectation* of drift; this measures it.

    **IF A NEW ENVIRONMENT READS OUTSIDE 912-933, RE-DERIVE THE MARGIN FROM
    THE NEW BAND -- DO NOT BUMP THE NUMBER.** A threshold raised to admit a
    reading nobody explained is the guard decaying into a ritual, which is the
    failure mode a bound has and a pin does not.

    **THESE NUMBERS EXIST ONLY BECAUSE THE COUNT ALSO GOES TO
    `DIAGNOSTIC_LINES`.** An assertion message prints when it FIRES; all four
    runs above passed, so the message said nothing in any of them. **A
    measurement that only surfaces on failure is not a record.**
    """
    count = runtime_reading["modules"]
    assert isinstance(count, int)
    # **THE MEASUREMENT REACHES A CI LOG FROM A PASSING TEST, AND THE
    # ASSERTION MESSAGE DOES NOT.** The ruling owes "CI's own count, recorded
    # beside the local 933 after the first run", and a message that prints
    # only when the bound fires has no source for it on a green run. This is
    # the channel `conftest.DIAGNOSTIC_LINES` exists for.
    conftest.DIAGNOSTIC_LINES.append(
        f"report module graph: {count} modules after the whole package ran "
        "(ceiling 980; local reference 936, 2026-09-23)"
    )
    assert count < 980, (
        f"the report now loads {count} modules against a ceiling of 980, "
        "measured at 936 on 2026-09-23. Something heavy has entered the graph, "
        "most likely through metamer/core/__init__.py or a family module -- or "
        "a new report module brought a dependency with it, in which case the "
        "band is re-measured for the new subject rather than the number bumped"
    )


# ---------------------------------------------------------------------------
# The reader
# ---------------------------------------------------------------------------


def test_a_finished_store_round_trips_every_array_and_both_label_axes(finished_store):
    """The reader opens what the writer wrote, including the labels.

    Expected values determined independently from the config: two candidates
    and two criteria, on a 4 x 4 grid, so `outcome` is (4, 4, 2), `delta_ic` is
    (4, 4, 2, 2), `selected` is (4, 4, 2) and `n_valid` is (4, 4). The model
    labels are the canonical forms of the requested candidates and the
    criterion labels are `aic` and `hqic`.

    Bug this catches: a reader keyed on a group or array name the writer does
    not use -- `/status/outcomes` for `/status/outcome`, or the criterion axis
    read off the root instead of off `/selection/`. **No unit test of the
    writer can see that**, because the writer is not wrong; the two halves
    simply never meet until something reads what was written.
    """
    view = read_store(finished_store)

    assert view.outcome.shape == (4, 4, 2)
    assert view.delta_ic.shape == (4, 4, 2, 2)
    assert view.selected.shape == (4, 4, 2)
    assert view.n_valid.shape == (4, 4)
    assert view.iterations.shape == (4, 4, 2)
    assert view.criterion_labels == ("aic", "hqic")
    assert len(view.model_labels) == 2
    assert all(isinstance(label, str) and label for label in view.model_labels)
    assert view.attrs["schema_version"] == 5


def test_an_unknown_schema_version_is_refused_naming_both_versions(
    finished_store, tmp_path
):
    """A store from a newer writer is refused, not read.

    Expected value determined independently: `store.SCHEMA_VERSION` is 5, so a
    store claiming 6 is from a writer this reader does not know.

    Bug this catches: a reader that ignores the version and reports numbers off
    a layout it has guessed at -- silently, since a later schema is most likely
    to ADD arrays rather than move the ones being read. The message names both
    versions because "unsupported schema" sends a user to the wrong place;
    what they need to know is which writer made the store and which reader they
    have.
    """
    import shutil

    store = tmp_path / "future.zarr"
    shutil.copytree(finished_store, store)
    root = zarr.open_group(str(store), mode="r+")
    root.attrs["schema_version"] = 6

    with pytest.raises(InputContractError) as caught:
        read_store(store)

    assert exit_code_for(caught.value) is ExitCode.DATA_INVALID
    assert "6" in str(caught.value) and "5" in str(caught.value)


@pytest.mark.parametrize(
    ("what", "build"),
    [
        ("a directory that is not a store", lambda p: p.mkdir()),
        (
            "a zarr group that is not a metamer store",
            lambda p: zarr.open_group(str(p), mode="w"),
        ),
    ],
)
def test_a_store_shaped_thing_that_is_not_one_exits_data_invalid(what, build, tmp_path):
    """Neither an empty directory nor a foreign zarr group is read.

    Expected value determined independently: design doc section 14.3 gives
    `DATA_INVALID` for input the run cannot use, and for this entry point the
    store IS the data -- there is no config.

    Bug this catches: a bare `KeyError` or `FileNotFoundError` escaping to the
    top, which `metamer.__main__` maps to `INTERNAL_ERROR`. That tells a
    scripting user the report is broken when their input is, which is the exact
    collision 2e's Task 1 separated exit 5 from exit 1 to prevent.
    """
    target = tmp_path / "thing"
    build(target)

    with pytest.raises(InputContractError) as caught:
        read_store(target)

    assert exit_code_for(caught.value) is ExitCode.DATA_INVALID, what


def test_a_finished_store_reports_every_tile_complete(finished_store):
    """The completion state comes back as counted tiles, not as a boolean.

    Expected value determined independently: the fixture's run completed, so
    every tile's bit is set and `complete == total`.

    Bug this catches: a reader that reports completeness as "finished or not",
    which cannot say `N of M` -- and design doc section 14.2's report must put
    that number beside every denominator, because a rate quoted without its
    population is what a reader carries away.
    """
    view = read_store(finished_store)

    assert view.completion.total > 0
    assert view.completion.complete == view.completion.total
    assert view.completion.is_finished is True


def test_an_incomplete_store_is_described_and_not_refused(finished_store, tmp_path):
    """An unfinished store reports `N of M` and does not raise.

    Expected value determined independently: clearing one bit of a fixture
    whose run completed leaves `complete == total - 1`.

    Bug this catches: a reader that treats incompleteness as an error. Design
    doc section 14.1 exists because discovering at hour 9 that ten hours were
    wasted is the expensive outcome, so **a report that refuses to run on
    exactly the store that discovery produces is the mechanism declining its
    own use case.** Section 12.5's "a finished store should hold none" is a
    fact about finished stores, not a definition of this command's subject.
    """
    import shutil

    store = tmp_path / "partial.zarr"
    shutil.copytree(finished_store, store)
    root = zarr.open_group(str(store), mode="r+")
    tiles = root["completion/tiles"]
    assert isinstance(tiles, zarr.Array)
    before = int(np.count_nonzero(np.asarray(tiles[:])))
    tiles[0, 0] = 0

    view = read_store(store)

    assert view.completion.total == before
    assert view.completion.complete == before - 1
    assert view.completion.is_finished is False


def test_the_bitmap_is_authoritative_and_a_disagreement_is_reported(
    finished_store, tmp_path
):
    """Completeness is read from the bitmap; a contradiction is surfaced, not resolved.

    Expected value determined independently: 2a's data-then-bitmap invariant
    makes the bitmap the authority -- data is written, THEN the bit is set --
    so a tile whose bit is set while its cells read `NOT_ATTEMPTED` is a
    contradiction between two records rather than a state either one describes.

    Bug this catches: a reader that infers completeness from `NOT_ATTEMPTED`
    instead of from the bitmap. **Those answer different questions** -- the
    bitmap says which tiles were WRITTEN, the outcome says what a cell HOLDS --
    and a complete tile holding ANY `NOT_ATTEMPTED` cell is a contradiction:
    section 12.5 says that code means "nothing wrote here" and that a finished
    store should hold none, while a decided skip is `SCREENED_OUT` -- the
    OPPOSITE member. Silently resolving the two lets a partially-written tile
    read as a screened candidate.

    **FIXTURE REACHABILITY, STATED RATHER THAN IMPLIED:** this state is
    CONSTRUCTIBLE and **not producible by any run** -- 2a's write path lands
    the data before it sets the bit, so no run can leave a complete tile
    unwritten. The test does not imply the condition occurs in the wild; it
    pins what the reader does if it ever does, which is what a report that
    survives its run is for.
    """
    import shutil

    store = tmp_path / "disagreeing.zarr"
    shutil.copytree(finished_store, store)
    root = zarr.open_group(str(store), mode="r+")
    outcome = root["status/outcome"]
    assert isinstance(outcome, zarr.Array)
    block = np.asarray(outcome[:])
    block[0, 0, :] = Outcome.NOT_ATTEMPTED.code
    outcome[:] = block

    view = read_store(store)

    assert view.completion.is_finished is True
    assert view.disagreements, (
        "a complete tile holding NOT_ATTEMPTED is a contradiction between the "
        "bitmap and the outcome array, and the reader must say so"
    )
    assert any("NOT_ATTEMPTED" in note for note in view.disagreements)


def test_a_complete_store_reports_no_disagreement(finished_store):
    """The positive control for the check above.

    Bug this catches: a disagreement detector that fires on every store, under
    which the test above passes for the wrong reason and every report carries a
    defect notice. (i2), and it is not optional -- the sibling asserts that
    something is REPORTED, so this asserts the quiet case is reachable.
    """
    assert read_store(finished_store).disagreements == ()


def test_the_reader_opens_the_store_read_only(finished_store, tmp_path):
    """Reading a store leaves its bytes untouched.

    Expected value determined independently: a read is a read.

    Bug this catches: opening in `r+` "for convenience", which is how a
    consolidated-metadata rewrite or an attrs normalisation lands on someone
    else's store. **This is the cheap half of the guarantee** -- Task 8 asserts
    the strong form by running the whole report against a store whose write
    permission has been removed, which catches a write of identical bytes, a
    reordered-key rewrite and a write on a path this test does not exercise.
    """
    import hashlib
    import shutil

    store = tmp_path / "readonly.zarr"
    shutil.copytree(finished_store, store)

    def digest() -> str:
        acc = hashlib.sha256()
        for path in sorted(store.rglob("*")):
            if path.is_file():
                acc.update(path.relative_to(store).as_posix().encode())
                acc.update(path.read_bytes())
        return acc.hexdigest()

    before = digest()
    read_store(store)

    assert digest() == before
