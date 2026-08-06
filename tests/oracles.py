"""Brute-force reference implementations used to validate the fast paths.

Independently-derived references. Nothing here may import the code under test.
"""

from collections.abc import Callable

import numpy as np
from numpy.typing import NDArray

# scipy ships no type stubs and `scipy-stubs` is not a project dependency, so
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
