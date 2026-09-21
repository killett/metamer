"""Design doc section 14.2's report, computed from a finished store.

**THE PROPERTY THIS PACKAGE EXISTS TO PRESERVE IS "USABLE ON SOMEONE ELSE'S
STORE".** Section 14.2 names three consequences of computing the report from
the stored status arrays rather than from carried counters -- resumption
correctness is free, the report is independently testable, and it runs on a
store its reader did not produce -- and the third is the one that constrains
every module here.

Three things follow, and each is enforced rather than intended:

1. **Nothing in this package opens a store for writing.** A report that mutates
   its subject cannot be run on a store you do not own.
2. **The import graph carries no config machinery and no plotting stack.** A
   user with a store and NO CONFIG must not be made to load the validator for a
   config they do not have; `tests/test_report_reader.py` holds that line in a
   subprocess, with a positive control proving the probe can see a violation.
3. **Every number says where it came from**, because a report read by someone
   who did not run the run cannot be interpreted by knowing what was typed.

**WHAT THIS PACKAGE IS NOT.** The `metamer report` subcommand is Phase 5's;
section 14.2 resolved that split on 2026-09-12 by the same measure/print rule
that split section 14.1's counters from their display. Sub-phase 2f ships the
computation and `python -m metamer.report <store>` as a minimal entry point.
"""
