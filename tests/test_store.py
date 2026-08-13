"""Store creation: fill values, dtypes, coordinates, provenance and the read.

**NOTHING ABOUT A CORRECT STORE IS OBSERVABLE IN ITS BYTES AT CREATION.** Zarr
does not write a chunk equal to the fill value, so every array here is pure
metadata and a store created with the wrong fill is byte-for-byte identical to
one created with the right one. **Every assertion below is on values read back**,
and the one test that does look at files exists to pin that fact with a positive
control beside it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import warnings
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pytest
import xarray as xr
import zarr

import metamer
from metamer.batch import geometry, store
from metamer.batch.input import open_input
from metamer.config import load
from metamer.core import hashing
from metamer.core.capability import EngineId, Objective
from metamer.core.criteria import CandidateScores, Criterion, rank_candidates
from metamer.core.outcomes import Outcome
from metamer.core.registry import REGISTRY_VERSION

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")

_CONFIG = """
data_uri = "{uri}"
variable = "sla"
signal_terms = ["constant", "trend", "annual"]
candidates = ["white", "white + matern12"]
criteria = ["aic", "hqic"]
"""


def _months(n: int, start: str = "2000-01-01") -> np.ndarray:
    origin = np.datetime64(start)
    return np.array([origin + np.timedelta64(31 * i, "D") for i in range(n)])


def _input(tmp_path: Path, *, n_y: int = 4, n_x: int = 6) -> str:
    """A real zarr input satisfying the stage-4a contract."""
    dataset = xr.Dataset(
        {"sla": (("time", "y", "x"), np.zeros((24, n_y, n_x), dtype="float32"))},
        coords={
            "time": _months(24),
            "y": np.arange(n_y, dtype="float64") * 0.5,
            "x": np.arange(n_x, dtype="float64") * 0.25,
        },
    )
    path = tmp_path / "in.zarr"
    dataset.to_zarr(path)
    return str(path)


def _fixture(tmp_path: Path, **shape_kwargs: int) -> tuple[Path, dict[str, Any]]:
    """Create a store from a real TOML config over a real input.

    Returns:
        The store path and the provenance attrs it was created with.
    """
    uri = _input(tmp_path)
    config_path = tmp_path / "c.toml"
    config_path.write_text(_CONFIG.format(uri=uri))
    config = load(config_path)
    components = geometry.geometry_components(open_input(uri, "sla"))
    attrs = store.provenance_attrs(
        config,
        geometry_components=components,
        thread_limits={"openblas": 1, "openmp": 1, "numba": 1},
        read_amplification=1.0,
        unique_dt_count=2,
        tile_sides={"shared": 338, "per_point": 186},
    )
    shape = store.StoreShape(
        **{"n_y": 4, "n_x": 6, "n_beta": 4, "tile_side": 2, **shape_kwargs}
    )
    path = tmp_path / "out.zarr"
    store.create_store(
        path,
        specs=config.process_specs(),
        criteria=config.criteria,
        shape=shape,
        attrs=attrs,
    )
    return path, attrs


def _open(path: Path, group: str) -> xr.Dataset:
    return xr.open_zarr(str(path), group=group)


def _group(path: Path, name: str) -> zarr.Group:
    """One group of an opened store, narrowed for the type checker."""
    group = zarr.open_group(str(path), mode="r")[name]
    assert isinstance(group, zarr.Group)
    return group


def _raw(
    path: Path, group: str, name: str, mode: Literal["r", "r+"] = "r"
) -> zarr.Array[Any]:
    """One array of an opened store, narrowed for the type checker."""
    holder = zarr.open_group(str(path), mode=mode)[group]
    assert isinstance(holder, zarr.Group)
    array = holder[name]
    assert isinstance(array, zarr.Array)
    return array


# --------------------------------------------------------------------------
# Fill values -- the class of defect that is invisible on disk
# --------------------------------------------------------------------------


def test_status_reads_not_attempted_and_never_ok_before_anything_is_written(tmp_path):
    """A fresh store's status is NOT_ATTEMPTED at every point and model.

    `Outcome.OK` is code **0** and zarr's default integer `fill_value` is **0**,
    so the wrong fill makes a store that has computed nothing report a complete,
    wholly successful run -- and because zarr writes no chunk equal to the fill,
    the two stores are byte-identical on disk.

    Catches exactly that: taking the default fill, or writing zeros as an
    "initialization". The expected code is 8, which `outcomes._CODES` fixes
    permanently ("NEVER renumber").
    """
    path, _ = _fixture(tmp_path)

    outcome = _open(path, "status")["outcome"].values
    point = _open(path, "status")["point_outcome"].values

    assert np.all(outcome == 8)
    assert np.all(outcome == Outcome.NOT_ATTEMPTED.code)
    assert not np.any(outcome == Outcome.OK.code)
    assert np.all(point == Outcome.NOT_ATTEMPTED.code)


def test_every_fill_value_is_one_the_write_path_cannot_produce(tmp_path):
    """The whole fill table, hand-written, read back through xarray.

    Each entry is a value the writer never emits: a count is never negative, the
    iteration cap is 200, and -1 in `selected` already means "no winner", so an
    unwritten point must read as something else again.

    Catches any array left on a plausible default -- a `selected` of -1 reading
    as "ranked, no winner", an `n_valid` of 0 reading as "every candidate
    failed", an `iterations` of 0 reading as a real count.
    """
    path, _ = _fixture(tmp_path)

    selection = _open(path, "selection")
    primitives = _open(path, "primitives")
    signal = _open(path, "signal")
    noise = _open(path, "noise")
    warmstart = _open(path, "warmstart")

    assert np.all(np.isnan(signal["beta"].values))
    assert np.all(np.isnan(signal["beta_err"].values))
    assert np.all(np.isnan(selection["delta_ic"].values))
    assert np.all(np.isnan(selection["weight"].values))
    assert np.all(np.isnan(selection["ic_best"].values))
    assert np.all(selection["selected"].values == -2)
    assert np.all(selection["n_valid"].values == -1)
    for name in ("log_lik", "k", "n", "n_eff_trend", "n_eff_bic"):
        assert np.all(np.isnan(primitives[name].values)), name
    assert np.all(primitives["iterations"].values == 65535)
    assert np.all(np.isnan(noise["theta"].values))
    assert np.all(np.isnan(noise["theta_err"].values))
    assert np.all(np.isnan(warmstart["theta_unconstrained"].values))


def test_the_completion_bitmap_is_tile_shaped_and_zero_means_incomplete(tmp_path):
    """`/completion/tiles` is one element per tile and starts at zero.

    Hand-derived: a 4x6 grid at `tile_side = 2` is 2x3 tiles.

    Catches a bitmap shaped by points rather than tiles -- which would make the
    resume gate consult a per-point array that no write path sets -- and a fill
    of 1, which marks a store nothing has written as wholly complete. **Zero is
    the deliberate exception to the fill rule**: an unwritten tile really is
    incomplete.
    """
    path, _ = _fixture(tmp_path)

    tiles = _open(path, "completion")["tiles"]

    assert tiles.shape == (2, 3)
    assert tiles.dims == ("tile_y", "tile_x")
    assert np.all(tiles.values == 0)


def test_a_created_store_writes_no_chunks_and_a_region_write_writes_one(tmp_path):
    """The fill-value fact, executable, with the positive control beside it.

    Task 6 measured that zarr does not write a chunk equal to the fill value. At
    creation every array is entirely fill, so the store is metadata only.

    Catches any later assertion about "bytes written" being trusted as evidence
    that creation worked -- it reads a correct-looking zero. The control is the
    half that can fail: writing one tile's region produces exactly one shard
    object, so the absence above is a suppressed write and not a missing array.
    """
    path, _ = _fixture(tmp_path)
    # The label coordinates ARE written at creation -- they carry values, not
    # fill -- so the claim is about the data arrays, one group at a time.
    assert [f for f in (path / "status" / "outcome").rglob("c/*") if f.is_file()] == []
    assert [f for f in (path / "noise" / "theta").rglob("c/*") if f.is_file()] == []
    assert [f for f in (path / "noise" / "m").rglob("c/*") if f.is_file()] != []

    _raw(path, "status", "outcome", mode="r+")[0:2, 0:2, :] = Outcome.OK.code

    after = [p for p in (path / "status" / "outcome").rglob("*") if p.is_file()]
    assert len([p for p in after if p.name != "zarr.json"]) == 1
    assert _open(path, "status")["outcome"].values[0, 0, 0] == Outcome.OK.code


# --------------------------------------------------------------------------
# Chunking, sharding, and what gets recorded about them
# --------------------------------------------------------------------------


def test_shard_is_one_tile_and_the_chunk_subdivides_it(tmp_path):
    """A shard is exactly one tile, and the chunk divides it evenly.

    Design doc 12.7 makes shard = tile so that a region write is one shard per
    array. Zarr requires the shard to be a whole number of chunks.

    Catches a shard that is not the tile -- a tile write would then touch two
    shards and lose the one-region-per-tile property the write ordering rests on
    -- and a chunk that does not divide the shard, which zarr would refuse only
    for some tile sides.
    """
    path, _ = _fixture(tmp_path)

    for group, name in (
        ("signal", "beta"),
        ("selection", "delta_ic"),
        ("primitives", "log_lik"),
        ("noise", "theta"),
        ("status", "outcome"),
    ):
        array = _raw(path, group, name)
        assert array.shards is not None, name
        assert array.shards[:2] == (2, 2), name
        assert array.shards[2:] == array.shape[2:], name
        for shard, chunk in zip(array.shards, array.chunks, strict=True):
            assert shard % chunk == 0, name


def test_the_recorded_bytes_are_uncompressed_products_not_file_sizes(tmp_path):
    """Recorded chunk and shard bytes are `prod(shape) * itemsize`.

    Hand-derived for `/status/outcome` at tile_side 2, M=2, uint8: a shard is
    2*2*2 = 8 bytes. For `/primitives/log_lik`, float64: 2*2*2*8 = 64 bytes.

    Catches the figure being taken from the file on disk. Both sides of a
    recorded quantity must be in the same unit, and the store's bytes are
    compressed -- Task 6's read-amplification trap in a new place. The recorded
    number is the budget number the "few MB per chunk" target is about.
    """
    path, _ = _fixture(tmp_path)
    recorded = xr.open_zarr(str(path)).attrs["array_bytes"]

    assert recorded["status/outcome"]["shard_bytes"] == 8
    assert recorded["primitives/log_lik"]["shard_bytes"] == 64
    assert recorded["primitives/log_lik"]["chunk_bytes"] <= 64


# --------------------------------------------------------------------------
# What the recompute path needs
# --------------------------------------------------------------------------


def test_the_stored_primitives_alone_can_rank_a_point(tmp_path):
    """`/primitives/` is sufficient input for `rank_candidates`, `n` included.

    Design doc 12.2 lists `log_lik`, `k`, `n_eff_*` and `iterations` and omits
    **`n`**, which `CandidateScores` requires; without it Task 12 would have to
    reopen the input and recount the mask, and 12.8's "recompute without
    refitting" rests on `rank_candidates` needing nothing but stored primitives.

    Values are written, read back through xarray, and ranked. Expected HQIC by
    hand from the documented `HQIC = 2k ln ln n - 2l`: at l = (-100, -95),
    k = (3, 5), n = 100, ln ln 100 = 1.5271796, so HQIC = (209.1630778,
    205.2717963) and delta = (3.8912815, 0).

    Catches the omission of any primitive the ranking needs -- the store would
    look complete and the recompute path would be unimplementable, discovered
    four tasks later when the schema can no longer change.
    """
    path, _ = _fixture(tmp_path)
    _raw(path, "primitives", "log_lik", mode="r+")[0, 0, :] = [-100.0, -95.0]
    _raw(path, "primitives", "k", mode="r+")[0, 0, :] = [3.0, 5.0]
    _raw(path, "primitives", "n", mode="r+")[0, 0, :] = [100.0, 100.0]
    _raw(path, "primitives", "n_eff_bic", mode="r+")[0, 0, :] = [100.0, 100.0]
    _raw(path, "status", "outcome", mode="r+")[0, 0, :] = Outcome.OK.code

    primitives = _open(path, "primitives")
    status = _open(path, "status")
    scores = CandidateScores(
        labels=tuple(str(v) for v in primitives["m"].values),
        engines=(EngineId.KALMAN,) * 2,
        objectives=(Objective.ML,) * 2,
        loglik=primitives["log_lik"].values[0, 0][None, :],
        k=primitives["k"].values[0, 0][None, :],
        n=primitives["n"].values[0, 0][None, :],
        n_eff=primitives["n_eff_bic"].values[0, 0][None, :],
        outcome=status["outcome"].values[0, 0][None, :],
    )

    ranking = rank_candidates(scores, Criterion.HQIC)

    assert ranking.delta_ic[0, 0] == pytest.approx(3.8912815, rel=1e-6)
    assert ranking.delta_ic[0, 1] == 0.0
    assert ranking.best_index[0] == 1
    assert ranking.ic_best[0] == pytest.approx(205.2717963, rel=1e-9)


# --------------------------------------------------------------------------
# The ragged axis, and what is deliberately absent
# --------------------------------------------------------------------------


def test_the_noise_axis_and_its_columns_come_from_the_builder(tmp_path):
    """`/noise/` is `P_total` long and carries Task 7's five columns.

    Hand-derived for `white` (p=1) beside `white + matern12` (p=3): P_total = 4,
    offsets (0, 1), and the second model's parameters in canonical order
    (matern12 sigma, matern12 rho, white sigma).

    Catches a schema that stubs the offsets or sizes the axis from `M * p_max`
    -- 2*3 = 6 here -- which pads the ragged axis and reintroduces exactly the
    padding-NaN versus failure-NaN ambiguity 12.3 rejects.
    """
    path, _ = _fixture(tmp_path)
    noise = _open(path, "noise")

    assert noise.sizes["p"] == 4
    assert list(noise["noise_offset"].values) == [0, 1]
    assert list(noise["noise_extent"].values) == [1, 3]
    assert list(noise["noise_param_name"].values) == ["sigma", "sigma", "rho", "sigma"]
    assert list(noise["noise_param_term"].values) == [
        "white[0]",
        "matern12[0]",
        "matern12[0]",
        "white[0]",
    ]
    assert list(noise["noise_param_unit"].values) == ["", "", "time", ""]
    assert list(noise["noise_param_model_index"].values) == [0, 1, 1, 1]
    assert json.loads(json.dumps(_open(path, "noise").attrs["legend"]))[
        "transform"
    ] == ["Log"]


def test_detail_is_not_created_and_no_covariance_offsets_are_written(tmp_path):
    """`/detail/` is absent, and so is the offset table that would describe it.

    An uncreated group is a cleaner deferral than an empty one, and an offset
    table for a group that does not exist is a name with a reader on the other
    end -- the same class as a gate that reads as present and is not. The
    triangular extent is exercised in `tests/test_ragged.py`, where it needs no
    store.

    Catches both halves: creating an empty `/detail/`, and writing the
    triangular offsets "for later" beside the noise ones, where the only thing
    telling them apart is which name someone happened to choose. Hand-derived:
    the covariance table for this candidate set would be extents (1, 6) summing
    to 7, so a `noise_offset` of (0, 1) with a `noise_extent` of (1, 3) is the
    noise table and nothing else is present.
    """
    path, _ = _fixture(tmp_path)
    root = zarr.open_group(str(path), mode="r")

    assert "detail" not in list(root.group_keys())
    arrays = {
        f"{group}/{name}"
        for group in root.group_keys()
        for name in _group(path, group).array_keys()
    }
    # `/warmstart/` shares the ragged `p` axis, so it carries the same table:
    # each group is opened separately and one without the offsets cannot be
    # sliced per model. Both are written from a single builder call here, so
    # there is no second derivation to drift.
    assert {name for name in arrays if "offset" in name or "extent" in name} == {
        "noise/noise_offset",
        "noise/noise_extent",
        "warmstart/noise_offset",
        "warmstart/noise_extent",
    }
    assert list(np.asarray(_raw(path, "noise", "noise_extent")[:])) == [1, 3]


def test_the_model_and_criterion_axes_carry_their_labels(tmp_path):
    """Every group carrying `m` or `c` names its own axis.

    The model labels are the canonical spec labels -- `"matern12[0] + white[0]"`,
    not the config's `"white + matern12"` -- and the criteria are in config
    order.

    Catches a positional axis with no names: a reader opening `/selection/`
    would have two criteria and no way to tell which column is AIC, and every
    group is opened separately by `xr.open_zarr(group=...)`, so labels in the
    root alone do not reach it.
    """
    path, _ = _fixture(tmp_path)

    selection = _open(path, "selection")
    assert list(selection["m"].values) == ["white[0]", "matern12[0] + white[0]"]
    assert list(selection["c"].values) == ["aic", "hqic"]
    assert list(_open(path, "primitives")["m"].values) == list(selection["m"].values)
    assert list(_open(path, "status")["m"].values) == list(selection["m"].values)


def test_spatial_coordinates_come_from_the_geometry_components(tmp_path):
    """`y` and `x` are written, with the values the fingerprint was taken over.

    The input's grid is `y = 0, 0.5, 1.0, 1.5` and `x = 0, 0.25, ... 1.25`.

    Catches a store with no spatial coordinates at all -- 12.2's layout lists
    none, and a trend field that cannot be plotted or regridded fails the
    no-metamer read the whole schema is built around -- and catches coordinates
    taken from anywhere other than the components the `fit_hash` rests on.
    """
    signal = _open(_fixture(tmp_path)[0], "signal")

    assert list(signal["y"].values) == [0.0, 0.5, 1.0, 1.5]
    assert list(signal["x"].values) == [0.0, 0.25, 0.5, 0.75, 1.0, 1.25]


# --------------------------------------------------------------------------
# The read a consumer without metamer performs
# --------------------------------------------------------------------------


def test_opening_the_store_emits_no_warning(tmp_path):
    """Plain `xr.open_zarr` is warning-free.

    Measured: an unconsolidated zarr store makes xarray warn and tell the reader
    to consolidate or pass a keyword.

    Catches the metadata not being consolidated at creation. The acceptance
    criterion is a round trip through *plain* `xr.open_zarr`, and a reader who
    must first discover `consolidated=False` is not that reader.
    """
    path, _ = _fixture(tmp_path)

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        dataset = xr.open_zarr(str(path), group="primitives")

    assert dataset.sizes["m"] == 2


@pytest.mark.slow
def test_the_store_opens_in_a_process_that_cannot_import_metamer(tmp_path):
    """Design doc 12.4's acceptance criterion, with its control.

    A subprocess with `PYTHONPATH` unset, run outside the tree, has xarray and
    zarr and cannot import metamer.

    Catches metadata only metamer can interpret -- an unstable dtype, a
    dimension name xarray cannot map, a group that needs a keyword to open. The
    control is the half that can fail: the subprocess asserts metamer really is
    absent, because a store opened by a process that quietly imported it proves
    nothing at all.
    """
    path, _ = _fixture(tmp_path)
    program = textwrap.dedent(
        """
        import sys, importlib.util
        assert importlib.util.find_spec("metamer") is None, "control failed"
        import xarray as xr
        tree = xr.open_datatree(sys.argv[1], engine="zarr")
        print(sorted(tree.groups))
        noise = xr.open_zarr(sys.argv[1], group="noise")
        print(list(noise["noise_param_name"].values))
        print(int(xr.open_zarr(sys.argv[1]).attrs["schema_version"]))
        """
    )
    environment = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    result = subprocess.run(
        [sys.executable, "-c", program, str(path)],
        capture_output=True,
        text=True,
        cwd="/",
        env=environment,
    )

    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert "/noise" in lines[0]
    assert "/completion" in lines[0]
    assert lines[1] == "['sigma', 'sigma', 'rho', 'sigma']"
    assert lines[2] == str(store.SCHEMA_VERSION)


# --------------------------------------------------------------------------
# Provenance
# --------------------------------------------------------------------------


def test_a_geometry_that_was_never_opened_is_refused(tmp_path):
    """Provenance refuses components that are not a fingerprint of an input.

    `geometry_hash({})` returns a well-formed hash of nothing, so a caller that
    skipped stage 4a would get a store whose `fit_hash` is a valid-looking string
    -- and it matches every other store built the same way, which is a resume
    gate that reads as present and is not.

    Catches the entry contract's ordering being broken at the one place a store
    is born.
    """
    uri = _input(tmp_path)
    config_path = tmp_path / "c.toml"
    config_path.write_text(_CONFIG.format(uri=uri))
    config = load(config_path)

    with pytest.raises(ValueError, match="not a fingerprint of an opened input"):
        store.provenance_attrs(
            config,
            geometry_components={},
            thread_limits={"openblas": 1},
            read_amplification=1.0,
            unique_dt_count=2,
            tile_sides={"shared": 338},
        )


def test_provenance_carries_the_components_and_the_rollup_and_they_agree(tmp_path):
    """Root attrs hold both the `geometry_hash` and the components it came from.

    Section 13.3 requires both, because a mismatch has to name the differing
    component from the stored store alone -- "your hash changed" is not
    actionable.

    Catches the rollup being stored without the components, and catches the two
    being taken from different sources: the hash here is recomputed from the
    stored components and must match.
    """
    path, attrs = _fixture(tmp_path)

    stored = xr.open_zarr(str(path)).attrs
    assert stored["geometry_hash"] == attrs["geometry_hash"]
    assert (
        geometry.geometry_hash(stored["geometry_components"]) == stored["geometry_hash"]
    )
    assert sorted(stored["geometry_components"]) == [
        "arrays",
        "calendar",
        "spatial_coordinates",
        "time_coordinate",
        "variable",
    ]


def test_provenance_identities_come_from_the_installed_code(tmp_path):
    """`schema_version`, `algorithm_version` and `registry_version` are stamped.

    All three identify code, not a request, so each must be read from the module
    that defines it.

    Catches any of them being taken from the config -- the defect that put
    `registry_version` in the allowlist reading correctly for the wrong reason,
    and the one that made `metamer_version` fit identity.
    """
    stored = xr.open_zarr(str(_fixture(tmp_path)[0])).attrs

    assert stored["schema_version"] == store.SCHEMA_VERSION
    assert stored["algorithm_version"] == hashing.ALGORITHM_VERSION
    assert stored["registry_version"] == REGISTRY_VERSION
    assert stored["metamer_version"] == metamer.__version__


def test_warm_start_used_is_a_fact_about_the_run_not_the_config(tmp_path):
    """A config that enables warm starts still records `warm_start_used: false`.

    2a has no warm-start machinery at all, so a run under that config used none.

    Catches the field being read off `config.warm_start.enabled`, which would
    write `true` about a run that cannot warm-start -- provenance asserting a
    request as though it were an outcome.
    """
    uri = _input(tmp_path)
    config_path = tmp_path / "c.toml"
    config_path.write_text(_CONFIG.format(uri=uri) + "\n[warm_start]\nenabled = true\n")
    config = load(config_path)
    assert config.warm_start.enabled is True

    attrs = store.provenance_attrs(
        config,
        geometry_components=geometry.geometry_components(open_input(uri, "sla")),
        thread_limits={"openblas": 1},
        read_amplification=1.0,
        unique_dt_count=2,
        tile_sides={"shared": 338},
    )

    assert attrs["warm_start_used"] is False


# --------------------------------------------------------------------------
# Refusals
# --------------------------------------------------------------------------


def test_creating_over_an_existing_store_is_refused(tmp_path):
    """A second `create_store` at the same path raises rather than overwriting.

    Catches a rerun silently destroying a finished 10^7-point store: zarr's own
    `overwrite=True` would do exactly that, and the resume path -- not this
    function -- is what reopens one.
    """
    path, attrs = _fixture(tmp_path)
    config = load(tmp_path / "c.toml")

    with pytest.raises(FileExistsError, match="created once"):
        store.create_store(
            path,
            specs=config.process_specs(),
            criteria=config.criteria,
            shape=store.StoreShape(n_y=4, n_x=6, n_beta=4, tile_side=2),
            attrs=attrs,
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("n_beta", 1, "n_beta must be at least 2"),
        ("n_y", 0, "n_y must be at least 1"),
        ("tile_side", 0, "tile_side must be at least 1"),
    ],
)
def test_a_degenerate_axis_is_refused(field, value, message):
    """Axis lengths that make assertions vacuous are refused at construction.

    A length-1 axis makes every quantity defined across it constant, so every
    test over it passes against an implementation that never writes anything --
    the argument the plan makes for M=2 and C=2, applied to the axis the plan
    does not mention.

    Catches a store created with `n_beta = 1`, where `/signal/`'s whole model
    axis would be exercised at the one width that cannot be wrong.
    """
    kwargs = {"n_y": 4, "n_x": 6, "n_beta": 4, "tile_side": 2, field: value}

    with pytest.raises(ValueError, match=message):
        store.StoreShape(**kwargs)


def test_a_single_criterion_or_candidate_is_refused(tmp_path):
    """M = 1 and C = 1 are refused at creation, each naming its consequence.

    Catches a store whose `delta_ic` is identically 0 and whose `weight` is
    identically 1, against which every ranking assertion passes without any
    normalization, exclusion or sentinel ever being written.
    """
    path, attrs = _fixture(tmp_path)
    config = load(tmp_path / "c.toml")
    shape = store.StoreShape(n_y=4, n_x=6, n_beta=4, tile_side=2)

    with pytest.raises(ValueError, match="at least 2 criteria"):
        store.create_store(
            tmp_path / "one_c.zarr",
            specs=config.process_specs(),
            criteria=("aic",),
            shape=shape,
            attrs=attrs,
        )
    with pytest.raises(ValueError, match="at least 2 candidates"):
        store.create_store(
            tmp_path / "one_m.zarr",
            specs=config.process_specs()[:1],
            criteria=config.criteria,
            shape=shape,
            attrs=attrs,
        )


def test_a_missing_provenance_key_is_refused(tmp_path):
    """Creation refuses attrs missing a required key, naming it.

    Catches a store created from a hand-built mapping that omits `fit_hash` or
    the candidate spec hashes -- both are gates the resume path reads, and their
    absence surfaces only at the resume, when the fits are already paid for.
    """
    path, attrs = _fixture(tmp_path)
    config = load(tmp_path / "c.toml")
    thinned = {k: v for k, v in attrs.items() if k != "fit_hash"}

    with pytest.raises(ValueError, match="fit_hash"):
        store.create_store(
            tmp_path / "thin.zarr",
            specs=config.process_specs(),
            criteria=config.criteria,
            shape=store.StoreShape(n_y=4, n_x=6, n_beta=4, tile_side=2),
            attrs=thinned,
        )


@pytest.mark.slow
def test_the_root_attrs_are_byte_identical_across_processes(tmp_path):
    """Provenance does not depend on `PYTHONHASHSEED`.

    Attrs are JSON written once at creation and compared by the resume gate in
    another process, so a mapping built by iterating a set is stable within a
    process and unstable between them -- the one defect class an in-process suite
    cannot reach.

    Catches a set or a hash-ordered mapping entering the attrs.
    """
    uri = _input(tmp_path)
    config_path = tmp_path / "c.toml"
    config_path.write_text(_CONFIG.format(uri=uri))
    program = textwrap.dedent(
        """
        import json, sys
        from metamer.batch import geometry, store
        from metamer.batch.input import open_input
        from metamer.config import load

        config = load(sys.argv[1])
        attrs = store.provenance_attrs(
            config,
            geometry_components=geometry.geometry_components(
                open_input(sys.argv[2], "sla")
            ),
            thread_limits={"openblas": 1, "openmp": 1},
            read_amplification=1.0,
            unique_dt_count=2,
            tile_sides={"shared": 338, "per_point": 186},
        )
        print(json.dumps(attrs, sort_keys=False))
        """
    )
    source_root = str(Path(metamer.__file__).resolve().parents[1])
    runs = [
        subprocess.run(
            [sys.executable, "-c", program, str(config_path), uri],
            capture_output=True,
            text=True,
            check=True,
            env={**os.environ, "PYTHONHASHSEED": seed, "PYTHONPATH": source_root},
        ).stdout
        for seed in ("1", "2")
    ]

    assert runs[0] == runs[1]
    assert json.loads(runs[0])["schema_version"] == store.SCHEMA_VERSION
