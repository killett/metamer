"""The thread budget: one owner at a time, limits observed rather than requested.

**THE DETERMINISM PRECONDITION IS OBSERVED, NOT REQUESTED** (design doc section
11.3). `OMP_NUM_THREADS=1` recorded in provenance is a record of a *request*, and
whether it took effect depends on import ordering that nothing in the process
enforces -- set after numpy is imported it does nothing, silently. That is
name-is-not-a-gate at its sharpest: a determinism guarantee resting on a value
written down after being ignored.

**TWO INSTRUMENTS, BECAUSE ONE OF THEM CANNOT SEE THE LIBRARY THAT MATTERS.**
Both facts below were measured on 2026-08-12, and neither is visible by reading
`threadpoolctl`'s documentation:

- **numba's threading layer is invisible to `threadpool_info()` until something
  parallel has run.** After `import numba` the table holds OpenBLAS alone;
  `libgomp` appears only once a `prange` function has executed. The layer-3
  check runs at startup, which is exactly when the layer is not there -- and
  `threadpool_limits` does not retroactively limit a library loaded after it. So
  `observe_thread_limits` calls `numba.get_num_threads()` first, which launches
  the layer as a documented side effect of a public call.
- **`threadpool_limits(1)` does not change `numba.get_num_threads()`.** Measured:
  inside the limit, `threadpool_info()` reports `openblas 1, openmp 1` while
  numba still reports 4. They are different quantities -- threadpoolctl caps the
  OpenMP runtime's pool, numba's mask is how many slices a `prange` is cut into,
  and a `prange` reduction reassociates over numba's count. Numba's limit is
  therefore set and observed **through numba**, under its own key.

**ONE OWNER AT A TIME, NEVER BOTH** (section 11.1.1). Assemble (I/O, decompress,
the float32 to float64 cast) and fit (`prange` over the tile's series) never
overlap, so neither reasons about the other's threads, and that is what makes
"the tile is the batch" hold. `ThreadBudget.phase` **raises on overlap** rather
than documenting the rule: the phase that would violate it -- prefetching tile
`N+1` during tile `N`'s fit -- does not exist yet, so a written rule would ship
unenforced and the first prefetch optimization would break it silently.

**AND THE RATIO THAT JUSTIFIES SERIALIZING IS RECORDED, NOT ASSUMED.** Fit at
~5.4 s per series against a tile read of order seconds means the idle I/O is
free; **if that ever inverts the decision needs revisiting and nothing else would
show it**, so the budget accumulates seconds per phase.
"""

from __future__ import annotations

import time
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from metamer.batch.validation import ValidationError, ValidationLayer

NUMBA_KEY = "numba"
"""Key for numba's own thread mask.

Deliberately not folded into the OpenMP entry. They are measured by different
instruments and can disagree -- measured, `openmp 1` beside `numba 4` -- and it
is numba's count that a `prange` reduction reassociates over.
"""


class Phase(StrEnum):
    """Which phase owns the machine. They never overlap."""

    ASSEMBLE = "assemble"
    FIT = "fit"


