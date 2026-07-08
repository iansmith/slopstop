# merge-cleanup.md — Step 8: Local branch cleanup + propagate merge to other remotes

Used by `/slopstop:merge` Step 8. Skip entirely if `merge-only`.

## 8a. Switch to the base and pull the merge

```
git fetch $ORIGIN_REMOTE --prune
git switch $baseRefName
git pull --ff-only $ORIGIN_REMOTE $baseRefName
```

## 8b. Push the merged-onto branch to all other remotes

The merge only updated $ORIGIN_REMOTE. If the repo has any other remotes configured (e.g. a personal fork to keep in sync, a mirror for backup, an internal-vs-public pair), propagate `$baseRefName` to them now.

```
for remote in $(git remote); do
  [ "$remote" = "$ORIGIN_REMOTE" ] && continue
  git push "$remote" "$baseRefName" || echo "  warning: push to $remote failed (continuing)"
done
```

This is best-effort — a failed push to a fork doesn't roll anything back. The merge already landed on $ORIGIN_REMOTE (the source of truth); the warning surfaces so the user knows to fix the mirror manually. If `git remote` returns only `$ORIGIN_REMOTE`, this loop is a no-op.

## 8c. Remove the worktree or delete the local feature branch

The simple rule: "clean up if the PR is logically merged." Cleanup is worktree-aware — the branch may be checked out in an agent worktree rather than as a local branch:

1. **Worktree check:** `git worktree list --porcelain | grep -B2 "branch refs/heads/$BRANCH"` — extract the worktree path if found.
   - `git worktree remove "$WORKTREE_PATH"` (removes the directory; the branch is no longer checked out anywhere, but the branch ref still exists — `worktree remove` detaches, does not delete).
   - `git branch -D $BRANCH` (delete the now-orphaned branch ref).
   - If `git worktree remove` fails (e.g. worktree still dirty): surface the error, leave the worktree in place, continue to Step 9 — the merge succeeded.

2. **Local branch check (no registered worktree):** `git rev-parse --verify "refs/heads/$BRANCH"`. If the branch exists locally:
   - `git branch -D $BRANCH` (force-delete — `state == MERGED` confirms squash/rebase histories are handled correctly).

3. **Neither:** the branch exists only remotely or was already cleaned up. Skip — nothing to delete locally. Note in the Step 9 `Branch:` line.

If the working tree on the new base is dirty after the Step 8a pull (shouldn't happen), refuse to delete and report.
