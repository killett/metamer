"""Sub-phase 2f Task 4: the resolved-candidate block and the domain-mask era.

**THE BLOCK RECORDS WHAT RESOLUTION PRODUCED, AND THE WHOLE RISK IS THAT IT
RECORDS THE REQUEST INSTEAD** (D12). With one engine in the tree those are
equal, so a column wired to `config.engine` passes every test until Phase 3's
Whittle engine makes them differ -- which is why the engine column is filled
through the resolution path or not at all, and why the tests here discriminate
on the two fields that narrow TODAY.
"""

from __future__ import annotations

import json
import pathlib
import textwrap
from typing import Any

import numpy as np
import pytest
import xarray as xr
import zarr

import metamer.core  # noqa: F401  -- registration side effect
from metamer.batch.ragged import model_label
from metamer.batch.run import run
from metamer.batch.store import REQUIRED_ATTRS
from metamer.config.model import load
from metamer.core import hashing
from metamer.core.capability import CostClass, EngineId, GradientMode, Objective
from metamer.core.resolution import (
    ENGINE_NOT_RESOLVED,
    CandidateResolution,
    resolve_candidate,
)

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")

_CONFIG = """
data_uri = "{uri}"
variable = "sla"
signal_terms = ["constant", "trend"]
candidates = [{candidates}]
criteria = ["aic"]
"""


def _input(base: pathlib.Path) -> str:
    origin = np.datetime64("2000-01-01")
    times = np.array([origin + np.timedelta64(31 * i, "D") for i in range(24)])
    dataset = xr.Dataset(
        {"sla": (("time", "y", "x"), np.zeros((24, 4, 4), dtype="float32"))},
        coords={"time": times, "y": np.arange(4), "x": np.arange(4)},
    )
    uri = base / "in.zarr"
    dataset.to_zarr(uri)
    return str(uri)


def _config(base: pathlib.Path, candidates: str, name: str = "c.toml") -> pathlib.Path:
    path = base / name
    path.write_text(
        textwrap.dedent(_CONFIG.format(uri=_input(base), candidates=candidates))
    )
    return path


@pytest.fixture(scope="module")
def narrowing_store(tmp_path_factory: pytest.TempPathFactory) -> pathlib.Path:
    """A real run over two candidates whose capability intersections differ.

    `matern32` withholds `celerite2` -- its own docstring says declaring it
    would let the intersection claim an engine that cannot evaluate the kernel
    without altering it -- so `white` survives on four engines and
    `white + matern32` on three. **That difference is the per-candidate
    narrowing the block has to record.**
    """
    base = tmp_path_factory.mktemp("resolved")
    config = _config(base, '"white", "white + matern32"')
    store = base / "out.zarr"
    run(config, store)
    return store


def _attrs(store: pathlib.Path) -> dict[str, Any]:
    return dict(zarr.open_group(str(store), mode="r").attrs)


def test_the_block_records_a_narrowing_that_differs_between_candidates(
    narrowing_store,
):
    """Two candidates, two intersections, and the block carries both.

    Expected values determined independently by reading the families' own `n`
    mappings: `white` declares all four engines, `matern32` withholds
    `celerite2`, and `intersect_engine_costs` keeps only engines every term
    supports. So the composite's surviving set is exactly the single term's
    minus `celerite2`.

    Bug this catches: **a block that records a run-level fact per candidate.**
    `engine`, `objective` and `registry_version` are all run-level and all
    already in attrs; a builder that filled the rows from those would produce
    two identical rows and pass any test that only checked a row exists. The
    two rows must DIFFER, and differ in the field section 4.2's intersection
    actually moves.

    **THE GRADIENT-MODE COLUMN IS NOT A DISCRIMINATOR ON THIS FIXTURE** and
    that is stated rather than left to be discovered: no family in this set
    implements analytic gradients, so both rows read `fd`. The column is
    asserted to be present and correct, not to differ.
    """
    block = _attrs(narrowing_store)["resolved_candidates"]
    rows = {row["label"]: row for row in block["candidates"]}

    assert len(rows) == 2
    single = next(row for label, row in rows.items() if "matern32" not in label)
    composite = next(row for label, row in rows.items() if "matern32" in label)

    assert "celerite2" in single["engine_costs"]
    assert "celerite2" not in composite["engine_costs"]
    assert set(composite["engine_costs"]) == set(single["engine_costs"]) - {"celerite2"}
    assert single["gradient_mode"] == composite["gradient_mode"] == "fd"


