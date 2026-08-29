# metamer

`metamer` fits stochastic noise models to time series and selects among them using
configurable information criteria, after (or jointly with) a user-specified deterministic
signal model. It is designed to work on a single time series and on very large collections
of them — up to 10^7 series, as produced by a global gridded geophysical dataset where
every lat/lon point carries its own series. The scientific payoff is a correctly calibrated
uncertainty on fitted signal parameters, especially linear trends; everything else serves
that.

## Status

**Alpha — Phase 1 and Phase 2a/2b complete; Phase 2c in progress.**

`metamer.core` is the likelihood spine, end to end. A `ProcessSpec` goes in; a scored,
ranked, per-series result comes out. That covers the state-space representation, the
Kalman and compiled likelihood engines, the Matérn ν=1/2 and ν=3/2 and white-noise
families, the differentiable objective with an adopted gradient oracle, the information
criteria, and the comparability guards that refuse to rank scores which are not on the
same footing.

`metamer.batch` is the orchestration layer: the config model and its three hashes, the
input contract, the geometry fingerprint, the memory budget and the tiling derived from
it, the zarr store, the completion bitmap, resumption, and — since Phase 2c — the
two-pass warm start described under [Usage](#usage). `python -m metamer` drives it.

`metamer.bench` also ships: the benchmark harness used to pick the evaluation path.

1174 tests, `mypy --strict`.

**Not yet built:** `metamer.cli` as a command tree. `python -m metamer` is a deliberately
provisional entry point — naming a subcommand would design the argument structure before
`validate` and `report` are real. There are no `[batch]` or `[cli]` extras to install
yet; the batch layer's dependencies (xarray, zarr) are not gated.

The API is alpha and may change without a deprecation cycle before 1.0.

## Installation

```
pip install metamer
```

Python 3.12 or newer. Runtime dependencies are numpy, scipy, numba, and psutil.

To run the test suite you also need the `test` extra, which adds pytest and celerite2 —
the latter is an independent oracle the Matérn ν=1/2 likelihood is checked against:

```
pip install "metamer[test]"
```

## Usage

A run is a config file and a store path:

```
python -m metamer config.toml out.zarr
```

The store is resumable: the same command after an interruption skips the tiles whose
completion bits are set and finishes the rest, bit for bit as an uninterrupted run would.
Peak RAM is derived from `memory_budget_gb` (or `--memory-budget`) alone, and the output
does not depend on it.

### The two-pass warm start

```
python -m metamer config.toml out.zarr --two-pass
```

Pass 1 fits a coarse grid — every `warm_start.coarse_stride`-th point on both spatial
axes — from a cold start. Pass 2 then fits **every** point of the full grid, each one
warm-started from its nearest valid coarse fit. On a simulated field this cut iterations
substantially; on real altimetry it has not been measured, and the saving is a ceiling
rather than an estimate.

**Pass 1's store is written beside the output**, with `.pass1` inserted before the
extension: `out.zarr` gives `out.pass1.zarr`.

> **IT IS A PERMANENT ARTIFACT AND NOT SCRATCH. DO NOT DELETE IT WHEN PASS 2
> COMPLETES.** It holds cold fits of the coarse points, and it is the **only** record of
> what those points fit to without a warm start. Deleting it does not free a cache; it
> discards a measurement that cannot be recovered without refitting.
>
> **IT IS THE AUDIT'S CROSS-CHECK, NOT THE AUDIT'S SAMPLE** — this paragraph used to say it
> was *"the sole reference the hysteresis audit can compare against"*, which is wrong.
> **A coarse point's nearest valid source is itself**, so pass 2's warm fit there starts from
> pass 1's own optimum for the same series and the same candidate: comparing them asks whether
> restarting the optimizer from its own optimum moves it, which is convergence idempotence and
> not hysteresis. **The audit draws FINE points and computes its own cold arm.** Pass 1's store
> is what that cold arm is checked against — a freshly computed cold fit at a coarse point must
> reproduce the stored one bitwise — which is why the store still must not be deleted.

Setting `warm_start.enabled = false` makes `--two-pass` a single cold pass: no coarse
store is written, and the output is what a plain run produces. The setting is part of the
fit identity, so a store fitted with warm starts and one fitted without do not share a
`fit_hash` and neither resumes the other.

## Where to look

| Document | What it is |
|---|---|
| [`docs/superpowers/specs/2026-08-04-metamer-design.md`](docs/superpowers/specs/2026-08-04-metamer-design.md) | The design. Module boundaries, the public API surface, the likelihood engines, the zarr output schema, the phased implementation plan, and the testing strategy. |
| [`docs/superpowers/plans/2026-08-05-metamer-phase1.md`](docs/superpowers/plans/2026-08-05-metamer-phase1.md) | The Phase 1 implementation plan: twenty tasks building the likelihood spine end to end on arrays. |
| [`docs/superpowers/plans/2026-08-24-metamer-phase2c.md`](docs/superpowers/plans/2026-08-24-metamer-phase2c.md) | The Phase 2c plan: the two-pass warm start, its barrier, and the hysteresis audit. |
| [`docs/superpowers/notes/phase1-to-phase2-handoff.md`](docs/superpowers/notes/phase1-to-phase2-handoff.md) | The pre-flight — the audit run against every implementation brief before code, and the standing rules. The most reusable thing here. |
| [`PROGRESS.md`](PROGRESS.md) | Current state, cross-cutting decisions, gotchas, and open questions. |
| [`docs/phase1-prompt.md`](docs/phase1-prompt.md) | The original brief. Superseded by the design document's §2 wherever they conflict. |

## Background

The direct ancestor is Hughes & Williams (2010), *The color of sea level: Importance of
spatial variations in spectral shape for assessing the significance of trends*,
J. Geophys. Res. 115, C10048, [doi:10.1029/2010JC006102](https://doi.org/10.1029/2010JC006102).
That work fitted AR(p) models to weekly gridded altimetry at every ocean grid point,
selected the order by BIC, and used the result to compute trend uncertainties — finding
that statistical errors in local trends range from under 1× to over 5× what a white-noise
assumption gives.

`metamer` sets out to address four limitations of that methodology: two-stage estimation
of signal then noise, AR(p) as a discrete-time stand-in for continuous-time processes, hard
per-point model selection, and gap handling by interpolation. The design document sets out
the approach in detail.

## Planned structure

Three layers, gated by optional dependency extras. **The first two exist today**; the
extras themselves do not exist yet, so nothing is actually gated.

- **`metamer.core`** — *implemented.* numpy/scipy/numba. Arrays in, results out. No file
  I/O, no xarray, no dask. This is what other projects import, and it must be importable
  without the rest.
- **`metamer.batch`** — *implemented* (extra `[batch]` planned). xarray orchestration,
  zarr output, checkpointing, resumability, and the two-pass warm start.
- **`metamer.cli`** (planned, extra `[cli]`) — a config-file-driven runner with a command
  tree. `python -m metamer` is today's provisional stand-in.

`metamer` is consumed by [synesthesia](https://github.com/killett/synesthesia), which
renders the frequency content of gridded time series as colour. The dependency runs one
way: synesthesia imports metamer, never the reverse.

## Development

Dependencies are managed with [pixi](https://pixi.sh/). All tooling runs through it:

```
pixi install
```

```
pixi run test
```

```
pixi run lint
```

```
pixi run typecheck
```

```
pixi run pre-commit run --all-files
```

Python 3.12 or newer.

Releases are tag-driven — see [`RELEASING.md`](RELEASING.md).

## Licence

Apache-2.0. See [`LICENSE`](LICENSE).
