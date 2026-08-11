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

---

## P1 — `HESSIAN_COND_LIMIT`, and the constants around it

*(Filled in with the P1 commit.)*

---

## P2 — make `_augment` stream

*(Filled in with the P2 commit.)*
