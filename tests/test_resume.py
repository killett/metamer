"""The resume gate: what it compares, what it refuses, and in what order.

**EVERY REFUSAL HERE IS ALSO AN ASSERTION THAT NO FIT RAN.** The gate's value is
that it fires *before* the tiling loop -- a refusal that arrives after ten hours
of fitting is a crash report, not a gate -- and the only honest way to observe
that is the raising stub engine. **The paired positive control lives in
`tests/test_completion.py`**: the same seam, the same store, one clear bit, and
the engine IS reached. Without it "no fit ran" would pass equally well for a
gate that refuses because it cannot open the store at all.

**THE TWO COMPARISONS THAT ARE NOT HASHES ARE THE DANGEROUS ONES.** `candidates`
and the `/detail/` selection are in no hash by design, so nothing but this gate
stands between a resume and a store that is wrong with every array the right
shape. The candidate comparison is **positional**, and the fixture that
separates positional from set-based is a **permutation**.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import xarray as xr
import zarr

from metamer.batch.input import InputContractError
from metamer.batch.run import run
from metamer.batch.store import REQUIRED_ATTRS, SCHEMA_VERSION
from metamer.batch.validation import ExitCode, ValidationError
from tests.conftest import RaisingStubEngine

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")

#: One point, one tile: the gate runs before the tiling loop, so every test here
#: needs a store to exist and none of them needs it to be big.
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
variable = "{variable}"
signal_terms = ["constant", "trend", "annual"]
candidates = {candidates}
criteria = {criteria}
memory_budget_gb = {budget}
objective = "{objective}"

[detail]
subsample = "{subsample}"
"""

STORED_CANDIDATES = '["white", "white + matern12"]'
STORED_CRITERIA = '["aic", "hqic"]'


def _input(directory: Path, *, n_time: int = 60) -> str:
    """A one-point zarr input of white noise.

    Args:
        directory: Destination directory.
        n_time: Series length.

    Returns:
        The store URI.
    """
    rng = np.random.default_rng(0)
    values = rng.standard_normal((n_time, 1, 1)).astype("float32")
    origin = np.datetime64("2000-01-01")
    axis = np.array([origin + np.timedelta64(31 * i, "D") for i in range(n_time)])
    xr.Dataset(
        {"sla": (("time", "y", "x"), values)},
        coords={
            "time": axis,
            "y": np.zeros(1, dtype="float64"),
            "x": np.zeros(1, dtype="float64"),
        },
    ).to_zarr(directory / "in.zarr")
    return str(directory / "in.zarr")


def _config(
    directory: Path,
    uri: str,
    *,
    name: str = "c.toml",
    variable: str = "sla",
    candidates: str = STORED_CANDIDATES,
    criteria: str = STORED_CRITERIA,
    objective: str = "ml",
    subsample: str = "pass1",
    budget: float = ONE_POINT_PER_TILE,
) -> Path:
    """Write a configuration, varying one field at a time.

    Args:
        directory: Destination directory.
        uri: The input store.
        name: File name, so one directory holds several.
        variable: The named variable; a wrong one fails stage 4a.
        candidates: TOML list literal.
        criteria: TOML list literal.
        objective: `ml` or `reml` -- fit-relevant.
        subsample: The `/detail/` selector.
        budget: `memory_budget_gb`.

    Returns:
        The config path.
    """
    path = directory / name
    path.write_text(
        _CONFIG.format(
            uri=uri,
            variable=variable,
            candidates=candidates,
            criteria=criteria,
            objective=objective,
            subsample=subsample,
            budget=budget,
        )
    )
    return path


def _attrs(store: Path) -> dict[str, Any]:
    """Read a store's root attrs.

    Args:
        store: The store.

    Returns:
        The attrs mapping.
    """
    return dict(zarr.open_group(str(store), mode="r").attrs)


@pytest.fixture(scope="module")
def fitted(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, str, Path]:
    """One complete single-point store, and the input it was fitted from.

    Args:
        tmp_path_factory: pytest's directory factory.

    Returns:
        `(directory, input uri, store path)`.
    """
    base = tmp_path_factory.mktemp("resume")
    uri = _input(base)
    store = base / "done.zarr"
    report = run(_config(base, uri), store)
    # FIXTURE GUARD: the gate is only interesting against a store that exists
    # and is complete, so a resume has nothing outstanding and any fit that runs
    # is a fit the gate should have prevented.
    assert report.tiles_written == 1
    return base, uri, store


