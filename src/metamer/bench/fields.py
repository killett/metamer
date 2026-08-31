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

**`easy`, `middle` and `hard` are ALL OURS TO CHOOSE and all say so.** The easy
rung is tuned so the artifact must appear -- it is the positive control, and its
numbers are a floor and a demonstration, never a magnitude. The hard rung probes
the floor from below.

**AND THE MIDDLE RUNG IS THE ONE MOST LIKELY TO BE MISREAD, WHICH IS WHY IT SAYS
SO TWICE.** It occupies the slot a *plausibility* rung would have held, and **a
middle rung on a sweep is exactly where a later reader supplies "plausible" for
free** -- it sits between two extremes, so it reads as the realistic case
without anyone having claimed it is. It is not. Its `sources` say **CHOSEN BY
US** for both parameters, and **every figure drawn from it must carry the same
sentence**; `Rung.sources` is per parameter precisely so that this cannot be
covered by a citation belonging to something else.

**Its `l` and `contrast` are the GEOMETRIC MIDPOINTS of the two shipped rungs**,
computed from them rather than written again, so the three sit on one line by
construction and cannot drift off it. `l` is `sqrt(16 x 6) = 9.80` fine cells --
`1.22 x COARSE_STRIDE`, between the easy rung's `2k` and the hard rung's
`0.75k`, so it is the rung whose coarse neighbour sits *just* inside one
correlation length. `contrast` is `sqrt(3 x 0.75) = 1.5` exactly, making the
three a factor-of-two ladder. **Off that line the three stop being one lever's
curve and become three unrelated settings.**

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

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import xarray as xr
from numpy.typing import NDArray

from metamer.batch.timeaxis import to_decimal_years
from metamer.config.candidates import parse_candidate
from metamer.config.model import WarmStart
from metamer.config.signal_terms import parse_signal_terms
from metamer.core.signal import SignalSpec
from metamer.core.terms import ProcessSpec

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

#: How far the smear estimator's negative control sits from the boundary, in
#: fine cells. **MORE THAN ONE COARSE SPACING**, so no point on the null line
#: can have been warm-started across the step. **THIS IS THE PARAMETER**:
#: `smear.interior_null` takes an offset, because the control is defined by its
#: distance from the boundary and not by where that lands.
NULL_LINE_OFFSET_CELLS: int = 12

#: The index the offset lands on. **DERIVED, NEVER WRITTEN BESIDE THE OFFSET.**
#: Until 2026-08-31 this was the literal `4` with a docstring saying *"12 cells
#: from it"* -- one location spelled as an index and as a distance, which is
#: (j9)'s exact shape and which moving `BOUNDARY_INDEX` would have broken in
#: only one of the two places.
NULL_LINE_INDEX: int = BOUNDARY_INDEX - NULL_LINE_OFFSET_CELLS

#: Index of `sigma` in `BASE` and in `FieldTruth.parameters`.
SIGMA: int = 0

#: The two regimes' families, in `FieldTruth.family` index order. **THE
#: BOUNDARY IS A CHANGE OF FAMILY, NOT A CHANGE OF MAGNITUDE**, taken
#: 2026-08-30 after both of Task 1's field readings were refuted from below.
#: 2c's field changed family across its boundary and its cold arm ran at
#: **40.79 iterations per point** at `N = 630`; the first 2d field changed
#: magnitude inside one family and ran at **14.31**, and at that cost a warm
#: start has nothing to improve. **The constraint is the LIKELIHOOD, not the
#: truth's coherence**: the saving is bounded above by what the cold start
#: leaves on the table.
FAMILY_KINDS: tuple[str, str] = ("matern12", "matern32")

#: **THE SMEAR ESTIMATOR'S SUBJECT IS THE SELECTED CANDIDATE**, not a
#: parameter. Across a change of family the parameter that steps is not the
#: same parameter on both sides, so a width "of sigma" would be a width of
#: different things either side of the boundary. Selection disagreement is
#: §11.2's most interpretable metric, it is per point, and it is the axis D3a
#: and S4 both identified as where the effect lives.
SMEAR_SUBJECT: str = "selected candidate"

#: Peak-to-peak of the smooth within-regime variation, as a fraction of each
#: parameter's base value. `Rung.contrast` is a MULTIPLE of this, which is what
#: gives the contrast a unit -- two rungs would otherwise agree on
#: `contrast = 3` and disagree about what it means.
WITHIN_REGIME_RANGE: float = 0.5

