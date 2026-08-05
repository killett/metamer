# metamer — design document

**Status:** approved in outline through brainstorming rounds Q1–Q8; awaiting spec review.
**Date:** 2026-08-04
**Licence:** Apache-2.0
**Minimum Python:** 3.12

---

## 0. How to read this document

Section 1 states the mission. Section 2 records **corrections to the original build
prompt** — the prompt contains factual errors and two significant omissions, and this
document supersedes it where they conflict. Sections 3–15 specify the system. Section 16
covers testing, 17 the phasing, 18 the consolidated Phase 1 exit criteria, and 19 the
deferred items and remaining open questions.

Everything outside Phase 1 is specified at **interface level only**: the seams are fixed,
the internals are deferred.

---

## 1. Mission

`metamer` fits stochastic noise models to time series and selects among them using
configurable information criteria, after (or jointly with) a user-specified deterministic
signal model. It must work on a single series and on collections up to 10^7, as produced
by a global gridded geophysical dataset.

The scientific payoff is a **correctly calibrated uncertainty on fitted signal
parameters, especially linear trends**. Every other feature serves that.

The direct ancestor is Hughes & Williams (2010), *The color of sea level*, J. Geophys.
Res. 115, C10048, doi:10.1029/2010JC006102. `metamer` exists to fix four defects in that
methodology: two-stage estimation, AR(p) as the wrong parameterization, hard per-point
selection, and interpolation-based gap handling.

### 1.1 Downstream consumer

`metamer` will be consumed by `synesthesia`. Dependency direction is one-way. `metamer`
must know nothing about NetCDF loaders, CIE colour matching, cartopy, or GMT. Two
concrete integration requirements:

- Every term in synesthesia's `--fit-terms {constant, trend, accel, annual, semiannual}`
  must be expressible in the signal specification.
- A multitaper (Thomson) spectral estimator must be public API.

---

## 2. Corrections to the build prompt

These are recorded so the erroneous version does not survive in the project record.

### 2.1 The `expm` amortization claim was wrong

The prompt states that transition matrices are "computed once per (model, parameter
vector, timestep) and broadcast across the whole batch." **This is false during
optimization.** `A` depends on the model parameters, and every series searches its own
parameter vector, so `expm(A·Δt)` is inherently per-series. There is no sharing across
the batch.

The real amortization is over **unique Δt**, not over series:

| sampling | consequence |
|---|---|
| regular | exactly one unique Δt; one transition + one process-noise covariance per series per optimizer iteration, reused across all N timesteps. An N-fold saving, and the dominant win. |
| irregular, shared axis | the unique-Δt set is identical for every series, so the memo table is a uniform array of shape `(B, n_unique_dt, d, d)`. |
| ragged | each series has its own unique-Δt set; the table cannot be a uniform array and vectorization is lost. The performance cliff stands, but for this reason rather than the prompt's. |

**Consequence that connects to the parameterization decision (§4.1):** for CARMA, `A` is a
companion matrix whose eigenvalues *are* the AR roots. Since roots are already the
parameterization chosen to make stationarity automatic, the eigendecomposition comes for
free and the transition matrix is analytic. The root parameterization does double duty;
this is a design rationale, not a coincidence.

**Policy:** prefer analytic transition and process-noise construction per family (§7.1). A
general `expm`/Lyapunov path exists as a fallback and should almost never run. Frequent
fallback firing is a signal that something is wrong.

### 2.2 "Single-series only in Phase 1" is retracted

`(B, N)` is the **only** code path. `B=1` is a shape, never a separate implementation. Two
implementations of the likelihood diverge, and a single-series Phase 1 is the standard
route to discovering in Phase 3 that the design assumes a Python loop over pixels.

Phase 1 ships no batch *orchestration* (no tiling, no zarr, no CLI) while the array API is
batched throughout.

### 2.3 REML was omitted

The prompt does not mention restricted maximum likelihood. It should have. See §6. The
prompt's own argument that `n_eff ≪ n` (used to justify an effective-sample-size BIC
variant) is precisely the argument that makes the ML degrees-of-freedom bias
non-negligible; dismissing REML on `(n−k)/n` grounds while asserting `n_eff ≪ n` is
incoherent.

### 2.4 The warm-starting hysteresis hazard was omitted

Warm-starting from a converged spatial neighbour biases every point toward its neighbour's
answer, producing spatially smooth maps by an illegitimate mechanism that is visually
indistinguishable from the legitimate one (IC weights and model averaging). See §11.2.
This is the most seductive failure mode in the system and requires a mandatory audit.

### 2.5 Chunk-size arithmetic

An earlier estimate in discussion put a `theta[tile, tile, P_total]` chunk at 150–600 MB.
The correct figure at `tile_side ≈ 445` (from `sqrt(1 GB / (630 × 8))`), `P_total ≈ 40`,
float32 is **≈ 32 MB**; at `tile_side = 200` it is 6.4 MB. Still above a few-MB read
target, so shard/chunk decoupling (§12.6) is retained, but chunking the parameter axis is
not required. The computed table is in §12.6.

---

## 3. Package structure

One repository, three layers, gated by optional dependency extras.

| layer | extra | contents | constraint |
|---|---|---|---|
| `metamer.core` | — | numpy/scipy only. Arrays in, results out. | Must be importable without the others. No file I/O, no xarray, no dask. |
| `metamer.batch` | `[batch]` | xarray/dask orchestration, zarr output, checkpointing, resumability | |
| `metamer.cli` | `[cli]` | config-file-driven runner | |

Additional optional extras: `[compiled]` (numba), `[mcmc]` (emcee), `[test]` (celerite2 and
benchmark dependencies).

---

## 4. Core abstractions

The API is a **kernel algebra as substrate, with a registry as a thin naming layer over
it**, and a **structured canonical config form** with string sugar for humans.

```python
@dataclass(frozen=True)
class ParamSpec:
    name: str
    default: float
    transform: Bijector                    # to/from unconstrained R, with log|J|
    bounds: tuple[float, float] | None     # mathematical bounds, enforced by transform
    diagnostic_limits: tuple[float, float] # reporting limits, NOT clipped
    fixed: bool = False
    unit: str | None = None

@dataclass(frozen=True)
class TermSpec:
    kind: str                              # kernel registry key
    params: Mapping[str, ParamSpec]
    def engine_costs(self) -> Mapping[EngineId, CostClass]: ...
    def gradient_modes(self) -> Mapping[Objective, GradientMode]: ...
    def n_free(self) -> int: ...
    def canonical(self) -> dict: ...

@dataclass(frozen=True)
class ProcessSpec:
    terms: tuple[TermSpec, ...]            # canonically ordered, stably labelled
    def __add__(self, other) -> ProcessSpec: ...
    def engine_costs(self) -> Mapping[EngineId, CostClass]:   # intersection over terms
    def gradient_modes(self) -> Mapping[Objective, GradientMode]:  # intersection
    def n_free(self, objective: Objective) -> int: ...
    def canonical(self) -> dict: ...
    def spec_hash(self) -> str: ...
```

Candidate sets for selection are `Sequence[ProcessSpec]`. The future signal × noise
product space is `Sequence[tuple[SignalSpec, ProcessSpec]]` — a type change, not a
redesign.

### 4.1 Separate the process from its parameterization

**This is the single highest-leverage decision in the API.** A kernel term must not
conflate the mathematical process with the coordinates the optimizer searches in.

Each parameter carries a **bijection to unconstrained ℝ**:

| parameter class | transform |
|---|---|
| scales, variances, timescales | `log` |
| bounded (ν, Q) | `logit` or `softplus` |
| CARMA autoregressive roots | root-based factorization: stable real roots and conjugate quadratic pairs, parameterized so stationarity is automatic rather than constrained |

The transform **must expose `log|Jacobian|`**. It is required for MCMC if ever enabled,
and required *now* for correct reporting: an uncertainty estimated in log-space and
reported in natural units needs a delta-method push-through. Getting this wrong produces
plausible, wrong error bars — the exact failure class this package exists to eliminate.

**The push-through is first-order.** Reported parameter covariance in natural units is

```
Σ_natural = J Σ_unconstrained Jᵀ ,      J = dg/du      (g = the inverse transform)
```

which is the delta method to first order. **It degrades for parameters pushed near a
diagnostic limit**, where the transform's curvature is not negligible and the linearization
stops being a good approximation. This is a caveat on the package's headline numbers and
must be visible: a `DIAGNOSTIC_LIMIT` outcome (§8.6) therefore also implies the reported
uncertainty for that parameter is unreliable, not merely that the parameter is extreme.

`diagnostic_limits` are distinct from `bounds`. The bijector guarantees a scale stays
positive; it does not stop `log ρ` marching to 50, which is the near-degenerate direction
the identifiability lint (§4.8) targets. **Hitting a diagnostic limit is a reported
outcome in the failure taxonomy (§8.6), never a silent clip.**

### 4.2 Engine capability, resolved by intersection, with cost classes

A spec does **not** name an engine. It declares which engines *can* evaluate it, and
composition takes the intersection. The declaration is a **cost class, not a boolean**:

```
{kalman: O(N), whittle: O(N log N), toeplitz: O(N³)}
```

So `white + exact_powerlaw + sho` resolves to toeplitz-only at O(N³), and the batch layer
can refuse it at 10^7 scale on cost grounds rather than discovering it at runtime.

**Empty intersection is a hard error at spec-construction time**, with a message naming
which term eliminated which engine.

### 4.3 Gradient capability, same machinery

Gradient availability resolves by intersection across terms, structurally identical to
engine capability, and **reuses the same machinery** rather than being a separate boolean.
If three families ship analytic gradients and one does not, the composite has none.

Gradient availability is **per (family, objective)**: a family may ship analytic ML
gradients before REML ones, because the REML penalty term is not covered by the envelope
theorem (§8.1). The capability is therefore a small matrix.

**The resolved gradient mode is a reported field on the result** and on `--explain`
output. A composite silently falling back to finite differences is a ~1.7× cost
difference at p=6 and must not be invisible.

### 4.4 Registries: extensible, versioned, and split

Two **separate** registries:

- **Kernel registry** — maps short names (`"white"`, `"ou"`, `"matern32"`) to `TermSpec`
  constructors. Decorator-based registration plus an entry-point group so a third party
  can add a family without forking.
- **Recipe registry** — experiment configurations such as `"hw2010_ar5"`, which bundle a
  noise model *with* a signal model, an engine, and a criterion. These are not kernels.
  Keeping them separate stops the kernel registry becoming a junk drawer and keeps the
  return type of a registry lookup predictable.

A **registry version** is stamped into provenance so `"matern32"` cannot silently change
meaning between runs and invalidate a cached 10^7-point result.

Third-party families registered via the entry-point group must pass the public
**conformance-test helper** (§16.1) — that is what makes the extensibility claim real
rather than nominal.

### 4.5 Canonical ordering and stable term labels

Two Matérn terms in one composite are exchangeable; the likelihood is invariant to
swapping them. That is label-switching, and it makes warm-starting, caching, and
cross-run comparison incoherent.

Define a canonical sort (by kind, then by a designated ordering parameter such as
timescale) and assign stable labels so "term 2" means the same thing across grid points
and runs.

**Canonicalization happens at spec construction and at result reporting, never
mid-optimization.** Re-sorting terms between optimizer iterations permutes the parameter
vector under L-BFGS's stored curvature history and corrupts it.

The general rule, of which ordering is one instance:

> **No reparameterization, reordering, or preconditioner refresh may change the coordinate
> system mid-run without an explicit curvature-history reset.**

This binds any future adaptive reparameterization or diagonal preconditioner as well.

### 4.6 Canonical serialization and stable hashing

Specs serialize to a canonical form with a stable hash, insensitive to dict ordering and
float formatting. That hash keys:

- provenance in zarr attributes
- the `expm`/Lyapunov memo cache
- warm-start reuse (§11.1)

Implementation: `json.dumps(model.model_dump(mode="json"), sort_keys=True,
separators=(",", ":"))`, hashed with SHA-256. Python's `repr` shortest-roundtrip float
formatting makes this deterministic.

### 4.7 Parameter counting is a first-class, tested property

`n_free` must account for frozen parameters, parameters shared across terms, and —
critically — the linear signal parameters profiled out via GLS.

The counting rule is **stated per objective as a definition, not as an adjustment**,
because ML and REML are different model classes rather than the same model with different
bookkeeping. Under REML the objective is the likelihood of a set of error contrasts, a
different random quantity from `y`; `β` is **not a parameter of the REML model at all**.

