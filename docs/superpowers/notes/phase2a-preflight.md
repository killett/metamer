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

---

## Task 5 — the thread budget (audited 2026-08-12)

Every finding below came from **running the instruments**, not from reading the brief. The
brief's model of `threadpoolctl` — "it sets and reports, record every library it finds" — is
right in intent and wrong about what "finds" means at the moment the check runs.

### MEASURED: numba's threading layer is INVISIBLE until something parallel has run

`threadpool_info()` immediately after `import numba` reports **OpenBLAS only**. `libgomp`
appears only after a `prange` function has actually executed:

    bare                -> []
    after numpy         -> [openblas 4]
    after import numba  -> [openblas 4]
    after a prange call -> [openblas 4, openmp 4]

**The layer-3 check runs at startup, which is exactly when the layer is not there.** So the
brief's check, implemented literally, would report "every library observes 1" while the
library the fit phase is about to use had not been loaded — and `threadpool_limits` does not
retroactively limit a library loaded after it. **Name-is-not-a-gate, in the instrument this
time**: a determinism precondition confirmed against a table that does not yet contain the
thing whose determinism is at stake.

**Changed:** the observation calls `numba.get_num_threads()` first, which **launches the
threading layer as a side effect** — measured: `libgomp` is present in `threadpool_info()`
immediately afterwards — so the table the check reads covers what the fit phase will use.
Public API, not `numba.np.ufunc.parallel._launch_threads`.

### MEASURED: `threadpool_limits(1)` does not change `numba.get_num_threads()`

Inside `threadpool_limits(limits=1)`, `threadpool_info()` reports `openblas 1, openmp 1` while
`numba.get_num_threads()` still reports **4**. They are different quantities: threadpoolctl
caps the OpenMP runtime's pool, numba's mask is how many slices a `prange` is cut into, and a
`prange` reduction reassociates over **numba's** count. So a check reading threadpoolctl alone
certifies a determinism precondition that numba is not subject to.

**Changed:** numba's limit is **set and observed through numba** and carried in the same table
under its own key, beside the threadpoolctl entries. This is the design doc's "a precondition
that holds for OpenBLAS while MKL runs multithreaded is not a precondition that holds" —
occurring *within one process, between two instruments of the same OpenMP layer*, which is
sharper than the cross-library case it was written for.

### MEASURED: a genuine, unmocked observed-vs-requested mismatch exists, and the two libraries fail differently

Requesting 1000 threads on this 4-core machine:

    numba.set_num_threads(1000)              -> ValueError: The number of threads must be
                                                between 1 and 4
    threadpool_limits(limits=1000)           -> openblas 128, openmp 1000

**OpenBLAS silently clamps to its build-time `NUM_THREADS=128`.** So one library refuses
loudly and the other lies quietly, and **only the second is the dangerous one** — it is
precisely the shape the check exists to catch, and it needs no mock to construct. That is the
fixture: (i) is satisfied by a real machine limit rather than by a patched observer.

numba's raise must be **staged as layer 3**, or an over-large `threads` in a config is an
unhandled `ValueError`, i.e. exit code 1 — the (k2) alias again, one task later.

### (a2) — `machine_fingerprint` is an IDENTITY, and `platform.processor()` returns `''` on Linux

Classified before checking, per the rule. `machine_fingerprint` answers "what machine is this",
so it is an **identity**: it must be populated by reading the machine. Today nothing in `src/`
populates it, and its three arguments are supplied by the caller — the same shape as
`registry_version` before Task 1.

**Measured on this box:** `platform.processor()` is `''`, `platform.machine()` is `'x86_64'`,
`/proc/cpuinfo`'s model name is `'Intel(R) N95'`, `psutil.cpu_count(logical=False)` is 4,
`psutil.virtual_memory().total` is 16 535 728 128.

**So the obvious source fails (a2)'s third fact: a change in the thing identified does not move
the field.** `cpu_model=platform.processor()` gives `''` on *every* Linux box, so every Linux
machine shares a fingerprint that differs only by core count and RAM. Harmless while the
fingerprint reaches `run_hash` alone; at §11.4's calibration cache it is a gate, and two
different CPUs sharing a key means one machine's bytes-per-series is reused on another against
a hard RAM constraint. **Changed:** `core.machine` reads `/proc/cpuinfo` on Linux and
`sysctl machdep.cpu.brand_string` on macOS, falls back to `platform.processor()` then
`platform.machine()`, and **raises rather than returning an empty string** — an identity that
cannot distinguish anything is worse than an error.

### (d) — the brief does not say how the per-library table is KEYED, and the obvious key loses entries

`{entry["internal_api"]: entry["num_threads"] for entry in threadpool_info()}` silently drops a
second library with the same `internal_api`, and **numpy's OpenBLAS beside scipy's is the
ordinary case** on a pip-installed stack. A dropped entry is a library whose limit is never
checked, in a check whose whole point is per-library coverage.

Measured here: `openblas` (`libopenblas`) and `openmp` (`libgomp`) — one entry each, so the
collision is **not reachable in this environment**. The keying is still done by a function that
disambiguates with the library's filename and the table is built from a list, so the guard is
tested by handing that function a constructed two-OpenBLAS list rather than by waiting for an
install that has one.

### (a) — the assembly-concurrency clamp only ever LOWERS W, and that is the invariant

`W = clamp(1, assembly_bytes // chunk_bytes, T)`. The upper clamp is a thread count, so read
carelessly this is "concurrency derived from core count", which §11.1.1 forbids. It is not:
clamping by `T` only ever reduces `W`, so `W * chunk_bytes <= assembly_bytes` holds regardless
of `T`, and **peak RAM stays derivable from the budget alone**.

**That is the assertion, not "W equals the expected number".** A test comparing `W` against a
recomputed clamp shares the implementation's derivation path — (j) — and would pass against a
formula that multiplied by core count in both places. The test asserts the **bytes** bound
across a sweep of `T`, which is the property §11.1.1 actually states.

### (c) — "one owner at a time" is prose that nothing enforces

The brief and §11.1.1 both state that assemble and fit never overlap. Nothing in the tree makes
that false-able, and the phase that would violate it does not exist until Tasks 6 and 9 — so it
would ship as a sentence, and the first prefetch optimization would silently break it while
every test stayed green.

**Changed:** the budget hands out phases through a context manager that **raises on overlap**
and accumulates elapsed seconds per phase. That makes the invariant executable now and makes
§11.1.1's *"record the ratio, because if it inverts the decision needs revisiting and nothing
else would show it"* a recorded quantity rather than an instruction to a future author.

### (k) — thread limits and numba's mask are PROCESS-GLOBAL, and a test that sets them leaks

`numba.set_num_threads` has no context-manager form and persists for the process, so a test
that lowers it changes every later test in the same pytest session — the same class as the
`run_spike` allocation that raised the session watermark and failed a test in another module.
The budget restores both on exit, and the tests assert the restoration rather than assuming it.

### (g) — signature binding

`hashing.machine_fingerprint(cpu_model, cores, total_ram_bytes)`,
`Config.run_hash(machine=None, geometry_hash=None)`,
`batch.validation.check_thread_limits(requested, observed)` and
`batch.run.run(..., observed_thread_limits=None)` all bind. The last two are Task 4's, and this
task's job is to make the second argument non-vacuous.

### Bite checks

**22 mutations, 22 caught** — after **three survivors were diagnosed rather than accepted**, and
each was a different one of (e)'s causes.

| what was mutated | outcome |
|---|---|
| numba's layer never launched before the table is read | 1 failure |
| numba's mask reported as the OpenMP entry | 1 failure |
| keying collapses two libraries with the same api | 1 failure |
| disambiguation applied unconditionally | 1 failure |
| numba's limit set but threadpoolctl's not | 1 failure |
| threadpoolctl limited but numba's mask left alone | 1 failure |
| the budget does not restore numba's mask | **survived first** — see below |
| numba's over-request `ValueError` escapes unstaged | 1 failure |
| the phase guard never refuses an overlap | 1 failure |
| the phase guard is one-shot rather than re-entrant | 1 failure |
| no phase seconds accumulated | 1 failure |
| an unmeasured ratio reported as infinity | 1 failure |
| assembly concurrency taken straight from the core count | 1 failure |
| the clamp written with `max` where `min` belongs | 1 failure |
| the floor of one dropped, so a huge chunk gives zero workers | 1 failure |
| a zero chunk size divided rather than refused | 1 failure |
| cpu model taken from `platform.processor()` | 1 failure |
| cpu model dropped from the fingerprint | 1 failure |
| logical cores reported as physical | **survived first** — see below |
| the run goes back to passing `None` for the observation | **survived first** — see below |
| the report carries the request instead of the observation | 1 failure |
| the machine fingerprint never reaches `run_hash` | 1 failure |

**Survivor 1 — (k), a delta whose baseline is set by history outside the test.** The restore
test read `before = numba.get_num_threads()`. The mutation makes an *earlier test in the same
module* leave the mask at 1, so `before` reads 1, the budget sets 1, and nothing moved. Fixed by
pinning the baseline explicitly: set the mask to 2, run the budget at 1, assert 2 came back.
**The memory module documents this exact hazard in capitals and it recurred in a different
subsystem** — documentation does not constrain the next author.

**Survivor 2 — (i), the host cannot express the defect.** `logical=True` is indistinguishable
from `logical=False` on a box with no SMT, and this one reports 4 and 4. Fixed the way the
threadpool-keying collision was: the choice moved into `machine.choose_core_count(physical,
logical)`, a pure function exercised with the inputs an SMT machine would supply. **A guard that
only a different machine can test belongs in a function that takes the machine's numbers as
arguments.**

**Survivor 3 — no test protected the guard.** `report.thread_limits` is built from the
observation whether or not layer 3 was given it, so a run that observes, records, and then hands
`None` to `check_semantics` produces an identical report. The claim needed a test where the
check *fires*: `run(..., observed_thread_limits={"openblas": 99})` must raise at layer 3.

### MEASURED after implementation: `bench/` leaks numba's mask, and it silenced a test

`bench/references.py` and `bench/spike.py` call `numba.set_num_threads` and never restore it.
`test_bench.py` sorts before `test_threads.py`, so by the time the thread tests ran in the full
sweep **the process mask was already 1** — and a skip guard written as "skip if fewer than two
threads are available" turned the sharpest test in the module into a silent no-op. It passed in
isolation every time. **A silent skip in a diagnostic is the worst available failure**, and this
is the second instance in the project.

**Recorded, not fixed in passing.** The honest fix is for `bench` to acquire its threads through
`batch.threads.thread_budget`, and it cannot: `bench` sits under `metamer.bench` beside `core`,
while the budget is batch-layer because `threadpoolctl` is a `[batch]` dependency and
`metamer.core` must stay importable without it. That is a layering decision, not a two-line
change, and pinning a contract in passing inside a task about something else is what this
project keeps paying for.

### MEASURED: observing numba's limit costs about 2.6 s of process start-up

`python -m metamer` over a 24 x 2 x 3 fixture: **21.4 s cold, 6.4 s and 8.4 s warm**, against
2.4 s for `python -c "import numba; numba.get_num_threads()"` through the same `pixi run`
wrapper. Breakdown in one process: importing `batch.run` 5.25 s, importing numba 2.59 s,
launching the threading layer 0.06 s, the first `run()` 9.57 s and every later one 0.03 s — so
the cost is imports and page cache, and **Task 5's share is numba's import on a path that did
not previously import it.**

Worth stating rather than absorbing: for a ten-hour fit this is noise; for a validate-only
invocation it is most of the wall time. It is not deferrable — the check is layer 3 and a
precondition observed after the work is not a precondition — but Phase 5's `validate --explain`
should know that its own start-up is dominated by a check it needs.

The full sweep went **298 s to ~500 s**, most of it in `test_runner.py`'s subprocess tests, which
now pay that start-up per invocation.

### Post-acceptance: the bench leak fixed, and open question 12 closed

Both were carried out after Task 5 was accepted, on the user's direction, and both are
recorded here because they changed code rather than only notes.

