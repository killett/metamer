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

---

## The allowlist source sweep (run 2026-08-11, after Task 1)

Five allowlist findings in five questions means `FIT_RELEVANT_FIELDS` was assembled at Task 16
**before the mechanisms that populate it existed**, so membership tracked what was known then.
One pass over the whole set is cheaper than five more discoveries.

**The question for each field, per the sharpened (a2):** what populates it, and is that source
independent of what the field claims to identify?

**The sweep's own finding is the sort.** The allowlist holds two kinds of field, and the
independence check applies to only one of them:

- **A REQUEST** — which variable, which objective, which seed, which criteria. Self-reported
  by definition, and that is correct: *the field is the request*. There is nothing else it
  could come from, and no independent source exists to check it against.
- **AN IDENTITY** — a claim about something that exists independently of the config: installed
  code, a registry, a dataset on disk. Self-report here is the defect.

**Only three of fourteen are identities.** That converts "expect a sixth finding" into a
bounded, enumerated list.

| field | populated by | kind | independent? |
|---|---|---|---|
| `variable` | user config | request | n/a |
| `signal_terms` | user config | request | n/a |
| `objective` | user config | request | n/a |
| `engine` | user config | request | n/a |
| `seed` | user config | request | n/a |
| `criteria` (compat only) | user config | request | n/a |
| `warm_start_enabled` | user config | request | n/a |
| `warm_start_coarse_stride` | user config | request | n/a |
| `warm_start_interpolation_rule` | user config | request | n/a |
| `warm_start_spiral_bound` | user config | request | n/a |
| `warm_start_tie_break` | user config | request | n/a |
| **`algorithm_version`** | `normalize`, from a hand-bumped constant | **identity** | **yes** — of the installed code, though hand-bumped means it can be forgotten, which its own docstring and `RELEASING.md` both state |
| **`registry_version`** | `normalize`, from `registry.REGISTRY_VERSION` | **identity** | **yes, since Task 1.** It was the user's config until then |
| **`data_uri`** | user config | **identity** — it stands in for the data | **NO.** Known-wrong in both directions since Q5; **Task 3 replaces it with `geometry_hash`**, populated by reading the opened dataset, which is independent |

**So the audit is closed except for the one field already scheduled.** `data_uri` is the last
self-reported identity in either allowlist, and Task 3 is what removes it.

**Two adjacent gates checked in the same pass, both clean and recorded as such:**

- **Per-candidate `spec_hash`** — the value Task 11's positional comparison uses. Computed by
  `ProcessSpec.spec_hash()` from the term structure, so it identifies a model by *being* a
  function of that model. Independent.
- **`machine_fingerprint(cpu_model, cores, total_ram_bytes)`** — takes its inputs as
  arguments, so it is self-reported *at the function boundary*. It reaches `run_hash` alone,
  which is **provenance and never a gate**, so a wrong fingerprint misreports and decides
  nothing. **Task 5 must supply those arguments from `core.machine`, not from the config**;
  noted here because that is the moment a self-reported machine could enter the calibration
  cache key, where it WOULD be a gate.

---

## Task 2 — the opener registry, the zarr opener, and stage 4a (audited 2026-08-12)

**Two of the brief's own statements are wrong, and both were found by running the numbers
rather than by reading.** That is the pre-flight's highest-yield move for the third time.

### (d) — the design doc requires the conversion rule and never states it

§13.6 says the conversion to decimal years is fit identity and that three calendars give
different answers for one timestamp. **It does not say what the formula is**, and two
reasonable formulas differ enough to matter:

| candidate | a calendar year measures |
|---|---|
| `year + (t − start_of_year) / (start_of_next_year − start_of_year)` | exactly 1.0, every calendar |
| `epoch + elapsed_seconds / (365.25 · 86400)` | 0.9993–1.0027 (Gregorian), 0.9993 (`noleap`), **0.9856 (`360_day`)** |

