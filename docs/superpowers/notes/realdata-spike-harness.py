#!/usr/bin/env python
"""The real-data spike, first half: cold difficulty of real fits, in three arms.

**READ [`realdata-spike-preflight.md`](realdata-spike-preflight.md) FIRST.** This
implements what that document specifies and re-argues none of it.

## The three arms, and why the first is not optional

| arm | field | signal model | what it is for |
|---|---|---|---|
| `control` | 2d's easy rung, construction 2, at `FIELD_SEED` | `constant + trend` | **the known-good** |
| `real_ct` | DUACS monthly SLA, 300 points, `N = 396` | `constant + trend` | comparable to every anchor |
| `real_ctas` | the same store | `+ annual + semiannual` | what you would actually fit |

**THE CONTROL'S EXPECTED VALUE IS AN EQUALITY, NOT A BAND.** Iterations are
deterministic, `src/` has not changed since the anchor was measured
(`git log f409b7f..HEAD -- src/` is empty), and the anchor's own cold arm was
`batch.run.run(config, store, max_iter=None)` followed by
`fields.iteration_count` -- the identical two calls this harness makes. So the
control must return **42.080729166666664** per point and **42.0390625** OK-only,
and anything else says the environment or the tree has moved rather than that
the field has. That is the strongest form (i2) can take here: a low real reading
is exactly what a silently broken pipeline produces, and a band would not have
separated them.

**IT IS ALSO WHY NO DEPENDENCY WAS ADDED TO FETCH THE DATA.** `pixi add` would
have re-solved the lock this equality is asserted under.

## The two real arms differ in exactly one thing

`constant + trend` is what every anchor used and it is **misspecified** against
monthly sea level, which carries a large annual cycle: the seasonal signal lands
in the residual and the noise model absorbs it. That biases difficulty upward --
**toward the answer this measurement exists to be sceptical of** -- which is
(a4)'s worked instance, where contamination pushed a reading toward the number
it was being checked against and ended the search.

**So the misspecification is measured rather than reasoned about.** The gap
between the arms is how much of real difficulty is the ocean and how much is our
model choice, and neither arm alone can say.

## What this harness does NOT measure

No warm start, no coarse grid, no spiral, no barrier, no N2 arm, and no
coherence. **A cold iteration count is a BOUND on the saving and not a
measurement of it.**

Usage:
    realdata-spike-harness.py <out.jsonl> <fixture-dir> [smoke|full]
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, TextIO

import numpy as np
import zarr
from threadpoolctl import threadpool_limits

from metamer.batch.run import run
from metamer.batch.store import ITERATIONS_UNSET
from metamer.batch.timeaxis import to_decimal_years
from metamer.bench import fields, host
from metamer.config.candidates import parse_candidate
from metamer.config.signal_terms import parse_signal_terms
from metamer.core.criteria import Criterion
from metamer.core.fit import fit
from metamer.core.outcomes import Outcome

#: Where the report lands. **Named here rather than passed**, so the artifact a
#: later check reads cannot be pointed somewhere else by a caller.
REPORT_PATH = Path(__file__).with_name("realdata-spike-report.json")

#: Where a smoke run lands instead. **A separate path, not a flag inside one
#: file**: a smoke report and a measurement report at one filename are the
#: same bytes to anything that reads the path.
SMOKE_REPORT_PATH = Path(__file__).with_name("realdata-spike-smoke.json")

#: The committed anchor, from `phase2d-difficulty-rung-report.json`'s
#: `iterations` block. **Frozen literals, deliberately** -- (j8)'s third
#: register. These are a RECORD of a past value, not a spelling of a current
#: one, and importing them from anywhere would replay the anchor at today's tree.
CONTROL_EXPECTED_PER_POINT = 42.080729166666664
CONTROL_EXPECTED_OK_PER_POINT = 42.0390625

#: The signal model per arm. **The only thing that differs between the two real
#: arms**, which is what makes their difference attributable.
SIGNAL_MODELS: dict[str, tuple[str, ...]] = {
    "control": fields.SIGNAL_TERMS,
    "real_ct": fields.SIGNAL_TERMS,
    "real_ctas": ("constant", "trend", "annual", "semiannual"),
}

#: Take every `KAPPA_STRIDE`-th point for the in-process condition-number pass.
#: **The kappa reading is a DISTRIBUTION, not a rate that must match an anchor**,
#: so it can afford a subsample where the iteration reading cannot.
KAPPA_STRIDE = 5

_CONFIG_TEMPLATE = """\
data_uri = "{uri}"
variable = "sla"
signal_terms = {signal_terms}
candidates = {candidates}
criteria = {criteria}

