"""The RSS validity channel classifies a failure instead of losing it.

**THE CHANNEL CONTRADICTED ITS OWN CONTRACT UNTIL 2026-10-21.** `rss_validity`
promises that a reading taken under reclaim "can neither confirm nor refute what
it was measuring", and the summary promises that every bracketed measurement
prints a line "whether it passed, abstained or was never judged". Both held only
for a PASSING block. The context manager's `yield` was bare and the witness was
read after it, so an assertion failing inside the block left at the `yield`: the
witness was never consulted and no line reached the summary. A reclaimed
reading could be downgraded from pass to INDETERMINATE, never from fail -- and a
failed measurement vanished, which is why a 2f Task 7 sweep printed
"5 measured" where six had run.

**AND THE COUNT HAS A PINNED SCOPE.** `0 INDETERMINATE` describes the bracketed
readings only. Ten live RSS tests run outside the bracket by Task 8i's margin
decision or because nobody surveyed them; the summary names each with its
outcome on every run, and the golden table below is what makes the next RSS
test a decision rather than a silence. Whether those ten SHOULD be bracketed is
open question 27, and this module does not decide it.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from _pytest.outcomes import Skipped

from tests import conftest
from tests.conftest import INDETERMINATE_RSS, RSS_MEASUREMENTS, rss_validity


def _pop_own(before: int) -> list[conftest.RssMeasurement]:
    """Remove the records a test constructed, so the real summary stays honest.

    A constructed failure left in the summary would teach every reader that one
    FAILED line is the healthy count -- the reason the channel's existing tests
    pop their own constructions.

    Args:
        before: `len(RSS_MEASUREMENTS)` before the construction.

    Returns:
        The removed records, oldest first.
    """
    removed = RSS_MEASUREMENTS[before:]
    del RSS_MEASUREMENTS[before:]
    return removed


def test_a_failing_assertion_in_a_margin_bracket_is_recorded_and_still_fails():
    """No witness: the failure stands, and it reaches the summary.

    Bug this catches: the bare `yield`. The failure propagated and NO record was
    appended, so the summary's per-measurement list silently lost a line --
    sweep 2 of 2f Task 7 printed "5 measured" while the floor ladder, the sixth,
    had failed inside its bracket.
    """
    before = len(RSS_MEASUREMENTS)
    observed = 1
    try:
        with pytest.raises(AssertionError, match="planted"):
            with rss_validity("a planted margin failure"):
                assert observed == 2, "planted"
        records = RSS_MEASUREMENTS[before:]
        assert len(records) == 1, "the failed measurement must still be recorded"
        (record,) = records
        assert record.what == "a planted margin failure"
        assert record.gate == "margin"
        assert record.failed is True
        assert record.indeterminate is False
    finally:
        _pop_own(before)


def test_a_failing_assertion_under_a_witnessed_shortfall_is_indeterminate():
    """The documented contract, now on the failing branch too.

    The witness reports a 5 MB shortfall; the assertion inside fails. A reading
    taken under reclaim can neither confirm NOR REFUTE what it measured, so this
    is INDETERMINATE -- skipped, recorded, and counted as such.

    Bug this catches: the asymmetry the bare `yield` produced. Under reclaim a
    passing reading became INDETERMINATE and a failing one became a FAILURE,
    blamed on the code under test, which is exactly the misreading the three
    ambient red tests of 2026-08-17 invited.
    """
    before = len(RSS_MEASUREMENTS)
    before_reasons = len(INDETERMINATE_RSS)
    observed = 1
    try:
        with pytest.raises(Skipped) as caught:
            with rss_validity("a planted failure under reclaim", witness=lambda: 5e6):
                assert observed == 2, "planted"
        assert "BELOW a reference" in str(caught.value)
        assert "5.0 MB" in str(caught.value)
        (record,) = RSS_MEASUREMENTS[before:]
        assert record.indeterminate is True
        assert record.failed is False
        assert record.gate == "witness"
        assert len(INDETERMINATE_RSS) == before_reasons + 1
        assert "a planted failure under reclaim" in INDETERMINATE_RSS[-1]
    finally:
        _pop_own(before)
        del INDETERMINATE_RSS[before_reasons:]


def test_a_failing_assertion_with_a_clean_witness_still_fails():
    """The negative case, so the new branch is not a blanket amnesty.

    Bug this catches: the over-correction -- every failure inside a witnessed
    bracket turned into INDETERMINATE whatever the witness said, which would
    make a witnessed RSS assertion unable to fail at all.
    """
    before = len(RSS_MEASUREMENTS)
    before_reasons = len(INDETERMINATE_RSS)
    observed = 1
    try:
        with pytest.raises(AssertionError, match="planted"):
            with rss_validity("a planted failure, witness clean", witness=lambda: 0.0):
                assert observed == 2, "planted"
        (record,) = RSS_MEASUREMENTS[before:]
        assert record.failed is True
        assert record.indeterminate is False
        assert record.gate == "witness"
        assert len(INDETERMINATE_RSS) == before_reasons
    finally:
        _pop_own(before)


def test_an_error_that_is_not_an_assertion_is_never_excused_by_reclaim():
    """Only an ASSERTION can be a reading; an error in the code is not one.

    The witness reports a shortfall and the block raises `ValueError`.

    Bug this catches: catching every exception into the INDETERMINATE branch,
    which would let a genuine defect -- a crash in the code under test -- vanish
    as an abstention on any box that happened to be under memory pressure.

    **THE SKIP IS CAUGHT AND FAILED HERE, NOT LEFT TO PROPAGATE.** `Skipped` is a
    `BaseException`, so it passes straight through `pytest.raises(ValueError)`
    and pytest reports the test SKIPPED: the very mutant this test exists for
    (excuse every error) turned it from red to a skip, observed 2026-10-22.
    """
    before = len(RSS_MEASUREMENTS)
    before_reasons = len(INDETERMINATE_RSS)
    try:
        try:
            with pytest.raises(ValueError, match="not a reading"):
                with rss_validity("a planted error under reclaim", witness=lambda: 5e6):
                    raise ValueError("not a reading")
        except Skipped as excused:
            pytest.fail(f"an error that is not an assertion was excused: {excused}")
        (record,) = RSS_MEASUREMENTS[before:]
        assert record.failed is True
        assert record.indeterminate is False
        assert len(INDETERMINATE_RSS) == before_reasons
    finally:
        _pop_own(before)


class _Reporter:
    """Records what the summary writes, as `test_stall.py`'s reporter does."""

    def __init__(self) -> None:
        self.lines: list[str] = []

    def write_sep(self, *_args: object, **_kwargs: object) -> None:
        """Ignore separators; the lines are the subject."""

    def write_line(self, line: str) -> None:
        """Keep one line.

        Args:
            line: What the summary wrote.
        """
        self.lines.append(line)


