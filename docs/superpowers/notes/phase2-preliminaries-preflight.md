# Pre-flight (a)–(k) on the Phase 2 preliminaries

**Written 2026-08-10.** The three preliminaries P0, P1 and P2 arrived as a written brief,
and the handoff's own rule is that a brief is audited before code is written — including a
brief written by the person who owns the project, because the audit catches a wrong *model*
of the problem and authorship is no defence against that. Every finding below changed what
was implemented.

The categories are those of
[`phase1-to-phase2-handoff.md`](phase1-to-phase2-handoff.md) §1.

---

## P0 — reconcile the branches, and fix the version in `fit_hash`

### (g) — does every claim bind against the current tree? **Two claims do not.**

**P0(a) says "THE BRANCHES HAVE DIVERGED". They have not.** Measured:

```
git merge-base --is-ancestor phase-1 main   -> success
git log --oneline main..phase-1             -> empty
git log --oneline phase-1..main             -> 5 commits (at 2372bbb, before this work)
```

`phase-1` is a strict **ancestor** of `main`. It carries nothing `main` lacks. The brief's
framing — "decide deliberately whether Phase 1 merges to main first or phase-1 rebases onto
it" — presents a choice between two operations, and **the correct answer is neither**: a
merge would be an empty no-op and a rebase would rewrite five already-published commits for
no gain, which the project's own git rules forbid. The action is a fast-forward of the stale
pointer. This matters beyond pedantry: had the audit been skipped, "reconcile the diverged
branches" reads as licence to rebase, and rebasing `phase-1` onto `main` is exactly the
published-history rewind CLAUDE.md records as having cost two commits once already.

**P0(b)/P1 inherit a misattribution from the handoff.** The handoff §2 says
"`signal.X_RANK_RTOL = 1e-10`, on which `RANK_DEFICIENT_LOG_LIMIT` is derived". It is not.
`objective.RANK_DEFICIENT_LOG_LIMIT = -0.5 * log(_RANK_RTOL)` imports `_RANK_RTOL` from
`metamer.core.engines.kalman` — the **Gram** cutoff — not `signal.X_RANK_RTOL`. The two are
different constants in different modules that happen to hold the same numeral `1e-10`, which
is precisely why the misreading is available. Consequence for P1: re-deriving
`X_RANK_RTOL` alone would have left `RANK_DEFICIENT_LOG_LIMIT` resting on the picked
constant the exercise existed to remove. Both are addressed; see the P1 section.

### (c) — enumerate the exits. Where can a VCS-derived string actually enter a hash?

Enumerated, not counted. Three hash-producing call paths exist in `src/`:

| producer | payload source | can a VCS value enter? |
|---|---|---|
| `hashing.fit_hash` / `compat_hash` / `run_hash` | the caller's config mapping, plus `CONFIG_DEFAULTS` and `MACHINE_KEY` | **yes** — via the `metamer_version` field |
| `hashing.machine_fingerprint` | `cpu_model`, `cores`, `total_ram_bytes` | no |
| `terms.ProcessSpec.spec_hash` | `TermSpec.canonical()` — family, params, transforms, `shared_with` | no |

### (a)/(k) — the defect, stated as measured rather than assumed

The brief says "Establish first whether the package version is actually in the `fit_hash`
payload — check, do not assume." Checked:

- `metamer_version` **is** a member of `hashing.FIT_RELEVANT_FIELDS`, so it is in the
  `fit_hash` payload, and `_subset` **raises** if a config omits it. It is not optional.
- **Nothing in `src/` populates it.** The value is supplied by the caller; today the only
  callers are tests, which pass the literal `"0.1.0"`.

So the defect is **latent, not live** — and that is worse rather than better, because the
thing that makes it live is a single obvious line in Phase 2's config builder
(`metamer_version=metamer.__version__`), which is the reading any author would give the
field's name. Under `hatch-vcs` that expression yields:

