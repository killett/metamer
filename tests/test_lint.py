"""Tests for the static identifiability lint (design doc section 4.8).

The lint makes claims about which compositions are observationally
indistinguishable. Several tests below check the *claim* with the families'
own `acvf` rather than checking the lint against itself: the lint decides by
comparing timescales, the families decide by evaluating a kernel, so the two
constructions share no code. That is the independent-oracle discipline --
a reference built the same way as its subject only measures the shared step.
"""

from __future__ import annotations

import math
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

import numpy as np
import pytest

from metamer.core.families.matern12 import Matern12
from metamer.core.families.matern32 import Matern32
from metamer.core.families.white import White
from metamer.core.lint import (
    OVERLAP_RATIO,
    WHITE_COLLAPSE_LOG_LIMIT,
    WHITE_TIMESCALE_FRACTION,
    Finding,
    Rule,
    lint,
)
from metamer.core.params import ParamSpec
from metamer.core.registry import kernel_registry
from metamer.core.terms import ProcessSpec, TermSpec
from metamer.core.transforms import Log
from tests.test_statespace import _term

if TYPE_CHECKING:
    from collections.abc import Iterator

# eps = 2**-52 for float64 -- a property of the IEEE format, not of this code.
# -0.5 * log(2**-52) = 26 * log(2), and exp(-26*log(2)) = 2**-26 = sqrt(eps).
LOG_LIMIT_BY_HAND = 26.0 * math.log(2.0)
CORRELATION_AT_LIMIT = 2.0**-26


def _rules(findings: list[Finding]) -> set[Rule]:
    """Return the set of rules that fired."""
    return {f.rule for f in findings}


def _of(findings: list[Finding], rule: Rule) -> list[Finding]:
    """Return the findings raised under one rule."""
    return [f for f in findings if f.rule is rule]


class _StatefulStub:
    """A family with state but no parameter named `rho`.

    Stands in for SHO (design doc section 4.8), whose timescale is Q/omega0
    rather than a `rho`. The lint must report that it cannot check such a term
    rather than skipping it silently.
    """

    kind = "lint_stub_stateful"
    state_dim = 1


@contextmanager
def _registered(key: str, family: Any) -> Iterator[None]:
    """Register `family` under `key` for the block, then remove it."""
    kernel_registry.register(key)(lambda: family)
    try:
        yield
    finally:
        kernel_registry.unregister(key)


def _param(name: str, default: float, *, fixed: bool = False) -> ParamSpec:
    """Build a positive-scale ParamSpec for stub terms."""
    return ParamSpec(
        name=name,
        default=default,
        transform=Log(),
        bounds=(0.0, np.inf),
        diagnostic_limits=(1e-8, 1e8),
        fixed=fixed,
    )


# --------------------------------------------------------------------------
# The derived white-collapse threshold
# --------------------------------------------------------------------------


def test_the_white_collapse_limit_is_the_square_root_of_machine_epsilon():
    """The threshold is derived from float64, not calibrated against a fixture.

    Expected value determined independently: float64 eps is 2**-52 by the IEEE
    format, so -0.5*log(eps) = 26*log(2) = 18.021826694558577, and the lag-one
    correlation at that point is exp(-26*log(2)) = 2**-26 = sqrt(eps). The
    half-power is the standard "a minimum can only be located to sqrt(eps)"
    argument: near the optimum the log-likelihood changes quadratically in the
    parameter, so a model difference smaller than sqrt(eps) moves it by less
    than eps*|l| and no optimizer can resolve it.

    Bug this catches: someone replacing the derived limit with a round number
    tuned until a hand-built fixture fired. PROGRESS.md records that exact
    failure for the conditioning thresholds -- a fixture proves a band is
    reachable, it must never specify the constant.
    """
    assert WHITE_COLLAPSE_LOG_LIMIT == pytest.approx(LOG_LIMIT_BY_HAND, rel=1e-15)
    assert WHITE_TIMESCALE_FRACTION == pytest.approx(1.0 / LOG_LIMIT_BY_HAND, rel=1e-15)
    assert math.exp(-WHITE_COLLAPSE_LOG_LIMIT) == pytest.approx(
        CORRELATION_AT_LIMIT, rel=1e-14
    )


