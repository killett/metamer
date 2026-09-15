"""Section 14.1's live counters, and the boundary that keeps them display-only."""

from __future__ import annotations

import subprocess
import sys

import numpy as np
import pytest

from metamer.batch.tiling import Tile
from metamer.core.outcomes import Outcome
from metamer.progress import PREFIX, LiveCounters

_LABELS = ("white", "white + matern12")

# A REAL `Tile` RATHER THAN `None`. `record` does not inspect it -- the tallies
# are over points -- but passing the type the seam declares keeps these calls
# exercising the same signature `run` calls, and mypy says so.
_TILE = Tile(y_start=0, y_stop=1, x_start=0, x_stop=3)


def _codes(*rows: tuple[Outcome, Outcome]) -> np.ndarray:
    """Build a `(B, M)` outcome-code block from members, for readability."""
    return np.array([[a.code, b.code] for a, b in rows], dtype=np.uint8)


def test_the_batch_package_never_imports_the_counters():
    """The import boundary is what makes "no decision may read them" true.

    Design doc section 14.1 says the counters are display-only and that no
    decision may read them, **and says why the rule needs teeth**: the obvious
    future change -- "we already have these tallies, let's abort on them" --
    reintroduces the tile-prefix bias section 14.1 exists to avoid, and **it
    will look like a free optimization**. A comment cannot stop that; an import
    boundary can.

    Run in a SUBPROCESS deliberately, for the reason
    `tests/test_core_isolation.py` already gives about its own boundary: inside
    the pytest session `metamer.progress` is imported by this very module, so an
    in-process check would pass against any `metamer.batch` at all -- it would
    be measuring the session rather than the import graph.

    Expected value determined independently: from the direction of the
    dependency. The display reads the run's output; the run must not read the
    display. `metamer.progress` may import from `metamer.batch` (it does, for
    `Tile`, under `TYPE_CHECKING`) and not the reverse.

    Bug this catches: any wiring of the counters into the run -- the abort
    verdict reading a tally, a tile-prefix early abort, a `batch` module
    importing `LiveCounters` for convenience. **Each of those is a one-line
    change that passes every other test in this suite.**

    **PROVED TO BITE 2026-09-14:** a single
    `from metamer.progress import LiveCounters` was added to
    `metamer/batch/run.py` and this test failed. **No other test in the suite
    changed colour** -- which is the point: the wiring is invisible to
    behaviour until somebody reads a tally, and by then the bias is shipped.
    """
    code = (
        "import metamer.batch.run, metamer.batch.twopass, sys; "
        "leaked = [m for m in sys.modules if m == 'metamer.progress']; "
        "assert not leaked, leaked"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )

    assert result.returncode == 0, result.stderr


def test_the_counters_import_without_rich():
    """Phase 2 prints plain lines; the `rich` display is Phase 5's.

    Section 17's table gives Phase 2 "plain lines" and Phase 5 "the `rich`
    progress display (section 14.1)". Section 14.1's own sentence names `rich`,
    which reads as a conflict and is not one: this module computes the tallies
    and Phase 5 renders them -- the same computation-versus-interface split that
    put section 14.2's report in 2f and its subcommand in Phase 5.

    Expected value determined independently: from section 17's table, not from
    this module's imports.

    Bug this catches: Phase 5's interface pulled forward, which would design the
    progress display before `validate --explain` exists to say what the command
    tree looks like -- and would add a dependency to the batch install for a
    line of output.
    """
    code = (
        "import metamer.progress, sys; "
        "assert 'rich' not in sys.modules, sorted(sys.modules)[:0] or 'rich'"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )

    assert result.returncode == 0, result.stderr


def test_the_tallies_count_points_and_not_tiles():
    """Point granularity, asserted on counts rather than on a docstring.

    Expected values determined independently by counting the constructed blocks
    by hand: two tiles of three points each, two candidates. Candidate 0 is OK
    at all six points. Candidate 1 is `DEGENERATE_HESSIAN` at four of them and
    OK at two. So 12 fits, 4 failures, and the totals are over POINTS.

    Bug this catches: a tile-granularity tally -- incrementing one counter per
    tile by the tile's dominant outcome, or counting tiles that "contain a
    failure". At ~10^5 points per tile every tile contains some of everything,
    so such a tally reports the same thing for every tile and is a plausible
    progress display that carries no information. Section 14.1 says a
    tile-granularity verdict is meaningless at that scale; this is that sentence
    as arithmetic.
    """
    counters = LiveCounters()
    first = _codes(
        (Outcome.OK, Outcome.DEGENERATE_HESSIAN),
        (Outcome.OK, Outcome.DEGENERATE_HESSIAN),
        (Outcome.OK, Outcome.OK),
    )
    second = _codes(
        (Outcome.OK, Outcome.DEGENERATE_HESSIAN),
        (Outcome.OK, Outcome.DEGENERATE_HESSIAN),
        (Outcome.OK, Outcome.OK),
    )

    counters.record(_TILE, first, _LABELS)
    counters.record(_TILE, second, _LABELS)

    assert counters.tiles == 2
    assert counters.by_branch() == {"ok": 8, "degenerate_hessian": 4}
    assert counters.by_candidate() == {
        "white": {"ok": 6},
        "white + matern12": {"degenerate_hessian": 4, "ok": 2},
    }


