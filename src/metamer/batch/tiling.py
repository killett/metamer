"""Tiling: the grid, the assembly, and read amplification.

**THE TILE IS THE BATCH.** No inner loop over pixels — the batched engine
advances all `tile_side**2` series together, and `B = 1` is a shape rather than a
code path.

**PARALLELISM IS WITHIN A TILE, OVER SERIES, NEVER ACROSS TILES.** Both engines
already work this way and it is written here because **across-tile parallelism is
the obvious later optimization and it multiplies peak RAM by thread count**,
silently breaking the 16 GB constraint. Within-tile parallelism is what makes
peak RAM independent of core count, and hence what lets the same job run on 4
cores and on 64. The general form, stronger than the ban and design doc §11.1.1's
own words:

> **Peak RAM must be derivable from the memory budget alone.** Any concurrency
> whose degree is set by core count, thread count or worker count reintroduces
> the dependency, **regardless of which subsystem hosts it.**

**PREFETCHING TILE `N+1` DURING TILE `N`'s FIT IS DEFERRED, AND ITS COST IS THAT
IT DOUBLES THE TILE TERM IN THE MEMORY FORMULA.** It arrives with a formula
update or it does not arrive. It is not merely documented: `ThreadBudget.phase`
raises when assemble and fit overlap, so the first attempt fails a test rather
than silently doubling peak RAM.

**NO DASK.** A tile is `isel(...).load()` against zarr and zarr does the chunk
reads. `.load()`'s peak is analytic where a graph's is emergent, which is what
lets 2b's calibration tile turn the memory formula from a model into a
measurement.

**A TILE SIDE IS NOT A NUMBER WITHOUT ITS PRECONDITIONS, AND THIS DOCSTRING
STATES NEITHER.** Both live in `PUBLISHED_TILE_SIDE` below — the value, the
budget, the pinned floor and what was open when it was measured, the headroom,
the base, §9.4's model, and the dispute the per-series cost is currently under.
**It is a value rather than a paragraph so that a test can recompute it**, which
is exit criterion 16 and the only durable end to this cascade: `tile_side` has
been wrong four times and every correction was found by a reader.

This file carried ~~347 shared / 187 per-point~~ until 2026-08-15, which was
Task 0's corrected per-series cost divided into the **whole** budget — the
defect F1 names, and Task 2 fixed. **A second copy here is how the two came to
disagree**, and the source docstring is the half a documentation sweep misses:
this is the position §11.1 held while it carried the superseded 445.

**AND THE SIDE NO LONGER CARRIES A BACKEND**, which is the visible half of the
correction: the two engines' published pairs differed only because the formula
charged one live solver working set to every series. `fit` runs one series at a
time, so the per-series cost is the data tile plus the output slots — neither of
which knows which engine is running — and the placement moves a **constant**.
~~`NUMPY_BATCHED` gives 338 / 186 and `COMPILED` gives 361 / 189~~, struck
2026-08-14.

**THE BUDGET'S UNIT IS SETTLED: `memory_budget_gb` IS 10⁹ BYTES.** It was
`1024**3` in `run.py` until Phase 2b Task 2 — 7.4% more bytes for the same word
— and correcting it LOWERS the budget, which is the safe direction against a
constraint the design doc calls hard. The field is named `_gb` and SI GB is
10⁹; a `1024**3` field is named `_gib`. **The value itself is resolved at run**
since Task 3: a config that omits it is distinguishable from one that names a
number, and the omission resolves to a fraction of TOTAL RAM.

**FORWARD NOTE — PASS 1's COARSE STRIDE LANDS HERE IN 2c AND HAS FIVE DOWNSTREAM
CONSUMERS.** 2a defines no stride. Nowhere else records the list, so a later
change to the stride or its membership has one place to look:

    1  the coarse warm-start source                              §11.1
    2  the calibration-tile RSS measurement                      §11.4
    3  the early-abort evaluation, stratified by construction    §14.1
    4  the COLD reference for the hysteresis audit               §11.2
    5  the default `/detail/` subsample, wanting cold-fit points §12.2
"""

from __future__ import annotations

import math
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

from metamer.batch.input import InputContractError, InputHandle
from metamer.batch.store import TILE_SIDE_BASE
from metamer.core.memory import (
    HEADROOM_FRACTION,
    FloorReport,
    SolverPlacement,
    resident_bytes_per_series,
    solver_state_bytes,
    tile_side,
)


@dataclass(frozen=True)
class DisputedHypothesis:
    """One reading of the per-series cost, and the side it derives.

    Attributes:
        per_series_bytes: The per-series cost this reading implies at the
            published model.
        side: The shared-design tile side it derives, recomputed by
            `tests/test_tiling.py` rather than transcribed.
        basis: Where the number comes from, in one line.
    """

    per_series_bytes: float
    side: int
    basis: str


