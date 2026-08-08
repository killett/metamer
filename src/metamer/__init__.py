"""metamer — stochastic noise-model fitting and selection for time series."""

try:
    # Written by hatch-vcs at build time from the git tag, so an installed
    # package always reports the released version and it cannot drift from
    # the tag that produced it.
    from metamer._version import __version__
except ImportError:  # pragma: no cover - exercised only in an uninstalled tree
    # pixi runs this package straight off PYTHONPATH=src without ever installing
    # it, so _version.py does not exist there. A sentinel is honest about that;
    # inventing a number would let an uninstalled tree claim to be a release.
    __version__ = "0.0.0.dev0"

__all__ = ["__version__"]
