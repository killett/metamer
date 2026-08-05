# Build `metamer` — a noise-model fitting and selection package

## How to run this task

Start with the **superpowers brainstorming skill**. Do not begin implementation
until brainstorming has produced a design document that I have approved.

Much of the design below is already settled and is not up for renegotiation
during brainstorming — it is the input, not the subject. The section **"Open
questions for brainstorming"** near the end lists what is genuinely undecided.
Focus the brainstorming there, and push back on anything in the settled sections
only if you believe it is actually wrong (in which case say so explicitly and
explain why, rather than quietly designing around it).

Deliverable from brainstorming: a design document covering module boundaries,
public API surface, data structures, the zarr output schema, the compiled-kernel
strategy, and a phased implementation plan. After I approve it, implement in
phases, with tests written alongside each phase rather than at the end.

---

## Mission

`metamer` fits stochastic noise models to time series and selects among them
using configurable information criteria, after (or jointly with) a
user-specified deterministic signal model. It must work on a single time series
and on very large collections of them — up to 10^7 series, as produced by a
global gridded geophysical dataset where every lat/lon point carries its own
series.

The scientific payoff is a correctly calibrated uncertainty on fitted signal
parameters (especially linear trends). Everything else serves that.

## Motivating background — and the defects to fix

The direct ancestor is Hughes & Williams (2010), *The color of sea level:
Importance of spatial variations in spectral shape for assessing the
significance of trends*, J. Geophys. Res. 115, C10048,
doi:10.1029/2010JC006102. They fit AR(p) models to 12 years of weekly gridded
altimetry at every ocean grid point, selected the order by BIC, and used the
result to compute trend uncertainties. Their headline finding: statistical
errors in local trends range from under 1× to over 5× what a white-noise
assumption gives, so spectral shape genuinely matters.

`metamer` exists because that methodology has four fixable defects:

1. **Two-stage estimation.** They fit the signal by OLS, subtracted it, then fit
   noise to the residuals. OLS residuals systematically understate low-frequency
   power because the trend fit absorbs it. This biases the noise model toward
   white, which understates the trend uncertainty — precisely the quantity being
   computed. Joint maximum-likelihood estimation of signal and noise fixes this
   and has been standard in geodesy since well before 2010 (CATS, Hector,
   `est_noise`).
2. **AR(p) is the wrong parameterization.** It is a discrete-time model standing
   in for continuous-time physical processes. That is why they needed five shape
   parameters where a Matérn or CARMA formulation needs two or three. They also
   explicitly noted that AR(5) could not capture the sharp spectral peaks
   present at the shoulder — those peaks are real oscillatory dynamics (tropical
   instability waves, mesoscale eddy shedding) that a damped-oscillator kernel
   represents naturally.
3. **Hard selection.** Per-point BIC selection produced spatially patchy orders,
   so they forced AR(5) everywhere to avoid discontinuities. That patchiness was
   mostly selection *uncertainty*. Information-criterion weights and multi-model
   averaging give spatial smoothness and local flexibility simultaneously.
4. **Data handling.** They linearly interpolated short gaps, discarded series
   with longer ones, and used raw periodograms with no leakage control on
   spectra as steep as σ^-5. A likelihood engine that handles missing data
   natively never needs to interpolate, and multitaper estimation controls the
   leakage.

---

## Settled: package structure

One repository, three layers, gated by optional dependency extras.

- **`metamer.core`** — numpy/scipy only. Arrays in, results out. No file I/O, no
  xarray, no dask. This is what other projects import.
- **`metamer.batch`** (extra `[batch]`) — xarray/dask orchestration, zarr
  output, checkpointing, resumability.
- **`metamer.cli`** (extra `[cli]`) — config-file-driven runner.

`core` must be importable without `batch` or `cli` installed.

### Downstream consumer

`metamer` will be consumed by https://github.com/killett/synesthesia, which
renders the frequency content of gridded time series as colour. Dependency
direction is one-way: synesthesia imports metamer, never the reverse. metamer
must know nothing about NetCDF loaders, CIE colour-matching, cartopy, or GMT.

Two concrete integration requirements:

- Synesthesia currently has a `--fit-terms {constant, trend, accel, annual,
  semiannual}` flag for detrending. Every one of those terms must be expressible
  in metamer's signal specification, so synesthesia can delete its own
  implementation and call metamer instead.
- metamer must export a **multitaper (Thomson) spectral estimator** as public
  API. Synesthesia currently takes a raw NFFT periodogram with no band
  averaging; on σ^-5 spectra the leakage is severe, and this replaces it.

---

## Settled: continuous-time formulation

