import sys
import time
import unittest

from lowlevel_computer_use_mcp import server

if sys.platform == "win32":
    from lowlevel_computer_use_mcp import winio
else:
    winio = None


class HeadlessSafetyBannerInputTests(unittest.TestCase):
    def test_show_input_accepts_a_concrete_instruction(self):
        params = server.ShowHeadlessDesktopInput(
            name="work",
            instruction="Sign in, then tell the agent you are done.",
        )

        self.assertEqual(params.name, "work")
        self.assertIn("Sign in", params.instruction)


@unittest.skipUnless(sys.platform == "win32", "Win32 desktop API required")
class HeadlessSafetyBannerWin32Tests(unittest.TestCase):
    def setUp(self):
        self.desktop_name = f"LowLevelCUSafetyBannerTest_{id(self):x}"
        winio.create_desktop(self.desktop_name)
        self.banner = winio._HeadlessSafetyBanner(
            self.desktop_name,
            "Complete the test step.",
        )
        self.banner.start()

    def tearDown(self):
        self.banner.close()
        winio.close_desktop(self.desktop_name)

    def test_banner_spans_the_top_of_the_desktop(self):
        windows = winio.list_desktop_windows(self.desktop_name)
        banner = next(window for window in windows if window["handle"] == self.banner.hwnd)

        self.assertEqual(banner["title"], "Agent desktop instructions")
        self.assertEqual(banner["height"], 72)
        self.assertGreaterEqual(banner["width"], 640)

    def test_close_message_is_ignored(self):
        hwnd = self.banner.hwnd
        winio.user32.PostMessageW(hwnd, winio.WM_CLOSE, 0, 0)
        time.sleep(0.05)

        self.assertTrue(winio.user32.IsWindow(hwnd))

    def test_emergency_exit_restores_and_removes_banner(self):
        hwnd = self.banner.hwnd
        current = winio.user32.OpenInputDesktop(0, False, winio.GENERIC_ALL)
        self.assertTrue(current)
        winio._saved_input_desktop = int(current)
        winio.user32.PostMessageW(
            hwnd,
            winio.WM_COMMAND,
            winio.EMERGENCY_EXIT_CONTROL_ID,
            0,
        )
        time.sleep(0.05)

        self.assertFalse(winio.user32.IsWindow(hwnd))
        self.assertIsNone(winio._saved_input_desktop)


if __name__ == "__main__":
    unittest.main()
