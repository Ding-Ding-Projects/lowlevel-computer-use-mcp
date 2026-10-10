"""Focused environment isolation and Squirrel executable alias controls."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("installer", Path(__file__).with_name("package-installer.py"))
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class Controls(unittest.TestCase):
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
