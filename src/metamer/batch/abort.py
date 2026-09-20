"""Section 14.1's early abort: the VERDICT, which is a pure function.

**THE DECISION AND THE ACTION ARE TWO THINGS, AND ONLY ONE OF THEM IS A STORE
READER.** This module holds the first: a finished pass-1 store goes in, a
verdict comes out, and nothing else is consulted -- no clock, no environment, no
process state. The second -- returning `ABORTED_EARLY`, demoting a candidate,
writing `CANDIDATE_DROPPED` across the rest of pass 2 -- changes what a run
does and lives with the run.

**THE SPLIT BUYS A TEST.** A verdict that could only be exercised through a full
two-pass run would be expensive to check and therefore rarely checked; this one
is a function of a constructed store, so the boundary cases below are cheap
assertions rather than ten-hour experiments. Same discipline as section 14.2's
report being computed from the store, and for the same reason.

**THE POPULATION IS THE COARSE GRID.** Pass 1 fits a decimated grid, so this
rate is a SAMPLE and is not the run's failure rate -- section 14.2's report is
computed from the full store and is the one that describes the run. Section
14.1 already accounts for that: the thresholds here are calibrated *"to catch
bugs, not to second-guess science"*, and a candidate failing 95% of a
stratified sample is a capability or parameterization error whatever the
sampling. **Two numbers, two populations, and this one is the smaller.**

**AND THE SAMPLE IS STRATIFIED BY CONSTRUCTION**, which is why the abort is
evaluated here rather than on a prefix of tiles. Tiles are processed in spatial
order, so "the first 1% of eligible points" is a geographically contiguous
strip -- on a global grid a polar band or a single basin -- and both failure
rates and spectral regimes vary enormously by region.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Literal

import numpy as np
import zarr
from numpy.typing import NDArray

from metamer.batch.completion import completed_tiles
from metamer.batch.resume import _refuse
from metamer.core.outcomes import Outcome

#: Section 14.1's default. **Strictly greater**: a candidate at exactly this
#: rate continues. The sentence is *"> 90% failure"*, the side is invisible on
#: any realistic fixture, and a boundary nobody states is a boundary nobody
#: tests.
DEFAULT_FAILURE_THRESHOLD = 0.90


class CandidateFailurePolicy(StrEnum):
    """What to do when a SINGLE candidate fails above the threshold.

    Section 14.1: abort by default, with `--on-candidate-failure` to choose.
    Dropping one failing candidate and continuing with the rest is often the
    useful action, and it is not the safe default.
    """

    ABORT = "abort"
    DROP = "drop"
    CONTINUE = "continue"


@dataclass(frozen=True)
class CandidateRate:
    """One candidate's failure rate over pass 1, with its own denominator.

    **THE DENOMINATOR IS PER CANDIDATE AND IS REPORTED, NOT ASSUMED SHARED.**
    Eligibility is a property of an outcome CODE and codes live on the
    `(y, x, m)` axis, so two candidates' rates are over different populations
    and a table showing rates without denominators invites a comparison that is
    not available.

    **In v1 they happen to be equal**, because `fit.py` computes
    `design_info(t, mask)` once before the candidate loop, so the design-derived
    outcomes are constant along the model axis. That is an implementation
    property and not a contract -- it holds until a joint signal x noise search
    lands -- which is why this is a field rather than a comment.

    **`fitted` AND `eligible` ARE TWO COUNTS AND THIS VERDICT READS THE FIRST
    FOR BOTH ITS QUESTIONS (2026-09-19, extended 2026-09-20).** `eligible` is
    section 14.2's failure-rate population. `fitted` is whether the store is
    making a fit claim at all, by section 12.5's non-fit grouping table through
    `Outcome.is_fit_verdict`. `fitted <= eligible` always.

    **THE RATE'S DENOMINATOR IS `fitted`, AND THAT IS CORRECT IN BOTH ERAS
    RATHER THAN CONVENIENT IN THIS ONE.** This gate asks whether a candidate is
    failing the fits it ATTEMPTS. That question has nothing to do with how much
    of the box is out of domain, and it will still have nothing to do with it
    after section 13.6's declared domain mask makes land `NOT_APPLICABLE`. **A
    gate whose denominator is land-sensitive is broken whether or not
    `INSUFFICIENT_DATA` is eligible**; open question 24 only exposed it.

    **MEASURED, on exit criterion 12's own fixture (2026-09-20).** Twelve ocean
    points and eight land points, a candidate failing all twelve: over
    `eligible` the full store reads **12/20 = 0.60 and continues** while its
    ocean crop reads **12/12 = 1.00 and drops** -- the same data, two verdicts,
    which is the defect that criterion's docstring exists to catch. Over
    `fitted` both read **12/12** and both drop. `fitted` is 12 in both stores.

    **`eligible` IS STILL COUNTED AND RECORDED**, because section 14.2's report
    is over that population and the gap between the two counts is the store's
    land-and-thin-record exposure -- a quantity worth printing, not discarding.

    **SEVENTH INSTANCE OF ONE ROOT CAUSE:** `is_eligible` was doing two jobs.
    The first repair moved judgeability off it; this moves the rate off it.

    Attributes:
        candidate: The label, as the store records it.
        failed: Eligible points this candidate failed, by `Outcome.is_failure`.
        eligible: Points where this candidate was in section 14.2's
            failure-rate population, by `Outcome.is_eligible`. **Recorded, and
            NOT this verdict's denominator** -- see `rate`.
        fitted: Points where the store records a fit verdict for this
            candidate, by `Outcome.is_fit_verdict`. **This verdict's
            denominator, and what `no_evidence` reads.**
        rate: `failed / fitted`, or **None when `fitted` is zero** -- see
            `abort_verdict` on why that is not the same as zero.
    """

    candidate: str
    failed: int
    eligible: int
    fitted: int
    rate: float | None


@dataclass(frozen=True)
class AbortVerdict:
    """What section 14.1 says to do, and the numbers it says it from.

    **FOUR OUTCOMES, NOT THREE, AND THE FOURTH IS NOT A KIND OF `continue`.**
    *"Continued because there was nothing to judge"* and *"continued because
    everything passed"* are different facts about a run, and the outcome
    vocabulary exists because such facts get collapsed. `no_evidence` is
    what the run does with an empty coarse sample (decided 2026-09-18, section
    14.1): it proceeds, the final line says so, and the store's `early_abort`
    attrs record it under this name.

    Attributes:
        action: `"continue"`, `"abort"`, `"drop"`, or `"no_evidence"`.
        candidates: The candidates to drop, empty unless `action` is `"drop"`.
        rates: Every candidate's rate, in store order, whatever the action.
        threshold: The rate compared against, carried so a reading is
            reproducible without knowing the caller's defaults.
        reason: One line naming why, for the final console line.
    """

    action: Literal["continue", "abort", "drop", "no_evidence"]
    candidates: tuple[str, ...]
    rates: tuple[CandidateRate, ...]
    threshold: float
    reason: str


def abort_verdict(
    pass1_store: Path | str,
    *,
    threshold: float = DEFAULT_FAILURE_THRESHOLD,
    policy: CandidateFailurePolicy = CandidateFailurePolicy.ABORT,
) -> AbortVerdict:
    """Decide section 14.1's early abort from a finished pass-1 store.

    **AN EMPTY ELIGIBLE POPULATION IS A FINDING, NOT A CLEAN BILL -- AND NOT
    AN ABORT EITHER.** The rate is `failed / eligible`, and with no eligible
    points that is `0/0`: a naive implementation either raises -- a crash, on a
    well-formed store -- or yields `nan` or `0.0`, **both of which compare
    False against the threshold and read as "continue"**. So the empty sample
    is its own verdict, `no_evidence`, and it is never allowed to read as
    healthy.

    **DECIDED 2026-09-18, (b): NO EVIDENCE CONTINUES LOUDLY.** ~~It aborts and
    says so~~ was Task 5's reading (2026-09-14), on the argument that a config
    pointing at the wrong variable, or at a domain that is entirely land, gives
    `INSUFFICIENT_DATA` everywhere -- *"a config or data error"*. **2c's
    criterion-1 fixture refuted the argument on 2026-09-16**: land on every
    stride-2 row leaves the coarse lattice entirely masked while the odd rows
    carry data, so an empty sample is a statement about the SAMPLE and not
    about the run. Three reasons, recorded at section 14.1 and summarised
    here: a gate reading the wrong subject is the shape open question 22 cost
    this project to measure; a wrong abort is lifted only by `--no-early-abort`,
    which disables the mechanism everywhere, while a wrong continue costs one
    run that section 14.2's report then describes; and section 14.1 aborts on
    near-total failure PATTERNS because those are essentially always config
    errors -- an empty sample is no pattern at all. **The run proceeds to pass
    2 with the fine grid unjudged, the final line carries the headline, and
    the exit code is 0** because exit 1 is defined as the verdict finding a
    candidate above threshold, and this verdict found none.

    Args:
        pass1_store: A finished pass-1 store.
        threshold: Failure rate above which a candidate counts as failing.
            **Strictly greater**; exactly `threshold` continues.
        policy: What a single failing candidate does.

    Returns:
        The verdict, carrying every candidate's rate whatever the action.

    Raises:
        ValidationError: Layer 3, if the store has tiles outstanding. A rate
            over a partial store is a rate over a SPATIAL PREFIX wearing a
            whole-domain name, and the stratification is the whole reason the
            abort is evaluated here.
    """
    path = Path(pass1_store)
    done = completed_tiles(path)
    if not bool(done.all()):
        outstanding = int((~done).sum())
        raise _refuse(
            f"the pass-1 store at {path} has {outstanding} tiles outstanding, "
            "so an early-abort verdict taken from it would describe a "
            "geographically contiguous prefix rather than the stratified "
            "sample section 14.1 relies on. Finish or resume the coarse pass "
            "first; the same command does it"
        )

    root = zarr.open_group(str(path), mode="r")
    status = root["status"]
    assert isinstance(status, zarr.Group)  # noqa: S101 - store schema
    outcome_array = status["outcome"]
    assert isinstance(outcome_array, zarr.Array)  # noqa: S101 - store schema
    label_array = status["m"]
    assert isinstance(label_array, zarr.Array)  # noqa: S101 - store schema

    codes = np.asarray(outcome_array[:], dtype=np.uint8)
    labels = tuple(str(name) for name in np.asarray(label_array[:]).tolist())
    rates = tuple(
        _rate_for(labels[column], codes[:, :, column])
        for column in range(codes.shape[2])
    )
    return _decide(rates, threshold=threshold, policy=policy)


def _rate_for(label: str, codes: NDArray[np.uint8]) -> CandidateRate:
    """Tally one candidate's plane of outcome codes.

    Args:
        label: The candidate's label.
        codes: Its `(y, x)` outcome codes.

    Returns:
        The rate over FITTED points, with `rate=None` when nothing was fitted,
        and `eligible` counted separately because section 14.2's report is over
        that population.
    """
    eligible = 0
    failed = 0
    fitted = 0
    values, counts = np.unique(codes, return_counts=True)
    for value, count in zip(values, counts, strict=True):
        member = Outcome.from_code(int(value))
        if member.is_fit_verdict:
            fitted += int(count)
        if member.is_eligible:
            eligible += int(count)
            if member.is_failure:
                failed += int(count)
    return CandidateRate(
        candidate=label,
        failed=failed,
        eligible=eligible,
        fitted=fitted,
        rate=None if fitted == 0 else failed / fitted,
    )


def _decide(
    rates: tuple[CandidateRate, ...],
    *,
    threshold: float,
    policy: CandidateFailurePolicy,
) -> AbortVerdict:
    """Turn the tallies into section 14.1's verdict.

    Args:
        rates: Every candidate's rate, in store order.
        threshold: Compared against strictly.
        policy: What a single failing candidate does.

    Returns:
        The verdict.
    """
    # THE EMPTY GUARD COMES FIRST, AND ITS POSITION IS THE WHOLE DISTINCTION
    # between "the sample holds no evidence" and "every candidate failed":
    # with no judgeable candidate both `over` and `judgeable` are empty and
    # `len(over) == len(judgeable)` is `0 == 0`. Below the all-over check this
    # branch is unreachable and an empty sample aborts with the wrong reason.
    #
    # AND JUDGEABILITY IS `fitted`, NOT `rate is not None` (2026-09-19, open
    # question 24's check). `rate is not None` is `eligible > 0`, which is a
    # question about the failure-rate DENOMINATOR; this gate's question is
    # whether the sample holds a fit to judge. The two agree only while
    # `INSUFFICIENT_DATA` is out of the denominator -- section 8.6's reading,
    # superseded by section 12.5 -- and they disagree today on any decided
    # skip: an all-`SCREENED_OUT` sample has a full denominator and a rate of
    # exactly 0.0, and returned `continue`, "no candidate failed above 90%",
    # over a sample in which nothing was ever fitted. See
    # `Outcome.is_fit_verdict` for the pattern this is the third instance of.
    judgeable = [rate for rate in rates if rate.fitted > 0]
    if not judgeable:
        return AbortVerdict(
            action="no_evidence",
            candidates=(),
            rates=rates,
            threshold=threshold,
            reason=(
                "no point in the coarse pass was fitted for any candidate, so "
                "the sample holds no evidence and nothing was judged. The run "
                "continues with the fine grid unjudged; section 14.2's report "
                "is the only rate for it. Either every coarse point was out of "
                "domain or too thin to fit, or the candidates were all skipped "
                "before any fit ran"
            ),
        )

    over = [rate for rate in judgeable if (rate.rate or 0.0) > threshold]
    percent = f"{threshold:.0%}"
    if len(over) == len(judgeable):
        return AbortVerdict(
            action="abort",
            candidates=tuple(rate.candidate for rate in over),
            rates=rates,
            threshold=threshold,
            reason=(
                f"every candidate failed above {percent} of the coarse pass, "
                "which is a config or data error rather than a result"
            ),
        )
    if not over:
        return AbortVerdict(
            action="continue",
            candidates=(),
            rates=rates,
            threshold=threshold,
            reason=f"no candidate failed above {percent} of the coarse pass",
        )

    named = ", ".join(rate.candidate for rate in over)
    if policy is CandidateFailurePolicy.CONTINUE:
        return AbortVerdict(
            action="continue",
            candidates=(),
            rates=rates,
            threshold=threshold,
            reason=(
                f"{named} failed above {percent} of the coarse pass; "
                "--on-candidate-failure=continue keeps it"
            ),
        )
    action: Literal["abort", "drop"] = (
        "drop" if policy is CandidateFailurePolicy.DROP else "abort"
    )
    return AbortVerdict(
        action=action,
        candidates=tuple(rate.candidate for rate in over),
        rates=rates,
        threshold=threshold,
        reason=(
            f"{named} failed above {percent} of the coarse pass; "
            f"--on-candidate-failure={policy.value}"
        ),
    )


__all__ = [
    "DEFAULT_FAILURE_THRESHOLD",
    "AbortVerdict",
    "CandidateFailurePolicy",
    "CandidateRate",
    "abort_verdict",
]