def test_the_summary_prints_a_failed_measurement_and_counts_it():
    """A FAILED line, and the count beside the INDETERMINATE count.

    Expected value determined independently: the count is the number of failed
    records in the list at the time of the call, read off the list rather than
    off the summary's own logic.

    Bug this catches: a record that carries `failed` and a summary that never
    reads it -- the instrument connected to nothing, (i2).
    """
    before = len(RSS_MEASUREMENTS)
    RSS_MEASUREMENTS.append(
        conftest.RssMeasurement(
            "a planted summary failure", "margin", None, False, False, failed=True
        )
    )
    expected = sum(1 for record in RSS_MEASUREMENTS if record.failed)
    reporter = _Reporter()
    try:
        conftest.pytest_terminal_summary(reporter)
    finally:
        _pop_own(before)

    (line,) = [
        entry for entry in reporter.lines if "a planted summary failure" in entry
    ]
    assert "FAILED" in line
    # **THE COUNTS LINE BY ITS OWN SHAPE**, not "any line": the exclusion header
    # below the count also says "N FAILED", and a test that matched it would
    # pass while the count it is about stayed wrong.
    (counts,) = [entry for entry in reporter.lines if " measured, " in entry]
    assert f"{expected} FAILED" in counts


def test_the_summary_names_every_unbracketed_rss_test_on_both_branches():
    """`0 INDETERMINATE` cannot be read as covering what it does not cover.

    Run twice: once with the session's records, once with none -- the "no
    RSS-difference measurement ran" branch, which returns early and is where a
    line added to only one branch goes missing.

    Bug this catches: a headline that reads complete and is not. 2f Task 7's
    third sweep printed `0 INDETERMINATE` while a live RSS assertion failed
    outside the bracket; this line is what makes that combination impossible to
    misread, because the failure is named directly under the count.
    """
    name = next(iter(conftest.UNBRACKETED_RSS_TESTS))
    saved_outcomes = dict(conftest.UNBRACKETED_RSS_OUTCOMES)
    saved_records = RSS_MEASUREMENTS[:]
    try:
        conftest.UNBRACKETED_RSS_OUTCOMES.clear()
        conftest.UNBRACKETED_RSS_OUTCOMES[name] = "failed"
        for records in (saved_records, []):
            RSS_MEASUREMENTS[:] = records
            reporter = _Reporter()
            conftest.pytest_terminal_summary(reporter)
            (header,) = [line for line in reporter.lines if "OQ27" in line]
            assert "outside rss_validity" in header
            assert "1 FAILED" in header
            for other in conftest.UNBRACKETED_RSS_TESTS:
                (row,) = [
                    line for line in reporter.lines if line.strip().startswith(other)
                ]
                expected = "failed" if other == name else "not run this session"
                assert expected in row, (other, row)
    finally:
        RSS_MEASUREMENTS[:] = saved_records
        conftest.UNBRACKETED_RSS_OUTCOMES.clear()
        conftest.UNBRACKETED_RSS_OUTCOMES.update(saved_outcomes)


