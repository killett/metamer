"""`python -m metamer.report <store>`: the entry point, its exit codes, and render-from-record.

2f Task 8, written against the pre-flight's Task 8 section and its addendum
(`docs/superpowers/notes/phase2f-preflight.md`). **The structure carries the
guarantees and the behavioural tests check that the structure is wired**: the
renderer's only input is the saved record, the exit codes are D13's table, and
writability is checked before the permutation null runs.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import shutil
import subprocess
import sys
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import zarr

import metamer.exitcodes as exitcodes
from metamer.batch import validation
from metamer.batch.input import InputContractError
from metamer.exitcodes import ExitCode
from tests import test_report_reader

SRC = Path(__file__).resolve().parents[1] / "src" / "metamer"


def _imported_modules(path: Path) -> set[str]:
    """Every module name a file imports, at any depth, by its own spelling."""
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names.add(node.module)
    return names


# ---------------------------------------------------------------------------
# A. The exit-code table, moved from behind the boundary
# ---------------------------------------------------------------------------


def test_the_exit_code_table_is_one_object_wherever_it_is_imported_from():
    """`validation.ExitCode` IS `exitcodes.ExitCode`, not an equal copy.

    Expected value determined independently: D13 -- *"one published table, not
    a second"* -- so the only correct relation is identity.

    Bug this catches: a second enum with the same values. Two `IntEnum`s with
    equal values compare equal as ints, so every `==` and every exit status
    would agree until the next appended member landed in one table and not the
    other. **Only identity distinguishes them**, which is why this is `is`.
    """
    assert validation.ExitCode is exitcodes.ExitCode


def test_the_exit_code_module_imports_only_the_standard_library():
    """The table's module drags nothing in, so the report can import it.

    Expected value determined independently: the pre-flight addendum's reason
    for the move -- `metamer.batch.validation` loads `pydantic`, which the
    report's boundary forbids -- so the new module may import only from the
    standard library, listed here by hand.

    Bug this catches: the move re-importing what it was made to leave behind,
    e.g. a convenience `from metamer.batch.validation import ...` for a
    docstring cross-reference.
    """
    assert _imported_modules(SRC / "exitcodes.py") <= {"__future__", "enum"}


# ---------------------------------------------------------------------------
# The entry point: shared machinery
# ---------------------------------------------------------------------------

#: The reader's real-run store, shared rather than rebuilt: a fixture is found
#: by name in this module's namespace, and the reader's tests own it.
finished_store = test_report_reader.finished_store

#: The module the entry point lives in, by path, for the structural checks.
MAIN = SRC / "report" / "__main__.py"
RENDER = SRC / "report" / "render.py"


def _exit(argv: Sequence[str]) -> int:
    """The entry point's exit status, whether it returns or raises `SystemExit`.

    `_Parser.error` raises, as the batch CLI's does; every other path returns.
    """
    from metamer.report.__main__ import main

    try:
        return int(main(list(argv)))
    except SystemExit as stop:
        return int(stop.code) if isinstance(stop.code, int) else -1


def _default_out(store: Path) -> Path:
    """Where the report writes when `--out` is absent -- the pre-flight's definition."""
    return store.parent / f"{store.name}.report"


def _copy(store: Path, tmp_path: Path, name: str = "copy.zarr") -> Path:
    target = tmp_path / name
    shutil.copytree(store, target)
    return target


