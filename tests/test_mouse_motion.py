import unittest
from types import SimpleNamespace
from unittest.mock import patch

from lowlevel_computer_use_mcp import server


class FakePyAutoGui:
    def __init__(self, x=0, y=0):
        self._pos = SimpleNamespace(x=x, y=y)
        self.moves = []

    def position(self):
        return self._pos

    def moveTo(self, x, y, duration=0):
        self.moves.append((int(x), int(y), duration))
        self._pos = SimpleNamespace(x=int(x), y=int(y))


class MouseMotionTests(unittest.TestCase):
    def test_default_duration_never_resolves_to_zero_without_instant_flag(self):
        self.assertGreaterEqual(server._smooth_duration(None), server._MIN_MOUSE_MOVE_DURATION)
        self.assertEqual(server._smooth_duration(None, instant=True), 0.0)

    def test_smooth_path_contains_intermediate_points_and_final_target(self):
        path = server._smooth_mouse_path(0, 0, 220, 110, 0.25)

        self.assertGreater(len(path), 3)
        self.assertNotEqual(path[0], (220, 110))
        self.assertEqual(path[-1], (220, 110))

    def test_smooth_move_emits_multiple_absolute_moves(self):
        fake = FakePyAutoGui(0, 0)

        with patch.object(server, "pyautogui", fake), patch.object(server.time, "sleep"):
            server._smooth_mouse_move_to(220, 110, duration=0.25)

        self.assertGreater(len(fake.moves), 3)
        self.assertEqual(fake.moves[-1], (220, 110, 0))

    def test_instant_move_emits_only_the_target(self):
        fake = FakePyAutoGui(0, 0)

        with patch.object(server, "pyautogui", fake), patch.object(server.time, "sleep"):
            server._smooth_mouse_move_to(220, 110, instant=True)

        self.assertEqual(fake.moves, [(220, 110, 0)])


if __name__ == "__main__":
    unittest.main()
