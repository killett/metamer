# metamer

`metamer` fits stochastic noise models to time series and selects among them using
configurable information criteria, after (or jointly with) a user-specified deterministic
signal model. It is designed to work on a single time series and on very large collections
of them — up to 10^7 series, as produced by a global gridded geophysical dataset where
every lat/lon point carries its own series. The scientific payoff is a correctly calibrated
uncertainty on fitted signal parameters, especially linear trends; everything else serves
that.

## Status

**Pre-implementation.** This repository currently contains a design document and a Phase 1
implementation plan. There is no package code yet — no `src/`, no build backend, nothing
installable. The `pixi` environment and tooling configuration are in place so that
implementation can start immediately.

If you are looking for working software, this is not yet that. If you are looking for what
is going to be built and why, start with the design document.

## Where to look

| Document | What it is |
|---|---|
| [`docs/superpowers/specs/2026-08-04-metamer-design.md`](docs/superpowers/specs/2026-08-04-metamer-design.md) | The design. Module boundaries, the public API surface, the likelihood engines, the zarr output schema, the phased implementation plan, and the testing strategy. |
| [`docs/superpowers/plans/2026-08-05-metamer-phase1.md`](docs/superpowers/plans/2026-08-05-metamer-phase1.md) | The Phase 1 implementation plan: twenty tasks building the likelihood spine end to end on arrays. |
| [`PROGRESS.md`](PROGRESS.md) | Current state, cross-cutting decisions, gotchas, and open questions. |
| [`metamer-build-prompt.md`](metamer-build-prompt.md) | The original brief. Superseded by the design document's §2 wherever they conflict. |

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

Three layers, gated by optional dependency extras:

- **`metamer.core`** — numpy/scipy only. Arrays in, results out. No file I/O, no xarray,
  no dask. This is what other projects import, and it must be importable without the rest.
- **`metamer.batch`** (extra `[batch]`) — xarray/dask orchestration, zarr output,
  checkpointing, resumability.
- **`metamer.cli`** (extra `[cli]`) — a config-file-driven runner.

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
pixi run pre-commit-all
```

Python 3.12 or newer.

## Licence

Apache-2.0. See [`LICENSE`](LICENSE).