def test_the_outcome_hook_keeps_the_worst_outcome_of_a_named_test():
    """The hook that feeds the line above, against pytest's own report shape.

    Bug this catches: a parametrized id (`name[case]`) missing the table because
    the key is the full node id, and a later passing case overwriting an earlier
    failure -- either would print "passed" for a test that failed.
    """
    name = next(iter(conftest.UNBRACKETED_RSS_TESTS))
    saved = dict(conftest.UNBRACKETED_RSS_OUTCOMES)
    try:
        conftest.UNBRACKETED_RSS_OUTCOMES.clear()
        for outcome in ("failed", "passed"):
            conftest.pytest_runtest_logreport(
                SimpleNamespace(
                    nodeid=f"tests/test_memory.py::{name}[case-{outcome}]",
                    when="call",
                    outcome=outcome,
                )
            )
        conftest.pytest_runtest_logreport(
            SimpleNamespace(
                nodeid="tests/test_memory.py::test_not_in_the_table",
                when="call",
                outcome="failed",
            )
        )
        assert conftest.UNBRACKETED_RSS_OUTCOMES == {name: "failed"}
    finally:
        conftest.UNBRACKETED_RSS_OUTCOMES.clear()
        conftest.UNBRACKETED_RSS_OUTCOMES.update(saved)


#: The OS-level readers in `metamer.core.machine`. Every other reader is DERIVED
#: from these by `_src_readers`, never listed: a hand-picked reader list missed
#: `measure_tile_peak` and `measure_evaluation_rss_slope` on its first draft,
#: which is the import probe's lesson -- a listed scope misses the next member.
_LEAF_READERS = frozenset(
    {"peak_rss_bytes", "current_rss_bytes", "reclaim_shortfall_bytes"}
)

#: What `_src_readers` derives today, pinned, so a new reader in `src/` is a
#: decision rather than a silent widening of every count below.
_DERIVED_READERS = frozenset(
    {"measure_floor", "measure_evaluation_rss_slope", "measure_tile_peak", "calibrate"}
)

#: RSS tests bracketed by `rss_validity`, pinned. `file::name`.
_BRACKETED = frozenset(
    {
        "test_exit_criteria.py::test_criteria_6_and_7_peak_rss_is_bounded_and_does_not_track_the_grid",
        "test_memory.py::test_peak_residency_does_not_move_with_the_iteration_cap",
        "test_memory.py::test_the_floor_ladder_reproduces_the_recorded_rungs",
        "test_memory.py::test_the_floor_with_the_input_open_exceeds_the_floor_without_it",
        "test_memory.py::test_the_validity_gate_declares_indeterminate_on_a_constructed_reclaim",
        "test_memory.py::test_the_validity_gate_stays_quiet_when_the_working_set_holds",
        "test_reuse.py::test_the_recompute_loop_retains_nothing_that_survives_its_warm_up",
        "test_warmstart.py::test_the_reader_does_not_load_pass_ones_store_whole",
    }
)

