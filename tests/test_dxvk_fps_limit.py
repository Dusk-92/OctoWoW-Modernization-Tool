import os
import tempfile
import unittest

import dxvk_fps


class DxvkFpsLimitTests(unittest.TestCase):
    def write_config(self, root, text):
        path = os.path.join(root, "dxvk.conf")
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        return path

    def read_config(self, path):
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()

    def test_enable_replaces_bundled_commented_value_and_preserves_other_options(self):
        with tempfile.TemporaryDirectory() as root:
            path = self.write_config(
                root,
                "# DXVK configuration\n"
                "# d3d9.maxFrameRate = 1000\n"
                "dxvk.allowFse = False\n",
            )

            dxvk_fps.apply_dxvk_fps_limit(path, True, 165)
            updated = self.read_config(path)

            self.assertIn("d3d9.maxFrameRate = 165\n", updated)
            self.assertNotIn("# d3d9.maxFrameRate = 1000", updated)
            self.assertIn("dxvk.allowFse = False\n", updated)
            self.assertEqual(updated.count("d3d9.maxFrameRate"), 1)
            self.assertEqual(dxvk_fps.read_dxvk_fps_limit(path), (True, 165))

    def test_disable_comments_the_setting(self):
        with tempfile.TemporaryDirectory() as root:
            path = self.write_config(
                root,
                "d3d9.maxFrameRate = 144\n"
                "dxvk.numCompilerThreads = 4\n",
            )

            dxvk_fps.apply_dxvk_fps_limit(path, False, 144)
            updated = self.read_config(path)

            self.assertIn("# d3d9.maxFrameRate = 144\n", updated)
            self.assertNotIn("\nd3d9.maxFrameRate = 144\n", "\n" + updated)
            self.assertEqual(dxvk_fps.read_dxvk_fps_limit(path), (False, 144))

    def test_duplicate_limit_lines_are_collapsed_to_one(self):
        with tempfile.TemporaryDirectory() as root:
            path = self.write_config(
                root,
                "d3d9.maxFrameRate = 60\n"
                "# d3d9.maxFrameRate = 120\n"
                "dxvk.allowFse = False\n",
            )

            dxvk_fps.apply_dxvk_fps_limit(path, True, 240)
            updated = self.read_config(path)

            self.assertEqual(updated.count("d3d9.maxFrameRate"), 1)
            self.assertIn("d3d9.maxFrameRate = 240\n", updated)
            self.assertIn("dxvk.allowFse = False\n", updated)

    def test_missing_limit_line_is_appended(self):
        with tempfile.TemporaryDirectory() as root:
            path = self.write_config(root, "dxvk.allowFse = False\n")

            dxvk_fps.apply_dxvk_fps_limit(path, True, 75)
            updated = self.read_config(path)

            self.assertIn("dxvk.allowFse = False\n", updated)
            self.assertTrue(updated.endswith("d3d9.maxFrameRate = 75\n"))

    def test_invalid_values_are_rejected_without_modifying_file(self):
        with tempfile.TemporaryDirectory() as root:
            original = "# d3d9.maxFrameRate = 1000\n"
            path = self.write_config(root, original)

            with self.assertRaises(ValueError):
                dxvk_fps.apply_dxvk_fps_limit(path, True, 0)

            self.assertEqual(self.read_config(path), original)

    def test_non_windows_detection_uses_fallback(self):
        if os.name == "nt":
            self.skipTest("Non-Windows fallback test")
        self.assertEqual(dxvk_fps.detect_max_refresh_rate(default=77), 77)


if __name__ == "__main__":
    unittest.main()
