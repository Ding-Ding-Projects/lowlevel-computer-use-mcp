import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lowlevel_computer_use_mcp import installer_gui, server


class CheapEntryTests(unittest.TestCase):
    def test_cheap_list_uses_registered_tools_only(self):
        names = server._cheap_tool_names()
        self.assertIn("get_screen_size", names)
        self.assertIn("screenshot", names)
        self.assertNotIn("health", names)
        self.assertNotIn("api_execute", names)

    def test_cheap_usage_does_not_advertise_transport_endpoints(self):
        usage = server._cheap_usage()
        self.assertIn("get_screen_size", usage)
        self.assertNotIn("health\n", usage)
        self.assertNotIn("api_execute\n", usage)


class LegacyRegistrationMigrationTests(unittest.TestCase):
    def _quiet_command_patches(self):
        return (
            patch.object(
                installer_gui,
                "server_command",
                return_value=r"C:\Lowlevel\venv\Scripts\pythonw.exe",
            ),
            patch.object(
                installer_gui,
                "server_args",
                return_value=["-m", "lowlevel_computer_use_mcp.server"],
            ),
        )

    def test_json_migration_removes_only_the_legacy_entry(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "client.json"
            path.write_text(
                json.dumps(
                    {
                        "mcpServers": {
                            "lowlevel-computer-use": {"type": "stdio"},
                            "lowlevel-computer-use-http": {"type": "http"},
                            "other": {"type": "stdio"},
                        }
                    }
                ),
                encoding="utf-8",
            )
            logs = []
            self.assertTrue(
                installer_gui._remove_json_mcp_entry(
                    path, "mcpServers", "lowlevel-computer-use-http", logs.append
                )
            )
            data = json.loads(path.read_text(encoding="utf-8"))

        self.assertIn("lowlevel-computer-use", data["mcpServers"])
        self.assertIn("other", data["mcpServers"])
        self.assertNotIn("lowlevel-computer-use-http", data["mcpServers"])

    def test_toml_migration_removes_one_exact_table(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.toml"
            path.write_text(
                "[mcp_servers.lowlevel-computer-use-http]\n"
                'url = "http://127.0.0.1:8765/mcp"\n\n'
                "[mcp_servers.lowlevel-computer-use]\n"
                'command = "pythonw.exe"\n',
                encoding="utf-8",
            )
            logs = []
            self.assertTrue(
                installer_gui._remove_toml_mcp_entry(
                    path, "lowlevel-computer-use-http", logs.append
                )
            )
            text = path.read_text(encoding="utf-8")

        self.assertNotIn("lowlevel-computer-use-http", text)
        self.assertIn("[mcp_servers.lowlevel-computer-use]", text)
        self.assertIn('command = "pythonw.exe"', text)

    def test_claude_registration_replaces_a_console_launcher(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir)
            (home / ".claude.json").write_text(
                json.dumps(
                    {
                        "mcpServers": {
                            "lowlevel-computer-use": {
                                "command": "lowlevel-computer-use-mcp.exe",
                                "args": [],
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            logs = []
            command_patch, args_patch = self._quiet_command_patches()
            with patch.object(installer_gui.Path, "home", return_value=home), command_patch, args_patch:
                installer_gui._register_claude_json(logs.append)
            data = json.loads((home / ".claude.json").read_text(encoding="utf-8"))

        self.assertEqual(
            data["mcpServers"]["lowlevel-computer-use"]["command"],
            r"C:\Lowlevel\venv\Scripts\pythonw.exe",
        )

    def test_codex_registration_replaces_an_existing_console_table(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir)
            codex_dir = home / ".codex"
            codex_dir.mkdir()
            path = codex_dir / "config.toml"
            path.write_text(
                "[mcp_servers.lowlevel-computer-use]\n"
                "command = 'lowlevel-computer-use-mcp.exe'\n"
                "args = []\n\n"
                "[other]\nvalue = true\n",
                encoding="utf-8",
            )
            logs = []
            command_patch, args_patch = self._quiet_command_patches()
            with (
                patch.object(installer_gui.Path, "home", return_value=home),
                patch.object(installer_gui.shutil, "which", return_value=None),
                command_patch,
                args_patch,
            ):
                installer_gui.action_register_codex(logs.append)
            text = path.read_text(encoding="utf-8")

        self.assertIn(r"command = 'C:\Lowlevel\venv\Scripts\pythonw.exe'", text)
        self.assertIn("[other]", text)
        self.assertNotIn("lowlevel-computer-use-mcp.exe", text)


if __name__ == "__main__":
    unittest.main()
