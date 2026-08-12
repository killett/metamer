"""The run configuration, and the only path from a file to a set of hashes.

`load(path)` is the sole constructor a run uses, going through `tomllib` to
pydantic to `hashing.normalize` to `canonical_json` to the three hashes. **No
production path constructs a `Config` inline**: a `compat_hash`-only difference
proves nothing unless it survived the real normalizer, so every integration test
and every exit criterion loads from a real file on disk.

The model is hashed, never the file text -- comments, key order, whitespace and
explicit-versus-default all normalize away, and hashing the text would
invalidate a 10^7-point store on a comment.

See `metamer.config.model` for the field-by-field reasoning and
`metamer.config.candidates` for how a `"white + matern12"` expression desugars.
"""

from __future__ import annotations

from metamer.config.candidates import parse_candidate, term_spec
from metamer.config.model import (
    Audit,
    Config,
    Detail,
    Screening,
    WarmStart,
    load,
    normalize_candidates,
)

__all__ = [
    "Audit",
    "Config",
    "Detail",
    "Screening",
    "WarmStart",
    "load",
    "normalize_candidates",
    "parse_candidate",
    "term_spec",
]