[audit]
seed = {audit_seed}
"""


def config_text(uri: str, signal_terms: tuple[str, ...]) -> str:
    """The spike's config: the benchmark's, with the signal model as a knob.

    **EVERY OTHER QUANTITY IS IMPORTED FROM `bench.fields`**, so the candidate
    set has one spelling and `M` cannot drift between an arm and its anchor --
    (j9), whose fifth instance in this project was a harness naming its own
    candidate set while `CANDIDATES` grew from two members to three.

    `test_the_spike_config_is_the_benchmark_config` asserts that this template
    at `fields.SIGNAL_TERMS` renders byte-identically to `fields.config_text`,
    which is what stops the knob becoming a second config.

    Args:
        uri: The input store.
        signal_terms: The deterministic model to fit.

    Returns:
        The config file's text.
    """
    return _CONFIG_TEMPLATE.format(
        uri=uri,
        signal_terms=json.dumps(list(signal_terms)),
        candidates=json.dumps(list(fields.CANDIDATES)),
        criteria=json.dumps(list(fields.CRITERIA)),
        audit_seed=fields.AUDIT_SEED,
    )


def emit(handle: TextIO, record: dict[str, Any]) -> None:
    """Append one JSON record and flush."""
    handle.write(json.dumps(record, default=str) + "\n")
    handle.flush()


def _git_head() -> str:
    """The tree this ran on."""
    return subprocess.run(  # noqa: S603
        ["git", "rev-parse", "HEAD"],  # noqa: S607
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def renamed_for_tiling(source: Path, destination: Path) -> dict[str, Any]:
    """Copy a store with its spatial dims renamed to `y` and `x`.

    **THIS IS A WORKAROUND FOR AN OPEN DEFECT AND IT IS NOT A FIX.** The
    pre-flight's F6 is measured: a `(time, latitude, longitude)` input passes
    stage 4a and then dies at `tiling.py`'s `by_dim["y"]` with a `KeyError`,
    unhandled, **exit code 1** -- which the taxonomy defines as "completed with
    failures above threshold". The real store and that failure are both on the
    record, in the committed pre-flight, **before** this rename existed.

    **The rename is what lets a spike measure the science without taking a scope
    decision that belongs to nobody in this session.** Recording it here is what
    stops it reading as support: a positional decimation above a name-based
    assembler does not make such inputs work, and neither does this.

    Args:
        source: The store as the product ships it.
        destination: Where the renamed copy goes.

    Returns:
        What was renamed, for the artifact.
    """
    import shutil

    import xarray as xr

    if destination.exists():
        shutil.rmtree(destination)
    dataset = xr.open_zarr(source, chunks=None, decode_times=True, consolidated=True)
    mapping = {"latitude": "y", "longitude": "x"}
    renamed = dataset.rename(mapping).load()
    for name in (*renamed.data_vars, *renamed.coords):
        renamed[name].encoding.clear()
    values = renamed["sla"]
    renamed.to_zarr(
        destination,
        encoding={"sla": {"chunks": values.shape}},
        consolidated=True,
    )
    return {
        "record": "renamed_for_tiling",
        "source": str(source),
        "destination": str(destination),
        "mapping": mapping,
        "why": (
            "tiling.py names the spatial dims literally; the un-renamed store's "
            "failure is measured in realdata-spike-preflight.md F6 and is the "
            "reading, not this copy"
        ),
    }


def read_iterations(store: Path, arm: str) -> dict[str, Any]:
    """The arm's iteration reading, both ways, off the store.

    **BOTH READINGS, BECAUSE THE ANCHOR CHOSE ONE.** `42.08` is the all-cells
    figure; a capped cell contributes `max_iter`, so on real data the two can
    separate by far more than the 0.04 they differ by on the simulated field --
    in the direction that flatters "real fits are hard".
    """
    everything = fields.iteration_count(store)
    ok_only = fields.iteration_count(store, ok_only=True)
    return {
        "record": "iterations",
        "arm": arm,
        "store": str(store),
        "per_point": everything.per_point,
        "per_cell": everything.per_cell,
        "total": everything.total,
        "points": everything.points,
        "cells": everything.cells,
        "ok_per_point": ok_only.per_point,
        "ok_per_cell": ok_only.per_cell,
        "ok_total": ok_only.total,
        "ok_points": ok_only.points,
        "ok_cells": ok_only.cells,
        "all_minus_ok_per_point": everything.per_point - ok_only.per_point,
    }


def outcome_distribution(store: Path, arm: str) -> dict[str, Any]:
    """The outcome codes over every fitted cell, including the zeros.

    **(a2b) AT A COUNT.** An outcome absent from a histogram and an outcome the
    pipeline cannot reach print the same way, so the count of every reachable
    code is emitted and the fixture's own limit is stated beside it: this box
    has no land and no gaps, so `NOT_ATTEMPTED` cannot appear and a clean
    histogram here is not evidence that a global run is clean.
    """
    root = zarr.open_group(str(store), mode="r")
    written = root["primitives/iterations"]
    outcome = root["status/outcome"]
    if not isinstance(written, zarr.Array) or not isinstance(outcome, zarr.Array):
        raise TypeError("the store's iteration and outcome nodes are not arrays")
    iterations = np.asarray(written[:])
    codes = np.asarray(outcome[:])
    fitted = iterations != ITERATIONS_UNSET
    ok = fitted & (codes == Outcome.OK.code)
    counts = {
        Outcome.from_code(int(code)).name: int((codes[fitted] == code).sum())
        for code in np.unique(codes[fitted])
    }
    capped = fitted & (iterations >= 200)
    return {
        "record": "outcome_distribution",
        "arm": arm,
        "cells_total": int(codes.size),
        "cells_fitted": int(fitted.sum()),
        "cells_ok": int(ok.sum()),
        "ok_fraction": float(ok.sum() / fitted.sum()) if fitted.any() else float("nan"),
        "counts": counts,
        "cells_at_cap": int(capped.sum()),
        "reachable_codes_here": sorted(counts),
        "fixture_limit": (
            "this box has no land, ice or gaps, so NOT_ATTEMPTED is unreachable "
            "and a clean histogram is a property of the box"
        ),
    }


def kappa_pass(
    store: Path, arm: str, signal_terms: tuple[str, ...], stride: int
) -> dict[str, Any]:
    """Condition numbers, from an in-process `fit` over a subsample.

    **THIS IS A SECOND INSTRUMENT AND IT IS NOT A CROSS-CHECK OF THE FIRST.**
    (j5): it differs from the run by code path, which is exactly the difference
    the record refuses to reconcile between 2c's 40.79 and the probe's 43.94.
    **Its iteration counts are therefore not quoted as a second reading of the
    primary quantity** and are emitted under their own names.

    It exists because `kappa` is not in the store: `store._array_specs` declares
    `/primitives/iterations` and `/status/outcome` and no condition-number
    array, so `FitResult.hessian_cond` is the only place it lives.

    **THE READING IS TAKEN OVER EVERY CELL, NOT OVER THE `OK` ONES** -- (h3).
    `optimize.HESSIAN_COND_LIMIT` is `eps**-0.5 = 2**26` and `optimize_series`
    refuses `OK` above it, so a distribution over `OK` cells has already been
    filtered at the boundary anyone would want to cut it at, and "no
    ill-conditioned cells" would be a property of the selection.

    Args:
        store: The store the arm was fitted from (the input, not the output).
        arm: The arm's name.
        signal_terms: The arm's signal model.
        stride: Take every `stride`-th point of the flattened grid.

    Returns:
        The distribution, with the degenerate count beside it.
    """
    import xarray as xr

    dataset = xr.open_zarr(store, chunks=None, decode_times=True, consolidated=True)
    values = np.asarray(dataset["sla"].values, dtype=np.float64)
    n_time = values.shape[0]
    series = values.reshape(n_time, -1).T[::stride]
    t = to_decimal_years(dataset["time"].values)
    mask = np.isfinite(series)

    started = time.perf_counter()
    result = fit(
        series,
        t,
        parse_signal_terms(list(signal_terms)),
        [parse_candidate(name) for name in fields.CANDIDATES],
        Criterion.AIC,
        mask=mask,
    )
    seconds = time.perf_counter() - started

    condition = np.asarray(result.hessian_cond, dtype=np.float64)
    finite = np.isfinite(condition)
    codes = np.asarray(result.outcome)
    degenerate = int((codes == Outcome.DEGENERATE_HESSIAN.code).sum())
    quantiles = (
        [float(v) for v in np.quantile(condition[finite], [0.5, 0.9, 0.99, 1.0])]
        if finite.any()
        else []
    )
    return {
        "record": "kappa",
        "arm": arm,
        "instrument": "in-process core.fit; NOT the run's store path (j5)",
        "stride": stride,
        "points": int(series.shape[0]),
        "cells": int(condition.size),
        "cells_with_defined_kappa": int(finite.sum()),
        "kappa_undefined": int((~finite).sum()),
        "kappa_quantiles_50_90_99_100": quantiles,
        "hessian_cond_limit": float(2.0**26),
        "cells_above_limit": int((condition[finite] > 2.0**26).sum()),
        "degenerate_hessian_cells": degenerate,
        "seconds": seconds,
        "note_iterations_are_not_the_primary_reading": True,
    }


def build_control(directory: Path, *, smoke: bool = False) -> tuple[Path, Path]:
    """Rebuild 2d's easy rung at construction 2, and write its config.

    **THROUGH THE SHIPPED BUILDER AT THE SHIPPED GEOMETRY AND SEED**, so the
    field is the field the anchor was measured on. `write_config` is the
    benchmark's own, which is what makes the control's config identical to the
    anchor's rather than merely equivalent.

    Args:
        directory: Where the field and config go.
        smoke: Build a reduced geometry instead. **A smoke field is NOT the
            anchor's field** -- the rung's parameters are placed relative to a
            boundary at `n_normal // 2`, so a smaller grid is a different field
            and not a subset of the shipped one. `build_field`'s own docstring
            says a non-shipped geometry is marked in the report, and the
            control equality is skipped in this mode for exactly that reason.

    Returns:
        The field's URI and the config path.
    """
    out_dir = directory / ("control-smoke" if smoke else "control")
    out_dir.mkdir(parents=True, exist_ok=True)
    shape = {"n_time": 60, "n_normal": 4, "n_parallel": 3} if smoke else {}
    truth = fields.build_field(
        fields.rung("easy"),
        path=out_dir / "easy-field.zarr",
        seed=fields.FIELD_SEED,
        **shape,
    )
    config_path = fields.write_config(out_dir, "easy.toml", truth.uri)
    return Path(truth.uri), config_path


def decimated(source: Path, destination: Path, stride: int) -> Path:
    """A spatially decimated copy of a store, for the smoke run.

    **THE SERIES ARE UNCHANGED AND ONLY THE POINT SET SHRINKS**, which is what
    makes a smoke run exercise the same wiring at a fraction of the fits. The
    record length is deliberately NOT cut: `N` is the quantity the anchors are
    keyed on, and a smoke run at a different `N` would exercise a different
    regime of the very thing under measurement.
    """
    import shutil

    import xarray as xr

    if destination.exists():
        shutil.rmtree(destination)
    dataset = xr.open_zarr(source, chunks=None, decode_times=True, consolidated=True)
    cut = dataset.isel(y=slice(None, None, stride), x=slice(None, None, stride)).load()
    for name in (*cut.data_vars, *cut.coords):
        cut[name].encoding.clear()
    cut.to_zarr(
        destination,
        encoding={"sla": {"chunks": cut["sla"].shape}},
        consolidated=True,
    )
    return destination


def measure(
    handle: TextIO,
    *,
    arm: str,
    input_store: Path,
    config_path: Path,
    out_store: Path,
    kappa_stride: int,
) -> dict[str, Any]:
    """Run one cold arm, read it three ways, and emit each reading."""
    emit(handle, {"record": "arm_start", "arm": arm, "config": str(config_path)})
    started = time.perf_counter()
    run(config_path, out_store, max_iter=None)
    seconds = time.perf_counter() - started

    iterations = read_iterations(out_store, arm)
    outcomes = outcome_distribution(out_store, arm)
    emit(handle, iterations)
    emit(handle, outcomes)
    emit(handle, {"record": "cost", "arm": arm, "seconds": seconds})

    kappa = kappa_pass(input_store, arm, SIGNAL_MODELS[arm], kappa_stride)
    emit(handle, kappa)

    return {
        "arm": arm,
        "signal_terms": list(SIGNAL_MODELS[arm]),
        "iterations": iterations,
        "outcomes": outcomes,
        "kappa": kappa,
        "seconds": seconds,
    }


def main() -> int:
    """Gate on the host, then measure the three arms in one session."""
    out = Path(sys.argv[1])
    fixtures = Path(sys.argv[2])
    mode = sys.argv[3] if len(sys.argv) > 3 else "full"
    fixtures.mkdir(parents=True, exist_ok=True)

    with out.open("a", encoding="utf-8") as handle:
        emit(
            handle,
            {
                "record": "header",
                "task": "the real-data spike, first half -- cold difficulty",
                "mode": mode,
                "preflight": "realdata-spike-preflight.md",
                "predictions": "realdata-spike-predictions.json",
                "fetch_provenance": "realdata-spike-fetch-provenance.json",
                "git_head": _git_head(),
                "arms": list(SIGNAL_MODELS),
                "signal_models": {k: list(v) for k, v in SIGNAL_MODELS.items()},
                "candidates": list(fields.CANDIDATES),
                "criteria": list(fields.CRITERIA),
                "control_expected_per_point": CONTROL_EXPECTED_PER_POINT,
                "control_expected_ok_per_point": CONTROL_EXPECTED_OK_PER_POINT,
            },
        )

        # **THE GATE REFUSES; IT DOES NOT ANNOTATE.** Task 0's fourth defect was
        # a harness that recorded a loud host and measured anyway.
        reading = host.quiet_check()
        emit(handle, reading.as_record())
        if not reading.quiet:
            emit(handle, {"record": "refused", "reason": host.REFUSAL})
            print(host.REFUSAL, file=sys.stderr)
            return 1

        # **THE CONFIG KNOB IS ASSERTED AGAINST THE BENCHMARK'S BEFORE ANY RUN.**
        # A second config that agrees until one of them moves is (j9), and this
        # harness is the place it would happen.
        probe = str(fixtures / "probe.zarr")
        if config_text(probe, fields.SIGNAL_TERMS) != fields.config_text(probe):
            raise AssertionError(
                "the spike's config template has diverged from bench.fields."
                "config_text; the candidate set or the criteria have two spellings"
            )

        real_named = fixtures / "duacs-monthly.zarr"
        if not real_named.exists():
            raise FileNotFoundError(
                f"{real_named} is missing; run realdata-spike-fetch.py first"
            )
        renamed = fixtures / "duacs-monthly-yx.zarr"
        emit(handle, renamed_for_tiling(real_named, renamed))
        smoke = mode == "smoke"
        if smoke:
            renamed = decimated(renamed, fixtures / "duacs-smoke-yx.zarr", 5)
            emit(handle, {"record": "smoke_decimation", "store": str(renamed)})

        results: list[dict[str, Any]] = []
        with threadpool_limits(limits=1):
            control_input, control_config = build_control(fixtures, smoke=smoke)
            results.append(
                measure(
                    handle,
                    arm="control",
                    input_store=control_input,
                    config_path=control_config,
                    out_store=control_config.parent / "easy-cold.zarr",
                    kappa_stride=8,
                )
            )
            # **THE CONTROL IS CHECKED BEFORE THE REAL ARMS RUN**, so five hours
            # are not spent producing numbers that cannot be compared to
            # anything.
            measured = results[0]["iterations"]["per_point"]
            held = abs(measured - CONTROL_EXPECTED_PER_POINT) < 1e-9
            emit(
                handle,
                {
                    "record": "control_check",
                    "measured_per_point": measured,
                    "expected_per_point": CONTROL_EXPECTED_PER_POINT,
                    "difference": measured - CONTROL_EXPECTED_PER_POINT,
                    "held": held,
                },
            )
            if not held and mode != "smoke":
                emit(
                    handle, {"record": "refused", "reason": "control did not reproduce"}
                )
                print(
                    "the control did not reproduce the committed anchor; the "
                    "environment or the tree has moved and the real readings "
                    "would not be comparable",
                    file=sys.stderr,
                )
                return 1

            for arm in ("real_ct", "real_ctas"):
                config_path = fixtures / f"{arm}.toml"
                config_path.write_text(config_text(str(renamed), SIGNAL_MODELS[arm]))
                results.append(
                    measure(
                        handle,
                        arm=arm,
                        input_store=renamed,
                        config_path=config_path,
                        out_store=fixtures / f"{arm}-cold.zarr",
                        kappa_stride=KAPPA_STRIDE,
                    )
                )

        report = {
            "record": "realdata_spike_report",
            "git_head": _git_head(),
            "quiet": reading.as_record(),
            "arms": results,
            "control_expected_per_point": CONTROL_EXPECTED_PER_POINT,
            "control_expected_ok_per_point": CONTROL_EXPECTED_OK_PER_POINT,
            "instrument": {
                "primary": "batch.run.run then bench.fields.iteration_count",
                "secondary": "in-process core.fit for kappa only, not a cross-check",
                "candidates": list(fields.CANDIDATES),
                "criteria": list(fields.CRITERIA),
                "algorithm_version": __import__(
                    "metamer.core.hashing", fromlist=["ALGORITHM_VERSION"]
                ).ALGORITHM_VERSION,
                "max_iter": 200,
                "threads": 1,
                "seconds_are_the_contaminated_half": (
                    "iterations, outcomes and kappa are host-independent; only "
                    "the cost blocks are"
                ),
                "unique_dt_on_the_real_axis": 6,
            },
        }
        # **A SMOKE RUN MUST NOT OVERWRITE THE ARTIFACT A LATER CHECK READS.**
        # The two would be the same bytes to anything reading the path, which
        # is (a0) at a report: a run that measured the pipeline and a run that
        # measured the ocean would be indistinguishable by filename.
        report["is_a_smoke_run"] = smoke
        destination = SMOKE_REPORT_PATH if smoke else REPORT_PATH
        destination.write_text(json.dumps(report, indent=2, default=str) + "\n")
        emit(handle, {"record": "written", "path": str(destination)})
    return 0


if __name__ == "__main__":
    sys.exit(main())
