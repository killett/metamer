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

**Algorithm identity is declared, not inferred from the package version.** The
allowlist carries `ALGORITHM_VERSION`, a hand-bumped constant, and NOT
`metamer.__version__`, which `hatch-vcs` derives from the git tag and which
therefore changes on every commit and again between an installed package and
the uninstalled `PYTHONPATH=src` tree that `pixi run` uses. See
`ALGORITHM_VERSION` for the full argument; the short form is that "does this
change invalidate stored fits?" must be a decision someone makes rather than a
side effect of committing.

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

from metamer.core.registry import REGISTRY_VERSION

ALGORITHM_VERSION = "1"
"""Identity of the code that computes theta-hat and log_lik. HAND-BUMPED.

**Bump this, in its own commit, when and only when a change alters the value
of `theta_hat` or `log_lik` for some input that previously fit.** That covers
the objective (including its REML constant), the filter recursion, the
concentration and GLS solve, the optimizer's step rules, the initialization
ladder, the parameter transforms, and any diagnostic threshold whose crossing
changes a reported fit. It does not cover the CLI, the store writer, the
reporting layer, documentation, packaging, or a criterion added to
`criteria` -- none of those moves an optimum.

WHY THIS IS NOT THE PACKAGE VERSION, which is the obvious thing to put here
and was in fact what this field held until 2026-08-10. Under `hatch-vcs` the
package version is derived from the git tag, so an untagged commit reports
something like `0.1.1.dev3+g6a0fb3b` -- **a new string on every commit** -- and
the same tree reports `0.0.0.dev0` when run uninstalled off `PYTHONPATH=src`,
which is how `pixi run` executes it. Either variation reaching this payload
means a finished 10^7-point store stops resuming and silently refits: no
exception, no warning, and the same symptom profile as the `PYTHONHASHSEED`
serializer defect this module was written to close -- correct-looking
behaviour and a compute bill.

The alternatives were weighed and are recorded in
`docs/superpowers/notes/phase2-preliminaries-preflight.md`. In short: a
release version with the dev and local segments stripped is wrong in both
directions (a packaging-only patch release invalidates every store, while an
algorithm change on an untagged commit does not move it, so a stale fit is
reused against changed code); `registry_version` identifies the family
registry and not the objective, the optimizer or the engine; and hashing the
source of the fit-determining modules moves on comments and on whether the
code is a wheel, an sdist or a working tree.

**A hand-bumped constant is the only option under which "does this change
invalidate stored fits?" is a decision someone makes rather than a side effect
of tagging or of committing.** Its one real cost is that it can be forgotten,
which is the cost of every declared-identity mechanism here, `FIT_RELEVANT_FIELDS`
included, and is answered the same way: the rule is stated where the constant
lives and repeated on the release checklist in `RELEASING.md`.
"""

ALGORITHM_VERSION_KEY = "algorithm_version"
"""Payload key under which `normalize` stamps `ALGORITHM_VERSION`.

Reserved: a config supplying it is refused, not overridden. Silently
overriding would leave a user who believed they had pinned the algorithm
identity with a payload that says otherwise, which is the "silent skip in an
allowlist is a demotion" failure pointed the other way.
"""

REGISTRY_VERSION_KEY = "registry_version"
"""Payload key under which `normalize` stamps `registry.REGISTRY_VERSION`.

**STAMPED AND RESERVED FOR THE SAME REASON `algorithm_version` IS, AND IT WAS
NEITHER UNTIL PHASE 2a TASK 1.** It identifies the installed family registry --
a property of the code -- and it sits in `FIT_RELEVANT_FIELDS`, where `_subset`
requires it. Until a config file existed, every caller was a test supplying it
by hand, so nothing had to decide where it came from.

The moment `metamer.config.load` exists, the alternative is that a user's TOML
supplies it: a value identifying the installed registry, provided by the thing
it is supposed to identify. Pinning `registry_version = "1"` while running a
registry that has changed then reuses fits computed by different kernels, with
every array the right shape and no symptom. **That is `metamer_version` in
`FIT_RELEVANT_FIELDS` all over again -- a name that gates nothing -- caught here
before a config could populate it rather than after.**

The stamped value equals what the fixtures used to supply, so no hash moved
when this changed; only the source did.
"""

