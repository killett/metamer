# metamer Phase 1 — Likelihood Spine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `metamer.core` — a batched, exact, continuous-time state-space likelihood engine with joint signal/noise estimation — end to end on arrays, with no batch orchestration, no zarr, and no CLI.

**Architecture:** A kernel algebra (`ProcessSpec` = sum of `TermSpec`) whose parameters carry bijections to unconstrained ℝ. Terms declare per-engine cost classes and per-objective gradient capability, resolved by intersection across a composite. A batched Kalman filter over `(B, N)` with scalar observations and masked gaps evaluates the likelihood; linear signal terms are profiled out by GLS inside the same filter pass, giving ML and REML objectives. The public API is `(B, N)` only — `B=1` is a shape, never a separate code path.

**Tech Stack:** Python 3.12, numpy 2.5, scipy 1.18, pytest, mypy strict, ruff. numba (added in Task 18) for the compiled spike backend. celerite2 optional, test-only. psutil for the RSS shim.

**Global Constraints:**
- `(B, N)` is the only code path. Every public function takes a leading batch axis.
- float64 throughout `core`. No float32 anywhere in this phase.
- Never interpolate gaps — mask the Kalman update, keep the prediction step.
- Analytic `F`, `Q`, `P∞` per family. A general `expm`/Lyapunov path exists only as a test reference and a numerical-degeneracy fallback.
- Every score carries an `engine` tag AND an `objective` tag. Ranking across either is a hard error.
- Parameter counting is defined per objective: ML `k = k_θ + k_β`, `n = n_obs`; REML `k = k_θ`, `n = n_obs − rank(X)`.
- No reordering, reparameterization, or preconditioner refresh mid-optimization.
- Parallelism is within a tile (over series), never across tiles.
- `pathlib` only; no POSIX-only syscalls; no `fork` assumptions.
- Design doc is authoritative: `docs/superpowers/specs/2026-08-04-metamer-design.md`. Section references below (§N) point into it.

**User decisions (already made):**
- "Phase 1 ships no batch orchestration (no tiling, no zarr, no CLI) while the array API is batched throughout. B=1 is a shape, never a code path."
- "Phase 1 minimum: white + Matérn ν=1/2 + at least one d>1 family, and sums of them."
- "The primary oracle is brute-force MVN, not celerite2." celerite2 is optional and is the designated first cut if Phase 1 proves too large.
- "FD as the Phase 1 default, analytic forward-mode as the target with a protocol slot, complex-step as the test oracle."
- "Do not build the batched trust-region until the stage-1 spike says to." Path A's reference form is a plain per-series scipy loop.
- "Both objectives are supported. ML is the default." REML lands in Phase 1 because deferring it leaves the warm-start key wrong and the IC bookkeeping with an unexercised second branch.
- Three hashes: `fit_hash` ⊂ `compat_hash` ⊂ `run_hash`, compat-relevance by allowlist.
- Machines: mini PC (4 cores, ~10 GB free) for development; 64-core box for the budget measurement; MacBook as the adversarial case for path A.

---

## Resolved ambiguity: which families give d=3

§9.2 offers "Matérn ν=5/2 or white+SHO" as the d=3 spike case. **`white + SHO` is d=2, not d=3** — white noise is *measurement* noise contributing to `R`, not to the state. This plan resolves it by implementing **white (d=0), Matérn ν=1/2 (d=1), Matérn ν=3/2 (d=2)** and reaching d=3 through the composite **`white + matern12 + matern32`**.

That is strictly better than adding Matérn ν=5/2: it hits d=3 *and* exercises composition, block-diagonal assembly, and canonical ordering — the central architectural claims — in the same test case.

---

## File structure

```
src/metamer/
  __init__.py                 version, public re-exports
  __main__.py                 `python -m metamer` smoke entry point
  core/
    __init__.py               the public core API surface
    transforms.py             Bijector protocol; Log, Logit, Identity; delta method
    params.py                 ParamSpec
    terms.py                  TermSpec, ProcessSpec, canonical ordering, canonical JSON
    capability.py             EngineId, CostClass, Objective, GradientMode; intersection
    registry.py               kernel registry, recipe registry, REGISTRY_VERSION
    lint.py                   static identifiability lint
    counting.py               n_free per objective
    outcomes.py               Outcome enum (failure taxonomy)
    hashing.py                canonical JSON, sha256, fit/compat/run hash + allowlist
    machine.py                peak-RSS shim (Linux/macOS/Windows branches)
    memory.py                 analytic bytes-per-series formula
    families/
      __init__.py             registration side effects
      base.py                 Family protocol; expm/Lyapunov reference builders
      white.py                white measurement noise (d=0)
      matern12.py             Ornstein-Uhlenbeck (d=1)
      matern32.py             Matérn 3/2, Jordan form (d=2)
    statespace.py             composite block-diagonal assembly; defective-root guard
    engines/
      __init__.py
      protocol.py             Engine protocol; ScoredResult carrying engine+objective tags
      kalman.py               batched Kalman, masked gaps, augmented GLS accumulation
    signal.py                 SignalSpec, term taxonomy, design matrix, rank(X)
    objective.py              ML and REML concentrated objectives
    gradients.py              FD, complex-step oracle, analytic forward-mode dispatch
    optimize.py               reference per-series driver, init ladder, Hessian at optimum
    criteria.py               AIC etc.; comparability guard
    fit.py                    fit() — the (B, N) driver
  bench/
    __init__.py
    references.py             canonical filter pass; compute reference; bandwidth reference
    spike.py                  stage-1 harness
tests/
  __init__.py
  test_transforms.py          test_terms.py          test_capability.py
  test_registry.py            test_families.py       test_statespace.py
  test_kalman.py              test_signal.py         test_objective.py
  test_counting.py            test_criteria.py       test_gradients.py
  test_optimize.py            test_fit.py            test_lint.py
  test_hashing.py             test_memory.py         test_outcomes.py
  oracles.py                  brute-force MVN, FD Hessian, expm/Lyapunov references
```

---

## Task index and the branch

Tasks 0–17 are unconditional. Task 18 builds the spike harness. **Task 19 is a user-thrown gate** — it requires runs on machines this session cannot reach. **Task 20 is conditional and may never be built.**

| # | task | blocked by |
|---|---|---|
| 0 | Package skeleton and dependencies | — |
| 1 | Bijectors, `ParamSpec`, delta method | 0 |
| 2 | `TermSpec` / `ProcessSpec` algebra, canonical ordering, canonical JSON | 1 |
| 3 | Capability resolution and the two registries | 2 |
| 4 | Family protocol; white and Matérn ν=1/2; analytic vs `expm`/Lyapunov | 3 |
| 5 | Matérn ν=3/2 (Jordan form); composite assembly; defective-root guard | 4 |
| 6 | Engine protocol and the batched Kalman filter; MVN oracle | 5 |
| 7 | Signal spec, design matrix, `rank(X)`, linear/nonlinear taxonomy | 2 |
| 8 | GLS profiling; ML and REML concentrated objectives | 6, 7 |
| 9 | Parameter counting per objective; both effective sample sizes | 8 |
| 10 | Criteria and the comparability guards | 9 |
| 11 | FD gradients, step rule, complex-step viability verdict | 9 |
| 12 | Analytic forward-mode for Matérn ν=1/2; gradient-capability resolution | 11 |
| 13 | Optimizer driver: init ladder, convergence, Hessian at optimum | 11 |
| 14 | `fit()` — the `(B, N)` driver with `x0` | 13, 10 |
| 15 | Identifiability lint | 5 |
| 16 | Three-hash machinery with the compat-relevance allowlist | 2 |
| 17 | Memory formula, RSS shim, benchmark references, spike harness | 14, 16 |
| 18 | **USER GATE** — cross-machine stage-1 measurement and the ≥3× decision | 17 |
| 19 | **CONDITIONAL** — batched trust-region, only if 18 is inconclusive | 18 |

The failure-taxonomy enum (`outcomes.py`) lands in **Task 3**, not later: `objective.py`
imports it in Task 8, and retrofitting a taxonomy onto a boolean `converged` flag means
revisiting every early return in the fit driver.

---

## Task 0: Package skeleton and dependencies

**Goal:** A `src/` layout package that imports, runs as `python -m metamer`, and has the Phase 1 dependencies installed.

**Files:**
- Create: `src/metamer/__init__.py`, `src/metamer/__main__.py`, `src/metamer/core/__init__.py`
- Create: `src/metamer/core/families/__init__.py`, `src/metamer/core/engines/__init__.py`
- Create: `src/metamer/bench/__init__.py`, `tests/__init__.py`, `tests/oracles.py`
- Modify: `pixi.toml` (add `psutil`; `numba` and `celerite2` are added later, in Task 18)

**Acceptance Criteria:**
- [ ] `pixi run python -m metamer` prints the version and exits 0
- [ ] `pixi run test` collects zero tests without error
- [ ] `pixi run typecheck` passes on the empty package
- [ ] `import metamer.core` succeeds without importing xarray, dask, or zarr

**Verify:** `pixi run python -m metamer && pixi run typecheck && pixi run lint`

**Steps:**

- [ ] **Step 1: Create the package skeleton**

```python
# src/metamer/__init__.py
"""metamer — stochastic noise-model fitting and selection for time series."""

__version__ = "0.1.0"

__all__ = ["__version__"]
```

```python
# src/metamer/__main__.py
"""Entry point so the package is runnable with `python -m metamer`."""

import sys

from metamer import __version__


def main() -> int:
    """Print the package version.

    Returns:
        Process exit code.
    """
    print(f"metamer {__version__}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

```python
# src/metamer/core/__init__.py
"""Array-level API: numpy/scipy only. No file I/O, no xarray, no dask."""
```

Create `src/metamer/core/families/__init__.py`, `src/metamer/core/engines/__init__.py`,
`src/metamer/bench/__init__.py`, and `tests/__init__.py` as empty files.

- [ ] **Step 2: Add the import-isolation test**

```python
# tests/test_core_isolation.py
import subprocess
import sys


