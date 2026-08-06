# Macro Skill Template

When you (an agent) perform a multi-step UI sequence with this MCP server that the
user is likely to repeat, **save it as a reusable macro** instead of leaving it as
ad-hoc tool calls. A macro is just a Skill that records the ordered tool calls and
parameterizes the parts that vary.

## How to create one

1. Use the `skill-creator` skill if available, or simply write a `SKILL.md` to
   `~/.claude/skills/<macro-name>/SKILL.md` (Claude Code) or your client's skills
   directory.
2. Follow the structure below.

## Rules for good macros

- **Resolve handles at run time, never hard-code them.** Window/control HWNDs
  change every launch. Each replay must call `list_windows` → `list_child_windows`
  to find the current handle by title/class.
- **Prefer background-targeting tools** (`win_set_control_text`, `mouse_click` with
  `hwnd=`, `screenshot(hwnd=...)`) so replays don't steal focus.
- **Parameterize** the variable parts (text to type, file path, target app).
- **Verify** with a `screenshot(hwnd=...)` after key steps and check the result.
- For interactive **login** steps, call `show_window` / `show_headless_desktop`,
  wait for the user, then `hide_window` / `hide_headless_desktop`.

## SKILL.md skeleton

```markdown
---
name: <macro-name>
description: <when to use this macro — the trigger phrases / situation>
---

# <Macro Title>

Goal: <one line>.

Parameters:
- `text` — <what the user provides>
- `app_title` — default "<Window Title Substring>"

Steps (replay in order with this MCP server):

1. Ensure the app is running:
   - `list_windows { "title_filter": "{app_title}" }`
   - If absent, `run_command { "command": "<launch command>" }` and re-list.
2. Find the target control:
   - `list_child_windows { "window_title": "{app_title}" }`
   - Pick the control whose class is e.g. "Edit"; note its `handle`.
3. Drive it in the background:
   - `win_set_control_text { "hwnd": <edit handle>, "text": "{text}" }`
   - or `mouse_click { "hwnd": <handle>, "x": .., "y": .. }`
4. Verify:
   - `screenshot { "window_title": "{app_title}" }` and confirm the change.
5. (If a login is required) bring it forward for the human:
   - `show_window { "window_title": "{app_title}" }`
   - wait for the user to confirm sign-in
   - `hide_window { "window_title": "{app_title}" }`
```

## Worked example: "append a note in Notepad (background)"

```markdown
---
name: notepad-append
description: Append a line of text to the open Notepad without focusing it
---

1. `list_child_windows { "window_title": "Notepad" }` → find the control whose
   class contains "Edit"/"RichEdit"; capture its `handle`.
2. `win_set_control_text { "hwnd": <handle>, "text": "{text}" }`.
3. `screenshot { "window_title": "Notepad" }` to confirm.
```
