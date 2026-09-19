"""Section 14.1's early abort as an ACTION: the drop, the abort, and exit 1.

The verdict itself is `tests/test_abort.py`'s. Everything here takes a verdict
as given -- most tests inject one -- because the question is what the run DOES
with it, and a fit cannot be asked to fail above 90% on demand.
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import xarray as xr
import zarr

from metamer.batch import twopass
from metamer.batch.abort import (
    AbortVerdict,
    CandidateFailurePolicy,
    CandidateRate,
)
from metamer.batch.run import run
from metamer.batch.twopass import run_two_pass
from metamer.batch.validation import ExitCode, ValidationError, ValidationLayer
from metamer.core.outcomes import Outcome

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")

_CONFIG = """
data_uri = "{uri}"
variable = "sla"
signal_terms = ["constant", "trend", "annual"]
candidates = ["white", "white + matern12"]
criteria = ["aic", "hqic"]

[warm_start]
coarse_stride = 2
"""


def _months(n: int) -> np.ndarray:
    origin = np.datetime64("2000-01-01")
    return np.array([origin + np.timedelta64(31 * i, "D") for i in range(n)])


def _input(tmp_path: Path, *, masked_rows: slice | None = None) -> str:
    """A small real input with seeded noise, optionally masking rows."""
    values = np.random.default_rng(3).normal(size=(24, 6, 6)).astype("float32")
    if masked_rows is not None:
        values[:, masked_rows, :] = np.nan
    dataset = xr.Dataset(
        {"sla": (("time", "y", "x"), values)},
        coords={"time": _months(24), "y": np.arange(6), "x": np.arange(6)},
    )
    path = tmp_path / "in.zarr"
    dataset.to_zarr(path)
    return str(path)


def _config(tmp_path: Path, uri: str, name: str = "c.toml") -> Path:
    path = tmp_path / name
    path.write_text(textwrap.dedent(_CONFIG.format(uri=uri)))
    return path


def _group(store: Path, name: str) -> zarr.Group:
    group = zarr.open_group(str(store), mode="r")[name]
    assert isinstance(group, zarr.Group)
    return group


def _outcome(store: Path) -> np.ndarray:
    array = _group(store, "status")["outcome"]
    assert isinstance(array, zarr.Array)
    return np.asarray(array[:])


def _labels(store: Path) -> tuple[str, ...]:
    array = _group(store, "status")["m"]
    assert isinstance(array, zarr.Array)
    return tuple(str(v) for v in np.asarray(array[:]).tolist())


def _early_abort(store: Path) -> dict[str, Any]:
    """The store's recorded verdict, typed for reading."""
    attrs = zarr.open_group(str(store), mode="r").attrs
    value: dict[str, Any] = json.loads(json.dumps(attrs["early_abort"]))
    return value


def _verdict(action: str, labels: tuple[str, ...], over: int) -> AbortVerdict:
    """A verdict naming candidate `over` as failing, all others clean."""
    rates = tuple(
        CandidateRate(
            candidate=label,
            failed=19 if index == over else 1,
            eligible=20,
            rate=0.95 if index == over else 0.05,
        )
        for index, label in enumerate(labels)
    )
    return AbortVerdict(
        action=action,  # type: ignore[arg-type]
        candidates=(labels[over],) if action == "drop" else (),
        rates=rates,
        threshold=0.90,
        reason=f"{labels[over]} failed above 90% of the coarse pass",
    )


# --------------------------------------------------------------------------
# The drop, at `run`
# --------------------------------------------------------------------------


