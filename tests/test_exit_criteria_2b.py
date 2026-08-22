"""Phase 2b's sixteen exit criteria: the closing evidence, and the record binding.

**THIS MODULE IS DELIBERATELY SMALL, AND THAT IS THE FINDING RATHER THAN A
SHORTFALL.** All sixteen criteria already have coverage in the module their own
task landed, so the default outcome of a closing suite is a **roll-up** -- a
criterion re-checked by calling the helper the implementing task's test called
shares its whole derivation with the subject (pre-flight (j)), and 2b is more
exposed to that than 2a was, because six of its criteria are about a *number*
and a number re-read from the constant that published it agrees with itself.

**SO THE AUDIT PARTITIONED THEM FIRST AND ONLY THE GAPS ARE HERE.** Criteria 1,
2 and 3 have **no outside at all** -- they are claims about code shape, and a
subprocess wrapped around the same call is that call in a second interpreter.
Criteria 10, 12, 13 and 14 are already driven from a genuine outside by their
own tasks' tests. Criterion 16 was met at Task 9 by five tests that recompute
it. What was left is three gaps and one binding:

  - **criterion 5** never reached a *user*: the refusal was asserted as an
    exception type in-process, and the exit code and stderr are what a resuming
    script branches on. Two tests, and the second is (i2)'s positive control on
    the message's own promise.
  - **criterion 9** was asserted analytically, never against chunk shapes read
    back off a store zarr actually wrote.
  - **the verdict record** had no binding at all, which is how criterion 6 read
    *"MET as written"* through three tasks after the measurement under it was
    withdrawn.

The closing table with its reasoning is in `PROGRESS.md` and in the plan;
`tests/exit_criteria_2b.py` holds the part a test can check.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import xarray as xr
import zarr

from metamer.batch.store import CHUNK_TARGET_BYTES, TILE_SIDE_BASE
from metamer.batch.tiling import PUBLISHED_TILE_SIDE
from metamer.batch.validation import ExitCode
from metamer.core.memory import SLOPE_BAND_FACTOR
from tests.conftest import STUB_FLOOR_PEAK
from tests.exit_criteria_2b import (
    PHASE_2B_EXIT_CRITERIA,
    READINGS,
    ExitCriterion,
    Verdict,
)

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")

#: A budget of 100 bytes, which cannot clear the session's 1 MB stub floor.
#: **Below the floor rather than merely small**, because the two refusals are
#: different arms: `tiling.py:212` fires when the budget does not clear floor
#: plus headroom, and `tiling.py:329` fires when it does and the remaining block
#: will not hold one series at the base. This criterion is the first.
BUDGET_BELOW_THE_FLOOR = 0.0000001

#: The tile side criterion 9's store is built at, and it is production-scale on
#: purpose. `CHUNK_TARGET_BYTES` is 4 MB and a shard is one tile, so at any side
#: a *fitted* fixture could afford no array reaches the target and the band is
#: asserted over an empty set. At 336 with this candidate set the widest array's
#: shard is tens of megabytes and the divisor logic is exercised. **336 is
#: 2**4 x 3 x 7**, which is why Task 0 recorded it as the smooth alternative to
#: the prime 347.
SIDE = 336


def _input(tmp_path: Path, *, n_time: int = 12, side: int = 4) -> str:
    """A small real store with non-constant data.

    **Zeros would make this vacuous**: zarr does not write a chunk equal to the
    fill value, so a zero-filled store serves every read from the fill and the
    chunks this module measures would not exist.

    Args:
        tmp_path: Where to write it.
        n_time: Series length.
        side: Grid side, both axes. **Four, because the positive control below
            RUNS the budget the refusal offers**, and a 16x16 grid is 256
            uncapped series -- the fixture has to be small enough that the
            control is affordable, or the control is what gets deleted.

    Returns:
        The store path as a URI string.
    """
    values = np.random.default_rng(0).standard_normal((n_time, side, side))
    dataset = xr.Dataset(
        {"sla": (("time", "y", "x"), values.astype("float32"))},
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
    path = tmp_path / "in.zarr"
    dataset.to_zarr(path, encoding={"sla": {"chunks": (n_time, 2, 2)}})
    return str(path)


def _config(tmp_path: Path, uri: str, *, budget: float, name: str = "c.toml") -> Path:
    """Write a config naming an explicit budget.

    Args:
        tmp_path: Where to write it.
        uri: The input store.
        budget: `memory_budget_gb`.
        name: File name, so two configs can coexist.

    Returns:
        The config path.
    """
    path = tmp_path / name
    path.write_text(
        f'data_uri = "{uri}"\n'
        'variable = "sla"\n'
        'signal_terms = ["constant", "trend", "annual"]\n'
        'candidates = ["white", "white + matern12"]\n'
        'criteria = ["aic"]\n'
        'objective = "reml"\n'
        "threads = 1\n"
        f"memory_budget_gb = {budget!r}\n"
    )
    return path


def _cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    """Run `python -m metamer` in a fresh process.

    **The exit code and stderr ARE the interface for criterion 5.** Calling
    `run()` and catching `ValidationError` checks the exception; a user gets
    neither the exception nor its type, and a resuming script branches on the
    code.

    Args:
        *arguments: Command-line arguments after `-m metamer`.

    Returns:
        The completed process.
    """
    import os

    environment = dict(os.environ)
    # The session's floor stub is a fixture and does not reach a subprocess; the
    # env override is how `run.py` lets one in, and it is the same 1 MB.
    environment["METAMER_FLOOR_BYTES"] = str(STUB_FLOOR_PEAK)
    # S603: this interpreter, this package, arguments built above from tmp_path.
    return subprocess.run(  # noqa: S603
        [sys.executable, "-m", "metamer", *arguments],
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )


# --------------------------------------------------------------------------
# Criterion 5 -- the refusal, from where a user stands
# --------------------------------------------------------------------------


def test_criterion_5_the_refusal_reaches_a_user_as_exit_code_three(tmp_path):
    """A budget below the floor exits 3 and says all four things on stderr.

    **The in-module test asserts a `ValidationError` with `layer is SEMANTIC`.
    A user sees neither.** What crosses the process boundary is an integer and
    some text, and the criterion is about what the refusal *tells* someone --
    so it is checked where they stand.

    Expected values determined independently of the implementation: the
    criterion names four things the message must carry -- that the budget is
    refused, the floor, the floor's components, and a budget that would work --
    and `ExitCode.CONFIG_INVALID` is 3 in the taxonomy. The floor here is the
    session stub, 1 MB, supplied to the subprocess through `METAMER_FLOOR_BYTES`
    because a fixture does not cross a fork.

    Bug this catches: `BudgetTooSmallError` escaping as a bare `ValueError`,
    which CPython reports as **exit code 1** -- and 1 means "completed with
    failures above threshold" here, i.e. **the opposite fact about the run**, so
    a caller that resumes on 1 resumes from a crash. The in-module test cannot
    see that, because it never leaves the process where the exception exists.
    And a message that names the floor while dropping the workable budget, which
    leaves the user refused with nothing to try.
    """
    config = _config(tmp_path, _input(tmp_path), budget=BUDGET_BELOW_THE_FLOOR)
    result = _cli(str(config), str(tmp_path / "out.zarr"))

    assert result.returncode == ExitCode.CONFIG_INVALID, result.stderr
    assert int(ExitCode.CONFIG_INVALID) == 3, (
        "the taxonomy moved: 3 is what a resuming script branches on"
    )
    message = result.stderr
    assert "leaves nothing for a tile" in message
    assert "1.0 MB" in message, "the floor itself"
    assert "rung by rung" in message, "the floor's components"
    assert "leaves a positive block" in message, "a budget that would work"
    assert not (tmp_path / "out.zarr").exists(), (
        "a refused run must not leave a store behind: a half-created store with "
        "the right attrs and no data is what the fill-value rule (a0) is about"
    )


def test_criterion_5_the_workable_budget_the_refusal_names_actually_works(tmp_path):
    """(i2): the message promises a budget that works, so run that budget.

    **A refusal that names a remedy is making a claim, and nothing checked it.**
    The message says *"a budget above X GB leaves a positive block"*; X is
    computed in the same function that raises, from the same floor, and if the
    arithmetic were off by the headroom the message would be confidently wrong
    and every assertion about its *text* would still pass. This is the positive
    control for the negative above -- the half that can fail.

    Expected behaviour determined independently: the promise is only that the
    block is positive, not that the run is sensible, so what is asserted is that
    the same command **stops being refused** -- not that it produces a good tile.

    Bug this catches: the workable figure computed against the floor alone while
    the refusal tests floor plus headroom, so the number the message offers is
    itself refused. The user then follows the instruction and is refused again,
    which is worse than an unhelpful message because it reads as a bug in their
    input.
    """
    uri = _input(tmp_path)
    config = _config(tmp_path, uri, budget=BUDGET_BELOW_THE_FLOOR)
    refused = _cli(str(config), str(tmp_path / "out.zarr"))
    assert refused.returncode == ExitCode.CONFIG_INVALID

    offered = [
        word
        for word in refused.stderr.replace("(", " ").replace(")", " ").split()
        if word.replace(".", "", 1).replace("e-", "", 1).isdigit()
    ]
    quoted = refused.stderr.split("A budget above ", 1)[1].split(" GB", 1)[0]
    workable = float(quoted)
    assert workable > 0, (offered, refused.stderr)

    # Strictly above, because the message says "above". A hair over is what
    # tests the boundary the arithmetic claims rather than a comfortable margin.
    retry = _config(tmp_path, uri, budget=workable * 1.000001, name="retry.toml")
    second = _cli(str(retry), str(tmp_path / "second.zarr"))
    assert second.returncode != ExitCode.CONFIG_INVALID, (
        f"the budget the refusal offered was itself refused: {second.stderr[-400:]}"
    )


# --------------------------------------------------------------------------
# Criterion 9 -- the chunk band, against a store on disk
# --------------------------------------------------------------------------


def test_criterion_9_the_worst_array_on_disk_is_inside_the_band(tmp_path):
    """The chunking a store actually declares, measured, worst array first.

    **The in-module test computes the achieved bytes from `_chunk_side` and the
    declared dtype widths.** That is the arithmetic checking itself: if the
    store's writer and the sizing helper disagreed -- a dtype changed in one and
    not the other, a shard shape rounded differently -- the analytic test would
    still pass. Here the shapes come out of `zarr.open_group` on a store
    `create_store` wrote.

    **AND THE FIXTURE IS AT A PRODUCTION-SCALE TILE SIDE BECAUSE NOTHING ELSE
    CAN EXPRESS THE PROPERTY.** The first version of this test drove a real run
    on a 16x16 grid and asserted the band; **no array reached the chunk target
    at all**, so the assertion was over an empty set and would have passed the
    moment the guard came out. `CHUNK_TARGET_BYTES` is 4 MB and a shard is one
    tile, so a store has to be sized like a real one -- which costs nothing
    here, because `create_store` writes pure metadata and zarr writes no chunk
    equal to the fill value.

    Expected values determined independently of the implementation: an array's
    achieved chunk bytes are `prod(chunk shape) * itemsize`, read off disk, and
    the band is `CHUNK_TARGET_BYTES` to twice it. **The population is
    partitioned rather than the band widened**: an array whose whole shard
    cannot reach the target -- `point_outcome` is one byte per cell -- has one
    chunk per shard as the *right* answer, and holding the band over those would
    destroy the check for the arrays it exists for.

    Bug this catches: a store whose worst array lands a chunk far outside the
    band while every typical array is fine -- measured at Task 2, one dtype
    apart doubles the ratio, 2.3x on `noise/theta` against 4.57x on
    `warmstart/theta_unconstrained` at the same `P_total`. **A band checked on a
    representative array describes a case nobody operates at.** And the
    exemption swallowing a wide array: it is keyed on the shard being unable to
    reach the target, so both groups are asserted non-empty.
    """
    from metamer.batch import geometry
    from metamer.batch import store as store_module
    from metamer.batch.input import open_input
    from metamer.config import load

    uri = _input(tmp_path, side=8)
    config_path = tmp_path / "wide.toml"
    config_path.write_text(
        f'data_uri = "{uri}"\n'
        'variable = "sla"\n'
        'signal_terms = ["constant", "trend", "annual"]\n'
        'candidates = ["white", "matern12", "matern32", "white + white", '
        '"white + matern12", "white + matern32"]\n'
        'criteria = ["aic", "bic"]\n'
        'objective = "reml"\n'
        "threads = 1\n"
        "memory_budget_gb = 1.0\n"
    )
    config = load(config_path)
    attrs = store_module.provenance_attrs(
        config,
        geometry_components=geometry.geometry_components(open_input(uri, "sla")),
        thread_limits={"openblas": 1, "openmp": 1, "numba": 1},
        read_amplification=1.0,
        unique_dt_count=2,
        tile_sides={"shared": SIDE, "per_point": SIDE // 2},
        tile_side_basis=store_module.TileSideBasis.DEFAULT,
        memory_budget_requested_gb=1.0,
        max_iter=200,
        floor=PUBLISHED_TILE_SIDE.floor,
    )
    path = tmp_path / "wide.zarr"
    store_module.create_store(
        path,
        specs=config.process_specs(),
        criteria=config.criteria,
        shape=store_module.StoreShape(n_y=SIDE, n_x=SIDE, n_beta=4, tile_side=SIDE),
        attrs=attrs,
    )

    group = zarr.open_group(str(path), mode="r")
    in_band: list[tuple[str, int]] = []
    exempt: list[tuple[str, int]] = []
    for name, array in _arrays(group):
        chunk = int(np.prod(array.chunks)) * array.dtype.itemsize
        shard = int(np.prod(array.shards or array.chunks)) * array.dtype.itemsize
        (exempt if shard < CHUNK_TARGET_BYTES else in_band).append((name, chunk))

    assert in_band, "no array reached the chunk target, so the band is untested"
    assert exempt, (
        "no array was exempt, so the partition is untested -- and it exists "
        "because several arrays cannot reach the target at all"
    )
    worst = max(in_band, key=lambda pair: pair[1])
    assert CHUNK_TARGET_BYTES <= worst[1] <= 2 * CHUNK_TARGET_BYTES, (worst, in_band)
    for name, chunk in exempt:
        assert chunk <= 2 * CHUNK_TARGET_BYTES, (name, chunk)
    assert SIDE % TILE_SIDE_BASE == 0, SIDE


def _arrays(group: zarr.Group, prefix: str = "") -> list[tuple[str, Any]]:
    """Every array in a group, recursively, with its path.

    Args:
        group: The store root or a subgroup.
        prefix: Path accumulated so far.

    Returns:
        `(path, array)` pairs.
    """
    found: list[tuple[str, Any]] = []
    for name, member in group.members():
        path = f"{prefix}{name}"
        if isinstance(member, zarr.Group):
            found.extend(_arrays(member, f"{path}/"))
        else:
            found.append((path, member))
    return found


# --------------------------------------------------------------------------
# The verdict record, bound to the tree
# --------------------------------------------------------------------------


def _collected_test_names() -> set[str]:
    """Every `test_*` function defined anywhere under `tests/`.

    **A STATIC SCAN AND NOT THE SESSION'S ITEM LIST**, deliberately: the claim
    is that the evidence EXISTS, not that this invocation selected it, and
    `pytest -k` would otherwise make the binding fail for a reason unrelated to
    its subject -- (i9) at a test's own fixture.

    Returns:
        The function names.
    """
    names: set[str] = set()
    for module in Path(__file__).parent.glob("test_*.py"):
        for node in ast.walk(ast.parse(module.read_text())):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                names.add(node.name)
    return names


def test_the_record_covers_every_criterion_exactly_once():
    """Sixteen criteria, numbered 1 to 16, no gaps and no repeats.

    Expected value determined independently: the plan's table has sixteen rows
    numbered 1 through 16.

    Bug this catches: a criterion dropped from the record while the plan still
    lists it -- the record then reports a complete sub-phase with a row missing,
    which is (a0)'s shape at a table rather than at a fill value. **Compared as
    a set rather than by counting**, because a count cannot tell a duplicate
    from an omission and the two are different defects.
    """
    numbers = [criterion.number for criterion in PHASE_2B_EXIT_CRITERIA]
    assert sorted(numbers) == list(range(1, 17))
    assert len(set(numbers)) == len(numbers)


def test_every_criterion_names_evidence_that_exists():
    """A verdict standing on a test that was renamed or deleted fails here.

    **This is the binding the closing table never had.** Criterion 6 read "MET
    as written" through Tasks 8, 9 and 8a while the measurement under it was
    being withdrawn, because a sentence in a document is attached to nothing.

    Expected values determined independently: every name in `established_by` is
    a `def test_...` somewhere under `tests/`, found by parsing the files rather
    than by importing them.

    Bug this catches: a test renamed during a refactor, leaving a verdict whose
    stated evidence does not exist -- which reads exactly like a verdict whose
    evidence does. And a criterion added to the record with an aspirational test
    name that was never written.
    """
    have = _collected_test_names()
    missing = {
        (criterion.number, name)
        for criterion in PHASE_2B_EXIT_CRITERIA
        for name in criterion.established_by
        if name not in have
    }
    assert not missing, missing
    for criterion in PHASE_2B_EXIT_CRITERIA:
        assert criterion.established_by, criterion.number


def test_every_verdict_states_a_reading_or_states_that_it_has_none():
    """A criterion over a measured quantity must name which reading.

    **One run yields several readings and criteria 6 and 7 were written as
    though it yielded one.** Re-measured 2026-08-22 at Task 8b's own fixture:
    931.7, 1470.9 and 1468.8 B/series on a single ladder, and criterion 6 is met
    on the first and failed on the other two. (~~970.6, 1504.1 and 2410.0~~ --
    the peak was superseded when `SVD_CHUNK_SERIES` bounded the fit phase's
    maximum; the other two reproduce.)

    Expected values determined independently: the readings a harness here can
    take are the three in `READINGS`, and the criteria whose subject is an RSS
    measurement are **4, 6, 7 and 8** -- listed here by hand from the plan's
    table rather than read off the record, so that a criterion quietly losing
    its reading fails instead of redefining the expectation.

    Bug this catches: a verdict quoting a reading no instrument produces, and a
    memory criterion added with no reading at all -- which is the ambiguity that
    let 6 and 7 read as settled through four tasks.
    """
    about_a_measurement = {4, 6, 7, 8}
    for criterion in PHASE_2B_EXIT_CRITERIA:
        if criterion.number in about_a_measurement:
            assert criterion.reading in READINGS, criterion.number
        else:
            assert criterion.reading is None, criterion.number


def test_every_non_met_verdict_states_its_scope():
    """A reduced scope or a failure without its regime is a shrug.

    Expected behaviour determined independently: `MET` may carry an empty scope,
    because "it holds" needs no qualification; the other two may not, because
    what a reader needs from them is exactly the qualification.

    Bug this catches: a criterion downgraded to FAILED during a review with no
    statement of where it fails, which is indistinguishable downstream from a
    criterion that fails everywhere -- and 2b's criterion 7 passes at small
    tiles and fails at production ones, so "failed" alone would be wrong in both
    directions.
    """
    for criterion in PHASE_2B_EXIT_CRITERIA:
        if criterion.verdict is not Verdict.MET:
            assert criterion.scope.strip(), criterion.number
        assert criterion.outside.strip(), criterion.number


def test_criterion_6_and_7_move_with_the_published_record():
    """The two failing verdicts and the published caveat cannot drift apart.

    **THIS IS THE ONE THAT MATTERS AND IT IS THE ONE THAT DID NOT EXIST.** The
    published tile side carries a caveat saying the per-series cost is unsettled;
    criteria 6 and 7 are failed for that same reason. **Nothing connected them**,
    so the caveat could be deleted by a task that settled the number without
    anyone revisiting the criteria -- or the criteria marked met while the
    caveat stood.

    Expected values determined independently, from the 2026-08-22 ladder: the
    peak is **1468.8 B/series** against an analytic **926**, so the ratio is
    **1.586** and `slope_band(926)` at `SLOPE_BAND_FACTOR = 1.5` is **617.3 to
    1389.0** -- 1468.8 is outside it by **79.8 B/series, 4.3 sigma on its own
    18.4**, which is what makes criterion 6's verdict FAILED on the peak
    reading. Both criteria name the peak.

    ~~2410.0, ratio 2.603, outside by 22 sigma~~ -- superseded 2026-08-22, and
    **the verdict did not move because the margin narrowed**: it is the same
    verdict on a smaller margin, which is the improvement `SVD_CHUNK_SERIES`
    earned and it should be legible here rather than hidden behind an unchanged
    word. **A margin of 4.3 sigma is close enough that the next bounding could
    flip this criterion**, and that is the state, not a warning.

    Bug this catches: the dispute field deleted in a commit that settles the
    per-series cost, leaving criteria 6 and 7 marked failed for a reason that no
    longer exists -- (a6), a description whose subject is gone. And the inverse:
    a verdict flipped to met while the record still says the number is not
    settled.
    """
    six = _criterion(6)
    seven = _criterion(7)
    assert six.verdict is Verdict.FAILED
    assert seven.verdict is Verdict.FAILED
    assert six.reading == seven.reading == "peak"

    dispute = PUBLISHED_TILE_SIDE.dispute
    assert dispute is not None, (
        "the per-series cost is settled, so criteria 6 and 7 must be re-judged "
        "in the same commit that settles it -- failing here rather than passing "
        "vacuously is the point"
    )
    measured = dispute.measured_bytes_per_series
    analytic = dispute.analytic_bytes_per_series
    assert round(measured / analytic, 3) == 1.586
    low, high = analytic / SLOPE_BAND_FACTOR, analytic * SLOPE_BAND_FACTOR
    assert round(low, 1) == 617.3
    assert round(high, 1) == 1389.0
    assert not low <= measured <= high, (
        "the measured peak is inside the band, so criterion 6 is no longer "
        "failed on this reading and its verdict has to change with it"
    )


def _criterion(number: int) -> ExitCriterion:
    """The record for one criterion.

    Args:
        number: Its number in the plan's table.

    Returns:
        The criterion.

    Raises:
        KeyError: If the record has no such number, which
            `test_the_record_covers_every_criterion_exactly_once` would already
            have caught.
    """
    for criterion in PHASE_2B_EXIT_CRITERIA:
        if criterion.number == number:
            return criterion
    raise KeyError(number)