@pytest.fixture
def store(fitted: tuple[Path, str, Path], tmp_path: Path) -> tuple[str, Path]:
    """A private copy of the fitted store, with its input.

    Args:
        fitted: The module's completed run.
        tmp_path: This test's directory.

    Returns:
        `(input uri, store path)`.
    """
    _base, uri, source = fitted
    copy = tmp_path / "out.zarr"
    shutil.copytree(source, copy)
    return uri, copy


# --------------------------------------------------------------------------
# The green path, which is every refusal's control
# --------------------------------------------------------------------------


def test_an_unchanged_configuration_resumes_and_fits_nothing(
    store: tuple[str, Path], tmp_path: Path, raising_engine: RaisingStubEngine
) -> None:
    """The gate passes what it should, and passes it without refitting.

    **This is the control for every refusal below**, and it is not a formality:
    `Config.criteria` and `candidate_spec_hashes()` are **tuples** and come back
    out of the store's attrs as JSON **lists**, so a comparison written the
    obvious way refuses every resume including the correct one.

    Catches exactly that -- a gate that refuses everything, which looks
    conservative and makes the store unresumable.
    """
    uri, path = store

    report = run(_config(tmp_path, uri), path, engine=raising_engine)

    assert report.tiles_skipped == 1
    assert report.tiles_written == 0
    assert raising_engine.calls == []


# --------------------------------------------------------------------------
# The hashed comparisons
# --------------------------------------------------------------------------


def test_a_fit_relevant_change_is_refused_naming_both_hashes(
    store: tuple[str, Path], tmp_path: Path, raising_engine: RaisingStubEngine
) -> None:
    """Different `fit_hash`, so the stored fits are not reusable.

    `objective` is fit-relevant: ML and REML land on different optima. The
    refusal names both hashes, because a user comparing two stores has nothing
    else to compare.

    Catches a resume that reuses fits from a different objective -- every array
    the right shape, every value finite, and a store whose `/primitives/` were
    produced under a likelihood its own attrs no longer describe.
    """
    uri, path = store
    stored = _attrs(path)["fit_hash"]

    with pytest.raises(ValidationError) as refusal:
        run(
            _config(tmp_path, uri, objective="reml"),
            path,
            engine=raising_engine,
        )

    assert "fit_hash" in str(refusal.value)
    assert stored in str(refusal.value)
    assert raising_engine.calls == []


def test_a_criterion_set_change_is_refused_naming_both_sets(
    store: tuple[str, Path], tmp_path: Path, raising_engine: RaisingStubEngine
) -> None:
    """Dropping a criterion resizes `c`, which is a whole-store rewrite.

    The `c` axis is fixed at creation and has no completion bitmap of its own,
    so an interrupted resize leaves a store that is neither shape. The refusal
    names the stored set, the requested set, and what resolves it.

    Catches a resume that writes two criteria' worth of `/selection/` into a
    one-criterion request or the reverse -- and a refusal that says only "the
    configuration changed", which leaves the user to find which field.
    """
    uri, path = store

    with pytest.raises(ValidationError) as refusal:
        run(
            _config(tmp_path, uri, criteria='["aic"]'),
            path,
            engine=raising_engine,
        )

    message = str(refusal.value)
    assert "aic" in message and "hqic" in message
    assert "new store" in message
    assert raising_engine.calls == []


def test_a_compat_difference_that_is_not_the_criterion_set_is_refused(
    store: tuple[str, Path], tmp_path: Path, raising_engine: RaisingStubEngine
) -> None:
    """The arm with no producer is refused rather than fallen through.

    `COMPAT_RELEVANT_FIELDS` is `FIT_RELEVANT_FIELDS | {"criteria"}`, so no
    configuration in this release can make `compat_hash` differ while
    `fit_hash` and the criterion set both match. The state is reached here by
    editing the stored hash, which is what a future compat-only field would do.

    **The alternative is worse than the refusal**: falling through would resume
    against `/selection/` arrays computed under a policy the configuration no
    longer requests, with no symptom.

    Catches the gate comparing only the fields it knows about, which silently
    accepts every compat-relevant field added after it was written.
    """
    uri, path = store
    root = zarr.open_group(str(path), mode="r+")
    root.attrs["compat_hash"] = "0" * 16

    with pytest.raises(ValidationError) as refusal:
        run(_config(tmp_path, uri), path, engine=raising_engine)

    assert "compat_hash" in str(refusal.value)
    assert raising_engine.calls == []


