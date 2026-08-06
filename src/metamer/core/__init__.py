"""Array-level API: numpy/scipy only. No file I/O, no xarray, no dask."""

# Registration of the built-in families is a decorator side effect in each
# family module, so *something* has to import them eagerly. That trigger lives
# here, in `metamer.core`, rather than in the top-level `metamer` package,
# because both halves of the lookup are inside `metamer.core`: `terms.py`
# resolves a TermSpec's `kind` through `registry.py`'s `kernel_registry`. If
# the trigger sat one level up, `import metamer.core` on its own would leave
# the registry empty and `TermSpec.engine_costs()` would raise
# `KeyError: unknown key 'matern12'. Available: ` -- which is exactly the
# state this import fixes. Keeping it here also keeps `metamer.core`
# self-contained, which is what `test_core_imports_without_batch_dependencies`
# guards; the families import numpy only, so that guarantee is preserved.
#
# This does not reintroduce the import cycle that `registry.py`'s
# TYPE_CHECKING import resolves: nothing under `families/` imports
# `metamer.core` itself, only its leaf submodules (capability, params,
# registry, transforms), none of which import back into `families`.
from metamer.core import families  # noqa: F401

__all__ = ["families"]