def test_at_the_limit_the_family_kernel_reports_a_correlation_of_sqrt_eps():
    """The threshold's meaning is verified against the family's own kernel.

    Expected value determined independently: Matern12's ACVF is
    sigma^2 exp(-tau/rho); at tau = dt and rho = dt * WHITE_TIMESCALE_FRACTION
    the exponent is exactly -1/WHITE_TIMESCALE_FRACTION = -26*log(2), so the
    correlation is 2**-26. Computed from the closed-form kernel in the class
    docstring, not by re-running the lint's arithmetic.

    Bug this catches: the fraction and the log limit drifting apart -- e.g.
    WHITE_TIMESCALE_FRACTION hardcoded to 0.1 while the log limit says
    otherwise, so the constant the lint compares against no longer means the
    correlation it claims to mean. The lint decides by comparing timescales;
    this decides by evaluating the kernel, so the two cannot agree by
    construction.
    """
    dt = 7.0
    rho = dt * WHITE_TIMESCALE_FRACTION
    acvf = Matern12().acvf(np.array([[1.0, rho]]), np.array([dt]))
    assert float(acvf[0, 0]) == pytest.approx(CORRELATION_AT_LIMIT, rel=1e-12)


def test_the_white_limit_scales_with_the_sampling_interval():
    """The same rho is degenerate at one cadence and healthy at another.

    Expected value determined independently: the limit is
    dt / (26*log(2)) = dt * 0.055488. At dt = 10 that is 0.5549, so a term with
    rho = 1.0 resolves; at dt = 100 it is 5.549, so the same term does not.
    Both computed by hand from the derived fraction.

    Bug this catches: dropping the `* sampling_interval` factor, or comparing
    rho against a bare constant. THE BRIEF'S FOUR TESTS ALL USED
    sampling_interval=1.0, where that factor is the identity and deleting it
    changes no number -- the cancellation rule in PROGRESS.md (a) applied to
    this task. Sampling interval is the comparison axis here, and a test that
    holds it fixed at 1.0 is structurally blind to it.
    """
    spec = ProcessSpec((_term("white"), _term("matern12", rho=1.0)))
    assert _of(lint(spec, sampling_interval=10.0), Rule.WHITE_COLLAPSE) == []
    flagged = _of(lint(spec, sampling_interval=100.0), Rule.WHITE_COLLAPSE)
    assert [f.terms for f in flagged] == [("matern12[0]", "white[0]")]


# --------------------------------------------------------------------------
# Collapse onto white
# --------------------------------------------------------------------------


def test_a_short_timescale_matern_beside_white_collapses_to_white_plus_white():
    """The design doc's first named degeneracy, reported with its own words.

    Expected value determined independently: design doc section 4.8 states
    "white + Matern nu=1/2 with rho -> 0 is white + white". At rho = 1e-4 and
    dt = 1 the lag-one correlation is exp(-10000), which underflows float64
    entirely, so the Matern term's covariance is the identity times sigma^2 --
    numerically the same object as the white term.

    Bug this catches: no short-timescale rule at all, or one that names the
    composite rather than the terms, leaving a user with three Matern terms
    unable to tell which one is degenerate (acceptance criterion 5).
    """
    spec = ProcessSpec((_term("white"), _term("matern12", rho=1e-4)))
    findings = _of(lint(spec, sampling_interval=1.0), Rule.WHITE_COLLAPSE)
    assert [f.terms for f in findings] == [("matern12[0]", "white[0]")]
    assert "collapses to white + white" in findings[0].message