| objective | k | n |
|---|---|---|
| ML | `k_θ + k_β` (including profiled-out β) | `n_obs` |
| REML | `k_θ` | `n_obs − rank(X)` |

Profiled-out parameters were still estimated from the data and still count toward `k`
under ML. **This is the most common silent bug in concentrated-likelihood
implementations**, and it corrupts every selection decision downstream without any
visible symptom.

Tests are written against **hand-counted expected values**, not against the
implementation, for both objectives.

### 4.8 Static identifiability lint

Compositional freedom lets users specify structurally non-identifiable models:

- `white + Matérn ν=1/2` with `ρ → 0` is `white + white`
- two free-ν Matérns can collapse onto each other
- SHO with `Q → 0.5` degenerates

Ship a lint pass over the spec flagging known-degenerate patterns at construction time,
plus a runtime diagnostic flagging near-degeneracy in the fitted solution via the Hessian
condition number (§8.5). **Warn, do not block — but say it out loud.**

---

## 5. Signal model

### 5.1 Terms and the linear/nonlinear taxonomy

| term | linear in parameters? |
|---|---|
| Polynomial: constant, trend, acceleration, arbitrary order | yes |
| Harmonics: annual, semiannual, arbitrary specified periods | yes (deterministic amplitude) |
| Offsets / jumps at user-supplied epochs | yes |
| Piecewise-linear rate changes at user-supplied epochs | yes |
| External regressors (scalar index, or per-point field) | yes |
| Exponential and logarithmic decays | **no** — nonlinear in the timescale |

**The taxonomy and the dispatch exist from day one**, with nonlinear terms raising
`NotImplementedError` in Phase 1. Retrofitting the linear/nonlinear split later means
rewriting the fit driver.

External regressors have two distinct plumbing cases: a scalar index broadcast identically
to all series, and a per-point field that must be chunked and spatially aligned alongside
the data.

### 5.2 GLS profiling and rank deficiency

Linear terms are **profiled out analytically via GLS at each noise-parameter evaluation**,
so the optimizer searches only the noise parameters (typically 2–6 dimensions). The
concentrated-likelihood fast path and the general joint-optimization path are dispatched
automatically, **and the choice is logged** so users know when they have left the fast
lane.

**`rank(X)`, not `ncol(X)`.** `log|XᵀΣ⁻¹X|` is only defined for full-column-rank `X`, and
rank deficiency is not exotic here: an offset epoch at a series boundary, a piecewise
breakpoint with no samples on one side, a regressor constant over the window, or a
harmonic at a period the sampling cannot resolve. Any of these appear at some grid points
and not others in a 10^7 run.

Compute `rank(X)` numerically (pivoted QR or SVD with a stated tolerance), use it in both
the REML penalty and the `n − rank(X)` bookkeeping, and **surface rank deficiency
explicitly in the failure taxonomy** rather than letting it emerge as a NaN.

**Effective rank is per series, not per batch.** The design matrix may be shared, but the
filter accumulates `XᵀΣ⁻¹X` only over each series' *unmasked* epochs — so the design that
actually enters the solve is X restricted to those rows. A globally full-rank X still
yields a singular system for any series whose gaps remove all support for one of its
columns: an offset or piecewise rate change whose epoch falls inside a seasonal sea-ice
dropout is the ordinary case, not a contrived one. A batch-level rank check is therefore
necessary but not sufficient, and the per-series classification happens in the GLS solve. This also
matters under ML, where rank-deficient `X` silently inflates `k`.

### 5.3 The offset/random-walk confound

An undetected offset is nearly indistinguishable from random-walk noise — a well-known
trap in GNSS trend estimation. **Breakpoint epochs are user-supplied in v1. Breakpoint
detection is explicitly out of scope and must not be silently approximated.** This is
documented prominently, and the misspecification benchmark (§16.2) measures which noise
model wins in the presence of an undetected offset.

---

## 6. Objectives: ML and REML

Maximum likelihood estimates of covariance parameters are biased when regression
parameters are estimated from the same data — the fit absorbs variance and the noise
estimate comes back too small. This is Hughes & Williams defect #1 in a second guise.
Joint estimation fixes the *two-stage* version of the bias; joint ML does **not** fix the
*degrees-of-freedom* version. REML does:

```
ℓ_R(θ) = ℓ_c(θ) − ½ log|XᵀΣ(θ)⁻¹X|
```

**Why it bites here.** The usual dismissal is that the correction scales as `(n−k)/n`,
negligible at n=630. That assumes independent observations. The relevant quantity is
`(n_eff − k)/n_eff`, and this design already concedes `n_eff ≪ n`. For a series dominated
by low-frequency power, `n_eff` can be single or low double digits, and losing four
degrees of freedom to constant + trend + annual + semiannual is then a large fraction. The
bias direction is the damaging one: understated low-frequency power, understated trend
uncertainty.

**Cost is near zero.** The augmented/collapsed Kalman filter that profiles out `β`
already accumulates the whitened normal equations. Carry the Cholesky (or QR `R`-factor)
of `XᵀΣ⁻¹X`; the REML term is `2·Σ log diag(R)`. No `k×k` determinant call, no explicit
inverse, and the same factor yields the `β` covariance. One extra reduction over a `k×k`
triangular matrix.

### 6.1 Decision

**Both objectives are supported. ML is the default.**

- ML default keeps the Hector/CATS/`est_noise` external cross-validation (§16.3)
  apples-to-apples, and keeps the signal × noise seam open.
- REML is a documented option **on the linear path only** — it has no exact profiling for
  nonlinear signal terms.
- **Within a fixed `X`, REML ICs are a legitimate and arguably preferable basis for
  comparing noise models — which is exactly the v1 task.** The restriction binds only when
  `X` varies. Documentation frames it as "valid for the v1 task, forbidden for the v2 joint
  search," not as a niche option.
- **The v2 joint signal × noise search must force `objective=ML`.** The guard raises if a
  user configures REML with a varying-`X` candidate set. This check is written **now**,
  even though the candidate set cannot vary yet — three lines, and it documents the
  constraint in executable form.

### 6.2 Comparability guard

Every score is tagged with **both** the engine that produced it and the objective it
came from. The comparison/selection layer **refuses** to rank scores across engines or
across objectives. Both are hard errors, not warnings: a Whittle score is not an exact
likelihood, and an ML and a REML likelihood live on different measures. The numbers look
commensurable and are not. This is a silent-failure mode that produces plausible-looking
but wrong maps.

Warm-start cache keys include the objective, since `θ̂_REML ≠ θ̂_ML` and a neighbour fitted
under one objective is a poor start under the other.

---

## 7. Likelihood engines

| engine | role | cost |
|---|---|---|
| **Batched Kalman (exact state-space)** | the workhorse; Phase 1's only implementation | O(N) |
| `celerite2` | single-series reference for sums of exponential and SHO kernels; MIT licence | O(N) |
| Debiased Whittle (Sykulski et al. 2019) | cheap screening pass | O(N log N) |
| Exact Toeplitz | exact power-law path, opt-in, single-series scale | O(N³) |

### 7.1 Analytic transition and process-noise construction

Two structural facts make the filter simple:

- **The observation is scalar.** Each series is univariate at each epoch, so the innovation
  variance `S = HPHᵀ + R` is a scalar. No matrix inverse, no Cholesky, no pivoting
  anywhere in the filter.
- **`P∞` is analytic per family**, so there is no Lyapunov solve either.

The filter is therefore **analytic in θ end to end**, which is what makes exact-gradient
options available (§8.2).

Per-family closed forms:

| family | d | transition |
|---|---|---|
| Matérn ν=1/2 (OU) | 1 | scalar, `exp(−Δt/ρ)` |
| Matérn ν=3/2 | 2 | Jordan-block closed form (repeated real root) |
| Matérn ν=5/2 | 3 | Jordan-block closed form (repeated real root) |
| SHO | 2 | closed form |
| General CARMA(p,q) | p | from AR roots |

### 7.2 The defective-root guard

`expm(A·Δt)` from an eigendecomposition requires `A` diagonalizable. A companion matrix
with repeated roots is **defective**, and the true solution carries `t·exp(−λt)` terms
the eigen-route cannot produce.

- **Matérn 3/2 and 5/2 are exactly this case** — repeated real root at `−λ` with
  multiplicity 2 and 3. Their closed forms are Jordan-block forms, **not**
  eigendecompositions. They are separate analytic constructions and are *not* instances of
  the general CARMA root path. Recorded here so nobody later "simplifies" them into it.
- **General CARMA has no repeated roots almost surely, but the optimizer will walk near
  them.** As two roots approach, the eigenvector matrix becomes ill-conditioned and
  `V·diag(exp(λΔt))·V⁻¹` loses precision *continuously* — no exception, just a quietly
  wrong likelihood. The optimizer is *attracted* to these regions, because near-degenerate
  roots are where composite models collapse onto simpler ones — the same geography the
  identifiability lint (§4.8) targets.

**Guard:** monitor the eigenvector-matrix condition number; fall back to scaling-and-
squaring `expm` below a threshold; **surface the fallback rate as a diagnostic.** Frequent
firing means the model is non-identifiable there and the lint should say so.

### 7.3 Gaps

**Never interpolate to fill gaps.** Mask the Kalman update and keep the prediction step. A
gridded product with sea-ice dropouts stays on the fast path.

Required invariant, tested: a series with masked points gives the **same likelihood** as
the same series with those points genuinely absent.

### 7.4 The engine protocol

Phase 1 ships only the exact state-space backend, but Whittle, exact-Toeplitz and
celerite2 must slot in without reshaping the core. The abstraction is **the protocol**,
not merely the engine tag. §4.2's capability-and-cost machinery forces most of this; the
protocol completes it.

### 7.5 Power-law: two paths, both required

- **Default: sum-of-OU (Markovian) approximation.** Component count and frequency band are
  documented, user-facing parameters. Keeps power-law models inside the same likelihood
  engine so information criteria stay comparable. **Required validation:** the
  approximation reproduces the target spectrum to a stated tolerance across the stated
  band.
- **Also required: an exact power-law path** (exact Toeplitz likelihood), opt-in,
  single-series scale. This exists so results can be cross-validated against published
  geodesy results from Hector, CATS, and `est_noise`. Without it, any discrepancy against
  those packages is unattributable — approximation error and implementation bug look
  identical.

---

## 8. Gradients and optimization

### 8.1 The envelope theorem

For the concentrated ML objective `ℓ_c(θ) = ℓ(θ, β̂(θ))`, since `β̂` is an **exact**
stationary point, `∂ℓ/∂β = 0` there and

```
dℓ_c/dθ = ∂ℓ/∂θ |_{β=β̂}      (exactly)
```

No `dβ̂/dθ` is required.

**Under REML this does not cover the penalty term**, which needs
`d/dθ log|XᵀΣ⁻¹X|`. So REML's analytic gradient is strictly more work than ML's.
Forward-mode obtains it automatically; hand-derivation does not. This is why gradient
capability is per (family, **objective**) in §4.3.

### 8.2 Gradient strategy

Costs in filter-pass equivalents, at p = 2–6 noise parameters:

| approach | cost | exact? | per-family work |
|---|---|---|---|
| **Central finite differences** | `2p` | no (~4×10⁻⁸ abs. for ℓ ~ 10³) | none |
| **Analytic forward-mode** (differentiated Kalman filter) | `1+p` | yes | `dF/dθ`, `dQ/dθ`, `dP∞/dθ` |
| **Complex-step** | `p` complex ≈ `3–4p` real | yes | none, *if viable* |
| Reverse-mode (JAX) | ~3 | yes | — **rejected**: tape memory `N·d²` per series, hard dependency fighting the numba backend, would relitigate §9 |

**Decision: FD as the Phase 1 default, analytic forward-mode as the target with a protocol
slot, complex-step as the test oracle.**

- FD ships in Phase 1 because it costs zero per-family work and unblocks everything.
- The kernel protocol carries the gradient hook from day one (non-retrofittable).
- Analytic forward-mode lands per-family once the §9 spike shows where time goes; at p=6
  it is a ~1.7× cut on the dominant cost.
- **Complex-step's role is verification, not production.** It is an exact gradient
  requiring no derivation, so it is the oracle that catches an incorrect hand-derived
  `dQ/dθ`. FD alone cannot play that role — agreeing to 10⁻⁸ with a wrong analytic
  gradient is entirely possible.

**Complex-step viability must be verified before it is relied on.** Complex-step requires
the whole evaluation path to be complex-analytic. These are not, and at least some will
appear: `abs()`, `max()`/`min()`, comparison-based branches, norms computed with numpy's
conjugating default, sorting, clipping guards. Each **silently returns a wrong derivative
rather than raising.**