def test_the_failure_count_uses_the_taxonomy_and_not_a_name_test():
    """A decided skip is not a failure, here as everywhere.

    Expected values determined independently: `CANDIDATE_DROPPED` is a decided
    skip per design doc section 12.5's grouping table, so of these six fits two
    failed -- the `DEGENERATE_HESSIAN` pair -- and the three dropped ones are
    not failures.

    Bug this catches: a display computing "failed" as "not OK", which is the
    obvious shortcut and is wrong for every member of the decided-skip group.
    **The display is where that error is most expensive**: a run that dropped a
    candidate on purpose would report a failure rate of 83% while the store says
    33%, and the operator reads the display.
    """
    counters = LiveCounters()
    counters.record(
        _TILE,
        _codes(
            (Outcome.OK, Outcome.CANDIDATE_DROPPED),
            (Outcome.DEGENERATE_HESSIAN, Outcome.CANDIDATE_DROPPED),
            (Outcome.DEGENERATE_HESSIAN, Outcome.CANDIDATE_DROPPED),
        ),
        _LABELS,
    )

    head = counters.lines()[0]

    assert "fits=6" in head
    assert "failed=2" in head
    assert "33.3%" in head


def test_the_approximation_lives_in_the_counters_and_nowhere_else():
    """A resumed run under-counts, and that is the declared behaviour.

    The counters accumulate what THIS process fitted, so a resumed run counts
    only its own tiles. Section 14.1 calls that harmless **because nothing reads
    them** -- the early abort reads pass 1's stored status and section 14.2's
    report is computed from the store.

    Expected values determined independently by hand: a counter given two tiles
    sees six fits; one given the second tile alone sees three. The store would
    hold all six either way, which is the half that matters.

    Bug this catches: the counters being made resume-exact by reading each
    tile's region back from the store. That sounds like an improvement and is
    the opposite -- it costs a read per tile, and **it would suggest something
    depends on them**, which is the belief section 14.1 is trying to prevent.
    (i2): this is the positive control on the word "harmless", since a test that
    only asserted the totals are right could not distinguish the two designs.
    """
    block = _codes(
        (Outcome.OK, Outcome.OK),
        (Outcome.OK, Outcome.DEGENERATE_HESSIAN),
        (Outcome.OK, Outcome.OK),
    )
    whole = LiveCounters()
    whole.record(_TILE, block, _LABELS)
    whole.record(_TILE, block, _LABELS)

    resumed = LiveCounters()
    resumed.record(_TILE, block, _LABELS)

    assert sum(whole.by_branch().values()) == 12
    assert sum(resumed.by_branch().values()) == 6
    assert resumed.by_branch() != whole.by_branch()


def test_labels_arriving_late_are_adopted_and_labels_changing_are_refused():
    """The caller holds a config path, so the labels ride on the seam.

    `__main__` cannot name the candidates before the run starts -- it has a
    path, not a `Config` -- so `run` passes the labels on every call and the
    first one is adopted.

    Expected values determined independently: adoption means the tallies come
    out under the supplied names; refusal means a second, different tuple
    raises rather than re-labelling counts already taken.

    Bug this catches: labels silently replaced mid-run, which would attribute
    one candidate's tallies to another. **Every count already taken would be
    wrong and nothing would say so** -- the display would simply name the last
    candidate set it saw.
    """
    counters = LiveCounters()
    block = _codes((Outcome.OK, Outcome.OK))

    counters.record(_TILE, block, _LABELS)
    assert set(counters.by_candidate()) == set(_LABELS)

    with pytest.raises(ValueError, match="mislabelled"):
        counters.record(_TILE, block, ("white", "something else"))


def test_nothing_is_rendered_before_anything_is_recorded():
    """An empty counter prints nothing rather than a row of zeros.

    Expected value determined independently: there is no run to describe yet, so
    the honest output is none. A caller need not special-case the start.

    Bug this catches: a display emitting `fits=0 failed=0 (n/a)` before the
    first tile, which at the head of a ten-hour log reads as a completed run
    that fitted nothing.
    """
    assert LiveCounters().lines() == []
    assert LiveCounters(_LABELS).lines() == []
    assert PREFIX


def test_a_line_is_plain_text_with_no_control_characters():
    """Plain lines, asserted rather than described.

    Expected value determined independently: section 17 gives Phase 2 plain
    lines, so every character emitted is printable.

    Bug this catches: ANSI colour or cursor movement creeping in -- which is
    invisible in a terminal and corrupts a redirected log, and which is how a
    `rich`-shaped display arrives without importing `rich`.
    """
    counters = LiveCounters()
    counters.record(_TILE, _codes((Outcome.OK, Outcome.OK)), _LABELS)

    for line in counters.lines():
        assert line.startswith(PREFIX)
        assert line.isprintable(), repr(line)