def test_a_short_timescale_matern_alone_reports_an_unidentified_timescale():
    """Without a nugget beside it the scale survives; only rho is lost.

    Expected value determined independently: a lone Matern nu=1/2 with
    rho << dt has covariance sigma^2 I, in which sigma is still estimable from
    the variance but rho appears nowhere -- the likelihood is flat in it. With
    a white term present it is sigma_white^2 + sigma_matern^2 that is
    estimable, so a second parameter is lost. Two different statements.

    Bug this catches: reporting "collapses to white + white" for a composite
    with no white term, which names a term that is not there, or conversely
    collapsing both cases into one message so a user cannot tell whether their
    amplitude estimate survived.
    """
    spec = ProcessSpec((_term("matern12", rho=1e-4),))
    findings = lint(spec, sampling_interval=1.0)
    assert _rules(findings) == {Rule.TIMESCALE_UNIDENTIFIED}
    assert findings[0].terms == ("matern12[0]",)


def test_a_fixed_short_timescale_is_reported_as_the_model_not_as_a_start():
    """A frozen parameter states the model; a free one states the search start.

    Expected value determined independently: `ParamSpec.default` is documented
    in params.py as "Starting value in natural units". For a free parameter
    that is where the optimizer begins, and it says nothing about where the
    optimizer ends; for `fixed=True` it is the value the model is pinned to
    for the whole fit. Those are different facts about identifiability and the
    finding must say which one it saw.

    Bug this catches: THE BRIEF READS `term.params["rho"].default`
    UNCONDITIONALLY and reports it as a property of the model. A free rho with
    an unlucky default would then be reported as structurally degenerate when
    the optimizer is free to walk straight out of that region on the first
    iteration -- a false positive, which the brief's own third test says
    trains users to ignore the lint.
    """
    free = ProcessSpec((_term("white"), _term("matern12", rho=1e-4)))
    pinned = ProcessSpec((_term("white"), _term("matern12", rho=1e-4, fixed=("rho",))))
    free_message = _of(lint(free, sampling_interval=1.0), Rule.WHITE_COLLAPSE)[
        0
    ].message
    pinned_message = _of(lint(pinned, sampling_interval=1.0), Rule.WHITE_COLLAPSE)[
        0
    ].message
    assert "fixed at" in pinned_message
    assert "fixed at" not in free_message
    assert "starts at" in free_message


# --------------------------------------------------------------------------
# Nugget terms
# --------------------------------------------------------------------------


def test_two_free_nugget_terms_are_flagged_and_are_provably_indistinguishable():
    """white + white is exactly non-identifiable, and the claim is checked.

    Expected value determined independently: White's ACVF is sigma^2 at lag 0
    and 0 elsewhere, so two nugget terms contribute sigma_a^2 + sigma_b^2 and
    nothing else. With sigma_a = 3 and sigma_b = 4 that is 25, identical at
    every lag to a single nugget with sigma = 5 -- the 3-4-5 triangle, chosen
    so the expected value is exact in binary. The second assertion is computed
    from the family's kernel, which shares no code with the lint.

    Bug this catches: THE BRIEF KEYS EVERY RULE ON A `rho` PARAMETER, and
    White has none -- so `white + white`, the literal composition acceptance
    criterion 1 names, returns an empty finding list. It is the purest
    non-identifiability in the whole taxonomy and the brief cannot see it.
    """
    two = White().acvf(np.array([[3.0]]), np.array([0.0, 1.0])) + White().acvf(
        np.array([[4.0]]), np.array([0.0, 1.0])
    )
    one = White().acvf(np.array([[5.0]]), np.array([0.0, 1.0]))
    assert np.array_equal(two, one)

    spec = ProcessSpec((_term("white", sigma=3.0), _term("white", sigma=4.0)))
    findings = lint(spec, sampling_interval=1.0)
    assert _rules(findings) == {Rule.NUGGET_COLLAPSE}
    assert findings[0].terms == ("white[0]", "white[1]")


