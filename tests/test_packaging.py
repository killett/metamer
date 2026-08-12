"""The shipped artifact, checked from outside the development environment.

**`pixi run` executes off `PYTHONPATH=src` inside an environment that already
has everything installed.** A dependency the package fails to DECLARE is
therefore invisible to every other test in this suite: the import succeeds here
and fails for whoever ran `pip install metamer`. The property that must hold is
a property of a DIFFERENT process -- one that has only what the distribution
asked for -- and no amount of testing in this one reaches it. Same argument as
pre-flight (k), one layer out from `PYTHONHASHSEED`.

It recurs at every task that adds a dependency, which is why this is a standing
guard and not a Task 0 finding. Phase 2a Task 0 is the worked instance: `xarray`
and `pydantic` sat in `pixi.toml` while `pyproject.toml` named neither, and
`tests/test_core_isolation.py` had been documenting a `[batch]` extra that did
not exist since Phase 1.

WHAT THESE TESTS DO NOT COVER, stated here rather than discovered later:

  - **They do not resolve dependencies.** There is no `pip` in the pixi
    environment and no wheelhouse, so the clean environment gets the metamer
    wheel with `--no-deps` and nothing else. A version FLOOR that is wrong --
    `numpy>=2.4` against a package that needs 2.5 -- is not caught here. Closing
    that needs an offline wheelhouse; see the open question in `PROGRESS.md`.
  - **They do not import modules that need third-party packages.** In the clean
    environment `metamer.core.fit` cannot execute, because numpy is not there.
    Presence is therefore a filesystem question, walked outward from
    `metamer.__file__`. That is enough for the failure being guarded -- a module
    the build did not ship -- and it is not enough to catch a module that
    imports something at module scope and does not declare it, which is what the
    requirement check covers instead.
  - **The requirement check is only as live as `src/` is.** It compares what
    `src/metamer` actually imports against what the wheel declares, so a
    dependency that is declared and not yet imported is not exercised by it. At
    Task 0 that is all four batch dependencies: nothing under `src/` imports
    them yet, so the check passes on the core four alone. It becomes
    load-bearing the moment Task 1 imports pydantic, and that is the intended
    shape -- it guards the direction that hurts (imported but undeclared) and
    says nothing about the direction that does not.

The two tests are deliberately separate. One asks whether the wheel CONTAINS
what it claims; the other asks whether it ASKED FOR what it needs. Both failures
present as `ImportError` for a user and they have different causes, so
conflating them would not say which happened.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import venv
from pathlib import Path

import pytest

# Building a wheel and creating a virtual environment costs ~20-40 s, which is
# why this is `slow`. It is not optional: it is the only test in the suite that
# runs outside the development environment.
pytestmark = pytest.mark.slow

_REPO = Path(__file__).resolve().parents[1]
_SRC = _REPO / "src"

# Third-party top-level module name -> the distribution that provides it.
#
# DELIBERATELY A HAND-MAINTAINED TABLE, AND DELIBERATELY FAIL-LOUD ON A MISS.
# `importlib.metadata.packages_distributions()` cannot be used: in the clean
# environment only metamer is installed, so it knows nothing, and in THIS
# environment it would answer from packages the wheel never asked for -- the
# exact substitution this module exists to prevent. An import this table does
# not know about fails the test with a message saying to add it here AND to
# `pyproject.toml`, so the next dependency add is routed through this check
# rather than around it.
_MODULE_TO_DISTRIBUTION = {
    "numpy": "numpy",
    "scipy": "scipy",
    "numba": "numba",
    "psutil": "psutil",
    "xarray": "xarray",
    "zarr": "zarr",
    "pydantic": "pydantic",
    "threadpoolctl": "threadpoolctl",
}

# Modules the wheel must ship. Enumerated, never counted -- an asserted count is
# how two bypassed exits survived Phase 1's Task 8, and a count here would pass
# against any two subpackages at all.
_MUST_SHIP = (
    "metamer",
    "metamer.__main__",
    "metamer.batch",
    "metamer.config",
    "metamer.core",
    "metamer.core.fit",
    "metamer.core.hashing",
    "metamer.core.engines.kalman",
    "metamer.bench.spike",
)


def _clean_env() -> dict[str, str]:
    """The parent environment with `PYTHONPATH` stripped.

    **THIS IS LOAD-BEARING AND IT WAS MISSING ON THE FIRST WRITING OF THIS
    MODULE.** `pixi.toml` sets `PYTHONPATH = "src"` under `[activation.env]` so
    that `python -m metamer` works without an editable install, and a
    subprocess inherits it. Without this the clean environment's interpreter
    resolves `metamer` out of `/workspace/src` -- the development tree, the one
    thing these tests exist to look past -- while every other assertion still
    passes. Measured: the first run's traceback named
    `/workspace/src/metamer/core/families/matern12.py`.

    Returns:
        An environment mapping with `PYTHONPATH` removed.
    """
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    return env


def _run(python: Path, code: str) -> subprocess.CompletedProcess[str]:
    """Run `code` in the clean environment's interpreter.

    Args:
        python: The clean environment's interpreter.
        code: Source to execute with `-c`.

    Returns:
        The completed process.
    """
    return subprocess.run(
        [str(python), "-c", code], capture_output=True, text=True, env=_clean_env()
    )


def _third_party_imports() -> set[str]:
    """Top-level third-party modules imported anywhere under `src/metamer`.

    Returns:
        Distribution-independent top-level module names, with stdlib and
        first-party names removed.
    """
    found: set[str] = set()
    for path in sorted(_SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                found.add(node.module.split(".")[0])
    return {
        name
        for name in found
        if name != "metamer" and name not in sys.stdlib_module_names
    }


@pytest.fixture(scope="module")
def clean_environment(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build the wheel and install it, alone, into a fresh virtual environment.

    `--no-deps` and `--no-index` are both required and both deliberate: the
    environment must contain the artifact and nothing else, and it must be
    reachable with no network.

    Returns:
        Path to the new environment's interpreter.
    """
    root = tmp_path_factory.mktemp("packaging")
    dist = root / "dist"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "build",
            "--wheel",
            "--no-isolation",
            "--outdir",
            str(dist),
        ],
        cwd=_REPO,
        check=True,
        capture_output=True,
    )
    wheels = list(dist.glob("metamer-*.whl"))
    assert len(wheels) == 1, wheels

    env_dir = root / "env"
    # `system_site_packages` defaults to False and must stay that way: one
    # keyword turns this into the development environment wearing a different
    # path, and every assertion below would keep passing.
    venv.EnvBuilder(with_pip=True, clear=True).create(env_dir)
    python = env_dir / "bin" / "python"
    subprocess.run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--no-deps",
            "--no-index",
            "--disable-pip-version-check",
            str(wheels[0]),
        ],
        check=True,
        capture_output=True,
        env=_clean_env(),
    )
    return python