#: RSS tests that run a reader and ASSERT NO RSS VALUE -- an error path, a
#: refusal, the shape of a ladder, outcome counts. Not measurements of a working
#: set, so neither bracketed nor named under the count.
_NO_RSS_VALUE_ASSERTED = {
    "test_a_floor_probe_that_cannot_open_the_input_raises_rather_than_returning_zero": (
        "an error path"
    ),
    "test_a_non_positive_reference_is_refused_rather_than_certifying_the_reading": (
        "an argument refusal"
    ),
    "test_a_ladder_of_one_point_is_refused": "a refusal",
    "test_the_calibration_lands_on_the_sides_it_asked_for": "the ladder's shape",
    "test_the_calibration_records_what_its_slope_is_licensed_for": "the basis string",
    "test_a_converging_cap_reaches_a_regime_a_capped_one_does_not": "outcome counts",
}

#: Live, unbracketed RSS tests the scan CANNOT see, named by hand with the reason.
#: **THE SCAN'S NAMED GAP:** a reading that reaches the test through a store's
#: attrs -- written by `run()`, which measures its own floor -- crosses a module
#: boundary the scan deliberately does not follow, because following it would
#: make every `run()` caller an RSS test.
_OUTSIDE_THE_SCAN = frozenset(
    {"test_a_run_measures_its_own_floor_when_none_is_supplied"}
)


def _module_names(tree: ast.Module) -> dict[str, ast.AST]:
    """Module-level functions and assigned names, for intra-module resolution.

    Args:
        tree: A parsed module.

    Returns:
        Name to its defining node.
    """
    named: dict[str, ast.AST] = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            named[node.name] = node
        elif isinstance(node, ast.Assign | ast.AnnAssign):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    named[target.id] = node
    return named


def _names_a_reader(node: ast.AST, readers: frozenset[str]) -> bool:
    """Whether `node` NAMES a reader: as a name, an attribute, an import, or a
    call or import inside a code string.

    **IDENTIFIER-LEVEL, NOT SUBSTRING.** A substring rule counted
    `run(..., calibrate=True)`, `recalibrate` and prose mentions, doubling the
    scope with tests that read nothing. A keyword argument is not a name, and a
    docstring is a string with no call shape.

    Args:
        node: Any subtree.
        readers: The reader names.

    Returns:
        True if a reader is named.
    """
    alternation = "|".join(sorted(readers))
    code_shape = re.compile(
        rf"\b({alternation})\s*\(|\bimport\b[^\n]*\b({alternation})\b"
    )
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and child.id in readers:
            return True
        if isinstance(child, ast.Attribute) and child.attr in readers:
            return True
        if isinstance(child, ast.alias) and child.name.split(".")[-1] in readers:
            return True
        if (
            isinstance(child, ast.Constant)
            and isinstance(child.value, str)
            and code_shape.search(child.value)
        ):
            return True
    return False


def _reads(
    node: ast.AST, named: dict[str, ast.AST], readers: frozenset[str], seen: set[str]
) -> bool:
    """Whether `node`, or a module-level name it uses, transitively, names a reader.

    Args:
        node: The subtree.
        named: The module's own definitions -- the boundary of the closure.
        readers: The reader names.
        seen: Names already followed.

    Returns:
        True if a reader is reached within the module.
    """
    if _names_a_reader(node, readers):
        return True
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and child.id in named and child.id not in seen:
            seen.add(child.id)
            if _reads(named[child.id], named, readers, seen):
                return True
    return False


def _src_readers(package: Path) -> frozenset[str]:
    """Public `src/` functions that read RSS: a leaf, or one reaching a leaf in-module.

    Docstrings are excluded before matching, so a function that only mentions a
    leaf in prose is not a reader.

    Args:
        package: `src/metamer`.

    Returns:
        The derived reader names, leaves excluded.
    """
    derived: set[str] = set()
    for path in sorted(package.rglob("*.py")):
        tree = ast.parse(path.read_text())
        named = _module_names(tree)
        for name, node in named.items():
            if name.startswith("_") or name in _LEAF_READERS:
                continue
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            body = ast.Module(body=node.body, type_ignores=[])
            if body.body and isinstance(body.body[0], ast.Expr):
                if isinstance(getattr(body.body[0], "value", None), ast.Constant):
                    body.body = body.body[1:]
            if _reads(body, named, _LEAF_READERS, {name}):
                derived.add(name)
    return frozenset(derived)