**Measured**, and the `360_day` row decides it: under `/365.25` a `360_day` calendar year is
1.46% short, so an `Annual` design column drifts 5.25 days per year and accumulates **0.72
years of phase over 50 years** — the harmonic is decorrelated from the season it models. The
design matrix carries `Annual` and `SemiAnnual`, and `360_day` is an ordinary climate-model
calendar, so this is reachable rather than hypothetical.

**Adopted: fraction of the actual year, evaluated in the timestamp's own calendar.** Stated in
one place, in `timeaxis.py`'s module docstring, under `ALGORITHM_VERSION`.

**Its cost is stated rather than hidden:** because a year is exactly 1.0, a Gregorian daily
axis has **two** distinct timesteps (1/365 and 1/366) where `/365.25` has one, so `F` and `Q`
are built twice per series per iteration instead of once. Measured on 20 years of daily data.

### (i) — MEASURED: the brief's unique-Δt test cannot fail as written

The brief asks for a test that the count is *"1 for a regular axis and large for one perturbed
by float noise."* **Neither half holds against the real function.**

`StateSpace.unique_dt` is tolerance-aware with `UNIQUE_DT_RTOL = 1e-9` applied per adjacent
pair. Measured on a 50-year monthly axis:

| axis | unique steps |
|---|---|
| month-start timestamps, real calendar | **6** |
| the same, mid-month | **8** |
| 20 years of daily timestamps | **2** |
| synthetic `2000 + arange(n)/12` | **1** |
| monthly perturbed at 1e-16 of value (float64 rounding) | **1** — collapses |
| monthly perturbed at 1e-12 of value | 36 |
| monthly perturbed at 1e-10 of value | 571 |

So: **a real "regular" axis gives 6, not 1** — calendar months are 28–31 days — and **float
noise does not inflate the count at all**, because the tolerance sits decades above float64
rounding at these magnitudes. The hazard the number exists to report is real but its trigger
is **sub-second jitter**: on a monthly axis the per-pair tolerance is about 2.6 ms.

Transcribing the brief's test verbatim would have produced a failing assertion, and **the
tempting fix is lowering `UNIQUE_DT_RTOL`** — which would destroy the `F`/`Q` amortization on
every axis in order to hide a number that is telling the truth about one. Both sides of the
crossover are now pinned so that the constant's role is explicit.

### (a) — the seconds-versus-datetimes test is blind to the convention

*"A seconds-since-1970 axis and a decimal-years axis produce the same result"* sends both sides
through the same converter, so **any uniformly wrong convention cancels exactly** — including
`/365.25`, and including an off-by-one year.

**Changed:** four hand-computed decimal years are the absolute anchor
(`2000-01-01 → 2000.0`; `2000-07-01 → 2000 + 182/366`; `2001-07-01 → 2001 + 181/365`, the leap
year visible in the axis; `2000-12-31T12:00 → 2000 + 365.5/366`), and the differential test is
kept as an additional check rather than as the check.

### (a3) — netCDF's seam is asserted, not intended

"Adding netCDF must be a registration, not a refactor" is impossible to verify by reading while
zarr is the only opener. **Changed:** a test registers a second opener under its own scheme and
drives the whole of `open_input` and `check_contract` through it. Mutating `open_input` to call
`_open_zarr` directly fails it. The registry is `core.registry.Registry`, so the entry-point
group comes free and a third-party opener is a package, not a patch.

### Two defects the tests caught on their first run

- **`type(sample)(year, 1, 1)` SILENTLY DROPS cftime's CALENDAR.** `cftime.datetime` carries
  its calendar as an *attribute*, not as a subclass, so reconstructing through `type()` yields
  a date on the **default** calendar — the denominator would be a standard year while the
  numerator was measured in a `noleap` or `360_day` one. Wrong on exactly the calendars the
  conversion exists to handle. `.replace()` preserves it and is spelled the same way on
  `datetime.datetime`.
- **A stage-4a helper was escaping as a bare `ValueError`.** `check_strictly_increasing` lives
  in `timeaxis`, which knows nothing about validation staging, so a duplicate timestamp raised
  `ValueError` rather than `InputContractError` — and Task 4 maps the staged type to exit code
  4, so a bare one would be an unhandled error instead. Now wrapped at the stage boundary.

