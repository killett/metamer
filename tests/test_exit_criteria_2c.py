"""Phase 2c's exit criteria: the record bound to the tree, and the outsides.

**THE SUITE IS AN INDEPENDENT CHECK, NOT A ROLL-UP.** A criterion satisfied by
calling the same helper the implementing task's test called verifies nothing
new -- it re-runs one derivation and reports agreement with itself. Five of the
twelve were in that state after Task 7, and the five tests here drive them from
**bytes on disk or a process exit code**, neither of which shares a call path
with the thing under test.

**THREE CRITERIA HAVE NO OUTSIDE AND THE RECORD SAYS WHICH KIND.** The audit
has no command line, so 9, 10 and 11's (j7) half are library-only until Phase
5's `--explain`. That is `NO_CLI_YET` -- a case that CLOSES -- and it is
deliberately a different constant from 2b's `NO_OUTSIDE`, which covers a claim
about code shape that no subprocess could ever strengthen.

**AND THE SOURCE INDEX IS NOT ON DISK, WHICH NARROWS TWO OUTSIDES RATHER THAN
REMOVING THEM.** Task 5 refused to store it -- 160 MB at 10^7 points with two
candidates, against the invariant that peak RAM is derivable from the budget
alone -- so criteria 4 and 5 cannot read the map back element by element. What
IS on disk is the map's per-point CONSEQUENCE (`/warmstart/theta_unconstrained`)
and the run's own radius histogram, and the substitute instrument Task 5 named
is exact: a point is coarse iff `y % k == 0 and x % k == 0`, which is arithmetic
on the stride, and it sources itself exactly when pass 1's `/status/outcome` is
OK there.

**THE CONSTANTS AND THE INPUT BUILDERS ARE IMPORTED FROM `tests/test_twopass.py`
RATHER THAN RE-DERIVED.** `_SIDE_6_BUDGET` and `_SIDE_10_BUDGET` carry a
derivation and an assertion that the two sides differ; a second pair computed
here would be a second derivation of the same fact, and `tile_side_for` is on
the path under test.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import xarray as xr
import zarr

from metamer.batch.decimate import pass1_store_path
from metamer.batch.twopass import run_two_pass
from metamer.config import load
from tests.exit_criteria_2b import PHASE_2B_EXIT_CRITERIA, Verdict
from tests.exit_criteria_2c import PHASE_2C_EXIT_CRITERIA, READINGS
from tests.test_twopass import (
    _SIDE_6_BUDGET,
    _SIDE_10_BUDGET,
    _config,
    _input,
    _invoke,
)

pytestmark = pytest.mark.slow


def _attrs(store: Path) -> dict[str, Any]:
    """A store's root attrs, off disk."""
    return dict(zarr.open_group(str(store), mode="r").attrs)


def _array(store: Path, group: str, name: str) -> np.ndarray:
    """One array out of a written store, as a numpy array."""
    root = zarr.open_group(str(store), mode="r")
    array = root[f"{group}/{name}"]
    assert isinstance(array, zarr.Array)
    return np.asarray(array[:])


# --------------------------------------------------------------------------
# Criterion 1 -- an unwarmed cell, read off disk against a cold run
# --------------------------------------------------------------------------


