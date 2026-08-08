# Releasing metamer

Releases are tag-driven. Pushing a `v*` tag to GitHub is the entire release action:
`.github/workflows/release.yml` builds the distributions and uploads them to PyPI.
Nothing is ever uploaded from a developer machine.

## The one-time setup (already done, recorded here so it can be re-done)

PyPI publishing uses **Trusted Publishing** (OIDC), not an API token. There is no
long-lived secret in this repository and nothing to rotate.

The publisher is registered at <https://pypi.org/manage/account/publishing/> with:

| Field | Value |
|---|---|
| PyPI project name | `metamer` |
| Owner | `killett` |
| Repository name | `metamer` |
| Workflow name | `release.yml` |
| Environment name | `pypi` |

The GitHub environment `pypi` must exist on the repository, and the PyPI account must
have 2FA enabled. There is no API for registering a trusted publisher — it is a web form.

## Cutting a release

1. Make sure `main` is green on CI and your working tree is clean.
2. Decide the version. Versions come **from the git tag** via `hatch-vcs`; there is no
   version string to edit in any file. SemVer, prefixed with `v`.
3. Tag and verify *before* pushing:

   ```
   git tag -a v0.1.0 -m "Release v0.1.0"
   ```

   ```
   python -m build
   ```

   Confirm the filenames in `dist/` say exactly `0.1.0` and the wheel is
   `py3-none-any` — this package is pure Python and a platform tag would mean
   something is wrong. A local tag is cheap to delete and redo; a PyPI upload is not.

4. Push the single tag:

   ```
   git push origin v0.1.0
   ```

   Do not use `git push --tags`. It publishes every local tag, including ones you
   were not ready to release.

5. Watch the run, then confirm the package is really installable:

   ```
   gh run watch
   ```

   ```
   pip install metamer==0.1.0
   ```

6. Publish the GitHub Release:

   ```
   gh release create v0.1.0 --verify-tag --generate-notes
   ```

## When a release fails

**PyPI filenames are immutable.** A filename that has been uploaded can never be reused,
even after the file is deleted. This governs the recovery procedure:

- **The workflow failed before anything uploaded** — safe to fix and retry the same
  version. Delete the tag locally and remotely (`git tag -d v0.1.0`,
  `git push origin :refs/tags/v0.1.0`), fix, re-tag, push.
- **Any file uploaded** — that version number is spent. Do not delete and re-upload.
  Fix the problem and release the next patch version instead.

## Python support

`requires-python` carries a floor (`>=3.12`) and deliberately **no upper cap**. Caps on
`requires-python` are unresolvable by downstream consumers and go stale the moment a new
Python ships. The supported ceiling is expressed in two places instead: the CI matrix in
`.github/workflows/test.yml` and the trove classifiers in `pyproject.toml`. When a new
Python is supported, add it to both.

## conda-forge

`metamer` is not on conda-forge. Adding it means submitting a recipe to
[staged-recipes](https://github.com/conda-forge/staged-recipes), built from the sdist
already published on PyPI. After a feedstock exists, the autotick bot opens a version-bump
PR for each PyPI release and the only manual step is approving it.
