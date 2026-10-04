#!/usr/bin/env bash
# Refuse to CREATE a commit the push credential cannot PUBLISH.
#
# GitHub rejects any push that creates or updates a file under
# .github/workflows/ unless the token carries the `workflow` scope -- and the
# rejection arrives from the post-commit hook, AFTER the commit exists and
# after the sweep that validated it. On 2026-10-03 that cost a day: an OAuth
# token minted without `workflow` had pushed every commit for months, because
# none had touched .github/. This hook moves the failure to commit time, where
# it costs one line.
#
# WHAT IT COMPARES: the index (what is about to be committed) against the
# PUBLISHED tip, origin/main, not against HEAD. So it also fires when an
# earlier, still-unpushed commit carries the workflow change -- stacking more
# commits behind one that cannot be pushed only makes them all unpushable,
# because a push is linear.
#
# WHAT IT NEEDS: `gh`, because `gh auth git-credential` is this repo's
# credential helper and `gh auth status` is where the token's scopes are read.
# If gh is absent the scopes cannot be assessed and the hook says so and
# PASSES: it exists to catch a known refusal, not to invent a new one.
set -u

base=origin/main
if ! git rev-parse --verify -q "$base" >/dev/null; then
  base=HEAD
fi

changed=$(git diff --cached --name-only "$base" -- .github/workflows/ 2>/dev/null)
if [ -z "$changed" ]; then
  exit 0
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "check-push-scope: workflow files changed but gh is not installed," >&2
  echo "  so the token's scopes cannot be read; not blocking." >&2
  exit 0
fi

scopes=$(gh auth status 2>&1 | grep -i 'token scopes' || true)
if printf '%s' "$scopes" | grep -qw 'workflow'; then
  exit 0
fi

cat >&2 <<EOF
check-push-scope: this commit changes a GitHub workflow file:
$(printf '  %s\n' $changed)
but the push credential has no 'workflow' scope, so GitHub WILL refuse the
push and the commit will sit unpublished.
  scopes seen: ${scopes:-<none -- is gh logged in?>}
Fix the credential first, then commit. For a gh OAuth token (gho_...), on
the HOST (not inside the container):
  gh auth refresh -h github.com -s workflow
then relaunch so the new token is injected. Or keep the workflow change out
of this commit.
EOF
exit 1