### One defect found by running the code, which no test had asked for

**CF decoding CONSUMES `units` and `calendar` and files them under `.encoding`.** Reading
`.attrs` returns None for every successfully decoded axis — that is, for every axis this code
ever sees. Measured on a round-tripped store: `.attrs` gave None while `.encoding` carried
`days since 2000-01-01`. **A provenance field that is always empty records nothing**, and
nothing else in the system would have reported it.

### (d) — `cftime` is a dependency the packaging guard cannot see

Nothing under `src/` imports it; **xarray reaches for it to decode any non-standard calendar**,
and `noleap` and `360_day` are ordinary. `tests/test_packaging.py` scans `src/` for imports, so
it guards "imported but undeclared" and **this case is outside it**. Declared by hand in the
`batch` extra, with the limit stated in both places.

### Bite checks

Six mutations, six different guards, all bit: `/365.25`; `units` from `.attrs` only;
`np.unique(np.diff(t))` without tolerance; `steps < 0` instead of `<= 0`; `_open_zarr` called
directly instead of through the registry; `.astype(object)` on nanoseconds.

---

## Task 3 — `geometry_hash` (audited 2026-08-12)

Q5 settled the design, so this audit is about the ways a correct design gets built wrong.
**Two findings came from a mutation that did NOT bite, which is the more useful direction.**

### (g) — `canonical_json` accepts `np.float64` and refuses `np.int64`, which makes the trap asymmetric

Measured. `np.float64` subclasses `float` and passes; `np.ndarray` and `np.int64` are refused
by name. So **`list(coordinate_array)` works on a float coordinate and raises on an integer
one** — and `y`/`x` index coordinates are routinely integers. A fingerprint built that way
passes every test written against a float grid and fails on the first real store.
`.tolist()` converts uniformly; `list()` and `.tolist()` read as the same thing.

### (a) — every geometry test is differential

"A regrid moves it", "a value edit does not", "these two calendars differ" — all comparisons,
all blind to a `geometry_hash` that is uniformly wrong. **Changed:** the digest construction is
pinned against `hashlib` applied directly to `canonical_json`'s output, and the time component's
representation is asserted to be decimal years in a plausible range rather than merely to differ.

### (i2) — the limit and its control

*"A value edit at fixed geometry does not move the hash"* is the honest documentation of what
this component covers, and it is a pure negative — satisfied equally by a correct limit and by
a `geometry_hash` that returns a constant. Its control is the extent-preserving regrid through
the same components: `linspace(0, 10, 5)` against `[0, 1, 3, 6, 10]`, identical min, max **and
length**, different hash. That pairing is also the argument against summarizing coordinates.

### MEASURED: a mutation that did not bite, and what it taught

Mutating the time component from decimal years to `[str(v) for v in time.values]` **left every
test green**, including the two-calendar test written to catch exactly that.

**The reason is that decoding happens in the opener.** By the time `geometry_components` sees
the coordinate it is already `datetime64` or `cftime`, so *any* representation taken there is
post-decode and distinguishes calendars. The defect Q5 warns about — inheriting a dependency's
parsing by fingerprinting the attrs string — is guarded one layer up, by `calendar_of` reading
the decoded objects, and `tests/test_input.py` already covers it.

**So the reachable defect is a different one, and it needed a different assertion.** Decimal
years must be the component because:

- they move when the **conversion rule** moves, and the conversion is under
  `ALGORITHM_VERSION`, so a change to it must invalidate stored fits. A rendering of the
  timestamps would not move at all.
- `str()` of a datetime64 or a cftime date is a **repr**, and a repr is a library-version
  artefact — pre-flight (k), the same hazard that made `default=repr` a drifting hash at Task
  16.

The assertion that bites pins the representation: every entry is a `float` in `(1990, 2010)`.

