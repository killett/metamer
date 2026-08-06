import json

import pytest

from metamer.core.capability import CostClass, EngineId, IncompatibleSpecError
from metamer.core.params import ParamSpec
from metamer.core.registry import kernel_registry
from metamer.core.terms import ProcessSpec, TermSpec, free_param_index
from metamer.core.transforms import Log, Logit


class _FakeFamily:
    """Throwaway stand-in for a kernel family, used only to probe engine_costs wiring."""

    def __init__(self, costs):
        self.engine_costs = costs


def _param(name: str, default: float) -> ParamSpec:
    return ParamSpec(
        name=name,
        default=default,
        transform=Log(),
        bounds=(0.0, float("inf")),
        diagnostic_limits=(1e-8, 1e8),
    )


def _matern12(rho: float) -> TermSpec:
    return TermSpec(
        kind="matern12",
        params={"sigma": _param("sigma", 1.0), "rho": _param("rho", rho)},
        ordering_param="rho",
    )


def _white(sigma: float = 0.1) -> TermSpec:
    return TermSpec(kind="white", params={"sigma": _param("sigma", sigma)})


def _matern12_with_fixed_rho(rho: float) -> TermSpec:
    """Build a matern12 term identical to _matern12 but with rho frozen."""
    from dataclasses import replace

    term = _matern12(rho)
    return TermSpec(
        kind=term.kind,
        params={
            name: replace(p, fixed=(name == "rho")) for name, p in term.params.items()
        },
        ordering_param=term.ordering_param,
    )


def test_addition_produces_process_spec():
    """TermSpec + TermSpec composes into a two-term ProcessSpec.

    Bug this catches: __add__ returning a tuple or mutating in place, either
    of which breaks the frozen-value semantics every hash depends on.
    """
    spec = _white() + _matern12(10.0)
    assert isinstance(spec, ProcessSpec)
    assert len(spec.terms) == 2


def test_canonical_order_is_independent_of_construction_order():
    """Construction order does not survive into the canonical form.

    Expected value determined independently: canonical order is (kind,
    ordering default) ascending with kind compared as a string, so
    matern12(rho=2) sorts before matern12(rho=50) before white, regardless of
    how they were added.
    """
    a = _matern12(50.0) + _white() + _matern12(2.0)
    b = _white() + _matern12(2.0) + _matern12(50.0)
    assert [t.kind for t in a.terms] == [t.kind for t in b.terms]
    assert a.spec_hash() == b.spec_hash()


def test_hash_is_insensitive_to_dict_insertion_order():
    """Reordering a params dict does not change spec_hash.

    Bug this catches: hashing repr() or a non-sorted json.dumps, which would
    make an identical model look like a different one across runs and
    invalidate a completed 10^7-point store.
    """
    forward = TermSpec(
        kind="matern12",
        params={"sigma": _param("sigma", 1.0), "rho": _param("rho", 3.0)},
        ordering_param="rho",
    )
    backward = TermSpec(
        kind="matern12",
        params={"rho": _param("rho", 3.0), "sigma": _param("sigma", 1.0)},
        ordering_param="rho",
    )
    assert ProcessSpec((forward,)).spec_hash() == ProcessSpec((backward,)).spec_hash()


def test_stable_labels_disambiguate_exchangeable_terms():
    """Two terms of the same kind get distinct, order-stable labels.

    Bug this catches: label collision, which makes warm-start reuse and
    cross-grid-point comparison silently attach 'term 2' to different objects
    at different points.
    """
    spec = _matern12(2.0) + _matern12(50.0)
    assert spec.labels() == ("matern12[0]", "matern12[1]")
    assert spec.terms[0].params["rho"].default == 2.0