def test_criterion_1_an_unwarmed_cell_matches_a_cold_run_on_disk():
    """A run where the spiral finds nothing writes exactly what a cold run does.

    Behaviour under test: criterion 1's second clause -- *"a false cell is
    bit-identical to the same cell fit with `x0=None`"* -- **driven from
    outside**. `tests/test_fit.py` asserts it by calling `fit` twice, which is
    the same derivation twice; this compares two stores' bytes and never calls
    `fit` at all.

    **THE FIXTURE MAKES EVERY CELL EXHAUSTED, WHICH IS WHAT MAKES THE
    COMPARISON LOCATION-FREE.** The store does not record which cells were
    warm-started (Task 5 refused to carry the source index), so a mixed run
    would leave the test unable to name the cells it is supposed to compare.
    With every coarse point on land, `coarse_ok` is all-false, every spiral
    exhausts, and the whole store must equal the cold one.

    Expected values determined independently: the cold run is a plain `run` of
    the same input at the same budget, and the comparison is
    `np.testing.assert_array_equal` on the raw arrays -- NaN-aware, and equality
    rather than a tolerance because the claim is bit-identity.

    Bug this catches: `fit` consulting `x0` where `x0_valid` is false --
    `fit.py:227`'s old call-level all-or-nothing, which is the defect Task 0
    exists to have removed. It would show up here as a store that differs from
    the cold one **while every report field still says nothing was
    warm-started**, because the counts come from the source map and not from
    `fit`.

    **AND THE POSITIVE CONTROL IS THE SECOND HALF**, (i2): a run whose coarse
    set IS usable must NOT be bit-identical to the cold one, or this assertion
    would pass against a mechanism that never warm-starts anything.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as raw:
        tmp_path = Path(raw)
        # Land over every coarse point of a stride-2 lattice: rows and columns
        # 0, 2, 4, ... are all-NaN, so no coarse fit is usable anywhere.
        uri = _input(tmp_path, name="land.zarr", n_y=7, n_x=6)
        dataset = xr.open_zarr(uri).load()
        values = np.asarray(dataset["sla"].values)
        values[:, ::2, :] = np.nan
        dataset["sla"] = (("time", "y", "x"), values)
        blank = tmp_path / "blank.zarr"
        dataset.to_zarr(blank)

        config = _config(tmp_path, str(blank))
        warm = run_two_pass(config, tmp_path / "warm.zarr")
        assert warm.pass2 is not None and warm.pass2.warm_start is not None
        assert warm.pass2.warm_start.warm_started == 0, (
            "every cell must exhaust, or the comparison below is over an "
            "unknown subset of the grid"
        )
        assert warm.pass2.warm_start.exhausted > 0

        from metamer.batch.run import run

        cold = run(config, tmp_path / "cold.zarr")
        assert cold.tiles_written == warm.pass2.tiles_written

        for group, name in (
            ("noise", "theta"),
            ("primitives", "iterations"),
            ("primitives", "log_lik"),
            ("status", "outcome"),
        ):
            np.testing.assert_array_equal(
                _array(warm.store_path, group, name),
                _array(tmp_path / "cold.zarr", group, name),
                err_msg=f"{group}/{name} differs although no cell was warm-started",
            )

        # The positive control: a usable coarse set DOES move the output, so
        # the equality above is a fact about x0_valid and not about a mechanism
        # that never fires.
        live = _config(tmp_path, _input(tmp_path, name="live.zarr"), name="live.toml")
        moved = run_two_pass(live, tmp_path / "moved.zarr")
        assert moved.pass2 is not None and moved.pass2.warm_start is not None
        assert moved.pass2.warm_start.warm_started > 0
        cold_live = run(live, tmp_path / "coldlive.zarr")
        assert not np.array_equal(
            _array(moved.store_path, "primitives", "iterations"),
            _array(cold_live.store_path, "primitives", "iterations"),
        ), "warm-starting must change SOMETHING, or the test above is vacuous"


# --------------------------------------------------------------------------
# Criterion 2 -- the stored hash, off three stores
# --------------------------------------------------------------------------


def test_criterion_2_the_stride_moves_the_stored_hash_and_the_audit_does_not(tmp_path):
    """`fit_hash` read off written stores, which is what a resume compares.

    Behaviour under test: criterion 2 **as a resume would see it**.
    `tests/test_config.py` asserts the same thing by calling `Config`'s own
    hashing helpers -- the functions under test. This writes three stores and
    reads the attr each one stamped.

    Expected values determined independently: the base and the audit-changed
    config differ in `[audit]` alone; the base and the stride-changed config
    differ in `warm_start.coarse_stride` alone. **One field moves per
    comparison**, or the hash would move for a reason the criterion is not
    about.

    Bug this catches: the audit block reaching the flattening that builds
    `fit_hash`. Read loosely, the argument that puts warm-start settings into
    fit identity sweeps the audit settings in with them -- and then re-running
    an audit at a different subsample size invalidates the store it audits,
    which is the exact failure the separate block exists to prevent. **It would
    be invisible until someone re-audited a finished 10^7-point store.**
    """
    uri = _input(tmp_path)
    base = _config(tmp_path, uri, name="base.toml")
    strided = _config(tmp_path, uri, name="strided.toml")
    strided.write_text(
        strided.read_text().replace("coarse_stride = 2", "coarse_stride = 3")
    )
    audited = _config(tmp_path, uri, name="audited.toml")
    audited.write_text(
        audited.read_text() + "\n[audit]\nsubsample = 500\nstratify = true\nseed = 9\n"
    )

    from metamer.batch.run import run

    hashes = {}
    for label, config in (("base", base), ("strided", strided), ("audited", audited)):
        report = run(config, tmp_path / f"{label}.zarr")
        hashes[label] = _attrs(report.store_path)["fit_hash"]

    assert hashes["strided"] != hashes["base"], (
        "the coarse stride is fit identity: a store fitted at one stride must "
        "not resume a store fitted at another"
    )
    assert hashes["audited"] == hashes["base"], (
        "the audit settings measure a store, they do not compute it; a "
        "different subsample must leave the store it audits resumable"
    )
    # And the audited run really did carry different settings, or the equality
    # above is a statement about two identical configs.
    assert load(audited).audit.subsample == 500
    assert load(base).audit.subsample != 500


# --------------------------------------------------------------------------
# Criteria 4 and 5 -- the source map's consequence and its lattice, on disk
# --------------------------------------------------------------------------


def test_criterion_4_the_recorded_source_index_is_identical_at_two_tile_sides(tmp_path):
    """Two tile sides, one warm start per point, compared byte for byte.

    Behaviour under test: §11.3's tile-independence **reaching `theta_hat`**.
    `tests/test_warmstart.py` asserts the map itself is region-independent by
    calling `source_map` twice; this runs the whole pipeline at two memory
    budgets and compares what each wrote.

    **THE MAP ITSELF IS NOT ON DISK AND THAT NARROWS THE READING RATHER THAN
    WEAKENING IT.** Task 5 refused to store the source index -- 160 MB at
    production scale, against the invariant that peak RAM comes from the budget
    alone -- so what is compared is the map's per-point consequence: every
    point's warm start, hence every point's optimum. A map that differed at one
    point would have to produce a bit-identical optimum there to survive this.

    Expected values determined independently: `_SIDE_6_BUDGET` and
    `_SIDE_10_BUDGET` are imported from `tests/test_twopass.py`, where they are
    derived and where both halves of the precondition are asserted; recomputing
    them here would put `tile_side_for` -- which is on the path under test -- on
    both sides of the comparison.

    Bug this catches: a source map built from tile-local indices rather than
    from the full grid with a region. The tiling comes from `--memory-budget`,
    so the defect would put **the memory budget inside `theta_hat`** -- two
    machines with different RAM producing different science, silently.
    """
    uri = _input(tmp_path, n_y=11, n_x=7)
    config = _config(tmp_path, uri)
    six = run_two_pass(config, tmp_path / "six.zarr", memory_budget_gb=_SIDE_6_BUDGET)
    ten = run_two_pass(config, tmp_path / "ten.zarr", memory_budget_gb=_SIDE_10_BUDGET)

    assert six.pass2 is not None and ten.pass2 is not None
    assert six.pass2.tile_side != ten.pass2.tile_side, (
        "equal tile sides would make this a comparison of two identical traversals"
    )
    assert six.pass2.tiles_total > 1 and ten.pass2.tiles_total > 1

    np.testing.assert_array_equal(
        _array(six.store_path, "warmstart", "theta_unconstrained"),
        _array(ten.store_path, "warmstart", "theta_unconstrained"),
    )
    assert six.pass2.warm_start is not None and ten.pass2.warm_start is not None
    assert (
        six.pass2.warm_start.radius_histogram == ten.pass2.warm_start.radius_histogram
    )
    assert six.pass2.warm_start.warm_started > 0


def test_criterion_5_a_coarse_points_recorded_source_on_disk_is_itself(tmp_path):
    """Radius 0 is exactly the OK coarse cells, counted from two stores.

    Behaviour under test: criterion 5, driven from the instrument Task 5 named
    when it refused to store the source index. *"Self-sourced"* does not have to
    be read back: a point is coarse iff `y % k == 0 and x % k == 0`, which is
    arithmetic on the stride, and it sources itself exactly when pass 1's own
    fit there is `OK` -- which is `/status/outcome` in pass 1's store.

    Expected value determined independently: the count is built from pass 1's
    outcome array and the stride, with no reference to the source map. The run
    report's `radius_histogram[0]` is what it is compared against, and D12 says
    radius 0 means a coarse point sourcing itself.

    Bug this catches: a spiral that skips radius 0 and sends coarse points to a
    neighbour. It would make the coarse points **the worst-sourced in the
    field** -- their source `k` cells away against a fine-point mean radius of
    2.556 -- which is the repair D12 rejected as one that relocates the artifact
    rather than removing it. Nothing in the output would look wrong; the lattice
    signal would simply invert.
    """
    from metamer.core.outcomes import Outcome

    uri = _input(tmp_path, n_y=9, n_x=8)
    config = _config(tmp_path, uri)
    report = run_two_pass(config, tmp_path / "out.zarr")
    assert report.pass1_path is not None and report.pass2 is not None
    assert report.pass2.warm_start is not None

    stride = load(config).warm_start.coarse_stride
    coarse_outcome = _array(Path(report.pass1_path), "status", "outcome")
    expected = int(np.count_nonzero(coarse_outcome == Outcome.OK.code))

    histogram = report.pass2.warm_start.radius_histogram
    assert expected > 0, "no OK coarse cell would make this vacuous"
    assert expected < report.pass2.warm_start.warm_started, (
        "every cell at radius 0 would mean the fine points are not being "
        "sourced from anywhere, which is a different fixture"
    )
    assert histogram.get(0, 0) == expected
    # The coarse lattice really is a subset of the grid, from the stride alone.
    assert coarse_outcome.shape[0] == -(-9 // stride)
    assert coarse_outcome.shape[1] == -(-8 // stride)


# --------------------------------------------------------------------------
# Criterion 6 -- the refusal as a user meets it
# --------------------------------------------------------------------------


def test_criterion_6_the_refusal_reaches_a_user_as_an_exit_code_and_a_message(tmp_path):
    """A mismatched pass-1 store on disk stops the run, in a real process.

    Behaviour under test: criterion 6's user-facing half. `tests/test_barrier.py`
    asserts ten refusals by calling the gate; this types a command line and
    reads the exit code and stderr, which is what a user gets and what a
    resuming script branches on.

    **THE BARRIER ITSELF IS NOT REACHABLE FROM THE COMMAND LINE, AND THAT IS
    STATED RATHER THAN WORKED AROUND.** `run_two_pass` derives both passes from
    one config, so pass 1's recorded parent `fit_hash` and pass 2's own can
    never disagree on that path -- the cross-store gate guards a door only a
    library caller can open, and `tests/test_twopass.py` and
    `tests/test_barrier.py` are where it is exercised. What a user CAN reach is
    a pass-1 store left on disk by an earlier run at a different stride, which
    is the same class of fault caught one gate earlier.

    Expected values determined independently: the exit code is design doc
    §14.3's, and the message must name what would lift the refusal rather than
    merely refusing -- **a refusal that says what would lift it is planning
    information; one that does not is a wall.**

    Bug this catches: a mismatch that is detected and then swallowed, so the
    second run silently resumes a store fitted under different settings. Every
    tile would look complete and the fits would be a mixture of two
    parameterisations, with nothing on disk recording which points came from
    which.
    """
    uri = _input(tmp_path)
    first = _config(tmp_path, uri, name="first.toml")
    store = tmp_path / "out.zarr"
    assert _invoke(str(first), str(store), "--two-pass").returncode == 0
    assert pass1_store_path(store).exists()

    second = _config(tmp_path, uri, name="second.toml")
    second.write_text(
        second.read_text().replace("coarse_stride = 2", "coarse_stride = 3")
    )
    # **THE SAME OUTPUT PATH, WHICH IS THE WHOLE FIXTURE.** Pass 1's store is
    # derived from the output path by a stated rule, so writing elsewhere gives
    # the second run a fresh coarse store and no mismatch to detect -- which is
    # what this test did on its first run, and it passed the command line with
    # exit 0 while claiming to have found a refusal.
    result = _invoke(str(second), str(store), "--two-pass")

    assert result.returncode != 0, result.stdout
    message = result.stderr + result.stdout
    assert "fit_hash" in message, message
    assert str(pass1_store_path(store)) in message, (
        f"the refusal must name WHICH store it refused. Got: {message}"
    )
    # **NAMING WHAT WOULD LIFT IT, ASSERTED ON THE REMEDY AND NOT ON A WORD.**
    # The message offers two: restore the configuration that produced the
    # store, or write a new one. A refusal that says what would lift it is
    # planning information; one that does not is a wall.
    assert "restore the configuration" in message, message
    assert "write a new store" in message, message


# --------------------------------------------------------------------------
# Criterion 12 -- the SIGN, on a coherent field, and never the magnitude
# --------------------------------------------------------------------------


def _coherent_input(
    tmp_path: Path, n_y: int = 7, n_x: int = 6, n_time: int = 48
) -> str:
    """A field whose true parameters vary SMOOTHLY across the grid.

    **(h): A FIELD OF INDEPENDENT DRAWS WOULD MEASURE NOTHING.** Warm-starting
    pays only where a neighbour's optimum is near your own, so a saving measured
    on `standard_normal` per point -- which is every other two-pass fixture in
    this suite -- is a measurement of the store round-trip. Here the noise
    amplitude and the trend both vary as smooth functions of position, so
    neighbouring optima are genuinely close and the mechanism has something to
    exploit.

    **THE COHERENCE IS A CONSTRUCTION PARAMETER AND THAT IS THE STANDING
    LIMITATION, NOT A DEFECT OF THIS FIXTURE.** No 2c number comes from real
    data; the spatial coherence of real altimetry optima has never been
    measured. This fixture can establish a SIGN and cannot establish a
    magnitude -- see `test_criterion_12_...` for why the magnitude needs 2d.
    """
    origin = np.datetime64("2000-01-01")
    rng = np.random.default_rng(17)
    time = np.arange(n_time, dtype=np.float64) / 12.0
    values = np.empty((n_time, n_y, n_x), dtype=np.float64)
    for iy in range(n_y):
        for ix in range(n_x):
            # Smooth in BOTH axes and slow relative to the stride, so a coarse
            # neighbour two cells away is a good start rather than a random one.
            amplitude = 1.0 + 0.6 * np.sin(0.35 * iy) * np.cos(0.30 * ix)
            slope = 0.4 * np.cos(0.25 * iy + 0.20 * ix)
            values[:, iy, ix] = slope * time + amplitude * rng.standard_normal(n_time)
    dataset = xr.Dataset(
        {"sla": (("time", "y", "x"), values.astype("float32"))},
        coords={
            "time": np.array(
                [origin + np.timedelta64(31 * i, "D") for i in range(n_time)]
            ),
            "y": 100.0 + 2.5 * np.arange(n_y),
            "x": 500.0 - 0.5 * np.arange(n_x),
        },
    )
    path = tmp_path / "coherent.zarr"
    dataset.to_zarr(path)
    return str(path)


def test_criterion_12_the_shipped_mechanism_saves_iterations_on_a_coherent_field(
    tmp_path,
):
    """The SIGN of the saving, through the shipped path. Never the magnitude.

    **THIS IS CRITERION 12's POSITIVE CONTROL AND NOT CRITERION 12.** The
    criterion's threshold -- §11.2's 30% at production record length -- is not
    measured here and cannot be: 21 s per point per arm at `N = 630` puts the
    smallest non-degenerate `k = 8` lattice at 1.7 hours against a 39-minute
    suite, no spatially coherent production-length fixture exists, and the
    saving is 7.80 / 31.73 / 42.28% at `N = 96 / 384 / 630` so a short run
    measures a different number rather than a weaker one. The magnitude's
    verdict is MET_WITH_REDUCED_SCOPE and its closer is 2d.

    **WHAT THIS ESTABLISHES IS THE DIFFERENCE BETWEEN "NOT MEASURED" AND
    "INERT".** A reduced-scope verdict on a magnitude is indistinguishable from
    a mechanism that does nothing, and those are opposite findings. So: does
    warm-starting through `run_two_pass` -- the source map, the store
    round-trip, `x0_valid`, all of it -- reduce iterations at all, on a field
    where a neighbour's optimum is a good start?

    Expected value determined independently: the comparison is the total
    `/primitives/iterations` of a `--two-pass` run against a plain cold run of
    the same input at the same budget, both read off disk. The assertion is
    `warm < cold` **strictly**, with no threshold, and it is one-sided because
    the spike measured +7.80% at the shortest length it tried.

    Bug this catches: warm starts that are computed, stored, read back and then
    not used -- (a2c) at the whole mechanism. Every count in the report would
    still say `warm_started`, because those counts come from the source map and
    not from the optimizer, so the run would report a working warm start while
    taking exactly the cold path. **It also catches the reverse**: a source map
    that hands out systematically bad starts, which costs iterations rather
    than saving them and would show up here as the wrong sign.
    """
    from metamer.batch.run import run

    uri = _coherent_input(tmp_path)
    config = _config(tmp_path, uri)
    warm = run_two_pass(config, tmp_path / "warm.zarr")
    cold = run(config, tmp_path / "cold.zarr")
    assert warm.pass2 is not None and warm.pass2.warm_start is not None
    assert warm.pass2.warm_start.warm_started > 0

    warm_iterations = _array(warm.store_path, "primitives", "iterations")
    cold_iterations = _array(cold.store_path, "primitives", "iterations")
    fitted = (
        _array(warm.store_path, "status", "outcome")
        == _array(cold.store_path, "status", "outcome")
    ) & (cold_iterations != np.iinfo(np.uint16).max)
    assert fitted.any(), "no comparable cell would make this vacuous"

    warm_total = int(warm_iterations[fitted].sum())
    cold_total = int(cold_iterations[fitted].sum())
    assert warm_total < cold_total, (
        f"warm-starting took {warm_total} iterations against cold's "
        f"{cold_total} on a spatially coherent field; the mechanism is inert "
        "or is handing out bad starts"
    )


# --------------------------------------------------------------------------
# The verdict record, bound to the tree
# --------------------------------------------------------------------------


def _collected_test_names() -> set[str]:
    """Every `test_*` function defined anywhere under `tests/`.

    **THE SAME STATIC SCAN 2b's BINDER USES, AND THE REASON IS ITS REASON**: the
    claim is that the evidence EXISTS, not that this invocation selected it, so
    `pytest -k` must not make the binding fail for an unrelated cause. It is
    reimplemented here rather than imported only because 2b's is module-private;
    **if either grows a case, both must** -- and that is exactly the drift the
    duplication rule warns about, so it is stated where a reader will hit it.

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
    """Twelve criteria, numbered 1 to 12, no gaps and no repeats.

    Expected value determined independently: the plan's Task 8 table has twelve
    rows numbered 1 through 12. **The two inherited criteria are 2b's 6 and 7
    and are NOT numbered 13 and 14 here** -- doing so would give two criteria
    two numbers each, and a reader reconciling the two sub-phases' tables would
    find four criteria where there are two.

    Bug this catches: a criterion dropped from the record while the plan still
    lists it, which reports a complete sub-phase with a row missing. **Compared
    as a set as well as a count**, because a count cannot tell a duplicate from
    an omission.
    """
    numbers = [criterion.number for criterion in PHASE_2C_EXIT_CRITERIA]
    assert sorted(numbers) == list(range(1, 13))
    assert len(set(numbers)) == len(numbers)


