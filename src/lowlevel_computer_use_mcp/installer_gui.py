"""Tkinter GUI installer for lowlevel-computer-use-mcp.

One-click helper to:
  * install Python dependencies (uv sync)
  * register the server with Claude Code and Codex
  * install / remove the boot-startup scheduled task (optionally as admin)
  * install AutoHotkey (winget)
  * show current registration / startup status

Run with:  uv run lowlevel-computer-use-mcp-installer
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from .process import run_hidden

SERVER_KEY = "lowlevel-computer-use"
CODEX_BLOCK_MARKER = f"[mcp_servers.{SERVER_KEY}]"


def repo_dir() -> Path:
    return Path(__file__).resolve().parents[2]


def uv_path() -> str:
    found = shutil.which("uv")
    if found:
        return found
    candidate = Path.home() / ".local" / "bin" / ("uv.exe" if os.name == "nt" else "uv")
    return str(candidate) if candidate.exists() else "uv"


def server_args() -> list[str]:
    return hidden_server_command()[1]


def server_command() -> str:
    return hidden_server_command()[0]


def ensure_uv(log) -> bool:
    """Make sure uv is installed, bootstrapping it if necessary. Returns True if available."""
    if shutil.which("uv") or (Path.home() / ".local" / "bin" / "uv.exe").exists():
        return True
    log("uv not found - attempting to install it automatically...")
    winget = shutil.which("winget")
    if winget:
        rc = _run([winget, "install", "-e", "--id", "astral-sh.uv",
                   "--accept-source-agreements", "--accept-package-agreements"], log)
        if rc == 0 and (shutil.which("uv") or (Path.home() / ".local" / "bin" / "uv.exe").exists()):
            return True
    log("Trying pip install uv ...")
    import sys
    _run([sys.executable, "-m", "pip", "install", "--user", "uv"], log)
    return bool(shutil.which("uv") or (Path.home() / ".local" / "bin" / "uv.exe").exists())


# --------------------------------------------------------------------------- #
# Actions (each takes a log callback)
# --------------------------------------------------------------------------- #
def _run(cmd: list[str], log, cwd: str | None = None) -> int:
    log("$ " + " ".join(cmd))
    try:
        proc = run_hidden(cmd, capture_output=True, text=True, cwd=cwd, timeout=600)
        if proc.stdout.strip():
            log(proc.stdout.strip())
        if proc.stderr.strip():
            log(proc.stderr.strip())
        log(f"(exit {proc.returncode})")
        return proc.returncode
    except Exception as exc:  # noqa: BLE001
        log(f"ERROR: {type(exc).__name__}: {exc}")
        return 1


def action_uv_sync(log) -> None:
    log("== Installing dependencies (uv sync) ==")
    if not ensure_uv(log):
        log("Could not obtain uv automatically. Install it from https://docs.astral.sh/uv/ and retry.\n")
        return
    rc = _run([uv_path(), "sync"], log, cwd=str(repo_dir()))
    log("Dependencies installed.\n" if rc == 0 else "Dependency installation failed.\n")


def action_register_claude(log) -> None:
    log("== Registering with Claude Code (user scope) ==")
    claude = shutil.which("claude")
    if claude:
        _run([claude, "mcp", "remove", "--scope", "user", SERVER_KEY], log)
        rc = _run(
            [claude, "mcp", "add", SERVER_KEY, "--scope", "user", "--", server_command(), *server_args()],
            log,
        )
        if rc == 0:
            log("Registered via Claude CLI.\n")
            return
        log("Claude CLI failed; falling back to editing ~/.claude.json")
    _register_claude_json(log)


def _register_claude_json(log) -> None:
    path = Path.home() / ".claude.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception as exc:  # noqa: BLE001
        log(f"Could not read {path}: {exc}")
        return
    data.setdefault("mcpServers", {})
    data["mcpServers"][SERVER_KEY] = {
        "type": "stdio",
        "command": server_command(),
        "args": server_args(),
        "env": {},
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    log(f"Wrote {SERVER_KEY} into {path}\n")


def action_enable_yolo(log) -> None:
    """YOLO by default: auto-approve this server's tools in Claude Code (no prompts)."""
    log("== Enabling YOLO (auto-approve this server's tools) ==")
    path = Path.home() / ".claude" / "settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception as exc:  # noqa: BLE001
        log(f"Could not read {path}: {exc}")
        return
    perms = data.setdefault("permissions", {})
    allow = perms.setdefault("allow", [])
    rule = f"mcp__{SERVER_KEY}__*"
    if rule not in allow:
        allow.append(rule)
        log(f"Added allow rule: {rule}")
    else:
        log("Allow rule already present.")
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    log("Codex: approval_policy is set globally in ~/.codex/config.toml (set to 'never' for YOLO).\n")


