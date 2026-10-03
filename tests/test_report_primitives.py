"""Sub-phase 2f Task 4: the primitives sections, and what an older store cannot say.

**THE FILL VALUES ARE THE SUBJECT OF HALF THIS FILE.** `-1` and `65535` are
in-range integers that any histogram will bin happily, and a spike at either
reads as a real population -- a grid where 400 points "converged in 65535
iterations" or "had -1 valid samples". Excluding them alone is the other half
of the same defect: the report would then describe a smaller grid than the one
that ran.
"""

from __future__ import annotations

import ast
import pathlib
import textwrap
from typing import Any

import numpy as np
import pytest
import xarray as xr

from metamer.batch.run import run
from metamer.batch.store import ITERATIONS_UNSET, N_VALID_UNSET
from metamer.core.outcomes import Outcome
from metamer.report.primitives import NOT_RECORDED, compute
from metamer.report.reader import Completion, StoreView, read_store

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")

_CONFIG = """
data_uri = "{uri}"
variable = "sla"
signal_terms = ["constant", "trend"]
candidates = ["white", "white + matern12"]
criteria = ["aic"]
"""


#: The store's own flag attributes, as `reader._legend` returns them. These
#: helpers plant an outcome cube directly rather than opening a store, so the
#: legend is supplied the same way -- from `Outcome`, which is what the writer
#: builds it from.
_LEGEND = {member.code: str(member.value) for member in Outcome}


def _view(
    *,
    n_valid: list[int],
    iterations: list[int],
    attrs: dict[str, Any] | None = None,
) -> StoreView:
    """A view carrying planted primitive arrays and nothing else."""
    return StoreView(
        path=pathlib.Path("/nonexistent"),
        outcome=np.zeros((1, len(n_valid), 1), dtype=np.uint8),
        delta_ic=np.zeros((1, len(n_valid), 1, 1), dtype=np.float32),
        selected=np.zeros((1, len(n_valid), 1), dtype=np.int16),
        n_valid=np.array([n_valid], dtype=np.int16),
        iterations=np.array([iterations], dtype=np.uint16).reshape(
            1, len(iterations), 1
        ),
        model_labels=("only",),
        criterion_labels=("aic",),
        attrs=attrs if attrs is not None else {},
        completion=Completion(complete=1, total=1),
        spatial={},
        disagreements=(),
        legend=_LEGEND,
    )


def test_the_fill_values_are_counted_and_never_binned():
    """`-1` and `65535` are reported beside the distribution, not inside it.

    Expected values computed by hand from the literal arrays: `n_valid` holds
    [24, 24, 18, -1, -1], so the real population is 3 with `{24: 2, 18: 1}` and
    2 unset; `iterations` holds [7, 7, 7, 65535, 12], so the real population is
    4 with `{7: 3, 12: 1}` and 1 unset.

    Bug this catches: a histogram with a spike at the fill value, which reads
    as a real population -- **"two points had -1 valid samples" and "one point
    converged in 65535 iterations"** are both nonsense a reader would
    otherwise have to know to discount. And the other direction: silently
    dropping them, which makes the report describe a smaller grid than the one
    that ran, so the counts are asserted too.
    """
    sections = compute(
        _view(n_valid=[24, 24, 18, -1, -1], iterations=[7, 7, 7, 65535, 12])
    )

    assert sections.n_valid.counts == {24: 2, 18: 1}
    assert sections.n_valid.unset == 2
    assert sections.n_valid.population == 3
    assert sections.iterations.counts == {7: 3, 12: 1}
    assert sections.iterations.unset == 1
    assert sections.iterations.population == 4


def test_an_all_unset_array_reports_an_empty_distribution_and_its_size():
    """A store where nothing wrote reports nothing, and says how much nothing.

    Expected values determined independently: five cells, all fill, so the
    distribution is empty and the unset count is five.

    Bug this catches: a population of zero rendered as a distribution over
    nothing, from which a reader cannot tell "no fit ran anywhere" from "this
    section is broken". **An empty table and an empty table with `unset = 5`
    beside it are different statements**, which is (a2b)'s rule: unavailable
    with a reason beats a plausible blank.
    """
    sections = compute(
        _view(
            n_valid=[N_VALID_UNSET] * 5,
            iterations=[ITERATIONS_UNSET] * 5,
        )
    )

    assert sections.n_valid.counts == {}
    assert sections.n_valid.unset == 5
    assert sections.n_valid.population == 0
    assert sections.iterations.counts == {}
    assert sections.iterations.unset == 5


