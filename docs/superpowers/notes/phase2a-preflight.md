# Phase 2a — the (a)–(k) pre-flight, per task

The audit run against each Phase 2a task brief **before** any code was written, and what
each finding changed. Same role as
[`phase2-preliminaries-preflight.md`](phase2-preliminaries-preflight.md) played for P0–P2.

The method is [`phase1-to-phase2-handoff.md`](phase1-to-phase2-handoff.md) §1. Only the
findings live here; the reasoning behind the decisions being audited is in `PROGRESS.md`'s
brainstorm section and the plan itself.

---

## Task 0 — package skeleton and dependencies (audited 2026-08-11)

Task 0 is mostly structural, so the interesting half of the audit is not the dependency
list — it is the **raising stub engine**, which the brief defines here and does not exercise
until Task 11. Six findings changed the implementation; two checks came back clean and are
recorded because a clean result is what makes the checks credible rather than ritual.

### (a) / (a2) — the stub engine is a pure negative, and a negative cancels

The stub exists to prove "no fit ran". That claim is **constant across every axis its
consumers compare**: a stub wired into the run and never reached, and a stub never wired in
at all, produce byte-identical green results. This is the cancellation rule at the level of a
test fixture, and it is the same shape as `metamer_version` sitting in `FIT_RELEVANT_FIELDS`
with nothing in `src/` populating it — present, named, and gating nothing.

**Changed:** Task 0 ships a **positive control**. `tests/test_stub_engine.py` asserts the stub
*does* raise when `fit()` is given a fittable batch. Without it the fixture ships untested
through four tasks and is first exercised where its own failure would be read as a bug in the
recompute path.

### (i) — MEASURED: the stub is silent for a wholly-masked tile

`ConcentratedObjective.evaluate` returns at `src/metamer/core/objective.py:862`, **before**
`self.engine.score` at `:872`, whenever `not np.any(precheck == Outcome.OK.code)`. The
short-circuit is deliberate and documented in place (it is what keeps a wholly-masked tile
`INSUFFICIENT_DATA` rather than `RANK_DEFICIENT_X`).

The consequence for the fixture is that **a raising stub raises nothing when every series in
the batch fails the design precheck** — and that is exactly the cheap fixture a recompute test
would reach for, because `fit` costs ~5.4 s per series and a real batch is expensive.

**Changed:** the hazard is made **executable rather than advisory**, in the project's own
idiom (a test asserting a limit *is not* crossed is the only documentation this project has
evidence for). `tests/test_stub_engine.py` carries both halves:

- a healthy batch through `fit()` raises `StubEngineCalled`;
- a wholly-masked batch through `fit()` **does not raise**, and the test says why.

A later author who deletes the short-circuit will fail the second test and be pointed at the
reason, rather than discovering it inside Task 12.

### (h) — the seam, not just the fixture

`fit()` takes `engine: Engine | None = None` (`fit.py:134`) and defaults to `KalmanEngine()`
(`fit.py:170`). A test that means to prove "no fit ran" must thread the stub through **as a
real caller would**. If a later task's runner constructs its engine internally from the config
instead of accepting an injected one, the stub cannot be threaded at all and the fixture is
decorative — Task 11's `scale`-left-at-its-default instance, one level out.

**Changed:** `tests/conftest.py` documents `fit(..., engine=...)` as the injection seam, and
the plan's Task 4/9 briefs inherit the requirement that the runner keep an injectable engine.

### (f) — the tree already names a `[batch]` extra that does not exist

`tests/test_core_isolation.py` was written in Phase 1 and its docstring reads:

> someone adds `import xarray` to a core module, silently making `metamer.core` unusable for
> downstream consumers that installed without the **[batch] extra**.

There is no `[batch]` extra in `pyproject.toml`. Task 0 is the dependency task, so it is where
that extra belongs; deferring it leaves a test in the tree documenting a packaging contract
nothing implements.

Its guard set is `{xarray, dask, zarr}` — **three of the five imports 2a adds**, so it reads as
covering the batch boundary while `pydantic` and `threadpoolctl` cross it unwatched. Measured
before extending it: importing `metamer.core` pulls **none** of the five, so widening the set
costs nothing and is not merely aspirational.

**Changed:** `pyproject.toml` gains `[project.optional-dependencies] batch`, and the isolation
set is widened to all five.

### (d) — `pyproject.toml` appears nowhere in the brief, and pixi hides the consequence

The brief's whole dependency story is `pixi.toml`. But `pixi run` executes off
`PYTHONPATH=src` with the environment already complete, so **an import that would break the
published wheel is invisible in the development environment.** `[project] dependencies` is
`numpy`, `scipy`, `numba`, `psutil` — nothing else — and CI installs the package.

**Changed:** the runtime dependency declaration is part of Task 0. `metamer.core`'s
dependencies stay exactly as they are (that is what the isolation test protects); the new ones
go in the `batch` extra.

### (a2) — "zarr (v3)" is a name, not a pin

`zarr = "*"` resolves to 3.3.0 today. That is an accident of the current conda-forge release
and of `exclude-newer = "7d"`, not a constraint — and the manifest's solve is therefore a
function of wall-clock time (pre-flight (k) applied to a dependency spec). Task 8 depends on
v3 sharding and the v2/v3 store layouts differ.