**The bench leak, narrow fix.** `bench/references.py` and `bench/spike.py` now restore numba's
thread mask in a `try/finally` around the point where they set it. That requires nothing from
`core` and no new dependency, and it explicitly does **not** route `bench` through
`batch.threads.thread_budget` — the layering question (bench sits beside `core`, which must stay
importable without `threadpoolctl`) is recorded separately as owed work. `run_spike`'s cell sweep
moved into `_sweep_cells` only so one `try/finally` can wrap the whole sweep instead of each
cell. **A third defect fell out of the same reading:** the report's `numba_threads_available`
read `get_num_threads()`, i.e. whatever the process last set — including by an earlier cell of
the same sweep — so on a second sweep in one process it recorded a number that was merely
current. It now reads `NUMBA_NUM_THREADS`, the ceiling, which is what "available" means. Three
guards, **3/3 mutations bite**.

**And the actual defect was the skip guard, not the leak.** A guard whose condition is set by
test ordering is unfalsifiable: the leak made it skip, but any future leak would too. Both skip
guards now set an explicit mask and compare against it. **A test that cannot fail is worse than
a test that does not exist, because it is counted.**

**Open question 12, closed.** The probe specified in `PROGRESS.md` — vary the parent's current
RSS and its watermark independently, then spawn — gives an unambiguous answer, reproduced three
times: **the child inherits the parent's watermark**, and a parent that allocated 400 MiB and
**freed** it still hands its child 493.3 MB while its own current RSS is back at 74.3.

The corollary was not in the question and is what reconciles the project's two conflicting
readings: **the inheritance does not compound.** `peak_rss_bytes()` returns
`max(inherited, own high-water)` and a child inherits **only the second term** — measured across
three generations, a middle process that allocates nothing reports 493.1 MB while its own child
reports 74.1 MB. The 2026-08-10 observation of a probe reading 454.8 MB whose child reported
84.6 MB is that rule, not a contradiction.

**The intermittent test is gone rather than loosened.** Its baseline was the pytest session's
watermark. The replacements spawn every process they measure **behind a bare launcher** — a
process importing nothing large, whose own high-water is a bare interpreter — so the controlled
parent starts from a known floor whatever the session allocated. **The launcher is the fix that
the newly-measured non-compounding rule made available**, which is the useful shape here: the
contract was not only recorded, it was immediately load-bearing.

Writing it also caught an assumption of my own. The first version asserted
`small_child == small_peak`; it fails, because the small parent is spawned by pytest and so
*reports* the session's watermark while its child gets only the 74 MB it generated itself. **The
non-compounding rule showing up inside the test that was written to establish it** is recorded
in the assertion rather than smoothed over.

macOS is untested and stays under open question 10, which already owns the decision about what
RSS accounting should mean there.

---

## Task 6 — tiling (audited 2026-08-12)

Two of the brief's own bullets cannot both be satisfied literally, the design doc carries the
superseded tile formula in the section this task would read, and the read-amplification metric
has a units trap that would let it report a value below 1.

### (f) — THE DESIGN DOC CARRIES THE SUPERSEDED `tile_side` FORMULA IN §11.1, WHICH IS THE SECTION THIS TASK READS

§11.1's tiling bullet still says:

> Derive a square spatial tile from a byte budget:
> `tile_side = sqrt(block_bytes / (n_time × itemsize))`.

