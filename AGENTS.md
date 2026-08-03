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

## Sanitized shared agent-instructions mirror

This section is a repository-local mirror of the shared agent instructions. It
is intentionally sanitized for a public repository; edit the canonical global
instructions instead of treating this copy as the source of truth.

### Scope and safety

- A current user request and platform policy take precedence. Never expose
  credentials, discard unrelated work, bypass access controls, or infer consent
  for a materially different action.
- Apply the rules to every app, page, landing page, documentation surface,
  settings panel, dialog, and nested component. Small or documentation-only
  surfaces are not silent exemptions.
- Route computer-use work through this project's headless path whenever it can
  perform the task. A visible fallback must name the limitation, use the
  safety banner and emergency exit, and return to headless operation promptly.
- Keep child processes hidden, avoid shell execution where possible, preserve
  the user's input focus, and never create a terminal flash as part of normal
  app operation.
- For secrets, use a temporary least-privileged secure input flow; never ask
  for a secret in chat, source, arguments, URLs, logs, screenshots, or history.

### Engineering and repository completion

- Inspect local instructions, existing changes, branches, linked worktrees, and
  stashes before editing. Preserve unrelated work and use reversible changes.
- Use the `git` CLI for Git and the `gh` CLI for GitHub. Finish intended work
  committed on the default branch, pushed, and proven present on the pushed
  default branch. Never force-push or delete work that is uncommitted, unmerged,
  or unpushed.
- Keep README, categorized feature articles, roadmap, handoff, wiki, Pages, and
  API/Postman documentation accurate. Every feature article states behaviour,
  configuration, failure modes, security, and verification, then suggests
  related articles.
- Scan open issues on every touched repository. Work on actionable issues with
  start/progress/finish evidence; visible-surface issue comments require a real
  capture of that issue's own surface.
- Each push and dispatch workflow tests before publishing one unique, real,
  non-draft release with the appropriate installer. Verify the run, release,
  artifacts, Pages, and live endpoint; never predict green checks.

### User-facing product requirements

- Provide English, playful Hong Kong Cantonese, and bilingual modes, with
  independent persisted funny-level controls for both languages. Humour changes
  voice only; facts, paths, commands, errors, warnings, and affected data stay
  exact. Keep optional narration off by default and assistive-technology-safe.
- Use Material Design 3 with accessible roles, keyboard focus, contrast,
  reduced-motion support, correct sizing, no clipping, and non-blocking
  notifications for information and non-decision errors. Use blocking dialogs
  only for decisions, consent, credentials, or destructive confirmation.
- Every app and Pages surface has browser-style tabs with overflow, reorder,
  pin, group, persistence, four independent tab searches, and a full local
  regex builder beside every search. Bulk actions preview exact scope/count,
  protect pinned and unsaved work, and report exclusions honestly.
- Every rendered element has an anchored appearance editor and reset path.
  Appearance includes theme, density, seed/accent, font family/scale/weight,
  Word-depth typography, continuous color selection, translated color formats,
  alpha, gamut/clipping, contrast, import/export, presets, and persistence.
- Every list/table/grid supports multi-select and complete bulk actions with
  reviewable previews, progress/cancellation for long work, and undo or an
  explicit explanation when undo is impossible. Every owned record is
  exportable in faithful formats.
- Every app provides local append-only version history for documents, records,
  settings, accounts, and connections. Restores create new revisions and keep
  history searchable by action, date, text, and regex.
- Include an in-app complete changelog with dates, exact commit links, search,
  date filtering, export, and honest empty states; include a discoverable
  command palette containing every command, setting, and destination.
- Bundle local assets only. Releases use the verified public dim-sum catalog for
  a unique English/Traditional-Chinese code name and link to its published
  asset without copying or generating images in this repository.