@dataclass(frozen=True)
class PerSeriesDispute:
    """The unsettled per-series cost under the published side, as a value.

    **THIS IS A FIELD RATHER THAN A PARAGRAPH BECAUSE A CAVEAT MUST NOT OUTLIVE
    ITS SUBJECT.** A number published with its caveat is honest; a caveat still
    attached after its subject is settled is (a6) -- a description of something
    that no longer exists, unfalsifiable because nothing exercises it, which is
    what `Backend` was. Every number here is recomputed by a test, so the task
    that settles this deletes the field in the edit that moves the value, or the
    suite fails.

    > **THE SUBJECT CHANGED AT PHASE 2b TASK 8b AND THE FIELDS CHANGED WITH IT.**
    > It used to be *"two instruments disagree by 1.86x"* -- Task 7's 1021.6 +/-
    > 134.7 against Task 8's 1900.9 +/- 84.1. **That is settled: both are
    > underestimates and the mechanism is the same one in both.** Each ladder's
    > run length grew with its own abscissa, from 45.6 s to 1780.1 s in Task 8's
    > case, and a long run under memory pressure loses working set and takes its
    > watermark down with it. Restricted to the points its run length cannot have
    > damaged -- the three under 440 s -- **Task 8's own ladder gives 2584.3 +/-
    > 127.0**, and a duration-controlled ladder at the same fixture and the same
    > three sides gives **2574.9 +/- 236.1**. Two independent lines, 0.4% apart.
    >
    > **SO WHAT REMAINS IS NOT A DISAGREEMENT, IT IS AN UNMODELLED GAP**, and it
    > is why no term has moved: the ratio of measured peak to the analytic
    > formula is **not a constant of the code**. Measured at three fixtures it is
    > 1.888, 2.603 and 3.850, so a multiplier is the wrong SHAPE of correction
    > and fitting one to a fixture is (a7) and F5 exactly.

    Attributes:
        owner: Who owns what is left. **Not the same question 8a and 8b were
            given** -- the instrument question is closed and the shape of the
            correction is what is open.
        analytic_bytes_per_series: What the formula predicts at the ladder
            fixture -- **not** at the published model.
        measured_bytes_per_series: The duration-controlled ladder's peak slope
            at that fixture, over fifteen points at five sides.
        measured_standard_error: Its standard error. **1.9% relative, against
            Task 8's 4.4% and Task 7's 13.2%**, because holding run length
            constant removes the variable that was moving the long points.
        ladder_fixture: The configuration every figure here belongs to, and the
            controls it was taken under. A slope without them is not a number.
        resident_at_tile_bytes_per_series: What the process still HOLDS at the
            end of the tile, with the block alive. The peak's excess over this
            is transient by construction.
        transient_bytes_per_series: **MEASURED, not bounded.** Task 8a inferred
            `<= 152` from one contaminated run's `peak - current_end`; measured
            at this fixture it is 905.9, so that bound does not hold and the
            headroom explanation is back in play as a *partial* one.
        peak_to_analytic_by_fixture: The ratio at each fixture measured, keyed
            by `N=<n_time> M=<n_models>`. **The reason no correction has
            landed**: three values spanning 2x say the gap is not a multiplier.
        headroom_fraction_required: What `HEADROOM_FRACTION` would have to
            become for the measured peak to sit inside the budget as B grows.
            Derived from the two slopes so it cannot drift from them.
        hypotheses: The readings that remain live, by name.
    """

    owner: str
    analytic_bytes_per_series: float
    measured_bytes_per_series: float
    measured_standard_error: float
    ladder_fixture: str
    resident_at_tile_bytes_per_series: float
    transient_bytes_per_series: float
    peak_to_analytic_by_fixture: Mapping[str, float]
    headroom_fraction_required: float
    hypotheses: Mapping[str, DisputedHypothesis]


@dataclass(frozen=True)
class PublishedTileSide:
    """The published tile side, its preconditions, and its dispute, once.

    **THE NUMBER LIVES HERE AND NOWHERE ELSE, AND THAT IS THE POINT OF THE
    TYPE.** `tile_side` has been wrong four times -- 171 through Phase 1, 338
    from 2026-08-10, 347 after Task 0 corrected the per-series formula, and 272
    since Task 2 stopped treating the budget as the block -- and every
    correction had to chase four documents, five source docstrings and a dozen
    test assertions, because each of them held its own copy. **A set of
    consistent copies is the wrong repair.** Documents point at this record;
    `tests/test_tiling.py` recomputes it from `tile_side_for`, so the next
    correction fails a test instead of orphaning a paragraph.

    **AND A SIDE IS NOT A NUMBER WITHOUT ITS PRECONDITIONS**, which is why they
    are fields and not prose. `arguments` is bound against `tile_side_for`'s
    signature by a test: a parameter added with a default would otherwise move
    the published number with nothing to see it, which is how 338 came to be
    quoted with no backend attached.

    **THE FLOOR IS THE ONLY PRECONDITION THAT IS A MEASUREMENT, AND IT IS
    INPUT-DEPENDENT.** `measure_floor` takes a `data_uri`, so the floor a run
    derives depends on the store it opens: measured 2026-08-17 on the
    development machine at 0.0000 ms/s of full stall, opening a 60x160x160
    input gave 228.61 MB and a 630x64x64 input gave 229.89 MB -- 1.28 MB apart,
    eleven times the 0.11 MB within-fixture span. **So a pinned floor needs its
    input beside it or it is not reproducible**, and `floor_basis` carries it.

    Attributes:
        budget_bytes: The resolved budget. **SI, 10**9 B**, not `1024**3`.
        floor: The pinned process floor, measured with the input open.
        floor_basis: What was open when the floor was measured, and when.
        d: Composite state dimension. Reaches the arithmetic only through the
            solver constant, which is why it is not in `per_series_model`.
        k_beta: Design columns.
        p_max: Widest candidate's free noise parameter count.
        n_time: Series length.
        n_models: Candidates held until the tile is written.
        placement: The one reachable placement.
        threads: Ignored under that placement, and named anyway because it is a
            parameter of the function that derives the number.
        headroom_fraction: **A LITERAL, NOT A READ OF
            `memory.HEADROOM_FRACTION`**, checked against it by a test. Reading
            the constant here would make that test compare a value with itself
            -- the shape of an oracle sharing its subject's derivation path (j)
            -- and a change to the headroom would move the published side with
            nothing to say so.
        smooth_base: A literal pin of `store.TILE_SIDE_BASE`, same reason.
        shared: The published side with a shared design.
        per_point: The published side with a per-point design.
        dispute: The live disagreement about the per-series cost, or None once
            it is settled.
    """

    budget_bytes: int
    floor: FloorReport
    floor_basis: str
    d: int
    k_beta: int
    p_max: int
    n_time: int
    n_models: int
    placement: SolverPlacement
    threads: int
    headroom_fraction: float
    smooth_base: int
    shared: int
    per_point: int
    dispute: PerSeriesDispute | None

    @property
    def per_series_model(self) -> Mapping[str, int]:
        """What `memory.resident_bytes_per_series` takes, and only that.

        Returns:
            The model keywords, without `d`.
        """
        return {
            "k_beta": self.k_beta,
            "p_max": self.p_max,
            "n_time": self.n_time,
            "n_models": self.n_models,
        }

    @property
    def arguments(self) -> Mapping[str, Any]:
        """Every argument `tile_side_for` needs to reproduce `shared`.

        **A VIEW RATHER THAN A SECOND COPY.** The two branches the record
        publishes both ways -- `per_point_design` -- and the calibration seam
        `per_series_bytes` are the only parameters left out, and a test binds
        that split against the signature.

        Returns:
            The call keywords.
        """
        return {
            "budget_bytes": self.budget_bytes,
            "floor": self.floor,
            "placement": self.placement,
            "threads": self.threads,
            "d": self.d,
            **self.per_series_model,
        }