def test_one_free_nugget_beside_a_pinned_one_is_identified():
    """A known variance offset leaves the free scale estimable.

    Expected value determined independently: with sigma_a fixed the total
    nugget variance is sigma_a^2 + sigma_b^2 where sigma_a^2 is known, so
    sigma_b^2 = total - sigma_a^2 is determined. Nothing is lost. Only when
    two or more nugget scales are free does the sum stop pinning its parts.

    Bug this catches: flagging on "two nugget terms" rather than on "two free
    nugget scales", which fires on the ordinary case of a known instrument
    noise floor beside a fitted one.
    """
    spec = ProcessSpec(
        (_term("white", sigma=3.0, fixed=("sigma",)), _term("white", sigma=4.0))
    )
    assert lint(spec, sampling_interval=1.0) == []


# --------------------------------------------------------------------------
# Same-kind terms
# --------------------------------------------------------------------------


def test_same_kind_free_timescales_are_flagged_however_far_apart_the_defaults():
    """Exchangeability does not depend on where the search starts.

    Expected value determined independently: for two terms of the same kind
    the sum kernel is symmetric under swapping their whole parameter tuples,
    so any optimum has a mirror image with the labels exchanged, and the
    surface rho_a = rho_b -- where the two merge into one term with
    sigma^2 = sigma_a^2 + sigma_b^2 -- lies inside the searched region for any
    starting values. PROGRESS.md records that nothing reorders terms
    mid-optimization, so the symmetry is genuinely in the searched space.

    Bug this catches: THE BRIEF COMPARES THE RATIO OF THE TWO DEFAULTS, so
    this spec (a factor of 1000 apart) lints clean while the fitted per-term
    sigma and rho maps come out salt-and-pepper across a 10^7-point grid as
    neighbouring pixels land in different mirror images.
    """
    spec = ProcessSpec((_term("matern12", rho=1.0), _term("matern12", rho=1000.0)))
    findings = lint(spec, sampling_interval=1.0)
    assert _rules(findings) == {Rule.SAME_KIND_FREE_TIMESCALES}
    assert findings[0].terms == ("matern12[0]", "matern12[1]")


def test_equal_timescale_same_kind_terms_are_indistinguishable_from_one_term():
    """The collapse the previous test warns about, verified on the kernel.

    Expected value determined independently: Matern12's ACVF is
    sigma^2 exp(-tau/rho), so at a shared rho two terms give
    (sigma_a^2 + sigma_b^2) exp(-tau/rho). With sigma_a = 3, sigma_b = 4 that
    is 25 exp(-tau/rho), identical to one term with sigma = 5. The identity is
    exact in real arithmetic; in float64 the two routes round differently --
    `9*e + 16*e` against `25*e` -- so the tolerance below is a few ulp and
    nothing more. It is not a fitted agreement band: a genuine separability
    between the two forms would be O(1), not O(1e-16).

    Bug this catches: the exchangeability warning being wrong -- if the sum of
    two same-kind terms at equal rho were separable, the rule above would be a
    pure false positive. It also fails if a family's ACVF stops being additive
    in sigma^2.
    """
    lags = np.array([0.0, 0.5, 3.0, 40.0])
    two = Matern12().acvf(np.array([[3.0, 2.0]]), lags) + Matern12().acvf(
        np.array([[4.0, 2.0]]), lags
    )
    one = Matern12().acvf(np.array([[5.0, 2.0]]), lags)
    assert two == pytest.approx(one, rel=1e-15, abs=0.0)