def test_a_dropped_candidate_is_dropped_everywhere_and_moves_no_hash(tmp_path):
    """Every point says `candidate_dropped`, and the identity is untouched.

    Expected values determined independently: the same config run without the
    drop. The hashes are compared against that run's, not against anything this
    test derives, and the retained candidate's outcomes are compared column for
    column.

    Bug this catches: a drop implemented by removing the candidate from the set.
    That changes the store's shape and both gate hashes -- **so a resumed pass 2
    would refuse its own store**, silently defeating section 12.8's gate, and the
    store would be incomparable to the same configuration run on a day when
    nothing was dropped.
    """
    uri = _input(tmp_path)
    config = _config(tmp_path, uri)
    plain = run(config, tmp_path / "plain.zarr")
    label = _labels(tmp_path / "plain.zarr")[1]

    demoted = run(config, tmp_path / "demoted.zarr", dropped=frozenset({label}))

    codes = _outcome(tmp_path / "demoted.zarr")
    assert (codes[:, :, 1] == Outcome.CANDIDATE_DROPPED.code).all()
    np.testing.assert_array_equal(
        codes[:, :, 0], _outcome(tmp_path / "plain.zarr")[:, :, 0]
    )
    assert demoted.fit_hash == plain.fit_hash
    assert demoted.compat_hash == plain.compat_hash


def test_a_drop_naming_an_unknown_candidate_is_refused(tmp_path):
    """A demotion that names nothing must not report that it dropped something.

    Expected value determined independently: the candidate set is the config's,
    and a label outside it cannot be demoted -- a layer-3 refusal, because it is
    a request inconsistent with the configuration and resuming will not help.

    Bug this catches: an unknown label silently ignored. The run would finish,
    exit 1 on the strength of a drop that never happened, and the store would
    hold no `candidate_dropped` anywhere.
    """
    config = _config(tmp_path, _input(tmp_path))

    with pytest.raises(ValidationError) as caught:
        run(config, tmp_path / "out.zarr", dropped=frozenset({"no such model"}))

    assert caught.value.layer is ValidationLayer.SEMANTIC
    assert "no such model" in str(caught.value)


# --------------------------------------------------------------------------
# The action, at the two-pass driver
# --------------------------------------------------------------------------


def test_a_drop_keeps_pass_one_evidence_and_records_its_rule(tmp_path, monkeypatch):
    """Pass 1 keeps its real outcomes; pass 2 records why it dropped.

    Expected values determined independently: pass 1 is written before the
    verdict exists, so its outcomes must be what the fit produced -- read here
    from a store the verdict never touched. The recorded threshold and policy
    are the ones this test passes in.

    Bug this catches: two of them. Overwriting pass 1's cells with
    `candidate_dropped`, **which destroys the only record of why the candidate
    was demoted** and makes the run's own justification unreproducible from its
    artifacts. And not recording the rule: the threshold and the policy are
    command-line flags that exist nowhere in the store, so without the attr
    section 14.2's report could see `candidate_dropped` and could not say what
    put it there.
    """
    config = _config(tmp_path, _input(tmp_path))
    seen: list[Path] = []

    def _inject(path: Path | str, **_: object) -> AbortVerdict:
        seen.append(Path(path))
        return _verdict("drop", _labels(Path(path)), over=1)

    monkeypatch.setattr(twopass, "abort_verdict", _inject)

    report = run_two_pass(
        config,
        tmp_path / "out.zarr",
        candidate_failure_policy=CandidateFailurePolicy.DROP,
    )

    assert report.pass1_path is not None and report.pass2 is not None
    pass1 = _outcome(report.pass1_path)
    assert not (pass1 == Outcome.CANDIDATE_DROPPED.code).any()
    assert (
        _outcome(report.store_path)[:, :, 1] == Outcome.CANDIDATE_DROPPED.code
    ).all()

    recorded = _early_abort(report.store_path)
    assert recorded["evaluated"] is True
    assert recorded["action"] == "drop"
    assert recorded["policy"] == "drop"
    assert recorded["threshold"] == 0.90
    assert recorded["population"] == "pass 1 coarse grid"
    assert recorded["dropped"] == [_labels(report.store_path)[1]]
    assert seen == [report.pass1_path]


