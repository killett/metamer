"""The README's smear figure section, and the generator that draws it.

**THE README IS AN ARTIFACT WITH READERS, AND THE FIGURE IS THE MOST-QUOTED
PART OF IT.** A figure travels without the paragraph around it, so what the
caption must say is a test rather than a review note -- which is Task 8's own
requirement and exit criterion 15's reading.

**AND THE GENERATOR IS CHECKED AGAINST THE COMMITTED REPORTS**, because a
figure with its own copy of the numbers is (j9) at the one artifact a reader
meets first.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
from typing import Any

import pytest

README = pathlib.Path("README.md")
FIGURE = pathlib.Path("docs/figures/phase2d-smear-figure.png")
PROVENANCE = pathlib.Path("docs/figures/phase2d-smear-figure.provenance.json")
GENERATOR = pathlib.Path("docs/superpowers/notes/phase2d-figure.py")
NOTES = pathlib.Path("docs/superpowers/notes")

#: **NOTHING HERE IMPORTS THE GENERATOR, AND THAT IS THE POINT.** The subject of
#: these tests is the committed ARTIFACTS -- the figure, its provenance record
#: and the reports -- not the plotting code. Importing the generator dragged
#: `matplotlib` into the suite, which is in the dev environment and **not in the
#: dependency set CI installs**, so this file passed locally and failed in CI on
#: its first push. **The local sweep and CI are designed to fail differently and
#: this is what that looks like.** The provenance record makes the import
#: unnecessary: it names the reports it was drawn from, so a checker needs no
#: second copy of the generator's paths and no knowledge of which file is which.

#: The section under test, by its own heading. **Sliced rather than searched
#: whole-file**: a phrase that happens to appear in the Usage section would
#: otherwise satisfy an assertion about the caption.
SECTION_HEADING = "### The warm-start smear, and what it is allowed to say"


def _section() -> str:
    """The figure's section text, from its heading to the next `## `."""
    text = README.read_text()
    start = text.index(SECTION_HEADING)
    rest = text[start + len(SECTION_HEADING) :]
    end = rest.find("\n## ")
    return rest if end == -1 else rest[:end]


@pytest.mark.parametrize(
    ("token", "what_it_pins"),
    [
        ("easy", "the rung"),
        ("20260830", "the seed"),
        ("32 × 12", "the geometry"),
        ("N = 630", "the record length"),
        ("construction 1", "the signal-free field"),
        ("construction 2", "the signal-bearing field"),
    ],
)
def test_the_figure_section_names_the_field_it_was_measured_on(token, what_it_pins):
    """A reader can say which field produced the figure, from the README alone.

    Behaviour: the section names the rung, the seed, the geometry and the
    record length, and distinguishes the two constructions.

    Expected value determined independently: each token is what the committed
    reports' instrument blocks record, read from the artifacts and not from
    this test's own memory.

    Bug this catches: **the figure being read as a measurement of altimetry** --
    the one thing the standing limitation forbids, and the failure mode a figure
    is most prone to because it travels without its paragraph. A section that
    names no field describes any field.
    """
    assert token in _section(), f"the figure section does not name {what_it_pins}"


def test_the_caption_carries_the_standing_limitation_and_names_its_closer():
    """The disclosure travels with the figure, not beside it.

    Behaviour: the section says the field is simulated and ours, that real
    altimetry's coherence is unmeasured, and that a spike on a real gridded
    product is what would close it.

    Expected value determined independently: the standing limitation as
    PROGRESS.md states it, which names the real-data spike as the closer.

    Bug this catches: **2d written up as having closed D1.** The saving and the
    absent artifact are both attractive results, and a caption that omits the
    limitation invites exactly the reading the limitation exists to prevent.
    """
    section = _section().lower()

    assert "simulated" in section, "the caption does not say the field is simulated"
    assert "chosen by us" in section, "the caption does not say the parameters are ours"
    assert "never been measured" in section, (
        "the caption does not say real altimetry's coherence is unmeasured"
    )
    assert "real gridded product" in section, (
        "the caption does not name the real-data spike as the closer"
    )


def test_the_reserved_position_names_its_content_and_its_owner():
    """An empty position with a named owner is a plan; one without is a gap.

    Behaviour: the section states that the misspecification figure is absent,
    names it as §16.2 item 4, and names Phase 6 as its owner.

    Expected value determined independently: E7's own words, which say the
    position is reserved and the absence stated.

    Bug this catches: a reserved position reading as a completed one -- a
    reader concluding item 4 shipped because the README mentions it -- or an
    owner-less gap wearing a plan's clothing.
    """
    section = _section()

    assert "item 4" in section, "the reserved position does not name its content"
    assert "Phase 6" in section, "the reserved position does not name its owner"
    assert "not built" in section.lower(), (
        "the section does not say the misspecification figure is absent"
    )


def test_every_number_in_the_section_is_tied_to_a_construction():
    """E1's constraint 2, at the boundary where the project meets its readers.

    Behaviour: the two savings and the two iteration counts appear in a table
    whose columns are the two constructions, so no headline number stands
    alone.

    Expected value determined independently: the four numbers are read out of
    the two committed reports here, and matched against the section's text.

    Bug this catches: **a number quoted without its population.** "+41.9%" with
    no construction beside it is the sentence that would travel into a slide,
    and it is true of exactly one of the two fields measured.
    """
    section = _section()
    one = json.loads(
        pathlib.Path("docs/superpowers/notes/phase2d-easy-rung-report.json").read_text()
    )
    two = json.loads(
        pathlib.Path(
            "docs/superpowers/notes/phase2d-difficulty-rung-report.json"
        ).read_text()
    )

    for report in (one, two):
        expected = f"{report_cold(report):.1f}"
        assert expected in section, (
            f"the section does not carry {expected} cold iterations per point"
        )

    saving = (report_cold(two) - report_warm(two)) / report_cold(two)
    assert f"{saving:.1%}" in section, "the section does not carry the measured saving"

    header = [line for line in section.splitlines() if line.startswith("| |")]
    assert header, "the numbers are not in a table with the constructions as columns"
    assert "construction 1" in header[0] and "construction 2" in header[0], (
        "the table's columns are not the two constructions, so its numbers do "
        "not carry the field they describe"
    )


