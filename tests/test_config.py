"""`metamer.config.load`, and the hash boundary it is the only way through.

Every test here loads from a REAL FILE. A `Config` built inline has not been
through `tomllib`, pydantic or the flattening, so a hash computed from it is
evidence about the object and not about the config path -- and the config path
is the whole subject.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from pydantic import ValidationError

import metamer
from metamer import config as config_module
from metamer.config.model import Audit
from metamer.core import hashing

# The canonical rendering of `_GOLDEN_TOML` restricted to each allowlist,
# written out BY HAND: keys sorted, `(",", ":")` separators, no whitespace, list
# order preserved because a signal-term list is ordered data. These strings are
# the derivation; the hex below is each one's sha256 prefix, taken with
# `hashlib` directly so it shares no construction with `canonical_json`.
#
# THE FIT STRING IS DELIBERATELY IDENTICAL TO `tests/test_hashing.py`'s
# GOLDEN_FIT_PAYLOAD, and so is its digest. That is not duplication -- it is the
# claim this module exists to make: a config that comes off disk through
# pydantic and the block flattening produces the SAME fit payload as the
# hand-built mapping the hashing tests use. If the two ever disagree, the config
# path has introduced a field, dropped one, or renamed one, and no test that
# only compares configs against other configs could see it.
_GEOMETRY = "0123456789abcdef"
"""A stand-in fingerprint, so the config layer's goldens do not depend on a file.

The REAL derivation -- which components, read from which dataset -- is
`tests/test_geometry.py`'s subject. Using a literal here keeps the two apart:
this module asserts that a config off disk assembles the payload correctly, and
a fingerprint computed from a fixture would make every constant below depend on
xarray's rounding of a coordinate array.
"""

_GOLDEN_FIT_PAYLOAD = (
    '{"algorithm_version":"2","engine":"kalman",'
    '"geometry_hash":"0123456789abcdef",'
    '"objective":"ml","registry_version":"1","seed":0,'
    '"signal_terms":["constant","trend","annual"],"variable":"sla",'
    '"warm_start_coarse_stride":8,"warm_start_enabled":true,'
    '"warm_start_interpolation_rule":"nearest_valid","warm_start_spiral_bound":4,'
    '"warm_start_tie_break":"lowest_yx"}'
)
_GOLDEN_COMPAT_PAYLOAD = (
    '{"algorithm_version":"2","criteria":["aic","hqic"],"engine":"kalman",'
    '"geometry_hash":"0123456789abcdef",'
    '"objective":"ml","registry_version":"1","seed":0,'
    '"signal_terms":["constant","trend","annual"],"variable":"sla",'
    '"warm_start_coarse_stride":8,"warm_start_enabled":true,'
    '"warm_start_interpolation_rule":"nearest_valid","warm_start_spiral_bound":4,'
    '"warm_start_tie_break":"lowest_yx"}'
)
GOLDEN_FIT_HASH = "91d7cbf6d0350072"
GOLDEN_COMPAT_HASH = "71f01dd155aace17"

#: What the two strings above hashed to before `ALGORITHM_VERSION` became "2".
#:
#: **THIS MODULE'S GOLDENS HAD NO REVERSAL UNTIL 2026-08-27, AND THAT WAS THE
#: GAP.** `tests/test_hashing.py` carries `_HISTORY` and reverses its three
#: constants one hop at a time; these two are not in it, so for two allowlist
#: changes and one version bump they were re-derived with nothing able to tell a
#: hand derivation from a value pasted out of a failure. The pair below closes
#: that for the bump, and `test_the_goldens_reverse_to_the_previous_version` is
#: the executable form.
_PREVIOUS_VERSION_HASHES = ("1eb1fd731b4ae8d6", "8e7c1e4c82d36022")

# NO GOLDEN FOR `run_hash`, AND THE REASON IS WORTH STATING. `run_hash` carries
# `metamer_version`, which `hatch-vcs` derives from the git tag, so it changes
# on every commit -- measured here as `0.1.1.dev23+g883c0eb8b`. A golden for it
# would fail on the next commit and be "fixed" by pasting the new value, which
# is precisely the discipline `tests/test_hashing.py` exists to protect. What
# `run_hash` must satisfy is STABILITY ACROSS PROCESSES at a fixed tree, and
# that is what the cross-process test asserts for it.

_GOLDEN_TOML = """
    # A comment, which must not reach any hash.
    data_uri = "s3://bucket/ssh.zarr"
    variable = "sla"
    signal_terms = ["constant", "trend", "annual"]
    candidates = ["white", "white + matern12"]
    criteria = ["aic", "hqic"]
    memory_budget_gb = 1.0
"""
"""The golden config. **The budget is named explicitly since Phase 2b Task 3.**

It has no effect on either golden payload above -- `memory_budget_gb` is in
neither allowlist, which the goldens themselves demonstrate by not moving -- and
it is here because the field became `float | None` with `None` meaning *the
config did not say*. An unresolved config has no `run_hash`, and this module's
`run_hash` tests are about other fields entirely; naming the budget keeps them
about their own subjects. The omitted case has its own test.
"""

_UNSET_BUDGET_TOML = _GOLDEN_TOML.replace("memory_budget_gb = 1.0", "")
"""The same config with the budget omitted -- the unset sentinel's fixture."""


def _write(tmp_path: Path, text: str, name: str = "config.toml") -> Path:
    path = tmp_path / name
    path.write_text(textwrap.dedent(text))
    return path


def _golden(tmp_path: Path) -> Path:
    return _write(tmp_path, _GOLDEN_TOML)


# --------------------------------------------------------------------------
# The golden payloads: the absolute anchors
# --------------------------------------------------------------------------