def test_a_store_without_the_block_says_so_and_still_renders_everything_else():
    """Absence is the answer, and it does not take the rest of the section down.

    Expected value determined independently: a store written before 2f Task 4
    carries no `resolved_candidates` key at all, and D12 refuses a back-fill --
    a guessed block would make an old store claim a resolution nobody recorded.

    Bug this catches: **a report that requires the newest writer**, which
    breaks the foreign-store property section 14.2 exists for. The distributions
    and the hashes come from arrays and attrs an old store has, so they must
    still render; only the block's own line says it is missing.
    """
    sections = compute(
        _view(
            n_valid=[24, 24],
            iterations=[5, 6],
            attrs={"fit_hash": "abc", "registry_version": "3"},
        )
    )

    assert sections.resolved_candidates is None
    assert sections.resolved_at == NOT_RECORDED
    assert sections.n_valid.counts == {24: 2}
    assert sections.iterations.counts == {5: 1, 6: 1}
    assert sections.hashes["fit_hash"] == "abc"
    assert sections.hashes["compat_hash"] == NOT_RECORDED
    assert sections.registry_version == "3"


def test_a_real_store_carries_the_block_and_its_rows_match_the_axis():
    """The end-to-end arm: a run's own store, read back through the reader.

    Expected value determined independently: the config names two candidates,
    so the block carries two rows and the store's `m` axis two labels, and the
    rows' labels are those labels.

    Bug this catches: a block written in a different order from the `m` axis,
    or over a different candidate set -- which would make every per-candidate
    row in the report describe the wrong column. **The constructed views above
    cannot catch it**, because they plant both sides themselves.
    """
    sections = compute(read_store(_real.path))
    view = read_store(_real.path)

    assert sections.resolved_candidates is not None
    assert [row["label"] for row in sections.resolved_candidates] == list(
        view.model_labels
    )
    assert sections.resolved_at.startswith("run start, against registry version ")
    assert sections.hashes["fit_hash"] != NOT_RECORDED


class _Real:
    path: pathlib.Path


_real = _Real()


@pytest.fixture(scope="module", autouse=True)
def _build(tmp_path_factory: pytest.TempPathFactory) -> None:
    """One real store, built once for the end-to-end arm."""
    base = tmp_path_factory.mktemp("primitives")
    origin = np.datetime64("2000-01-01")
    times = np.array([origin + np.timedelta64(31 * i, "D") for i in range(24)])
    xr.Dataset(
        {"sla": (("time", "y", "x"), np.zeros((24, 4, 4), dtype="float32"))},
        coords={"time": times, "y": np.arange(4), "x": np.arange(4)},
    ).to_zarr(base / "in.zarr")
    config = base / "c.toml"
    config.write_text(textwrap.dedent(_CONFIG.format(uri=base / "in.zarr")))
    store = base / "out.zarr"
    run(config, store)
    _real.path = store


def test_the_report_reads_the_sentinels_from_their_one_definition():
    """The fill values are imported, not re-spelled.

    Expected values determined independently from `batch.store`, which owns
    them: `-1` for `n_valid` and `65535` for `iterations`.

    Bug this catches: a second copy of either constant in the report. A
    sentinel written twice is the two-definitions defect on a value whose whole
    job is to be recognised -- and the day one moves, a report holding the old
    number bins the fill value as data and reports it as a population.
    """
    assert N_VALID_UNSET == -1
    assert ITERATIONS_UNSET == 65535
    # **THE SUBJECT IS THE CODE, NOT THE FILE.** The module docstring names
    # both values in prose, and prose is documentation rather than a second
    # definition -- a grep over the text cannot tell them apart and would have
    # to be loosened, which is the trap a check that fails for the wrong reason
    # always ends in. The `ast` sees numeric literals only.
    tree = ast.parse(
        (
            pathlib.Path(__file__).resolve().parents[1]
            / "src"
            / "metamer"
            / "report"
            / "primitives.py"
        ).read_text()
    )
    literals = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, int)
    }

    assert ITERATIONS_UNSET not in literals, "the sentinel is re-spelled in the report"
    assert N_VALID_UNSET not in literals, "the sentinel is re-spelled in the report"
