"""`--reuse-fits-from`: recompute the derived arrays into a new store.

**THIS IS THE ONLY CONSUMER OF THE THREE-HASH SPLIT.** Task 11 established that
the in-place recompute arm has no reachable input, so this command is the sole
demonstration that `fit_hash` identifies anything rather than merely existing.
The tests below are therefore the tests of the split: `fit_hash` equal across
two stores whose `compat_hash` and `run_hash` both differ, with no fit run.

**"NO FIT RAN" IS A PURE NEGATIVE AND IS PROVED BY THE RAISING STUB**, never by
timing. Its positive controls are elsewhere and are cited rather than
re-derived: `tests/test_stub_engine.py` proves the stub raises when `fit` is
reached at all, and
`test_completion.py::test_the_same_resume_reaches_the_engine_for_an_outstanding_tile`
proves the runner's own seam reaches it. Without them, a recompute that
never entered the tiling loop would satisfy every assertion here.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import xarray as xr
import zarr

from metamer.batch.input import InputContractError
from metamer.batch.run import run
from metamer.batch.validation import ExitCode, ValidationError
from metamer.batch.write import InvariantError
from tests.conftest import RaisingStubEngine

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")

#: One point per tile at this fixture's geometry; see `test_completion.py` for
#: the measurement. The recompute reads primitives, so the tile count matters
#: only in that a source with an unset bit must be constructible.
#: **RE-DERIVED 2026-08-15 AT PHASE 2b TASK 2**, where the budget stopped being
#: the block. `block = (budget - floor) x (1 - 0.15)` and the floor here is
#: `tests/conftest.py`'s 1 MB stub, in-process and through `METAMER_FLOOR_BYTES`
#: for a subprocess. At `d=1, k_beta=4, p_max=3, N=60, M=2` the per-series cost
#: is **926 B** (was 1322 before Task 0 corrected the formula) and the live
#: solver working set is **11 200 B**, so a side of `s` needs a block of
#: `s^2 x 926 + 11 200`. **The old 2e-6 GB -- 2000 bytes -- is now below the
#: floor and refused**, correctly: it worked only because the budget was the
#: block, which is the defect F1 names.
ONE_POINT_PER_TILE = 0.001015900

_CONFIG = """
data_uri = "{uri}"
variable = "sla"
signal_terms = ["constant", "trend", "annual"]
candidates = ["white", "white + matern12"]
criteria = {criteria}
memory_budget_gb = {budget}
objective = "{objective}"
"""


def _input(directory: Path, *, n_y: int = 2, n_x: int = 1, n_time: int = 60) -> str:
    """A zarr input of white noise with one short series.

    The point at `(0, 0)` keeps six samples and is NaN afterwards. Under REML
    that gives `n = n_obs - design_rank = 2`, so HQIC is undefined there while
    AIC ranks it -- the fit-OK / criterion-undefined point the recompute must
    reproduce from stored primitives.

    Args:
        directory: Destination directory.
        n_y: Grid rows.
        n_x: Grid columns.
        n_time: Series length.

    Returns:
        The store URI.
    """
    rng = np.random.default_rng(0)
    values = rng.standard_normal((n_time, n_y, n_x)).astype("float32")
    values[6:, 0, 0] = np.nan
    origin = np.datetime64("2000-01-01")
    axis = np.array([origin + np.timedelta64(31 * i, "D") for i in range(n_time)])
    xr.Dataset(
        {"sla": (("time", "y", "x"), values)},
        coords={
            "time": axis,
            "y": np.arange(n_y, dtype="float64"),
            "x": np.arange(n_x, dtype="float64"),
        },
    ).to_zarr(directory / "in.zarr")
    return str(directory / "in.zarr")


def _config(
    directory: Path,
    uri: str,
    *,
    name: str = "c.toml",
    criteria: str = '["aic", "hqic"]',
    objective: str = "reml",
    budget: float = ONE_POINT_PER_TILE,
) -> Path:
    """Write a configuration.

    Args:
        directory: Destination directory.
        uri: The input store.
        name: File name.
        criteria: TOML list literal -- what the recompute varies.
        objective: `reml`, so the criterion-undefined point is reachable.
        budget: `memory_budget_gb`.

    Returns:
        The config path.
    """
    path = directory / name
    path.write_text(
        _CONFIG.format(uri=uri, criteria=criteria, objective=objective, budget=budget)
    )
    return path


def _clear_first_bit(store: Path) -> None:
    """Mark the first tile of a store outstanding again.

    Args:
        store: The store to damage.
    """
    group = zarr.open_group(str(store), mode="r+")["completion"]
    assert isinstance(group, zarr.Group)
    tiles = group["tiles"]
    assert isinstance(tiles, zarr.Array)
    tiles[0, 0] = 0


def _array_of(store: Path, group: str, name: str) -> zarr.Array[Any]:
    """Open one array for writing, narrowed for the type checker.

    Args:
        store: The store.
        group: Group name.
        name: Array name.

    Returns:
        The array.
    """
    holder = zarr.open_group(str(store), mode="r+")[group]
    assert isinstance(holder, zarr.Group)
    array = holder[name]
    assert isinstance(array, zarr.Array)
    return array


def _attrs(store: Path) -> dict[str, Any]:
    """Read a store's root attrs.

    Args:
        store: The store.

    Returns:
        The attrs mapping.
    """
    return dict(zarr.open_group(str(store), mode="r").attrs)


def _data_arrays(store: Path) -> dict[str, np.ndarray]:
    """Every gridded array outside `/selection/` and `/completion/`.

    **Derived from the store's own listing, never from a list here**, so a
    schema addition that the copy misses fails the comparison rather than
    passing it. Coordinates are excluded by their dimensions rather than by
    name.

    Args:
        store: The store.

    Returns:
        `group/name` to values.
    """
    root = zarr.open_group(str(store), mode="r")
    found: dict[str, np.ndarray] = {}
    for group_name in ("signal", "primitives", "noise", "status", "warmstart"):
        group = root[group_name]
        assert isinstance(group, zarr.Group)
        for name, array in group.arrays():
            dims = tuple(getattr(array.metadata, "dimension_names", None) or ())
            if dims[:2] == ("y", "x"):
                found[f"{group_name}/{name}"] = np.asarray(array[:])
    return found


@pytest.fixture(scope="module")
def source(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, str, Path]:
    """A complete two-point store fitted under REML with AIC and HQIC.

    Args:
        tmp_path_factory: pytest's directory factory.

    Returns:
        `(directory, input uri, store path)`.
    """
    base = tmp_path_factory.mktemp("reuse")
    uri = _input(base)
    store = base / "source.zarr"
    report = run(_config(base, uri), store)
    # FIXTURE GUARDS: the source must be complete, or every recompute below is
    # testing the refusal instead of the operation -- and it must carry the
    # fit-OK / criterion-undefined point, or the criterion axis is not exercised.
    assert report.tiles_written == report.tiles_total
    selection = xr.open_zarr(store, group="selection")
    criteria = [str(name) for name in selection["c"].values]
    assert np.isnan(selection["ic_best"].values[0, 0, criteria.index("hqic")])
    assert np.isfinite(selection["ic_best"].values[0, 0, criteria.index("aic")])
    return base, uri, store


@pytest.fixture
def ready(source: tuple[Path, str, Path], tmp_path: Path) -> tuple[str, Path]:
    """A private copy of the source store, with its input.

    Args:
        source: The module's fitted store.
        tmp_path: This test's directory.

    Returns:
        `(input uri, source copy)`.
    """
    _base, uri, fitted = source
    copy = tmp_path / "source.zarr"
    shutil.copytree(fitted, copy)
    return uri, copy


# --------------------------------------------------------------------------
# The operation
# --------------------------------------------------------------------------


def test_a_recompute_adds_a_criterion_without_fitting(
    ready: tuple[str, Path], tmp_path: Path, raising_engine: RaisingStubEngine
) -> None:
    """The whole point: a criterion set changes and nothing is refitted.

    The source ranks by AIC and HQIC; the new store ranks by AIC alone, which
    resizes the `c` axis -- the operation Task 11 refuses in place and names
    this command as the resolution for.

    **The negative is proved by the stub**, whose positive controls are named in
    this module's docstring.

    Catches a recompute that quietly refits (the stub raises), and one that
    writes a `/selection/` of the wrong width.
    """
    uri, src = ready
    new = tmp_path / "new.zarr"

    report = run(
        _config(tmp_path, uri, criteria='["aic"]', name="new.toml"),
        new,
        reuse_fits_from=src,
        engine=raising_engine,
    )

    assert report.tiles_written == report.tiles_total
    assert raising_engine.calls == []
    selection = xr.open_zarr(new, group="selection")
    assert [str(name) for name in selection["c"].values] == ["aic"]
    assert selection["delta_ic"].shape[-1] == 1


def test_the_new_store_keeps_the_source_fit_hash_and_changes_the_others(
    ready: tuple[str, Path], tmp_path: Path, raising_engine: RaisingStubEngine
) -> None:
    """The entire claim the three-hash split makes, asserted directly.

    `fit_hash` equal across the two stores, `compat_hash` and `run_hash` not --
    and the source's path and all three of its hashes recorded as provenance, so
    a reader verifies the claim instead of trusting the label.

    **Not inferred from the recompute succeeding**: a recompute that copied the
    source's attrs wholesale would also succeed, and would produce a store
    claiming a `run_hash` that describes a different invocation.

    Catches inherited provenance, and a `fit_hash` that moved when the criterion
    set changed -- which would mean the split separates nothing.
    """
    uri, src = ready
    new = tmp_path / "new.zarr"
    before = _attrs(src)

    run(
        _config(tmp_path, uri, criteria='["aic"]', name="new.toml"),
        new,
        reuse_fits_from=src,
        engine=raising_engine,
    )

    after = _attrs(new)
    assert after["fit_hash"] == before["fit_hash"]
    assert after["compat_hash"] != before["compat_hash"]
    assert after["run_hash"] != before["run_hash"]
    assert after["source_store"] == str(src)
    assert after["source_fit_hash"] == before["fit_hash"]
    assert after["source_compat_hash"] == before["compat_hash"]
    assert after["source_run_hash"] == before["run_hash"]


def test_everything_outside_selection_is_copied_verbatim(
    ready: tuple[str, Path], tmp_path: Path, raising_engine: RaisingStubEngine
) -> None:
    """`/primitives/`, `/noise/`, `/signal/`, `/status/` and `/warmstart/` transfer.

    The comparison is over **the arrays the store lists**, not over a list
    carried here, so an array added to the schema later fails this test rather
    than passing it -- a missed array keeps its fill value, which for every
    float array is NaN and reads as "this point failed".

    Catches a copy that misses a group, and a recompute that rewrites `/status/`
    -- fit-stage outcomes transfer unchanged, because a recompute-stage failure
    is criterion-specific and `outcome` has no `c` axis.
    """
    uri, src = ready
    new = tmp_path / "new.zarr"

    run(
        _config(tmp_path, uri, criteria='["aic"]', name="new.toml"),
        new,
        reuse_fits_from=src,
        engine=raising_engine,
    )

    original = _data_arrays(src)
    copied = _data_arrays(new)
    assert set(copied) == set(original)
    assert original  # the listing produced something to compare
    for name, values in original.items():
        np.testing.assert_array_equal(copied[name], values, err_msg=name)


def test_the_criterion_undefined_point_survives_the_recompute(
    ready: tuple[str, Path], tmp_path: Path, raising_engine: RaisingStubEngine
) -> None:
    """A recompute-stage failure lands in `/selection/`, never in `/status/`.

    The point at `(0, 0)` fits under REML with `n = 2`, so HQIC is undefined
    there and AIC is not. Reproducing that **from stored primitives** is the
    claim: the criterion axis carries the failure, the outcome axis is untouched,
    and `selected` is the `-1` no-winner sentinel rather than a candidate index.

    Catches a recompute that folds a criterion-specific failure into the outcome
    ladder -- which would make a criterion-independent array depend on which
    criterion was requested -- and one that writes `0` where no candidate won.
    """
    uri, src = ready
    new = tmp_path / "new.zarr"

    run(
        _config(tmp_path, uri, name="new.toml"),
        new,
        reuse_fits_from=src,
        engine=raising_engine,
    )

    selection = xr.open_zarr(new, group="selection")
    criteria = [str(name) for name in selection["c"].values]
    hqic = criteria.index("hqic")
    assert np.isnan(selection["ic_best"].values[0, 0, hqic])
    assert selection["selected"].values[0, 0, hqic] == -1
    assert np.isfinite(selection["ic_best"].values[0, 0, criteria.index("aic")])
    status = xr.open_zarr(new, group="status")
    original = xr.open_zarr(src, group="status")
    np.testing.assert_array_equal(status["outcome"].values, original["outcome"].values)


@pytest.mark.slow
def test_the_new_store_opens_with_the_source_deleted(
    ready: tuple[str, Path], tmp_path: Path, raising_engine: RaisingStubEngine
) -> None:
    """Self-contained: no reference, no symlink, no path a reader must resolve.

    **Asserting this with the source still on disk tests nothing** -- a zarr
    reference would resolve happily. The source is deleted first, and the read
    happens in a subprocess without metamer, which is the reader design doc 12.4
    has in mind.

    Catches provenance that a reader must follow rather than merely read, and a
    copy that left an array resolving through the source.
    """
    uri, src = ready
    new = tmp_path / "new.zarr"
    run(
        _config(tmp_path, uri, criteria='["aic"]', name="new.toml"),
        new,
        reuse_fits_from=src,
        engine=raising_engine,
    )

    shutil.rmtree(src)

    program = textwrap.dedent(
        """
        import sys, importlib.util
        assert importlib.util.find_spec("metamer") is None, "control failed"
        import numpy as np, xarray as xr
        primitives = xr.open_zarr(sys.argv[1], group="primitives")
        selection = xr.open_zarr(sys.argv[1], group="selection")
        print(int(np.isfinite(primitives["log_lik"].values).sum()))
        print(list(selection["c"].values))
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", program, str(new)],
        capture_output=True,
        text=True,
        cwd="/",
        env={k: v for k, v in os.environ.items() if k != "PYTHONPATH"},
    )

    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert int(lines[0]) > 0
    assert lines[1] == "['aic']"


