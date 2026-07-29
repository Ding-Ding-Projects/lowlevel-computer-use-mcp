import asyncio
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lowlevel_computer_use_mcp import processes, server


class FocusProtectionTests(unittest.TestCase):
    def assert_focus_blocked(self, result: str) -> None:
        payload = json.loads(result)
        self.assertFalse(payload["ok"])
        self.assertTrue(payload["focus_protected"])

    def test_foreground_pointer_keyboard_and_handoff_are_blocked_by_default(self):
        calls = [
            server.mouse_move(server.MoveInput(x=1, y=1)),
            server.mouse_click(server.ClickInput(x=1, y=1)),
            server.mouse_drag(server.DragInput(end_x=1, end_y=1)),
            server.mouse_scroll(server.ScrollInput(amount=1)),
            server.type_text(server.TypeInput(text="x")),
            server.press_keys(server.HotkeyInput(keys=["enter"])),
            server.show_window(server.ShowWindowInput(hwnd=1)),
            server.show_headless_desktop(server.ShowHeadlessDesktopInput(name="work")),
        ]
        for call in calls:
            with self.subTest(call=call):
                self.assert_focus_blocked(asyncio.run(call))

    def test_explicit_confirmation_is_preserved_in_models(self):
        self.assertTrue(
            server.MoveInput(
                x=1, y=1, confirm_focus_disruption=True
            ).confirm_focus_disruption
        )
        self.assertTrue(
            server.ShowHeadlessDesktopInput(
                name="work", confirm_focus_disruption=True
            ).confirm_focus_disruption
        )

    def test_server_instructions_make_headless_the_first_choice(self):
        self.assertIn("HEADLESS FIRST", server.SERVER_INSTRUCTIONS)
        self.assertIn("focus-protected by default", server.SERVER_INSTRUCTIONS)


class HiddenProcessTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Windows process flags required")
    def test_windows_child_process_policy_hides_windows_and_consoles(self):
        kwargs = processes.hidden_subprocess_kwargs()
        self.assertEqual(
            kwargs["creationflags"] & processes.CREATE_NO_WINDOW,
            processes.CREATE_NO_WINDOW,
        )
        self.assertEqual(kwargs["startupinfo"].wShowWindow, subprocess.SW_HIDE)
        self.assertTrue(kwargs["startupinfo"].dwFlags & subprocess.STARTF_USESHOWWINDOW)

    @unittest.skipUnless(os.name == "nt", "Windows pythonw policy required")
    def test_console_free_server_launcher_fails_closed_without_pythonw(self):
        with patch(
            "lowlevel_computer_use_mcp.processes.Path.exists", return_value=False
        ):
            with self.assertRaises(FileNotFoundError):
                processes.pythonw_executable()

    @unittest.skipIf(os.name == "nt", "Non-Windows behavior")
    def test_non_windows_process_policy_is_a_noop(self):
        self.assertEqual(processes.hidden_subprocess_kwargs(), {})

    def test_user_startup_registration_uses_console_free_python(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            script_path = Path(temp_dir) / "LowLevelComputerUseMCP.vbs"
            with (
                patch.object(
                    server,
                    "hidden_server_command",
                    return_value=(r"C:\Python\pythonw.exe", []),
                ),
                patch.object(server, "_startup_script_path", return_value=script_path),
            ):
                result = server._install_startup(
                    http=True, host="127.0.0.1", port=8765, run_as_admin=False
                )
            body = script_path.read_text(encoding="utf-16")

        self.assertTrue(result["ok"])
        self.assertIn(r"C:\Python\pythonw.exe", body)
        self.assertIn("-m lowlevel_computer_use_mcp.server", body)
        self.assertIn("shell.Run", body)
        self.assertIn(", 0, False", body)
        self.assertNotIn("uv run", body)

    def test_elevated_startup_registration_uses_console_free_python(self):
        with (
            patch.object(
                server,
                "hidden_server_command",
                return_value=(r"C:\Python\pythonw.exe", []),
            ),
            patch.object(
                server,
                "_run_powershell",
                return_value={"ok": True, "returncode": 0, "output": "ok"},
            ) as run,
        ):
            server._install_startup(
                http=True, host="127.0.0.1", port=8765, run_as_admin=True
            )

        body = run.call_args.args[0]
        self.assertIn("-Execute 'C:\\Python\\pythonw.exe'", body)
        self.assertIn("-m lowlevel_computer_use_mcp.server", body)
        self.assertNotIn("uv run", body)

    def test_startup_status_recognizes_user_launcher(self):
        with patch.object(
            server,
            "_startup_status",
            return_value={
                "ok": True,
                "returncode": 0,
                "output": "STARTUP_SCRIPT|Installed=true|Path=C:\\startup.vbs",
            },
        ):
            payload = json.loads(asyncio.run(server.startup_status()))

        self.assertTrue(payload["installed"])
        self.assertEqual(payload["method"], "startup-folder-pythonw")

    @unittest.skipUnless(os.name == "nt", "PowerShell behavior is Windows-only")
    def test_powershell_nonterminating_errors_become_failures(self):
        result = server._run_powershell(
            "Write-Error 'expected test failure'", require_admin=False
        )

        self.assertFalse(result["ok"])
        self.assertNotEqual(result["returncode"], 0)


if __name__ == "__main__":
    unittest.main()