def test_the_config_path_produces_the_hand_derived_payloads(tmp_path):
    """A config off disk hashes to the hand-written canonical JSON.

    Expected value determined independently: the strings at the top of this
    module were written by hand from the allowlists and hashed with `hashlib`
    directly, sharing no construction with `canonical_json`.

    THIS IS THE ONLY ABSOLUTE ASSERTION IN THE MODULE AND EVERY OTHER TEST HERE
    DEPENDS ON IT. The rest are differential -- "field X moves hash Y" -- and a
    difference cannot see anything constant across both sides: a flattening that
    prefixed every key wrongly, a payload that dropped `seed` entirely, or a
    `load` that returned the same object regardless of its argument would leave
    every differential test green. That is the cancellation rule, and this test
    is the cure.

    Bug it catches: the block flattening emitting `warmstart_enabled`,
    `warm_start.enabled` or a nested mapping. Any of those makes the five
    warm-start settings invisible to `FIT_RELEVANT_FIELDS` -- `_subset` would
    raise, which is the loud case -- or, worse, visible under a name the
    allowlist happens to contain for some other reason.
    """
    cfg = config_module.load(_golden(tmp_path))
    payload = hashing.fit_payload(cfg.to_payload(_GEOMETRY))

    assert json.dumps(payload, sort_keys=True, separators=(",", ":")) == (
        _GOLDEN_FIT_PAYLOAD
    )
    assert cfg.fit_hash(_GEOMETRY) == GOLDEN_FIT_HASH
    assert (
        hashlib.sha256(_GOLDEN_FIT_PAYLOAD.encode("utf-8")).hexdigest()[:16]
        == GOLDEN_FIT_HASH
    )

    compat = hashing.compat_payload(cfg.to_payload(_GEOMETRY))
    assert json.dumps(compat, sort_keys=True, separators=(",", ":")) == (
        _GOLDEN_COMPAT_PAYLOAD
    )
    assert cfg.compat_hash(_GEOMETRY) == GOLDEN_COMPAT_HASH


def test_the_goldens_reverse_to_the_previous_version():
    """Undoing the 2026-08-27 bump reproduces the constants it replaced.

    Expected values determined independently: `_PREVIOUS_VERSION_HASHES` are the
    two strings this module carried before `ALGORITHM_VERSION` became "2". They
    are hardcoded history, derived nowhere, so they are a reference this file
    cannot get wrong in the same way twice.

    THIS IS THE ONLY THING THAT SAYS THE REGENERATION WAS HONEST, and it did not
    exist here until the bump. A golden edited to match failing output passes
    `test_the_config_path_produces_the_hand_derived_payloads` exactly as a
    hand-derived one does -- both are self-consistent. What separates them is
    that a hand-written string still contains the previous one as a sub-case, so
    putting the old version back must return the old digests.

    Bug this catches: closing the next `ALGORITHM_VERSION` bump by running the
    suite and pasting two new hex strings, which pins whatever the code now
    produces and turns this module into a mirror of `hashing.py`.

    **The substitution is textual and touches nothing else**, so a bump that had
    also moved a field would fail here rather than reverse cleanly -- which is
    the case the assertion is really about.
    """
    for payload, previous in zip(
        (_GOLDEN_FIT_PAYLOAD, _GOLDEN_COMPAT_PAYLOAD),
        _PREVIOUS_VERSION_HASHES,
        strict=True,
    ):
        before = payload.replace(
            '"algorithm_version":"2"', '"algorithm_version":"1"', 1
        )
        assert before != payload, "the substitution must actually change the string"
        assert hashlib.sha256(before.encode("utf-8")).hexdigest()[:16] == previous


# --------------------------------------------------------------------------
# The model is hashed, not the file
# --------------------------------------------------------------------------


def test_comments_key_order_and_explicit_defaults_do_not_move_a_hash(tmp_path):
    """Three spellings of one configuration hash identically.

    Expected value determined independently: the hashed object is the validated
    model, and none of comments, key order or explicit-versus-default survives
    validation. All three must therefore reach the same payload.

    Bug this catches: hashing the file text or the raw parse. A user who
    reformats their config, adds a comment explaining a choice, or writes out a
    default they had been relying on implicitly would invalidate a 10^7-point
    store and refit it, with no exception, no warning and no symptom but a bill.

    The three spellings vary all three axes at once deliberately: they are the
    same mechanism -- text that must not reach the payload -- and separating
    them would triple the test without testing anything more.
    """
    plain = config_module.load(_golden(tmp_path))
    reordered = config_module.load(
        _write(
            tmp_path,
            """
            criteria = ["aic", "hqic"]
            memory_budget_gb = 1.0
            variable = "sla"
            candidates = ["white", "white + matern12"]
            signal_terms = ["constant", "trend", "annual"]
            data_uri = "s3://bucket/ssh.zarr"
            """,
            "reordered.toml",
        )
    )
    explicit = config_module.load(
        _write(
            tmp_path,
            """
            data_uri = "s3://bucket/ssh.zarr"   # trailing comment
            variable = "sla"
            signal_terms = ["constant", "trend", "annual"]
            candidates = ["white", "white + matern12"]
            criteria = ["aic", "hqic"]
            objective = "ml"
            seed = 0
            engine = "kalman"
            # NOT a spelling of the default, and that is the point: since Phase
            # 2b Task 3 `memory_budget_gb` has no declared default, so omitting
            # it means "the config did not say" and is a DIFFERENT config from
            # this one. It is written out in all three spellings so this test
            # stays about text that must not reach the payload.
            memory_budget_gb = 1.0

            [warm_start]
            enabled = true
            coarse_stride = 8
            """,
            "explicit.toml",
        )
    )

    for other in (reordered, explicit):
        assert other.fit_hash(_GEOMETRY) == plain.fit_hash(_GEOMETRY)
        assert other.compat_hash(_GEOMETRY) == plain.compat_hash(_GEOMETRY)
        assert other.run_hash() == plain.run_hash()


