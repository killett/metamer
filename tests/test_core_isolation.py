import subprocess
import sys


def test_core_imports_without_batch_dependencies():
    """core must be importable with no xarray/dask/zarr in sys.modules.

    Bug this catches: someone adds `import xarray` to a core module, silently
    making `metamer.core` unusable for downstream consumers that installed
    without the [batch] extra.
    """
    code = (
        "import metamer.core, sys; "
        "bad = {'xarray', 'dask', 'zarr'} & set(sys.modules); "
        "assert not bad, bad"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
