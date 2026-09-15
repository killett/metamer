"""`python -m metamer <config.toml> <store>`: argparse, one screen.

**`python -m`, NOT `metamer run <config>` VIA `console_scripts`.** Naming a
subcommand presupposes the tree it belongs to and designs the argument structure
now rather than in Phase 5, when `validate` and `report` are real. `python -m`
presupposes nothing and reads as provisional, which it is.

**ARGPARSE EXITS 2 ON A USAGE ERROR AND 2 MEANS "ABORTED EARLY".** A mistyped
command line would otherwise report the code that means a run started,
evaluated its abort criterion and stopped. `_Parser` overrides `error` so a
usage failure exits `CONFIG_INVALID`, which is what it is.

**PYTHON EXITS 1 ON AN UNHANDLED EXCEPTION AND 1 MEANS "COMPLETED WITH FAILURES
ABOVE THRESHOLD".** ~~That collision is not fixable inside a taxonomy with no
internal-error code, and it is harmless only while 1 has no producer.~~
**CLOSED AT 2e's TASK 1, 2026-09-12:** `ExitCode.INTERNAL_ERROR` is the sixth
code and `main` carries a catch-all, so a crash exits 5 and 1 is left to the
failure-rate threshold that 2e's Task 6 wires.

**THE CATCH-ALL WRAPS `main`'s WHOLE BODY, AND THAT IS NOT A STYLE CHOICE.** The
`try` around `run` spans the fit and its staged handler and nothing else: the
identifiability warnings, the budget and calibration warnings, the entire
printed report block and the `report.interrupted` branch all sit AFTER it.
Appending `except Exception` to that `try` type-checks, passes a test that
crashes inside `run`, and **leaves every reporting path exiting 1** -- so the
guard is an outer frame rather than another clause. There is a second,
independent reason: `exit_code_for` raises `TypeError` on a non-staged type and
is called from INSIDE the staged `except`, so the handler for the honest
failures has its own crash path, and only an outer frame sees it.

**IT CATCHES `Exception`, NEVER `BaseException`.** `_Parser.error` raises
`SystemExit(ExitCode.CONFIG_INVALID)` and `--version` raises `SystemExit(0)`.
A `BaseException` catch-all would report a clean `--version` as an internal
error and swallow `KeyboardInterrupt` -- converting the paths that are already
right into the one code that means the run did not finish.
"""

from __future__ import annotations

import argparse
import sys
import traceback
from collections.abc import Callable, Sequence
from typing import NoReturn

import numpy as np
from numpy.typing import NDArray

from metamer import __version__
from metamer.batch.input import InputContractError
from metamer.batch.run import RunReport, run
from metamer.batch.tiling import Tile
from metamer.batch.twopass import run_two_pass
from metamer.batch.validation import ExitCode, ValidationError, exit_code_for, layer_of
from metamer.progress import LiveCounters


class _Parser(argparse.ArgumentParser):
    """An `ArgumentParser` whose usage errors exit 3 rather than argparse's 2."""

    def error(self, message: str) -> NoReturn:
        """Print usage and exit with the config-invalid code.

        Args:
            message: What argparse could not parse.

        Raises:
            SystemExit: Always, with `ExitCode.CONFIG_INVALID`.
        """
        self.print_usage(sys.stderr)
        print(f"{self.prog}: {message}", file=sys.stderr)
        raise SystemExit(ExitCode.CONFIG_INVALID)