def test_every_criterion_names_evidence_that_exists():
    """A verdict standing on a test that was renamed or deleted fails here.

    **THIS IS THE BINDING, AND ITS LIMIT IS STATED RATHER THAN IMPLIED.** A
    static scan can check that the evidence EXISTS; it cannot check that the
    evidence is relevant. It is a guard against drift, not a proof of
    relevance -- the relevance is carried by each criterion's `statement`
    sitting beside its names, where a reviewer can see both.

    Expected values determined independently: every name in `established_by` is
    a `def test_...` somewhere under `tests/`, found by parsing rather than by
    importing.

    Bug this catches: a test renamed during a refactor, leaving a verdict whose
    stated evidence does not exist -- which reads exactly like a verdict whose
    evidence does. This is the failure 2b's criterion 6 had for four tasks,
    because a sentence in a document is attached to nothing.
    """
    have = _collected_test_names()
    missing = {
        (criterion.number, name)
        for criterion in PHASE_2C_EXIT_CRITERIA
        for name in criterion.established_by
        if name not in have
    }
    assert not missing, missing
    for criterion in PHASE_2C_EXIT_CRITERIA:
        assert criterion.established_by, criterion.number


def test_every_criterion_names_a_reading_with_no_exempt_list():
    """All twelve, not a listed subset. That is this task's first requirement.

    **2c's RULE IS STRICTLY STRONGER THAN 2b's**, which asserts *"a reading, or
    a statement that it has none"* because only four of its sixteen criteria
    were about a measured quantity. Every 2c criterion is about something a
    harness reads, and the plan's table gives all twelve a third column.

    Expected values determined independently: `READINGS` is the plan's own
    third column, entry by entry.

    Bug this catches: a criterion added later with `reading=None`, which is how
    2b's 6 and 7 stayed ambiguous through four tasks. **An exempt list would be
    (c5)** -- a gate written as an enumeration of the members that happened to
    exist when it was written, which has now fired twice in this project.
    """
    for criterion in PHASE_2C_EXIT_CRITERIA:
        assert criterion.reading is not None, criterion.number
        assert criterion.reading in READINGS, (criterion.number, criterion.reading)