def test_a_json_config_and_a_toml_config_agree(tmp_path):
    """`.json` is accepted for machine-generated configs and hashes the same.

    Expected value determined independently: the format is a transport, and the
    model is what is hashed, so two transports of one configuration cannot
    differ.

    Bug this catches: the JSON path skipping validation or the flattening --
    e.g. `Config(**raw)` instead of `model_validate` -- which would let a
    generated config bypass `extra="forbid"` and carry a typo straight into
    provenance.
    """
    toml = config_module.load(_golden(tmp_path))
    as_json = _write(
        tmp_path,
        json.dumps(
            {
                "data_uri": "s3://bucket/ssh.zarr",
                "variable": "sla",
                "signal_terms": ["constant", "trend", "annual"],
                "candidates": ["white", "white + matern12"],
                "criteria": ["aic", "hqic"],
            }
        ),
        "config.json",
    )
    assert config_module.load(as_json).fit_hash(_GEOMETRY) == toml.fit_hash(_GEOMETRY)


# --------------------------------------------------------------------------
# The allowlist partition, with its positive control
# --------------------------------------------------------------------------


def _moved(tmp_path: Path, name: str, body: str) -> tuple[bool, bool, bool]:
    """Return which of (fit, compat, run) moved when `body` replaces the golden.

    The single mutation helper every partition test below shares, so that
    `test_a_run_only_field_moves_no_gate`'s negative and the positive controls
    around it exercise the same wiring. A helper that silently failed to apply
    its override would otherwise make every negative pass.
    """
    base = config_module.load(_golden(tmp_path))
    changed = config_module.load(_write(tmp_path, body, name))
    return (
        changed.fit_hash(_GEOMETRY) != base.fit_hash(_GEOMETRY),
        changed.compat_hash(_GEOMETRY) != base.compat_hash(_GEOMETRY),
        changed.run_hash() != base.run_hash(),
    )


_WITH = """
    data_uri = "s3://bucket/ssh.zarr"
    variable = "sla"
    signal_terms = ["constant", "trend", "annual"]
    candidates = ["white", "white + matern12"]
    criteria = ["aic", "hqic"]
    memory_budget_gb = 1.0
"""
"""The golden body, for tests that append a block to it.

**The budget matches `_GOLDEN_TOML`'s deliberately**, because `_moved` compares
against the golden and an unnamed budget is a real difference since Task 3 --
one that would show up as a moved `run_hash` in every test here and be read as
the field under test moving it.
"""


def test_the_warm_start_coarse_stride_moves_fit_hash(tmp_path):
    """Changing pass 1's stride invalidates every stored fit.

    THIS IS THE (a2) CHECK FOR THE FOURTH ALLOWLIST FINDING, and the point is
    that it asserts the MOVEMENT rather than the membership. `FIT_RELEVANT_FIELDS`
    containing `warm_start_coarse_stride` is a name; that a change to the config
    field reaches the payload under that exact name, survives the flattening and
    moves the digest is the gate. Phase 1 shipped three fields that passed the
    first test and failed the second.

    Expected value determined independently: §11.1 -- a stale warm start
    produces converged-looking fits at the WRONG optimum, so the stride is fit
    identity, and `COMPAT_RELEVANT_FIELDS` is a strict superset so compat must
    move too.

    Bug this catches: the warm-start cache keyed on `(fit_hash, spec_hash)`
    accepting a stale entry after the coarse grid changed underneath it. Every
    resulting fit converges, reports `ok`, and sits at a different optimum from
    the one the config asks for.
    """
    assert _moved(
        tmp_path, "stride.toml", _WITH + "\n[warm_start]\ncoarse_stride = 16\n"
    ) == (True, True, True)


@pytest.mark.parametrize(
    ("block_body", "expected"),
    [
        ("[warm_start]\nenabled = false\n", (True, True, True)),
        ("[warm_start]\nspiral_bound = 7\n", (True, True, True)),
        ("[warm_start]\ncoarse_stride = 16\n", (True, True, True)),
        # Setting the only legal value is a no-op, and that is asserted as a
        # no-op rather than dressed up as coverage -- see the docstring.
        ("[warm_start]\ntie_break = 'lowest_yx'\n", (False, False, False)),
        ("[warm_start]\ninterpolation_rule = 'nearest_valid'\n", (False, False, False)),
    ],
)
def test_every_warm_start_setting_reaches_fit_identity(tmp_path, block_body, expected):
    """Each varyable warm-start setting moves both gates and `run_hash`.

    Parametrized because one field is not evidence about a set -- the same
    reasoning as `test_a_fit_mismatch_always_forces_a_compat_mismatch`. A
    flattening that emitted four of the five correctly and dropped one would
    sail through a single-field test.

    THE EXPECTED TRIPLE IS SPELLED OUT PER CASE, NOT DERIVED. An earlier version
    of this test asserted `fit_moved == compat_moved`, which is satisfied by
    `(False, False)` -- i.e. it passed against a flattening that dropped the
    field entirely, which is the defect it was written to catch. A relation
    between two observations is not a substitute for the observations.

    `tie_break` and `interpolation_rule` are `Literal`s with one member each, so
    neither can be varied at all; their membership is pinned by the golden
    payload above, where both appear by name. Asserting they "move the hash"
    would require inventing a second rule to prove a point, so the honest
    assertion is that setting either explicitly changes nothing -- which is also
    the explicit-equals-omitted property, checked here for two more fields.

    **ALL FIVE APPEAR HERE AS OF 2026-08-24, AND FOUR DID BEFORE.**
    `interpolation_rule` was the omission, and it was covered by the golden
    payload rather than unguarded -- but this parametrization is where a reader
    checks for completeness, and a five-case argument backed by four cases is
    the shape that earns the wrong conclusion. `REQUEST_FIELDS` in
    `tests/test_hashing.py` now checks the same property over the whole class,
    so a sixth setting fails there even if nobody extends this list.
    """
    assert _moved(tmp_path, "ws.toml", _WITH + "\n" + block_body) == expected


