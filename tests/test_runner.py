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

import numpy as np
import pytest
import xarray as xr

from metamer.batch.input import InputContractError
from metamer.batch.run import run
from metamer.batch.validation import ExitCode, ValidationError, ValidationLayer

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
    assert default.config.memory_budget_gb == 1.0
    assert overridden.run_hash != default.run_hash
    # The budget is run-relevant and NOT fit-relevant, so the gates must not
    # move. Asserted as its own expected value rather than as a relation:
    # "both moved" and "neither moved" both satisfy an equality between them.
    assert overridden.fit_hash == default.fit_hash
    assert overridden.compat_hash == default.compat_hash


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


def test_the_two_unreachable_codes_have_no_producer_in_this_sub_phase(tmp_path):
    """Codes 1 and 2 are declared and unreachable here, and that is recorded.

    `COMPLETED_WITH_FAILURES` needs a failure-rate threshold and
    `ABORTED_EARLY` needs the early-abort mechanism; both are sub-phase 2e's.
    They land now as an interface because retrofitting an exit code means
    revisiting every early return.

    **The note is executable rather than prose**: the reachable set is asserted
    to be exactly the three this sub-phase can produce, so the moment 2e wires a
    producer this test fails and has to be re-pointed rather than quietly
    outliving its subject.

    Bug this catches: a member deleted on the grounds that nothing produces it,
    which is the retrofit the taxonomy exists to avoid.
    """
    assert ExitCode.COMPLETED_WITH_FAILURES.value == 1
    assert ExitCode.ABORTED_EARLY.value == 2

    config = _config(tmp_path, _store(tmp_path))
    reachable = {
        _invoke(str(config), str(tmp_path / "out.zarr")).returncode,
        _invoke(str(tmp_path / "absent.toml"), str(tmp_path / "out.zarr")).returncode,
    }
    assert reachable == {ExitCode.OK, ExitCode.CONFIG_INVALID}
