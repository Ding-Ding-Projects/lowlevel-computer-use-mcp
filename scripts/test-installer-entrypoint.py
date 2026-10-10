"""Focused environment isolation and Squirrel executable alias controls."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
import json
import subprocess

spec = importlib.util.spec_from_file_location("installer", Path(__file__).with_name("package-installer.py"))
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class Controls(unittest.TestCase):
    def test_real_supported_packaging_configuration_survives_overrides(self):
        root = Path(__file__).resolve().parents[1]
        base = json.loads((root / "electron/package.json").read_text())["build"]
        before = json.loads(json.dumps(base))
        config = installer.packaging_configuration(base, Path("fixture-output"))
        self.assertEqual(base, before)
        for key in ["appId", "productName", "artifactName", "files", "squirrelWindows"]:
            self.assertEqual(config[key], base[key], key)
        self.assertEqual(config["win"]["target"], [{"target": "squirrel", "arch": ["x64"]}])
        self.assertTrue(config["squirrelWindows"]["iconUrl"].startswith("https://"))
        self.assertFalse(config["win"]["signAndEditExecutable"])
        self.assertFalse(config["forceCodeSigning"])
        self.assertEqual(config["directories"]["output"], "fixture-output")

    def test_installer_silent_arguments_do_not_bind_codename(self):
        header = Path(__file__).with_name("build-installer-root.ps1").read_text().split("$ErrorActionPreference", 1)[0]
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / "arguments.ps1"
            fixture.write_text(header + '\n@{codename=$ReleaseCodename;silent=[bool]$Silent}|ConvertTo-Json -Compress\n')
            for arguments, expected in [(["/s"], ""), (["--silent"], ""),
                                        (["/s", "-ReleaseCodename", "fixture.json"], "fixture.json")]:
                run = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(fixture), *arguments], capture_output=True, text=True)
                self.assertEqual(run.returncode, 0, run.stderr)
                result = json.loads(run.stdout)
                self.assertEqual(result["codename"], expected)
                self.assertTrue(result["silent"])

    def test_unknown_root_argument_rejected_before_bootstrap(self):
        header = Path(__file__).with_name("build-installer-root.ps1").read_text().split("$ErrorActionPreference", 1)[0]
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / "arguments.ps1"
            fixture.write_text(header + '\nWrite-Output "BOOTSTRAP_REACHED"\n')
            run = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(fixture), "unexpected"], capture_output=True, text=True)
            self.assertNotEqual(run.returncode, 0)
            self.assertNotIn("BOOTSTRAP_REACHED", run.stdout)

    def test_signing_values_removed_only_from_child_copy(self):
        parent = {"CSC_LINK": "synthetic", "WIN_CSC_KEY_PASSWORD": "synthetic",
                  "Azure_Sign_Value": "synthetic", "PATH": "fixture", "GH_TOKEN": "synthetic"}
        child = installer.unsigned_environment(parent)
        self.assertEqual(parent["CSC_LINK"], "synthetic")
        self.assertNotIn("CSC_LINK", child)
        self.assertNotIn("WIN_CSC_KEY_PASSWORD", child)
        self.assertNotIn("Azure_Sign_Value", child)
        self.assertEqual(child["CSC_IDENTITY_AUTO_DISCOVERY"], "false")
        self.assertEqual(child["PATH"], parent["PATH"])

    def test_setup_name_does_not_copy_itself(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Setup.exe").write_bytes(b"synthetic-executable")
            self.assertEqual(installer.ensure_setup_alias(root), root / "Setup.exe")
            self.assertEqual((root / "Setup.exe").read_bytes(), b"synthetic-executable")

    def test_named_setup_creates_exact_byte_alias(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "named-setup.exe").write_bytes(b"synthetic-executable")
            alias = installer.ensure_setup_alias(root)
            self.assertEqual(alias.read_bytes(), (root / "named-setup.exe").read_bytes())

    def test_missing_or_multiple_generated_executables_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(RuntimeError): installer.ensure_setup_alias(root)
            (root / "one.exe").touch()
            (root / "two.exe").touch()
            with self.assertRaises(RuntimeError): installer.ensure_setup_alias(root)


if __name__ == "__main__":
    unittest.main()