def test_an_abort_writes_no_pass_two_and_is_not_a_preemption(tmp_path, monkeypatch):
    """`aborted` and `interrupted` are different facts, though both exit 2.

    Expected values determined independently: an abort is decided after a
    COMPLETE pass 1, so nothing is outstanding -- and pass 2 never starts, so its
    store never exists.

    Bug this catches: an abort reported as a preemption. A resuming script told
    "tiles outstanding, the same command resumes" would rerun forever, reaching
    the same verdict each time; what lifts an abort is a different request, and
    only a report that can tell the two apart can say so.

    **PROVED TO BITE 2026-09-16:** `interrupted` was made to count an aborted
    pass 2 as outstanding, and this test failed on `interrupted is False`.
    """
    config = _config(tmp_path, _input(tmp_path))
    monkeypatch.setattr(
        twopass,
        "abort_verdict",
        lambda path, **_: _verdict("abort", _labels(Path(path)), over=1),
    )

    report = run_two_pass(config, tmp_path / "out.zarr")

    assert report.pass2 is None
    assert report.aborted is True
    assert report.interrupted is False
    assert not (tmp_path / "out.zarr").exists()


def test_no_early_abort_disables_a_decision_and_not_a_computation(
    tmp_path, monkeypatch
):
    """The flag skips the verdict and pass 2 fits what `continue` would.

    Expected values determined independently: a second run of the same config
    under an injected `continue` verdict, compared array for array.

    Bug this catches: the flag changing what is fitted -- skipping pass 1's
    demotion bookkeeping in a way that alters pass 2, or evaluating the verdict
    anyway. **The injected verdict raises**, so a consultation fails the test
    rather than passing silently.
    """
    config = _config(tmp_path, _input(tmp_path))

    def _forbidden(*_: object, **__: object) -> AbortVerdict:
        raise AssertionError("--no-early-abort must not consult the verdict")

    monkeypatch.setattr(twopass, "abort_verdict", _forbidden)
    off = run_two_pass(config, tmp_path / "off.zarr", early_abort=False)

    monkeypatch.setattr(
        twopass,
        "abort_verdict",
        lambda path, **_: AbortVerdict("continue", (), (), 0.90, "clean"),
    )
    kept = run_two_pass(config, tmp_path / "kept.zarr")

    assert off.verdict is None
    for group, name in (("status", "outcome"), ("primitives", "log_lik")):
        mine = _group(off.store_path, group)[name]
        theirs = _group(kept.store_path, group)[name]
        assert isinstance(mine, zarr.Array) and isinstance(theirs, zarr.Array)
        np.testing.assert_array_equal(np.asarray(mine[:]), np.asarray(theirs[:]))
    assert _early_abort(off.store_path) == {
        "evaluated": False,
        "reason": "--no-early-abort",
    }


def test_a_second_process_reaches_the_same_verdict_on_the_same_store(tmp_path):
    """Resume-consistency, from the verdict's purity rather than by hope.

    A resumed two-pass run re-enters the barrier and re-evaluates the verdict.
    If it could move, a resume could demote a candidate the first process kept,
    **leaving one candidate with `candidate_dropped` in some tiles and fits in
    others, with nothing recording why.**

    Expected value determined independently: the verdict is a pure function of a
    frozen pass-1 store (2e Task 5), so it cannot move -- asserted here against
    the REAL verdict, not an injected one, across two driver calls.

    Bug this catches: any process-local input to the decision -- a cached table,
    a clock, a policy default read from the environment. The second call finds
    every tile complete, so it does no fitting and differs from the first only
    in being a new invocation.
    """
    config = _config(tmp_path, _input(tmp_path))
    policy = CandidateFailurePolicy.CONTINUE

    first = run_two_pass(config, tmp_path / "out.zarr", candidate_failure_policy=policy)
    codes = _outcome(first.store_path)
    second = run_two_pass(
        config, tmp_path / "out.zarr", candidate_failure_policy=policy
    )

    assert first.verdict is not None
    assert second.verdict == first.verdict
    np.testing.assert_array_equal(_outcome(second.store_path), codes)