**Changed:** `zarr = ">=3,<4"`, and a test asserts the *installed* major version is 3, because
a lock refresh is the thing that would silently move it.

### (a2) — the stub's `engine_id` is a decision the brief does not make

`Engine` carries a data member `engine_id: EngineId` (`engines/protocol.py:122`) and `EngineId`
is a closed `StrEnum` of four members. Scores carry an engine tag and **ranking across tags is
a hard error, not a warning** — so a stub tagged `WHITTLE` would make a consumer's test fail
inside the tag guard rather than inside the assertion it was written for.

**Changed:** the stub is tagged `EngineId.KALMAN` and says why in its docstring: it stands in
for the engine it replaces, and it must be commensurable with whatever else the run scored, or
the negative it proves gets swallowed by an unrelated refusal.

### (c) — the protocol surface, enumerated rather than counted

`Engine` is exactly one data member (`engine_id`) and one method (`score`), read off
`engines/protocol.py:113-135`. One raising path covers it **today**. Recorded as enumerated,
not counted, so a protocol method added later is a known review point rather than a silent
gap — an asserted count is how two bypassed exits survived Phase 1's Task 8.

### (g) — signature binding, and one clean result worth recording

- `score(state_space, theta, y, mask, t, design, objective=Objective.ML) -> ScoredResult`.
  **`design` is `NDArray[np.float64] | None`, not a `DesignInfo`** — a stub written from
  memory of `fit()`'s vocabulary would get this wrong.
- **`runtime_checkable` checks method *presence*, not signature**, so `isinstance(stub, Engine)`
  is a weak assertion by construction and `mypy` is the real gate on the stub's shape. Both
  are used; neither is treated as the other's substitute.
- `protocol.py:117` states in capitals: **check conformance with `isinstance`, never
  `issubclass`** — a `runtime_checkable` protocol with a data member raises `TypeError` from
  `issubclass` by design.
- **Clean, and recorded as such:** `objective.py:201`'s `KalmanEngine().score(...)` is inside a
  module docstring — the reproduction recipe for its conditioning table — and **not** live
  code. So `fit(engine=...)` is the only engine construction site on the fit path, and the
  injection seam is genuinely single. Every prior seam check in this project found the seam
  imagined or stale; this one did not.

### (j) — `pixi install` cannot be its own oracle

"`pixi install` solves on all four platforms" is evidence produced by the same solver that
wrote the lock file, so it cannot disagree with itself — a reference sharing a derivation path
with its subject.

**The independent check is `pixi search --platform` per platform with a known-good control**,
because `rg | head` swallows a non-zero exit and an empty result looks identical to a failed
query. Run 2026-08-11:

| platform | zarr | threadpoolctl | numba (control) |
|---|---|---|---|
| linux-64 | 3.3.0 | 3.6.0 | 0.66.0 |
| linux-aarch64 | 3.3.0 | 3.6.0 | 0.66.0 |
| osx-arm64 | 3.3.0 | 3.6.0 | 0.66.0 |
| osx-64 | 3.3.0 | 3.6.0 | 0.66.0 |

**Neither package needs `[target.linux-64.dependencies]`.**

### (e) — the brief's acceptance criteria cannot fail for an interesting reason

`python -c "import metamer.batch, metamer.config"` passes against two empty files; a green
suite, typecheck and lint say nothing about anything Task 0 adds; and `pixi install` solving is
(j) above. **The stub engine — the task's only behavioural artifact — has no test in the brief
at all.**

**Changed:** the positive control and the short-circuit test above are Task 0's actual
acceptance. Everything else is a smoke check and is labelled as one.

### Ran the brief's numbers

Both of the brief's factual claims were re-checked rather than trusted, as it instructs:

- **`check-added-large-files` limit is 2000 KB.** Confirmed — `.pre-commit-config.yaml` carries
  the local reimplementation at `max=2000000` bytes.
- **`pixi.lock` is 635.6 KB, not 630.** The brief's own instruction is "re-check the number,
  not this note", and re-checking is what found the drift. Still ~3× under the limit; zarr does
  not bring it close.

### What is genuinely new, against what the brief claims

The brief lists four dependencies to add. Measured:

| dependency | state before Task 0 |
|---|---|
| `zarr` | **genuinely absent** — not in `pixi.toml`, not in the lock, not importable |
| `threadpoolctl` | **already installed at 3.6.0**, transitively, and undeclared |
| `xarray` | already declared in `pixi.toml` |
| `pydantic` | already declared in `pixi.toml` |

So the brief's watch item — "adding dependencies rewrites and stages `pixi.lock`" — is a
prediction to check, not a fact. Phase 1's Task 0 hit the same thing from the other side:
`psutil` produced **no lock diff at all** because it was already resolved on all four platforms
as a transitive dependency. Declaring `threadpoolctl` is still correct: **a package that is
present only transitively is a dependency nothing guarantees**, and Task 5's whole subject is
the difference between a limit that is requested and a limit that is observed.
