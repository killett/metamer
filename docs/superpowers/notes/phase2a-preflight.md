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

---

## Task 1 — the config model, `load()`, and the hash wiring (audited 2026-08-11)

The brief's own risk is stated in the plan: a hash module is made entirely of comparisons,
so its tests cancel the thing they are testing. Every finding below is downstream of that.

### (a2) — `registry_version` is in the allowlist, is required, and nothing decided where it comes from

`FIT_RELEVANT_FIELDS` has always carried `registry_version`, and `_subset` **raises** when an
allowlisted field is absent. **The plan's Task 1 field table does not mention it at all.** It
was not stamped like `algorithm_version` and not defaulted like `seed`; every caller was a
test supplying it by hand, so nothing ever had to decide its source.

`metamer.config.load` is the moment that stops being tenable. The reading the field's name
invites is that the TOML supplies it — a value identifying the installed family registry,
provided by the thing it is supposed to identify. A user pinning `registry_version = "1"`
against a registry that has since changed then reuses fits computed by different kernels,
with every array the right shape, every value finite, and no symptom.

**This is `metamer_version` in `FIT_RELEVANT_FIELDS` a second time**, caught before a config
could populate it rather than after.

**Changed:** `normalize` stamps `REGISTRY_VERSION_KEY` from `registry.REGISTRY_VERSION` and
refuses a config carrying it, exactly as it already did for `algorithm_version`. The stamped
value equals what the fixtures supplied, **so no hash moved — only the source did.** Both
stamped keys are now covered by parametrized tests deriving the module attribute from the
payload key, so a third stamped key cannot fall out of both.

### (a2) — a nested `warm_start` mapping would make allowlist membership implicit

The five warm-start settings could enter the allowlist as one `warm_start` key holding a
mapping. **They must not.** Compat relevance is an allowlist and *membership is the entire
mechanism*; one nested key makes membership implicit for everything inside it, so a field
added to that block later becomes fit identity by accident.

The boundary is narrow and real, and it is exactly the one the brief names: §11.1's argument
— a stale warm start lands at the wrong optimum — read one clause too far sweeps in the
**audit** settings, and then re-running a hysteresis audit at a different subsample size
invalidates the store it is auditing.

**Changed:** the payload is flat, blocks flatten to `block_field`, and the five settings are
five names in `FIT_RELEVANT_FIELDS`. The audit settings are a separate config block so the
flattening cannot gather them, and `tests/test_config.py` asserts a change to either moves
neither gate — with the warm-start test immediately above it as the positive control.

### (i2) — "`threads` moves neither hash" is a pure negative

Three of the brief's five tests are negatives: `threads` moves neither, `criteria` does not
move `fit_hash`, `candidates` moves nothing. **A mutation helper that silently failed to
apply its override produces exactly the same result as correct behaviour.**

**Changed:** every partition test shares one `_moved` helper, and the `threads` test asserts
in the same body that the identical wiring **does** move all three when applied to `seed`.

### (a) — the differential tests cannot see the config path itself

A flattening that prefixed every key wrongly, a payload that dropped a field, or a `load`
returning the same object regardless of its argument leaves every "field X moves hash Y"
test green.

**Changed:** `tests/test_config.py` carries hand-written canonical-JSON payloads and their
digests. **Its fit payload is byte-identical to `test_hashing.py`'s golden**, which is the
claim worth making: a config that comes off disk through pydantic and the flattening produces
the same payload as the hand-built mapping the hashing tests use.

### The goldens moved, and the reversal is now a test

Adding five fields moved all three `GOLDEN_*` constants. Re-derived by hand from the field
list and **verified by reversal**: deleting the five `warm_start_*` keys reproduces
`faf2d107bab48b06 / bb28cb8d4bffa049 / af313190251af95f` exactly, proving the separators, the
sort rule, the digest and the truncation are unchanged and only the field set moved.

`test_the_goldens_reverse_to_the_previous_constants` keeps that executable rather than leaving
it in a comment, because Task 3 does the same thing again for `geometry_hash` — and **the two
must not be batched.** One combined regeneration proves nothing about either.

### (c) — `load`'s exits, enumerated

Missing file; unrecognized suffix; TOML parse error; JSON parse error; JSON top level not a
mapping; a stamped key supplied; pydantic validation (missing required, unrecognized extra,
constraint violation); candidate expression malformed; unknown term kind. **Enumerated from
the source, never counted.**

### (a3) — two regimes declared without their features

- `screening` validates as a block so Task 4's refusal can name the missing engine
  specifically. The feature is Phase 4; the shape is here so Task 4 does not invent one.
- `Config.fit_hash()` returns `str | None` although **at Task 1 it is never None** —
  `data_uri` is still the fit-relevant stand-in for the data. Fixing the optional return now
  avoids every caller being written against `str` and needing revisiting at exactly the moment
  the None case starts happening.

### A finding the pre-flight did not predict: two default mechanisms, one of them silently dead

`hashing.CONFIG_DEFAULTS` and the pydantic field defaults now both supply `seed` and
`objective`. `normalize` computes `{**CONFIG_DEFAULTS, **config, ...}`, so **once pydantic has
filled them the config always carries them and `CONFIG_DEFAULTS` never applies to anything
that came through `load`.** If the two disagreed, the hashed value would be pydantic's and the
constant would be dead code that reads as authoritative.

`CONFIG_DEFAULTS` is not removable — it still applies to callers holding a payload and no
file, which is every test in `test_hashing.py`. **So the correct response is to pin the
agreement, not to delete either**, and there is a test that does.

### Bite checks

Five mutations against five different guards, and **one of them exposed a weak assertion in a
test written minutes earlier**:

| mutation | outcome |
|---|---|
| flattening drops the block prefix | 14 failures |
| `extra="ignore"` | **did not bite** — see below |
| candidate spec hashes sorted | positional test fails |
| `metamer_version` added to `FIT_RELEVANT_FIELDS` | 12 failures |
| `registry_version` no longer stamped | 51 failures |

**`pytest.raises(ValidationError, match="data_url")` PASSES UNDER `extra="ignore"`.** With the
extra field ignored, `data_uri` is simply missing, and pydantic renders the offered input in
its `input_value=` echo — so the typo appears in the message of an error that never diagnosed
it. **A message that quotes what you typed is not a message that diagnosed it.** The assertion
is now on `errors()[i]["type"] == "extra_forbidden"` and its `loc`.

That mutation also produced the second instance of the doubled-guard rule in as many tasks:
`extra="forbid"` catches the field that is **present** and unrecognized, `hashing._subset`
catches the one that is **absent** and required, and a single typo trips both. The two now
have **a test each**, which is what makes either mutation bite somewhere.

A weak assertion of my own in the same sitting: the warm-start parametrization asserted
`fit_moved == compat_moved`, which `(False, False)` satisfies — i.e. it passed against the
dropped-field defect it existed to catch. **A relation between two observations is not a
substitute for the observations**; the expected triple is now spelled out per case.
