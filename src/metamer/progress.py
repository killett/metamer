"""Section 14.1's live counters: point-granularity tallies, display only.

**AT TEN HOURS, DISCOVERING A CONFIG BUG AT HOUR NINE IS THE EXPENSIVE
OUTCOME.** This module turns each tile's outcome codes into running totals a
human can read while a run is going, and it does nothing else.

**IT LIVES OUTSIDE `metamer.batch`, AND THAT IS THE ENFORCEMENT RATHER THAN A
FILING CHOICE.** Design doc section 14.1 says the counters are display-only and
that **no decision may read them**, because the obvious future change -- *"we
already have these tallies, let's abort on them"* -- reintroduces exactly the
tile-prefix bias section 14.1 exists to avoid, and **it will look like a free
optimization**. A comment cannot hold that. Two mechanisms do:

- **`metamer.batch` never imports this module**, asserted in a subprocess by
  `tests/test_progress.py`. The counters are physically unreachable from the
  run.
- **The seam that feeds them returns `None`.** `run`'s `on_tile_progress` is
  `Callable[[Tile, NDArray[np.uint8]], None]`, so nothing computed here can flow
  back into the loop even if somebody later wants it to.

**THE TALLIES ARE APPROXIMATE UNDER A RESUME, AND THAT IS DECLARED RATHER THAN
FIXED.** They accumulate what THIS process fitted, so a resumed run counts only
the tiles it did itself. That is harmless precisely because nothing reads them:
the early abort reads pass 1's stored status and section 14.2's report is
computed from the store. **Making them resume-exact would require reading the
store back per tile -- which would also suggest something depends on them.**

**PLAIN LINES, NOT `rich`.** Section 17's table gives Phase 2 plain lines and
Phase 5 the `rich` progress display. This module computes; Phase 5 renders.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from typing import TYPE_CHECKING

import numpy as np

from metamer.core.outcomes import Outcome

if TYPE_CHECKING:  # pragma: no cover - typing only
    from numpy.typing import NDArray

    from metamer.batch.tiling import Tile

#: Printed at the head of every counter line, so a reader grepping a log can
#: find them and a reader of the code can see they are one thing.
PREFIX = "progress:"


class LiveCounters:
    """Running point-granularity tallies, by outcome branch and by candidate.

    Attributes:
        candidates: The candidate labels, in store order.
    """

    def __init__(self, candidates: Sequence[str] = ()) -> None:
        """Start every tally at zero.

        **THE LABELS MAY ARRIVE LATER, AND USUALLY DO.** `__main__` holds a
        config PATH and not a `Config`, so it cannot name the candidates before
        the run starts; `run` passes them on every `record` call instead. They
        are adopted on the first one and are then fixed -- a later call carrying
        different labels is a bug in the caller, and is refused rather than
        silently re-labelling tallies already taken.

        Args:
            candidates: Candidate labels in outcome-column order, when the
                caller happens to know them.
        """
        self.candidates = tuple(candidates)
        self._tiles = 0
        self._by_branch: Counter[str] = Counter()
        self._by_candidate: list[Counter[str]] = [Counter() for _ in self.candidates]

    def record(
        self,
        tile: Tile,
        outcome: NDArray[np.uint8],
        candidates: Sequence[str] = (),
    ) -> None:
        """Accumulate one tile's outcomes.

        **COUNTS POINTS, NOT TILES.** A tile-granularity tally is meaningless at
        ~10^5 points per tile: every tile contains some of everything, so every
        tile would report the same thing.

        Args:
            tile: The block just written. Unused except to count tiles; the
                counts come from `outcome`.
            outcome: Per-(series, candidate) codes, shape `(B, M)`.
            candidates: Candidate labels in column order. Adopted on the first
                call that supplies them.

        Raises:
            ValueError: If a later call supplies different labels, which would
                mean tallies already taken are attributed to the wrong
                candidates.
        """
        del tile  # counted, not inspected -- the tallies are over points
        codes = np.asarray(outcome, dtype=np.uint8)
        if candidates:
            incoming = tuple(candidates)
            if not self.candidates:
                self.candidates = incoming
                self._by_candidate = [Counter() for _ in incoming]
            elif incoming != self.candidates:
                raise ValueError(
                    f"candidate labels changed mid-run: {self.candidates} then "
                    f"{incoming}; tallies already taken would be mislabelled"
                )
        self._tiles += 1
        for column, counter in enumerate(self._by_candidate):
            if column >= codes.shape[1]:
                break
            values, counts = np.unique(codes[:, column], return_counts=True)
            for value, count in zip(values, counts, strict=True):
                name = Outcome.from_code(int(value)).value
                counter[name] += int(count)
                self._by_branch[name] += int(count)

    @property
    def tiles(self) -> int:
        """How many tiles have been recorded."""
        return self._tiles

    def by_branch(self) -> dict[str, int]:
        """Point counts per outcome branch, summed over candidates."""
        return dict(self._by_branch)

    def by_candidate(self) -> dict[str, dict[str, int]]:
        """Point counts per outcome branch, per candidate label."""
        return {
            label: dict(counter)
            for label, counter in zip(self.candidates, self._by_candidate, strict=True)
        }

    def lines(self) -> list[str]:
        """Render the current tallies as plain lines.

        Returns:
            One summary line plus one line per candidate. Empty when nothing
            has been recorded, so a caller need not special-case the start.
        """
        if not self._tiles:
            return []
        total = sum(self._by_branch.values())
        failed = sum(
            count for name, count in self._by_branch.items() if Outcome(name).is_failure
        )
        head = (
            f"{PREFIX} tiles={self._tiles}  fits={total}  "
            f"failed={failed} ({_percent(failed, total)})"
        )
        rows = [
            f"{PREFIX}   {label}: " + _render(counter)
            for label, counter in zip(self.candidates, self._by_candidate, strict=True)
            if counter
        ]
        return [head, *rows]


def _percent(part: int, whole: int) -> str:
    """Format a percentage, or `n/a` when the denominator is zero.

    Args:
        part: Numerator.
        whole: Denominator.

    Returns:
        A formatted string.
    """
    if whole == 0:
        return "n/a"
    return f"{100.0 * part / whole:.1f}%"


def _render(counter: Counter[str]) -> str:
    """Format one candidate's branch counts, largest first.

    Args:
        counter: Branch name to point count.

    Returns:
        A single line fragment.
    """
    ordered = sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    return "  ".join(f"{name}={count}" for name, count in ordered)
