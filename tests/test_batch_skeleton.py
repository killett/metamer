"""The Phase 2a package skeleton and the dependencies it declares.

These are smoke checks and are labelled as such -- importability is not wiring,
and an empty module satisfies an import. The one assertion here that can fail
for an interesting reason is the zarr major-version pin.
"""

from __future__ import annotations

import importlib.metadata
import tomllib
from pathlib import Path

import zarr

_PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def test_the_batch_and_config_packages_import() -> None:
    """`metamer.batch` and `metamer.config` exist.

    A smoke check. It cannot distinguish a wired module from an empty one; what
    it catches is a layout mistake -- a missing `__init__.py`, or a package that
    shadows a stdlib name -- reaching a later task as an import error whose
    cause is three tasks back.
    """
    import metamer.batch
    import metamer.config

    assert metamer.batch.__name__ == "metamer.batch"
    assert metamer.config.__name__ == "metamer.config"


def test_the_installed_zarr_is_version_3() -> None:
    """zarr's MAJOR version is 3, asserted against the installed package.

    Bug this catches: a lock refresh moving zarr across a major boundary. The
    store schema depends on v3 sharding and the v2 and v3 on-disk layouts are
    not the same format, so a store written under one is not readable as the
    other -- a failure that would surface as a resume refusing a store that is
    perfectly valid, at whatever scale the store happens to have reached.

    `zarr = "*"` in `pixi.toml` resolves to 3.x TODAY, which is a fact about
    the current conda-forge release and about `exclude-newer = "7d"` rather
    than a constraint. The manifest pins `>=3,<4`; this asserts the pin took
    effect, because a version specifier is a name and a name is not a gate.
    """
    assert zarr.__version__.split(".")[0] == "3"


def test_the_batch_extra_declares_every_dependency_the_batch_layer_imports() -> None:
    """`pyproject.toml` carries a `batch` extra naming all four packages.

    Bug this catches: a dependency that exists only in `pixi.toml`. `pixi run`
    executes off `PYTHONPATH=src` inside an environment that already has
    everything, so an import that would break the published wheel is invisible
    in development -- the failure appears for someone who ran `pip install
    metamer[batch]`, and never here.

    The core runtime dependencies are deliberately NOT widened. `metamer.core`
    must stay importable without any of these; `test_core_isolation.py` is what
    holds that line.
    """
    pyproject = tomllib.loads(_PYPROJECT.read_text())
    extras = pyproject["project"]["optional-dependencies"]

    assert "batch" in extras
    declared = {
        requirement.split(">")[0].split("=")[0].split("[")[0].strip()
        for requirement in extras["batch"]
    }
    assert declared == {"xarray", "zarr", "pydantic", "threadpoolctl"}

    core = {
        requirement.split(">")[0].split("=")[0].split("[")[0].strip()
        for requirement in pyproject["project"]["dependencies"]
    }
    assert core.isdisjoint(declared)


def test_every_batch_dependency_is_actually_installed() -> None:
    """Each name in the `batch` extra resolves to an installed distribution.

    Bug this catches: a package declared in `pyproject.toml` and forgotten in
    `pixi.toml`, so the extra is a claim about an environment nobody has. The
    inverse of the previous test, and it needs to be separate: the two failures
    have different causes and conflating them does not say which happened.

    `threadpoolctl` is the live instance -- it was present transitively and
    undeclared before Task 0, which is a dependency nothing guarantees.
    """
    for name in ("xarray", "zarr", "pydantic", "threadpoolctl"):
        assert importlib.metadata.version(name)
