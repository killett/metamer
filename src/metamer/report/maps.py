"""Downsampled maps, one per branch, drawn only if matplotlib is installed.

**EVERY MAP IS A FRACTION AND NO ARITHMETIC EVER REACHES AN OUTCOME CODE
(D9).** A categorical code array has no honest arithmetic reduction:
`mean(DEGENERATE_HESSIAN, ILL_CONDITIONED_X)` is `mean(7, 11) == 9`, which is
`CANDIDATE_DROPPED` -- a real, different, **valid-looking** code from the other
side of section 12.5's grouping table. The two cells say *this fit failed twice
over* and their mean says *the run chose not to fit this candidate here*. A
downsampled categorical map is therefore not noisy, it is **articulate and
wrong**, and on a global grid it would be wrong across whole regions with every
legend entry a real member of the alphabet. So the reduction is over a
**binary indicator** per branch, and `block_fractions` returns a fraction in
`[0, 1]` by construction.

**THE DENOMINATOR IS THE POPULATION's CELLS IN THE BLOCK, NOT THE BLOCK's CELLS
(T7-1).** This is the denominator defect in map form. D9's invariant is that the
map and the statistic never cover different things, and D3 sets that population
to `Outcome.is_fit_verdict`; dividing by every cell in the block would make a
coastal block that is half land show **half** its real failure fraction. That is
D2b's dilution, drawn as a map and printed beside a statistic that does not have
it.

**AND A BLOCK WITH NO POPULATION IS MASKED, NEVER ZERO.** Zero is the bottom of
`viridis` and reads as *no failures here*, so an all-land block rendered as 0
makes the emptiest part of the map look like the healthiest. This is the
`fitted == 0` rule -- a rate over an empty population is unavailable, not
`0.0` -- arriving in a colourmap.

**MATPLOTLIB IS IMPORTED INSIDE `draw` AND NOWHERE ELSE (D10).** The numbers
path has to work on someone else's store in an environment that never installed
a plotting stack, so everything in this module except `draw` is numpy only.
`tests/test_packaging.py` walks function bodies with `ast`, so the lazy import
is a declared-dependency question exactly like an eager one and matplotlib is
declared in the `[report]` extra: lazy import buys **portability at run time**,
the extra states **what the distribution asks for**, and the two are different
claims.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from metamer.core.outcomes import Outcome
from metamer.report.reader import StoreView

#: The extra that installs the plotting stack. Named in the report when the
#: maps could not be drawn, so the message is actionable rather than a notice.
REPORT_EXTRA = "report"

#: Target side, in cells, of a downsampled block. The map is a diagnostic read
#: at a glance rather than a figure anybody measures off, so this is a bound on
#: output size and not a derived constant: `_block_side` divides the grid down
#: until neither axis exceeds this, which keeps a 10^7-point grid's PNG small
#: while leaving a 40x40 fixture undownsampled.
MAX_BLOCKS = 256


@dataclass(frozen=True)
class BranchMap:
    """One branch's downsampled fraction field, before anything is drawn.

    Attributes:
        branch: The outcome code this map is about.
        title: The branch's name **as the store spells it**, with the
            population it is over. Empty legend means the code alone.
        candidate: The `m`-axis label, or `None` for the point-level aggregate.
        kind: `"failure"` over fit-verdict cells, or `"coverage"` over covered
            cells. **A non-fit branch is never a failure map** (T7-1): it has
            no fit verdict to fail, so its denominator and its label both say
            coverage.
        population: The denominator's name, recorded so the map and the
            statistic can be compared without reading this module.
        fraction: `(rows, columns)` float64 in `[0, 1]`; `nan` where the block
            held no population cells.
        masked: `(rows, columns)` bool, true where `fraction` is `nan`.
        block: The `(y, x)` cells per block the reduction used.
    """

    branch: int
    title: str
    candidate: str | None
    kind: str
    population: str
    fraction: NDArray[np.float64]
    masked: NDArray[np.bool_]
    block: tuple[int, int]


def _block_side(length: int) -> int:
    """Cells per block along one axis, so the output is at most `MAX_BLOCKS`.

    Args:
        length: The axis's length in cells.

    Returns:
        At least 1, and 1 for any axis already short enough -- an undownsampled
        axis is the identity reduction rather than a special case.
    """
    if length <= MAX_BLOCKS:
        return 1
    return -(-length // MAX_BLOCKS)


def block_fractions(
    indicator: NDArray[np.bool_],
    population: NDArray[np.bool_],
    *,
    block: tuple[int, int] | None = None,
) -> tuple[NDArray[np.float64], NDArray[np.bool_], tuple[int, int]]:
    """Reduce a binary indicator to per-block fractions of its population.

    **THE WHOLE POINT IS THE DENOMINATOR.** `indicator.sum() / population.sum()`
    per block, never `indicator.mean()`, so a block that is half outside the
    population reports the fraction among the cells that could have carried the
    code.

    Args:
        indicator: `(y, x)` true where the cell carries the branch. Must be a
            subset of `population`; cells outside it are ignored rather than
            trusted, so a caller that passes a superset cannot inflate a
            fraction above 1.
        population: `(y, x)` true where the cell is in the denominator.
        block: Cells per block, `(y, x)`. Defaults to whatever keeps the output
            within `MAX_BLOCKS` on both axes.

    Returns:
        The fractions, the mask, and the block size used. `nan` and masked
        wherever a block held no population cells.

    Raises:
        ValueError: If the two arrays are not the same 2-D shape.
    """
    if indicator.shape != population.shape or indicator.ndim != 2:
        raise ValueError(
            "indicator and population must be the same 2-D shape; got "
            f"{indicator.shape} and {population.shape}"
        )
    rows, columns = indicator.shape
    side = block or (_block_side(rows), _block_side(columns))
    # **PAD TO A WHOLE NUMBER OF BLOCKS WITH FALSE, NOT WITH ZERO FRACTIONS.**
    # Padding the counts would invent population; padding the masks with False
    # adds cells that are outside the population, so an edge block's
    # denominator is its real cell count and a block that is entirely padding
    # is masked for the same reason an all-land block is.
    down = -(-rows // side[0]), -(-columns // side[1])
    shape = (down[0], side[0], down[1], side[1])
    pad = ((0, down[0] * side[0] - rows), (0, down[1] * side[1] - columns))
    inside = np.asarray(population, dtype=np.bool_) & np.asarray(
        indicator, dtype=np.bool_
    )
    counts = np.pad(inside, pad).reshape(shape).sum(axis=(1, 3))
    totals = (
        np.pad(np.asarray(population, dtype=np.bool_), pad)
        .reshape(shape)
        .sum(axis=(1, 3))
    )
    masked: NDArray[np.bool_] = totals == 0
    fraction = np.full(masked.shape, np.nan, dtype=np.float64)
    np.divide(counts, totals, out=fraction, where=~masked)
    return fraction, masked, side


def _title(view: StoreView, branch: int, kind: str, population: str) -> str:
    """One map's title, naming the branch and the population it is over.

    **THE BRANCH's NAME COMES FROM THE STORE** (`StoreView.legend`), never from
    this build's `Outcome`, so a title describes the alphabet that wrote the
    store. A code the store did not describe is titled by its number, which is
    the honest answer and not a fallback to the local enum.

    **AND THE POPULATION IS IN THE TITLE BECAUSE THE FRACTION IS MEANINGLESS
    WITHOUT IT** (T7-1). Two maps of the same branch over different
    denominators are different quantities, and a reader comparing them needs the
    denominator on the image rather than in the surrounding document.

    Args:
        view: The store, for its own flag attributes.
        branch: The outcome code.
        kind: `"failure"` or `"coverage"`.
        population: The denominator's name.

    Returns:
        The title line.
    """
    name = view.legend.get(branch, f"code {branch}")
    return f"{name} - {kind} fraction over {population}"


@dataclass(frozen=True)
class MapPlan:
    """Every map a store earns, and every branch that earns none.

    Attributes:
        maps: The computed maps, in a deterministic order.
        unmapped: `(code, name, reason)` per branch present in the store that
            has no population to be a fraction of. **Reported rather than
            dropped**: a branch that is present and absent from the map set
            must say so, or a reader cannot tell "no such branch" from "we
            declined to draw it".
    """

    maps: tuple[BranchMap, ...]
    unmapped: tuple[tuple[int, str, str], ...]


def plan_maps(view: StoreView) -> MapPlan:
    """Every map this store earns, computed but not drawn.

    **THE INVENTORY IS BOUNDED BY WHAT OCCURRED, NOT BY THE ALPHABET** (D9).
    Fourteen members times a candidate count would mostly produce empty maps,
    and an empty map is indistinguishable at a glance from a map of a branch
    that never happened -- so a branch earns a map where it is present.

    **A BRANCH IS MAPPED OVER THE POPULATION IT BELONGS TO, AND TWO MEMBERS
    BELONG TO NEITHER.** A fit-verdict branch is a failure fraction over
    fit-verdict cells, which is what `clustering.compute` counts. A covered
    branch that is not a fit verdict is a **coverage** fraction over covered
    cells, labelled as one, because it has no fit verdict to fail and putting a
    decision the run took on the failure axis is D1's tell.

    **`NOT_ATTEMPTED` AND `NOT_APPLICABLE` ARE IN NEITHER POPULATION, SO THEY
    GET NO MAP** -- and that is a finding rather than a tidy-up. Mapping them as
    a fraction of covered cells, which an earlier draft of this function did,
    yields `0 / covered` in every block: **an all-zero map of a branch that is
    present**, which under fixed limits renders as uniform dark purple and reads
    as *this never happens* for the one code an interrupted store is full of.
    The mean-of-codes defect's whole shape -- not a wrong picture, a plausible
    one -- reached through the denominator instead of the numerator.

    Args:
        view: A store, read-only.

    Returns:
        The maps and the unmapped branches. Candidate order follows the `m`
        axis and branch order follows the code, because a set's iteration order
        is a `PYTHONHASHSEED` dependency and provenance that varies by
        interpreter is not provenance -- Task 4's defect, one task later.
    """
    codes = np.asarray(view.outcome, dtype=np.uint8)
    fit_verdict = np.zeros(codes.shape, dtype=np.bool_)
    covered = np.zeros(codes.shape, dtype=np.bool_)
    fit_codes: set[int] = set()
    covered_codes: set[int] = set()
    for member in Outcome:
        if member.is_fit_verdict:
            fit_verdict |= codes == member.code
            fit_codes.add(member.code)
        if member.is_covered:
            covered |= codes == member.code
            covered_codes.add(member.code)

    maps: list[BranchMap] = []
    unmapped: list[tuple[int, str, str]] = []
    for branch in sorted({int(code) for code in np.unique(codes)}):
        if branch in fit_codes:
            kind, population, source = "failure", "fit-verdict cells", fit_verdict
        elif branch in covered_codes:
            kind, population, source = "coverage", "covered cells", covered
        else:
            unmapped.append(
                (
                    branch,
                    view.legend.get(branch, f"code {branch}"),
                    "in neither the fit-verdict nor the covered population, so "
                    "it is not a fraction of anything; mapping it over covered "
                    "cells would render a present branch as uniform zero",
                )
            )
            continue
        for index, label in enumerate(view.model_labels):
            fraction, masked, block = block_fractions(
                codes[..., index] == branch, source[..., index]
            )
            maps.append(
                BranchMap(
                    branch=branch,
                    title=_title(view, branch, kind, population),
                    candidate=str(label),
                    kind=kind,
                    population=population,
                    fraction=fraction,
                    masked=masked,
                    block=block,
                )
            )
        # **THE POINT-LEVEL MAP IS ANY-CANDIDATE OVER ANY-CANDIDATE**, matching
        # `clustering.compute`'s aggregate population (`fit_verdict.any`)
        # rather than summarising the per-candidate maps -- D7, the aggregate is
        # a different kind of headline and not a mean of the rows above it.
        fraction, masked, block = block_fractions(
            np.asarray((codes == branch).any(axis=-1), dtype=np.bool_),
            np.asarray(source.any(axis=-1), dtype=np.bool_),
        )
        maps.append(
            BranchMap(
                branch=branch,
                title=_title(view, branch, kind, f"{population}, any candidate"),
                candidate=None,
                kind=kind,
                population=f"{population}, any candidate",
                fraction=fraction,
                masked=masked,
                block=block,
            )
        )
    return MapPlan(maps=tuple(maps), unmapped=tuple(unmapped))


def matplotlib_available() -> bool:
    """Whether the plotting stack is importable, without importing it eagerly.

    **`find_spec` RATHER THAN A `try: import`** so asking the question does not
    answer it differently: an import inside this function would put matplotlib
    into `sys.modules` for the rest of the process and make the import-graph
    probe's reading depend on whether anything had asked.

    Returns:
        True if `draw` can run.
    """
    from importlib.util import find_spec

    try:
        return find_spec("matplotlib") is not None
    except (ImportError, ValueError):
        # A partially installed distribution raises rather than returning None.
        # Unavailable is the answer: the numbers path must survive it.
        return False


def draw(entry: BranchMap, destination: Path) -> Path:
    """Write one map to a PNG.

    **`vmin=0` AND `vmax=1`, ALWAYS** (D9). matplotlib autoscales to the data,
    so a branch present at 0.01 to 0.03 everywhere renders full-range and 3%
    looks like 100%, and two stores with different ranges are not comparable.
    That is the mean-of-codes defect in continuous form -- not a wrong picture,
    a **plausible** one.

    **AND MASKED BLOCKS GET THEIR OWN COLOUR, NOT `viridis`'s BOTTOM.** With the
    limits fixed, 0.0 is dark purple and means *no failures among cells that
    could have failed*; a block with nothing to fail must not land on the same
    pixel value.

    Args:
        entry: The computed map.
        destination: The PNG path to write. Its parent must exist.

    Returns:
        `destination`.
    """
    # **IMPORTED HERE AND NOWHERE ELSE (D10).** Module scope would make the
    # numbers path require a plotting stack, and the import-graph probe would
    # catch it -- which is the half of the enforcement that bites.
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    colours = matplotlib.colormaps["viridis"].with_extremes(bad="#b0b0b0")
    figure, axes = plt.subplots(figsize=(6.0, 4.0), layout="constrained")
    image = axes.imshow(
        np.ma.masked_invalid(entry.fraction),
        cmap=colours,
        vmin=0.0,
        vmax=1.0,
        origin="lower",
        interpolation="nearest",
    )
    axes.set_title(entry.title, fontsize=9)
    axes.set_xlabel(
        f"block = {entry.block[0]}x{entry.block[1]} cells; grey = no population"
    )
    figure.colorbar(image, ax=axes, label="fraction")
    figure.savefig(destination, dpi=110)
    plt.close(figure)
    return destination


def _slug(text: str) -> str:
    """A filename-safe form of a candidate label.

    Args:
        text: The label as the store spells it.

    Returns:
        Lowercase alphanumerics and underscores, never empty.
    """
    kept = "".join(character if character.isalnum() else "_" for character in text)
    return kept.strip("_").lower() or "unnamed"


def draw_all(view: StoreView, out_dir: Path) -> dict[str, Any]:
    """Compute every map and draw what can be drawn.

    **THE RECORD IS WRITTEN WHETHER OR NOT THE PNGS ARE** (D10). Without
    matplotlib every map still appears in the record with its population, block
    size and `drawn: false`, so the report says which maps the store earned and
    which extra draws them rather than falling silent.

    Args:
        view: A store, read-only.
        out_dir: Directory for the PNGs. Must exist.

    Returns:
        `maps`, one record per map in `plan_maps` order, and `unmapped`, the
        branches present with no population -- carried into the record so the
        report can state them.
    """
    plan = plan_maps(view)
    drawable = matplotlib_available()
    records: list[dict[str, Any]] = []
    for entry in plan.maps:
        # **THE NAME IDENTIFIES THE MAP's SUBJECT, NOT ITS POSITION.** An
        # earlier draft numbered the file by the loop index and spelled the
        # candidate from the same number, so two different candidates' maps were
        # named by where they happened to fall in the inventory -- a filename
        # that changes meaning when a branch stops occurring.
        stem = "_".join(
            (
                f"code{entry.branch:02d}",
                entry.kind,
                "point" if entry.candidate is None else _slug(entry.candidate),
            )
        )
        record: dict[str, Any] = {
            "branch": entry.branch,
            "title": entry.title,
            "candidate": entry.candidate,
            "kind": entry.kind,
            "population": entry.population,
            "block": list(entry.block),
            "masked_blocks": int(np.count_nonzero(entry.masked)),
            "drawn": drawable,
        }
        if drawable:
            record["png"] = draw(entry, out_dir / f"{stem}.png").name
        else:
            record["extra"] = REPORT_EXTRA
        records.append(record)
    return {
        "maps": records,
        "unmapped": [
            {"branch": code, "name": name, "reason": reason}
            for code, name, reason in plan.unmapped
        ],
        "drawn": drawable,
        "extra": None if drawable else REPORT_EXTRA,
    }
