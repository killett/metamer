"""Matern nu=3/2: d=2, repeated real root, Jordan-form closed solution.

The drift matrix has eigenvalue -lambda with multiplicity 2 and is therefore
defective. Its matrix exponential carries a t*exp(-lambda t) term that no
eigendecomposition can produce, which is why this family is a separate analytic
construction and NOT an instance of the general root-based CARMA path.
"""

from __future__ import annotations

from math import factorial

import numpy as np
from numpy.typing import NDArray

from metamer.core.capability import CostClass, EngineId, GradientMode, Objective
from metamer.core.params import ParamSpec
from metamer.core.registry import kernel_registry
from metamer.core.transforms import Log

_SQRT3 = np.sqrt(3.0)

Q_SERIES_CROSSOVER = 1.0
"""Value of u = 2 lambda dt below which Q is evaluated by its Maclaurin series.

Chosen by measuring both formulations against a 60-digit Decimal evaluation of
the same closed forms (see `tests/oracles.matern32_process_noise_exact`). The
direct form's relative error behaves as about 4.6e-16 / u^3 for Q_11 -- 4.6e-13
at u = 0.1, 1.9e-15 at u = 0.5, 3.9e-16 at u = 1 -- while the truncated series
is accurate to 3e-16 up to u = 1 and then degrades (1.5e-14 at u = 1.5 with
these term counts). Worst-case relative error of the piecewise rule over
u in [1e-14, 30], measured on a 6000-point log grid:

    crossover u* | worst Q_11 | worst Q_22
    -------------+------------+-----------
        0.25     |   1.0e-13  |   3.6e-16
        0.50     |   1.0e-14  |   1.9e-16
        0.75     |   3.9e-15  |   2.8e-16
        1.00     |   2.6e-15  |   3.5e-16   <- chosen
        1.50     |   7.6e-16  |   2.3e-14

u* = 1 is the minimum of the larger of the two columns. In physical terms
u = 2 sqrt(3) dt / rho, so the series branch covers every step shorter than
rho / (2 sqrt 3) = 0.289 rho -- i.e. most real sampling of a resolved process.
"""

_Q_SATURATION_U = 60.0
"""Above this u, exp(-u) (1 +- u + u^2/2) < 2e-23, below half an ulp of 1.

The direct branch clamps u here so that a pathologically large dt/rho cannot
form inf * 0 = nan in `exp(-u) * u**2`. Clamping is exact in float64: both
bracketed factors are already exactly 1.0 at u = 60, so the clamped and
unclamped results are bit-identical wherever the clamp is active.
"""


def _series_coefficients(kind: str, n_max: int) -> tuple[float, ...]:
    """Return Maclaurin coefficients for Q's cancelling factors, highest power first.

    Both factors come from the same convolution of exp(-u) with a quadratic:

        g1(u) = 1 - e^-u (1 + u + u^2/2) = sum_{n>=3} (-1)^{n+1} (n-1)(n-2) u^n / (2 n!)
        g2(u) = 1 - e^-u (1 - u + u^2/2) = sum_{n>=1} (-1)^{n+1} (n^2+n+2) u^n / (2 n!)

    Derivation, done once by hand and recorded here: writing e^-u = sum_k
    (-1)^k u^k / k! and multiplying by the quadratic p(u) = 1 +- u + u^2/2, the
    coefficient of u^n in the product is
    (-1)^n [1/n! -/+ 1/(n-1)! + 1/(2 (n-2)!)], whose bracket over a common
    denominator n! is (n^2 - 3n + 2)/2 = (n-1)(n-2)/2 for g1 and
    (n^2 + n + 2)/2 for g2. Subtracting from 1 flips the sign and kills n = 0.
    The (n-1)(n-2) factor is why g1 starts at u^3: its n = 1 and n = 2
    coefficients vanish identically, which is the cubic behaviour that makes the
    difference form lose three times the digits the nu=1/2 case lost.

    Leading terms, for cross-checking against the docstrings above:
        g1 = u^3/6 - u^4/8 + u^5/20 - u^6/72 + ...
        g2 = 2u - 2u^2 + 7u^3/6 - 11u^4/24 + ...

    Args:
        kind: Either "g1" or "g2".
        n_max: Highest power of u retained.

    Returns:
        Coefficients of u^k for k = n_max - lowest down to 0, where `lowest` is
        3 for g1 and 1 for g2, ordered highest power first for Horner
        evaluation of the factored-out polynomial.

    Raises:
        ValueError: If `kind` is not "g1" or "g2".
    """
    if kind == "g1":
        lowest = 3
        numerator = {n: (n - 1) * (n - 2) for n in range(lowest, n_max + 1)}
    elif kind == "g2":
        lowest = 1
        numerator = {n: n * n + n + 2 for n in range(lowest, n_max + 1)}
    else:
        raise ValueError(f"unknown series {kind!r}")
    return tuple(
        (-1.0) ** (n + 1) * numerator[n] / (2.0 * factorial(n))
        for n in range(n_max, lowest - 1, -1)
    )