_WARM_START_FIT_FIELDS = frozenset(
    {
        "warm_start_enabled",
        "warm_start_coarse_stride",
        "warm_start_interpolation_rule",
        "warm_start_spiral_bound",
        "warm_start_tie_break",
    }
)
"""The warm-start settings that move theta-hat. FLATTENED, one name each.

**NOT a single `warm_start` mapping, deliberately.** Compat relevance is an
allowlist and *membership is the entire mechanism*; a nested mapping makes
membership implicit for everything inside it, so a field added to that block
later becomes fit-relevant by accident and invalidates every store the first
time someone changes it.

The boundary this protects is narrow and real. §11.1's own words settle why the
settings below are fit-relevant: a stale warm start produces converged-looking
fits at the wrong optimum, the worst failure mode in the system. But read
loosely the same argument sweeps in the **audit** settings, and then re-running
a hysteresis audit at a different subsample size invalidates the store it is
auditing. The audit settings live in their own config block, are absent from
this set, and `tests/test_config.py` asserts that changing one moves neither
`fit_hash` nor `compat_hash`.
"""

GEOMETRY_HASH_KEY = "geometry_hash"
"""Payload key for the input's geometry fingerprint. Stamped by stage 4a.

**IT REPLACED `data_uri` ON 2026-08-12, AND `data_uri` WAS WRONG IN BOTH
DIRECTIONS AT ONCE.** Moving a file invalidated a resume that is scientifically
valid; editing a file in place at a fixed URI permitted a resume that is
scientifically invalid. A gate wrong in both directions is not a conservative
approximation of the right gate -- it is unrelated to it.

It was also the **last self-reported identity in either allowlist**: a value
claiming to identify the data, supplied by the config rather than read from the
data. `metamer.batch.geometry` reads every component from the opened dataset.
`data_uri` remains in the config as provenance, reaching `run_hash` alone.

**A config cannot supply this and `normalize` does not stamp it**, because it is
not a property of the installed code -- it is a property of an input that may
not exist yet. `Config.fit_hash()` therefore returns None until stage 4a has
run, which is the regime the optional return type was declared for at Task 1.
"""

REQUEST_FIELDS = (
    frozenset(
        {
            "variable",
            "signal_terms",
            "objective",
            "engine",
            "seed",
        }
    )
    | _WARM_START_FIT_FIELDS
)
"""Fit-relevant fields THE CONFIG IS AUTHORITATIVE FOR. The user is asking.

A request cannot be wrong: the config is the only thing that knows what was
asked for, so a value here identifies nothing outside itself and there is no
party it can disagree with. **This is the safe class, and it is the only one a
config may supply.**

**THE FIVE WARM-START SETTINGS ARE REQUESTS, AND THEY WERE THE ONLY UNCLASSIFIED
MEMBERS OF THE ALLOWLIST.** They entered on 2026-08-11; `data_uri` was named
*"the last self-reported identity in either allowlist"* on 2026-08-12 -- so the
vocabulary that would have classified them arrived one day after they did, and
the audit that closed with it never covered them. Classified 2026-08-24, at
Phase 2c Task 1. `warm_start_coarse_stride` asks for a stride; it does not claim
that a store on disk WAS decimated at one. **That claim is a different check, at
a different layer** -- Phase 2c Task 4's cross-store gate, which compares the two
stores' recorded strides positionally and never infers one from the other.
"""

