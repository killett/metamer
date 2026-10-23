"""The report's markdown, rendered from its saved record and nothing else.

**THE STRUCTURE IS THE GUARANTEE; THE TOKEN CHECK IS ONLY ITS BACKSTOP.** 2f
Task 8's pre-flight, §2 and §6, fixes four things, each asserted by
`tests/test_report_main.py`:

- **The only input is the record as written.** The entry point parses the
  `report.json` it just saved and passes that object here, so the markdown is a
  function of the JSON -- not of the in-memory sections, which carry precision
  and fields the artifact does not.
- **This module imports from an arithmetic-free standard-library allowlist**:
  no numpy, no `metamer.*`, none of `math`, `operator`, `statistics`,
  `fractions`, `decimal`. With `divmod` and `pow` also unnamed, the only way
  left to divide here is a `BinOp`, which the golden rate-site table counts --
  and pins at 0. A deliberate `x.__truediv__(y)` stays outside that reach; the
  check is against accident, not an adversary.
- **Every number becomes text in exactly one function, `_number`.** A format
  spec is arithmetic the division count cannot see -- `.1%` multiplies by 100
  with no `BinOp` in sight -- so no other format spec, `%`-formatting or
  `.format` appears in the module.
- **The static text carries no digits**, so every numeric token in the markdown
  came from the record, which is what the backstop checks.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

__all__ = ["render"]

#: What the markdown prints for an absent value. No digits, so it can never be
#: mistaken for -- or counted as -- a number from the record.
ABSENT = "—"


def _number(value: object) -> str:
    """The one place a value from the record becomes text.

    **FOUR SIGNIFICANT FIGURES FOR A FLOAT, EXACT FOR AN INT.** A rate is a
    reading, not a measurement to sixteen digits; the record keeps the full
    value for anyone who needs it.

    Args:
        value: A JSON scalar from the record.

    Returns:
        Its text. `None` is `ABSENT`, a bool is yes/no.
    """
    if value is None:
        return ABSENT
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, int):
        return format(value, "d")
    if isinstance(value, float):
        return format(value, ".4g")
    return str(value)


def _row(cells: Sequence[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def _table(header: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    return [_row(header), _row(["---"] * len(header)), *(_row(r) for r in rows)]


def _rate(tally: Mapping[str, Any]) -> str:
    """A failure rate WITH its population, which D6 makes the record's job.

    `rate` is `failed / fitted` and `coverage_rate` is `failed / covered`, so
    each is printed beside exactly the two counts it divides.
    """
    if tally["rate"] is None:
        return f"no rate: {tally['unavailable']}"
    failed = _number(tally["failed"])
    return (
        f"{_number(tally['rate'])} ({failed} of {_number(tally['fitted'])} "
        f"fitted); coverage {_number(tally['coverage_rate'])} ({failed} of "
        f"{_number(tally['covered'])} covered)"
    )


def _distribution(counts: Mapping[str, Any]) -> str:
    if not counts:
        return ABSENT
    return ", ".join(f"{key}: {_number(count)}" for key, count in counts.items())


def _store(record: Mapping[str, Any]) -> list[str]:
    store = record["store"]
    lines = [
        "## The store",
        "",
        f"`{store['path']}` — {_number(store['complete'])} of "
        f"{_number(store['total'])} tiles complete.",
    ]
    if store["scope"]:
        lines += ["", store["scope"]]
    lines += ["", "**Disagreements between records in this store:**", ""]
    lines += [f"- {note}" for note in store["disagreements"]] or ["- none found"]
    return lines


def _numbers(record: Mapping[str, Any]) -> list[str]:
    numbers = record["numbers"]
    lines = ["## Outcomes", ""]
    lines += _table(
        ["outcome", "cells"],
        [[name, _number(count)] for name, count in numbers["by_branch"].items()],
    )
    lines += ["", "## Failure rates", ""]
    for row in numbers["by_candidate"]:
        lines.append(f"- **{row['candidate']}**: {_rate(row['tally'])}")
    lines.append(
        f"- **any candidate, per point**: {_rate(numbers['aggregate'])}",
    )
    if numbers["caveat"]:
        lines += ["", f"*{numbers['caveat']}*"]
    return lines


def _selectability(record: Mapping[str, Any]) -> list[str]:
    section = record["selectability"]
    lines = [
        "## Selectability",
        "",
        f"Candidates converged per point: {_distribution(section['converged'])} "
        f"(unset {_number(section['unset'])}; in domain "
        f"{_number(section['in_domain'])}, out of domain "
        f"{_number(section['out_of_domain'])}).",
        "",
    ]
    lines += _table(
        [
            "criterion",
            "contention",
            "no winner",
            "unwritten",
            "unrankable, infinite",
            "unrankable, not scored",
        ],
        [
            [
                row["criterion"],
                _distribution(row["contention"]),
                _number(row["no_winner"]),
                _number(row["unwritten"]),
                _number(row["unrankable_infinite"]),
                _number(row["unrankable_not_scored"]),
            ]
            for row in section["by_criterion"]
        ],
    )
    lines += ["", f"*{section['caveat']}*"]
    lines += [f"- defect: {defect}" for defect in section["defects"]]
    return lines


def _primitives(record: Mapping[str, Any]) -> list[str]:
    section = record["primitives"]
    lines = ["## Primitives and provenance", ""]
    for name in ("n_valid", "iterations"):
        dist = section[name]
        lines.append(
            f"- `{name}`: {_distribution(dist['counts'])} (unset "
            f"{_number(dist['unset'])} of {_number(dist['population'])})"
        )
    lines += [f"- `{name}`: `{value}`" for name, value in section["hashes"].items()]
    lines += [
        f"- registry version `{section['registry_version']}`, tile side "
        f"{section['tile_side_basis']}",
        f"- candidates resolved at {section['resolved_at']}",
    ]
    for candidate in section["resolved_candidates"] or []:
        lines.append(
            f"  - {candidate['label']}: spec `{candidate['spec_hash']}`, engine "
            f"{candidate['engine']}"
        )
    return lines


def _arrangement(name: str, arrangement: Mapping[str, Any]) -> list[str]:
    if not arrangement["available"]:
        return [name, ABSENT, ABSENT, ABSENT, ABSENT, arrangement["reason"]]
    return [
        name,
        _number(arrangement["observed"]),
        _number(arrangement["null_median"]),
        _number(arrangement["z"]),
        _number(arrangement["p"]),
        f"{_number(arrangement['failures'])} failures among "
        f"{_number(arrangement['eligible'])} eligible; "
        f"{_number(arrangement['permutations'])} permutations, seed "
        f"{_number(arrangement['seed'])}",
    ]


def _clustering(record: Mapping[str, Any]) -> list[str]:
    section = record["clustering"]
    lines = ["## Clustering of failures", ""]
    # **BOTH ARMS IN FULL, THE REPORTED ONE FIRST AND MARKED ONCE** (D4). The
    # labels are the record's own keys, so the renderer names no arm itself.
    reported = section["reported"]
    others = [name for name in ("unwrapped", "wrapped") if name != reported]
    for name in [reported, *others]:
        arm = section[name]
        if arm is None:
            continue
        rows = [_arrangement(label, item) for label, item in arm["by_candidate"]]
        rows.append(_arrangement(section["headline_label"], arm["aggregate"]))
        mark = ", reported" if name == reported else ""
        lines += [f"**{name} arm{mark}**", ""]
        lines += _table(["population", "join count", "null median", "z", "p", ""], rows)
        lines += [""]
    lines += [f"Domain span: {section['span_note']}."]
    return lines


def _early_abort(record: Mapping[str, Any]) -> list[str]:
    section = record["early_abort"]
    lines = ["## Early abort", "", f"{section['reason']}."]
    if section["rows"]:
        lines += [""] + _table(
            ["candidate", "rate", "failed", "live", "dropped", "provenance"],
            [
                [
                    row["candidate"],
                    f"{_number(row['rate'])} over {row['denominator']}",
                    _number(row["failed"]),
                    _number(row["live"]),
                    _number(row["dropped"]),
                    row["provenance"],
                ]
                for row in section["rows"]
            ],
        )
    lines += [f"- defect: {defect}" for defect in section["defects"]]
    return lines


def _maps(record: Mapping[str, Any]) -> list[str]:
    section = record["maps"]
    lines = ["## Maps", ""]
    if not section["drawn"]:
        lines += [
            f"Not drawn: install the `{section['extra']}` extra to draw them.",
            "",
        ]
    for entry in section["maps"]:
        where = f"`{entry['png']}`" if entry["drawn"] else "not drawn"
        lines.append(
            f"- {entry['title']} — {where}; blocks of "
            f"{' × '.join(_number(side) for side in entry['block'])}, "
            f"{_number(entry['masked_blocks'])} masked"
        )
    for entry in section["unmapped"]:
        lines.append(f"- {entry['name']}: no map — {entry['reason']}")
    return lines


def render(record: Mapping[str, Any]) -> str:
    """The report's markdown, from the parsed `report.json`.

    Args:
        record: The saved record, as `json.loads` returned it.

    Returns:
        The markdown, ending in a newline.
    """
    lines = [
        "# metamer report",
        "",
        f"metamer `{record['metamer_version']}`. Every value here is in "
        "`report.json`, at full precision.",
        "",
    ]
    for section in (
        _store,
        _numbers,
        _selectability,
        _primitives,
        _clustering,
        _early_abort,
        _maps,
    ):
        lines += [*section(record), ""]
    return "\n".join(lines).rstrip("\n") + "\n"