Verification: run complex-step against central FD on Matérn 5/2. Agreement to ~10⁻¹²
means viable; ~10⁻⁷ means something non-analytic is in the path. **Fallback oracle if it
proves awkward:** Richardson-extrapolated central FD in unconstrained coordinates, which
reaches ~10⁻¹⁰–10⁻¹¹ — weaker, but sufficient, since a wrong `dQ/dθ` produces O(1)
relative error, not O(10⁻⁷).

**FD step rule.** Steps are taken in the **unconstrained Bijector coordinates**, where
log/logit transforms have made every coordinate O(1)-scaled; that licenses a single
relative step size across families and is a second dividend from §4.1. But accuracy also
depends on `|ℓ|`, which scales with N — at N=630 the cancellation error is `ε·|ℓ|/h`, not
`ε/h`. The rule accounts for both, in the spirit of `h ≈ (ε·|ℓ|/|ℓ''|)^(1/3)`, and is
**validated against the oracle at three widely separated N (100, 630, 5000)** rather than
hardcoded as cube-root-of-eps. This is the class of thing that works at Phase 1 scale and
silently degrades at production scale.

### 8.3 Optimizer

- **Path A (batched) uses a batched trust-region, not batched line-search L-BFGS.** A line
  search has a *data-dependent* number of inner function evaluations, which is exactly the
  pathology that destroys batch utilization — the batch runs at the pace of whichever
  series is having the worst line search. A trust-region method does **fixed work per
  iteration**: one function + gradient per active series, then a masked accept/reject and a
  masked radius update. Fixed per-iteration work is what makes a batched optimizer
  tractable. Dogleg or Steihaug on a quasi-Newton (BFGS/SR1) model. *This is the same
  argument as the active-mask tax in §9.2 — one argument, not two.*
- **Path B (compiled) uses ordinary per-thread L-BFGS with backtracking Armijo**,
  implemented in numba. This is unavoidable work if path B wins: keeping the optimizer in
  Python and compiling only the likelihood reintroduces the forbidden shape, and the
  arithmetic says so — 1–5 ms of scipy overhead × ~50 iterations is 50–250 ms against a
  19 ms budget.
- **Convergence is judged in unconstrained coordinates** — relative gradient norm plus
  relative function change, with an iteration cap producing an explicit non-convergence
  outcome.

### 8.4 Initialization, with a defined failure ladder

**Deterministic and moment-based**, not random multi-start: estimate starting θ from the
empirical autocovariance or periodogram. Cheap, reproducible, no seed dependence, and it
is the precursor of the Whittle screening pass. Random multi-start is a straight
multiplier on a budget with little headroom.

Moment initialization can fail — a non-monotone empirical autocovariance, a positive
periodogram slope estimate, a near-zero-variance series. The ladder:

```
moment estimate  →  clipped to diagnostic limits  →  family default from ParamSpec
```

**The ladder rung reached is reported.** A seeded random-restart escape hatch is available
but off by default, for debugging a suspicious grid point.

The result records **which initialization source was used** (moment / warm start /
default), because it affects reproducibility semantics and is needed when diagnosing
traversal-order dependence.

### 8.5 Hessian at the optimum

A converged quasi-Newton approximation is **too crude** for the uses below. Budget an
explicit Hessian at the optimum:

- FD-on-analytic-gradient where analytic gradients exist (`p` extra gradient evaluations)
- FD-on-FD otherwise (`~2p²` passes; at p=6 that is 72 passes, acceptable because it
  happens once per fit rather than per iteration — roughly +12% on a 50-iteration fit)

Consumers: **TIC** (the `J` in `tr(J⁻¹K)`), the **sandwich estimator**, **near-degeneracy
detection** via condition number (§4.8), and **reported parameter uncertainties**.

Stated explicitly because otherwise someone reuses the BFGS matrix and the sandwich
variance is quietly wrong.

### 8.6 Failure taxonomy

Non-convergence is **not one outcome**. Encoded as an enum written to the output, never a
boolean `converged` flag. Retrofitting a taxonomy onto a boolean means revisiting every
early-return in the fit driver, so this is Phase 1.

| outcome | meaning |
|---|---|
| `OK` | converged |
| `ITER_CAP_SMALL_GRAD` | iteration cap hit, gradient small — probably fine, flagged |
| `ITER_CAP_LARGE_GRAD` | iteration cap hit, gradient large — real failure |
| `DIAGNOSTIC_LIMIT` | a parameter reached its diagnostic limit |
| `TRUST_RADIUS_COLLAPSED` | trust region collapsed |
| `NONFINITE_OBJECTIVE` | non-finite objective encountered |
| `RANK_DEFICIENT_X` | design matrix exactly singular **for this series** (§5.2) |
| `ILL_CONDITIONED_X` | design matrix technically full rank for this series but barely identified |
| `DEGENERATE_HESSIAN` | near-degenerate Hessian at the optimum |
| `NOT_ATTEMPTED` | candidate skipped — screened out, capability-excluded, or cost-refused |
| `CANDIDATE_DROPPED` | candidate abandoned run-wide by the early-abort demotion path (§14.1) |
| `INSUFFICIENT_DATA` | too few valid samples — land, permanent ice. **A legitimate expected outcome, excluded from every failure-rate denominator.** |

`INSUFFICIENT_DATA` fixes the denominator problem: without it, an ocean-only run on a
global grid reports ~70% "failure" and the number becomes noise everyone learns to ignore.

At 10^7 series nobody inspects individuals — **the map of which failure occurred where is
itself the diagnostic.**

---

## 9. Execution strategy and the Phase 1 spike

### 9.1 The two shapes

**Path A — vectorized batch (pure numpy).** Batched Kalman over `(B, N)`, batched
trust-region where every series carries its own parameter vector, with an active mask
freezing converged series. Zero build complexity, runs anywhere, natural reference
implementation. Cost: the batched optimizer is real, subtle work, and the working set is
`B × (d² + d + workspace)`.

**Path B — compiled per-series.** Filter *and* optimizer compiled, `prange` over series.
Sidesteps the batched-optimizer problem entirely — each thread runs an ordinary scalar
L-BFGS. Per-thread working set is ~`d²` floats with d ≤ 6, so it fits in L1 and the 16 GB
constraint stops binding on solver state. Ragged time axes become identical to the fast
path. Costs cross-series SIMD.

**Expectation:** at d ≤ 6 the per-series matrices are 6×6 or smaller; batched numpy on
`(B,6,6)` is memory-bound because the arithmetic intensity of a 6×6 solve is dismal,
whereas a compiled per-series loop keeps state in registers across all N. Path B is
expected to win, possibly by a large factor. **An unmeasured factor is not an
architecture**, and the cost of being wrong is asymmetric: committing to B and losing
leaves Phase 1 with a compiled toolchain it does not need and no numpy reference to check
it against.

**Decision: ship A as the Phase 1 correctness reference, spike B, measure, decide.**

### 9.2 The staged spike

**The spike is staged, and the staging is what keeps Phase 1 tractable.**

Most of Phase 1's bulk sits in one place: path A's batched trust-region optimizer, with
active masks and compaction. That machinery exists *only* for path A's performance. **If
path B wins, it is dead weight — a correctness reference does not need to be fast.** So the
spike is sequenced to answer the question before that machinery is built.

#### Stage 1 — optimistic bound (days, not weeks)

Build the batched Kalman filter in numpy, which is needed for the reference regardless, and
measure its per-pass cost. Then compute **path A's optimistic bound**:

```
t_A_bound  =  (filter pass cost)  ×  (mean iteration count)
```

assuming a **zero-overhead batched optimizer at 100% utilization** — a performance path A
can never exceed. Build the compiled path B for Matérn ν=1/2 and the d=3 case, and measure
it fully.

| stage 1 outcome | action |
|---|---|
| **B beats A's optimistic bound by ≥3× at d=3** | A can never win. **Adopt B. Never build the batched trust-region.** Path A's permanent form becomes a plain per-series scipy loop — slow, obviously correct, ideal as the reference implementation and as the MVN-oracle harness. This is the large saving. |
| **B does not beat the optimistic bound** | The comparison is genuinely close. Proceed to stage 2 and build the real path A, now knowing it is worth the effort. |

The optimistic bound is sound **because it is one-sided**: it can only overstate A. "B wins
even against A's best conceivable case" is a safe conclusion; the converse requires the real
measurement, which stage 2 provides.

#### Stage 2 — only if stage 1 is inconclusive

Full batched trust-region, real measurement, the ≥3×-at-d=3 decision rule applied to
measured rather than bounded path-A performance.

**Why utilization matters at stage 2.** Path A's efficiency depends entirely on how much
work is wasted on converged series still riding in the batch. With realistic heterogeneity
some series converge in 20 iterations and some in 200, so the batch runs at the tail's pace
unless the active set is compacted. A low utilization number means A's effective throughput
is far below its nominal FLOP rate, and periodic compaction is mandatory work not yet
costed. Path B has no equivalent tax — a thread finishes and takes the next series. The
optimistic bound assumes 100% utilization precisely so stage 1 does not have to model this.

#### Measurement specification (both stages)

| aspect | specification |
|---|---|
| **families** | Matérn ν=1/2 (d=1) **and** a d=3 case (Matérn ν=5/2 or white+SHO). Two points show the scaling in d, which is the actual question — the curves may cross. Spiking only ν=1/2 measures scalar recursions with no matrix ops and flatters A for the wrong reason. |
| **N** | 630 |
| **gap sweep** | **{0%, 10% scattered, 40% contiguous blocks}** — see below. Report the A:B ratio **per gap case**, not pooled. |
| **B** | 10³ and 10⁴ |
| **signal** | `k_β = 4` (constant, trend, annual, semiannual), shared X |
| **objective** | ML (the default) |
| **what is run** | **full fit to convergence**, including the trust-region / line-search loop — not a filter-only benchmark. A filter-only comparison measures the part where A is least disadvantaged and skips the part that costs weeks. (Stage 1 substitutes the optimistic bound for A's loop, not for B's.) |
| **primary metric** | **ms per series-model fit** — the quantity the budget is denominated in |
| **also reported** | mean iteration count; active-mask utilization (stage 2, path A); peak RSS; wall time |
| **JIT** | benchmark with warm JIT; **report compile time separately** (real, but amortized to nothing at 10⁷ series) |
| **threading** | `OMP_NUM_THREADS` and any BLAS threading **pinned explicitly** in the harness, or the thread-count sweep measures nothing |

**Gap structure matters more than gap fraction, and it decides the question.** High-latitude
gridded altimetry loses points to seasonal ice for a large fraction of the year; 30–50%
missing at a high-latitude point is ordinary, not extreme. And seasonal ice produces **long
contiguous blocks**, not scattered dropouts. The two paths respond asymmetrically:

- Under **path A** the mask is a multiply — **full cost regardless of gap fraction**.
- Under **path B** a compiled loop can branch past the update entirely — **a real saving
  proportional to gap fraction**.

So high gap fraction *favours* B, and measuring only at 10% scattered understates B's
advantage exactly where the data is gappiest.

#### Equivalence check

`max|Δθ|/σ_θ < 0.01` alone is right for well-conditioned cases and meaningless for the rest:
in a flat or near-degenerate direction θ is genuinely not identified, so demanding parameter
agreement there tests the optimizer's stopping rule rather than correctness — and it will
produce spurious failures exactly where the two paths use different optimizers, which is by
construction.

Use the **same three comparisons as the hysteresis audit (§11.2)**, one implementation
serving both:

| comparison | rule |
|---|---|
| **objective** | `|Δℓ|` below a stated tolerance — this is the real "same optimum" test |
| **parameters** | `max|Δθ|/σ_θ < 0.01`, applied **only** when the Hessian condition number is below a stated threshold |
| **selection** | both paths choose the same candidate |

All three are reported.

#### Machine plan

| machine | threads | role |
|---|---|---|
| Ubuntu mini PC, **4 slow cores, 16 GB RAM (~10 GB free)** | {1, 4} | **primary development.** Correctness, the oracles, and the memory-formula validation. **Not** where the budget question is answered. |
| **Linux box, 64 cores** | {1, 4, full} | **the decisive measurement.** Run once or twice, not continuously. The 4-thread point is the *bridge*: it isolates machine from thread count against the mini PC's 4-thread number. RAM unknown — establish it first, and run `--explain` before the run regardless. (At 8490 B/series and `tile_side` 343 a tile is ~1 GB, so it is almost certainly fine.) |
| Apple Silicon MacBook, 32 GB | {1, full} | **the adversarial case.** Unified memory gives unusually high bandwidth per core, so **if path A wins anywhere, it wins here.** A machine where the expected answer might flip is worth more than a third confirmation. Also the numba-on-arm64 and celerite2-on-arm64 smoke test that §15 needs anyway. |
| SkyPilot via a forthcoming `cloudify` skill | — | future; see §15.5 |

