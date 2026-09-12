#!/usr/bin/env python
"""Wiring one -- the smoke: does `batch.audit` reach a rung report, end to end?

**THIS IS NOT A MEASUREMENT AND IT SAYS SO IN ITS OWN BYTES.** `is_a_smoke_run`
is `true` in the instrument block, the geometry is **26 x 2** against the
shipped **32 x 12** and the record length is **24** against **630**. Task 9's
rule already refuses a report carrying that flag as evidence for any criterion,
and **the report this writes is deliberately NOT one of `COMMITTED_REPORTS`**,
so criterion 12 stays reduced and its reminder does not fire. That is the
intended order: the reminder should fire on a real reading.

**WHAT IT ESTABLISHES IS WIRING, WHICH NO UNIT TEST CAN REACH.** `run_rung` is
excluded from `pixi run test` (E7), so every line below that joins the audit to
the rung report -- the lint mapping built per spec, the trend column taken from
the shipped `design_info`, the sampling interval read off the contract, the
strata computed over arms the rung already fitted, the lift onto `RungQuantity`,
and the `strata` key landing where 2d's criterion-12 guard looks -- runs here or
nowhere.

**THE POSITIVE CONTROL IS THE FIRST RECORD AND IT IS BEFORE THE GATE.** (i2):
`MOVE = 0` is the comfortable reading of a clean decomposition, and a rule that
cannot see a move produces the same integer as a population that has none. A
gate refusal is the cheapest opportunity there is to discover the instrument is
broken, so the control must not sit behind one.

**NO PREDICTIONS FILE ACCOMPANIES THIS, AND THAT IS DELIBERATE.** Predictions
are owed before a measurement; this measures nothing. Every expectation below is
a WIRING fact -- a key present, an identity holding, a type arriving -- asserted
inline, and the run refuses rather than reports when one fails. **No magnitude
here transfers to the shipped geometry.**

Usage:
    wiring-one-harness.py <out.jsonl>   # runs BOTH gate branches
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, TextIO

from threadpoolctl import threadpool_limits

from metamer.batch.audit_report import (
    MIN_STRATUM_MEMBERS,
    KappaBin,
    decomposition_selftest,
)
from metamer.bench import fields, host, report
from metamer.bench.report import decomposition_from_record

#: The field's draw seed. **THE SAME ONE THE EASY RUNG'S SMOKE USED**, so this
#: exercises the same field construction and any difference in what comes back
#: is a difference in the wiring rather than in the draw.
FIELD_SEED = 20_260_830

#: The seed the committed CLEAN driver smoke was drawn at. **BOTH BRANCHES ARE
#: RUN, as `phase2d-driver-smoke.md` ran both branches of E6's gate.** At
#: `FIELD_SEED` this geometry comes back CONTAMINATED -- the easy rung
#: harness's own smoke recorded `null_cells = 7.0` there -- and a contaminated
#: rung never computes its widths, so a run at that seed alone would never
#: exercise `build_report` with widths and strata together.
CLEAN_SEED = 20_260_831

#: The reduced geometry. **26 is the smallest normal axis on which a legal
#: interior null line exists** -- the shipped offset is 12 and the null needs
#: `n_normal // 2 - 12 >= 1` -- so a field small enough to be fast cannot carry
#: the control, and this is as small as a wiring check gets.
SMOKE_N_NORMAL = 26
SMOKE_N_PARALLEL = 2
SMOKE_N_TIME = 24

#: The report this writes. **NOT under a `COMMITTED_REPORTS` name**, on purpose.
REPORT_PATH = Path(__file__).with_name("wiring-one-smoke-report.json")


def emit(handle: TextIO, record: dict[str, Any]) -> None:
    """Append one JSON record and flush, so a killed run keeps what it wrote."""
    handle.write(json.dumps(record, default=str) + "\n")
    handle.flush()


def _git_head() -> str:
    """The commit this ran at, for the record."""
    return subprocess.run(  # noqa: S603
        ["/usr/bin/env", "git", "rev-parse", "HEAD"],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()


def control() -> dict[str, Any]:
    """(i2), run before the gate: prove the rule can report a move.

    **THE DRIVER RUNS THIS TOO**, inside `run_rung`, before any fit. It is run
    here as well and emitted as a record, because a control whose result is not
    written down is a control nobody can check afterwards.
    """
    decomposition_selftest()
    return {
        "record": "selftest",
        "rule": "decomposition_selftest",
        "passed": True,
        "why": "a MOVE count of zero is a statement about the instrument until this passes",
    }


def _identity_holds(built: report.RungReport) -> bool:
    """Move + dropout + both-unavailable == differing, in EVERY stratum.

    **THE ARITHMETIC THAT MAKES A DECOMPOSITION A DECOMPOSITION.** A comment
    cannot fail; this can, and it is checked on the real report rather than on
    a constructed one because the serialiser sits between the two.
    """
    if built.strata is None:  # pragma: no cover - the caller checked
        raise RuntimeError("no strata to check the identity on")
    return all(
        stratum.by_move + stratum.by_dropout + stratum.by_both_unavailable
        == stratum.differing
        for stratum in built.strata.point_strata
    )


def smoke(handle: TextIO, directory: Path, seed: int, label: str) -> bool:
    """Run the pipeline at reduced geometry and read the wiring off the report."""
    started = time.perf_counter()
    built = report.run_rung(
        fields.rung("easy"),
        out_dir=directory / f"smoke-{label}",
        seed=seed,
        is_a_smoke_run=True,
        n_normal=SMOKE_N_NORMAL,
        n_parallel=SMOKE_N_PARALLEL,
        n_time=SMOKE_N_TIME,
    )
    seconds = time.perf_counter() - started
    record = built.reproducible()
    strata = record["strata"]

    if built.strata is None or strata is None:
        emit(
            handle,
            {
                "record": "refused",
                "why": "run_rung produced no strata, which is the whole wiring",
            },
        )
        return False

    # **EVERY NUMBER THE REPORT CAN REACH CARRIES ITS RUNG**, the audit's
    # included -- E1's constraint 2, which `audit_report` knows nothing about.
    every = built.quantities() + built.withheld()
    all_lifted = all(isinstance(q, report.RungQuantity) for q in every)

    points = built.strata.points
    populated = [s for s in built.strata.point_strata if s.members]
    emit(
        handle,
        {
            "record": "smoke",
            "branch": label,
            "field_seed": seed,
            "seconds": seconds,
            "is_a_smoke_run": built.instrument["is_a_smoke_run"],
            "geometry": [SMOKE_N_NORMAL, SMOKE_N_PARALLEL, SMOKE_N_TIME],
            "contaminated": built.contaminated,
            # **A FREE CONTROL ON A PATH THIS CHANGE DOES NOT TOUCH.** The null
            # is read off the warm SELECTION map and the strata are a different
            # measurement over the same arms, so an identical reading here is
            # evidence that the wiring moved nothing it was not meant to.
            "null_cells": built.null_line.cells,
            "null_at_floor": built.null_line.at_floor,
            "null_profile": list(built.null_line.profile),
            # --- the wiring facts, each a boolean a unit test cannot reach ---
            "strata_key_is_top_level": "strata" in record,
            "every_quantity_carries_its_rung": all_lifted,
            "quantities_on_the_report": len(every),
            "decomposition_identity_holds": _identity_holds(built),
            "seed_matches_the_block": built.strata.seed
            == built.instrument["audit_seed"],
            "min_stratum_members": built.strata.min_stratum_members,
            "floor_is_the_shipped_one": (
                built.strata.min_stratum_members == MIN_STRATUM_MEMBERS
            ),
            # --- what the strata actually came back with ---
            "audited_points": points.audited_points,
            "both_ranked": points.both_ranked,
            "cold_only_winner": points.cold_only_winner,
            "warm_only_winner": points.warm_only_winner,
            "no_margin": points.no_margin,
            "populated_point_strata": len(populated),
            "point_strata_total": len(built.strata.point_strata),
            "differing_total": sum(s.differing for s in populated),
            "move_total": sum(s.by_move for s in populated),
            "dropout_total": sum(s.by_dropout for s in populated),
            "both_unavailable_total": sum(s.by_both_unavailable for s in populated),
            # --- W3: the kappa axis is degenerate and membership is what moves ---
            "unreachable_kappa_bins": strata["unreachable_kappa_bins"],
            "populated_kappa_bins": sorted(
                {str(c.kappa) for c in built.strata.cell_strata if c.members}
            ),
            "kappa_axis_has_one_live_bin": len(
                {str(c.kappa) for c in built.strata.cell_strata if c.members}
            )
            <= 1,
            "candidates": [
                {
                    "candidate": entry.candidate[:12],
                    "lint_flagged": entry.lint_flagged,
                    "lint_findings": list(entry.lint_findings),
                    "attempted": entry.attempted,
                    "cold_ok": entry.cold_ok,
                    "cold_degenerate": entry.cold_degenerate,
                    "warm_degenerate": entry.warm_degenerate,
                    "both_ok": entry.both_ok,
                    "both_ok_fraction": entry.both_ok_fraction.value,
                }
                for entry in built.strata.candidates
            ],
            "headlines": [h["name"] for h in strata["headlines"]],
            "withheld_quantities": len(built.strata.withheld()),
            "notes": len(built.strata.notes),
            "lint_was_run": all(
                "identifiability lint was NOT run" not in note
                for note in built.strata.notes
            ),
            "not_a_measurement": (
                "26 x 2 at n_time 24 against the shipped 32 x 12 at 630. No "
                "magnitude here transfers; what this establishes is that the "
                "wiring runs and that the report carries what it must."
            ),
        },
    )

    path = REPORT_PATH.with_name(f"wiring-one-smoke-{label}-report.json")
    text = json.dumps(record, indent=2, default=str) + "\n"
    path.write_text(text)

    # **U1 ON A REAL ARTIFACT: the tests prove the rule, this proves the FILE.**
    # Re-read from disk rather than from the in-memory record, so the JSON
    # round-trip is inside the check rather than beside it.
    reread = json.loads(path.read_text())
    round_trip = decomposition_from_record(reread["arm_arrays"])
    in_memory = {
        (st.candidate, str(st.margin)): (
            st.differing,
            st.by_move,
            st.by_dropout,
            st.by_both_unavailable,
        )
        for st in built.strata.point_strata
        if st.members
    }
    emit(
        handle,
        {
            "record": "wrote",
            "branch": label,
            "path": str(path),
            "bytes": len(text.encode("utf-8")),
            "arm_arrays_bytes": len(json.dumps(record["arm_arrays"]).encode("utf-8")),
            "arms_in_the_artifact": sorted(reread["arm_arrays"]["per_arm"]),
            "decomposition_round_trips": round_trip == in_memory,
            "round_trip_strata": len(round_trip),
            "kappa_nulls": sum(
                1
                for arm in reread["arm_arrays"]["per_arm"].values()
                for row in arm["hessian_cond"]
                for v in row
                if v is None
            ),
        },
    )
    if round_trip != in_memory:
        emit(
            handle,
            {
                "record": "refused",
                "why": "the decomposition does not round-trip through the artifact",
                "from_file": {str(k): v for k, v in round_trip.items()},
                "from_memory": {str(k): v for k, v in in_memory.items()},
            },
        )
        return False

    # **REFUSE ON A WIRING FACT, NEVER MERELY REPORT IT.** A smoke that prints
    # `false` beside a green exit is a smoke nobody reads.
    for name, value in (
        ("strata_key_is_top_level", "strata" in record),
        ("every_quantity_carries_its_rung", all_lifted),
        ("decomposition_identity_holds", _identity_holds(built)),
        ("seed_matches_the_block", built.strata.seed == built.instrument["audit_seed"]),
        ("unreachable_bins_named", bool(built.strata.unreachable_kappa_bins)),
        (
            "the_two_upper_kappa_bins_are_the_unreachable_ones",
            set(built.strata.unreachable_kappa_bins)
            == {KappaBin.HALF_PRECISION, KappaBin.SINGULAR},
        ),
    ):
        if not value:
            emit(handle, {"record": "refused", "why": f"{name} is false"})
            return False
    return True


def main() -> int:
    """The control, then the gate, then the smoke."""
    out = Path(sys.argv[1])
    with out.open("a", encoding="utf-8") as handle:
        emit(
            handle,
            {
                "record": "header",
                "task": "wiring one -- batch.audit over a rung's arms, smoke only",
                "git_head": _git_head(),
                "preflight": "wiring-one-preflight.md",
                "field_seed": FIELD_SEED,
                "audit_seed": fields.AUDIT_SEED,
                "threads": 1,
                "closes_criterion_12": False,
                "why_not": (
                    "the report this writes is not one of COMMITTED_REPORTS, so "
                    "criterion 12's guard does not fire; the criterion stays "
                    "reduced with its closer changed to a population that has a "
                    "live differing set"
                ),
            },
        )
        # **BEFORE THE GATE, BECAUSE IT COSTS NOTHING AND GATES EVERYTHING.**
        emit(handle, control())

        reading = host.quiet_check()
        emit(handle, reading.as_record())
        if not reading.quiet:
            emit(handle, {"record": "refused", "reason": dict(host.REFUSAL)})
            return 1

        with threadpool_limits(limits=1), tempfile.TemporaryDirectory() as raw:
            # **BOTH BRANCHES, AND THE CONTAMINATED ONE FIRST.** A rung whose
            # null fires never computes its widths, so only the clean branch
            # exercises `build_report` with widths AND strata present -- and
            # only the contaminated one exercises the decision to keep the
            # strata when the widths are withheld.
            for seed, label in ((FIELD_SEED, "contaminated"), (CLEAN_SEED, "clean")):
                if not smoke(handle, Path(raw), seed, label):
                    return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