Irregular sampling is first-class, not an afterthought. Use continuous-time
state-space formulations (CARMA / Matérn / Gaussian-process kernels) as the
primary representation. Discrete ARMA is a secondary, regular-sampling-only
family retained for direct comparison with Hughes & Williams.

Two performance facts that should shape the implementation:

- **Assume a shared time axis in the fast path.** All series in a batch share
  one time vector. Since the CARMA transition matrix is `expm(A·Δt)` and the
  process-noise covariance requires a Lyapunov solve per Δt, a shared axis means
  those are computed **once per (model, parameter vector, timestep)** and
  broadcast across the whole batch. On a regular grid there is a single Δt, so
  it is one `expm` for the entire filter pass. Memoize on unique Δt values.
- **Gaps do not break the fast path.** Mask the Kalman update and keep the
  prediction step. A gridded product with sea-ice dropouts stays on the fast
  path. **Never interpolate to fill gaps.**

The ragged case (e.g. a tide-gauge collection with genuinely different
timestamps per station) is a supported fallback that loses the shared-Δt
amortization. It is a performance *cliff*, not a slope — it must log a
prominent warning, not degrade silently.

## Settled: model families

- White (measurement) noise
- Matérn: ν = 1/2 (Ornstein–Uhlenbeck, the continuous AR(1)), 3/2, 5/2, and ν free
- CARMA(p,q), general
- Damped harmonic oscillator (SHO)
- **Additive compositions of the above** — the realistic model for sea level is
  something like white + Matérn + one or two oscillators. Composition should be
  a first-class API concept (kernel algebra), not a fixed enumeration of named
  models.
- Power-law family: flicker, random walk, general power-law with estimated
  spectral index, white-plus-power-law mixtures, Generalized Gauss-Markov
- ARFIMA / long-memory
- Discrete AR(p) / ARMA — optional, regular sampling only, retained so that the
  Hughes & Williams AR(5) result is reproducible as a one-line config change

### Power-law: two paths, both required

Exact fractional noise has no finite-dimensional state-space representation.

- **Default: sum-of-OU (Markovian) approximation.** Represent the power law as a
  superposition of OU processes fitted to the target spectrum. Component count
  and frequency band are documented, user-facing parameters. This keeps
  power-law models inside the same likelihood engine as everything else, so
  information criteria stay comparable. **Required validation test:** the
  approximation reproduces the target spectrum to a stated tolerance across the
  stated band.
- **Also required: an exact power-law path** (e.g. exact Toeplitz likelihood),
  opt-in, single-series scale. This is not optional polish — it exists so that
  results can be **cross-validated against published geodesy results from
  Hector, CATS, and `est_noise`**. Without it, any discrepancy against those
  packages is unattributable: approximation error and implementation bug look
  identical. Build reproduction of at least one published benchmark from that
  literature into the validation suite.

## Settled: likelihood engines and the comparability guard

- **Batched Kalman filter** — the workhorse. Exact, O(N), vectorized across the
  series axis, masked updates for gaps.
- **`celerite2`** — exact O(N) for sums of exponential and SHO kernels; MIT
  licence, compatible with Apache-2.0. Use as the single-series reference
  implementation. **Make "the batched Kalman and celerite2 agree to near machine
  precision on identical input" a headline test.**
- **Debiased Whittle** (Sykulski et al. 2019) — O(N log N), for the cheap
  screening pass.
- **Exact Toeplitz** — for the exact power-law path.

**Comparability guard (important).** A Whittle score is not an exact likelihood
and lives on a different scale than a Kalman one. Every score must be tagged
with the engine that produced it, and the comparison/selection layer must
**refuse** to rank scores across engines. This is a silent-failure mode that
produces plausible-looking but wrong maps; make it a hard error, not a warning.

## Settled: signal model

Supported terms:

- Polynomial: constant, linear trend, acceleration, arbitrary order
- Harmonics: annual, semiannual, arbitrary specified periods (deterministic
  amplitude for now — see the seam note below)
- Offsets / jumps at **user-supplied** epochs
- Piecewise-linear rate changes at **user-supplied** epochs
- Exponential and logarithmic decays
- External regressors, in two distinct plumbing cases:
  - a scalar index (e.g. ENSO) broadcast identically to all series
  - a per-point field (e.g. a GIA model) that must be chunked and spatially
    aligned alongside the data

**Fast and slow paths.** Polynomials, harmonics, offsets, rate changes, and
regressors are all *linear in their parameters*, so they can be profiled out
analytically via GLS at each noise-parameter evaluation — the optimizer then
searches only the noise parameters (typically 2–6 dimensions). Exponential and
log decays are *nonlinear* in the timescale and break this. Implement both a
concentrated-likelihood fast path for linear-only signal models and a general
joint-optimization path, dispatched automatically, with the choice logged so
users understand when they have left the fast lane.

