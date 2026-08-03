import json
import unittest
from unittest.mock import patch

from lowlevel_computer_use_mcp import ahk, server
from lowlevel_computer_use_mcp.process import hidden_subprocess_kwargs

import sys
if sys.platform == "win32":
    from lowlevel_computer_use_mcp import winio
else:
    winio = None


class HeadlessMultiAgentModelTests(unittest.TestCase):
    def test_batch_defaults_are_bounded_and_project_agent_prefix_is_supported(self):
        params = server.CreateHeadlessDesktopsInput(count=3, prefix="project-a-agent-2")
        names = [f"{params.prefix}-{i}" for i in range(1, params.count + 1)]
        self.assertEqual(names, ["project-a-agent-2-1", "project-a-agent-2-2", "project-a-agent-2-3"])

    def test_explicit_names_reject_duplicates_at_backend_boundary(self):
        with self.assertRaises(ValueError):
            server.CreateHeadlessDesktopsInput(names=["same", "same"])

    def test_targeted_hotkey_does_not_require_pyautogui(self):
        params = server.HotkeyInput(keys=["ctrl", "c"], hwnd=1234)
        self.assertEqual(params.hwnd, 1234)
        self.assertTrue(params.prefer_ahk)


class HiddenProcessAndHotkeyTests(unittest.TestCase):
    def test_non_windows_does_not_add_windows_process_flags(self):
        with patch("lowlevel_computer_use_mcp.process.os.name", "posix"):
            self.assertEqual(hidden_subprocess_kwargs(), {})

    def test_ahk_hotkey_translation(self):
        self.assertEqual(ahk.keys_to_text(["ctrl", "shift", "s"]), "^+s")
        self.assertEqual(ahk.keys_to_text(["alt", "enter"]), "!{Enter}")

    def test_json_round_trip_for_batch_payload(self):
        payload = server.CreateHeadlessDesktopsInput(count=2, prefix="repo-agent")
        decoded = json.loads(payload.model_dump_json())
        self.assertEqual(decoded["count"], 2)
        self.assertEqual(decoded["prefix"], "repo-agent")

    def test_lan_json_route_delegates_to_registered_tool(self):
        class Request:
            async def json(self):
                return {"tool": "ahk_status", "arguments": {}}

        import asyncio
        response = asyncio.run(server.api_execute(Request()))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.body)["ok"], True)


@unittest.skipUnless(sys.platform == "win32", "Win32 desktop API required")
class MultiDesktopWin32Tests(unittest.TestCase):
    def setUp(self):
        self.names = [f"LowLevelCUMultiAgent_{id(self):x}_one", f"LowLevelCUMultiAgent_{id(self):x}_two"]
        winio.create_desktops(self.names)

    def tearDown(self):
        for name in self.names:
            winio.close_desktop(name)

    def test_two_desktops_are_independent_and_launch_is_quiet(self):
        listed = {item["name"]: item for item in winio.list_desktops()}
        self.assertTrue(set(self.names).issubset(listed))
        result = winio.launch_on_desktop(self.names[0], "cmd.exe /c exit")
        self.assertFalse(result["terminal_window"])
        self.assertFalse(result["focus_stealing"])


if __name__ == "__main__":
    unittest.main()
