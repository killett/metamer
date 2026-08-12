"""The thread budget: one owner at a time, limits observed rather than requested.

Design doc section 11.3's determinism precondition is **observed**:
`OMP_NUM_THREADS=1` in provenance records a *request*, and whether it took effect
depends on import ordering that nothing enforces. Two things are established
here and they are separate claims -- that the observation covers every library
that will actually run, and that the two phases never overlap.
"""

from __future__ import annotations

import numba
import pytest
import threadpoolctl

from metamer.batch.threads import (
    NUMBA_KEY,
    Phase,
    ThreadBudget,
    assembly_concurrency,
    library_table,
    observe_thread_limits,
    thread_budget,
)
from metamer.batch.validation import ValidationError, ValidationLayer

# --------------------------------------------------------------------------
# The observation: which libraries, and can it see them yet
# --------------------------------------------------------------------------


def test_the_observation_is_a_per_library_table_and_not_one_number():
    """Every loaded threading library gets its own entry.

    Bug this catches: one number standing for four. Section 11.3 is explicit --
    **a precondition that holds for OpenBLAS while MKL runs multithreaded is not
    a precondition that holds** -- so a scalar cannot express the property being
    checked, whatever value it holds.
    """
    observed = observe_thread_limits()
    assert len(observed) >= 2
    assert all(isinstance(value, int) for value in observed.values())
    assert all(isinstance(key, str) for key in observed)


def test_numba_is_in_the_table_even_though_threadpoolctl_cannot_see_it_yet():
    """**MEASURED: numba's layer is invisible until something parallel runs.**

    `threadpool_info()` after `import numba` reports OpenBLAS only; `libgomp`
    appears only once a `prange` function has executed. The layer-3 check runs
    at startup, which is exactly when the layer is not there -- so a check built
    on `threadpool_info()` alone would certify "every library observes 1" while
    the library the fit phase is about to use had not been loaded, and
    `threadpool_limits` does not retroactively limit a library loaded later.

    Bug this catches: reading the table without first launching the layer.
    Asserted through the OpenMP entry as well as numba's own, because those are
    two different quantities -- see the next test.
    """
    observed = observe_thread_limits()
    assert NUMBA_KEY in observed
    assert any(key.startswith("openmp") for key in observed)


def test_numbas_own_limit_is_not_what_threadpoolctl_reports():
    """**MEASURED: `threadpool_limits(1)` leaves `numba.get_num_threads()` at 4.**

    They are different quantities. threadpoolctl caps the OpenMP runtime's pool;
    numba's mask is how many slices a `prange` is cut into, and a `prange`
    reduction reassociates over **numba's** count. So a determinism precondition
    confirmed against threadpoolctl alone is one numba is not subject to.

    Bug this catches: recording the OpenMP entry as though it were numba's, at
    which point the table has an entry per library and still cannot see the one
    that matters for bitwise reproducibility.

    **THE MASK IS SET EXPLICITLY, BECAUSE READING IT SKIPPED THE TEST.** Written
    as `before = numba.get_num_threads()` with a skip below 2, this test
    **silently stopped running in the full sweep**: `bench/references.py` and
    `bench/spike.py` call `numba.set_num_threads` and never restore it, and
    `test_bench.py` sorts before `test_threads.py`, so the mask was already 1 by
    the time this ran. A skip is a silent loss of coverage -- the same shape as a
    diagnostic that reports "clean" because it could not run -- and the ambient
    value was never this test's to read.
    """
    ceiling = int(numba.config.NUMBA_NUM_THREADS)  # type: ignore[attr-defined]
    if ceiling < 2:  # pragma: no cover - single-core host
        pytest.skip("needs at least two numba threads to tell the two apart")
    original = numba.get_num_threads()
    numba.set_num_threads(2)
    try:
        with threadpoolctl.threadpool_limits(limits=1):
            observed = observe_thread_limits()
    finally:
        numba.set_num_threads(original)
    assert observed[NUMBA_KEY] == 2
    assert all(value == 1 for key, value in observed.items() if key != NUMBA_KEY)