# --------------------------------------------------------------------------
# Verifying the source
# --------------------------------------------------------------------------


def test_an_incompletely_fitted_source_is_refused_with_exit_code_four(
    ready: tuple[str, Path], tmp_path: Path, raising_engine: RaisingStubEngine
) -> None:
    """The refusal without which the failure has no symptom at all.

    Recomputing from a partially fitted store yields a **complete-looking** new
    store: every array the right shape, `/selection/` written everywhere, and
    `/primitives/` full of fill values at the tiles the source never fitted.

    It is a layer-4 error because it is a fact about data on disk rather than
    about the configuration -- exit code 4 -- and `InputContractError` is not a
    `ValidationError`, so the two cannot land in one clause.

    Catches verifying the source after the tiling loop, or not at all.
    """
    uri, src = ready
    _clear_first_bit(src)

    with pytest.raises(InputContractError) as refusal:
        run(
            _config(tmp_path, uri, criteria='["aic"]', name="new.toml"),
            tmp_path / "new.zarr",
            reuse_fits_from=src,
            engine=raising_engine,
        )

    assert "completion" in str(refusal.value)
    assert raising_engine.calls == []
    assert not (tmp_path / "new.zarr").exists()


def test_a_source_whose_fits_do_not_match_the_request_is_refused(
    ready: tuple[str, Path], tmp_path: Path, raising_engine: RaisingStubEngine
) -> None:
    """`fit_hash` is checked against the source before anything is read.

    The request changes `objective`, which is fit-relevant, so the source's
    primitives were produced under a different likelihood. Reusing them would
    produce a store whose `/selection/` ranks numbers its own attrs no longer
    describe.

    Catches a recompute that checks only that the source *exists*, and one that
    checks after copying.
    """
    uri, src = ready

    with pytest.raises(ValidationError) as refusal:
        run(
            _config(tmp_path, uri, objective="ml", name="new.toml"),
            tmp_path / "new.zarr",
            reuse_fits_from=src,
            engine=raising_engine,
        )

    assert "fit_hash" in str(refusal.value)
    assert raising_engine.calls == []