def action_register_codex(log) -> None:
    log("== Registering with Codex (~/.codex/config.toml) ==")
    codex = shutil.which("codex")
    if codex:
        _run([codex, "mcp", "remove", SERVER_KEY], log)
        rc = _run([codex, "mcp", "add", SERVER_KEY, "--", server_command(), *server_args()], log)
        if rc == 0:
            log("Registered via Codex CLI with the console-free launcher.\n")
            return
        log("Codex CLI failed; falling back to an additive config entry.")
    path = Path.home() / ".codex" / "config.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if CODEX_BLOCK_MARKER in existing:
        log("Already present in config.toml.\n")
        return
    executable = server_command().replace("'", "''")
    args = ", ".join(f"'{a}'" for a in server_args())
    block = (
        f"\n{CODEX_BLOCK_MARKER}\n"
        f"command = '{executable}'\n"
        f"args = [{args}]\n"
        f"startup_timeout_sec = 60\n"
    )
    with path.open("a", encoding="utf-8") as f:
        f.write(block)
    log(f"Appended block to {path}\n")


def action_register_opencode(log) -> None:
    """Register the console-free stdio server in OpenCode's user config."""
    log("== Registering with OpenCode (~/.config/opencode/opencode.json) ==")
    config_dir = Path.home() / ".config" / "opencode"
    jsonc_path = config_dir / "opencode.jsonc"
    path = jsonc_path if jsonc_path.exists() else config_dir / "opencode.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception as exc:  # noqa: BLE001
        log(f"Could not safely update {path}: {exc}")
        return
    mcp = data.setdefault("mcp", {})
    # Migrate the short-lived nested draft written by older installer builds.
    nested = mcp.pop("servers", None)
    if isinstance(nested, dict):
        mcp.update(nested)
    mcp[SERVER_KEY] = {
        "type": "local",
        "command": [server_command(), *server_args()],
        "enabled": True,
    }
    data.setdefault("$schema", "https://opencode.ai/config.json")
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    log(f"Registered {SERVER_KEY} with the console-free launcher in {path}.\n")


def action_install_startup(admin: bool, port: int, log) -> None:
    log(f"== Installing boot startup (admin={admin}, port={port}) ==")
    cmd = [server_command(), *server_args(), "install-startup", "--port", str(port)]
    if admin:
        cmd.append("--admin-task")
    _run(cmd, log, cwd=str(repo_dir()))
    log("Done.\n")


def action_uninstall_startup(log) -> None:
    log("== Removing boot startup ==")
    _run([server_command(), *server_args(), "uninstall-startup"], log, cwd=str(repo_dir()))
    log("Done.\n")


def action_install_ahk(log) -> None:
    log("== Installing AutoHotkey (winget) ==")
    try:
        from . import ahk
        if ahk.find_ahk():
            log("AutoHotkey is already installed.\n")
            return
    except Exception:
        pass
    winget = shutil.which("winget")
    if not winget:
        log("winget not found. Install AutoHotkey manually from https://www.autohotkey.com\n")
        return
    rc = _run([winget, "install", "-e", "--id", "AutoHotkey.AutoHotkey", "--accept-source-agreements",
          "--accept-package-agreements"], log)
    log("Done.\n" if rc == 0 else "AutoHotkey installation failed.\n")


def action_status(log) -> None:
    log("== Status ==")
    claude_json = Path.home() / ".claude.json"
    codex_toml = Path.home() / ".codex" / "config.toml"
    opencode_dir = Path.home() / ".config" / "opencode"
    opencode_json = (
        opencode_dir / "opencode.jsonc"
        if (opencode_dir / "opencode.jsonc").exists()
        else opencode_dir / "opencode.json"
    )
    claude_ok = False
    if claude_json.exists():
        try:
            claude_ok = SERVER_KEY in json.loads(claude_json.read_text(encoding="utf-8")).get("mcpServers", {})
        except Exception:  # noqa: BLE001
            pass
    codex_ok = codex_toml.exists() and CODEX_BLOCK_MARKER in codex_toml.read_text(encoding="utf-8")
    opencode_ok = False
    if opencode_json.exists():
        try:
            opencode_ok = SERVER_KEY in json.loads(opencode_json.read_text(encoding="utf-8")).get("mcp", {})
        except Exception:  # noqa: BLE001
            pass
    log(f"Repo:        {repo_dir()}")
    log(f"uv:          {uv_path()}")
    log(f"Claude Code: {'registered' if claude_ok else 'not registered'}")
    log(f"Codex:       {'registered' if codex_ok else 'not registered'}")
    log(f"OpenCode:    {'registered' if opencode_ok else 'not registered'}")
    _run([server_command(), *server_args(), "startup-status"], log, cwd=str(repo_dir()))
    log("")


