# History filters and export

## Behavior

The Electron History tab keeps plain-text search as the default and adds an
optional bounded regex builder, an ISO-compatible date range, and multi-select
action filters. Action choices are derived from the records currently stored,
with counts beside each choice; they are not a hard-coded list. Filters compose
and the result count states how many records remain visible.

## Configuration

Enter a start date, end date, or search query. Select any combination of the
recorded actions, or leave them all unselected to include every action. An
invalid date range is reported inline and returns no records until corrected.

## Failure modes

Malformed regex input keeps the search in its existing validation state and
does not broaden the result set. A date range whose start follows its end is
reported inline. Empty results say that the current filters have no matches.

## Security

Filtering and regex evaluation stay local to the renderer. Export contains the
filtered records only and uses the existing user-chosen export path; no history
is uploaded to the documentation site or a remote service.

## Verification

The contract checks cover the derived action filter and composed filtering
functions. The real off-screen capture includes the History surface and its
date/action controls. Python tests continue to cover the underlying history
recording path.

## Suggested articles

- [Electron manual client](electron-manual-client.md)
- [Memory checkpoints and local revisions](memory-checkpoints.md)
- [Tab groups and bulk close](tab-management.md)
