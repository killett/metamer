"""Tests for the three-hash machinery (design doc section 13.3).

Two disciplines run through this file.

**Every hash comparison is blind to the hash function.** A test asserting
`fit_hash(a) == fit_hash(b)` still passes when the separators, the sort order,
the digest algorithm or the truncation length all change, because they change
both sides identically -- PROGRESS.md's cancellation rule, applied to a module
made entirely of comparisons. The cure is the same: an absolute value,
hand-derived. `GOLDEN_*` below are computed from a canonical JSON string
written out by hand in this file and hashed with `hashlib` directly, so they
share no construction with `hashing.canonical_json`.

**Stability is the product, not a property of it.** A hash that changes
between runs on identical input silently invalidates a 10^7-point store: every
resume reads as a mismatch. The cross-process test is the direct guard.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tomllib

import numpy as np
import pytest

from metamer.core.criteria import Criterion, rank_candidates
from metamer.core.hashing import (
    COMPAT_RELEVANT_FIELDS,
    CONFIG_DEFAULTS,
    FIT_RELEVANT_FIELDS,
    MACHINE_KEY,
    canonical_json,
    compat_hash,
    compat_payload,
    fit_hash,
    fit_payload,
    machine_fingerprint,
    run_hash,
    run_payload,
)
from metamer.core.params import ParamSpec
from metamer.core.terms import ProcessSpec, TermSpec
from metamer.core.transforms import Log
from tests.test_criteria import _scores

# The canonical rendering of `_config()` restricted to FIT_RELEVANT_FIELDS,
# written out by hand: keys sorted, `(",", ":")` separators, no whitespace,
# list order preserved because a signal-term list is ordered data. This string
# is the derivation; GOLDEN_FIT_HASH is its sha256 prefix, and both are
# independent of anything in `hashing.py`.
GOLDEN_FIT_PAYLOAD = (
    '{"data_uri":"s3://bucket/ssh.zarr","engine":"kalman","objective":"ml",'
    '"registry_version":"1","seed":0,"signal_terms":["constant","trend","annual"],'
    '"metamer_version":"0.1.0","variable":"sla"}'
)
GOLDEN_COMPAT_PAYLOAD = (
    '{"criteria":["aic"],"data_uri":"s3://bucket/ssh.zarr","engine":"kalman",'
    '"objective":"ml","registry_version":"1","seed":0,'
    '"signal_terms":["constant","trend","annual"],"metamer_version":"0.1.0",'
    '"variable":"sla"}'
)
GOLDEN_RUN_PAYLOAD = (
    '{"candidates":["white+matern12"],"criteria":["aic"],'
    '"data_uri":"s3://bucket/ssh.zarr","engine":"kalman","memory_budget_gb":4.0,'
    '"objective":"ml","output":"out.zarr","registry_version":"1","seed":0,'
    '"signal_terms":["constant","trend","annual"],"metamer_version":"0.1.0",'
    '"threads":4,"variable":"sla"}'
)
GOLDEN_FIT_HASH = "29de378159709ecc"
GOLDEN_COMPAT_HASH = "7c66ee0878f1bc8e"
GOLDEN_RUN_HASH = "1b660e9fee1dc96b"


def _config(**overrides):
    """A fully specified config: every allowlisted field present."""
    base = {
        "data_uri": "s3://bucket/ssh.zarr",
        "variable": "sla",
        "signal_terms": ["constant", "trend", "annual"],
        "objective": "ml",
        "engine": "kalman",
        "registry_version": "1",
        "metamer_version": "0.1.0",
        "seed": 0,
        "criteria": ["aic"],
        "candidates": ["white+matern12"],
        "memory_budget_gb": 4.0,
        "threads": 4,
        "output": "out.zarr",
    }
    base.update(overrides)
    return base


def _param(name: str, default: float) -> ParamSpec:
    """Build a positive-scale ParamSpec for hashing fixtures."""
    return ParamSpec(
        name=name,
        default=default,
        transform=Log(),
        bounds=(0.0, np.inf),
        diagnostic_limits=(1e-8, 1e8),
    )


# --------------------------------------------------------------------------
# Absolute values: the hash function itself is invisible to every comparison
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("hasher", "payload_fn", "payload", "golden"),
    [
        (fit_hash, fit_payload, GOLDEN_FIT_PAYLOAD, GOLDEN_FIT_HASH),
        (compat_hash, compat_payload, GOLDEN_COMPAT_PAYLOAD, GOLDEN_COMPAT_HASH),
        (run_hash, run_payload, GOLDEN_RUN_PAYLOAD, GOLDEN_RUN_HASH),
    ],
)
def test_each_hash_of_a_fully_specified_config_is_a_hand_derived_constant(
    hasher, payload_fn, payload, golden
):
    """All three hashes are pinned to values derived outside this module.

    Expected value determined independently: each `GOLDEN_*_PAYLOAD` above is
    the canonical JSON written out by hand -- that hash's fields in sorted key
    order with `(",", ":")` separators -- and each `GOLDEN_*_HASH` is the first
    16 hex digits of its SHA-256, computed with `hashlib` and not with
    anything from `hashing.py`. The string and the digest are checked
    separately, so a failure says which of the two moved.

    Bug this catches: EVERY OTHER TEST IN THIS FILE COMPARES TWO HASHES, and a
    change to the separators, the sort order, the digest algorithm or the
    truncation length moves both sides identically and is invisible to all of
    them -- the cancellation rule at the level of the hash function. All three
    are pinned rather than one because each payload builder can drift
    independently: a `run_payload` that filed a `None` fingerprint under the
    machine key changed every `run_hash` while leaving every comparison test
    green, and only an absolute value caught it.
    """
    assert canonical_json(payload_fn(_config())) == payload
    assert hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16] == golden
    assert hasher(_config()) == golden


def test_the_hash_is_identical_across_processes_with_different_hash_seeds():
    """Identical input hashes identically in a fresh interpreter.

    Expected value determined independently: `GOLDEN_FIT_HASH` again, so the
    subprocess is compared against a hand-derived constant rather than against
    this process. Three seeds, because `PYTHONHASHSEED` randomizes `str`
    hashing per process and one extra process could coincide.

    Bug this catches: THE FENCE'S `json.dumps(..., default=repr)`. Measured,
    `{"criteria": {"aic", "bic", "hqic"}}` renders as three different strings
    under seeds 1, 2 and 3, and an object without `__repr__` renders its
    memory address. Either one gives a different `compat_hash` every run, so
    every resume of a finished 10^7-point store reports a mismatch and refits
    it. This is the failure the module exists to prevent, and no comparison
    test in this file can see it -- both sides move together within one
    process.
    """
    code = f"from metamer.core.hashing import fit_hash;print(fit_hash({_config()!r}))"
    for seed in ("1", "2", "3"):
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONHASHSEED": seed},
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == GOLDEN_FIT_HASH


# --------------------------------------------------------------------------
# What the serializer refuses
# --------------------------------------------------------------------------


def test_a_value_json_cannot_represent_is_refused_by_name():
    """An unserializable value raises rather than being stringified.

    Expected value determined independently: `json.dumps` raises `TypeError`
    for a type it does not know, and the fence suppressed that with
    `default=repr`. Measured, a bare object then renders as
    `"<Foo object at 0x74c3bb3de900>"` -- a memory address, different in every
    process -- and a `set` renders in an order that varies with
    `PYTHONHASHSEED`. Both are silently unstable rather than wrong-looking.

    Bug this catches: reinstating `default=`. The failure it produces is not a
    crash but a hash that drifts, which is undetectable downstream: a resume
    sees a mismatch and refits, and the only symptom is a bill.
    """

    class _Unserializable:
        pass

    with pytest.raises(TypeError, match="candidates"):
        canonical_json({"candidates": _Unserializable()})
    with pytest.raises(TypeError, match="criteria"):
        canonical_json({"criteria": {"aic", "bic"}})


def test_a_non_string_mapping_key_is_refused():
    """A key JSON would coerce is refused before it can collide.

    Expected value determined independently: `json.dumps` silently coerces
    non-string keys to strings -- measured, `{1: "a"}` and `{"1": "a"}` both
    render as `{"1":"a"}`, and `{True: "a"}` renders as `{"true":"a"}`. Two
    distinct mappings, one canonical form.

    Bug this catches: accepting the coercion. A nested per-candidate mapping
    keyed by an integer index would hash identically to one keyed by the
    string of that index, so two different configurations share a hash and one
    resumes into the other's store. The coercion is silent and lossy in the
    one direction that matters, which is why this refuses rather than
    normalizing: normalizing would make the collision deliberate.
    """
    with pytest.raises(TypeError, match="per_candidate"):
        canonical_json({"per_candidate": {1: "white"}})


def test_a_non_finite_float_is_refused():
    """Infinity and NaN are not JSON and are not hashed as if they were.

    Expected value determined independently: `json.dumps` renders them as the
    bare tokens `Infinity` and `NaN`, which no conforming JSON reader accepts.
    `terms.py::_transform_args_canonical` already documents this exact trap for
    a `Logit` built with an infinite bound, and solves it there by
    stringifying every float. This module refuses instead, because an infinite
    memory budget is a user error while an infinite bijector bound is
    legitimate -- the divergence is deliberate and is stated in
    `canonical_json`'s docstring.

    Bug this catches: a canonical form that is not parseable JSON, so
    provenance written into zarr attributes cannot be read back by anything
    but Python.
    """
    with pytest.raises(ValueError, match="memory_budget_gb"):
        canonical_json({"memory_budget_gb": float("inf")})
    with pytest.raises(ValueError, match="seed"):
        canonical_json({"seed": float("nan")})


def test_a_missing_allowlisted_field_is_refused():
    """A field the allowlist declares fit-relevant must be present.

    Expected value determined independently: the allowlist is the statement
    "these fields determine theta-hat". A config lacking one has not been
    specified, so there is no fit for the hash to name.

    Bug this catches: THE FENCE'S `{key: config[key] for key in fields if key
    in config}`, which drops a missing field silently. Combined with an
    allowlist that is the whole point of the module, a single typo --
    `data_url` for `data_uri` -- demotes the data source to provenance-only,
    and two runs over DIFFERENT DATA then share a `fit_hash` and reuse each
    other's fits. The typo is in the config, so nothing else in the system is
    positioned to notice.
    """
    del_uri = _config()
    del del_uri["data_uri"]
    with pytest.raises(KeyError, match="data_uri"):
        fit_hash(del_uri)
    with pytest.raises(KeyError, match="data_uri"):
        compat_hash(del_uri)

    # Every missing field is named at once. A bare `config[key]` lookup also
    # raises KeyError, so the message is the only thing separating a deliberate
    # refusal from an incidental one -- and reporting the first missing field
    # per run turns one broken config into five edit-and-rerun cycles.
    del_two = _config()
    del del_two["data_uri"], del_two["variable"]
    with pytest.raises(KeyError, match="data_uri.*variable"):
        fit_hash(del_two)


def test_a_config_cannot_shadow_the_machine_slot():
    """The machine fingerprint's key is reserved.

    Expected value determined independently: `run_hash` merges the machine
    fingerprint into the config payload under one key, so a config carrying
    that key would overwrite it or be overwritten by it -- either way two
    different (config, machine) pairs collide, silently.

    Bug this catches: merging without a guard. The collision is between a
    provenance record and a user field, so it produces a run_hash that names
    the wrong machine, which is exactly the record anyone reaches for when a
    benchmark disagrees between boxes.
    """
    with pytest.raises(ValueError, match=MACHINE_KEY):
        run_hash(_config(**{MACHINE_KEY: "mine"}))


# --------------------------------------------------------------------------
# Normalization: the four axes, one test each
# --------------------------------------------------------------------------


def test_key_order_does_not_change_the_hash():
    """Insertion order is not part of the model.

    Expected value determined independently: `sort_keys=True` renders the same
    string for any insertion order, and design doc section 4.6 requires
    insensitivity to dict ordering.

    Bug this catches: dropping `sort_keys`. Python dicts preserve insertion
    order, so a config assembled by a different code path -- a CLI parser
    versus a YAML loader -- would hash differently while describing the same
    run.
    """
    assert canonical_json({"b": 1, "a": 4.0}) == canonical_json({"a": 4.0, "b": 1})
    forward = _config()
    backward = dict(reversed(list(forward.items())))
    assert list(forward) != list(backward)
    assert run_hash(forward) == run_hash(backward)


def test_a_comment_does_not_change_the_hash():
    """Hash the parsed model, not the file text.

    Expected value determined independently: a TOML comment is not part of the
    parsed document, so `tomllib.loads` returns equal mappings for the two
    texts below. Asserting that first makes the test say which layer
    normalizes -- the loader, not the hasher.

    Bug this catches: hashing file bytes, under which adding an explanatory
    comment to a config invalidates a completed 10^7-point store. Design doc
    section 13.3 names this as the reason the normalized model is hashed.
    """
    plain = 'data_uri = "s3://b/x.zarr"\nseed = 0\n'
    commented = (
        '# which bucket the SSH lives in\ndata_uri = "s3://b/x.zarr"\nseed = 0\n'
    )
    assert tomllib.loads(plain) == tomllib.loads(commented)
    assert run_hash(_config(**tomllib.loads(plain))) == run_hash(
        _config(**tomllib.loads(commented))
    )


def test_whitespace_does_not_change_the_hash():
    """Blank lines and spacing are not part of the model either.

    Expected value determined independently: TOML treats runs of whitespace
    and blank lines between key-value pairs as insignificant, so the two texts
    parse to equal mappings.

    Bug this catches: the same text-hashing failure as the comment test, by a
    different route -- reformatting a config file, or a checkout with
    different line endings, would invalidate the store. Tested separately from
    comments because one test covering both cannot say which normalization is
    broken.
    """
    tight = 'data_uri = "s3://b/x.zarr"\nseed = 0\n'
    loose = 'data_uri   =    "s3://b/x.zarr"\n\n\nseed  =  0\n'
    assert tomllib.loads(tight) == tomllib.loads(loose)
    assert run_hash(_config(**tomllib.loads(tight))) == run_hash(
        _config(**tomllib.loads(loose))
    )


def test_an_explicit_default_hashes_the_same_as_an_omitted_one():
    """Writing a default out is not a different model from leaving it off.

    Expected value determined independently: `CONFIG_DEFAULTS` declares
    `seed = 0`, so a config omitting `seed` and one setting `seed = 0`
    describe the same run and must hash the same. The third assertion pins
    that this is filling a declared default and not ignoring the field: a
    config setting `seed = 1` must hash differently.

    Bug this catches: hashing the config as supplied. A user who writes out a
    default for clarity would get a different `fit_hash` than one who omits
    it, so the two could not share warm starts and a resume after an edit that
    only made an implicit value explicit would refit 10^7 points.
    """
    explicit = _config(seed=0)
    implicit = _config()
    del implicit["seed"]
    assert fit_hash(explicit) == fit_hash(implicit)
    assert fit_hash(_config(seed=1)) != fit_hash(implicit)


def test_a_declared_default_is_not_silently_a_hash_of_nothing():
    """`CONFIG_DEFAULTS` covers only fields with a real default.

    Expected value determined independently: design doc section 13.3 names the
    sharp edge -- because defaults are included in the hash, any version bump
    touching a compat-relevant default invalidates every in-progress store. So
    the defaults table is deliberately small, and every key in it must be one
    the allowlist actually hashes, or the entry is dead weight that still
    carries that risk.

    Bug this catches: a defaults table that drifts to cover provenance-only
    fields, which would make `run_hash` depend on values no one declared, or
    one that names a field no hash reads, which reads as protection that is
    not there.
    """
    assert set(CONFIG_DEFAULTS) <= COMPAT_RELEVANT_FIELDS
    assert CONFIG_DEFAULTS == {"seed": 0, "objective": "ml"}
    bare = {k: v for k, v in _config().items() if k not in CONFIG_DEFAULTS}
    assert set(CONFIG_DEFAULTS) <= set(compat_payload(bare))


def test_float_formatting_is_shortest_roundtrip_and_distinguishes_neighbours():
    """Floats render deterministically without collapsing distinct values.

    Expected value determined independently: `0.1 + 0.2` is exactly the
    float64 whose shortest round-tripping decimal is 0.30000000000000004, so
    the computed value and that literal are the SAME float and must hash the
    same. They are not the same as 0.3, which is a different float64, and the
    two differ by one ulp -- so a serializer rounding to fewer digits would
    make them collide. Both facts are properties of IEEE 754, not of this
    module.

    Bug this catches: formatting floats with `%g`, `%.6f`, or `str()` under an
    older Python, any of which would give 0.3 and 0.30000000000000004 the same
    rendering and so the same hash. Two runs at genuinely different budgets
    would then share a `run_hash`, and the provenance record would name a
    configuration that was never run.
    """
    assert run_hash(_config(memory_budget_gb=0.1 + 0.2)) == run_hash(
        _config(memory_budget_gb=0.30000000000000004)
    )
    assert run_hash(_config(memory_budget_gb=0.3)) != run_hash(
        _config(memory_budget_gb=0.30000000000000004)
    )


def test_list_order_is_significant():
    """An ordered field is not normalized into a set.

    Expected value determined independently: `signal_terms` fixes the column
    order of the design matrix, so `[constant, trend]` and `[trend, constant]`
    produce different beta layouts and different per-column stored arrays.
    Sorting them would be a normalization that loses information.

    Bug this catches: over-normalizing -- sorting every list on the way in, so
    two runs whose stored trend lives in a different column share a
    `fit_hash`, and a resume writes one run's coefficients under the other's
    column labels.
    """
    assert fit_hash(_config(signal_terms=["constant", "trend"])) != fit_hash(
        _config(signal_terms=["trend", "constant"])
    )


# --------------------------------------------------------------------------
# The allowlist
# --------------------------------------------------------------------------


def test_compat_relevance_is_an_allowlist_golden_set():
    """The two field sets are pinned against a hand-written list.

    Expected value determined independently by reading design doc section 13.3
    and listing the fields by hand: `fit_hash` covers data source and
    selection, signal spec, objective, engine, registry version, seeds and the
    metamer version, and `compat_hash` adds the criterion set. The last two
    assertions state the structural facts that make the split mean anything --
    fit is a strict subset of compat, and neither contains a runtime knob.

    Bug this catches: a denylist, under which every newly added field silently
    becomes compat-relevant and the failure mode is "resume broke and nobody
    knows why". Golden-file discipline: changing the set requires editing this
    list, which is the point at which someone has to justify it.
    """
    assert FIT_RELEVANT_FIELDS == frozenset(
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
    assert COMPAT_RELEVANT_FIELDS == FIT_RELEVANT_FIELDS | {"criteria"}
    assert FIT_RELEVANT_FIELDS < COMPAT_RELEVANT_FIELDS
    assert not COMPAT_RELEVANT_FIELDS & {
        "memory_budget_gb",
        "threads",
        "output",
        "candidates",
    }


def test_an_unknown_field_is_provenance_only():
    """A field nobody declared defaults to `run_hash` alone.

    Expected value determined independently: the allowlist names what is
    relevant, so anything absent from it is by definition not, and design doc
    section 13.3 requires the default to be provenance-only.

    Bug this catches: the denylist failure mode. Under a denylist, adding an
    experimental knob to the config schema invalidates every in-progress
    store, and the release that did it looks innocent.
    """
    base = _config()
    extended = _config(new_experimental_knob=True)
    assert fit_hash(base) == fit_hash(extended)
    assert compat_hash(base) == compat_hash(extended)
    assert run_hash(base) != run_hash(extended)


# --------------------------------------------------------------------------
# The three-hash structure
# --------------------------------------------------------------------------


def test_adding_a_criterion_changes_compat_but_not_fit():
    """A criterion change must not discard warm starts or force a refit.

    Expected value determined independently: design doc section 13.3 puts the
    criterion set in `compat_hash` and out of `fit_hash`, because AIC versus
    BIC changes the stored `/selection/` arrays and changes nothing about
    where the optimizer lands.

    Bug this catches: a single hash boundary, under which adding HQIC to a
    finished 10^7-point run demands a full refit to compute arithmetic on
    numbers already sitting in the store.
    """
    base = _config()
    more = _config(criteria=["aic", "hqic"])
    assert fit_hash(base) == fit_hash(more)
    assert compat_hash(base) != compat_hash(more)


def test_the_candidate_set_is_outside_both_gates():
    """Extending the candidate set is an incremental operation.

    Expected value determined independently: design doc section 13.3's table
    says `fit_hash` covers "**Not** the candidate set", and section 11.1 keys
    warm starts on `(fit_hash, candidate spec_hash)` -- the candidate is the
    other half of that pair, so folding it into `fit_hash` would make the pair
    redundant and the gate wrong.

    Bug this catches: THE FENCE HAS NO TEST FOR THIS, though its own
    acceptance criterion names the candidate set beside the criterion set.
    Including it would discard every warm start and every fitted candidate the
    moment a user appends one more candidate to an existing run -- the exact
    incremental workflow the three-hash split is for.
    """
    base = _config()
    more = _config(candidates=["white+matern12", "white+matern32"])
    assert fit_hash(base) == fit_hash(more)
    assert compat_hash(base) == compat_hash(more)
    assert run_hash(base) != run_hash(more)


def test_runtime_knobs_change_only_run_hash():
    """Memory budget and thread count are provenance, never a gate.

    Expected value determined independently: design doc section 13.3 lists
    memory budget, tile size, thread count, output path and verbosity under
    `run_hash` only, and section 11.3's determinism guarantee is what makes
    that safe.

    Bug this catches: gating resumption on runtime knobs, which would block
    starting on the 64-core box and resuming on the mini PC -- a real workflow
    the determinism guarantee exists to permit, and the same property that
    makes a future cloud burst a resume rather than a rerun.
    """
    base = _config()
    other = _config(memory_budget_gb=1.0, threads=64, output="elsewhere.zarr")
    assert fit_hash(base) == fit_hash(other)
    assert compat_hash(base) == compat_hash(other)
    assert run_hash(base) != run_hash(other)


def test_objective_is_fit_relevant():
    """theta_hat_REML != theta_hat_ML, so the objective gates fit reuse.

    Expected value determined independently: REML maximizes the likelihood of
    a different quantity -- error contrasts rather than the data -- so its
    optimum is a different point in parameter space. Design doc section 11.1
    states the consequence: a warm-start array written under a different
    objective must not be read.

    Bug this catches: reusing a warm start across objectives, which produces
    converged-looking fits at the wrong optimum -- the worst failure mode in
    the system, because every downstream number is finite, plausible and
    wrong.
    """
    assert fit_hash(_config()) != fit_hash(_config(objective="reml"))


@pytest.mark.parametrize("field", sorted(FIT_RELEVANT_FIELDS))
def test_a_fit_mismatch_always_forces_a_compat_mismatch(field):
    """`fit_hash` differing with `compat_hash` matching must be impossible.

    Expected value determined independently: `compat_hash` is defined over a
    strict superset of `fit_hash`'s fields, so any change visible to the
    smaller set is visible to the larger. Section 12.8's mismatch behaviour
    depends on it: a `compat_hash` match is taken as licence to recompute the
    derived arrays from stored primitives WITHOUT refitting, which is only
    sound if a matching `compat_hash` guarantees a matching fit.

    Bug this catches: computing `compat_hash` over a disjoint set -- say, the
    criterion set alone -- which types and reads identically and makes
    "compat matches, fit differs" reachable. A resume would then recompute
    selection arrays over primitives from a different model, producing a
    complete, confident, wrong map. Parametrized over every fit-relevant field
    because one field is not evidence about the set.
    """
    changed = _config(
        **{field: ["something", "else"] if field == "signal_terms" else 99}
    )
    assert fit_hash(changed) != fit_hash(_config())
    assert compat_hash(changed) != compat_hash(_config())


# --------------------------------------------------------------------------
# The machine fingerprint
# --------------------------------------------------------------------------


def test_the_machine_fingerprint_depends_on_exactly_its_three_inputs():
    """Same instance type, same fingerprint; any change, a different one.

    Expected value determined independently: design doc section 11.4 keys the
    calibration cache on the instance type, so the fingerprint must be a
    function of CPU model, core count and RAM and of nothing else. Hostname is
    meaningless on ephemeral nodes and thread count is a runtime knob, so
    neither is an argument -- a fresh spot instance of the same type must
    reuse its calibration.

    Bug this catches: THE FENCE SHIPS THIS FUNCTION WITH NO TEST AT ALL,
    including its two docstring claims. A fingerprint folding in hostname
    would give every spot instance a cold calibration cache, which is a
    measurable cost with no symptom other than slowness.
    """
    ref = machine_fingerprint("AMD EPYC 7B12", 64, 256 * 1024**3)
    assert machine_fingerprint("AMD EPYC 7B12", 64, 256 * 1024**3) == ref
    assert machine_fingerprint("AMD EPYC 7B13", 64, 256 * 1024**3) != ref
    assert machine_fingerprint("AMD EPYC 7B12", 4, 256 * 1024**3) != ref
    assert machine_fingerprint("AMD EPYC 7B12", 64, 16 * 1024**3) != ref


def test_the_machine_fingerprint_reaches_run_hash_and_no_other():
    """Which box a run happened on is provenance.

    Expected value determined independently: design doc section 13.3 lists the
    machine fingerprint under `run_hash` only. Section 11.3's determinism
    guarantee is the reason -- the same config on two machines must produce
    the same numbers, so the machine cannot gate reuse.

    Bug this catches: threading the machine into the fit or compat payload,
    which would mean a run started on the 64-core box could never be resumed
    on the mini PC. That workflow is the stated justification for having three
    hashes rather than two.
    """
    config = _config()
    machine = machine_fingerprint("Intel N100", 4, 16 * 1024**3)
    assert run_hash(config, machine) != run_hash(config)
    assert run_hash(config, machine) != run_hash(
        config, machine_fingerprint("Intel N100", 4, 32 * 1024**3)
    )
    assert fit_hash(config) == GOLDEN_FIT_HASH


# --------------------------------------------------------------------------
# The workflow the split exists to permit
# --------------------------------------------------------------------------


def test_adding_a_criterion_reranks_stored_primitives_without_refitting():
    """PHASE 2 STORE CONTRACT, tested today against in-memory primitives.

    Expected value determined independently, by hand from the AIC and BIC
    definitions on a two-candidate, two-series block. With loglik
    [[-50, -48], [-30, -36]], k = 2 for candidate 0 and 4 for candidate 1, and
    n = 100: AIC = 2k - 2L gives [[104, 104], [64, 80]] -- an exact tie on
    series 0 -- and BIC = k log n - 2L with log 100 = 4.60517 gives
    [[109.21, 114.42], [69.21, 90.42]], so BIC picks candidate 0 on both
    series while AIC ties on the first. The point is not the ranking: it is
    that `rank_candidates` takes ONLY the stored primitives and never a spec,
    a design matrix or the data, so the recompute is possible from what
    section 12.5 already stores.

    Bug this catches: a hash split that permits the recompute in principle
    while the recompute path needs something the store does not hold. Design
    doc section 12.8 says a `compat_hash` mismatch with a matching `fit_hash`
    recomputes and continues; if `rank_candidates` needed the data, that
    sentence would be unimplementable and the whole three-hash split would buy
    nothing. Also fails if re-ranking mutated the primitives, which would make
    the second criterion's answer depend on the first's having run.
    """
    scores = _scores([[-50.0, -48.0], [-30.0, -36.0]], k=np.array([[2.0, 4.0]] * 2))
    loglik_before = scores.loglik.copy()

    base = _config()
    resumed = _config(criteria=["aic", "bic"])
    assert fit_hash(base) == fit_hash(resumed)
    assert compat_hash(base) != compat_hash(resumed)

    aic = rank_candidates(scores, Criterion.AIC)
    bic = rank_candidates(scores, Criterion.BIC)

    np.testing.assert_array_equal(scores.loglik, loglik_before)
    np.testing.assert_allclose(aic.ic_best, [104.0, 64.0], rtol=1e-12)
    np.testing.assert_allclose(
        bic.ic_best, [2 * np.log(100.0) + 100.0, 2 * np.log(100.0) + 60.0], rtol=1e-12
    )
    np.testing.assert_array_equal(bic.best_index, [0, 0])
    np.testing.assert_allclose(
        rank_candidates(scores, Criterion.AIC).delta_ic, aic.delta_ic, rtol=0.0
    )


# --------------------------------------------------------------------------
# Spec identity: shared_with
# --------------------------------------------------------------------------


def test_the_three_hashes_are_on_the_public_surface():
    """The hashes are reachable from `metamer.core` beside `fit` and `lint`.

    Expected value determined independently: `metamer/core/__init__.py`
    declares the array-level public API, and these four are what a caller
    needs to write provenance or decide whether to resume -- the three gates
    and the fingerprint that keys the calibration cache. The payload helpers
    and the serializer stay unexported: they exist for inspection and for this
    file, not for callers.

    Bug this catches: shipping the resumption gate at a module path a caller
    has to go read the source to find. Provenance that is inconvenient to
    write does not get written, and a store without its three hashes cannot be
    resumed at all.
    """
    import metamer.core as core

    assert {"fit_hash", "compat_hash", "run_hash", "machine_fingerprint"} <= set(
        core.__all__
    )
    assert core.fit_hash is fit_hash
    assert core.compat_hash is compat_hash
    assert core.run_hash is run_hash
    assert core.machine_fingerprint is machine_fingerprint


def test_two_specs_differing_only_in_shared_with_hash_differently():
    """A shared-parameter declaration changes what the model is.

    Expected value determined independently: design doc section 4.7 counts a
    shared parameter once rather than twice, so two specs differing only in
    `shared_with` have different `k` and are different models. `canonical()`
    defines spec identity, so identity must see the field.

    Bug this catches: `TermSpec.canonical()` omitting `shared_with`, which it
    did. The omission is invisible today because `n_free()` refuses such a
    spec before anything hashes it -- but that is an argument about
    REACHABILITY, not about identity, and reachability changes the moment
    sharing is implemented. At that point two genuinely different models would
    share a `spec_hash` and one would silently reuse the other's cached
    `expm`, warm start and fits. Task 16 owns spec identity, so it is the
    place to fix it; the test passes today via the refusal path and keeps
    passing when sharing lands.
    """
    params = {"sigma": _param("sigma", 1.0), "rho": _param("rho", 5.0)}
    plain = TermSpec(kind="matern12", params=params, ordering_param="rho")
    shared = TermSpec(
        kind="matern12",
        params=params,
        ordering_param="rho",
        shared_with={"sigma": "other_term"},
    )
    assert plain.canonical() != shared.canonical()
    assert ProcessSpec((plain,)).spec_hash() != ProcessSpec((shared,)).spec_hash()


def test_a_shared_with_declaration_stays_json_safe_and_order_independent():
    """The new field does not break the canonical-JSON round trip.

    Expected value determined independently: `ProcessSpec.spec_hash` serializes
    `canonical()` with `json.dumps`, and design doc section 4.6 requires
    insensitivity to dict ordering. A `Mapping[str, str]` written in two
    different insertion orders is the same declaration.

    Bug this catches: emitting `shared_with` as the raw mapping, so the hash
    depends on the order the user happened to write the pairs in -- the exact
    instability `sort_keys` exists to remove, reintroduced by a field added
    after the invariant was established. It also fails if the field is emitted
    as a non-JSON type, which would make `spec_hash` raise for every sharing
    spec.
    """
    params = {"sigma": _param("sigma", 1.0), "rho": _param("rho", 5.0)}
    forward = TermSpec(
        kind="matern12",
        params=params,
        ordering_param="rho",
        shared_with={"sigma": "a", "rho": "b"},
    )
    backward = TermSpec(
        kind="matern12",
        params=params,
        ordering_param="rho",
        shared_with={"rho": "b", "sigma": "a"},
    )
    encoded = json.dumps(forward.canonical(), sort_keys=True, separators=(",", ":"))
    assert json.loads(encoded) == forward.canonical()
    assert ProcessSpec((forward,)).spec_hash() == ProcessSpec((backward,)).spec_hash()

    # Serialized WITHOUT sort_keys, so this bites `canonical()`'s own ordering
    # rather than `spec_hash`'s. `spec_hash` passes sort_keys=True, which sorts
    # nested mappings too and would mask an unsorted `shared_with` -- the
    # assertion above cannot fail while that flag is set. `canonical()` promises
    # a canonical dict, so a consumer serializing it any other way must get the
    # same bytes.
    assert json.dumps(forward.canonical()) == json.dumps(backward.canonical())