**And the fixture had to be rebuilt to say anything at all.** Comparing a `datetime64` store
against a `cftime` store varies the raw representation as well as the calendar. The honest
fixture stores **bit-identical numbers** under `calendar="standard"` and `calendar="noleap"`,
so the raw arrays are indistinguishable and only the decoding differs.

### The run-hash degraded mode, found by the allowlist change breaking it

`run_payload` validated the full `FIT_RELEVANT_FIELDS` — "a config that cannot be fit-hashed is
not a run". The moment `geometry_hash` joined that set, **every `run_hash` call without an
opened input raised `KeyError`**, which turns §13.4's degraded mode into an error: `--explain`'s
most valuable use is a config with **no data staged yet**, sizing a run before moving 25 GB.

`STAGE_4A_FIELDS` is the exclusion, and it is an exclusion of *"not supplied by a config"*
rather than a loosening of *"must be specified"*. `fit_hash` and `compat_hash` return None
there; `run_hash` is a string. **The optional return type was declared at Task 1, two tasks
before it could happen**, so no caller needed revisiting when it started happening.

### When an allowlist changes, its guards must be re-pointed, not just re-run

`test_a_missing_allowlisted_field_is_refused` probed `data_uri`. After the demotion, a config
omitting `data_uri` hashes perfectly happily — so the test **would have gone on passing while
checking nothing**, asserting a real refusal about a field that no longer has the property. It
now probes `geometry_hash`, and asserts as its counterpart that `data_uri` really is optional
to both gates.

### The reversal is a chain, one hop per change

Two allowlist changes landed a day apart. `_HISTORY` walks them newest-first — undo
`geometry_hash → data_uri`, check against the 2026-08-11 constants; then drop the warm-start
fields, check against the 2026-08-10 ones. **Collapsing them into one transform would give two
ways to be wrong that cancel**, which is the whole thing a reversal exists to rule out.

Verified: `1eb1fd731b4ae8d6 / d368e07b5f99efe9 / 0b82f20c43f2f378` reverse one hop to
`1de18c706b69c39e / cc099be86aca999b / b89d484190d5d0af`, and those reverse one hop to
`faf2d107bab48b06 / bb28cb8d4bffa049 / af313190251af95f`.

### The audit's last row is closed

`data_uri` was the final self-reported identity in either allowlist — a value claiming to
identify the data, supplied by the config. Every component of `geometry_hash` is read from the
opened dataset. **The allowlist source sweep is now closed with nothing outstanding.**

### Bite checks

Five mutations, four bit immediately: coordinates summarized as min/max/len; `source_dtype`
constant; `list()` for `.tolist()`; `data_uri` restored to the allowlist. The fifth is the
non-biting one recorded above, and it is the finding.

---

## Task 4 — validation staging, exit codes, and `python -m metamer` (audited 2026-08-12)

The brief is a structure task, so the audit is mostly about **whether the structure it
describes can exist as described**. Two of its own clauses contradict each other, one of the
checks it lists has no config field to fire on, and two of the five exit codes collide with
codes that Python and argparse produce for unrelated reasons.

### (f) — "layer 3 needs no data" and "layer 3 carries the identifiability lint" cannot both hold

`lint(spec, sampling_interval)` takes a **median observation spacing** and **raises** when it
is not finite and positive — deliberately, because a diagnostic that reports "clean" because
it could not run is worse than one that stops (Task 15). A sampling interval is a property of
the data. So the lint cannot run in a data-independent layer.

**This is the design doc's own contradiction, not the plan's.** §13.2 heads layer 3
"**Semantic, data-independent**" and lists "identifiability lint (§4.8), as a warning" inside
it. PROGRESS's Task 4 handoff repeats both halves.

**Resolved by splitting on what fails rather than on when it runs.** Layer 3 is the layer of
*config-internal* faults; every layer-3 check that can **fail** — screening, per-point
regressors, duplicate candidates, criterion membership, thread limits — runs before anything
is opened and needs no data. The lint is a **warning**, it cannot move the exit code, and it
therefore runs after stage 4a with the sampling interval stage 4a already computed. That
ordering is what keeps the attribution honest: a run with both a bad config and bad data must
report the config, and it does, because every layer-3 *failure* is upstream of the open.

