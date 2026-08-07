"""The Family protocol: analytic state-space construction per kernel family.

Every family supplies closed-form F, Q, P_inf and an analytic autocovariance.
The general expm/Lyapunov route exists only as a test reference and as the
numerical fallback for near-degenerate roots; if it runs often in production,
something is wrong.

Every family is specified by a linear time-invariant SDE

    dx = A x dt + L dW,

from which F = expm(A dt), P_inf solves A P + P A' + L L' = 0, and
Q = P_inf - F P_inf F'. Each family states its own A and L explicitly in its
class docstring, because that SDE-to-matrix mapping is the one assumption the
expm/Lyapunov reference tests share with the code they check: a conceptual
error in the mapping would appear on both sides and cancel. The mapping is
therefore verified by re-derivation from the SDE, not by those tests.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np
from numpy.typing import NDArray

from metamer.core.capability import CostClass, EngineId, GradientMode, Objective
from metamer.core.params import ParamSpec

Batch = NDArray[np.float64]


@runtime_checkable
class Family(Protocol):
    """A kernel family, evaluated batched over the leading axis of `theta`."""

    kind: str
    state_dim: int
    engine_costs: dict[EngineId, CostClass]
    gradient_modes: dict[Objective, GradientMode]

    def param_specs(self) -> dict[str, ParamSpec]:
        """Return this family's parameter specifications, in canonical order."""
        ...

    def transition(self, theta: Batch, dt: float) -> Batch:
        """Return F = expm(A dt), shape (B, d, d)."""
        ...

    def process_noise(self, theta: Batch, dt: float) -> Batch:
        """Return Q = P_inf - F P_inf F', shape (B, d, d)."""
        ...

    def stationary_cov(self, theta: Batch) -> Batch:
        """Return P_inf, shape (B, d, d)."""
        ...

    def observation(self, theta: Batch) -> Batch:
        """Return the observation row H, shape (B, d)."""
        ...

    def measurement_variance(self, theta: Batch) -> Batch:
        """Return this family's contribution to R, shape (B,)."""
        ...

    def acvf(self, theta: Batch, lags: NDArray[np.float64]) -> Batch:
        """Return the analytic autocovariance at `lags`, shape (B, n_lags)."""
        ...


@runtime_checkable
class DifferentiableFamily(Protocol):
    """A family that also supplies analytic derivatives of F, Q and P_inf.

    THE GRADIENT HOOK IS PART OF THE PROTOCOL FROM DAY ONE, AND DELIBERATELY SO.
    Design doc §8.2 calls it non-retrofittable: a kernel protocol without a
    derivative slot forces every out-of-tree family to be rewritten when
    forward-mode lands, and the registry is extensible precisely so that does
    not happen. It is a SEPARATE protocol rather than optional methods on
    `Family` because analytic derivatives are genuinely optional — Matérn
    ν=3/2 ships none in Phase 1 — and a `Family` that had to stub three
    methods to say "no" would make declining costlier than complying.

    Each derivative is shaped `(B, p, d, d)`: batch, then one slice per
    parameter in `param_specs()` order, then the matrix itself. Parameters the
    quantity does not depend on give exactly zero, not a small number.

    Declaring `gradient_modes[objective] = ANALYTIC` without satisfying this
    protocol is refused by `gradients.resolve_gradient_mode`. The failure it
    prevents is a composite reporting ANALYTIC while finite differences
    silently run — the inverse of a silent fallback, and just as invisible.
    """

    def dtransition(self, theta: Batch, dt: float) -> Batch:
        """Return dF/dtheta, shape (B, p, d, d)."""
        ...

    def dprocess_noise(self, theta: Batch, dt: float) -> Batch:
        """Return dQ/dtheta, shape (B, p, d, d)."""
        ...

    def dstationary_cov(self, theta: Batch) -> Batch:
        """Return dP_inf/dtheta, shape (B, p, d, d)."""
        ...


def supports_analytic_gradient(family: object) -> bool:
    """Whether `family` implements the analytic-derivative protocol.

    Structural rather than nominal, so a third-party kernel needs no import
    from this package to qualify — the registry is extensible by entry point,
    and requiring a base class would make that a lie.

    Args:
        family: A family instance, or anything else.

    Returns:
        True if all three derivative methods are present and callable.
    """
    return isinstance(family, DifferentiableFamily)
