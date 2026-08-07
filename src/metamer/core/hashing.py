"""Three hashes, with compat relevance declared by allowlist.

    fit_hash     everything determining theta-hat and log_lik
    compat_hash  fit_hash's fields + the criterion set (which determines
                 the stored /selection/ arrays)
    run_hash     everything, plus runtime knobs and the machine fingerprint

Design doc section 13.3. Two hashes are not enough: the criterion set belongs
in the resumption gate and **not** in the warm-start key, because AIC versus
BIC changes the derived arrays and changes nothing about where the optimizer
lands. Collapsing them discards every warm start the moment a user adds HQIC.
The payoff is section 12.8's mismatch behaviour -- a `compat_hash` mismatch
with a matching `fit_hash` recomputes the derived arrays from the stored
primitives and continues, neither refusing nor refitting.

`fit_hash` is a strict subset of `compat_hash` by construction, and that is
load-bearing rather than tidy: section 12.8 treats a `compat_hash` match as
licence to skip refitting, which is sound only if a matching `compat_hash`
guarantees a matching fit.

**Compat relevance is an ALLOWLIST.** Fields are relevant by explicit
membership below; anything else defaults to provenance-only. With a denylist
every newly added field silently becomes compat-relevant and the failure mode
is "resume broke and nobody knows why". The sharp edge, named in section 13.3:
because defaults are included, any version bump touching a compat-relevant
default invalidates every in-progress store. The allowlist is what keeps that
surface small enough to review.

**What this module refuses, and why refusing is the point.** A hash that
changes between runs on identical input silently invalidates a 10^7-point
store -- every resume reads as a mismatch and refits. So `canonical_json`
accepts only what JSON can represent exactly and raises otherwise, rather than
falling back to `repr`:

- `repr` of an object without one embeds its **memory address**, which differs
  in every process.
- `repr` of a `set` renders in an order that varies with `PYTHONHASHSEED`.
  Measured: `{"aic", "bic", "hqic"}` gives three different strings under three
  seeds -- and `criteria` is exactly the kind of field a user would pass as a
  set.

Neither looks wrong. Both produce a drifting hash, which has no symptom other
than a bill.

Non-finite floats are refused for a different reason: `json.dumps` renders
them as the bare tokens `Infinity` and `NaN`, which no conforming JSON reader
accepts, so the canonical form would not round-trip out of zarr attributes.
**This diverges deliberately from `terms.py`**, which keeps infinities by
stringifying every float through `repr(float(...))`: an infinite bijector
bound is a legitimate `Logit` parameter, while an infinite memory budget is a
user error. Same trap, opposite correct answer.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

FIT_RELEVANT_FIELDS = frozenset(
    {
        "data_uri",
        "variable",
        "signal_terms",
        "objective",
        "engine",
        "registry_version",
        "metamer_version",
        "seed",
    }
)
"""Fields determining theta-hat and log_lik. Extending this is a deliberate act.

Excludes the criterion set (AIC versus BIC does not move the optimum) and the
candidate set (candidate-set extension is a legitimate incremental operation,
and section 11.1 keys warm starts on `(fit_hash, candidate spec_hash)` -- the
candidate is the other half of that pair).
"""

COMPAT_RELEVANT_FIELDS = FIT_RELEVANT_FIELDS | {"criteria"}
"""Fields determining the stored derived arrays. A strict superset of the above."""

CONFIG_DEFAULTS: dict[str, Any] = {"seed": 0, "objective": "ml"}
"""Declared defaults, filled in before hashing so explicit equals omitted.

Deliberately small. Every entry is a field some hash actually reads, and every
entry carries section 13.3's sharp edge: changing one of these values in a
release invalidates every in-progress store, bugfix releases included. Adding
an entry is the same weight of decision as extending the allowlist.
"""

MACHINE_KEY = "_machine"
"""Reserved key under which `run_payload` files the machine fingerprint."""

_JSON_SCALARS = (str, int, float, bool, type(None))


def _check(value: object, path: str) -> None:
    """Refuse anything JSON cannot represent exactly, naming where it is.

    `json.dumps` would report the offending *type* and not the field, which is
    the one fact needed to fix a config. Checking first is also what lets
    non-finite floats raise rather than emit a non-standard token.

    Args:
        value: The value to check.
        path: Dotted path to `value` within the payload, used in messages.

    Raises:
        TypeError: If `value` is not a JSON scalar, list, tuple, or mapping
            with string keys. Notably a `set` -- whose iteration order varies
            with `PYTHONHASHSEED` -- and any object whose `repr` carries a
            memory address.
        ValueError: If `value` is a non-finite float, which `json.dumps`
            renders as the non-standard `Infinity` or `NaN` token.
    """
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError(
                f"{path}: {value} is not representable in JSON; a hash payload "
                "must round-trip through any conforming reader"
            )
        return
    if isinstance(value, _JSON_SCALARS):
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(
                    f"{path}: mapping key {key!r} is not a string, so the "
                    "canonical form would depend on how it happens to sort"
                )
            _check(item, f"{path}.{key}" if path else key)
        return
    if isinstance(value, Sequence):
        for index, item in enumerate(value):
            _check(item, f"{path}[{index}]")
        return
    raise TypeError(
        f"{path}: {type(value).__name__} is not JSON-representable. It is "
        "refused rather than stringified because a repr fallback hashes "
        "memory addresses and set orderings, which differ between processes "
        "and silently invalidate a stored run"
    )


def canonical_json(payload: Mapping[str, Any]) -> str:
    """Render a mapping to canonical JSON: sorted keys, compact separators.

    Insensitive to insertion order by `sort_keys`, and to float formatting by
    Python's shortest-round-tripping `repr` -- which distinguishes 0.3 from
    0.30000000000000004 while rendering each identically every time. List
    order is preserved, not sorted: `signal_terms` fixes the design matrix's
    column order, so two orderings are two different models.

    Args:
        payload: The mapping to render.

    Returns:
        The canonical JSON string.

    Raises:
        TypeError: If any value is not JSON-representable -- see `_check`.
        ValueError: If any float is non-finite.
    """
    _check(payload, "")
    return json.dumps(dict(payload), sort_keys=True, separators=(",", ":"))


def _digest(payload: Mapping[str, Any]) -> str:
    """Return the first 16 hex digits of the payload's canonical SHA-256."""
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()[:16]


