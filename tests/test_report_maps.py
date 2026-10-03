"""Sub-phase 2f Task 7: the maps, and the denominator they are fractions of.

**EVERY TEST HERE IS ABOUT A NUMBER THAT WOULD LOOK FINE IF IT WERE WRONG.**
The mean-of-codes defect produces a *valid* code; an autoscaled fraction map
produces a *plausible* picture; a block divided by its own cell count instead of
its population produces a *smaller* failure fraction with no tell at all. So no
test here asserts "a map was produced" -- each one plants a fixture where the
right answer and the defect's answer differ, and names which.
"""

from __future__ import annotations

import pathlib
from typing import Any

import numpy as np
import pytest

from metamer.core.outcomes import Outcome
from metamer.report.maps import (
    MAX_BLOCKS,
    REPORT_EXTRA,
    block_fractions,
    draw_all,
    matplotlib_available,
    plan_maps,
)
from metamer.report.reader import Completion, StoreView

#: The legend as the writer builds it -- `flag_values`/`flag_meanings` on
#: `/status/outcome`, which `reader._legend` returns as code to meaning.
_LEGEND = {member.code: str(member.value) for member in Outcome}


def _view(outcome: np.ndarray, *, legend: dict[int, str] | None = None) -> StoreView:
    """A view carrying a planted outcome cube and nothing else of substance."""
    rows, columns, models = outcome.shape
    return StoreView(
        path=pathlib.Path("/nonexistent"),
        outcome=np.asarray(outcome, dtype=np.uint8),
        delta_ic=np.zeros((rows, columns, models, 1), dtype=np.float32),
        selected=np.zeros((rows, columns, 1), dtype=np.int16),
        n_valid=np.zeros((rows, columns), dtype=np.int16),
        iterations=np.zeros(outcome.shape, dtype=np.uint16),
        model_labels=tuple(f"m{index}" for index in range(models)),
        criterion_labels=("aic",),
        attrs={},
        completion=Completion(complete=1, total=1),
        spatial={},
        disagreements=(),
        legend=_LEGEND if legend is None else legend,
    )


def test_a_blocks_fraction_is_over_its_population_not_over_its_cells():
    """T7-1: the denominator is the fit-verdict cells in the block.

    **Hand-derived from the fixture's literal counts.** One 4x4 block: 8 cells
    carry a fit verdict, of which **4** failed, and the other 8 carry
    `INSUFFICIENT_DATA`, which is covered but is not a fit verdict. The failure
    fraction among cells that could have failed is **4 / 8 = 0.5**.

    Bug this catches: reducing by `indicator.mean()` over the block, which
    divides by all 16 and reports **0.25** -- D2b's dilution drawn as a map. A
    coastal block that is half land would show half its real failure fraction,
    beside a statistic that does not have the defect, and nothing about the
    picture would look wrong.
    """
    codes = np.full((4, 4), Outcome.INSUFFICIENT_DATA.code, dtype=np.uint8)
    codes[0, :] = Outcome.DEGENERATE_HESSIAN.code
    codes[1, :] = Outcome.OK.code

    fit_verdict = np.isin(
        codes, [member.code for member in Outcome if member.is_fit_verdict]
    )
    failed = codes == Outcome.DEGENERATE_HESSIAN.code
    fraction, masked, block = block_fractions(failed, fit_verdict, block=(4, 4))

    assert block == (4, 4)
    assert fraction.shape == (1, 1)
    assert not masked[0, 0]
    assert fraction[0, 0] == pytest.approx(0.5)
    # The diluted answer, named so a regression cannot be read as a new baseline.
    assert fraction[0, 0] != pytest.approx(0.25)