def test_an_empty_coarse_sample_continues_loudly_when_the_fine_grid_has_data(
    tmp_path,
):
    """The criterion-1 shape, pinned -- and the decision it pins is (b), taken.

    Masking every even row leaves a stride-2 coarse lattice with no eligible
    point while the odd rows carry data. The verdict then has **no evidence**,
    and the run continues to pass 2 with its own third outcome recorded.

    Expected value determined independently: `abort_verdict` on the pass-1
    store this shape produces has an empty denominator for every candidate,
    and the fine grid has 3 of 6 rows of data, so pass 2 has tiles to write
    and nothing to warm-start them from.

    **INVERTED 2026-09-18, NOT DELETED.** This test pinned reading (a) -- the
    abort -- from 2026-09-16, when its docstring said it was the test that
    changes if the question goes the other way. It went the other way on
    2026-09-18, for the reasons at section 14.1: an empty coarse sample is a
    statement about the SAMPLE, and this fixture is the proof; a wrong abort
    is recovered only by disabling the mechanism everywhere; and section 14.1
    aborts on near-total failure patterns, of which an empty sample is none.

    Bug this catches: the abort still standing; or the empty sample collapsed
    into `continue`, which reads as a clean pass and is the silent failure
    section 14.1's thresholds exist to prevent; or a reason that still names
    `--no-early-abort` as a lift for a run that is not blocked.
    """
    config = _config(tmp_path, _input(tmp_path, masked_rows=slice(None, None, 2)))

    report = run_two_pass(config, tmp_path / "out.zarr")

    assert report.aborted is False
    assert report.interrupted is False
    assert report.verdict is not None
    assert report.verdict.action == "no_evidence"
    assert all(rate.eligible == 0 for rate in report.verdict.rates)
    assert "no evidence" in report.verdict.reason
    assert "--no-early-abort" not in report.verdict.reason
    # CONTINUES, POSITIVELY: pass 2 fitted the fine grid and seeded nothing.
    assert report.pass2 is not None
    assert report.pass2.tiles_written > 0
    assert report.pass2.warm_start is not None
    assert report.pass2.warm_start.warm_started == 0
    assert (_outcome(report.store_path) == Outcome.OK.code).any()
    recorded = _early_abort(report.store_path)
    assert recorded["evaluated"] is True
    assert recorded["action"] == "no_evidence"
    assert recorded["dropped"] == [] and recorded["above_threshold"] == []


def test_a_no_evidence_run_exits_ok_with_the_headline_on_the_final_line(tmp_path):
    """Loudly, in a real process: exit 0 and the headline on stderr.

    Expected values determined independently: section 14.3 defines exit 1 as
    the verdict finding a candidate above threshold, and a no-evidence verdict
    found none, so the code is 0; section 14.1's rule for the drop -- a
    headline line, not a buried counter -- applies to the third outcome by
    the same argument. Run in a SUBPROCESS against the REAL fixture, with no
    injected verdict, because the loudness is a property of the process and
    the `_INJECT` harness cannot express an empty sample.

    Bug this catches: the mechanism continuing and saying nothing -- the
    verdict recorded in the store and absent from the terminal, which is where
    an operator at hour nine is looking. Or the headline sending them to
    `--no-early-abort`, which lifts nothing here.
    """
    config = _config(tmp_path, _input(tmp_path, masked_rows=slice(None, None, 2)))
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "metamer",
            str(config),
            str(tmp_path / "out.zarr"),
            "--two-pass",
            "--no-progress",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == ExitCode.OK, result.stderr
    assert "Traceback" not in result.stderr
    assert "early abort: no evidence" in result.stderr
    assert "--no-early-abort" not in result.stderr
    assert "aborted early" not in result.stderr
    assert (tmp_path / "out.zarr").exists()