def test_pinned_timescales_are_flagged_inside_the_overlap_ratio_and_not_outside():
    """With both timescales frozen, separability is decided by their ratio.

    Expected value determined independently: the bracket is placed at 1% on
    either side of the declared OVERLAP_RATIO, so the test pins that the
    constant is honoured without letting the fixture choose its value --
    PROGRESS.md's rule that a fixture proves a band is reachable and never
    specifies a production constant.

    Bug this catches: a pinned-overlap rule that always fires (every same-kind
    pair, making the lint noise) or never fires (the threshold ignored), and a
    comparison written on the difference rather than the ratio, which would
    behave differently at rho = 1 and rho = 1000.
    """
    inside = ProcessSpec(
        (
            _term("matern12", rho=1.0, fixed=("rho",)),
            _term("matern12", rho=OVERLAP_RATIO * 0.99, fixed=("rho",)),
        )
    )
    outside = ProcessSpec(
        (
            _term("matern12", rho=1.0, fixed=("rho",)),
            _term("matern12", rho=OVERLAP_RATIO * 1.01, fixed=("rho",)),
        )
    )
    assert _rules(lint(inside, sampling_interval=1.0)) == {
        Rule.SAME_KIND_PINNED_OVERLAP
    }
    assert lint(outside, sampling_interval=1.0) == []


def test_the_overlap_ratio_means_a_stated_maximum_correlation_separation():
    """The policy constant has a stated consequence on the kernel.

    Expected value determined independently, by hand: for two Matern nu=1/2
    ACFs with timescales rho and r*rho, the difference exp(-tau/(r rho)) -
    exp(-tau/rho) is maximal at tau* = rho r log(r) / (r-1), where it equals
    r^(-1/(r-1)) - r^(-r/(r-1)). At r = 3/2 the exponents are 2 and 3, giving
    (2/3)^2 - (2/3)^3 = 4/9 - 8/27 = 4/27 = 0.148148...

    Bug this catches: OVERLAP_RATIO being changed without re-deriving what it
    means, leaving the docstring's justification attached to a different
    number. Unlike the white-collapse limit this constant is policy, not a
    float64 consequence, so pinning its meaning is the only check available.
    """
    assert OVERLAP_RATIO == 1.5
    rho, r = 2.0, OVERLAP_RATIO
    tau_star = rho * r * math.log(r) / (r - 1.0)
    slow = Matern12().acvf(np.array([[1.0, r * rho]]), np.array([tau_star]))
    fast = Matern12().acvf(np.array([[1.0, rho]]), np.array([tau_star]))
    assert float(slow[0, 0] - fast[0, 0]) == pytest.approx(4.0 / 27.0, rel=1e-12)


def test_different_kinds_at_the_same_timescale_are_not_flagged():
    """Matern nu=1/2 and nu=3/2 are distinct kernels at a shared rho.

    Expected value determined independently: at tau = rho the two ACFs are
    exp(-1) = 0.36788 and (1 + sqrt(3)) exp(-sqrt(3)) = 0.48285 -- a
    separation of 0.115, comparable to the 4/27 that the pinned-overlap rule
    treats as separable. Both computed from the closed forms in the family
    docstrings. The assertion below checks that separation on the kernels, so
    the test states why no finding is correct rather than merely observing
    that none appears.

    Bug this catches: a rule keyed on the timescale ratio alone rather than on
    the ratio *within a kind*, which would flag the project's own d = 3 spike
    composite the moment two of its terms landed on similar timescales.
    """
    rho = 3.0
    m12 = float(Matern12().acvf(np.array([[1.0, rho]]), np.array([rho]))[0, 0])
    m32 = float(Matern32().acvf(np.array([[1.0, rho]]), np.array([rho]))[0, 0])
    assert m12 == pytest.approx(math.exp(-1.0), rel=1e-12)
    assert m32 == pytest.approx(
        (1.0 + math.sqrt(3.0)) * math.exp(-math.sqrt(3.0)), rel=1e-12
    )
    assert abs(m32 - m12) > 4.0 / 27.0 * 0.5

    spec = ProcessSpec((_term("matern12", rho=rho), _term("matern32", rho=rho)))
    assert lint(spec, sampling_interval=1.0) == []


