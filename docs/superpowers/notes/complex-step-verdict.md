# Complex-step viability verdict

**Date:** 2026-08-06 · **Task:** Phase 1 Task 11 · **Exit criterion:** §18.8

## Verdict

**Complex-step differentiation is not viable through `ConcentratedObjective`.**
Richardson (Romberg) extrapolated central differences in unconstrained
coordinates is adopted as the gradient oracle instead — the fallback design doc
§8.2 named for exactly this outcome.

The failure is total rather than marginal. Design doc §8.2 framed the decision as
"agreement to ~1e-12 means viable; ~1e-7 means something non-analytic is in the
path". Neither describes what happens: complex-step returns a gradient of
**exactly zero**, a relative disagreement of **1.000e+00**.

## Measurement

`matern32`, one series, `N = 64`, `t = arange(64.0)`, `y` from
`default_rng(7).standard_normal`, evaluated at `u0 = [0.0, log 5.0]` in
unconstrained coordinates, complex step `1e-20`. Reference gradient from a
six-level Romberg tableau started at `h0 = 1e-2` (self-consistency of the
deepest two extrapolations: 7.85e-13).

| quantity | value |
|---|---|
| reference gradient | `[ 4006.82376884, -5844.55596968 ]` |
| complex-step gradient | `[ 0.0, 0.0 ]` |
| relative agreement | **1.000e+00** |
| raised | `ComplexWarning`, not an exception |

## Where analyticity is lost

Not to any of the operations §8.2 anticipated. There is no `abs`, no `min`/`max`,
no comparison-based branch and no conjugating norm in the path. It is an explicit
dtype cast, and it happens **before the filter is reached**:

| stage | output dtype | max &#124;imag&#124; | warning |
|---|---|---|---|
| `ConcentratedObjective.to_natural` | `float64` | 0.0 | `ComplexWarning` |
| `ConcentratedObjective.hydrate` | `float64` | 0.0 | `ComplexWarning` |
| `KalmanEngine.score` | `float64` | 0.0 | `ComplexWarning` |

The first one is decisive. `ConcentratedObjective._map` (`objective.py:1010`)
opens with

```python
arr = np.asarray(values, dtype=np.float64)
```

so the imaginary perturbation is discarded by `to_natural`, the very first thing
the unconstrained vector meets. Two further layers repeat it independently:
every bijector in `transforms.py` casts on entry (`transforms.py:41–118`), and
`KalmanEngine.score` casts `theta`, `y` and `t` and allocates its state,
covariance and accumulator buffers as `dtype=np.float64`
(`engines/kalman.py:142–160`).

**This is a more tractable diagnosis than a non-analytic operation would have
been** — a cast is removable, a `max()` is not — but it is a three-layer change,
not a one-line one, and it would put a complex dtype through the whole hot path.
Phase 1 does not need it: the fallback oracle is strong enough for the job the
oracle exists to do.

## Why the fallback is sufficient

The oracle's job is to catch an incorrect hand-derived `dQ/dθ` in Task 12's
analytic forward-mode. A wrong derivative produces O(1) relative error, not
O(1e-7), so an oracle good to 1e-13 is far more than the task requires.

Measured on an analytically differentiable function
(`sin(3u₀) + u₁³ + 0.5·u₀u₁`, chosen because its third derivative is non-zero
and a quadratic's is not), relative error against the paper gradient:

| method | relative error |
|---|---|
| `richardson_gradient`, `h0 = 1e-2`, 4 levels | **5.80e-14** |
| `richardson_gradient`, `h0 = 6.06e-6`, 4 levels | 5.08e-11 |
| plain central difference at `h = 6.06e-6` | 4.43e-11 |

The middle row is the warning worth recording: **starting the extrapolation at
the finite-difference optimum makes it worse than the difference it was supposed
to improve.** Richardson extrapolates the truncation series, so it has to start
where truncation dominates. `RICHARDSON_H0 = 1e-2` is set from this measurement.

Four levels is enough. Against a six-level tableau on the real filter:
7.4e-13 (N = 100), 1.1e-12 (N = 630), 6.7e-12 (N = 5000).

## Consequence for the step rule

The same sweep settled a second question. Central-difference error is
`h²|ℓ'''|/6 + ε|ℓ|/h`, so the optimum is `h ~ (ε|ℓ|/|ℓ'''|)^(1/3)` — design doc
§8.2 writes the same structure as `(ε·|ℓ|/|ℓ''|)^(1/3)`. Sweeping `h` over ten
decades on the real filter against the Romberg reference:

| `h` | N = 100 | N = 630 | N = 5000 |
|---|---|---|---|
| 1e-08 | 8.22e-09 | 2.65e-08 | 2.11e-07 |
| 1e-07 | 1.74e-09 | 2.65e-09 | 1.35e-08 |
| **1e-06** | **1.45e-10** | 4.45e-10 | 4.06e-10 |
| **1e-05** | 1.56e-10 | **1.47e-10** | **2.67e-10** |
| 1e-04 | 1.50e-08 | 1.50e-08 | 1.50e-08 |
| 1e-03 | 1.50e-06 | 1.50e-06 | 1.50e-06 |

Two things follow.

1. **The optimum barely moves with N** — `1e-6` to `1e-5` across `|ℓ|` from
   3.2e3 to 2.2e5. `ε^(1/3) = 6.055e-06` sits inside it at every N.
2. **The truncation branch is N-independent to three digits** (1.501e-08,
   1.498e-08, 1.497e-08 at `h = 1e-4`), which is direct evidence that
   `|ℓ'''|/|ℓ'|` does not vary with N — both the likelihood and its derivatives
   scale with N, so the ratio in the step rule is O(1).

So the curvature denominator is load-bearing. Using `(ε|ℓ|)^(1/3)` instead —
which is what the plan's Task 11 fence proposed — puts the step at 8.90e-05
(N = 100), 1.74e-04 (N = 630) and 3.64e-04 (N = 5000), all deep in the
truncation-dominated region:

| rule | N = 100 | N = 630 | N = 5000 |
|---|---|---|---|
| `(ε·\|ℓ\|)^(1/3)` | 1.19e-08 | 4.51e-08 | 1.98e-07 |
| `(ε·\|ℓ\|/\|ℓ''\|)^(1/3)` | 4.28e-11 | 1.00e-10 | 1.76e-10 |

280× to 1100× worse, and at N = 5000 the dropped denominator misses Task 11's
own "1e-7 relative" acceptance criterion.

## What would change the verdict

`tests/test_gradients.py::test_complex_step_is_not_viable_through_the_filter`
asserts the gradient is **exactly** zero rather than merely far from the oracle.
That is deliberate: if the cast chain is ever made dtype-following, complex-step
starts working and that test fails, which forces this note to be rewritten
rather than quietly going stale.
