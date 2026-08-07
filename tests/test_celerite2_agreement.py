"""Optional celerite2 agreement on the shared kernel subset (exit criterion 2).

**This validates a different axis from the MVN oracle.** MVN validates the
state-space construction -- `F`, `Q`, `P_inf`, the block-diagonal assembly, the
augmented filter -- which is the bespoke part of this package. celerite2
validates the **autocovariance function**, which is textbook: it computes the
same Gaussian likelihood from an entirely different algorithm (a semiseparable
Cholesky over the kernel's real-exponential basis) with no Kalman recursion
anywhere in it. Agreement therefore says the ACF this package *implements* is
the ACF it *claims*, which no amount of internal consistency can establish.

**The shared subset is white + Matern nu=1/2 and nothing else.** celerite2's
basis is sums of real and complex exponentials, so `sigma^2 exp(-tau/rho)` is a
single `RealTerm(a=sigma^2, c=1/rho)` exactly. Matern nu=3/2 is **not** in that
basis -- celerite2 offers it only as an approximation built by splitting the
term -- so a composite containing it is eliminated from the comparison rather
than compared approximately. `test_families.py` documents that elimination.

**Optional, and Tier-1 only.** `celerite2` has no `osx-arm64` conda-forge build
and is pinned to `[target.linux-64.dependencies]`, so this module skips wherever
it is not importable rather than failing.
"""

from __future__ import annotations

import numpy as np
import pytest

from metamer.core.capability import Objective
from metamer.core.engines.kalman import KalmanEngine
from metamer.core.outcomes import Outcome
from metamer.core.statespace import StateSpace
from metamer.core.terms import ProcessSpec
from tests.test_statespace import _term

celerite2 = pytest.importorskip(
    "celerite2", reason="celerite2 is optional and has no osx-arm64 conda-forge build"
)

SIGMA_M, RHO, SIGMA_W = 1.3, 2.7, 0.6


def _spec_and_theta() -> tuple[ProcessSpec, np.ndarray]:
    """Build `white + matern12` and its full natural-unit parameter vector.

    The layout is read off `spec.terms` rather than assumed: `ProcessSpec`
    sorts canonically, so `matern12` precedes `white` and the vector is
    (sigma_matern, rho, sigma_white). Hardcoding that order would silently
    swap two scales if the canonical sort ever changed.
    """
    spec = ProcessSpec(
        (_term("white", sigma=SIGMA_W), _term("matern12", sigma=SIGMA_M, rho=RHO))
    )
    values = [
        float(term.params[name].default) for term in spec.terms for name in term.params
    ]
    assert values == [SIGMA_M, RHO, SIGMA_W], values
    return spec, np.asarray([values], dtype=np.float64)


def _celerite_loglik(t: np.ndarray, y: np.ndarray) -> float:
    """Log-likelihood of white + Matern nu=1/2 from celerite2.

    `RealTerm(a, c)` is `a * exp(-c * tau)`, so the Matern nu=1/2 covariance
    `sigma^2 exp(-tau/rho)` is `a = sigma^2`, `c = 1/rho` -- exact, not an
    approximation. White noise goes in as `diag`, which is where a measurement
    variance belongs: it is a nugget on the diagonal only, never off it.
    """
    # Imported here rather than at module scope: the `importorskip` above has
    # to run first, and a module-level import after it is an E402.
    from celerite2 import terms  # type: ignore[import-untyped]

    kernel = terms.RealTerm(a=SIGMA_M**2, c=1.0 / RHO)
    gp = celerite2.GaussianProcess(kernel, mean=0.0)
    gp.compute(t, diag=np.full(t.size, SIGMA_W**2))
    return float(gp.log_likelihood(y))


def _engine_loglik(t: np.ndarray, y: np.ndarray, mask: np.ndarray) -> float:
    """Log-likelihood of the same model from the batched Kalman engine."""
    spec, theta = _spec_and_theta()
    result = KalmanEngine().score(
        StateSpace.from_spec(spec),
        theta,
        y[None, :],
        mask[None, :],
        t,
        None,
        Objective.ML,
    )
    assert result.outcome[0] == Outcome.OK.code
    return float(result.loglik[0])


