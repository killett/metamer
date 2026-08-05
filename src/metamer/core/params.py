"""Parameter specifications: the coordinates the optimizer searches in."""

from dataclasses import dataclass

import numpy as np

from metamer.core.transforms import Bijector


@dataclass(frozen=True)
class ParamSpec:
    """One scalar parameter of a kernel term.

    Attributes:
        name: Parameter name, unique within its term.
        default: Starting value in natural units.
        transform: Bijection to unconstrained R.
        bounds: Mathematical domain, enforced by `transform`. Never clipped
            against directly.
        diagnostic_limits: Reporting limits. Reaching one is an outcome, not a
            clamp: it means the fit ran away and the delta-method uncertainty
            for this parameter is unreliable.
        fixed: If True the parameter is frozen and excluded from `n_free`.
        unit: Optional unit string, recorded in output metadata.
    """

    name: str
    default: float
    transform: Bijector
    bounds: tuple[float, float]
    diagnostic_limits: tuple[float, float]
    fixed: bool = False
    unit: str | None = None

    def __post_init__(self) -> None:
        """Validate that `default` lies within `bounds` and limits are ordered.

        Raises:
            ValueError: If `default` is outside `bounds`, or if
                `diagnostic_limits` is not strictly increasing.
        """
        lo, hi = self.bounds
        if not lo <= self.default <= hi:
            raise ValueError(
                f"{self.name}: default {self.default} outside bounds {self.bounds}"
            )
        dlo, dhi = self.diagnostic_limits
        if not dhi > dlo:
            raise ValueError(
                f"{self.name}: diagnostic_limits must be increasing, got "
                f"{self.diagnostic_limits}"
            )

    def at_diagnostic_limit(self, value: float) -> bool:
        """Report whether a fitted value has reached a diagnostic limit.

        Args:
            value: Fitted value in natural units.

        Returns:
            True if the value is at or beyond either diagnostic limit.
        """
        lo, hi = self.diagnostic_limits
        return bool(value <= lo or value >= hi)

    def to_unconstrained(self, value: float) -> float:
        """Convert a natural-unit value to unconstrained coordinates."""
        return float(self.transform.inverse(np.asarray(value, dtype=np.float64)))

    def to_natural(self, value: float) -> float:
        """Convert an unconstrained value to natural units."""
        return float(self.transform.forward(np.asarray(value, dtype=np.float64)))