**Document the offset/random-walk confound.** An undetected offset is nearly
indistinguishable from random-walk noise — a well-known trap in GNSS trend
estimation. Breakpoint epochs are user-supplied in v1; breakpoint *detection* is
explicitly out of scope and must not be silently approximated.

**Seam for future work.** In v1 the user fixes the signal specification and only
the noise model is selected. Design the selection layer so that a future version
can search over signal × noise jointly — i.e. the candidate set should be a
product space in the abstraction even though v1 only ever varies one factor.

## Settled: selection criteria and model averaging

- Criteria: AIC, AICc, BIC, HQIC, **TIC**, and cross-validation with
  blocked / rolling-origin splits. User-configurable.
- **TIC matters specifically because of the robust-variance option.** AIC's
  penalty is only correct under correct specification, which sandwich estimation
  concedes you do not have; TIC is the sandwich-corrected AIC and keeps the
  robust path internally consistent.
- Offer a BIC variant using an **effective sample size**: the standard `n`
  penalty assumes independent observations, and with strongly correlated
  residuals the effective count is much smaller, making the usual penalty too
  harsh.
- **Information-criterion weights** (Akaike / Schwarz) and **multi-model
  averaging** of parameters and their uncertainties. This is the principled fix
  for the spatial patchiness that forced Hughes & Williams into a global AR(5).
- **ΔIC to next-best is a first-class output.** A selection map without a
  confidence measure is misleading.

## Settled: distributional assumptions

- Gaussian likelihood as the simple default.
- **Robust sandwich variance estimators** for parameter covariance (pairs with
  TIC above).
- **Student-t option.** Note this breaks the linear-Gaussian state space; the
  cleanest route is a scale-mixture representation with EM, keeping a Gaussian
  filter in the inner loop at the cost of an outer iteration. It is meaningfully
  more expensive than a flag flip and should be documented as such.
- Provide a non-Gaussianity diagnostic (skewness / kurtosis of standardized
  residuals) so users know when the default is inappropriate — sea-surface-height
  anomalies commonly show skewness in the range −2 to +2.

## Settled: MCMC

Support optional MCMC (e.g. `emcee` with `celerite2`) as a user-configurable
alternative to ML point estimation, for single-series and small-collection work.
Warn when it is requested for a large number of series, and require explicit
confirmation above a higher threshold. It is meaningless at 10^7.

## Settled: batch execution and memory

**Target:** a full 10^7-series run overnight on a 64-core node. **Hard
constraint:** the same job must *run at all*, however slowly, on a 16 GB laptop.
Memory scalability is the binding requirement; speed is the goal.

Adopt and generalize the tiling pattern already used in synesthesia's
`timeseries2color.py`:

- Rechunk along time only. Spatial rechunking creates one dask task per
  (time chunk × lat tile × lon tile), which on a large archive consumes
  gigabytes of graph state by itself.
- Derive a square spatial tile from a byte budget:
  `tile_side = sqrt(block_bytes / (n_time * itemsize))`.
- Outer Python loop over tiles; materialize one tile at a time. Peak RAM is one
  tile plus one dask chunk.
- Keep a hard cap on total dask graph chunks as a guard.

Two changes from synesthesia's version:

1. **The tile is the batch.** Synesthesia loops over pixels inside each tile.
   Here that inner loop must vanish into vectorized array operations — the
   batched Kalman advances all `tile_side²` series through time together.