STAMPED_IDENTITY_FIELDS = frozenset({ALGORITHM_VERSION_KEY, REGISTRY_VERSION_KEY})
"""Fit-relevant fields THE INSTALLED CODE IS AUTHORITATIVE FOR.

`normalize` stamps both from the running package and **a config supplying either
is refused, not overridden** -- `metamer.config.model` reads this set for that
refusal, so adding a member here makes it refusable without a second edit.

The hazard in this class is forgetting to bump, and it is answered at
`ALGORITHM_VERSION` rather than here.
"""

MEASURED_IDENTITY_FIELDS = frozenset({GEOMETRY_HASH_KEY})
"""Fit-relevant fields THE INPUT IS AUTHORITATIVE FOR, read rather than declared.

`metamer.batch.geometry` reads every component from the opened dataset, so the
value cannot be asserted by anything that has not opened it. **`Config` declares
no field for these**, and `Config` is a strict model, so the model itself is the
gate -- there is no deny-list to drift.
"""

FIT_RELEVANT_FIELDS = (
    REQUEST_FIELDS | STAMPED_IDENTITY_FIELDS | MEASURED_IDENTITY_FIELDS
)
"""Fields determining theta-hat and log_lik. Extending this is a deliberate act.

THE TEST FOR MEMBERSHIP IS A QUESTION, NOT THIS LIST. **A field is fit-relevant if
changing it can move `theta_hat` or `log_lik` for any input.** This set was
assembled at Task 16, before the mechanisms that populate it existed, so it is
evidence of what was known then and not of what belongs -- four separate omissions
or errors were found in it during Phase 2 planning. Ask the question about a new
field; do not reason from what is already here.

**AND THE BOUNDARY THE QUESTION DRAWS, STATED HERE BECAUSE THIS IS WHERE IT GETS
READ.** The audit's settings -- subsample size, stratification, whether an audit
ran at all -- **MEASURE a run; they are not inputs to it**, so they are outside
this set and re-running an audit at a different subsample size must leave the
store it audits resumable. The argument that puts the warm-start settings IN
(§11.1: a stale warm start produces converged-looking fits at the wrong optimum)
sweeps the audit settings in too when read one clause too far. See
`_WARM_START_FIT_FIELDS` for the boundary and `tests/test_config.py` for the
executable form.

**EXTENDING IT MEANS CLASSIFYING, BECAUSE THERE IS NOWHERE ELSE TO ADD A FIELD.**
This set is the union of three classes and has no members of its own: a request
(the config is authoritative), a stamped identity (the installed code is), or a
measured identity (the input is). **A fourth class exists and must stay empty --
a SELF-REPORTED identity, a value claiming to identify something outside the
config and supplied by the config anyway.** `data_uri` and `metamer_version`
were both that, and `data_uri` was **wrong in both directions at once**: moving a
file invalidated a scientifically valid resume, and editing a file in place at a
fixed URI permitted an invalid one. **Nothing declares the fourth class, and that
is the point** -- it is whatever the other three do not cover, so the three
covering everything is what proves it empty.

Excludes the criterion set (AIC versus BIC does not move the optimum) and the
candidate set (candidate-set extension is a legitimate incremental operation,
and section 11.1 keys warm starts on `(fit_hash, candidate spec_hash)` -- the
candidate is the other half of that pair).

**DO NOT "FIX" THE CANDIDATE-SET OMISSION BY ADDING IT HERE.** Section 12.8
permits resuming with a SUPERSET of the stored candidates -- same candidates
in the same order, possibly more -- and **a hash can only express equality**,
so putting `candidates` in either allowlist forbids the extension workflow
outright. The enforcement is a **positional comparison of candidate spec
hashes** against the ones in the store's root attrs, run by the resume gate:
`stored[i] == requested[i]` for every `i < len(stored)`, and
`len(requested) >= len(stored)`. A mismatch at any position is refused, naming
the index and both hashes.

That comparison is load-bearing and its absence is silent. Nothing else stops
a resume from writing candidate B's fits into candidate A's slice of the model
axis: every array keeps its shape, every value is finite, every status reads
`ok`, and the store is wrong in a way no invariant catches. Where the
candidates have different free-parameter counts it also shifts every offset on
the ragged `/noise/` axis, so the corruption lands in two arrays rather than
one.

**THIS SET HAS MOVED TWICE IN TWO DAYS AND EACH MOVE WAS REVERSED SEPARATELY.**
2026-08-11: the five warm-start settings entered, because §11.1 says a stale
warm start produces converged-looking fits at the wrong optimum; the **audit**
settings are the boundary and stay out, see `_WARM_START_FIT_FIELDS`.
2026-08-12: `data_uri` left and `geometry_hash` entered. **Both moved all three
`GOLDEN_*` constants, and `tests/test_hashing.py` reverses them one hop at a
time** -- a single combined regeneration would prove nothing about either.

Also excludes `metamer_version`, which it held until 2026-08-10. The package
version is now VCS-derived and therefore changes on every commit; it remains
in the config as **provenance**, where `run_hash` -- which is provenance and
never a gate -- still records it. Algorithm identity is carried by
`ALGORITHM_VERSION` instead. Design doc section 13.3's table says "metamer
version"; this is the narrower reading of that entry, and it is the one that
survives a version string derived from the git tag.
"""

