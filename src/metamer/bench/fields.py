"""The 2d benchmark field: smooth variation, one step, and the rungs.

Design doc §16.2 item 6 asks for hysteresis measured on simulated **fields**:
*"Generate lat/lon fields where the true noise parameters (i) vary smoothly and
(ii) vary sharply across a boundary, simulate a series at each point, fit warm
and cold. The sharp-boundary case is decisive: warm-starting will smear the
boundary, and the smear width is a direct measurement of the artifact."*

**THIS LIVES IN `src` AND NOT IN A HARNESS, AND THAT IS THE POINT.** Phase 2c's
warm-start spike built a coherent field inside a script that is not in the
tree, so nothing it established transferred to the shipped path and criterion
12 could not be re-measured on the mechanism. **Every 2d field goes through the
ordinary opener, stage 4a, tiling and `fit`.**

**THE BOUNDARY IS A STEP, `w = 0`, AND THAT IS THE DESIGN RATHER THAN A
PARAMETER CHOICE.** At `w > 0` a measured width is a true width plus an
artifact width, so reading the artifact means **subtracting a known quantity
from a measured one** -- which is where an artifact hides. At `w = 0` the whole
measured width **is** artifact and the reading is direct. §16.2 says *"vary
sharply"*; a step is the sharp limit, not an approximation to it. **Recorded
here so that a later proposal to sweep `w` "for realism" meets the argument
rather than a silent constant.** The realism axis is the rung, not the
boundary's width.

## The geometry, which is derived from `k` and not chosen

| axis | size | why |
|---|---|---|
| **normal**, across the boundary | **32 = 4k** | the boundary sits at the **midpoint**, so there are 16 cells either side and an interior profile line can sit **two full coarse spacings** from it -- outside the warm start's coupling range, which is what makes the null-line control real rather than assumed |
| **parallel**, along the boundary | **12** | **NOT a minimum.** At `k = 8` the coarse indices are `0, 8, 16, …`, so **`n = 9` already gives two.** 12 is chosen for two reasons: `32 x 12 = 384` points, which is what gives D9's **six point strata** a chance at **30 members** each; and indices 9-11 lie **beyond the last coarse point**, so they source from **one side only** -- the ordinary case at a real field's edge, which `n = 9` barely exercises |

**"12 is the minimum giving two coarse points" was asserted in four documents
and is false**; it was corrected at Task 1's pre-flight, 2026-08-30, by
multiplying it out.

## The rungs, and the one that does not exist

**`easy` and `hard` are OURS TO CHOOSE and say so.** The easy rung is tuned so
the artifact must appear -- it is the positive control, and its numbers are a
floor and a demonstration, never a magnitude. The hard rung probes the floor
from below.

**THERE IS NO `plausibility` RUNG AND ASKING FOR ONE RAISES.** Its parameters
were to be sourced from published altimetry values, and the parameter that
matters most **cannot be**: `coherence_length` is the spatial coherence of the
fitted **optima**, published values describe the coherence of the **data**, and
Phase 2c's ceiling arm already measured that these differ -- *"the optimum is
far less spatially coherent than the data is."* **The obvious source is not
merely absent, it is contradicted.** Sourcing it means measuring optimum
coherence on a real gridded product, which is the real-data spike that is D1's
named closer.

**A provisional number in that slot would be a claim about the ocean, it would
be quoted as the plausibility rung's, and nothing downstream could tell a
chosen `coherence_length` from a sourced one.** So the value is made
**unavailable** rather than emitted with a caveat -- the (a2b) rule, at the one
slot where an invalid value is a scientific error rather than a placeholder.

**Consequence, stated here because it is easy to lose: 2d quotes no magnitude.**
It establishes that the instrument works and reports a resolution floor.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import xarray as xr
from numpy.typing import NDArray

from metamer.batch.timeaxis import to_decimal_years
from metamer.config.model import WarmStart

#: Pass 1's stride, read from the config default rather than written again.
#: The geometry below is derived from it, so a stride change must move the
#: geometry's justification and not merely disagree with it.
COARSE_STRIDE: int = WarmStart().coarse_stride

#: Cells across the boundary. `4 * COARSE_STRIDE`.
N_NORMAL: int = 4 * COARSE_STRIDE

#: Cells along the boundary. A CHOICE -- see the module docstring.
N_PARALLEL: int = 12

#: The step's position along the normal axis: the **midpoint**, so both regimes
#: are 16 cells deep and an interior line can clear the coupling range on
#: either side.
BOUNDARY_INDEX: int = N_NORMAL // 2

#: Where the smear estimator's negative control is taken -- a line parallel to
#: the boundary and `12` cells from it, which is more than one coarse spacing,
#: so no point on it can have been warm-started across the step.
NULL_LINE_INDEX: int = 4

#: Which parameter the boundary steps in, and which the smear width is a width
#: OF. **"The smear width" is a family of numbers**, so the one being measured
#: is named rather than left to a reduction over an axis that mixes units.
PRIMARY: int = 0

#: Peak-to-peak of the smooth within-regime variation, as a fraction of each
#: parameter's base value. `Rung.contrast` is a MULTIPLE of this, which is what
#: gives the contrast a unit -- two rungs would otherwise agree on
#: `contrast = 3` and disagree about what it means.
WITHIN_REGIME_RANGE: float = 0.5

#: Base values, in the order `(matern12 sigma, matern12 rho, white sigma)`.
#: `PRIMARY` indexes the first.
BASE: tuple[float, float, float] = (1.0, 0.8, 0.4)

#: Production record length -- §11.2's threshold applies at no other.
N_TIME: int = 630

_CONFIG = """\
data_uri = "{uri}"
variable = "sla"
signal_terms = ["constant", "trend"]
candidates = ["white", "white + matern12"]
criteria = ["aic"]
"""


class RungNotConstructible(Exception):
    """A rung whose parameters cannot be sourced, so it is not offered."""


@dataclass(frozen=True)
class Rung:
    """One setting of the sweep, with a source for every parameter.

    Attributes:
        name: The rung's label. **Every number 2d emits carries it**, because a
            floor from a control is not a statement about any other rung.
        coherence_length: The spatial scale, in cells, over which the true
            parameters vary. E5's primary lever: it sets whether a coarse
            source `COARSE_STRIDE` cells away is a good start.
        contrast: The step across the boundary, as a **multiple of
            `WITHIN_REGIME_RANGE`**. E5's second lever: it sets whether the
            boundary is visible at all.
        sources: Provenance **per parameter**, not one string per rung. A
            single rung-level citation covering `contrast` would silently
            appear to cover `coherence_length` too -- and that is the one
            parameter which cannot be sourced, so the one-string design hides
            exactly the gap that matters.

    Raises:
        ValueError: If any parameter has no source. **A source is a
            construction requirement rather than a docstring**, because a rung
            that can be retuned after a null result is not a measurement.
    """

    name: str
    coherence_length: float
    contrast: float
    sources: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Refuse a rung whose parameters do not each carry a source."""
        for parameter in ("coherence_length", "contrast"):
            if not self.sources.get(parameter, "").strip():
                raise ValueError(
                    f"rung {self.name!r} gives no source for {parameter!r}; "
                    "every rung parameter records where its value came from, "
                    "including 'chosen by us, and why'"
                )