`ContractReport` gains `median_dt`, computed where the decimal-year axis already exists —
measure in the phase that can.

### (a3) / (d) — the per-point regressor refusal has no config field to fire on

The brief requires layer 3 to refuse a per-point regressor "**naming the field** and both
tile sizes". `Config` has no such field. Task 1's (a3) sweep declared the `screening` regime
as a block and **did not declare this one**; design doc §13.4 says the config field ships
while the feature is refused, and §11.4 says the regime "is expressed inside `signal_terms`"
so that it reaches `fit_hash` by construction rather than through a sibling field.

Without a declaration the refusal is unreachable, its test is vacuous, and (a3)'s own
standard — "a field, a formula branch, and an explicit refusal with a test, not a comment
promising a hook" — is failed with two of the three present: the formula branch
(`memory.per_point_design`) and the narrowing seam (`signal.DesignInfo.per_point`) both
already exist.

**Changed:** `config.model` gains `PER_POINT_TERM_PREFIX = "regressor_field:"` and
`Config.per_point_regressors()`. The declaration lives inside `signal_terms`, which is
already fit-relevant, so no new hashed field is created and (a2) has nothing new to classify
— `signal_terms` is a REQUEST, self-reported correctly. The spelling is provisional and says
so; what is not provisional is that the declaration must sit inside `signal_terms`.

### MEASURED: the brief's 338 and 186 are path A's numbers, and the adopted path is B

Recomputed 2026-08-12 from `memory.resident_bytes_per_series` and `memory.tile_side` at
§9.4's worked example (d=3, k_β=4, p=4, N=630, M=12, 1 GB):

| backend | shared X | per-point X | tile side | area ratio |
|---|---|---|---|---|
| `NUMPY_BATCHED` (path A) | 8 722 B | 28 882 B | **338 / 186** | 3.30× |
| `COMPILED` (path B) | 7 634 B | 27 794 B | **361 / 189** | 3.65× |

The brief, PROGRESS and design doc §13.4 all quote 338/186 and "3.3× in tile area" **without
naming a backend**, and the spike adopted path B by ≥3×. So both the tile sides and the
headline ratio are backend-specific, and the quoted pair is the one for the backend `fit()`
actually defaults to today (`KalmanEngine`, i.e. `NUMPY_BATCHED`).

**Changed:** the refusal computes its numbers live from `memory`, at the worked example's
parameters, and **names the backend and the parameters in the message**. Nothing is
hard-coded, so a change to the formula moves the message rather than dating it.

### (c) — an unknown candidate kind raises `KeyError`, is LAZY, and Task 1's enumeration says otherwise

Measured. `load()` does **not** validate candidates: `parse_candidate` runs only when
`process_specs()` or `candidate_spec_hashes()` is called. And an unknown kind comes out of the
kernel registry as a **`KeyError`**, not a `ValueError`:

    load OK -> ('aic', 'not_a_criterion') ('nosuchkind',)
    lazy raise: KeyError "kernel_registry: unknown key 'nosuchkind'. Available: matern12, matern32, white"

Task 1's audit listed "candidate expression malformed; unknown term kind" among **`load`'s**
exits. They are not `load`'s exits, and one of the two is not a `ValueError`. A layer-3 pass
catching `ValueError` alone would let an unknown candidate kind escape as an unhandled
exception — which Python reports as **exit code 1**, i.e. "completed with failures above
threshold" in this taxonomy. Both types are caught and staged.

Placement is nonetheless right: candidate parsing is semantic, so layer 3 is where it belongs.

### (c) — an unknown criterion passes layers 1 and 2 today