PUBLISHED_TILE_SIDE = PublishedTileSide(
    budget_bytes=10**9,
    floor=FloorReport(
        pre_warm_bytes=171_200_000,
        post_warm_bytes=216_900_000,
        with_input_bytes=228_200_000,
        peak_bytes=228_200_000,
        components={"input_open": 228_200_000},
    ),
    floor_basis=(
        "measured 2026-08-15 on the development machine with the input open; "
        "re-measured 2026-08-17 at 228.4-229.9 MB across three inputs at "
        "0.0000 ms/s of full stall"
    ),
    d=3,
    k_beta=4,
    p_max=4,
    n_time=630,
    n_models=12,
    placement=SolverPlacement.PER_SERIES_LIVE,
    threads=1,
    headroom_fraction=0.15,
    smooth_base=16,
    shared=272,
    per_point=144,
    dispute=PerSeriesDispute(
        owner=(
            "unowned. Phase 2b Task 8b closed the instrument question -- both "
            "published slopes are duration-contaminated underestimates of one "
            "quantity -- and did NOT determine the correction's shape, which is "
            "what a later task has to own. The measured peak-to-analytic ratio "
            "is 1.888, 2.603 and 3.850 at three fixtures, so no multiplier and "
            "no single added term reproduces all three"
        ),
        analytic_bytes_per_series=926.0,
        measured_bytes_per_series=2410.0,
        measured_standard_error=46.0,
        ladder_fixture=(
            "N = 60, M = 2, k_beta = 4, p_max = 3, grid = side, "
            "standard-normal float32 from rng(0) with all but 16 series wholly "
            "masked, an explicit (60, 16, 16) chunking so the largest "
            "assembly span is 256 series at every side, max_iter = 1, criteria "
            "['aic'], objective reml, threads 1, floor measured on this input "
            "and pinned; fifteen points at sides 16/32/48/64/96, three repeats, "
            "EVERY POINT PADDED TO A CONSTANT 30 s WALL CLOCK so run length is "
            "not confounded with B, and every point's reclaim shortfall read in "
            "the child (max 0.344 MB, which is the floor measurement's own "
            "between-process scatter). Measured 2026-08-19 on the development "
            "machine, 20 s idle at 0.0000 ms/s of full stall, 4.5-5.0 GB "
            "available. Task 8's own ladder over the three sides its run length "
            "cannot have damaged gives 2584.3 +/- 127.0 and this one gives "
            "2574.9 +/- 236.1 over the same three -- two independent lines, "
            "0.4% apart"
        ),
        resident_at_tile_bytes_per_series=1504.1,
        transient_bytes_per_series=905.9,
        peak_to_analytic_by_fixture={
            "N=60 M=6": 1.888,
            "N=60 M=2": 2.603,
            "N=240 M=2": 3.850,
        },
        headroom_fraction_required=1.0 - 926.0 / 2410.0,
        hypotheses={
            "published": DisputedHypothesis(
                per_series_bytes=8274.0,
                side=272,
                basis="the corrected analytic formula, Task 0",
            ),
            "additive": DisputedHypothesis(
                per_series_bytes=8274.0 + (2410.0 - 926.0),
                side=256,
                basis=(
                    "the 1484.0 B/series excess is a per-series term "
                    "independent of the configuration. **Refuted at the second "
                    "fixture and kept for the spread**: at N = 240 the excess "
                    "is 7255 B/series, not 1484"
                ),
            ),
            "multiplicative": DisputedHypothesis(
                per_series_bytes=8274.0 * 2410.0 / 926.0,
                side=160,
                basis=(
                    "the formula understates every per-series term by 2.603x. "
                    "**Refuted at the second and third fixtures**: the ratio is "
                    "1.888 at M = 6 and 3.850 at N = 240"
                ),
            ),
        },
    ),
)
"""**`tile_side` IS 272 SHARED / 144 PER-POINT, AND THE MEASURED PEAK PER-SERIES
COST IS 2.60x THE FORMULA THE SIDE IS DERIVED FROM** -- 2410.0 +/- 46.0 B/series
against an analytic 926 at the ladder fixture, measured 2026-08-19 over fifteen
duration-controlled points. **The published side is 272 and the live readings
now span 160 to 272**, which is wider than the 192-272 this record carried while
the cost was thought to be 1900.9.

~~Under dispute by 1.86x between Task 7's 1021.6 +/- 134.7 and Task 8's 1900.9
+/- 84.1~~ -- struck 2026-08-19. **Both are underestimates of one quantity, by
one mechanism**: each ladder's run length grew with its own abscissa, and a long
run under memory pressure loses working set and takes its watermark down with
it. Task 8's own three points under 440 s give **2584.3 +/- 127.0**; the new
ladder gives **2574.9 +/- 236.1** over the same three sides.

**THE VALUE STILL DOES NOT MOVE, AND THAT IS A DECISION WITH A REASON.** The
measured ratio of peak to formula is **1.888 at M = 6, 2.603 at M = 2 and 3.850
at N = 240**, so the gap is not a multiplier and not a single added term, and a
coefficient fitted to one fixture is right at that fixture and wrong everywhere
else -- which is F5 and (a7). **Exit criterion 7 is therefore recorded as a
known limitation rather than closed**, with its failing regime named: measured
cleanly, peak RSS exceeds the budget at every tile above roughly B = 1500 at
three fixtures, by 11 MB at side 96 with N = 60 and by 61 MB at side 96 with
N = 240.

That sentence is the number's, not a footnote's, and `dispute` is what makes it
one: every figure in it is recomputed by `tests/test_tiling.py`, so the task
that settles the remainder deletes the field in the edit that moves the value.

**WHAT IS NOT IN DISPUTE:** that the floor, the headroom, the base and the model
are preconditions of the answer; that the placement moves a constant and not the
slope, so the side carries no backend; and that a side quoted without this list
is not a number. Superseded pairs are struck in the handoff's section 3 with
their dates -- ~~171~~, ~~338~~/~~186~~, ~~339~~, ~~347~~/~~187~~, ~~361~~/~~189~~
-- so a reader meeting one in an old note can date it.
"""


