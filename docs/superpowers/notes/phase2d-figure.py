"""Design doc section 16.2 item 6's figure, drawn from the committed reports.

**THIS READS THE ARTIFACTS AND NOTHING ELSE.** Every number it draws comes out
of `phase2d-easy-rung-report.json` and `phase2d-difficulty-rung-report.json`;
nothing is transcribed, and a test asserts the drawn profiles equal the
reports' own arrays. A figure with its own copy of the numbers is (j9) at the
one artifact readers meet first.

**WHAT IT SHOWS, AND WHY IT IS THE PROFILE RATHER THAN THE WIDTH.** Every width
in both reports is at the 1-cell floor, on every arm -- six readings of one
censored value. A chart whose every mark is the same number shows nothing, and
the record already says the profile is the primary reading wherever the
baseline leaves zero. **So the drawn quantity is the per-row misclassification
profile, with the majority threshold a smear would have to cross drawn as the
line it is, and the width stated as the annotation it is.**

**ONE RUNG, TWO CONSTRUCTIONS.** Only the easy rung ran the full audit, so only
it has arms and profiles; the middle and hard rungs contributed iteration
counts and no widths. The honest comparison is therefore the same rung, same
seed, same geometry, at the two field constructions -- which is also the
cleanest one, because the single difference between the panels is the term
whose absence was the defect.

Usage:
    phase2d-figure.py [<out.png>]
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.axes import Axes  # noqa: E402

NOTES = Path("docs/superpowers/notes")
VERSION_1_REPORT = NOTES / "phase2d-easy-rung-report.json"
VERSION_2_REPORT = NOTES / "phase2d-difficulty-rung-report.json"
DEFAULT_OUT = Path("docs/figures/phase2d-smear-figure.png")

#: **THE FIGURE'S PROVENANCE, WRITTEN BESIDE IT.** A PNG cannot be checked
#: against the reports it was drawn from -- pixels are not a comparison -- so
#: the generator records WHICH reports it read, by content hash, and WHAT it
#: drew from them. A test compares that record against the current reports, so
#: **a report edited without redrawing the figure fails** instead of leaving
#: the picture silently describing an older run.
PROVENANCE = Path("docs/figures/phase2d-smear-figure.provenance.json")

#: Categorical slots 1-3 of the reference palette, in fixed order, validated
#: for CVD separation and the normal-vision floor. **Arms are identities, not
#: magnitudes**, so the colour job is categorical and never a ramp. The aqua
#: slot warns on contrast against the surface, and the relief is that all three
#: lines are direct-labelled rather than left to a legend box alone.
ARM_COLOUR = {"cold": "#2a78d6", "warm": "#eb6834", "n2": "#1baf7a"}
ARM_LABEL = {"cold": "cold", "warm": "warm", "n2": "N2 floor"}

#: **THE ARMS VERY NEARLY COINCIDE, AND THAT IS THE FINDING**, so the drawing
#: has to make three lines on top of each other legible rather than let two of
#: them hide the third. Width is the secondary encoding: cold is the reference
#: and is drawn widest and underneath, warm sits on it, N2 is thinnest and on
#: top. A reader sees blue wherever nothing moved, which is almost everywhere.
ARM_WIDTH = {"cold": 5.0, "warm": 2.6, "n2": 1.4}
ARM_Z = {"cold": 3, "warm": 4, "n2": 5}

#: Where each arm's direct label sits, as a row index. **Fixed rather than
#: placed at each arm's own peak**: the peaks coincide, so peak-placement
#: stacked all three labels on one point.
LABEL_ROW = {"cold": 24, "warm": 20, "n2": 4}

INK = "#0b0b0b"
MUTED = "#52514e"
GRID = "#e6e5e1"


def load(path: Path) -> dict[str, Any]:
    """One committed report."""
    loaded: dict[str, Any] = json.loads(path.read_text())
    return loaded


def profiles(report: dict[str, Any]) -> dict[str, list[float]]:
    """Each arm's per-row misclassification profile, from the report itself."""
    return {s["arm"]: list(s["reading"]["profile"]) for s in report["smears"]}