The ≥3×-at-d=3 decision rule (§9.2 stage 1) is evaluated on the **64-core box**, with the
mini PC and MacBook as the bracketing cases. The single-machine fallback rule from an
earlier draft is void — all three machines are available.

**Expected bandwidth ordering, to be measured rather than assumed:** bandwidth-per-core on
the 4-core mini PC is probably *higher* than on the 64-core box at full load, because 64
cores contend for a memory system that is not 16× wider. If so, the mini PC flatters path A
relative to the production machine, which strengthens the conservative-for-A direction of
the whole exercise — but only if measured.

#### Cross-machine normalization: two instruments, two questions

These are different questions needing different instruments, and conflating them leaves
both half-answered.

**(i) "Does the 64-core box clear the 19 ms budget?" — normalizer: the canonical filter
pass.**

A fixed micro-benchmark of **one likelihood evaluation at a canonical configuration**:
N=630, d=3, no gaps, single-threaded, no optimizer, fixed θ. **Zero proxy risk, because it
*is* the workload**, and it is being built anyway. Report ms per series-model fit both raw
and **in units of canonical filter passes**. Cross-machine comparison of the raw number
becomes meaningful immediately.

**(ii) "Which path wins on machine X, including machines not yet measured?" — instrument:
the compute/bandwidth pair, fitted as a roofline.**

A pair of numbers cannot normalize a scalar ms/fit — you cannot divide by a 2-tuple. What
the pair supports is a two-parameter model:

```
predicted_ms  ≈  compute_work / compute_rate  +  memory_traffic / bandwidth
```

where the machine supplies the two rates and the spike supplies the two workloads. That is
a real model with real fitting error.

| reference | definition | why not the obvious choice |
|---|---|---|
| **compute** | fixed-iteration compiled loop of `P = F @ P @ F.T + Q` at **d=3**, plus a rank-1 downdate, single-threaded | **A dense 6×6 LU is the wrong proxy.** Per §7.1 the filter contains *no* matrix factorization — the scalar observation makes `S` a scalar, so there is no inverse, no Cholesky, no pivoting. An LU's pivoting branches and data-dependent control flow measure something the filter never does. It is also the wrong *size*: the spike runs at d=1 and d=3, where loop overhead and instruction latency dominate, not d=6. |
| **bandwidth** | STREAM-triad-like over an array sized past L3, measured **at 1 thread and at full thread count**, reporting derived bandwidth-per-core at full occupancy | **Single-threaded STREAM does not measure a machine's memory bandwidth** — it measures what *one core* can pull, which on a server is limited by that core's outstanding-miss capacity rather than the memory subsystem. A 64-core server shows modest single-thread and very high aggregate bandwidth; a 4-core mini PC shows the opposite ratio. Path A's cost at full occupancy is governed by **aggregate bandwidth ÷ active cores.** |

The compute reference nearly collapses into the canonical filter pass, and that is fine.
They stay separate because **the canonical pass includes the N-loop and gap handling and the
compute reference must not** — the latter is a machine characteristic, the former is a
workload measurement.

**The roofline model must be validated before it is trusted.** Measure the pair *and* the
real spike on all three machines, fit the model, and **report the prediction error.** An
unvalidated extrapolation model is worse than no model, because it will be believed.

**The spike's real deliverable is the protocol, not the kernel.** Even a losing spike must
prove a second backend slots in behind the §7.4 protocol without reshaping the core. That
cannot be verified by argument, and it is why the spike belongs in Phase 1 regardless of
outcome — and why the stage-1 "never build the trust-region" branch still requires both
paths to sit behind the protocol. If wiring the compiled path requires touching the fit
driver, the protocol is wrong.

### 9.3 The budget

Overnight (10 h) on 64 cores against 10⁷ series × 12 candidate models:

```
10 × 3600 × 64 / (10⁷ × 12) ≈ 19 ms per series-model fit
```

A compiled Kalman at N=630, d=3 is plausibly 30–100 µs per pass, so ~50 optimizer
iterations is 1.5–5 ms — inside budget with room. But Python-level scipy overhead is
1–5 ms per call, multi-start multiplies everything, and the 16 GB laptop has ~8 cores. The
margin is close enough that this must be measured, not argued.

### 9.4 Memory formula — a Phase 1 deliverable

Produce an **analytic bytes-per-series formula per family and per backend**, plus a test
asserting measured peak RSS matches it within tolerance at two or three values of B. The
calibration tile (§11.4) then validates against something instead of being a black box. A
large mismatch is a Phase 1 bug, to be found before zarr exists.

**One formula per backend, not one formula** — the shapes genuinely differ:

```
Path A:  bytes ≈ B × ( N×9 + X_term + out(M, p, k_β) + c_A(d, k_β, p) )
Path B:  bytes ≈ B × ( N×9 + X_term + out(M, p, k_β) )  +  T × c_B(d, k_β, p)

  N×9      = data tile: 8 bytes float64 y + 1 byte mask
  X_term   = 0                if all regressors are shared (one copy, negligible)
           = N × k_β × 8      if ANY regressor is a per-point field
  out(...) = M × (2p + 2k_β + 2) × 8 + M × 3      output slots, held until tile write
             (θ̂, θ̂_err, β, β_err, log_lik, k as float64;
              iterations uint16 + status uint8 = 3 B.
              n_eff is per point, not per candidate.)
  T        = thread count
```

**`X_term` is not a rounding error.** With a shared time axis and no per-point regressors,
the design matrix is one shared copy. But the prompt requires per-point regressor fields
(e.g. a GIA model), and then `X` is per-series: at N=630, k_β=4 that is **20.2 kB/series**,
roughly 2.4× the entire rest of the per-series cost. It changes `tile_side` by a factor of
~2 and is the difference between a configuration fitting in 16 GB and not.
**`--explain` (§13.4) reports which regressor regime the config lands in.**

**Directive on dtype conversion (not an open measurement).** Data arrives float32 from disk
and `core` is float64 (§15.4). **Convert per dask chunk during tile assembly**, so the full
float32 and full float64 representations never coexist. Peak then carries one float64 tile
plus one float32 chunk, and the ~44% swing on the dominant term disappears.

Per-series solver state, path A, with the collapsed/augmented GLS filter:

| item | bytes |
|---|---|
| `P` (data-independent, shared across the `1+k_β` filtered signals but **not** across series, since θ differs) | `d² × 8` |
| `x`, augmented over `y` and each column of `X` | `d × (1+k_β) × 8` |
| `F`, `Q`, `P∞` (per series — θ differs) | `3 d² × 8` |
| normal-equation accumulators `XᵀΣ⁻¹X`, `XᵀΣ⁻¹y`, `yᵀΣ⁻¹y` | `(k_β(k_β+1)/2 + k_β + 1) × 8` |
| prediction/update workspace copies | `~2 d² × 8` |
| **optimizer state — path A: dense quasi-Newton trust-region model** (§8.3) | `(p² + ~4p) × 8` |
| **optimizer state — path B: L-BFGS history m≈10, per *thread*** | `~22 p × 8` |
| Hessian at optimum (transient) | `p² × 8` |

**The optimizer term is per backend.** §8.3 specifies a batched **trust-region** for path A
precisely because line search breaks batch utilization, and a trust-region with a dense
quasi-Newton model stores `p²` plus a few `p`-vectors — **not** the 22`p` of an L-BFGS
history. L-BFGS appears only on path B, where it is per-thread.

**Output slots are per series and do not shrink under path B.** Results for all `M`
candidates are held until the tile is written: `θ̂`, `θ̂_err` (`p` each), `β`, `β_err`
(`k_β` each), `log_lik`, `k`, `n_eff`, plus `iterations` (uint16) and `status` (uint8).

Worked example at **d=3, k_β=4, p=4, N=630, M=12**, shared X:

| term | path A | path B |
|---|---|---|
| data `N×9` | 5670 B | 5670 B |
| output slots `M × 18 × 8 + M × 3` | 1764 B | 1764 B |
| `d²` terms (`P`, `F`, `Q`, `P∞`, 2 workspace) = `6d²×8` | 432 B | per thread |
| augmented `x` = `d(1+k_β)×8` | 120 B | per thread |
| normal-equation accumulators | 120 B | per thread |
| optimizer (A: `(p²+4p)×8`; B: `22p×8`) | 256 B | per thread |
| Hessian at optimum | 128 B | per thread |
| **per series** | **8490 B ≈ 8.49 kB** | **7434 B ≈ 7.43 kB** |
| per thread (path B only) | — | ≈ 1.50 kB |

**Data plus output slots account for 87% of path A's total.** The largest *solver* term is
the `d²` Kalman state at 432 B, not the optimizer at 256 B — the reverse of what an L-BFGS
history would give, which is why §8.3's trust-region choice matters here as well as for
utilization.

**Path B saves 12.4%** (1056 B of 8490 B). With per-point regressors both totals gain
20 160 B, and the saving falls to **3.7%**. Per-thread solver state totals ~6 kB at T=4 and
~96 kB at T=64 — negligible either way. See §11.5 for the consequence.

**Consequence for tiling.** The prompt's `tile_side = sqrt(block_bytes / (n_time · itemsize))`
counts only the float64 data and therefore **overestimates**:

| accounting | bytes/series | `tile_side` at a 1 GB budget |
|---|---|---|
| prompt formula (data only) | 5040 B | 445 |
| this section, shared X | 8490 B | 343 |
| this section, per-point X | 28 650 B | 187 |

---

## 10. Selection, criteria, and model averaging

- **Criteria:** AIC, AICc, BIC, HQIC, **TIC**, and cross-validation with blocked /
  rolling-origin splits. User-configurable.
- **TIC matters specifically because of the robust-variance option.** AIC's penalty is only
  correct under correct specification, which sandwich estimation concedes you do not have.
  TIC is the sandwich-corrected AIC and keeps the robust path internally consistent.
- **BIC variant using an effective sample size.** The standard `n` penalty assumes
  independent observations; with strongly correlated residuals the effective count is much
  smaller and the usual penalty is too harsh.
- **Information-criterion weights** (Akaike / Schwarz) and **multi-model averaging** of
  parameters and their uncertainties. This is the principled fix for the spatial patchiness
  that forced Hughes & Williams into a global AR(5).
- **ΔIC to next-best is a first-class output.** A selection map without a confidence
  measure is misleading.

### 10.1 Two distinct effective sample sizes

`n_eff` is used for two different purposes and **a single definition cannot serve both**:

| name | definition | used by |
|---|---|---|
| `n_eff_trend` | from the variance of the GLS trend estimate relative to its white-noise equivalent | the ML-vs-REML rule of thumb (§16.2), coverage diagnostics |
| `n_eff_bic` | a whole-series effective count (e.g. from the sum of squared autocorrelations, or `tr` of the correlation matrix) | the effective-sample-size BIC variant |

`n_eff_trend` is *term-specific* — it is the effective sample size for estimating the
trend, not a global property of the series — so using it as the BIC penalty's `n` would be
a category error. Both are stored (§12), and **they must never be interchanged.**

**`n_eff_bic` uses the participation-ratio form** on the model correlation matrix `R`:

```
n_eff = n² / ‖R‖²_F = n² / ( n + 2 Σ_{k=1}^{n-1} (n−k) ρ_k² )
```

Chosen because it is always in `[1, n]`, always well-defined, monotone in correlation
strength, computable directly from the fitted model's ACF without forming `R`, and it
degrades gracefully for near-degenerate fits. The classic `n / (1 + 2 Σ ρ_k)` alternative
is specifically the effective size for estimating *a mean*, can exceed `n` or go negative
under negative correlation, and requires windowing choices that would then need defending.

### 10.2 Weights when candidates fail

Weights are computed as `exp(−ΔIC/2)` normalized across candidates, so a NaN poisons the
entire weight vector at that point. Explicit rule:

- Failed candidates get `ΔIC = NaN` and are **excluded from the weight normalization**.
- Weights are renormalized over surviving candidates only.
- **`n_valid[y,x]` is stored.** A point where 11 of 12 candidates failed has a weight
  vector that reads as a confident selection and is nothing of the sort. Without
  `n_valid` there is no way to tell those apart downstream.

### 10.3 The signal × noise seam

