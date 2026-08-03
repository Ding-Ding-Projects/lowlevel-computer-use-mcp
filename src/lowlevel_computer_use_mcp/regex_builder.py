"""Bounded, local Python-regex builder and evaluator.

The builder never transmits or persists patterns or sample text. Evaluation is
isolated in a subprocess with a hard timeout to contain catastrophic backtracking.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .processes import hidden_subprocess_kwargs, pythonw_executable

MAX_PATTERN_LENGTH = 4096
MAX_SAMPLE_LENGTH = 200_000
MAX_MATCHES = 500
DEFAULT_TIMEOUT_SECONDS = 0.5
SUPPORTED_FLAGS = "imsxau"

_FLAG_VALUES = {
    "i": re.IGNORECASE,
    "m": re.MULTILINE,
    "s": re.DOTALL,
    "x": re.VERBOSE,
    "a": re.ASCII,
    "u": re.UNICODE,
}


def parse_flags(flags: str) -> int:
    unknown = sorted(set(flags.lower()) - set(SUPPORTED_FLAGS))
    if unknown:
        raise ValueError(
            f"Unsupported flags: {''.join(unknown)}. Supported: {SUPPORTED_FLAGS}"
        )
    value = 0
    for flag in flags.lower():
        value |= _FLAG_VALUES[flag]
    return value


@dataclass
class GuidedBuilder:
    """Construct a Python ``re`` pattern from explicit guided components."""

    parts: list[str] = field(default_factory=list)
    anchor_start: bool = False
    anchor_end: bool = False

    def literal(self, value: str) -> "GuidedBuilder":
        self.parts.append(re.escape(value))
        return self

    def character_class(self, value: str, negate: bool = False) -> "GuidedBuilder":
        self.parts.append(f"[{'^' if negate else ''}{value}]")
        return self

    def group(self, value: str, capture: bool = True) -> "GuidedBuilder":
        self.parts.append(f"({value})" if capture else f"(?:{value})")
        return self

    def quantify_last(self, quantifier: str) -> "GuidedBuilder":
        if not self.parts:
            raise ValueError("Add a component before applying a quantifier.")
        if not re.fullmatch(r"(?:[?*+]|\{\d+(?:,\d*)?\})\??", quantifier):
            raise ValueError(
                "Quantifier must be ?, *, +, {n}, {n,}, or {n,m}, optionally lazy."
            )
        self.parts[-1] = f"(?:{self.parts[-1]}){quantifier}"
        return self

    def alternate(self, value: str) -> "GuidedBuilder":
        current = "".join(self.parts)
        self.parts = [f"(?:{current}|{value})"]
        return self

    def pattern(self) -> str:
        return (
            ("^" if self.anchor_start else "")
            + "".join(self.parts)
            + ("$" if self.anchor_end else "")
        )


def _evaluate_inline(pattern: str, flags: int, sample: str) -> dict[str, Any]:
    try:
        compiled = re.compile(pattern, flags)
        matches = []
        truncated = False
        for index, match in enumerate(compiled.finditer(sample)):
            if index >= MAX_MATCHES:
                truncated = True
                break
            matches.append(
                {
                    "span": list(match.span()),
                    "text": match.group(0),
                    "groups": list(match.groups()),
                    "named_groups": match.groupdict(),
                }
            )
        return {
            "ok": True,
            "matches": matches,
            "count": len(matches),
            "truncated": truncated,
        }
    except re.error as exc:
        return {"ok": False, "error": str(exc), "error_type": "syntax"}
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "error_type": "runtime",
        }


def _worker_main() -> None:
    payload = json.load(sys.stdin)
    result = _evaluate_inline(
        payload["pattern"], int(payload["flags"]), payload["sample"]
    )
    # Keep the worker protocol ASCII-safe because pythonw may inherit a legacy
    # Windows code page even when the parent pipe transports Unicode data.
    json.dump(result, sys.stdout, ensure_ascii=True)


def evaluate(
    pattern: str,
    sample: str,
    flags: str = "",
    *,
    plain_text: bool = False,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Evaluate locally with bounded input, match count, and wall-clock time."""
    if len(pattern) > MAX_PATTERN_LENGTH:
        return {
            "ok": False,
            "error": f"Pattern exceeds {MAX_PATTERN_LENGTH} characters.",
            "error_type": "limit",
        }
    if len(sample) > MAX_SAMPLE_LENGTH:
        return {
            "ok": False,
            "error": f"Sample exceeds {MAX_SAMPLE_LENGTH} characters.",
            "error_type": "limit",
        }
    if timeout_seconds <= 0 or timeout_seconds > 5:
        return {
            "ok": False,
            "error": "Timeout must be greater than 0 and at most 5 seconds.",
            "error_type": "limit",
        }
    try:
        flag_value = parse_flags(flags)
    except ValueError as exc:
        return {"ok": False, "error": str(exc), "error_type": "flags"}

    effective_pattern = re.escape(pattern) if plain_text else pattern
    worker = [
        pythonw_executable(),
        "-m",
        "lowlevel_computer_use_mcp.regex_builder",
        "--_worker",
    ]
    try:
        proc = subprocess.run(
            worker,
            input=json.dumps(
                {"pattern": effective_pattern, "flags": flag_value, "sample": sample}
            ),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
            **hidden_subprocess_kwargs(),
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "error": f"Evaluation exceeded {timeout_seconds:.3f}s and was terminated.",
            "error_type": "timeout",
        }
    try:
        result = json.loads(proc.stdout)
    except (TypeError, ValueError):
        detail = (proc.stderr or "").strip()
        return {
            "ok": False,
            "error": "Evaluator exited without a valid result."
            + (f" {detail}" if detail else ""),
            "error_type": "runtime",
        }
    result.update(
        {
            "pattern": effective_pattern,
            "raw_input": pattern,
            "plain_text": plain_text,
            "flags": flags.lower(),
            "engine": "Python re",
            "dialect": f"Python {sys.version_info.major}.{sys.version_info.minor}",
        }
    )
    return result


