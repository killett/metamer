"""Entry point so the package is runnable with `python -m metamer`."""

import sys

from metamer import __version__


def main() -> int:
    """Print the package version.

    Returns:
        Process exit code.
    """
    print(f"metamer {__version__}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