_INVERSE_WALK_LIMIT = 64
"""How far `budget_bytes_for_side` may walk from its closed form, in bytes.

The closed form and `block_bytes_for` are the same arithmetic in opposite
directions, so they can disagree only by float rounding -- a byte or two. The
limit is generous against that and tiny against any real error, which is what
makes it a guard: see `budget_bytes_for_side`.
"""


class BudgetTooSmallError(ValueError):
    """A memory budget that does not leave a usable block.

    **A DISTINCT TYPE RATHER THAN A BARE `ValueError`**, so the caller that
    stages it into a layer-3 refusal dispatches structurally instead of on
    message text -- (c2). `memory.tile_side` also raises `ValueError`, for the
    different condition "the block holds no series", and the two must never be
    told apart by their wording.
    """


@dataclass(frozen=True)
class Tile:
    """A contiguous spatial block of whole series, half-open in both axes.

    Attributes:
        y_start: First row, inclusive.
        y_stop: Last row, exclusive.
        x_start: First column, inclusive.
        x_stop: Last column, exclusive.
    """

    y_start: int
    y_stop: int
    x_start: int
    x_stop: int

    @property
    def n_series(self) -> int:
        """Number of series in this tile.

        Returns:
            The batch size the engine will see.
        """
        return (self.y_stop - self.y_start) * (self.x_stop - self.x_start)


def tile_grid(n_y: int, n_x: int, side: int) -> Iterator[Tile]:
    """Yield tiles covering the grid exactly once, ragged edges included.

    **COVERAGE IS THE ONE PLACE AN OFF-BY-ONE IS SILENT.** A miss leaves a seam
    of unwritten points in a store whose completion bitmap is per tile and
    therefore cannot see it; an overlap writes some points twice. Neither
    raises, and both produce a store that looks complete.

    Args:
        n_y: Grid rows.
        n_x: Grid columns.
        side: Tile side, from `tile_side_for`.

    Yields:
        One `Tile` per block, row-major.

    Raises:
        ValueError: If `side` is not positive, or the grid is empty. A side of 0
            is a plausible-looking number that holds no data — the same refusal
            `memory.tile_side` makes, for the same reason.
    """
    if side <= 0:
        raise ValueError(f"tile side must be positive, got {side}")
    if n_y <= 0 or n_x <= 0:
        raise ValueError(f"grid must be non-empty, got {n_y} x {n_x}")
    for y_start in range(0, n_y, side):
        for x_start in range(0, n_x, side):
            yield Tile(
                y_start=y_start,
                y_stop=min(y_start + side, n_y),
                x_start=x_start,
                x_stop=min(x_start + side, n_x),
            )