#: **BOTH RUNGS ARE OURS TO CHOOSE AND BOTH SAY SO.** Neither is a claim about
#: the ocean. See the module docstring for the rung that is missing and why.
RUNGS: Mapping[str, Rung] = {
    "easy": Rung(
        name="easy",
        coherence_length=16.0,
        contrast=3.0,
        sources={
            "coherence_length": (
                "chosen for detectability: 2x the coarse stride, so a coarse "
                "neighbour is well inside one correlation length and the warm "
                "start has something to exploit"
            ),
            "contrast": (
                "chosen for detectability: 3x the within-regime range, so the "
                "step dominates the smooth variation and the smear estimator "
                "has an edge it can resolve"
            ),
        },
    ),
    "hard": Rung(
        name="hard",
        coherence_length=6.0,
        contrast=0.75,
        sources={
            "coherence_length": (
                "chosen to be hard: below the coarse stride, so a coarse "
                "neighbour lies outside one correlation length and carries "
                "little information about its neighbours' optima"
            ),
            "contrast": (
                "chosen to be hard: below the within-regime range, so the step "
                "does not dominate the smooth variation"
            ),
        },
    ),
}

_NOT_CONSTRUCTIBLE = {
    "plausibility": (
        "the plausibility rung is not constructible. Its `coherence_length` is "
        "the spatial coherence of the fitted OPTIMA; published altimetry "
        "values describe the coherence of the DATA; and Phase 2c's ceiling arm "
        "measured that these differ -- 'the optimum is far less spatially "
        "coherent than the data is'. So the obvious source is contradicted, "
        "not merely absent, and sourcing it means measuring optimum coherence "
        "on a real gridded product, which is the real-data spike that closes "
        "D1. A provisional value here would be a claim about the ocean and "
        "nothing downstream could tell it from a sourced one."
    )
}