def test_a_source_with_different_candidates_is_refused_naming_the_index(
    ready: tuple[str, Path], tmp_path: Path, raising_engine: RaisingStubEngine
) -> None:
    """The positional comparison applies to a source too, and for the same reason.

    The model axis is positional in both stores, so a differing candidate would
    have the recompute rank one candidate's primitives under another's label --
    and the new store's `/noise/` coordinates would describe the requested
    candidates over the copied candidates' values.

    Catches reusing Task 11's gate wholesale on the source **and** dropping the
    comparison for it: the criterion arm must not apply here, and this one must.
    """
    uri, src = ready
    config = tmp_path / "new.toml"
    config.write_text(
        _CONFIG.format(
            uri=uri, criteria='["aic"]', objective="reml", budget=ONE_POINT_PER_TILE
        ).replace(
            'candidates = ["white", "white + matern12"]',
            'candidates = ["white", "matern32"]',
        )
    )

    with pytest.raises(ValidationError) as refusal:
        run(
            config,
            tmp_path / "new.zarr",
            reuse_fits_from=src,
            engine=raising_engine,
        )

    assert "index 1" in str(refusal.value)
    assert raising_engine.calls == []


def test_a_missing_source_is_a_layer_four_fault_and_not_a_crash(
    ready: tuple[str, Path], tmp_path: Path
) -> None:
    """A named source that is not there is diagnosed, not raised through.

    It is layer 4 for the same reason an incomplete source is: **a fact about
    data on disk**, not about the configuration. The message names the flag,
    because the path came from the command line and the user needs to know
    which argument was wrong.

    Catches the absence surfacing as a zarr `FileNotFoundError` -- an unhandled
    exception, exit code 1, which the taxonomy spends on "completed with
    failures above threshold" and which prints a traceback where a user expects
    a diagnosis.
    """
    uri, _src = ready

    with pytest.raises(InputContractError, match="reuse-fits-from"):
        run(
            _config(tmp_path, uri, criteria='["aic"]', name="new.toml"),
            tmp_path / "new.zarr",
            reuse_fits_from=tmp_path / "absent.zarr",
        )


