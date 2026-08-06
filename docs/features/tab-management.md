# Tab groups and bulk close

## Behavior

The Electron manual client keeps browser-style tabs in a persisted model with
order, pinned order, group membership, group labels, and collapsed state. The
Settings tab provides four independent searches: the visible strip, tabs inside
groups, group names, and every tab owned by the app. Each search has its own
plain-text-first regex builder and does not share pattern or flag state.

Users can create, rename, collapse, expand, and select groups. A row-level group
selector moves a tab between groups, while the active-tab control provides a
keyboard-friendly move path. Right-clicking a tab opens a painted, bounded menu
with its own search field, pin/unpin, group moves, and **Edit tab appearance…**;
Shift+right-click and the platform context-menu key open the appearance path.

Bulk close operates on visible tab labels only. Choose a scope, enter non-empty
text, select **Close tabs containing text** or **Close tabs not containing text**,
and preview the exact affected count and labels. Pinned tabs are excluded by
default. The optional anchored regex panel validates the real JavaScript regex
dialect and applies the same predicate to both inverse actions. Invalid or empty
queries never close anything, and the active tab is protected if the operation
would remove the whole navigation surface.

## Configuration

Open `Settings` → `Tab manager`. Tab order, pins, groups, and collapsed state are
stored through the Electron user-data settings store. Bulk scope and query are
session controls; the app deliberately does not persist a potentially dangerous
close query.

## Failure modes and security

Matching never inspects page contents or hidden data. Regex evaluation is local,
bounded by the same input size and engine behavior as the other app search
surfaces, and a malformed pattern is reported inline. Pinned tabs are visibly
protected until the user opts in. Closing is gated by the app's native
two-independent-key and full-range slider confirmation, and every completed
operation is written to local history/notifications.

## Verification

`npm run check --prefix electron` asserts the bulk actions, group controls, and
searchable context menu are present. `npm run capture --prefix electron` creates
the real Settings screenshot; the Python suite remains green at 35 tests. A
full assistive-technology pass and a live multi-window tab interaction run are
still host-specific evidence and are not inferred from static checks.

## Suggested articles

- [Electron manual client](electron-manual-client.md)
- [Quick launch and path browsers](quick-launch-browser.md)
- [Subagent lanes](subagent-lanes.md)
- [Regex builder](developer-tools/regex-builder.md)