def test_the_clean_environment_really_is_clean(clean_environment: Path) -> None:
    """numpy is absent, and `metamer` resolves from inside the environment.

    THIS IS THE POSITIVE CONTROL FOR THE ISOLATION ITSELF, and without it the
    other tests here are unfalsifiable in the way pre-flight (i2) describes: an
    environment that quietly inherited the development tree would pass every
    assertion below while checking nothing at all.

    IT NEEDS BOTH HALVES, AND THE FIRST WRITING OF THIS MODULE HAD ONLY ONE.
    The two leaks are independent and have different causes:

      - third-party packages leak through `system_site_packages=True`, one
        keyword away in the fixture;
      - **metamer itself leaks through `PYTHONPATH=src`**, which `pixi.toml`
        sets under `[activation.env]` and a subprocess inherits. Measured on the
        first run: the traceback named
        `/workspace/src/metamer/core/families/matern12.py`, i.e. the artifact
        under test was the source tree. The numpy half did not notice, because
        numpy genuinely was absent.

    So a `metamer` that imports is not evidence of anything until its
    `__file__` is shown to be inside this environment.
    """
    absent = _run(clean_environment, "import numpy")
    assert absent.returncode != 0
    assert "numpy" in absent.stderr

    located = _run(clean_environment, "import metamer; print(metamer.__file__)")
    assert located.returncode == 0, located.stderr
    assert str(clean_environment.parent.parent) in located.stdout
    assert str(_SRC) not in located.stdout


