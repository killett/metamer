"""Compiled kernels for the two roofline references.

Separate from `references.py` so the `njit` compilation happens once at import
and the timing functions stay readable. `fastmath` is off for the same reason
it is off in `engines/compiled.py`: reassociation would change what is being
measured, and in the STREAM case it would let the compiler vectorize
differently than the real workload does.
"""

from __future__ import annotations

import numpy as np
from numba import njit, prange
from numpy.typing import NDArray


@njit(cache=True, fastmath=False, nogil=True)
def propagate_covariance(  # pragma: no cover - compiled, timed not asserted
    f: NDArray[np.float64],
    q: NDArray[np.float64],
    p: NDArray[np.float64],
    h: NDArray[np.float64],
    iterations: int,
) -> float:
    """Run `P = F P F' + Q` plus a rank-1 downdate, `iterations` times.

    This is the filter's actual inner arithmetic. There is no factorization
    anywhere in it, which is the whole point of using it as the compute
    reference instead of an LU.

    Args:
        f: Transition, (d, d).
        q: Process noise, (d, d).
        p: Covariance, (d, d). Modified in place.
        h: Observation vector, (d,).
        iterations: Number of steps.

    Returns:
        A checksum, so the loop cannot be optimized away.
    """
    dim = f.shape[0]
    tmp = np.zeros((dim, dim), dtype=np.float64)
    hp = np.zeros(dim, dtype=np.float64)
    total = 0.0
    for _ in range(iterations):
        for i in range(dim):
            for j in range(dim):
                acc = 0.0
                for k in range(dim):
                    acc += f[i, k] * p[k, j]
                tmp[i, j] = acc
        for i in range(dim):
            for j in range(dim):
                acc = 0.0
                for k in range(dim):
                    acc += tmp[i, k] * f[j, k]
                p[i, j] = acc + q[i, j]
        # Rank-1 downdate, the scalar-observation update. No solve.
        s = 1.0
        for i in range(dim):
            acc = 0.0
            for j in range(dim):
                acc += h[j] * p[j, i]
            hp[i] = acc
            s += acc * h[i]
        for i in range(dim):
            gain = hp[i] / s
            for j in range(dim):
                p[i, j] -= gain * hp[j]
        total += p[0, 0]
    return total


@njit(cache=True, fastmath=False, parallel=True, nogil=True)
def stream_triad(  # pragma: no cover - compiled, timed not asserted
    a: NDArray[np.float64],
    b: NDArray[np.float64],
    c: NDArray[np.float64],
    scalar: float,
) -> None:
    """STREAM triad: `a = b + scalar * c`, over an array sized past L3.

    Three streams touched per element -- two read, one written -- which is the
    standard STREAM triad accounting.

    Args:
        a: Output vector.
        b: First input.
        c: Second input.
        scalar: Multiplier.
    """
    for i in prange(a.shape[0]):  # type: ignore[no-untyped-call, attr-defined]
        a[i] = b[i] + scalar * c[i]