def test_a_block_with_no_population_is_masked_and_never_zero():
    """T7-1: an empty denominator is unavailable, not `0.0`.

    Bug this catches: a `0 / 0 -> 0` guard, or `np.divide`'s default `out`,
    which makes an all-land block report **no failures**. With `vmin=0` fixed,
    0.0 is the bottom of `viridis`, so the emptiest part of the map renders as
    the healthiest -- the `fitted == 0` rule, which this project already applies
    to printed rates, arriving in a colourmap.
    """
    codes = np.full((2, 4), Outcome.NOT_APPLICABLE.code, dtype=np.uint8)
    codes[:, :2] = Outcome.OK.code

    fit_verdict = codes == Outcome.OK.code
    failed = np.zeros_like(fit_verdict)
    fraction, masked, _ = block_fractions(failed, fit_verdict, block=(2, 2))

    assert fraction.shape == (1, 2)
    # Left block: 4 fit-verdict cells, none failed -> a real 0.0.
    assert not masked[0, 0]
    assert fraction[0, 0] == pytest.approx(0.0)
    # Right block: no fit-verdict cells at all -> masked, and nan rather than 0.
    assert masked[0, 1]
    assert np.isnan(fraction[0, 1])


def test_no_arithmetic_ever_reaches_an_outcome_code():
    """D9: the reduction is over a binary indicator, so `mean(7, 11)` cannot happen.

    **The fixture is the defect's own worked example.** A block holding only
    `DEGENERATE_HESSIAN` (7) and `ILL_CONDITIONED_X` (11) averages to 9, which
    is `CANDIDATE_DROPPED` -- a real, different, valid-looking code from the
    other side of section 12.5's grouping table: the cells say *this fit failed
    twice over* and their mean says *the run chose not to fit this candidate
    here*.

    Bug this catches: downsampling the code array itself. Asserted two ways --
    every finite value lies in [0, 1], and the specific poisoned value 9 is
    absent -- because "in [0, 1]" alone would also pass for a code array of
    zeros and ones.
    """
    assert Outcome.DEGENERATE_HESSIAN.code == 7
    assert Outcome.ILL_CONDITIONED_X.code == 11
    # The arithmetic this design refuses, stated as a fact about the alphabet
    # rather than as a comment, so the test fails if the codes are renumbered.
    assert np.mean([7, 11]) == Outcome.CANDIDATE_DROPPED.code

    codes = np.array(
        [
            [Outcome.DEGENERATE_HESSIAN.code, Outcome.ILL_CONDITIONED_X.code],
            [Outcome.ILL_CONDITIONED_X.code, Outcome.DEGENERATE_HESSIAN.code],
        ],
        dtype=np.uint8,
    )[:, :, None]

    plan = plan_maps(_view(codes))
    values = np.concatenate(
        [entry.fraction[~entry.masked].ravel() for entry in plan.maps]
    )
    assert values.size > 0
    assert np.all((values >= 0.0) & (values <= 1.0))
    assert not np.any(values == float(Outcome.CANDIDATE_DROPPED.code))

    # **AND THE SAME CUBE REDUCED AS ONE BLOCK, WHICH IS WHERE A MEAN WOULD
    # SHOW.** `plan_maps` leaves a 2x2 grid undownsampled -- it is far below
    # `MAX_BLOCKS` -- so every block above holds a single cell and the fractions
    # are 0 or 1, which a code array of 0s and 1s would also satisfy. Forcing one
    # 2x2 block makes the honest answer 2/4 and the mean-of-codes answer 9.
    whole = block_fractions(
        np.asarray(codes[:, :, 0] == Outcome.DEGENERATE_HESSIAN.code),
        np.ones((2, 2), dtype=np.bool_),
        block=(2, 2),
    )[0]
    assert whole.shape == (1, 1)
    assert whole[0, 0] == pytest.approx(0.5)