def test_the_criterion_set_moves_compat_and_not_fit(tmp_path):
    """Adding a criterion licenses a recompute, never a refit.

    Expected value determined independently: `COMPAT_RELEVANT_FIELDS` is
    `FIT_RELEVANT_FIELDS | {"criteria"}`, and §12.8 treats a compat mismatch
    with a fit match as licence to recompute the derived arrays from stored
    primitives WITHOUT refitting. If `criteria` moved `fit_hash`, adding HQIC to
    a finished 10^7-point store would refit all of it.

    Bug this catches: collapsing the two hashes into one, which types
    identically and reads as a simplification.
    """
    assert _moved(
        tmp_path,
        "criteria.toml",
        """
        data_uri = "s3://bucket/ssh.zarr"
        variable = "sla"
        signal_terms = ["constant", "trend", "annual"]
        candidates = ["white", "white + matern12"]
        criteria = ["aic", "hqic", "bic"]
        memory_budget_gb = 1.0
        """,
    ) == (False, True, True)


def test_a_run_only_field_moves_no_gate_and_the_helper_can_still_move_one(tmp_path):
    """`threads` moves neither gate -- and the same helper does move them.

    **THE SECOND HALF IS THE POSITIVE CONTROL AND IT IS NOT OPTIONAL.** "This
    change moved nothing" is a pure negative, and a helper that silently failed
    to apply its override -- a typo in the block name, a file written to a path
    nobody reads, a `load` that returned a cached object -- produces exactly the
    same `(False, False, ...)` as the correct behaviour. Without a paired
    assertion that the identical wiring CAN move a hash, this test is
    unfalsifiable.

    Expected value determined independently: §11.3's determinism guarantee says
    thread count cannot change a fitted value. If `threads` moved `fit_hash` the
    hash boundary would be conceding that the guarantee does not hold -- the two
    are the same claim stated twice and they must not drift apart. It must still
    move `run_hash`, which is provenance and records what was actually run.

    Bug this catches: a run-only knob reaching either gate, which makes a run
    started on the 64-core node unresumable on the mini PC -- the exact
    workflow the boundary exists to permit.
    """
    assert _moved(tmp_path, "threads.toml", _WITH + "\nthreads = 8\n") == (
        False,
        False,
        True,
    )
    # The control: same helper, same file mechanics, a fit-relevant field.
    assert _moved(tmp_path, "control.toml", _WITH + "\nseed = 7\n") == (
        True,
        True,
        True,
    )


def _perturbed(field: str, annotation: object, default: object) -> str:
    """A TOML line for `field` holding a value DIFFERENT from its default.

    A different value is the whole point: `_moved` compares against a golden
    that omits the block entirely, so a field written at its default moves
    nothing and would be indistinguishable from one the payload never carried.

    **IT RAISES ON A TYPE IT DOES NOT KNOW RATHER THAN SKIPPING THE FIELD.** A
    silently skipped field is one the boundary does not cover while the suite
    still prints green -- which is (c6) reintroduced inside the repair for (c6).

    Args:
        field: The field name.
        annotation: Its declared type.
        default: Its declared default.

    Returns:
        One line of TOML.

    Raises:
        TypeError: If the type has no perturbation rule here.
    """
    if annotation is bool:
        return f"{field} = {str(not default).lower()}"
    if annotation is int:
        return f"{field} = {int(default) + 500}"  # type: ignore[call-overload]
    raise TypeError(
        f"audit field {field!r} is typed {annotation!r}, which this test does "
        f"not know how to perturb. Extend the rule -- do not skip the field, or "
        f"the boundary stops covering it and says nothing about having stopped"
    )


def test_every_audit_setting_moves_run_hash_and_neither_gate(tmp_path):
    """Re-running an audit must not invalidate the store it audits.

    THE BOUNDARY AGAINST `WarmStart`, MADE EXECUTABLE OVER **EVERY FIELD `Audit`
    DECLARES**. §11.1's argument -- a stale warm start lands at the wrong
    optimum -- is correct and, read one clause too far, sweeps in the audit
    settings as well. It must not: the audit MEASURES a store, and a subsample
    size, a stratification and a seed are properties of the measurement.

    Expected values determined independently: the field list comes from
    `Audit.model_fields`, so it is the model's own answer rather than a
    transcription, and each value is perturbed away from its declared default.

    Bug this catches: `audit.seed` -- or any field added later -- entering
    `FIT_RELEVANT_FIELDS`, or being declared in the `warm_start` block because
    it is "warm-start related". Either makes a 10^7-point store unresumable the
    first time an audit is re-run, and the run that does it looks innocent.

    **AND IT CATCHES THE SHAPE THIS TEST ITSELF HAD UNTIL 2026-08-28.** It was
    written as `subsample = 500` and `stratify = true` -- an enumeration of the
    two fields that existed then -- so `Audit.seed` was added at Phase 2c Task 6
    with the boundary silently not covering it. **A partially-installed guard
    prints a complete-looking green**, (c6), and deriving the list from the
    model is what makes the next field covered without a second edit.

    The control for this negative is `test_the_warm_start_coarse_stride_moves_fit_hash`
    immediately above: same helper, adjacent block, and it does move both gates.
    """
    fields = Audit.model_fields
    assert set(fields) >= {"subsample", "stratify", "seed"}
    block = "\n".join(
        _perturbed(name, info.annotation, info.default) for name, info in fields.items()
    )
    assert all(f"{name} =" in block for name in fields), "every field is exercised"

    assert _moved(tmp_path, "audit.toml", _WITH + "\n[audit]\n" + block + "\n") == (
        False,
        False,
        True,
    )