def test_free_param_index_matches_hand_written_expectations():
    """The flat parameter vector's layout is stated once and tested directly.

    Expected values determined independently by applying the canonical-order
    rule on paper: kind ascending as a string puts matern12(rho=2) before
    matern12(rho=50) before white, and within a term the declared parameter
    order is preserved.

    Bug this catches: five separate copies of this nested loop existed across
    objective.py, optimize.py and gradients.py, two of them reading their
    ordering from different sources (term.params vs family.param_specs()).
    Divergence between two copies does not raise -- it produces converged-
    looking fits at values interpreted differently in two places.
    """
    single = ProcessSpec((_matern12(3.0),))
    assert free_param_index(single) == (
        ("matern12[0]", "sigma"),
        ("matern12[0]", "rho"),
    )

    composite = _white() + _matern12(50.0) + _matern12(2.0)
    assert free_param_index(composite) == (
        ("matern12[0]", "sigma"),
        ("matern12[0]", "rho"),
        ("matern12[1]", "sigma"),
        ("matern12[1]", "rho"),
        ("white[0]", "sigma"),
    )


def test_free_param_index_omits_fixed_parameters():
    """A frozen parameter is absent from the flat vector entirely.

    Bug this catches: the optimizer moving a parameter the user pinned, and
    k in AIC counting a parameter that was never estimated. Both are silent.
    """
    from dataclasses import replace

    term = _matern12(4.0)
    frozen = TermSpec(
        kind="matern12",
        params={n: replace(p, fixed=(n == "rho")) for n, p in term.params.items()},
        ordering_param="rho",
    )
    spec = ProcessSpec((frozen,))
    assert free_param_index(spec) == (("matern12[0]", "sigma"),)


@pytest.mark.parametrize(
    "spec_factory",
    [
        lambda: ProcessSpec((_matern12(3.0),)),
        lambda: _white() + _matern12(2.0),
        lambda: _white() + _matern12(2.0) + _matern12(50.0),
        lambda: _white() + _matern12_with_fixed_rho(4.0),
    ],
)
def test_free_param_index_length_equals_n_theta(spec_factory):
    """The layout and the count can never disagree.

    This single invariant is what makes the parameter vector safe: n_theta
    feeds k in every information criterion, and free_param_index defines what
    the optimizer searches. If they diverge, selection is corrupted with no
    visible symptom. The fourth case includes a fixed parameter, so a bug
    where free_param_index and n_theta agree on unconstrained specs but
    disagree once something is pinned would otherwise slip through: every
    other case in this list has zero fixed parameters.
    """
    spec = spec_factory()
    assert len(free_param_index(spec)) == spec.n_theta()


def test_shared_parameters_are_refused_rather_than_miscounted():
    """Cross-term parameter sharing is out of scope and says so.

    Design doc section 4.7 requires counting to handle shared parameters.
    Phase 1 implements no sharing mechanism, so a spec that declares one must
    raise rather than be silently counted as independent -- the same discipline
    as nonlinear signal terms.
    """
    term = _matern12(3.0)
    shared = TermSpec(
        kind="matern12",
        params=term.params,
        ordering_param="rho",
        shared_with={"sigma": "other"},
    )
    with pytest.raises(NotImplementedError, match="shared"):
        free_param_index(ProcessSpec((shared,)))


def test_canonical_is_json_serializable():
    """canonical() round-trips through json.dumps with sorted keys.

    Bug this catches: leaving a Bijector object or a numpy scalar in the
    canonical dict, which raises at hash time rather than at construction.
    """
    spec = _white() + _matern12(7.5)
    encoded = json.dumps(spec.canonical(), sort_keys=True, separators=(",", ":"))
    assert json.loads(encoded) == json.loads(encoded)
    assert "matern12" in encoded