_G1_COEFFS = _series_coefficients("g1", 22)
_G2_COEFFS = _series_coefficients("g2", 20)


def _horner(coeffs: tuple[float, ...], u: NDArray[np.float64]) -> NDArray[np.float64]:
    """Evaluate a polynomial given highest-power-first coefficients."""
    acc = np.zeros_like(u)
    for c in coeffs:
        acc = acc * u + c
    return acc


@kernel_registry.register("matern32")
class Matern32:
    """Matern nu=3/2 with marginal standard deviation sigma and timescale rho.

    The governing SDE, stated in full because `families/base.py` requires it:
    the SDE-to-matrix mapping is the one assumption shared between this
    implementation and the expm/Lyapunov references that check it, so an error
    in the mapping would appear on both sides and cancel. It is verified by
    re-derivation, not by those tests.

        d[x1]   [   0     1 ] [x1]       [       0        ]
        d[x2] = [-lam^2 -2lam] [x2] dt + [ 2 sigma lam^{3/2} ] dW,

    i.e. drift A = [[0, 1], [-lam^2, -2 lam]] and diffusion
    L = [0, 2 sigma lam^{3/2}]', with lam = sqrt(3) / rho and dW standard
    Brownian motion. The state is (position, velocity); `rho` is a timescale
    (larger = longer memory) and `sigma` is the marginal standard deviation, the
    same convention as Matern12. It follows that:

        P_inf = diag(sigma^2, sigma^2 lam^2)   (solves A P + P A' + L L' = 0)
        F(dt) = exp(-lam dt) (I + dt (A + lam I))
        k(tau) = sigma^2 (1 + lam|tau|) exp(-lam|tau|)

    with P_inf[0, 0] = k(0) = sigma^2, so sigma keeps its meaning across
    families. Cov(x1, x2) = +k'(0) = 0 (the identity is +k'(0), not -k'(0); the
    value is zero either way because k is even and differentiable at 0), and
    Var(x2) = -k''(0) = sigma^2 lam^2.

    THE DEFECT IS THE POINT. A has the single eigenvalue -lam with algebraic
    multiplicity 2 and a one-dimensional eigenspace, so there is no
    eigendecomposition. Writing N = A + lam I gives N^2 = 0 exactly, so the
    matrix exponential terminates after two terms:

        exp(A dt) = exp(-lam dt) exp(N dt) = exp(-lam dt) (I + N dt).

    The dt exp(-lam dt) term that carries is precisely what a numerical
    eigendecomposition drops. `statespace.eigen_transition` refuses this drift
    (measured cond(V) = 2.03e8 at rho = 1); it is that guard's calibration case.

    State-space: d = 2, H = [1, 0], no measurement-noise contribution.

    CAVEAT ON `engine_costs`. KALMAN is exact here. The celerite2/n2 route
    represents this kernel only approximately: those solvers handle sums of
    (complex) exponentials, and the repeated root has to be split by a small
    perturbation first. The cost class is declared because the family is not
    *eliminated* there -- `intersect_engine_costs` drops any engine a single
    term fails to declare -- but an engine-selection layer that cares about
    exactness must treat celerite2 for this family as approximate.
    """

    kind = "matern32"
    state_dim = 2
    ordering_param = "rho"
    engine_costs = {
        EngineId.KALMAN: CostClass.LINEAR,
        EngineId.WHITTLE: CostClass.NLOGN,
        EngineId.TOEPLITZ: CostClass.CUBIC,
        EngineId.CELERITE2: CostClass.LINEAR,
    }
    # Declared FD for the same reason as White and Matern12: no analytic
    # derivative is implemented yet, and a family must never advertise ANALYTIC
    # without shipping the derivatives.
    gradient_modes = {
        Objective.ML: GradientMode.FINITE_DIFFERENCE,
        Objective.REML: GradientMode.FINITE_DIFFERENCE,
    }

    def param_specs(self) -> dict[str, ParamSpec]:
        """Return sigma and rho, both log-transformed, in theta-column order."""
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

    @staticmethod
    def _lam(theta: NDArray[np.float64]) -> NDArray[np.float64]:
        """Return lambda = sqrt(3) / rho, shape (B,)."""
        return np.asarray(
            _SQRT3 / np.asarray(theta, dtype=np.float64)[:, 1], dtype=np.float64
        )

    def transition(self, theta: NDArray[np.float64], dt: float) -> NDArray[np.float64]:
        """Return the Jordan-form F = exp(-lam dt) (I + dt (A + lam I)).

        Args:
            theta: Parameters, shape (B, 2), columns (sigma, rho).
            dt: Step length. At dt = 0 this is exactly the identity, because
                every off-diagonal entry carries a factor dt and the diagonal
                entries are 1 +- lam*0 times exp(0).

        Returns:
            F, shape (B, 2, 2).
        """
        lam = self._lam(theta)
        t = float(dt)
        decay = np.exp(-lam * t)
        out = np.empty((lam.size, 2, 2), dtype=np.float64)
        out[:, 0, 0] = 1.0 + lam * t
        out[:, 0, 1] = t
        out[:, 1, 0] = -(lam**2) * t
        out[:, 1, 1] = 1.0 - lam * t
        return np.asarray(out * decay[:, None, None], dtype=np.float64)

    def stationary_cov(self, theta: NDArray[np.float64]) -> NDArray[np.float64]:
        """Return diag(sigma^2, sigma^2 lam^2).

        Cov(x1, x2) = +k'(0) = 0 and Var(x2) = -k''(0) = sigma^2 lam^2, so the
        stationary covariance is exactly diagonal -- position and velocity are
        uncorrelated at a single instant even though the process is smooth.

        Args:
            theta: Parameters, shape (B, 2), columns (sigma, rho).

        Returns:
            P_inf, shape (B, 2, 2).
        """
        arr = np.asarray(theta, dtype=np.float64)
        sigma = arr[:, 0]
        lam = self._lam(arr)
        out = np.zeros((sigma.size, 2, 2), dtype=np.float64)
        out[:, 0, 0] = sigma**2
        out[:, 1, 1] = (sigma * lam) ** 2
        return out

    def process_noise(
        self, theta: NDArray[np.float64], dt: float
    ) -> NDArray[np.float64]:
        """Return Q, evaluated so that every entry keeps full relative precision.

        Q = P_inf - F P_inf F' is exact in exact arithmetic and unusable in
        float64. Writing u = 2 lam dt, the three distinct entries are

            Q_11 = sigma^2 [1 - e^-u (1 + u + u^2/2)]  = sigma^2 g1(u)
            Q_22 = sigma^2 lam^2 [1 - e^-u (1 - u + u^2/2)] = sigma^2 lam^2 g2(u)
            Q_12 = Q_21 = 2 sigma^2 lam^3 dt^2 e^-u.

        Q_12 is safe as written: P_inf[0, 1] is zero, so nothing is subtracted
        from it. The other two are not. g1(u) = u^3/6 - u^4/8 + ... is CUBIC in
        u while the quantities differenced to reach it are O(1), so the literal
        difference loses about three times the digits the nu=1/2 case lost --
        measured at sigma = rho = 1: 4.0e-5 relative error at dt = 1e-4, 3.9e-2
        at dt = 1e-5, exactly 0.0 at dt = 3e-6, and -2.2e-16 at dt = 1e-6, i.e.
        a Q whose smallest eigenvalue is -2.3e-16. That is a Cholesky failure
        inside the Kalman filter, not a rounding detail. g2(u) = 2u - 2u^2 + ...
        is the linear cancellation nu=1/2 already fixed.

        `expm1` alone does NOT fix g1: -expm1(-u) - e^-u (u + u^2/2) still
        cancels two O(u) quantities against an O(u^3) answer, measuring 4.7e-2
        relative error at u = 1e-7. Hence the series branch, taken for
        u < `Q_SERIES_CROSSOVER` = 1.0; see that constant's docstring for the
        measured error table that fixes the crossover, and
        `_series_coefficients` for the derivation of the coefficients.

        Both branches are evaluated unconditionally and selected with
        `np.where`, so the series argument is zeroed outside its branch to keep
        u**22 from overflowing, and the direct branch's u is clamped at
        `_Q_SATURATION_U`.

        Args:
            theta: Parameters, shape (B, 2), columns (sigma, rho).
            dt: Step length. At dt = 0 this is exactly zero: u is exactly 0, the
                series branch is selected, and every term carries a factor u.

        Returns:
            Q, shape (B, 2, 2), exactly symmetric by construction.
        """
        arr = np.asarray(theta, dtype=np.float64)
        sigma = arr[:, 0]
        lam = self._lam(arr)
        t = float(dt)
        u = 2.0 * lam * t

        small = u < Q_SERIES_CROSSOVER
        u_series = np.where(small, u, 0.0)
        u_direct = np.minimum(u, _Q_SATURATION_U)
        decay = np.exp(-u_direct)

        g1 = np.where(
            small,
            u_series**3 * _horner(_G1_COEFFS, u_series),
            1.0 - decay * (1.0 + u_direct + 0.5 * u_direct**2),
        )
        g2 = np.where(
            small,
            u_series * _horner(_G2_COEFFS, u_series),
            1.0 - decay * (1.0 - u_direct + 0.5 * u_direct**2),
        )

        var = sigma**2
        out = np.empty((sigma.size, 2, 2), dtype=np.float64)
        out[:, 0, 0] = var * g1
        out[:, 1, 1] = var * lam**2 * g2
        off = 2.0 * var * lam**3 * t**2 * np.exp(-u)
        out[:, 0, 1] = off
        out[:, 1, 0] = off
        return out

    def observation(self, theta: NDArray[np.float64]) -> NDArray[np.float64]:
        """Return H = [1, 0], shape (B, 2).

        The modelled signal is the state's position component; the velocity is
        latent. Observing it too would be a different process entirely.

        Args:
            theta: Parameters, shape (B, 2). Only its batch size is used.

        Returns:
            The observation row, shape (B, 2).
        """
        out = np.zeros((np.shape(theta)[0], 2), dtype=np.float64)
        out[:, 0] = 1.0
        return out

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
        """Return sigma^2 (1 + lam|tau|) exp(-lam|tau|), shape (B, n_lags).

        Args:
            theta: Parameters, shape (B, 2), columns (sigma, rho).
            lags: Lags tau at which to evaluate, shape (n_lags,).

        Returns:
            The autocovariance, shape (B, n_lags).
        """
        arr = np.asarray(theta, dtype=np.float64)
        sigma = arr[:, 0][:, None]
        lam = self._lam(arr)[:, None]
        tau = np.abs(np.asarray(lags, dtype=np.float64))[None, :]
        return np.asarray(
            sigma**2 * (1.0 + lam * tau) * np.exp(-lam * tau), dtype=np.float64
        )