§9.4 says of exactly that expression: *"The prompt's `tile_side = sqrt(block_bytes / (n_time ·
itemsize))` counts only the float64 data and therefore **overestimates**"* — 445 against 339
shared and 186 per-point. §2.5 then quotes `tile_side ≈ 445` from it. **Three sections, two
answers, and the one an implementer of this task opens first is the wrong one.** Third instance
of this cascade, after `n_eff_*`'s `[y,x]` versus `[y,x,m]` and the output-slot `+2` versus `+4`.

The plan's Task 6 brief is correct (`resident_bytes_per_series`), so **transcribing the plan
would have been safe and reading the design doc would not** — which is the reverse of the usual
direction and worth recording. §11.1 amended; §2.5's 445 annotated rather than rewritten,
because that section is about chunk arithmetic and its conclusion does not move.

**And `resident_`, never `bytes_per_series`.** The model and the resident figure agree to 0.5%
today and that is a measurement, not a guarantee. Recomputed 2026-08-12: 8682 model against
8722 resident, tile side 339 against **338**.

### THE BRIEF'S OWN TWO BULLETS CONFLICT, AND THE NUMBERS SAY WHICH WINS

> - **A tile is `ds[var].isel(y=…, x=…).load()`.**
> - **float32 → float64 conversion per chunk during assembly**, so both full representations
>   never coexist.

One `.load()` over the whole tile materializes the **entire** float32 block, and casting it
afterwards has both full representations alive at once — which the second bullet exists to
forbid. Measured at §9.4's worked example (`tile_side` 338, N=630): the float32 tile is
**288 MB** and the float64 tile **575 MB**, so the one-call form peaks at **863 MB against
575 MB**, a **50% overshoot of the data term** against a budget the design doc calls hard.

**Resolved in favour of the second bullet**, which carries the reason: the tile is assembled by
`.isel(...).load()` over **chunk-aligned sub-blocks**, cast into a preallocated float64
destination, so at most one chunk's float32 is alive. Still no dask, still one tile at a time,
still analytic. Reported as a deviation from the brief's literal first bullet.

### MEASURED: the read-amplification metric has a units trap that can report less than 1

A counting store wrapper on a 16x16 grid with 4x4 chunks (random float32, so barely
compressible):

    tile y[2:6] x[2:6]  -> 4 chunk fetches, 3112 store bytes, 768 bytes used
    tile y[0:4] x[0:4]  -> 1 chunk fetch,    778 store bytes, 768 bytes used

The ratios are 4.05 and 1.01 where the true amplifications are 4 and 1. **The store's bytes are
COMPRESSED and the tile's bytes are DECOMPRESSED**, so dividing one by the other measures
compression as well as amplification — and on a compressible variable it would report a value
**below 1**, which is meaningless for a metric defined as bytes read over bytes used.

**Changed:** amplification is computed from chunk geometry in decompressed units on both sides,
and the counting store is used as an **oracle over the set of chunks fetched** rather than over
bytes — arithmetic on index ranges against observed store keys, which share no construction (j).

### (i) — MEASURED: A FIXTURE OF ZEROS READS NOTHING AT ALL

The first version of the probe used `np.zeros`. Zarr does not write a chunk equal to the fill
value, so **every read was served from the fill value and the store was never touched**: 0 bytes
read, 0 keys fetched, and a correct-looking 768 bytes used. A read-amplification test on a zero
fixture cannot express its own subject. The fixture is random float32.

**A second instrumentation trap in the same sitting:** subclassing `zarr.storage.LocalStore` and
passing the instance to `xr.open_zarr(store)` records nothing — the reads do not go through the
subclass. Patching `LocalStore.get` for the duration of the test does work, and is what the
oracle does.

### (a2) — nothing this task produces is fit identity, and that is a claim to assert

Classified before checking. `tile_side` derives from `memory_budget_gb`, which is
**run-relevant only**; read amplification is a **measurement of this run**, so it is provenance
and belongs in neither allowlist. §11.3's guarantee is that output is bitwise identical
*regardless of memory budget and tile size*, so **the moment any tiling quantity reached
`fit_hash` the hash boundary would be conceding the guarantee does not hold** — the same
argument that keeps thread counts out. Asserted rather than assumed: two runs at different
budgets must produce the same `fit_hash` and different `run_hash`.

### (c) — tile coverage is the one place an "off by one" is silent

A tile grid that misses a row writes a store with an unwritten seam; one that overlaps writes
some points twice. Neither raises, both produce a complete-looking store, and the completion
bitmap is per tile so it cannot see either. **Enumerated rather than counted**: the test
accumulates every (y, x) the grid yields and compares the multiset against the full grid, so a
miss and a duplicate are distinguishable — asserting the *number* of tiles would catch neither.

### (a3) — prefetch is deferred with its cost, and the phase guard now enforces it

Prefetching tile `N+1` during tile `N`'s fit **doubles the tile term in the memory formula**.
Task 5's `ThreadBudget.phase` raises on overlap, so the deferral is enforced rather than
documented — the first attempt to assemble during a fit fails a test instead of silently
doubling peak RAM.

### (g) — signature binding

`memory.tile_side(budget_bytes, per_series_bytes)`,
`memory.resident_bytes_per_series(backend, d, k_beta, p, n_time, n_models, per_point_design)`,
`batch.threads.ThreadBudget.phase(Phase)`, `batch.input.InputHandle.dataset`,
`ContractReport.n_y/n_x/n_time`. All bind.

### Bite checks

**10 mutations, 10 caught** — after one survivor which was a genuine coverage gap.

| what was mutated | outcome |
|---|---|
| grid misses the ragged edge | 1 failure |
| grid overlaps by one row | 1 failure |
| a zero side yields nothing instead of raising | 1 failure |
| budgeted against the model rather than the resident figure | 1 failure |
| amplification computed from the request | 1 failure |
| the edge chunk counted full rather than clipped | 1 failure |
| chunk shape assumed to be the whole array | 1 failure |
| a store with no declared chunking is guessed at | **survived first** — see below |
| assembly loads the whole tile in one span | 1 failure |
| assembly transposes the tile | 1 failure |

**The survivor was (e)'s first cause — no test protected the guard**, and the condition is
reachable: an opener returning an in-memory dataset produces a handle whose variable has no
`encoding["chunks"]`, which is what any non-chunked backend registered later will hand back. The
test drives it through the opener registry, the same route `tests/test_input.py` uses to prove
the registry has no zarr-shaped hole. **The defect it guards is the worst available one for this
metric**: falling back to the array's shape reports amplification 1.0 for every input including
the pathological ones, and this metric *replaced* the graph-chunk cap as the only guard watching
for a pathological input — so a silent 1.0 removes the guard rather than weakening it.

### What is NOT asserted, stated rather than implied

**The peak itself.** At test scale the difference between one-call and per-span assembly is
kilobytes, and RSS cannot resolve it — the instruments that could are the ones this project has
already paid twice to make honest. What the test asserts is the mechanism the peak rests on: the
spans are sub-chunk, they partition the tile exactly, and `assemble_tile` consumes exactly them.
`assembly_spans` is public for that reason.

### BLOCKED, AND NOT WIRED INTO `run()`: NOTHING MAPS `signal_terms` TO SIGNAL TERMS

`tile_side_for` needs `k_beta`, the number of design columns. `k_beta` comes from the design
matrix, the design comes from `signal_terms`, and **`signal_terms` is a tuple of strings that
nothing in the tree parses.** `config.candidates.parse_candidate` resolves *noise* terms through
`kernel_registry`; `core.signal` has the term classes and **no registry and no parser**, and no
task in the plan is assigned one.

So Task 6 ships its units complete and tested, and `run()` is **not** wired to iterate tiles,
because it cannot size one. **Recorded rather than closed by inventing the vocabulary**: which
signal terms exist and how a parameterized one (`offset:2005.5`, a rate change, a named
regressor) is spelled is a design decision that belongs to the task that builds the design, not
to a task about tiling — the same reasoning that made the per-point prefix provisional.

**It is owed by Task 9 at the latest**, which fits and therefore needs the design itself; Tasks 7
and 8 need `P_total` and the offsets, which come from the *candidate* list and are unaffected.

---

## The handoff sweep (2026-08-12, at the close of Task 6)

**THE DUPLICATED-MEASUREMENT SWEEP, AND WHAT IT FOUND ABOUT THE PREVIOUS ONE.** Task 4 found
`PROGRESS.md` carrying **693** and **692** as the test count twelve lines apart, and reconciled
the values. **That was the wrong fix and this sweep shows why**: by Task 6 the same two places
held 802 and 802, and the same two places held ~271 s and ~271 s — agreeing, undated in one of
them, and **guaranteed to drift again the moment one is updated.** Reconciling values treats the
symptom; **deleting the second copy treats the cause.**

Reduced to one dated, precondition-carrying statement each:

| measurement | was | now |
|---|---|---|
| test count | twice in `PROGRESS.md` | cold-start head only, dated |
| full-sweep timing | twice in `PROGRESS.md`, once in `pyproject.toml` as a stale `~255 s` | cold-start head only, dated, with its machine and the fact that it postdates the `bench/` leak fix; `pyproject.toml` now carries **no figure** and says why |
| the open-questions table | three copies | one summary plus the full text at the end |
| Phase 1's `~255 s` | undated, read as current | labelled historical |
| Task 5's `~500 s` | read as a measurement | **labelled VOID** — measured under the `bench/` thread-mask leak, so everything after `test_bench.py` ran single-threaded |

**A comment in `pyproject.toml` is the worst place to keep a figure**, and it held the oldest
one: nobody re-measures while editing a marker list, so `~255 s` sat there through 271, 298 and
~500. It now carries the reasoning and no number.

**THE ~271 s FIGURE IS PROVISIONAL AND SAYS SO.** Two changes landed together — the `bench/`
restore and open question 12's test replacement — and the split was not decomposed. The
inference that the leak was the cause is plausible and unmeasured; it is written down as
plausible and unmeasured.

---

## Task 7 — the ragged index builder (audited 2026-08-12)

The brief is seventeen lines and its central claim — *a design that reuses one table looks
correct at equal `p` and is wrong at unequal `p`* — is **true of the mechanism and false of
the fixture the same paragraph prescribes.** That is this audit's main finding, and four of
the others follow from reading `free_param_index` rather than the brief.

### (a) — THE M=2 FIXTURE'S TWO OFFSET TABLES ARE IDENTICAL, SO IT CANNOT SEE A REUSED TABLE

The plan, design doc §12.3 and `PROGRESS.md` all prescribe `white` (p=1) beside
`white + matern12` (p=3) as the fixture that separates the two extent functions. Compute
both tables on it:

| extent function | extents | **offsets** | total |
|---|---|---|---|
| `p_m` (`/noise/`) | (1, 3) | **(0, 1)** | 4 |
| `p_m(p_m+1)/2` (`/detail/`) | (1, 6) | **(0, 1)** | 7 |

**The offsets coincide, because `off_0` is 0 under every extent function and `off_1` is the
first model's extent — and `p = 1` is a FIXED POINT of `p ↦ p(p+1)/2`.** So is `p = 0`. A
builder that computed one offset table and reused it for both axes passes every offset
assertion this fixture can make, and is caught only by `total` and `extents` — the two
quantities an implementer is least likely to assert per model.

**Changed:** the offset assertions run on a fixture whose **first** model has `p ∉ {0, 1}`.
`matern32` (p=2) first gives (0, 2) against (0, 3) at M=2, and the M=3 fixture
`white / white + matern12 / matern32` gives **(0, 1, 4)** against **(0, 1, 7)**. The M=2
store fixture is still asserted, because Task 8 consumes exactly it — but it is asserted for
its values, not relied on to discriminate.

### (a) — AND THE NUMBER THE THREE DOCUMENTS QUOTE IS THE MISTAKE THEY WARN ABOUT

Design doc §12.3, the 2a plan's Task 7, and `PROGRESS.md`'s Task 7 inheritance section all
state the extent as `Σ_m p_m(p_m+1)/2` and then illustrate it as **`4 + 6 = 10`**. At
p = (1, 3) that sum is `1 + 6 = 7`. **10 is `P_total(P_total+1)/2 = 4·5/2`** — the triangle
of the *flattened total*, which is precisely the one-table-reused error the paragraph exists
to warn against, committed in its own worked example. (`4 + 6` is also not 10.)

The intent is unambiguous from the same section: model *m*'s block is contiguous and
per-model, and a joint covariance across mutually exclusive candidates is not a quantity.
**`Σ_m p_m(p_m+1)/2 = 7` is correct and the three copies of `10` are wrong.** Reported rather
than resolved silently; all three corrected, with the derivation written beside the number.

### (a2) — THE FIVE COORDINATE COLUMNS ARE IDENTITIES, AND ONE OF THEM READS AS A REQUEST

New fields, so the classification is owed. Every column of `noise_param_*[P]` is an
**IDENTITY**: it says what a stored `theta` slot actually *is*, and it must be populated by
reading the `ParamSpec` reached through the kernel registry.

The one that fails on the obvious implementation is `noise_param_model`. The tempting source
is the config's own candidate string — `"white + matern12"` — which is a **REQUEST**. The
identity is the spec's canonical label, and **the two differ in order on the very fixture 2a
uses**: `ProcessSpec` sorts `matern12` before `white`, so the identity is
`"matern12[0] + white[0]"`. A test asserting the config string passes against a builder that
never looks at a spec.

The four checks for an identity field: something populates it (the builder); it derives from
the thing it identifies (the `ParamSpec` objects, through `spec.terms`); a change in that
quantity moves it (a `fixed=True` parameter removes a slot — asserted); and the populator is
not the thing identified (the config supplies only which candidates, never their layout).

### (f) — THE BRIEF SAYS "PURE ARITHMETIC" AND `free_param_index` SAYS IT IS THE ONLY LAYOUT

`terms.free_param_index`'s docstring, in the tree already:

> THIS IS THE SINGLE SOURCE OF TRUTH for the ordering of the parameter vector the optimizer
> searches. Everything that packs or unpacks that vector … calls this rather than re-deriving
> the layout with its own nested loop.

"Pure arithmetic over the candidate list" invites exactly that nested loop. **The slot order
in `/noise/` IS the order of the optimizer's vector** — the store's columns label the values
`fit` produces — so a second derivation that agrees today and diverges later mislabels every
`theta` in a 10⁷-point store with every array the right shape and every value finite.

**Changed:** the name/unit/transform columns come from `free_param_index(spec)`, and the
extent comes from `spec.n_theta()`. `n_theta`'s own docstring says it is deliberately derived
*independently* of `free_param_index` so the two stay separate checks on one invariant — so
the builder **asserts the two agree per model** rather than collapsing them, and that
assertion is a live guard rather than a tautology.

### (d) — THE VOCABULARY THE BRIEF NEVER USES

Absent from Task 7's brief, and each one changes the answer: **`fixed`** (a fixed parameter
occupies no slot; `len(term.params)` over-counts, `n_free()` does not), **canonical order**
(the slot order is the spec's, not the config's), **`free_param_index`**, **`unit`**,
**`transform`**, **M = 0**, and **the coordinate width**. The four `noise_param_*` column
names appear in the design doc and `PROGRESS.md` but not in the brief being implemented.

### (i) — `noise_param_name[P]` IS AMBIGUOUS WITHIN A MODEL AT EXACTLY 2a's FIXTURE

Measured: `white + matern12` has free parameters
`[(matern12[0], sigma), (matern12[0], rho), (white[0], sigma)]`. **Two slots are named
`sigma`.** A reader selecting `noise_param_name == "sigma"` inside model 1's block gets two
values and no way to tell the measurement noise from the correlated component — a
plausible-number failure with no symptom, in the group whose whole purpose is to be readable
without metamer installed.

**Changed, and reported as a deviation from the design doc's four columns:** the builder
emits **five** — `model`, `term`, `name`, `unit`, `transform` — keeping each column atomic
and making `(model, term, name)` unique. Qualifying `name` as `"matern12[0].sigma"` was the
alternative and was rejected: it puts two facts in one column and forces a reader to parse it.

### (c) — EXITS, ENUMERATED

`build_ragged_index`: one return; `ValueError` on an empty candidate list; `ValueError` on a
negative or non-integral extent; `NotImplementedError` propagating out of `n_theta()` for a
shared-parameter spec. `noise_param_coordinates`: one return; the same three, plus
`ValueError` on a coordinate value wider than the fixed width or outside ASCII.

**M = 0 is refused rather than returning an empty index.** A store with no models makes every
array constant across the axis every downstream assertion compares along — the cancellation
rule, applied to an axis length. It is also unreachable through `Config` today, which is an
argument for the guard being cheap, not for it being unnecessary.

### (c2) — `NotImplementedError` IS NOT A `ValueError`, AND LAYER 3 CATCHES THE SECOND

Task 4's layer-3 staging catches `ValueError` and `KeyError`. A shared-parameter spec raises
`NotImplementedError` from `n_theta()`, which would escape as an unhandled exception — exit
code 1, which in 2a means a crash. **Unreachable today**: no family sets `shared_with` and
nothing in the config path can. Recorded, not built for; it becomes live the moment sharing is
implemented, and that is the task that must stage it.

### (h) — THE EXTENT FUNCTION MUST NOT HAVE A DEFAULT

A default extent argument means every call site that does not think about it silently builds
the `/noise/` table, including the one that meant `/detail/`. **The parameter is required**,
so naming the axis is forced at each call. This is (h) applied to the interface rather than to
a test: a parameter left at its default is a parameter not exercised.

### (i3) / (j) — THE ORACLE IS A HAND-WRITTEN TUPLE, NEVER A `cumsum`

`offsets[-1] + extents[-1] == total` is a relation two consistently-wrong tables satisfy, and
`np.cumsum(extents)` is the builder's own construction. Every expected table in the tests is
written out by hand — `(0, 1, 4)`, `(1, 3, 2)`, `6` — and `covariance_extent` is additionally
checked against an **enumeration of the (i, j) pairs**, which shares no derivation with
`p(p+1)/2`.

### (a3) — THE PACKED STORAGE ORDER IS THE DEFERRED GROUP'S REGIME, AND A BARE STRING IS NOT A GATE

§12.3 names the plausible-number failure of `/detail/`: row-major-lower unpacked as
column-major-lower is **still symmetric, often still positive definite, and wrong with no
symptom.** The brief asks only for the extent function. An attrs string declaring the order
with no code that produces it is name-is-not-a-gate in its purest form, so the order ships as
an **executable enumeration** (`covariance_slot_pairs`) whose length is what checks the extent
formula. Deviation from the brief, and its reason.

### (k) — THE COLUMNS ARE WRITTEN ONCE INTO A 10⁷-POINT STORE AND NEVER RE-DERIVED

Nothing here iterates a set today, but the failure mode is the one (k) exists for: a
seed-dependent column order is invisible to every same-process test and to mutation testing,
and the store is created in one process and resumed in another. A subprocess test pins the
five columns' bytes under two `PYTHONHASHSEED` values.

**And the trap one module over:** `terms._param_canonical` iterates `sorted(term.params)`
while `free_param_index` iterates declaration order. Two orders over the same mapping, in the
same file, both correct for their own purpose. `sorted` is the wrong one here and reads as the
tidier choice.

### MEASURED — `S32` TRUNCATES SILENTLY AND REFUSES NON-ASCII LOUDLY

`np.array(["x" * 40], dtype="S32")` returns a 32-byte value with **no error**; a truncated
model label still reads as a label. `np.array(["µm"], dtype="S32")` raises
`UnicodeEncodeError`. **One library lies quietly and the other refuses loudly**, in one
constructor. The builder measures every value against the width and refuses, naming the value
and its length.

### (i5) — WHAT THE TEMPTING REPAIR WOULD MOVE

If the name column's order surprises the author, the repair that makes it "look right" is to
sort the parameters — which moves `free_param_index`, the optimizer's own vector layout, for
every fit in the system. **The shared thing is the layout; fix the expectation, never the
order.**

### A finding for Task 8, recorded here so it is not rediscovered

**Do not write the covariance offset table into a 2a store.** `/detail/` is not created, and
an offset table describing a group that does not exist is a name-is-not-a-gate hazard with a
reader on the other end — the same argument that made an uncreated group cleaner than an empty
one. The builder is exercised with both extent functions in the *tests*; only the `/noise/`
table is written.

### Bite checks — 13 mutations, 13 bite

Each guard removed or inverted against the finished suite, one at a time:

| mutation | tests that failed |
|---|---|
| `covariance_extent` returns `n_theta()` — one table reused for both axes | 4 |
| `block()` returns `slice(off, p)` | 2 |
| extent from `len(term.params)` rather than the free count | **1** |
| columns re-derived by a `sorted(term.params)` nested loop | 3 |
| model label built from a non-canonical label order | 3 |
| width check deleted | 1 |
| ASCII check deleted | 1 |
| empty-candidate guard deleted | 1 |
| negative-extent guard deleted | 1 |
| non-integer-extent guard deleted | 1 |
| layout-versus-count disagreement guard deleted | 1 |
| `model_index` off by one | 1 |
| slot pairs emitted column-major | 1 |

**The third row is the one worth keeping.** Counting declared parameters instead of free ones
fails **exactly one** test — the constructed fixed-parameter fixture — because **no shipped
family declares a `fixed=True` parameter**, so every other fixture in the suite gives the same
answer either way. A defect visible only to a constructed fixture is still visible; dropping
that fixture as artificial would have dropped the only test of it. It is the same argument as
`machine.choose_core_count` (no SMT on this host) and `library_table` (one OpenBLAS here).

**The cross-process test's control is inside it:** besides the two seeds agreeing, it asserts
the leading bytes, so it fails if the columns are empty or reordered — which the label-order
mutation confirmed.

---

## Task 8 — the store schema (audited 2026-08-12)

The most consequential brief in 2a, because every choice it makes is unchangeable once data
exists. Six findings changed the schema; two of them — a missing primitive and a fill value —
would each have been discovered at a task that could no longer fix them.

### (d) / (f) — `/primitives/` IS MISSING `n`, AND WITHOUT IT THE RECOMPUTE PATH CANNOT RUN

`criteria.rank_candidates` takes a `CandidateScores`, whose fields are `loglik`, **`k`**,
**`n`**, `n_eff` and `outcome`. Design doc §12.2's `/primitives/` lists `log_lik`, `k`,
`n_eff_trend`, `n_eff_bic` and `iterations`. **`n` — the per-objective sample size — is in
neither §12.2 nor the plan's Task 8 layout, and it is not derivable from what is stored.**
Under ML it is the per-point valid-sample count and under REML it is that minus the design
rank; both come from the **mask**, which is data, not a stored primitive.

The consequence is precisely the one the handoff names as fatal:

> If any future change makes `rank_candidates` need the data, §12.8 becomes unimplementable
> and the three-hash split buys nothing.

Task 12 would have had to re-open the input and recount to "recompute without refitting",
which is the claim exit criteria 5a, 15 and 16 exist to establish. **Found by binding
`CandidateScores`'s field list against the layout — (g) applied to a data structure rather
than to a call.**

**Changed:** `/primitives/` gains `n[y,x,m]`. It is stored **per model even though v1 makes
it constant along `m`** (the design is built once, before the candidate loop), for the same
reason §12.3 gives `/signal/` an explicit model axis: a shape change later is a format
migration on a 10⁷-point store, and `k` beside it genuinely does vary with `p_m`. Design doc
§12.2 and the plan amended.

### (a2) MEASURED — `OK = 0`, SO A DEFAULT `fill_value` MAKES AN UNWRITTEN STORE READ "ALL OK"

`outcomes._CODES` puts `OK` at **0** and `NOT_ATTEMPTED` at **8**. zarr's default
`fill_value` for an integer array is **0**, and **zarr does not write a chunk equal to the
fill value** (Task 6 measured this for reads; it applies to creation with more force). So a
store created with the default fill is, on disk, byte-for-byte identical to one created with
the correct fill — **0 chunk files either way** — and reads back as a completed, successful
run over the whole grid.

Measured here: an array created with `fill_value=8` and never written yields
`np.unique(...) == [8]` and **zero chunk files**; the same array with the default yields
`[0]` and zero chunk files. **The defect is invisible in the store's bytes and inverts the
store's meaning.**

**Changed, and generalized into the rule the whole fill table follows:**

> **Every array's fill value must be a value its write path cannot produce.**

| array | fill | why it is unproducible |
|---|---|---|
| `/status/outcome` | `NOT_ATTEMPTED` (8) | nothing in 2a writes that code |
| every float array | NaN | consistent with the invariant: a non-`OK` slot is NaN anyway |
| `/primitives/iterations` (uint16) | **65535** | the cap is 200; a fit never reports it |
| `/selection/n_valid` (int16) | **-1** | a count is never negative |
| `/selection/selected` (int16) | **-2** | `-1` already means "no winner" |
| `/completion/tiles` (uint8) | **0** | **the deliberate exception** — an unwritten tile *is* incomplete, so here the neutral value is the true one |

**The exception is stated because otherwise it is "fixed" later.** Every other zero-looking
fill in this store is a defect; that one is the definition.

### (a) — THE STATUS/VALUE INVARIANT CANNOT HOLD FOR `iterations`, AND THE DTYPE IS THIS TASK'S

The invariant is *"a non-`OK` status has NaN in **all** corresponding value slots"*, and it
is stated over `/primitives/` — which contains `iterations`, specified as **uint16** in three
documents. **A uint16 has no NaN.** The dtype is fixed at store creation, so the contradiction
must be resolved here even though Task 9 wires the invariant.

`k` and `n` are not affected: `CandidateScores` already carries both as **float64**, so they
take NaN naturally. **`iterations` is the only integral member**, and it is the only one that
feeds no arithmetic — nothing recomputes from it.

**Changed:** `iterations` keeps uint16 and is **explicitly exempt from the invariant, with
65535 as its "no fit ran" value**, recorded where the dtype is chosen. Task 9's invariant
check must name the exemption rather than discover it.

### MEASURED — §12.4's CHOSEN DTYPE IS THE UNSPECIFIED ONE, AND ITS REJECTED ALTERNATIVE IS NOT

§12.4 chose fixed-width bytes (`S32`) over variable-length strings, because *"zarr v3 string
support and xarray's handling of it are the least stable corner of the stack"*. Measured
2026-08-12 with **zarr 3.3.0 / xarray 2026.7.0**, that is now backwards:

| dtype | `zarr.json` `data_type` | on creation |
|---|---|---|
| `S32` | `null_terminated_bytes` | **`UnstableSpecificationWarning`: "does not have a Zarr V3 specification … may be unreadable by other Zarr libraries … may change without warning"** |
| `str` | `string` | no warning |
| `uint8` | `uint8` | core spec |

Both round-trip through `xr.open_zarr` today. But **the writing library declares the chosen
one unstable on disk**, and §12.4's entire concern is the durability of exactly this metadata
in an archive meant to outlive the version that wrote it.

**Changed:** the label coordinates use the **v3-specified `string` dtype**, and §12.4's
integer-code JSON legend in attrs stays exactly as specified, as the redundancy. **Only the
dtype moves; the structure §12.4 prescribes is unchanged.** Consequence for Task 7:
`ragged`'s columns become `tuple[str, ...]`, and `COORDINATE_WIDTH` with its truncation and
ASCII refusals is **deleted along with its two tests** — those guards existed for a
fixed-width dtype and guard nothing without one. Keeping a refusal whose reason has
evaporated is worse than deleting it: it reads as a constraint the format imposes.

### MEASURED — "PLAIN `xr.open_zarr`" WARNS UNLESS THE METADATA IS CONSOLIDATED

Opening a store created through the raw zarr API emits a warning telling the reader to
consolidate, pass `consolidated=False`, or pass `consolidated=True`. **The acceptance
criterion is a round-trip through *plain* `xr.open_zarr`** — a reader who must first discover
a keyword is not the reader §12.4 has in mind.

**Changed:** `zarr.consolidate_metadata` runs at the end of store creation. **And the
coupling is recorded rather than left to be discovered**: consolidated metadata is a *copy*
of the array metadata and attrs, so **anything that later creates an array or writes an attr
must re-consolidate.** In 2a nothing does — provenance is written at creation and every later
write is chunk data — and that is now an assertion, not an assumption. This is the
duplicated-measurement rule at the level of zarr metadata: the copy drifts the moment one
side is updated.

Also measured, and it is what makes exit criterion 3 cheap: a subprocess run with
`PYTHONPATH` unset from a directory outside the tree **has xarray and cannot import
metamer**, so "with metamer uninstalled" is constructible without touching the environment.
`xr.open_datatree(engine="zarr")` reads the whole group hierarchy in one call.

### (a2) — THE THREE NEW ATTRS THAT WOULD HAVE BEEN NAMES

- **`schema_version` is an IDENTITY of the writing code**, so it is a module constant stamped
  by the writer, never a config field — the same argument that moved `algorithm_version` and
  `registry_version`. **And its bump rule has a producer this sub-phase**: `outcomes._CODES`'s
  own docstring says adding a member bumps the store's schema version, and **Task 9 adds
  `SCREENED_OUT` and `NOT_APPLICABLE`.** Recorded as a requirement on Task 9 rather than
  pre-empted here, because their `is_failure` / `is_eligible` semantics belong to the task
  that owns the failure-rate denominator, and adding members without deciding those is a name
  without a gate.
- **`fit_hash` is `str | None` and a store must never carry the None.** `Config.fit_hash()`
  returns None when stage 4a has not run, so a store created before the input is opened would
  write `fit_hash: null` — and Task 11's resume gate comparing `null == null` **matches every
  such store**. Refused at creation, naming the entry contract's ordering.
- **`profile_name` has no producer until Phase 5, so it is omitted rather than written
  empty.** A provenance field that is always empty records nothing — Task 2's CF-attrs
  finding. **`warm_start_used` is a fact about the RUN, not about the config**: reading it off
  `config.warm_start.enabled` would write `true` for a 2a run that cannot warm-start, so it is
  an explicit parameter defaulting to `False`.

### (a) — A LENGTH-1 AXIS AGAIN, AND THIS TIME IT IS `b`

The plan fixes M=2 and C=2 for exactly this reason and says nothing about `b`, the signal
parameter axis. `k_beta` is unobtainable in 2a (the signal-term parser is Task 9's), so the
width is a parameter — and a test that passes `n_beta = 1` makes every quantity defined
across `b` constant, which is the same defect one axis over. **Fixtures use `n_beta >= 2`.**

### (c) — EXITS, ENUMERATED

`create_store`: one return; `FileExistsError` if the path exists (a store is created once,
and silently overwriting a 10⁷-point run is unrecoverable); `ValueError` for a missing or
None-valued required provenance key, for a non-positive axis length, for a `tile_side` that
exceeds the grid, and for a coordinate length that disagrees with the ragged index's total.
`provenance_attrs`: one return; `ValueError` when `fit_hash` or `compat_hash` is None.

### (i) — A FIXTURE OF FILL VALUES WRITES NOTHING, SO NO TEST MAY ASSERT ON FILES

Task 6 measured that zarr does not write a chunk equal to the fill value. At **creation**
every array is entirely fill, so the whole store is metadata: measured, four files for two
arrays. **Any store-creation assertion about bytes written or keys present reads a
correct-looking zero**, exactly as the brief warns. Every assertion here is on **values read
back**, and the paired positive control is a region write producing exactly one shard file.

### (j) — THE RECORDED SHARD AND CHUNK BYTES ARE NOT THE FILE SIZES

The brief asks for the actual chunk and shard bytes to be recorded. **Those are
`prod(shape) * itemsize`, and the file on disk is compressed** — measured, a 913 952-byte
float32 shard lands as 790 204 bytes of random data and would be far smaller for a smooth
field. This is Task 6's read-amplification units trap in a new place: **both sides of a
recorded quantity must be in the same unit**, and the recorded figure is the uncompressed
budget number, because that is what the memory formula and the "few MB per chunk" target are
about.

### (g) — SIGNATURES BOUND, AND ONE BLOCKER CONFIRMED

`Config.{fit,compat,run}_hash()`, `candidate_spec_hashes()`, `process_specs()`,
`hashing.ALGORITHM_VERSION`, `registry.REGISTRY_VERSION`, `geometry.geometry_components` /
`geometry_hash`, `threads.observe_thread_limits`, `Outcome.code`, and Task 7's
`build_ragged_index` / `noise_param_coordinates` all bind. **`tile_side` does not**: it needs
`k_beta`, which needs the signal-term parser Task 9 owns, so **store creation takes the tile
side as an argument rather than deriving it** — the same accommodation Task 6 made.

### (k) — THE ATTRS ARE JSON AND MUST NOT CARRY PROCESS-LOCAL ORDER

Every legend and every mapping written into attrs is built with sorted keys, and the
provenance dict is asserted byte-identical across two processes under different
`PYTHONHASHSEED` values. `json.dumps` of a dict preserves insertion order, so an attrs
mapping built by iterating a set is stable within a process and unstable between them — the
one defect class an in-process suite cannot reach, in the one part of the store a resume
compares.

### Bite checks

Recorded after implementation, below.

### Bite checks — 21 mutations, 21 bite

Fill values (5): outcome left on zarr's default, `iterations` 0, `n_valid` 0, `selected` −1
colliding with the no-winner sentinel, the completion bitmap filled complete. Shape (3):
bitmap shaped by points, shard equal to the whole array, noise axis sized `M * p_max`.
Content (5): `n` dropped from `/primitives/`, spatial coordinates not written, model labels
omitted, criterion labels omitted, metadata not consolidated. Provenance (5):
`schema_version` from the config, `warm_start_used` from the config, the geometry-emptiness
guard, the required-attrs guard, the existing-store refusal. Axes (3): recorded bytes taken as
a chunk count, the single-criterion guard, the `n_beta = 1` guard.

**Two mutations each failed three tests rather than one**, and both are the store's identity
rather than its contents: `schema_version` taken from the config, and the noise axis sized
`M * p_max`. **The fill-value mutations failed one test each**, which is the whole argument
for the hand-written fill table — no other assertion in the suite can see them, because they
change nothing about shape, dtype or the store's bytes.

**A test failure during development that was itself a finding:** the first version of the
no-chunk-files assertion checked the whole `/status/` group and failed, because **the label
coordinates *are* written at creation** — they carry values, not fill. The claim is about the
data arrays, and the corrected test asserts both halves: the data arrays have no chunk files
and `noise/m` does.

---

## Task 9 — the tile write path, the signal parser, and the invariant (audited 2026-08-13)

The largest brief in 2a, and **(g2) — promoted the day before out of Task 8 — paid for itself
immediately on a different pair of lists.**

### (g2) — `FitResult` DOES NOT CARRY `k` OR `n`, SO THE STORE'S PRIMITIVES HAVE NO SOURCE

Task 8 established that `/primitives/` must hold `loglik`, `k`, `n`, `n_eff_*` because
`rank_candidates` reads them. Binding the **producer** against the same list:

    FitResult: candidates theta theta_err theta_unconstrained beta beta_err loglik
               outcome init_rung n_iter n_eff_bic n_eff_trend ranking engine
               objective gradient_mode

**`k` and `n` are absent.** Both are computed inside `fit()` by `counting.penalty_terms` to
build the `CandidateScores` it ranks with, and then **discarded with the local**. So the write
path would have had to call `penalty_terms` itself — **a second derivation of a stored
primitive**, computed from a different call site than the one that produced the stored ΔIC,
with nothing keeping the two in step. That is the cancellation rule at a module boundary:
every test comparing a store's `k` against a recomputed `k` would compare one derivation with
itself.

**And the same object solves the second problem.** `fit()` takes **one** `criterion` and
returns **one** `Ranking`; the store has **C = 2**. Calling `fit` twice would refit 10⁷ series
to add a criterion — the exact thing §12.8's split exists to prevent.

**Changed:** `FitResult` gains `scores: CandidateScores` — the object `fit` already built —
and the write path ranks per criterion from it with `rank_candidates(scores, c)`. One
derivation, C rankings, no refit. `FitResult.ranking` stays as the single-criterion
convenience every Phase 1 test uses.

### (d) / (a3) — THE SIGNAL VOCABULARY IS PARAMETERIZED AND THE NOISE ONE IS NOT

The brief says to mirror `kernel_registry`. **The two vocabularies are not the same shape.**
A noise candidate is a sum of bare names (`"white + matern12"`) and `parse_candidate`'s
restricted AST **refuses a call, an attribute, a subscript and a literal by name**. Signal
terms are constructed with arguments: `Offset(epoch)`, `RateChange(epoch)`,
`Harmonic(period)`, `Regressor(values, name)`.

**The spelling is already half-decided in the tree**, and inventing a second idiom would put
two syntaxes inside one config field: Task 4 added
`config.model.PER_POINT_TERM_PREFIX = "regressor_field:"`, **a `kind:argument` spelling that
already lives inside `signal_terms`**. So a parameterized term is `offset:2005.5`, and the
parser is per-entry rather than an expression parser — `signal_terms` is a **list**, with no
`+` in it at all.

**What is shared is `core.registry.Registry`, not the parser.** Sharing the parser would force
one grammar to grow the other's: the sum-expression walker would have to admit arguments, and
the colon form would have to admit `+`. The registry is generic and gives the entry-point
group for free, exactly as `kernel_registry` does.

### (a3) — THREE TERM CLASSES CANNOT BE BUILT FROM A CONFIG STRING, AND EACH FAILS DIFFERENTLY

`Regressor` needs a numpy column — that is the per-point regressor regime, already refused at
layer 3. `ExpDecay` and `LogDecay` declare `linear = False` and their `columns()` **raises
`NotImplementedError`, naming Phase 4**. Registering them under names a config can reach would
turn a refusal that belongs at layer 3 into an exception raised **inside the design build,
inside the tile loop, ten hours in**. They are therefore not registered, and the parser's
"unknown term" message names them explicitly as deferred rather than as typos.

### (a) — `k_beta` IS A COLUMN COUNT, NOT A TERM COUNT, AND THE TWO DIFFER ON 2a's OWN CONFIG

`Harmonic` contributes **two** columns (cos and sin). For `["constant", "trend", "annual"]`
the term count is **3** and `k_beta` is **4** — which is §9.4's worked value, so the wrong one
is not even self-consistently wrong: it silently changes every tile size and every memory
figure derived from it.

**`k_beta` is read off the built design**, `design_matrix(t).shape[-1]`, against the **real**
time axis the runner already has after stage 4a — not off a synthetic one-sample probe, whose
`Trend` column is identically zero and whose `Regressor` length check would fire.

### (a) — THE MODEL AXIS IS THE CANCELLATION AXIS, AGAIN, AND IT IS WORSE HERE

`fit.py` computes `design_info(t, mask)` **once**, before the candidate loop, so **every
design-derived outcome is identical for every `m`.** A test that varies the *candidate* to
produce a design failure varies nothing. **The mask is what varies**, and the two required
fixture points are both mask constructions.

Beyond the brief's warning: it also means `RANK_DEFICIENT_X` and `INSUFFICIENT_DATA` are
**constant along `m` by construction in v1**, so the invariant's "non-`OK` has NaN in all
slots" is exercised by those outcomes at every model at once. The point where **candidate 1
fails and candidate 2 succeeds** cannot come from the design — it must come from the
optimizer, which is why the offset-inside-a-gap construction is specified as a *required*
property rather than an incidental one.

### (c) — THE WRITE PATH'S EXITS, AND THE ONE THAT MUST NOT EXIST

`write_tile`: one return; `ValueError` on a tile whose shape disagrees with the result's `B`,
on a candidate count disagreeing with the store's model axis, and on a violated status/value
invariant. **There is deliberately no "skip this tile" exit**: a write path that can decline
silently makes the completion bitmap's meaning depend on which branch ran, and Task 10 sets
the bit from the fact that the write returned.

### (a0) — THE INVARIANT IS CHECKED BEFORE THE WRITE, NOT AFTER

A store is not readable-back cheaply mid-run, and a violated invariant that reaches disk is
already the defect. The check runs on the **arrays about to be written**, so the failure is a
refusal rather than a corrupted region — and it is the same function Task 13's exit criterion
4 runs over a finished store, so the two cannot drift.

**`iterations` is exempt and `/selection/` is exempt, for different reasons**: uint16 has no
NaN, and `outcome` has no `c` axis. Both exemptions are named in the checker rather than
implied by which arrays it happens to look at.

### (k2) — `SCREENED_OUT` AND `NOT_APPLICABLE` TAKE THE NEXT FREE CODES, AND THE VERSION BUMPS

`outcomes._CODES` currently ends at `ILL_CONDITIONED_X = 11`; the new members take **12** and
**13**. `_CODES`'s own docstring makes adding a member a `schema_version` bump, so
`store.SCHEMA_VERSION` goes to **2** — the store's `flag_values` / `flag_meanings` legend is
written from the enum at creation, so a v1 store and a v2 store disagree about the vocabulary
even though no 2a run can emit either code.

**Their `is_failure` / `is_eligible` semantics are decided here because this task owns the
denominator**: `SCREENED_OUT` is a deliberate skip, like `NOT_ATTEMPTED` — not a failure;
`NOT_APPLICABLE` is a declared domain mask, like `INSUFFICIENT_DATA` — not a failure and
**not eligible**, because land is not a point the failure rate is over.

### (i2) — THE `engine=` SEAM, AND THE CONTROL IT FINALLY GETS

Task 4 deliberately did not add `engine=` to the runner because no test there could make it
bite. The write path can: a raising stub proves "no fit ran" only if the seam it is delivered
through actually reaches the fit. **The positive control is that the same stub, on a tile with
a fittable series, DOES raise** — Task 0 shipped that control, and this is the first task
where the runner-level seam exists to be checked.

### THE PRESCRIBED FIXTURE FOR EXIT CRITERION 14 CANNOT WORK, AND THE BRIEF SAYS WHY TWO LINES LATER

`PROGRESS.md` and the plan both specify the one-candidate-fails point as
**"the offset-inside-a-gap construction, a breakpoint with no support for one candidate's
design"**. In v1 **the signal spec is fixed and only the noise model is selected**, and
`fit.py` builds `design_info(t, mask)` **once, before the candidate loop** — a fact the same
brief states, in its own "Watch" paragraph, as *"a test asserting design-failure behaviour
must vary the mask, never the candidate"*.

**So a design failure is identical for every `m` and cannot distinguish candidates.** The
prescribed construction produces `RANK_DEFICIENT_X` at *both* candidates, i.e. `n_valid = 0`,
which is a different test point entirely.

**The reachable construction is an optimizer-stage failure**, and it arrives for free:
fitting `white + matern12` to white noise leaves the correlated candidate degenerate —
measured, `DEGENERATE_HESSIAN` at three of four points — while `white` fits. That is open
question 9's own fixture defect, used deliberately. The test states the reasoning so the
recipe is not reinstated.

### Bite checks — 11 mutations, 11 bite

Invariant (4): each direction deleted, the `-inf` check deleted, the trend exemption made
unconditional. Aggregate (1): a bare `merge_outcomes` with no OK-wins rule. Layout (2): the
ragged un-pad writing every model at slot 0, the tile/result size guard. Selection (1): one
ranking reused for every criterion. Vocabulary (2): `k_beta` as the term count, `k_beta` as
the numerical rank. Seam (1): `engine=` not threaded to `fit`.

**`k_beta` as the term count failed three tests and as the rank failed one**, which is the
right asymmetry: the term count is wrong for every composition containing a harmonic, and the
rank is wrong only where the design is degenerate — the case a test has to construct on
purpose.

### WHAT THE FULL SWEEP CAUGHT THAT THE TASK'S OWN TESTS COULD NOT

Two failures, both in modules Task 9 never opened, and **both are the standing rules
working**:

- **`test_objective.py` carried a SECOND copy of the outcome code table.** Adding two members
  meant editing two suites, which is the drift "state a fact once" exists to prevent.
  `tests/test_outcomes.py` now owns the enumeration; the objective test asserts what only it
  can — that every `OUTCOME_PRECEDENCE` member's code **round-trips and lands inside
  `_RANK_TABLE`**, since that ladder is indexed by code and a member outside it is silently
  demoted to "unranked".
- **`create_store`'s "at least 2 candidates" refusal was a FIXTURE RULE ENFORCED AGAINST
  USERS.** A runner test with a single candidate began failing inside store creation. The
  vacuity argument — a length-1 axis makes every assertion over it pass — is **true of tests
  and false of the format**: fitting one candidate under one criterion is coherent, and
  `delta_ic = 0` with `weight = 1` is the correct answer there. The refusal is now "at least
  one", and the M=2/C=2 requirement is asserted **of the suite's own fixture** instead.

**Generalize: a constraint justified by "otherwise the test is vacuous" belongs on the test,
not on the product.** The tell is a refusal whose stated reason is about assertions rather
than about data.

---

## Task 10 — the completion bitmap, write ordering, and SIGTERM (audited 2026-08-13)

The shortest brief in 2a — three behaviour bullets and one test — and the audit returned the
largest ratio of findings to brief lines. Two of them are reachable defects in code that is
already committed; one contradicts a docstring this project wrote itself.

### (d) — `signal` IS ALREADY A LOCAL VARIABLE IN THE FUNCTION THAT MUST INSTALL THE HANDLER

`run()` binds `signal = config.signal_spec()` and reads `signal.terms` at
`src/metamer/batch/run.py:274`. A module-level `import signal` in that file is therefore
**shadowed for the whole body of `run`**, so `signal.signal(SIGTERM, ...)` inside the tile
loop resolves against a `SignalSpec` and raises `AttributeError` — or worse, would be "fixed"
by renaming the stdlib import, leaving two spellings of one module in one file.

**Changed:** the handler lives in a new module, `batch/completion.py`, which imports the
stdlib module and never imports `core.signal`. `run()` uses it through a context manager and
never names the module at all. The grep that found this is (d) exactly as specified: the
vocabulary the task requires, looked for in the tree before writing any of it.

### (a2) — CLASSIFY THE BIT: IT IS AN IDENTITY, AND THE FOURTH FACT IS THE ONE THAT FAILS

The handoff says the classification generalizes past hashes to *"every gate made of a name — a
completion bitmap, a calibration cache key, a warm-start cache key"*, so the bit gets the sort
before it gets a writer.

`/completion/tiles[ty,tx]` claims **what the store contains**, which is an IDENTITY, not a
REQUEST. Of the four facts an identity must satisfy:

| fact | verdict |
|---|---|
| something populates it | yes — `run()`, at exactly one site |
| it derives from the quantity it identifies | yes — the bit is set from the fact that `write_tile` **returned** |
| a change in that quantity moves it | yes — a raising write propagates and the bit stays 0 |
| the populator is not the thing being identified | **NO. The writer reports on itself.** |

**The fourth cannot be satisfied at an acceptable price**, because the only independent
populator is a reader that re-reads the region it just wrote, at 10⁷ points, per tile. What
makes the self-report safe is **structural rather than conventional**, and both halves are
already committed: `write_tile` has **no decline path** (Task 9, deliberately), and the bit is
set only on its normal return — so "returned" and "every region write for this tile was
issued" are the same event. **A later "skip this tile" exit in the write path would silently
turn the bit into a self-report of nothing**, which is the mechanism to watch, and it is why
Task 9's missing exit is a load-bearing absence rather than an omission.

**Scope stated rather than implied:** the bit certifies that every region write returned, not
that the bytes survive a power cut. There is no `fsync` — an `fsync` would be a POSIX
assumption of the kind §15.5 forbids in the store layer, which relies on per-object write
atomicity alone. Measured: setting one bit at `chunks=(1,1)` creates exactly one object
(`tiles/c/1/2`), so no other tile's bit is read-modify-written.

### (a2) — SECOND INSTANCE, REACHABLE TODAY: THE BIT'S *INDEX* IS A NAME WHOSE MEANING MOVES

The bit is `[ty, tx]`, and `ty = y_start // tile_side`. **`tile_side` is derived from
`memory_budget_gb`, which is run-relevant and therefore in neither `fit_hash` nor
`compat_hash`** — by design (§13.3), so that "run locally, burst to cloud, resume" is a resume
and not a rerun. So Task 11's gate will **pass** a resume whose budget differs, and a
different budget gives a different tile side, and bit `(1,0)` then names a different region
than the one it was set for. Symptoms: none. Every array keeps its shape, some points are
never written and read back as `NOT_ATTEMPTED`, others are written twice, and the bitmap ends
fully set.

