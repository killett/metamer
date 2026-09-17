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

    Attributes:
        candidate: The label, as the store records it.
        failed: Eligible points this candidate failed, by `Outcome.is_failure`.
        eligible: Points where this candidate was a real candidate for fitting,
            by `Outcome.is_eligible`.
        rate: `failed / eligible`, or **None when `eligible` is zero** -- see
            `abort_verdict` on why that is not the same as zero.
    """

    candidate: str
    failed: int
    eligible: int
    rate: float | None


@dataclass(frozen=True)
class AbortVerdict:
    """What section 14.1 says to do, and the numbers it says it from.

    Attributes:
        action: `"continue"`, `"abort"`, or `"drop"`.
        candidates: The candidates to drop, empty unless `action` is `"drop"`.
        rates: Every candidate's rate, in store order, whatever the action.
        threshold: The rate compared against, carried so a reading is
            reproducible without knowing the caller's defaults.
        reason: One line naming why, for the final console line.
    """

    action: Literal["continue", "abort", "drop"]
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

    **AN EMPTY ELIGIBLE POPULATION IS A FINDING, NOT A CLEAN BILL.** The rate is
    `failed / eligible`, and with no eligible points that is `0/0`: a naive
    implementation either raises -- a crash, on a well-formed store -- or yields
    `nan` or `0.0`, **both of which compare False against the threshold and read
    as "continue"**. That case is reachable by exactly the mistake this section
    exists to catch: a config pointing at the wrong variable, or at a domain
    that is entirely land, gives `INSUFFICIENT_DATA` everywhere, every
    denominator is empty, and the run would proceed through pass 2 at full cost
    to produce a store of nothing. **"Zero cases" is a claim about the
    instrument until proven otherwise**, so it aborts and says so.

    **CORRECTED 2026-09-16: AN EMPTY COARSE SAMPLE DOES NOT IMPLY AN EMPTY
    GRID.** ~~That is a config or data error~~ was the first wording, and 2c's
    criterion-1 fixture refutes it: land on every stride-2 row leaves the
    coarse lattice entirely masked while the odd rows carry data. The sample
    then holds **no evidence**, which is what the refusal now says, and the
    message names `--no-early-abort` as the lift when the lattice is known to
    fall on masked cells. **Whether no-evidence should abort or continue
    loudly is open** -- see PROGRESS.md -- and this abort is the conservative
    reading until it is settled.

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
        The rate, with `rate=None` when nothing was eligible.
    """
    eligible = 0
    failed = 0
    values, counts = np.unique(codes, return_counts=True)
    for value, count in zip(values, counts, strict=True):
        member = Outcome.from_code(int(value))
        if member.is_eligible:
            eligible += int(count)
            if member.is_failure:
                failed += int(count)
    return CandidateRate(
        candidate=label,
        failed=failed,
        eligible=eligible,
        rate=None if eligible == 0 else failed / eligible,
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
    judgeable = [rate for rate in rates if rate.rate is not None]
    if not judgeable:
        return AbortVerdict(
            action="abort",
            candidates=(),
            rates=rates,
            threshold=threshold,
            reason=(
                "no point in the coarse pass was eligible for any candidate, so "
                "the sample holds no evidence and the run is refused rather than "
                "continued blind. Either the input is masked everywhere, or the "
                "coarse lattice happens to fall only on masked cells; if the "
                "second, --no-early-abort proceeds"
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
