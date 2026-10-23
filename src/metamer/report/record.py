"""The report's record: every section, as the JSON the markdown is rendered from.

**THE RECORD IS THE ARTIFACT AND THE MARKDOWN IS A VIEW OF IT.** The entry point
writes this to `report.json`, reads the file back, and hands the parsed object
to `metamer.report.render` -- so a number in the markdown is a number in the
saved JSON by construction, not by a promise (2f Task 8's pre-flight, §2). The
plan's precedent is `bench/report.py`'s `decomposition_from_record`, which
re-derives from the artifact alone.

**THE CONVERSION IS GENERIC AND STRICT.** `_plain` walks the section
dataclasses rather than spelling each field, so a field added to a section is
in the record on the day it lands; and it refuses what JSON cannot carry
faithfully -- an array, an unknown type, a non-finite float at write time --
instead of stringifying it, because a record that silently says `"nan"` or
`"<object>"` is a record nobody can read back.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from enum import Enum
from pathlib import Path
from typing import Any

import numpy as np

from metamer import __version__
from metamer.report import clustering, drop, maps, numbers, primitives, selectability
from metamer.report.reader import StoreView

__all__ = ["UNFINISHED_SCOPE", "build"]

#: D6, carried in the record rather than left to the renderer: the statistic on
#: an unfinished store keeps its word, and its interpretation narrows.
UNFINISHED_SCOPE = (
    "This store is unfinished. Unwritten tiles are rectangular holes in the "
    "eligible mask, and the clustering null holds that mask fixed, so the "
    "statistic is valid and its question narrows: it asks whether the "
    "arrangement is unusual given what was fitted, not given the domain."
)


def _plain(value: object) -> object:
    """`value` as JSON-ready data: dicts, lists, strings, numbers, None.

    Args:
        value: A section record or any part of one.

    Returns:
        The same content in JSON's types. Enum members become their names,
        mapping keys become strings, tuples become lists.

    Raises:
        TypeError: On an array or any type JSON cannot carry faithfully.
    """
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, Enum):
        return value.name
    if isinstance(value, np.generic):
        return _plain(value.item())
    if isinstance(value, Path):
        return str(value)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _plain(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    if isinstance(value, Mapping):
        return {_key(key): _plain(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_plain(item) for item in value]
    raise TypeError(
        f"the report record cannot carry a {type(value).__name__}; convert it "
        "in the section that produces it"
    )


def _key(key: object) -> str:
    """A mapping key as JSON requires one: an `Outcome` by name, else `str`."""
    return key.name if isinstance(key, Enum) else str(key)


def build(view: StoreView, out_dir: Path) -> dict[str, Any]:
    """Compute every section and return the record.

    **THE MAPS ARE DRAWN HERE, INTO `out_dir`**, because `maps.draw_all` returns
    the record of what it drew; the entry point has already checked that
    `out_dir` is writable, which is why this runs after that check and never
    before it.

    Args:
        view: The store, read-only.
        out_dir: The report's output directory. Must exist and be writable.

    Returns:
        The record, in JSON's types.
    """
    completion = view.completion
    return {
        "metamer_version": __version__,
        "store": {
            "path": str(view.path),
            "complete": completion.complete,
            "total": completion.total,
            "finished": completion.is_finished,
            "scope": None if completion.is_finished else UNFINISHED_SCOPE,
            "disagreements": list(view.disagreements),
        },
        "numbers": _plain(numbers.compute(view)),
        "selectability": _plain(selectability.compute(view)),
        "primitives": _plain(primitives.compute(view)),
        "clustering": _plain(clustering.compute(view)),
        "early_abort": _plain(drop.describe(view)),
        "maps": _plain(maps.draw_all(view, out_dir)),
    }