def test_a_branch_in_neither_population_gets_no_map_and_is_reported():
    """A present branch with no denominator is named, not drawn as zero.

    `NOT_ATTEMPTED` is neither `is_fit_verdict` nor `is_covered`, so it is a
    fraction of nothing.

    Bug this catches: mapping it over covered cells anyway, which yields
    `0 / covered` in **every** block -- an all-zero map of a branch that is
    present, rendering under fixed limits as uniform dark purple and reading as
    *this never happens* for the one code an interrupted store is full of. This
    was a real defect in the first draft of `plan_maps`, found before it
    shipped; dropping the branch silently is the same error one step quieter.
    """
    assert not Outcome.NOT_ATTEMPTED.is_fit_verdict
    assert not Outcome.NOT_ATTEMPTED.is_covered

    codes = np.array([[Outcome.OK.code, Outcome.NOT_ATTEMPTED.code]], dtype=np.uint8)[
        :, :, None
    ]
    plan = plan_maps(_view(codes))

    assert Outcome.NOT_ATTEMPTED.code not in {entry.branch for entry in plan.maps}
    unmapped = {code: reason for code, _, reason in plan.unmapped}
    assert set(unmapped) == {Outcome.NOT_ATTEMPTED.code}
    assert "not a fraction of anything" in unmapped[Outcome.NOT_ATTEMPTED.code]


def test_a_non_fit_branch_is_a_coverage_map_over_covered_cells():
    """T7-1: a non-fit branch is labelled coverage, never failure.

    `INSUFFICIENT_DATA` is covered and is not a fit verdict, so it has no fit
    verdict to fail.

    Bug this catches: giving every branch the fit-verdict denominator and the
    word "failure", which puts a decision the run took on the same axis as a fit
    that broke -- D1's tell, a name saying one thing while the value is another.
    """
    codes = np.array(
        [[Outcome.OK.code, Outcome.INSUFFICIENT_DATA.code]], dtype=np.uint8
    )[:, :, None]
    plan = plan_maps(_view(codes))

    kinds = {entry.branch: entry.kind for entry in plan.maps}
    populations = {entry.branch: entry.population for entry in plan.maps}
    assert kinds[Outcome.OK.code] == "failure"
    assert kinds[Outcome.INSUFFICIENT_DATA.code] == "coverage"
    assert "fit-verdict cells" in populations[Outcome.OK.code]
    assert "covered cells" in populations[Outcome.INSUFFICIENT_DATA.code]


def test_the_title_names_the_branch_from_the_stores_own_legend():
    """The store's alphabet supplies the title, not this build's `Outcome`.

    **The fixture's legend deliberately disagrees with `Outcome`**: code 7 is
    spelled `ancient_name`. A store written by an older build must have its own
    spelling in its titles.

    Bug this catches: a title written from a hard-coded name table or from the
    local enum, which drifts from the store's alphabet -- so a report about an
    older store would describe a code table that store never used. The
    assertion is both halves: the store's name present AND the local name
    absent, because present-only would pass for a title carrying both.
    """
    codes = np.full((1, 1, 1), Outcome.DEGENERATE_HESSIAN.code, dtype=np.uint8)
    plan = plan_maps(
        _view(codes, legend={Outcome.DEGENERATE_HESSIAN.code: "ancient_name"})
    )

    titles = [entry.title for entry in plan.maps]
    assert titles
    assert all("ancient_name" in title for title in titles)
    assert not any(str(Outcome.DEGENERATE_HESSIAN.value) in title for title in titles)
    # And the population is on the image, because the fraction means nothing
    # without its denominator.
    assert all("fit-verdict cells" in title for title in titles)


def test_a_code_the_legend_does_not_describe_is_titled_by_its_number():
    """The empty-legend boundary: absent is answered, not guessed.

    Bug this catches: a `KeyError` on a store that wrote no flag attributes, or
    a silent fallback to the local `Outcome` name -- which is the drift the test
    above forbids, arriving through the error path instead of the happy one.
    """
    codes = np.full((1, 1, 1), Outcome.OK.code, dtype=np.uint8)
    plan = plan_maps(_view(codes, legend={}))

    assert plan.maps
    assert all(f"code {Outcome.OK.code}" in entry.title for entry in plan.maps)


