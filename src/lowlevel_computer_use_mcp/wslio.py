"""Ephemeral WSL (Windows Subsystem for Linux) provisioning.

Spin up a throwaway WSL distro on demand, run Linux commands inside it, then tear
it down. By default a tiny Alpine minirootfs is downloaded and imported (a few MB,
seconds to provision) so existing distros are never touched. You can also clone an
existing distro or import a provided rootfs tar.

All wsl.exe calls run with WSL_UTF8=1 so output is clean UTF-8.
"""

from __future__ import annotations

import gzip
import os
import platform
import re
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any, Optional

from .processes import hidden_subprocess_kwargs

WSL_EXE = "wsl.exe"
ALPINE_LATEST_DIR = "https://dl-cdn.alpinelinux.org/alpine/latest-stable/releases/{arch}/"

# name -> {install_dir, created_at, source}
_TEMP_DISTROS: dict[str, dict[str, Any]] = {}


class WslError(RuntimeError):
    pass


def _arch() -> str:
    m = platform.machine().lower()
    if m in ("amd64", "x86_64"):
        return "x86_64"
    if m in ("arm64", "aarch64"):
        return "aarch64"
    return "x86_64"


def _state_dir() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "lowlevel-cu-wsl"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _decode(b: bytes) -> str:
    if not b:
        return ""
    # WSL_UTF8 should give UTF-8, but fall back to UTF-16LE (legacy wsl.exe output).
    if b"\x00" in b[:64]:
        try:
            return b.decode("utf-16-le")
        except UnicodeDecodeError:
            pass
    return b.decode("utf-8", errors="replace")


def _wsl(args: list[str], timeout: float = 120.0, input_bytes: Optional[bytes] = None) -> tuple[int, str, str]:
    env = {**os.environ, "WSL_UTF8": "1"}
    proc = subprocess.run(
        [WSL_EXE, *args],
        capture_output=True,
        input=input_bytes,
        env=env,
        timeout=timeout,
        check=False,
        **hidden_subprocess_kwargs(),
    )
    return proc.returncode, _decode(proc.stdout), _decode(proc.stderr)


def available() -> dict[str, Any]:
    """Return whether WSL is usable on this host."""
    if os.name != "nt":
        return {"available": False, "reason": "WSL is only available on Windows."}
    if not shutil.which(WSL_EXE):
        return {"available": False, "reason": "wsl.exe not found. Install WSL with `wsl --install`."}
    try:
        rc, out, err = _wsl(["--status"], timeout=30)
        if rc != 0:
            return {"available": False, "reason": (err or out or "wsl --status failed").strip()}
        ver_rc, ver_out, _ = _wsl(["--version"], timeout=30)
        return {"available": True, "status": out.strip(), "version": ver_out.strip()}
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "reason": f"{type(exc).__name__}: {exc}"}


def list_distros() -> list[dict[str, Any]]:
    """List installed WSL distros with state and version."""
    rc, out, err = _wsl(["--list", "--verbose"], timeout=30)
    if rc != 0:
        raise WslError((err or out or "wsl --list failed").strip())
    distros: list[dict[str, Any]] = []
    for line in out.splitlines()[1:]:  # skip header
        line = line.strip()
        if not line:
            continue
        default = line.startswith("*")
        parts = line.lstrip("*").split()
        if len(parts) >= 3:
            distros.append(
                {"name": parts[0], "state": parts[1], "version": parts[2], "default": default}
            )
    return distros


def _discover_alpine_url() -> str:
    arch = _arch()
    listing_url = ALPINE_LATEST_DIR.format(arch=arch)
    try:
        with urllib.request.urlopen(listing_url, timeout=30) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        raise WslError(f"Could not reach Alpine mirror ({listing_url}): {exc}")
    m = re.findall(r"alpine-minirootfs-[0-9.]+-" + re.escape(arch) + r"\.tar\.gz", html)
    if not m:
        raise WslError(f"No minirootfs found at {listing_url}. Pass rootfs_url or clone_from.")
    return listing_url + sorted(set(m))[-1]