def copy_pattern(pattern: str) -> None:
    """Copy without opening or focusing a window."""
    if os.name == "nt":
        subprocess.run(
            ["clip.exe"],
            input=pattern,
            text=True,
            check=True,
            **hidden_subprocess_kwargs(),
        )
        return
    tool = "pbcopy" if sys.platform == "darwin" else "xclip"
    cmd = [tool] if tool == "pbcopy" else [tool, "-selection", "clipboard"]
    subprocess.run(cmd, input=pattern, text=True, check=True)


def _settings_path() -> Path:
    return Path.home() / ".config" / "lowlevel-computer-use-mcp" / "regex-builder.json"


def load_settings() -> dict[str, Any]:
    defaults = {"language": "en", "funny_en": 1, "funny_yue": 1}
    path = _settings_path()
    if not path.exists():
        return defaults
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return defaults
    return {
        "language": data.get("language", "en")
        if data.get("language") in {"en", "yue", "bilingual"}
        else "en",
        "funny_en": max(1, min(5, int(data.get("funny_en", 1)))),
        "funny_yue": max(1, min(5, int(data.get("funny_yue", 1)))),
    }


def save_settings(language: str, funny_en: int, funny_yue: int) -> None:
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"language": language, "funny_en": funny_en, "funny_yue": funny_yue},
            indent=2,
        ),
        encoding="utf-8",
    )


def _build_from_args(args: argparse.Namespace) -> str:
    if args.pattern is not None:
        return args.pattern
    builder = GuidedBuilder(anchor_start=args.start, anchor_end=args.end)
    for value in args.literal:
        builder.literal(value)
    for value in args.char_class:
        builder.character_class(value)
    for value in args.group:
        builder.group(value)
    for value in args.non_capture_group:
        builder.group(value, capture=False)
    for value in args.quantifier:
        builder.quantify_last(value)
    for value in args.alternate:
        builder.alternate(value)
    return builder.pattern()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build and safely test Python re patterns locally (no network or sample persistence)."
    )
    parser.add_argument(
        "--pattern", help="Raw Python re pattern; overrides guided components"
    )
    parser.add_argument(
        "--literal", action="append", default=[], help="Append an escaped literal"
    )
    parser.add_argument(
        "--char-class",
        action="append",
        default=[],
        help="Append class contents, e.g. A-Z0-9",
    )
    parser.add_argument(
        "--group",
        action="append",
        default=[],
        help="Append a capturing group expression",
    )
    parser.add_argument(
        "--non-capture-group",
        action="append",
        default=[],
        help="Append a non-capturing group",
    )
    parser.add_argument(
        "--alternate",
        action="append",
        default=[],
        help="Alternate the built pattern with an expression",
    )
    parser.add_argument(
        "--quantifier",
        action="append",
        default=[],
        help="Apply a quantifier to the latest component",
    )
    parser.add_argument("--start", action="store_true", help="Add ^ anchor")
    parser.add_argument("--end", action="store_true", help="Add $ anchor")
    parser.add_argument(
        "--flags", default="", help=f"Python re flags: {SUPPORTED_FLAGS}"
    )
    parser.add_argument(
        "--sample", default="", help="Local sample text (max 200,000 characters)"
    )
    parser.add_argument(
        "--plain-text",
        action="store_true",
        help="Escape the pattern and perform literal search",
    )
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument(
        "--copy",
        action="store_true",
        help="Copy the effective pattern without focusing a window",
    )
    parser.add_argument(
        "--export", type=Path, help="Export pattern metadata and results as JSON"
    )
    parser.add_argument("--language", choices=["en", "yue", "bilingual"])
    parser.add_argument("--funny-en", type=int, choices=range(1, 6), metavar="1..5")
    parser.add_argument("--funny-yue", type=int, choices=range(1, 6), metavar="1..5")
    args = parser.parse_args()

    settings = load_settings()
    language = args.language or settings["language"]
    funny_en = args.funny_en or settings["funny_en"]
    funny_yue = args.funny_yue or settings["funny_yue"]
    if args.language or args.funny_en or args.funny_yue:
        save_settings(language, funny_en, funny_yue)

    try:
        pattern = _build_from_args(args)
    except ValueError as exc:
        print(
            json.dumps(
                {"ok": False, "error": str(exc), "error_type": "builder"}, indent=2
            )
        )
        raise SystemExit(2)
    result = evaluate(
        pattern,
        args.sample,
        args.flags,
        plain_text=args.plain_text,
        timeout_seconds=args.timeout,
    )
    result["language"] = language
    result["funny_levels"] = {"en": funny_en, "yue": funny_yue}
    if args.copy and result.get("ok"):
        copy_pattern(result["pattern"])
        result["copied"] = True
    if args.export:
        args.export.write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        result["exported_to"] = str(args.export)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    raise SystemExit(0 if result.get("ok") else 2)


if __name__ == "__main__":
    if sys.argv[1:] == ["--_worker"]:
        _worker_main()
    else:
        main()