**Refusing a budget change outright is the wrong repair**, and this is the (i5) shape at the
level of a product decision: the tempting fix breaks §15.5's headline workflow, where the
cloud instance that resumes the run is chosen for having *more* RAM than the laptop that
started it.

**Changed — the rule is over the derived tile side, never over the budget** (two budgets can
derive the same side, and refusing on the budget would refuse a resume that is geometrically
identical):

| stored side vs derived | action |
|---|---|
| equal | proceed |
| **stored < derived** | **adopt the stored side.** The shards were fixed at creation and a smaller tile is inside the requested budget, so the resume is both geometry-correct and memory-safe |
| **stored > derived** | **refuse**, naming both sides, the store's recorded `memory_budget_gb`, and the two resolutions — raise `--memory-budget`, or write a new store. Finishing this store needs tiles the requested budget cannot hold, and writing sub-shard regions instead would make every tile write a read-modify-write of a shard |

**(a4) recomputed, because the brief's one number is load-bearing.** "At 10⁷ points the bitmap
is of order 100 elements": 10⁷ points is a 3163 × 3163 grid, `ceil(3163 / 338) = 10` per axis,
**100 bits**. Confirmed.

### (a5) — THE BRIEF'S TWO BEHAVIOURS PRESCRIBE OPPOSITE TREATMENTS OF THE SAME WINDOW

