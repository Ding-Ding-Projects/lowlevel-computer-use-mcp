# Appearance color editor

## Behavior

The Electron Settings surface includes a continuous color field and a local
translator for HEX, HEX8, RGB, RGBA, alpha, HSL, HSV, HWB, CIELab, LCH, OKLab,
OKLCH, CMYK, and common CSS names. Editing any representation converts the
same color and updates the live appearance accent. Alpha is preserved, and
out-of-sRGB values are reported before the displayed color is clamped.

Every rendered surface can open the anchored editor from right-click or the
keyboard context-menu path. A target stores its own font family, weight, size
scale, letter spacing, line height, radius, colors, and resettable override;
tabs use the same path. Global and per-target appearance values are persisted,
exported, and importable. Built-in presets include Default, High contrast, and
Paper, and users can save named presets into the exported profile.

## Configuration

Open Settings, choose the appearance editor, and enter a value in the format
shown beside the representation. The color field remains the source of truth
for the live preview; each representation has its own copy action. Use the
preset controls for a named global theme, or right-click a rendered element to
change only that target. Appearance settings are persisted with the rest of the
local Electron profile.

## Failure modes

Invalid values stay in their field and receive inline validity feedback; they
do not replace the current appearance. Conversion results identify gamut
clipping and retain alpha rather than silently dropping it. Named-color input
accepts the browser's CSS color parser and reports unknown names as invalid.

## Security

Color parsing and conversion run locally in the renderer. Values are not sent
to a service, persisted as history, or evaluated as executable code. Clipboard
copy is user initiated.

## Verification

`npm run --prefix electron start -- --appearance-self-test` runs the real
renderer conversion self-test, including round trips through every listed
space, a named CSS color, and a per-target typography override. The off-screen
capture includes the visible appearance editor and translator;
`npm run check --prefix electron` requires that capture and the renderer
contract.

## Suggested articles

- [Electron manual client](electron-manual-client.md)
- [History filters and export](history-filters.md)
- [Memory checkpoints and local revisions](memory-checkpoints.md)