# --------------------------------------------------------------------------- #
# GUI
# --------------------------------------------------------------------------- #
def main() -> None:
    root = tk.Tk()
    root.title("lowlevel-computer-use-mcp — Installer")
    root.geometry("760x560")

    header = ttk.Label(
        root,
        text="Low-Level Computer-Use MCP — Setup",
        font=("Segoe UI", 14, "bold"),
    )
    header.pack(pady=(12, 2))
    ttk.Label(root, text=str(repo_dir()), foreground="#666").pack()

    log_frame = ttk.Frame(root)
    log_frame.pack(fill="both", expand=True, padx=12, pady=8)
    text = tk.Text(log_frame, height=16, wrap="word", bg="#0f111a", fg="#d7dae0",
                   insertbackground="#d7dae0", font=("Consolas", 9))
    scroll = ttk.Scrollbar(log_frame, command=text.yview)
    text.configure(yscrollcommand=scroll.set)
    text.pack(side="left", fill="both", expand=True)
    scroll.pack(side="right", fill="y")

    def log(msg: str) -> None:
        root.after(0, lambda: (text.insert("end", msg + "\n"), text.see("end")))

    def run_async(fn, *args) -> None:
        threading.Thread(target=lambda: fn(*args, log), daemon=True).start()

    # Options row
    opts = ttk.Frame(root)
    opts.pack(fill="x", padx=12)
    admin_var = tk.BooleanVar(value=False)
    port_var = tk.StringVar(value="8765")
    ttk.Checkbutton(opts, text="Startup as Administrator", variable=admin_var).pack(side="left")
    ttk.Label(opts, text="   HTTP port:").pack(side="left")
    ttk.Entry(opts, textvariable=port_var, width=7).pack(side="left")

    def _port() -> int:
        try:
            return int(port_var.get())
        except ValueError:
            return 8765

    # Buttons
    btns = ttk.Frame(root)
    btns.pack(fill="x", padx=12, pady=10)

    def add(col, row, label, fn):
        b = ttk.Button(btns, text=label, command=fn, width=26)
        b.grid(column=col, row=row, padx=4, pady=4, sticky="ew")

    add(0, 0, "1. Install dependencies", lambda: run_async(action_uv_sync))
    add(1, 0, "2. Register Claude Code", lambda: run_async(action_register_claude))
    add(2, 0, "3. Register Codex", lambda: run_async(action_register_codex))
    add(0, 1, "Install boot startup", lambda: run_async(action_install_startup, admin_var.get(), _port()))
    add(1, 1, "Remove boot startup", lambda: run_async(action_uninstall_startup))
    add(2, 1, "Install AutoHotkey", lambda: run_async(action_install_ahk))
    add(0, 2, "Check status", lambda: run_async(action_status))
    add(1, 2, "Register OpenCode", lambda: run_async(action_register_opencode))
    add(2, 2, "Enable YOLO (no prompts)", lambda: run_async(action_enable_yolo))

    def do_all() -> None:
        def seq(_log):
            _log("===== AUTOMATIC INSTALL =====")
            action_uv_sync(_log)
            action_install_ahk(_log)
            action_register_claude(_log)
            action_register_codex(_log)
            action_register_opencode(_log)
            action_enable_yolo(_log)
            action_status(_log)
            _log("===== DONE. Restart Claude Code / Codex to load the server. =====\n")
        run_async(seq)

    full = ttk.Button(btns, text="★ Full install (1+2+3)", command=do_all, width=26)
    full.grid(column=1, row=2, padx=4, pady=4, sticky="ew")

    for i in range(3):
        btns.columnconfigure(i, weight=1)

    auto_var = tk.BooleanVar(value=True)
    bottom = ttk.Frame(root)
    bottom.pack(fill="x", padx=12, pady=(0, 8))
    ttk.Checkbutton(bottom, text="Run full install automatically on launch", variable=auto_var).pack(side="left")
    ttk.Label(
        bottom,
        text="  After it finishes, restart Claude Code / Codex.",
        foreground="#666",
    ).pack(side="left")

    log("Starting up...")
    # Fully automatic: kick off dependency install + registration shortly after the
    # window appears, so the user does not have to click anything.
    if "--no-auto" not in sys.argv:
        root.after(600, do_all)
    root.mainloop()


if __name__ == "__main__":
    main()
