"""The batch layer: config to input to tiling to fit to store to resume.

Phase 2a's vertical slice lives here. `metamer.core` is the likelihood spine and
knows nothing about stores, tiles or configs; this package is the only thing
that does, and the dependency direction is one-way. **`metamer.core` must remain
importable with none of `xarray`, `dask`, `zarr`, `pydantic` or `threadpoolctl`
in `sys.modules`** -- see `tests/test_core_isolation.py`, and the `batch` extra
in `pyproject.toml` that it names.

The Python API is the unit of implementation and testing;
`python -m metamer <config.toml> <store>` is a thin argparse wrapper over it and
presupposes no command tree, which Phase 5 is what decides.

Task 2 added `input` (the opener registry and the stage-4a contract) and
`timeaxis` (the decimal-year conversion). Task 4 adds the runner.
"""

from __future__ import annotations

__all__: list[str] = []