| where it runs | value |
|---|---|
| installed from tag `v0.1.0` | `0.1.0` |
| installed from any untagged commit after it | `0.1.1.dev3+g6a0fb3b` — **new on every commit** |
| `pixi run`, i.e. the uninstalled `PYTHONPATH=src` tree | `0.0.0.dev0`, the `__init__.py` sentinel |

The third row is a second, independent instability the brief does not name: the same code
hashes differently depending on whether it is *installed*, so a store written by the CLI in
a pixi shell and resumed from an installed wheel would refit even at a tagged release.

This is pre-flight (k) — a value that must be stable across runs depending on state outside
the code — one layer further out than the `PYTHONHASHSEED` instance: the process-local state
is now the *installation*.

### (e)/(i) — could any existing test have caught it?

No, and the reason is (a), the cancellation rule, in its purest form. Every test in
`tests/test_hashing.py` that involves `metamer_version` supplies it from `_config()`, so it
is **constant across every comparison axis those tests use**. The three `GOLDEN_*` constants
are absolute values and would catch a change to the field's *name or position* — which is
how the 2026-08-07 regeneration was detected — but not a change to a value the test itself
supplies. A fixture that hardcodes `"0.1.0"` cannot express a defect whose whole mechanism
is that the real value is not `"0.1.0"`.

The new guard therefore does not compare two hashes of configs the test wrote by hand; it
asserts that the payload's algorithm-identity field **does not vary with
`metamer.__version__`** at all, exercised across processes with different versions injected.

### (f) — does the brief contradict a docstring already in the tree?

`hashing.py`'s module docstring already states the sharp edge: "because defaults are
included, any version bump touching a compat-relevant default invalidates every in-progress
store. The allowlist is what keeps that surface small enough to review." That paragraph
argues for keeping the *surface* small. It does not notice that one allowlisted field's own
value had become a per-commit string, which converts "any version bump" into "any commit" —
the documentation was right and was not constraining, which is the handoff's standing
observation about documentation and tests.

### The decision, argued

The brief leans toward an explicit constant and asks for an argument rather than assent.
The argument, against each named alternative:

- **Release version with dev and local segments stripped.** Rejected. It is wrong in both
  directions at once. Too coarse: a patch release that changes packaging, docs or CLI help
  and nothing about the likelihood invalidates every in-progress store. Too fine in the
  dangerous direction it is meant to fix: an algorithm change on an untagged commit does
  **not** move it, so a stale fit is silently reused against changed code. A rule that fails
  open on the case that matters is not a fix.
- **`registry_version` alone.** Rejected on scope. `registry_version` identifies the family
  registry — which families exist and under what names. `theta_hat` and `log_lik` also
  depend on `objective.py`'s REML constant, on `optimize.py`'s step rules and convergence
  classification, on `gradients.py`'s step constants and on the engine's recursion. A change
  to any of those moves the fit without touching the registry.
- **An explicit `ALGORITHM_VERSION`.** Adopted. It is the only candidate where "does this
  change invalidate stored fits?" is a decision a person makes rather than a side effect of
  tagging or of committing. Its one real cost — someone can forget to bump it — is the cost
  of *every* declared-identity mechanism in the module, including the allowlist itself, and
  it is answered the same way: state the bump rule where the constant lives, and put it on
  the release checklist.
- **Hashing the source of the fit-determining modules.** Considered and rejected, though the
  brief does not list it. It is automatic, which is attractive, but it moves on comments,
  docstrings and formatting, and it differs between an sdist, a wheel and a working tree.
  That is the same too-fine-grained failure as the VCS version, arrived at by a different
  route.

**`metamer_version` is not deleted.** It moves out of the allowlist and stays in the config
as provenance, where `run_hash` — which is provenance and never a gate — still carries it.
That is the correct home for a value that should be *recorded* on every store and must
*gate* nothing.

### P0(c) — did the publish flow put anything else VCS-derived into a hashed payload?

**No, and the check is decisive rather than a survey.** The publishing work is exactly the
five commits `99f690e..2372bbb`, and its entire footprint under `src/` is:

```
git diff --stat 99f690e..2372bbb -- src/
 src/metamer/__init__.py | 11 ++++++++++-
 src/metamer/py.typed    |  0
```

`py.typed` is empty by definition and `__init__.py`'s change is the `hatch-vcs` import with
its `ImportError` fallback — that is, `__version__` itself and nothing else. No other
module changed, so no other module can have acquired a VCS-derived value to contribute.

The rest of the diff is `pyproject.toml`, the two workflows, `dependabot.yml`,
`.gitignore`, `RELEASING.md`, `README.md`, `PROGRESS.md` and four test files. Checked
against the allowlist one by one, none of them is a payload input: the build backend, the
`dynamic = ["version"]` declaration, `[tool.hatch.build.hooks.vcs]`, the wheel and sdist
targets, the classifiers, the dependency floors and the CI matrix are all consumed by the
*build*, never by `hashing.normalize`. `run_payload`'s only non-config input is
`machine_fingerprint(cpu_model, cores, total_ram_bytes)`, whose three arguments come from
`core/machine.py`, which the publish flow did not touch.

The one field worth naming as *deliberately* out of scope: `registry_version` is a literal
in `core/registry.py`, hand-maintained, and stays that way. It is a second declared
identity of exactly the kind `ALGORITHM_VERSION` now is, and it should not be wired to the
package version either.

---

## P1 — `HESSIAN_COND_LIMIT`, and the constants around it

### (f)/(g) — the brief's own dependency claim, checked against the tree

Carried forward from the P0 section: **`RANK_DEFICIENT_LOG_LIMIT` does not rest on
`signal.X_RANK_RTOL`.** It rests on `engines.kalman._RANK_RTOL`. The brief inherits the
handoff's wording — "re-derive `X_RANK_RTOL` rather than keeping it … a derived constant
resting on a picked one inherits the arbitrariness" — and the second half of that sentence
is aimed at the wrong constant. Acting on the brief verbatim would have re-derived
`X_RANK_RTOL`, left `RANK_DEFICIENT_LOG_LIMIT` resting on `_RANK_RTOL` exactly as before,
and produced a report saying the arbitrariness had been removed.

Checked further, and this is the part that changes the answer rather than merely the
citation: **`_RANK_RTOL` is not a picked constant.** Its docstring carries a measured
calibration table (cond(X_w) against the Gram's singular-value ratio, at n = 200 on
numpy 2.x / OpenBLAS) and a window bounded from both sides — an exactly deficient design
lands at 0 or ~5e-17 of the leading singular value, and a Gram accumulated at
`cond(X_w) = 1e8` has already lost its small singular value into float64 noise, so a
threshold below ~1e-16 would be reading rounding error. The standing rule offers three
acceptable states, "derive, measure, or document explicitly why a picked value is
correct"; `_RANK_RTOL` is in the second and third of them and is left alone. Saying so is
the finding, because the alternative was moving a calibrated constant on the strength of a
misquoted dependency.

### (i) — can the brief's expected outcome be observed at all?

The brief predicts `DEGENERATE_HESSIAN` will "start firing on cases that previously
reported OK" and asks which fixtures move. Before changing anything, the question is
whether the suite contains a fixture *capable* of showing it: a fixture whose `cond(H)`
lands between `6.7e7` and `1e10`. It does, and finding it first is what made the result
interpretable rather than a surprise. `test_fit.py::_plain_batch` builds
`rng.standard_normal(...) + trend` and fits it with `[white, white + Matérn 1/2]` — **pure
white noise fitted with a composite that has a timescale**, which is precisely the
construction open question 9 diagnosed in `_mixed_batch`'s row 0 and fixed there. Measured
before the constant was touched, at `batch=2, n=200`: series 0 at
`sigma_matern = 9.3e-4`, `cond(H) = 1.194e+08`; series 1, same generator and seed stream,
at `cond(H) = 1.447e+03`. **One non-identified row and one healthy row from an identical
construction** is the signature of a fixture that is not asserting what it claims, and it
was invisible under `1e10` because `1.194e+08` reads as healthy by 84x.