STAGE_4A_FIELDS = MEASURED_IDENTITY_FIELDS
"""Fit-relevant fields a CONFIG cannot supply, stamped by stage 4a instead.

**AN ALIAS, NOT A COPY, AND THE TWO CONCEPTS ARE NOT THE SAME ONE.**
`MEASURED_IDENTITY_FIELDS` says **who is authoritative** -- the input. This says
**when the value arrives** -- at stage 4a. They coincide today because the only
way to read a value off the input is to open it, which is what stage 4a does.
Written as an alias so the two cannot silently disagree; **if a measured identity
ever arrives at a different stage, splitting them is a deliberate edit** rather
than a divergence nobody notices.

**`run_payload` VALIDATES THE FIT FIELDS MINUS THESE, AND THAT IS §13.4's
DEGRADED MODE RATHER THAN A LOOSENING.** The validation exists to refuse a
config that is not a runnable config -- "a config that cannot be fit-hashed is
not a run". `geometry_hash` is not a config field at all: it is read from an
input, and §13.4 requires that `--explain` work on **a config with no data
staged yet**, because sizing a run before moving 25 GB is that command's most
valuable use. Demanding it here would make an unreachable input an error where
the design says it is a degraded mode.

`run_hash` remains computable in that mode and `fit_hash` returns None, which is
the split §13.4 specifies: print compat- and run-relevant content always, and
`fit_hash: not computed (requires stage 4a)` otherwise.
"""

COMPAT_RELEVANT_FIELDS = FIT_RELEVANT_FIELDS | {"criteria"}
"""Fields determining the stored derived arrays. A strict superset of the above."""