# --------------------------------------------------------------------------
# The command line
# --------------------------------------------------------------------------


def test_the_flag_parses_and_an_incomplete_source_exits_four(
    ready: tuple[str, Path], tmp_path: Path
) -> None:
    """`--reuse-fits-from` on the real command line, and its exit code.

    Task 4 left the flag out deliberately -- "a flag that parses and does
    nothing reads as supported" -- so this is the first test that it exists at
    all, and it is paired with the exit code because a flag that parses and
    refuses everything would satisfy the first half alone.

    Catches the flag absent (argparse exits 3 on an unknown option, which is
    also a refusal), and the layer-4 error being mapped to the wrong code.
    """
    uri, src = ready
    _clear_first_bit(src)
    config = _config(tmp_path, uri, criteria='["aic"]', name="new.toml")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "metamer",
            str(config),
            str(tmp_path / "new.zarr"),
            "--reuse-fits-from",
            str(src),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == ExitCode.DATA_INVALID
    assert "layer 4 (data)" in result.stderr
    assert "Traceback" not in result.stderr


def test_the_criterion_refusal_now_names_the_command_that_resolves_it(
    ready: tuple[str, Path], tmp_path: Path
) -> None:
    """The one diagnostic that was waiting on this task.

    Task 11 refuses an in-place criterion-set change and named the *operation*
    only -- "recompute into a new store, or rerun" -- because naming a flag that
    does not parse reads as supported, which Q3 calls a defect committed on
    purpose. The flag parses now, so the message names it.

    Catches the message being left generic, which is how a refusal that could
    tell a user exactly what to type goes on not telling them.
    """
    uri, src = ready

    with pytest.raises(ValidationError) as refusal:
        run(_config(tmp_path, uri, criteria='["aic"]', name="new.toml"), src)

    assert "--reuse-fits-from" in str(refusal.value)