def rung(name: str) -> Rung:
    """Return a rung by name.

    Args:
        name: `"easy"` or `"hard"`.

    Returns:
        The rung.

    Raises:
        RungNotConstructible: For a rung that is deliberately absent, with the
            reason. **Silence and absence are the same bytes**, so a rung whose
            omission is a decision says so rather than presenting as a typo.
        KeyError: For a name that is simply not a rung.
    """
    if name in _NOT_CONSTRUCTIBLE:
        raise RungNotConstructible(_NOT_CONSTRUCTIBLE[name])
    return RUNGS[name]


@dataclass(frozen=True)
class FieldTruth:
    """A built field, and the truth the estimator is allowed to know.

    Attributes:
        uri: The written store, for the ordinary opener.
        parameters: The TRUE parameters, shape `(N_NORMAL, N_PARALLEL, 3)`, in
            `BASE`'s order. **This is what the tests assert on**: the builder
            controls the truth, while the fits are what the benchmark is trying
            to move, so asserting on fits would make the oracle a function of
            the thing under test.
        boundary_index: Where the step is, along the normal axis. **A property
            of the field rather than a constant the estimator re-derives** --
            the oracle must not share a derivation path with what it checks.
        t: The time axis, from `to_decimal_years` of the stored coordinate.
        rung: The rung this field is, carried so every number can name it.
    """

    uri: str
    parameters: NDArray[np.float64]
    boundary_index: int
    t: NDArray[np.float64]
    rung: Rung


def _factor(rung_: Rung) -> NDArray[np.float64]:
    """The dimensionless truth: smooth everywhere, one step at the boundary.

    Smooth in **both** axes, with a term in `y` that survives averaging over
    `x` -- a profile taken across the boundary would otherwise have no
    within-regime structure at all, and the null-line control would pass
    vacuously.

    The step is added **after** the smooth part and is a pure indicator, so the
    transition occupies exactly one cell. Adding it before any smoothing is the
    `w > 0` design this module refuses.
    """
    y = np.arange(N_NORMAL, dtype=np.float64)[:, None]
    x = np.arange(N_PARALLEL, dtype=np.float64)[None, :]
    amplitude = WITHIN_REGIME_RANGE / 2.0
    smooth = amplitude * np.sin(2.0 * np.pi * y / rung_.coherence_length) + (
        amplitude * np.cos(2.0 * np.pi * x / rung_.coherence_length)
    )
    step = np.zeros((N_NORMAL, N_PARALLEL), dtype=np.float64)
    step[BOUNDARY_INDEX:, :] = rung_.contrast * WITHIN_REGIME_RANGE
    return 1.0 + smooth + step


def _covariance(
    t: NDArray[np.float64], sigma: float, rho: float, white: float
) -> NDArray[np.float64]:
    """Textbook Matern nu = 1/2 covariance plus a white floor.

    Rasmussen & Williams eq. 4.9 at nu = 1/2, **written here rather than
    imported**: the fixture's only source of truth about the family shares no
    code with `metamer.core.statespace`, so a slip in the family's construction
    cannot cancel between the data and the fit.
    """
    d = np.abs(t[:, None] - t[None, :])
    return np.asarray(
        sigma**2 * np.exp(-d / rho) + white**2 * np.eye(t.size), dtype=np.float64
    )