`Config.criteria` is `tuple[str, ...]` with no membership constraint, so `criteria =
["aic", "not_a_criterion"]` loads clean and would fail at ranking time, inside a tile loop,
ten hours in. This is the reachable half of §13.2's "criterion/objective compatibility" row:
TIC and CV are the row's examples and neither is implemented, and every implemented criterion
is computable under both ML and REML. Refused at layer 3, naming the offending value and the
implemented set. **Deliberately not moved into the pydantic model**: §13.2 places it at layer
3, the message can then name the objective, and constraining the field would change what
reaches `compat_hash`.

### TWO EXIT-CODE COLLISIONS, BOTH FROM CODE NOBODY WRITES

- **argparse exits 2 on a usage error, and 2 is "aborted early".** `python -m metamer` with no
  arguments would report the code that means a run started and stopped, from a run that never
  started. **Changed:** the parser's `error()` exits `ExitCode.CONFIG_INVALID` (3), and a
  subprocess test pins it — a bare invocation must be 3, never 2.
- **Python exits 1 on an unhandled exception, and 1 is "completed with failures above
  threshold".** Unfixable inside the taxonomy, which has no internal-error code. It is
  harmless in 2a because **1 is unreachable here**, so any observed 1 is a crash; it stops
  being harmless in 2e, when 1 acquires a producer. Recorded in PROGRESS as a 2e requirement:
  a test asserting exit 1 must also assert the absence of a traceback.

### (c) — `load`'s ValueError does not say which layer raised it

`_read` raises `ValueError` for an unrecognized suffix and for a parse failure (layer 1);
`load` raises a bare `ValueError` for a supplied stamped key (layer 2 — `extra="forbid"` would
catch the same key as `extra_forbidden` if the pre-check were not there). The two are
indistinguishable by type, so a runner cannot name the layer correctly. Both map to exit code
3, so the **code** is unaffected and only the **message** would be wrong — which is exactly
what "each layer names itself" exists to prevent.

**Changed:** `config.model` gains `StampedKeyError(ValueError)`. One line, no behaviour
change, and it keeps the staging vocabulary out of `config` — the layer enum stays in
`batch.validation`, which is where layer 4 already lives.

### (i2) — three pure negatives in this task, each given its control

| the negative | the control |
|---|---|
| a clean config raises no layer-3 error | each of the five layer-3 checks raises on its own trigger |
| a matching thread-limit table raises nothing | a mismatched table raises a layer-3 error naming the library |
| `observed_thread_limits=None` skips the check | the same call with a table does not skip it |

The third is the one that would otherwise ship silently: until Task 5 supplies the
observation, the production runner passes `None` and the check does nothing. That is stated
in the docstring and pinned by a test, so the vacuity is a recorded state rather than a
belief.

### (k) — an exit code is a process property, and so is the final line

Every exit-code assertion runs `python -m metamer` in a subprocess and reads `returncode`.
Calling `main()` in-process tests the mapping function, which is worth doing separately and is
not the same claim: `sys.exit` semantics, argparse's own exits and an unhandled traceback are
all invisible to an in-process call.

### (a) — every exit-code test compares against an absolute integer, but the LAYER can still cancel

A runner that reported layer 3 for everything passes any test that only asserts "an error
naming a layer". **Changed:** the layer-3 and layer-4 tests assert **different** codes for
**different** constructed faults, and one test constructs a config that fails layer 3 **and**
stage 4a at once and asserts it reports 3 — the ordering claim, which no single-fault test can
express.

### (g) — signature binding

Checked against the committed sources, not against the brief: `config.load(path)`,
`Config.fit_hash(geometry_hash=None)` / `compat_hash` / `run_hash(machine=None,
geometry_hash=None)`, `Config.candidate_spec_hashes()`, `open_input(uri, variable)`,
`check_contract(handle) -> ContractReport`, `geometry_components(handle, variables=None)`,
`geometry_hash(components)`, `lint(spec, sampling_interval) -> list[Finding]`,
`memory.resident_bytes_per_series(backend, d, k_beta, p, n_time, n_models, per_point_design)`,
`memory.tile_side(budget_bytes, per_series_bytes)`. All bind. **A clean (g) is not a
pre-flight** — every finding above is one (g) cannot see.