*"An interruption injected between the two writes leaves the bit unset"* and *"SIGTERM flushes
rather than dying mid-region-write"* both talk about the interval between the data write and
the bitmap write, and they want opposite things there: the first wants the run to stop inside
it, the second wants it not to.

**They are consistent only if SIGTERM is never observed inside that window.** So the handler
**records and returns** — it sets a flag and does nothing else — and the flag is read **after**
the bit is written, between tiles. A handler that raised (the `KeyboardInterrupt` idiom) would
land the exception in precisely the window the other requirement forbids, and would do it
non-deterministically. Stated in the module, because "the handler only sets a flag" reads as a
style preference and is a correctness requirement.

### (a) — A RESUMED STORE AND A FRESHLY WRITTEN ONE ARE IDENTICAL, SO THE STORE CANNOT WITNESS THE SKIP

§11.3 makes the fits deterministic, so a run that ignores the bitmap and rewrites every tile
produces **byte-identical contents** to one that skips correctly. The cancellation rule: every
assertion comparing a resumed store against a complete one is invisible to the defect the task
exists to fix, and the report's own `tiles_skipped` is the code under test reporting on
itself.

**Two observables that are not constant across the comparison, both used:** the raising stub
engine (a fit that runs at all raises), and **a marker written into the store between the two
runs** — the outstanding tile's `/status/outcome` region set back to `NOT_ATTEMPTED`, a value
no successful write can produce, so a rewritten region is distinguishable from one that was
left alone. The second is what pins *which* tiles were rewritten rather than *whether* any
were.

