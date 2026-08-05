import numpy as np
import pytest

from metamer.core.params import ParamSpec
from metamer.core.transforms import Identity, Log, Logit, delta_method_cov


@pytest.mark.parametrize(
    "bij, u",
    [
        (Log(), np.array([-3.0, 0.0, 2.5])),
        (Logit(0.0, 1.0), np.array([-2.0, 0.0, 4.0])),
        (Logit(0.5, 10.0), np.array([-1.0, 0.3])),
        (Identity(), np.array([-7.0, 0.0, 7.0])),
    ],
)
def test_roundtrip(bij, u):
    """inverse(forward(u)) recovers u.

    Bug this catches: a Logit that forgets to rescale by (hi - lo) in one
    direction, which silently squashes every bounded parameter toward its
    lower bound.
    """
    np.testing.assert_allclose(bij.inverse(bij.forward(u)), u, rtol=0, atol=1e-12)


@pytest.mark.parametrize(
    "bij, u",
    [
        (Log(), np.array([-1.5, 0.0, 2.0])),
        (Logit(0.0, 1.0), np.array([-1.0, 0.0, 1.0])),
        (Logit(-2.0, 3.0), np.array([0.25])),
        (Identity(), np.array([-7.0, 0.0, 7.0])),
    ],
)
def test_log_abs_det_jacobian_matches_finite_difference(bij, u):
    """log|J| equals log|d forward / d u| computed by central differences.

    Bug this catches: a sign error or a missing (hi - lo) factor in log|J|,
    which would bias any future MCMC and corrupt reported error bars now.
    Also covers Identity(), whose only correct log|J| is exactly zero
    everywhere — a stray nonzero constant would pass unnoticed without it.
    """
    h = 1e-6
    numeric = np.log(np.abs((bij.forward(u + h) - bij.forward(u - h)) / (2 * h)))
    np.testing.assert_allclose(
        bij.log_abs_det_jacobian(u), numeric, rtol=1e-6, atol=1e-7
    )


@pytest.mark.parametrize(
    "bij, u",
    [
        (Identity(), np.array([-7.0, 0.0, 7.0])),
        (Log(), np.array([-1.5, 0.0, 2.0])),
        (Logit(0.0, 1.0), np.array([-1.0, 0.0, 1.0])),
        (Logit(-2.0, 3.0), np.array([0.25])),
    ],
)
def test_dforward_matches_finite_difference(bij, u):
    """dforward equals d(forward)/du computed by central differences.

    dforward is the exact quantity delta_method_cov consumes to push
    covariances into natural units, so an error here silently corrupts
    every reported uncertainty. Bug this catches: Logit.dforward missing
    the (hi - lo) width factor — invisible on the (0, 1) box, where that
    factor is 1, but a 5x error on the (-2, 3) box below — or Log.dforward
    / Identity.dforward returning anything other than exp(u) / 1.
    """
    h = 1e-6
    numeric = (bij.forward(u + h) - bij.forward(u - h)) / (2 * h)
    np.testing.assert_allclose(bij.dforward(u), numeric, rtol=1e-6, atol=1e-7)


def test_delta_method_cov_against_explicit_computation():
    """delta_method_cov(d, cov) equals diag(d) @ cov @ diag(d).T.

    Expected value determined independently: J is diagonal because the
    transforms are elementwise, so the answer is d_i d_j cov_ij by hand.
    """
    d = np.array([2.0, 3.0])
    cov_u = np.array([[1.0, 0.5], [0.5, 4.0]])
    expected = np.array([[4.0 * 1.0, 6.0 * 0.5], [6.0 * 0.5, 9.0 * 4.0]])
    np.testing.assert_allclose(delta_method_cov(d, cov_u), expected, rtol=1e-12)


def test_delta_method_cov_with_batch_axis():
    """delta_method_cov broadcasts correctly across a leading batch axis.

    (B, N) is the only code path this project supports — B=1 is a shape,
    never a separate implementation — so a batch axis is the contract,
    not an extra. Bug this catches: `d[:, None]` written where
    `d[..., :, None]` is meant, which silently misaligns the scaling once
    a batch axis is present and mixes one batch member's d into another
    member's covariance. Two batch members with different d vectors make
    such a mix-up visible instead of cancelling out.

    Expected values hand-computed independently of the implementation, per
    batch member b: expected[b, i, j] = d[b, i] * cov[b, i, j] * d[b, j].
    """
    d = np.array([[2.0, 3.0], [1.0, 5.0]])
    cov_u = np.array(
        [
            [[1.0, 0.5], [0.5, 4.0]],
            [[2.0, -1.0], [-1.0, 3.0]],
        ]
    )
    expected = np.array(
        [
            [[4.0, 3.0], [3.0, 36.0]],
            [[2.0, -5.0], [-5.0, 75.0]],
        ]
    )
    np.testing.assert_allclose(delta_method_cov(d, cov_u), expected, rtol=1e-12)


def test_paramspec_rejects_default_outside_bounds():
    """A default outside bounds is a construction-time error.

    Bug this catches: a family shipping nu=0.5 with bounds (1.0, 3.0), which
    would otherwise surface as a mystifying optimizer failure at fit time.
    """
    with pytest.raises(ValueError, match="default"):
        ParamSpec(
            name="nu",
            default=0.5,
            transform=Logit(1.0, 3.0),
            bounds=(1.0, 3.0),
            diagnostic_limits=(1.0, 3.0),
        )


def test_diagnostic_limits_are_independent_of_bounds():
    """diagnostic_limits may be strictly inside bounds and do not clip.

    Bug this catches: conflating the two, which would silently clamp a
    parameter instead of reporting DIAGNOSTIC_LIMIT.
    """
    spec = ParamSpec(
        name="rho",
        default=10.0,
        transform=Log(),
        bounds=(0.0, np.inf),
        diagnostic_limits=(1e-3, 1e4),
    )
    assert spec.bounds == (0.0, np.inf)
    assert spec.diagnostic_limits == (1e-3, 1e4)
    assert spec.at_diagnostic_limit(1e5) is True
    assert spec.at_diagnostic_limit(10.0) is False
