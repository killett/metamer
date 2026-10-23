"""`python -m metamer.report <store>`: describe a store, never write to it.

Writes `report.json`, `report.md` and the maps' PNGs **beside the store** --
`<parent>/<store name>.report/`, never inside it -- or to `--out <dir>`.

**THE ORDER IS THE CONTRACT, AND A TEST HOLDS EACH STEP TO IT** (2f Task 8's
pre-flight, §3): arguments, then output writability, then `read_store`, then
the sections -- the permutation null lives in `clustering.compute` -- then the
writes. A report that computed for minutes and then could not save is the one
failure that wastes a user's time entirely, so nothing is computed until the
output is known to be writable.

**EXIT CODES ARE D13's TABLE, AND A REPORT's CODE DESCRIBES THE REPORT**, never
the run it describes:

- 0 -- the report was written.
- 3 -- usage: the parser refused the command line (as `metamer.__main__`'s
  `_Parser` does), or the output directory is unwritable or inside the store.
  Both are arguments the caller supplied that cannot be honoured.
- 4 -- the store: the reader's `InputContractError` and nothing else. That is
  the batch run's code for the same exception (`exit_code_for`), carried here
  rather than imported because the validator sits behind this package's import
  boundary; a test holds the two equal.
- 5 -- an internal error, with its traceback.

**1 and 2 are not producible**, and this module does not name them: 1 is a
property of a run whose verdict found a candidate above threshold, 2 of a
resumable run, and a report is neither.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from collections.abc import Sequence
from pathlib import Path
from typing import NoReturn

from metamer.batch.input import InputContractError
from metamer.exitcodes import ExitCode

#: The two artifacts, by name, inside the output directory.
RECORD_NAME = "report.json"
MARKDOWN_NAME = "report.md"

#: The probe file the writability check writes and removes.
_PROBE_NAME = ".metamer-report-write-check"


class _Parser(argparse.ArgumentParser):
    """An `ArgumentParser` whose usage errors exit 3 rather than argparse's 2.

    The batch CLI's `_Parser`, restated because importing it would import the
    run driver this package's boundary excludes. argparse's 2 means *aborted
    early, resumable* in this project's table.
    """

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

    Returns:
        The parser.
    """
    parser = _Parser(
        prog="python -m metamer.report",
        description=(
            "Describe a metamer store -- its outcomes, rates, selectability, "
            "provenance, the clustering of its failures and its maps -- without "
            "writing to it."
        ),
    )
    parser.add_argument("store", help="path to the zarr store to describe")
    parser.add_argument(
        "--out",
        default=None,
        metavar="DIR",
        help=(
            "directory for report.json, report.md and the PNGs; defaults to "
            "<store>.report beside the store, never inside it"
        ),
    )
    return parser


def default_out(store: Path) -> Path:
    """The output directory when `--out` is absent: beside the store, not in it.

    **"BESIDE" IS THE PARENT DIRECTORY, DEFINED BEFORE THE CODE**, because a
    report run against a store whose directory refuses writes must still
    succeed, and output inside the store would make that impossible.

    Args:
        store: The store's path.

    Returns:
        `<parent>/<store name>.report`.
    """
    return store.parent / f"{store.name}.report"


def _inside(path: Path, store: Path) -> bool:
    """Whether `path` is the store or anything under it, after resolution."""
    resolved, root = path.resolve(), store.resolve()
    return resolved == root or root in resolved.parents


def _prepare(out: Path) -> Path | None:
    """Make `out` exist and prove it writable; return the topmost dir created.

    **A REAL WRITE, NOT `os.access`**, which answers for the real uid on some
    platforms and ignores read-only mounts on others.

    Args:
        out: The output directory.

    Returns:
        The outermost directory this call created, so a run that fails before
        writing anything can remove it, or None if `out` already existed.

    Raises:
        OSError: If the directory cannot be created or written.
    """
    created: Path | None = None
    for candidate in (out, *out.parents):
        if candidate.exists():
            break
        created = candidate
    out.mkdir(parents=True, exist_ok=True)
    probe = out / _PROBE_NAME
    probe.write_text("")
    probe.unlink()
    return created


def _discard(created: Path | None, out: Path) -> None:
    """Remove the directories `_prepare` created, if nothing was written in them."""
    if created is None:
        return
    for directory in (out, *out.parents):
        try:
            directory.rmdir()
        except OSError:
            return
        if directory == created:
            return


def main(argv: Sequence[str] | None = None) -> int:
    """Run the report.

    Args:
        argv: The arguments after the program name; `sys.argv[1:]` if None.

    Returns:
        The exit code, from D13's table.
    """
    args = _build_parser().parse_args(argv)
    store = Path(args.store)
    out = Path(args.out) if args.out is not None else default_out(store)

    if _inside(out, store):
        print(
            f"{out} is inside the store {store}; the report never writes to "
            "the store it describes. Choose an output directory outside it",
            file=sys.stderr,
        )
        return ExitCode.CONFIG_INVALID
    try:
        created = _prepare(out)
    except OSError as error:
        print(
            f"the output directory {out} is not writable ({error}); nothing "
            "was computed",
            file=sys.stderr,
        )
        return ExitCode.CONFIG_INVALID

    try:
        return _report(store, out)
    except InputContractError as error:
        _discard(created, out)
        print(f"{store}: {error}", file=sys.stderr)
        return ExitCode.DATA_INVALID
    except Exception:  # noqa: BLE001 - the catch-all IS the contract: 5, not 1
        _discard(created, out)
        traceback.print_exc()
        return ExitCode.INTERNAL_ERROR


def _report(store: Path, out: Path) -> int:
    """Read, compute, write the record, then render the markdown FROM THE FILE.

    Args:
        store: The store to describe.
        out: A directory already proven writable.

    Returns:
        `ExitCode.OK`.
    """
    # Imported here, after the writability check, so a usage or output error
    # costs no import of the numerical stack.
    from metamer.report.reader import read_store
    from metamer.report.record import build
    from metamer.report.render import render

    view = read_store(store)
    record = build(view, out)
    record_path = out / RECORD_NAME
    record_path.write_text(json.dumps(record, indent=2, allow_nan=False) + "\n")
    # **THE MARKDOWN IS RENDERED FROM THE FILE JUST WRITTEN**, parsed back --
    # not from `record` -- so it is a function of the saved artifact by
    # construction.
    markdown = render(json.loads(record_path.read_text()))
    (out / MARKDOWN_NAME).write_text(markdown)
    print(f"wrote {record_path} and {out / MARKDOWN_NAME}")
    return ExitCode.OK


if __name__ == "__main__":
    sys.exit(main())
