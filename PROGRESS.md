# metamer — progress

## Current work

| what | where |
|---|---|
| Design document | [`docs/superpowers/specs/2026-08-04-metamer-design.md`](docs/superpowers/specs/2026-08-04-metamer-design.md) |
| Original build prompt | [`metamer-build-prompt.md`](metamer-build-prompt.md) — **superseded** by the design doc's §2 where they conflict |
| Implementation plan | not written yet |

**Next action:** spec review with the user, then write the Phase 1 implementation plan.

Phase list lives in design doc §17. Phase 1 exit criteria live in §18. Do not duplicate
either here.

---

## Cross-cutting decisions

These are recorded in full in the design doc; this is an index of the ones most likely to
be violated by accident.

- **`(B, N)` is the only code path.** `B=1` is a shape, never a separate implementation.
- **No reparameterization, reordering, or preconditioner refresh may change the coordinate
  system mid-optimization** without an explicit curvature-history reset. (§4.5)
- **Never interpolate to fill gaps.** Mask the update, keep the prediction. (§7.3)
- **Analytic transition/process-noise per family.** The general `expm`/Lyapunov path is a
  fallback that should almost never run; frequent firing is a bug signal. (§2.1, §7.1)
- **Scores carry both an engine tag and an objective tag**, and the selection layer refuses
  to rank across either. Hard error, not a warning. (§6.2)
- **Profiled-out GLS parameters count toward `k` under ML.** Under REML, `β` is not a
  parameter of the model at all. Two definitions, not one with an adjustment. (§4.7)
- **float64 throughout `core`**; float32 only at the batch/IO boundary. (§15.4)
- **Primary likelihood oracle is brute-force MVN, not celerite2.** celerite2 shares the GP
  conceptual frame and can agree while both are wrong. (§16.1)

---

## Gotchas discovered

- **`celerite2` has no `osx-arm64` conda-forge build** (verified 2026-08-04). Coverage is
  split between conda-forge and PyPI with no single source covering every target platform.
  Mitigated by making it a test-only dependency. Full table in design doc §15.2.
- **`pixi search` without `--platform` reports an arbitrary subdir** — it showed `osx-64`
  while running on linux. Always pass `--platform` when checking availability, and use a
  known-good package (e.g. `numba`) as a control, because `rg | head` swallows the
  non-zero exit and an empty result looks the same as a failed query.
- Per user global instructions: never do investigative `git checkout <sha>` inside the
  working tree. Use `git show <sha>:<path>`, `git worktree add`, or `git diff <sha>`.

---

## Open questions needing user input

1. **Hardware for the execution-strategy spike (design doc §9.2).** The decision rule
   requires measurement on both a 64-core node and an 8-core/16 GB laptop. Availability
   unconfirmed. Without both, the decision rule needs restating.
2. **CI.** Not specified anywhere. It determines whether Tier-2 platforms and the celerite2
   agreement test are actually exercised, and whether Windows could ever be claimed.
3. **`n_eff_bic` estimator** (design doc §10.1) — the two effective-sample-size quantities
   are named and their uses separated, but the precise estimator for the BIC variant is not
   fixed.
4. **Index-space vs area-weighted adjacency** for the failure clustering statistic
   (§14.2). Index-space is recommended; not yet final.

---

## Deferred items

Design-level deferrals with their landing conditions live in design doc §19. Nothing is
deferred that is not recorded there.