def test_a_store_written_by_another_schema_version_is_refused(
    store: tuple[str, Path], tmp_path: Path, raising_engine: RaisingStubEngine
) -> None:
    """`schema_version` is checked on resume, per design doc 12.7.

    Catches resuming a store whose stored code meanings differ from this
    release's -- an `Outcome` member added, a fill value changed, an attr the
    gate reads absent -- which reads as a valid store and answers questions
    with a vocabulary the reader does not share.
    """
    uri, path = store
    root = zarr.open_group(str(path), mode="r+")
    root.attrs["schema_version"] = SCHEMA_VERSION - 1

    with pytest.raises(ValidationError) as refusal:
        run(_config(tmp_path, uri), path, engine=raising_engine)

    assert "schema" in str(refusal.value)
    assert raising_engine.calls == []


# --------------------------------------------------------------------------
# The comparisons no hash covers
# --------------------------------------------------------------------------


def test_a_different_candidate_at_index_one_is_refused_naming_the_index(
    store: tuple[str, Path], tmp_path: Path, raising_engine: RaisingStubEngine
) -> None:
    """The positional comparison, at a single changed position.

    `candidates` is in no hash allowlist, deliberately, so nothing else stands
    between this resume and a store where `matern32`'s fits sit in
    `white + matern12`'s slice of the model axis: every array the right shape,
    every value finite, every status `ok`. At unequal `p` -- 3 against 2 -- it
    also shifts every offset on the ragged `/noise/` axis, so the corruption
    lands in two arrays.

    The message names the index and both spec hashes, because "the candidates
    changed" does not tell a user which one to put back.

    Catches the comparison being absent, and one that reports a difference
    without saying where.
    """
    uri, path = store
    stored = list(_attrs(path)["candidate_spec_hashes"])

    with pytest.raises(ValidationError) as refusal:
        run(
            _config(tmp_path, uri, candidates='["white", "matern32"]'),
            path,
            engine=raising_engine,
        )

    message = str(refusal.value)
    assert "index 1" in message
    assert stored[1] in message
    assert raising_engine.calls == []


def test_a_permutation_of_the_stored_candidates_is_refused(
    store: tuple[str, Path], tmp_path: Path, raising_engine: RaisingStubEngine
) -> None:
    """The fixture that separates a positional comparison from a set one.

    A permutation has the same *set* of candidates, the same length and the
    same multiset of spec hashes, so `set(...)`, `sorted(...)` and any
    membership test accept it -- and it is exactly the case that writes each
    candidate's fits into the other's slice. **Two functions that differ in
    general are identical on every fixture except a reordering**, which is why
    this test exists beside the one above rather than instead of it.

    Catches a gate written with `set(stored) == set(requested)`, which is the
    natural spelling and is silent here.
    """
    uri, path = store

    with pytest.raises(ValidationError) as refusal:
        run(
            _config(tmp_path, uri, candidates='["white + matern12", "white"]'),
            path,
            engine=raising_engine,
        )

    assert "index 0" in str(refusal.value)
    assert raising_engine.calls == []


def test_a_strict_superset_of_the_candidates_is_refused_in_place(
    store: tuple[str, Path], tmp_path: Path, raising_engine: RaisingStubEngine
) -> None:
    """Extension is legal at the hash boundary and not in this store.

    The stored candidates are a prefix of the request, which is what
    `len(requested) >= len(stored)` permits -- and the `m` and `p` axes are
    fixed at creation, so writing the new candidate needs a whole-store rewrite.
    **The completion bitmap has no model axis**, so a tile cannot be complete
    for candidates 0 and 1 and outstanding for 2: there is no state in which a
    superset resume could record what it had done.

    Catches an implementation that reads `len(requested) >= len(stored)` as
    sufficient and proceeds -- which fails later, inside `write_tile`, on an
    array shape, after a full tile of fits and with a message about shapes
    rather than about candidates.
    """
    uri, path = store

    with pytest.raises(ValidationError) as refusal:
        run(
            _config(
                tmp_path,
                uri,
                candidates='["white", "white + matern12", "matern32"]',
            ),
            path,
            engine=raising_engine,
        )

    message = str(refusal.value)
    assert "new store" in message
    assert raising_engine.calls == []