So the answer to "is this fixture genuinely healthy?" was available *before* the change,
which is the only order in which the question can be answered honestly.

### (a) — the cancellation rule, applied to a threshold

**Every rank, outcome and tolerance assertion in the suite compares a fixture against the
constant, so both sides move together and the constant's value is invisible to all of
them.** This is the same structure as the hash module's, where six comparison tests passed
against a silently unstable serializer. The cure is the same: an absolute value, worked out
by hand. Each of the four constants now has a pin stated as a power of two —
`HESSIAN_COND_LIMIT == 2**26`, `X_RANK_RTOL == 2**-26`,
`_NEGATIVE_REDUCTION_RTOL == 2**-26` — plus the other half of its derivation written as an
independent identity (`eps * HESSIAN_COND_LIMIT == sqrt(eps)`,
`X_RANK_RTOL**2 == eps`, `_NEGATIVE_REDUCTION_RTOL == eps * exp(2*CONDITION_LOG_LIMIT)`).
Restating `float(EPS) ** -0.5` in the test would assert only that the line was copied.

### The three landing on `2^±26` is a hazard, not a confirmation

`HESSIAN_COND_LIMIT = eps^(-1/2)`, `X_RANK_RTOL = eps^(1/2)` and
`_NEGATIVE_REDUCTION_RTOL = eps^(1/2)` are the same numeral by three different routes: one
inversion; one squaring; one solve at the worst admitted conditioning. The standing rule
warns that copying the neighbouring constant is the measured default mistake, and a family
that agrees numerically is exactly the condition under which copying looks safe. Each
docstring therefore states its own count and names the neighbour whose exponent must
**not** be borrowed — `objective.CONDITION_LOG_LIMIT` takes a *fourth* root because its
solve forms the normal equations.

### (h)/(e) — `GRAD_TOL`, where the brief's three options all fail

The brief says "derive, measure, or document explicitly why a picked value is correct".
Attempting the first is what produced the finding. Two candidate derivations exist and
both are wrong:

- **`sqrt(eps)`**, by the same argument that fixes `WHITE_COLLAPSE_LOG_LIMIT` — a model
  difference below `sqrt(eps)` is unresolvable. Measured, no converged fit gets within
  three decades of `1.49e-08`, so `ITER_CAP_SMALL_GRAD` would have become dead code.
- **`eps^(2/3)`**, the finite-difference gradient's own error floor. Measured against a
  nested-Richardson gradient at the optimum, that floor really is ~3e-10 relative to
  `|loglik|` — and it is not what stops the optimizer either.

**The floor is set by scipy's L-BFGS-B stopping rule**, which is not a property of float64
at all, so this constant is measured rather than derived and is labelled as such. What it
separates is two populations, measured over six fits, two compositions and three record
lengths:

    converged (max_iter = 200, OK)              3.46e-07 .. 2.30e-05
    genuinely unconverged (max_iter = 1, 2, 3)  1.45e-04 .. 1.84e-02

**The previous `1e-5` sat below the converged population's maximum**, so a fit that was
done would be reported `ITER_CAP_LARGE_GRAD`. That is the clamp rule inverted: a guard
below the diagnostic limit of what it guards does not fabricate a number, it makes the
milder outcome under-reachable and mislabels the fits that do reach it. `5e-5` sits 2.2x
above the converged maximum and 2.9x below the unconverged minimum. A 2-3x margin is
accepted here and would not be accepted for `HESSIAN_COND_LIMIT`, because both cap outcomes
are already `is_failure` — this splits one flagged category in two rather than calling a
bad fit good, and the docstring says so.

### What the change surfaced that the brief did not anticipate

Making `_plain_batch` honest broke `test_bic_neff_and_bic_disagree_end_to_end`, which is
not a constants failure at all. On white noise the white candidate won every series, so the
correlated candidate's ΔIC was always positive and comparing it across criteria was safe.
On data that really is correlated the correlated candidate **wins** some series, and a
winner's ΔIC is zero under both criteria by definition, so the assertion became `0 < 0`.
**A fixture made honest can invalidate an assertion that was only true because the fixture
was dishonest** — and the failure names the criterion, not the fixture, so it reads as a
regression in the thing that is still correct.