# --------------------------------------------------------------------------
# Clean specifications
# --------------------------------------------------------------------------


def test_the_projects_own_d3_composite_lints_clean():
    """white + matern12 + matern32 is the spike composite and must not fire.

    Expected value determined independently: PROGRESS.md records that d = 3 is
    reached via white + matern12 + matern32 precisely because the three terms
    are distinct. The timescales below (2.0 and 60.0 against dt = 1) are far
    above the white limit of 0.0555 and belong to different kinds, so no rule
    applies.

    Bug this catches: a lint that fires on the composition the project itself
    ships. PROGRESS.md's argument against false positives is not abstract --
    a lint that flags the canonical spec is one users learn to ignore, which
    costs the true positives too.
    """
    spec = ProcessSpec(
        (_term("white"), _term("matern12", rho=2.0), _term("matern32", rho=60.0))
    )
    assert lint(spec, sampling_interval=1.0) == []


def test_pinned_and_well_separated_same_kind_terms_lint_clean():
    """Two frozen timescales two orders of magnitude apart are separable.

    Expected value determined independently: ratio 100 against an overlap
    threshold of 1.5, and both far above the white limit of 0.0555 at dt = 1.
    Frozen, so the exchangeability rule does not apply either.

    Bug this catches: a same-kind rule that fires on kind alone, which would
    make every multi-component Matern model unlintable.
    """
    spec = ProcessSpec(
        (
            _term("matern12", rho=1.0, fixed=("rho",)),
            _term("matern12", rho=100.0, fixed=("rho",)),
        )
    )
    assert lint(spec, sampling_interval=1.0) == []


# --------------------------------------------------------------------------
# Specifications the lint cannot check, and inputs it refuses
# --------------------------------------------------------------------------


def test_an_unregistered_kind_is_reported_rather_than_raised():
    """A typo in a kind must not come back as "clean".

    Expected value determined independently: `Registry.__getitem__` is
    documented to raise KeyError for an unknown key, so any lookup through the
    registry is a raise waiting to happen -- and acceptance criterion 4 says
    the lint returns rather than raises. Skipping the term instead would be
    worse: the lint would report no findings for a spec that cannot even be
    built, which is the silent all-clear.

    Bug this catches: `kernel_registry[term.kind]` called bare, turning the
    warn-only lint into a blocker at exactly the moment a user most needs a
    readable report; or a bare `except KeyError: continue`.
    """
    spec = ProcessSpec((TermSpec(kind="no_such_kind", params={}),))
    findings = lint(spec, sampling_interval=1.0)
    assert _rules(findings) == {Rule.NOT_LINTABLE}
    assert findings[0].terms == ("no_such_kind[0]",)
    assert "not registered" in findings[0].message


def test_a_stateful_family_without_a_known_timescale_is_reported_unchecked():
    """The lint's coverage gap is a finding, not a silent skip.

    Expected value determined independently: design doc section 4.8 names SHO
    with Q -> 0.5 as a degenerate pattern, and SHO's timescale is Q/omega0,
    not a `rho`. A term with state but no `rho` therefore has a timescale the
    lint does not know how to read, and it must say so.

    Bug this catches: THE BRIEF'S `if "rho" not in term.params: continue`,
    which merges two entirely different cases into one silent skip -- white,
    where skipping is correct because there is no timescale, and any future
    stateful family, where skipping means the term was never checked. The
    second case lints clean and no test can see the loss.
    """
    with _registered("lint_stub_stateful", _StatefulStub()):
        spec = ProcessSpec(
            (
                _term("white"),
                TermSpec(
                    kind="lint_stub_stateful",
                    params={"omega0": _param("omega0", 1.0)},
                ),
            )
        )
        findings = lint(spec, sampling_interval=1.0)
    assert _rules(findings) == {Rule.NOT_LINTABLE}
    assert findings[0].terms == ("lint_stub_stateful[0]",)
    assert "timescale" in findings[0].message


