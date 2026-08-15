"""Phase 2a's sixteen exit criteria, checked from outside the code that satisfies them.

**THE SUITE'S OWN FAILURE MODE IS BEING A ROLL-UP.** A criterion checked by
calling the helper the implementing task's test called shares its whole
derivation with the subject -- pre-flight (j) -- so it asserts the criterion
rather than verifying it. Every check here is driven from the outside where one
exists: a subprocess, a killed process, a store read back from disk, a plain
`xr.open_zarr` in an environment without metamer.

**Six of the sixteen are cross-process or cross-store properties no single
task's tests can express**, which is why this is a task and not a formality:
1 (kill and resume), 2 (two budgets, two thread counts), 3 (no metamer),
5 (the whole resume taxonomy), 15 and 16 (the recomputed store).

The closing table -- met, met with reduced scope, deferred -- is in
`PROGRESS.md` and in the plan, not here; what is here is the evidence.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import xarray as xr
import zarr

from metamer.batch.completion import completed_tiles
from metamer.batch.ragged import (
    build_ragged_index,
    covariance_extent,
    noise_extent,
)
from metamer.batch.run import run
from metamer.batch.store import SCHEMA_VERSION
from metamer.batch.validation import ExitCode, ValidationError
from metamer.batch.write import check_status_invariant
from metamer.config import load
from metamer.core.outcomes import Outcome
from tests.conftest import RaisingStubEngine

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")

#: `tile_side = 1` at this fixture's geometry, so a 2x2 grid is four tiles --
#: enough for a kill to land between them and for a resume to have something to
#: skip. See `test_completion.py` for the measurement.
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

#: `tile_side = 2`: the same grid in one tile, which is criterion 2's second
#: memory budget.
FOUR_POINTS_PER_TILE = 0.001020258

_CONFIG = """
data_uri = "{uri}"
variable = "sla"
signal_terms = ["constant", "trend", "annual"]
candidates = ["white", "white + matern12"]
criteria = {criteria}
memory_budget_gb = {budget}
objective = "reml"
threads = {threads}
"""


def _input(directory: Path, *, n_time: int = 60) -> str:
    """A 2x2 zarr input of white noise with one short series.

    The point at `(0, 0)` keeps six samples. Under REML `n = n_obs -
    design_rank = 2`, so HQIC is undefined there and AIC is not: criterion 13.
    Fitting `white + matern12` to white noise leaves the correlated candidate
    degenerate at most points, which is criterion 14.

    Args:
        directory: Destination directory.
        n_time: Series length.

    Returns:
        The store URI.
    """
    rng = np.random.default_rng(0)
    values = rng.standard_normal((n_time, 2, 2)).astype("float32")
    values[6:, 0, 0] = np.nan
    origin = np.datetime64("2000-01-01")
    axis = np.array([origin + np.timedelta64(31 * i, "D") for i in range(n_time)])
    xr.Dataset(
        {"sla": (("time", "y", "x"), values)},
        coords={
            "time": axis,
            "y": np.arange(2, dtype="float64"),
            "x": np.arange(2, dtype="float64"),
        },
    ).to_zarr(directory / "in.zarr")
    return str(directory / "in.zarr")


def _config(
    directory: Path,
    uri: str,
    *,
    name: str = "c.toml",
    criteria: str = '["aic", "hqic"]',
    budget: float = ONE_POINT_PER_TILE,
    threads: int = 1,
) -> Path:
    """Write a configuration.

    Args:
        directory: Destination directory.
        uri: The input store.
        name: File name.
        criteria: TOML list literal.
        budget: `memory_budget_gb`.
        threads: Requested thread count.

    Returns:
        The config path.
    """
    path = directory / name
    path.write_text(
        _CONFIG.format(uri=uri, criteria=criteria, budget=budget, threads=threads)
    )
    return path


def _digest(store: Path) -> dict[str, str]:
    """Hash every file in a store, by relative path.

    **Bytes, not values.** Criterion 1 says byte-identical, and a comparison of
    decoded arrays would pass over a chunk written with different compression
    settings, a metadata document whose keys moved, or an attr that acquired a
    timestamp.

    Args:
        store: The store to digest.

    Returns:
        Relative path to SHA-256, for every file.
    """
    digests: dict[str, str] = {}
    for path in sorted(store.rglob("*")):
        if path.is_file():
            digests[str(path.relative_to(store))] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    return digests


#: Root attrs that record a MEASUREMENT OF THE PROCESS rather than a property
#: of the run, and therefore cannot be part of a byte-identity claim about the
#: run's output. **Naming them is the whole point**: a key that varies and is
#: not here fails criterion 1, and the criterion keeps its force for everything
#: else. `floor` is measured fresh every run and deliberately never cached
#: (Phase 2b Task 1), so two runs of one configuration record two different
#: byte counts -- which is correct behaviour and an honest difference.
_MEASURED_ATTRS = frozenset({"floor"})


def _attrs(store: Path) -> dict[str, Any]:
    """Read a store's root attrs.

    Args:
        store: The store to read.

    Returns:
        The root attrs mapping.
    """
    return dict(zarr.open_group(str(store), mode="r").attrs)


def _group(store: Path, name: str) -> xr.Dataset:
    """Open one group with xarray.

    Args:
        store: The store.
        name: Group name.

    Returns:
        The group.
    """
    return xr.open_zarr(store, group=name)


def _values(store: Path) -> dict[str, bytes]:
    """Every gridded array's raw buffer, by `group/name`.

    Used where the two stores are not expected to be byte-identical **on disk**
    -- different tile sizes give different chunk geometry -- but their values
    must be bit-for-bit equal. `tobytes()` distinguishes `-0.0` from `0.0` and
    two NaN payloads, which `assert_array_equal` does not.

    Args:
        store: The store.

    Returns:
        Name to buffer.
    """
    out: dict[str, bytes] = {}
    for group_name in ("signal", "primitives", "noise", "status", "selection"):
        dataset = _group(store, group_name)
        for name, array in dataset.data_vars.items():
            if array.dims[:2] == ("y", "x"):
                out[f"{group_name}/{name}"] = np.ascontiguousarray(
                    array.values
                ).tobytes()
    return out


def _run_cli(
    config: Path, store: Path, *extra: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Invoke `python -m metamer`.

    Args:
        config: Config path.
        store: Store path.
        *extra: Further arguments.
        env: Environment override.

    Returns:
        The finished process.
    """
    return subprocess.run(
        [sys.executable, "-m", "metamer", str(config), str(store), *extra],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


@pytest.fixture(scope="module")
def fitted(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, str, Path, Path]:
    """One complete four-tile store, its input, and the config that made it.

    **One input and one config file for the whole module**, because criterion 1
    compares bytes: a second input at a different path would change `data_uri`,
    hence `run_hash`, hence the attrs -- a difference that would read as
    nondeterminism in the write path and is nothing of the kind.

    Args:
        tmp_path_factory: pytest's directory factory.

    Returns:
        `(directory, input uri, config path, store path)`.
    """
    base = tmp_path_factory.mktemp("criteria")
    uri = _input(base)
    config = _config(base, uri)
    store = base / "fitted.zarr"
    report = run(config, store)
    assert report.tiles_total == 4
    assert report.tiles_written == 4
    return base, uri, config, store


@pytest.fixture
def store_copy(fitted: tuple[Path, str, Path, Path], tmp_path: Path) -> Path:
    """A private copy of the fitted store.

    Args:
        fitted: The module's completed run.
        tmp_path: This test's directory.

    Returns:
        The copy's path.
    """
    copy = tmp_path / "store.zarr"
    shutil.copytree(fitted[3], copy)
    return copy


# --------------------------------------------------------------------------
# 1 -- kill and resume produces a byte-identical store
# --------------------------------------------------------------------------


@pytest.mark.slow
def test_criterion_1_a_killed_and_resumed_run_is_byte_identical(
    fitted: tuple[Path, str, Path, Path], tmp_path: Path
) -> None:
    """`kill -9` mid-run, resume, and the bytes match an uninterrupted run.

    **SIGKILL, not SIGTERM**: the flush path is Task 10's and is tested there.
    This is the case where the process gets no chance to do anything -- the
    store is whatever the last completed region write left, and the resume must
    reach the same bytes as if nothing had happened.

    **Byte-identical rather than equivalent**, which is what makes it worth
    running: anything nondeterministic reaching the store -- a timestamp, a
    dictionary order, a differently formatted float in an attr -- surfaces here
    and nowhere else, and it is much cheaper to find now than in 2c, where warm
    starting adds nondeterminism of its own.

    Catches a resume that rewrites a completed tile with different bytes, and
    any provenance field that varies between two runs of one configuration.

    **ONE PROVENANCE KEY IS EXCLUDED, AND FINDING THAT OUT COST THIS TEST A
    FAILURE (2026-08-15, Phase 2b Task 1).** `floor` is **measured fresh every
    run and deliberately never cached**, so two runs of one configuration record
    two different byte counts and the root `zarr.json` differs -- while every
    array, every chunk and every other attr is identical. **Two settled
    requirements that cannot both hold as stated**: a measurement of the process
    cannot be part of a byte-identity claim about the run's output, and (a5) is
    exactly this shape -- a requirement and the constraint that forbids it,
    written paragraphs apart and both correct.

    **The resolution keeps the criterion's force rather than the sentence.**
    Every file is still compared byte for byte, including the root document's
    structure; the root ATTRS are then compared key by key with the measured
    keys named and excluded, and **the excluded keys are asserted present in
    both stores**, so "excluded" cannot silently become "absent". A key that
    varies and is not in `_MEASURED_ATTRS` still fails.
    """
    _base, _uri, config, reference = fitted
    store = tmp_path / "killed.zarr"
    child = subprocess.Popen(
        [sys.executable, "-m", "metamer", str(config), str(store)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    deadline = time.monotonic() + 120.0
    while time.monotonic() < deadline:
        try:
            if store.exists() and completed_tiles(store).any():
                break
        except ValidationError:
            pass
        if child.poll() is not None:
            break
        time.sleep(0.02)
    child.send_signal(signal.SIGKILL)
    child.communicate(timeout=120)

    assert child.returncode == -signal.SIGKILL
    partial = completed_tiles(store)
    assert partial.any() and not partial.all()

    finished = _run_cli(config, store)

    assert finished.returncode == ExitCode.OK, finished.stderr
    assert completed_tiles(store).all()

    # Everything except the root document, byte for byte. This is where a
    # rewritten chunk, a moved metadata key or a differently formatted float
    # would surface, and none of it is excluded.
    resumed_files = _digest(store)
    reference_files = _digest(reference)
    assert set(resumed_files) == set(reference_files)
    assert {
        name: value for name, value in resumed_files.items() if name != "zarr.json"
    } == {name: value for name, value in reference_files.items() if name != "zarr.json"}

    # ...then the root attrs, key by key, with the measured keys named.
    resumed_attrs = _attrs(store)
    reference_attrs = _attrs(reference)
    assert set(resumed_attrs) == set(reference_attrs)
    # The exclusion is not an absence: both stores carry it, and it differs,
    # which is what makes the exclusion necessary rather than convenient.
    for key in _MEASURED_ATTRS:
        assert key in resumed_attrs and key in reference_attrs
    assert {
        key: value for key, value in resumed_attrs.items() if key not in _MEASURED_ATTRS
    } == {
        key: value
        for key, value in reference_attrs.items()
        if key not in _MEASURED_ATTRS
    }


# --------------------------------------------------------------------------
# 2 -- identical output across two memory budgets and two thread counts
# --------------------------------------------------------------------------


@pytest.mark.slow
def test_criterion_2_the_budget_does_not_move_a_single_bit(
    fitted: tuple[Path, str, Path, Path], tmp_path: Path
) -> None:
    """Four one-point tiles against one four-point tile, bit for bit.

    **This half is currently trivial and is pinned anyway.** No cross-point
    dependency exists in 2a -- every point is fitted cold, so the tiling cannot
    reach the numbers. **It stops being trivial in 2c**, where a warm start
    makes a point's result depend on its neighbours and therefore on which tile
    it landed in, and this test is what makes that regression visible instead of
    plausible.

    The stores are not byte-identical on disk and must not be: different tile
    sizes give different shard geometry. The comparison is over decoded buffers.

    Catches a tiling that reaches the arithmetic -- today only through a bug,
    tomorrow through a feature.
    """
    _base, uri, _config_path, reference = fitted
    other = tmp_path / "one_tile.zarr"

    report = run(_config(tmp_path, uri, budget=FOUR_POINTS_PER_TILE), other)

    assert report.tile_side == 2
    assert report.tiles_total == 1
    assert _values(other) == _values(reference)


@pytest.mark.slow
def test_criterion_2_the_thread_count_does_not_move_a_single_bit(
    fitted: tuple[Path, str, Path, Path], tmp_path: Path
) -> None:
    """The half that is not trivial now.

    A `float64` reduction inside a `prange` over a tile reassociates with the
    thread count, so the sum changes in its last bits and every criterion
    difference downstream moves with it. Nothing else in this suite would catch
    that.

    Catches exactly that reassociation, and any parallel path that reduces over
    series rather than within one.
    """
    _base, uri, _config_path, reference = fitted
    other = tmp_path / "threads.zarr"

    report = run(_config(tmp_path, uri, threads=2), other)

    assert report.config.threads == 2
    assert _values(other) == _values(reference)


# --------------------------------------------------------------------------
# 3 -- the store round-trips through plain xr.open_zarr, warning-free
# --------------------------------------------------------------------------


@pytest.mark.slow
def test_criterion_3_the_store_opens_cleanly_without_metamer(
    fitted: tuple[Path, str, Path, Path],
) -> None:
    """Plain means warning-free, and without metamer means without `PYTHONPATH`.

    **Two traps, both already paid for once in this project.** `PYTHONPATH=src`
    is inherited by subprocesses, so a "clean" child imports metamer out of the
    development tree and passes for the wrong reason -- the control asserts the
    module is genuinely absent. And an unconsolidated store *opens*: it warns,
    through the `warnings` module, and tells the reader to pass a keyword. "It
    opened" and "it opened cleanly" are different acceptance bars, so the child
    promotes warnings to errors around every open.

    Catches metadata that stops being consolidated -- which is what any later
    task that creates an array or writes an attr will do -- and any array whose
    dtype xarray cannot decode unaided.
    """
    _base, _uri, _config_path, store = fitted

    program = textwrap.dedent(
        """
        import sys, importlib.util, warnings
        assert importlib.util.find_spec("metamer") is None, "control failed"
        import numpy as np, xarray as xr
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            groups = {
                name: xr.open_zarr(sys.argv[1], group=name)
                for name in (
                    "signal", "primitives", "noise", "status", "selection",
                    "warmstart", "completion",
                )
            }
        print(sorted(groups))
        print(int(np.isfinite(groups["primitives"]["log_lik"].values).sum()))
        print(list(groups["selection"]["c"].values))
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", program, str(store)],
        capture_output=True,
        text=True,
        cwd="/",
        env={k: v for k, v in os.environ.items() if k != "PYTHONPATH"},
    )

    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert "completion" in lines[0] and "selection" in lines[0]
    assert int(lines[1]) > 0
    assert lines[2] == "['aic', 'hqic']"


# --------------------------------------------------------------------------
# 4 -- the status/value invariant, over a finished store
# --------------------------------------------------------------------------


def test_criterion_4_the_invariant_holds_over_the_finished_store(
    fitted: tuple[Path, str, Path, Path],
) -> None:
    """Both directions, read back from disk, with the same function.

    The write path checks the arrays it is **about to write**; this checks what
    a reader **gets back**, which is a different input to the same function --
    and it is the same function deliberately, so the two cannot drift.

    The three unreachable members are recorded rather than asserted absent by
    accident: `SCREENED_OUT` needs the Whittle engine and the screening block,
    `CANDIDATE_DROPPED` needs 14.1's early abort, and `NOT_APPLICABLE` needs a
    declared domain mask in 13.6's input contract. Their codes are fixed at 12,
    9 and 13 regardless, because stored code meanings are fixed at creation.

    Catches a store that reads back differently from what was written -- a fill
    value that collides with a real one, a dtype that decodes with a different
    NaN payload -- and any of the three unreachable members becoming producible
    without the note being revisited.
    """
    _base, _uri, _config_path, store = fitted
    primitives = _group(store, "primitives")
    status = _group(store, "status")
    outcome = status["outcome"].values.reshape(-1, status["outcome"].shape[-1])

    def flat(name: str) -> np.ndarray:
        """Read one primitive as `(B, M)`.

        Args:
            name: Array name.

        Returns:
            The values.
        """
        return primitives[name].values.reshape(outcome.shape)

    check_status_invariant(
        outcome.astype(np.uint8),
        {
            "log_lik": flat("log_lik"),
            "k": flat("k"),
            "n": flat("n"),
            "n_eff_bic": flat("n_eff_bic"),
        },
    )

    present = {int(code) for code in np.unique(outcome)}
    assert Outcome.OK.code in present
    assert Outcome.NOT_ATTEMPTED.code not in present
    unreachable = {
        Outcome.SCREENED_OUT.code,
        Outcome.CANDIDATE_DROPPED.code,
        Outcome.NOT_APPLICABLE.code,
    }
    assert not (present & unreachable)


# --------------------------------------------------------------------------
# 5 -- the resume taxonomy, all five arms plus the exit-4 source
# --------------------------------------------------------------------------


@pytest.mark.slow
def test_criterion_5_every_arm_of_the_resume_taxonomy(
    fitted: tuple[Path, str, Path, Path], store_copy: Path, tmp_path: Path
) -> None:
    """Six refusals and one acceptance, over one finished store.

    Each arm is exercised against a store this suite fitted, rather than against
    a fixture built to be refused -- which is the difference between checking
    the gate and checking the test's own construction. The arms: a criterion-set
    change, a `fit_hash` mismatch, a `/detail/` change, a wrong candidate at
    index 1 naming the index, an incomplete source refused with exit code 4, and
    the recompute into a new store with no fit.

    Catches any arm that stops refusing -- each would produce a store that is
    wrong in a way no invariant catches -- and the taxonomy collapsing to fewer
    arms than it claims.
    """
    _base, uri, _config_path, _store = fitted
    engine = RaisingStubEngine()
    refusals: dict[str, str] = {}

    with pytest.raises(ValidationError) as criterion_change:
        run(_config(tmp_path, uri, criteria='["aic"]', name="a.toml"), store_copy)
    refusals["criteria"] = str(criterion_change.value)

    other = tmp_path / "other.toml"
    other.write_text(
        _CONFIG.format(
            uri=uri, criteria='["aic", "hqic"]', budget=ONE_POINT_PER_TILE, threads=1
        ).replace('objective = "reml"', 'objective = "ml"')
    )
    with pytest.raises(ValidationError) as fit_change:
        run(other, store_copy, engine=engine)
    refusals["fit_hash"] = str(fit_change.value)

    detail = tmp_path / "detail.toml"
    detail.write_text(
        _CONFIG.format(
            uri=uri, criteria='["aic", "hqic"]', budget=ONE_POINT_PER_TILE, threads=1
        )
        + '\n[detail]\nsubsample = "none"\n'
    )
    with pytest.raises(ValidationError) as detail_change:
        run(detail, store_copy, engine=engine)
    refusals["detail"] = str(detail_change.value)

    candidates = tmp_path / "candidates.toml"
    candidates.write_text(
        _CONFIG.format(
            uri=uri, criteria='["aic", "hqic"]', budget=ONE_POINT_PER_TILE, threads=1
        ).replace(
            'candidates = ["white", "white + matern12"]',
            'candidates = ["white", "matern32"]',
        )
    )
    with pytest.raises(ValidationError) as candidate_change:
        run(candidates, store_copy, engine=engine)
    refusals["candidates"] = str(candidate_change.value)

    assert "aic" in refusals["criteria"] and "--reuse-fits-from" in refusals["criteria"]
    assert "fit_hash" in refusals["fit_hash"]
    assert "detail" in refusals["detail"]
    assert "index 1" in refusals["candidates"]
    assert engine.calls == []


# --------------------------------------------------------------------------
# 6 and 7 -- memory
# --------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.machine
def test_criteria_6_and_7_peak_rss_is_bounded_and_does_not_track_the_grid(
    fitted: tuple[Path, str, Path, Path], tmp_path: Path
) -> None:
    """What is measurable at test scale, with the reduced scope stated.

    **THE CRITERIA ARE ABOUT A 10^7-POINT RUN AND THIS SUITE FITS FOUR SERIES.**
    Peak RSS of any process that has imported numpy, xarray and zarr is hundreds
    of MB before a tile exists, so "peak at or below the budget" is satisfied by
    the interpreter alone at any budget above that baseline. Both criteria are
    reported as met **with reduced scope** for that reason.

    What this does check, in a fresh process each time and therefore free of the
    session's watermark: the run stays under a budget well below available RAM,
    and **peak RSS does not track the grid** -- four one-point tiles and one
    four-point tile land within a few MB of each other. A run whose peak scaled
    with the grid rather than with the tile would separate them.

    Catches a tiling loop that accumulates per-tile state instead of releasing
    it, which is the defect the budget exists to prevent and the one that only
    a multi-tile run can show.
    """
    _base, uri, _config_path, _store = fitted
    program = textwrap.dedent(
        """
        import sys
        from metamer.batch.run import run
        from metamer.core import machine
        report = run(sys.argv[1], sys.argv[2])
        print(report.tiles_total)
        print(machine.peak_rss_bytes())
        """
    )

    def peak(config: Path, store: Path) -> tuple[int, float]:
        """Run in a fresh process and report its watermark.

        Args:
            config: Config path.
            store: Store path.

        Returns:
            `(tiles, peak bytes)`.
        """
        result = subprocess.run(
            [sys.executable, "-c", program, str(config), str(store)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        tiles, watermark = result.stdout.splitlines()[-2:]
        return int(tiles), float(watermark)

    many_tiles, many_peak = peak(
        _config(tmp_path, uri, name="small.toml"), tmp_path / "many.zarr"
    )
    one_tile, one_peak = peak(
        _config(tmp_path, uri, name="big.toml", budget=FOUR_POINTS_PER_TILE),
        tmp_path / "one.zarr",
    )

    assert many_tiles == 4
    assert one_tile == 1
    budget_bytes = 1.0 * 1024**3
    assert many_peak < budget_bytes
    assert one_peak < budget_bytes
    assert abs(many_peak - one_peak) < 64e6


# --------------------------------------------------------------------------
# 8 -- the bitmap is never set ahead of the data
# --------------------------------------------------------------------------


@pytest.mark.slow
def test_criterion_8_every_set_bit_in_a_killed_store_has_its_data(
    fitted: tuple[Path, str, Path, Path], tmp_path: Path
) -> None:
    """The ordering property, checked over a store nobody wrote deliberately.

    Task 10 demonstrates the ordering with an injected fault, which is the only
    way to *choose* the moment. This checks the resulting invariant over a store
    killed at a moment nobody chose: **for every set bit, that tile's region
    carries data**. The assertion holds whatever the timing, so it is not a
    race -- what varies is only how much of the store is filled.

    Catches a bit set before its region write returns, which an injected fault
    at one point could miss if some other path set bits too.
    """
    _base, _uri, config, _store = fitted
    store = tmp_path / "killed.zarr"
    child = subprocess.Popen(
        [sys.executable, "-m", "metamer", str(config), str(store)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    deadline = time.monotonic() + 120.0
    while time.monotonic() < deadline:
        try:
            if store.exists() and completed_tiles(store).any():
                break
        except ValidationError:
            pass
        if child.poll() is not None:
            break
        time.sleep(0.01)
    child.send_signal(signal.SIGKILL)
    child.communicate(timeout=120)

    done = completed_tiles(store)
    assert done.any()
    outcome = _group(store, "status")["outcome"].values
    for ty, tx in zip(*np.nonzero(done), strict=True):
        assert np.all(outcome[ty, tx] != Outcome.NOT_ATTEMPTED.code)


# --------------------------------------------------------------------------
# 9 -- geometry_hash moves with the geometry and not with the values
# --------------------------------------------------------------------------


@pytest.mark.slow
def test_criterion_9_the_geometry_hash_moves_only_with_the_geometry(
    tmp_path: Path,
) -> None:
    """A value edit at fixed geometry does not move it; a grid change does.

    Both halves through `run` rather than through the hashing function, because
    the criterion is about what a **run** fingerprints: the pair `data_uri` used
    to stand in for was wrong in both directions at once -- moving a file
    invalidated a valid resume, editing one in place permitted an invalid one.

    Catches a fingerprint taken from the configuration rather than from the
    opened dataset, which is exactly what `data_uri` was.
    """
    edited = tmp_path / "edited"
    edited.mkdir()
    uri = _input(edited)
    config = _config(edited, uri, budget=FOUR_POINTS_PER_TILE)
    first = run(config, tmp_path / "a.zarr")

    dataset = xr.open_zarr(uri).load()
    dataset["sla"].values[0, 1, 1] += 1.0
    shutil.rmtree(uri)
    dataset.to_zarr(uri)
    second = run(config, tmp_path / "b.zarr")

    assert second.geometry_hash == first.geometry_hash

    wider = tmp_path / "wider"
    wider.mkdir()
    rng = np.random.default_rng(1)
    xr.Dataset(
        {
            "sla": (
                ("time", "y", "x"),
                rng.standard_normal((60, 3, 2)).astype("float32"),
            )
        },
        coords={
            "time": dataset["time"].values,
            "y": np.arange(3, dtype="float64"),
            "x": np.arange(2, dtype="float64"),
        },
    ).to_zarr(wider / "in.zarr")
    third = run(
        _config(wider, str(wider / "in.zarr"), budget=FOUR_POINTS_PER_TILE),
        tmp_path / "c.zarr",
    )

    assert third.geometry_hash != first.geometry_hash


# --------------------------------------------------------------------------
# 10 and 11 -- thread limits, and the entry contract's ordering
# --------------------------------------------------------------------------


def test_criterion_10_observed_thread_limits_are_reported_per_library(
    fitted: tuple[Path, str, Path, Path], tmp_path: Path
) -> None:
    """Observed, per library, and a mismatch is a layer-3 failure.

    The run **observes** rather than asserting: requesting 1000 threads leaves
    OpenBLAS reporting its build-time 128 while numba raises, so a request is
    not a result. The mismatch arm is constructed with an observation this
    machine cannot produce, which is what the `observed_thread_limits` seam
    exists for.

    Catches a report that echoes the request, and a mismatch that raises
    something other than a staged layer-3 failure.
    """
    _base, uri, _config_path, _store = fitted
    config = _config(tmp_path, uri, name="threads.toml", budget=FOUR_POINTS_PER_TILE)

    with pytest.raises(ValidationError) as mismatch:
        run(
            config,
            tmp_path / "mismatch.zarr",
            observed_thread_limits={"openblas": 4, "numba": 1},
            engine=RaisingStubEngine(),
        )

    assert "layer 3" in str(mismatch.value)
    assert "openblas" in str(mismatch.value)


@pytest.mark.slow
def test_criterion_11_the_entry_contract_order_is_tested_not_trusted(
    store_copy: Path, tmp_path: Path
) -> None:
    """Layer 4 is reported for a run whose config would also be refused.

    The configuration names a variable the input does not have, so stage 4a
    fails -- **and** `variable` is fit-relevant, so the resume gate would refuse
    it too. Only one of the two can be reported, and which one says whether the
    fingerprint was taken from the data or from the config.

    Driven through the command line, so what is asserted is the exit code and
    the layer prefix a user sees rather than an exception type.

    Catches a gate hoisted above stage 4a, which reports "layer 3" for a run
    whose real fault is in the data and sends the user to the wrong file.
    """
    absent = tmp_path / "absent.toml"
    absent.write_text(
        _CONFIG.format(
            uri=str(tmp_path / "missing.zarr"),
            criteria='["aic", "hqic"]',
            budget=ONE_POINT_PER_TILE,
            threads=1,
        ).replace('variable = "sla"', 'variable = "nope"')
    )

    result = _run_cli(absent, store_copy)

    assert result.returncode == ExitCode.DATA_INVALID
    assert "layer 4 (data)" in result.stderr


# --------------------------------------------------------------------------
# 12 -- the ragged builder, on a fixture that discriminates the two extents
# --------------------------------------------------------------------------


def test_criterion_12_both_extent_functions_on_a_discriminating_fixture(
    tmp_path: Path,
) -> None:
    """`p_m` against `p_m(p_m+1)/2`, where the two disagree.

    **The M=2 store fixture does not discriminate them**: `p = 0` and `p = 1`
    are the fixed points of `p -> p(p+1)/2`, so `white` first gives `(0, 1)`
    under both. Hand-derived here from `p = (1, 3, 2)` for
    `white / white + matern12 / matern32`: offsets `(0, 1, 4)` with totals 6
    under `noise_extent`, and `(0, 1, 7)` with total 10 under `covariance_extent`.

    **The candidate list comes through a real config file**, because
    `config.load` is the only constructor a run uses and a `Config` built inline
    has not been through `tomllib`, pydantic or the flattening.

    Catches a builder that computes one offset table and reuses it for the other
    axis -- which passes every assertion a non-discriminating fixture can make.
    """
    path = tmp_path / "three.toml"
    path.write_text(
        """
data_uri = "unused.zarr"
variable = "sla"
signal_terms = ["constant"]
candidates = ["white", "white + matern12", "matern32"]
criteria = ["aic"]
"""
    )
    specs = list(load(path).process_specs())

    noise = build_ragged_index(specs, noise_extent)
    detail = build_ragged_index(specs, covariance_extent)

    assert noise.offsets_array().tolist() == [0, 1, 4]
    assert noise.total == 6
    assert detail.offsets_array().tolist() == [0, 1, 7]
    assert detail.total == 10


# --------------------------------------------------------------------------
# 13 and 14 -- the two fixture points
# --------------------------------------------------------------------------


def test_criterion_13_a_point_is_ok_while_one_criterion_cannot_rank_it(
    fitted: tuple[Path, str, Path, Path],
) -> None:
    """NaN delta-IC beside an `OK` status, in a finished store.

    Under REML `n = n_obs - design_rank`, so the six-sample point gives `n = 2`
    and HQIC -- `2k ln ln n` -- is undefined while AIC ranks it. **`outcome` has
    no `c` axis**, so a criterion-specific failure cannot go through the outcome
    ladder without making a criterion-independent array depend on which
    criterion was requested.

    Catches a store that folds the failure into `/status/`, and one that writes
    a winner where no criterion could rank the point.
    """
    _base, _uri, _config_path, store = fitted
    selection = _group(store, "selection")
    status = _group(store, "status")
    criteria = [str(name) for name in selection["c"].values]
    hqic = criteria.index("hqic")

    assert status["outcome"].values[0, 0, 0] == Outcome.OK.code
    assert np.isnan(selection["ic_best"].values[0, 0, hqic])
    assert np.all(np.isnan(selection["delta_ic"].values[0, 0, :, hqic]))
    assert selection["selected"].values[0, 0, hqic] == -1
    assert np.isfinite(selection["ic_best"].values[0, 0, criteria.index("aic")])


def test_criterion_14_a_point_with_one_surviving_candidate(
    fitted: tuple[Path, str, Path, Path],
) -> None:
    """`n_valid = 1`, weights renormalized over the survivor.

    **The case that reads as confident selection and is not**: a weight vector
    summing to 1 over a single candidate, because the other failed rather than
    because the winner was decisive. The construction is an optimizer-stage
    failure -- `white + matern12` on white noise -- and it must be, since in v1
    the design is built once before the candidate loop and a design failure
    cannot distinguish candidates.

    Catches weights normalized over all M rather than over the survivors, which
    would give the failed candidate a share and the survivor less than 1.
    """
    _base, _uri, _config_path, store = fitted
    selection = _group(store, "selection")
    n_valid = selection["n_valid"].values
    weight = selection["weight"].values

    assert np.any(n_valid == 1), "fixture produced no single-survivor point"
    single = n_valid == 1
    weights_there = weight[single][..., 0]
    assert np.allclose(np.nansum(weights_there, axis=-1), 1.0)
    assert np.count_nonzero(weights_there > 0) == np.count_nonzero(single)


# --------------------------------------------------------------------------
# 15 and 16 -- the recomputed store
# --------------------------------------------------------------------------


@pytest.mark.slow
def test_criteria_15_and_16_the_recomputed_store_stands_alone(
    fitted: tuple[Path, str, Path, Path], store_copy: Path, tmp_path: Path
) -> None:
    """Self-contained with the source deleted, and the hashes tell the story.

    Criterion 15 is a claim about a reader that has neither metamer nor the
    source, so the source is **deleted** and the read happens in a subprocess
    with `PYTHONPATH` stripped -- asserting it in-process against a store that
    is still there would pass for a zarr reference.

    Criterion 16 is the whole claim of the three-hash split: `fit_hash` equal to
    the source's, `compat_hash` and `run_hash` not, and the source's three
    hashes recorded so a reader can check the first rather than trust it.

    Catches a recompute that inherits provenance, one that leaves an array
    resolving through the source, and a `fit_hash` that moved when the criterion
    set changed -- which would mean the split separates nothing.
    """
    _base, uri, _config_path, _store = fitted
    source_attrs = json.loads(
        json.dumps(dict(zarr.open_group(str(store_copy), mode="r").attrs))
    )
    new = tmp_path / "recomputed.zarr"

    run(
        _config(tmp_path, uri, criteria='["aic"]', name="recompute.toml"),
        new,
        reuse_fits_from=store_copy,
        engine=RaisingStubEngine(),
    )

    attrs = dict(zarr.open_group(str(new), mode="r").attrs)
    assert attrs["fit_hash"] == source_attrs["fit_hash"]
    assert attrs["compat_hash"] != source_attrs["compat_hash"]
    assert attrs["run_hash"] != source_attrs["run_hash"]
    assert attrs["source_fit_hash"] == source_attrs["fit_hash"]
    assert attrs["source_compat_hash"] == source_attrs["compat_hash"]
    assert attrs["source_run_hash"] == source_attrs["run_hash"]
    assert attrs["schema_version"] == SCHEMA_VERSION

    shutil.rmtree(store_copy)
    program = textwrap.dedent(
        """
        import sys, importlib.util, warnings
        assert importlib.util.find_spec("metamer") is None, "control failed"
        import numpy as np, xarray as xr
        with warnings.catch_warnings():
            warnings.simplefilter("error")
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


def test_criterion_5_an_incomplete_source_exits_four(
    fitted: tuple[Path, str, Path, Path], store_copy: Path, tmp_path: Path
) -> None:
    """The sixth arm of the taxonomy, through the command line.

    A source whose completion bitmap is not fully set would give a
    complete-looking new store whose primitives are fill values wherever the
    source never fitted -- numbers that read as failed fits and were never
    attempted. It is layer 4 because it is a fact about data on disk.

    Catches the check running after the tiling loop, or the layer-4 error being
    mapped to the config-invalid code.
    """
    _base, uri, _config_path, _store = fitted
    group = zarr.open_group(str(store_copy), mode="r+")["completion"]
    assert isinstance(group, zarr.Group)
    tiles = group["tiles"]
    assert isinstance(tiles, zarr.Array)
    tiles[0, 0] = 0
    config = _config(tmp_path, uri, criteria='["aic"]', name="recompute.toml")

    result = _run_cli(
        config, tmp_path / "new.zarr", "--reuse-fits-from", str(store_copy)
    )

    assert result.returncode == ExitCode.DATA_INVALID
    assert "layer 4 (data)" in result.stderr
    assert not (tmp_path / "new.zarr").exists()
