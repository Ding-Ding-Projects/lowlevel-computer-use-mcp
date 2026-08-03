# Local regex builder

## Behavior

`lowlevel-computer-use-regex-builder` uses the exact Python `re` engine shipped
with the active interpreter. Guided components cover escaped literals, character
classes, `^`/`$` anchors, capturing and non-capturing groups, alternation, and
quantifiers. `--pattern` enables raw editing; `--flags` accepts `i`, `m`, `s`, `x`,
`a`, and `u`. Results include syntax errors, match spans, text, numbered captures,
and named captures. `--plain-text` escapes the input before searching.

Use `--copy` to copy the effective pattern without focusing a window, or
`--export result.json` to save the complete result. Copy uses hidden `clip.exe` on
Windows. Language mode (`en`, `yue`, `bilingual`) and independent funny levels
(`--funny-en 1..5`, `--funny-yue 1..5`) persist in the user's config; pattern and
sample content never does.

## Escaping

Shell escaping happens before Python regex parsing. Prefer `--pattern` with the
shell's literal quoting. Guided `--literal` values are escaped by `re.escape`;
guided class/group/alternation values are Python regex fragments and are not
escaped.

## Limits and failure modes

- Pattern: 4,096 characters.
- Sample: 200,000 characters.
- Matches: 500 returned.
- Timeout: 0.5 seconds by default, maximum 5 seconds.
- Evaluation runs in a separate console-free process and is terminated on timeout.
- Zero-width matches use Python `finditer`, which advances safely.
- Invalid flags, syntax errors, limit errors, timeouts, and worker failures are
  distinct `error_type` values.

## Verification

`tests/test_regex_builder.py` covers valid/invalid patterns, no-match, Unicode,
multiline, zero-width, capture groups, adversarial backtracking, guided construction,
input limits, and plain-text-versus-regex behavior.
