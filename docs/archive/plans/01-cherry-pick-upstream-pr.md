# Cherry-Pick an Upstream PR into This Fork

## Context

This fork (`joeblackwaslike/safaribooks`) already has `upstream` configured pointing to `lorenzodifuccia/safaribooks`. The goal is to bring in commits from a specific upstream PR without merging the entire upstream history.

## Procedure

### 1. Fetch upstream and identify the PR's commits

```bash
# Fetch upstream refs (including PR heads)
git fetch upstream

# Fetch the specific PR branch by number (creates a local ref)
git fetch upstream pull/<PR_NUMBER>/head:upstream-pr-<PR_NUMBER>
```

### 2. Inspect what you're about to cherry-pick

```bash
# See the commits on that PR branch vs upstream/master
git log --oneline upstream/master..upstream-pr-<PR_NUMBER>

# Review the diff
git diff upstream/master...upstream-pr-<PR_NUMBER>
```

### 3. Create a feature branch on your fork

```bash
git checkout -b cherry-pick/pr-<PR_NUMBER>
```

### 4. Cherry-pick

**Single commit PR:**
```bash
git cherry-pick <COMMIT_SHA>
```

**Multi-commit PR (preserve each commit):**
```bash
git cherry-pick <OLDEST_SHA>^..<NEWEST_SHA>
```

**Multi-commit PR (squash into one):**
```bash
git cherry-pick --no-commit <OLDEST_SHA>^..<NEWEST_SHA>
git commit -m "Cherry-pick upstream PR #<PR_NUMBER>: <description>"
```

### 5. Resolve conflicts (if any)

```bash
# After resolving conflicts in your editor:
git add <resolved_files>
git cherry-pick --continue

# Or abort if it's too messy:
git cherry-pick --abort
```

### 6. Push and optionally PR

```bash
git push -u origin cherry-pick/pr-<PR_NUMBER>

# Create a PR on your fork if desired:
gh pr create --title "Cherry-pick upstream PR #<PR_NUMBER>" \
  --body "Cherry-picked from lorenzodifuccia/safaribooks#<PR_NUMBER>"
```

## Quick-Reference One-Liner

For a simple single-commit cherry-pick, the entire flow is:

```bash
git fetch upstream pull/379/head:upstream-pr-379 && \
git checkout -b cherry-pick/pr-379 && \
git cherry-pick upstream-pr-379 && \
git push -u origin cherry-pick/pr-379
```

Replace `379` with the actual PR number.
