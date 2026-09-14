"""The one machine-readable home for "how name-dependent is the input path?".

**THIS FILE EXISTS BECAUSE THE NUMBER LIVED IN PROSE AND DRIFTED.** Eight
documents stated how many places `tiling.py` required the spatial dimensions to
be literally `y` and `x`. All eight said *four*; the tree had said *six, in
three functions* since before any of them was written. **The count is now ZERO
-- 2e's Task 2 made the path positional -- and this file is what keeps it
there.** The correction was made
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


def test_the_tiling_path_addresses_its_spatial_axes_by_position():
    """Zero sites. The defect that eight documents described is closed.

    **RENAMED, NOT EDITED, AT 2e's TASK 2 (2026-09-12.)** It was
    `test_the_tiling_path_is_name_dependent_in_three_functions_and_six_places`
    and asserted `{"read_amplification": 2, "assembly_spans": 2,
    "assemble_tile": 2}` -- six occurrences at lines 904-905, 932-933 and
    974-975, hand-counted and cross-checked against `realdata-spike-preflight.md`,
    which reached the same six by a separate reading on 2026-09-07. **A count in
    a test's NAME is the same hazard as a count in prose**, so the rename is the
    record of the change rather than a silent edit of the expected value.

    Expected value determined independently: from the contract. Stage 4a
    requires three dimensions with `time` first and says nothing about the other
    two names -- its own message calls the contract *"three, mapping to (time,
    y, x)"* -- so the correct number of literal spatial-name sites downstream of
    it is zero, and was zero before anybody counted.

    Bug this catches: a name-based site reintroduced into the tiling path, which
    would restore a defect that took two documents' worth of correcting to
    describe accurately and which fails only on inputs no fixture in this
    project had until 2e.

    **The `time` lookups are deliberately still here and are not sites.**
    `time`-first is the contract, `input.py` enforces it, and this module's
    docstring excludes it by construction -- so this assertion does not go to
    zero by counting less.
    """
    assert dimension_name_sites(_source_of(metamer.batch.tiling)) == {}


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