---

## P2 — make `_augment` stream

### (d) — grep for the vocabulary the task requires. **`compiled.py` is missing from it.**

The brief scopes the change to one place: "It touches the reference engine's hot loop, so:
re-pin the path-B agreement test and the MVN oracles." That sentence treats path B as a
*consumer* of the change. It is not — it is a second site of the same defect.
`CompiledEngine.score` reads

```
cols = np.ascontiguousarray(reference._augment(y, design, batch, n_time))
```

so **path B materialized the same `(B, N, 1+k_β)` block, and additionally forced it
contiguous.** One grep for `_augment` across `src/` returns two call sites, and only one of
them is in the brief.

This is the finding that most changes the work, because **path B is the adopted production
path** — the stage-1 gate chose it. Fixing path A alone would have moved
`resident_bytes_per_series` for the reference engine, left the production engine at 33 882
B/series, and produced a `tile_side` of 338 that no production run could honour. The
memory formula is already parameterized by backend, so the wrong number would have been
reported per backend, confidently, with a test pinning it.

Both engines are fixed. `_augment` is replaced by `_design_block`, which validates the
design and returns it as a `(1, N, k)` **view** when shared or `(B, N, k)` when per-point,
copying nothing; each engine reads column 0 out of `y` and the rest out of that block, per
timestep.

### (b) — batch versus series, in the numba kernel

The shared-design case must stay *one copy for the whole tile*, not one row per series —
that is the entire point of `X_term = 0` in §9.4. Inside `prange`, selecting the block row
with a branch on a boolean argument (`d = b if per_series else 0`) does not compile: numba
rejects it with `Unsupported array index type float64`, and it does so from inside the
parfor lowering pass, so the error names the indexing line rather than the branch. Passing
an explicit `block_row` index array of length B costs **8 B/series** and types cleanly. The
alternative that would have "worked" — broadcasting the shared design to `(B, N, k)` before
the call — reintroduces exactly the defect being removed, and would have looked like a fix.

### (j) — the oracles must not share a derivation path with the thing they check

Satisfied, and worth stating because it is easy to assume the agreement test carries the
weight here. The path-B agreement test compares two *implementations of the same
recursion*, so it is blind to anything both engines do identically — and both engines were
changed. What pins the values is `tests/test_kalman.py`'s MVN oracle, which builds the
covariance matrix explicitly and evaluates a multivariate-normal density; it shares no
construction with the filter. Both are green unchanged.

The stronger check available here is exactness rather than tolerance: indexing a value out
of `y` and writing it into a row is bit-identical to reading it out of a concatenated copy,
so the fix should move **no digit at all**. Measured, against the pre-fix modules loaded
straight out of git — `git show 29884aa:src/metamer/core/engines/kalman.py` into a temp
file and imported, never checked out into the working tree, per CLAUDE.md's rule about
investigative checkouts. Six comparisons, both engines × {shared design, per-point design,
no design}, on a gapped mask, over `loglik`, `normal_equations`, `rank_x`, `outcome` and
`n_used`:

**bit-identical in all thirty fields.** No tolerance, no `approx`. A tolerance-based
re-pin would have accepted a change that quietly perturbed the last digits; this says the
arithmetic is the same arithmetic in a different order of reads.

### (k)/(a) — the memory claim is a delta, so its baseline is the whole question

`resident_bytes_per_series` falling is not evidence: it is a formula, and the formula is
what changed. The standing check demands a measured slope of RSS against B in a fresh
process, and the number that matters is the **ratio to the arithmetic floor**, not the
fall. Measured: 43 392 → 8 471 B/series against a floor that went 31 542 → 6 382, i.e. a
ratio of 1.38 before and **1.33** after. Both inside ~1.5×, which is the honest reading —
*the old formula was not wrong about the code, it was wrong about the design*, and the
1.5× check would never have caught it. What caught it was reading the source.

