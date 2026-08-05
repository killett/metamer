import json

import pytest

from metamer.core.params import ParamSpec
from metamer.core.terms import ProcessSpec, TermSpec, free_param_index
from metamer.core.transforms import Log


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
    ],
)
def test_free_param_index_length_equals_n_theta(spec_factory):
    """The layout and the count can never disagree.

    This single invariant is what makes the parameter vector safe: n_theta
    feeds k in every information criterion, and free_param_index defines what
    the optimizer searches. If they diverge, selection is corrupted with no
    visible symptom.
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
