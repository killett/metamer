"""Sub-phase 2f Task 1: the reader, the import boundary, and completeness.

**THE PROPERTY EVERY TEST HERE SERVES IS "USABLE ON SOMEONE ELSE'S STORE"**
(design doc section 14.2). A user with a store and no config must be able to
run the report, which makes the import boundary a correctness requirement
rather than a tidiness one, and makes the reader's refusals part of the
contract.
"""

from __future__ import annotations

import dataclasses
import json
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import cast

import numpy as np
import pytest
import xarray as xr
import zarr

from metamer.batch.input import InputContractError
from metamer.batch.run import run
from metamer.batch.validation import ExitCode, exit_code_for
from metamer.core.outcomes import Outcome
from metamer.report.reader import StoreView, read_store
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
#: The report's module-graph ceiling. **A BOUND, NOT A PIN** -- the ceiling
#: test carries the spread it is derived from and the triggers that
#: re-derive it.
CEILING = 980

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

    Expected value determined independently: the reading this test emits on
    the current subject -- every module under `metamer.report` imported and the
    numbers path run on a real store. **The figure lives in the diagnostic line
    this test writes on every run**, not transcribed here, because every task
    from 5 to 9 adds a module and a transcribed figure would make each one buy
    a docstring edit.
    The ceiling is `CEILING`, and the margin's basis is the OBSERVED SPREAD
    rather than a round percentage -- this project does not carry an estimate
    where it has a measurement.

    **THE BASIS, NOT THE HISTORY.** The band has spanned about **21 modules**
    across four environments on every subject measured so far, and each change
    of subject has moved every environment by the same small amount -- so the
    local-versus-CI gap is a constant offset rather than something that scales.
    The ceiling sits more than **twice that spread** above the highest reading,
    which is why it holds: drift of the kind already seen cannot reach it, and
    an arrival larger than everything drift has ever done can.

    **EVERY RUN'S READING IS EMITTED THROUGH `DIAGNOSTIC_LINES`, AND THAT IS
    WHERE THE HISTORY LIVES** -- in CI logs and commit messages, not in this
    docstring. Logging each reading here turned it into a changelog, and every
    task from 5 to 9 adds a module, so every task would have bought a docstring
    edit plus a hunt through CI logs for three numbers.

    **A CHANGE OF SUBJECT IS NOT DRIFT.** The probe's reading moves when the
    package grows, because the probe walks the package; the re-derivation rule
    below is about a reading moving under a FIXED subject. Re-derive on the
    ruled triggers only: a reading outside the expected shift, or headroom
    shrinking below the spread -- plus one deliberate re-derivation at Task 8,
    when the subject becomes the entry point rather than a package walk.

    **IF A READING LANDS OUTSIDE THE EXPECTED SHIFT, OR HEADROOM DROPS BELOW
    THE SPREAD, RE-DERIVE THE MARGIN FROM THE NEW BAND -- DO NOT BUMP THE
    NUMBER.** A threshold raised to admit a
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
        f"(ceiling {CEILING}, headroom {CEILING - count})"
    )
    assert count < CEILING, (
        f"the report now loads {count} modules against a ceiling of {CEILING}. "
        "Something heavy has entered the graph, most likely through "
        "metamer/core/__init__.py or a family module -- or a new report module "
        "brought a dependency with it, in which case the band is re-measured "
        "for the new subject rather than the number bumped"
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


#: What `StoreView` carries, against where the writer puts it. **The coverage
#: table T7-3 asks for**, and the mechanism that turns the next missing field
#: from a discovery into a decision.
#:
#: **THREE TASKS RUNNING FOUND THE READER SHORT OF ONE FACT.** Task 6 needed the
#: `x` coordinate; Task 7 needed `/status/outcome`'s flag attributes. Both were
#: ARRAY attributes or coordinate arrays, which `StoreView.attrs` -- root attrs
#: only -- structurally cannot carry, and each was found mid-implementation. The
#: repair each time was to widen the reader rather than let a second consumer
#: open the store, because two readers of one store is the defect this sub-phase
#: has refused under three names.
_EXPOSED: dict[str, str] = {
    "status/outcome": "outcome",
    "status/m": "model_labels",
    "selection/delta_ic": "delta_ic",
    "selection/selected": "selected",
    "selection/n_valid": "n_valid",
    "selection/c": "criterion_labels",
    "primitives/iterations": "iterations",
}

#: Arrays the writer creates that the reader deliberately does not expose, each
#: with the reason. **Pinned rather than defaulted**: an array absent from both
#: tables fails the test, so a new one is a decision somebody makes rather than
#: a silence somebody inherits.
_NOT_EXPOSED: dict[str, str] = {
    "status/point_outcome": (
        "the report recomputes the point aggregate from `outcome` under its own "
        "any/all rule (D7); reading the stored one would make the report's "
        "aggregate depend on which rule the WRITER used"
    ),
    "primitives/log_lik": "no 2f section reads a likelihood",
    "primitives/k": "no 2f section reads a parameter count",
    "primitives/n": "no 2f section reads a sample count",
    "primitives/n_eff_trend": "no 2f section reads an effective sample size",
    "primitives/n_eff_bic": "no 2f section reads an effective sample size",
    "selection/weight": "no 2f section reads an Akaike weight",
    "selection/ic_best": "no 2f section reads the winning criterion value",
    "signal/beta": "regression coefficients are not a fit diagnostic",
    "signal/beta_err": "regression coefficient errors are not a fit diagnostic",
    "noise/theta": "parameter values are not a fit diagnostic",
    "noise/theta_err": "parameter errors are not a fit diagnostic",
    "warmstart/theta_unconstrained": (
        "a warm-start cache, not a record of what the run produced"
    ),
}


def test_every_array_the_writer_creates_is_exposed_or_pinned_as_excluded():
    """T7-3: the writer's arrays, enumerated, each decided for.

    **THE SCOPE IS MECHANICAL** -- `store._array_specs` is the writer's own
    declaration of every array it creates, so this test cannot drift from the
    writer by being out of date about it. F3's rule: assert what the enumeration
    found, never a hand-maintained copy of it.

    Bug this catches: the writer gaining an array and nobody deciding whether the
    report should read it. That is not hypothetical -- it happened twice in two
    tasks with array ATTRIBUTES (Task 6's `x`, Task 7's `flag_meanings`), each
    found mid-implementation after the consumer was already being written. An
    array in neither table fails here, naming it, which makes the next one a
    decision at review time instead of a discovery at implementation time.

    **AND IT BITES BOTH WAYS**: a path in `_EXPOSED` that the writer no longer
    creates fails too, so a renamed array cannot leave a stale row behind
    claiming coverage.
    """
    from metamer.batch.store import StoreShape, _array_specs

    specs = _array_specs(
        StoreShape(n_y=4, n_x=4, n_beta=2, tile_side=4),
        n_models=2,
        n_criteria=1,
        p_total=3,
    )
    written = {
        f"{group}/{spec.name}" for group, items in specs.items() for spec in items
    }
    # The axis-label arrays are created by the coordinate path rather than by
    # `_array_specs`, and the report reads both, so they are named here with the
    # reason they are not in the enumeration.
    written |= {"status/m", "selection/c"}

    decided = set(_EXPOSED) | set(_NOT_EXPOSED)
    undecided = written - decided
    assert not undecided, (
        f"the writer creates arrays the reader neither exposes nor excludes: "
        f"{sorted(undecided)}. Add each to _EXPOSED (and to StoreView) or to "
        f"_NOT_EXPOSED with the reason it is not read."
    )
    stale = decided - written
    assert not stale, (
        f"these paths are decided for but the writer does not create them: "
        f"{sorted(stale)}. A renamed or removed array must not leave a row "
        f"behind claiming coverage."
    )

    # Every exposed path names a field that actually exists on the view.
    fields = {field.name for field in dataclasses.fields(StoreView)}
    missing = set(_EXPOSED.values()) - fields
    assert not missing, f"_EXPOSED names fields StoreView does not carry: {missing}"


def test_the_non_array_facts_the_reader_carries_are_pinned_too():
    """T7-3's other half: the fields that come from attributes, not arrays.

    **THIS IS WHERE BOTH MISSES ACTUALLY HAPPENED**, so a coverage table over
    arrays alone would have caught neither. `spatial` comes from coordinate
    arrays named by a ROOT attr; `legend` comes from an ARRAY attr on
    `/status/outcome`; `attrs` is root attrs; `completion` and `disagreements`
    are derived.

    Bug this catches: a `StoreView` field added with no statement of where it
    comes from -- which is how a reader grows a field whose source nobody can
    find, and how the next task's "the reader does not carry it" becomes a
    discovery for the third time.
    """
    sources = {
        "path": "the caller's argument, not read from the store",
        "outcome": "array /status/outcome",
        "delta_ic": "array /selection/delta_ic",
        "selected": "array /selection/selected",
        "n_valid": "array /selection/n_valid",
        "iterations": "array /primitives/iterations",
        "model_labels": "array /status/m",
        "criterion_labels": "array /selection/c",
        "spatial": "coordinate arrays under /status/, named by root attr "
        "spatial_coordinates_written (added 2f Task 6)",
        "legend": "ARRAY attrs flag_values/flag_meanings on /status/outcome "
        "(added 2f Task 7)",
        "attrs": "root attrs",
        "completion": "derived from the completion bitmap",
        "disagreements": "derived; contradictions between two records, reported "
        "and never resolved",
    }
    fields = {field.name for field in dataclasses.fields(StoreView)}

    assert set(sources) == fields, (
        "every StoreView field must name where it comes from; unexplained: "
        f"{sorted(fields - set(sources))}, stale: {sorted(set(sources) - fields)}"
    )
    # The two that cost a task each, asserted by name so the lesson is not
    # carried only by a comment.
    assert "ARRAY attrs" in sources["legend"]
    assert "root attr" in sources["spatial"]


def test_the_legend_comes_from_the_stores_own_flag_attributes(finished_store):
    """T7-3: `/status/outcome`'s own `flag_values`/`flag_meanings`, as a mapping.

    **A REAL STORE, NOT A HAND-BUILT ONE.** The writer builds these two attrs
    from `Outcome` at `store.py:956`, so on a store this build wrote the legend
    must agree with this build's alphabet exactly -- which is what makes the
    disagreement case below meaningful.

    Bug this catches: reading the legend from root attrs, where it does not
    exist, and silently yielding `{}` -- every map titled `code 7` on a store
    that names its codes perfectly well. That is the shape of the Task 6 miss one
    task earlier, and `StoreView.attrs` being root-only is exactly why it is
    reachable.
    """
    view = read_store(finished_store)

    assert view.legend, "a real store names its codes"
    assert view.legend == {member.code: str(member.value) for member in Outcome}
    # The two that every map title depends on, named rather than left to the
    # dict comparison, so a failure says which end moved.
    assert view.legend[Outcome.OK.code] == "ok"
    assert view.legend[Outcome.DEGENERATE_HESSIAN.code] == "degenerate_hessian"


def test_a_flag_pair_that_disagrees_in_length_yields_no_legend(
    finished_store, tmp_path
):
    """A mismatched pair is not half-usable.

    **Hand-derived:** drop one meaning from a 14-member list and `zip` would
    attach `iter_cap_small_grad` to code 0, `iter_cap_large_grad` to code 1, and
    a wrong name to **every** code after the divergence. There is no prefix that
    is safely usable, because the divergence point is not knowable from the two
    lists.

    Bug this catches: `zip(values, names)` without a length check -- which
    silently produces a complete-looking legend in which every title is wrong,
    and `strict=True` would raise instead, turning a describable store into a
    crash. D6 says a store is described, so the answer is no legend.
    """
    import shutil

    store = tmp_path / "mismatched.zarr"
    shutil.copytree(finished_store, store)
    root = zarr.open_group(store, mode="r+")
    values = list(cast("list[int]", root["status/outcome"].attrs["flag_values"]))
    meanings = str(root["status/outcome"].attrs["flag_meanings"]).split()
    assert len(values) == len(meanings), "the fixture must start consistent"
    root["status/outcome"].attrs["flag_meanings"] = " ".join(meanings[:-1])
    # **RE-CONSOLIDATE, OR THE MUTATION DOES NOT REACH THE READER.** This store
    # carries consolidated metadata, and the reader opens the group plainly --
    # so the root's consolidated copy of the array attrs is what it sees, and an
    # edit to the array alone leaves the stale pair in place. Found while writing
    # this test: the first version asserted `{}` and read a full legend back.
    zarr.consolidate_metadata(store)

    view = read_store(store)

    assert view.legend == {}, (
        "a pair that disagrees in length must yield no legend rather than a "
        "silently misaligned one"
    )


def test_a_store_with_no_flag_attributes_yields_no_legend(finished_store, tmp_path):
    """Absent is the answer, not an error -- `_spatial`'s precedent.

    Bug this catches: a `KeyError` on a store written by a build that did not
    write flag attributes, which would make the whole report unavailable for a
    missing title rather than titling by code number.
    """
    import shutil

    store = tmp_path / "unlabelled.zarr"
    shutil.copytree(finished_store, store)
    root = zarr.open_group(store, mode="r+")
    for name in ("flag_values", "flag_meanings"):
        del root["status/outcome"].attrs[name]
    zarr.consolidate_metadata(store)

    view = read_store(store)

    assert view.legend == {}
    # And the rest of the view is unaffected: a missing legend is not a missing
    # store.
    assert view.outcome.size > 0
    assert view.model_labels