### (i7) — A SQUARE TILE GRID WITH A DIAGONAL FIXTURE CANNOT SEE A TRANSPOSED INDEX

Where the two candidate index functions `(ty, tx)` and `(tx, ty)` agree: the diagonal, and any
grid with one tile. The fixture is 2 × 2 grid points at `memory_budget_gb = 5e-6`, which gives
`tile_side = 1` and a 2 × 2 tile grid — square, so the fixture must clear the bit of an
**off-diagonal** tile, `(0, 1)`. Measured for the sizing: `resident_bytes_per_series` is
**1786 B** at `d=3, k_beta=4, p=3, N=60, M=2`, and `floor(sqrt(5368 / 1786)) = 1`;
`1e-5 GB` gives 2.

### (g) / (i) — `Tile` MUST NOT GAIN A TILE INDEX, BECAUSE NOT EVERY `Tile` IS A GRID TILE

The obvious implementation is to have `tile_grid` stamp `(ty, tx)` onto each `Tile` so the
consumer cannot mis-derive it. **`tiling.assembly_spans` builds `Tile` objects for
chunk-aligned sub-spans** (`tiling.py:292`) which are not grid tiles and have no bit —
so the field would be either wrong or optional on the type that carries it, and an optional
index defaults to `(0, 0)`, which is a valid-looking bit.

**Changed:** the mapping is a function, `completion.tile_index(tile, side)`, which **refuses a
tile that is not aligned to the grid** (`y_start % side` or `x_start % side` non-zero). A span
tile handed to the bitmap raises instead of setting some other tile's bit.

### (c) — EXITS, ENUMERATED

`run()`: one `return`. Raises: `ValidationError` layer 2 (the `--memory-budget` override),
layer 3 (`check_semantics`, **and the new stored-versus-derived tile-side refusal**),
`InputContractError` layer 4, and anything `fit` or `write_tile` raises — `InvariantError`,
`ValueError`, an engine's exception, and the injected fault. **No exit sets a bit**, and the
bit is set at exactly one site. The loop gains two non-exit branches: `continue` on an
already-complete tile, and `break` on a recorded SIGTERM after the bit is written.

`completion.mark_complete`: one return, no raise of its own. `tile_index`: one return, one
`ValueError`. `flush_on_sigterm`: yields once, restores the previous handler in `finally`.

### (k2) — THE FLUSHED-SIGTERM EXIT CODE, AND IT GIVES CODE 2 ITS FIRST PRODUCER

Enumerating what the runtime emits here before choosing: an **unhandled** SIGTERM kills the
process as 128+15 (`subprocess` reports **−15**); argparse's 2 is already remapped to 3 by
`_Parser.error`; CPython's 1 on an unhandled exception is the known unfixable alias.

Design doc §14.3 defines **2 = "aborted early — resumable"**, and gives as its rationale that
*"a script that resumes on failure needs to distinguish 'aborted, resumable' from 'config
rejected'"*. **A preempted run is exactly that case**, so a flushed SIGTERM exits
`ExitCode.ABORTED_EARLY`. Exiting 0 is the alternative and it lies: the store is incomplete
and the caller is told the run finished.

**This contradicts something this project wrote.** `validation.ExitCode`'s docstring and
`PROGRESS.md` both say codes 1 and 2 *"have no producer until sub-phase 2e"*, on the ground
that 2 needs the early-abort mechanism. §14.3's definition is broader than 2e's mechanism, and
the design doc is authoritative on intent — so the docstring is **amended**, not worked
around, and 2e's early abort becomes the second producer of a code that now has one.
Re-raising the signal with the default handler to die as −15 was the alternative considered:
it keeps the taxonomy untouched, and it forfeits the one distinction §14.3 says the taxonomy
exists to make.

### (a3) — DEFER THE FEATURE, DECLARE THE REGIME: THE HANDLER IS MAIN-THREAD-ONLY

Measured: `signal.signal` off the main thread raises `ValueError: signal only works in main
thread of the main interpreter`; the default disposition of SIGTERM in a pytest process is
`SIG_DFL`. A `run()` driven from a worker thread therefore cannot arm the handler.

**Changed:** the regime is declared rather than crashed on or silently swallowed —
`flush_on_sigterm` reports whether it armed, `RunReport.sigterm_armed` carries it, and the
context manager **restores the previous handler** on exit. Without the restore the handler
outlives the run and every later test in the same process inherits it, which is (k): process
state set by one test deciding another's behaviour.

### (i2) — THREE POSITIVE CONTROLS, ONE PER NEGATIVE

| the negative | its control |
|---|---|
| the injected fault leaves the bit unset | the same hook, **not raising**, sets it |
| a resumed run refits nothing | the same resume with one tile's bit cleared **rewrites exactly that tile's region** |
| SIGTERM does not lose a tile | the same fixture with no signal completes and exits 0 |