def test_the_wheel_ships_every_module_the_package_claims(
    clean_environment: Path,
) -> None:
    """Each module in `_MUST_SHIP` is present in the installed distribution.

    Bug this catches: a subpackage the build did not include -- a missing
    `__init__.py`, a `[tool.hatch.build.targets.wheel]` exclude wider than
    intended -- so `pip install metamer` yields a package whose imports fail for
    a reason no test in the development tree can see, because there the module
    is on `PYTHONPATH` whether or not the build shipped it. `metamer.batch` and
    `metamer.config` are the live case: a directory without an `__init__.py` is
    importable from source as a namespace package while being invisible to the
    wheel build.

    PRESENCE IS A FILESYSTEM QUESTION HERE, NOT AN IMPORT ONE, AND
    `find_spec` IS NOT A WAY ROUND THAT. `find_spec` locates a module without
    executing it but it DOES execute the parent packages, and
    `metamer.core.__init__` eagerly imports the family registry, which imports
    numpy -- absent by construction. Measured: the first version of this test
    failed with `ModuleNotFoundError: No module named 'numpy'` raised from
    inside `find_spec`. Importing `metamer` alone is safe, since its `__init__`
    touches only `_version`, so the check walks outward from `metamer.__file__`.
    """
    probe = (
        "import json, metamer\n"
        "from pathlib import Path\n"
        f"names = {list(_MUST_SHIP)!r}\n"
        "root = Path(metamer.__file__).parent\n"
        "missing = []\n"
        "for name in names:\n"
        "    parts = name.split('.')[1:]\n"
        "    base = root.joinpath(*parts) if parts else root\n"
        "    if not (base.with_suffix('.py').is_file() or (base / '__init__.py').is_file()):\n"
        "        missing.append(name)\n"
        "print(json.dumps(missing))\n"
    )
    result = _run(clean_environment, probe)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == []


def test_every_third_party_import_is_declared_by_the_wheel(
    clean_environment: Path,
) -> None:
    """Everything `src/metamer` imports is named in the WHEEL's own metadata.

    Bug this catches: a dependency declared in `pixi.toml` and forgotten in
    `pyproject.toml`. The development environment has it either way, so the
    import succeeds here and raises `ModuleNotFoundError` for anyone who
    installed the package -- a failure that reaches users and never reaches CI's
    source-tree jobs.

    THE REQUIREMENTS ARE READ FROM THE INSTALLED DISTRIBUTION, NOT FROM
    `pyproject.toml`. Reading the source of truth would test that the file says
    what the file says; reading the artifact tests that the build carried it
    through, which is a different claim and the one a user depends on. Extras
    count as declared -- `metamer.batch` is behind `[batch]` by design -- so
    what this catches is a requirement declared NOWHERE, not one behind an extra.

    An import whose distribution is unknown to `_MODULE_TO_DISTRIBUTION` fails
    here by design, naming the module: a new third-party dependency must be
    routed through this test rather than around it.
    """
    imported = _third_party_imports()
    unknown = imported - set(_MODULE_TO_DISTRIBUTION)
    assert not unknown, (
        f"third-party imports with no known distribution: {sorted(unknown)}. "
        f"Add each to _MODULE_TO_DISTRIBUTION and to pyproject.toml."
    )

    probe = (
        "import importlib.metadata as m, json\n"
        "print(json.dumps(m.requires('metamer') or []))\n"
    )
    result = _run(clean_environment, probe)
    assert result.returncode == 0, result.stderr

    declared = set()
    for requirement in json.loads(result.stdout):
        name = requirement.split(";")[0].strip()
        for separator in ("[", "<", ">", "=", "!", "~", "(", " "):
            name = name.split(separator)[0]
        declared.add(name.strip())

    needed = {_MODULE_TO_DISTRIBUTION[name] for name in imported}
    assert needed <= declared, (
        f"imported by src/metamer but declared nowhere in the wheel: "
        f"{sorted(needed - declared)}"
    )