def _prepare_rootfs_tar(name: str, rootfs_url: Optional[str], clone_from: Optional[str],
                        base_tar: Optional[str], work: Path) -> Path:
    """Produce an uncompressed .tar suitable for `wsl --import`."""
    tar_path = work / "rootfs.tar"
    if base_tar:
        src = Path(base_tar)
        if not src.exists():
            raise WslError(f"base_tar not found: {src}")
        if src.suffix == ".gz":
            with gzip.open(src, "rb") as fi, open(tar_path, "wb") as fo:
                shutil.copyfileobj(fi, fo)
            return tar_path
        return src
    if clone_from:
        rc, _out, err = _wsl(["--export", clone_from, str(tar_path)], timeout=1800)
        if rc != 0:
            raise WslError(f"Failed to export '{clone_from}': {err.strip()}")
        return tar_path
    # Default: download Alpine minirootfs and gunzip it.
    url = rootfs_url or _discover_alpine_url()
    gz_path = work / "rootfs.tar.gz"
    try:
        urllib.request.urlretrieve(url, gz_path)
    except Exception as exc:  # noqa: BLE001
        raise WslError(f"Failed to download rootfs from {url}: {exc}")
    with gzip.open(gz_path, "rb") as fi, open(tar_path, "wb") as fo:
        shutil.copyfileobj(fi, fo)
    return tar_path


def create_temp(name: Optional[str] = None, rootfs_url: Optional[str] = None,
                clone_from: Optional[str] = None, base_tar: Optional[str] = None,
                version: int = 2, timeout: float = 1800.0) -> dict[str, Any]:
    """Provision a throwaway WSL distro and register it for later teardown."""
    if os.name != "nt":
        raise WslError("WSL is only available on Windows.")
    name = name or f"llcu-tmp-{int(time.time())}-{os.getpid() & 0xFFFF:04x}"
    if any(d["name"] == name for d in list_distros()):
        raise WslError(f"A distro named '{name}' already exists.")
    install_dir = _state_dir() / name
    install_dir.mkdir(parents=True, exist_ok=True)
    work = install_dir / "_work"
    work.mkdir(exist_ok=True)
    try:
        tar_path = _prepare_rootfs_tar(name, rootfs_url, clone_from, base_tar, work)
        rc, out, err = _wsl(
            ["--import", name, str(install_dir), str(tar_path), "--version", str(version)],
            timeout=timeout,
        )
        if rc != 0:
            raise WslError(f"wsl --import failed: {(err or out).strip()}")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    source = "base_tar" if base_tar else ("clone:" + clone_from if clone_from else "alpine")
    _TEMP_DISTROS[name] = {"install_dir": str(install_dir), "created_at": time.time(), "source": source}
    return {"name": name, "install_dir": str(install_dir), "source": source, "version": version}


def run(distro: str, command: str, user: Optional[str] = None, cwd: Optional[str] = None,
        timeout: float = 120.0) -> dict[str, Any]:
    """Run a shell command inside a WSL distro and capture output."""
    if os.name != "nt":
        raise WslError("WSL is only available on Windows.")
    args = ["-d", distro]
    if user:
        args += ["-u", user]
    full = command if not cwd else f"cd {shlex_quote(cwd)} && {command}"
    args += ["--", "/bin/sh", "-lc", full]
    rc, out, err = _wsl(args, timeout=timeout)
    return {"distro": distro, "returncode": rc, "stdout": out, "stderr": err}


def shlex_quote(s: str) -> str:
    if not s:
        return "''"
    if re.match(r"^[A-Za-z0-9_@%+=:,./-]+$", s):
        return s
    return "'" + s.replace("'", "'\"'\"'") + "'"


def destroy(name: str, remove_files: bool = True) -> dict[str, Any]:
    """Terminate and unregister a distro, deleting its files."""
    if os.name != "nt":
        raise WslError("WSL is only available on Windows.")
    _wsl(["--terminate", name], timeout=60)
    rc, out, err = _wsl(["--unregister", name], timeout=120)
    info = _TEMP_DISTROS.pop(name, None)
    if remove_files and info:
        shutil.rmtree(info["install_dir"], ignore_errors=True)
    if rc != 0:
        raise WslError(f"wsl --unregister failed: {(err or out).strip()}")
    return {"name": name, "destroyed": True}


def list_temp() -> list[dict[str, Any]]:
    """List throwaway distros provisioned in this server session."""
    return [{"name": k, **v} for k, v in _TEMP_DISTROS.items()]


def destroy_all() -> dict[str, Any]:
    """Tear down every throwaway distro this session created."""
    destroyed = []
    for name in list(_TEMP_DISTROS):
        try:
            destroy(name)
            destroyed.append(name)
        except WslError:
            pass
    return {"destroyed": destroyed, "count": len(destroyed)}