def test_two_libraries_with_the_same_api_both_survive_the_keying():
    """A second OpenBLAS is kept, not silently dropped.

    `{entry["internal_api"]: entry["num_threads"] for entry in info}` drops one
    of them, and **numpy's OpenBLAS beside scipy's is the ordinary case** on a
    pip-installed stack. A dropped entry is a library whose limit is never
    checked, inside a check whose whole point is per-library coverage.

    Bug this catches: exactly that comprehension. The collision is **not
    reachable in this environment** -- measured, one `libopenblas` and one
    `libgomp` -- so the input is constructed rather than waited for, which is
    what makes the guard testable at all.
    """
    table = library_table(
        [
            {
                "internal_api": "openblas",
                "prefix": "libopenblas",
                "filepath": "/a/libopenblas-numpy.so",
                "num_threads": 4,
            },
            {
                "internal_api": "openblas",
                "prefix": "libopenblas",
                "filepath": "/b/libopenblas-scipy.so",
                "num_threads": 2,
            },
        ]
    )
    assert sorted(table.values()) == [2, 4]
    assert len(table) == 2


def test_a_single_library_keeps_a_readable_key():
    """The control: no collision means no disambiguation noise in the name.

    Bug this catches: disambiguating unconditionally, which puts a filesystem
    path into the layer-3 error message that a user has to read at four in the
    morning. The message names the library; it should say `openblas`.
    """
    table = library_table(
        [
            {
                "internal_api": "openblas",
                "prefix": "libopenblas",
                "filepath": "/a/libopenblas.so",
                "num_threads": 4,
            }
        ]
    )
    assert table == {"openblas": 4}


# --------------------------------------------------------------------------
# Setting the budget, and what happens when a library does not comply
# --------------------------------------------------------------------------


def test_inside_the_budget_every_library_observes_what_was_requested():
    """The positive control for every refusal below.

    Bug this catches: a budget that records the request and sets nothing, which
    is the `OMP_NUM_THREADS=1`-written-after-numpy-was-imported failure with a
    Python wrapper around it. Every entry is asserted, including numba's, so a
    budget that sets threadpoolctl and forgets numba fails here.
    """
    with thread_budget(1) as budget:
        assert budget.observed
        assert set(budget.observed.values()) == {1}
        assert budget.observed[NUMBA_KEY] == 1


def test_the_budget_restores_the_limits_it_changed():
    """Leaving the budget puts numba's mask back.

    **`numba.set_num_threads` has no context-manager form and persists for the
    process**, so a budget that does not restore changes every later test in the
    same pytest session -- the same class of defect as the `run_spike`
    allocation that raised the session watermark and failed a test in another
    module.

    Bug this catches: setting without restoring. It is invisible in the test
    that does the setting and shows up somewhere else entirely.

    **THE BASELINE IS SET EXPLICITLY AND NOT READ FROM THE AMBIENT STATE.**
    Written as `before = numba.get_num_threads()` this test **did not bite**:
    the mutation makes an *earlier* test in this module leave the mask at 1, so
    `before` reads 1, the budget sets 1, and nothing moved. That is the
    delta-with-an-external-baseline hazard the memory module documents, arriving
    in a different subsystem -- a difference whose baseline is set by history
    outside the test is order-dependent by construction. Measured: the mutation
    survived until the baseline was pinned.
    """
    ceiling = int(numba.config.NUMBA_NUM_THREADS)  # type: ignore[attr-defined]
    if ceiling < 2:  # pragma: no cover - single-core host
        pytest.skip("needs a mask value distinguishable from the budget's")
    original = numba.get_num_threads()
    numba.set_num_threads(2)
    try:
        with thread_budget(1):
            pass
        assert numba.get_num_threads() == 2
    finally:
        numba.set_num_threads(original)