def test_a_family_that_does_not_declare_state_dim_is_reported_unchecked():
    """A third-party family missing a protocol attribute is reported, not fatal.

    Expected value determined independently: `Family` in families/base.py
    declares `state_dim: int`, and `Registry` loads families from an
    entry-point group, so a family the project does not own can reach the lint
    without satisfying the protocol. The lint decides nugget-versus-stateful
    entirely from `state_dim`, so without it there is no classification to
    make.

    Bug this catches: `family.state_dim` accessed bare, raising AttributeError
    out of a pass whose acceptance criterion is that it never raises -- and
    doing so from inside a third-party plugin path, where the traceback points
    at the lint rather than at the family that is actually malformed.
    """

    class _NoStateDim:
        kind = "lint_stub_no_state_dim"

    with _registered("lint_stub_no_state_dim", _NoStateDim()):
        spec = ProcessSpec((TermSpec(kind="lint_stub_no_state_dim", params={}),))
        findings = lint(spec, sampling_interval=1.0)
    assert _rules(findings) == {Rule.NOT_LINTABLE}
    assert findings[0].terms == ("lint_stub_no_state_dim[0]",)
    assert "state_dim" in findings[0].message


def test_lint_does_not_raise_for_a_spec_the_rest_of_the_tree_refuses():
    """Warn, do not block -- including for specs nothing else will accept.

    Expected value determined independently: `terms.free_param_index` and
    `ProcessSpec.n_theta` both raise NotImplementedError for a term declaring
    `shared_with`, per design doc section 4.7. The lint runs before any of
    that, so it must report what it can and return.

    Bug this catches: the lint reaching for `n_theta()` or
    `free_param_index()` to decide which parameters are free and inheriting
    their refusal, which converts the one advisory pass in the pipeline into a
    hard stop. The brief's own version of this test asserted only
    `isinstance(result, list)`, which the return annotation already
    guarantees and which passes against `return []`.
    """
    shared = TermSpec(
        kind="matern12",
        params={"sigma": _param("sigma", 1.0), "rho": _param("rho", 1e-4)},
        ordering_param="rho",
        shared_with={"sigma": "other_term"},
    )
    spec = ProcessSpec((_term("white"), shared))
    findings = lint(spec, sampling_interval=1.0)
    assert _rules(findings) == {Rule.WHITE_COLLAPSE}


def test_an_empty_specification_is_reported():
    """A model with no noise terms has no likelihood to be flat.

    Expected value determined independently: with no terms Sigma is the zero
    matrix, which has no Cholesky factor and no log-determinant, so every
    parameter is trivially unidentified. `ProcessSpec()` defaults to an empty
    tuple, so this is reachable by construction rather than contrived.

    Bug this catches: a lint whose rules are all pairwise or per-term, so the
    empty spec falls through every loop and returns [] -- reporting the one
    model that cannot be fitted at all as the cleanest in the suite.
    """
    findings = lint(ProcessSpec(()), sampling_interval=1.0)
    assert _rules(findings) == {Rule.NO_NOISE_TERMS}
    assert findings[0].terms == ()


@pytest.mark.parametrize("bad", [0.0, -1.0, float("nan"), float("inf")])
def test_an_invalid_sampling_interval_raises(bad):
    """A bad cadence is a caller error, not a model finding.

    Expected value determined independently: the white limit is
    dt/(26 log 2), so dt = 0 makes it 0 and no rho can fall below it; dt < 0
    makes it negative with the same effect; NaN makes every comparison False.
    All three produce an empty finding list -- a silent all-clear from a
    diagnostic, which PROGRESS.md records as the worst available failure.
    Infinity is the mirror image: every term is flagged.

    Bug this catches: accepting the argument unchecked. This does not
    contradict acceptance criterion 4, which is about degenerate
    *specifications* being reported rather than rejected; the spec here is
    fine and it is the cadence that is unusable, so returning "no findings"
    would be an answer to a question that was never asked.
    """
    spec = ProcessSpec((_term("white"), _term("matern12", rho=1.0)))
    with pytest.raises(ValueError, match="sampling_interval"):
        lint(spec, sampling_interval=bad)


