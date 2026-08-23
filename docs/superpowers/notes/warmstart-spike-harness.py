"""2c Task 0 -- the warm-start spike: measure the saving section 11.2's verdict turns on.

**WHY THIS EXISTS, AND WHY IT RUNS BEFORE THE MECHANISM.** Design doc section
11.2 makes warm-starting's own survival conditional on a number it calls
unmeasured: *"If warm-starting saves less than ~30% of iterations, the mechanism
is not paying for its complexity or its hysteresis risk, and warm-starting is
dropped."* Measured after the mechanism exists, that verdict costs store fields,
a cache key, a resume-gate interaction and a schema bump -- a sixth cascade --
so it is not really available, and the pull toward *"22% is nearly 30%"* is what
an expensive "no" produces. **Measured first it costs one harness.**

**THE MECHANISM LIVES HERE AND NOWHERE ELSE.** The stride, the spiral, the
tie-break and the interpolation rule are implemented in this file. No production
module changes, no store field, no cache key, no schema version. That is not
tidiness: it is the property that makes a "drop it" verdict cost nothing.

**FOUR ARMS, AND TWO OF THEM ARE CONTROLS THAT DECIDE WHETHER THE OTHER TWO MEAN
ANYTHING.**

| arm | `x0` | what it is for |
|---|---|---|
| `cold` | none | the reference. Section 11.2: cold has no inter-point coupling |
| `warm` | nearest-valid coarse point, section 11.3's rule at stride 4 | the subject |
| `self` | the point's own converged `theta_unconstrained` | **(i2) positive control.** "Warm saves nothing" and "`x0` never reached the optimizer" are byte-identical in the output. If iterations do not collapse here, `x0` is inert and nothing else may be quoted |
| `random` | a coarse point at index distance > 6, fixed seed | **(i7) the discriminating control.** A saving over the moment ladder is not evidence for the two-pass GEOMETRY. If `warm` ~= `random`, proximity buys nothing and 2c owes far less than section 11.1 describes |

**THE FIXTURE IS THE MEASUREMENT'S WEAKEST POINT, SO IT IS BUILT AGAINST THAT.**
Warm-starting's benefit is entirely a claim about neighbours being similar, so a
field of independent draws would measure nothing -- the same defect section 11.2
already flags for hysteresis. The true parameters vary **smoothly within a
regime**, and the field carries a **sharp regime boundary** -- a change of
family, not merely of scale -- placed **between** the coarse columns so that
cross-regime warm sources genuinely occur and the lowest-`x` tie-break is
exercised. Boundary-crossing points are labelled and reported apart.

**AND THE DATA DOES NOT COME FROM THE CODE UNDER TEST.** The field is drawn from
covariance matrices written from the textbook Matern ACF below, never from
`metamer.core.statespace`, so a slip in a family's construction cannot cancel
between the fixture and the fit. The cold arm and the warm arm share `fit` on
purpose: the question is about one optimizer's path, not about correctness.

**A CONSTRAINT FOUND WHILE WRITING THIS, AND IT IS A FINDING ABOUT PRODUCTION.**
`fit.py:227` reads `warm = None if x0 is None else x0[b : b + 1, c, :p]`, so
`x0` is **call-level all-or-nothing**: either every (series, candidate) in the
batch gets a warm start or none does. Section 11.3's spiral requires the
opposite -- *"on exhaustion fall back to the moment-init ladder with the rung
recorded as such"* -- which is a per-(series, candidate) decision. **If the
mechanism survives this spike, `fit` needs a per-cell warm-start selector rather
than one array**, and that is a signature change nothing in the plan currently
owns. Here it is handled by measuring only the points that have a valid source
for every candidate, and reporting the excluded count.

Usage:
    warmstart-spike-harness.py <out.jsonl> [n_side] [n_time] [stride] [repeats]
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import replace
from typing import Any, TextIO

import numpy as np
from numpy.typing import NDArray
from threadpoolctl import threadpool_limits

from metamer.core.criteria import Criterion
from metamer.core.fit import FitResult, fit
from metamer.core.lint import lint
from metamer.core.registry import kernel_registry
from metamer.core.signal import Constant, SignalSpec, Trend
from metamer.core.terms import ProcessSpec, TermSpec

SQRT3 = np.sqrt(3.0)

# The regime boundary sits at this column: strictly between the coarse columns 4
# and 8 at stride 4, so a pass-2 point at column 6 is equidistant from a
# same-regime source and a cross-regime one and the lowest-x tie-break decides.
BOUNDARY_COL = 6

# The random-distant arm's source must be this far away in index space, or it is
# measuring proximity again under another name.
DISTANT_MIN = 6


def term(kind: str, **defaults: float) -> TermSpec:
    """Build a `TermSpec` from a registered family, overriding its defaults."""
    family = kernel_registry[kind]()
    specs = {
        name: replace(spec, default=defaults.get(name, spec.default))
        for name, spec in family.param_specs().items()
    }
    return TermSpec(
        kind=kind, params=specs, ordering_param=getattr(family, "ordering_param", None)
    )


def candidate_set() -> list[ProcessSpec]:
    """Three candidates, lint-clean by construction.

    No two terms of the same kind with a free timescale, so section 4.5's
    exchangeability cannot fire and parameter disagreement between the arms
    cannot be label switching wearing hysteresis' clothes.
    """
    return [
        ProcessSpec((term("white"),)),
        ProcessSpec((term("matern12"), term("white"))),
        ProcessSpec((term("matern32"), term("white"))),
    ]


def matern_cov(
    t: NDArray[np.float64], kind: str, sigma: float, rho: float
) -> NDArray[np.float64]:
    """Textbook Matern covariance, written here rather than imported.

    Rasmussen & Williams eq. 4.9 at nu = 1/2 and nu = 3/2. This is the fixture's
    only source of truth about the families, and it deliberately shares no code
    with `metamer.core.statespace`.
    """
    d = np.abs(t[:, None] - t[None, :])
    if kind == "matern12":
        cov = sigma**2 * np.exp(-d / rho)
    elif kind == "matern32":
        cov = sigma**2 * (1.0 + SQRT3 * d / rho) * np.exp(-SQRT3 * d / rho)
    else:
        raise ValueError(kind)
    return np.asarray(cov, dtype=np.float64)


def true_params(row: int, col: int, n_side: int) -> dict[str, Any]:
    """The field: smooth within a regime, with one sharp family boundary.

    Region A (col < BOUNDARY_COL) is Matern nu=3/2 plus white with a long,
    smoothly varying timescale; region B is Matern nu=1/2 plus white with a
    short one. Both vary smoothly in `row`, so neighbours within a regime are
    genuinely similar and neighbours across the boundary are genuinely not.
    """
    u = row / (n_side - 1)
    if col < BOUNDARY_COL:
        v = col / max(BOUNDARY_COL - 1, 1)
        return {
            "regime": "A",
            "kind": "matern32",
            "sigma": 1.0 + 0.5 * u,
            "rho": 0.8 + 1.2 * v,
            "white": 0.4,
        }
    v = (col - BOUNDARY_COL) / max(n_side - 1 - BOUNDARY_COL, 1)
    return {
        "regime": "B",
        "kind": "matern12",
        "sigma": 0.7 + 0.4 * u,
        "rho": 0.30 + 0.30 * v,
        "white": 0.5,
    }


def build_field(
    n_side: int, n_time: int
) -> tuple[NDArray[np.float64], NDArray[np.float64], list[dict[str, Any]]]:
    """Draw the field. Returns (y, t, per-point truth) with y in row-major order."""
    t = np.arange(n_time, dtype=np.float64) / 12.0
    rows = []
    truth = []
    for row in range(n_side):
        for col in range(n_side):
            spec = true_params(row, col, n_side)
            cov = matern_cov(t, spec["kind"], spec["sigma"], spec["rho"])
            cov = cov + spec["white"] ** 2 * np.eye(n_time)
            rng = np.random.default_rng(1_000_000 + row * 1000 + col)
            draw = rng.multivariate_normal(np.zeros(n_time), cov)
            rows.append(draw + 2.0 + 0.3 * (t - t.mean()))
            truth.append(spec | {"row": row, "col": col})
    return np.asarray(rows), t, truth


def coarse_indices(n_side: int, stride: int) -> list[tuple[int, int]]:
    """Pass-1 membership: every stride-th point in DATASET coordinates."""
    return [(r, c) for r in range(0, n_side, stride) for c in range(0, n_side, stride)]


def spiral_source(
    target: tuple[int, int],
    coarse: list[tuple[int, int]],
    ok: NDArray[np.bool_],
    cand: int,
    max_radius: int,
) -> tuple[int, int] | tuple[None, None]:
    """Section 11.3's rule: nearest valid coarse point, ties lowest y then x.

    Searched outward in Chebyshev radius. Returns (coarse position, radius), or
    (None, None) on exhaustion -- which section 11.3 says falls back to the
    moment ladder with the rung recorded as such.

    The tie-break is the load-bearing part: it is what makes the choice
    independent of iteration order, hence of tiling, hence of --memory-budget.
    """
    tr, tc = target
    for radius in range(max_radius + 1):
        ring = [
            (i, (r, c))
            for i, (r, c) in enumerate(coarse)
            if max(abs(r - tr), abs(c - tc)) == radius and ok[i, cand]
        ]
        if ring:
            best = min(ring, key=lambda item: (item[1][0], item[1][1]))
            return best[0], radius
    return None, None


def arm_x0(
    n_points: int,
    n_cand: int,
    p_max: int,
    sources: NDArray[np.int64],
    donor: NDArray[np.float64],
) -> NDArray[np.float64]:
    """Assemble (B, M, p_max) warm starts from a per-(point, candidate) source."""
    out = np.full((n_points, n_cand, p_max), np.nan)
    for b in range(n_points):
        for c in range(n_cand):
            out[b, c, :] = donor[sources[b, c], c, :]
    return out


def summarise(result: FitResult, arm: str, seconds: float) -> dict[str, Any]:
    """One row per arm run: the timing and the determinism fingerprint."""
    return {
        "kind": "timing",
        "arm": arm,
        "seconds": seconds,
        "n_iter_total": int(result.n_iter.sum()),
        "loglik_fingerprint": float(np.nansum(result.loglik)),
    }


def emit(handle: TextIO, record: dict[str, Any]) -> None:
    """Write one JSONL record and flush, so a killed run keeps what it had."""
    handle.write(json.dumps(record) + "\n")
    handle.flush()


def main() -> None:  # noqa: PLR0912, PLR0915
    """Run every arm and write the JSONL the analyser reads."""
    out_path = sys.argv[1]
    n_side = int(sys.argv[2]) if len(sys.argv) > 2 else 16
    n_time = int(sys.argv[3]) if len(sys.argv) > 3 else 96
    stride = int(sys.argv[4]) if len(sys.argv) > 4 else 4
    repeats = int(sys.argv[5]) if len(sys.argv) > 5 else 3

    y, t, truth = build_field(n_side, n_time)
    signal = SignalSpec([Constant(), Trend()])
    cands = candidate_set()
    n_cand = len(cands)

    lint_findings = {
        f"cand{i}": [str(f) for f in lint(spec, 1.0 / 12.0)]
        for i, spec in enumerate(cands)
    }

    coarse = coarse_indices(n_side, stride)
    coarse_flat = [r * n_side + c for r, c in coarse]
    coarse_set = set(coarse_flat)
    fine_flat = [i for i in range(n_side * n_side) if i not in coarse_set]

    handle = open(out_path, "w")
    emit(
        handle,
        {
            "kind": "config",
            "n_side": n_side,
            "n_time": n_time,
            "stride": stride,
            "repeats": repeats,
            "boundary_col": BOUNDARY_COL,
            "n_coarse": len(coarse_flat),
            "n_fine": len(fine_flat),
            "candidates": [str(c.spec_hash()) for c in cands],
            "lint_findings": lint_findings,
        },
    )

    with threadpool_limits(limits=1):
        # ---- Pass 1: the coarse points, cold. Their theta is every warm start's
        # source, so this runs once and outside the timed repeats.
        start = time.perf_counter()
        pass1 = fit(
            y[coarse_flat], t, signal, cands, criterion=Criterion.AIC, mask=None
        )
        emit(handle, summarise(pass1, "pass1", time.perf_counter() - start))

        p_max = pass1.theta_unconstrained.shape[2]
        coarse_ok = pass1.outcome == 0
        emit(
            handle,
            {
                "kind": "coarse_health",
                "ok_fraction": float(coarse_ok.mean()),
                "per_candidate_ok": [float(x) for x in coarse_ok.mean(axis=0)],
            },
        )

        # ---- The source maps. `warm` is section 11.3's rule; `random` is the
        # discriminating control and must be genuinely distant.
        rng = np.random.default_rng(20260823)
        warm_src = np.full((len(fine_flat), n_cand), -1, dtype=np.int64)
        warm_radius = np.full((len(fine_flat), n_cand), -1, dtype=np.int64)
        rand_src = np.full((len(fine_flat), n_cand), -1, dtype=np.int64)
        # P8's metric as first written -- "the spiral steps beyond radius 0" --
        # is mis-specified and always true: a pass-2 point is by construction not
        # a coarse point, so its nearest source is never at radius 0. The
        # quantity P8 was reaching for is whether the OK filter CHANGED the
        # choice, which is what makes the spiral load-bearing rather than
        # defensive. Recorded as a correction rather than a silent redefinition.
        ok_changed = np.zeros((len(fine_flat), n_cand), dtype=bool)
        all_ok = np.ones_like(coarse_ok)
        excluded: list[int] = []
        for b, flat in enumerate(fine_flat):
            target = (flat // n_side, flat % n_side)
            for c in range(n_cand):
                idx, radius = spiral_source(target, coarse, coarse_ok, c, n_side)
                geom, _ = spiral_source(target, coarse, all_ok, c, n_side)
                if idx is None:
                    excluded.append(flat)
                    continue
                ok_changed[b, c] = idx != geom
                warm_src[b, c] = int(idx)
                warm_radius[b, c] = int(radius) if radius is not None else -1
                far = [
                    i
                    for i, (r, cc) in enumerate(coarse)
                    if coarse_ok[i, c]
                    and max(abs(r - target[0]), abs(cc - target[1])) > DISTANT_MIN
                ]
                rand_src[b, c] = int(rng.choice(far)) if far else int(idx)

        keep = [b for b in range(len(fine_flat)) if (warm_src[b] >= 0).all()]
        emit(
            handle,
            {
                "kind": "source_map",
                "n_measured": len(keep),
                "n_excluded": len(fine_flat) - len(keep),
                "ok_filter_changed_source": float(
                    ok_changed[keep].mean() if keep else float("nan")
                ),
                "max_radius_used": int(warm_radius[keep].max()) if keep else -1,
            },
        )

        measured_flat = [fine_flat[b] for b in keep]
        y_fine = y[measured_flat]
        warm_src = warm_src[keep]
        warm_radius = warm_radius[keep]
        rand_src = rand_src[keep]

        # ---- Prep cold run: supplies the SELF arm's x0. Its timing is not used.
        start = time.perf_counter()
        prep = fit(y_fine, t, signal, cands, criterion=Criterion.AIC, mask=None)
        emit(handle, summarise(prep, "prep_cold", time.perf_counter() - start))

        self_x0 = prep.theta_unconstrained.copy()
        donor = pass1.theta_unconstrained
        arms = {
            "cold": None,
            "warm": arm_x0(len(keep), n_cand, p_max, warm_src, donor),
            "self": self_x0,
            "random": arm_x0(len(keep), n_cand, p_max, rand_src, donor),
        }

        # ---- The timed repeats. Arm order rotates so a drifting box does not
        # land the same way on the same arm three times.
        names = list(arms)
        detail_done = False
        for rep in range(repeats):
            order = names[rep % len(names) :] + names[: rep % len(names)]
            for name in order:
                start = time.perf_counter()
                res = fit(
                    y_fine,
                    t,
                    signal,
                    cands,
                    criterion=Criterion.AIC,
                    mask=None,
                    x0=arms[name],
                )
                seconds = time.perf_counter() - start
                row = summarise(res, name, seconds)
                row["repeat"] = rep
                emit(handle, row)

                if not detail_done or rep == 0:
                    for b in range(len(keep)):
                        flat = measured_flat[b]
                        spec = truth[flat]
                        for c in range(n_cand):
                            src = int(warm_src[b, c])
                            emit(
                                handle,
                                {
                                    "kind": "point",
                                    "arm": name,
                                    "flat": flat,
                                    "row": spec["row"],
                                    "col": spec["col"],
                                    "regime": spec["regime"],
                                    "cand": c,
                                    "n_iter": int(res.n_iter[b, c]),
                                    "outcome": int(res.outcome[b, c]),
                                    "rung": str(res.init_rung[b, c]),
                                    "loglik": float(res.loglik[b, c]),
                                    "theta": [float(v) for v in res.theta[b, c]],
                                    "theta_err": [
                                        float(v) for v in res.theta_err[b, c]
                                    ],
                                    "theta_u": [
                                        float(v) for v in res.theta_unconstrained[b, c]
                                    ],
                                    "best_index": int(res.ranking.best_index[b]),
                                    "source_regime": truth[coarse_flat[src]]["regime"],
                                    "cross_regime": (
                                        truth[coarse_flat[src]]["regime"]
                                        != spec["regime"]
                                    ),
                                    "spiral_radius": int(warm_radius[b, c]),
                                },
                            )
            detail_done = True

    handle.close()


if __name__ == "__main__":
    main()