def _build_parser() -> _Parser:
    """Return the argument parser.

    **`--reuse-fits-from` LANDED AT TASK 12, WITH ITS BEHAVIOUR.** It was
    deliberately absent until then -- a flag that parses and does nothing reads
    as supported -- and the same rule ran the other way: Task 11's criterion-set
    refusal named the *operation* rather than this flag until the flag existed.
    Both halves are the same rule, which is that a diagnostic and a command line
    must not describe different programs.

    Returns:
        The parser.
    """
    parser = _Parser(
        prog="python -m metamer",
        description=(
            "Fit stochastic noise models over a gridded time series and select "
            "among them by information criteria."
        ),
    )
    parser.add_argument("config", help="path to a .toml or .json run configuration")
    parser.add_argument("store", help="path to the zarr store to write")
    parser.add_argument(
        "--memory-budget",
        type=float,
        default=None,
        metavar="GB",
        dest="memory_budget",
        help=(
            "override the configuration's memory_budget_gb. Peak RAM is derived "
            "from this alone, so it is the only knob on concurrency"
        ),
    )
    parser.add_argument(
        "--reuse-fits-from",
        default=None,
        metavar="STORE",
        dest="reuse_fits_from",
        help=(
            "recompute the derived arrays from a finished store's primitives "
            "instead of fitting. The new store is self-contained and records "
            "the source's hashes as provenance; its fit_hash equals the "
            "source's and its compat_hash and run_hash do not"
        ),
    )
    parser.add_argument(
        "--calibrate",
        action="store_true",
        help=(
            "measure bytes per series before tiling, reusing a cached "
            "measurement filed under this run's key. Opt-in because it is "
            "expensive: the shipped ladder is hours at production sizes. "
            "Without it the tile is sized by the analytic formula and the "
            "store records that as its basis"
        ),
    )
    parser.add_argument(
        "--recalibrate",
        action="store_true",
        help=(
            "measure even if the cache has an entry, and overwrite it. Implies "
            "--calibrate. The cache has no expiry -- time does not cause the "
            "change an expiry stands in for -- so this is the only override"
        ),
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        dest="no_progress",
        help=(
            "suppress section 14.1's per-tile counters. They go to stderr and "
            "are display-only -- nothing in the run reads them -- so this "
            "changes what is printed and nothing about what is computed"
        ),
    )
    parser.add_argument(
        "--two-pass",
        action="store_true",
        dest="two_pass",
        help=(
            "fit a coarse pass first and warm-start the full grid from it "
            "(Phase 2c). The coarse store is written beside the output as "
            "<store>.pass1.<ext> and is a PERMANENT artifact: it is the only "
            "record of what the same points fit to without a warm start. "
            "warm_start.enabled = false in the configuration makes this one "
            "cold pass and writes no coarse store"
        ),
    )
    parser.add_argument("--version", action="version", version=f"metamer {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line and return its exit code.

    **This docstring is true because of the catch-all below**, and it was false
    before 2e's Task 1: an unhandled exception left `main` without returning, so
    `sys.exit(main())` never ran and CPython supplied its own 1.

    Args:
        argv: Arguments, defaulting to `sys.argv[1:]`.

    Returns:
        One of `ExitCode`. Never raises `Exception`; `SystemExit` from argparse
        and `KeyboardInterrupt` pass through untouched, which is what keeps
        `--version`, `--help` and a usage error exiting as they already do.
    """
    try:
        return _run(argv)
    except Exception:
        # THE TRACEBACK IS EMITTED, NOT MERELY PERMITTED -- (i2): an absence is
        # not a signal. The CODE carries the fact that this was a crash and the
        # TRACEBACK carries which one, so neither has to be inferred from the
        # other. A caller that only reads the code still learns the right thing.
        traceback.print_exc()
        print(
            "internal error: the run did not finish and no map was written; "
            "this is a defect in metamer, not in your configuration or data",
            file=sys.stderr,
        )
        return ExitCode.INTERNAL_ERROR


def _run(argv: Sequence[str] | None) -> int:
    """The command line proper, guarded by `main`.

    Args:
        argv: Arguments, defaulting to `sys.argv[1:]`.

    Returns:
        One of `ExitCode`.
    """
    parser = _build_parser()
    arguments = parser.parse_args(argv)

    # **REFUSED AT THE PARSER, WHICH IS WHERE A COMBINATION OF FLAGS BELONGS.**
    # A recompute fits nothing, so there is no optimizer for a warm start to
    # start; `run` refuses the same pair inside, and this one exists so the
    # message names the two FLAGS a user typed rather than the two arguments
    # they became.
    if arguments.two_pass and arguments.reuse_fits_from is not None:
        parser.error(
            "--two-pass fits the grid twice and --reuse-fits-from does not fit "
            "at all; a recompute has no optimizer for a warm start to start"
        )

    # SECTION 14.1's COUNTERS ARE CONSTRUCTED HERE, OUTSIDE `metamer.batch`,
    # AND THAT IS THE ENFORCEMENT OF "NO DECISION MAY READ THEM". The run gets
    # a callback returning None and never imports this type; see
    # `metamer.progress` and `tests/test_progress.py`'s import boundary.
    #
    # STDERR, NOT STDOUT. The end-of-run report is stdout and is what a caller
    # pipes; progress is transient and would corrupt it. Warnings already go
    # here for the same reason.
    counters = LiveCounters()
    pass1_counters = LiveCounters()

    def _progress(
        target: LiveCounters, label: str
    ) -> Callable[[Tile, NDArray[np.uint8], tuple[str, ...]], None]:
        def record(
            tile: Tile, outcome: NDArray[np.uint8], candidates: tuple[str, ...]
        ) -> None:
            target.record(tile, outcome, candidates)
            for line in target.lines():
                print(f"{label}{line}", file=sys.stderr)

        return record

    progress = None if arguments.no_progress else _progress(counters, "")
    pass1_progress = (
        None if arguments.no_progress else _progress(pass1_counters, "pass 1 ")
    )

    pass1: RunReport | None = None
    pass1_seconds: float | None = None
    try:
        if arguments.two_pass:
            two = run_two_pass(
                arguments.config,
                arguments.store,
                memory_budget_gb=arguments.memory_budget,
                calibrate=arguments.calibrate,
                recalibrate=arguments.recalibrate,
                on_tile_progress=progress,
                on_pass1_tile_progress=pass1_progress,
            )
            pass1, pass1_seconds = two.pass1, two.pass1_seconds
            if two.pass2 is None:
                # PASS 1 STOPPED SHORT AND PASS 2 NEVER STARTED. Exit 2, not 3:
                # the store is resumable and the same command finishes it. This
                # is the case the driver returns before the barrier for -- the
                # barrier's refusal is layer 3 and would report a preempted run
                # as an invalid request.
                outstanding = (
                    0
                    if pass1 is None
                    else pass1.tiles_total - pass1.tiles_written - pass1.tiles_skipped
                )
                print(
                    f"aborted early: pass 1 has {outstanding} tiles outstanding "
                    "after SIGTERM and pass 2 has not started; the same command "
                    "resumes",
                    file=sys.stderr,
                )
                return ExitCode.ABORTED_EARLY
            report = two.pass2
        else:
            report = run(
                arguments.config,
                arguments.store,
                memory_budget_gb=arguments.memory_budget,
                reuse_fits_from=arguments.reuse_fits_from,
                calibrate=arguments.calibrate,
                recalibrate=arguments.recalibrate,
                on_tile_progress=progress,
            )
    except (ValidationError, InputContractError) as error:
        # LAYER 4's TYPE CARRIES NO LAYER PREFIX OF ITS OWN, so the naming
        # happens here for both. That keeps "each layer names itself" satisfied
        # without Task 2's exception having to know about validation staging --
        # which is the same separation that lets `InputContractError` stay the
        # thing exit code 4 rests on.
        layer = layer_of(error)
        prefix = (
            ""
            if isinstance(error, ValidationError)
            else f"layer {layer.value} ({layer.name.lower()}): "
        )
        print(f"{prefix}{error}", file=sys.stderr)
        return exit_code_for(error)

    for finding in report.warnings:
        print(f"warning: identifiability: {finding.message}", file=sys.stderr)

    # A WARNING, PRINTED WHERE WARNINGS GO, AND IT DOES NOT REACH THE RETURN
    # BELOW. Availability is ambient machine state; gating on it would make a
    # store that resumed this morning refuse this afternoon.
    if report.budget_warning is not None:
        print(f"warning: memory: {report.budget_warning}", file=sys.stderr)

    # A MEASUREMENT THE BAND REFUSED IS REPORTED AND NEVER FATAL. The run used
    # the analytic formula, which is what it would have used without
    # `--calibrate`, so nothing is degraded and there is nothing to abort for --
    # but a user who waited for a measurement has to learn it was discarded.
    if report.calibration_warning is not None:
        print(f"warning: calibration: {report.calibration_warning}", file=sys.stderr)

    print(f"input:      {report.config.data_uri}")
    print(
        f"grid:       {report.contract.n_time} x {report.contract.n_y} x "
        f"{report.contract.n_x}  calendar={report.contract.calendar}  "
        f"unique_dt={report.contract.unique_dt}"
    )
    # THE OBSERVED LIMITS, NOT THE REQUESTED ONE. A line reading
    # "threads: 1" would be a record of what was asked for, and section 11.3's
    # determinism precondition is a statement about what took effect.
    observed = "  ".join(
        f"{library}={limit}" for library, limit in sorted(report.thread_limits.items())
    )
    print(f"threads:    requested={report.config.threads}  observed: {observed}")
    print(f"machine:    {report.machine}")
    print(f"run_hash={report.run_hash}  geometry_hash={report.geometry_hash}")
    print(
        f"tiles:      side={report.tile_side}  written={report.tiles_written}  "
        f"skipped={report.tiles_skipped}  of {report.tiles_total}"
    )
    if pass1 is not None and pass1_seconds is not None:
        print(
            f"pass 1:     store={pass1.store_path}  side={pass1.tile_side}  "
            f"tiles={pass1.tiles_total}  {pass1_seconds:.1f} s  "
            "(KEEP IT: the only cold reference for these points)"
        )
    # THE AGGREGATES 2c MEASURES AND §13.4 WILL PRINT PROPERLY. The per-point
    # source map is deliberately not among them -- see `run.WarmStartSummary`.
    if report.warm_start is not None:
        warm = report.warm_start
        farthest = max(warm.radius_histogram, default=0)
        print(
            f"warm start: source={warm.source}  "
            f"{warm.warm_started}/{warm.cells} cells warm  "
            f"{warm.exhausted} exhausted  farthest source {farthest} cells"
        )
    if report.init_rungs:
        rungs = "  ".join(
            f"{name}={count}" for name, count in sorted(report.init_rungs.items())
        )
        print(f"init rungs: {rungs}")
    print(
        f"fit_hash={report.fit_hash}  compat_hash={report.compat_hash}  "
        f"store={report.store_path}"
    )
    if report.interrupted:
        # EXIT 2 IS SECTION 14.3's "ABORTED EARLY -- RESUMABLE", and a preempted
        # run is exactly that: the completed tiles are on disk with their bits
        # set, and the same command finishes the job. Exiting 0 would tell a
        # resuming script the store is complete when it is not.
        print(
            f"aborted early: {report.tiles_total - report.tiles_written - report.tiles_skipped}"
            " tiles outstanding after SIGTERM; the same command resumes",
            file=sys.stderr,
        )
        return ExitCode.ABORTED_EARLY
    return ExitCode.OK


if __name__ == "__main__":
    sys.exit(main())