### (j) — THE ORACLE FOR "THIS TILE'S DATA IS THERE" IS NOT THE BITMAP

Reading the bitmap to check the data was written shares its entire derivation with the thing
under test. The oracle is `/status/outcome` over the tile's region, which is written by a
different call on a different array, and whose fill (`NOT_ATTEMPTED`) is a value the write path
cannot produce.

### (g2) — BIND THE BITMAP'S CONSUMERS AGAINST WHAT THE STORE HOLDS

Two consumers exist that are not in this task: Task 11 needs *which tiles are outstanding* and
Task 12 needs *is the bitmap fully set*. Both need to map a bit back to a region, which needs
the tile side and the grid. **The store carries both**: `attrs["tile_sides"]["shared"]` and any
dense array's leading two axes. Checked rather than assumed, because had the side not been in
attrs the fix would have been a schema change and the schema is frozen at creation.

### Bite checks

Recorded with the implementation below.

### Bite checks — 15 mutations, 15 bite

Ordering (2): the bitmap written before the data; the injection hook moved to
*after* the bit, which is the mutation that pins where the seam is rather than
that it exists. Resume (3): the bitmap not consulted; the bit index transposed;
the alignment guard deleted. Signal (4): the recorded SIGTERM ignored;
`interrupted` read off the signal rather than off the tile counts; the handler
raising; the previous handler not restored. Regime (1): `armed` claimed off the
main thread. Geometry (3): a resume re-tiling from its own budget; a budget too
small for the stored tile accepted; the bitmap shape unchecked against the grid.
Bitmap (2): an absent bitmap read as "nothing is complete"; the bit written as
the fill value.

**Two are worth their reasons.** *The handler raising* is caught by the session
aborting rather than by an assertion — `KeyboardInterrupt` propagates out of
`run`, which is exactly the defect — so it is recorded as caught by mechanism
rather than by a red test. And *`interrupted` off the signal* survived until a
test was written for it: with four tiles the two formulations agree, and only a
**one-tile** grid taking the signal on its last tile separates them. That is
(i7) again — the fixture must be placed outside where the two functions agree —
and it is the fifth-cause check paying off, since the mutation is a real
behaviour change and the survivor was a missing test rather than an equivalence.

### THE (a1) SWEEP — every stored geometry, and what derives it (run 2026-08-13)

(a1) was promoted out of Task 10 on the ground that one instance implies others, so the
sweep is over **everything in this store whose shape or index says WHERE data goes**, asking
of each: is it re-derived at resume, and from an input any hash covers?

| stored geometry | derived from | in a hash? | verdict |
|---|---|---|---|
| `y`/`x` extents, spatial coordinates | the input's grid | `geometry_hash`, fit-relevant | covered — a change refuses at the `fit_hash` gate |
| `b` axis (`k_beta`) | `signal_terms` against the real time axis | both fit-relevant (`signal_terms`, `geometry_hash`) | covered |
| `c` axis | `criteria` | compat-relevant | covered — and it is the refusal §12.8 already narrowed, because growing `c` is a whole-store rewrite |
| shard shape, chunk shape, `/completion/tiles` shape | `tile_side` from `memory_budget_gb` | **neither** | **the Task 10 instance**, now guarded by `completion.resume_tile_side` |
| **`m` axis, `P_total`, and both ragged offset tables** | **`candidates`** | **neither, deliberately** | **A SECOND LIVE INSTANCE — Task 11's** |

**The negative result is worth as much as the positive one, and it is a distinction to
carry: a geometry READ BACK from the store is not an instance.** The chunk subdivision
depends on `CHUNK_TARGET_BYTES`, a code constant in no hash — but chunking is used only at
creation, and every later write goes through the stored array's own chunk grid. **The hazard
is a geometry RE-DERIVED at resume from inputs the gate does not cover**, not one that merely
has an unhashed ancestor.

**The second live instance, stated so Task 11 inherits it rather than discovers it.** The
candidate list fixes three things at creation — the length of the `m` axis, `P_total`, and
the per-model offsets into `/noise/` — and it is in **no hash by design**, because §12.8
permits resuming with a **superset** and a hash can only express equality. So the exclusion
that makes extension legal is exactly what removes every gate from three stored geometries,
which is (a1) word for word.

Today's behaviour, measured against the code: a **prefix** mismatch (a different candidate at
index 1, same length) is **silent** — every array keeps its shape and the store is wrong;
a **longer** list fails on a shape mismatch inside `write_tile`, **after a full tile of fits**
and with a message about array shapes rather than about candidates. Both are Task 11's, and
the gate must run **before the tiling loop**.

---

## Task 11 — the resume gate and its three outcomes (audited 2026-08-13)

The brief's own taxonomy is where the findings are. **One of its four arms has no producer,
one of its refusals has nothing to read, and one of the design doc's permitted resumes
contradicts the argument the same section uses to refuse a different one.**

### (a5) / (c) — THE MIDDLE ARM IS EMPTY BY CONSTRUCTION, MEASURED FROM THE ALLOWLISTS

The brief's table has four rows, and the second is *"a compat-relevant field that is not the
criterion set → recompute derived arrays from stored primitives; do not refit"*.

    hashing.COMPAT_RELEVANT_FIELDS = FIT_RELEVANT_FIELDS | {"criteria"}

**`criteria` is the only field in compat and not in fit.** So *"`fit_hash` matches and
`compat_hash` differs"* is **logically equivalent to "the criterion set changed"**, and the
row above it — refuse, because growing `c` is a whole-store rewrite with no bitmap of its
own — consumes every input that could reach the recompute arm. The middle row has no
producer and cannot be tested through a config.

**The design doc already knew and the plan did not follow.** §12.8's own table carries the
recompute row **struck through**, with *"NARROWED 2026-08-11"* beside it; the plan's Task 11
brief and `PROGRESS.md`'s inheritance section both still describe recompute-in-place as a
live outcome. **The design doc is authoritative on intent, so the arm goes**, and this is the
kind of disagreement the precedence rule says to resolve in the documents rather than carry
into an implementation.

**Consequence for the shape of this task: Task 11 implements no recompute.** The reachable
outcomes on a matching `fit_hash` are **proceed** or **refuse**, with distinct refusal
*reasons*; the recompute path is Task 12's `--reuse-fits-from`, which writes a **new** store
and is the only place the three-hash split's claim is cashed. A future compat-only field
would make the middle arm reachable, so the gate refuses an unrecognized compat difference
explicitly rather than falling through — (a3), the regime declared without the feature.

### (a2) / (g2) — THE `/detail/` REFUSAL HAS NOTHING TO COMPARE AGAINST

Binding the gate's inputs against what the store actually holds, which is (g2) applied to a
gate rather than to a consumer:

| the gate needs | in root attrs? |
|---|---|
| `schema_version` | yes |
| `fit_hash`, `compat_hash` | yes |
| `candidate_spec_hashes` | yes |
| `criteria` | yes |
| **the `/detail/` selection** | **NO** |

`Config.Detail` exists — `region` and `subsample`, and its docstring says *"Fixed at store
creation; Task 11 refuses a change"* — and `provenance_attrs` never writes it. **A refusal
that reads nothing is a name, not a gate**, and this one would have shipped as an arm of the
taxonomy that no input can move.

**Changed:** `provenance_attrs` records `detail`, `REQUIRED_ATTRS` demands it, and
`SCHEMA_VERSION` goes **2 → 3** — a v2 store cannot answer a question the v3 gate asks, which
is the store's own stated bump rule. `test_schema_version_moved_when_the_outcome_vocabulary_grew`
is **re-pointed rather than re-run**, per the standing rule.

### (a5) — §12.8's SUPERSET ROW CONTRADICTS ITS OWN CRITERION-SET NARROWING

§12.8 permits resuming when *"the candidate set is a superset"* — resume normally, fitting
only what the bitmap says is outstanding. **Two facts make that unimplementable in place, and
the second is the stronger one:**

1. The `m` axis and the ragged `/noise/` axis are **fixed at store creation**. Adding a
   candidate grows both across the whole grid — a whole-store rewrite, which is precisely why
   the same section refuses a criterion-set change.
2. **The completion bitmap has no model axis.** A tile is complete or it is not; it cannot be
   *complete for candidates 0..M−1 and outstanding for M*. So even with a growable axis there
   is no state in which a superset resume could record what it had done.

**So the positional rule is necessary and not sufficient.** `len(requested) >= len(stored)`
is what keeps the *extension* legal at the hash boundary — the reason `candidates` is in no
allowlist — and an in-place resume still refuses it, naming "write a new store" as the
resolution. The two refusals are different faults and get different messages: a **prefix
mismatch** is a corruption refusal (candidate B's fits into candidate A's slice), an
**extension** is an unimplementable-in-place refusal.

Design doc §12.8 amended, dated, in the same idiom as its 2026-08-11 narrowing.

### (g) — `tuple != list` ACROSS THE JSON BOUNDARY, AND IT FAILS TOWARD REFUSING EVERYTHING

`Config.criteria` and `Config.candidate_spec_hashes()` are **tuples**; the same values come
back out of zarr's attrs as **JSON lists**. `("aic", "hqic") == ["aic", "hqic"]` is `False`
in Python, so the natural comparison refuses **every** resume, including the correct one.

**The tell is which way it fails**: a gate that refuses everything looks conservative and is
caught by the first green-path test, which is why it is worth naming rather than fearing —
but a gate written the other way round (`set(...)`) would pass a permutation, and that is the
one that is silent. Both directions are pinned below.

### (i7) — A PERMUTATION IS THE FIXTURE THAT SEPARATES POSITIONAL FROM SET COMPARISON

Where a positional comparison and a set (or sorted) comparison **agree**: every case except a
reordering. So the discriminating fixture is a **permutation of the stored candidates** —
`["white", "white + matern12"]` resumed as `["white + matern12", "white"]` — which a set
comparison accepts and which writes each candidate's fits into the other's slice. At this
fixture's unequal `p` (1 against 3) it also shifts every ragged offset, so the corruption
lands in `/noise/` as well as in the model axis.

A **single-position** change is the second fixture, and it is what the "names the index"
requirement needs: `["white", "matern32"]` differs from the stored list at index 1 only.

### (a1) — THE GATE MUST RUN BEFORE THE TILING LOOP, WHICH IS WHERE THE OTHER HALF ALREADY IS

From the (a1) sweep above: the candidate list fixes the `m` axis, `P_total` and both offset
tables, and is in no hash by design. Today a prefix mismatch is **silent** and an extension
fails on an array shape **inside `write_tile`, after a full tile of fits**. Task 10's
`resume_tile_side` already sits between the hashes and the tiling; the identity comparisons
join it there, and the ordering inside that block is **identity first, geometry second** — a
store whose fits are unusable should say so before it says anything about tile sizes.

### (c) — EXITS, ENUMERATED

`resume.check_resume`: one `return None`; `ValidationError(SEMANTIC)` for each of
**schema_version, fit_hash, candidate prefix, candidate extension, criterion set, `/detail/`,
and an unrecognized compat difference** — seven refusals, each naming what differs and what
resolves it. Exit code **3**: §14.3's *"config/validation error — resuming will not help"*,
which is true of every one of them.

`run()` gains no new return. The gate raises before the tiling loop, so a refusal is
`tiles_written == 0` by construction rather than by an assertion.

### (c2) — THE REFUSAL TYPE CANNOT BE SWALLOWED BY AN EARLIER CLAUSE

`ValidationError` derives from `Exception`, not from `ValueError`, and the only `except
ValueError` on the path is `_with_memory_budget`'s, which wraps a `model_validate` call and
is far above the gate. `__main__` catches `(ValidationError, InputContractError)` and reports
the layer. Checked rather than assumed, because (c2)'s worked instance was exactly a refusal
landing in a clause written for something else.

### (i2) — THE NEGATIVE IS "NO FIT RAN BEFORE THE REFUSAL", AND ITS CONTROL EXISTS

