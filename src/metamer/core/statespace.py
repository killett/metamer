"""Composite state-space assembly and the defective-root guard."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.linalg import expm

from metamer.core.families.base import Family
from metamer.core.registry import kernel_registry
from metamer.core.terms import ProcessSpec

EIGEN_TARGET_ACCURACY = 1e-8
"""Relative accuracy required of F from the eigen route.

Eight digits: well above what the likelihood itself needs, but far enough below
full precision to leave the optimizer's finite differences meaningful.
"""

EIGEN_CONDITION_LIMIT = EIGEN_TARGET_ACCURACY / float(np.finfo(np.float64).eps)
"""Maximum eigenvector-matrix condition number the eigen route will accept.

DERIVATION, evaluated rather than transcribed. The eigen route's relative error
is roughly cond(V) * eps, so requiring `cond * eps <= target` gives
`cond <= target / eps` = 1e-8 / 2.220446049250313e-16 = 4.5035996273704956e+07.
The constant IS that expression: an earlier version rounded it to 1e8, which is
2.2x more permissive than its own stated derivation and in the direction that
weakens the guard. A derivation that does not produce the constant beside it is
worse than no derivation, so the rounding is gone.

CALIBRATION CASE, recorded because this constant has no independently correct
value and must be specified by the case it has to catch rather than have that
case loosened to fit it. The exactly-defective Matern nu=3/2 drift
A = [[0, 1], [-lam^2, -2 lam]], lam = sqrt(3)/rho, measured with
`np.linalg.cond(np.linalg.eig(A)[1])` on numpy 2.x / OpenBLAS:

    rho = 0.1  -> 1.80e+16
    rho = 1    -> 2.03e+08     <-- factor 4.5 of margin (was 2.0 at 1e8)
    rho = 10   -> 4.58e+08     <-- factor 10.2 of margin (was 4.6 at 1e8)
    rho = 100  -> inf

Raising this limit past 2.03e8 would send the single most defective matrix in
the library down the eigen route and return a silently wrong F.
`test_eigen_transition_refuses_the_defective_matern32_drift` is the standing
guard: it re-measures cond(V) and asserts it still exceeds this limit, so a
LAPACK change that erodes the margin fails loudly.

Tightening to the derived value costs nothing on the other side. Well-conditioned
drifts sit more than seven decades below: diag(-1, -3) measures 1.0 exactly (its
eigenvectors are orthonormal) and a generic non-normal 2x2 measures 1.084.
"""

UNIQUE_DT_RTOL = 1e-9
"""Relative tolerance for treating two timesteps as the same step.