def test_core_imports_without_batch_dependencies():
    """core must be importable with no xarray/dask/zarr in sys.modules.

    Bug this catches: someone adds `import xarray` to a core module, silently
    making `metamer.core` unusable for downstream consumers that installed
    without the [batch] extra.
    """
    code = (
        "import metamer.core, sys; "
        "bad = {'xarray', 'dask', 'zarr'} & set(sys.modules); "
        "assert not bad, bad"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
```

- [ ] **Step 3: Run it and confirm it passes**

Run: `pixi run test tests/test_core_isolation.py -v`
Expected: PASS

- [ ] **Step 4: Add psutil to pixi.toml**

Add `psutil = "*"` to the `[dependencies]` table, then:

Run: `pixi install`
Expected: solve succeeds on all four platforms

- [ ] **Step 5: Commit**

```bash
git add src tests pixi.toml pixi.lock
git commit -m "feat: scaffold metamer package skeleton"
```

---

## Task 1: Bijectors, ParamSpec, and the delta method

**Goal:** Every parameter carries a bijection to unconstrained ℝ that exposes `log|J|` and the first-order derivative needed to push uncertainties back to natural units.

**Files:**
- Create: `src/metamer/core/transforms.py`, `src/metamer/core/params.py`
- Create: `tests/test_transforms.py`

**Acceptance Criteria:**
- [ ] `Log`, `Logit(lo, hi)`, and `Identity` round-trip: `inverse(forward(u)) == u` to 1e-12
- [ ] `log_abs_det_jacobian` matches a finite-difference `log|d forward/d u|` to 1e-7
- [ ] `delta_method_cov` reproduces an explicitly computed `J Σ Jᵀ` for a 2×2 case
- [ ] `ParamSpec` rejects a `default` outside `bounds` at construction
- [ ] `diagnostic_limits` are stored separately from `bounds` and never clip

**Verify:** `pixi run test tests/test_transforms.py -v` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_transforms.py
import numpy as np
import pytest

from metamer.core.params import ParamSpec
from metamer.core.transforms import Identity, Log, Logit, delta_method_cov


@pytest.mark.parametrize(
    "bij, u",
    [
        (Log(), np.array([-3.0, 0.0, 2.5])),
        (Logit(0.0, 1.0), np.array([-2.0, 0.0, 4.0])),
        (Logit(0.5, 10.0), np.array([-1.0, 0.3])),
        (Identity(), np.array([-7.0, 0.0, 7.0])),
    ],
)
def test_roundtrip(bij, u):
    """inverse(forward(u)) recovers u.

    Bug this catches: a Logit that forgets to rescale by (hi - lo) in one
    direction, which silently squashes every bounded parameter toward its
    lower bound.
    """
    np.testing.assert_allclose(bij.inverse(bij.forward(u)), u, rtol=0, atol=1e-12)


@pytest.mark.parametrize(
    "bij, u",
    [
        (Log(), np.array([-1.5, 0.0, 2.0])),
        (Logit(0.0, 1.0), np.array([-1.0, 0.0, 1.0])),
        (Logit(-2.0, 3.0), np.array([0.25])),
    ],
)
def test_log_abs_det_jacobian_matches_finite_difference(bij, u):
    """log|J| equals log|d forward / d u| computed by central differences.

    Bug this catches: a sign error or a missing (hi - lo) factor in log|J|,
    which would bias any future MCMC and corrupt reported error bars now.
    """
    h = 1e-6
    numeric = np.log(np.abs((bij.forward(u + h) - bij.forward(u - h)) / (2 * h)))
    np.testing.assert_allclose(bij.log_abs_det_jacobian(u), numeric, rtol=1e-6, atol=1e-7)


def test_delta_method_cov_against_explicit_computation():
    """delta_method_cov(d, cov) equals diag(d) @ cov @ diag(d).T.

    Expected value determined independently: J is diagonal because the
    transforms are elementwise, so the answer is d_i d_j cov_ij by hand.
    """
    d = np.array([2.0, 3.0])
    cov_u = np.array([[1.0, 0.5], [0.5, 4.0]])
    expected = np.array([[4.0 * 1.0, 6.0 * 0.5], [6.0 * 0.5, 9.0 * 4.0]])
    np.testing.assert_allclose(delta_method_cov(d, cov_u), expected, rtol=1e-12)


def test_paramspec_rejects_default_outside_bounds():
    """A default outside bounds is a construction-time error.

    Bug this catches: a family shipping nu=0.5 with bounds (1.0, 3.0), which
    would otherwise surface as a mystifying optimizer failure at fit time.
    """
    with pytest.raises(ValueError, match="default"):
        ParamSpec(
            name="nu",
            default=0.5,
            transform=Logit(1.0, 3.0),
            bounds=(1.0, 3.0),
            diagnostic_limits=(1.0, 3.0),
        )


def test_diagnostic_limits_are_independent_of_bounds():
    """diagnostic_limits may be strictly inside bounds and do not clip.

    Bug this catches: conflating the two, which would silently clamp a
    parameter instead of reporting DIAGNOSTIC_LIMIT.
    """
    spec = ParamSpec(
        name="rho",
        default=10.0,
        transform=Log(),
        bounds=(0.0, np.inf),
        diagnostic_limits=(1e-3, 1e4),
    )
    assert spec.bounds == (0.0, np.inf)
    assert spec.diagnostic_limits == (1e-3, 1e4)
    assert spec.at_diagnostic_limit(1e5) is True
    assert spec.at_diagnostic_limit(10.0) is False
```

- [ ] **Step 2: Run to verify failure**

Run: `pixi run test tests/test_transforms.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'metamer.core.transforms'`

- [ ] **Step 3: Implement transforms.py**

```python
# src/metamer/core/transforms.py
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
        return self.lo + self._width * s

    def inverse(self, x: NDArray[np.float64]) -> NDArray[np.float64]:
        """Map (lo, hi) onto R."""
        s = (np.asarray(x, dtype=np.float64) - self.lo) / self._width
        return np.log(s) - np.log1p(-s)

    def dforward(self, u: NDArray[np.float64]) -> NDArray[np.float64]:
        """Derivative of the scaled logistic."""
        s = 1.0 / (1.0 + np.exp(-np.asarray(u, dtype=np.float64)))
        return self._width * s * (1.0 - s)

    def log_abs_det_jacobian(self, u: NDArray[np.float64]) -> NDArray[np.float64]:
        """log(width) + log s + log(1 - s), computed stably."""
        arr = np.asarray(u, dtype=np.float64)
        log_s = -np.logaddexp(0.0, -arr)
        log_1ms = -np.logaddexp(0.0, arr)
        return np.log(self._width) + log_s + log_1ms


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
    return d[..., :, None] * cov * d[..., None, :]
```

- [ ] **Step 4: Implement params.py**

```python
# src/metamer/core/params.py
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pixi run test tests/test_transforms.py -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add src/metamer/core/transforms.py src/metamer/core/params.py tests/test_transforms.py
git commit -m "feat: add bijectors, ParamSpec, and delta-method push-through"
```

---

## Task 2: TermSpec / ProcessSpec algebra, canonical ordering, canonical JSON

**Goal:** Kernel terms compose with `+`, sort into a canonical order, and serialize to a stable hash that is insensitive to dict ordering and float formatting.

**Files:**
- Create: `src/metamer/core/terms.py`
- Create: `tests/test_terms.py`

**Acceptance Criteria:**
- [ ] `TermSpec + TermSpec` and `ProcessSpec + ProcessSpec` both yield a `ProcessSpec`
- [ ] Terms are canonically ordered by `(kind, ordering-parameter default)` at construction
- [ ] Two specs differing only in construction order produce identical `spec_hash()`
- [ ] Two specs differing only in Python dict insertion order produce identical `spec_hash()`
- [ ] Stable labels (`matern12[0]`, `matern12[1]`) survive a re-sort
- [ ] `canonical()` is JSON-serializable and round-trips through `json.dumps`
- [ ] **`free_param_index(spec)` is the single source of truth for the flat parameter vector**, returning ordered `(term_label, param_name)` pairs for **free** parameters only
- [ ] **`len(free_param_index(spec)) == spec.n_theta()` asserted for every spec in the test set**, including one with a fixed parameter
- [ ] `free_param_index` matches hand-written expected output for: one term; a composite; a composite with a fixed parameter; two exchangeable terms
- [ ] A spec declaring a shared parameter raises `NotImplementedError` rather than silently miscounting

**Verify:** `pixi run test tests/test_terms.py -v` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_terms.py
import json

import pytest

from metamer.core.params import ParamSpec
from metamer.core.terms import ProcessSpec, TermSpec, free_param_index
from metamer.core.transforms import Log


def _param(name: str, default: float) -> ParamSpec:
    return ParamSpec(
        name=name,
        default=default,
        transform=Log(),
        bounds=(0.0, float("inf")),
        diagnostic_limits=(1e-8, 1e8),
    )


def _matern12(rho: float) -> TermSpec:
    return TermSpec(
        kind="matern12",
        params={"sigma": _param("sigma", 1.0), "rho": _param("rho", rho)},
        ordering_param="rho",
    )


def _white(sigma: float = 0.1) -> TermSpec:
    return TermSpec(kind="white", params={"sigma": _param("sigma", sigma)})


def test_addition_produces_process_spec():
    """TermSpec + TermSpec composes into a two-term ProcessSpec.

    Bug this catches: __add__ returning a tuple or mutating in place, either
    of which breaks the frozen-value semantics every hash depends on.
    """
    spec = _white() + _matern12(10.0)
    assert isinstance(spec, ProcessSpec)
    assert len(spec.terms) == 2


def test_canonical_order_is_independent_of_construction_order():
    """Construction order does not survive into the canonical form.

    Expected value determined independently: canonical order is (kind,
    ordering default) ascending with kind compared as a string, so
    matern12(rho=2) sorts before matern12(rho=50) before white, regardless of
    how they were added.
    """
    a = _matern12(50.0) + _white() + _matern12(2.0)
    b = _white() + _matern12(2.0) + _matern12(50.0)
    assert [t.kind for t in a.terms] == [t.kind for t in b.terms]
    assert a.spec_hash() == b.spec_hash()


def test_hash_is_insensitive_to_dict_insertion_order():
    """Reordering a params dict does not change spec_hash.

    Bug this catches: hashing repr() or a non-sorted json.dumps, which would
    make an identical model look like a different one across runs and
    invalidate a completed 10^7-point store.
    """
    forward = TermSpec(
        kind="matern12",
        params={"sigma": _param("sigma", 1.0), "rho": _param("rho", 3.0)},
        ordering_param="rho",
    )
    backward = TermSpec(
        kind="matern12",
        params={"rho": _param("rho", 3.0), "sigma": _param("sigma", 1.0)},
        ordering_param="rho",
    )
    assert ProcessSpec((forward,)).spec_hash() == ProcessSpec((backward,)).spec_hash()


def test_stable_labels_disambiguate_exchangeable_terms():
    """Two terms of the same kind get distinct, order-stable labels.

    Bug this catches: label collision, which makes warm-start reuse and
    cross-grid-point comparison silently attach 'term 2' to different objects
    at different points.
    """
    spec = _matern12(2.0) + _matern12(50.0)
    assert spec.labels() == ("matern12[0]", "matern12[1]")
    assert spec.terms[0].params["rho"].default == 2.0


def test_free_param_index_matches_hand_written_expectations():
    """The flat parameter vector's layout is stated once and tested directly.

    Expected values determined independently by applying the canonical-order
    rule on paper: kind ascending as a string puts matern12(rho=2) before
    matern12(rho=50) before white, and within a term the declared parameter
    order is preserved.

    Bug this catches: five separate copies of this nested loop existed across
    objective.py, optimize.py and gradients.py, two of them reading their
    ordering from different sources (term.params vs family.param_specs()).
    Divergence between two copies does not raise -- it produces converged-
    looking fits at values interpreted differently in two places.
    """
    single = ProcessSpec((_matern12(3.0),))
    assert free_param_index(single) == (("matern12[0]", "sigma"), ("matern12[0]", "rho"))

    composite = _white() + _matern12(50.0) + _matern12(2.0)
    assert free_param_index(composite) == (
        ("matern12[0]", "sigma"),
        ("matern12[0]", "rho"),
        ("matern12[1]", "sigma"),
        ("matern12[1]", "rho"),
        ("white[0]", "sigma"),
    )


def test_free_param_index_omits_fixed_parameters():
    """A frozen parameter is absent from the flat vector entirely.

    Bug this catches: the optimizer moving a parameter the user pinned, and
    k in AIC counting a parameter that was never estimated. Both are silent.
    """
    from dataclasses import replace

    term = _matern12(4.0)
    frozen = TermSpec(
        kind="matern12",
        params={n: replace(p, fixed=(n == "rho")) for n, p in term.params.items()},
        ordering_param="rho",
    )
    spec = ProcessSpec((frozen,))
    assert free_param_index(spec) == (("matern12[0]", "sigma"),)


@pytest.mark.parametrize(
    "spec_factory",
    [
        lambda: ProcessSpec((_matern12(3.0),)),
        lambda: _white() + _matern12(2.0),
        lambda: _white() + _matern12(2.0) + _matern12(50.0),
    ],
)
def test_free_param_index_length_equals_n_theta(spec_factory):
    """The layout and the count can never disagree.

    This single invariant is what makes the parameter vector safe: n_theta
    feeds k in every information criterion, and free_param_index defines what
    the optimizer searches. If they diverge, selection is corrupted with no
    visible symptom.
    """
    spec = spec_factory()
    assert len(free_param_index(spec)) == spec.n_theta()


def test_shared_parameters_are_refused_rather_than_miscounted():
    """Cross-term parameter sharing is out of scope and says so.

    Design doc section 4.7 requires counting to handle shared parameters.
    Phase 1 implements no sharing mechanism, so a spec that declares one must
    raise rather than be silently counted as independent -- the same discipline
    as nonlinear signal terms.
    """
    term = _matern12(3.0)
    shared = TermSpec(kind="matern12", params=term.params, ordering_param="rho", shared_with={"sigma": "other"})
    with pytest.raises(NotImplementedError, match="shared"):
        free_param_index(ProcessSpec((shared,)))


def test_canonical_is_json_serializable():
    """canonical() round-trips through json.dumps with sorted keys.

    Bug this catches: leaving a Bijector object or a numpy scalar in the
    canonical dict, which raises at hash time rather than at construction.
    """
    spec = _white() + _matern12(7.5)
    encoded = json.dumps(spec.canonical(), sort_keys=True, separators=(",", ":"))
    assert json.loads(encoded) == json.loads(encoded)
    assert "matern12" in encoded
```

- [ ] **Step 2: Run to verify failure**

Run: `pixi run test tests/test_terms.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'metamer.core.terms'`

- [ ] **Step 3: Implement terms.py**

```python
# src/metamer/core/terms.py
"""The kernel algebra: TermSpec, ProcessSpec, canonical form, and hashing."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from metamer.core.params import ParamSpec


def _param_canonical(spec: ParamSpec) -> dict[str, Any]:
    """Render a ParamSpec into a JSON-safe canonical dict."""
    return {
        "name": spec.name,
        "default": repr(float(spec.default)),
        "transform": type(spec.transform).__name__,
        "transform_args": getattr(spec.transform, "__dict__", {}),
        "bounds": [repr(float(b)) for b in spec.bounds],
        "diagnostic_limits": [repr(float(b)) for b in spec.diagnostic_limits],
        "fixed": bool(spec.fixed),
        "unit": spec.unit,
    }


@dataclass(frozen=True)
class TermSpec:
    """One additive kernel term.

    Attributes:
        kind: Registry key naming the family.
        params: Parameter specifications, keyed by name.
        ordering_param: Parameter used as the secondary canonical sort key.
            Terms without one sort only by kind.
    """

    kind: str
    params: Mapping[str, ParamSpec]
    ordering_param: str | None = None
    shared_with: Mapping[str, str] | None = None

    def order_key(self) -> tuple[str, float]:
        """Return the canonical sort key for this term."""
        if self.ordering_param is None:
            return (self.kind, 0.0)
        return (self.kind, float(self.params[self.ordering_param].default))

    def n_free(self) -> int:
        """Count parameters this term contributes to k_theta."""
        return sum(1 for p in self.params.values() if not p.fixed)

    def canonical(self) -> dict[str, Any]:
        """Render to a JSON-safe canonical dict with sorted parameter keys."""
        return {
            "kind": self.kind,
            "ordering_param": self.ordering_param,
            "params": {name: _param_canonical(self.params[name]) for name in sorted(self.params)},
        }

    def __add__(self, other: TermSpec | ProcessSpec) -> ProcessSpec:
        """Compose with another term or process."""
        return ProcessSpec((self,)) + other


@dataclass(frozen=True)
class ProcessSpec:
    """An additive composition of kernel terms, canonically ordered.

    Canonicalization happens here, at construction, and again when results are
    packed. It must never happen mid-optimization: re-sorting between optimizer
    iterations permutes the parameter vector under stored curvature and
    corrupts it.
    """

    terms: tuple[TermSpec, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        ordered = tuple(sorted(self.terms, key=lambda t: t.order_key()))
        object.__setattr__(self, "terms", ordered)

    def __add__(self, other: TermSpec | ProcessSpec) -> ProcessSpec:
        """Compose with another term or process."""
        if isinstance(other, TermSpec):
            return ProcessSpec(self.terms + (other,))
        return ProcessSpec(self.terms + other.terms)

    def __radd__(self, other: TermSpec) -> ProcessSpec:
        """Support TermSpec + ProcessSpec."""
        return ProcessSpec((other,)) + self

    def labels(self) -> tuple[str, ...]:
        """Return stable per-term labels, disambiguating repeated kinds."""
        counts: dict[str, int] = {}
        out: list[str] = []
        for term in self.terms:
            index = counts.get(term.kind, 0)
            counts[term.kind] = index + 1
            out.append(f"{term.kind}[{index}]")
        return tuple(out)

    def n_theta(self) -> int:
        """Count free noise parameters across all terms."""
        return sum(term.n_free() for term in self.terms)

    def canonical(self) -> dict[str, Any]:
        """Render the whole composition to a JSON-safe canonical dict."""
        return {"terms": [term.canonical() for term in self.terms]}

    def spec_hash(self) -> str:
        """Return a stable 16-character hash of the canonical form."""
        encoded = json.dumps(self.canonical(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def free_param_index(spec: ProcessSpec) -> tuple[tuple[str, str], ...]:
    """Return the layout of the flat parameter vector, free parameters only.

    THIS IS THE SINGLE SOURCE OF TRUTH for the ordering of the parameter vector
    the optimizer searches. Everything that packs or unpacks that vector --
    `objective.to_natural`, `to_unconstrained`, `dforward`, the diagnostic-limit
    check in `optimize`, the gradient routines, and the memory formula -- calls
    this rather than re-deriving the layout with its own nested loop.

    The convention is: canonical term order (already applied by ProcessSpec),
    then each term's declared parameter order, skipping any parameter with
    `fixed=True`.

    The invariant `len(free_param_index(spec)) == spec.n_theta()` ties this
    layout to the count that feeds `k` in every information criterion. If the
    two ever disagree, selection is corrupted with no visible symptom.

    Args:
        spec: The composite specification.

    Returns:
        Ordered (term_label, param_name) pairs, one per free parameter.

    Raises:
        NotImplementedError: If any term declares a shared parameter. Design
            doc section 4.7 requires counting to handle cross-term sharing;
            Phase 1 implements no sharing mechanism, so such a spec must be
            refused rather than silently counted as independent.
    """
    out: list[tuple[str, str]] = []
    for label, term in zip(spec.labels(), spec.terms, strict=True):
        if term.shared_with:
            raise NotImplementedError(
                f"{label}: cross-term shared parameters {sorted(term.shared_with)} are "
                "not implemented in Phase 1; see design doc section 4.7"
            )
        for name, param in term.params.items():
            if not param.fixed:
                out.append((label, name))
    return tuple(out)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pixi run test tests/test_terms.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/metamer/core/terms.py tests/test_terms.py
git commit -m "feat: add kernel algebra with canonical ordering and stable hashing"
```

---

## Task 3: Capability resolution, the two registries, and the failure taxonomy

**Goal:** A spec declares which engines can evaluate it and at what cost; composition takes the intersection and errors informatively when it is empty. Kernel families and experiment recipes live in separate, versioned registries. The failure taxonomy is an enum from the outset.

**Files:**
- Create: `src/metamer/core/capability.py`, `src/metamer/core/registry.py`, `src/metamer/core/outcomes.py`
- Modify: `src/metamer/core/terms.py` (add `engine_costs` to `TermSpec`/`ProcessSpec`)
- Create: `tests/test_capability.py`, `tests/test_registry.py`, `tests/test_outcomes.py`

**Acceptance Criteria:**
- [ ] `CostClass` orders `LINEAR < NLOGN < CUBIC`; intersection takes the worst per engine
- [ ] An empty engine intersection raises `IncompatibleSpecError` naming the eliminating term
- [ ] Kernel and recipe registries are separate objects with separate lookup types
- [ ] Duplicate registration under the same key raises rather than silently overwriting
- [ ] `REGISTRY_VERSION` is a module constant included in provenance
- [ ] `Outcome` has all twelve members; `INSUFFICIENT_DATA` and `NOT_ATTEMPTED` are distinct from every failure; `RANK_DEFICIENT_X` and `ILL_CONDITIONED_X` are distinct from each other
- [ ] `Outcome.is_failure` excludes `OK`, `NOT_ATTEMPTED`, and `INSUFFICIENT_DATA` — the denominator rule

**Verify:** `pixi run test tests/test_capability.py tests/test_registry.py tests/test_outcomes.py -v`

**Steps:**

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_capability.py
import pytest

from metamer.core.capability import (
    CostClass,
    EngineId,
    IncompatibleSpecError,
    intersect_engine_costs,
)


def test_cost_class_orders_by_asymptotic_cost():
    """LINEAR < NLOGN < CUBIC, so `max` picks the worst.

    Expected value determined independently: O(N) is cheaper than O(N log N)
    is cheaper than O(N^3) for all N > 1.
    """
    assert CostClass.LINEAR < CostClass.NLOGN < CostClass.CUBIC
    assert max(CostClass.LINEAR, CostClass.CUBIC) is CostClass.CUBIC


def test_intersection_keeps_only_engines_supported_by_every_term():
    """An engine survives only if every term supports it.

    Expected value determined independently: term A supports {kalman,
    whittle}, term B supports {whittle, toeplitz}; the intersection is
    {whittle} by set intersection done on paper.
    """
    a = {EngineId.KALMAN: CostClass.LINEAR, EngineId.WHITTLE: CostClass.NLOGN}
    b = {EngineId.WHITTLE: CostClass.NLOGN, EngineId.TOEPLITZ: CostClass.CUBIC}
    result = intersect_engine_costs([("a", a), ("b", b)])
    assert set(result) == {EngineId.WHITTLE}


def test_intersection_takes_the_worst_cost_per_engine():
    """A composite is as expensive as its most expensive term.

    Bug this catches: taking the min or the first cost, which would let the
    batch layer accept an O(N^3) composite at 10^7 scale.
    """
    a = {EngineId.KALMAN: CostClass.LINEAR}
    b = {EngineId.KALMAN: CostClass.CUBIC}
    result = intersect_engine_costs([("a", a), ("b", b)])
    assert result[EngineId.KALMAN] is CostClass.CUBIC


def test_empty_intersection_names_the_eliminating_term():
    """The error message identifies which term removed which engine.

    Bug this catches: a bare "no engine available", which at 12 candidates
    leaves the user guessing which term is at fault.
    """
    a = {EngineId.KALMAN: CostClass.LINEAR}
    b = {EngineId.TOEPLITZ: CostClass.CUBIC}
    with pytest.raises(IncompatibleSpecError) as excinfo:
        intersect_engine_costs([("statespace_term", a), ("exact_powerlaw", b)])
    message = str(excinfo.value)
    assert "exact_powerlaw" in message
    assert "kalman" in message
```

```python
# tests/test_registry.py
import pytest

from metamer.core.registry import (
    REGISTRY_VERSION,
    DuplicateRegistrationError,
    kernel_registry,
    recipe_registry,
)


def test_registry_version_is_recorded():
    """REGISTRY_VERSION exists and is a non-empty string.

    Bug this catches: shipping without a version stamp, so "matern32" could
    change meaning between releases and silently invalidate a cached run.
    """
    assert isinstance(REGISTRY_VERSION, str)
    assert REGISTRY_VERSION


def test_kernel_and_recipe_registries_are_distinct():
    """Kernels and recipes do not share a namespace.

    Bug this catches: putting 'hw2010_ar5' in the kernel registry, which
    bundles a noise model with a signal model, an engine, and a criterion and
    makes the return type of a lookup unpredictable.
    """
    assert kernel_registry is not recipe_registry
    kernel_registry.register("dummy_kernel_probe")(lambda: "kernel")
    assert "dummy_kernel_probe" not in recipe_registry
    kernel_registry.unregister("dummy_kernel_probe")


def test_duplicate_registration_raises():
    """Registering the same key twice is an error, not an overwrite.

    Bug this catches: two plugins claiming 'matern32', where last-import-wins
    would change results depending on import order.
    """
    kernel_registry.register("dup_probe")(lambda: 1)
    with pytest.raises(DuplicateRegistrationError, match="dup_probe"):
        kernel_registry.register("dup_probe")(lambda: 2)
    kernel_registry.unregister("dup_probe")
```

- [ ] **Step 2: Run to verify failure**

Run: `pixi run test tests/test_capability.py tests/test_registry.py -v`
Expected: FAIL — both modules missing

- [ ] **Step 3: Implement capability.py**

```python
# src/metamer/core/capability.py
"""Engine, objective, and gradient capability, resolved by intersection."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from enum import IntEnum, StrEnum


class EngineId(StrEnum):
    """Likelihood engines. Only KALMAN is implemented in Phase 1."""

    KALMAN = "kalman"
    WHITTLE = "whittle"
    TOEPLITZ = "toeplitz"
    CELERITE2 = "celerite2"


class CostClass(IntEnum):
    """Asymptotic evaluation cost, ordered cheapest to most expensive."""

    LINEAR = 1
    NLOGN = 2
    CUBIC = 3


class Objective(StrEnum):
    """Which likelihood is being maximized."""

    ML = "ml"
    REML = "reml"


class GradientMode(StrEnum):
    """How the gradient is obtained. ANALYTIC beats FD when available."""

    ANALYTIC = "analytic"
    FINITE_DIFFERENCE = "fd"


class IncompatibleSpecError(ValueError):
    """No engine can evaluate the composite specification."""


def intersect_engine_costs(
    per_term: Iterable[tuple[str, Mapping[EngineId, CostClass]]],
) -> dict[EngineId, CostClass]:
    """Resolve a composite's engine capability by intersection.

    An engine survives only if every term supports it, and the composite's
    cost for that engine is the worst cost across terms.

    Args:
        per_term: Pairs of (term label, that term's engine cost mapping).

    Returns:
        Mapping from surviving engine to composite cost class.

    Raises:
        IncompatibleSpecError: If no engine survives. The message names which
            term eliminated which engine.
    """
    items = list(per_term)
    if not items:
        return {}

    surviving: dict[EngineId, CostClass] = dict(items[0][1])
    eliminated_by: dict[EngineId, str] = {}

    for label, costs in items[1:]:
        for engine in list(surviving):
            if engine not in costs:
                eliminated_by[engine] = label
                del surviving[engine]
            else:
                surviving[engine] = max(surviving[engine], costs[engine])

    if not surviving:
        detail = ", ".join(f"{engine.value} eliminated by {label}" for engine, label in eliminated_by.items())
        raise IncompatibleSpecError(f"No engine can evaluate this composite: {detail}")
    return surviving


def intersect_gradient_modes(
    per_term: Iterable[Mapping[Objective, GradientMode]], objective: Objective
) -> GradientMode:
    """Resolve the composite gradient mode for one objective.

    A composite has an analytic gradient only if every term does, for that
    objective. Gradient availability differs by objective because the REML
    penalty is not covered by the envelope theorem.

    Args:
        per_term: Each term's per-objective gradient mode.
        objective: The objective being evaluated.

    Returns:
        ANALYTIC if every term supplies it, otherwise FINITE_DIFFERENCE.
    """
    modes = [m.get(objective, GradientMode.FINITE_DIFFERENCE) for m in per_term]
    if modes and all(m is GradientMode.ANALYTIC for m in modes):
        return GradientMode.ANALYTIC
    return GradientMode.FINITE_DIFFERENCE
```

- [ ] **Step 4: Implement registry.py**

```python
# src/metamer/core/registry.py
"""Two separate registries: kernel families, and experiment recipes.

Recipes bundle a noise model with a signal model, an engine, and a criterion.
They are not kernels, and keeping them apart is what stops the kernel registry
becoming a junk drawer with an unpredictable lookup type.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from importlib.metadata import entry_points
from typing import Generic, TypeVar

REGISTRY_VERSION = "1"
"""Stamped into provenance so a name cannot silently change meaning."""

T = TypeVar("T")


class DuplicateRegistrationError(KeyError):
    """A key was registered twice."""


class Registry(Generic[T]):
    """A name-to-factory registry with decorator registration."""

    def __init__(self, name: str, entry_point_group: str | None = None):
        self._name = name
        self._entry_point_group = entry_point_group
        self._items: dict[str, T] = {}
        self._loaded_entry_points = False

    def register(self, key: str) -> Callable[[T], T]:
        """Return a decorator registering a factory under `key`.

        Args:
            key: Registry name.

        Returns:
            A decorator that registers and returns its argument unchanged.

        Raises:
            DuplicateRegistrationError: If `key` is already registered.
        """

        def decorator(item: T) -> T:
            if key in self._items:
                raise DuplicateRegistrationError(
                    f"{self._name}: {key!r} is already registered"
                )
            self._items[key] = item
            return item

        return decorator

    def unregister(self, key: str) -> None:
        """Remove a key. Used by tests; not part of the public contract."""
        self._items.pop(key, None)

    def _load_entry_points(self) -> None:
        if self._loaded_entry_points or self._entry_point_group is None:
            return
        self._loaded_entry_points = True
        for ep in entry_points(group=self._entry_point_group):
            if ep.name not in self._items:
                self._items[ep.name] = ep.load()

    def __getitem__(self, key: str) -> T:
        self._load_entry_points()
        if key not in self._items:
            available = ", ".join(sorted(self._items))
            raise KeyError(f"{self._name}: unknown key {key!r}. Available: {available}")
        return self._items[key]

    def __contains__(self, key: str) -> bool:
        self._load_entry_points()
        return key in self._items

    def __iter__(self) -> Iterator[str]:
        self._load_entry_points()
        return iter(sorted(self._items))


kernel_registry: Registry[Callable[..., object]] = Registry(
    "kernel_registry", entry_point_group="metamer.kernels"
)
recipe_registry: Registry[Callable[..., object]] = Registry("recipe_registry")
```

- [ ] **Step 5: Implement outcomes.py and its test**

```python
# tests/test_outcomes.py
from metamer.core.outcomes import Outcome


def test_insufficient_data_is_not_a_failure():
    """Land and permanent-ice pixels must not inflate the failure rate.

    Bug this catches: counting INSUFFICIENT_DATA as failure, which on a global
    ocean-only run reports ~70% 'failure' and turns the number into noise
    everyone learns to ignore.
    """
    assert Outcome.INSUFFICIENT_DATA.is_failure is False
    assert Outcome.INSUFFICIENT_DATA.is_eligible is False


def test_not_attempted_is_distinct_from_failure():
    """A screened-out candidate is not a failed candidate.

    Bug this catches: collapsing 'skipped' and 'failed' into one NaN, which
    have opposite scientific meanings.
    """
    assert Outcome.NOT_ATTEMPTED.is_failure is False
    assert Outcome.CANDIDATE_DROPPED is not Outcome.NOT_ATTEMPTED


def test_every_real_failure_reports_is_failure():
    """All genuine failure branches are counted as failures.

    Expected value determined independently by reading the taxonomy table in
    design doc section 8.6 and listing the failure rows by hand.
    """
    failures = {
        Outcome.ITER_CAP_LARGE_GRAD,
        Outcome.DIAGNOSTIC_LIMIT,
        Outcome.TRUST_RADIUS_COLLAPSED,
        Outcome.NONFINITE_OBJECTIVE,
        Outcome.RANK_DEFICIENT_X,
        Outcome.ILL_CONDITIONED_X,
        Outcome.DEGENERATE_HESSIAN,
        Outcome.CANDIDATE_DROPPED,
    }
    assert {o for o in Outcome if o.is_failure} == failures


def test_iteration_cap_with_small_gradient_is_flagged_not_failed():
    """Hitting the cap with a small gradient is probably fine, and flagged.

    Bug this catches: treating all cap hits identically, which discards the
    distinction between 'converged slowly' and 'did not converge'.
    """
    assert Outcome.ITER_CAP_SMALL_GRAD.is_failure is False
    assert Outcome.ITER_CAP_SMALL_GRAD is not Outcome.OK
```

```python
# src/metamer/core/outcomes.py
"""The failure taxonomy.

Non-convergence is not one outcome. At 10^7 series nobody inspects individual
fits, so the map of *which* failure occurred *where* is itself the diagnostic.
This is an enum written to the output, never a boolean `converged` flag.
"""

from __future__ import annotations

from enum import StrEnum

import numpy as np
from numpy.typing import NDArray


class Outcome(StrEnum):
    """Per (point, candidate) fit outcome."""

    OK = "ok"
    ITER_CAP_SMALL_GRAD = "iter_cap_small_grad"
    ITER_CAP_LARGE_GRAD = "iter_cap_large_grad"
    DIAGNOSTIC_LIMIT = "diagnostic_limit"
    TRUST_RADIUS_COLLAPSED = "trust_radius_collapsed"
    NONFINITE_OBJECTIVE = "nonfinite_objective"
    RANK_DEFICIENT_X = "rank_deficient_x"
    DEGENERATE_HESSIAN = "degenerate_hessian"
    ILL_CONDITIONED_X = "ill_conditioned_x"
    NOT_ATTEMPTED = "not_attempted"
    CANDIDATE_DROPPED = "candidate_dropped"
    INSUFFICIENT_DATA = "insufficient_data"

    @property
    def is_eligible(self) -> bool:
        """Whether this point counts toward a failure-rate denominator.

        INSUFFICIENT_DATA is a legitimate expected outcome — land, permanent
        ice, or too few valid samples — and is excluded.
        """
        return self is not Outcome.INSUFFICIENT_DATA

    @property
    def is_failure(self) -> bool:
        """Whether this outcome counts as a failure.

        Excludes OK, NOT_ATTEMPTED (deliberately skipped) and
        INSUFFICIENT_DATA (expected). ITER_CAP_SMALL_GRAD is flagged but is
        not a failure: the gradient is small, so the fit is probably fine.
        """
        return self not in {
            Outcome.OK,
            Outcome.ITER_CAP_SMALL_GRAD,
            Outcome.NOT_ATTEMPTED,
            Outcome.INSUFFICIENT_DATA,
        }

    @property
    def code(self) -> int:
        """Stable integer code, for the batched arrays and the zarr schema."""
        return _CODES[self]

    @classmethod
    def from_code(cls, value: int) -> Outcome:
        """Invert `code`."""
        return _BY_CODE[int(value)]


# Stable on-disk codes. NEVER renumber: they are written to the zarr store as
# uint8 and a renumbering silently reinterprets every archived run. Adding a new
# member takes the next free code and bumps the store's schema_version.
_CODES: dict[Outcome, int] = {
    Outcome.OK: 0,
    Outcome.ITER_CAP_SMALL_GRAD: 1,
    Outcome.ITER_CAP_LARGE_GRAD: 2,
    Outcome.DIAGNOSTIC_LIMIT: 3,
    Outcome.TRUST_RADIUS_COLLAPSED: 4,
    Outcome.NONFINITE_OBJECTIVE: 5,
    Outcome.RANK_DEFICIENT_X: 6,
    Outcome.DEGENERATE_HESSIAN: 7,
    Outcome.NOT_ATTEMPTED: 8,
    Outcome.CANDIDATE_DROPPED: 9,
    Outcome.INSUFFICIENT_DATA: 10,
    Outcome.ILL_CONDITIONED_X: 11,
}
_BY_CODE: dict[int, Outcome] = {code: member for member, code in _CODES.items()}


def outcome_array(batch: int, outcome: Outcome = Outcome.OK) -> NDArray[np.uint8]:
    """Return a per-series outcome array filled with one value.

    Outcomes are PER SERIES wherever they cross a batched boundary. A scalar
    outcome for a batch of B means one bad grid point marks all B as failed,
    which contradicts both "(B, N) is the only code path" and the output
    schema's per-(point, model) status -- and turns the spatial failure map,
    which is itself a diagnostic, into a picture of the tile grid.
    """
    return np.full(batch, outcome.code, dtype=np.uint8)
```

- [ ] **Step 6: Wire capability into ProcessSpec**

Add to `TermSpec` in `src/metamer/core/terms.py`:

```python
    def engine_costs(self) -> dict["EngineId", "CostClass"]:
        """Return this term's per-engine cost classes from its family."""
        from metamer.core.registry import kernel_registry

        return kernel_registry[self.kind]().engine_costs
```

Add to `ProcessSpec`:

```python
    def engine_costs(self) -> dict["EngineId", "CostClass"]:
        """Resolve composite engine capability by intersection across terms."""
        from metamer.core.capability import intersect_engine_costs

        return intersect_engine_costs(
            zip(self.labels(), (t.engine_costs() for t in self.terms), strict=True)
        )
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pixi run test tests/test_capability.py tests/test_registry.py tests/test_outcomes.py -v`
Expected: all PASS

- [ ] **Step 8: Commit**

```bash
git add src/metamer/core/capability.py src/metamer/core/registry.py src/metamer/core/outcomes.py src/metamer/core/terms.py tests/test_capability.py tests/test_registry.py tests/test_outcomes.py
git commit -m "feat: add capability resolution, registries, and failure taxonomy"
```

---

## Task 4: Family protocol; white and Matérn ν=1/2

**Goal:** A `Family` protocol supplying analytic `F`, `Q`, `P∞`, `H` and an analytic autocovariance, with white noise and Ornstein–Uhlenbeck implemented and checked against a general `expm`/Lyapunov reference.

**Files:**
- Create: `src/metamer/core/families/base.py`, `white.py`, `matern12.py`
- Modify: `src/metamer/core/families/__init__.py`
- Create: `tests/oracles.py`, `tests/test_families.py`

**Acceptance Criteria:**
- [ ] `matern12.transition(theta, dt)` matches `scipy.linalg.expm(A*dt)` to `rtol=1e-12, atol=1e-14`
- [ ] `matern12.process_noise` matches `P∞ − F P∞ Fᵀ` computed from a Lyapunov solve to
      `rtol=1e-11, atol=1e-13` — the looser of the two, because the difference form loses
      precision at small nonzero `Δt` at every state dimension
- [ ] `matern12.acvf(τ) == sigma² exp(−|τ|/rho)` — a closed form taken from the literature, not from the implementation
- [ ] White noise reports `state_dim == 0` and contributes only to `measurement_variance`
- [ ] All family methods accept `theta` of shape `(B, p)` and return leading batch axes

**Verify:** `pixi run test tests/test_families.py -v` → all pass

**Steps:**

- [ ] **Step 1: Write the oracle helpers**

```python
# tests/oracles.py
"""Independently-derived references. Nothing here may import the code under test."""

import numpy as np
from numpy.typing import NDArray
from scipy.linalg import expm, solve_continuous_lyapunov


def expm_transition(drift: NDArray[np.float64], dt: float) -> NDArray[np.float64]:
    """Transition matrix by general matrix exponential."""
    return expm(np.asarray(drift, dtype=np.float64) * float(dt))


def lyapunov_stationary_cov(
    drift: NDArray[np.float64], diffusion: NDArray[np.float64]
) -> NDArray[np.float64]:
    """Stationary covariance from A P + P A' + L L' = 0."""
    a = np.asarray(drift, dtype=np.float64)
    ll = np.asarray(diffusion, dtype=np.float64) @ np.asarray(diffusion, dtype=np.float64).T
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


def fd_hessian(fn, x: NDArray[np.float64], step: float = 1e-4) -> NDArray[np.float64]:
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
```

- [ ] **Step 2: Write the failing family tests**

```python
# tests/test_families.py
import numpy as np
import pytest

from metamer.core.families.matern12 import Matern12
from metamer.core.families.white import White
from tests.oracles import (
    expm_transition,
    lyapunov_stationary_cov,
    process_noise_from_stationary,
)


@pytest.mark.parametrize("dt", [0.1, 1.0, 7.0])
@pytest.mark.parametrize("rho", [0.5, 3.0, 40.0])
def test_matern12_transition_matches_expm(dt, rho):
    """Analytic F equals expm(A*dt) for the OU drift A = -1/rho.

    Bug this catches: a sign error or a missing reciprocal in the analytic
    form, which would invert the meaning of the correlation timescale.
    """
    fam = Matern12()
    theta = np.array([[1.0, rho]])
    drift = np.array([[-1.0 / rho]])
    np.testing.assert_allclose(
        fam.transition(theta, dt)[0], expm_transition(drift, dt), rtol=1e-12, atol=1e-14
    )


@pytest.mark.parametrize("dt", [0.25, 2.0])
def test_matern12_process_noise_matches_lyapunov(dt):
    """Analytic Q equals P_inf - F P_inf F' with P_inf from a Lyapunov solve.

    Bug this catches: forgetting the (1 - exp(-2 dt / rho)) factor, which
    makes the process non-stationary and inflates low-frequency power.
    """
    sigma, rho = 2.0, 5.0
    fam = Matern12()
    theta = np.array([[sigma, rho]])
    drift = np.array([[-1.0 / rho]])
    diffusion = np.array([[sigma * np.sqrt(2.0 / rho)]])
    p_inf = lyapunov_stationary_cov(drift, diffusion)
    f = expm_transition(drift, dt)
    np.testing.assert_allclose(
        fam.process_noise(theta, dt)[0],
        process_noise_from_stationary(p_inf, f),
        rtol=1e-11,
        atol=1e-13,
    )
    np.testing.assert_allclose(fam.stationary_cov(theta)[0], p_inf, rtol=1e-12)


def test_matern12_acvf_matches_textbook_closed_form():
    """ACVF is sigma^2 exp(-|tau|/rho).

    Expected value determined independently: this is the standard OU
    autocovariance (Rasmussen & Williams eq. 4.9, Matern nu=1/2), written out
    by hand rather than read off the implementation.
    """
    sigma, rho = 1.5, 4.0
    lags = np.array([0.0, 1.0, 10.0])
    expected = sigma**2 * np.exp(-np.abs(lags) / rho)
    np.testing.assert_allclose(
        Matern12().acvf(np.array([[sigma, rho]]), lags)[0], expected, rtol=1e-12
    )


def test_white_is_measurement_noise_not_state():
    """White noise has no state dimension and only sets R.

    Bug this catches: giving white a state dimension, which would make
    `white + SHO` d=3 instead of d=2 and silently change every memory figure.
    """
    fam = White()
    assert fam.state_dim == 0
    theta = np.array([[0.3]])
    assert fam.measurement_variance(theta)[0] == pytest.approx(0.09)
    assert fam.transition(theta, 1.0).shape == (1, 0, 0)


def test_families_broadcast_over_the_batch_axis():
    """theta of shape (B, p) yields leading batch axes everywhere.

    Bug this catches: a family written for a single series, which would force
    a Python loop over pixels at the exact place the design forbids one.
    """
    theta = np.array([[1.0, 2.0], [2.0, 8.0], [0.5, 1.0]])
    fam = Matern12()
    assert fam.transition(theta, 1.0).shape == (3, 1, 1)
    assert fam.process_noise(theta, 1.0).shape == (3, 1, 1)
    assert fam.stationary_cov(theta).shape == (3, 1, 1)
    assert fam.acvf(theta, np.array([0.0, 1.0])).shape == (3, 2)
```

- [ ] **Step 3: Run to verify failure**

Run: `pixi run test tests/test_families.py -v`
Expected: FAIL — family modules missing

- [ ] **Step 4: Implement the family protocol**

```python
# src/metamer/core/families/base.py
"""The Family protocol: analytic state-space construction per kernel family.

Every family supplies closed-form F, Q, P_inf and an analytic autocovariance.
The general expm/Lyapunov route exists only as a test reference and as the
numerical fallback for near-degenerate roots; if it runs often in production,
something is wrong.
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
```

- [ ] **Step 5: Implement white.py and matern12.py**

```python
# src/metamer/core/families/white.py
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
    """Independent Gaussian measurement noise of standard deviation sigma."""

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
        """Return an empty (B, 0, 0) array — white noise has no state."""
        return np.zeros((np.shape(theta)[0], 0, 0), dtype=np.float64)

    def process_noise(self, theta: NDArray[np.float64], dt: float) -> NDArray[np.float64]:
        """Return an empty (B, 0, 0) array."""
        return np.zeros((np.shape(theta)[0], 0, 0), dtype=np.float64)

    def stationary_cov(self, theta: NDArray[np.float64]) -> NDArray[np.float64]:
        """Return an empty (B, 0, 0) array."""
        return np.zeros((np.shape(theta)[0], 0, 0), dtype=np.float64)

    def observation(self, theta: NDArray[np.float64]) -> NDArray[np.float64]:
        """Return an empty (B, 0) observation row."""
        return np.zeros((np.shape(theta)[0], 0), dtype=np.float64)

    def measurement_variance(self, theta: NDArray[np.float64]) -> NDArray[np.float64]:
        """Return sigma^2, shape (B,)."""
        return np.asarray(theta, dtype=np.float64)[:, 0] ** 2

    def acvf(self, theta: NDArray[np.float64], lags: NDArray[np.float64]) -> NDArray[np.float64]:
        """Return sigma^2 at lag 0 and zero elsewhere."""
        arr = np.asarray(theta, dtype=np.float64)
        lags = np.asarray(lags, dtype=np.float64)
        out = np.zeros((arr.shape[0], lags.size), dtype=np.float64)
        out[:, lags == 0.0] = (arr[:, 0] ** 2)[:, None]
        return out
```

```python
# src/metamer/core/families/matern12.py
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

    ACVF: k(tau) = sigma^2 exp(-|tau| / rho).
    State-space: d = 1, A = -1/rho, F = exp(-dt/rho), P_inf = sigma^2.
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
        """Return exp(-dt/rho) as a (B, 1, 1) array."""
        rho = np.asarray(theta, dtype=np.float64)[:, 1]
        return np.exp(-float(dt) / rho)[:, None, None]

    def stationary_cov(self, theta: NDArray[np.float64]) -> NDArray[np.float64]:
        """Return sigma^2 as a (B, 1, 1) array."""
        sigma = np.asarray(theta, dtype=np.float64)[:, 0]
        return (sigma**2)[:, None, None]

    def process_noise(self, theta: NDArray[np.float64], dt: float) -> NDArray[np.float64]:
        """Return sigma^2 (1 - exp(-2 dt / rho)) as a (B, 1, 1) array."""
        arr = np.asarray(theta, dtype=np.float64)
        sigma, rho = arr[:, 0], arr[:, 1]
        return (sigma**2 * (1.0 - np.exp(-2.0 * float(dt) / rho)))[:, None, None]

    def observation(self, theta: NDArray[np.float64]) -> NDArray[np.float64]:
        """Return H = [1], shape (B, 1)."""
        return np.ones((np.shape(theta)[0], 1), dtype=np.float64)

    def measurement_variance(self, theta: NDArray[np.float64]) -> NDArray[np.float64]:
        """Return zeros — this family contributes no measurement noise."""
        return np.zeros(np.shape(theta)[0], dtype=np.float64)

    def acvf(self, theta: NDArray[np.float64], lags: NDArray[np.float64]) -> NDArray[np.float64]:
        """Return sigma^2 exp(-|tau| / rho), shape (B, n_lags)."""
        arr = np.asarray(theta, dtype=np.float64)
        sigma, rho = arr[:, 0][:, None], arr[:, 1][:, None]
        tau = np.abs(np.asarray(lags, dtype=np.float64))[None, :]
        return sigma**2 * np.exp(-tau / rho)
```

Import both from `src/metamer/core/families/__init__.py` so registration happens on
package import:

```python
# src/metamer/core/families/__init__.py
"""Kernel families. Importing this module registers every built-in family."""

from metamer.core.families import matern12, white  # noqa: F401

__all__ = ["matern12", "white"]
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pixi run test tests/test_families.py -v`
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add src/metamer/core/families tests/oracles.py tests/test_families.py
git commit -m "feat: add family protocol with white and Matern 1/2"
```

---

## Task 5: Matérn ν=3/2, composite assembly, and the defective-root guard

**Goal:** A `d=2` family with a repeated real root (so its closed form is a Jordan-block form, not an eigendecomposition), block-diagonal assembly of composites, and a condition-number guard on the general fallback path.

**Files:**
- Create: `src/metamer/core/families/matern32.py`, `src/metamer/core/statespace.py`
- Modify: `src/metamer/core/families/__init__.py`
- Create: `tests/test_statespace.py`; modify `tests/test_families.py`

**Acceptance Criteria:**
- [ ] `matern32.transition` matches `expm(A·dt)` to 1e-11 for `A = [[0, 1], [−λ², −2λ]]`
- [ ] `matern32.acvf(τ) == σ²(1 + λ|τ|)exp(−λ|τ|)` with `λ = √3/ρ`
- [ ] `StateSpace.from_spec(white + matern12 + matern32)` reports `state_dim == 3`
- [ ] Composite `F`, `Q`, `P∞` are block-diagonal; `H` concatenates; `R` sums
- [ ] `unique_dt` memoization returns one entry for a regular grid, `n` for an irregular one
- [ ] `eigen_transition` raises `DefectiveMatrixError` above a stated condition-number threshold, and the fallback to scaling-and-squaring is counted

**Verify:** `pixi run test tests/test_families.py tests/test_statespace.py -v`

**Steps:**

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_statespace.py
import numpy as np
import pytest

from metamer.core.families.matern12 import Matern12
from metamer.core.families.matern32 import Matern32
from metamer.core.statespace import DefectiveMatrixError, StateSpace, eigen_transition
from metamer.core.terms import ProcessSpec, TermSpec
from tests.oracles import expm_transition


def _term(kind: str, **defaults: float) -> TermSpec:
    from metamer.core.registry import kernel_registry

    family = kernel_registry[kind]()
    specs = family.param_specs()
    for name, value in defaults.items():
        specs[name] = type(specs[name])(
            name=specs[name].name,
            default=value,
            transform=specs[name].transform,
            bounds=specs[name].bounds,
            diagnostic_limits=specs[name].diagnostic_limits,
            fixed=specs[name].fixed,
            unit=specs[name].unit,
        )
    return TermSpec(kind=kind, params=specs, ordering_param=getattr(family, "ordering_param", None))


@pytest.mark.parametrize("dt", [0.2, 1.0, 5.0])
@pytest.mark.parametrize("rho", [1.0, 12.0])
def test_matern32_transition_matches_expm(dt, rho):
    """Analytic Jordan-form F equals expm(A dt) for the defective drift.

    Bug this catches: someone 'simplifying' Matern 3/2 into the general
    root-based CARMA path. Its root is repeated, so an eigendecomposition is
    defective and silently drops the t*exp(-lambda t) term.
    """
    lam = np.sqrt(3.0) / rho
    drift = np.array([[0.0, 1.0], [-(lam**2), -2.0 * lam]])
    theta = np.array([[1.0, rho]])
    np.testing.assert_allclose(
        Matern32().transition(theta, dt)[0], expm_transition(drift, dt), rtol=1e-11, atol=1e-13
    )


def test_matern32_acvf_matches_textbook_closed_form():
    """ACVF is sigma^2 (1 + lambda|tau|) exp(-lambda|tau|), lambda = sqrt(3)/rho.

    Expected value determined independently: standard Matern nu=3/2 kernel
    (Rasmussen & Williams eq. 4.17), written out by hand.
    """
    sigma, rho = 2.0, 3.0
    lam = np.sqrt(3.0) / rho
    lags = np.array([0.0, 0.5, 4.0])
    expected = sigma**2 * (1.0 + lam * lags) * np.exp(-lam * lags)
    np.testing.assert_allclose(
        Matern32().acvf(np.array([[sigma, rho]]), lags)[0], expected, rtol=1e-12
    )


def test_composite_state_dim_is_the_sum_of_its_terms():
    """white + matern12 + matern32 has d = 0 + 1 + 2 = 3.

    Expected value determined independently by adding the documented state
    dimensions. This is the d=3 spike configuration, and getting it wrong
    invalidates every memory figure that depends on d^2.
    """
    spec = ProcessSpec((_term("white"), _term("matern12"), _term("matern32")))
    assert StateSpace.from_spec(spec).state_dim == 3


def test_composite_matrices_are_block_diagonal():
    """Composite F places each term's block on the diagonal, zeros elsewhere.

    Bug this catches: assembling with a reshape instead of a block placement,
    which silently couples independent processes.
    """
    spec = ProcessSpec((_term("matern12", rho=2.0), _term("matern32", rho=9.0)))
    ss = StateSpace.from_spec(spec)
    theta = np.array([[1.0, 2.0, 1.0, 9.0]])
    f = ss.transition(theta, 1.0)[0]
    assert f.shape == (3, 3)
    np.testing.assert_allclose(f[0, 1:], 0.0, atol=0.0)
    np.testing.assert_allclose(f[1:, 0], 0.0, atol=0.0)


def test_measurement_variance_sums_over_terms():
    """R is the sum of every term's measurement-variance contribution.

    Bug this catches: taking the first term's R, which drops white noise
    whenever it is not sorted first.
    """
    spec = ProcessSpec((_term("white", sigma=0.5), _term("matern12")))
    ss = StateSpace.from_spec(spec)
    theta = np.array([[0.5, 1.0, 1.0]])
    assert ss.measurement_variance(theta)[0] == pytest.approx(0.25)


def test_unique_dt_collapses_a_regular_grid():
    """A regular time axis has exactly one unique dt.

    Bug this catches: recomputing F and Q at every one of N timesteps, which
    throws away the N-fold amortization that is the dominant win.
    """
    regular = np.arange(0.0, 10.0, 1.0)
    irregular = np.array([0.0, 1.0, 3.0, 6.0])
    assert StateSpace.unique_dt(regular).size == 1
    assert StateSpace.unique_dt(irregular).size == 3


def test_eigen_transition_refuses_a_near_defective_matrix():
    """The guard fires before the eigen route returns a quietly wrong answer.

    Bug this catches: silent precision loss as two roots coalesce. There is no
    exception from numpy here -- the eigenvector matrix simply becomes
    ill-conditioned and the result degrades continuously.
    """
    eps = 1e-12
    drift = np.array([[-1.0, 1.0], [0.0, -1.0 - eps]])
    with pytest.raises(DefectiveMatrixError):
        eigen_transition(drift, 1.0, cond_threshold=1e8)
```

- [ ] **Step 2: Run to verify failure**

Run: `pixi run test tests/test_statespace.py -v`
Expected: FAIL — modules missing

- [ ] **Step 3: Implement matern32.py**

```python
# src/metamer/core/families/matern32.py
"""Matern nu=3/2: d=2, repeated real root, Jordan-form closed solution.

The drift matrix has eigenvalue -lambda with multiplicity 2 and is therefore
defective. Its matrix exponential carries a t*exp(-lambda t) term that no
eigendecomposition can produce, which is why this family is a separate analytic
construction and NOT an instance of the general root-based CARMA path.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from metamer.core.capability import CostClass, EngineId, GradientMode, Objective
from metamer.core.params import ParamSpec
from metamer.core.registry import kernel_registry
from metamer.core.transforms import Log

_SQRT3 = np.sqrt(3.0)


@kernel_registry.register("matern32")
class Matern32:
    """Matern nu=3/2 with marginal standard deviation sigma and timescale rho."""

    kind = "matern32"
    state_dim = 2
    ordering_param = "rho"
    engine_costs = {
        EngineId.KALMAN: CostClass.LINEAR,
        EngineId.WHITTLE: CostClass.NLOGN,
        EngineId.TOEPLITZ: CostClass.CUBIC,
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

    @staticmethod
    def _lam(theta: NDArray[np.float64]) -> NDArray[np.float64]:
        return _SQRT3 / np.asarray(theta, dtype=np.float64)[:, 1]

    def transition(self, theta: NDArray[np.float64], dt: float) -> NDArray[np.float64]:
        """Return the Jordan-form F = exp(-lam dt) (I + dt (A + lam I))."""
        lam = self._lam(theta)
        t = float(dt)
        decay = np.exp(-lam * t)
        out = np.empty((lam.size, 2, 2), dtype=np.float64)
        out[:, 0, 0] = 1.0 + lam * t
        out[:, 0, 1] = t
        out[:, 1, 0] = -(lam**2) * t
        out[:, 1, 1] = 1.0 - lam * t
        return out * decay[:, None, None]

    def stationary_cov(self, theta: NDArray[np.float64]) -> NDArray[np.float64]:
        """Return diag(sigma^2, sigma^2 lam^2).

        Cov(f, f') = -k'(0) = 0 and Var(f') = -k''(0) = sigma^2 lam^2.
        """
        arr = np.asarray(theta, dtype=np.float64)
        sigma = arr[:, 0]
        lam = self._lam(arr)
        out = np.zeros((sigma.size, 2, 2), dtype=np.float64)
        out[:, 0, 0] = sigma**2
        out[:, 1, 1] = (sigma * lam) ** 2
        return out

    def process_noise(self, theta: NDArray[np.float64], dt: float) -> NDArray[np.float64]:
        """Return Q = P_inf - F P_inf F'."""
        p_inf = self.stationary_cov(theta)
        f = self.transition(theta, dt)
        return p_inf - f @ p_inf @ np.transpose(f, (0, 2, 1))

    def observation(self, theta: NDArray[np.float64]) -> NDArray[np.float64]:
        """Return H = [1, 0], shape (B, 2)."""
        out = np.zeros((np.shape(theta)[0], 2), dtype=np.float64)
        out[:, 0] = 1.0
        return out

    def measurement_variance(self, theta: NDArray[np.float64]) -> NDArray[np.float64]:
        """Return zeros — this family contributes no measurement noise."""
        return np.zeros(np.shape(theta)[0], dtype=np.float64)

    def acvf(self, theta: NDArray[np.float64], lags: NDArray[np.float64]) -> NDArray[np.float64]:
        """Return sigma^2 (1 + lam|tau|) exp(-lam|tau|), shape (B, n_lags)."""
        arr = np.asarray(theta, dtype=np.float64)
        sigma = arr[:, 0][:, None]
        lam = self._lam(arr)[:, None]
        tau = np.abs(np.asarray(lags, dtype=np.float64))[None, :]
        return sigma**2 * (1.0 + lam * tau) * np.exp(-lam * tau)
```

Add `matern32` to the imports in `src/metamer/core/families/__init__.py`.

- [ ] **Step 4: Implement statespace.py**

```python
# src/metamer/core/statespace.py
"""Composite state-space assembly and the defective-root guard."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.linalg import expm

from metamer.core.families.base import Family
from metamer.core.registry import kernel_registry
from metamer.core.terms import ProcessSpec


class DefectiveMatrixError(RuntimeError):
    """The eigenvector matrix is too ill-conditioned for the eigen route."""


def eigen_transition(
    drift: NDArray[np.float64], dt: float, cond_threshold: float = 1e8
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
    drift: NDArray[np.float64], dt: float, counter: dict[str, int] | None = None
) -> NDArray[np.float64]:
    """Transition matrix, falling back to scaling-and-squaring when defective.

    Args:
        drift: The drift matrix A.
        dt: Timestep.
        counter: Optional dict whose "fallback" key is incremented on fallback,
            so the rate can be surfaced as a diagnostic.

    Returns:
        expm(A * dt).
    """
    try:
        return eigen_transition(drift, dt)
    except DefectiveMatrixError:
        if counter is not None:
            counter["fallback"] = counter.get("fallback", 0) + 1
        return np.asarray(expm(np.asarray(drift, dtype=np.float64) * float(dt)))


@dataclass(frozen=True)
class StateSpace:
    """A composite state space assembled block-diagonally from its terms."""

    families: tuple[Family, ...]
    slices: tuple[slice, ...]
    param_slices: tuple[slice, ...]
    state_dim: int

    @classmethod
    def from_spec(cls, spec: ProcessSpec) -> StateSpace:
        """Assemble from a canonically ordered ProcessSpec.

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
    def unique_dt(t: NDArray[np.float64]) -> NDArray[np.float64]:
        """Return the sorted unique timesteps of a shared time axis.

        On a regular grid this has one entry, so F and Q are computed once per
        series per optimizer iteration rather than once per timestep.
        """
        return np.unique(np.diff(np.asarray(t, dtype=np.float64)))

    def _assemble(self, theta: NDArray[np.float64], method: str, *args: float) -> NDArray[np.float64]:
        arr = np.asarray(theta, dtype=np.float64)
        batch = arr.shape[0]
        out = np.zeros((batch, self.state_dim, self.state_dim), dtype=np.float64)
        for family, block, pslice in zip(self.families, self.slices, self.param_slices, strict=True):
            if family.state_dim == 0:
                continue
            out[:, block, block] = getattr(family, method)(arr[:, pslice], *args)
        return out

    def transition(self, theta: NDArray[np.float64], dt: float) -> NDArray[np.float64]:
        """Return the block-diagonal composite F, shape (B, d, d)."""
        return self._assemble(theta, "transition", dt)

    def process_noise(self, theta: NDArray[np.float64], dt: float) -> NDArray[np.float64]:
        """Return the block-diagonal composite Q, shape (B, d, d)."""
        return self._assemble(theta, "process_noise", dt)

    def stationary_cov(self, theta: NDArray[np.float64]) -> NDArray[np.float64]:
        """Return the block-diagonal composite P_inf, shape (B, d, d)."""
        return self._assemble(theta, "stationary_cov")

    def observation(self, theta: NDArray[np.float64]) -> NDArray[np.float64]:
        """Return the concatenated observation row H, shape (B, d)."""
        arr = np.asarray(theta, dtype=np.float64)
        out = np.zeros((arr.shape[0], self.state_dim), dtype=np.float64)
        for family, block, pslice in zip(self.families, self.slices, self.param_slices, strict=True):
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

    def acvf(self, theta: NDArray[np.float64], lags: NDArray[np.float64]) -> NDArray[np.float64]:
        """Return the summed autocovariance, shape (B, n_lags)."""
        arr = np.asarray(theta, dtype=np.float64)
        total = np.zeros((arr.shape[0], np.size(lags)), dtype=np.float64)
        for family, pslice in zip(self.families, self.param_slices, strict=True):
            total = total + family.acvf(arr[:, pslice], lags)
        return total
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pixi run test tests/test_families.py tests/test_statespace.py -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add src/metamer/core/families/matern32.py src/metamer/core/statespace.py src/metamer/core/families/__init__.py tests/test_statespace.py
git commit -m "feat: add Matern 3/2, composite assembly, and defective-root guard"
```

---

## Task 6: Engine protocol and the batched Kalman filter

**Goal:** An `Engine` protocol and a batched, masked, scalar-observation Kalman filter that accumulates whitened cross-products for an augmented observation matrix `[y | X]`. Validated against the brute-force MVN oracle.

The filter is **written augmented from the start**. Task 8 supplies a non-empty `X`; here `X` is empty and the accumulator is 1×1. Building the y-only version first and generalising later would be exactly the rework this design avoids.

**Files:**
- Create: `src/metamer/core/engines/protocol.py`, `src/metamer/core/engines/kalman.py`
- Create: `tests/test_kalman.py`

**Acceptance Criteria:**
- [ ] Filter log-likelihood matches `mvn_loglik` with an explicitly built Toeplitz covariance to 1e-9 for `matern12`, `matern32`, and `white + matern12 + matern32`
- [ ] A series with masked points gives **exactly** the same log-likelihood as the same series with those points genuinely absent (to 1e-12)
- [ ] `B = 1` and `B = 64` produce identical per-series results for identical inputs
- [ ] `F`/`Q` are computed once per unique Δt, verified by a call counter on a regular grid
- [ ] `ScoredResult` carries both `engine` and `objective` tags

**Verify:** `pixi run test tests/test_kalman.py -v` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_kalman.py
import numpy as np
import pytest
from scipy.linalg import toeplitz

from metamer.core.capability import EngineId
from metamer.core.engines.kalman import KalmanEngine
from metamer.core.statespace import StateSpace
from metamer.core.terms import ProcessSpec
from tests.oracles import mvn_loglik
from tests.test_statespace import _term


def _covariance(ss: StateSpace, theta: np.ndarray, t: np.ndarray) -> np.ndarray:
    """Build Sigma explicitly from the analytic ACVF plus measurement noise."""
    lags = np.abs(t[:, None] - t[None, :])
    acv = ss.acvf(theta, np.unique(lags))[0]
    lookup = dict(zip(np.unique(lags), acv, strict=True))
    cov = np.vectorize(lookup.get)(lags).astype(np.float64)
    return cov + np.eye(t.size) * ss.measurement_variance(theta)[0]


@pytest.mark.parametrize(
    "kinds, theta",
    [
        (["matern12"], [1.3, 4.0]),
        (["matern32"], [0.8, 6.0]),
        (["white", "matern12", "matern32"], [0.25, 1.3, 4.0, 0.8, 11.0]),
    ],
)
def test_filter_loglik_matches_brute_force_mvn(kinds, theta):
    """The Kalman log-likelihood equals an explicit MVN density.

    The oracle is built from analytic autocovariances and an explicit
    covariance matrix, so it is independent of the entire state-space
    formulation. This is the primary correctness test for the engine.

    Bug this catches: a missing 2*pi, a dropped log|S| term, or an incorrect
    stationary initialisation -- each of which shifts the likelihood by a
    constant and silently biases every information criterion.
    """
    spec = ProcessSpec(tuple(_term(k) for k in kinds))
    ss = StateSpace.from_spec(spec)
    theta_b = np.array([theta], dtype=np.float64)
    t = np.arange(24.0)
    rng = np.random.default_rng(0)
    cov = _covariance(ss, theta_b, t)
    y = rng.multivariate_normal(np.zeros(t.size), cov)[None, :]
    mask = np.ones_like(y, dtype=bool)

    result = KalmanEngine().score(ss, theta_b, y, mask, t, design=None)
    assert result.loglik[0] == pytest.approx(mvn_loglik(y[0], cov), abs=1e-9)


def test_masked_points_equal_genuinely_absent_points():
    """Masking a sample gives the same likelihood as deleting it.

    Bug this catches: applying the update with a zero innovation instead of
    skipping it, which adds a spurious log|S| term per gap and biases every
    fit on gappy series -- exactly the high-latitude sea-ice case.
    """
    spec = ProcessSpec((_term("matern12"),))
    ss = StateSpace.from_spec(spec)
    theta = np.array([[1.0, 5.0]])
    t_full = np.arange(20.0)
    rng = np.random.default_rng(1)
    y_full = rng.standard_normal((1, 20))
    keep = np.ones(20, dtype=bool)
    keep[[3, 4, 5, 11]] = False

    masked = KalmanEngine().score(
        ss, theta, y_full, keep[None, :], t_full, design=None
    )
    absent = KalmanEngine().score(
        ss, theta, y_full[:, keep], np.ones((1, keep.sum()), dtype=bool), t_full[keep], design=None
    )
    assert masked.loglik[0] == pytest.approx(absent.loglik[0], abs=1e-12)


def test_masked_update_leaves_the_covariance_untouched():
    """At a masked epoch P is unchanged, not merely gain-scaled.

    Bug this catches: applying the update with a zeroed gain, which still
    shrinks P by `- 0 * H P` only if the arithmetic is exactly right and
    corrupts it otherwise. This is a numerical error that survives every
    structural test, so it is asserted directly on the state.
    """
    spec = ProcessSpec((_term("matern12"),))
    ss = StateSpace.from_spec(spec)
    theta = np.array([[1.0, 5.0]])
    t = np.array([0.0, 1.0])
    y = np.array([[3.0, 3.0]])

    engine = KalmanEngine()
    all_masked = engine.score(ss, theta, y, np.zeros_like(y, dtype=bool), t, design=None)
    # With every epoch masked the filter never updates, so nothing accumulates.
    assert all_masked.n_used[0] == 0
    assert all_masked.loglik[0] == pytest.approx(0.0, abs=1e-15)
    assert all_masked.normal_equations[0, 0, 0] == pytest.approx(0.0, abs=1e-15)


def test_log_determinant_accumulates_only_over_unmasked_epochs():
    """sum log S counts exactly the observed epochs.

    Expected value determined independently: for white noise of variance
    sigma^2 with no state, S = sigma^2 at every epoch, so the log-likelihood
    over m observed points is -0.5*m*(log(2 pi sigma^2) + y^2/sigma^2).

    Bug this catches: accumulating log S at masked epochs, which adds a
    spurious constant per gap and biases every fit on gappy series.
    """
    spec = ProcessSpec((_term("white"),))
    ss = StateSpace.from_spec(spec)
    sigma = 2.0
    theta = np.array([[sigma]])
    t = np.arange(6.0)
    y = np.full((1, 6), 1.5)
    mask = np.array([[True, False, True, False, True, False]])

    got = KalmanEngine().score(ss, theta, y, mask, t, design=None).loglik[0]
    m = int(mask.sum())
    expected = -0.5 * m * (np.log(2 * np.pi * sigma**2) + (1.5 / sigma) ** 2)
    assert got == pytest.approx(expected, abs=1e-12)


def test_batch_of_one_matches_batch_of_many():
    """B=1 is a shape, not a code path.

    Bug this catches: a broadcasting error that only appears at B>1, or a
    special case for B=1 that drifts from the batched path.
    """
    spec = ProcessSpec((_term("matern12"),))
    ss = StateSpace.from_spec(spec)
    rng = np.random.default_rng(2)
    theta = np.repeat(np.array([[1.0, 3.0]]), 64, axis=0)
    t = np.arange(30.0)
    y = rng.standard_normal((64, 30))
    mask = np.ones_like(y, dtype=bool)

    many = KalmanEngine().score(ss, theta, y, mask, t, design=None)
    one = KalmanEngine().score(ss, theta[:1], y[:1], mask[:1], t, design=None)
    assert many.loglik[0] == pytest.approx(one.loglik[0], abs=1e-12)


def test_transition_is_computed_once_per_unique_dt():
    """A regular grid triggers exactly one transition build.

    Bug this catches: rebuilding F and Q inside the time loop, which discards
    the N-fold amortization that the whole performance argument rests on.
    """
    spec = ProcessSpec((_term("matern12"),))
    ss = StateSpace.from_spec(spec)
    calls = {"n": 0}
    original = ss.transition

    def counting(theta, dt):
        calls["n"] += 1
        return original(theta, dt)

    object.__setattr__(ss, "transition", counting)
    t = np.arange(50.0)
    y = np.zeros((1, 50))
    KalmanEngine().score(ss, np.array([[1.0, 4.0]]), y, np.ones_like(y, dtype=bool), t, design=None)
    assert calls["n"] == 1


def test_result_carries_engine_tag():
    """Every score is tagged with the engine that produced it.

    Bug this catches: an untagged score reaching the selection layer, where
    the comparability guard could not then refuse a cross-engine comparison.
    """
    spec = ProcessSpec((_term("matern12"),))
    ss = StateSpace.from_spec(spec)
    t = np.arange(8.0)
    y = np.zeros((1, 8))
    result = KalmanEngine().score(ss, np.array([[1.0, 2.0]]), y, np.ones_like(y, dtype=bool), t, design=None)
    assert result.engine is EngineId.KALMAN
```

- [ ] **Step 2: Run to verify failure**

Run: `pixi run test tests/test_kalman.py -v`
Expected: FAIL — engine modules missing

- [ ] **Step 3: Implement the engine protocol**

```python
# src/metamer/core/engines/protocol.py
"""The engine protocol and the tagged score it returns."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import numpy as np
from numpy.typing import NDArray

from metamer.core.capability import EngineId, Objective
from metamer.core.statespace import StateSpace


@dataclass(frozen=True)
class ScoredResult:
    """A likelihood evaluation, tagged with its engine and objective.

    The tags are load-bearing. A Whittle score is not an exact likelihood, and
    an ML and a REML likelihood live on different measures. Both look
    commensurable and are not, so the selection layer refuses to rank across
    either tag.

    Attributes:
        loglik: Log-likelihood per series, shape (B,).
        engine: Which engine produced this score.
        objective: Which objective this score is on.
        n_used: Number of unmasked observations per series, shape (B,).
        rank_x: Numerical rank of the design matrix per series, shape (B,).
        normal_equations: Accumulated whitened cross-products, (B, 1+k, 1+k).
    """

    loglik: NDArray[np.float64]
    engine: EngineId
    objective: Objective
    n_used: NDArray[np.int64]
    rank_x: NDArray[np.int64]
    normal_equations: NDArray[np.float64]


@runtime_checkable
class Engine(Protocol):
    """Evaluates a likelihood for a state space over a batch of series."""

    engine_id: EngineId

    def score(
        self,
        state_space: StateSpace,
        theta: NDArray[np.float64],
        y: NDArray[np.float64],
        mask: NDArray[np.bool_],
        t: NDArray[np.float64],
        design: NDArray[np.float64] | None,
        objective: Objective = Objective.ML,
    ) -> ScoredResult:
        """Return the tagged log-likelihood for each series in the batch."""
        ...
```

- [ ] **Step 4: Implement the batched Kalman filter**

```python
# src/metamer/core/engines/kalman.py
"""Batched Kalman filter: scalar observations, masked gaps, augmented GLS.

Two structural facts make this simple. The observation is scalar, so the
innovation variance S = H P H' + R is a scalar and there is no inverse, no
Cholesky and no pivoting anywhere in the filter. And P_inf is analytic per
family, so there is no Lyapunov solve either. The filter is therefore analytic
in theta end to end, which is what makes exact-gradient options available.

Because P and S do not depend on the data, one covariance recursion serves the
observation column and every design column at once: the filter runs on the
augmented matrix [y | X] and accumulates the whitened cross-products from which
the GLS solution and the REML penalty both follow.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from metamer.core.capability import EngineId, Objective
from metamer.core.engines.protocol import ScoredResult
from metamer.core.statespace import StateSpace

_RANK_RTOL = 1e-10


class KalmanEngine:
    """Exact O(N) state-space likelihood, vectorized over the series axis."""

    engine_id = EngineId.KALMAN

    def score(
        self,
        state_space: StateSpace,
        theta: NDArray[np.float64],
        y: NDArray[np.float64],
        mask: NDArray[np.bool_],
        t: NDArray[np.float64],
        design: NDArray[np.float64] | None,
        objective: Objective = Objective.ML,
    ) -> ScoredResult:
        """Filter a batch of series and accumulate whitened cross-products.

        Args:
            state_space: Composite state space for this candidate.
            theta: Noise parameters in natural units, shape (B, p).
            y: Observations, shape (B, N).
            mask: True where an observation is present, shape (B, N).
            t: Shared time axis, shape (N,).
            design: Optional design matrix, shape (N, k) if shared across
                series or (B, N, k) if per-point.
            objective: Recorded on the result; the penalty itself is applied by
                `metamer.core.objective`.

        Returns:
            A ScoredResult whose `loglik` is the y-only Gaussian log-likelihood
            and whose `normal_equations` is the (B, 1+k, 1+k) accumulator.
        """
        theta = np.asarray(theta, dtype=np.float64)
        y = np.asarray(y, dtype=np.float64)
        mask = np.asarray(mask, dtype=bool)
        t = np.asarray(t, dtype=np.float64)
        batch, n_time = y.shape
        dim = state_space.state_dim

        cols = self._augment(y, design, batch, n_time)
        n_cols = cols.shape[2]

        # F and Q depend on theta and dt only, so memoize on unique dt.
        # On a regular grid this loop body runs exactly once.
        matrices: dict[float, tuple[NDArray[np.float64], NDArray[np.float64]]] = {}
        for dt in state_space.unique_dt(t):
            matrices[float(dt)] = (
                state_space.transition(theta, float(dt)),
                state_space.process_noise(theta, float(dt)),
            )

        h = state_space.observation(theta)
        r = state_space.measurement_variance(theta)
        p = state_space.stationary_cov(theta)
        x = np.zeros((batch, dim, n_cols), dtype=np.float64)

        accum = np.zeros((batch, n_cols, n_cols), dtype=np.float64)
        sum_log_s = np.zeros(batch, dtype=np.float64)
        n_used = np.zeros(batch, dtype=np.int64)

        for step in range(n_time):
            if step > 0:
                f, q = matrices[float(t[step] - t[step - 1])]
                x = f @ x
                p = f @ p @ np.transpose(f, (0, 2, 1)) + q

            active = mask[:, step]
            if not active.any():
                continue

            hp = np.einsum("bd,bde->be", h, p)            # (B, d)
            s = np.einsum("be,be->b", hp, h) + r          # (B,)
            v = cols[:, step, :] - np.einsum("bd,bdc->bc", h, x)   # (B, n_cols)
            gain = hp / s[:, None]                        # (B, d)

            upd_x = x + gain[:, :, None] * v[:, None, :]
            upd_p = p - gain[:, :, None] * hp[:, None, :]

            w = active.astype(np.float64)
            x = np.where(active[:, None, None], upd_x, x)
            p = np.where(active[:, None, None], upd_p, p)

            accum += (w / s)[:, None, None] * v[:, :, None] * v[:, None, :]
            sum_log_s += w * np.log(s)
            n_used += active.astype(np.int64)

        loglik = -0.5 * (
            n_used.astype(np.float64) * np.log(2.0 * np.pi) + sum_log_s + accum[:, 0, 0]
        )
        rank_x = self._rank(accum[:, 1:, 1:]) if n_cols > 1 else np.zeros(batch, dtype=np.int64)

        return ScoredResult(
            loglik=loglik,
            engine=self.engine_id,
            objective=objective,
            n_used=n_used,
            rank_x=rank_x,
            normal_equations=accum,
        )

    @staticmethod
    def _augment(
        y: NDArray[np.float64],
        design: NDArray[np.float64] | None,
        batch: int,
        n_time: int,
    ) -> NDArray[np.float64]:
        """Stack [y | X] into a (B, N, 1+k) array of filtered columns."""
        if design is None:
            return y[:, :, None]
        x = np.asarray(design, dtype=np.float64)
        if x.ndim == 2:
            x = np.broadcast_to(x, (batch, n_time, x.shape[1]))
        return np.concatenate([y[:, :, None], x], axis=2)

    @staticmethod
    def _rank(xtx: NDArray[np.float64]) -> NDArray[np.int64]:
        """Numerical rank of each accumulated X' Sigma^-1 X block."""
        values = np.linalg.svdvals(xtx)
        tol = _RANK_RTOL * values[:, :1]
        return (values > tol).sum(axis=1).astype(np.int64)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pixi run test tests/test_kalman.py -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add src/metamer/core/engines tests/test_kalman.py
git commit -m "feat: add batched Kalman engine with masked gaps and augmented GLS"
```

---

## Task 7: Signal spec, design matrix, rank(X), linear/nonlinear taxonomy

**Goal:** Every signal term synesthesia needs, plus offsets and rate changes, with the linear/nonlinear split and its dispatch present from day one and nonlinear terms raising `NotImplementedError`.

**Files:**
- Create: `src/metamer/core/signal.py`
- Create: `tests/test_signal.py`

**Acceptance Criteria:**
- [ ] `constant`, `trend`, `accel`, `annual`, `semiannual`, `offset`, `rate_change` all build correct columns
- [ ] Harmonic columns are `[cos(2πt/P), sin(2πt/P)]` with `P` in the time axis's own units
- [ ] An offset epoch **at the first sample** yields an all-ones column; **after the last sample** yields an all-zeros column and is flagged rank-deficient
- [ ] A rate change with no samples on one side yields an all-zeros column
- [ ] `rank(X)` is computed by SVD with a stated tolerance and returned alongside `X`
- [ ] `ExpDecay` and `LogDecay` are constructible and raise `NotImplementedError` from `design_matrix`
- [ ] `SignalSpec.is_linear` is `False` when any nonlinear term is present

**Verify:** `pixi run test tests/test_signal.py -v` → all pass

**Steps:**

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_signal.py
import numpy as np
import pytest

from metamer.core.signal import (
    Accel,
    Annual,
    Constant,
    ExpDecay,
    Offset,
    RateChange,
    SemiAnnual,
    SignalSpec,
    Trend,
)


def test_polynomial_columns_are_powers_of_centred_time():
    """constant/trend/accel are t^0, t^1, t^2/2 about the record mean.

    Expected value determined independently: centring at t.mean() is stated in
    the docstring, so for t = [0,1,2] the trend column is [-1,0,1] and the
    acceleration column is [0.5,0,0.5].
    """
    t = np.array([0.0, 1.0, 2.0])
    x, _ = SignalSpec([Constant(), Trend(), Accel()]).design_matrix(t)
    np.testing.assert_allclose(x[:, 0], [1.0, 1.0, 1.0])
    np.testing.assert_allclose(x[:, 1], [-1.0, 0.0, 1.0])
    np.testing.assert_allclose(x[:, 2], [0.5, 0.0, 0.5])


def test_harmonic_columns_are_cosine_then_sine():
    """A harmonic contributes cos then sin at 2*pi*t/period.

    Bug this catches: swapping the column order, which silently swaps the
    reported amplitude and phase of the annual cycle.
    """
    t = np.array([0.0, 0.25, 0.5])
    x, _ = SignalSpec([Annual(period=1.0)]).design_matrix(t)
    np.testing.assert_allclose(x[:, 0], np.cos(2 * np.pi * t), atol=1e-14)
    np.testing.assert_allclose(x[:, 1], np.sin(2 * np.pi * t), atol=1e-14)


def test_offset_at_first_sample_is_all_ones():
    """An offset at or before t[0] steps the entire record.

    Bug this catches: a strict `>` comparison, which would make an offset at
    the first epoch an all-zeros column indistinguishable from a no-op.
    """
    t = np.arange(5.0)
    x, _ = SignalSpec([Offset(epoch=0.0)]).design_matrix(t)
    np.testing.assert_allclose(x[:, 0], np.ones(5))


def test_offset_after_last_sample_is_rank_deficient():
    """An out-of-record offset produces a zero column and drops the rank.

    Bug this catches: letting an all-zero column through, where log|X'S^-1X|
    is undefined and the fit returns NaN rather than a named failure.
    """
    t = np.arange(5.0)
    x, rank = SignalSpec([Constant(), Offset(epoch=99.0)]).design_matrix(t)
    np.testing.assert_allclose(x[:, 1], np.zeros(5))
    assert rank == 1


def test_rate_change_with_no_samples_after_the_break_is_zero():
    """A piecewise rate change beyond the record contributes nothing.

    Bug this catches: producing negative ramp values before the break, which
    would silently redefine the term as a two-sided hinge.
    """
    t = np.arange(5.0)
    x, _ = SignalSpec([RateChange(epoch=10.0)]).design_matrix(t)
    np.testing.assert_allclose(x[:, 0], np.zeros(5))


def test_nonlinear_terms_are_classified_and_refused():
    """Nonlinear terms exist in the taxonomy but are not implemented.

    Bug this catches: omitting the taxonomy entirely, which means retrofitting
    the linear/nonlinear dispatch later requires rewriting the fit driver.
    """
    spec = SignalSpec([Constant(), ExpDecay(epoch=0.0)])
    assert spec.is_linear is False
    with pytest.raises(NotImplementedError, match="nonlinear"):
        spec.design_matrix(np.arange(5.0))


def test_semiannual_period_is_half_the_annual_period():
    """SemiAnnual defaults to half of Annual's default period.

    Expected value determined independently: 'semiannual' means twice per
    year, so period = 0.5 yr when the axis is in years.
    """
    assert SemiAnnual().period == pytest.approx(Annual().period / 2.0)
```

- [ ] **Step 2: Run to verify failure**

Run: `pixi run test tests/test_signal.py -v`
Expected: FAIL — `metamer.core.signal` missing

- [ ] **Step 3: Implement signal.py**

```python
# src/metamer/core/signal.py
"""Deterministic signal terms and design-matrix construction.

Linear terms are profiled out analytically by GLS at each noise-parameter
evaluation. Nonlinear terms (exponential and logarithmic decays) break that and
require joint optimization; the taxonomy and the dispatch exist from day one so
the fit driver never has to be rewritten to accommodate them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import numpy as np
from numpy.typing import NDArray

RANK_RTOL = 1e-10
"""Relative singular-value tolerance for the numerical rank of X."""


@runtime_checkable
class SignalTerm(Protocol):
    """One deterministic term contributing columns to the design matrix."""

    linear: bool

    def columns(self, t: NDArray[np.float64]) -> NDArray[np.float64]:
        """Return this term's design columns, shape (n, n_cols)."""
        ...


@dataclass(frozen=True)
class Constant:
    """An intercept."""

    linear: bool = True

    def columns(self, t: NDArray[np.float64]) -> NDArray[np.float64]:
        """Return a column of ones."""
        return np.ones((t.size, 1), dtype=np.float64)


@dataclass(frozen=True)
class Trend:
    """A linear rate, in time units centred on the record mean."""

    linear: bool = True

    def columns(self, t: NDArray[np.float64]) -> NDArray[np.float64]:
        """Return (t - mean(t))."""
        return (t - t.mean())[:, None]


@dataclass(frozen=True)
class Accel:
    """A quadratic term, parameterized so its coefficient is an acceleration."""

    linear: bool = True

    def columns(self, t: NDArray[np.float64]) -> NDArray[np.float64]:
        """Return (t - mean(t))^2 / 2."""
        return (0.5 * (t - t.mean()) ** 2)[:, None]


@dataclass(frozen=True)
class Harmonic:
    """A cosine/sine pair at a specified period, in the time axis's units."""

    period: float
    linear: bool = True

    def columns(self, t: NDArray[np.float64]) -> NDArray[np.float64]:
        """Return [cos(2 pi t / P), sin(2 pi t / P)]."""
        phase = 2.0 * np.pi * t / self.period
        return np.column_stack([np.cos(phase), np.sin(phase)])


@dataclass(frozen=True)
class Annual(Harmonic):
    """The annual cycle. Default period assumes a time axis in years."""

    period: float = 1.0


@dataclass(frozen=True)
class SemiAnnual(Harmonic):
    """The semiannual cycle: twice per year, hence half the annual period."""

    period: float = 0.5


@dataclass(frozen=True)
class Offset:
    """A step of unit height at a user-supplied epoch.

    Breakpoint epochs are user-supplied in v1. Breakpoint *detection* is out of
    scope and is not silently approximated: an undetected offset is nearly
    indistinguishable from random-walk noise, a well-known trap in GNSS trend
    estimation.
    """

    epoch: float
    linear: bool = True

    def columns(self, t: NDArray[np.float64]) -> NDArray[np.float64]:
        """Return 1 where t >= epoch, else 0."""
        return (t >= self.epoch).astype(np.float64)[:, None]


@dataclass(frozen=True)
class RateChange:
    """A one-sided ramp starting at a user-supplied epoch."""

    epoch: float
    linear: bool = True

    def columns(self, t: NDArray[np.float64]) -> NDArray[np.float64]:
        """Return max(t - epoch, 0)."""
        return np.maximum(t - self.epoch, 0.0)[:, None]


@dataclass(frozen=True)
class Regressor:
    """An external regressor supplied as a column of values."""

    values: NDArray[np.float64]
    name: str = "regressor"
    linear: bool = True

    def columns(self, t: NDArray[np.float64]) -> NDArray[np.float64]:
        """Return the supplied values as a single column."""
        arr = np.asarray(self.values, dtype=np.float64)
        if arr.shape[0] != t.size:
            raise ValueError(f"{self.name}: length {arr.shape[0]} != time axis {t.size}")
        return arr.reshape(t.size, -1)


@dataclass(frozen=True)
class ExpDecay:
    """Exponential decay from an epoch. Nonlinear in its timescale."""

    epoch: float
    linear: bool = False

    def columns(self, t: NDArray[np.float64]) -> NDArray[np.float64]:
        """Not available on the concentrated path."""
        raise NotImplementedError("ExpDecay is nonlinear; joint optimization is Phase 4")


@dataclass(frozen=True)
class LogDecay:
    """Logarithmic decay from an epoch. Nonlinear in its timescale."""

    epoch: float
    linear: bool = False

    def columns(self, t: NDArray[np.float64]) -> NDArray[np.float64]:
        """Not available on the concentrated path."""
        raise NotImplementedError("LogDecay is nonlinear; joint optimization is Phase 4")


@dataclass(frozen=True)
class DesignInfo:
    """A built design matrix and everything derived from it that is theta-free.

    `gram_logdet` is log|X'X|, the REML basis-invariance term. It is a property
    of X alone, so computing it inside the likelihood would recompute a fixed
    quantity ~50 times per fit, 12 candidates per point, 10^7 points.

    SEAM (Phase 2, per-point regressors): when a regressor is a per-point field
    -- a GIA model -- `matrix` becomes (B, N, k), `rank` and `gram_logdet`
    become shape (B,), and `per_point` becomes True. Every consumer already
    takes this object rather than a loose (design, rank) pair, so that change is
    a shape widening, not a signature rewrite. It also triggers the
    N*k_beta*8-per-series memory term, which dominates the per-series budget.
    """

    matrix: NDArray[np.float64]
    rank: int
    gram_logdet: float
    per_point: bool = False

    @property
    def n_beta(self) -> int:
        """Number of design columns."""
        return int(self.matrix.shape[-1])

    @property
    def is_deficient(self) -> bool:
        """Whether the design is rank-deficient."""
        return bool(self.matrix.size and self.rank < self.n_beta)


@dataclass(frozen=True)
class SignalSpec:
    """An ordered collection of deterministic signal terms."""

    terms: list[SignalTerm]

    def design_info(self, t: NDArray[np.float64]) -> DesignInfo:
        """Build the design matrix and its theta-free derived quantities once.

        Args:
            t: Time axis, shape (n,).

        Returns:
            A DesignInfo. `gram_logdet` is -inf for a rank-deficient design; the
            caller classifies that as RANK_DEFICIENT_X rather than using it.
        """
        matrix, rank = self.design_matrix(t)
        if matrix.size == 0:
            return DesignInfo(matrix, 0, 0.0)
        sign, logdet = np.linalg.slogdet(matrix.T @ matrix)
        return DesignInfo(matrix, rank, float(logdet) if sign > 0 else float("-inf"))

    @property
    def is_linear(self) -> bool:
        """True when every term is linear in its parameters."""
        return all(term.linear for term in self.terms)

    def design_matrix(
        self, t: NDArray[np.float64]
    ) -> tuple[NDArray[np.float64], int]:
        """Build the design matrix and its numerical rank.

        Args:
            t: Time axis, shape (n,).

        Returns:
            A tuple of the design matrix (n, k) and its numerical rank.

        Raises:
            NotImplementedError: If any term is nonlinear. Phase 1 implements
                only the GLS-concentrated linear path.
        """
        if not self.is_linear:
            raise NotImplementedError(
                "This signal specification contains nonlinear terms; only the "
                "GLS-concentrated linear path is implemented in Phase 1"
            )
        t = np.asarray(t, dtype=np.float64)
        if not self.terms:
            return np.zeros((t.size, 0), dtype=np.float64), 0
        x = np.concatenate([term.columns(t) for term in self.terms], axis=1)
        return x, self.rank(x)

    @staticmethod
    def rank(x: NDArray[np.float64]) -> int:
        """Numerical rank of a design matrix by SVD, with a stated tolerance."""
        if x.size == 0:
            return 0
        values = np.linalg.svdvals(x)
        if values[0] == 0.0:
            return 0
        return int((values > RANK_RTOL * values[0]).sum())

    def n_beta(self, t: NDArray[np.float64]) -> int:
        """Number of design columns for this time axis."""
        return int(self.design_matrix(t)[0].shape[1])
```

- [ ] **Step 4: Run tests and commit**

Run: `pixi run test tests/test_signal.py -v` → all PASS

```bash
git add src/metamer/core/signal.py tests/test_signal.py
git commit -m "feat: add signal terms, design matrix, and linear/nonlinear taxonomy"
```

---

## Task 8: GLS profiling and the ML concentrated objective

**Goal:** Profile `β` out of the likelihood using the accumulator the filter already produces, and expose the concentrated ML objective in unconstrained coordinates.

**Files:**
- Create: `src/metamer/core/objective.py`
- Create: `tests/test_objective.py`

**Acceptance Criteria:**
- [ ] `β̂` from the accumulator matches an explicit `(XᵀΣ⁻¹X)⁻¹XᵀΣ⁻¹y` inversion to 1e-9
- [ ] Concentrated ML log-likelihood matches `mvn_loglik(y, Σ, design=X)` to 1e-9
- [ ] `β` covariance matches `(XᵀΣ⁻¹X)⁻¹` to 1e-9
- [ ] A rank-deficient `X` returns `Outcome.RANK_DEFICIENT_X` **before any factorization**, never NaN with `OK` and never an uncaught `LinAlgError`
- [ ] The objective accepts unconstrained `u` and maps through the spec's bijectors
- [ ] **`to_natural`, `to_unconstrained` and `dforward` all drive off `free_param_index`** — no local re-derivation of the layout, and fixed parameters are excluded
- [ ] **REML absolute log-likelihood matches an independently-written brute-force oracle** at small N, with the convention named in both. A differential test against ML cannot see a constant offset and is not sufficient.
- [ ] The REML constant is `(n − rank(X))·log(2π)`, not `n·log(2π)`, and the basis-invariance term `+½log|XᵀX|` is present
- [ ] `GlsResult` is produced by **one** `cho_factor` and carries `beta`, `beta_cov`, `logdet`, `rss_reduction` and an `Outcome` — no second solve, no `np.linalg.inv`
- [ ] The σ²-profiling decision is stated in the module docstring with its reason
- [ ] **Outcomes are per series everywhere they cross a batched boundary** — `GlsResult.outcome` and `ObjectiveResult.outcome` are shape `(B,)` `uint8`, never a scalar
- [ ] **`np.linalg.slogdet` builds the validity mask before any factorization**; only the valid subset is factorized and results are scattered back, so one bad series cannot fail the stack
- [ ] **A shared, globally full-rank design still fails per series when a gap removes a column's support** — an offset epoch inside a masked window marks that series alone, with NaN, while every other series is `OK`, finite, and equal to its solo fit
- [ ] The three-way split is exercised: full support → `OK`; two post-breakpoint samples → `ILL_CONDITIONED_X`; none → `RANK_DEFICIENT_X`
- [ ] `check_design` passing is shown to be **necessary but not sufficient** — a design it accepts still yields a per-series failure
- [ ] **Failed series carry NaN, not −inf**, in anything destined for the store; −inf appears only as the optimizer's internal barrier in `optimize_series`
- [ ] `log|XᵀX|` is computed once on `DesignInfo`, never inside the likelihood
- [ ] `Outcome.code` values are stable and documented as never renumbered

**Verify:** `pixi run test tests/test_objective.py -v`

**Steps:**

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_objective.py
import numpy as np
import pytest

from metamer.core.capability import Objective
from metamer.core.engines.kalman import KalmanEngine
from metamer.core.objective import ConcentratedObjective
from metamer.core.signal import DesignInfo, gls_solution
from metamer.core.signal import Constant, Offset, SignalSpec, Trend
from metamer.core.statespace import StateSpace
from metamer.core.terms import ProcessSpec
from tests.oracles import mvn_loglik, reml_loglik, reml_penalty
from tests.test_kalman import _covariance
from tests.test_statespace import _term


def _setup(seed: int = 3, n: int = 40):
    spec = ProcessSpec((_term("white"), _term("matern12")))
    ss = StateSpace.from_spec(spec)
    theta = np.array([[0.4, 1.2, 6.0]])
    t = np.arange(float(n))
    signal = SignalSpec([Constant(), Trend()])
    design = signal.design_info(t)
    x = design.matrix
    cov = _covariance(ss, theta, t)
    rng = np.random.default_rng(seed)
    y = (rng.multivariate_normal(np.zeros(n), cov) + 2.0 + 0.05 * (t - t.mean()))[None, :]
    return spec, ss, theta, t, design, cov, y


def test_beta_hat_matches_explicit_gls():
    """Profiled beta equals an explicit generalized-least-squares inversion.

    Bug this catches: partitioning the accumulator wrongly (row/column swap),
    which produces a plausible but incorrect trend -- the headline number.
    """
    _, ss, theta, t, design, cov, y = _setup()
    x = design.matrix
    result = KalmanEngine().score(ss, theta, y, np.ones_like(y, dtype=bool), t, design=x)
    gls = gls_solution(result.normal_equations)
    cov_inv = np.linalg.inv(cov)
    expected = np.linalg.solve(x.T @ cov_inv @ x, x.T @ cov_inv @ y[0])
    np.testing.assert_allclose(gls.beta[0], expected, rtol=1e-9, atol=1e-9)


def test_concentrated_loglik_matches_profiled_mvn():
    """The concentrated ML objective equals the GLS-profiled MVN density.

    The oracle profiles beta explicitly from an explicit covariance matrix, so
    it shares nothing with the augmented-filter route.
    """
    spec, ss, theta, t, design, cov, y = _setup()
    x = design.matrix
    obj = ConcentratedObjective(spec, ss, KalmanEngine(), Objective.ML)
    value = obj.loglik(theta, y, np.ones_like(y, dtype=bool), t, design)
    assert value[0] == pytest.approx(mvn_loglik(y[0], cov, design=x), abs=1e-9)


def test_beta_covariance_matches_explicit_inverse():
    """Reported beta covariance equals (X' Sigma^-1 X)^-1.

    Bug this catches: returning the un-inverted information matrix, which
    would understate trend uncertainty by orders of magnitude.
    """
    _, ss, theta, t, design, cov, y = _setup()
    x = design.matrix
    result = KalmanEngine().score(ss, theta, y, np.ones_like(y, dtype=bool), t, design=x)
    gls = gls_solution(result.normal_equations)
    cov_inv = np.linalg.inv(cov)
    np.testing.assert_allclose(gls.beta_cov[0], np.linalg.inv(x.T @ cov_inv @ x), rtol=1e-9)


def test_reml_penalty_matches_brute_force_logdet():
    """The R-factor REML penalty equals -0.5 log|X' Sigma^-1 X|.

    Expected value determined independently from an explicitly constructed
    Sigma and an explicit slogdet, sharing no code with the filter.
    """
    spec, ss, theta, t, design, cov, y = _setup()
    x = design.matrix
    obj = ConcentratedObjective(spec, ss, KalmanEngine(), Objective.REML)
    ml = ConcentratedObjective(spec, ss, KalmanEngine(), Objective.ML)
    mask = np.ones_like(y, dtype=bool)
    delta = obj.loglik(theta, y, mask, t, design)[0] - ml.loglik(theta, y, mask, t, design)[0]
    assert delta == pytest.approx(reml_penalty(cov, x), abs=1e-9)


def test_reml_absolute_value_matches_an_independent_oracle():
    """The REML value itself is right, not merely its difference from ML.

    The oracle is written from the published Harville form, term by term, and
    shares no code with the implementation.

    Bug this catches: inheriting ML's n*log(2pi) constant instead of REML's
    (n - rank(X))*log(2pi), and omitting the +0.5*log|X'X| basis-invariance
    term. Both are constant in theta, so they cancel in delta-IC and every
    selection test passes -- while the stored log_lik primitive is wrong in
    absolute terms and the Hector cross-validation becomes unattributable
    between a convention difference and a bug.
    """
    spec, ss, theta, t, design, cov, y = _setup()
    x = design.matrix
    obj = ConcentratedObjective(spec, ss, KalmanEngine(), Objective.REML)
    got = obj.loglik(theta, y, np.ones_like(y, dtype=bool), t, design)
    assert got[0] == pytest.approx(reml_loglik(y[0], cov, x), abs=1e-9)


@pytest.mark.parametrize("mode", ["duplicate_column", "offset_at_first_sample"])
def test_rank_deficient_design_is_a_named_outcome_not_an_exception(mode):
    """A rank-deficient X gives RANK_DEFICIENT_X before any factorization.

    Two realistic cases: a duplicated column, and an offset epoch at the first
    sample, which is collinear with the intercept (design doc section 5.2).

    Bug this catches: a singular X'Sigma^-1X reaching np.linalg.cholesky and
    raising LinAlgError. Exit criterion 6 requires the documented failure; an
    uncaught exception is neither that nor a NaN, and at 10^7 points it aborts
    a tile instead of recording an outcome.
    """
    from metamer.core.outcomes import Outcome
    from metamer.core.signal import Constant, DesignInfo, Offset

    spec, ss, theta, t, _, _, y = _setup()
    obj = ConcentratedObjective(spec, ss, KalmanEngine(), Objective.REML)
    if mode == "duplicate_column":
        x_bad = np.column_stack([np.ones(t.size), np.ones(t.size)])
    else:
        x_bad, _ = SignalSpec([Constant(), Offset(epoch=float(t[0]))]).design_matrix(t)

    bad = DesignInfo(x_bad, SignalSpec.rank(x_bad), float("-inf"))
    assert np.all(obj.check_design(bad, 1) == Outcome.RANK_DEFICIENT_X.code)

    result = obj.evaluate(theta, y, np.ones_like(y, dtype=bool), t, bad)
    assert np.all(result.outcome == Outcome.RANK_DEFICIENT_X.code)
    assert np.all(np.isnan(result.loglik))


def _gapped_setup(n: int = 60, break_at: float = 40.0):
    """Shared design containing an offset, so gaps can remove its support."""
    spec = ProcessSpec((_term("white"), _term("matern12")))
    ss = StateSpace.from_spec(spec)
    theta = np.array([[0.4, 1.2, 6.0]])
    t = np.arange(float(n))
    design = SignalSpec([Constant(), Trend(), Offset(epoch=break_at)]).design_info(t)
    return spec, ss, theta, t, design


@pytest.mark.parametrize(
    "post_break_kept, expected",
    [
        (20, Outcome.OK),
        (2, Outcome.ILL_CONDITIONED_X),
        (0, Outcome.RANK_DEFICIENT_X),
    ],
)
def test_effective_rank_is_per_series_because_the_mask_restricts_the_design(
    post_break_kept, expected
):
    """A shared, globally full-rank X still fails for one series in a batch.

    The filter accumulates X' Sigma^-1 X only over each series' unmasked
    epochs, so the design that actually enters the solve is X restricted to
    those rows. Here the offset column is fully supported globally, but series
    2's gap removes all (or nearly all) of its post-breakpoint samples. On a
    grid point with a seasonal sea-ice dropout this is ordinary.

    The three cases separate two scientific facts the map should distinguish:
    a term with no support at all (exactly singular) and a term identified by a
    handful of samples (barely identified). The middle case is what the AM-GM
    conditioning proxy exists to catch and is otherwise untested.

    Bug this catches: THE batched-granularity failure. np.linalg.cholesky raises
    for the whole (B, k, k) stack if one member is not positive definite, so a
    scalar outcome marks all B as failed. At B = 10^4 one such grid point
    destroys 9,999 good fits and the spatial failure map becomes a picture of
    the tile grid. Every small-B test passes, because there the batch is the
    series.

    NOTE for the implementer: if the (2, ILL_CONDITIONED_X) case comes back OK,
    `CONDITION_LOG_LIMIT` needs calibrating against this test rather than the
    test being loosened -- that constant has no independently correct value and
    this is the case it is for.
    """
    spec, ss, theta, t, design = _gapped_setup()
    batch = 5
    rng = np.random.default_rng(21)
    y = rng.standard_normal((batch, t.size))
    mask = np.ones_like(y, dtype=bool)
    keep_until = 40 + post_break_kept
    mask[2, keep_until:] = False

    obj = ConcentratedObjective(spec, ss, KalmanEngine(), Objective.ML)
    result = obj.evaluate(np.repeat(theta, batch, axis=0), y, mask, t, design)

    assert result.outcome[2] == expected.code
    if expected is Outcome.OK:
        assert np.isfinite(result.loglik[2])
    else:
        assert np.isnan(result.loglik[2])

    others = np.array([0, 1, 3, 4])
    assert np.all(result.outcome[others] == Outcome.OK.code)
    assert np.all(np.isfinite(result.loglik[others]))

    solo = obj.evaluate(theta, y[3:4], mask[3:4], t, design)
    assert result.loglik[3] == pytest.approx(solo.loglik[0], rel=1e-12)


def test_batch_level_rank_check_is_necessary_but_not_sufficient():
    """check_design passes a design that still fails per series.

    Bug this catches: believing the batch-level rank(X) is the whole story, and
    so never classifying per series at all. X here is globally full rank, so
    check_design returns OK for every series -- and one of them is nonetheless
    singular once its mask is applied.
    """
    spec, ss, theta, t, design = _gapped_setup()
    assert not design.is_deficient
    assert np.all(obj_codes := ConcentratedObjective(
        spec, ss, KalmanEngine(), Objective.ML
    ).check_design(design, 3) == Outcome.OK.code)
    assert obj_codes.shape == (3,)

    y = np.random.default_rng(5).standard_normal((3, t.size))
    mask = np.ones_like(y, dtype=bool)
    mask[1, 40:] = False
    obj = ConcentratedObjective(spec, ss, KalmanEngine(), Objective.ML)
    result = obj.evaluate(np.repeat(theta, 3, axis=0), y, mask, t, design)
    assert result.outcome[1] == Outcome.RANK_DEFICIENT_X.code
    assert np.all(result.outcome[[0, 2]] == Outcome.OK.code)


def test_fixed_parameter_is_pinned_and_absent_from_the_flat_vector():
    """A frozen parameter is not searched, and hydrate restores its default.

    Bug this catches: the flat vector carrying n_total entries while k counts
    n_free, which either raises on a shape mismatch or silently shifts every
    later parameter one slot left -- a wrong fit that still converges.
    """
    from dataclasses import replace

    from metamer.core.terms import TermSpec, free_param_index

    spec, ss, _, t, design, _, y = _setup()
    term = spec.terms[-1]
    pinned = TermSpec(
        kind=term.kind,
        params={n: replace(p, fixed=(n == "rho")) for n, p in term.params.items()},
        ordering_param=term.ordering_param,
    )
    frozen_spec = ProcessSpec(spec.terms[:-1] + (pinned,))
    obj = ConcentratedObjective(frozen_spec, StateSpace.from_spec(frozen_spec), KalmanEngine(), Objective.ML)

    n_free = len(free_param_index(frozen_spec))
    assert n_free == frozen_spec.n_theta()

    theta_free = np.full((1, n_free), 1.0)
    full = obj.hydrate(theta_free)
    assert full.shape[1] == sum(len(term.params) for term in frozen_spec.terms)
    assert full[0, -1] == pytest.approx(pinned.params["rho"].default)
    assert np.isfinite(obj.loglik(theta_free, y, np.ones_like(y, dtype=bool), t, design)[0])
```

- [ ] **Step 2: Run to verify failure**

Run: `pixi run test tests/test_objective.py -v`
Expected: FAIL — `metamer.core.objective` missing

- [ ] **Step 3: Implement objective.py**

```python
# src/metamer/core/objective.py
"""Concentrated ML and REML objectives built on the filter's accumulator.

The augmented filter returns A = sum_t v_t v_t' / S_t for the columns [y | X].
Partitioning A gives every quantity needed:

    A[0,0]   = y' Sigma^-1 y
    A[0,1:]  = y' Sigma^-1 X
    A[1:,1:] = X' Sigma^-1 X

so beta_hat, the residual sum of squares, the beta covariance and the REML
penalty all follow from one filter pass and a small Cholesky.

REML CONVENTION (pinned; do not change without updating the oracle).
--------------------------------------------------------------------
This module implements the Harville (1974) form, which is invariant to the
choice of error-contrast basis:

    l_R = -0.5 * [ (n - rank(X)) log(2 pi)
                   + log|Sigma|
                   + log|X' Sigma^-1 X|
                   - log|X' X|
                   + y' P y ]

Relative to the concentrated ML value l_c = -0.5 [n log(2pi) + log|Sigma| + y'Py]
that is

    l_R = l_c + 0.5 * rank(X) * log(2 pi) + 0.5 * log|X'X| - 0.5 * log|X' Sigma^-1 X|

The two correction terms beyond the penalty are CONSTANT IN THETA, so they
cancel in delta-IC and every selection decision is unaffected by omitting them.
That is exactly what makes omitting them dangerous: no in-repo differential test
can see it. They matter because (a) log_lik is stored as an auditable primitive
and would be wrong in absolute terms, and (b) the Hector / CATS / est_noise
cross-validation compares absolute REML values, where an unexplained constant is
unattributable between "different convention" and "implementation bug" -- the
precise ambiguity the exact power-law path exists to eliminate.

OPEN: verify which convention Hector uses and record it in the design doc. If it
differs, the cross-validation carries a documented offset, not a mystery.

SIGMA-SQUARED IS NOT PROFILED OUT (deliberate).
-----------------------------------------------
Standard GLS profiles the overall noise scale analytically, dropping p by one
and improving conditioning, and most of the geodesy literature does so. This
package does not, because a composite kernel has a scale per term (white sigma,
matern12 sigma, matern32 sigma) and there is no single sigma^2 to profile
without reparameterizing as an overall amplitude times a simplex of per-term
weights. That is a CROSS-TERM SHARED PARAMETER, and Phase 1 implements no
sharing mechanism (see `terms.free_param_index`, which refuses such specs).

Consequence to keep in view: this is a real comparability difference against
Hector, on top of the REML convention above. Revisit when shared parameters
land; it is a Phase 3+ change to the kernel algebra, not a flag flip.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.linalg import LinAlgError
from numpy.typing import NDArray

from metamer.core.capability import Objective
from metamer.core.engines.protocol import Engine
from metamer.core.outcomes import Outcome, outcome_array
from metamer.core.params import ParamSpec
from metamer.core.signal import DesignInfo
from metamer.core.statespace import StateSpace
from metamer.core.terms import ProcessSpec, free_param_index

CONDITION_LOG_LIMIT = 30.0
"""Per-dimension log-determinant slack allowed before X'Sigma^-1X reads as singular."""


@dataclass(frozen=True)
class GlsResult:
    """Everything one Cholesky of X' Sigma^-1 X yields, computed once.

    Attributes:
        beta: GLS estimates, shape (B, k).
        beta_cov: Their covariance (X' Sigma^-1 X)^-1, shape (B, k, k). This is
            the reported trend uncertainty -- the headline scientific output of
            the package -- so it comes from a triangular solve against the
            identity, never from `np.linalg.inv`.
        logdet: log|X' Sigma^-1 X|, shape (B,).
        rss_reduction: y' Sigma^-1 X (X' Sigma^-1 X)^-1 X' Sigma^-1 y, shape (B,).
        outcome: PER-SERIES outcome codes, shape (B,) uint8. Not a scalar: one
            rank-deficient grid point must not mark the other 9,999 as failed.
    """

    beta: NDArray[np.float64]
    beta_cov: NDArray[np.float64]
    logdet: NDArray[np.float64]
    rss_reduction: NDArray[np.float64]
    outcome: NDArray[np.uint8]


@dataclass(frozen=True)
class ObjectiveResult:
    """One objective evaluation, with everything the driver needs downstream.

    Attributes:
        loglik: Objective value per series, shape (B,). **NaN** where `outcome`
            is not OK -- not -inf. The store's status invariant is bidirectional
            (non-OK implies NaN in the value slots), and -inf is a
            finite-looking sentinel that survives some consumers' checks and
            poisons a downstream mean. -inf is the optimizer's internal barrier
            value only, applied at `optimize_series`, never here.
        gls: The GLS solve, or None when there is no design matrix.
        outcome: PER-SERIES outcome codes, shape (B,) uint8.
        n_used: Unmasked observation count per series, shape (B,).
        rank_x: Numerical rank of the design matrix. Scalar in Phase 1, where
            the design is shared across the batch; shape (B,) once per-point
            regressors land (see `signal.DesignInfo`).
    """

    loglik: NDArray[np.float64]
    gls: GlsResult | None
    outcome: NDArray[np.uint8]
    n_used: NDArray[np.int64]
    rank_x: int


def gls_solution(accum: NDArray[np.float64]) -> GlsResult:
    """Solve the profiled generalized least squares problem, once.

    One `cho_factor` yields beta, beta_cov, the log-determinant and the residual
    reduction. The earlier draft factorized the same k x k system four times
    (cholesky, solve, inv, then another solve in the caller) and discarded beta
    and beta_cov -- the two quantities the package exists to produce.

    Args:
        accum: Accumulated whitened cross-products, shape (B, 1+k, 1+k), with
            block structure [[y'Sy, y'SX], [X'Sy, X'SX]] where S = Sigma^-1.

    Returns:
        A GlsResult. On a singular or non-finite system the arrays are filled
        with NaN and `outcome` names the failure; the caller must not treat a
        non-OK outcome as a usable fit.
    """
    xtx = accum[:, 1:, 1:]
    xty = accum[:, 1:, 0]
    batch, k = xty.shape

    beta = np.full((batch, k), np.nan)
    beta_cov = np.full((batch, k, k), np.nan)
    logdet = np.full(batch, np.nan)
    rss_reduction = np.full(batch, np.nan)
    outcome = outcome_array(batch, Outcome.OK)

    finite = np.isfinite(xtx).all(axis=(1, 2)) & np.isfinite(xty).all(axis=1)
    outcome[~finite] = Outcome.NONFINITE_OBJECTIVE.code

    # slogdet is batched AND non-raising, unlike cholesky, which raises for the
    # whole stack if any single member is not positive definite. Classifying
    # validity here -- before any factorization -- is what keeps one bad grid
    # point from failing its 9,999 neighbours. It also yields the determinant
    # that is needed anyway, so this removes work rather than adding it.
    with np.errstate(invalid="ignore", divide="ignore"):
        sign, log_abs_det = np.linalg.slogdet(xtx)

    # Conditioning proxy, scale-free and diagonal-only. By AM-GM on the
    # eigenvalues, log|A| <= k log(tr(A)/k) for positive definite A; a
    # log-determinant far below that bound means near-singularity.
    diag_mean = np.diagonal(xtx, axis1=1, axis2=2).mean(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        slack = k * np.log(np.maximum(diag_mean, np.finfo(np.float64).tiny)) - log_abs_det

    singular = finite & (~(sign > 0) | ~np.isfinite(log_abs_det))
    ill = finite & ~singular & ~(slack < k * CONDITION_LOG_LIMIT)
    valid = finite & ~singular & ~ill
    outcome[singular] = Outcome.RANK_DEFICIENT_X.code
    outcome[ill] = Outcome.ILL_CONDITIONED_X.code

    if not valid.any():
        return GlsResult(beta, beta_cov, logdet, rss_reduction, outcome)

    index = np.flatnonzero(valid)
    sub = xtx[index]
    try:
        lower = np.linalg.cholesky(sub)
    except LinAlgError:
        # Backstop for the marginally positive-definite case: identify the
        # offending members individually rather than failing the whole subset.
        keep = np.ones(index.size, dtype=bool)
        factors = np.full((index.size, k, k), np.nan)
        for position in range(index.size):
            try:
                factors[position] = np.linalg.cholesky(sub[position])
            except LinAlgError:
                keep[position] = False
        outcome[index[~keep]] = Outcome.RANK_DEFICIENT_X.code
        index = index[keep]
        if index.size == 0:
            return GlsResult(beta, beta_cov, logdet, rss_reduction, outcome)
        lower = factors[keep]

    upper = np.swapaxes(lower, -1, -2)
    logdet[index] = 2.0 * np.log(np.diagonal(lower, axis1=-2, axis2=-1)).sum(axis=-1)

    # Two triangular solves reuse the one factorization. At k ~ 4 the cost of
    # not exploiting triangularity is irrelevant; avoiding a second
    # factorization -- and avoiding np.linalg.inv for beta_cov -- is not.
    sub_beta = np.linalg.solve(upper, np.linalg.solve(lower, xty[index][..., None]))[..., 0]
    eye = np.broadcast_to(np.eye(k), (index.size, k, k))
    beta[index] = sub_beta
    beta_cov[index] = np.linalg.solve(upper, np.linalg.solve(lower, eye))
    rss_reduction[index] = np.einsum("bi,bi->b", xty[index], sub_beta)

    return GlsResult(beta, beta_cov, logdet, rss_reduction, outcome)


@dataclass(frozen=True)
class ConcentratedObjective:
    """The objective the optimizer sees, in natural or unconstrained units."""

    spec: ProcessSpec
    state_space: StateSpace
    engine: Engine
    objective: Objective

    def check_design(self, design: DesignInfo, batch: int) -> NDArray[np.uint8]:
        """Classify the design matrix before it reaches the likelihood.

        THIS CHECK IS NECESSARY BUT NOT SUFFICIENT. It sees only the global
        rank of X. The design that actually enters X' Sigma^-1 X for a given
        series is X RESTRICTED TO THAT SERIES' UNMASKED ROWS, because the filter
        accumulates only over unmasked epochs -- so effective rank is per-series
        whenever masks differ, which in real gridded data is always. A shared,
        globally full-rank X still yields a singular system for any series whose
        gaps remove all support for one of its columns. `gls_solution` is what
        catches that, per series.

        Returns the per-series form for the same reason: a scalar that later has
        to be broadcast is exactly how a per-series concept gets implemented at
        batch granularity.

        Args:
            design: The built design matrix and its derived quantities.
            batch: Number of series.

        Returns:
            Per-series outcome codes, shape (B,).
        """
        if design.is_deficient or not np.isfinite(design.gram_logdet):
            return outcome_array(batch, Outcome.RANK_DEFICIENT_X)
        return outcome_array(batch, Outcome.OK)

    def loglik(
        self,
        theta: NDArray[np.float64],
        y: NDArray[np.float64],
        mask: NDArray[np.bool_],
        t: NDArray[np.float64],
        design: DesignInfo | None,
    ) -> NDArray[np.float64]:
        """Return the concentrated log-likelihood per series.

        Under ML the envelope theorem applies exactly: beta_hat is a stationary
        point, so d loglik / d theta needs no d beta_hat / d theta term. Under
        REML the penalty is NOT covered by that argument, which is why
        analytic REML gradients are strictly more work.

        Args:
            theta: Noise parameters in natural units, shape (B, p).
            y: Observations, shape (B, N).
            mask: Presence mask, shape (B, N).
            t: Shared time axis, shape (N,).
            design: The built design matrix and its theta-free quantities, or
                None. Carrying a DesignInfo rather than a loose (matrix, rank)
                pair is what lets per-point regressors widen the shapes in
                Phase 2 without a signature rewrite.

        Returns:
            Log-likelihood per series, shape (B,), NaN where the fit failed.
        """
        return self.evaluate(theta, y, mask, t, design).loglik

    def evaluate(
        self,
        theta: NDArray[np.float64],
        y: NDArray[np.float64],
        mask: NDArray[np.bool_],
        t: NDArray[np.float64],
        design: DesignInfo | None,
    ) -> ObjectiveResult:
        """Evaluate the objective and return everything one pass produces.

        The fit driver consumes `gls.beta` and `gls.beta_cov` from here rather
        than running a second filter pass to recover them.

        Returns:
            An ObjectiveResult. When `outcome` is not OK, `loglik` is -inf so an
            optimizer walks away from the region, and the caller must record the
            outcome rather than treating the value as a fit.
        """
        batch = np.shape(y)[0]
        nan = np.full(batch, np.nan)

        # Rank deficiency is classified BEFORE any factorization: a singular
        # X' Sigma^-1 X would otherwise reach cholesky, which raises for the
        # WHOLE STACK if any one member is not positive definite.
        if design is not None and design.matrix.size:
            precheck = self.check_design(design, batch)
            if np.any(precheck != Outcome.OK.code):
                return ObjectiveResult(nan, None, precheck, np.zeros(batch, np.int64), design.rank)

        matrix = None if design is None else design.matrix
        result = self.engine.score(
            self.state_space, self.hydrate(theta), y, mask, t, matrix, self.objective
        )
        if design is None or design.n_beta == 0:
            return ObjectiveResult(
                result.loglik, None, outcome_array(batch), result.n_used, 0
            )

        gls = gls_solution(result.normal_equations)
        ok = gls.outcome == Outcome.OK.code

        concentrated = np.where(ok, result.loglik + 0.5 * gls.rss_reduction, np.nan)
        if self.objective is Objective.ML:
            return ObjectiveResult(concentrated, gls, gls.outcome, result.n_used, design.rank)

        # REML, Harville form -- see the module docstring. The two terms beyond
        # the penalty are constant in theta and cancel in delta-IC, which is
        # exactly why their absence cannot be detected by a differential test.
        # gram_logdet is precomputed on DesignInfo: X does not depend on theta,
        # so recomputing it here would repeat a fixed quantity ~50 times per
        # fit, per candidate, per grid point.
        reml = np.where(
            ok,
            concentrated
            + 0.5 * design.rank * np.log(2.0 * np.pi)
            + 0.5 * design.gram_logdet
            - 0.5 * gls.logdet,
            np.nan,
        )
        return ObjectiveResult(reml, gls, gls.outcome, result.n_used, design.rank)

    def unconstrained_loglik(
        self,
        u: NDArray[np.float64],
        y: NDArray[np.float64],
        mask: NDArray[np.bool_],
        t: NDArray[np.float64],
        design: DesignInfo | None,
    ) -> NDArray[np.float64]:
        """Evaluate at unconstrained coordinates, mapping through bijectors."""
        return self.loglik(self.to_natural(u), y, mask, t, design)

    def hydrate(self, theta_free: NDArray[np.float64]) -> NDArray[np.float64]:
        """Expand a free-parameter vector to the full per-term layout.

        `StateSpace` slices `theta` over ALL of a term's parameters, including
        frozen ones, so the optimizer's free-only vector must be widened with
        the pinned defaults before it reaches any family. Without this a spec
        with a fixed parameter either raises on a shape mismatch or -- worse --
        silently shifts every subsequent parameter one slot to the left.

        Args:
            theta_free: Natural-units free parameters, shape (B, p_free).

        Returns:
            Natural-units full parameter matrix, shape (B, p_total).
        """
        arr = np.asarray(theta_free, dtype=np.float64)
        free = {pair: column for pair, column in zip(free_param_index(self.spec), arr.T, strict=True)}
        columns: list[NDArray[np.float64]] = []
        for label, term in zip(self.spec.labels(), self.spec.terms, strict=True):
            for name, spec in term.params.items():
                key = (label, name)
                if key in free:
                    columns.append(free[key])
                else:
                    columns.append(np.full(arr.shape[0], spec.default, dtype=np.float64))
        return np.column_stack(columns)

    def _free_specs(self) -> tuple[ParamSpec, ...]:
        """Resolve the flat vector's ParamSpecs via the single source of truth.

        All three mappings below drive off `free_param_index` rather than each
        re-deriving the layout. Five separate copies of that nested loop existed
        in an earlier draft, two of them reading their order from different
        sources; divergence produces converged-looking fits at values
        interpreted differently in two places, with no exception raised.
        """
        by_label = dict(zip(self.spec.labels(), self.spec.terms, strict=True))
        return tuple(
            by_label[label].params[name] for label, name in free_param_index(self.spec)
        )

    def _map(self, values: NDArray[np.float64], method: str) -> NDArray[np.float64]:
        arr = np.asarray(values, dtype=np.float64)
        specs = self._free_specs()
        if arr.shape[1] != len(specs):
            raise ValueError(
                f"parameter vector has {arr.shape[1]} columns but this spec has "
                f"{len(specs)} free parameters"
            )
        out = np.empty_like(arr)
        for index, spec in enumerate(specs):
            out[:, index] = getattr(spec.transform, method)(arr[:, index])
        return out

    def to_natural(self, u: NDArray[np.float64]) -> NDArray[np.float64]:
        """Map an unconstrained parameter matrix (B, p_free) to natural units."""
        return self._map(u, "forward")

    def to_unconstrained(self, theta: NDArray[np.float64]) -> NDArray[np.float64]:
        """Map a natural-units matrix (B, p_free) to unconstrained space."""
        return self._map(theta, "inverse")

    def dforward(self, u: NDArray[np.float64]) -> NDArray[np.float64]:
        """Return d(natural)/d(unconstrained) for the delta method."""
        return self._map(u, "dforward")
```

- [ ] **Step 4: Run tests and commit**

Note the REML test in this file passes only after Task 9's counting lands; run it now and
confirm the ML tests pass and the REML one exercises the penalty already implemented above.

Run: `pixi run test tests/test_objective.py -v` → all PASS

```bash
git add src/metamer/core/objective.py tests/test_objective.py
git commit -m "feat: add GLS profiling with ML and REML concentrated objectives"
```

---

## Task 9: Parameter counting per objective and both effective sample sizes

**Goal:** `k` and `n` defined **per objective as definitions, not adjustments**, and the two distinct effective sample sizes named so they can never be interchanged.

**Files:**
- Create: `src/metamer/core/counting.py`
- Create: `tests/test_counting.py`

**Acceptance Criteria:**
- [ ] ML: `k == k_θ + k_β` (including profiled-out `β`), `n == n_obs`
- [ ] REML: `k == k_θ`, `n == n_obs − rank(X)`
- [ ] Frozen parameters are excluded from `k_θ`
- [ ] Rank-deficient `X` reduces REML's `n` by `rank(X)`, not by `ncol(X)`
- [ ] `n_eff_bic` is the participation ratio `n² / ‖R‖²_F`, equals `n` at zero correlation and 1 at perfect correlation
- [ ] `n_eff_trend` is a separate function and is never used as the BIC penalty's `n`

**Verify:** `pixi run test tests/test_counting.py -v`

**Steps:**

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_counting.py
import numpy as np
import pytest

from metamer.core.capability import Objective
from metamer.core.counting import n_eff_bic, n_eff_trend, penalty_terms
from metamer.core.terms import ProcessSpec
from tests.test_statespace import _term


def test_ml_counts_profiled_out_beta():
    """Under ML, k includes the GLS-profiled signal parameters.

    Expected value determined independently by hand: white(1) + matern12(2)
    gives k_theta = 3; a constant+trend signal gives k_beta = 2; so k = 5.

    Bug this catches: the single most common silent bug in concentrated-
    likelihood implementations. Profiled parameters were still estimated from
    the data and still count toward k; omitting them corrupts every selection
    decision with no visible symptom.
    """
    spec = ProcessSpec((_term("white"), _term("matern12")))
    k, n = penalty_terms(spec, Objective.ML, n_obs=630, rank_x=2, k_beta=2)
    assert k == 5
    assert n == 630


def test_reml_excludes_beta_entirely_and_reduces_n_by_rank():
    """Under REML, beta is not a parameter of the model at all.

    Expected value determined independently: REML is the likelihood of a set
    of error contrasts, a different random quantity from y. So k = k_theta = 3
    and n = 630 - rank(X) = 628. This is a definition on a different model
    class, not ML's bookkeeping with an adjustment.
    """
    spec = ProcessSpec((_term("white"), _term("matern12")))
    k, n = penalty_terms(spec, Objective.REML, n_obs=630, rank_x=2, k_beta=2)
    assert k == 3
    assert n == 628


def test_rank_deficiency_uses_rank_not_ncol():
    """REML's n uses rank(X), which is smaller than ncol(X) when deficient.

    Bug this catches: using ncol(X), which over-subtracts and makes the REML
    penalty wrong exactly at the grid points where an offset epoch or an
    unresolvable harmonic has collapsed a column.
    """
    spec = ProcessSpec((_term("matern12"),))
    _, n = penalty_terms(spec, Objective.REML, n_obs=100, rank_x=3, k_beta=5)
    assert n == 97


def test_frozen_parameters_are_not_counted():
    """A fixed parameter contributes nothing to k_theta.

    Bug this catches: counting every declared parameter, which inflates the
    penalty for any candidate with a pinned timescale.
    """
    from dataclasses import replace

    term = _term("matern12")
    frozen = {name: replace(p, fixed=(name == "rho")) for name, p in term.params.items()}
    spec = ProcessSpec((type(term)(kind="matern12", params=frozen, ordering_param="rho"),))
    k, _ = penalty_terms(spec, Objective.ML, n_obs=50, rank_x=0, k_beta=0)
    assert k == 1


def test_n_eff_bic_endpoints():
    """Participation ratio equals n when uncorrelated and 1 when perfectly so.

    Expected value determined independently: ||R||_F^2 = n for R = I, giving
    n^2/n = n; and ||R||_F^2 = n^2 for the all-ones R, giving 1.
    """
    n = 50
    assert n_eff_bic(np.zeros(n - 1), n) == pytest.approx(float(n))
    assert n_eff_bic(np.ones(n - 1), n) == pytest.approx(1.0)


def test_n_eff_bic_is_monotone_in_correlation_strength():
    """Stronger correlation gives a smaller effective sample size.

    Bug this catches: an estimator that can exceed n or go negative -- the
    classic n/(1 + 2 sum rho_k) form does both under negative correlation,
    which is why it is not used here.
    """
    n = 200
    lags = np.arange(1, n)
    weak = n_eff_bic(0.3**lags, n)
    strong = n_eff_bic(0.9**lags, n)
    assert 1.0 <= strong < weak <= n


def test_n_eff_trend_is_a_separate_quantity():
    """n_eff_trend is term-specific and distinct from n_eff_bic.

    Bug this catches: interchanging them. n_eff_trend is the effective sample
    size for estimating the trend, not a global property of the series, so
    using it as the BIC penalty's n is a category error.
    """
    n = 100
    var_gls = 4.0
    var_white = 1.0
    assert n_eff_trend(var_gls, var_white, n) == pytest.approx(25.0)
```

- [ ] **Step 2: Run to verify failure, then implement**

Run: `pixi run test tests/test_counting.py -v` → FAIL (module missing)

```python
# src/metamer/core/counting.py
"""Parameter counting and effective sample sizes.

ML and REML are different model classes, not the same model with different
bookkeeping: under REML the objective is the likelihood of a set of error
contrasts, and beta is not a parameter of that model at all. The counts are
therefore stated as two definitions.

    ML:   k = k_theta + k_beta (including profiled-out beta), n = n_obs
    REML: k = k_theta,                                        n = n_obs - rank(X)
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from metamer.core.capability import Objective
from metamer.core.terms import ProcessSpec


def penalty_terms(
    spec: ProcessSpec, objective: Objective, n_obs: int, rank_x: int, k_beta: int
) -> tuple[int, int]:
    """Return (k, n) for an information criterion, per objective.

    Args:
        spec: The noise specification, supplying k_theta.
        objective: ML or REML.
        n_obs: Number of unmasked observations.
        rank_x: Numerical rank of the design matrix.
        k_beta: Number of design columns (only used under ML).

    Returns:
        A tuple of (k, n) for the criterion's penalty.
    """
    k_theta = spec.n_theta()
    if objective is Objective.REML:
        return k_theta, int(n_obs - rank_x)
    return k_theta + int(k_beta), int(n_obs)


def n_eff_bic(autocorrelation: NDArray[np.float64], n: int) -> float:
    """Effective sample size for the BIC penalty, as a participation ratio.

    Uses n_eff = n^2 / ||R||_F^2 where R is the model correlation matrix. For
    a Toeplitz R this is

        ||R||_F^2 = n + 2 * sum_{k=1}^{n-1} (n - k) * rho_k^2

    so it never forms R explicitly. Chosen because it is always in [1, n],
    always well-defined, monotone in correlation strength, and degrades
    gracefully for near-degenerate fits. The classic n / (1 + 2 sum rho_k)
    form is the effective size for estimating *a mean*, can exceed n or go
    negative under negative correlation, and needs windowing choices.

    Args:
        autocorrelation: rho_k for k = 1 .. n-1.
        n: Series length.

    Returns:
        Effective sample size in [1, n].
    """
    rho = np.asarray(autocorrelation, dtype=np.float64)
    lags = np.arange(1, rho.size + 1, dtype=np.float64)
    frob_sq = float(n) + 2.0 * float(np.sum((n - lags) * rho**2))
    return float(n * n / frob_sq)


def n_eff_trend(var_trend_gls: float, var_trend_white: float, n: int) -> float:
    """Effective sample size for estimating the trend.

    This is term-specific and must never be substituted for `n_eff_bic`. It is
    used by the ML-versus-REML rule of thumb and by coverage diagnostics.

    Args:
        var_trend_gls: Variance of the GLS trend estimate under the fitted
            noise model.
        var_trend_white: Variance the trend estimate would have under white
            noise of the same marginal variance.
        n: Series length.

    Returns:
        n * var_white / var_gls, clipped to [1, n].
    """
    ratio = float(n) * float(var_trend_white) / float(var_trend_gls)
    return float(np.clip(ratio, 1.0, float(n)))
```

- [ ] **Step 3: Run tests and commit**

Run: `pixi run test tests/test_counting.py -v` → all PASS

```bash
git add src/metamer/core/counting.py tests/test_counting.py
git commit -m "feat: add per-objective parameter counting and effective sample sizes"
```

---

## Task 10: Criteria and the comparability guards

**Goal:** AIC (plus AICc, BIC, HQIC and the effective-sample-size BIC variant, which are arithmetic on the same primitives), and a selection layer that **refuses** to rank across engines or across objectives.

**Files:**
- Create: `src/metamer/core/criteria.py`
- Create: `tests/test_criteria.py`

**Acceptance Criteria:**
- [x] `aic == 2k − 2ℓ`; `bic == k ln n − 2ℓ`; `aicc == aic + 2k(k+1)/(n−k−1)`; `hqic == 2k ln ln n − 2ℓ`
- [x] `bic_neff` substitutes `n_eff_bic` for `n` and is strictly smaller than `bic` when `n_eff < n`
- [x] Ranking two scores with different `engine` tags raises `ComparabilityError`
- [x] Ranking two scores with different `objective` tags raises `ComparabilityError`
- [x] `ΔIC` is relative to the best surviving candidate; failed candidates get `NaN` and are excluded from weight normalization
- [x] `n_valid` counts surviving candidates and is returned alongside the weights

**Verify:** `pixi run test tests/test_criteria.py -v`

> **Corrections applied at implementation time (commit `5003e9b`). The code
> fences below are the pre-audit draft and are kept only as the record of what
> was written; `src/metamer/core/criteria.py` is authoritative.**
>
> 1. **The API is batched `(B, M)`, not one `CandidateScore` per candidate per
>    point.** `CandidateScores` holds `loglik`, `k`, `n`, `n_eff` and `outcome`
>    as `(B, M)` arrays with per-candidate `labels` / `engines` / `objectives`
>    tuples; `rank_candidates` returns `delta_ic` and `weights` as `(B, M)` and
>    `ic_best`, `best_index`, `n_valid` as `(B,)`. Everything the module
>    consumes is already per series — `penalty_terms` returns `(k, n)` as `(B,)`
>    arrays, `n_eff_bic` returns `(B,)`, `ObjectiveResult.loglik` and
>    `.outcome` are `(B,)` — so the scalar form both forced a per-point Python
>    loop over 10⁷ grid points and made the caller unpack those arrays by hand,
>    which is exactly where the `rank_x` / `design_rank` substitution gets
>    reintroduced. The shapes now match the `/selection/` layout of design doc
>    §12.2.
> 2. **`ok: bool` is replaced by the `(B, M)` `outcome` array.** Survival is
>    `outcome == OK`. Gating on `isfinite(loglik)` would resurrect an
>    iteration-capped or diagnostic-limited candidate, which carries the last
>    finite value it evaluated; gating on `Outcome.is_failure` would *admit*
>    `INSUFFICIENT_DATA` and `NOT_ATTEMPTED`, so a wholly-masked tile would come
>    back with a confident-looking selection. An `OK` outcome beside a NaN
>    primitive now raises rather than being silently dropped.
> 3. **The log-based penalties have domains; outside them the value is NaN.**
>    Measured: at `n = 1` BIC's penalty is exactly `0.0` and HQIC's is `−inf`;
>    at `n = 2` HQIC's is `−2.93`, i.e. it rewards parameters. `n = 1` is
>    reachable — `penalty_terms` guarantees only `n_obs − design_rank ≥ 1`. So
>    `BIC` needs `n > 1`, `HQIC` needs `n > e`, `BIC_NEFF` needs `n_eff > 1`.
> 4. **The draft's `max(n_eff, 2.0)` floor is dropped.** It silently answers a
>    different question, and at `n = 2`, `n_eff = 1.5` it makes `bic_neff`
>    exactly *equal* to `bic` — contradicting this task's own second acceptance
>    criterion, which the draft's own `loose < strict` test could not see.
> 5. **`n_valid` counts fits, not finite criterion values.** The store holds one
>    `n_valid[y,x]` shared by every criterion (§12.2 gives it no `c` axis), so
>    it cannot depend on which criterion was asked for. An AICc of `+inf` at
>    `n ≤ k + 1` is ranked last with weight `0` and `ΔIC = +inf`, and still
>    counts as valid.
> 6. **`Ranking` also carries `criterion` and `ic_best`.** §12.6 stores
>    `ic_best[y,x,c]` in float64 beside float32 `ΔIC`; without it the store
>    cannot be written from a `Ranking`.
>
> **Task 14's fence is stale in the same way** and must be corrected before it
> is implemented: it calls `penalty_terms(spec, objective, int(mask[b].sum()),
> design.rank, k_beta)`, a scalar positional signature that Task 9 replaced with
> keyword-only per-series arrays (`n_obs=`, `design_rank=`, `outcome=`,
> `k_beta=`); it builds one `CandidateScore` per `(series, candidate)` in a
> double Python loop; and it passes `n_eff=float(n)`, so `n_eff_bic` is never
> called.

**Steps:**

- [x] **Step 1: Write the failing tests**

```python
# tests/test_criteria.py
import numpy as np
import pytest

from metamer.core.capability import EngineId, Objective
from metamer.core.criteria import (
    Criterion,
    ComparabilityError,
    CandidateScore,
    ic_value,
    rank_candidates,
)


def _score(loglik, k, n, engine=EngineId.KALMAN, objective=Objective.ML, ok=True):
    return CandidateScore(
        label="c", loglik=loglik, k=k, n=n, n_eff=float(n), engine=engine,
        objective=objective, ok=ok,
    )


def test_criterion_formulae_match_textbook_definitions():
    """AIC, BIC, AICc and HQIC match their standard definitions.

    Expected values determined independently by hand from the published
    formulae: AIC = 2k - 2l; BIC = k ln n - 2l; AICc = AIC + 2k(k+1)/(n-k-1);
    HQIC = 2k ln ln n - 2l.
    """
    loglik, k, n = -100.0, 4.0, 50.0
    assert ic_value(Criterion.AIC, loglik, k, n, n) == pytest.approx(2 * 4 + 200)
    assert ic_value(Criterion.BIC, loglik, k, n, n) == pytest.approx(4 * np.log(50) + 200)
    assert ic_value(Criterion.AICC, loglik, k, n, n) == pytest.approx(
        2 * 4 + 200 + 2 * 4 * 5 / (50 - 4 - 1)
    )
    assert ic_value(Criterion.HQIC, loglik, k, n, n) == pytest.approx(
        2 * 4 * np.log(np.log(50)) + 200
    )


def test_bic_neff_is_a_smaller_penalty_when_correlation_is_strong():
    """Substituting n_eff for n loosens BIC's penalty.

    Expected value determined independently: BIC's penalty is k ln n, and
    ln(n_eff) < ln(n) whenever n_eff < n, so the criterion value is smaller.
    """
    strict = ic_value(Criterion.BIC, -100.0, 4.0, 500.0, 500.0)
    loose = ic_value(Criterion.BIC_NEFF, -100.0, 4.0, 500.0, 12.0)
    assert loose < strict


def test_cross_engine_ranking_is_a_hard_error():
    """A Whittle score and a Kalman score are never ranked together.

    Bug this catches: the silent-failure mode that produces plausible-looking
    but wrong maps. A Whittle score is not an exact likelihood and lives on a
    different scale.
    """
    scores = [_score(-10.0, 2, 100), _score(-9.0, 2, 100, engine=EngineId.WHITTLE)]
    with pytest.raises(ComparabilityError, match="engine"):
        rank_candidates(scores, Criterion.AIC)


def test_cross_objective_ranking_is_a_hard_error():
    """An ML score and a REML score are never ranked together.

    Bug this catches: the same failure class one level up. The two live on
    different measures -- REML is the likelihood of error contrasts -- and the
    numbers look commensurable while not being so.
    """
    scores = [_score(-10.0, 2, 100), _score(-9.0, 2, 100, objective=Objective.REML)]
    with pytest.raises(ComparabilityError, match="objective"):
        rank_candidates(scores, Criterion.AIC)


def test_failed_candidates_do_not_poison_the_weight_vector():
    """A failed candidate gets NaN delta-IC and is excluded from weights.

    Bug this catches: letting a NaN through exp(-dIC/2), which makes every
    weight at that grid point NaN and silently destroys the whole model-average.
    """
    scores = [_score(-10.0, 2, 100), _score(np.nan, 2, 100, ok=False), _score(-12.0, 2, 100)]
    result = rank_candidates(scores, Criterion.AIC)
    assert np.isnan(result.delta_ic[1])
    assert result.weights[1] == 0.0
    assert result.weights[[0, 2]].sum() == pytest.approx(1.0)
    assert result.n_valid == 2


def test_delta_ic_is_zero_for_the_best_candidate():
    """The winner has delta-IC exactly zero.

    Bug this catches: normalizing against the mean or the first candidate,
    which makes delta-IC maps uninterpretable.
    """
    scores = [_score(-20.0, 2, 100), _score(-10.0, 2, 100)]
    result = rank_candidates(scores, Criterion.AIC)
    assert result.delta_ic[1] == pytest.approx(0.0)
    assert result.best_index == 1
```

- [x] **Step 2: Run to verify failure, then implement**

Run: `pixi run test tests/test_criteria.py -v` → FAIL (module missing)

```python
# src/metamer/core/criteria.py
"""Information criteria and the comparability guards.

Every score carries the engine that produced it and the objective it is on.
Ranking across either is a hard error, not a warning: both are silent-failure
modes that produce plausible-looking but wrong maps.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import numpy as np
from numpy.typing import NDArray

from metamer.core.capability import EngineId, Objective


class Criterion(StrEnum):
    """Selectable information criteria."""

    AIC = "aic"
    AICC = "aicc"
    BIC = "bic"
    BIC_NEFF = "bic_neff"
    HQIC = "hqic"


class ComparabilityError(ValueError):
    """Scores from different engines or objectives cannot be ranked."""


@dataclass(frozen=True)
class CandidateScore:
    """One candidate's score at one grid point, with its provenance tags."""

    label: str
    loglik: float
    k: float
    n: float
    n_eff: float
    engine: EngineId
    objective: Objective
    ok: bool = True


@dataclass(frozen=True)
class Ranking:
    """The result of ranking a candidate set at one point."""

    delta_ic: NDArray[np.float64]
    weights: NDArray[np.float64]
    best_index: int
    n_valid: int


def ic_value(criterion: Criterion, loglik: float, k: float, n: float, n_eff: float) -> float:
    """Evaluate an information criterion from the stored primitives.

    Args:
        criterion: Which criterion to evaluate.
        loglik: Maximized log-likelihood.
        k: Parameter count, per objective (see `counting.penalty_terms`).
        n: Sample size, per objective.
        n_eff: Effective sample size, used only by BIC_NEFF.

    Returns:
        The criterion value; lower is better.
    """
    fit = -2.0 * loglik
    match criterion:
        case Criterion.AIC:
            return 2.0 * k + fit
        case Criterion.AICC:
            denom = n - k - 1.0
            correction = np.inf if denom <= 0 else 2.0 * k * (k + 1.0) / denom
            return 2.0 * k + fit + correction
        case Criterion.BIC:
            return k * np.log(n) + fit
        case Criterion.BIC_NEFF:
            return k * np.log(max(n_eff, 2.0)) + fit
        case Criterion.HQIC:
            return 2.0 * k * np.log(np.log(n)) + fit
    raise ValueError(f"unknown criterion {criterion!r}")


def rank_candidates(scores: list[CandidateScore], criterion: Criterion) -> Ranking:
    """Rank a candidate set, refusing incomparable scores.

    Args:
        scores: One score per candidate, all from the same engine and
            objective.
        criterion: Criterion to rank by.

    Returns:
        A Ranking with delta-IC, normalized weights, the winning index, and the
        number of surviving candidates.

    Raises:
        ComparabilityError: If the scores mix engines or objectives.
    """
    engines = {s.engine for s in scores}
    if len(engines) > 1:
        raise ComparabilityError(
            f"refusing to rank across engine tags {sorted(e.value for e in engines)}: "
            "these scores are not on a common scale"
        )
    objectives = {s.objective for s in scores}
    if len(objectives) > 1:
        raise ComparabilityError(
            f"refusing to rank across objective tags {sorted(o.value for o in objectives)}: "
            "ML and REML likelihoods live on different measures"
        )

    values = np.array(
        [
            ic_value(criterion, s.loglik, s.k, s.n, s.n_eff) if s.ok else np.nan
            for s in scores
        ],
        dtype=np.float64,
    )
    valid = np.isfinite(values)
    if not valid.any():
        nan = np.full(values.shape, np.nan)
        return Ranking(nan, np.zeros_like(values), -1, 0)

    best = int(np.nanargmin(values))
    delta = values - values[best]
    weights = np.zeros_like(values)
    weights[valid] = np.exp(-0.5 * delta[valid])
    weights[valid] /= weights[valid].sum()
    return Ranking(delta, weights, best, int(valid.sum()))
```

- [x] **Step 3: Run tests and commit**

Run: `pixi run test tests/test_criteria.py -v` → all PASS

```bash
git add src/metamer/core/criteria.py tests/test_criteria.py
git commit -m "feat: add information criteria with engine and objective guards"
```

---

## Task 11: Finite-difference gradients, the step rule, and the complex-step verdict

**Goal:** Central-difference gradients in unconstrained coordinates with a step rule that accounts for `|ℓ|` scaling with `N`, plus a recorded verdict on whether complex-step differentiation is viable through this filter.

**Files:**
- Create: `src/metamer/core/gradients.py`
- Create: `tests/test_gradients.py`, `docs/superpowers/notes/complex-step-verdict.md`

**Acceptance Criteria:**
- [x] `fd_gradient` matches an analytically differentiable reference to 1e-7 relative
- [x] The step rule holds at `N ∈ {100, 630, 5000}` — gradient error does not degrade as `|ℓ|` grows
- [x] Steps are taken in unconstrained coordinates, so one relative step serves every family
- [x] Complex-step is run against central FD on `matern32`; the agreement level is **recorded with numbers** in the verdict note
- [x] If complex-step agrees to ~1e-12 it becomes the oracle; if only ~1e-7, Richardson-extrapolated central FD is adopted instead and the note says so

**Verify:** `pixi run test tests/test_gradients.py -v` and the verdict note exists with numbers

> **Corrections applied at implementation time (commit `d4396a6`). The code fences
> below are the pre-audit draft, kept as the record of what was written;
> `src/metamer/core/gradients.py` and
> [`docs/superpowers/notes/complex-step-verdict.md`](../notes/complex-step-verdict.md)
> are authoritative.**
>
> 1. **`fd_step` keeps the curvature denominator.** The fence proposed
>    `(ε·|ℓ|)^(1/3)`; design doc §8.2 specifies `(ε·|ℓ|/|ℓ''|)^(1/3)`. Both `|ℓ|`
>    and its derivatives scale with N, so the ratio is O(1) and the optimal step
>    barely moves with N — measured optimum `h ∈ [1e-6, 1e-5]` across `|ℓ|` from
>    3.2e3 to 2.2e5. Relative gradient error against the oracle: **1.19e-08 /
>    4.51e-08 / 1.98e-07** for the fence's rule at N = 100 / 630 / 5000, against
>    **4.28e-11 / 1.00e-10 / 1.76e-10** for the corrected one. At N = 5000 the
>    fence's own "1e-7 relative" acceptance criterion is missed by its own rule.
> 2. **`richardson_gradient` starts at `h0 = 1e-2`, not at `fd_step(scale)`.**
>    Richardson extrapolates the *truncation* series, so starting at the FD
>    optimum extrapolates rounding noise: measured 5.08e-11 from `h0 = 6.06e-6`
>    against **5.80e-14** from `h0 = 1e-2` — and the former is *worse* than the
>    plain central difference it was meant to improve (4.43e-11).
> 3. **The complex-step verdict is negative, and `assert rel < 1e-4` cannot
>    pass.** Measured `rel = 1.000e+00`; the gradient comes back exactly
>    `[0, 0]`. The cause is **not** a non-analytic operation — it is
>    `ConcentratedObjective._map`'s `np.asarray(values, dtype=np.float64)`,
>    which discards the perturbation at `to_natural` before the filter is
>    reached. The test now asserts exact zero, so a later dtype-following change
>    breaks it and forces the note to be rewritten.
> 4. **The fence's `from metamer.core.signal import DesignInfo` sits at column
>    0 inside a test body** and would not have parsed. The name was unused.
> 5. **The test function is `sin(3u₀) + u₁³ + 0.5·u₀u₁`, not the fence's
>    quadratic.** A quadratic has zero third derivative, so central differences
>    are exact at any step and no step rule is distinguishable from any other —
>    the fence's step-rule test could not fail for the reason its docstring gave.
> 6. **The three-N test passes `scale` explicitly**, as a real caller does. With
>    `scale` left at its default the numerator is 1, the denominator is
>    irrelevant, and deleting it changes no number — verified by mutation: the
>    test passed against the defect until `scale` was threaded through.
>
> **Cost note:** `tests/test_gradients.py` runs the real filter at N = 5000, so
> the suite is now ~21 s rather than ~2 s. That is one Romberg tableau plus one
> central difference at each of three N; it is not accidental repetition.

**Steps:**

- [x] **Step 1: Write the failing tests**

```python
# tests/test_gradients.py
import numpy as np
import pytest

from metamer.core.gradients import complex_step_gradient, fd_gradient, fd_step


def _quadratic(u):
    """A function with a known analytic gradient, scaled to mimic |loglik| ~ N."""
    return -0.5 * np.sum((u - np.array([0.3, -1.2])) ** 2) * 1000.0


def _quadratic_grad(u):
    return -(u - np.array([0.3, -1.2])) * 1000.0


def test_fd_gradient_matches_the_analytic_gradient():
    """Central differences recover a known gradient.

    Expected value determined independently by differentiating the quadratic
    on paper.
    """
    u = np.array([1.0, 2.0])
    np.testing.assert_allclose(
        fd_gradient(_quadratic, u, scale=1000.0), _quadratic_grad(u), rtol=1e-7
    )


@pytest.mark.parametrize("n", [100, 630, 5000])
def test_step_rule_holds_as_the_objective_magnitude_grows(n):
    """Gradient accuracy does not degrade as |loglik| scales with N.

    Bug this catches: a hardcoded cube-root-of-eps step. FD cancellation error
    is eps*|l|/h, not eps/h, so a step tuned at N=100 quietly loses digits at
    production N. This is the class of thing that works at Phase 1 scale and
    fails silently later.
    """

    def scaled(u):
        return _quadratic(u) * (n / 1000.0)

    u = np.array([0.7, -0.4])
    expected = _quadratic_grad(u) * (n / 1000.0)
    got = fd_gradient(scaled, u, scale=float(n))
    np.testing.assert_allclose(got, expected, rtol=1e-6)


def test_fd_step_scales_with_objective_magnitude():
    """The step grows with |loglik| as the cube-root rule requires.

    Expected value determined independently: h ~ (eps*|l|)^(1/3), so a 1000x
    larger objective gives a 10x larger step.
    """
    assert fd_step(1e6) / fd_step(1e3) == pytest.approx(10.0, rel=1e-9)


def test_complex_step_matches_fd_on_an_analytic_function():
    """Complex-step reproduces the analytic gradient to machine precision.

    This establishes the mechanism works; the *verdict* test below establishes
    whether the actual filter is complex-analytic, which is a different and
    harder question.
    """
    u = np.array([1.0, 2.0])
    np.testing.assert_allclose(complex_step_gradient(_quadratic, u), _quadratic_grad(u), rtol=1e-12)


def test_complex_step_viability_on_the_real_filter_is_recorded():
    """Run complex-step against central FD on matern32 and record the level.

    Complex-step silently returns a WRONG derivative -- it does not raise --
    when any non-analytic operation is in the path: abs(), max()/min(), a
    comparison-based branch, numpy's conjugating norm, sorting, or a clipping
    guard. Agreement to ~1e-12 means viable; ~1e-7 means something
    non-analytic is present and the fallback oracle must be adopted.
    """
    from metamer.core.capability import Objective
    from metamer.core.engines.kalman import KalmanEngine
    from metamer.core.objective import ConcentratedObjective
from metamer.core.signal import DesignInfo
    from metamer.core.statespace import StateSpace
    from metamer.core.terms import ProcessSpec
    from tests.test_statespace import _term

    spec = ProcessSpec((_term("matern32"),))
    ss = StateSpace.from_spec(spec)
    obj = ConcentratedObjective(spec, ss, KalmanEngine(), Objective.ML)
    t = np.arange(64.0)
    rng = np.random.default_rng(7)
    y = rng.standard_normal((1, 64))
    mask = np.ones_like(y, dtype=bool)

    def f(u):
        return float(obj.unconstrained_loglik(u[None, :], y, mask, t, None)[0])

    u0 = np.array([0.0, np.log(5.0)])
    g_fd = fd_gradient(f, u0, scale=64.0)
    g_cs = complex_step_gradient(f, u0)
    rel = float(np.max(np.abs(g_cs - g_fd) / np.maximum(np.abs(g_fd), 1e-12)))
    # Record the number; the assertion only guards against outright breakage.
    print(f"COMPLEX_STEP_AGREEMENT rel={rel:.3e}")
    assert rel < 1e-4
```

- [x] **Step 2: Implement gradients.py**

```python
# src/metamer/core/gradients.py
"""Gradient strategies.

Finite differences are the Phase 1 default because they cost zero per-family
work. Analytic forward-mode is the target (1+p passes against FD's 2p, and
exact). Complex-step's role is VERIFICATION, not production: it is an exact
gradient requiring no derivation, so it is the oracle that catches an incorrect
hand-derived dQ/dtheta. FD alone cannot play that role -- agreeing to 1e-8 with
a wrong analytic gradient is entirely possible.

Steps are taken in unconstrained coordinates, where log and logit transforms
have already made every coordinate O(1)-scaled. That licenses a single relative
step across families, and is a second dividend from the ParamSpec contract.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
from numpy.typing import NDArray

_EPS = float(np.finfo(np.float64).eps)


def fd_step(objective_scale: float) -> float:
    """Return the central-difference step for an objective of a given size.

    Truncation error is O(h^2 |l'''|) and cancellation error is O(eps |l| / h),
    so the optimum is h ~ (eps |l|)^(1/3). The |l| factor matters: the
    log-likelihood scales with N, so a step tuned at small N loses digits at
    production N.

    Args:
        objective_scale: Rough magnitude of the objective, e.g. |loglik|.

    Returns:
        A step size in unconstrained coordinates.
    """
    return float((_EPS * max(abs(objective_scale), 1.0)) ** (1.0 / 3.0))


def fd_gradient(
    fn: Callable[[NDArray[np.float64]], float],
    u: NDArray[np.float64],
    scale: float,
    step: float | None = None,
) -> NDArray[np.float64]:
    """Central-difference gradient in unconstrained coordinates.

    Args:
        fn: Scalar objective of an unconstrained parameter vector.
        u: Point at which to differentiate, shape (p,).
        scale: Rough magnitude of `fn`, used to size the step.
        step: Explicit step, overriding the rule.

    Returns:
        Gradient, shape (p,).
    """
    u = np.asarray(u, dtype=np.float64)
    h = fd_step(scale) if step is None else float(step)
    out = np.empty_like(u)
    for i in range(u.size):
        e = np.zeros_like(u)
        e[i] = h
        out[i] = (fn(u + e) - fn(u - e)) / (2.0 * h)
    return out


def richardson_gradient(
    fn: Callable[[NDArray[np.float64]], float], u: NDArray[np.float64], scale: float
) -> NDArray[np.float64]:
    """Richardson-extrapolated central difference.

    The fallback oracle if complex-step proves non-viable through the filter.
    Reaches roughly 1e-10 to 1e-11, which is weaker than complex-step but
    sufficient for its actual job: a wrong dQ/dtheta produces O(1) relative
    error, not O(1e-7).
    """
    h = fd_step(scale)
    coarse = fd_gradient(fn, u, scale, step=h)
    fine = fd_gradient(fn, u, scale, step=h / 2.0)
    return (4.0 * fine - coarse) / 3.0


def complex_step_gradient(
    fn: Callable[[NDArray[np.complex128]], complex],
    u: NDArray[np.float64],
    step: float = 1e-20,
) -> NDArray[np.float64]:
    """Complex-step derivative: exact, with no subtractive cancellation.

    Requires the whole evaluation path to be complex-analytic. abs(), max(),
    comparison-based branches, numpy's conjugating norms, sorting and clipping
    guards all silently return a WRONG derivative rather than raising, which is
    why viability must be measured rather than assumed.

    Args:
        fn: Objective, which must accept a complex argument.
        u: Point at which to differentiate, shape (p,).
        step: Imaginary step; 1e-20 is safe because there is no cancellation.

    Returns:
        Gradient, shape (p,).
    """
    u = np.asarray(u, dtype=np.float64)
    out = np.empty_like(u)
    for i in range(u.size):
        e = np.zeros(u.size, dtype=np.complex128)
        e[i] = 1j * step
        out[i] = float(np.imag(fn(u.astype(np.complex128) + e)) / step)
    return out
```

- [x] **Step 3: Run the tests, capture the complex-step number, write the verdict note**

Run: `pixi run test tests/test_gradients.py -v -s | rg COMPLEX_STEP_AGREEMENT`

Write `docs/superpowers/notes/complex-step-verdict.md` containing the measured relative
agreement, the decision that follows (`rel < 1e-10` → complex-step is the oracle;
otherwise Richardson-extrapolated central FD is), and the specific non-analytic operation
found in the path if the verdict is negative.

- [x] **Step 4: Commit**

```bash
git add src/metamer/core/gradients.py tests/test_gradients.py docs/superpowers/notes/complex-step-verdict.md
git commit -m "feat: add FD gradients with a scale-aware step rule and complex-step oracle"
```

---

## Task 12: Analytic forward-mode for Matérn ν=1/2 and gradient-capability resolution

**Goal:** One family ships a real analytic gradient, so the forward-mode machinery is exercised now rather than in Phase 3, and the composite resolution rule is testable against a family that lacks one.

**Files:**
- Modify: `src/metamer/core/families/matern12.py` (add `dtransition`, `dprocess_noise`, `dstationary_cov`; flip `gradient_modes[ML]` to `ANALYTIC`)
- Modify: `src/metamer/core/gradients.py` (forward-mode dispatch)
- Create: `tests/test_gradient_capability.py`

**Acceptance Criteria:**
- [x] `matern12` analytic derivatives match the complex-step (or Richardson) oracle to the level recorded in Task 11
- [x] A composite of `matern12 + matern32` resolves to `FINITE_DIFFERENCE`, because `matern32` has no analytic gradient
- [x] A composite of `matern12 + matern12` resolves to `ANALYTIC` under ML and `FINITE_DIFFERENCE` under REML
- [x] The resolved gradient mode is a **reported field**, not a silent fallback
- [x] A test-only stub family exercises the resolution logic without shipping a real family

**Verify:** `pixi run test tests/test_gradient_capability.py -v`

> **Corrections applied at implementation time (commit `6c63451`). The fences
> below are the pre-audit draft; `families/matern12.py`, `families/base.py` and
> `gradients.py` are authoritative.**
>
> 1. **`dQ/dσ` uses `-expm1`, not `1 - exp(-x)`.** The fence proposed the naive
>    form, contradicting the docstring in the same file it modifies. Measured
>    relative error of the naive form: 1.09e-10 at `2Δt/ρ = 2e-7`, **8.28e-08 at
>    2e-10**, 7.99e-04 at 2e-14. **The ordinary fixture cannot see it** — at
>    `Δt = 2, ρ = 5` the ratio is 0.8 and the two forms agree to 1.2e-16, so the
>    small-ratio case is a separate test (pre-flight (i)).
> 2. **The fence tested only `dtransition`** while shipping `dprocess_noise` and
>    `dstationary_cov` unverified. All three are now checked against the oracle
>    and against their hand-differentiated forms.
> 3. **The gradient hook is added to the kernel protocol.** Design doc §8.2
>    calls it non-retrofittable and the fence omitted it entirely.
>    `DifferentiableFamily` is a *separate* `Protocol` so that declining stays
>    cheaper than complying, and `resolve_gradient_mode` **refuses** a family
>    that declares ANALYTIC without implementing it — a composite reporting
>    ANALYTIC while FD silently runs is the inverse of a silent fallback and
>    just as invisible. `test_families` asserts this for every family.
> 4. **The oracle is `richardson_gradient`, not complex-step**, per Task 11's
>    verdict. Tolerance `1e-11`, derived: the oracle's worst disagreement with
>    the paper forms is 6.67e-13 (15× headroom), it is four decades below the
>    ~1e-7 a real derivation error gives, and it is tighter than the ~4e-11
>    plain central differences reach — so a wrong derivative cannot pass by
>    agreeing with a weak reference. Complex-step *is* exact on these closed
>    forms (1e-16) and appears as a corroborating route, which localizes Task
>    11's verdict to the objective's cast chain rather than to complex-step.
> 5. **`resolve_gradient_mode` is fully annotated.** The fence's
>    `def resolve_gradient_mode(spec, objective) -> "GradientMode"` fails
>    `mypy --strict` under `disallow_untyped_defs`.
> 6. **`EXPECTED_GRADIENT_MODES` in `tests/test_families.py` had to change** —
>    it pins each family's declared modes, and flipping `matern12[ML]` breaks it
>    by design. That table's own comment anticipated this task.
>
> **Scope boundary, stated because "analytic forward-mode" can be read two
> ways:** this task ships the per-family derivative matrices and the capability
> machinery. It does **not** ship a differentiated Kalman filter, so the
> optimizer still calls `fd_gradient` even where resolution reports ANALYTIC.
> `test_the_reported_mode_describes_the_family_not_the_optimizer_path` pins that
> boundary and fails the moment a likelihood-level analytic gradient lands.

**Steps:**

- [x] **Step 1: Write the failing tests**

```python
# tests/test_gradient_capability.py
import numpy as np
import pytest

from metamer.core.capability import GradientMode, Objective, intersect_gradient_modes
from metamer.core.families.matern12 import Matern12
from metamer.core.gradients import complex_step_gradient


def test_matern12_analytic_transition_derivative_matches_the_oracle():
    """d/d rho exp(-dt/rho) equals (dt/rho^2) exp(-dt/rho).

    Expected value determined independently by differentiating the closed form
    on paper, then cross-checked against the complex-step oracle -- which
    requires no derivation at all and so catches a wrong hand derivation that
    FD would happily agree with.
    """
    dt, sigma, rho = 2.0, 1.0, 5.0
    analytic = Matern12().dtransition(np.array([[sigma, rho]]), dt)[0, :, 0, 0]

    def f(theta):
        return complex(np.exp(-dt / theta[1]))

    oracle = complex_step_gradient(f, np.array([sigma, rho]))
    np.testing.assert_allclose(analytic, oracle, rtol=1e-10, atol=1e-14)


def test_composite_falls_back_when_any_term_lacks_an_analytic_gradient():
    """A composite has an analytic gradient only if every term does.

    Bug this catches: a composite silently using FD while reporting ANALYTIC,
    which is a ~1.7x cost difference at p=6 and makes the wall-time projection
    wrong.
    """
    has = {Objective.ML: GradientMode.ANALYTIC}
    lacks = {Objective.ML: GradientMode.FINITE_DIFFERENCE}
    assert intersect_gradient_modes([has, lacks], Objective.ML) is GradientMode.FINITE_DIFFERENCE
    assert intersect_gradient_modes([has, has], Objective.ML) is GradientMode.ANALYTIC


def test_gradient_capability_is_per_objective():
    """A family may ship analytic ML gradients before REML ones.

    Expected value determined independently: under ML the envelope theorem
    removes the d beta_hat / d theta term exactly, but the REML penalty is not
    covered by that argument, so its analytic gradient is strictly more work.
    """
    modes = Matern12().gradient_modes
    assert modes[Objective.ML] is GradientMode.ANALYTIC
    assert modes[Objective.REML] is GradientMode.FINITE_DIFFERENCE


def test_stub_family_exercises_resolution_without_shipping_a_family():
    """A test-only stub covers the resolution logic in isolation.

    Bug this catches: resolution logic that is only ever exercised through
    real families, so a bug in it hides until a third-party kernel registers.
    """

    class _Stub:
        gradient_modes = {Objective.ML: GradientMode.ANALYTIC, Objective.REML: GradientMode.ANALYTIC}

    resolved = intersect_gradient_modes(
        [_Stub().gradient_modes, Matern12().gradient_modes], Objective.REML
    )
    assert resolved is GradientMode.FINITE_DIFFERENCE
```

- [x] **Step 2: Add analytic derivatives to Matern12**

```python
    def dtransition(self, theta: NDArray[np.float64], dt: float) -> NDArray[np.float64]:
        """Return dF/dtheta, shape (B, p, 1, 1).

        F = exp(-dt/rho), so dF/dsigma = 0 and dF/drho = (dt/rho^2) F.
        """
        arr = np.asarray(theta, dtype=np.float64)
        rho = arr[:, 1]
        f = np.exp(-float(dt) / rho)
        out = np.zeros((arr.shape[0], 2, 1, 1), dtype=np.float64)
        out[:, 1, 0, 0] = float(dt) / rho**2 * f
        return out

    def dstationary_cov(self, theta: NDArray[np.float64]) -> NDArray[np.float64]:
        """Return dP_inf/dtheta, shape (B, p, 1, 1). P_inf = sigma^2."""
        arr = np.asarray(theta, dtype=np.float64)
        out = np.zeros((arr.shape[0], 2, 1, 1), dtype=np.float64)
        out[:, 0, 0, 0] = 2.0 * arr[:, 0]
        return out

    def dprocess_noise(self, theta: NDArray[np.float64], dt: float) -> NDArray[np.float64]:
        """Return dQ/dtheta, shape (B, p, 1, 1).

        Q = sigma^2 (1 - exp(-2 dt / rho)); differentiate both factors.
        """
        arr = np.asarray(theta, dtype=np.float64)
        sigma, rho = arr[:, 0], arr[:, 1]
        decay = np.exp(-2.0 * float(dt) / rho)
        out = np.zeros((arr.shape[0], 2, 1, 1), dtype=np.float64)
        out[:, 0, 0, 0] = 2.0 * sigma * (1.0 - decay)
        out[:, 1, 0, 0] = -(sigma**2) * decay * (2.0 * float(dt) / rho**2)
        return out
```

Flip `gradient_modes[Objective.ML]` to `GradientMode.ANALYTIC` in the same file.

- [x] **Step 3: Add the resolution helper to gradients.py**

```python
def resolve_gradient_mode(spec, objective) -> "GradientMode":
    """Resolve a composite's gradient mode and return it for reporting.

    The resolved mode is a reported field on every result. A composite
    silently falling back to finite differences must not be invisible.
    """
    from metamer.core.capability import intersect_gradient_modes
    from metamer.core.registry import kernel_registry

    modes = [kernel_registry[t.kind]().gradient_modes for t in spec.terms]
    return intersect_gradient_modes(modes, objective)
```

- [x] **Step 4: Run tests and commit**

Run: `pixi run test tests/test_gradient_capability.py -v` → all PASS

```bash
git add src/metamer/core/families/matern12.py src/metamer/core/gradients.py tests/test_gradient_capability.py
git commit -m "feat: add analytic forward-mode for Matern 1/2 and gradient resolution"
```

---

## Task 13: Optimizer driver — initialization ladder, convergence, Hessian at optimum

**Goal:** The reference per-series optimizer (plain scipy L-BFGS-B in a loop), a deterministic moment-based initialization ladder with a reported rung, and an explicit Hessian at the optimum.

**This is path A's permanent reference form.** It is deliberately not fast. Whether the batched trust-region is ever built is decided by Task 18.

**Files:**
- Create: `src/metamer/core/optimize.py`
- Create: `tests/test_optimize.py`

**Acceptance Criteria:**
- [x] Moment initialization recovers `ρ` within a factor of 3 on a simulated OU series
- [x] The ladder falls back `moment → clipped → family default` and **reports the rung reached**
- [x] A degenerate series (zero variance) reaches the `default` rung rather than raising
- [x] Convergence is judged in unconstrained coordinates on relative gradient norm and relative function change
- [x] Hitting the iteration cap with a small gradient gives `ITER_CAP_SMALL_GRAD`; with a large gradient, `ITER_CAP_LARGE_GRAD`
- [x] A parameter reaching a diagnostic limit gives `DIAGNOSTIC_LIMIT`
- [x] Hessian at the optimum matches `fd_hessian` from `tests/oracles.py` to 1e-4 relative
- [x] A Hessian with condition number above threshold gives `DEGENERATE_HESSIAN`

**Verify:** `pixi run test tests/test_optimize.py -v`

> **Corrections applied at implementation time. The fences below are the
> pre-audit draft; `src/metamer/core/optimize.py` is authoritative.**
>
> 1. **The Hessian step is `eps^(1/4)`, not `max(fd_step(scale), 1e-5)`.** A
>    second central difference divides by `h²`, so its cancellation error is
>    `4ε|f|/h²` and its optimum is `(ε|f|/|f''''|)^(1/4)` — 1.221e-04, not
>    6.055e-06. Measured against a nested Richardson oracle on the real filter
>    at N = 200: **4.39e-05** for the fence's step, **2.86e-05** for
>    `eps^(1/3)`, **2.98e-07** for `eps^(1/4)`. A factor of 147, and a sweep
>    over ten decades puts the empirical optimum at 1e-04. Reusing `fd_step`
>    here is the easiest mistake in the file, so `hessian_step` is a separate
>    function.
> 2. **The oracle is a nested Richardson construction, not `oracles.fd_hessian`.**
>    That helper and `hessian_at_optimum` are the *same stencil* at different
>    steps, so checking one against the other measures the step choice and
>    nothing else — pre-flight (i). The oracle now differentiates a
>    Richardson-extrapolated gradient by Richardson; its own asymmetry is
>    **8.8e-13**. Gate `1e-5`: ~34× headroom over the achieved 2.98e-07, and
>    the fence's step fails it.
> 3. **The outcome precedence is reordered.** The fence checked the Hessian
>    *before* the iteration cap, so a fit that had simply not converged would
>    report `DEGENERATE_HESSIAN`. Curvature at a non-optimum means nothing, so
>    the cap and the diagnostic limit are now classified first, and the Hessian
>    is not computed at all for a non-OK fit — which also saves `2p²`
>    evaluations on exactly the fits that were slow enough to hit the cap.
> 4. **`TRUST_RADIUS_COLLAPSED` is now reachable.** The fence produced five of
>    the taxonomy's optimizer outcomes and never this one, which would leave
>    design doc §18 criterion 12 unsatisfiable once Task 19 is deleted.
>    scipy's `status == 2` is ABNORMAL_TERMINATION_IN_LNSRCH — the line search
>    could not find a decreasing step, the line-search analogue of a collapsed
>    trust region. `outcome_for_status` maps it, and an unrecognized status maps
>    to a failure rather than to `OK`.
> 5. **Two hidden clamps removed from `moment_init`, both of which fabricated a
>    plausible number.** `np.clip(r1, 1e-6, 1 - 1e-6)` turns "the data are
>    anticorrelated at lag 1, which this family cannot represent" into
>    `rho = 0.0724` at `dt = 1`, reported as MOMENT; `np.sqrt(np.maximum(var,
>    1e-12))` reports `sigma = 1e-6` for any series below 1e-12 variance —
>    **above sigma's own 1e-8 diagnostic limit, so the clip never fires and the
>    CLIPPED rung is unreachable for the vanishing-amplitude case.** A floor
>    that pre-empts a diagnostic limit converts a reportable fact into a
>    fabricated one. Both now fall through the ladder and report the rung.
> 6. **The reported covariance's first-order caveat is quantified, not
>    assumed.** `J Σ_u Jᵀ` under a `Log` transform understates the true
>    (lognormal) variance by `(e^s − 1)e^s/s` with `s = σ_u²`: **1.5% at
>    σ_u = 0.1, 46% at 0.5, 367% at 1.0**. Large `σ_u` is the regime near a
>    diagnostic limit, so the caveat travels with the headline number.
> 7. **`SeriesFit`'s scalar shape is documented as deliberate** in the module
>    docstring, with the reason: this module *is* path A's per-series reference
>    form (§17). It is the one place in `core` where scalar is correct, and a
>    later (b) sweep would otherwise flag it and someone would "fix" it.

**Steps:**

- [x] **Step 1: Write the failing tests**

```python
# tests/test_optimize.py
import numpy as np
import pytest

from metamer.core.capability import Objective
from metamer.core.engines.kalman import KalmanEngine
from metamer.core.objective import ConcentratedObjective
from metamer.core.signal import DesignInfo
from metamer.core.optimize import InitRung, hessian_at_optimum, moment_init, optimize_series
from metamer.core.outcomes import Outcome
from metamer.core.statespace import StateSpace
from metamer.core.terms import ProcessSpec
from tests.oracles import fd_hessian
from tests.test_kalman import _covariance
from tests.test_statespace import _term


def _ou_series(sigma=1.0, rho=8.0, n=400, seed=11):
    spec = ProcessSpec((_term("matern12"),))
    ss = StateSpace.from_spec(spec)
    theta = np.array([[sigma, rho]])
    t = np.arange(float(n))
    cov = _covariance(ss, theta, t)
    rng = np.random.default_rng(seed)
    y = rng.multivariate_normal(np.zeros(n), cov)[None, :]
    return spec, ss, theta, t, y


def test_moment_init_recovers_the_timescale_within_a_factor_of_three():
    """The deterministic initializer lands in the right basin.

    Expected value determined independently: the lag-1 autocorrelation of an
    OU process is exp(-dt/rho), so rho_hat = -dt / log(r1) by hand. A factor
    of 3 is a deliberately loose band -- this is a starting point, not an
    estimate.

    Bug this catches: an initializer that returns the family default whatever
    the data, which would silently make every fit a cold start from 1.0.
    """
    spec, _, theta, t, y = _ou_series(rho=8.0)
    init, rung = moment_init(spec, y, np.ones_like(y, dtype=bool), t)
    assert rung is InitRung.MOMENT
    assert init.shape[1] == spec.n_theta()
    assert 8.0 / 3.0 < init[0, 1] < 8.0 * 3.0


def test_zero_variance_series_falls_through_to_the_family_default():
    """A degenerate series reaches the default rung rather than raising.

    Bug this catches: a NaN or a divide-by-zero escaping the initializer,
    which at 10^7 points would abort a tile instead of recording an outcome.
    """
    spec = ProcessSpec((_term("matern12"),))
    t = np.arange(50.0)
    y = np.zeros((1, 50))
    init, rung = moment_init(spec, y, np.ones_like(y, dtype=bool), t)
    assert rung is InitRung.DEFAULT
    assert np.all(np.isfinite(init))


def test_optimizer_recovers_simulated_parameters():
    """Fitting a simulated OU series returns close to the truth.

    Expected value determined independently: the series was generated from
    known sigma and rho, so recovery within 30% at N=400 is a weak but
    honest check that the optimizer is descending the right surface.
    """
    spec, ss, theta, t, y = _ou_series(sigma=1.0, rho=8.0)
    obj = ConcentratedObjective(spec, ss, KalmanEngine(), Objective.ML)
    result = optimize_series(obj, y, np.ones_like(y, dtype=bool), t, design=None)
    assert result.outcome is Outcome.OK
    assert result.theta[0, 1] == pytest.approx(8.0, rel=0.3)


def test_iteration_cap_outcome_depends_on_the_gradient_norm():
    """Cap-with-small-gradient and cap-with-large-gradient are distinct.

    Bug this catches: collapsing both into one 'not converged' flag, which
    discards the distinction between a slow fit and a failed one -- and at
    10^7 points nobody will re-inspect.
    """
    spec, ss, _, t, y = _ou_series()
    obj = ConcentratedObjective(spec, ss, KalmanEngine(), Objective.ML)
    capped = optimize_series(
        obj, y, np.ones_like(y, dtype=bool), t, design=None, max_iter=1
    )
    assert capped.outcome in {Outcome.ITER_CAP_SMALL_GRAD, Outcome.ITER_CAP_LARGE_GRAD}


def test_hessian_matches_the_brute_force_oracle():
    """The reported Hessian matches a brute-force FD Hessian.

    The oracle is a double-central-difference of the objective, sharing no
    code with the Hessian routine.

    Bug this catches: reusing the quasi-Newton approximation, which is too
    crude for TIC and the sandwich estimator and would make reported parameter
    uncertainties quietly wrong.
    """
    spec, ss, _, t, y = _ou_series(n=200)
    obj = ConcentratedObjective(spec, ss, KalmanEngine(), Objective.ML)
    mask = np.ones_like(y, dtype=bool)

    def f(u):
        return float(obj.unconstrained_loglik(u[None, :], y, mask, t, None)[0])

    u0 = np.array([0.0, np.log(8.0)])
    np.testing.assert_allclose(
        hessian_at_optimum(f, u0, scale=200.0), fd_hessian(f, u0), rtol=1e-4, atol=1e-4
    )
```

- [x] **Step 2: Implement optimize.py**

```python
# src/metamer/core/optimize.py
"""Reference per-series optimizer, initialization ladder, and Hessian.

This is path A's permanent reference form: a plain scipy loop over series. It is
deliberately not fast. A correctness reference does not need to be, and whether
the batched trust-region is ever built is decided by the stage-1 spike.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import minimize

from metamer.core.gradients import fd_gradient, fd_step
from metamer.core.objective import ConcentratedObjective
from metamer.core.signal import DesignInfo
from metamer.core.outcomes import Outcome
from metamer.core.terms import ProcessSpec, free_param_index

GRAD_TOL = 1e-5
"""Relative gradient-norm tolerance, judged in unconstrained coordinates."""

HESSIAN_COND_LIMIT = 1e10
"""Above this condition number the fit is reported as near-degenerate."""


class InitRung(StrEnum):
    """Which rung of the initialization ladder produced the starting point."""

    WARM_START = "warm_start"
    MOMENT = "moment"
    CLIPPED = "clipped"
    DEFAULT = "default"


@dataclass(frozen=True)
class SeriesFit:
    """One series' fit result."""

    theta: NDArray[np.float64]
    loglik: float
    outcome: Outcome
    n_iter: int
    init_rung: InitRung
    hessian: NDArray[np.float64] | None


def moment_init(
    spec: ProcessSpec,
    y: NDArray[np.float64],
    mask: NDArray[np.bool_],
    t: NDArray[np.float64],
) -> tuple[NDArray[np.float64], InitRung]:
    """Deterministic moment-based starting point, with a fallback ladder.

    Deterministic rather than random multi-start: reproducible, seed-free, and
    the precursor of the Whittle screening pass. Random multi-start is a
    straight multiplier on a budget with little headroom.

    Ladder: moment estimate -> clipped to diagnostic limits -> family default.
    The rung reached is returned so it can be reported.

    Args:
        spec: The noise specification. Note this takes the SPEC, not the state
            space: parameter defaults and the free-parameter layout both come
            from the spec, and reading them from `family.param_specs()` instead
            was a second, independent ordering source that nothing kept in sync
            with `free_param_index`.
        y: Observations, shape (B, N).
        mask: Presence mask, shape (B, N).
        t: Shared time axis, shape (N,).

    Returns:
        A tuple of the starting theta (B, p_free) in natural units and the rung.
    """
    free = free_param_index(spec)
    by_label = dict(zip(spec.labels(), spec.terms, strict=True))
    defaults = np.array(
        [by_label[label].params[name].default for label, name in free], dtype=np.float64
    )
    batch = y.shape[0]
    start = np.repeat(defaults[None, :], batch, axis=0)

    valid = mask.sum(axis=1)
    var = np.where(valid > 1, np.nanvar(np.where(mask, y, np.nan), axis=1), 0.0)
    if not np.all(np.isfinite(var)) or np.all(var <= 0.0):
        return start, InitRung.DEFAULT

    centred = np.where(mask, y - np.nanmean(np.where(mask, y, np.nan), axis=1, keepdims=True), 0.0)
    num = np.sum(centred[:, 1:] * centred[:, :-1], axis=1)
    den = np.sum(centred**2, axis=1)
    r1 = np.divide(num, den, out=np.zeros_like(num), where=den > 0)

    dt = float(np.median(np.diff(t))) if t.size > 1 else 1.0
    with np.errstate(divide="ignore", invalid="ignore"):
        rho = -dt / np.log(np.clip(r1, 1e-6, 1.0 - 1e-6))

    rung = InitRung.MOMENT
    for index, (label, name) in enumerate(free):
        param = by_label[label].params[name]
        if name == "sigma":
            start[:, index] = np.sqrt(np.maximum(var, 1e-12))
        elif name == "rho":
            start[:, index] = rho
        lo, hi = param.diagnostic_limits
        clipped = np.clip(start[:, index], lo, hi)
        if not np.array_equal(clipped, start[:, index]):
            rung = InitRung.CLIPPED
        start[:, index] = clipped

    if not np.all(np.isfinite(start)):
        return np.repeat(defaults[None, :], batch, axis=0), InitRung.DEFAULT
    return start, rung


def hessian_at_optimum(
    fn: Callable[[NDArray[np.float64]], float], u: NDArray[np.float64], scale: float
) -> NDArray[np.float64]:
    """Explicit Hessian by central differences on the objective.

    A converged quasi-Newton approximation is too crude for TIC, the sandwich
    estimator, and near-degeneracy detection, so the Hessian is computed
    explicitly once per fit. At p=6 that is ~2p^2 = 72 passes, roughly +12% on
    a 50-iteration fit.
    """
    u = np.asarray(u, dtype=np.float64)
    h = max(fd_step(scale), 1e-5)
    p = u.size
    out = np.zeros((p, p), dtype=np.float64)
    for i in range(p):
        for j in range(i, p):
            ei = np.zeros(p)
            ej = np.zeros(p)
            ei[i] = h
            ej[j] = h
            value = (fn(u + ei + ej) - fn(u + ei - ej) - fn(u - ei + ej) + fn(u - ei - ej)) / (
                4.0 * h * h
            )
            out[i, j] = out[j, i] = value
    return out


def optimize_series(
    objective: ConcentratedObjective,
    y: NDArray[np.float64],
    mask: NDArray[np.bool_],
    t: NDArray[np.float64],
    design: DesignInfo | None,
    x0: NDArray[np.float64] | None = None,
    max_iter: int = 200,
) -> SeriesFit:
    """Fit one series. The batch driver in `fit.py` loops over this.

    Args:
        objective: The concentrated objective.
        y: Observations, shape (1, N).
        mask: Presence mask, shape (1, N).
        t: Shared time axis, shape (N,).
        design: The built design matrix and its theta-free quantities, or None.
        x0: Optional warm start in unconstrained coordinates, shape (1, p).
        max_iter: Iteration cap.

    Returns:
        A SeriesFit carrying theta in natural units and a taxonomy outcome.
    """
    # p is the FREE parameter count, from the single source of truth. Using
    # len(term.params) here would size the vector to include frozen parameters
    # and silently shift every later coordinate.
    free = free_param_index(objective.spec)
    p = len(free)

    if design is not None and design.matrix.size:
        codes = objective.check_design(design, 1)
        if codes[0] != Outcome.OK.code:
            outcome = Outcome.from_code(int(codes[0]))
            return SeriesFit(
                np.full((1, p), np.nan), float("nan"), outcome, 0, InitRung.DEFAULT, None
            )

    if x0 is None:
        start_natural, rung = moment_init(objective.spec, y, mask, t)
        u0 = objective.to_unconstrained(start_natural)[0]
    else:
        u0, rung = np.asarray(x0, dtype=np.float64)[0], InitRung.WARM_START

    scale = float(max(mask.sum(), 1))

    def negative(u: NDArray[np.float64]) -> float:
        # NaN (a failed evaluation) and -inf both become +inf here. This is the
        # ONLY place -inf-as-barrier is used: results destined for the store
        # carry NaN, because -inf is a finite-looking sentinel that survives
        # some consumers' checks and poisons a downstream mean.
        value = objective.unconstrained_loglik(u[None, :], y, mask, t, design)[0]
        return float(np.inf) if not np.isfinite(value) else float(-value)

    def jac(u: NDArray[np.float64]) -> NDArray[np.float64]:
        return fd_gradient(negative, u, scale)

    res = minimize(negative, u0, jac=jac, method="L-BFGS-B", options={"maxiter": max_iter})
    theta = objective.to_natural(np.atleast_2d(res.x))
    loglik = -float(res.fun)

    if not np.isfinite(loglik):
        return SeriesFit(theta, loglik, Outcome.NONFINITE_OBJECTIVE, res.nit, rung, None)

    by_label = dict(zip(objective.spec.labels(), objective.spec.terms, strict=True))
    limit_hit = any(
        by_label[label].params[name].at_diagnostic_limit(float(theta[0, i]))
        for i, (label, name) in enumerate(free)
    )
    if limit_hit:
        return SeriesFit(theta, loglik, Outcome.DIAGNOSTIC_LIMIT, res.nit, rung, None)

    hess = hessian_at_optimum(negative, res.x, scale)
    if float(np.linalg.cond(hess)) > HESSIAN_COND_LIMIT:
        return SeriesFit(theta, loglik, Outcome.DEGENERATE_HESSIAN, res.nit, rung, hess)

    grad_norm = float(np.linalg.norm(jac(res.x)))
    if res.nit >= max_iter:
        capped = (
            Outcome.ITER_CAP_SMALL_GRAD
            if grad_norm < GRAD_TOL * max(abs(loglik), 1.0)
            else Outcome.ITER_CAP_LARGE_GRAD
        )
        return SeriesFit(theta, loglik, capped, res.nit, rung, hess)

    return SeriesFit(theta, loglik, Outcome.OK, res.nit, rung, hess)
```

- [x] **Step 3: Run tests and commit**

Run: `pixi run test tests/test_optimize.py -v` → all PASS

```bash
git add src/metamer/core/optimize.py tests/test_optimize.py
git commit -m "feat: add reference optimizer, init ladder, and explicit Hessian"
```

---

## Task 14: `fit()` — the (B, N) driver

**Goal:** The public entry point: a batched driver taking a candidate set, returning tagged scores, a ranking, natural-unit uncertainties via the delta method, and a per-(series, candidate) outcome.

**Files:**
- Create: `src/metamer/core/fit.py`; modify `src/metamer/core/__init__.py` to re-export
- Create: `tests/test_fit.py`

**Acceptance Criteria:**
- [x] `fit(y, t, signal, candidates)` accepts `y` of shape `(B, N)` and returns per-(series, candidate) results
- [x] `B=1` and `B=64` give identical per-series output for identical inputs
- [x] `x0` is accepted and, when supplied, `init_rung == WARM_START`
- [x] Parameter uncertainties are in **natural units**, via `delta_method_cov`
- [x] A `DIAGNOSTIC_LIMIT` outcome also marks that parameter's uncertainty unreliable
- [x] Every result carries `engine`, `objective`, and the resolved `gradient_mode`
- [x] Selection uses `rank_candidates`, so the comparability guards apply
- [x] **Standing invariant: batched results equal solo results series by series**, for both `loglik` and `outcome`

**Verify:** `pixi run test tests/test_fit.py -v`

> **The fences below were CORRECTED IN PLACE on 2026-08-06**, during the forward
> audit run after Task 10 — before implementation, not after. They were written
> against the pre-Task-9 scalar model and called six things that no longer exist
> in that form. Re-run pre-flight (g) against them anyway; the correction is one
> reading of the source, not a substitute for it.
>
> 1. **`signal.design_info(t, mask)`** — `mask` is required, and it is what makes
>    `rank`, `gram_logdet`, `condition_number` and `n_rows` per series. A design
>    built without it reports a batch-wide rank that a gap invalidates, which is
>    the `design_rank` / `rank_x` distinction one level up.
> 2. **`penalty_terms` is keyword-only and per series**: `n_obs=design.n_rows`,
>    `design_rank=design.rank`, `outcome=outcome[:, c]`, `k_beta=k_beta`, all
>    `(B,)`. The old call passed `int(mask[b].sum())` and `design.rank`
>    positionally, one series at a time.
> 3. **`CandidateScores` is one `(B, M)` block**, not a `CandidateScore` per
>    `(series, candidate)` built in a double Python loop — that loop is
>    per-point Python over 10⁷ grid points.
> 4. **`n_eff` is `n_eff_bic(...)`, not `float(n)`.** Passing `n` makes
>    `Criterion.BIC_NEFF` silently identical to `BIC`: no error, no warning, a
>    plausible number. It is computed once at the optimum, per
>    `(series, candidate)`, from the HYDRATED natural vector — never inside the
>    fit loop, where its O(n_used²) sum would run every iteration.
> 5. **`FitResult.outcome` is `(B, M)` uint8 codes**, not an object array of
>    `Outcome` members. The codes are what the store writes, what
>    `penalty_terms(outcome=)` gates on, and what `CandidateScores.outcome`
>    takes. Note the test consequence: `out.outcome[0, 0] is Outcome.OK` is
>    False against a uint8, so a test guarded on it would silently assert
>    nothing — pre-flight (h) and (i).
> 6. **`FitResult.ranking` is one `Ranking`**, not a list of B of them.
>    `rank_candidates` is `(B, M)` in and `(B, M)` / `(B,)` out.
>
> **Still open for Task 14 to decide:** `n_eff_trend[y,x,m]` is a stored
> primitive (design doc §12.2) and is **not** wired here, because it needs the
> GLS trend variance and its white-noise equivalent, which means identifying
> which design column is the trend — `DesignInfo` exposes no such mapping today.
> Either widen `DesignInfo` or record the deferral explicitly; do not quietly
> leave the slot unwritten.

**Steps:**

- [x] **Step 1: Write the failing tests**

```python
# tests/test_fit.py
import numpy as np
import pytest

from metamer.core.capability import EngineId, Objective
from metamer.core.criteria import Criterion
from metamer.core.fit import fit
from metamer.core.outcomes import Outcome
from metamer.core.signal import Constant, SignalSpec, Trend
from metamer.core.terms import ProcessSpec
from tests.test_statespace import _term


def _candidates():
    return [
        ProcessSpec((_term("white"),)),
        ProcessSpec((_term("white"), _term("matern12"))),
    ]


def _data(batch=4, n=120, seed=5):
    rng = np.random.default_rng(seed)
    t = np.arange(float(n))
    y = rng.standard_normal((batch, n)) + 0.02 * (t - t.mean())
    return y, t


def test_fit_returns_a_result_per_series_and_candidate():
    """The result grid is (B, M).

    Bug this catches: collapsing the candidate axis, which would make ranking
    and delta-IC meaningless.
    """
    y, t = _data()
    out = fit(y, t, SignalSpec([Constant(), Trend()]), _candidates(), criterion=Criterion.AIC)
    assert out.theta.shape[0] == y.shape[0]
    assert len(out.candidates) == 2
    assert out.outcome.shape == (y.shape[0], 2)


def test_batch_of_one_matches_batch_of_many():
    """B=1 is a shape, not a code path.

    Bug this catches: a per-series driver that diverges from the batched one.
    This is the single invariant the whole design rests on.
    """
    y, t = _data(batch=8)
    signal = SignalSpec([Constant(), Trend()])
    many = fit(y, t, signal, _candidates(), criterion=Criterion.AIC)
    one = fit(y[:1], t, signal, _candidates(), criterion=Criterion.AIC)
    np.testing.assert_allclose(many.loglik[0], one.loglik[0], rtol=1e-12)


def test_batched_results_equal_solo_results_series_by_series():
    """STANDING INVARIANT: fitting B series together equals fitting each alone.

    This is the general guard against the whole batched-granularity class --
    any per-series concept accidentally implemented at batch granularity shows
    up here, whether it is a failure outcome, a validity mask, a factorization,
    or a reduction. It is deliberately a standing test rather than a regression
    test for one bug.

    Bug this catches: a scalar outcome, a batch-wide early return, or a
    factorization that raises for the stack when one member is bad -- none of
    which are visible at the B=1 or B=2 sizes the rest of the suite uses.
    """
    y, t = _data(batch=6, seed=17)
    signal = SignalSpec([Constant(), Trend()])
    cands = _candidates()
    together = fit(y, t, signal, cands, criterion=Criterion.AIC)
    for b in range(y.shape[0]):
        alone = fit(y[b : b + 1], t, signal, cands, criterion=Criterion.AIC)
        np.testing.assert_allclose(together.loglik[b], alone.loglik[0], rtol=1e-12)
        assert list(together.outcome[b]) == list(alone.outcome[0])


def test_warm_start_is_recorded_as_such():
    """Supplying x0 changes the reported initialization rung.

    Bug this catches: accepting x0 and silently ignoring it, which would make
    Phase 2's warm-starting a no-op that still carries all its hysteresis
    risk in the accounting.
    """
    from metamer.core.optimize import InitRung

    y, t = _data(batch=2)
    signal = SignalSpec([Constant()])
    cands = [ProcessSpec((_term("white"), _term("matern12")))]
    cold = fit(y, t, signal, cands, criterion=Criterion.AIC)
    warm = fit(y, t, signal, cands, criterion=Criterion.AIC, x0=cold.theta_unconstrained)
    assert warm.init_rung[0, 0] is InitRung.WARM_START


def test_uncertainties_are_reported_in_natural_units():
    """theta_err is in natural units, not log-space.

    Bug this catches: reporting the unconstrained standard error directly,
    which is the exact failure class this package exists to eliminate --
    plausible, wrong error bars.
    """
    y, t = _data(batch=1, n=300)
    out = fit(y, t, SignalSpec([Constant()]), [ProcessSpec((_term("matern12"),))], criterion=Criterion.AIC)
    # outcome holds CODES, not Outcome members -- `is Outcome.OK` against a
    # uint8 is False for every series, so this guard would skip the assertions
    # entirely and the test would pass without testing anything.
    assert out.outcome[0, 0] == Outcome.OK.code
    assert np.all(out.theta_err[0, 0] > 0.0)
    assert np.all(np.isfinite(out.theta_err[0, 0]))


def test_results_carry_all_three_provenance_tags():
    """engine, objective, and the resolved gradient mode are all reported.

    Bug this catches: an untagged result reaching selection, or a silent FD
    fallback that makes the wall-time projection wrong.
    """
    y, t = _data(batch=1)
    out = fit(y, t, SignalSpec([Constant()]), _candidates(), criterion=Criterion.AIC)
    assert out.engine is EngineId.KALMAN
    assert out.objective is Objective.ML
    assert len(out.gradient_mode) == 2
```

- [x] **Step 2: Implement fit.py**

```python
# src/metamer/core/fit.py
"""The (B, N) fit driver. B=1 is a shape, never a separate code path."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from metamer.core.capability import EngineId, GradientMode, Objective
from metamer.core.counting import n_eff_bic, penalty_terms
from metamer.core.criteria import CandidateScores, Criterion, Ranking, rank_candidates
from metamer.core.engines.kalman import KalmanEngine
from metamer.core.engines.protocol import Engine
from metamer.core.gradients import resolve_gradient_mode
from metamer.core.objective import ConcentratedObjective
from metamer.core.optimize import InitRung, optimize_series
from metamer.core.outcomes import Outcome
from metamer.core.signal import SignalSpec
from metamer.core.statespace import StateSpace
from metamer.core.terms import ProcessSpec, free_param_index
from metamer.core.transforms import delta_method_cov


@dataclass(frozen=True)
class FitResult:
    """Results for a batch of series across a candidate set.

    Attributes:
        outcome: Per-(series, candidate) outcome CODES, shape (B, M) uint8 --
            not `Outcome` members in an object array. The codes are what the
            store writes, what `penalty_terms(outcome=)` gates on, and what
            `CandidateScores.outcome` takes; an object array of enum members
            would have to be converted at each of those three boundaries, and a
            conversion that exists three times is a conversion that will
            disagree with itself once.
        ranking: ONE `Ranking`, spanning the batch. `rank_candidates` is
            `(B, M)` in and `(B, M)` / `(B,)` out, so a list of per-series
            rankings would be B copies of the same object shape.
    """

    candidates: tuple[ProcessSpec, ...]
    theta: NDArray[np.float64]
    theta_err: NDArray[np.float64]
    theta_unconstrained: NDArray[np.float64]
    beta: NDArray[np.float64]
    beta_err: NDArray[np.float64]
    loglik: NDArray[np.float64]
    outcome: NDArray[np.uint8]
    init_rung: NDArray[np.object_]
    n_iter: NDArray[np.int64]
    ranking: Ranking
    engine: EngineId
    objective: Objective
    gradient_mode: tuple[GradientMode, ...]


def fit(
    y: NDArray[np.float64],
    t: NDArray[np.float64],
    signal: SignalSpec,
    candidates: list[ProcessSpec],
    criterion: Criterion,
    mask: NDArray[np.bool_] | None = None,
    objective: Objective = Objective.ML,
    engine: Engine | None = None,
    x0: NDArray[np.float64] | None = None,
    max_iter: int = 200,
) -> FitResult:
    """Fit a candidate set to a batch of series and rank the candidates.

    Args:
        y: Observations, shape (B, N).
        t: Shared time axis, shape (N,).
        signal: The fixed signal specification; only the noise model is
            selected in v1.
        candidates: Noise specifications to compare.
        criterion: Information criterion for ranking.
        mask: Presence mask, shape (B, N). Defaults to all present.
        objective: ML (default) or REML.
        engine: Likelihood engine. Defaults to the batched Kalman filter.
        x0: Optional warm starts in unconstrained coordinates, shape
            (B, M, p_max). Phase 2 supplies these; the signature exists now
            because it constrains this one.
        max_iter: Iteration cap per series.

    Returns:
        A FitResult carrying natural-unit estimates, natural-unit
        uncertainties, per-(series, candidate) outcomes, and the ranking.
    """
    y = np.asarray(y, dtype=np.float64)
    t = np.asarray(t, dtype=np.float64)
    mask = np.ones_like(y, dtype=bool) if mask is None else np.asarray(mask, dtype=bool)
    engine = KalmanEngine() if engine is None else engine

    # design_info takes the MASK, and that is not optional: rank, gram_logdet,
    # condition_number and n_rows all describe X restricted to each series'
    # unmasked rows, which is why they are (B,) and not scalars. A design built
    # without the mask reports a batch-wide rank that a gap can invalidate --
    # the same distinction as design_rank vs rank_x, one level up.
    design = signal.design_info(t, mask)
    k_beta = design.n_beta
    batch = y.shape[0]
    n_cand = len(candidates)
    p_max = max(len(free_param_index(spec)) for spec in candidates)

    theta = np.full((batch, n_cand, p_max), np.nan)
    theta_u = np.full((batch, n_cand, p_max), np.nan)
    theta_err = np.full((batch, n_cand, p_max), np.nan)
    beta = np.full((batch, n_cand, k_beta), np.nan)
    beta_err = np.full((batch, n_cand, k_beta), np.nan)
    loglik = np.full((batch, n_cand), np.nan)
    outcome = np.full((batch, n_cand), Outcome.NOT_ATTEMPTED.code, dtype=np.uint8)
    rung = np.empty((batch, n_cand), dtype=object)
    n_iter = np.zeros((batch, n_cand), dtype=np.int64)
    # theta_full carries the HYDRATED natural vector, including frozen
    # parameters, because that is the layout StateSpace.param_slices expects
    # and therefore what n_eff_bic must be given.
    objectives_by_candidate: list[ConcentratedObjective] = []
    theta_full: list[NDArray[np.float64]] = []
    modes: list[GradientMode] = []

    for c, spec in enumerate(candidates):
        state_space = StateSpace.from_spec(spec)
        obj = ConcentratedObjective(spec, state_space, engine, objective)
        objectives_by_candidate.append(obj)
        modes.append(resolve_gradient_mode(spec, objective))
        p = len(free_param_index(spec))

        for b in range(batch):
            warm = None if x0 is None else x0[b : b + 1, c, :p]
            res = optimize_series(
                obj, y[b : b + 1], mask[b : b + 1], t, design, warm, max_iter
            )
            outcome[b, c] = res.outcome.code
            rung[b, c] = res.init_rung
            n_iter[b, c] = res.n_iter
            loglik[b, c] = res.loglik
            theta[b, c, :p] = res.theta[0]
            if res.hessian is not None and res.outcome is Outcome.OK:
                u_hat = obj.to_unconstrained(res.theta)[0]
                theta_u[b, c, :p] = u_hat
                cov_u = np.linalg.inv(res.hessian)
                cov_nat = delta_method_cov(obj.dforward(u_hat[None, :])[0], cov_u)
                theta_err[b, c, :p] = np.sqrt(np.clip(np.diag(cov_nat), 0.0, np.inf))
                # One evaluation at the optimum yields beta and beta_cov. An
                # earlier draft ran a second full filter pass here purely to
                # recover quantities the objective had already computed and
                # discarded.
                final = obj.evaluate(res.theta, y[b : b + 1], mask[b : b + 1], t, design)
                if k_beta and final.gls is not None and final.gls.outcome[0] == Outcome.OK.code:
                    beta[b, c] = final.gls.beta[0]
                    beta_err[b, c] = np.sqrt(np.clip(np.diag(final.gls.beta_cov[0]), 0.0, np.inf))

        # Hydrated once per candidate, after that candidate's whole batch is
        # fitted, because n_eff_bic wants (B, p_total) natural parameters.
        theta_full.append(obj.hydrate(theta[:, c, :p]))

    # k, n and n_eff come back from counting.py already per series. Unpacking
    # them one series at a time is precisely where the design_rank / rank_x
    # substitution and the n_obs - (-1) off-by-one get reintroduced by hand.
    k = np.full((batch, n_cand), np.nan)
    n = np.full((batch, n_cand), np.nan)
    n_eff = np.full((batch, n_cand), np.nan)
    for c, spec in enumerate(candidates):
        k[:, c], n[:, c] = penalty_terms(
            spec,
            objective,
            # design.n_rows is count_nonzero(mask, axis=1) -- the per-series
            # unmasked count, carrying no sentinel.
            n_obs=design.n_rows,
            # design_rank, NOT rank_x: rank_x is the whitened Gram's rank and
            # is -1 on every failed series, so n_obs - rank_x silently gives
            # n_obs + 1 there.
            design_rank=design.rank,
            outcome=outcome[:, c],
            k_beta=k_beta,
        )
        # Computed ONCE, at the optimum, per (series, candidate) -- never
        # inside the fit loop, where its O(n_used^2) realized-pairs sum would
        # run every iteration. `n_eff = n` would make BIC_NEFF silently
        # identical to BIC: no error, no warning, a plausible number.
        n_eff[:, c] = n_eff_bic(
            objectives_by_candidate[c].state_space,
            theta_full[c],
            t,
            mask=mask,
            outcome=outcome[:, c],
        )

    # ONE ranking over the whole (B, M) block. The comparability guards see the
    # candidate set's engine and objective tags before anything is scored.
    ranking = rank_candidates(
        CandidateScores(
            labels=tuple(spec.spec_hash()[:12] for spec in candidates),
            engines=(engine.engine_id,) * n_cand,
            objectives=(objective,) * n_cand,
            loglik=loglik,
            k=k,
            n=n,
            n_eff=n_eff,
            outcome=outcome,
        ),
        criterion,
    )

    return FitResult(
        candidates=tuple(candidates),
        theta=theta,
        theta_err=theta_err,
        theta_unconstrained=theta_u,
        beta=beta,
        beta_err=beta_err,
        loglik=loglik,
        outcome=outcome,
        init_rung=rung,
        n_iter=n_iter,
        ranking=ranking,
        engine=engine.engine_id,
        objective=objective,
        gradient_mode=tuple(modes),
    )
```

Re-export from `src/metamer/core/__init__.py`:

```python
from metamer.core import families  # noqa: F401  (registers built-in kernels)
from metamer.core.capability import EngineId, GradientMode, Objective
from metamer.core.criteria import Criterion
from metamer.core.fit import FitResult, fit
from metamer.core.outcomes import Outcome
from metamer.core.signal import SignalSpec
from metamer.core.terms import ProcessSpec, TermSpec

__all__ = [
    "Criterion", "EngineId", "FitResult", "GradientMode", "Objective",
    "Outcome", "ProcessSpec", "SignalSpec", "TermSpec", "fit",
]
```

- [x] **Step 3: Run tests and commit**

Run: `pixi run test tests/test_fit.py -v` → all PASS

```bash
git add src/metamer/core/fit.py src/metamer/core/__init__.py tests/test_fit.py
git commit -m "feat: add the (B, N) fit driver with natural-unit uncertainties"
```

---

## Task 15: Static identifiability lint

**Goal:** Flag structurally non-identifiable compositions at construction time. **Warn, do not block — but say it out loud.**

**Files:**
- Create: `src/metamer/core/lint.py`; create `tests/test_lint.py`

**Acceptance Criteria:**
- [ ] `white + matern12` with `ρ` below a stated fraction of the sampling interval flags "collapses to white + white"
- [ ] Two free-`ν` Matérn terms with overlapping timescales flag "terms may collapse onto each other"
- [ ] A clean composite returns an empty finding list
- [ ] Findings are warnings, never exceptions — `lint()` returns, it does not raise
- [ ] Each finding names the offending term labels, not just the composite

**Verify:** `pixi run test tests/test_lint.py -v`

**Steps:**

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_lint.py
from dataclasses import replace

from metamer.core.lint import lint
from metamer.core.terms import ProcessSpec, TermSpec
from tests.test_statespace import _term


def _with(term: TermSpec, **defaults: float) -> TermSpec:
    params = {
        name: replace(p, default=defaults.get(name, p.default)) for name, p in term.params.items()
    }
    return TermSpec(kind=term.kind, params=params, ordering_param=term.ordering_param)


def test_short_timescale_matern_is_flagged_as_white():
    """matern12 with rho far below the sampling interval is white noise.

    Expected value determined independently: exp(-dt/rho) -> 0 as rho -> 0, so
    the process decorrelates entirely between samples and is indistinguishable
    from white noise at the observed cadence.
    """
    spec = ProcessSpec((_term("white"), _with(_term("matern12"), rho=1e-4)))
    findings = lint(spec, sampling_interval=1.0)
    assert any("white" in f.message for f in findings)
    assert any("matern12[0]" in f.terms for f in findings)


def test_overlapping_matern_terms_are_flagged():
    """Two same-kind terms with nearly equal timescales may collapse.

    Bug this catches: shipping a candidate set whose members are pairwise
    indistinguishable, which produces meaningless IC weights.
    """
    spec = ProcessSpec((_with(_term("matern12"), rho=5.0), _with(_term("matern12"), rho=5.2)))
    findings = lint(spec, sampling_interval=1.0)
    assert any("collapse" in f.message for f in findings)


def test_clean_composite_produces_no_findings():
    """A well-separated composite lints clean.

    Bug this catches: a lint that fires on everything, which trains users to
    ignore it.
    """
    spec = ProcessSpec((_term("white"), _with(_term("matern12"), rho=30.0)))
    assert lint(spec, sampling_interval=1.0) == []


def test_lint_warns_and_never_raises():
    """Degenerate specifications are reported, not rejected.

    Bug this catches: blocking a user from fitting a model they knowingly
    want. The lint's job is to say it out loud, not to decide.
    """
    spec = ProcessSpec((_with(_term("matern12"), rho=1e-6),))
    assert isinstance(lint(spec, sampling_interval=1.0), list)
```

- [ ] **Step 2: Implement lint.py**

```python
# src/metamer/core/lint.py
"""Static identifiability lint over a composite specification.

Compositional freedom lets users specify structurally non-identifiable models.
This pass flags the known-degenerate patterns at construction time. A runtime
counterpart flags near-degeneracy in the fitted solution via the Hessian
condition number (see `optimize.HESSIAN_COND_LIMIT`).

Warn, do not block.
"""

from __future__ import annotations

from dataclasses import dataclass

from metamer.core.terms import ProcessSpec

SHORT_TIMESCALE_FRACTION = 0.1
"""Below this multiple of the sampling interval a process reads as white."""

OVERLAP_RATIO = 1.5
"""Same-kind terms within this ratio of each other may be inseparable."""


@dataclass(frozen=True)
class Finding:
    """One lint finding."""

    terms: tuple[str, ...]
    message: str


def lint(spec: ProcessSpec, sampling_interval: float) -> list[Finding]:
    """Report structurally degenerate patterns in a composition.

    Args:
        spec: The composite specification.
        sampling_interval: Median observation spacing, in the same time units
            as the timescale parameters.

    Returns:
        A list of findings, empty if the composition lints clean.
    """
    findings: list[Finding] = []
    labels = spec.labels()

    timescales: list[tuple[str, str, float]] = []
    for label, term in zip(labels, spec.terms, strict=True):
        if "rho" not in term.params:
            continue
        rho = float(term.params["rho"].default)
        timescales.append((label, term.kind, rho))
        if rho < SHORT_TIMESCALE_FRACTION * sampling_interval:
            findings.append(
                Finding(
                    terms=(label,),
                    message=(
                        f"{label}: rho={rho:g} is far below the sampling interval "
                        f"{sampling_interval:g}; this term is indistinguishable from "
                        "white noise at the observed cadence"
                    ),
                )
            )

    for i, (label_a, kind_a, rho_a) in enumerate(timescales):
        for label_b, kind_b, rho_b in timescales[i + 1 :]:
            if kind_a != kind_b:
                continue
            hi, lo = max(rho_a, rho_b), min(rho_a, rho_b)
            if lo > 0.0 and hi / lo < OVERLAP_RATIO:
                findings.append(
                    Finding(
                        terms=(label_a, label_b),
                        message=(
                            f"{label_a} and {label_b} have timescales within a factor of "
                            f"{hi / lo:.2f}; these terms may collapse onto each other and "
                            "the resulting IC weights would not be meaningful"
                        ),
                    )
                )
    return findings
```

- [ ] **Step 3: Run tests and commit**

Run: `pixi run test tests/test_lint.py -v` → all PASS

```bash
git add src/metamer/core/lint.py tests/test_lint.py
git commit -m "feat: add static identifiability lint"
```

---

## Task 16: Three-hash machinery with the compat-relevance allowlist

**Goal:** `fit_hash ⊂ compat_hash ⊂ run_hash`, hashed from a normalized model rather than file text, with compat-relevance declared by **allowlist**.

**Files:**
- Create: `src/metamer/core/hashing.py`; create `tests/test_hashing.py`

**Acceptance Criteria:**
- [ ] `fit_hash` covers data selection, signal spec, objective, engine, registry version, seeds, metamer version — and **excludes** the criterion set and the candidate set
- [ ] Adding a criterion changes `compat_hash` but leaves `fit_hash` unchanged
- [ ] Changing the memory budget or thread count changes only `run_hash`
- [ ] Compat relevance is an **allowlist**: a newly added field defaults to provenance-only
- [ ] A golden test enumerates the compat-relevant field set, so changing it requires updating the test
- [ ] Hashing is insensitive to dict ordering and float formatting

**Verify:** `pixi run test tests/test_hashing.py -v`

**Steps:**

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_hashing.py
from metamer.core.hashing import (
    COMPAT_RELEVANT_FIELDS,
    FIT_RELEVANT_FIELDS,
    canonical_json,
    compat_hash,
    fit_hash,
    run_hash,
)


def _config(**overrides):
    base = {
        "data_uri": "s3://bucket/ssh.zarr",
        "variable": "sla",
        "signal_terms": ["constant", "trend", "annual"],
        "objective": "ml",
        "engine": "kalman",
        "registry_version": "1",
        "metamer_version": "0.1.0",
        "seed": 0,
        "criteria": ["aic"],
        "candidates": ["white+matern12"],
        "memory_budget_gb": 4.0,
        "threads": 4,
        "output": "out.zarr",
    }
    base.update(overrides)
    return base


def test_adding_a_criterion_changes_compat_but_not_fit():
    """A criterion change must not discard warm starts or force a refit.

    Bug this catches: a single hash boundary, under which adding HQIC to a
    finished 10^7-point run demands a full refit to compute arithmetic on
    numbers already sitting in the store.
    """
    base = _config()
    more = _config(criteria=["aic", "hqic"])
    assert fit_hash(base) == fit_hash(more)
    assert compat_hash(base) != compat_hash(more)


def test_runtime_knobs_change_only_run_hash():
    """Memory budget and thread count are provenance, never a gate.

    Bug this catches: gating resumption on runtime knobs, which would block
    starting on the 64-core box and resuming on the mini PC -- a real workflow
    the determinism guarantee exists to permit.
    """
    base = _config()
    other = _config(memory_budget_gb=1.0, threads=64)
    assert fit_hash(base) == fit_hash(other)
    assert compat_hash(base) == compat_hash(other)
    assert run_hash(base) != run_hash(other)


def test_objective_is_fit_relevant():
    """theta_hat_REML != theta_hat_ML, so the objective must gate fit reuse.

    Bug this catches: reusing a warm start across objectives, which produces
    converged-looking fits at the wrong optimum -- the worst failure mode in
    the system.
    """
    assert fit_hash(_config()) != fit_hash(_config(objective="reml"))


def test_compat_relevance_is_an_allowlist_golden_set():
    """The compat-relevant field set is pinned by a golden test.

    Expected value determined independently by reading design doc section
    13.3 and listing the fields by hand. With a denylist, every newly added
    field would silently become compat-relevant and the failure mode is
    'resume broke and nobody knows why'.
    """
    assert FIT_RELEVANT_FIELDS == frozenset(
        {
            "data_uri", "variable", "signal_terms", "objective", "engine",
            "registry_version", "metamer_version", "seed",
        }
    )
    assert COMPAT_RELEVANT_FIELDS == FIT_RELEVANT_FIELDS | {"criteria"}


def test_hash_is_insensitive_to_key_order_and_float_formatting():
    """Reordering keys or writing 4.0 as 4 does not change the hash.

    Bug this catches: hashing file text, under which adding a comment would
    invalidate a completed 10^7-point store.
    """
    a = canonical_json({"b": 1, "a": 4.0})
    b = canonical_json({"a": 4.0, "b": 1})
    assert a == b


def test_an_unknown_field_is_provenance_only():
    """A new field defaults to run_hash only.

    Bug this catches: the denylist failure mode, where adding any field
    silently invalidates every in-progress store.
    """
    base = _config()
    extended = _config(new_experimental_knob=True)
    assert fit_hash(base) == fit_hash(extended)
    assert compat_hash(base) == compat_hash(extended)
    assert run_hash(base) != run_hash(extended)
```

- [ ] **Step 2: Implement hashing.py**

```python
# src/metamer/core/hashing.py
"""Three hashes, with compat relevance declared by allowlist.

    fit_hash    everything determining theta_hat and log_lik
    compat_hash fit_hash + the criterion set (which determines /selection/)
    run_hash    everything, plus runtime knobs and the machine fingerprint

The split exists so that a criterion-only change recomputes the derived arrays
from the stored primitives rather than refitting, and so that warm starts
survive a criterion change.

Compat relevance is an ALLOWLIST. With a denylist, every newly added field
silently becomes compat-relevant and the failure mode is "resume broke and
nobody knows why".
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

FIT_RELEVANT_FIELDS = frozenset(
    {
        "data_uri",
        "variable",
        "signal_terms",
        "objective",
        "engine",
        "registry_version",
        "metamer_version",
        "seed",
    }
)
"""Fields determining theta_hat and log_lik. Extending this is a deliberate act."""

COMPAT_RELEVANT_FIELDS = FIT_RELEVANT_FIELDS | {"criteria"}
"""Fields determining the stored derived arrays."""


def canonical_json(payload: Mapping[str, Any]) -> str:
    """Render a mapping to canonical JSON: sorted keys, compact separators."""
    return json.dumps(dict(payload), sort_keys=True, separators=(",", ":"), default=repr)


def _digest(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()[:16]


def _subset(config: Mapping[str, Any], fields: frozenset[str]) -> dict[str, Any]:
    return {key: config[key] for key in sorted(fields) if key in config}


def fit_hash(config: Mapping[str, Any]) -> str:
    """Hash the fields determining theta_hat and log_lik.

    Excludes the criterion set (AIC versus BIC changes nothing about where the
    optimizer lands) and the candidate set (candidate-set extension is a
    legitimate incremental operation).
    """
    return _digest(_subset(config, FIT_RELEVANT_FIELDS))


def compat_hash(config: Mapping[str, Any]) -> str:
    """Hash the fields determining the stored derived arrays."""
    return _digest(_subset(config, COMPAT_RELEVANT_FIELDS))


def run_hash(config: Mapping[str, Any], machine: Mapping[str, Any] | None = None) -> str:
    """Hash everything, including runtime knobs and the machine fingerprint.

    Provenance only. Never a gate.
    """
    payload = dict(config)
    if machine is not None:
        payload["_machine"] = dict(machine)
    return _digest(payload)


def machine_fingerprint(cpu_model: str, cores: int, total_ram_bytes: int) -> str:
    """Instance-type-based fingerprint for the calibration cache.

    Hostname is meaningless on ephemeral nodes. Thread count is deliberately
    excluded so a fresh spot instance of the same type reuses its calibration.
    """
    return _digest({"cpu": cpu_model, "cores": int(cores), "ram": int(total_ram_bytes)})
```

- [ ] **Step 3: Run tests and commit**

Run: `pixi run test tests/test_hashing.py -v` → all PASS

```bash
git add src/metamer/core/hashing.py tests/test_hashing.py
git commit -m "feat: add three-hash machinery with a compat-relevance allowlist"
```

---

## Task 17: Memory formula, RSS shim, benchmark references, and the stage-1 spike harness

**Goal:** An analytic bytes-per-series formula validated against measured peak RSS, the two cross-machine normalization instruments, a compiled path-B backend, and the harness that runs the stage-1 comparison.

**Files:**
- Create: `src/metamer/core/machine.py`, `src/metamer/core/memory.py`
- Create: `src/metamer/bench/references.py`, `src/metamer/bench/spike.py`
- Create: `src/metamer/core/engines/compiled.py` (numba path B)
- Create: `tests/test_memory.py`, `tests/test_compiled.py`
- Modify: `pixi.toml` (add `numba`; add `celerite2` under `[target.linux-64.dependencies]`)

**Acceptance Criteria:**
- [ ] `bytes_per_series` reproduces the design-doc worked example: **8490 B** for path A and **7434 B** for path B at `d=3, k_β=4, p=4, N=630, M=12`, shared X
- [ ] Per-point regressors add exactly `N·k_β·8 = 20 160 B` to both
- [ ] `peak_rss_bytes()` returns a finite value on Linux and macOS; the Windows branch exists though untested
- [ ] Measured peak RSS matches the formula within 25% at `B ∈ {10³, 10⁴}`
- [ ] The compiled path-B engine agrees with `KalmanEngine` to 1e-10 on identical input
- [ ] `bench.references.canonical_filter_pass()` times one likelihood evaluation at N=630, d=3, single-threaded, fixed θ
- [ ] The compute reference is a compiled `P = F P Fᵀ + Q` loop at d=3 plus a rank-1 downdate — **not** a 6×6 LU
- [ ] The bandwidth reference is measured at **1 thread and full thread count**, reporting bandwidth-per-core at full occupancy
- [ ] `bench.spike` runs the gap sweep `{0%, 10% scattered, 40% contiguous}` and reports the A:B ratio **per gap case**

**Verify:** `pixi run test tests/test_memory.py tests/test_compiled.py -v` and `pixi run python -m metamer.bench.spike --threads 1 --threads 4`

**Steps:**

- [ ] **Step 1: Add dependencies**

Add `numba = "*"` to `[dependencies]` and `celerite2 = "*"` to `[target.linux-64.dependencies]`
(celerite2 has no `osx-arm64` conda-forge build; it is optional and test-only).

Run: `pixi install`

- [ ] **Step 2: Write the failing memory tests**

```python
# tests/test_memory.py
import numpy as np
import pytest

from metamer.core.machine import peak_rss_bytes
from metamer.core.memory import Backend, bytes_per_series, tile_side


def test_path_a_matches_the_design_doc_worked_example():
    """Path A is 8490 B/series at the documented configuration.

    Expected value determined independently by summing the design doc's
    section 9.4 table by hand: 5670 data + 1764 output + 432 d^2 + 120 x +
    120 accumulators + 256 trust-region + 128 Hessian.
    """
    got = bytes_per_series(Backend.NUMPY_BATCHED, d=3, k_beta=4, p=4, n_time=630, n_models=12)
    assert got == 8490


def test_path_b_drops_only_the_per_series_solver_state():
    """Path B is 7434 B/series: data plus output slots only.

    Bug this catches: claiming path B's memory advantage is transformative.
    It is 12.4%, because data and output already account for 87%.
    """
    got = bytes_per_series(Backend.COMPILED, d=3, k_beta=4, p=4, n_time=630, n_models=12)
    assert got == 7434
    assert (8490 - 7434) / 8490 == pytest.approx(0.124, abs=0.001)


def test_per_point_regressors_add_the_design_matrix_per_series():
    """A per-point X adds N*k_beta*8 bytes to both backends.

    Expected value determined independently: 630 * 4 * 8 = 20160 by hand.
    """
    shared = bytes_per_series(Backend.NUMPY_BATCHED, 3, 4, 4, 630, 12, per_point_design=False)
    per_point = bytes_per_series(Backend.NUMPY_BATCHED, 3, 4, 4, 630, 12, per_point_design=True)
    assert per_point - shared == 20160


def test_tile_side_shrinks_under_the_full_accounting():
    """The prompt's data-only formula overestimates tile_side.

    Expected value determined independently: sqrt(1e9 / 8490) = 343 with
    shared X and sqrt(1e9 / 28650) = 187 with per-point X, against the naive
    sqrt(1e9 / (630*8)) = 445.
    """
    assert tile_side(10**9, 8490) == 343
    assert tile_side(10**9, 28650) == 187


def test_peak_rss_is_finite_on_this_platform():
    """The RSS shim returns a usable number.

    Bug this catches: ru_maxrss unit confusion -- KB on Linux, bytes on macOS
    -- which would make the memory-formula validation wrong by 1024x on one
    platform while looking fine on the other.
    """
    value = peak_rss_bytes()
    assert np.isfinite(value)
    assert value > 10 * 1024 * 1024


@pytest.mark.parametrize("batch", [1000, 10000])
def test_measured_peak_rss_matches_the_formula(batch):
    """Measured peak RSS tracks the analytic formula within 25%.

    A large mismatch is a Phase 1 bug and must be found before zarr exists,
    so that Phase 2's calibration tile validates against something rather than
    being a black box.
    """
    from metamer.core.memory import measure_peak_rss_for_batch

    predicted = bytes_per_series(Backend.NUMPY_BATCHED, 3, 4, 4, 630, 2) * batch
    measured = measure_peak_rss_for_batch(batch=batch, n_time=630)
    assert 0.75 * predicted <= measured <= 1.25 * predicted
```

- [ ] **Step 3: Implement machine.py and memory.py**

```python
# src/metamer/core/machine.py
"""Peak-RSS measurement, with a branch per platform.

Linux reports ru_maxrss in kilobytes and macOS in bytes -- a 1024x difference
that would look fine on one platform and be badly wrong on the other. Windows
has no `resource` module at all; that branch is written but untested, and is
part of the "portable, unclaimed" position on Windows support.
"""

from __future__ import annotations

import sys


def peak_rss_bytes() -> float:
    """Return this process's peak resident set size, in bytes.

    Returns:
        Peak RSS in bytes.
    """
    if sys.platform == "win32":  # pragma: no cover - written, untested
        import psutil

        return float(psutil.Process().memory_info().peak_wset)

    import resource

    raw = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return raw if sys.platform == "darwin" else raw * 1024.0
```

```python
# src/metamer/core/memory.py
"""Analytic bytes-per-series, one formula per backend.

    Path A:  B * ( N*9 + X_term + out(M, p, k_beta) + c_A(d, k_beta, p) )
    Path B:  B * ( N*9 + X_term + out(M, p, k_beta) )  +  T * c_B(d, k_beta, p)

The shapes genuinely differ: path A's solver state is per series, path B's is
per thread. N*9 is the data tile: 8 bytes float64 y plus 1 byte mask.
"""

from __future__ import annotations

from enum import StrEnum

import numpy as np


class Backend(StrEnum):
    """Which execution strategy the formula describes."""

    NUMPY_BATCHED = "numpy_batched"
    COMPILED = "compiled"


def _output_slots(n_models: int, p: int, k_beta: int) -> int:
    """theta, theta_err, beta, beta_err, loglik, k as float64; iterations + status."""
    return n_models * (2 * p + 2 * k_beta + 2) * 8 + n_models * 3


def _solver_state(backend: Backend, d: int, k_beta: int, p: int) -> int:
    """Per-series (path A) or per-thread (path B) solver working set."""
    d2 = 6 * d * d * 8                      # P, F, Q, P_inf and two workspace copies
    x_aug = d * (1 + k_beta) * 8            # augmented state over [y | X]
    accum = (k_beta * (k_beta + 1) // 2 + k_beta + 1) * 8
    hessian = p * p * 8
    if backend is Backend.COMPILED:
        optimizer = 22 * p * 8              # L-BFGS history, m ~= 10
    else:
        optimizer = (p * p + 4 * p) * 8     # dense quasi-Newton trust-region model
    return d2 + x_aug + accum + optimizer + hessian


def bytes_per_series(
    backend: Backend,
    d: int,
    k_beta: int,
    p: int,
    n_time: int,
    n_models: int,
    per_point_design: bool = False,
) -> int:
    """Analytic per-series memory cost.

    Args:
        backend: Which execution strategy.
        d: Composite state dimension.
        k_beta: Number of design columns.
        p: Number of free noise parameters.
        n_time: Series length.
        n_models: Candidate count held until the tile is written.
        per_point_design: True if any regressor is a per-point field, which
            makes X per-series rather than one shared copy.

    Returns:
        Bytes per series.
    """
    data = n_time * 9
    x_term = n_time * k_beta * 8 if per_point_design else 0
    total = data + x_term + _output_slots(n_models, p, k_beta)
    if backend is Backend.NUMPY_BATCHED:
        total += _solver_state(backend, d, k_beta, p)
    return int(total)


def thread_state_bytes(d: int, k_beta: int, p: int) -> int:
    """Per-thread solver state for the compiled backend."""
    return int(_solver_state(Backend.COMPILED, d, k_beta, p))


def tile_side(budget_bytes: int, per_series_bytes: int) -> int:
    """Square spatial tile side from a byte budget and the full accounting."""
    return int(np.floor(np.sqrt(budget_bytes / per_series_bytes)))


def measure_peak_rss_for_batch(batch: int, n_time: int) -> float:
    """Fit a synthetic batch and return the peak RSS increase, in bytes."""
    import gc

    import numpy as np

    from metamer.core.capability import Objective
    from metamer.core.criteria import Criterion
    from metamer.core.fit import fit
    from metamer.core.machine import peak_rss_bytes
    from metamer.core.signal import Annual, Constant, SemiAnnual, SignalSpec, Trend
    from metamer.core.terms import ProcessSpec
    from metamer.core.registry import kernel_registry

    def _term(kind: str):
        from metamer.core.terms import TermSpec

        family = kernel_registry[kind]()
        return TermSpec(kind, family.param_specs(), getattr(family, "ordering_param", None))

    gc.collect()
    before = peak_rss_bytes()
    rng = np.random.default_rng(0)
    y = rng.standard_normal((batch, n_time))
    t = np.arange(float(n_time))
    fit(
        y,
        t,
        SignalSpec([Constant(), Trend(), Annual(period=52.0), SemiAnnual(period=26.0)]),
        [ProcessSpec((_term("white"), _term("matern12"), _term("matern32")))],
        criterion=Criterion.AIC,
        objective=Objective.ML,
        max_iter=5,
    )
    gc.collect()
    return peak_rss_bytes() - before
```

- [ ] **Step 4: Implement the compiled path-B engine and its agreement test**

`src/metamer/core/engines/compiled.py` implements the same scalar-observation filter
in a `numba.njit(parallel=True)` kernel with `prange` over series, exposing the same
`Engine` protocol. `tests/test_compiled.py` asserts agreement with `KalmanEngine` to
1e-10 on `white + matern12 + matern32` at `B=64, N=630`, on all three gap cases, with a
docstring naming the bug it catches: **a compiled kernel that diverges from the numpy
reference is the one failure the two-implementation design exists to detect.**

Set `fastmath=False` and pin `NUMBA_NUM_THREADS` in the harness — `fastmath` reassociates
and would void the bitwise-reproducibility precondition.

- [ ] **Step 5: Implement the benchmark references**

`src/metamer/bench/references.py` provides three functions:

1. `canonical_filter_pass()` — times **one likelihood evaluation** at N=630, d=3, no gaps,
   single-threaded, fixed θ, no optimizer. **Zero proxy risk, because it is the workload.**
   This is the normalizer for the budget question.
2. `compute_reference()` — a compiled fixed-iteration loop of `P = F @ P @ F.T + Q` at
   **d=3** plus a rank-1 downdate, single-threaded. **Not a 6×6 LU:** the filter contains
   no matrix factorization (the scalar observation makes `S` a scalar), and the spike runs
   at d=1 and d=3, not d=6.
3. `bandwidth_reference(threads)` — a STREAM-triad over an array sized past L3, run at
   **1 thread and at full thread count**, reporting bandwidth-per-core at full occupancy.
   Single-threaded STREAM measures one core's outstanding-miss capacity, not the memory
   subsystem.

- [ ] **Step 6: Implement the stage-1 spike harness**

`src/metamer/bench/spike.py` exposes `python -m metamer.bench.spike`:

- Families: `matern12` (d=1) and `white + matern12 + matern32` (d=3)
- N=630; `k_β=4`; `B ∈ {10³, 10⁴}`; objective ML
- Gap sweep `{0%, 10% scattered, 40% contiguous blocks}`
- **Path A's optimistic bound** = `canonical_filter_pass_cost × mean_iterations`, assuming
  a zero-overhead batched optimizer at 100% utilization — a performance A can never exceed
- **Path B measured fully**, warm JIT, compile time reported separately
- Equivalence: `|Δℓ|` below tolerance; `max|Δθ|/σ_θ < 0.01` **only where the Hessian
  condition number is below threshold**; both paths select the same candidate
- Emits JSON: per (family, gap case, B, thread count) the A:B ratio, ms/fit raw **and in
  canonical-filter-pass units**, peak RSS, mean iterations, compile time, and the roofline
  pair for this machine

- [ ] **Step 7: Run everything on the mini PC and commit**

```bash
pixi run test tests/test_memory.py tests/test_compiled.py -v
pixi run python -m metamer.bench.spike --threads 1 --threads 4 --out bench/minipc.json
git add src/metamer/core/machine.py src/metamer/core/memory.py src/metamer/bench src/metamer/core/engines/compiled.py tests/test_memory.py tests/test_compiled.py bench/minipc.json pixi.toml pixi.lock
git commit -m "feat: add memory formula, RSS shim, benchmark references, and spike harness"
```

---

## Task 18: Cross-machine stage-1 measurement and the ≥3× decision

**USER-ORDERED GATE — NON-SKIPPABLE.** This task was requested by the user in the current conversation. It MUST NOT be closed by walking around it, by declaring it "verified inline", or by substituting a cheaper check. Close only after every item in `acceptanceCriteria` has been re-validated independently, with output captured.

**Goal:** Run the Task 17 harness on all three machines, evaluate the ≥3×-at-d=3 rule on the 64-core box, and record the decision that determines whether Task 19 is built at all.

**This session cannot close this task alone.** The mini PC is the only machine reachable from here; the 64-core box and the MacBook runs must be executed by the user. The budget comparison is **valid only on the 64-core box**.

**Files:**
- Create: `bench/minipc.json`, `bench/box64.json`, `bench/macbook.json`
- Create: `docs/superpowers/notes/2026-XX-XX-spike-stage1-verdict.md`

**Acceptance Criteria:**
- [ ] `bench/minipc.json` exists, from `{1, 4}` threads — establishes feasibility and correctness
- [ ] `bench/box64.json` exists, from `{1, 4, full}` threads — **the only valid budget comparison**; the 4-thread point bridges to the mini PC
- [ ] `bench/macbook.json` exists, from `{1, full}` threads — the adversarial case; unified memory gives high bandwidth per core, so **if path A wins anywhere it wins here**
- [ ] The roofline pair (compute reference, bandwidth reference at 1 and full threads) is recorded for all three machines, and the fitted model's **prediction error is stated**
- [ ] ms/fit is reported raw **and in canonical-filter-pass units**
- [ ] The A:B ratio is reported **per gap case**, not pooled
- [ ] The verdict note states, explicitly, one of: **adopt B** (B ≥3× at d=3 on the 64-core box), **inconclusive → build Task 19**, or **A stays default** with the measured number recorded
- [ ] Measured ms/fit on the 64-core box is compared against the **19 ms** budget

**Verify:** `pixi run python -m metamer.bench.spike --report bench/minipc.json bench/box64.json bench/macbook.json` → prints the three-machine table, the roofline fit and its prediction error, and the verdict line

**Steps:**

- [ ] **Step 1: Run the harness on the mini PC (this session can do this)**

```bash
pixi run python -m metamer.bench.spike --threads 1 --threads 4 --out bench/minipc.json
```

- [ ] **Step 2: Ask the user to run the 64-core box and the MacBook**

Give the user these commands, one per line so terminal wrapping cannot corrupt a paste.
First establish the 64-core box's RAM, then run `--explain` before the measurement.

```bash
free -g
```

```bash
pixi run python -m metamer.bench.spike \
  --threads 1 --threads 4 --threads 0 \
  --out bench/box64.json
```

```bash
pixi run python -m metamer.bench.spike \
  --threads 1 --threads 0 \
  --out bench/macbook.json
```

(`--threads 0` means "all available".)

- [ ] **Step 3: Collect the three JSON files and fit the roofline**

```bash
pixi run python -m metamer.bench.spike --report bench/minipc.json bench/box64.json bench/macbook.json
```

Expected: a table of ms/fit per (machine, family, gap case, thread count), the same numbers
in canonical-filter-pass units, the A:B ratio per gap case, the fitted roofline with its
prediction error, and a verdict line.

- [ ] **Step 4: Write the verdict note**

Record: the decision, the measured ratios, the budget comparison on the 64-core box, the
bandwidth-per-core ordering across machines (the design doc predicts the mini PC has
*higher* bandwidth per core than the 64-core box at full load, which would mean the mini PC
flatters path A — confirm or refute), and the roofline prediction error.

- [ ] **Step 5: Commit**

```bash
git add bench docs/superpowers/notes
git commit -m "test: record stage-1 spike results and the execution-strategy verdict"
```

---

## Task 19: **CONDITIONAL** — batched trust-region optimizer

**Build this only if Task 18's verdict is "inconclusive".** If path B wins by ≥3× at d=3 on the 64-core box, **this task is deleted, not deferred**: path A's permanent form is the plain per-series scipy loop from Task 13, which is already a complete and tested correctness reference.

**Goal:** A batched trust-region optimizer with per-series radii, an active mask, and periodic compaction, so path A can be measured at its real performance rather than its optimistic bound.

**Files:**
- Create: `src/metamer/core/optimize_batched.py`
- Create: `tests/test_optimize_batched.py`

**Acceptance Criteria:**
- [ ] Trust-region, **not** line-search L-BFGS: per-iteration work is fixed (one function and gradient per active series, then a masked accept/reject and a masked radius update). A data-dependent inner loop is the pathology that destroys batch utilization.
- [ ] Per-series results are **identical** to the Task 13 reference to 1e-8 on the same inputs
- [ ] The active mask freezes converged series; utilization is reported
- [ ] Compaction repacks the active set and does **not** change results
- [ ] Trust-radius collapse produces `Outcome.TRUST_RADIUS_COLLAPSED`
- [ ] No reordering or rescaling of the parameter vector occurs mid-run without an explicit curvature-history reset

**Verify:** `pixi run test tests/test_optimize_batched.py -v` and a rerun of the stage-2 spike

**Steps:**

- [ ] **Step 1: Confirm this task is still required**

Read `docs/superpowers/notes/*-spike-stage1-verdict.md`. If the verdict is "adopt B",
**stop and close this task as not-required**, recording the verdict's ratio in the closing
note. Do not build the optimizer.

- [ ] **Step 2: Write the equivalence test first**

The single most important test is that the batched path reproduces the reference exactly:

```python
def test_batched_trust_region_matches_the_reference_optimizer():
    """The batched path and the scipy reference reach the same optimum.

    Bug this catches: a masked update that leaks across series, or a radius
    update applied to frozen series. Both produce plausible fits that differ
    from the reference in ways no single-series test would reveal.
    """
```

- [ ] **Step 3: Implement, then rerun the stage-2 comparison and record it**

```bash
pixi run test tests/test_optimize_batched.py -v
pixi run python -m metamer.bench.spike --stage 2 --out bench/box64-stage2.json
git add src/metamer/core/optimize_batched.py tests/test_optimize_batched.py bench
git commit -m "feat: add batched trust-region optimizer and stage-2 spike results"
```

---

## Phase 1 exit criteria checklist

Mapped from design doc §18. Tick these before declaring Phase 1 complete.

- [ ] 1. Brute-force MVN agreement at small N, every family **and a sum** — Task 6
- [ ] 2. `celerite2` agreement (optional, Tier-1) — **first cut if Phase 1 is too large**
- [ ] 3. Masked-gap likelihood identical to genuinely-absent — Task 6
- [ ] 4. Analytic `F`/`Q`/`P∞` vs `expm`/Lyapunov, per family — Tasks 4, 5
- [ ] 5. Parameter counting vs hand counts, **both objectives** — Task 9
- [ ] 6. Rank-deficient `X` gives the documented failure, not NaN — Tasks 7, 8
- [ ] 7. REML penalty vs brute-force `log|XᵀΣ⁻¹X|` — Task 8
- [ ] 8. Complex-step viability verdict **recorded with numbers** — Task 11
- [ ] 9. FD step rule validated at N ∈ {100, 630, 5000} — Task 11
- [ ] 10. Gradient-capability resolution on a mixed composite — Task 12
- [ ] 11. Hessian vs brute-force FD Hessian — Task 13
- [ ] 12. **Every** failure-taxonomy branch reachable by a constructed test — Tasks 3, 13
- [ ] 13. Measured peak RSS matches the analytic formula at two values of B — Task 17
- [ ] 14. Stage-1 comparison at B ≈ 10⁴, N ≈ 630, split by machine — Task 18
- [ ] 15. Gap-structure sweep, A:B ratio **per gap case** — Tasks 17, 18
- [ ] 16. `fit_hash`/`compat_hash` separation exercised end to end — Task 16

Criterion 16's full end-to-end form (a resume that adds a criterion without refitting)
needs the zarr store and therefore lands in Phase 2; Task 16 proves the hash boundary that
makes it possible.

---

## Deferred to Phase 2 and beyond

Nothing in this plan builds tiling, zarr, the CLI, warm-starting, the hysteresis audit, the
calibration tile, Whittle, exact Toeplitz, CARMA, SHO, sum-of-OU power law, TIC, the
sandwich estimator, model averaging, Student-t, or MCMC. Those are Phases 2–6 in design doc
§17 and get their own plans.