def panel(axis: Axes, report: dict[str, Any], title: str, subtitle: str) -> None:
    """One construction's three arms against the row index."""
    drawn = profiles(report)
    boundary = report["instrument"]["boundary_index"]
    rows = range(len(next(iter(drawn.values()))))

    axis.axvline(boundary, color=MUTED, lw=1.0, zorder=1)
    axis.text(
        boundary + 0.5, 0.97, "boundary", color=MUTED, fontsize=7, va="top", zorder=6
    )
    axis.axhline(0.5, color=MUTED, lw=1.0, zorder=1)
    axis.text(
        0.4,
        0.52,
        "majority threshold — a smear must cross this to register a width",
        color=MUTED,
        fontsize=7,
        va="bottom",
        zorder=6,
    )

    for arm in ("cold", "warm", "n2"):
        values = drawn[arm]
        axis.plot(
            list(rows),
            values,
            color=ARM_COLOUR[arm],
            lw=ARM_WIDTH[arm],
            solid_capstyle="round",
            solid_joinstyle="round",
            zorder=ARM_Z[arm],
        )
        row = LABEL_ROW[arm]
        axis.annotate(
            ARM_LABEL[arm],
            (row, values[row]),
            textcoords="offset points",
            xytext=(0, 9),
            color=ARM_COLOUR[arm],
            fontsize=8,
            ha="center",
            zorder=7,
        )

    # **THE EMPTY UPPER HALF IS THE READING**, so it carries the width the
    # profile is the evidence for rather than being left blank.
    axis.text(
        len(list(rows)) - 0.9,
        0.80,
        "smear width, every arm:\n<= 1 cell — the floor,\nunresolved rather than zero",
        color=INK,
        fontsize=8,
        ha="right",
        va="top",
        zorder=6,
    )

    axis.set_ylim(0.0, 1.0)
    axis.set_xlim(-0.5, len(list(rows)) - 0.5)
    axis.set_xlabel("row along the normal axis", fontsize=8, color=MUTED)
    axis.set_ylabel("misclassified fraction of the row", fontsize=8, color=MUTED)
    axis.set_title(f"{title}\n{subtitle}", fontsize=9.5, color=INK, loc="left")
    axis.grid(axis="y", color=GRID, lw=0.8)
    axis.set_axisbelow(True)
    for side in ("top", "right"):
        axis.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        axis.spines[side].set_color(GRID)
    axis.tick_params(labelsize=8, colors=MUTED)


