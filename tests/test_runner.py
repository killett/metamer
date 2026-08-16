"""`metamer.batch.run` and `python -m metamer`: the entry contract and the codes.

Two claims, and they are tested in two different places on purpose.

**The ordering of the entry contract** (design doc section 13.7) is a property of
`run`, and it is tested rather than trusted: a hash computed before the input
contract check would be computed from the config alone, which is exactly where
`data_uri`-as-proxy came from.

**An exit code is a property of a PROCESS**, so every exit-code assertion runs
`python -m metamer` in a subprocess and reads `returncode`. Calling `main()`
in-process tests the mapping function -- worth doing, and not the same claim:
`sys.exit` semantics, argparse's own exits and an unhandled traceback are all
invisible to an in-process call.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
import xarray as xr

from metamer.batch.input import InputContractError
from metamer.batch.run import run
from metamer.batch.threads import NUMBA_KEY
from metamer.batch.validation import ExitCode, ValidationError, ValidationLayer
from metamer.core import machine
from metamer.core.memory import default_budget_gb
from metamer.core.outcomes import Outcome

# `to_zarr` warns that consolidated metadata is not in the v3 spec. It is
# xarray's default and says nothing about this code.
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


def _store(tmp_path: Path, *, n_time: int = 24, n_y: int = 2, n_x: int = 3) -> str:
    """A minimal but real zarr input satisfying the stage-4a contract."""
    dataset = xr.Dataset(
        {
            "sla": (
                ("time", "y", "x"),
                np.zeros((n_time, n_y, n_x), dtype="float32"),
            )
        },
        coords={
            "time": _months(n_time),
            "y": np.arange(n_y),
            "x": np.arange(n_x),
        },
    )
    path = tmp_path / "in.zarr"
    dataset.to_zarr(path)
    return str(path)


def _config(tmp_path: Path, uri: str, extra: str = "", name: str = "c.toml") -> Path:
    path = tmp_path / name
    path.write_text(textwrap.dedent(_CONFIG.format(uri=uri)) + textwrap.dedent(extra))
    return path


def _invoke(*arguments: str) -> subprocess.CompletedProcess[str]:
    """Run `python -m metamer` in a fresh process."""
    return subprocess.run(
        [sys.executable, "-m", "metamer", *arguments],
        capture_output=True,
        text=True,
        check=False,
    )


# --------------------------------------------------------------------------
# The entry contract's ordering
# --------------------------------------------------------------------------


def test_a_valid_config_over_a_valid_input_produces_both_gate_hashes(tmp_path):
    """The positive control for every refusal below, and for the None branch.

    `fit_hash` and `compat_hash` are `str | None`, and None is a real answer:
    section 13.4 makes an unreachable input a DEGRADED MODE, because sizing a
    run before staging 25 GB is `--explain`'s most valuable use. So "the run
    produced no fit_hash" is not evidence of anything on its own -- it is what a
    correct run over no data also does.

    Bug this catches: a runner that never opens the input and hashes the config
    alone, which returns None for both gates and looks like a clean run.
    """
    report = run(_config(tmp_path, _store(tmp_path)), tmp_path / "out.zarr")

    assert report.geometry_hash is not None
    assert report.fit_hash is not None
    assert report.compat_hash is not None
    assert len(report.fit_hash) == 16
    assert report.fit_hash != report.compat_hash
    assert report.contract.n_time == 24
    assert report.contract.n_y == 2
    assert report.contract.n_x == 3


def test_the_gate_hashes_come_from_the_input_and_not_from_the_config(tmp_path):
    """Editing the input's GEOMETRY moves both gates; the config is unchanged.

    Bug this catches: `fit_hash` computed from the config alone -- which is
    what `data_uri` was, and it was wrong in both directions at once. The two
    runs below share a config file byte for byte and differ only in the grid the
    URI points at, so a config-only hash returns the same value twice.
    """
    first = run(_config(tmp_path, _store(tmp_path)), tmp_path / "a.zarr")

    wide = tmp_path / "wide"
    wide.mkdir()
    second = run(_config(wide, _store(wide, n_x=4), name="c.toml"), tmp_path / "b.zarr")

    assert first.fit_hash != second.fit_hash
    assert first.compat_hash != second.compat_hash


def test_no_hash_is_computed_when_the_input_contract_fails(tmp_path):
    """Section 13.7's ordering: contract check BEFORE the fingerprint.

    **THE FIXTURE IS CHOSEN SO THE TWO ORDERINGS RAISE DIFFERENT THINGS**, and
    that choice is the whole test. A bare numeric time axis with no `units`
    attribute does not CF-decode, so:

      - contract first  -> `InputContractError`, saying the axis did not decode
        and that no unit is inferred from magnitude;
      - fingerprint first -> a bare `TypeError` out of `to_decimal_years`,
        which is unstaged and reaches the user as a traceback and exit code 1.

    A wrong-shaped variable would NOT have worked: both orderings raise
    `InputContractError` there, so the assertion would pass against either and
    the ordering claim would be untested while looking tested. Measured before
    the test was written.

    Bug this catches: computing `geometry_hash` from whatever opened and then
    validating. Where it does not crash it is silent -- the hash is well-formed,
    the store it keys is wrong, and the mismatch surfaces as a refused resume
    months later.
    """
    dataset = xr.Dataset(
        {"sla": (("time", "y", "x"), np.zeros((6, 2, 3), dtype="float32"))},
        coords={"time": np.arange(6.0), "y": np.arange(2), "x": np.arange(3)},
    )
    path = tmp_path / "undecodable.zarr"
    dataset.to_zarr(path)

    with pytest.raises(InputContractError, match="did not decode"):
        run(_config(tmp_path, str(path)), tmp_path / "out.zarr")


def test_a_config_that_fails_layer_3_and_layer_4_reports_layer_3(tmp_path):
    """Layer 3 runs before the input is opened, and the ordering is the claim.

    The config below enables screening (layer 3) **and** points at a URI with no
    data behind it (layer 4). Only one of the two can be reported, and it must
    be the config: a user whose config is wrong should not be sent to inspect
    their data.

    Bug this catches: opening the input first -- the natural order if the
    runner is written as "get everything you need, then check it". No
    single-fault test can express this, because either ordering passes both of
    them.
    """
    config = _config(
        tmp_path,
        str(tmp_path / "absent.zarr"),
        extra="\n[screening]\nenabled = true\n",
    )
    with pytest.raises(ValidationError) as caught:
        run(config, tmp_path / "out.zarr")
    assert caught.value.layer is ValidationLayer.SEMANTIC


def test_a_bad_data_uri_alone_is_a_layer_4_failure(tmp_path):
    """The control for the ordering test: with the config clean, layer 4 fires.

    Bug this catches: an ordering test that passes because layer 4 never runs
    at all. If the open were unreachable, the test above would pass for the
    wrong reason and this one would fail.
    """
    with pytest.raises(InputContractError):
        run(_config(tmp_path, str(tmp_path / "absent.zarr")), tmp_path / "out.zarr")


def test_the_memory_budget_override_reaches_the_run_hash(tmp_path):
    """`--memory-budget` changes the EFFECTIVE config, so provenance follows it.

    `memory_budget_gb` is run-relevant: section 11.1.1 requires peak RAM to be
    derivable from the budget alone, so a run whose budget came from the command
    line must record the budget it actually used.

    Bug this catches: applying the override to the tiling arithmetic while
    hashing the file's value, which makes `run_hash` describe a run that did not
    happen -- and neither gate moves, so nothing else would notice.
    """
    config = _config(tmp_path, _store(tmp_path))
    default = run(config, tmp_path / "a.zarr")
    overridden = run(config, tmp_path / "b.zarr", memory_budget_gb=4.0)

    assert overridden.config.memory_budget_gb == 4.0
    # **NOT 1.0 SINCE PHASE 2b TASK 3.** The field has no declared default any
    # more -- an omitted budget is the unset sentinel and resolves from the
    # machine -- so the value to compare against is what `default_budget_gb()`
    # gives, and the override is asserted to have replaced it rather than to
    # differ from a constant.
    assert default.config.memory_budget_gb == default_budget_gb()
    assert default.memory_budget_requested_gb is None
    assert overridden.memory_budget_requested_gb == 4.0
    assert overridden.run_hash != default.run_hash
    # The budget is run-relevant and NOT fit-relevant, so the gates must not
    # move. Asserted as its own expected value rather than as a relation:
    # "both moved" and "neither moved" both satisfy an equality between them.
    assert overridden.fit_hash == default.fit_hash
    assert overridden.compat_hash == default.compat_hash


def test_a_config_omitting_the_budget_hashes_as_one_naming_the_resolved_value(
    tmp_path,
):
    """2b exit criterion 10, and it is two claims rather than one.

    **The resolved value is what the run used, so it is what `run_hash`
    records** -- a config that says nothing and a config that names the number
    the machine gives are the same run and must be the same hash. **Provenance
    still tells them apart**, because "the user asked for 4.13 GB" and "the user
    asked for nothing and this machine offered 4.13 GB" are different facts, and
    the second one stops being reconstructible the moment the store moves to
    another box.

    Expected values determined independently: `memory.default_budget_gb()` is
    what an unset budget resolves to, and its own arithmetic is pinned in
    `tests/test_memory.py` against constructed RAM readings rather than here.

    Bug this catches: the `None` reaching the payload, where it hashes as JSON
    `null` -- the two runs then disagree about a budget they both used. And the
    resolution being applied to the tiling arithmetic alone, which leaves
    `run_hash` describing a run that did not happen. **The third config is the
    control**: without it, a budget dropped from the payload entirely would
    satisfy the equality above for the wrong reason.
    """
    import xarray as xr

    uri = _store(tmp_path)
    resolved = default_budget_gb()
    omitted = run(_config(tmp_path, uri, name="omitted.toml"), tmp_path / "a.zarr")
    named = run(
        _config(
            tmp_path,
            uri,
            extra=f"memory_budget_gb = {resolved!r}\n",
            name="named.toml",
        ),
        tmp_path / "b.zarr",
    )
    elsewhere = run(
        _config(
            tmp_path,
            uri,
            extra=f"memory_budget_gb = {resolved * 2!r}\n",
            name="elsewhere.toml",
        ),
        tmp_path / "c.zarr",
    )

    assert omitted.config.memory_budget_gb == resolved
    assert omitted.run_hash == named.run_hash
    assert omitted.tile_side == named.tile_side
    assert omitted.run_hash != elsewhere.run_hash

    stored_omitted = xr.open_zarr(str(omitted.store_path)).attrs
    stored_named = xr.open_zarr(str(named.store_path)).attrs
    assert stored_omitted["memory_budget_gb"] == resolved
    assert stored_named["memory_budget_gb"] == resolved
    assert stored_omitted["memory_budget_requested_gb"] is None
    assert stored_named["memory_budget_requested_gb"] == resolved


def test_a_config_with_no_budget_cannot_bypass_the_budget_refusal(
    tmp_path, monkeypatch
):
    """The floor refusal fires on the RESOLVED budget, not on the config's.

    **THIS TEST WAS OWED BY TASK 2 AND COULD NOT BE WRITTEN THERE.** The field
    still had a pydantic default of 1.0, so there was no `None` to bypass the
    check with, and a test asserting that one could not would have been asserting
    something about a state that could not occur.

    Expected values determined independently: the constructed cgroup limit makes
    total RAM 4 000 000 B, so the default budget is a quarter of that --
    1 000 000 B, which is exactly `tests/conftest.py`'s stub floor. `budget -
    floor` is then 0 and no headroom fraction can make a positive block out of
    it, so `tiling.block_bytes_for` refuses and `run()` stages it as layer 3.

    Bug this catches: the resolution happening below the tiling call, or the
    refusal reading `config.memory_budget_gb` instead of the resolved value.
    Either way a `None` budget is the **one** path on which a run whose budget
    cannot hold a tile proceeds anyway -- and what it would proceed to is a
    `TypeError` in the arithmetic at best, and a tile sized from a default
    nobody chose at worst.
    """
    uri = _store(tmp_path)
    config = _config(tmp_path, uri)

    # THE POSITIVE CONTROL, FIRST: the same config on this machine's real RAM
    # runs. Without it, a refusal below could be the cgroup patch breaking the
    # run rather than the budget being refused.
    assert run(config, tmp_path / "ok.zarr").tiles_written == 1

    limit = tmp_path / "memory.max"
    limit.write_text("4000000\n")
    monkeypatch.setattr(machine, "CGROUP_V2_PATH", str(limit))
    monkeypatch.setattr(machine, "CGROUP_V1_PATH", str(tmp_path / "absent"))
    assert default_budget_gb() == 0.001

    with pytest.raises(ValidationError) as caught:
        run(config, tmp_path / "refused.zarr")

    message = str(caught.value)
    assert caught.value.layer is ValidationLayer.SEMANTIC
    assert "leaves nothing for a tile" in message
    # The refusal names the floor and a budget that would work, which is what
    # makes it planning information rather than a wall.
    assert "1.0 MB before a tile exists" in message
    assert not (tmp_path / "refused.zarr").exists()


def test_the_derived_tile_side_does_not_move_when_available_ram_does(
    tmp_path, monkeypatch
):
    """Two runs on one machine derive one side, whatever else is running.

    Expected values determined independently: total RAM is held at
    16 000 000 000 B in both runs and only the available figure moves, so the
    resolved budget is 4.0 GB both times -- 0.25 of the total -- and the side
    follows the budget alone.

    **THE THIRD RUN IS THE DISCRIMINATOR AND THE TEST IS VACUOUS WITHOUT IT
    (i7).** "The side did not move" is satisfied for free wherever the two
    candidate budgets happen to round to the same side, and with conftest's 1 MB
    stub floor most pairs do. The third run asks for 0.25 GB -- exactly what an
    available-RAM default would have produced from the first run's availability
    figure -- and its side must be **different**, so the equality above is a
    statement about the rule rather than about the fixture.

    Bug this catches: `min(total, available)` or a straight available reading in
    the default. Its symptom is not an error: the side moves with ambient load,
    so a resume of a store built on a quiet machine refuses on a busy one, which
    is the failure design doc section 15.5's burst-and-resume argument exists to
    prevent.
    """
    import psutil

    uri = _store(tmp_path)
    config = _config(tmp_path, uri)

    monkeypatch.setattr(
        psutil,
        "virtual_memory",
        lambda: SimpleNamespace(total=16_000_000_000, available=1_000_000_000),
    )
    busy = run(config, tmp_path / "busy.zarr")
    available_default = run(
        _config(tmp_path, uri, extra="memory_budget_gb = 0.25\n", name="avail.toml"),
        tmp_path / "avail.zarr",
    )

    monkeypatch.setattr(
        psutil,
        "virtual_memory",
        lambda: SimpleNamespace(total=16_000_000_000, available=15_000_000_000),
    )
    quiet = run(config, tmp_path / "quiet.zarr")

    assert busy.config.memory_budget_gb == 4.0
    assert quiet.config.memory_budget_gb == 4.0
    assert busy.tile_side == quiet.tile_side
    assert available_default.tile_side != busy.tile_side


def test_a_defaulted_store_resumed_on_a_smaller_machine_is_refused_by_its_side(
    tmp_path, monkeypatch
):
    """The machine-dependent default reaches the (a1) re-derivation guard.

    Until Task 3 the tile side was re-derived at every resume from a budget that
    lived **in the config**, so two resumes of one config derived one side on any
    machine. The default makes the derived side a function of the machine's total
    RAM, so a store built where RAM is plentiful and resumed where it is not hits
    `completion.resume_tile_side`'s *stored > derived* arm. **That arm is the
    right answer** -- the shards were fixed at creation and adopting the larger
    tile would exceed the budget this run was given.

    Expected values determined independently: the first run resolves 4.0 GB from
    a constructed 16 GB total; the second sees a constructed 40 MB allowance and
    resolves 10 MB, which cannot hold a tile of the stored side.

    Bug this catches, and it is the reason this task touches the refusal's text:
    the message says *"the budget that produced them was X GB ... raise
    --memory-budget to at least that"*, and **the user never typed a budget** --
    X is an artefact of the other machine's RAM. A resolution naming an operation
    the caller is not performing is worse than none, which is (c3)'s phrasing
    rule one register over.
    """
    import psutil

    uri = _store(tmp_path)
    config = _config(tmp_path, uri)
    store_path = tmp_path / "out.zarr"

    monkeypatch.setattr(
        psutil,
        "virtual_memory",
        lambda: SimpleNamespace(total=16_000_000_000, available=8_000_000_000),
    )
    first = run(config, store_path)
    assert first.memory_budget_requested_gb is None

    limit = tmp_path / "memory.max"
    limit.write_text("40000000\n")
    monkeypatch.setattr(machine, "CGROUP_V2_PATH", str(limit))
    monkeypatch.setattr(machine, "CGROUP_V1_PATH", str(tmp_path / "absent"))

    with pytest.raises(ValidationError) as caught:
        run(config, store_path)

    message = str(caught.value)
    assert caught.value.layer is ValidationLayer.SEMANTIC
    assert f"tile side of {first.tile_side}" in message
    assert "4.0 GB" in message
    # The store records that nobody asked for that budget, so the refusal says
    # so rather than telling the user to raise a flag they never set.
    assert "which that run did not ask for" in message


@pytest.mark.slow
@pytest.mark.machine
@pytest.mark.real_floor
def test_a_run_measures_its_own_floor_when_none_is_supplied(tmp_path):
    """**THE POSITIVE CONTROL FOR conftest's FLOOR STUB.** Without it, nothing.

    Every other `run()` in this suite gets a stubbed probe, because the real one
    is a child process that imports numba and opens the input and there are ~80
    call sites. **A default-stubbed seam makes every downstream floor assertion
    vacuous** -- "the floor reached the store" is satisfied identically by a
    probe that ran and a probe that was never wired in. This is the test that
    can tell them apart, and it is the only one.

    Expected values determined independently, from the ladder in
    `test_memory.py`: on this machine the post-warm floor is ~217 MB and the
    figure with the input open is ~228 MB. The bounds below are 120-500 MB,
    deliberately wide -- what is being pinned is that a **measurement** happened,
    not what it measured -- and they exclude conftest's stub, whose ladder is
    round hundreds of megabytes ending at 600 MB.

    Bug this catches: `run()` never calling `measure_floor` at all, or the
    `floor=` seam swallowing the default. Under either, the store records a
    floor that describes no process, and Task 2 would compute
    `block_bytes = budget - floor - headroom` from a number nobody measured.
    """
    import xarray as xr

    from tests.conftest import STUB_FLOOR_COMPONENTS

    report = run(_config(tmp_path, _store(tmp_path)), tmp_path / "out.zarr")

    stored = xr.open_zarr(str(report.store_path)).attrs["floor"]
    print(f"\nmeasured floor: {stored}")
    assert 120e6 < stored["post_warm_bytes"] < 500e6
    assert stored["with_input_bytes"] >= stored["post_warm_bytes"]
    assert stored["post_warm_bytes"] > stored["pre_warm_bytes"]
    assert stored["peak_bytes"] >= max(stored["components"].values())
    # ...and it is NOT the stub, which is the half that makes this a control.
    assert stored["components"] != STUB_FLOOR_COMPONENTS
    assert stored["with_input_bytes"] != STUB_FLOOR_COMPONENTS["input_open"]


def test_a_supplied_floor_is_used_instead_of_a_measurement(tmp_path):
    """The seam overrides, and the store records what the run actually used.

    Expected values determined independently: they are the ones handed in, and
    they are outside any real machine's ladder so a measurement could not
    produce them by accident.

    Bug this catches: the parameter being accepted and ignored -- the
    `observed`-recorded-and-ignored shape Task 5 of 2a already found once, and
    the reason that seam exists at all is that a test needs to construct a state
    this machine will not produce.
    """
    import xarray as xr

    from metamer.core.memory import FloorReport

    supplied = FloorReport(
        pre_warm_bytes=11_000_000,
        post_warm_bytes=22_000_000,
        with_input_bytes=33_000_000,
        peak_bytes=44_000_000,
        components={"constructed": 33_000_000},
    )
    report = run(
        _config(tmp_path, _store(tmp_path)), tmp_path / "out.zarr", floor=supplied
    )

    stored = xr.open_zarr(str(report.store_path)).attrs["floor"]
    assert stored["pre_warm_bytes"] == 11_000_000
    assert stored["post_warm_bytes"] == 22_000_000
    assert stored["with_input_bytes"] == 33_000_000
    assert stored["peak_bytes"] == 44_000_000
    assert stored["components"] == {"constructed": 33_000_000}


def test_the_iteration_cap_reaches_the_fits_and_an_uncapped_run_does_not_cap(tmp_path):
    """The `max_iter` seam, with the positive control that makes it falsifiable.

    **THE CALIBRATION'S WHOLE CLAIM IS "IT DRIVES THE PRODUCTION PATH", WHICH IS
    A PURE NEGATIVE** -- nothing observable says a harness was *not* used. What
    is observable is the cap arriving at the optimizer through `run()`, and the
    store already records it: `/primitives/iterations` per candidate and
    `/status/outcome`, whose `ITER_CAP_*` members are what a stopped fit gets.

    Expected values determined independently, measured 2026-08-15 before this
    test was written: at `max_iter=1` over `white` and `white + matern12` on
    white noise, 128 fits give `ITER_CAP_LARGE_GRAD` 114 and
    `ITER_CAP_SMALL_GRAD` 14 and **no `OK` at all**; at the default cap they
    give 87 `OK` and 41 `DEGENERATE_HESSIAN`. So "no OK, iterations at the cap"
    and "some OK, iterations above the cap" are the two regimes, and they are
    asserted separately rather than as a difference (i3).

    Bug this catches: `run()` accepting `max_iter` and not passing it, which
    makes every calibration a full-cost converged run reporting itself as
    capped -- and, in the other direction, a default run silently capped, which
    would ship a product that never converges. **The pair is what separates
    them**: neither assertion alone can tell a seam that does nothing from a
    seam that does everything.
    """
    import xarray as xr

    # **WHITE NOISE, NOT THE MODULE'S ZERO-FILLED INPUT.** A record of exact
    # zeros drives sigma to its lower diagnostic limit and comes back
    # `DIAGNOSTIC_LIMIT` for every point at every cap -- measured -- so the
    # uncapped half of the pair could never produce an `OK` and the control
    # would be vacuous. This is the handoff's fixture fact about
    # `DIAGNOSTIC_LIMIT` reached through sigma rather than through rho, met from
    # the other side.
    dataset = xr.Dataset(
        {
            "sla": (
                ("time", "y", "x"),
                np.random.default_rng(0).standard_normal((60, 2, 3)).astype("float32"),
            )
        },
        coords={"time": _months(60), "y": np.arange(2), "x": np.arange(3)},
    )
    uri = str(tmp_path / "noise.zarr")
    dataset.to_zarr(uri)
    config = _config(tmp_path, uri)
    capped = run(config, tmp_path / "capped.zarr", max_iter=1)
    default = run(config, tmp_path / "default.zarr")

    capped_iterations = xr.open_zarr(
        str(capped.store_path), group="primitives"
    ).iterations.values
    default_iterations = xr.open_zarr(
        str(default.store_path), group="primitives"
    ).iterations.values
    capped_outcome = xr.open_zarr(str(capped.store_path), group="status").outcome.values
    default_outcome = xr.open_zarr(
        str(default.store_path), group="status"
    ).outcome.values

    assert capped_iterations.max() == 1
    assert not (capped_outcome == Outcome.OK.code).any()
    assert (capped_outcome == Outcome.ITER_CAP_LARGE_GRAD.code).any()

    assert default_iterations.max() > 1
    assert (default_outcome == Outcome.OK.code).any()

    # **THE CAP IS NOT IN ANY HASH, AND THAT IS DELIBERATE AND DANGEROUS.** It
    # is a `run()` argument rather than a config field, because a cap in the
    # config would move `fit_hash` and a calibration would then key on a
    # different fit identity from the run whose memory it measures -- which
    # destroys the cache key at Task 5. The cost is that these two stores, whose
    # CONTENTS differ completely, agree on all three hashes. Provenance is what
    # tells them apart, and this asserts both halves.
    assert capped.fit_hash == default.fit_hash
    assert capped.run_hash == default.run_hash
    assert xr.open_zarr(str(capped.store_path)).attrs["max_iter"] == 1
    assert xr.open_zarr(str(default.store_path)).attrs["max_iter"] == 200


def test_a_run_records_the_basis_that_produced_its_tile_side(tmp_path):
    """No calibration exists yet, so the only honest basis is the shipped default.

    Expected value determined independently from design doc 13.4's vocabulary:
    a constant is (a) cached, (b) measured this session, or (c) a shipped
    default. Phase 2b Task 5 is what makes (a) and (b) reachable; until then a
    run that used the analytic formula must say so.

    Bug this catches: the attr defaulting to `cached` or `measured`, which would
    make Task 6's refusal name calibration for a run that never calibrated --
    sending the user to a cache that does not exist while the real cause was the
    budget.
    """
    import xarray as xr

    report = run(_config(tmp_path, _store(tmp_path)), tmp_path / "out.zarr")

    stored = xr.open_zarr(str(report.store_path)).attrs
    assert stored["tile_side_basis"] == "default"
    # **BOUNDED, NOT PINNED.** v4 is the version that introduced
    # `tile_side_basis`, which is this test's subject; pinning the current value
    # here made it fail at Task 3's bump for a reason unrelated to the basis,
    # and a test that fails for the wrong reason teaches its next reader that
    # editing the number is the fix. `test_store.py`'s ledger owns the value.
    assert stored["schema_version"] >= 4


def test_the_budget_is_si_gigabytes_and_not_gibibytes(tmp_path):
    """`memory_budget_gb` is 10**9 bytes, decided at Phase 2b Task 2.

    Expected value determined independently: `run()` must derive the same side
    as `tile_side_for` called with `budget * 10**9`, and a DIFFERENT one from
    `budget * 1024**3`, which is 7.4% more bytes. The fixture picks a budget
    where the two land on different multiples of the base, or the assertion
    below cannot fail -- (i7), a fixture placed off the point where the two
    functions agree.

    Bug this catches: the `1024**3` this ran on until 2026-08-15. The field is
    named `_gb`, every published tile side in this project is a 10**9 number,
    and the Hardware table already reports this machine as 16.54 GB -- the SI
    reading -- so the runner and the documentation meant different things by one
    word. **The correction lowers the budget**, which is the safe direction.
    """
    from metamer.batch.tiling import tile_side_for
    from metamer.core.memory import FloorReport
    from tests.conftest import STUB_FLOOR_PEAK

    floor = FloorReport(
        pre_warm_bytes=STUB_FLOOR_PEAK,
        post_warm_bytes=STUB_FLOOR_PEAK,
        with_input_bytes=STUB_FLOOR_PEAK,
        peak_bytes=STUB_FLOOR_PEAK,
        components={"override": STUB_FLOOR_PEAK},
    )
    # 0.1 GB gives 384 under SI and 400 under GiB. **0.05 GB gives 272 under
    # BOTH** -- the rounding absorbs the 7.4% there -- and this test was written
    # at 0.05 first and passed against a runner still using `1024**3`. That is
    # (i7) in one line: a fixture placed where the two functions agree.
    # p_max is 3, not 2: `white + matern12` has three free parameters (both
    # sigmas and the timescale), and the ragged index says so -- read from it
    # rather than counted by eye, since a wrong p_max here would make this test
    # agree with a runner doing something else.
    budget = 0.1
    shape: dict[str, Any] = {
        "d": 1,
        "k_beta": 4,
        "p_max": 3,
        "n_time": 24,
        "n_models": 2,
    }
    si = tile_side_for(budget_bytes=int(budget * 10**9), floor=floor, **shape)
    gib = tile_side_for(budget_bytes=int(budget * 1024**3), floor=floor, **shape)
    # THE FIXTURE CAN FAIL: the two units give different sides here.
    assert si != gib
    assert si < gib

    report = run(
        _config(tmp_path, _store(tmp_path), extra=f"memory_budget_gb = {budget}\n"),
        tmp_path / "out.zarr",
    )
    assert report.tile_side == si


def test_a_budget_below_the_process_floor_is_a_layer_three_refusal(tmp_path):
    """The refusal reaches the user as exit code 3, naming the floor.

    Expected behaviour determined independently: conftest pins the floor at
    1 MB, so a budget of 0.0000001 GB -- 100 bytes -- cannot clear it.

    Bug this catches: `BudgetTooSmallError` escaping as a bare `ValueError`,
    which CPython reports as exit code 1 -- and 1 means "completed with failures
    above threshold" in this taxonomy, i.e. **the opposite fact about the run**.
    A caller that resumes on 1 would resume from a crash. Staging it as layer 3
    is what makes the code say "your request is wrong".
    """
    with pytest.raises(ValidationError) as caught:
        run(
            _config(tmp_path, _store(tmp_path), extra="memory_budget_gb = 0.0000001\n"),
            tmp_path / "out.zarr",
        )

    assert caught.value.layer is ValidationLayer.SEMANTIC
    message = str(caught.value)
    assert "1.0 MB" in message
    assert "override" in message  # the floor's rungs, which here is the override
    assert "leaves nothing for a tile" in message


def test_the_identity_gate_refuses_before_the_budget_does(tmp_path):
    """A wrong candidate list and a small budget: the candidates are reported.

    Design doc 13.7 orders the entry contract identity-first, geometry-second.
    The tiling step only became able to FAIL at Phase 2b Task 2, so until then
    deriving the side above the gates was harmless; after it, a derivation above
    the gates makes this run report the budget.

    Expected behaviour determined independently: the store below was fitted with
    two candidates, this run asks for three, and its budget cannot hold three
    candidates' output slots -- so both refusals are live and exactly one of
    them is the right answer.

    Bug this catches: the budget refusal preempting the resume gate, which sends
    a user to raise their budget when the real problem is that these fits are
    not the ones they asked for. **The two send them to different places.**
    """
    uri = _store(tmp_path)
    store = tmp_path / "out.zarr"
    run(_config(tmp_path, uri), store)

    with pytest.raises(ValidationError) as caught:
        run(
            _config(
                tmp_path,
                uri,
                extra='objective = "reml"\nmemory_budget_gb = 0.0000001\n',
                name="reml.toml",
            ),
            store,
        )
    message = str(caught.value)
    # BOTH refusals are live: the objective moves `fit_hash`, and the budget
    # cannot clear the 1 MB floor. Exactly one of them is the right answer.
    assert "fit_hash" in message
    assert "leaves nothing for a tile" not in message

    # THE POSITIVE CONTROL: the same tiny budget against a store whose identity
    # matches DOES reach the budget refusal, so the assertion above is about
    # ordering rather than about the budget check being unreachable (i2).
    with pytest.raises(ValidationError) as budget_refusal:
        run(
            _config(
                tmp_path,
                uri,
                extra="memory_budget_gb = 0.0000001\n",
                name="small.toml",
            ),
            store,
        )
    assert "leaves nothing for a tile" in str(budget_refusal.value)


def test_an_out_of_range_memory_budget_is_a_schema_failure(tmp_path):
    """A command-line budget goes through the same pydantic constraint.

    Bug this catches: an override applied with `model_copy`, which does NOT
    re-validate -- a budget of 0 or -1 would then be accepted from the command
    line while the identical value in the file is refused, so the same run is
    valid or invalid depending on where the number was typed.
    """
    config = _config(tmp_path, _store(tmp_path))
    with pytest.raises(ValidationError) as caught:
        run(config, tmp_path / "out.zarr", memory_budget_gb=0.0)
    assert caught.value.layer is ValidationLayer.SCHEMA


def test_a_degenerate_candidate_warns_and_the_run_still_completes(tmp_path):
    """The identifiability lint reaches the report as a warning, not a refusal.

    It runs after stage 4a because it needs a sampling interval, which is a
    property of the data. That it cannot move the outcome is what makes running
    it there safe -- see `batch.validation`'s module docstring.

    Bug this catches: the lint never being wired in at all. It is easy to write
    `identifiability_warnings` and never call it, and nothing else in the run
    would report the omission.
    """
    config = _config(tmp_path, _store(tmp_path)).with_suffix(".toml")
    config.write_text(
        config.read_text().replace('["white", "white + matern12"]', '["white + white"]')
    )
    report = run(config, tmp_path / "out.zarr")
    assert [finding.rule.value for finding in report.warnings] == ["nugget_collapse"]


def test_a_clean_run_carries_no_warnings(tmp_path):
    """The control: the good config warns about nothing.

    Bug this catches: a warning channel that reports findings unconditionally,
    which would satisfy the test above without the lint ever being consulted.
    """
    assert (
        run(_config(tmp_path, _store(tmp_path)), tmp_path / "out.zarr").warnings == ()
    )


def test_the_contract_report_carries_a_usable_sampling_interval(tmp_path):
    """`median_dt` is measured where the decimal-year axis already exists.

    Expected value derived independently: the fixture steps 31 days at a time
    from 2000-01-01, so every gap is 31 days and the median in decimal years is
    31/366 for the leap year the axis starts in.

    Bug this catches: a sampling interval taken as `(t_end - t_start) / n_time`,
    which is off by a factor of `(n-1)/n` and is silently wrong on any gapped
    axis -- and the lint's white-collapse rule compares a timescale against it.
    """
    report = run(_config(tmp_path, _store(tmp_path)), tmp_path / "out.zarr")
    assert report.contract.median_dt == pytest.approx(31 / 366, rel=1e-3)


# --------------------------------------------------------------------------
# Exit codes, through a process boundary
# --------------------------------------------------------------------------


def test_a_clean_run_exits_zero_and_its_last_line_carries_both_hashes(tmp_path):
    """Exit code 0, and the final line's contract.

    The final line carries `fit_hash`, `compat_hash` and the store path,
    because those three are what a later resume compares and what a user pastes
    into a bug report.

    Bug this catches: a runner that prints its summary and then exits nonzero,
    or one that exits zero having printed nothing -- and a final line that omits
    the store path, which is the only part of the line that says *which* store
    the hashes belong to.
    """
    config = _config(tmp_path, _store(tmp_path))
    store = tmp_path / "out.zarr"
    result = _invoke(str(config), str(store))

    assert result.returncode == ExitCode.OK
    final = result.stdout.strip().splitlines()[-1]
    assert "fit_hash=" in final
    assert "compat_hash=" in final
    assert str(store) in final
    assert "not computed" not in final


def test_a_budget_above_available_ram_warns_and_still_exits_zero(tmp_path):
    """The availability warning is a warning, through a real process boundary.

    **NEVER A GATE, AND THE REASON IS THE ONE THAT RULED OUT AN AVAILABLE-RAM
    DEFAULT.** A refusal here would make a run's success depend on ambient
    machine state, so a store that resumed this morning would refuse this
    afternoon -- design doc section 15.5's burst-and-resume argument again, from
    the other side. So it prints and the code stays 0.

    **The fixture moves the BUDGET rather than the availability, and that is
    what makes the claim expressible at all (k).** An exit code is a property of
    a process, so this has to run out of process, where no monkeypatch of
    `psutil` survives. Availability and the budget are the two sides of one
    inequality: 100 000 GB is above any development machine's free memory --
    asserted below rather than assumed -- so the warning must fire with nothing
    patched.

    Bug this catches: the warning promoted to a refusal, which someone will
    attempt on the grounds that overcommitting memory is bad. **And the second
    invocation is the (i2) control**: "the warning does not move the exit code"
    is satisfied for free by a warning that never fires, so the same command
    under a budget the machine can hold must print no such line and also exit 0.
    """
    config = _config(tmp_path, _store(tmp_path))
    assert machine.available_ram_bytes() < 100_000 * 10**9

    warned = _invoke(str(config), str(tmp_path / "big.zarr"), "--memory-budget", "1e5")
    assert warned.returncode == ExitCode.OK
    assert "warning: memory:" in warned.stderr
    assert "100000 GB" in warned.stderr

    quiet = _invoke(str(config), str(tmp_path / "small.zarr"), "--memory-budget", "0.5")
    assert quiet.returncode == ExitCode.OK
    assert "warning: memory:" not in quiet.stderr


@pytest.mark.parametrize(
    ("extra", "replace"),
    [
        ("\n[screening]\nenabled = true\n", None),
        ("", ('["aic", "hqic"]', '["aic", "not_a_criterion"]')),
        ("", ('"annual"', '"regressor_field:gia"')),
    ],
    ids=["screening", "unknown-criterion", "per-point-regressor"],
)
def test_each_layer_3_refusal_exits_three(tmp_path, extra, replace):
    """Exit code 3, from three different layer-3 faults.

    Three faults rather than one, because a runner that mapped **everything**
    to 3 would satisfy any single case. The layer-4 test below is what makes
    that failure visible; these are what make it visible within layer 3.

    Bug this catches: an early return that exits 0 after refusing -- the
    refusal is printed, the process reports success, and a shell script driving
    a thousand configs records a clean sweep.
    """
    config = _config(tmp_path, _store(tmp_path))
    if replace is not None:
        config.write_text(config.read_text().replace(*replace))
    config.write_text(config.read_text() + textwrap.dedent(extra))

    result = _invoke(str(config), str(tmp_path / "out.zarr"))
    assert result.returncode == ExitCode.CONFIG_INVALID
    assert "layer 3 (semantic)" in result.stderr


def test_a_missing_config_file_exits_three(tmp_path):
    """Exit code 3 from layer 1, which shares the code with layers 2 and 3.

    Bug this catches: `FileNotFoundError` escaping unstaged. Python reports an
    unhandled exception as exit code **1**, which in this taxonomy means
    "completed with failures above threshold" -- a run that finished badly
    rather than one that never started.
    """
    result = _invoke(str(tmp_path / "absent.toml"), str(tmp_path / "out.zarr"))
    assert result.returncode == ExitCode.CONFIG_INVALID
    assert "layer 1 (file)" in result.stderr
    assert "Traceback" not in result.stderr


def test_an_input_that_violates_the_contract_exits_four(tmp_path):
    """Exit code 4, and it is a DIFFERENT code from every layer-3 fault above.

    Bug this catches: layer 4 folded into exit code 3, which makes the staging
    decorative -- "your config is wrong" and "your data is wrong" send a user to
    different places, and that split is the entire reason validation is staged.
    """
    dataset = xr.Dataset(
        {"sla": (("time", "y"), np.zeros((6, 2), dtype="float32"))},
        coords={"time": _months(6), "y": np.arange(2)},
    )
    dataset.to_zarr(tmp_path / "flat.zarr")

    result = _invoke(
        str(_config(tmp_path, str(tmp_path / "flat.zarr"))),
        str(tmp_path / "out.zarr"),
    )
    assert result.returncode == ExitCode.DATA_INVALID
    assert "layer 4 (data)" in result.stderr
    assert "Traceback" not in result.stderr


def test_a_usage_error_exits_three_and_not_argparses_own_two():
    """**argparse exits 2 on a usage error, and 2 means "aborted early".**

    Expected value derived from the taxonomy rather than from argparse: a run
    that never started is not a run that aborted early, and code 2's producer
    is sub-phase 2e's early-abort mechanism.

    Bug this catches: leaving `ArgumentParser.error` at its default. Nothing
    would look wrong -- the usage message is correct and the exit is nonzero --
    and a caller branching on 2 would treat a typo'd command line as a run that
    started, evaluated its abort criterion and stopped.
    """
    result = _invoke()
    assert result.returncode == ExitCode.CONFIG_INVALID
    assert result.returncode != ExitCode.ABORTED_EARLY


def test_code_one_has_no_producer_and_code_two_now_does(tmp_path):
    """Re-pointed at Task 10, because code 2's status changed.

    **This test used to say both 1 and 2 were unreachable**, and its own
    docstring required it to be re-pointed the moment one of them acquired a
    producer rather than to be re-run. Task 10 gave 2 one: a run flushed by
    SIGTERM exits `ABORTED_EARLY`, which is design doc 14.3's "aborted early --
    resumable". That producer is tested where the signal is,
    `tests/test_completion.py`, across a process boundary.

    What is still true and is what this asserts: **neither code arises from an
    ordinary run or from a rejected config**, so 1 remains without a producer
    and 2 is not reachable by accident.

    Bug this catches: a member deleted on the grounds that nothing produces it,
    and an ordinary clean run drifting onto a nonzero code.
    """
    assert ExitCode.COMPLETED_WITH_FAILURES.value == 1
    assert ExitCode.ABORTED_EARLY.value == 2

    config = _config(tmp_path, _store(tmp_path))
    reachable = {
        _invoke(str(config), str(tmp_path / "out.zarr")).returncode,
        _invoke(str(tmp_path / "absent.toml"), str(tmp_path / "out.zarr")).returncode,
    }
    assert reachable == {ExitCode.OK, ExitCode.CONFIG_INVALID}


# --------------------------------------------------------------------------
# The thread budget, wired (Task 5)
# --------------------------------------------------------------------------


def test_the_run_observes_its_own_thread_limits_rather_than_being_told_them(tmp_path):
    """`run` observes, and the layer-3 check Task 4 wired is no longer vacuous.

    Task 4 landed `check_thread_limits` with `observed=None` skipping it, and
    pinned that vacuity so it was a recorded state rather than a belief. This is
    the test that makes it non-vacuous: the run establishes a budget, observes
    every library, and hands the table to layer 3 without a caller supplying it.

    Bug this catches: `run` continuing to pass None. The check would then exist,
    be tested in isolation, be called on every run, and never be able to fire --
    which would satisfy exit criterion 10 with a check that observes nothing.
    Every entry is asserted equal to the request, so a table containing one
    library, or numba's mask left unset, fails here.
    """
    config = _config(tmp_path, _store(tmp_path), extra="\nthreads = 1\n")
    report = run(config, tmp_path / "out.zarr")

    assert len(report.thread_limits) >= 2
    assert set(report.thread_limits.values()) == {1}
    assert NUMBA_KEY in report.thread_limits


def test_the_machine_fingerprint_reaches_the_run_hash(tmp_path):
    """`run_hash` is computed WITH the platform's fingerprint.

    `machine_fingerprint` is an identity and until this task nothing in `src/`
    populated it. It is provenance today -- never a gate -- and section 11.4's
    calibration cache key is where it becomes one, which is why it is wired from
    the platform now rather than at the moment the cache exists.

    Bug this catches: `run` calling `config.run_hash(geometry_hash=...)` with no
    machine, which is what it did before this task. The hash is well-formed
    either way, so the omission is invisible without comparing against the
    hash the same config produces WITHOUT a fingerprint -- which is the
    comparison made here.
    """
    report = run(_config(tmp_path, _store(tmp_path)), tmp_path / "out.zarr")

    assert report.machine == machine.fingerprint()
    assert report.run_hash == report.config.run_hash(
        machine=report.machine, geometry_hash=report.geometry_hash
    )
    assert report.run_hash != report.config.run_hash(geometry_hash=report.geometry_hash)


def test_thread_counts_stay_out_of_both_gates(tmp_path):
    """Changing `threads` moves `run_hash` and neither `fit_hash` nor `compat_hash`.

    **The determinism guarantee and the hash boundary are the same claim stated
    twice** (section 11.3): if thread count moved `fit_hash`, the boundary would
    be conceding that the guarantee does not hold.

    Bug this catches: `threads` added to either allowlist -- at which point two
    runs of the same science at different thread counts stop sharing a store and
    a finished 10^7-point run refits. Each expected value is spelled out rather
    than asserted as a relation between the two moves, because "both moved" and
    "neither moved" satisfy an equality equally well.
    """
    uri = _store(tmp_path)
    one = run(
        _config(tmp_path, uri, extra="\nthreads = 1\n"),
        tmp_path / "a.zarr",
    )
    two = run(
        _config(tmp_path, uri, extra="\nthreads = 2\n", name="d.toml"),
        tmp_path / "b.zarr",
    )

    assert one.fit_hash == two.fit_hash
    assert one.compat_hash == two.compat_hash
    assert one.run_hash != two.run_hash


def test_asking_for_more_threads_than_the_machine_has_exits_three(tmp_path):
    """An unhonourable thread request is a layer-3 failure through the process.

    **Measured:** `numba.set_num_threads(1000)` raises on a 4-core box. Staged,
    that is exit code 3; unstaged it is an unhandled exception and Python
    reports **exit code 1**, which this taxonomy defines as "completed with
    failures above threshold" -- a run that finished badly rather than a config
    that was never runnable.

    Bug this catches: the budget raising a bare `ValueError`. The distinction is
    invisible in-process, because both look like an exception; it is only the
    process's exit code that differs, which is why this is a subprocess test.
    """
    config = _config(tmp_path, _store(tmp_path), extra="\nthreads = 100000\n")
    result = _invoke(str(config), str(tmp_path / "out.zarr"))

    assert result.returncode == ExitCode.CONFIG_INVALID
    assert "layer 3 (semantic)" in result.stderr
    assert "Traceback" not in result.stderr


def test_a_mismatched_observation_reaches_layer_3_through_the_runner(tmp_path):
    """The observation is what layer 3 checks, not a value the run discarded.

    `report.thread_limits` alone cannot establish this: a run that observes the
    limits, records them, and hands `None` to layer 3 produces an identical
    report. **Measured -- that mutation survived** until this test existed.

    Bug this catches: exactly that. The check would then be called on every run,
    tested in isolation, and unable to fire -- which is exit criterion 10
    satisfied by a check that observes nothing. The table is supplied here
    because this machine cannot be made to disagree with itself on demand; the
    unmocked disagreement lives in `tests/test_threads.py`, where OpenBLAS
    clamps an over-large request.
    """
    config = _config(tmp_path, _store(tmp_path), extra="\nthreads = 1\n")
    with pytest.raises(ValidationError) as caught:
        run(config, tmp_path / "out.zarr", observed_thread_limits={"openblas": 99})
    assert caught.value.layer is ValidationLayer.SEMANTIC
    assert "openblas" in str(caught.value)