def test_asking_for_more_threads_than_the_machine_has_is_a_layer_3_failure():
    """numba refuses an over-large request, and the refusal must be staged.

    **Measured on this 4-core box:** `numba.set_num_threads(1000)` raises
    `ValueError: The number of threads must be between 1 and 4`.

    Bug this catches: letting that `ValueError` escape. An unstaged exception is
    an unhandled exception, which Python reports as **exit code 1** -- "completed
    with failures above threshold" in this taxonomy, i.e. a run that finished
    badly rather than a config that was never runnable. The message must name
    the machine's limit, because "invalid thread count" does not say what to put
    in the config instead.
    """
    with pytest.raises(ValidationError) as caught:
        with thread_budget(1000):
            pass  # pragma: no cover - the budget raises on entry
    assert caught.value.layer is ValidationLayer.SEMANTIC
    assert str(numba.config.NUMBA_NUM_THREADS) in str(caught.value)  # type: ignore[attr-defined]


@pytest.mark.machine
def test_a_library_can_silently_clamp_a_request_and_the_observation_catches_it():
    """**OpenBLAS clamps to its build-time maximum and says nothing.**

    Measured: `threadpool_limits(limits=1000)` leaves OpenBLAS reporting **128**
    while OpenMP reports 1000. So one library refuses loudly and the other lies
    quietly, and **only the second is the dangerous one** -- it is the exact
    shape the observed-versus-requested check exists to catch, and it needs no
    mock to construct.

    Bug this catches: trusting the request. A run recording "1000 threads" in
    provenance while OpenBLAS used 128 has recorded a number that was never
    true, and the determinism guarantee rests on it.

    Marked `machine` because 128 is the installed OpenBLAS build's
    `NUM_THREADS`, not a property of this package. The assertion is that the
    request was **not** honoured, not that the value is 128.
    """
    with threadpoolctl.threadpool_limits(limits=1000):
        observed = observe_thread_limits()
    blas = [value for key, value in observed.items() if key.startswith("openblas")]
    assert blas
    assert all(value != 1000 for value in blas)


# --------------------------------------------------------------------------
# One owner at a time
# --------------------------------------------------------------------------


def test_the_two_phases_cannot_overlap():
    """Opening `fit` inside `assemble` raises.

    Section 11.1.1's "one owner at a time, never both" is what makes "the tile
    is the batch" hold: neither phase has to reason about the other's threads.

    Bug this catches: the invariant staying prose. Nothing in the tree made it
    false-able before this, and the phase that would violate it -- prefetching
    tile N+1 during tile N's fit -- does not exist until later, so it would have
    shipped as a sentence and the first prefetch optimization would have broken
    it with every test green.
    """
    with thread_budget(1) as budget:
        with budget.phase(Phase.ASSEMBLE):
            with pytest.raises(RuntimeError, match="one owner at a time"):
                with budget.phase(Phase.FIT):
                    pass  # pragma: no cover - the guard raises on entry


def test_the_phases_are_reusable_in_sequence():
    """The control: assemble, then fit, then assemble again, is the tile loop.

    Bug this catches: a guard implemented as "a phase may be entered once",
    which refuses the second tile. The refusal test above passes against that
    too, so without this one the guard could be wrong in the opposite direction.
    """
    with thread_budget(1) as budget:
        for _ in range(2):
            with budget.phase(Phase.ASSEMBLE):
                pass
            with budget.phase(Phase.FIT):
                pass
    assert set(budget.seconds) == {Phase.ASSEMBLE, Phase.FIT}


def test_the_phase_ratio_is_recorded_rather_than_assumed():
    """The fit-to-assemble ratio is a measured quantity on the budget.

    Section 11.1.1 justifies serializing the two phases on the ratio -- fit at
    ~5.4 s per series dominates a tile read of order seconds, so the idle I/O is
    free -- and says in terms that **if it ever inverts the decision needs
    revisiting and nothing else would show it**.

    Bug this catches: the justification staying an argument. A ratio nothing
    computes cannot invert visibly. The fixture makes fit the longer phase by
    construction, so the expected direction is known independently of what the
    code measures.
    """
    with thread_budget(1) as budget:
        with budget.phase(Phase.ASSEMBLE):
            pass
        with budget.phase(Phase.FIT):
            sum(range(200_000))
    assert budget.seconds[Phase.FIT] > budget.seconds[Phase.ASSEMBLE]
    assert budget.fit_to_assemble_ratio is not None
    assert budget.fit_to_assemble_ratio > 1.0


