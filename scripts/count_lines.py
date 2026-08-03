"""Print the reproducible source/test/markup line table used by releases."""

from __future__ import annotations

import argparse
import subprocess
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT_EXTENSIONS = {
    ".c", ".cc", ".cpp", ".cjs", ".css", ".go", ".h", ".hpp", ".html",
    ".java", ".js", ".json", ".md", ".mjs", ".py", ".rs", ".sh", ".toml",
    ".ts", ".tsx", ".txt", ".vue", ".yaml", ".yml",
}
EXCLUDED_NAMES = {"package-lock.json", "uv.lock", "pnpm-lock.yaml", "yarn.lock"}
EXCLUDED_PREFIXES = (".git/", ".venv/", "electron/node_modules/", "dist/", "build/")


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, encoding="utf-8", errors="replace")


def tracked_files() -> list[str]:
    raw = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
    return [item.decode("utf-8") for item in raw.split(b"\0") if item]


def included(path: str) -> bool:
    normalized = path.replace("\\", "/")
    return (
        Path(path).suffix.lower() in TEXT_EXTENSIONS
        and Path(path).name not in EXCLUDED_NAMES
        and not normalized.startswith(EXCLUDED_PREFIXES)
    )


def category(path: str) -> str:
    normalized = path.replace("\\", "/")
    if normalized.startswith("tests/") or "/tests/" in normalized or Path(path).name.startswith("test_"):
        return "tests"
    if Path(path).suffix.lower() in {".css", ".html", ".vue"}:
        return "styles/markup"
    if normalized.startswith("docs/") or Path(path).suffix.lower() == ".md":
        return "documentation"
    return "source"


def line_counts(path: str) -> tuple[int, int]:
    data = (ROOT / path).read_text(encoding="utf-8", errors="replace")
    lines = data.splitlines()
    return len(lines), sum(bool(line.strip()) for line in lines)


def agent_commits() -> set[str]:
    records = git("log", "--all", "--format=%H%x1f%an%x1f%ae%x1f%B%x1e").split("\x1e")
    result: set[str] = set()
    for record in records:
        fields = record.split("\x1f", 3)
        if len(fields) != 4:
            continue
        commit, author, email, body = fields
        marker = f"{author} {email} {body}".lower()
        if any(token in marker for token in ("github-actions[bot]", "claude", "codex", "openai", "smoke user", "co-authored-by: agent")):
            result.add(commit)
    return result


def agent_lines(paths: list[str], commits: set[str]) -> int:
    total = 0
    for path in paths:
        try:
            blame = git("blame", "--line-porcelain", "--", path).splitlines()
        except subprocess.CalledProcessError:
            continue
        for line in blame:
            if line and not line.startswith((" ", "author ", "author-mail ", "author-time ", "author-tz ", "committer ", "committer-mail ", "committer-time ", "committer-tz ", "summary ", "filename ", "previous ", "boundary")):
                commit = line.split(" ", 1)[0]
                if commit in commits:
                    total += 1
    return total


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--markdown", action="store_true")
    args = parser.parse_args()
    paths = [path for path in tracked_files() if included(path)]
    rows: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0, 0])
    paths_by_category: dict[str, list[str]] = defaultdict(list)
    for path in paths:
        total, nonblank = line_counts(path)
        row = rows[category(path)]
        row[0] += total
        row[1] += nonblank
        row[2] += 1
        paths_by_category[category(path)].append(path)
    total_lines = sum(row[0] for row in rows.values())
    total_nonblank = sum(row[1] for row in rows.values())
    commits = agent_commits()
    for name, category_paths in paths_by_category.items():
        rows[name][3] = agent_lines(category_paths, commits)
    attribution = sum(row[3] for row in rows.values())
    if args.markdown:
        print("## Reproducible line count")
        print("\n| Category | Files | Total lines | Non-blank lines | Agent-attributed lines |")
        print("|---|---:|---:|---:|---:|")
        for name in sorted(rows):
            files, lines, nonblank, agent = rows[name][2], rows[name][0], rows[name][1], rows[name][3]
            print(f"| {name} | {files} | {lines} | {nonblank} | {agent} |")
        print(f"| **Project total** | **{len(paths)}** | **{total_lines}** | **{total_nonblank}** | **{attribution}** |")
        print(f"| Grand total counted | {len(paths)} | {total_lines} | {total_nonblank} | {attribution} |")
        print("\nExcluded: vendored/dependency directories, build output, binary assets, and lockfiles; agent attribution uses surviving `git blame` lines from automation/agent-marked commits.")
    else:
        print({"categories": rows, "project_total": {"files": len(paths), "lines": total_lines, "nonblank": total_nonblank}, "agent_attributed_lines": attribution})


if __name__ == "__main__":
    main()
