"""White measurement noise: no state, contributes only to R."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from metamer.core.capability import CostClass, EngineId, GradientMode, Objective
from metamer.core.params import ParamSpec
from metamer.core.registry import kernel_registry
from metamer.core.transforms import Log


@kernel_registry.register("white")
class White:
    """Independent Gaussian measurement noise of standard deviation sigma.

    There is no SDE here and no state: white noise is d = 0. It enters the
    model only through the measurement equation, as R += sigma^2. That is why
    `white + matern12 + matern32` has state dimension 3 and not 4.

    ACVF: k(0) = sigma^2, k(tau) = 0 for tau != 0.
    """

    kind = "white"
    state_dim = 0
    engine_costs = {
        EngineId.KALMAN: CostClass.LINEAR,
        EngineId.WHITTLE: CostClass.NLOGN,
        EngineId.TOEPLITZ: CostClass.CUBIC,
        EngineId.CELERITE2: CostClass.LINEAR,
    }
    # Declared FD in Task 4 because no analytic derivative is implemented yet.
    # Task 12 adds one for matern12 only; a family must never advertise ANALYTIC
    # without shipping the derivatives, or the composite resolution silently lies.
    gradient_modes = {
        Objective.ML: GradientMode.FINITE_DIFFERENCE,
        Objective.REML: GradientMode.FINITE_DIFFERENCE,
    }

    def param_specs(self) -> dict[str, ParamSpec]:
        """Return the single scale parameter."""
        return {
            "sigma": ParamSpec(
                name="sigma",
                default=1.0,
                transform=Log(),
                bounds=(0.0, np.inf),
                diagnostic_limits=(1e-8, 1e8),
            )
        }

    def transition(self, theta: NDArray[np.float64], dt: float) -> NDArray[np.float64]:
        """Return an empty (B, 0, 0) array -- white noise has no state.

        Args:
            theta: Parameters, shape (B, 1).
            dt: Step length. Unused: there is no state to advance.

        Returns:
            Zeros of shape (B, 0, 0).
        """
        return np.zeros((np.shape(theta)[0], 0, 0), dtype=np.float64)

    def process_noise(
        self, theta: NDArray[np.float64], dt: float
    ) -> NDArray[np.float64]:
        """Return an empty (B, 0, 0) array.

        Args:
            theta: Parameters, shape (B, 1).
            dt: Step length. Unused: there is no state to perturb.

        Returns:
            Zeros of shape (B, 0, 0).
        """
        return np.zeros((np.shape(theta)[0], 0, 0), dtype=np.float64)

    def stationary_cov(self, theta: NDArray[np.float64]) -> NDArray[np.float64]:
        """Return an empty (B, 0, 0) array.

        Args:
            theta: Parameters, shape (B, 1).

        Returns:
            Zeros of shape (B, 0, 0).
        """
        return np.zeros((np.shape(theta)[0], 0, 0), dtype=np.float64)

    def observation(self, theta: NDArray[np.float64]) -> NDArray[np.float64]:
        """Return an empty (B, 0) observation row.

        Args:
            theta: Parameters, shape (B, 1).

        Returns:
            Zeros of shape (B, 0).
        """
        return np.zeros((np.shape(theta)[0], 0), dtype=np.float64)

    def measurement_variance(self, theta: NDArray[np.float64]) -> NDArray[np.float64]:
        """Return sigma^2, shape (B,).

        Args:
            theta: Parameters, shape (B, 1), column 0 being sigma.

        Returns:
            The per-series measurement variance, shape (B,).
        """
        arr = np.asarray(theta, dtype=np.float64)
        return np.asarray(arr[:, 0] ** 2, dtype=np.float64)

    def acvf(
        self, theta: NDArray[np.float64], lags: NDArray[np.float64]
    ) -> NDArray[np.float64]:
        """Return sigma^2 at lag 0 and zero elsewhere.

        Args:
            theta: Parameters, shape (B, 1), column 0 being sigma.
            lags: Lags tau at which to evaluate, shape (n_lags,).

        Returns:
            The autocovariance, shape (B, n_lags).
        """
        arr = np.asarray(theta, dtype=np.float64)
        tau = np.asarray(lags, dtype=np.float64)
        out = np.zeros((arr.shape[0], tau.size), dtype=np.float64)
        out[:, tau == 0.0] = (arr[:, 0] ** 2)[:, None]
        return out
