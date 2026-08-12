"""The run configuration, and the only path from a file to a set of hashes.

`load(path)` will be the sole constructor a run uses, going through `tomllib` to
pydantic to `hashing.normalize` to `canonical_json` to the three hashes. **No
production path constructs a `Config` inline**: a `compat_hash`-only difference
proves nothing unless it survived the real normalizer, so every integration test
and every exit criterion loads from a real file on disk.

The model is hashed, never the file text -- comments, key order, whitespace and
explicit-versus-default all normalize away, and hashing the text would invalidate
a 10^7-point store on a comment.

Skeleton only in Task 0; Task 1 adds the model and `load`.
"""

from __future__ import annotations

__all__: list[str] = []
