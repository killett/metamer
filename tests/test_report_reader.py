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


def test_the_report_module_graph_stays_under_its_ceiling():
    """A SIZE assertion, because a denylist cannot see a fifth arrival.

    Expected value determined independently: measured at 708 modules for
    `metamer.core.outcomes` on 2026-09-20, and `metamer.report` sits just above
    it. The ceiling is set at 900 -- comfortably above the measurement, well
    below `metamer.batch.run`'s 1002 -- so ordinary growth does not trip it and
    a heavy dependency does.

    Bug this catches: the failure the four named modules structurally cannot.
    `metamer/core/__init__.py`'s registration side effect is load-bearing and
    is staying, which makes this graph hostage to the spine: anyone adding a
    heavy dependency to `core/__init__.py` or to `families/` lands it in the
    report silently, and a list of four names will not notice a fifth arriving.

    **Handoff (c7) reaching a new place**: assert the SIZE of what a discovery
    mechanism found, not only the values it found. An unasserted enumeration is
    a silent denominator.
    """
    source = (
        "import json, sys; import metamer.report; print(json.dumps(len(sys.modules)))"
    )
    result = subprocess.run(
        [sys.executable, "-c", source],
        capture_output=True,
        text=True,
        env={"PYTHONPATH": "src", "PATH": "/usr/bin:/bin"},
        check=False,
    )
    assert result.returncode == 0, result.stderr
    count = int(json.loads(result.stdout))
    assert count < 900, (
        f"metamer.report now loads {count} modules against a ceiling of 900, "
        "measured at 708 on 2026-09-20. Something heavy has entered the graph, "
        "most likely through metamer/core/__init__.py or a family module"
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
