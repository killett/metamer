"""Phase 2f Task 0 -- the two spike extensions the first verdict owed.

**THROWAWAY, and it REUSES the first harness's instrument deliberately** — the
question here is about the fixtures and the detector, not about the join count,
and a second implementation of the statistic would make a disagreement between
the two passes ambiguous.

Predictions were committed to `phase2f-clustering-prime-predictions.json` BEFORE
this ran. Readings go to `phase2f-clustering-prime-measured.jsonl`.

**P5-prime STOPS if its precondition fails.** A detector that cannot see the
degenerate case already in hand is not calibrated to look for it, and no floor
it reported would be evidence.

Run: `pixi run python docs/superpowers/notes/phase2f-clustering-prime-harness.py`
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray
from scipy import stats

HERE = Path(__file__).resolve().parent
MEASURED = HERE / "phase2f-clustering-prime-measured.jsonl"
PREDICTIONS = HERE / "phase2f-clustering-prime-predictions.json"

_spec = importlib.util.spec_from_file_location(
    "_clustering_spike", HERE / "phase2f-clustering-harness.py"
)
if _spec is None or _spec.loader is None:  # pragma: no cover - a moved sibling
    raise RuntimeError("the first spike's harness is not beside this one")
spike = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(spike)

SEED = 20260919
ALPHA = 0.05
REPLICATES = 120
#: KS <= this is called uniform. The 5% critical value at 120 samples is about
#: 1.36/sqrt(120) = 0.124, so this sits just above it and is not tuned to data.
KS_UNIFORM = 0.15


def _emit(record: dict[str, Any]) -> None:
    with MEASURED.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
        handle.flush()
    print(f"  wrote {record['record']}", flush=True)


# ---------------------------------------------------------------------------
# P4-prime -- a small cluster that exists ONLY at the seam
# ---------------------------------------------------------------------------


def seam_cluster(
    height: int, width: int, side: int, rng: np.random.Generator
) -> NDArray[np.bool_]:
    """A `side x side` patch straddling the antimeridian, at a random row.

    Half its columns sit at the right edge and half at column 0, so the patch
    is one connected block **only if the seam is closed**.
    """
    grid = np.zeros((height, width), dtype=bool)
    top = int(rng.integers(0, height - side))
    half = side // 2
    grid[top : top + side, :half] = True
    grid[top : top + side, width - (side - half) :] = True
    return grid.reshape(-1)


def p4_prime() -> None:
    """Does NOT wrapping actually miss a small seam-only cluster?"""
    height, width = 90, 360
    eligible = np.ones((height, width), dtype=bool)
    arms = {
        "unwrapped": spike.rook_edges(eligible, wrap=False),
        "wrapped": spike.rook_edges(eligible, wrap=True),
    }
    for side in (4, 6, 8, 10, 12, 14):
        rejects = {"unwrapped": 0, "wrapped": 0}
        evaluated = 0
        for i in range(REPLICATES):
            rng = np.random.default_rng(SEED + 60_000 + side * 1000 + i)
            failed = seam_cluster(height, width, side, rng)
            evaluated += 1
            for name, (left, right) in arms.items():
                result = spike.permutation_null(
                    failed, left, right, seed=SEED + 70_000 + side * 1000 + i
                )
                if result["available"] and float(result["p"]) <= ALPHA:
                    rejects[name] += 1
        wrapped = rejects["wrapped"] / evaluated
        unwrapped = rejects["unwrapped"] / evaluated
        _emit(
            {
                "record": "p4_prime",
                "prediction": "P4p-1",
                "side": side,
                "cluster_cells": side * side,
                "grid": [height, width],
                "replicates": evaluated,
                "alpha": ALPHA,
                "wrapped_rejection": wrapped,
                "unwrapped_rejection": unwrapped,
                "gap": wrapped - unwrapped,
                "paired_fixture": True,
                "host_dependent": False,
            }
        )


# ---------------------------------------------------------------------------
# P5-prime -- the floor, with a distributional detector
# ---------------------------------------------------------------------------


def _p_values(target: int, replicates: int, seed0: int) -> list[float]:
    """Replicate p-values at one eligible-population size."""
    side = max(2, int(round(np.sqrt(target / 0.7))))
    out: list[float] = []
    for i in range(replicates):
        rng = np.random.default_rng(seed0 + i)
        eligible, failed = spike.scattered((side, side), 0.7, 0.1, rng)
        left, right = spike.rook_edges(eligible)
        result = spike.permutation_null(failed, left, right, seed=seed0 + 50_000 + i)
        if result["available"]:
            out.append(float(result["p"]))
    return out


def _reading(target: int, ps: list[float]) -> dict[str, Any]:
    array = np.asarray(ps, dtype=float)
    ks = stats.kstest(array, "uniform")
    return {
        "target_eligible": target,
        "evaluated": int(array.size),
        "ks_distance": float(ks.statistic),
        "ks_p": float(ks.pvalue),
        "fraction_at_one": float(np.mean(array >= 1.0)),
        "p_median": float(np.median(array)),
        "uniform_by_ks": bool(ks.statistic <= KS_UNIFORM),
        "host_dependent": False,
    }


def p5_prime() -> bool:
    """The floor. Returns False if the PRECONDITION fails, having said so."""
    degenerate = _reading(50, _p_values(50, REPLICATES, SEED + 80_000 + 50))
    degenerate.update(
        {
            "record": "p5_prime_precondition",
            "prediction": "P5p-1",
            "claim": "the new detector must FIRE on the known-degenerate case",
            "required_ks_at_least": 0.5,
            "required_fraction_at_one_at_least": 0.5,
            "fires": bool(
                degenerate["ks_distance"] >= 0.5
                and degenerate["fraction_at_one"] >= 0.5
            ),
            "known_from_the_first_pass": "p-median exactly 1.000 at this size",
        }
    )
    _emit(degenerate)
    if not degenerate["fires"]:
        _emit(
            {
                "record": "p5_prime_stopped",
                "reason": (
                    "the replacement detector did not fire on the degenerate case "
                    "already in hand, so no floor it reported would be evidence"
                ),
                "host_dependent": False,
            }
        )
        return False

    for target in (2000, 1000, 500, 200, 100, 50, 25):
        reading = _reading(
            target, _p_values(target, REPLICATES, SEED + 80_000 + target)
        )
        reading.update({"record": "p5_prime_floor", "prediction": "P5p-2"})
        _emit(reading)
    return True


def main() -> int:
    """Run the precondition, then the floor, then the seam-only cluster."""
    MEASURED.unlink(missing_ok=True)
    predictions = json.loads(PREDICTIONS.read_text())
    _emit(
        {
            "record": "header",
            "task": "Phase 2f Task 0 -- spike extensions",
            "predictions_committed_first": True,
            "predictions_record": predictions["record"],
            "instrument_reused_from": "phase2f-clustering-harness.py",
            "why_reused": (
                "the question is about the fixtures and the detector, not the "
                "statistic; a second implementation would make a disagreement "
                "between the two passes ambiguous"
            ),
            "seed": SEED,
        }
    )
    print("P5-prime (precondition, then the floor)...", flush=True)
    p5_prime()
    print("P4-prime (a small seam-only cluster)...", flush=True)
    p4_prime()
    print(f"done -> {MEASURED}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
