import os
import tempfile
import unittest
from unittest import mock

import setup_tool_dynamic
import setup_tool_responsive


class _Var:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


class FarclipConfigSyncTests(unittest.TestCase):
    def _tool(self, farclip=777):
        tool = object.__new__(setup_tool_responsive.ResponsiveModernWowSetupTool)
        tool.vt_farclip = _Var(farclip)
        return tool

    def test_executable_farclip_ceiling_has_3000_floor(self):
        tool = self._tool()
        with mock.patch.object(
            setup_tool_dynamic.ModernWowSetupTool,
            "_desired_normalized_values",
            return_value={"farclip": 777.0},
        ):
            desired = tool._desired_normalized_values()
        self.assertEqual(desired["farclip"], 3000.0)

    def test_executable_farclip_ceiling_keeps_explicit_value_above_3000(self):
        tool = self._tool(5000)
        with mock.patch.object(
            setup_tool_dynamic.ModernWowSetupTool,
            "_desired_normalized_values",
            return_value={"farclip": 5000.0},
        ):
            desired = tool._desired_normalized_values()
        self.assertEqual(desired["farclip"], 5000.0)

    def test_existing_farclip_cvar_is_replaced_without_touching_other_settings(self):
        tool = self._tool(777)
        with tempfile.TemporaryDirectory() as root:
            wtf_dir = os.path.join(root, "WTF")
            os.makedirs(wtf_dir)
            config_path = os.path.join(wtf_dir, "Config.wtf")
            with open(config_path, "w", encoding="utf-8") as handle:
                handle.write('SET locale "enUS"\nSET farclip "2100"\nSET gxWindow "1"\n')

            tool._configure_farclip_cvar(root)

            with open(config_path, "r", encoding="utf-8") as handle:
                result = handle.read()

            self.assertIn('SET locale "enUS"', result)
            self.assertIn('SET gxWindow "1"', result)
            self.assertIn('SET farclip "777"', result)
            self.assertNotIn('SET farclip "2100"', result)

    def test_missing_farclip_cvar_is_appended(self):
        tool = self._tool(1500)
        with tempfile.TemporaryDirectory() as root:
            wtf_dir = os.path.join(root, "WTF")
            os.makedirs(wtf_dir)
            config_path = os.path.join(wtf_dir, "Config.wtf")
            with open(config_path, "w", encoding="utf-8") as handle:
                handle.write('SET locale "enUS"')

            tool._configure_farclip_cvar(root)

            with open(config_path, "r", encoding="utf-8") as handle:
                result = handle.read()

            self.assertEqual(
                result,
                'SET locale "enUS"\nSET farclip "1500"\n',
            )

    def test_missing_config_wtf_is_created(self):
        tool = self._tool(1000)
        with tempfile.TemporaryDirectory() as root:
            tool._configure_farclip_cvar(root)
            config_path = os.path.join(root, "WTF", "Config.wtf")
            with open(config_path, "r", encoding="utf-8") as handle:
                result = handle.read()
            self.assertEqual(result, 'SET farclip "1000"\n')

    def test_configure_script_memory_also_synchronizes_farclip(self):
        tool = self._tool(777)
        with mock.patch.object(
            setup_tool_dynamic.ModernWowSetupTool,
            "configure_script_memory",
        ) as parent_configure, mock.patch.object(
            tool,
            "_configure_farclip_cvar",
        ) as sync_farclip:
            tool.configure_script_memory("C:/WoW")

        parent_configure.assert_called_once_with("C:/WoW")
        sync_farclip.assert_called_once_with("C:/WoW")


if __name__ == "__main__":
    unittest.main()
