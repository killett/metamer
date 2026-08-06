"""Matern nu=1/2, the Ornstein-Uhlenbeck process (continuous-time AR(1))."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from metamer.core.capability import CostClass, EngineId, GradientMode, Objective
from metamer.core.params import ParamSpec
from metamer.core.registry import kernel_registry
from metamer.core.transforms import Log


@kernel_registry.register("matern12")
class Matern12:
    """OU process with marginal standard deviation sigma and timescale rho.

    The governing SDE, stated in full because it is the one assumption shared
    between this implementation and the expm/Lyapunov reference that checks it
    (an error in the mapping would appear on both sides and cancel, so it is
    verified by re-derivation, not by that test):

        dx = -(1 / rho) x dt + sigma sqrt(2 / rho) dW,

    i.e. drift A = -1/rho and diffusion L = sigma sqrt(2/rho), with dW standard
    Brownian motion. Here `rho` is a timescale (units of time, larger = longer
    memory) and `sigma` is the marginal standard deviation, so that:

        P_inf = sigma^2                      (solves A P + P A' + L L' = 0,
                                              i.e. -2 P / rho + 2 sigma^2 / rho = 0)
        F(dt) = exp(-dt / rho)
        Q(dt) = P_inf - F P_inf F' = sigma^2 (1 - exp(-2 dt / rho))
        k(tau) = sigma^2 exp(-|tau| / rho)

    Q is written in that factored form rather than as the literal difference
    P_inf - F P_inf F'. At d = 1 the two agree bit for bit -- including at
    dt = 0, where both give exactly zero, checked numerically with F analytic
    and with F from `scipy.linalg.expm` -- so the choice buys nothing here and
    is made for the d > 1 families to follow, where the difference form is a
    sum of products and does lose cancellation. What matters at every d is
    that dt = 0 must yield F = I and Q = 0 exactly: repeated timestamps are
    ordinary in real records, and any floor on dt or jitter added to Q for
    Cholesky stability injects process noise the model does not contain.

    State-space: d = 1, H = [1], no measurement-noise contribution.
    """

    kind = "matern12"
    state_dim = 1
    ordering_param = "rho"
    engine_costs = {
        EngineId.KALMAN: CostClass.LINEAR,
        EngineId.WHITTLE: CostClass.NLOGN,
        EngineId.TOEPLITZ: CostClass.CUBIC,
        EngineId.CELERITE2: CostClass.LINEAR,
    }
    gradient_modes = {
        Objective.ML: GradientMode.FINITE_DIFFERENCE,
        Objective.REML: GradientMode.FINITE_DIFFERENCE,
    }

    def param_specs(self) -> dict[str, ParamSpec]:
        """Return sigma and rho, both log-transformed."""
        return {
            "sigma": ParamSpec(
                name="sigma",
                default=1.0,
                transform=Log(),
                bounds=(0.0, np.inf),
                diagnostic_limits=(1e-8, 1e8),
            ),
            "rho": ParamSpec(
                name="rho",
                default=1.0,
                transform=Log(),
                bounds=(0.0, np.inf),
                diagnostic_limits=(1e-6, 1e6),
                unit="time",
            ),
        }

    def transition(self, theta: NDArray[np.float64], dt: float) -> NDArray[np.float64]:
        """Return exp(-dt/rho) as a (B, 1, 1) array.

        Args:
            theta: Parameters, shape (B, 2), columns (sigma, rho).
            dt: Step length.

        Returns:
            F, shape (B, 1, 1).
        """
        rho = np.asarray(theta, dtype=np.float64)[:, 1]
        return np.asarray(np.exp(-float(dt) / rho)[:, None, None], dtype=np.float64)

    def stationary_cov(self, theta: NDArray[np.float64]) -> NDArray[np.float64]:
        """Return sigma^2 as a (B, 1, 1) array.

        Args:
            theta: Parameters, shape (B, 2), columns (sigma, rho).

        Returns:
            P_inf, shape (B, 1, 1).
        """
        sigma = np.asarray(theta, dtype=np.float64)[:, 0]
        return np.asarray((sigma**2)[:, None, None], dtype=np.float64)

    def process_noise(
        self, theta: NDArray[np.float64], dt: float
    ) -> NDArray[np.float64]:
        """Return sigma^2 (1 - exp(-2 dt / rho)) as a (B, 1, 1) array.

        Args:
            theta: Parameters, shape (B, 2), columns (sigma, rho).
            dt: Step length. At dt = 0 this is exactly zero.

        Returns:
            Q, shape (B, 1, 1).
        """
        arr = np.asarray(theta, dtype=np.float64)
        sigma, rho = arr[:, 0], arr[:, 1]
        noise = sigma**2 * (1.0 - np.exp(-2.0 * float(dt) / rho))
        return np.asarray(noise[:, None, None], dtype=np.float64)

    def observation(self, theta: NDArray[np.float64]) -> NDArray[np.float64]:
        """Return H = [1], shape (B, 1).

        Args:
            theta: Parameters, shape (B, 2). Only its batch size is used.

        Returns:
            The observation row, shape (B, 1).
        """
        return np.ones((np.shape(theta)[0], 1), dtype=np.float64)

    def measurement_variance(self, theta: NDArray[np.float64]) -> NDArray[np.float64]:
        """Return zeros -- this family contributes no measurement noise.

        Args:
            theta: Parameters, shape (B, 2). Only its batch size is used.

        Returns:
            Zeros, shape (B,).
        """
        return np.zeros(np.shape(theta)[0], dtype=np.float64)

    def acvf(
        self, theta: NDArray[np.float64], lags: NDArray[np.float64]
    ) -> NDArray[np.float64]:
        """Return sigma^2 exp(-|tau| / rho), shape (B, n_lags).

        Args:
            theta: Parameters, shape (B, 2), columns (sigma, rho).
            lags: Lags tau at which to evaluate, shape (n_lags,).

        Returns:
            The autocovariance, shape (B, n_lags).
        """
        arr = np.asarray(theta, dtype=np.float64)
        sigma, rho = arr[:, 0][:, None], arr[:, 1][:, None]
        tau = np.abs(np.asarray(lags, dtype=np.float64))[None, :]
        return np.asarray(sigma**2 * np.exp(-tau / rho), dtype=np.float64)