def _snapshot(store: Path) -> dict[str, str]:
    """Every file under the store, by relative path, to its content hash."""
    return {
        str(path.relative_to(store)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(store.rglob("*"))
        if path.is_file()
    }


@pytest.fixture(scope="module")
def reported(
    finished_store: Path, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[tuple[Path, dict[str, Any], str]]:
    """The full report on the real store, run once: out dir, record, markdown."""
    store = _copy(finished_store, tmp_path_factory.mktemp("reported"), "out.zarr")
    assert _exit([str(store)]) == ExitCode.OK
    out = _default_out(store)
    yield (
        out,
        json.loads((out / "report.json").read_text()),
        (out / "report.md").read_text(),
    )


# ---------------------------------------------------------------------------
# B. Exit codes per D13
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "argv", [[], ["--no-such-flag", "x.zarr"]], ids=["no store", "unknown flag"]
)
def test_a_usage_error_exits_three_and_not_argparses_two(argv, capsys):
    """A command line the parser refuses exits `CONFIG_INVALID`.

    Expected value determined independently: D13 -- *"3 (usage, as
    `_Parser.error` already maps)"* -- and argparse's own code is 2.

    Bug this catches: a bare `ArgumentParser`, whose 2 means *aborted early,
    resumable* in this project's table, so a script would wait to resume a
    report that never started.
    """
    assert _exit(argv) == ExitCode.CONFIG_INVALID
    assert "usage:" in capsys.readouterr().err


def _no_schema_store(tmp_path: Path) -> Path:
    store = tmp_path / "foreign.zarr"
    zarr.open_group(str(store), mode="w").attrs["something"] = "else"
    return store


def _future_schema_store(finished_store: Path, tmp_path: Path) -> Path:
    store = _copy(finished_store, tmp_path, "future.zarr")
    root = zarr.open_group(str(store), mode="r+")
    root.attrs["schema_version"] = 999
    zarr.consolidate_metadata(str(store))
    return store


@pytest.mark.parametrize(
    ("make", "named"),
    [
        (lambda fs, tmp: tmp / "absent.zarr", "absent.zarr"),
        (lambda fs, tmp: _no_schema_store(tmp), "schema_version"),
        (_future_schema_store, "999"),
    ],
    ids=["no such path", "zarr but not metamer", "unknown schema_version"],
)
def test_an_unreadable_store_exits_four_names_why_and_leaves_nothing(
    finished_store, tmp_path, capsys, make, named
):
    """Every reader refusal is `DATA_INVALID`, with its reason and no traceback.

    Expected value determined independently: D13's table -- *"4 (the store is
    unreadable, is not a metamer store, or carries an unknown
    `schema_version`)"* -- one parametrized case per clause.

    Bug this catches: a refusal escaping as `INTERNAL_ERROR`, which tells a
    script the report is broken when the input is; and a default output
    directory created for the writability check and left behind beside a store
    the report never read.
    """
    store = make(finished_store, tmp_path)

    assert _exit([str(store)]) == ExitCode.DATA_INVALID

    err = capsys.readouterr().err
    assert named in err
    assert "Traceback" not in err
    assert not _default_out(store).exists()


def test_the_reports_four_is_the_batch_runs_code_for_the_same_refusal(tmp_path):
    """One refusal, one code: the report agrees with `exit_code_for`.

    Expected value determined independently: `exit_code_for` is the batch
    run's published mapping, and the reader raises the same exception type.

    Bug this catches: the report carrying its own mapping (it must -- the
    validator is behind the boundary) and that mapping drifting from the batch
    run's, so one store gives two codes depending on which command read it.
    """
    from metamer.batch.validation import exit_code_for

    assert _exit([str(tmp_path / "absent.zarr")]) == exit_code_for(
        InputContractError("x")
    )


def test_a_crash_inside_a_section_exits_five_with_its_traceback(
    finished_store, tmp_path, monkeypatch, capsys
):
    """An unexpected exception is `INTERNAL_ERROR`, and the traceback is kept.

    Expected value determined independently: D13 -- 5 is producible -- and
    CPython's own code for an unhandled exception is 1.

    Bug this catches: no catch-all, so a crash exits 1, which means *completed
    with failures above threshold* -- a fact about a run, reported for a report
    that did not finish. And a catch-all that swallows the traceback, which
    leaves the defect undiagnosable.
    """
    import metamer.report.selectability as selectability

    def planted(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("planted inside a section")

    monkeypatch.setattr(selectability, "compute", planted)

    assert _exit([str(_copy(finished_store, tmp_path))]) == ExitCode.INTERNAL_ERROR
    err = capsys.readouterr().err
    assert "Traceback" in err
    assert "planted inside a section" in err


def test_the_entry_point_never_names_the_two_codes_a_report_cannot_produce():
    """1 and 2 describe runs; the entry point's source names neither.

    Expected value determined independently: D13 -- *"1 is ... a property of a
    run, and the report is not a run; 2 is aborted early, resumable, and a
    report is not resumable."*

    Bug this catches: a report that exits 1 because the store it describes
    recorded failures above threshold -- the report's code describing the run,
    which D13's rule forbids. Structural, because no fixture can enumerate
    every store a later edit might special-case.
    """
    named = {
        node.attr
        for node in ast.walk(ast.parse(MAIN.read_text()))
        if isinstance(node, ast.Attribute)
    }
    assert not named & {"COMPLETED_WITH_FAILURES", "ABORTED_EARLY"}


def _spy_on_the_null(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Count calls to the section that runs the permutation null."""
    import metamer.report.clustering as clustering

    calls: list[int] = []
    real = clustering.compute

    def counting(*args: Any, **kwargs: Any) -> Any:
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(clustering, "compute", counting)
    return calls


def _refuses_writes(directory: Path) -> None:
    """Fixture precondition: a write into `directory` must actually fail.

    **A precondition that refuses to run beats an assertion that passes** -- as
    root, permission bits are ignored and every "unwritable" test below would
    pass while testing nothing.
    """
    try:
        (directory / ".precondition").write_text("x")
    except PermissionError:
        return
    (directory / ".precondition").unlink()
    pytest.fail(f"{directory} accepted a write; this test cannot run as root")


def test_an_unwritable_output_fails_before_the_permutation_null_runs(
    finished_store, tmp_path, monkeypatch, capsys
):
    """Writability is checked first: exit 3 and ZERO calls to the null.

    Expected value determined independently: the plan -- *"Writability is
    checked up front, before the permutation null runs"* -- and the
    pre-flight's order, arguments then writability then everything else.

    Bug this catches: a report that computes for minutes and then cannot save,
    the one failure that wastes the user's time entirely.
    """
    out = tmp_path / "locked"
    out.mkdir()
    out.chmod(0o500)
    try:
        _refuses_writes(out)
        calls = _spy_on_the_null(monkeypatch)
        code = _exit([str(_copy(finished_store, tmp_path)), "--out", str(out)])
    finally:
        out.chmod(0o700)

    assert code == ExitCode.CONFIG_INVALID
    assert calls == []
    assert str(out) in capsys.readouterr().err


def test_the_spy_sees_the_null_when_the_output_is_writable(
    finished_store, tmp_path, monkeypatch
):
    """Control for the test above: the same spy counts exactly one call.

    Bug this catches: a spy installed somewhere the entry point never looks,
    under which "zero calls" holds whatever the order is.
    """
    calls = _spy_on_the_null(monkeypatch)
    code = _exit(
        [str(_copy(finished_store, tmp_path)), "--out", str(tmp_path / "free")]
    )
    assert code == ExitCode.OK
    assert calls == [1]


def test_an_output_inside_the_store_is_refused_and_the_store_untouched(
    finished_store, tmp_path, capsys
):
    """`--out` resolving inside the store exits 3 and writes nothing there.

    Expected value determined independently: the plan's invariant -- *"No write
    to the store"* -- which an output directory inside it would break by
    construction.

    Bug this catches: the read-only guarantee holding for the default path and
    failing for a caller-supplied one.
    """
    store = _copy(finished_store, tmp_path)
    before = _snapshot(store)

    assert _exit([str(store), "--out", str(store / "report")]) == (
        ExitCode.CONFIG_INVALID
    )
    assert _snapshot(store) == before
    assert "inside the store" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# C. The store is read, never written, and the output sits beside it
# ---------------------------------------------------------------------------


def test_the_default_output_is_beside_the_store_and_never_inside_it(reported):
    """The report writes to `<parent>/<store name>.report/`.

    Expected value determined independently: the pre-flight's definition of
    "beside", written before the code because the first draft of a default
    path is where "next to it" becomes "in it".

    Bug this catches: output written into the store directory, which the
    permission test below would turn into a failure on every read-only store.
    """
    out, _record, _markdown = reported
    assert out.name == "out.zarr.report"
    assert (out / "report.json").is_file()
    assert (out / "report.md").is_file()
    assert not (out.parent / "out.zarr" / "report.json").exists()


def test_the_full_report_runs_on_a_store_that_refuses_every_write(
    finished_store, tmp_path
):
    """Write permission removed from the whole store, and the report exits 0.

    Expected value determined independently: the plan's first Task 8 test --
    *"A store that raises on any write catches all of them, on every path"*.

    Bug this catches: any write to the store on any path -- an attrs rewrite
    of identical content, a re-consolidation, a sibling file -- which a byte
    comparison misses and a read-only filesystem does not.
    """
    store = _copy(finished_store, tmp_path)
    modes = {path: path.stat().st_mode for path in [store, *store.rglob("*")]}
    for path in modes:
        path.chmod(0o555 if path.is_dir() else 0o444)
    try:
        _refuses_writes(store)
        code = _exit([str(store)])
    finally:
        for path, mode in modes.items():
            path.chmod(mode)

    assert code == ExitCode.OK
    assert (_default_out(store) / "report.json").is_file()


def test_the_store_is_byte_for_byte_identical_and_the_report_was_written(
    finished_store, tmp_path
):
    """The cheap positive control for the permission test.

    Expected value determined independently: hashing every file before and
    after; the report's own output proves it ran.

    Bug this catches: a permission test that is green because the report did
    nothing at all.
    """
    store = _copy(finished_store, tmp_path)
    before = _snapshot(store)

    assert _exit([str(store)]) == ExitCode.OK

    assert _snapshot(store) == before
    assert json.loads((_default_out(store) / "report.json").read_text())


def test_an_unfinished_store_is_described_with_its_tile_count(finished_store, tmp_path):
    """D6: an unfinished store exits 0 and the markdown says how unfinished.

    Expected value determined independently: clearing one bit of a finished
    fixture leaves `total - 1` of `total` tiles complete.

    Bug this catches: the report refusing the store D6 exists for, or
    describing it without saying that its statistic's scope narrowed.
    """
    from metamer.report.render import _number

    store = _copy(finished_store, tmp_path)
    tiles = zarr.open_group(str(store), mode="r+")["completion/tiles"]
    assert isinstance(tiles, zarr.Array)
    total = int(np.asarray(tiles[:]).size)
    tiles[0, 0] = 0

    assert _exit([str(store)]) == ExitCode.OK

    markdown = (_default_out(store) / "report.md").read_text()
    assert f"{_number(total - 1)} of {_number(total)} tiles" in markdown
    assert "given what was fitted" in markdown


# ---------------------------------------------------------------------------
# D. Render-from-record: the structure, then the backstop
# ---------------------------------------------------------------------------

#: The standard-library modules the renderer may import: none does arithmetic.
RENDER_ALLOWED = {"__future__", "collections.abc", "typing"}


def test_the_renderer_imports_nothing_that_can_compute():
    """`render.py` imports only from an arithmetic-free allowlist.

    Expected value determined independently: the pre-flight's §2 and §6 -- no
    numpy, no `metamer.*`, none of `math`, `operator`, `statistics`,
    `fractions`, `decimal`.

    Bug this catches: a renderer that imports a section module or numpy and
    recomputes a number at render time, which is how two artifacts of one run
    come to disagree.
    """
    assert _imported_modules(RENDER) <= RENDER_ALLOWED


def _enclosing_functions(tree: ast.AST) -> dict[ast.AST, str]:
    owner: dict[ast.AST, str] = {}
    for function in ast.walk(tree):
        if isinstance(function, ast.FunctionDef):
            for node in ast.walk(function):
                owner.setdefault(node, function.name)
    return owner


def test_the_renderer_formats_numbers_in_one_place_and_divides_nowhere():
    """Every format spec lives in `_number`; no `divmod`, `pow`, `%` or `.format`.

    Expected value determined independently: the pre-flight's §2 -- *"a format
    spec is arithmetic the division count cannot see"* -- and §6's closing of
    the third gap inside the renderer.

    Bug this catches: `f"{rate:.1%}"` multiplying by 100 outside the formatter,
    invisible to the golden table; and a `divmod` or `pow(x, -1)` computing a
    rate as a call, which the table cannot see anywhere.
    """
    tree = ast.parse(RENDER.read_text())
    owner = _enclosing_functions(tree)
    offences: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in {"divmod", "pow", "format"}:
            if not (node.id == "format" and owner.get(node) == "_number"):
                offences.append(f"line {node.lineno}: {node.id}")
        if isinstance(node, ast.FormattedValue) and owner.get(node) != "_number":
            if node.format_spec is not None or node.conversion not in (-1, 115):
                offences.append(f"line {node.lineno}: a format spec outside _number")
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
            offences.append(f"line {node.lineno}: %")
        if isinstance(node, ast.Attribute) and node.attr == "format":
            offences.append(f"line {node.lineno}: .format")
    assert offences == []


def test_the_markdown_is_the_render_of_the_saved_record(reported):
    """`report.md` equals `render` applied to the parsed `report.json`.

    Expected value determined independently: the structure the pre-flight
    fixes -- the renderer's only input is the record as written -- so the two
    must agree byte for byte.

    Bug this catches: the entry point rendering from the in-memory sections,
    which carry precision and fields the saved artifact does not, so the
    markdown and the JSON of one run disagree.
    """
    from metamer.report.render import render

    out, record, markdown = reported
    assert markdown == render(json.loads((out / "report.json").read_text()))
    assert record  # the saved record is not empty


_NUMBER = re.compile(r"-?\d+(?:\.\d+)?(?:e[+-]?\d+)?")


def _tokens(text: str) -> set[str]:
    return set(_NUMBER.findall(text))


def _record_tokens(value: Any) -> set[str]:
    """Every numeric token the record can legitimately put in the markdown.

    Numbers pass through the renderer's own formatter -- the same function the
    renderer uses, so `0.6` and `0.60` cannot fail for the wrong reason -- and
    strings (keys included) contribute the digits they already contain.
    """
    from metamer.report.render import _number

    if isinstance(value, dict):
        found = set()
        for key, item in value.items():
            found |= _tokens(str(key)) | _record_tokens(item)
        return found
    if isinstance(value, list):
        return set().union(*(_record_tokens(item) for item in value))
    if isinstance(value, bool) or value is None:
        return set()
    if isinstance(value, int | float):
        return _tokens(_number(value))
    return _tokens(str(value))


def _unsourced(markdown: str, record: dict[str, Any]) -> set[str]:
    return _tokens(markdown) - _record_tokens(record)


def test_every_number_in_the_markdown_is_in_the_record(reported):
    """The backstop: no numeric token in the markdown is absent from the record.

    Expected value determined independently: exit criterion 23's reading.

    Bug this catches: a number computed at render time. **ITS WEAKNESS, WRITTEN
    BESIDE IT AS THE PRE-FLIGHT RULES:** this is set membership, so a rendered
    number that happens to equal a DIFFERENT field in the record passes. Only
    the structure above -- the renderer's input is the saved record, and it
    cannot compute -- rules that out.
    """
    _out, record, markdown = reported
    assert _unsourced(markdown, record) == set()


def test_the_backstop_catches_a_planted_number(reported):
    """Control: a number that is not in the record is reported by the same check.

    Bug this catches: a checker that cannot fail -- for example a regex that
    never matches, under which the test above is green on any markdown.
    """
    _out, record, markdown = reported
    assert "31337" not in _record_tokens(record)
    assert _unsourced(markdown + "\n| planted | 31337 |\n", record) == {"31337"}


def test_every_rate_travels_with_its_population(reported):
    """D6: each rate is rendered beside exactly the two counts it divides.

    Expected value determined independently: `FailureTally`'s definitions --
    `rate` is `failed / fitted` and `coverage_rate` is `failed / covered` -- so
    each rate's text must carry its numerator and its denominator, in the form
    the renderer's docstring publishes.

    Bug this catches: a rate quoted without its population, the reading D6
    makes the record's job to prevent. **Not the two denominators swapped**:
    every candidate in this fixture has `covered == fitted`, so the next test
    makes them differ.
    """
    from metamer.report.render import _number

    _out, record, markdown = reported
    tallies = [row["tally"] for row in record["numbers"]["by_candidate"]]
    tallies.append(record["numbers"]["aggregate"])
    rated = [tally for tally in tallies if tally["rate"] is not None]
    assert rated, "the fixture has rated candidates; a vacuous loop proves nothing"
    for tally in rated:
        failed = _number(tally["failed"])
        assert (
            f"{_number(tally['rate'])} ({failed} of {_number(tally['fitted'])} fitted)"
            in markdown
        )
        assert (
            f"coverage {_number(tally['coverage_rate'])} ({failed} of "
            f"{_number(tally['covered'])} covered)"
        ) in markdown


def _with_aggregate(record: dict[str, Any], **tally: Any) -> dict[str, Any]:
    """The real record with its aggregate tally replaced, every other field kept."""
    changed = json.loads(json.dumps(record))
    changed["numbers"]["aggregate"] = {
        **changed["numbers"]["aggregate"],
        "covered_not_fitted": {},
        **tally,
    }
    return changed


def test_a_rate_is_printed_beside_its_own_denominator_when_the_two_differ(reported):
    """`fitted` and `covered` are different populations, and each rate names its own.

    Expected value determined independently, by hand: 2 failures over 5 fitted
    is 0.4, over 8 covered is 0.25.

    Bug this catches: the two denominators swapped. **The real fixture cannot
    catch it** -- every candidate there has `covered == fitted` -- which a
    mutant swapping them showed: the test above passed it, 2026-10-23. So the
    populations are made to differ here, in an otherwise real record.
    """
    from metamer.report.render import render

    _out, record, _markdown = reported
    markdown = render(
        _with_aggregate(
            record, failed=2, fitted=5, covered=8, rate=0.4, coverage_rate=0.25
        )
    )
    assert "0.4 (2 of 5 fitted); coverage 0.25 (2 of 8 covered)" in markdown


def test_an_absent_rate_is_never_printed_as_zero(reported):
    """No fits, no rate -- and the reason, never `0`.

    Expected value determined independently: `FailureTally`'s contract --
    *"Never a rate of 0.0 for a candidate that was never tried"*.

    Bug this catches: a renderer that formats `None` as a number, so a
    candidate nobody fitted reads identically to one fitted everywhere and
    passing.
    """
    from metamer.report.render import render

    _out, record, _markdown = reported
    markdown = render(
        _with_aggregate(
            record,
            failed=0,
            fitted=0,
            rate=None,
            coverage_rate=None,
            unavailable="planted: nothing was fitted",
        )
    )
    (line,) = [
        text
        for text in markdown.splitlines()
        if text.startswith("- **any candidate, per point**")
    ]
    assert line.endswith("no rate: planted: nothing was fitted")


def test_the_populated_forms_of_every_section_render_from_their_real_types(reported):
    """An available statistic, a judged candidate and an unmapped branch all render.

    Expected value determined independently: each section's populated form is
    built from its REAL dataclass (`Arrangement`, `DropRow`) with values chosen
    by hand, so a field the renderer reads must exist on the type -- and the
    backstop must still find every rendered number in the record.

    Bug this catches: a renderer that reads a field the real type does not
    have. **The real fixture cannot see it**: its 9 eligible points are below
    the statistic's 500-point floor, its store carries no early-abort record,
    and every branch present has a population -- measured by coverage on
    2026-10-23, `render.py`'s available-statistic line had never run. That
    `KeyError` would exit 5 on exactly the stores large enough to have a
    statistic.
    """
    from metamer.report.clustering import Arrangement
    from metamer.report.drop import DropRow
    from metamer.report.record import _plain
    from metamer.report.render import render

    _out, record, _markdown = reported
    changed = json.loads(json.dumps(record))
    arm = changed["clustering"][changed["clustering"]["reported"]]
    arm["aggregate"] = _plain(
        Arrangement(
            available=True,
            reason=None,
            edges=24,
            eligible=16,
            failures=5,
            observed=3,
            null_median=1.5,
            null_q95=4.0,
            z=1.25,
            p=0.125,
            permutations=999,
            seed=7,
        )
    )
    changed["early_abort"]["rows"] = [
        _plain(
            DropRow(
                candidate="planted-candidate",
                failed=3,
                live=10,
                denominator="fitted",
                eligible=12,
                fitted=10,
                rate=0.3,
                dropped=True,
                provenance="recomputed from the pass-one store",
                defects=(),
            )
        )
    ]
    changed["maps"]["unmapped"] = [
        {"branch": 9, "name": "planted_branch", "reason": "no population"}
    ]

    markdown = render(changed)

    assert "| 3 | 1.5 | 1.25 | 0.125 |" in markdown
    assert "5 failures among 16 eligible; 999 permutations, seed 7" in markdown
    assert "| planted-candidate | 0.3 over fitted | 3 | 10 | yes |" in markdown
    assert "planted_branch: no map — no population" in markdown
    assert _unsourced(markdown, changed) == set()


def test_the_markdown_prints_the_arm_d4s_gate_reports(reported):
    """On a gate-global store the table is the wrapped arm, as the note says.

    Expected values determined by hand, on Task 6's seam-straddling grid
    (`test_report_clustering`): the arms differ by the patch's own 15 seam
    joins, 550 unwrapped and 565 wrapped, for the one candidate and for the
    aggregate alike. The record's span note says "global, wrapped".

    Bug this catches: a renderer that reads the unwrapped arm whatever the
    gate decided, which prints 550 beside a note saying the seam was wrapped
    -- a number contradicting the words beside it. **Printing both arms,
    labelled and with the reported one marked, is the next fix's**; this one
    only binds the table to the arm the record says it reports.
    """
    from metamer.report.clustering import compute
    from metamer.report.record import _plain
    from metamer.report.render import render
    from tests.test_report_clustering import _cube, _longitude

    rows, columns = 30, 360
    failed = np.zeros((rows, columns), dtype=bool)
    failed[5:20, 350:] = True
    failed[5:20, :10] = True
    _out, record, _markdown = reported
    changed = json.loads(json.dumps(record))
    changed["clustering"] = _plain(
        compute(_longitude(_cube(failed), np.arange(columns, dtype=np.float64)))
    )

    lines = render(changed).splitlines()
    label = changed["clustering"]["headline_label"]

    assert [line.split(" | ")[1] for line in lines if line.startswith("| m0 |")] == [
        "565"
    ]
    assert [
        line.split(" | ")[1] for line in lines if line.startswith(f"| {label} |")
    ] == ["565"]
    assert "Domain span: 360° of 360°, global, wrapped." in lines


def test_the_record_refuses_what_json_cannot_carry_faithfully():
    """An array is refused; a numpy scalar and a path become JSON's own types.

    Expected value determined independently: the record module's contract --
    *"it refuses what JSON cannot carry faithfully ... instead of stringifying
    it"* -- and JSON's types.

    Bug this catches: an array or an unknown object written as its `str()`,
    which `json.dumps(default=str)` would do silently and which no reader of
    `report.json` could turn back into the value; and a numpy integer written
    as a float or a string, so the markdown's token check and a downstream
    reader disagree about one number.
    """
    from metamer.report.record import _plain

    assert _plain({"n": np.int64(3), "where": Path("a/b")}) == {"n": 3, "where": "a/b"}
    assert type(_plain(np.int64(3))) is int
    with pytest.raises(TypeError, match="cannot carry a ndarray"):
        _plain({"field": np.zeros(2)})


# ---------------------------------------------------------------------------
# E. A foreign store, no config
# ---------------------------------------------------------------------------


def test_the_report_runs_on_another_processs_store_with_no_config(
    finished_store, tmp_path
):
    """`python -m metamer.report <store>` from an empty directory exits 0.

    Expected value determined independently: the plan's foreign-store property
    -- a user with a store and no config.

    Bug this catches: any dependence on a config file, the working directory,
    or state the parent process built.
    """
    store = _copy(finished_store, tmp_path)
    empty = tmp_path / "empty"
    empty.mkdir()
    result = subprocess.run(
        [sys.executable, "-m", "metamer.report", str(store)],
        cwd=empty,
        capture_output=True,
        text=True,
        env={"PYTHONPATH": str(SRC.parent), "PATH": "/usr/bin:/bin"},
        check=False,
    )
    assert result.returncode == ExitCode.OK, result.stderr
    assert (_default_out(store) / "report.json").is_file()
    assert list(empty.iterdir()) == []


# ---------------------------------------------------------------------------
# H. The maps, in both environments
# ---------------------------------------------------------------------------


def test_without_matplotlib_the_report_still_exits_zero_and_says_why(
    finished_store, tmp_path, monkeypatch
):
    """D10: no plotting stack, no PNGs, and the record names the extra.

    Expected value determined independently: `maps.REPORT_EXTRA` is the
    published name of the extra, and the plan's D10 keeps the numbers path
    usable where the store is readable.

    Bug this catches: the report failing on a machine without `[report]`, or
    skipping the maps silently.
    """
    import metamer.report.maps as maps

    monkeypatch.setattr(maps, "matplotlib_available", lambda: False)
    store = _copy(finished_store, tmp_path)

    assert _exit([str(store)]) == ExitCode.OK

    out = _default_out(store)
    record = json.loads((out / "report.json").read_text())
    assert record["maps"]["drawn"] is False
    assert record["maps"]["extra"] == maps.REPORT_EXTRA
    assert list(out.glob("*.png")) == []
    assert maps.REPORT_EXTRA in (out / "report.md").read_text()


@pytest.mark.skipif(
    not __import__("metamer.report.maps").report.maps.matplotlib_available(),
    reason="matplotlib absent: the [report] job runs this",
)
def test_with_matplotlib_every_drawn_map_is_beside_the_record(reported):
    """Each PNG the record names exists in the output directory, and only those.

    Expected value determined independently: the record's own `png` names.

    Bug this catches: maps drawn somewhere other than the output directory --
    into the store, say -- or drawn and not recorded.
    """
    out, record, _markdown = reported
    names = {entry["png"] for entry in record["maps"]["maps"]}
    assert names, "the fixture earns maps; a vacuous comparison proves nothing"
    assert {path.name for path in out.glob("*.png")} == names