def block_bytes_for(*, budget_bytes: int, floor: FloorReport) -> int:
    """Return what a tile may hold, out of what the process may hold.

    **`block_bytes = budget - floor - headroom`, AND THE BUDGET IS THE PROCESS,
    NOT THE TILE.** `--memory-budget` bounds process peak RSS -- that is what
    exit criterion 7 asserts -- and until 2026-08-15 the budget was passed
    straight in as the block, so a tile was sized to the whole budget and the
    interpreter's hundreds of megabytes had nowhere to live. At a 1 GB budget
    the tile came out at **996 MB, 92.8% of it, against a 221.5 MB floor**: the
    criterion was met only because the suite fits four series.

    **The floor taken is `peak_bytes`**, not the post-warm current reading,
    because criterion 7 is about a peak: what must come out of the budget is the
    high-water mark of everything that is not the tile. See `memory.FloorReport`.

    **The headroom is a FRACTION of what is left after the floor**, not of the
    budget: what it absorbs scales with the block. See `memory.HEADROOM_FRACTION`
    for the four things it covers and for the asymmetry that sets its value.

    Args:
        budget_bytes: The resolved process memory budget, in bytes.
        floor: The measured process floor.

    Returns:
        Bytes a tile may hold.

    Raises:
        BudgetTooSmallError: If the budget does not clear the floor and the
            headroom. **The message names the floor, its components and a budget
            that would work**, because the user has no other way to find out --
            a refusal that says only "too small" is a wall, and this one is
            planning information against a hard constraint.
    """
    available = budget_bytes - floor.peak_bytes
    block = int(available * (1.0 - HEADROOM_FRACTION))
    if block < 1:
        ladder = ", ".join(
            f"{name} {value / 1e6:.1f} MB"
            for name, value in sorted(floor.components.items())
        )
        workable = int((floor.peak_bytes + 1) / (1.0 - HEADROOM_FRACTION)) + 1
        raise BudgetTooSmallError(
            f"a memory budget of {budget_bytes / 1e9:.4g} GB ({budget_bytes} B) "
            f"leaves nothing for a tile: this process holds "
            f"{floor.peak_bytes / 1e6:.1f} MB before a tile exists, and "
            f"{HEADROOM_FRACTION:.0%} of what is left is held back for "
            f"transients. The floor, rung by rung: {ladder}. A budget above "
            f"{workable / 1e9:.4g} GB ({workable} B) leaves a positive block; a "
            f"useful one is several times that, since the tile is what the "
            f"budget is for"
        )
    return block