def normalize(config: Mapping[str, Any]) -> dict[str, Any]:
    """Fill declared defaults so an explicit value equals an omitted one.

    Args:
        config: The config as supplied.

    Returns:
        A new mapping with every `CONFIG_DEFAULTS` key present.
    """
    return {**CONFIG_DEFAULTS, **dict(config)}


def _subset(config: Mapping[str, Any], fields: frozenset[str]) -> dict[str, Any]:
    """Take the allowlisted fields, refusing a config that omits one.

    A missing field is refused rather than skipped. The allowlist is the
    statement "these fields determine theta-hat", so a config lacking one has
    not been specified -- and skipping silently would let a single typo
    (`data_url` for `data_uri`) demote the data source to provenance-only, at
    which point two runs over different data share a `fit_hash` and reuse each
    other's fits.

    Args:
        config: A normalized config.
        fields: The allowlist to take.

    Returns:
        The subset, as a plain dict.

    Raises:
        KeyError: If any allowlisted field is absent.
    """
    missing = sorted(fields - set(config))
    if missing:
        raise KeyError(
            f"config is missing required field(s) {missing}; every allowlisted "
            "field determines the fit and none may be defaulted silently"
        )
    return {key: config[key] for key in sorted(fields)}


def fit_payload(config: Mapping[str, Any]) -> dict[str, Any]:
    """Return exactly what `fit_hash` hashes, for inspection and provenance."""
    return _subset(normalize(config), FIT_RELEVANT_FIELDS)


def compat_payload(config: Mapping[str, Any]) -> dict[str, Any]:
    """Return exactly what `compat_hash` hashes."""
    return _subset(normalize(config), COMPAT_RELEVANT_FIELDS)


def run_payload(
    config: Mapping[str, Any], machine: str | None = None
) -> dict[str, Any]:
    """Return exactly what `run_hash` hashes: everything, plus the machine.

    Args:
        config: The config as supplied.
        machine: Optional machine fingerprint from `machine_fingerprint`.

    Returns:
        The normalized config with the fingerprint filed under `MACHINE_KEY`.

    Raises:
        KeyError: If an allowlisted field is absent -- `run_hash` is
            provenance, but a config that cannot be fit-hashed is not a run.
        ValueError: If the config itself carries `MACHINE_KEY`, which would
            collide with the fingerprint slot and silently record the wrong
            machine.
    """
    payload = normalize(config)
    if MACHINE_KEY in payload:
        raise ValueError(
            f"{MACHINE_KEY!r} is reserved for the machine fingerprint and must "
            "not appear in a config"
        )
    _subset(payload, FIT_RELEVANT_FIELDS)
    if machine is not None:
        payload[MACHINE_KEY] = machine
    return payload


def fit_hash(config: Mapping[str, Any]) -> str:
    """Hash the fields determining theta-hat and log_lik.

    The warm-start key's first component (section 11.1) and the gate for
    reusing fits.
    """
    return _digest(fit_payload(config))


def compat_hash(config: Mapping[str, Any]) -> str:
    """Hash the fields determining the stored derived arrays.

    The gate for reusing `/selection/`. Differs from `fit_hash` only by the
    criterion set, so a criterion-only change recomputes rather than refits.
    """
    return _digest(compat_payload(config))


def run_hash(config: Mapping[str, Any], machine: str | None = None) -> str:
    """Hash everything, including runtime knobs and the machine fingerprint.

    **Provenance only, never a gate.** Runtime knobs appear here and nowhere
    else, which is what permits starting on the 64-core node and resuming on
    the mini PC -- a real workflow, made legitimate by section 11.3's
    determinism guarantee, and the same property that makes a future cloud
    burst a resume rather than a rerun.
    """
    return _digest(run_payload(config, machine))


def machine_fingerprint(cpu_model: str, cores: int, total_ram_bytes: int) -> str:
    """Instance-type fingerprint for the calibration cache (section 11.4).

    Hostname is meaningless on ephemeral nodes and thread count is a runtime
    knob, so neither is an input: a fresh spot instance of the same type must
    reuse its calibration rather than re-measure it.

    Args:
        cpu_model: CPU model string as reported by the platform.
        cores: Physical core count.
        total_ram_bytes: Total system RAM in bytes.

    Returns:
        The fingerprint, a 16-hex-digit digest.
    """
    return _digest({"cpu": cpu_model, "cores": int(cores), "ram": int(total_ram_bytes)})
