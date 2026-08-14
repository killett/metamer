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
ABOVE THRESHOLD".** That collision is not fixable inside a taxonomy with no
internal-error code, and it is harmless only while 1 has no producer -- in Phase
2a any observed 1 is a crash, with a traceback to say so. Sub-phase 2e is where
1 acquires a producer and where the two must be made distinguishable.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from typing import NoReturn

from metamer import __version__
from metamer.batch.input import InputContractError
from metamer.batch.run import run
from metamer.batch.validation import ExitCode, ValidationError, exit_code_for, layer_of


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
    parser.add_argument("--version", action="version", version=f"metamer {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line and return its exit code.

    Args:
        argv: Arguments, defaulting to `sys.argv[1:]`.

    Returns:
        One of `ExitCode`.
    """
    arguments = _build_parser().parse_args(argv)

    try:
        report = run(
            arguments.config,
            arguments.store,
            memory_budget_gb=arguments.memory_budget,
            reuse_fits_from=arguments.reuse_fits_from,
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