def test_a_one_pass_run_has_no_verdict_and_says_so(tmp_path, monkeypatch):
    """Reading (i): no coarse pass, no early abort, and no exit 1.

    Expected value determined independently from section 14.1's own argument:
    the abort is evaluated on pass 1's stratified sample, and
    `warm_start.enabled = false` writes no pass 1.

    Bug this catches: a one-pass run consulting the verdict on something else --
    the full store's first tiles, which is the geographic prefix section 14.1
    spends four paragraphs forbidding. **The injected verdict raises**, and the
    store records that nothing was evaluated rather than recording nothing.
    """
    uri = _input(tmp_path)
    config = tmp_path / "one.toml"
    config.write_text(
        textwrap.dedent(_CONFIG.format(uri=uri)).replace(
            "coarse_stride = 2", "enabled = false"
        )
    )

    def _forbidden(*_: object, **__: object) -> AbortVerdict:
        raise AssertionError("a one-pass run has no sample to judge")

    monkeypatch.setattr(twopass, "abort_verdict", _forbidden)

    report = run_two_pass(config, tmp_path / "out.zarr")

    assert report.pass1 is None and report.verdict is None
    recorded = _early_abort(report.store_path)
    assert recorded["evaluated"] is False
    assert "one-pass" in recorded["reason"]


# --------------------------------------------------------------------------
# The exit codes, in a real process
# --------------------------------------------------------------------------

_INJECT = """
import sys
from pathlib import Path

import numpy as np
import zarr

from metamer import __main__ as entry
from metamer.batch import twopass
from metamer.batch.abort import AbortVerdict, CandidateRate

ACTION, OVER = sys.argv[1], int(sys.argv[2])


def _inject(path, **kwargs):
    group = zarr.open_group(str(path), mode="r")["status"]
    labels = tuple(str(v) for v in np.asarray(group["m"][:]).tolist())
    rates = tuple(
        CandidateRate(label, 19 if i == OVER else 1, 20,
                      0.95 if i == OVER else 0.05)
        for i, label in enumerate(labels)
    ) if OVER >= 0 else tuple(
        CandidateRate(label, 1, 20, 0.05) for label in labels
    )
    over = (labels[OVER],) if OVER >= 0 else ()
    return AbortVerdict(
        ACTION, over if ACTION == "drop" else (), rates, 0.90,
        f"{over} failed above 90% of the coarse pass",
    )


twopass.abort_verdict = _inject
sys.exit(entry.main(sys.argv[3:]))
"""


@pytest.mark.parametrize(
    ("action", "over", "policy", "expected"),
    [
        ("drop", 1, "drop", ExitCode.COMPLETED_WITH_FAILURES),
        ("continue", 1, "continue", ExitCode.COMPLETED_WITH_FAILURES),
        ("abort", 1, "abort", ExitCode.ABORTED_EARLY),
        ("continue", -1, "abort", ExitCode.OK),
    ],
)
def test_the_verdict_reaches_the_process_exit_code(
    tmp_path, action, over, policy, expected
):
    """Exit 1 is produced, and only by a threshold the run finished past.

    **EXIT 1's DEFINITION IS 2e's, BECAUSE THE DESIGN DOC NEVER GAVE ONE.**
    Section 14.3 says "completed with failures above threshold" and names no
    threshold; the only one this project has is section 14.1's, which decides a
    drop. So: the verdict found a candidate above it, and the run completed
    anyway -- under `drop` or `continue`. `abort` is 2; nothing above is 0.

    Expected values determined independently from that definition, with the
    verdict injected so the fit is not asked to fail on demand. Run in a
    SUBPROCESS because an exit code is a property of a process.

    Bug this catches: exit 1 reported for a clean run, or withheld from a run
    that finished past a failing candidate -- and the caveat missing. **Without
    "COARSE pass" on the final line, exit 1 reads as a statement about the run,
    and it is a statement about a sample.**

    **PROVED TO BITE 2026-09-16:** exit 1's branch was disabled and the `drop`
    and `continue` rows failed with exit 0, while `abort` and the clean row
    passed.
    """
    config = _config(tmp_path, _input(tmp_path))
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            _INJECT,
            action,
            str(over),
            str(config),
            str(tmp_path / "out.zarr"),
            "--two-pass",
            f"--on-candidate-failure={policy}",
            "--no-progress",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == expected, result.stderr
    if expected == ExitCode.COMPLETED_WITH_FAILURES:
        assert "COARSE pass" in result.stderr
    if expected == ExitCode.ABORTED_EARLY:
        assert "--on-candidate-failure=drop" in result.stderr
        assert "SIGTERM" not in result.stderr
    assert "Traceback" not in result.stderr
