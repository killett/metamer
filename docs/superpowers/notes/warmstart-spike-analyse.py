"""Read the warm-start spike's JSONL and report the verdict against its predictions.

**THE SAVING IS COMPUTED OVER THE BOTH-OK INTERSECTION.** A saving over `n_iter`
at points where one arm failed is a comparison of two failure paths, not of two
starts. The excluded count is reported rather than absorbed.

**AND IT IS REPORTED PER CANDIDATE, PER REGIME AND PER BOUNDARY STRATUM.** The
pooled number is the one that gets quoted and the per-stratum ones are the ones
that are true -- section 11.2's own rule for the audit, applied to the spike
standing in for it. The uncertainty is a bootstrap over points, so
band-versus-uncertainty is a comparison rather than a preference.

Usage:
    warmstart-spike-analyse.py <measured.jsonl>
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from typing import Any

import numpy as np

BOOTSTRAP = 2000
RNG_SEED = 20260823


def load(path: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Split the JSONL into point rows and everything else, keyed by kind."""
    points: list[dict[str, Any]] = []
    other: dict[str, Any] = defaultdict(list)
    with open(path) as handle:
        for line in handle:
            row = json.loads(line)
            if row["kind"] == "point":
                points.append(row)
            else:
                other[row["kind"]].append(row)
    return points, other


def by_arm(points: list[dict[str, Any]]) -> dict[str, dict[tuple[int, int], Any]]:
    """Index point rows by arm and (flat index, candidate)."""
    out: dict[str, dict[tuple[int, int], Any]] = defaultdict(dict)
    for row in points:
        out[row["arm"]][(row["flat"], row["cand"])] = row
    return out


def saving(cold: list[float], warm: list[float]) -> tuple[float, float]:
    """Fractional saving in the mean, with a paired bootstrap standard error."""
    if not cold:
        return float("nan"), float("nan")
    c = np.asarray(cold, dtype=float)
    w = np.asarray(warm, dtype=float)
    point = 1.0 - w.mean() / c.mean()
    rng = np.random.default_rng(RNG_SEED)
    draws = rng.integers(0, len(c), size=(BOOTSTRAP, len(c)))
    boot = 1.0 - w[draws].mean(axis=1) / c[draws].mean(axis=1)
    return float(point), float(boot.std(ddof=1))


def report_saving(
    label: str, arms: dict[str, dict[tuple[int, int], Any]], arm: str
) -> None:
    """Print the saving of `arm` against cold, pooled and split every way."""
    cold = arms["cold"]
    other = arms[arm]
    strata: dict[str, tuple[list[float], list[float]]] = defaultdict(lambda: ([], []))
    for key, crow in cold.items():
        orow = other.get(key)
        if orow is None or crow["outcome"] != 0 or orow["outcome"] != 0:
            continue
        buckets = [
            "pooled",
            f"cand{key[1]}",
            f"regime{crow['regime']}",
            "cross" if orow["cross_regime"] else "same",
        ]
        for bucket in buckets:
            strata[bucket][0].append(crow["n_iter"])
            strata[bucket][1].append(orow["n_iter"])
    print(f"\n--- {label}: {arm} vs cold, iteration saving ---")
    for bucket in sorted(strata):
        point, err = saving(*strata[bucket])
        n = len(strata[bucket][0])
        print(f"  {bucket:10s} n={n:5d}  {point:+7.2%} +/- {err:.2%}")


def report_agreement(arms: dict[str, dict[tuple[int, int], Any]], arm: str) -> None:
    """Do warm and cold land at the same optimum? P6's three comparisons."""
    cold, other = arms["cold"], arms[arm]
    dll: list[float] = []
    dpar: list[float] = []
    selection_same = 0
    selection_n = 0
    seen_points: set[int] = set()
    for key, crow in cold.items():
        orow = other.get(key)
        if orow is None or crow["outcome"] != 0 or orow["outcome"] != 0:
            continue
        dll.append(abs(crow["loglik"] - orow["loglik"]))
        err = np.asarray(crow["theta_err"], dtype=float)
        d = np.abs(
            np.asarray(crow["theta"], dtype=float)
            - np.asarray(orow["theta"], dtype=float)
        )
        finite = np.isfinite(d) & np.isfinite(err) & (err > 0)
        if finite.any():
            dpar.append(float(np.nanmax(d[finite] / err[finite])))
        if key[0] not in seen_points:
            seen_points.add(key[0])
            selection_n += 1
            selection_same += int(crow["best_index"] == orow["best_index"])
    dll_arr = np.asarray(dll)
    dpar_arr = np.asarray(dpar)
    print(f"\n--- {arm} vs cold, same optimum? ---")
    print(
        f"  selection agreement      {selection_same}/{selection_n} = "
        f"{selection_same / max(selection_n, 1):.2%}"
    )
    print(
        f"  |dloglik| < 0.01         {(dll_arr < 0.01).mean():.2%} "
        f"(median {np.median(dll_arr):.2e}, max {dll_arr.max():.2e})"
    )
    print(
        f"  max param dist < 0.25 SE {(dpar_arr < 0.25).mean():.2%} "
        f"(median {np.median(dpar_arr):.3f}, max {dpar_arr.max():.3f})"
    )


def report_timing(other: dict[str, Any]) -> None:
    """Wall clock per arm across the repeats, and the determinism fingerprint."""
    per_arm: dict[str, list[float]] = defaultdict(list)
    fingerprints: dict[str, set[tuple[int, float]]] = defaultdict(set)
    for row in other["timing"]:
        if "repeat" not in row:
            continue
        per_arm[row["arm"]].append(row["seconds"])
        fingerprints[row["arm"]].add(
            (row["n_iter_total"], round(row["loglik_fingerprint"], 9))
        )
    print("\n--- wall clock, seconds per arm across repeats ---")
    cold_mean = float(np.mean(per_arm["cold"])) if per_arm["cold"] else float("nan")
    for arm in sorted(per_arm):
        vals = np.asarray(per_arm[arm])
        rel = 1.0 - vals.mean() / cold_mean
        stable = "yes" if len(fingerprints[arm]) == 1 else "NO"
        print(
            f"  {arm:8s} {vals.mean():8.2f} +/- {vals.std(ddof=1) if len(vals) > 1 else 0.0:5.2f}"
            f"   saving vs cold {rel:+7.2%}   deterministic across repeats: {stable}"
        )


def main() -> None:
    """Print the verdict tables for one measured JSONL."""
    points, other = load(sys.argv[1])
    arms = by_arm(points)
    config = other["config"][0]
    print(
        f"fixture: {config['n_side']}x{config['n_side']}, N={config['n_time']}, "
        f"stride={config['stride']}, candidates={len(config['candidates'])}"
    )
    print(f"lint findings: {config['lint_findings']}")
    for row in other.get("coarse_health", []):
        print(
            f"coarse OK fraction: {row['ok_fraction']:.3f} "
            f"per candidate {[round(x, 3) for x in row['per_candidate_ok']]}"
        )
    for row in other.get("source_map", []):
        print(
            f"measured {row['n_measured']} points, excluded {row['n_excluded']}; "
            f"OK filter changed the source: {row['ok_filter_changed_source']:.3f}, "
            f"max radius {row['max_radius_used']}"
        )
    for arm in ("self", "warm", "random"):
        if arm in arms:
            report_saving("iterations", arms, arm)
    for arm in ("warm", "random"):
        if arm in arms:
            report_agreement(arms, arm)
    report_timing(other)


if __name__ == "__main__":
    main()