#: Base values, in the order `(sigma, rho, white sigma)`, shared by both
#: families so that the step across the boundary is a change of FAMILY plus
#: whatever magnitude step `Rung.contrast` asks for, and nothing else.
BASE: tuple[float, float, float] = (1.0, 0.8, 0.4)

#: Production record length -- §11.2's threshold applies at no other.
N_TIME: int = 630

#: **`M = 3`, AND BOTH TRUE FAMILIES ARE IN THE SET.** A candidate set that
#: cannot express one of the regimes would make the boundary undetectable by
#: selection, which is now the smear estimator's subject. `M` sets the price
#: AND D9's stratum count -- `3 x M` point strata and `M x 4` cell strata --
#: so it is stated here and recomputed wherever it is used. **Checked at the
#: rebuild: 384 points over 9 point strata is 42.67 members each at uniform
#: occupancy, against the 30 floor**, and 64 if `white` never wins.
CANDIDATES: tuple[str, ...] = ("white", "white + matern12", "white + matern32")

#: The signal, named once. **A second spelling is a second design matrix** --
#: `k_beta` enters the memory formula, the penalty counts and every fit -- and
#: (j9) says a rule against duplication does not prevent duplication. Both the
#: config text and any `SignalSpec` a caller needs are BUILT from this tuple.
SIGNAL_TERMS: tuple[str, ...] = ("constant", "trend")

#: The criteria, named once for the same reason.
CRITERIA: tuple[str, ...] = ("aic",)

_CONFIG_TEMPLATE = """\
data_uri = "{uri}"
variable = "sla"
signal_terms = {signal_terms}
candidates = {candidates}
criteria = {criteria}
"""


def config_text(uri: str) -> str:
    """The benchmark's config, rendered from the single sources above.

    **EVERY QUANTITY HERE HAS EXACTLY ONE SPELLING IN THE TREE** -- (j9),
    promoted after five instances in one sub-phase of two derivations agreeing
    until one moved. The most recent was a harness naming its own candidate
    set while `CANDIDATES` went from two members to three, which measured a
    field at `M = 2` that had been built for `M = 3`.
    """
    return _CONFIG_TEMPLATE.format(
        uri=uri,
        signal_terms=json.dumps(list(SIGNAL_TERMS)),
        candidates=json.dumps(list(CANDIDATES)),
        criteria=json.dumps(list(CRITERIA)),
    )


def signal_spec() -> SignalSpec:
    """The benchmark's `SignalSpec`, parsed from `SIGNAL_TERMS`.

    **Through the shipped parser**, so a caller building a batch by hand and a
    run reading the config cannot disagree about the design matrix.
    """
    return parse_signal_terms(list(SIGNAL_TERMS))


def candidate_specs() -> list[ProcessSpec]:
    """The benchmark's candidate set, parsed from `CANDIDATES`."""
    return [parse_candidate(c) for c in CANDIDATES]


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
        contrast: The **additional magnitude** step across the boundary, as a
            multiple of `WITHIN_REGIME_RANGE`. **The family change is
            unconditional**, so `contrast = 0` is a family change alone and a
            larger value adds a larger sigma step on top. E5's second lever,
            and it keeps the unit it had before the family change: a family
            change has no natural multiple, so `Delta` scales the one quantity
            that still has one.
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


_EASY = Rung(
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
)

_HARD = Rung(
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
)


def _geometric_midpoint(low: float, high: float) -> float:
    """The point midway between two ratio-scale values.

    **GEOMETRIC AND NOT ARITHMETIC, AND THE REASON IS THE QUANTITIES' KIND**,
    not the numbers it happens to produce. `coherence_length` is a LENGTH SCALE
    -- what matters about it is its ratio to `COARSE_STRIDE`, not its
    difference from it -- and `contrast` is already defined as a MULTIPLE of
    `WITHIN_REGIME_RANGE`. Both are ratio-scale, so evenly spaced means evenly
    spaced in the logarithm, and the three rungs are then one lever's curve
    rather than three points that happen to be ordered.
    """
    return float(np.sqrt(low * high))


