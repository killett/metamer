"""The process exit codes: one published table, imported by every entry point.

**MOVED HERE FROM `metamer.batch.validation` AT 2f TASK 8 (2026-10-23), WITH ITS
VALUES AND DOCSTRING UNCHANGED.** That module imports `pydantic` and the config
model at module scope, so importing the table from it loads the validator --
and the report's import boundary forbids exactly that, because a user with a
store and no config must not be made to load the validator for a config they do
not have. D13 rules *"one published table, not a second"*, so the table moved
rather than being copied: `metamer.batch.validation` re-exports it and every
existing import resolves to **this object**. A copy would have compared equal
member by member -- `IntEnum` members compare as ints -- and drifted silently on
the next appended member; `tests/test_report_main.py` asserts identity.

**THIS MODULE IMPORTS ONLY THE STANDARD LIBRARY**, and that is asserted, not
assumed: it is the reason the module exists.
"""

from __future__ import annotations

from enum import IntEnum


class ExitCode(IntEnum):
    """The process exit codes, as an enum and a return value.

    **All five land now**, even though sub-phase 1 produces only three of them,
    because retrofitting an exit code means revisiting every early return -- the
    argument that made the failure taxonomy a Phase 1 deliverable.

    **`INTERNAL_ERROR` IS THE SIXTH AND IT LANDED AT 2e's TASK 1 (2026-09-12),
    APPENDED AND NEVER RENUMBERED.** The numbers are a published interface: a
    shell script branching on them cannot be updated by a later commit, so a new
    member takes the next free value and no existing one moves.

    **It closes a collision rather than adding a capability.** CPython reports an
    unhandled exception as exit 1, and 1 means *completed with failures above
    threshold* -- **opposite facts about a run**, one saying it finished and the
    map is written, the other saying it did not. A script resuming on 1 would
    resume from a crash that left nothing to resume. The collision was harmless
    only while 1 had no producer; 2e's Task 6 gives it one, so the separation
    lands first, in the sub-phase that creates the hazard.

    **The weaker fallback was refused**, and the reason is recorded at design doc
    section 14.3: requiring every test that asserts exit 1 to also assert the
    absence of a traceback tests the *symptom*, and leaves two different events
    sharing a code -- which is the collision, not a fix for it.

    **`ABORTED_EARLY` ACQUIRED A PRODUCER AT TASK 10, AHEAD OF THE MECHANISM
    THIS DOCSTRING ORIGINALLY NAMED.** It said both 1 and 2 waited on sub-phase
    2e's failure-rate threshold and early-abort criterion. Design doc 14.3
    defines 2 more broadly than that mechanism -- *"aborted early --
    resumable"*, whose stated purpose is to let a resuming script tell an
    abort apart from a rejected config -- and **a run flushed by SIGTERM is
    exactly that case**: its completed tiles are on disk with their bits set and
    the same command finishes them. Exiting 0 there would report a store as
    complete when it is not. 2e's early abort becomes the second producer.

    **`COMPLETED_WITH_FAILURES` IS UNREACHABLE BY CONSTRUCTION BETWEEN 2e's TASK
    1 AND ITS TASK 6, AND THAT IS ASSERTED RATHER THAN ASSUMED.** It needs the
    failure-rate threshold, which is Task 6's. Until then no path returns it --
    ~~and while it has no producer, an observed 1 is CPython's
    unhandled-exception code~~, **struck 2026-09-12: that is now
    `INTERNAL_ERROR`, so an observed 1 is a DEFECT rather than a crash.** That is
    a stronger statement than the one it replaces, it holds only inside this
    window, and `tests/test_runner.py` pins it there.

    **THE WINDOW CLOSED AT 2e's TASK 6 (2026-09-16).** `COMPLETED_WITH_FAILURES`
    now has its producer, and **its definition is 2e's because design doc
    section 14.3 never gave one**: a two-pass run whose early-abort verdict found
    a candidate above section 14.1's threshold, and which completed anyway under
    `--on-candidate-failure=drop` or `continue`. The rate behind it was measured
    on the COARSE pass, and the final console line says so. **A one-pass run has
    no verdict and therefore can never exit 1.** `tests/test_runner.py`'s
    unreachability test was inverted to "only from the threshold" rather than
    deleted.
    """

    OK = 0
    COMPLETED_WITH_FAILURES = 1
    ABORTED_EARLY = 2
    CONFIG_INVALID = 3
    DATA_INVALID = 4
    INTERNAL_ERROR = 5
