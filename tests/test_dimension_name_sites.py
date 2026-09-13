"""The one machine-readable home for "how name-dependent is the input path?".

**THIS FILE EXISTS BECAUSE THE NUMBER LIVED IN PROSE AND DRIFTED.** Eight
documents stated how many places `tiling.py` requires the spatial dimensions to
be literally `y` and `x`. All eight said *four*; the tree has said *six, in
three functions* since before any of them was written. The correction was made
once, in `realdata-spike-preflight.md` on 2026-09-07, and **five other sites
still said four five days later** -- a correction recorded only where it was
found is not a correction, it is a second version of the claim.

So the count is asserted here, against the file, and every prose mention is a
pointer rather than a copy.

**WHAT COUNTS AS A SITE.** A literal use of a spatial dimension NAME to address
an INPUT array: the string constants `"y"` / `"x"`, and the keyword arguments
`y=` / `x=` in a call. `"time"` is deliberately NOT a site -- `time`-first is
the stage-4a contract (`input.py`), it is enforced, and it is never going
away. Counting it would inflate the number today and, once the tiling path goes
positional, would make this file fail for a reason that is not a defect.

**WHAT IS DELIBERATELY OUT OF SCOPE.** `store.py` and `reuse.py` use `("y",
"x")` throughout, and neither is a site: those are the dimension names of the
OUTPUT store, which is this project's own product naming its own axes. They are
not claims about anybody's input. Including them would make this file assert
that metamer may not name its own schema.
"""

from __future__ import annotations

import ast
from pathlib import Path

import metamer.batch.decimate
import metamer.batch.tiling

#: The input-array spatial dimension names this project's fixtures happen to use,
#: and which the stage-4a contract does NOT require.
SPATIAL_NAMES = frozenset({"y", "x"})


def dimension_name_sites(source: str) -> dict[str, int]:
    """Count literal spatial-dimension-name uses, per enclosing function.

    Args:
        source: Python source text.

    Returns:
        Function name to the number of sites inside it. Functions with no site
        are absent, so an empty mapping means a fully positional module.
    """
    tree = ast.parse(source)
    counts: dict[str, int] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        found = 0
        for inner in ast.walk(node):
            if isinstance(inner, ast.Constant) and inner.value in SPATIAL_NAMES:
                found += 1
            elif isinstance(inner, ast.keyword) and inner.arg in SPATIAL_NAMES:
                found += 1
        if found:
            counts[node.name] = found
    return counts


def _source_of(module: object) -> str:
    """Read a module's own source text from disk.

    Args:
        module: An imported module.

    Returns:
        Its source.
    """
    return Path(module.__file__).read_text(encoding="utf-8")  # type: ignore[attr-defined]


def test_the_tiling_path_is_name_dependent_in_three_functions_and_six_places():
    """The enumeration eight documents cite, asserted against the file.

    Expected values determined independently: read off `tiling.py` by hand at
    lines 904-905 (`read_amplification`'s span tuples), 932-933
    (`assembly_spans`' `by_dim` lookups) and 974-975 (`assemble_tile`'s own
    `isel` keywords) -- and cross-checked against `realdata-spike-preflight.md`,
    which arrived at the same six by a separate reading on 2026-09-07.

    Bug this catches: a fourth name-dependent site added to the tiling path, or
    one removed, while every prose statement of the figure goes on saying six.
    That drift has already happened twice by hand, in opposite directions -- the
    count said four against an enumeration of three, and a line citation aged by
    one -- which is why the number now has exactly one home.

    **Enumerated by FUNCTION, never by line.** The by-line form has drifted the
    record twice; the by-function form never has.

    **This assertion is expected to become `{}` when the tiling path goes
    positional, and that change is the deliverable, not a break.**

    **PROVED TO BITE 2026-09-12, BEFORE BEING RECORDED AS A GUARD** -- (e2)'s
    converse. Two constructed mutants of `tiling.py`'s source, neither applied
    to the tree: a fourth name-dependent function appended gives
    `{..., '_fifth_site': 2}`, and `assembly_spans` made positional drops its
    key entirely. Both differ from the baseline, so this test fails in each
    direction rather than only in the one that is easy to imagine.
    """
    assert dimension_name_sites(_source_of(metamer.batch.tiling)) == {
        "read_amplification": 2,
        "assembly_spans": 2,
        "assemble_tile": 2,
    }


def test_the_enumerator_reads_the_source_it_is_given():
    """The count varies with the text, so it is a reading and not a constant.

    Expected values determined independently: counted by hand off the
    constructed source below -- one keyword site in `f`, and in `g` two string
    constants plus one keyword.

    Bug this catches: an enumerator that returns a hard-coded mapping, or that
    returns `{}` whenever its walk matches nothing. **Either makes the test
    above pass against any tree at all** -- a check that never read the file
    prints the same word as one that did. Without this test, the guard that the
    whole file exists to provide is unfalsifiable.
    """
    source = (
        "def f(a):\n"
        "    return a.isel(y=0)\n"
        "\n"
        "def g(a, by_dim):\n"
        '    return a.isel(x=by_dim["y"]), by_dim["x"]\n'
    )

    assert dimension_name_sites(source) == {"f": 1, "g": 3}


def test_the_time_axis_is_not_a_site():
    """`time` is contract-mandated and is excluded by construction.

    Expected value determined independently: the constructed source addresses
    only `time`, which the stage-4a contract requires by name, so by the
    definition in this module's docstring it contains no site.

    Bug this catches: an enumerator that counts every string-keyed dimension
    lookup. `tiling.py` reads `sizes["time"]` and `by_dim["time"]`, so such an
    enumerator would report eight sites rather than six today -- and once the
    spatial names go positional it would report two rather than zero, failing
    for a reason that is not a defect and sending the next reader to remove a
    contract the project enforces on purpose.
    """
    source = 'def f(sizes, by_dim):\n    return sizes["time"] * by_dim["time"]\n'

    assert dimension_name_sites(source) == {}


def test_the_decimation_is_positional_and_stays_positional():
    """`decimate.py` reads `dims[1]` and `dims[2]`, and nothing may undo that.

    Expected value determined independently: from the module's design rather
    than its current body -- its docstring states that it takes the spatial
    dimensions positionally specifically so as not to become another
    name-dependent site, which means zero.

    Bug this catches: `array.dims[1]` being rewritten to `"y"` as "consistent
    with the existing convention" -- the exact near-miss recorded in the
    phase-1-to-phase-2 handoff, where a pre-flight entry claiming the path was
    already positional would have licensed precisely that edit. Until now the
    only thing preventing it was a paragraph asking nicely.
    """
    assert dimension_name_sites(_source_of(metamer.batch.decimate)) == {}
