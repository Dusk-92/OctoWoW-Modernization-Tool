import os
import tempfile
import unittest
from unittest import mock

import setup_tool_dynamic


class _Var:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


class FarclipConfigSyncTests(unittest.TestCase):
    def _tool(self, farclip=777):
        tool = object.__new__(setup_tool_dynamic.ModernWowSetupTool)
        tool.vt_farclip = _Var(farclip)
        return tool

    @staticmethod
    def _add_numeric_vars(tool):
        tool.vt_fov = _Var(1.9199)
        tool.vt_frill = _Var(300)
        tool.vt_nameplate = _Var(41)
        tool.vt_maxcam = _Var(100)
        tool.vt_soundchan = _Var(64)

    def test_executable_farclip_ceiling_is_always_3000(self):
        tool = self._tool(777)
        self._add_numeric_vars(tool)
        desired = tool._desired_normalized_values()
        self.assertEqual(desired["farclip"], 3000.0)

        tool.vt_farclip = _Var(3000)
        desired = tool._desired_normalized_values()
        self.assertEqual(desired["farclip"], 3000.0)

    def test_farclip_above_3000_is_rejected_even_with_direct_internal_call(self):
        tool = self._tool(5000)
        self._add_numeric_vars(tool)
        with self.assertRaisesRegex(RuntimeError, "Farclip"):
            tool._desired_normalized_values()

    def test_normalization_signature_bump_forces_existing_install_refresh(self):
        tool = self._tool(777)
        self._add_numeric_vars(tool)
        tool.vt_quickloot = _Var(True)
        tool.vt_bg_sound = _Var(True)
        tool.vt_laa = _Var(True)
        tool.vt_cam_fix = _Var(True)
        tool.vt_crossfaction_res = _Var(False)
        tool.vt_custom_glues = _Var(True)
        tool.vt_bluemoon = _Var(False)
        signature = tool._vanilla_tweaks_signature()
        self.assertEqual(signature["selected_patch_normalization"], 4)
        self.assertEqual(signature["farclip"], 3000)

        tool.vt_farclip = _Var(1500)
        runtime_changed = tool._vanilla_tweaks_signature()
        self.assertEqual(runtime_changed["farclip"], 3000)
        self.assertEqual(signature, runtime_changed)

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

    def test_farclip_cvar_rejects_value_above_fixed_ceiling(self):
        tool = self._tool(3001)
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(RuntimeError, "3000"):
                tool._configure_farclip_cvar(root)
            self.assertFalse(os.path.exists(os.path.join(root, "WTF", "Config.wtf")))

    def test_configure_script_memory_also_synchronizes_farclip(self):
        tool = self._tool(777)
        tool.core_plugins = {"SuperWoWhook.dll": _Var(False)}
        with mock.patch.object(
            setup_tool_dynamic._ModernWowSetupToolCore,
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
