"""The pass-1 barrier and the cross-store gate.

**EVERY PASS-1 STORE HERE COMES FROM A REAL `run(decimate=True)`.** A store
assembled by hand would carry whatever attrs the test wrote, so the gate would
be checked against a fixture rather than against the thing it will actually
meet -- and the one defect that matters most, a field the writer stopped
recording, would be invisible.

The candidate set is **two** candidates throughout, because a permuted list of
one is the same list and a positional comparison cannot then be told from a set
comparison.
"""

from __future__ import annotations

import os
import signal
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import xarray as xr
import zarr

from metamer.batch.barrier import check_pass1_complete, check_pass1_store
from metamer.batch.geometry import geometry_components, geometry_hash
from metamer.batch.input import open_input
from metamer.batch.run import run
from metamer.batch.validation import ValidationError
from metamer.config import load
from metamer.core.hashing import FIT_RELEVANT_FIELDS, digest

#: The budget that puts the coarse grid in more than one tile -- see
#: `tests/test_decimate.py`, where the same figure is derived and explained. A
#: single-tile pass-1 store is complete after one write, so an INCOMPLETE one
#: cannot be constructed and the barrier's whole test would be vacuous.
MULTI_TILE_BUDGET = 0.0010159

_CONFIG = """
data_uri = "{uri}"
variable = "sla"
signal_terms = ["constant", "trend"]
candidates = ["white", "white + matern12"]
criteria = ["aic"]
memory_budget_gb = 1.0
"""


def _input(tmp_path: Path, name: str = "in.zarr", n_y: int = 12, n_x: int = 12) -> str:
    origin = np.datetime64("2000-01-01")
    dataset = xr.Dataset(
        {
            "sla": (
                ("time", "y", "x"),
                np.random.default_rng(3)
                .standard_normal((24, n_y, n_x))
                .astype("float32"),
            )
        },
        coords={
            "time": np.array([origin + np.timedelta64(31 * i, "D") for i in range(24)]),
            "y": 100.0 + 2.5 * np.arange(n_y),
            "x": 500.0 - 0.5 * np.arange(n_x),
        },
    )
    path = tmp_path / name
    dataset.to_zarr(path)
    return str(path)


def _config(tmp_path: Path, uri: str, extra: str = "", name: str = "c.toml") -> Path:
    path = tmp_path / name
    path.write_text(_CONFIG.format(uri=uri) + extra)
    return path


def _rollup(uri: str) -> str:
    return geometry_hash(geometry_components(open_input(uri, "sla")))


def _pass1(
    tmp_path: Path, uri: str, extra: str = "", name: str = "coarse.zarr"
) -> tuple[Path, Path]:
    """A COMPLETE pass-1 store from a real decimated run, and its config path."""
    config = _config(tmp_path, uri, "\n[warm_start]\ncoarse_stride = 2\n" + extra)
    store = tmp_path / name
    run(config, store, decimate=True)
    return store, config


# --------------------------------------------------------------------------
# The barrier
# --------------------------------------------------------------------------


def test_a_complete_pass_one_store_passes_the_barrier(tmp_path):
    """The positive control every refusal below needs.

    Behaviour under test: that the barrier can be satisfied at all.

    Bug this catches: a barrier that refuses everything, under which each
    refusal test below passes for the wrong reason. (i2) -- and it is not
    optional here, because five of the six tests in this module assert that
    something raises.
    """
    uri = _input(tmp_path)
    store, _ = _pass1(tmp_path, uri)
    check_pass1_complete(store)


def test_an_incomplete_pass_one_store_refuses_and_names_the_outstanding_tiles(
    tmp_path,
):
    """A killed pass 1 blocks pass 2, and the message says which tiles.

    Behaviour under test: the barrier reading "the store is COMPLETE" rather
    than "the store exists".

    Expected values determined independently: the outstanding tiles are read
    from `completed_tiles` in the test, not from the message, and the message is
    then required to contain them.

    Bug this catches: warm-starting from a partial coarse grid. It does not
    fail -- it produces a **valid-looking** source map whose sources are
    systematically further away in the unfitted region, so the saving looks like
    the mechanism underperforming and nothing points at the cause.

    **The multi-tile budget is a precondition, asserted.** At the default budget
    the 6x6 coarse grid is one tile, which is complete after one write, and an
    incomplete store cannot be built at all.
    """
    from metamer.batch.completion import completed_tiles

    uri = _input(tmp_path)
    config = _config(tmp_path, uri, "\n[warm_start]\ncoarse_stride = 2\n")
    store = tmp_path / "coarse.zarr"
    report = run(
        config,
        store,
        decimate=True,
        memory_budget_gb=MULTI_TILE_BUDGET,
        on_tile_written=lambda tile: os.kill(os.getpid(), signal.SIGTERM),
    )
    assert report.tiles_total > 1, "a single-tile fixture cannot be incomplete"
    done = completed_tiles(store)
    assert not done.all()

    with pytest.raises(ValidationError) as raised:
        check_pass1_complete(store)
    message = str(raised.value)
    assert str(int((~done).sum())) in message
    first = tuple(int(v) for v in np.argwhere(~done)[0])
    assert str(first) in message
    assert "Resume pass 1" in message, "a refusal must say what would lift it"