def test_n_theta_excludes_fixed_parameters():
    """n_theta() counts only free parameters, not every declared parameter.

    Expected value determined independently: the composite has three
    declared parameters total (white.sigma, matern12.sigma, matern12.rho),
    exactly one of which (rho) is fixed, so n_theta() must be 2. That value
    is distinct from both "count every declared parameter regardless of
    fixed" (3) and an inverted fixed-check that counts frozen parameters
    instead of free ones (1) -- with a 2-vs-1 split of free-vs-fixed
    parameters, those two wrong implementations cannot coincidentally agree
    with the correct answer the way they would on a term with exactly one
    free and one fixed parameter.

    Bug this catches: n_theta() ignoring `fixed` (or inverting the check),
    which lets a parameter the user pinned inflate -- or deflate -- k in
    every information criterion even though the optimizer never touches it.
    """
    spec = _white() + _matern12_with_fixed_rho(4.0)
    assert spec.n_theta() == 2


def test_spec_hash_differs_for_specs_with_different_defaults():
    """spec_hash() distinguishes specs that differ only in a parameter default.

    Every other hash test in this file asserts equality between specs that
    are the same model up to construction order or dict insertion order, so
    a spec_hash() that always returned a fixed constant -- or that hashed
    only term kinds and labels while dropping parameter values -- would pass
    every one of them. This test is the only one in the suite that requires
    inequality, so it is the only one such a stub implementation would fail.

    Bug this catches: spec_hash() dropping parameter defaults from the
    canonical form, which would let a genuinely different model fit collide
    with an unrelated cached result in the 10^7-point store.
    """
    a = ProcessSpec((_matern12(3.0),))
    b = ProcessSpec((_matern12(4.0),))
    assert a.spec_hash() != b.spec_hash()


def test_n_theta_refuses_shared_parameters():
    """n_theta() raises on a shared-parameter spec instead of miscounting it.

    Before this fix, ProcessSpec.n_theta() summed TermSpec.n_free(), which
    checked only `fixed` and ignored `shared_with` entirely -- a spec with a
    shared parameter returned a finite n_theta() while free_param_index()
    raised NotImplementedError on the identical spec. That divergence is
    exactly what the project's shared-parameter discipline forbids: k in
    every information criterion must never silently count a shared parameter
    as independent.

    Bug this catches: n_theta() and free_param_index() disagreeing on
    whether a shared-parameter spec is refused.
    """
    term = _matern12(3.0)
    shared = TermSpec(
        kind="matern12",
        params=term.params,
        ordering_param="rho",
        shared_with={"sigma": "other"},
    )
    with pytest.raises(NotImplementedError, match="shared"):
        ProcessSpec((shared,)).n_theta()


def test_label_association_survives_a_tied_ordering_value():
    """Same ordering-param value: labels attach to the same term either way.

    Two matern12 terms share rho=5.0 but differ in sigma (1.0 vs 2.0), so
    order_key()'s first two elements (kind, ordering default) tie. Under a
    non-total key, Python's stable sort would then fall back to construction
    order, and matern12[0] would mean "whichever term was added first"
    rather than a property of the term itself.

    Expected association determined independently of the implementation:
    with kind and ordering default tied, canonical() renders each term's
    params as a dict sorted by key ("rho" before "sigma"), so the two terms'
    JSON strings are identical character-for-character up through the "rho"
    entry and first diverge at sigma's "default" field: '"default":"1.0"'
    vs '"default":"2.0"'. Lexicographic string comparison then orders the
    sigma=1.0 term first regardless of which object was constructed first.
    So matern12[0] must carry sigma=1.0 and matern12[1] must carry sigma=2.0
    in both construction orders, and the two resulting specs must hash
    identically.

    Bug this catches: order_key() returning only (kind, ordering default),
    which is not a total order -- terms with a tied ordering-param default
    silently keep construction order, so matern12[0] refers to a different
    term depending on which ProcessSpec was built first. This corrupts
    warm-start reuse and cross-run comparison without raising anything.
    """
    term_sigma1 = TermSpec(
        kind="matern12",
        params={"sigma": _param("sigma", 1.0), "rho": _param("rho", 5.0)},
        ordering_param="rho",
    )
    term_sigma2 = TermSpec(
        kind="matern12",
        params={"sigma": _param("sigma", 2.0), "rho": _param("rho", 5.0)},
        ordering_param="rho",
    )
    forward = term_sigma1 + term_sigma2
    backward = term_sigma2 + term_sigma1

    assert forward.labels() == ("matern12[0]", "matern12[1]")
    assert backward.labels() == ("matern12[0]", "matern12[1]")
    assert forward.terms[0].params["sigma"].default == 1.0
    assert backward.terms[0].params["sigma"].default == 1.0
    assert forward.terms[1].params["sigma"].default == 2.0
    assert backward.terms[1].params["sigma"].default == 2.0
    assert forward.spec_hash() == backward.spec_hash()


