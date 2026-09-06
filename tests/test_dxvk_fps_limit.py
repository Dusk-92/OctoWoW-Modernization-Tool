import ctypes
import os
import tempfile
import types
import unittest
from unittest import mock

import dxvk_fps
import setup_tool_dynamic
import setup_tool_responsive


class FakeVar:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class DxvkFpsLimitTests(unittest.TestCase):
    def write_config(self, root, text):
        path = os.path.join(root, "dxvk.conf")
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        return path

    def read_config(self, path):
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()

    def detect_with_fake_displays(self, devices, default=77):
        """Run Windows display detection against deterministic fake Win32 APIs."""
        # Each record is (device name, state flags, refresh rate, settings_ok).
        def enum_display_devices(_device, index, device_ptr, _flags):
            if index >= len(devices):
                return False
            name, state_flags, _rate, _settings_ok = devices[index]
            device_ptr._obj.DeviceName = name
            device_ptr._obj.StateFlags = state_flags
            return True

        def enum_display_settings(device_name, _mode, mode_ptr):
            for name, _state_flags, rate, settings_ok in devices:
                if name != device_name:
                    continue
                if not settings_ok:
                    return False
                mode_ptr._obj.dmDisplayFrequency = rate
                return True
            return False

        fake_user32 = types.SimpleNamespace(
            EnumDisplayDevicesW=enum_display_devices,
            EnumDisplaySettingsW=enum_display_settings,
        )
        fake_windll = types.SimpleNamespace(user32=fake_user32)

        with mock.patch.object(dxvk_fps.os, "name", "nt"), mock.patch.object(
            ctypes,
            "windll",
            fake_windll,
            create=True,
        ):
            return dxvk_fps.detect_max_refresh_rate(default=default)

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

    def test_signed_legacy_values_are_replaced_without_duplicates(self):
        with tempfile.TemporaryDirectory() as root:
            path = self.write_config(
                root,
                "d3d9.maxFrameRate = -120\n"
                "# d3d9.maxFrameRate = +90\n"
                "dxvk.allowFse = False\n",
            )

            dxvk_fps.apply_dxvk_fps_limit(path, True, 165)
            updated = self.read_config(path)

            self.assertEqual(updated.count("d3d9.maxFrameRate"), 1)
            self.assertIn("d3d9.maxFrameRate = 165\n", updated)
            self.assertNotIn("-120", updated)
            self.assertNotIn("+90", updated)
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

    def test_refresh_detection_uses_fastest_attached_valid_display(self):
        detected = self.detect_with_fake_displays(
            [
                ("DISPLAY1", 0x00000001, 60, True),
                # Faster but not attached to the desktop: must be ignored.
                ("DISPLAY2", 0x00000000, 360, True),
                ("DISPLAY3", 0x00000001, 165, True),
                # Windows unknown/default frequency: must be ignored.
                ("DISPLAY4", 0x00000001, 1, True),
                # Current settings query failed: must be ignored.
                ("DISPLAY5", 0x00000001, 240, False),
            ],
            default=77,
        )
        self.assertEqual(detected, 165)

    def test_refresh_detection_falls_back_when_no_usable_display_rate_exists(self):
        detected = self.detect_with_fake_displays(
            [
                ("DISPLAY1", 0x00000000, 240, True),
                ("DISPLAY2", 0x00000001, 0, True),
                ("DISPLAY3", 0x00000001, 1, True),
                ("DISPLAY4", 0x00000001, 165, False),
            ],
            default=77,
        )
        self.assertEqual(detected, 77)

    def test_refresh_detection_always_returns_a_positive_integer(self):
        detected = dxvk_fps.detect_max_refresh_rate(default=77)
        self.assertIsInstance(detected, int)
        self.assertGreater(detected, 0)

    @mock.patch.object(setup_tool_dynamic.ModernWowSetupTool, "configure_dxvk")
    @mock.patch("setup_tool_responsive.dxvk_fps.apply_dxvk_fps_limit")
    def test_directx9_never_applies_fps_config(self, apply_limit, parent_configure):
        tool = setup_tool_responsive.ResponsiveModernWowSetupTool.__new__(
            setup_tool_responsive.ResponsiveModernWowSetupTool
        )
        tool.rendering_mode = FakeVar("directx9")
        tool.limit_dxvk_fps = FakeVar(True)
        tool.dxvk_fps_limit = FakeVar(165)

        tool.configure_dxvk("C:/WoW")

        parent_configure.assert_called_once_with("C:/WoW")
        apply_limit.assert_not_called()

    @mock.patch.object(setup_tool_dynamic.ModernWowSetupTool, "configure_dxvk")
    @mock.patch("setup_tool_responsive.dxvk_fps.apply_dxvk_fps_limit")
    def test_dxvk_applies_selected_fps_value(self, apply_limit, parent_configure):
        tool = setup_tool_responsive.ResponsiveModernWowSetupTool.__new__(
            setup_tool_responsive.ResponsiveModernWowSetupTool
        )
        tool.rendering_mode = FakeVar("dxvk")
        tool.limit_dxvk_fps = FakeVar(True)
        tool.dxvk_fps_limit = FakeVar(144)

        tool.configure_dxvk("C:/WoW")

        parent_configure.assert_called_once_with("C:/WoW")
        apply_limit.assert_called_once_with(
            os.path.join("C:/WoW", "dxvk.conf"),
            True,
            144,
        )


if __name__ == "__main__":
    unittest.main()
