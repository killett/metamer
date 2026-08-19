"""Run a reader in a subprocess that provably cannot import metamer.

Design doc 12.4's acceptance criterion is that a store opens under plain
`xr.open_zarr` in a process with no metamer in it. Every test of that criterion
needs a control, because a reader that quietly imported metamer would open
anything and prove nothing.

**THE CONTROL MUST NOT BE "METAMER IS ABSENT".** That is a statement about the
environment: it holds under `pixi run`, which puts the package on `PYTHONPATH`
and never installs it, and it fails under `pip install metamer` -- which is
every user, and, from 2026-08-19, CI. Five probes asserted absence, and the
first CI run that reached the suite failed all five with `control failed`. The
criterion had never once been checked in an environment where metamer was
installed, which is the only environment anyone else has.

What is asserted here instead is that the reader CANNOT import metamer: a
meta-path finder refuses the name, and the preamble proves the refusal bites
before the reader runs. That property is identical in both environments, and it
is the one the criterion actually needs. `tests/test_reader_probe.py` is this
module's own guard.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap

# Prepended to every reader program. The trailing control is not decoration:
# a finder that returns instead of raising would defer to the next finder on
# `sys.meta_path`, metamer would import, and each probe would go on passing.
BLOCK_METAMER = textwrap.dedent(
    """
    import sys as _sys


    class _MetamerBlocked:
        def find_spec(self, name, path=None, target=None):
            if name == "metamer" or name.startswith("metamer."):
                raise ImportError(f"{name} is blocked in this reader process")
            return None


    _sys.meta_path.insert(0, _MetamerBlocked())

    try:
        import metamer  # noqa: F401
    except ImportError:
        pass
    else:
        raise AssertionError("control failed: metamer imported through the block")
    """
)


def run_reader(program: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    """Run `program` where metamer is unimportable, outside the source tree.

    Args:
        program: The reader's source. Dedented before use, so it may be written
            as an indented triple-quoted string at the call site. Its arguments
            arrive at `sys.argv[1]` onwards, as with any `python -c` program.
        *arguments: Passed through to the subprocess, typically a store path.

    Returns:
        The completed process, with stdout and stderr captured as text. Callers
        assert on `returncode` and read their values back off stdout.
    """
    return subprocess.run(
        [
            sys.executable,
            "-c",
            BLOCK_METAMER + textwrap.dedent(program),
            *arguments,
        ],
        capture_output=True,
        text=True,
        # Outside the tree, and with `PYTHONPATH` dropped, so that reaching
        # metamer would take both a broken block and a deliberate path change.
        cwd="/",
        env={k: v for k, v in os.environ.items() if k != "PYTHONPATH"},
    )