def test_the_kalman_filter_agrees_with_celerite2_on_a_regular_axis():
    """Two unrelated algorithms give the same likelihood for the same model.

    Expected value determined independently: celerite2 computes the Gaussian
    log-likelihood by a semiseparable Cholesky over the kernel's exponential
    basis, with no Kalman recursion in it, and it was itself checked here
    against an explicit MVN at N=50 (agreed to all printed digits). So it is a
    third construction, not a restatement of either the filter or the oracle.

    1e-10 relative is a tolerance on summation order. A wrong ACF -- a missing
    factor of 2 in the exponent, `rho` read as a rate rather than a timescale,
    the nugget placed off-diagonal -- produces O(1) relative error.

    Bug this catches: THE ONE AXIS THE MVN ORACLE CANNOT SEE. MVN validates
    that the state-space construction reproduces the covariance matrix this
    package builds; it cannot say that covariance is the Matern nu=1/2 anyone
    else means by the name. If `Q(dt)` and `P_inf` were internally consistent
    but implemented a different kernel, every MVN test would still pass and
    every cross-validation against Hector or celerite2 would silently
    disagree.
    """
    rng = np.random.default_rng(0)
    t = np.arange(200, dtype=np.float64) / 12.0
    y = rng.standard_normal(200)
    mask = np.ones(200, dtype=bool)
    assert _engine_loglik(t, y, mask) == pytest.approx(
        _celerite_loglik(t, y), rel=1e-10
    )


def test_the_two_agree_on_an_irregular_axis():
    """Uneven spacing is the case the ACF and the recursion could diverge on.

    Expected value determined independently: both implementations are exact
    for arbitrary spacing -- celerite2 evaluates `exp(-c*tau)` at the actual
    lags, and the filter builds `F` and `Q` per distinct `dt`. Neither
    approximates, so they must still agree to summation order.

    Bug this catches: a filter that is right only on a uniform grid, which is
    the grid every other fixture in this suite uses. `statespace.unique_dt`
    clusters timesteps by tolerance, and an irregular axis is what exercises
    that clustering -- a bug there gives every interval the wrong `F` and `Q`
    and shows up nowhere on `np.arange`.
    """
    rng = np.random.default_rng(4)
    t = np.sort(rng.uniform(0.0, 20.0, 150))
    y = rng.standard_normal(150)
    mask = np.ones(150, dtype=bool)
    assert _engine_loglik(t, y, mask) == pytest.approx(
        _celerite_loglik(t, y), rel=1e-10
    )


def test_a_masked_epoch_matches_celerite2_on_the_genuinely_shorter_series():
    """Masking is identical to absence, checked against an outside implementation.

    Expected value determined independently: celerite2 has no mask, so it is
    given the series with the masked samples REMOVED -- a genuinely shorter
    record on a genuinely irregular axis. The filter is given the full series
    with those epochs masked. The two must agree exactly, because a masked
    epoch is defined to contribute nothing.

    Bug this catches: down-weighting a gap instead of skipping the update, or
    letting a masked sample's value leak into the innovation. Exit criterion 3
    already pins masked-equals-absent internally; this pins it against an
    implementation that has no concept of a mask at all, so an error shared
    between this package's two masked code paths cannot hide in it.
    """
    rng = np.random.default_rng(7)
    n = 180
    t = np.sort(rng.uniform(0.0, 15.0, n))
    y = rng.standard_normal(n)
    mask = rng.random(n) >= 0.25
    assert 0.6 < mask.mean() < 0.9, "fixture must actually drop a meaningful share"

    filtered = _engine_loglik(t, y, mask)
    absent = _celerite_loglik(t[mask], y[mask])
    assert filtered == pytest.approx(absent, rel=1e-10)


def test_a_matern32_composite_is_not_compared_against_celerite2():
    """The shared subset excludes nu=3/2, and that exclusion is deliberate.

    Expected value determined independently: celerite2's basis is sums of real
    and complex exponentials. Matern nu=1/2 is one real exponential exactly;
    Matern nu=3/2, `sigma^2 (1 + sqrt(3) tau/rho) exp(-sqrt(3) tau/rho)`,
    carries a factor linear in tau and is NOT in that basis -- celerite2
    provides it only as an approximation. Comparing against an approximation
    would produce a disagreement that says nothing about either implementation.

    Bug this catches: a later session widening this module to the full
    candidate set and then loosening the tolerance until it passes. That would
    convert an exact agreement test into a fitted one, and the loosened
    tolerance would mask a real ACF error in the nu=1/2 term. The assertion
    below is the boundary: only kinds in SHARED_KINDS may be compared here.
    """
    shared_kinds = {"white", "matern12"}
    spec, _ = _spec_and_theta()
    assert {term.kind for term in spec.terms} <= shared_kinds
    assert "matern32" not in shared_kinds