# --------------------------------------------------------------------------
# The cross-store gate
# --------------------------------------------------------------------------


def test_a_matching_pass_one_store_is_accepted(tmp_path):
    """The gate's positive control, on a store from a real decimated run.

    Behaviour under test: that the whole gate -- parent geometry, key sets,
    stride, candidates and the fit-identity digest -- can be satisfied by the
    store `run(decimate=True)` actually writes.

    Bug this catches: a gate whose stored and requested payloads never agree,
    for instance because the writer records the DECIMATED rollup and the reader
    computes the parent's. Every refusal test below would still pass.
    """
    uri = _input(tmp_path)
    store, config_path = _pass1(tmp_path, uri)
    check_pass1_store(store, load(config_path), geometry_hash=_rollup(uri))


def test_a_stride_mismatch_refuses_and_says_what_it_would_do(tmp_path):
    """Pass 1 at stride 2 refuses a run configured for stride 3.

    Behaviour under test: the check the plan singles out. A hash proves two
    CONFIGS agree; it says nothing about what a STORE ON DISK was decimated at,
    so this is compared explicitly against the recorded value rather than
    inferred.

    Bug this catches: assuming the two agree because one was derived from the
    other. A pass-1 store built at one stride consumed at another gives **every
    source index in range and every warm start finite, taken from the wrong
    cell** -- the Task 11 wrong-candidate-at-index-1 shape, one field over.

    **With the positive control**: the same store under the matching stride is
    accepted, so the refusal is about the stride and not about the call.
    """
    uri = _input(tmp_path)
    store, _ = _pass1(tmp_path, uri)
    rollup = _rollup(uri)

    other = _config(tmp_path, uri, "\n[warm_start]\ncoarse_stride = 3\n", "other.toml")
    with pytest.raises(ValidationError) as raised:
        check_pass1_store(store, load(other), geometry_hash=rollup)
    message = str(raised.value)
    assert "coarse stride 2" in message and "3" in message
    assert "wrong cell" in message

    matching = _config(tmp_path, uri, "\n[warm_start]\ncoarse_stride = 2\n", "m.toml")
    check_pass1_store(store, load(matching), geometry_hash=rollup)


def test_a_parent_geometry_mismatch_refuses(tmp_path):
    """A pass-1 store decimated from a different input is not this run's.

    Behaviour under test: the binding that makes the two stores related by
    CONTENT rather than by where somebody put them.

    Expected value determined independently: the second input has a different
    grid, so `geometry_components` differs and the rollup differs -- computed in
    the test from the input rather than read from either store.

    Bug this catches: two unrelated stores joined by a path, which is the
    copy-not-reference invariant's opposite failure. Every warm start would be a
    converged fit from another grid entirely, and the shapes need not even
    disagree.
    """
    uri = _input(tmp_path)
    store, config_path = _pass1(tmp_path, uri)
    stranger = _input(tmp_path, name="other.zarr", n_y=12, n_x=10)
    assert _rollup(stranger) != _rollup(uri), "the fixture must differ"

    with pytest.raises(ValidationError, match="was decimated from an input"):
        check_pass1_store(store, load(config_path), geometry_hash=_rollup(stranger))


def test_a_permuted_candidate_set_refuses(tmp_path):
    """Swapping the candidate order is refused positionally.

    Behaviour under test: the model axis being positional in both stores.

    Bug this catches: the comparison degrading to a set or a sorted one, which
    accepts a permutation and writes each candidate's warm start into another's
    slot. Where the candidates have different free-parameter counts it also
    shifts every offset on the ragged axis, so the corruption lands in two
    arrays rather than one.

    **Two candidates is the minimum that can express this**, which is why the
    module's config carries two: a permuted list of one is the same list.
    """
    uri = _input(tmp_path)
    store, _ = _pass1(tmp_path, uri)
    swapped = tmp_path / "swapped.toml"
    swapped.write_text(
        _CONFIG.format(uri=uri).replace(
            'candidates = ["white", "white + matern12"]',
            'candidates = ["white + matern12", "white"]',
        )
        + "\n[warm_start]\ncoarse_stride = 2\n"
    )
    with pytest.raises(ValidationError, match="candidate 0 differs"):
        check_pass1_store(store, load(swapped), geometry_hash=_rollup(uri))


