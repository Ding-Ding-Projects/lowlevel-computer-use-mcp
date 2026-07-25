# Repository agent instructions

## Desktop automation preference

- Prefer a headless desktop for GUI automation whenever the task and application support it. Use the visible interactive desktop only when headless operation is unavailable or human-visible interaction is required, and return to headless operation afterward when practical.
- When switching a headless desktop into interactive view, always provide a short, concrete `instruction` for the non-dismissible safety banner. Never obscure or disable its **EMERGENCY EXIT** button.

## Shared repository completion memory

- Every task that changes this repository must end with all intended task work committed and pushed.
- Review every local and remote branch, linked worktree, and stash before cleanup. Preserve useful work in commits, integrate every completed branch or worktree into the default branch, and verify each source tip is an ancestor of the pushed remote default branch.
- Never delete a branch, worktree, stash, or checkout that contains uncommitted, unmerged, or unpushed work.
- After remote proof, remove merged temporary branches, linked worktrees, their on-disk directories, stale worktree metadata, and redundant stashes.
- The final handoff target is a clean default checkout, no staged, unstaged, untracked, or stashed task work, and zero divergence from the remote default branch. Preserve and report unrelated pre-existing work instead of discarding it.
- Record significant completion and cleanup decisions in a repository-tracked handoff or memory file and push that update.
- Never force-push unless the user explicitly requests a history rewrite and the consequences have been reviewed.