def test_the_candidate_set_moves_neither_gate(tmp_path):
    """Extending the candidate list is not a hash mismatch.

    Expected value determined independently: §12.8 permits resuming with a
    SUPERSET of the stored candidates, and **a hash can only express equality**,
    so `candidates` cannot be in either allowlist without forbidding the
    extension workflow outright.

    Bug this catches: "fixing" the omission by adding `candidates` to
    `FIT_RELEVANT_FIELDS`. It reads as closing a hole -- the candidate set
    genuinely IS unprotected by any hash -- and it would forbid the one
    incremental operation the store is designed for. The protection is Task 11's
    POSITIONAL comparison of the spec hashes below, not a digest.

    `run_hash` must still move: it is provenance and a run over three candidates
    is not the run over two.
    """
    assert _moved(
        tmp_path,
        "candidates.toml",
        """
        data_uri = "s3://bucket/ssh.zarr"
        variable = "sla"
        signal_terms = ["constant", "trend", "annual"]
        candidates = ["white", "white + matern12", "matern32"]
        criteria = ["aic", "hqic"]
        memory_budget_gb = 1.0
        """,
    ) == (False, False, True)


def test_the_candidate_spec_hashes_are_positional_and_order_sensitive(tmp_path):
    """Reordering the candidate list changes what Task 11 will compare.

    Expected value determined independently: the model axis is positional, so
    `stored[i] == requested[i]` is the comparison, and swapping two candidates
    is a different assignment of models to indices even though the SET is
    unchanged.

    Bug this catches: `candidate_spec_hashes` sorting or de-duplicating its
    output. Either makes the swap invisible to Task 11's gate, and a resume then
    writes candidate B's fits into candidate A's slice -- every array the right
    shape, every value finite, every status `ok`. With unequal free-parameter
    counts it also shifts every offset on the ragged `/noise/` axis, so the
    corruption lands in two arrays.
    """
    forward = config_module.load(_golden(tmp_path)).candidate_spec_hashes()
    swapped = config_module.load(
        _write(
            tmp_path,
            """
            data_uri = "s3://bucket/ssh.zarr"
            variable = "sla"
            signal_terms = ["constant", "trend", "annual"]
            candidates = ["white + matern12", "white"]
            criteria = ["aic", "hqic"]
            """,
            "swapped.toml",
        )
    ).candidate_spec_hashes()

    assert forward == tuple(reversed(swapped))
    assert forward != swapped
    assert len(set(forward)) == 2


# --------------------------------------------------------------------------
# Candidate desugaring
# --------------------------------------------------------------------------


def test_the_expression_and_list_candidate_forms_agree(tmp_path):
    """`"white + matern12"` and `["white", "matern12"]` are one specification.

    Expected value determined independently: the structured list is canonical
    and the string desugars to it, so the two must produce identical
    `spec_hash`es -- a value computed by `terms.py` from the term structure and
    not by this module.

    Bug this catches: the two forms diverging, at which point the config file
    stops being a faithful description of the run. A user who rewrites
    `"white + matern12"` as a list to add a comment would get a different
    `spec_hash`, and Task 11's positional gate would refuse a resume that is
    scientifically identical.
    """
    expression = config_module.parse_candidate("white + matern12")
    listed = config_module.parse_candidate(["white", "matern12"])
    assert expression.spec_hash() == listed.spec_hash()
    # And the sum is order-insensitive, because ProcessSpec canonicalizes.
    assert config_module.parse_candidate("matern12 + white").spec_hash() == (
        expression.spec_hash()
    )


@pytest.mark.parametrize(
    "expression",
    [
        "white(3)",
        "white.matern12",
        "white - matern12",
        "white + 3",
        "white[0]",
        "__import__('os').system('true')",
    ],
)
def test_a_candidate_expression_that_is_not_a_sum_of_names_is_refused(expression):
    """Anything but names joined by `+` is refused, naming the node type.

    Expected value determined independently: the grammar is an allowlist of two
    AST node types, so every other construct is outside it by definition.

    Bug this catches: desugaring with `eval` against a restricted namespace.
    That executes arbitrary syntax and restricts by denying builtins, which is a
    denylist -- the last case here is what a denylist has to get right and an
    allowlist never has to consider. It also catches `str.split("+")`, which
    accepts `"white - matern12"` as a single unknown kind and blames the
    registry for a syntax error.
    """
    with pytest.raises(ValueError, match="candidate"):
        config_module.parse_candidate(expression)


def test_an_unknown_term_kind_names_what_is_available():
    """A misspelled kernel is refused by the registry, listing the alternatives.

    Bug this catches: swallowing the registry's `KeyError` and re-raising
    something vaguer. The available-keys list is the fact a user needs and it
    exists only at this boundary.
    """
    with pytest.raises(KeyError) as raised:
        config_module.parse_candidate("white + matern1")
    message = str(raised.value)
    # `match="matern1"` would be satisfied by the string "matern12" appearing in
    # the available-keys list, i.e. by a message that never mentions what the
    # user actually typed. Assert the two halves separately.
    assert "unknown key 'matern1'" in message
    assert "matern12" in message and "white" in message


# --------------------------------------------------------------------------
# Refusals
# --------------------------------------------------------------------------


