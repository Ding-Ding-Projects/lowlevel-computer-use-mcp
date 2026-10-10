"""Run the existing Squirrel producer without modifying tracked catalog data."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unsigned_environment(environment):
    result = {key: value for key, value in environment.items()
              if not key.upper().startswith(("CSC_", "WIN_CSC_", "AZURE_SIGN_"))}
    result["CSC_IDENTITY_AUTO_DISCOVERY"] = "false"
    return result


def ensure_setup_alias(bundle):
    executables = list(bundle.glob("*.exe"))
    if len(executables) != 1:
        raise RuntimeError("Expected one generated Squirrel setup executable")
    setup = bundle / "Setup.exe"
    if executables[0].resolve() != setup.resolve():
        shutil.copy2(executables[0], setup)
    return setup


class ChildExit(Exception):
    def __init__(self, code):
        self.code = code


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--node", type=Path, required=True)
    parser.add_argument("--npm-cli", type=Path, required=True)
    parser.add_argument("--codename", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    run = root / "dist" / "installer" / uuid.uuid4().hex
    run.mkdir(parents=True)
    receipt = {"schemaVersion": 1, "startedUtc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "source": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
               "nodeSha256": digest(args.node), "npmCliSha256": digest(args.npm_cli),
               "output": str(run.relative_to(root)), "phases": [], "unsignedRequested": True}
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=root).split(b"\0")
    def inputs():
        return {os.fsdecode(name): digest(root / os.fsdecode(name)) for name in tracked
                if name and (root / os.fsdecode(name)).is_file()}
    before = inputs()
    receipt["inputsBefore"] = before
    exit_code = 1
    try:
        if subprocess.check_output(["git", "status", "--porcelain"], cwd=root).strip():
            raise RuntimeError("Installer production requires unchanged committed source")
        receipt["sourceTree"] = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=root, text=True).strip()
        receipt["indexTree"] = subprocess.check_output(["git", "write-tree"], cwd=root, text=True).strip()
        environment = unsigned_environment(os.environ)
        def npm(arguments, phase):
            command = [str(args.node), str(args.npm_cli), *arguments]
            code = subprocess.run(command, cwd=root, env=environment).returncode
            receipt["phases"].append({"phase": phase, "exitCode": code})
            return code
        exit_code = npm(["ci", "--prefix", "electron"], "locked-dependencies")
        if exit_code:
            raise ChildExit(exit_code)
        # Override only packaging configuration, leaving product source untouched.
        config = {"directories": {"output": str(run / "payload")},
                  "win": {"signAndEditExecutable": False}, "forceCodeSigning": False}
        if args.codename:
            data = json.loads(args.codename.read_text(encoding="utf-8-sig"))
            if not isinstance(data, dict) or not isinstance(data.get("codeName"), str):
                raise RuntimeError("Invalid release code-name document")
            catalog = run / "catalog"
            catalog.mkdir()
            staged = catalog / "release-codename.json"
            staged.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            config["files"] = ["**/*", "!release-codename.json", "!docs/screenshots/**", "!node_modules/.cache/**",
                               {"from": str(catalog), "to": ".", "filter": ["release-codename.json"]}]
            receipt["catalogSha256"] = digest(staged)
        config_path = run / "builder.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        receipt["configurationSha256"] = digest(config_path)
        exit_code = npm(["run", "package", "--prefix", "electron", "--", "--config", str(config_path)], "squirrel-package")
        if exit_code:
            raise ChildExit(exit_code)
        bundle = run / "payload/squirrel-windows"
        if not (bundle / "RELEASES").is_file() or not list(bundle.glob("*-full.nupkg")):
            raise RuntimeError("Required Squirrel RELEASES/full package is absent")
        ensure_setup_alias(bundle)
        receipt["assets"] = [{"path": str(p.relative_to(root)), "bytes": p.stat().st_size, "sha256": digest(p)}
                             for p in bundle.iterdir() if p.is_file()]
        receipt["sourceUnchanged"] = inputs() == before
        if not receipt["sourceUnchanged"]:
            raise RuntimeError("Tracked source changed during installer production")
        print("Squirrel output: " + str(bundle))
        exit_code = 0
    except ChildExit as exc:
        exit_code = exc.code
    except Exception as exc:
        receipt["errorType"] = type(exc).__name__
        receipt["error"] = str(exc)
        exit_code = 1
    finally:
        receipt["inputsAfter"] = inputs()
        receipt["sourceAfter"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        receipt["indexAfter"] = subprocess.check_output(["git", "write-tree"], cwd=root, text=True).strip()
        receipt["sourceUnchanged"] = before == receipt["inputsAfter"] and receipt["sourceAfter"] == receipt["source"] and receipt["indexAfter"] == receipt.get("indexTree", receipt["indexAfter"])
        if not receipt["sourceUnchanged"]:
            exit_code = 1
        receipt["exitCode"] = exit_code
        receipt["completedUtc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        (run / "receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