def test_a_fit_identity_difference_the_gate_never_enumerated_still_refuses(tmp_path):
    """A different `objective` refuses, though no check names it.

    Behaviour under test: **the reason the gate is a digest over the allowlist
    and not a list of comparisons.** `objective` is not mentioned anywhere in
    the plan's Task 4, and a warm start from a store fitted under REML into an
    ML run is a converged fit at another likelihood's optimum -- exactly as
    wrong as a stride mismatch and just as silent.

    Expected value determined independently: `objective` is in
    `FIT_RELEVANT_FIELDS`, so it moves `fit_hash`, so it must move this gate.
    Asserted here rather than assumed.

    Bug this catches: an enumerated gate. It protects the fields somebody
    thought of, and every field added later defaults to unprotected -- which is
    a denylist wearing an allowlist's clothes.

    **And the message names the field**, because a digest mismatch on its own is
    a wall.
    """
    assert "objective" in FIT_RELEVANT_FIELDS
    uri = _input(tmp_path)
    store, _ = _pass1(tmp_path, uri)
    reml = tmp_path / "reml.toml"
    reml.write_text(
        _CONFIG.format(uri=uri)
        + '\nobjective = "reml"\n\n[warm_start]\ncoarse_stride = 2\n'
    )
    with pytest.raises(ValidationError) as raised:
        check_pass1_store(store, load(reml), geometry_hash=_rollup(uri))
    message = str(raised.value)
    assert "objective" in message and "reml" in message
    assert "another" in message and "optimum" in message


def test_an_ordinary_store_is_refused_as_a_pass_one_store(tmp_path):
    """A full-grid store carries no parent geometry, and that is the answer.

    Behaviour under test: the (a0) decision that the decimation attrs' ABSENCE
    means "not a pass-1 store", rather than being a missing required field.

    Bug this catches: the gate reading a missing key through `attrs.get` as a
    default and comparing `None` against `None`, which accepts any ordinary
    store as pass 1 for anything.
    """
    uri = _input(tmp_path)
    config = _config(tmp_path, uri)
    full = tmp_path / "full.zarr"
    run(config, full)
    assert "parent_geometry_hash" not in dict(
        zarr.open_group(str(full), mode="r").attrs
    )
    with pytest.raises(ValidationError, match="records no parent geometry"):
        check_pass1_store(full, load(config), geometry_hash=_rollup(uri))


# --------------------------------------------------------------------------
# The stored payload and its digest
# --------------------------------------------------------------------------


def test_the_stored_payload_hashes_to_the_stored_parent_fit_hash(tmp_path):
    """The deliberate duplication cannot drift.

    Behaviour under test: `digest(parent_fit_payload) == parent_fit_hash`, the
    invariant that makes storing both safe. The payload exists so a refusal can
    NAME the differing field; the digest is the gate. Two records of one fact
    drift the moment either is written from a different place.

    Expected value determined independently: `digest` is applied to the payload
    read back out of the store, and compared with the separately stored string.
    Neither is recomputed from the config.

    Bug this catches: the writer taking the digest over a different mapping from
    the one it records -- for instance over the full payload rather than the
    allowlist subset. Every gate would then refuse, and the refusal would name
    no difference at all.

    **This is `geometry_components` beside `geometry_hash` one group over**, and
    that pairing exists for the same reason: §13.3 requires a mismatch to be
    diagnosable from the store alone.
    """
    uri = _input(tmp_path)
    store, _ = _pass1(tmp_path, uri)
    attrs = dict(zarr.open_group(str(store), mode="r").attrs)
    stored: Any = attrs["parent_fit_payload"]
    assert digest(dict(stored)) == attrs["parent_fit_hash"]
    assert set(stored) == set(FIT_RELEVANT_FIELDS)


def test_the_parent_fit_hash_is_not_the_stores_own_fit_hash(tmp_path):
    """The two differ, and the difference is exactly the geometry.

    Behaviour under test: **why the gate needs a substituted rollup at all.**
    Pass 1's own `fit_hash` is over the DECIMATED geometry; the gate compares
    over the PARENT's. If the two were equal, the substitution would be doing
    nothing and the geometry difference would not be cancelling -- it would be
    absent, which would mean the decimation had not reached the hash.

    Expected value determined independently: substituting the store's OWN
    `geometry_hash` into the parent payload must reproduce the store's OWN
    `fit_hash`. That is a stronger statement than comparing the two digests --
    it says the two payloads differ in `geometry_hash` **and in nothing else**,
    and it is checked against a value the store recorded rather than against a
    second computation of the same thing.

    Bug this catches: recording the decimated rollup as `parent_geometry_hash`,
    under which the gate compares pass 1 against itself and accepts a store
    decimated from any input. It also catches the parent payload drifting from
    the run's actual configuration in any other field, since the substitution
    would then not reproduce `fit_hash`.
    """
    uri = _input(tmp_path)
    store, _ = _pass1(tmp_path, uri)
    attrs = dict(zarr.open_group(str(store), mode="r").attrs)
    raw: Any = attrs["parent_fit_payload"]
    parent = dict(raw)

    assert attrs["parent_fit_hash"] != attrs["fit_hash"]
    assert parent["geometry_hash"] == attrs["parent_geometry_hash"]
    assert parent["geometry_hash"] != attrs["geometry_hash"]

    own = dict(parent, geometry_hash=attrs["geometry_hash"])
    assert digest(own) == attrs["fit_hash"]