@pytest.mark.parametrize("key", sorted(hashing.STAMPED_IDENTITY_FIELDS))
def test_a_config_supplying_a_stamped_key_is_refused_by_name(tmp_path, key):
    """Code identity comes from the code, and the message names the file.

    Expected value determined independently: both constants describe the
    installed code, so a config value for either is a claim about code the
    config cannot see.

    Bug this catches: a user pinning `registry_version = "1"` against a registry
    that has since changed, then reusing fits computed by different kernels --
    every array the right shape, every value finite, no symptom at all. Until
    Task 1 there was no config file, so nothing had to decide where that value
    came from, and `registry_version` was supplied by every caller by hand.

    Refused in `load` as well as in `normalize` deliberately: by the time
    `normalize` sees a payload there is no filename left to point at. `normalize`
    remains the authority, since callers that never touch a file go through it.
    """
    path = _write(tmp_path, _WITH + f'\n{key} = "99"\n', "stamped.toml")
    with pytest.raises(ValueError, match=key) as raised:
        config_module.load(path)
    assert str(path) in str(raised.value)


def test_an_unrecognized_key_is_refused(tmp_path):
    """`data_url` for `data_uri` fails loudly instead of demoting the data source.

    Expected value determined independently: the allowlist is the statement
    "these fields determine theta-hat". A typo makes the real field absent and
    an unrecognized one present, and the absent half is what `hashing._subset`
    already refuses.

    THIS IS THE OTHER HALF OF A DELIBERATELY DOUBLED GUARD. `extra="forbid"`
    catches the field that is PRESENT and unrecognized; `_subset` catches the
    one that is ABSENT and required. Mutating either alone will not make this
    test bite, because the other still fires -- that is defence in depth working,
    not dead code, and `_STRICT`'s docstring says so in both directions so a
    later simplification sees both.

    Bug this catches: `extra="ignore"`, pydantic's default. The typo would then
    be silently dropped, `data_uri` would fall back to nothing, and two runs
    over different data would share a `fit_hash` and reuse each other's fits.

    THE ASSERTION IS ON THE ERROR **TYPE**, NOT ON THE MESSAGE TEXT, AND THE
    FIRST VERSION OF THIS TEST WAS WRONG ABOUT EXACTLY THAT. `pytest.raises(...,
    match="data_url")` passes under `extra="ignore"` as well, because the
    resulting error -- `data_uri` is then simply missing -- renders the offered
    input in its `input_value=` echo, and the typo appears there. Measured: the
    mutation to `extra="ignore"` left this test green. A message that quotes
    what you typed is not a message that diagnosed it.
    """
    path = _write(
        tmp_path,
        """
        data_url = "s3://bucket/ssh.zarr"
        variable = "sla"
        signal_terms = ["constant"]
        candidates = ["white"]
        criteria = ["aic"]
        """,
        "typo.toml",
    )
    with pytest.raises(ValidationError) as raised:
        config_module.load(path)
    assert any(
        error["type"] == "extra_forbidden" and error["loc"] == ("data_url",)
        for error in raised.value.errors()
    ), raised.value.errors()


def test_a_missing_required_field_is_refused(tmp_path):
    """The other half of the doubled guard, tested on its own.

    Expected value determined independently: `data_uri` has no default, because
    there is no defensible one -- and `hashing._subset` refuses a payload
    missing an allowlisted field for the same reason.

    THIS IS A SEPARATE TEST FROM THE TYPO CASE ON PURPOSE. One typo trips both
    guards at once, so a single test cannot say which fired, and mutating either
    guard alone leaves that test green. Splitting them is what makes each
    mutation bite somewhere. The corollary from the doubled-guard rule applies:
    the redundancy is deliberate, it is cross-commented in `_STRICT`, and it must
    not be simplified away on the grounds that one covers the other.
    """
    path = _write(
        tmp_path,
        """
        variable = "sla"
        signal_terms = ["constant"]
        candidates = ["white"]
        criteria = ["aic"]
        """,
        "missing.toml",
    )
    with pytest.raises(ValidationError) as raised:
        config_module.load(path)
    assert any(
        error["type"] == "missing" and error["loc"] == ("data_uri",)
        for error in raised.value.errors()
    ), raised.value.errors()


def test_an_unrecognized_suffix_names_both_accepted_forms(tmp_path):
    """A `.yaml` config is refused with what to do about it.

    Bug this catches: dispatching on content sniffing, or defaulting to TOML for
    anything unrecognized, which turns a wrong-format file into a parse error
    that blames the contents.
    """
    path = _write(tmp_path, _WITH, "config.yaml")
    with pytest.raises(ValueError, match=r"\.toml"):
        config_module.load(path)


def test_a_missing_file_is_refused_before_parsing(tmp_path):
    """A path that does not exist raises `FileNotFoundError`, not a parse error."""
    with pytest.raises(FileNotFoundError):
        config_module.load(tmp_path / "absent.toml")


# --------------------------------------------------------------------------
# Two default mechanisms, and they must agree
# --------------------------------------------------------------------------


