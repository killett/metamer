"""Brute-force reference implementations used to validate the fast paths.

Independently-derived references. Nothing here may import the code under test.
"""

from collections.abc import Callable
from decimal import Decimal, localcontext

import numpy as np
from numpy.typing import NDArray
from scipy.linalg import expm, solve_continuous_lyapunov


def expm_transition(drift: NDArray[np.float64], dt: float) -> NDArray[np.float64]:
    """Transition matrix by general matrix exponential."""
    return expm(np.asarray(drift, dtype=np.float64) * float(dt))


def lyapunov_stationary_cov(
    drift: NDArray[np.float64], diffusion: NDArray[np.float64]
) -> NDArray[np.float64]:
    """Stationary covariance from A P + P A' + L L' = 0."""
    a = np.asarray(drift, dtype=np.float64)
    ll = (
        np.asarray(diffusion, dtype=np.float64)
        @ np.asarray(diffusion, dtype=np.float64).T
    )
    return solve_continuous_lyapunov(a, -ll)


def process_noise_from_stationary(
    stationary: NDArray[np.float64], transition: NDArray[np.float64]
) -> NDArray[np.float64]:
    """Q = P_inf - F P_inf F' for a stationary initialisation."""
    return stationary - transition @ stationary @ transition.T


def matern32_process_noise_exact(
    sigma: float, rho: float, dt: float, digits: int = 60
) -> NDArray[np.float64]:
    """Q = P_inf - F P_inf F' for Matern nu=3/2, evaluated at `digits` digits.

    The float64 evaluation of Q is the whole numerical difficulty of the family
    (Q_11 is cubic in the step while the terms subtracted to reach it are O(1)),
    so a reference has to be free of that cancellation rather than merely
    written differently. Decimal arithmetic at 60 significant digits leaves
    roughly 45 digits of headroom over the worst cancellation reachable here, so
    the result is exact to the last bit once rounded back to float64.

    This deliberately uses the SAME expression the naive implementation would --
    the literal difference P_inf - F P_inf F', with F the Jordan-block form and
    P_inf = diag(sigma^2, sigma^2 lambda^2) -- and NOT the small-step series the
    implementation switches to. So it is not a mirror of the code under test: a
    slip in the series derivation shows up here as a disagreement, while a slip
    in F or P_inf is caught separately by the expm and Lyapunov references
    above. What it does share, and does not test, is the SDE-to-matrix mapping
    (lambda = sqrt(3)/rho, A, L) stated in the `Matern32` class docstring.

    Args:
        sigma: Marginal standard deviation.
        rho: Correlation timescale.
        dt: Step length, non-negative.
        digits: Decimal working precision.

    Returns:
        Q, shape (2, 2), rounded to float64.
    """
    with localcontext() as ctx:
        ctx.prec = digits
        s, t = Decimal(repr(sigma)), Decimal(repr(dt))
        lam = Decimal(3).sqrt() / Decimal(repr(rho))
        decay = (-lam * t).exp()
        f = [
            [decay * (1 + lam * t), decay * t],
            [-decay * lam * lam * t, decay * (1 - lam * t)],
        ]
        p = [s * s, s * s * lam * lam]
        # (F P F')_ij = sum_k F_ik P_kk F_jk, with P diagonal.
        fpf = [
            [sum(f[i][k] * p[k] * f[j][k] for k in (0, 1)) for j in (0, 1)]
            for i in (0, 1)
        ]
        q = [
            [(p[i] if i == j else Decimal(0)) - fpf[i][j] for j in (0, 1)]
            for i in (0, 1)
        ]
        return np.array([[float(q[i][j]) for j in (0, 1)] for i in (0, 1)])