def test_every_non_met_verdict_states_its_scope_and_every_criterion_its_outside():
    """A reduced scope without its qualification is a shrug.

    Expected behaviour determined independently: `MET` may carry an empty
    scope, because "it holds" needs no qualification; the other two may not,
    because the qualification is exactly what a reader needs from them.
    `outside` is never empty for any verdict -- *"driven from outside wherever
    an outside exists"* has a clause people drop, so the record states which of
    the two cases each criterion is in.

    Bug this catches: criterion 12 downgraded to reduced scope with no
    statement of what was and was not measured, which downstream is
    indistinguishable from a criterion that was measured and passed narrowly.
    """
    for criterion in PHASE_2C_EXIT_CRITERIA:
        if criterion.verdict is not Verdict.MET:
            assert criterion.scope.strip(), criterion.number
        assert criterion.outside.strip(), criterion.number


def test_the_two_inherited_criteria_are_read_out_of_2bs_record_and_still_failed():
    """2b's criteria 6 and 7 stay FAILED, bound rather than copied.

    **THE OBVIOUS WRONG IMPLEMENTATION IS TWO BOOLEANS IN 2c's RECORD**, and it
    drifts silently in the direction that matters: 2c would go on asserting
    they failed after somebody fixed them, or stop asserting it after somebody
    renumbered them. This reads the verdicts out of `PHASE_2B_EXIT_CRITERIA` --
    the same construction 2b used to stop its own criterion 6 going stale,
    applied one sub-phase later.

    Expected values determined independently: the plan says 2b's criterion 6
    and criterion 7 stay FAILED and that **2c must not be read as having
    reopened the residency model**.

    Bug this catches: 2c being credited with a repair it did not make. It also
    catches a renumbering -- both criteria are looked up BY NUMBER and both
    must be found, so a record that renumbered them fails loudly instead of
    silently asserting about two different criteria.
    """
    by_number = {criterion.number: criterion for criterion in PHASE_2B_EXIT_CRITERIA}
    assert {6, 7} <= by_number.keys()
    for number in (6, 7):
        assert by_number[number].verdict is Verdict.FAILED, number
        assert by_number[number].scope.strip(), number

    # And 2c's own record does not claim them. Numbers are per sub-phase; a 2c
    # criterion numbered 13 or 14 would be one of these wearing a second number.
    assert max(c.number for c in PHASE_2C_EXIT_CRITERIA) == 12


def test_the_record_is_serialisable_so_the_closing_table_cannot_drift_from_it():
    """Every field is plain data, so PROGRESS.md's table has one source.

    Behaviour under test: that the record can be rendered without executing
    anything -- which is what makes it possible for the closing table to be
    generated from it rather than written beside it.

    Expected value determined independently: `json.dumps` succeeds on the
    record's fields, with `Verdict` a `StrEnum` and everything else a string,
    an int or a tuple of strings.

    Bug this catches: a field holding a callable or an object, which would make
    the record readable only by importing it -- and a table nobody can render is
    a table that gets retyped, which is how the two copies drift.
    """
    payload = json.dumps(
        [
            {
                "number": criterion.number,
                "statement": criterion.statement,
                "verdict": str(criterion.verdict),
                "reading": criterion.reading,
                "scope": criterion.scope,
                "established_by": list(criterion.established_by),
                "outside": criterion.outside,
            }
            for criterion in PHASE_2C_EXIT_CRITERIA
        ]
    )
    assert len(json.loads(payload)) == 12