# --------------------------------------------------------------------------
# Several rules at once
# --------------------------------------------------------------------------


def test_a_spec_triggering_several_rules_reports_every_one():
    """Findings accumulate; no rule short-circuits the pass.

    Expected value determined independently, rule by rule, on a deliberately
    heterogeneous spec: two free nugget scales (NUGGET_COLLAPSE); a Matern
    nu=1/2 at rho = 1e-4 against a white limit of 0.0555 at dt = 1, with
    nuggets present (WHITE_COLLAPSE); and two free-timescale matern32 terms
    (SAME_KIND_FREE_TIMESCALES). Three rules, and the matern12 is not paired
    with itself because there is only one of it.

    Bug this catches: an early `return findings` after the first rule, or a
    later rule overwriting the list rather than extending it. PROGRESS.md's
    standing rule against homogeneous fixtures applies to rule coverage too --
    a spec that trips exactly one rule cannot show that the others still run.
    """
    spec = ProcessSpec(
        (
            _term("white", sigma=1.0),
            _term("white", sigma=2.0),
            _term("matern12", rho=1e-4),
            _term("matern32", rho=5.0),
            _term("matern32", rho=50.0),
        )
    )
    findings = lint(spec, sampling_interval=1.0)
    assert _rules(findings) == {
        Rule.NUGGET_COLLAPSE,
        Rule.WHITE_COLLAPSE,
        Rule.SAME_KIND_FREE_TIMESCALES,
    }
    assert _of(findings, Rule.SAME_KIND_FREE_TIMESCALES)[0].terms == (
        "matern32[0]",
        "matern32[1]",
    )


def test_the_lint_is_on_the_public_surface_beside_fit():
    """`lint` is reachable from `metamer.core`, not only from its own module.

    Expected value determined independently: `metamer/core/__init__.py`
    declares the array-level public API in `__all__`, and design doc section
    4.8 asks for a pass users run "at construction time" -- the same category
    of user-facing entry point as `fit`, which is already exported. The names
    below are the whole surface this module offers: the function and the two
    types needed to read what it returns.

    Bug this catches: the lint shipping only at `metamer.core.lint`, so a
    user follows the design doc, finds `fit` at the top level, and concludes
    there is no lint. It also fails if `Rule` or `Finding` is left behind,
    which would export a function whose return value cannot be typed or
    filtered without a second, deeper import.
    """
    import metamer.core as core

    assert {"lint", "Finding", "Rule"} <= set(core.__all__)
    assert core.lint is lint
    assert core.Rule is Rule
    assert core.Finding is Finding


def test_every_finding_names_labels_drawn_from_the_spec():
    """Acceptance criterion 5, checked across every rule that can fire.

    Expected value determined independently: `ProcessSpec.labels()` is the
    only source of stable per-term names, and it disambiguates repeated kinds
    with a bracketed index. A finding naming a bare kind would be ambiguous
    for exactly the specs the lint exists to report, since those are the ones
    with repeated kinds.

    Bug this catches: a finding built from `term.kind` rather than from the
    label, so a three-Matern spec reports "matern12" three times and the user
    cannot tell which pair to change.
    """
    spec = ProcessSpec(
        (
            _term("white", sigma=1.0),
            _term("white", sigma=2.0),
            _term("matern12", rho=1e-4),
            _term("matern32", rho=5.0),
            _term("matern32", rho=50.0),
        )
    )
    labels = set(spec.labels())
    findings = lint(spec, sampling_interval=1.0)
    for finding in findings:
        assert finding.terms
        assert set(finding.terms) <= labels
        for label in finding.terms:
            assert label in finding.message