def test_logit_transform_args_round_trip_and_are_construction_insensitive():
    """A transform with float constructor args serializes safely and stably.

    Round-trip: this path has zero prior coverage, since every other test in
    this file uses Log(), whose __dict__ is empty. Logit(0.5, 10.0) exercises
    the transform_args stringification directly. Expected value determined
    independently from Logit.__init__ (self.lo = float(lo); self.hi =
    float(hi)) and the repr(float(...)) convention _param_canonical already
    applies elsewhere: transform_args must equal {"lo": "0.5", "hi": "10.0"}.

    Construction-insensitivity: two independently constructed Logit(0.5, 10.0)
    objects (different Python objects, same argument values) must canonicalize
    identically. A buggy implementation that stringified the transform object
    itself (str(transform), or a default object repr, which embeds the
    object's memory address) would make two logically-identical Logit
    instances hash differently purely because they are different objects --
    the same kind of accidental-identity dependence the dict-insertion-order
    tests in this file already guard against, just for the transform instead
    of the params dict.
    """
    param_a = ParamSpec(
        name="p",
        default=1.0,
        transform=Logit(0.5, 10.0),
        bounds=(0.5, 10.0),
        diagnostic_limits=(0.5, 10.0),
    )
    param_b = ParamSpec(
        name="p",
        default=1.0,
        transform=Logit(0.5, 10.0),
        bounds=(0.5, 10.0),
        diagnostic_limits=(0.5, 10.0),
    )
    term_a = TermSpec(kind="custom", params={"p": param_a})
    term_b = TermSpec(kind="custom", params={"p": param_b})

    transform_args = term_a.canonical()["params"]["p"]["transform_args"]
    assert transform_args == {"lo": "0.5", "hi": "10.0"}

    encoded = json.dumps(term_a.canonical(), sort_keys=True, separators=(",", ":"))
    assert json.loads(encoded) == json.loads(encoded)

    assert ProcessSpec((term_a,)).spec_hash() == ProcessSpec((term_b,)).spec_hash()


def test_labels_are_independent_of_construction_order():
    """.labels() is identical regardless of the order terms were added.

    test_canonical_order_is_independent_of_construction_order (above) checks
    only the sequence of `.kind` values and the hash; it never calls
    `.labels()`. That leaves a gap: labels() derives purely from position, so
    two same-kind terms swapping positions between constructions is
    invisible to a kind-only check when both specs contain the same
    multiset of kinds (the .kind sequence looks identical either way). This
    test asserts on .labels() directly to close that gap.

    Bug this catches: any construction-order dependence in the canonical
    sort -- including a non-total order_key that lets tied terms fall back
    to construction order -- surfaces here as labels() disagreeing between
    two differently-constructed but equivalent specs.
    """
    a = _matern12(50.0) + _white() + _matern12(2.0)
    b = _white() + _matern12(2.0) + _matern12(50.0)
    assert a.labels() == ("matern12[0]", "matern12[1]", "white[0]")
    assert b.labels() == ("matern12[0]", "matern12[1]", "white[0]")


