"""Bijections from constrained parameter space to unconstrained R.

The optimizer only ever sees unconstrained coordinates. Each bijector exposes
the log absolute Jacobian determinant (needed for MCMC, and for correctness of
reported uncertainties) and the first derivative of the forward map (needed for
the delta-method push-through of covariances into natural units).
"""

from typing import Protocol, runtime_checkable

import numpy as np
from numpy.typing import NDArray


@runtime_checkable
class Bijector(Protocol):
    """Elementwise bijection between unconstrained R and a parameter's domain."""

    def forward(self, u: NDArray[np.float64]) -> NDArray[np.float64]:
        """Map unconstrained coordinates to natural units."""
        ...

    def inverse(self, x: NDArray[np.float64]) -> NDArray[np.float64]:
        """Map natural units to unconstrained coordinates."""
        ...

    def dforward(self, u: NDArray[np.float64]) -> NDArray[np.float64]:
        """Derivative of `forward` with respect to `u`."""
        ...

    def log_abs_det_jacobian(self, u: NDArray[np.float64]) -> NDArray[np.float64]:
        """Log absolute determinant of the forward Jacobian."""
        ...


class Identity:
    """The trivial bijection, for parameters already unconstrained."""

    def forward(self, u: NDArray[np.float64]) -> NDArray[np.float64]:
        """Return `u` unchanged."""
        return np.asarray(u, dtype=np.float64)

    def inverse(self, x: NDArray[np.float64]) -> NDArray[np.float64]:
        """Return `x` unchanged."""
        return np.asarray(x, dtype=np.float64)

    def dforward(self, u: NDArray[np.float64]) -> NDArray[np.float64]:
        """Return ones."""
        return np.ones_like(np.asarray(u, dtype=np.float64))

    def log_abs_det_jacobian(self, u: NDArray[np.float64]) -> NDArray[np.float64]:
        """Return zeros."""
        return np.zeros_like(np.asarray(u, dtype=np.float64))


class Log:
    """Positivity constraint: natural = exp(unconstrained)."""

    def forward(self, u: NDArray[np.float64]) -> NDArray[np.float64]:
        """Exponentiate."""
        return np.exp(np.asarray(u, dtype=np.float64))

    def inverse(self, x: NDArray[np.float64]) -> NDArray[np.float64]:
        """Take the natural logarithm."""
        return np.log(np.asarray(x, dtype=np.float64))

    def dforward(self, u: NDArray[np.float64]) -> NDArray[np.float64]:
        """Derivative of exp is exp."""
        return np.exp(np.asarray(u, dtype=np.float64))

    def log_abs_det_jacobian(self, u: NDArray[np.float64]) -> NDArray[np.float64]:
        """log|d exp(u)/du| = u."""
        return np.asarray(u, dtype=np.float64)


class Logit:
    """Box constraint on (lo, hi) via the logistic map."""

    def __init__(self, lo: float, hi: float):
        """Store the box bounds.

        Args:
            lo: Lower bound, exclusive.
            hi: Upper bound, exclusive. Must be strictly greater than `lo`.

        Raises:
            ValueError: If `hi` is not strictly greater than `lo`.
        """
        if not hi > lo:
            raise ValueError(f"Logit requires hi > lo, got lo={lo}, hi={hi}")
        self.lo = float(lo)
        self.hi = float(hi)

    @property
    def _width(self) -> float:
        return self.hi - self.lo

    def forward(self, u: NDArray[np.float64]) -> NDArray[np.float64]:
        """Map R onto (lo, hi)."""
        s = 1.0 / (1.0 + np.exp(-np.asarray(u, dtype=np.float64)))
        return np.asarray(self.lo + self._width * s, dtype=np.float64)

    def inverse(self, x: NDArray[np.float64]) -> NDArray[np.float64]:
        """Map (lo, hi) onto R."""
        s = (np.asarray(x, dtype=np.float64) - self.lo) / self._width
        return np.asarray(np.log(s) - np.log1p(-s), dtype=np.float64)

    def dforward(self, u: NDArray[np.float64]) -> NDArray[np.float64]:
        """Derivative of the scaled logistic."""
        s = 1.0 / (1.0 + np.exp(-np.asarray(u, dtype=np.float64)))
        return np.asarray(self._width * s * (1.0 - s), dtype=np.float64)

    def log_abs_det_jacobian(self, u: NDArray[np.float64]) -> NDArray[np.float64]:
        """log(width) + log s + log(1 - s), computed stably."""
        arr = np.asarray(u, dtype=np.float64)
        log_s = -np.logaddexp(0.0, -arr)
        log_1ms = -np.logaddexp(0.0, arr)
        return np.asarray(np.log(self._width) + log_s + log_1ms, dtype=np.float64)


def delta_method_cov(
    dforward: NDArray[np.float64], cov_unconstrained: NDArray[np.float64]
) -> NDArray[np.float64]:
    """Push a covariance from unconstrained to natural coordinates.

    The transforms are elementwise, so the Jacobian is diagonal and the
    push-through reduces to scaling rows and columns.

    This is first order. It degrades for parameters near a diagnostic limit,
    where the transform's curvature is not negligible; callers must surface
    that via the DIAGNOSTIC_LIMIT outcome.

    Args:
        dforward: Derivative of the forward map at the estimate, shape (..., p).
        cov_unconstrained: Covariance in unconstrained coordinates, (..., p, p).

    Returns:
        Covariance in natural units, same shape as `cov_unconstrained`.
    """
    d = np.asarray(dforward, dtype=np.float64)
    cov = np.asarray(cov_unconstrained, dtype=np.float64)
    return np.asarray(d[..., :, None] * cov * d[..., None, :], dtype=np.float64)