def _rss_tests(directory: Path, readers: frozenset[str]) -> dict[str, bool]:
    """Every RSS test under `directory`, and whether it is bracketed.

    **THIS MODULE IS EXCLUDED, AND THAT IS THE ONE EXCLUSION.** Its scope test
    names every reader and would classify itself; its constructed channel tests
    use a `witness` callable and read nothing live.

    Args:
        directory: The tests directory.
        readers: Leaf and derived reader names.

    Returns:
        `file::name` to bracketed.
    """
    found: dict[str, bool] = {}
    for path in sorted(directory.glob("test_*.py")):
        if path.name == Path(__file__).name:
            continue
        source = path.read_text()
        tree = ast.parse(source)
        named = _module_names(tree)
        for name, node in named.items():
            if not name.startswith("test_"):
                continue
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            if _reads(node, named, readers, {name}):
                body = ast.get_source_segment(source, node) or ""
                found[f"{path.name}::{name}"] = "rss_validity(" in body
    return found


def test_the_rss_readers_are_derived_from_src_and_pinned():
    """The scope's own scope: which `src/` functions count as readers.

    Bug this catches: a new measurement function landing in `src/` -- a probe
    that reads RSS in a child -- and every test that calls it staying outside the
    scope below, because the reader list was written by hand. Pinned, so a new
    reader is noticed on the day it lands.
    """
    package = Path(__file__).resolve().parents[1] / "src" / "metamer"
    assert _src_readers(package) == _DERIVED_READERS


def test_every_rss_test_is_bracketed_unbracketed_by_decision_or_asserts_no_rss_value():
    """The golden scope table: an RSS test lands somewhere on purpose.

    **MEASURED 2026-10-21, AND IT IS NOT THE NINE TASK 8i SURVEYED.** The
    mechanical scope finds 24 tests: 8 bracketed, 10 live and unbracketed, and 6
    that run a reader and assert no RSS value. One more live test is outside the
    scan and named by hand. The pinned tables are the classification; the scan
    is what checks it is still true.

    Bug this catches: a new RSS test added outside the bracket and outside the
    summary's list -- which is how a live reading comes to fail under a headline
    of `0 INDETERMINATE` with nothing on the page connecting the two. It fails
    naming the test, so the next one is a decision rather than a discovery. Also
    a stale row: a renamed or deleted test left in a table claiming scope.
    """
    readers = _LEAF_READERS | _DERIVED_READERS
    tests = Path(__file__).resolve().parent
    found = _rss_tests(tests, readers)
    bracketed = {key for key, inside in found.items() if inside}
    unbracketed = {key.split("::", 1)[1] for key, inside in found.items() if not inside}

    assert found, "the scan must find RSS tests at all"
    assert bracketed == _BRACKETED, (
        f"bracketed RSS tests moved: new {sorted(bracketed - _BRACKETED)}, "
        f"gone {sorted(_BRACKETED - bracketed)}"
    )
    live_in_scan = set(conftest.UNBRACKETED_RSS_TESTS) - _OUTSIDE_THE_SCAN
    decided = live_in_scan | set(_NO_RSS_VALUE_ASSERTED)
    assert unbracketed == decided, (
        f"unbracketed RSS tests with no decision: {sorted(unbracketed - decided)}; "
        f"decided for but absent: {sorted(decided - unbracketed)}. A live one goes "
        f"in conftest.UNBRACKETED_RSS_TESTS with its reason, so the summary names "
        f"it; one asserting no RSS value goes in _NO_RSS_VALUE_ASSERTED."
    )
    assert not set(conftest.UNBRACKETED_RSS_TESTS) & set(_NO_RSS_VALUE_ASSERTED)

    # **THE HAND-NAMED GAP IS CHECKED BOTH WAYS**: each name must still exist,
    # and must still be invisible to the scan -- if the scan learns to see it,
    # the hand entry is stale and must move.
    assert _OUTSIDE_THE_SCAN <= set(conftest.UNBRACKETED_RSS_TESTS)
    defined = {
        node.name
        for path in tests.glob("test_*.py")
        for node in ast.parse(path.read_text()).body
        if isinstance(node, ast.FunctionDef)
    }
    assert _OUTSIDE_THE_SCAN <= defined, "a hand-named test no longer exists"
    assert not _OUTSIDE_THE_SCAN & unbracketed, "the scan now sees a hand-named test"