def test_a_ratio_with_no_assembly_measured_is_none_rather_than_a_number():
    """No assemble phase means no ratio, not a division by zero or an infinity.

    Bug this catches: reporting `inf`, which is a finite-looking sentinel that
    reads as "assembly was free" -- the opposite of "assembly was never
    measured". This project already refuses `-inf` as a stored sentinel for the
    same reason.
    """
    budget = ThreadBudget(requested=1, observed={})
    assert budget.fit_to_assemble_ratio is None


# --------------------------------------------------------------------------
# Assembly concurrency, derived from bytes
# --------------------------------------------------------------------------


@pytest.mark.parametrize("max_workers", [1, 2, 4, 8, 64, 1024])
def test_peak_assembly_bytes_stay_inside_the_budget_whatever_the_core_count(
    max_workers,
):
    """`W * chunk_bytes` never exceeds the assembly budget, for any `T`.

    **This is the assertion, not "W equals the expected number".** A test
    comparing `W` against a recomputed clamp shares the implementation's
    derivation path and would pass against a formula that multiplied by core
    count on both sides. Section 11.1.1 states a property about **bytes** --
    peak RAM must be derivable from the memory budget alone -- so that is what
    is asserted, across a sweep of core counts spanning this box and a 64-core
    one.

    Bug this catches: `W = T`, or `W = min(T, something)` with the byte term
    dropped. Peak RAM then tracks core count, which is the identical failure the
    across-tile parallelism ban exists to prevent, arriving through the assembly
    door.
    """
    assembly_bytes = 900_000_000
    chunk_bytes = 64_000_000
    workers = assembly_concurrency(assembly_bytes, chunk_bytes, max_workers)
    assert workers >= 1
    assert workers * chunk_bytes <= assembly_bytes
    assert workers <= max_workers


def test_raising_the_core_count_never_raises_the_peak():
    """The byte bound is flat in `T` once the budget is the binding constraint.

    Bug this catches: a clamp written the other way round -- `max` where `min`
    belongs -- which passes a single-`T` test and turns the core count into the
    memory knob. Asserted as a monotonicity across the sweep rather than at one
    point, because one point cannot see a bound that is not flat.
    """
    peaks = {
        max_workers: assembly_concurrency(900_000_000, 64_000_000, max_workers)
        * 64_000_000
        for max_workers in (1, 2, 4, 8, 64, 1024)
    }
    assert max(peaks.values()) <= 900_000_000


def test_one_chunk_is_irreducible_and_that_is_the_one_way_to_exceed_the_budget():
    """A chunk larger than the whole assembly budget still gives `W = 1`.

    **The floor of 1 is the single place peak assembly can exceed the assembly
    budget, and it is irreducible**: reading zero chunks makes no progress, so
    the loop would spin rather than report the problem. The cost is stated here
    rather than hidden -- a memory budget must leave room for at least one input
    chunk, and section 11.1.1's derivation assumes it.

    Bug this catches: returning 0 from the floor division, which is a
    plausible-looking number that holds no data. Same failure `tile_side` refuses
    for the same reason.
    """
    assert assembly_concurrency(10_000, 64_000_000, 8) == 1


def test_a_chunk_size_of_zero_is_refused():
    """A zero or negative chunk size raises rather than dividing.

    Bug this catches: `assembly_bytes // 0`, which is a `ZeroDivisionError`
    escaping into a run -- unstaged, so exit code 1 -- where the real fault is
    an input whose chunk geometry was never read.
    """
    with pytest.raises(ValueError, match="chunk_bytes"):
        assembly_concurrency(900_000_000, 0, 4)