def tile_side_for(
    *,
    budget_bytes: int,
    floor: FloorReport,
    placement: SolverPlacement = SolverPlacement.PER_SERIES_LIVE,
    d: int,
    threads: int = 1,
    k_beta: int,
    p_max: int,
    n_time: int,
    n_models: int,
    per_point_design: bool = False,
    per_series_bytes: float | None = None,
) -> int:
    """Return the square tile side a memory budget allows.

    `sqrt((block_bytes - solver_state) / resident_bytes_per_series)`, floored,
    then rounded **down** to a multiple of `store.TILE_SIDE_BASE`.

    **NOT `sqrt(block_bytes / (n_time * itemsize))`**, which is the prompt's
    formula: it counts only the float64 data and overestimates, giving ~~445~~
    where the full accounting gives `PUBLISHED_TILE_SIDE.shared`. Design doc
    §11.1 carried it until 2026-08-12 while §9.4 rejected it, and §11.1 is the
    section a tiling implementer opens first. **The answer is not repeated here**
    — this is the function the record recomputes its value through, so a copy in
    its own docstring is the one place the cascade could restart.

    **THE ROUNDING HAPPENS HERE, BEFORE THE SIDE IS STORED**, and that placement
    is the point rather than a detail. A calibration that rounded at its own call
    site would exercise a derivation the production run does not, which is (j2);
    and a resume reads the side back out of the store, so the stored value must
    already be the rounded one or the two derivations disagree by construction.

    **AND IT REMOVES A FOOTGUN RATHER THAN DOCUMENTING ONE.** With every derived
    side a multiple of the base, Task 7's instrument gets chunk-friendly sides
    **by construction**, and there is no deliberate choice of awkward budgets for
    a later reader to "simplify" into round numbers. A property that holds
    structurally beats one that must survive future editing.

    Args:
        budget_bytes: The resolved process memory budget, in bytes.
        floor: The measured process floor.
        placement: Where the live solver state sits. One reachable value.
        d: Composite state dimension, the widest candidate's. It reaches the
            arithmetic only through the solver constant.
        threads: Worker threads. Ignored under the reachable placement.
        k_beta: Number of design columns.
        p_max: Widest candidate's free noise parameter count. The tile holds
            whichever candidate is being fitted and `fit` sizes every slot to
            the widest, so a per-candidate `p` understates the allocation.
        n_time: Series length.
        n_models: Candidate count held until the tile is written.
        per_point_design: True if any regressor is a per-point field.
        per_series_bytes: A **measured** per-series cost to use instead of the
            analytic one. **THE ONE SEAM A CALIBRATION REACHES A TILE SIDE
            THROUGH**, and it is a parameter here rather than a second
            derivation at the calibration's own call site: a calibrated path
            that re-did this arithmetic would be a second description of one
            subject (a6), and it would drift silently because a wrong side still
            runs. Only the **slope** belongs here -- a calibration's intercept
            is not the process floor and `memory.CalibrationResult` says so.

    Returns:
        The tile side in grid points: a multiple of `store.TILE_SIDE_BASE`, or a
        raw side below the base, where the base is provably inert.

    Raises:
        BudgetTooSmallError: If the budget does not clear the floor and the
            headroom, or if what is left does not hold one series at the base.
            **Both arms are this type**, because both are the same question to
            the user -- "your budget is too small, here is one that works" --
            and dispatching on which arithmetic step ran out is the caller's
            problem rather than theirs.
        ValueError: If `per_series_bytes` is not positive. **DOUBLY GUARDED,
            DELIBERATELY, AND EACH GUARD NAMES THE OTHER**:
            `calibration.unusable_reason` refuses a non-positive slope by the
            band -- whose lower bound is positive -- so nothing in the run path
            reaches this. It is not dead code, because this function is public
            and this parameter is the seam a caller that skipped the band
            arrives through, and without it the symptom is a domain error out of
            `math.sqrt` that names nothing. Removing either guard on the grounds
            that the other covers it removes the coverage as well.
    """
    block = block_bytes_for(budget_bytes=budget_bytes, floor=floor)
    constant = solver_state_bytes(
        placement, d=d, k_beta=k_beta, p_max=p_max, threads=threads
    )
    if per_series_bytes is not None and per_series_bytes <= 0:
        raise ValueError(
            f"a per-series cost of {per_series_bytes:g} B says a tile gets "
            "cheaper as it grows, which no measurement means; see "
            "metamer.batch.calibration.unusable_reason for the band a measured "
            "slope has to clear before it sizes anything"
        )
    per_series: float = (
        resident_bytes_per_series(
            k_beta=k_beta,
            p_max=p_max,
            n_time=n_time,
            n_models=n_models,
            per_point_design=per_point_design,
        )
        if per_series_bytes is None
        else per_series_bytes
    )
    if block - constant < per_series:
        raise BudgetTooSmallError(
            f"a memory budget of {budget_bytes / 1e9:.4g} GB leaves a block of "
            f"{block} B, of which {constant} B is the live solver working set, "
            f"so {block - constant} B remain against {per_series} B for one "
            f"series. The process floor is {floor.peak_bytes / 1e6:.1f} MB and "
            f"{HEADROOM_FRACTION:.0%} of what is above it is held back for "
            f"transients"
        )
    raw = tile_side(block - constant, per_series)
    # **BELOW THE BASE THE BASE IS INERT, SO THE SIDE PASSES THROUGH.** The base
    # exists because `store._chunk_side` picks a DIVISOR of the side, and that
    # only matters once some array's shard can reach `CHUNK_TARGET_BYTES`. The
    # widest array is `warmstart/theta_unconstrained` at `8 * P_total` bytes per
    # cell, so a shard reaches the target at
    # `side >= sqrt(CHUNK_TARGET_BYTES / (8 * P_total))` -- 112 at P_total = 40,
    # and a side below 16 would need P_total above 2200 to get there. **So for
    # every side under the base, every array is already one chunk per shard and
    # the divisor structure is irrelevant.** Rounding such a side to zero would
    # refuse a small run for no benefit at all.
    if raw < TILE_SIDE_BASE:
        return raw
    return (raw // TILE_SIDE_BASE) * TILE_SIDE_BASE


def budget_bytes_for_side(
    *,
    side: int,
    floor: FloorReport,
    placement: SolverPlacement = SolverPlacement.PER_SERIES_LIVE,
    d: int,
    threads: int = 1,
    k_beta: int,
    p_max: int,
    n_time: int,
    n_models: int,
    per_point_design: bool = False,
) -> int:
    """Return the smallest budget whose derived tile side is exactly `side`.

    **`tile_side_for` INVERTED, IN THE SAME MODULE AND OFF THE SAME CONSTANTS**,
    because a calibration cannot choose its own B. A run's batch is a **tile**,
    so `B = side**2`, and since Task 2 every derived side is a multiple of
    `store.TILE_SIDE_BASE` -- which is why Phase 2b's calibration ladder is a
    ladder in **sides** and not in series, and why the brief's
    `B in {1000, 2000, 4000}` names three batches no tile can have
    (`sqrt(1000) = 31.6`).

    **THE INVERSE LIVES BESIDE THE FORWARD FUNCTION DELIBERATELY.** Split across
    modules the two drift, and the drift is silent: the ladder still runs and
    every point sits at a B nobody asked for. `tests/test_tiling.py` asserts the
    round trip rather than any hand-written budget, which is the executable form
    of "the calibration uses the production derivation" (j2).

    Args:
        side: The tile side wanted. Below `store.TILE_SIDE_BASE` the base is
            inert and any side is reachable; at or above it, only multiples of
            the base are, and a non-multiple raises.
        floor: The measured process floor. **Pin it across a ladder**: it is
            measured fresh per run and varies by megabytes, while the budget
            window selecting one multiple of the base is narrower than that.
        placement: Where the live solver working set sits.
        d: Composite state dimension, the widest candidate's.
        threads: Worker threads. Ignored under the reachable placement.
        k_beta: Number of design columns.
        p_max: Widest candidate's free noise parameter count.
        n_time: Series length.
        n_models: Candidate count held until the tile is written.
        per_point_design: True if any regressor is a per-point field.

    Returns:
        The budget in bytes.

    Raises:
        ValueError: If `side` is not positive, or is at or above the base and
            not a multiple of it -- **a request no budget can satisfy**, and
            returning the nearest reachable side instead would hand the caller a
            B it did not ask for, which is the defect this function exists to
            make impossible.
    """
    if side < 1:
        raise ValueError(f"tile side must be positive, got {side}")
    if side >= TILE_SIDE_BASE and side % TILE_SIDE_BASE:
        raise ValueError(
            f"no budget derives a tile side of {side}: every side at or above "
            f"{TILE_SIDE_BASE} is rounded down to a multiple of it, so the "
            f"reachable sides near {side} are "
            f"{(side // TILE_SIDE_BASE) * TILE_SIDE_BASE} and "
            f"{(side // TILE_SIDE_BASE + 1) * TILE_SIDE_BASE}"
        )
    block = side * side * resident_bytes_per_series(
        k_beta=k_beta,
        p_max=p_max,
        n_time=n_time,
        n_models=n_models,
        per_point_design=per_point_design,
    ) + solver_state_bytes(placement, d=d, k_beta=k_beta, p_max=p_max, threads=threads)
    # **THE CLOSED FORM IS THE STARTING POINT AND `block_bytes_for` IS THE
    # ARBITER.** Inverting `int((budget - floor) * (1 - headroom))` in floats
    # gets the answer right to within a byte or two and wrong in a direction
    # that depends on the rounding, and a byte here is a whole tile side. So the
    # closed form seeds a walk that asks the forward function -- **the inverse
    # is verified against the function it inverts rather than against a second
    # piece of float reasoning** (j), and the result is exactly minimal.
    budget = floor.peak_bytes + int(math.ceil(block / (1.0 - HEADROOM_FRACTION)))
    for _ in range(_INVERSE_WALK_LIMIT):
        if block_bytes_for(budget_bytes=budget, floor=floor) >= block:
            return budget
        budget += 1
    # **BOUNDED, AND THE BOUND IS A GUARD RATHER THAN A SAFETY NET.** An
    # unbounded walk repairs a closed form that is wrong by any amount -- it
    # just takes a byte at a time, so a seed that omitted the headroom would
    # still return the right answer after ~10**8 iterations and nothing would
    # fail. Measured: that mutation left every round-trip test green and turned
    # a 2.4 s module into a 21.5 s one, which is a defect no assertion here was
    # looking at. With the bound, a closed form that disagrees with
    # `block_bytes_for` by more than rounding says so.
    raise ValueError(
        f"the closed form for a tile side of {side} disagrees with "
        f"block_bytes_for by more than {_INVERSE_WALK_LIMIT} bytes; the two are "
        "the same arithmetic and one of them has changed"
    )


def chunk_shape(handle: InputHandle) -> tuple[int, ...]:
    """Return the store's own chunk shape for the handle's variable.

    Read from the array's encoding, which for a dataset opened with
    `chunks=None` is the on-disk chunking. **A dataset opened through dask
    reports dask's graph chunking there instead**, which is a different number
    and is not what zarr reads — one more reason 2a stays off dask.

    Args:
        handle: An opened input, past the stage-4a contract.

    Returns:
        Chunk shape, in the variable's dimension order.

    Raises:
        InputContractError: If the array declares no chunking. Guessing one
            would make read amplification a number about an assumption.
    """
    array = handle.dataset[handle.variable]
    chunks = array.encoding.get("chunks") or array.encoding.get("preferred_chunks")
    if not chunks:
        raise InputContractError(
            f"{handle.uri!r}: variable {handle.variable!r} declares no chunk "
            "shape, so read amplification cannot be measured. Rechunk the store "
            "or open it through a reader that reports its chunking"
        )
    if isinstance(chunks, dict):
        chunks = tuple(chunks[str(dim)] for dim in array.dims)
    return tuple(int(size) for size in chunks)


def _chunk_points(start: int, stop: int, chunk: int, extent: int) -> int:
    """Points zarr decompresses on one axis to deliver `[start, stop)`.

    Args:
        start: First index, inclusive.
        stop: Last index, exclusive.
        chunk: Chunk length on this axis.
        extent: Axis length, so the last chunk is counted clipped.

    Returns:
        The decompressed point count on this axis.
    """
    first = start // chunk
    last = (stop - 1) // chunk
    return min((last + 1) * chunk, extent) - first * chunk


def read_amplification(handle: InputHandle, tile: Tile) -> float:
    """Return bytes read over bytes used for one tile, both decompressed.

    zarr reads whole chunks, so a tile straddling chunk boundaries silently
    reads several times what it needs. **This replaces the dask graph-chunk cap
    as the guard watching for a pathological input**, and tile geometry should
    align with input chunk geometry where possible.

    **THE UNITS ARE THE TRAP.** A store's bytes are compressed and a tile's are
    not, so a ratio taken across that boundary measures compression as well as
    amplification — measured, 3112 store bytes for 768 used where the true
    amplification is 4 — and on a compressible variable it would report a value
    **below 1**, which is meaningless for a metric defined as bytes read over
    bytes used. Both sides here are decompressed point counts.

    **Measured in the phase that can, printed by the phase that shows.** 2a
    computes and records it; Phase 5's `--explain` prints it. Computing it twice
    is how the two versions come to disagree, so this returns a number rather
    than warning.

    Args:
        handle: An opened input, past the stage-4a contract.
        tile: The tile about to be assembled.

    Returns:
        Bytes read divided by bytes used. 1.0 when the tile aligns with the
        chunk grid; never below 1.

    Raises:
        InputContractError: If the variable declares no chunk shape.
    """
    array = handle.dataset[handle.variable]
    chunks = chunk_shape(handle)
    sizes = {
        str(dim): int(size) for dim, size in zip(array.dims, array.shape, strict=True)
    }
    by_dim = {str(dim): size for dim, size in zip(array.dims, chunks, strict=True)}

    # The time axis is read WHOLE for every tile, so it contributes its full
    # extent to both sides and cancels -- but it is written out rather than
    # dropped, because it stops cancelling the moment a time-chunked read lands.
    read = _chunk_points(0, sizes["time"], by_dim["time"], sizes["time"])
    used = sizes["time"]
    for dim, start, stop in (
        ("y", tile.y_start, tile.y_stop),
        ("x", tile.x_start, tile.x_stop),
    ):
        read *= _chunk_points(start, stop, by_dim[dim], sizes[dim])
        used *= stop - start
    return read / used


def assembly_spans(handle: InputHandle, tile: Tile) -> list[Tile]:
    """Split a tile into sub-blocks, each lying inside one chunk.

    **THIS IS WHAT MAKES "BOTH FULL REPRESENTATIONS NEVER COEXIST" TRUE**, and
    it is public so it can be asserted rather than described. `assemble_tile`
    materializes these one at a time into a preallocated float64 destination, so
    at most one span's float32 is ever alive.

    Args:
        handle: An opened input, past the stage-4a contract.
        tile: The tile to split.

    Returns:
        The spans, in row-major order. They partition the tile exactly.
    """
    array = handle.dataset[handle.variable]
    chunks = chunk_shape(handle)
    by_dim = {str(dim): size for dim, size in zip(array.dims, chunks, strict=True)}
    return [
        Tile(y_start=y_from, y_stop=y_to, x_start=x_from, x_stop=x_to)
        for y_from, y_to in _aligned_spans(tile.y_start, tile.y_stop, by_dim["y"])
        for x_from, x_to in _aligned_spans(tile.x_start, tile.x_stop, by_dim["x"])
    ]


def assemble_tile(handle: InputHandle, tile: Tile) -> NDArray[np.float64]:
    """Materialize one tile as an `(n_series, n_time)` float64 block.

    **ASSEMBLED PER CHUNK-ALIGNED SPAN, WHICH IS A DEVIATION FROM THE BRIEF's
    LITERAL FIRST BULLET AND IS REQUIRED BY ITS SECOND.** One `.load()` over the
    whole tile materializes the entire float32 block, and casting that has both
    full representations alive at once -- which "float32 to float64 conversion
    per chunk, so both full representations never coexist" exists to forbid.
    Recomputed at design doc section 9.4's worked example on 2026-08-17 at
    `PUBLISHED_TILE_SIDE.shared` = 272 and N = 630: 272**2 * 630 = 46 609 920
    points, so the float32 tile is **186 MB** and the float64 tile **373 MB**,
    and the one-call form peaks at **559 MB against 373 MB -- a 50% overshoot of
    the data term** against a budget the design doc calls hard. ~~At 347 the
    same figures were 303 MB, 607 MB and 910 MB~~, struck 2026-08-17.
    The ratio is 3:2 by construction and does not move with the side; the
    absolute figures do, which is why they carry the side that produced them --
    **and why they are recomputed whenever the record moves**, including
    whichever way Task 8a resolves.

    So the float64 destination is allocated once and each span from
    `assembly_spans` is loaded, cast into its slice, and dropped.

    Args:
        handle: An opened input, past the stage-4a contract.
        tile: Which block to materialize.

    Returns:
        `(n_series, n_time)` float64, series in row-major grid order.
    """
    array = handle.dataset[handle.variable]
    n_time = int(array.shape[0])
    block = np.empty((tile.n_series, n_time), dtype=np.float64)
    width = tile.x_stop - tile.x_start

    for span in assembly_spans(handle, tile):
        piece = (
            array.isel(
                y=slice(span.y_start, span.y_stop),
                x=slice(span.x_start, span.x_stop),
            )
            .values.astype(np.float64)
            .reshape(n_time, -1)
            .T
        )
        rows = np.arange(span.y_start - tile.y_start, span.y_stop - tile.y_start)
        columns = np.arange(span.x_start - tile.x_start, span.x_stop - tile.x_start)
        block[(rows[:, None] * width + columns[None, :]).ravel()] = piece
        del piece
    return block


def _aligned_spans(start: int, stop: int, chunk: int) -> Iterator[tuple[int, int]]:
    """Split `[start, stop)` at chunk boundaries.

    Args:
        start: First index, inclusive.
        stop: Last index, exclusive.
        chunk: Chunk length on this axis.

    Yields:
        Half-open spans, each inside one chunk.
    """
    edge = start
    while edge < stop:
        nxt = min(int(math.floor(edge / chunk) + 1) * chunk, stop)
        yield edge, nxt
        edge = nxt


__all__ = [
    "Tile",
    "budget_bytes_for_side",
    "assemble_tile",
    "assembly_spans",
    "chunk_shape",
    "read_amplification",
    "tile_grid",
    "tile_side_for",
]