Sized between the two scales it has to separate: float64 representation noise on
a `linspace`/`arange` grid is O(1e-16) relative, and genuinely distinct sampling
rates differ by far more than 1e-9. See `StateSpace.unique_dt`.
"""


class DefectiveMatrixError(RuntimeError):
    """The eigenvector matrix is too ill-conditioned for the eigen route."""


def eigen_transition(
    drift: NDArray[np.float64],
    dt: float,
    cond_threshold: float = EIGEN_CONDITION_LIMIT,
) -> NDArray[np.float64]:
    """Transition matrix via eigendecomposition, with a conditioning guard.

    As two roots coalesce the eigenvector matrix becomes ill-conditioned and
    V diag(exp(lam dt)) V^-1 loses precision *continuously* -- no exception,
    just a quietly wrong likelihood. The optimizer is attracted to these
    regions because near-degenerate roots are where composite models collapse
    onto simpler ones, so the guard is not an edge case.

    Args:
        drift: The drift matrix A, shape (d, d).
        dt: Timestep.
        cond_threshold: Maximum acceptable eigenvector-matrix condition number.
            Defaults to `EIGEN_CONDITION_LIMIT`, whose docstring records the
            derivation and the calibration case.

    Returns:
        expm(A * dt).

    Raises:
        DefectiveMatrixError: If the condition number exceeds the threshold.
            Callers fall back to scaling-and-squaring and count the fallback.
    """
    values, vectors = np.linalg.eig(np.asarray(drift, dtype=np.float64))
    cond = float(np.linalg.cond(vectors))
    if not np.isfinite(cond) or cond > cond_threshold:
        raise DefectiveMatrixError(
            f"eigenvector condition number {cond:.3e} exceeds {cond_threshold:.3e}; "
            "roots are near-degenerate and this model may be non-identifiable here"
        )
    return np.real(vectors @ np.diag(np.exp(values * dt)) @ np.linalg.inv(vectors))


def safe_transition(
    drift: NDArray[np.float64],
    dt: float,
    counter: dict[str, int] | None = None,
    cond_threshold: float = EIGEN_CONDITION_LIMIT,
) -> NDArray[np.float64]:
    """Transition matrix, falling back to scaling-and-squaring when defective.

    Args:
        drift: The drift matrix A.
        dt: Timestep.
        counter: Optional dict whose "fallback" key is incremented on fallback,
            so the rate can be surfaced as a diagnostic. Frequent firing is a
            bug signal, not a normal cost -- every shipped family has an
            analytic F, and this path exists for numerical degeneracy only.
        cond_threshold: Forwarded to `eigen_transition`. Without the forwarding
            the guard would be pinned to its default from the only caller,
            which is not acceptable for a constant with a factor-of-two margin.

    Returns:
        expm(A * dt).
    """
    try:
        return eigen_transition(drift, dt, cond_threshold=cond_threshold)
    except DefectiveMatrixError:
        if counter is not None:
            counter["fallback"] = counter.get("fallback", 0) + 1
        return np.asarray(expm(np.asarray(drift, dtype=np.float64) * float(dt)))


@dataclass(frozen=True)
class StepMatrices:
    """F and Q evaluated once per distinct timestep, plus the interval mapping.

    PROVISIONAL: the return type of `StateSpace._step_matrices`, whose docstring
    explains why that method is private and why Task 6 may replace both.

    Attributes:
        steps: The distinct timesteps, ascending, shape (S,).
        index: For each of the n-1 intervals of the time axis, the index into
            `steps` of the step it belongs to, shape (n-1,).
        transition: F at each distinct step, shape (S, B, d, d).
        process_noise: Q at each distinct step, shape (S, B, d, d).
    """

    steps: NDArray[np.float64]
    index: NDArray[np.intp]
    transition: NDArray[np.float64]
    process_noise: NDArray[np.float64]


@dataclass(frozen=True)
class StateSpace:
    """A composite state space assembled block-diagonally from its terms.

    Attributes:
        families: The instantiated families, in the spec's canonical order.
        slices: Each family's block of the composite state, same order.
        param_slices: Each family's columns of `theta`. See `from_spec` for
            which parameter vector these index -- it is NOT the free-parameter
            vector `terms.free_param_index` describes.
        state_dim: Total state dimension, the sum of the families' own.
    """

    families: tuple[Family, ...]
    slices: tuple[slice, ...]
    param_slices: tuple[slice, ...]
    state_dim: int

    @classmethod
    def from_spec(cls, spec: ProcessSpec) -> StateSpace:
        """Assemble from a canonically ordered ProcessSpec.

        THE THETA THIS BUILDS SLICES IS THE FULL PARAMETER VECTOR, NOT THE FREE
        ONE. `param_slices` is built from `len(term.params)`, which counts
        parameters with `fixed=True`, whereas `terms.free_param_index` -- the
        single source of truth for the vector the optimizer searches -- skips
        them. Those are two different vectors and the difference is deliberate:
        a free-only vector must be widened by `ConcentratedObjective.hydrate`
        before it reaches any `StateSpace` method, or a single frozen parameter
        shifts every later coordinate one slot to the left and the model is
        silently fitted with the wrong numbers in the wrong places.
        `test_state_space_slices_theta_over_fixed_parameters_too` pins this.

        Args:
            spec: The composite specification.

        Returns:
            A StateSpace whose block layout follows the spec's canonical order.
        """
        families: list[Family] = []
        blocks: list[slice] = []
        params: list[slice] = []
        offset = 0
        p_offset = 0
        for term in spec.terms:
            family = kernel_registry[term.kind]()
            families.append(family)
            blocks.append(slice(offset, offset + family.state_dim))
            offset += family.state_dim
            n_p = len(term.params)
            params.append(slice(p_offset, p_offset + n_p))
            p_offset += n_p
        return cls(tuple(families), tuple(blocks), tuple(params), offset)

    @staticmethod
    def unique_dt(
        t: NDArray[np.float64], rtol: float = UNIQUE_DT_RTOL
    ) -> NDArray[np.float64]:
        """Return the distinct timesteps of a shared time axis, ascending.

        On a regular grid this has one entry, so F and Q are computed once per
        series per optimizer iteration rather than once per timestep.

        TOLERANCE-AWARE, DELIBERATELY. `np.unique(np.diff(t))` does not collapse
        a float grid: `np.linspace(0, 1, 11)` yields FOUR distinct float64
        differences and `np.arange(0, 1, 0.1)` also four, because neither
        constructor produces bit-identical spacing unless the step happens to be
        exact in binary. A bit-exact `unique` therefore silently loses the
        amortization on most real time axes while appearing to work on
        `np.arange(0, 10, 1.0)`.

        THE TOLERANCE IS LOCAL, NOT GLOBAL. Each adjacent pair of sorted steps
        is compared against `rtol` times its OWN magnitude, never against
        `rtol * max|step|`. A global scale is set by the largest step in the
        record, so a single long gap inflates the tolerance everywhere: on
        `[0, 1, 2, 3.003, 4e9]` the global tolerance is 4.0 ABSOLUTE, which
        merges the genuinely distinct steps 1.0 and 1.003 and reports 2 steps
        where the same axis without the gap correctly reports 3. That is not an
        exotic input -- sub-second sampling inside a multi-year record puts
        gap/step above 1e9 routinely.

        The grouping is single-linkage on the sorted steps: a new group starts
        wherever an adjacent pair differs by more than the local tolerance, and
        each group is represented by its smallest member. Single linkage chains:
        a dense ladder of steps each within `rtol` of the next merges end to
        end, so a group can in principle span a factor of `(1 + rtol)^k` after k
        links. Reaching even a factor of two that way needs
        `ln 2 / rtol ~ 7e8` intermediate steps, so it is a property to know
        about rather than a hazard in practice -- but it does mean this returns
        representatives of clusters, not a partition into exactly-equal values.

        Args:
            t: Timestamps, shape (n,). Fewer than two entries gives no steps.
            rtol: Relative tolerance, applied to each adjacent pair's own scale.

        Returns:
            The distinct steps, ascending, shape (S,).
        """
        steps = np.sort(np.diff(np.asarray(t, dtype=np.float64)))
        if steps.size == 0:
            return steps
        # Local scale: the larger magnitude of the pair, so the comparison is
        # symmetric and stays meaningful for a negative step (an unsorted axis).
        scale = np.maximum(np.abs(steps[1:]), np.abs(steps[:-1]))
        starts = np.empty(steps.size, dtype=bool)
        starts[0] = True
        # An all-duplicate axis gives scale 0 and diff 0, so `0 > 0` is False
        # and the steps merge -- which is correct, and needs no special case.
        starts[1:] = np.diff(steps) > float(rtol) * scale
        return np.asarray(steps[starts], dtype=np.float64)

    def _step_matrices(
        self,
        theta: NDArray[np.float64],
        t: NDArray[np.float64],
        rtol: float = UNIQUE_DT_RTOL,
    ) -> StepMatrices:
        """Build F and Q once per distinct timestep, with the interval mapping.

        PROVISIONAL, AND PRIVATE FOR THAT REASON. Task 5 needed something to
        make the amortization real rather than merely claimed, but nothing in
        this task chose the shape deliberately, and the eager
        `(S, B, d, d)` materialisation is the wrong one for a chunked filter --
        see the cost note below. Task 6 owns the batched Kalman engine and
        should feel free to replace this outright rather than treat it as
        settled API.

        THIS IS THE MEMOIZATION, done explicitly rather than as a hidden cache:
        a regular axis of n points has n-1 intervals but one distinct step, so
        one F and one Q are built and `index` points every interval at them.

        Cost note for the caller: the returned stacks are S * B * d^2 floats
        each. On a regular grid S = 1; on a fully irregular one S = n-1 and this
        degenerates to materializing every interval's matrices at once, which is
        exactly the amortization failing and which would break the Task 17
        memory budget. An engine driving a long irregular series must chunk
        rather than call this once for the whole axis.

        Args:
            theta: Parameters, shape (B, p) -- the FULL vector, see `from_spec`.
            t: Timestamps, shape (n,).
            rtol: Relative tolerance forwarded to `unique_dt`.

        Returns:
            A `StepMatrices` whose `steps`, `transition` and `process_noise`
            share a leading axis, and whose `index` has one entry per interval.
        """
        arr = np.asarray(theta, dtype=np.float64)
        raw = np.diff(np.asarray(t, dtype=np.float64))
        steps = self.unique_dt(t, rtol=rtol)
        if steps.size == 0:
            empty = np.zeros((0, arr.shape[0], self.state_dim, self.state_dim))
            return StepMatrices(steps, np.zeros(0, dtype=np.intp), empty, empty)
        # `steps` is ascending and each group is represented by its smallest
        # member, so every raw step is at or above its own representative.
        index = np.clip(
            np.searchsorted(steps, raw, side="right") - 1, 0, steps.size - 1
        ).astype(np.intp)
        transition = np.stack([self.transition(arr, float(s)) for s in steps])
        process_noise = np.stack([self.process_noise(arr, float(s)) for s in steps])
        return StepMatrices(steps, index, transition, process_noise)

    def _assemble(
        self, theta: NDArray[np.float64], method: str, *args: float
    ) -> NDArray[np.float64]:
        """Place each family's (B, d_i, d_i) block on the composite diagonal."""
        arr = np.asarray(theta, dtype=np.float64)
        batch = arr.shape[0]
        out = np.zeros((batch, self.state_dim, self.state_dim), dtype=np.float64)
        for family, block, pslice in zip(
            self.families, self.slices, self.param_slices, strict=True
        ):
            if family.state_dim == 0:
                continue
            block_fn: Callable[..., NDArray[np.float64]] = getattr(family, method)
            out[:, block, block] = block_fn(arr[:, pslice], *args)
        return out

    def transition(self, theta: NDArray[np.float64], dt: float) -> NDArray[np.float64]:
        """Return the block-diagonal composite F, shape (B, d, d)."""
        return self._assemble(theta, "transition", dt)

    def process_noise(
        self, theta: NDArray[np.float64], dt: float
    ) -> NDArray[np.float64]:
        """Return the block-diagonal composite Q, shape (B, d, d)."""
        return self._assemble(theta, "process_noise", dt)

    def stationary_cov(self, theta: NDArray[np.float64]) -> NDArray[np.float64]:
        """Return the block-diagonal composite P_inf, shape (B, d, d)."""
        return self._assemble(theta, "stationary_cov")

    def observation(self, theta: NDArray[np.float64]) -> NDArray[np.float64]:
        """Return the concatenated observation row H, shape (B, d)."""
        arr = np.asarray(theta, dtype=np.float64)
        out = np.zeros((arr.shape[0], self.state_dim), dtype=np.float64)
        for family, block, pslice in zip(
            self.families, self.slices, self.param_slices, strict=True
        ):
            if family.state_dim == 0:
                continue
            out[:, block] = family.observation(arr[:, pslice])
        return out

    def measurement_variance(self, theta: NDArray[np.float64]) -> NDArray[np.float64]:
        """Return the summed measurement variance R, shape (B,)."""
        arr = np.asarray(theta, dtype=np.float64)
        total = np.zeros(arr.shape[0], dtype=np.float64)
        for family, pslice in zip(self.families, self.param_slices, strict=True):
            total = total + family.measurement_variance(arr[:, pslice])
        return total

    def acvf(
        self, theta: NDArray[np.float64], lags: NDArray[np.float64]
    ) -> NDArray[np.float64]:
        """Return the summed autocovariance, shape (B, n_lags)."""
        arr = np.asarray(theta, dtype=np.float64)
        total = np.zeros((arr.shape[0], np.size(lags)), dtype=np.float64)
        for family, pslice in zip(self.families, self.param_slices, strict=True):
            total = total + family.acvf(arr[:, pslice], lags)
        return total