def test_the_map_set_is_every_present_branch_times_every_candidate_plus_the_point_map():
    """D9's inventory, enumerated rather than counted.

    Two candidates, two mappable branches present: four per-candidate maps and
    two point-level maps.

    Bug this catches: map and statistic drifting onto different populations --
    a branch dropped because it occurs in only one candidate, or a point-level
    map computed as a mean of the per-candidate maps rather than over the
    any-candidate population, which D7 forbids.
    """
    codes = np.array(
        [
            [[Outcome.OK.code, Outcome.DEGENERATE_HESSIAN.code]],
            [[Outcome.DEGENERATE_HESSIAN.code, Outcome.OK.code]],
        ],
        dtype=np.uint8,
    )
    assert codes.shape == (2, 1, 2)
    plan = plan_maps(_view(codes))

    pairs = {(entry.branch, entry.candidate) for entry in plan.maps}
    assert pairs == {
        (Outcome.OK.code, "m0"),
        (Outcome.OK.code, "m1"),
        (Outcome.OK.code, None),
        (Outcome.DEGENERATE_HESSIAN.code, "m0"),
        (Outcome.DEGENERATE_HESSIAN.code, "m1"),
        (Outcome.DEGENERATE_HESSIAN.code, None),
    }
    assert len(plan.maps) == len(pairs)


def test_an_indivisible_grid_keeps_each_edge_blocks_real_denominator():
    """Padding adds cells outside the population, never population.

    A 3x1 column of fit-verdict cells reduced by 2x1 blocks: the first block
    holds two cells, the second holds one real cell plus one pad cell. With the
    first cell failed, the fractions are **0.5** and **0.0** by hand -- the
    second block's denominator is 1, not 2.

    Bug this catches: padding the population with `True`, which gives the edge
    block a denominator of 2 and halves its fraction; or padding the counts,
    which invents population. Both dilute exactly the blocks at a grid's edge,
    where a global map's seam lives.
    """
    population = np.ones((3, 1), dtype=np.bool_)
    indicator = np.array([[True], [False], [False]])
    fraction, masked, _ = block_fractions(indicator, population, block=(2, 1))

    assert fraction.shape == (2, 1)
    assert not masked.any()
    assert fraction[0, 0] == pytest.approx(0.5)
    assert fraction[1, 0] == pytest.approx(0.0)


def test_an_entirely_padded_block_cannot_exist_but_a_fully_masked_one_does():
    """The pad and the mask are the same mechanism, checked at the boundary.

    Bug this catches: a reshape that silently produces a block of pure padding
    and reports it as a real 0.0 rather than masked. `_block_side` cannot
    produce such a block -- ceil division never adds a whole empty block -- so
    the assertion is that the mask count equals the number of blocks with no
    population, which holds whatever the padding does.
    """
    population = np.zeros((4, 4), dtype=np.bool_)
    population[0, 0] = True
    fraction, masked, _ = block_fractions(
        np.zeros_like(population), population, block=(2, 2)
    )

    assert masked.sum() == 3
    assert not masked[0, 0]
    assert fraction[0, 0] == pytest.approx(0.0)
    assert np.isnan(fraction[masked]).all()


def test_mismatched_shapes_raise_rather_than_broadcasting():
    """The error path: a map of the wrong grid is worse than no map.

    Bug this catches: numpy broadcasting a `(4, 1)` indicator against a
    `(4, 4)` population into a plausible map of a grid neither array describes.
    """
    with pytest.raises(ValueError, match="same 2-D shape"):
        block_fractions(
            np.zeros((4, 1), dtype=np.bool_), np.zeros((4, 4), dtype=np.bool_)
        )
    with pytest.raises(ValueError, match="same 2-D shape"):
        block_fractions(
            np.zeros((4, 4, 2), dtype=np.bool_), np.zeros((4, 4, 2), dtype=np.bool_)
        )


