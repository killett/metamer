"""Validation staging: which layer refused, and which exit code that becomes.

The staging exists so that "your config is invalid" before a ten-hour job says
**which layer and why**. Two claims are being established and they are easy to
conflate: that each fault is attributed to the right layer, and that the layer
maps to the right process exit code. The second is a process property and is
tested through a subprocess in `tests/test_runner.py`; this module tests the
attribution, which is a pure function of the exception.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from metamer.batch.input import InputContractError
from metamer.batch.validation import (
    ExitCode,
    ValidationError,
    ValidationLayer,
    check_semantics,
    check_thread_limits,
    exit_code_for,
    identifiability_warnings,
    layer_of,
    load_config,
)
from metamer.core.lint import Rule
from metamer.core.memory import Backend, resident_bytes_per_series, tile_side

_GOOD = """
data_uri = "x.zarr"
variable = "sla"
signal_terms = ["constant", "trend", "annual"]
candidates = ["white", "white + matern12"]
criteria = ["aic", "hqic"]
"""


def _write(tmp_path: Path, body: str, name: str = "c.toml") -> Path:
    path = tmp_path / name
    path.write_text(textwrap.dedent(body))
    return path


# --------------------------------------------------------------------------
# The taxonomy itself
# --------------------------------------------------------------------------


def test_the_five_exit_codes_are_the_five_the_taxonomy_names():
    """Every `ExitCode` member, enumerated by name against its declared value.

    Expected values come from the Phase 2 brainstorm's Q1, not from the code:
    0 clean, 1 completed with failures above threshold, 2 aborted early, 3
    config/validation layers 1-3, 4 data-dependent layer 4.

    Bug this catches: a member renumbered, added or dropped. The numbers are a
    published interface -- a shell script branching on them cannot be updated
    by a later commit -- so the enum is pinned member by member.

    **Enumerated, never counted.** An asserted count passes against a member
    swapped for another of the same arity, which is the mistake this project
    has already paid for twice.
    """
    assert ExitCode.OK.value == 0
    assert ExitCode.COMPLETED_WITH_FAILURES.value == 1
    assert ExitCode.ABORTED_EARLY.value == 2
    assert ExitCode.CONFIG_INVALID.value == 3
    assert ExitCode.DATA_INVALID.value == 4
    assert [member.name for member in ExitCode] == [
        "OK",
        "COMPLETED_WITH_FAILURES",
        "ABORTED_EARLY",
        "CONFIG_INVALID",
        "DATA_INVALID",
    ]


def test_the_four_validation_layers_are_numbered_as_the_design_doc_numbers_them():
    """`ValidationLayer` members against design doc section 13.2's numbering.

    Bug this catches: the layer numbers drifting from the document that a user
    reads to interpret them. A message saying "layer 3" is useless if the
    document's layer 3 is this code's layer 2.
    """
    assert ValidationLayer.FILE.value == 1
    assert ValidationLayer.SCHEMA.value == 2
    assert ValidationLayer.SEMANTIC.value == 3
    assert ValidationLayer.DATA.value == 4
    assert [member.name for member in ValidationLayer] == [
        "FILE",
        "SCHEMA",
        "SEMANTIC",
        "DATA",
    ]


@pytest.mark.parametrize(
    ("layer", "expected"),
    [
        (ValidationLayer.FILE, ExitCode.CONFIG_INVALID),
        (ValidationLayer.SCHEMA, ExitCode.CONFIG_INVALID),
        (ValidationLayer.SEMANTIC, ExitCode.CONFIG_INVALID),
        (ValidationLayer.DATA, ExitCode.DATA_INVALID),
    ],
)
def test_layers_one_to_three_are_one_exit_code_and_layer_four_is_another(
    layer, expected
):
    """The 3-versus-4 split, stated per layer rather than as a relation.

    Expected values are the taxonomy's, not the implementation's: layers 1-3
    are all "your config is wrong" and layer 4 is "your data is wrong", and the
    whole reason validation is staged is that those send a user to different
    places.

    Bug this catches: layer 4 folded into exit code 3, which is the collapse
    that makes the staging decorative. A single assertion that the two differ
    would pass with both wrong in the same direction, so each layer names its
    own expected code.
    """
    assert exit_code_for(ValidationError(layer, "constructed")) == expected


def test_the_staged_types_are_enumerated_and_an_unstaged_error_is_refused():
    """`layer_of` accepts exactly the two staged types and refuses the rest.

    `InputContractError` is Task 2's staged layer-4 type and exit code 4 rests
    on it: a helper that raises a bare `ValueError` at the stage boundary
    produces an unhandled error rather than exit code 4, which is why
    `check_contract` wraps `timeaxis`'s `ValueError`.

    Bug this catches: a mapping written as "anything that is not a
    `ValidationError` is a data error", which would file an internal `KeyError`
    -- an unknown candidate kind is one -- as "your data is wrong" and send the
    user to inspect a perfectly good input.
    """
    assert layer_of(ValidationError(ValidationLayer.SEMANTIC, "x")) is (
        ValidationLayer.SEMANTIC
    )
    assert layer_of(InputContractError("x")) is ValidationLayer.DATA
    with pytest.raises(TypeError, match="not a staged validation failure"):
        layer_of(KeyError("kernel_registry: unknown key 'nosuchkind'"))


def test_a_validation_error_names_its_own_layer_in_its_message():
    """The rendered message carries the layer number and the layer's name.

    Bug this catches: the layer being carried as an attribute nobody prints.
    "Your config is invalid" before a ten-hour job is not actionable; design
    doc section 13.2 requires each stage to name itself *in its error*, and an
    attribute that only a debugger sees does not satisfy that.
    """
    rendered = str(ValidationError(ValidationLayer.SEMANTIC, "screening is refused"))
    assert "layer 3" in rendered
    assert "semantic" in rendered
    assert "screening is refused" in rendered


# --------------------------------------------------------------------------
# Layers 1 and 2: the file, and the schema
# --------------------------------------------------------------------------


def test_a_missing_file_is_layer_1(tmp_path):
    """A config path that does not exist is a file-layer failure.

    Bug this catches: `FileNotFoundError` escaping unstaged, which Python
    reports as exit code 1 -- "completed with failures above threshold" in this
    taxonomy, i.e. a run that finished badly rather than one that never
    started.
    """
    with pytest.raises(ValidationError) as caught:
        load_config(tmp_path / "absent.toml")
    assert caught.value.layer is ValidationLayer.FILE


@pytest.mark.parametrize(
    ("name", "body"),
    [
        ("c.yaml", "data_uri: x\n"),
        ("c.toml", "this is not = = toml\n"),
        ("c.json", "{not json,}\n"),
    ],
    ids=["unrecognized-suffix", "bad-toml", "bad-json"],
)
def test_a_file_that_does_not_parse_is_layer_1(tmp_path, name, body):
    """Suffix and parse failures are the file layer, enumerated one per case.

    Bug this catches: a parse failure reported as a schema failure. The user's
    next action differs -- a TOML syntax error is fixed in an editor, a schema
    error is fixed against the field table -- so the layers are not
    interchangeable even though both exit 3.
    """
    with pytest.raises(ValidationError) as caught:
        load_config(_write(tmp_path, body, name))
    assert caught.value.layer is ValidationLayer.FILE


def test_an_unrecognized_key_is_layer_2_and_pydantic_diagnosed_it(tmp_path):
    """A misspelled field is a schema failure, and the diagnosis is asserted.

    Bug this catches: `extra="ignore"`, under which the typo is dropped, the
    real field is then simply missing, and pydantic echoes the offered mapping
    in `input_value=` -- so the typo appears in the message of an error that
    never saw it. **A message that quotes what you typed is not a message that
    diagnosed it.** The assertion therefore reads the structured error rather
    than matching the user's own string.

    Bug this ALSO catches, and it is the one that fired: a layer-1 `except
    ValueError` clause placed above the schema clause. `pydantic.ValidationError
    subclasses ValueError`, so that ordering swallows every schema failure and
    reports "layer 1 (file)" for a file that parsed perfectly. Measured during
    implementation, on this test.

    Both of pydantic's errors are asserted, in order, because a single typo
    trips both guards -- the field is unrecognized AND the real one is then
    missing -- and asserting only one would pass against a model that had lost
    the other.
    """
    body = _GOOD.replace("data_uri", "data_url")
    with pytest.raises(ValidationError) as caught:
        load_config(_write(tmp_path, body))
    assert caught.value.layer is ValidationLayer.SCHEMA
    causes = caught.value.__cause__.errors()  # type: ignore[union-attr]
    assert [(error["type"], error["loc"]) for error in causes] == [
        ("missing", ("data_uri",)),
        ("extra_forbidden", ("data_url",)),
    ]


def test_a_supplied_stamped_key_is_layer_2_and_not_layer_1(tmp_path):
    """`algorithm_version` in a config is a schema failure, not a parse failure.

    Both `load`'s stamped-key refusal and its parse failures were bare
    `ValueError` before this task, so a runner had no way to tell them apart
    and would have named the wrong layer for one of them. The pre-check exists
    only to give a better message than `extra_forbidden` would; the fault it
    describes is the same kind of fault, so it is layer 2.

    Bug this catches: classifying by exception type alone, which files this as
    layer 1 -- "your file does not parse" for a file that parses perfectly.
    """
    body = _GOOD + '\nalgorithm_version = "1"\n'
    with pytest.raises(ValidationError) as caught:
        load_config(_write(tmp_path, body))
    assert caught.value.layer is ValidationLayer.SCHEMA
    assert "algorithm_version" in str(caught.value)


def test_a_valid_config_loads_and_is_the_control_for_every_refusal_above(tmp_path):
    """`load_config` returns a `Config` for a config with nothing wrong with it.

    **The positive control.** Every test above asserts a refusal, and a
    `load_config` that refused everything -- or that refused on the first
    branch it evaluated -- would satisfy all of them. This is the half that can
    fail if the staging is over-eager.

    Bug this catches: a layer-2 check that fires on a default-filled field, so
    that no config is loadable at all.
    """
    config = load_config(_write(tmp_path, _GOOD))
    assert config.variable == "sla"
    assert config.candidates == ("white", "white + matern12")


# --------------------------------------------------------------------------
# The thread-limit check: Task 5 observes, this task attributes
# --------------------------------------------------------------------------


def test_a_thread_limit_that_was_not_honoured_is_a_layer_3_failure():
    """An observed limit differing from the requested one raises at layer 3.

    Design doc section 11.1's determinism precondition is **observed**, not
    requested: `OMP_NUM_THREADS=1` records a request, and whether it took
    effect depends on import ordering that nothing enforces -- set after numpy
    is imported it does nothing, silently. So a precondition that holds for
    OpenBLAS while MKL runs multithreaded is not a precondition that holds.

    Bug this catches: the observation being recorded into provenance and then
    ignored, which is the shape that satisfies exit criterion 10 with something
    that is not a layer-3 failure. The message must name the library, because
    "threads mismatch" does not say which one to go and fix.
    """
    with pytest.raises(ValidationError) as caught:
        check_thread_limits(1, {"openblas": 1, "mkl": 4, "omp": 1})
    assert caught.value.layer is ValidationLayer.SEMANTIC
    assert "mkl" in str(caught.value)
    assert "openblas" not in str(caught.value)


def test_a_thread_limit_table_that_matches_raises_nothing():
    """The control for the negative above: a matching table is accepted.

    Bug this catches: a check that raises whenever it is given any table at
    all, which would pass the refusal test above while making every run fail.
    """
    check_thread_limits(4, {"openblas": 4, "mkl": 4})


def test_an_absent_observation_skips_the_check_and_that_is_a_stated_limit():
    """`None` means "nothing observed yet", and the check does nothing.

    **This vacuity is deliberate and is recorded rather than believed.** Task 5
    is what supplies the observation through `threadpoolctl`; until it lands,
    the production runner passes `None` and this check cannot fire. Pinning it
    means the state is visible in the suite instead of being a belief about
    what the runner does.

    Bug this catches: a `None` table compared elementwise against the request,
    which would raise on every run in a tree where Task 5 has not landed.
    """
    check_thread_limits(4, None)


# --------------------------------------------------------------------------
# Layer 3: cross-field and environment sense, on no data
# --------------------------------------------------------------------------


def test_a_clean_config_passes_layer_3(tmp_path):
    """The positive control for every layer-3 refusal below.

    Every other layer-3 test asserts that something is refused, and a
    `check_semantics` whose first line raised unconditionally would satisfy all
    of them. This is the half that can fail if a check is over-eager -- and
    `_GOOD` deliberately carries two DIFFERENT candidates, three signal terms
    and two criteria, so it exercises the duplicate, prefix and membership
    scans rather than short-circuiting on an empty sequence.
    """
    check_semantics(load_config(_write(tmp_path, _GOOD)))


def test_screening_is_refused_naming_the_engine_that_would_lift_it(tmp_path):
    """A config enabling screening is refused at layer 3, naming the engine.

    Bug this catches: a refusal that says "not implemented". **A refusal that
    says what would lift it is planning information and one that does not is a
    wall** -- and the message is the only place the user learns that screening
    is waiting on the debiased Whittle engine rather than on a flag.

    The `[screening]` block validates at layer 2 precisely so this refusal can
    be specific; an unknown-key error would say nothing about what is missing.
    """
    body = _GOOD + "\n[screening]\nenabled = true\nkeep = 2\n"
    with pytest.raises(ValidationError) as caught:
        check_semantics(load_config(_write(tmp_path, body)))
    assert caught.value.layer is ValidationLayer.SEMANTIC
    assert "debiased Whittle engine" in str(caught.value)
    assert "Phase 4" in str(caught.value)


def test_a_per_point_regressor_is_refused_naming_the_field_and_both_tile_sides(
    tmp_path,
):
    """The per-point refusal names the declaration and both tile sizes.

    **The regime is declared even though the feature is deferred**, because a
    mechanism that can only be right in one regime is not right -- it is
    untested in the other. One declaration moves `tile_side` from 338 to 186 at
    design doc section 9.4's worked example, a 3.3x change in tile area, and
    against a hard 16 GB constraint that is the difference between a
    configuration fitting in RAM and not.

    Bug this catches: a refusal reading "per-point regressors are not
    implemented", which wastes the context layer 3 already has. The expected
    tile sides are recomputed here from `memory` at the same worked example --
    an independent evaluation of the same public functions, so a message that
    quoted stale constants would fail even while the formula moved.
    """
    body = _GOOD.replace(
        '["constant", "trend", "annual"]',
        '["constant", "trend", "regressor_field:gia"]',
    )
    with pytest.raises(ValidationError) as caught:
        check_semantics(load_config(_write(tmp_path, body)))

    expected = [
        tile_side(
            10**9,
            resident_bytes_per_series(
                Backend.NUMPY_BATCHED, 3, 4, 4, 630, 12, per_point_design=per_point
            ),
        )
        for per_point in (False, True)
    ]
    assert expected == [338, 186]  # the published pair, recomputed 2026-08-12
    message = str(caught.value)
    assert caught.value.layer is ValidationLayer.SEMANTIC
    assert "gia" in message
    assert str(expected[0]) in message
    assert str(expected[1]) in message
    assert Backend.NUMPY_BATCHED.value in message


def test_the_quoted_tile_sides_are_backend_specific_and_the_message_says_which(
    tmp_path,
):
    """Path A and path B do not give the same tile sizes, nor the same ratio.

    Expected values recomputed 2026-08-12 from `memory`, independently of the
    refusal: `NUMPY_BATCHED` gives 338 / 186 and a 3.30x change in tile area;
    `COMPILED` gives 361 / 189 and 3.65x. Design doc section 13.4, the Phase 2a
    plan and PROGRESS all quote the first pair **without naming a backend**,
    and the spike adopted path B.

    Bug this catches: a message quoting a tile size with no backend attached --
    the same shape of claim as a benchmark ratio quoted without its harness,
    which this project has already paid for. The two pairs differ, so a user
    planning a per-point run against the wrong one is off by 4%% in tile side
    and 10%% in area.
    """
    sides = {
        backend: [
            tile_side(
                10**9,
                resident_bytes_per_series(
                    backend, 3, 4, 4, 630, 12, per_point_design=per_point
                ),
            )
            for per_point in (False, True)
        ]
        for backend in Backend
    }
    assert sides[Backend.NUMPY_BATCHED] == [338, 186]
    assert sides[Backend.COMPILED] == [361, 189]

    body = _GOOD.replace('"annual"', '"regressor_field:gia"')
    with pytest.raises(ValidationError) as caught:
        check_semantics(load_config(_write(tmp_path, body)))
    message = str(caught.value)
    assert Backend.NUMPY_BATCHED.value in message
    assert str(sides[Backend.COMPILED][0]) not in message


def test_two_candidates_that_are_the_same_model_are_refused_by_spec_hash(tmp_path):
    """A duplicate candidate is refused, naming both indices and the hash.

    The two spellings below are the same model: `parse_candidate` accepts a sum
    expression and a term list, and both desugar to the same `ProcessSpec`. So
    a string comparison of the config entries would call them different and let
    the duplicate through.

    Bug this catches: exactly that -- comparing `config.candidates` rather than
    their spec hashes. A duplicate is a wasted slice of every stored array on a
    positional model axis, and nothing downstream would report it: every array
    is the right shape, every value finite, and the two slices simply agree.
    """
    body = _GOOD.replace(
        '["white", "white + matern12"]',
        '["white + matern12", ["white", "matern12"]]',
    )
    with pytest.raises(ValidationError) as caught:
        check_semantics(load_config(_write(tmp_path, body)))
    assert caught.value.layer is ValidationLayer.SEMANTIC
    message = str(caught.value)
    assert "candidates 0" in message
    assert "and 1" in message


def test_two_candidates_that_merely_look_alike_are_not_refused(tmp_path):
    """The control: `white` and `white + white` are different models.

    Bug this catches: a duplicate check keyed on anything coarser than the spec
    hash -- the kind set, say, or the first term -- which would refuse a
    legitimate candidate set. `white + white` has two nugget scales and its own
    `spec_hash`; it lints as degenerate, which is a warning and not a refusal.
    """
    body = _GOOD.replace('["white", "white + matern12"]', '["white", "white + white"]')
    check_semantics(load_config(_write(tmp_path, body)))


@pytest.mark.parametrize(
    ("candidates", "expected_fragment"),
    [
        ('["nosuchkind"]', "nosuchkind"),
        ('["white - matern12"]', "BinOp"),
    ],
    ids=["unknown-kind-raises-KeyError", "malformed-expression-raises-ValueError"],
)
def test_an_unresolvable_candidate_is_a_layer_3_failure(
    tmp_path, candidates, expected_fragment
):
    """Both candidate failure types are staged, and they are different types.

    **`load` DOES NOT PARSE CANDIDATES**; `parse_candidate` runs only when
    `candidate_spec_hashes()` is called, so both faults arrive at layer 3 rather
    than at layer 2. Measured: an unknown kernel kind comes out of the registry
    as a **`KeyError`** and a malformed expression as a `ValueError`.

    Bug this catches: a layer-3 pass catching `ValueError` alone. The `KeyError`
    then escapes unstaged, and Python reports an unhandled exception as **exit
    code 1** -- "completed with failures above threshold" in this taxonomy, i.e.
    a run that finished badly rather than one that never started.
    """
    body = _GOOD.replace('["white", "white + matern12"]', candidates)
    with pytest.raises(ValidationError) as caught:
        check_semantics(load_config(_write(tmp_path, body)))
    assert caught.value.layer is ValidationLayer.SEMANTIC
    assert expected_fragment in str(caught.value)


def test_a_criterion_no_implementation_can_compute_is_refused(tmp_path):
    """An unknown criterion is refused at layer 3, naming the computable set.

    **It passes layers 1 and 2 today**: `Config.criteria` is `tuple[str, ...]`
    with no membership constraint, so without this check the fault surfaces at
    ranking time -- inside the tile loop, ten hours in.

    Bug this catches: leaving the membership question to `ic_value`'s own
    `ValueError`, which fires per tile rather than per run. The message names
    the implemented set because that is what the user needs to edit the config,
    and design doc section 13.2 places this at layer 3 rather than in the
    schema so that it can also speak about the objective.
    """
    body = _GOOD.replace('["aic", "hqic"]', '["aic", "not_a_criterion"]')
    with pytest.raises(ValidationError) as caught:
        check_semantics(load_config(_write(tmp_path, body)))
    assert caught.value.layer is ValidationLayer.SEMANTIC
    message = str(caught.value)
    assert "not_a_criterion" in message
    assert "bic_neff" in message


def test_every_implemented_criterion_is_accepted_under_both_objectives(tmp_path):
    """The control: all five criteria pass, under ML and under REML.

    Bug this catches: a membership check written against a subset -- the three
    a fixture happens to use -- which would refuse `aicc` or `bic_neff` on a
    perfectly valid config. Both objectives are exercised because the design
    doc's row is "criterion/objective compatibility", and asserting only ML
    would hide a check that rejected everything under REML.
    """
    every = '["aic", "aicc", "bic", "bic_neff", "hqic"]'
    for objective in ("ml", "reml"):
        body = (
            _GOOD.replace('["aic", "hqic"]', every) + f'\nobjective = "{objective}"\n'
        )
        check_semantics(load_config(_write(tmp_path, body, f"{objective}.toml")))


def test_a_thread_limit_mismatch_reaches_layer_3_through_check_semantics(tmp_path):
    """The observed-limits check is WIRED, not merely available.

    Task 5 exposes the observation; this task is what makes it a layer-3
    failure. Without the wiring it ships as a bare exception with no layer
    attached, **which would satisfy exit criterion 10 with something that is not
    a layer-3 failure**.

    Bug this catches: `check_thread_limits` existing and never being called.
    Testing the function directly (above) cannot see that, because a function
    nobody calls passes its own unit test perfectly.
    """
    config = load_config(_write(tmp_path, _GOOD))
    with pytest.raises(ValidationError) as caught:
        check_semantics(config, observed_thread_limits={"openblas": 8})
    assert caught.value.layer is ValidationLayer.SEMANTIC
    assert "openblas" in str(caught.value)


# --------------------------------------------------------------------------
# The identifiability lint: a warning, and it needs data
# --------------------------------------------------------------------------


def test_a_degenerate_candidate_produces_a_warning_and_not_a_refusal(tmp_path):
    """`white + white` lints as degenerate, and the lint never blocks.

    Two free nugget scales are constrained only as a sum, so the composite is
    structurally non-identifiable -- design doc section 4.8's `white + white`,
    named there because a rule keyed on `rho` cannot see it.

    Bug this catches: the lint promoted to a refusal. **Warn, do not block**: a
    user who knowingly wants that model can still fit it, and the a-posteriori
    half reports the same phenomenon after the fact as `DEGENERATE_HESSIAN`.
    That `check_semantics` accepts the same config is the other half of the
    claim and is asserted here rather than assumed.
    """
    body = _GOOD.replace('["white", "white + matern12"]', '["white + white"]')
    config = load_config(_write(tmp_path, body))
    check_semantics(config)
    findings = identifiability_warnings(config, sampling_interval=1 / 12)
    assert [finding.rule for finding in findings] == [Rule.NUGGET_COLLAPSE]


def test_a_clean_candidate_set_lints_clean(tmp_path):
    """The control: the good config's candidates produce no findings.

    Bug this catches: a lint wired to return every rule for every spec, which
    would make the warning channel noise and satisfy the test above for the
    wrong reason.
    """
    config = load_config(_write(tmp_path, _GOOD))
    assert identifiability_warnings(config, sampling_interval=1 / 12) == ()


def test_an_unusable_sampling_interval_is_layer_4_and_not_layer_3(tmp_path):
    """A non-positive sampling interval is a fact about the DATA.

    `lint` raises rather than returning an empty list, deliberately: comparing
    every timescale against a limit of zero returns "clean", and a diagnostic
    that reports clean because it could not run is worse than one that stops.

    Bug this catches: attributing that raise to layer 3. The interval comes from
    the time axis, so an unusable one means the axis is unusable -- the user
    must look at the data, not at the config, and the exit code is what tells
    them which.
    """
    config = load_config(_write(tmp_path, _GOOD))
    with pytest.raises(ValidationError) as caught:
        identifiability_warnings(config, sampling_interval=0.0)
    assert caught.value.layer is ValidationLayer.DATA
    assert exit_code_for(caught.value) == ExitCode.DATA_INVALID