def test_the_hashing_defaults_agree_with_the_model_defaults(tmp_path):
    """`CONFIG_DEFAULTS` and the pydantic defaults hold the same values.

    **THIS EXISTS BECAUSE THE TWO ARE NOW REDUNDANT AND THE REDUNDANCY IS
    SILENT.** `normalize` computes `{**CONFIG_DEFAULTS, **config, ...}`, so the
    config wins -- and once pydantic has filled `seed` and `objective`, the
    config ALWAYS carries them and `CONFIG_DEFAULTS` never applies to anything
    that came through `load`. If the two disagreed, the value that reaches the
    hash would be pydantic's and the constant would be dead code that reads as
    authoritative.

    `CONFIG_DEFAULTS` is not therefore removable: it still applies to callers
    that build a mapping by hand, which is every test in `test_hashing.py` and
    every future caller that has a payload but no file. So the correct response
    is to pin the agreement, not to delete either.

    Bug this catches: changing one default and not the other. The symptom would
    be that a config omitting `seed` hashes differently from one that spells out
    the documented default -- which is exactly what
    `test_comments_key_order_and_explicit_defaults_do_not_move_a_hash` promises
    cannot happen, but only for the fields it happens to name.
    """
    defaults = config_module.load(_golden(tmp_path)).to_payload(_GEOMETRY)
    for key, value in hashing.CONFIG_DEFAULTS.items():
        assert defaults[key] == value, key


def test_the_metamer_version_is_provenance_and_reaches_run_hash_alone(
    tmp_path, monkeypatch
):
    """The package version moves `run_hash` and neither gate.

    Expected value determined independently: under `hatch-vcs` the version is
    derived from the git tag, so it changes on every commit and again between an
    installed package and the uninstalled `PYTHONPATH=src` tree. A gate keyed on
    it stops resuming after any commit at all.

    Bug this catches: `metamer_version=metamer.__version__` reaching
    `FIT_RELEVANT_FIELDS` -- the reading the field's own name invites, and the
    one P0 found latent because nothing under `src/` populated it. **Task 1 is
    the commit that populates it**, so this is the first moment the defect could
    become live rather than latent.

    The version is varied by patching the attribute `to_payload` reads, which is
    the mechanism a real version change would use.
    """
    cfg = config_module.load(_golden(tmp_path))
    before = (cfg.fit_hash(_GEOMETRY), cfg.compat_hash(_GEOMETRY), cfg.run_hash())
    monkeypatch.setattr(metamer, "__version__", "99.99.99")
    after = (cfg.fit_hash(_GEOMETRY), cfg.compat_hash(_GEOMETRY), cfg.run_hash())

    assert after[0] == before[0]
    assert after[1] == before[1]
    assert after[2] != before[2]


# --------------------------------------------------------------------------
# (k): across processes, not within one
# --------------------------------------------------------------------------


_PROBE = """
import json, sys
from metamer import config
cfg = config.load(sys.argv[1])
g = "0123456789abcdef"
print(json.dumps([cfg.fit_hash(g), cfg.compat_hash(g), cfg.run_hash()]))
"""