CONFIG_DEFAULTS: dict[str, Any] = {"seed": 0, "objective": "ml"}
"""Declared defaults, filled in before hashing so explicit equals omitted.

Deliberately small. Every entry is a field some hash actually reads, and every
entry carries section 13.3's sharp edge: changing one of these values in a
release invalidates every in-progress store, bugfix releases included. Adding
an entry is the same weight of decision as extending the allowlist.

**THIS IS THE SECOND OF TWO DEFAULT MECHANISMS AND IT LOOKS DEAD FROM ONE SIDE.
DO NOT DELETE IT.** `metamer.config.Config` declares the same defaults as
pydantic field defaults, and `normalize` computes `{**CONFIG_DEFAULTS,
**config, ...}` -- the config wins. So once a config has come through
`config.load`, it always carries `seed` and `objective` explicitly and **this
mapping never applies to it.** Reading only that path, the constant is
unreachable code.

It is not. Every caller holding a payload and no file goes through here and
nothing else fills these in: that is the whole of `tests/test_hashing.py` today
and every future caller that builds a payload directly. Removing it would make
such a payload hash differently from the identical config loaded from disk.

**The two must AGREE, and the agreement is pinned by
`tests/test_config.py::test_the_hashing_defaults_agree_with_the_model_defaults`,**
because if they diverged the value reaching the hash would be pydantic's while
this constant still read as authoritative. Deliberate redundancy, per the
standing rule that doubled guards must be cross-commented so a later
simplification sees both -- the pointer back is in `Config`'s field defaults.
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


def digest(payload: Mapping[str, Any]) -> str:
    """Return the first 16 hex digits of the payload's canonical SHA-256.

    Public because `metamer.batch.geometry` computes `geometry_hash` with the
    same construction, and two spellings of "canonical" would eventually be two
    different canonicals.

    Args:
        payload: The mapping to digest.

    Returns:
        The truncated hex digest.
    """
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()[:16]


def normalize(config: Mapping[str, Any]) -> dict[str, Any]:
    """Fill declared defaults and stamp the algorithm version.

    `ALGORITHM_VERSION` is stamped rather than defaulted: it is a property of
    the installed code, not of the config, and a caller must not be able to
    supply it. Every hash goes through here, so the stamp reaches all three.

    Args:
        config: The config as supplied.

    Returns:
        A new mapping with every `CONFIG_DEFAULTS` key present,
        `ALGORITHM_VERSION_KEY` set from `ALGORITHM_VERSION` and
        `REGISTRY_VERSION_KEY` set from `registry.REGISTRY_VERSION`.

    Raises:
        ValueError: If the config carries either stamped key itself. Refused
            rather than overridden -- see those constants' docstrings. Both are
            named in one message: a bare lookup would raise anyway, so the
            message is the only thing distinguishing a deliberate refusal from
            an incidental one.
    """
    supplied = sorted({ALGORITHM_VERSION_KEY, REGISTRY_VERSION_KEY} & set(config))
    if supplied:
        raise ValueError(
            f"{supplied} is stamped from the installed code and must not appear "
            "in a config; it is refused rather than overridden so a config that "
            "tries to pin it fails loudly instead of being quietly ignored"
        )
    return {
        **CONFIG_DEFAULTS,
        **dict(config),
        ALGORITHM_VERSION_KEY: ALGORITHM_VERSION,
        REGISTRY_VERSION_KEY: REGISTRY_VERSION,
    }


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
        KeyError: If a config-supplied allowlisted field is absent -- `run_hash`
            is provenance, but a config that cannot be fit-hashed is not a run.
            `STAGE_4A_FIELDS` are excluded from that check: they come from an
            input rather than from the config, and §13.4 requires this to work
            with no data staged.
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
    _subset(payload, FIT_RELEVANT_FIELDS - STAGE_4A_FIELDS)
    if machine is not None:
        payload[MACHINE_KEY] = machine
    return payload


def fit_hash(config: Mapping[str, Any]) -> str:
    """Hash the fields determining theta-hat and log_lik.

    The warm-start key's first component (section 11.1) and the gate for
    reusing fits.
    """
    return digest(fit_payload(config))


def compat_hash(config: Mapping[str, Any]) -> str:
    """Hash the fields determining the stored derived arrays.

    The gate for reusing `/selection/`. Differs from `fit_hash` only by the
    criterion set, so a criterion-only change recomputes rather than refits.
    """
    return digest(compat_payload(config))


def run_hash(config: Mapping[str, Any], machine: str | None = None) -> str:
    """Hash everything, including runtime knobs and the machine fingerprint.

    **Provenance only, never a gate.** Runtime knobs appear here and nowhere
    else, which is what permits starting on the 64-core node and resuming on
    the mini PC -- a real workflow, made legitimate by section 11.3's
    determinism guarantee, and the same property that makes a future cloud
    burst a resume rather than a rerun.
    """
    return digest(run_payload(config, machine))


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
    return digest({"cpu": cpu_model, "cores": int(cores), "ram": int(total_ram_bytes)})
