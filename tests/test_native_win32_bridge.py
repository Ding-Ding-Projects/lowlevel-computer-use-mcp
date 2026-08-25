import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from lowlevel_computer_use_mcp import native_win32
from lowlevel_computer_use_mcp import processes


class NativeBridgeContractTests(unittest.TestCase):
    def test_candidate_paths_include_packaged_native_directory(self):
        candidates = native_win32.candidate_paths()
        self.assertTrue(any(path.parts[-2:] == ("native", "lowlevel_win32_native.dll") for path in candidates))

    def test_non_windows_load_is_explicit(self):
        if os.name == "nt":
            self.skipTest("Non-Windows contract")
        bridge, reason = native_win32.load_native_bridge()
        self.assertIsNone(bridge)
        self.assertIn("only on Windows", reason)

    def test_native_launch_is_console_free_and_targets_named_desktop(self):
        source = (
            Path(__file__).resolve().parents[1] / "native" / "win32_desktop_bridge.cpp"
        ).read_text(encoding="utf-8")
        self.assertIn("CREATE_NO_WINDOW", source)
        self.assertIn('L"WinSta0\\\\" + std::wstring(name)', source)
        self.assertIn("WaitForInputIdle", source)

    def test_supervisor_is_console_free_and_preserves_stdio_bytes(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "native" / "mcp_supervisor.cpp").read_text(encoding="utf-8")
        cmake = (root / "native" / "CMakeLists.txt").read_text(encoding="utf-8")
        self.assertIn("CREATE_NO_WINDOW", source)
        self.assertIn("STARTF_USESHOWWINDOW", source)
        self.assertIn("add_executable(lowlevel_mcp_supervisor WIN32", cmake)
        if sys.platform != "win32":
            return
        supervisor = root / "src" / "lowlevel_computer_use_mcp" / "native" / "lowlevel_mcp_supervisor.exe"
        self.assertTrue(supervisor.is_file(), supervisor)
        payload = b'{"jsonrpc":"2.0","id":1,"method":"ping"}\n'
        child = [
            str(supervisor),
            sys.executable,
            "-c",
            "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read()); sys.stdout.buffer.flush()",
        ]
        completed = subprocess.run(child, input=payload, capture_output=True, timeout=10, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr.decode(errors="replace"))
        self.assertEqual(completed.stdout, payload)

    def test_server_command_prefers_supervisor_and_keeps_python_child(self):
        command, arguments = processes.hidden_server_command()
        if sys.platform == "win32":
            self.assertTrue(command.endswith("lowlevel_mcp_supervisor.exe"), command)
            self.assertTrue(arguments[0].endswith("pythonw.exe"), arguments)
            self.assertEqual(arguments[1:], ["-m", "lowlevel_computer_use_mcp.server"])
        else:
            self.assertEqual(command, sys.executable)
            self.assertEqual(arguments, ["-m", "lowlevel_computer_use_mcp.server"])

    def test_server_command_falls_back_to_pythonw_when_supervisor_is_missing(self):
        if sys.platform != "win32":
            self.skipTest("Windows fallback contract")
        with (
            patch.object(processes, "pythonw_executable", return_value=r"C:\Python\pythonw.exe"),
            patch.object(Path, "is_file", return_value=False),
        ):
            command, arguments = processes.hidden_server_command()
        self.assertEqual(command, r"C:\Python\pythonw.exe")
        self.assertEqual(arguments, ["-m", "lowlevel_computer_use_mcp.server"])

    def test_direct_cli_entry_remains_independent_of_supervisor(self):
        pyproject = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn(
            'lowlevel-computer-use-cheap = "lowlevel_computer_use_mcp.server:cheap_entry"',
            pyproject,
        )


@unittest.skipUnless(sys.platform == "win32", "Native Win32 DLL required")
class NativeBridgeLiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bridge, reason = native_win32.load_native_bridge()
        if cls.bridge is None:
            raise unittest.SkipTest(reason)

    def test_create_launch_close_round_trip(self):
        name = f"LowLevelNative_{os.getpid()}_{id(self):x}"
        try:
            created = self.bridge.create_desktop(name)
            self.assertEqual(created["backend"], "native-cpp")
            self.assertGreater(created["handle"], 0)
            reopened = self.bridge.create_desktop(name)
            self.assertTrue(reopened["already_exists"])
            launched = self.bridge.launch_on_desktop(name, "cmd.exe /d /c exit 0", 1_000)
            self.assertGreater(launched["pid"], 0)
            self.assertEqual(launched["input_idle"], "not-applicable")
        finally:
            closed = self.bridge.close_desktop(name)
            self.assertTrue(closed["closed"])

    def test_invalid_name_fails_before_win32_mutation(self):
        with self.assertRaisesRegex(native_win32.NativeWin32Error, "without slashes"):
            self.bridge.create_desktop("invalid/name")


if __name__ == "__main__":
    unittest.main()