def test_a_shortened_candidate_list_is_refused(
    store: tuple[str, Path], tmp_path: Path, raising_engine: RaisingStubEngine
) -> None:
    """Dropping a candidate is an axis resize too, and it is a prefix.

    `["white"]` matches the store's list at every position it has, so the
    positional comparison passes it and only the length rule catches it. **The
    mutation survived until this test existed** -- the superset arm was covered
    and its mirror was not, which is what a length rule written as one
    comparison invites.

    Catches proceeding with M=1 against a store whose model axis is 2, which
    fails much later inside `write_tile` on an array shape, after a full tile of
    fits and with a message about shapes rather than about candidates.
    """
    uri, path = store

    with pytest.raises(ValidationError) as refusal:
        run(
            _config(tmp_path, uri, candidates='["white"]'),
            path,
            engine=raising_engine,
        )

    message = str(refusal.value)
    assert "2 candidates" in message and "asks for 1" in message
    assert "new store" in message
    assert raising_engine.calls == []


def test_a_detail_selection_change_is_refused(
    store: tuple[str, Path], tmp_path: Path, raising_engine: RaisingStubEngine
) -> None:
    """Neither fit-relevant nor recomputable, so refusal is the only answer.

    A `/detail/` covariance derives from the Hessian at the optimum and the
    Hessian is **not stored**, so the request can be satisfied neither by
    reusing what is there nor by recomputing from primitives -- and a refit
    contradicts the completion bitmap.

    Catches a resume that silently keeps the stored selection, which leaves the
    store's own attrs describing a selection the user did not ask for.
    """
    uri, path = store

    with pytest.raises(ValidationError) as refusal:
        run(
            _config(tmp_path, uri, subsample="none"),
            path,
            engine=raising_engine,
        )

    message = str(refusal.value)
    assert "detail" in message
    assert "pass1" in message and "none" in message
    assert raising_engine.calls == []


def test_the_detail_selection_is_recorded_at_creation(
    store: tuple[str, Path],
) -> None:
    """The refusal above needs something to compare against, so it is stored.

    Until Task 11 `provenance_attrs` did not record `detail` at all, which made
    that arm of the taxonomy a **name with no gate** -- the same defect class as
    `data_uri` standing in for the data it named.

    Catches the attr being dropped, which would leave the refusal comparing a
    request against nothing and passing every change.
    """
    _uri, path = store

    assert "detail" in REQUIRED_ATTRS
    assert _attrs(path)["detail"] == {"region": None, "subsample": "pass1"}


# --------------------------------------------------------------------------
# Ordering, and the exit code
# --------------------------------------------------------------------------


def test_the_input_contract_is_checked_before_the_gate(
    store: tuple[str, Path], tmp_path: Path
) -> None:
    """`open -> contract (4a) -> fingerprint -> fit_hash -> gate -> tiling`.

    The configuration names a variable the input does not have **and** would
    fail the gate, since `variable` is fit-relevant. Only one of the two errors
    can be raised first, so the type says which check ran.

    **The ordering is the guard, and this is why it is tested rather than
    trusted**: a gate computed before the contract check would be computed from
    the config alone, which is where `data_uri`-as-proxy came from -- a hash
    that moved when a file moved and did not move when its contents changed.

    Catches the gate being hoisted above stage 4a, which reports layer 3 for a
    run whose real fault is layer 4 and sends the user to the wrong file.
    """
    uri, path = store

    with pytest.raises(InputContractError):
        run(_config(tmp_path, uri, variable="absent"), path)


def test_a_refusal_exits_three_from_the_command_line(
    store: tuple[str, Path], tmp_path: Path
) -> None:
    """The gate's output is an exit code, and that crosses a process boundary.

    Design doc 14.3: 3 is "config/validation error -- resuming will not help",
    which is true of every refusal this gate makes. In-process the exception
    type is the only observable, and the type-to-code mapping is a second thing
    that can break.

    Catches a refusal escaping as an unhandled exception -- exit code 1, which
    the taxonomy spends on "completed with failures above threshold", printing
    a traceback where a user expects a diagnosis.
    """
    uri, path = store
    config = _config(tmp_path, uri, objective="reml")

    result = subprocess.run(
        [sys.executable, "-m", "metamer", str(config), str(path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == ExitCode.CONFIG_INVALID
    assert "layer 3 (semantic)" in result.stderr
    assert "Traceback" not in result.stderr
    assert json.loads(json.dumps(_attrs(path)))["fit_hash"] is not None