def test_a_grid_larger_than_the_block_cap_is_downsampled_and_a_smaller_one_is_not():
    """`MAX_BLOCKS` bounds the output, and a small grid is the identity.

    Bug this catches: downsampling unconditionally, which blurs a small
    diagnostic grid for no reason, or never downsampling, which writes a PNG
    per cell for a 10^7-point store.
    """
    small = np.ones((MAX_BLOCKS, 4), dtype=np.bool_)
    _, _, block = block_fractions(small, small)
    assert block == (1, 1)

    big = np.ones((MAX_BLOCKS * 2, 4), dtype=np.bool_)
    fraction, _, block = block_fractions(big, big)
    assert block == (2, 1)
    assert fraction.shape[0] <= MAX_BLOCKS


def test_without_matplotlib_every_map_is_still_recorded_and_the_extra_is_named(
    monkeypatch, tmp_path
):
    """D10: the numbers path survives an absent plotting stack.

    Bug this catches: a hard dependency smuggled in -- the report falling over,
    or falling silent about the maps, on a store read in an environment that
    installed only the base package. `test_readme_figure.py`'s docstring records
    the real instance: importing a figure generator dragged matplotlib into the
    suite, which passed locally and failed in CI on its first push.

    The absence is simulated at `matplotlib_available`'s own seam rather than by
    deleting the module, because this test is about what `draw_all` does with
    the answer; the import graph itself is measured by the subprocess probe.
    """
    monkeypatch.setattr("metamer.report.maps.matplotlib_available", lambda: False)

    codes = np.full((2, 2, 1), Outcome.DEGENERATE_HESSIAN.code, dtype=np.uint8)
    record = draw_all(_view(codes), tmp_path)

    assert record["drawn"] is False
    assert record["extra"] == REPORT_EXTRA
    assert record["maps"], "a store with a present branch must still earn a record"
    for entry in record["maps"]:
        assert entry["drawn"] is False
        assert entry["extra"] == REPORT_EXTRA
        assert "png" not in entry
        # The numbers are present whether or not the picture is.
        assert entry["population"]
        assert entry["block"] == [1, 1]
    assert not list(tmp_path.iterdir()), "nothing may be written without matplotlib"