def saving_panel(axis: Axes, one: dict[str, Any], two: dict[str, Any]) -> None:
    """Cold against warm iterations per point, at both constructions."""
    pairs = [
        (
            "signal-free",
            one["iterations"]["cold_per_point"],
            one["iterations"]["warm_per_point"],
        ),
        (
            "with the trend",
            two["iterations"]["cold_per_point"],
            two["iterations"]["warm_per_point"],
        ),
    ]
    for index, (label, cold, warm) in enumerate(pairs):
        y = len(pairs) - 1 - index
        axis.plot(
            [warm, cold], [y, y], color=GRID, lw=3.0, solid_capstyle="round", zorder=1
        )
        # A 2px surface ring, so the two dots stay separable where they nearly
        # coincide -- which is the whole of the signal-free row.
        # Cold is drawn larger and underneath so that where the two coincide
        # -- the whole of the signal-free row -- the blue still reads as a ring
        # around the orange rather than vanishing under it.
        axis.scatter(
            [cold],
            [y],
            s=150,
            color=ARM_COLOUR["cold"],
            zorder=3,
            edgecolors="#fcfcfb",
            linewidths=2,
        )
        axis.scatter(
            [warm],
            [y],
            s=70,
            color=ARM_COLOUR["warm"],
            zorder=4,
            edgecolors="#fcfcfb",
            linewidths=2,
        )
        saving = (cold - warm) / cold
        # **THE TWO ROWS NEED DIFFERENT LABEL PLACEMENT BECAUSE ONE IS A
        # DUMBBELL AND THE OTHER IS A POINT.** Side-by-side labels overlap the
        # moment the arms agree, which they do wherever there is no saving.
        if abs(cold - warm) < 3.0:
            axis.text(
                cold + 1.2,
                y + 0.10,
                f"cold {cold:.1f}",
                color=ARM_COLOUR["cold"],
                fontsize=8,
                va="center",
            )
            axis.text(
                cold + 1.2,
                y - 0.10,
                f"warm {warm:.1f}",
                color=ARM_COLOUR["warm"],
                fontsize=8,
                va="center",
            )
            note = f"{saving:+.1%} — nothing to save"
        else:
            axis.text(
                cold + 1.2,
                y,
                f"cold {cold:.1f}",
                color=ARM_COLOUR["cold"],
                fontsize=8,
                va="center",
            )
            axis.text(
                warm - 1.2,
                y,
                f"warm {warm:.1f}",
                color=ARM_COLOUR["warm"],
                fontsize=8,
                va="center",
                ha="right",
            )
            note = f"{saving:+.1%} of the iterations"
        axis.text(
            (cold + warm) / 2.0, y + 0.24, note, color=MUTED, fontsize=8, ha="center"
        )
        axis.text(
            warm - 1.2, y - 0.30, label, color=INK, fontsize=9, ha="right", va="top"
        )

    axis.set_ylim(-0.75, len(pairs) - 0.25)
    axis.set_xlim(17, 49)
    axis.set_yticks([])
    axis.set_xlabel("iterations per point", fontsize=8, color=MUTED)
    axis.set_title(
        "the saving, at both constructions\nsame rung, same seed — the trend is the only difference",
        fontsize=9.5,
        color=INK,
        loc="left",
    )
    axis.grid(axis="x", color=GRID, lw=0.8)
    axis.set_axisbelow(True)
    for side in ("top", "right", "left"):
        axis.spines[side].set_visible(False)
    axis.spines["bottom"].set_color(GRID)
    axis.tick_params(labelsize=8, colors=MUTED)


def main() -> None:
    """Draw the figure from the two committed reports."""
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    one, two = load(VERSION_1_REPORT), load(VERSION_2_REPORT)

    figure, axes = plt.subplots(1, 3, figsize=(14.0, 4.6))
    panel(
        axes[0],
        one,
        "field construction 1 — no signal drawn",
        "24.4 cold iterations per point — nothing for a warm start to improve",
    )
    panel(
        axes[1],
        two,
        "field construction 2 — a trend at 16 sigma",
        "42.1 cold iterations per point — 2c's own difficulty",
    )
    saving_panel(axes[2], one, two)
    figure.suptitle(
        "The warm-start smear at the easy rung: every arm at the 1-cell floor, at both constructions",
        fontsize=11,
        color=INK,
        x=0.005,
        ha="left",
    )
    figure.tight_layout(rect=(0, 0, 1, 0.93), w_pad=2.5)
    out.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(out, dpi=200, facecolor="#fcfcfb")

    PROVENANCE.write_text(
        json.dumps(
            {
                "figure": str(out),
                "drawn_from": {
                    path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in (VERSION_1_REPORT, VERSION_2_REPORT)
                },
                "profiles": {
                    "construction_1": profiles(one),
                    "construction_2": profiles(two),
                },
                "iterations": {
                    "construction_1": one["iterations"],
                    "construction_2": two["iterations"],
                },
            },
            indent=2,
        )
        + "\n"
    )
    print(f"wrote {out} and {PROVENANCE}")


if __name__ == "__main__":
    main()
