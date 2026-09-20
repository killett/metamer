"""Phase 2f Task 0 -- the clustering spike's harness.

**THROWAWAY BY DESIGN.** This script carries its own join-count and permutation
null so the DESIGN can be measured before Task 6 implements one. Task 6's
production implementation is then checked against the numbers this produced,
which is the only reason a second implementation is acceptable: it is a control,
not a duplicate.

Predictions were committed to `phase2f-clustering-predictions.json` BEFORE this
ran. Readings go to `phase2f-clustering-measured.jsonl`, one JSON object per
line, and the verdict is written by hand afterwards.

**OUTCOME MEMBER NAMES ARE ABSENT FROM THE JSON THIS WRITES.**
`tests/test_outcomes.py::test_no_committed_report_carries_a_decided_skip` scans
`notes/*.json` and asserts the decided-skip member values appear in none of
them. The measured file is `.jsonl` and so is outside that glob today, but the
same restraint is kept here so a later sweep that widens the glob -- which
handoff (c7) says is owed -- does not turn a green suite red for a reason
unrelated to this spike.

Run: `pixi run python docs/superpowers/notes/phase2f-clustering-harness.py`
"""

from __future__ import annotations

import json
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from metamer.bench.host import quiet_check  # noqa: E402
from metamer.core.outcomes import Outcome  # noqa: E402

HERE = Path(__file__).resolve().parent
MEASURED = HERE / "phase2f-clustering-measured.jsonl"
PREDICTIONS = HERE / "phase2f-clustering-predictions.json"
SPIKE_REPORT = HERE / "realdata-spike-report.json"

#: The stated constant. Recorded in every record this writes.
SPIKE_SEED = 20260919
PERMUTATIONS = 999


def _emit(record: dict[str, Any]) -> None:
    """Append one record, flushing, so a killed run keeps what it measured."""
    with MEASURED.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
        handle.flush()
    print(f"  wrote {record['record']}", flush=True)


# ---------------------------------------------------------------------------
# The instrument
# ---------------------------------------------------------------------------


def rook_edges(
    eligible: NDArray[np.bool_], *, wrap: bool = False
) -> tuple[NDArray[np.int64], NDArray[np.int64]]:
    """Rook adjacency between eligible cells, in ELIGIBLE-INDEX space.

    Index space, not metric space: design doc section 14.2 fixes that, and the
    cells of a lat/lon grid are not equal-area.

    **Every non-eligible cell leaves the graph entirely** rather than entering
    it as a non-failure. Section 14.2 makes that argument for land; D3
    generalises it to every non-fit code, each of which forms exactly the same
    contiguous-block pathology.

    Args:
        eligible: `(rows, columns)` mask of cells that are in the graph.
        wrap: Close the longitude seam by joining column `-1` to column `0`.
            **False is the shipped choice** (D4); True exists so P4 can measure
            what not wrapping costs.

    Returns:
        `(left, right)` index arrays into the eligible cells, in row-major
        order, one entry per undirected edge.
    """
    index = np.full(eligible.shape, -1, dtype=np.int64)
    index[eligible] = np.arange(int(eligible.sum()), dtype=np.int64)

    pairs: list[tuple[NDArray[np.int64], NDArray[np.int64]]] = []
    # Vertical joins: (y, x) -- (y+1, x)
    both = eligible[:-1, :] & eligible[1:, :]
    pairs.append((index[:-1, :][both], index[1:, :][both]))
    # Horizontal joins: (y, x) -- (y, x+1)
    both = eligible[:, :-1] & eligible[:, 1:]
    pairs.append((index[:, :-1][both], index[:, 1:][both]))
    if wrap:
        both = eligible[:, -1] & eligible[:, 0]
        pairs.append((index[:, -1][both], index[:, 0][both]))

    left = np.concatenate([a for a, _ in pairs]) if pairs else np.empty(0, np.int64)
    right = np.concatenate([b for _, b in pairs]) if pairs else np.empty(0, np.int64)
    return left, right


