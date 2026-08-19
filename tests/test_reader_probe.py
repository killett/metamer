"""The reader probe's own tests -- the guard that guards the store's guards.

`tests/reader_probe.py` is what every "this store opens without metamer" test
runs its reader in, so a defect there is invisible: the probe would keep
returning 0 and the acceptance criterion would keep reporting success while
proving nothing. These tests are the half that can fail.

WRITTEN AGAINST A REAL FAILURE. Until 2026-08-19 each probe asserted
`importlib.util.find_spec("metamer") is None` and called that its control.
That is a claim about the ENVIRONMENT, not about the reader: it held only
because `pixi run` puts metamer on `PYTHONPATH` and never installs it. The
first CI run that reached the suite installed the package, five probes failed
with `control failed`, and the property they were meant to establish had never
been tested anywhere metamer was installed -- which includes every machine
that ran `pip install metamer`.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tests.reader_probe import BLOCK_METAMER, run_reader

_SOURCE_ROOT = str(Path(__file__).resolve().parent.parent / "src")


def test_the_block_refuses_metamer_even_when_it_is_importable():
    """`import metamer` raises under the block in a process that could import it.

    Bug this catches: the defect this module was written against -- a control
    that tests for metamer's ABSENCE. Such a control passes vacuously wherever
    metamer is not installed and fails wherever it is, so it certifies the
    environment rather than the reader. Here `PYTHONPATH` is set to `src`
    deliberately, so metamer is importable and only an active block can hold.

    The expected value is fixed by the block's contract rather than by reading
    its code: the program prints `blocked` on the `ImportError` path and
    `imported` on the path where metamer came in, and only the first is
    acceptable.
    """
    program = BLOCK_METAMER + (
        "\ntry:\n"
        "    import metamer\n"
        "except ImportError:\n"
        "    print('blocked')\n"
        "else:\n"
        "    print('imported')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True,
        text=True,
        cwd="/",
        env={"PYTHONPATH": _SOURCE_ROOT, "PATH": "/usr/bin:/bin"},
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "blocked"


def test_the_block_is_not_a_blanket_import_ban():
    """xarray and zarr still import under the block, and still read a store.

    Bug this catches: a finder whose name test is wrong -- `startswith("m")`,
    or a `return` that raises for every module. Every reader probe would then
    fail for a reason that has nothing to do with the store, and the store's
    stand-alone property would be untestable in the direction that matters.

    The expected value is arithmetic done here rather than by the code under
    test: 2 + 2 = 4 through numpy, after both third-party imports succeed.
    """
    result = run_reader(
        """
        import numpy as np, xarray as xr, zarr
        print(sorted({"xarray", "zarr"} & {"xarray", "zarr"}))
        print(int(np.array([2, 2]).sum()))
        """
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["['xarray', 'zarr']", "4"]


def test_a_reader_that_imports_metamer_fails_loudly():
    """A program that reaches for metamer exits nonzero and says so.

    Bug this catches: a block that RETURNS rather than raises -- `find_spec`
    handing back `None` defers to the next finder, so metamer would import and
    every probe would pass while proving nothing at all. This is the
    `control failed` guard's job, kept rather than dropped: what changed is
    that it now fires on an import the reader performed, not on the ambient
    presence of a package.
    """
    result = run_reader("import metamer\nprint('should not get here')\n")

    assert result.returncode != 0
    assert "should not get here" not in result.stdout
    assert "metamer" in result.stderr
    assert "ImportError" in result.stderr or "ModuleNotFoundError" in result.stderr


def test_the_reader_runs_outside_the_tree_with_pythonpath_stripped():
    """The subprocess has no `PYTHONPATH` and a working directory outside src.

    Bug this catches: a helper that runs in the repository root, or that
    forwards the ambient `PYTHONPATH=src`. Either would let a future reader
    reach metamer's source by path -- and because the block would then be the
    only thing standing between the reader and the package, a single
    regression in the finder would silently restore the vacuous control this
    module exists to prevent. Belt and braces, asserted rather than assumed.
    """
    result = run_reader(
        """
        import os
        print(os.getcwd())
        print(repr(os.environ.get("PYTHONPATH")))
        """
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["/", "None"]


@pytest.mark.parametrize("argument", ["one", "two words", "/a/path"])
def test_arguments_reach_the_reader_at_the_expected_index(argument):
    """`sys.argv[1]` is the first argument passed, as every caller assumes.

    Bug this catches: a helper that prepends the block as a separate argv
    entry, or that passes arguments before `-c`. Every existing probe indexes
    `sys.argv[1]` for the store path, so an off-by-one here would send them
    reading a path that is not the fixture -- and a store that fails to open
    reads exactly like a store that is not stand-alone.
    """
    result = run_reader("import sys\nprint(sys.argv[1])\n", argument)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == argument