@pytest.mark.slow
def test_the_same_file_hashes_identically_across_processes(tmp_path):
    """Three `PYTHONHASHSEED` values, one config file, identical hashes.

    **THE ONLY DEFECT CLASS AN IN-PROCESS SUITE CANNOT REACH**, and this module
    is one of the two where it has already happened once: Task 16's fence
    serialized with `json.dumps(..., default=repr)`, under which
    `{"aic", "bic", "hqic"}` renders as three different strings under three
    seeds. Every one of its six tests passed. Every resume of a finished
    10^7-point store would have refit it.

    The config layer reintroduces the exact hazard, because `criteria` and
    `candidates` are the fields a user most naturally supplies as an unordered
    collection, and pydantic will happily coerce a `set` if the annotation says
    so. Both are tuples in the model for that reason.

    Expected values determined independently: `fit_hash` and `compat_hash` are
    compared against the hand-derived constants at the top of this module, not
    against this process -- comparing the seeds only to each other would pass
    against a serializer that is stable and wrong.

    `run_hash` is compared across seeds only, and deliberately: it carries the
    VCS-derived `metamer_version`, so no constant can be pinned for it without
    being rewritten on every commit. What it must satisfy is stability at a
    fixed tree, which is what is asserted.
    """
    path = _golden(tmp_path)
    results = []
    for seed in ("1", "2", "3"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        completed = subprocess.run(
            [sys.executable, "-c", _PROBE, str(path)],
            capture_output=True,
            text=True,
            env=env,
        )
        assert completed.returncode == 0, completed.stderr
        results.append(json.loads(completed.stdout))

    assert results[0] == results[1] == results[2]
    assert results[0][0] == GOLDEN_FIT_HASH
    assert results[0][1] == GOLDEN_COMPAT_HASH


# --------------------------------------------------------------------------
# data_uri demoted, and the degraded mode it makes possible
# --------------------------------------------------------------------------


def test_the_data_uri_moves_run_hash_alone(tmp_path):
    """Moving a store to a new path does not invalidate its fits.

    **THIS IS THE WHOLE POINT OF `geometry_hash`, IN ONE ASSERTION.** `data_uri`
    was fit-relevant until 2026-08-12 and was wrong in BOTH directions: moving a
    file invalidated a resume that is scientifically valid, and editing a file in
    place at a fixed URI permitted one that is scientifically invalid. **A gate
    wrong in both directions is not a conservative approximation of the right
    gate -- it is unrelated to it.**

    Expected value determined independently: a URI is a location. The fitted
    values depend on the data's geometry and content, neither of which changes
    when a file is copied.

    It must still move `run_hash`: that is provenance, and where the data was
    read from is a fact about the run worth recording.

    Bug this catches: putting `data_uri` back, which reads as a fix -- "surely
    the data source is fit-relevant" -- and is the regression this change exists
    to prevent.
    """
    assert _moved(
        tmp_path,
        "moved.toml",
        """
        data_uri = "s3://other-bucket/ssh.zarr"
        variable = "sla"
        signal_terms = ["constant", "trend", "annual"]
        candidates = ["white", "white + matern12"]
        criteria = ["aic", "hqic"]
        memory_budget_gb = 1.0
        """,
    ) == (False, False, True)


def test_the_geometry_hash_moves_both_gates(tmp_path):
    """A different fingerprint invalidates fits and derived arrays alike.

    **THE POSITIVE CONTROL FOR THE TEST ABOVE.** "`data_uri` moves no gate" is a
    pure negative, and it is satisfied equally by a correct demotion and by a
    `fit_hash` that ignores its argument entirely. This is the same call with
    the geometry varied, and it must move.

    Expected value determined independently: `geometry_hash` is in
    `FIT_RELEVANT_FIELDS` and `COMPAT_RELEVANT_FIELDS` is a strict superset.
    """
    cfg = config_module.load(_golden(tmp_path))
    other = "fedcba9876543210"
    assert cfg.fit_hash(other) != cfg.fit_hash(_GEOMETRY)
    assert cfg.compat_hash(other) != cfg.compat_hash(_GEOMETRY)
    assert cfg.run_hash(geometry_hash=other) != cfg.run_hash(geometry_hash=_GEOMETRY)


def test_the_gates_are_none_before_stage_4a_and_run_hash_still_works(tmp_path):
    """With no input opened, both gates are None and `run_hash` is a string.

    **§13.4's DEGRADED MODE, AND IT IS A REQUIREMENT RATHER THAN A CONVENIENCE.**
    `--explain`'s most valuable use is a config with no data staged yet -- sizing
    a run before moving 25 GB -- so an unreachable input must print compat- and
    run-relevant content and say `fit_hash: not computed (requires stage 4a)`.

    Expected value determined independently: `geometry_hash` is read from an
    input, so with no input there is no value; and `run_hash` is provenance over
    the config, which exists either way.

    Bug this catches: `run_payload` validating the full `FIT_RELEVANT_FIELDS`.
    It did -- that check exists so a config that cannot be fit-hashed is not
    called a run -- and once `geometry_hash` joined the allowlist it turned
    §13.4's degraded mode into a `KeyError`. Measured: every run-hash test in
    this module failed the moment the allowlist changed. `STAGE_4A_FIELDS` is
    the exclusion, and it is an exclusion of "not supplied by a config" rather
    than a loosening of "must be specified".

    The optional return type was declared at Task 1, two tasks before it could
    happen, so no caller had to be revisited when it started happening.
    """
    cfg = config_module.load(_golden(tmp_path))
    assert cfg.fit_hash() is None
    assert cfg.compat_hash() is None
    assert isinstance(cfg.run_hash(), str)
    assert len(cfg.run_hash()) == 16


def test_an_omitted_budget_is_the_unset_sentinel_and_has_no_run_identity(tmp_path):
    """A config naming no budget reads back None, and cannot be run-hashed.

    **THE FIELD MUST BE ABLE TO EXPRESS ITS OWN ABSENCE.**
    `Field(default=1.0)` makes a config that omits the field byte-identical to
    one that specifies 1.0, so "accepted the default" and "chose 1 GB" are the
    same observation and a defaulting rule has nothing to fire on. That is
    pre-flight (a0) at a config field, and it resolves the way every fill value
    in the store does: **the sentinel is a value the writer cannot produce** --
    `gt=0.0` refuses every number a config could name, so `None` is unforgeable.

    Expected values determined independently: `memory_budget_gb` is in neither
    `FIT_RELEVANT_FIELDS` nor `COMPAT_RELEVANT_FIELDS`, which
    `tests/test_hashing.py` asserts directly, so an unresolved config must still
    produce **both goldens at the top of this module unchanged**. Refusing them
    here would assert a dependence the allowlists deny -- the same error Task 0
    avoided when it dropped `placement` and `d` from `resident_bytes_per_series`.

    Bug this catches: the `None` reaching the payload, where it hashes as JSON
    `null` and gives a defaulted run a `run_hash` no resolved run can reproduce.
    **Nothing downstream would notice**, because `run_hash` gates nothing; the
    only symptom is provenance describing a run that did not happen.
    """
    unset = config_module.load(_write(tmp_path, _UNSET_BUDGET_TOML, "unset.toml"))

    assert unset.memory_budget_gb is None
    assert "memory_budget_gb" not in unset.to_payload(_GEOMETRY)
    assert unset.fit_hash(_GEOMETRY) == GOLDEN_FIT_HASH
    assert unset.compat_hash(_GEOMETRY) == GOLDEN_COMPAT_HASH
    with pytest.raises(ValueError, match="resolved at run"):
        unset.run_hash()

    # THE POSITIVE CONTROL (i2). A refusal is an absence of a result, and an
    # absence is produced equally well by the sentinel being caught and by
    # `run_hash` being unreachable from this fixture at all. The same call on
    # the same config with the field named returns a hash.
    named = config_module.load(_golden(tmp_path))
    assert named.to_payload(_GEOMETRY)["memory_budget_gb"] == 1.0
    assert len(named.run_hash()) == 16


def test_a_config_cannot_supply_the_geometry_hash(tmp_path):
    """The fingerprint comes from the data, and a config cannot claim it.

    Expected value determined independently: it is an IDENTITY -- what the input
    actually is -- so it must be populated by reading that input. A
    config-supplied value would be self-reported identity, which is the exact
    defect `data_uri` embodied and the reason it was replaced.

    Bug this catches: adding `geometry_hash` to the pydantic model as a
    convenience -- "so a user can pin it" -- which would restore the hole under
    a new name and pass every other test in this module.
    """
    path = _write(
        tmp_path, _WITH + '\ngeometry_hash = "0123456789abcdef"\n', "geo.toml"
    )
    with pytest.raises(ValidationError) as raised:
        config_module.load(path)
    assert any(
        error["type"] == "extra_forbidden" and error["loc"] == ("geometry_hash",)
        for error in raised.value.errors()
    ), raised.value.errors()
