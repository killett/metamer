import subprocess
import sys

# The batch layer's dependencies, and the whole of them. `metamer.core` is the
# likelihood spine; a consumer who wants it without the store installs
# `metamer` and not `metamer[batch]`, and that is the contract this module
# holds.
#
# THE SET WAS {xarray, dask, zarr} UNTIL PHASE 2a AND THAT WAS THREE OF FIVE.
# `pydantic` and `threadpoolctl` cross the same boundary -- config validation
# and thread-limit observation are both batch-layer concerns -- so a guard
# naming only the first three reads as covering the boundary while two imports
# walk through it. Measured before widening: importing `metamer.core` pulls in
# none of the five, so this is a line the tree already holds rather than an
# aspiration.
_BATCH_ONLY = ("xarray", "dask", "zarr", "pydantic", "threadpoolctl")


def test_core_imports_without_batch_dependencies():
    """core must be importable with no batch-layer package in sys.modules.

    Bug this catches: someone adds `import xarray` to a core module, silently
    making `metamer.core` unusable for downstream consumers that installed
    without the [batch] extra.

    Run in a SUBPROCESS deliberately. Inside the pytest session every one of
    these is already imported by some other test module, so an in-process check
    would pass against any core module at all -- it would be measuring the
    session, not the import graph.
    """
    code = (
        "import metamer.core, sys; "
        f"bad = set({_BATCH_ONLY!r}) & set(sys.modules); "
        "assert not bad, bad"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


def test_the_isolation_guard_bites():
    """The same probe fails when a batch-layer package IS imported.

    Bug this catches: the guard passing because its probe is broken -- a typo in
    the module names, an assertion that cannot fire, a subprocess whose failure
    is swallowed. Without this, `test_core_imports_without_batch_dependencies`
    is indistinguishable from a test that asserts nothing, which is the shape
    the suite has been caught in before.
    """
    code = (
        "import metamer.core, threadpoolctl, sys; "
        f"bad = set({_BATCH_ONLY!r}) & set(sys.modules); "
        "assert not bad, bad"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True
    )
    assert result.returncode != 0
    assert "threadpoolctl" in result.stderr