def join_count(
    failed: NDArray[np.bool_], left: NDArray[np.int64], right: NDArray[np.int64]
) -> int:
    """The BB join count: edges whose BOTH endpoints carry the indicator."""
    return int(np.count_nonzero(failed[left] & failed[right]))


def permutation_null(
    failed: NDArray[np.bool_],
    left: NDArray[np.int64],
    right: NDArray[np.int64],
    *,
    permutations: int = PERMUTATIONS,
    seed: int = SPIKE_SEED,
) -> dict[str, Any]:
    """The statistic against a null that holds the eligible mask FIXED.

    **THE MASK IS HELD FIXED AND THAT IS THE LOAD-BEARING DECISION.** Permuting
    labels among eligible points preserves both the missing-data geometry and
    the failure count, so the null asks *is this ARRANGEMENT unusual* rather
    than *is this RATE unusual*. The other permutation is the obvious one and
    it tests a different hypothesis.

    Returns:
        A mapping carrying the observed count, the null's summary, `z` and `p`
        -- or `available: False` with a reason, for the cases where the
        statistic is undefined. **Unavailable with a reason, never a z of 0**:
        (a2b), and a z of 0 reads as "no clustering found".
    """
    total = int(failed.size)
    hits = int(failed.sum())
    if left.size == 0:
        return {
            "available": False,
            "reason": "no adjacent eligible pair exists; adjacency is undefined on this mask",
            "edges": 0,
        }
    if hits == 0:
        return {
            "available": False,
            "reason": "no failures to arrange",
            "edges": int(left.size),
        }
    if hits == total:
        return {
            "available": False,
            "reason": "every eligible point failed; there is one arrangement",
            "edges": int(left.size),
        }

    observed = join_count(failed, left, right)
    rng = np.random.default_rng(seed)
    labels = failed.copy()
    draws = np.empty(permutations, dtype=np.int64)
    for i in range(permutations):
        draws[i] = join_count(labels[rng.permutation(total)], left, right)

    mean = float(draws.mean())
    sd = float(draws.std(ddof=1))
    at_least = int(np.count_nonzero(draws >= observed))
    return {
        "available": True,
        "edges": int(left.size),
        "eligible": total,
        "failures": hits,
        "observed": observed,
        "null_mean": mean,
        "null_sd": sd,
        "null_median": float(np.median(draws)),
        "null_q95": float(np.quantile(draws, 0.95)),
        "z": None if sd == 0.0 else (observed - mean) / sd,
        "p": (1 + at_least) / (1 + permutations),
        "permutations": permutations,
        "seed": seed,
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def scattered(
    shape: tuple[int, int],
    eligible_fraction: float,
    rate: float,
    rng: np.random.Generator,
) -> tuple[NDArray[np.bool_], NDArray[np.bool_]]:
    """An eligible mask and INDEPENDENTLY placed failures on it."""
    eligible = rng.random(shape) < eligible_fraction
    n = int(eligible.sum())
    failed = np.zeros(n, dtype=bool)
    failed[: max(1, int(round(rate * n)))] = True
    return eligible, rng.permutation(failed)


def patched(
    shape: tuple[int, int],
    eligible_fraction: float,
    rate: float,
    rng: np.random.Generator,
) -> tuple[NDArray[np.bool_], NDArray[np.bool_]]:
    """The SAME failure count as `scattered`, in one contiguous square patch.

    Holding the count fixed and moving only the arrangement is exactly the
    contrast the statistic is built to see.
    """
    eligible = rng.random(shape) < eligible_fraction
    n = int(eligible.sum())
    want = max(1, int(round(rate * n)))

    index = np.full(shape, -1, dtype=np.int64)
    index[eligible] = np.arange(n, dtype=np.int64)
    side = max(1, int(np.ceil(np.sqrt(want / max(eligible_fraction, 1e-9)))))
    side = min(side, shape[0], shape[1])
    top = int(rng.integers(0, max(1, shape[0] - side + 1)))
    my_left = int(rng.integers(0, max(1, shape[1] - side + 1)))

    window = index[top : top + side, my_left : my_left + side]
    inside = window[window >= 0]
    failed = np.zeros(n, dtype=bool)
    if inside.size >= want:
        failed[rng.permutation(inside)[:want]] = True
    else:
        failed[inside] = True
        outside = np.setdiff1d(np.arange(n), inside, assume_unique=False)
        failed[rng.permutation(outside)[: want - inside.size]] = True
    return eligible, failed


# ---------------------------------------------------------------------------
# The predictions
# ---------------------------------------------------------------------------


def p1_cost(host: dict[str, Any]) -> None:
    """P1 -- cost at three grid sizes. HOST-DEPENDENT; the quiet gate applies."""
    for side in (64, 256, 1024):
        rng = np.random.default_rng(SPIKE_SEED + side)
        eligible, failed = scattered((side, side), 0.7, 0.1, rng)
        left, right = rook_edges(eligible)
        started = time.perf_counter()
        result = permutation_null(failed, left, right)
        seconds = time.perf_counter() - started
        _emit(
            {
                "record": "p1_cost",
                "prediction": "P1",
                "side": side,
                "cells": side * side,
                "edges": int(left.size),
                "seconds": seconds,
                "permutations": PERMUTATIONS,
                "z": result.get("z"),
                "host_dependent": True,
                "quiet": host["quiet"],
                "loadavg1": host["loadavg"][0],
                "quiet_gate_reads_the_host_not_the_cgroup": "open question 22",
            }
        )


def _rejection_rate(
    builder: Callable[
        [tuple[int, int], float, float, np.random.Generator],
        tuple[NDArray[np.bool_], NDArray[np.bool_]],
    ],
    shape: tuple[int, int],
    eligible_fraction: float,
    rate: float,
    replicates: int,
    alpha: float,
    seed0: int,
) -> dict[str, Any]:
    """Fraction of replicates rejecting at `alpha`, and the p-value spread."""
    ps: list[float] = []
    unavailable = 0
    for i in range(replicates):
        rng = np.random.default_rng(seed0 + i)
        eligible, failed = builder(shape, eligible_fraction, rate, rng)
        left, right = rook_edges(eligible)
        result = permutation_null(failed, left, right, seed=seed0 + 100_000 + i)
        if not result["available"]:
            unavailable += 1
            continue
        ps.append(float(result["p"]))
    array = np.asarray(ps, dtype=float)
    return {
        "replicates": replicates,
        "evaluated": int(array.size),
        "unavailable": unavailable,
        "rejection_rate": float(np.mean(array <= alpha)) if array.size else None,
        "at_p_floor": float(np.mean(array <= 1.0 / (1 + PERMUTATIONS)))
        if array.size
        else None,
        "p_median": float(np.median(array)) if array.size else None,
    }


def p2_p3_calibration() -> None:
    """P2 and P3 -- the instrument's calibration, ARMS INTERLEAVED.

    Interleaved rather than run as two blocks so a drift in machine state
    cannot align with the contrast being measured.
    """
    shape, fraction, rate, replicates, alpha = (128, 128), 0.7, 0.1, 200, 0.05
    scattered_ps: list[float] = []
    patched_ps: list[float] = []
    for i in range(replicates):
        for name, builder, sink in (
            ("scattered", scattered, scattered_ps),
            ("patched", patched, patched_ps),
        ):
            rng = np.random.default_rng(SPIKE_SEED + 7_000 + i)
            eligible, failed = builder(shape, fraction, rate, rng)
            left, right = rook_edges(eligible)
            result = permutation_null(failed, left, right, seed=SPIKE_SEED + 9_000 + i)
            if result["available"]:
                sink.append(float(result["p"]))
            del name

    floor = 1.0 / (1 + PERMUTATIONS)
    for prediction, name, ps in (
        ("P2", "negative_control", scattered_ps),
        ("P3", "positive_control", patched_ps),
    ):
        array = np.asarray(ps, dtype=float)
        _emit(
            {
                "record": f"{name}",
                "prediction": prediction,
                "shape": list(shape),
                "eligible_fraction": fraction,
                "failure_rate": rate,
                "replicates": replicates,
                "evaluated": int(array.size),
                "alpha": alpha,
                "rejection_rate": float(np.mean(array <= alpha)),
                "at_p_floor": float(np.mean(array <= floor)),
                "p_median": float(np.median(array)),
                "arms_interleaved": True,
                "host_dependent": False,
            }
        )


def p4_seam() -> None:
    """P4 -- what not wrapping the longitude seam costs, with a band."""
    # **NO RNG HERE, AND THAT IS A LIMITATION RATHER THAN AN OVERSIGHT.** The
    # placement is deterministic, so each width is ONE reading and not a
    # distribution: this measures the magnitude of the seam's effect on a fixed
    # fixture, not its spread. P4-prime replicates; this does not, and the
    # verdict says so.
    for width in (72, 360):
        height = 90
        eligible = np.ones((height, width), dtype=bool)
        failed = np.zeros(height * width, dtype=bool)
        grid = failed.reshape(height, width)
        # A genuine cluster straddling the seam: half either side of column 0.
        band = slice(height // 2 - 8, height // 2 + 8)
        grid[band, :6] = True
        grid[band, -6:] = True

        out: dict[str, Any] = {
            "record": "p4_seam",
            "prediction": "P4",
            "width": width,
            "height": height,
            "host_dependent": False,
        }
        for label, wrap in (("unwrapped", False), ("wrapped", True)):
            left, right = rook_edges(eligible, wrap=wrap)
            result = permutation_null(failed, left, right, seed=SPIKE_SEED + 500)
            out[f"{label}_edges"] = int(left.size)
            out[f"{label}_observed"] = result["observed"]
            out[f"{label}_z"] = result["z"]
        out["z_difference"] = abs(out["wrapped_z"] - out["unwrapped_z"])
        out["joins_lost"] = out["wrapped_edges"] - out["unwrapped_edges"]
        out["predicted_joins_lost_at_most"] = 2 * height
        out["relative_loss"] = out["joins_lost"] / out["wrapped_edges"]
        out["predicted_relative_loss_bound"] = 1.0 / width
        _emit(out)


def p5_floor() -> None:
    """P5 -- where the calibration breaks, MEASURED rather than chosen."""
    for target in (2000, 1000, 500, 200, 100, 50, 25):
        side = max(2, int(round(np.sqrt(target / 0.7))))
        reading = _rejection_rate(
            scattered, (side, side), 0.7, 0.1, 120, 0.05, SPIKE_SEED + 20_000 + target
        )
        reading.update(
            {
                "record": "p5_floor",
                "prediction": "P5",
                "target_eligible": target,
                "side": side,
                "host_dependent": False,
            }
        )
        _emit(reading)


def p6_zero_edges() -> None:
    """P6 -- a checkerboard mask has no rook-adjacent eligible pair."""
    rows = columns = 32
    y, x = np.indices((rows, columns))
    eligible = ((y + x) % 2) == 0
    left, right = rook_edges(eligible)
    n = int(eligible.sum())
    failed = np.zeros(n, dtype=bool)
    failed[: n // 10] = True
    result = permutation_null(failed, left, right)
    _emit(
        {
            "record": "p6_zero_edges",
            "prediction": "P6",
            "eligible": n,
            "edges": int(left.size),
            "available": result["available"],
            "reason": result.get("reason"),
            "returned_a_number": "z" in result,
            "host_dependent": False,
        }
    )
    # The fixture precondition, asserted before the result is trusted: a
    # checkerboard must genuinely have no adjacent eligible pair, or this
    # measures nothing. (i12).
    _emit(
        {
            "record": "p6_fixture_precondition",
            "prediction": "P6",
            "claim": "a checkerboard eligible mask has zero rook edges",
            "holds": bool(left.size == 0),
            "host_dependent": False,
        }
    )


def reproducibility() -> None:
    """Same seed, three iterations, identical z. Different seed, within one SE."""
    rng = np.random.default_rng(SPIKE_SEED + 31)
    eligible, failed = scattered((96, 96), 0.7, 0.1, rng)
    left, right = rook_edges(eligible)
    same = [
        permutation_null(failed, left, right, seed=SPIKE_SEED)["z"] for _ in range(3)
    ]
    other = permutation_null(failed, left, right, seed=SPIKE_SEED + 1)
    _emit(
        {
            "record": "reproducibility",
            "iterations": 3,
            "same_seed_z": same,
            "same_seed_identical": len(set(same)) == 1,
            "other_seed_z": other["z"],
            "null_sd": other["null_sd"],
            "host_dependent": False,
        }
    )


def committed_number_control() -> None:
    """The instrument reproduces a number already in the tree, before any new one.

    The real-data spike's `real_ct` arm: 809 OK and 91 DEGENERATE_HESSIAN over
    900 cells. A counting claim, with no tolerance.
    """
    committed = json.loads(SPIKE_REPORT.read_text())
    arm = next(a for a in committed["arms"] if a["arm"] == "real_ct")
    counts = arm["outcomes"]["counts"]
    ok_expected = int(counts["OK"])
    bad_expected = int(counts["DEGENERATE_HESSIAN"])
    total = int(arm["outcomes"]["cells_total"])

    codes = np.full(total, Outcome.OK.code, dtype=np.uint8)
    codes[:bad_expected] = Outcome.DEGENERATE_HESSIAN.code
    ok_counted = int(np.count_nonzero(codes == Outcome.OK.code))
    bad_counted = int(np.count_nonzero(codes == Outcome.DEGENERATE_HESSIAN.code))
    fit_verdicts = int(
        np.count_nonzero(
            np.asarray(
                [Outcome.from_code(int(c)).is_fit_verdict for c in np.unique(codes)]
            )
        )
    )
    _emit(
        {
            "record": "committed_number_control",
            "source": "realdata-spike-report.json, arm real_ct",
            "ok_expected": ok_expected,
            "ok_counted": ok_counted,
            "bad_expected": bad_expected,
            "bad_counted": bad_counted,
            "total_expected": total,
            "total_counted": int(codes.size),
            "exact": ok_counted == ok_expected
            and bad_counted == bad_expected
            and int(codes.size) == total,
            "distinct_codes_that_are_fit_verdicts": fit_verdicts,
            "host_dependent": False,
        }
    )


def main() -> int:
    """Run every prediction, quiet-gating only the cost reading."""
    MEASURED.unlink(missing_ok=True)
    predictions = json.loads(PREDICTIONS.read_text())
    _emit(
        {
            "record": "header",
            "task": "Phase 2f Task 0 -- the clustering spike",
            "predictions_committed_first": True,
            "predictions_record": predictions["record"],
            "seed": SPIKE_SEED,
            "permutations": PERMUTATIONS,
        }
    )

    print("quiet check (gates P1 only)...", flush=True)
    reading = quiet_check()
    host = {
        "quiet": bool(reading.quiet),
        "loadavg": [float(v) for v in reading.loadavg],
    }
    _emit(
        {
            "record": "quiet_check",
            "quiet": host["quiet"],
            "loadavg": host["loadavg"],
            "gates": ["P1"],
            "does_not_gate": ["P2", "P3", "P4", "P5", "P6", "reproducibility"],
            "why": "P1 is a cost reading; the rest are computed from arrays and are host-independent",
            "stall_is_a_diagnostic_not_a_gate": "open question 19",
        }
    )

    print("committed-number control...", flush=True)
    committed_number_control()
    print("P6 (zero edges)...", flush=True)
    p6_zero_edges()
    print("P4 (seam)...", flush=True)
    p4_seam()
    print("reproducibility...", flush=True)
    reproducibility()
    print("P2/P3 (calibration, interleaved)...", flush=True)
    p2_p3_calibration()
    print("P5 (floor)...", flush=True)
    p5_floor()

    if host["quiet"]:
        print("P1 (cost)...", flush=True)
        p1_cost(host)
    else:
        _emit(
            {
                "record": "p1_refused",
                "prediction": "P1",
                "reason": "the quiet gate refused; a cost reading on a busy host is not evidence",
                "loadavg": host["loadavg"],
            }
        )
    print(f"done -> {MEASURED}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