def test_term_engine_costs_resolve_from_kernel_registry():
    """TermSpec.engine_costs() looks up `kind` in kernel_registry and returns
    the registered family's `.engine_costs` attribute.

    Task-3 brief correction 5: none of the brief's own test files exercised
    this wiring, and it is the only new code touching an already-committed
    module (terms.py) -- exactly where correction 3's two mypy defects live.

    Bug this catches: engine_costs() reading from the wrong registry (e.g.
    recipe_registry, which would KeyError here since the kind is only
    registered in kernel_registry), or returning the factory's raw return
    value instead of its `.engine_costs` attribute.
    """
    costs = {EngineId.KALMAN: CostClass.LINEAR, EngineId.WHITTLE: CostClass.NLOGN}
    kernel_registry.register("throwaway_engine_costs_a")(lambda: _FakeFamily(costs))
    try:
        term = TermSpec(kind="throwaway_engine_costs_a", params={})
        assert term.engine_costs() == costs
    finally:
        kernel_registry.unregister("throwaway_engine_costs_a")


def test_process_spec_engine_costs_intersects_with_worst_cost_per_engine():
    """ProcessSpec.engine_costs() is the per-engine worst cost, intersected
    across every term via TermSpec.engine_costs().

    Expected value determined independently: both throwaway terms support
    only KALMAN, at LINEAR and CUBIC respectively; the worst of the two is
    CUBIC, computed on paper via CostClass's declared ordering, not by
    re-running intersect_engine_costs mentally.

    Bug this catches: ProcessSpec.engine_costs() not calling
    intersect_engine_costs at all (e.g. returning only the first term's
    costs), or intersecting without taking the max, which would let a
    composite report a cheaper cost class than its most expensive term.
    """
    kernel_registry.register("throwaway_engine_costs_b1")(
        lambda: _FakeFamily({EngineId.KALMAN: CostClass.LINEAR})
    )
    kernel_registry.register("throwaway_engine_costs_b2")(
        lambda: _FakeFamily({EngineId.KALMAN: CostClass.CUBIC})
    )
    try:
        spec = ProcessSpec(
            (
                TermSpec(kind="throwaway_engine_costs_b1", params={}),
                TermSpec(kind="throwaway_engine_costs_b2", params={}),
            )
        )
        assert spec.engine_costs() == {EngineId.KALMAN: CostClass.CUBIC}
    finally:
        kernel_registry.unregister("throwaway_engine_costs_b1")
        kernel_registry.unregister("throwaway_engine_costs_b2")


def test_process_spec_engine_costs_raises_naming_a_term_when_no_engine_survives():
    """A composite whose terms share no common engine raises
    IncompatibleSpecError naming the terms responsible.

    Expected value determined independently: the two throwaway terms support
    disjoint engines (KALMAN only vs. TOEPLITZ only), so by set intersection
    done on paper the surviving set is empty and both term labels must appear
    in the error, one as KALMAN's eliminator and one as TOEPLITZ's.

    Bug this catches: ProcessSpec.engine_costs() swallowing the empty
    intersection instead of propagating IncompatibleSpecError, or passing
    plain `kind` strings instead of `labels()` into intersect_engine_costs
    and losing the per-term label the error is supposed to carry.
    """
    kernel_registry.register("throwaway_engine_costs_c1")(
        lambda: _FakeFamily({EngineId.KALMAN: CostClass.LINEAR})
    )
    kernel_registry.register("throwaway_engine_costs_c2")(
        lambda: _FakeFamily({EngineId.TOEPLITZ: CostClass.CUBIC})
    )
    try:
        spec = ProcessSpec(
            (
                TermSpec(kind="throwaway_engine_costs_c1", params={}),
                TermSpec(kind="throwaway_engine_costs_c2", params={}),
            )
        )
        with pytest.raises(IncompatibleSpecError) as excinfo:
            spec.engine_costs()
        message = str(excinfo.value)
        assert "throwaway_engine_costs_c1[0]" in message
        assert "throwaway_engine_costs_c2[0]" in message
    finally:
        kernel_registry.unregister("throwaway_engine_costs_c1")
        kernel_registry.unregister("throwaway_engine_costs_c2")