def build_field(
    rung_: Rung, *, path: Path, n_time: int = N_TIME, seed: int
) -> FieldTruth:
    """Draw the field, write it, and return it with its truth.

    Args:
        rung_: Which rung. Part of the fixture's identity: the same rung and
            seed reproduce the field exactly, and a different rung does not.
        path: Where the store goes.
        n_time: Record length. Defaults to production.
        seed: Base seed. Each point draws from its own generator keyed on its
            grid position, so the field does not depend on traversal order.

    Returns:
        The field and its truth.
    """
    factor = _factor(rung_)
    parameters = factor[:, :, None] * np.asarray(BASE, dtype=np.float64)[None, None, :]

    origin = np.datetime64("2000-01-01")
    stamps = np.array([origin + np.timedelta64(31 * i, "D") for i in range(n_time)])
    # **THE AXIS COMES FROM THE CONVERSION, NEVER FROM ARITHMETIC.** 2c Task 6
    # measured that a hand-built decimal-year axis moves `theta_hat` by 6.7e-05
    # relative, and the conversion is under `ALGORITHM_VERSION`, so a second
    # derivation of it is a second derivation of fit identity. Task 0's own
    # harness shipped this defect and it took two runs to find.
    t = to_decimal_years(stamps)

    values = np.empty((n_time, N_NORMAL, N_PARALLEL), dtype=np.float64)
    for iy in range(N_NORMAL):
        for ix in range(N_PARALLEL):
            sigma, rho, white = parameters[iy, ix]
            covariance = _covariance(t - t[0], sigma, rho, white)
            generator = np.random.default_rng([seed, iy, ix])
            values[:, iy, ix] = generator.multivariate_normal(
                np.zeros(n_time), covariance
            )

    dataset = xr.Dataset(
        {"sla": (("time", "y", "x"), values.astype("float32"))},
        coords={
            "time": stamps,
            "y": np.arange(N_NORMAL, dtype=np.float64),
            "x": np.arange(N_PARALLEL, dtype=np.float64),
        },
    )
    dataset.to_zarr(path)
    return FieldTruth(
        uri=str(path),
        parameters=parameters,
        boundary_index=BOUNDARY_INDEX,
        t=t,
        rung=rung_,
    )


def write_config(directory: Path, name: str, uri: str) -> Path:
    """Write the config a benchmark run reads.

    **One template, so the run and any comparison agree by construction.** A
    second spelling of the candidate set would be a second `M`, and `M` sets
    both the price and D9's stratum count.
    """
    path = directory / name
    path.write_text(_CONFIG.format(uri=uri))
    return path


@dataclass(frozen=True)
class IterationCount:
    """What a field cost, in the unit the budget is built in.

    **THE BUDGET IS IN ITERATIONS AND NOT IN SECONDS**, because iterations are
    deterministic -- Task 0 measured the same fixture returning 405 in every
    one of five repeats -- while the same box's wall clock spread 11% quiet and
    21% loud. This is exit criterion 17's reading.

    Attributes:
        total: Iterations over every fitted cell.
        per_point: `total / points`, which is what the cost model multiplies.
        per_cell: `total / cells`, for comparison with figures quoted per cell.
        points: Points that produced at least one fitted cell.
        cells: Fitted cells.
    """

    total: int
    per_point: float
    per_cell: float
    points: int
    cells: int


def iteration_count(store_path: Path | str) -> IterationCount:
    """Read a finished store's iteration total.

    **Read from the store rather than from a report**, so the number describes
    the run that was written rather than the object a caller happens to hold --
    and so it can be re-read from a committed artifact later, which is what
    lets a 27-hour measurement's criteria be checked at all.
    """
    import zarr

    from metamer.batch.store import ITERATIONS_UNSET

    root = zarr.open_group(str(store_path), mode="r")
    written = root["primitives/iterations"]
    if not isinstance(written, zarr.Array):  # pragma: no cover - store shape
        raise TypeError("primitives/iterations is not an array")
    iterations = np.asarray(written[:])
    live = iterations != ITERATIONS_UNSET
    total = int(iterations[live].sum())
    cells = int(live.sum())
    points = int(live.any(axis=-1).sum()) if live.ndim > 2 else cells
    return IterationCount(
        total=total,
        per_point=total / points if points else 0.0,
        per_cell=total / cells if cells else 0.0,
        points=points,
        cells=cells,
    )