In v1 the user fixes the signal specification and only the noise model is selected. The
selection layer takes `(signal_spec, noise_spec)` pairs so a future joint search is a
change of iterator, not of architecture. §6.1's REML/varying-`X` guard is written now as
the executable form of the constraint.

---

## 11. Batch execution

### 11.1 Tiling and the two-pass warm start

Tiling generalizes synesthesia's `timeseries2color.py` pattern:

- **Rechunk along time only.** Spatial rechunking creates one dask task per
  (time chunk × lat tile × lon tile), which on a large archive consumes gigabytes of graph
  state by itself.
- Derive a square spatial tile from a byte budget:
  `tile_side = sqrt(block_bytes / (n_time × itemsize))`.
- Outer Python loop over tiles; materialize one tile at a time. Peak RAM is one tile plus
  one dask chunk.
- Hard cap on total dask graph chunks as a guard.
- **The tile is the batch** — no inner loop over pixels; the batched engine advances all
  `tile_side²` series together.

**Requirement: parallelism is WITHIN a tile (over series), never ACROSS tiles.** Both paths
already work this way, but it must be written down, because across-tile parallelism is the
obvious "optimization" someone adds later — and it **multiplies peak RAM by thread count**,
silently breaking the 16 GB constraint. Within-tile parallelism is what makes peak RAM
independent of core count, and hence what lets the same job run on 4 cores and on 64.

**The conflict that forces the warm-start design.** Warm-starting from a converged
*neighbour* requires that neighbour to be finished. Per-series parallelism — path B, which
is expected to win — hands each thread the next available series with no ordering
guarantee. **Warm-starting as originally specified and the likely-winning execution
strategy are directly incompatible.** Sequential locality-preserving traversal would also
make the scientific answer depend on tile size, hence on `--memory-budget`, hence on how
much RAM the machine has. Both are unacceptable.

**Resolution — hierarchical two-pass with a barrier:**

- **Pass 1:** fit a coarse subsample — every k-th point **in dataset coordinates, not tile
  coordinates** — cold, fully parallel, no inter-point dependencies.
- **Barrier.**
- **Pass 2:** fit every remaining point warm-started from the interpolated coarse solution,
  also fully parallel, because all its inputs already exist.

Extends to a multi-level V-cycle if one level proves insufficient. The coarse grid being in
**dataset** coordinates is the load-bearing detail: it decouples the result from available
RAM.

**Pass 1 does four jobs at once** — it already fits a stratified global subsample cold with
no dependencies, so it is also the natural place for the Whittle screening pass, the
calibration-tile RSS measurement (§11.4), the cold reference for the hysteresis audit
(§11.2), and the early-abort decision point (§14.1). Four mechanisms collapse into one
pass.

**Screening caution.** A candidate eliminated by coarse-grid screening is eliminated
*everywhere*, which is a stronger assumption than per-point elimination — and the whole
premise is that spectral shape varies spatially. Therefore: either screen **per-point in
pass 2** (cheap; Whittle is O(N log N)), or require **unanimity across the coarse points**
rather than an aggregate. Either way, record which candidates were eliminated globally so
the output is not silently conditioned on a decision the user never saw. Screening scores
are Whittle-engine scores and **must not be compared against final scores** (§6.2).

Warm start carries **θ̂ in unconstrained coordinates only** — not L-BFGS curvature history,
which is fragile across points and would deepen the hysteresis coupling.

**Warm-start cache key: `(fit_hash, candidate spec_hash)`** — see §13.3. `fit_hash`, not
`compat_hash`: θ̂ does not depend on the criterion set, so keying warm starts on
`compat_hash` would discard every warm start the moment a user adds HQIC. And the candidate
spec hash is needed because warm starts are per-candidate while neither run-level hash
covers the candidate set.

A warm-start array written under a different objective, spec, or registry version is
**actively harmful** — silent reuse of a stale warm-start cache produces converged-looking
fits at the wrong optimum, the worst failure mode in the system. Mismatch is refused, never
used.

