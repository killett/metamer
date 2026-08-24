"""Read the stride sweep's JSONL and report s(k), the objective, and agreement.

**THE MEASUREMENT AND THE ARITHMETIC ARE KEPT APART.** `s(k)` and the wall-clock
rates are measured on one common point set; the `1/k^2` fraction is arithmetic
over the grid. The objective combines them and says which is which.

    relative_cost(k) = (1/k^2) + (1 - 1/k^2) * (T_warm(k) / T_cold)

**AND AGREEMENT IS A COLUMN, NOT A FOOTNOTE.** The mechanism was authorized at
90.37% selection agreement against a pre-agreed 90% stop, so if the net-cost
optimum and the correctness optimum diverge the stride is a scope decision
rather than an arithmetic one.

Usage:
    warmstart-stride-analyse.py <measured.jsonl>
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from collections.abc import Sequence
from typing import Any

import numpy as np

BOOTSTRAP = 2000
RNG_SEED = 20260824


def load(
    path: str,
) -> tuple[dict[str, dict[tuple[int, int], Any]], dict[str, list[Any]]]:
    """Index point rows by arm and (flat, candidate); collect the rest by kind."""
    arms: dict[str, dict[tuple[int, int], Any]] = defaultdict(dict)
    other: dict[str, list[Any]] = defaultdict(list)
    with open(path) as handle:
        for line in handle:
            row = json.loads(line)
            if row["kind"] == "point":
                arms[row["arm"]][(row["flat"], row["cand"])] = row
            else:
                other[row["kind"]].append(row)
    return arms, other


def saving(cold: Sequence[float], warm: Sequence[float]) -> tuple[float, float]:
    """Fractional saving in the mean, with a paired bootstrap standard error."""
    if not cold:
        return float("nan"), float("nan")
    c, w = np.asarray(cold, float), np.asarray(warm, float)
    rng = np.random.default_rng(RNG_SEED)
    draws = rng.integers(0, len(c), size=(BOOTSTRAP, len(c)))
    boot = 1.0 - w[draws].mean(axis=1) / c[draws].mean(axis=1)
    return float(1.0 - w.mean() / c.mean()), float(boot.std(ddof=1))


def strata(
    cold: dict[Any, Any], warm: dict[Any, Any]
) -> dict[str, tuple[list[int], list[int]]]:
    """Group the both-OK intersection by pooled, candidate and boundary."""
    out: dict[str, tuple[list[int], list[int]]] = defaultdict(lambda: ([], []))
    for key, crow in cold.items():
        wrow = warm.get(key)
        if wrow is None or crow["outcome"] != 0 or wrow["outcome"] != 0:
            continue
        buckets = ["pooled", f"cand{key[1]}"]
        if wrow.get("cross_regime") is not None:
            buckets.append("cross" if wrow["cross_regime"] else "same")
        for bucket in buckets:
            out[bucket][0].append(crow["n_iter"])
            out[bucket][1].append(wrow["n_iter"])
    return out


def agreement(
    cold: dict[Any, Any], warm: dict[Any, Any]
) -> tuple[int, int, float, float]:
    """Selection agreement over points, and the |dloglik| tail over cells."""
    same = total = 0
    seen: set[int] = set()
    dll: list[float] = []
    for key, crow in cold.items():
        wrow = warm.get(key)
        if wrow is None or crow["outcome"] != 0 or wrow["outcome"] != 0:
            continue
        dll.append(abs(crow["loglik"] - wrow["loglik"]))
        if key[0] not in seen:
            seen.add(key[0])
            total += 1
            same += int(crow["best_index"] == wrow["best_index"])
    arr = np.asarray(dll)
    return same, total, float((arr < 0.01).mean()), float(arr.max())


def main() -> None:
    """Print the stride curve, the objective and the agreement column."""
    arms, other = load(sys.argv[1])
    config = other["config"][0]
    strides = config["strides"]
    rates = {r["arm"]: r["per_series_s"] for r in other["timing"]}

    print(
        f"fixture: {config['n_side']}x{config['n_side']}, N={config['n_time']}, "
        f"common fine set {config['n_common_fine']}, "
        f"coarse counts {config['coarse_counts']}"
    )
    for row in other.get("coarse_health", []):
        print(
            f"coarse OK fraction: {row['ok_fraction']:.4f} "
            f"per candidate {[round(x, 4) for x in row['per_candidate_ok']]}"
        )
    for row in other.get("source_map", []):
        print(
            f"  k={row['stride']}: mean source radius {row['mean_radius']:.3f}, "
            f"max {row['max_radius']}, invalid cells {row['n_invalid_cells']}"
        )

    cold = arms["cold"]
    t_cold = rates["cold"]
    print(f"\ncold: {t_cold:.4f} s/series\n")
    print(
        f"{'k':>3} {'s(k) pooled':>18} {'T_warm/T_cold':>14} {'wall saving':>12} "
        f"{'1/k^2':>7} {'net saving':>11} {'agreement':>12} {'max|dll|':>10}"
    )
    for k in strides:
        arm = f"warm_k{k}"
        if arm not in arms:
            print(f"{k:>3}  (arm missing)")
            continue
        s, err = saving(*strata(cold, arms[arm])["pooled"])
        ratio = rates[arm] / t_cold
        frac = 1.0 / (k * k)
        net = 1.0 - (frac + (1.0 - frac) * ratio)
        same, total, near, mx = agreement(cold, arms[arm])
        print(
            f"{k:>3} {s:>10.2%} +/-{err:>5.2%} {ratio:>14.4f} {1 - ratio:>11.2%} "
            f"{frac:>7.4f} {net:>10.2%} {same:>5}/{total:<4}={same / total:>5.1%} {mx:>10.2e}"
        )

    print("\nper stratum, iteration saving:")
    for k in strides:
        arm = f"warm_k{k}"
        if arm not in arms:
            continue
        buckets = strata(cold, arms[arm])
        parts = []
        for name in sorted(buckets):
            if name == "pooled":
                continue
            s, err = saving(*buckets[name])
            parts.append(f"{name} {s:+.2%}+/-{err:.2%} (n={len(buckets[name][0])})")
        print(f"  k={k}: " + "  ".join(parts))


if __name__ == "__main__":
    main()