def mvn_loglik(
    y: NDArray[np.float64],
    cov: NDArray[np.float64],
    design: NDArray[np.float64] | None = None,
) -> float:
    """Brute-force multivariate-normal log-likelihood, GLS-profiled.

    This is the primary oracle. It is built from an analytic autocovariance and
    an explicit covariance matrix, so it is independent of the entire
    state-space formulation.

    Args:
        y: Observations, shape (n,).
        cov: Covariance matrix, shape (n, n).
        design: Optional design matrix (n, k). If given, beta is profiled out
            by generalized least squares.

    Returns:
        The (concentrated, if `design` is given) log-likelihood.
    """
    y = np.asarray(y, dtype=np.float64)
    cov = np.asarray(cov, dtype=np.float64)
    n = y.size
    sign, logdet = np.linalg.slogdet(cov)
    assert sign > 0, "covariance is not positive definite"
    cov_inv = np.linalg.inv(cov)
    if design is None:
        resid = y
    else:
        x = np.asarray(design, dtype=np.float64)
        xtwx = x.T @ cov_inv @ x
        beta = np.linalg.solve(xtwx, x.T @ cov_inv @ y)
        resid = y - x @ beta
    quad = float(resid @ cov_inv @ resid)
    return float(-0.5 * (n * np.log(2.0 * np.pi) + logdet + quad))


def reml_penalty(cov: NDArray[np.float64], design: NDArray[np.float64]) -> float:
    """Brute-force -0.5 log|X' Sigma^-1 X|, computed from an explicit Sigma."""
    cov_inv = np.linalg.inv(np.asarray(cov, dtype=np.float64))
    x = np.asarray(design, dtype=np.float64)
    sign, logdet = np.linalg.slogdet(x.T @ cov_inv @ x)
    assert sign > 0
    return float(-0.5 * logdet)


def reml_loglik(
    y: NDArray[np.float64], cov: NDArray[np.float64], design: NDArray[np.float64]
) -> float:
    """Brute-force ABSOLUTE REML log-likelihood, Harville (1974) form.

    Written from the published formula rather than from the implementation, and
    assembled term by term so that a constant offset in the code under test is
    visible. A differential test against ML cannot see such an offset, which is
    how the wrong normalization constant survived an earlier draft.

        l_R = -0.5 [ (n - rank(X)) log(2 pi) + log|Sigma|
                     + log|X' Sigma^-1 X| - log|X' X| + y' P y ]

    with P = Sigma^-1 - Sigma^-1 X (X' Sigma^-1 X)^-1 X' Sigma^-1.

    Args:
        y: Observations, shape (n,).
        cov: Covariance matrix Sigma, shape (n, n).
        design: Full-column-rank design matrix, shape (n, k).

    Returns:
        The REML log-likelihood.
    """
    y = np.asarray(y, dtype=np.float64)
    cov = np.asarray(cov, dtype=np.float64)
    x = np.asarray(design, dtype=np.float64)
    n = y.size
    rank = int(np.linalg.matrix_rank(x))

    cov_inv = np.linalg.inv(cov)
    xtwx = x.T @ cov_inv @ x
    p_matrix = cov_inv - cov_inv @ x @ np.linalg.solve(xtwx, x.T @ cov_inv)

    _, logdet_cov = np.linalg.slogdet(cov)
    _, logdet_xtwx = np.linalg.slogdet(xtwx)
    _, logdet_xtx = np.linalg.slogdet(x.T @ x)
    quad = float(y @ p_matrix @ y)

    return float(
        -0.5
        * (
            (n - rank) * np.log(2.0 * np.pi)
            + logdet_cov
            + logdet_xtwx
            - logdet_xtx
            + quad
        )
    )


def fd_hessian(
    fn: Callable[[NDArray[np.float64]], float],
    x: NDArray[np.float64],
    step: float = 1e-4,
) -> NDArray[np.float64]:
    """Central-difference Hessian of a scalar function."""
    x = np.asarray(x, dtype=np.float64)
    p = x.size
    out = np.zeros((p, p))
    for i in range(p):
        for j in range(p):
            ei = np.zeros(p)
            ej = np.zeros(p)
            ei[i] = step
            ej[j] = step
            out[i, j] = (
                fn(x + ei + ej) - fn(x + ei - ej) - fn(x - ei + ej) + fn(x - ei - ej)
            ) / (4.0 * step * step)
    return out