**Nested-model chaining within a point** (initializing AR(5) from AR(4)'s optimum) is
deferred, and the deferral carries its condition: it has the same hysteresis pathology in a
different axis — it would bias toward the nested solution and systematically favour simpler
models. When it lands it needs its own audit.

### 11.2 The hysteresis audit — mandatory, not optional

Warm-starting does not merely speed convergence; on a multimodal likelihood it changes
which optimum you land in. That is inherent. But consider what it does *here*: initializing
each point from its neighbour's answer biases every point toward its neighbour's answer,
producing spatially smooth maps.

**Spatial smoothness is exactly what this package is trying to achieve** — and the entire
argument is that it should be earned honestly via IC weights and model averaging.
**Optimizer hysteresis produces a visually identical result by an illegitimate mechanism.**
A smoothness artifact from warm-starting would look like the design working.

**Cold is the reference**, since it has no inter-point coupling.

**Disagreement is measured four ways**, because they answer different questions:

| metric | question answered |
|---|---|
| **Selection disagreement** | did warm and cold select a different model? Binary, most interpretable, most directly about the smoothness artifact |
| **Objective disagreement** | `|ℓ_warm − ℓ_cold|` above a threshold — distinguishes "different optimum" from "same optimum to different precision" |
| **Parameter disagreement** | distance in unconstrained coordinates, normalized by estimated standard error, so it is in units of "how much does this matter" |
| **Signed trend disagreement** | the actual scientific payload. **Mean signed difference, not just magnitude** — zero-mean disagreement is noise, a biased one is systematic contamination |

**The audit subsample is stratified, not uniform random.** Hysteresis will concentrate
exactly where the likelihood is multimodal or flat — the near-degenerate geography of
§4.8, high-variability regions, and boundaries between spectral regimes (shelf/deep ocean,
the Rossby-wave transition near ±30°). A uniform random subsample is dominated by easy
points and reports a reassuringly low rate. Stratify by a post-fit difficulty proxy —
Hessian condition number, ΔIC to next-best (small ΔIC = ambiguous selection), or
failure-taxonomy status. **Report per stratum as well as overall: the overall number is
the one that gets quoted and the per-stratum numbers are the ones that are true.**

**The audit must be able to conclude "do not do this."** Report mean iterations cold vs
warm. **If warm-starting saves less than ~30% of iterations, the mechanism is not paying
for its complexity or its hysteresis risk, and warm-starting is dropped.**

**Barrier cost is measured, not assumed.** Two passes means coarse points are fit twice (or
special-cased) and the barrier costs a full sync at 10⁷ scale. At subsample rate `1/k²`,
pass 1 costs ~`1/k²` of a cold run, so the arithmetic is favourable for `k ≥ 4` *provided*
warm starts save a meaningful fraction of iterations — which is the unmeasured quantity
above.

Warm-starting is **disableable by config**, and whether it was used is recorded in
provenance, because it changes the meaning of the output.

### 11.3 Reproducibility guarantee, with preconditions

> For a given (data, config, metamer version), output is **bitwise identical** regardless
> of memory budget, tile size, thread count, and traversal order.

This is achievable **because each series is fit independently — there are no cross-series
floating-point reductions to reassociate.** The guarantee is stated *with* its
preconditions, because an overclaimed determinism guarantee that fails once is worse than
a precise narrower one:

1. **Coarse-to-fine interpolation in pass 2 must be order-independent** — nearest-coarse-
   point, or bilinear with a fixed evaluation order. A neighbourhood reduction whose
   summation order depends on chunking breaks the guarantee. Tested.
2. **Global diagnostic reductions** (mean `n_eff`, aggregate counts) either use a
   deterministic reduction order or are **explicitly excluded** from the claim.
3. **numba `fastmath` off** (or documented as on with the guarantee weakened to "bitwise
   for fixed thread count"); **BLAS threading fixed or unused.** Both can reassociate.
4. **Within a platform, not across platforms.** `exp` and `log` differ in the last bit
   between libms, so Linux and macOS will not agree bitwise. This is true today and is not
   a consequence of any Windows decision.

Exit criterion: two runs at different memory budgets and thread counts produce
byte-identical stores.

### 11.4 Memory budget and the calibration tile

Expose a single **`--memory-budget` in GB** as the primary knob (defaulting to a fraction
of detected free RAM), with byte-level manual overrides retained.

The memory multiplier is not 1: beyond the data tile (float64, so 2× synesthesia's
float32) there is a validity mask, Kalman state means and covariances, residual and
workspace copies, and gradient buffers scaled by parameter count. Rather than hardcode a
constant, **measure**: pass 1 doubles as the calibration tile, deriving true
bytes-per-series for this dataset and model set, validated against §9.4's analytic formula.

**Cache key: `fit_hash` + backend + machine fingerprint** (§13.3 — the criterion set does
not affect bytes-per-series).

- **Backend must be in the key** because bytes-per-series is backend-dependent — path A's
  solver state is per-series, path B's is per-thread; the formulas have different *shapes*,
  not just different constants. (If the backend is fixed per metamer version, the version
  covers it; the design states which.)
- **Machine fingerprint is `(CPU model, core count, total RAM)` hashed — instance-type
  based.** Hostname is meaningless on ephemeral nodes. Thread count is deliberately
  excluded so a fresh spot instance of the same type **reuses** a calibration rather than
  remeasuring.
- **The calibration cache lives with the store, not in local scratch** (§15.5). On a
  preemptible instance anything in local temp is gone on restart, and the two-pass barrier
  means losing pass 1's warm starts costs a full re-run of it.
- The cache has an explicit expiry and a `--recalibrate` flag. A cached measurement
  surviving a hardware change silently produces a bad RSS projection against a hard memory
  constraint.

### 11.5 Consequences if path B wins

Both are recorded now so they are not surprises:

- **The ragged fallback stops being a cliff.** Per-series compiled code does not care that
  time axes differ; each series memoizes its own unique-Δt set. §2.1's ragged language
  survives as a modest cost, not a large penalty. It must still log a prominent warning
  rather than degrade silently.
- **The memory formula changes shape** (§9.4): path B's solver state is per-thread rather
  than per-series. But the *magnitude* of that win must not be overstated. By §9.4's
  corrected figures, path A is 8.49 kB/series and path B 7.43 kB/series — a **12.4%
  saving**, because data and output slots already account for 87% of the total. With
  per-point regressor fields the saving falls to **3.7%**.

  **The 16 GB constraint is governed by the data tile and the output slots, essentially
  regardless of backend.** Path B's memory advantage is useful, not transformative; the
  reason to prefer path B is speed and the collapse of the ragged cliff, not memory.

---

## 12. Output: zarr schema

### 12.1 The structural claim

The prompt frames this as "ragged per-model output with variable parameter counts." That is
true, but it applies to the wrong half. **In v1 the signal spec is fixed** — only the noise
model is selected — so `β` has the same length at every grid point and under every
candidate. The trend, its uncertainty, and its model-averaged version — the entire
scientific payload — are **dense, uniform, and rectangular.** Raggedness afflicts only the
noise parameters, which are secondary diagnostics.

### 12.2 Layout

```
/                 attrs: schema_version, fit_hash, compat_hash, run_hash, objective, engine,
                         registry_version, metamer_version, profile_name,
                         candidate spec hashes, warm_start_used, calibration provenance
/signal/          dense   beta[y,x,m,b], beta_err[y,x,m,b]      (selected + model-averaged)
/selection/       dense   delta_ic[y,x,m,c], weight[y,x,m,c], ic_best[y,x,c],
                          selected[y,x,c], n_valid[y,x]
/primitives/      dense   log_lik[y,x,m], k[y,x,m], n_eff_trend[y,x], n_eff_bic[y,x],
                          iterations[y,x,m]
/noise/           ragged  theta[y,x,P_total], theta_err[y,x,P_total]
/status/          dense   outcome[y,x,m] (enum), outcome[y,x] (aggregate)
/detail/          ragged  full parameter covariances — subsample / region only
/warmstart/       dense   unconstrained θ̂ — machine state, disposable, separately keyed
/completion/      dense   tiles[ty,tx] uint8
```

`m` = model axis, `b` = signal-parameter axis, `c` = criterion axis.

### 12.3 The ragged noise axis: flattened with an index

`theta` has one axis of length `P_total = Σ_m p_m`, with coordinate arrays
`noise_param_model[P]`, `noise_param_name[P]`, `noise_param_unit[P]`,
`noise_param_transform[P]`. Model *m*'s block is the contiguous slice
`theta[..., off_m : off_m + p_m]`.

Rejected alternatives: **padded** `theta[y,x,m,p_max]` creates an indistinguishable
padding-NaN vs failure-NaN ambiguity — an ambiguity you would be choosing to create;
**one group per family** is self-describing but multiplies arrays and forces region writes
and the completion bitmap to stay coherent across all of them.

**The flattening machinery is written generically over "a ragged axis with an index,"
not hardcoded to noise parameters**, so `/signal/` can adopt it unchanged when v2's joint
search makes `β` ragged too.

**`/signal/` carries an explicit model axis even in v1** (length M, or length 1 with a
documented broadcast), so adding per-candidate `β` is a shape change rather than a
restructure. Cost now is near zero; cost later is a format migration on a 10⁷-point store.

### 12.4 Coordinate dtypes

Coordinate arrays use **fixed-width bytes (e.g. `S32`)**, with an integer-code JSON legend
in attrs as redundancy. Variable-length strings are the default path and a compatibility
hazard — zarr v3 string support and xarray's handling of it are the least stable corner of
the stack, and this is precisely the metadata a consumer without metamer installed must be
able to read.

**Acceptance criterion for "self-describing": round-trip through plain `xr.open_zarr` with
no metamer installed.** This is the kind of thing that works on the author's machine and
fails for a collaborator.

### 12.5 Status invariants and primitives

**Both directions asserted, and tested:**

- A NaN value never coexists with an `OK` status.
- A non-`OK` status has NaN in **all** corresponding value slots. Otherwise a partially
  written failure leaves stale or garbage numbers that read as valid.

**The status array is initialized to `NOT_ATTEMPTED`, not to zero/OK**, so an interrupted or
partial write reads as unattempted rather than as success.

**Status is per `(point, model)`, not per point.** A candidate can fail where another
succeeds — that is the near-degeneracy geography of §4.8 — and its spatial pattern is
itself a diagnostic.

**Store the primitives, not just the verdict.** `log_lik[y,x,m]`, `k[y,x,m]`,
`n_eff_trend[y,x]`, `n_eff_bic[y,x]` make the store scientifically auditable rather than a
black box that emits a winner, and let a user recompute a criterion that was not anticipated
**without refitting 10⁷ series**. `k` is unambiguous because the objective is fixed per run
and recorded in attrs (§4.7). The engine and objective tags live as attrs on `log_lik`, so
the §6.2 guard can be enforced by a consumer at read time, not only at write time.

`iterations[y,x,m]` is dense `uint16` (240 MB at 10⁷×12, compressing well — low entropy).
It is stored because the end-of-run report is **derived from the store** (§14.2) and could
not otherwise regenerate the iteration histogram or the warm-vs-cold comparison. It is also
independently useful: an iteration-count map is a good proxy for likelihood difficulty and
correlates with the near-degenerate geography.

### 12.6 ΔIC, criteria, and precision

**Store ΔIC, not IC.** `ic_best[y,x,c]` in float64 plus `delta_ic[y,x,m,c]` in float32. Raw
IC values are ~10³ with scientifically meaningful differences ~1, so float32 IC would lose
the signal; ΔIC in float32 keeps it exactly, and ΔIC is a required first-class output
anyway.

**A criterion axis, not one criterion per run.** The fits dominate cost; the criteria are
arithmetic on already-stored `log_lik` and `k`. Several criteria are computed from the same
fits, so `/selection/` carries a criterion axis and the store answers questions it was not
configured for.

**Store all M rather than top-k while M ≲ 32.** Top-k needs a parallel index array and
complicates every read; at M ≈ 12 it saves nothing worth the complexity. Threshold
documented; the top-k path is deferred until a candidate set exceeds it.

### 12.7 Units, chunking, and write ordering

**Natural units on disk, unconstrained space in the sidecar.** The store is an
earth-science data product and must be readable without the library, so `theta` and
`theta_err` are in natural units with the §4.1 delta-method push-through already applied.
The unconstrained θ̂ that warm-starting wants lives in a separate, deletable `/warmstart/`
array — machine state, not science.

**Zarr v3 with sharding.** Shard = one spatial tile, so a region write is exactly one shard
per array and aligns with the tiling loop by construction; chunk = a subdivision of the
shard, sized for reads. This preserves the one-region-per-tile write property while keeping
read chunks sane. Sharding is also what keeps tile-sized writes from producing an inode
explosion at 10⁷ points — and it is the mitigation that makes the NTFS many-small-files
concern (§15) tractable.

Computed shard sizes (float32, `P_total = 40`):

| `tile_side` | `theta` shard | `delta_ic` shard (M=12, C=3) |
|---|---|---|
| 200 | 6.4 MB | 5.8 MB |
| 445 | 31.7 MB | 28.5 MB |

Chunk subdivision targets a few MB. Compression: zstd + shuffle.

**Write order is data-then-bitmap, always.** The completion bitmap for a tile is written
only after every array's region write for that tile has flushed, so an interrupted run can
never mark incomplete data complete.

**`schema_version` is written into root attrs at store creation**, and checked on resume and
on read. It costs nothing and is the only thing that makes a future migration tractable
rather than archaeological.

### 12.8 Resumption

Resume compares the three hashes of §13.3 and the candidate set, and there are **three**
outcomes, not two:

| condition | action |
|---|---|
| `fit_hash` matches, `compat_hash` matches, candidate set is a **superset** | resume normally: reuse all completed tiles, fit only what the completion bitmap says is outstanding |
| `fit_hash` matches, **`compat_hash` differs** (e.g. a criterion was added) | **recompute the derived `/selection/` arrays from the stored `log_lik`, `k`, `n_eff` primitives and continue. Do not refuse. Do not refit.** |
| `fit_hash` differs | refuse — the stored fits are not reusable |

The candidate-set **superset** rule (same candidates in the same order, possibly more)
exists because §12.5 stores per-candidate primitives, making candidate-set extension a
*scientifically* legitimate incremental operation: existing fits are unaffected, only
`P_total` and the model axis grow.

The middle row is the reason §13.3 splits `fit_hash` out of `compat_hash` at all. Without
it, adding HQIC to a finished 10⁷-point run would demand a full refit to compute arithmetic
on numbers already sitting in the store.

Refusal never silently mixes.

---

## 13. Config and validation

### 13.1 Format

**TOML as the human format, pydantic as the schema, canonical JSON as the hashed form.**
`tomllib` is stdlib in 3.12 — no new dependency — and `pydantic`, `typer`, `rich` are
already present. `.json` is also accepted for machine-generated configs.

TOML's weakness is deep nesting, and a candidate set is three levels deep. Inline tables
handle it, and the §4 string sugar means the verbose form appears only when pinning or
sharing parameters:

```toml
[[candidates]]
label = "white+ou"
terms  = ["white", "matern12"]                                   # sugar

[[candidates]]
label = "white+ou+sho"
terms  = [ "white",
           { kind = "matern12", params = { rho = { fixed = 90.0 } } },
           "sho" ]
```

**The structured list-of-terms form is canonical; strings desugar to it.** No infix grammar
as the primary representation — it grows warts the moment someone needs a fixed parameter,
a shared parameter across terms, or a non-default bound. Strings are parsed by restricted
evaluation against the registry namespace, not a hand-rolled tokenizer.

YAML was rejected: more natural for nesting, but costs a dependency and brings
implicit-typing footguns into a scientific config, where `no` becoming `False` or a version
string becoming a float is a real hazard.

### 13.2 Staged validation

Each stage **names itself in its error**, because "your config is invalid" before a 10-hour
job needs to say which layer and why.

1. **Syntax** — TOML/JSON parse.
2. **Schema** — pydantic: types, ranges, enums.
3. **Semantic, data-independent** —
   - empty engine-capability intersection, naming which term eliminated which engine (§4.2)
   - **gradient-capability resolution across composite terms** (§4.3) — a silent FD
     fallback is a ~1.7× cost difference at p=6 and changes the wall-time projection
   - REML with a varying-`X` candidate set (§6.1); REML with nonlinear signal terms
   - criterion/objective compatibility: TIC requires a Hessian; CV requires a splitting
     strategy defined for the data layout; the `n_eff` BIC variant needs a post-fit
     quantity, so `--explain` reports **which criteria are computable at all**
   - cost class incompatible with series count — refusing Toeplitz at 10⁷
   - duplicate candidates by spec hash
   - MCMC above the confirmation threshold
   - identifiability lint (§4.8), as a warning
4. **Data-dependent** — only checkable once data is open: epochs inside the record,
   harmonics resolvable by the sampling, regressor alignment, `rank(X)` (§5.2). Runs at
   startup against pass 1, not at parse time.

### 13.3 Three hashes

Two are not enough. The criterion set belongs in the resumption gate (it determines the
stored `/selection/` arrays) but **not** in the warm-start key (AIC vs BIC changes nothing
about where the optimizer lands). Collapsing them discards every warm start the moment a
user adds HQIC, and blocks a legitimate resume workflow.

| hash | covers | used for |
|---|---|---|
| **`fit_hash`** | everything determining `θ̂` and `log_lik`: data source and selection, signal spec, objective, engine, registry version, seeds, metamer version. **Not** the criterion set. **Not** the candidate set. | warm-start key component; the gate for **reusing fits** |
| **`compat_hash`** | `fit_hash` + criterion set + anything else affecting stored *derived* arrays | the gate for reusing `/selection/` |
| **`run_hash`** | everything, plus memory budget, tile size, thread count, output path, verbosity, machine fingerprint | provenance only, never a gate |

Runtime knobs appear only in `run_hash`, which is what permits starting on the 64-core node
and resuming on the mini PC — a real workflow, made legitimate by §11.3's determinism
guarantee, and the same property that makes a future cloud burst (§15.5) a resume rather
than a rerun.

**The payoff is in the mismatch behaviour** (§12.8): `compat_hash` mismatch with matching
`fit_hash` **recomputes the derived arrays from the stored primitives and continues** — it
does not refuse and it does not refit. §12.5 already stores `log_lik`, `k`, and `n_eff`
precisely so criteria are recomputable without refitting 10⁷ series; a single hash boundary
would have forbidden exactly that.

Calibration cache key: `fit_hash` + backend + machine fingerprint (§11.4) — the criterion
set does not affect bytes-per-series.

**Hashing the validated, normalized pydantic model rather than the file text** normalizes
away comments, key order, whitespace, and explicit-vs-default, so adding a comment does not
invalidate a 10⁷-point store.

**Compat-relevance is an allowlist, not a denylist.** Fields are marked compat-relevant by
explicit annotation. With a denylist, every newly added field silently becomes
compat-relevant and the failure mode is "resume broke and nobody knows why." A test
enumerates the compat-relevant field set and asserts it against a hardcoded list, so
changing it requires updating the test — golden-file discipline.

The sharp edge, named explicitly: because defaults are included, **any metamer version bump
touching a compat-relevant default invalidates every in-progress store**, including bugfix
releases. The allowlist is what keeps that surface small and reviewable.

### 13.4 `metamer validate --explain`

Dry run: executes layers 1–3, layer 4 if data is reachable, then prints the resolved
canonical config, **all three hashes**, and a per-candidate table of **resolved engine, cost
class, gradient mode, and objective**, plus projected wall time and peak RSS.

**It also reports which regressor regime the config lands in** — shared X or per-point X
(§9.4) — because that single fact changes bytes-per-series by ~3.4× and `tile_side` by ~2×,
and it is the difference between a configuration fitting in the available RAM and not.

Given the hard 16 GB constraint, finding out before starting is worth considerably more
than the hours it costs to implement.

**Projections carry their provenance inline**, or they will be trusted wrongly. Each printed
constant is labelled as: (a) measured on this machine from a cached calibration, (b)
measured on this machine in this session, or (c) a default shipped with the package. **In
case (c), print a range, not a point estimate**, and offer `--explain --calibrate` to run a
quick measurement first. A confidently wrong RSS projection against a hard memory constraint
is worse than an honestly wide one.

**`--explain` accepts a machine profile, not only the local machine.** A profile is the
§9.2 roofline pair plus core count and RAM. Shipped profiles accumulate as instance types
get measured. This is where the roofline model earns its cost: it lets `--explain` project
wall time — **and therefore rental cost** — on an instance type that has never been rented,
before renting it, turning instance selection into a calculation rather than a guess. The
prediction is always printed with the model's validated error bar (§9.2).

When screening is enabled, the projection is an **upper bound** (screening has not yet run
and cannot be predicted) and says so.

### 13.5 Profiles

Flat named presets (`screening`, `exact`, `fast`) applied **before** validation — never an
inheritance or include chain, which is a config-language rabbit hole. The resolved config
is what gets hashed, so switching profile is visible in `compat_hash`.

**Provenance also records the profile name**, because "this run used the screening profile"
is the human-legible fact someone needs six months later and is not recoverable from the
resolved config.

---

## 14. Run-level reporting

Per-point status exists in the store; something must turn 10⁷ × 12 status codes into
something a human learns without writing analysis code. A run that quietly succeeds on 97%
of points and returns 0 is the failure mode this section exists to prevent.

### 14.1 Live: streaming counters with a conservative early abort

Per-tile tallies by taxonomy branch and by candidate on a `rich` progress display. At 10
hours, discovering a config bug at hour 9 is the expensive outcome.

**The abort is evaluated on pass 1, not on a fixed prefix of tiles.** Tiles are processed in
spatial order, so "the first 1% of eligible points" is a geographically contiguous strip —
on a global grid, a polar band or a single basin — and both failure rates and spectral
regimes vary enormously by region. A candidate failing 95% of the first strip may be fine
globally, and vice versa. Pass 1 is stratified across the whole domain **by construction**,
completes before pass 2 starts, and its barrier is a natural decision point. It costs
nothing because the pass already exists.

Thresholds are calibrated to catch **bugs**, not to second-guess science. A 25% failure rate
may be real; a candidate failing 95% of a global stratified sample is a capability or
parameterization error.

| pattern | default response |
|---|---|
| **all candidates** > 90% failure | **abort** — config or data error |
| **a single candidate** > 90% failure | **abort by default**, with `--on-candidate-failure={abort,drop,continue}` |

**Demotion, not only termination.** Dropping a single failing candidate and continuing with
the rest is often the useful action. A dropped candidate gets the distinct
`CANDIDATE_DROPPED` status across all remaining points — **not** `NOT_ATTEMPTED`, which
means "screened out" — so the store records what happened, and the drop is a **headline
line in the report**, not a buried counter.

`--no-early-abort` exists for datasets where high failure is genuinely expected.

### 14.2 End of run: a report derived from the store

Computed **from the stored status arrays, not from carried counters**. The status arrays are
dense `uint8[y,x,m]` — 120 MB at 10⁷ × 12, trivially reducible. This makes **resumption
correctness free**: a resumed run's report covers the whole run because it reads the whole
store. Exposed as `metamer report <store>`, so it is regenerable, independently testable,
and usable on someone else's store.

Contents:

- Counts and rates per branch and per candidate, with the **eligible-point denominator
  stated explicitly** (excluding `INSUFFICIENT_DATA` / `NOT_APPLICABLE`).
- **A spatial clustering statistic on the failure indicator.** This carries the information:
  3% scattered is fine, 3% concentrated in the Southern Ocean is a finding, and a scalar
  rate cannot distinguish them. Specifics that matter:
  - **Index-space adjacency, documented as such** (not metric-space) — longitude wraps and
    latitude convergence mean adjacency at 80°N is not the same physical distance as at the
    equator. Area-weighting is the alternative; the design states which is used.
  - **`NOT_APPLICABLE` points are excluded from the adjacency graph entirely**, not treated
    as non-failures. Land forms enormous contiguous blocks and would dominate the statistic
    with a spurious signal.
  - Reported **with a permutation null distribution**, not as a bare coefficient, since
    nobody remembers what a given Moran's I value means.
- Downsampled PNG map per branch. In this domain the map *is* the diagnostic.
- The `n_valid[y,x]` distribution (§10.2).
- §11.2 audit numbers: disagreement rates overall **and per difficulty stratum**; mean
  iterations warm vs cold against the ≥30% threshold.
- Iteration-count histogram from `iterations[y,x,m]`.
- Resolved config, all three hashes (§13.3), profile name, calibration provenance.
- **Per-candidate resolved engine, cost class, gradient mode, and objective** — the same
  table `--explain` prints. The report is the artifact that survives; reading what was
  actually run without reconstructing it from the config and the registry version is worth
  four columns.

Markdown plus PNGs beside the store, the same numbers as JSON, and the scalar summary into
root attrs.

### 14.3 Exit codes and the final line

| code | meaning |
|---|---|
| 0 | clean |
| 1 | completed with failures above threshold |
| 2 | aborted early — **resumable** |
| 3 | config/validation error (layers 1–3) — resuming will not help |
| 4 | data-dependent validation error (layer 4) |

A script that resumes on failure needs to distinguish "aborted, resumable" from "config
rejected."

**The final console line includes `fit_hash`, `compat_hash`, and the store path** — that is
what a user needs to resume or regenerate the report, and what they will copy out of a
terminal scrollback three days later.

---

## 15. Platforms and dependencies

### 15.1 Tiers

| tier | platforms | commitment |
|---|---|---|
| **1** | `linux-64`, `osx-arm64` | Supported. All exit criteria must pass. |
| **2** | `osx-64`, `linux-aarch64` | Supported, best-effort. Kept until a solve actually breaks, then dropped with a note. |
| **—** | `win-64` | **Portable by discipline, not claimed in v1.** |

### 15.2 celerite2 availability (verified 2026-08-04)

| platform | conda-forge | PyPI wheel |
|---|---|---|
| `linux-64` | ✅ 0.3.2 | ✅ |
| `osx-64` | ✅ 0.3.2 | ❌ |
| `osx-arm64` | ❌ **none** | ✅ 0.3.3 |
| `win-64` | ⚠️ 0.2.0 / py39 only | ✅ 0.3.3 |
| `linux-aarch64` | ❌ | ❌ |

No single package source covers everything. **This is acceptable because celerite2 is a
test dependency, not a runtime one** — §16.1 makes brute-force MVN the *primary* oracle
precisely because celerite2 shares the GP-likelihood conceptual frame, and MVN is pure
numpy with no platform gap. celerite2 lives in a test-only pixi feature and its agreement
test skips where it is not importable. A decision made for correctness reasons paid for
itself in portability.

`numba` is available on every platform above (verified).

Packages with no `osx-arm64` build go under `[target.linux-64.dependencies]` in
`pixi.toml`, per the project's cross-platform conda conventions.

### 15.3 Windows: portable, unclaimed

**In favour.** The usual Windows blocker is `fork`, and **this design does not have one** —
the tiling loop is a single process with numba's threaded `prange` and dask's threaded
scheduler. No multiprocessing to port. Every core dependency is on conda-forge `win-64`,
and celerite2 has modern PyPI wheels there.

**Against.**

1. **No `resource` module** for peak-RSS measurement — and that measurement is load-bearing,
   feeding the calibration tile and the memory formula against a *hard* 16 GB constraint. A
   shim is needed regardless (`ru_maxrss` is KB on Linux, bytes on macOS), so the marginal
   cost is one branch — but an untested branch guarding a hard constraint is worth little.
2. **Filesystem.** Zarr stores are directory trees; NTFS is markedly slower for
   many-small-files, and `MAX_PATH` bites without long paths enabled. §12.7's sharding helps
   substantially.
3. **The commitment.** "Runs on Windows" without Windows CI is a claim that decays silently.

**Four disciplines adopted from day one**, cheap now and expensive to retrofit:

1. `pathlib` throughout; no `os.path` string joins, no POSIX path literals.
2. No `fork` assumptions. Parallelism is threads. Any future process use must be spawn-safe.
3. A **platform shim module for peak RSS** from the start, with the Windows branch written
   though untested. Needed for Linux/macOS anyway.
4. No POSIX-only syscalls, no shell-outs; `os.replace` for atomic writes; never hold a
   handle open across a rename.

Windows then becomes "add `win-64` to the platform list and stand up a CI leg," not a port.

### 15.4 dtype policy

**float64 throughout `core`**, stated explicitly. float32 conversion happens at the
batch/IO boundary, **per dask chunk during tile assembly** (§9.4) so both full
representations never coexist. Output arrays are float32 except where §12.6 requires
float64.

### 15.5 Cloud readiness

Development happens on a 4-core / 16 GB mini PC (§9.2), and a `cloudify` skill giving
SkyPilot access is forthcoming. The upgrade should be a configuration change, not a port.
**Most of what that requires is already in the design for other reasons:**

| property | already decided because | cloud consequence |
|---|---|---|
| **zarr v3 + sharding** (§12.7) | inode explosion at 10⁷ points | object stores penalize many small objects far more harshly than POSIX filesystems; sharding collapses object count by the shard factor. The single most important cloud property, already chosen. |
| **runtime knobs excluded from `fit_hash`/`compat_hash`** (§13.3) | resume on a different machine | "run locally until the budget runs out, burst to cloud, resume" works **by construction** — it is a resume, not a rerun |
| **determinism independent of memory budget and thread count** (§11.3) | results must not depend on RAM | a cloud-resumed run produces the same answer as a local one |
| **calibration keyed on machine fingerprint** (§11.4) | heterogeneous nodes | each instance type gets its own cache entry automatically |
| **single-process, threaded tiling loop** (§11.1) | Windows portability, simplicity | a cloud node is simply a bigger box — no distributed scheduler required |

Five things to add now, all cheap:

1. **Every path is an fsspec URL, not a filesystem path** — data source, output store,
   warm-start sidecar, report output, cache locations. **No POSIX assumptions in the store
   layer:** no file locking, no rename-based atomicity, no directory-listing-as-truth. The
   data-then-bitmap ordering (§12.7) is already the right pattern for object storage and
   relies only on per-object write atomicity, which S3 and GCS both provide. Do not add
   anything needing more.
2. **Caches live with the store, not in local scratch.** The warm-start array and the
   calibration cache go in (or beside) the zarr store in object storage. On a preemptible
   instance, local scratch is gone on restart — and because of the two-pass barrier
   (§11.1), losing pass 1's warm starts costs a full re-run of pass 1.
3. **Machine fingerprint is instance-type-based** — `(CPU model, core count, total RAM)`
   hashed (§11.4) — so a fresh spot instance of the same type reuses its calibration.
4. **`--explain` takes a machine profile** (§13.4), so wall time and cost can be projected
   for an instance type before renting it.
5. **Preemption is just resumption.** `fit_hash` gating plus the completion bitmap already
   handle it. The only additions: checkpoint the bitmap frequently enough that a preemption
   loses **at most one tile**, and **handle `SIGTERM` by flushing** rather than dying
   mid-region-write.

- **No local-filesystem assumptions in the reporting path** (§14.2) — PNGs and JSON are
  written through the same abstraction as the store.

**One thing deliberately not built, with its blocker named.** Horizontal scaling across
*multiple* nodes would partition the tile space, and the completion bitmap is already the
natural coordination primitive. But the bitmap is read-modify-write, which is **not atomic
on object stores**, so multi-node writers would need a tile-claiming mechanism (a lease
directory, or per-worker bitmap shards reduced at the end). That is the one piece requiring
design rather than configuration, and it is out of scope for v1 — recorded here so a future
multi-node attempt starts from the known obstacle rather than discovering it through
corrupted state.

---

## 16. Testing

Two suites, kept strictly separate. Conflating them yields a suite that is both slow and
flaky.

### 16.1 Unit tests — fast, seeded, deterministic

Designed under the `test-design` skill. For each test, state the behaviour under test, a
concrete bug that would make it fail, and how the expected value was determined
**independently of the implementation**. Drop any test for which that sentence cannot be
written.

**The primary oracle is brute-force MVN, not celerite2.** At small N, build the covariance
matrix explicitly from the analytic autocovariance and evaluate the multivariate normal
density directly. That is independent of the entire state-space formulation. celerite2
agreement is a valuable second check, but it shares the GP-likelihood conceptual frame — it
can agree with you and both be wrong.

**They validate different things, and that is what sets the priority.** MVN checks the
filter against an analytic ACF taken from the literature, so it independently validates the
**state-space construction** — the part that is bespoke here. celerite2 validates the **ACF
itself**, which is valuable but less so, because the Matérn ACFs are textbook and checkable
by inspection. celerite2 is therefore an **optional test on Tier-1 platforms**, and it is
the first thing to cut if Phase 1 proves too large (§18).

High-value targets:

- Kalman log-likelihood vs brute-force MVN at small N, every Phase 1 family **and a sum**
- Batched Kalman vs `celerite2` on identical input (headline test; `linux-64`/PyPI-wheel
  platforms)
- Known analytic autocovariance for OU / Matérn ν=1/2
- Analytic `F`, `Q`, `P∞` vs a general `expm`/Lyapunov reference, per family
- Defective-root guard: condition-number fallback fires where expected
- Sum-of-OU power-law approximation vs its target spectrum, to the stated tolerance
- GLS profiling vs explicit generalized-least-squares inversion
- REML penalty vs brute-force `log|XᵀΣ⁻¹X|` from an explicitly constructed Σ at small N
- Design-matrix construction for every signal term, including boundary cases (offset at
  first/last sample, zero-length segments) and rank-deficient cases
- **Gap masking:** masked points give the same likelihood as genuinely absent points
- Parameter counting vs hand-counted values, **both objectives**
- Gradient-capability resolution on a composite where one term lacks analytic gradients
- Analytic gradient vs oracle, at randomized θ within diagnostic limits, **per family**
- Hessian at optimum vs brute-force FD Hessian at small N
- The engine-comparability guard actually raises; the objective guard actually raises
- The REML-with-varying-`X` guard actually raises
- Reproducibility under a fixed seed, including with warm-starting enabled
- Every failure-taxonomy branch reachable by a constructed test case
- Both status/value invariants (§12.5), in both directions
- Round-trip read of a store through plain `xr.open_zarr` with no metamer installed

**Public conformance-test helper.** Analytic-gradient agreement is a *permanent* test run
per family at registration, and it is **enforced for third-party families registered via the
entry-point group**, not only for in-tree ones. The helper is public API so a third-party
kernel author can run it against their own family. That is what makes the extensibility
claim real rather than nominal.

### 16.2 Simulation-recovery benchmark — slow, stochastic, tolerance-banded

A first-class component. Run on demand; in CI only at small N. Emits a reproducible report.

1. **Selection accuracy** — confusion matrices across families as a function of series
   length, SNR, sampling rate, and gap fraction, for each criterion. The
   flicker / AR(1) / GGM triangle is the headline; the honest result is likely "these are
   not separable below some N," and that is exactly what users need told.
2. **Parameter recovery** — bias and RMSE per family.
3. **Trend-uncertainty calibration** — empirical coverage of nominal 95% intervals under
   (i) the true model, (ii) the selected model, (iii) the model-averaged estimate. **This is
   the most important number the package produces**, since it validates the actual
   downstream claim.
4. **Misspecification** — simulate a series with an undetected offset and record which noise
   model wins. **Figure goes in the README.**
5. **ML vs REML coverage**, swept properly. A single-point comparison produces a number; the
   informative structure is where the gap is large. Sweep against `k / n_eff_trend` — vary
   low-frequency dominance (spectral index, or Matérn ρ relative to record length) crossed
   with `k` (2 vs 4 vs 8 signal terms). **Prediction:** the gap grows as `k / n_eff` grows
   and is negligible when it is small. If it holds, there is a defensible documented rule of
   thumb ("use REML when `k/n_eff` exceeds ~X"); if it does not, either the implementation
   or the argument is wrong and it matters which. Optimizer settings are held fixed across
   objectives, or the coverage difference partly measures convergence differences.
6. **Warm-start hysteresis, on simulated *fields*.** The benchmark as originally specified
   simulates independent series — and **hysteresis is a spatial phenomenon that cannot
   appear in independent draws with no neighbour structure.** Generate lat/lon fields where
   the true noise parameters (i) vary smoothly and (ii) vary sharply across a boundary,
   simulate a series at each point, fit warm and cold. **The sharp-boundary case is
   decisive: warm-starting will smear the boundary, and the smear width is a direct
   measurement of the artifact.** That figure goes in the README next to the
   misspecification figure — it is the honest disclosure that makes the smoothness claim
   credible.

### 16.3 External cross-validation

Reproduce at least one published result from Hector, CATS, or `est_noise` using the **exact
power-law path**, as a regression test against the geodesy literature. Run under **ML**, for
comparability with those packages.

---

## 17. Phased implementation plan

Phase 1 is a **vertical slice**, not a horizontal layer. A horizontal "build all the kernels
first" phase gives no feedback until Phase 3 and hides interface mistakes until they are
expensive.

### Phase 1 — the likelihood spine (`metamer.core`, arrays only)

Batched `(B, N)` API throughout; no tiling, no zarr, no CLI.

- ParamSpec / Bijector machinery with `log|J|` and delta-method reporting (§4.1)
- TermSpec / ProcessSpec algebra, canonical ordering, canonical serialization + hashing
- Kernel registry (decorator + entry point) and recipe registry, versioned
- Engine-capability and gradient-capability resolution with cost classes
- Parameter counting, both objectives, tested against hand counts
- Identifiability lint
- Families: **white, Matérn ν=1/2, and at least one d>1 family (Matérn ν=3/2 or SHO), plus
  sums.** One family is not enough: with only ν=1/2 the state dimension is 1, so every `d²`
  term in the memory formula is invisible and composition — the central architectural claim
  — is never exercised.
- Exact state-space engine with analytic `F`/`Q`/`P∞`, defective-root guard, masked gaps
- Engine protocol (one implementation)
- Signal spec with the full linear/nonlinear taxonomy; nonlinear terms raise
  `NotImplementedError`; GLS-concentrated linear path with `rank(X)`
- ML and REML objectives; engine + objective tags; comparability guards
- FD gradients; gradient protocol slot; **analytic forward-mode for Matérn ν=1/2** (see
  §18 note); complex-step viability verdict
- Moment initialization ladder; Hessian at optimum
- Failure taxonomy as an enum throughout
- One criterion (AIC) end to end
- `fit()` accepts `x0` — warm-starting is Phase 2, but it constrains the Phase 1 signature
- **The §9.4 memory formula**, validated against measured peak RSS
- Platform RSS shim (§15.3)
- Three-hash machinery (§13.3), with the compat-relevance allowlist and its golden test

**Optimizer scope is decided by the staged spike, not fixed in advance** (§9.2). This is the
largest single lever on Phase 1's size:

| stage | what gets built |
|---|---|
| **Stage 1** (always) | batched Kalman filter in numpy; compiled path B for Matérn ν=1/2 and the d=3 case; path A's optimistic bound measured; gap-structure sweep; write-up against the 19 ms budget |
| **Stage 1 says B wins by ≥3×** | **the batched trust-region is never built.** Path A's permanent form is a plain per-series scipy loop, retained as the reference implementation and the MVN-oracle harness |
| **Stage 1 inconclusive → Stage 2** | full batched trust-region with active masks and compaction, then the original decision rule |

Both branches still require **both paths to sit behind the §7.4 engine protocol** — that is
the spike's real deliverable and it is not conditional.

### Phase 2 — batch orchestration (`metamer.batch`)

Tiling; two-pass hierarchical warm start; hysteresis audit; calibration tile; zarr schema
with region writes, sharding, completion bitmap, resumption; run-level reporting; float32 IO
boundary.

### Phase 3 — model families

Matérn ν free; CARMA(p,q) general with root parameterization; SHO; sum-of-OU power law with
spectrum validation; discrete AR(p)/ARMA (regular sampling only) so the Hughes & Williams
AR(5) result is a one-line config change.

### Phase 4 — inference extras

Debiased Whittle engine and the screening profile; exact Toeplitz path; robust sandwich
variance; TIC; effective-sample-size BIC; multi-model averaging; ΔIC outputs; non-Gaussianity
diagnostic; Student-t via scale-mixture EM; optional MCMC with the large-N warning and
confirmation threshold.

### Phase 5 — CLI and public spectral API

`metamer.cli` with config validation and `--explain`; multitaper (Thomson) spectral
estimator as public API; `metamer report`.

### Phase 6 — validation suites

Simulation-recovery benchmark including the spatial-field hysteresis measurement and the
ML/REML sweep; external cross-validation against Hector / CATS / `est_noise`; README figures.

---

## 18. Phase 1 exit criteria (consolidated)

1. Brute-force MVN agreement at small N, **every Phase 1 family and a sum**
2. `celerite2` agreement on the shared kernel subset — **optional**, Tier-1 platforms where
   importable. **The designated first cut if Phase 1 proves too large** (§16.1): MVN
   validates the state-space construction, which is the bespoke part; celerite2 validates
   the ACF, which is textbook.
3. Masked-gap likelihood identical to the same series with those samples genuinely absent
4. Analytic `F`/`Q`/`P∞` verified against a general `expm`/Lyapunov reference, per family
5. Parameter counting verified against hand-counted values for **both objectives**,
   including profiled-out linear signal parameters
6. Rank-deficient `X` produces the documented failure rather than NaN
7. REML penalty verified against brute-force `log|XᵀΣ⁻¹X|` from an explicitly constructed Σ
   at small N
8. Complex-step viability verdict **recorded with numbers**; fallback oracle adopted if it
   fails
9. FD step rule validated against the oracle at **three values of N** (100, 630, 5000)
10. Gradient-capability resolution tested on a composite where one term lacks analytic
    gradients
11. Hessian at optimum verified against a brute-force FD Hessian at small N
12. **Every** failure-taxonomy branch reachable by a constructed test case
13. Measured peak RSS matching the analytic memory formula at two or three values of B
14. A completed run at **B ≈ 10⁴, N ≈ 630**, with the **stage-1** execution-strategy
    comparison written up: compiled path B measured fully against path A's **optimistic
    bound**. Stage 2 is required only if stage 1 is inconclusive (§9.2). Split by machine,
    because the development machine cannot satisfy the budget clause:
    - **Mini PC {1, 4}** — establishes feasibility, correctness, and the memory formula.
    - **64-core box {1, 4, full}** — **the only machine on which the 19 ms budget
      comparison is valid**, and where the ≥3× decision rule is evaluated.
    - **MacBook {1, full}** — the adversarial case for path A, plus the arm64 smoke test.
    - Reported in **canonical-filter-pass units** as well as raw ms, with the roofline
      pair measured on all three and the model's **prediction error stated** (§9.2).
15. **Gap-structure sweep results** at {0%, 10% scattered, 40% contiguous blocks}, with the
    A:B ratio reported **per gap case** rather than pooled
16. **`fit_hash` / `compat_hash` separation exercised end to end**: a resume that adds a
    criterion recomputes `/selection/` from the stored primitives **without refitting**, and
    a `fit_hash` mismatch is refused

**Note on criterion 10.** It requires at least one family *with* an analytic gradient and one
*without*, which pulls the forward-mode path into Phase 1 rather than deferring it. Resolved
by shipping analytic gradients for **Matérn ν=1/2 only** — genuinely trivial, since
`F = exp(−Δt/ρ)` and its derivatives are one line each — which validates the whole
forward-mode machinery on the simplest case, plus a **test-only stub family** for exercising
the resolution logic itself. This keeps the criterion achievable without making analytic
gradients a per-family Phase 1 obligation.

---

## 19. Deferred items and open questions

### Deferred, with conditions attached

| item | condition on landing |
|---|---|
| Nested-model warm-start chaining within a point | needs its own hysteresis audit — biases toward the nested solution, systematically favouring simpler models |
| Joint signal × noise search | must force `objective=ML`; the guard is already written |
| Top-k storage instead of all-M | only when a candidate set exceeds ~32 |
| Candidate-set extension on an existing store | hash boundary already permits it (§12.8); exposing the workflow is a scoping decision |
| Breakpoint *detection* | explicitly out of scope; must not be silently approximated |
| Windows support | four portability disciplines adopted now; needs a CI leg to be claimed |
| Cython / C backend | swap behind the engine protocol if numba's `nopython` constraints or compile times become binding |
| Multi-node horizontal scaling | needs a tile-claiming mechanism; the completion bitmap is read-modify-write and **not atomic on object stores** (§15.5) |
| Batched trust-region optimizer | built **only** if the stage-1 spike is inconclusive (§9.2) |

### Conditionally settled

**Compiled backend.** numba **if** the §9.2 spike selects path B under the ≥3×-at-d=3 rule.
If path A wins, v1 ships no compiled backend and the protocol slot stays empty. Do **not**
spike Cython/C first — the toolchain cost would contaminate the measurement of the thing
actually being measured.

### Open

- **CI.** Not specified. It determines whether Tier-2 platforms and the optional celerite2
  agreement test are actually exercised, and whether Windows could ever be claimed.
- **Index-space vs area-weighted adjacency** for the §14.2 clustering statistic — index-space
  is the recommendation, but the choice is recorded as not-yet-final.

### Closed since first draft

- **Hardware for the §9.2 spike** — resolved by the one-machine thread-sweep rule (§9.2),
  with the 4-core / 16 GB mini PC as the primary development machine.
- **`n_eff_bic` estimator** — participation-ratio form, §10.1.
- **Criterion 10's pull on analytic gradients** — Matérn ν=1/2 analytic gradients plus a
  test-only stub family (§18 note).

---

## 20. Practicalities

- Package name: **`metamer`** (available on PyPI)
- Licence: Apache-2.0
- Minimum Python: 3.12
- Compiled dependencies acceptable
- `pyproject.toml`, `src/` layout, dependency extras as in §3
- **Do not publish.** No PyPI upload, no GitHub release, no publishing instructions in the
  README or CI. Publication is handled separately.