def report_cold(report: dict[str, Any]) -> float:
    """Cold iterations per point, from a committed report."""
    return float(report["iterations"]["cold_per_point"])


def report_warm(report: dict[str, Any]) -> float:
    """Warm iterations per point, from a committed report."""
    return float(report["iterations"]["warm_per_point"])


@pytest.mark.parametrize(
    ("stale", "why_it_is_wrong"),
    [
        ("Phase 2c in progress", "2c closed 2026-08-29"),
        ("1174 tests", "the suite has grown since"),
        (
            "the benchmark harness used to pick the evaluation path.",
            "bench now carries the 2d benchmark, not only the evaluation spike",
        ),
        (
            "On a simulated field this cut iterations\nsubstantially",
            "it cut nothing on the signal-free construction",
        ),
    ],
)
def test_the_swept_claims_do_not_come_back(stale, why_it_is_wrong):
    """(a6): a sweep done once is a sweep that drifts back.

    Behaviour: four claims the 2d measurements falsified are absent from the
    README.

    Expected value determined independently: each string is the exact text that
    was in the README before this task, and the reason it is false is a
    measurement in the tree.

    Bug this catches: the same false sentence returning in a later edit -- which
    is how it survived from 2b to 2d in the first place. **The two-pass claim is
    the one that matters**: it says warm-starting cut iterations substantially
    on a simulated field, and on the signal-free construction it cut nothing.
    """
    assert stale not in README.read_text(), (
        f"a swept claim is back in the README: {why_it_is_wrong}"
    )


def test_the_readme_does_not_state_a_test_count_it_cannot_keep():
    """A number the README cannot check is a number that ages silently.

    Behaviour: the README describes the suite without pinning an exact test
    count that nothing verifies.

    Expected value determined independently: the failure that motivates it --
    the README said "1174 tests" while the suite held 1349, and nothing noticed
    because nothing read it.

    Bug this catches: a hand-maintained count drifting back in. **A count is
    only worth stating if something checks it**, and checking it here would
    make every subset run fail, since a `-k` selection collects fewer tests
    than the suite has. The honest repair is to describe the suite rather than
    count it, so this asserts the count is gone rather than that it is right.
    """
    text = README.read_text()

    stale = re.search(r"\b\d[\d,]*\s+tests,\s+`mypy --strict`", text)
    assert stale is None, (
        f"the README pins a test count nothing verifies: {stale.group(0)!r}; "
        "describe the suite instead, or add a check that survives a subset run"
    )
    assert "`mypy --strict`" in text, "the README no longer states its type-check bar"


def test_the_committed_figure_was_drawn_from_the_committed_reports():
    """The picture and the numbers cannot drift apart unnoticed.

    Behaviour: the provenance record written beside the figure names the two
    reports by content hash, and those hashes are what the reports hash to now.
    The profiles and iteration counts it records are the reports' own.

    Expected value determined independently: the reports are hashed here, from
    disk, by a path that shares no code with the generator's.

    Bug this catches: **a report edited and the figure not redrawn** -- after
    which the README shows a picture of an older run, with a caption quoting
    the newer numbers, and nothing in the suite disagrees. A first attempt at
    this test compared the generator's extraction against the same file the
    test had loaded, which is a tautology: it passed with a report deliberately
    corrupted underneath it. **The hash is what makes the comparison real.**
    """
    constructions = json.loads(PROVENANCE.read_text())["constructions"]
    assert set(constructions) == {"construction_1", "construction_2"}, (
        "the figure does not record both constructions, so it cannot be the "
        "comparison the caption claims"
    )

    for key, drawn in constructions.items():
        path = NOTES / drawn["report"]
        assert path.exists(), f"{key} names a report that is not in the tree"

        current = hashlib.sha256(path.read_bytes()).hexdigest()
        assert drawn["sha256"] == current, (
            f"{path.name} has changed since the figure was drawn: re-run "
            f"{GENERATOR} and commit the new figure and its provenance"
        )

        report = json.loads(path.read_text())
        expected = {s["arm"]: list(s["reading"]["profile"]) for s in report["smears"]}
        assert drawn["profiles"] == expected, (
            f"the figure's {key} profiles are not {path.name}'s"
        )
        assert set(expected) == {"cold", "warm", "n2"}, (
            "the figure would not draw all three arms, so a warm width would "
            "appear without the floor that makes it interpretable"
        )


def test_the_committed_figure_exists_and_the_readme_points_at_it():
    """The picture and the pointer travel together.

    Behaviour: the PNG is in the tree and the README's image link resolves to
    it.

    Expected value determined independently: the path is read out of the
    README's own markdown, not assumed.

    Bug this catches: a README that references a figure nobody committed --
    which renders as a broken image on the project's front page, and is the
    single most visible defect this repository could ship.
    """
    link = re.search(r"!\[[^\]]*\]\(([^)]+)\)", _section())
    assert link is not None, "the figure section has no image"

    referenced = pathlib.Path(link.group(1))
    assert referenced == FIGURE, f"the README points at {referenced}, not {FIGURE}"
    assert referenced.exists(), "the referenced figure is not in the tree"
    assert referenced.stat().st_size > 10_000, "the committed figure is a stub"