@pytest.mark.skipif(
    not matplotlib_available(), reason="the [report] extra is not installed"
)
def test_draw_fixes_the_colour_limits_at_zero_and_one_whatever_the_range(tmp_path):
    """D9: `draw` passes fixed limits, on a fixture whose range is 1%.

    **THE LIMITS ARE CAPTURED AT THE LIBRARY SEAM, NOT RE-ASSERTED.** An earlier
    version of this test drew a fresh `imshow` with `vmin=0, vmax=1` and
    asserted `get_clim() == (0, 1)` -- which checks that matplotlib honours
    arguments the *test* passed, and would pass identically if `draw` autoscaled.
    So `imshow` is wrapped and the kwargs `draw` actually sends are the subject.

    The fixture's own range is 0.00 to 0.01: one failure among a hundred
    fit-verdict cells, reduced as a single block.

    Bug this catches: matplotlib's autoscale, under which that branch renders
    full-range and 1% looks like 100%, and two stores with different ranges are
    not comparable. **That is the mean-of-codes defect in continuous form** --
    not a wrong picture, a plausible one.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from metamer.report.maps import BranchMap, draw

    codes = np.full((10, 10), Outcome.OK.code, dtype=np.uint8)
    codes[0, 0] = Outcome.DEGENERATE_HESSIAN.code
    fraction, masked, block = block_fractions(
        codes == Outcome.DEGENERATE_HESSIAN.code,
        np.ones((10, 10), dtype=np.bool_),
        block=(10, 10),
    )
    assert fraction[0, 0] == pytest.approx(0.01), "the fixture's range must stay narrow"

    entry = BranchMap(
        branch=Outcome.DEGENERATE_HESSIAN.code,
        title="planted",
        candidate="m0",
        kind="failure",
        population="fit-verdict cells",
        fraction=fraction,
        masked=masked,
        block=block,
    )

    # **THE REAL AXES IS KEPT AND ITS ARTIST IS THE SUBJECT.** Patching
    # `Axes.imshow` does not work here and the reason is worth recording:
    # `pyplot` generates its module-level wrappers by introspecting Axes methods
    # and raises `RuntimeError: Wrapped method from unexpected class` on a
    # replacement. So the real call runs and `plt.subplots` is wrapped only to
    # keep a handle -- the artist survives `plt.close`, so the limits can be read
    # back off the object `draw` itself configured.
    captured: list[Any] = []
    original = plt.subplots

    def recording(*args, **kwargs):
        """Create the real figure and axes, keeping the axes for inspection."""
        figure, axes = original(*args, **kwargs)
        captured.append(axes)
        return figure, axes

    monkey = pytest.MonkeyPatch()
    try:
        monkey.setattr(plt, "subplots", recording)
        destination = draw(entry, tmp_path / "narrow.png")
    finally:
        monkey.undo()

    assert destination.exists()
    assert len(captured) == 1
    axes = captured[0]
    assert len(axes.images) == 1, "one image per map"
    assert axes.images[0].get_clim() == (0.0, 1.0)


@pytest.mark.skipif(
    not matplotlib_available(), reason="the [report] extra is not installed"
)
def test_a_masked_block_and_a_zero_block_are_different_colours():
    """T7-1: "nothing to fail" must not render as "nothing failed".

    Bug this catches: masked blocks drawn as 0.0. With `vmin=0` fixed, 0.0 is
    `viridis`'s darkest value, so an all-land block would be pixel-identical to
    a block whose every fit succeeded -- and on an ocean grid that is most of
    the image.
    """
    import matplotlib

    colours = matplotlib.colormaps["viridis"].with_extremes(bad="#b0b0b0")
    bottom = colours(0.0)
    bad = colours(np.ma.masked_invalid(np.array([np.nan])))[0]

    assert tuple(bottom) != tuple(bad)


def test_ci_covers_both_maps_environments_by_construction():
    """T7-2: one job installs `[report]`, at least one does not.

    **THE WORKFLOW IS THE SUBJECT, NOT A PROMISE ABOUT IT.** D10 has two halves
    and one environment can only test one: with matplotlib the maps are drawn and
    their colour limits checked, without it the no-matplotlib path runs. Before
    this, CI installed matplotlib nowhere, so every drawing test skipped in every
    job -- and a skip in all three jobs is indistinguishable from a pass.

    Bug this catches: the `[report]` job quietly disappearing -- a renamed extra,
    a dropped matrix row, a typo in the extras string -- which would take the
    drawing tests back to skipping everywhere while the run stayed green. It also
    catches the inverse: every job gaining the extra, which would leave the
    no-matplotlib path unexercised and is the easier mistake to make while
    debugging a skip.

    **AND IT CATCHES THE `include` TRAP, WHICH ALMOST SHIPPED.** A GitHub Actions
    `include` entry whose keys are all new is merged into *every* combination, so
    listing `python-version` only under `include` collapses three jobs into one.
    Asserting the expanded job count rather than the include count is what
    distinguishes them.
    """
    import itertools

    import yaml

    workflow = yaml.safe_load(
        (
            pathlib.Path(__file__).resolve().parents[1] / ".github/workflows/test.yml"
        ).read_text()
    )
    matrix = workflow["jobs"]["test"]["strategy"]["matrix"]

    combinations = list(itertools.product(matrix["os"], matrix["python-version"]))
    extras = {entry["python-version"]: entry["extras"] for entry in matrix["include"]}

    # Every expanded job has its extras decided, so a new version cannot inherit
    # a blank.
    undecided = {version for _, version in combinations} - set(extras)
    assert not undecided, f"matrix jobs with no extras decided: {sorted(undecided)}"
    assert len(combinations) >= 2, (
        "both halves of D10 need at least two jobs; one expanded job means the "
        "`include` entries collapsed into a single combination"
    )

    with_report = [v for v, value in extras.items() if REPORT_EXTRA in value.split(",")]
    without = [v for v, value in extras.items() if REPORT_EXTRA not in value.split(",")]
    assert len(with_report) == 1, (
        f"exactly one job must install [{REPORT_EXTRA}] so the maps are actually "
        f"drawn and checked; got {sorted(with_report)}"
    )
    assert without, (
        f"at least one job must omit [{REPORT_EXTRA}] so the no-matplotlib path "
        f"is exercised; every job installs it"
    )

    # The install step must actually consume the per-job value rather than a
    # hard-coded extras list, or the matrix above is decoration.
    steps = workflow["jobs"]["test"]["steps"]
    installs = [
        step["run"] for step in steps if "pip install" in str(step.get("run", ""))
    ]
    assert installs, "the test job must install the package"
    assert any("matrix.extras" in command for command in installs), (
        "the install step must use ${{ matrix.extras }}; a hard-coded extras list "
        "makes the per-job matrix above have no effect"
    )


@pytest.mark.skipif(
    not matplotlib_available(), reason="the [report] extra is not installed"
)
def test_draw_all_writes_one_png_per_map_named_for_its_subject(tmp_path):
    """The drawable path: a file per map, named by what it is OF.

    **THIS TEST EXISTS BECAUSE COVERAGE FOUND ITS ABSENCE.** The matplotlib-absent
    path was tested and this one was not, so the branch that actually writes PNGs
    -- and the filename logic -- had no test at all. Happy-path-only coverage
    inverted: only the failure path was exercised.

    Bug this catches: the filename identifying a map by its POSITION rather than
    its subject. An earlier draft built the stem from the loop index and spelled
    the candidate from the same number, so `m000`/`m001` tracked where a map fell
    in the inventory rather than which candidate it was about -- and a branch
    ceasing to occur silently renamed every file after it. Two candidates with a
    map of the same branch is the fixture that separates the two.
    """
    codes = np.array(
        [
            [[Outcome.DEGENERATE_HESSIAN.code, Outcome.OK.code]],
            [[Outcome.OK.code, Outcome.DEGENERATE_HESSIAN.code]],
        ],
        dtype=np.uint8,
    )
    record = draw_all(_view(codes), tmp_path)

    assert record["drawn"] is True
    assert record["extra"] is None
    assert record["maps"]

    written = sorted(path.name for path in tmp_path.iterdir())
    assert len(written) == len(record["maps"]), "one PNG per map, no collisions"
    for entry in record["maps"]:
        assert entry["drawn"] is True
        assert "extra" not in entry
        assert entry["png"] in written
        assert (tmp_path / entry["png"]).stat().st_size > 0

    # **THE NAMES CARRY THE SUBJECT.** Both candidates have a map of the failure
    # branch, and their filenames must differ by the CANDIDATE, not by an index.
    failure_pngs = {
        entry["candidate"]: entry["png"]
        for entry in record["maps"]
        if entry["branch"] == Outcome.DEGENERATE_HESSIAN.code
    }
    assert set(failure_pngs) == {"m0", "m1", None}
    assert len(set(failure_pngs.values())) == 3, "distinct subjects, distinct files"
    assert "m0" in failure_pngs["m0"]
    assert "m1" in failure_pngs["m1"]
    assert "point" in failure_pngs[None]
    for name in failure_pngs.values():
        assert f"code{Outcome.DEGENERATE_HESSIAN.code:02d}" in name
        assert "failure" in name


def test_matplotlib_availability_is_answered_and_never_raises(monkeypatch):
    """A broken install answers "unavailable" rather than propagating.

    Bug this catches: a partially installed distribution making `find_spec` raise
    -- which it does, rather than returning None -- and taking the whole numbers
    path down with it. The numbers path's entire purpose is to survive an absent
    or broken plotting stack, so an exception here defeats D10 exactly as a hard
    import would.
    """
    import importlib.util

    def exploding(name: str) -> None:
        """Stand in for a half-installed distribution.

        Args:
            name: The module being looked up.

        Raises:
            ValueError: Always; this is the failure being simulated.
        """
        raise ValueError(f"{name}.__spec__ is not set")

    monkeypatch.setattr(importlib.util, "find_spec", exploding)

    assert matplotlib_available() is False