The measured fall of **34 921 B/series exceeds the 25 200 B block itself**, because the
per-step temporaries at peak scaled with it. That is a term neither formula names, and it
is the reason the measurement is worth taking rather than inferring.

### The consequence the brief could not have anticipated

`tile_side` at 1 GB goes 171 → 338, so **production-scale B goes from ~29 000 to ~114 000**
— tile side squared. The stage-1 verdict's falsifier is stated "at production-scale B", and
its batch sweep tops out at B = 20 000, which was close to 29 000 and is not close to
114 000. **The fix moved the goalposts of its own re-measurement**, so the re-run carries a
point at the new production scale as well as the two the brief names.

### What the re-measurement falsified

The brief inherits the verdict's reasoning verbatim: "the fix removes ~25 kB/series of
memory traffic and path A is memory-bound, so path A's bound improves". Measured, the half
of that which is resolvable is **wrong**, and it is wrong in the direction that makes the
verdict *safer* — which is why reporting only the ratio would have buried it.

Per-pass seconds per series at d=3, one thread, no gaps, B=1000, in both harnesses:

| | spike 08-07 | sweep 08-07 | spike 08-10 | sweep 08-10 |
|---|---|---|---|---|
| path A | 6.88e-4 | 8.73e-4 | 6.97e-4 | 6.79e-4 |
| path B | 2.26e-4 | 2.64e-4 | **1.82e-4** | **2.07e-4** |

**Path B's gain is consistent across harnesses (−19% and −22%). Path A did not measurably
move** — +1% by one harness and −22% by the other, against a **27% between-harness
disagreement on that same quantity before the fix**. Quoting the spike's path-A row alone
(+1.3% / −11.5% / −3.8% across gap cases) would have read as "inside its own scatter" and
been an accident: the scatter that matters here is between harnesses, not within one.

The mechanism the prediction missed is the one (d) turned up: **path B was the engine
holding a per-series private copy of the shared design.** B copies of the same `(N, k)`
bytes competing for cache is a locality problem, not a bandwidth one, and it belongs to the
compiled per-series loop rather than to the batched numpy one — whose cost is the
`(B, d, n_cols)` einsum temporaries it rebuilds every timestep, which the block never
touched.

**And the (k) lesson underneath it:** the verdict quoted **±0.15** run-to-run scatter, and
the two harnesses differ by **0.57** on the ratio. A delta asserted against a baseline taken
by a different harness, on a different day, on a loaded 4-core box, is not a controlled
comparison — the falsifier survives only because it is a **threshold on an absolute value**
(≥3×, cleared by 9% at the worst measurement) rather than a claim about a change.

### A P1 constant changed a P2 measurement, and the report nearly attributed it to P2

`mean_iterations` at d=3 moved 68.7 → 90.0 and path A's utilization 0.64 → 0.84 between the
two spike runs. Neither is an effect of the streaming fix. `measure_mean_iterations` filters
to `outcome == OK` before averaging, and P1's derived `HESSIAN_COND_LIMIT` moved one of the
four sampled series from `OK` to `DEGENERATE_HESSIAN` — measured,
`['DEGENERATE_HESSIAN', 'OK', 'DEGENERATE_HESSIAN', 'OK']` at d=3. The sample is
`rng.standard_normal(...)` fitted with white + Matérn 1/2 + Matérn 3/2: **white noise fitted
with two timescales, the same fixture defect for the third time in a third place.**

This is (k) in its "every delta has a baseline" form. Two runs of the same harness across
two commits are not a controlled comparison unless every constant between them is fixed,
and here one was not. What saves the headline is that the **A:B ratio is structurally immune**
— the iteration count is common to both paths and cancels — so the falsifier is evaluated on
a quantity the confound cannot reach. The per-fit millisecond columns are not immune and
carry the new count. Recorded as open question 11 rather than fixed here, so the
re-measurement compares like with like.
