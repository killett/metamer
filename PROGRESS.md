# metamer — progress

## Current work

| what | where |
|---|---|
| Design document | [`docs/superpowers/specs/2026-08-04-metamer-design.md`](docs/superpowers/specs/2026-08-04-metamer-design.md) |
| Original build prompt | [`metamer-build-prompt.md`](metamer-build-prompt.md) — **superseded** by the design doc's §2 where they conflict |
| Phase 1 implementation plan | [`docs/superpowers/plans/2026-08-05-metamer-phase1.md`](docs/superpowers/plans/2026-08-05-metamer-phase1.md) |
| Phase 1 task tracker | `docs/superpowers/plans/2026-08-05-metamer-phase1.md.tasks.json` (native task ids 8–27) |

**Next action:** execute Phase 1 Task 0 (package skeleton). Resume with
`/superpowers-extended-cc:executing-plans docs/superpowers/plans/2026-08-05-metamer-phase1.md`.

**The Phase 1 branch:** Task 18 is a user gate requiring runs on the 64-core box and the
MacBook. Task 19 (batched trust-region) is built **only** if Task 18's verdict is
"inconclusive" — if path B wins by ≥3× at d=3, it is deleted rather than deferred.

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
  conceptual frame and can agree while both are wrong. MVN validates the state-space
  construction (bespoke); celerite2 validates the ACF (textbook). (§16.1)
- **Three hashes, not two.** `fit_hash` ⊂ `compat_hash` ⊂ `run_hash`. Warm starts and the
  calibration cache key on `fit_hash`; a `compat_hash`-only mismatch recomputes derived
  arrays from stored primitives rather than refitting. (§13.3, §12.8)
- **Do not build the batched trust-region until the stage-1 spike says to.** It exists only
  for path A's performance; if path B wins it is dead weight, and path A's permanent form
  is a plain per-series scipy loop. (§9.2, §17)
- **Delta-method uncertainties are first-order** and degrade near a diagnostic limit — a
  `DIAGNOSTIC_LIMIT` outcome also means the reported uncertainty is unreliable. (§4.1)
- **Parallelism is WITHIN a tile, never ACROSS tiles.** Across-tile parallelism is the
  obvious later "optimization" and it multiplies peak RAM by thread count, silently
  breaking the 16 GB constraint. (§11.1)
- **Caches live with the zarr store, not in local scratch** — preemptible instances lose
  local scratch, and losing pass 1's warm starts costs a full re-run of pass 1. (§15.5)

---

## Gotchas discovered

- **`celerite2` has no `osx-arm64` conda-forge build** (verified 2026-08-04). Coverage is
  split between conda-forge and PyPI with no single source covering every target platform.
  Mitigated by making it a test-only dependency. Full table in design doc §15.2.
- **`pixi search` without `--platform` reports an arbitrary subdir** — it showed `osx-64`
  while running on linux. Always pass `--platform` when checking availability, and use a
  known-good package (e.g. `numba`) as a control, because `rg | head` swallows the
  non-zero exit and an empty result looks the same as a failed query.
- **The prompt's `tile_side = sqrt(block_bytes / (n_time · itemsize))` counts only the
  float64 data.** Full accounting gives 343 instead of 445 at a 1 GB budget with a shared
  design matrix, and 187 with per-point regressor fields. Design doc §9.4.
- **Per-point regressor fields (e.g. GIA) cost `N × k_β × 8` per series** — 20.2 kB at
  N=630, k_β=4, which is ~2.4× everything else combined. Whether a config lands in the
  shared-X or per-point-X regime is the single biggest memory fact about it.
- Per user global instructions: never do investigative `git checkout <sha>` inside the
  working tree. Use `git show <sha>:<path>`, `git worktree add`, or `git diff <sha>`.

---

## Hardware

| machine | threads | role |
|---|---|---|
| Ubuntu mini PC — 4 slow cores, 16 GB RAM (~10 GB free) | {1, 4} | primary development; correctness, oracles, memory formula. **Cannot answer the budget question.** |
| Linux box, 64 cores (RAM unknown — establish before use) | {1, 4, full} | **the decisive measurement**; the only machine where the 19 ms budget comparison is valid |
| Apple Silicon MacBook, 32 GB | {1, full} | adversarial case for path A (high bandwidth per core); arm64 smoke test |
| SkyPilot via a forthcoming `cloudify` skill | — | future; design doc §15.5 |

Machine plan and the two normalization instruments (canonical filter pass for the budget
question; compute/bandwidth roofline pair for cross-machine prediction) are in design doc
§9.2.

## Open questions needing user input

1. **CI.** Not specified anywhere. It determines whether Tier-2 platforms and the optional
   celerite2 agreement test are actually exercised, and whether Windows could ever be
   claimed.
2. **Index-space vs area-weighted adjacency** for the failure clustering statistic
   (§14.2). Index-space is recommended; not yet final.

---

## Deferred items

Design-level deferrals with their landing conditions live in design doc §19. Nothing is
deferred that is not recorded there.