### (f) — one stale docstring in the tree, from Task 3

`Config.data_uri`'s attribute docstring still reads "**Fit-relevant until Task 3**, which
replaces it with `geometry_hash` and demotes it to provenance. The gate is wrong in both
directions today". Task 3 landed; `to_payload`'s docstring three methods below already says
`data_uri` is provenance only. Corrected.

### The engine seam is NOT wired here, deliberately

PROGRESS's Task 4 handoff requires the engine to stay injectable. Task 4's runner fits
nothing, so an `engine=` parameter on `run()` would be a parameter no test could make bite —
"a comment promising a hook" in argument form. It is stated in `run()`'s docstring and carried
forward to **Task 9**, the first task that fits, where the raising stub can actually be
delivered through it and the assertion can fail.

### Bite checks

**22 mutations, 22 caught**, against `tests/test_validation.py`, `tests/test_runner.py` and
`tests/test_input.py`. The battery is grouped by what it attacks rather than by file:

| what was mutated | outcome |
|---|---|
| screening refusal deleted | 3 failures |
| per-point refusal deleted | 3 failures |
| per-point message quotes the `COMPILED` backend | 2 failures |
| tile sides hard-coded at the pre-streaming 171 | 1 failure |
| duplicate-candidate check deleted | 1 failure |
| duplicates compared by config string rather than by spec hash | 3 failures |
| candidate resolution catches `ValueError` only | 1 failure |
| criterion membership check deleted | 2 failures |
| thread check not wired into layer 3 | 1 failure |
| the `None` guard deleted, so an unobserved run dereferences None | 1 failure |
| layer-1 `ValueError` clause placed above the schema clauses | 2 failures |
| the lint promoted from warning to refusal | 11 failures |
| unusable sampling interval attributed to layer 3 | 1 failure |
| layer 3 moved below the open | 1 failure |
| fingerprint taken before the contract check | 1 failure |
| gates computed without the geometry (the degraded mode, always) | 2 failures |
| memory-budget override applied with `model_copy`, i.e. unvalidated | 1 failure |
| the lint never called | 1 failure |
| `median_dt` taken as span / `n_time` | 1 failure |
| argparse usage error left at its own exit code 2 | 1 failure |
| every staged failure mapped to exit code 3 | 3 failures |
| layer 4 loses its prefix on stderr | 1 failure |

**ONE MUTATION SURVIVED ON THE FIRST PASS AND IT WAS NOT A DEFECT.** Replacing
`if observed is None: return` with `if observed is None: observed = {}` left everything green
— correctly, because the two are the same behaviour: an empty table has no offenders. That is
none of (e)'s four causes; **it is a mutation that is not a defect at all**, which is a fifth
thing a survivor can be and is worth naming. The mutation that expresses the reachable defect
is deleting the guard outright, so `observed.items()` runs against `None` — and that one bites.
**Diagnose the survivor before writing a test for it**: a test written to catch the first
version would have been a test of an equivalence.

### MEASURED: the ordering test had to be rebuilt before it could bite

The first version of *"no hash is computed when the input contract fails"* used a
two-dimensional variable. **Both orderings raise `InputContractError` there**, so the assertion
passed against a fingerprint-first runner and the section 13.7 claim would have been untested
while looking tested — (i) at its purest, and the same shape as Task 3's non-biting mutation.

The fixture that discriminates is a **bare numeric time axis with no `units`**: contract-first
gives `InputContractError` naming the decode failure, fingerprint-first gives a bare
`TypeError` out of `to_decimal_years`, which is unstaged and reaches the user as a traceback
and exit code 1. Measured both orderings before rewriting the test.

### The stale number this audit found in PROGRESS itself

The cold-start summary said **693 collected** and the same file's "Tests:" bullet said **692**,
twelve lines apart. Measured: 693 before this task. **A recorded measurement carries its
measurement date, and two undated copies of one measurement is how the drift starts.** There is
now one number, and it is dated.