_MIDDLE = Rung(
    name="middle",
    coherence_length=_geometric_midpoint(
        _HARD.coherence_length, _EASY.coherence_length
    ),
    contrast=_geometric_midpoint(_HARD.contrast, _EASY.contrast),
    sources={
        "coherence_length": (
            "CHOSEN BY US, not sourced: the geometric midpoint of the easy and "
            "hard rungs, 9.80 fine cells. It occupies the slot a plausibility "
            "rung would have held and it is NOT a claim about the ocean -- see "
            "the module docstring for why that rung is not constructible"
        ),
        "contrast": (
            "CHOSEN BY US, not sourced: the geometric midpoint of the easy and "
            "hard rungs, exactly 1.5x the within-regime range, which makes the "
            "three contrasts a factor-of-two ladder 3.0 / 1.5 / 0.75"
        ),
    },
)

#: **ALL THREE RUNGS ARE OURS TO CHOOSE AND ALL THREE SAY SO.** None is a claim
#: about the ocean. See the module docstring for the rung that is missing and
#: why, and for what the middle one is and is not.
RUNGS: Mapping[str, Rung] = {"easy": _EASY, "middle": _MIDDLE, "hard": _HARD}

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
        family: The TRUE family index per point, shape `(N_NORMAL,
            N_PARALLEL)`, indexing `FAMILY_KINDS`. **This is what steps.**
            Across a change of family the parameter that jumps is not the same
            parameter on both sides, so the categorical index is the only
            quantity defined either side of the boundary -- and it is what the
            selected candidate responds to.
        boundary_index: Where the step is, along the normal axis. **A property
            of the field rather than a constant the estimator re-derives** --
            the oracle must not share a derivation path with what it checks.
        t: The time axis, from `to_decimal_years` of the stored coordinate.
        rung: The rung this field is, carried so every number can name it.
    """

    uri: str
    parameters: NDArray[np.float64]
    family: NDArray[np.int8]
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


def _family() -> NDArray[np.int8]:
    """Return the true family index per point, with one transition.

    Region A is `FAMILY_KINDS[1]` and region B is `FAMILY_KINDS[0]`: the
    stiffer family first, matching 2c's field, where all eleven of its
    large-`|dl|` disagreements landed in the stiffest candidate.
    """
    index = np.zeros((N_NORMAL, N_PARALLEL), dtype=np.int8)
    index[:BOUNDARY_INDEX, :] = 1
    return index


_SQRT3 = np.sqrt(3.0)


def _covariance(
    t: NDArray[np.float64], kind: str, sigma: float, rho: float, white: float
) -> NDArray[np.float64]:
    """Textbook Matern covariance plus a white floor, for either family.

    Rasmussen & Williams eq. 4.9 at nu = 1/2 and nu = 3/2, **written here
    rather than imported**: the fixture's only source of truth about the
    families shares no code with `metamer.core.statespace`, so a slip in a
    family's construction cannot cancel between the data and the fit.

    Raises:
        ValueError: If `kind` is not one of `FAMILY_KINDS`.
    """
    d = np.abs(t[:, None] - t[None, :])
    if kind == "matern12":
        correlated = sigma**2 * np.exp(-d / rho)
    elif kind == "matern32":
        correlated = sigma**2 * (1.0 + _SQRT3 * d / rho) * np.exp(-_SQRT3 * d / rho)
    else:
        raise ValueError(f"unknown family {kind!r}; expected one of {FAMILY_KINDS}")
    return np.asarray(correlated + white**2 * np.eye(t.size), dtype=np.float64)


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
    family = _family()

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
            kind = FAMILY_KINDS[int(family[iy, ix])]
            covariance = _covariance(t - t[0], kind, sigma, rho, white)
            generator = np.random.default_rng([seed, iy, ix])
            # **`method="cholesky"` IS NOT A MICRO-OPTIMISATION.** NumPy's
            # default is SVD, measured at **1.85 s per draw** at `N = 630`
            # against **0.209 s** for Cholesky -- 709 s against 80 s to build
            # one 384-point field, and the build was dominating the benchmark
            # rather than the fits. The covariance is positive definite by
            # construction, a Matern kernel plus a white floor, so Cholesky is
            # the correct decomposition and not merely the fast one.
            #
            # **IT CHANGES THE DRAWN BYTES FOR A GIVEN SEED**, because the two
            # decompositions map the standard normals differently. Taken
            # 2026-08-30, while no committed measurement depended on the old
            # bytes; a later change here would invalidate every committed rung
            # report and must be treated as such.
            values[:, iy, ix] = generator.multivariate_normal(
                np.zeros(n_time), covariance, method="cholesky"
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
        family=family,
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
    path.write_text(config_text(uri))
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
