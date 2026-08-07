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

    Q is written in that factored form, evaluated with `-expm1`, rather than
    as the literal difference P_inf - F P_inf F'. The two agree exactly at
    dt = 0 -- where F is exactly I, so the subtraction is exact at any state
    dimension, checked numerically with F analytic and with F from
    `scipy.linalg.expm`. The difference form's weakness is small *nonzero*
    dt, at every d: F is then near I, P_inf - F P_inf F' is a difference of
    nearly equal quantities, and the relative accuracy of Q collapses. Q is a
    variance the filter divides by, so relative accuracy is what matters.

    Two separate requirements, both load-bearing:
      * dt = 0 must give F = I and Q = 0 exactly. Repeated timestamps are
        ordinary in real records, and any floor on dt or jitter added to Q for
        Cholesky stability injects process noise the model does not contain.
      * dt > 0 must give Q > 0 with full relative precision, however small
        dt/rho is -- see the `-expm1` note in `process_noise`.

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
        # ANALYTIC under ML only. The envelope theorem removes the
        # d beta_hat / d theta term exactly for the concentrated ML objective;
        # REML's -0.5 log|X' Sigma^-1 X| penalty is not covered by that
        # argument, so its analytic gradient is strictly more work and is not
        # claimed here. Design doc sections 8.1 and 8.2.
        Objective.ML: GradientMode.ANALYTIC,
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
        # -expm1(-x), never 1 - exp(-x). For small x = 2 dt / rho, exp(-x) is
        # near 1 and the subtraction is catastrophic cancellation: measured
        # relative error 8.3e-8 at x = 2e-10 and 8.0e-4 at x = 2e-14, and
        # below x ~ 5e-17 exp(-x) rounds to exactly 1.0 so Q flushes to zero
        # -- zero process noise on a nonzero step. That regime is reachable:
        # rho's diagnostic limit is 1e6 and the caller picks the time units.
        noise = sigma**2 * -np.expm1(-2.0 * float(dt) / rho)
        return np.asarray(noise[:, None, None], dtype=np.float64)

    def dtransition(self, theta: NDArray[np.float64], dt: float) -> NDArray[np.float64]:
        """Return dF/dtheta, shape (B, 2, 1, 1).

        `F = exp(-dt/rho)`, so `dF/dsigma = 0` and

            dF/drho = (dt / rho^2) exp(-dt / rho),

        which is POSITIVE: a longer timescale means less decay per step. At
        `dt = 0` it is exactly zero, matching this family's requirement that a
        repeated timestamp contribute nothing -- there is no floor on `dt` and
        no epsilon, because either would make this small-but-nonzero and hand
        the optimizer a gradient component for a step carrying no information.

        Args:
            theta: Parameters, shape (B, 2), columns (sigma, rho).
            dt: Step length.

        Returns:
            dF/dtheta, shape (B, 2, 1, 1). The `sigma` slice is exactly zero.
        """
        arr = np.asarray(theta, dtype=np.float64)
        rho = arr[:, 1]
        out = np.zeros((arr.shape[0], 2, 1, 1), dtype=np.float64)
        out[:, 1, 0, 0] = float(dt) / rho**2 * np.exp(-float(dt) / rho)
        return out

    def dstationary_cov(self, theta: NDArray[np.float64]) -> NDArray[np.float64]:
        """Return dP_inf/dtheta, shape (B, 2, 1, 1).

        `P_inf = sigma^2` with `sigma` the marginal STANDARD DEVIATION, so
        `dP_inf/dsigma = 2 sigma` and `dP_inf/drho = 0`. Reading `sigma` as a
        variance gives `1` instead, and the two agree only at `sigma = 0.5`.

        Args:
            theta: Parameters, shape (B, 2), columns (sigma, rho).

        Returns:
            dP_inf/dtheta, shape (B, 2, 1, 1). The `rho` slice is exactly zero.
        """
        arr = np.asarray(theta, dtype=np.float64)
        out = np.zeros((arr.shape[0], 2, 1, 1), dtype=np.float64)
        out[:, 0, 0, 0] = 2.0 * arr[:, 0]
        return out

    def dprocess_noise(
        self, theta: NDArray[np.float64], dt: float
    ) -> NDArray[np.float64]:
        """Return dQ/dtheta, shape (B, 2, 1, 1).

        From `Q = sigma^2 (1 - exp(-2 dt / rho))`:

            dQ/dsigma = 2 sigma (1 - exp(-2 dt / rho))
            dQ/drho   = -sigma^2 exp(-2 dt / rho) (2 dt / rho^2)

        `dQ/drho` is NEGATIVE -- a longer timescale injects less new variance
        per step -- and dropping the inner minus sign from the chain rule
        flips it while leaving the magnitude right.

        **`dQ/dsigma` uses `-expm1`, exactly as `process_noise` does**, and for
        exactly the same reason: `1 - exp(-x)` at small `x = 2 dt / rho` is
        catastrophic cancellation. Measured relative error of the naive form
        against `-expm1`: 1.09e-10 at `x = 2e-7`, 8.28e-08 at 2e-10, 7.99e-04
        at 2e-14. A derivative written from the algebra rather than from
        `process_noise`'s docstring reintroduces it, and at the ordinary
        fixture ratio `x = 0.8` the two forms agree to 1.2e-16, so nothing
        notices.

        Args:
            theta: Parameters, shape (B, 2), columns (sigma, rho).
            dt: Step length. At `dt = 0` every entry is exactly zero.

        Returns:
            dQ/dtheta, shape (B, 2, 1, 1).
        """
        arr = np.asarray(theta, dtype=np.float64)
        sigma, rho = arr[:, 0], arr[:, 1]
        ratio = 2.0 * float(dt) / rho
        out = np.zeros((arr.shape[0], 2, 1, 1), dtype=np.float64)
        out[:, 0, 0, 0] = 2.0 * sigma * -np.expm1(-ratio)
        out[:, 1, 0, 0] = -(sigma**2) * np.exp(-ratio) * (2.0 * float(dt) / rho**2)
        return out

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
