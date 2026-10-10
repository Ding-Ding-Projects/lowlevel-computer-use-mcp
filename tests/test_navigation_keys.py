import unittest
from unittest.mock import patch
from lowlevel_computer_use_mcp import winio

class NavigationKeyEncodingTests(unittest.TestCase):
    def test_extended_scan_code_sets_bit_24_without_leaking_prefix(self):
        for vk, scan in [(0x21, 0xE049), (0x22, 0xE051), (0x23, 0xE04F), (0x24, 0xE047), (0x25, 0xE04B), (0x26, 0xE048), (0x27, 0xE04D), (0x28, 0xE050), (0x2D, 0xE052), (0x2E, 0xE053), (0x5B, 0xE05B), (0x2C, 0xE037)]:
            with self.subTest(vk=vk), patch.object(winio.user32, 'MapVirtualKeyW', return_value=scan) as mapper:
                down, up = winio._key_lparams(vk)
                mapper.assert_called_once_with(vk, 4)
                self.assertEqual(down, 1 | ((scan & 0xFF) << 16) | (1 << 24))
                self.assertEqual(up, down | (3 << 30))

    def test_regular_keys_keep_extended_bit_clear(self):
        for vk, scan in [(0x09, 0x0F), (0x0D, 0x1C), (0x41, 0x1E), (0x11, 0x1D)]:
            with self.subTest(vk=vk), patch.object(winio.user32, 'MapVirtualKeyW', return_value=scan):
                down, up = winio._key_lparams(vk)
                self.assertEqual(down, 1 | (scan << 16))
                self.assertEqual(down & (1 << 24), 0)
                self.assertEqual(up, down | (3 << 30))

    def test_sender_posts_extended_down_and_up_to_only_requested_target(self):
        with patch.object(winio, 'run_on_window_desktop', side_effect=lambda hwnd, action: action()), patch.object(winio.user32, 'MapVirtualKeyW', return_value=0xE051), patch.object(winio.user32, 'PostMessageW', return_value=1) as post:
            result = winio.send_keys(123, ['pagedown'])
            expected = 1 | (0x51 << 16) | (1 << 24)
            self.assertEqual([call.args for call in post.call_args_list], [(123, winio.WM_KEYDOWN, 0x22, expected), (123, winio.WM_KEYUP, 0x22, expected | (3 << 30))])
            self.assertEqual(result['target_hwnd'], 123)

if __name__ == '__main__':
    unittest.main()