def test_the_new_store_keeps_the_sources_tile_geometry(
    ready: tuple[str, Path], tmp_path: Path, raising_engine: RaisingStubEngine
) -> None:
    """The tile side is READ BACK from the source, not re-derived from the budget.

    The recompute runs at a budget large enough to derive a tile side of 77
    against the source's 1, so the two disagree and the fixture can express the
    defect at all -- **the previous fixture ran at the source's own budget,
    where both derivations agree and the mutation survived.**

    Copied groups must be byte-identical to the source (exit criterion 5a),
    which needs identical chunk and shard geometry; and a re-derived side would
    give the new store a completion bitmap whose bits index different regions
    than the ones being copied into.

    Catches sizing the new store from `memory_budget_gb`, which is the natural
    thing to do because that is what a fitting run does.
    """
    uri, src = ready
    new = tmp_path / "new.zarr"

    report = run(
        _config(tmp_path, uri, criteria='["aic"]', name="new.toml"),
        new,
        memory_budget_gb=0.01,
        reuse_fits_from=src,
        engine=raising_engine,
    )

    assert _attrs(src)["tile_sides"]["shared"] == 1
    assert report.tile_side == 1
    assert _attrs(new)["tile_sides"]["shared"] == 1
    source_array = _array_of(src, "primitives", "log_lik")
    copied = _array_of(new, "primitives", "log_lik")
    assert copied.chunks == source_array.chunks
    assert copied.shards == source_array.shards


