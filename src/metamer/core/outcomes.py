"""The failure taxonomy.

Non-convergence is not one outcome. At 10^7 series nobody inspects individual
fits, so the map of *which* failure occurred *where* is itself the diagnostic.
This is an enum written to the output, never a boolean `converged` flag.
"""

from __future__ import annotations

from enum import StrEnum

import numpy as np
from numpy.typing import NDArray


class Outcome(StrEnum):
    """Per (point, candidate) fit outcome."""

    OK = "ok"
    ITER_CAP_SMALL_GRAD = "iter_cap_small_grad"
    ITER_CAP_LARGE_GRAD = "iter_cap_large_grad"
    DIAGNOSTIC_LIMIT = "diagnostic_limit"
    TRUST_RADIUS_COLLAPSED = "trust_radius_collapsed"
    NONFINITE_OBJECTIVE = "nonfinite_objective"
    RANK_DEFICIENT_X = "rank_deficient_x"
    DEGENERATE_HESSIAN = "degenerate_hessian"
    ILL_CONDITIONED_X = "ill_conditioned_x"
    NOT_ATTEMPTED = "not_attempted"
    CANDIDATE_DROPPED = "candidate_dropped"
    INSUFFICIENT_DATA = "insufficient_data"
    SCREENED_OUT = "screened_out"
    NOT_APPLICABLE = "not_applicable"

    @property
    def is_eligible(self) -> bool:
        """Whether this point counts toward a failure-rate denominator.

        INSUFFICIENT_DATA is a legitimate expected outcome -- land, permanent
        ice, or too few valid samples -- and is excluded.
        """
        return self not in {Outcome.INSUFFICIENT_DATA, Outcome.NOT_APPLICABLE}

    @property
    def is_failure(self) -> bool:
        """Whether this outcome counts as a failure.

        Every member not excluded below is a failure, including
        ITER_CAP_SMALL_GRAD: design doc section 8.6 describes hitting the
        iteration cap with a small gradient as "probably fine, flagged" --
        flagged, not excluded. Excluding it here would make a real (if mild)
        non-convergence invisible in the spatial failure map, which at 10^7
        series is the diagnostic that matters.

        **THE DECIDED-SKIP GROUP IS SPECIFIED AT DESIGN DOC SECTION 12.5 AND IS
        NOT RE-ARGUED HERE.** That section's non-fit grouping table carries the
        rule -- *"the grouping is what section 14.2's denominator reads"* -- and
        classifies `SCREENED_OUT` and `CANDIDATE_DROPPED` identically, as
        **legitimate non-fits**. A code the run assigns *because the run chose
        not to fit* is eligible and is not a failure. **A future member is
        classified by that rule, at that section**; three statements of one rule
        is how a count in this project reached twelve sites.

        **`CANDIDATE_DROPPED` JOINED THE GROUP AT 2e's TASK 1 GROUPING PASS
        (2026-09-14), AND THAT WAS A CORRECTION RATHER THAN A DECISION.** It sat
        in the failure set from 2a while section 12.5 said otherwise, and
        **nothing caught the disagreement because the member has no producer** --
        2e's early abort is its first. A classification that has never been
        exercised has never been checked. The argument was also already in the
        suite, at the sibling: `SCREENED_OUT`'s test says counting a decided skip
        as a failure "would make a *cheaper* configuration report a worse failure
        rate", which is true of a dropped candidate word for word.

        **The consequence that makes it matter** is that the early abort drops a
        candidate *because* it failed, then writes `CANDIDATE_DROPPED` at every
        remaining point -- so a rate computed over those points would report the
        decision rather than the candidate, and would read louder than the
        evidence that triggered it. See the handoff's (j7b).

        **`INSUFFICIENT_DATA`'s exclusion follows section 8.6, which section 12.5
        contradicts** -- open question 24, filed to 2f. It is left alone here
        because it has producers: changing it re-baselines every failure rate,
        which is a different act from a correction that cannot move a number.
        """
        return self not in {
            Outcome.OK,
            Outcome.NOT_ATTEMPTED,
            Outcome.INSUFFICIENT_DATA,
            Outcome.SCREENED_OUT,
            Outcome.CANDIDATE_DROPPED,
            Outcome.NOT_APPLICABLE,
        }

    @property
    def code(self) -> int:
        """Stable integer code, for the batched arrays and the zarr schema."""
        return _CODES[self]

    @classmethod
    def from_code(cls, value: int) -> Outcome:
        """Invert `code`."""
        return _BY_CODE[int(value)]


# Stable on-disk codes. NEVER renumber: they are written to the zarr store as
# uint8 and a renumbering silently reinterprets every archived run. Adding a new
# member takes the next free code and bumps the store's schema_version.
_CODES: dict[Outcome, int] = {
    Outcome.OK: 0,
    Outcome.ITER_CAP_SMALL_GRAD: 1,
    Outcome.ITER_CAP_LARGE_GRAD: 2,
    Outcome.DIAGNOSTIC_LIMIT: 3,
    Outcome.TRUST_RADIUS_COLLAPSED: 4,
    Outcome.NONFINITE_OBJECTIVE: 5,
    Outcome.RANK_DEFICIENT_X: 6,
    Outcome.DEGENERATE_HESSIAN: 7,
    Outcome.NOT_ATTEMPTED: 8,
    Outcome.CANDIDATE_DROPPED: 9,
    Outcome.INSUFFICIENT_DATA: 10,
    Outcome.ILL_CONDITIONED_X: 11,
    Outcome.SCREENED_OUT: 12,
    Outcome.NOT_APPLICABLE: 13,
}
_BY_CODE: dict[int, Outcome] = {code: member for member, code in _CODES.items()}


def outcome_array(batch: int, outcome: Outcome = Outcome.OK) -> NDArray[np.uint8]:
    """Return a per-series outcome array filled with one value.

    Outcomes are PER SERIES wherever they cross a batched boundary. A scalar
    outcome for a batch of B means one bad grid point marks all B as failed,
    which contradicts both "(B, N) is the only code path" and the output
    schema's per-(point, model) status -- and turns the spatial failure map,
    which is itself a diagnostic, into a picture of the tile grid.
    """
    return np.full(batch, outcome.code, dtype=np.uint8)