Every refusal test asserts `raising_engine.calls == []`, which is unfalsifiable on its own —
a gate that refuses because the store cannot be opened at all would satisfy it equally. The
control is Task 10's `test_the_same_resume_reaches_the_engine_for_an_outstanding_tile`: the
same seam, the same store, one clear bit, and the engine **is** reached. It is cited in the
new tests rather than duplicated.

### (k) — ONE REFUSAL IS TESTED ACROSS A PROCESS BOUNDARY

The gate's inputs are on disk and its output is an exit code, so at least one arm goes
through `python -m metamer` and asserts **3**. In-process, the exception type is the only
observable and the mapping from type to code is a second thing that can break.

### Bite checks — 13 mutations, 13 bite, and the two survivors were different faults

Wiring (2): the gate not called; the gate moved below the tiling loop. Hashed
comparisons (3): `fit_hash`, the criterion set, `schema_version`. Unhashed comparisons (4):
the candidate prefix dropped; the prefix compared as a **set**; a strict superset accepted; a
**shortened** list accepted. Consistency (1): the compat check dropped. Provenance (1):
`detail` not recorded at creation. Boundary (1): the criterion comparison written without
normalizing the JSON list. Ordering (1): `check_resume` placed after `resume_tile_side`
(caught by the message a grid change produces).

**Two survived on the first pass, and they diagnose to different causes — which is the whole
point of running the taxonomy rather than reacting.**

- **A shortened candidate list was accepted — cause 1, no test protected the guard.** The
  superset arm had a test and its mirror did not: `["white"]` is a *prefix* of the stored
  list, so every positional comparison passes it and only the length rule catches it. Test
  written; the mutation now bites. **A length rule written as one comparison invites exactly
  this**, because the arm that feels like the interesting one gets the test.
- **The `tuple`/`list` mutation was not a defect — cause 5.** The mutation written first was
  `tuple(stored) != config.criteria and stored != config.criteria`, which is **semantically
  identical to the original on every reachable input**. The reachable defect is the
  unnormalized comparison alone, `stored_criteria != config.criteria`, and that bites on the
  green-path test immediately — a gate that refuses every resume. **Verify the mutation is a
  behaviour change before concluding anything about the test.**

### The defence-in-depth outcome, and both guards now name each other

`completion.resume_tile_side`'s **bitmap-shape refusal became unreachable through a
configuration** the moment this gate landed: the grid is in `geometry_hash`, which is
fit-relevant, so a changed grid is refused upstream by name. That is cause 2 of the five —
a guard above it fires first — and the response is the recorded one: **keep it, comment both,
each naming the other**, and re-point its test at what stays reachable, which is a store
whose bitmap does not describe its own grid (a truncated copy, a foreign writer). Without the
cross-comments the next simplification deletes one on the grounds that the other covers it,
and deletes the coverage with it.

---

## Task 12 — `--reuse-fits-from`, the recompute path (audited 2026-08-13)

**With Task 11's in-place recompute arm gone, this command is the ONLY consumer of the
three-hash split** — the sole demonstration that `fit_hash` identifies anything rather than
merely existing. Its tests are the tests of the split.

### (a5) — THE SOURCE CHECK CANNOT BE `check_resume`, AND THE ARM THAT DIFFERS IS THE POINT

The obvious economy is to run Task 11's gate against the source store: same comparisons,
different store. **It is wrong on exactly one arm, and it is the arm the feature exists for.**
`check_resume` refuses a **criterion-set change**, and a criterion-set change is *the* reason
to run `--reuse-fits-from` at all. Reusing it wholesale would make the command refuse its own
primary use.

**Changed:** the comparisons are factored so both callers share them per-check rather than in
one block — schema version, `fit_hash`, the positional candidate comparison — and the source
check adds *bitmap fully set* while omitting *criteria*, *compat_hash* and *`/detail/`*.

**Two of those omissions are decisions rather than oversights, and both are recorded here:**

- **`compat_hash` is omitted because it is `fit_hash` plus the criterion set**, and the
  criterion set is licensed to differ. Comparing it would refuse everything the criteria
  comparison already lets through.
- **`/detail/` is omitted because 2a creates no `/detail/` group in either store**, so
  nothing is claimed falsely by a new store recording a different selection. **The regime is
  declared for the task that creates the group**: a recompute cannot produce `/detail/` (the
  Hessian is not stored), so once the group exists, a source that lacks the requested
  selection must be refused here.

**And the shared refusal messages could not be shared verbatim.** Task 11's name "write a new
store" as the resolution — which is the operation *being performed* in this context. The
message text takes the resolution from the caller; a refusal that suggests what the user is
already doing is worse than one that says nothing.

### (a1) — THE NEW STORE'S GEOMETRY IS READ BACK FROM THE SOURCE, NOT RE-DERIVED

(a1) in its sharpened form decides this outright: the tile side is a stored geometry, and the
recompute has a store to read it from, so it is **read back rather than re-derived from the
current budget**. Two independent reasons agree:

- **Exit criterion 5a requires `/primitives/`, `/noise/`, `/signal/` and `/status/` to be
  byte-identical to the source.** Identical bytes need identical chunk and shard geometry,
  which is `tile_side`. A recompute at a different side could not satisfy the criterion no
  matter how correct its arithmetic.
- **The budget rule does not apply, because no fit runs.** `resume_tile_side`'s "stored >
  derived, refuse" arm exists to stop a *fitting* run exceeding a hard RAM budget; a
  recompute holds a tile of primitives — `(B, M)` float64 arrays — not a tile of filter
  state. **Applying it would refuse the cheap operation on precisely the small machine that
  most wants to run it.**

**The consequence is stated rather than left to be discovered: the new store carries the
source's tile side**, so a later *fitting* run against it under a smaller budget refuses —
correctly, because that run would fit.

### (g2) — `CandidateScores` FROM A STORE: FIVE ARRAYS, ONE COORDINATE, TWO ATTRS

The standing test binds the five **per-cell** fields against stored arrays. The other three
have no test because they are not per-cell, and this is where they come from:

| field | source | why it is sound |
|---|---|---|
| `loglik`, `k`, `n`, `n_eff`, `outcome` | `/primitives/` and `/status/` | the standing subset test |
| `labels` | the `m` coordinate | written at creation from the same candidate list the gate compares positionally |
| `engines`, `objectives` | root attrs `engine` and `objective` | **both are fit-relevant**, so `fit_hash` equality — verified before anything is read — is what makes the config's values equal the source's. Taking them from the config is not a shortcut; it is the same values by a checked identity |

`EngineId` and `Objective` are `StrEnum`s over exactly those config strings, so the
conversion is total and needs no table.

### (a) — ONE SELECTION WRITER, OR THE TWO PATHS DISAGREE WHERE NOTHING COMPARES THEM

`/selection/` is produced in two places after this task: the fit path and the recompute path.
**A second implementation is the cancellation rule at a module boundary** — every test that
compares a recomputed store against a fitted one would be comparing two derivations that were
written to match, and a difference in weight normalization or in the no-winner sentinel would
be invisible until a user compared two stores by hand.

**Changed:** `write._write_selection` takes a `CandidateScores` rather than a `FitResult` and
becomes public. The fit path passes `result.scores`; the recompute path passes the block it
read. One derivation, two callers.

### (g2) — THE COPY IS DERIVED FROM THE STORE'S OWN LISTING, NOT FROM A LIST IN THE CODE

Everything outside `/selection/` and `/completion/` is copied. **A hand-written list of
arrays is the thing that goes stale when the schema grows**, and the failure is silent: the
new array keeps its fill value in the recomputed store, which for every float array is NaN
and reads as "this point failed" rather than as "nobody copied this". So the copy walks the
source's groups and takes every array whose leading dimensions are `(y, x)` — coordinates are
excluded by that test, and a new data array is included automatically.

**And the test binds the same way**: it asserts equality over the arrays *the store lists*,
not over a list the test carries, so a schema addition that the copy misses fails here.

### (c) — EXITS AND EXIT CODES, WITH THE ONE THAT IS LAYER 4

`check_source`: one `return`; refusals for **schema version**, **`fit_hash`**, **a candidate
prefix mismatch**, **a candidate-list length change** — all `ValidationError(SEMANTIC)`, exit
**3** — and **an incompletely set completion bitmap**, which is `InputContractError`, exit
**4**.

**The split is not arbitrary and (c2) is why it is safe.** A hash or candidate mismatch is
the *configuration* disagreeing with a store: layer 3, "resuming will not help". An
incomplete source is a fact about *data on disk*: layer 4, exactly like the stage-4a
contract, and it reaches exit 4 through the type `exit_code_for` already dispatches on. **The
two types are structurally disjoint** — `InputContractError` is not a `ValidationError` —
so the dispatch cannot fail toward the earlier clause.

### (i2) — "NO FIT RAN" IS THIS TASK'S CENTRAL CLAIM, SO ITS CONTROL IS NAMED TWICE

The raising stub proves the negative; its positive controls already exist and are cited
rather than re-derived: Task 0's (`fit` with a fittable batch does raise) and Task 10's (the
same runner seam, a store with one outstanding tile, engine reached). **Without them "no fit
ran" is satisfied by a recompute that never reached the tiling loop at all** — which is
precisely what a source-verification bug would produce.

### (i) — THE FIXTURE MUST CARRY THE FIT-OK / CRITERION-UNDEFINED POINT

Q3 item 4: recompute-stage failures live in `/selection/` on the criterion axis, never in
`/status/`, because `outcome` has no `c` axis. A fixture whose every point ranks cleanly
under every criterion **cannot express that at all**, so the source store is built with the
REML route Task 9 established — `n_obs = 6` against a rank-4 design gives `n = 2`, and HQIC
is undefined while AIC is fine. The recompute must reproduce it **from stored primitives**,
which is the whole claim: NaN `ic_best`, `-1` in `selected`, and `/status/` untouched.

### (k) — THE SELF-CONTAINMENT TEST MUST DELETE THE SOURCE, IN ANOTHER PROCESS

"The new store is self-contained" is a claim about a reader that does not have metamer or the
source. Asserting it in-process, with the source still on disk, tests nothing: zarr would
resolve a reference happily. The test **deletes the source** and opens the new store with
plain `xr.open_zarr` in a subprocess with `PYTHONPATH` unset, which is the same construction
`test_write.py` already uses for the no-metamer read.

### Bite checks — 13 mutations, 13 bite, and all three survivors were fixture failures

Source verification (5): the completion bitmap unchecked; `fit_hash` unchecked; the candidate
comparison dropped; a missing source undiagnosed; **the criterion comparison added** — the
mutation that proves the omission is deliberate rather than forgotten, since adding it makes
the command refuse its own primary use. Provenance (2): the source's attrs inherited; the
source hashes not recorded. Copy (2): only `/primitives/` copied; the dimension test dropped
so coordinates are copied too. Operation (1): the recompute refitting instead of reading.
Geometry (1): the tile side re-derived. Reading (1): `n_eff` taken from `n_eff_trend`.
Checking (1): the invariant not run on the copied block.

**Three survived the first pass and none of them was a weak assertion — all three were
fixtures that could not express the defect.** That is (i) three times over, and it is worth
naming because the reflex on a survivor is to strengthen an assertion:

- **The tile side re-derived from the budget.** The fixture ran the recompute at the
  source's own budget, where the derived side and the stored side are **both 1** — the two
  functions agree exactly there, which is (i7) at a scalar. The new test runs the recompute
  at a budget deriving **77** against the source's 1.
- **`n_eff` read from the wrong array.** `n_eff` is read by **`bic_neff` alone**; under AIC
  and HQIC the field is never touched, so the wrong array produces byte-identical output. The
  new test ranks by `bic_neff` and compares against **the fit path's own values for the same
  criterion** — a different derivation reaching the store by a different route.
- **The invariant not checked on the copied block.** No fixture had a corrupt source, because
  every source in the module was written by this code. The new test writes NaN into a
  `log_lik` cell whose status is `OK` — the state a store handed over by someone else can be
  in, and the reason the check exists at all.