def test_the_engine_column_says_it_is_not_resolved_rather_than_holding_the_request(
    narrowing_store,
):
    """A column named `resolved` must not hold the request.

    Expected value determined independently: `run.py` passes `config.engine`
    into `fit` and `ProcessSpec.engine_costs()` has no caller outside `terms`
    and `capability`, so **the batch path never narrows the engine**. With one
    engine there is nothing to narrow and nothing is wrong -- and the honest
    record of "not resolved" is not the request.

    Bug this catches: the column filled from `config.engine`. It would agree
    with the truth until Phase 3's Whittle engine lands, then record the
    REQUEST under the name `resolved` while the run began narrowing -- D1's
    tell exactly, a name saying one thing while the value is another, shipped
    with a passing test suite behind it.

    **THE ENGINE-NARROWING TEST IS OWED AT A TRIGGER**, recorded in PROGRESS
    beside P4'': when a second engine lands, a candidate whose terms exclude
    the configured engine must record the engine it actually ran.
    """
    block = _attrs(narrowing_store)["resolved_candidates"]

    assert block["engine_resolution"] == ENGINE_NOT_RESOLVED
    for row in block["candidates"]:
        assert row["engine"] == ENGINE_NOT_RESOLVED
        assert row["engine"] != "kalman", "the column holds the request"


def test_the_block_says_when_it_was_resolved_and_against_which_registry(
    narrowing_store,
):
    """ "Resolved at run start" is the D12 distinction, stated not blurred.

    Expected value determined independently: the block is built inside
    `provenance_attrs`, which runs before any fit, and `registry_version` is
    written into the same attrs -- so the label can name the exact registry the
    fits are about to use.

    Bug this catches: a block that reads as "what the run resolved" while
    having been computed from the config. **It WAS computed from the config**,
    at run start, and the difference from the Phase 5 case D12 refuses is the
    registry: this one resolves against the registry in force for these fits,
    that one would re-resolve later against whatever registry existed then. A
    label that does not say which is which leaves a later reader to guess.
    """
    attrs = _attrs(narrowing_store)
    block = attrs["resolved_candidates"]

    assert block["resolved_at"] == (
        f"run start, against registry version {attrs['registry_version']}"
    )


def test_the_block_matches_what_the_resolution_path_returns_for_the_same_spec(
    narrowing_store,
):
    """The recorded rows are the resolver's own output, not a parallel build.

    Expected values determined independently by calling `resolve_candidate` on
    the same config's specs and comparing record for record -- an oracle that
    does not go through `provenance_attrs`.

    Bug this catches: a second construction of the rows inside `store.py` that
    drifts from the resolver -- the two-definitions defect at the granularity
    of a provenance block. **And it is the binding test the pre-fit label
    needs**: the label claims the block is the resolution the fits will use, so
    something must compare the two.

    **ITS LIMIT IS STATED BECAUSE IT IS REAL.** This binds the block to the
    RESOLVER, and the resolver to the fit path is bound by the finding recorded
    at the block: nothing after run start can move a series' engine, cost class
    or gradient mode -- `resolve_gradient_mode` runs once per candidate before
    the per-series loop and raises rather than downgrading, the engine is bound
    once per `fit()` call, and the one per-series fallback is the starting rung,
    a different quantity that is already persisted per series. **If a runtime
    fallback is ever added, this test keeps passing and the label becomes
    false**, so the finding is recorded where the label is.
    """
    base = narrowing_store.parent
    config = load(base / "c.toml")
    expected = [
        resolve_candidate(
            spec, model_label(spec), Objective(config.objective)
        ).as_record()
        for spec in config.process_specs()
    ]
    recorded = _attrs(narrowing_store)["resolved_candidates"]["candidates"]

    assert recorded == expected


def test_the_domain_mask_field_records_false_rather_than_staying_absent(
    narrowing_store,
):
    """A run that applied no mask says so; it does not stay silent.

    Expected value determined independently: design doc section 13.6's declared
    domain mask does not exist yet, so every run today applies none -- and
    `false` is a fact the run knows and can record.

    Bug this catches: leaving the field out until section 13.6 lands, which
    keeps every store in the "did not record" state and gives the report no way
    to distinguish a run that had no mask from a writer that did not know to
    ask. **Absence and `false` are different sentences** and the report prints
    them differently.
    """
    assert _attrs(narrowing_store)["domain_mask"] is False