def test_the_new_store_copies_the_sources_tile_side_basis(
    ready: tuple[str, Path], tmp_path: Path, raising_engine: RaisingStubEngine
) -> None:
    """A recompute derives no side, so it claims no basis of its own.

    The side is read back from the source (a1), so the basis that produced it is
    the source's too. Expected value determined independently: the source was
    written by an ordinary run, which can only use the shipped analytic formula
    until Phase 2b Task 5, so both stores must read `default`.

    **THIS FIXTURE CANNOT YET FAIL FOR THE RIGHT REASON AND THAT IS RECORDED
    HERE**, not left for a reader to discover: nothing in 2b before Task 5 can
    write a basis other than `default`, so `copy the source's` and `write
    DEFAULT` agree on every store this suite can build -- (i7), a fixture
    sitting exactly where the two functions agree. **Task 5 is what moves it off
    that point**, by making a calibrated source expressible, and it owns
    strengthening this to a source whose basis is `cached`.

    Bug this catches once that lands: a recompute claiming it derived the side
    analytically when it derived nothing, which makes Task 6 read a basis change
    across a resume that never happened -- and send the user to a cache that was
    never involved.
    """
    uri, src = ready
    new = tmp_path / "new.zarr"

    run(
        _config(tmp_path, uri, criteria='["aic"]', name="new.toml"),
        new,
        reuse_fits_from=src,
        engine=raising_engine,
    )

    assert _attrs(src)["tile_side_basis"] == "default"
    assert _attrs(new)["tile_side_basis"] == _attrs(src)["tile_side_basis"]


def test_the_recomputed_ranking_matches_the_one_the_fit_path_wrote(
    ready: tuple[str, Path], tmp_path: Path, raising_engine: RaisingStubEngine
) -> None:
    """Same criterion, two paths, and the values must agree exactly.

    **`bic_neff` is the criterion that reads `n_eff`**, and it is here for that
    reason: under AIC and HQIC the field is never touched, so a recompute
    reading `n_eff_trend` where it should read `n_eff_bic` produces identical
    output and no test can see it. The source ranks by AIC and `bic_neff`; the
    new store ranks by `bic_neff` alone, and its `delta_ic` must equal the
    source's for that criterion.

    The oracle is the **fit path's own values**, which is a different derivation
    reaching the store by a different route -- not a recomputation of the
    recomputation.

    Catches the wrong primitive being read into `CandidateScores`, and a
    recompute that ranks under the wrong criterion when `c` is reordered.
    """
    uri, _src = ready
    base = tmp_path / "with_neff.zarr"
    run(_config(tmp_path, uri, criteria='["aic", "bic_neff"]', name="base.toml"), base)
    new = tmp_path / "new.zarr"

    run(
        _config(tmp_path, uri, criteria='["bic_neff"]', name="new.toml"),
        new,
        reuse_fits_from=base,
        engine=raising_engine,
    )

    fitted = xr.open_zarr(base, group="selection")
    recomputed = xr.open_zarr(new, group="selection")
    position = [str(name) for name in fitted["c"].values].index("bic_neff")
    np.testing.assert_array_equal(
        recomputed["delta_ic"].values[..., 0],
        fitted["delta_ic"].values[..., position],
    )
    np.testing.assert_array_equal(
        recomputed["weight"].values[..., 0], fitted["weight"].values[..., position]
    )


def test_a_source_violating_the_status_invariant_is_refused(
    ready: tuple[str, Path], tmp_path: Path, raising_engine: RaisingStubEngine
) -> None:
    """The copied block is checked before it is ranked, not trusted.

    A source whose `log_lik` is NaN where its status says `OK` is corrupt, and
    recomputing from it would produce a new store that inherits the corruption
    and looks freshly computed -- with its own provenance, its own hashes, and
    nothing to say the numbers came from somewhere broken.

    The check is the same function the fit path uses and the same one exit
    criterion 4 runs over a finished store, so the three cannot drift apart.

    Catches the recompute trusting its input because "the source was checked
    when it was written" -- which is true of a source this process wrote and
    says nothing about one it was handed.
    """
    uri, src = ready
    log_lik = _array_of(src, "primitives", "log_lik")
    outcome = _array_of(src, "status", "outcome")
    healthy = np.argwhere(np.asarray(outcome[:]) == 0)
    assert healthy.size, "fixture has no OK cell to corrupt"
    y, x, m = (int(value) for value in healthy[0])
    values = np.asarray(log_lik[:])
    values[y, x, m] = np.nan
    log_lik[:] = values

    with pytest.raises(InvariantError):
        run(
            _config(tmp_path, uri, criteria='["aic"]', name="new.toml"),
            tmp_path / "new.zarr",
            reuse_fits_from=src,
            engine=raising_engine,
        )