def library_table(info: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    """Key `threadpool_info()`'s entries by library, keeping every one.

    **THE OBVIOUS COMPREHENSION LOSES ENTRIES.**
    `{entry["internal_api"]: entry["num_threads"] for entry in info}` drops one
    of two libraries sharing an API, and **numpy's OpenBLAS beside scipy's is the
    ordinary case** on a pip-installed stack. A dropped entry is a library whose
    limit is never checked, inside a check whose entire purpose is per-library
    coverage.

    Disambiguation is applied **only on collision**, so the common case keeps a
    key a human can read in an error message at four in the morning.

    Args:
        info: `threadpoolctl.threadpool_info()`'s output, or a constructed
            equivalent.

    Returns:
        Observed thread count per library.
    """
    counts: dict[str, list[Mapping[str, Any]]] = {}
    for entry in info:
        counts.setdefault(str(entry["internal_api"]), []).append(entry)

    table: dict[str, int] = {}
    for api, entries in counts.items():
        if len(entries) == 1:
            table[api] = int(entries[0]["num_threads"])
            continue
        for entry in entries:
            leaf = str(entry.get("filepath") or entry.get("prefix") or "?").rsplit(
                "/", 1
            )[-1]
            table[f"{api}:{leaf}"] = int(entry["num_threads"])
    return table


def _numba_maximum() -> int:
    """Return the largest thread count numba will accept in this process.

    `NUMBA_NUM_THREADS` is fixed at import and `set_num_threads` refuses
    anything above it, so this is what a user has to write in the config
    instead of whatever they asked for.

    Returns:
        The ceiling.
    """
    import numba

    return int(numba.config.NUMBA_NUM_THREADS)  # type: ignore[attr-defined]


def observe_thread_limits() -> dict[str, int]:
    """Return the OBSERVED thread limit for every library that will run.

    Reads both instruments -- see this module's docstring for why one is not
    enough, and why `numba.get_num_threads()` is called before the table is
    taken rather than after.

    Returns:
        Observed limit per library, including numba's own mask under
        `NUMBA_KEY`.
    """
    import numba
    import threadpoolctl

    # FIRST, AND THE ORDER IS THE WHOLE POINT: this launches numba's threading
    # layer, so `libgomp` is in the table below. Called at startup without it,
    # the table reports every library at the requested limit while the library
    # the fit phase is about to use has not been loaded.
    numba_threads = int(numba.get_num_threads())  # type: ignore[no-untyped-call]
    table = library_table(threadpoolctl.threadpool_info())
    table[NUMBA_KEY] = numba_threads
    return table


@dataclass
class ThreadBudget:
    """The established budget, its observation, and the phase accounting.

    Attributes:
        requested: The thread count the config asked for.
        observed: Observed limit per library, taken after the limits were set.
        seconds: Accumulated wall-clock seconds per phase.
    """

    requested: int
    observed: dict[str, int]
    seconds: dict[Phase, float] = field(default_factory=dict)
    _owner: Phase | None = None

    @property
    def fit_to_assemble_ratio(self) -> float | None:
        """Fit seconds over assemble seconds, or None if either was not measured.

        **None rather than `inf`.** An infinity is a finite-looking sentinel
        that reads as "assembly was free", which is the opposite of "assembly
        was never measured" -- the same argument that keeps `-inf` out of every
        stored slot in this project.

        Returns:
            The ratio, or None.
        """
        assemble = self.seconds.get(Phase.ASSEMBLE, 0.0)
        fit = self.seconds.get(Phase.FIT, 0.0)
        if assemble <= 0.0 or fit <= 0.0:
            return None
        return fit / assemble

    @contextmanager
    def phase(self, phase: Phase) -> Iterator[None]:
        """Own the machine for `phase`, refusing to overlap with another.

        Args:
            phase: Which phase is starting.

        Yields:
            Nothing; the phase is the context.

        Raises:
            RuntimeError: If another phase is already open. Section 11.1.1's
                "one owner at a time" made executable -- the alternative is a
                sentence that the first prefetch optimization breaks silently.
        """
        if self._owner is not None:
            raise RuntimeError(
                f"one owner at a time: {self._owner.value!r} is already running "
                f"and {phase.value!r} tried to start. Assemble and fit never "
                "overlap, which is what lets neither reason about the other's "
                "threads"
            )
        self._owner = phase
        started = time.perf_counter()
        try:
            yield
        finally:
            self.seconds[phase] = self.seconds.get(phase, 0.0) + (
                time.perf_counter() - started
            )
            self._owner = None


@contextmanager
def thread_budget(threads: int) -> Iterator[ThreadBudget]:
    """Set the thread limits, observe what actually took effect, and restore.

    **RESTORATION IS NOT TIDINESS.** `numba.set_num_threads` has no
    context-manager form and persists for the whole process, so a budget that
    does not put it back changes every later caller in the same process -- the
    same class of defect as a test whose allocation raises the session watermark
    and fails a test in another module.

    Args:
        threads: The thread count the config requested.

    Yields:
        The established budget, carrying the observation.

    Raises:
        ValidationError: Layer 3, if the request exceeds what numba will accept.
            **Measured on a 4-core box, `numba.set_num_threads(1000)` raises
            `ValueError`**, and an unstaged `ValueError` is an unhandled
            exception -- exit code 1, which this taxonomy defines as "completed
            with failures above threshold". The message names the machine's
            limit, because "invalid thread count" does not say what to write in
            the config instead.
    """
    import numba
    import threadpoolctl

    previous = int(numba.get_num_threads())  # type: ignore[no-untyped-call]
    try:
        numba.set_num_threads(threads)  # type: ignore[no-untyped-call]
    except ValueError as error:
        raise ValidationError(
            ValidationLayer.SEMANTIC,
            f"threads = {threads} cannot be honoured on this machine: {error}. "
            f"numba reports a maximum of {_numba_maximum()} "
            "threads here",
        ) from error

    try:
        with threadpoolctl.threadpool_limits(limits=threads):
            yield ThreadBudget(requested=threads, observed=observe_thread_limits())
    finally:
        numba.set_num_threads(previous)  # type: ignore[no-untyped-call]


def assembly_concurrency(
    assembly_bytes: int, chunk_bytes: int, max_workers: int
) -> int:
    """Derive the assembly worker count from a BYTE budget.

    `W = clamp(1, assembly_bytes // chunk_bytes, max_workers)`.

    **THE UPPER CLAMP IS A THREAD COUNT AND THIS IS STILL NOT
    CORE-COUNT-DERIVED.** Clamping by `max_workers` only ever *lowers* `W`, so
    `W * chunk_bytes <= assembly_bytes` holds whatever the machine has, and
    section 11.1.1's requirement -- **peak RAM must be derivable from the memory
    budget alone** -- survives. Read carelessly the formula looks like the
    failure the across-tile parallelism ban exists to prevent; the direction of
    the clamp is what makes it not that.

    **THE FLOOR OF 1 IS THE ONE PLACE PEAK CAN EXCEED THE BUDGET, AND IT IS
    IRREDUCIBLE.** Reading zero chunks makes no progress, so the loop would spin
    rather than report the problem -- the same reason `tile_side` refuses a
    budget that does not hold one series. **A memory budget must therefore leave
    room for at least one input chunk**, and section 11.1.1's derivation assumes
    it.

    Args:
        assembly_bytes: Bytes the budget allows the assemble phase to hold.
        chunk_bytes: Size of one input chunk.
        max_workers: Upper bound from the thread budget.

    Returns:
        The number of chunks to have in flight at once.

    Raises:
        ValueError: If `chunk_bytes` is not positive. Dividing by it would raise
            `ZeroDivisionError` inside a run -- unstaged, so exit code 1 -- when
            the real fault is an input whose chunk geometry was never read.
    """
    if chunk_bytes <= 0:
        raise ValueError(
            f"chunk_bytes must be positive, got {chunk_bytes}; a zero chunk size "
            "means the input's chunk geometry was never read"
        )
    return max(1, min(assembly_bytes // chunk_bytes, max_workers))