def test_neither_new_key_is_required_so_older_stores_still_open():
    """Absence is the answer, which means absence must not be refused.

    Expected value determined independently: `create_store` raises on any
    member of `REQUIRED_ATTRS` that is missing, so a key added there would
    refuse every store written before this task.

    Bug this catches: the reflex of adding a new provenance key to the required
    set. `decimation` and `calibration` are the precedent and their own comment
    says it -- "which would refuse every store written before this task" --
    and this is the third instance of the same additive shape.
    """
    assert "resolved_candidates" not in REQUIRED_ATTRS
    assert "domain_mask" not in REQUIRED_ATTRS


def test_the_block_reaches_none_of_the_three_hash_payloads(narrowing_store):
    """Additive provenance, asserted rather than argued (D12).

    Expected value determined independently: the three payloads are built from
    `normalize(config)`, and the block records what resolution PRODUCED -- an
    output of the run, never a config field -- so neither new key can appear in
    any of them. The payloads are built here directly from the config, which is
    a different route from the one that wrote the store.

    Bug this catches: a later change deriving a block field from a config
    field. That would put it in a payload, move the hash, and **invalidate
    every existing store's resume** -- the most expensive failure in the
    project, and one whose structural argument is sound today and guaranteed by
    nothing tomorrow. That is exactly why D12 says asserted rather than
    assumed.

    **THE KEYS ARE CHECKED AGAINST THE PAYLOADS AND NOT THE HASH VALUES**,
    deliberately: comparing two hashes only shows they differ or not, and a
    hash that did not move because the payload builder dropped the key for
    another reason would read as a pass. The payload is the subject.
    """
    config = load(narrowing_store.parent / "c.toml")
    payload = config.to_payload(_attrs(narrowing_store)["geometry_hash"])
    payloads = {
        "fit": hashing.fit_payload(payload),
        "compat": hashing.compat_payload(payload),
        "run": hashing.run_payload(payload),
    }

    for name, payload in payloads.items():
        flattened = json.dumps(payload, sort_keys=True)
        assert "resolved_candidates" not in flattened, name
        assert "domain_mask" not in flattened, name
    # And the store really does carry what the payloads exclude.
    attrs = _attrs(narrowing_store)
    assert "resolved_candidates" in attrs and "domain_mask" in attrs


def test_the_record_orders_its_engines_deterministically():
    """Provenance must not depend on `PYTHONHASHSEED`.

    Expected value determined independently: the four engine names in
    lexicographic order. The input mapping here is deliberately built out of
    order, so a record that preserves insertion order fails and one that sorts
    passes -- the assertion cannot be satisfied by luck.

    Bug this catches: **the one the full sweep found.**
    `intersect_engine_costs` returns a dict built from SET iteration, so its
    key order varies with the interpreter's hash seed -- measured at three
    seeds, three different orders for identical content. That made the store's
    root attrs byte-different between two runs of the same config, which
    `tests/test_store.py::test_the_root_attrs_are_byte_identical_across_processes`
    exists to refuse. **Nothing in this file's other tests could see it**: they
    all run in one process, where the order is whatever that process drew.

    **IT IS THE (k) SHAPE**: a property of a DIFFERENT process that no amount
    of testing in this one reaches, which is why the guard that caught it is a
    cross-process test and this one is only the fast local echo of it.
    """
    unsorted = {
        EngineId.TOEPLITZ: CostClass.CUBIC,
        EngineId.CELERITE2: CostClass.LINEAR,
        EngineId.KALMAN: CostClass.LINEAR,
    }
    record = CandidateResolution(
        label="x",
        spec_hash="deadbeef",
        engine=ENGINE_NOT_RESOLVED,
        engine_costs=unsorted,
        gradient_mode=GradientMode.FINITE_DIFFERENCE,
        objective=Objective.ML,
    ).as_record()
    costs = record["engine_costs"]
    assert isinstance(costs, dict)

    assert list(costs) == ["celerite2", "kalman", "toeplitz"]