2. **The memory multiplier is no longer 1.** Beyond the data tile (now float64,
   so 2× synesthesia's float32) you carry a validity mask, Kalman state means
   and covariances (B×d and B×d², d ≲ 6), residual and workspace copies, and
   possibly gradient buffers scaled by parameter count. Rather than hardcode a
   constant, implement a **calibration tile**: fit one small tile at startup,
   measure peak RSS, derive true bytes-per-series for this dataset and model
   set, and size all subsequent tiles from it.

Expose a single `--memory-budget` in GB as the primary knob (defaulting to a
fraction of detected free RAM), with byte-level manual overrides retained.

Additional performance requirements:

- **Spatial warm-starting.** Neighbouring grid points have similar spectra —
  that is the entire premise of the colour maps. Initialize each point's
  optimizer from a converged neighbour rather than cold-starting. Process in a
  locality-preserving order within each tile.
- **Screening pass.** Optionally use debiased Whittle across all points to rank
  candidates cheaply, then run exact MLE only on the top few. Configurable as a
  profile. (Respect the comparability guard: screening scores must not be
  compared against final scores.)
- Compiled kernels are acceptable and probably necessary for the filter inner
  loop.

## Settled: output

- **Full grid:** selected-model parameters and uncertainties, IC weights, ΔIC to
  next-best, top-k model scores, convergence flags.
- **Configurable subsample or region:** complete per-model diagnostics including
  full parameter covariances.
- Zarr output with region writes and a completion bitmap for **resumability** —
  an interrupted 10^7 run must restart without redoing finished tiles.
- Record provenance in zarr attributes: config hash, package versions, random
  seeds, metamer version.
- Non-convergence and numerical failure must be represented explicitly in the
  output, never silently as a plausible-looking fit.

---

## Testing

Keep two suites strictly separate. Conflating them yields a suite that is both
slow and flaky.

### 1. Unit tests — fast, seeded, deterministic

**Use the `test-design` skill for these, and follow it.** In particular: present
the test plan before writing any test code, and for each proposed test state the
behaviour under test, a concrete bug that would make it fail, and how the
expected value was determined independently of the implementation. Drop any test
for which you cannot write that sentence.

High-value targets, determined independently of the code under test:

- Kalman log-likelihood against a brute-force multivariate-normal evaluation at
  small N with an explicitly constructed covariance matrix
- Batched Kalman vs. `celerite2` on identical input
- Known analytic autocovariance for OU / Matérn ν=1/2
- Sum-of-OU power-law approximation vs. its target spectrum, to the stated
  tolerance
- GLS profiling vs. explicit generalized-least-squares inversion
- Design-matrix construction for every signal term, including boundary cases
  (offset at the first/last sample, zero-length segments)
- Gap masking: a series with masked points must give the same likelihood as the
  same series with those points genuinely absent
- The engine-comparability guard actually raises
- Reproducibility under a fixed seed, including with warm-starting enabled

### 2. Simulation-recovery benchmark — slow, stochastic, tolerance-banded

A first-class component, not an afterthought. Run on demand, and in CI only at
small N. Simulate from known models and measure:

1. **Selection accuracy** — confusion matrices across model families as a
   function of series length, SNR, sampling rate, and gap fraction, for each
   available criterion. The flicker / AR(1) / GGM triangle is the headline: the
   honest result is likely "these are not separable below some N," and that is
   exactly what users need told.
2. **Parameter recovery** — bias and RMSE per family.
3. **Trend-uncertainty calibration** — empirical coverage of nominal 95%
   intervals under (i) the true model, (ii) the selected model, (iii) the
   model-averaged estimate. *This is the most important number the package
   produces*, since it validates the actual downstream claim.
4. **Misspecification** — simulate a series containing an undetected offset and
   record which noise model wins. Put the resulting figure in the README.

The benchmark should emit a reproducible report. Knowing the framework's
discrimination limits is as valuable as its point estimates.

### 3. External cross-validation

Reproduce at least one published result from Hector, CATS, or `est_noise` using
the exact power-law path, as a regression test against the geodesy literature.

---

## Open questions for brainstorming

These are genuinely undecided. Interrogate them:

- **API shape:** kernel algebra with composable terms vs. a registry of named
  models. The compositional requirement pushes toward the former; ergonomics and
  discoverability may push back.
- **Constrained parameterization:** CARMA stationarity requires all AR roots in
  the left half-plane, and several parameters are positivity-constrained. What
  reparameterization keeps the optimizer unconstrained and well-conditioned?
- **Optimizer choice**, and whether analytic gradients are worth implementing
  versus finite differences or autodiff.
- **Compiled backend:** Numba vs. Cython vs. a small C extension. Weigh build
  and wheel complexity against speed.
- **Concrete expression of the signal × noise seam** — how to make the candidate
  set a product space without over-engineering v1.
- **Zarr schema design** for ragged per-model output with variable parameter
  counts across families.
- **Config format** and validation approach.
- **Interaction of warm-starting with reproducibility** — warm starts make
  results depend on traversal order. Is that acceptable, and how is it recorded?
- **Failure taxonomy:** what distinguishes non-convergence, singular covariance,
  insufficient data, and rejected series, and how each surfaces in the output.
- **Calibration tile:** per-run, or cached across runs keyed on dataset and model
  set?

---

## Practicalities

- Package name: **`metamer`** (confirmed available on PyPI)
- Licence: Apache-2.0
- Minimum Python: 3.12 (matching synesthesia)
- Compiled dependencies are acceptable
- Modern packaging: `pyproject.toml`, `src/` layout, dependency extras as
  described above
- **Do not publish.** No PyPI upload, no GitHub release, no publishing
  instructions in the README or CI. Publication is handled separately.
